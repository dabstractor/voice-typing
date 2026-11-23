"""voice_typing.feedback — state-file writer + Hyprland notify (PRD §4.6).

Feedback is the daemon's live-state publisher. It writes a small JSON snapshot of the
current voice-typing session (listening flag, VAD phase, latest partial, last final,
timestamp) to an atomic state file, and fires fire-and-forget `hyprctl notify` popups
on the events that are NOT spammy: listening-start, each final, listening-stop, and (for a
cold model load) a one-shot 'Loading…' toast before the start.

STATE FILE (PRD §4.6), written atomically (tempfile + os.replace) to
$XDG_RUNTIME_DIR/voice-typing/state.json (overridable via feedback.state_file):
    {"listening": true, "phase": "speaking", "models_loaded": true, "mode": "lite", "ducked": false,
     "delivery_mode": "stream-edit", "delivery_state": "inactive", "delivery_reason": "",
     "last_confirmed_op": "", "partial": "...", "last_final": "...", "ts": 1783718400.123}
DELIVERY FIELDS (PRD §4.2sexies R.5, P1.M3.T3.S2 — surface only, no writer wired yet):
`delivery_mode` mirrors the configured bulk-delivery path ("stream-edit" | "bulk-text"); the
seed is the config-default LITERAL — the bulk wiring (P1.M6.T2.S1) re-seeds it from
[output] delivery at boot. `delivery_state` is the R.5 taxonomy
(inactive | active | unsupported | fault); `delivery_reason` is ONE concise reason;
`last_confirmed_op` is the last APPLIED bulk op as counts+times (verb + ids + revision +
elapsed ms). reason/op pass through _sanitize_status_text (whitespace-collapsed, ≤160
chars) so state NEVER carries recognition text or the surrounding user document, and
`voicectl status` can render them as one line each. Written ONLY by the bulk wiring
(P1.M4/P1.M6 setters) — until then the seeds are the truthful "surface unwired" values.
"ducked" (PRD §4.2quinquies, P1.M2.T3.S1) mirrors the DESIRED media-ducking state —
the crash-safety signal a post-crash boot reads to self-heal a stuck duck (T3.S2).
While models are not yet loaded (boot) or mid-load, phase is 'unloaded' or 'loading' and
models_loaded is false (§4.2bis); once loaded, phase cycles idle/listening/speaking.
Consumed by `voicectl status` and polled by the E2E tests (which verify finals through it).

NOTIFICATION DISCIPLINE (the #1 contract — PRD §4.6 inline example is SUPERSEDED):
Hyprland notifications are NOT replaceable by ID, so per-partial popups would stack into
unreadable spam. Partials go to the state file ONLY. hyprctl popups
fire EXCLUSIVELY on:
  - listening-start  -> "Recording"     (set_listening False->True transition)
  - each final       -> "✔ <text>"      (record_final; GATED by notify_on_final — the text is
                                          already typed into the focused window, so this popup is optional)
  - listening-stop   -> "Recording Stopped" (set_listening True->False transition; ANY disarm)
  - cold model load  -> "Loading…" (Feedback.notify, BEFORE the lazy first-arm model load). The
                        daemon fires this ONCE per session so the hotkey isn't a silent ~1–3 s gap;
                        the load is then confirmed by the normal "Recording" start toast. Warm arms
                        (models resident) skip it. All of these are transient hyprctl toasts.
NEVER on update_partial. NEVER on set_phase (VAD phase flips are not start/final/stop events).

THROTTLE: update_partial is capped at >=10 Hz max (min 0.1 s between disk writes). The
in-memory partial is ALWAYS updated (so the next flush captures the latest words); only
the disk write is throttled. set_phase / record_final / set_listening always write.

ATOMIC WRITE: tempfile.mkstemp(dir=<target dir>) + os.replace(tmp, target) is a
same-filesystem atomic rename (POSIX) — a concurrent reader (voicectl status, the E2E
pollers) never sees a half-written file. mkstemp creates the file mode 0o600 (Python 3 default) →
the renamed state.json inherits 0o600. Parent dir makedirs(exist_ok=True, mode=0o700).

THREAD SAFETY: Feedback methods are called from RealtimeSTT callback threads (partial/
final) and the control-socket thread (set_listening). on_final is serialized by the
daemon's _on_final_lock (VoiceTypingDaemon). Additionally, self._state dict updates are
individually atomic in CPython, and _write() uses tempfile + os.replace (atomic at OS
level) — a torn write is impossible. Feedback itself needs no Lock (it relies on these
atomic primitives; a lock here would risk deadlock if a future caller recurses).

CONSUMES: voice_typing.config.FeedbackConfig (P1.M2.T1.S1): state_file, hypr_notify, notify_ms, notify_on_final.
  resolved_state_file() is the SINGLE source of truth for the path — called lazily inside
  _write() (NOT __init__) because XDG_RUNTIME_DIR is unset outside real sessions.
CONSUMED BY: daemon partial/state callbacks (P1.M4.T1.S1) and on_final (P1.M4.T1.S2) as:
    fb = feedback.Feedback(cfg.feedback)
    fb.set_listening(False)                 # startup (not-listening, per PRD §4.9)
    # on_realtime_transcription_stabilized: fb.update_partial(text)
    # on_recording_start/on_vad_detect_start: fb.set_phase("listening"|"speaking"|"idle")
    # on_final: fb.record_final(text)
    # toggle/start/stop socket cmd: fb.set_listening(True|False)

PURE STDLIB (json, os, subprocess, tempfile, time, logging + FeedbackConfig). No cuda_check
/ torch / realtimestt / ctranslate2 — loads in CPU-only and test contexts; subprocess.run +
time.monotonic are mocked in unit tests (P1.M3.T2.S1).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time

from voice_typing.config import FeedbackConfig

logger = logging.getLogger(__name__)

# Minimum seconds between update_partial DISK writes (>=10 Hz max — PRD §4.6). The throttle
# clock is time.monotonic() (never time.time() — wall clock can jump backward on NTP and
# would freeze the partial forever). The ts FIELD still uses time.time() (wall epoch).
_PARTIAL_WRITE_MIN_INTERVAL = 0.1

# P1.M3.T3.S2: bulk-delivery status surface (PRD §4.2sexies R.5). The vocabularies mirror
# the planning round (d2_bulk_delivery_map.md §4): modes mirror the [output] delivery value
# space (P1.M3.T3.S1); states are the R.5 taxonomy; reason/op are capped so a pasted
# document can never ride in state.json (the sanitizer is the mechanical guard).
_DELIVERY_MODES = ("stream-edit", "bulk-text")
_DELIVERY_STATES = ("inactive", "active", "unsupported", "fault")
_STATUS_TEXT_MAX = 160


def _sanitize_status_text(value: str) -> str:
    """Collapse whitespace runs to single spaces + truncate — the R.5 guard that keeps
    delivery_reason/last_confirmed_op to counts/times, never recognition text or the
    surrounding user document (a newline in the value would break `voicectl status`'s
    one-line rendering; anything longer than 160 chars is a document, not a reason).
    Applied ONLY to the delivery reason/op fields — partial/last_final carry recognition
    text BY DESIGN and are never sanitized.
    """
    return " ".join(value.split())[:_STATUS_TEXT_MAX]

# hyprctl notify icon "-1" means "No icon" (verified: `hyprctl notify --help`) — so the
# message text itself ('Recording' / 'Loading…' / 'Recording Stopped' / '✔ <text>') IS the
# visual. Color is Nord frost (PRD §4.6).
_HYPR_ICON = "-1"
_HYPR_COLOR = "rgb(88c0d0)"


class Feedback:
    """Daemon state publisher: atomic state file + fire-and-forget hyprctl notify (PRD §4.6)."""

    def __init__(self, cfg: FeedbackConfig) -> None:
        self._cfg = cfg
        # In-memory state mirrors the on-disk JSON shape EXACTLY (PRD §4.6 / item contract).
        # Boot state (P1.M2.T2.S1 / §4.2bis): phase 'unloaded' + models_loaded False — models are NOT resident
        # until the first arm's _load_recorder() succeeds. The daemon overrides both at construction + each
        # lifecycle transition (set_phase + set_models_loaded); these are just the safe pre-daemon defaults.
        self._state: dict[str, object] = {
            "listening": False,
            "phase": "unloaded",      # P1.M2.T2.S1: boot phase (models not yet loaded, §4.2bis)
            "models_loaded": False,   # P1.M2.T2.S1: True once _load_recorder succeeds (driven by the daemon)
            "mode": "lite",          # Rev 2 constant (§4.2quater): ALWAYS "lite" — seeded "lite" at
                                     # boot too, so state.json never carries the retired "normal"
                                     # name in the boot→first-arm window (validation Issue 4)
            "ducked": False,          # P1.M2.T3.S1 (§4.2quinquies): DESIRED ducking state, mirrored
                                     # by Feedback.set_ducked at each engage/release seam; the
                                     # crash-safety signal T3.S2's boot self-heal reads ("ducked"
                                     # here does NOT mean the backend already applied it)
            # P1.M3.T3.S2 (PRD §4.2sexies R.5): bulk-delivery status surface. Literal seeds
            # (config default) — NO config read here (Feedback sees only FeedbackConfig);
            # the bulk wiring (P1.M6.T2.S1) re-seeds delivery_mode from [output] delivery
            # at boot and drives state/reason/op. Until then these are the truthful
            # "surface unwired" values.
            "delivery_mode": "stream-edit",   # mirrors [output] delivery ("stream-edit"|"bulk-text")
            "delivery_state": "inactive",     # R.5 taxonomy: inactive|active|unsupported|fault
            "delivery_reason": "",            # one concise reason (stop/acquire failure), sanitized
            "last_confirmed_op": "",          # last APPLIED op descriptor (counts+times), sanitized
            "partial": "",
            "last_final": "",
            "ts": 0.0,
        }
        # Throttle baseline: 0.0 so the FIRST update_partial always writes (monotonic() >> 0.1).
        self._last_partial_write = 0.0

    # --- public API (the daemon calls these) ---

    def update_partial(self, text: str) -> None:
        """Record a realtime partial; THROTTLED disk write (>=10 Hz max); NEVER notify.

        The in-memory partial is updated unconditionally so the next flush (from any
        method) captures the latest words — only the disk write is throttled.
        """
        self._state["partial"] = text
        now = time.monotonic()
        if now - self._last_partial_write < _PARTIAL_WRITE_MIN_INTERVAL:
            return  # throttled: skip this disk write; memory already holds the latest partial
        self._last_partial_write = now
        self._write()

    def set_phase(self, phase: str) -> None:
        """Record a VAD/recording phase (idle/listening/speaking); always write; never notify.

        Phase flips are NOT start/final/stop events, so they never fire hyprctl (the
        anti-spam rule — see module docstring). The lazy-load lifecycle (§4.2bis) also uses
        'unloaded' (boot / failed load) and 'loading' (first arm in progress); the daemon's
        _load_recorder() drives those. This method accepts any string (no validation).
        """
        self._state["phase"] = phase
        self._write()

    def set_models_loaded(self, loaded: bool) -> None:
        """Record whether the ASR models are resident on the GPU (PRD §4.2bis / §4.6).

        Driven by the daemon's _load_recorder() at each lifecycle transition (->False while
        loading / on failure; ->True on success) and at construction. Always writes —
        model-lifecycle transitions are infrequent, so the state file stays current for
        voicectl status. Never notifies (not a start/final/stop event — same
        anti-spam rule as set_phase).
        """
        self._state["models_loaded"] = bool(loaded)
        self._write()

    def set_mode(self, mode: str) -> None:
        """Record the armed mode (PRD §4.2ter: "normal" | "lite"). Driven by the daemon's _arm()
        right before set_listening(True), so state.json + voicectl status reflect which model set
        is active. Always writes; never notifies (not a start/final/stop event).
        """
        self._state["mode"] = mode
        self._write()

    def set_ducked(self, ducked: bool) -> None:
        """Record the DESIRED media-ducking state (PRD §4.2quinquies / P1.M2.T3.S1).

        Driven by the daemon's _duck_engage()/_duck_release() at each lifecycle seam
        (engage at the _arm() toast site; release on EVERY disarm path — _disarm(),
        request_shutdown(), _handle_dead_host() — but NOT cancel(), which keeps the mic
        hot). This mirrors what the daemon ASKED the ducker for, not what the backend has
        applied yet (the AsyncDucker apply is asynchronous): conservative for crash
        safety — if the daemon dies between dispatch and apply, the flag errs "ducked"
        and the boot-time release (T3.S2) is a safe no-op when wrong. Always writes;
        never notifies (same anti-spam rule as set_phase/set_models_loaded).
        """
        self._state["ducked"] = bool(ducked)
        self._write()

    def set_delivery_mode(self, mode: str) -> None:
        """Record the armed bulk-delivery path (P1.M3.T3.S2; PRD §4.2sexies R.5 surface).

        One of "stream-edit" | "bulk-text" — the value space of [output] delivery
        (P1.M3.T3.S1). The __init__ seed is the config-default LITERAL; the bulk wiring
        (P1.M6.T2.S1) calls this at boot with the [output] delivery config value. Mode is
        orthogonal to
        listening: it describes WHICH delivery path is live for the session, not whether
        the mic is armed. Written ONLY by the bulk wiring — never by the daemon core.
        Always writes; never notifies (same anti-spam rule as set_phase).
        """
        if mode not in _DELIVERY_MODES:
            raise ValueError(
                f"delivery_mode must be one of {_DELIVERY_MODES}, got {mode!r}"
            )
        self._state["delivery_mode"] = mode
        self._write()

    def set_delivery_state(self, state: str, reason: str = "") -> None:
        """Record the bulk-delivery state + one concise reason (PRD §4.2sexies R.5; P1.M3.T3.S2).

        Taxonomy: inactive | active | unsupported | fault. Written ONLY by the bulk-delivery
        wiring (P1.M6.T2.S1 maps the controller's on_stopped/stats onto these): controller
        stop reasons queue-overflow | op-deadline | refused | unknown | target-error ->
        "fault" with that reason; a clean stop -> "inactive"; acquire failure ->
        "unsupported" + the AcquireResult.reason; a successful acquire -> "active".
        `reason` is ALWAYS overwritten (the default "" clears a stale fault reason on the
        next healthy transition — never leave a dead fault label on a live session).
        Sanitized via _sanitize_status_text: whitespace-collapsed, <=160 chars — counts and
        times, never recognition text or the surrounding user document (R.5). Always
        writes; never notifies (same anti-spam rule as set_phase).
        """
        if state not in _DELIVERY_STATES:
            raise ValueError(
                f"delivery_state must be one of {_DELIVERY_STATES}, got {state!r}"
            )
        self._state["delivery_state"] = state
        self._state["delivery_reason"] = _sanitize_status_text(reason)
        self._write()

    def record_confirmed_op(self, op: str) -> None:
        """Record the last APPLIED bulk-delivery op descriptor (PRD §4.2sexies R.5; P1.M3.T3.S2).

        Called by the bulk wiring on each in-time ShowResult.APPLIED (controller law: ONLY
        an applied op confirms — unchanged/refused/unknown never do). `op` format is
        counts + times, never recognition text: verb + utterance/seq ids + revision +
        elapsed ms, e.g. "insert utt=3 seq=7 rev=12 +34ch 41ms" (P1.M6 builds the string).
        Sanitized via _sanitize_status_text (whitespace-collapsed, <=160 chars) so the
        surrounding user document can never ride into state.json or the one-line status
        rendering. Always writes; never notifies (same anti-spam rule as set_phase).
        """
        self._state["last_confirmed_op"] = _sanitize_status_text(op)
        self._write()

    def record_final(self, text: str) -> None:
        """Record a finalized utterance; set last_final AND partial; always write; maybe notify.

        partial is overwritten with the FINAL text so status consumers see what was actually
        typed — without this, voicectl status keeps showing the last realtime partial,
        which usually trails the final by a word or two (final "...typing here today?" vs partial
        "...typing here?"). The next update_partial (new utterance) overwrites it again.

        The '✔ <text>' notification fires only when BOTH cfg.hypr_notify AND cfg.notify_on_final
        are True — the popup is redundant once the text is typed into the focused window, so
        notify_on_final lets users keep just the brief Recording / Recording Stopped toasts.
        """
        self._state["last_final"] = text
        self._state["partial"] = text  # status line shows the final, not the stale last partial
        self._write()
        if self._cfg.hypr_notify and self._cfg.notify_on_final:
            self._notify("✔ " + text)

    def set_listening(self, listening: bool) -> None:
        """Set the master listening gate; always write; notify start/stop ON TRANSITION ONLY.

        start (False->True): 'Recording' (a transient hyprctl toast), AND clears any stale partial
        left over from the previous session — otherwise consumers flash the stale old words
        the instant the mic arms (state.json still carries the old partial as listening flips true).
        The partial repopulates from the next on_realtime_transcription_stabilized callback once
        speech is actually detected. For the FIRST arm of a session the daemon ALSO fires a 'Loading…'
        toast beforehand (Feedback.notify), so a cold model load reads 'Loading…' then 'Recording'.
        Warm arms (models resident) show just 'Recording'. stop (True->False): 'Recording Stopped',
        for ANY disarm (manual stop, toggle-off, the idle auto-stop). A no-op call (same value)
        writes but does NOT notify (avoids startup spam — daemon starts not-listening per PRD §4.9)
        and does NOT clear (no transition). Notifications fire only when cfg.hypr_notify is True.
        """
        prev = self._state["listening"]
        self._state["listening"] = listening
        if listening and not prev:
            self._state["partial"] = ""  # fresh session: don't flash last session's words
        self._write()
        if self._cfg.hypr_notify and listening != prev:
            self._notify("Recording" if listening else "Recording Stopped")

    def snapshot(self) -> dict:
        """A shallow copy of the live in-memory state {listening,phase,models_loaded,partial,last_final,ts}.

        For low-latency status reads (the control socket `status` cmd) WITHOUT hitting the
        throttled state.json on disk (which lags >=10 Hz). Returns a COPY (dict(self._state)) so
        a concurrent reader never aliases the live dict the callback threads mutate. CPython dict
        copy is atomic; no Lock is needed in Feedback itself (it is designed lock-free — on_final
        serialization is the daemon's _on_final_lock; see the THREAD SAFETY note above).
        """
        return dict(self._state)

    def notify(self, msg: str) -> None:
        """Fire an ad-hoc hyprctl toast, gated by cfg.hypr_notify (no state change, no disk write).

        Used for the 'Loading…' toast the daemon fires BEFORE the cold first-arm model load (~1–3 s)
        so the hotkey isn't a silent gap (that load is then confirmed by the 'Recording' start toast
        from set_listening). Unlike set_listening / record_final this is NOT a session transition —
        it neither touches the state file nor follows the start/final/stop notify discipline; it is a
        one-shot toast. hypr_notify=False suppresses it (the same master switch as every other toast).
        """
        if self._cfg.hypr_notify:
            self._notify(msg)

    # --- internals ---

    def _write(self) -> None:
        """Atomically write self._state to cfg.resolved_state_file() (tempfile + os.replace).

        Sets ts=time.time() (wall epoch). Creates the parent dir 0o700. The temp file is
        created IN THE TARGET DIRECTORY (same filesystem → os.replace is atomic) and starts
        mode 0o600 (Python 3 mkstemp default), which the renamed state.json inherits.
        Raises propagate (a state-write failure is a real error the daemon should log) —
        but the temp file is cleaned up first so no .tmp litters the dir.
        """
        self._state["ts"] = time.time()
        path = self._cfg.resolved_state_file()  # raises RuntimeError if empty AND XDG unset
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh)
            os.replace(tmp, path)
        except BaseException:
            # Clean up the orphaned temp file on ANY failure (incl. json/replace errors)
            # so a crash mid-write doesn't leave .state.*.tmp littering the runtime dir.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _notify(self, msg: str) -> None:
        """Fire-and-forget `hyprctl notify`. Swallow ALL errors (missing binary / non-Hyprland).

        check=False + DEVNULL so hyprctl's `ok` ack never clutters journald and a nonzero
        exit never raises. OSError (binary missing) + SubprocessError are both caught — a
        notification failure must NEVER crash the daemon or stall on_final.
        """
        try:
            subprocess.run(
                ["hyprctl", "notify", _HYPR_ICON, str(self._cfg.notify_ms), _HYPR_COLOR, msg],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # Fire-and-forget: log at DEBUG (not WARNING) — non-Hyprland/SSH runs hit this
            # routinely and it is not actionable. Never re-raise.
            logger.debug("hyprctl notify failed (%s); ignored", exc)

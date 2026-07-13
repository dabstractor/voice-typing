"""voice_typing.feedback — state-file writer + Hyprland notify (PRD §4.6).

Feedback is the daemon's live-state publisher. It writes a small JSON snapshot of the
current voice-typing session (listening flag, VAD phase, latest partial, last final,
timestamp) to an atomic state file, and fires fire-and-forget `hyprctl notify` popups
on the three events that are NOT spammy: listening-start, each final, listening-stop.

STATE FILE (PRD §4.6), written atomically (tempfile + os.replace) to
$XDG_RUNTIME_DIR/voice-typing/state.json (overridable via feedback.state_file):
    {"listening": true, "phase": "speaking", "models_loaded": true, "partial": "...", "last_final": "...", "ts": 1783718400.123}
While models are not yet loaded (boot) or mid-load, phase is 'unloaded' or 'loading' and
models_loaded is false (§4.2bis); once loaded, phase cycles idle/listening/speaking.
Consumed by voice_typing/status.sh (the tmux status-right helper) and by voicectl status.

NOTIFICATION DISCIPLINE (the #1 contract — PRD §4.6 inline example is SUPERSEDED):
Hyprland notifications are NOT replaceable by ID, so per-partial popups would stack into
unreadable spam. Partials go to the state file ONLY (tmux shows them live). hyprctl popups
fire EXCLUSIVELY on:
  - listening-start  -> "● listening"   (set_listening False->True transition)
  - each final       -> "✔ <text>"      (record_final; GATED by notify_on_final — the text is
                                          already typed + shown in tmux, so this popup is optional)
  - listening-stop   -> "■ stopped"      (set_listening True->False transition)
NEVER on update_partial. NEVER on set_phase (VAD phase flips are not start/final/stop events).

THROTTLE: update_partial is capped at >=10 Hz max (min 0.1 s between disk writes). The
in-memory partial is ALWAYS updated (so the next flush captures the latest words); only
the disk write is throttled. set_phase / record_final / set_listening always write.

ATOMIC WRITE: tempfile.mkstemp(dir=<target dir>) + os.replace(tmp, target) is a
same-filesystem atomic rename (POSIX) — a concurrent tmux jq-reader (status-interval 1s)
never sees a half-written file. mkstemp creates the file mode 0o600 (Python 3 default) →
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

# hyprctl notify icon "-1" means "No icon" (verified: `hyprctl notify --help`) — so the
# leading glyph in the message string (●/✔/■) IS the visual. Color is Nord frost (PRD §4.6).
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
        voicectl status + status.sh. Never notifies (not a start/final/stop event — same
        anti-spam rule as set_phase).
        """
        self._state["models_loaded"] = bool(loaded)
        self._write()

    def record_final(self, text: str) -> None:
        """Record a finalized utterance; set last_final AND partial; always write; maybe notify.

        partial is overwritten with the FINAL text so the tmux status-right matches what was
        actually typed — without this, the status line keeps showing the last realtime partial,
        which usually trails the final by a word or two (final "...typing here today?" vs partial
        "...typing here?"). The next update_partial (new utterance) overwrites it again.

        The '✔ <text>' notification fires only when BOTH cfg.hypr_notify AND cfg.notify_on_final
        are True — the popup is redundant once the text is typed and shown live in tmux, so
        notify_on_final lets users keep just the brief ●/■ start/stop indicators.
        """
        self._state["last_final"] = text
        self._state["partial"] = text  # status line shows the final, not the stale last partial
        self._write()
        if self._cfg.hypr_notify and self._cfg.notify_on_final:
            self._notify("✔ " + text)

    def set_listening(self, listening: bool) -> None:
        """Set the master listening gate; always write; notify start/stop ON TRANSITION ONLY.

        start (False->True): '● listening', AND clears any stale partial left over from the
        previous session — otherwise the tmux status-right flashes the old words the instant
        the mic arms (status.sh renders '🎤 <partial>' as soon as listening flips true). The
        partial repopulates from the next on_realtime_transcription_stabilized callback once
        speech is actually detected. stop (True->False): '■ stopped'. A no-op call (same
        value) writes but does NOT notify (avoids startup spam — daemon starts not-listening
        per PRD §4.9) and does NOT clear (no transition). Notifications fire only when
        cfg.hypr_notify is True.
        """
        prev = self._state["listening"]
        self._state["listening"] = listening
        if listening and not prev:
            self._state["partial"] = ""  # fresh session: don't flash last session's words
        self._write()
        if self._cfg.hypr_notify and listening != prev:
            self._notify("● listening" if listening else "■ stopped")

    def snapshot(self) -> dict:
        """A shallow copy of the live in-memory state {listening,phase,models_loaded,partial,last_final,ts}.

        For low-latency status reads (the control socket `status` cmd) WITHOUT hitting the
        throttled state.json on disk (which lags >=10 Hz). Returns a COPY (dict(self._state)) so
        a concurrent reader never aliases the live dict the callback threads mutate. CPython dict
        copy is atomic; no Lock is needed in Feedback itself (it is designed lock-free — on_final
        serialization is the daemon's _on_final_lock; see the THREAD SAFETY note above).
        """
        return dict(self._state)

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

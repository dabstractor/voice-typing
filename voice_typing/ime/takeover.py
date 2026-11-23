"""takeover: takeover DETECTION + revocation policy for the IM-v2 route (P1.M4.T4.S1).

R.5 verbatim: "any ordinary physical key, caret move, selection change, mouse
click, focus change, tab/pane switch, or target death revokes the handle AT THE
TARGET; queued operations re-check at mutation time. ... The arming chord is
ignored (matched BY COMPOSITION, never by a timed window). Synthetic delivery
events cannot
self-trigger HALT or leave modifiers held. Pointer motion alone is not an edit."

Two pieces, both stdlib-pure (no Wayland/evdev imports — the ime package purity
rule, mirroring bulk's):

  - TakeoverDetector: the POLICY. ``feed(ev_dict) -> reason | None`` over the
    JSONL event dicts the manager forwards on its reader thread (the
    ime_host.on_event vocabulary: grab_key / surrounding_text /
    text_change_cause / deactivate / activate / done / keymap / modifiers /
    unavailable ...). Reasons are short machine-readable strings (R.5's
    one-concise-reason law). Keycodes are matched RAW (wlwire closes keymap
    fds immediately — no keymap names exist on this transport).

  - TakeoverWatch: the WIRING. Binds the manager's T4 feed
    (``ImeProcess(on_event=watch.on_event)``, or ``watch.attach(proc)``) to
    the detector and to the revocation action: ``target.leave()`` — which
    RELEASES the keyboard grab AT THE TARGET and clears the binding — then
    ``controller.halt_for_takeover(reason)`` through the controller's
    existing stop machinery. Exactly ONE revocation per watch; events arrive
    on the reader thread, so the latch needs no lock.

Evidence carried in the rules (never re-derived; R.2/R.4):
  - im-lab row O: grabbed keys reach the adapter while the field stays
    untouched — the grab CONSUMES the user's keys, so revocation MUST release
    the grab at the compositor; a daemon flag alone would leave the whole
    keyboard dead ("revoke AT THE TARGET").
  - im-lab row O2 / d2 map :189: commit_string generates ZERO key events —
    our own delivery cannot self-trigger HALT (we also never synthesize key
    events, so no synthetic event can leave modifiers held).
  - our own commits DO change surrounding_text — attributed via the
    text_change_cause cycle (cause == input_method) AND the accounting rule
    (cursor == acquired cursor + committed bytes — the SAME formula
    ImeTarget.recheck() re-verifies fresh at mutation time, the backstop for
    any op already past this detector).
  - the arming chord (§4.10's two binds: Ctrl+Alt+Super+D and Alt+Super+D) is
    matched BY COMPOSITION — key == KEY_D while ALT+SUPER are held (Super+Alt
    ⊆ Ctrl+Super+Alt, so one ⊇-test covers both) — never by a time window
    (the legacy §4.2quater timed window is deliberately NOT ported).
  - pointer motion alone generates NO input-method event → nothing here can
    fire on it; `unavailable`/child death is likewise NOT re-emitted here —
    the manager already emits unsupported/fault exactly once and the daemon
    wiring treats that as revocation.

Logs carry counts/times/keycodes/reasons ONLY — never recognition text (R.5).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---- keycodes: Linux input.h literals (the ime package must stay stdlib-pure;
# ---- key_listener.py's _MODIFIER_KEYCODES is the evdev-lineage source of these).
KEY_D = 32

MODIFIER_KEYCODES = frozenset(
    {29, 97, 56, 100, 42, 54, 58, 69, 70, 125, 126}
)  # L/R ctrl, L/R alt, L/R shift, caps, num, scroll, L/R super(meta)

MODIFIER_NAMES = {
    29: "CTRL",
    97: "CTRL",
    56: "ALT",
    100: "ALT",
    42: "SHIFT",
    54: "SHIFT",
    58: "CAPSLOCK",
    69: "NUMLOCK",
    70: "SCROLLLOCK",
    125: "SUPER",
    126: "SUPER",
}

# text_change_cause enum (vendored input-method-unstable-v2.xml): input_method=0, other=1.
CAUSE_INPUT_METHOD = 0

# The §4.10 arming chord, matched by composition ONLY (never a timer):
# key == KEY_D while ALT and SUPER are held. The ⊇-subset test matches BOTH
# binds — Alt+Super+D (lite) and Ctrl+Alt+Super+D (normal).
CHORD_KEY = KEY_D
CHORD_MODS = frozenset({"ALT", "SUPER"})


class TakeoverDetector:
    """Pure takeover policy over the manager's event dicts.

    State: the modifier DOWN-set (maintained from grab_key DOWN/UP transitions
    — never from the advisory `modifiers` group event), the caret EXPECTATION
    (acquired cursor + bytes we committed — the recheck() accounting formula),
    and the last text_change_cause (attributing surrounding_text deltas to our
    own commits).

    feed(ev) returns a short machine-readable revoke reason, or None when the
    event is benign/silent. Never raises on a malformed event: anything it
    cannot judge is advisory (None).
    """

    def __init__(self) -> None:
        self._mods_down: set[str] = set()
        self._expected_caret: int | None = None
        self._cause: int | None = None

    # --- expectation bookkeeping (the daemon wiring calls these; tests pin them) ---
    def note_acquired(self, cursor_bytes: int) -> None:
        """Arm-time: the expectation is the acquire reply's caret; modifier
        state resets (a fresh acquisition must not inherit a stuck down-set)."""
        self._expected_caret = int(cursor_bytes)
        self._mods_down = set()

    def note_committed(self, n_bytes: int) -> None:
        """Our own applied commit advanced the caret (the inserted_bytes term
        of the accounting formula cursor == acquired + committed)."""
        if self._expected_caret is not None:
            self._expected_caret += int(n_bytes)

    # --- the policy --------------------------------------------------------
    def feed(self, ev: dict) -> str | None:
        """One manager-forwarded event dict → revoke reason | None."""
        if not isinstance(ev, dict):
            return None
        name = ev.get("ev")
        if name == "grab_key":
            return self._feed_key(ev)
        if name == "surrounding_text":
            return self._feed_surrounding(ev)
        if name == "text_change_cause":
            args = ev.get("args")
            if isinstance(args, (list, tuple)) and args and isinstance(args[0], int):
                self._cause = args[0]
            return None
        if name == "deactivate":
            return "deactivated"  # focus/pane/tab switch — R.5 revokes
        # activate/done/keymap/modifiers/unavailable/repeat_info/...: silent.
        # unavailable on purpose: the manager already emitted unsupported/fault
        # exactly once — double-emission here is forbidden (T4 contract).
        return None

    def _feed_key(self, ev: dict) -> str | None:
        key = ev.get("key")
        if not isinstance(key, int) or isinstance(key, bool):
            return None  # malformed keycode — advisory, never guess
        state = ev.get("state", 1)
        if key in MODIFIER_KEYCODES:
            name = MODIFIER_NAMES[key]
            if state == 1:
                self._mods_down.add(name)
            else:
                self._mods_down.discard(name)
            return None  # modifier-only presses are NOT user typing (key_listener law)
        if state != 1:
            return None  # releases never revoke: a chord's own key release must
            # stay silent even if the user released the mods first — composition
            # is evaluated on PRESS only (also why no synthetic key may revoke).
        if self._chord(key):
            return None  # the arming chord itself — ignored, not a grace window
        return f"user key {key}"

    def _feed_surrounding(self, ev: dict) -> str | None:
        cursor, anchor = ev.get("cursor"), ev.get("anchor")
        expected = self._expected_caret
        if (
            not all(
                isinstance(v, int) and not isinstance(v, bool) for v in (cursor, anchor)
            )
            or expected is None
        ):
            return None  # nothing to judge against (pre-acquire events are advisory)
        if cursor == expected and anchor == cursor:
            return None  # matches OUR accounting exactly — benign
        if self._cause == CAUSE_INPUT_METHOD:
            # Our own commit landing (row O2: commits generate zero key events;
            # the toolkit attributes the delta to the input method). Adopt the
            # new caret so the accounting formula stays true after this commit.
            self._expected_caret = cursor
            return None
        if anchor != cursor:
            return "selection present"  # mirrors recheck()'s precedence
        if cursor != expected:
            return "caret moved"
        return None

    def _chord(self, key: int) -> bool:
        """The §4.10 arming chord BY COMPOSITION: KEY_D with ALT+SUPER held
        (⊇ covers Ctrl+Alt+Super+D AND Alt+Super+D). No timer anywhere."""
        return key == CHORD_KEY and CHORD_MODS.issubset(self._mods_down)


class TakeoverWatch:
    """Wiring: manager T4 feed → detector → ONE revocation at the target.

    Revocation order (R.5): ``target.leave()`` FIRST — it releases the
    keyboard grab AT THE TARGET (row O: the grab consumes keys until released)
    and clears the binding so every later mutating call refuses "not
    acquired" — then ``controller.halt_for_takeover(reason)`` records the ONE
    concise reason through the controller's existing stop machinery (whose
    own leave is idempotent). Second-and-later revoke reasons are latched
    away: exactly one leave, one halt, one reason per watch.

    on_event runs ON the manager's reader thread (single-threaded by
    construction — the latch needs no lock) and must be quick + non-blocking:
    leave() is a bounded 0.25 s request; halt never joins unboundedly. The
    watch NEVER raises out of on_event — a detector/target/controller fault
    is logged (keycodes/reasons only, never recognition text) and dropped.
    """

    def __init__(self, proc=None, target=None, controller=None, detector=None):
        self._detector = detector if detector is not None else TakeoverDetector()
        self._target = target
        self._controller = controller
        self._revoked = False
        self.revocations = 0  # observable count (always 0 or 1)
        self.reason: str | None = None  # THE recorded reason (None until revoked)
        if proc is not None:
            self.attach(proc)

    # --- subscription -------------------------------------------------------
    def attach(self, proc) -> None:
        """Subscribe to a process's T4 feed. Real ImeProcess takes on_event at
        construction — the daemon wiring shape is
        ``ImeProcess(on_event=watch.on_event)`` — so attach() exists for fakes
        and late binding: a settable ``.on_event`` attribute is used when
        present, else the manager's ``_on_event`` callback slot."""
        try:
            proc.on_event = self.on_event  # fake-style plain attribute
            return
        except AttributeError:
            pass
        proc._on_event = self.on_event  # real ImeProcess slot

    # --- the feed -----------------------------------------------------------
    def on_event(self, ev) -> None:
        """The T4 feed target. Never raises (manager guards callbacks anyway)."""
        if self._revoked:
            return  # latched: exactly one revocation per watch
        try:
            reason = self._detector.feed(ev)
        except Exception:  # noqa: BLE001 — a bad event must not kill the reader
            logger.warning(
                "ime takeover: detector dropped an event (%s)",
                ev.get("ev", "?") if isinstance(ev, dict) else "?",
                exc_info=True,
            )
            return
        if reason:
            self._revoke(reason)

    # --- the revocation action ----------------------------------------------
    def _revoke(self, reason: str) -> None:
        self._revoked = True  # latch BEFORE acting: one revocation, ever
        self.revocations += 1
        self.reason = reason
        logger.info(
            "ime takeover: revoke reason=%s", reason
        )  # R.5: reason only, no text
        if self._target is not None:
            try:
                self._target.leave()  # grab released AT THE TARGET + binding cleared
            except Exception:  # noqa: BLE001 — dead target must not block the halt
                logger.warning("ime takeover: target.leave() raised", exc_info=True)
        if self._controller is not None:
            try:
                self._controller.halt_for_takeover(reason)
            except Exception:  # noqa: BLE001 — the halt seam must never break the feed
                logger.warning("ime takeover: halt_for_takeover raised", exc_info=True)

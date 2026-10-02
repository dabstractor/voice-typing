# PRP — P1.M2.T7.S2: evdev passive Backspace-cancel listener + synthetic parser tests

---

## Goal

**Feature Goal**: A passive, read-only evdev listener thread in the **daemon process** that observes real keyboard events on `/dev/input/event*` nodes and, while armed with a pending streaming `tail`, (a) a KEY_BACKSPACE press triggers the existing `daemon.cancel()` path (P1.M2.T7.S1), and (b) any other keypress triggers the existing `daemon.note_user_keypress()` freeze seam (PRD §4.2quater rule 5). Never `EVIOCGRAB` (the user's own typing must keep flowing). Fails safe: if no keyboard node is readable, log ONCE at arm and stay silent forever — the `voicectl cancel` keybind (S1, already landed) keeps working.

**Deliverable**:
1. `voice_typing/key_listener.py` (NEW) — device enumeration (auto or `[cancel].devices` override), a pure `parse_key_event()` classifier, and the `KeyListener` background thread.
2. `voice_typing/daemon.py` (MODIFY) — instantiate/start `KeyListener`, route callbacks to `cancel()` / `note_user_keypress()`, once-per-session failure log at arm.
3. `tests/test_key_listener.py` (NEW) — synthetic-event parser unit tests + thread routing tests with fake devices (NO real keyboard, NO GPU, fast pure-python).
4. `config.toml` comment touch-up only if needed (schema for `[cancel]` already landed in P1.M1.T1.S1).

**Success Definition**: All new tests + full existing suite pass (`timeout 600 uv run pytest tests/test_key_listener.py -q`, plus re-run of `tests/test_daemon.py -q`); the classifier correctly distinguishes Backspace-press / other-key-press / release / autorepeat / non-key events from synthetic structs; a Backspace event routed while a tail is pending calls `daemon.cancel()` exactly once and further Backspaces with no tail are plain no-ops; a non-Backspace keypress with a pending tail calls `note_user_keypress()`; enumeration failures log once and never crash the daemon; the listener never grabs a device.

## User Persona (if applicable)

**Target User**: The dictating user (owner of this machine, in the `input` group — no permission changes needed, PRD §2/§4.2quater).

**Use Case**: Mid-dictation, the recognizer has typed a garbage tentative fragment. The user physically presses Backspace: the fragment vanishes (`len(tail)−1` chars rewound — the keystroke deleted the 1st), the in-flight utterance is dropped, the mic stays hot — just say the sentence again. If the user instead types a letter/edit key, the tail freezes (never type over the user's cursor).

**User Journey**: arm → speak → tail typed live → user hits Backspace → `daemon.cancel()` → tail gone, listening continues → next utterance streams fresh. Second Backspace with no tail = normal user editing (ignored). Real-Backspace behavior is additionally covered by the T5 manual smoke (already specced in the PRD; NOT automatable here).

**Pain Points Addressed**: needing the `SUPER ALT, Backspace` fallback bind for the common case; accidental text-over-type when the user starts editing mid-fragment.

## Why

- PRD §4.2quater: Backspace-cancel is the ONLY mechanism that deletes typed dictation, and the evdev gesture is its primary trigger (the S1 `voicectl cancel` was the fallback + test seam). This item completes PRD acceptance #11/#12's primary path.
- The non-Backspace branch closes PRD rule 5 (user-typing protection) with a real observer instead of only the `voicectl`-independent seam landed in T6.S3.
- Dependencies: S1 (`cancel()`, `_cancel_suppress_final`, host `cancel`) and T6.S3 (`note_user_keypress()` freeze) are **Complete** — this item only wires an input source into them. It unblocks P1.M3.T8.S2 assert (e)/(f) wiring.

## What

User-visible:
- While armed and a tentative tail is on screen: physical Backspace = cancel (rewind + drop utterance, keep listening). Physical any-other-key = the tail freezes and that utterance is never revised again.
- While disarmed, or armed with no tail: the listener's events change nothing (Backspace/keys are the user's own edits).
- If no keyboard node can be opened (permissions, container, exotic setup): one journal WARNING at the first arm — `voice-typing cancel-listener: no readable keyboard devices; Backspace-cancel unavailable (voicectl cancel keybind still works)` — then silence. Daemon never crashes or blocks on the listener.

### Success Criteria

- [ ] `parse_key_event(type, code, value)` classifies synthetic evdev events: `(EV_KEY, KEY_BACKSPACE, 1)` → `BACKSPACE_PRESS`; `(EV_KEY, <other>, 1)` → `OTHER_PRESS`; releases (`value=0`), autorepeats (`value=2`), and non-`EV_KEY` types → `None`.
- [ ] Auto-enumerate: only `/dev/input/event*` nodes whose capabilities include `EV_KEY` → `KEY_BACKSPACE` are watched; `[cancel].devices` (non-empty) replaces enumeration entirely; unreadable nodes are skipped without error.
- [ ] Exclusion filter: devices whose `name` matches virtual/self-typed sources (`ydotool`/`uinput`-style names, see Gotchas) are NEVER watched — otherwise ydotool's own rewinds would self-trigger cancels.
- [ ] Backspace press → routes to `daemon.cancel()` (which is already idempotent); further Backspaces with no tail are no-ops by construction.
- [ ] Other-key press while a tail is pending → `daemon.note_user_keypress()` (freeze seam); no-op otherwise.
- [ ] Listener opens devices read-only, NEVER calls `device.grab()` (EVIOCGRAB would swallow the user's keystrokes — hard PRD requirement).
- [ ] Failure semantics: enumeration/open failure → one WARNING at first arm, no retry storm; an `OSError`/read error mid-loop on one device → drop that device, keep the rest; the listener thread is a `daemon=True` thread so it never blocks shutdown.
- [ ] `on_backspace = false` in config → the listener is never started (pure no-op; keybind fallback unaffected).
- [ ] All existing tests still pass unmodified; no real `/dev/input` access from the test suite.

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, could they implement this successfully?" — Yes: the routing targets (`cancel()`, `note_user_keypress()`) already exist with pinned line references below, the config schema exists, `evdev>=2.0.0` is already a project dependency (verified in `pyproject.toml` + `uv.lock`), and the pure-classifier design keeps every testable piece free of real hardware.

### Documentation & References

```yaml
- url: https://python-evdev.readthedocs.io/en/latest/tutorial.html#reading-events-from-a-device
  why: InputDevice.read_loop(), InputEvent fields (type, code, value), event value semantics (1=press, 0=release, 2=autorepeat)
  critical: value==2 is autorepeat — MUST be ignored or a held Backspace fires cancel repeatedly

- url: https://python-evdev.readthedocs.io/en/latest/tutorial.html#listing-input-devices
  why: evdev.list_devices() + InputDevice(path).capabilities(); capability check pattern (verbose=False dict keyed by ecodes.EV_KEY)
  critical: capabilities()[ecodes.EV_KEY] is a list of keycodes — check ecodes.KEY_BACKSPACE membership; opening a device with InputDevice(path) is read-only unless .grab() is called

- docfile: plan/007_cfc245548aec/architecture/daemon_control_map.md
  why: Lock discipline around cancel() (daemon _lock then engine lock), _dispatch layout, test seams
  section: "§3 Stop/drain/abort", "§6 Test seams"
  critical: cancel() is called under self._lock internally — the listener must NOT hold any lock when invoking it; the idle watchdog thread pattern is the template for a daemon-owned background thread

- file: voice_typing/daemon.py
  why: Wiring point + routing targets
  pattern: cancel() :1282-1317 (idempotent, self-locking); note_user_keypress() :1216-1235 (defensive getattr seam); _arm() :1075-1090 (where the once-only failure log hooks and where armed-ness lives via self._listening)
  gotcha: never call cancel() while holding daemon _lock (deadlock — cancel takes it); _listening is a threading.Event — gate both callbacks on _listening.is_set() and a pending tail (use the same _pending_tail_len()/stream-state accessors cancel uses, or simply let cancel()/note_user_keypress() self-gate — they already do)

- file: voice_typing/config.py
  why: CancelConfig already validated (on_backspace: bool, devices: list[str]) — NOTHING to add
  pattern: CancelConfig :161-196, cancel=_overlay(CancelConfig, "cancel") :349
  gotcha: do NOT touch the schema; only read cfg.cancel.on_backspace / cfg.cancel.devices

- file: tests/test_streaming_freeze.py
  why: The pattern for fast pure-python tests against the streaming engine with fake backend/feedback
  pattern: RecordingBackend/FakeFeedback fixtures at top; _make_stream helper :63
  gotcha: no mic, no CUDA — key_listener tests must follow the same shape (fakes only)

- file: voice_typing/streaming.py
  why: pending_tail_len() :186 and note_user_keypress() :273 define "tail pending" semantics
  pattern: pending tail = tail non-empty and not frozen; the daemon seam _pending_tail_len() wraps it
```

### Current Codebase tree (relevant excerpt)

```bash
voice_typing/
├── config.py            # CancelConfig (on_backspace, devices) — landed P1.M1.T1.S1
├── daemon.py            # cancel() + note_user_keypress() seams — landed T7.S1 / T6.S3
├── streaming.py         # StreamingOutput: tail/freeze/reset_after_cancel
├── typing_backends.py   # press_backspace(n) — landed T3.S1
└── key_listener.py      # NEW (this item)
tests/
├── test_streaming_freeze.py   # fake-backend test pattern to copy
└── test_key_listener.py       # NEW (this item)
```

### Desired Codebase tree with files to be added

```bash
voice_typing/key_listener.py     # enumeration + pure classifier + KeyListener thread (no daemon imports; callbacks injected)
tests/test_key_listener.py       # synthetic parser tests + routing tests with a fake daemon-facing callable recorder
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL — self-observation loop: ydotool types via ydotoold's uinput device, which IS a
# /dev/input/event* node. If the listener watches it, our own press_backspace()/type_text()
# rewinds would be seen as "user" Backspaces/keys → self-cancel / self-freeze feedback loops.
# (wtype uses the Wayland virtual-keyboard protocol and never touches kernel input nodes —
# safe — but ydotool is the auto-fallback backend.) Filter by device name at enumeration:
# skip devices whose name matches r'(?i)(uinput|ydotool)' (and log the skip at DEBUG).

# CRITICAL — evdev event values: 1 = press, 0 = release, 2 = autorepeat. Only value==1 counts.
# A held Backspace (autorepeat) must NOT fire repeated cancels.

# CRITICAL — never device.grab(): EVIOCGRAB is exclusive and would swallow the user's typing
# from the focused window. PRD hard requirement.

# GOTCHA — InputDevice(path) constructor itself fails on unreadable nodes (OSError/PermissionError)
# — wrap per-device open in try/except and skip; enumerate must not raise.

# GOTCHA — read_loop() blocks per device; one thread per device (or one selector/poll loop) —
# a dying device's thread must exit quietly. All threads daemon=True.

# GOTCHA — the listener runs in the DAEMON process; per PRD §4.2bis the daemon must never import
# RealtimeSTT/torch — evdev is pure-python and fine.

# GOTCHA — AGENTS.md: every non-trivial command needs an inner `timeout` AND a bash-tool timeout.
# voicectl always under `timeout 30`. The new tests are pure-python (<5 s) but follow the rule anyway.
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/key_listener.py — no dataclasses needed; a small enum + constants:
from enum import Enum

class KeyEvent(Enum):
    BACKSPACE_PRESS = "backspace_press"
    OTHER_PRESS = "other_press"

# Pure function — the ONLY piece that sees raw event tuples (unit-testable with synthetic values):
def parse_key_event(ev_type: int, code: int, value: int) -> KeyEvent | None:
    """evdev.EV_KEY events only. value 1=press, 0=release, 2=autorepeat (ignored).
    Returns None for releases/autorepeats/non-key types."""

_EXCLUDE_NAME_RE = re.compile(r"(?i)(uinput|ydotool)")   # self-typing sources (Gotcha above)

def enumerate_keyboard_devices(explicit: list[str]) -> list[str]:
    """explicit non-empty -> use it verbatim (still skipping names matching _EXCLUDE_NAME_RE
    and unreadable opens — the user override wins on WHICH nodes, not on safety filters).
    Else scan evdev.list_devices(): keep EV_KEY devices exposing KEY_BACKSPACE,
    excluding _EXCLUDE_NAME_RE names. Never raises; returns [] on total failure."""
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/key_listener.py
  - IMPLEMENT: KeyEvent enum, parse_key_event(), _EXCLUDE_NAME_RE, enumerate_keyboard_devices(),
    class KeyListener(cancel_cb, other_key_cb, is_active: Callable[[], bool], devices: list[str])
  - PATTERN: thread-per-watched-device; each thread: InputDevice(path).read_loop(); for each
    ev, parse_key_event(ev.type, ev.code, ev.value); BACKSPACE_PRESS -> cancel_cb();
    OTHER_PRESS -> other_key_cb(). ALL callbacks invoked with NO listener-held locks and wrapped
    in try/except (a callback failure kills nothing — log at WARNING).
  - GOTCHA: constructing InputDevice may raise per node — per-device try/except, skip quietly.
  - GOTCHA: `is_active()` (daemon supplies `lambda: self._listening.is_set()` — the caller-side
    gate; note is_active is read OUTSIDE any lock) lets the threads run for the daemon's whole
    lifetime while events are inert while disarmed. KeyListener.start() is idempotent;
    KeyListener.stop() closes fds; both never raise.
  - NAMING: snake_case functions, PascalCase classes; module must NOT import voice_typing.daemon
    (callbacks injected — keeps it testable and avoids import cycles).

Task 2: MODIFY voice_typing/daemon.py — wire the listener
  - FIND: VoiceTypingDaemon.__init__ (where self._listening, self._cfg exist) and _arm() :1075
  - ADD (in __init__, only when cfg.cancel.on_backspace):
      self._key_listener = KeyListener(
          cancel_cb=self._on_cancel_backspace,        # -> self.cancel() (lock-free call site)
          other_key_cb=self._on_user_keypress,        # -> self.note_user_keypress()
          is_active=lambda: self._listening.is_set(),
          devices=cfg.cancel.devices)
      self._cancel_listener_warned = False            # once-only failure log latch
  - ADD two tiny wrapper methods (docstrings citing PRD §4.2quater): _on_cancel_backspace()
    checks is-active then calls self.cancel() (cancel() self-gates on listening/tail —
    idempotency already proven by S1 tests); _on_user_keypress() calls self.note_user_keypress().
    Neither holds _lock across the call.
  - START the listener threads lazily at the FIRST _arm() (after the arm work, outside the
    critical section if possible — a no-lock start() is safe since start() is idempotent):
    if a later enumerate shows zero devices and not self._cancel_listener_warned: log the
    single WARNING (message in Success Criteria) and set the latch. Do NOT log again on later arms.
  - PRESERVE: everything else in _arm()/__init__ — this is additive wiring only.

Task 3: CREATE tests/test_key_listener.py
  - IMPLEMENT (pure, no real /dev/input, no CUDA):
    Parser tests (synthetic constants — import ecodes from evdev; evdev is importable
    everywhere, only *opening devices* needs hardware):
      test_backspace_press_detected / test_other_key_press_detected /
      test_release_ignored / test_autorepeat_ignored / test_non_key_type_ignored /
      test_backspace_release_is_not_press / test_mouse_button_press_is_other_press
    Enumeration tests with monkeypatched evdev.list_devices + a FakeInputDevice class
    (capabilities() returning {EV_KEY: [KEY_BACKSPACE, KEY_A]} etc., name attribute,
    optional raise-on-open):
      test_enumeration_filters_non_backspace_devices / test_explicit_devices_override /
      test_excluded_virtual_device_names_skipped (name="ydotoold virtual device") /
      test_unreadable_node_skipped_no_raise / test_total_failure_returns_empty
    Routing tests with a fake device thread or by driving the per-device loop function
    directly with a canned event iterable (design the loop as
    `_pump_events(events, cancel_cb, other_key_cb, is_active)` — a free function the thread
    wraps, so tests need no real device or thread):
      test_backspace_press_routes_cancel_once_per_event /
      test_repeated_backspace_routes_cancel_but_daemon_cancel_is_idempotent (assert cancel_cb
      call count == press count; idempotency itself is the daemon's, already S1-tested) /
      test_other_press_routes_other_cb / test_events_inert_when_not_active /
      test_callback_exception_does_not_propagate (cancel_cb raising -> pump survives next event)
  - FOLLOW pattern: tests/test_streaming_freeze.py (fixture-light, plain asserts, module docstring
    explaining coverage)
  - PLACEMENT: tests/test_key_listener.py

Task 4: ADD daemon wiring tests (extend tests/test_daemon.py or the new file)
  - IMPLEMENT: with on_backspace=false no listener is constructed; with the default config the
    daemon holds a KeyListener whose cancel_cb routes to cancel() (call it with the daemon
    disarmed -> no-op ok; this reuses the existing fake-host test harness already in
    test_daemon.py — follow its fake recorder-host/backend fixtures).
  - GOTCHA: test_daemon.py loads no CUDA models in these paths (pure daemon state machine)
    but keep the `timeout 600` discipline anyway.
```

### Implementation Patterns & Key Details

```python
# voice_typing/key_listener.py — core shapes

def _pump_events(events, cancel_cb, other_key_cb, is_active):
    """Consume an iterable of (type, code, value); route presses. Shared by the device
    threads (read_loop) and the tests (canned lists). Never raises past a callback."""
    for ev_type, code, value in events:
        parsed = parse_key_event(ev_type, code, value)
        if parsed is None or not is_active():
            continue
        try:
            if parsed is KeyEvent.BACKSPACE_PRESS:
                cancel_cb()
            else:
                other_key_cb()
        except Exception:                       # pylint: disable=broad-except
            logger.warning("key-listener callback failed", exc_info=True)

class KeyListener:
    def start(self):  # idempotent; spawn one daemon thread per device in enumerate...
    def stop(self):   # close fds, join(brief); never raise; safe when never started
# Pattern: the device thread is `for ev in dev.read_loop(): pump one event` — reuse _pump_events
# via a generator adapter so the tested code path is identical to the live one.

# daemon.py wrappers — the ONLY new daemon methods:
def _on_cancel_backspace(self) -> None:
    """PRD §4.2quater Backspace-cancel: physical Backspace with a pending tail.
    cancel() self-gates (idempotent, listening-gated) — see P1.M2.T7.S1."""
    if self._listening.is_set():
        self.cancel()          # takes _lock internally; we hold none

def _on_user_keypress(self) -> None:
    """PRD §4.2quater rule 5: any non-Backspace keypress freezes a pending tail."""
    self.note_user_keypress()  # already a no-op without a pending tail (T6.S3)
```

### Integration Points

```yaml
CONFIG:
  - read-only: cfg.cancel.on_backspace (bool), cfg.cancel.devices (list[str]) — schema landed, do not extend

DAEMON LIFECYCLE:
  - start: first _arm() when on_backspace; threads daemon=True (no shutdown ordering hazard)
  - stop: optional best-effort KeyListener.stop() in the quit/teardown path; process exit alone is safe

LOGGING:
  - single WARNING at first arm when zero devices: "voice-typing cancel-listener: no readable
    keyboard devices; Backspace-cancel unavailable (voicectl cancel keybind still works)"
  - DEBUG for per-device skip reasons (capability miss, name exclusion, open failure)

HYPR-BINDS / INSTALL: NO changes — the SUPER ALT,Backspace fallback bind and install.sh usage
  text landed in T7.S1 and remain the documented fallback.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
uv run ruff check voice_typing/key_listener.py tests/test_key_listener.py --fix
uv run ruff format voice_typing/key_listener.py tests/test_key_listener.py
# Expected: zero errors (match repo ruff config; no mypy in this repo — ruff only)
```

### Level 2: Unit Tests (Component Validation)

```bash
timeout 600 /home/dustin/.local/bin/uv run pytest tests/test_key_listener.py -q
timeout 600 /home/dustin/.local/bin/uv run pytest tests/test_daemon.py tests/test_control_socket.py tests/test_streaming_freeze.py -q   # regressions
# bash-tool timeout: 700. Expected: all pass. These are pure-python — seconds, not minutes.
```

### Level 3: Live smoke (optional, hardware-touching — do NOT run automatically)

```bash
# Only if the operator asks for a live check: daemon under systemd is presumably running.
timeout 15 .venv/bin/voicectl status                     # confirm daemon up + mode fields
# Real Backspace behavior = T5 manual smoke (per PRD): arm, speak, press Backspace mid-fragment
# -> fragment disappears, dictation stays armed. Do NOT script this — it types into the
# focused window. Confirm the once-only warning path instead by checking:
journalctl --user -u voice-typing -n 50 --no-pager | grep -i cancel-listener || true
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Static sanity that the listener never grabs:
grep -rn "\.grab(" voice_typing/ ; # MUST return nothing
# Static sanity that key_listener has no daemon import (testability/no-cycle):
grep -n "import" voice_typing/key_listener.py
```

## Final Validation Checklist

### Technical Validation

- [ ] Levels 1-2 pass; regression files pass; no `.grab()` anywhere in `voice_typing/`
- [ ] `timeout 600 uv run pytest tests/ -q` broader run (excluding CUDA-heavy files if iterating) shows no new failures

### Feature Validation

- [ ] All Success Criteria boxes above ticked with actual test names
- [ ] Parser handles press/release/autorepeat/non-key correctly (each has a named test)
- [ ] Virtual-device (ydotool/uinput) exclusion tested by name
- [ ] Once-only arm-time WARNING latch implemented + unit-asserted where feasible
- [ ] `on_backspace=false` disables the listener entirely (tested)

### Code Quality Validation

- [ ] `key_listener.py` imports nothing from `voice_typing.daemon` (callbacks injected)
- [ ] Follows test_streaming_freeze.py test style; module docstring states coverage scope
- [ ] No new config schema, no changes to cancel() semantics (S1 behavior untouched)

### Documentation & Deployment

- [ ] Code comments cite PRD §4.2quater rule references (matching repo convention seen in daemon.py)
- [ ] No README/PRD edits needed (README sync is P1.M3.T10.S1; PRD is read-only)

## Anti-Patterns to Avoid

- ❌ Do NOT `EVIOCGRAB`/`device.grab()` — swallows the user's keystrokes (hard PRD rule)
- ❌ Do NOT watch ydotool/uinput-named devices — self-typing feedback loop
- ❌ Do NOT treat autorepeat (value 2) or release (value 0) as presses
- ❌ Do NOT hold the daemon `_lock` when invoking listener callbacks (cancel() takes it)
- ❌ Do NOT retry-open failed devices in a loop — skip, log once, move on
- ❌ Do NOT touch `cancel()`/`note_user_keypress()` internals or the config schema — this item is wiring only
- ❌ Do NOT open real `/dev/input` nodes from the test suite (fake devices + pure parser only)

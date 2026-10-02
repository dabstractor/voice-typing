# PRP — P1.M2.T7.S2: evdev passive listener thread + synthetic parser tests

---

## Goal

**Feature Goal**: A passive, read-only evdev listener (one reader thread per keyboard device, NEVER
`EVIOCGRAB`) running in the daemon process. Started at arm when `cfg.cancel.on_backspace` is true
(false ⇒ never started; `voicectl cancel` socket path still works). Device nodes come from explicit
`cfg.cancel.devices` when non-empty, else auto-enumerated via `evdev.list_devices()` filtered by
capabilities exposing `KEY_BACKSPACE`. A KEY_BACKSPACE **press** (value==1) while armed AND a tail
is pending triggers the exact `cancel()` path delivered by P1.M2.T7.S1; ANY other key press triggers
the `on_user_key()` freeze hook delivered by P1.M2.T6.S3. Failure to open/enumerate any/all devices
is logged ONCE at arm (with the `voicectl cancel` fallback pointer), never per retry. Event
interpretation is a PURE function over synthetic InputEvent-like values so unit tests need no real
keyboard.

**Deliverable**:
1. `voice_typing/key_listener.py` (NEW): pure event-classification function + `KeyListener` class
   (enumerate → filter → open passively → per-device reader threads → dispatch), injectable
   `evdev` module shim for tests.
2. `voice_typing/daemon.py` (MODIFY): construct + start the listener at `_arm()` when
   `cfg.cancel.on_backspace`; thread naming; once-only failure logging.
3. `tests/test_key_listener.py` (NEW): synthetic-event parser tests, enumeration-filter tests with
   fake device lists, dispatch tests (cancel vs freeze), failure-logging tests. No real
   `/dev/input` access, no CUDA, no daemon process.

**Success Definition**: All new + existing unit tests pass (`timeout 600 uv run pytest
tests/test_key_listener.py -q` and the affected daemon tests); the pure parser correctly classifies
press/release/autorepeat × Backspace/non-Backspace; multi-device dispatch routes each device's
events to the same handler; enumeration uses `cfg.cancel.devices` when non-empty and the
capabilities filter otherwise; open failure logs exactly once per arm; the listener never calls
`grab()`.

## User Persona (if applicable)

**Target User**: The dictating user on this machine (Wayland/Hyprland, in group `input`).

**Use Case**: While dictating, the recognizer has typed a garbage tentative `tail`. The user taps
Backspace: the tail is cancelled (rewound), the in-flight utterance dropped, mic stays hot — just
say it again. If the user instead types any other key, the engine freezes the tail and stops
revising (user took the cursor).

**User Journey**: arm → speak → partial tail typed → user hits Backspace → `cancel()` fires (same
path as `voicectl cancel`) → tail gone, still listening. Alternatively user types a letter →
`on_user_key()` → partial revision frozen.

**Pain Points Addressed**: needing a keybind/tooling to cancel; the engine typing over text the
user started editing.

## Why

- PRD §4.2quater "Backspace-cancel / Listener": passive read-only evdev listener over every
  keyboard `/dev/input/event*` node; auto-enumerate EV_KEY devices exposing KEY_BACKSPACE;
  `[cancel].devices` overrides; user already in group `input` — no permission changes.
- PRD §8 risk row "evdev listener misses keyboards / permission loss": fail-safe — log once at arm,
  keybind (`voicectl cancel`, P1.M2.T7.S1) keeps working.
- Unblocks P1.M3.T8.S2 assert (e): cancel behavior asserted via synthetic events through this
  parser seam.

## What

- At the first arm with `cfg.cancel.on_backspace == true`, the daemon enumerates target nodes
  (explicit `cfg.cancel.devices` if non-empty, else auto), opens each passively, and spawns one
  daemon reader thread per device.
- KEY_BACKSPACE press (EV_KEY, code 14, value 1) while armed AND tail pending →
  `VoiceTypingDaemon.cancel()` (the P1.M2.T7.S1 path — it is itself idempotent, so the listener
  does not need to re-check tail state; but the armed gate is checked cheaply via the existing
  listening Event to avoid useless wakeups). Release (0) and autorepeat (2) are ignored.
- Any OTHER key press (value 1) → `on_user_key()` (P1.M2.T6.S3 freeze hook).
- `cfg.cancel.on_backspace == false` ⇒ listener never starts; socket cancel unchanged.
- If enumeration yields zero devices, or any/all opens fail (FileNotFoundError, PermissionError,
  OSError): log ONE warning at arm naming the failure and pointing at the Hyprland
  `SUPER ALT, Backspace` / `voicectl cancel` fallback. Never crash the daemon; subsequent arms
  re-attempt enumeration but the log fires at most once per daemon process per distinct failure
  (simplest compliant: once per process).
- A device vanishing mid-read (OSError/EOFError out of `read_loop()`): close the fd and end that
  reader thread quietly (log at debug); re-enumeration happens on the next arm.
- NEVER call `dev.grab()` (EVIOCGRAB). Plain `read_loop()` is already passive.

### Success Criteria

- [ ] Pure classifier: `(EV_KEY, KEY_BACKSPACE, 1)` → CANCEL; `(EV_KEY, <other>, 1)` → FREEZE;
      value 0 → IGNORE; value 2 (autorepeat) → IGNORE; non-EV_KEY → IGNORE.
- [ ] Enumeration: `cfg.cancel.devices == ["/dev/input/event3"]` ⇒ exactly that node, no
      capabilities call; empty ⇒ `list_devices()` filtered to EV_KEY devices whose capability set
      contains KEY_BACKSPACE (fake device list test).
- [ ] Dispatch: synthetic Backspace press invokes the injected cancel callback exactly once;
      synthetic other-key press invokes the injected freeze callback; events from two fake devices
      both dispatch (multi-device).
- [ ] Listener threads are `daemon=True`, named (`vt-keyreader-<basename>`), and stop when the
      device read raises.
- [ ] Open/enumeration failure: exactly ONE warning logged per process, containing "voicectl
      cancel" fallback pointer; daemon arm still succeeds (`ok:true`).
- [ ] `cfg.cancel.on_backspace == false` ⇒ no listener threads, no enumeration.
- [ ] No call to `grab()` anywhere (assert via fake device recording).
- [ ] All existing tests still pass.

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, could they implement this successfully?" — Yes: the
evdev API contract is fully specified (below), every integration site is pinned, the upstream
contracts (`cancel()`, `on_user_key()`) are described with their producing PRPs, and tests are
designed to need zero real hardware.

### Documentation & References

```yaml
- docfile: plan/007_cfc245548aec/architecture/external_deps.md
  why: Authoritative evdev 1.9.3 API contract (probed locally) — list_devices, InputDevice open modes/exceptions, capabilities filter, read_loop value semantics, no-grab rule, multi-device patterns, permissions
  section: "## 1. python-evdev"
  critical: value 2 = autorepeat MUST be ignored; read_loop is passive (grab() is opt-in and forbidden); InputDevice opens O_RDWR — user's input-group rw is required and already present

- url: https://python-evdev.readthedocs.io/en/latest/tutorial.html
  why: canonical usage: list_devices, InputDevice, capabilities(), read_loop()
  critical: InputEvent fields (type, code, value, sec, usec); read_loop blocks per device — hence one thread per device

- docfile: plan/007_cfc245548aec/P1M2T7S1/PRP.md
  why: CONTRACT — defines VoiceTypingDaemon.cancel() + _dispatch 'cancel' that this listener triggers; idempotence semantics (no tail ⇒ no-op) mean the listener can call cancel() unconditionally on Backspace press while armed
  section: "Success Criteria" + "Implementation Blueprint"
  critical: cancel() must NOT be re-implemented here — only invoked

- docfile: plan/007_cfc245548aec/P1M2T4S1/PRP.md
  why: sibling implementing in parallel; textproc guards — do not touch textproc.py
  critical: no overlap: this task adds no textproc code

- file: voice_typing/daemon.py
  why: integration site
  pattern: _arm() :973-990 (add listener ensure-start at end, still under lock but the open/enumerate must be quick and failure-swallowed); thread creation pattern :791-794 (threading.Thread(target=..., name=..., daemon=True).start()); _listening Event :580 as the cheap armed gate; LOCK DISCIPLINE from _disarm docstring :992-1018 — never block under self._lock
  gotcha: evdev open of a handful of nodes is fast (<10ms) but wrap ALL of it in try/except so arm can never fail from the listener; reader threads must NOT take self._lock — they call self.cancel()/self.on_user_key() which manage locking themselves

- file: voice_typing/config.py
  why: CancelConfig fields (complete since P1.M1.T1.S1)
  pattern: CancelConfig :160-195 — on_backspace: bool = True, devices: list[str] = []
  gotcha: devices empty list means AUTO-enumerate, not "no devices"

- file: tests/test_daemon.py
  why: fake-injection pattern for daemon-level tests
  pattern: _FakeHost :532-613, _FakeBackend :493-504, _make_lazy_daemon :2859-2867
  gotcha: never load CUDA; the listener must be injectable (constructor arg or attribute) so tests pass a fake factory — no real /dev/input

- file: tests/test_textproc.py
  why: style template for pure-function tests
  pattern: plain module-level test functions, no fixtures

- file: AGENTS.md (repo root)
  why: hard safety rules for this repo
  critical: any /dev/input probe under `timeout`; NEVER run the daemon foreground; unit tests use synthetic events only (this task's whole design); every pytest under `timeout 600`, bash-tool timeout above that
```

### Current Codebase tree (relevant excerpt)

```bash
voice_typing/
  config.py           # CancelConfig complete (P1.M1.T1.S1)
  daemon.py           # cancel() arriving from P1.M2.T7.S1; on_user_key() from P1.M2.T6.S3
  key_listener.py     # ← NEW (this task)
tests/
  test_key_listener.py  # ← NEW (this task)
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
voice_typing/
  key_listener.py       # NEW — pure classify_key_event() + enumerate_keyboards() + KeyListener class
  daemon.py             # MODIFY — construct KeyListener (injectable), ensure-start in _arm(), wire callbacks to self.cancel / self.on_user_key
tests/
  test_key_listener.py  # NEW — synthetic parser tests, fake-device enumeration/filter/dispatch/failure tests
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: evdev read_loop() blocks per device — one daemon=True reader thread PER device.
# CRITICAL: EV_KEY value 2 = autorepeat — MUST be ignored (else key-hold spams cancel).
# CRITICAL: NEVER call dev.grab() — EVIOCGRAB would steal the keyboard from Hyprland.
# CRITICAL: InputDevice opens O_RDWR (not O_RDONLY) — a read-only-only permission would fail;
#           user is in group input with rw, verified.
# GOTCHA: cfg.cancel.devices == [] means AUTO-enumerate (capabilities filter), not "none".
# GOTCHA: daemon lock discipline (validation NEW-2): reader threads must never block under
#         self._lock; they only call self.cancel()/self.on_user_key() (self-locking seams).
# GOTCHA: a vanished device raises OSError/EOFError out of read_loop — close fd, end thread
#         quietly; re-enumeration naturally happens at the next arm.
# GOTCHA: import evdev at module top of key_listener.py is fine (dep landed P1.M1.T1.S2), but
#         tests inject a fake module — design KeyListener to receive the evdev module (or
#         InputDevice/list_devices callables) as constructor args with real defaults.
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/key_listener.py — no new persistent models; one enum + one small result type:

from enum import Enum

class KeyAction(Enum):
    CANCEL = "cancel"      # Backspace press (value==1)
    FREEZE = "freeze"      # any other key press (value==1)
    IGNORE = "ignore"      # release (0), autorepeat (2), non-EV_KEY

# Pure function — the tested seam:
def classify_key_event(ev_type: int, ev_code: int, ev_value: int) -> KeyAction: ...

# Constants: from evdev import ecodes → EV_KEY = ecodes.EV_KEY (1), KEY_BACKSPACE (14).
# Use evdev.ecodes at runtime, but the pure function takes plain ints so tests never import evdev.
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/key_listener.py — pure layer
  - IMPLEMENT: KeyAction enum + classify_key_event(ev_type, ev_code, ev_value) -> KeyAction
    (pure, no evdev import needed at call time; keep EV_KEY/KEY_BACKSPACE as module constants
    sourced from evdev.ecodes with literal fallbacks 1 / 14)
  - IMPLEMENT: enumerate_keyboards(evdev_mod, explicit_devices: list[str]) -> list[str]
    - if explicit_devices non-empty → return it verbatim (no capabilities probing)
    - else → [path for path in evdev_mod.list_devices() if node is a keyboard], where "keyboard"
      = capabilities() has ecodes.EV_KEY and ecodes.KEY_BACKSPACE in caps[ecodes.EV_KEY];
      per-device open/capabilities failure (FileNotFoundError/PermissionError/OSError) → skip silently
  - FOLLOW pattern: plain module functions like voice_typing/textproc.py (pure, unit-testable)
  - NAMING: snake_case; file key_listener.py
  - PLACEMENT: voice_typing/

Task 2: CREATE voice_typing/key_listener.py — KeyListener class
  - IMPLEMENT: class KeyListener with constructor
    (on_cancel: Callable[[], None], on_user_key: Callable[[], None],
     devices: list[str], logger, evdev_mod=evdev)  # injectable module for tests
  - METHODS:
    - start(): enumerate (Task 1) → open each InputDevice (never grab(); record grabbed=False
      implicitly — simply never call grab) → spawn one threading.Thread(daemon=True,
      name=f"vt-keyreader-{basename(path)}") per device running _read_device(dev); if zero
      devices or open errors → ONE warning log mentioning "voicectl cancel" (guard with a
      self._warned flag so it fires once per KeyListener lifetime); swallow all exceptions —
      start() must never raise.
    - _read_device(dev): for ev in dev.read_loop(): act = classify_key_event(ev.type, ev.code,
      ev.value); CANCEL → self._on_cancel(); FREEZE → self._on_user_key(); on OSError/EOFError →
      dev.close() and return.
    - is_running / threads introspection minimal (tests use fake devices whose read_loop yields
      a bounded sequence then raises EOFError).
  - GOTCHA: callbacks are invoked on reader threads — they must be the daemon's self.cancel /
    self.on_user_key (self-locking); KeyListener itself holds no locks.
  - PLACEMENT: same file, below the pure functions

Task 3: MODIFY voice_typing/daemon.py — wiring
  - CONSTRUCT in VoiceTypingDaemon.__init__: self._key_listener = KeyListener(
      on_cancel=self.cancel, on_user_key=self.on_user_key,
      devices=cfg.cancel.devices, logger=..., evdev_mod=evdev)   # keep evdev import inside a
      try/except at module import time is NOT needed (dep landed); but allow test injection by
      assigning daemon._key_listener a fake before first arm
  - MODIFY _arm() (:973-990): at the END add:
      if self._cfg.cancel.on_backspace: self._key_listener.start()   # idempotent + never raises
  - FIND pattern: thread creation at :791-794; once-only logging pattern from _refresh_mic_status TTL
  - PRESERVE: existing _arm ordering (listening set, toasts, mic status) — listener start goes last
  - GOTCHA: on_backspace=false ⇒ start() never called (test asserts no threads). on_user_key()
    arrives with P1.M2.T6.S3 — per plan ordering T6 precedes T8; if the method is absent at
    implementation time, reference it anyway (contract) — do NOT invent a stub in daemon.py.

Task 4: CREATE tests/test_key_listener.py
  - IMPLEMENT (plain functions, tests/test_textproc.py style — no fixtures, no hardware):
    - classify: press/release/autorepeat × backspace/other × non-EV_KEY (8-10 asserts)
    - enumerate_keyboards: explicit list returned verbatim; empty → fake list_devices() filtered
      by fake capabilities (include one non-keyboard node, one EV_KEY-without-Backspace node, one
      KEY_BACKSPACE node → only the last survives; one node whose open raises PermissionError →
      skipped)
    - KeyListener.start + dispatch: fake evdev_mod with FakeDevice(read_loop yields synthetic
      events then raises EOFError); join threads with a timeout; assert on_cancel called exactly
      once per Backspace press, on_user_key per other press, nothing for release/autorepeat
    - multi-device: two FakeDevices → both dispatch through the same callbacks
    - failure logging: fake list_devices raising → start() returns cleanly, exactly ONE warning
      containing "voicectl cancel"
    - no-grab: FakeDevice records method calls; assert "grab" not in recorded calls
    - on_backspace gating: daemon-level — use tests/test_daemon.py _make_lazy_daemon pattern with
      a fake listener; arm with on_backspace=True → fake.start called once (idempotent on second
      arm); on_backspace=False → never called. Add these daemon cases to tests/test_daemon.py
      (extend existing fakes, do not build a new harness).
  - NAMING: test_classify_*, test_enumerate_*, test_listener_*, test_arm_* 
  - GOTCHA: reader threads must terminate — every FakeDevice.read_loop must terminate (raise
    EOFError after its event list); never sleep-wait, join(timeout=5)

Task 5: VALIDATE
  - timeout 600 uv run pytest tests/test_key_listener.py -q
  - timeout 600 uv run pytest tests/test_daemon.py -q
  - timeout 600 uv run pytest tests/test_textproc.py tests/test_config.py -q   (regression)
```

### Implementation Patterns & Key Details

```python
# Pure classifier — THE tested seam (tests never touch /dev/input):
def classify_key_event(ev_type: int, ev_code: int, ev_value: int) -> KeyAction:
    if ev_type != EV_KEY or ev_value != 1:   # 1 == press; 0 release, 2 autorepeat -> ignore
        return KeyAction.IGNORE
    return KeyAction.CANCEL if ev_code == KEY_BACKSPACE else KeyAction.FREEZE

# Reader thread body:
def _read_device(self, dev) -> None:
    try:
        for ev in dev.read_loop():
            act = classify_key_event(ev.type, ev.code, ev.value)
            if act is KeyAction.CANCEL:
                self._on_cancel()      # daemon.cancel() — idempotent when no tail pending
            elif act is KeyAction.FREEZE:
                self._on_user_key()    # engine freeze hook (P1.M2.T6.S3)
    except (OSError, EOFError):
        pass                            # device vanished — close and end this thread
    finally:
        try: dev.close()
        except Exception: pass

# start() failure path — ONCE per listener, never raises:
if not opened:
    if not self._warned:
        self._warned = True
        self._logger.warning(
            "Backspace-cancel: no keyboard device could be opened; "
            "use the SUPER ALT, Backspace bind / `voicectl cancel` fallback")
    return
```

### Integration Points

```yaml
DAEMON:
  - voice_typing/daemon.py __init__: construct KeyListener (test-injectable attribute)
  - _arm(): conditional ensure-start as the last statement
CONFIG:
  - read-only consumer: cfg.cancel.on_backspace, cfg.cancel.devices (no config changes — complete)
ROUTES: none (no socket surface — socket cancel belongs to P1.M2.T7.S1)
DOCS: none beyond code comments (config.toml [cancel] comments landed in P1.M1.T1.S1;
      hypr-binds comment landed in P1.M2.T7.S1)
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
uv run ruff check voice_typing/key_listener.py tests/test_key_listener.py --fix
uv run ruff format voice_typing/key_listener.py tests/test_key_listener.py
# Expected: clean. (Project uses ruff; run on the touched daemon.py too.)
```

### Level 2: Unit Tests (Component Validation)

```bash
timeout 600 uv run pytest tests/test_key_listener.py -v
timeout 600 uv run pytest tests/test_daemon.py -q
# bash-tool timeout: 700. Expected: all pass, zero real /dev/input access, no CUDA loads.
```

### Level 3: Integration Testing (System Validation)

```bash
# Static sanity only — NO daemon foreground run (AGENTS.md Rule 2), NO real keyboard probing in
# automated tests. Optional bounded hardware probe (allowed, must be timed):
timeout 10 uv run python -c "
import evdev, evdev.ecodes as ecodes
for p in evdev.list_devices():
    d = evdev.InputDevice(p)
    caps = d.capabilities()
    if ecodes.EV_KEY in caps and ecodes.KEY_BACKSPACE in caps[ecodes.EV_KEY]:
        print(p, d.name)
"
# Expected: lists the machine's keyboards. Real-Backspace behavior itself stays in the T5 manual
# smoke (P1.M3.T10.S1 README first-run).
```

### Level 4: Creative & Domain-Specific Validation

```bash
# None for this task — real-keyboard E2E is explicitly deferred to the manual smoke (item
# contract point 3) and asserted synthetically by P1.M3.T8.S2 (asserts e/f).
```

## Final Validation Checklist

### Technical Validation

- [ ] `timeout 600 uv run pytest tests/test_key_listener.py tests/test_daemon.py -q` passes
- [ ] Existing suites unaffected: textproc/config/typing_backends tests still pass
- [ ] ruff clean on touched files

### Feature Validation

- [ ] All "Success Criteria" boxes above demonstrably covered by a named test
- [ ] No `grab()` anywhere; reader threads daemon=True and named
- [ ] Failure logging exactly once, mentions `voicectl cancel`
- [ ] `on_backspace=false` ⇒ listener never started (test)

### Code Quality Validation

- [ ] Pure seam (`classify_key_event`) takes plain ints — tests import no evdev
- [ ] Injectable evdev module / listener on the daemon — no hardware in unit tests
- [ ] Reader threads never touch `self._lock` directly

### Documentation & Deployment

- [ ] Code comments only (per item contract); no README/config edits

## Anti-Patterns to Avoid

- ❌ Don't call `dev.grab()` — passive means passive (Hyprland coexistence)
- ❌ Don't treat autorepeat (value 2) as a press — key-hold must not spam cancel
- ❌ Don't re-implement cancel logic in the listener — call the P1.M2.T7.S1 `cancel()` seam
- ❌ Don't probe /dev/input or run the daemon in unit tests (AGENTS.md Rules 1–2)
- ❌ Don't let listener start/enumeration failures break `_arm()` — swallow + warn once
- ❌ Don't hold or acquire `self._lock` on reader threads (NEW-2 wedge class)

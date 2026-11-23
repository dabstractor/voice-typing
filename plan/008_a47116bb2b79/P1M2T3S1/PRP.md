# PRP — P1.M2.T3.S1: Engage/release media ducking at the arm/disarm seams

## Goal

**Feature Goal**: Wire media ducking (PRD §4.2quinquies, D1) into the daemon's lifecycle: the ducker
**engages at ONE choke point** — `_arm()`'s toast site (covers every arm: start, toggle, warm/cold) —
and **releases on EVERY disarm path**: `_disarm()` (which manual stop/toggle-off immediate+drain,
idle auto-stop, and Rev-3 HALT all funnel into), `request_shutdown()` (quit + SIGTERM), AND the
`_handle_dead_host()` edge (child death while ducked fires the stop toast WITHOUT `_disarm`).
`cancel()` must NOT release (the mic stays hot). All dispatch is **non-blocking** — never blocking
work under `self._lock` — via P1.M2.T2.S4's `AsyncDucker`. `feedback.set_ducked()` mirrors desired
state on every engage/release (the crash-safety signal T3.S2 will read).

**Deliverable** (3 files edited, ~10 tests appended; no new files):
1. `voice_typing/daemon.py` — `ducker=` ctor seam (mirror `key_listener=`), `_duck_engage()`/
   `_duck_release()` helpers, 4 seam insertions, module-docstring ducking note (Mode A).
2. `voice_typing/feedback.py` — `"ducked": False` in `_state` + `set_ducked()` (clone
   `set_models_loaded`) + docstring schema line.
3. `tests/test_feedback.py` (:129, :441 lockstep) + `tests/test_ducking.py` (lifecycle cases).

**Success Definition**:
- (a) Arm via `start()`/`toggle()` → ducker.engage() dispatched; state.json gains `"ducked": true`.
- (b) Every disarm path (stop, toggle-off, drain completion, idle auto-stop, HALT, quit/SIGTERM,
  dead-host) → ducker.release() dispatched; `"ducked": false`.
- (c) `cancel()` → NO release; ducker stays engaged; `_listening` stays set.
- (d) `duck_mode="off"` (default) → `self._ducker is None`; zero ducking calls; behavior
  byte-identical to today (PRD acceptance).
- (e) No blocking under `self._lock`: AsyncDucker dispatch returns immediately (S4 contract); the
  arm path never waits on ducking (PRD "engage runs concurrently; arm latency must not measurably change").
- (f) `timeout 600 .venv/bin/python -m pytest tests/test_ducking.py -q` green (core + new
  lifecycle); `tests/test_feedback.py tests/test_daemon.py` green; fast sweep shows no new failures
  vs `tests/G1_BASELINE.md`.

## User Persona

Not a user surface yet (`duck_mode` ships "off"; T4 flips the default). Beneficiaries: the end user
once enabled (music pauses within ~1 s of arm and resumes at stop, on EVERY stop path — never left
ducked by a crash, an auto-stop, or a HALT) and T3.S2 (consumes `state["ducked"]` for boot-time
self-heal + `flush()` at quit).

## Why

- **PRD §4.2quinquies "Lifecycle wiring" is normative**: "Engage where the arm toast fires; release
  on EVERY disarm path: manual stop/toggle-off, idle auto-stop, Rev 3 HALT keypress disarm, daemon
  quit — but NOT on Backspace-cancel (the mic stays hot)." This task is exactly that wiring.
- **A missed seam = media stuck ducked.** The seams doc proved all ordinary disarms funnel into
  `_disarm()`, but `_handle_dead_host()` fires the stop toast WITHOUT `_disarm()` — a child crash
  while ducked would leave media ducked until quit. The edge gets its own release (contract EDGE).
- **Lock discipline (the NEW-2 wedge class).** `_arm()`/`_disarm()` run under `self._lock`; a
  blocking call there once wedged every control command (voicectl timeouts). S4's `AsyncDucker`
  makes the inline dispatch safe; this task must NOT reintroduce inline blocking.
- **`ducked` is the crash-safety contract.** PRD: "a `ducked` field in the feedback state file lets
  a post-crash restart self-heal". The WRITE side (set_ducked at each seam) is this task; the READ
  side (boot self-heal, ExecStopPost, flush) is T3.S2.

## What

Add the `ducker=` injection seam (default built from `cfg.audio` when `duck_mode != "off"`, wrapped
`AsyncDucker(AudioDucker.from_config(cfg, tier_backend))`), two tiny dispatch helpers, four seam
calls (engage @_arm toast; release @_disarm toast, @request_shutdown after `_shutdown.set()`,
@_handle_dead_host stop-toast), the `Feedback.set_ducked` write side + state field, and ~10
lifecycle tests via a `_FakeDucker` injected through a copy of `_make_daemon`.

### Success Criteria

- [ ] `daemon.py` ctor accepts `ducker=`; default factory builds the wrapped ducker only when
      `duck_mode != "off"`; construction is PURE (no subprocess/threads at ctor).
- [ ] `self._duck_engage()` at the `_arm()` toast site (`set_listening(True)`); `self._duck_release()`
      at `_disarm()`'s `set_listening(False)`, in `request_shutdown()` right after `self._shutdown.set()`,
      and in `_handle_dead_host()` after its `set_listening(False)`.
- [ ] `cancel()` untouched by ducking (no release call anywhere in it).
- [ ] `Feedback.set_ducked(bool)` exists; `"ducked": False` seeded in `_state`; test_feedback.py
      :129 + :441 key-set assertions updated in lockstep.
- [ ] The 9+ lifecycle tests pass (incl. PRD case (c): release on every disarm path incl HALT + auto-stop).
- [ ] daemon.py module docstring gains the ducking note.

## All Needed Context

### Context Completeness Check

_Pass._ The research note carries the full pre-verified detail: the exact anchor text of every seam
(current line numbers re-verified: `_arm`@1409, `_disarm`@1470, `_handle_dead_host`@1062,
`cancel`@1804, `request_shutdown`@2207 — the contract's cites are ~50 lines stale), the funnel proof
(all ordinary disarms → `_disarm`), the AsyncDucker reconciliation (§1 — supersedes the contract's
"spawn threads" wording per S4's PRP), the ctor-seam mirror, the feedback recipe + the two
lockstep test lines, the `_FakeDucker`/`_make_daemon`-copy injection pattern, and the verified
validation commands.

### Documentation & References

```yaml
# MUST READ — the pre-verified wiring map (anchors, reconciliation, feedback recipe, test matrix)
- docfile: plan/008_a47116bb2b79/P1M2T3S1/research/ducking_lifecycle_wiring.md
  why: "§1 ★ the AsyncDucker reconciliation (inline dispatch, NOT raw thread spawns). §2 the seam
        table with CURRENT anchors + the funnel proof + the dead-host edge. §3 the ctor seam +
        default factory. §4 the dispatch helpers (desired-state set_ducked rationale). §5 the
        feedback recipe + the :129/:441 lockstep pins. §6 the 9-test matrix + injection pattern.
        §7 scope boundaries vs T3.S2. §8 validation."
  section: "ALL. §1-§2 load-bearing."

# MUST READ — the authoritative seam analysis (arm/disarm path table, lock discipline, edge case).
- docfile: plan/008_a47116bb2b79/architecture/d1_ducking_seams.md
  why: "§1a/1a′ the arm/disarm path table (every entry, its thread, its lock). §1c the choke-point
        choice rationale. §1d the NEW-2 lock-wedge precedent (why nothing blocking may run under
        _lock; Feedback is lock-free/any-thread). §1b why cancel() must not release. §2 the feedback
        ducked recipe. §5 the test-seam recommendation (_FakeDucker + _make_daemon copy)."
  critical: "Its line numbers are HEAD-2335a9e (stale ~+50) — re-locate by anchor text; the PATH
             analysis remains valid (re-verified at research time)."

# MUST READ — the parallel CONTRACT defining the dispatch layer this task consumes.
- docfile: plan/008_a47116bb2b79/P1M2T2S4/PRP.md
  why: "Defines AsyncDucker (voice_typing/ducking_async.py): engage()/release() return immediately,
        never raise, coalesce, latest-wins; worker thread 'vt-ducking'; flush(timeout) bounded.
        Its PRP states T3.S1 wires AsyncDucker.engage()/release() at the seams — this PRP does
        exactly that. Precondition: ducking_async.py landed (verify with ls; the file was NOT on
        disk at this PRP's research time)."
  critical: "If ducking_async.py is absent at impl time, STOP and report (dependency not landed) —
             do not improvise a different dispatch design."

# MUST READ — the frozen bookkeeping layer (what engage/release actually do).
- file: voice_typing/audio_ducking.py
  why: "AudioDucker: idempotent engage/release, _engaged set FIRST (partial engage still unwinds),
        _call swallows every backend failure into one warning, from_config(cfg, backend). This task
        only CALLS it through AsyncDucker — never edits it (S1 FROZEN)."
  gotcha: "AudioDucker.engage() holds its internal lock across backend calls — never call the RAW
           AudioDucker inline at a daemon seam; always go through AsyncDucker."

# MUST READ — the file being edited (the four seams + ctor live here).
- file: voice_typing/daemon.py
  why: "ctor __init__@604-617 (key_listener param @615; wiring block @809-816 to mirror);
        _arm@1409 (toast site: 'self._feedback.set_listening(True)' just before
        'self._refresh_mic_status()'); _disarm@1470 (toast site: 'set_listening(False)' just before
        set_phase('idle')); _handle_dead_host@1062 (stop toast: set_phase('unloaded') then
        set_listening(False), ~@1105, inside 'with self._lock'); cancel@1804 (NO EDIT);
        request_shutdown@2207 (insert after the first body line 'self._shutdown.set()')."
  gotcha: "_arm/_disarm/_handle_dead_host run under self._lock — only AsyncDucker's immediate-return
           dispatch is safe there. Key-listener ctor block documents the CONSTRUCTION-IS-PURE rule
           (@806-808) the ducker factory must follow."

# MUST READ — the state-field write side + the lockstep test pins.
- file: voice_typing/feedback.py
  why: "_state @96-109 (add \"ducked\": False near \"mode\"); set_models_loaded @135-145 (the setter
        template — always-write, never notifies); module-docstring schema line @11 (add ducked)."
- file: tests/test_feedback.py
  why: ":129 and :441 pin the EXACT state key set — both must gain \"ducked\" or the suite breaks."
  gotcha: "These are the only two pins (verified by grep); update both in lockstep."

# MUST READ — the injection pattern + the file the lifecycle tests append to.
- file: tests/test_daemon.py
  why: "_make_daemon @682-700 (the copy pattern: fakes _DaemonFakeFeedback@470, _StubRecorder@490,
        _FakeBackend@517, _ok_probe@535; extend the feedback fake to record set_ducked). Existing
        HALT/drain/auto-stop tests show how to drive note_user_keypress/_complete_drain/
        _maybe_auto_stop without the run loop."
- file: tests/test_ducking.py
  why: "Currently core-only (imports AudioDucker, PlayerState). Append the lifecycle section:
        _FakeDucker + _make_ducking_daemon (the _make_daemon copy passing ducker=fake)."

# CONTEXT — the PRD spec.
- docfile: PRD.md  # §4.2quinquies
  why: "Lifecycle wiring paragraph (engage at arm toast; release on EVERY disarm incl quit, NOT
        cancel), failure discipline (enhancement never a gate; arm latency unchanged), the ducked
        crash-safety field, test case (c) (release on every disarm path incl HALT and auto-stop),
        duck_mode='off' byte-identical acceptance."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # EDIT: ctor seam + 2 helpers + 4 seam calls + docstring note
├── feedback.py          # EDIT: "ducked" field + set_ducked() + docstring schema
├── audio_ducking.py     # READ-ONLY (S1, frozen): AudioDucker
├── ducking_mpris.py     # READ-ONLY (S2): MprisBusctlBackend @75
├── ducking_async.py     # EXPECTED (S4, parallel): AsyncDucker — verify landed
└── ducking_volume.py    # EXPECTED (S3, parallel): wpctl backend — verify class name
tests/
├── test_ducking.py      # EDIT: append lifecycle tests (+_FakeDucker, +_make_daemon copy)
├── test_feedback.py     # EDIT: :129/:441 key-set lockstep
└── test_daemon.py       # READ: the _make_daemon pattern @682-700
```

### Desired Codebase tree (what changes)

```bash
# Same files; no new files. daemon.py +~30 lines, feedback.py +~10, tests +~150.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — LINE NUMBERS MOVED. The contract/seams-doc cites (1415/1454/1598/1754/1817/1871/
#   1050/2177) are HEAD-2335a9e, ~50 lines stale. Re-locate EVERY seam by anchor text (grep the
#   set_listening / _shutdown.set() lines). Current: _arm@1409, _disarm@1470, _handle_dead_host@1062,
#   cancel@1804, request_shutdown@2207.
# CRITICAL #2 — NEVER call the RAW AudioDucker at a seam (its engage/release hold a lock across
#   ≤1 s subprocess calls). Always dispatch through S4's AsyncDucker (immediate return). If
#   ducking_async.py is not on disk, STOP — the declared dependency (P1.M2.T2.S4) hasn't landed.
# CRITICAL #3 — _arm/_disarm/_handle_dead_host run UNDER self._lock. The AsyncDucker dispatch is
#   safe inline (immediate return); set_ducked is safe (Feedback is lock-free, any-thread). Do NOT
#   add anything else blocking at these seams (NEW-2 wedge class).
# CRITICAL #4 — test_feedback.py :129 AND :441 pin the exact state key set. Adding "ducked" without
#   updating BOTH breaks the suite. Update both in the same change.
# CRITICAL #5 — cancel() (@1804) must NEVER release ducking: it keeps _listening set and never
#   calls _disarm(). Do not "helpfully" add a release there — PRD: Backspace-cancel keeps the mic hot.
# CRITICAL #6 — CONSTRUCTION IS PURE at the ctor (mirror the key_listener rule): the default ducker
#   factory must not run subprocesses or start threads; backends shell out only inside their
#   primitives; AsyncDucker's worker spawns lazily on first dispatch.
# CRITICAL #7 — duck_mode="off" ⇒ self._ducker is None ⇒ every helper returns immediately. Zero
#   overhead, byte-identical behavior (PRD acceptance; pin with a test).
# GOTCHA #8 — Full paths (.venv/bin/python); zsh aliases python3/pytest. Unit tests are CUDA-free
#   and fast; wrap in timeout 600. No ruff/mypy in this repo (pytest is the gate).
```

## Implementation Blueprint

### Data models and structure

None new (the state field `"ducked": bool` joins the existing flat `_state` dict; the ducker is an
injected dependency, not a model).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/feedback.py — the ducked write side
  - ADD "ducked": False to _state (@96-109, near "mode"); ADD set_ducked() cloning set_models_loaded
    (@135-145: always-write + _write(), never notifies); UPDATE the docstring schema line (@11).

Task 2: EDIT tests/test_feedback.py — lockstep (:129 + :441)
  - Both key-set assertions gain "ducked". Run test_feedback.py → green before touching daemon.py.

Task 3: EDIT voice_typing/daemon.py — ctor seam + helpers
  - VERIFY PRECONDITION: ls voice_typing/ducking_async.py (S4) + the S3 volume backend class name.
  - ADD `ducker: Any = None` param (@604-617, after key_listener); wiring @809-816 mirror:
    self._ducker = ducker; if None and cfg.audio.duck_mode != "off": self._ducker = _build_default_ducker(cfg).
  - ADD module-level _build_default_ducker(cfg): tier backend by mode (mpris→MprisBusctlBackend(),
    volume→S3's class) → AsyncDucker(AudioDucker.from_config(cfg, backend)).
  - ADD _duck_engage()/_duck_release() helpers (research §4 verbatim shape: None-guard, dispatch,
    set_ducked(desired), swallow-all → one WARNING).
  - ADD the module-docstring ducking note (Mode A: the seams, never-a-gate, off ⇒ None).

Task 4: EDIT voice_typing/daemon.py — the four seam calls
  - _arm(): self._duck_engage() immediately after `self._feedback.set_listening(True)`.
  - _disarm(): self._duck_release() immediately after `self._feedback.set_listening(False)`.
  - request_shutdown(): self._duck_release() immediately after `self._shutdown.set()`.
  - _handle_dead_host(): self._duck_release() after its `self._feedback.set_listening(False)`.
  - NO edit to cancel().

Task 5: APPEND tests/test_ducking.py — the lifecycle cases
  - _FakeDucker (thread-safe engage/release/set_ducked-call recording) + _make_ducking_daemon
    (copy of tests/test_daemon.py:682-700 passing ducker=fake; feedback fake records set_ducked).
  - The 9 cases (research §6): engage-on-arm; release-on-stop / toggle-off / drain-completion /
    idle-auto-stop (_maybe_auto_stop direct) / HALT (note_user_keypress past the grace) / quit
    (request_shutdown) / dead-host (_handle_dead_host); NO-release-on-cancel (+_listening stays set);
    off-mode ⇒ _ducker is None + zero calls.

Task 6: VALIDATE (§Validation Loop) — all green, no new failures vs G1_BASELINE.md.
```

### Implementation Patterns & Key Details

```python
# The dispatch helper (never-a-gate; desired-state mirror):
def _duck_engage(self) -> None:
    d = self._ducker
    if d is None:                      # duck_mode="off" ⇒ byte-identical behavior
        return
    try:
        d.engage()                     # AsyncDucker: immediate return (S4); idempotent
        self._feedback.set_ducked(True)   # desired state; T3.S2's self-heal reads this
    except Exception:
        logger.warning("ducking: engage dispatch failed (ignored)")

# Seam insertions — anchor text (line numbers are stale; grep these):
#   _arm:              after `self._feedback.set_listening(True)`      → self._duck_engage()
#   _disarm:           after `self._feedback.set_listening(False)`     → self._duck_release()
#   request_shutdown:  after `self._shutdown.set()`                    → self._duck_release()
#   _handle_dead_host: after its `self._feedback.set_listening(False)` → self._duck_release()
#   cancel(): NO EDIT (mic stays hot — PRD)
```

### Integration Points

```yaml
CONSUMED (read-only): AudioDucker (audio_ducking.py, S1 frozen); AsyncDucker (ducking_async.py, S4);
  MprisBusctlBackend (ducking_mpris.py:75, S2); S3's wpctl backend (verify name); cfg.audio (T1, landed).
PRODUCED: ducker= ctor seam; _duck_engage/_duck_release; the four seam calls; Feedback.set_ducked +
  state["ducked"]; lifecycle tests; daemon docstring note.
DOWNSTREAM: T3.S2 consumes state["ducked"] (boot self-heal), adds flush() at quit + ExecStopPost;
  T4 flips the default to "mpris".
DO NOT TOUCH: audio_ducking.py / ducking_mpris.py / ducking_async.py / ducking_volume.py (S1-S4 own);
  config.py + config.toml (T1 landed); cancel(); systemd unit (T3.S2); README (P1.M7); PRD.md/tasks.json.
```

## Validation Loop

### Level 1: Unit suites (the gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_ducking.py -q
# Expected: existing core tests + the new lifecycle cases ALL pass.
timeout 600 .venv/bin/python -m pytest tests/test_feedback.py tests/test_daemon.py -q
# Expected: green (the :129/:441 lockstep took effect; no daemon regression).
```

### Level 2: Full fast sweep vs baseline

```bash
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: no NEW failures beyond tests/G1_BASELINE.md (the recorded pre-change reds).
```

### Level 3: Behavior spot-checks (off-mode purity + seam presence)

```bash
grep -n "_duck_engage\|_duck_release" voice_typing/daemon.py   # 1 engage + 3 release call sites + 2 defs
grep -n "def set_ducked\|\"ducked\"" voice_typing/feedback.py  # setter + seeded field
timeout 60 .venv/bin/python -c "from voice_typing.config import VoiceTypingConfig; \
from voice_typing.daemon import _build_default_ducker; \
d = _build_default_ducker(VoiceTypingConfig()); print('off-mode factory:', d)"  # off ⇒ None (or no-op ducker)
```

### Level 4: Creative & Domain-Specific

Not applicable (no live-audio gate in this task — the real MPRIS/wpctl behavior is T4's acceptance
evidence; here everything is mocked via `_FakeDucker`).

## Final Validation Checklist

### Technical Validation
- [ ] Level 1-2 suites green; no new failures vs `tests/G1_BASELINE.md`.
- [ ] `_duck_engage` called from exactly 1 site (`_arm`); `_duck_release` from exactly 3
      (`_disarm`, `request_shutdown`, `_handle_dead_host`); `cancel()` has none.
- [ ] Off-mode: `_ducker is None`; zero ducking dispatch (pinned by test).

### Feature Validation
- [ ] PRD case (c) pinned: release fires on every disarm path incl HALT and auto-stop (tests 2-8).
- [ ] cancel() does not release; `_listening` stays set (test 9).
- [ ] `"ducked"` mirrors desired state through engage/release; test_feedback lockstep updated.

### Code Quality / Scope
- [ ] Ctor seam mirrors `key_listener=`; construction pure; helpers swallow-all (one WARNING max).
- [ ] No edits to S1-S4 modules, cancel(), config, systemd unit, README.
- [ ] daemon.py module docstring carries the ducking note.

---

## Anti-Patterns to Avoid

- ❌ Don't spawn raw threads at the seams — S4's AsyncDucker IS the non-blocking layer; call it
  inline (immediate return). Raw AudioDucker at a seam would hold its lock across subprocess calls.
- ❌ Don't trust the contract's line numbers (1415/1454/1050/2177…) — ~50 lines stale; grep anchors.
- ❌ Don't add a release in `cancel()` — Backspace-cancel keeps the mic hot (PRD).
- ❌ Don't skip `_handle_dead_host` — it's the child-death-while-ducked edge the contract flagged.
- ❌ Don't add `"ducked"` to feedback without updating test_feedback.py :129 AND :441.
- ❌ Don't make the ctor factory impure (no subprocess/threads at construction — key_listener rule).
- ❌ Don't let ducking gate or block arming — any exception path is swallow → one WARNING → continue.
- ❌ Don't edit S1-S4's modules, the systemd unit (T3.S2), config (T1), or README (P1.M7).
- ❌ Don't use bare python/pytest (zsh aliases); full paths under timeout.

---

## Confidence Score

**8.5/10**. The seam map is pre-verified against the live tree (anchors + funnel proof + the
dead-host edge), the dispatch layer's contract is pinned by S4's PRP, the injection pattern
(`_make_daemon` copy) and the lockstep test pins (:129/:441) are verified, and all 9 test cases are
enumerated. Residual risk (−1.5): (1) S4's `ducking_async.py` and S3's volume backend were NOT on
disk at research time — the implementer must verify both landed and re-check the exact class/API
names (a hard stop if absent); (2) line anchors may drift further before implementation — mitigated
by anchor-text re-location throughout.

# PRP — P1.M2.T3.S2: Crash Safety — ducked flag self-heal + ExecStopPost

## Goal

**Feature Goal**: Complete the ducking crash-safety story (PRD §4.2quinquies "Crash-safety" sentence,
test case (f)) on top of P1.M2.T3.S1's write side: if the daemon dies while media is ducked, the
persisted `"ducked": true` flag in `state.json` drives TWO best-effort heals — (1) a **daemon
startup self-heal** (read the flag before Feedback's first write clobbers it; run the heal
non-blocking on a one-shot thread), and (2) an **`ExecStopPost`** in the systemd unit that runs the
same heal module on every stop (clean stops no-op via the flag). Plus the quit-side guarantee:
**`AsyncDucker.flush(2.0)` at the end of `shutdown()`** so the async release dispatched by S1's
`request_shutdown` seam actually completes before process exit.

**Deliverable** (1 new file, 4 edits):
1. `voice_typing/ducking_heal.py` — NEW: `read_ducked_flag(cfg)`, `heal(cfg)`, `main()` (for
   `python -m voice_typing.ducking_heal`). Stdlib-only + config + ducking_mpris import.
2. `voice_typing/daemon.py` — EDIT: startup self-heal (pre-Feedback read + heal thread) and
   `flush(2.0)` at the end of `shutdown()`; one docstring note line.
3. `systemd/voice-typing.service` — EDIT: `ExecStopPost=__REPO__/.venv/bin/python -m
   voice_typing.ducking_heal` + a Mode A comment explaining the crash-safety rationale.
4. `tests/test_ducking.py` — EDIT: append the heal/crash test section (7 cases).
5. `tests/test_systemd_unit.py` — EDIT: append the ExecStopPost lockstep test (mirrors
   `test_restart_on_failure` @93-96).

**Success Definition**:
- (a) PRD case (f) green: state.json `ducked: true` at daemon start → best-effort release fires
      (heal thread runs; paused players resumed via the mocked backend).
- (b) Clean-stop no-op: `ducked: false` (or file missing) → heal makes ZERO backend calls, exit 0
      (this is also what makes ExecStopPost harmless on every clean stop).
- (c) `shutdown()` flushes the ducker (bounded 2 s) — pinned by test.
- (d) systemd lockstep green: the unit carries exactly one `ExecStopPost=` line invoking the heal
      module with the `__REPO__` placeholder (substituted file-wide by install.sh:119's global sed —
      VERIFIED, no install.sh edit).
- (e) `timeout 600 .venv/bin/python -m pytest tests/test_ducking.py tests/test_systemd_unit.py
      tests/test_feedback.py -q` green; fast sweep shows no new failures vs `tests/G1_BASELINE.md`.

## User Persona

**Target User**: the end user (once `duck_mode` flips on in T4) whose music was paused by ducking
when the daemon crashed / was SIGKILLed — their media must not stay stuck off forever; and any
user whose sink volume was left at 15% by a crashed volume-duck (they get a journal warning
instead of a guessed, ear-blasting restore).

**Use Case**: daemon crashes (OOM, SIGKILL at TimeoutStopSec, bug) mid-dictation with media
ducked → systemd's `ExecStopPost` immediately runs the heal (resume paused players); if the
daemon restarts (`Restart=on-failure`) the startup self-heal covers the same flag; a clean quit
releases + flushes in-process and ExecStopPost no-ops.

**Pain Points Addressed**: ducking without crash safety would make "arm while music plays" a trap
— a crash strands the user's media. PRD §4.2quinquies makes this explicit ("lets a post-crash
restart self-heal … and the systemd unit gets an ExecStopPost best-effort restore").

## Why

- **PRD §4.2quinquies is normative** (research F13): the `ducked` field's stated purpose is
  post-crash self-heal + ExecStopPost restore. S1 (parallel) lands the WRITE side
  (`set_ducked` at every engage/release seam); THIS task is the READ side — without it the flag
  is write-only dead weight and a crash strands media.
- **Post-crash, ordinary `release()` is a no-op** (research F7): the MPRIS ledger and volume
  snapshot are in-memory and die with the process. The heal must be heuristic (resume currently
  paused players; warn on duck-level volume) — designed and justified in research §1.
- **`flush()` at quit closes S1's async gap**: S1's `request_shutdown` seam only DISPATCHES the
  release (AsyncDucker returns immediately); the process can exit before the worker finishes.
  A bounded `flush(2.0)` at the end of `shutdown()` guarantees the clean-stop restore lands
  (budget inside TimeoutStopSec=15: 5 s teardown + 2 s flush + headroom — research §2).
- **ExecStopPost covers the kill paths**: systemd runs ExecStopPost on clean exit, failure, AND
  SIGKILL/timeout (research F14) — exactly the crash net. Gated on the flag, it no-ops on clean
  stops, so it never fights the daemon's own in-process restore.

## What

One shared heal module consumed by both mechanisms; two daemon wiring sites; one unit directive;
lockstep + behavior tests. Heal semantics (research §1, mode-agnostic since the crashed
session's tier is unknowable): gate on `ducked is True`; resume ALL currently-paused MPRIS
players (false positives re-pausable); volume WARN-ONLY when the sink sits at
`duck_volume_pct` (a guessed restore could blast audio — PRD: a clobbering restore is worse
than not ducking); every backend call bounded ≤1 s; every failure → one warning; always exit 0.

### Success Criteria

- [ ] `voice_typing/ducking_heal.py` exists with `read_ducked_flag(cfg)` / `heal(cfg)` / `main()`;
      gate uses `cfg.feedback.resolved_state_file()` (the SINGLE path source of truth — F5);
      backend via `MprisBusctlBackend` (import only — module is S2-frozen).
- [ ] Daemon `__init__` reads the flag BEFORE the `self._feedback = Feedback(...)` line (F4:
      the boot `set_models_loaded` write clobbers it) and, when true, spawns the one-shot
      `vt-duck-heal` daemon thread + one INFO line.
- [ ] End of `shutdown()`: `self._ducker.flush(2.0)` behind a None-guard, swallow-all.
- [ ] Unit gains `ExecStopPost=__REPO__/.venv/bin/python -m voice_typing.ducking_heal` + the
      Mode A crash-safety comment (item DOCS requirement).
- [ ] `test_systemd_unit.py` gains the exact-line lockstep assert (§Implementation).
- [ ] The 7 test_ducking.py heal cases pass (research §4); no new failures vs G1_BASELINE.md.

## All Needed Context

### Context Completeness Check

_Pass._ The research note carries every verified fact: the install.sh sed-is-global finding (F1),
Feedback's ctor-doesn't-write / setters-clobber timing (F4), the path resolver (F5), flush's
existence + signature (F6), release-is-noop-post-crash (F7), frozen-module import rules (F8),
AudioConfig fields (F9), current daemon anchors (F12), the heal design with its documented
judgment call (§1), the exact ExecStopPost line + comment + lockstep test (§3), and the 7-case
test matrix (§4). A fresh implementer needs nothing beyond the research note + the cited files.

### Documentation & References

```yaml
# MUST READ — every verified fact + the heal design + test matrix.
- docfile: plan/008_a47116bb2b79/P1M2T3S2/research/crash_safety_research.md
  why: "§0 the 14 verified facts (F1-F14, each with file:line). §1 the heal design + the
        warn-only-volume judgment call. §2 the two daemon wiring sites with rationale. §3 the
        exact ExecStopPost directive + comment + lockstep test. §4 the 7-case test matrix. §6
        validation commands."
  section: "ALL load-bearing."

# MUST READ — the PARALLEL CONTRACT (S1): defines what this task consumes.
- docfile: plan/008_a47116bb2b79/P1M2T3S1/PRP.md
  why: "S1 delivers: Feedback.set_ducked + \"ducked\": False seed; ducker= ctor seam +
        _build_default_ducker (off ⇒ None ⇒ self._ducker is None); _duck_engage/_duck_release
        helpers; the 4 seam calls (incl. request_shutdown's release dispatch — which is WHY this
        task adds flush at quit); test_ducking.py _FakeDucker + _make_ducking_daemon fixtures.
        Its DOWNSTREAM note names T3.S2 as the flush + ExecStopPost owner. Treat as landed."
  critical: "If S1's pieces are NOT on disk at impl time (grep set_ducked / _duck_release in
             daemon.py+feedback.py), the release/flush test cannot pass — verify, and if absent
             report rather than reimplementing S1."

# MUST READ — the authoritative seams doc (its §2 feedback recipe + §4 unit/test/install facts).
- docfile: plan/008_a47116bb2b79/architecture/d1_ducking_seams.md
  why: "§2 the ducked recipe + 'Post-crash self-heal: ducked:true … is the signal ExecStopPost /
        next boot checks'. §4 the unit directives inventory, the lockstep-test guidance
        (mirroring 94-96), and the __REPO__ caution."
  critical: "Its 'install.sh seds __REPO__ in ExecStart only' worry is SUPERSEDED by research
             F1 — the sed at install.sh:119 is file-wide (g flag). Do not add an install.sh edit."

# MUST READ — the frozen dispatch layer (flush lives here) + the backend the heal reuses.
- file: voice_typing/ducking_async.py
  why: "AsyncDucker.flush(timeout=2.0) -> bool @84 — the exact call shutdown() makes."
- file: voice_typing/ducking_mpris.py
  why: "MprisBusctlBackend @75: list_players()/resume_player(name)/get_sink_volume_pct() — the
        heal's backend (IMPORT only; module is S2-owned/frozen). Mirror its bounded _run helper
        style for any direct subprocess the heal needs."
- file: voice_typing/audio_ducking.py
  why: "READ for _VOL_EPS (the volume compare epsilon the heal reuses) + the _call
        swallow-to-one-warning discipline the heal clones. NEVER edit (S1 frozen)."

# MUST READ — the files being edited.
- file: voice_typing/daemon.py
  why: "__init__ @604 (Feedback ctor line = the pre-read anchor — grep 'self._feedback =
        Feedback'); run() @953; request_shutdown() @2207 (S1's release dispatch is there);
        shutdown() ~@2210+ (single-flight via _teardown_done @660; teardown runs OUTSIDE _lock —
        append flush at its END)."
  gotcha: "The flag read MUST precede the Feedback ctor — the boot set_models_loaded call (also
           in __init__) is the first state write and clobbers ducked to the seeded False (F4)."
- file: voice_typing/feedback.py
  why: "READ: resolved_state_file() (the path source of truth, F5), _write() atomicity, set_ducked
        (S1's — read side only here). NOT edited by this task (S1 owns the edit)."
- file: systemd/voice-typing.service
  why: "EDIT: add ExecStopPost + the Mode A comment (research §3 verbatim). Note the file's
        comment conventions (long rationale comments above directives)."
- file: install.sh
  why: "READ-ONLY: line 119 `sed -i \"s#__REPO__#$REPO#g\"` is file-wide — covers the new
        ExecStopPost. NO EDIT (F1)."
- file: tests/test_systemd_unit.py
  why: "EDIT: append the ExecStopPost test; _unit_lines() @45 strips comments (assert against
        the directive line); mirror test_restart_on_failure @93-96 exact-line style."
- file: tests/test_ducking.py
  why: "EDIT: append the heal section (research §4). Core tests @97-240 show the fake-backend
        fixture style (_FakeBackend with recorded calls). S1's _FakeDucker/_make_ducking_daemon
        are contract — reuse if on disk, else a local minimal fake (F11)."
- file: voice_typing/config.py
  why: "READ: AudioConfig @218 (duck_mode/duck_volume_pct) + load path for the heal's main();
        FeedbackConfig.resolved_state_file."

# CONTEXT — the PRD spec.
- docfile: PRD.md  # §4.2quinquies
  why: "The Crash-safety sentence + test case (f) + failure discipline (never a gate, bounded
        calls, one-line failures) the heal must honor."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # EDIT: startup self-heal read+thread; flush at shutdown end; docstring line
├── ducking_heal.py      # CREATE: read_ducked_flag / heal / main  (the shared crash-heal module)
├── feedback.py          # READ (S1 edits it): resolved_state_file, set_ducked, _write
├── audio_ducking.py     # READ (frozen): _VOL_EPS, _call discipline
├── ducking_mpris.py     # READ (frozen): MprisBusctlBackend
├── ducking_async.py     # READ (frozen): AsyncDucker.flush
└── config.py            # READ: AudioConfig, FeedbackConfig.resolved_state_file
systemd/voice-typing.service   # EDIT: ExecStopPost + Mode A comment
install.sh                     # READ (verified: sed already covers __REPO__ file-wide)
tests/
├── test_ducking.py           # EDIT: append 7 heal cases
└── test_systemd_unit.py      # EDIT: append ExecStopPost lockstep test
```

### Desired Codebase tree (what changes)

```bash
# 1 new file + 4 edits (above). ducking_heal.py ~90 lines; daemon.py +~20; unit +~8; tests +~140.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ORDERING: the ducked-flag read MUST run BEFORE the Feedback ctor line in daemon
#   __init__ (F4): Feedback.__init__ doesn't write, but the boot set_models_loaded(...) call in
#   the same __init__ is the first write and resets ducked to the seeded False.
# CRITICAL #2 — POST-CRASH release() IS A NO-OP (F7): never "heal" by calling the ducker's
#   release(); the ledger/snapshot are gone. The heal is its own heuristic (research §1).
# CRITICAL #3 — VOLUME HEAL IS WARN-ONLY (documented decision): no safe restore target exists
#   post-crash; a guessed value can blast audio. Resume-the-paused is fine (re-pausable); a
#   volume guess is not. Keep the rationale comment in the code.
# CRITICAL #4 — ducking_heal must be stdlib-light (json/logging/subprocess/threading + config +
#   ducking_mpris): it runs via .venv/bin/python WITHOUT launch_daemon.sh's LD_LIBRARY_PATH
#   (no CUDA imports allowed — never import daemon.py or recorder_host from it).
# CRITICAL #5 — S1 is PARALLEL: verify its pieces landed (grep set_ducked in feedback.py,
#   _duck_release in daemon.py) before writing the flush test; report if absent — do NOT
#   reimplement S1. Reuse its _FakeDucker/_make_ducking_daemon if present (F11).
# CRITICAL #6 — The heal ALWAYS exits 0 / never raises: ExecStopPost failure is journal noise
#   only, and the daemon's boot thread must never crash the daemon. Swallow-all → one WARNING.
# CRITICAL #7 — No install.sh edit (F1): the sed is file-wide. Any test asserting substitution
#   just pins the __REPO__ placeholder form in the unit (the §3 exact-line assert does this).
# CRITICAL #8 — Full paths (.venv/bin/python); zsh aliases python3/pytest. Tests CUDA-free,
#   fast; wrap in timeout 600. No ruff/mypy in this repo — pytest is the gate.
# GOTCHA #9 — resolved_state_file() raises RuntimeError when the path is empty AND XDG_RUNTIME_DIR
#   is unset (outside real sessions): read_ducked_flag must catch that and treat as "no flag"
#   (missing file), never propagate into daemon boot or ExecStopPost.
```

## Implementation Blueprint

### Data models and structure

None new (the `"ducked": bool` state field is S1's; the heal is functions, not a model).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: VERIFY PRECONDITIONS (S1 parallel contract)
  - grep -n "set_ducked\|\"ducked\"" voice_typing/feedback.py        # S1's write side landed
  - grep -n "_duck_release\|ducker" voice_typing/daemon.py           # S1's seams landed
  - grep -n "def flush" voice_typing/ducking_async.py                # F6
  - If S1's pieces absent → STOP and report (do not reimplement S1).

Task 2: CREATE voice_typing/ducking_heal.py
  - read_ducked_flag(cfg) -> bool: path = cfg.feedback.resolved_state_file() inside try
    (RuntimeError/XDG-unset → False); json.load; return state.get("ducked") is True. Missing
    file / bad JSON → False (never raise).
  - heal(cfg): gate on read_ducked_flag; if False → return (zero backend calls). Else:
    (a) MPRIS: backend = MprisBusctlBackend(); for p in backend.list_players(): if not
        p.playing → backend.resume_player(p.name) (log each resume, swallow each failure).
    (b) Volume: cur = backend.get_sink_volume_pct(); if cur is not None and
        abs(cur - cfg.audio.duck_volume_pct) <= _VOL_EPS → logger.warning(... duck-level note),
        NO set call (CRITICAL #3 + code comment).
  - main(): load config (mirror daemon's config load path), heal(), exit 0 always.
  - Every direct subprocess bounded ≤1 s (mirror ducking_mpris._run); CRITICAL #4 + #6.

Task 3: EDIT voice_typing/daemon.py — startup self-heal
  - In __init__, BEFORE the `self._feedback = Feedback(...)` line (CRITICAL #1):
    `self._startup_ducked = ducking_heal.read_ducked_flag(cfg)` (import at module top).
  - After the ctor wiring block: if self._startup_ducked: log one INFO + spawn
    threading.Thread(target=ducking_heal.heal, args=(cfg,), daemon=True, name="vt-duck-heal").
  - One module-docstring line: crash-safety = startup self-heal + ExecStopPost + flush-at-quit.

Task 4: EDIT voice_typing/daemon.py — flush at quit
  - At the END of shutdown() (after host teardown, before return):
    if self._ducker is not None: try: self._ducker.flush(2.0) except Exception: warning.
    Comment: closes S1's async-release gap; 2 s inside the TimeoutStopSec=15 budget.

Task 5: EDIT systemd/voice-typing.service — ExecStopPost + Mode A comment
  - Insert research §3 verbatim (comment + `ExecStopPost=__REPO__/.venv/bin/python -m
    voice_typing.ducking_heal`) after the RestartSec line.

Task 6: EDIT tests/test_systemd_unit.py — lockstep (mirror :93-96)
  - test_execstoppost_ducking_crash_heal (research §3 code block): exactly one ExecStopPost line,
    exact content (doubles as the __REPO__-placeholder pin).

Task 7: APPEND tests/test_ducking.py — the 7 heal cases (research §4)
  - Fake backend (recorded calls; style of the core _FakeBackend @97-240) + tmp_path state file
    written via Feedback (or raw json) seeded ducked true/false/absent.
  - Case 6 drives the daemon ctor (tmp state_file in cfg) and JOINS the heal thread before
    asserting; case 7 uses S1's _make_ducking_daemon or a local fake ducker recording flush().
    Fake ducker needs a flush() recorder if S1's lacks one (extend locally, don't edit S1's).

Task 8: VALIDATE (§Validation Loop) — all green; no new failures vs tests/G1_BASELINE.md.
```

### Implementation Patterns & Key Details

```python
# ducking_heal.heal — the gate + heuristic (CRITICAL #2/#3/#6):
def heal(cfg) -> None:
    if not read_ducked_flag(cfg):
        return                                  # clean-stop / no crash → zero backend calls
    backend = MprisBusctlBackend()
    for p in _bounded(lambda: backend.list_players(), []):
        if not p.playing:
            if _bounded(lambda n=p.name: backend.resume_player(n), False):
                logger.info("ducking crash-heal: resumed %s", p.name)
    cur = _bounded(backend.get_sink_volume_pct, None)
    if cur is not None and abs(cur - cfg.audio.duck_volume_pct) <= _VOL_EPS:
        # WARN-ONLY: the pre-duck volume is unknowable post-crash; a guessed restore could
        # blast audio — worse than a manual bump (PRD: a clobbering restore is worse than not ducking).
        logger.warning("ducking crash-heal: sink left at duck level %.0f%% by a crash; "
                       "restore it manually if unintended", cur)

# daemon __init__ pre-read (CRITICAL #1 — BEFORE the Feedback ctor line):
self._startup_ducked = ducking_heal.read_ducked_flag(cfg)
# ... later, after wiring:
if self._startup_ducked:
    logger.info("voice-typing: crash-recovery: ducked flag set; best-effort media release")
    threading.Thread(target=ducking_heal.heal, args=(cfg,), daemon=True,
                     name="vt-duck-heal").start()

# shutdown() tail (closes S1's async gap):
if self._ducker is not None:
    try:
        self._ducker.flush(2.0)   # bounded; inside the 15 s TimeoutStopSec budget
    except Exception:
        logger.warning("ducking: flush at quit failed (ignored)")
```

### Integration Points

```yaml
CONSUMED (read-only): S1's set_ducked/seams/ducker seam (parallel contract); AsyncDucker.flush
  (ducking_async.py:84); MprisBusctlBackend (ducking_mpris.py:75); _VOL_EPS (audio_ducking.py);
  cfg.feedback.resolved_state_file(); cfg.audio.duck_volume_pct.
PRODUCED: voice_typing/ducking_heal.py (read_ducked_flag/heal/main); daemon startup self-heal +
  shutdown flush; ExecStopPost + Mode A comment; 8 new tests (7 ducking + 1 systemd lockstep).
DOWNSTREAM: T4 (default flip + live acceptance) — the heal becomes user-visible once ducking is
  on; P1.M7 docs reference the unit comment.
DO NOT TOUCH: audio_ducking.py / ducking_mpris.py / ducking_volume.py / ducking_async.py
  (S1-S4 frozen); install.sh (F1 — sed already covers __REPO__ file-wide); config.py/config.toml
  (T1 landed); feedback.py (S1 owns its edit); README/ACCEPTANCE.md (P1.M7); PRD.md/tasks.json.
```

## Validation Loop

### Level 1: Unit suites (the gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_ducking.py -q
# Expected: core (S1-S4 era) + S1 lifecycle + the 7 new heal cases ALL pass.
timeout 600 .venv/bin/python -m pytest tests/test_systemd_unit.py tests/test_feedback.py -q
# Expected: green — the new ExecStopPost lockstep passes; feedback untouched by this task.
```

### Level 2: Full fast sweep vs baseline

```bash
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: no NEW failures beyond tests/G1_BASELINE.md (the recorded pre-change reds).
```

### Level 3: Behavior spot-checks (module + unit + ordering)

```bash
timeout 60 .venv/bin/python -m voice_typing.ducking_heal; echo "exit=$?"
# Expected: exit=0, quiet (real state.json has ducked:false/absent → gate no-ops).
grep -n "ExecStopPost" systemd/voice-typing.service          # exactly 1 directive (+comment)
grep -n "read_ducked_flag\|vt-duck-heal\|flush" voice_typing/daemon.py
# Expected: pre-read BEFORE the Feedback ctor line (visually confirm ordering); heal thread;
# flush at shutdown tail.
XDG_RUNTIME_DIR=/tmp/vt-heal-check timeout 60 .venv/bin/python -c "
from voice_typing.ducking_heal import read_ducked_flag
from voice_typing.config import VoiceTypingConfig
print(read_ducked_flag(VoiceTypingConfig()))"   # absent file → False, no raise
```

### Level 4: Creative & Domain-Specific

Not applicable — no live-audio gate here (all mocked; T4 owns live acceptance). The
ExecStopPost crash path is exercised structurally: flag-gate semantics are unit-tested and the
directive's presence/exact form is lockstep-tested.

## Final Validation Checklist

### Technical Validation
- [ ] Level 1-2 green; no new failures vs `tests/G1_BASELINE.md`.
- [ ] `python -m voice_typing.ducking_heal` exits 0 under timeout, no output when unflagged.

### Feature Validation
- [ ] PRD case (f) green: ducked flag → release at next daemon start (test 6).
- [ ] Heal no-ops (zero backend calls) when ducked is false / file missing (tests 1-2).
- [ ] Resume-paused heuristic + warn-only volume (tests 3-4); failures swallowed (test 5).
- [ ] shutdown() flushes once, bounded (test 7).
- [ ] Unit carries exactly one ExecStopPost line, exact form, `__REPO__` placeholder (test 8).

### Code Quality / Scope
- [ ] ducking_heal.py stdlib-light (no daemon/recorder_host/CUDA imports — CRITICAL #4).
- [ ] Ordering: flag read precedes the Feedback ctor (CRITICAL #1); heal thread non-blocking.
- [ ] No edits to S1-S4 modules, install.sh, config, feedback.py, README, PRD/tasks.json.
- [ ] Mode A comment in the unit explains the crash-safety rationale (item DOCS requirement).

---

## Anti-Patterns to Avoid

- ❌ Don't read the flag AFTER Feedback's first write — the boot set_models_loaded call clobbers
  it (CRITICAL #1).
- ❌ Don't "heal" by calling ducker.release() — post-crash bookkeeping is empty, it no-ops (F7).
- ❌ Don't auto-restore volume to a guessed value — warn only (CRITICAL #3).
- ❌ Don't add an install.sh sed — it's already file-wide (F1/CRITICAL #7).
- ❌ Don't let the heal raise, block boot, or gate anything — always exit 0, bounded calls,
  one-warning discipline (CRITICAL #6).
- ❌ Don't import daemon.py/recorder_host/CUDA-adjacent modules from ducking_heal — ExecStopPost
  runs it without launch_daemon.sh's LD_LIBRARY_PATH (CRITICAL #4).
- ❌ Don't reimplement S1 if its pieces are missing — STOP and report (CRITICAL #5).
- ❌ Don't use bare python/pytest (zsh aliases); full paths under timeout.

---

## Confidence Score

**8.5/10**. Every integration fact is verified live (sed-is-global, flush signature, ctor
write-timing, path resolver, frozen-module boundaries), the heal design's one judgment call
(warn-only volume) is pre-decided with PRD-anchored rationale, and the test matrix is enumerated.
Residual risk (−1.5): S1 is landing in parallel — its exact fixture names
(`_FakeDucker`/`_make_ducking_daemon`) and whether its fake records `flush()` are contract-level,
not disk-verified; the runbook's verify-first step (Task 1) plus local-fake fallback covers both.

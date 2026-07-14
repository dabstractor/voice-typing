# PRP — P1.M2.T1.S1: Add `set_phase('idle')` to `_disarm()` to reflect the 'loaded / not listening' lifecycle state

## Goal

**Feature Goal**: Fix bugfix **Issue 2** (Major): after any disarm (`stop`, `toggle`-off, or the 30 s auto-stop), the `phase` field in `state.json` and the `voicectl status` `phase:` line must return to **`idle`** (the "loaded / not listening" lifecycle state per PRD §4.2bis/§4.6) instead of staying stuck at the last VAD value (`listening`/`speaking`). This is a **one-line addition** to `VoiceTypingDaemon._disarm()`.

**Deliverable** (one source edit; no new files, no test file — see S2 boundary):
- `voice_typing/daemon.py` — in `_disarm()`, immediately after `self._feedback.set_listening(False)`, add `self._feedback.set_phase("idle")`. Verbatim oldText→newText in Implementation Blueprint → Task 1.

**Success Definition**:
- (a) `_disarm()` calls `self._feedback.set_phase("idle")` right after `set_listening(False)`.
- (b) After `voicectl start` → `stop` (or toggle-off, or the 30 s auto-stop), `jq .phase "$XDG_RUNTIME_DIR/voice-typing/state.json"` → `"idle"` (currently `"listening"`/`"speaking"`), and `voicectl status` shows `phase: idle` with `listening: off` (no longer contradictory).
- (c) The full fast pytest suite stays GREEN (the additive `set_phase("idle")` does not break any existing `fb.phases` assertion — verified; see Context).
- (d) No other file touched; the optional VAD-relay gate is NOT added (deferred — "only if observed").

## User Persona

Not applicable (behavior/state-correctness fix; no new config/API surface — DOCS: none).

## Why

- **The state contract is violated today.** PRD §4.6 ("once loaded, `phase` cycles `idle`/`listening`/`speaking`") + §4.2bis (`loaded / not listening` ⇒ phase `idle`). Today `phase` freezes at the last VAD value after any stop, so `voicectl status` reports a self-contradictory `listening: off / phase: listening` (or `speaking`). Any consumer keying off `phase` (a future overlay UI, a lifecycle-rendering script) is misled. (bugfix Issue 2.)
- **`_disarm()` is the single chokepoint.** It is the one method called by all three disarm paths (`stop()`, `toggle()` disarm-branch, `_maybe_auto_stop()` 30 s auto-stop). One line here fixes all three. No other listening/phase transition is missing (`__init__`, `_load_host` success, `_unload`, `_handle_dead_host` all already set phase correctly).
- **The visible tmux line is unaffected** (`status.sh` keys off `.listening`, not `.phase`), so this is correctness for the documented state contract + future consumers, not a cosmetic fix.

## What

Add one line to `_disarm()`:
```python
self._feedback.set_phase("idle")  # Issue 2 / P1.M2.T1.S1: 'loaded / not listening' ⇒ phase idle (PRD §4.2bis, §4.6)
```
`feedback.set_phase` writes `state["phase"]="idle"` + an atomic state-file flush, so both `state.json` and `voicectl status` (reads `feedback.snapshot()["phase"]`) reflect `idle` immediately on every disarm.

### Success Criteria

- [ ] `_disarm()` calls `self._feedback.set_phase("idle")` immediately after `self._feedback.set_listening(False)`.
- [ ] `stop`/`toggle`-off/auto-stop each leave `phase == "idle"` (S2 adds the committed pytest; S1 proves it via the inline check in Validation L3).
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (no regression).
- [ ] Only `voice_typing/daemon.py` modified; the VAD-relay gate is NOT added.

## All Needed Context

### Context Completeness Check

_Pass._ The defect root cause is confirmed in `architecture/bug_analysis.md §Issue 2` and in the code (`_disarm()` never sets phase); the exact edit site is given with a unique anchor (the `_safe_abort` NOTE comment is only in `_disarm()`); the no-regression claim is verified (no existing test asserts `fb.phases` after a disarm); and the test-ownership boundary (S1=code, S2=test) is explicit. A developer new to the repo can apply the one-line patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — root cause + the one-line fix + the optional-gate deferral
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "§Issue 2 (MAJOR): '_disarm() ... NEVER calls feedback.set_phase(\"idle\")'. Suggested fix: 'In _disarm(),
        after self._feedback.set_listening(False), call self._feedback.set_phase(\"idle\")'. Key code location:
        daemon.py _disarm() (~970; actually ~851 in the current tree). Optional hardening (gate the (\"vad\",...)
        relay) is 'a secondary measure IF observed in practice' — S1 does NOT add it."
  section: "Issue 2 (the 'phase field stays listening/speaking after stop' section)."

# MUST READ — the exact edit site (the one method this changes)
- file: voice_typing/daemon.py
  why: "VoiceTypingDaemon._disarm() @851. Body tail @870-875: set_microphone(False) -> set_listening(False) ->
        the '# NOTE: caller MUST call self._safe_abort() ...' comment. The fix inserts set_phase('idle') between
        set_listening(False) and that NOTE comment (the NOTE is the unique anchor — set_listening(False) also
        appears in run()@708 and elsewhere). _disarm is the chokepoint called by stop()/toggle()/_maybe_auto_stop()."
  critical: "Anchor the edit on the '# NOTE: caller MUST call self._safe_abort()' comment (unique to _disarm), NOT on
             set_listening(False) alone (it is not unique). _arm() @841 is UNCHANGED. Do NOT touch _handle_dead_host
             (Issue 3 / P1.M2.T2) or _load_host/_unload (they already set phase correctly)."

# THE PRD CONTRACT this honors
- file: PRD.md
  why: "§4.2bis lifecycle: 'loaded / not listening ⇒ phase idle; loaded / listening ⇒ phase listening'. §4.6:
        'once loaded, phase cycles idle/listening/speaking'. This fix makes _disarm() close the cycle back to idle."

# THE NO-REGRESSION PROOF + the test-fake interface
- file: tests/test_daemon.py
  why: "_FakeFeedback.set_phase (42) ONLY appends to fb.phases (37) — it does not touch listening_states/finals, so
        the added set_phase('idle') only adds an 'idle' entry to fb.phases on each disarm. Every existing fb.phases
        assertion (239/247/250/307/1277/1290/2528/2870/2930) is in a VAD-callback or _load_host/_unload test — NONE
        go through _disarm(), so none see the extra 'idle'. The disarm/stop/toggle/auto-stop tests assert listening/
        abort/_disarmed_monotonic, NOT fb.phases. => the suite stays green."
  critical: "S2 (P1.M2.T1.S2, Planned) owns the committed pytest ('Test phase returns to idle after disarm').
             S1 delivers ONLY the code change; S1's validation uses a throwaway inline check (NOT a committed test
             file) to avoid pre-empting S2."

# THE OPTIONAL GATE SITE (do NOT edit — documented so the implementer doesn't speculate-add it)
- file: voice_typing/recorder_host.py
  why: "RecorderHost._dispatch('vad') @348-350 calls self._feedback.set_phase(phase) unconditionally — a stray late
        VAD event could re-flip phase after disarm. The item + bug-analysis say gate it ONLY if observed. The host
        does NOT currently know the daemon's _listening state (it holds self._feedback, not the listening Event),
        so gating is an invasive cross-layer change for an unobserved theoretical race. The next disarm resets it.
        S1 does NOT add the gate."
  critical: "Do NOT edit recorder_host.py. If a stray re-flip is ever seen in practice, a follow-up task adds the
             gate (the host would need a listening-state callback). Speculative gating is an anti-pattern here."

# PARALLEL CONTEXT — P1.M1.T2.S3 (SIGTERM teardown; NO overlap)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T2S3/PRP.md
  why: "T2.S3 (Implementing) is the SIGTERM teardown test: concurrent request_shutdown()+shutdown() -> single
        host.stop(). It touches daemon.py request_shutdown/shutdown/_bounded_shutdown + adds a test to test_daemon.py.
        NO overlap with _disarm()/phase (Issue 1 vs Issue 2; different methods)."
```

### Current Codebase tree (relevant slice — the one file this task edits)

```bash
/home/dustin/projects/voice-typing/
└── voice_typing/
    └── daemon.py   # EDIT: _disarm() @851 — insert ONE line (set_phase('idle')) after set_listening(False) @874.
# feedback.py (set_phase writes state.json — UNCHANGED). recorder_host.py (_dispatch('vad') — UNCHANGED). No new files.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py   # EDIT — one line added inside _disarm().
# NOTHING ELSE. (test_daemon.py = P1.M2.T1.S2. recorder_host.py gate = deferred. README/ACCEPTANCE = P1.M4.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ANCHOR THE EDIT ON THE UNIQUE NOTE COMMENT. self._feedback.set_listening(False) appears in run()
#   (@708), _disarm (@874), and possibly _handle_dead_host. Match the TWO-line block
#   `set_listening(False)` + `# NOTE: caller MUST call self._safe_abort() AFTER releasing _lock (see start/stop/toggle).`
#   — that NOTE comment is UNIQUE to _disarm(), so the oldText is unambiguous. (research §2.)

# CRITICAL #2 — PLACE set_phase('idle') AFTER set_listening(False), not before. set_listening(False) is the
#   "now disarmed" marker; set_phase('idle') reflects that state. Order within _disarm() (both under _lock) does
#   not affect correctness, but keeping it adjacent to set_listening(False) reads naturally + matches the bug-analysis.

# CRITICAL #3 — DO NOT ADD THE VAD-RELAY GATE. The item + bug-analysis say gate the ("vad",...) relay ONLY if a
#   stray re-flip is OBSERVED in practice. The host (recorder_host._dispatch) does not know the daemon's _listening
#   state — gating is an invasive cross-layer change for an unobserved race. The next disarm resets phase. S1 = the
#   one-liner only. (research §5.)

# CRITICAL #4 — DO NOT TOUCH _handle_dead_host / _load_host / _unload. Those already set phase correctly ('unloaded'/
#   'idle'). _disarm() is the ONLY missing case. _handle_dead_host is Issue 3 (P1.M2.T2) — out of scope. (research §3.)

# GOTCHA #5 — S1 = CODE ONLY; S2 OWNS THE TEST. Do NOT add a committed pytest for phase-after-disarm (that is
#   P1.M2.T1.S2). S1's validation = static grep + existing fast suite green + a throwaway inline proof. (research §6.)

# GOTCHA #6 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare python/pytest.

# GOTCHA #7 — pytest>=9.1.1 is the runner; NO ruff/mypy. Validation = py_compile + pytest.
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/types change. This adds one method call (`feedback.set_phase("idle")`) inside an existing method.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — add set_phase('idle') to _disarm()
  - FIND _disarm() (@851). The edit site is the body tail. Apply this ONE exact oldText -> newText:
      OLD:
            self._feedback.set_listening(False)
            # NOTE: caller MUST call self._safe_abort() AFTER releasing _lock (see start/stop/toggle).
      NEW:
            self._feedback.set_listening(False)
            self._feedback.set_phase("idle")  # Issue 2 / P1.M2.T1.S1: 'loaded / not listening' ⇒ phase idle (PRD §4.2bis, §4.6)
            # NOTE: caller MUST call self._safe_abort() AFTER releasing _lock (see start/stop/toggle).
  - WHY: _disarm() is the chokepoint for all 3 disarm paths (stop/toggle-off/30s auto-stop). set_phase('idle')
    writes state["phase"]="idle" + an atomic state.json flush, so voicectl status + state.json immediately reflect
    the 'loaded / not listening' state. The NOTE comment is the unique anchor (CRITICAL #1).
  - DO NOT: add the line in _arm(); touch _handle_dead_host/_load_host/_unload (CRITICAL #4); add the VAD-relay
    gate in recorder_host.py (CRITICAL #3); add a committed test (GOTCHA #5).

Task 2: VALIDATE — run the Validation Loop L1-L3; fix until green. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M2.T1.S1: reset phase to 'idle' on disarm (stop/toggle-off/auto-stop) — Issue 2 fix".
```

### Implementation Patterns & Key Details

```python
# PATTERN — _disarm() closes the phase cycle. set_listening(False) marks 'disarmed'; set_phase('idle') publishes
# the matching lifecycle phase. set_phase ALWAYS writes state.json (feedback.py), so status.json + voicectl status
# (reads feedback.snapshot()["phase"]) agree immediately.
self._feedback.set_listening(False)
self._feedback.set_phase("idle")   # <- THE FIX (PRD §4.2bis: loaded / not listening ⇒ phase idle)
# NOTE: caller MUST call self._safe_abort() AFTER releasing _lock (see start/stop/toggle).
```

### Integration Points

```yaml
UPSTREAM CONSUMED — feedback.set_phase (UNCHANGED): writes state["phase"] + atomic state.json flush. Called under
  _lock (same as the adjacent set_listening(False)) — set_phase is lock-free by design (Feedback relies on CPython
  atomic dict ops + tempfile+os.replace), so holding _lock briefly is fine.

DOWNSTREAM — P1.M2.T1.S2 (the committed pytest): arms -> triggers a VAD phase -> disarms (all 3 paths) -> asserts
  phase == 'idle'. S1's one-liner is what makes those assertions pass. No overlap (S1=code, S2=test).

UNCHANGED: _arm(), _handle_dead_host (Issue 3 / P1.M2.T2), _load_host/_unload (already set phase), recorder_host.py
  (_dispatch('vad') relay — the optional gate is deferred), feedback.py, config, ctl.py, status.sh, systemd, README.

PARALLEL — P1.M1.T2.S3 (SIGTERM teardown): touches request_shutdown/shutdown/_bounded_shutdown + a test; NO overlap
  with _disarm()/phase.

BUILD ARTIFACTS: NO new files, NO pyproject/uv.lock/.venv changes. Validation = py_compile + pytest.
```

## Validation Loop

> Full paths in every bash command (zsh aliases — GOTCHA #6). Run from `/home/dustin/projects/voice-typing`. pytest is
> the runner (NO ruff/mypy — GOTCHA #7). L1 is static; L2 is the no-regression suite; L3 is a throwaway inline proof
> (NOT a committed test — S2 owns that).

### Level 1: the edit is in place (static)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile voice_typing/daemon.py && echo "L1 PASS: py_compile" || echo "L1 FAIL"
# the one-liner is present, exactly once, inside _disarm (after set_listening(False), before the _safe_abort NOTE):
grep -nE 'self\._feedback\.set_phase\("idle"\)' voice_typing/daemon.py | grep -i 'idle'
# confirm it sits in _disarm (between set_listening(False) and the _safe_abort NOTE):
awk '/def _disarm\(/{f=1} f&&/set_feedback.set_phase\("idle"\)|def _arm\(|def _touch_speech\(/{print NR": "$0; if(/def _arm|def _touch/)f=0}' voice_typing/daemon.py
# Expected: py_compile clean; exactly one set_phase("idle") line, and it appears under _disarm (before _touch_speech).
```

### Level 2: no regression — the full fast suite stays green

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. The additive set_phase('idle') only appends to fb.phases on disarm; NO existing test asserts
# fb.phases after a disarm (research §4), so nothing breaks. (test_feed_audio.py is the heavy GPU suite — ignored.)
```

### Level 3: throwaway inline proof — disarm drives phase to 'idle' (NOT a committed test; S2 owns the pytest)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" - <<'PYEOF'
# Prove the one-liner works via the test fakes (no real daemon/CUDA). NOT committed — S2 writes the real pytest.
import voice_typing.daemon as d
from voice_typing.config import VoiceTypingConfig

class _StubHost:
    def __init__(self): self.mic = []
    def set_microphone(self, on): self.mic.append(on)
    def is_alive(self): return True

class _FB:
    def __init__(self): self.phase = "unloaded"; self.listening = None
    def set_phase(self, p): self.phase = p
    def set_listening(self, x): self.listening = x
    def set_models_loaded(self, x): pass
    def update_partial(self, t): pass
    def record_final(self, t): pass
    def snapshot(self): return {"phase": self.phase}

fb = _FB()
host = _StubHost()
# Build a daemon already-loaded (recorder/host injected) so _disarm is reachable without _load_host.
dae = d.VoiceTypingDaemon(VoiceTypingConfig(), fb, recorder=object(), backend=type("B",(),{"type_text":lambda s,t:None})(),
                          mic_prober=lambda:(True,None))
dae._host = host
dae._feedback.set_phase("speaking")     # simulate VAD reached 'speaking' before the stop
assert fb.phase == "speaking"
dae._disarm()                           # the disarm path (stop/toggle-off/auto-stop all funnel here)
assert fb.listening is False
assert fb.phase == "idle", f"expected phase 'idle' after disarm, got {fb.phase!r}"
print("L3 PASS: _disarm() drives phase -> 'idle' (was 'speaking')")
PYEOF
# Expected: "L3 PASS: _disarm() drives phase -> 'idle'". If it prints the assertion error, the one-liner wasn't added
# in _disarm (re-check Task 1 — the edit must be inside _disarm, after set_listening(False)).
```

### Level 4: scope guard

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY voice_typing/daemon.py (modified). No recorder_host.py, no feedback.py, no test_daemon.py (S2), no
# config/ctl/systemd/README. (P1.M1.T2.S3 may edit daemon.py shutdown paths + a test in parallel — different lines.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: py_compile clean; exactly one `set_phase("idle")` inside `_disarm()` (after `set_listening(False)`, before the `_safe_abort` NOTE).
- [ ] L2: `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] L3: throwaway inline proof — `_disarm()` drives `phase` → `'idle'`.
- [ ] L4: `git status` shows ONLY `voice_typing/daemon.py`.

### Feature Validation
- [ ] `_disarm()` resets phase to `'idle'` (covers stop / toggle-off / 30 s auto-stop — all funnel through `_disarm()`).
- [ ] No regression (existing suite green); the VAD-relay gate is NOT added.

### Code Quality Validation
- [ ] Edit anchored on the unique `_safe_abort` NOTE comment (unambiguous match).
- [ ] `set_phase("idle")` placed after `set_listening(False)`, adjacent + readable.
- [ ] Full paths in every bash command.

### Scope Boundary Validation
- [ ] Only `voice_typing/daemon.py` touched; no `recorder_host.py` (gate deferred), no `feedback.py`, no `test_daemon.py` (S2), no config/docs.
- [ ] `_handle_dead_host`/`_load_host`/`_unload` untouched (already correct / other tasks).

---

## Anti-Patterns to Avoid

- ❌ Don't anchor the edit on `set_listening(False)` alone — it's not unique (also in `run()`). Anchor on the `_safe_abort` NOTE comment (unique to `_disarm`).
- ❌ Don't add the VAD-relay gate in `recorder_host.py` — the item + bug-analysis say "only if observed"; the host doesn't know the listening state (invasive cross-layer change for an unobserved race). The next disarm resets phase.
- ❌ Don't add a committed pytest for phase-after-disarm — that is P1.M2.T1.S2 (S1 = code only; S1's proof is the throwaway inline check).
- ❌ Don't touch `_handle_dead_host`/`_load_host`/`_unload` — they already set phase correctly (`_handle_dead_host` is Issue 3 / P1.M2.T2).
- ❌ Don't add `set_phase("idle")` to `_arm()` — arming sets `listening` (phase advances to `listening`/`speaking` via VAD); `idle` is the disarmed state.
- ❌ Don't invent ruff/mypy commands — pytest only. Don't use bare python/pytest/uv (zsh aliases).

---

## Confidence Score

**10/10** for one-pass implementation success. The defect root cause is confirmed in `architecture/bug_analysis.md §Issue 2` and in the code; the fix is a single line whose exact insertion point is given with a unique text anchor (the `_safe_abort` NOTE comment, so the oldText match is unambiguous despite `set_listening(False)` appearing elsewhere); the no-regression claim is verified (no existing test asserts `fb.phases` after a disarm, so the additive `set_phase('idle')` keeps the suite green); the test-ownership boundary (S1=code, S2=test) is explicit; and the optional VAD-relay gate is correctly deferred ("only if observed"). The throwaway inline proof (L3) demonstrates the fix end-to-end via the test fakes without committing a test that would pre-empt S2.

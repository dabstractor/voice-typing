# PRP — P1.M1.T1.S1: Add `no_log_file=True` to `_FIXED_KWARGS`

## Goal

**Feature Goal**: Stop the production voice-typing daemon from creating an unbounded `realtimesst.log` file in its working directory (`$HOME` under systemd) by passing `no_log_file=True` to `AudioToTextRecorder`. This makes RealtimeSTT's logging flow exclusively through the daemon's own `logging → stderr → journald` path (PRD §4.2 / bugfix §2 Issue 1).

**Deliverable**: Two surgical edits + one new test, all verified against the installed library:
1. `voice_typing/daemon.py` — add one key `"no_log_file": True,` to the `_FIXED_KWARGS` dict.
2. `tests/test_daemon.py` — update the `expected` set in `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` to include `"no_log_file"` (lockstep — otherwise this exact-set test breaks).
3. `tests/test_daemon.py` — add a dedicated verification test asserting `kw["no_log_file"] is True`.

**Success Definition**: (a) `daemon._FIXED_KWARGS["no_log_file"] is True`; (b) `daemon.cfg_to_kwargs(cfg)["no_log_file"] is True` for a default config; (c) the existing `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` still PASSES (expected set updated); (d) the new verification test passes; (e) the full `tests/test_daemon.py` suite stays green. The runtime effect (no `realtimesst.log`) follows deterministically from RealtimeSTT's `_configure_logger` (verified — see Context).

## User Persona

Not applicable. This is an internal operational-robustness fix; no user-facing, config, or API surface changes (the bugfix contract §1 "DOCS: none").

## Why

- **Bugfix §2 Issue 1 (Major):** the live daemon (pid 1787) held an open `FileHandler` on `$HOME/realtimesst.log` growing ~620 B/s (~53 MB/day, unbounded, no rotation) because `no_log_file` was never set in production. The systemd unit has no `WorkingDirectory=`, so CWD = `$HOME`.
- **PRD §4.2 compliance:** the sole intended log path is `logging → stderr → journald`. RealtimeSTT's separate file log is an unintended side effect of a default (`no_log_file=False`).
- **Test/production parity:** the offline test suite already passes `no_log_file=True` (`tests/test_feed_audio.py:275`, marker `G-NOLOGFILE`). The production path simply needs to match.
- **One-line, low-risk fix:** the kwarg flows through the existing, tested `cfg_to_kwargs() → _construct() → _filter_kwargs_to_signature() → AudioToTextRecorder(**filtered)` pipeline; no new plumbing.

## What

Add `"no_log_file": True` to `_FIXED_KWARGS` in `voice_typing/daemon.py` so it is applied to every recorder construction (daemon + the kwargs path the tests use). Keep the existing exact-set unit test green by updating its `expected` set, and add a dedicated assertion test (the contract's prescribed verification: "assert 'no_log_file' is in daemon.cfg_to_kwargs(cfg) and equals True").

### Success Criteria

- [ ] `grep -n 'no_log_file' voice_typing/daemon.py` returns a match inside `_FIXED_KWARGS` set to `True`.
- [ ] `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` passes (its `expected` set now lists `"no_log_file"`).
- [ ] New test `test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log` passes: `"no_log_file" in kw` and `kw["no_log_file"] is True`.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` is fully green (no regressions).
- [ ] No other source/behavior change; daemon's own `_setup_logging` (stderr → journald) untouched.

## All Needed Context

### Context Completeness Check

_Pass._ All claims below are verified against the actual repo + the installed RealtimeSTT wheel (not assumed). Exact line numbers, the test pattern, the filter behavior, and the RealtimeSTT side-effect are all confirmed. A developer new to this codebase can apply the patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the defect definition (authoritative)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: §2 Issue 1 is the source of this fix — the verified live behavior (pid 1787,
       $HOME/realtimesst.log, ~620 B/s, no rotation), the reproduction steps, and the
       exact prescribed fix ("Add \"no_log_file\": True to _FIXED_KWARGS").
  critical: "The PRD §4.2 logging path (stderr → journald) is UNCHANGED. We are only
            suppressing RealtimeSTT's OWN FileHandler, not the daemon's logging."

# THE FIX SITE — the dict to edit
- file: voice_typing/daemon.py
  why: _FIXED_KWARGS (lines 96-108) is the single source of fixed recorder kwargs.
        cfg_to_kwargs() (line 133) does kwargs.update(_FIXED_KWARGS) at line 154, then
        _construct()/_filter_kwargs_to_signature() pass them to AudioToTextRecorder.
  pattern: "Each key is a bool/int/str literal with an inline trailing comment. Add the
            new key in the SAME style with a comment citing bugfix Issue 1 + PRD §4.2."
  gotcha: "_FIXED_KWARGS currently has 11 keys (contract said '10' — minor miscount;
            immaterial). Add no_log_file to make it 12."

# THE PIPELINE the kwarg flows through (verified — no edits needed here)
- file: voice_typing/daemon.py
  why: cfg_to_kwargs() (133-155) + _filter_kwargs_to_signature() (191-221). The filter
        keeps ONLY kwargs present in recorder_cls.__init__'s signature (strict-drop; the
        real AudioToTextRecorder has NO **kwargs — 84 params). no_log_file IS in that
        signature, so it survives filtering.
  critical: "Do NOT touch cfg_to_kwargs/_construct/_filter — the kwarg flows through
            unchanged. Confirmed: _filter keeps 'no_log_file' (it is a real param)."

# THE LOCKSTEP TEST — adding a key BREAKS this exact-set assertion unless updated
- file: tests/test_daemon.py
  why: test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set (line 98) asserts
        set(kw) == expected with an explicit expected set (lines ~105-110). Adding
        no_log_file to _FIXED_KWARGS makes cfg_to_kwargs() emit it -> this test FAILS
        with a set-symmetric-difference unless 'no_log_file' is added to `expected`.
  pattern: "expected is a set literal of kwarg names. Add \"no_log_file\", to it."
  critical: "This is the single most likely way to break the suite. Update it in the
            SAME edit as the daemon.py change, or the existing green test goes red."

# THE NEW VERIFICATION TEST — follow this sibling pattern exactly
- file: tests/test_daemon.py
  why: The cfg_to_kwargs tests (lines 113-165) show the canonical pattern: a `cfg`
        fixture + _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS) to force
        cuda_check onto a deterministic path, then assert on the returned dict.
  pattern: "def test_cfg_to_kwargs_<aspect>(cfg, monkeypatch): _cuda_resolve(...);
            kw = daemon.cfg_to_kwargs(cfg); assert ..."
  gotcha: "ALWAYS monkeypatch cuda_check via _cuda_resolve — bugfix Issue 4 shows the
           suite has a test-isolation/order-dependency problem when cuda_check resolution
           is left to probe the real GPU. Monkeypatching keeps this test hermetic."

# THE TEST THAT ALREADY SETS no_log_file (precedent / parity reference)
- file: tests/test_feed_audio.py
  why: Line 275 already passes kwargs['no_log_file']=True with marker G-NOLOGFILE
        ('keep the repo clean'). Confirms the kwarg is accepted + the intent is established.
  pattern: "Production must match what the test path already does."

# INSTALLED LIBRARY — confirms (a) kwarg exists, (b) it gates the FileHandler
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/audio_recorder.py
  why: __init__ signature contains 'no_log_file' (POSITIONAL_OR_KEYWORD, default False).
        No **kwargs (84 params) -> _filter_kwargs_to_signature's strict-drop path applies,
        so no_log_file is RETAINED.
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py
  why: _configure_logger (lines ~303-335) does: if not no_log_file:
        file_handler = logging.FileHandler('realtimesst.log') at DEBUG. With True, this
        block is SKIPPED -> no file. (console_handler StreamHandler -> stderr still added.)
  critical: "This is WHY the fix works at runtime. Verified verbatim in the wheel."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py          # _FIXED_KWARGS @ 96-108 (11 keys, no no_log_file) ← EDIT
└── tests/
    ├── test_daemon.py     # cfg_to_kwargs tests @ 98-197; exact-set test @ 98 ← EDIT + ADD test
    └── test_feed_audio.py # already sets no_log_file=True @ 275 (precedent, no change)
```

### Desired Codebase tree with files to be added/changed

```bash
voice_typing/daemon.py            # MODIFY: +1 key in _FIXED_KWARGS (no new files)
tests/test_daemon.py              # MODIFY: +1 line in expected set; +1 new test fn (no new files)
# No new files. No config/README/systemd changes. No dependency changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — LOCKSTEP TEST BREAKS IF FORGOTTEN. Adding "no_log_file" to _FIXED_KWARGS
# makes cfg_to_kwargs() emit it, which FAILS test_cfg_to_kwargs_keys_are_exactly_the_non_
# callback_set (it asserts set(kw) == an explicit expected set). You MUST add "no_log_file"
# to that test's `expected` set in the SAME change. (Verified: the test is currently green
# precisely because the key is absent.)

# CRITICAL #2 — no_log_file SURVIVES the signature filter. _filter_kwargs_to_signature()
# (daemon.py:191) keeps only kwargs in recorder_cls.__init__. The installed
# AudioToTextRecorder has NO **kwargs (84 explicit params) and DOES have 'no_log_file'
# (default False). So no_log_file is retained, not dropped. Do not 'fix' the filter.

# CRITICAL #3 — RealtimeSTT's FileHandler is gated by `not no_log_file`. core/initialization.py
# _configure_logger: `if not no_log_file: file_handler = logging.FileHandler('realtimesst.log')`.
# Setting True skips it entirely. The console StreamHandler (→ stderr → journald) is STILL
# added unconditionally, so RealtimeSTT messages remain visible in journald. Do NOT also
# try to redirect/silence RealtimeSTT's logger here — out of scope (that is Issue 2's concern).

# GOTCHA #4 — place the new key with a trailing comment, matching the dict's existing style.
# no_log_file is a LOGGING concern, not VAD/timing/silero, so the comment should say so
# (cites bugfix Issue 1) rather than pretend it's a §4.4 tuning value.

# GOTCHA #5 — the new verification test MUST monkeypatch cuda_check via _cuda_resolve(). The
# sibling value-tests do, and bugfix Issue 4 documents an order-dependent test-isolation
# failure when cuda_check resolution is left to probe the real GPU. Hermetic = monkeypatched.

# GOTCHA #6 — use FULL PATHS in all bash commands (this machine aliases python3→uv run,
# pip→alias, tmux→zsh plugin). Invoke .venv/bin/python and .venv/bin/pytest explicitly.

# GOTCHA #7 — DO NOT run the live/systemd daemon to verify (out of scope, slow, needs mic).
# The deterministic gate is the cfg_to_kwargs unit test + the verified RealtimeSTT
# _configure_logger logic. The contract explicitly prescribes the unit test as the check.
```

## Implementation Blueprint

### Data models and structure

None. No data models, types, or config schema change. This is a one-key addition to a `dict[str, Any]` literal plus two test edits.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/daemon.py — add no_log_file to _FIXED_KWARGS
  - FIND the _FIXED_KWARGS dict (lines 96-108). Its current tail is:
        "ensure_sentence_starting_uppercase": False,  # item correction (b); textproc owns cleanup
        "ensure_sentence_ends_with_period": False,
    }
  - EDIT: add ONE new key after "ensure_sentence_ends_with_period", before the closing brace:
        "ensure_sentence_ends_with_period": False,
        "no_log_file": True,  # bugfix Issue 1: suppress RealtimeSTT's unbounded realtimesst.log (PRD §4.2 sole path = stderr→journald)
    }
  - DO NOT change any other key. DO NOT edit cfg_to_kwargs / _construct / _filter — the kwarg
    flows through them unchanged (Task-2 of the existing pipeline). DO NOT touch _setup_logging.
  - VERIFY: grep -n 'no_log_file' voice_typing/daemon.py  → exactly ONE match, inside _FIXED_KWARGS.

Task 2: MODIFY tests/test_daemon.py — update the exact-set test's `expected`
  - FIND test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set (line 98). Its `expected`
    set literal contains 18 names ending with:
        ..., "ensure_sentence_starting_uppercase", "ensure_sentence_ends_with_period",
    }
  - EDIT: add "no_log_file", to that set (alphabetical position is not required by a set, but
    place it cleanly, e.g. after the ensure_sentence_* pair). This keeps the test green now that
    cfg_to_kwargs() emits the key.
  - WHY: this is the LOCKSTEP change — without it the existing green test fails (Gotcha #1).

Task 3: ADD tests/test_daemon.py — dedicated verification test (contract's prescribed check)
  - PLACE: among the cfg_to_kwargs tests, immediately after test_cfg_to_kwargs_fixed_values
    (around line 143), before test_cfg_to_kwargs_silero_correction.
  - ADD EXACTLY this function (follows the sibling pattern; monkeypatches cuda_check for hermeticity):
        def test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log(cfg, monkeypatch):
            """bugfix Issue 1: no_log_file=True is fixed so the production daemon never opens
            realtimesst.log (PRD §4.2 sole log path is stderr → journald; parity with the
            tests/test_feed_audio.py G-NOLOGFILE override)."""
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
            kw = daemon.cfg_to_kwargs(cfg)
            assert "no_log_file" in kw, sorted(kw)
            assert kw["no_log_file"] is True
  - The contract's success condition ("assert 'no_log_file' is in daemon.cfg_to_kwargs(cfg)
    and equals True") maps 1:1 to these two asserts.

Task 4: VALIDATE — run the Validation Loop below; fix until all green. No git commit unless the
  orchestrator directs it (it manages commits between subtasks). If asked, message:
  "P1.M1.T1.S1: add no_log_file=True to _FIXED_KWARGS (suppress realtimesst.log)".
```

### Implementation Patterns & Key Details

```python
# The ONLY source edit — a single dict key (daemon.py _FIXED_KWARGS). After the edit the dict
# is 12 keys; cfg_to_kwargs() returns it merged with the model/device/timing kwargs, e.g.:
#   >>> daemon.cfg_to_kwargs(cfg)["no_log_file"]
#   True
# Because the installed AudioToTextRecorder.__init__ accepts no_log_file (default False) and
# has no **kwargs, _filter_kwargs_to_signature() RETAINS it, so AudioToTextRecorder(**filtered)
# receives no_log_file=True. RealtimeSTT core/initialization.py _configure_logger then SKIPS:
#     if not no_log_file:                       # False -> block skipped
#         file_handler = logging.FileHandler('realtimesst.log')   # NOT created
# while still adding the console StreamHandler (stderr -> journald). Net: no file, logs intact.

# The ONLY two test edits:
#   (a) expected set gains "no_log_file"  -> keeps the exact-set test green.
#   (b) new test asserts presence + True   -> the contract's verification gate.
# No mocking of AudioToTextRecorder is needed for these tests: cfg_to_kwargs() is pure-dict;
# cuda_check.resolve_device_and_models is monkeypatched (via _cuda_resolve) for determinism.
```

### Integration Points

```yaml
PRODUCTION RUNTIME (daemon → AudioToTextRecorder):
  - With no_log_file=True now flowing in _FIXED_KWARGS, every recorder construction
    (VoiceTypingDaemon.build_recorder → _construct → AudioToTextRecorder) suppresses the
    FileHandler. The daemon's own _setup_logging (stderr StreamHandler → journald) is
    UNCHANGED and remains the sole log sink. systemd unit needs NO change.
  - The previously-growing $HOME/realtimesst.log stops receiving writes on next daemon
    restart. (Deleting the existing stale file is a one-off housekeeping step, NOT part of
    this code change; mention in the final docs task if desired.)

TEST RUNTIME (tests/test_feed_audio.py):
  - That suite ALREADY sets kwargs["no_log_file"]=True (line 275). With _FIXED_KWARGS now
    also setting it, the test's explicit override becomes redundant but harmless (dict.update
    overwrites with the same True value). DO NOT remove the test override — it is the
    intentional G-NOLOGFILE marker and also protects the test if _FIXED_KWARGS ever reverts.

NO INTERFACE CHANGES:
  - config.toml / VoiceTypingConfig: no new field (no_log_file is a fixed internal default,
    deliberately NOT user-tunable). status_snapshot() / voicectl output: unchanged.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the
> repo root `/home/dustin/projects/voice-typing`. These gates are pure/unit (no model load, no
> mic, no systemd) — cfg_to_kwargs is a dict-builder and cuda_check is monkeypatched in the tests.

### Level 1: The edit is in place (static check)

```bash
cd /home/dustin/projects/voice-typing
echo "--- no_log_file present in daemon.py _FIXED_KWARGS, set True, exactly once ---"
.venv/bin/python - <<'PY'
import voice_typing.daemon as d
assert "no_log_file" in d._FIXED_KWARGS, "_FIXED_KWARGS missing no_log_file"
assert d._FIXED_KWARGS["no_log_file"] is True, d._FIXED_KWARGS["no_log_file"]
print("L1 PASS: _FIXED_KWARGS['no_log_file'] is True; dict now has", len(d._FIXED_KWARGS), "keys")
PY
echo "--- only ONE no_log_file occurrence in daemon.py (inside _FIXED_KWARGS) ---"
test "$(grep -c 'no_log_file' voice_typing/daemon.py)" -eq 1 && echo "L1 PASS: single match" || echo "L1 FAIL: expected exactly 1 match"
# Expected: "L1 PASS: _FIXED_KWARGS['no_log_file'] is True; dict now has 12 keys" + "single match".
```

### Level 2: cfg_to_kwargs emits it (the contract's prescribed verification)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "cfg_to_kwargs_no_log_file or cfg_to_kwargs_keys_are_exactly or cfg_to_kwargs_fixed_values or filter_keeps"
# Expected: all selected tests PASS, including:
#   test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log PASSED  (the new test)
#   test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set PASSED  (lockstep update worked)
#   test_filter_keeps_kwargs_in_signature PASSED                     (no_log_file survives filter)
```

### Level 3: No regressions across the full daemon unit suite

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v
# Expected: ALL tests PASS (the suite was 73 collected / green before; remains green after).
# This confirms the _FIXED_KWARGS addition + expected-set update didn't break any other
# cfg_to_kwargs / _construct / recorder-wiring assertion.
```

### Level 4: Filter behavior confirmed against the INSTALLED recorder (defense-in-depth)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import inspect, voice_typing.daemon as d
from RealtimeSTT import AudioToTextRecorder
# no_log_file is a real param of the installed recorder -> _filter keeps it (Gotcha #2).
params = inspect.signature(AudioToTextRecorder.__init__).parameters
assert "no_log_file" in params
filtered = d._filter_kwargs_to_signature({"no_log_file": True, "bogus_xyz": 1}, AudioToTextRecorder)
assert filtered.get("no_log_file") is True, filtered
assert "bogus_xyz" not in filtered  # unknown kwargs ARE dropped (strict-drop path)
print("L4 PASS: no_log_file retained by filter; unknown kwargs dropped")
PY
# Expected: "L4 PASS: ...". (This is the same _filter logic the production construction uses.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `_FIXED_KWARGS["no_log_file"] is True`; exactly one `no_log_file` match in daemon.py.
- [ ] L2: new test `test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log` PASSES; exact-set + filter tests still PASS.
- [ ] L3: full `tests/test_daemon.py` suite green (no regressions).
- [ ] L4: `_filter_kwargs_to_signature` retains `no_log_file` against the installed recorder.

### Feature Validation
- [ ] `daemon.cfg_to_kwargs(VoiceTypingConfig())["no_log_file"] is True` (the contract's explicit success condition).
- [ ] `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` updated in lockstep and green.
- [ ] No `realtimesst.log` FileHandler is created by the production path (follows from RealtimeSTT `_configure_logger` `if not no_log_file:` skip — verified in the wheel).

### Code Quality Validation
- [ ] New `_FIXED_KWARGS` key has an inline trailing comment citing bugfix Issue 1 + PRD §4.2 (matches dict style).
- [ ] New test follows the sibling pattern (`cfg` fixture + `_cuda_resolve` monkeypatch + dict asserts).
- [ ] No edits to `cfg_to_kwargs` / `_construct` / `_filter_kwargs_to_signature` / `_setup_logging`.
- [ ] No bare `python`/`pip`/`pytest` used in commands (all `.venv/bin/...`).

### Scope Boundary Validation
- [ ] No config/README/systemd/install.sh changes; no new dependencies; no new files.
- [ ] `tests/test_feed_audio.py` left unchanged (its `no_log_file=True` override is intentionally retained).
- [ ] No attempt to also fix Issue 2 (mic retry) or Issue 3 (CUDA construction fallback) — those are sibling subtasks P1.M1.T2 / P1.M1.T3.

---

## Anti-Patterns to Avoid

- ❌ Don't add `no_log_file` to `_FIXED_KWARGS` without also updating the exact-set test's `expected` — it WILL go red (verified: that test is green precisely because the key is currently absent).
- ❌ Don't edit `cfg_to_kwargs` / `_filter_kwargs_to_signature` to "make room" for the kwarg — it already flows through and survives filtering; those functions are correct.
- ❌ Don't make `no_log_file` a `config.toml`/`VoiceTypingConfig` field — it is a fixed internal default, deliberately not user-tunable (the bug is that the file exists at all in production).
- ❌ Don't silence/redirect RealtimeSTT's logger or touch the daemon's `_setup_logging` — out of scope (stderr→journald stays; Issue 2 owns the retry-traceback concern).
- ❌ Don't remove the `no_log_file=True` override in `tests/test_feed_audio.py:275` — it's the intentional `G-NOLOGFILE` marker and a defensive backstop.
- ❌ Don't write the new test without monkeypatching `cuda_check` — bugfix Issue 4 documents order-dependent test isolation when the real GPU is probed.
- ❌ Don't run/restart the live systemd daemon as a "verification" — slow, needs the mic, and the deterministic gate is the unit test + the verified `_configure_logger` logic.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The change is a single dict key plus two small, pattern-matched test edits. Every claim in this PRP is verified against the actual repo and the installed RealtimeSTT wheel (signature presence, no-`**kwargs` strict-drop path, `_configure_logger` FileHandler gating, the exact-set test's current green state, the sibling test pattern, and the working pytest invocation). The only residual risk (−0.5) is forgetting the lockstep `expected`-set update — which this PRP calls out as CRITICAL #1 and verifies in L2.

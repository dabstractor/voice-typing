# PRP — P1.M2.T2.S2: Correct THREAD SAFETY docstrings to reflect actual serialization

## Goal

**Feature Goal**: Fix bugfix Issue 5's documentation half (PRD §4.2/§4.3, selected h3.4) by correcting **three docstring blocks** that make a FALSE concurrency claim — `"the daemon serializes on_final"` — to instead name the actual mechanism (`VoiceTypingDaemon._on_final_lock`, added by the sibling task P1.M2.T2.S1). The claim was historically false (RealtimeSTT fires each `on_final` in a fresh worker thread with no join), but S1 makes it **true** by adding the lock; THIS task (S2) corrects the prose so a maintainer reading the docstrings relies on the right invariant.

**Deliverable** (3 surgical docstring edits across 2 files + 2 textual regression-guard tests; no logic change, no new files):
1. `voice_typing/typing_backends.py` lines 19-23 — rewrite the THREAD SAFETY block of the module docstring to name `_on_final_lock`.
2. `voice_typing/feedback.py` lines 31-35 — rewrite the THREAD SAFETY block of the module docstring to name `_on_final_lock` (drop the false "serializes on_final anyway").
3. `voice_typing/feedback.py` lines 144-145 — clarify the snapshot() docstring's "no Lock" note to cross-reference `_on_final_lock` (keep the true lock-free snapshot design).
4. `tests/test_typing_backends.py` (append) + `tests/test_feedback.py` (append) — one Issue-5 regression-guard test each (textual: false phrase gone + `_on_final_lock` named).

**Success Definition**:
- (a) Both module docstrings name `VoiceTypingDaemon._on_final_lock` as the on_final serialization mechanism.
- (b) Neither module docstring contains the stale false phrases (`"serializes on_final calls"`, `"no locking is needed"`, `"serializes on_final anyway"`).
- (c) The snapshot() docstring still states it is lock-free (dict copy is atomic) AND cross-references `_on_final_lock`.
- (d) The 2 new regression-guard tests pass; the existing 57 tests in the two files still pass.
- (e) `.venv/bin/python -m pytest tests/test_typing_backends.py tests/test_feedback.py -q` → `59 passed`. `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- (f) No out-of-scope files: **no** edits to `voice_typing/daemon.py` / `tests/test_daemon.py` (S1 owns them), **no** `tests/test_voicectl.py` (P1.M2.T1.S2 owns it), **no** `plan/` files, **no** `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new dependencies.

## User Persona

Not applicable (internal documentation correction; item DOCS: "Mode A — these ARE documentation (module docstrings). The correction rides WITH the lock implementation work in S1 (same task). No separate docs subtask needed."). The beneficiary is the **maintainer** who reads the THREAD SAFETY docstrings to reason about the concurrency model and must not be misled by a false invariant.

## Why

- **The stated invariant was false.** `typing_backends.py:22` ("The daemon serializes on_final calls, so no locking is needed") and `feedback.py:35` ("The daemon serializes on_final anyway") claimed serialization that did not exist. The installed RealtimeSTT runs `transcribe_text()`'s heavy inference in the calling thread, then `threading.Thread(target=on_final, ...).start()` and returns immediately (no `.join()`), so `run()` re-enters `recorder.text()` while the previous `on_final` is still running (verified in the sibling research note `../P1M2T2S1/research/on_final_serialization_lock.md` §2).
- **S1 makes it true; S2 makes the docs match.** The two tasks are complementary and touch **disjoint files** (S1: `daemon.py` + `test_daemon.py`; S2: `typing_backends.py` + `feedback.py` + their tests) → no merge conflict. S1 adds the lock; S2 (this task) corrects the prose so the docstrings describe the mechanism that now actually exists.
- **Cheap, surgical, zero-risk.** Pure prose edits (no behavior change) plus two textual regression guards that prevent the Issue-5 false claim from creeping back. No runtime change, no config change, no API change.

## What

Rewrite the three docstring blocks (verbatim edits below) so they (1) name `VoiceTypingDaemon._on_final_lock`, (2) keep every TRUE statement that was there (backend statelessness; immutable `tmux_target`; reentrant per-call `subprocess.run`; CPython dict atomicity; atomic `os.replace`; Feedback's own internals need no lock), and (3) drop the false "serializes on_final [calls/anyway]" / "no locking is needed" sentences. Add one Issue-5 regression-guard test per module that asserts the docstring names `_on_final_lock` and no longer contains the stale false phrase.

### Success Criteria

- [ ] `voice_typing/typing_backends.py` module docstring THREAD SAFETY block names `_on_final_lock`, states "only one type_text call executes at a time", and contains NEITHER `"no locking is needed"` NOR `"serializes on_final calls"`.
- [ ] `voice_typing/feedback.py` module docstring THREAD SAFETY block names `_on_final_lock`, keeps the CPython-dict-atomic + atomic-os.replace facts, and does NOT contain `"serializes on_final anyway"`.
- [ ] `voice_typing/feedback.py` snapshot() docstring keeps a "lock-free" statement for `snapshot()` AND references `_on_final_lock`.
- [ ] `test_module_docstring_names_on_final_serialization_lock` in BOTH test files passes.
- [ ] `.venv/bin/python -m pytest tests/test_typing_backends.py tests/test_feedback.py -q` → `59 passed`.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] `git status --short` shows ONLY `voice_typing/typing_backends.py`, `voice_typing/feedback.py`, `tests/test_typing_backends.py`, `tests/test_feedback.py`.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the referenced research. The defect and the (sibling-verified) RealtimeSTT concurrency model are explained; the **exact** current text of all three edit sites is reproduced verbatim (including the `—` em dash at feedback.py:34) so the edits are copy-exact `oldText→newText`; the **exact** corrected text is given. The 2 test additions follow a verified repo convention (local imports inside test functions: `tests/test_config.py:141`, `tests/test_daemon.py:824`) and avoid the `feedback`-fixture name collision by using a local alias. Baseline (57 passed) verified live.

### Documentation & References

```yaml
# MUST READ — the exact current (FALSE) text + exact corrected text + sibling coordination + test
# strategy. ALL load-bearing.
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T2S2/research/docstring_concurrency_correction.md
  why: "§2 the EXACT current text + verified line numbers for all 3 edit sites (incl. the em dash at
        feedback.py:34). §3 the EXACT corrected wording with per-phrase rationale. §4 sibling
        coordination (S1 owns daemon.py/test_daemon.py; S2 owns these files — DISJOINT). §5 the test
        strategy: NO existing test pins the docstring wording (so edits can't break tests); local
        imports inside test funcs are repo convention; the `feedback` fixture-collision gotcha. §6
        the verified baseline (57 passed) + validation commands."
  section: "ALL. §2 (exact edits), §3 (corrected text), §4 (no conflicts), §5 (tests), §6 (validate)."

# MUST READ — the SIBLING task contract (complementary, DISJOINT files). S1 makes the claim TRUE.
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T2S1/PRP.md
  why: "S1 adds self._on_final_lock = threading.Lock() to VoiceTypingDaemon.__init__ and wraps the
        on_final body in 'with self._on_final_lock:'. S1 edits daemon.py + test_daemon.py ONLY.
        S2 (THIS task) corrects the docstrings in typing_backends.py + feedback.py to name that lock.
        Disjoint files -> no merge conflict. S1's research §2 verifies the RealtimeSTT no-join model."
  critical: "Do NOT edit daemon.py or test_daemon.py here (S1 owns them). Do NOT edit test_voicectl.py
             (P1.M2.T1.S2, parallel). The docstring edits are TEXT and do NOT require S1 to have landed
             first (they just name the lock)."

# MUST READ — the files being edited (verbatim source for the exact edits below)
- file: voice_typing/typing_backends.py
  why: "Module docstring THREAD SAFETY block = lines 19-23 (the Edit 1 site). The edits below
        reproduce this source VERBATIM, so apply them as exact edits. The block names _on_final_lock
        after S1; backends remain stateless/immutable/reentrant (those TRUE facts are preserved)."
  critical: "Edit ONLY the THREAD SAFETY block (19-23). Do NOT touch the backend classes, make_backend,
             or the NEVER EMIT ENTER note."

# MUST READ — the other edited source file (two edit sites here)
- file: voice_typing/feedback.py
  why: "Module docstring THREAD SAFETY block = lines 31-35 (Edit 2). snapshot() docstring = lines
        144-145 (Edit 3). Both reproduced VERBATIM below."
  critical: "Line 34 contains an EM DASH '—' (U+2014) before 'a torn write'. The edit tool matches
             exact bytes — reproduce '—' in oldText, NOT '-' or '->'. Edit ONLY those two docstring
             blocks; do NOT touch the Feedback class methods, _write, _notify, or the module header."

# MUST READ — the test files getting the 2 regression guards (append-only)
- file: tests/test_typing_backends.py
  why: "Append ONE test (test_module_docstring_names_on_final_serialization_lock) at EOF. Use a LOCAL
        'import voice_typing.typing_backends as ...' inside the test (repo convention: tests/
        test_config.py:141, test_daemon.py:824). No import-block edit."
  critical: "Do NOT add a module-level import (keeps the change append-only / minimal blast radius)."

- file: tests/test_feedback.py
  why: "Append ONE test at EOF (after test_snapshot_reflects_recorded_final). LOCAL import inside the
        test."
  critical: "`feedback` is a pytest FIXTURE here (line 90: def feedback(monkeypatch, tmp_path)). A
             module-level 'import voice_typing.feedback as feedback' would SHADOW it and break ~20
             tests. The LOCAL import inside the test function uses a distinct alias (feedback_module)
             and never escapes -> no collision. Do NOT bind a module global named `feedback`."

# THE DEFECT (Issue 5) — the PRD source for this fix
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2.3/§3.4 Issue 5 'Incorrect daemon serializes on_final docstring claim' — documents the two
        fix options (add a lock OR correct the docstrings). S1+S2 implement BOTH (lock in S1,
        docstrings here)."
  critical: "READ-ONLY. Never modify prd_snapshot.md (orchestrator-owned)."

# Background — the TRUE backend reentrancy (why the race was garble, not a crash)
- file: voice_typing/typing_backends.py
  why: "Each backend.type_text() spawns an INDEPENDENT subprocess.run per call (reentrant) -> concurrent
        calls interleave rather than crash. That is why the false docstring never caused visible
        breakage. The corrected docstring keeps this TRUE fact (stateless / immutable target)."
  critical: "Context only (already captured by Edit 1's newText)."
```

### Current Codebase tree (relevant slice — the only files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── typing_backends.py   # EDIT (Edit 1: module docstring THREAD SAFETY block, lines 19-23).
│   └── feedback.py          # EDIT (Edit 2: module docstring THREAD SAFETY, lines 31-35;
│                            #        Edit 3: snapshot() docstring, lines 144-145).
└── tests/
    ├── test_typing_backends.py  # EDIT (append 1 Issue-5 regression guard).
    ├── test_feedback.py         # EDIT (append 1 Issue-5 regression guard).
    ├── test_daemon.py           # OUT OF SCOPE (S1, parallel — adds _on_final_lock + 3 tests).
    └── test_voicectl.py         # OUT OF SCOPE (P1.M2.T1.S2, parallel).
# NOTHING ELSE. No new files. No pyproject.toml/uv.lock/.gitignore/PRD.md/tasks.json change.
```

### Desired Codebase tree (unchanged structure — edits are prose-only + 2 appended tests)

```bash
# Same tree as above. No files added/removed/renamed. Only 4 files' contents change:
#   voice_typing/typing_backends.py   — 5-line docstring block rewritten (Edit 1)
#   voice_typing/feedback.py          — 5-line docstring block rewritten (Edit 2) + 2-line note clarified (Edit 3)
#   tests/test_typing_backends.py     — +1 test function appended (Edit 4)
#   tests/test_feedback.py            — +1 test function appended (Edit 5)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — EM DASH exact match (feedback.py:34). The THREAD SAFETY block's oldText contains
#   'level — a torn write is impossible' with an EM DASH '—' (U+2014). The edit tool matches EXACT
#   bytes; typing '-' or '->' makes oldText not match and the edit FAILS. Copy the verbatim block.
#   (Research §7.1.) [Write-tech-docs note: this is a Python string-literal edit, not prose, so the
#   em dash is acceptable here.]

# CRITICAL #2 — `feedback` is a pytest FIXTURE in tests/test_feedback.py (line 90). A MODULE-LEVEL
#   'import voice_typing.feedback as feedback' would shadow it and break ~20 tests that take
#   `feedback` as a param. Solution: put the import INSIDE the new test function with a distinct
#   alias (feedback_module). The local import never escapes the function scope. (Research §5.)

# CRITICAL #3 — LOCAL imports inside test functions are REPO CONVENTION. Verified:
#   tests/test_config.py:141 'import tomllib', tests/test_control_socket.py:90 'import stat',
#   tests/test_daemon.py:824 'import threading', tests/test_feed_audio.py:66 'import numpy as np'.
#   So a local 'import voice_typing.X as X' inside the new test is idiomatic (no import-block edit,
#   minimal blast radius). There is NO [tool.ruff] config in pyproject.toml, so default ruff runs
#   (E4/E7/E9/F) — it does NOT flag local imports (PLC0415 is not in the default select set).

# CRITICAL #4 — NO test currently pins the docstring wording (verified: grep of `serializes on_final`
#   / `THREAD SAFETY` / `lock-free` across tests/ → no hits). So the docstring edits CANNOT break any
#   existing test. The 2 new guards are the FIRST tests to assert on this prose.

# CRITICAL #5 — DISJOINT from sibling S1. S1 edits voice_typing/daemon.py + tests/test_daemon.py.
#   Do NOT touch those. The docstring edits here are TEXT in typing_backends.py/feedback.py and do
#   NOT depend on S1 having landed (they just name the lock the docstring describes). (Research §4.)

# CRITICAL #6 — SCOPE = 2 source files + their 2 test files. Do NOT edit anything under plan/
#   (orchestrator-owned: PRD.md, tasks.json, prd_snapshot.md, architecture/*). The false-claim
#   references in plan/.../architecture/system_context.md:40,44 describe the PRE-fix analysis state
#   and are out of scope (changeset-level doc sync is P1.M3.T1).

# CRITICAL #7 — FULL TOOL PATHS (zsh aliases python/pip). Run pytest as
#   .venv/bin/python -m pytest ... (never bare 'pytest'/'python'). Optional ruff is at
#   /home/dustin/.local/bin/ruff (NOT in .venv). mypy is NOT installed — do NOT run it. (Research §6.)
```

## Implementation Blueprint

### Data models and structure

None. No data model, no new state, no new imports, no API change. Pure docstring prose edits + two appended test functions.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/typing_backends.py — module docstring THREAD SAFETY block (Edit 1)
  - REPLACE: the 5-line THREAD SAFETY block (current lines 19-23) with the corrected block that names
    VoiceTypingDaemon._on_final_lock.
  - EXACT oldText->newText: see "Edit 1" verbatim block below.
  - DO NOT: touch any backend class, make_backend, or the NEVER EMIT ENTER note.

Task 2: EDIT voice_typing/feedback.py — module docstring THREAD SAFETY block (Edit 2)
  - REPLACE: the 5-line THREAD SAFETY block (current lines 31-35) with the corrected block that names
    _on_final_lock (drops the false "serializes on_final anyway"; keeps the TRUE CPython-dict-atomic +
    atomic-os.replace + Feedback-needs-no-lock facts).
  - GOTCHA: reproduce the EM DASH '—' in oldText EXACTLY (Critical #1).
  - EXACT oldText->newText: see "Edit 2" verbatim block below.

Task 3: EDIT voice_typing/feedback.py — snapshot() docstring note (Edit 3)
  - REPLACE: the 2-line note (current lines 144-145) with a clarified version that KEEPS the lock-free
    snapshot design AND cross-references _on_final_lock.
  - EXACT oldText->newText: see "Edit 3" verbatim block below.

Task 4: EDIT tests/test_typing_backends.py — append Issue-5 regression guard (Edit 4)
  - APPEND: one test function (test_module_docstring_names_on_final_serialization_lock) at EOF.
  - LOCAL import inside the test (repo convention — Critical #3). No import-block edit.
  - EXACT newText: see "Edit 4" verbatim block below.

Task 5: EDIT tests/test_feedback.py — append Issue-5 regression guard (Edit 5)
  - APPEND: one test function at EOF (after test_snapshot_reflects_recorded_final).
  - LOCAL import with alias feedback_module (NOT `feedback` — fixture collision, Critical #2).
  - EXACT newText: see "Edit 5" verbatim block below.
```

### Edits — verbatim oldText → newText

#### Edit 1 — `voice_typing/typing_backends.py` module docstring THREAD SAFETY (lines 19-23)

`oldText` (current, verbatim):
```
THREAD SAFETY: type_text is safe to call from the daemon's on_final callback thread.
The backends hold NO shared mutable state (Wtype/Ydotool are stateless; TmuxBackend
stores one immutable tmux_target at construction), and subprocess.run spawns an
independent child process per call (reentrant). The daemon serializes on_final calls,
so no locking is needed.
```
`newText`:
```
THREAD SAFETY: type_text is called from the daemon's on_final callback thread. on_final
is serialized by the daemon's _on_final_lock (VoiceTypingDaemon), so only one type_text
call executes at a time. The backends are also individually safe: WtypeBackend/
YdotoolBackend are stateless and spawn an independent child subprocess per call;
TmuxBackend stores one immutable tmux_target at construction.
```

#### Edit 2 — `voice_typing/feedback.py` module docstring THREAD SAFETY (lines 31-35)

`oldText` (current, verbatim — NOTE the `—` em dash on the 4th line):
```
THREAD SAFETY: Feedback methods are called from RealtimeSTT callback threads (partial/
final) and the control-socket thread (set_listening). self._state dict updates are
individually atomic in CPython, and _write()'s tempfile+os.replace is atomic at the OS
level — a torn write is impossible. No Lock is needed (and would risk deadlock if a future
caller recurses). The daemon serializes on_final anyway.
```
`newText`:
```
THREAD SAFETY: Feedback methods are called from RealtimeSTT callback threads (partial/
final) and the control-socket thread (set_listening). on_final is serialized by the
daemon's _on_final_lock (VoiceTypingDaemon). Additionally, self._state dict updates are
individually atomic in CPython, and _write() uses tempfile + os.replace (atomic at OS
level) — a torn write is impossible. Feedback itself needs no Lock (it relies on these
atomic primitives; a lock here would risk deadlock if a future caller recurses).
```

#### Edit 3 — `voice_typing/feedback.py` snapshot() docstring note (lines 144-145)

`oldText` (current, verbatim):
```
        a concurrent reader never aliases the live dict the callback threads mutate. CPython dict
        copy is atomic; no Lock needed (Feedback is designed lock-free).
```
`newText`:
```
        a concurrent reader never aliases the live dict the callback threads mutate. CPython dict
        copy is atomic; no Lock is needed in Feedback itself (it is designed lock-free — on_final
        serialization is the daemon's _on_final_lock; see the THREAD SAFETY note above).
```

#### Edit 4 — `tests/test_typing_backends.py` append one Issue-5 regression guard (at EOF)

The file currently ends after `test_no_real_subprocess_run_dduring_tests` (line 329: `assert rec.argvs == [("wtype", "--", "x")]`). Append after the final line:

`newText` (the existing last line, then the appended block — `oldText` is the single last line `    assert rec.argvs == [("wtype", "--", "x")]`):
```
    assert rec.argvs == [("wtype", "--", "x")]


# ---------------------------------------------------------------------------
# Issue 5 (P1.M2.T2.S2): the THREAD SAFETY module-docstring must NOT restate the
# FALSE "The daemon serializes on_final calls, so no locking is needed" claim. It
# must name the actual serialization mechanism — VoiceTypingDaemon._on_final_lock,
# added by the sibling task P1.M2.T2.S1. Textual guard only (does not import daemon).
# ---------------------------------------------------------------------------


def test_module_docstring_names_on_final_serialization_lock():
    """Issue 5 regression guard: THREAD SAFETY note names _on_final_lock; stale false claim gone."""
    import voice_typing.typing_backends as typing_backends

    doc = typing_backends.__doc__ or ""
    assert "_on_final_lock" in doc, "THREAD SAFETY note must reference _on_final_lock"
    assert "no locking is needed" not in doc, "stale FALSE claim removed (Issue 5)"
    assert "serializes on_final calls" not in doc, "stale FALSE claim removed (Issue 5)"
```

#### Edit 5 — `tests/test_feedback.py` append one Issue-5 regression guard (at EOF)

The file currently ends after `test_snapshot_reflects_recorded_final` (line 381: `    assert fb.snapshot()["last_final"] == "a final utterance"`). Append after the final line:

`newText` (the existing last line, then the appended block — `oldText` is the single last line `    assert fb.snapshot()["last_final"] == "a final utterance"`):
```
    assert fb.snapshot()["last_final"] == "a final utterance"


# ---------------------------------------------------------------------------
# Issue 5 (P1.M2.T2.S2): the THREAD SAFETY module-docstring must NOT restate the
# FALSE "The daemon serializes on_final anyway" claim. It must name the actual
# serialization mechanism — VoiceTypingDaemon._on_final_lock (sibling P1.M2.T2.S1).
# Textual guard only. NOTE: `feedback` is a fixture here, so use a distinct alias.
# ---------------------------------------------------------------------------


def test_module_docstring_names_on_final_serialization_lock():
    """Issue 5 regression guard: THREAD SAFETY note names _on_final_lock; stale false claim gone."""
    import voice_typing.feedback as feedback_module  # NOT `feedback` — that's a pytest fixture here

    doc = feedback_module.__doc__ or ""
    assert "_on_final_lock" in doc, "THREAD SAFETY note must reference _on_final_lock"
    assert "serializes on_final anyway" not in doc, "stale FALSE claim removed (Issue 5)"
```

### Implementation Patterns & Key Details

```python
# The whole change is prose + 2 appended tests. Non-obvious details:

# (1) Preserve TRUE facts, drop only the FALSE claim. The backends ARE stateless; tmux_target IS
#     immutable; subprocess.run IS reentrant per call; CPython dict ops ARE atomic; os.replace IS
#     atomic; snapshot() needs no lock. Only "the daemon serializes on_final [calls/anyway]" and
#     "no locking is needed" were false. The corrected blocks keep the true sentences and replace
#     the false ones with the naming of _on_final_lock.

# (2) Em dash (feedback.py:34 + the new snapshot note). Use '—' (U+2014), never '-' or '->'.
#     This is a Python source edit (exact-byte match), not user-facing prose, so the em dash is fine.

# (3) Local import inside the test function (repo convention). Avoids editing the import block AND
#     sidesteps the `feedback` fixture-name collision in test_feedback.py:
def test_module_docstring_names_on_final_serialization_lock():
    import voice_typing.feedback as feedback_module   # alias != fixture name `feedback`
    doc = feedback_module.__doc__ or ""
    ...

# (4) The guards are TEXTUAL — they do NOT import voice_typing.daemon or check hasattr(daemon,
#     "_on_final_lock"). So they pass as soon as THIS task edits the docstrings, regardless of
#     whether sibling S1 has landed. (S1's own 3 tests in test_daemon.py verify the lock exists.)
```

### Integration Points

```yaml
# No database, routes, config, env-var, dependency, or public-API change. The change is purely
# docstring prose + 2 appended textual tests.

DOCUMENTATION (module docstrings — the deliverable):
  - voice_typing/typing_backends.py: "THREAD SAFETY block now names _on_final_lock"
  - voice_typing/feedback.py:        "THREAD SAFETY block now names _on_final_lock; snapshot() note cross-references it"

TESTS (Issue-5 regression guards):
  - tests/test_typing_backends.py: "+test_module_docstring_names_on_final_serialization_lock (append)"
  - tests/test_feedback.py:        "+test_module_docstring_names_on_final_serialization_lock (append)"

COORDINATION (sibling / parallel — DISJOINT files, no conflict):
  - S1 (P1.M2.T2.S1):  "adds _on_final_lock to daemon.py + tests in test_daemon.py (NOT touched here)"
  - P1.M2.T1.S2:       "owns tests/test_voicectl.py (NOT touched here)"
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing

# After each edit, confirm the false phrases are GONE and _on_final_lock is present:
grep -n "serializes on_final\|no locking is needed\|_on_final_lock" \
    voice_typing/typing_backends.py voice_typing/feedback.py
# Expected: typing_backends.py has ONE hit ('_on_final_lock'), NO 'serializes on_final calls',
#           NO 'no locking is needed'. feedback.py has TWO '_on_final_lock' hits (module + snapshot),
#           NO 'serializes on_final anyway'.

# Confirm both modules still import (no accidental docstring-quote breakage):
.venv/bin/python -c "import voice_typing.typing_backends, voice_typing.feedback; print('imports OK')"

# OPTIONAL lint — ruff is a uv tool at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed.
/home/dustin/.local/bin/ruff check voice_typing/typing_backends.py voice_typing/feedback.py \
    tests/test_typing_backends.py tests/test_feedback.py || true
# Expected: clean (prose-only source edits; the 2 new tests use the idiomatic local-import pattern).
```

### Level 2: Unit Tests (THE gate)

```bash
cd /home/dustin/projects/voice-typing

# The 2 new guards + all existing tests in BOTH files (baseline 57 -> 59 passed):
.venv/bin/python -m pytest tests/test_typing_backends.py tests/test_feedback.py -v
# Expected: 59 passed (incl. both test_module_docstring_names_on_final_serialization_lock).

# Just the two new guards (fast):
.venv/bin/python -m pytest tests/test_typing_backends.py tests/test_feedback.py \
    -v -k on_final_serialization_lock
# Expected: 2 passed.

# The documented fast suite (must stay green; S1 also adds 3 tests to test_daemon.py — those run too):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py needs a GPU + espeak assets; excluded.)

# Negative control (optional, proves the guards bite): temporarily revert Edit 1 so the old
# 'so no locking is needed.' line returns, re-run test_module_docstring_names_on_final_serialization_lock
# in test_typing_backends.py -> it FAILS on the 'no locking is needed' assertion. Restore Edit 1; passes.
```

### Level 3: Integration Testing (System Validation)

```bash
cd /home/dustin/projects/voice-typing

# Confirm the corrected docstrings are actually what Python sees at runtime (not just source text):
.venv/bin/python - <<'PY'
import voice_typing.typing_backends as tb, voice_typing.feedback as fb
tb_doc, fb_doc = tb.__doc__ or "", fb.__doc__ or ""
assert "_on_final_lock" in tb_doc, "typing_backends docstring missing _on_final_lock"
assert "no locking is needed" not in tb_doc
assert "serializes on_final calls" not in tb_doc
assert "_on_final_lock" in fb_doc, "feedback docstring missing _on_final_lock"
assert "serializes on_final anyway" not in fb_doc
# snapshot() docstring keeps a lock-free statement AND names _on_final_lock:
snap_doc = fb.Feedback.snapshot.__doc__ or ""
assert "lock-free" in snap_doc, "snapshot docstring must keep the lock-free design note"
assert "_on_final_lock" in snap_doc, "snapshot docstring must cross-reference _on_final_lock"
print("OK: both module docstrings + snapshot docstring corrected and internally consistent")
PY
# Expected: prints "OK: both module docstrings + snapshot docstring corrected and internally consistent", exit 0.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No live-daemon/GPU/audio path is exercised by a docstring change. The end-to-end guarantee that
# "two finals typed in quick succession never garble" is provided by sibling S1's lock (verified by
# S1's two-thread no-overlap test in tests/test_daemon.py) — NOT by this task. This task's job is
# solely that the docstrings describe that guarantee accurately, which Level 2 + Level 3 prove.

# Optional: confirm the broader plan docs that ALSO quoted the false claim are out of scope (do NOT
# edit them — they are orchestrator-owned plan/ artifacts describing the pre-fix analysis state):
grep -rn "serializes on_final anyway\|no locking is needed" plan/ | head   # informational only
```

## Final Validation Checklist

### Technical Validation

- [ ] `grep -n "serializes on_final\|no locking is needed" voice_typing/typing_backends.py voice_typing/feedback.py` → no hits in source.
- [ ] `grep -n "_on_final_lock" voice_typing/typing_backends.py` → 1 hit (module docstring).
- [ ] `grep -n "_on_final_lock" voice_typing/feedback.py` → 2 hits (module docstring + snapshot docstring).
- [ ] `.venv/bin/python -m pytest tests/test_typing_backends.py tests/test_feedback.py -q` → `59 passed`.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/typing_backends.py voice_typing/feedback.py tests/test_typing_backends.py tests/test_feedback.py` → clean.

### Feature Validation

- [ ] `typing_backends.py` THREAD SAFETY block names `_on_final_lock` and states "only one type_text call executes at a time".
- [ ] `feedback.py` THREAD SAFETY block names `_on_final_lock`, keeps the CPython-dict-atomic + atomic-os.replace facts, drops "serializes on_final anyway".
- [ ] `feedback.py` snapshot() docstring keeps "lock-free" AND references `_on_final_lock`.
- [ ] Both `test_module_docstring_names_on_final_serialization_lock` tests pass.
- [ ] (Optional) negative control: reverting Edit 1 makes the typing_backends guard fail; restoring it passes.

### Code Quality Validation

- [ ] Every TRUE statement from the original docstrings is preserved (stateless backends, immutable target, reentrant subprocess, atomic dict/os.replace, Feedback needs no internal lock).
- [ ] Only the FALSE serialization claim is replaced (not the surrounding true facts).
- [ ] Edits use exact-byte `oldText` (incl. the `—` em dash) — apply as one `edit` call each.
- [ ] Test additions are append-only with local imports (no import-block edit; repo convention).
- [ ] Only `voice_typing/typing_backends.py`, `voice_typing/feedback.py`, `tests/test_typing_backends.py`, `tests/test_feedback.py` modified (`git status --short`).

### Documentation & Deployment

- [ ] Module docstrings accurately describe the concurrency model (the deliverable).
- [ ] snapshot() docstring is internally consistent with the module THREAD SAFETY block.
- [ ] No new env vars, no config keys, no user-facing surface, no new dependencies.
- [ ] No `plan/` files edited (orchestrator-owned); changeset-level doc sync (P1.M3.T1) handles plan/ artifacts separately.

---

## Anti-Patterns to Avoid

- ❌ Don't delete the TRUE facts when removing the FALSE one — keep the backend-safety / atomic-dict / atomic-os.replace sentences; replace only the "serializes on_final" / "no locking is needed" phrasing.
- ❌ Don't type `-` or `->` where the source has `—` (em dash, U+2014) in feedback.py:34 — exact-byte match required (Gotcha #1).
- ❌ Don't add a module-level `import voice_typing.feedback as feedback` in test_feedback.py — it shadows the `feedback` fixture and breaks ~20 tests; use a LOCAL import with alias `feedback_module` inside the test (Gotcha #2/#3).
- ❌ Don't edit `voice_typing/daemon.py` / `tests/test_daemon.py` (sibling S1 owns them) or `tests/test_voicectl.py` (P1.M2.T1.S2 owns it) — disjoint files, no conflict.
- ❌ Don't edit anything under `plan/` (PRD.md, tasks.json, prd_snapshot.md, architecture/*) — orchestrator-owned; out of scope (Gotcha #6).
- ❌ Don't make the regression guard import `voice_typing.daemon` or assert `hasattr(daemon, "_on_final_lock")` — keep it TEXTUAL so it depends only on THIS task's edits, not on S1's landing (Gotcha — test independence).
- ❌ Don't run `mypy` — it's not installed; pytest is the authoritative gate (Gotcha #7).

---

## Confidence Score

**9/10** — one-pass success likelihood. This is a low-risk, surgical documentation correction: three exact-byte docstring rewrites (current text reproduced verbatim, including the em dash) plus two append-only textual regression guards that follow a verified repo convention (local imports). No logic change, no new imports at module scope, no dependency on sibling S1 landing first, no conflict with any parallel task (disjoint files). The only residual risk is an exact-byte mismatch on the em dash in Edit 2's oldText, which is explicitly flagged and the verbatim block is provided.

# Research — correct the THREAD SAFETY docstrings (P1.M2.T2.S2 / bugfix Issue 5)

This note pins the **exact** current (FALSE) docstring text, the **exact** corrected
text, the sibling-task coordination, and the deterministic test strategy. The PRP
(../PRP.md) references it as the single source of truth. All line numbers verified
live against the working tree on 2026-07-08.

## 1. The defect (bugfix Issue 5, PRD §4.2/§4.3 — see selected PRD h3.4)

Three docstring blocks claim "the daemon serializes on_final" — historically FALSE.
The installed RealtimeSTT fires each `on_final` callback in a **fresh worker thread
without joining** (`transcribe_text()` runs the heavy inference in the calling thread,
then `threading.Thread(target=on_final, ...).start()` and returns immediately), so two
finals can overlap. (Full verification of the threading model is in the SIBLING task's
research note: `../P1M2T2S1/research/on_final_serialization_lock.md` §2.)

The sibling task **P1.M2.T2.S1** ADDS `self._on_final_lock = threading.Lock()` to
`VoiceTypingDaemon` and wraps the `on_final` body in `with self._on_final_lock:` — which
makes the "serializes on_final" claim **TRUE**. THIS task (S2) corrects the docstrings
to (a) name the actual mechanism (`_on_final_lock`) and (b) drop the stale false phrasing.

## 2. Exact current (FALSE) text + verified line numbers

### 2.1 `voice_typing/typing_backends.py` lines 19-23 (module docstring THREAD SAFETY)
```
19: THREAD SAFETY: type_text is safe to call from the daemon's on_final callback thread.
20: The backends hold NO shared mutable state (Wtype/Ydotool are stateless; TmuxBackend
21: stores one immutable tmux_target at construction), and subprocess.run spawns an
22: independent child process per call (reentrant). The daemon serializes on_final calls,
23: so no locking is needed.
```
False phrases to remove: `"The daemon serializes on_final calls,"` + `"so no locking is needed."`

### 2.2 `voice_typing/feedback.py` lines 31-35 (module docstring THREAD SAFETY)
```
31: THREAD SAFETY: Feedback methods are called from RealtimeSTT callback threads (partial/
32: final) and the control-socket thread (set_listening). self._state dict updates are
33: individually atomic in CPython, and _write()'s tempfile+os.replace is atomic at the OS
34: level — a torn write is impossible. No Lock is needed (and would risk deadlock if a future
35: caller recurses). The daemon serializes on_final anyway.
```
False phrase to remove: `"The daemon serializes on_final anyway."`
NOTE: line 34 contains an EM DASH `—` (U+2014) before "a torn write". The `edit` tool matches
exact bytes — the `oldText` MUST reproduce it as `—`, NOT `-` or `->`.

### 2.3 `voice_typing/feedback.py` line 145 (snapshot() docstring, in context 144-145)
```
144:         a concurrent reader never aliases the live dict the callback threads mutate. CPython dict
145:         copy is atomic; no Lock needed (Feedback is designed lock-free).
```
This note is **still TRUE** for `snapshot()` itself (a `dict()` copy is atomic in CPython, so
`snapshot()` needs no lock). The item CONTRACT says **keep the lock-free snapshot design note**
but make it consistent with the corrected THREAD SAFETY block (cross-reference `_on_final_lock`
so a reader knows WHICH component provides on_final serialization). Line 145 does NOT contain
"serializes on_final anyway" — that phrase is at line 35.

## 3. Corrected wording (item CONTRACT; rationale per phrase)

### 3.1 typing_backends.py 19-23 →
```
THREAD SAFETY: type_text is called from the daemon's on_final callback thread. on_final
is serialized by the daemon's _on_final_lock (VoiceTypingDaemon), so only one type_text
call executes at a time. The backends are also individually safe: WtypeBackend/
YdotoolBackend are stateless and spawn an independent child subprocess per call;
TmuxBackend stores one immutable tmux_target at construction.
```
Why: names the actual lock; keeps the true backend-safety facts (stateless, immutable target,
reentrant subprocess). "only one type_text call executes at a time" is the precise invariant S1
guarantees.

### 3.2 feedback.py 31-35 →
```
THREAD SAFETY: Feedback methods are called from RealtimeSTT callback threads (partial/
final) and the control-socket thread (set_listening). on_final is serialized by the
daemon's _on_final_lock (VoiceTypingDaemon). Additionally, self._state dict updates are
individually atomic in CPython, and _write() uses tempfile + os.replace (atomic at OS
level) — a torn write is impossible. Feedback itself needs no Lock (it relies on these
atomic primitives; a lock here would risk deadlock if a future caller recurses).
```
Why: names `_on_final_lock`; KEEPS the true statement that Feedback's OWN internals need no lock
(atomic dict ops + atomic os.replace) — that fact was never false, only mis-attributed. Drops the
false "serializes on_final anyway" sentence. Em dash preserved for style consistency.

### 3.3 feedback.py 144-145 →
```
        a concurrent reader never aliases the live dict the callback threads mutate. CPython dict
        copy is atomic; no Lock is needed in Feedback itself (it is designed lock-free — on_final
        serialization is the daemon's _on_final_lock; see the THREAD SAFETY note above).
```
Why: keeps the true lock-free snapshot design note; disambiguates "no Lock" = "no Lock in Feedback
itself" and points at the daemon's `_on_final_lock` for on_final serialization.

## 4. Sibling-task coordination (CRITICAL — avoid conflicts)

- **S1 (P1.M2.T2.S1)** edits `voice_typing/daemon.py` + `tests/test_daemon.py`. **DO NOT touch
  those files here** — S1 owns them. (Verified: `daemon.py` does NOT yet have `_on_final_lock`
  today — S1 is in progress in parallel. Our docstring edits are TEXT in typing_backends.py /
  feedback.py, so they do NOT depend on S1 landing first.)
- **This task (S2)** edits `voice_typing/typing_backends.py` + `voice_typing/feedback.py` + adds
  regression-guard tests to `tests/test_typing_backends.py` + `tests/test_feedback.py`.
- **DISJOINT files** → no merge conflict with S1.
- **DO NOT** edit `tests/test_voicectl.py` (P1.M2.T1.S2, parallel).
- **DO NOT** edit any file under `plan/` (orchestrator-owned: PRD.md, tasks.json,
  prd_snapshot.md, architecture/*). The false-claim references in
  `plan/.../architecture/system_context.md:40,44` describe the PRE-fix analysis state and are
  out of scope for this item (changeset-level doc sync is P1.M3.T1).

## 5. Test strategy — textual Issue-5 regression guards

There are **NO existing tests** that pin the module-docstring wording (verified: `grep -rn`
of `serializes on_final` / `THREAD SAFETY` / `lock-free` across `tests/` → no hits). So the
docstring edits cannot break any current test.

Add ONE small regression-guard test per module (2 tests total) that asserts the docstring:
(a) names `_on_final_lock`, and (b) does NOT contain the stale false phrase. These are
**textual** — they do NOT import the daemon or check `hasattr(daemon, "_on_final_lock")`, so
they pass independently of whether S1 has landed (the docstring just needs to name the lock).

CONVENTION (verified live): this repo uses **local imports inside test functions** —
`tests/test_config.py:141 import tomllib`, `tests/test_control_socket.py:90 import stat`,
`tests/test_daemon.py:824 import threading`, `tests/test_feed_audio.py:66 import numpy as np`.
So use a local `import voice_typing.X as X` INSIDE each new test (no import-block edit, minimal
blast radius).

COLLISION GOTCHA: `feedback` is a **pytest fixture** in `tests/test_feedback.py` (line 90:
`def feedback(monkeypatch, tmp_path)`). A module-level `import voice_typing.feedback as feedback`
would shadow that fixture and break ~20 tests. The local-import approach sidesteps this entirely
(the local alias `feedback_module` never escapes the function). Use a distinct alias name.

## 6. Baseline + validation commands (verified)

```bash
cd /home/dustin/projects/voice-typing
# Baseline (BEFORE this task): both files green — 57 passed.
.venv/bin/python -m pytest tests/test_typing_backends.py tests/test_feedback.py -q
# After: same 57 + 2 new guards = 59 passed.
# Full fast suite (must stay green; S1 also adds 3 tests to test_daemon.py):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Optional lint (ruff is a uv tool at /home/dustin/.local/bin/ruff, NOT in .venv; mypy NOT installed):
/home/dustin/.local/bin/ruff check voice_typing/typing_backends.py voice_typing/feedback.py \
    tests/test_typing_backends.py tests/test_feedback.py || true
```
ALWAYS use `.venv/bin/python -m pytest ...` (zsh aliases bare `python`/`pytest`). Never run mypy
(not installed).

## 7. Gotchas summary

1. **EM DASH exact match** — feedback.py:34 uses `—` (U+2014). oldText must reproduce it byte-for-byte.
2. **feedback fixture name** — `feedback` is a fixture in test_feedback.py; use a local import alias
   (`feedback_module`) inside the test, never a module global named `feedback`.
3. **No S1 dependency at test time** — guards are textual; they pass once THIS task edits the
   docstrings, regardless of S1's state.
4. **Disjoint files** — never edit daemon.py / test_daemon.py (S1) or test_voicectl.py (P1.M2.T1.S2).
5. **Scope = 2 source files (+ their 2 test files for guards)** — do NOT touch plan/ docs or PRD.

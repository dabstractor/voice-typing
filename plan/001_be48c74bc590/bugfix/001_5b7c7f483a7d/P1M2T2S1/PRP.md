# PRP — P1.M2.T2.S1: Add `_on_final_lock` to serialize `on_final` callbacks

## Goal

**Feature Goal**: Eliminate the latent concurrent-typing race in `VoiceTypingDaemon.on_final()` (bugfix Issue 5, PRD §4.2/§4.3) by adding a **dedicated serialization lock** (`self._on_final_lock = threading.Lock()`) held across the entire clean → type → record → log body. RealtimeSTT fires each `on_final` callback in a **new worker thread without joining**, so a second finalized utterance can start its callback while a slow `type_text` subprocess is still running — letting two finals interleave or land out of order. Today the daemon has **no** serialization; the "daemon serializes on_final" docstrings in `typing_backends.py:22` / `feedback.py:35` are false. This task makes the invariant **true** (the sibling S2 task corrects the docstrings to match).

**Deliverable** (3 surgical edits across 2 files; no new files):
1. `voice_typing/daemon.py` — **Edit A**: add `self._on_final_lock = threading.Lock()` in `__init__` (after `self._lock`). **Edit B**: wrap the `on_final` body (after the gate check) in `with self._on_final_lock:`, indenting that block +4 spaces. The gate check + entry timestamp stay OUTSIDE the lock.
2. `tests/test_daemon.py` — **Edit C**: add 3 focused tests under a new `# --- on_final serialization ---` banner in the existing on_final section (structural lock check, a deterministic "lock held during type_text" probe, and a two-thread no-overlap behavioral test).

**Success Definition**:
- (a) `VoiceTypingDaemon` has `self._on_final_lock` that `is not self._lock` (a SEPARATE lock), initialized in `__init__`.
- (b) `on_final` holds `_on_final_lock` across `textproc.clean` → `backend.type_text` → `feedback.record_final` → `latency.finalize_utterance` → both `logger` calls; the `if not self._listening.is_set(): return` gate (and the `t_final_ready` stamp) stay OUTSIDE the lock.
- (c) The 3 new tests pass; the existing 9 on_final tests still pass (uncontended single-threaded calls are unaffected).
- (d) `.venv/bin/python -m pytest tests/test_daemon.py -v` → all green; `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- (e) No out-of-scope files: no edits to `typing_backends.py`/`feedback.py` (S2 owns the docstring correction), `_arm`/`_disarm`/`start`/`stop`/`toggle`/`run` unchanged, `test_voicectl.py` untouched (P1.M2.T1.S2, parallel, owns it), no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock` changes. No new dependencies.

## User Persona

Not applicable (internal behavioral change; no user-facing/config/API/doc surface — item DOCS: "none. The docstring correction happens in S2."). The beneficiaries are the **maintainer** (the concurrency invariant the docstrings already describe becomes actually true) and the **end user** (two finals typed in quick succession can no longer interleave/garble).

## Why

- **The stated invariant is false today.** `typing_backends.py:22` and `feedback.py:35` both claim "the daemon serializes on_final." It does not. The installed RealtimeSTT runs `transcribe_text()`'s heavy inference in the calling thread, then `threading.Thread(target=on_final, ...).start()` and returns immediately (no `.join()`), so `run()` re-enters `recorder.text()` while the previous `on_final` is still running. Two callbacks overlap.
- **Low-probability but real garbling.** The typing backends spawn an independent child subprocess per call (reentrant → no crash), but if a second final's `type_text` fires before the first's subprocess finishes, keystrokes can interleave or land out of order. GPU transcription ≫ wtype latency makes this rare, but "rare garbling" in a typing daemon is exactly the kind of bug that erodes trust and is impossible to reproduce on demand.
- **Cheap, surgical, proven fix.** One uncontended `threading.Lock` held across the body. Single-threaded callers (all existing tests, and the common case where transcription is slower than typing) pay only an instant acquire/release. The lock is SEPARATE from `self._lock` so it cannot stall `voicectl toggle`/`start`/`stop` (which take `self._lock` via `_arm`/`_disarm`) and cannot deadlock (no lock-ordering cycle — see Known Gotcha #4).
- **Defense-in-depth with S2.** S2 (P1.M2.T2.S2) corrects the docstrings. This task (S1) does the work that lets S2 leave the wording essentially as-is (the claim becomes true). The two tasks are complementary and touch disjoint files — no merge conflict.

## What

Make `on_final` actually serialize by holding a dedicated lock across its typed-output body. Concretely: in `__init__`, add `self._on_final_lock = threading.Lock()` right after `self._lock = threading.Lock()` (lines 413-414), with a comment explaining why it is separate. In `on_final`, leave the entry-stamp + gate check outside the lock and wrap everything from `cleaned = textproc.clean(...)` through the final `logger.debug(...)` in `with self._on_final_lock:`. Add three tests proving the lock exists, is separate from `_lock`, is held during `type_text`, and serializes two concurrent callbacks.

### Success Criteria

- [ ] `VoiceTypingDaemon.__init__` sets `self._on_final_lock = threading.Lock()` (separate object from `self._lock`).
- [ ] `on_final`'s gate check (`if not self._listening.is_set(): return`) and `t_final_ready` stamp are OUTSIDE the lock; `textproc.clean` + its `if not cleaned: return`, `backend.type_text` (+ its try/except), `feedback.record_final`, `latency.finalize_utterance`, and BOTH `logger.info`/`logger.debug` calls are INSIDE `with self._on_final_lock:`.
- [ ] `test_on_final_has_dedicated_serialization_lock` passes (lock exists, `is not _lock`, working mutex).
- [ ] `test_on_final_lock_held_across_type_text` passes (deterministic: `locked()` True during a blocked `type_text`, False after).
- [ ] `test_on_final_serializes_two_concurrent_callbacks` passes (two concurrent `on_final` → `max_in_flight == 1`, both texts typed).
- [ ] The existing 9 on_final tests still pass (no behavioral change for uncontended calls).
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` → all green.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] `git status --short` shows ONLY `voice_typing/daemon.py` and `tests/test_daemon.py` modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the referenced research. The defect and the verified RealtimeSTT concurrency model are explained; the **exact** current `__init__` lock-init lines (413-415) and the **full** current `on_final` body (490-528) are reproduced verbatim so the two `daemon.py` edits are copy-exact `oldText→newText` (including the `→`/`—` Unicode in existing comments). The 3 verbatim tests reuse existing fixtures (`_make_daemon`, `_wait_for`) and already-imported module globals (`threading`, `time as _time` at lines 334-335) — no new imports. The deadlock/latency analysis for using a SEPARATE lock is in the research note §5 and Gotcha #4. Baseline (9 on_final tests pass) verified live.

### Documentation & References

```yaml
# MUST READ — the defect + verified concurrency model + exact edit sites (load-bearing)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T2S1/research/on_final_serialization_lock.md
  why: "§2 the verified RealtimeSTT threading model (transcribe_text fires on_final in a new
        thread, no join). §4 the EXACT current line numbers + full on_final source. §5 WHY a
        separate lock (deadlock/latency analysis — on_final never takes _lock; _arm/_disarm never
        call on_final -> no lock-ordering cycle). §7 the test fixtures + the import fact (threading
        + time as _time are module-level at lines 334-335 -> NO new import; use _time.sleep). §8 the
        3-test strategy incl. the deterministic locked()-during-type_text probe."
  section: "ALL load-bearing. §4 (exact edits), §5 (separate-lock rationale), §7 (fixtures/imports),
            §8 (tests)."

# MUST READ — the file being edited (daemon.py): __init__ (401-441) + on_final (490-528)
- file: voice_typing/daemon.py
  why: "__init__ sets self._lock = threading.Lock() at line 413 — Edit A inserts _on_final_lock right
        after it. on_final (490-528) is the body Edit B wraps. run() (438-455) calls
        self._recorder.text(self.on_final) — unchanged. _arm/_disarm (530+) take self._lock —
        unchanged. The edits below reproduce this source VERBATIM, so apply them as exact edits."
  critical: "Reproduce the Unicode in existing comments (→ in the docstring/gate, — in comments)
             EXACTLY in Edit B's oldText or the match fails. Do NOT touch _arm/_disarm/start/stop/
             toggle/run/request_shutdown/shutdown. threading is ALREADY imported (line 75)."

# MUST READ — the test file: fixtures to reuse + the insertion site
- file: tests/test_daemon.py
  why: "_make_daemon(*, recorder, backend, cfg) -> (d, fb, rec, be) accepts a custom backend= (the
        returned be IS the injected backend). _FakeBackend.typed records calls. _wait_for(predicate,
        timeout, interval) polls. d.start() arms the mic so the gate passes. The on_final section
        runs lines ~429-469; Edit C inserts the 3 tests AFTER test_on_final_typing_raises_... and
        BEFORE the '# --- start / stop / toggle ---' divider."
  critical: "threading + 'time as _time' are ALREADY imported at module level (lines 334-335); _wait_for
             is at line 402. Add NO new import. Use _time.sleep (NOT time.sleep). The 3 new tests use
             custom inline backend stubs (not _FakeBackend) — that is fine; _make_daemon accepts any
             duck-typed backend. Do NOT edit any existing test."

# MUST READ — the sibling task contract (complementary, DISJOINT files — no conflict)
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T2S2/PRP.md
  why: "S2 corrects the FALSE docstrings in typing_backends.py:22 and feedback.py:35 ('daemon
        serializes on_final'). S1 (THIS task) makes the claim TRUE so S2 can leave the wording. The
        two tasks touch DIFFERENT files (S1: daemon.py + test_daemon.py; S2: typing_backends.py +
        feedback.py + their tests) -> no merge conflict."
  critical: "Do NOT edit typing_backends.py or feedback.py here (S2 owns them). Do NOT edit
             test_voicectl.py (P1.M2.T1.S2, parallel, owns it). Do NOT edit test_typing_backends.py
             or test_feedback.py (S2 may touch those)."

# Background — the typing-backend reentrancy that makes this a garble (not a crash) today
- file: voice_typing/typing_backends.py
  why: "Each backend.type_text() spawns an INDEPENDENT subprocess.run per call (reentrant) — so
        concurrent calls do not crash, they just interleave. That is why the race is latent (rare
        garble, not an exception). Line 22's 'no locking needed' comment is the FALSE claim S2 fixes."
  critical: "OUT OF SCOPE here. Read-only context confirming the failure mode is garble, not crash."

# THE DEFECT (Issue 5) — the PRD source for this fix
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2.3/§3.4 Issue 5 'Incorrect daemon serializes on_final docstring claim' — documents the
        latent race and the two fix options (add a lock, OR correct the docstrings). This task +
        S2 implement BOTH options together (lock here, docstrings in S2)."
  critical: "The item CONTRACT prescribes the LOCK option verbatim (separate lock; gate outside;
             clean/type/record/log inside). Implement exactly that — do not pick the 'accept the
             caveat' branch."
```

### Current Codebase tree (relevant slice — the only 2 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py            # EDIT (Edit A: __init__ +lock; Edit B: on_final wrap body).
│   ├── typing_backends.py   # OUT OF SCOPE (S2). 'serializes on_final' docstring is FALSE until S2.
│   └── feedback.py          # OUT OF SCOPE (S2). Same false docstring.
└── tests/
    ├── test_daemon.py       # EDIT (Edit C: +3 on_final serialization tests in the on_final section).
    ├── test_voicectl.py     # OUT OF SCOPE (P1.M2.T1.S2, parallel).
    ├── test_typing_backends.py  # OUT OF SCOPE (S2 may touch).
    └── test_feedback.py     # OUT OF SCOPE (S2 may touch).
# NOTHING ELSE. No new files. No pyproject.toml/uv.lock/.gitignore/PRD.md/tasks.json change.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — SEPARATE lock from self._lock (item CONTRACT). self._lock guards toggle/start/stop
#   (via _arm/_disarm, which run UNDER self._lock). If on_final took self._lock, a slow type_text
#   subprocess would BLOCK voicectl toggle for the typing duration — coupling unrelated latencies.
#   _on_final_lock is dedicated so on_final latency never affects control-plane latency.
#   (Research §5.)

# CRITICAL #2 — NO DEADLOCK. The lock is safe precisely because of the SEPARATION: on_final (in a
#   RealtimeSTT worker thread) NEVER acquires self._lock, and _arm/_disarm (under self._lock) NEVER
#   call on_final. So there is no lock-ordering cycle. The calls made INSIDE _on_final_lock
#   (feedback.record_final, latency.finalize_utterance) each take their OWN leaf lock, acquire+release
#   it entirely within the call, and never reach back for _on_final_lock or self._lock — verified by
#   grep. Do not "simplify" by reusing self._lock; that reintroduces both the latency coupling AND a
#   potential ordering deadlock. (Research §5.)

# CRITICAL #3 — GATE STAYS OUTSIDE THE LOCK. The early 'if not self._listening.is_set(): return' is a
#   READ-ONLY race guard (an utterance may finalize right after stop). Keep it (and the t_final_ready
#   entry stamp) BEFORE 'with self._on_final_lock:'. Only the clean→type→record→log body is inside.
#   Putting the gate inside the lock would serialize the cheap gate check too (harmless but pointless
#   and slightly delays a just-stopped callback). (Item CONTRACT; Research §4.2.)

# CRITICAL #4 — REPRODUCE UNICODE IN Edit B's oldText. The existing on_final source uses → (in the
#   docstring "Gate → clean" and the gate comment) and — (em dash in comments). The edit tool matches
#   EXACT bytes; if you type '->' or '-' instead, oldText will not match and the edit fails. Copy the
#   verbatim block from the Implementation Blueprint. (Research §4.2.)

# CRITICAL #5 — UNCONTENDED CALLS UNCHANGED. All existing tests call d.on_final(...) synchronously
#   from the main thread. An uncontended 'with lock:' acquires instantly and releases on exit — ZERO
#   observable behavior change. So the 9 existing on_final tests stay green with no edits. (Verified
#   baseline: 9 passed.) Do not modify any existing test.

# CRITICAL #6 — TEST IMPORTS: NO NEW IMPORT. tests/test_daemon.py ALREADY has 'import threading'
#   (line 334) and 'import time as _time' (line 335) at module level, plus _wait_for (line 402). The
#   new tests reuse them. Use _time.sleep(...) — NOT time.sleep — because of the 'as _time' alias.
#   (Research §7.) Line 583 documents this exact reuse convention.

# CRITICAL #7 — FULL TOOL PATHS (zsh aliases python/pip/tmux). Run pytest as
#   .venv/bin/python -m pytest ... (never bare 'pytest'/'python'). Optional ruff is at
#   /home/dustin/.local/bin/ruff (NOT in .venv). mypy is NOT installed — do NOT run it. (Research §9.)
```

## Implementation Blueprint

### Data models and structure

No data-model change. The only new state is one instance attribute: `self._on_final_lock: threading.Lock` on `VoiceTypingDaemon`. It is a non-reentrant mutex (`threading.Lock()`, NOT `RLock`) — correct because a single `on_final` call acquires it exactly once. `on_final`'s signature `on_final(self, text: str) -> None` is unchanged.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — __init__ (Edit A)
  - ADD: self._on_final_lock = threading.Lock() immediately AFTER 'self._lock = threading.Lock()'
    (current line 413), with a 4-line comment explaining: serializes on_final; SEPARATE from _lock
    so slow type_text cannot stall toggle/start/stop (which take _lock via _arm/_disarm); no
    lock-ordering deadlock (on_final never takes _lock).
  - EXACT oldText→newText: see "Edit A" verbatim block below.
  - DO NOT: reorder existing init lines, touch _listening/_shutdown, or import threading (already at
    line 75).

Task 2: EDIT voice_typing/daemon.py — on_final body (Edit B)
  - WRAP: the block from 'cleaned = textproc.clean(...)' (line 495) through the end of the
    logger.debug(...) call (line 528) in 'with self._on_final_lock:', indenting every line of that
    block +4 spaces. Leave t_final_ready (492) + the gate check (493-494) OUTSIDE the lock.
  - EXACT oldText→newText: see "Edit B" verbatim block below (oldText is the full current body after
    the gate; newText prepends the 'with' + comment and re-indents the whole block).
  - GOTCHA: reproduce the → and — Unicode in oldText EXACTLY (Critical #4).
  - VERIFY after: 'grep -n "_on_final_lock" voice_typing/daemon.py' shows exactly 2 hits (init + with).

Task 3: EDIT tests/test_daemon.py — add 3 tests (Edit C)
  - ADD: a '# --- on_final serialization (P1.M2.T2.S1 / bugfix Issue 5) ---' banner + 3 tests,
    inserted AFTER 'test_on_final_typing_raises_is_caught_and_record_still_happens' (its last assert
    is 'assert fb.finals == ["boom"]   # record_final STILL called ...') and BEFORE the
    '# --- start / stop / toggle ---' divider.
  - TESTS (verbatim below): test_on_final_has_dedicated_serialization_lock (structural),
    test_on_final_lock_held_across_type_text (deterministic probe), test_on_final_serializes_two_
    concurrent_callbacks (behavioral).
  - REUSE: _make_daemon(backend=<inline stub>), d.start(), _wait_for, threading, _time. NO new import.
  - EXACT oldText→newText: see "Edit C" verbatim block below.
```

### Edits — verbatim oldText → newText

#### Edit A — `voice_typing/daemon.py` `__init__` (add the lock)

`oldText` (current lines 413-414):
```
        self._lock = threading.Lock()
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
```
`newText`:
```
        self._lock = threading.Lock()
        # Serializes on_final callbacks (bugfix Issue 5 / P1.M2.T2.S1). RealtimeSTT fires each
        # on_final in a NEW thread without joining, so a second final can arrive while a slow
        # type_text is still running. SEPARATE from _lock: a slow type_text must not stall
        # toggle/start/stop (which take _lock via _arm/_disarm), and on_final never takes _lock
        # (nor do _arm/_disarm call on_final) -> no lock-ordering deadlock. Held across clean→
        # type→record→log; the gate check stays OUTSIDE (read-only race guard).
        self._on_final_lock = threading.Lock()
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
```

#### Edit B — `voice_typing/daemon.py` `on_final` (wrap the body)

`oldText` (current lines 495-528 — the body AFTER the gate, reproduced **verbatim including `→`/`—`**):
```
        cleaned = textproc.clean(text, self._cfg.filter)
        if not cleaned:                        # rejected: blocklist hallucination / below min_chars
            return
        payload = cleaned + (" " if self._cfg.output.append_space else "")
        try:
            self._backend.type_text(payload)   # may raise → caught so the on_final thread survives
        except Exception:
            logger.exception("typing backend failed for final %r", cleaned)
        t_typed = time.monotonic()             # right after type_text (PRD §4.2 latency logging)
        self._feedback.record_final(cleaned)   # recognition is final regardless of typing success
        record = self._latency.finalize_utterance(
            text=cleaned, t_final_ready=t_final_ready, t_typed=t_typed
        )
        # Structured per-utterance latency line — T1 (test_feed_audio) parses this. Stable prefix +
        # key=value tokens; text=<repr> is LAST (repr may contain spaces). *_ms are 'n/a' when no
        # on_vad_stop preceded this final (t_speech_end is None). (PRD §6 latency targets.)
        logger.info(
            "%s event=%s speech_end_to_final_ms=%s final_to_typed_ms=%s total_ms=%s "
            "partials=%d ts_epoch=%.3f text=%r",
            _LATENCY_LOG_PREFIX,
            record["event"],
            record["speech_end_to_final_ms"] if record["speech_end_to_final_ms"] is not None else "n/a",
            record["final_to_typed_ms"],
            record["total_ms"] if record["total_ms"] is not None else "n/a",
            record["partials"],
            record["ts"],
            cleaned,
        )
        logger.debug(
            "voice-typing latency debug: t_speech_end=%s t_final_ready=%.4f t_typed=%.4f",
            record["t_speech_end"] if record["t_speech_end"] is not None else "n/a",
            record["t_final_ready"],
            record["t_typed"],
        )
```

`newText` (same body, wrapped in `with self._on_final_lock:` and indented +4, with a comment; everything from `cleaned = ...` onward is now at 12-space indent inside the `with`):
```
        # Serialize clean→type→record→log across concurrent on_final worker threads (bugfix Issue 5 /
        # P1.M2.T2.S1). The gate above stays OUTSIDE the lock (read-only race guard); the lock is
        # SEPARATE from _lock (see __init__) so this never stalls toggle/start/stop and never deadlocks.
        with self._on_final_lock:
            cleaned = textproc.clean(text, self._cfg.filter)
            if not cleaned:                    # rejected: blocklist hallucination / below min_chars
                return
            payload = cleaned + (" " if self._cfg.output.append_space else "")
            try:
                self._backend.type_text(payload)   # may raise → caught so the on_final thread survives
            except Exception:
                logger.exception("typing backend failed for final %r", cleaned)
            t_typed = time.monotonic()             # right after type_text (PRD §4.2 latency logging)
            self._feedback.record_final(cleaned)   # recognition is final regardless of typing success
            record = self._latency.finalize_utterance(
                text=cleaned, t_final_ready=t_final_ready, t_typed=t_typed
            )
            # Structured per-utterance latency line — T1 (test_feed_audio) parses this. Stable prefix +
            # key=value tokens; text=<repr> is LAST (repr may contain spaces). *_ms are 'n/a' when no
            # on_vad_stop preceded this final (t_speech_end is None). (PRD §6 latency targets.)
            logger.info(
                "%s event=%s speech_end_to_final_ms=%s final_to_typed_ms=%s total_ms=%s "
                "partials=%d ts_epoch=%.3f text=%r",
                _LATENCY_LOG_PREFIX,
                record["event"],
                record["speech_end_to_final_ms"] if record["speech_end_to_final_ms"] is not None else "n/a",
                record["final_to_typed_ms"],
                record["total_ms"] if record["total_ms"] is not None else "n/a",
                record["partials"],
                record["ts"],
                cleaned,
            )
            logger.debug(
                "voice-typing latency debug: t_speech_end=%s t_final_ready=%.4f t_typed=%.4f",
                record["t_speech_end"] if record["t_speech_end"] is not None else "n/a",
                record["t_final_ready"],
                record["t_typed"],
            )
```

> The implementer applies Edit B as ONE `edit` call (oldText/newText above). The structural change is purely: prepend the comment + `with self._on_final_lock:`, then indent the existing 34 lines by 4 spaces. No logic change. (`cleaned`'s own `if not cleaned: return` now returns from inside the `with` — correct; the lock releases on return.)

#### Edit C — `tests/test_daemon.py` (insert 3 tests in the on_final section)

`oldText` (the tail of the last existing on_final test + the next section's divider):
```
    assert be.typed == []          # nothing typed (it raised)
    assert fb.finals == ["boom"]   # record_final STILL called (recognition is final regardless)


# --- start / stop / toggle ---
```
`newText`:
```
    assert be.typed == []          # nothing typed (it raised)
    assert fb.finals == ["boom"]   # record_final STILL called (recognition is final regardless)


# --- on_final serialization (P1.M2.T2.S1 / bugfix Issue 5) ---
# RealtimeSTT fires on_final in a NEW thread per final without joining, so two finals can overlap.
# _on_final_lock serializes the clean->type->record->log body. threading + time (as _time) are
# module-level (lines 334-335); _wait_for is at line 402. No new import needed.


def test_on_final_has_dedicated_serialization_lock():
    """The lock exists, is a SEPARATE object from self._lock, and is a working mutex."""
    d, _, _, _ = _make_daemon()
    assert hasattr(d, "_on_final_lock"), "daemon must expose self._on_final_lock"
    assert d._on_final_lock is not d._lock, "must be a SEPARATE lock from self._lock"
    # It is a real, working mutex: acquires uncontended; reports locked().
    assert d._on_final_lock.acquire(blocking=False) is True
    assert d._on_final_lock.locked() is True
    d._on_final_lock.release()
    assert d._on_final_lock.locked() is False


def test_on_final_lock_held_across_type_text():
    """The lock is held for the whole clean->type->record->log body, so a second on_final cannot
    interleave its type_text. Deterministic: while a worker is blocked INSIDE type_text (holding the
    lock), the lock is locked(); once on_final returns, it is not. No fixed sleeps."""
    started = threading.Event()
    release = threading.Event()

    class _BlockingBackend:
        def __init__(self):
            self.typed = []

        def type_text(self, text):
            started.set()                 # signal: we are inside type_text
            release.wait(timeout=2.0)     # hold so the probe can observe the lock being held
            self.typed.append(text)

    probe = _BlockingBackend()
    d, _, _, _ = _make_daemon(backend=probe)
    d.start()
    worker = threading.Thread(target=d.on_final, args=("hello world",))
    worker.start()
    assert _wait_for(started.is_set), "type_text never started (worker stalled)"
    assert d._on_final_lock.locked() is True, "lock must be held while type_text runs"
    release.set()                        # let the worker finish
    worker.join(timeout=2.0)
    assert not worker.is_alive(), "on_final worker did not finish"
    assert d._on_final_lock.locked() is False, "lock must be released once on_final returns"
    assert probe.typed == ["hello world "]   # append_space default True


def test_on_final_serializes_two_concurrent_callbacks():
    """Two on_final callbacks fired concurrently run strictly sequentially: type_text calls never
    overlap (max in-flight == 1) and both texts are typed. In a no-lock (buggy) build the second
    worker enters type_text during the gate window and max_in_flight becomes 2 -> this asserts fail."""
    gate = threading.Event()

    class _ConcurrencyBackend:
        def __init__(self):
            self.typed = []
            self.max_in_flight = 0
            self._in_flight = 0
            self._guard = threading.Lock()

        def type_text(self, text):
            with self._guard:
                self._in_flight += 1
                if self._in_flight > self.max_in_flight:
                    self.max_in_flight = self._in_flight
            gate.wait(timeout=2.0)        # a second call WOULD overlap here if on_final were unserialized
            with self._guard:
                self._in_flight -= 1
            self.typed.append(text)

    probe = _ConcurrencyBackend()
    d, _, _, _ = _make_daemon(backend=probe)
    d.start()
    t1 = threading.Thread(target=d.on_final, args=("alpha",))
    t2 = threading.Thread(target=d.on_final, args=("bravo",))
    t1.start()
    t2.start()
    # Wait until one worker is blocked inside type_text (holding the lock), then give the second a
    # clear window to (wrongly) enter. Under the lock the second is blocked on _on_final_lock.
    assert _wait_for(lambda: probe.max_in_flight >= 1), "no worker reached type_text"
    _time.sleep(0.2)                      # let the second worker attempt entry
    assert probe.max_in_flight == 1, "type_text calls overlapped — on_final is not serialized"
    gate.set()                            # release the blocked worker(s)
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)
    assert not t1.is_alive() and not t2.is_alive(), "workers did not finish"
    assert sorted(probe.typed) == ["alpha ", "bravo "]   # both typed, in some order


# --- start / stop / toggle ---
```

> **Why these 3 tests:** #1 pins the structural contract (exists, separate, working). #2 is the **deterministic, sleep-free** proof the item literally asks for ("the lock is held during on_final") — `locked()` is True while a worker is blocked inside `type_text`. #3 is the **behavioral** two-thread test that fails (`max_in_flight == 2`) on a no-lock build, directly exercising the bugfix-Issue-5 race pattern. Together they cover structure + invariant + behavior; all three are deterministic (#3's single 0.2 s sleep only widens the race window for the negative control — the assertion is on `max_in_flight`, not timing).

### Implementation Patterns & Key Details

```python
# The whole change is: one new attribute + one 'with' block. Non-obvious details:

# (1) SEPARATE lock, not self._lock (latency + deadlock — see Gotcha #1/#2):
self._on_final_lock = threading.Lock()   # NOT self._lock; NOT an RLock

# (2) Gate OUTSIDE the lock (read-only race guard), body INSIDE:
def on_final(self, text):
    t_final_ready = time.monotonic()
    if not self._listening.is_set():       # OUTSIDE — cheap read-only guard
        return
    with self._on_final_lock:              # INSIDE — clean/type/record/log serialized
        cleaned = textproc.clean(text, self._cfg.filter)
        if not cleaned:
            return                         # lock released on early return — correct
        ...

# (3) Deterministic test of "held during type_text" (no sleeps):
#   worker blocked inside type_text  ->  d._on_final_lock.locked() is True
#   after on_final returns           ->  d._on_final_lock.locked() is False

# (4) Uncontended single-threaded call (all existing tests): instant acquire/release, zero behavior
#   change -> the 9 existing on_final tests stay green with no edits.
```

### Integration Points

```yaml
# No database, routes, config, or env-var change. No new public API. The change is internal state
# (one instance attribute) + the on_final control-flow wrap.

STATE (VoiceTypingDaemon):
  - add attr: "self._on_final_lock: threading.Lock  (in __init__, after self._lock)"
  - invariant: "held across on_final clean->type->record->log; gate check outside"

CONSUMERS (unchanged behavior):
  - run(): "self._recorder.text(self.on_final)  # on_final now self-serializes"
  - sibling S2 (P1.M2.T2.S2): "corrects the now-TRUE 'serializes on_final' docstrings in
    typing_backends.py:22 and feedback.py:35 — this task makes them accurate"
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing

# Structural sanity after Edits A+B: exactly 2 references to the new lock.
grep -n "_on_final_lock" voice_typing/daemon.py
# Expected: one in __init__ (self._on_final_lock = threading.Lock()) and one in on_final
# ('with self._on_final_lock:'). No others.

# OPTIONAL lint — ruff is a uv tool at /home/dustin/.local/bin/ruff (NOT in .venv). Skip if absent.
# mypy is NOT installed — do NOT run it.
/home/dustin/.local/bin/ruff check voice_typing/daemon.py tests/test_daemon.py || true
# Expected: clean (the only new symbol is a threading.Lock() using the already-imported threading).
```

### Level 2: Unit Tests (THE gate)

```bash
cd /home/dustin/projects/voice-typing

# The 3 new tests + all existing on_final tests:
.venv/bin/python -m pytest tests/test_daemon.py -v -k on_final
# Expected: the original 9 on_final tests PASS (uncontended, unchanged) + the 3 NEW tests PASS.

# The whole daemon suite (confirm no regression):
.venv/bin/python -m pytest tests/test_daemon.py -v

# The documented fast suite (bugfix Issue 4's green baseline must hold):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py needs a GPU + espeak assets; it is excluded here.)

# Negative control (optional, proves test #3 bites): temporarily comment out the 'with
# self._on_final_lock:' line, re-run test_on_final_serializes_two_concurrent_callbacks -> it FAILS
# with 'type_text calls overlapped'. Restore the lock; it passes again.
```

### Level 3: Integration Testing (System Validation)

```bash
cd /home/dustin/projects/voice-typing

# Daemon module imports cleanly and the lock is wired (no service to start for a pure-lock change):
.venv/bin/python - <<'PY'
import threading
from voice_typing import daemon
# Cheap construction with stubs (mirrors _make_daemon): no RealtimeSTT, no CUDA.
class _FB:
    def set_listening(self, b): pass
    def record_final(self, t): pass
class _Rec:
    def set_microphone(self, b=True): pass
    def abort(self): pass
    def shutdown(self): pass
class _Be:
    def type_text(self, t): pass
def _probe(): return (True, None)
d = daemon.VoiceTypingDaemon(daemon.VoiceTypingConfig.__new__(daemon.VoiceTypingConfig),
                             _FB(), recorder=_Rec(), backend=_Be(), mic_prober=_probe)
assert hasattr(d, "_on_final_lock"), "missing _on_final_lock"
assert d._on_final_lock is not d._lock, "must be a SEPARATE lock"
assert isinstance(d._on_final_lock, type(threading.Lock())), "must be a threading.Lock"
print("OK: _on_final_lock present, separate from _lock, is a threading.Lock")
PY
# Expected: prints "OK: _on_final_lock present, separate from _lock, is a threading.Lock", exit 0.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No live-daemon/GPU/audio path is exercised by a pure-lock change. The end-to-end guarantee that
# "two finals typed in quick succession never garble" is structurally proven by Level 2 test #3
# (the two-thread no-overlap test). The idle-stability and E2E suites (tests/test_feed_audio.py,
# tests/e2e_virtual_mic.sh) are unaffected and not required to pass for this item (they need GPU +
# PulseAudio null-sink). If a GPU IS available, the optional full-suite smoke is:
#   .venv/bin/python -m pytest tests/test_feed_audio.py -q   # (optional; GPU-gated)
```

## Final Validation Checklist

### Technical Validation

- [ ] `grep -n "_on_final_lock" voice_typing/daemon.py` → exactly 2 hits (init + `with`).
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` → all green (incl. the 3 new tests).
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/daemon.py tests/test_daemon.py` → clean.
- [ ] (Optional) negative control: removing the `with` makes `test_on_final_serializes_two_concurrent_callbacks` fail; restoring it passes.

### Feature Validation

- [ ] `self._on_final_lock` exists in `__init__`, is `not self._lock`, is a `threading.Lock`.
- [ ] `on_final` gate check + `t_final_ready` stamp are OUTSIDE the lock.
- [ ] `textproc.clean`, `backend.type_text`, `feedback.record_final`, `latency.finalize_utterance`, and both `logger` calls are INSIDE `with self._on_final_lock:`.
- [ ] `test_on_final_lock_held_across_type_text` proves the lock is held during `type_text` (deterministic, no fixed sleeps).
- [ ] `test_on_final_serializes_two_concurrent_callbacks` proves two concurrent callbacks never overlap (`max_in_flight == 1`).

### Code Quality Validation

- [ ] Follows the existing on_final test style (section banner, `_make_daemon`, `d.start()`, one focused behavior per test).
- [ ] No new imports in `test_daemon.py` (reuses module-level `threading`/`_time`/`_wait_for`).
- [ ] The `daemon.py` edits are pure structure (one attribute + one `with`); no logic change.
- [ ] Only `voice_typing/daemon.py` and `tests/test_daemon.py` modified (`git status --short`).

### Documentation & Deployment

- [ ] `__init__` lock comment explains why it is separate (latency + deadlock).
- [ ] `on_final` `with` comment cross-references bugfix Issue 5 / P1.M2.T2.S1.
- [ ] No new env vars, no config keys, no user-facing surface (item DOCS: "none — S2 handles docstrings").

---

## Anti-Patterns to Avoid

- ❌ Don't reuse `self._lock` for on_final serialization — it couples on_final latency to toggle/start/stop and risks a lock-ordering deadlock (Gotcha #1/#2).
- ❌ Don't use an `RLock` — on_final acquires the lock exactly once; a plain `Lock` is correct and signals intent.
- ❌ Don't put the gate check inside the lock — it's a read-only race guard; keep it outside (item CONTRACT).
- ❌ Don't edit the `→`/`—` Unicode when copying Edit B's oldText — exact-byte match required (Gotcha #4).
- ❌ Don't modify any existing on_final test, `_arm/_disarm/start/stop/toggle/run`, or `typing_backends.py`/`feedback.py`/`test_voicectl.py` (S2 / P1.M2.T1.S2 own those).
- ❌ Don't add `import time` or `import threading` to `test_daemon.py` — they're already module-level (Gotcha #6); use `_time.sleep`, not `time.sleep`.
- ❌ Don't run `mypy` — it's not installed; pytest is the authoritative gate (Gotcha #7).
- ❌ Don't skip the negative control — confirm test #3 actually bites by (temporarily) removing the `with`.

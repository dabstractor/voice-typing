# Research — on_final serialization lock (P1.M2.T2.S1 / bugfix Issue 5)

This note pins the exact defect, the verified concurrency model of the installed
RealtimeSTT, the precise edit sites in `daemon.py`, and the deterministic test
strategy. The PRP (../PRP.md) references it as the single source of truth.

## 1. The defect (bugfix Issue 5, PRD §4.2/§4.3)

`VoiceTypingDaemon.on_final()` runs gate → clean → type → record → log with
**NO lock** around the body. The docstrings in `typing_backends.py:22` and
`feedback.py:35` CLAIM "the daemon serializes on_final calls" — this is FALSE.
There is no actual serialization. Sibling task S2 (P1.M2.T2.S2) corrects those
docstrings; THIS task (S1) ADDS the lock that makes the claim TRUE.

## 2. Verified concurrency model (the installed RealtimeSTT wheel)

- `VoiceTypingDaemon.run()` (daemon.py:438-455) calls `self._recorder.text(
  self.on_final)` which **blocks** until ONE utterance finalizes, then
  **returns**; the loop re-enters `text()`.
- RealtimeSTT's `transcribe_text()` runs the heavy final-model inference in the
  CALLING (main) thread, then fires the callback via
  `threading.Thread(target=on_transcription_finished, args=(...)).start()` and
  **returns immediately** — no `.join()`. So `text()` returns while the
  `on_final` callback is STILL RUNNING in a fresh worker thread.
- Consequence: the loop re-enters `text()` → the next utterance finalizes → a
  SECOND `on_final` worker thread starts while the FIRST is still in
  `backend.type_text()` (a `subprocess.run` that can take tens of ms). The two
  callbacks overlap.
- Severity: the typing backends spawn an INDEPENDENT child subprocess per call
  (reentrant), so concurrent calls do not CRASH — but typed text can INTERLEAVE
  or land OUT OF ORDER. Low probability in practice (GPU transcription ≫ wtype
  latency) but the invariant "finals are typed in order" is not actually
  guaranteed. The fix (this task) makes it guaranteed.

Reproduction (code inspection, cited in the PRD):
`.venv/bin/python -c "import inspect, RealtimeSTT.audio_recorder as a; \
print(inspect.getsource(a.transcribe_text))"` shows the callback branch is
`threading.Thread(...).start()` with no `.join()`.

## 3. The prescribed fix (item CONTRACT, verbatim requirements)

(a) Add `self._on_final_lock = threading.Lock()` in `VoiceTypingDaemon.__init__`,
    near the other lock/thread init. Use a **SEPARATE** lock from `self._lock`.
(b) In `on_final()`, wrap the clean → type → record → log body (the part AFTER
    the early-return gate check) in `with self._on_final_lock:`. The gate check
    (`if not self._listening.is_set(): return`) STAYS OUTSIDE the lock (read-only
    race guard). `textproc.clean`, `backend.type_text`, `feedback.record_final`,
    `latency.finalize_utterance`, and BOTH `logger` calls go INSIDE the lock.
(c) Test: verify the lock exists and is held during on_final (two concurrent
    calls serialize, or mock the backend and assert no overlap).

## 4. Exact edit sites in `voice_typing/daemon.py` (verified line numbers)

### 4.1 `__init__` — lock initialization (current lines 413-415)
```
413:        self._lock = threading.Lock()
414:        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
415:        self._shutdown = threading.Event()    # cleared → keep looping
```
Insert `self._on_final_lock = threading.Lock()` IMMEDIATELY after line 413
(`self._lock`), with a comment explaining (1) it serializes on_final, (2) it is
SEPARATE from `_lock` so a slow `type_text` cannot stall toggle/start/stop (which
take `_lock` via `_arm/_disarm`), and (3) no lock-ordering deadlock (on_final
never takes `_lock`; `_arm/_disarm` never call on_final).

### 4.2 `on_final` body (current lines 490-528)
```
490:    def on_final(self, text: str) -> None:
491:        """Gate → clean → type → record + log latency. Fired by RealtimeSTT in a NEW thread."""
492:        t_final_ready = time.monotonic()       # entry stamp (PRD §4.2 latency logging)
493:        if not self._listening.is_set():       # GATE: race guard (PRD §4.2/§8 — utterance may
494:            return                             #   complete right after stop)
495:        cleaned = textproc.clean(text, self._cfg.filter)
496:        if not cleaned:                        # rejected: blocklist hallucination / below min_chars
497:            return
498:        payload = cleaned + (" " if self._cfg.output.append_space else "")
499:        try:
500:            self._backend.type_text(payload)   # may raise → caught so the on_final thread survives
501:        except Exception:
502:            logger.exception("typing backend failed for final %r", cleaned)
503:        t_typed = time.monotonic()             # right after type_text (PRD §4.2 latency logging)
504:        self._feedback.record_final(cleaned)   # recognition is final regardless of typing success
505:        record = self._latency.finalize_utterance(
506:            text=cleaned, t_final_ready=t_final_ready, t_typed=t_typed
507:        )
508-517:    # Structured per-utterance latency line ... logger.info(...)
518-528:    logger.debug(...)
```
The transformation: keep lines 492-494 (entry stamp + gate) OUTSIDE the lock;
wrap lines 495-528 (`cleaned = ...` through the end of `logger.debug(...)`) in
`with self._on_final_lock:`, indenting that whole block +4 spaces. The PRP gives
the EXACT oldText→newText so the implementer applies a single `edit` call (no
hand-re-indentation). Note the `→`/`—` Unicode in existing comments — reproduce
them verbatim in oldText.

### 4.3 No other daemon.py changes
`_arm`/`_disarm`/`start`/`stop`/`toggle`/`request_shutdown`/`shutdown` use only
`self._lock` — they are NOT modified. The control-socket server thread takes its
own `self._lock` (a DIFFERENT `threading.Lock` on the `ControlSocketServer`
class, daemon.py:746) — unrelated. `run()` calls `self._recorder.text(
self.on_final)` — unchanged.

## 5. Why a SEPARATE lock (not reusing `self._lock`) — deadlock/latency analysis

- `self._lock` guards toggle/start/stop (via `_arm/_disarm`, which run UNDER
  `self._lock`). If `on_final` ALSO took `self._lock`, a slow `type_text`
  (subprocess) would BLOCK `voicectl toggle` for the typing duration — coupling
  unrelated latencies and making toggle feel laggy.
- Lock-ordering: `on_final` runs in a RealtimeSTT worker thread; it never calls
  any method that takes `self._lock`. `_arm/_disarm` (under `self._lock`) never
  call `on_final`. So acquiring `_on_final_lock` inside `on_final` while NEVER
  holding `self._lock` (and vice versa) creates NO lock-ordering cycle → no
  deadlock. (This is the item's stated rationale; verified by grep — `on_final`
  touches only `self._listening`, `self._cfg`, `self._backend`,
  `self._feedback`, `self._latency`, `logger`, none of which take `self._lock`
  while `on_final` would be holding `_on_final_lock`. `feedback.record_final`
  uses Feedback's OWN internal lock; `latency.finalize_utterance` uses
  LatencyLog's OWN lock — both are leaf locks acquired+released entirely within
  the call, never held across an `on_final`→`_lock` boundary.)

## 6. Existing on_final tests must still pass (single-threaded, uncontended)

Adding an uncontended `with self._on_final_lock:` around the body changes NOTHING
for the existing synchronous tests (they call `d.on_final(...)` from the main
thread; the lock acquires instantly and releases on exit). Verified baseline:
`.venv/bin/python -m pytest tests/test_daemon.py -k on_final -q` → **9 passed**.
The 9 tests (gate, happy-path, append_space false, hallucination reject, typing-
raises, structured-latency-line x2, ring-buffer, rejected-no-latency-line) all
remain valid and green after the change. No existing test is edited by this task.

## 7. Test fixtures available in `tests/test_daemon.py` (reuse, do not reinvent)

- `_make_daemon(*, recorder=None, backend=None, cfg=None)` → `(d, fb, rec, be)`.
  Accepts a custom `backend=` (any duck-typed object with `type_text(text)`); the
  returned `be` IS the injected backend. `_StubRecorder` is the default recorder.
- `_FakeBackend.typed: list[str]` records `type_text` calls; `_FakeBackend(
  raise_on=...)` raises to test error handling.
- `d.start()` arms the mic + sets listening (calls `_arm` → `set_microphone(True)`
  on the stub + `set_listening(True)`). Needed so the on_final gate passes.
- `_wait_for(predicate, timeout=2.0, interval=0.01)` polls until truthy.
- **Imports already module-level (lines 334-335):** `import threading` and
  `import time as _time`. ⇒ New tests use `threading.Event/Thread`, `_time.sleep`,
  and `_wait_for` with **NO new import**. (Line 583 documents this reuse
  convention: "reused here".) Use `_time.sleep`, NOT `time.sleep` (the alias).
- Section banner style: `# --- <topic> ---` dividers; one focused assert per test.

## 8. Deterministic test strategy (3 focused tests)

1. **Structural** — `test_on_final_has_dedicated_serialization_lock`: `d.
   _on_final_lock` exists, `is not d._lock` (separate), is a working mutex
   (`acquire(blocking=False)` returns True; `locked()` True then False after
   release). Pins the item's "SEPARATE lock" requirement.
2. **Deterministic probe (authoritative)** — `test_on_final_lock_held_across_
   type_text`: inject a backend whose `type_text` sets an Event then blocks on a
   release Event; spawn `d.on_final(...)` in a worker thread; `_wait_for(started)`
   → assert `d._on_final_lock.locked() is True` (held DURING type_text → a second
   on_final would block); `release.set()`; join; assert `locked() is False` and
   the text was typed. **Zero fixed sleeps** — fully deterministic. This is the
   "the lock is held during on_final" assertion the item literally asks for.
3. **Behavioral (two threads)** — `test_on_final_serializes_two_concurrent_
   callbacks`: inject a backend that tracks `max_in_flight` (concurrent type_text
   calls) and blocks on a gate; fire two `on_final` in two threads; `_wait_for(
   max_in_flight >= 1)` then `_time.sleep(0.2)` to give the second worker a clear
   window to (wrongly) enter; assert `max_in_flight == 1` (never overlapped);
   release; join; assert both texts typed. In the BUGGY (no-lock) build this
   asserts `== 2` and fails — confirmed negative control.

Placement: insert the 3 tests (under a `# --- on_final serialization ... ---`
banner) in the existing on_final section, AFTER `test_on_final_typing_raises_
is_caught_and_record_still_happens` and BEFORE the `# --- start / stop / toggle
---` divider. Exact insertion oldText→newText is in the PRP.

## 9. Tooling & validation reality (verified)

- pytest 9.1.1 in `.venv`. Run: `.venv/bin/python -m pytest tests/test_daemon.py
  -v` (FULL path — zsh aliases `python`/`pip`). Whole fast suite:
  `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`.
- ruff 0.14.13 is a uv tool at `/home/dustin/.local/bin/ruff` (NOT in `.venv`);
  optional lint: `/home/dustin/.local/bin/ruff check voice_typing/daemon.py
  tests/test_daemon.py`. The verbatim edits/tests are ruff-clean (the only new
  daemon symbol is a module-level `threading.Lock()`, already-imported).
- mypy is NOT installed — do NOT list it as a gate.

## 10. Scope boundaries (do / don't)

DO: edit `voice_typing/daemon.py` (`__init__` + `on_final`); add 3 tests to
`tests/test_daemon.py`.
DON'T: edit `typing_backends.py` or `feedback.py` docstrings (S2 / P1.M2.T2.S2
owns the docstring correction — this task makes the claim TRUE so S2 can leave
the wording as-is or tighten it); edit `test_voicectl.py` (P1.M2.T1.S2, parallel,
owns it); change `_arm/_disarm/start/stop/toggle/run`; add `append_space` or any
behavioral change beyond the lock; touch `PRD.md`/`tasks.json`/
`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps.

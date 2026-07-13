# PRP — P1.M1.T1.S2: Implement bounded teardown — hard timeout + force-cleanup of worker processes

## Goal

**Feature Goal**: Make `VoiceTypingDaemon.shutdown()` **bounded** — it completes in ≤ its timeout budget even when RealtimeSTT's `recorder.shutdown()` wedges indefinitely at an unbounded `threading.Thread.join()` (the confirmed ~90s root cause). On timeout it **force-cleans** the spawn-started worker processes (`transcript_process`, `reader_process`) that hold the CUDA contexts/VRAM, so VRAM is actually released and a racing re-arm (under M3's idle-unload) is never blocked for ~90s. This is the **hard prerequisite** for the lazy-load feature (PRD §4.2bis "Idle unload" + §8 risk row) and also fixes the existing `voicectl quit` hang.

**Deliverable**: (1) a new `_bounded_shutdown(self, timeout=10.0)` method on `VoiceTypingDaemon` (daemon thread + `threading.Event` wait + force-cleanup); (2) `shutdown()` rewritten to add an `if self._recorder is not None:` guard (M2 lazy-load prep) and delegate to `_bounded_shutdown()`; (3) docstring/comment refresh (shutdown docstring + the stale `LATER`/`P1.M4.T2.S2` tags at daemon.py:11 and :409); (4) new tests in `tests/test_daemon.py` (`FakeSlowRecorder` + force-cleanup assertion, a delegation spy test, and a None-guard test). The existing `_StubRecorder`/`_RaisingRecorder` shutdown tests stay green.

**Success Definition**:
- (a) `shutdown()` returns within `~timeout` seconds even if `recorder.shutdown()` blocks forever (proven by the `FakeSlowRecorder` test: `_bounded_shutdown(timeout=0.3)` returns in `< 2.0s`).
- (b) On timeout, `transcript_process.terminate()` + `reader_process.terminate()` are called (force-releasing VRAM), `recorder.is_shut_down=True` (idempotency), and `recorder.realtime_transcription_model=None` (model-ref release) — all asserted.
- (c) The fast path (`_StubRecorder`) still completes instantly and increments `.shutdowns`; existing tests `test_shutdown_calls_recorder_shutdown_once`, `test_shutdown_is_idempotent`, `test_shutdown_swallows_recorder_failure`, `test_stop_and_request_shutdown_still_never_shutdown` all pass UNCHANGED.
- (d) `_RaisingRecorder` (shutdown raises) still produces the `"recorder.shutdown() failed"` ERROR log via `caplog` (the exception is logged inside the bounded thread, NOT silently swallowed).
- (e) `shutdown()` with `self._recorder = None` (M2 prep) is a no-op and does not raise.
- (f) Idempotent (`_shutdown_done` flag) and defensive (never re-raises).
- (g) `.venv/bin/python -m pytest tests/test_daemon.py -v` is fully green (existing + new).

## User Persona

**Target User**: (1) The end user — whose `voicectl quit` / `systemctl --user stop voice-typing` currently hangs ~90s then gets `SIGKILL`'d; and (2) the M3 idle-unload watchdog (PRD §4.2bis), which will call this exact teardown path every `auto_unload_idle_seconds` and would re-trigger the hang every 30 min if teardown were unbounded.

**Use Case**: The daemon tears the recorder down on `quit` (and, after M3, after idle). The teardown MUST be bounded so (a) `quit` returns promptly, (b) systemd never reaches its `TimeoutStopSec` `SIGKILL`, and (c) idle-unload doesn't wedge the single-flight load/teardown lock for ~90s at a time.

**Pain Points Addressed**: the ~90s `quit` hang (`run() loop exiting` → 90s → `SIGKILL` / `Failed with result 'timeout'`), and the latent risk that idle-unload (M3) would reproduce it every 30 min. Bounded teardown is the prescribed mitigation (PRD §8 risk row).

## Why

- **Prerequisite for lazy-load (PRD §4.2bis + §8).** Idle-unload tears the recorder down every 30 min and blocks any re-arm racing it under the single-flight lock. An unbounded teardown would hang the daemon for ~90s each time. Bounded teardown is the explicit hard prerequisite.
- **Fixes the existing `quit` hang now.** Every `voicectl quit` today runs `run() loop exiting` → ~90s → systemd `SIGKILL`. S2 makes `quit` return in ~seconds (well inside the `TimeoutStopSec=15` T2.S1 will set).
- **Root cause is confirmed (S1).** S1 pinned the wedge to an unbounded `threading.Thread.join()` inside `RealtimeSTT.shutdown_recorder()` (`recording_thread.join()` / `realtime_thread.join()`, no timeout); the two `mp.Process` joins are already bounded (10s + `terminate()`). So the correct fix shape is a **whole-call hard timeout + force-terminate the spawn processes** (the VRAM holders) — NOT trying to kill Python threads (impossible; they're `daemon=True` and die with the process anyway).
- **Preserves every existing invariant.** Idempotency (`_shutdown_done` + RealtimeSTT's `is_shut_down`), defensiveness (never re-raise), and the "shutdown is ONLY for quit, never toggle/stop" rule are all kept. S2 is additive at the call site + additive in tests.

## What

Rewrite `VoiceTypingDaemon.shutdown()` (daemon.py:818-844) to: keep the idempotency guard; add `if self._recorder is None: return` (M2 prep); delegate to a new `_bounded_shutdown()`. Add `_bounded_shutdown(self, timeout=10.0)` that runs `recorder.shutdown()` in a daemon thread, waits on a `threading.Event` up to `timeout`, and on timeout force-terminates `transcript_process` + `reader_process`, sets `is_shut_down=True`, and clears `realtime_transcription_model`. Refresh the shutdown docstring + the stale `LATER`/`P1.M4.T2.S2` comment tags. Add tests covering the timeout/force-cleanup path, the delegation wiring, and the None guard.

### Success Criteria

- [ ] `_bounded_shutdown(self, timeout=10.0)` exists; launches `recorder.shutdown()` in a `daemon=True` thread; waits via `threading.Event().wait(timeout)`; on the fast path returns after completion.
- [ ] On timeout: `transcript_process` and `reader_process` are `.terminate()`'d if `.is_alive()`; `recorder.is_shut_down = True`; `recorder.realtime_transcription_model = None`; a WARNING is logged.
- [ ] `shutdown()` adds `if self._recorder is not None:` guard; replaces the direct `self._recorder.shutdown()` with `self._bounded_shutdown()`; stays idempotent + defensive.
- [ ] `_do_shutdown` (inner thread) LOGS failures via `logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")` — NOT a silent `pass` (preserves `test_shutdown_swallows_recorder_failure`).
- [ ] Docstring (L819) + comments (L11, L409) refreshed (bounded teardown now implemented; stale plan tags removed; the "NEVER on toggle/stop" rule preserved).
- [ ] New tests pass: `FakeSlowRecorder` force-cleanup-returns-within-timeout; delegation spy; None-guard. Existing shutdown tests unchanged + green.

## All Needed Context

### Context Completeness Check

_Pass._ The exact current `shutdown()` body, the precise edit anchors (verbatim), the test-fake contracts (`_StubRecorder`/`_RaisingRecorder`/`_make_daemon`), the one critical compatibility trap (silent-swallow breaks `test_shutdown_swallows_recorder_failure`), and the confirmed RealtimeSTT attributes for force-cleanup are all captured below with line citations. A developer who has never seen this repo can implement S2 from this PRP + the reference implementation. No live daemon/GPU probe is needed — the unit tests with fakes are deterministic.

### Documentation & References

```yaml
# THE ROOT-CAUSE CONTRACT (S1's deliverable — the premise S2 builds on)
- docfile: plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis.md
  why: §Mitigation SKETCHES _bounded_shutdown (daemon thread + Event wait + force-terminate processes).
       §Process/Thread model confirms transcript_process/reader_process are mp.Process(spawn) = VRAM
       holders; recording_thread/realtime_thread are daemon=True (die with process; can't/needn't kill).
  critical: "The sketch's `except Exception: pass` is a TRAP — it would break test_shutdown_swallows_
       recorder_failure. S2 must logger.exception() instead (see Gotcha #1 + this PRP's research §5)."

- docfile: plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md
  why: S1's confirmation. Pins the wedge to an unbounded threading.Thread.join() in shutdown_recorder();
       confirms the two process joins are bounded (timeout=10 + terminate); links 90s to systemd's
       default TimeoutStopSec. Validates that force-terminating the spawn processes is the right release.
  critical: "S2 need NOT know which thread blocks — it wraps the WHOLE recorder.shutdown() + force-
       terminates the processes regardless. The confirmation hands this off explicitly."

# THIS SUBTASK'S OWN RESEARCH NOTE — exact anchors + the compat trap + test design
- docfile: plan/003_27d1f88f5a9f/P1M1T1S2/research/bounded_teardown_findings.md
  why: §1 the verbatim shutdown() body + line numbers; §2 the verbatim comment/docstring anchors;
       §3 the RealtimeSTT attribute table; §4 the test-fake contracts; §5 THE compat trap; §6 the
       happens-before proof that fast-path .shutdowns assertions hold; §7 the new-test design.
  section: "§5 (silent-swallow trap) and §6 (happens-before) are load-bearing."

# THE EDIT SITE
- file: voice_typing/daemon.py
  why: shutdown() @ 818-844 (body); docstring opener @ 819; module-top SCOPE comment @ 11; comment @ 409.
       threading (L75) + time (L76) already imported → _bounded_shutdown needs NO new imports.
  pattern: "Idempotency guard under self._lock + getattr(self,'_shutdown_done',False); defensive
            try/except with logger.exception (never re-raise). KEEP both; add None guard + delegation."
  gotcha: "The success INFO log 'recorder shutdown complete (GPU workers released)' and the failure
           logger.exception MUST move INSIDE _do_shutdown (the thread) so they fire on the bounded
           path and caplog still captures the failure (Gotcha #1)."

# THE TEST FILE + FAKES (the pattern to mirror + the tests to keep green)
- file: tests/test_daemon.py
  why: _StubRecorder (L365-390, .shutdowns counter); _make_daemon (L424-430); _RaisingRecorder
       (L1074-1079); existing shutdown tests (L1058-1095). threading (L346) + time as _time (L347)
       already imported (additive-section style).
  pattern: "Additive section: place new fakes (_FakeProcess, FakeSlowRecorder) + new tests after the
            existing Layer-A shutdown tests (after ~L1095). Reuse _make_daemon + threading + _time."
  gotcha: "Do NOT change _StubRecorder/_RaisingRecorder or the 4 existing shutdown tests. New tests
           are ADDITIVE. _StubRecorder has NO transcript_process/reader_process/is_shut_down/
           realtime_transcription_model attrs — FakeSlowRecorder must ADD them (§7 of research note)."

# PRD CONTEXT (READ-ONLY) — why teardown must be bounded
- docfile: plan/003_27d1f88f5a9f/prd_snapshot.md
  why: §4.2bis 'Idle unload' = bounded teardown is a HARD PREREQUISITE; §8 risk row 'recorder.shutdown()
       hangs ~90s' prescribes 'hard timeout + force-cleanup of worker threads / transcript_process'.
  critical: "The bounded teardown is what makes idle-unload safe. Cite §4.2bis + §8 in the docstring."

# DOWNSTREAM (NOT this subtask — scope boundaries)
- file: systemd/voice-typing.service
  why: T2.S1 (P1.M1.T2.S1) adds TimeoutStopSec=15. S2 does NOT touch the unit.
- file: voice_typing/daemon.py (_load_recorder)
  why: M2 (P1.M2.T1.S1) adds lazy load. S2 only adds the `if self._recorder is None:` guard as PREP;
       it does not implement lazy load itself.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py            # shutdown() @ 818-844 (EDIT); _bounded_shutdown NEW; docstring L819 + comments L11/L409 (EDIT)
├── tests/
│   └── test_daemon.py       # _StubRecorder L365, _make_daemon L424, _RaisingRecorder L1074, shutdown tests L1058-1095
│                            #   (ADD new fakes _FakeProcess + FakeSlowRecorder + 3 new tests after ~L1095)
├── systemd/voice-typing.service  # UNTOUCHED (T2.S1 owns TimeoutStopSec)
└── .venv/.../RealtimeSTT/core/shutdown.py  # read-only wheel (the confirmed root cause; not edited)
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py        # MODIFY: +_bounded_shutdown method; rewrite shutdown() body; refresh docstring + 2 comments. NO new files.
tests/test_daemon.py          # MODIFY: +_FakeProcess +FakeSlowRecorder fakes; +3 tests (force-cleanup, delegation, None-guard). NO new files.
# NOTHING ELSE. No systemd, no config, no README, no other source.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT SILENTLY SWALLOW THE RECORDER EXCEPTION. The architecture-analysis sketch uses
#   `except Exception: pass` inside _do_shutdown. That BREAKS the existing test_shutdown_swallows_
#   recorder_failure, which asserts caplog contains "recorder.shutdown() failed". The inner thread MUST:
#       except Exception:
#           logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")
#   (logger.exception is ERROR-level on voice_typing.daemon; caplog captures it; thread-safe.) This also
#   preserves the success INFO log. See research note §5.

# CRITICAL #2 — HAPPENS-BEFORE OF .shutdowns ON THE FAST PATH. _StubRecorder.shutdown() increments
# .shutdowns then returns. _do_shutdown sets done.set() in `finally` AFTER recorder.shutdown() returns.
# done.wait() returns True only after done.set(). So when d.shutdown() returns, rec.shutdowns==1 is
# guaranteed (no race). The existing test_shutdown_calls_recorder_shutdown_once / _is_idempotent pass
# UNCHANGED. Do not add sleeps or re-checks.

# CRITICAL #3 — FORCE-CLEAN THE PROCESSES, NOT THE THREADS. recording_thread/realtime_thread are
# threading.Thread with .daemon=True — Python has NO thread.kill(); they die when the PROCESS exits and
# need not (and cannot) be killed. transcript_process/reader_process are mp.Process(spawn) with their
# OWN CUDA context/VRAM — .terminate()-ing them releases VRAM immediately. S2 touches ONLY the processes.

# CRITICAL #4 — DEFAULT TIMEOUT IS 10.0 (the contract). Use 10.0, not the analysis sketch's 15.0. Tests
# call _bounded_shutdown(timeout=0.3) DIRECTLY (not via shutdown()) so the suite stays fast — shutdown()
# with a slow recorder would otherwise wait the full 10s.

# CRITICAL #5 — _StubRecorder LACKS the force-cleanup attributes. It has no transcript_process,
# reader_process, is_shut_down, or realtime_transcription_model. The force-cleanup branch MUST use
# getattr(self._recorder, attr, None) for the processes (defensive) so a real AudioToTextRecorder AND a
# stub both work; is_shut_down / realtime_transcription_model are set via direct attribute assignment
# (real recorders + FakeSlowRecorder allow it). FakeSlowRecorder must ADD all four attributes (§7).

# CRITICAL #6 — IDEMPOTENCY + DEFENSIVENESS ARE NON-NEGOTIABLE. Keep the `with self._lock: if getattr(
# self,"_shutdown_done",False): return; self._shutdown_done=True` guard EXACTLY. Keep shutdown() defensive
# (never re-raise) — wrap the _bounded_shutdown() call in try/except logger.exception as belt-and-suspenders.
# _bounded_shutdown itself is also defensive (the force-cleanup steps each wrapped in try/except).

# GOTCHA #7 — `if self._recorder is None:` IS M2 PREP. Today __init__ always builds a recorder, so the
# guard never fires in current tests. M2 (lazy load) makes recorder possibly-None. S2 adds the guard now;
# a small test (d._recorder=None; d.shutdown() must not raise) proves it. Do NOT implement lazy load here.

# GOTCHA #8 — KEEP THE "NEVER shutdown() ON TOGGLE/STOP" RULE. The L409 comment says
# "NEVER recorder.shutdown() on toggle/stop — only on quit". That rule STAYS CORRECT. The S2 edit to L409
# only refreshes the stale (P1.M4.T2.S2) plan tag, NOT the rule. test_stop_and_request_shutdown_still_
# never_shutdown must still pass (rec.shutdowns == 0).

# GOTCHA #9 — ADDITIVE TEST STYLE. test_daemon.py uses additive sections that re-import as needed
# (signal as _signal @ L1052, ast/sys @ L1171, inspect @ L1730). threading (L346) + time as _time (L347)
# are already module-level → a new test placed after L1095 can use them directly. Match the section style.

# GOTCHA #10 — full-path discipline. `.venv/bin/python -m pytest tests/test_daemon.py -v` (machine aliases
# python3→uv run). `bash`/`grep`/`git` are fine as-is.
```

## Implementation Blueprint

### Data models and structure

None (no ORM/pydantic). The only "structure" is the `_bounded_shutdown` control flow: a daemon thread running `recorder.shutdown()`, a `threading.Event` join, and a force-cleanup branch. The RealtimeSTT attribute contract:

```python
# Force-cleanup touches these recorder attributes (confirmed in shutdown analysis + installed wheel):
#   transcript_process          mp.Process(spawn)  → .is_alive() then .terminate()  (releases VRAM)
#   reader_process              mp.Process(spawn)  → .is_alive() then .terminate()  (releases VRAM/mic)
#   is_shut_down                bool flag          → set = True (future .shutdown() returns early = idempotent)
#   realtime_transcription_model whisper model ref → set = None (lets GC reclaim host-side model state)
# recording_thread / realtime_thread are daemon=True threading.Thread → NOT touched (die with process).
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD the _bounded_shutdown(self, timeout=10.0) method to VoiceTypingDaemon
  - PLACE: directly BEFORE the existing shutdown() method (keeps the two teardown methods adjacent).
  - CODE (reference implementation — copy-ready; load-bearing parts annotated):
        def _bounded_shutdown(self, timeout: float = 10.0) -> None:
            """Tear down the recorder with a hard timeout + force-cleanup of spawn processes.

            recorder.shutdown() (RealtimeSTT v1.0.2 shutdown_recorder()) can wedge indefinitely at an
            unbounded threading.Thread.join() (recording_thread/realtime_thread — confirmed root cause of
            the ~90s quit hang; see architecture/realtimestt_shutdown_analysis_confirmed.md). This wraps
            the whole call in a daemon thread + a threading.Event wait. If it completes within `timeout`,
            great. If not, we force-terminate the spawn-started transcript_process + reader_process (the
            CUDA-context/VRAM holders — terminating them releases VRAM immediately), mark is_shut_down
            (idempotency), drop the realtime model reference, and log a WARNING. The daemon threads
            (recording_thread/realtime_thread) are daemon=True and die with the process — we cannot and
            need not kill them.

            Defensive: every step is best-effort; this method never re-raises.
            """
            done = threading.Event()

            def _do_shutdown() -> None:
                try:
                    self._recorder.shutdown()
                    logger.info("recorder shutdown complete (GPU workers released)")
                except Exception:
                    # NOT a silent pass — preserves the "recorder.shutdown() failed" log the tests +
                    # operators rely on (test_shutdown_swallows_recorder_failure). caplog is thread-safe.
                    logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")
                finally:
                    done.set()

            t = threading.Thread(target=_do_shutdown, name="vt-recorder-shutdown", daemon=True)
            t.start()

            if done.wait(timeout=timeout):
                return  # completed within budget (success or handled-failure already logged)

            # Timed out — force-clean the spawn processes (VRAM holders) + mark shut down for idempotency.
            logger.warning(
                "recorder.shutdown() exceeded %.1fs budget; force-terminating worker processes "
                "(transcript_process, reader_process) to release VRAM", timeout
            )
            for attr in ("transcript_process", "reader_process"):
                proc = getattr(self._recorder, attr, None)   # defensive: stubs may lack the attr
                try:
                    if proc is not None and proc.is_alive():
                        proc.terminate()
                except Exception:
                    logger.debug("force-terminate of %s failed (best-effort)", attr, exc_info=True)
            try:
                self._recorder.is_shut_down = True           # makes a future .shutdown() a no-op
            except Exception:
                pass
            try:
                self._recorder.realtime_transcription_model = None   # release host-side model ref
            except Exception:
                pass
  - CONSTRAINTS:
      * Use logger.exception(...) in _do_shutdown's except — NOT `pass` (Gotcha #1).
      * `timeout=10.0` default (Gotcha #4). daemon=True thread (so a wedged thread never blocks process exit).
      * getattr(..., None) for the processes (Gotcha #5); direct assignment for is_shut_down/model.
      * No new imports (threading L75 + time L76 already in daemon.py — time not strictly needed here).

Task 2: REWRITE shutdown() to add the None guard + delegate to _bounded_shutdown()
  - EDIT (exact oldText → newText). The CURRENT body block is:
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return
            self._shutdown_done = True
        try:
            self._recorder.shutdown()
            logger.info("recorder shutdown complete (GPU workers released)")
        except Exception:
            logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")
  - REPLACE WITH:
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return
            self._shutdown_done = True
        if self._recorder is None:
            # M2 lazy-load prep: the recorder is built on first arm, so it may never exist (e.g. a
            # session that never armed). Nothing to tear down.
            return
        try:
            self._bounded_shutdown()
        except Exception:
            # Defensive belt-and-suspenders: _bounded_shutdown is already best-effort, but shutdown()
            # itself must NEVER re-raise (a teardown failure must not mask the original shutdown reason).
            logger.exception("bounded teardown failed (best-effort; ignored)")
  - CONSTRAINTS:
      * KEEP the idempotency guard (`with self._lock` + `_shutdown_done`) EXACTLY.
      * The success/failure logging now lives INSIDE _bounded_shutdown (moved, not duplicated). Do NOT
        leave a duplicate `logger.info("recorder shutdown complete...")` in shutdown().
      * shutdown() takes NO timeout arg (uses the _bounded_shutdown default 10.0).

Task 3: REFRESH the shutdown() docstring (daemon.py:819)
  - EDIT the docstring opener + body. CURRENT opener:
        """Full recorder teardown (PRD §4.2; P1.M4.T2.S2). Idempotent + defensive.
  - The docstring body currently describes the direct recorder.shutdown() call. REWRITE to describe the
    BOUNDED behavior. Suggested opener + additions:
        """Full recorder teardown — BOUNDED (PRD §4.2; §4.2bis idle-unload prerequisite; §8 risk row).

        Idempotent + defensive. Delegates to _bounded_shutdown(): runs recorder.shutdown() in a daemon
        thread under a hard timeout (default 10s); on timeout it force-terminates the spawn-started
        transcript_process + reader_process (the CUDA/VRAM holders) so VRAM is released and a racing
        re-arm under the single-flight lock is never blocked for the ~90s RealtimeSTT wedge. Keeps the
        idempotency + defensive guarantees; never re-raises.
        ... (KEEP the "NEVER call this on toggle/stop ..." + sanctioned-callers paragraphs) ...
  - Drop the stale "P1.M4.T2.S2" tag (this is plan 003's bounded teardown). Keep the rest of the
    docstring's correct guidance (NEVER on toggle/stop; sanctioned callers; must-not-run-inside-text()).

Task 4: REFRESH the stale plan tags at daemon.py:11 and daemon.py:409
  - L11 CURRENT: `  - LATER: control socket (P1.M4.T2.S1), full clean shutdown (P1.M4.T2.S2 — recorder.shutdown()),`
    EDIT the "full clean shutdown (P1.M4.T2.S2 — recorder.shutdown())" clause to reflect that bounded
    teardown is now IMPLEMENTED, e.g.:
        `  - DONE: control socket, bounded recorder teardown (hard timeout + force-cleanup of worker`
        `    processes) — see _bounded_shutdown(). LATER: ... (leave any genuinely-still-LATER items).`
    (Keep it surgical: only the shutdown clause changes; if other LATER items remain, keep them.)
  - L409 CURRENT: `    toggle-on). NEVER recorder.shutdown() on toggle/stop — only on quit (P1.M4.T2.S2).`
    EDIT to drop the stale tag while KEEPING the rule, e.g.:
        `    toggle-on). NEVER recorder.shutdown() on toggle/stop — only on quit (bounded teardown).`
  - CONSTRAINT: the "NEVER on toggle/stop — only on quit" RULE is correct and MUST remain (Gotcha #8).

Task 5: ADD the new test fakes + tests to tests/test_daemon.py
  - PLACE: in a new additive section AFTER the existing Layer-A shutdown tests (after ~L1095, before the
    next existing section). Reuse _make_daemon (L424) + threading (L346) + time as _time (L347).
  - CODE (reference implementation — copy-ready):
        # P1.M1.T1.S2 — bounded teardown: _bounded_shutdown force-cleans on timeout (ADDITIVE).
        # Reuses _make_daemon / _StubRecorder / threading / time-as-_time from earlier in this file.


        class _FakeProcess:
            """Stand-in for an mp.Process: .is_alive() True, .terminate() records the call."""

            def __init__(self) -> None:
                self.terminated = False

            def is_alive(self) -> bool:
                return True

            def terminate(self) -> None:
                self.terminated = True


        class _FakeSlowRecorder(_StubRecorder):
            """shutdown() blocks forever — simulates the RealtimeSTT ~90s wedge.

            Adds the force-cleanup attrs the real recorder has (transcript_process, reader_process,
            is_shut_down, realtime_transcription_model) so the timeout branch can act on them.
            """

            def __init__(self) -> None:
                super().__init__()
                self.transcript_process = _FakeProcess()
                self.reader_process = _FakeProcess()
                self.is_shut_down = False
                self.realtime_transcription_model = object()  # non-None sentinel

            def shutdown(self):  # type: ignore[override]
                # Blocks forever; never returns, never increments .shutdowns. Runs in a daemon thread
                # inside _bounded_shutdown, so it dies with the test process (no hang).
                threading.Event().wait()


        def test_bounded_shutdown_force_cleans_on_timeout():
            d, _fb, rec, _be = _make_daemon(recorder=_FakeSlowRecorder())
            start = _time.monotonic()
            d._bounded_shutdown(timeout=0.3)   # MUST return despite shutdown() blocking forever
            elapsed = _time.monotonic() - start
            assert elapsed < 2.0, f"bounded teardown took {elapsed:.2f}s (expected < ~0.3s + slack)"
            assert rec.transcript_process.terminated, "transcript_process not force-terminated (VRAM leak)"
            assert rec.reader_process.terminated, "reader_process not force-terminated (VRAM leak)"
            assert rec.is_shut_down is True, "is_shut_down not set (idempotency marker)"
            assert rec.realtime_transcription_model is None, "realtime model ref not released"


        def test_shutdown_delegates_to_bounded_shutdown():
            # Proves shutdown() routes through _bounded_shutdown (not a leftover direct recorder.shutdown()).
            d, _fb, _rec, _be = _make_daemon()
            calls: list[float] = []
            d._bounded_shutdown = lambda timeout=10.0: calls.append(timeout)
            d.shutdown()
            assert calls == [10.0], f"shutdown() did not delegate to _bounded_shutdown(): {calls}"


        def test_shutdown_is_noop_when_recorder_is_none():
            # M2 lazy-load prep: if the recorder was never built, shutdown() must not raise / not touch it.
            d, _fb, _rec, _be = _make_daemon()
            d._recorder = None
            d.shutdown()  # must NOT raise
  - CONSTRAINTS:
      * Do NOT modify _StubRecorder / _RaisingRecorder / _make_daemon / the 4 existing shutdown tests.
      * _FakeSlowRecorder.shutdown() blocks via threading.Event().wait() (NOT time.sleep(huge) — Event is
        cleaner and the daemon thread dies with the process).
      * The force-cleanup test calls _bounded_shutdown(timeout=0.3) DIRECTLY (fast; Gotcha #4).
      * assert elapsed < 2.0 (generous upper bound for CI jitter; the real expectation is ~0.3s).

Task 6: VALIDATE — run the Validation Loop L1–L4. No git commit unless the orchestrator directs it.
  If asked to commit, message:
  "P1.M1.T1.S2: bounded teardown — _bounded_shutdown hard-timeout + force-cleanup of worker processes".
```

### Implementation Patterns & Key Details

```python
# PATTERN — the bounded teardown control flow (the load-bearing design):
def _bounded_shutdown(self, timeout: float = 10.0) -> None:
    done = threading.Event()
    def _do_shutdown():
        try:
            self._recorder.shutdown()
            logger.info("recorder shutdown complete (GPU workers released)")
        except Exception:
            logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")  # NOT pass!
        finally:
            done.set()
    threading.Thread(target=_do_shutdown, name="vt-recorder-shutdown", daemon=True).start()
    if done.wait(timeout=timeout):
        return  # fast path (stub completes instantly) OR handled-failure — both already logged inside
    # timeout path: force-terminate processes (VRAM holders) + mark shut down + drop model ref
    logger.warning("recorder.shutdown() exceeded %.1fs budget; force-terminating worker processes", timeout)
    for attr in ("transcript_process", "reader_process"):
        proc = getattr(self._recorder, attr, None)
        try:
            if proc is not None and proc.is_alive():
                proc.terminate()
        except Exception:
            logger.debug("force-terminate of %s failed (best-effort)", attr, exc_info=True)
    try: self._recorder.is_shut_down = True
    except Exception: pass
    try: self._recorder.realtime_transcription_model = None
    except Exception: pass

# GOTCHA: the daemon thread is daemon=True so a wedged recorder.shutdown() never blocks process exit.
# GOTCHA: done.wait() returning True is a happens-before edge — anything _do_shutdown did before done.set()
#         (incl. incrementing .shutdowns / logging) is visible to the main thread. (research §6)
```

### Integration Points

```yaml
DAEMON LIFECYCLE:
  - shutdown() is called by (a) the quit on_quit hook (after request_shutdown() broke text()), and
    (b) main()'s finally block (after run() returns; covers the SIGTERM/SIGINT signal path). Both now
    get a BOUNDED teardown: a normal quit returns in seconds, never hits systemd's TimeoutStopSec.

DOWNSTREAM — T2.S1 (P1.M1.T2.S1, systemd TimeoutStopSec=15):
  - S2's bounded teardown completes well inside 15s, so T2.S1's TimeoutStopSec=15 is safe — systemd
    never reaches SIGKILL on a normal quit. S2 does NOT touch the unit; T2.S1 does.

DOWNSTREAM — M2 (P1.M2.T1.S1, lazy load):
  - S2 adds the `if self._recorder is None: return` guard as PREP. When M2 makes the recorder
    possibly-None (built on first arm), shutdown() is already safe. S2 does NOT implement lazy load.

DOWNSTREAM — M3 (P1.M3.T1.S1, idle-unload watchdog):
  - Idle-unload calls this exact teardown path every auto_unload_idle_seconds. S2's boundedness is the
    hard prerequisite (PRD §4.2bis) — without it idle-unload would wedge every 30 min. M3 can now call
    shutdown()/teardown knowing it returns in ~seconds.

REALTIMESTT ATTRIBUTE CONTRACT (the force-cleanup surface):
  - transcript_process / reader_process: mp.Process(spawn), own CUDA context/VRAM → .terminate() releases.
  - is_shut_down: bool → set True (shutdown_recorder() returns early if already shut down = idempotent).
  - realtime_transcription_model: whisper ref → None (host-side GC).
  - recording_thread / realtime_thread: daemon=True → NOT touched (die with process).

FILES NOT TOUCHED (scope boundary):
  - systemd/voice-typing.service (T2.S1 owns TimeoutStopSec).
  - _load_recorder / lazy load (M2 owns).
  - config.py / config.toml / README / install.sh (later milestones).
```

## Validation Loop

> All commands use FULL PATHS (machine aliases python3→uv run). Run from `/home/dustin/projects/voice-typing`.
> All gates are FAST unit tests with fakes — NO GPU/models/network/live daemon needed.

### Level 1: Syntax + the new method exists + tests collect

```bash
cd /home/dustin/projects/voice-typing
echo "--- daemon.py parses ---"
.venv/bin/python -c "import ast; ast.parse(open('voice_typing/daemon.py').read()); print('L1a PASS: daemon.py parses')"
echo "--- test_daemon.py parses ---"
.venv/bin/python -c "import ast; ast.parse(open('tests/test_daemon.py').read()); print('L1b PASS: test_daemon.py parses')"
echo "--- _bounded_shutdown exists on VoiceTypingDaemon ---"
.venv/bin/python -c "from voice_typing import daemon; assert hasattr(daemon.VoiceTypingDaemon, '_bounded_shutdown'); print('L1c PASS: _bounded_shutdown present')"
echo "--- new tests collect ---"
.venv/bin/python -m pytest tests/test_daemon.py --collect-only -q | grep -E 'test_bounded_shutdown_force_cleans_on_timeout|test_shutdown_delegates_to_bounded_shutdown|test_shutdown_is_noop_when_recorder_is_none' \
  && echo "L1d PASS: new tests collected" || echo "L1d FAIL: new tests missing"
# Expected: all green; 3 new tests collected.
```

### Level 2: Existing shutdown tests STILL pass (compat — the load-bearing regression gate)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v -k "shutdown or stop_never or request_shutdown_still_never" 
# Expected (existing, UNCHANGED):
#   test_shutdown_calls_recorder_shutdown_once   PASSED  (rec.shutdowns == 1 after d.shutdown())
#   test_shutdown_is_idempotent                  PASSED  (3x shutdown -> rec.shutdowns == 1)
#   test_shutdown_swallows_recorder_failure      PASSED  (rec.shutdowns==1 + "recorder.shutdown() failed" in caplog)
#   test_stop_and_request_shutdown_still_never_shutdown  PASSED (rec.shutdowns == 0)
# If test_shutdown_swallows_recorder_failure FAILS, the _do_shutdown except is a silent `pass` (Gotcha #1) —
# change it to logger.exception(...) and re-run.
```

### Level 3: The new bounded-teardown tests pass (the feature gate)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v -k "bounded_shutdown_force_cleans or delegates_to_bounded or noop_when_recorder_is_none"
# Expected:
#   test_bounded_shutdown_force_cleans_on_timeout  PASSED  (returns < 2.0s; both processes terminated;
#     is_shut_down True; realtime_transcription_model None)
#   test_shutdown_delegates_to_bounded_shutdown    PASSED  (spy saw [10.0])
#   test_shutdown_is_noop_when_recorder_is_none    PASSED  (no raise)
# If force-cleans FAILS on elapsed: the timeout branch isn't reached (check done.wait(timeout) + the
# WARNING log). If it FAILS on .terminated: the getattr/terminate path is wrong (Gotcha #5).
```

### Level 4: Full test_daemon.py green + scope (only daemon.py + test_daemon.py changed)

```bash
cd /home/dustin/projects/voice-typing
echo "--- full test_daemon.py suite ---"
.venv/bin/python -m pytest tests/test_daemon.py -q
echo "exit: $? (expect 0)"
echo "--- docstring + comment tags refreshed (no stale P1.M4.T2.S2 in the edited zones) ---"
grep -n "P1.M4.T2.S2" voice_typing/daemon.py && echo "L4 NOTE: stale tag still present somewhere (review)" || echo "L4 PASS: no P1.M4.T2.S2 tags remain in daemon.py"
grep -q "_bounded_shutdown" voice_typing/daemon.py && echo "L4 PASS: _bounded_shutdown present in daemon.py"
echo "--- git diff touches ONLY voice_typing/daemon.py + tests/test_daemon.py ---"
git diff --name-only | grep -vxE 'voice_typing/daemon.py|tests/test_daemon.py' && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only daemon.py + test_daemon.py changed"
# Expected: full suite green; bounded teardown present; only the two files changed.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: daemon.py + test_daemon.py parse; `_bounded_shutdown` exists; 3 new tests collect.
- [ ] L2: existing shutdown tests pass UNCHANGED (incl. `test_shutdown_swallows_recorder_failure` — proves the inner thread LOGS, not silently swallows).
- [ ] L3: new tests pass — force-cleanup returns within budget + terminates both processes + sets is_shut_down + clears model ref; delegation spy sees `[10.0]`; None-guard no-raise.
- [ ] L4: full `test_daemon.py` green; only `voice_typing/daemon.py` + `tests/test_daemon.py` changed.

### Feature Validation
- [ ] `shutdown()` is bounded: returns within ~timeout even if `recorder.shutdown()` blocks forever (FakeSlowRecorder test).
- [ ] Force-cleanup releases VRAM holders (transcript_process + reader_process `.terminate()`'d) on timeout.
- [ ] Idempotency (`_shutdown_done`) + defensiveness (never re-raise) preserved.
- [ ] `if self._recorder is None:` guard present (M2 lazy-load prep) and proven by a test.

### Code Quality Validation
- [ ] `_do_shutdown` uses `logger.exception(...)` on failure (NOT `pass`) — compat with existing test + operator visibility.
- [ ] Success/failure logging lives inside `_do_shutdown` (no duplicate logs in `shutdown()`).
- [ ] Force-cleanup uses `getattr(self._recorder, attr, None)` for processes (defensive vs stubs lacking the attr).
- [ ] Follows file conventions: `threading`/`time` already imported; additive test section; `_make_daemon` reused.

### Scope Boundary Validation
- [ ] `systemd/voice-typing.service` unmodified (T2.S1 owns `TimeoutStopSec`).
- [ ] Lazy load NOT implemented (M2 owns; S2 only adds the None guard as prep).
- [ ] No config/README/install.sh/other-source edits.
- [ ] The "NEVER shutdown() on toggle/stop — only on quit" rule preserved (L409 edit refreshes the tag only).
- [ ] No bare `python`/`pytest` (full-pathed `.venv/bin/python -m pytest`).

### Documentation & Deployment
- [ ] shutdown() docstring describes bounded behavior + force-cleanup + cites PRD §4.2bis/§8.
- [ ] Stale `P1.M4.T2.S2`/`LATER` tags at daemon.py:11 and :409 refreshed (bounded teardown now implemented).
- [ ] If asked to commit: message references bounded teardown + force-cleanup for traceability.

---

## Anti-Patterns to Avoid

- ❌ Don't use `except Exception: pass` inside `_do_shutdown` — it erases the failure log and BREAKS `test_shutdown_swallows_recorder_failure`. Use `logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")`. (Gotcha #1.)
- ❌ Don't try to kill `recording_thread`/`realtime_thread` — they're `daemon=True` `threading.Thread`; Python has no `thread.kill()`. They die with the process. Force-terminate only the spawn PROCESSES (the VRAM holders). (Gotcha #3.)
- ❌ Don't change the default timeout to 15.0 — the contract specifies `timeout=10.0`. Tests use a small timeout directly on `_bounded_shutdown`. (Gotcha #4.)
- ❌ Don't break the idempotency guard or the defensiveness — `with self._lock` + `_shutdown_done` stays; `shutdown()` never re-raises. (Gotcha #6.)
- ❌ Don't duplicate the success/failure logging in `shutdown()` — it now lives inside `_bounded_shutdown`'s `_do_shutdown` thread.
- ❌ Don't modify `_StubRecorder`/`_RaisingRecorder`/`_make_daemon`/the 4 existing shutdown tests — S2 tests are ADDITIVE. (Gotcha #5/#8.)
- ❌ Don't drop the "NEVER shutdown() on toggle/stop — only on quit" rule when editing the L409 comment — only the stale plan tag changes. (Gotcha #8.)
- ❌ Don't implement lazy load — S2 only adds the `if self._recorder is None:` guard as M2 prep. (Gotcha #7.)
- ❌ Don't touch `systemd/voice-typing.service` — T2.S1 owns `TimeoutStopSec=15`.
- ❌ Don't test the slow path via `d.shutdown()` (it would wait the full 10s default) — call `_bounded_shutdown(timeout=0.3)` directly.
- ❌ Don't use bare `python`/`pytest` (zsh aliases python3→uv run); use `.venv/bin/python -m pytest`.

---

## Confidence Score

**9/10** for one-pass implementation success. The change is small and precisely specified: one new method (`_bounded_shutdown`) + a surgical rewrite of the `shutdown()` body (exact oldText/newText given) + two comment-tag refreshes + three additive tests, all with copy-ready reference code. Every load-bearing fact is empirically verified against the live repo: the exact `shutdown()` body and line numbers, the test-fake contracts (`_StubRecorder`/`_RaisingRecorder`/`_make_daemon`), the four existing shutdown tests that must stay green, the `threading`/`time` imports already present, and — critically — the silent-swallow compatibility trap (the architecture sketch's `except: pass` would break `test_shutdown_swallows_recorder_failure`; the PRP mandates `logger.exception`). The deterministic L2 gate (existing tests pass) + L3 gate (new tests pass) catch every way this can go wrong without needing a GPU/live daemon. The −1 is that the force-cleanup branch touches RealtimeSTT-private attributes (`transcript_process`, `is_shut_down`, `realtime_transcription_model`) whose exact runtime types are confirmed by source analysis but only exercised against fakes in the unit tests — a future RealtimeSTT bump could rename them; the defensive `getattr`/try-except wrapping limits that blast radius, and the production-path confirmation (force-cleanup actually releasing VRAM on a hung shutdown) is a runtime check best done in T2/M3 integration, not this unit-test subtask.

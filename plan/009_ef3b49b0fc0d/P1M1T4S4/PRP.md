# PRP — P1.M1.T4.S4: Route native finals before any generic output

## Goal

**Feature Goal**: Give `voice_typing/daemon.py` a **native-only acceptance route** for recorder callbacks. While a
native editor session (PRD §4.8.1 B) has capture open, an ASR final is handled by identity verification →
`textproc.clean` → retain+enqueue — and **nothing generic runs**: no typing/`StreamingOutput` commit, no generic
`SessionRecovery`, no `feedback.record_final`/latency/transcript log, no hypr notify, no cancel-suppression window,
no evdev HALT/Backspace guard. Partials and the `speech` event support **lifecycle only**. Media duck, mic, listening
gate, idle auto-stop and drain flags behave exactly as today. The route exposes the **wakeups** T4.S5 (stop/cancel/
drain), T4.S6 (ended) and T4.S7 (socket pump) hang off.

**Deliverable** (1 module edited, 1 new test file; nothing else):
1. `voice_typing/daemon.py` — native state + 5 helpers + early native branches in `on_final`, `_on_partial`,
   `_touch_speech`, `note_user_keypress`, `_arm`, `_refresh_context_prompt`; [Mode A] docstrings.
2. `tests/test_native_final_route.py` — hermetic CPU-only tests over the existing fake host + tripwires.

**Success Definition**:
- (a) With a native session listening, an `ACCEPTED` final whose `(host_generation, arm_seq)` equals the session arm
  fence is cleaned, retained in `NativeRecovery` and enqueued in `OfferQueue`; every generic tripwire is silent.
- (b) Missing identity (no `relay_event`), non-`ACCEPTED` classes (sentinel / cancelled / unidentified), and fence
  mismatches (previous arm, respawned host, `arm_seq == 0`) are **rejected**: not retained, not typed, no seed consumed,
  utterance lifecycle closed.
- (c) `_on_partial` and `_touch_speech` do no generic work for native; idle auto-stop clock and `_final_pending`
  still update.
- (d) `note_user_keypress` is a no-op for native (no HALT, no cancel, no abort, mic stays on).
- (e) `_arm(native=True)` opens mic, listening gate, lifecycle feedback and ducking, but opens no generic recovery
  session and touches no stream-engine session state.
- (f) With no native capture open, `on_final` / `_on_partial` / `_touch_speech` behave **byte-identically** to today
  (the native route helper is never entered; existing `tests/test_daemon.py` FAILED set == G1 baseline).
- (g) The reader thread adds no lock other than a short `self._lock` hold around the pure in-memory `enqueue`
  (no I/O, no wait, no join, no abort, no drain); `_on_final_lock` is still the only outer lock.
- (h) No new log line carries recognition text or seed text — codes, counts and ids only.
- (i) `timeout 300 .venv/bin/python -m pytest tests/test_native_final_route.py tests/test_editor_offer_queue.py tests/test_editor_session.py tests/test_session_recovery.py tests/test_native_recovery.py -q` → all green.
- (j) `git diff --name-only` == `{voice_typing/daemon.py, tests/test_native_final_route.py}`.

## User Persona

**Target User**: the dictation user in a native editor (Pi prompt, Neovim) — via the T4.S5/T4.S7 consumers.
**Use Case**: Start dictation from an editor adapter; speak several utterances; each accepted final is offered to
the editor over the owner socket and inserted there as one undoable edit — never typed globally.
**Pain Points Addressed**: native-era text leaking into the focused window via the generic typing backend; native
transcript appearing in `state.json` / `voicectl session` / toasts; a stray Backspace or keypress (the editor's own
input) disarming or cancelling the session; a previous arm's or a respawned host's final being attributed to the
current session.

## Why

- PRD §4.8.1 B: "Native sessions bypass `StreamingOutput`, bulk target acquisition, focus injectors, evdev
  typing/cancel guards, and transcript-bearing desktop/state feedback." "Daemon-side ASR callbacks run the existing
  final cleaning/filtering, deduplicate by recorder generation/utterance id (reject missing/stale identity), record
  the accepted final for recovery, and enqueue it without socket I/O under the control lock or on the recorder
  reader thread." "For native delivery, use only this session's accepted finals as the rolling source."
- `architecture/system_context.md` → "Control/recorder boundaries": "Native `on_final` clean/filter/retain/enqueue
  precedes all generic backend, recovery, `record_final`/latency and log branches; `_on_partial`/`_touch_speech` may
  update lifecycle, not output. Inspect recorder relay's direct `_feedback` calls and daemon run/arm/guard paths as
  well; native bypass means no typing/paste/clipboard/adapter activation, evdev guarding, or transcript feedback even
  during failure."
- Chain: T2.S4 gives the acceptance point (`_handoff_context_prompt`), T3.S4 the reservation, T4.S1 `NativeRecovery`,
  T4.S2 `OfferQueue` (retain-before-offer), T4.S3 the per-event identity (`relay_event`, `FinalClass`) and the
  documented eligibility contract (`recorder_host.py:114-119`). This task is the first consumer that wires them.

## What

### Success Criteria
- [ ] New daemon surface: `_native_recovery`, `_native_fence`, `_native_queue`, `_native_offer_evt`,
      `_native_rejects`; helpers `_native_open_capture_locked`, `_native_close_capture_locked`, `_native_on_final`,
      `_native_final_verdict`, `_native_reject_final`; `_arm(..., native=False)` keyword.
- [ ] (a)–(j) hold; T3.S4 / T4.S1 / T4.S2 suites unchanged-green.
- [ ] Not in scope (left to their items): stop/cancel/drain policy (T4.S5), `NativeRecovery.end_session` and the
      `ended` frame (T4.S6), any socket/`editor-start` activation (T4.S7), `voicectl recover` (T5).

## All Needed Context

### Context Completeness Check
_Pass._ The exact insertion lines, every branch that must be bypassed, the eligibility expression, the lock/thread
discipline, the rolling-context gap and its fix, the test harness names, and a verbatim test list are given below.
The implementer needs only this PRP, `research/insertion_point_map.md`, and `daemon.py` :1006-1019, :1463-1642,
:1802-1941, :2083-2100, :2208-2314, :2775-2816, :2883-3045.

### Documentation & References

```yaml
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S4/research/insertion_point_map.md
  why: "§1 on_final branch table + insertion point; §2 reader siblings; §3 arm/disarm; §4 existing native seams; §5 rolling gap."
  critical: "Insertion = first statement inside `with self._on_final_lock:` (:1484). `_arm` is called at :2816 INSIDE the _lock hold."
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S4/research/native_contracts.md
  why: "Extracted signatures for NativeReservation / OfferQueue / NativeRecovery, prior-PRP T4.S4 lines, G1 baseline."
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Control/recorder boundaries' paragraph 3 is this task's spec; 'Buffer ownership and recovery' gives the lock rule."
- file: voice_typing/recorder_host.py
  why: "IDENTITY CONTRACT — on disk since cc203ce. `FinalClass` :1443-1453; `_RelayEvent` :1455-1470
        (kind, final_class, host_generation, arm_seq, session_gen, utterance_id); `_CaptureBoundary` :1473-1483;
        properties `relay_identity` :392, `generation` :407, `arm_seq` :413, `relay_event` :419, `capture_boundary` :430."
  pattern: "CONSUMER CONTRACT :114-119 — inside on_final (reader thread):
            ev = host.relay_event; eligible = (ev is not None and ev.kind == 'final'
            and ev.final_class is FinalClass.ACCEPTED and ev.arm_seq > 0
            and (ev.host_generation, ev.arm_seq) == session_arm_fence)"
  gotcha: "relay_event is meaningful ONLY inside the callback. DUPLICATE/STALE finals never reach on_final (host
           drops them before the callback). READ ONLY — do not edit recorder_host.py."
- file: voice_typing/editor_session.py
  why: "Stage :71-78 (STARTING/LISTENING/DRAINING/ENDED, ACTIVE_STAGES); Owner(id, token, created_at, deadline) :82-87;
        NativeReservation :106-165 (.owner, .stage, .live, .commit(token), .end_evt); OfferQueue :210-430."
  pattern: "OfferQueue(session_id, recovery, *, clock=time.monotonic, ack_timeout_s=5.0, max_unsettled=8);
            enqueue(text) -> EnqueueOutcome {QUEUED, REVOKED, CLOSED} — retain-before-offer, so ONE call retains AND
            queues; close() makes later enqueue CLOSED (no retain). READ ONLY."
  gotcha: "OfferQueue takes no lock internally — every mutation must happen under the caller's `_lock`."
- file: voice_typing/session_recovery.py
  why: "NativeRecovery :319 — retain_final(sid, seq, text)->bool :334; mark_offer_attempted :375; settle_final :392;
        end_session(sid, reason) :409; recover :428; active_id :448; counts()->tuple[int,int] :454; clear :463.
        Construct with defaults (read :319-333). READ ONLY."
- file: voice_typing/daemon.py
  why: "The only module edited. Line map in research/insertion_point_map.md."
  pattern: "Lock-free sentinel reads on the reader (`self._listening.is_set()` gate :1476; 'stores are atomic in
            CPython' :1958); `_locked` helpers called only under `self._lock`; 'safe from ANY thread' seam
            `note_user_keypress` :2092-2096; DEBUG/INFO lines carry ids/counts only (T2.S2/S3 style)."
  gotcha: "on_final never takes `_lock` today (`_on_final_lock` is used only at :1483) — this task adds the FIRST
           `_on_final_lock → _lock` edge; no path may hold `_lock` and then call on_final."
- file: tests/test_daemon.py
  why: "Harness: _FakeBackend :739, _FakeHost :783 (cfg, feedback, latency, on_final, on_partial, on_speech, *),
        _make_daemon(...) :904-921 -> (d, fb, rec, be) via hermetic_cfg / _DaemonFakeFeedback / _StubRecorder /
        _ok_probe; _make_daemon_with_feedback :2174. See how an existing test arms a daemon with a fake host
        (grep -n 'd._arm()' tests/test_daemon.py | head -3). Do NOT edit this file."
- file: plan/009_ef3b49b0fc0d/P1M1T4S2/PRP.md
  why: "CALLER PATTERN (quoted): reader thread `with d._lock: q.enqueue(text)` (retains + queues, never writes);
        pump `with d._lock: attempt = q.begin_offer(now)` → write OUTSIDE the lock → `q.finish_offer(ok)`."
- file: plan/009_ef3b49b0fc0d/P1M1T4S3/PRP.md
  why: "CONSUMER CONTRACT section (identical to recorder_host.py:114-124) and the T4.S5 drain rule this task leaves a seam for."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py            # on_final :1463, _touch_speech :1943, _on_partial :1983, note_user_keypress :2083,
                                  # _handoff_context_prompt :2208, _refresh_context_prompt :2260, _start_fenced :2691,
                                  # _arm :1802, _disarm :1882, native helpers :2883-3045                 ← EDIT
voice_typing/recorder_host.py     # T4.S3 identity surface (cc203ce)                                        READ ONLY
voice_typing/editor_session.py    # NativeReservation + OfferQueue                                           READ ONLY
voice_typing/session_recovery.py  # NativeRecovery                                                           READ ONLY
tests/test_daemon.py              # harness + G1 baseline                                                    do NOT edit
tests/test_native_final_route.py                                                                            ← CREATE
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
voice_typing/daemon.py
  + __init__ (:1019): _native_recovery, _native_fence, _native_queue, _native_offer_evt, _native_rejects
  + _native_open_capture_locked() -> bool      — latch the arm fence + build the queue (control thread, _lock held)
  + _native_close_capture_locked() -> None     — clear fence + close queue + clear wakeup (every native end)
  + _native_final_verdict(ev) -> str           — identity/fence verdict ("ok" | code)   [T4.S5 extends for DRAINING]
  + _native_reject_final(why) -> None          — lifecycle close + count + one text-free log (reader thread)
  + _native_on_final(text) -> None             — THE NATIVE ACCEPTANCE ROUTE (reader thread, _on_final_lock held)
  ~ on_final :1484, _on_partial :1994, _touch_speech :1978, note_user_keypress :2097, _arm :1823-1877,
    _refresh_context_prompt :2297, _end_native_locked :2972                                  — early native branches
tests/test_native_final_route.py               — (a)-(h) with tripwires + generic byte-identity
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — NATIVE GOES FIRST, AND ONLY NATIVE. Route on the lock-free sentinel `self._native_fence is not None`
# (a tuple/None reference assigned under _lock; atomic read on the reader). When it is None the generic path must
# execute EXACTLY today's lines — do not reorder, re-indent or "clean up" anything below the new branch.
# CRITICAL #2 — THE FENCE IS LATCHED AFTER THE MIC OPENS. RecorderHost.set_microphone(True) bumps the HOST's arm_seq
# BEFORE its cmd put (T4.S3 Critical #4), and _start_fenced calls _arm at :2816 inside the _lock hold that committed
# the reservation (:2803). So latch (host.generation, host.arm_seq) in _arm AFTER :1872. Never infer the fence from
# the first final, a daemon counter (self._arm_seq is a DIFFERENT counter) or the last partial.
# CRITICAL #3 — READER THREAD: _native_on_final runs with _on_final_lock held and must NOT take any other lock except
# a short `with self._lock` around OfferQueue.enqueue (pure memory). No socket write, no begin_offer, no wait/join,
# no _safe_abort, no _begin_drain, no host.set_prompt under _lock (set_prompt is a non-blocking queue put and runs
# under _on_final_lock per :2233 — via the existing _refresh_context_prompt).
# CRITICAL #4 — REJECTED ≠ LOST. A rejected native final still closes the utterance lifecycle
# (_final_pending=False, _utterance_finalized=True — the same two stores as :1621-1626) so run()/drain never waits
# for a "typed" final that will not come. It must NOT call _handoff_context_prompt (a rejected final never consumes
# the seed — T2.S4).
# CRITICAL #5 — OFFERQUEUE IS NOT THREAD-SAFE BY DESIGN. The reader (enqueue) and the T4.S7 pump (begin_offer/ack/
# check_deadline) share it; EVERY mutation happens under self._lock. Never hold _lock across a socket write.
# CRITICAL #6 — CLOSED MEANS NOT RETAINED. OfferQueue.enqueue returns CLOSED without retaining once close() ran.
# Close the queue in _native_close_capture_locked (called from _end_native_locked, the funnel every native end
# already reaches: _disarm :1940, terminate_native, dead-host :1422-1423) so a late final cannot resurrect a session.
# CRITICAL #7 — DO NOT IMPLEMENT T4.S5/S6/S7 here: no stop/cancel/drain policy, no capture_boundary rule, no
# `ended` frame, no NativeRecovery.end_session call, no socket/editor-start wiring, no voicectl recover.
# CRITICAL #8 — LOGS: codes/counts/ids only. Never text, never seed, never a ProtocolError detail.
# CRITICAL #9 — AGENTS.md: every pytest under `timeout` with the bash-tool timeout above it; .venv/bin/python;
# test_daemon.py = `timeout 500 ... --tb=no` with bash timeout >= 560; never run the daemon or voicectl.
# CRITICAL #10 — DO NOT EDIT recorder_host.py, editor_session.py, editor_protocol.py, session_recovery.py,
# tests/test_daemon.py, tests/test_recorder_host.py, tests/test_recorder_identity_boundary.py, any plan file,
# PRD.md, tasks.json, README.md.
```

## Implementation Blueprint

### Data models and structure

```python
# __init__ — append after :1019 (self._native_end_delivered = False)
self._native_recovery = NativeRecovery()               # daemon-wide: outlives sessions (T5.S1 serves it after end)
self._native_fence: "tuple[int, int] | None" = None    # (host.generation, host.arm_seq) of the OPEN native capture
self._native_queue: "OfferQueue | None" = None         # per native session: built at arm commit, closed at end
self._native_offer_evt = threading.Event()             # WAKEUP: reader SETs after a QUEUED enqueue; T4.S7 pump CLEARs
self._native_rejects: dict[str, int] = {}              # bounded: <= 8 fixed verdict keys, counts only
# imports: extend the existing `from voice_typing.editor_session import (...)` (:152) with OfferQueue, EnqueueOutcome;
# add `from voice_typing.recorder_host import FinalClass` and `from voice_typing.session_recovery import NativeRecovery`
# following the file's existing import style (check :140-160 for grouping; recorder_host import must stay lazy-free of CUDA).
```

```python
# Verdict codes of _native_final_verdict (fixed strings; they are the ONLY reject reason vocabulary)
"ok" | "missing" | "kind" | "class:<final_class.value>" | "fence"
```

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT (read-only, bounded): 
  git log --oneline -1 == cc203ce-or-later; grep -c "^class FinalClass" voice_typing/recorder_host.py == 1;
  grep -n "_on_final_lock" voice_typing/daemon.py  → only :867 and :1483 (no other holder ⇒ no lock-order edge);
  grep -c "Lock()" voice_typing/daemon.py          → record N (must be N after the edit);
  sed -n '1824,1870p;1994,2000p;2094,2100p;2290,2304p;2972,3010p;3011,3030p' voice_typing/daemon.py  → read before editing;
  sed -n '2142,2207p' voice_typing/daemon.py       → confirm EVERY key action funnels through note_user_keypress
                                                    (no other self.cancel()/_disarm() callout in the listener);
  grep -n "hermetic_cfg\|^from\|^import" tests/test_daemon.py | head -20 ; grep -ln "test_daemon import" tests/*.py | head -3
                                                    → how sibling files reuse the harness (follow that precedent);
  grep -n "d._arm()" tests/test_daemon.py | head -3 → how tests arm a daemon with a fake host;
  baseline: timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40
                                                    → save the FAILED node ids (bash-tool timeout 560).

Task 1: CREATE tests/test_native_final_route.py (RED first). CPU-only, no threads started by the test, no sockets,
        no subprocess (monkeypatch subprocess.run/Popen to raise during on_final), XDG_RUNTIME_DIR → tmp_path via
        hermetic_cfg. Harness:
  - reuse test_daemon's helpers per the Task-0 precedent (or define a local _make() mirroring :904-921).
  - class _IdentityHost(test_daemon._FakeHost): `generation = 3`; `arm_seq = 0`; `relay_event = None`;
    override set_microphone(True): `self.arm_seq += 1` THEN super().set_microphone(True).
  - SID = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"; def ev(cls, gen=1, uid=1, host_gen=3, arm=1) -> _RelayEvent(...)
  - def native_listening(d, host): d._host = host; now = monotonic(); d._native_seq += 1;
      owner = Owner(SID, d._native_seq, now, now + 30.0); d._native = NativeReservation(owner, None, now=now);
      with d._lock: assert d._native.commit(owner.token); d._arm(native=True)
  - tripwires: _NoBackend(_FakeBackend) type_text/press_backspace raise; _NoStream with on_partial/commit/freeze/
    resume/reset_boundary/reset_session/set_streaming/note_user_keypress AND a `committed` property that raises;
    _RecordingRecovery wrapping the real SessionRecovery (records method names); _NoLatency (note_partial/
    finalize_utterance raise); _DaemonFakeFeedback subclass with record_final/update_partial/notify raising.
  - def silent(*tripwires): context manager asserting no raise escaped (pytest.fail on tripwire fire).
  Tests:
  - test_accepted_final_is_retained_queued_and_not_typed — eligible ev; d.on_final("hello world"):
      queue.pending_count == 1; recovery.counts()[0] == 1; offer_evt.is_set(); _final_pending False;
      _utterance_finalized True; all tripwires silent; no subprocess call.
  - test_generic_session_is_byte_identical — fence None; the REAL _FakeBackend/_DaemonFakeFeedback:
      d.on_final("hello") types "hello " and records the final; monkeypatch d._native_on_final to raise → not called;
      _native_queue is None; offer_evt clear.
  - test_missing_identity_is_rejected — relay_event None → no retain (counts 0), nothing typed, lifecycle closed,
      _seed_handoff_pending unchanged (seed a daemon with d._seed_handoff_pending = True first).
  - test_non_accepted_classes_are_rejected — parametrize SENTINEL/CANCELLED/UNIDENTIFIED.
  - test_fence_mismatches_are_rejected — arm_seq 1 vs fence 2 (previous arm); host_generation 4 vs 3 (respawn);
      arm_seq 0; kind "partial".
  - test_filtered_final_is_rejected_and_seed_kept — "you" (blocklist) → verdict "filtered"; counts 0; seed pending.
  - test_partial_and_speech_are_lifecycle_only — d._on_partial("hel"): stream/recovery/latency/feedback silent;
      d._touch_speech(): _last_speech_monotonic set, _final_pending True, stream.resume NOT called.
  - test_keypress_neither_halts_nor_cancels_native — d.note_user_keypress(): _listening still set; host mic still on;
      no abort; _native still live/LISTENING; backend untouched.
  - test_arm_skips_generic_session_setup — after native_listening: _listening set; host mic True;
      feedback.set_listening(True) seen; recovery saw NO open_session; stream saw NO set_streaming/reset_session.
  - test_ended_session_closes_queue_and_refuses_late_final — with d._lock: d._end_native_locked("stopped", None)
      (mirror :1940); fence None; queue closed; then host.relay_event = eligible ev; d._listening.clear();
      d.on_final("late") → nothing retained/typed.
  - test_rolling_context_uses_this_sessions_accepted_finals — unseeded and seeded (d._seed_handoff_pending=True):
      after d.on_final("hello world") host.set_prompt called with prompt_engine.rolling_context_prompt("hello world");
      _stream.committed never read; after 2 finals the prompt covers both.
  - test_overflow_switches_to_recovery_only — 9 distinct-uid eligible finals: 9th REVOKED; queue.revoked;
      recovery.counts()[0] == 9; nothing typed.
  - test_reject_and_accept_logs_carry_no_text — caplog: no record contains "hello world" / "you".
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_final_route.py -q  → RED.

Task 2: EDIT voice_typing/daemon.py — state + imports (Blueprint "Data models").

Task 3: EDIT voice_typing/daemon.py — helpers (place after _native_blockers_locked, ~:2925):
  a) _native_open_capture_locked(self) -> bool:   # control thread, _lock held, mic ALREADY opening
         native = self._native; host = self._host
         if not (self._native_owner_live_locked() and native.stage is Stage.LISTENING and host is not None
                 and hasattr(host, "arm_seq")): logger.warning("native: cannot latch arm fence (stage=%s)", ...); return False
         self._native_fence = (host.generation, host.arm_seq)
         self._native_queue = OfferQueue(native.owner.id, self._native_recovery)
         self._native_rejects = {}; self._native_offer_evt.clear()
         logger.info("voice-typing native capture open: gen=%d arm_seq=%d", *self._native_fence); return True
  b) _native_close_capture_locked(self) -> None:   # idempotent; every native end
         self._native_fence = None; q, self._native_queue = self._native_queue, None
         if q is not None: q.close()
         self._native_offer_evt.clear()
  c) _native_final_verdict(self, ev) -> str:      # reader thread; T4.S5 ADDS the DRAINING rule here (document)
         if ev is None: return "missing"
         if ev.kind != "final": return "kind"
         if ev.final_class is not FinalClass.ACCEPTED: return "class:" + ev.final_class.value
         if ev.arm_seq <= 0 or ev.session_gen is None or ev.utterance_id is None: return "missing"
         if (ev.host_generation, ev.arm_seq) != self._native_fence: return "fence"
         return "ok"
  d) _native_reject_final(self, why: str) -> None:  # reader thread
         self._final_pending = False; self._utterance_finalized = True
         self._native_rejects[why] = self._native_rejects.get(why, 0) + 1
         logger.info("voice-typing native final rejected: %s", why)
  e) _native_on_final(self, text: str) -> None:    # reader thread; _on_final_lock held; NOT _lock
         why = self._native_final_verdict(getattr(self._host, "relay_event", None))
         if why != "ok": self._native_reject_final(why); return
         cleaned = textproc.clean(text, self._cfg.filter)
         if not cleaned: self._native_reject_final("filtered"); return
         self._handoff_context_prompt(cleaned)     # T2.S4 acceptance point (seed → rolling, once)
         self._refresh_context_prompt()            # native source branch (Task 3g) — accepted finals only
         with self._lock:                          # pure in-memory; NO I/O under the lock
             q = self._native_queue
             if not self._native_owner_live_locked() or q is None:
                 ended = True
             else:
                 ended = False; outcome = q.enqueue(cleaned)
         if ended: self._native_reject_final("ended"); return
         self._final_pending = False; self._utterance_finalized = True
         if outcome is EnqueueOutcome.QUEUED: self._native_offer_evt.set()   # WAKEUP for the T4.S7 pump
         logger.info("voice-typing native final: %s pending=%d", outcome.value, pending)  # counts only

Task 4: EDIT voice_typing/daemon.py — the early native branches (each a 2-4 line addition, nothing else moved):
  a) on_final, FIRST statement inside `with self._on_final_lock:` (:1484):
         if self._native_fence is not None: self._native_on_final(text); return
     (the listening gate :1476-1479 stays before it; the cancel window, clean, stream, typing, record_final,
      latency, notify, generic recovery all remain untouched below).
  b) _on_partial, right after the gate's `return` (:1993): if self._native_fence is not None: return
  c) _touch_speech (:1978): guard `self._stream.resume()` with `if self._native_fence is None:`; keep :1979-1981.
  d) note_user_keypress, right after the :2096-2097 gate: if self._native_fence is not None: return
  e) _arm signature: `def _arm(self, streaming: bool | None = None, *, native: bool = False) -> None`
     - guard the generic-session setup with `if not native:` — exactly three sites: stream set_streaming
       (:1830-1832), `self._session_recovery.open_session()` (:1834), stream reset_session (:~1843-1846).
       Keep :1855, :1860, :1865, :1872, :1873-1876, :1877 unconditional.
     - AFTER `self._host.set_microphone(True)` (:1872) add, fail CLOSED:
         if native and not self._native_open_capture_locked():
             self._host.set_microphone(False); self._listening.clear()
             self._end_native_locked("delivery_failed", "no-fence")   # mirror the call shape at :1940
             logger.warning("native: arm fence could not be latched; capture not opened"); return
     - _start_fenced :2816 → `self._arm(streaming=streaming, native=native_tok is not None)`.
     - _disarm needs NO change: close_session() :1913 is a no-op when no generic session was opened (assert in test).
  f) _end_native_locked (:2972): call self._native_close_capture_locked() in the same lock hold, immediately after
     the reservation's stage becomes ENDED (read :2972-3010 for the exact spot; it must run on EVERY end cause).
  g) _refresh_context_prompt (:2297): add a FIRST source branch — `if self._native_fence is not None:
     source = " ".join(self._session_accepted)` — ahead of the `_seed_handoff_done` branch (an unseeded native
     session never sets _seed_handoff_done and would otherwise read the generic engine's `committed`).

Task 5: EDIT docstrings [Mode A]: on_final (:1464-1475) — add a "NATIVE ROUTE (P1.M1.T4.S4)" paragraph: what is
        bypassed, the sentinel, the verdict codes, "rejected final closes lifecycle, never consumes the seed";
        one line each in _on_partial, _touch_speech, note_user_keypress, _arm; _native_on_final docstring carries
        the CONSUMER CONTRACT below verbatim.

Task 6: VERIFY: Task-1 file green; T3.S4/T4.S1/T4.S2 suites green; test_daemon.py FAILED set == Task-0 baseline.
Task 7: VALIDATE L1-L3. Commit only if the orchestrator directs.
```

### Implementation Patterns & Key Details

```python
# PATTERN — the route is a guard, not a rewrite: generic code below stays byte-identical.
with self._on_final_lock:
    if self._native_fence is not None:          # P1.M1.T4.S4: native route FIRST — before ANY generic output
        self._native_on_final(text)
        return
    ...existing :1486 onward unchanged...

# GOTCHA — eligibility is evaluated from the snapshot taken INSIDE the callback (host.relay_event), never cached.
# GOTCHA — order inside _native_on_final is load-bearing: verdict → clean → handoff → refresh → enqueue → lifecycle
#          stores → wakeup. A rejected/ended final must not reach _handoff_context_prompt.
# GOTCHA — `_locked` helpers (_native_owner_live_locked) are called only inside `with self._lock`.

CONSUMER CONTRACT (document it in the _native_on_final docstring; hand to T4.S5 / T4.S6 / T4.S7):
  T4.S5 (stop/cancel/drain): extend _native_final_verdict for Stage.DRAINING — accept iff
      (ev.host_generation, ev.arm_seq, ev.session_gen, ev.utterance_id) == host.capture_boundary
      (whole-value snapshot, may be <=1 event superseded). The route already sets _final_pending=False /
      _utterance_finalized=True exactly like the generic path, so the existing _begin_drain / _drain_timeout seams
      work unchanged. Cancel/lost: with d._lock: q.revoke("cancelled") (then the existing off-lock _safe_abort).
  T4.S6 (ended): recoverable = q.drain_pending(); call self._native_recovery.end_session(sid, reason) at end.
      The queue is already closed and the fence cleared by _native_close_capture_locked.
  T4.S7 (pump): wait on d._native_offer_evt (bounded by the 2 s ping tick); on wake: evt.clear(); loop
      `with d._lock: attempt = q.begin_offer(now)` → send_line_capped OUTSIDE the lock → `with d._lock:
      q.finish_offer(ok)`; `with d._lock: q.ack(obj)` on "applied"; `with d._lock: q.check_deadline(now)` on the
      timer. A stale set after close is harmless (q is None). Only QUEUED enqueues set the event; REVOKED =
      recovery-only (T4.S6 surfaces delivery_failed).
```

### Integration Points

```yaml
STATE:
  - add to: voice_typing/daemon.py __init__ (after :1019)
  - pattern: "_native_recovery (daemon-wide), _native_fence / _native_queue (per native capture), _native_offer_evt, _native_rejects"
ARM:
  - edit: _start_fenced :2816 passes native=native_tok is not None; _arm latches the fence after set_microphone(True)
END:
  - edit: _end_native_locked :2972 calls _native_close_capture_locked (all end causes funnel here)
CONTEXT:
  - edit: _refresh_context_prompt :2297 native source branch (accepted-only accumulator _session_accepted)
NO CHANGES: config, socket, status, state.json shape, ctl.py, recorder_host.py, editor_session.py,
session_recovery.py, media ducking, idle auto-stop/unload, cancel(), run() loop.
```

## Validation Loop

### Level 1: Syntax & Style
```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_native_final_route.py && echo "L1 PASS"
grep -c "Lock()" voice_typing/daemon.py          # == Task-0 count N (no new lock)
grep -n "def _native_open_capture_locked\|def _native_close_capture_locked\|def _native_on_final\|def _native_final_verdict\|def _native_reject_final" voice_typing/daemon.py
grep -n "_native_fence is not None" voice_typing/daemon.py    # >= 5 sites (on_final, _on_partial, note_user_keypress, _refresh, …)
.venv/bin/ruff check voice_typing/daemon.py tests/test_native_final_route.py 2>&1 | tail -3   # if ruff is configured
```

### Level 2: Unit Tests
```bash
PY=.venv/bin/python
timeout 300 "$PY" -m pytest tests/test_native_final_route.py -q                                   # bash timeout 360
timeout 300 "$PY" -m pytest tests/test_editor_offer_queue.py tests/test_editor_session.py tests/test_session_recovery.py tests/test_native_recovery.py -q 2>&1 | tail -2
timeout 500 "$PY" -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40 > /tmp/vt_t4s4_daemon.txt   # bash timeout >= 560; BOUNDED file
# Set-diff rule (tests/G1_BASELINE.md): the FAILED set must EQUAL the Task-0 baseline set — no new reds, no blanket skips.
# If any run returns 124: do NOT retry blindly — see AGENTS.md "Cleanup".
```

### Level 3: Scope & Integration
```bash
git diff --name-only            # == voice_typing/daemon.py, tests/test_native_final_route.py
git diff -- voice_typing/daemon.py | grep -E "^-.*(record_final\(|type_text\(|_handoff_context_prompt\(cleaned\)|open_session\(\)|note_final\()" | wc -l   # expect 0
git diff -- voice_typing/daemon.py | grep -E "^\+.*(subprocess|wl-copy|xclip|pactl|hyprctl|begin_offer|send_line)" | wc -l   # expect 0
git diff -- voice_typing/daemon.py | grep -nE "^\+.*logger\.(info|debug|warning)\(" | wc -l   # small; each new line audited by the caplog test
```

### Level 4: Creative & Domain-Specific Validation
```bash
# Identity interplay with the REAL relay (T4.S3 suite is hermetic — no CUDA):
timeout 120 .venv/bin/python -m pytest tests/test_recorder_identity_boundary.py -q           # bash timeout 180
# Negative proof that no desktop/injection tool is reachable from the native route:
grep -nE "wtype|ydotool|wl-copy|notify-send|hyprctl" voice_typing/daemon.py | grep -n "_native" || echo "L4 PASS: no desktop/injection call in native helpers"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 pass; Success (a)–(j) hold; `tests/test_daemon.py` FAILED set == G1 baseline (set-diff, not count).
- [ ] Reader thread: only `_on_final_lock` + a short `_lock` around `enqueue`; no I/O/wait/join/abort/drain there.
- [ ] `_native_fence is None` ⇒ every generic callback runs today's exact lines (test_generic_session_is_byte_identical).

### Feature Validation
- [ ] Accepted native final: cleaned, retained, queued, wakeup set — zero generic side effects (all tripwires).
- [ ] Missing / non-ACCEPTED / fence-mismatched / filtered / ended finals rejected with lifecycle closed and seed intact.
- [ ] Partials, speech and keypresses are lifecycle-only; `_arm(native=True)` keeps mic, gate, lifecycle feedback, ducking.
- [ ] Rolling context for native comes only from this session's accepted finals (seeded and unseeded).

### Code Quality Validation
- [ ] Helpers placed with the other native helpers; names exactly as specified; no new pattern invented.
- [ ] No edits outside the two files; recorder_host/editor_session/session_recovery untouched.
- [ ] [Mode A] docstrings: on_final native-route paragraph, sibling one-liners, CONSUMER CONTRACT verbatim.

### Documentation & Deployment
- [ ] No new config keys or environment variables. Logs carry codes/counts/ids only.

---

## Anti-Patterns to Avoid

- ❌ Putting the native branch after `textproc.clean` or inside the generic commit — it must precede ALL generic output.
- ❌ Latching the fence from the first final, from `self._arm_seq`, or before `set_microphone(True)` bumps the host.
- ❌ Calling `begin_offer`, writing to the socket, `set_prompt` under `_lock`, or aborting/draining on the reader.
- ❌ Letting a rejected final consume the seed, or leaving `_final_pending` set so a drain waits forever.
- ❌ Skipping the lifecycle stores, the idle clock, ducking, or `feedback.set_listening` for native ("bypass everything").
- ❌ Retaining a late final after the session ended; forgetting `q.close()` at end.
- ❌ Sourcing the native rolling prompt from `StreamingOutput.committed` (never fed in native sessions).
- ❌ Implementing stop/cancel/drain policy, `ended`, `end_session`, or socket activation — T4.S5/S6/S7 own them.
- ❌ Logging recognition or seed text; un-timed pytest; foregrounding the daemon; editing read-only files.

## Confidence Score
**8/10** — the insertion line, every bypassed branch, the on-disk eligibility contract, the arm-commit lock hold and
the rolling-context gap are verified against source at `cc203ce`, with a verbatim test list and G1 set-diff gate.
Residuals: `_end_native_locked`'s exact body (:2972-3010) and the harness-import precedent are left to Task 0 to
confirm rather than assumed; the T4.S5 drain narrowing is deliberately a documented seam, not implemented here.

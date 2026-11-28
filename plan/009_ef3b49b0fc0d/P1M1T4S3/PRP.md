# PRP — P1.M1.T4.S3: Make recorder identity safe at capture boundaries

## Goal

**Feature Goal**: Harden the recorder relay's identity seam in `voice_typing/recorder_host.py` so a
native consumer can always tell, for the event being relayed RIGHT NOW, **which host, which arm, which
session and which utterance it belongs to — and whether it is a fresh final, a sentinel, a cancel
sentinel, an unidentified legacy event, a duplicate or a stale straggler** — and can read the current
in-flight capture boundary explicitly. Close five verified defects (D1–D5 below) without changing what
legacy id-less events do, without moving `_final_evt.set()` (still after the callback), and without
adding any lock or wait on the reader thread.

**Deliverable** (1 module modified additively, 1 new test file; `daemon.py` untouched):
1. `voice_typing/recorder_host.py` — ADD `FinalClass`, `_RelayEvent`, `_CaptureBoundary`; properties
   `generation`, `arm_seq`, `relay_event`, `capture_boundary`; cold-host reset at `"ready"`; per-reader
   generation fence; identity cleared on id-less events; `arm_seq` bump in `set_microphone(True)`;
   stamped `speech` payload via a new module-level `_emit_speech`; [Mode A] docstrings.
2. `tests/test_recorder_identity_boundary.py` — hermetic tests over fake child queues and race gates
   (no media, no model, no device, no daemon).

**Success Definition**:
- (a) Inside `on_final`/`_on_partial`/`_on_speech`, `host.relay_event` reports the identity of THAT
  event; an id-less event reports `(None, None)` — never the previous event's identity.
- (b) Stale, duplicate, sentinel, cancelled and unidentified finals are mutually distinguishable via
  `FinalClass`; duplicates/stale never reach `on_final` yet still unblock `text()`.
- (c) A cold (re-spawned) host's tracker is reset at `"ready"`; the previous child's `session_gen`
  can neither drop nor advance the new child's events; an old reader's straggler is fenced by its
  captured generation.
- (d) `arm_seq` bumps exactly once per arm, is latched per session, and a previous arm's straggler
  keeps the previous `arm_seq` in its `relay_event`.
- (e) `capture_boundary` opens at the identified `speech` event and closes at every final path
  (accepted / sentinel / cancelled / filtered / dropped).
- (f) `relay_identity` stays a 2-field NamedTuple; `tests/test_recorder_host.py` is green unchanged.
- (g) `timeout 600 .venv/bin/python -m pytest tests/test_recorder_identity_boundary.py tests/test_recorder_host.py -q` → all green.
- (h) `git diff --name-only` == `{voice_typing/recorder_host.py, tests/test_recorder_identity_boundary.py}`.

## User Persona

**Target User**: the dictation user in a native editor (Pi prompt, Neovim) — via the T4.S4/T4.S5
consumers this task feeds.
**Use Case**: Stop mid-utterance, cancel, re-arm, or a host respawn (mode switch / idle-unload → reload /
dead-host recovery) while finals and partials are still in flight on the recorder IPC.
**Pain Points Addressed**: a previous utterance's or previous host's final being attributed to the
current native session; an in-flight utterance invisible at Stop time; a re-spawned host whose events
are all silently dropped.

## Why

- PRD §4.2sexies R.5: "utterance identities assigned at the decode source and carried through
  `recorder_host`'s event relay (a late event keeps its own identity, never relabeled as newer)";
  "Discard late post-final partials, duplicate finals, and canceled-utterance events; a dropped or
  filtered final still closes its utterance boundary."
- `architecture/system_context.md` ("Control/recorder boundaries"): "`relay_identity` is meaningful
  inside the callback only, and currently remains latched through an id-less event because assignment
  is conditional. Repair the per-event boundary … Drive drain from explicit host arm generation and a
  current in-flight identity/capture boundary; don't infer it from first final, guessed counter across
  host respawns, or the last arbitrary partial."
- T4.S2's `OfferQueue` settles *delivery*; T4.S3 is the recorder-side half that tells T4.S4 which
  final is eligible to enqueue and T4.S5 which single utterance may land during a drain.

## What

### Success Criteria
- [ ] New surface: `FinalClass`, `_RelayEvent`, `_CaptureBoundary`, `host.generation`, `host.arm_seq`,
      `host.relay_event`, `host.capture_boundary`, `_emit_speech(evt_q, ids)`.
- [ ] D1–D5 closed per the rules in Implementation Blueprint; (a)–(h) hold.
- [ ] Reader thread adds no lock/wait; `text()` unblocks on every final path as today.
- [ ] Legacy id-less events relay exactly as today (same callbacks, same order), reporting `(None, None)`.

## All Needed Context

### Context Completeness Check
_Pass._ Every touched line range, the existing rules, the test harness helpers, the defects, the new
data shapes, the dispatch rules per event kind, the consumer contract and a verbatim test list are
given below. The implementer needs only this PRP plus `recorder_host.py` :60-100, :286-352, :420-425,
:652-815, :920-936, :1229-1281.

### Documentation & References

```yaml
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S3/research/relay_identity_boundary.md
  why: "§1 ground-truth table with line numbers; §2 defects D1–D5; §3 design; §4 consumer contract."
  critical: "D2/D3 are the 'cold host' rules: the tracker resets ONLY on the reader thread at 'ready',
            and each reader thread captures its generation at entry and drops mismatched events."
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Control/recorder boundaries' — the relay/identity paragraph is this task's spec."
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S2/PRP.md
  why: "Contract consumed downstream: OfferQueue.enqueue is what T4.S4 calls for an ELIGIBLE final;
        this task decides eligibility data, it does NOT enqueue, route, drain or touch daemon.py."
- file: voice_typing/recorder_host.py
  why: "The only module edited. Identity contract docstring :73-88; state init :299-315; relay_identity
        :344-352; spawn bump :386; set_microphone :420-425; _read_loop :652-675; _ids_settle :676-690;
        _dispatch :692-815; child _child_on_speech :928-935; _RelayIdentity/_RelayIds/_with_identity
        :1229-1281; _RelayFeedback :1835."
  pattern: "Reader-thread-only state (G6) + immutable NamedTuple snapshots assigned by reference
            (relay_identity precedent). ADDITIVE keys only ('cancelled', 'context_prompt' precedents)."
  gotcha: "Do NOT change _RelayIdentity's shape (2-tuple equality is asserted at tests:878-905). Do NOT
           add a lock on the reader. Do NOT set _final_evt BEFORE on_final."
- file: tests/test_recorder_host.py
  why: "Harness to reuse verbatim: _FakeFeedback :33, _FakeLatency :47, _make_host(...) :61-76,
        _feed_event(host, kind, payload) :78-82; identity tests :878-1033 are the behavioral oracle."
  pattern: "Call host._dispatch(kind, payload) directly (no thread) for rule tests; _feed_event +
        host._read_loop in a thread for queue/reader tests; threading.Event gates for races."
- file: plan/009_ef3b49b0fc0d/P1M1T3S4/PRP.md
  why: "NativeReservation (editor_session.py :63-115) — the native session's arm fence that T4.S4
        combines with this task's (host_generation, arm_seq). READ ONLY here."

CONSUMER CONTRACT (hand to T4.S4 / T4.S5 — document it in the module docstring):
  T4.S4, inside on_final (reader thread):
      ev = host.relay_event
      eligible = (ev is not None and ev.kind == "final"
                  and ev.final_class is FinalClass.ACCEPTED and ev.arm_seq > 0
                  and (ev.host_generation, ev.arm_seq) == session_arm_fence)
  T4.S5, at Stop (control thread) and during the drain:
      b = host.capture_boundary          # whole value; may be <=1 event superseded
      nothing_eligible = b is None or b.utterance_id is None or b.arm_seq == 0
      accept_during_drain = eligible and (ev.host_generation, ev.arm_seq, ev.session_gen,
                                          ev.utterance_id) == b
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/recorder_host.py          # relay identity seam + _dispatch + child stamper    ← EDIT (additive)
tests/test_recorder_host.py            # oracle — do NOT edit
tests/test_recorder_identity_boundary.py                                                            ← CREATE
voice_typing/daemon.py                 # ZERO consumers today — do NOT edit
voice_typing/editor_session.py         # T3.S4 reservation + T4.S2 OfferQueue — READ ONLY
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
voice_typing/recorder_host.py
  + FinalClass (str-enum, 6 members)         — what a relayed/dropped final IS
  + _RelayEvent (NamedTuple, 6 fields)       — identity + class of the event being relayed NOW
  + _CaptureBoundary (NamedTuple, 4 fields)  — current in-flight (host arm, session, utterance)
  + RecorderHost.generation / arm_seq / relay_event / capture_boundary (properties)
  + RecorderHost._arm_seq, _boundary_arm_seq, _ids_open_gen, _relay_event, _capture_boundary
  + RecorderHost._resolve_identity(uid, gen) -> str   ("accept"|"stale"|"duplicate"|"legacy")
  + _emit_speech(evt_q, ids)                 — module-level; the child's stamped speech put
tests/test_recorder_identity_boundary.py     — rules D1–D5 + text() unblock + reader ordering
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — READER THREAD OWNS THE TRACKER (G6). _ids_*, _relay_identity, _relay_event,
# _capture_boundary, _boundary_arm_seq are written ONLY inside _dispatch. Reset them at "ready"
# (the reader thread), NEVER in spawn()/stop() (the spawner thread).
# CRITICAL #2 — PER-READER GENERATION. _read_loop captures gen = self._generation AT ENTRY (spawn()
# bumps BEFORE starting the reader, :386/:392) and calls self._dispatch(kind, payload, generation=gen).
# _dispatch(self, kind, payload, generation=None) keeps the 2-arg call working (30+ test call sites).
# An event whose generation != self._generation is dropped (DEBUG, counts only) — no tracker change,
# NO _final_evt.set().
# CRITICAL #3 — ORDER IS LOAD-BEARING in the final branch: identity handling -> _cancel_mark ->
# on_final -> _final_evt.set(). Dropped stale/duplicate: set _final_evt and return WITHOUT touching
# _cancel_mark (G3/G5, pinned by tests :914-930).
# CRITICAL #4 — arm_seq bumps BEFORE the cmd put in set_microphone(True) (happens-before: bump -> put
# -> child 'arm' -> new_session() -> first stamped event -> reader latches). set_microphone(False)
# does NOT bump.
# CRITICAL #5 — LATCH, DON'T RE-READ: the reader latches _boundary_arm_seq = self._arm_seq ONLY when
# the session ADVANCES (gen > _ids_latest_session, incl. the first event after "ready"). Same-session
# events reuse the latch, so a previous arm's straggler keeps the previous arm_seq.
# CRITICAL #6 — LEGACY IS PRESERVED: an id-less final/partial/speech still relays to the same callback
# in the same order; it just reports (None, None) and never moves the boundary or the tracker.
# CRITICAL #7 — tests/test_recorder_host.py LOADS REAL CUDA MODELS in places (AGENTS.md): run it under
# `timeout 600` with the bash-tool timeout above; never foreground the daemon; .venv/bin/python.
# CRITICAL #8 — DO NOT EDIT daemon.py, editor_session.py, editor_protocol.py, session_recovery.py,
# tests/test_recorder_host.py, any plan file, PRD.md, tasks.json, README.
```

## Implementation Blueprint

### Data models and structure

```python
class FinalClass(str, enum.Enum):
    ACCEPTED = "accepted"        # identified, non-empty, not cancelled — the ONLY class native may enqueue
    SENTINEL = "sentinel"        # text == "" unblock signal (plain abort / shutdown)
    CANCELLED = "cancelled"      # payload["cancelled"] truthy (Backspace-cancel / voicectl cancel)
    UNIDENTIFIED = "legacy"      # id-less payload (pre-upgrade child / test double) — relayed, never eligible
    DUPLICATE = "duplicate"      # uid already settled -> dropped before on_final (relay_event still reports it)
    STALE = "stale"              # session_gen < latest -> dropped before on_final (relay_event still reports it)

class _RelayEvent(NamedTuple):
    kind: str                          # "final" | "partial" | "speech"
    final_class: "FinalClass | None"   # None for partial/speech
    host_generation: int               # the reader's captured generation (child lifetime fence)
    arm_seq: int                       # latched host arm generation of this event's session (0 = never armed)
    session_gen: "int | None"
    utterance_id: "int | None"

class _CaptureBoundary(NamedTuple):
    host_generation: int
    arm_seq: int
    session_gen: "int | None"
    utterance_id: "int | None"         # None = no utterance in flight (closed by a final / reset)
```

```python
# __init__ additions (next to :311-315): all reader-thread-only except _arm_seq (control thread, int)
self._arm_seq = 0                      # bumped in set_microphone(True) — BEFORE the cmd put
self._boundary_arm_seq = 0             # reader latches self._arm_seq at session advance
self._ids_open_gen: "int | None" = None
self._relay_event: "_RelayEvent | None" = None
self._capture_boundary: "_CaptureBoundary | None" = None
```

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT (read-only): confirm `grep -n "_ids_latest_session" voice_typing/recorder_host.py`
        shows assignments ONLY at :311 and :729/:767 (no reset in spawn/stop); confirm `grep -n
        "relay_identity\|_generation" voice_typing/daemon.py` is empty; run the identity oracle once:
        `timeout 600 .venv/bin/python -m pytest tests/test_recorder_host.py -q -k "identity or dispatch
        or relay or sentinel or legacy or arm"` (record pass count; it must be identical after Task 3).

Task 1: CREATE tests/test_recorder_identity_boundary.py (RED first). Reuse the harness shape from
        tests/test_recorder_host.py :33-82 (copy the three tiny helpers; do NOT import the test module).
        All tests: fake queues + threading.Event gates, bounded joins (timeout=2.0), zero sleeps.
  - test_idless_event_clears_identity_and_reports_unidentified — id'd final (uid 7, gen 2) then
    id-less final: inside the 2nd callback relay_identity == (None, None) and
    relay_event == ("final", FinalClass.UNIDENTIFIED, host.generation, host.arm_seq, None, None);
    same for an id-less partial after an id'd partial. (D1)
  - test_final_classes_are_distinguishable — five hosts; feed: (uid 1,"hi",gen 1) -> ACCEPTED;
    (uid 1,"",gen 1) after rotate... use fresh hosts: text "" -> SENTINEL; cancelled True -> CANCELLED;
    no uid -> UNIDENTIFIED; repeat uid -> on_final NOT called, _final_evt set, relay_event.final_class
    is DUPLICATE; gen 0 after gen 1 -> not called, _final_evt set, STALE. (b)
  - test_cold_host_ready_resets_tracker — relay gen 5 / uid 9 final (settled=[9], latest=5);
    _dispatch("ready", {"device":"cpu"}) -> latest -1, settled empty, _ids_open None, relay_identity
    (None, None), relay_event None, capture_boundary None; then (uid 1, gen 1) final IS relayed. (D2)
  - test_previous_generation_events_are_fenced — host.generation is 0 in tests; emulate a respawn:
    _dispatch("ready", {}, generation=1) then an identified partial (gen 3, uid 4, generation=1) ->
    relayed with relay_event.host_generation == 1; now "respawn": set host._generation = 2 (test-only
    poke), _dispatch("ready", {}, generation=2); an OLD-reader straggler (gen 9, uid 9, generation=1)
    -> _on_partial NOT called, _ids_latest_session stays -1 (not advanced to 9), _final_evt NOT set;
    a new-reader partial (gen 1, uid 1, generation=2) -> relayed, boundary.host_generation == 2. (D3)
  - test_arm_seq_bumps_once_per_arm_and_latches_per_session — arm_seq == 0; set_microphone(False) ->
    still 0; set_microphone(True) -> 1; identified speech (gen 1, uid 1) -> relay_event.arm_seq 1,
    capture_boundary.arm_seq 1; set_microphone(True) again -> 2 (re-arm); OLD-session partial (gen 1,
    uid 1) -> relay_event.arm_seq == 1 (latch kept) ; NEW-session speech (gen 2, uid 2) ->
    relay_event.arm_seq == 2 and capture_boundary.arm_seq == 2. (D5)
  - test_boundary_opens_at_speech_and_closes_on_every_final_path — four hosts: (i) speech (gen 2,
    uid 3) -> capture_boundary == (G, A, 2, 3), _ids_open == 3, relay_identity == (2, 3); final uid 3
    -> (G, A, 2, None). (ii) sentinel final closes. (iii) on_final raising (filtered) still closes.
    (iv) duplicate final leaves it closed and sets _final_evt. Id-less partial never moves it. (D4, e)
  - test_emit_speech_is_stamped_and_legacy_default — ids = _RelayIds(); _emit_speech(q, ids) puts
    ("speech", {"utterance_id": 1, "session_gen": 0}); second call -> utterance_id 2;
    _emit_speech(q, None) puts ("speech", {}) byte-identical to today. (D4)
  - test_text_unblocks_on_dropped_duplicate_without_callback — settle uid 1 via _dispatch; thread:
    host.text(cb); wait until host._on_final is cb (poll with monotonic deadline 1 s, no sleep) —
    simpler: call host.text(cb) in a thread, _feed_event a duplicate (uid 1); join(2.0) -> not alive,
    cb never called. (reader responsiveness / VT-007)
  - test_final_evt_set_after_callback_not_before — on_final blocks on a gate Event; thread runs
    host._read_loop with _feed_event(final uid 1, gen 1); poll until the callback entered (Event
    "entered"); assert NOT host._final_evt.is_set(); gate.set(); join(2.0); assert _final_evt.is_set().
    (preserves the :744-745 ordering)
  - test_legacy_events_relay_unchanged_in_order — id-less final then id-less partial: on_final and
    _on_partial each called once with the text, in order; relay_identity (None, None) both times;
    tracker untouched. (f)
  RUN: timeout 120 .venv/bin/python -m pytest tests/test_recorder_identity_boundary.py -q -> RED.

Task 2: EDIT voice_typing/recorder_host.py — data shapes + state (Blueprint "Data models"): add
        FinalClass, _RelayEvent, _CaptureBoundary after _RelayIdentity (:1240); add the five __init__
        fields after :315.

Task 3: EDIT voice_typing/recorder_host.py — behavior:
  a) set_microphone (:420-425): `if on: self._arm_seq += 1` as the FIRST statement (before the put).
  b) _read_loop (:652): `generation = self._generation` before the loop; `self._dispatch(kind,
     payload, generation=generation)`.
  c) _dispatch signature: `(self, kind: str, payload: dict, generation: "int | None" = None)`;
     first line: `gen_host = self._generation if generation is None else generation`;
     if `gen_host != self._generation` and kind in ("final","partial","speech","vad","speech_end"):
     logger.debug(counts only) + return. ("ready"/"error"/"prime_ack" are exempt — spawn() waits on
     ready and _dispatch("ready") must still run when tests call it 2-arg.)
  d) "ready" branch (:693-701): ADD the cold-host reset (Critical #1): _ids_latest_session=-1,
     _ids_settled.clear(), _ids_settled_set.clear(), _ids_open=None, _ids_open_gen=None,
     _boundary_arm_seq=0, _relay_identity=(None,None), _relay_event=None, _capture_boundary=None.
  e) ADD `_resolve_identity(self, uid, gen) -> str` (reader thread): returns "legacy" if uid is None
     (no tracker change); "stale" if isinstance(gen,int) and gen < _ids_latest_session; "duplicate"
     if uid in _ids_settled_set; else "accept" — and on accept, if gen > _ids_latest_session:
     _ids_latest_session=gen, clear settled + set, _boundary_arm_seq=self._arm_seq. Return the string.
     This is the EXISTING logic (:716-731, :753-768) factored once; the oracle tests are the proof.
  f) "final" branch (:710-745): v = _resolve_identity(uid, gen). If v in ("stale","duplicate"):
     self._relay_event = _RelayEvent("final", FinalClass(v.upper()), gen_host, self._boundary_arm_seq,
     gen, uid); self._final_evt.set(); return (same debug lines as today). Else: if v=="accept":
     _ids_settle(uid); _ids_open=None; _ids_open_gen=None; self._capture_boundary =
     _CaptureBoundary(gen_host, _boundary_arm_seq, gen, None); self._relay_identity =
     _RelayIdentity(gen, uid).  else (legacy): self._relay_identity = _RelayIdentity(None, None).
     cls = CANCELLED if payload.get("cancelled") else SENTINEL if text == "" else UNIDENTIFIED if
     v=="legacy" else ACCEPTED.  self._relay_event = _RelayEvent("final", cls, gen_host,
     self._boundary_arm_seq if v=="accept" else self._arm_seq, gen if v=="accept" else None,
     uid if v=="accept" else None).  Then the UNCHANGED tail: _cancel_mark, on_final (try/except),
     _final_evt.set().
  g) "partial" branch (:748-771): v = _resolve_identity(...). stale/duplicate -> log + return
     (ALSO set _relay_event with the drop class; NO _final_evt — unchanged). accept -> _ids_open=uid;
     _ids_open_gen=gen; _capture_boundary=(gen_host, _boundary_arm_seq, gen, uid); _relay_identity=
     (gen, uid); _relay_event=("partial", None, gen_host, _boundary_arm_seq, gen, uid). legacy ->
     _relay_identity=(None,None); _relay_event=("partial", None, gen_host, self._arm_seq, None,
     None). Then the UNCHANGED self._on_partial(text).
  h) "speech" branch (:773): uid/gen = payload.get(...); v = _resolve_identity(uid, gen) — for
     speech, "duplicate" cannot occur (rotation) but keep the shared rule; on accept: _ids_open=uid;
     _ids_open_gen=gen; _capture_boundary=(gen_host, _boundary_arm_seq, gen, uid); _relay_identity=
     (gen, uid); _relay_event=("speech", None, gen_host, _boundary_arm_seq, gen, uid). On legacy
     (uid None): _relay_identity=(None,None); _relay_event=("speech", None, gen_host, self._arm_seq,
     None, None). On stale: same as legacy reporting (do not advance). ALWAYS: self._on_speech()
     (legacy behavior preserved — _touch_speech must keep firing for every speech event).
  i) child (:928-935): replace the body of _child_on_speech with `_emit_speech(evt_q, ids)`; add
     module-level `def _emit_speech(evt_q, ids): ids.rotate_utterance() if ids is not None else None;
     _safe_put(evt_q, ("speech", _with_identity({}, ids)))` — note _with_identity returns the SAME
     dict stamped; with ids=None it is `{}`. Update the comment ("the speech payload now carries the
     rotated id — the boundary opens at the decode source").
  j) Properties (next to relay_identity :344): generation -> self._generation; arm_seq -> self._arm_seq;
     relay_event -> self._relay_event; capture_boundary -> self._capture_boundary.

Task 4: EDIT the module docstring [Mode A] (:73-88 "IDENTITY" paragraph) + the callback-scope
        docstrings (relay_identity :345-351, text() :572-577, _dispatch final/partial comments,
        _RelayIdentity :1230-1236): one paragraph covering (1) per-event identity incl. (None, None)
        for id-less events; (2) FinalClass + the drop-before-callback rule; (3) the cold-host reset at
        "ready" + per-reader generation fence; (4) arm_seq latch rule; (5) capture_boundary open/close
        rules and the "whole, <=1 event superseded off-reader" caveat; (6) the CONSUMER CONTRACT block
        verbatim. Update the "six final/partial event sites" comment (:933, :1276) to "seven … sites
        (speech included)".

Task 5: VERIFY: Task-1 file green; the Task-0 oracle subset green with the SAME count; then Success (g).
Task 6: VALIDATE L1–L3. Commit only if the orchestrator directs.
```

### Implementation Patterns & Key Details

```python
# PATTERN — the reader thread is the ONLY writer; snapshots are immutable and assigned by reference:
def _resolve_identity(self, uid, gen) -> str:          # reader thread; returns the verdict
    if uid is None:
        return "legacy"                                # no tracker change (G7)
    if isinstance(gen, int) and gen < self._ids_latest_session:
        return "stale"
    if uid in self._ids_settled_set:
        return "duplicate"
    if isinstance(gen, int) and gen > self._ids_latest_session:   # session ADVANCE == a new arm
        self._ids_latest_session = gen
        self._ids_settled.clear(); self._ids_settled_set.clear()
        self._boundary_arm_seq = self._arm_seq          # LATCH here, nowhere else
    return "accept"

# GOTCHA — final class precedence is cancelled > sentinel > unidentified > accepted:
cls = (FinalClass.CANCELLED if payload.get("cancelled")
       else FinalClass.SENTINEL if text == ""
       else FinalClass.UNIDENTIFIED if verdict == "legacy"
       else FinalClass.ACCEPTED)
# GOTCHA — a final's relay_event uses the session's LATCHED arm_seq; a legacy event uses the current
# self._arm_seq (best effort; it is never eligible anyway because utterance_id is None).
```

### Integration Points

```yaml
CONSUMED BY:
  P1.M1.T4.S4 (route native finals): reads host.relay_event INSIDE on_final; only FinalClass.ACCEPTED
    with (host_generation, arm_seq) == the session's arm fence may reach OfferQueue.enqueue.
  P1.M1.T4.S5 (stop/cancel/drain): snapshots host.capture_boundary at Stop; accepts during the drain
    iff ACCEPTED and the event's (generation, arm_seq, session_gen, utterance_id) == the snapshot.
  P1.M1.T4.S6 (ended cause): FinalClass/relay_event give fixed codes for "what landed last".
NO CHANGES: daemon.py, editor_session.py, editor_protocol.py, session_recovery.py, config, socket,
status, state.json, logging text (DEBUG lines carry ids/counts only — never seed or final text).
```

## Validation Loop

### Level 1: Static
```bash
cd /home/dustin/projects/voice-typing
grep -nE "^class FinalClass|^class _RelayEvent|^class _CaptureBoundary|^def _emit_speech" voice_typing/recorder_host.py
grep -n "def generation\|def arm_seq\|def relay_event\|def capture_boundary" voice_typing/recorder_host.py
grep -c "Lock()" voice_typing/recorder_host.py            # must equal the pre-edit count (no new lock)
.venv/bin/python -m py_compile voice_typing/recorder_host.py && echo "L1 PASS"
```
### Level 2: Tests
```bash
PY=.venv/bin/python
timeout 120 "$PY" -m pytest tests/test_recorder_identity_boundary.py -q
timeout 600 "$PY" -m pytest tests/test_recorder_host.py -q -k "identity or dispatch or relay or sentinel or legacy or arm" 2>&1 | tail -2
timeout 600 "$PY" -m pytest tests/test_recorder_identity_boundary.py tests/test_recorder_host.py -q 2>&1 | tail -2
# bash-tool timeout >= 660 for the last two (AGENTS.md: this suite loads real CUDA models).
# If a run returns 124: do NOT retry blindly — see AGENTS.md "Cleanup".
```
### Level 3: Scope
```bash
git diff --name-only            # == voice_typing/recorder_host.py, tests/test_recorder_identity_boundary.py
git diff -- voice_typing/recorder_host.py | grep -c "^-"   # only replaced comment lines / the factored rules
git diff -- voice_typing/recorder_host.py | grep -E "^-.*(_final_evt\.set\(\)|_on_final\(|self\._on_partial\(|self\._on_speech\(\))" | wc -l   # expect 0 removed calls
```

## Final Validation Checklist
- [ ] L1–L3 pass; Success (a)–(h) hold; Task-0 oracle count unchanged.
- [ ] Reader thread: no new lock, no wait/join; `_final_evt.set()` still AFTER `on_final`; drops still set it.
- [ ] Legacy id-less final/partial/speech relay exactly as before (same callbacks, same order).
- [ ] `relay_identity` 2-field unchanged; all new names are additive; `__all__` unchanged (module has none → leave).
- [ ] Mode A docstrings updated: identity paragraph, callback-scope docs, "seven sites", consumer contract.
- [ ] No seed/final text in any new log line; no edits outside the two files.

## Anti-Patterns to Avoid
- ❌ Resetting the tracker in `spawn()`/`stop()` (spawner thread) instead of at `"ready"` (reader thread).
- ❌ Re-reading `self._arm_seq` for same-session events (breaks the previous-arm straggler rule).
- ❌ Changing `_RelayIdentity` to 3+ fields, or renaming/removing the additive `utterance_id`/`session_gen`/`cancelled` keys.
- ❌ Dropping a stale/duplicate final WITHOUT `_final_evt.set()` (strands `text()` — VT-007).
- ❌ Relaying stale/duplicate finals to `on_final` so native can "see" them (legacy acceptance changes).
- ❌ Setting `_final_evt` before the callback, or adding a reader-side wait/lock.
- ❌ Enqueueing, routing, draining, or editing `daemon.py` — that is T4.S4/T4.S5.
- ❌ Untimed pytest; foregrounding the daemon; editing `tests/test_recorder_host.py`.

## Confidence Score
**9/10** — every touched line range, rule, ordering constraint and test harness helper is pinned with
line numbers; D1–D5 are verified against source, and the existing identity tests are a hard oracle for
the factored `_resolve_identity`. The one residual: `tests/test_recorder_host.py` loads real CUDA
models (slow/flaky under VRAM contention), mitigated by the fast `-k` oracle subset in Task 0/Level 2.

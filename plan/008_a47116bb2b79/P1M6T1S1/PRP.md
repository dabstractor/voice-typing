# PRP — P1.M6.T1.S1: Payload helper at the five final sites + partial site (utterance_id + session_gen through the relay)

## Goal

**Feature Goal**: Extend `recorder_host.py`'s child→daemon event relay (PRD §4.2sexies **R.5**) so
every `final`/`partial` event carries **`utterance_id` + `session_gen`** identity: the child assigns
ids **at the decode source** (a late event keeps its own identity, never relabeled as newer;
session generation bumps at every arm), and the daemon-side `_dispatch` choke point consumes them
additively — **discarding late post-final partials, duplicate finals, and canceled/cross-session
stragglers, while a dropped or filtered final still closes its utterance boundary**. Stream-edit
behavior on the happy path is bit-identical; `RecorderHost.text()`, the daemon run loop, and the
arm/disarm audio purges need NO change. This is the relay plumbing P1.M6.T2.S1 (dispatch wiring +
bulk cancel intercept) consumes.

**Deliverable** (2 files — 1 MODIFY source, 1 MODIFY tests; adds-only within them, the plan's house rule):
1. `voice_typing/recorder_host.py` — (a) ONE payload helper `_with_identity(payload, ids) -> dict`
   wrapping ALL SIX put sites (five `final` + one `partial`); (b) child-side `_RelayIds` stamper
   (lock-guarded `utterance`/`session` counters); (c) daemon-side identity tracker + discard rules in
   `_dispatch` + a `relay_identity` accessor (the T2.S1 seam); (d) protocol docstring update (Mode A).
2. `tests/test_recorder_host.py` — new tests using the EXISTING doubles (direct `host._dispatch(...)`
   style + `_AbortFakeRecorder`/`_NormalFakeRecorder` + a `_RelayIds` unit layer).

**Success Definition**:
- (a) All six sites route through the ONE helper; the keys are **additive** (`cancelled` at
  `:439-441` and `ready`'s `context_prompt` at `:864-873` are the precedents — never rename/remove).
- (b) **Id semantics**: consecutive utterances get distinct ids (rotation at `_child_on_speech`,
  the decode-source boundary); partials and their final share the id; sentinels settle the current
  id; a late partial arriving after its final keeps the OLD id (speech-start rotation is what makes
  "never relabeled" hold — see Gotcha G2).
- (c) **Session semantics**: every `arm` command bumps `session_gen`; events carry the gen current
  at decode; the daemon drops events with an older gen than the latest seen and clears settled ids
  on session advance.
- (d) **Daemon discard rules at `_dispatch`** (single choke point): late post-final partial →
  dropped (not relayed to `_on_partial`); duplicate final → `_on_final` NOT called but `_final_evt`
  STILL set (the `host.text()` unblock invariant, VT-007); every relayed final-kind event settles
  its id BEFORE the downstream `on_final` runs — so a dropped/filtered final (clean() rejection,
  cancel suppression) still closes the boundary. The `_cancel_mark` flow is unchanged.
- (e) **Backward compat / no stream-edit change**: payloads WITHOUT `utterance_id` dispatch
  byte-identically to today (no tracking, no discards) — every existing test double and the
  4-arg `_run_text_and_emit_final` call sites stay green untouched.
- (f) `relay_identity` exposes the (session_gen, utterance_id) of the event being relayed — the
  documented seam T2.S1 reads inside the daemon callbacks (they run ON the reader thread).
- (g) Mode A: the `:27-78` protocol docstring documents the new keys + the discard rules.
- (h) **Out of scope**: `daemon.py` (T2.S1 owns wiring/cancel-intercept), `bulk_delivery.py` /
   `streaming.py` / `typing_backends.py` (untouchable per map §3), config keys, `RecorderHost.text()`.

## User Persona

**Target User**: internal — three consumers:
1. **P1.M6.T2.S1 (dispatch wiring + bulk cancel intercept)** — the direct consumer: it reads
   `host.relay_identity` inside the daemon's `on_final`/`_on_partial` callbacks to associate bulk
   `show()` operations with utterances and sessions, and relies on the discard rules so the bulk
   controller never sees stale events.
2. **P1.M6.T2.S2 (session recovery)** — uses `session_gen` to delimit arm→disarm sessions.
3. **Future maintainers** — the protocol docstring is the contract for the IPC payload shape.

**Use Case**: armed dictation under `output.delivery="bulk-text"`: partial i for utterance 7 →
bulk controller revises utterance 7's span; final for 7 → commit + boundary closes; a late partial
for 7 (realtime thread straggler) arrives → `_dispatch` drops it before any consumer sees it; user
Backspace-cancels → cancelled sentinel settles 7 → stragglers dropped; re-arm → session_gen bumps →
any pre-re-arm straggler is dropped by generation. In stream-edit mode the identity flows but only
the pathological-event suppression differs — normal flows are unchanged.

**Pain Points Addressed**: (1) R.5 requires utterance identities "assigned at the decode source and
carried through the relay" — today's payloads are identity-free, so the bulk controller cannot
associate revisions with utterances or detect staleness. (2) Late realtime partials after a final
currently reach `StreamingOutput.on_partial` and can rewind the committed tail with stale text (the
stale-tail bug class). (3) Cross-arm stragglers from a disarmed session can leak into the next.

## Why

- **R.5 is the ordering backbone of bulk delivery**: "New session generation at every arm; utterance
  identities assigned at the decode source and carried through recorder_host's event relay… Discard
  late post-final partials, duplicate finals, and canceled-utterance events; a dropped or filtered
  final still closes its utterance boundary." Without this item T2.S1 has nothing to wire.
- **The relay already has the seams** (map §1): all five `final` puts are the only construction
  sites; `_dispatch` is the single daemon choke point; additive-key consumption is twice-precedented;
  the child's per-utterance lifecycle (`aborted`/`cancelled`/`text_running`, `:631-643`) is the
  piggyback. Least-disruption: one helper + one stamper + tracker state.
- **The discard rules are a correctness fix that also protects stream-edit**: they only suppress
  events that are pathological today (late/duplicate/cross-session), which is why "no behavior
  change to stream-edit" and "daemon discards…" reconcile — the happy path is bit-identical and the
  existing suite is the gate.
- **Identity at the choke point, not in the callbacks**: keeping `_on_final(text)`/`_on_partial(text)`
  signatures unchanged means zero daemon.py edits in THIS item; T2.S1 opts in via the accessor.

## What

Three additive layers in `recorder_host.py` + docstring + tests. Exact code below.

### Success Criteria

- [ ] One helper `_with_identity` used by all six sites (`:644`, `:742`, `:745`, `:1052`, `:1054`, `:1100`).
- [ ] `_RelayIds`: lock-guarded; `rotate_utterance()` wired at `_child_on_speech`; `new_session()`
      wired in the `arm` cmd branch; `stamp()` capture-at-entry.
- [ ] `_dispatch` discards late post-final partials + duplicate finals + older-session events;
      settles every relayed final-kind id; `_final_evt` set on EVERY final-kind event (discarded or not).
- [ ] `_cancel_mark` consumption + sentinel relay flow unchanged; VAD stale-drop unchanged.
- [ ] Id-less payloads → byte-identical legacy dispatch (existing doubles untouched and green).
- [ ] `relay_identity` accessor present + documented as the T2.S1 seam.
- [ ] Protocol docstring (Mode A) documents `utterance_id`/`session_gen` + the discard rules.
- [ ] Existing suite green; new tests cover: rotation, shared-id, late-partial drop, duplicate-final
      drop + `_final_evt` still set, cancel-sentinel settle + straggler drop, session bump + cross-session
      drop + settled-clear, boundary-closes-on-filtered-final, id-less legacy path, helper unit.
- [ ] No daemon.py / bulk_delivery.py / streaming.py / typing_backends.py / config edits.

## All Needed Context

### Context Completeness Check

_Pass._ The exact recipe (map §1, verified against live code), the full reference implementation
(helper + stamper + tracker + the six edited sites + `_dispatch` branches), the design rationale for
the one subtle decision (speech-start rotation, G2), the existing test-double patterns to extend,
and executable validation commands are all below. Line numbers are from the map @ HEAD `2335a9e` —
re-grep live before editing (they may have drifted by a few lines).

### Documentation & References

```yaml
# MUST READ — the exact recipe (THIS is the primary spec).
- file: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§1 the event-relay extension recipe: the site table (five final puts :644/:742/:745/:1052/:1054,
        partial :1100), the _dispatch choke point :426-479, the additive-key precedents (cancelled
        P1.M2.T7.S1; ready's context_prompt :864-873), the per-utterance lifecycle :631-643 the id
        piggybacks on, and the explicit 'text()/run-loop need no change' boundary. §2 the cancel-intercept
        site (daemon.py) that T2.S1 owns — do NOT touch it here. §3 what bulk code must NOT touch."
  critical: "Line cites are @ 2335a9e — re-grep live. RecorderHost.text() :310-338 and the daemon run
             loop need NO change; the payload dict flows through whole."

# MUST READ — the design decisions + verified code reading (this PRP's research).
- file: plan/008_a47116bb2b79/P1M6T1S1/research/relay_identity_design.md
  why: "§1 the six sites + choke point verified live. §2 D1-D6: the ONE helper, WHY utterance rotation
        fires at _child_on_speech (:571) and NOT at the text-cmd top (the never-relabeled requirement),
        session bump placement, capture-at-entry, the daemon tracker + discard rules, the no-id legacy
        path. §3 the existing test-double layers. §4 scope boundaries."

# MUST READ — the file being modified.
- file: voice_typing/recorder_host.py
  why: "(1) Protocol docstring :27-78 (Mode A target + the exact event grammar to extend). (2) The six
        sites. (3) _dispatch :426-479 (the choke point; final branch :437-451 reads the additive
        'cancelled' key — the pattern to copy for the new keys; the VAD stale-drop :460-468 stays). (4)
        The cmd loop :700-800 (arm branch :756, stale sentinels :742/:745, marker clears :735-737). (5)
        _run_text_and_emit_final :984-1058 (its optional-arg backward-compat pattern — text_running's
        'Default None keeps the existing unit-test call sites (4-arg) unchanged'). (6) _RelayFeedback
        :1085-1102. (7) _child_on_speech :571. (8) IMPORT PURITY note in the docstring — keep it."
  critical: "Do NOT change _on_final(text)/_on_partial(text) signatures. Do NOT touch RecorderHost.text(),
             _handle_arm's signature, the arm/disarm audio purges (_clear_recorder_audio), or the VAD
             stale-drop. Keep every _safe_put site's tuple KIND unchanged."

# MUST READ — the PRD clause being implemented.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.5 (verbatim): 'New session generation at every arm; utterance identities assigned at
        the decode source and carried through recorder_host's event relay (extend the partial/final
        payloads — a late event keeps its own identity, never relabeled as newer); keep the existing
        arm/disarm audio purges. Discard late post-final partials, duplicate finals, and canceled-utterance
        events; a dropped or filtered final still closes its utterance boundary; a rejected final never
        auto-erases visible words.' R.5 also mandates 'one writer per target; finals and boundaries are
        ordered barriers' — the settling rule is what T2.S1 builds barriers on."

# MUST READ — the test doubles to extend.
- file: tests/test_recorder_host.py
  why: "The two existing layers: (a) direct host._dispatch(...) with stub callbacks (tests :82-150 —
        test_dispatch_final_calls_on_final_and_sets_final_event :111 is the template for the discard
        tests); (b) _AbortFakeRecorder :393 / _NormalFakeRecorder :409 driving _run_text_and_emit_final
        (:436/:462) — the template for the sentinel-stamping tests. The spawn/stop tests :306+ show the
        stubbed-_worker_main real-child pattern for one round-trip test."
  critical: "Existing tests pass id-LESS payloads — they must stay green UNCHANGED (the no-id legacy
             path). Add new tests; do not rewrite the old ones."

# Cross-refs — the consumers/neighbors (cite, don't duplicate).
- file: plan/008_a47116bb2b79/P1M5T3S1/PRP.md
  why: "The parallel item (clipboard adapter; adds-only, zero modifications to landed files — the house
        rule this item follows within its 2 files). Its 'P1.M6.T2.S1 will route ghostty-class fields'
        note confirms T2.S1 is the shared consumer of its adapter and THIS item's identity events."
- file: plan/008_a47116bb2b79/tasks.json
  why: "P1.M6.T2.S1 (dispatch wiring + bulk cancel intercept), T2.S2 (session recovery — consumes
        session_gen), T2.S3. Confirms the OUTPUT contract: identity-carrying events + the accessor."

# Hard rules.
- file: AGENTS.md
  why: "Two timeouts on every non-trivial command; pytest under timeout 600 with the bash-tool timeout
        above it; never foreground the daemon; prefer single-file/-k pytest runs."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── recorder_host.py        # ← MODIFY: _RelayIds + _with_identity + six sites + _dispatch tracker + docstring
│   ├── protocol docstring  #   :27-78  (Mode A target)
│   ├── _dispatch           #   :426-479 (choke point: final :437-451, partial :452-454)
│   ├── _child_on_speech    #   :571-572 (rotation site)
│   ├── per-utterance evt   #   :631-643 (lifecycle the id piggybacks on)
│   ├── cmd loop            #   :700-800 (arm :756, sentinels :742/:745, clears :735-737)
│   ├── _run_text_and_emit_final # :984-1058 (sentinels :1052/:1054)
│   └── _RelayFeedback      #   :1085-1102 (partial put :1100)
├── daemon.py               # READ ONLY (T2.S1 owns; callbacks' signatures unchanged)
├── bulk_delivery.py streaming.py typing_backends.py  # READ ONLY (untouchable per map §3)
tests/
└── test_recorder_host.py   # ← MODIFY: add the identity/discard test layers
```

### Desired Codebase tree with files to be added

```bash
# No NEW files. Modifications only:
voice_typing/recorder_host.py      # + _RelayIds, + _with_identity, six sites wrapped, _dispatch tracker + rules,
                                   # + relay_identity accessor, docstring §identity
tests/test_recorder_host.py        # + ~12 tests (three layers)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G1) — ADDITIVE keys only. The payload grammar is consumed at _dispatch with
#   payload.get(...); 'cancelled' (:439-441) and 'context_prompt' (:864-873) are the precedents. Never
#   rename 'text', never remove 'cancelled', never change a tuple KIND. The daemon must tolerate the
#   keys' ABSENCE (old payloads, doubles) — read with payload.get("utterance_id") and treat None as
#   "no identity → legacy path".

# CRITICAL #2 (G2) — rotate the utterance id at _child_on_speech (:571), NOT at the text-cmd top.
#   This is the load-bearing decision behind "a late event keeps its own identity, never relabeled":
#   with text-cmd rotation, a late realtime partial landing after final-N but before text-cmd-N+1
#   processes is stamped with the NEW id → indistinguishable from utterance N+1's first partial →
#   stale text reaches the tail. With speech-start rotation the holder keeps N until N+1's speech
#   begins, so the late partial keeps N → the daemon's settled-id rule drops it. on_speech fires on
#   VAD speech detection per utterance and is already wired. Sentinels do NOT rotate (they settle the
#   current id). Do NOT add a "rotate if settled" fallback — it reintroduces relabeling.

# CRITICAL #3 (G3) — _final_evt must be set for EVERY final-kind event, including DISCARDED
#   duplicates. host.text() blocks on it (VT-007: without a final event the run loop wedges forever).
#   Dropping the _on_final RELAY is safe; dropping the event-set is not.

# CRITICAL #4 (G4) — settle BEFORE relaying. "A dropped or filtered final still closes its utterance
#   boundary" must hold regardless of what the daemon's on_final does downstream (textproc.clean
#   rejection, cancel suppression, exceptions — note _dispatch already swallows on_final exceptions
#   :445-447). Settling at relay time in _dispatch gives this by construction.

# CRITICAL #5 (G5) — the _cancel_mark flow is ORDER-SENSITIVE: _dispatch records
#   self._cancel_mark = bool(payload.get("cancelled")) BEFORE self._on_final(text) (:439-444). Keep
#   that order; the identity tracker must not interleave between them.

# CRITICAL #6 (G6) — reader-thread-only state. The tracker (latest_session, settled ids, open id,
#   relay_identity) is mutated ONLY on the reader thread inside _dispatch; the daemon callbacks read
#   relay_identity ON that same thread (on_final/_on_partial run there) → no extra locking needed
#   beyond the child-side _RelayIds lock (which guards the realtime-thread vs cmd-loop-thread race).

# CRITICAL #7 (G7) — backward-compat defaults on every new parameter: _RelayFeedback(evt_q, ids=None),
#   _run_text_and_emit_final(..., ids=None). The existing unit tests construct both with the old
#   signatures (the 4-arg call sites are called out in _run_text_and_emit_final's own docstring).
#   ids=None → stamp nothing → payloads identical to today → old tests stay green untouched.

# CRITICAL #8 (G8) — bounded tracker state. settled ids: keep at most the last ~16 per session and
#   CLEAR on session advance (a monotonically growing set in a long daemon session is a leak).

# CRITICAL #9 (G9) — no daemon.py edit. The callbacks' signatures stay (str)->None. T2.S1 consumes
#   via host.relay_identity inside the existing callbacks. bulk_delivery.py/streaming.py/
#   typing_backends.py are untouchable (map §3).

# CRITICAL #10 (G10) — validation discipline (AGENTS.md): timeout-wrapped pytest, single file, never
#   foreground the daemon; the unit tests here need no CUDA/no child process except the one stubbed
#   _worker_main round-trip (the :306+ pattern — a stub target, not the real recorder).
```

## Implementation Blueprint

### Data models and structure

No persistent model. Two small runtime structures:

```python
# CHILD side — created once per _worker_main, shared by closure into the six sites.
class _RelayIds:
    """Child-side utterance/session identity stamper (PRD §4.2sexies R.5).

    utterance_id: rotated ONLY at on_speech (the decode source's new-utterance boundary) so a LATE
    partial keeps the settled id of the utterance it belonged to (never relabeled as newer — R.5).
    session_gen: bumped at every 'arm' command (new session generation per arm — R.5).
    stamp() captures both under the lock at callback entry (the realtime thread races the cmd loop).
    """
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._utterance = 0
        self._session = 0
    def rotate_utterance(self) -> int:
        with self._lock:
            self._utterance += 1
            return self._utterance
    def new_session(self) -> int:
        with self._lock:
            self._session += 1
            return self._session
    def stamp(self, payload: dict) -> dict:
        with self._lock:
            payload["utterance_id"] = self._utterance
            payload["session_gen"] = self._session
        return payload

def _with_identity(payload: dict, ids: "_RelayIds | None") -> dict:
    """ONE payload helper for the six event sites — adds utterance_id + session_gen (ADDITIVE keys;
    the 'cancelled' sentinel key and ready's 'context_prompt' are the precedents). ids=None stamps
    nothing (legacy/test call sites)."""
    return ids.stamp(payload) if ids is not None else payload

# DAEMON side — on RecorderHost, reader-thread-only.
_RelayIdentity = "NamedTuple(session_gen int | None, utterance_id int | None)"  # relay_identity accessor's value
# tracker fields: _ids_latest_session=-1(?), _ids_settled: deque(maxlen=16) + membership set, _ids_open=None
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — re-verify the site lines live (the map cites @ 2335a9e; expect small drift).
  - RUN: grep -n '_safe_put(evt_q, ("final"\|_safe_put(self._evt_q, ("partial"\|def _dispatch\|def _child_on_speech\|kind == "arm"\|def _run_text_and_emit_final\|class _RelayFeedback' voice_typing/recorder_host.py
  - RUN (baseline): timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q   # all green pre-change
  - EXPECTED: the six sites + choke point located; baseline green. Do not proceed on a red baseline.

Task 1: CHILD side — _RelayIds + _with_identity + wire the six sites + rotation/bump triggers.
  - ADD _RelayIds + _with_identity (module scope, near _safe_put :798+).
  - _worker_main: ids = _RelayIds() after the queue setup; pass ids into _RelayFeedback(evt_q, ids).
  - _child_on_speech (:571): ids.rotate_utterance() FIRST, then the existing ("speech", {}) put (speech
    payload itself stays unstamped — only the six contracted sites carry keys).
  - _child_on_final (:643-644): _safe_put(evt_q, ("final", _with_identity({"text": text}, ids))).
  - cmd loop sentinels (:742/:745): wrap both dicts with _with_identity(..., ids).
  - arm branch (:756): ids.new_session() immediately BEFORE _handle_arm(...) (signature untouched).
  - _run_text_and_emit_final: add trailing kwarg ids=None; wrap the two sentinel puts (:1052/:1054);
    pass ids at the call site (:753).
  - KEEP: tuple kinds, _safe_put usage, marker clears :735-737, audio purges, text_running semantics.

Task 2: DAEMON side — the tracker + discard rules + accessor in/around _dispatch.
  - __init__ (near :133-135): self._ids_latest_session = -1; self._ids_settled = collections.deque(maxlen=16);
    self._ids_settled_set = set(); self._ids_open = None; self._relay_identity = _RelayIdentity(None, None).
  - Add the read-only property relay_identity (returns self._relay_identity) — document as the T2.S1 seam.
  - _dispatch final branch (:437-451), BEFORE the existing _cancel_mark line, insert:
    uid = payload.get("utterance_id"); gen = payload.get("session_gen")
    if uid is not None:
      if gen is not None and isinstance(gen, int) and gen < self._ids_latest_session:
        self._final_evt.set(); logger.debug(...late session final dropped...); return        # late cross-session
      if uid in self._ids_settled_set:
        self._final_evt.set(); logger.debug(...duplicate final dropped...); return            # G3: still set evt
      if gen is not None and isinstance(gen, int) and gen > self._ids_latest_session:
        self._ids_latest_session = gen; self._ids_settled.clear(); self._ids_settled_set.clear()  # session advance
      self._ids_settled.append(uid); self._ids_settled_set.add(uid); self._ids_open = None    # G4: settle pre-relay
      self._relay_identity = _RelayIdentity(gen, uid)
    then the EXISTING body unchanged (_cancel_mark → _on_final(text) → _final_evt.set()).
  - _dispatch partial branch (:452-454), before self._on_partial(text):
    uid = payload.get("utterance_id"); gen = payload.get("session_gen")
    if uid is not None:
      if gen is not None and isinstance(gen, int) and gen < self._ids_latest_session: return  # late session
      if uid in self._ids_settled_set: logger.debug(...late post-final partial dropped...); return
      if gen is not None and isinstance(gen, int) and gen > self._ids_latest_session:
        self._ids_latest_session = gen; self._ids_settled.clear(); self._ids_settled_set.clear()
      self._ids_open = uid; self._relay_identity = _RelayIdentity(gen, uid)
    then self._on_partial(text).
  - uid is None (no identity) → the inserted blocks are skipped → byte-identical legacy dispatch (G7).

Task 3: DOCSTRING (Mode A) — extend the :27-78 grammar lines:
  ("final", {text, utterance_id, session_gen})  # or {text:"", cancelled:True, ...} — id settles the utterance
  ("partial", {text, utterance_id, session_gen})
  plus a short §IDENTITY paragraph: decode-source assignment (on_speech rotation — late events keep
  their own id), session bump per arm, the three daemon discard rules, the settle-before-relay
  boundary rule, and relay_identity as the consumer seam (P1.M6.T2.S1).

Task 4: TESTS — three layers appended to tests/test_recorder_host.py (existing doubles; no CUDA):
  - Layer A (_RelayIds/_with_identity units): stamp adds both keys + returns same dict; ids=None no-op;
    rotate/new_session monotonic; lock-guarded concurrent stamp (2 threads, no lost updates).
  - Layer B (direct _dispatch, stub callbacks — extend the :82-150 pattern):
    partial+final with same id → both relayed, relay_identity updated each time;
    late post-final partial (same id after the final) → on_partial NOT called;
    duplicate final (same id twice) → second on_final NOT called, _final_evt IS set;
    cancel sentinel (cancelled:True + id) → on_final("") called, _cancel_mark set, id settled,
      straggler partial dropped; filtered-final boundary: final with id + a stub on_final that
      raises/returns → id still settled (next same-id partial dropped);
    session advance: events gen=1 → gen=2 → settled cleared; a gen=1 straggler after gen=2 → dropped;
    no-id payload → both relayed exactly as today (legacy path pin).
  - Layer C (sentinel stamping via the fakes — extend :436/:462): _run_text_and_emit_final with ids
    stamps the abort sentinel and the cancel sentinel (assert the put payloads carry both keys, and
    the cancel one keeps cancelled:True); plus ONE stubbed-_worker_main round-trip (the :306+ pattern)
    asserting a real child's final arrives identity-carrying through the queue → _dispatch relay.
  - RUN after writing: timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q
    (bash-tool timeout 330). Then the fuller gate (Validation L2).

Task 5: VALIDATE — the Validation Loop below; iterate until green. No git commit unless directed
  (message if so: "P1.M6.T1.S1: relay payload identity — utterance_id + session_gen at the six sites,
  _dispatch discard rules + relay_identity seam").
```

### Implementation Patterns & Key Details

```python
# PATTERN — the six sites, after (only the dict argument changes):
_safe_put(evt_q, ("final", _with_identity({"text": text}, ids)))                       # :644 real final
_safe_put(evt_q, ("final", _with_identity({"text": "", "cancelled": True}, ids)))       # :742 stale-cancel
_safe_put(evt_q, ("final", _with_identity({"text": ""}, ids)))                          # :745 stale-abort
# ...same two inside _run_text_and_emit_final (:1052/:1054) with its ids kwarg...
_safe_put(self._evt_q, ("partial", _with_identity({"text": text}, self._ids)))          # :1100 partial

# PATTERN — rotation + bump triggers (the ONLY two mutation points child-side):
def _child_on_speech() -> None:
    ids.rotate_utterance()          # G2: the decode-source new-utterance boundary (BEFORE the put)
    _safe_put(evt_q, ("speech", {}))  # speech payload stays unstamped (contract: six sites only)
...
elif kind == "arm":
    ids.new_session()               # R.5: new session generation at every arm (before _handle_arm)
    _handle_arm(recorder, cancel_event, abort_event)

# GOTCHA — G3/G5 ordering inside the final branch: identity settle FIRST, then the EXISTING
# _cancel_mark = bool(payload.get("cancelled")) → self._on_final(text) → self._final_evt.set().
# A discarded duplicate sets _final_evt and returns BEFORE _cancel_mark (a duplicate must not
# disturb an already-consumed cancel mark).
```

### Integration Points

```yaml
IPC PROTOCOL (the contract this item extends):
  - "final" payload: {text} | {text:"", cancelled:True}  →  + utterance_id:int, session_gen:int (additive)
  - "partial" payload: {text}                            →  + utterance_id:int, session_gen:int (additive)
  - all other kinds unchanged (ready/error/speech/vad/speech_end/gone)
  - daemon consumption: _dispatch (single choke point) + host.relay_identity (T2.S1 seam)

CONSUMERS (do not build here):
  - P1.M6.T2.S1: reads relay_identity inside on_final/_on_partial; builds bulk barriers on the settle rule
  - P1.M6.T2.S2: session_gen delimits arm→disarm recovery sessions

NO config keys. NO daemon.py/bulk_delivery.py/streaming.py/typing_backends.py edits.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/recorder_host.py tests/test_recorder_host.py && echo OK
.venv/bin/python -c "
import voice_typing.recorder_host as rh   # import-pure: no RealtimeSTT/torch/ctranslate2
import sys; assert not [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
assert hasattr(rh.RecorderHost, 'relay_identity'), 'accessor missing'
assert callable(rh._with_identity) and hasattr(rh, '_RelayIds')
print('symbols + import purity OK')"
```

### Level 2: Unit Tests (Component Validation)

```bash
# The item's gate (existing doubles; no CUDA; includes the pre-existing suite = the no-regression pin):
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q        # bash-tool timeout 330
# Neighbor suites that consume recorder_host (mocked; still no CUDA):
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "host or cancel or final or partial"  # spot
# Full pure-python sweep if time allows (the plan's standard gate):
timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py 2>&1 | tail -3
# Expected: ALL green — existing tests unchanged (no-id legacy path), ~12 new tests pass.
```

### Level 3: Integration Testing (System Validation)

```bash
# Structural: all six sites route through the helper; no bare final/partial puts remain:
grep -n '_with_identity' voice_typing/recorder_host.py | wc -l          # expect >= 8 (def + 6 sites + pass-through)
grep -nE '_safe_put\((evt_q|self\._evt_q), \("(final|partial)", \{' voice_typing/recorder_host.py \
  | grep -v _with_identity && echo "UNWRAPPED SITE FOUND — fix" || echo "all six sites wrapped"
# Rotation/bump triggers present:
grep -n 'rotate_utterance()\|new_session()' voice_typing/recorder_host.py   # both present exactly once each
# Docstring documents the keys (Mode A):
grep -n 'utterance_id' voice_typing/recorder_host.py | head -3            # hits in the docstring grammar
```

### Level 4: Creative & Domain-Specific Validation

```bash
# The discard-semantics pin (the one behavior delta) — covered by Layer B; verify by count:
timeout 120 .venv/bin/python -m pytest tests/test_recorder_host.py -q -k "identity or session or duplicate or late" -v 2>&1 | tail -15
# Expected: each named rule has a passing test; the cancelled-sentinel test asserts BOTH cancelled:True
# survived stamping AND the id settled (the cancel flow + the identity flow compose).
# NO live-daemon / CUDA / mic use anywhere in this item's tests (AGENTS.md).
```

## Final Validation Checklist

### Technical Validation

- [ ] L1 py_compile + import purity + symbols OK.
- [ ] `tests/test_recorder_host.py` fully green (existing untouched + new).
- [ ] The neighbor spot-run (`test_daemon.py -k host/cancel/final/partial`) green.
- [ ] Structural greps: six sites wrapped; both triggers present exactly once; docstring updated.

### Feature Validation

- [ ] Additive keys on all six sites; tuple kinds unchanged; `cancelled` survives stamping.
- [ ] Rotation at `_child_on_speech`; session bump in the arm branch; capture-at-entry under lock.
- [ ] Discard rules: late post-final partial, duplicate final (evt still set), cross-session straggler;
      settled cleared on session advance; bounded (maxlen 16).
- [ ] Settle-before-relay (filtered/dropped final closes the boundary) — pinned by test.
- [ ] No-id payloads → byte-identical legacy dispatch — pinned by test.
- [ ] `relay_identity` updated per relay; documented as the T2.S1 seam.

### Code Quality Validation

- [ ] Adds-only within the 2 files; no signature change to `_on_final`/`_on_partial`/`_handle_arm`/
      `RecorderHost.text()`; audio purges + VAD stale-drop untouched.
- [ ] `_RelayFeedback(evt_q, ids=None)` + `_run_text_and_emit_final(..., ids=None)` defaults (G7).
- [ ] Tracker state reader-thread-only (G6); bounded (G8); `_cancel_mark` ordering preserved (G5).

### Documentation & Deployment

- [ ] Protocol docstring (Mode A): grammar lines + §IDENTITY paragraph (assignment, rotation rationale,
      session rule, the three discards, the seam).
- [ ] No new config keys / env vars.

---

## Anti-Patterns to Avoid

- ❌ Don't rotate the utterance id at the text-cmd top — it relabels late partials (G2); rotate at on_speech.
- ❌ Don't skip `_final_evt.set()` on a discarded duplicate — `host.text()` would wedge (G3/VT-007).
- ❌ Don't settle AFTER `on_final` — a filtered/raised final must still close the boundary (G4).
- ❌ Don't reorder `_cancel_mark` relative to `_on_final` (G5), and don't let a discarded duplicate
  disturb the mark.
- ❌ Don't make the new params required — the old 4-arg test call sites and doubles must stay green (G7).
- ❌ Don't touch daemon.py / bulk_delivery.py / streaming.py / typing_backends.py / config (G9, map §3).
- ❌ Don't stamp the `speech`/`vad`/`speech_end`/`ready`/`error`/`gone` payloads — the contract is the
  five final sites + the partial site, exactly.
- ❌ Don't add a "rotate-if-settled" fallback — it reintroduces relabeling (G2).
- ❌ Don't run the daemon, the E2E scripts, or CUDA tests for this item (unit doubles only).

---

## Confidence Score

**9/10.** The recipe is pre-verified against live code (map §1 + this session's reads): the six sites,
the choke point, the additive-key precedents, the per-utterance lifecycle, and the exact test-double
layers are all confirmed. The one subtle decision (speech-start rotation vs text-cmd rotation) is
reasoned and test-pinned (G2). Residual risk: line drift since `2335a9e` (mitigated by Task 0's
re-grep) and RealtimeSTT's on_speech firing cadence in exotic paths (mitigated: the no-id legacy path
means a missed rotation degrades to today's behavior rather than breaking; the round-trip test pins
the normal case). Zero coupling to the parallel P1.M5.T3.S1 (different files; both feed T2.S1).

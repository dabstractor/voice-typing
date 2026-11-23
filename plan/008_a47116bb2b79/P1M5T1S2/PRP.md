# PRP — P1.M5.T1.S2: daemon-side cooperating-editor TargetAdapter (pi-editor socket)

## Goal

**Feature Goal**: Build the **second real bulk-delivery TargetAdapter** (PRD §4.2sexies R.3): a
daemon-side `PiEditorTarget` implementing the `bulk_delivery.DeliveryTarget` Protocol by speaking the
**AF_UNIX JSONL socket served by the pi extension** (P1.M5.T1.S1's `pi-editor.sock`), with **editor
takeover events mapped into the shared takeover taxonomy** (one concise reason →
`controller.halt_for_takeover`). Same contracts as the IM adapter (P1.M4.T2/T3/T4): acquire/show/
finalize/leave/cancel, the `ShowResult` taxonomy, mutation-time re-checks, ops executed on the
target's event loop (the extension applies buffer edits on pi's Node loop), the 250 ms engineering
deadline (owned by the failure-complete controller from P1.M3.T2.S2 — the adapter never self-times
out, it reports honestly), and **never retry a may-have-landed op** (a None/timeout reply ⇒
`UNKNOWN`, the controller disarms).

**Deliverable** (2 NEW files; **ZERO modifications** to `bulk_controller.py`, `bulk_delivery.py`,
`daemon.py`, `.pi/**` (S1's), any `tests/ime_*` / G3 lab file):
1. `voice_typing/pi_editor.py` — Mode A module docstring carrying the R.3 contract (mirroring
   `voice_typing/ime/target.py`'s docstring style), plus:
   - `PiEditorClient` — the transport duck: AF_UNIX SOCK_STREAM connect, JSONL framing (one line in →
     one line out), `request(op, timeout=…, **fields) -> dict | None`, and a background reader thread
     that routes id-less `{"event":…}` lines to an `on_event` callback (the ime/manager
     `_read_loop`/`_dispatch` split; strictly one request in flight because the protocol has NO id echo).
   - `PiEditorTarget` — the adapter: acquire (read-state verify + fail-before-delivery taxonomy),
     show (zero-diff-first, insert-vs-replace, UTF-16 offsets via `map_span`), finalize (settle,
     no-edit-when-matching), leave (no post-stop writes, clear-first, idempotent), cancel (ONE op,
     nothing-pending ⇒ UNCHANGED with no request).
   - `PiEditorTakeoverWatch` — the event→taxonomy latch: exactly ONE halt + ONE reason per watch
     (TakeoverWatch pattern), reason `"pi-editor key takeover"`; logs carry counts/times only (R.5).
2. `tests/test_pi_editor.py` — taxonomy-pinned unit tests with a `_FakeClient` duck (mirror
   `tests/test_ime_target.py`'s `_FakeProc`) + socket-level tests with a real in-process fake
   extension server on `tmp_path` (mirror `tests/test_control_socket.py`: real AF_UNIX JSONL,
   `_wait_for` polls, no real pi needed).

**Success Definition**:
- (a) `PiEditorTarget` satisfies `isinstance(target, DeliveryTarget)` (runtime_checkable Protocol).
- (b) Unit tests pin EVERY refusal branch: socket absent / no reply / dirty / stale-owned fragment /
  read-missing-fields / inconsistent owned range; zero-diff ⇒ UNCHANGED with NO socket request;
  insert-vs-replace op selection (extension ⇒ insert delta; divergence ⇒ ONE replace over the owned
  UTF-16 range); None/timeout reply ⇒ UNKNOWN (and never re-sent); finalize settles (duplicate final ⇒
  refused "utterance closed"); cancel nothing-pending ⇒ UNCHANGED no request; leave clears binding
  FIRST and never writes after.
- (c) UTF-16 units proven: astral payloads (e.g. "Zoë — naïve 日本語 🫡") produce replace offsets =
  `map_span(..., TargetUnits.UTF16_UNITS)` — 🫡 counts 2 units, never `len()`.
- (d) Takeover: a `{"event":"takeover","source":"key"}` line → exactly ONE `halt_for_takeover` call
  with ONE concise reason; a second event is latched away; our own op replies never trigger it.
- (e) Socket-level: against an in-process fake extension honoring S1's protocol v1 (applied/unchanged/
  refused, read with owned/dirty/units), the adapter drives a full arm→show×2→finalize→cancel cycle.
- (f) `timeout 180 .venv/bin/python -m pytest tests/test_pi_editor.py -q` green; the neighboring
  suites stay green (`test_bulk_controller.py`, `test_bulk_delivery.py`, `test_ime_target.py` — this
  task adds files only); `git status --porcelain` shows exactly the two new files.

## User Persona

**Target User**: Internal — three consumers:
1. **P1.M5.T2.S1 (G3 row: pi prompt in isolated Ghostty)** — instantiates `PiEditorTarget` against a
   real pi (S1's extension serving the socket) for the visible-field proof (single visible edit, no
   blank frames). Its op vocabulary, result mapping, and takeover seam are THIS item's output contract.
2. **P1.M6.T2.S1 (daemon dispatch wiring)** — constructs the adapter in the daemon behind the
   `output.delivery` gate; it needs the same `target:` duck shape `BulkController` already consumes
   (the ImeTarget precedent).
3. **P1.M7.T1 (G6 graduation)** — counts this adapter's G3 row toward "verified G3 rows for the pi
   prompt in Ghostty".

**Use Case**: The daemon (bulk-text mode) recognizes speech while pi's prompt editor is focused. The
adapter connects to `pi-editor.sock`, `acquire()` binds the field via a `read` (refusing dirty or
stale-owned states), and on each recognition update `show()`s ONE insert (delta) or ONE replace
(minimal-diff over the owned UTF-16 range). The user presses any key → the extension pushes
`{"event":"takeover"}` → the watch calls `controller.halt_for_takeover("pi-editor key takeover")` —
exactly once, no retry, no post-takeover mutation.

**Pain Points Addressed**: (1) The IM-v2 route is DEAD on ghostty 1.3.1/1.4.0 (R.2/G3 matrix) — the
pi prompt needs a second real route with insert AND correct; the extension gives verified ownership
at the target (the editor knows exactly what it wrote — R.5's strongest form). (2) The controller is
route-agnostic but needs a second `DeliveryTarget` to prove the seam generalizes beyond IM. (3)
Synthesized typing is FORBIDDEN in bulk mode (R.1) — every primitive here is one buffer op.

## Why

- **PRD §4.2sexies R.3** makes the terminal chat prompt the first bulk-delivery milestone via the
  cooperating-editor seam; S1 builds the editor side (socket + ops), THIS item builds the daemon side.
  R.4: "Prove insert AND correct before any mic integration" — this adapter + its tests are that
  mechanism proof's daemon half (the real-field row is M5.T2).
- **It exercises the controller against a real second route**: P1.M3.T2.S2's controller was
  fake-target-tested (G2); the IM adapter was the first real one; this is the second — same contracts,
  different transport (synchronous JSONL socket vs subprocess wire), which is exactly what "second
  real adapter for G3 rows" means in the task tree.
- **Ownership-verified at the target**: the extension refuses non-owned ranges and reports takeover —
  the adapter can therefore keep its client-side accounting honest with cheap server-side truth
  (unlike terminals that never send `surrounding_text`).

## What

A `DeliveryTarget` implementation over S1's socket: transport duck with request/event split, adapter
with the full R.3 lifecycle and refusal taxonomy, takeover latch, and taxonomy-pinned tests (fake
client) + socket-level tests (in-process fake extension). No config changes, no daemon wiring, no
real-pi dependency in tests.

### Success Criteria

- [ ] (a)–(f) of the Success Definition, verified by the Validation Loop below.
- [ ] Module docstring carries the R.3 contract verbatim-style (delivery model, result taxonomy,
      event-count law, units rule, refusal taxonomy, documented password/selection limitation).
- [ ] Zero-diff guard runs BEFORE any socket request; no code path retries after UNKNOWN.
- [ ] `git status --porcelain` = exactly the two new files.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer gets: the S1 socket protocol v1 (reproduced below — the input contract), the
ImeTarget structural template (file + line-anchored behaviors), the controller's consumption surface
(read from source this session), the takeover latch pattern, the test fakes to mirror, and every
gotcha (no-id-echo framing, UTF-16 units, controller-owned deadline). No pi/TS knowledge is needed —
this item never runs pi.

### Documentation & References

```yaml
# MUST READ — this item's own research (verified this session; compact, authoritative).
- docfile: plan/008_a47116bb2b79/P1M5T1S2/research/pi_editor_adapter_research.md
  why: "§1 the verified source surfaces (bulk_delivery/ImeTarget/controller/takeover/manager/test
        patterns with line anchors). §2 the S1 socket contract v1 verbatim. §3 the design decisions
        (module layout, refusal taxonomy, op selection, cancel/leave semantics, takeover latch).
        §4 scope fences + parallel-safety with S1."

# MUST READ — the S1 PRP (the socket contract's source of truth; S1 is IN FLIGHT — treat as contract).
- file: plan/008_a47116bb2b79/P1M5T1S1/PRP.md
  why: "The 'socket protocol (v1)' block (ops insert/replace/cancel/read, replies
        applied|unchanged|refused with ok/error shapes, takeover events, owned/dirty/units:'utf-16',
        socket path $XDG_RUNTIME_DIR/voice-typing/pi-editor.sock, one line in → one line out) and the
        success criteria that pin them (b)-(c). unknown is RESERVED for S2's deadline layer — i.e.
        THIS item synthesizes it on timeout."
  critical: "S1 replies carry NO id echo → the client must serialize strictly one request in flight
             and route id-less {\"event\":…} lines to the takeover callback (never to a pending reply)."

# MUST READ — the contracts module (the vocabulary; import from it, never restate).
- file: voice_typing/bulk_delivery.py
  why: "DeliveryTarget Protocol (:117-160: acquire/show/finalize/leave/cancel signatures with session/
        utterance/seq/expected_revision), ShowResult (:42-53), AcquireResult (:96-113),
        TargetUnits.UTF16_UNITS + map_span (:183-212, surrogate-pair aware, ORIGINAL string only),
        rendered_equal (:224-234, whitespace-fold only, never case/punct)."

# MUST READ — THE structural template (mirror its shape, docstring style, and guards).
- file: voice_typing/ime/target.py
  why: "Mode A docstring (:1-40); units class-attr (:87); FieldBinding (:62); acquire refusal chain
        (:89-121); zero-diff-first + revision-regression guard + insert/correction split (:131-230);
        honest result mapping None→UNKNOWN (:207-215); finalize settle/duplicate-refused (:232-260);
        leave clear-first/idempotent (:262-285); cancel nothing-pending→UNCHANGED no request
        (:287-320); last_reason machine-readable everywhere. DO NOT copy the wire specifics — the pi
        socket differs (UTF-16 units, owned-range semantics, no verify cmd — read IS the verify)."

# MUST READ — the controller's consumption surface (read-only; the adapter's customer).
- file: voice_typing/bulk_controller.py
  why: ":219-264 __init__(target, on_stopped, op_deadline=0.25): the controller IS the receiver and
        owns the 250 ms deadline — the adapter is NEVER trusted to self-timeout; a deadline miss is
        unknown-class → stop 'op-deadline', NEVER resubmit (:51-58). halt_for_takeover (:368).
        stop reasons (:72). expected_revision is +1'd by the controller ONLY on applied (:160 area)."
  gotcha: "DO NOT modify this file. The adapter's job: return honest ShowResult values fast."

# MUST READ — the takeover latch pattern (exactly one halt/reason per watch).
- file: voice_typing/ime/takeover.py
  why: "TakeoverWatch (:196-260): attach/on_event→detector.feed→reason→_revoke once, latched; second
        reasons logged (counts/reasons only, never recognition text — R.5) and dropped. Mirror the
        LATCH shape; the pi variant's feed is trivial (event dict → fixed reason)."

# MUST READ — the transport + test patterns.
- file: voice_typing/ime/manager.py
  why: "ImeProcess.request (:219) + _read_loop/_dispatch (:288-341): the reader-thread split of
        id-echoed replies (resolve the pending future) vs id-less events (callback). The pi client is
        the same shape minus subprocess management (the socket is served by the live pi)."
- file: tests/test_ime_target.py
  why: "_FakeProc (:21) scripted-request duck + _RaisingProc (:675): how taxonomy branches are pinned
        WITHOUT real transports. Mirror for _FakeClient."
- file: tests/test_control_socket.py
  why: "Real in-process AF_UNIX JSONL server on tmp_path + monkeypatched XDG_RUNTIME_DIR + _wait_for
        poll helper: the socket-level test pattern (bounded, hermetic — no real pi)."

# PRD ground truth.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.1 (event-count law: insert=1, correction=1, zero-diff=0), R.3 (the delivery
        model + units rule + 'extension seam preferred over a fork'), R.5 (takeover at the target;
        250 ms deadline; never retry a may-have-landed op; validate in the RECEIVER), R.7 (G2
        necessary-never-sufficient; isolation)."

# External — Python AF_UNIX client mechanics (stdlib only).
- url: https://docs.python.org/3/library/socket.html#socket.socket.connect
  why: "AF_UNIX SOCK_STREAM connect; FileNotFoundError = no socket (pi/extension absent) → the
        'pi socket absent' refusal; ConnectionRefusedError = stale file → 'pi socket no reply'."
- url: https://docs.python.org/3/library/socket.html#socket.socket.makefile
  why: "makefile('r') for line framing — BUT pair with settimeout (the ctl.py makefile-without-timeout
        hang is the repo's canonical bug): implement reads via a select/poll or a socket-timeout
        reader thread, never an unbounded makefile read on the caller's thread."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── bulk_delivery.py        # contracts (READ-ONLY) — DeliveryTarget/ShowResult/map_span/rendered_equal
├── bulk_controller.py      # controller (READ-ONLY, failure-complete P1.M3.T2.S2) — owns the 250ms deadline
├── ime/
│   ├── target.py           # ImeTarget — THE structural template (READ-ONLY)
│   ├── takeover.py         # TakeoverWatch latch pattern (READ-ONLY)
│   ├── manager.py          # request/event reader-thread split pattern (READ-ONLY)
│   └── protocol.py         # JSONL encode/decode precedent (READ-ONLY)
tests/
├── test_ime_target.py      # _FakeProc duck pattern (READ-ONLY)
├── test_control_socket.py  # in-process AF_UNIX + _wait_for pattern (READ-ONLY)
.pi/extensions/             # S1's (in flight; NOT this item's concern beyond the protocol)
plan/008_a47116bb2b79/
├── P1M5T1S1/PRP.md         # the socket contract source of truth
└── architecture/pi_seam_proof.md  # S1 will produce; cite if present at implementation time
```

### Desired Codebase tree with files to be added

```bash
voice_typing/pi_editor.py     # NEW — Mode A docstring + PiEditorClient + PiEditorTarget + PiEditorTakeoverWatch
tests/test_pi_editor.py       # NEW — _FakeClient taxonomy tests + in-process fake-extension socket tests
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — the S1 protocol has NO id echo (unlike ime/protocol.py's id-echoed replies). The
#   client MUST serialize strictly one request in flight (a lock around send+await-reply), and the
#   reader thread must route {"event":…} lines to the takeover callback — a takeover line arriving
#   between request and reply must NEVER be parsed as the reply. Dispatch on the "event" key FIRST.

# CRITICAL #2 — UNITS are UTF-16 code units. ALL char→offset math via bulk_delivery.map_span(text,
#   start, end, TargetUnits.UTF16_UNITS) on the ORIGINAL string; an astral char (🫡) is 2 units.
#   NEVER len() a str and call it an offset; never slice via a normalized/lowercased copy (R.3).

# CRITICAL #3 — the CONTROLLER owns the 250 ms deadline (bulk_controller.py:51-58). The adapter uses
#   its own short socket timeouts (~0.25 s per read; ~2.5 s for acquire) only to return HONEST values
#   fast; expiry ⇒ ShowResult.UNKNOWN / AcquireResult(ok=False). NEVER retry after UNKNOWN — the
#   controller disarms; a retried may-have-landed op is the R.5 cardinal sin.

# CRITICAL #4 — zero-diff guard FIRST, zero socket traffic: rendered_equal(_last_applied_span, span)
#   ⇒ UNCHANGED with NO request (R.1: zero-diff = 0 events). Also refuse BEFORE any request on
#   not-acquired / utterance-closed / revision-regression (mirror ime/target.py's guard order).

# CRITICAL #5 — acquire is fail-before-delivery over a read: socket absent (FileNotFoundError) →
#   "pi socket absent"; no reply → "pi socket no reply"; dirty=true → "editor dirty"; owned non-null
#   → "editor owns fragment" (a stranded prior-session fragment — never adopt it); missing fields →
#   "read missing fields"; owned out of bounds → "inconsistent owned range". Track the acquired
#   owned_start (UTF-16) + caret context for later replace math.

# CRITICAL #6 — S1's read returns cursor as {row,col} — row/col is NOT a byte/unit offset. Use ONLY
#   the owned range (UTF-16 offsets) for replace math; treat cursor as informational. Document this
#   in the docstring (the IM adapter's analogous honest-gap precedent: no password/selection signal
#   in protocol v1 — record the limitation, never guess a heuristic).

# CRITICAL #7 — leave() clears the binding FIRST, sends nothing (or at most a best-effort nothing —
#   protocol v1 has no leave op; stop = preserve visible words, zero post-stop writes). Idempotent;
#   never raises; a dead socket in leave is one warning line. Post-leave every op refuses
#   "not acquired" until a fresh acquire.

# CRITICAL #8 — cancel: {"op":"cancel"} is ONE op removing the owned range; the extension clears
#   owned. Nothing pending ⇒ UNCHANGED with NO request (G2 trace_07 pin). Uncertain state (dirty,
#   stale) ⇒ REFUSED — stop, never repair.

# CRITICAL #9 — takeover latch: exactly ONE halt_for_takeover + ONE reason per watch; subsequent
#   events logged-and-dropped. Our OWN op replies must never trigger it (they aren't events —
#   guaranteed by CRITICAL #1's dispatch). Reason string is fixed + machine-readable
#   ("pi-editor key takeover"); logs carry counts/times only, never recognition text (R.5).

# CRITICAL #10 — socket reads must be timeout-bounded on the READER THREAD (or select-based); the
#   repo's canonical hang is ctl.py's makefile("r") without timeout (AGENTS.md). Every test wait is
#   _wait_for-bounded; every pytest run under TWO timeouts (AGENTS.md Rule 1).

# CRITICAL #11 — scope: do NOT modify bulk_controller.py / bulk_delivery.py / daemon.py / .pi/** /
#   tests/ime_* / pyproject / .gitignore. Daemon wiring is P1.M6.T2.S1; the G3 real-field row is
#   P1.M5.T2.S1. This item ships adapter + tests ONLY (S1 is parallel — zero file overlap).

# CRITICAL #12 — the controller +1s expected_revision ONLY on applied (bulk_controller.py): seed the
#   binding revision from acquire's read (use a monotonically increasing client-side counter if the
#   protocol reports none — document the choice; refuse revision REGRESSION before any request).
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/pi_editor.py — imports: stdlib (socket, threading, json, logging, os, dataclasses)
# + voice_typing.bulk_delivery (AcquireResult, ShowResult, TargetUnits, map_span, rendered_equal).
# NO import of bulk_controller / daemon / ime (the controller duck-types the adapter; the watch takes
# a controller duck with halt_for_takeover — same duck-typing ime/takeover.py uses).

@dataclass(frozen=True)
class PiEditorBinding:          # the opaque AcquireResult.handle
    sock_path: str
    owned_start_u16: int        # UTF-16 offset where our fragment begins (from acquire's read; -1 ⇒ none)
    owned_len_u16: int          # length of the (possibly stale-refused → always 0 at bind) owned range
    revision: int               # client-side revision counter (CRITICAL #12)

class PiEditorClient:           # transport duck — mirrors ImeProcess.request + manager's event split
    def __init__(self, sock_path, *, on_event=None): ...
    def connect(self, timeout=1.0) -> bool        # False on ENOENT/stale (CRITICAL #5 taxonomy)
    def request(self, op, timeout=0.25, **fields) -> dict | None   # one-in-flight lock; None on timeout/IO death
    def start_events(self) -> None                # reader thread: {"event":…} → on_event(dict) (CRITICAL #1)
    def close(self) -> None                       # idempotent; joins the reader briefly

class PiEditorTarget:            # implements DeliveryTarget (runtime_checkable)
    units = TargetUnits.UTF16_UNITS
    # state: _client, _binding, _last_applied_span, _owned_start_u16 (advances on applied),
    #        _owned_utterance / _closed_utterances, last_reason  (mirror ime/target.py's fields)

class PiEditorTakeoverWatch:     # latch — mirror ime/takeover.py TakeoverWatch (:196-260)
    # attach(client) wires client.on_event → on_event; feed maps {"event":"takeover","source":s}
    # → "pi-editor {source} takeover"; _revoke calls controller.halt_for_takeover(reason) ONCE.
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/pi_editor.py — PiEditorClient transport FIRST.
  - IMPLEMENT: connect (ENOENT/ECONNREFUSED → False), request (send JSONL + "\n", bounded read of one
    reply line via the reader/timeout discipline — CRITICAL #10, NO unbounded makefile), one-in-flight
    lock, event routing (dispatch on "event" key BEFORE reply matching — CRITICAL #1), close.
  - FOLLOW pattern: voice_typing/ime/manager.py request/_read_loop/_dispatch (:219, :288-341) minus
    subprocess management; JSONL framing per voice_typing/ctl.py's ControlServer house style.
  - NAMING: PiEditorClient.request(op, timeout=…, **fields) — SAME duck shape tests/ime use.
  - PLACEMENT: voice_typing/pi_editor.py (single module; small enough — do NOT create a package).

Task 2: EXTEND voice_typing/pi_editor.py — PiEditorTarget (the DeliveryTarget).
  - IMPLEMENT acquire(): connect + {"op":"read"} → the CRITICAL #5 refusal chain → PiEditorBinding;
    show(): guard order = not-acquired → utterance-closed → zero-diff(rendered_equal, NO request) →
    revision-regression → insert-vs-replace (span startswith owned ⇒ {"op":"insert","text":delta};
    else {"op":"replace","start":owned_start,"end":owned_start+len_utf16(owned),"text":span}) →
    honest reply mapping (None ⇒ UNKNOWN; ok&applied ⇒ advance state; ok&refused ⇒ REFUSED+reason;
    ok:false ⇒ REFUSED with the error string); finalize(): matching ⇒ settle WITHOUT a request
    (ownership ends, utterance closed), differing ⇒ delegate to show then settle; leave(): CRITICAL #7;
    cancel(): CRITICAL #8. last_reason set on EVERY non-applied return.
  - FOLLOW pattern: voice_typing/ime/target.py guard-for-guard (cited lines in refs); the module
    docstring = Mode A R.3 contract in ime/target.py's style (delivery model, taxonomy, event-count
    law, units, refusal list, password/selection limitation, cursor-is-row/col note).
  - TEST as you go: after this task, Task 4's fake-client tests must pass unmodified.

Task 3: EXTEND voice_typing/pi_editor.py — PiEditorTakeoverWatch.
  - IMPLEMENT: attach(client), on_event(ev) → reason → ONE controller.halt_for_takeover(reason)
    (duck-typed controller, never imported), latch + log-and-drop subsequent, close().
  - FOLLOW pattern: voice_typing/ime/takeover.py TakeoverWatch (:196-260).

Task 4: CREATE tests/test_pi_editor.py — _FakeClient taxonomy suite.
  - IMPLEMENT: _FakeClient (scripted replies per op + a queue of injectable events; request() duck)
    mirroring tests/test_ime_target.py's _FakeProc; pin EVERY branch: each acquire refusal (absent /
    no-reply / dirty / stale-owned / missing-fields / inconsistent-range); zero-diff ⇒ UNCHANGED +
    zero requests sent; insert op = {"op":"insert"} with delta only; replace op carries map_span
    UTF-16 offsets incl. astral 🫡 (assert EXACT offsets vs map_span ground truth); None ⇒ UNKNOWN and
    the op is never re-sent; finalize matching ⇒ NO request + duplicate final ⇒ "utterance closed";
    cancel nothing-pending ⇒ UNCHANGED no request; leave ⇒ no requests after, idempotent; takeover
    event ⇒ exactly ONE halt with the fixed reason, second latched; revision regression refused.
  - FOLLOW pattern: tests/test_ime_target.py (branch-per-test, scripted fakes, no real sockets).
  - COVERAGE: every last_reason string asserted verbatim (the machine-readable taxonomy is the API).

Task 5: EXTEND tests/test_pi_editor.py — socket-level suite (in-process fake extension).
  - IMPLEMENT: a threading AF_UNIX JSONL server on tmp_path honoring S1 protocol v1 (insert/replace/
    cancel/read + takeover push), monkeypatched XDG_RUNTIME_DIR; drive arm→acquire→show(insert)→
    show(replace)→finalize→cancel; server pushes a takeover mid-session → watch halts once; server
    death mid-op ⇒ UNKNOWN. Every wait via _wait_for (tests/test_control_socket.py helper pattern,
    copied locally); NO real pi, NO .pi/, NO daemon.
  - RUN: timeout 180 .venv/bin/python -m pytest tests/test_pi_editor.py -q   (bash timeout 240)

Task 6: VALIDATE — the full Validation Loop L1–L4. No git commit unless directed; if asked:
  "P1.M5.T1.S2: daemon-side pi-editor TargetAdapter (bulk delivery route 2)".
```

### Implementation Patterns & Key Details

```python
# The show() decision core (the ONLY place op selection happens; mirror ime/target.py:131-230):
def show(self, session, utterance, seq, expected_revision, span) -> ShowResult:
    if self._binding is None:
        self.last_reason = "not acquired"; return ShowResult.REFUSED
    if utterance in self._closed_utterances:
        self.last_reason = "utterance closed"; return ShowResult.REFUSED
    if rendered_equal(self._last_applied_span, span):
        return ShowResult.UNCHANGED                      # ZERO events, ZERO requests (R.1)
    if not isinstance(expected_revision, int) or expected_revision < self._binding.revision:
        self.last_reason = "revision regression"; return ShowResult.REFUSED
    owned = self._last_applied_span
    if span.startswith(owned):
        op = {"op": "insert", "text": span[len(owned):]}                 # pure extension: 1 insert
    else:
        s = self._owned_start_u16
        e = s + map_span(owned, 0, len(owned), TargetUnits.UTF16_UNITS)[1]  # len in UTF-16 units
        op = {"op": "replace", "start": s, "end": e, "text": span}       # ONE atomic correction
    r = self._client.request(**op, timeout=_SHOW_TIMEOUT_S)              # deadline honesty, never retry
    if r is None:
        self.last_reason = "pi socket no reply"; return ShowResult.UNKNOWN
    if r.get("result") == "applied":
        self._last_applied_span = span; self._owned_start_u16 = ...      # advance ONLY on applied
        return ShowResult.APPLIED
    if r.get("result") == "refused":
        self.last_reason = r.get("reason", "editor refused"); return ShowResult.REFUSED
    if r.get("result") == "unchanged":
        return ShowResult.UNCHANGED
    self.last_reason = f"editor result {r.get('result')!r}"; return ShowResult.UNKNOWN

# The reader-thread dispatch (CRITICAL #1 — events NEVER parse as replies):
def _on_line(self, line: str) -> None:
    obj = json.loads(line)
    if "event" in obj:                 # id-less, unsolicited → takeover path
        cb = self._on_event
        if cb: cb(obj)
        return
    with self._reply_cv:               # else it is the pending request's reply
        self._pending_reply = obj; self._reply_cv.notify_all()
```

### Integration Points

```yaml
CONSUMES (read-only):
  - S1's socket contract: $XDG_RUNTIME_DIR/voice-typing/pi-editor.sock, protocol v1 (ops/replies/events)
  - voice_typing/bulk_delivery.py — DeliveryTarget, ShowResult, AcquireResult, map_span, rendered_equal
  - voice_typing/ime/{target,takeover,manager}.py — patterns only (no imports)
PRODUCES (the downstream contract):
  - voice_typing/pi_editor.py: PiEditorClient + PiEditorTarget (a DeliveryTarget) + PiEditorTakeoverWatch
  - consumed by P1.M5.T2.S1 (G3 pi-prompt row) and P1.M6.T2.S1 (daemon wiring behind output.delivery)
DOES NOT TOUCH:
  - bulk_controller.py, bulk_delivery.py, daemon.py, .pi/** (S1's), tests/ime_*/G3 labs, pyproject, .gitignore
PARALLEL-SAFE: S1 (in flight) writes .pi/extensions/* + tests/pi_seam_* + architecture/pi_seam_proof.md —
  zero path overlap with this item's two files; neither reads the other's outputs (only the PRP contract).
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 60 .venv/bin/python -c "import voice_typing.pi_editor" && echo "imports clean"
ruff check voice_typing/pi_editor.py tests/test_pi_editor.py --fix && \
  ruff format voice_typing/pi_editor.py tests/test_pi_editor.py   # zero errors (repo gate; no mypy)
grep -c "DeliveryTarget\|ShowResult\|map_span" voice_typing/pi_editor.py   # ≥3 (imports the contracts)
```

### Level 2: Unit Tests (THE gate)

```bash
timeout 180 .venv/bin/python -m pytest tests/test_pi_editor.py -q          # (bash timeout 240)
# Expected: all green; every refusal branch + zero-diff-no-request + utf16 offsets + takeover latch pinned.
# Regression (adds-files-only proof):
timeout 240 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_bulk_controller.py \
  tests/test_ime_target.py -q                                              # (bash timeout 300)
```

### Level 3: Protocol-shape audit (contract invariants, grep-provable)

```bash
grep -n '"op"' voice_typing/pi_editor.py | grep -v 'insert\|replace\|cancel\|read' || echo "ok: closed op set"
grep -n 'map_span' voice_typing/pi_editor.py | head -5        # utf16 math routed through map_span
grep -nE '\blen\(owned\)\s*\+' voice_typing/pi_editor.py || echo "ok: no raw-len offsets"
grep -n 'UNKNOWN' voice_typing/pi_editor.py | grep -ci 'retry\|resend' || echo "ok: unknown never retried"
.venv/bin/python -c "
from voice_typing import pi_editor
from voice_typing.bulk_delivery import DeliveryTarget
t = pi_editor.PiEditorTarget.__new__(pi_editor.PiEditorTarget)
assert isinstance(t, DeliveryTarget), 'Protocol not satisfied'
print('ok: DeliveryTarget satisfied')"
```

### Level 4: Isolation + hygiene

```bash
grep -nE 'subprocess|popen|voicectl|systemctl|RealtimeSTT|torch' voice_typing/pi_editor.py || echo "ok: pure transport+adapter"
git status --porcelain    # exactly: voice_typing/pi_editor.py + tests/test_pi_editor.py (and this plan/ dir)
timeout 120 .venv/bin/python -m pytest tests/test_pi_editor.py -q -p no:cacheprovider 2>&1 | tail -1   # repeat-run stability (no leaked threads/sockets)
```

## Final Validation Checklist

### Technical Validation

- [ ] L1: imports clean; ruff zero errors; contracts imported (not restated).
- [ ] L2: `tests/test_pi_editor.py` green; bulk + ime suites green (adds-only proof).
- [ ] L3: closed op set; map_span-routed UTF-16 math; no raw-len offsets; UNKNOWN never retried;
      `isinstance(PiEditorTarget(...), DeliveryTarget)` passes.
- [ ] L4: no subprocess/daemon/engine imports; git status = the two new files; repeat run stable.

### Feature Validation

- [ ] Success Definition (a)–(f) all demonstrated by the test suites.
- [ ] Every `last_reason` string asserted verbatim in tests (the machine-readable taxonomy).
- [ ] Zero-diff ⇒ zero requests; leave ⇒ zero post-stop writes; takeover ⇒ exactly one halt.
- [ ] Astral-character offsets equal `map_span` ground truth (UTF-16 surrogate pairs).

### Code Quality Validation

- [ ] Mirrors ime/target.py guard order and docstring discipline; no new patterns invented.
- [ ] Reader thread bounded, daemon-threaded, joined on close; no unbounded makefile reads.
- [ ] Anti-patterns below avoided.

### Documentation & Deployment

- [ ] Mode A module docstring carries the R.3 contract (delivery model, taxonomy, event-count law,
      units, refusal list, documented password/selection + cursor-row/col limitations).
- [ ] No config surface added (selection/wiring is M6.T2 — out of scope).

---

## Anti-Patterns to Avoid

- ❌ Don't restate the ShowResult/AcquireResult vocabulary — import it from `bulk_delivery`.
- ❌ Don't compute offsets with `len()` or on normalized/lowercased strings — always `map_span` on the
  ORIGINAL string (UTF-16 surrogate pairs; the R.3 index-desync rule).
- ❌ Don't retry, resend, or "repair" after UNKNOWN/timeout — the controller disarms; a may-have-landed
  op is never repeated (R.5).
- ❌ Don't send ANY request for a zero-diff, a matching finalize, a nothing-pending cancel, or after
  leave — each of those is a zero-event outcome by contract.
- ❌ Don't let an event line parse as a reply (dispatch on "event" first; serialize one request in flight).
- ❌ Don't trust the adapter to enforce the 250 ms deadline — the controller owns it; the adapter only
  reports honestly and fast.
- ❌ Don't parse cursor {row,col} as an offset — owned-range UTF-16 offsets are the only position truth.
- ❌ Don't modify bulk_controller/bulk_delivery/daemon/.pi/ime files; don't add config keys; don't
  touch S1's or M4.T5's files (parallel + scope fences).
- ❌ Don't run real pi, the daemon, voicectl, or anything desktop-side in tests — fakes + in-process
  AF_UNIX on tmp_path only (R.7).
- ❌ Don't use unbounded socket reads (the ctl.py makefile hang) or un-waited threads; every test wait
  is `_wait_for`-bounded and every run is under both AGENTS.md timeouts.

---

## Confidence Score

**9/10.** The structural template (ImeTarget + its 943-line taxonomy-pinned test file) is proven and
read line-by-line this session; the input socket contract is fully specified in S1's PRP (ops, reply
shapes, events, units — stable v1, mirrored from the ShowResult vocabulary); the controller's
consumption surface and deadline ownership were verified from source; and the only novel mechanics
(no-id-echo JSONL framing with an event split, UTF-16 offset math) are covered by explicit gotchas +
pinned tests. Residual -1: S1 is still in flight — if its landed protocol drifts from the PRP
(e.g. reply field names), the fake-client tests encode the PRP shapes and would need a one-line
update; the socket-level suite would catch it immediately against S1's real extension at M5.T2.

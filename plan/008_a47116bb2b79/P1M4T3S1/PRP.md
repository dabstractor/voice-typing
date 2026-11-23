# PRP — P1.M4.T3.S1: `show()` INSERT path — one atomic `commit_string`+`commit` (`voice_typing/ime/target.py` evolves)

## Goal

**Feature Goal**: Ship the **insert path** of the IM-v2 adapter's `show()` (PRD §4.2sexies R.3/R.4:
route DECIDED — insert = `commit_string`+`commit`, ZERO typing fallback): the daemon-side
`ImeTarget.show(session, utterance, seq, expected_revision, span) -> ShowResult` that the landed
bulk controller already calls. One pure-extension delta → ONE atomic insert commit; **zero-diff ⇒
zero events**; **recheck-at-mutation** (T2.S1's `recheck`) before every request; **≤4000 B/commit**
(the engineering rule — larger ⇒ refused with a reason, never silently chunked); honest result
mapping **applied | unchanged | refused | unknown** where "applied" means the COMPOSITOR confirmed
(host `dones` increment), not bytes-sent; the **250 ms deadline** honored end-to-end (request
timeout 0.25 s + receiver-side confirm wait ≤0.22 s). The host half (`_show`, `before=0`) is
already landed (S1, `ime_host.py:154-177`); this task ships the daemon half + the deadline
constant check.

**Deliverable** (2 evolved files + 2 test files; everything else fenced):
1. `voice_typing/ime/target.py` — **EVOLVE** (T2.S1 lands it first; preflight gates on it): add
   `ShowResult`/`rendered_equal` imports; add insert-delivery state to `__init__`; 3 lines in
   `acquire()` (remember the binding + reset insert state); add the `show()` insert-path method
   + 3 module constants. Existing acquire/recheck/binding_caret_after/to_bytes_span semantics
   UNCHANGED.
2. `tests/test_ime_target.py` — **APPEND** ~13 fake-proc show() cases (T2.S1's bodies untouched).
3. `voice_typing/ime/ime_host.py` — **CONDITIONAL** one-constant change: lower `SHOW_CONFIRM_WAIT`
   to 0.22 ONLY if preflight finds it larger (receiver-side validation must land before the
   daemon's 0.25 s give-up). T2.S1 doesn't touch `_show`/this constant → no conflict.
4. `tests/ime_show_lab.py` — **CREATE** (optional evidence, NON-collected): env-gated GTK insert
   row (`IME_SHOW_LAB=1`), private seat, per the im-lab pattern.

**Success Definition**:
- (a) `timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py
  tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_bulk_delivery.py
  tests/test_bulk_controller.py -q` → all green; `git status --porcelain` shows ONLY the files
  above (3 + optional 1).
- (b) `show()` is the landed `DeliveryTarget` protocol signature (`bulk_delivery.py:132-140`) and
  returns `ShowResult`. Order-pinned semantics: **zero-diff** (`rendered_equal`) ⇒ `UNCHANGED`,
  NO request; **non-extension span** ⇒ `REFUSED` (correction = T3.S2), NO request; **recheck
  failure** ⇒ `REFUSED` + that reason, NO request; **delta >4000 B** ⇒ `REFUSED` (cap reason),
  NO request; else ONE `request("show", timeout=0.25, <all SHOW_FIELDS>, text=delta, before=0)`.
- (c) Result mapping: reply `applied` ⇒ `APPLIED` AND state advances (`_last_applied_span=span`,
  `_inserted_bytes += len(delta.encode())`); `refused` ⇒ `REFUSED`; anything else or `None`
  (timeout/death) ⇒ `UNKNOWN`; **state advances ONLY on APPLIED** (a later show after a
  refused/unknown still diffs against the last APPLIED span).
- (d) Recheck is called with the CUMULATIVE `inserted_bytes` of everything this acquisition has
  committed (UTF-8 bytes; an astral char counts 4 — test-pinned), proving the caret arithmetic.
- (e) Every REFUSED/UNKNOWN records a machine-readable `self.last_reason` (test-pinned: not
  acquired / zero-diff is not a refusal / recheck:<reason> / commit cap / correction not
  implemented / host:<result>) and logs carry **counts and times, never recognition text** (R.5).
- (f) Deadline budget: the show request passes `timeout=0.25` (asserted); the host's
  `SHOW_CONFIRM_WAIT` ≤ 0.22 after Task 3.
- (g) Fences: NO correction-path sends (`before>0` never originates here — T3.S2), NO
  finalize/leave/cancel (T3.S3), NO takeover (T4), NO manager/controller/daemon/feedback/ctl/
  config/protocol.py/wlwire.py/tools-im-lab edits, `bulk_controller.py`/`bulk_delivery.py`
  consumed read-only.

## User Persona

**Target User**: Internal — **bulk_controller** (landed, M3) is the direct caller of
`show()`; **P1.M4.T3.S2** (correction) extends the same method with the `before>0` branch;
**P1.M6.T2.S1** constructs `ImeTarget(ImeProcess(...))` and arms bulk delivery. No end-user
surface changes.

**Use Case**: Bulk mode armed on a GTK field: acquire binds the caret; the controller enqueues the
first partial → `show(..., span="hello")` → zero-diff vs `""`? no → pure extension → recheck
(caret still at binding+offset 0, no selection, prefix intact) → delta `"hello"` ≤4000 B → one
`commit_string("hello")`+`commit` → host sees the `done` ⇒ reply `applied` ⇒ `APPLIED`, state
advances. Next partial `"hello world"` → delta `" world"`, recheck with cumulative 5 B. The user
selects text mid-stream → recheck ⇒ `REFUSED "recheck: user selection present"`, NO request — the
controller disarms. A compositor hiccup ⇒ reply late/none ⇒ `UNKNOWN` — never retried (R.5).

**Pain Points**: (1) The controller's `DeliveryTarget.show()` has no IM implementation — bulk
delivery cannot run. (2) bytes-sent≠applied and unknown≠delivered are easy to fake and fatal to
fake (silent text loss / double inserts). (3) A >4000 B payload chunked naively = N visible edits
= event-count-law violation; a wrong caret offset = corrupted range (byte/char desync).

## Why

- **The controller is landed and waiting**: `bulk_controller.py:617,664-721` already calls
  `target.show(...)` with `expected_revision` (+1 ONLY on APPLIED, :442-445) and disarms on
  refused/unknown. T3.S1 is the missing half of the M3↔M4 contract.
- **The host machinery is proven**: `_show` (`ime_host.py:154-177`) performs the atomic
  insert/replace commit and maps applied via a compositor `done` (dones increment) within
  `SHOW_CONFIRM_WAIT` — lab-proven 26–40 ms cmd→field, ZERO key events (R.2; a delivery commit can
  never self-trigger the T4 takeover listener).
- **Insert-first is the R.4 order**: "Prove insert AND correct before any mic integration" —
  corrections are T3.S2; this adapter HONESTLY refuses what it doesn't implement rather than
  approximating it with per-character typing (forbidden in this mode).
- **Safety lives in the ordering**: zero-diff before any request (event-count law: zero-diff = 0
  events); recheck before mutation (R.5); cap before the wire; state advance only on applied
  (double-delivery guard); unknown never retried (R.5).

## What

Per the research note §3 (pinned algorithm). The exact source is in Implementation Blueprint.

### Success Criteria

- [ ] All 4 files as specified; the combined suites green under `timeout 120`; scope guard clean.
- [ ] The ordering pinned: zero-diff → extension-check → recheck → cap → request; each refusal
      branch provably sends NO show request.
- [ ] Result mapping + state-advance-only-on-applied + cumulative inserted_bytes pinned.
- [ ] `timeout=0.25` on the request and `SHOW_CONFIRM_WAIT ≤ 0.22` asserted.
- [ ] `last_reason` taxonomy pinned; logs carry counts/times, never text.
- [ ] Optional GTK row runs only under `IME_SHOW_LAB=1`; default pytest never collects it.

## All Needed Context

### Context Completeness Check

_Pass._ The consumed surfaces are landed-and-anchored (protocol SHOW_FIELDS `protocol.py:37,40,79-93`;
host `_show` semantics `ime_host.py:154-177`; `ShowResult`/`DeliveryTarget.show`/`rendered_equal`
`bulk_delivery.py:77-89,114-158,220+`; controller expectations `bulk_controller.py:44-45,442-445`);
the T2.S1 acquire/recheck contract is pinned as landed (preflight gates on it); the `show()` source
is pinned verbatim below; tests are case-enumerated; the 4000 B rule + 26–40 ms/zero-key-events
evidence is cited from R.2 (do-not-re-derive).

### Documentation & References

```yaml
# MUST READ — this task's design record (algorithm, deadlines, fences).
- docfile: plan/008_a47116bb2b79/P1M4T3S1/research/ime_insert_path_design.md
  section: "ALL. §0 task shape (host half landed), §1 consumed-contract anchors, §2 wire facts
            (4000 B rule; 26-40 ms; zero key events), §3 the pinned algorithm, §4 deadline budget,
            §5 test matrix, §6 fences."

# MUST READ — the file being EVOLVED (T2.S1's, gated by preflight).
- file: voice_typing/ime/target.py
  why: "Add to the bulk_delivery import: ShowResult, rendered_equal. Add __init__ state:
        _binding/_last_applied_span/_inserted_bytes/last_reason. Add 3 lines at acquire()'s
        SUCCESS return (store binding + reset insert state). Append show() per the Blueprint."
  gotcha: "Do NOT alter acquire's refusal taxonomy, recheck, binding_caret_after, to_bytes_span,
           or _ACQUIRE_TIMEOUT_S (T2.S1's, test-pinned). Byte arithmetic ONLY via
           .encode('utf-8') on ORIGINAL strings."

# MUST READ — the host half + the deadline constant.
- file: voice_typing/ime/ime_host.py
  why: "_show :154-177 (before=0 insert path; applied = dones increment; SHOW_CONFIRM_WAIT bound).
        Task 3 touches ONLY the SHOW_CONFIRM_WAIT constant if > 0.22 — nothing else."
  gotcha: "T2.S1 is editing _acquire/_verify in parallel-then-merged; this task must NOT touch
           those methods or _SNAPSHOT_HEAD_BYTES/_SURROUND_WAIT_S."

# MUST READ — the vocabulary + protocol the adapter must satisfy exactly.
- file: voice_typing/bulk_delivery.py
  why: "ShowResult :77-89 (UNCHANGED = zero events; UNKNOWN never retried), DeliveryTarget.show
        :114-140 (signature; span = COMPLETE rendered span), rendered_equal :220+ (spacing-only
        render equality — consume, don't reimplement), map_span/TargetUnits (T2.S1 already
        imports)."
- file: voice_typing/ime/protocol.py
  why: "SHOW_FIELDS :40 — validate_request :79-93 REQUIRES session/utterance/seq/expected_revision/
        text on EVERY show request; extra fields (before) ride free. Replies tolerate extra fields."

# MUST READ — the caller's contract (read-only).
- file: voice_typing/bulk_controller.py
  why: ":44-45,442-445 expected_revision +1 ONLY on APPLIED; :617,664-721 the show() call sites;
        refused/unknown stop delivery — the adapter must never advance state on a non-applied
        result (the controller would desync its revision)."
  gotcha: "FENCED — do not edit. If a controller test fails, the adapter's mapping is wrong."

# CONTRACT — the predecessor PRP (assume landed; preflight verifies).
- docfile: plan/008_a47116bb2b79/P1M4T2S1/PRP.md
  why: "ImeTarget/FieldBinding/recheck(...)->(ok,reason,rev)/to_bytes_span semantics + the
        _FakeProc pattern (:Implementation Patterns) this task's tests reuse."

# READ — grounding + PRD + discipline.
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  section: "§9 risks (4000-byte cap noted; GTK 1-2 changed-signals-per-commit is EXPECTED)."
- docfile: PRD.md
  section: "§4.2sexies R.2 (evidence; do-not-re-derive), R.3 (show contract), R.4 (route DECIDED),
            R.5 (result taxonomy, mutation-time re-checks, never-retry, logs w/o text)."
- docfile: AGENTS.md
  section: "Rules 1-3 (GNU timeout everywhere; .venv/bin/python; never the live desktop)."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/ime/                       # protocol.py, wlwire.py, ime_host.py (S1) + target.py (T2.S1, gated)
voice_typing/bulk_delivery.py           # READ-ONLY vocabulary
voice_typing/bulk_controller.py         # READ-ONLY caller (M3, landed)
tests/test_ime_target.py                # T2.S1's suite — APPEND here
tests/ime_acquire_lab.py                # T2.S1's env-gated driver — pattern for ours (untouched)
tools/im-lab/                           # FENCED evidence
# NOT YET: tests/ime_show_lab.py
```

### Desired Codebase tree

```bash
voice_typing/ime/target.py          # EVOLVE: +show() insert path, +3 constants, +state, +3 acquire lines
tests/test_ime_target.py            # APPEND ~13 show() cases
voice_typing/ime/ime_host.py        # CONDITIONAL: SHOW_CONFIRM_WAIT → 0.22 (only if currently larger)
tests/ime_show_lab.py               # CREATE: env-gated GTK insert row (optional evidence)
```

### Known Gotchas

```python
# CRITICAL #1 — STATE ADVANCES ONLY ON APPLIED. A refused/unknown must leave _last_applied_span/
#   _inserted_bytes untouched (the controller disarms; a stale advance would double-insert on the
#   next arm). Pin with: refused → next show still sends the delta vs the last APPLIED span.
# CRITICAL #2 — ZERO-DIFF BEFORE ANYTHING. rendered_equal(last, span) ⇒ UNCHANGED, ZERO requests —
#   the R.1 event-count law (zero-diff = 0 events). The guard is spacing-normalization-only by
#   contract; consume bulk_delivery.rendered_equal, never reimplement.
# CRITICAL #3 — NON-EXTENSION = REFUSED, NOT A GUESSED CORRECTION. span must startswith the last
#   APPLIED span (ORIGINAL strings). Otherwise REFUSE (correction = T3.S2). Sending before>0 from
#   this task is out of scope; approximating a correction with N inserts is FORBIDDEN (event law).
# CRITICAL #4 — UTF-8 BYTES EVERYWHERE. delta length, cap check, and inserted_bytes all use
#   .encode("utf-8") on ORIGINAL strings; recheck expects BYTES (an astral char = 4).
# CRITICAL #5 — THE 4000 B CAP IS PER COMMIT. delta.encode() > 4000 ⇒ REFUSED (never chunk inside
#   show(): N chunks = N visible edits = event-law violation; the item allows refuse-with-reason).
# CRITICAL #6 — DEADLINE BUDGET. request timeout=0.25 (assert); host SHOW_CONFIRM_WAIT ≤ 0.22
#   (Task 3) so the receiver's verdict precedes the caller's give-up. Never raise these to "be
#   safe" — the controller's 250 ms failure deadline is landed (M3.T2.S2).
# CRITICAL #7 — ALL SHOW_FIELDS ON EVERY REQUEST. validate_request rejects a show missing any of
#   session/utterance/seq/expected_revision/text. before=0 rides as the extra field (tolerated).
# CRITICAL #8 — LOGS: counts + times, NEVER the delta text (R.5). last_reason carries taxonomy.
# GOTCHA #9 — a reply with no/odd "result" field ⇒ UNKNOWN (defensive), never a crash.
# GOTCHA #10 — the lab driver: no test_ prefix, IME_SHOW_LAB=1 gate, timeout 300, private seat
#   (xvfb-run + dbus-run-session + sway), mktemp scratch + EXIT trap (AGENTS.md Rule 3).
# GOTCHA #11 — GNU timeout + .venv/bin/python on EVERY command (AGENTS.md Rule 1; zsh aliases).
```

## Implementation Blueprint

### Data models and structure

No new dataclasses. Adapter state: `_binding: FieldBinding|None`, `_last_applied_span: str`,
`_inserted_bytes: int`, `last_reason: str`; constants `_SHOW_TIMEOUT_S=0.25`,
`_COMMIT_CAP_BYTES=4000`.

### `show()` reference implementation (implement verbatim; acquire/init additions below)

```python
_SHOW_TIMEOUT_S = 0.25      # fits the controller's 250 ms failure deadline (M3.T2.S2)
_COMMIT_CAP_BYTES = 4000    # ≤4000 B/commit — engineering rule (item contract; origin unresolved)

    # __init__ additions (after T2.S1's lines):
        self._binding: "FieldBinding | None" = None
        self._last_applied_span = ""      # the last APPLIED complete rendered span ("" until applied)
        self._inserted_bytes = 0          # cumulative UTF-8 bytes WE committed this acquisition
        self.last_reason = ""             # machine-readable refusal/unknown taxonomy (R.5 logs)

    # acquire(): 3 lines inserted at the SUCCESS return (before `return AcquireResult(ok=True, ...)`):
        self._binding = binding
        self._last_applied_span = ""
        self._inserted_bytes = 0

    def show(self, session: int, utterance: str, seq: int,
             expected_revision: int, span: str) -> ShowResult:
        """Insert path (R.3/R.5; P1.M4.T3.S1): extend our confirmed span at the caret.

        ONE atomic commit per change: commit_string(delta) + commit. Zero-diff ⇒ zero events.
        Corrections (non-extension spans) are REFUSED here — the correction path is P1.M4.T3.S2.
        State advances ONLY on applied; unknown is never retried by the caller (controller).
        """
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        # (1) zero-diff guard FIRST — render-equal ⇒ ZERO events (R.1 event-count law)
        if rendered_equal(self._last_applied_span, span):
            return ShowResult.UNCHANGED
        # (2) insert condition: pure extension of the last APPLIED span, on ORIGINAL strings
        if not span.startswith(self._last_applied_span):
            self.last_reason = "correction not implemented (P1.M4.T3.S2)"
            return ShowResult.REFUSED
        delta = span[len(self._last_applied_span):]
        # (3) mutation-time re-check (R.5): fresh verify — activation/caret/selection/adjacency
        ok, reason, _rev = self.recheck(binding, inserted_bytes=self._inserted_bytes)
        if not ok:
            self.last_reason = f"recheck: {reason}"
            return ShowResult.REFUSED                 # NO request sent
        # (4) the per-commit byte cap (engineering rule; never chunk inside show())
        delta_bytes = len(delta.encode("utf-8"))
        if delta_bytes > _COMMIT_CAP_BYTES:
            self.last_reason = f"commit cap {_COMMIT_CAP_BYTES}B exceeded ({delta_bytes}B)"
            return ShowResult.REFUSED                 # NO request sent
        # (5) ONE atomic insert: commit_string(delta) + commit   (before=0 → no delete)
        r = self._proc.request("show", timeout=_SHOW_TIMEOUT_S, session=session,
                               utterance=utterance, seq=seq, expected_revision=expected_revision,
                               text=delta, before=0)
        # (6) honest mapping — bytes-sent ≠ applied; None/odd ⇒ unknown; never retry (R.5)
        if r is None:
            self.last_reason = "ime no reply"
            logger.warning("ime show: no reply (session=%s seq=%s span_chars=%d)",
                           session, seq, len(span))
            return ShowResult.UNKNOWN
        result = r.get("result")
        if result == "applied":
            self._last_applied_span = span            # advance ONLY on applied (Critical #1)
            self._inserted_bytes += delta_bytes
            self.last_reason = ""
            logger.info("ime show applied: session=%s seq=%s delta_bytes=%d t_ms=%s total=%d",
                        session, seq, delta_bytes, r.get("t_ms"), self._inserted_bytes)
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = "host refused"
            return ShowResult.REFUSED
        self.last_reason = f"host result {result!r}"
        logger.warning("ime show unknown: session=%s seq=%s result=%r", session, seq, result)
        return ShowResult.UNKNOWN
```

(`logger = logging.getLogger(__name__)` — add if T2.S1 didn't. Import additions:
`ShowResult, rendered_equal` join `AcquireResult, TargetUnits, map_span`.)

### Implementation Tasks

```yaml
Task 0: PREFLIGHT (no mutation)
  - RUN:
      test -f voice_typing/ime/target.py && test -f tests/test_ime_target.py && echo ok \
        || echo "PREFLIGHT FAIL: P1.M4.T2.S1 not landed — STOP"
      env -u WAYLAND_DISPLAY .venv/bin/python -c "from voice_typing.ime.target import ImeTarget, \
FieldBinding; assert hasattr(ImeTarget,'acquire') and hasattr(ImeTarget,'recheck'); print('T2.S1 ok')"
      grep -n "SHOW_CONFIRM_WAIT" voice_typing/ime/ime_host.py    # RECORD the value (Task 3 input)
      timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py \
        tests/test_ime_protocol.py tests/test_bulk_delivery.py tests/test_bulk_controller.py -q | tail -1
  - EXPECTED: T2.S1 landed + all green. If target.py lacks acquire/recheck → STOP (dependency).

Task 1: tests/test_ime_target.py — APPEND the show() matrix FIRST (TDD RED). Reuse the file's
        _FakeProc (records (cmd, timeout, fields); scripted replies; None = no reply). Cases:
        not-acquired → REFUSED "not acquired", no request;
        zero-diff exact → UNCHANGED, zero requests; render-equal (spacing-only diff) → UNCHANGED;
        pure extension → request once: cmd show, timeout==0.25, before==0, ALL SHOW_FIELDS
          present, text==delta only → reply applied → APPLIED + state advanced;
        second extension after APPLIED → delta == only the new part; the fake's verify reply
          proves recheck got inserted_bytes == bytes(first delta) (cumulative; astral char = 4);
        reply unknown / refused / None / missing "result" → UNKNOWN / REFUSED / UNKNOWN / UNKNOWN;
        recheck caret-moved (with inserted_bytes>0 in the fake's assert) → REFUSED
          "recheck: caret moved" AND no show request in proc.calls;
        recheck selection → REFUSED; delta >4000 B (build a 4001-ASCII-char span) → REFUSED cap,
          no request; non-extension span (e.g. "xello" after "hello") → REFUSED correction, no
          request; state NOT advanced: after a refused/unknown, a retry-identical show still
          computes delta vs the last APPLIED span;
        last_reason taxonomy asserted on each refusal path.
        DO NOT: import manager; need WAYLAND_DISPLAY; edit T2.S1's test bodies.

Task 2: EVOLVE voice_typing/ime/target.py per the Blueprint (imports + state + 3 acquire lines +
        show()) → the appended suite GREEN.

Task 3: HOST DEADLINE — if the recorded SHOW_CONFIRM_WAIT > 0.22: set it to 0.22 with a comment
        ("receiver-side validation must precede the caller's 250 ms give-up; P1.M4.T3.S1").
        If already ≤ 0.22: NO host change (record the value in the commit message). Re-run
        tests/test_ime_host.py — S1's show tests must stay green.

Task 4: CREATE tests/ime_show_lab.py (optional evidence; mirror tests/ime_acquire_lab.py's
        env-gate + private-seat pattern): gate IME_SHOW_LAB=1 (else print "skipped" exit 0);
        acquire → 3 sequential inserts ("Hel", "lo w", "orld" via show()) → assert the GTK field's
        dumped text ends with "Hello world", caret at the end, edit-count grew by ≤3, zero
        grab_keys; ONE verdict line per row; mktemp scratch + EXIT trap; timeout 300.

Task 5: VALIDATE (below). Commit if directed:
        "P1.M4.T3.S1: IM show() insert path — atomic commit_string+commit, recheck-gated, 4000B cap".
```

### Integration Points

```yaml
PACKAGE SEAM (consumed downstream; nothing wired here):
  - P1.M4.T3.S2: "the non-extension branch becomes the correction path (before>0 via
                  to_bytes_span of the owned range); the insert branch stays this task's code"
  - P1.M6.T2.S1: "constructs ImeTarget(ImeProcess(...)); the controller calls show() — this
                  method IS the DeliveryTarget implementation for the IM route"
NOTHING WIRED: "no daemon/feedback/ctl/bulk_*/config/protocol.py/wlwire.py/tools-im-lab changes."
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# L1 syntax + purity
timeout 60 .venv/bin/python -m py_compile voice_typing/ime/target.py tests/test_ime_target.py \
  tests/ime_show_lab.py && echo "L1 OK"
env -u WAYLAND_DISPLAY .venv/bin/python -c "from voice_typing.ime.target import ImeTarget; \
  from voice_typing.bulk_delivery import ShowResult; print('pure import ok')"

# L2 the gate
timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py
  tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_bulk_delivery.py
  tests/test_bulk_controller.py -q | tail -1
# Expected: 0 failed. A bulk_controller failure ⇒ the adapter's mapping/state is wrong (read first).

# L3 fake duplex smoke (no compositor)
timeout 60 .venv/bin/python - <<'EOF'
from voice_typing.ime.target import ImeTarget
from voice_typing.bulk_delivery import ShowResult
class P:
    def __init__(s): s.calls=[]
    def request(s, cmd, timeout=None, **f):
        s.calls.append((cmd, timeout, f))
        if cmd == "acquire": return {"ok": True, "handle": "im", "revision": 2,
            "text": "hi ", "cursor": 3, "anchor": 3, "snapshot_truncated": False}
        if cmd == "verify":  return {"ok": True, "activated": True, "dones": 3,
            "text": "hi ", "cursor": 3, "anchor": 3, "snapshot_truncated": False}
        return {"result": "applied", "t_ms": 31.0}
p = P(); t = ImeTarget(p); a = t.acquire(); assert a.ok
r1 = t.show(1, "u1", 1, 2, "Hel"); r2 = t.show(1, "u1", 2, 3, "Hello w")
assert r1 is ShowResult.APPLIED and r2 is ShowResult.APPLIED
assert p.calls[-1][2]["text"] == "lo w" and p.calls[-1][2]["before"] == 0
assert t._inserted_bytes == 6, t._inserted_bytes
assert t.show(1, "u1", 3, 4, "Hello w") is ShowResult.UNCHANGED
print("L3 OK", len(p.calls))
EOF
# Expected: L3 OK 6  (acquire + verify + show + verify + show... zero-diff sent nothing)

# L4 scope guards + optional evidence
git status --porcelain        # ONLY: target.py(M), test_ime_target.py(M), [ime_host.py(M)], ime_show_lab.py
git diff --stat voice_typing/ime/protocol.py voice_typing/ime/wlwire.py voice_typing/bulk_delivery.py \
  voice_typing/bulk_controller.py voice_typing/daemon.py tools/im-lab | wc -l   # 0
timeout 120 .venv/bin/python -m pytest tests/ -q --collect-only 2>/dev/null | grep -c ime_show_lab || echo "ok: not collected"
timeout 300 env IME_SHOW_LAB=1 .venv/bin/python tests/ime_show_lab.py || echo "lab row failed/skipped — record honestly"
```

## Final Validation Checklist

- [ ] L1–L4 green; all listed suites pass; scope guard clean (fenced files untouched).
- [ ] Ordering pinned (zero-diff → extension → recheck → cap → request); every refusal sends NO request.
- [ ] State advances ONLY on APPLIED; cumulative UTF-8 inserted_bytes (astral = 4) proven.
- [ ] `timeout=0.25` asserted; `SHOW_CONFIRM_WAIT ≤ 0.22` (value recorded).
- [ ] `last_reason` taxonomy pinned; logs = counts/times only.
- [ ] Fences held: no `before>0` sends, no T3.S3/T4/M6 scope, no fenced-file edits.

## Anti-Patterns to Avoid

- ❌ Don't advance state on refused/unknown (double-insert class) — only on APPLIED (Critical #1).
- ❌ Don't chunk a >4000 B payload inside show() (N commits = N visible edits) — refuse (Critical #5).
- ❌ Don't send a correction from this task (`before>0` is T3.S2); don't approximate one with N
      inserts — the event-count law forbids it (Critical #3).
- ❌ Don't reimplement zero-diff or byte mapping — consume `rendered_equal`/`.encode()` on ORIGINAL
      strings (Critical #2/#4).
- ❌ Don't retry an unknown, don't edit the controller/protocol/wlwire/host `_show` body, don't let
      pytest collect the lab driver, don't run anything without GNU timeout + `.venv/bin/python`.

---

**Confidence Score: 9/10.** All consumed surfaces are landed-and-anchored (protocol/host/bulk_
delivery/controller) or pinned as the T2.S1 contract with a hard preflight gate; the `show()`
source is pinned verbatim with the ordering + state rules; the test matrix is case-enumerated;
validation commands are executable as written. −1: T3.S1 depends on T2.S1 landing first (mitigated
by the Task 0 STOP gate) and the optional GTK row depends on the disposable-desktop environment
(bounded — it is optional evidence with an honest skip path; the fake-proc suite is the gate).

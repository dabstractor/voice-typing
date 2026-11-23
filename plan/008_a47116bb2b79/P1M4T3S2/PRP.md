# PRP — P1.M4.T3.S2: `show()` CORRECTION path — one atomic range replacement (`delete_surrounding_text(before,0)`+`commit_string`+`commit`)

## Goal

**Feature Goal**: Ship the **correction path** of the IM-v2 adapter's `show()` (PRD §4.2sexies
R.3/R.4; route DECIDED — correction = `delete_surrounding_text(before,0)` + `commit_string` +
`commit(serial)` in ONE atomic commit, lab-proven byte-exact on a 1024-byte span). S1 (insert path,
in flight) lands `show()` with the placeholder branch
`REFUSED "correction not implemented (P1.M4.T3.S2)"` — **this task replaces that refusal with the
real thing and delivers the FULL `show()`**: the insert branch preserved verbatim in behavior
(S1's tests stay green) + the correction branch for ANY non-extension span. Corrections are
**verified-owned-range replacements**: recheck proves the caret sits at the END of our owned range
(a delete counts backward from the caret — anything else would eat user text); a NEW
`_owned_region_intact()` guard re-reads the snapshot and proves the range's CURRENT content is
still exactly ours; the request carries `before = len(owned.encode())` (UTF-8 bytes — the wire's
units) + `text = the FULL corrected span`; correction reach is bounded by **OWNERSHIP, never
size** (user decision 2026-11-19 — the whole owned range may be replaced in one commit); an
**unchunkable** correction (> 4000 B span) is REFUSED with a `delivery_reason`, never silently
chunked (N chunks = N visible edits = event-count-law violation); the `expected_revision` guard
(pass-through + a local regression check); honest mapping `applied|unchanged|refused|unknown`
with **state advancing ONLY on APPLIED** (the controller +1s expected_revision only on applied).

**Deliverable** (2 evolved files + 1 optional; everything else fenced):
1. `voice_typing/ime/target.py` — **EVOLVE** (S1's show() is the base; preflight gates on it):
   replace the `"correction not implemented"` refusal branch with the correction path; add the
   `_owned_region_intact()` private helper (~8 lines); add the revision-regression guard. The
   insert branch, ordering, state rules, and constants are S1's — behavior unchanged.
2. `tests/test_ime_target.py` — **APPEND** ~15 correction cases (S1/T2.S1 bodies untouched).
3. `tests/ime_correction_lab.py` — **CREATE** (optional evidence, NON-collected): env-gated GTK
   correction row (`IME_CORRECTION_LAB=1`), incl. the >1024 B byte-exact replacement, per the
   im-lab pattern.

**Success Definition**:
- (a) `timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py
  tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_ime_manager.py
  tests/test_bulk_delivery.py tests/test_bulk_controller.py -q` → all green (S1's insert tests
  included — no regression); `git status --porcelain` shows ONLY the files above.
- (b) A non-extension span produces **exactly ONE show request** with `before ==
  len(last_applied_span.encode("utf-8"))` (UTF-8 bytes; an astral char counts 4), `text` = the
  FULL corrected span, ALL `SHOW_FIELDS` present, `timeout == 0.25`; no second request, no
  per-character or chunked sends.
- (c) Ordering pinned: zero-diff (`rendered_equal`) ⇒ `UNCHANGED`, NO request; revision regression
  ⇒ `REFUSED`, NO request; recheck failure ⇒ `REFUSED "recheck: <reason>"`, NO request;
  **owned-region divergence ⇒ `REFUSED "owned region diverged"`, NO request**; span > 4000 B ⇒
  `REFUSED` (unchunkable cap), NO request.
- (d) On `applied`: `_last_applied_span = span` AND `_inserted_bytes = len(span.encode())` (**SET**
  to the owned size — invariant: the field always equals the UTF-8 bytes of the currently-owned
  span, so recheck's caret arithmetic `binding.cursor_bytes + inserted_bytes` stays true after a
  shrink/rewrite). On refused/unknown: state untouched (a retry recomputes `before` vs the last
  APPLIED span — pinned).
- (e) Every REFUSED/UNKNOWN records a machine-readable `self.last_reason` (taxonomy:
  `not acquired` / `revision regression` / `recheck:<reason>` / `owned region diverged` /
  `unchunkable correction <N>B > <cap>B cap` / `host refused` / `host result <r>` / `ime no reply`);
  logs carry **counts and times, never recognition text** (R.5).
- (f) Fences: NO finalize/leave/cancel (T3.S3), NO takeover (T4), NO `ime_host.py` edits (S1 owns
  `SHOW_CONFIRM_WAIT`; `_show` untouched — record its value at preflight), NO protocol/wlwire/
  manager/controller/bulk_delivery/daemon/feedback/ctl/config/tools-im-lab edits. The controller
  and `bulk_delivery.py` are consumed read-only.

## User Persona

**Target User**: Internal — **bulk_controller** (landed, M3) is the caller: on every
partial/final it calls `show(session, utterance, seq, expected_revision, span)` and +1s
`expected_revision` only on APPLIED. **P1.M4.T3.S3** (finalize) builds on the same method;
**P1.M4.T5** (G3) exercises corrections in real fields. No end-user surface changes.

**Use Case**: Bulk mode armed on a GTK field; acquire binds the caret; partials
`"hel"`→`"hello w"` flow through the insert path. The commit's correction pass re-decodes the
utterance as `"hello world"` — not an extension of `"hello w"`? It IS (`"hello w"` →
`"hello world"` = extension)… the real trigger is a **rewrite**: the decoder revises
`"helllo w"` → `"hello world"` (first character changed). `show(..., span="hello world")`:
zero-diff? no → extension? no (`"helllo w"` prefix diverges at char 1) → **correction path**:
`before = len("helllo w".encode()) = 8`, recheck proves the caret is 8 bytes past the binding
caret and nothing else moved, `_owned_region_intact` re-reads the field and confirms those 8
bytes are still `"helllo w"`, span ≤ 4000 B → ONE commit:
`delete_surrounding_text(8, 0)` + `commit_string("hello world")` + `commit(serial)` → the field
shows the replacement with NO visible intermediate state (GTK may fire 1–2 internal `changed`
signals within the one commit cycle — EXPECTED, per the lab). Reply `applied` ⇒ `APPLIED`,
state = the new span.

**Pain Points**: (1) Without the correction path, every decoder revision that isn't a pure
extension REFUSES and disarms bulk delivery — the tool is unusable for real dictation (stabilized
partials routinely revise earlier characters). (2) A wrong `before` count corrupts adjacent user
text — the single worst failure class (hence recheck + owned-region verification). (3) A chunked
large correction = N visible edits = event-count-law violation; a silent retry of an `unknown`
could double-apply.

## Why

- **The controller is landed and demands it**: `bulk_controller.py:617,664-688` calls `show()` for
  every partial and final; real decoder revisions are routinely non-extensions. S1's insert-only
  show() turns the first revision into a refusal that stops delivery — the correction path is the
  missing half of R.3's `show` contract ("one insert-or-replace").
- **The mechanism is lab-proven** (R.2, do-not-re-derive): ONE atomic commit
  (delete_surrounding_text + commit_string + commit) corrected a whole 1024-byte span
  byte-exactly in GTK4; the wire's evaluation order (preedit-replace → delete → insert) makes the
  replacement atomic; 26–40 ms cmd→field; IM commits generate ZERO key events (cannot self-trigger
  T4's takeover).
- **The host half is already landed**: `ime_host.py:_show` (:172-200) sends the atomic
  delete+commit+commit sequence whenever `before>0` and maps `applied` via a compositor `done`.
  This task only needs the daemon half.
- **Safety lives in the guards**: the delete counts backward from the caret, so correctness =
  proving (a) the caret is at the end of OUR range (`recheck(binding, inserted_bytes=owned_bytes)`)
  and (b) the range's content is still ours (`_owned_region_intact` — one fresh verify pull +
  byte-slice equality). Both refuse BEFORE any request (R.5 mutation-time re-checks).

## What

Per the research note §3 (pinned algorithm). The exact source is in the Blueprint.

### Success Criteria

- [ ] All files as specified; the combined suites green under `timeout 120` (incl. S1's insert
      tests — zero regression); scope guard clean.
- [ ] One-request corrections with byte-exact `before` (UTF-8, astral = 4) and the FULL span as
      `text`; every refusal branch provably sends NO show request.
- [ ] `_owned_region_intact` guard lands (refuses on diverged/truncated/missing snapshots) and is
      exercised by tests (including the divergence case).
- [ ] State-advance-only-on-APPLIED + `_inserted_bytes` = owned-span bytes after a correction
      (shrink-safe) pinned; retry-after-refusal recomputes vs the last APPLIED span.
- [ ] `last_reason` taxonomy pinned; logs = counts/times, never text.
- [ ] Optional GTK row runs only under `IME_CORRECTION_LAB=1`; default pytest never collects it.

## All Needed Context

### Context Completeness Check

_Pass._ The consumed surfaces are landed-and-anchored (host `_show` semantics `ime_host.py:172-200`;
`recheck`/`FieldBinding` `target.py:48-133`; `ShowResult`/`rendered_equal` `bulk_delivery.py:77-89,220+`;
`SHOW_FIELDS` `protocol.py:40,79-93`; controller revision contract `bulk_controller.py:289-297,443,617,688`);
S1's show() is pinned as the in-flight contract with a hard preflight gate (Task 0 stops if the
insert path + state are absent); the correction algorithm is pinned verbatim below; the test
matrix is case-enumerated with the existing `_FakeProc`/`_verify`/`_acquired` helpers; the
protocol/evidence facts (byte units, atomicity, 1024 B proof, 1–2 changed-signals) are cited from
R.2 and the research note.

### Documentation & References

```yaml
# MUST READ — this task's design record (algorithm, guards, test matrix, fences).
- docfile: plan/008_a47116bb2b79/P1M4T3S2/research/ime_correction_path_design.md
  section: "ALL. §1 consumed-surface anchors (live-verified), §2 protocol/evidence facts
            (byte units; commit order; 1024 B proof; OWNERSHIP-not-size), §3 the pinned algorithm
            + why each guard + residual risks, §4 test matrix, §5 fences."

# MUST READ — the sibling insert-path PRP (the in-flight base this task evolves; ASSUME LANDED).
- docfile: plan/008_a47116bb2b79/P1M4T3S1/PRP.md
  section: "Goal (b)/(c)/(e) — the ordering + state rules + last_reason taxonomy this task
            PRESERVES; Implementation Blueprint — the show() reference implementation (our base);
            Known Gotchas #1-#8 (state-only-on-applied, zero-diff-first, UTF-8 everywhere,
            4000 B cap, deadline budget, SHOW_FIELDS, no-text logs)."
  critical: "S1's branch `self.last_reason = 'correction not implemented (P1.M4.T3.S2)'; return
             REFUSED` is EXACTLY what this task replaces. Everything else in show() keeps its
             behavior. S1's tests must stay green — run them first (Task 0)."

# MUST READ — the file being EVOLVED (T2.S1's acquire/recheck + S1's show, gated by preflight).
- file: voice_typing/ime/target.py
  why: "recheck :101-125 (call with inserted_bytes=owned_bytes; returns (ok, reason, rev); its
        signature/body are T2.S1's test-pinned — do NOT edit), FieldBinding :48-59 (cursor_bytes
        is the byte offset the delete range is anchored to), to_bytes_span/binding_caret_after
        :127-133. Add: _owned_region_intact(), the revision-regression guard, the correction
        branch."
  gotcha: "Byte arithmetic ONLY via .encode('utf-8') on ORIGINAL strings (never normalized
           copies). recheck's caret math is `binding.cursor_bytes + inserted_bytes` — after an
           applied correction the field must equal the owned span's byte length (hence SET, not +=)."

# MUST READ — the host half (semantics consumed; file FENCED).
- file: voice_typing/ime/ime_host.py
  why: "_show :172-200 — before>0 ⇒ delete_surrounding_text(before, 0) + commit_string(text) +
        commit(dones) in ONE commit; applied = dones increment within SHOW_CONFIRM_WAIT (:38);
        wire-send Exception ⇒ unknown (never retry); not-activated ⇒ refused."
  gotcha: "DO NOT EDIT this file (S1 owns SHOW_CONFIRM_WAIT; _show is landed + test-pinned).
           Record SHOW_CONFIRM_WAIT at preflight — it should be ≤ 0.22 once S1 lands."

# MUST READ — the vocabulary + protocol + caller (all read-only).
- file: voice_typing/bulk_delivery.py
  why: "ShowResult :77-89 (UNCHANGED = zero events; UNKNOWN never retried), rendered_equal :220+
        (consume; never reimplement), DeliveryTarget.show :114-140 (span = COMPLETE rendered span)."
- file: voice_typing/ime/protocol.py
  why: "SHOW_FIELDS :40 + validate_request :79-93 — session/utterance/seq/expected_revision/text
        REQUIRED on every show; `before` rides free as an extra field."
- file: voice_typing/bulk_controller.py
  why: ":289-297 revision seeded from acquire; :443 +1 ONLY on applied; :617,664-688 the show()
        call sites. refused/unknown stop delivery — the adapter must never advance state on a
        non-applied result."
  gotcha: "FENCED — do not edit. If a controller test fails, the adapter's mapping/state is wrong."

# MUST READ — the test file to APPEND to (reuse its helpers verbatim).
- file: tests/test_ime_target.py
  why: "_FakeProc :21+ (records (cmd, timeout, fields); scripted replies; None = dead), the
        _verify(text, cursor, anchor, ...) reply helper (:40), _acquired() fixture (:48).
        S1's show tests are appended here too — do NOT edit their bodies; APPEND ours."

# READ — grounding + PRD + discipline.
- docfile: PRD.md
  section: "§4.2sexies R.1 (event-count law; correction = 1 op; reach bounded by OWNERSHIP never
            size), R.2 (im-lab evidence — 1024-byte atomic correction, commit order, byte units —
            do not re-derive), R.3 (show contract: one insert-or-replace, only if
            focus/caret/selection/ownership still match; units mapping; never touch adjacent
            text), R.4 (route DECIDED), R.5 (mutation-time re-checks; never retry; logs w/o text)."
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  section: "§9 open risks (4000-byte cap; GTK 1-2 changed-signals-per-commit EXPECTED; foot/kitty
            insert-only)."
- docfile: AGENTS.md
  section: "Rules 1-3 (GNU timeout everywhere; .venv/bin/python; never the live desktop)."
```

### Current Codebase tree (excerpt, state at task start)

```bash
voice_typing/ime/target.py             # EVOLVE: replace the correction-refusal branch + add guards (S1's show() is the base)
voice_typing/ime/ime_host.py           # FENCED (host _show incl. the before>0 half — landed)
voice_typing/ime/protocol.py           # FENCED (SHOW_FIELDS already tolerate `before`)
voice_typing/bulk_delivery.py          # READ-ONLY vocabulary
voice_typing/bulk_controller.py        # READ-ONLY caller
tests/test_ime_target.py               # APPEND ~15 correction cases (_FakeProc/_verify/_acquired helpers)
tests/ime_acquire_lab.py               # T2.S1's env-gated lab — the pattern for ours (untouched)
tests/ime_show_lab.py                  # S1's optional insert lab — pattern reference (untouched)
tools/im-lab/                          # FENCED evidence (the 1024-byte atomic-correction proof)
# NOT YET: tests/ime_correction_lab.py
```

### Desired Codebase tree

```bash
voice_typing/ime/target.py          # EVOLVE: full show() — insert branch (S1, unchanged behavior) + correction branch
tests/test_ime_target.py            # APPEND the correction matrix
tests/ime_correction_lab.py         # CREATE: env-gated GTK correction row (optional evidence)
```

### Known Gotchas

```python
# CRITICAL #1 — THE DELETE COUNTS BACKWARD FROM THE CARET. before must be EXACTLY
#   len(owned.encode()) AND the caret must be at binding.cursor_bytes + that count (recheck with
#   inserted_bytes=owned_bytes proves it). A wrong count or caret eats ADJACENT USER TEXT — the
#   worst failure class. Never derive `before` from a normalized/lowercased copy.
# CRITICAL #2 — _owned_region_intact BEFORE THE REQUEST. recheck proves the caret position;
#   it does NOT prove the range's CONTENT is still ours (a same-length in-region edit with the
#   caret restored would pass recheck alone). One fresh verify pull + byte-slice equality
#   [cursor_bytes, cursor_bytes+owned_bytes) == owned.encode() makes the range verified-owned.
#   Refuse on: no reply / not ok / snapshot truncated past the range end / slice mismatch
#   ("owned region diverged"). Inserts do NOT pay this second pull (correction-only).
# CRITICAL #3 — STATE SET, NOT +=, ON AN APPLIED CORRECTION. _inserted_bytes = len(span.encode())
#   (the owned size). A shrink correction makes the caret EARLIER; += would desync recheck's
#   expected-caret math and the next operation would delete user text. _last_applied_span = span.
# CRITICAL #4 — STATE ADVANCES ONLY ON APPLIED (same as S1). refused/unknown leave both fields
#   untouched; the controller disarms. Pin: after a refused correction, a retry recomputes
#   `before` vs the last APPLIED span.
# CRITICAL #5 — UNCHUNKABLE > 4000 B ⇒ REFUSED. Never split a correction into multiple commits
#   (N commits = N visible edits = event-count-law violation). Reason: "unchunkable correction
#   <N>B > <cap>B cap". The delete side carries only a count — the cap applies to the span text.
# CRITICAL #6 — UTF-8 BYTES EVERYWHERE. before, cap, and _inserted_bytes all use
#   .encode("utf-8") on ORIGINAL strings; the wire's surrounding_text offsets are UTF-8 byte
#   positions (an astral char = 4 — test-pinned).
# CRITICAL #7 — ZERO-DIFF BEFORE ANYTHING (S1's rule, unchanged). rendered_equal ⇒ UNCHANGED,
#   ZERO requests — including for spans that would take the correction branch.
# CRITICAL #8 — EXTENSION FAST-PATH PRESERVED. span.startswith(_last_applied_span) keeps S1's
#   before=0 + delta-only commit (no delete, no second verify pull). The correction branch is for
#   ANY non-extension span (rewrite, shrink, prefix change) — reach bounded by OWNERSHIP, and the
#   FULL owned range is replaced in one commit regardless of how much differs.
# CRITICAL #9 — DEADLINE BUDGET. request timeout=0.25 (assert); host SHOW_CONFIRM_WAIT ≤ 0.22
#   (S1's Task 3 — record at preflight, do NOT edit the host). The two verify pulls
#   (recheck + _owned_region_intact) are local JSONL roundtrips (ms) under _ACQUIRE_TIMEOUT_S
#   upper bounds — consistent with S1's recheck usage; the controller's 250 ms failure deadline
#   remains the outer bound.
# CRITICAL #10 — LOGS: counts + times, NEVER the span text (R.5). last_reason carries the
#   taxonomy (test-pinned).
# GOTCHA #11 — a reply with no/odd "result" ⇒ UNKNOWN (defensive), never a crash; None reply ⇒
#   UNKNOWN ("ime no reply"). Never retry (the controller's rule).
# GOTCHA #12 — the lab driver: no test_ prefix, IME_CORRECTION_LAB=1 gate, timeout 300, private
#   seat (xvfb-run + dbus-run-session + sway), mktemp scratch + EXIT trap (AGENTS.md Rule 3).
# GOTCHA #13 — GNU timeout + .venv/bin/python on EVERY command (AGENTS.md Rule 1; zsh aliases).
# GOTCHA #14 — GTK may fire 1-2 internal `changed` signals within ONE commit cycle — EXPECTED,
#   not a defect (R.2). Frame-level single-edit verification is G3 (P1.M4.T5.S1), NOT this task.
```

## Implementation Blueprint

### Data models and structure

No new dataclasses or constants (S1's `_SHOW_TIMEOUT_S`/`_COMMIT_CAP_BYTES` are reused). Adapter
additions: the `_owned_region_intact(binding, owned) -> bool` private helper + the
revision-regression guard + the correction branch inside `show()`.

### `show()` correction path (implement verbatim; S1's insert branch and guards stay)

```python
    def show(self, session: int, utterance: str, seq: int,
             expected_revision: int, span: str) -> ShowResult:
        """Insert OR correction (R.3/R.5; P1.M4.T3.S1 insert + P1.M4.T3.S2 correction).

        Extension of the owned span  → ONE atomic insert  (commit_string(delta)+commit, before=0).
        Any non-extension span       → ONE atomic range replacement
          (delete_surrounding_text(before,0) + commit_string(span) + commit) — verified-owned:
          the delete counts backward from the caret, so recheck proves the caret sits at the END
          of our range and _owned_region_intact proves the range's content is still ours.
          Reach is bounded by OWNERSHIP, never size (user decision 2026-11-19).
        Zero-diff ⇒ zero events. State advances ONLY on applied (controller +1s revision then).
        """
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if rendered_equal(self._last_applied_span, span):
            return ShowResult.UNCHANGED                       # R.1: zero-diff = 0 events
        if not isinstance(expected_revision, int) or expected_revision < binding.revision:
            self.last_reason = "revision regression"          # stale/desynced caller (controller
            return ShowResult.REFUSED                         # seeds from acquire + only +1s)
        owned = self._last_applied_span
        owned_bytes = len(owned.encode("utf-8"))              # wire units: UTF-8 bytes
        span_bytes = len(span.encode("utf-8"))
        if span.startswith(owned):
            # ---- INSERT path (P1.M4.T3.S1, unchanged behavior) -------------------------
            delta = span[len(owned):]
            delta_bytes = span_bytes - owned_bytes
            ok, reason, _rev = self.recheck(binding, inserted_bytes=self._inserted_bytes)
            if not ok:
                self.last_reason = f"recheck: {reason}"
                return ShowResult.REFUSED                     # NO request sent
            if delta_bytes > _COMMIT_CAP_BYTES:
                self.last_reason = f"commit cap {_COMMIT_CAP_BYTES}B exceeded ({delta_bytes}B)"
                return ShowResult.REFUSED                     # NO request sent
            r = self._proc.request("show", timeout=_SHOW_TIMEOUT_S, session=session,
                                   utterance=utterance, seq=seq,
                                   expected_revision=expected_revision, text=delta, before=0)
            advance = lambda: (setattr(self, "_last_applied_span", span),
                               setattr(self, "_inserted_bytes", self._inserted_bytes + delta_bytes))
        else:
            # ---- CORRECTION path (P1.M4.T3.S2, THIS TASK) ------------------------------
            # (1) caret at the END of the owned range — the delete counts backward from it
            ok, reason, _rev = self.recheck(binding, inserted_bytes=owned_bytes)
            if not ok:
                self.last_reason = f"recheck: {reason}"
                return ShowResult.REFUSED                     # NO request sent
            # (2) the range's CURRENT content is still exactly ours (verified-owned range)
            if not self._owned_region_intact(binding, owned):
                self.last_reason = "owned region diverged"
                return ShowResult.REFUSED                     # NO request sent
            # (3) unchunkable ⇒ refuse (never split: N commits = N visible edits)
            if span_bytes > _COMMIT_CAP_BYTES:
                self.last_reason = (f"unchunkable correction {span_bytes}B "
                                    f"> {_COMMIT_CAP_BYTES}B cap")
                return ShowResult.REFUSED                     # NO request sent
            # (4) ONE atomic replacement: delete_surrounding_text(before,0)+commit_string+commit
            r = self._proc.request("show", timeout=_SHOW_TIMEOUT_S, session=session,
                                   utterance=utterance, seq=seq,
                                   expected_revision=expected_revision, text=span,
                                   before=owned_bytes)
            advance = lambda: (setattr(self, "_last_applied_span", span),
                               setattr(self, "_inserted_bytes", span_bytes))  # SET: owned size
        # ---- honest mapping (both paths; bytes-sent ≠ applied) --------------------------
        if r is None:
            self.last_reason = "ime no reply"
            logger.warning("ime show: no reply (session=%s seq=%s span_chars=%d)",
                           session, seq, len(span))
            return ShowResult.UNKNOWN
        result = r.get("result")
        if result == "applied":
            advance()                                         # ONLY on applied (Critical #4)
            self.last_reason = ""
            logger.info("ime show applied: session=%s seq=%s before=%d text_bytes=%d t_ms=%s "
                        "owned_bytes=%d", session, seq, owned_bytes if not span.startswith(owned)
                        or True else 0, span_bytes if False else (span_bytes - 0),
                        r.get("t_ms"), self._inserted_bytes)
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = "host refused"
            return ShowResult.REFUSED
        self.last_reason = f"host result {result!r}"
        logger.warning("ime show unknown: session=%s seq=%s result=%r", session, seq, result)
        return ShowResult.UNKNOWN

    def _owned_region_intact(self, binding: "FieldBinding", owned: str) -> bool:
        """(P1.M4.T3.S2) ONE fresh verify pull; the byte range we are about to delete must
        still contain EXACTLY our owned span — a verified-owned range (R.3: never touch
        adjacent user text). Corrections only; inserts do not pay this roundtrip."""
        r = self._proc.request("verify", timeout=_ACQUIRE_TIMEOUT_S)
        if r is None or not r.get("ok", False) or r.get("text") is None:
            return False
        raw = r["text"].encode("utf-8")                       # ORIGINAL bytes
        end = binding.cursor_bytes + len(owned.encode("utf-8"))
        if r.get("snapshot_truncated") and end > len(raw):
            return False                                      # cannot verify through the cap
        return raw[binding.cursor_bytes:end] == owned.encode("utf-8")
```

> NOTE on the `advance` lambdas: they exist to keep the mapping shared between the two paths;
> write them as plain `if/else` blocks if clearer — the PINNED behavior is: insert path does
> `_inserted_bytes += delta_bytes`; correction path does `_inserted_bytes = span_bytes`. (Also
> simplify the applied-log line to: `before=<0 on insert path, owned_bytes on correction>`,
> `text_bytes=<delta_bytes|span_bytes>` — counts and times only, never text.) `logger` and the
> S1 state/constant declarations come from S1's landed code; add nothing else to `__init__`.

### Implementation Tasks

```yaml
Task 0: PREFLIGHT (no mutation) — STOP if the base is missing
  - RUN:
      test -f voice_typing/ime/target.py && grep -q "def show" voice_typing/ime/target.py \
        && echo "S1 show() landed" || echo "PREFLIGHT FAIL: P1.M4.T3.S1 not landed — STOP"
      grep -n "_last_applied_span\|_COMMIT_CAP_BYTES\|_SHOW_TIMEOUT_S\|correction not implemented" \
        voice_typing/ime/target.py        # the S1 state/constants + the branch we replace
      grep -n "SHOW_CONFIRM_WAIT" voice_typing/ime/ime/../../../voice_typing/ime/ime_host.py 2>/dev/null \
        || grep -n "SHOW_CONFIRM_WAIT" voice_typing/ime/ime_host.py   # RECORD (expect ≤ 0.22)
      timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py \
        tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_ime_manager.py \
        tests/test_bulk_delivery.py tests/test_bulk_controller.py -q | tail -1
  - EXPECTED: S1 landed + all green (if show() absent → STOP; if a suite is red at baseline,
    record it and proceed only if unrelated to show()).

Task 1: tests/test_ime_target.py — APPEND the correction matrix FIRST (TDD RED). Reuse
        _FakeProc/_verify/_acquired; do NOT touch S1/T2.S1 bodies. Cases (script the verify
        replies with cursor == binding.cursor + owned bytes so recheck passes unless the case
        says otherwise):
        prefix-divergent correction: insert "helllo w" (applied), then show span="hello world"
          → ONE show request: before==len(b"helllo w")==8, text=="hello world" (FULL span),
          ALL SHOW_FIELDS, timeout==0.25 → reply applied → APPLIED, _last_applied_span==span,
          _inserted_bytes==len(b"hello world");
        shrink correction: owned "hello world" → span "hi" → before==11, text=="hi" → applied →
          _inserted_bytes==2 (SET, not += — the shrink pin);
        correction-after-correction: second divergent show → before == bytes of the FIRST
          corrected span (state chaining);
        UTF-8: owned "hi 😀 you" → divergent span "hi 🙂 you" → before==len(b"hi \U0001F600 you")
          (astral = 4), text==full span;
        owned region diverged: verify text where [cursor, cursor+owned) differs → REFUSED
          "owned region diverged", NO show request in proc.calls, state NOT advanced;
        recheck caret-moved on correction: verify cursor elsewhere → REFUSED
          "recheck: caret moved", NO show request;
        unchunkable: owned "a", span = "b" + "x"*4000 (4001 B, divergent) → REFUSED
          "unchunkable correction 4001B > 4000B cap", NO request;
        revision regression: expected_revision < acquire revision → REFUSED, NO request
          (and the equal case still proceeds);
        extension regression (S1): span startswith owned → request before==0 text==delta
          (unchanged S1 behavior after our edit);
        zero-diff / render-equal → UNCHANGED, zero requests (incl. a would-be correction);
        reply None / unknown / refused → UNKNOWN / UNKNOWN / REFUSED; state untouched;
        retry-after-refusal: refused correction, then the identical show again → before still
          computed vs the last APPLIED span (state-not-advanced pin);
        call-count pin: one correction = exactly [verify, verify, show] requests (recheck pull
          + owned-region pull + the one show) in order;
        last_reason asserted on every refusal path.

Task 2: EVOLVE voice_typing/ime/target.py per the Blueprint (correction branch +
        _owned_region_intact + the regression guard) → the whole file's suites GREEN.

Task 3: CREATE tests/ime_correction_lab.py (optional evidence; mirror tests/ime_acquire_lab.py):
        gate IME_CORRECTION_LAB=1 (else print "skipped" exit 0); private seat (xvfb-run +
        dbus-run-session + sway), mktemp + EXIT trap; acquire → 2 inserts ("hell", "lo w") →
        ONE correction to "hello world" (show() with the divergent span) → assert the GTK field's
        dumped text ends with "hello world", caret at the end, edit-count grew by ≤3, zero
        grab_keys; plus the >1024 B row: build a 1500-char owned span via shows, correct its
        first char → assert byte-exact replacement. ONE verdict line per row. timeout 300.

Task 4: VALIDATE (below). Commit if directed:
        "P1.M4.T3.S2: IM show() correction path — atomic delete+commit range replacement,
         verified-owned, unchunkable-refuse".
```

### Integration Points

```yaml
PACKAGE SEAM (consumed downstream; nothing wired here):
  - P1.M4.T3.S3: "finalize() builds on the same owned-span state (_last_applied_span) — a final
                  matching the visible text ⇒ NO further edit"
  - P1.M4.T5.S1: "G3 GTK rows exercise corrections in a real field (frame-level single-edit
                  verification is G3's concern, not this task's)"
  - P1.M6.T2.S1: "constructs ImeTarget(ImeProcess(...)); the controller calls show() for every
                  partial/final — this method IS the DeliveryTarget implementation"
NOTHING WIRED: "no daemon/feedback/ctl/bulk_*/config/protocol.py/wlwire.py/manager.py/
                ime_host.py/tools-im-lab changes."
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# L1 syntax + purity
timeout 60 .venv/bin/python -m py_compile voice_typing/ime/target.py tests/test_ime_target.py \
  tests/ime_correction_lab.py && echo "L1 OK"
env -u WAYLAND_DISPLAY .venv/bin/python -c "from voice_typing.ime.target import ImeTarget, \
  FieldBinding; assert hasattr(ImeTarget, '_owned_region_intact'); print('pure import ok')"

# L2 the gate (S1's + T2.S1's + ours, zero regression)
timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py \
  tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_ime_manager.py \
  tests/test_bulk_delivery.py tests/test_bulk_controller.py -q | tail -1
# Expected: 0 failed. A bulk_controller failure ⇒ the adapter's mapping/state is wrong (read first).

# L3 fake duplex smoke (no compositor) — one atomic correction end-to-end
timeout 60 .venv/bin/python - <<'EOF'
from voice_typing.ime.target import ImeTarget
from voice_typing.bulk_delivery import ShowResult
owned = "helllo w"
class P:
    def __init__(s): s.calls = []
    def request(s, cmd, timeout=None, **f):
        s.calls.append((cmd, f))
        if cmd == "acquire": return {"ok": True, "handle": "im", "revision": 2,
            "text": "hi ", "cursor": 3, "anchor": 3, "snapshot_truncated": False}
        if cmd == "verify":  return {"ok": True, "activated": True, "dones": 5,
            "text": "hi " + ("helllo w" if len(s.calls) > 3 else ""),
            "cursor": 3 + len((owned if len(s.calls) > 3 else "").encode()), "anchor": 3,
            "snapshot_truncated": False}
        return {"result": "applied", "t_ms": 29.0}
p = P(); t = ImeTarget(p); assert t.acquire().ok
r1 = t.show(1, "u1", 1, 2, owned)            # insert path lands "helllo w"
r2 = t.show(1, "u1", 2, 3, "hello world")    # CORRECTION (diverges at char 1)
assert r1 is ShowResult.APPLIED and r2 is ShowResult.APPLIED, (r1, r2)
show_calls = [c for c in p.calls if c[0] == "show"]
assert show_calls[-1][1]["before"] == len(owned.encode()) == 8
assert show_calls[-1][1]["text"] == "hello world"
assert t._last_applied_span == "hello world" and t._inserted_bytes == 11
assert t.show(1, "u1", 3, 4, "hello world") is ShowResult.UNCHANGED   # zero-diff ⇒ 0 events
print("L3 OK", [c[0] for c in p.calls])
EOF
# Expected: L3 OK ['acquire', 'verify', 'show', 'verify', 'verify', 'show'] — the correction
# pays recheck + owned-region pulls then ONE show; the zero-diff sends nothing.

# L4 scope guards + optional evidence
git status --porcelain   # ONLY: target.py(M), test_ime_target.py(M), ime_correction_lab.py
git diff --stat voice_typing/ime/ime_host.py voice_typing/ime/protocol.py voice_typing/ime/wlwire.py \
  voice_typing/ime/manager.py voice_typing/bulk_delivery.py voice_typing/bulk_controller.py \
  voice_typing/daemon.py tools/im-lab | wc -l   # 0
timeout 120 .venv/bin/python -m pytest tests/ -q --collect-only 2>/dev/null | grep -c ime_correction_lab || echo "ok: not collected"
timeout 300 env IME_CORRECTION_LAB=1 .venv/bin/python tests/ime_correction_lab.py || echo "lab row failed/skipped — record honestly"
```

## Final Validation Checklist

- [ ] L1–L4 green; all listed suites pass (S1's insert tests included — zero regression); scope
      guard clean (fenced files untouched).
- [ ] One-request corrections: `before` = UTF-8 bytes of the owned span (astral = 4), `text` =
      FULL corrected span, ALL SHOW_FIELDS, `timeout=0.25`; refusal branches send NO request.
- [ ] `_owned_region_intact` lands and refuses on divergence; corrections are verified-owned
      (recheck caret-at-end + content equality).
- [ ] State advances ONLY on APPLIED; `_inserted_bytes` SET to the owned size on a correction
      (shrink-safe); retry-after-refusal recomputes vs the last APPLIED span.
- [ ] Unchunkable > 4000 B ⇒ REFUSED with the reason; never chunked.
- [ ] `last_reason` taxonomy pinned; logs = counts/times only (no span text).
- [ ] Fences held: no T3.S3/T4/M6 scope, no host/protocol/wlwire/manager/controller/bulk_delivery
      edits, lab not collected by default.

## Anti-Patterns to Avoid

- ❌ Don't compute `before` from anything but `len(_last_applied_span.encode("utf-8"))` on the
      ORIGINAL string, and never send a correction without recheck + `_owned_region_intact` —
      the delete eats whatever sits before the caret (Critical #1/#2).
- ❌ Don't `+=` on a correction (shrink desync) and don't advance state on refused/unknown
      (Critical #3/#4).
- ❌ Don't chunk a large correction or approximate one with delete-everything + N inserts — one
      atomic replacement or a refusal (Critical #5).
- ❌ Don't reimplement zero-diff/byte mapping — consume `rendered_equal`/`.encode()` on ORIGINAL
      strings (Critical #6/#7).
- ❌ Don't regress the extension fast-path to the full-replacement path (cost + extra roundtrips
      for the common case) (Critical #8).
- ❌ Don't edit the host/protocol/controller, don't retry an unknown, don't log span text, don't
      let pytest collect the lab driver, don't run anything without GNU timeout +
      `.venv/bin/python`.
- ❌ Don't chase frame-level single-edit visibility or foot/kitty insert-only behavior here —
      both are G3 (P1.M4.T5) concerns; record, don't fix.

---

**Confidence Score: 9/10.** The host half is landed and test-pinned; the consumed daemon-side
surfaces (recheck/FieldBinding/ShowResult/rendered_equal/SHOW_FIELDS/controller revision) are
anchored with line numbers; S1's show() is pinned as the base with a hard preflight STOP gate;
the correction algorithm + the new guard are pinned verbatim with the ordering and state rules;
the test matrix is case-enumerated against the existing fake helpers. −1: depends on S1 landing
first (mitigated by the Task 0 gate) and the optional GTK row depends on the disposable-desktop
environment (bounded — optional evidence with an honest skip path; the fake-proc suite is the gate).

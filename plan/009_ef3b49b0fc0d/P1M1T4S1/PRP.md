# PRP — P1.M1.T4.S1: Retain bounded native recovery in memory (`NativeRecovery` leaf)

## Goal

**Feature Goal**: Implement PRD §4.8.1 C's **native recovery** store — "Keep native recovery in
daemon memory only, separately keyed by id ... Retain up to two nonempty ended sessions with
unacknowledged finals, at most 1 MiB UTF-8 per session including while active for the unacknowledged
suffix; reclaim acknowledged text from this budget. On overflow retain the newest complete finals that
fit, mark truncation (a lone oversized final may be safely clipped for recovery only)." — as a
**separate `NativeRecovery` leaf class in `voice_typing/session_recovery.py`**, next to the legacy
ordinary-session `SessionRecovery` (which is WRONG for native: it keeps finals + the unfinished *tail*,
applies its cap only at close, has no ACK awareness, no uncertainty flag, and is single-draft keyed).
NativeRecovery: keyed by the session's UUIDv4; retains **unacknowledged accepted finals only** (no
partials, no seed, no tail); **bounded while active** (1 MiB UTF-8 INCLUDING the single-space
separators); `mark_offer_attempted` BEFORE the socket write sets an uncertainty flag that survives
truncation; a **verified ACK removes** the final and reclaims budget; `end_session` keeps ≤ 2 nonempty
ended sessions (fully-ACKed/empty endings are discarded and never evict); immutable `recover()`
snapshots feed T4.S6 (failure hints), T4.S2 (the ACK path) and T5.S1 (the capped wire reply); `clear()`
at daemon exit. Pure fixtures + fake clock, no I/O, no logging, leaf-locked, legacy isolated.

**Deliverable** (1 module appended, 1 test file created — no new source file, no other file touched):
1. `voice_typing/session_recovery.py` — **APPEND**: `_MAX_NATIVE_SESSIONS`, `_MAX_NATIVE_SESSION_BYTES`,
   `_NATIVE_SEP`; `_HeldFinal` (frozen: seq, text, offer_attempted); `_NativeSession` (internal);
   `NativeRecoverySnapshot` (frozen: session_id, text, truncated, possibly_applied, final_count,
   end_reason, ended_monotonic); `NativeRecovery` with `retain_final`, `mark_offer_attempted`,
   `settle_final`, `end_session`, `recover`, `active_id`, `counts`, `clear` (injected `clock`).
   Mode A docstrings: native-vs-ordinary retention/ownership/uncertainty. The legacy
   `SessionRecovery`/`CompletedSession`/`_fit_text` code stays **byte-identical** (NativeRecovery
   reuses `_fit_text` + imports `is_uuid_v4`, `utf8_len`, `has_lone_surrogates` from `editor_protocol`).
2. `tests/test_native_recovery.py` — **NEW**: 17 hermetic tests (pure store + fake clock + a bounded
   thread-safety smoke + a legacy-isolation pin).

**Success Definition**:
- (a) `retain_final(id, seq, text)` auto-creates the ACTIVE session for a UUIDv4 id, is exactly-once
  per `(id, seq)`, rejects (returns False, state untouched) non-UUIDv4 ids, lone surrogates, `seq<=0`,
  duplicate seq, and any retain while ANOTHER session is active or for an ENDED id.
- (b) The 1 MiB UTF-8 cap holds **at every retain** (bounded while active), separators included:
  whole-oldest-first eviction; a lone oversized final clipped at a codepoint boundary keeping its
  START with `truncated=True`.
- (c) `mark_offer_attempted(id, seq)` → `possibly_applied=True` in the snapshot and survives clipping;
  `settle_final(id, seq)` (verified ACK) removes the final (budget reclaimed, flag gone with it).
- (d) `end_session(id, reason)`: nothing retained → discarded (does NOT evict); else appended to the
  ≤2 ended deque (oldest nonempty evicted). `recover()` with no id → latest ended; `recover(ended_id)`
  → that session; nothing → None (T5.S1's `not_found`).
- (e) `clear()` drops everything; the store is reusable. `counts()` returns ints only.
- (f) Legacy `SessionRecovery` behavior byte-identical: `tests/test_session_recovery.py` green
  unmodified; `tests/test_editor_protocol_vectors.py` green (editor_protocol untouched).
- (g) `timeout 300 .venv/bin/python -m pytest tests/test_native_recovery.py tests/test_session_recovery.py -q`
  → 0 failures; `git diff --name-only` == `{voice_typing/session_recovery.py, tests/test_native_recovery.py}`.

> **VERIFIED (this PRP's research):** the legacy store's shape at HEAD (cap only at `close_session`,
> tail-retaining, single draft) is confirmed by reading `session_recovery.py` this round; the
> architecture note (`system_context.md` "Buffer ownership and recovery") explicitly proposes
> `NativeRecovery` as a separate leaf reusing only the byte helpers. `editor_protocol.is_uuid_v4` /
> `utf8_len` / `has_lone_surrogates` exist (T3.S2 complete) and are imported, not duplicated.

## User Persona

**Target User**: the dictation user whose native editor session ended abnormally (target lost,
disconnect, delivery failure, timeout) with accepted finals the editor may or may not have inserted —
and the downstream implementers (T4.S2 offer/ACK, T4.S6 failure hints, T5.S1 `editor-recover` reply,
T5.S2 `voicectl recover`).
**Use Case / Journey**: daemon accepts final #7 → retains it (budget-bounded) → offers it to the editor
(`mark_offer_attempted` BEFORE the write) → the socket drops before the `applied` ACK → the session ends
`disconnected` → the user runs `voicectl recover <id>` → gets "…final 7" text with a stderr warning that
it may already be in the buffer (`possibly_applied`) — never auto-replayed, never duplicated.
**Pain Points Addressed**: silent loss of dictated text on an abnormal end (the §4.8.1 C warning
"Unconfirmed text: voicectl recover <id>" needs a store behind it); accidental double-insertion from
replaying an unverified offer; unbounded memory during a long active session.

## Why

- **PRD §4.8.1 C is normative** and names every property this store must have (id-keyed, ≤2 nonempty
  ended, 1 MiB UTF-8 including while active, ACK reclaims budget, newest-complete-first overflow,
  truncation marked, lone-final clipping for recovery only, `possibly_applied` semantics, no
  crash persistence). The architecture note designates `session_recovery.py` as its home and the
  legacy `_fit_text` as the reusable byte discipline.
- **The legacy store cannot be bent to fit** without breaking `voicectl session` (ordinary mode's
  contract: finals + tail, exactly-once, previous completed session survives). Native has different
  content (unACKed finals only), different timing (bounded while active), and extra state
  (offer-attempted). Two leaves in one module keeps the R.6 "reuse the bounded store machinery where
  practical" promise (shared `_fit_text`, shared G2 leaf law) while honoring "isolate legacy".
- **Uncertainty must be recorded BEFORE the risk.** A lost ACK is indistinguishable from an unapplied
  edit; the only honest signal is "an offer write was attempted" — recorded before the write so a
  mid-write exception still leaves it set. This is what lets T5.S2 warn about possible duplication and
  what forbids T4.S2 from ever re-sending.
- **Downstream contracts need a concrete shape now.** T4.S2/S6 and T5.S1 are planned against this
  task's OUTPUT: a `NativeRecoverySnapshot` with exactly the wire fields (`id,text,truncated,
  possibly_applied`) plus diagnostics. Defining it here (frozen dataclass) lets those tasks consume it
  without touching the store.
- **Scope discipline.** T4.S1 owns ONLY the leaf + its tests. It does NOT wire the daemon (T4.S4 routes
  finals; T4.S6 ends sessions), does NOT touch `editor_protocol.py` (T3.S2 — complete) or
  `editor_session.py`/`daemon.py` (T3.S4 — parallel, in flight), does NOT implement the wire reply
  (T5.S1) or the CLI (T5.S2). Pure stdlib + one leaf import; no socket, no CUDA, no I/O.

## What

Append `NativeRecovery` (+ snapshot + helpers) to `session_recovery.py` per the design below; add
`tests/test_native_recovery.py` (17 tests). Legacy code untouched.

### Success Criteria

- [ ] `NativeRecovery` exists in `voice_typing/session_recovery.py` with the 9 public methods and an injected `clock` (default `time.monotonic`).
- [ ] Active-slot exclusivity: one active session; a retain for a second id while one is active → False; after `end_session` the slot frees.
- [ ] Exactly-once per `(id, seq)`; rejects non-UUIDv4 ids (via `editor_protocol.is_uuid_v4`), lone surrogates, `seq<=0`/bool, ended ids, empty-after-strip text.
- [ ] Cap (1 MiB UTF-8, separators included) enforced at EVERY retain; whole-oldest-first; lone oversized clipped via `_fit_text` (codepoint-safe, keeps START); `truncated=True` only when clipping/dropping happened.
- [ ] `mark_offer_attempted` → `possibly_applied=True`; survives truncation of that final; `settle_final` removes the final and its flag.
- [ ] `end_session`: empty → discarded (no eviction); nonempty → ≤2 ended, oldest nonempty evicted; `recover(None)` → latest ended by end time; `recover(id)` → that/None.
- [ ] `clear()` empties all; reusable. `counts()` → `(ended_count, active_final_count)` ints.
- [ ] `NativeRecoverySnapshot` frozen with `session_id, text, truncated, possibly_applied, final_count, end_reason, ended_monotonic`.
- [ ] Mode A docstrings: module-level "native vs ordinary" section + per-method ownership/uncertainty notes.
- [ ] Legacy `SessionRecovery` tests green unmodified; `git diff --name-only` == the 2 files.

## All Needed Context

### Context Completeness Check

_Pass._ The legacy module's full source was read this round (shape, `_fit_text`, G2 leaf law, lock
discipline); the native requirement is quoted from PRD §4.8.1 C + the architecture note; every
public method's accept/reject semantics, the byte-accounting rule (separators included), the
overflow order, the uncertainty-flag lifecycle, the snapshot fields (matching the wire reply 1:1),
the reusable `editor_protocol` helpers (with line numbers), and all 17 tests are specified. The
parallel T3.S4 boundary (`editor_session.py`/`daemon.py`) is disjoint. No CUDA/socket/daemon — pure
Python with fakes.

### Documentation & References

```yaml
# MUST READ — the design, semantics table, interface + snapshot, and the 17 tests (this task's research)
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S1/research/native_recovery_leaf.md
  why: "§1 is the legacy-vs-native table (why a separate leaf). §2 lists the imported helpers with
        line numbers + the upstream signals (retain / offer-attempt / verified ACK) + the T3.S4
        EndRecord coupling (id + reason strings only). §3 is the full design: constants, _HeldFinal,
        _NativeSession, byte accounting INCLUDING separators, overflow order, uncertainty lifecycle,
        the public interface with per-method True/False semantics, the active-slot rule, the frozen
        NativeRecoverySnapshot (wire 1:1), thread discipline, Unicode safety. §4 = the 17 tests.
        §5 = verify + scope."
  critical: "§3 'Byte accounting INCLUDING separators' and 'Active-slot rule' are load-bearing: the
            budget is utf8_len(' '.join(texts)), NOT the sum of parts; and a retain for a NEW id
            while another is active is REFUSED (False), never a second active session. The
            mark_offer_attempted flag is set BEFORE the write and cleared only by removal via
            settle_final — nothing else clears it."

# THE FILE TO APPEND TO — voice_typing/session_recovery.py
- file: voice_typing/session_recovery.py
  why: "Legacy R.6 store (226 lines @HEAD): _MAX_SESSIONS/_MAX_SESSION_BYTES constants, _fit_text
        (:48-64, codepoint binary search — REUSE), CompletedSession (:67), SessionRecovery (:84) with
        the G2 leaf law (own threading.Lock, no callbacks, no I/O, no logging). APPEND NativeRecovery
        after SessionRecovery; add the new imports at the top (`from voice_typing.editor_protocol
        import has_lone_surrogates, is_uuid_v4, utf8_len`) — editor_protocol is pure stdlib (verified:
        re/json/threading only) so the import keeps this module leaf-pure."
  pattern: "Mirror the legacy style exactly: `from __future__ import annotations`, frozen dataclasses,
            `with self._lock:` on every public method, docstrings in the Mode A 'contract in one breath'
            voice, code constants (NOT config), counts-only diagnostics, never logs text."
  gotcha: "Do NOT modify ANY legacy line (SessionRecovery, CompletedSession, _fit_text, the module
           docstring's R.6 text) — tests/test_session_recovery.py imports _MAX_SESSION_BYTES etc. and
           pins behavior. ADD a module-docstring paragraph 'NATIVE RECOVERY (PRD §4.8.1 C)' rather than
           rewriting the existing header."

# THE HELPERS — voice_typing/editor_protocol.py (T3.S2, COMPLETE — import only)
- file: voice_typing/editor_protocol.py
  why: "is_uuid_v4(value) :170 (strict canonical lowercase v4 via UUID_V4_RE :153); utf8_len(text) :175;
        has_lone_surrogates(text) :180. MAX_FINAL_TEXT_BYTES :116 = 4 KiB (the per-final wire cap —
        the daemon enforces it BEFORE retain; the store does not need to, but a test documents it)."
  pattern: "Import the three helpers; do not re-implement UUID or UTF-8 logic (cross-language oracle
            symmetry — the same rules the TS/Lua adapters consume from tests/fixtures/editor_v1.json)."
  gotcha: "DO NOT EDIT editor_protocol.py (T3.S2's file; T3.S3/S4 import from it)."

# THE PARALLEL CONTRACT — T3.S4 (in flight)
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S4/PRP.md
  why: "Creates voice_typing/editor_session.py (Owner, EndRecord with id + reason ∈ END_REASONS) and
        edits daemon.py + test_editor_session.py. NativeRecovery takes `session_id: str` and
        `reason: str` — NO import of editor_session (keeps this task decoupled from T3.S4's exact
        class shapes and from any edit conflict)."
  critical: "DISJOINT files: T4.S1 = session_recovery.py + test_native_recovery.py; T3.S4 =
             editor_session.py + daemon.py + test_editor_session.py. Do not touch T3.S4's files."

# THE SPEC — PRD §4.8.1 C + the architecture note
- docfile: plan/009_ef3b49b0fc0d/prd_snapshot.md
  why: "§4.8.1 C, the 'Keep native recovery in daemon memory only' bullet (:475) — every rule in Goal/
        What above quotes it. §4.8.1 B: 'one offer outstanding at a time', `applied` only for the
        outstanding seq — the reason settle_final is per-(id, seq) and exactly-once."
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Buffer ownership and recovery' (:24-28): SessionRecovery is a leaf with _fit_text UTF-8-safe
        clipping and cap-at-close (ordinary); 'Proposed NativeRecovery is keyed by UUIDv4 and
        accepted-final identity/offer sequence, is actively bounded including separators, discards
        verified ACKed text, carries possible-prior-insertion flag ..., stores at most two nonempty
        ended sessions of 1 MiB UTF-8, and does not add partial/seed text. Keep attempted/uncertain
        metadata safe through truncation and loss; limit serialized response to 7 MiB ... Recovery is
        one-shot explicit read ..., non-consuming ..., entirely separate from voicectl session.'"
  critical: "The 7 MiB escaped-JSON cap and the `busy`-for-active-id decision belong to T5.S1 (wire);
             the store only guarantees text ≤ 1 MiB UTF-8 and exposes active_id() for the busy check."

# THE TEST PATTERN — tests/test_session_recovery.py (legacy — the file to mirror, NOT edit)
- file: tests/test_session_recovery.py
  why: "433 lines; header shows the conventions: `from __future__ import annotations`, sys.path shims
        (parents[1] + parent), direct store calls, a bounded thread-safety smoke, `timeout 300
        .venv/bin/python -m pytest ... -q` as the run command. Layer A (pure store) is the pattern."
  pattern: "Mirror Layer A's structure for the new file; use a fake clock `clock=lambda: t[0]` with a
            mutable list; build ids with uuid.UUID(int=n, version=4) formatted lowercase (canonical v4)."
  gotcha: "Do NOT append the native tests to this file (keeps the legacy file byte-identical so its own
           green run is the isolation proof). New file: tests/test_native_recovery.py."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── session_recovery.py      # legacy R.6 SessionRecovery (226 lines) — _fit_text :48, SessionRecovery :84.  ← APPEND NativeRecovery
├── editor_protocol.py       # T3.S2 (complete): is_uuid_v4 :170, utf8_len :175, has_lone_surrogates :180.  READ-ONLY import source
└── editor_session.py        # T3.S4 (parallel, in flight) — NOT touched by this task.
tests/
├── test_session_recovery.py # legacy store tests (433 lines) — must stay green UNMODIFIED.
└── test_native_recovery.py  # ← CREATE (17 tests; pure store + fake clock + thread smoke + isolation pin).
```

### Desired Codebase tree with files to be added/changed

```bash
voice_typing/session_recovery.py   # APPEND: imports (editor_protocol helpers) + native module-docstring paragraph
                                   #   + _MAX_NATIVE_SESSIONS/_MAX_NATIVE_SESSION_BYTES/_NATIVE_SEP + _HeldFinal + _NativeSession
                                   #   + NativeRecoverySnapshot + NativeRecovery (9 methods, injected clock). Legacy lines byte-identical.
tests/test_native_recovery.py      # CREATE: 17 hermetic tests.
# No other file changes (no daemon.py / editor_session.py / editor_protocol.py / ctl.py / config).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TDD: WRITE tests/test_native_recovery.py FIRST (or test-by-test). Against the UNEDITED
# module every `from voice_typing.session_recovery import NativeRecovery` raises ImportError → RED.
# Then append the leaf → GREEN. Run the legacy file too (it must never change).

# CRITICAL #2 — APPEND ONLY; LEGACY BYTE-IDENTICAL. tests/test_session_recovery.py imports
# _MAX_SESSION_BYTES, _MAX_SESSIONS, CompletedSession, SessionRecovery and pins their behavior. Do not
# rename/reorder/re-docstring any legacy symbol. Add the editor_protocol import at the TOP of the
# module's import block (a new line) — that is the ONLY change above the legacy code.

# CRITICAL #3 — THE BUDGET INCLUDES SEPARATORS. budget_used = utf8_len(_NATIVE_SEP.join(f.text for f
# in finals)) — NOT sum(len(f.text)). Test 8 proves it: cap == len(a)+len(b) exactly leaves no room
# for the 1-byte joiner → the oldest is dropped. Getting this wrong makes the "1 MiB including
# separators" contract silently false by (n-1) bytes per session.

# CRITICAL #4 — BOUNDED WHILE ACTIVE: run the cap pass INSIDE retain_final (after append), not only at
# end_session. Order: drop WHOLE OLDEST first while over budget AND len(finals) > 1; then if a LONE
# final still exceeds, clip with _fit_text(text, cap) keeping the START and set truncated=True. Mirror
# SessionRecovery.close_session's two-pass shape (:139-160) — same discipline, different timing.

# CRITICAL #5 — ONE ACTIVE SLOT; NEW-id RETAIN WHILE ACTIVE IS REFUSED. The native reservation is
# exclusive (§4.8.1 B). retain_final(new_id) while active_id() is a different id → return False, state
# untouched. end_session(id) frees the slot. Retain for an ENDED id → False ("reject an id already
# active or retained"). Do NOT auto-end the previous session or create a second active record.

# CRITICAL #6 — THE UNCERTAINTY FLAG LIFECYCLE. mark_offer_attempted(id, seq): True only for a retained
# final in the ACTIVE session; sets offer_attempted (idempotent). NOTHING clears it except
# settle_final (which REMOVES the final). In particular: truncation clipping keeps the flag on the
# clipped final (possibly_applied survives); end_session keeps it; recover() computes
# possibly_applied = any(f.offer_attempted for f in retained). settle_final for an unknown seq → False.

# CRITICAL #7 — EXACTLY-ONCE + VALIDATION AT RETAIN. Reject (False, no mutation): not is_uuid_v4(id);
# has_lone_surrogates(text); not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0;
# not text.strip(); seq already retained in that session; id ended; another id active. Accepted text
# is stored as given (stripped? — store text.strip(); the daemon already cleaned it, but a whitespace-
# only final must not be retained). Never raise for bad input — the reader thread calls this.

# CRITICAL #8 — SNAPSHOT IS FROZEN AND CARRIES NO LIVE REFERENCES. NativeRecoverySnapshot is a
# @dataclass(frozen=True) built under the lock; text is a fresh join; the daemon hands it to the
# control-socket thread (T5.S1) without further locking. Fields map 1:1 to the wire reply
# {ok,id,text,truncated,possibly_applied}; final_count/end_reason/ended_monotonic are diagnostics.

# CRITICAL #9 — recover() DOES NOT DECIDE `busy`. recover(active_id) returns the snapshot (the store is
# a leaf). T5.S1 checks `store.active_id() == id` first and answers `busy`. Document this in the
# recover() docstring so T5.S1's implementer doesn't expect a sentinel here. recover(None) → the
# LATEST ENDED session by ended_monotonic (never the active one). Nothing retained → None (= not_found).

# GOTCHA #10 — LEAF LAW (G2): one threading.Lock; never held across callbacks (there are none); no I/O,
# no logging, no time.time for ordering — use the INJECTED clock (default time.monotonic) so tests use a
# fake. counts() is the only log-facing output (ints). Never let text into logs (G6).

# GOTCHA #11 — UUID FIXTURES MUST BE CANONICAL v4. is_uuid_v4 is STRICT (lowercase, version nibble 4,
# variant 8/9/a/b). Build ids as `str(uuid.UUID(int=n, version=4))` (uuid sets version+variant; str()
# is lowercase). A hand-typed "...-0000-..." id with version 0 is REJECTED — that's test 2's point.

# GOTCHA #12 — FULL PATHS + TIMEOUTS (AGENTS.md Rule 1): `.venv/bin/python -m pytest` (zsh aliases
# shadow python3/pip), wrapped in `timeout` + a bash-tool timeout above it. pytest only — no ruff/mypy.
# No daemon, no foreground process, no CUDA, no socket: the store is pure Python.

# GOTCHA #13 — DO NOT touch editor_protocol.py (T3.S2), editor_session.py/daemon.py/test_editor_session.py
# (T3.S4, parallel), ctl.py (T5.S1/S2), tests/test_session_recovery.py (legacy — must stay unmodified),
# PRD.md, tasks.json, prd_snapshot.md, .gitignore.
```

## Implementation Blueprint

### Data models and structure

```python
# APPEND to voice_typing/session_recovery.py (legacy lines byte-identical; new import line at top)

from voice_typing.editor_protocol import has_lone_surrogates, is_uuid_v4, utf8_len  # (top of file, new line)

# ---- NATIVE RECOVERY (PRD §4.8.1 C) — Mode A: native vs ordinary -------------------------------
# ORDINARY (SessionRecovery, above): one draft at a time; finals + the unfinished TAIL; capped only
#   at close; feeds `voicectl session` (R.6). NATIVE (NativeRecovery, below): keyed by the session's
#   UUIDv4; UNACKNOWLEDGED accepted finals only (no partials, no seed, no tail); capped WHILE ACTIVE
#   (1 MiB UTF-8 including separators); a verified ACK removes a final (budget reclaimed); an offer
#   write ATTEMPTED without a verified ACK is flagged `possibly_applied` (survives truncation/end);
#   ≤ 2 nonempty ended sessions (fully-ACKed/empty endings never evict); feeds `editor-recover` /
#   `voicectl recover` (T5.S1/S2). OWNERSHIP: the daemon retains from the reader thread after the
#   gates (T4.S4), marks BEFORE the socket write, settles on the editor's `applied` (T4.S2), ends with
#   the reservation's reason (T4.S6). UNCERTAINTY: `possibly_applied` means the text MAY already be in
#   the editor — consumers warn, never auto-replay (a lost ACK must not become a second insert).

_MAX_NATIVE_SESSIONS = 2          # §4.8.1 C: two nonempty ended sessions (code constant, NOT config)
_MAX_NATIVE_SESSION_BYTES = 1 << 20  # §4.8.1 C: 1 MiB UTF-8 per session, INCLUDING separators, while active
_NATIVE_SEP = " "                 # single-space join of unacknowledged finals (the recovery text)

@dataclass(frozen=True)
class _HeldFinal:
    seq: int
    text: str
    offer_attempted: bool = False   # set BEFORE the offer write; cleared only by removal (settle_final)

class _NativeSession:               # internal, mutable, guarded by NativeRecovery._lock
    __slots__ = ("session_id", "finals", "truncated", "ended", "end_reason", "ended_monotonic")
    ...

@dataclass(frozen=True)
class NativeRecoverySnapshot:
    """Immutable recovery read — the 1:1 source of T5.S1's {ok,id,text,truncated,possibly_applied} reply."""
    session_id: str
    text: str                 # unacknowledged finals in seq order, single-space joined
    truncated: bool           # a cap pass dropped and/or clipped finals
    possibly_applied: bool    # ANY retained final's offer write was attempted without a verified ACK
    final_count: int          # diagnostics (never on the wire)
    end_reason: str | None    # None while active
    ended_monotonic: float | None
```

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST, then the leaf)

```yaml
Task 1: CREATE tests/test_native_recovery.py FIRST (TDD red) — 17 tests, pure fixtures + fake clock
  - HEADER: mirror tests/test_session_recovery.py (docstring, `from __future__ import annotations`,
    sys.path shims, pytest import). Imports: `from voice_typing.session_recovery import (NativeRecovery,
    NativeRecoverySnapshot, SessionRecovery, _MAX_NATIVE_SESSION_BYTES, _MAX_NATIVE_SESSIONS)`.
  - HELPERS: `_id(n) -> str` = `str(uuid.UUID(int=n, version=4))` (canonical lowercase v4 — Gotcha #11);
    `_clock()` returns `(lambda: t[0], t)` with `t = [1000.0]`.
  - TESTS (names verbatim; assertions per research §4):
      1  test_retain_final_creates_active_session_and_snapshot_lists_text_in_seq_order
      2  test_retain_rejects_non_uuid_lone_surrogates_bad_seq_and_duplicates
      3  test_second_active_session_is_refused_while_one_is_active
      4  test_mark_offer_attempted_sets_possibly_applied
      5  test_verified_ack_removes_final_and_reclaims_budget
      6  test_mark_attempt_survives_truncation
      7  test_overflow_drops_whole_oldest_first_while_active     (NativeRecovery(max_session_bytes=100))
      8  test_overflow_separators_count_toward_budget            (cap == len(a)+len(b) exactly)
      9  test_end_session_retains_unacknowledged_and_discards_empty
      10 test_two_ended_sessions_cap_evicts_oldest_nonempty
      11 test_recover_omitting_id_selects_latest_ended           (advance the fake clock between ends)
      12 test_retain_after_end_is_refused
      13 test_unicode_finals_round_trip_and_clip_on_codepoint_boundary  (CJK "汉" ×N + "😀"; clipped text
          encodes ≤ cap and decodes; no replacement char)
      14 test_clear_drops_everything_and_store_is_reusable
      15 test_counts_are_counts_only
      16 test_concurrent_retain_and_settle_thread_safety_smoke  (bounded: 4 threads × 200 ops; final
          invariant: every retained seq unique; counts() consistent)
      17 test_legacy_session_recovery_untouched                  (a SessionRecovery instance's state is
          unaffected by any NativeRecovery mutation; both classes coexist)
  - RUN (confirm RED): cd /home/dustin/projects/voice-typing && timeout 120 .venv/bin/python -m pytest tests/test_native_recovery.py -q
    → ImportError: cannot import name 'NativeRecovery' (every test errors). That is the TDD baseline.

Task 2: EDIT voice_typing/session_recovery.py — the import + the native module-docstring paragraph
  - ADD at the top import block (new line after `import threading`/`import time`/`from dataclasses import dataclass`):
      from voice_typing.editor_protocol import has_lone_surrogates, is_uuid_v4, utf8_len
  - APPEND to the module docstring (after the existing "Draft accumulation note" paragraph) the
    NATIVE RECOVERY paragraph from the Blueprint's data-models block (Mode A: native vs ordinary,
    ownership, uncertainty). Do NOT alter the existing header text.

Task 3: EDIT voice_typing/session_recovery.py — constants + _HeldFinal + _NativeSession + NativeRecoverySnapshot
  - APPEND after the SessionRecovery class (end of file): the block from the Blueprint's data-models
    section, verbatim (constants, _HeldFinal, _NativeSession with __slots__, NativeRecoverySnapshot).

Task 4: EDIT voice_typing/session_recovery.py — the NativeRecovery class (the 9 methods)
  - SIGNATURES + SEMANTICS (every method `with self._lock:`; never raises on bad input):
      __init__(self, max_sessions=_MAX_NATIVE_SESSIONS, max_session_bytes=_MAX_NATIVE_SESSION_BYTES,
               clock: Callable[[], float] = time.monotonic)
          state: _active: _NativeSession | None; _ended: list[_NativeSession] (oldest first, ≤ max_sessions)
      retain_final(session_id, seq, text) -> bool
          validate (Gotcha #7) → False on any failure; auto-create _active if None; append _HeldFinal(seq,
          text.strip()); then the cap pass (Gotcha #4) — drop whole oldest while over budget and len>1;
          clip a lone oversized via _fit_text(…, cap) + truncated=True; return True.
      mark_offer_attempted(session_id, seq) -> bool
          True iff _active and _active.session_id == session_id and a final with that seq exists → set flag.
      settle_final(session_id, seq) -> bool
          True iff found in _active → REMOVE it (budget reclaimed); False otherwise (incl. ended/unknown).
      end_session(session_id, reason) -> None
          iff _active and ids match: set ended=True, end_reason=reason, ended_monotonic=clock(); if no
          finals remain → discard (do not touch _ended); else append to _ended and
          `del _ended[:-max_sessions]`. Free _active. Unknown/already-ended id → no-op.
      recover(session_id=None) -> NativeRecoverySnapshot | None
          None + _ended empty → None; None → _ended[-1]; id matches an ended → that; id == active id →
          the active snapshot (the store does NOT decide `busy` — Gotcha #9); else None. Snapshot built
          under the lock: text = _NATIVE_SEP.join(f.text…), possibly_applied = any(flag), truncated from
          the session, final_count = len(finals), end_reason/ended_monotonic (None while active).
      active_id() -> str | None
      counts() -> tuple[int, int]        # (len(_ended), len(_active.finals) if active else 0)
      clear() -> None                    # _active = None; _ended = []
  - Each method gets a Mode A docstring (retain/mark/settle/end/read/clear + ownership + uncertainty).

Task 5: VERIFY — TDD green + legacy/protocol untouched
  - RUN:
      cd /home/dustin/projects/voice-typing
      timeout 120 .venv/bin/python -m pytest tests/test_native_recovery.py -q
      timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py tests/test_editor_protocol_vectors.py -q
      timeout 120 .venv/bin/python -m py_compile voice_typing/session_recovery.py && echo compiles
  - EXPECTED: 17 passed; legacy + vectors green (unmodified); compiles.

Task 6: VALIDATE — the Validation Loop L1–L4. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T4.S1: NativeRecovery leaf added to session_recovery.py (id-keyed, unACKed
  finals only, 1 MiB UTF-8 bounded while active incl. separators, offer-attempt uncertainty flag,
  verified-ACK reclaim, ≤2 nonempty ended, frozen snapshots for T4.S2/S6 + T5.S1); legacy
  SessionRecovery byte-identical; 17 hermetic tests green."
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the cap pass runs at EVERY retain (bounded while active), two passes like the legacy
# close_session (:139-160) but on the live list. Budget INCLUDES the joiner:
def _cap_locked(self, s: _NativeSession) -> None:
    while len(s.finals) > 1 and utf8_len(_NATIVE_SEP.join(f.text for f in s.finals)) > self._max_session_bytes:
        s.finals.pop(0); s.truncated = True            # whole OLDEST first ("newest complete finals that fit")
    if s.finals and utf8_len(s.finals[0].text) > self._max_session_bytes:   # a LONE oversized final
        f = s.finals[0]
        s.finals[0] = _HeldFinal(f.seq, _fit_text(f.text, self._max_session_bytes), f.offer_attempted)
        s.truncated = True                               # clipped for RECOVERY only; flag SURVIVES

# PATTERN 2 — retain validation returns False, never raises (reader-thread safe):
if (not is_uuid_v4(session_id) or has_lone_surrogates(text) or isinstance(seq, bool)
        or not isinstance(seq, int) or seq <= 0 or not text.strip()):
    return False
if self._ended and any(e.session_id == session_id for e in self._ended): return False   # "already retained"
if self._active is not None and self._active.session_id != session_id: return False       # one active slot

# PATTERN 3 — the frozen snapshot is built under the lock and handed off lock-free (T5.S1 reads it):
return NativeRecoverySnapshot(session_id=s.session_id, text=_NATIVE_SEP.join(f.text for f in s.finals),
                              truncated=s.truncated, possibly_applied=any(f.offer_attempted for f in s.finals),
                              final_count=len(s.finals), end_reason=s.end_reason, ended_monotonic=s.ended_monotonic)
```

### Integration Points

```yaml
DELTA ACCEPTANCE (PRD §4.8.1 C — native recovery bullet):
  - Every clause is implemented in the leaf: id-keyed, ≤2 nonempty ended, 1 MiB UTF-8 incl. while active,
    ACK reclaims budget, newest-complete-first overflow, truncation marked, lone-final clipping
    (recovery only), possibly_applied semantics, no persistence (clear at exit), no partials/seed.
  - The wire reply (7 MiB escaped cap, not_found/busy) is T5.S1's; `voicectl recover` is T5.S2's.

CONSUMERS (downstream — the contract's OUTPUT):
  - P1.M1.T4.S2 (one sequenced offer + verified ACK): calls mark_offer_attempted(id, seq) BEFORE the
    socket write and settle_final(id, seq) on the editor's `applied`. Never re-sends: the flag persists.
  - P1.M1.T4.S6 (finalize ownership + failure hints): calls end_session(id, reason) with the EndRecord's
    reason; reads recover(id) for the "recoverable" flag on the `ended` frame + the hint.
  - P1.M1.T5.S1 (owner-only capped recovery reply): `active_id() == id` → busy; recover(id or None) →
    None → not_found; else {ok:true,id,text,truncated,possibly_applied} from the snapshot, escaped ≤7 MiB.
  - P1.M1.T4.S4 (route native finals, later): retain_final(id, seq, text) from the reader thread AFTER
    clean/filter, BEFORE any generic output (per system_context) — the store is lock-safe there.

PARALLEL — P1.M1.T3.S4 (in flight): editor_session.py + daemon.py + test_editor_session.py — DISJOINT.
   NativeRecovery takes plain `str` ids/reasons (no editor_session import) so T3.S4's class shapes
   cannot break this task and there is no import cycle.

NO INTERFACE / CONFIG CHANGES: no config keys (code constants), no socket, no daemon edits, no state.json.
```

## Validation Loop

> Full paths (zsh aliases shadow python3/pip); inner `timeout` on every pytest/py_compile invocation
> (AGENTS.md Rule 1) + the bash-tool timeout above it. pytest only (no ruff/mypy). Pure Python — no
> daemon, no socket, no CUDA, no foreground process.

### Level 1: The leaf is in place and compiles (static)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/session_recovery.py && echo "L1 PASS: compiles"
echo "--- public surface ---"
grep -nE "^class NativeRecovery|^class NativeRecoverySnapshot|^class _HeldFinal|^class _NativeSession|^_MAX_NATIVE_SESSIONS|^_MAX_NATIVE_SESSION_BYTES|^_NATIVE_SEP|def (retain_final|mark_offer_attempted|settle_final|end_session|recover|active_id|counts|clear)\(" voice_typing/session_recovery.py
echo "--- legacy symbols untouched (diff shows only additions above/below them) ---"
git diff voice_typing/session_recovery.py | grep -E '^-[^-]' && echo "L1 FAIL: a legacy line was removed/changed" || echo "L1 PASS: no removed lines — append-only"
# Expected: compiles; all symbols present; `git diff` has NO '-' lines (append-only except the one
# added import line, which is also an addition).
```

### Level 2: TDD red→green + legacy + protocol vectors

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- the new leaf suite (GREEN after Tasks 2-4; RED per Task 1 before) ---"
timeout 120 "$PY" -m pytest tests/test_native_recovery.py -q 2>&1 | tail -3
echo "--- legacy store + protocol vectors (unmodified files must stay green) ---"
timeout 300 "$PY" -m pytest tests/test_session_recovery.py tests/test_editor_protocol_vectors.py -q 2>&1 | tail -3
# Expected: 17 passed; legacy + vectors green. Record the counts.
```

### Level 3: The contract's properties hold empirically (doubles, fake clock)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python - <<'PY'
import uuid
from voice_typing.session_recovery import NativeRecovery, _MAX_NATIVE_SESSION_BYTES
_id = lambda n: str(uuid.UUID(int=n, version=4))
r = NativeRecovery()
a, b = _id(1), _id(2)
# bounded WHILE active incl. separators: 1 MiB cap; a 1.2 MiB lone final clips to <= cap
assert r.retain_final(a, 1, "x" * (1_200_000)) is True
snap = r.recover(a); assert len(snap.text.encode()) <= _MAX_NATIVE_SESSION_BYTES and snap.truncated
# uncertainty survives; verified ACK reclaims
assert r.retain_final(a, 2, "second") and r.mark_offer_attempted(a, 2) and r.recover(a).possibly_applied
assert r.settle_final(a, 2) is True and not r.recover(a).possibly_applied and r.recover(a).final_count == 1
# one active slot; ended ids retained; empty ending never evicts
assert r.retain_final(b, 1, "other") is False           # a still active
r.end_session(a, "disconnected"); assert r.recover(a).end_reason == "disconnected"
assert r.retain_final(b, 1, "other") and r.settle_final(b, 1); r.end_session(b, "stopped")
assert r.recover(b) is None and r.recover(a) is not None  # fully-ACKed ending discarded, a intact
assert r.recover() .session_id == a                     # latest ENDED nonempty
print("L3 PASS: bounded-while-active, uncertainty, ACK reclaim, one-active-slot, no-evict-on-empty")
PY
# Expected: PASS — every clause of §4.8.1 C exercised end-to-end on the real leaf.
```

### Level 4: Scope guards — only the 2 in-scope files changed

```bash
cd /home/dustin/projects/voice-typing
git status --short | grep -vE 'plan/' 
git diff --name-only
# Expected: voice_typing/session_recovery.py (M) + tests/test_native_recovery.py (??) — nothing else
git diff --exit-code -- voice_typing/editor_protocol.py voice_typing/daemon.py tests/test_session_recovery.py voice_typing/ctl.py config.toml voice_typing/config.py PRD.md && echo "L4 PASS: sibling/parallel/read-only files untouched"
# (editor_session.py may appear as T3.S4's untracked add — not this task's; do not touch it.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: module compiles; all native symbols present; `git diff` shows no removed legacy lines (append-only).
- [ ] L2: `tests/test_native_recovery.py` 17 passed (RED first per Task 1); `test_session_recovery.py` + `test_editor_protocol_vectors.py` green unmodified.
- [ ] L3: the empirical probe proves bounded-while-active (lone 1.2 MiB final clips ≤ cap, truncated), uncertainty flag, ACK reclaim, one-active-slot, empty-ending-no-evict, latest-ended selection.
- [ ] L4: exactly `session_recovery.py` + `test_native_recovery.py` changed; editor_protocol/daemon/test_session_recovery/ctl/config/PRD untouched.

### Feature Validation
- [ ] Every §4.8.1 C clause maps to a passing test (1–14); thread-safety smoke (16); legacy isolation pin (17).
- [ ] `NativeRecoverySnapshot` fields = the wire reply 1:1 (+ diagnostics); frozen; built under the lock.
- [ ] `recover()` documented as NOT deciding `busy` (T5.S1 uses `active_id()`).
- [ ] Rejections return False and never mutate state (test 2/3/12).

### Code Quality / Scope Validation
- [ ] Legacy `SessionRecovery`/`CompletedSession`/`_fit_text` byte-identical; one new import line at the top.
- [ ] Leaf law kept: one lock, no callbacks, no I/O, no logging, injected clock, counts-only diagnostics.
- [ ] Reused `editor_protocol` helpers (no duplicated UUID/UTF-8 logic) and `_fit_text` (no second clipper).
- [ ] Code constants, not config; no new dependencies.

### Documentation & Deployment
- [ ] [Mode A] module-docstring "NATIVE RECOVERY" paragraph (native vs ordinary, ownership, uncertainty) + per-method docstrings.
- [ ] No config/env/socket/state.json changes.

---

## Anti-Patterns to Avoid

- ❌ Don't modify the legacy `SessionRecovery`, `CompletedSession`, `_fit_text`, or any existing line (append-only + one import line) — the legacy test file is the isolation proof (Gotcha #2).
- ❌ Don't reuse `SessionRecovery` for native or add ACK/uncertainty state to it — different content (no tail), different timing (bounded while active), different keying (UUIDv4); the contract says "isolate legacy" (Why §2).
- ❌ Don't compute the budget as the sum of part lengths — separators count (Gotcha #3, test 8).
- ❌ Don't apply the cap only at `end_session` — it must run at every `retain_final` (Gotcha #4).
- ❌ Don't allow a second active session, auto-end the previous one, or re-retain an ended id (Gotcha #5).
- ❌ Don't clear `offer_attempted` on truncation/end or anything other than removal via `settle_final`; don't `mark` a seq in an ended/unknown session (Gotcha #6).
- ❌ Don't raise on bad input in `retain_final` — the reader thread calls it; return False (Gotcha #7).
- ❌ Don't return live internal lists from `recover()`/`counts()` — frozen snapshot, ints only (Gotcha #8/#10).
- ❌ Don't make `recover(active_id)` return `busy`/None — return the snapshot; T5.S1 decides busy via `active_id()` (Gotcha #9).
- ❌ Don't hand-type UUID fixtures — `str(uuid.UUID(int=n, version=4))` (strict `is_uuid_v4`, Gotcha #11).
- ❌ Don't edit `editor_protocol.py`, `editor_session.py`, `daemon.py`, `ctl.py`, `tests/test_session_recovery.py`, or read-only files (Gotcha #13); don't import `editor_session` into the store (decoupling from T3.S4).
- ❌ Don't run pytest without `timeout`/with bare `python`, and don't invent ruff/mypy gates (Gotcha #12).

---

## Confidence Score

**9.5/10** for one-pass implementation success. The legacy module was read in full this round (shape, `_fit_text`, leaf law), the native requirements are quoted verbatim from PRD §4.8.1 C + the architecture's explicit `NativeRecovery` proposal, the reusable `editor_protocol` helpers are confirmed present with line numbers, every public method's accept/reject semantics and the two load-bearing subtleties (separators-in-budget; one-active-slot refusal) are spelled out with tests that discriminate them, the snapshot shape is fixed 1:1 to the wire reply, and the parallel T3.S4 owns disjoint files with no import coupling. The −0.5 residual is the small chance of an off-by-one in the lone-final clip reserve (there is no tail reserve here, unlike the legacy close — `_fit_text(text, cap)` directly) — which test 6/13's `≤ cap` assert catches immediately. No CUDA, socket, or daemon involved.

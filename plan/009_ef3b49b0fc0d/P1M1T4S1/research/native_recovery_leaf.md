# Research — P1.M1.T4.S1: Retain bounded native recovery in memory (NativeRecovery leaf)

> PRD §4.8.1 C ("Keep native recovery in daemon memory only, separately keyed by id ...") +
> architecture/system_context.md "Buffer ownership and recovery". The legacy `SessionRecovery`
> (voice_typing/session_recovery.py) is an ORDINARY-session store (finals + unfinished tail, cap applied
> only at close) — wrong for native: native retains UNACKNOWLEDGED accepted finals only, must be bounded
> WHILE ACTIVE, must carry an "offer attempted but not verified" uncertainty flag, and is keyed by UUIDv4.
> Decision: a SEPARATE `NativeRecovery` leaf in the same module (reuse `_fit_text` byte discipline only).

## §1 — Why the legacy store is wrong for native (verified, session_recovery.py @HEAD)

| Aspect | `SessionRecovery` (ordinary, R.6) | Native requirement (§4.8.1 C) |
|---|---|---|
| Keyed by | the single "current draft" (one session at a time) | **session id (UUIDv4)** — up to two ENDED sessions retained + the ACTIVE one |
| Content | accepted finals + the unfinished **tail** (partials) | **unacknowledged accepted finals only** — NO partials, NO seed, NO tail |
| Cap timing | 1 MiB applied **only at close** (draft grows unbounded while open — documented) | 1 MiB UTF-8 **including while active**, for the unacknowledged suffix |
| ACK awareness | none | verified ACK → the final is **reclaimed** from the budget (removed) |
| Uncertainty | none | **possibly_applied**: an offer write was ATTEMPTED but not verified → survives truncation/loss |
| Eviction | empty/failed arms never evict; ≤ 2 completed | ≤ 2 **nonempty ended** sessions; "fully acknowledged or empty endings do not evict previous recovery" |

Reusing `SessionRecovery` directly would (a) pollute the ordinary `voicectl session` path, (b) keep
partial text the PRD forbids in native recovery, and (c) be unbounded while active. Hence: a separate
leaf, same module, shared pure byte helper. The contract says "isolate legacy SessionRecovery" —
NativeRecovery must not touch `SessionRecovery`'s state or API; `daemon.py` wiring is NOT in scope.

## §2 — Inputs available (from the completed/parallel contracts)

- **Schema/vectors (T3.S2, COMPLETE) — `voice_typing/editor_protocol.py`:** `is_uuid_v4(value)` (:170,
  strict canonical lowercase v4), `utf8_len(text)` (:175), `has_lone_surrogates(text)` (:180),
  `MAX_FINAL_TEXT_BYTES = 4 KiB` (:116), `MAX_FRAME_BYTES = 32 KiB` (:22), `END_REASONS` (:144),
  `ProtocolError(code, detail)` (:156). NativeRecovery IMPORTS `is_uuid_v4`, `utf8_len`,
  `has_lone_surrogates` (no duplication) — the module is pure stdlib + this leaf import (no socket).
- **Reservation (T3.S4, in flight) — `voice_typing/editor_session.py`:** `Owner`, `EndRecord`
  (carries `id`, `reason` ∈ END_REASONS), `Stage`. NativeRecovery consumes only the **id string** and
  the **reason string** — no object coupling, so T3.S4's exact class shapes cannot break this task.
- **Signals (from T4.S2 — one sequenced offer/verified ACK; T4.S4 — route native finals):**
  accepted final `(session_id, seq, text)`; **offer-attempt** `(id, seq)` marked BEFORE the socket
  write; **verified ACK** `(id, seq)` only after the editor's `applied` for the outstanding seq.

## §3 — The NativeRecovery design (pure, leaf, fake-clock injectable)

**Constants (code constants, NOT config — mirror the legacy module):**
`_MAX_NATIVE_SESSIONS = 2`, `_MAX_NATIVE_SESSION_BYTES = 1 << 20` (1 MiB UTF-8, INCLUDING the
single-space separators between retained finals), `_NATIVE_SEP = " "`.

**Per-session record (`_NativeSession`, internal):** `finals: list[_HeldFinal]` (ordered by seq),
`ended: bool`, `end_reason: str | None`. `_HeldFinal = dataclass(frozen)`: `seq: int`, `text: str`,
`offer_attempted: bool` (set by `mark_offer_attempted`, never cleared).

**Byte accounting INCLUDING separators:** `rendered = " ".join(f.text for f in finals)`; budget
check uses `utf8_len(rendered)`. On overflow: drop the WHOLE OLDEST final first ("retain the newest
complete finals that fit"); if a LONE final still exceeds the cap, clip it with `_fit_text`
(codepoint-safe, keeps the START — the recoverable part) and set `truncated=True`. This is the
"lone oversized final may be safely clipped for recovery only" carve-out. The `_fit_text` helper
(`session_recovery._fit_text`, codepoint binary search, never splits a surrogate pair) is REUSED
verbatim — it is already UTF-8-safe.

**Uncertainty metadata survives truncation/loss:** `possibly_applied` is computed from the RETAINED
finals' `offer_attempted` flags — so a clipped final still reports its own flag; a dropped final's
flag is lost by necessity but `truncated=True` tells the consumer the record is incomplete (the
PRD's "keep attempted/uncertain metadata safe through truncation" — we preserve it for everything
retained and flag the loss). The flag is set at `mark_offer_attempted` time and NEVER cleared by
anything except a verified ACK (which REMOVES the final entirely).

**Public interface (the contract's OUTPUT):**

```python
class NativeRecovery:
    def __init__(self, max_sessions=_MAX_NATIVE_SESSIONS, max_session_bytes=_MAX_NATIVE_SESSION_BYTES,
                 clock: Callable[[], float] = time.monotonic) -> None: ...
    # retain
    def retain_final(self, session_id: str, seq: int, text: str) -> bool
        # False (no-op) if id not UUIDv4 / has_lone_surrogates / seq <= 0 / unknown-or-ended session
        #   / duplicate seq (exactly-once) / text empty-after-strip. Active sessions are auto-created
        #   on first retain ONLY if one is allowed (see "active slot" below). Applies the cap AFTER
        #   insertion (bounded while active).
    # mark-attempt
    def mark_offer_attempted(self, session_id: str, seq: int) -> bool
        # True iff a retained final with that seq exists in the ACTIVE session; sets offer_attempted.
        # Called BEFORE the socket write (so an exception mid-write still leaves the flag set).
    # settle (verified ACK)
    def settle_final(self, session_id: str, seq: int) -> bool
        # True iff a retained final with that seq existed in the ACTIVE session → REMOVED (budget reclaimed).
    # end
    def end_session(self, session_id: str, reason: str) -> None
        # Active → ended. If NOTHING retained → the record is DISCARDED (does not evict anything —
        # "fully acknowledged or empty endings do not evict previous recovery"). Else appended to the
        # ≤2 ended deque (oldest nonempty evicted). Unknown id → no-op.
    # read
    def recover(self, session_id: str | None = None) -> NativeRecoverySnapshot | None
        # None (= wire `not_found`) when nothing retained; omitted id → the LATEST ended session
        # (by end time). Returns an immutable snapshot — see below.
    def active_id(self) -> str | None
    def counts(self) -> tuple[int, int]           # (ended sessions retained, active retained finals) — counts ONLY, for logs
    # clear
    def clear(self) -> None                        # daemon exit — drops active + ended
```

**Active-slot rule:** at most ONE active session (the native reservation is exclusive — §4.8.1 B).
A `retain_final` for a NEW id while another is active → no-op (False) — the reservation layer
(T3.S4) already guarantees exclusivity; the store refuses rather than corrupts. `end_session`
frees the slot. A re-retain for an ENDED id → no-op (reject "an id already active or retained").

**Snapshot (`NativeRecoverySnapshot`, frozen dataclass) — the contract for T4.S6 + T5.S1:**

```python
@dataclass(frozen=True)
class NativeRecoverySnapshot:
    session_id: str
    text: str            # unacknowledged finals in seq order, single-space joined (the RECOVERY text)
    truncated: bool      # size-cap clipping happened (dropped and/or clipped finals)
    possibly_applied: bool  # ANY retained final had offer_attempted=True
    final_count: int     # number of retained finals (diagnostic; not on the wire)
    end_reason: str | None  # None while active (recover() of the ACTIVE id is the daemon's `busy` decision, not the store's)
    ended_monotonic: float | None
```

`recover(active_id)` still returns the snapshot (the store is a leaf; T5.S1 decides `busy` for the
active id before calling — expose `active_id()` for that check). The wire reply
`{"ok":true,"id","text","truncated","possibly_applied"}` maps 1:1 from the snapshot; the 7 MiB
escaped-JSON cap is T5.S1's concern (text ≤ 1 MiB UTF-8 → worst-case JSON escaping of control
chars ≈ 6× → the 7 MiB bound; the store guarantees the text bound).

**Thread discipline (G2 leaf law, same as the legacy store):** one `threading.Lock`, never held across
callbacks (there are none), no I/O, no logging, O(1) hooks (`retain/mark/settle` are list ops on ≤ a
few thousand finals), `end_session` bounded (≤ ~1 MiB encode worst case). Safe under the daemon's
`_lock` and on the reader thread — but T4.S4 must call `retain_final` from the reader thread WITHOUT
the control lock (per system_context) — that's the daemon's concern; the store itself is safe anywhere.

**Unicode safety:** reject `has_lone_surrogates(text)` at retain (a str that cannot encode); the cap
accounting is in UTF-8 bytes via `utf8_len`; clipping uses `_fit_text` (codepoint-safe). Non-BMP
(emoji) and CJK finals round-trip. No normalization, no `\s` tricks.

## §4 — TDD tests (tests/test_native_recovery.py — NEW, pure fixtures + fake clock, no I/O)

The legacy test file (tests/test_session_recovery.py) is the pattern: `sys.path` shims + direct
store calls + a bounded thread-safety smoke. Fake clock = a `clock()` closure over a mutable list.

1. `test_retain_final_creates_active_session_and_snapshot_lists_text_in_seq_order` — retain seq 1,2,3;
   `recover()` → text "a b c", possibly_applied False, truncated False, end_reason None.
2. `test_retain_rejects_non_uuid_lone_surrogates_bad_seq_and_duplicates` — each → False; state unchanged.
3. `test_second_active_session_is_refused_while_one_is_active` — retain(id2) → False; after `end_session(id1)`
   retain(id2) → True.
4. `test_mark_offer_attempted_sets_possibly_applied` — mark seq 2 → snapshot.possibly_applied True.
5. `test_verified_ack_removes_final_and_reclaims_budget` — settle seq 2 → text "a c", possibly_applied False.
6. `test_mark_attempt_survives_truncation` — 1 MiB cap; retain a huge final (~1.2 MiB "x"*N) marked
   attempted, then a small one → the huge is clipped (start kept), truncated True, possibly_applied True.
7. `test_overflow_drops_whole_oldest_first_while_active` — cap 100 B; retain 3×"a"*40 → oldest dropped,
   truncated True, text is the 2 newest joined; `counts()` active finals == 2.
8. `test_overflow_separators_count_toward_budget` — cap exactly len(a)+len(b) (no room for the space)
   → b retained alone / a dropped (truncated) — proves separators are accounted.
9. `test_end_session_retains_unacknowledged_and_discards_empty` — ended with 1 unacked → recoverable;
   a second session fully ACKed then ended → discarded, does NOT evict the first (recover(first) intact).
10. `test_two_ended_sessions_cap_evicts_oldest_nonempty` — three nonempty ended → first gone (None), two kept.
11. `test_recover_omitting_id_selects_latest_ended` — two ended with distinct fake end times → latest.
12. `test_retain_after_end_is_refused` — retain(ended id) → False.
13. `test_unicode_finals_round_trip_and_clip_on_codepoint_boundary` — CJK + emoji; a clipped lone final
    encodes ≤ cap and decodes (no split codepoint).
14. `test_clear_drops_everything_and_store_is_reusable` — clear → recover None, active_id None; a new
    retain works afterwards.
15. `test_counts_are_counts_only` — counts() returns ints; snapshot exposes no raw list.
16. `test_concurrent_retain_and_settle_thread_safety_smoke` — bounded threads (mirror the legacy smoke).
17. `test_legacy_session_recovery_untouched` — import both; mutate NativeRecovery; a SessionRecovery
    instance's state is unaffected (isolation pin).

## §5 — Verify + scope

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_native_recovery.py -q
timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py tests/test_editor_protocol_vectors.py -q   # legacy + protocol untouched
```

Scope: `voice_typing/session_recovery.py` (APPEND NativeRecovery + snapshot + Mode A docstrings; legacy
code byte-identical) + `tests/test_native_recovery.py` (NEW). NO daemon.py (T4.S4/T4.S6 wire it), NO
editor_protocol.py / editor_session.py (T3.S2 done / T3.S4 in flight), NO ctl.py (T5.S1/S2), no config.
The parallel T3.S4 owns editor_session.py + daemon.py + test_editor_session.py — DISJOINT.

Machine gotchas: `.venv/bin/python` full path; `timeout` wrapper (AGENTS.md Rule 1); pytest only; no
daemon/foreground/CUDA — the store is pure Python.

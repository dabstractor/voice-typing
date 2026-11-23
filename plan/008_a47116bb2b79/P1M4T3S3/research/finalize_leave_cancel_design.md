# P1.M4.T3.S3 research — finalize/leave/cancel semantics (ime target adapter)

## §1 Consumed-surface anchors (live-verified 2026-12, pre-S2-merge; S2 assumed landed per its PRP)

| Surface | Anchor | Fact |
|---|---|---|
| DeliveryTarget protocol | `voice_typing/bulk_delivery.py` `DeliveryTarget` | `finalize(session, utterance, seq, expected_revision, span) -> ShowResult` (same signature as show); `leave() -> None`; `cancel() -> ShowResult` — cancel docstring: "nothing pending ⇒ unchanged" |
| Controller span model | `bulk_controller.py:672` `_process_next` | `prev_span = self._shown_span.get(key, "")` where `key=(gen, utterance)` — **span is PER-UTTERANCE, starts ""** ⇒ the adapter's owned span is per-utterance too; committed bytes are NOT |
| Controller finalize dispatch | `bulk_controller.py:678` | `op = self._target.show if isinstance(item, _Partial) else self._target.finalize` — same op runner, 250 ms deadline, +1 revision ONLY on APPLIED (:721); UNCHANGED keeps active (:726); REFUSED/UNKNOWN stop |
| Controller leave | `bulk_controller.py:331-366` `stop(leave=True)` | calls `target.leave()` **directly, OUTSIDE the op runner** — a raising/wedged leave must not mask the stop reason (try/except there, but adapter must never raise/hang) |
| Controller cancel | `bulk_controller.py:368-451` | purges queued partials + closes their boundaries controller-side, then ONE `target.cancel()` through the runner; APPLIED ⇒ +1 revision, STAYS active; UNCHANGED ⇒ fine; REFUSED/UNKNOWN ⇒ stop, never retry. Reaches the target ONLY when a partial was pending — but the adapter's owned span may still be "" (partial queued, not yet dispatched) ⇒ **UNCHANGED-for-empty-owned is load-bearing** |
| Rejected final | `bulk_controller.py:554+` `on_final_dropped` | NO finalize call, ever (pinned `tests/test_bulk_controller.py:259`) — the adapter NEVER hears about rejections; it must self-heal via the utterance switch |
| Host `_show` | `ime_host.py:174-197` | `before>0` ⇒ `delete_surrounding_text(before,0)` + `commit_string(text)` + `commit(dones)` in ONE commit; applied = dones increment within `SHOW_CONFIRM_WAIT = 0.22` (:38); wire Exception ⇒ unknown; not-activated ⇒ refused |
| Host `_leave` | `ime_host.py:214-221` | releases grab if held, replies `{ok:true}`, KEEPS SERVING — already in `REQUEST_CMDS`; adapter leave is daemon-side bookkeeping + this best-effort request |
| Protocol cancel | `ime/protocol.py:37,81-82` | `REQUEST_CMDS` excludes cancel; `validate_request` returns error `"cancel reserved (P1.M4.T3.S3)"` — **this task owns lifting the reservation**; pinned by `tests/test_ime_host.py:101 test_cancel_reserved` (must be REPLACED) and protocol tests |
| Verify snapshot | `ime_host.py:199-212` | head cap `_SNAPSHOT_HEAD_BYTES = 64 KiB`, `snapshot_truncated` flag — verification-bounded cancel (refuse past the cap) |
| S2's guards | `ime/target.py` (post-S2) | `recheck(binding, inserted_bytes) -> (ok, reason, rev)` caret math = `binding.cursor_bytes + inserted_bytes`; `_owned_region_intact(binding, owned)` slices `[binding.cursor_bytes, cursor_bytes+owned_bytes)`; correction advance SETs `_inserted_bytes = span_bytes` |
| Legacy cancel compensation | `daemon.py:1938-1968` | legacy path does `press_backspace(max(len(tail)-1, 0))` — the −1 physical-keystroke compensation is LEGACY-ONLY; bulk cancel sends `before == owned_bytes` EXACTLY (M6.T2.S1 routes bulk cancel before `daemon.cancel`) |
| G2 fake target | `tests/test_g2_bulk_gate.py:126-228` | cancel: nothing owned ⇒ UNCHANGED +0 edits; owned ⇒ range removed, caret back to owned start, +1 edit; trace_07 repeated cancel pins idempotence |
| Test helpers | `tests/test_ime_target.py` | `_FakeProc` (:21, scripted replies, None=dead), `_snap` (:33), `_verify` (:40), `_bound` (:47) |

## §2 The state-machine derivation (the core design)

Controller spans are per-utterance; committed bytes are cumulative. Therefore the adapter needs TWO
orthogonal trackers it doesn't have yet:

- `_owned_utterance: str | None` — which utterance the current `_last_applied_span` belongs to.
- `_closed_utterances: set[str]` — utterances settled by finalize/cancel (defensive: late strays REFUSE, never mutate).

**Invariant (extends S2's):** `_inserted_bytes` = bytes of everything WE committed since acquire =
bytes(prior settled utterances) + bytes(current owned span). The owned span is always the contiguous
suffix `[caret − owned_bytes, caret)` of our committed range.

Three behavior-preserving-in-S2's-world edits to S2's landed code (S2's world has exactly one
utterance per acquisition, where `_inserted_bytes == len(_last_applied_span.encode())` ALWAYS —
so each edit's S2-world result is byte-identical, S2's tests stay green):

1. **show() top — utterance-switch guard** (~5 lines): if `_owned_utterance` set and differs ⇒ the
   previous utterance's final was dropped/rejected (no finalize ever came): reset
   `_last_applied_span = ""` (visible words STAY — never erased), KEEP `_inserted_bytes` (caret
   math spans utterances). Then `_owned_utterance = utterance`. Plus the closed-set refusal.
2. **`_owned_region_intact` anchor**: slice `[binding.cursor_bytes + self._inserted_bytes −
   owned_bytes, +owned_bytes)` instead of `[binding.cursor_bytes, ...)`. S2-world: equal.
3. **Correction advance**: `_inserted_bytes = self._inserted_bytes − owned_bytes + span_bytes`
   instead of `= span_bytes`. S2-world: equal. Cancel is the `span_bytes = 0` case:
   `_inserted_bytes -= owned_bytes`.

**finalize()** = guard (not-acquired / closed) + delegate to `self.show(...)` (the differing-final
branch IS "ONE replacement" — the same op) + on APPLIED/UNCHANGED settle: `_last_applied_span=""`,
`_owned_utterance=None`, add to closed set. Zero-diff ⇒ UNCHANGED with NO request (no commit ⇒ no
side effects ⇒ cannot duplicate). Missed-live-update = finalize applied with no prior applied
partial of this utterance → log `live=false` (counts/times only). Latency-evidence COUNTING is
M6.T4/G5 — fenced here.

**leave()** = clear binding FIRST, then best-effort `request("leave", timeout=0.25)` never raising;
idempotent no-op when unbound; NO field writes; post-leave show/finalize/cancel ⇒ REFUSED
"not acquired" until fresh acquire.

**cancel()** = nothing pending (unbound ⇒ REFUSED "not acquired"; empty owned ⇒ UNCHANGED "nothing
pending", no request) / owned ⇒ recheck(caret at end of owned) + `_owned_region_intact` (uncertain
range ⇒ REFUSED — stop, never repair) + ONE `request("cancel", timeout=0.25, before=owned_bytes)`
— **NO −1 compensation** / applied ⇒ owned reset, utterance closed, `_inserted_bytes −=
owned_bytes`; refused/unknown ⇒ state untouched, never retry. No explicit byte cap: the delete
carries only a count; verification (64 KiB snapshot) bounds it naturally — refuse when unverifiable.

## §3 Host/protocol cancel design

- `protocol.py`: `REQUEST_CMDS += "cancel"`; drop the reserved-error branch; `validate_request`:
  cancel requires `before` as int ≥ 0.
- `ime_host.py::_cancel`: mirror `_show` minus text — `delete_surrounding_text(before, 0)` +
  `commit_string("")` + `commit(dones)`; applied = dones increment within SHOW_CONFIRM_WAIT; same
  error posture. Chosen over omitting `commit_string` to stay closest to the lab-proven triple
  (R.2: delete+commit_string+commit corrected 1024 B byte-exactly). Open mechanism risk: the empty
  commit_string variant is NOT lab-proven — the optional GTK lab row verifies; one-line fallback
  (drop the commit_string request) if GTK misbehaves. Wire legality: a commit cycle may contain any
  combination of state requests ending in commit — https://wayland.app/protocols/input-method-unstable-v2#zwp_input_method_context_v2
  (the XML Hyprland vendors; wlwire sends it via the generic `request()`).

## §4 Test matrix

See PRP Implementation Tasks. Key pins: rejected-final never auto-erases (partial u1 applied, NO
finalize, show u2 ⇒ INSERT before=0); no −1 compensation (before == owned_bytes exactly); post-
finalize correction anchor (delete anchored at caret−owned_bytes, not binding caret); multi-
utterance `_inserted_bytes` (finalize does NOT reset bytes); leave clears binding + no field
writes; cancel accounting round-trip (cancel then fresh insert, recheck passes).

## §5 Fences

No takeover (T4); no daemon/ctl/feedback/manager/wlwire/bulk_controller/bulk_delivery edits; no
M6 scope (session recovery, voicectl session, G5 counting, recorder abort — "drops its buffered
audio" is the controller/daemon seam, already landed controller-side); no legacy backspace changes;
only `test_cancel_reserved` may be REPLACED (it pins the reservation this task lifts).

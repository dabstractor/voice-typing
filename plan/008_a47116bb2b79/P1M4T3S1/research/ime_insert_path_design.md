# P1.M4.T3.S1 — insert-path show() design (verified against the LIVE tree)

Evidence map for the PRP. All line numbers re-grepped 2026-11-22 against the live tree.

## 0. Task shape: the host half is LANDED; this task ships the DAEMON half

- Host insert machinery already exists (S1, `voice_typing/ime/ime_host.py:154-177`): `_show`
  executes on the host's own Wayland loop — `before>0` → one atomic replace
  (`delete_surrounding_text` + `commit_string` + `commit`), `before==0` → pure insert
  (`commit_string` + `commit(self.dones)`); result mapping: `refused` (not activated),
  `unknown` (wire exception OR confirm deadline `SHOW_CONFIRM_WAIT` elapsed without a `done`),
  `applied` (`self.dones > dones_before`, i.e. the compositor CONFIRMED — bytes-sent ≠ applied);
  `t_ms` reported. The `before` field rides the request as an EXTRA field (tolerated by design:
  `protocol.validate_request` only checks presence of SHOW_FIELDS).
- What is MISSING (this task): the daemon-side `DeliveryTarget.show()` — `bulk_controller.py`
  (landed, M3) calls `target.show(session, utterance, seq, expected_revision, span) ->
  ShowResult` and owns ordering/barriers/disarm; `ImeTarget` (T2.S1, in flight) ships only
  acquire/recheck/to_bytes_span. T3.S1 adds the INSERT path of show(): recheck-at-mutation →
  delta commit (`before=0`) → honest result mapping + zero-diff + the 4000 B cap + the 250 ms
  budget. T3.S2 owns the correction path (`before>0`); T3.S3 owns finalize/leave/cancel; T4 owns
  takeover; M6 wires the daemon.

## 1. Consumed contracts (verbatim anchors)

| surface | anchor | what T3.S1 consumes |
|---|---|---|
| JSONL protocol | `voice_typing/ime/protocol.py:37,40,79-93` | `REQUEST_CMDS` incl. `"show"`; `SHOW_FIELDS = (session, utterance, seq, expected_revision, text)` — validate_request REQUIRES all five on every show request; extra fields (e.g. `before`) tolerated |
| host show semantics | `ime_host.py:154-177` | insert = `commit_string(text)` + `commit(dones)`; reply `{result: applied\|refused\|unknown, t_ms}`; confirm = dones increment (receiver-side validation) |
| result taxonomy | `voice_typing/bulk_delivery.py:77-89` | `ShowResult`: APPLIED / UNCHANGED (render-equal ⇒ ZERO events) / REFUSED / UNKNOWN (never retried; bytes-sent ≠ applied) |
| DeliveryTarget protocol | `bulk_delivery.py:114-158` | `show(session, utterance, seq, expected_revision, span) -> ShowResult`; `span` = the COMPLETE rendered span |
| zero-diff guard | `bulk_delivery.py:220+` | `rendered_equal(old, new)` — spacing-normalization-only render equality; two strings that render identically ⇒ zero events |
| controller contract | `bulk_controller.py:44-45,442-445,617,664-721` | caller owns ordering/queue; `expected_revision` seeded from acquire, **+1 ONLY on APPLIED**; UNCHANGED = no advance; REFUSED/UNKNOWN ⇒ stop delivery, no retry — the adapter must never violate these by mutating on a non-applied result |
| acquire contract (T2.S1, in flight — treat as landed) | `P1M4T2S1/PRP.md` What §2 | `ImeTarget(proc)`, `FieldBinding(im_handle, cursor_bytes, anchor_bytes, pre_caret, revision)`, `recheck(binding, inserted_bytes) -> (ok, reason, rev)`, `binding_caret_after`, `to_bytes_span`; acquire/verify pass `timeout=2.5` |

## 2. Wire facts (R.2 lab evidence — do not re-derive)

- insert 26–40 ms cmd→visible-field on GTK4, exact cursor; ONE atomic commit corrects a 1024 B
  span byte-exactly; IM commits generate ZERO key events (delivery cannot self-trigger the T4
  takeover listener); GTK fires 1–2 internal `changed` signals per commit cycle (expected).
- `commit_string`/`commit` semantics per the vendored XML + S1 wlwire: serial on `commit` ties the
  commit to a `done` event; `dones` counter = the host's revision clock (T2.S1's acquire returns
  `revision=self.dones`).
- 4000 B cap: origin unresolved in research — **treat ≤4000 B/commit as the engineering rule**
  (item contract). Chunking without violating the one-edit rule is NOT achievable for a single
  show() (each commit = 1 visible edit; N chunks = N edits ⇒ violates the event-count law) ⇒
  the compliant T3.S1 behavior for a >4000 B delta is **REFUSED with a cap reason** (an honest,
  spec-sanctioned option in the item text; chunking decisions belong to the controller, not the
  adapter).

## 3. The insert-path algorithm (pinned)

Adapter state (per ImeTarget instance, created at acquire time by the caller): `_last_applied_span`
(str, `""` initially) + `_inserted_bytes` (cumulative UTF-8 bytes WE committed).

`show(session, utterance, seq, expected_revision, span) -> ShowResult`:
1. **Zero-diff first (no request):** `rendered_equal(self._last_applied_span, span)` ⇒ `UNCHANGED`
   (zero events; controller does not advance revision).
2. **Insert condition:** `span.startswith(self._last_applied_span)` on the ORIGINAL strings ⇒
   `delta = span[len(last):]`. NOT a pure extension ⇒ `REFUSED` (reason: correction path is
   T3.S2) — the insert-capable adapter never fakes a correction.
3. **Mutation-time re-check (R.5):** `recheck(binding, inserted_bytes=self._inserted_bytes)` —
   fresh verify; failure (no-reply/deactivated/no-snapshot/selection/caret-moved/adjacent-changed)
   ⇒ `REFUSED` with that reason; **NO show request sent** (test-pinned).
4. **Cap:** `len(delta.encode()) > 4000` ⇒ `REFUSED` (reason: 4000-byte commit cap).
5. **Request:** `proc.request("show", timeout=0.25, session=…, utterance=…, seq=…,
   expected_revision=…, text=delta, before=0)` — all SHOW_FIELDS present (validate_request
   demands them); `before=0` = pure insert.
6. **Result mapping:** reply `result=="applied"` ⇒ APPLIED (update `_last_applied_span=span`,
   `_inserted_bytes += len(delta.encode())`); `"refused"` ⇒ REFUSED; anything else / `None`
   (timeout/death) ⇒ UNKNOWN — never retried, state NOT advanced (controller disarms).
7. Order matters: state advances ONLY on APPLIED; a REFUSED/UNKNOWN leaves `_last_applied_span`
   untouched so the disarm path (controller) sees the last confirmed truth.

## 4. Deadline budget (250 ms engineering deadline, receiver-side validation)

- Daemon side: the show `request` timeout = **0.25 s** (fits inside the controller's landed
  250 ms failure deadline; M3.T2.S2 owns the controller-side enforcement — the adapter just must
  not exceed it).
- Receiver side: the host's confirm wait `SHOW_CONFIRM_WAIT` (ime_host.py, value set by S1) must
  be ≤ ~0.22 s so the host's applied/unknown verdict lands before the daemon's 0.25 s give-up.
  Preflight greps the value; if > 0.22 the task lowers it (one-constant change, disjoint from
  T2.S1's edits which touch only `_acquire`/`_verify`/`_SNAPSHOT_HEAD_BYTES`/`_SURROUND_WAIT_S`).
- The mutation itself happens synchronously at commit-send inside `_dispatch` — a daemon-side
  timeout NEVER cancels a commit already sent; hence "unknown ⇒ disarm, never retry" (R.5).

## 5. Test strategy (fake-proc, no compositor; pattern = T2.S1's `_FakeProc`)

APPEND to `tests/test_ime_target.py` (T2.S1 creates it): the fake records `(cmd, timeout,
fields)` and scripts replies — ~13 cases: zero-diff exact / render-equal; pure extension →
request with `before=0` + all SHOW_FIELDS + `timeout<=0.25` asserted + delta-only text; second
extension after APPLIED (delta = new part only; recheck called with CUMULATIVE inserted_bytes);
reply unknown → UNKNOWN; reply refused → REFUSED; `None` → UNKNOWN (no retry); recheck caret-moved
→ REFUSED and NO show request; recheck selection → REFUSED; >4000 B delta → REFUSED (no request);
non-extension → REFUSED correction-not-implemented (no request); Unicode/astral delta byte
accounting (1 astral char = 4 bytes into _inserted_bytes); reply missing `result` → UNKNOWN;
state NOT advanced on non-applied (subsequent show after refused recheck still compares against
the last APPLIED span). Plus: L3 fake-duplex smoke + L4 scope guards (git status; protocol.py /
wlwire.py / bulk_controller.py / bulk_delivery.py / daemon/feedback/ctl / tools/im-lab untouched;
manager not imported). Optional env-gated GTK insert row in `tests/ime_show_lab.py`
(`IME_SHOW_LAB=1`, private seat, pattern from `tools/im-lab/imlab_run.py` + T2.S1's
`tests/ime_acquire_lab.py`): acquire → 3 inserts → assert field text == concatenation + caret at
end + edit-count grew by ≤ #inserts + zero grab keys. Never auto-collected (no `test_` prefix).

## 6. Fences

No correction-path implementation (`before>0` stays T3.S2 — the adapter REFUSES corrections,
it does not send them); no finalize/leave/cancel semantics (T3.S3 — `_leave`/host leave untouched);
no takeover/T4; no manager/controller/daemon/feedback/ctl/config edits (M6 owns wiring); no
protocol.py/wlwire.py/tools-im-lab changes; `map_span`/rendered_equal consumed, not duplicated.
Byte arithmetic ONLY via `.encode("utf-8")` on ORIGINAL strings (T2.S1 Critical #1).

# Research — P1.M4.T2.S1: acquire() — field binding, verification, units mapping

Design + verification record for the IM-route verified acquire. The PRP pins the full design; this doc
records the consumed contracts (verbatim surfaces), the wire facts that shape the design, the
host/daemon split rationale, and the test strategy.

---

## 1. Consumed contracts (verbatim surfaces, verified at research time)

### S1 transport — LANDED (`voice_typing/ime/`, tests green)
- `protocol.py`: `REQUEST_CMDS = ("acquire","show","verify","leave","ping")` (+ reserved `cancel`),
  `SHOW_RESULTS = ("applied","unchanged","refused","unknown")`, `make_reply(id, cmd, **fields)`
  (extra reply fields TOLERATED — replies are open dicts), `ProtocolError`, `encode/decode`.
- `ime_host.py` (the file this task EVOLVES — S1's own docstring: "acquire's handle/revision is a
  placeholder passthrough; show does no ownership/units verification (T2)"):
  - `ImeHost(client, out, log_path=None)`; state `activated` (bool), `dones` (int, bumps on each
    compositor `done` event), `surround` (`{"text": str, "cursor": int, "anchor": int} | None`,
    cached from `surrounding_text` events at ime_host.py:92-95), `grab`/`grab_keys`.
  - `_acquire(rid)` (ime_host.py:146-152) — TODAY: not-activated → `ok=False reason="not activated"`;
    else `ok=True, handle=str(self.im), revision=self.dones` — NO field verification (the placeholder
    this task replaces).
  - `_verify(rid)` (ime_host.py:179-183) — TODAY: replies `text_head=head[:80], cursor, anchor`
    (head-truncated for the counts-discipline LOG; the REPLY needs the fuller snapshot this task adds).
  - `_drain_events()` — non-blocking event pump; forwards `surrounding_text`/`done`/etc. as id-less
    `{"ev":...}` lines AND caches `self.surround`.
  - serve loop: `for line in stdin:` → `handle_line` → ONE id-echoing reply per request; survives bad rows.
- Fences: `protocol.py` / `wlwire.py` stay UNTOUCHED this task; `tools/im-lab/` stays byte-identical.

### S2 supervisor — IN FLIGHT (treat as contract; NOT landed at research time)
`voice_typing/ime/manager.py` `ImeProcess`: `request(cmd, timeout=1.0, **fields) -> dict | None`
(None on timeout/dead child; NO resend), `on_event`/`on_delivery_state` callbacks, `stop()`,
`healthy()`, states idle/starting/running/unsupported/fault. **This task duck-types `proc`**
(`.request(cmd, timeout=..., **fields)`) — target.py must NOT import manager (parallel-safe; tests
inject fakes). NOTE: acquire needs a LONGER request timeout than S2's 1.0 s default because the host
briefly waits for a snapshot (§3) — the adapter passes `timeout=2.5`.

### bulk_delivery contracts — LANDED (READ-ONLY)
- `AcquireResult(ok, handle, revision, reason)` — frozen dataclass; `revision: int = 0`,
  `reason: str = ""`. Docstring: "Fail BEFORE delivery for non-editable / password-secret / selected /
  unidentified".
- `ShowResult` (applied/unchanged/refused/unknown); `DeliveryTarget` Protocol (acquire/show/finalize/
  leave/cancel) — T3 completes show/finalize/cancel/leave; THIS task ships acquire + the re-check
  helpers T3 consumes.
- `TargetUnits.UTF8_BYTES` + `map_span(text, start_char, end_char, units)` — counts on the ORIGINAL
  string only ("never a lowercased/normalized copy"); UTF-8 offsets are cumulative byte lengths;
  raises ValueError on malformed spans. `rendered_equal` (zero-diff guard) — T3's concern.

---

## 2. Wire facts that shape the design (R.2 evidence; do not re-derive)

- **`surrounding_text(text, cursor, anchor)` carries UTF-8 BYTE offsets** (per the vendored
  input-method-unstable-v2.xml: cursor/anchor are `uint` byte positions into the UTF-8 `string`).
  GTK4 pushes it byte-exactly up to 1024 B, 14+ events during a session → **the units for this
  adapter are `TargetUnits.UTF8_BYTES`, fixed**. `delete_surrounding_text(before, after)` also takes
  BYTE counts — char→byte conversion MUST go through `map_span(..., UTF8_BYTES)` on the original str.
- **The IM cannot REQUEST surrounding_text — the text-input side pushes it** (at enable and after
  edits). Hence acquire = "use the host's cached snapshot, briefly waiting/draining for one if the
  activation just happened". foot/kitty NEVER send it → acquire MUST refuse them ("no surrounding
  text — cannot be ownership-verified") — that is CORRECT, not a bug: unverified fields are exactly
  R.3's "fail BEFORE delivery for unidentified fields"; the insert-only class is served by OTHER
  adapters (pi seam / clipboard fallback, M5), never by weakening this one.
- **Selection = cursor != anchor** in the snapshot → a pre-existing user selection → REFUSE ("never
  replace a pre-existing user selection by default" — R.3).
- **`done` events bump the host's `dones` counter** — the natural revision token (each commit the
  compositor applies increments it). revision at acquire = dones; show (T3) carries
  `expected_revision` re-checked at mutation time.
- **A commit the field applies pushes a FRESH surrounding_text** — so after T3's inserts, the
  mutation-time verify pull sees our own text; the re-check helper accounts for that via
  `inserted_bytes` (the caller's bookkeeping of bytes WE typed since acquire).
- **`commit_string` generates ZERO key events** (lab-proven) — our own commits cannot self-trigger
  takeover; irrelevant to acquire but it is why ownership bookkeeping (not key accounting) is the
  verification basis.

---

## 3. The host/daemon split (why each piece lives where it does)

| Piece | Where | Why |
|---|---|---|
| snapshot wait/drain (bounded poll of `self.surround` via `_drain_events`, ≤1.0 s) | HOST `_acquire` | only the host sees wire events; the poll must pump `_drain_events` to let the snapshot arrive |
| snapshot delivery in the acquire/verify REPLIES (full bounded text + cursor + anchor) | HOST | the daemon cannot see events except via `on_event`; replies are the pull-based, id-correlated channel (replies tolerate extra fields — S1 protocol) |
| SELECTION / consistency / binding / units / re-check SEMANTICS | DAEMON `target.py` | the TargetAdapter (R.3) is daemon-side by design; unit-testable with a fake proc; the host stays transport-level |
| revision = dones; handle = frozen binding dataclass | DAEMON | AcquireResult.handle is "adapter-defined"; the binding must carry pre-caret context for mutation-time ownership checks |

Snapshot head cap: `_SNAPSHOT_HEAD_BYTES = 64 KiB` (generous vs the protocol's ~4 KiB practical cap;
if cursor/anchor exceed the sent text's byte length the daemon refuses "snapshot truncated" — a
byte-cut that splits a UTF-8 char or drops the cursor is worse than refusing). Event LOG lines keep
the existing `:80` head truncation (counts discipline — untouched).

---

## 4. The re-check helpers (consumed by show() in T3 — pinned contract)

`recheck(binding, inserted_bytes=0) -> tuple[bool, str, int]` — (ok, reason, current_revision), ONE
fresh `verify` pull, then in order:
1. reply None → `(False, "ime no reply", 0)`
2. not activated → `(False, "ime deactivated", 0)`
3. no snapshot → `(False, "no surrounding text", 0)`
4. `cursor != anchor` → `(False, "user selection present", 0)`
5. `cursor != binding.cursor_bytes + inserted_bytes` → `(False, "caret moved", rev)`
6. fresh `text_bytes[:expected_caret]` does not end with `binding.pre_caret_bytes` →
   `(False, "adjacent text changed", rev)`
7. else `(True, "", current_revision)`
Rules: post-caret text changes do NOT revoke (only the act of typing is T4's takeover signal — key
events); the helper NEVER mutates; expected caret is OUR accounting (acquire caret + bytes we typed).
Also `binding_caret_after(binding, inserted_bytes)` and a thin `to_bytes_span(text, sc, ec)` wrapper
over `map_span(..., UTF8_BYTES)` so T3 never hand-rolls offsets.

## 5. Test strategy (the contract: "the fake wire and the GTK harness field")

1. **Fake-proc unit suite** (`tests/test_ime_target.py`, NEW, the required gate): a `_FakeProc`
   recording requests + scripted replies — happy path; no-reply; not-activated propagation;
   no-surrounding propagation; **selection refusal**; inconsistent snapshot (cursor > byte len);
   truncated snapshot; Unicode/astral byte-offset correctness (pre-caret bytes, map_span round-trip);
   every recheck branch (6 + happy); acquire request carries `timeout=2.5` (asserted).
2. **Fake-wire host tests** (APPEND to `tests/test_ime_host.py`): activated + cached snapshot →
   ok=True WITH text/cursor/anchor fields; activated + NO snapshot → ok=False "no surrounding
   text"; snapshot arrives LATE via drain → ok=True; verify reply carries the full bounded text;
   existing host tests UNCHANGED.
3. **GTK harness evidence row** (`tests/ime_acquire_lab.py` — a NON-collected driver; name lacks
   `test_` so pytest ignores it): the disposable-desktop pattern from `tools/im-lab/imlab_run.py`
   (xvfb-run + dbus-run-session + sway, private seat), field_gtk as the target, OUR ime_host over
   pipes (S2-style Popen), rows: (R1) seed one character via the lab's synthetic-key mechanism →
   acquire → ok with byte-exact pre-caret; (R2) Ctrl+A selection → acquire → REFUSED "user selection
   present"; (R3 optional, foot/kitty) no surrounding_text → REFUSED. Prints one verdict line per
   row; bounded (`timeout 300`); NEVER the live desktop; never auto-run by pytest (env-gated
   `IME_ACQUIRE_LAB=1`). The unit suites remain THE gate; this row is the mechanism evidence
   (a passing probe never flips acceptance — R.2).

## 6. Fences

- NO show/finalize/cancel/leave SEMANTICS (T3.S1/S2/S3); NO takeover policy (T4 — but the re-check
  helpers ARE the mutation-time half of R.5 takeover that T3/T4 consume); NO pi seam / clipboard
  (M5); NO daemon/feedback/ctl/bulk_* edits (M6 wiring); NO config/pyproject/systemd/hypr-binds
  changes; `protocol.py`/`wlwire.py`/`tools/im-lab/` byte-identical; NO manager import (duck-typed
  proc — S2 lands in parallel).
- Password/secret detection: IM-v2 exposes NO signal for it — DOCUMENTED LIMITATION (module
  docstring), not a fake heuristic. R.3's password rule is enforced where a signal exists (other
  adapters).

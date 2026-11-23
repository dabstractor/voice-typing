# Research Note — P1.M1.T2.S2: 6 ms press→release contact gap on the ydotoold socket path

## 1. Sequencing: S1's merge must land FIRST (gate)

`tests/test_ydotoold_client.py` does NOT exist on main (verified) — it arrives whole with S1's merge of
`fix/ydotoold-datagram` (commit 33321c6). The branch's ONLY client change is `_connect` SOCK_STREAM→
SOCK_DGRAM (main bug site :41) — everything else in `ydotoold_client.py` is byte-identical to main, so
the line-verified bodies below hold post-merge (line numbers shift only if the docstring edit moves them).
Gate: `test -f tests/test_ydotoold_client.py && grep -q SOCK_DGRAM voice_typing/ydotoold_client.py`.

## 2. The verified edit sites (main's file ≡ branch's file except :41)

- `_CHAR_GAP_S = 0.012` @25 ("Rev 3d: 12 ms/char — same pace as the text path") — the new constant goes
  beside it.
- `press_backspace(n)` @63-71 — the ONLY `_key` pair site:
  ```python
  for i in range(n):
      if i:
          time.sleep(_CHAR_GAP_S)      # inter-char (release→next press)
      self._key(_BACKSPACE, 1)         # press
      self._key(_BACKSPACE, 0)         # release — BACK-TO-BACK with the press (the gap to fix)
  ```
- `_key(code, value)` @51 sends ONE 24-byte `<6I` datagram (16 zero bytes + ev_type/keycode + value).
  The contact gap belongs in `press_backspace` between the two `_key` calls (NOT inside `_key`).
- CLI fallback for reference (`typing_backends.py:145-149`): `ydotool key -d 6` + `["14:1","14:0"]*n`
  — the CLI gaps EVERY event 6 ms (6 contact + 6 inter = 12 ms/char). The PRD §8 triage finding:
  "CLI gaps every event; socket path currently does not."
- Uses bare `time.sleep` (no injectable clock) — tests measure wall-clock with slack, per the existing
  style.

## 3. The end-state pacing (per the contract: add 6 ms contact, KEEP 12 ms inter-char)

press → **6 ms** (`_CONTACT_GAP_S`) → release → **12 ms** (`_CHAR_GAP_S`) → next press …
Per-char cycle 12→**18 ms**; `press_backspace(3)` sleeps 6+2×18 = **42 ms** (was 24 ms).

**Existing latency test stays green unchanged** (verified verbatim from the branch):
`test_press_backspace_3_latency_under_100ms` — asserts `dt < 0.100` (42 ms ✓) and the pacing-sanity
lower bound `dt >= 2*_CHAR_GAP_S - 0.002` (42 ≥ 22.8 ✓). Only its comment ("2 inter-char gaps") is now
incomplete — optionally refresh; the precise spacing belongs in the NEW test.

**Stale 12 ms/char comments to align (Mode A, ride-along):** `_CHAR_GAP_S`'s own comment ("12 ms/char"),
`typing_backends.py:147` ("persistent socket, 12 ms/char (3e)"). The CLI comment's own math
("-d 6 = 6ms/event, 2 events/char = 12ms/char") stays true. PRD §8's aspirational "~80 chars < 150 ms"
is already violated at 12 ms/char and at 18 (1.44 s) — NOT this task's concern (note only).

## 4. The test seam (verified from the branch's new test file)

- `FakeYdotoold` (threading AF_UNIX **SOCK_DGRAM** server): `self.datagrams: list[(bytes, src)]`
  appended in `_serve`; **NO timestamps recorded** — per-event spacing assertions need a small ADDITIVE
  extension: `self.times: list[float]` appended in `_serve` (`time.monotonic()` per datagram).
  `datagrams`'s shape is unchanged (existing tests + `.payloads` untouched).
- `wait_for(n)` blocks bounded until n datagrams recorded; `_decode_event(data)` unpacks the 24-byte
  message into {zeros, code, ev_type, value}.
- Datagram order for `press_backspace(3)` = **12 datagrams**: key-event, sync, key-event, sync …
  (the "interleaving_event_then_sync" test) — 6 KEY events (press,release ×3). The new test decodes
  payloads, filters `ev_type == EV_KEY`, and asserts arrival-time deltas. AF_UNIX datagram latency is
  µs-scale, so arrival deltas track send deltas; use the file's existing slack style (−0.002).
- Fixtures: `fake_daemon(tmp_path)` (bound BEFORE client construction — never touches the REAL
  /run/ydotoold.socket), `client(fake_daemon)` → `YdotoolClient(socket_path=fake_daemon.path)`.
- Module docstring of the client documents the wire protocol + "exactly what `ydotool key -d 6 …`
  writes" — the Mode A gap note extends this (contact time = what real apps need to register a press;
  PRD §8 protocol finding; CLI parity).

## 5. Sibling boundaries

- S1 (merge): lands the client + test file; my task edits the SAME two files AFTER the merge (Task 0
  gate). No overlap in flight (S1 makes no edits — the content arrives whole from the branch).
- S3 (journal-noise guard): guards the Errno-91 CLI fallback storm in typing_backends — different seam;
  my only typing_backends touch is the stale "12 ms/char" comment at :147.
- The 18 ms/char pace is a deliberate contract value ("keeping the 12 ms inter-char gap") — do NOT
  rebalance to 6+6 (CLI parity of the TOTAL was considered; the contract fixes 6 contact + 12 inter).

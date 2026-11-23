# Research: D3.2 — sustained-Backspace hold trace (VERIFIED, probe-passed)

**Status:** Every claim below verified against the live tree; the full test scenario was executed as a
throwaway probe (no files written) and PASSED end-to-end. Source: `key_listener.py`, `daemon.py`,
`tests/test_key_listener.py`, `tests/test_daemon.py` (cancel suite), `d3_defects_g1_baseline.md` PART C.

## 1. The mechanism (baseline Part C, line-verified)

- **Filter:** `key_listener.py:81` — `if ev_type != ecodes.EV_KEY or value != 1: return None`. Press=1
  routes; release=0 and **autorepeat=2 drop** — a held Backspace is invisible to the daemon BY DESIGN.
- **Wiring:** daemon.py:799-805 — `KeyListener(cancel_cb=self._on_cancel_backspace,
  other_key_cb=self._on_user_keypress, is_active=lambda: self._listening.is_set())`.
  `_on_cancel_backspace` gates on `_listening` → `self.cancel()`.
- **Compensation:** daemon.py:1779 `n = max(tail_len - 1, 0)` → `self._backend.press_backspace(n)`
  (ONE batched paced burst; the merged D3.1 socket path ≈12 ms/char; PRD budget ~80 chars <150 ms).
- **Suppression window:** latch `_cancel_suppress_final = True` + stamp
  `_cancel_suppress_since = time.monotonic()` (daemon.py:1788-1791) — "refreshed per press"
  (**a separate press re-stamps; repeats never reach here**). Guarded by
  `if self._text_in_flight.is_set() and self._host is not None:` → then `host.cancel()`.
- **Residual defect (the audit finding):** during the hold the OS autorepeat deletes REAL on-screen
  chars the daemon cannot observe. Repeats landing **while the paced burst runs** interleave with it:
  total deleted = `n + 1 + R` vs `n + 1` believed → **belief-desync of R chars** (PRD §8 known defect).
  Repeats after the burst eat committed/user text — accounting already zeroed, plain user edits,
  uncompensable by design.

## 2. Existing coverage gap (grep-verified, baseline Part C)

- `test_key_listener.py:61-65 test_autorepeat_ignored` — PARSE level only (value 2 → None).
- `test_key_listener.py:218-228 test_repeated_backspace_presses_route_one_cancel_each` — PUMP level
  with spy callbacks, **no daemon, no tail, no compensation, no window**.
- `test_daemon.py:4467+` cancel suite (`_make_cancel_daemon` + `_FakeStream(tail_len=8)`) — pins the
  compensation arithmetic but calls `d.cancel()` DIRECTLY; **no hold event trace**.
- `test_streaming.py::test_e_cancel` — engine/T8 level. **NO test anywhere replays
  press(1)+repeats(2)×R+release(0) through the daemon's real wired seams with a tail in flight.**

## 3. The probe (executed, PASSED — the exact test body to transcribe)

Harness: `tkl._wire_daemon()` (real daemon ctor, `_WireBackend` recording, default config → `d._key_listener`
wired). Setup: local `_HoldStream` (`pending_tail_len()->8`, `reset_after_cancel()` zeroes + counts) +
`_HoldHost` (`cancel()` counts); `d._stream=…; d._host=…; d._listening.set(); d._text_in_flight.set()`.
Sequence (`R=6`): `[BS_PRESS] + [BS_REPEAT]*6 + [BS_RELEASE, SYN]` pumped via
`_pump_events(..., cancel_cb=kl.cancel_cb, other_key_cb=kl.other_key_cb, is_active=kl._is_active)`
(the daemon's REAL wired callbacks — no monkeypatching).

**Probe output / assertions (all passed):**
```
backend calls: [('bs', 7)]     host cancels: 1 | suppress latched: True | stamp: 20807.23…
stream resets: 1 | tail now: 0
```
- `be.calls == [("bs", 7)]` — exactly ONE compensation (n=8−1); repeats + release produced NOTHING.
- `d._host.cancel_calls == 1`; `d._cancel_suppress_final is True`; `d._cancel_suppress_since` not None.
- **Re-stamp pin:** pump a SECOND pure-repeat burst `[BS_REPEAT]*6` →
  `d._cancel_suppress_since == stamp1` (bit-identical), host still 1, backend unchanged.
  (A re-fired cancel WOULD re-stamp — `time.monotonic()` differs — and would re-call `host.cancel()`
  since `_text_in_flight` stays set; both detectors are strong.)
- `cancel()`'s trailing `status_snapshot()` works with `_WireFeedback` (probe ran clean — no raise).
- Event tuples `_BS_PRESS/_BS_REPEAT/_BS_RELEASE/_SYN` already exist at test_key_listener.py:190-193.

## 4. The audit note (Mode A — goes in the test docstring; consumed by S2)

RESIDUAL UNOBSERVABLE-DELETION WINDOW: the daemon sees only the press; the OS repeats are dropped at
key_listener.py:81. Repeats landing while the paced `press_backspace(n)` burst runs interleave with it:
total deleted = n+1+R vs n+1 believed → belief-desync. **Bound:** R ≈ repeat_rate × burst_duration —
at a typical Linux autorepeat (~30 cps after ~500 ms delay) and the ≤150 ms burst (80 chars ≈ 12 ms/char
on the D3.1 socket path), R ≤ ~4–5 chars worst case during the burst; repeats after the burst delete
committed/user text (accounting already zeroed — plain user edits, uncompensable by design). Mitigation
or acceptance is S2's (P1.M1.T3.S2) decision; this test pins the CURRENT contract (one cancel, no
re-stamp) so any future change is a deliberate, visible red.

## 5. Scope

- ONE file edited: `tests/test_key_listener.py` (new banner section at END + local `_HoldStream`/
  `_HoldHost` doubles). NO source change — the current behavior is CORRECT per design; this task pins it
  + documents the residual window.
- Parallel P1.M1.T2.S3 edits `tests/test_typing_backends.py` — DISJOINT.
- Verify: `timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q` green + the daemon
  cancel suite `-k cancel` green (no regression) + no source diff.

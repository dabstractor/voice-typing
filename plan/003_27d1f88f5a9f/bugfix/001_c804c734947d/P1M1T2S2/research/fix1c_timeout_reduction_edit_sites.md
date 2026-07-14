# Research Note — P1.M1.T2.S2: Reduce `_bounded_shutdown` default timeout 10s → 5s (Fix 1C)

**Task type:** surgical 1-parameter change + budget-math docstring/comment alignment. Fix 1C of bugfix
Issue 1 (the third of three measures: 1A=RecorderHost._stop_lock [Complete], 1B=daemon single-flight
[P1.M1.T2.S1, parallel], **1C=this task**). 0.5-point scope.

## 1. The exact change (daemon.py) — navigate by SIGNATURE, not line number

The parallel S1 task is concurrently editing daemon.py, so line numbers are MOVING. Verified current
locations (will be stale by arrival): `_bounded_shutdown` @1294; its signature `def _bounded_shutdown
(self, timeout: float = 10.0) -> None:`. **Navigate by `def _bounded_shutdown(self, timeout`**.

EDIT 1 — signature default (the core):
```python
# FROM:  def _bounded_shutdown(self, timeout: float = 10.0) -> None:
# TO:    def _bounded_shutdown(self, timeout: float = 5.0) -> None:
```

EDIT 2 — add budget-math paragraph to `_bounded_shutdown`'s docstring (the canonical place for it):
```
Budget (bugfix Issue 1 / Fix 1C, P1.M1.T2.S2): host.stop(timeout=5) → proc.join(5) + killpg +
join(2) ≈ 7s max per call; plus ControlServer.stop() join(2) ≈ 2s. With daemon single-flight
(P1.M1.T2.S1: exactly ONE teardown runs on the SIGTERM path) the total is ≤ ~9s — comfortable
headroom under systemd TimeoutStopSec=15. The default was 10.0 (→ ~12s/call, ~14s total, no margin).
```

## 2. contract vs bug_analysis reconciliation (load-bearing)

bug_analysis.md Fix 1C says: "Update `request_shutdown()` to call `_bounded_shutdown(timeout=5.0)`."
The ITEM CONTRACT instead says "Change the DEFAULT parameter." The contract is AUTHORITATIVE:
changing the default covers BOTH `request_shutdown()` and `shutdown()` (both call `self._bounded_
shutdown()` with no arg) in ONE edit, with less churn. Do NOT add an explicit `timeout=5.0` to
`request_shutdown()`/`shutdown()` — let them use the new default. (`_unload_host()` already calls
`_bounded_shutdown(timeout=5.0)` explicitly → now redundant-but-harmless (explicit == default); LEAVE
it, don't churn.)

## 3. Call sites (all verified) — which use the default vs explicit

| caller | call | after change |
|---|---|---|
| `request_shutdown()` (@~1194) | `self._bounded_shutdown()` | default → 5.0 ✓ (no edit) |
| `shutdown()` (@~1368) | `self._bounded_shutdown()` | default → 5.0 ✓ (no edit) |
| `_unload_host()` (@~1003) | `self._bounded_shutdown(timeout=5.0)` | explicit 5.0 == new default; redundant, harmless, LEAVE |

So the ONLY daemon.py behavioral edit is the signature default. The two default-using callers pick up
5.0 automatically.

## 4. The S1 composition (why 5s, not something else) — the ~9s target

- Fix 1A (Complete): `RecorderHost._stop_lock` — two concurrent `host.stop()` share ONE teardown.
- Fix 1B (P1.M1.T2.S1, parallel): `request_shutdown` claims `_shutdown_done` + signals `_teardown_done`;
  `shutdown()` WAITS (bounded `_TEARDOWN_WAIT_TIMEOUT=8.0`) instead of a 2nd teardown.
- **Fix 1C (this task): default 10→5.** S1's `_TEARDOWN_WAIT_TIMEOUT=8.0` was sized ASSUMING 1C's ~7s
  teardown lands (8.0 > 7.0 with margin). Without 1C, a single teardown is ~12s (10+2) > 8.0s wait →
  `shutdown()` would fall back to its own teardown on every SIGTERM (still safe via 1A's _stop_lock, but
  not the clean path, and wall-time ~12s+2s). WITH 1C: ~7s teardown signals `_teardown_done` well
  inside the 8.0s wait → `shutdown()` returns clean → total ~7s + server.stop() ~2s = **~9s** < 15s. ✓

⇒ 1C is REQUIRED for the contract OUTPUT's ~9s wall-time target. 1B alone fixes the double-teardown
BUG; 1C tightens the budget so the clean path fits.

## 5. Stale "10s" reference inventory (align for accuracy — none break the suite)

| location | text | action |
|---|---|---|
| `voice_typing/daemon.py` `shutdown()` docstring | "under a hard timeout (default 10s)" | → "(default 5s)" (disjoint sentence from S1's IDEMPOTENT-paragraph edit) |
| `systemd/voice-typing.service` ~L44-48 | "_bounded_shutdown(timeout=10) … ~10s … 15s budget = 10s bound + 5s grace" | → 5s math (Mode A — the contract-required doc) |
| `tests/test_daemon.py:1472` | `lambda timeout=10.0: …` + `assert calls == [10.0]` | → `5.0` / `[5.0]` (lambda's OWN default; suite green either way; align for faithfulness) |
| `tests/test_systemd_unit.py:97` (docstring) | "_bounded_shutdown(timeout=10) … ~10s … 10s bound + 5s grace" | → 5s math (comment only; asserts TimeoutStopSec=15, unchanged) |
| `tests/test_idle_and_gpu.sh:40` (comment) | "≤10s _bounded_shutdown teardown" | → "≤7s" (auto-unload ceiling comment; optional) |

**No test ASSERTS on the real 10s default** — the only `10.0` in a test is the lambda's own default
(test_daemon.py:1472), which is independent of the real method default. The contract's "verify no test
asserts on the 10s default" → CONFIRMED (suite green pre- and post-change). The updates above are
faithfulness/accuracy, not breakage fixes.

## 6. Parallel-execution conflict analysis (S1 ↔ S2)

Both edit daemon.py + test_daemon.py, at DISJOINT locations:
- daemon.py: S1 = `__init__` (+_teardown_done), `request_shutdown` (claim+signal), `shutdown` (wait
  branch + IDEMPOTENT docstring paragraph), +`_TEARDOWN_WAIT_TIMEOUT`. S2 = `_bounded_shutdown`
  SIGNATURE + its docstring (budget math), + the "(default 10s)" sentence in shutdown()'s docstring.
  → The ONE shared surface is shutdown()'s docstring, but S1 edits the IDEMPOTENT paragraph while S2
  edits the "(default 10s)" phrase — DISJOINT sentences; text-based edits compose cleanly.
- test_daemon.py: S1 adds 6 coordination tests (~after L1095); S2 edits the lambda at ~L1472 — far
  apart, no line conflict.
- systemd/voice-typing.service, test_systemd_unit.py, test_idle_and_gpu.sh: S2-ONLY (S1 doesn't touch).

No line-level merge conflict expected. The true dependency is semantic: S1's `_TEARDOWN_WAIT_TIMEOUT=8.0`
presupposes 1C's 5s default for the clean path (1B+1C compose to ~9s).

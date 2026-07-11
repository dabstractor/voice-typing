# Research — TTL cache for mic probe (P1.M2.T2.S1 / bugfix Issue 3)

This note pins the defect, the exact edit sites, the **sentinel-collision footgun**
the item's own example trips on, the **full set of tests that break** (more than
the item flagged), and the deterministic test strategy. The PRP (../PRP.md)
references it as the single source of truth.

## 1. The defect (bugfix Issue 3, PRD §4.2)

`_arm()` (daemon.py:575-581) calls `_refresh_mic_status()` on EVERY arm.
`_refresh_mic_status()` (633-648) → production prober `_probe_mic()` (650-672)
does `import pyaudio; pa = pyaudio.PyAudio(); <enumerate all devices>;
pa.terminate()` — measured ~39-43 ms per arm, and it runs WHILE HOLDING
`self._lock` (start/toggle take the lock → _arm). Single-user: imperceptible
(~40 ms). The cost is paid on every keystroke that arms the mic. Fix: TTL-cache
the probe result (re-probe at most once every 30 s).

## 2. Verified call graph + lock-site audit (scout_mic_probe.md)

- `_arm()` (575-581) → `_refresh_mic_status()` (581, no force today).
- `__init__` (453-456) → `_refresh_mic_status()` (456).
- `_refresh_mic_status` (633-648) is the SINGLE writer of `_mic_ok`/`_mic_error`
  and the SINGLE sanctioned caller of the probe.
- `_probe_mic` (650-672) is the raw probe (NOT TTL-gated; tests call it directly).
- Lock holders: `start()`→`_arm()` under `self._lock` (675-676);
  `stop()`→`_disarm()` (680-681); `toggle()` both branches (684-687);
  `_maybe_auto_stop()`→`_disarm()` (610-619); `__init__` single-threaded.
  **Conclusion (scout): `_mic_probe_at`/`_mic_ok`/`_mic_error` are read/written
  ONLY under `self._lock` or in `__init__` → NO extra locking needed.**
- `import time` is already at daemon.py:76. `time.monotonic` is used in 9+ places.
- Existing TTL/window analog: `MicRetryRateLimitFilter` (1080-1127), esp.
  `_last_seen = 0.0  # 0.0 == never` (1111) and `now - self._last_seen >=
  dedup_seconds` (1123). The new code mirrors this convention.

## 3. Exact edit sites in `voice_typing/daemon.py` (verified line numbers)

### 3.1 Module constant — insert after `_PARTIAL_CALLBACK_ATTR` (line 114)
```
114: _PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"
115: (blank)
116: (blank)
117: def _resolve_device_config(cfg: VoiceTypingConfig) -> dict[str, str]:
```
Insert `_MIC_PROBE_TTL_S: float = 30.0` (with a 3-line comment) between line 114
and `def _resolve_device_config`. Anchor oldText = the
`_PARTIAL_CALLBACK_ATTR = ...` line + 2 blanks + `def _resolve_device_config...`
line (unique).

### 3.2 `__init__` mic-probe block (current lines 453-456)
```
453:     self._mic_ok: bool = True            # default True: never-probed != broken (PRD §4.4 spirit)
454:     self._mic_error: str | None = None
455:     self._mic_prober = mic_prober
456:     self._refresh_mic_status()
```
Add `self._mic_probe_at: float = 0.0` after line 455 (with comment), and change
line 456 → `self._refresh_mic_status(force=True)` (construction always probes).

### 3.3 `_refresh_mic_status` (current lines 633-648) — signature + TTL gate + stamp + docstring
```
633: def _refresh_mic_status(self) -> None:
634-640:     """...docstring..."""
641:     prober = self._probe_mic if self._mic_prober is None else self._mic_prober
642:     try:
643:         ok, error = prober()
644:     except Exception as exc:
645:         ok, error = False, str(exc)
646:     self._mic_ok = bool(ok)
647:     self._mic_error = error
```
Changes: signature → `def _refresh_mic_status(self, *, force: bool = False) -> None`;
add the TTL gate at the TOP of the body (item verbatim):
`if not force and self._mic_probe_at != 0.0 and (time.monotonic() -
self._mic_probe_at) < _MIC_PROBE_TTL_S: return`; stamp
`self._mic_probe_at = time.monotonic()` AFTER line 647; extend the docstring.

### 3.4 `_arm` inline comment (line 581) — minor doc update
```
581:     self._refresh_mic_status()  # bugfix Issue 2 / P1.M1.T2.S1: re-probe mic health on each arm
```
Update the trailing comment to note TTL caching. The CALL stays
`self._refresh_mic_status()` (no force) — _arm respects the TTL.

### 3.5 NO other callers
grep `_refresh_mic_status` over daemon.py → only 456 (init), 581 (_arm), 633
(def). status_snapshot (714-733) only READS `_mic_ok`/`_mic_error` — it does
NOT call _refresh_mic_status, so it is unaffected.

## 4. ★ CRITICAL FOOTGUN: the `0.0 == never` sentinel vs frozen-clock=0.0 ★

The item prescribes the gate `if not force and self._mic_probe_at != 0.0 and
(time.monotonic() - self._mic_probe_at) < _MIC_PROBE_TTL_S: return` with the
sentinel `0.0 == never` (matching MicRetryRateLimitFilter). This is CORRECT in
production: `time.monotonic()` is system-uptime-scaled and never 0.0, so a real
probe never stamps `_mic_probe_at = 0.0`.

BUT the item's example test freezes the clock to `t=0.0` at construction. With
the gate above, `__init__`'s `force=True` probe stamps `_mic_probe_at =
time.monotonic() = 0.0` — which is INDISTINGUISHABLE from the "never" sentinel.
Then the within-TTL arm checks `_mic_probe_at != 0.0` → FALSE → does NOT cache →
RE-PROBES. The test's "within TTL → still 1 call" assertion FAILS.

**Verified live (isolated gate simulation):**
```
clock base=0.0   (item's literal t=0):  init=1  withinTTL=2 (WRONG)  pastTTL=3  -> FAIL
clock base=1000.0 (non-zero):           init=1  withinTTL=1 (OK)    pastTTL=2  -> PASS
```

**Resolution (preserves the item's exact gate):** the TTL test MUST use a
clearly-non-zero base clock — `_fixed_clock(monkeypatch, 1000.0)` for
construction, then 1005.0 (within TTL) and `1000.0 + _MIC_PROBE_TTL_S + 5.0`
(past TTL). Do NOT freeze the clock to exactly 0.0 anywhere a probe stamps
`_mic_probe_at`. The real-clock test (`test_arm_refreshes_mic_status`) is
unaffected (real monotonic is never 0.0). Documented as Critical Gotcha #1.

(Alternative not taken: an `Optional[float]` / `None` sentinel would remove the
footgun but DEVIATES from the item's explicit "0.0 == never, matching
MicRetryRateLimitFilter" prescription. Keep the 0.0 sentinel; steer the test
away from 0.0.)

## 5. ★ FULL set of tests that break (3, not 1) ★

The item flagged only `test_arm_refreshes_mic_status`. Two MORE existing tests
break because they call `d._refresh_mic_status()` DIRECTLY (no force) right
after swapping `d._mic_prober`, expecting it to re-probe — but with TTL the call
is cached within the 30 s window (real clock, <1 s elapsed) and the swapped
prober never runs:

| line | test | why it breaks | fix |
|------|------|---------------|-----|
| 1484 | `test_refresh_mic_status_catches_probe_exception` | swaps prober→`boom`, calls `_refresh_mic_status()` (cached → boom never runs → `_mic_ok` stays True) | `force=True` |
| 1491 | `test_refresh_mic_status_stores_probe_result` | swaps prober→`(False,"no devices")`, calls `_refresh_mic_status()` (cached → result never stored) | `force=True` |
| 1506 | `test_arm_refreshes_mic_status` (item-flagged) | init+start within TTL → 2nd probe cached → `len(calls)` is 1 not 2 | assert `== 1` |

`test_init_initializes_mic_status_and_calls_probe` (1495) STILL PASSES: init uses
`force=True` → probes exactly once → `len(calls) == 1`. ✓
`test_probe_mic_*` (1471/1477/1484-ish) call `d._probe_mic()` DIRECTLY (raw, not
TTL-gated) → unaffected. ✓
`test_make_daemon_injection_is_hermetic_no_real_pyaudio` (1518) → unaffected. ✓

## 6. Test fixtures to reuse (tests/test_daemon.py)

- `_make_daemon(*, recorder, backend, cfg)` (424-430) → injects `mic_prober=
  _ok_probe`. For TTL tests, construct `daemon.VoiceTypingDaemon(...)` directly
  with a counting `mic_prober=` (mirroring 1495/1506).
- `_DaemonFakeFeedback`, `_StubRecorder`, `_FakeBackend` — the construction args
  used by 1495/1506; reuse verbatim.
- `_fixed_clock(monkeypatch, t)` (1551-1553): `monkeypatch.setattr(daemon.time,
  "monotonic", lambda: t)`. Patches `daemon.time.monotonic` globally for the
  test. Set BEFORE construction (init stamps `_mic_probe_at`) and re-set before
  each `d.start()` to advance the clock.
- Counting prober idiom (1495/1506): `mic_prober=lambda: (calls.append(1),
  (True, None))[1]` — append side-effect, return the (ok,error) tuple.
- `daemon._MIC_PROBE_TTL_S` is importable in tests (`from voice_typing import
  daemon`) — reference it (not a hardcoded 30.0) so the test survives tuning.

## 7. New test design (`test_mic_probe_cached_within_ttl`)

Uses `_fixed_clock` with a NON-ZERO base (1000.0 — see §4):
- construct at t=1000.0 with counting prober → init force-probes (calls=1),
  `_mic_probe_at=1000.0`.
- `_fixed_clock(1005.0)`; `d.start()` → `_arm` → `_refresh_mic_status()` →
  `1005-1000=5 < 30` → CACHED → calls still 1. ✓
- `_fixed_clock(1000.0 + daemon._MIC_PROBE_TTL_S + 5.0)`; `d.start()` →
  elapsed >= TTL → re-probe → calls=2. ✓

`d.start()` (not a raw `_refresh_mic_status` call) exercises the REAL _arm→
_refresh_mic_status integration path. Calling `d.start()` twice is idempotent
(re-arm); only the probe call count matters. No `run()` loop is started, so the
frozen clock does NOT trigger idle auto-stop (`_maybe_auto_stop` runs only in
the run loop). Placement: between `test_arm_refreshes_mic_status` (1506) and
`test_make_daemon_injection_is_hermetic_no_real_pyaudio` (1518).

## 8. Tooling & validation reality (verified)

- pytest 9.1.1 in `.venv`. Run: `.venv/bin/python -m pytest tests/test_daemon.py
  -v` (FULL path — zsh aliases). Whole fast suite:
  `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`
  (the item's "269+ tests" = whole repo; test_daemon.py alone = 117, all pass
  today).
- ruff 0.14.13 at `/home/dustin/.local/bin/ruff` (NOT in .venv); optional lint:
  `/home/dustin/.local/bin/ruff check voice_typing/daemon.py tests/test_daemon.py`.
- mypy NOT installed — do NOT list it as a gate.

## 9. Scope boundaries (do / don't)

DO: edit `voice_typing/daemon.py` (module const + __init__ + _refresh_mic_status
+ _arm comment); edit `tests/test_daemon.py` (2 force=True + 1 assertion update
+ 1 new test).
DON'T: edit `status.sh`/`test_status_sh.py` (P1.M2.T1.S1, parallel — disjoint);
edit `_probe_mic` itself; change the `_arm`/`_disarm`/`start`/`stop`/`toggle`
control flow (only the _arm inline comment); add locking (cache fields are
already lock-protected — scout §2); touch `PRD.md`/`tasks.json`/
`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps.
DOCS (Mode A): update the `_refresh_mic_status` docstring (TTL behavior, force
param, sentinel) and the `_arm` inline comment — no external docs files.

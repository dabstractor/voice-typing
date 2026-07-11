# Scout: Mic Probe Code Path & TTL Cache Design (from scout subagent)

## Files Mapped

1. `voice_typing/daemon.py:76` — `import time` (top-level; `time.monotonic` used in 9+ places)
2. `voice_typing/daemon.py:407-459` — `__init__`: lock, events, mic-probe attrs
3. `voice_typing/daemon.py:575-672` — `_arm`, `_disarm`, `_refresh_mic_status`, `_probe_mic`
4. `voice_typing/daemon.py:674-688` — `start`/`stop`/`toggle` (lock holders)
5. `voice_typing/daemon.py:1080-1130` — `MicRetryRateLimitFilter` (existing TTL/window pattern)
6. `tests/test_daemon.py:405-430` — `_ok_probe()` + `_make_daemon()` helpers
7. `tests/test_daemon.py:1431-1526` — mic-probe test block
8. `tests/test_daemon.py:1551-1553` — `_fixed_clock(monkeypatch, t)` (deterministic clock)

## Key Code

### `_arm()` (daemon.py:575-580) — calls _refresh_mic_status every arm
```python
575: def _arm(self) -> None:
576:     """Private: arm mic + set listening + notify. Called under the lock by start/toggle."""
577:     self._listening.set()
578:     self._last_speech_monotonic = time.monotonic()
579:     self._recorder.set_microphone(True)
580:     self._feedback.set_listening(True)
581:     self._refresh_mic_status()  # re-probe mic health on each arm
```

### `_refresh_mic_status()` (daemon.py:633-648) — SINGLE probe caller; TTL gate site
```python
633: def _refresh_mic_status(self) -> None:
641:     prober = self._probe_mic if self._mic_prober is None else self._mic_prober
642:     try:
643:         ok, error = prober()
644:     except Exception as exc:
645:         ok, error = False, str(exc)
646:     self._mic_ok = bool(ok)
647:     self._mic_error = error
```

### `_probe_mic()` (daemon.py:650-672) — the expensive PyAudio enumeration
```python
650: def _probe_mic(self) -> tuple[bool, str | None]:
661:     import pyaudio  # lazy: preserve ctl import purity
663:     pa = pyaudio.PyAudio()
664:     try:
665:         inputs = [
666:             i for i in range(pa.get_device_count())
667:             if (pa.get_device_info_by_index(i).get("maxInputChannels") or 0) > 0
668:         ]
669:     finally:
670:         pa.terminate()
671:     if not inputs:
672:         return False, "no PyAudio input devices available"
673:     return True, None
```

### `__init__` mic-probe setup (daemon.py:450-456)
```python
453: self._mic_ok: bool = True
454: self._mic_error: str | None = None
455: self._mic_prober = mic_prober
456: self._refresh_mic_status()
```

### Lock-site audit — ALL `_arm`/`_disarm` under `self._lock`:
- `start()` → `_arm()` under `with self._lock` (675→676) ✓
- `stop()` → `_disarm()` under `with self._lock` (680→681) ✓
- `toggle()` → both branches under `with self._lock` (684→685/687) ✓
- `_maybe_auto_stop()` → `_disarm()` under `with self._lock` (610→619) ✓
- `__init__` → `_refresh_mic_status()` — single-threaded construction ✓

**Conclusion: cache fields are ONLY ever read/written under self._lock (or construction). No extra locking needed.**

### Existing TTL pattern to mirror — MicRetryRateLimitFilter (daemon.py:1106-1123)
```python
1106: def __init__(self, dedup_seconds=60.0, ...):
1110:     self._last_seen = 0.0  # time.monotonic() of last EMITTED record; 0.0 == never
1117:     now = time.monotonic()
1123:         now - self._last_seen >= self.dedup_seconds
```

## Test Patterns

### `_ok_probe()` (test_daemon.py:405-411)
```python
405: def _ok_probe():
411:     return (True, None)
```

### `_make_daemon()` factory (test_daemon.py:424-430)
```python
424: def _make_daemon(*, recorder=None, backend=None, cfg=None):
429:     d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be, mic_prober=_ok_probe)
430:     return d, fb, rec, be
```

### `_fixed_clock()` — deterministic time.monotonic (test_daemon.py:1551-1553)
```python
1551: def _fixed_clock(monkeypatch, t):
1553:     monkeypatch.setattr(daemon.time, "monotonic", lambda: t)
```

### Existing mic-probe tests (test_daemon.py:1431-1526)
- `test_arm_refreshes_mic_status` (1506) — asserts 2nd arm re-probes (`len(calls)==2`). **MUST UPDATE for TTL.**
- `test_init_initializes_mic_status_and_calls_probe` (1495) — asserts `len(calls)==1` after init. Still passes (force=True).

## TTL Design
- Module constant: `_MIC_PROBE_TTL_S = 30.0`
- Field: `self._mic_probe_at: float = 0.0` (0.0 = never, sentinel convention)
- `_refresh_mic_status(force=False)`: gate on `self._mic_probe_at == 0.0 or time.monotonic() - self._mic_probe_at >= _MIC_PROBE_TTL_S or force`
- `__init__` calls with `force=True`

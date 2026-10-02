# Research: press_backspace(n) primitive — impl facts & test plan (VERIFIED)

**Status:** Verified against live `voice_typing/typing_backends.py` (301-line test file),
`plan/007_cfc245548aec/architecture/external_deps.md` §2–§4 (LOCAL probes on this machine), and
`substrate_map.md` §5. Load-bearing source for `P1M1T3S1/PRP.md`.

## 1. Current typing_backends.py (the INPUT — verified shape)

- `TypingBackend` ABC — ONE abstract method `type_text(text)` only. **No `press_backspace` exists
  anywhere yet** (verified: `grep -c press_backspace typing_backends.py` → 0).
- `WtypeBackend.type_text`: `subprocess.run(["wtype","--",text], check=True)`.
- `YdotoolBackend.type_text`: `subprocess.run(["ydotool","type","--key-delay","2","--",text], check=True)`.
- `NullBackend.type_text`: logs debug, spawns nothing.
- `_WtypeWithFallback`: ctor injects primary/fallback; `type_text` catches
  `(subprocess.CalledProcessError, OSError)`, `logger.warning("wtype typing failed (%s); retrying once
  via ydotool", exc)`, retries ONCE via `self._fallback.type_text(text)`; second failure propagates;
  TypeError NOT caught.
- `make_backend(cfg)`: "wtype"→`_WtypeWithFallback()`, "ydotool"→`YdotoolBackend()`, "null"→`NullBackend()`,
  else ValueError.
- No other `TypingBackend` subclass exists anywhere (daemon.py only uses it as a type hint at :95/:541) —
  adding `@abstractmethod press_backspace` breaks NOTHING existing.

## 2. External-binary facts (external_deps.md §2–§4 — LOCAL probes, authoritative)

- **wtype** (`man wtype` + `env -i /usr/bin/wtype -k Backspace -k Backspace` probe): `-k KEY` repeats
  within ONE invocation; the probe produced no usage/parse error (failed only at Wayland connect →
  nonzero exit → caught by the fallback as CalledProcessError). "Backspace" is a standard xkb keysym.
  → ONE call: `["wtype"] + ["-k","Backspace"]*n`. NO `--` needed (all args are options; no positional).
- **ydotool** (`ydotool key --help`): `key [OPTION]... [KEYCODES]...`; `-d N` = ms between keystrokes;
  codes are `<keycode>:<pressed>` pairs; Backspace keycode = 14 (linux/input-event-codes.h).
  → ONE call: `["ydotool","key","-d","1"] + ["14:1","14:0"]*n` (explicit small `-d`; do NOT rely on the
  default delay for 80-press batches).
- **Budget (PRD R2, ~80 chars < 150 ms):** one fork/exec (~5–15 ms) + 80 pairs ≈ 45–175 ms worst —
  batched single invocation meets it; per-keystroke spawning (80 × ~10 ms) is categorically too slow.
  THE reason both impls MUST batch.

## 3. The contract impls (exactly as the item specifies)

```python
# ABC:
@abstractmethod
def press_backspace(self, n: int) -> None: ...

# WtypeBackend:
def press_backspace(self, n: int) -> None:
    if n <= 0:
        return                      # no spawn
    subprocess.run(["wtype"] + ["-k", "Backspace"] * n, check=True)

# YdotoolBackend:
def press_backspace(self, n: int) -> None:
    if n <= 0:
        return                      # no spawn
    subprocess.run(["ydotool", "key", "-d", "1"] + ["14:1", "14:0"] * n, check=True)

# NullBackend:
def press_backspace(self, n: int) -> None:  # no-op — headless E2E safety
    logger.debug("null backend: suppressed %d backspaces", n)

# _WtypeWithFallback — SAME contract as type_text:
def press_backspace(self, n: int) -> None:
    if n <= 0:
        return                      # avoids pointless wtype try + WARNING on n=0
    try:
        self._primary.press_backspace(n)
    except (subprocess.CalledProcessError, OSError) as exc:
        logger.warning("wtype backspace failed (%s); retrying once via ydotool", exc)
        self._fallback.press_backspace(n)   # may raise -> propagates
```

## 4. Test plan (mirror the existing `_Recorder` harness; no real keystrokes EVER)

The `recorder` fixture monkeypatches `subprocess.run` and records `(argv, kwargs)`; `raise_on(argv[0],
exc)` simulates failures. New tests (ADDITIVE banner section):

1. `test_wtype_press_backspace_exact_argv` — n=3 → argv == `("wtype","-k","Backspace","-k","Backspace","-k","Backspace")`, check=True.
2. `test_ydotool_press_backspace_exact_argv` — n=2 → argv == `("ydotool","key","-d","1","14:1","14:0","14:1","14:0")`, check=True.
3. `test_press_backspace_n0_and_negative_spawn_nothing` — (WtypeBackend, YdotoolBackend, _WtypeWithFallback) × n ∈ {0, -1, -5} → `recorder.calls == []`.
4. `test_press_backspace_n80_is_one_invocation` — n=80 → `len(recorder.argvs) == 1`, argv length == 2+2*80, "Backspace" count == 80 (both backends; the <150 ms budget contract).
5. `test_press_backspace_fallback_ordering` — wrapper, wtype raises CalledProcessError → calls == [wtype-argv, ydotool-argv] (retry exactly once).
6. `test_press_backspace_fallback_logs_warning` (caplog) — WARNING mentions ydotool.
7. `test_press_backspace_fallback_failure_propagates` — both raise FileNotFoundError → the OSError propagates.
8. `test_press_backspace_fallback_success_no_third_call` — wtype fails once, ydotool succeeds → exactly 2 calls.
9. `test_null_press_backspace_no_subprocess` — `NullBackend().press_backspace(5)` → `recorder.calls == []`.
10. `test_typing_backend_is_abstract` — EXTEND or add: `TypingBackend()` still TypeError; AND a minimal subclass implementing only `type_text` fails to instantiate (missing abstract press_backspace) — proves the new method is genuinely abstract.
11. `test_wrapper_press_backspace_n0_skips_warning` — n=0 on wrapper → no call AND no WARNING logged.

The existing `test_no_real_subprocess_run_during_tests` guard (:274) already covers the whole file.

## 5. Parallel / scope

- **P1.M1.T2.S4** (parallel): prefetch.py, hypr-binds.conf, install.sh, ACCEPTANCE.md,
  test_systemd_unit.py — DISJOINT from typing_backends.py / test_typing_backends.py.
- This task: ONLY typing_backends.py + tests/test_typing_backends.py (+ docstring notes). No daemon
  wiring (P1.M2.T6), no cancel (P1.M2.T7), no RecordingTypingBackend (T8) — those CONSUME the primitive.
- Docs: none beyond docstrings (README streaming section = P1.M3.T10.S1).

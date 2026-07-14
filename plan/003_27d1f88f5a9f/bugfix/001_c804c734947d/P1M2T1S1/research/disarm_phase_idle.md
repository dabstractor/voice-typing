# Research: reset phase to 'idle' on disarm (P1.M2.T1.S1 / bugfix Issue 2)

Target: `voice_typing/daemon.py` `VoiceTypingDaemon._disarm()` — add a single
`self._feedback.set_phase("idle")` so the `phase` field returns to `idle` ("loaded /
not listening") after any disarm, instead of staying stuck at the last VAD value
(`listening`/`speaking`). PRD §4.2bis / §4.6.

---

## 1. The defect (root cause — from architecture/bug_analysis.md §Issue 2, confirmed in code)

`_disarm()` (daemon.py:851) clears `_listening`, stamps `_disarmed_monotonic`, calls
`host.set_microphone(False)`, and calls `feedback.set_listening(False)` — but it **never
calls `feedback.set_phase("idle")`**. The `phase` field is only ever ADVANCED by the child's
VAD callbacks relayed through `recorder_host._dispatch("vad", ...)` → `feedback.set_phase(phase)`
(`on_vad_detect_start`→`listening`, `on_vad_start`→`speaking`, `on_vad_stop`→`listening`).
There is no path that resets phase on disarm. So after `stop`/`toggle`-off/30s-auto-stop, `phase`
freezes at the last VAD value while `listening: off` — a self-contradictory status. Reproduced
live: `voicectl start` → `stop` → `status` shows `listening: off / phase: listening`.

`_disarm()` is the single chokepoint: it is called by `stop()`, `toggle()` (the disarm branch),
and `_maybe_auto_stop()` (the 30s auto-stop). Fixing it here covers ALL three disarm paths.

## 2. The fix (one line)

Current `_disarm()` body tail (daemon.py:870-875):
```python
        self._disarmed_monotonic = time.monotonic()  # start the idle-UNLOAD clock (P1.M3.T1.S1)
        if self._host is not None:
            self._host.set_microphone(False)
        self._feedback.set_listening(False)
        # NOTE: caller MUST call self._safe_abort() AFTER releasing _lock (see start/stop/toggle).
```
Add `self._feedback.set_phase("idle")` immediately AFTER `self._feedback.set_listening(False)`.
`set_phase` writes `state["phase"]="idle"` + an atomic state-file write (feedback.py `set_phase`
always writes), so both `state.json` and `voicectl status` (which reads
`feedback.snapshot()["phase"]`) immediately reflect `idle`.

The edit anchor is the unique trailing comment `# NOTE: caller MUST call self._safe_abort()
AFTER releasing _lock (see start/stop/toggle).` — it appears ONLY in `_disarm()`, so the
oldText→newText match is unambiguous despite `set_listening(False)` appearing elsewhere.

## 3. Why this is the ONLY place (no other disarm-like path needs it)

All other listening/phase transitions already set phase correctly:
- `__init__` (604): `set_phase("idle" if loaded else "unloaded")` — correct boot state.
- `run()` boot (708): `set_listening(False)` only (phase already 'unloaded'/'idle' from __init__).
- `_load_host` success (677): `set_phase("idle")` — correct ("loaded / not listening").
- `_load_host`/`_unload` failure/unload (690, 1018): `set_phase("unloaded")` — correct.
- `_handle_dead_host` (Issue 3, ~1018): `set_phase("unloaded")` — a DIFFERENT state (dead child);
  owned by P1.M2.T2 (Issue 3), NOT this task.
`_disarm()` is the one missing case. The one-liner completes the lifecycle.

## 4. No regression in the existing suite (verified)

`_FakeFeedback.set_phase` (test_daemon.py:42) ONLY appends to `fb.phases: list[str]` — it does
not touch `listening_states`, `finals`, or anything else. So adding `set_phase("idle")` to
`_disarm()` only adds an `'idle'` entry to `fb.phases` on each disarm. The existing `fb.phases`
assertions are at lines 239, 247, 250, 307 (`test_callback_vad_phases` — calls VAD callbacks
directly, NOT via _disarm), 1277, 1290 (`test_build_callbacks_threads_latency...` — calls
`cb["on_vad_stop"]()` directly, NOT via _disarm), and 2528/2870/2930 (lazy-load `_load_host`/
`_unload` tests — `fb.phases[-1]`, no disarm involved). **NONE of these go through `_disarm()`**,
so none see the extra `'idle'` entry. The disarm/auto-stop/stop/toggle tests (583, 626, 746, 757,
770, 778, 788, 795, 839, 897) assert `listening` state / abort calls / `_disarmed_monotonic`, NOT
`fb.phases`. Therefore the full fast pytest suite stays GREEN after the one-liner. (Confirmed by
grepping every `phases` reference — none sit inside a disarm-path test.)

## 5. The optional VAD-relay gate is OUT OF SCOPE (deferred — "only if observed")

A stray LATE `("vad", phase)` event from the child, arriving after disarm, could transiently
re-flip phase (recorder_host.py:348-350 `_dispatch("vad")` calls `feedback.set_phase(phase)`
unconditionally). The PRD/bug-analysis suggest gating it ("if that is observed"). The item contract
is explicit: **"Only add the gate if observed in practice."** Gating would require the host
(`recorder_host.RecorderHost._dispatch`) to know the daemon's `_listening` state, which it does NOT
currently have (the host holds `self._feedback`, not the daemon's listening Event) — an invasive
cross-layer change for an unobserved theoretical race. **S1 does NOT add the gate.** If a stray
re-flip is ever observed, the next disarm resets it (and a follow-up can add the gate). Documented
as an explicit anti-pattern (do NOT add it speculatively).

## 6. Test ownership boundary (S1 = code; S2 = the comprehensive test)

The plan splits this fix: **P1.M2.T1.S1 (THIS task, 0.5 pt) = the one-line code change**;
**P1.M2.T1.S2 (Planned, 1 pt) = "Test phase returns to idle after disarm (stop, toggle-off,
auto-stop)"**. So S1 delivers the code; S2 delivers the committed pytest that arms→triggers a VAD
phase→disarms (all 3 paths)→asserts `phase=='idle'`. S1's validation = static grep + the existing
fast suite green (no regression) + a throwaway inline proof (via the test fakes, NOT a committed
test file, to avoid pre-empting S2). This keeps S1 minimal and non-conflicting with S2.

## 7. Parallel context + scope

- **P1.M1.T2.S3 (parallel, Implementing)** = the SIGTERM teardown test (concurrent
  `request_shutdown()` + `shutdown()` → single `host.stop()`). It touches `daemon.py`'s
  `request_shutdown`/`shutdown`/`_bounded_shutdown` + adds a test to `test_daemon.py`. **No overlap**
  with `_disarm()`/phase — different methods, different concern (Issue 1 vs Issue 2).
- S1 edits ONLY the one line in `_disarm()`. No other source, no config, no recorder_host.py, no
  feedback.py, no docs (DOCS: none — behavior fix).
- pytest>=9.1.1 is the runner (NO ruff/mypy). Full paths in bash (`.venv/bin/python`, zsh aliases).

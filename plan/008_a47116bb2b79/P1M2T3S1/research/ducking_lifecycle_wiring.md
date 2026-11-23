# Research — daemon lifecycle wiring for media ducking (P1.M2.T3.S1)

## §0. Input chain state (re-verify at impl time)

- **LANDED**: `voice_typing/audio_ducking.py` — `AudioDucker` (engage/release idempotent, internal
  `threading.Lock`, `_engaged` set FIRST on engage, `_call` swallow; `from_config(cfg, backend)`).
  `voice_typing/ducking_mpris.py:75 class MprisBusctlBackend` (S2). `tests/test_ducking.py` (core
  tests only; imports `AudioDucker, PlayerState`). `config.py` AudioConfig (duck_mode="off",
  duck_volume_pct=15, guards @221-239).
- **PARALLEL/EXPECTED (the declared INPUT — "AudioDucker from P1.M2.T2.S4")**: `voice_typing/
  ducking_async.py` — `AsyncDucker` (single-flight latest-wins dispatcher; `engage()`/`release()`
  return immediately, never raise, worker thread `vt-ducking`; `flush(timeout)` bounded; `engaged`
  property proxy). NOT on disk at research time — verify `ls voice_typing/ducking_async.py` first.
- **PARALLEL**: `voice_typing/ducking_volume.py` (S3 wpctl backend) — NOT on disk at research time;
  verify its class name (expect `WpctlVolumeBackend`) before wiring the default factory.

## §1. THE RECONCILIATION — contract "spawn threads" vs S4's AsyncDucker

The item contract says "spawn engage/release threads at the sites (never inline under _lock)". That
wording predates S4's design. S4's PRP (the parallel CONTRACT) says explicitly: "**T3 (P1.M2.T3.S1)
wires `AsyncDucker.engage()` at `_arm()`'s toast site and `release()` at every disarm seam**". With
AsyncDucker, the daemon calls `engage()`/`release()` INLINE at the seams — they are non-blocking
(S4 contract: return <0.5 s even with a 5 s-hung backend; they only record desired state + ensure
one worker). The load-bearing invariant — **no blocking work under `self._lock`** — is preserved by
the AsyncDucker layer; the backend subprocess work runs on S4's `vt-ducking` worker, never on the
caller's thread. Do NOT spawn raw threads at the sites if `ducking_async.py` is present. (Fallback
ONLY if the orchestrator redirects: raw `threading.Thread(target=ducker.engage, daemon=True,
name="vt-duck").start()` per site — the seams doc §1c shape.)

## §2. The seams — current verified anchors (contract line numbers are STALE ~+50)

The contract cites daemon.py:1415/1454/1598-1601/1754/1817-1818/1871-1872/1050/2177 (seams-doc HEAD
2335a9e). The tree moved (P1.M1.* landed daemon edits). Current verified:
`_arm` @1409, `_disarm` @1470, `_handle_dead_host` @1062, `cancel` @1804, `request_shutdown` @2207,
ctor `__init__` @604-617 (`key_listener` param @615), ctor wiring @809-816. ALWAYS re-locate by
anchor text, not line number.

| Seam | Anchor (unique text) | Insert |
|---|---|---|
| ENGAGE (one choke point — covers EVERY arm: start, toggle, warm/cold) | in `_arm()`: `self._feedback.set_listening(True)` (immediately before `self._refresh_mic_status()`) | `self._duck_engage()` after it. `_arm` runs UNDER `self._lock` — safe only because AsyncDucker dispatch returns immediately |
| RELEASE 1 (covers manual stop + toggle-off immediate AND graceful-drain completion + idle auto-stop + Rev-3 HALT — ALL funnel into `_disarm()`) | in `_disarm()`: `self._feedback.set_listening(False)` (just before `set_phase("idle")`) | `self._duck_release()` after it. Under `_lock` — same reasoning |
| RELEASE 2 (quit + SIGTERM) | in `request_shutdown()`: `self._shutdown.set()` (first body line) | `self._duck_release()` after it (outside `_lock`) |
| RELEASE 3 (EDGE — child death while ducked; NOT a `_disarm()` path) | in `_handle_dead_host()`: `self._feedback.set_listening(False)` after `set_phase("unloaded")` (~@1105, inside `with self._lock`) | `self._duck_release()` after it |
| MUST NOT RELEASE | `cancel()` @1804 — never clears `_listening`, never calls `_disarm()` | no edit (assert in tests) |

Funnel verification (seams doc §1a′, still true): stop/toggle-off → `_request_stop()` → `_disarm()`
(imm) or drain Timer → `_complete_drain()` → `_disarm()`; idle auto-stop → `_maybe_auto_stop()` →
`_disarm()`; HALT → `note_user_keypress()` → `with self._lock: _disarm()`. All reach RELEASE 1.

## §3. ctor seam (mirror `key_listener=`)

`__init__` @604-617 gains `ducker: Any = None` keyword param (after `key_listener`). Wiring @809-816
mirrors the key_listener block:
```python
self._ducker: Any = ducker
if self._ducker is None and cfg.audio.duck_mode != "off":
    self._ducker = _build_default_ducker(cfg)   # module-level factory; PURE construction
```
`_build_default_ducker(cfg)`: pick the tier backend by `cfg.audio.duck_mode` ("mpris" →
`MprisBusctlBackend()`, "volume" → S3's wpctl backend class) → `AsyncDucker(AudioDucker.from_config(cfg, backend))`.
`duck_mode == "off"` ⇒ `self._ducker is None` ⇒ every seam no-ops ⇒ **byte-identical behavior**
(PRD acceptance). Construction is PURE (no subprocess, no threads at ctor — backends shell out only
inside their primitives; mirrors the key_listener "CONSTRUCTION IS PURE" rule @806-808). Import the
ducking modules top-level (all stdlib+subprocess-light; daemon stays CUDA-free).

## §4. The dispatch helpers (the only daemon-side new methods)

```python
def _duck_engage(self) -> None:
    """Best-effort media-ducking engage (PRD §4.2quinquies). Enhancement, NEVER a gate."""
    d = self._ducker
    if d is None:
        return
    try:
        d.engage()                       # AsyncDucker: non-blocking dispatch (S4)
        self._feedback.set_ducked(True)  # desired-state mirror (crash-safety signal, T3.S2 reads)
    except Exception:
        logger.warning("ducking: engage dispatch failed (ignored)")

def _duck_release(self) -> None:   # same shape; d.release(); set_ducked(False)
```
- `set_ducked` mirrors DESIRED state (conservative for crash-safety: if the daemon dies between
  dispatch and apply, the flag errs "ducked" and T3.S2's boot-time release is a safe no-op when
  wrong). The contract's "from the ducker thread" predates AsyncDucker; with the wrapper the
  synchronous call at the seam is correct (Feedback methods are lock-free, any-thread-safe —
  seams doc §1d).
- Idempotence: `_arm` twice → `d.engage()` twice (AsyncDucker coalesces; S4 territory) +
  `set_ducked(True)` twice (plain always-write setter — harmless).

## §5. feedback.py — the `ducked` field + LOCKSTEP test updates

Recipe (seams doc §2, templates verified): (1) add `"ducked": False,` to `_state` (feedback.py
@96-109, near "mode"); (2) add `set_ducked(self, ducked: bool) -> None` cloning `set_models_loaded`
@135-145 (`self._state["ducked"] = bool(ducked); self._write()`; never notifies — anti-spam rule);
(3) update the module-docstring schema line @11. ⚠ **tests/test_feedback.py PINS the exact key set
at :129 and :441** (`set(state.keys()) == {"listening","phase","models_loaded","mode","partial",
"last_final","ts"}`) — BOTH assertions must gain `"ducked"` in lockstep or the suite breaks.
`snapshot()` returns `dict(self._state)` → status sees `ducked` free. voicectl status RENDERING of
`ducked` is OUT of scope (optional surface; T3.S2/T4/P1.M7 may add).

## §6. Tests (append to tests/test_ducking.py — the "lifecycle cases")

Injection: `_FakeDucker` (records engage/release call counts + order, thread-safe) via the new
`ducker=` kwarg through a COPY of `_make_daemon` (tests/test_daemon.py @682-700 — verified: builds
VoiceTypingDaemon with fakes: `_DaemonFakeFeedback` @470, `_StubRecorder` @490, `_FakeBackend` @517,
`_ok_probe` @535). The copied factory in test_ducking.py passes `ducker=fake`; extend the feedback
fake to record `set_ducked` calls (subclass _DaemonFakeFeedback or add the attr dynamically).
The 9 lifecycle cases:
1. `test_ducking_engage_on_arm` — `start()` → engage called once; set_ducked(True) recorded.
2. `test_ducking_release_on_stop` — start→stop → release called.
3. `test_ducking_release_on_toggle_off` — start→toggle (armed) → release called.
4. `test_ducking_release_on_drain_completion` — graceful_stop cfg, start, `_request_stop()` with a
   pending final → run-loop drain path → `_complete_drain()` → release (or drive `_complete_drain`
   directly if the run loop isn't running — mirror existing drain tests in test_daemon.py).
5. `test_ducking_release_on_idle_auto_stop` — call `_maybe_auto_stop()` directly (precedent:
   daemon docstring "also safe to call directly (unit tests do)").
6. `test_ducking_release_on_halt` — arm then `note_user_keypress()` (after the 1.5 s grace — pass
   `time.monotonic` seam or monkeypatch; mirror existing HALT tests) → release called.
7. `test_ducking_release_on_quit` — `request_shutdown()` → release called.
8. `test_ducking_release_on_dead_host` — `_handle_dead_host()` → release called.
9. `test_ducking_no_release_on_cancel` — arm → `cancel()` → release NOT called; ducker stays
   engaged; `_listening` still set (the distinguishing signal, seams doc §1b).
Plus: `test_ducking_off_mode_no_ducker` — default cfg (duck_mode="off") → daemon._ducker is None;
arm/disarm make zero ducking calls (byte-identical behavior). ≈10 new tests.

## §7. Scope boundaries

- THIS task: ctor seam, `_duck_engage`/`_duck_release` helpers, engage @_arm, release @_disarm/
  request_shutdown/_handle_dead_host, Feedback.set_ducked + `_state["ducked"]` + docstring +
  test_feedback lockstep (:129/:441), daemon.py module-docstring ducking note (Mode A), lifecycle
  tests in test_ducking.py.
- T3.S2 (NEXT — crash safety): startup self-heal (reads state `ducked:true` → best-effort release),
  `flush()` at the quit path, ExecStopPost in systemd/voice-typing.service + its lockstep test.
  → Do NOT add those here. set_ducked is OURS (the write side); the boot-time READ is S2's.
- S4 owns AsyncDucker internals; S1 owns AudioDucker bookkeeping (FROZEN); T4 owns the default flip.
- NOT here: voicectl status rendering of ducked, README (P1.M7), config surface (done T1).

## §8. Validation (verified commands)

```bash
timeout 600 .venv/bin/python -m pytest tests/test_ducking.py -q                    # core + new lifecycle green
timeout 600 .venv/bin/python -m pytest tests/test_feedback.py tests/test_daemon.py -q   # lockstep + no regression
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q  # no new failures vs tests/G1_BASELINE.md
```
All unit tests are CUDA-free/mocked (fast). Full paths always (zsh aliases).

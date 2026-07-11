# System Context — Plan 002 Delta (idle auto-stop / notify_on_final / partial-sync)

## Project State

**NOT a greenfield project.** The voice-typing daemon is fully implemented, tested, and committed
across two prior planning sessions (`plan/001_be48c74bc590` and its bugfix cycle). The repository
at `/home/dustin/projects/voice-typing` contains a complete, working system:

- `voice_typing/daemon.py` (66,965 bytes) — full daemon with recorder wiring, control socket,
  toggle/start/stop gate, idle watchdog, CPU fallback, mic probe, logging.
- `voice_typing/config.py` (10,536 bytes) — dataclass + TOML loader with XDG search order.
- `voice_typing/feedback.py` (11,319 bytes) — atomic state file writer + hyprctl notify.
- `voice_typing/typing_backends.py` — wtype/ydotool/tmux backends with auto-fallback.
- `voice_typing/textproc.py` — normalization + hallucination blocklist filter.
- `voice_typing/ctl.py` — voicectl client CLI.
- `voice_typing/cuda_check.py`, `voice_typing/prefetch.py`, `voice_typing/launch_daemon.sh`,
  `voice_typing/status.sh` — support modules.
- `config.toml`, `pyproject.toml`, `uv.lock`, `install.sh`, `systemd/voice-typing.service`,
  `hypr-binds.conf` — config/packaging.
- `tests/` — 10 test files: `test_config.py`, `test_config_repo_default.py`, `test_daemon.py`
  (79,313 bytes, 116 tests), `test_feedback.py`, `test_textproc.py`, `test_typing_backends.py`,
  `test_voicectl.py`, `test_control_socket.py`, `test_feed_audio.py`, `e2e_virtual_mic.sh`,
  `test_idle_and_gpu.sh`, `make_test_audio.sh`, plus `ACCEPTANCE.md`.

**Git HEAD:** `367b774 add idle auto-stop for forgotten hot-mics` — all three delta features
(D1, D2, D3) are ALREADY committed.

## This Delta (Plan 002)

A **spec-sync verification** — the PRD was updated to document three already-shipped features,
plus one residual stale comment fix. No functional code changes are required.

### Delta D1: Idle auto-stop (`asr.auto_stop_idle_seconds`)

- **Config:** `config.py:58` → `AsrConfig.auto_stop_idle_seconds: float = 30.0`
- **Config file:** `config.toml:35` → `auto_stop_idle_seconds = 30.0`
- **Daemon:** `daemon.py:581` `_maybe_auto_stop()` — disarms under `_lock` when
  `time.monotonic() - _last_speech_monotonic >= threshold`; `daemon.py:602` `_idle_watchdog()`
  — background daemon thread ticking every 1s via `_shutdown.wait(1.0)`.
- **Tests:** `test_daemon.py` — 6 idle tests (disarm-on-idle, keep-alive, touch-resets, disabled-
  at-0, noop-when-not-listening, real background-thread disarm). ALL PASS.

### Delta D2: `feedback.notify_on_final`

- **Config:** `config.py:78` → `FeedbackConfig.notify_on_final: bool = True`
- **Config file:** `config.toml:51` → `notify_on_final = true`
- **Feedback:** `feedback.py:record_final()` — `if self._cfg.hypr_notify and self._cfg.notify_on_final: self._notify(...)`.
- **Tests:** `test_feedback.py::test_record_final_silent_when_notify_on_final_false` + others. ALL PASS.

### Delta D3: `record_final` writes finalized text into `partial`

- **Feedback:** `feedback.py:record_final()` → `self._state["partial"] = text` (line in method body).
- **Tests:** `test_feedback.py::test_record_final_updates_partial_so_status_matches_screen`. PASS.

### Residual Fix: stale `hypr_notify` comment in `config.toml:49`

**Current (WRONG):**
```toml
hypr_notify = true      # show a hyprctl notify one-liner for start/partial/final/stop. ...
```
**Should be:**
```toml
hypr_notify = true      # show a hyprctl notify one-liner for start/final/stop. ...
```
The word "partial" is wrong — partials NEVER fire hyprctl (anti-spam discipline, PRD §4.6).
README.md already states this correctly. Only `config.toml` lags.

### T4 Interaction (test_idle_and_gpu.sh vs auto_stop_idle_seconds)

`test_idle_and_gpu.sh` arms the daemon and holds 120s of silence. With the default
`auto_stop_idle_seconds=30.0`, the daemon auto-disarms ~30s into the window.

**Verified:** The test does NOT assert `listening==true` at the end of the idle window. It only
checks:
1. `typed_before == typed_after` (capture-pane unchanged — no finals typed)
2. `last_final_before == last_final_after` (state.json unchanged — no hallucination)
3. `kill -0 $DAEMON_PID` (daemon alive — no crash)
4. CPU avg < 25% of one core

Auto-disarm satisfies all four (it types nothing, doesn't set last_final, doesn't crash, uses
negligible CPU after disarming). The `voicectl stop` call after the idle window returns `ok:true`
even if already stopped (it's idempotent — the stop path is a no-op when not listening).

**Verdict: T4 passes without modification.** No assertion relaxation needed.

## Machine Facts (verified this session)

| Fact | Value | Status |
|---|---|---|
| GPU | NVIDIA RTX 3080 Ti, 12 GiB, driver 610.43.02 | ✅ Verified |
| wtype/ydotool/xdotool | All installed at /usr/bin/ | ✅ Verified |
| portaudio | **NOT installed** (PyAudio dep) | ⚠️ Known gap — install.sh handles |
| espeak-ng, sox, ffmpeg, jq, cargo, go | All present | ✅ Verified |
| hyprctl | /usr/bin/hyprctl | ✅ Verified |
| No notification daemon | Confirmed (expected) | ✅ Verified |
| /dev/uinput | crw-rw-rw-+ user in input group | ✅ Verified |
| Default source | Webcam Vitade AF Mono (USB) | ✅ Verified |
| Python | System python3 is 3.14.5; .venv has 3.12 (managed by uv) | ✅ Verified |
| uv | 0.7.11 at /home/dustin/.local/bin/uv | ✅ Verified |

## Test Suite Status (verified this session)

```
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py \
  tests/test_feedback.py tests/test_textproc.py → 81 passed in 0.07s
.venv/bin/python -m pytest tests/test_daemon.py → 116 passed in 1.52s
Total: 197 passed (fast suite)
```

Heavy shell tests (test_idle_and_gpu.sh, e2e_virtual_mic.sh) not re-run this session (3-4 min each,
require GPU cold init) — they are for the implementation phase regression run.

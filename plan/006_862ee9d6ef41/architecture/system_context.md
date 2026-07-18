# System Context — voice-typing (plan/006)

## CRITICAL FINDING: Project is NOT greenfield — it is substantially implemented

The PRD §2 states "empty git repo (only `.git`), branch `main`, clean." This is **stale**.
The actual repo at `/home/dustin/projects/voice-typing` is a **mature, heavily-developed codebase**
with 50+ commits spanning July 6–18, 2026. All modules, tests, config, and infrastructure
described in the PRD §4.1 repository layout **already exist and are coded**.

### Existing source files (all present, all non-trivial):

| File | Lines | PRD § | Status |
|------|-------|-------|--------|
| `voice_typing/daemon.py` | 2221 | §4.2, §4.2bis | **Fully implemented**: VoiceTypingDaemon class with lazy load, recorder-host subprocess management, graceful drain, idle auto-stop, idle unload, lite mode, control socket |
| `voice_typing/recorder_host.py` | 774 | §4.2bis | **Fully implemented**: RecorderHost class, multiprocessing queue IPC, `_worker_main` child, process group mgmt (os.setsid/killpg), `_RelayFeedback`/`_RelayLatency` |
| `voice_typing/config.py` | 308 | §4.5 | **Fully implemented**: AsrConfig, OutputConfig, FeedbackConfig, FilterConfig, LogConfig dataclasses, tomllib loader, type validation |
| `voice_typing/ctl.py` | 219 | §4.8 | **Fully implemented**: all 7 commands, loading hint, socket client |
| `voice_typing/cuda_check.py` | 168 | §4.4 | **Fully implemented**: ctranslate2 CUDA probe, CPU fallback |
| `voice_typing/feedback.py` | 262 | §4.6 | **Fully implemented**: atomic state file, hyprctl notify, throttling |
| `voice_typing/typing_backends.py` | 164 | §4.3 | **Fully implemented**: WtypeBackend, YdotoolBackend, TmuxBackend, auto-fallback wrapper |
| `voice_typing/textproc.py` | 70 | §4.7 | **Fully implemented**: clean() with blocklist, min_chars, whitespace |
| `voice_typing/prefetch.py` | 168 | §4.4 | **Fully implemented**: HF model prefetch |
| `voice_typing/launch_daemon.sh` | — | §4.4,§4.9 | **Fully implemented**: LD_LIBRARY_PATH wrapper |
| `voice_typing/status.sh` | — | §4.6 | **Fully implemented**: tmux status helper |

### Existing tests (14 test files):
test_config.py, test_config_repo_default.py, test_control_socket.py, test_daemon.py,
test_feed_audio.py, test_feedback.py, test_recorder_host.py, test_status_sh.py,
test_systemd_unit.py, test_textproc.py, test_typing_backends.py, test_voicectl.py

Plus shell tests: make_test_audio.sh, e2e_virtual_mic.sh, test_idle_and_gpu.sh
Test audio assets generated: utt_simple.wav, utt_pause.wav, utt_punct.wav, utt_multi.wav

### Existing infrastructure:
- config.toml (fully self-documenting, mirrors config.py schema)
- hypr-binds.conf (both keybinds: Ctrl+Alt+Super+D, Alt+Super+D)
- systemd/voice-typing.service (with __REPO__ placeholder, graphical-session.target, KillMode=mixed)
- install.sh (idempotent, uv sync, prefetch, service install)
- README.md (20KB, comprehensive)

### Git history highlights:
- Core implementation, graceful drain, recorder-host subprocess architecture
- Lite mode (§4.2ter) with silence gate optimization
- Multiple bug fix rounds: dead child detection, config type validation, VAD race, abort deadlock
- Config hardening and portability fixes
- Documentation sync commits

## Implication for plan/006

This round is a **verification, gap-analysis, and remediation** cycle, NOT a greenfield build.
The task breakdown must:
1. **Audit** every PRD requirement against the actual codebase
2. **Validate** test coverage matches T1–T7 and acceptance criteria §7
3. **Identify and close** any remaining gaps (stale docs, missing test assertions, drift)
4. **Run** the full test suite and heavy E2E/GPU tests to confirm acceptance
5. **Sync** all changeset-level documentation

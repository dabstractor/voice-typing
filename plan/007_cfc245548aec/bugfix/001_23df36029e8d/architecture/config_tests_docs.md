# Config, tests & docs findings

## Config (BUG-006)

`voice_typing/config.py` — `VoiceTypingConfig.from_toml(data)` :329-354 builds via nested `_overlay(section_cls, table_name)` for exactly six tables: `asr`, `output`, `cancel`, `feedback`, `filter`, `log`. Unknown KEYS raise TypeError because `section_cls(**section)` hits the dataclass `__init__` (documented in the from_toml docstring). Unknown top-level TABLES are silently ignored — `data.get(table_name, {})` never consults the remaining keys of `data`. Fix shape: after (or before) overlaying, compute `unknown = set(data) - {"asr","output","cancel","feedback","filter","log"}` and `raise TypeError(...)` naming them, mirroring the existing message style; update the from_toml docstring. Callers: `from_toml_file` :356, `load` :361 (search order: `$XDG_CONFIG_HOME/voice-typing/config.toml` → `<repo>/config.toml` → defaults).

Existing rejection test to mirror: `tests/test_config.py::test_from_toml_unknown_key_raises` :135-147.

Doc surface (Mode A rides with the fix): `config.toml` header :22 — "Unknown keys are REJECTED at load time (a typo raises an error instead of being silently ignored)" — extend to say unknown `[table]` names are rejected too.

## Test infrastructure

Fast (no CUDA, doubles only — safe to run targeted): `test_config.py`, `test_control_socket.py`, `test_streaming_core.py`, `test_streaming_freeze.py`, `test_streaming_commit.py`, `test_streaming.py`(?), `test_textproc.py`, `test_feedback.py`, `test_key_listener.py`, `test_prompt_engine.py`, `test_typing_backends.py`, `test_voicectl.py`, `test_cuda_check.py`, `test_systemd_unit.py`, and the doubles-driven parts of `test_daemon.py` (ACCEPTANCE row 10 calls the mocked daemon tests "fast suite", 193 tests). CUDA-heavy (do NOT run casually; single-file + `timeout 600` + harness backstop per AGENTS.md): `test_feed_audio.py`, model-loading tests inside `test_daemon.py`/`test_recorder_host.py`, `test_streaming.py` (CUDA-gated, `timeout 900`), plus shell suites `test_idle_and_gpu.sh` / `e2e_virtual_mic.sh` (5-8 min, global audio rebind — out of scope for this bugfix changeset).

Key patterns:
- `tests/test_streaming_core.py:292` — `stream.reset_boundary()  # next utterance begins` — manual boundary invocation that MASKS the daemon sequencing bugs; new daemon-level regression tests must drive daemon methods (`d._touch_speech()`, `d.on_final(...)`, `d.cancel()`) instead.
- `tests/test_control_socket.py` — dispatch-level tests (`test_dispatch_malformed_json` :178, `test_dispatch_unknown_command` :170) + round-trip tests over a real socket (`test_round_trip_status` :190, `test_round_trip_toggle_then_status` :196) — the empty-line fix needs a round-trip-level test (the `continue` lives in `_handle`, not `_dispatch`).
- Regression-test homes recommended: engine semantics → `test_streaming_freeze.py` / `test_streaming_core.py` / `test_streaming_commit.py`; daemon sequencing (rejected-final recovery, cancel→next-utterance live typing, stale-partial-after-disarm, stop-after-cancel) → `tests/test_daemon.py` (new test functions using the :684 construction pattern); empty-line reply → `test_control_socket.py`; unknown table → `test_config.py`.

## Documentation surfaces (no docs/ dir exists)

- `README.md` headings (line numbers): `# voice-typing` :1, Requirements :14, Install :22, First run :48, Hotkey :79, Upgrading from Rev 1 :114, **Streaming dictation :129**, **Backspace-cancel :164**, Feedback surfaces :182, **Configuration :197**, voice-activity constants note :234, CPU-only :255, Troubleshooting :282, **Logs, status, stopping :339**, Model lifecycle & VRAM :389. Mode B final sweep: update §Streaming dictation / §Backspace-cancel / §Configuration for the fixed behaviors.
- `tests/ACCEPTANCE.md` — row 4 :35 ("nothing typed while toggled off (the `listening` gates on partial and commit paths are unchanged)" — evidence text claims the gate covers BOTH paths; false until BUG-004 fixed → Mode A update with the fix, then Mode B re-verify), rows 11-12 :42-43 (streaming & cancel criteria evidence). Header note :18 mentions one-model greps.
- `config.toml` header :22 (unknown-key rejection promise — extend for tables, Mode A with BUG-006).
- `hypr-binds.conf` — Backspace binding doc; unaffected by these fixes (verify only).

## Per-bug doc-touch map (Mode A)

| Bug | File/section |
|---|---|
| BUG-001 | none per-subtask (README §Streaming sweep is Mode B); in-code docstrings ride with the change |
| BUG-002 | none per-subtask (README §Backspace-cancel sweep is Mode B) |
| BUG-003 | none (internal correctness; README already promises space-separated words) |
| BUG-004 | `tests/ACCEPTANCE.md` row 4 evidence text + new regression-test citation |
| BUG-005 | `ControlServer` class docstring behavior table (daemon.py :2338); README §Logs/status only if it documents request framing |
| BUG-006 | `config.toml` header :22 + `from_toml` docstring |
| BUG-007 | none |
| BUG-008 | none |

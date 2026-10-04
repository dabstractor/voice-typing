# External dependencies — Rev 2 bugfix changeset

**No new external dependencies are required.** This is a pure bugfix changeset against existing code; every fix is within `voice_typing/{streaming,daemon,config,textproc}.py` and `tests/`. No new tech to research externally; no network access needed by any subtask.

Context on the external surfaces the fixes touch (for MOCKING guidance):

- **RealtimeSTT (via `voice_typing/recorder_host.py` subprocess)** — emits stabilized partials continuously (including stray post-final partials), `on_speech`/`on_vad_*` hooks, silence-triggered finals. ALL subtasks must mock at the recorder-host/IPC boundary (use `tests/test_daemon.py` doubles: `_StubRecorder`, `_FakeHost` with `consume_cancel_mark`, `_FakeBackend`) or drive `StreamingOutput` directly with fake backend/feedback. Never load a real model in these subtasks (AGENTS.md: CUDA suites are minutes-long; not needed to expose or verify any of the 8 bugs).
- **Typing backends (wtype/ydotool)** — `type_text(s)` / `press_backspace(n)`; mock with `_FakeBackend` recording calls.
- **evdev** — listener maps KEY_BACKSPACE→cancel, all other keys→`note_user_keypress`; key_listener logic is NOT modified by this changeset (BUG-003's trigger is accepted behavior; the fix is the separator, not the routing).
- **Control socket clients (`voicectl` / `nc -U`)** — line-oriented JSON; the socket has NO read timeout (AGENTS.md hazard) — that is exactly why BUG-005 matters; any live verification MUST use `timeout 5` wrappers, but unit/round-trip tests with the in-process `ControlServer` suffice.

Verification commands (fast, no CUDA): `timeout 600 uv run pytest tests/test_streaming_freeze.py tests/test_streaming_core.py tests/test_streaming_commit.py -q` and `timeout 600 uv run pytest tests/test_daemon.py -k '<new test names>' -q` (set the harness timeout above the inner one). Do NOT run the two shell E2E suites for this changeset.

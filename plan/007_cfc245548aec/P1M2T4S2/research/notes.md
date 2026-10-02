# Research notes — P1.M2.T7.S2 evdev passive listener

## evdev API facts (from architecture/external_deps.md §1, verified LOCAL/WEB)
- `evdev` 1.9.3, installed in venv since P1.M1.T1.S2 (import available).
- `evdev.list_devices() -> list[str]` of readable `/dev/input/event*` paths.
- `evdev.InputDevice(path)` opens fd O_RDWR|O_NONBLOCK (group `input` rw required — user has it). Raises FileNotFoundError/PermissionError.
- `dev.capabilities()` dict keyed by ecodes; keyboard filter: `ecodes.EV_KEY in caps and ecodes.KEY_BACKSPACE in caps[ecodes.EV_KEY]` (KEY_BACKSPACE == 14).
- `dev.read_loop()` yields InputEvent(type, code, value, sec, usec). EV_KEY value: 1=press, 0=release, 2=autorepeat (IGNORE 2).
- read_loop does NOT grab; `dev.grab()` (EVIOCGRAB) must NEVER be called.
- Multi-device: one reader thread per device (matches daemon thread style) or selectors on fileno().
- Device vanishing mid-read: OSError/EOFError out of read_loop → close, optionally re-enumerate. Open failures logged ONCE at arm, not per retry.
- Docs: https://python-evdev.readthedocs.io/en/latest/tutorial.html , /api.html

## Daemon integration sites (voice_typing/daemon.py, HEAD)
- `_arm()` :973-990 — listener start hook point (called under lock by start/toggle :1377-1413).
- `_disarm()` :992-1018 — must NOT tear down listener (per PRD: keep listening gesture independent; listener runs daemon-lifetime once armed at first arm; simplest per contract: start at arm when cfg.cancel.on_backspace; keep running afterwards — re-arm cheap/idempotent).
- Threading pattern: `threading.Thread(target=..., name="...", daemon=True).start()` (:791-794).
- Lock discipline: NEVER call anything that can block under `self._lock` (validation NEW-2) — evdev open/enumerate happens at arm on the control thread; per-event callbacks must not take the lock; they call existing `cancel()` / `on_user_key()` seams which handle their own locking.

## Upstream seams (contracts from sibling PRPs)
- P1.M2.T7.S1 delivers `VoiceTypingDaemon.cancel()` + `_dispatch "cancel"` — same path used by `voicectl cancel`. Idempotent when no tail pending.
- P1.M2.T6.S3 delivers `engine.on_user_key()` freeze hook (StreamingOutput freeze on non-Backspace press). PRP assumes this method exists; guard with `getattr`/hasattr is NOT desired — plan orders S3 before T7 verification; but task tree shows T6 planned before T8. Reference the method as the contract.
- Config (P1.M1.T1.S1, config.py:160-195): `CancelConfig.on_backspace: bool = True`, `devices: list[str] = []`, validated bool/str-list.

## Test patterns
- Pure-parser tests modeled on tests/test_textproc.py style (plain functions, no fixtures, no hardware).
- tests/test_daemon.py `_FakeHost` :532-613 / `_FakeBackend` :493-504 — fake injection pattern for daemon-level tests; inject a fake listener factory to avoid real /dev/input.
- AGENTS.md: any /dev/input probe under timeout; never run daemon foreground; unit tests use synthetic events only.

## Real keyboard smoke
- Deferred to T5 manual smoke / P1.M3.T10.S1 README first-run (per item contract point 3).

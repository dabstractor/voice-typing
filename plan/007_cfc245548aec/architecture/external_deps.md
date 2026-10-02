# External dependencies — Rev 2 (python-evdev, wtype/ydotool key batching)

Compiled 2026-10-02 from LOCAL probes on this machine (authoritative for the installed binaries)
plus two web checks (evdev version/API). Facts marked LOCAL were executed here; facts marked WEB
carry their source URL. Anything not verifiable is marked UNVERIFIED.

## 1. python-evdev (PyPI package `evdev`, import `evdev`)

- **Version:** 1.9.3 (Feb 5, 2025) is the latest stable release — WEB:
  https://python-evdev.readthedocs.io/en/latest/changelog.html . PyPI requires Python >=3.11 —
  WEB: https://pypi.org/project/evdev — so the repo venv (Python 3.12.10, LOCAL) is compatible.
  Binary wheels ship via the companion `evdev-binary` package; plain `evdev` may compile a small
  C extension at install time (uv handles this normally on Arch).
- **Status on this machine:** NOT installed in `.venv` or system python (LOCAL probe:
  `ModuleNotFoundError: No module named 'evdev'`) → must be added via
  `/home/dustin/.local/bin/uv add evdev` (PRD §5).
- **API contract for the passive listener** (docs: https://python-evdev.readthedocs.io/en/latest/tutorial.html
  and /api.html):
  - `evdev.list_devices() -> list[str]` — readable `/dev/input/event*` paths.
  - `evdev.InputDevice(path)` — opens the fd (O_RDWR|O_NONBLOCK by default); raises
    `FileNotFoundError` / `PermissionError` for missing/unreadable nodes (catch and skip).
  - `dev.capabilities()` — dict keyed by event type; a keyboard node for our purposes is one where
    `ecodes.EV_KEY in caps and ecodes.KEY_BACKSPACE in caps[ecodes.EV_KEY]`.
  - `ecodes.KEY_BACKSPACE == 14` — LOCAL, `/usr/include/linux/input-event-codes.h:90`
    (`#define KEY_BACKSPACE 14`).
  - `dev.read_loop()` — generator of `InputEvent(type, code, value, sec, usec)`. For `type == EV_KEY`:
    `value` 1 = key press, 0 = key release, 2 = autorepeat (MUST be ignored as a fresh press).
  - **Passive read, no grab:** plain `read_loop()` does NOT grab the device; `EVIOCGRAB` is opt-in
    via `dev.grab()`, which we must NEVER call (PRD §4.2quater). Without a grab the compositor
    keeps receiving events — coexistence with Hyprland is the kernel-input-layer default.
  - **Multi-device watching:** either one reader thread per device (simplest; matches our daemon's
    thread style) or `selectors.DefaultSelector()` registered on each `dev.fileno()` with
    `dev.read_one()` on readiness.
  - **Resilience:** a device vanishing mid-read raises `OSError`/`EOFError` out of `read_loop()`;
    the resilient pattern is close + (optionally) re-enumerate. Open failures at enumeration are
    per-device and must be logged ONCE at arm (PRD R4), not per retry.
- **Permissions (LOCAL):** `/dev/input/event*` are `crw-rw---- root:input`; user `dustin` is in
  group `input` (994, `id` probe) — no permission changes needed. NOTE: evdev's `InputDevice`
  opens O_RDWR even for reading, so group rw (which we have) is required — read-only bits alone
  would NOT suffice.

## 2. wtype (default typing backend; installed `/usr/bin/wtype`)

- LOCAL, `man wtype`: "-k KEY — Type (press and release) key KEY." Named keys are resolved by
  libxkbcommon ("Left", "Home" given as valid examples — "Backspace" is a standard xkb keysym
  name). SYNOPSIS: `wtype [OPTION_OR_TEXT]... -- [TEXT]...` — option occurrences REPEAT within a
  single invocation.
- LOCAL parse probe (`env -i /usr/bin/wtype -k Backspace -k Backspace`): no usage/parse error —
  wtype accepted both `-k` occurrences and proceeded to fail only at Wayland connect
  ("XDG_RUNTIME_DIR is invalid or not set", "Wayland connection failed"). Exit code note: the
  probe's `exit=0` is the pipeline's `head`, not wtype; wtype exits nonzero on connect failure
  (which `_WtypeWithFallback` catches as `CalledProcessError`).
- **VERDICT for `press_backspace(n)`:** ONE subprocess call — `["wtype"] + ["-k", "Backspace"] * n`.
  Do NOT spawn wtype per keystroke: ~80 spawns × ~10 ms would blow the PRD budget (~80 chars in
  <150 ms); one process doing 80 press/release pairs is comfortably inside it.
- Upstream: https://git.sr.ht/~sircmpwn/wtype (README examples with several `-M/-k/-m` options in
  one invocation — UNVERIFIED-live, but the local man synopsis + parse probe are sufficient).
- wtype has NO `--help` flag (LOCAL: prints "Missing argument to --help"); `-d ms` sets the
  inter-keystroke delay for typed TEXT, not for `-k` presses.

## 3. ydotool (fallback backend; installed)

- LOCAL `ydotool key --help`: `Usage: key [OPTION]... [KEYCODES]...`; `-d/--key-delay=N`
  (milliseconds between keystrokes); raw keycodes as `<keycode>:<pressed>`, e.g. `28:1 28:0` =
  Enter press+release; refers to `/usr/include/linux/input-event-codes.h` (Backspace = 14).
- **VERDICT for `press_backspace(n)`:** ONE subprocess call —
  `["ydotool", "key", "-d", "1"] + ["14:1", "14:0"] * n` (pass an explicit small `-d`; do not rely
  on the default delay for 80-press batches).
- Requires the `ydotoold` daemon socket (`YDOTOOL_SOCKET` or default) — already the situation for
  the existing `ydotool type` fallback path; no new setup.

## 4. Budget check (PRD R2: ~80 chars rewound in <150 ms)

One fork/exec (~5–15 ms) + 80 press/release pairs over the virtual-keyboard/uinput protocol
(~0.5–2 ms each worst case) ≈ 45–175 ms worst case, typically well under 150 ms with a single
batched invocation. Per-keystroke process spawning is categorically too slow. Both backends MUST
batch into a single invocation; the `_WtypeWithFallback` wrapper applies the same retry-once
fallback contract to `press_backspace` as to `type_text`.

## 5. Web-check provenance

- evdev changelog/version: https://python-evdev.readthedocs.io/en/latest/changelog.html (1.9.3, Feb 2025)
- evdev PyPI metadata (requires-python >=3.11): https://pypi.org/project/evdev
- evdev docs home: https://python-evdev.readthedocs.io (tutorial + api pages)
- wtype upstream: https://git.sr.ht/~sircmpwn/wtype (UNVERIFIED-live)
- Researcher-child note: the `researcher` subagent cannot load MCP web tools as a foreground
  child in this harness; the parent ran the two web checks directly (see system_context.md).

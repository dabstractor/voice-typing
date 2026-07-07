# Research — P1.M3.T1.S1 typing_backends.py

Verified machine facts + design decisions for `voice_typing/typing_backends.py`.
All shell checks were run live on the target machine on 2026-07-06. This is a
RESEARCH artifact (the implementer reads it; the PRP is the deliverable).

---

## 1. Verified CLI facts (live, on this exact machine)

| Tool | Path | Status | Notes |
|---|---|---|---|
| wtype | `/usr/bin/wtype` | present | Wayland virtual-keyboard-v1. `wtype -- "text"` types into focused window. `--help` prints "Missing argument to --help" (argp quirk; harmless). |
| ydotool | `/usr/bin/ydotool` | present | uinput-level. `ydotool type [OPTION]... [STRINGS]...`. |
| tmux | `/usr/bin/tmux` | present | zsh aliases `tmux` → ALWAYS use the full path `/usr/bin/tmux` in subprocess. |

### 1.1 tmux `send-keys -l` LIVE round-trip (verified, not assumed)

```bash
/usr/bin/tmux new-session -d -s voicetest_x
/usr/bin/tmux send-keys -t voicetest_x -l -- "Hello tmux literal"
sleep 0.2
/usr/bin/tmux capture-pane -t voicetest_x -p   # → "Hello tmux literal"
/usr/bin/tmux kill-session -t voicetest_x
```
RESULT: captured `"Hello tmux literal"`. So `["/usr/bin/tmux","send-keys","-t",target,"-l","--",text]`
is correct and the `-l` flag makes the keys literal text (no key-name interpretation;
punctuation typed verbatim). This is the backend the E2E test (P1.M7.T3.S1) exercises
end-to-end with real audio, and the one S1 can smoke-test safely (it types into a
throwaway tmux pane, never into the user's focused window).

### 1.2 ydotool `type` argument form (verified via man page + parsing probe)

- `ydotool type --help` shows `-d, --key-delay=N`.
- `man ydotool` documents the SPACE form: `type [-d,--key-delay <ms>] [-f,--file <filepath>] "text"`.
- GNU argp (ydotool's parser) accepts BOTH `--key-delay 2` and `--key-delay=2`.
- Probe: `ydotool type --key-delay notanumber` printed Usage (the value was consumed
  as the option arg; no typing occurred because no string remained). → space form is
  accepted. NOTE: `notanumber` was NOT typed — it was parsed as the delay value and
  rejected, so the space form is safe.
- CONCLUSION: `["ydotool","type","--key-delay","2","--",text]` (PRD §4.3 verbatim) is
  correct. The unit tests (P1.M3.T1.S2) MOCK subprocess.run so they assert the exact
  command LIST; the real execution is validated by the E2E test (P1.M7.T3.S1).

### 1.3 wtype argument form

`wtype` treats non-option args as text to type. `wtype -- "text"` uses `--` so text
beginning with `-` is treated as literal text, not an option. This is defensive and
correct. (`wtype` has no `-l`-style flag; the `--` separator is the standard guard.)

---

## 2. Permissions / environment

| Fact | Value | Relevance |
|---|---|---|
| user groups | `groups=...,994(input),985(video)` | ydotool uinput access works (user is in `input`). |
| `/dev/uinput` | `crw-rw-rw-+ ... input` | world/group-writable; ydotool type works without root. |
| `ydotoold` service | **`inactive`** (item text says "already running") | DISCREPANCY — see §2.1. |

### 2.1 ydotoold inactive — DOES NOT affect this task

The item description states "ydotoold already running as user service"; `systemctl
--user is-active ydotoold` returns `inactive` at research time. This is an
ENVIRONMENT/install concern, NOT a backend-code concern:

- `typing_backends.py` only runs `subprocess.run(["ydotool","type",...])`.
- ydotool 1.x auto-spawns its socket daemon if `ydotoold` isn't running (it prints a
  notice and starts one). So the call still works; at worst there is a one-time startup
  latency on first ydotool invocation.
- STARTING `ydotoold` is the job of `install.sh` (P1.M6.T1.S1) + the systemd unit
  (P1.M6.T1.S2, `After=ydotool.service`), and the E2E test (P1.M7.T3.S1) ensures it.
- S1 must NOT start services, edit systemd, or run install.sh — it only ships the Python
  module. The README troubleshooting (P2.M1.T2.S1) + install.sh cover the wtype-vs-ydotool
  story. So the discrepancy is noted here for awareness; it does NOT change the S1 contract.

---

## 3. subprocess semantics (verified live)

```python
r = subprocess.run(['false'])            # exit 1, no raise -> r.returncode == 1
subprocess.run(['false'], check=True)    # -> raises CalledProcessError(returncode=1)
subprocess.run(['missing-bin-xyz'], check=True)  # -> raises FileNotFoundError
```

- **Detecting nonzero exit requires `check=True`** (or manual returncode inspection).
  The auto-fallback contract ("on subprocess non-zero exit / FileNotFoundError") needs
  to DETECT nonzero exit, so the concrete backends use `check=True` (the idiomatic way).
  PRD §4.3 lists `subprocess.run([...])` (the command list); `check=True` is ADDED to
  make nonzero detection possible for the wrapper — it does not change WHICH command runs.
- **`FileNotFoundError` is a subclass of `OSError`.** A missing/unusable binary raises
  `OSError` (FileNotFoundError, PermissionError, …). The wrapper therefore catches
  `(subprocess.CalledProcessError, OSError)` — OSError covers "binary missing" AND
  "binary not executable" (the item's "FileNotFoundError" is the common case).
- **stderr inherits the parent fd** (goes to journald under systemd). No capture needed;
  the wrapper logs the exception. (Capturing stderr into the warning is an optional
  refinement; not required for correctness and not in the verbatim contract.)

---

## 4. Auto-fallback design (PRD §4.3 + §8 risk "wtype fails on some window")

COMPOSITION (not inheritance hack): the concrete `WtypeBackend`/`YdotoolBackend` each do
ONE thing — run their subprocess with `check=True`, raising on failure. A wrapper
`_WtypeWithFallback` holds a primary (`WtypeBackend`) + fallback (`YdotoolBackend`)
and implements the retry-once logic. `make_backend(cfg)` returns this wrapper when
`backend == "wtype"`.

Why composition:
- Each backend is independently testable (S2 mocks `subprocess.run`).
- The wrapper accepts OPTIONAL `primary`/`fallback` `TypingBackend` instances (default =
  real backends) so S2 can inject fakes to assert fallback ordering without depending on
  subprocess.run's call sequence.
- One retry only. If the fallback (ydotool) ALSO raises, the exception PROPAGATES to the
  caller (the daemon logs/handles it). We never silently swallow a total failure.

Exception catch set: `(subprocess.CalledProcessError, OSError)`.
- `CalledProcessError` = nonzero exit (the §8 "wtype fails" risk).
- `OSError` ⊇ `FileNotFoundError` = binary missing (the "wtype not installed" case).
- Anything else (e.g., a bug raising `TypeError`) is NOT caught — let it surface loudly.

---

## 5. Thread safety (on_final callback)

`type_text` is called from the daemon's `on_final` callback (P1.M4.T1.S2), which
RealtimeSTT invokes on its own thread. Requirements met WITHOUT locking:

- Backends hold **no shared mutable state**. `TmuxBackend` stores one immutable
  `_tmux_target` str at construction; `WtypeBackend`/`YdotoolBackend` are stateless.
- `subprocess.run` is reentrant: each call spawns an independent child process; there is
  no global resource contention.
- The daemon serializes `on_final` calls (one finalized utterance at a time), so no two
  `type_text` calls overlap in practice. Even if they did, each is an independent child
  process. → no lock, no thread-local needed. Documented in the module docstring.

---

## 6. Purity / importability

`typing_backends.py` is **GPU-free and pure-stdlib** (+ the OutputConfig import):

- imports: `subprocess`, `logging`, `abc` (ABC + abstractmethod), `from voice_typing.config import OutputConfig`.
- does NOT import cuda_check / torch / ctranslate2 / realtimestt.
- → loads in CPU-only + test contexts; S2 unit tests mock `subprocess.run`.

This matches the purity rule established by `config.py` and `textproc.py`.

---

## 7. Scope boundaries (S1 vs S2)

| | S1 (THIS task) | S2 (NEXT task) |
|---|---|---|
| Deliverable | `voice_typing/typing_backends.py` (impl only) | `tests/test_typing_backends.py` (pytest, subprocess.run mocked) |
| Validates via | py_compile + import + manual smoke (real tmux round-trip + factory wiring) | committed pytest suite: command lists, factory dispatch, auto-fallback ordering |
| Tests file | NONE (do NOT create `tests/test_typing_backends.py`) — S2 owns it | the committed unit tests |

S1 must NOT create a test file (S2 owns tests). S1's validation is the manual smoke in
the PRP's Validation Loop L1 + L3 (no committed test file). This mirrors how the plan
deliberately split M3.T1 into S1 (impl) + S2 (tests), unlike M2.T2 which bundled both.

---

## 8. make_backend signature — takes OutputConfig, NOT VoiceTypingConfig

Item INPUT: "OutputConfig(backend, tmux_target, append_space) from P1.M2.T1.S1".
So `make_backend(cfg: OutputConfig) -> TypingBackend`. The daemon calls it as
`typing_backends.make_backend(cfg.output)`. `append_space` is the DAEMON's concern
(on_final appends " " when true) — make_backend reads only `backend` + `tmux_target`.
This matches the P1.M2.T1.S1 PRP integration note ("typing_backends (cfg.output)").

`OutputConfig` confirmed in `voice_typing/config.py` (read directly): fields
`backend: str = "wtype"`, `tmux_target: str = ""`, `append_space: bool = True`. ✓

---

## 9. Verbatim command lists (the contract — pin exactly)

```python
# WtypeBackend
subprocess.run(["wtype", "--", text], check=True)
# YdotoolBackend
subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text], check=True)
# TmuxBackend (tmux_target from cfg)
subprocess.run(["/usr/bin/tmux", "send-keys", "-t", tmux_target, "-l", "--", text], check=True)
```

`check=True` is the only addition to the PRD §4.3 command lists; it is REQUIRED for the
auto-fallback to detect nonzero exit (see §3). Everything else is byte-for-byte PRD §4.3.

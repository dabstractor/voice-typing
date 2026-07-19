# Gap Report — P1.M3.T2.S2: voicectl CLI (ctl.py) vs PRD §4.8 / §4.2bis / §4.2ter

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/ctl.py` against PRD §4.8 (the voicectl command surface) + §4.2bis (the
`loading models…` hint on the first arm) + §4.2ter (lite mode: `toggle-lite`/`start-lite`) — the 5 item
checks (a)-(e) + Mode A docs (the `__doc__` + argparse help list all 7 commands) — and re-run the
pure-Python unit suite (`tests/test_voicectl.py`). Subtask **P1.M3.T2.S2** of verification round
`006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/ctl.py` — `_COMMANDS` (`:37`), `format_result` (`:48`-`103`), `send_command`
  (`:106`-`122`), `_send_command_with_loading_hint` (`:125`-`144`), `_build_parser`
  (`:147`-`165`), `main` (`:168`-`213`), module `__doc__` (`:1`-`26`), `_EX_USAGE=64`
  (`:40`), `_LOADING_HINT_DELAY=0.3` (`:45`).
- `tests/test_voicectl.py` — the 404-line suite (the contract's run command); 3 layers + 2 feature
  sections; NO RealtimeSTT/CUDA/real daemon (socket round-trips use `_StubDaemon`; import purity runs in
  a fresh subprocess).
- `pyproject.toml` — `[project.scripts]` (`:16`-`18`): the `voicectl` console-script entry point.
- `.venv/bin/voicectl` — the installed console script (live `--help` probe corroborates the entry point).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.8, §4.2bis, §4.2ter, §7#6 (the contract).

**Bottom line:** ✅ `ctl.py` is **COMPLIANT** with PRD §4.8 / §4.2bis / §4.2ter — all 5 checks (a)-(e)
+ Mode A docs hold, each mapped to a `ctl.py`/`pyproject.toml` file:line and a pinning test, and the
suite is green (32 passed). **No source files were modified** — the CLI faithfully implements the spec, including
the documented exit-64 (EX_USAGE) extension that keeps exit 2 exclusive to "daemon not running". The
four non-blocking observations (the VT-001 scope boundary; loading-hint routing tested via `start` only;
the entry point being a packaging declaration; the exit-64 extension) are recorded in §4 so they are not
mistaken for defects.

---

## 1. Method

Each of the 5 item checks (a)-(e) + Mode A docs was mapped 1:1 to its `ctl.py`/`pyproject.toml`
implementation by `grep -n` (the file:line evidence), and the exit-2 / exit-64 paths were checked
directly. The entry point (e) was corroborated by the LIVE installed script (`.venv/bin/voicectl
--help`). The full `tests/test_voicectl.py` suite was then **re-run live** to record the actual pass
count and timing. Nothing was assumed from the PRP's embedded numbers — every line number + the pass
count below was re-verified this round (pure stdlib: argparse/json/socket/sys/threading + the shared
`_default_control_socket_path`; no GPU/daemon required).

### Commands run (re-verification)

```bash
# (a-e + Mode A) Line-number map (grep -n)
grep -nE '_COMMANDS.*=|_EX_USAGE|_LOADING_HINT_DELAY' voice_typing/ctl.py
grep -nE 'if cmd == "status"|mode = response|phase = response|models_loaded = response|loaded_marker' voice_typing/ctl.py
grep -nE 'if cmd in ("start"|_send_command_with_loading_hint|loading models' voice_typing/ctl.py
grep -nE 'return 2|except OSError|except RuntimeError|_default_control_socket_path' voice_typing/ctl.py
grep -nE 'epilog=|help="toggle|def __doc__|^"""voicectl' voice_typing/ctl.py
grep -nE 'voicectl = "|voice-typing-daemon = "' pyproject.toml
# (e) live entry-point corroboration
.venv/bin/voicectl --help >/dev/null 2>&1 && echo "voicectl --help exit 0"
# the unit suite (the contract's run command), LIVE
.venv/bin/python -m pytest tests/test_voicectl.py -q
```

### Observed output (abridged — re-verified live this round)

```
(a) 37:_COMMANDS = ("toggle","start","stop","status","quit","toggle-lite","start-lite")
(b) 66:if cmd == "status":  69:mode = response.get("mode","normal")  68:phase = response.get("phase","") or ""
    77:models_loaded = response.get("models_loaded", False)  87:loaded_marker = "loaded" if models_loaded else "not loaded"
    90:f"mode: {mode}\n"  92:f"phase: {phase}\n"  96:f"models: {final_model} + {realtime_model} ({loaded_marker})\n"
(c) 199:if cmd in ("start", "toggle", "start-lite", "toggle-lite"):  200:response = _send_command_with_loading_hint(socket_path, cmd)
    137:lambda: print("loading models… (first arm, ~1–3 s)", file=sys.stderr, flush=True)  45:_LOADING_HINT_DELAY: float = 0.3
(d) 189:except RuntimeError: ... 191:return 2   203:except OSError as exc: ... 205:return 2
(e) pyproject.toml:17:voicectl = "voice_typing.ctl:main"   live: .venv/bin/voicectl --help exit 0
(Mode A) 12-20:subcommand block lists 7  22:Usage lists 7  158:epilog lists 7  163:cmd help lists 7
................................                                         [100%]
32 passed in 2.18s
```

---

## 2. Per-check Compliance Table (PRD §4.8 / §4.2bis / §4.2ter vs `ctl.py`)

| # | PRD requirement | Expected (spec) | `ctl.py` / `pyproject.toml` actual | file:line | Pinning tests (`tests/test_voicectl.py`) | Verdict |
|---|---|---|---|---|---|---|
| **(a)** | All 7 commands present (`toggle`/`start`/`stop`/`status`/`quit`/`toggle-lite`/`start-lite`) | `_COMMANDS` tuple with exactly those 7 (§4.8 + §4.2ter lite pair) | `_COMMANDS = ("toggle","start","stop","status","quit","toggle-lite","start-lite")` | `ctl.py:37` | `test_help_surfaces_list_all_seven_commands` `:387` (asserts `set(ctl._COMMANDS)==seven`); `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` `:75` | ✅ |
| **(b)** | `status` pretty-prints `phase` / `models_loaded` / `mode` (§4.8 + §4.2bis + §4.2ter) | multi-line: listening, mode, phase, partial, last, uptime, device, models (loaded marker), mic (+ load error) | `if cmd=="status":` branch renders `mode:` (from `response.get("mode","normal")`), `phase:`, `models: <f> + <r> (<loaded\|not loaded>)` (from `models_loaded`→`loaded_marker`), + partial/last/uptime/device/mic/load_error | status branch `ctl.py:66`-`101`; mode `:69`/`:90`; phase `:68`/`:92`; models `:77`/`:87`/`:96` | `test_format_status_multiline_has_partial_and_models` `:62`; `test_format_status_shows_unloaded_state_and_load_error` `:82`; `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` `:75` (mode: lite) | ✅ |
| **(c)** | `loading models…` hint for start/toggle/start-lite/toggle-lite (§4.2bis) | the 4 ARM commands route through the hint wrapper; hint to stderr after a delay, cancelled for fast arms | `if cmd in ("start","toggle","start-lite","toggle-lite"): response = _send_command_with_loading_hint(...)`; the wrapper starts a `threading.Timer(_LOADING_HINT_DELAY=0.3)` printing `"loading models… (first arm, ~1–3 s)"` to **stderr**, cancelled in `finally` | routing `ctl.py:199`-`200`; wrapper `:125`-`144`; delay `:45`; print `:137` | `test_start_prints_loading_hint_when_arm_is_slow` `:317`; `test_start_does_not_print_loading_hint_for_fast_arm` `:331`; `test_status_and_stop_do_not_print_loading_hint` `:340` | ✅ |
| **(d)** | exit 2 when daemon not running (socket refused / XDG unset) | `RuntimeError` (XDG unset) AND connect `OSError` (FileNotFoundError/ConnectionRefusedError/PermissionError) → stderr msg + `return 2` | `_default_control_socket_path()` `RuntimeError` → `return 2`; `send_command` connect `OSError` → `return 2` | `ctl.py:189`-`191` (RuntimeError); `:203`-`205` (OSError) | `test_main_exit2_when_socket_absent` `:196`; `test_main_exit2_when_stale_socket_no_listener` `:203`; `test_main_exit2_when_xdg_runtime_dir_unset` `:212` | ✅ |
| **(e)** | console-script entry point `[project.scripts] voicectl='voice_typing.ctl:main'` | the hatchling-generated `.venv/bin/voicectl` dispatches to `voice_typing.ctl:main` | `[project.scripts]` block: `voicectl = "voice_typing.ctl:main"`; live `.venv/bin/voicectl --help` prints argparse help (exit 0) | `pyproject.toml:17` (block `:16`-`18`) | (none — packaging declaration; corroborated by the live `--help` probe) | ✅ |
| **Mode A** | `__doc__` + argparse help list all 7 commands | the module docstring subcommand block + Usage line, AND argparse epilog + positional help, all list the 7 | docstring "Subcommands" block + Usage line; `_build_parser` epilog + `cmd` help — all list 7 | `ctl.py:12`-`20` + `:22` (doc); `:158` (epilog) + `:163` (cmd help) | `test_help_surfaces_list_all_seven_commands` `:387` (asserts all 7 in `_COMMANDS` + `format_help()` + `__doc__`) | ✅ |

> All checks **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this
> round. The exit-code matrix (0 success / 1 logical failure / 2 daemon-not-running / 64 usage) is
> documented in §4.4.

---

## 3. Test results (the contract's run command, LIVE)

```
$ .venv/bin/python -m pytest tests/test_voicectl.py -q
................................                                         [100%]
32 passed in 2.18s
```

The suite (404 lines) has 3 layers + 2 feature sections: Layer A `format_result` (pure, canned JSON),
Layer B real-socket round-trip (`_StubDaemon` + `ControlServer`), Layer C exit-2 paths, the
argparse/structural tests, the P1.M2.T1.S2 loading-hint + load-failure section, and the P1.M1.T3.S1
help-surfaces-all-7 section. Pure stdlib — no GPU/CUDA/real daemon. Entry point (e) corroborated by the
live `.venv/bin/voicectl --help` probe (exit 0).

---

## 4. Non-defect nuances (so they are not mistaken for gaps)

### 4.1 VT-001 is daemon-side, NOT a `ctl.py` client gap (out of scope)
PRD §4.2bis says "caveat: `voicectl status` currently violates this [the daemon never imports
RealtimeSTT/torch/ctranslate2]; see BUGS.md VT-001." Two facts: (i) **BUGS.md does not exist** in the
repo (`find . -name BUGS.md` → none) — the reference is doc drift owned by **P1.M6.T1.S2**; (ii) the
**client** `voice_typing.ctl` is import-clean: `test_ctl_module_present_and_imports_pure` (`:235`)
runs a FRESH interpreter importing only `voice_typing.ctl` and asserts NO
`RealtimeSTT`/`torch`/`ctranslate2` in `sys.modules`. The "violation" is the **daemon's** status path
(`status_snapshot → _resolved_device → cuda_check` imports ctranslate2 IN THE DAEMON PROCESS) — out of
scope for S2 (owned by P1.M2/P1.M6.T1.S2). The client itself is clean. ✅

### 4.2 Loading-hint routing is tested via `start` only (not per-command)
The routing tuple `("start","toggle","start-lite","toggle-lite")` (`ctl.py:199`) covers all 4 arm
commands, but the hint-EMISSION tests exercise `start` only (`test_start_prints_loading_hint...` `:317`,
with `_LOADING_HINT_DELAY` monkeypatched to 0.02 + a `_SlowStartStubDaemon(0.4)` so it is deterministic)
plus the stop/status negatives (`:340`). `toggle`/`start-lite`/`toggle-lite` route through the same
one-line `if cmd in (...)` membership, so their routing is implicit (not a separate test). Not a defect —
the routing is a single set-membership check proven by `start`; the negatives prove stop/status/quit do
NOT route through it.

### 4.3 The entry point (e) is a packaging declaration — verified by inspection, not pytest
`[project.scripts] voicectl = "voice_typing.ctl:main"` (`pyproject.toml:17`) is a Hatchling build
declaration; no unit test asserts it (it produces the `.venv/bin/voicectl` console script at install).
Verified by reading `pyproject.toml:16`-`18` AND the live probe `.venv/bin/voicectl --help` (prints
the argparse help, exit 0). Consistent with how every round-006 audit treated packaging declarations.

### 4.4 Exit 64 (EX_USAGE) is a documented extension beyond PRD §4.8's "0/1/2"
PRD §4.8 specifies exit 0/1 + "exit 2 if daemon not running". `ctl.py` adds **64** (BSD `sysexits.h`
`EX_USAGE`, `_EX_USAGE=64` `:40`) for unknown/missing commands, deliberately validated in `main`
(NOT argparse `choices`) so argparse's `SystemExit(2)` cannot collide with the daemon-not-running exit 2
(bugfix Issue 7). Pinning tests: `test_main_rejects_unknown_command` `:220` +
`test_main_rejects_missing_command` `:227` + the returns-int contract `test_main_returns_int` `:258`.
Documented in the docstring (`:7`-`10`) + the argparse description (`:153`-`156`). A faithful,
documented enhancement, NOT a deviation.

---

## 5. Conclusion

**PASS.** `voice_typing/ctl.py` is compliant with PRD §4.8 / §4.2bis / §4.2ter on all 5 item checks
(a)-(e) + Mode A docs. The CLI surface — 7 commands, status rendering (mode/phase/models_loaded/...),
the client-side `loading models…` hint on a cold arm, the exit-2 daemon-not-running paths, the
exit-64 usage extension, and the console-script entry point — all hold, each pinned by a
`tests/test_voicectl.py` test (except the packaging entry point, corroborated live) and re-verified
live this round. **No source files were modified** (read-only audit); the sole artifact is this report.
Scope is the `ctl.py` client only — the daemon-side control socket is P1.M3.T2.S1 (`gap_socket.md`),
`status.sh` is P1.M3.T2.S3, and the VT-001 daemon-side doc-drift is P1.M6.T1.S2.
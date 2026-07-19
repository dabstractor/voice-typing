# Research — P1.M3.T2.S2: voicectl CLI audit (ctl.py) vs PRD §4.8 / §4.2bis / §4.2ter

Ground truth verified by reading the LIVE `voice_typing/ctl.py` (219 lines), `tests/test_voicectl.py`
(404 lines), `pyproject.toml`, the PRD (§4.8, §4.2bis, §4.2ter, §7 acceptance #6/#10), the sibling S1
PRP (`plan/006_862ee9d6ef41/P1M3T2S1/PRP.md` → `gap_socket.md`), and the gap-report format template
(`gap_typing.md`) on 2026-07-18.

This is the **CLIENT-side** control-plane audit (P1.M3.T2.S2). S1 (parallel) audits the DAEMON-side
control socket (`gap_socket.md`); THIS task audits the `ctl.py` CLI and produces `gap_voicectl.md`.
Both are **READ-ONLY audits**: the deliverable is a report file; NO source code is modified.

---

## 0. VERIFIED VERDICT: ctl.py is COMPLIANT on all 5 item checks (a)-(e) + Mode A docs

The audit's job is to **re-confirm this live** (re-grep + re-read + re-run the suite) and document it
with file:line evidence + pinning tests, mirroring `gap_typing.md`/`gap_socket.md`. If a check
surprisingly fails on re-read, document it as a real gap for a SEPARATE remediation task (this audit
does NOT fix code — consistent with S1 + every other round-006 audit).

---

## 1. The contract checks → ctl.py file:line → ✅ verdict → pinning test

### (a) All 7 commands in `_COMMANDS`
- **ctl.py:37** — `_COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit", "toggle-lite", "start-lite")`. Exactly 7, matching PRD §4.8's command list (toggle/start/stop/status/quit) PLUS the lite pair (§4.2ter: toggle-lite/start-lite).
- **Pin tests**: `test_help_surfaces_list_all_seven_commands` (test_voicectl.py:339 — asserts `set(ctl._COMMANDS) == seven`); `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` (:75 — asserts lite ⊂ _COMMANDS).
- ✅ COMPLIANT.

### (b) `status` pretty-prints phase / models_loaded / mode (PRD §4.8)
- **ctl.py:66-101** — the `if cmd == "status":` branch. `mode:` rendered (:90, from `response.get("mode","normal")` :69 — PRD §4.2ter); `phase:` rendered (:91, from `response.get("phase","")` :68 — PRD §4.2bis); `models: <final> + <realtime> (<loaded|not loaded>)` rendered (:96, from `models_loaded` :77 → `loaded_marker` :87 — PRD §4.8 "models loaded"). Also: partial (:92), last_final (:93), uptime (:94), device+compute_type (:95), final_model+realtime_model (:96), mic (:97, from mic_ok/mic_error :79-86), and a conditional `load error:` (:99-100).
- **Pin tests**: `test_format_status_multiline_has_partial_and_models` (:62 — asserts mode/phase/models/partial/device/uptime); `test_format_status_shows_unloaded_state_and_load_error` (:82 — phase:unloaded + (not loaded) + load error); `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` (:75 — mode: lite).
- ✅ COMPLIANT.

### (c) Loading hint prints for start/toggle/start-lite/toggle-lite
- **ctl.py:199-200** — `if cmd in ("start", "toggle", "start-lite", "toggle-lite"): response = _send_command_with_loading_hint(socket_path, cmd)`. All 4 ARM commands route through the hint wrapper; stop/status/quit use plain `send_command` (:201-202).
- **The hint itself**: `_send_command_with_loading_hint` (:125-144) starts a `threading.Timer(_LOADING_HINT_DELAY=0.3, ...)` (:135-138) that prints `"loading models… (first arm, ~1–3 s)"` to **stderr** (so stdout stays clean for scripts); cancelled in `finally` (:143-144) so a fast/resident arm never prints it (no flicker).
- **Pin tests** (the P1.M2.T1.S2 section, :262-356): `test_start_prints_loading_hint_when_arm_is_slow` (:319 — monkeypatches `_LOADING_HINT_DELAY=0.02` + `_SlowStartStubDaemon(0.4)` → asserts `"loading models" in err`); `test_start_does_not_print_loading_hint_for_fast_arm` (:333 — resident arm → no hint); `test_status_and_stop_do_not_print_loading_hint` (:342 — stop/status never use the wrapper). **Deterministic** (the slow path uses a monkeypatched tiny delay + a stub that sleeps 0.4s — no real-timing flakiness).
- ✅ COMPLIANT. (Nuance §4.2: the routing tuple covers all 4 arm commands, but the hint-emission tests exercise `start` only; `toggle`/`start-lite`/`toggle-lite` routing is implicit via the shared `if cmd in (...)` membership. Not a defect — the routing is one line, and `start` proves it.)

### (d) Exit 2 when daemon not running (socket connection refused)
- **ctl.py:187-191** — `_default_control_socket_path()` raises `RuntimeError` when `XDG_RUNTIME_DIR` is unset → caught → `"voicectl: daemon not running (XDG_RUNTIME_DIR is not set)"` to stderr → `return 2`.
- **ctl.py:203-205** — `send_command()`'s `sock.connect()` raises `FileNotFoundError`/`ConnectionRefusedError`/`PermissionError` (all `OError` subclasses) → caught → `"voicectl: daemon not running (...)"` to stderr → `return 2`.
- **Pin tests** (Layer C, :194-215): `test_main_exit2_when_socket_absent` (:196 — path resolves, file absent → FileNotFoundError → exit 2); `test_main_exit2_when_stale_socket_no_listener` (:203 — stale file present, nothing listening → ConnectionRefusedError → exit 2); `test_main_exit2_when_xdg_runtime_dir_unset` (:212 — RuntimeError → exit 2). All assert `code == 2 and "not running" in err`.
- ✅ COMPLIANT.

### (e) Console-script entry point: `[project.scripts] voicectl='voice_typing.ctl:main'`
- **pyproject.toml:16-18** — `[project.scripts]` block: `voicectl = "voice_typing.ctl:main"` (:17) + `voice-typing-daemon = "voice_typing.daemon:main"` (:18). Hatchling build backend (:1-3) generates the `.venv/bin/voicectl` console script from this.
- **Verification**: this is a PACKAGING declaration, not a pytest assertion. Verify by (i) reading pyproject.toml :16-18, AND (ii) confirming the installed script exists + dispatches to `main`: `.venv/bin/voicectl --help` (prints the argparse help, exit 0) OR `head -1 .venv/bin/voicectl` (the hatchling-generated shebang + `from voice_typing.ctl import main`). No pytest pins it (it's a build artifact).
- ✅ COMPLIANT. (Nuance §4.3: the entry point is verified by inspection/live `--help`, not a unit test — consistent with how every round-006 audit treated packaging declarations.)

### Mode A docs — `__doc__` + help text list all 7 commands
- **ctl.py:1-26** — module docstring. The "Subcommands (PRD §4.8):" block (:12-20) lists all 7 (toggle/start/stop/status/quit/toggle-lite/start-lite); the Usage line (:22) lists all 7.
- **ctl.py:147-165** — `_build_parser()`. The argparse `epilog` (:158) lists all 7; the positional `cmd` `help=` (:163) lists all 7. So `format_help()` renders all 7 in BOTH the positional help AND the epilog.
- **Pin test** (the P1.M1.T3.S1 section, :339-404): `test_help_surfaces_list_all_seven_commands` (:339) asserts all 7 appear in `ctl._COMMANDS`, `ctl._build_parser().format_help()`, AND `ctl.__doc__`. This is EXACTLY the Mode A check.
- ✅ COMPLIANT — the docs ALREADY list all 7. Mode A = verify + document; NO edit needed (the audit is read-only; ctl.py is correct).

---

## 2. Exit-code matrix (the full contract, beyond the item's "0/1/2")

ctl.py documents + implements FOUR exit codes (docstring :7-10; help :155-156):
- **0** — success (`response["ok"] is True`); format_result returns code 0.
- **1** — logical failure (`response["ok"]` not True → `format_result` :62-63 returns 1; OR protocol `ValueError` :206-208).
- **2** — daemon not running (RuntimeError :189-191 OR OSError :203-205). EXCLUSIVE to this (bugfix Issue 7).
- **64** — usage error, BSD `EX_USAGE` (`_EX_USAGE = 64` :40); unknown/missing command → `main` :179-184 returns 64 (NOT argparse's `SystemExit(2)`, which would collide with exit 2). Validated in `main` (NOT argparse `choices`) so 64 stays distinct from 2.

**Pin tests**: 0 → every Layer A/B test; 1 → `test_format_ok_false_*` (:114-126) + `test_start_load_failure_returns_ok_false_and_exit_one` (:351); 2 → Layer C (:196-215); 64 → `test_main_rejects_unknown_command` (:220) + `test_main_rejects_missing_command` (:227); returns-int contract → `test_main_returns_int` (:258).

✅ COMPLIANT. (Nuance §4.4: PRD §4.8 says "exit code 0/1" + "exit 2 if daemon not running"; ctl.py adds the documented 64 = EX_USAGE extension [bugfix Issue 7] so exit 2 stays exclusive. This is a faithful, documented enhancement, NOT a deviation — record it in §4.)

---

## 3. The gap-report FORMAT (mirror `gap_typing.md` / `gap_socket.md`)

`plan/006_862ee9d6ef41/architecture/gap_voicectl.md` is a NEW file (CREATE, like gap_socket.md).
Structure (mirror gap_typing.md exactly):
1. **Title**: `# Gap Report — P1.M3.T2.S2: voicectl CLI (ctl.py) vs PRD §4.8 / §4.2bis / §4.2ter`
2. **Date + Scope + Audited artifacts (read-only)**: `voice_typing/ctl.py`, `tests/test_voicectl.py`, `pyproject.toml`, PRD §4.8/§4.2bis/§4.2ter/§7#6.
3. **Bottom line**: ✅ COMPLIANT — all 5 checks (a)-(e) + Mode A docs hold, each mapped to a ctl.py/pyproject.toml file:line + a pinning test; the suite is green; NO source files modified.
4. **§1 Method**: the grep commands run + the live `pytest` invocation + abridged observed output (the file:line evidence + the pass count).
5. **§2 Per-check Compliance TABLE**: columns `# | PRD req | expected | ctl.py actual | file:line | pinning test | ✅`. One row per check (a)-(e) + a Mode A docs row.
6. **§3 Test results**: the LIVE pass count from `.venv/bin/python -m pytest tests/test_voicectl.py -q` (re-run this round; do NOT trust an embedded number).
7. **§4 Non-defect nuances**: the 4 nuances below (so they aren't mistaken for gaps).
8. **§5 Conclusion**: PASS; no fix.

---

## 4. The 4 NON-DEFECT nuances (document in §4)

### 4.1 VT-001 scope boundary (daemon-side, NOT a ctl.py client gap)
PRD §4.2bis implementation note says: "the daemon process is therefore intended to never import
RealtimeSTT/torch/ctranslate2 and never create a CUDA context — **caveat: `voicectl status` currently
violates this; see BUGS.md VT-001.**" Two facts resolve this for the CLIENT audit:
- **(i)** BUGS.md does NOT exist in the repo (`find . -name BUGS.md` → none). The reference is doc drift — owned by **P1.M6.T1.S2** ("Verify no stale BUGS.md/VT-* references & resolve doc drift"), NOT this audit.
- **(ii)** The CLIENT (`voice_typing.ctl`) is import-clean: `test_ctl_module_present_and_imports_pure` (:235) runs a FRESH interpreter importing only `voice_typing.ctl` and asserts NO `RealtimeSTT`/`torch`/`ctranslate2` in `sys.modules` (defense-in-depth with P1.M2.T1.S1). So the "violation" is about the **daemon's** status path (`status_snapshot → _resolved_device → cuda_check` imports ctranslate2 IN THE DAEMON PROCESS), not the ctl.py client. That is daemon-side, owned by P1.M2/P1.M6.T1.S2 — **OUT OF SCOPE for S2**. The client itself is clean. ✅

### 4.2 Loading-hint routing is tested via `start` only (not per-command)
The hint-routing tuple `("start","toggle","start-lite","toggle-lite")` (ctl.py:199) covers all 4 arm
commands, but the hint-EMISSION tests exercise `start` only (`test_start_prints_loading_hint...` :319)
+ the stop/status negatives (:342). `toggle`/`start-lite`/`toggle-lite` route through the same one-line
`if cmd in (...)` membership, so their routing is implicit (not a separate test). Not a defect — the
routing is a single set-membership check proven by `start`; the negative tests prove stop/status/quit
do NOT route through it. Record so it isn't mistaken for a coverage gap.

### 4.3 The entry point (e) is a packaging declaration — verified by inspection, not pytest
`[project.scripts] voicectl = "voice_typing.ctl:main"` (pyproject.toml:17) is a Hatchling build
declaration; no unit test asserts it (it produces the `.venv/bin/voicectl` console script at install).
Verify by reading pyproject.toml :16-18 AND confirming the installed script dispatches to `main`
(`.venv/bin/voicectl --help` prints the argparse help; or `head -1 .venv/bin/voicectl` shows the
hatchling entry-point line). Consistent with how every round-006 audit treated packaging declarations.

### 4.4 Exit 64 (EX_USAGE) is a documented extension beyond PRD §4.8's "0/1/2"
PRD §4.8 specifies exit 0/1 + "exit 2 if daemon not running". ctl.py adds **64 (BSD `sysexits.h`
EX_USAGE)** for unknown/missing commands (ctl.py:40, 179-184), deliberately validated in `main` (NOT
argparse `choices`) so argparse's `SystemExit(2)` can't collide with the daemon-not-running exit 2
(bugfix Issue 7; test `test_main_rejects_unknown_command` :220 + `test_main_rejects_missing_command`
:227). This is a faithful, documented enhancement (docstring :10, help :155-156), NOT a deviation.

---

## 5. The test suite (`tests/test_voicectl.py`, 404 lines) — coverage map

Three layers + two feature sections (the contract's run command: `.venv/bin/python -m pytest tests/test_voicectl.py -q`):
- **Layer A — `format_result` (pure; canned JSON)** (:39-126): toggle/start/stop/quit; status multiline (mode/phase/models/partial/device/uptime); lite accepted + mode:lite; unloaded + load_error; mic ok/unavailable/default-healthy; ok:false (unknown/malformed/missing-error).
- **Layer B — real-socket round-trip** (live `ControlServer` + `_StubDaemon`) (:129-191): status; toggle→status; quit.
- **Layer C — exit-2 paths** (:194-215): socket absent; stale socket no listener; XDG unset.
- **argparse/structural** (:218-260): unknown→64; missing→64; import purity (fresh subprocess, no heavy-dep leak); main returns int.
- **P1.M2.T1.S2 — loading hint + load-failure** (:262-356): slow-arm hint; fast-arm no-hint; status/stop no-hint; start load-failure→ok:false+exit1; `_dispatch` start/toggle load-failure→ok:false; `_dispatch` start ok:true (duck-type guard). Stubs: `_SlowStartStubDaemon`, `_FailingLoadStubDaemon`.
- **P1.M1.T3.S1 — help surfaces all 7** (:339-404): `_COMMANDS` == 7; `format_help()` lists 7; `__doc__` lists 7.

NO RealtimeSTT/CUDA/real daemon (the socket round-trips use `_StubDaemon`; import purity runs in a
fresh subprocess). Re-run live + record the count (the PRP does not hard-code it).

---

## 6. Scope boundaries (S2 vs siblings)

- **P1.M3.T2.S1** (parallel, `gap_socket.md`): the DAEMON-side control socket (`ControlServer`/`_dispatch`/`status_snapshot`/`_arm_response`). DISJOINT from S2 (the client). No file conflict (gap_socket.md vs gap_voicectl.md).
- **P1.M3.T2.S3** (`status.sh`): the tmux status helper. NOT ctl.py. Separate.
- **P1.M2.*** / **P1.M6.T1.S2**: the daemon's lifecycle / recorder-host / VT-001 doc-drift. The VT-001 caveat is daemon-side (nuance §4.1), out of scope for the client audit.
- **S2 edits ONLY** `plan/006_862ee9d6ef41/architecture/gap_voicectl.md` (CREATE). NO source/test/doc edits (ctl.py is compliant; the audit is read-only).

---

## 7. Tooling + validation reality
- pytest is the gate: `.venv/bin/python -m pytest tests/test_voicectl.py -q` (FULL PATH — zsh aliases python/pytest). Pure stdlib (argparse/json/socket/sys/threading + the shared `_default_control_socket_path`); no GPU/CUDA/daemon. Runs in <1s.
- The entry-point check (e) needs `.venv/bin/voicectl --help` (or `head -1 .venv/bin/voicectl`) — a live CLI probe, not pytest.
- mypy NOT installed (skip). ruff at `/home/dustin/.local/bin/ruff` is OPTIONAL (not in .venv; not a gate; ctl.py is already clean).
- The gap report goes in `plan/006_862ee9d6ef41/architecture/` (same dir as gap_socket.md/gap_typing.md/gap_feedback.md).
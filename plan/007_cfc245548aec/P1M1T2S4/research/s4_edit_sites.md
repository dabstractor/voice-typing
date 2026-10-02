# Research Note — P1.M1.T2.S4: Prefetch slim-down, bind collapse, ACCEPTANCE #10 rewrite

Verified against the live tree. Inputs: S2 research (`P1M1T2S2/research/mode_collapse_edit_sites.md`
§7 downstream: "S4 owns prefetch.py CORE_REPOS + hypr-binds.conf:52 + ACCEPTANCE #10"), S3's PRP
(`P1M1T2S3/PRP.md` — 5-command ctl surface, parallel; its scope note: "hypr-binds.conf:52 +
test_config_repo_default.py:56 are S4's; prefetch is S4's").

## 1. prefetch.py (voice_typing/prefetch.py, 157 lines)

- `CORE_REPOS` @36-40: 3 entries — `distil-large-v3` @37 (DELETE), `small.en` @38 (KEEP — sole
  model), `tiny.en` @39 (KEEP — CPU fallback via cuda_check S1 contract).
- `OPTIONAL_REPOS` @43-47: turbo entry (DELETE dict entirely; note mobiuslabsgmbh owner trap dies
  with it).
- Module docstring @1-29: rewrite. Currently claims "all four repos local, CUDA path (distil-large-v3
  + small.en), approved substitute (large-v3-turbo)". End state: 2 repos — small.en (the single
  model, Rev 2 §4.2ter-style single-mode collapse) + tiny.en (CPU-fallback). Drop the
  distil-whisper raw-PyTorch trap note only if the distil mention goes entirely (turbo note goes);
  keep HF-cache rationale, lazy-import note, install.sh caller note.
- `prefetch()` @50: default arg merge `{**CORE_REPOS, **OPTIONAL_REPOS}` → `dict(CORE_REPOS)` (or
  `CORE_REPOS.copy()`).
- `_main()` @103-151: delete the OPTIONAL loop (opt_ok/opt_fail, @134-143), summary `opt ok/ opt warn`
  lines, the `opt_fail` NOTE block, and the "(turbo)" mentions in the docstring @105-109. Core loop /
  exit-by-core semantics unchanged. `total` loop uses `{**CORE_REPOS, **OPTIONAL_REPOS}[short]`
  → `CORE_REPOS[short]`.
- No test file imports prefetch / CORE_REPOS (grep over tests/*.py: zero hits). No unit test needed
  per contract (docs/substrate task); validation = grep + import + `--help`-style smoke via
  `python -c "import voice_typing.prefetch as p; print(sorted(p.CORE_REPOS))"`.

## 2. hypr-binds.conf (52 lines + header)

- Line 52 (`bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite`): DELETE.
- Line 50 (`bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle`): KEEP (the one bind).
- Header @1-48 rewrite to end state: ONE bind, Ctrl+Alt+Super+D → toggle, single small.en model
  (live partials + finals from the same model, streaming Rev 2). Delete all lite/two-mode prose
  (:4-6, :29-35). KEEP: the source-don't-copy integration block (:10-27), VT-003 $HOME launcher
  note (:21-27), precedence/conflicts block (:37-43), mods-syntax block (:45-47) — test
  `test_hypr_binds_use_portable_home_launcher` (tests/test_systemd_unit.py:321-332) reads every
  `bind =` line and requires `$HOME/.local/bin/voicectl` + no `/home/`; it stays green as long as
  the remaining bind is untouched.
- ADD a placeholder comment where the cancel bind will go: `# (P1.M2.T7.S1) bind = SUPER ALT,
  Backspace, exec, $HOME/.local/bin/voicectl cancel   # cancel fallback — ADDED by P1.M2.T7.S1`
  (commented-out, NOT a live bind — cancel doesn't exist in ctl until T7.S1).

## 3. install.sh

- :209 `usage : ... toggle|start|stop|status|quit|toggle-lite|start-lite` → drop the two lite cmds
  (5 commands, matching S3's `_COMMANDS`).
- :210 bind hint `(bind Ctrl+Alt+Super+D -> voicectl toggle;  Alt+Super+D -> voicectl toggle-lite;
  see the Hyprland note below)` → drop the Alt+Super+D clause (or replace with the single-bind
  phrasing; T7.S1 appends the cancel bind mention later).
- :100-104 (prefetch invocation `"$PY" -m voice_typing.prefetch`): NO text change — output shrinks
  automatically once prefetch.py is slimmed.
- :19 comment, :205 daemon line: already correct (`voicectl toggle` arming) — untouched.
- TEST THAT GOES RED: `tests/test_systemd_unit.py::test_install_sh_usage_lists_all_commands_and_correct_keybinds`
  @223-254 asserts `toggle-lite`/`start-lite` in install.sh text and the
  `Alt+Super+D -> voicectl toggle-lite` mapping. REWRITE it: (a) usage line lists exactly the 5
  `toggle|start|stop|status|quit`; (b) `Ctrl+Alt+Super+D` still stated; (c) NEGATIVE asserts:
  `toggle-lite`, `start-lite`, and `Alt+Super+D` not in the usage block; (d) docstring updated.
  Sibling tests in the same file (VT-003 blocks @257-332, offline @~200-220) unaffected.

## 4. tests/ACCEPTANCE.md

- Row #4 @35: criterion text "Only finalized text reaches the target; nothing typed while toggled
  off" → Rev 2: "Only the daemon's typed output reaches the target — live partial text plus commits
  (§4.2quater); nothing typed while toggled off (listening gates unchanged)". Keep/adjust evidence
  wording (streaming evidence lands P1.M3.T8/T9 — evidence cell may reference T8 as PENDING, mirror
  how #11/#12 are deferred; keep Status honest — mark evidence as pending-streaming-tests rather
  than fabricating).
- Row #10 @41: full rewrite to the single-model form: `voicectl toggle` arms the single-model
  engine using ONLY `lite_model` (small.en sole model — the large model never loads, ~half the old
  two-model VRAM); no large-model worker; the silence gate (`lite_post_speech_silence_duration`,
  0.8 Rev 2 default) applies; graceful drain unchanged; `status`/`state.json` still report `mode`
  (constant "lite"). Evidence: existing single-model LIVE tests + the mode-collapse suite (S1/S2/S3
  landed) — cite `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` still valid; VRAM evidence
  regenerates with T9.S1's updated `test_idle_and_gpu.sh` (rows #11/#12 land with P1.M3.T9.S1).
- Keep rows #1-#3, #5-#9 verbatim. Line 3 header text "criteria 1–10" and the intro/regeneration
  prose may mention rows 5/6/8/9/10 blocks — leave the evidence fenced block as a historical
  capture (it is verbatim from an older passing run; T9.S1 owns regeneration). The `models:
  distil-large-v3 + small.en (loaded)` line @68 inside the fenced historical block is fine (it is
  quoted output, not a live claim).
- No test greps ACCEPTANCE.md content (grep found none).

## 5. NOT S4's (scope fence)

- `tests/test_idle_and_gpu.sh` T7 lite-mode sections (:536-590) → P1.M3.T9.S1.
- README → P1.M3.T10.S1. `tests/test_config_repo_default.py:56` already end-state (landed T1.S1).
- ctl.py/daemon.py → S3/S2. `cancel` anywhere → P1.M2.T7.S1. config.toml → T1.S1 (settled).
- test_daemon.py:3818-3824 (lite-unknown dispatch) → S2's, landed.

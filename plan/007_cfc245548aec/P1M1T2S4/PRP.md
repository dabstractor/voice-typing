# PRP — P1.M1.T2.S4: Prefetch slim-down, bind collapse, ACCEPTANCE #10 rewrite

## Goal

**Feature Goal**: Finish the single-mode collapse at the install/substrate layer: prefetch exactly
**2 models** (`small.en` sole model + `tiny.en` CPU fallback), collapse hypr-binds.conf to **one
toggle bind** with end-state header docs (plus a commented placeholder for the future cancel bind),
drop the lite commands from install.sh's printed usage, and rewrite tests/ACCEPTANCE.md rows
**#4** and **#10** to the Rev 2 single-model form.

**Deliverable** (4 files modified + 1 test file updated, no new files):
1. `voice_typing/prefetch.py` — `CORE_REPOS` = 2 entries; `OPTIONAL_REPOS` + all `_main()` optional/
   turbo handling deleted; module docstring rewritten.
2. `hypr-binds.conf` — line :52 (SUPER ALT, D → toggle-lite) deleted; header :1-48 rewritten to the
   one-bind end state; commented placeholder for the P1.M2.T7.S1 cancel bind.
3. `install.sh` — usage lines :209-210 drop `toggle-lite`/`start-lite` and the lite-bind mention.
4. `tests/ACCEPTANCE.md` — row #4 amended (typed output = live partials + commits), row #10
   rewritten to single-model form; rows #1-#3, #5-#9 untouched.
5. `tests/test_systemd_unit.py` — rewrite `test_install_sh_usage_lists_all_commands_and_correct_keybinds`
   (@223-254) to the 5-command / one-bind expectation (it would otherwise go RED against the new
   install.sh).

**Success Definition**:
- (a) `python -c "import voice_typing.prefetch as p; print(sorted(p.CORE_REPOS))"` →
  `['small.en', 'tiny.en']`; `grep -c 'OPTIONAL_REPOS\|turbo\|distil' voice_typing/prefetch.py` → 0.
- (b) `grep -c '^bind =' hypr-binds.conf` → 1 (CTRL SUPER ALT, D → toggle); zero `lite` mentions in
  the file; a `# (P1.M2.T7.S1)` commented cancel-bind placeholder exists; the surviving bind still
  uses `$HOME/.local/bin/voicectl` (VT-003 test stays green).
- (c) `grep -c 'toggle-lite\|start-lite\|Alt+Super+D' install.sh` → 0.
- (d) ACCEPTANCE.md row #10 describes single-model arming only (no toggle-lite, no mode-switch, no
  0.5 default); row #4 says "live partial text plus commits"; rows #1-#3/#5-#9 byte-identical.
- (e) `timeout 600 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` → 0 failures, and the
  full fast suite green:
  `timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py`.
- (f) `git diff --name-only` ⊆ {voice_typing/prefetch.py, hypr-binds.conf, install.sh,
  tests/ACCEPTANCE.md, tests/test_systemd_unit.py}.

## User Persona

**Target User**: the installer / keybind user. After the Rev 2 collapse there is ONE dictation mode;
prefetching a 1.5 GB distil model that never loads, a second keybind that arms a mode that no longer
exists, and an acceptance table that describes the dead two-mode architecture are pure confusion
and wasted disk.

**Use Case**: `./install.sh` on a fresh machine → prefetches only small.en + tiny.en; user sources
hypr-binds.conf and gets exactly one dictation key (Ctrl+Alt+Super+D); tests/ACCEPTANCE.md is the
honest Rev 2 definition-of-done record.

**Pain Points Addressed**: ~1.6 GB of never-used distil-large-v3 + turbo downloads; a dead
Alt+Super+D bind; ACCEPTANCE.md promising behavior (mode switching, 0.5 silence default) the
post-S2 daemon no longer has.

## Why

- **S1/S2/S3 removed the consumers; this removes the residue.** S1's cuda_check resolves only
  `small.en` (CUDA) / `tiny.en` (CPU); S2's daemon loads one model (`cfg.asr.lite_model`); S3's
  ctl has 5 commands. prefetch's distil/turbo entries, the lite bind, and install.sh's lite usage
  advertise machinery that no longer exists.
- **PRD §7 Mode A names these exact doc surfaces** (prefetch.py docstring, hypr-binds.conf
  comments, install.sh usage lines, tests/ACCEPTANCE.md) — they ride with the work.
- **Downstream gates on this**: P1.M2.T7.S1 appends the cancel bind (placeholder reserved here);
  P1.M3.T9.S1 regenerates the ACCEPTANCE evidence and adds rows #11/#12 against the rewritten #10.

## What

- prefetch.py: `CORE_REPOS` = `{"small.en": "Systran/faster-whisper-small.en", "tiny.en":
  "Systran/faster-whisper-tiny.en"}` (tiny.en stays — CPU fallback). Delete `OPTIONAL_REPOS`, the
  `distil-large-v3` core entry, `_main()`'s optional loop/summary/NOTE, and the
  `{**CORE_REPOS, **OPTIONAL_REPOS}` merges (→ `CORE_REPOS`). Rewrite the docstring (2 repos; small.en
  = the single model used for both live partials and finals; tiny.en = CPU fallback).
- hypr-binds.conf: delete the toggle-lite bind; rewrite the header to the end state (one mode, one
  bind, streaming partials+commits); keep the integration/VT-003/precedence/mods-syntax blocks; add
  a commented `# (P1.M2.T7.S1) bind = SUPER ALT, Backspace, ... cancel` placeholder.
- install.sh: usage line → 5 commands; bind hint → Ctrl+Alt+Super+D only. The prefetch step
  (:100-104) needs no change (output shrinks via prefetch.py).
- tests/ACCEPTANCE.md: rewrite #10 / amend #4 per the exact forms below; keep everything else.

### Success Criteria

- [ ] (a)-(f) from Success Definition all hold.

## All Needed Context

### Context Completeness Check

_Pass._ All five edit targets were read in full or in the relevant regions (prefetch.py 157L read
whole; hypr-binds.conf header+binds; install.sh :85-120, :195-225; ACCEPTANCE.md rows :30-78;
test_systemd_unit.py :60-80, :215-345). The upstream contracts (S2's daemon shape, S3's 5-command
ctl) are pinned in their PRPs. An agent new to the repo can implement from this PRP + the research
note alone.

### Documentation & References

```yaml
# MUST READ — this task's verified edit-site tables (source of truth)
- docfile: plan/007_cfc245548aec/P1M1T2S4/research/s4_edit_sites.md
  why: "§1 prefetch.py sites (CORE_REPOS @36-40, OPTIONAL_REPOS @43-47, prefetch() default merge,
        _main() optional loop/summary); §2 hypr-binds.conf sites + what to KEEP; §3 install.sh :209-210
        + the test that goes red; §4 ACCEPTANCE rows #4/#10; §5 scope fence."
  critical: "§3: no test imports prefetch (grep-verified) — validation is import-smoke + grep; the
            ONLY test that breaks is test_systemd_unit.py::test_install_sh_usage_..."

# Inputs (assume landed exactly as specified)
- docfile: plan/007_cfc245548aec/P1M1T2S2/PRP.md
  why: "Single-mode daemon contract: one model via cfg.asr.lite_model, status 13-key with mode
        constant 'lite', lite dispatch arms deleted."
- docfile: plan/007_cfc245548aec/P1M1T2S3/PRP.md
  why: "ctl._COMMANDS == (toggle, start, stop, status, quit) — the 5-command surface install.sh's
        usage line must mirror. Its grep gate (a) already enforces zero lite refs in ctl.py."
- docfile: plan/007_cfc245548aec/P1M1T2S1/PRP.md
  why: "cuda_check 3-key contract: CUDA small.en / CPU-fallback tiny.en — exactly the two repos
        CORE_REPOS must keep."

# Edit targets — read each before editing
- file: voice_typing/prefetch.py
  pattern: "Keep lazy huggingface_hub import, per-repo print format, _model_bin_size/_human_bytes/
            _local_snapshot, core-fail-fatal exit semantics. Only the repo sets + docstring shrink."
  gotcha: "Keep HF_HUB_DISABLE_TELEMETRY setdefault and snapshot_download default kwargs (cache_dir/
           token None, force_download False) — load-bearing per the original docstring."
- file: hypr-binds.conf
  gotcha: "test_systemd_unit.py::test_hypr_binds_use_portable_home_launcher (:321) reads EVERY
           'bind =' line — the placeholder cancel bind must be a COMMENT, not a live bind line."
- file: install.sh
  pattern: "Only the two echo lines :209-210; keep the 'Hyprland — source' block and offline lines."
- file: tests/ACCEPTANCE.md
  gotcha: "Rows #1-#3/#5-#9 and the fenced historical evidence block stay verbatim — T9.S1 owns
            regeneration; do NOT 'fix' the old 'models: distil-large-v3 + small.en' line @68 (it is
            quoted historical output)."
- file: tests/test_systemd_unit.py
  pattern: "Static read_text asserts (same style as the file's other tests). Rewrite @223-254:
            positive = 5 cmds + Ctrl+Alt+Super+D; negative = toggle-lite/start-lite/Alt+Super+D
            absent from install.sh text; update the docstring."
```

### Current Codebase tree (relevant slice — S1/S2 landed; S3 parallel)

```bash
voice_typing/prefetch.py        # 4 repos → EDIT to 2
hypr-binds.conf                 # 2 binds → EDIT to 1 (+ commented cancel placeholder)
install.sh                      # 7-cmd usage → EDIT to 5
tests/ACCEPTANCE.md             # two-mode rows #4/#10 → EDIT to Rev 2
tests/test_systemd_unit.py      # install-usage test → EDIT to 5-cmd/one-bind
# Inputs landed: config.py/config.toml (T1.S1), cuda_check.py (S1), daemon.py/recorder_host.py (S2).
# Parallel: ctl.py 5-cmd surface (S3) — install.sh's usage line mirrors its _COMMANDS.
# NOT S4's: tests/test_idle_and_gpu.sh T7 lite block, README, ctl/daemon, cancel.
```

### Desired Codebase tree with files to be changed

```bash
# (the same 5 files, MODIFIED — no new files, no file deletions)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — SEQUENCING GATE (Task 0). S2 must be landed; S3 may be parallel (install.sh does not
# read ctl.py), but the usage LINE you print must equal S3's end-state _COMMANDS (5). Gate:
#   grep -q '"mode": "lite"' voice_typing/daemon.py && \
#   [ "$(grep -c 'start-lite\|toggle-lite' voice_typing/daemon.py)" -eq 0 ]
# If false, STOP and flag.

# CRITICAL #2 — THE CANCEL BIND IS A COMMENT, NOT A BIND. `cancel` does not exist in ctl until
# P1.M2.T7.S1. A live `bind = SUPER ALT, Backspace, ... voicectl cancel` would (a) break
# test_hypr_binds_use_portable_home_launcher? no — it passes VT-003 — but it WOULD ship a dead
# keybind the daemon rejects. Emit it commented with a '# (P1.M2.T7.S1)' tag.

# CRITICAL #3 — TDD: rewrite test_systemd_unit.py's install-usage test FIRST, watch it go red
# against current install.sh (it asserts lite cmds PRESENT today — flip to absent), then edit
# install.sh and watch it go green. Do not weaken the negative asserts into loose ones.

# CRITICAL #4 — ACCEPTANCE.md ROW #10 CONTENT (use this form): single-model arming —
# `voicectl toggle` arms the engine using ONLY lite_model (small.en sole model, large-model worker
# never loads, ~half the old two-model VRAM); silence gate = asr.lite_post_speech_silence_duration
# (Rev 2 default 0.8); graceful drain unchanged; status/state.json report mode (constant "lite").
# NO toggle-lite, NO mode-switch, NO "0.5" default (those claims are Rev 1). Evidence: cite the
# landed single-model suite (S1/S2) + mark T9.S1 as the VRAM-evidence regenerator. Keep the row
# honest — do not fabricate new LIVE evidence.

# CRITICAL #5 — REPO TIMEOUT RULES (AGENTS.md): every pytest/voicectl invocation wrapped in
# `timeout N`; never run the daemon in the foreground; test_idle_and_gpu.sh / e2e_virtual_mic.sh are
# NOT run by this task (T9.S1 owns them).

# CRITICAL #6 — tiny.en STAYS. It is the cuda_check CPU-fallback model; dropping it would break
# CPU-mode installs (PRD §5 install path + config.toml CPU-only doc).
```

## Implementation Blueprint

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE — verify S2 landed (CRITICAL #1 greps); read all 5 edit targets + the research note.

Task 1: EDIT tests/test_systemd_unit.py FIRST (TDD red)
  - REWRITE test_install_sh_usage_lists_all_commands_and_correct_keybinds (:223-254):
    docstring → "install.sh [7/7] usage lists the 5 commands + the single toggle keybind (Rev 2)";
    (a) assert "toggle|start|stop|status|quit" in text; (b) assert "Ctrl+Alt+Super+D" in text;
    (c) NEGATIVE: assert "toggle-lite" not in text, "start-lite" not in text,
        "Alt+Super+D" not in text; (d) keep "SUPER+ALT+D -> voicectl toggle" not-in check if it
        still makes sense (it does — wrong mapping guard).
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_systemd_unit.py -q  → expect exactly
    this ONE test red.

Task 2: EDIT voice_typing/prefetch.py
  - CORE_REPOS: delete the distil-large-v3 line; keep small.en + tiny.en with their comments
    updated (small.en = "the SINGLE model (Rev 2): partials + finals"; tiny.en = CPU fallback).
  - DELETE OPTIONAL_REPOS; prefetch() default → dict(CORE_REPOS); _main(): delete optional loop,
    opt_ok/opt_fail, "opt ok/ opt warn" summary lines, opt_fail NOTE; total loop → CORE_REPOS[short];
    docstring drops "(turbo)".
  - REWRITE module docstring: 2 repos, end-state rationale; drop distil/turbo/owner-trap prose;
    keep HF-cache + lazy-import + install.sh-caller notes.
  - SMOKE: timeout 60 .venv/bin/python -c "import voice_typing.prefetch as p; \
    assert sorted(p.CORE_REPOS)==['small.en','tiny.en']; assert not hasattr(p,'OPTIONAL_REPOS')"

Task 3: EDIT hypr-binds.conf
  - DELETE :52 (SUPER ALT, D toggle-lite). KEEP :50 unchanged.
  - REWRITE header :1-48 to one-bind end state (keep integration/VT-003/precedence/mods blocks).
  - ADD commented placeholder directly below the toggle bind:
    "# (P1.M2.T7.S1) cancel fallback bind — ADDED by that task:
    #  bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel"

Task 4: EDIT install.sh (:209-210 only)
  - usage line: "$REPO/.venv/bin/voicectl toggle|start|stop|status|quit"
  - bind line: "(bind Ctrl+Alt+Super+D -> voicectl toggle; see the Hyprland note below)"
  - RUN Task 1's test → green.

Task 5: EDIT tests/ACCEPTANCE.md
  - Row #4: criterion text → "Only the daemon's typed output reaches the target — Rev 2: live
    partial text plus commits (§4.2quater); nothing typed while toggled off (the `listening` gates
    on partial and commit paths are unchanged)". Evidence cell: keep the disarm-gate LIVE evidence,
    note streaming evidence lands with P1.M3.T8/T9.
  - Row #10: rewrite per CRITICAL #4. Keep rows #1-#3, #5-#9 and the fenced block verbatim.

Task 6: VALIDATE (below), then confirm git diff ⊆ the 5 files.
```

### Implementation Patterns & Key Details

```python
# prefetch.py end-state constants:
CORE_REPOS: dict[str, str] = {
    "small.en": "Systran/faster-whisper-small.en",  # THE single model (Rev 2): partials + finals
    "tiny.en": "Systran/faster-whisper-tiny.en",    # CPU fallback (cuda_check downgrade path)
}
# _main(): core loop + summary unchanged EXCEPT no optional section:
#   summary prints: core ok / core FAIL / total bytes; exit 1 iff core_fail.
```

### Integration Points

```yaml
INSTALL.SH: no functional change — the [3/7] prefetch step calls `python -m voice_typing.prefetch`
  which now downloads 2 repos; usage echo lines updated only.
HYPR: users who previously sourced hypr-binds.conf get the lite bind removed on next
  `hyprctl reload` — the header comment should say so (one bind now; SUPER+ALT+D is free again).
ACCEPTANCE: rows #11/#12 are NOT added here (P1.M3.T9.S1).
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 60 .venv/bin/python -m py_compile voice_typing/prefetch.py
timeout 60 .venv/bin/ruff check voice_typing/prefetch.py 2>/dev/null || true   # if ruff configured
bash -n install.sh   # shell syntax of the edited echoes
```

### Level 2: Unit Tests

```bash
timeout 300 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py
# Expected: 0 failures (fast suite; excludes the CUDA-loading file per AGENTS.md).
```

### Level 3: Substrate smoke (no daemon, no network)

```bash
timeout 60 .venv/bin/python -c "import voice_typing.prefetch as p; \
  assert sorted(p.CORE_REPOS)==['small.en','tiny.en']; assert not hasattr(p,'OPTIONAL_REPOS'); print('prefetch OK')"
grep -c '^bind =' hypr-binds.conf          # → 1
grep -c 'lite' hypr-binds.conf             # → 0
grep -c 'toggle-lite\|start-lite\|Alt+Super+D' install.sh   # → 0
grep -n 'P1.M2.T7.S1' hypr-binds.conf       # → placeholder present
# prefetch dry-CLI (no download: uses cache if present; abort-prone on network — smoke only):
timeout 120 .venv/bin/python -m voice_typing.prefetch || echo "note: network/cache state"
```

### Level 4: Documentation consistency

```bash
grep -n 'toggle-lite\|start-lite' tests/ACCEPTANCE.md   # → only inside row #10's rewrite if it
#   mentions their REMOVAL (prefer zero mentions); rows #1-3/#5-9 unchanged:
git diff tests/ACCEPTANCE.md   # visually confirm only rows #4 and #10 (and their evidence cells)
git diff --name-only           # ⊆ the 5 deliverable files
```

## Final Validation Checklist

- [ ] Success criteria (a)-(f) all verified by actual command output.
- [ ] prefetch imports cleanly; CORE_REPOS == {small.en, tiny.en}; no OPTIONAL_REPOS/turbo/distil refs.
- [ ] hypr-binds.conf: exactly 1 live bind (CTRL SUPER ALT, D → toggle, $HOME launcher); commented
      cancel placeholder tagged P1.M2.T7.S1; zero lite prose.
- [ ] install.sh usage = 5 commands, single-bind hint; `bash -n` clean.
- [ ] ACCEPTANCE.md rows #4/#10 rewritten to Rev 2 single-model form; #1-3/#5-9 verbatim.
- [ ] tests/test_systemd_unit.py green; full fast suite green (timeout-wrapped).
- [ ] git diff limited to the 5 files; nothing else touched (README/ctl/daemon/test_idle untouched).

## Anti-Patterns to Avoid

- ❌ Don't add a live cancel bind (it's P1.M2.T7.S1's; comment-only placeholder).
- ❌ Don't drop tiny.en (CPU-fallback install path breaks).
- ❌ Don't regenerate/alter the ACCEPTANCE fenced evidence block or add rows #11/#12 (T9.S1's).
- ❌ Don't touch tests/test_idle_and_gpu.sh, README, ctl.py, daemon.py — out of scope.
- ❌ Don't run test_feed_audio.py / test_idle_and_gpu.sh / the daemon in the foreground.

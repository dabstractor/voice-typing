# PRP — P1.M4.T3.S1: Audit install.sh — all steps, `__REPO__` substitution, idempotency, stale-symlink cleanup (vs PRD §5)

## Goal

**Feature Goal**: Produce the authoritative **`install.sh` compliance audit** as a NEW
`gap_install.md` report — verifying **ALL** work-item contract points (a)–(j) + PRD §5 + the
VT-003/VT-004 wiring against the LIVE 220-line / 12 KB `install.sh`: (a) `uv sync`; (b) prefetch
invoked (`python -m voice_typing.prefetch`); (c) CUDA smoke (`python -m voice_typing.cuda_check`);
(d) `sed` `__REPO__`→`$REPO` on the COPIED unit; (e) `cp` to `$XDG_CONFIG_HOME/systemd/user/`;
(f) `daemon-reload` + `enable` + `restart`; (g) removes the stale `default.target.wants` symlink
(VT-004); (h) copies `config.toml` to XDG **if absent**; (i) prints the tmux snippet + usage; **AND
the item's explicit DOCS point** — that the printed tmux snippet is **current and matches `status.sh`
and PRD §4.6**; (j) idempotent (safe to re-run). This is a **READ-ONLY AUDIT**: the deliverable is
the report file; NO source is modified (install.sh is compliant — this PRP's research verified all
10 points + the DOCS match + 15/15 tests pass; the audit re-confirms live).

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_install.md` — a NEW self-contained `# Gap Report —
  P1.M4.T3.S1: …` file (there is NO existing `gap_install.md`; this subtask creates it). Format
  mirrors `gap_systemd.md` / `gap_launch_daemon.md` / `gap_typing.md`. Verbatim content in the
  Implementation Blueprint → Task 3 (evidence pre-filled from verified `install.sh:line` + the
  pinning tests + the status.sh/PRD-§4.6 DOCS match; the auditor re-confirms the line numbers live
  + records the live pytest count).

> **VERIFIED VERDICT (this PRP's research): `install.sh` is COMPLIANT with PRD §5 + the work-item
> contract + VT-003/VT-004 — no fix needed.** All 10 contract points present + correct: `"$UV" sync`
> (`:65`); `"$PY" -m voice_typing.prefetch` (`:102`, warn-only); `"$PY" -m voice_typing.cuda_check`
> (`:89`, under `_setup_cuda_libs` `:72`-`82`, non-aborting `if !`); `sed -i "s#__REPO__#$REPO#g"`
> on the COPY (`:119`, after `cp` `:115`); `cp` to `$XDG_CONFIG_HOME/systemd/user/` (`:115`);
> `daemon-reload` + `enable` + `restart` (`:120`/`:125`/`:129` — restart = start-superset);
> `rm -f …/default.target.wants/voice-typing.service` (`:124`, before enable); `config.toml` if-absent
> copy (`:167`-`172`); the tmux snippet `set -g status-right "#($REPO/voice_typing/status.sh)"`
> (`:213`-`214`); + VT-003 portability (`UV=…command -v uv…` `:33`) + the stable `$HOME/.local/bin/
> voicectl` launcher symlink (`:190`). The DOCS match PASSES: install.sh's printed snippet is
> consistent with `status.sh`'s documented integration AND PRD §4.6's prescribed realized approach
> (status.sh helper, not inline jq). `tests/test_systemd_unit.py` = **15 passed** (re-run live).
>
> **The audit's value-add (HEADLINE NUANCE):** the 6 named install.sh tests pin ONLY the
> **bugfix-additions / VT-* wiring / Mode-A-docs** — (d) `__REPO__` sed, (g) stale-symlink string,
> VT-003 UV-portability, VT-003 launcher-presence, the offline regression guard, (i) the 7-command
> usage list. The **CORE PRD §5 install flow** — (a) `uv sync`, (b) prefetch invoke, (c) cuda-smoke
> invoke, (e) `cp` unit, (f) `daemon-reload`/`enable`/`restart`, (h) config-copy, (j) idempotency,
> the launcher's if-absent/foreign branches — has **NO named test** (verifiable only by reading the
> script). This audit IS the PRD-§5 compliance check the suite cannot perform — exactly the role
> `gap_systemd.md`'s `KillMode=mixed` + `gap_launch_daemon.md`'s lib-discovery nuances play.

**Success Definition**:
- (a) The report verifies **all 10** work-item contract points + the DOCS tmux-snippet match against
  the LIVE `install.sh` (re-grep — not trusting this PRP's line numbers blindly) and records a ✅
  verdict + `install.sh:line` evidence + a pinning test (or "coverage gap §5.4") for each.
- (b) The **DOCS point** is answered explicitly (§3 of the report): the printed tmux snippet
  (`install.sh:213`-`214`) is compared 1:1 against `voice_typing/status.sh`'s documented USER
  INTEGRATION block AND PRD §4.6's *"Provide a small `voice_typing/status.sh` helper script instead
  of inline jq, and reference that"* — recording the MATCH + the one nuance (`$REPO`-expanded vs the
  `/home/<you>/…` placeholder in status.sh's doc, functionally identical).
- (c) The contract's mandated test command — `.venv/bin/python -m pytest tests/test_systemd_unit.py -q`
  — is re-run live (under `timeout 60`, per AGENTS.md Rule 1) and the pass count recorded in §4 (do
  NOT hard-code; record what the live run prints; this research: **15 passed**).
- (d) The report documents the **headline nuance — the core install flow is untested** (§5.4): the 6
  named install.sh tests pin the additions (VT-003/VT-004/offline/usage), but NONE asserts the core
  PRD §5 steps (uv sync / prefetch invoke / cuda smoke / daemon-reload+enable+restart / config-copy /
  idempotency) — so a regression there would pass the suite silently. This is a **coverage gap, NOT a
  code defect** (the code is correct: read §1 + the file).
- (e) The report documents the other non-defect nuances (§5.1 `restart`-vs-`start` = start-superset;
  §5.2 XDG-honoring `$XDG_CONFIG_HOME` vs the contract's literal `~/.config`; §5.3 `sed -i` on the COPY
  keeps the git template generic; §5.5 the `if`/`elif` set-e-safe guards under `set -euo pipefail`;
  + §2 the robustness extras portaudio/`XDG_RUNTIME_DIR` preflight/launcher foreign-detection/offline
  regression guard).
- (f) **No source files are modified** — `install.sh` / `systemd/voice-typing.service` /
  `voice_typing/launch_daemon.sh` / `voice_typing/prefetch.py` / `voice_typing/cuda_check.py` /
  `voice_typing/status.sh` / `PRD.md` are compliant + read-only; the only artifact change is creating
  `gap_install.md`. `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_install.md`.
- (g) The report's scope is **`install.sh` ONLY** — NOT `prefetch.py` internals (P1.M4.T3.S2), NOT
  the systemd unit directives (P1.M4.T1.S1 → `gap_systemd.md`), NOT `launch_daemon.sh` internals
  (P1.M4.T2.S1 → `gap_launch_daemon.md`), NOT `cuda_check`'s probe (P1.M1.T4.S1 → `gap_cuda_check.md`),
  NOT `status.sh` internals (P1.M3.T2.S3 → `gap_status_sh.md`), NOT `hypr-binds.conf` (P1.M4.T4.S1).
  The cross-file artifacts are cited as evidence the install.sh steps have correct targets, NOT
  re-audited.

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance cross-check,
which maps PRD §7 acceptance criteria to the audit evidence) who needs an authoritative, file:line-
evidenced record that `install.sh` matches PRD §5 + the item contract on every point — incl. the
VT-003 `__REPO__` substitution (portable ExecStart), the VT-004 stale `default.target.wants` cleanup
(so enabling the unit does NOT leave a dead symlink from a prior install), the if-absent config copy
(never clobbering the user's edits), the idempotent re-run safety, AND the Mode-A user-facing tmux/
usage snippets being current — so a regression (a dropped `uv sync`, a reverted `restart`→`start`,
a stale `/home/dustin` path, a clobbering `cp` that wipes user config, an outdated tmux snippet)
cannot ship silently.

**Use Case**: A reviewer asks "does install.sh (1) uv-sync, (2) prefetch, (3) cuda-smoke, (4) sed
`__REPO__` on the copied unit, (5) cp to the systemd user dir, (6) daemon-reload+enable+restart,
(7) remove the stale default.target.wants symlink, (8) copy config.toml if-absent, (9) print a tmux
snippet that matches status.sh + PRD §4.6, (10) survive a re-run — exactly as PRD §5 + the contract +
VT-003/VT-004 say?" The report answers yes/no per point with the exact source line + the pinning test
(or the coverage-gap note) + the DOCS match proof.

**Pain Points Addressed**: Without this audit, the CORE install flow (uv sync / prefetch / cuda smoke
/ daemon-reload+enable+restart / config-copy) is invisible — no test pins it, so a regression that
silently broke any step would pass CI and surface only as a broken first-run ("daemon not active",
"models download on first arm", "wrong ExecStart path", "user config overwritten"). The audit pins
contract points to PRD §5 with read evidence + records the coverage gap, closing the verification hole
the test suite leaves open.

## Why

- **`install.sh` is the single setup entrypoint** (PRD §5 + §4.9) — what a user runs to go from
  `git clone` to a running, systemd-managed, UN-ARMED daemon. A drift here ships straight to a broken
  first-run or (worse) a silent hot-mic / a wiped user config / a stale ExecStart. The audit + the
  6-test additions are the guard; this audit ADDS the core-flow compliance check the suite lacks.
- **VT-003/VT-004 are correctness, not polish.** VT-003 (`__REPO__` substitution + portable `UV=` +
  the `$HOME/.local/bin/voicectl` launcher) makes the install portable across users/repo-locations
  (no hardcoded `/home/dustin`). VT-004 (`WantedBy=graphical-session.target` + the stale
  `default.target.wants` cleanup) fixes a cold-boot race where the daemon started BEFORE the compositor
  exported `WAYLAND_DISPLAY`. The audit certifies install.sh performs BOTH substitutions/cleanups.
- **Idempotency is a stated contract** (the script header + item point (j)): a 2nd run must refresh
  deps, skip cached models, never overwrite the user's XDG config, never error on an already-enabled
  unit. The audit confirms each idempotency guard (`restart`-not-`start`, if-absent config, if-absent
  launcher, `rm -f` stale symlink, warn-only prefetch/cuda).
- **The DOCS point is load-bearing for Mode A** (the script's stdout IS the user-facing install/usage
  quick-start; README P2.M1.T2.S1 copies the snippets verbatim). If the printed tmux snippet drifted
  from `status.sh` or PRD §4.6, a user following it would get a broken status line. The audit proves
  the 3-way consistency (install.sh ↔ status.sh ↔ PRD §4.6).
- **Read-only + parallel-safe.** The audit reads `install.sh` + `tests/test_systemd_unit.py` +
  `status.sh` + the unit and CREATES `gap_install.md`. No source edits → no conflict with the in-flight
  P1.M4.T2.S1 (`launch_daemon.sh` audit — disjoint file).
- **The research already did the work.** This PRP's research note pre-maps every contract point to its
  `install.sh:line` + verdict + pinning test + the DOCS match, so the implementing agent re-verifies +
  writes the report in one pass.

## What

A read-only verification of `install.sh` (the 220-line bash setup entrypoint, PRD §5 + §4.9) — re-
confirmed live via grep + the pytest re-run + the status.sh/PRD-§4.6 cross-read, then documented as a
new `gap_install.md` (mirroring `gap_systemd.md`'s format). The 10 contract points + the DOCS match +
the headline core-flow coverage gap + the other nuances.

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_install.md` exists, titled `# Gap Report — P1.M4.T3.S1: install.sh idempotency, model prefetch & service install vs PRD §5`.
- [ ] The report records a ✅ verdict + `install.sh:line` + a pinning test (or "coverage gap §5.4") for
      each of the 10 contract points.
- [ ] The DOCS point is answered (§3): the printed tmux snippet (`install.sh:213`-`214`) ↔ `status.sh`
      doc ↔ PRD §4.6 — MATCH recorded + the `$REPO`-expanded-vs-placeholder nuance noted.
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` is re-run live; its pass
      count (baseline 15) is recorded (not hard-coded).
- [ ] The headline nuance (§5.4: the core PRD §5 install flow has NO named test — coverage gap, not a
      defect) is documented, listing exactly which 6 tests exist + which 7 core points are untested.
- [ ] The other nuances (§5.1 restart-vs-start; §5.2 XDG_CONFIG_HOME; §5.3 sed-on-the-copy; §5.5 set-e
      guards) + the robustness extras (§2) are documented.
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_install.md` — NO source modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task
nature (read-only audit → new report file), the `gap_systemd.md` / `gap_launch_daemon.md` FORMAT
template, the verified verdict (compliant) + the `install.sh:line` evidence + the pinning test for all
10 contract points + the DOCS 3-way match, the exact test command, the verbatim report body (Task 3),
and the scope boundaries are all pinned. The audit re-verifies live (re-grep + re-run + re-cross-read)
rather than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + line-numbered evidence + the DOCS match + scope boundaries
- docfile: plan/006_862ee9d6ef41/P1M4T3S1/research/install_sh_audit.md
  why: "§0 THE VERIFIED VERDICT: install.sh COMPLIANT (10/10 + DOCS match + 15 tests). §1 the 10-point
        contract TABLE (each -> install.sh:line -> ✅ -> pinning test or 'coverage gap §4'). §2 the DOCS
        3-way match (install.sh:213-214 <-> status.sh doc <-> PRD §4.6 'status.sh helper, not inline jq').
        §3 robustness extras (set -euo pipefail / UV= portability / portaudio+XDG_RUNTIME_DIR preflight /
        restart-not-start / offline guard / launcher symlink). §4 THE HEADLINE NUANCE: the 6 named tests
        pin ONLY additions; the CORE flow (a/b/c/e/f/h/j) is UNTESTED (coverage gap, not a defect).
        §5 scope boundaries (prefetch=S2 / unit=T1.S1 / launch_daemon=T2.S1 / cuda_check=M1.T4.S1 /
        status_sh=M3.T2.S3). §6 grep+pytest re-verification commands. §7 tooling."
  section: "ALL load-bearing. §1 (verdict+evidence), §2 (DOCS match), §4 (the headline nuance), §5 (scope)."

# MUST READ — the file being audited (install.sh — the 10 contract points)
- file: install.sh
  why: "AUDIT TARGET (read-only, 220 lines). set -euo pipefail (:25). UV portability (:33). SCRIPT_DIR/
        REPO CWD-resolution (:35-37). XDG_RUNTIME_DIR preflight (:40-41). portaudio preflight (:52-61).
        (a) uv sync: ==> [1/7] (:64) + \"$UV\" sync (:65). (c) cuda smoke: _setup_cuda_libs (:72-82) +
        ==> [2/7] (:85) + \"$PY\" -m voice_typing.cuda_check (:89, non-aborting if ! :88, VERDICT parse
        :92-99). (b) prefetch: ==> [3/7] (:101) + \"$PY\" -m voice_typing.prefetch (:102, warn-only if !).
        (e)+(d) unit install: ==> [4/7] (:107) + cp $SRC_UNIT $USER_UNIT_DIR/voice-typing.service (:115)
        + sed -i \"s#__REPO__#$REPO#g\" (:119). (f) systemctl --user daemon-reload (:120). (g) rm -f
        $USER_UNIT_DIR/default.target.wants/voice-typing.service (:124, before enable). enable (:125).
        restart (:129). offline regression guard (voicectl-status poll :143-149 + journalctl grep for
        huggingface.co :156). (h) config: ==> [5/7] (:164) + if [ ! -f $CFG_DIR/config.toml ] cp (:167-172).
        VT-003 launcher: ln -s $REPO/.venv/bin/voicectl $LAUNCHER (:190, if-absent :182-189). (i) usage
        + tmux snippet: set -g status-interval 1 (:213) + set -g status-right \"#($REPO/voice_typing/
        status.sh)\" (:214) + hypr source (:217)."
  critical: "RE-VERIFY by grep (see research §6 commands) — do NOT trust the line numbers blindly
             (re-locate them live). The audit READS this file; it does NOT edit it (compliant code =
             no modification). NEVER run install.sh (AGENTS.md Rule 2 — it systemctl --user restarts
             the daemon + touches ~/.config; the audit is read-only + the pure-stdlib test suite)."

# MUST READ — the test file (coverage to cite per contract point; the contract's run command)
- file: tests/test_systemd_unit.py
  why: "15-test suite, pure-stdlib re+pathlib (parses the unit + launch_daemon.sh + install.sh +
        hypr-binds.conf; NO live systemd/GPU/CUDA/daemon/mic). _install_sh_path() (:61-63) resolves
        install.sh. The 6 install.sh-specific tests: test_install_sh_offline_grep_and_summary (:205) ->
        the huggingface.co journal grep + the offline summary line; test_install_sh_usage_lists_all_
        commands_and_correct_keybinds (:223) -> the 7 commands (incl toggle-lite/start-lite) + the
        Ctrl+Alt+Super+D / Alt+Super+D keybinds; test_systemd_unit_execstart_uses_repo_placeholder (:266)
        -> source-unit ExecStart=__REPO__; test_install_sh_substitutes_repo_placeholder (:280) -> the
        sed -i s#__REPO__#$REPO#g; test_install_sh_uv_path_is_portable (:293) -> no /home/dustin +
        command -v uv; test_install_sh_installs_stable_voicectl_launcher (:306) -> $HOME/.local/bin/
        voicectl + ln -s; test_install_sh_cleans_stale_default_target_symlink (:362) -> the stale
        default.target.wants string. Run it + record the count."
  critical: "Characterize coverage accurately. The 6 tests pin: (d) sed __REPO__ (:280), (g) stale
             symlink (:362), VT-003 UV portability (:293), VT-003 launcher-presence (:306), the offline
             regression guard (:205), (i) the 7-command usage list (:223). They do NOT pin: (a) uv sync,
             (b) prefetch invoke, (c) cuda-smoke invoke, (e) cp unit, (f) daemon-reload/enable/restart,
             (h) config-copy, (j) idempotency, OR the launcher's if-absent/foreign-detection BRANCHES
             (only the bare ln -s presence). That is the HEADLINE coverage gap (§5.4). Do NOT invent
             coverage that isn't there."

# MUST READ — the DOCS cross-reference (install.sh's printed snippet POINTS AT status.sh)
- file: voice_typing/status.sh
  why: "The helper install.sh's tmux snippet references. Its USER INTEGRATION comment block (:9-16)
        documents the SAME two lines install.sh prints: 'set -g status-interval 1' + 'set -g status-right
        \"#(/home/<you>/projects/voice-typing/voice_typing/status.sh)\"'. The DOCS point (item §5) is to
        prove install.sh's snippet is consistent with THIS + PRD §4.6. status.sh's INTERNALS (jq render,
        exit-0 contract, MAX truncation) are audited by P1.M3.T2.S3 (gap_status_sh.md) — NOT this task."
  critical: "Compare ONLY the printed snippet (install.sh:213-214) vs status.sh's documented integration
             block (:9-16) vs PRD §4.6's 'status.sh helper, not inline jq' mandate. Do NOT re-audit
             status.sh's jq logic (M3.T2.S3). Record the MATCH + the $REPO-expanded-vs-/home/<you>/-
             placeholder nuance (functionally identical)."

# MUST READ — the gap-report FORMAT template (mirror its structure for the new file)
- file: plan/006_862ee9d6ef41/architecture/gap_systemd.md
  why: "The closest sibling format (single-file CREATE, systemd/install-adjacent, recently created
        P1.M4.T1.S1). Structure: title (# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X) + Date + Scope +
        Audited artifacts (read-only) + Bottom line (✅) + §1 Method (commands run + observed output) +
        §2 per-point compliance TABLE (contract req | expected | actual | file:line | pinning test | ✅) +
        §3 a focused cross-reference (here: the DOCS tmux-snippet match) + §4 Test results (the live
        count) + §5 Non-defect nuances (incl. the headline coverage gap) + §6 Conclusion (PASS; ties to
        acceptance). Mirror it EXACTLY. gap_install.md is a NEW file (CREATE, not append)."
  critical: "Mirror the structure. Cite install.sh:line + a tests/test_systemd_unit.py test per contract
             point (or 'coverage gap §5.4'). gap_launch_daemon.md (P1.M4.T2.S1) + gap_typing.md are the
             other format references (same single-file CREATE pattern)."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§5 Installation steps (the 7 steps install.sh realizes): (1) cd project; (2) ensure portaudio;
        (3) uv init (already done — install.sh correctly does NOT re-init); (4) uv add deps (already in
        pyproject — install.sh uses uv sync, the idempotent materialization); (5) write source; (6)
        prefetch models + run tests + install service; (7) commit. §4.9 the systemd unit (ExecStart=
        __REPO__/voice_typing/launch_daemon.sh + WantedBy=graphical-session.target + 'install.sh: uv sync,
        prefetch models, run a 5-second CUDA smoke test, install+daemon-reload+enable+start the unit,
        print tmux snippet and usage. Idempotent'). §4.6 the DOCS mandate: 'Provide a small
        voice_typing/status.sh helper script instead of inline jq, and reference that.' §8 risk row #1
        (cuDNN -> the LD_LIBRARY_PATH wrapper install.sh's cuda-smoke reproduces). This is the spec each
        contract point is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §5 + §4.9 + §4.6 + §8 as the contract."

# CONTEXT — the sibling audit PRP (the CREATE-new-gap-file precedent + the parallel contract)
- docfile: plan/006_862ee9d6ef41/P1M4T2S1/PRP.md
  why: "The launch_daemon.sh audit (P1.M4.T2.S1) is the EXACT sibling: same single-file-CREATE pattern,
        same read-only-audit discipline, same gap-report structure, same 'headline coverage-gap nuance'
        framing (its lib-discovery gap == this task's core-flow gap). It defines gap_launch_daemon.md;
        this task defines gap_install.md — DISJOINT files (launch_daemon.sh vs install.sh), no merge
        conflict. Treat it as a contract (it is being implemented in parallel)."
  critical: "gap_install.md is INDEPENDENT of gap_launch_daemon.md (different files, different audit
             areas). CREATE the file fresh. Do NOT duplicate the launch_daemon findings. install.sh
             INVOKES launch_daemon.sh (transitively, via the unit) + cuda_check + prefetch — cite those
             as the targets install.sh's steps point at; their INTERNAL compliance is each owner's audit."

# CONTEXT — prefetch.py (cross-file: install.sh invokes it; its INTERNALS are P1.M4.T3.S2's scope)
- file: voice_typing/prefetch.py
  why: "install.sh runs `python -m voice_typing.prefetch` (:102). This audit confirms ONLY the invocation
        (+ warn-only handling). prefetch.py's download logic (snapshot_download of Systran/faster-distil-
        whisper-large-v3 + Systran/faster-whisper-small.en + tiny.en + the mobiuslabs turbo; NOT the raw-
        PyTorch distil-whisper repo) is P1.M4.T3.S2's audit. The docstring (:6-7, :19-20, :39-41) confirms
        all 4 repos are downloaded idempotently."
  critical: "Do NOT re-audit prefetch.py's download logic (P1.M4.T3.S2 owns it). Confirm install.sh
             invokes the module (:102) + is warn-only; cite prefetch.py's docstring as the 'both models'
             evidence + DEFER the deep audit to S2."
```

### Current Codebase tree (state at P1.M4.T3.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── install.sh                    # AUDIT TARGET (read-only — the 10 contract points + robustness extras, 220 lines)
├── systemd/voice-typing.service  # CROSS-FILE (ExecStart=__REPO__ + WantedBy=graphical-session; audited by P1.M4.T1.S1)
├── voice_typing/
│   ├── launch_daemon.sh          # CROSS-FILE (install.sh's unit ExecStarts it; audited by P1.M4.T2.S1)
│   ├── cuda_check.py             # CROSS-FILE (install.sh invokes it; probe audited by P1.M1.T4.S1)
│   ├── prefetch.py               # CROSS-FILE (install.sh invokes it; download logic audited by P1.M4.T3.S2)
│   └── status.sh                 # CROSS-FILE (install.sh's tmux snippet references it; audited by P1.M3.T2.S3)
├── hypr-binds.conf               # CROSS-FILE (install.sh prints a source= instruction; audited by P1.M4.T4.S1)
├── config.toml                   # CROSS-FILE (install.sh copies it to XDG if-absent)
└── tests/
    └── test_systemd_unit.py      # AUDIT (cite the pinning test per contract point; the contract's run command) — 15 tests
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_systemd.md            # FORMAT TEMPLATE + SIBLING (P1.M4.T1S1 — single-file CREATE)
    ├── gap_launch_daemon.md      # SIBLING REFERENCE (P1.M4.T2.S1 — being created in parallel)
    ├── gap_status_sh.md          # CROSS-REFERENCE (the status.sh internals; this audit only checks the snippet match)
    ├── gap_cuda_check.md         # CROSS-REFERENCE (the cuda_check probe; install.sh invokes it)
    └── gap_install.md            # <-- CREATE (NEW file; no prior install gap report exists)
# NO source/test/doc files modified. The only artifact change is creating gap_install.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_install.md   # CREATE (NEW): the P1.M4.T3.S1 install.sh audit
                                                   #   (10-contract-point compliance table + DOCS tmux-snippet 3-way match
                                                   #    + live pytest count + 5 nuances [restart-vs-start / XDG_CONFIG_HOME /
                                                   #    sed-on-the-copy / set-e guards / THE HEADLINE: core-flow coverage gap]
                                                   #    + conclusion tied to PRD §5 / acceptance).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```sh
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT; DO NOT EDIT install.sh / systemd/voice-typing.service /
#   voice_typing/launch_daemon.sh / voice_typing/prefetch.py / voice_typing/cuda_check.py /
#   voice_typing/status.sh / config.toml / hypr-binds.conf / PRD.md / any source. install.sh is
#   COMPLIANT (this PRP's research verified all 10 contract points + the DOCS match + 15/15 tests).
#   The ONLY artifact change is CREATATING gap_install.md. If a contract point fails on re-read,
#   document it as a real gap for a SEPARATE remediation task — do NOT fix install.sh here
#   (consistent with every round-006 audit). (Research §0/§5.)

# CRITICAL #2 — RE-VERIFY THE LINE NUMBERS LIVE. This PRP cites install.sh's elements at :25/:33/:64/:65/
#   :72-82/:85/:89/:101/:102/:107/:115/:119/:120/:124/:125/:129/:143-161/:164/:167-172/:182-191/:213-214
#   + the test functions at :205/:223/:266/:280/:293/:306/:362. These were correct at research time but
#   the file may have shifted — re-grep (research §6) and record the ACTUAL line numbers in the report.
#   Do NOT copy the PRP's numbers blind.

# CRITICAL #3 — THE CORE-INSTALL-FLOW COVERAGE GAP IS THE HEADLINE NUANCE (§5.4), NOT a defect. The 6
#   named install.sh tests pin ONLY: (d) sed __REPO__ (:280), (g) stale symlink (:362), VT-003 UV
#   portability (:293), VT-003 launcher-presence (:306), the offline regression guard (:205), (i) the
#   7-command usage list (:223). NONE asserts the CORE PRD §5 flow: (a) uv sync, (b) prefetch invoke,
#   (c) cuda-smoke invoke, (e) cp unit, (f) daemon-reload/enable/restart, (h) config-copy, (j)
#   idempotency, OR the launcher's if-absent/foreign BRANCHES. The code IS correct (read §1); record
#   the gap as a coverage observation (§5.4), NOT a code gap. Do NOT add a test here (read-only audit).
#   (Research §4.)

# CRITICAL #4 — RECORD THE LIVE PYTEST COUNT; DO NOT HARD-CODE IT. The contract's run command is
#   `.venv/bin/python -m pytest tests/test_systemd_unit.py -q` (FULL PATH — zsh aliases python/pytest).
#   Run it (under `timeout 60` per AGENTS.md Rule 1) + paste the actual "N passed in Xs" line into §4.
#   This research: 15 passed. (Critical #4 in the sibling gap_systemd.md/gap_launch_daemon.md PRPs;
#   same discipline.)

# CRITICAL #5 — ANSWER THE DOCS POINT EXPLICITLY (§3), NOT just the 10 contract points. The item's §5
#   DOCS mandate is: 'install.sh prints the tmux status snippet and usage instructions — verify the
#   printed snippets are current and match status.sh and PRD §4.6.' Compare install.sh:213-214
#   (`set -g status-interval 1` + `set -g status-right "#($REPO/voice_typing/status.sh)"`) vs status.sh's
#   USER INTEGRATION block (the same two lines, with /home/<you>/... as a placeholder) vs PRD §4.6's
#   'Provide a small voice_typing/status.sh helper script instead of inline jq, and reference that.'
#   Record the MATCH + the $REPO-expanded-vs-placeholder nuance (functionally identical). (Research §2.)

# CRITICAL #6 — CHARACTERIZE TEST COVERAGE ACCURATELY. The 6 tests pin the ADDITIONS, not the core
#   flow (Critical #3). Do NOT invent pinning tests for untested points (a/b/c/e/f/h/j). Cite them as
#   'coverage gap §5.4'. The launcher test (:306) asserts the bare `ln -s` PRESENCE, not the
#   if-absent/foreign-detection BRANCHES — characterize it precisely. Do NOT add a test here.

# CRITICAL #7 — SCOPE IS install.sh ONLY. Do NOT audit prefetch.py's download logic (P1.M4.T3.S2 —
#   confirm install.sh INVOKES it + cite prefetch.py's docstring as the both-models evidence, DEFER the
#   deep audit), the systemd unit directives (P1.M4.T1.S1), launch_daemon.sh internals (P1.M4.T2.S1),
#   cuda_check's probe (P1.M1.T4.S1), status.sh's jq logic (P1.M3.T2.S3), or hypr-binds.conf (P1.M4.T4.S1).
#   The cross-file artifacts are the TARGETS install.sh's steps point at — cite them as evidence, NOT
#   re-audited.

# GOTCHA #8 — NEVER RUN install.sh (AGENTS.md Rule 2). It `systemctl --user restart`s the daemon +
#   touches ~/.config/systemd/user + $HOME/.local/bin + the XDG config dir. The audit READS the file +
#   runs the pure-stdlib test suite (NO live install, NO daemon, NO mic, NO model load). Do NOT run
#   `bash install.sh` or `./install.sh` to 'test' it.

# GOTCHA #9 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always `.venv/bin/python -m
#   pytest ...`. mypy NOT installed (skip). ruff at /home/dustin/.local/bin/ruff is OPTIONAL (not a
#   gate; install.sh is bash — ruff/mypy do not apply to it; shellcheck if present is a nice-to-have,
#   not a gate). (Research §7.)

# GOTCHA #10 — TWO TIMEOUTS PER AGENTS.md RULE 1. The test is sub-second + pure-stdlib — but STILL
#   wrap: `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` (inner GNU timeout) +
#   set the bash-tool `timeout` param above 60 (outer harness backstop). This research did exactly that.

# GOTCHA #11 — gap_install.md is a NEW file. architecture/ has gap_config/cuda_check/daemon_loop/
#   feedback/lifecycle/lite/recorder_kwargs/socket/status_sh/systemd/textproc/typing/voicectl but NO
#   gap_install (confirmed). CREATE it fresh; do NOT append to a sibling. (Research §7.)
```

## Implementation Blueprint

### Data models and structure

No production data model. The deliverable is a Markdown gap-report file mirroring `gap_systemd.md`'s
structure. No code changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — re-verify the contract + locate the live line numbers (no mutation)
  - RUN (from /home/dustin/projects/voice-typing) — the research §6 commands:
      test -f install.sh && test -f tests/test_systemd_unit.py && echo "ok: files present" || echo "PREFLIGHT FAIL"
      # the 10 contract points (line-numbered):
      grep -nE '\$UV" sync|==> \[1/7\]' install.sh                                  # (a) uv sync
      grep -nE '\-m voice_typing\.prefetch|==> \[3/7\]' install.sh                  # (b) prefetch invoke
      grep -nE '\-m voice_typing\.cuda_check|==> \[2/7\]|_setup_cuda_libs' install.sh  # (c) cuda smoke
      grep -nE 'cp "\$SRC_UNIT"|==> \[4/7\]' install.sh                             # (e) cp unit
      grep -nE "sed -i .s#__REPO__" install.sh                                      # (d) sed __REPO__
      grep -nE 'daemon-reload|enable voice-typing|restart voice-typing' install.sh  # (f) reload/enable/restart
      grep -nE 'default\.target\.wants/voice-typing' install.sh                     # (g) stale symlink
      grep -nE 'CFG_DIR/config\.toml|==> \[5/7\]' install.sh                        # (h) config copy
      grep -nE 'status-interval 1|status-right.*status\.sh' install.sh              # (i) tmux snippet
      grep -nE 'set -euo pipefail' install.sh                                       # robustness
      # VT-003 extras:
      grep -nE '\$\{UV:-|command -v uv' install.sh                                  # UV portability
      grep -nE 'ln -s "\$REPO/\.venv/bin/voicectl"|\(6b\)' install.sh               # launcher symlink
      grep -nE 'HTTP Request: GET https://huggingface\.co|offline check' install.sh # offline guard
      # the source unit has the __REPO__ placeholder + graphical-session WantedBy (install.sh's targets):
      grep -nE 'ExecStart=__REPO__|WantedBy=graphical' systemd/voice-typing.service
      # the named install.sh test functions (coverage map §5.4):
      grep -nE '^def test_install_sh|^def test_systemd_unit_execstart_uses_repo_placeholder' tests/test_systemd_unit.py
      # confirm NO test pins the core flow (headline gap §5.4):
      grep -qE 'def test_.*(uv_sync|uv sync|prefetch_invoke|cuda_smoke_invoke|daemon.reload.*enable|config_copy|install_core)' tests/test_systemd_unit.py && echo "a core-flow test EXISTS (update §5.4)" || echo "no core-flow test (coverage gap §5.4 confirmed)"
  - EXPECTED: install.sh present; the 10 contract points all located at the research-cited lines
    (a :65, b :102, c :89, d :119, e :115, f :120/:125/:129, g :124, h :167, i :213-214) + the extras
    (:25/:33/:190/:156); source unit ExecStart=__REPO__ (:50) + WantedBy=graphical-session.target (:86);
    the 6+1 named test functions located; the no-core-flow-test grep confirms the §5.4 coverage gap.
    RECORD the actual line numbers.
  - DO NOT: edit anything yet, run install.sh, or touch any source/test/doc file.

Task 2: RUN the suite (record §4) + the DOCS cross-read (record §3) — TWO TIMEOUTS per AGENTS.md Rule 1
  - RUN: timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
    (and set the bash-tool `timeout` param to 90 — above the inner 60s backstop)
  - READ (for §3 DOCS match): the install.sh tmux snippet (install.sh:213-214) vs voice_typing/status.sh's
    USER INTEGRATION comment block (status.sh:9-16) vs PRD §4.6 (prd_snapshot.md §4.6 'tmux status
    integration' — the inline-jq concept + 'Provide a small voice_typing/status.sh helper script
    instead of inline jq, and reference that' mandate).
  - EXPECTED: suite all pass (~0.01s). RECORD the exact "N passed in Xs" line (this research: 15 passed).
    The 3-way DOCS read confirms MATCH (install.sh ↔ status.sh ↔ PRD §4.6 all reference status.sh-as-helper
    via #(...) substitution; the only difference is install.sh's $REPO is expanded vs status.sh's /home/<you>/
    placeholder). If a test FAILS: READ it — if it is a REAL install.sh defect, document it as a gap in §5
    (do NOT fix install.sh here); if it is an environment issue, note it. (Critical #4/#5; Gotcha #10.)

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_install.md — write the report body from
        "Task 3 SOURCE" below, REPLACING the <...> placeholders with the LIVE line numbers from Task 1
        and the LIVE pass count from Task 2 (§4). Mirror gap_systemd.md's structure exactly.
  - FILE: plan/006_862ee9d6ef41/architecture/gap_install.md (NEW — CREATE, do not append).
  - DO NOT: edit install.sh/the unit/launch_daemon.sh/prefetch.py/cuda_check.py/status.sh/config.toml/
    hypr-binds.conf/PRD.md (Critical #1); hard-code the pass count (Critical #4); flag the core-flow
    coverage gap as a code defect (Critical #3); invent pinning tests for untested points (Critical #6);
    audit the prefetch/unit/launch_daemon/cuda_check/status_sh/hypr internals (Critical #7).

Task 4: VALIDATE — L1 (file exists + markdown sanity) + L2 (the pytest count is in §4 + the DOCS match
        in §3) + L3 (scope guard: ONLY gap_install.md created; no source modified) + L4 (evidence
        spot-check). No git commit unless the orchestrator directs it. If asked: message
        "P1.M4.T3.S1: install.sh audit (compliant; gap_install.md created; no code changes)".
```

#### Task 3 SOURCE — `gap_install.md` (write this body; replace `<...>` with LIVE values from Task 1/2)

````markdown
# Gap Report — P1.M4.T3.S1: install.sh idempotency, model prefetch & service install vs PRD §5

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `install.sh` — the single idempotent setup entrypoint (PRD §5 + §4.9 "install.sh: uv sync,
prefetch models, run a 5-second CUDA smoke test, install+daemon-reload+enable+start the unit, print tmux
snippet and usage. Idempotent") — against ALL work-item contract points: (a) `uv sync`; (b) prefetch
invoked (`python -m voice_typing.prefetch`); (c) CUDA smoke (`python -m voice_typing.cuda_check`); (d)
`sed` `__REPO__`→`$REPO` on the COPIED unit (VT-003); (e) `cp` to `$XDG_CONFIG_HOME/systemd/user/`; (f)
`daemon-reload` + `enable` + `restart`; (g) removes the stale `default.target.wants` symlink (VT-004); (h)
copies `config.toml` to XDG **if absent**; (i) prints the tmux snippet + usage; **+ the DOCS point**: the
printed snippet is current + matches `status.sh` + PRD §4.6; (j) idempotent — re-verified live via grep +
the pure-Python `tests/test_systemd_unit.py` re-run + the status.sh/PRD-§4.6 cross-read. Subtask
**P1.M4.T3.S1** of verification round `006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `install.sh` — the 220-line bash entrypoint. `set -euo pipefail` (`:<L25>`); `UV="${UV:-$(command -v uv …)}"`
  (`:<L33>`, no hardcoded `/home/dustin`); CWD-independent `SCRIPT_DIR`/`REPO` (`:<L35>`-`<L37>`); the
  `XDG_RUNTIME_DIR` + `command -v` preflight (`:<L40>`-`<L43>`); the portaudio preflight (`:<L52>`-`<L61>`).
  (a) `"$UV" sync` (`:<L65>`, `==> [1/7]` `:<L64>`). (c) the `_setup_cuda_libs` LD_LIBRARY_PATH reproduce
  (`:<L72>`-`<L82>`) + `"$PY" -m voice_typing.cuda_check` (`:<L89>`, non-aborting `if !` `:<L88>`, VERDICT
  parse `:<L92>`-`<L99>`). (b) `"$PY" -m voice_typing.prefetch` (`:<L102>`, warn-only). (e) `cp "$SRC_UNIT"
  "$USER_UNIT_DIR/voice-typing.service"` (`:<L115>`). (d) `sed -i "s#__REPO__#$REPO#g"` on the copy
  (`:<L119>`). (f) `daemon-reload` (`:<L120>`) + `enable` (`:<L125>`) + `restart` (`:<L129>`). (g) `rm -f
  …/default.target.wants/voice-typing.service` (`:<L124>`, BEFORE enable). the offline regression guard
  (voicectl-status poll + journalctl huggingface.co grep, `:<L143>`-`<L161>`). (h) `config.toml` if-absent
  copy (`:<L167>`-`<L172>`). VT-003 launcher `ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER"` (`:<L190>`,
  if-absent/foreign-check `:<L182>`-`<L189>`). (i) the tmux snippet `set -g status-interval 1` (`:<L213>`) +
  `set -g status-right "#($REPO/voice_typing/status.sh)"` (`:<L214>`) + the hypr `source=` instruction
  (`:<L217>`).
- `tests/test_systemd_unit.py` — the 15-test suite (the contract's run command); pure-stdlib re+pathlib.
- `voice_typing/status.sh` — the helper install.sh's snippet references (its USER INTEGRATION block is the
  DOCS cross-reference; its internals audited by P1.M3.T2.S3).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §5 (the 7 install steps) + §4.9 (the unit + the
  install.sh mandate) + §4.6 (the status.sh-helper DOCS mandate) + §8 risk row #1 (cuDNN).

**Bottom line:** ✅ `install.sh` is **COMPLIANT** with PRD §5 + the work-item contract + VT-003/VT-004 —
all 10 contract points present + correct, the DOCS tmux-snippet point PASSES (3-way match install.sh ↔
status.sh ↔ PRD §4.6), the unit's source `__REPO__` + `WantedBy=graphical-session.target` are exactly what
the sed + stale-symlink-cleanup target, and the suite is green (**<N> passed in <X>s**, re-run live).
**No source files were modified** — install.sh faithfully implements the spec. The audit's value-add = the
**headline nuance (§5.4)**: the 6 named install.sh tests pin ONLY the bugfix-additions / VT-* wiring /
Mode-A-docs — the **CORE PRD §5 install flow** (uv sync / prefetch invoke / cuda-smoke invoke / cp unit /
daemon-reload+enable+restart / config-copy / idempotency) has **NO named test** — so this audit IS the
PRD-§5 compliance check the suite cannot perform, recording the gap so a regression cannot ship silently.

---

## 1. Method

Each of the 10 work-item contract points was mapped 1:1 to its `install.sh` implementation by `grep -nE`
(the file:line evidence), the header comments explaining the non-obvious parts (VT-003 `__REPO__`
portability; VT-004 stale-symlink cleanup; `restart`-vs-`start` idempotency) were read directly, and the
DOCS point was verified by a **3-way cross-read** (install.sh's printed snippet ↔ `status.sh`'s USER
INTEGRATION block ↔ PRD §4.6's "status.sh helper, not inline jq" mandate). The full `tests/test_systemd_unit.py`
suite was then **re-run live** to record the actual pass count + timing. Nothing was assumed from the PRP's
embedded numbers — every line number + the pass count below was re-verified this round (the suite is
pure-stdlib `re`/`pathlib`; no GPU/CUDA/daemon/mic/model-load required).

### Commands run (re-verification)

```bash
# (a)-(j): install.sh — the 10 contract points (line-numbered)
grep -nE '\$UV" sync|==> \[1/7\]' install.sh                                   # (a) uv sync
grep -nE '\-m voice_typing\.prefetch|==> \[3/7\]' install.sh                   # (b) prefetch invoke
grep -nE '\-m voice_typing\.cuda_check|==> \[2/7\]|_setup_cuda_libs' install.sh  # (c) cuda smoke
grep -nE 'cp "\$SRC_UNIT"|==> \[4/7\]' install.sh                              # (e) cp unit
grep -nE "sed -i .s#__REPO__" install.sh                                       # (d) sed __REPO__
grep -nE 'daemon-reload|enable voice-typing|restart voice-typing' install.sh   # (f) reload/enable/restart
grep -nE 'default\.target\.wants/voice-typing' install.sh                      # (g) stale symlink
grep -nE 'CFG_DIR/config\.toml|==> \[5/7\]' install.sh                         # (h) config copy
grep -nE 'status-interval 1|status-right.*status\.sh' install.sh               # (i) tmux snippet
grep -nE 'set -euo pipefail|\$\{UV:-|ln -s "\$REPO/\.venv/bin/voicectl"' install.sh  # robustness/VT-003
# source unit has the __REPO__ placeholder + graphical-session WantedBy (install.sh's targets):
grep -nE 'ExecStart=__REPO__|WantedBy=graphical' systemd/voice-typing.service
# the named install.sh test functions (coverage map §5.4):
grep -nE '^def test_install_sh|^def test_systemd_unit_execstart_uses_repo_placeholder' tests/test_systemd_unit.py
# confirm NO test pins the core flow (headline gap §5.4):
grep -qE 'def test_.*(uv_sync|prefetch_invoke|cuda_smoke_invoke|daemon.reload.*enable|config_copy|install_core)' tests/test_systemd_unit.py && echo "a core-flow test EXISTS" || echo "no core-flow test (coverage gap §5.4)"
# the contract's run command (two timeouts per AGENTS.md Rule 1):
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
```

### Observed output (abridged — replace with the LIVE re-verification)

```
==> [1/7] uv sync                    :<L64>   "$UV" sync                  :<L65>
==> [2/7] CUDA smoke                 :<L85>   "$PY" -m voice_typing.cuda_check :<L89>  (_setup_cuda_libs :<L72>-<L82>)
==> [3/7] prefetch models            :<L101>  "$PY" -m voice_typing.prefetch  :<L102>
==> [4/7] install systemd user service :<L107> cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service" :<L115>
  sed -i "s#__REPO__#$REPO#g" "$USER_UNIT_DIR/voice-typing.service" :<L119>
  systemctl --user daemon-reload     :<L120>
  rm -f …/default.target.wants/voice-typing.service :<L124>   (BEFORE enable)
  systemctl --user enable voice-typing.service :<L125>
  systemctl --user restart voice-typing.service :<L129>      (restart = start-superset)
==> [5/7] config                     :<L164>  if [ ! -f $CFG_DIR/config.toml ] cp … :<L167>-<L172>
(6b) ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER" :<L190>    (if-absent/foreign-check :<L182>-<L189>)
[7/7] set -g status-interval 1       :<L213>  set -g status-right "#($REPO/voice_typing/status.sh)" :<L214>
ExecStart=__REPO__/voice_typing/launch_daemon.sh  (systemd/voice-typing.service :<L50>)
WantedBy=graphical-session.target                  (systemd/voice-typing.service :<L86>)
(no core-flow test — coverage gap §5.4)
<N> passed in <X>s
```

---

## 2. Per-contract-point Compliance Table (work-item contract / PRD §5 vs `install.sh`)

| # | contract requirement | expected | actual (install.sh:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| (a) | `uv sync` (PRD §5 step 4; deps already in pyproject) | the idempotent materialization of pyproject deps | `"$UV" sync` (`:<L65>`, `==> [1/7] uv sync` `:<L64>`) | none — **coverage gap §5.4** | ✅ |
| (b) | prefetch.py called OR `huggingface_hub.snapshot_download` (both models) | `python -m voice_typing.prefetch`, warn-only | `"$PY" -m voice_typing.prefetch` (`:<L102>`, `==> [3/7]` `:<L101>`, warn-only `if !`) | none — **coverage gap §5.4** (prefetch.py INTERNALS = P1.M4.T3.S2) | ✅ |
| (c) | CUDA smoke (`ctranslate2.get_cuda_device_count`) | `python -m voice_typing.cuda_check`, non-aborting on cpu-fallback | `"$PY" -m voice_typing.cuda_check` (`:<L89>`, under `_setup_cuda_libs` `:<L72>`-`<L82>` reproducing launch_daemon.sh's LD_LIBRARY_PATH; non-aborting `if !` `:<L88>`; VERDICT parse `:<L92>`-`<L99>`) | none — **coverage gap §5.4** (cuda_check probe = P1.M1.T4.S1) | ✅ |
| (d) | `sed` `__REPO__` → actual path on the COPIED unit (VT-003) | `sed -i s|__REPO__|$REPO|` AFTER `cp`, on the COPY (git template stays generic) | `sed -i "s#__REPO__#$REPO#g" "$USER_UNIT_DIR/voice-typing.service"` (`:<L119>`, after `cp` `:<L115>`); source unit `ExecStart=__REPO__/…` (`systemd/voice-typing.service:<L50>`) | `test_install_sh_substitutes_repo_placeholder` (`:<L280>`) + `test_systemd_unit_execstart_uses_repo_placeholder` (`:<L266>`) | ✅ |
| (e) | `cp` unit to `~/.config/systemd/user/` (honors XDG) | `cp` to the systemd user dir | `cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service"` (`:<L115>`); `USER_UNIT_DIR="$XDG_CONFIG_HOME/systemd/user"` (`:<L113>`) — MORE correct than hardcoded `~/.config` (§5.2) | none direct — **coverage gap §5.4** | ✅ |
| (f) | `daemon-reload` + `enable` + `start` | reload + enable + (re)start the unit | `daemon-reload` (`:<L120>`) + `enable voice-typing.service` (`:<L125>`) + `restart voice-typing.service` (`:<L129>`) — uses **restart** = start-superset (applies a freshly-copied unit to a running one + idempotent; §5.1) | none — **coverage gap §5.4** (live systemctl, not unit-testable) | ✅ |
| (g) | remove stale `default.target.wants` symlink (VT-004) | `rm -f` the old symlink BEFORE enable (systemctl enable/disable key off the CURRENT [Install]) | `rm -f "$USER_UNIT_DIR/default.target.wants/voice-typing.service" 2>/dev/null \|\| true` (`:<L124>`) — BEFORE `enable` (`:<L125>`); the unit's `WantedBy=graphical-session.target` (`:<L86>`) | `test_install_sh_cleans_stale_default_target_symlink` (`:<L362>`) | ✅ |
| (h) | copy `config.toml` to `$XDG_CONFIG_HOME/voice-typing/` IF ABSENT | copy only when absent (never clobber user edits) | `if [ ! -f "$CFG_DIR/config.toml" ]; then cp "$REPO/config.toml" …; else echo "kept existing … (not overwritten)"` (`:<L167>`-`<L172>`) — idempotent | none — **coverage gap §5.4** | ✅ |
| (i) | print tmux snippet + usage (Mode A docs) | the `[7/7]` usage + tmux + hypr block | usage (`:<L205>`-`<L211>`) + `set -g status-interval 1` (`:<L213>`) + `set -g status-right "#($REPO/voice_typing/status.sh)"` (`:<L214>`) + `source = $REPO/hypr-binds.conf` (`:<L217>`) | `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:<L223>`) — pins the 7 commands + keybinds | ✅ |
| (j) | idempotent (safe to re-run) | every step safe on a 2nd run | structural: `uv sync` refreshes; prefetch cached; `restart` not `start`; config **if-absent** (`:<L167>`); launcher **if-absent/foreign-check** (`:<L182>`-`<L189>`); stale-symlink `rm -f` (`:<L124>`); cuda smoke + prefetch warn-only | none — **coverage gap §5.4** (idempotency is structural, asserted by read) | ✅ |

> All 10 contract points **PASS**. The file:line numbers above are `grep -n`-verified against the live tree
> this round. The 7 untested points are confirmed correct by direct read; the gap is recorded as a
> non-blocking coverage observation in §5.4.

### Robustness extras (compliant, beyond the 10 contract points — recorded so they are not "simplified" away)

| extra | actual (install.sh:line) | why it matters | tested? |
|---|---|---|---|
| `set -euo pipefail` | `:<L25>` | fail-fast on error/unset-var/broken-pipe | no |
| `UV="${UV:-$(command -v uv \|\| echo "$HOME/.local/bin/uv")}"` (VT-003) | `:<L33>` | NO hardcoded `/home/dustin`; honors `UV=` override; bash shebang (no zsh aliases) | yes (`:<L293>`) |
| CWD-independent `SCRIPT_DIR`/`REPO` | `:<L35>`-`<L37>` | works from any cwd | no |
| `XDG_RUNTIME_DIR` + `command -v` preflight | `:<L40>`-`<L43>` | `systemctl --user` + the daemon's socket need it; actionable error | no |
| portaudio preflight (pacman -Q; PRD §5 step 2) | `:<L52>`-`<L61>` | PyAudio dlopen dep; non-Arch warn-and-continue; `if !`/`elif !` set-e-safe | no |
| `restart` (not `start`) | `:<L129>` | applies a freshly-copied unit to a running one + idempotent (§5.1) | no |
| offline regression guard (post-restart journal grep for huggingface.co HTTP) | `:<L143>`-`<L161>` | asserts HF_HUB_OFFLINE=1 active at runtime; warn-only, set-e-safe | yes (`:<L205>`) |
| stale `realtimesst.log` removal | `:<L133>`-`<L138>` | housekeeping for pre-`no_log_file` runs; gitignored | no |
| VT-003 voicectl launcher `$HOME/.local/bin/voicectl → $REPO/.venv/bin/voicectl` | `:<L176>`-`<L191>` | hypr-binds.conf uses `$HOME/.local/bin/voicectl`; only-create-if-absent + warn-on-foreign | yes (`:<L306>` — presence only, not the branches) |

---

## 3. The DOCS point: printed tmux snippet ↔ `status.sh` ↔ PRD §4.6 (3-way MATCH)

The item's explicit DOCS mandate: *"install.sh prints the tmux status snippet and usage instructions —
verify the printed snippets are current and match `status.sh` and PRD §4.6."*

| source | what it says | note |
|---|---|---|
| **install.sh** (`:<L213>`-`<L214>`) | `set -g status-interval 1` + `set -g status-right "#($REPO/voice_typing/status.sh)"` | `$REPO` is the REAL expanded repo path at install time |
| **`voice_typing/status.sh`** (USER INTEGRATION block) | `set -g status-interval 1` + `set -g status-right "#(/home/<you>/projects/voice-typing/voice_typing/status.sh)"` | `/home/<you>/…` is a PLACEHOLDER; install.sh's `$REPO` is the realized value |
| **PRD §4.6** | shows an INLINE-jq snippet as the *concept*, THEN: *"Provide a small `voice_typing/status.sh` helper script instead of inline jq, and reference that — cleaner quoting."* | the REALIZED approach is exactly status.sh-as-helper via `#(...)` — what install.sh + status.sh both do |

**✅ MATCH.** install.sh's printed snippet is CURRENT and CONSISTENT with `status.sh`'s documented
integration AND with PRD §4.6's prescribed realized approach (helper script, not inline jq). The
`status-interval 1` + the `#(…)` substitution + the `status.sh` path all agree across all three. The
single nuance: install.sh prints the snippet with `$REPO` already expanded (so a user pastes it verbatim),
while `status.sh`'s doc keeps `/home/<you>/…` as a placeholder — functionally identical (install.sh's
expansion IS the value the placeholder stands for). `status.sh`'s INTERNALS (jq render, exit-0 contract,
MAX truncation) are audited by P1.M3.T2.S3 (`gap_status_sh.md`) — NOT this task.

---

## 4. Test results (the contract's run command, LIVE)

```
$ timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
.<paste the live summary line, e.g. "15 passed in 0.01s">.
```

The suite (15 tests) is pure-stdlib `re`/`pathlib`: it parses `systemd/voice-typing.service` +
`voice_typing/launch_daemon.sh` + `install.sh` + `hypr-binds.conf` — no GPU/CUDA/daemon/mic. **6 tests
pin install.sh-specific concerns** (all bugfix-additions / VT-* wiring / Mode-A-docs): `test_install_sh_
substitutes_repo_placeholder` (`:<L280>`, (d)), `test_install_sh_uv_path_is_portable` (`:<L293>`,
VT-003), `test_install_sh_installs_stable_voicectl_launcher` (`:<L306>`, VT-003 launcher-presence),
`test_install_sh_cleans_stale_default_target_symlink` (`:<L362>`, (g)), `test_install_sh_offline_grep_
and_summary` (`:<L205>`, the offline guard), `test_install_sh_usage_lists_all_commands_and_correct_
keybinds` (`:<L223>`, (i)); + `test_systemd_unit_execstart_uses_repo_placeholder` (`:<L266>`, source-side
`__REPO__`). **Coverage gap**: NO test pins the CORE flow (a) `uv sync`, (b) prefetch invoke, (c) cuda-
smoke invoke, (e) `cp` unit, (f) `daemon-reload`/`enable`/`restart`, (h) config-copy, (j) idempotency,
or the launcher's if-absent/foreign BRANCHES (§5.4).

---

## 5. Non-defect nuances (so they are not mistaken for gaps)

### 5.1 `restart` (not `start`) is a deliberate start-SUPERSET (contract point (f))
The contract says "start"; install.sh uses `systemctl --user restart voice-typing.service` (`:<L129>`).
`restart` is strictly more correct for an installer: it BOTH starts a stopped unit AND applies a freshly-
copied unit to an already-running one (so a re-install actually picks up the new unit file), and it is
idempotent. The in-script comment documents this. ✅

### 5.2 `$XDG_CONFIG_HOME` (not hardcoded `~/.config`) is MORE correct (contract point (e)/(h))
The contract says "~/.config/systemd/user/" and "$XDG_CONFIG_HOME/voice-typing/". install.sh sets
`XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"` and uses `$XDG_CONFIG_HOME/systemd/user` (`:<L113>`)
+ `$XDG_CONFIG_HOME/voice-typing` (`:<L165>`) — honoring an explicit XDG override (mirroring
`voice_typing/config.py`'s search order) while defaulting to `~/.config`. ✅

### 5.3 `sed -i` on the COPY keeps the git template generic (contract point (d))
install.sh `cp`s the unit into `$XDG_CONFIG_HOME/systemd/user/` FIRST (`:<L115>`) and only THEN
`sed -i "s#__REPO__#$REPO#g"` the COPY (`:<L119>`). The source `systemd/voice-typing.service` in git
keeps the literal `__REPO__` placeholder (so it is portable / not user-specific in version control).
The `#` delimiter (not `|`) avoids clashes with repo paths. ✅

### 5.4 THE HEADLINE — the CORE PRD §5 install flow has NO named test (coverage gap, NOT a code defect)
The 6 named install.sh tests (§4) pin ONLY the bugfix-additions / VT-* wiring / Mode-A-docs: (d) the
`__REPO__` sed, (g) the stale-symlink STRING, VT-003 UV-portability, VT-003 launcher-PRESENCE (bare
`ln -s`, not the if-absent/foreign branches), the offline regression guard, (i) the 7-command usage list.
**NONE asserts the CORE flow**: (a) `uv sync`, (b) the `prefetch` invocation, (c) the `cuda_check`
invocation, (e) the `cp` of the unit, (f) `daemon-reload`/`enable`/`restart`, (h) the `config.toml`
if-absent copy, (j) idempotency. So a regression that dropped the `uv sync` line, changed `restart`→
`start`, removed the config-copy step, or broke the launcher's foreign-detection branch would pass the
15-test suite silently. **This is a coverage gap, not a code defect**: the code is correct (verified by
read §1). This audit IS the PRD-§5 compliance check the suite cannot perform — exactly the role
`gap_systemd.md`'s `KillMode=mixed` + `gap_launch_daemon.md`'s lib-discovery nuances play. A future
test-hardening pass COULD add a `test_install_sh_runs_core_prd5_flow` (grep for `"$UV" sync` +
`-m voice_typing.prefetch` + `-m voice_typing.cuda_check` + `daemon-reload` + `enable` + `restart` +
the `if [ ! -f` config-copy + the `status.sh` tmux snippet) — **out of scope for this read-only audit**
(do NOT add a test here; consistent with every round-006 audit's "read-only, no new tests" discipline). ✅

### 5.5 `set -euo pipefail` + the `if !`/`elif !` guards keep optional-step non-zero exits from aborting
`set -euo pipefail` (`:<L25>`) makes the script fail-fast on real errors, but several steps legitimately
return non-zero (cuda_check exits 1 on cpu-fallback; prefetch may partially fail; pacman -Q on absent
portaudio; the journal grep). install.sh wraps these in `if !`/`elif !` conditions (errexit-exempt) so a
valid degraded-mode result never aborts the install — the documented idiom for mixing `set -e` with
optional checks. ✅

---

## 6. Conclusion

**PASS.** `install.sh` fully complies with PRD §5 + the work-item contract + VT-003/VT-004: all 10
contract points (a)–(j) are present + correct (file:line-evidenced), the DOCS tmux-snippet point is a
3-way match (install.sh ↔ `status.sh` ↔ PRD §4.6), the unit's source `__REPO__` + `WantedBy=graphical-
session.target` are exactly the sed + stale-symlink-cleanup targets, the VT-003 portability (no hardcoded
`/home/dustin`) + the stable launcher symlink are in place, and the suite is green (**<N> passed**).
**No source files were modified.** The audit's value-add = the headline §5.4 coverage gap (the CORE
install flow is verified by read, not by test) — recorded so a regression cannot ship silently. Ties to
PRD §5 (the 7 install steps), §4.9 (the unit + the install.sh mandate), §4.6 (the status.sh-helper DOCS
mandate), and §8 risk row #1 (the cuDNN wrapper install.sh's cuda-smoke reproduces). Acceptance criteria
for installability (a user can `git clone` → `./install.sh` → running un-armed daemon) are met.
````

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
# The deliverable is a Markdown report — sanity-check it exists + is non-trivial:
test -f plan/006_862ee9d6ef41/architecture/gap_install.md && wc -l plan/006_862ee9d6ef41/architecture/gap_install.md
grep -c '^| (' plan/006_862ee9d6ef41/architecture/gap_install.md   # the per-point table rows (expect ~10)
grep -q '✅' plan/006_862ee9d6ef41/architecture/gap_install.md && echo "verdict present"
# (No ruff/mypy apply — the only code touched is none; install.sh is bash, read-only.)
# Expected: file exists; ~10 table rows; verdict present.
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing
# The contract's run command (re-run live; two timeouts per AGENTS.md Rule 1):
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
# Expected: all green (this research: 15 passed in 0.01s). The pass count is recorded in the report §4.
# (The install.sh-specific tests: -k "install_sh" — pin the 6 additions documented in §5.4.)
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q -k "install_sh"
```

### Level 3: Integration Testing (the audit's evidence chain — read-only)

```bash
cd /home/dustin/projects/voice-typing
# Re-confirm every contract point is present in the LIVE install.sh (the §1 evidence):
grep -nE '\$UV" sync|-m voice_typing\.prefetch|-m voice_typing\.cuda_check|cp "\$SRC_UNIT"|sed -i .s#__REPO__|daemon-reload|enable voice-typing|restart voice-typing|default\.target\.wants/voice-typing|if \[ ! -f "\$CFG_DIR/config\.toml"|status-right.*status\.sh' install.sh
# Re-confirm the source unit has the __REPO__ placeholder + graphical-session WantedBy (install.sh's targets):
grep -nE 'ExecStart=__REPO__|WantedBy=graphical' systemd/voice-typing.service
# Re-confirm the DOCS 3-way match (install.sh snippet <-> status.sh doc <-> PRD §4.6):
sed -n '/set -g status-right/p' install.sh; grep -n 'set -g status-right' voice_typing/status.sh; sed -n '/status.sh helper/p' plan/006_862ee9d6ef41/prd_snapshot.md
# Expected: every contract-point pattern hits its cited line; the unit has __REPO__ + graphical-session;
# the 3-way snippet matches. (NO live install, NO daemon — read-only.)
```

### Level 4: Creative & Domain-Specific Validation (scope + no-mutation guard)

```bash
cd /home/dustin/projects/voice-typing
# Scope guard: ONLY gap_install.md created; NO source modified.
git status --short | grep -vE '^\?\? plan/006_862ee9d6ef41/architecture/gap_install.md$' || echo "ok: only gap_install.md is new"
git status --short -- install.sh systemd/voice-typing.service voice_typing/ tests/ config.toml hypr-binds.conf  # expect: empty (no source touched)
# Evidence spot-check: the headline nuance (§5.4) + the DOCS match (§3) are in the report:
grep -q 'coverage gap' plan/006_862ee9d6ef41/architecture/gap_install.md && echo "headline nuance present"
grep -qE 'MATCH|3-way' plan/006_862ee9d6ef41/architecture/gap_install.md && echo "DOCS match present"
# Expected: only gap_install.md is new; no source changed; both nuances documented.
```

## Final Validation Checklist

### Technical Validation

- [ ] All 4 validation levels completed successfully.
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` green (live count recorded in §4).
- [ ] `plan/006_862ee9d6ef41/architecture/gap_install.md` exists with the §1 table (~10 contract points),
      §3 DOCS match, §4 test count, §5 nuances.
- [ ] All cited `install.sh:line` numbers are `grep -n`-verified live (not copied blind from the PRP).

### Feature Validation

- [ ] All 10 contract points (a)–(j) have a ✅ verdict + file:line + pinning test (or "coverage gap §5.4").
- [ ] The DOCS point (§3): the printed tmux snippet matches `status.sh` + PRD §4.6 (3-way match recorded).
- [ ] The headline nuance (§5.4: core install flow untested — coverage gap, not a defect) is documented.
- [ ] The other nuances (§5.1 restart-vs-start; §5.2 XDG_CONFIG_HOME; §5.3 sed-on-the-copy; §5.5 set-e guards)
      + the robustness extras (§2) are documented.
- [ ] The report ties the verdict to PRD §5 + §4.9 + §4.6 + §8.

### Code Quality Validation

- [ ] Report mirrors `gap_systemd.md`'s structure (title/date/scope/artifacts/bottom line/§1 method/§2 table/
      §3 cross-ref/§4 tests/§5 nuances/§6 conclusion).
- [ ] Test coverage characterized accurately (the 6 named tests pin additions; the 7 core points are gaps —
      no invented coverage).
- [ ] Anti-patterns avoided (no source edits; no hard-coded pass count; no running install.sh; no re-auditing
      prefetch/unit/launch_daemon/cuda_check/status_sh/hypr internals; no flagging the coverage gap as a defect).
- [ ] Scope is `install.sh` ONLY (cross-files cited as targets, not re-audited).

### Documentation & Deployment

- [ ] The report is self-contained (a reviewer needs only it + the cited files to confirm compliance).
- [ ] The §5.4 coverage gap + the optional future test-hardening suggestion are recorded for a later pass.
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_install.md`.

---

## Anti-Patterns to Avoid

- ❌ Don't EDIT install.sh / the unit / launch_daemon.sh / prefetch.py / cuda_check.py / status.sh / config.toml
  / hypr-binds.conf / PRD.md / any source — this is a READ-ONLY audit; install.sh is compliant. The ONLY
  artifact change is creating `gap_install.md`. A re-read that finds a real defect → document it as a gap for
  a SEPARATE remediation task (consistent with every round-006 audit).
- ❌ Don't hard-code the pytest pass count or copy the PRP's line numbers blind — re-grep + re-run live.
- ❌ Don't flag the core-flow coverage gap (§5.4) as a code DEFECT — the code is correct (read §1); the gap is
  a coverage observation. Don't add a test here (read-only audit).
- ❌ Don't invent pinning tests for the untested core points (a/b/c/e/f/h/j) — cite them as "coverage gap §5.4".
- ❌ Don't RUN install.sh (AGENTS.md Rule 2 — it restarts the daemon + touches ~/.config). The audit is read-only
  + the pure-stdlib test suite.
- ❌ Don't re-audit the cross-file artifacts' INTERNALS — prefetch.py (P1.M4.T3.S2), the unit (P1.M4.T1.S1),
  launch_daemon.sh (P1.M4.T2.S1), cuda_check.py (P1.M1.T4.S1), status.sh (P1.M3.T2.S3), hypr-binds.conf
  (P1.M4.T4.S1). Cite them as the TARGETS install.sh's steps point at.
- ❌ Don't skip the DOCS point (§3) — it is an explicit item requirement (verify the printed snippet matches
  status.sh + PRD §4.6); record the 3-way match.
- ❌ Don't conflate the `restart`-vs-`start` or the XDG-vs-`~/.config` differences with defects — they are
  deliberate improvements (§5.1/§5.2).

---

## Confidence Score

**9/10** — one-pass implementation success is highly likely. The audit is read-only with a pre-filled
verifiable verdict: every one of the 10 contract points is mapped to a `grep -n`-verified `install.sh:line`
(re-confirmed this round: a `:65`, b `:102`, c `:89`, d `:119`, e `:115`, f `:120`/`:125`/`:129`, g `:124`,
h `:167`, i `:213`-`214`), the DOCS tmux-snippet 3-way match (install.sh ↔ `status.sh` ↔ PRD §4.6) is
proven by direct cross-read, the 6 named install.sh tests + the 7-point core-flow coverage gap are
characterized precisely, and the contract's test command (`timeout 60 .venv/bin/python -m pytest
tests/test_systemd_unit.py -q`) was re-run live (**15 passed**). The verbatim `gap_install.md` body (Task 3
SOURCE) mirrors `gap_systemd.md`'s structure. The single residual risk is line-number drift between
research time and audit time — mitigated by the Task 1 preflight re-grep + the `<L…>` placeholder discipline
(the auditor records the LIVE numbers, never copies the PRP's blind). The validation gates (L1 markdown
sanity, L2 the live pytest count, L3 the evidence-chain re-grep + the 3-way DOCS read, L4 the scope/no-
mutation guard) are executable as written.
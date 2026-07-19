# P1.M4.T3.S1 — install.sh audit research (verified against the LIVE tree)

The authoritative evidence map for the PRP. Every line number + the test count was re-grepped
this round (2026-07-18). `install.sh` = 220 lines, 12 KB.

## 0. VERIFIED VERDICT: install.sh is COMPLIANT with PRD §5 + the item contract + VT-003/VT-004

ALL 10 work-item contract points (a)–(j) are present + correct. No source change needed. The
audit's value-add = the **HEADLINE NUANCE (§4 below)**: `tests/test_systemd_unit.py` (15 tests)
pins the VT-003/VT-004/offline-guard/usage-listing **additions** via 6 named install.sh tests, but
the **CORE PRD §5 install flow** — uv sync / prefetch invoke / cuda smoke / daemon-reload+enable+
restart / config-copy / idempotency — has **NO named test** (it is verifiable only by reading the
script). This audit IS the PRD-§5 compliance check the suite cannot perform — exactly the role
`gap_systemd.md`'s `KillMode=mixed` + `gap_launch_daemon.md`'s lib-discovery nuances play.

## 1. Per-contract-point evidence table (install.sh:line → verdict → pinning test / coverage gap)

| # | contract requirement | actual (install.sh:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|
| (a) | uv sync step (PRD §5 step 4; deps already in pyproject) | `"$UV" sync` (`:65`; header `==> [1/7] uv sync` `:64`) | none — **coverage gap §4** | ✅ |
| (b) | prefetch.py called OR huggingface_hub.snapshot_download (both models) | `"$PY" -m voice_typing.prefetch` (`:102`, warn-only `if !`); header `==> [3/7]` `:101` | none — **coverage gap §4** (prefetch.py INTERNALS = P1.M4.T3.S2; this audit confirms install.sh INVOKES the module) | ✅ |
| (c) | CUDA smoke test (ctranslate2.get_cuda_device_count) | `"$PY" -m voice_typing.cuda_check` (`:89`, under `_setup_cuda_libs` `:72`-`82` which reproduces launch_daemon.sh's LD_LIBRARY_PATH; non-aborting `if !` `:88`; VERDICT parse `:92`-`99`) | none — **coverage gap §4** (cuda_check probe internals = P1.M1.T4.S1/gap_cuda_check.md) | ✅ |
| (d) | sed `__REPO__` → actual path on the COPIED unit (VT-003) | `sed -i "s#__REPO__#$REPO#g" "$USER_UNIT_DIR/voice-typing.service"` (`:119`, AFTER `cp` `:115` — the template in git stays generic) | `test_install_sh_substitutes_repo_placeholder` (`:280`) + `test_systemd_unit_execstart_uses_repo_placeholder` (`:266`, source-side) | ✅ |
| (e) | cp unit to ~/.config/systemd/user/ (honors XDG) | `cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service"` (`:115`); `USER_UNIT_DIR="$XDG_CONFIG_HOME/systemd/user"` (`:113`) — MORE correct than hardcoded ~/.config | none direct — **coverage gap §4** | ✅ |
| (f) | systemctl --user daemon-reload + enable + start | `daemon-reload` (`:120`) + `enable voice-typing.service` (`:125`) + `restart voice-typing.service` (`:129`). Uses **restart** (superset of start: applies a freshly-copied unit to a running one + idempotent — documented in the comment) | none — **coverage gap §4** (live systemctl, not unit-testable) | ✅ |
| (g) | remove stale default.target.wants symlink (VT-004) | `rm -f "$USER_UNIT_DIR/default.target.wants/voice-typing.service" 2>/dev/null \|\| true` (`:124`) BEFORE `enable` (`:125`) | `test_install_sh_cleans_stale_default_target_symlink` (`:362`) | ✅ |
| (h) | copy config.toml to $XDG_CONFIG_HOME/voice-typing/ IF ABSENT | `if [ ! -f "$CFG_DIR/config.toml" ]; then cp "$REPO/config.toml" …; else echo "kept existing … (not overwritten)"` (`:167`-`172`) — idempotent, never overwrites | none — **coverage gap §4** | ✅ |
| (i) | print tmux snippet + usage instructions (Mode A docs) | `[7/7]` block (`:200`-`220`): usage (`:205`-`211`) + tmux snippet (`:213`-`214`) + hypr source (`:217`) + logs/config | `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:223`) — pins the 7 commands + the keybinds | ✅ |
| (j) | idempotent (safe to re-run) | structural: `uv sync` refreshes (safe); prefetch cached (snapshot_download skips); `restart` not `start`; config **if-absent** (`:167`); launcher **if-absent/foreign-check** (`:182`-`189`); stale-symlink `rm -f` (`:124`); cuda smoke warn-only (`:88`) | none — **coverage gap §4** (idempotency is structural, asserted by read) | ✅ |

> All 10 PASS. Line numbers are `grep -n`-verified live this round.

## 2. The DOCS point (item §5): printed tmux snippet ↔ status.sh ↔ PRD §4.6 — they MATCH

This is the item's explicit DOCS requirement: *"install.sh prints the tmux status snippet and
usage instructions — verify the printed snippets are current and match status.sh and PRD §4.6."*

| source | what it says | note |
|---|---|---|
| **install.sh** (`:213`-`214`) | `set -g status-interval 1` + `set -g status-right "#($REPO/voice_typing/status.sh)"` | `$REPO` is the REAL expanded repo path at install time |
| **status.sh** doc (USER INTEGRATION comment, `:10`-`15`) | `set -g status-interval 1` + `set -g status-right "#(/home/<you>/projects/voice-typing/voice_typing/status.sh)"` | the `/home/<you>/…` is a PLACEHOLDER; install.sh's `$REPO` is the realized value |
| **PRD §4.6** (prd_snapshot) | shows an INLINE-jq snippet as the *concept*, THEN: *"Provide a small `voice_typing/status.sh` helper script instead of inline jq, and reference that — cleaner quoting."* | the REALIZED approach is exactly status.sh-as-helper, referenced via `#(...)` — what install.sh + status.sh both do |

**Verdict: ✅ MATCH.** install.sh's printed snippet is CURRENT and CONSISTENT with status.sh's
documented integration AND with PRD §4.6's prescribed realized approach (helper script, not inline
jq). The single nuance: install.sh prints the snippet with `$REPO` already expanded to the real
path (so a user can paste it verbatim), while status.sh's doc keeps `/home/<you>/…` as a placeholder
— functionally identical (install.sh's expansion IS the value the placeholder stands for). The
`status-interval 1` + the `#(...)` substitution + the `status.sh` path all agree across all three.

## 3. Robustness extras (compliant, beyond the 10 contract points — record so not "simplified" away)

| extra | actual (install.sh:line) | why it matters | tested? |
|---|---|---|---|
| `set -euo pipefail` | `:25` | fail-fast on error/unset-var/broken-pipe (prevents the AGENTS.md PATH-shim recursion class) | no |
| `UV="${UV:-$(command -v uv \|\| echo "$HOME/.local/bin/uv")}"` (VT-003) | `:33` | NO hardcoded /home/dustin; honors `UV=` override; bash shebang (no zsh aliases) | yes (`:293`) |
| CWD-independent `SCRIPT_DIR`/`REPO` resolution | `:35`-`37` | works from any cwd (systemd absolute ExecStart or manual `./install.sh`) | no |
| `XDG_RUNTIME_DIR` preflight (exit 1 if unset) | `:40`-`41` | `systemctl --user` + the daemon's own socket need it; fail clearly | no |
| `command -v uv`/`systemctl` preflight | `:42`-`43` | actionable error before any step | no |
| portaudio preflight (pacman -Q; PRD §5 step 2) | `:52`-`61` | PyAudio dlopen dep; non-Arch hosts warn-and-continue; `if !`/`elif !` set-e-safe | no |
| `restart` (not `start`) | `:129` | starts a stopped unit AND applies a freshly-copied unit to a running one (idempotent + update-applying) | no |
| offline regression guard (post-restart journal grep for huggingface.co HTTP) | `:143`-`161` | asserts HF_HUB_OFFLINE=1 is active at runtime (the hard gate is test_launch_daemon_exports_offline_vars); warn-only, set-e-safe `if` | yes (`:205`) |
| stale `realtimesst.log` removal | `:133`-`138` | housekeeping for pre-no_log_file runs; gitignored; current daemon never appends | no |
| voicectl launcher symlink `$HOME/.local/bin/voicectl → $REPO/.venv/bin/voicectl` (VT-003) | `:176`-`191` | hypr-binds.conf uses `$HOME/.local/bin/voicectl` (Hyprland `bind exec` expands $HOME via /bin/sh); only-create-if-absent + warn-on-foreign (never clobber) | yes (`:306`) |

## 4. THE HEADLINE NUANCE — the CORE install flow is untested (coverage gap, NOT a code defect)

`tests/test_systemd_unit.py` (15 tests, pure-stdlib re/pathlib — parses install.sh/unit/wrapper/
binds; NO live systemd/GPU/CUDA/daemon/mic) pins **6 install.sh-specific concerns**, ALL of which
are **bugfix-additions / VT-* wiring / Mode-A-docs**, NOT the core PRD §5 flow:

- `test_install_sh_substitutes_repo_placeholder` (`:280`) → (d) sed `__REPO__`
- `test_install_sh_uv_path_is_portable` (`:293`) → VT-003 no-hardcoded-/home/dustin
- `test_install_sh_installs_stable_voicectl_launcher` (`:306`) → VT-003 launcher present (`ln -s`)
- `test_install_sh_cleans_stale_default_target_symlink` (`:362`) → (g) stale-symlink string
- `test_install_sh_offline_grep_and_summary` (`:205`) → offline regression guard
- `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:223`) → (i) 7 commands + keybinds
- (+ `test_systemd_unit_execstart_uses_repo_placeholder` `:266` — source-side `__REPO__`)

**NONE of these asserts the CORE flow**: (a) `uv sync`, (b) the `prefetch` invocation, (c) the
`cuda_check` invocation, (e) the `cp` of the unit, (f) `daemon-reload`/`enable`/`restart`,
(h) the `config.toml` if-absent copy, (j) idempotency, OR the launcher's if-absent/foreign-detection
*branches* (only the bare `ln -s` presence is checked). So a regression that, say, dropped the
`uv sync` line, or changed `restart`→`start`, or removed the config-copy step, would pass the
15-test suite silently. **This is a coverage gap, NOT a code defect**: the code is correct (verified
by read §1). This audit IS the PRD-§5 compliance check the suite cannot perform. A future
test-hardening pass COULD add a `test_install.sh_runs_core_prd5_flow` (grep for `$UV" sync` +
`-m voice_typing.prefetch` + `-m voice_typing.cuda_check` + `daemon-reload` + `enable` +
`restart` + the config-copy `if [ ! -f` + the `status.sh` tmux snippet) — **out of scope here**
(read-only audit; consistent with every round-006 audit's "no new tests" discipline). ✅

## 5. Scope boundaries (do NOT re-audit these — they are other subtasks)

| area | owner | cross-reference |
|---|---|---|
| `prefetch.py` INTERNAL download logic (both models / snapshot_download / Systran vs distil-whisper) | **P1.M4.T3.S2** | this audit only confirms install.sh INVOKES `python -m voice_typing.prefetch` (`:102`); prefetch.py docstring confirms all 4 repos (distil-large-v3/small.en/tiny.en + turbo) |
| `systemd/voice-typing.service` directives (KillMode/TimeoutStopSec/ExecStartPre/VT-004 After=) | P1.M4.T1.S1 | `gap_systemd.md` — this audit only confirms the source unit has `ExecStart=__REPO__` (`:50`) + `WantedBy=graphical-session.target` (`:86`) so install.sh's sed + stale-symlink-cleanup have the right targets |
| `voice_typing/launch_daemon.sh` wrapper internals | P1.M4.T2.S1 | `gap_launch_daemon.md` — install.sh EXECUTES it via the unit (transitively); its compliance is T2.S1's |
| `voice_typing/cuda_check.py` probe (get_cuda_device_count / CPU fallback) | P1.M1.T4.S1 | `gap_cuda_check.md` — install.sh only INVOKES cuda_check (`:89`); its verdict semantics are M1.T4.S1's |
| `voice_typing/status.sh` (the helper install.sh's snippet references) | P1.M3.T2.S3 | `gap_status_sh.md` — this audit only confirms install.sh's printed snippet POINTS AT it + matches its doc + PRD §4.6 (§2) |
| `hypr-binds.conf` | P1.M4.T4.S1 | install.sh prints a `source = $REPO/hypr-binds.conf` instruction (`:217`); the binds file itself is T4.S1's |

## 6. Re-verification commands (two timeouts per AGENTS.md Rule 1; FULL paths — zsh aliases)

```bash
cd /home/dustin/projects/voice-typing
# (a)-(j) + extras — line-numbered evidence (re-locate live; do NOT trust these blindly):
grep -nE '\$UV" sync|==> \[1/7\]' install.sh                          # (a) uv sync            -> :64/:65
grep -nE '\-m voice_typing\.cuda_check|==> \[2/7\]|_setup_cuda_libs' install.sh  # (c) cuda smoke -> :85/:89/:72
grep -nE '\-m voice_typing\.prefetch|==> \[3/7\]' install.sh          # (b) prefetch           -> :101/:102
grep -nE 'cp "\$SRC_UNIT"|==> \[4/7\]' install.sh                     # (e) cp unit            -> :107/:115
grep -nE "sed -i .s#__REPO__" install.sh                              # (d) sed __REPO__       -> :119
grep -nE 'daemon-reload|enable voice-typing|restart voice-typing' install.sh  # (f)            -> :120/:125/:129
grep -nE 'default\.target\.wants/voice-typing' install.sh             # (g) stale symlink      -> :124
grep -nE 'CFG_DIR/config\.toml|==> \[5/7\]' install.sh                # (h) config copy        -> :164/:167
grep -nE 'ln -s "\$REPO/\.venv/bin/voicectl"|\(6b\)' install.sh       # VT-003 launcher        -> :174/:190
grep -nE 'status-interval 1|status-right.*status\.sh' install.sh      # (i) tmux snippet       -> :213/:214
grep -nE 'HTTP Request: GET https://huggingface\.co|offline check' install.sh  # offline guard -> :156/:160
grep -nE 'set -euo pipefail' install.sh                               # robustness             -> :25
# source unit has the __REPO__ placeholder + the graphical-session WantedBy (install.sh's targets):
grep -nE 'ExecStart=__REPO__|WantedBy=graphical' systemd/voice-typing.service   # -> :50/:86
# the named install.sh test functions (coverage map §4):
grep -nE '^def test_install_sh|^def test_systemd_unit_execstart_uses_repo_placeholder' tests/test_systemd_unit.py
# confirm NO test pins the core flow (headline gap §4):
grep -qE 'def test_.*(uv_sync|uv sync|prefetch_invoke|cuda_smoke_invoke|daemon.reload.*enable|config_copy|install_core)' tests/test_systemd_unit.py && echo "a core-flow test EXISTS (update §4)" || echo "no core-flow test (coverage gap §4 confirmed)"
# the contract's run command (record the LIVE count — do NOT hard-code):
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q     # this round: 15 passed
```

## 7. Tooling / AGENTS.md notes

- **READ-ONLY AUDIT.** Do NOT edit install.sh / the unit / launch_daemon.sh / prefetch.py /
  cuda_check.py / status.sh / PRD.md / any source. install.sh is compliant — the ONLY artifact
  change is CREATING `plan/006_862ee9d6ef41/architecture/gap_install.md` (NEW — it does not exist;
  confirmed: architecture/ has gap_config/cuda_check/daemon_loop/feedback/lifecycle/lite/recorder_
  kwargs/socket/status_sh/systemd/textproc/typing/voicectl but NO gap_install).
- **NEVER run install.sh** (AGENTS.md Rule 2 — it `systemctl --user restart`s the daemon, rebinds
  nothing global but restarts a foreground-blocking service + touches ~/.config). The audit READS
  the file + runs the pure-stdlib test suite (NO live install, NO daemon, NO mic, NO model load).
- **FULL paths** for tooling (zsh aliases python/pytest→uv run): `.venv/bin/python -m pytest …`.
  ruff at /home/dustin/.local/bin/ruff is OPTIONAL (install.sh is bash — ruff/mypy don't apply;
  `shellcheck` if present is a nice-to-have, NOT a gate).
- **Two timeouts** on the test (AGENTS.md Rule 1): inner `timeout 60` + the bash-tool `timeout`
  param above 60. (The suite is sub-second + pure-stdlib, but the rule is non-negotiable.)
- **Record the LIVE pytest count** (Critical #4 discipline, same as gap_systemd.md/gap_launch_
  daemon.md): this round = **15 passed**. Paste the real "N passed in Xs" line into §4.
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
- `install.sh` — the 220-line bash entrypoint. `set -euo pipefail` (`:25`); `UV="${UV:-$(command -v uv …)}"`
  (`:31`, no hardcoded `/home/dustin`); CWD-independent `SCRIPT_DIR`/`REPO` (`:36`-`37`); the
  `XDG_RUNTIME_DIR` + `command -v` preflight (`:40`-`43`); the portaudio preflight (`:53`-`58`).
  (a) `"$UV" sync` (`:65`, `==> [1/7]` `:64`). (c) the `_setup_cuda_libs` LD_LIBRARY_PATH reproduce
  (`:72`-`82`) + `"$PY" -m voice_typing.cuda_check` (`:89`, non-aborting `if !` `:88`, VERDICT
  parse `:92`-`99`). (b) `"$PY" -m voice_typing.prefetch` (`:102`, warn-only). (e) `cp "$SRC_UNIT"
  "$USER_UNIT_DIR/voice-typing.service"` (`:115`). (d) `sed -i "s#__REPO__#$REPO#g"` on the copy
  (`:119`). (f) `daemon-reload` (`:120`) + `enable` (`:125`) + `restart` (`:129`). (g) `rm -f
  …/default.target.wants/voice-typing.service` (`:124`, BEFORE enable). the offline regression guard
  (voicectl-status poll + journalctl huggingface.co grep, `:143`-`161`). (h) `config.toml` if-absent
  copy (`:167`-`172`). VT-003 launcher `ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER"` (`:190`,
  if-absent/foreign-check `:182`-`189`). (i) the tmux snippet `set -g status-interval 1` (`:213`) +
  `set -g status-right "#($REPO/voice_typing/status.sh)"` (`:214`) + the hypr `source=` instruction
  (`:217`).
- `tests/test_systemd_unit.py` — the 15-test suite (the contract's run command); pure-stdlib re+pathlib.
- `voice_typing/status.sh` — the helper install.sh's snippet references (its USER INTEGRATION block is the
  DOCS cross-reference; its internals audited by P1.M3.T2.S3).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §5 (the 7 install steps) + §4.9 (the unit + the
  install.sh mandate) + §4.6 (the status.sh-helper DOCS mandate) + §8 risk row #1 (cuDNN).

**Bottom line:** ✅ `install.sh` is **COMPLIANT** with PRD §5 + the work-item contract + VT-003/VT-004 —
all 10 contract points present + correct, the DOCS tmux-snippet point PASSES (3-way match install.sh ↔
status.sh ↔ PRD §4.6), the unit's source `__REPO__` + `WantedBy=graphical-session.target` are exactly what
the sed + stale-symlink-cleanup target, and the suite is green (**15 passed in 0.01s**, re-run live).
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

### Observed output (re-verified against the live tree this round)

```
==> [1/7] uv sync                    :64    "$UV" sync                  :65
==> [2/7] CUDA smoke                 :85    "$PY" -m voice_typing.cuda_check :89  (_setup_cuda_libs :72-82)
==> [3/7] prefetch models            :101   "$PY" -m voice_typing.prefetch  :102
==> [4/7] install systemd user service :107 cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service" :115
  sed -i "s#__REPO__#$REPO#g" "$USER_UNIT_DIR/voice-typing.service" :119
  systemctl --user daemon-reload     :120
  rm -f …/default.target.wants/voice-typing.service :124   (BEFORE enable)
  systemctl --user enable voice-typing.service :125
  systemctl --user restart voice-typing.service :129      (restart = start-superset)
==> [5/7] config                     :164   if [ ! -f $CFG_DIR/config.toml ] cp … :167-172
(6b) ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER" :190    (if-absent/foreign-check :182-189)
[7/7] set -g status-interval 1       :213   set -g status-right "#($REPO/voice_typing/status.sh)" :214
ExecStart=__REPO__/voice_typing/launch_daemon.sh  (systemd/voice-typing.service :50)
WantedBy=graphical-session.target                  (systemd/voice-typing.service :86)
(no core-flow test — coverage gap §5.4)
15 passed in 0.01s
```

---

## 2. Per-contract-point Compliance Table (work-item contract / PRD §5 vs `install.sh`)

| # | contract requirement | expected | actual (install.sh:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| (a) | `uv sync` (PRD §5 step 4; deps already in pyproject) | the idempotent materialization of pyproject deps | `"$UV" sync` (`:65`, `==> [1/7] uv sync` `:64`) | none — **coverage gap §5.4** | ✅ |
| (b) | prefetch.py called OR `huggingface_hub.snapshot_download` (both models) | `python -m voice_typing.prefetch`, warn-only | `"$PY" -m voice_typing.prefetch` (`:102`, `==> [3/7]` `:101`, warn-only `if !`) | none — **coverage gap §5.4** (prefetch.py INTERNALS = P1.M4.T3.S2) | ✅ |
| (c) | CUDA smoke (`ctranslate2.get_cuda_device_count`) | `python -m voice_typing.cuda_check`, non-aborting on cpu-fallback | `"$PY" -m voice_typing.cuda_check` (`:89`, under `_setup_cuda_libs` `:72`-`82` reproducing launch_daemon.sh's LD_LIBRARY_PATH; non-aborting `if !` `:88`; VERDICT parse `:92`-`99`) | none — **coverage gap §5.4** (cuda_check probe = P1.M1.T4.S1) | ✅ |
| (d) | `sed` `__REPO__` → actual path on the COPIED unit (VT-003) | `sed -i s|__REPO__|$REPO|` AFTER `cp`, on the COPY (git template stays generic) | `sed -i "s#__REPO__#$REPO#g" "$USER_UNIT_DIR/voice-typing.service"` (`:119`, after `cp` `:115`); source unit `ExecStart=__REPO__/…` (`systemd/voice-typing.service:50`) | `test_install_sh_substitutes_repo_placeholder` (`:280`) + `test_systemd_unit_execstart_uses_repo_placeholder` (`:266`) | ✅ |
| (e) | `cp` unit to `~/.config/systemd/user/` (honors XDG) | `cp` to the systemd user dir | `cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service"` (`:115`); `USER_UNIT_DIR="$XDG_CONFIG_HOME/systemd/user"` (`:113`) — MORE correct than hardcoded `~/.config` (§5.2) | none direct — **coverage gap §5.4** | ✅ |
| (f) | `daemon-reload` + `enable` + `start` | reload + enable + (re)start the unit | `daemon-reload` (`:120`) + `enable voice-typing.service` (`:125`) + `restart voice-typing.service` (`:129`) — uses **restart** = start-superset (applies a freshly-copied unit to a running one + idempotent; §5.1) | none — **coverage gap §5.4** (live systemctl, not unit-testable) | ✅ |
| (g) | remove stale `default.target.wants` symlink (VT-004) | `rm -f` the old symlink BEFORE enable (systemctl enable/disable key off the CURRENT [Install]) | `rm -f "$USER_UNIT_DIR/default.target.wants/voice-typing.service" 2>/dev/null \|\| true` (`:124`) — BEFORE `enable` (`:125`); the unit's `WantedBy=graphical-session.target` (`:86`) | `test_install_sh_cleans_stale_default_target_symlink` (`:362`) | ✅ |
| (h) | copy `config.toml` to `$XDG_CONFIG_HOME/voice-typing/` IF ABSENT | copy only when absent (never clobber user edits) | `if [ ! -f "$CFG_DIR/config.toml" ]; then cp "$REPO/config.toml" …; else echo "kept existing … (not overwritten)"` (`:167`-`172`) — idempotent | none — **coverage gap §5.4** | ✅ |
| (i) | print tmux snippet + usage (Mode A docs) | the `[7/7]` usage + tmux + hypr block | usage (`:208`-`211`) + `set -g status-interval 1` (`:213`) + `set -g status-right "#($REPO/voice_typing/status.sh)"` (`:214`) + `source = $REPO/hypr-binds.conf` (`:217`) | `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:223`) — pins the 7 commands + keybinds | ✅ |
| (j) | idempotent (safe to re-run) | every step safe on a 2nd run | structural: `uv sync` refreshes; prefetch cached; `restart` not `start`; config **if-absent** (`:167`); launcher **if-absent/foreign-check** (`:182`-`189`); stale-symlink `rm -f` (`:124`); cuda smoke + prefetch warn-only | none — **coverage gap §5.4** (idempotency is structural, asserted by read) | ✅ |

> All 10 contract points **PASS**. The file:line numbers above are `grep -n`-verified against the live tree
> this round. The 7 untested points are confirmed correct by direct read; the gap is recorded as a
> non-blocking coverage observation in §5.4.

### Robustness extras (compliant, beyond the 10 contract points — recorded so they are not "simplified" away)

| extra | actual (install.sh:line) | why it matters | tested? |
|---|---|---|---|
| `set -euo pipefail` | `:25` | fail-fast on error/unset-var/broken-pipe | no |
| `UV="${UV:-$(command -v uv \|\| echo "$HOME/.local/bin/uv")}"` (VT-003) | `:31` | NO hardcoded `/home/dustin`; honors `UV=` override; bash shebang (no zsh aliases) | yes (`:293`) |
| CWD-independent `SCRIPT_DIR`/`REPO` | `:36`-`37` | works from any cwd | no |
| `XDG_RUNTIME_DIR` + `command -v` preflight | `:40`-`43` | `systemctl --user` + the daemon's socket need it; actionable error | no |
| portaudio preflight (pacman -Q; PRD §5 step 2) | `:53`-`58` | PyAudio dlopen dep; non-Arch warn-and-continue; `if !`/`elif !` set-e-safe | no |
| `restart` (not `start`) | `:129` | applies a freshly-copied unit to a running one + idempotent (§5.1) | no |
| offline regression guard (post-restart journal grep for huggingface.co HTTP) | `:143`-`161` | asserts HF_HUB_OFFLINE=1 active at runtime; warn-only, set-e-safe | yes (`:205`) |
| stale `realtimesst.log` removal | `:133`-`138` | housekeeping for pre-`no_log_file` runs; gitignored | no |
| VT-003 voicectl launcher `$HOME/.local/bin/voicectl → $REPO/.venv/bin/voicectl` | `:174`-`191` | hypr-binds.conf uses `$HOME/.local/bin/voicectl`; only-create-if-absent + warn-on-foreign | yes (`:306` — presence only, not the branches) |

---

## 3. The DOCS point: printed tmux snippet ↔ `status.sh` ↔ PRD §4.6 (3-way MATCH)

The item's explicit DOCS mandate: *"install.sh prints the tmux status snippet and usage instructions —
verify the printed snippets are current and match `status.sh` and PRD §4.6."*

| source | what it says | note |
|---|---|---|
| **install.sh** (`:213`-`214`) | `set -g status-interval 1` + `set -g status-right "#($REPO/voice_typing/status.sh)"` | `$REPO` is the REAL expanded repo path at install time |
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
...............                                                          [100%]
15 passed in 0.01s
```

The suite (15 tests) is pure-stdlib `re`/`pathlib`: it parses `systemd/voice-typing.service` +
`voice_typing/launch_daemon.sh` + `install.sh` + `hypr-binds.conf` — no GPU/CUDA/daemon/mic. **6 tests
pin install.sh-specific concerns** (all bugfix-additions / VT-* wiring / Mode-A-docs): `test_install_sh_
substitutes_repo_placeholder` (`:280`, (d)), `test_install_sh_uv_path_is_portable` (`:293`,
VT-003), `test_install_sh_installs_stable_voicectl_launcher` (`:306`, VT-003 launcher-presence),
`test_install_sh_cleans_stale_default_target_symlink` (`:362`, (g)), `test_install_sh_offline_grep_
and_summary` (`:205`, the offline guard), `test_install_sh_usage_lists_all_commands_and_correct_
keybinds` (`:223`, (i)); + `test_systemd_unit_execstart_uses_repo_placeholder` (`:266`, source-side
`__REPO__`). **Coverage gap**: NO test pins the CORE flow (a) `uv sync`, (b) prefetch invoke, (c) cuda-
smoke invoke, (e) `cp` unit, (f) `daemon-reload`/`enable`/`restart`, (h) config-copy, (j) idempotency,
or the launcher's if-absent/foreign BRANCHES (§5.4).

---

## 5. Non-defect nuances (so they are not mistaken for gaps)

### 5.1 `restart` (not `start`) is a deliberate start-SUPERSET (contract point (f))
The contract says "start"; install.sh uses `systemctl --user restart voice-typing.service` (`:129`).
`restart` is strictly more correct for an installer: it BOTH starts a stopped unit AND applies a freshly-
copied unit to an already-running one (so a re-install actually picks up the new unit file), and it is
idempotent. The in-script comment documents this. ✅

### 5.2 `$XDG_CONFIG_HOME` (not hardcoded `~/.config`) is MORE correct (contract point (e)/(h))
The contract says "~/.config/systemd/user/" and "$XDG_CONFIG_HOME/voice-typing/". install.sh sets
`XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"` (`:61`) and uses `$XDG_CONFIG_HOME/systemd/user` (`:113`)
+ `$XDG_CONFIG_HOME/voice-typing` (`:165`) — honoring an explicit XDG override (mirroring
`voice_typing/config.py`'s search order) while defaulting to `~/.config`. ✅

### 5.3 `sed -i` on the COPY keeps the git template generic (contract point (d))
install.sh `cp`s the unit into `$XDG_CONFIG_HOME/systemd/user/` FIRST (`:115`) and only THEN
`sed -i "s#__REPO__#$REPO#g"` the COPY (`:119`). The source `systemd/voice-typing.service` in git
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
`set -euo pipefail` (`:25`) makes the script fail-fast on real errors, but several steps legitimately
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
`/home/dustin`) + the stable launcher symlink are in place, and the suite is green (**15 passed in 0.01s**).
**No source files were modified.** The audit's value-add = the headline §5.4 coverage gap (the CORE
install flow is verified by read, not by test) — recorded so a regression cannot ship silently. Ties to
PRD §5 (the 7 install steps), §4.9 (the unit + the install.sh mandate), §4.6 (the status.sh-helper DOCS
mandate), and §8 risk row #1 (the cuDNN wrapper install.sh's cuda-smoke reproduces). Acceptance criteria
for installability (a user can `git clone` → `./install.sh` → running un-armed daemon) are met.
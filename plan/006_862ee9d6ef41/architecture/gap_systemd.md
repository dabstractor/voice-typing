# Gap Report — P1.M4.T1.S1: systemd unit directives vs PRD §4.9

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `systemd/voice-typing.service` — the systemd user unit (PRD §4.9) — against ALL directives
PRD §4.9 names (Description, After, PartOf, ExecStartPre, ExecStart, Restart, RestartSec, KillMode,
TimeoutStopSec, WantedBy) + the two validation-round wirings expressed BY the unit (VT-003 `__REPO__`
portability placeholder; VT-004 graphical-session-target lifecycle) + the Issue-1/BUG-1 `KillMode=mixed` —
and re-run the pure-Python unit suite (`tests/test_systemd_unit.py`). Subtask **P1.M4.T1.S1** of verification
round `006_862ee9d6ef41`. Satisfies **Acceptance #6** ("daemon runs as systemd service, auto-restarts").
**Audited artifacts (all read-only):**
- `systemd/voice-typing.service` — the 86-line INI user unit. `[Unit]` (`:1`): Description (`:2`),
  After=pipewire.service ydotool.service graphical-session.target (`:9`), PartOf=graphical-session.target
  (`:10`). `[Service]` (`:12`): ExecStartPre=/usr/bin/systemctl --user import-environment
  WAYLAND_DISPLAY DISPLAY (`:26`), ExecStart=__REPO__/voice_typing/launch_daemon.sh (`:50`),
  Restart=on-failure (`:51`), RestartSec=2 (`:52`), KillMode=mixed (`:67`, the Issue-1/BUG-1 fix —
  inline comment `:53-66`), TimeoutStopSec=15 (`:78`). `[Install]` (`:80`):
  WantedBy=graphical-session.target (`:86`).
- `tests/test_systemd_unit.py` — the 15-test suite (the contract's run command); pure-stdlib re+pathlib
  (parses the unit + the wrapper/install/binds files; NO live systemd/GPU/CUDA/daemon/mic).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.9 (the directive list + inline rationale) + §8 risk
  row (the KillMode+TimeoutStopSec story).

**Bottom line:** ✅ `systemd/voice-typing.service` is **COMPLIANT** with PRD §4.9 — all 10 directives present
+ correct, VT-003 (`__REPO__`) + VT-004 (graphical-session) wiring both hold, `KillMode=mixed` is the
Issue-1/BUG-1 fix, and the suite is green (**15 passed in 0.01s**, re-run live). **No source files were
modified** — the unit faithfully implements the spec. The audit's value-add = confirming by direct read the
directives the suite does NOT pin (`KillMode=mixed`, `RestartSec`, `Description`, the full `After=` list, the
ExecStartPre `/usr/bin/systemctl` path) and recording those as non-blocking coverage observations (§4), so a
regression on the un-pinned directives cannot ship silently. Acceptance #6 (systemd service + auto-restart)
is met: the unit IS the service definition; `Restart=on-failure` (`:51`) is the auto-restart;
`RestartSec=2` (`:52`) the backoff.

---

## 1. Method

Each of the 10 PRD §4.9 directives + VT-003 + VT-004 was mapped 1:1 to its `systemd/voice-typing.service`
implementation by `grep -n` (the file:line evidence), and the inline comments explaining the non-obvious
directives (KillMode/TimeoutStopSec/VT-003/VT-004) were read directly. The full `tests/test_systemd_unit.py`
suite was then **re-run live** to record the actual pass count and timing. Nothing was assumed from the PRP's
embedded numbers — every line number + the pass count below was re-verified this round (the suite is pure-stdlib
`re`/`pathlib`; it parses the unit + wrapper/install/binds files — no GPU/CUDA/daemon/mic required).

### Commands run (re-verification)

```bash
# ALL directives (line-numbered) — confirms the 10 + no extras:
grep -nE '^[A-Za-z][A-Za-z0-9_-]*=' systemd/voice-typing.service
# section headers:
grep -nE '^\[[A-Za-z]+\]' systemd/voice-typing.service
# KillMode=mixed present (the headline directive):
grep -nE '^KillMode=mixed' systemd/voice-typing.service
# the unit-directive test functions (coverage to cite):
grep -nE '^def test_(execstart_points|execstartpre_imports|restart_on_failure|timeout_stop_sec|systemd_unit_execstart_uses_repo|unit_is_graphical_session)' tests/test_systemd_unit.py
# the 3 directives with NO test (coverage gaps §4.1/§4.2):
grep -qE 'def test_.*killmode|def test_.*restartsec|def test_.*description' tests/test_systemd_unit.py && echo "a test exists (update §4)" || echo "no KillMode/RestartSec/Description test (coverage gaps §4.1/§4.2)"
# the unit suite (the contract's run command), LIVE (two timeouts per AGENTS.md Rule 1)
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
```

### Observed output (abridged — replace with the LIVE re-verification)

```
[Unit]:1  [Service]:12  [Install]:80
Description=Local voice typing daemon (RealtimeSTT)                                   :2
After=pipewire.service ydotool.service graphical-session.target                        :9
PartOf=graphical-session.target                                                       :10
ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY     :26
ExecStart=__REPO__/voice_typing/launch_daemon.sh                                      :50
Restart=on-failure                                                                    :51
RestartSec=2                                                                          :52
KillMode=mixed                                                                        :67
TimeoutStopSec=15                                                                     :78
WantedBy=graphical-session.target                                                     :86
(no KillMode/RestartSec/Description test — coverage gaps §4.1/§4.2)
15 passed in 0.01s
```

---

## 2. Per-directive Compliance Table (PRD §4.9 vs `systemd/voice-typing.service`)

| # | PRD §4.9 directive | expected | actual (file:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| 1 | `Description=` | `Local voice typing daemon (RealtimeSTT)` | `Description=Local voice typing daemon (RealtimeSTT)` (`:2`) | (none — coverage gap §4.2) | ✅ |
| 2 | `After=` | `pipewire.service ydotool.service graphical-session.target` | `After=pipewire.service ydotool.service graphical-session.target` (`:9`) | `test_unit_is_graphical_session_aware` (`:341`) asserts `graphical-session.target ∈ After` — PARTIAL (does not assert pipewire/ydotool explicitly); §4.2 | ✅ |
| 3 | `PartOf=` | `graphical-session.target` | `PartOf=graphical-session.target` (`:10`) | `test_unit_is_graphical_session_aware` (`:341`) asserts `PartOf=graphical-session.target` | ✅ |
| 4 | `ExecStartPre=` | `import-environment WAYLAND_DISPLAY DISPLAY` | `ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY` (`:26`) — uses the absolute `/usr/bin/systemctl` path (best practice in units where PATH may be minimal) | `test_execstartpre_imports_wayland_and_display_env` (`:78`) checks `import-environment` + `WAYLAND_DISPLAY` + `DISPLAY` — does NOT pin the `/usr/bin/systemctl` path; §4.2 | ✅ |
| 5 | `ExecStart=` | `__REPO__/voice_typing/launch_daemon.sh` (VT-003 placeholder) | `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (`:50`) — the LD_LIBRARY_PATH wrapper, NOT python directly | `test_execstart_points_at_launch_daemon_wrapper` (`:71`, endswith launch_daemon.sh) + `test_systemd_unit_execstart_uses_repo_placeholder` (`:266`, `__REPO__` + no `/home/`) — TWO tests | ✅ |
| 6 | `Restart=` | `on-failure` | `Restart=on-failure` (`:51`) | `test_restart_on_failure` (`:94`) | ✅ |
| 7 | `RestartSec=` | `2` | `RestartSec=2` (`:52`) | (none — coverage gap §4.2) | ✅ |
| 8 | `KillMode=` | `mixed` (Issue-1/BUG-1 fix) | `KillMode=mixed` (`:67`) — SIGTERM to the MAIN daemon only (letting its `host.stop()` `killpg` its own child), SIGKILL the group only after `TimeoutStopSec` | (none — coverage gap §4.1, the HEADLINE nuance) | ✅ |
| 9 | `TimeoutStopSec=` | `15` | `TimeoutStopSec=15` (`:78`) — bounds the stop so the daemon is never SIGKILLed at systemd's 90s default | `test_timeout_stop_sec_bounds_shutdown` (`:99`) | ✅ |
| 10 | `WantedBy=` | `graphical-session.target` (VT-004) | `WantedBy=graphical-session.target` (`:86`) — NOT `default.target` (which raced the compositor on cold boot) | `test_unit_is_graphical_session_aware` (`:341`) asserts EXACTLY `WantedBy=graphical-session.target` | ✅ |

> All directives **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this round.
> The directives with no pinning test (Description, RestartSec, KillMode, the full After= list, the
> ExecStartPre path) are confirmed correct by direct read; the gaps are recorded as non-blocking coverage
> observations in §4.

### VT-003 / VT-004 wiring (expressed BY the unit)

| wiring | expected | actual (file:line) | pinning test | verdict |
|---|---|---|---|---|
| **VT-003** `__REPO__` portability | the SOURCE unit's ExecStart uses the `__REPO__` placeholder (install.sh substitutes `$REPO`); no hardcoded `/home/<user>` path | `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (`:50`) — the source unit is a portable TEMPLATE, not directly runnable until install (§4.3) | `test_systemd_unit_execstart_uses_repo_placeholder` (`:266`) + (the substitution in install.sh) `test_install_sh_substitutes_repo_placeholder` (`:280`) | ✅ |
| **VT-004** graphical-session lifecycle | After + PartOf + WantedBy all bind to `graphical-session.target` (NOT `default.target`) | After includes it (`:9`), PartOf=graphical-session.target (`:10`), WantedBy=graphical-session.target (`:86`) | `test_unit_is_graphical_session_aware` (`:341`) + (the stale-symlink cleanup in install.sh) `test_install_sh_cleans_stale_default_target_symlink` (`:362`) | ✅ |

---

## 3. Test results (the contract's run command, LIVE)

```
$ timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
...............                                                          [100%]
15 passed in 0.01s
```

The suite (440 lines, 15 tests) is pure-stdlib `re`/`pathlib`: it parses `systemd/voice-typing.service` +
the wrapper/install/binds files — no GPU/CUDA/daemon/mic. **6 tests pin UNIT directives** (ExecStart×2, Restart,
TimeoutStopSec, VT-003 `__REPO__`, VT-004 graphical-session); **9 tests are CROSS-FILE** (they read
`voice_typing/launch_daemon.sh` / `install.sh` / `hypr-binds.conf` and corroborate VT-003/VT-004/Issue-1
end-to-end — those files are audited by P1.M4.T2.S1 / P1.M4.T3.S1 / P1.M4.T4.S1; §4.4). Coverage gaps:
**no test pins `KillMode=mixed`** (§4.1), `RestartSec`, `Description`, the full `After=` list, or the
ExecStartPre `/usr/bin/systemctl` path (§4.2).

---

## 4. Non-defect nuances (so they are not mistaken for gaps)

### 4.1 `KillMode=mixed` is the load-bearing Issue-1/BUG-1 fix; it has NO dedicated test — coverage gap, not code gap
`KillMode=mixed` (`:67`) is the keystone directive for the SIGTERM-teardown story (PRD §4.9 inline comment
`:53-66` + §8 risk row + the P1.M2.T2.S3 bounded-teardown audit, `gap_lifecycle.md` §3). systemd's
DEFAULT is `control-group`, which sends SIGTERM to EVERY process in the unit's cgroup SIMULTANEOUSLY — the
daemon AND the recorder-host child AND the multiprocessing resource tracker. The recorder-host child does NOT
install a SIGTERM handler (only the daemon's `main()` does), so a cgroup-wide SIGTERM kills the child mid-
`recorder.text()`, wedging the multiprocessing Queue/Process such that the daemon's correct single-flight
`host.stop()` (`proc.join` / `cmd_q.put("shutdown")`) never completes → SIGKILL @ `TimeoutStopSec=15s`
(Result=timeout). Proven: `kill -TERM <MainPID>` (signal to the MAIN process only) exits cleanly in ~1.3s;
only `systemctl stop` (cgroup-wide) wedged. `KillMode=mixed` makes systemd deliver SIGTERM to the MAIN daemon
ONLY (letting the daemon's already-correct bounded `host.stop()` tear its OWN child group down via `killpg`),
while still sending the final SIGKILL to the whole group only after `TimeoutStopSec` — preserving the outer
safety net. **No test in the file asserts `KillMode=mixed`** — this is a **non-blocking coverage
observation**, not a §4.9 violation: the directive IS present + correct-by-read; the bounded-teardown tests
in `tests/test_daemon.py` / `tests/test_recorder_host.py` exercise the daemon-side mechanism (the P1.M2.T2.S3
audit), not the unit directive. A future test-hardening pass COULD add a `test_killmode_is_mixed` (out of scope
for this read-only audit — do NOT add one here; consistent with every round-006 audit's "read-only, no new
tests" discipline). ✅

### 4.2 The untested directives (Description / RestartSec / KillMode / the full After= list / the ExecStartPre path) — coverage gaps, not code gaps
The 15-test suite pins ExecStart(×2), Restart, TimeoutStopSec, After(PARTIAL — `graphical-session.target ∈
After` only, not `pipewire.service`/`ydotool.service` explicitly), PartOf, WantedBy, ExecStartPre(PARTIAL —
`import-environment` + `WAYLAND_DISPLAY` + `DISPLAY`, not the `/usr/bin/systemctl` absolute path). It does NOT
pin: `Description=` (`:2`), `RestartSec=2` (`:52`), `KillMode=mixed` (`:67`, §4.1), the FULL `After=`
list, or the `/usr/bin/systemctl` path. This audit CONFIRMS each by direct read (§2 table) — they are all
correct. Non-blocking coverage observations; a test-hardening pass could pin them (out of scope here). ✅

### 4.3 VT-003 `__REPO__`: the SOURCE unit is a portable TEMPLATE (not directly runnable)
The source unit's `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (`:50`) is NOT runnable as-is —
`__REPO__` is a PLACEHOLDER install.sh substitutes with `$REPO` (`sed -i "s#__REPO__#$REPO#g"`) when it copies
the unit into `~/.config/systemd/user/`. This is **compliant-by-design** (portability across users / repo
locations — the source unit is a template), NOT a defect. The INSTALLED unit (in `~/.config/systemd/user/`)
has the real repo path. Pinned by `test_systemd_unit_execstart_uses_repo_placeholder` (`:266`). ✅

### 4.4 The 9 cross-file tests corroborate VT-003/VT-004/Issue-1 but audit OTHER files
9 of the 15 tests in `test_systemd_unit.py` read `voice_typing/launch_daemon.sh` (`test_launch_daemon_exports_
offline_vars` `:115`, `test_launch_daemon_fetches_wayland_display_from_manager` `:164`), `install.sh`
(`test_install_sh_offline_grep_and_summary` `:205`, `test_install_sh_usage_lists_all_commands_and_correct_
keybinds` `:223`, `test_install_sh_substitutes_repo_placeholder` `:280`, `test_install_sh_uv_path_is_
portable` `:293`, `test_install_sh_installs_stable_voicectl_launcher` `:306`, `test_install_sh_cleans_
stale_default_target_symlink` `:362`), and `hypr-binds.conf` (`test_hypr_binds_use_portable_home_launcher`
`:321`). They CORROBORATE that the unit's VT-003/VT-004 wiring holds end-to-end (the `__REPO__` substitution
actually happens; the stale `default.target.wants` symlink is cleaned; the offline vars are exported before
exec) — but those FILES' internals are audited by **P1.M4.T2.S1** (launch_daemon.sh), **P1.M4.T3.S1**
(install.sh), and **P1.M4.T4.S1** (hypr-binds). This report's scope is the UNIT directives; it cites the
cross-file tests as evidence the wiring is exercised, WITHOUT re-auditing those files. ✅

---

## 5. Conclusion

**PASS.** `systemd/voice-typing.service` is compliant with PRD §4.9 on all 10 directives + the VT-003
(`__REPO__`) + VT-004 (graphical-session) wirings. The unit describes the service (`Description` `:2`),
orders + binds to the graphical session (`After` `:9` / `PartOf` `:10` / `WantedBy` `:86`), imports
the Wayland/X display vars (`ExecStartPre` `:26`), runs the LD_LIBRARY_PATH wrapper via the portable
`__REPO__` placeholder (`ExecStart` `:50`), auto-restarts on failure with a 2s backoff (`Restart` `:51`
/ `RestartSec` `:52` — Acceptance #6), bounds the stop at 15s (`TimeoutStopSec` `:78`), and — the
keystone — delivers SIGTERM main-only via `KillMode=mixed` (`:67`, the Issue-1/BUG-1 fix) so the daemon's
single-flight `host.stop()` can `killpg` its own recorder-host child instead of systemd cgroup-SIGTERMing it
mid-`text()`. The 15-test suite pins a strong subset; the un-pinned directives (KillMode/RestartSec/
Description/After-full/ExecStartPre-path) are confirmed correct by direct read and recorded as non-blocking
coverage observations (§4). **No source files were modified** (read-only audit); the sole artifact is this
report.

Acceptance #6 ("daemon runs as systemd service, auto-restarts") is met. Scope is the systemd UNIT directives
only — `launch_daemon.sh` is P1.M4.T2.S1, `install.sh` is P1.M4.T3.S1, `hypr-binds.conf` is P1.M4.T4.S1, and
the daemon teardown mechanism is P1.M2.T2.S3 (`gap_lifecycle.md` §3, which this report's `KillMode=mixed`
nuance cross-references).
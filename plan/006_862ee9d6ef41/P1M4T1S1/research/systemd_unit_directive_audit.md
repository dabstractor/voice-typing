# Research Brief: systemd unit directive audit (P1.M4.T1.S1)

**Status:** VERIFIED against the live `systemd/voice-typing.service` on 2026-07-18. The unit is
**PRD §4.9-COMPLIANT** — all 10 directives present + correct, and `tests/test_systemd_unit.py` is
**15 passed in 0.01s** (re-run live this round). This is a **READ-ONLY AUDIT**: the deliverable is a
new `gap_systemd.md` report; NO source is modified. Mirrors the `gap_status_sh.md` / `gap_typing.md`
"CREATE a new gap report" pattern (this is a NEW file — no prior `gap_systemd.md` exists).

---

## 0. THE VERDICT — ✅ COMPLIANT (read-only audit; no fix)

`systemd/voice-typing.service` implements every directive PRD §4.9 names, plus the two validation-
round wirings (VT-003 `__REPO__` portability placeholder; VT-004 graphical-session-target lifecycle)
and the Issue-1/BUG-1 `KillMode=mixed`. The 15-test suite (re-run live: **15 passed in 0.01s**) pins
a strong subset. The directives the suite does NOT pin (Description / RestartSec / KillMode / the full
`After=` list / the `/usr/bin/systemctl` ExecStartPre path) are confirmed by direct read this round and
recorded as non-blocking coverage observations (§4) — not defects.

---

## 1. Directive-by-directive line map + verdict + pinning test

All line numbers are `grep -n`-verified against the live unit THIS round.

| # | PRD §4.9 directive | expected | actual (file:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| 1 | `Description=` | "Local voice typing daemon (RealtimeSTT)" | `systemd/voice-typing.service:2` `Description=Local voice typing daemon (RealtimeSTT)` | (none — coverage gap §4.2) | ✅ |
| 2 | `After=` | `pipewire.service ydotool.service graphical-session.target` | `:9` `After=pipewire.service ydotool.service graphical-session.target` | `test_unit_is_graphical_session_aware` (:341) checks `graphical-session.target ∈ After` — PARTIAL (does not assert pipewire/ydotool explicitly); §4.2 | ✅ |
| 3 | `PartOf=` | `graphical-session.target` | `:10` `PartOf=graphical-session.target` | `test_unit_is_graphical_session_aware` (:341) asserts `PartOf=graphical-session.target` | ✅ |
| 4 | `ExecStartPre=` | `import-environment WAYLAND_DISPLAY DISPLAY` | `:26` `ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY` | `test_execstartpre_imports_wayland_and_display_env` (:78) checks `import-environment` + `WAYLAND_DISPLAY` + `DISPLAY` — does NOT pin the `/usr/bin/systemctl` absolute path; §4.2 | ✅ |
| 5 | `ExecStart=` | `__REPO__/voice_typing/launch_daemon.sh` | `:50` `ExecStart=__REPO__/voice_typing/launch_daemon.sh` | `test_execstart_points_at_launch_daemon_wrapper` (:71, endswith launch_daemon.sh) + `test_systemd_unit_execstart_uses_repo_placeholder` (:266, `__REPO__` + no `/home/`) — TWO tests | ✅ |
| 6 | `Restart=` | `on-failure` | `:51` `Restart=on-failure` | `test_restart_on_failure` (:94) | ✅ |
| 7 | `RestartSec=` | `2` | `:52` `RestartSec=2` | (none — coverage gap §4.2) | ✅ |
| 8 | `KillMode=` | `mixed` | `:67` `KillMode=mixed` | (none — coverage gap §4.1, the HEADLINE nuance: KillMode=mixed is the Issue-1/BUG-1 fix) | ✅ |
| 9 | `TimeoutStopSec=` | `15` | `:78` `TimeoutStopSec=15` | `test_timeout_stop_sec_bounds_shutdown` (:99) | ✅ |
| 10 | `WantedBy=` | `graphical-session.target` | `:86` `WantedBy=graphical-session.target` | `test_unit_is_graphical_session_aware` (:341) asserts EXACTLY `WantedBy=graphical-session.target` | ✅ |

Section layout (verified): `[Unit]` :1, `[Service]` :12, `[Install]` :80. No extra/stale directives.

**Acceptance #6 mapping** ("daemon runs as systemd service, auto-restarts"): the unit IS the service
definition; `Restart=on-failure` (:51) is the auto-restart; `RestartSec=2` (:52) the backoff. ✅.

---

## 2. The two validation-round wirings expressed BY the unit

### VT-003 — `__REPO__` portability placeholder
- The SOURCE unit's `ExecStart` (:50) uses the literal `__REPO__` placeholder, NOT a hardcoded
  `/home/<user>` path. install.sh substitutes `__REPO__ → $REPO` (sed) when it copies the unit into
  `~/.config/systemd/user/`, so the INSTALLED ExecStart is portable across users / repo locations.
  → the source unit is NOT directly runnable until install.sh substitutes it (a deliberate template,
  not a bug). Pinned by `test_systemd_unit_execstart_uses_repo_placeholder` (:266) + (the substitution
  itself, in install.sh) `test_install_sh_substitutes_repo_placeholder` (:280).
- NOTE: the wider VT-003 portability surface (install.sh `UV=` resolution + `$HOME/.local/bin/voicectl`
  symlink + hypr-binds `$HOME` launcher) is cross-FILE and is audited by **P1.M4.T3.S1** (install.sh)
  + **P1.M4.T4.S1** (hypr-binds). THIS audit's VT-003 scope is the UNIT's `__REPO__` ExecStart only.

### VT-004 — graphical-session-target lifecycle (NOT default.target)
- The unit binds its lifecycle to `graphical-session.target` three ways: `After=` includes it (:9),
  `PartOf=graphical-session.target` (:10), `WantedBy=graphical-session.target` (:86). Rationale (unit
  inline comment :3-8): the compositor (Hyprland) exports `WAYLAND_DISPLAY`/`DISPLAY` into the user
  manager AT graphical-session startup; ordering after it makes `ExecStartPre=import-environment`
  MEANINGFUL (on the old `default.target` the cold-boot race made the import a silent no-op). WantedBy
  was migrated from `default.target`; install.sh removes the stale `default.target.wants` symlink.
  Pinned by `test_unit_is_graphical_session_aware` (:341) + (the stale-symlink cleanup, in install.sh)
  `test_install_sh_cleans_stale_default_target_symlink` (:362).

---

## 3. The test file — what it pins + the contract's run command

`tests/test_systemd_unit.py` (440 lines, **15 tests, 15 passed in 0.01s** — re-run live this round).
Pure-stdlib (`re` + `pathlib.read_text`); it parses the unit + the wrapper/install/binds files — NO
live systemd session, NO GPU/CUDA/daemon/mic. The contract's run command:
```
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q     # → 15 passed in 0.01s
```

Test → directive coverage (the rows in §1 cite these):
- `test_execstart_points_at_launch_daemon_wrapper` (:71) → ExecStart (launch_daemon.sh)
- `test_execstartpre_imports_wayland_and_display_env` (:78) → ExecStartPre (import + vars)
- `test_restart_on_failure` (:94) → Restart
- `test_timeout_stop_sec_bounds_shutdown` (:99) → TimeoutStopSec
- `test_systemd_unit_execstart_uses_repo_placeholder` (:266) → VT-003 ExecStart __REPO__
- `test_unit_is_graphical_session_aware` (:341) → VT-004 After/PartOf/WantedBy
- CROSS-FILE (corroborate VT-003/VT-004/Issue-1 but audit OTHER files — out of this task's scope):
  `test_launch_daemon_exports_offline_vars` (:115), `test_launch_daemon_fetches_wayland_display_from_manager`
  (:164) → `voice_typing/launch_daemon.sh` (audited by **P1.M4.T2.S1**); `test_install_sh_offline_grep_and_summary`
  (:205), `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (:223), `test_install_sh_substitutes_repo_placeholder`
  (:280), `test_install_sh_uv_path_is_portable` (:293), `test_install_sh_installs_stable_voicectl_launcher`
  (:306), `test_install_sh_cleans_stale_default_target_symlink` (:362) → `install.sh` (audited by
  **P1.M4.T3.S1**); `test_hypr_binds_use_portable_home_launcher` (:321) → `hypr-binds.conf` (audited
  by **P1.M4.T4.S1**).

> The contract says run the WHOLE file (`tests/test_systemd_unit.py`), so the report records all 15 —
> but the report's DIRECTIVE scope is the unit file only; the cross-file tests are cited as
> CORROBORATING evidence (they prove VT-003/VT-004 wiring holds end-to-end) WITHOUT re-auditing those
> files (their own tasks own that).

---

## 4. Non-defect nuances (the report's §4 — so they are not mistaken for gaps)

### §4.1 — `KillMode=mixed` is the load-bearing Issue-1/BUG-1 fix; it has NO dedicated test (coverage gap, NOT a code gap)
`KillMode=mixed` (:67) is the single most important directive for the SIGTERM-teardown story (PRD §4.9
+ §8 + the bounded-teardown audit P1.M2.T2.S3). systemd's DEFAULT is `control-group`, which SIGTERMs
EVERY process in the unit's cgroup simultaneously — the daemon AND the recorder-host child AND the
mp resource tracker. The child has NO SIGTERM handler, so a cgroup-wide SIGTERM kills it mid-
`recorder.text()`, wedging the multiprocessing Queue such that the daemon's correct single-flight
`host.stop()` never completes → SIGKILL @ TimeoutStopSec. `KillMode=mixed` makes systemd deliver
SIGTERM to the MAIN daemon ONLY (letting the daemon's `host.stop()` `killpg` its OWN child group),
then SIGKILL the whole group only after `TimeoutStopSec` (preserving the outer safety net). Proven
by the Issue-1 root cause (`kill -TERM <MainPID>` exits cleanly in ~1.3s; only `systemctl stop`
cgroup-wide wedged). **No test in the file asserts `KillMode=mixed`** — this is a non-blocking
coverage observation (the directive IS present + correct-by-read; the bounded-teardown tests in
`test_daemon.py`/`test_recorder_host.py` exercise the daemon-side mechanism, not the unit directive).
A future test-hardening pass COULD add a `test_killmode_is_mixed` (out of scope for this read-only
audit — do NOT add one here).

### §4.2 — the untested directives (Description / RestartSec / After-full-list / ExecStartPre-/usr/bin-path) — coverage gaps, not code gaps
The 15-test suite pins ExecStart(×2), Restart, TimeoutStopSec, After(partial), PartOf, WantedBy,
ExecStartPre(partial). It does NOT pin: `Description=` (:2), `RestartSec=2` (:52), `KillMode=mixed`
(:67, §4.1), the FULL `After=` list (it checks `graphical-session.target ∈ After` but not
`pipewire.service` + `ydotool.service` explicitly), or the `/usr/bin/systemctl` absolute path in
`ExecStartPre` (:26). This audit CONFIRMS each by direct read (§1 table) — they are all correct.
Non-blocking coverage observations; a test-hardening pass could pin them (out of scope here).

### §4.3 — VT-003 `__REPO__`: the SOURCE unit is a portable TEMPLATE (not directly runnable)
The source unit's `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (:50) is NOT runnable as-is —
`__REPO__` is a placeholder install.sh substitutes with `$REPO` at install time. This is
compliant-by-design (portability across users / repo locations), NOT a defect. The installed unit
(in `~/.config/systemd/user/`) has the real path. Pinned by
`test_systemd_unit_execstart_uses_repo_placeholder` (:266).

### §4.4 — cross-file tests in `test_systemd_unit.py` corroborate VT-003/VT-004 but audit OTHER files
8 of the 15 tests read `voice_typing/launch_daemon.sh` / `install.sh` / `hypr-binds.conf` (the offline-
vars exports, the WAYLAND fetch, the install steps, the `__REPO__` sed, the UV/voicectl/hypr portability,
the stale-symlink cleanup). They CORROBORATE that the unit's VT-003/VT-004 wiring holds end-to-end, but
those FILES' internals are audited by **P1.M4.T2.S1** (launch_daemon.sh), **P1.M4.T3.S1** (install.sh),
and **P1.M4.T4.S1** (hypr-binds). This report's scope is the UNIT directives; it cites the cross-file
tests as evidence the wiring is exercised, without re-auditing those files.

---

## 5. Scope boundaries (what this audit is NOT)

- **READ-ONLY.** No edit to `systemd/voice-typing.service` / `tests/test_systemd_unit.py` /
  `voice_typing/launch_daemon.sh` / `install.sh` / `hypr-binds.conf` / `PRD.md` / `tasks.json` /
  `prd_snapshot.md` / `.gitignore`. The unit is COMPLIANT; the ONLY artifact created is `gap_systemd.md`.
- **UNIT directives only.** NOT a launch_daemon.sh audit (P1.M4.T2.S1), NOT an install.sh audit
  (P1.M4.T3.S1), NOT a hypr-binds audit (P1.M4.T4.S1), NOT a daemon teardown audit (P1.M2.T2.S3 →
  `gap_lifecycle.md` §3). Cross-file tests are cited as corroborating evidence only.
- **No new tests.** Consistent with every round-006 audit's "read-only, no new tests" discipline. A
  test-hardening pass (pinning KillMode/RestartSec/Description) would be a SEPARATE task.
- The report goes in `plan/006_862ee9d6ef41/architecture/gap_systemd.md` (NEW file — mirrors
  `gap_status_sh.md` / `gap_typing.md`). There is NO prior `gap_systemd.md`.

---

## 6. Output location + format template

- **Deliverable**: `plan/006_862ee9d6ef41/architecture/gap_systemd.md` (NEW; CREATE, do not append —
  no prior file exists). Mirrors `gap_typing.md`'s structure exactly:
  `# Gap Report — P1.M4.T1.S1: …` title + `**Date:**` + `**Scope:**` + `**Audited artifacts (all
  read-only):**` + `**Bottom line:** ✅ …` + `## 1. Method` (commands run + observed output) +
  `## 2. Per-directive Compliance Table` (PRD §4.9 req | expected | actual file:line | pinning test |
  ✅) + `## 3. Test Results` (the live `15 passed` count) + `## 4. Mismatches / Drift / Notes` (the
  nuances §4.1-§4.4) + `## 5. Conclusion` (PASS; ties to acceptance #6).
- **My (PRP-author) research notes** go in `plan/006_862ee9d6ef41/P1M4T1S1/research/` (this file).

---

## 7. Tooling + AGENTS.md compliance

- **Two timeouts per AGENTS.md Rule 1.** `test_systemd_unit.py` is pure-stdlib + sub-second, but STILL
  wrap: `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` (inner GNU timeout) +
  set the bash-tool `timeout` param above it (outer harness backstop). This research did exactly that.
- **FULL PATHS** (zsh aliases `python`/`pytest` → `uv run`). Always `.venv/bin/python -m pytest`.
  mypy NOT installed (skip). ruff at `/home/dustin/.local/bin/ruff` is OPTIONAL (not in `.venv`; not a
  gate; the unit file is INI — ruff/mypy do not apply).
- The `.service` file is INI; `grep -nE '^[A-Za-z][A-Za-z0-9_-]*='` lists every directive (comments +
  blank lines excluded). The test's `_unit_lines()` helper does the same filtering.
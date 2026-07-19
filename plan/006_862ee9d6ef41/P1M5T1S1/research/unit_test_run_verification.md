# P1.M5.T1.S1 research — run pure-python unit tests (no CUDA)

## §0 Item type

This is a **test-EXECUTION** item (not a feature build, not a read-only audit). Contract: run 9 pure-
python test files (~196 tests), report pass/fail, **diagnose & fix failures** (source OR test), re-run
until green, and emit `test_results_unit.md`. The implementing agent MAY edit source/test files (unlike
the round-006 read-only `gap_*.md` audits) — but only if a test actually fails.

## §1 Verified baseline (LIVE this research session — the headline fact)

Exact contract command, run with AGENTS.md two-timeout discipline (inner `timeout 120` + outer bash
backstop 150):

```
timeout 120 .venv/bin/python -m pytest \
  tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
  tests/test_typing_backends.py tests/test_feedback.py tests/test_voicectl.py \
  tests/test_control_socket.py tests/test_status_sh.py tests/test_systemd_unit.py -q
```

**RESULT: `196 passed in 5.32s`, EXIT=0.** GREEN. No failures, no warnings, no skips. (The 5.32s wall
time confirms every one of these 9 files is genuinely pure-Python — a CUDA/model load would add minutes,
so no accidental CUDA leakage in this set.)

Per-file `pytest --collect-only` counts match the contract EXACTLY:

| file | contract says | collected (live) | match |
|---|---|---|---|
| test_config.py | 34 | 34 | ✓ |
| test_config_repo_default.py | 3 | 3 | ✓ |
| test_textproc.py | 21 | 21 | ✓ |
| test_typing_backends.py | 27 | 27 | ✓ |
| test_feedback.py | 38 | 38 | ✓ |
| test_voicectl.py | 32 | 32 | ✓ |
| test_control_socket.py | 21 | 21 | ✓ |
| test_status_sh.py | 5 | 5 | ✓ |
| test_systemd_unit.py | 15 | 15 | ✓ |
| **TOTAL** | **~196** | **196** | ✓ |

⇒ The PRP's expected outcome is **196 passed in ~5s**. The diagnosis/fix workflow is provided for the
case where a future drift or a flaky run surfaces a failure during the implementing agent's session (the
run happens later; state can drift between this research and execution).

## §2 Per-file coverage map (what each tests + the module under test + likely failure locus)

| test file | module under test | what it covers | PRD ref | if it fails, look at → |
|---|---|---|---|---|
| test_config.py (34) | `voice_typing.config` | dataclass schema, defaults, TOML overlay, search order, XDG resolution | §4.5 | config.py (source) — but a test encoding a PRD value is authoritative; fix the side that drifted from §4.5 |
| test_config_repo_default.py (3) | `config.toml` ↔ config.py | **DRIFT GUARD**: repo config.toml MUST equal dataclass defaults | §4.5 | config.toml OR config.py — realign the two (one drifted) |
| test_textproc.py (21) | `voice_typing.textproc.clean` | clean() 4-step spec (strip/normalize, min_chars, blocklist, return) = PRD test T2 | §4.7 / T2 | textproc.py (clean logic) or blocklist defaults |
| test_typing_backends.py (27) | `voice_typing.typing_backends` | wtype/ydotool/tmux impls + auto-fallback; subprocess MOCKED | §4.3 | typing_backends.py (backend selection/fallback) |
| test_feedback.py (38) | `voice_typing.feedback` | state.json schema, atomic writes, hyprctl notify events, throttling, phase/mode lifecycle | §4.6 | feedback.py (state writes/notify/throttle) |
| test_voicectl.py (32) | `voice_typing.ctl` | format_result pure logic, real-socket round-trip (ControlServer+_StubDaemon), exit codes 0/1/2 | §4.8 | ctl.py (formatting/exit codes) — note: quit reply has NO listening key |
| test_control_socket.py (21) | `voice_typing.daemon.ControlServer` | dispatch logic, real AF_UNIX round-trip, lifecycle/hardening (stale .sock, dir 0700, stop joins thread) | §4.2#3 | daemon.py (ControlServer/_dispatch/status_snapshot) — accept loop uses select() not close-to-unblock |
| test_status_sh.py (5) | `voice_typing/status.sh` (file-read) | exit-code contract (bugfix Issue 2) | §4.6 | status.sh — it READS the committed file, so failure = committed-file drift |
| test_systemd_unit.py (15) | `systemd/voice-typing.service` + install.sh + hypr-binds.conf (file-read) | unit directives, VT-003/004 wiring, launcher, keybinds (validation Issue 1) | §4.9 | the committed infra files — DRIFT GUARD; failure = committed file drifted from spec |

**Two categories of test in this set:**
- **Logic tests** (config 34, textproc 21, typing_backends 27, feedback 38, voicectl 32, socket 21 = 173):
  import the module and assert behavior. Failure = the module's logic is wrong (or the test drifted from
  the PRD contract it encodes).
- **Drift guards** (config_repo_default 3, status_sh 5, systemd_unit 15 = 23): READ committed files
  (config.toml, status.sh, systemd unit, install.sh, hypr-binds.conf) via `pathlib` and assert they
  match the spec. Failure = a COMMITTED FILE drifted — fix the file (not the test, unless the spec
  itself legitimately changed, which is out of scope for this item).

## §3 Failure-classification workflow (the "diagnose root cause, fix, re-run" loop)

When a test fails, classify before fixing (a mis-classified fix makes it worse):

1. **Collection/import error** (a `test_*.py` fails to import, or `ERROR` not `FAILED`): the imported
   module has a syntax/import bug → fix the SOURCE module. (e.g., `voice_typing.ctl` import error →
   ctl.py is broken.) Re-run.
2. **Assertion failure, logic test**: read pytest's `-vv` diff. Decide the source of truth:
   - If the test encodes a PRD value (§4.5/§4.6/§4.7/§4.8) and the SOURCE drifted → fix SOURCE.
   - If the test's expectation is NOT a PRD value (an implementation detail the test over-specified) →
     fix the TEST. (Round-006 is "verify against PRD" — the PRD wins; don't contort source to match an
     over-eager test assertion.)
3. **Drift-guard failure** (config_repo_default / status_sh / systemd_unit): a committed file diverged
   from spec → fix the COMMITTED FILE to match the PRD/contract (the test is the oracle). Do NOT silence
   by weakening the guard.
4. **Environment / fixture issue** (XDG_RUNTIME_DIR, tmp_path, monkeypatch leak, `capsys`/`capfd`
   ordering): these are test-environmental → fix the TEST fixture. voicectl/socket tests set
   `XDG_RUNTIME_DIR` via `monkeypatch.setenv` (hermetic) — never depend on the real env var.
5. **Flaky / timing** (socket round-trip, thread join): rare here (the full set is deterministic at
   5.32s). If seen, the house pattern is a `_wait_for(predicate, timeout=2.0)` poll helper (see
   test_control_socket.py) rather than a bare `sleep`. Do NOT add unconditional sleeps.

Re-run ONLY the failing file first (`timeout 60 .venv/bin/python -m pytest <file> -vv`), then the full
9-file set to confirm no regression.

## §4 Scope boundaries (respect them — sibling items own the rest)

- **IN scope (this item):** the 9 files above (196 tests). Pure-Python, mocked subprocess, no CUDA.
- **OUT of scope — P1.M5.T1.S2** (the NEXT leaf): `test_daemon.py` (193) + `test_recorder_host.py` (26).
  These MOCK CUDA but exercise the daemon core + the recorder-host subprocess IPC. Run them in T1.S2, not here.
- **OUT of scope — P1.M5.T2.S1 / T2 / T3 / T4:** `test_feed_audio.py` (9) is the PRD T1 offline pipeline
  (constructs a REAL recorder, loads CUDA models, feeds WAVs — minutes). T3 = `e2e_virtual_mic.sh`,
  T4 = idle-stability shell script, T6 = GPU-lifecycle nvidia-smi script. All are heavy; NONE in this set.

Do NOT add test_daemon.py / test_recorder_host.py / test_feed_audio.py to this run — they either need
mocked-but-heavy fixtures or real CUDA, and they belong to other leaves.

## §5 AGENTS.md constraints encoded into the PRP's run command

- **Two-timeout rule (non-negotiable):** inner GNU `timeout` (the contract's `120`) + outer bash-tool
  `timeout` ABOVE it (e.g. 150). The inner 124-exit = "wedged" → do NOT blindly retry; diagnose.
- **zsh aliases `python`/`pytest`:** ALWAYS full venv paths — `.venv/bin/python -m pytest` (never bare
  `python`/`pytest`). mypy is NOT installed (do not run it); ruff is optional
  (`/home/dustin/.local/bin/ruff`).
- **NEVER foreground the daemon** for these tests — they don't need it (mocked socket + subprocess). Do
  NOT `voicectl` against a real daemon; the socket tests spin up a `ControlServer(_StubDaemon())` on a
  tmp_path socket hermetically.
- These 9 files are explicitly GPU/CUDA/daemon/mic-FREE (confirmed by the 5.32s runtime) — safe + fast.

## §6 Output document (`test_results_unit.md`) — format precedent

No existing `test_results_*.md` in the plan tree (the 16 `gap_*.md` in `architecture/` are a DIFFERENT
category — read-only compliance audits; this is a results doc). This PRP defines the format. Recommended
location: `plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md` (keeps the artifact with its work item,
mirroring how gap_*.md live in architecture/). The doc must record: the exact command run, the per-file
+ total pass counts (and timing), the verdict (GREEN), and — if any fix was applied — a per-fix table
(file | change | root-cause class from §3 | which test it unblocked). Since the suite is GREEN now, the
"fixes" section will very likely be "none applied" — but the scaffold must support fixes if a failure
surfaces at execution time.
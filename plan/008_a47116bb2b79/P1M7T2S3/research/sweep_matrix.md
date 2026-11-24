# Sweep matrix — P1.M7.T2.S3 final consistency sweep

Recorded 2026-11-23 at HEAD `18015e4` (pre-sweep); fixes applied and re-verified same session.
Method: every row pairs a doc claim (file:line) with an executed landed-behavior check (code
line, command, or suite run THIS session). Verdicts: CLEAN / FIXED / FLAGGED.

## Surface 1 — README.md

| Claim (README:line at sweep) | Landed-behavior check | Verdict |
|---|---|---|
| Ducking default `duck_mode="mpris"`, ON by default (:204-206) | `AudioConfig().duck_mode == 'mpris'` (executed); config.toml :61; D1 evidence 12/12 incl. default-engages-without-`[audio]` | CLEAN |
| Pause ~107 ms after arm-return; sovereignty (a)/(b)/(c); `off` byte-identical; crash self-heal + ExecStopPost heal (:206-246) | `tests/D1_DUCK_EVIDENCE.md` (12/12, 107 ms, sovereignty ×4, journal lines verbatim-matched against README's fenced block) | CLEAN |
| Config rows `audio.duck_mode`/`audio.duck_volume_pct`/`output.delivery` (:365-367) | Executed assert: all three rows textually match config.py defaults (mpris / 15 / stream-edit) | CLEAN |
| Bulk opt-in + precondition triple + loader ValueError (:253-281) | config.py:399-428 precondition triple; config.toml :50 lockstep comment | CLEAN |
| Bulk framing "opt-in and unverified"/"unverified until G6" (:253, :367) | `tests/G6_GRADUATION.md:27` decision line VERBATIM; G6 assessment re-derivable | CLEAN |
| Field-class matrix incl. versions (:282-296) | `g3_field_matrix.md:20-24` — foot 1.28.0-2 / kitty 0.51.0-1 insert-only, ghostty 1.4.0-2 blocked, Hyprland relay blocked-in-lab; pi row reported unverified; NO row upgraded | CLEAN |
| G5 timing failing both routes; 12.6 s pi median (:298-301) | `tests/G5_TIMING_EVIDENCE.md` (recorded numbers match) | CLEAN |
| Clipboard fallback contract / L1 unprovable→refuse (:517-531) | `g4_clipboard_verdicts.jsonl` (L1 unprovable, L2-L6 verified) | CLEAN |
| `voicectl session` semantics: exit 0/1/64, `copied N chars`, no added newline (:308-316) | `ctl.py` main() docstring + `_COMMANDS`/`--copy` handling; `tests/test_voicectl.py` 54 passed (G1 re-run) | CLEAN |
| Command enumerations: "six commands… seventh, session" (:120); help/epilog surfaces | `_COMMANDS` = toggle,start,stop,status,quit,cancel,session (ctl.py:49-55); epilog names all 7 (ctl.py:333); `timeout 15 .venv/bin/voicectl --help` output confirms; lite names deliberately NOT in `_COMMANDS` (alias-only, ctl.py:56-62) → their omission from help surfaces is CORRECT, the PRP's "known suspect" is CLEARED | CLEAN |
| State fields `ducked` + 4 delivery fields (:331-338) | feedback.py vocab (inactive/active/unsupported/fault); test_feedback 49 passed | CLEAN |
| **`compute_type` "not a config key; derived from device (float32 on cuda…)" (:385-389)** | **STALE** — `AsrConfig.compute_type` IS a field (config.py:57, default `"float16"`), consumed on cuda by daemon.py:279 `cfg.asr.compute_type if device=="cuda" else "int8"`; cuda_check CUDA_DEFAULTS float16 (:53). Story is from the superseded 48a7eb9 era (bcfd171 later re-added the key for Ampere) | **FIXED** — stale sentence removed; honest `asr.compute_type` row added to the config table |
| **Config table missing `asr.compute_type` while claiming "every key below is a real field" (:347)** | Field exists + is consumed (config.py:57, daemon.py:279); config.toml documents it (:29) | **FIXED** — row added (float16 default, int8-on-CPU, Maxwell→float32 guidance) |
| **Status sample `device: cuda (float32)` (:565)** | `ctl.py:173` prints `device: {device} ({compute_type})` from resolved config → `cuda (float16)` with shipped defaults | **FIXED** — sample now `cuda (float16)` |
| CPU-only #1/#2/#3 (int8 + tiny.en fallback) (:405-430) | daemon.py:279/274, :418; cuda_check CPU_FALLBACK int8/tiny.en | CLEAN |
| Over-claim phrases ("works on Wayland", "production-ready", "fully verified") | grep = zero hits | CLEAN |

## Surface 2 — tests/ACCEPTANCE.md

| Claim | Check | Verdict |
|---|---|---|
| 14 rows (1–12 + D1 + 13); header scope "criteria 1–13 plus … (D1)" | `grep -c "^| [0-9D]"` = 14; `^| D1 `, `^| 13 ` present | CLEAN |
| G6 decision line verbatim | grep = exactly 1 occurrence, byte-identical to `G6_GRADUATION.md:27` | CLEAN |
| Stale numbers `7/7`, `77 passed`, bare `424` | greps clean; both `424` mentions round-attributed ("recorded that round … superseded") | CLEAN |
| Row 11 measured split (3/7 CUDA; 76/16 trio; 16 (i) exact; 2 (ii); g FLAKY) | Matches this session's G1 re-run byte-for-byte (below) | CLEAN |
| **Row 7 sign-off pointer → "P1.M6.T1.S3" (status cell + evidence cell + header blockquote)** | plan-006 task id; the owning sign-off is THIS task's section | **FIXED** — all 3 occurrences redirected to `## Final sign-off (P1.M7.T2.S3)` |
| **Row 7 README section line numbers (pre-S1 map: "Lite mode L118, Configuration L152…")** | README reshaped by S1; numbers 2–3 sections off | **FIXED** — line map refreshed at HEAD |
| **Row 6 "socket (35) + voicectl (32) + systemd (15) + status_sh (5) COMPLIANT, all LIVE"** | G1 re-run: control_socket **31**, voicectl **54** (suites grew with the changeset); systemd suite = **15 passed / 1 failed** (`test_hypr_binds_use_portable_home_launcher`) | **FIXED** — re-measured counts + the red NAMED (below) |
| **Row 10 "S3 trimmed ctl to the 5-command surface"** | Historical Rev-2 sentence reads as today's surface (7 commands) | **FIXED** — "then-5-command … seven today" |
| Evidence block `device: cuda (float32)` (:77) | Verbatim paste of the 2026-10-03 run (in-log timestamp :66); historical record, superseded where it matters by the 2026-11-23 re-measurements | CLEAN (left untouched, round-attributed) |

## Surface 3 — config.toml comments

| Claim | Check | Verdict |
|---|---|---|
| Header lockstep contract; unknown keys/tables rejected | config.py loader; `test_config` (69) + `test_config_repo_default` (3) green in G1 re-run | CLEAN |
| `delivery = "stream-edit"` + G6 STAY OPT-IN + precondition triple (:50) | OutputConfig().delivery == 'stream-edit'; G6 line verbatim | CLEAN |
| `duck_mode = "mpris"`, `duck_volume_pct = 15` (:61-62) | AudioConfig() defaults executed — match | CLEAN |
| `compute_type = "float16"` + Ampere/Maxwell comment (:29) | config.py:57 default + comment lockstep; README table row now matches too | CLEAN |
| streaming/graceful_stop/keypress_action values (:49, :32, :54) | config.py defaults executed — match | CLEAN |

## Surface 4 — voicectl --help + install.sh usage

| Claim | Check | Verdict |
|---|---|---|
| Epilog names 7 commands (ctl.py:333) | `timeout 15 .venv/bin/voicectl --help` executed — matches `_COMMANDS` exactly | CLEAN |
| Lite aliases absent from help surfaces | ctl.py:56-62 — deliberate ("NOT a member of _COMMANDS and NOT listed in any help surface"); `toggle-lite` remaps via `_ALIASES`, `start-lite` exits 64 (README :123-125 documents both) | CLEAN (PRP suspect cleared) |
| install.sh usage `toggle|start|stop|status|cancel|session|quit` + session hint (:209-212) | All 7 present; hint matches ctl.py semantics (exit 1, `copied N chars`) | CLEAN |
| ctl.py:56-58 comment "the documented Rev 2 surface stays the six commands above" | Stale count (seven now, `session` added P1.M6.T2.S3) — code-embedded comment | **FLAGGED** (not fixed — source comment; doc-level sweep) |

## G1 15-suite re-run (baseline-parity methodology, 2026-11-23 @ HEAD 18015e4)

Method per `tests/G1_BASELINE.md`: `timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q
--tb=line`, ONE file per call; bash-tool backstop 900. Log: /tmp/g1_rerun_s3.log (bounded, capped).

| Suite | Baseline P/F | This run P/F | Red-set verdict |
|---|---|---|---|
| test_streaming_commit | 22/10 | 22/10 | 10 (i) reds = exact 20-row names |
| test_streaming_core | 32/2 | 32/2 | 2 (i) reds = exact |
| test_streaming_freeze | 22/4 | 22/4 | 4 (i) reds = exact |
| test_streaming (CUDA) | 4/3 | 3/4 | a+b (ii) watch + f (i)/F1 red as recorded; **g FAILED this run — FLAKY class** (population now 5F/2P over 7 obs; flip proves nothing) |
| test_zero_diff_rewind | 3/0 | 3/0 | green |
| test_key_listener | 32/0 | 33/0 | +1 changeset test (D3 auto-repeat), green |
| test_control_socket | 27/0 | 31/0 | +4 changeset tests, green |
| test_config | 54/0 | 69/0 | +15 changeset tests ([audio]/delivery), green |
| test_config_repo_default | 3/0 | 3/0 | green |
| test_textproc | 31/0 | 31/0 | green |
| test_typing_backends | 36/0 | 38/0 | +2, green |
| test_voicectl | 36/0 | 54/0 | +18 (session/--copy), green |
| test_feedback | 38/0 | 49/0 | +11 (delivery fields), green |
| test_prompt_engine | 28/0 | 28/0 | green |
| test_context_prompt_refresh | 12/0 | 12/0 | green |
| **Total** | 380/19 | **430/20** | **16 fast (i) reds EXACT set; no NEW failures** |

Drift accounting: +51 passing tests = changeset-added (verified via `git diff d78ff95..HEAD`:
config +15, voicectl +18, feedback +11, control_socket +4, key_listener +1, typing_backends +2 —
sums exactly). 19→20 failed delta = `test_g_stranded_tail` (FLAKY). NO addendum row needed — the
addendum mechanism is for NEW failures; there are none.

**Outside the G1 set, run for row-6 accuracy:** `tests/test_systemd_unit.py` = 15 passed /
1 failed — `test_hypr_binds_use_portable_home_launcher` is a **PRE-EXISTING red** (the
`SUPER ALT, Escape → systemctl --user stop` bind landed pre-baseline in `0e7dd05`, and the
assertion "every bind line launches voicectl" predates it too — both present at baseline
d78ff95, so the red existed there; never surfaced because the suite is outside the G1 set).
NOT a G1 failure, NOT a changeset regression. Named in ACCEPTANCE row 6 + escalated in the
sign-off. Never reclassified, never fixed by this docs task (fix belongs to a code task:
teach the pin to tolerate non-voicectl binds).

# Validation Report — voice-typing (Rev-4 delta + bugfix 001_5597f70b5c13)

**Validated**: 2026-11-24 07:45–07:58 EST · HEAD `2645673` (code-identical to the G5-qualified
`2909e03`; the two commits above it are README/plan docs only — verified `git diff --stat`) ·
baseline under validation: PRD bug report `001_5597f70b5c13` (BUG-001..BUG-004, recorded at
`573d78f`), fix delta = 16 commits `74252cd..2645673` (P1.M1.T1–T3, P1.M2.T1–T3).

**Method**: `./validate.sh` (written by this validation; 5 phases, exit 0/1) plus direct
behavioral probes. All commands ran under the AGENTS.md two-timeout discipline; the daemon was
never spawned, armed, restarted, or quit by the validator; every live check is read-only;
scratch under `/tmp` was bounded and trap-cleaned.

---

## Verification of the four PRD bugs

### BUG-001 (Major) — ducking default flip made unit tests fire real busctl --user calls → **FIXED, VERIFIED**

- **Deterministic repro now passes**: `timeout 300 .venv/bin/pytest
  tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm
  tests/test_typing_backends.py -q` → **39 passed** (was a deterministic `test_wtype_passes_check_true`
  failure at `573d78f`).
- **Order-independence restored**: the previously flaky 8-file batch
  (control_socket, key_listener, typing_backends, textproc, prompt_engine,
  context_prompt_refresh, systemd_unit, ydotoold_client) → **210 passed, 3/3 runs clean**
  (was failing 2/5 at `573d78f`).
- **Mechanism verified in code**: `tests/conftest.py` ships the opt-in `hermetic_daemon_media`
  fixture whose fail-closed factory raises `AssertionError` on any unguarded
  `_build_default_ducker` call, plus the `hermetic_cfg()` builder (`duck_mode="off"` + private
  state file). Every raw `VoiceTypingDaemon(` construction site in `tests/` was audited — all
  30+ sites across 8 files now build through `hermetic_cfg(...)` or the `ducker=` fake seam
  (the dedicated duck-wiring tests, `tests/test_ducking.py`: 32 passed).
- **Defense in depth**: `tests/test_typing_backends.py`'s subprocess recorder now raises on any
  `busctl`/`wpctl` argv[0] AND the victim tests scan the call ledger (two layers, since a leaked
  worker swallows in-thread raises).
- **Full-suite proof**: all 48 pure suites ran (one file per call) with **zero cross-file
  pollution** and zero wedges; no live-desktop side effect is reachable from the suite anymore.

### BUG-002 (Major) — bulk-text delivery fails normative R.1 live-visibility → **PARTIALLY REMEDIATED, STILL OPEN** (see Issue 1 below)

- **Discharged obligation**: R.8's "compare callbacks" is now done. A `partial_source`
  selector ("plain" = `on_realtime_transcription_update` vs "stabilized") is threaded as
  picklable data across the spawn boundary (`daemon.py` `_PARTIAL_SOURCES` → `RecorderHost` →
  child), the paired A/B harness exists (`tests/g5_ab_compare.py`, 47 tests green), and the
  comparison was RUN and re-derived under the candidate cadence (G5_TIMING_EVIDENCE.md,
  qualification round P1.M2.T2.S3): stabilized beats plain on pi-ghostty (6714 vs 11978 ms
  speech→visible median; im-gtk plain arm not-run after two sanctioned re-arm-gate failures),
  so the default stays "stabilized" — a data-driven decision, recorded.
- **Still failing**: both G5 routes FAIL the R.7 gate on the production selection (20 measured
  replays each, at code-identical `2909e03`): im-gtk 4 insertions / 0 corrections vs ≥100/100
  floors with a sustained 57-word backlog; pi-ghostty speech→visible median **6714 ms ≈ 13×
  the ≤500 ms bar**, sentence-end dump persists, and the unchanged⇒zero-edits bar was breached
  for the first time. `tests/g6_assessment.py` mechanically re-derives
  `G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)`.
- **Safety posture verified live**: default `output.delivery = "stream-edit"` (config.py,
  config.toml, and `from_toml({})` probe); `bulk-text` loads only with the precondition triple
  (streaming=true, graceful_stop=false, keypress_action=disarm — bad companion rejected with a
  naming ValueError, probed directly); the failure is honestly recorded in-repo, not hidden.

### BUG-003 (Minor) — permanently red VT-003 panic-bind test → **FIXED, VERIFIED**

`tests/test_systemd_unit.py::test_hypr_binds_use_portable_home_launcher` now passes (full file:
**24 passed**). The fix pins the exact parsed panic bind (`SUPER ALT, Escape, exec, systemctl
--user stop voice-typing` — mods set, key, dispatcher, and token-list command all exact;
deliberately not a substring/`# exempt` marker, so `… stop voice-typing; reboot` would still
fail), asserts it appears exactly once, and adds string-fixture negative-space tests. The suite
carries no unexplained red anymore.

### BUG-004 (Minor) — test_daemon.py misclassified as a CUDA hang vector → **FIXED, VERIFIED**

- `tests/G1_BASELINE.md` gained the **"G1 CPU addendum — tests/test_daemon.py"** with the named
  20-case failure inventory and an operative future set-diff rule; `AGENTS.md`'s hang-vector
  table row now reads "NOT a CUDA suite … pure CPU, hermetic post-T1 … ~16 s" with the
  two-timeout discipline retained.
- **Live set-diff executed**: `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q
  --tb=no` → 20 failed / 243 passed (~17 s, CPU-only, no CUDA). The 20 failure NAMES are
  IDENTICAL to the addendum's inventory (verified by sorted diff) — zero unclassified reds.

---

## Issues found

### Critical Issues

None.

### Major Issues

#### Issue 1: bulk-text delivery still does not meet its normative R.1 live-visibility requirement — PRD acceptance #13 remains unmet (BUG-002 core persists)
**Severity**: Major · **ID**: BUG-002 (carried, partially remediated)
**Location**: `voice_typing/daemon.py` (`_PARTIAL_CALLBACK_ATTR` = stabilized; `_BULK_REALTIME_PROCESSING_PAUSE = 0.05`), `voice_typing/bulk_controller.py` (per-utterance coalescing); evidence: `tests/G5_TIMING_EVIDENCE.md` (2026-11-24 qualification round @ `2909e03`, code-identical to HEAD).

**Description**: PRD §4.2sexies R.1 (normative) requires words to become visible as updates
arrive — "never a sentence-end dump" — and R.7 G5 fails any route with a sustained ≥5-word
backlog or a dump regardless of medians. The shipped bulk-text path still fails on BOTH
instrumented routes after the remediation round: im-gtk is count/backlog-bound (4/0 vs
≥100/≥100 floors; 57-word sustained backlog), pi-ghostty's speech→visible median improved
7786 → 6714 ms (−14%, the 0.05 s cadence change) but remains ~13× the 500 ms bar, its
sentence-end dump persists, and the unchanged⇒zero-edits bar was breached. The R.8 comparison
obligation IS now discharged (stabilized measurably beats plain; default correctly not
flipped), and the repo's own docs state "BUG-002 and PRD acceptance #13 remain OPEN … No route
streams words at speaking pace yet." Net: with `output.delivery="bulk-text"`, dictation still
behaves like wait-for-silence delivery. Mitigations verified intact: the mode is opt-in, the
default is unchanged, G6 honestly stays STAY OPT-IN, and the failure is recorded rather than
hidden — which is why this remains Major, not Critical.

**Steps to Reproduce**: read `tests/G5_TIMING_EVIDENCE.md` (verdict table: both routes
`**fail**`); re-run per its own commands — `timeout -k 2 1500 env G5_TIMING_LAB=1
.venv/bin/python tests/g5_timing_lab.py --route im-gtk` (and `--route pi-ghostty` with
`PI_BIN`), each exits 1 with an honest-fail JSON verdict; or `timeout 60 .venv/bin/python
tests/g6_assessment.py` → `C-g5-timing: unmet`. `./validate.sh` gates the honesty/safety
properties (opt-in default, precondition triple, G6 consistency) on every run and exposes the
lab behind `RUN_G5=1`.

### Minor Issues

#### Issue 2: stale in-code comments claim duck_mode="off" is "the shipped default" — it is "mpris" since P1.M2.T4
**Severity**: Minor · **ID**: NEW-001
**Location**: `voice_typing/daemon.py:1159` ("duck_mode=\"off\" (the shipped default) ⇒ …") and `voice_typing/daemon.py:1838` ("# duck_mode=\"off\" (default) ⇒ no-op").

**Description**: The shipped default is `duck_mode = "mpris"` (`voice_typing/config.py:249`,
`config.toml:61`, and README "Media ducking while listening": "This is ON by default"). Two
daemon.py comments still describe `"off"` as the default — text written before the P1.M2.T4
flip and never updated. Comment-only, zero behavior impact (the `ducker is None` no-op guard
itself is correct), but it misleads exactly the audit path (default-config hermeticity) where
BUG-001 originated: a reader concluding "default config builds no ducker" would reintroduce
the BUG-001 class of reasoning error. One-line comment fixes at both sites.

**Steps to Reproduce**: `grep -n 'duck_mode="off" (the shipped default)\|duck_mode="off"
(default)' voice_typing/daemon.py` → 2 hits; compare `grep -n 'duck_mode: str'
voice_typing/config.py` → `"mpris"`.

---

## Fixed-and-verified (not counted as open issues)

- **BUG-001** — hermetic daemon tests: repro pair, 8-file batch ×3, full 48-suite run, ctor-site audit, tripwire + fail-closed factory all green (details above).
- **BUG-003** — panic-bind exemption: exact-match pin + negative-space tests; suite green.
- **BUG-004** — test_daemon.py classification: G1 CPU addendum + corrected AGENTS.md row; live 20/20 name-identical set-diff.

## Operational observations (not counted — not codebase defects)

1. **The live systemd daemon predates the `session` feature.** The unit (MainPID started Nov 23
   17:52:41, ~14 h uptime) was started before commit `445b9ed` (Nov 23 19:47) added
   `voicectl session`, so against the RUNNING process `voicectl session` prints
   `error: unknown command: 'session'` (rc=1, message on stdout). The code at HEAD supports it
   (`daemon.py:3793`, `ctl.py:185`) and `tests/test_voicectl_session.py` is green (5 passed).
   Fix is operational: `systemctl --user restart voice-typing`. The validator deliberately did
   not restart the operator's service; `validate.sh` detects and WARNs on this condition.
2. **HEAD advanced during validation** (`893f26a` → `2645673`: README sync + plan docs only,
   zero `voice_typing/`/`tests/` delta) — all results apply to both commits.

## Testing Summary

| Layer | What ran | Result |
|---|---|---|
| Static | `python -m compileall voice_typing` (no ruff/mypy/black config ships; README: "pytest is the gate") | clean |
| Unit (pure) | **48 suites, one file per call** under GNU `timeout` (repo methodology; CUDA/model suites and `.sh` harnesses excluded) | **1,243 passed / 36 failed — every red name-identical to the documented G1 baseline** (streaming_commit 10, streaming_core 2, streaming_freeze 4 — the legacy lazy-separator set; test_daemon 20 — the G1 CPU addendum). **0 new reds**; test_daemon counts moved 217P→243P at fixed reds (fix delta added tests, broke nothing) |
| Bug spotlights | BUG-001 repro pair + 8-file batch + tripwire/builder greps; BUG-002 config gates + G6/G5 consistency; BUG-003 panic-bind test; BUG-004 doc pins | all pass |
| Live E2E (read-only) | systemd unit active; `voicectl status` 10-field contract (listening/mode/phase/partial/last/uptime/device/mic/context-prompt/delivery); `voicectl session` exit-code contract (stale-daemon case detected, see obs. 1); usage contract (no cmd / unknown cmd → 64); journal readable; VT-003 launcher installed | all pass |
| Config-loader probes | default delivery `stream-edit`; bulk-text loads with the triple, rejects `streaming=false` with a naming ValueError | pass |
| Opt-in heavy (documented in validate.sh, NOT run by default) | `RUN_CUDA=1` (4 CUDA/model suites), `RUN_G5=1` (G5 lab, both routes), `RUN_D1=1` (duck evidence — pauses live media), `RUN_MIC_E2E=1` (virtual-mic E2E — rebinds default source) | behind env flags per AGENTS.md R.7 discipline |

**Totals**: bugs open: **2** (1 Major carried — BUG-002 core; 1 Minor new — stale comments).
Critical: 0. Fixed-and-verified this round: BUG-001, BUG-003, BUG-004.

## The validation script (`./validate.sh`)

Five phases, exit 0 (pass) / 1 (any gating failure), ~4–5 min default runtime:
0. preflight (venv + python 3.12);
1. static compileall;
2. all 48 pure suites, one file per call (per-file GNU timeout 300/500), with automatic
   **set-diff of every failure against the embedded G1 baseline inventories** (new red = FAIL,
   baselined red turning green = NOTE prompting a baseline update);
3. the four PRD bug spotlights (BUG-001 order-pollution repro + batch + tripwires; BUG-002
   safety/honesty gates; BUG-003 exemption test; BUG-004 doc pins);
4. read-only live E2E (unit, status fields, session exit codes incl. stale-daemon detection,
   usage exit 64s, journal, launcher).
Heavy desktop-mutating/GPU harnesses are opt-in (`STRICT`, `RUN_CUDA`, `RUN_G5`, `RUN_D1`,
`RUN_MIC_E2E`). AGENTS.md-compliant throughout: GNU timeout on every non-trivial command,
trap-cleaned bounded scratch, never spawns/arms/restarts the daemon.

## Recommendations

1. **BUG-002 / R.1**: continue remediation upstream of the adapter stages — the repo's own
   stage diagnosis places the dominant share in the decode-evaluation cadence + delivery
   complex, and the controller still coalesces partials per-utterance. Candidate directions:
   update-granular partial op dispatch ahead of the final, further cadence/decoder-thread
   work, or — if wait-for-silence behavior is acceptable for bulk-text — renegotiate R.1 with
   the PRD owner and record it. Keep G6 STAY OPT-IN and the opt-in default until a route
   actually passes G5.
2. Update the two stale `duck_mode="off" (default)` comments in `voice_typing/daemon.py`
   (lines 1159 and 1838) to name `"mpris"` as the shipped default.
3. Restart the live daemon to pick up the `session` command (operator action; `validate.sh`
   will WARN until then).
4. Hardening (optional): the `hermetic_daemon_media` fixture is opt-in; a future test could
   construct a default-config daemon without it and silently regress BUG-001. Consider a
   session-level guard (e.g., an autouse fixture that fail-closes `_build_default_ducker`
   unless the test opts out) once the migration semantics are settled.

# Research — P1.M3.T1.S1 Audit state.json schema (feedback.py vs PRD §4.6)

This is a **READ-ONLY AUDIT** task. The deliverable is a gap report (`gap_feedback.md`); NO source
code is modified (the code is compliant — verified). Ground truth gathered by reading
`voice_typing/feedback.py` + `tests/test_feedback.py` + the sibling gap reports + the parallel PRP
on 2026-07-18.

---

## 1. Task nature + deliverable location (CONVENTION — verified)

- This subtask audits `feedback.py`'s `state.json` schema against PRD §4.6 (the 6 contract checks a–f).
- **Deliverable:** a NEW standalone report at `plan/006_862ee9d6ef41/architecture/gap_feedback.md`.
  Siblings already present: `gap_config.md`, `gap_textproc.md`, `gap_typing.md`, `gap_cuda_check.md`,
  `gap_daemon_loop.md`, `gap_lifecycle.md`, `gap_lite.md` (+ the in-flight `gap_recorder_kwargs.md`
  from the parallel P1.M2.T4.S1). The parallel PRP CONFIRMS the convention: its agent writes
  `architecture/gap_recorder_kwargs.md`, "Format mirrors `gap_lifecycle.md`: title + date + scope +
  audited artifacts + bottom line + per-property findings + non-defect nuances + 'no source modified'".
- **Format template = `gap_lifecycle.md`** (read it): `# Gap Report — P1.M3.T1.S1: Feedback state.json
  schema vs PRD §4.6`, Date, Scope (audited regions w/ file:line), Audited artifacts (read-only),
  Bottom line (✅/❌), §1 Method, per-check findings w/ file:line evidence, a "non-defect nuances"
  section, and the closing "No source files were modified — only new artifact is this report."
- The PRP author (me) writes ONLY `PRP.md` + this research note. The IMPLEMENTING agent writes
  `gap_feedback.md`. The audit re-verifies LIVE (re-grep + re-read + re-run tests), then writes the
  report — it does not trust this note's verdict blindly (mirrors gap_lifecycle.md "re-verified
  against the live tree").

## 2. VERIFIED VERDICT: feedback.py state.json schema is COMPLIANT on all 6 checks

Re-verified by grep + read of `voice_typing/feedback.py`. Each check → file:line evidence:

| Check | Contract | Verdict | Evidence (feedback.py) |
|---|---|---|---|
| (a) 7 PRD fields | _state has listening, phase, models_loaded, mode, partial, last_final, ts | ✅ | `_state` dict L95-103: listening@96, phase@97, models_loaded@98, mode@99, partial@100, last_final@101, ts@102 — exactly the 7 PRD §4.6 fields |
| (b) boot state | phase='unloaded', models_loaded=False | ✅ | `"phase": "unloaded"` @97; `"models_loaded": False` @98; (mode 'normal' @99) |
| (c) set_phase values | accepts unloaded/loading/idle/listening/speaking | ✅ | `set_phase(phase: str)` L122 → `self._state["phase"] = phase` @130; NO validation (accepts any string); the daemon drives the 5 lifecycle values |
| (d) mode on arm/disarm | mode='normal'\|'lite' written on arm/disarm | ✅ | `set_mode(mode: str)` L145 → `self._state["mode"] = mode` @150; default `"normal"` @99; daemon calls it on arm/disarm (out of feedback.py's scope — it just publishes) |
| (e) record_final → BOTH | record_final writes last_final AND partial | ✅ | `record_final(text)` L153: `self._state["last_final"] = text` @165 AND `self._state["partial"] = text` @166 — matches PRD §4.6 "record_final ALSO writes the finalized text back into the partial field" |
| (f) ts = time.time() | ts uses wall epoch (time.time()) | ✅ | `_write()` L219 → `self._state["ts"] = time.time()` @227 (wall epoch). NOTE: the THROTTLE clock uses `time.monotonic()` @116 — but `ts` itself is `time.time()` (documented @75-76: "the ts FIELD still uses time.time() (wall epoch)") |

**Bottom line (expected):** ✅ All 6 checks COMPLIANT — no code defect. The only new artifact is
`gap_feedback.md`. (The audit re-confirms this live; if a check surprisingly fails on re-read, the
report documents it as a real gap for a SEPARATE remediation task — this audit does NOT fix code.)

## 3. TEST-COVERAGE nuances (NON-DEFECTS — record so they aren't mistaken for code gaps)

The code is compliant, but two test assertions are thinner than the contract's intent. These are
**test-coverage observations**, NOT code defects — record them in the report's "non-defect nuances"
section (mirrors gap_lifecycle.md §4):

1. **Check (e) partial-write-back is not asserted.** `test_record_final_sets_last_final`
   (test_feedback.py:146-150) asserts `state["last_final"]` but does NOT assert
   `state["partial"] == "A finished sentence."`. The CODE writes partial (feedback.py:166) — so the
   behavior is correct — but no test pins the PRD §4.6 "ALSO writes partial" clause. (A future test
   task could add the assertion; this audit does not add tests — it only reports.)
2. **Check (b) boot VALUES not explicitly asserted.** `test_state_shape_has_the_documented_fields`
   (125-129) asserts the exact 7-key SET (after `update_partial("x")`), and
   `test_set_mode_writes_mode_field` (141) asserts the boot `mode == "normal"`. But no test explicitly
   asserts boot `phase == "unloaded"` or `models_loaded is False`. The CODE defaults are correct
   (feedback.py:97-98) — the values just aren't pinned by a dedicated assertion. (Non-defect; the
   shape test implicitly exercises them without checking the values.)

`test_update_partial_round_trip` (117-122) asserts `isinstance(state["ts"], float) and > 0.0` →
adequately covers check (f) (a positive epoch float). `test_set_phase_round_trip` (132-135) covers (c).

## 4. The test command (the contract's run target)

```
.venv/bin/python -m pytest tests/test_feedback.py -q
```
FULL PATH (.venv/bin/python — zsh aliases python/pytest). The whole test_feedback.py suite is
fast + GPU-free (subprocess.run monkeypatched; time.monotonic mocked via the harness). The audit
re-runs it live and records the pass count in the report (mirrors gap_lifecycle.md's "43 passed"
evidence). mypy is NOT installed — do NOT run it. ruff is optional (/home/dustin/.local/bin/ruff).

## 5. Scope boundaries

- **READ-ONLY.** No source files modified (feedback.py is compliant). The ONLY new artifact is
  `architecture/gap_feedback.md`. If a real defect WERE found, the report documents it for a separate
  remediation task — this audit does not fix code (aligns with the FORBIDDEN OPERATIONS: the PRP
  author doesn't modify code; neither does the audit).
- **feedback.py + tests/test_feedback.py ONLY.** The daemon's ROLE (driving phase/mode transitions)
  is OUT of scope for this audit — feedback.py just publishes what it's told; whether the daemon
  CALLS set_phase/set_mode at the right moments is P1.M2.* (lifecycle/lite audits, already Complete).
  This audit verifies the SCHEMA + the methods' write semantics, not the daemon's call sites.
- **Parallel task (P1.M2.T4.S1)** audits recorder kwargs (daemon.py/config.py) → `gap_recorder_kwargs.md`.
  DISJOINT (different file, different report). No overlap.
- **The atomic-write/throttle/hyprctl-notify audit is P1.M3.T1.S2** (the NEXT subtask) — this task
  (S1) is the SCHEMA only (the 6 checks). Do NOT audit atomic writes / throttling / notify events here.
- **No docs** (item DOCS: none — status.sh + README document the external format; this is internal schema).
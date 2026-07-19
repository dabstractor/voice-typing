# Gap Report — P1.M3.T1.S1: Feedback state.json schema vs PRD §4.6

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/feedback.py`'s **`Feedback._state` schema** + the **6 write-method
semantics** against **PRD §4.6** on the **6 item checks (a)–(f)**: (a) the 7 PRD fields, (b) the boot
lifecycle state, (c) the `set_phase` values, (d) the `mode` field, (e) the `record_final` write-back
to `partial`, and (f) the `ts` wall-epoch clock. The audited code regions are: the `_state` dict
boot definition (L95-102), `set_phase` (L122 → write @130), `set_models_loaded` (L133 → @142),
`set_mode` (L145 → @150), `record_final` (L153 → `last_final` @165 AND `partial` @166),
`set_listening` (L171 → @186 + arm-clear @188), `snapshot` (L193 → @202), and `_write` (L218 →
`ts = time.time()` @227). The THROTTLE clock (`time.monotonic()` @116) is examined ONLY to
distinguish it from the `ts` wall-epoch clock (check (f)). Subtask **P1.M3.T1.S1** of verification
round `006_862ee9d6ef41`.

**Audited artifacts (all read-only):**
- `voice_typing/feedback.py` — `_state` dict (L95-102: `listening`@96, `phase`@97,
  `models_loaded`@98, `mode`@99, `partial`@100, `last_final`@101, `ts`@102 — exactly the 7 PRD §4.6
  fields); boot values (`"phase": "unloaded"`@97, `"models_loaded": False`@98, `"mode": "normal"`@99);
  `set_phase(phase: str)` L122 → `self._state["phase"] = phase` @130 (no validation — accepts any
  string; the daemon drives the 5 lifecycle values); `set_models_loaded(loaded: bool)` L133 →
  `self._state["models_loaded"] = bool(loaded)` @142; `set_mode(mode: str)` L145 →
  `self._state["mode"] = mode` @150; `record_final(text)` L153 → `self._state["last_final"] = text`
  @165 AND `self._state["partial"] = text` @166 (the PRD §4.6 "record_final ALSO writes the finalized
  text back into the partial field" clause); `set_listening(listening: bool)` L171 →
  `self._state["listening"] = listening` @186 (+ arm-clears `partial` @188 on a False→True
  transition); `snapshot()` L193 → `return dict(self._state)` @202 (a COPY — see nuance §3.0);
  `_write()` L218 → `self._state["ts"] = time.time()` @227 (WALL epoch — NOT `time.monotonic()`).
- `tests/test_feedback.py` — the contract's run target (`tests/test_feedback.py -q`; re-ran live).
  Coverage characterized in §3 (the non-defect nuances) + the test→check mapping in §2.1.

**Bottom line:** ✅ All 6 item checks (a)–(f) are **COMPLIANT** (each with file:line evidence below).
The contract's run target is **38 passed in 0.04s** (re-ran live; GPU-free — `subprocess.run` is
monkeypatched via `_Recorder` and `time.monotonic` is mocked via `_Clock`, so the suite is fast and
deterministic). Two **non-defect test-coverage nuances** are recorded so they are not mistaken for
code gaps (§3). **No source files were modified** — `feedback.py` is PRD §4.6-compliant per this
re-verification (no defect surfaced). The only new artifact is this report.

---

## 1. Method

Each of the 6 item checks was mapped to **specific `voice_typing/feedback.py` file:line** via
`grep -nE`, then re-verified by reading the `_state` dict (L95-102), `set_phase` (L122-130),
`set_models_loaded` (L133-142), `set_mode` (L145-150), `record_final` (L153-166), `set_listening`
(L171-188), `snapshot` (L193-202), and `_write` (L218-227) against the **PRD §4.6** wording (the
7-field schema, the boot phases `unloaded`/`loading` with `models_loaded: false`, the
`normal`|`lite` mode written on arm/disarm, the "record_final ALSO writes the finalized text back
into the partial field" clause, and `ts` as a wall epoch). The `ts` vs throttle-clock distinction
(Critical #4 of the PRP) was cross-checked against the module docstring (feedback.py:75-76: "The ts
FIELD still uses `time.time()` (wall epoch)" — distinct from the throttle clock
`time.monotonic()` @116). The contract's test target was then re-run live
(`tests/test_feedback.py -q`, §2.1). The 2 non-defect nuances (§3) were cross-checked against the
test file: `test_record_final_sets_last_final` (L146) and
`test_record_final_updates_partial_so_status_matches_screen` (L269) for nuance #1; and the absence
of any explicit boot-value assertion for nuance #2 (confirmed by grep — see §3.2).

### Commands run (re-verification)

```bash
# locate every _state field + every write-method site
grep -nE 'self\._state|^            "(listening|phase|models_loaded|mode|partial|last_final|ts)"' voice_typing/feedback.py
grep -nE 'def set_phase|def set_models_loaded|def set_mode|def record_final|def set_listening|def _write|def snapshot|def update_partial|time\.time\(\)|time\.monotonic\(\)' voice_typing/feedback.py
# the contract's run target (re-ran live)
timeout 120 .venv/bin/python -m pytest tests/test_feedback.py -q
# source-modification guard — read-only audit (expect empty)
git status --porcelain voice_typing/feedback.py tests/test_feedback.py
```

---

## 2. The 6 item checks — per-check compliance table

| # | Check (PRD §4.6) | Code actual (`voice_typing/feedback.py`) | Verdict |
|---|---|---|---|
| (a) | **`_state` has exactly the 7 PRD fields** — `{listening, phase, models_loaded, mode, partial, last_final, ts}` | `_state` dict L95-102: `"listening"` @96, `"phase"` @97, `"models_loaded"` @98, `"mode"` @99, `"partial"` @100, `"last_final"` @101, `"ts"` @102 — exactly the 7 PRD §4.6 fields, no more, no less. `test_state_shape_has_the_documented_fields` (test_feedback.py:125-128) pins the exact 7-key set. | ✅ **COMPLIANT** |
| (b) | **Boot state** — `phase='unloaded'`, `models_loaded=False` (models not resident until first arm; PRD §4.2bis) | Boot defaults in the `_state` dict: `"phase": "unloaded"` **@97**, `"models_loaded": False` **@98**, (`"mode": "normal"` @99). The daemon overrides both at construction + each lifecycle transition (`set_phase` + `set_models_loaded`); these are the safe pre-daemon defaults. (The boot VALUES are not explicitly pinned by a dedicated test — nuance §3.2; the SHAPE is pinned by test @125.) | ✅ **COMPLIANT** |
| (c) | **`set_phase` accepts the 5 lifecycle values** — `unloaded`/`loading`/`idle`/`listening`/`speaking` | `set_phase(self, phase: str)` **L122** → `self._state["phase"] = phase` **@130**. NO validation — accepts any string; the daemon drives the 5 lifecycle values (which value at which moment is P1.M2.*, out of scope here). Always writes (`self._write()` follows). `test_set_phase_round_trip` (test_feedback.py:132-135) covers the round-trip. | ✅ **COMPLIANT** |
| (d) | **`mode` field** — `normal`\|`lite`, written on every arm/disarm (PRD §4.2ter) | `set_mode(self, mode: str)` **L145** → `self._state["mode"] = mode` **@150**; default `"normal"` **@99** (the `_state` dict boot value). The daemon calls `set_mode` from `_arm()` right before `set_listening(True)` (out of feedback.py's scope — it just PUBLISHES what it's told). Always writes. `test_set_mode_writes_mode_field` (test_feedback.py:138-142) asserts both the boot default (`snapshot()["mode"] == "normal"`) and the write (`state["mode"] == "lite"`). | ✅ **COMPLIANT** |
| (e) | **`record_final` writes BOTH `last_final` AND `partial`** — PRD §4.6 "record_final ALSO writes the finalized text back into the partial field" (so the tmux status line matches the screen) | `record_final(self, text: str)` **L153**: `self._state["last_final"] = text` **@165** AND `self._state["partial"] = text` **@166** (comment @166: "status line shows the final, not the stale last partial"). The dual write is exactly the PRD §4.6 clause. The partial-write-back IS now asserted: `test_record_final_updates_partial_so_status_matches_screen` (test_feedback.py:269-282) asserts BOTH `state["partial"] == "Okay, what are we typing here today?"` (@281) AND `state["last_final"] == ...` (@282). | ✅ **COMPLIANT** |
| (f) | **`ts` uses `time.time()` (wall epoch)** — NOT `time.monotonic()` | `_write(self)` **L218** → `self._state["ts"] = time.time()` **@227** (WALL epoch). NOTE: the THROTTLE clock is `time.monotonic()` **@116** (`update_partial`'s `now = time.monotonic()`) — a SEPARATE mechanism that drives the >=10 Hz disk-write cap; it is deliberately NOT `time.time()` (the wall clock can jump backward on NTP and freeze the partial — module docstring feedback.py:75-76). Check (f) is about the `ts` FIELD ONLY; the two clocks are correctly distinct. `test_update_partial_round_trip` (test_feedback.py:117-122) asserts `isinstance(state["ts"], float) and state["ts"] > 0.0`. | ✅ **COMPLIANT** |

### 2.1 Test → check mapping

| Check | Covering test (`tests/test_feedback.py`) | What it asserts |
|---|---|---|
| (a) 7 fields | `test_state_shape_has_the_documented_fields` (125-128) | `set(state.keys()) == {"listening","phase","models_loaded","mode","partial","last_final","ts"}` — the exact 7-key set |
| (b) boot state | `test_state_shape_has_the_documented_fields` (125-128) + `test_set_mode_writes_mode_field` (138-142) | the shape test exercises the boot dict implicitly; the mode test asserts the boot `mode == "normal"` (@140). (No dedicated assertion for boot `phase=="unloaded"` / `models_loaded is False` — nuance §3.2.) |
| (c) set_phase | `test_set_phase_round_trip` (132-135) | `set_phase("speaking")` → `_read_state(...)["phase"] == "speaking"` |
| (d) mode field | `test_set_mode_writes_mode_field` (138-142) | boot `snapshot()["mode"] == "normal"` (@140); `set_mode("lite")` → `state["mode"] == "lite"` (@142) |
| (e) record_final → both | `test_record_final_sets_last_final` (146-150) + `test_record_final_updates_partial_so_status_matches_screen` (269-282) | @146 asserts `last_final` only; @269 asserts BOTH `partial` (@281) AND `last_final` (@282) — the partial write-back IS pinned by the dedicated regression test |
| (f) ts = wall epoch | `test_update_partial_round_trip` (117-122) | `isinstance(state["ts"], float) and state["ts"] > 0.0` (a positive epoch float; `time.time()` is left REAL in the harness — only `time.monotonic` is mocked) |

---

## 3. Non-defect nuances (NON-blocking — recorded so they are NOT mistaken for code gaps)

### 3.0 `snapshot()` returns a COPY (a `dict` aliasing guard, not a schema point)

`snapshot()` (feedback.py:193 → `return dict(self._state)` @202) returns a **shallow copy** of the
live `_state`, so a concurrent reader (the control-socket `status` cmd) never aliases the dict the
callback threads mutate. This is a concurrency/read-safety property, NOT a schema property — it is
mentioned only because the method is in the audited region. It carries the same 7 keys (verified by
`test_snapshot_returns_a_copy_with_the_state_keys`, test_feedback.py:289-296) and is therefore
schema-identical to the on-disk `state.json`. **Not a gap.**

### 3.1 Nuance #1 — `test_record_final_sets_last_final` asserts `last_final` only (but the partial write-back IS pinned by a dedicated test)

The OLDER test `test_record_final_sets_last_final` (test_feedback.py:146-150) asserts
`state["last_final"]` but does NOT assert `state["partial"]`. **However**, the dedicated regression
test `test_record_final_updates_partial_so_status_matches_screen` (test_feedback.py:269-282) — added
to guard the exact PRD §4.6 "record_final ALSO writes partial" clause (its docstring @270-275 quotes
the rationale: "the tmux status-right used to keep showing the last realtime partial, which trails
the final by a word or two") — asserts BOTH `state["partial"] == "Okay, what are we typing here
today?"` (@281) AND `state["last_final"] == ...` (@282).

**Conclusion:** the record_final→partial write-back (check (e)) **IS fully covered** by the
dedicated test. The older test's thinner assertion is a historical artifact (it predates the
regression test), NOT a coverage gap. Recorded so a future auditor does not re-flag the older test.
(The CODE is compliant regardless — feedback.py:166 writes `partial` unconditionally.)

> **Accuracy note:** this re-verification CORRECTS the research note's pre-mapped verdict, which
> stated the partial-write-back was "NOT asserted." The live tree shows it IS asserted (@269-282).
> This is the value of the PRP's Critical #2 ("RE-VERIFY LIVE; DON'T TRUST THE LINE NUMBERS BLINDLY")
> — the research note's snapshot was stale on this one point; the live audit supersedes it.

### 3.2 Nuance #2 — boot `phase='unloaded'` / `models_loaded=False` VALUES are not explicitly asserted

`test_state_shape_has_the_documented_fields` (test_feedback.py:125-128) asserts the exact 7-key
**SET** (after `update_partial("x")`, which means a write happened — the boot dict was serialized),
and `test_set_mode_writes_mode_field` (test_feedback.py:140) asserts the boot `mode == "normal"`.
But **no test explicitly asserts boot `phase == "unloaded"` or `models_loaded is False`** at
construction (confirmed by grep — no assertion pins those two boot values). The CODE defaults are
correct (feedback.py:97-98: `"phase": "unloaded"`, `"models_loaded": False`); the shape test
exercises them implicitly without checking their VALUES. A future test task could add a dedicated
boot-value assertion; **this audit does not add tests** (it only reports — read-only). The boot
state is nonetheless verified COMPLIANT by the source evidence (@97-98).

### 3.3 Scope boundaries (what this audit does NOT cover — recorded for boundary clarity)

- **Throttle / atomic-write / hyprctl-notify are P1.M3.T1.S2** (the NEXT subtask). This audit is the
  SCHEMA (the 6 checks) only. The `time.monotonic()` throttle clock (@116) is mentioned ONLY to
  distinguish it from the `ts` wall-epoch clock (check (f)); its >=10 Hz cap, the tempfile+`os.replace`
  atomic write, and the hyprctl notify events are S2's scope.
- **Daemon call sites are P1.M2.\*** (Complete). Whether the daemon CALLS `set_phase`/`set_mode` at
  the right lifecycle moments is out of scope here — `feedback.py` just PUBLISHES what it's told; this
  audit verifies the schema + the methods' write semantics, not the daemon's orchestration.
- **No source modified.** `feedback.py` and `tests/test_feedback.py` are READ-ONLY here. The only new
  artifact is this report (`gap_feedback.md`).

---

## 4. Conclusion

The `voice_typing/feedback.py` `state.json` schema faithfully implements **PRD §4.6** on all 6 item
checks (a)–(f): the `_state` dict has **exactly the 7 PRD fields** (a); the **boot state is
`phase='unloaded'` + `models_loaded=False`** (b); `set_phase` accepts any string the daemon passes
(the 5 lifecycle values) (c); the **`mode` field** (`normal`|`lite`) is written by `set_mode` with
a correct `"normal"` boot default (d); **`record_final` writes BOTH `last_final` AND `partial`** —
the PRD §4.6 "record_final ALSO writes the finalized text back into the partial field" clause (e);
and **`ts` uses `time.time()` (wall epoch)**, correctly distinct from the throttle's
`time.monotonic()` clock (f). All with `voice_typing/feedback.py` file:line evidence; the contract's
run target is **38 passed in 0.04s** (re-ran live).

The two recorded non-defect nuances are test-coverage observations, not code gaps: the older
`test_record_final_sets_last_final` asserts `last_final` only (but the dedicated
`test_record_final_updates_partial_so_status_matches_screen` DOES pin the partial write-back — nuance
§3.1), and no test explicitly asserts the boot `phase`/`models_loaded` VALUES (nuance §3.2). The code
is compliant regardless.

**Verdict: ✅ COMPLIANT on all 6 checks — no fix needed.** **No source files were modified** (this is
a read-only audit — the schema is PRD §4.6-compliant per this re-verification; no defect was found).
The only artifact produced by this subtask is this report. Adjacent concerns are correctly deferred:
**atomic-write / throttle / hyprctl-notify** is P1.M3.T1.S2; **daemon call sites** (phase/mode
orchestration) are P1.M2.\* (Complete).
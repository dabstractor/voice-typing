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

---

# Gap Report — P1.M3.T1.S2: Feedback atomic writes, throttling, hyprctl notify vs PRD §4.6

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Appended to `gap_feedback.md` (the state.json-SCHEMA audit above is **P1.M3.T1.S1**; this
section is **P1.M3.T1.S2**). Audit `voice_typing/feedback.py`'s **atomic-write**, **partial-write
throttling (≥10 Hz)**, and **hyprctl-notify discipline** against PRD §4.6 on the 7 item checks (a)-(g).
Audited regions: `_write` (atomic tempfile+rename, mode 0600 / dir 0700), `update_partial` (throttle:
in-memory update BEFORE the disk-write gate), `_notify` + every caller (notify fires only on
listening-start / cold-load / final / listening-stop, gated by `hypr_notify`, the final popup also by
`notify_on_final`, and NEVER on `update_partial`/`set_phase`). Audited artifacts (all read-only):
`voice_typing/feedback.py` + `tests/test_feedback.py`.
**Bottom line:** ✅ `feedback.py` is **COMPLIANT** with PRD §4.6 on all 7 checks — each mapped to a
`feedback.py` file:line + a pinning `tests/test_feedback.py` test, and the 38-test suite is green
(`subprocess.run` + `time.monotonic` mocked). **No source files were modified.** Two non-blocking
observations (the `mkstemp`-vs-`NamedTemporaryFile` primitive; the throttle-constant naming) are
recorded in §4 so they are not mistaken for defects.

## 1. Method

Each of the 7 checks was mapped 1:1 to its `feedback.py` implementation by `grep -n` (the file:line
evidence), the "no `_notify` in `update_partial`/`set_phase`" anti-spam invariant was checked directly
by enumerating every `_notify(` call site, and the full `tests/test_feedback.py` suite was **re-run
live** to record the actual pass count. Nothing was assumed from the PRP's embedded numbers — every
figure + line below was re-verified this round (pure stdlib: `json`/`os`/`subprocess`/`tempfile`/
`time`; no GPU/daemon required).

### Commands run (re-verification)

```bash
# (a) atomic write; (b) throttle constant + clock; (c) in-memory-before-throttle;
# (d) notify argv; (e)/(f) the hypr_notify + notify_on_final gates; (g) the no-notify-on-partial/phase invariant
grep -nE 'tempfile\.mkstemp|os\.replace\(tmp, path\)|os\.makedirs\(directory' voice_typing/feedback.py
grep -nE '_PARTIAL_WRITE_MIN_INTERVAL = 0\.1|time\.monotonic\(\)' voice_typing/feedback.py
grep -nE 'self\._state\["partial"\] = text|if now - self\._last_partial_write' voice_typing/feedback.py
grep -nE 'subprocess\.run\(\s*\["hyprctl"|_HYPR_ICON|_HYPR_COLOR' voice_typing/feedback.py
grep -nE 'if self\._cfg\.hypr_notify|notify_on_final' voice_typing/feedback.py
grep -nE '_notify\(' voice_typing/feedback.py   # enumerate the callers (anti-spam check (g))

# the contract's run command, LIVE
.venv/bin/python -m pytest tests/test_feedback.py -q
```

## 2. Per-check compliance table (PRD §4.6 vs `feedback.py`)

| # | PRD §4.6 requirement | `feedback.py` actual | file:line | Pinning tests (`tests/test_feedback.py`) | Verdict |
|---|---|---|---|---|---|
| **(a)** | state file written atomically (tempfile + rename); mode 0600, dir 0700 | `_write` does `os.makedirs(dir, exist_ok=True, mode=0o700)` → `tempfile.mkstemp(dir=<state dir>, prefix=".state.", suffix=".tmp")` (mode 0o600 by mkstemp default) → `json.dump` → `os.replace(tmp, path)` (same-filesystem POSIX-atomic rename); the orphan temp is `os.unlink`'d on ANY failure (`except BaseException`) | `_write` `:218`; `makedirs 0o700` `:230`; `mkstemp` `:231`; `os.replace` `:235`; docstring `:34` | `test_atomic_write_leaves_no_tmp_files` `:164`; `test_state_file_mode_0600` `:172`; `test_state_dir_mode_0700` `:179` | ✅ |
| **(b)** | partial DISK writes throttled ≥10 Hz (min 0.1 s) | `_PARTIAL_WRITE_MIN_INTERVAL = 0.1` (module constant); the throttle clock is `time.monotonic()` (never `time.time()` — wall clock can jump backward on NTP and freeze the partial forever) | `_PARTIAL_WRITE_MIN_INTERVAL = 0.1` `:77`; monotonic clock `:116` | `test_first_partial_always_writes` `:194`; `test_throttle_skips_write_within_0_1s` `:200`; `test_throttle_releases_after_0_1s` `:208` | ✅ |
| **(c)** | in-memory partial ALWAYS updated (before the throttle gate) | `update_partial` sets `self._state["partial"] = text` FIRST, THEN checks `if now - self._last_partial_write < _PARTIAL_WRITE_MIN_INTERVAL: return` — so a throttled call still captures the latest words and the next non-throttled flush writes them | `update_partial` `:109`; `partial = text` `:115` (BEFORE); throttle gate `:117` | `test_in_memory_partial_updated_even_when_throttled` `:216` | ✅ |
| **(d)** | `hyprctl notify` fires fire-and-forget | `_notify` runs `subprocess.run(["hyprctl", "notify", _HYPR_ICON, str(notify_ms), _HYPR_COLOR, msg], check=False, stdout=DEVNULL, stderr=DEVNULL)`; icon `-1` (no icon) + Nord frost `rgb(88c0d0)`; catches `(OSError, SubprocessError)` and logs at DEBUG so a notify failure never crashes the daemon | `_notify` `:245`; argv `:254`; `_HYPR_ICON = "-1"` `:82`; `_HYPR_COLOR` `:83` | `test_hyprctl_argv_exact_on_listening_start` `:246`; `test_hyprctl_passes_check_false_and_devnull` `:254` | ✅ |
| **(e)** | notify gated by `hypr_notify` (master switch) | EVERY notify call site checks `self._cfg.hypr_notify`: `record_final` (`:168`), `set_listening` (`:190`), ad-hoc `notify()` (`:213`) — `hypr_notify=False` suppresses ALL popups | `:168`, `:190`, `:213` | `test_no_notify_when_hypr_notify_false` `:340` (asserts `rec.argvs == []` `:345`) | ✅ |
| **(f)** | final popup gated by `notify_on_final` | `record_final` gates on BOTH: `if self._cfg.hypr_notify and self._cfg.notify_on_final: self._notify("✔ " + text)` — `notify_on_final=False` suppresses ONLY the final popup (start/stop still fire) | `record_final` `:153`; gate `:168`; `_notify("✔ " + text)` `:169` | `test_record_final_notifies_with_check_glyph` `:263`; `test_record_final_silent_when_notify_on_final_false` `:285`; `test_record_final_updates_partial_so_status_matches_screen` `:269` | ✅ |
| **(g)** | NEVER notify on `update_partial` or `set_phase` (anti-spam) | `update_partial` (`:109-120`) and `set_phase` (`:122`) contain NO `_notify` call. `grep -nE '_notify\('` lists exactly THREE call sites — `record_final:169`, `set_listening:191`, ad-hoc `notify():214` — none in `update_partial`/`set_phase`/`set_models_loaded`/`set_mode` | callers enumerated via `grep _notify` | `test_update_partial_never_invokes_hyprctl` `:308`; `test_set_phase_never_invokes_hyprctl` `:316`; `test_no_notify_on_noop_listening_transition` `:322`; `test_no_double_notify_when_set_true_twice` `:329` | ✅ |

> All 7 checks **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this
> round. The anti-spam invariant (check (g)) holds literally: `grep -nE '_notify\(' voice_typing/feedback.py`
> returns exactly three call sites, none of which are `update_partial`/`set_phase`.

## 3. Test results

```
.venv/bin/python -m pytest tests/test_feedback.py -q
......................................                                   [100%]
38 passed in 0.04s
```

**38 passed, 0 failed, 0 errors.** Coverage by concern: atomic write (`:164`/`:172`/`:179`); throttle
(`:194`/`:200`/`:208`/`:216` + the not-throttled `set_phase`/`record_final` `:225`/`:233`); hyprctl argv
+ `check=False`/DEVNULL (`:246`/`:254`); the `✔`-glyph final + `notify_on_final=False` suppression
(`:263`/`:285`); start/stop transitions (`:301`); the anti-spam "never per partial / never per phase"
contract (`:308`/`:316`); the no-op-transition + no-double-notify guards (`:322`/`:329`); the
`hypr_notify=False` master gate (`:340`). Every one of the 7 checks has at least one dedicated pinning test.

## 4. Non-defect nuances (recorded so they are not mistaken for code gaps)

### 4.1 (a) `mkstemp`, not `NamedTemporaryFile` — atomic intent met, arguably stronger

The item's check (a) wording names `tempfile.NamedTemporaryFile`; the code uses **`tempfile.mkstemp`**
(`feedback.py:231`) + `os.replace` (`:235`). Both achieve the same-filesystem POSIX-atomic rename PRD
§4.6 requires ("atomic write via tempfile+rename"). `mkstemp` is the **stronger** primitive: it returns
a raw file descriptor + path (mode `0o600` by Python's default), avoids `NamedTemporaryFile`'s
close-vs-delete dance, and makes the `0o600`-mode inheritance + the `except BaseException: os.unlink(tmp)`
cleanup deterministic. **The atomic-write contract is MET** — this is a wording mismatch in the audit
checklist, not a code gap. Do NOT "migrate" to `NamedTemporaryFile` (it would weaken the cleanup + mode
guarantees). This mirrors the "compliant-by-design" recording convention used in `gap_typing.md` §4.1.

### 4.2 (b) constant is `_PARTIAL_WRITE_MIN_INTERVAL`, not `_PARTIAL_WRITE_MIN_INTERVAL_S`

The item's check (b) names `_PARTIAL_WRITE_MIN_INTERVAL_S`; the code names it `_PARTIAL_WRITE_MIN_INTERVAL`
(`feedback.py:77`). Same value (`0.1` = ≥10 Hz), same intent. The unit (seconds) is documented at the
declaration (`# Minimum seconds between update_partial DISK writes`). NON-DEFECT — naming only.

## 5. Conclusion

**PASS — no fix required.** `voice_typing/feedback.py` is PRD §4.6-compliant on all 7 atomic-write /
throttle / hyprctl-notify checks: atomic `mkstemp`+`os.replace` (`:231`/`:235`) with `0o600` file +
`0o700` dir modes; ≥10 Hz throttle (`_PARTIAL_WRITE_MIN_INTERVAL = 0.1` `:77`) with the in-memory
partial updated BEFORE the disk-write gate (`:115` before `:117`); fire-and-forget `hyprctl notify`
(`:245`) gated everywhere by `hypr_notify` (`:168`/`:190`/`:213`), the final popup additionally by
`notify_on_final` (`:168`), and `_notify` invoked ONLY from `record_final`/`set_listening`/`notify()`
— never from `update_partial`/`set_phase`. The 38-test suite pins every check.

**No source changes were required and none were made.** This section appends to the state.json-schema
audit (**P1.M3.T1.S1**) above; together they close **P1.M3.T1** (the full `feedback.py` vs PRD §4.6
audit). Downstream **P1.M5.T5** (acceptance cross-check) can consume this section as the evidence that
the atomic-write + throttle + notify discipline matches PRD §4.6.
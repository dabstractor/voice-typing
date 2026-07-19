# Research — P1.M3.T1.S2 Audit feedback.py atomic writes / throttling / hyprctl notify (vs PRD §4.6)

This is a **READ-ONLY AUDIT**. The deliverable is a section **APPENDED** to
`plan/006_862ee9d6ef41/architecture/gap_feedback.md` (created by the parallel **P1.M3.T1.S1** with the
state.json-SCHEMA audit). NO source code is modified. Ground truth gathered by reading
`voice_typing/feedback.py` + `tests/test_feedback.py` + the sibling `gap_typing.md` format + the S1 PRP
on 2026-07-18.

---

## 0. Coordination with S1 (CRITICAL — the append contract)

- **S1 (P1.M3.T1.S1) CREATES `gap_feedback.md`** with the SCHEMA audit (6 checks a-f: fields, boot state,
  set_phase, set_mode, record_final→partial, ts=time.time). Its title is `# Gap Report — P1.M3.T1.S1:
  Feedback state.json schema vs PRD §4.6`. Its scope is the SCHEMA ONLY (it explicitly excludes
  atomic-write/throttle/notify = S2).
- **S2 (THIS task) APPENDS** the atomic-write / throttle / hyprctl-notify audit (7 checks a-g) to the
  END of that same file, as a clearly-delineated second section (`---` separator + its own title
  `# Gap Report — P1.M3.T1.S2: …`). It does NOT duplicate the schema content.
- Both run in parallel. S2's PRP treats S1 as a CONTRACT (gap_feedback.md exists with the schema
  report). The implementer re-verifies the file exists (grep the S1 title) before appending; if S1 has
  not landed yet, the implementer creates the file with a brief shared header + the S2 section (so the
  file is still valid) and notes S1's section is pending — robust to either landing order.

---

## 1. VERIFIED VERDICT: feedback.py is COMPLIANT on all 7 checks

Re-verified by `grep -n` + read of `voice_typing/feedback.py`. Each check → file:line evidence:

| Check | Contract (item / PRD §4.6) | Verdict | Evidence (feedback.py) |
|---|---|---|---|
| (a) atomic write | state file written atomically (tempfile + rename); mode 0600, dir 0700 | ✅ | `_write` `:218`: `os.makedirs(directory, exist_ok=True, mode=0o700)` `:230` → `tempfile.mkstemp(dir=directory, prefix=".state.", suffix=".tmp")` `:231` (mode 0o600 default) → `json.dump` → `os.replace(tmp, path)` `:235` (same-FS POSIX-atomic); orphan temp `os.unlink`'d on `except BaseException`. Docstring `:34`. |
| (b) throttle ≥10 Hz | min 0.1 s between partial DISK writes | ✅ | `_PARTIAL_WRITE_MIN_INTERVAL = 0.1` `:77`; clock `time.monotonic()` `:116` (never `time.time()` — wall clock jumps on NTP). |
| (c) in-memory BEFORE throttle | in-memory partial ALWAYS updated; only the disk write is gated | ✅ | `update_partial` `:109`: `self._state["partial"] = text` `:115` THEN `if now - self._last_partial_write < _PARTIAL_WRITE_MIN_INTERVAL: return` `:117`. |
| (d) notify fire-and-forget | `subprocess.run(["hyprctl","notify","-1",str(notify_ms),"rgb(88c0d0)",msg])`, swallow errors | ✅ | `_notify` `:245`: `subprocess.run(["hyprctl","notify",_HYPR_ICON, str(notify_ms), _HYPR_COLOR, msg], check=False, stdout=DEVNULL, stderr=DEVNULL)`; `_HYPR_ICON="-1"` `:82`, `_HYPR_COLOR="rgb(88c0d0)"` `:83`; catches `(OSError, SubprocessError)` @ DEBUG. |
| (e) hypr_notify gate | every notify gated by `hypr_notify` | ✅ | `record_final` `:168`, `set_listening` `:190`, `notify()` `:213` ALL check `self._cfg.hypr_notify`. |
| (f) final gated by notify_on_final | `✔ <text>` popup additionally gated by `notify_on_final` | ✅ | `record_final` `:168`: `if self._cfg.hypr_notify and self._cfg.notify_on_final:` → `_notify("✔ " + text)` `:169`. |
| (g) NEVER notify on update_partial / set_phase | anti-spam: partials/phase → state file ONLY | ✅ | `update_partial` (`:109-120`) + `set_phase` (`:122`) have NO `_notify` call. `grep -nE '_notify\('` lists exactly 3 callers: `record_final:169`, `set_listening:191`, `notify():214`. `set_models_loaded`/`set_mode` likewise never notify. |

**Bottom line (expected):** ✅ All 7 checks COMPLIANT — no code defect. The only new artifact is the
appended section in `gap_feedback.md`. (The audit re-confirms this live; if a check fails on re-read,
document it as a real gap for a SEPARATE remediation task — this audit does NOT fix code.)

---

## 2. The 2 NON-DEFECT nuances (record so they aren't mistaken for gaps — mirror gap_typing.md §4)

1. **(a) `mkstemp`, not `NamedTemporaryFile`.** The item's check (a) wording names
   `tempfile.NamedTemporaryFile`; the code uses `tempfile.mkstemp` (`:231`) + `os.replace` (`:235`).
   Both achieve the same-filesystem POSIX-atomic rename PRD §4.6 requires. `mkstemp` is the STRONGER
   primitive (raw fd, deterministic mode 0o600, clean `except BaseException: os.unlink(tmp)` cleanup,
   no NamedTemporaryFile close-vs-delete dance). The atomic-write CONTRACT is MET — wording mismatch in
   the checklist, NOT a code gap. Do NOT migrate to `NamedTemporaryFile` (it would weaken cleanup/mode).
2. **(b) constant naming.** The item names `_PARTIAL_WRITE_MIN_INTERVAL_S`; the code names it
   `_PARTIAL_WRITE_MIN_INTERVAL` (`:77`). Same value (`0.1` = ≥10 Hz), same intent. The unit (seconds)
   is documented at the declaration. NON-DEFECT — naming only.

---

## 3. Test coverage (tests/test_feedback.py — 38 tests, re-run live: **38 passed in 0.04s**)

Every one of the 7 checks has ≥1 dedicated pinning test:
- (a) atomic: `test_atomic_write_leaves_no_tmp_files` `:164`; `test_state_file_mode_0600` `:172`;
  `test_state_dir_mode_0700` `:179`.
- (b) throttle: `test_first_partial_always_writes` `:194`; `test_throttle_skips_write_within_0_1s` `:200`;
  `test_throttle_releases_after_0_1s` `:208`.
- (c) in-memory-before-throttle: `test_in_memory_partial_updated_even_when_throttled` `:216`.
- (d) notify argv + fire-and-forget: `test_hyprctl_argv_exact_on_listening_start` `:246`;
  `test_hyprctl_passes_check_false_and_devnull` `:254`.
- (e) hypr_notify=False gate: the `:340` test (`hypr_notify=False` → `rec.argvs == []` `:345`).
- (f) notify_on_final: `test_record_final_notifies_with_check_glyph` `:263`;
  `test_record_final_silent_when_notify_on_final_false` `:285`.
- (g) anti-spam: `test_update_partial_never_invokes_hyprctl` `:308`;
  `test_set_phase_never_invokes_hyprctl` `:316`; `test_no_notify_on_noop_listening_transition` `:322`;
  `test_no_double_notify_when_set_true_twice` `:329`.

The suite mocks `subprocess.run` (hyprctl argv captured, never sent) + `time.monotonic` (controllable
fake clock for the throttle). GPU-free; fast.

---

## 4. The test command (the contract's run target)

```
.venv/bin/python -m pytest tests/test_feedback.py -q
```
FULL PATH (`.venv/bin/python` — zsh aliases `python`/`pytest`). mypy NOT installed — do NOT run it.
ruff optional (`/home/dustin/.local/bin/ruff`, NOT a gate). The audit re-runs it live and records the
pass count (38) in the appended section.

---

## 5. Format + scope

- **FORMAT:** mirror `gap_typing.md` (title + Date + Scope + Audited artifacts + Bottom line + §1 Method
  w/ commands + §2 per-check table (file:line + pinning test + ✅) + §3 test results + §4 non-defect
  nuances + §5 conclusion). The appended section is a self-contained gap report scoped to the 7
  atomic/throttle/notify checks, preceded by a `---` separator so it is visually distinct from S1's
  schema report above it.
- **SCOPE:** atomic-write / throttle / hyprctl-notify ONLY (the 7 checks). NOT the schema (S1), NOT the
  daemon's call sites (P1.M2.* Complete), NOT status.sh/README (item DOCS: none).
- **READ-ONLY.** No source files modified. The ONLY artifact change is appending to `gap_feedback.md`.
  Re-verify live (re-grep + re-read + re-run tests); cite the CURRENT file:line (line numbers drift).
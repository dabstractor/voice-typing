# PRP — P1.M3.T1.S2: Audit feedback.py atomic writes, throttling, hyprctl notify events & run tests

## Goal

**Feature Goal**: Produce the authoritative **atomic-write / throttling / hyprctl-notify audit** for
`voice_typing/feedback.py` against PRD §4.6 — verifying the 7 item checks (a)-(g): atomic tempfile+rename
write (mode 0600 / dir 0700), the ≥10 Hz partial-disk-write throttle, in-memory-update-before-throttle-gate,
the fire-and-forget `hyprctl notify` argv, the `hypr_notify` master gate, the `notify_on_final` final
gate, and the anti-spam "never notify on `update_partial`/`set_phase`" invariant. This is a
**READ-ONLY AUDIT**: the deliverable is a report section; NO source code is modified (the code is
compliant — this PRP's research verified it; the audit re-confirms live).

**Deliverable** (ONE artifact — append to an existing report; do NOT create a new standalone file):
- `plan/006_862ee9d6ef41/architecture/gap_feedback.md` — **APPEND** a self-contained `# Gap Report —
  P1.M3.T1.S2: …` section to the END of the file the parallel **P1.M3.T1.S1** creates (the state.json-
  SCHEMA audit). A `---` separator precedes it so it is visually distinct from S1's schema report.
  Format mirrors `gap_typing.md`. Verbatim content in Implementation Blueprint → Task 3.

**Success Definition**:
- (a) The appended section verifies all 7 checks against the LIVE `voice_typing/feedback.py` (re-grep +
  re-read — not trusting this PRP's verdict blindly) and records a ✅ verdict + file:line evidence +
  a pinning `tests/test_feedback.py` test for each.
- (b) `.venv/bin/python -m pytest tests/test_feedback.py -q` is re-run live and the pass count (38) is
  recorded in the appended section (the contract's mandated run command).
- (c) The 2 non-defect nuances (`mkstemp`-vs-`NamedTemporaryFile`; the throttle-constant naming) are
  recorded in a §4 so they are not mistaken for code gaps.
- (d) **No source files are modified** — `feedback.py` is compliant; the only artifact change is the
  append to `gap_feedback.md`. `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_feedback.md`.
- (e) The section's scope is atomic-write/throttle/notify ONLY (the 7 checks) — NOT the schema (S1)
  and NOT the daemon's call sites (P1.M2.*, Complete).
- (f) The section APPENDS to (does not overwrite) S1's schema report, with a `---` separator + its own
  title, so both subtasks' audits coexist in one file.

> **VERIFIED VERDICT (this PRP's research): feedback.py is COMPLIANT on all 7 checks — no code fix
> needed.** The audit's job is to re-confirm this live and document it with evidence + the 2 non-defect
> nuances. If a check surprisingly fails on re-read, document it as a real gap for a SEPARATE
> remediation task (this audit does not fix code).

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance cross-check)
who needs an authoritative, file:line-evidenced record that feedback.py's atomic-write / throttle /
notify discipline matches PRD §4.6 — so external consumers (`status.sh`, the tmux status line) see a
consistent state file and the user is never spammed by per-partial hyprctl popups.

**Use Case**: A reviewer asks "does feedback write state.json atomically, throttle partial writes to
≥10 Hz, and fire hyprctl ONLY on start/cold-load/final/stop?" The appended section answers yes/no per
check with the exact source lines + the pinning test.

**Pain Points Addressed**: Without this audit, a regression (a non-atomic write that lets a tmux jq-reader
see a torn JSON; a dropped throttle that spams disk; a stray `_notify` in `update_partial` that floods
the screen with popups) would be invisible until a user sees flicker/spam. The audit pins the discipline
to PRD §4.6 with evidence.

## Why

- **PRD §4.6's atomic-write + anti-spam contracts are load-bearing for UX.** The state file is read by
  `status.sh` (tmux status-interval 1 s) via jq — a torn write would render a broken status line. And
  "Hyprland notifications are not replaceable by ID, so per-partial popups would stack into unreadable
  spam" (§4.6) — the anti-spam rule (check (g)) is what keeps the desktop usable. This audit proves both.
- **Closes the feedback audit area** (P1.M3.T1). S1 owns the schema; this task (S2) owns the
  write-mechanics + notify discipline. Together they are the full feedback.py-vs-§4.6 audit. Every other
  audit area in round 006 produced a `gap_*.md`; feedback is split schema(S1)+mechanics(S2) into one file.
- **Read-only + parallel-safe.** The audit reads `feedback.py` + `tests/test_feedback.py` and appends to
  `gap_feedback.md`. S1 creates that file (schema section, different content); S2 appends (different
  content, end of file). No source edits → no conflict with any in-flight implementation task.
- **The research already did the work.** This PRP's research note pre-maps every check to its file:line
  + verdict + pinning test, so the implementing agent re-verifies + writes the appended section in one
  pass (the value of a PRP: curated context, not open-ended exploration).

## What

A read-only verification of `voice_typing/feedback.py`'s atomic-write (`_write`), throttle
(`update_partial`), and notify discipline (`_notify` + every caller), re-confirmed live, then documented
as an appended section in `gap_feedback.md` (mirroring `gap_typing.md`'s format). The 7 checks:
(a) atomic `tempfile`+`os.replace` (mode 0600 / dir 0700); (b) throttle constant 0.1 (≥10 Hz);
(c) in-memory update before the throttle gate; (d) fire-and-forget `hyprctl notify` argv;
(e) `hypr_notify` master gate; (f) `notify_on_final` final gate; (g) no notify on `update_partial`/
`set_phase`. Plus the live test run + the 2 non-defect nuances.

### Success Criteria

- [ ] `architecture/gap_feedback.md` contains an appended section titled `# Gap Report — P1.M3.T1.S2: Feedback atomic writes, throttling, hyprctl notify vs PRD §4.6` (preceded by a `---` separator, AFTER S1's schema section).
- [ ] The section records a ✅ verdict + `feedback.py` file:line + a `tests/test_feedback.py` pinning test for each of the 7 checks (a-g).
- [ ] `.venv/bin/python -m pytest tests/test_feedback.py -q` is re-run live; its pass count (38) is recorded.
- [ ] The 2 non-defect nuances (`mkstemp`-vs-`NamedTemporaryFile`; `_PARTIAL_WRITE_MIN_INTERVAL` naming) are documented in a §4.
- [ ] The section's scope is atomic/throttle/notify ONLY — not the schema (S1), not daemon call-sites (P1.M2.*).
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_feedback.md` — NO source files modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task
nature (read-only audit → appended report section), the S1 coordination (it creates gap_feedback.md;
this appends), the `gap_typing.md` FORMAT template, the verified verdict (compliant) + the file:line
evidence + the pinning test for all 7 checks, the 2 non-defect nuances, the exact test command, and the
scope boundaries are all pinned. The audit re-verifies live (re-grep + re-read + re-run) rather than
trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + file:line evidence + the 2 nuances + the append coordination + scope
- docfile: plan/006_862ee9d6ef41/P1M3T1S2/research/feedback_atomic_throttle_notify_audit.md
  why: "§0 THE APPEND COORDINATION (S1 creates gap_feedback.md schema section; S2 appends this section).
        §1 THE VERIFIED VERDICT: a 7-row table mapping each check (a-g) to its feedback.py file:line +
        ✅ COMPLIANT. §2 the 2 NON-DEFECT nuances (mkstemp vs NamedTemporaryFile; constant naming).
        §3 the test coverage map (each check -> its pinning test). §4 the test command. §5 format + scope."
  section: "ALL load-bearing. §0 (append contract), §1 (verdict table), §2 (nuances), §3 (test map)."

# MUST READ — the file being audited (_write atomic; update_partial throttle; _notify + callers)
- file: voice_typing/feedback.py
  why: "AUDIT TARGET (read-only). _write L218 (atomic): makedirs 0o700 @230, mkstemp @231, os.replace
        @235, BaseException unlink. update_partial L109 (throttle): partial=text @115 BEFORE the gate
        @117; _PARTIAL_WRITE_MIN_INTERVAL=0.1 @77; monotonic clock @116. _notify L245 (argv: hyprctl/
        notify/-1/notify_ms/rgb(88c0d0)/msg; check=False+DEVNULL; catches OSError+SubprocessError);
        _HYPR_ICON/-COLOR @82-83. record_final L153 gate @168 (hypr_notify AND notify_on_final) ->
        _notify('✔ '+text) @169. set_listening L171 gate @190 (hypr_notify AND transition) -> _notify @191.
        notify() L213 gate @213 (hypr_notify). update_partial/set_phase/set_models_loaded/set_mode: NO _notify."
  critical: "RE-VERIFY by grep + read — do NOT trust the line numbers blindly (re-locate them live).
             The audit READS this file; it does NOT edit it (compliant code = no modification)."

# MUST READ — the test file (coverage to cite per check)
- file: tests/test_feedback.py
  why: "38-test suite (the contract's run command); subprocess.run MOCKED + time.monotonic mocked. Per-
        check tests: (a) atomic :164/:172/:179; (b) throttle :194/:200/:208; (c) in-memory :216;
        (d) argv :246/:254; (e) hypr_notify=False :340; (f) notify_on_final :263/:285; (g) anti-spam
        :308/:316/:322/:329. Run it live + record the count (38)."
  critical: "Characterize coverage accurately (cite the test that pins each check). Do NOT add tests
             (read-only). The hypr_notify=False gate DOES have a test (:340) — check (e) is covered."

# MUST READ — the gap-report FORMAT template (mirror its structure for the appended section)
- file: plan/006_862ee9d6ef41/architecture/gap_typing.md
  why: "The format template. Structure: title (`# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X`) + Date +
        Scope + Audited artifacts (read-only) + Bottom line (✅) + §1 Method (w/ commands run) + §2 per-
        check compliance TABLE (PRD req | actual | file:line | pinning test | ✅) + §3 Test results
        (the live count) + §4 non-defect nuances + §5 Conclusion (PASS; no fix). Mirror it EXACTLY."
  critical: "Mirror the structure. The appended section is a SELF-CONTAINED gap report scoped to the 7
             checks, preceded by a `---` separator so it is visually distinct from S1's schema section
             above it. Cite feedback.py file:line + a tests/test_feedback.py test per check."

# MUST READ — the parallel task contract (S1 CREATES gap_feedback.md; S2 APPENDS — do NOT duplicate schema)
- file: plan/006_862ee9d6ef41/P1M3T1S1/PRP.md
  why: "P1.M3.T1.S1 (IN PARALLEL) creates gap_feedback.md with the SCHEMA audit (6 checks a-f: fields,
        boot state, set_phase, set_mode, record_final->partial, ts=time.time). Its title is
        '# Gap Report — P1.M3.T1.S1: Feedback state.json schema vs PRD §4.6'. Its scope EXCLUDES
        atomic/throttle/notify (='S2', i.e. this task). S2 APPENDS after S1's §5 Conclusion."
  critical: "Do NOT overwrite S1's schema section. APPEND a new section at the END. If gap_feedback.md
             does not yet exist (S1 not landed), create it with a brief shared header noting S1's schema
             section is pending, then add the S2 section — robust to either landing order. Do NOT audit
             the schema here (S1 owns it)."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.6 Feedback: 'atomic write via tempfile+rename' + 'Written on every partial update (throttle
        to >=10 Hz max)' + 'hyprctl notify ... fire-and-forget, swallow errors ... only notify on:
        listening-start, each final (gated by notify_on_final), listening-stop' + 'Partials go to the
        state file only'. This is the authoritative spec each check is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.6 as the contract."

# CONTEXT — a second format reference (the largest gap report; same structure)
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "Another gap report in the series (same title/date/scope/bottom-line/method/findings/nuances/
        conclusion structure). Confirms the uniformity of the round-006 reports. (gap_typing.md is the
        closer analog — same size + the 'tested superset' non-defect-nuance pattern this audit mirrors.)"
  critical: "Read-only format reference. Do not copy its content."
```

### Current Codebase tree (state at P1.M3.T1.S2 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/feedback.py          # AUDIT TARGET (read-only — _write/update_partial/_notify + callers)
├── tests/test_feedback.py            # AUDIT (cite the pinning test per check; read-only)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_typing.md                 # FORMAT TEMPLATE (mirror its structure)
    ├── gap_lifecycle.md              # FORMAT REFERENCE (same structure)
    └── gap_feedback.md               # <-- APPEND the S2 section (S1 creates the file w/ the schema section)
# NO source files modified. The only artifact change is appending to gap_feedback.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_feedback.md   # MODIFIED (APPEND): + the S2 atomic/throttle/notify section
                                                     #   (S1's schema section stays above it; `---` separator).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT. The code is COMPLIANT (research §1). Do NOT modify feedback.py
#   or any source file. The ONLY artifact change is appending the S2 section to gap_feedback.md. If a
#   check fails on re-read, DOCUMENT it as a gap for a separate remediation task — do not fix it here.

# CRITICAL #2 — RE-VERIFY LIVE; DON'T TRUST THE LINE NUMBERS BLINDLY. The research pre-maps each check
#   to feedback.py file:line, but the audit must re-grep + re-read the live tree (mirrors gap_typing.md
#   "audit re-verified against the live tree"). Line numbers drift; the verdict must reflect the CURRENT
#   file. Re-run: grep -nE 'mkstemp|os\.replace|_PARTIAL_WRITE_MIN_INTERVAL|_notify\(|hypr_notify'
#   voice_typing/feedback.py

# CRITICAL #3 — APPEND, DON'T OVERWRITE. S1 (P1.M3.T1.S1) creates gap_feedback.md with the SCHEMA audit.
#   S2 APPENDS a new section at the END (after S1's §5 Conclusion), preceded by a `---` separator + its
#   own `# Gap Report — P1.M3.T1.S2: …` title. Do NOT edit/overwrite S1's schema section. If
#   gap_feedback.md does not yet exist (S1 not landed), create it with a brief shared header noting S1's
#   section is pending, then add the S2 section. (Research §0.)

# CRITICAL #4 — THE mkstemp NUANCE IS A NON-DEFECT, NOT A GAP. The item's check (a) wording names
#   tempfile.NamedTemporaryFile; the code uses tempfile.mkstemp (:231) + os.replace (:235). Both are
#   same-filesystem POSIX-atomic. mkstemp is STRONGER (raw fd, mode 0o600 default, clean BaseException
#   cleanup). Record it in §4 as a NON-DEFECT — do NOT flag it as a gap and do NOT "migrate" the code.
#   (Research §2 nuance 1.)

# CRITICAL #5 — THE THROTTLE CONSTANT NAME IS A NON-DEFECT. The item names _PARTIAL_WRITE_MIN_INTERVAL_S;
#   the code names it _PARTIAL_WRITE_MIN_INTERVAL (:77). Same value (0.1). Record in §4 as a NON-DEFECT,
#   not a gap. (Research §2 nuance 2.)

# CRITICAL #6 — CHECK (g) IS PROVEN BY ENUMERATING _notify CALLERS, not by a positive test alone. Run
#   `grep -nE '_notify\(' voice_typing/feedback.py` — it must list EXACTLY three call sites (record_final
#   :169, set_listening :191, notify() :214) and NONE in update_partial/set_phase/set_models_loaded/
#   set_mode. State this literal grep result in the §2 (g) row (mirrors gap_typing.md's "bare-tmux defect
#   check → CLEAN" idiom). (Research §1 check (g).)

# CRITICAL #7 — DON'T CONFLATE ts (time.time, wall epoch) WITH THE THROTTLE CLOCK (time.monotonic).
#   Check (b) is the throttle (monotonic @116); the ts field is S1's schema check (f), NOT here. This
#   audit's throttle evidence is _PARTIAL_WRITE_MIN_INTERVAL (:77) + the monotonic clock (:116). (S1 PRP.)

# GOTCHA #8 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest tests/test_feedback.py -q
#   (never bare python/pytest). mypy NOT installed — do NOT run it. ruff optional (not a gate). The
#   suite is GPU-free (subprocess + monotonic mocked) — fast (~0.04s).

# GOTCHA #9 — SCOPE = ATOMIC/THROTTLE/NOTIFY ONLY (the 7 checks). NOT the schema (S1), NOT the daemon's
#   call sites (P1.M2.* Complete), NOT status.sh/README (item DOCS: none). feedback.py just implements
#   the write/notify mechanics; whether the daemon CALLS them at the right moments is out of scope.
```

## Implementation Blueprint

### Data models and structure

Not applicable — no code, no data models. The "data" is the audit's findings table (7 checks → verdict +
file:line + pinning test), recorded as an appended section in `gap_feedback.md`.

### Audit Tasks (ordered — verify → run → append)

```yaml
Task 1: RE-VERIFY the 7 checks against the LIVE feedback.py (read-only; re-grep + re-read)
  - RUN (from /home/dustin/projects/voice-typing):
      grep -nE 'tempfile\.mkstemp|os\.replace\(tmp, path\)|os\.makedirs\(directory|except BaseException' voice_typing/feedback.py
      grep -nE '_PARTIAL_WRITE_MIN_INTERVAL = 0\.1|time\.monotonic\(\)' voice_typing/feedback.py
      grep -nE 'self\._state\["partial"\] = text|if now - self\._last_partial_write' voice_typing/feedback.py
      grep -nE 'subprocess\.run\(|_HYPR_ICON|_HYPR_COLOR' voice_typing/feedback.py
      grep -nE 'if self\._cfg\.hypr_notify|notify_on_final' voice_typing/feedback.py
      grep -nE '_notify\(' voice_typing/feedback.py     # enumerate the callers (check (g))
  - For each check (a)-(g), confirm the verdict + capture the CURRENT file:line (re-locate; Critical #2).
    Expected findings (research §1): all 7 ✅ COMPLIANT.
  - DO NOT edit feedback.py. This is read-only.

Task 2: RUN the test suite (the contract's run command; record the pass count)
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_feedback.py -q
  - EXPECTED: 38 passed (GPU-free; subprocess + monotonic mocked). Record the count + time in the
    appended section's §3. Cite the pinning test per check (research §3 map).

Task 3: APPEND the S2 section to plan/006_862ee9d6ef41/architecture/gap_feedback.md
  - FILE: plan/006_862ee9d6ef41/architecture/gap_feedback.md
  - FIRST: confirm S1's schema section exists (grep the S1 title). If absent (S1 not landed), create the
    file with a brief shared header noting the schema section (P1.M3.T1.S1) is pending, then add the S2
    section. If present, APPEND after S1's §5 Conclusion with a leading `---` separator.
  - CONTENT: the verbatim block in "Task 3 SOURCE" below (mirror gap_typing.md's structure — Critical #3).
  - ACCURACY: cite the LIVE file:line (from Task 1) + the LIVE pytest count (from Task 2). Replace the
    <N> / <today> placeholders with the real values. Re-verify the test line numbers (Critical #2).
  - DO NOT: modify feedback.py/tests/PRD.md/any source; overwrite S1's schema section; audit the schema
    (S1) or daemon call-sites (P1.M2.*); flag the mkstemp/constant-naming nuances as gaps.

Task 4: VALIDATE (no further file change — see Validation Loop)
  - The S2 section exists w/ the title + the 7-check table + the live pytest count + the 2 nuances.
  - git status --short shows ONLY gap_feedback.md (no source modified). No git commit unless directed.
```

#### Task 3 SOURCE — append verbatim to `gap_feedback.md` (after S1's schema section)

> Replace `<today>` with the audit date and confirm every file:line against the LIVE tree (Task 1) +
> the LIVE pytest count (Task 2). The block starts with a `---` separator so it is visually distinct
> from S1's schema report above it.

```markdown

---

# Gap Report — P1.M3.T1.S2: Feedback atomic writes, throttling, hyprctl notify vs PRD §4.6

**Date:** <today> (audit re-verified against the live tree)
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
| **(d)** | `hyprctl notify` fires fire-and-forget | `_notify` runs `subprocess.run(["hyprctl", "notify", "-1", str(notify_ms), "rgb(88c0d0)", msg], check=False, stdout=DEVNULL, stderr=DEVNULL)`; icon `-1` (no icon) + Nord frost `rgb(88c0d0)`; catches `(OSError, SubprocessError)` and logs at DEBUG so a notify failure never crashes the daemon | `_notify` `:245`; argv `:~252`; `_HYPR_ICON = "-1"` `:82`; `_HYPR_COLOR` `:83` | `test_hyprctl_argv_exact_on_listening_start` `:246`; `test_hyprctl_passes_check_false_and_devnull` `:254` | ✅ |
| **(e)** | notify gated by `hypr_notify` (master switch) | EVERY notify call site checks `self._cfg.hypr_notify`: `record_final` (`:168`), `set_listening` (`:190`), ad-hoc `notify()` (`:213`) — `hypr_notify=False` suppresses ALL popups | `:168`, `:190`, `:213` | `hypr_notify=False` test `:340` (asserts `rec.argvs == []` `:345`) | ✅ |
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
```

### Implementation Patterns & Key Details

```python
# PATTERN: each check -> PRD clause -> feedback.py file:line -> pinning test -> ✅ verdict (mirror
# gap_typing.md's §2 table). Example for check (g):
#   "(g) NEVER notify on update_partial/set_phase — PRD §4.6 'Partials go to the state file only.'
#    feedback.py: grep -nE '_notify(' lists exactly 3 callers (record_final:169, set_listening:191,
#    notify():214); update_partial(:109-120)/set_phase(:122) have NONE. ✅ COMPLIANT."

# PATTERN: non-defect nuances are recorded explicitly (gap_typing.md §4 style) so a future auditor does
# not re-flag them: "4.1 mkstemp not NamedTemporaryFile — atomic intent MET, stronger primitive. Do NOT
# migrate." / "4.2 constant named _PARTIAL_WRITE_MIN_INTERVAL not _..._S — same value. NON-DEFECT."

# GOTCHA: re-verify live; line numbers drift. The appended section cites the CURRENT file:line + the
# LIVE pytest count (replace <today>/<N> placeholders). (Critical #2.)

# GOTCHA: APPEND only. The `---` separator + the S2 title make the section visually distinct from S1's
# schema report. Do not touch S1's content. (Critical #3.)
```

### Integration Points

```yaml
AUDIT (read-only):
  - voice_typing/feedback.py: "READ — _write (atomic) / update_partial (throttle) / _notify + callers"
  - tests/test_feedback.py: "READ + RUN — cite the pinning test per check; record the live count"
REPORT (the deliverable):
  - append to: "plan/006_862ee9d6ef41/architecture/gap_feedback.md (S1 created it; S2 appends §S2)"
NO code/test/config changes:
  - feedback.py: UNCHANGED (compliant — read-only audit)
  - tests/test_feedback.py: UNCHANGED (cited, not edited)
  - PRD.md: READ-ONLY (forbidden)
DOWNSTREAM:
  - P1.M5.T5 (acceptance cross-check): "consumes this section as the atomic/throttle/notify evidence"
  - P1.M3.T1 (the parent): "S1 schema + S2 mechanics together close the feedback.py vs §4.6 audit"
```

## Validation Loop

> The audit's validation = re-run the test suite + verify the appended section exists w/ the right
> structure + git status shows only gap_feedback.md. No code is compiled/edited (read-only). FULL PATHS.

### Level 1: The audited file is unchanged (read-only guard)

```bash
cd /home/dustin/projects/voice-typing
echo "--- feedback.py / test_feedback.py NOT modified by this audit ---"
git status --porcelain voice_typing/feedback.py tests/test_feedback.py   # expect: empty (no modification)
```

### Level 2: The contract's test command (re-run live; record the count)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_feedback.py -q
# Expected: 38 passed (GPU-free). Record the pass count + time in the appended section's §3.
```

### Level 3: The appended section exists with the required structure

```bash
cd /home/dustin/projects/voice-typing
test -f plan/006_862ee9d6ef41/architecture/gap_feedback.md && echo "L3 gap_feedback.md exists" || echo "L3 FAIL"
grep -n 'Gap Report — P1.M3.T1.S2: Feedback atomic writes, throttling, hyprctl notify' plan/006_862ee9d6ef41/architecture/gap_feedback.md  # the S2 title
grep -cE '✅' plan/006_862ee9d6ef41/architecture/gap_feedback.md   # >=7 from S2 (one per check a-g) + S1's 6
grep -nE 'mkstemp.*not.*NamedTemporaryFile|_PARTIAL_WRITE_MIN_INTERVAL.*not.*_S|non-defect|nuance' plan/006_862ee9d6ef41/architecture/gap_feedback.md  # the 2 nuances recorded
grep -nE '38 passed' plan/006_862ee9d6ef41/architecture/gap_feedback.md   # the live pytest count
# Expected: the S2 title present; >=7 ✅ (S2's 7 + S1's 6 = 13 total); both nuances; the 38-passed line.
# Also confirm S1's schema section is STILL present (S2 appended, did not overwrite):
grep -n 'Gap Report — P1.M3.T1.S1: Feedback state.json schema' plan/006_862ee9d6ef41/architecture/gap_feedback.md  # S1's title intact
```

### Level 4: Scope guard

```bash
cd /home/dustin/projects/voice-typing
echo "--- ONLY gap_feedback.md changed; no source modified ---"
git status --porcelain
# Expected: " M plan/006_862ee9d6ef41/architecture/gap_feedback.md" (or "?? ..." if newly created by S1
#   this same round). Any M to voice_typing/feedback.py / tests/test_feedback.py / PRD.md = SCOPE VIOLATION.
echo "--- the S2 section is atomic/throttle/notify only (does not re-audit the schema) ---"
# (The S2 §2 table lists checks (a)-(g) — atomic/throttle/notify — NOT S1's schema checks. Confirm by
#  reading the §2 header; it must NOT duplicate S1's field/boot-state/set_phase-value checks.)
```

## Final Validation Checklist

### Technical Validation
- [ ] `git status --porcelain voice_typing/feedback.py tests/test_feedback.py` → empty (read-only).
- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_feedback.py -q` → 38 passed; count recorded in the appended §3.
- [ ] `gap_feedback.md` contains the `# Gap Report — P1.M3.T1.S2: …` section (appended, `---` separator).
- [ ] The section has a ✅ verdict + `feedback.py` file:line + a pinning test for each of the 7 checks (a)-(g).
- [ ] S1's schema section (`# Gap Report — P1.M3.T1.S1: …`) is still present above (append did not overwrite).

### Feature Validation
- [ ] Checks (a) atomic mkstemp+os.replace 0600/0700; (b) throttle 0.1 ≥10Hz; (c) in-memory before gate; (d) fire-and-forget hyprctl argv; (e) hypr_notify gate; (f) notify_on_final gate; (g) no _notify in update_partial/set_phase — each verified live with evidence + a pinning test.
- [ ] The 2 non-defect nuances (mkstemp-vs-NamedTemporaryFile; constant naming) are documented in §4.
- [ ] The section cites the LIVE file:line (re-verified, not this PRP's numbers).

### Code Quality Validation
- [ ] The appended section mirrors `gap_typing.md`'s structure (title + date + scope + audited artifacts + bottom line + method + findings table + test results + nuances + conclusion).
- [ ] Scope is atomic/throttle/notify (7 checks) only — no schema re-audit (S1), no daemon call-sites (P1.M2.*).
- [ ] Read-only — no source modified; APPEND only (S1's section intact).

### Documentation & Deployment
- [ ] `gap_feedback.md` is the only artifact change; it lands in the `architecture/gap_*.md` series.
- [ ] No README/ACCEPTANCE edits (item DOCS: none — internal mechanics).

---

## Anti-Patterns to Avoid

- ❌ Don't modify `feedback.py` or ANY source file — this is a READ-ONLY audit; the code is compliant (Critical #1).
- ❌ Don't trust this PRP's file:line numbers blindly — re-grep + re-read the live tree; cite the CURRENT lines (Critical #2).
- ❌ Don't OVERWRITE S1's schema section — APPEND a new section at the END with a `---` separator + the S2 title (Critical #3). If gap_feedback.md is absent (S1 pending), create it with a shared header + the S2 section.
- ❌ Don't flag `mkstemp`-vs-`NamedTemporaryFile` as a gap — it's a NON-DEFECT (atomic intent met, stronger primitive); record it in §4, do NOT migrate the code (Critical #4).
- ❌ Don't flag `_PARTIAL_WRITE_MIN_INTERVAL`-vs-`_..._S` as a gap — NON-DEFECT (same value 0.1); record in §4 (Critical #5).
- ❌ Don't conflate the throttle clock (`time.monotonic`) with `ts` (`time.time`) — check (b) is the throttle; `ts` is S1's schema check (Critical #7).
- ❌ Don't audit the schema (S1) or the daemon's call sites (P1.M2.*) — this audit is the write-mechanics + notify discipline only (Gotcha #9).
- ❌ Don't invent a report structure — mirror `gap_typing.md` (Critical #3 / the format template).
- ❌ Don't write the section anywhere except `plan/006_862ee9d6ef41/architecture/gap_feedback.md`.
- ❌ Don't run `mypy` (not installed) or bare `python`/`pytest` — use `.venv/bin/python -m pytest` (Gotcha #8).
- ❌ Don't add tests in this audit — it only REPORTS coverage; adding tests is a separate task (read-only).

---

**Confidence Score: 9.5/10** for one-pass success. The audit is read-only and the verdict is pre-established
(compliant on all 7 checks, with file:line + pinning-test evidence in the research note); the deliverable's
path + format are pinned to the established `gap_*.md` convention (confirmed by `gap_typing.md` + the
parallel S1/P1.M2.T4.S1 PRPs); the 2 non-defect nuances are identified; the test command + validation
greps are executable as written; and the verbatim appended-section content is provided in Task 3 SOURCE
(the implementer re-verifies the line numbers live + fills the `<today>` placeholder). The −0.5 reserves:
the audit must re-verify live (line numbers drift) + the S1/S2 append coordination (if both land
simultaneously there is a small write-ordering risk, mitigated by the "create with shared header if
absent" fallback) — but the grep gates (S2 title present; ≥7 ✅; both nuances; 38-passed line; S1 title
still present; only gap_feedback.md in git status; no source modified) catch structural/verdict/scope
regressions deterministically.
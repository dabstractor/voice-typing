# PRP — P1.M1.T3.S1: Record the named 20-case daemon baseline and correct test guidance (BUG-004)

## Goal

**Feature Goal**: Close bugfix **BUG-004** (Minor, documentation/classification debt): `tests/test_daemon.py` was misclassified as a CUDA hang vector and excluded from the G1 baseline, leaving its **20 legacy-red tests classified nowhere** — any sweep trusting "test_daemon.py is a CUDA suite, don't run it" flies blind over 20 reds. The fix is a **dated G1 CPU addendum** recording the exact **named** failed node IDs (one-line reason/facet each), a **future set-diff rule**, and corrected test guidance in the two docs that carry the mislabel — while preserving the historic totals, the original 16 fast lazy-separator reds, the real-model watch rules, and the two-timeout discipline. **No code, no skips/xfails, no base re-run.**

**Deliverable** (2 doc files edited, nothing else):
1. `tests/G1_BASELINE.md` — (a) a dated **"G1 CPU addendum — tests/test_daemon.py"** section: the named 20-case inventory + per-case one-liner + provenance (supplied comparison vs fresh capture, drift reported) + the set-diff rule; (b) correction of the header's exclusion note (test_daemon.py removed from the "contract-forbidden hang vectors" group; the real CUDA hang vectors stay).
2. `AGENTS.md` — the hang-vector table row `:92`: `test_daemon.py` removed from the "load real CUDA models" list; a bounded-CPU row added (~16 s hermetic; `timeout 500` inner / bash-tool ≥ 560); the 600 s CUDA rule retained for `test_feed_audio`/`test_recorder_host`/`test_cuda_check`.

**Success Definition**:
- (a) A fresh bounded hermetic run (`timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no`, bash-tool timeout ≥ 560) captures the **exact failed node IDs**; the addendum records them by NAME — counts are never identity evidence.
- (b) The fresh capture is **set-diffed** against this PRP's research baseline (20 names, listed below): expected SET IDENTITY of failure names (pass-count drift from newly landed passing tests is fine; a failure-name change is drift to investigate and report, never to paper over).
- (c) Each of the 20 carries a one-line reason/facet from live `--tb=line` output — most are the legacy lazy-separator class (`['hello world '] == ['hello world', ' ']`), but non-separator facets (e.g. `test_cfg_to_kwargs_cuda_path` `float16 == float32`) are recorded as they are, NOT blanket-labeled.
- (d) Provenance is explicit: the SUPPLIED comparison (base `2335a9e` 211P/21F; HEAD `573d78f` 217P/20F; fixed `test_status_snapshot_keys_and_cuda_values`, zero introduced) is recorded as supplied — the unisolated base is **never re-run** — and distinguished from the fresh capture with any drift noted.
- (e) The addendum's set-diff rule: a NEW failure name = investigate before trusting the change; a gone name = fixed → update the addendum (dated). Consumed by P1.M2.T1.S1, P1.M2.T2.S3, P1.M2.T3.S2.
- (f) PRESERVED in G1_BASELINE.md: the 15-suite table, historic totals, the 16 documented fast lazy-separator reds, the real-model watch rule (`test_streaming.py` 3P/4F re-run before/after), the `test_g_stranded_tail` flake note. AGENTS.md Rule 1 (two timeouts) and the real model-suite rules unchanged.
- (g) `git diff --name-only` == `{tests/G1_BASELINE.md, AGENTS.md}`. No skips/xfails added anywhere; no test/source/config edits.

> **FRESH CAPTURE (this PRP's research, 2026-11-23, post-T1.S1/S2 tree): 20 failed / 218 passed in 15.43 s, CPU-only.** The 20 canonical names + facet samples are in the research note §1 — the implementer re-captures and set-diffs against them.

## User Persona

**Target User**: the maintainer/future sweep agent deciding which suites are safe to run and what "red" means. **Use Case**: a Rev-5 sweep touches daemon code → runs `test_daemon.py` bounded (now correctly documented as CPU-only) → diffs the FAILED names against the addendum → a new name means "my change broke something", a gone name means "fixed". **Pain Points Addressed**: today the repo's own guidance says the file loads CUDA models (false — its header says NO CUDA; it runs in ~16 s), so sweeps skip it and 20 legacy reds sit unclassified; the G1 "failure inventory" is incomplete.

## Why

- **PRD h3.3 (BUG-004) is the mandate**: reclassify + fold the 20 reds into the documented classification "so future sweeps can diff against a complete inventory" (h2.5 recommendation). The audit already proved the hard part: base-vs-HEAD shows ZERO introduced failures and one fixed — this is debt, not regression.
- **Names, not counts.** The supplied rows (211P/21F → 217P/20F → fresh 218P/20F) differ in passers as tests land; only the NAMED failure set is a stable diff key. The addendum bakes that rule in so future sweeps cannot "infer identities from counts".
- **The mislabel has teeth.** AGENTS.md's hang-vector table is the repo's safety contract for agents; a false "loads real CUDA models" entry both forbids a safe 16 s CPU run and hides 20 reds. Correcting it — while KEEPING the true hang vectors and the two-timeout rule — makes the guidance truthful without relaxing discipline.
- **Lowest-risk outcome.** Pure documentation: no code, no test edits, no skips. The one operational act is a bounded hermetic test run.

## What

Run the file bounded → capture names + one-liners → set-diff vs the research baseline → write the addendum + correct the two docs.

### Success Criteria

- [ ] Fresh run: `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no` (bash-tool ≥ 560) → failure NAMES identical to the 20 in research §1 (or drift investigated + reported).
- [ ] G1_BASELINE.md gains the dated addendum: 20 named cases + one-line facet each + provenance (supplied vs fresh) + the set-diff rule.
- [ ] G1_BASELINE.md's exclusion note corrected: test_daemon.py is CPU-only; `test_feed_audio`/`test_recorder_host`/`test_cuda_check` remain contract-forbidden hang vectors; `test_systemd_unit` noted as T2.S1's scope.
- [ ] AGENTS.md:92 corrected: test_daemon.py out of the CUDA list; bounded-CPU guidance added; the 600 s CUDA rule + Rule 1 retained verbatim for the real model suites.
- [ ] Everything preserved (Success Definition f). No skips/xfails. `git diff --name-only` == the 2 files.

## All Needed Context

### Context Completeness Check

_Pass._ The 20 canonical names are already captured fresh (research §1) with facet samples; the two doc edit sites are quoted verbatim (research §3); the supplied-vs-fresh provenance table is complete; the exact commands (two-timeout discipline) are given; the parallel sibling's file set is confirmed disjoint. An agent new to this repo can execute from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the fresh capture (20 names + facets), provenance, doc sites, set-diff rule (this task's own research)
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T3S1/research/bug004_named_daemon_baseline.md
  why: "§1 THE FRESH CAPTURE — the 20 canonical node IDs verbatim + the facet samples (incl. the
        non-separator ones: cfg_to_kwargs_cuda_path float16/float32, the :4296 multi-field reseed assert —
        record facets AS THEY ARE). §2 the provenance table (supplied base/HEAD rows vs fresh; the +1 passer
        = T1 test growth). §3 the two doc sites VERBATIM (the G1 exclusion sentence; the AGENTS.md row).
        §4 the set-diff rule text. §5 scope."
  critical: "The implementer re-captures and SET-DIFFS against §1's names — identity of the failure set is
            the gate; pass-count drift is expected (T1.S3 may land more passing tests). Never infer
            identities from counts."

# THE MANDATE — BUG-004 + the recommendation
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/prd_snapshot.md
  why: "h3.3 (BUG-004): the misclassification, the CPU-only proof (header + 217P/20F ~16s), the base-vs-HEAD
        worktree comparison (one fixed, zero introduced). h2.5: 'Reclassify tests/test_daemon.py as a pure
        CPU suite in AGENTS.md and the G1 baseline, and fold its 20 legacy lazy-separator reds into the
        documented classification so future sweeps can diff against a complete inventory.'"
  critical: "The supplied comparison is HISTORY — do NOT re-run the unisolated base worktree (the contract
            forbids it; the audit already did it under controlled conditions)."

# THE DOC TO AMEND #1 — tests/G1_BASELINE.md
- file: tests/G1_BASELINE.md
  why: "The header exclusion sentence (research §3 quotes it) is the mislabel; the body carries the 15-suite
        table, the drift section, and the failure-inventory style (names + one-liners + the (i)/(ii) legend)
        the addendum mirrors. The addendum goes AFTER the existing inventory as a dated section."
  pattern: "Mirror the existing inventory's discipline: numbered names with file:line + one-line reason.
            Use the (i)-style facet labels where true but record non-separator facets honestly."
  gotcha: "PRESERVE the historic totals (380P/19F vs record 379P/20F), the 16 fast reds inventory, the
           test_streaming.py real-model watch rule (3P/4F, re-run before/after), and the test_g_stranded_tail
           flake note — the addendum ADDS, it does not rewrite."

# THE DOC TO AMEND #2 — AGENTS.md
- file: AGENTS.md
  why: "Row :92 (quoted in research §3) lists test_daemon.py among suites that 'load real CUDA models' —
        false (file header: 'NO real RealtimeSTT / NO model load / NO CUDA'; 5,409 lines; 15.4 s CPU-only).
        Edit: remove test_daemon.py from that row's list; add a separate bounded-CPU row; keep the
        `timeout 600` CUDA guidance for the remaining three suites."
  pattern: "Table format: | command | why it hangs/risks | safe form |. The new row: hermetic post-T1
            (fake ASR/mic/IM/typing/media), ~16 s, `timeout 500` inner + bash-tool ≥ 560 (Rule 1 two-timeout
            discipline applies to EVERY non-trivial command — keep it)."
  gotcha: "AGENTS.md is the repo's agent-safety contract — do NOT relax Rule 1 or the real hang-vector rows
           (voicectl, launch_daemon.sh, the shell E2E scripts). This task only corrects the one false row."

# THE PARALLEL SIBLING — disjoint files
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T2S1/PRP.md
  why: "T2.S1 (parallel, implementing) edits tests/test_systemd_unit.py ONLY (VT-003 panic-bind pin) —
        DISJOINT from tests/G1_BASELINE.md and AGENTS.md. The addendum may NOTE test_systemd_unit as T2.S1's
        scope but must not touch it."
```

### Current Codebase tree (relevant slice)

```bash
tests/test_daemon.py        # 5,409 lines; CPU-only (header); fresh 20F/218P in 15.43s. READ-ONLY here.
tests/G1_BASELINE.md        # the 15-suite record + the exclusion mislabel.                          ← EDIT (addendum + correction)
AGENTS.md                   # the hang-vector table row :92.                                      ← EDIT (bounded-CPU row)
# T1.S1/S2 landed (74252cd, 0749bdb — hermetic ctors); T1.S3 in flight (more passing tests may land: pass-count drift OK).
# Parallel T2.S1: tests/test_systemd_unit.py — DISJOINT.
```

### Desired Codebase tree with files to be changed

```bash
tests/G1_BASELINE.md   # ADD dated "G1 CPU addendum — tests/test_daemon.py" (names + facets + provenance + set-diff rule);
#                      CORRECT the header exclusion (test_daemon.py reclassified; real CUDA vectors stay).
AGENTS.md              # CORRECT row :92 (test_daemon.py → bounded-CPU row; CUDA list shrinks to the 3 real suites).
# NO other files. No skips/xfails, no test/source/config edits, no base-worktree run.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TWO TIMEOUTS ON THE TEST RUN (AGENTS.md Rule 1). Inner `timeout 500`, bash-tool timeout
# >= 560. Even though the file is CPU-only (~16 s), a regression could still wedge — the discipline is
# universal. Never run it bare.

# CRITICAL #2 — NAMES ARE THE ONLY IDENTITY. Pass counts drift as T1.S3 lands passing tests (fresh capture
# was already 218P vs the supplied 217P). The gate is SET IDENTITY of the 20 failure names vs research §1.
# A new name = investigate (do not record it as baseline without understanding); a gone name = fixed, note it.

# CRITICAL #3 — DO NOT RE-RUN THE UNISOLATED BASE. The contract forbids it; the supplied base/HEAD rows are
# history recorded as PROVENANCE. Also: no `git worktree add` for this task at all.

# CRITICAL #4 — RECORD FACETS AS THEY ARE. Most cases are the lazy-separator class (`['x '] == ['x', ' ']`),
# but at least test_cfg_to_kwargs_cuda_path is a float16/float32 compute-type drift and :4296 is a
# multi-field reseed assert. A blanket "all 20 are lazy-separator" label would be false inventory — the
# per-case one-liners come from live --tb=line output. (Classification verdicts remain the owning tasks'.)

# CRITICAL #5 — PRESERVE EVERYTHING THE ADDENDUM DOESN'T ADD. G1_BASELINE.md's historic totals, the 16
# fast reds inventory, the test_streaming.py real-model watch rule (3P/4F, re-run before/after ANY change),
# the test_g_stranded_tail flake note; AGENTS.md's Rule 1, the voicectl/daemon/shell-script hang rows, and
# the 600 s CUDA guidance for the three REAL model suites. The edits are additive/corrective, not rewrites.

# GOTCHA #6 — HERMETICITY IS THE PRECONDITION. The run is only safe because T1.S1/S2 landed (fake duck
# wiring — no real busctl against the live desktop). If the fresh run shows symptoms of live-desktop
# interaction (busctl children, media pauses), STOP: T1 regression — report, do not record that run.

# GOTCHA #7 — FULL PATHS + pytest only (no ruff/mypy configured). .venv/bin/python -m pytest. Never bare.
```

## Implementation Blueprint

### Data models and structure

None — documentation only. The "data" is the named inventory (a numbered list mirroring G1_BASELINE.md's existing failure-inventory style) plus the provenance table and the set-diff rule.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm hermeticity landed + tree state (no mutation)
  - RUN:
      cd /home/dustin/projects/voice-typing
      git log --oneline -4                     # expect 0749bdb (T1.S2) + 74252cd (T1.S1) present
      grep -c '_FakeDucker\|duck_mode' tests/test_daemon.py   # >0 — the hermetic wiring exists
      git status --short                       # note in-flight files (T1.S3 / T2.S1 may be editing others)
  - EXPECTED: T1.S1/S2 commits present. If the hermetic wiring is ABSENT, STOP — the run would touch the
    live desktop (Gotcha #6); report instead.

Task 2: FRESH CAPTURE — the named failure list + one-line facets (two timeouts)
  - RUN:
      cd /home/dustin/projects/voice-typing
      timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -25
      # (bash-tool timeout >= 560 on this call)
      timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=line 2>&1 | grep -E '^/home.*AssertionError' | head -25
  - EXPECTED: ~"20 failed, 218 passed in ~16s" (pass-count drift OK — Gotcha #2); the FAILED names.
  - SET-DIFF vs research §1's 20 names:
      - IDENTICAL → proceed (record the fresh list).
      - DRIFT (new/gone names) → investigate + REPORT in the addendum's drift note; never silently rebaseline.

Task 3: EDIT tests/G1_BASELINE.md — the dated addendum + the exclusion correction
  - (3a) CORRECT the header sentence (research §3 quotes it verbatim): remove test_daemon.py from the
    "contract-forbidden hang vectors" parenthetical; state it is CPU-only (~16 s, two-timeout discipline
    applies) and covered by the addendum below; test_systemd_unit noted as T2.S1's scope; the REAL vectors
    (test_feed_audio/test_recorder_host/test_cuda_check) stay forbidden.
  - (3b) APPEND the addendum at the END, mirroring the existing inventory style:
      ## G1 CPU addendum — tests/test_daemon.py (recorded <date>, code state <git rev-parse --short HEAD>)
      - Reclassification note (BUG-004): CPU-only, hermetic post-T1, ~16 s; 20 legacy reds, never in the
        G1 inventory because of the mislabel.
      - Provenance table (research §2 verbatim): supplied base 2335a9e 211P/21F; supplied HEAD 573d78f
        217P/20F (fixed test_status_snapshot_keys_and_cuda_values, zero introduced — base NOT re-run,
        contract-forbidden); FRESH <date> <rev> <P>/<F> (+drift note if any).
      - The named 20-case inventory: numbered node IDs + file:line + one-line facet from --tb=line
        (research §1 is the pre-filled draft; mark the separator-class ones, record the non-separator
        facets as they are — Gotcha #4).
      - FUTURE SET-DIFF RULE (research §4 text): diff FAILED names vs this list on every sweep touching
        daemon code; new name = investigate before trusting the change; gone name = fixed, update here
        (dated). Counts are never evidence. Consumers: P1.M2.T1.S1, P1.M2.T2.S3, P1.M2.T3.S2.
  - PRESERVE (Gotcha #5): the 15-suite table, historic totals, the 16-red inventory, the streaming
    real-model watch rule, the stranded-tail flake note.

Task 4: EDIT AGENTS.md — correct the hang-vector row
  - Row :92 (research §3 verbatim): remove test_daemon.py from the CUDA-model list → the row covers
    test_feed_audio.py/test_recorder_host.py/test_cuda_check.py only (600 s rule unchanged).
  - ADD a bounded-CPU row for tests/test_daemon.py: hermetic (fake ASR/mic/IM/typing/media, post-T1),
    ~16 s, 20 legacy reds classified in tests/G1_BASELINE.md's CPU addendum; safe form
    `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no` with the bash-tool timeout
    >= 560 (Rule 1 applies to everything).
  - DO NOT touch any other row or Rule 1/2/3 text.

Task 5: VALIDATE (L1–L4). If committing: "P1.M1.T3.S1: BUG-004 — G1 CPU addendum (named 20-case daemon
  baseline + set-diff rule); AGENTS.md hang-vector row corrected".
```

### Implementation Patterns & Key Details

```bash
# THE CAPTURE (two timeouts — Rule 1):
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no   # names + counts
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=line # per-case one-liners
# THE GATE: SET IDENTITY of failure names vs the research §1 list. Counts drift; names don't (unless real drift).

# THE SET-DIFF RULE (the addendum's operative sentence):
# "Diff the FAILED-name set against this inventory on every sweep touching daemon code: a NEW name is a
#  new failure — investigate before trusting the change; a GONE name is a fix — update this addendum
#  (dated). Pass counts are never identity evidence."
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS (the contract's OUTPUT):
  - P1.M2.T1.S1 / P1.M2.T2.S3 / P1.M2.T3.S2: every sweep that touches daemon code runs the file bounded
    and applies the set-diff rule — the addendum is their pre/post key.
PARALLEL — P1.M1.T2.S1 (implementing): edits tests/test_systemd_unit.py ONLY — DISJOINT. The addendum
  may note test_systemd_unit as T2.S1's scope; do not edit it.
UPSTREAM — P1.M1.T1.S1/S2 (landed) + T1.S3 (in flight): the hermeticity that makes the bounded CPU run
  safe. Pass-count drift from T1.S3 landing passing tests is expected (Gotcha #2).
UNCHANGED: all 30+ suites' code, the real model suites' rules, AGENTS.md's other rows, the G1 15-suite
  record's content. Zero code/test/config changes; no skips/xfails anywhere.
```

## Validation Loop

### Level 1: The docs are edited correctly

```bash
cd /home/dustin/projects/voice-typing
grep -n 'G1 CPU addendum' tests/G1_BASELINE.md                       # present, dated
grep -c 'test_daemon.py::' tests/G1_BASELINE.md                      # >= 20 (the named inventory)
grep -n 'test_daemon' tests/G1_BASELINE.md | head -3                 # exclusion corrected (CPU-only framing)
grep -n 'test_daemon' AGENTS.md                                      # the bounded-CPU row; NOT in the CUDA list row
grep -n 'timeout 600' AGENTS.md                                      # the CUDA rule RETAINED for the 3 real suites
```

### Level 2: The addendum's names match a fresh run (set identity)

```bash
cd /home/dustin/projects/voice-typing
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | grep '^FAILED' | sed 's/FAILED //;s/ - .*//' | sort > /tmp/fresh_names.txt
# diff against the addendum's recorded names (extract or retype) — expect IDENTICAL sets.
# (bash-tool timeout >= 560; /tmp scratch removed after.)
```

### Level 3: Everything preserved

```bash
cd /home/dustin/projects/voice-typing
grep -n '16 fast\|test_g_stranded_tail\|3P/4F\|380' tests/G1_BASELINE.md | head -5   # historic content intact
grep -n 'timeout 30 .venv/bin/voicectl\|Never foreground\|Rule 1' AGENTS.md | head -3 # safety contract intact
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only    # == tests/G1_BASELINE.md + AGENTS.md
git diff --exit-code -- voice_typing/ tests/test_daemon.py tests/test_systemd_unit.py config.toml && echo "L4 PASS: zero code/test changes" || echo "L4 FAIL"
grep -rn 'xfail\|pytest.mark.skip' tests/test_daemon.py | wc -l    # 0 — no skips/xfails introduced
rm -f /tmp/fresh_names.txt
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 addendum present + dated; ≥20 named cases; exclusion corrected; AGENTS.md row corrected with the CUDA rule retained.
- [ ] L2 fresh-run FAILED-name set IDENTICAL to the addendum (Task 2's set-diff held).
- [ ] L3 historic totals / 16-red inventory / streaming watch rule / flake note / AGENTS safety rows intact.
- [ ] L4 exactly the 2 doc files changed; zero skips/xfails; /tmp scratch removed.

### Feature Validation
- [ ] The named 20-case inventory carries per-case one-line facets (separator-class marked; non-separator facets recorded as they are).
- [ ] Provenance distinguishes the supplied comparison from the fresh capture, with drift (if any) reported.
- [ ] The set-diff rule is stated operatively and names its consumers (P1.M2.T1.S1 / T2.S3 / T3.S2).

### Code Quality / Scope Validation
- [ ] No base-worktree run; no E2E/live service; the capture was bounded + hermetic (two timeouts).
- [ ] Additive edits only; the existing G1 record's content preserved byte-for-byte outside the corrected sentence.

### Documentation & Deployment
- [ ] Mode A: the docs ARE the deliverable (tests/G1_BASELINE.md + AGENTS.md); no README change needed.

---

## Anti-Patterns to Avoid

- ❌ Don't run the test without BOTH timeouts, and don't run it if the hermetic wiring is absent (T1 regression → report, don't record). (Gotchas #1/#6.)
- ❌ Don't infer identities from counts — the gate is failure-NAME set identity; pass-count drift is expected. (Gotcha #2.)
- ❌ Don't re-run the unisolated base (no worktree at all this task) — the supplied rows are recorded provenance. (Gotcha #3.)
- ❌ Don't blanket-label all 20 "lazy-separator" — record each case's actual `--tb=line` facet (float16/float32 and the reseed assert are NOT separator facets). (Gotcha #4.)
- ❌ Don't rewrite or delete any preserved content (historic totals, 16-red inventory, streaming watch rule, flake note, AGENTS safety rows/Rule 1). (Gotcha #5.)
- ❌ Don't add skips/xfails "to clean up" the 20 reds — classification debt is recorded, not silenced.
- ❌ Don't touch tests/test_systemd_unit.py (parallel T2.S1) or any code/test/config file.
- ❌ Don't use bare python/pytest/uv; don't invent ruff/mypy gates.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The hard evidence is already captured: this PRP's research contains the fresh 20-name list (a 15.43 s CPU run at the current tree), facet samples, the verbatim text of both doc sites to correct, and the provenance table — the implementer re-captures, set-diffs (expected identical), and transcribes. The two operational risks are pre-guarded: running without the hermeticity precondition (Gotcha #6 stops it) and count-vs-identity confusion (Gotcha #2 + the L2 set-diff gate). The −0.5 is T1.S3 landing mid-task causing pass-count drift that a careless implementer might misread as baseline drift — the PRP's explicit drift rule handles it. No CUDA, no E2E, no live service; the only run is bounded and hermetic.

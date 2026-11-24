# PRP — P1.M2.T3.S2: Sync README.md overview to the landed fixes and limits

## Goal

**Feature Goal**: Make `README.md` read consistently with the landed bugfix-round state — the
documented SUPER+ALT+Escape panic bind (an explicit systemd stop bypassing the socket, NOT an
instant SIGKILL), the refreshed G5 timing verdict (2026-11-24 qualification: both routes still
FAIL, with the improved-but-failing numbers and the proxy/paint distinction), and S1's refreshed
G6 decision (STAY OPT-IN) — plus a short hermetic-tests/CPU note — **without promoting the
experimental bulk mode** and without touching any evidence file, spec, or default.

**Deliverable** (ONE file edited): `README.md` — 3 content edits + 1 audit pass:
1. **Hotkey** section: add the third bind + a precise panic-bind paragraph.
2. **Bulk text delivery** section: refresh the G6 cite (quote S1's current decision/date),
   mirror S1's outstanding inputs, and replace the stale timing paragraph (12.6 s → the
   2026-11-24 numbers) with the editor-state-proxy / two-route-scope / no-operator-acceptance
   distinctions.
3. **NEW short "Running the tests" section** (end of file): hermetic suite + CPU-only
   test_daemon.py + G1-baseline set-diff pointer.
4. **Audit** Media ducking + surrounding wording for contradictions (none expected).

**Success Definition**:
- (a) README documents SUPER+ALT+Escape exactly as the item requires: "an explicit systemd stop
      bypassing the socket, not an instant SIGKILL" (SIGTERM → bounded teardown → SIGKILL only at
      the TimeoutStopSec=15 outer net; restart via `systemctl --user start`).
- (b) README's bind block matches hypr-binds.conf's three binds exactly.
- (c) README's G6 decision line is string-identical to S1's refreshed current block (same date/@HEAD
      cite; STAY OPT-IN); the timing paragraph carries only numbers present in
      `tests/G5_TIMING_EVIDENCE.md` (6714.0 ms median, 11.3/13.2 s paint-qualified frame bars,
      4/0 and 14/14 counts, 57-word backlog) and explicitly distinguishes editor-state proxy
      (im-gtk), G5 two-route coverage, and operator acceptance (unmet, 0 sessions) — without
      generalizing to the G3 matrix.
- (d) `audio.duck_mode = "mpris"` stays documented as the production default; `output.delivery`
      stays `"stream-edit"`; the Bulk header still says "opt-in, experimental"; zero promotion
      language anywhere.
- (e) Validation is static-inspection-only (item LOGIC): grep/diff checks + one pure
      CPU pytest file; **no live services, no daemon, no voicectl**; `git status --short` ==
      `README.md` only.

## User Persona

**Target User**: "dustin, six months from now, and anyone who clones the repo" (README's own
declared reader). **Use Case**: (1) the socket is wedged mid-dictation — the reader presses
Super+Alt+Escape and wants to know exactly what that does (a graceful systemd stop, and how to
bring the daemon back); (2) the reader evaluates `output.delivery = "bulk-text"` and needs the
honest current state (what was remediated, what still fails, what the numbers do and do NOT
cover); (3) the reader runs the test suite and needs to know it is safe (hermetic) and how to
interpret test_daemon.py's baselined reds. **Pain Points**: a README whose panic bind is
undocumented, whose timing claims cite a superseded G5 round (12.6 s, pre-remediation), and
which says nothing about whether running the tests will pause their music.

## Why

- **The panic bind is shipped but undocumented in README** (research F1/F3): hypr-binds.conf:60
  carries it and P1.M1.T2.S1 pinned its test exemption, but the README Hotkey section shows only
  two binds. Worse, the conf's own comment overstates it as "hard-kill … SIGTERMs/SIGKILLs" —
  the item's LOGIC explicitly requires the README to be precise: it is a `systemctl --user stop`,
  i.e. the same bounded graceful teardown the README already documents, invoked out-of-band.
- **The Bulk timing text is stale** (research F4): it cites the superseded 2026-11-23 round
  (12.6 s median) — P1.M2.T2.S3's 2026-11-24 qualification re-measured both routes after the
  remediation (pi median 6.7 s; paint-qualified frame bars now FAIL honestly; im-gtk still
  proxy-based). The README also currently lacks the required distinctions (editor-state proxy vs
  paint; exactly-two-routes vs the G3 matrix; lab evidence vs operator acceptance) that stop a
  reader from over-generalizing the numbers.
- **G6 is being re-derived in parallel** (S1's contract): its refreshed current block is the
  README's single source of truth for the decision line and outstanding inputs — the README must
  quote it, not paraphrase history.
- **The test story changed and is worth 5 lines** (research F6/F7): the suite is now hermetic
  (BUG-001 fixed via `tests/conftest.py`) and test_daemon.py is reclassified CPU-only with a
  named 20-red baseline — exactly the "changed test isolation/CPU pointers" the item says to
  clarify "only where useful". A README that documents evidence files but not test-running
  discipline leaves the clone-er to rediscover both.
- **Anti-overclaim is the PRD's law**: G5's own file says "G6/README claims must not proceed on
  this evidence (P1.M2.T3 owns them)" — this task is that owner, and its job is alignment, not
  promotion (OUTPUT requirement).

## What

A documentation-only edit of README.md guided by the research note's edit map (§1): the Hotkey
addition (bind line + precise paragraph), the Bulk refresh (G6 cite, outstanding inputs, timing
paragraph + scope distinctions), the new short tests section, and a contradiction audit of the
Media-ducking section. Every factual string is traceable to a named artifact (hypr-binds.conf,
G5_TIMING_EVIDENCE.md, S1's G6_GRADUATION.md, tests/conftest.py, G1_BASELINE.md, config.py) and
validated by static string comparison — no live runs.

### Success Criteria

- [ ] Hotkey section shows all three binds; the panic paragraph uses the item's exact framing
      (explicit systemd stop bypassing the socket; not an instant SIGKILL; bounded teardown;
      SIGKILL only at the 15 s outer net; restart with `systemctl --user start voice-typing`).
- [ ] Bulk G6 cite quotes S1's current decision line verbatim (same date/@HEAD); outstanding
      inputs mirror S1's refreshed doc; timing paragraph cites only numbers present in the G5
      file and names the 2026-11-24 qualification round + the remediation that improved pi
      (update-granular dispatch + 0.05 s cadence).
- [ ] The proxy/paint distinction, the exactly-two-routes scope (NOT the G3 matrix), and the
      operator-acceptance separation each appear explicitly in the Bulk section.
- [ ] "Running the tests" section exists (≤ ~8 lines): hermetic (conftest fixture names), CPU-only
      test_daemon.py (~16 s) + the G1 CPU addendum set-diff rule, one-file-per-call under timeout.
- [ ] Media ducking audit performed and recorded (expected outcome: no change needed).
- [ ] Static validation battery (research §3) passes; `git status --short` == README.md only.

## All Needed Context

### Context Completeness Check

_Pass._ The research note carries: the 11 verified facts with file:line (the three binds + the
conf's overstated comment; the landed test exemption; the full refreshed G5 numbers; S1's
contract semantics; the hermetic conftest; the G1 CPU addendum; link-target existence; the
ducking-section consistency finding; the stabilized-callback non-change; the README section
map), the 4-edit map with target anchors and the required wording shapes, the must-not-change
list, and the exact static-validation battery. A fresh implementer needs only the note + README.

### Documentation & References

```yaml
# MUST READ — the edit map + verified facts + static validation battery.
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T3S2/research/readme_sync_research.md
  why: "§0 F1-F11 verified facts. §1 the 4-edit map (Hotkey / Bulk / tests section / ducking
        audit) with anchors and required wording shapes. §2 must-not-change list. §3 the static
        validation commands (bind diff, G6 string-equality, per-number G5 grep, link existence,
        no-promotion grep)."
  section: "ALL load-bearing."

# MUST READ — the PARALLEL CONTRACT (S1): produces the G6 current block this task quotes.
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T3S1/PRP.md
  why: "S1 refreshes tests/G6_GRADUATION.md: new current assessment (STAY OPT-IN; C re-derived
        from the 2026-11-24 G5; A/B/D unchanged), 2026-11-23 block archived verbatim, and a
        recorded decision+reason 'for P1.M2.T3.S2's README use'. Its DO-NOT-TOUCH names README
        as S2's. PRECONDITION for quoting: S1's refresh must be on disk."
  critical: "If G6_GRADUATION.md still shows only the 2026-11-23 @ 69952ae current block at impl
             time (no newer 'Assessed' date), S1 hasn't landed — wait/report; do NOT quote the
             stale block as current and do NOT author G6 content yourself."

# MUST READ — the authoritative timing evidence (the numbers README may cite).
- file: tests/G5_TIMING_EVIDENCE.md
  why: "The 2026-11-24 verdict table + qualification narrative (both routes FAIL; pi 6714.0 ms
        median, paint-qualified frame bars 11266.2/13150.8 ms; im-gtk 4/0 counts, change-log
        proxy, frame bars UNVERIFIED; 57-word backlog both; BUG-002/#13 OPEN; 'G6/README claims
        must not proceed on this evidence'). READ-ONLY — never edit."
  critical: "Every number in README's timing paragraph must grep-match this file (validation #3)."

# MUST READ — the file being edited.
- file: README.md
  why: "Section map (research F11): Hotkey @82 (bind block @103-104), ducking @204-249, Bulk
        @251 (G6 date cite @257; timing paragraph ~@295-299 '12.6 s' stale), Feedback @324,
        Configuration @343, Logs @537, Model lifecycle @591 (its teardown wording @626-637 is
        what the panic paragraph links to), file ends ~@638 (new tests section goes after)."

# MUST READ — the source of the bind truth + the landed exemption.
- file: hypr-binds.conf
  why: "The three bind lines (README's block must match them exactly). Its panic comment
        ('hard-kill … SIGTERMs/SIGKILLs') is the OVERSTATEMENT the README paragraph corrects —
        do NOT edit the conf (README-only, Mode B)."
- file: tests/test_systemd_unit.py   # :330-336 _PANIC_BIND tuple — the landed exemption (F2)

# MUST READ — the test-story sources for the new section.
- file: tests/conftest.py
  why: "`hermetic_daemon_media` fixture + `hermetic_cfg()` builder (F6) — the names to cite."
- file: tests/G1_BASELINE.md
  why: "The CPU addendum (F7): test_daemon.py CPU-only ~16 s, named 20-case baseline + set-diff
        rule — cite it, don't restate the 20 names."

# CONTEXT — the bug-hunt findings this round fixed (framing for honest wording).
- docfile: PRD.md  # bugfix h2.2/h2.3/h2.5 (BUG-001..004 + recommendations)
  why: "BUG-001 (hermetic), BUG-002 (bulk visibility; remediated, still failing), BUG-003 (panic
        bind), BUG-004 (CPU classification) — the four inputs this README sync reflects."

# CONTEXT — the gate law (what README may/may not claim about bulk).
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  section: "## Gate and evidence handoff"
  critical: "README must not imply operator acceptance, broaden G3, or graduate on timing."
```

### Current Codebase tree (relevant slice)

```bash
README.md                      # EDIT (the only file this task touches)
hypr-binds.conf                # READ: the three binds (README block must match)
tests/
├── G5_TIMING_EVIDENCE.md      # READ-ONLY: the 2026-11-24 numbers (citation source)
├── G6_GRADUATION.md           # READ-ONLY (S1's refresh — the decision source)
├── conftest.py                # READ: hermetic fixture names to cite
└── G1_BASELINE.md             # READ: the CPU addendum to cite
tests/test_systemd_unit.py     # READ: _PANIC_BIND exemption (:330-336)
voice_typing/config.py         # READ: defaults sanity (mpris / 15 / stream-edit)
```

### Desired Codebase tree (what changes)

```bash
README.md   # 3 content edits + 1 audit (no new files; ~+30/-12 lines)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — S1 PRECONDITION: before quoting, confirm tests/G6_GRADUATION.md carries a
#   CURRENT block newer than 2026-11-23 @ 69952ae (grep "Assessed"). If not, S1 hasn't landed —
#   report/wait; never quote the stale block as current, never author G6 content in README.
# CRITICAL #2 — NUMBERS ARE GREP-TRACEABLE: every timing figure in the README must appear
#   verbatim in tests/G5_TIMING_EVIDENCE.md (6714.0, 11266.2, 13150.8, 57, 12.6-as-history).
#   No rounding into new claims ("~7 s" as prose context is fine ONLY alongside the exact figure).
# CRITICAL #3 — DO NOT GENERALIZE (item LOGIC): timing claims scope to the TWO G5 lab routes;
#   im-gtk frame bars = editor-state/change-log proxy (UNVERIFIED), pi = paint-qualified;
#   operator acceptance is a separate unmet G6 condition. Never fold these into the G3 matrix.
# CRITICAL #4 — DO NOT PROMOTE: bulk stays "opt-in, experimental"; delivery default stays
#   "stream-edit"; no "graduated"/"verified"/"operator-accepted" language outside quoted G6 text.
# CRITICAL #5 — PANIC WORDING (item LOGIC, verbatim requirement): "an explicit systemd stop
#   bypassing the socket, not an instant SIGKILL" — SIGTERM → bounded single-flight teardown
#   (the README's own Model-lifecycle wording) → SIGKILL only at TimeoutStopSec=15; restart via
#   systemctl --user start. Do NOT copy hypr-binds.conf's "hard-kill" framing.
# CRITICAL #6 — READ-ONLY EVIDENCE: G5/G6/conftest/G1_BASELINE/hypr-binds.conf/test files are
#   citation sources — never edited (S3/S1/M1 own them). README.md is the ONLY file touched.
# CRITICAL #7 — STATIC VALIDATION ONLY (item LOGIC): grep/diff + at most the pure CPU
#   tests/test_config.py under GNU timeout. NO daemon start, NO voicectl, NO live services.
# CRITICAL #8 — Full paths (.venv/bin/python; zsh aliases python3/pytest); every command under
#   GNU timeout per AGENTS.md (two-timeout discipline even for "just greps" is not needed, but
#   any pytest invocation gets timeout 300 + the bash-tool backstop).
# GOTCHA #9 — duck_mode stays "mpris" in README (item: keep the production default); the
#   ducking section needs NO rewrite (F9) — resist scope creep beyond a contradiction fix.
```

## Implementation Blueprint

### Data models and structure

None (documentation; the "model" is the research note's edit map).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PRECONDITION — S1's G6 refresh on disk?
  - grep -n "Assessed" tests/G6_GRADUATION.md | head -3   # a date NEWER than 2026-11-23 must lead
  - Capture S1's current decision line + date/@HEAD + Outstanding inputs (quote sources).
  - If stale-only → STOP and report (CRITICAL #1).

Task 2: EDIT README Hotkey section (@82-115)
  - ADD the third bind line to the code block (exact hypr-binds.conf text).
  - ADD the panic paragraph per CRITICAL #5 (research §1 Edit 1 wording shape): what it runs,
    why it exists (wedged socket), what it is NOT (instant SIGKILL), the bounded-teardown link,
    the 15 s outer net, the restart command, and (one clause) that the portability test exempts
    exactly this documented bind.

Task 3: EDIT README Bulk section (@251-306)
  - REPLACE the G6 cite (@255-258): quote S1's current decision line verbatim + its date/@HEAD.
  - MIRROR S1's refreshed Outstanding inputs in the outstanding-inputs sentence (no invention).
  - REPLACE the timing paragraph (@295-299) with the 2026-11-24 qualification (research §1
    Edit 2): both routes FAIL; remediation landed (update-granular dispatch, prompt partial
    dispatch, 0.05 s bulk cadence) improved pi 12.6 s → 6.7 s median yet ~13× the 500 ms bar;
    sentence-end dump persists; pi paint-qualified frame bars FAIL 11.3/13.2 s p95; im-gtk 4/0
    counts + 57-word backlog + change-log-proxy frame bars UNVERIFIED; then the scope paragraph
    (CRITICAL #3: two lab routes only, proxy vs paint, NOT the G3 matrix, NOT operator
    acceptance — G6 condition D, 0 sessions); close with BUG-002/#13 open + opt-in retained.

Task 4: APPEND README "## Running the tests" (after Model lifecycle, ~@638)
  - ≤ ~8 lines: hermetic suite (conftest `hermetic_daemon_media` / `hermetic_cfg`; pytest never
    touches the live session bus or pauses media; subprocess recorders order-independent);
    test_daemon.py CPU-only ~16 s with the named 20-red G1 CPU addendum + set-diff rule; run one
    file per call under GNU timeout.

Task 5: AUDIT Media ducking (@204-249) + First-run/Feedback wording
  - Re-read against the landed state (F9: expected NO change). Record the audit result in
    research/ (even "no contradiction found"). Fix minimally ONLY a genuine contradiction.

Task 6: VALIDATE — research §3 battery, all static:
  bind-block diff vs hypr-binds.conf; G6 decision string-equality vs S1's current block; every
  timing number greps in G5; link targets exist; config defaults match config.py; no-promotion
  grep; optional timeout 300 .venv/bin/python -m pytest tests/test_config.py -q;
  git status --short == README.md only.
```

### Implementation Patterns & Key Details

```markdown
<!-- Panic paragraph shape (Task 2; adapt prose, keep every fact): -->
**Super+Alt+Escape is the panic bind**: it runs `systemctl --user stop voice-typing` — an
explicit systemd stop that bypasses voicectl and the control socket entirely, so it works even
when the socket is wedged. It is not an instant SIGKILL: systemd SIGTERMs the main process and
the daemon's bounded single-flight teardown (below) completes in seconds; SIGKILL fires only at
the unit's outer `TimeoutStopSec=15` net. A stop is intentional (`Restart=on-failure` does not
restart it), so bring the daemon back with `systemctl --user start voice-typing`.

<!-- Bulk scope paragraph shape (Task 3; the CRITICAL #3 distinctions, verbatim-required ideas): -->
These timings come from the isolated G5 lab on exactly two routes (im-gtk, pi-ghostty). The
im-gtk frame bars are an editor-state (field change-log) proxy — unverified; the pi bars are
paint-qualified (real visible change). They are not claims about the field-class matrix above,
and none of this is operator acceptance — that is G6 condition D, with 0 writing sessions on
record.
```

### Integration Points

```yaml
CONSUMED (read-only): S1's tests/G6_GRADUATION.md current block (decision + date + outstanding);
  tests/G5_TIMING_EVIDENCE.md (2026-11-24 numbers); hypr-binds.conf (bind truth);
  tests/conftest.py + tests/G1_BASELINE.md (test-story facts); voice_typing/config.py (defaults).
PRODUCED: README.md synced (panic bind, bulk status/timings/scopes, tests note, audit record).
DOWNSTREAM: none in this round (the changeset's final user-facing doc surface; P1 closes here).
DO NOT TOUCH: everything except README.md — especially tests/G5_TIMING_EVIDENCE.md,
  tests/G6_GRADUATION.md, hypr-binds.conf, tests/*, voice_typing/*, config.toml, PRD.md,
  tasks.json, prd_snapshot.md, .gitignore.
```

## Validation Loop

### Level 1: Static content checks (the gate — item LOGIC mandates static-only)

```bash
cd /home/dustin/projects/voice-typing
# (1) Bind block == hypr-binds.conf (3 binds, exact):
diff <(grep '^bind = ' hypr-binds.conf) \
     <(awk '/^```$/{f=!f;next} f && /^bind = /' README.md | grep '^bind = ') && echo BINDS-MATCH
# (2) G6 decision line string-identical to S1's current block:
grep -o "G6 DECISION: STAY OPT-IN ([^)]*)" README.md tests/G6_GRADUATION.md
# (3) Every cited number exists in G5:
for n in 6714.0 11266.2 13150.8; do grep -q "$n" tests/G5_TIMING_EVIDENCE.md && echo "$n ok"; done
# (4) Required distinctions present:
grep -cE 'proxy|paint' README.md          # proxy-vs-paint language in the Bulk section
grep -nE 'not .*operator acceptance|0 (writing )?sessions|two routes' README.md
# (5) Panic wording per the item:
grep -nE 'systemctl --user stop voice-typing|not an instant SIGKILL|TimeoutStopSec=15' README.md
```

### Level 2: No-promotion + no-staleness checks

```bash
sed -n '/^## Bulk text delivery/,+3p' README.md      # header still "opt-in, experimental"
grep -niE 'graduat|operator-accepted' README.md      # only inside quoted-G6/historical context
grep -n '69952ae\|12\.6 s' README.md                 # only as explicitly-labeled history, or gone
grep -n 'duck_mode = "mpris"\|"stream-edit"' README.md   # defaults unchanged
# Links resolve:
ls plan/008_a47116bb2b79/architecture/g3_field_matrix.md plan/008_a47116bb2b79/architecture/g4_clipboard_verdicts.jsonl tests/D1_DUCK_EVIDENCE.md tests/G6_WRITING_SESSIONS.md
```

### Level 3: Pure sanity (no service touched)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_config.py -q   # config untouched (defaults pinned)
git status --short                                               # → README.md ONLY
```

### Level 4: Creative & Domain-Specific

Not applicable — static documentation sync; NO desktop, daemon, voicectl, or live service may be
exercised (item LOGIC: "mock/no live services or CLI").

## Final Validation Checklist

### Technical Validation
- [ ] Level 1 static battery passes (binds match; G6 string-equality; numbers grep; distinctions
      present; panic wording present).
- [ ] Level 2: no promotion language; stale 69952ae/12.6 s cites gone or explicitly historical;
      defaults unchanged; links resolve.
- [ ] Level 3: test_config green; `git status --short` == README.md only.

### Feature Validation
- [ ] Panic bind documented as explicit systemd stop bypassing the socket, not instant SIGKILL.
- [ ] Bulk overview aligned with the 2026-11-24 G5 + S1's G6 (STAY OPT-IN) without promotion.
- [ ] Editor-state proxy vs paint, two-route scope vs G3 matrix, and operator acceptance each
      explicitly distinguished.
- [ ] Tests note covers hermeticity + CPU-only test_daemon.py + the G1 set-diff pointer.
- [ ] Media ducking audited (result recorded; expected no-change).

### Code Quality / Scope
- [ ] README-only diff; no evidence/spec/config/source file touched.
- [ ] Wording matches README's established voice (exact commands, no hand-holding).
- [ ] No new claims beyond the cited artifacts; every number traceable.

---

## Anti-Patterns to Avoid

- ❌ Don't promote bulk-text or soften "opt-in, experimental" — G6 says STAY OPT-IN; the item's
  OUTPUT forbids promoting the experimental mode.
- ❌ Don't generalize the G5 numbers to the G3 field matrix or call them operator-accepted.
- ❌ Don't quote the stale 2026-11-23 @ 69952ae G6 block as current (CRITICAL #1) or author G6
  content inside README.
- ❌ Don't copy hypr-binds.conf's "hard-kill … SIGKILLs" framing — the item mandates the precise
  systemd-stop wording (CRITICAL #5).
- ❌ Don't rewrite the ducking section (F9: consistent) or touch any evidence file.
- ❌ Don't run the daemon, voicectl, or any live service to "check" wording — static only.
- ❌ Don't use bare python/pytest (zsh aliases); full paths under GNU timeout.
- ❌ Don't edit hypr-binds.conf's comment to "fix" its wording — README-only scope (Mode B).

---

## Confidence Score

**9/10**. Every fact the README must state is verified against the live tree (binds, exemption,
refreshed G5 numbers, conftest/G1 facts, link targets, defaults), the parallel S1 contract
defines exactly what to quote and how to detect it landed, and validation is a deterministic
static battery. Residual risk (−1): S1's refreshed G6 block must be on disk before quoting
(hard precondition, checked first); if its wording of Outstanding inputs differs from the
anticipated shape, the implementer mirrors it rather than the research note's paraphrase.

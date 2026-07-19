# PRP — P1.M6.T1.S2: Verify no stale BUGS.md/VT-* references & resolve doc drift

## Goal

**Feature Goal**: **Audit** every `BUGS.md` and `VT-00N` reference in the shipped tree
(`voice_typing/`, `tests/`, `README.md`, `config.toml`, `install.sh`, `systemd/`, `hypr-binds.conf`)
against the LIVE code, classify each hit as **RESOLVED-in-code (comment/doc)** or **unresolved bug**,
explicitly resolve the **VT-001** headline ("voicectl status importing CUDA in the daemon process" — PRD
§4.2bis), and write the findings dossier. The PRD (read-only) references a **BUGS.md that does not
exist**; this audit determines whether any *shipped* artifact still carries a stale/dangling reference
or an unresolved VT-* bug, and routes the genuinely-stale items (all inside the read-only PRD) to a
human. **Pre-verified verdict (research `stale_refs_audit_findings.md`): BUGS.md is absent; ALL VT-001
through VT-008 references in source/tests/docs are explanatory comments documenting RESOLVED,
test-pinned fixes; there are ZERO unresolved VT-* bugs; README is clean of stale refs.** The deliverable
is therefore **`gap_stale_refs.md`** (a pure REPORT task — no shipped-tree edit, like the `gap_*.md`
audits).

**Deliverable** (1 artifact — 1 CREATE; **NO** edit to README/source/config/PRD/tasks/anything):
1. **CREATE** `plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md` — the self-contained stale-reference
   audit dossier. Structure: (1) verdict line; (2) the BUGS.md finding (absent; dangling PRD ref only);
   (3) the VT-001..VT-008 classification matrix (each: meaning → resolution site → pinning test →
   RESOLVED); (4) the VT-001 headline resolution (status never probes CUDA; VT-008 regression guard);
   (5) changeset-doc cleanliness (README + comments are CORRECT, not stale — do NOT "clean up" VT-*
   comments); (6) the read-only PRD drift register (3 items, routed to a human PRD edit); (7)
   remediation verdict (NONE required; routed recommendation only); (8) scope (README → S1, commit → S3).

**Success Definition**:
- (a) The contract's grep re-run LIVE over the exact input set
  (`grep -rn 'BUGS\.md\|VT-00[0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/
  hypr-binds.conf`); every hit classified RESOLVED vs UNRESOLVED with the resolution file:line + the
  pinning test:line.
- (b) **VT-001 explicitly resolved**: gap_stale_refs.md cites `daemon.py:566` (the un-probed
  `_resolved_device_cache` seed), `daemon.py:1585` (docstring), `test_daemon.py:1621` (status never
  calls cuda_check), and the **VT-008** guard `test_daemon.py:1745` — proving the "status imports CUDA"
  violation NO LONGER EXISTS. The PRD §4.2bis caveat is recorded as STALE (read-only).
- (c) **BUGS.md confirmed absent** (`find . -name BUGS.md` → none); the ONLY BUGS.md reference is
  `PRD.md:144` (read-only, dangling); ZERO references in any shipped file.
- (d) **No unresolved VT-* bug found** → NO remediation task created in the shipped tree (editing the
  resolved code/tests would REINTRODUCE the bugs). The sole routed item is the read-only PRD drift
  (3 entries) flagged for a human PRD edit.
- (e) `gap_stale_refs.md` written with the 8-section structure + an unambiguous verdict line.
- (f) Scope respected: ONLY stale-reference hygiene. README-COMPLETENESS → **P1.M6.T1.S1** (parallel);
  commit readiness → **P1.M6.T1.S3**. NO edit to README.md (to avoid a writer conflict with the parallel
  S1), NO edit to PRD.md/tasks.json/prd_snapshot.md/.gitignore, NO source/test/script/config edit, NO
  pytest, NO heavy shell script (AGENTS.md).

## User Persona

**Target User**: Internal — the plan orchestrator + sibling tasks S1/S3 + future maintainers:
1. **The orchestrator** reads `gap_stale_refs.md` as the stale-reference-hygiene evidence that closes the
   P1.M6.T1 documentation module. It must give a crisp verdict (no unresolved bugs) so the module closes.
2. **P1.M6.T1.S1** (README-completeness, parallel) consumes this audit's verdict that the README CONTENT
   is clean of stale refs, so S1 can focus purely on README-completeness without re-auditing references.
3. **P1.M6.T1.S3** (commit readiness) consumes the verdict to assert the changeset has no dangling
   BUGS.md/VT-* references before the final integration commit.
4. **Future maintainers** read `gap_stale_refs.md` to understand WHY the `# VT-0NN` comments must NOT be
   "cleaned up" (they are fix-rationale documentation + the test↔comment↔code traceability the gap audits
   rely on), and WHY the PRD still carries 3 stale items (read-only; routed for a human).

**Use Case**: The evolved PRD (§4.2bis/§4.9) carries inline `VT-00N` + `BUGS.md` references from a prior
bug-tracking convention (a BUGS.md that was never committed). P1.M1–P1.M5 verified the SOURCE (17 gap
audits, all COMPLIANT) + TESTS (LIVE-green). The acceptance gate (P1.M5.T5.S1) routed "VT-001 =
doc-drift only (→ P1.M6.T1.S2)" (tests/ACCEPTANCE.md:37). This audit is that per-VT, file:line-cited
confirmation — the final doc-hygiene gate before the integration commit.

**Pain Points Addressed**: (1) A dangling "see BUGS.md VT-001" reference + a stale "currently violates"
caveat in the PRD could mislead a future reader into believing VT-001 is an OPEN bug; this audit proves
it is RESOLVED + test-pinned + regression-guarded. (2) Without a per-VT classification, a maintainer
might "clean up" the `# VT-0NN` comments — destroying the fix rationale. (3) The audit closes the loop
the acceptance gate opened (it routed VT-001 here; this is the evidence).

## Why

- **This closes the stale-reference half of the documentation module.** The acceptance gate routed
  VT-001/BUGS.md doc-drift here; S1 owns README-completeness, S3 owns the commit. Without this audit,
  the doc module is only two-thirds evidenced.
- **VT-001 is the headline.** PRD §4.2bis says "`voicectl status` currently violates this [the daemon
  never imports RealtimeSTT/torch/ctranslate2]; see BUGS.md VT-001." This audit PROVES the violation no
  longer exists (the recorder-host subprocess + the un-probed device cache fixed it; VT-008 is the
  automated regression guard). Recording that proof — with file:line citations — IS the deliverable.
- **The `VT-0NN` comments are documentation, not drift.** A naive "resolve stale references" sweep could
  delete them. This audit records that they are the contract's ACCEPTABLE state ("resolved in code with
  comments explaining the fix") and that removing them would break the gap-audit traceability + lose the
  fix rationale. The deliverable prevents that regression.
- **BUGS.md does not exist, and must not be created.** Creating it to satisfy the PRD's dangling
  reference would paper over the drift; the proper fix is a human PRD edit (the PRD is read-only here).
- **Scope discipline.** This task writes ONE file (`gap_stale_refs.md`). It edits no shipped artifact
  (the changeset docs are clean), runs no tests (the fixes are already LIVE-green + the audit cites their
  pinning tests), and routes the genuinely-stale items (all in the read-only PRD) to a human.

## What

Four phases, in order: **(1) READ** the relevant source regions (`daemon.py` VT-001/VT-002 comments,
`recorder_host.py` VT-007, `config.py` VT-005/VT-006, `systemd/voice-typing.service` VT-003/VT-004,
`install.sh`/`hypr-binds.conf` VT-003, README's Model-lifecycle section) + the gap audits
(`gap_voicectl.md` §4.1, `gap_config.md` §3, `gap_systemd.md`); **(2) RUN the audit grep** over the
exact contract input set + `find . -name BUGS.md`; **(3) CLASSIFY every hit** RESOLVED vs UNRESOLVED
(pre-verified: all RESOLVED) with the resolution site + pinning test; **(4) WRITE `gap_stale_refs.md`**
(the dossier). NO pytest, NO heavy script, NO shipped-tree edit.

### Success Criteria

- [ ] `find . -name BUGS.md` → none (re-confirmed); the grep over the contract input set re-run LIVE.
- [ ] Every `VT-00N` + `BUGS.md` hit in the shipped tree CLASSIFIED (RESOLVED-in-code vs unresolved),
      each with the resolution file:line + the pinning test:line (re-grep; the PRP's numbers are a
      starting point, not gospel).
- [ ] VT-001 explicitly resolved: cites the un-probed `_resolved_device_cache` seed + the recorder-host
      subprocess + `test_daemon.py:1621` + the VT-008 guard; records the PRD caveat as STALE (read-only).
- [ ] gap_stale_refs.md written with the 8-section structure + a verdict line ("PASS: BUGS.md absent;
      all VT-001..VT-008 RESOLVED in code + test-pinned; no unresolved bugs; changeset docs clean; 3
      stale items routed to a human PRD edit (read-only).").
- [ ] NO remediation task created in the shipped tree (no unresolved bugs); the read-only PRD drift
      (3 entries) is the only routed item.
- [ ] Scope respected: NO edit to README.md (→ S1's lane), PRD.md, tasks.json, prd_snapshot.md,
      .gitignore, or any source/test/script/config; NO pytest / heavy script.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer gets: the pre-verified VT-001..VT-008 classification matrix (each: meaning →
resolution site → pinning test → RESOLVED), the BUGS.md-absent finding, the read-only-PRD drift
register (3 items), the verbatim `gap_stale_refs.md` scaffold (8 sections), the exact grep commands,
and the hard scope boundaries (README → S1, commit → S3, PRD read-only). No inference required — the
agent re-confirms line numbers live, re-runs the grep, and materializes the dossier.

### Documentation & References

```yaml
# MUST READ — the audit design + pre-verified findings (THIS is the spec for the audit).
- file: plan/006_862ee9d6ef41/P1M6T1S2/research/stale_refs_audit_findings.md
  why: "§0 the exact audit grep (contract input set). §1 BUGS.md absent + the dangling PRD.md:144 ref.
        §2 the VT-001..VT-008 classification matrix (ALL RESOLVED + test-pinned) with resolution site +
        pinning test per row. §3 changeset-doc cleanliness (README + comments CORRECT, not stale — do
        NOT clean up VT-* comments). §4 the 3 read-only PRD drift items. §5 no remediation required.
        §6 [Mode B] sweep verdict (CLEAN). §7 scope/coordination (README→S1, commit→S3). §8 grep-only
        validation."
  critical: "G1: ALL VT-* are RESOLVED — do NOT edit the code/tests (would reintroduce the bugs). G2:
             the # VT-0NN comments are documentation, NOT drift — do NOT delete them. G3: BUGS.md must
             NOT be created. G4: VT-001 is RESOLVED (the PRD caveat is the stale part, read-only)."

# MUST READ — the VT-001 headline (the code that fixed the "status imports CUDA" violation).
- file: voice_typing/daemon.py
  why: "L566 `self._resolved_device_cache = self._unprobed_device_config()` — the seed that makes the
        first `voicectl status` NEVER call cuda_check (VT-001). L571 the VT-002 reseed note. L899/L1244
        the dead-child/idle-unload reseed (VT-002). L1585-L1609 the _resolved_device() docstring spelling
        out VT-001/VT-002. The recorder-host subprocess (`self._host`, the P1.M3.T2.S2 re-plan note at
        ~L573) owns ALL CUDA contexts — the daemon process never creates one."
  critical: "VT-001 is FIXED here. Cite L566 (seed) + L1585 (docstring) in gap_stale_refs.md. Do NOT
             edit daemon.py."

# MUST READ — the VT-007 abort-sentinel fix + VT-001's recorder-host CUDA ownership.
- file: voice_typing/recorder_host.py
  why: "L511/L522/L543/L660/L675 the `aborted` flag + the ('final',{text:''}) sentinel (VT-007). The
        child process owns the recorder + ALL CUDA contexts (the VT-001 architectural fix)."
  critical: "VT-007 is FIXED here. Cite L511/L660. Do NOT edit recorder_host.py."

# MUST READ — VT-005/VT-006 (config) + the blocklist correctness.
- file: voice_typing/config.py
  why: "L105 the device-value validation (VT-005: only cuda|cpu, ValueError on typo). L191 the
        `NOTE (VT-006)` comment on blocklist (bare 'you' removed — common word, not a hallucination)."
  critical: "VT-005 + VT-006 FIXED here. Cite L105 + L191. Do NOT edit config.py. gap_config.md §3 is the
             deep VT-006 audit."

# MUST READ — VT-003/VT-004 (systemd unit + install.sh + hypr-binds.conf).
- file: systemd/voice-typing.service
  why: "L3/L81/L84 VT-004 (graphical-session.target After/PartOf/WantedBy). L47 VT-003 (__REPO__ is a
        PLACEHOLDER install.sh substitutes)."
- file: install.sh
  why: "L28/L116/L174 VT-003 (UV override + __REPO__ sed substitution + the $HOME/.local/bin/voicectl
        stable launcher). L121 VT-004 (rm stale default.target.wants symlink)."
- file: hypr-binds.conf
  why: "L21 VT-003 (binds use the stable $HOME/.local/bin/voicectl launcher)."
  critical: "VT-003 + VT-004 FIXED across these three files. Cite the lines. Do NOT edit them.
             gap_systemd.md is the deep audit; test_systemd_unit.py:258-370 pins both."

# MUST READ — the gap audits that already classified these (cite verdicts; don't re-derive).
- file: plan/006_862ee9d6ef41/architecture/gap_voicectl.md
  why: "§4.1 is the AUTHORITATIVE VT-001 classification: 'BUGS.md does not exist (doc drift owned by
        P1.M6.T1.S2); the CLIENT ctl.py is import-clean; the violation is daemon-side (now fixed by the
        recorder-host model)'. Cite its verdict + its import-purity test (test_voicectl.py:235)."
- file: plan/006_862ee9d6ef41/architecture/gap_config.md
  why: "§3 is the deep VT-006 audit (intentional deviation, compliant-by-design, documented in 3 places,
        test-pinned). §S2.3 blocklist correctness in BOTH files. Cite its verdict."
- file: plan/006_862ee9d6ef41/architecture/gap_systemd.md
  why: "VT-003/VT-004 audit (the unit is graphical-session-aware; install.sh substitutes __REPO__ +
        removes the stale symlink). Cite its verdict."
- file: plan/006_862ee9d6ef41/architecture/external_deps.md
  why: "L34-37 is the concise VT-001/VT-003/VT-004/VT-006 one-liner registry (the cross-cutting summary)."

# MUST READ — the parallel sibling (README owner) + the acceptance gate (routes VT-001 here).
- file: plan/006_862ee9d6ef41/P1M6T1S1/PRP.md
  why: "S1 owns README-COMPLETENESS (it routes VT-001/stale-refs to THIS task — the boundary is mutual).
        S1 MAY apply an optional 1-row README edit. To avoid a README-writer conflict with the parallel
        S1, THIS task does NOT edit README (any optional README note is routed in gap_stale_refs.md)."
  critical: "Do NOT edit README.md here (writer-conflict with S1). gap_stale_refs.md cites S1 as the
             README owner; this task owns stale-REF hygiene only."
- file: tests/ACCEPTANCE.md
  why: "L37 (criterion #6) asserts 'VT-003/VT-004 fixed in-source; VT-001 = doc-drift only (→
        P1.M6.T1.S2)'. gap_stale_refs.md is the deeper, per-VT confirmation the gate routed here."

# MUST READ — the merged PRD (the source of the stale references; READ-ONLY).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§4.2bis (the 'see BUGS.md VT-001' caveat + the 'currently violates' clause) + §4.9 (VT-003
        __REPO__, VT-004 graphical-session.target) + §4.5 (the blocklist still listing 'you' = VT-006).
        These are the stale references this audit CLASSIFIES; the PRD text itself is read-only."
  critical: "PRD.md / prd_snapshot.md are READ-ONLY (FORBIDDEN OPERATIONS). Record the drift; do NOT
             edit the PRD."

# Hard rules.
- file: AGENTS.md
  why: "This task runs ONLY grep + find + read (fast, safe). NO pytest, NO heavy shell script
        (test_idle_and_gpu.sh / e2e_virtual_mic.sh forbidden unless explicitly required — they are
        irrelevant to a doc-reference audit). The pinning tests are CITED, not re-run."
```

### Current Codebase tree (relevant slice — state at P1.M6.T1.S2)

```bash
/home/dustin/projects/voice-typing/
├── README.md                         # CLEAN (no BUGS.md/VT-* refs); Model-lifecycle section L333. READ ONLY (S1 owns).
├── PRD.md                            # READ-ONLY (carries the stale §4.2bis/§4.5/§4.9 refs this audit classifies)
├── config.toml                       # L67 `# NOTE (VT-006)` comment (CORRECT, not stale). READ ONLY.
├── install.sh                        # L28/L116/L174 VT-003, L121 VT-004 (CORRECT). READ ONLY.
├── hypr-binds.conf                   # L21 VT-003 (CORRECT). READ ONLY.
├── systemd/voice-typing.service      # L3/L47/L81/L84 VT-003/VT-004 (CORRECT). READ ONLY.
├── voice_typing/
│   ├── daemon.py                     # L566/L899/L1244/L1585 VT-001/VT-002 (CORRECT). READ ONLY.
│   ├── recorder_host.py              # L511/L660 VT-007 (CORRECT). READ ONLY.
│   └── config.py                     # L105/L191 VT-005/VT-006 (CORRECT). READ ONLY.
├── tests/                            # test_config/test_daemon/test_recorder_host/test_systemd_unit/test_textproc/ACCEPTANCE.md cite VT-* (CORRECT). READ ONLY.
└── plan/006_862ee9d6ef41/
    ├── architecture/gap_*.md         # 17 source audits; gap_voicectl/gap_config/gap_systemd/external_deps classify the VT-* (READ ONLY)
    └── P1M6T1S2/
        ├── PRP.md                    # THIS file
        ├── research/stale_refs_audit_findings.md   # the pre-verified VT-* matrix (this PRP's research)
        └── gap_stale_refs.md         # ← OUTPUT (NEW; the stale-reference audit dossier)
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md   # NEW — the stale-reference audit dossier (OUTPUT)
# (NO shipped-tree file edited. NO README.md edit (→ S1's lane). NO PRD.md/tasks.json edit. Audit only.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G1) — ALL VT-* are RESOLVED; do NOT edit the code/tests. Every VT-001..VT-008 reference
#   in the shipped tree is an explanatory comment (or test name) documenting a RESOLVED, test-pinned fix.
#   Editing the resolved code/tests to "remove the VT reference" would REINTRODUCE the bug + break the
#   pinning test. The deliverable is gap_stale_refs.md (a REPORT), not a code change.

# CRITICAL #2 (G2) — the # VT-0NN / NOTE (VT-0NN) comments are DOCUMENTATION, not drift. The contract's
#   ACCEPTABLE state is "resolved in code with comments explaining the fix." Removing the comments would
#   lose the fix rationale + break the test↔comment↔code traceability the 17 gap_*.md audits rely on.
#   Do NOT "clean up" the VT-* comments. gap_stale_refs.md §5 explicitly says so.

# CRITICAL #3 (G3) — BUGS.md must NOT be created. It does not exist (find . -name BUGS.md → none).
#   Creating it to satisfy PRD.md:144's "see BUGS.md VT-001" would paper over the drift; the proper fix
#   is a human PRD edit removing that clause now that VT-001 is resolved. The implementer CANNOT edit
#   the PRD (read-only) → the drift is ROUTED in gap_stale_refs.md §6, not fixed here.

# CRITICAL #4 (G4) — VT-001 is RESOLVED; the PRD caveat is the stale part. PRD §4.2bis:144 says
#   "voicectl status currently violates this [daemon never imports CUDA]; see BUGS.md VT-001." The code
#   PROVES the violation no longer exists: daemon.py:566 seeds the un-probed device cache (status never
#   calls cuda_check); the recorder-host subprocess owns ALL CUDA contexts; test_daemon.py:1621 asserts
#   calls["n"]==0; test_daemon.py:1745 (VT-008) is the automated regression guard. gap_stale_refs.md §3
#   must state this verdict explicitly with the citations — it is the HEADLINE finding.

# CRITICAL #5 (G5) — re-grep line numbers LIVE. The PRP/research cite VT-* at specific lines
#   (daemon.py:566, config.py:191, test_systemd_unit.py:258, etc.) but lines may have drifted. Cite
#   CURRENT line numbers from a fresh grep in gap_stale_refs.md, not the PRP's.

# CRITICAL #6 (G6) — scope boundary with siblings. README-COMPLETENESS is owned by P1.M6.T1.S1
#   (parallel; it MAY apply an optional README row). To avoid a README-writer conflict, THIS task does
#   NOT edit README.md — any optional README note is ROUTED in gap_stale_refs.md, not applied. The final
#   commit is P1.M6.T1.S3. Cite S1/S3 as owners; do not duplicate.

# CRITICAL #7 (G7) — the grep must use the EXACT contract input set. Scope the grep to
#   `voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf`. Do NOT include
#   plan/ (the research/gap docs legitimately cite VT-*) or .pi-subagents/artifacts/ (agent scratch) or
#   .venv/ — those are NOT shipped artifacts and their VT-* hits are out of scope.

# CRITICAL #8 (G8) — the PRD's stale references are READ-ONLY. The 3 genuinely-stale items
#   (PRD.md:144 "see BUGS.md VT-001"; PRD.md:144 "currently violates"; PRD §4.5 blocklist "you") live in
#   PRD.md, which is in the FORBIDDEN-TO-EDIT list. gap_stale_refs.md records them as known doc drift
#   routed for a human PRD edit; it does NOT fix them (and does NOT flag them as a defect in the shipped
#   artifacts, which are clean).

# CRITICAL #9 (G9) — DO NOT run pytest or heavy shell scripts. The audit is pure grep + find + read
#   (fast, safe, no AGENTS.md timeout needed). The pinning tests are CITED (file:line), not re-run —
#   test_daemon.py/test_recorder_host.py load CUDA models; running them is forbidden unless explicitly
#   required, and it is irrelevant to a doc-reference audit.

# CRITICAL #10 (G10) — this is a REPORT item. The ONLY write is gap_stale_refs.md (CREATE). Do NOT touch
#   voice_typing/*.py, tests/*, *.sh, *.service, *.conf, config.toml, README.md, PRD.md, tasks.json,
#   prd_snapshot.md, .gitignore, or any other plan/ file.
```

## Implementation Blueprint

### Data models and structure

N/A — no code. The "data" is the VT-001..VT-008 classification matrix (8 rows × {VT, meaning, resolution
site, pinning test, verdict}) + the BUGS.md finding + the read-only-PRD drift register (3 entries). The
deliverable is a Markdown dossier.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: READ the VT-* resolution sites + the classifying gap audits. CONFIRM line numbers.
  - READ daemon.py around L560-L575 (VT-001 seed + the recorder-host re-plan note), L895-L905 + L1240-
    L1250 (VT-002 reseeds), L1580-L1615 (the _resolved_device docstring).
  - READ recorder_host.py around L505-L545 + L655-L680 (VT-007 sentinel).
  - READ config.py around L100-L110 (VT-005) + L185-L200 (VT-006 blocklist comment).
  - READ systemd/voice-typing.service L1-L90 (VT-003 __REPO__ + VT-004 graphical-session.target).
  - READ install.sh L25-L35 + L110-L180 (VT-003/VT-004) + hypr-binds.conf L18-L30 (VT-003).
  - READ gap_voicectl.md §4.1 (the authoritative VT-001 classification) + gap_config.md §3 (VT-006) +
    gap_systemd.md (VT-003/VT-004) + external_deps.md L34-L37 (the one-liner registry).
  - READ README.md around L333 (Model lifecycle & VRAM) — confirm it documents the recorder-host model
    (the VT-001 architecture) and has NO BUGS.md/VT-* refs.
  - DO NOT run pytest or any heavy script. GO to Task 2.

Task 2: RUN the audit grep + the BUGS.md find. CLASSIFY every hit.
  - `find . -name BUGS.md` → confirm NONE (exclude .git/.venv).
  - `grep -rn 'BUGS\.md' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf`
    → expect ZERO hits (re-confirm).
  - `grep -rn 'VT-00[0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf`
    → the full VT-* hit list (re-confirm against research §2).
  - `grep -rn 'VT-0[0-9][0-9]' …` (broader; catches VT-010+ — expect none beyond VT-001..VT-008).
  - For EACH hit: map it to its VT-ID, its resolution site, and its pinning test (research §2 matrix).
    Classify RESOLVED (all) vs UNRESOLVED (none expected). Flag VT-001 explicitly (research §2 + §4).
  - DECIDE: if an UNRESOLVED VT-* bug is found (it won't be) → that becomes a remediation task. Else →
    no remediation (research §5). GO to Task 3.

Task 3: WRITE plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md (OUTPUT — the dossier).
  - USE the verbatim 8-section scaffold in "Task 3 SOURCE" below. Fill: the verdict line; the BUGS.md
    finding; the VT-001..VT-008 matrix (re-confirm resolution:line + pinning test:line from Task 1/2);
    the VT-001 headline resolution; the changeset-doc cleanliness verdict; the read-only-PRD drift
    register; the no-remediation verdict; the scope section (README→S1, commit→S3).
  - VERDICT line: "PASS: BUGS.md is absent (only a dangling PRD.md:144 reference, read-only). All VT-001
    through VT-008 references in the shipped tree are explanatory comments documenting RESOLVED,
    test-pinned fixes — there are ZERO unresolved VT-* bugs. VT-001 (the headline: 'voicectl status
    imports CUDA in the daemon process') is RESOLVED (daemon.py:<seed-line> un-probed device cache +
    recorder-host subprocess; test_daemon.py:<assert-line> + the VT-008 guard). The changeset docs
    (README + # VT-0NN comments) are CLEAN/CORRECT, not stale. Three stale references live in the
    read-only PRD (§4.2bis BUGS.md/VT-001 caveat; §4.5 blocklist 'you') — routed for a human PRD edit,
    out of this task's scope. No remediation task created."
  - DO NOT edit any shipped file / PRD / tasks / README. GO to Task 4.

Task 4: (NONE) — no shipped-tree changes. Verify gap_stale_refs.md is self-contained + the verdict is
  unambiguous, then done. (NO README edit — routed to S1's lane to avoid the parallel writer conflict.)
```

#### Task 3 SOURCE — `gap_stale_refs.md` verbatim scaffold (fill the static parts; confirm line numbers LIVE)

```markdown
# Stale-reference audit — P1.M6.T1.S2 (BUGS.md / VT-* doc drift)

**Date:** <YYYY-MM-DD>
**Verdict:** **PASS.** BUGS.md is absent from the repo (the only reference is a dangling `PRD.md:<line>`
clause, read-only). All `VT-001`..`VT-008` references in the shipped tree (`voice_typing/`, `tests/`,
`README.md`, `config.toml`, `install.sh`, `systemd/`, `hypr-binds.conf`) are **explanatory comments
documenting RESOLVED, test-pinned fixes** — there are **zero unresolved VT-* bugs**. The changeset docs
(README + the `# VT-0NN` comments) are **clean / correct, not stale**. Three stale references live in the
**read-only PRD** and are routed for a human PRD edit (out of this task's scope). No remediation task was
created. Scope: stale-reference hygiene ONLY; README-completeness → P1.M6.T1.S1; commit readiness →
P1.M6.T1.S3.

## 1. Audit command + scope

```bash
find . -name BUGS.md                                 # → none
grep -rn 'BUGS\.md'   voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf   # → 0 hits
grep -rn 'VT-00[0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf   # → the VT-* list below
```
Scope = the shipped tree only (NOT `plan/` research/gap docs, NOT `.pi-subagents/`, NOT `.venv/` —
those legitimately cite VT-* and are out of scope).

## 2. BUGS.md — absent (dangling PRD reference only)

- `find . -name BUGS.md` → **none**. No shipped file references BUGS.md (grep → 0 hits).
- The ONLY BUGS.md reference is **`PRD.md:<line>`** (§4.2bis): *"see BUGS.md VT-001"* — a dangling
  reference in the **read-only** PRD. (`.pi-subagents/artifacts/*` also mentions it; that is agent
  scratch, not a shipped artifact.)
- **Classification:** doc drift, READ-ONLY. BUGS.md is NOT created (it would paper over the drift); the
  proper fix is a human PRD edit (routed §6).

## 3. VT-001..VT-008 classification — ALL RESOLVED + test-pinned

| VT | Meaning | Resolution site (shipped) | Pinning test(s) | Verdict |
|----|---------|----------------------------|-----------------|---------|
| VT-001 | daemon process never probes CUDA / "status imports CUDA" (PRD §4.2bis caveat) | `daemon.py:<seed-line>` `_resolved_device_cache = _unprobed_device_config()`; `daemon.py:<doc-line>` docstring; recorder-host subprocess owns all CUDA contexts | `test_daemon.py:<assert-line>` `calls["n"]==0`; `test_daemon.py:<guard-line>` VT-008 | **RESOLVED** |
| VT-002 | reseed device cache to un-probed config on host death / idle-unload | `daemon.py:<reseed1-line>`, `daemon.py:<reseed2-line>` | `test_daemon.py:<test-line>` | **RESOLVED** |
| VT-003 | `__REPO__` placeholder + stable `$HOME/.local/bin/voicectl` launcher | `systemd/voice-typing.service:<line>`, `install.sh:<lines>`, `hypr-binds.conf:<line>` | `test_systemd_unit.py:<lines>` | **RESOLVED** |
| VT-004 | graphical-session.target After/PartOf/WantedBy (was default.target) | `systemd/voice-typing.service:<lines>`, `install.sh:<line>` (rm stale symlink) | `test_systemd_unit.py:<lines>` | **RESOLVED** |
| VT-005 | `asr.device` value validation (cuda\|cpu only, ValueError) | `config.py:<line>` | `test_config.py:<lines>` | **RESOLVED** |
| VT-006 | bare `"you"` removed from blocklist defaults | `config.py:<line>`, `config.toml:<line>` | `test_config.py:<line>`, `test_textproc.py:<lines>` | **RESOLVED** |
| VT-007 | abort-path unblock sentinel (API-drift robustness) | `recorder_host.py:<lines>` | `test_recorder_host.py:<lines>` | **RESOLVED** |
| VT-008 | daemon never imports ctranslate2/torch — VT-001 regression guard | (test-only guard) | `test_daemon.py:<lines>` | **RESOLVED** |

(Replace `<...-line>` with the LIVE grep'd numbers.)

## 4. VT-001 headline resolution (the contract's explicit flag)

PRD §4.2bis (`PRD.md:<line>`) says *"voicectl status currently violates this [the daemon never imports
RealtimeSTT/torch/ctranslate2]; see BUGS.md VT-001."* **This violation NO LONGER EXISTS.**
- `daemon.py:<seed-line>`: `self._resolved_device_cache = self._unprobed_device_config()` — the first
  `voicectl status` reads UN-PROBED config and **never calls** `cuda_check.resolve_device_and_models`.
- The **recorder-host subprocess** (`voice_typing/recorder_host.py`) owns the recorder + ALL CUDA
  contexts; the daemon process never imports torch/ctranslate2/creates a CUDA context.
- `test_daemon.py:<assert-line>`: `assert calls["n"] == 0, "status_snapshot must NOT call
  cuda_check.resolve_device_and_models (VT-001)"`.
- `test_daemon.py:<guard-line>` (VT-008): a fresh-subprocess import-purity guard asserts the daemon
  process never has `ctranslate2`/`torch` in `sys.modules` — the **automated regression guard** so a
  future status field cannot reintroduce the import.
- `gap_voicectl.md` §4.1 confirms: BUGS.md absent (doc drift); the CLIENT `ctl.py` is import-clean; the
  daemon-side status path is fixed.

**Verdict: VT-001 RESOLVED + test-pinned + regression-guarded.** The PRD caveat is the stale part
(read-only — routed §6).

## 5. Changeset-doc cleanliness — README + comments are CORRECT, not stale

- **README.md:** `grep -ni 'bugs\|VT-0' README.md` → **0 hits.** The `### Model lifecycle & VRAM`
  section (`README.md:<line>`) already documents the recorder-host subprocess + the bounded (`killpg`
  after 5 s join) teardown — the VT-001-relevant architecture — without citing VT-* IDs. **No edit.**
- **`# VT-0NN` / `NOTE (VT-0NN)` source comments:** every one is an explanatory comment documenting a
  RESOLVED fix (the contract's acceptable state). **Removing them would lose the fix rationale + break
  the test↔comment↔code traceability the gap audits rely on. Do NOT "clean up" the VT-* comments.**
- **`tests/`** VT-* references: test names/docstrings + assertions that PIN the fixes (e.g.
  `test_daemon.py` VT-001/VT-008, `test_systemd_unit.py` VT-003/VT-004). Correct, not stale.

## 6. Read-only PRD drift register (routed for a human PRD edit — out of this task's scope)

| PRD location | Stale text | Why stale | Owner |
|---|---|---|---|
| `PRD.md:<line>` §4.2bis | "see BUGS.md VT-001" | BUGS.md does not exist (dangling ref) | human PRD edit (read-only here) |
| `PRD.md:<line>` §4.2bis | "voicectl status currently violates this" | VT-001/VT-008 FIXED it (status never probes CUDA) | human PRD edit (read-only here) |
| `PRD.md` §4.5 blocklist | still lists bare `"you"` | VT-006 removed it from code + config + test | human PRD edit (read-only here) |

These are flagged as known doc drift, NOT defects in the shipped artifacts (which are clean). The
implementer cannot edit PRD.md (FORBIDDEN OPERATIONS); the recommendation is a PRD-only changeset by a
human.

## 7. Remediation — NONE required

The contract: *"If any unresolved VT-* issues found, create remediation tasks."* **No unresolved VT-*
issues exist** (§3: all RESOLVED; §5: changeset docs clean). Therefore: no code remediation; no BUGS.md
creation; one routed recommendation (§6, read-only PRD, non-blocking).

## 8. Scope

- **IN scope (this task):** stale-reference audit + gap_stale_refs.md.
- **OUT of scope (cited, not duplicated):** README-completeness → **P1.M6.T1.S1** (this task does NOT
  edit README — routed to avoid a parallel writer conflict); commit readiness → **P1.M6.T1.S3**;
  PRD.md / tasks.json / prd_snapshot.md edits → **human/orchestrator** (read-only here). No
  source/test/script/config edit; no pytest/heavy script.
```

### Implementation Patterns & Key Details

```bash
# The ONLY commands this audit runs (fast, safe, no AGENTS.md timeout needed). Do NOT run pytest/scripts.
cd /home/dustin/projects/voice-typing

# (0) BUGS.md existence + the contract grep (authoritative input set):
find . -name BUGS.md                                              # → none
grep -rn 'BUGS\.md'   voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf
grep -rn 'VT-00[0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf
grep -rn 'VT-0[0-9][0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf  # broader

# (1) The VT-001 headline citations (re-grep LIVE; these are the proof the violation is fixed):
grep -n '_resolved_device_cache = self\._unprobed_device_config' voice_typing/daemon.py
grep -n 'VT-001' voice_typing/daemon.py
grep -n 'calls\["n"\] == 0' tests/test_daemon.py            # the status-never-probes assertion
grep -n 'VT-008' tests/test_daemon.py                       # the regression guard

# (2) README cleanliness (expect 0 hits):
grep -cni 'bugs\|VT-0' README.md                            # → 0
grep -n 'Model lifecycle' README.md                        # the section that documents the recorder-host model

# (3) The read-only PRD drift (classify, do NOT edit):
grep -n 'BUGS\.md VT-001\|currently violates' PRD.md
grep -n '"you"' PRD.md | head                              # the §4.5 blocklist
```

### Integration Points

```yaml
DELIVERABLE (the audit dossier):
  - create: "plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md"
  - pattern: "Self-contained stale-reference audit (the verbatim 8-section scaffold in Task 3 SOURCE)."
  - consume_by: "P1.M5.T5.S1 acceptance gate (the VT-001 doc-drift it routed here, now per-VT confirmed);
                 P1.M6.T1.S1 (README owner — confirms README is clean of stale refs); P1.M6.T1.S3 (commit
                 readiness — asserts no dangling refs before the integration commit); the orchestrator +
                 future maintainers (the 'do NOT clean up VT-* comments' note prevents a regression)."

RUN (the only live actions — fast, safe):
  - commands: "find BUGS.md; grep BUGS.md/VT-* over the contract input set; grep the VT-001 citations;
               grep README cleanliness; grep the read-only PRD drift"
  - expected: "fast; BUGS.md absent; all VT-* RESOLVED; README clean; 3 PRD-drift items classified"

DO NOT RUN:
  - commands: [".venv/bin/python -m pytest ...", "tests/test_idle_and_gpu.sh", "tests/e2e_virtual_mic.sh"]
  - reason: "A doc-reference audit needs no test run. test_daemon.py/test_recorder_host.py load CUDA;
             AGENTS.md forbids the heavy scripts unless explicitly required; they are irrelevant here."

EDITS (1 — REPORT only):
  - create: "plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md"
  - forbidden: "README.md (→ S1's lane), voice_typing/*, tests/*, *.sh, *.service, *.conf, config.toml,
                PRD.md, tasks.json, prd_snapshot.md, .gitignore, any other plan/ file, BUGS.md (do NOT create)"
```

## Validation Loop

### Level 1: Syntax & Style (N/A — a Markdown dossier; no code)

```bash
ls -la plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md
grep -c '^## ' plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md    # expect >= 8 (sections 1-8)
grep -q 'PASS' plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md && echo "verdict present"
# Expected: dossier present with 8 sections + PASS verdict.
```

### Level 2: (N/A — no unit tests; this is a doc-audit item)

### Level 3: Static cross-check (fast, safe — confirms the dossier's claims against the LIVE tree)

```bash
cd /home/dustin/projects/voice-typing

# (A) BUGS.md absent + zero shipped references:
find . -name BUGS.md                                                  # → none
! grep -rqn 'BUGS\.md' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf \
  && echo "L3a PASS: no shipped BUGS.md reference" || echo "L3a FAIL: a shipped file references BUGS.md"

# (B) every shipped VT-* hit is a RESOLVED comment/test (re-confirm against the §3 matrix):
grep -rn 'VT-00[0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf \
  | sed 's/:.*//' | sort -u                                          # the FILES that cite VT-* (each must be a resolution site)

# (C) the VT-001 headline citations resolve LIVE (the proof the violation is fixed):
grep -q '_resolved_device_cache = self\._unprobed_device_config' voice_typing/daemon.py && echo "L3c PASS: VT-001 seed present"
grep -q 'calls\["n"\] == 0' tests/test_daemon.py && echo "L3c PASS: status-never-probes assertion present"
grep -q 'VT-008' tests/test_daemon.py && echo "L3c PASS: VT-008 regression guard present"

# (D) README clean of stale refs:
! grep -qni 'bugs\|VT-0' README.md && echo "L3d PASS: README clean" || echo "L3d FAIL: README has a stale ref"

# (E) the read-only PRD drift is the ONLY genuinely-stale surface (classify, do NOT edit):
grep -n 'BUGS\.md VT-001' PRD.md && echo "L3e: PRD §4.2bis dangling ref (read-only, routed)"
# Expected: L3a PASS; L3b the VT-* files are all resolution sites; L3c all three citations present;
# L3d README clean; L3e the PRD dangling ref confirmed (read-only).
```

### Level 4: Domain-specific validation (documentation accuracy)

```bash
cd /home/dustin/projects/voice-typing
# (a) Confirm the dossier's VT-001 citations match the LIVE code (accuracy, not just presence):
sed -n '<seed-line>p' voice_typing/daemon.py    # the _resolved_device_cache seed (use the dossier's line)
# (b) Confirm the classifying gap audits concur (cite, don't re-derive):
grep -q 'VT-001' plan/006_862ee9d6ef41/architecture/gap_voicectl.md && echo "L4b: gap_voicectl §4.1 classifies VT-001"
grep -q 'VT-006' plan/006_862ee9d6ef41/architecture/gap_config.md && echo "L4b: gap_config §3 classifies VT-006"
# (c) Confirm the acceptance gate routed VT-001 here (the loop-closing evidence):
grep -q 'VT-001.*P1.M6.T1.S2\|VT-003/VT-004 fixed' tests/ACCEPTANCE.md && echo "L4c: acceptance gate routed VT-001 → S2"
# Expected: the dossier's VT-001 seed line matches LIVE code; gap_voicectl/gap_config concur; the
# acceptance gate's routing is confirmed. (All read-only; no test run.)
```

## Final Validation Checklist

### Technical Validation

- [ ] `gap_stale_refs.md` written with the 8-section structure + a PASS verdict line.
- [ ] BUGS.md confirmed absent (`find` → none); ZERO shipped references to BUGS.md.
- [ ] VT-001..VT-008 classification matrix COMPLETE (each: resolution site:LIVE-line + pinning test +
      RESOLVED verdict); VT-001 headline resolved with the seed + docstring + test assertion + VT-008 guard.
- [ ] Changeset-doc cleanliness verdict recorded (README clean; VT-* comments are CORRECT, do NOT clean up).
- [ ] Read-only PRD drift register (3 items) recorded + routed for a human (not fixed here).
- [ ] (No pytest / heavy script — this is a doc audit; L1 + L3 + L4 grep checks are the gates.)

### Feature Validation

- [ ] The contract's grep re-run over the EXACT input set; every hit classified RESOLVED vs UNRESOLVED.
- [ ] VT-001 explicitly resolved (the headline the contract flags) — cited in code + test + the VT-008 guard.
- [ ] No unresolved VT-* bug → no remediation task created; the read-only PRD drift is the only routed item.
- [ ] [Mode B] doc-sweep verdict: changeset docs CLEAN; the stale surface is read-only (PRD) → routed.

### Code Quality Validation

- [ ] gap_stale_refs.md is self-contained (a reader needs no other file to see the verdict + evidence).
- [ ] Line numbers in gap_stale_refs.md are LIVE (re-grepped, not copy-pasted from the PRP/research).
- [ ] The "do NOT clean up VT-* comments" note is explicit (prevents a destructive future edit).

### Documentation & Deployment

- [ ] The stale-reference hygiene half of the docs module is closed (README → S1; commit → S3).
- [ ] gap_stale_refs.md cites the sibling owners (S1 README, S3 commit) so the docs module closes cleanly.
- [ ] No shipped-tree edit; no PRD/tasks edit; no BUGS.md created; no new env vars / config keys / source changes.

---

## Anti-Patterns to Avoid

- ❌ Don't edit the resolved code/tests to "remove a VT-* reference" — it would REINTRODUCE the bug + break
  the pinning test. The deliverable is a REPORT (gap_stale_refs.md), not a code change (G1).
- ❌ Don't "clean up" the `# VT-0NN` / `NOTE (VT-0NN)` comments — they are fix-rationale DOCUMENTATION
  (the contract's acceptable state) + the gap-audit traceability; removing them is destructive (G2).
- ❌ Don't create BUGS.md — it doesn't exist; creating it papers over the dangling PRD ref. The proper fix
  is a human PRD edit (read-only here) (G3).
- ❌ Don't flag VT-001 as an OPEN bug — it is RESOLVED (the recorder-host subprocess + the un-probed device
  cache + VT-008 guard). The stale part is the PRD caveat, which is read-only (G4).
- ❌ Don't cite PRP/research line numbers in gap_stale_refs.md — re-grep LIVE and cite CURRENT lines (G5).
- ❌ Don't edit README.md (→ S1's lane, parallel) or judge git cleanliness (→ S3) — scope boundary (G6).
- ❌ Don't scope the grep to `plan/` or `.pi-subagents/` — those legitimately cite VT-* and are out of
  scope; use the EXACT contract input set (G7).
- ❌ Don't try to fix the read-only PRD (PRD.md / prd_snapshot.md are FORBIDDEN-TO-EDIT) — record the drift
  + route it for a human (G8).
- ❌ Don't run pytest or the heavy shell scripts — a doc-reference audit uses grep + find + read only (G9).
- ❌ Don't manufacture an unresolved VT-* bug to justify the task — the audit is pre-PASS; a clean verdict
  (no unresolved bugs) is the correct, valuable outcome (G1/G10).

---

## Confidence Score

**9/10.** The audit is pre-verified: BUGS.md is absent (`find` → none; zero shipped references), and all
eight VT-001..VT-008 references in the shipped tree are explanatory comments documenting RESOLVED,
test-pinned fixes — each mapped 1:1 to a resolution site + a pinning test in the research matrix
(re-confirmed via the authoritative grep over the exact contract input set). The VT-001 headline is
proven RESOLVED by the un-probed `_resolved_device_cache` seed (`daemon.py`) + the recorder-host
subprocess + the `calls["n"]==0` assertion + the VT-008 automated regression guard (`test_daemon.py`),
with `gap_voicectl.md` §4.1 concurring. The changeset docs (README + comments) are CLEAN/CORRECT. The
only genuinely-stale items are 3 references in the read-only PRD — correctly routed for a human, not
"fixed" here. The task is a pure REPORT (one CREATE: `gap_stale_refs.md`), runs grep + find + read only
(no pytest / heavy script per AGENTS.md), and is robust to the parallel S1 (it does NOT edit README,
avoiding the writer conflict). The −1 residual is line-drift risk (the PRP/research cite specific lines)
— fully mitigated by the "re-grep LIVE" instruction (Task 2 + L3 cross-check). No shipped-tree edit; no
PRD/tasks edit; scope cleanly bounded from S1 (README) and S3 (commit).
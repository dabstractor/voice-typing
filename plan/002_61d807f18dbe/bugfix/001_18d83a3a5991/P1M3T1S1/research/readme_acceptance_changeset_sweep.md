# Research — P1.M3.T1.S1 README.md + ACCEPTANCE.md changeset sweep (bugfix release)

Mode B changeset-level documentation sweep (the LAST task; depends on all implementing
subtasks). Ground truth verified by reading the actual files on 2026-07-11. The changeset:
(a) Issue 1 (Critical): launch_daemon.sh exports HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 — the
production daemon no longer phones home to huggingface.co. (b) Issue 2: status.sh exits 0.
(c) Issue 3: mic probe is TTL-cached at 30s (P1.M2.T2.S1, IN PARALLEL — treat its PRP as a contract).
(d) Issue 4: install.sh confirms offline operation. (e) regression tests added.

---

## 1. Changeset landing status (verified live)

| Issue | Fix | Owner task | Status | Verified in source |
|---|---|---|---|---|
| 1 (Critical) | launch_daemon.sh exports offline vars | P1.M1.T1.S1 | **LANDED** | launch_daemon.sh:71-72 `export HF_HUB_OFFLINE=1` / `export TRANSFORMERS_OFFLINE=1` |
| 1 | drift-guard test | P1.M1.T1.S2 | LANDED | tests/test_systemd_unit.py (referenced by install.sh:135) |
| 1 | close circular-proof gap | P1.M1.T1.S3 | **LANDED** | test_idle_and_gpu.sh:225-234 greps daemon.log for ZERO `HTTP Request: GET https://huggingface.co`; does NOT pre-set the offline vars; launches via launch_daemon.sh (production path) |
| 4 | install.sh offline confirmation | P1.M1.T2.S1 | **LANDED** | install.sh:130-149 (post-restart journal grep + prints "offline check: no huggingface.co network calls after restart (HF_HUB_OFFLINE=1 active)") |
| 2 | status.sh exit 0 | P1.M2.T1.S1 | **LANDED** | status.sh:47 `exit 0`; comment softened at :24 ("tmux's #(...) IGNORES the exit code") |
| 3 | mic probe TTL cache (30s) | P1.M2.T2.S1 | **IN PARALLEL** (Ready) | daemon.py will gain `_MIC_PROBE_TTL_S = 30.0`; `_arm()` respects the TTL. NOT yet in tree at research time, but treat the P1.M2.T2.S1 PRP as a contract. |

**Consequence for this docs task:** Issues 1, 2, 4 are DONE in code; the docs must catch up
(ACCEPTANCE.md criterion 8 is still the OLD circular proof; the README makes no offline-enforcement
claim). Issue 3 is landing in parallel — the README's "Wrong microphone" claim "the probe re-runs on
each arm" will become STALE, and P1.M2.T2.S1 is Mode A (daemon.py docstrings only; it does NOT touch
README), so THIS task owns that cross-cutting README claim.

---

## 2. README.md — current state + required/optional edits

### 2.1 The offline promises (lines 3 & 6) — ALREADY CORRECT post-fix (no edit)
- Line 3: "Fully-local voice typing for Linux."
- Line 6: "The recognizer runs 100% on your machine; nothing is sent to a cloud."
- Pre-fix these were FALSE (the daemon phoned home). Post-fix (launch_daemon.sh exports) they are
  TRUE. The item: "If they already state the right thing, no edit needed." → these two lines need no
  change. (PRD Issue 1 references them as "the README explicitly promises … that promise is false as
  shipped" — the fix makes the existing promise true.)

### 2.2 (RECOMMENDED) Intro offline-enforcement note — the item's "consider adding" clause
- There is no dedicated "features/capabilities" section; the intro paragraph (lines 1-6) IS the
  overview. The item suggests: "add a brief note (e.g. 'Offline mode enforced via HF_HUB_OFFLINE=1 in
  the launch wrapper — models load from local cache, zero runtime network')."
- WHY add it: the whole changeset exists to make the "nothing is sent to a cloud" promise TRUE.
  Documenting the MECHANISM (launch_daemon.sh sets HF_HUB_OFFLINE=1) makes the promise credible and
  points a maintainer at the right file. It is one terse sentence, matching the README voice.
- WHERE: append one sentence to the intro paragraph, right after "nothing is sent to a cloud."
  Verbatim text in the PRP Task 2.
- ACCURACY: the launch wrapper (launch_daemon.sh:71-72) exports HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1
  before exec'ing python; install.sh prefetches models to ~/.cache/huggingface. So "models load from
  the local cache with zero runtime network calls" is accurate. ✓

### 2.3 (REQUIRED) "Wrong microphone" section — the mic-probe-on-each-arm claim is going stale
- Current text (README line 223-227): "After fixing the source, arm again with `voicectl toggle`
  (the probe re-runs on each arm)."
- Post P1.M2.T2.S1 (parallel, TTL cache `_MIC_PROBE_TTL_S = 30.0`): `_arm()` calls
  `_refresh_mic_status()` which is TTL-cached — the probe runs at most once per 30 s, NOT on every
  arm. So "re-runs on each arm" becomes FALSE.
- P1.M2.T2.S1 is Mode A (daemon.py docstrings + `_arm` inline comment); it does NOT edit README.md.
  This cross-cutting user-facing claim is Mode B → THIS task owns it. REQUIRED update.
- VERIFICATION GATE (implementer): before/after editing, `grep -n "_MIC_PROBE_TTL_S" voice_typing/daemon.py`.
  At implementation time (this task runs LAST, after P1.M2.T2.S1) the constant MUST be present. If it
  is somehow absent, STOP and flag — the parallel task has not landed and the README edit would be
  premature.
- Verbatim replacement in PRP Task 3. Accuracy points: (1) probe cached ~30 s; (2) arming stays
  instant (that's the WHY — PRD §4.2 "instant toggle-on"); (3) for an immediate re-probe, restart the
  daemon (construction force-probes). Match the README's terse voice.

### 2.4 status.sh / Issue 2 — NO README change needed
- The README "tmux status line" section (~line 92) describes status.sh's OUTPUT. Issue 2 (exit 0)
  changed status.sh's EXIT CODE, not its output (it always printed correctly). So the README's
  status.sh description is unaffected. ✓ (The Issue 2 comment-softening is inside status.sh itself —
  Mode A, already done by P1.M2.T1.S1.)

### 2.5 install.sh / Issue 4 — README "Install" section already accurate
- README "Install" step 4 says "Prefetches the whisper models into ~/.cache/huggingface (warn-only
  on miss)." Post Issue 4, install.sh ALSO does a post-restart offline journal grep and prints an
  "offline check: ..." line. The README's 7-step list predates that grep but is not INACCURATE (it
  just doesn't mention the offline confirmation). Adding it is OUT of scope for this task (the item's
  Install focus is the offline claim in the intro/criterion 8, not re-listing install steps; and the
  prior plan already added the portaudio step). OPTIONAL one-liner if desired; not required.

---

## 3. tests/ACCEPTANCE.md — criterion 8 is the OLD circular proof (4 stale spots)

The whole point of P1.M1.T1.S3 was to close the circular-proof gap (PRD Issue 1: the test pre-set
HF_HUB_OFFLINE=1 itself, so it passed trivially and never observed the production network calls).
test_idle_and_gpu.sh is NOW non-circular (launches via launch_daemon.sh, greps for zero HTTP
requests). ACCEPTANCE.md still describes the OLD circular proof in FOUR places. All four must be
updated to the non-circular framing.

### 3.1 The four stale spots (verbatim current text — see PRP Task 4 for exact replacements)

**Spot 1 — criterion 8 table row:**
```
| 8 | No network access needed at runtime (models cached by install) | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — the daemon ran the entire test under `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` and loaded the cached models (went ready + survived 120 s armed idle). (Block below.) |
```
Problem: "ran the entire test under HF_HUB_OFFLINE=1" IS the circular framing (the test set the var).

**Spot 2 — evidence block line (stale format vs the test's new emission):**
```
offline_env: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
```
The test now emits (test_idle_and_gpu.sh:422, verified):
```
offline_env: via launch_daemon.sh exports (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1); daemon.log HF-request grep: CLEAN
```

**Spot 3 — PASS line (stale vs the test's new PASS line):**
```
[PASS] criterion 8 (no network): daemon ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded cached models
```
The test now emits (test_idle_and_gpu.sh:234):
```
[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)
```

**Spot 4 — "Notes on the method" criterion 8 bullet:**
```
- **Criterion 8** is proven by the run itself: the daemon was launched with `HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1`, which is a hard offline switch. That it went ready and survived 120 s of
  armed idle is empirical proof the models load from the local cache with zero network access.
```
Problem: again the circular "launched with HF_HUB_OFFLINE=1" framing.

### 3.2 The non-circular proof (what the four spots must now describe)
From test_idle_and_gpu.sh (lines 4-6, 53-55, 225-234, 402-405, 422 — all verified):
- The test launches the daemon via `launch_daemon.sh` (the PRODUCTION path — `LAUNCH="$REPO/voice_typing/launch_daemon.sh"`, line 94).
- It does NOT pre-set HF_HUB_OFFLINE (the G-OFFLINE invariant, line 53: "do NOT pre-set HF_HUB_OFFLINE (that masked Issue 1)").
- The offline vars come FROM the wrapper (launch_daemon.sh exports them).
- The proof is a daemon.log grep: `grep -q 'HTTP Request: GET https://huggingface.co'` → FAIL if any match (line 231-232); PASS prints "ZERO … lines (production path offline)" (line 234).
- This is NON-CIRCULAR because the test does not supply the variable a regression would remove.

### 3.3 The "How to reproduce" + regenerate instructions — still accurate (no change)
"Regenerate the 5 / 6 / 8 block by running ./tests/test_idle_and_gpu.sh and pasting its
=== ACCEPTANCE EVIDENCE === output" — still correct (the test still emits that block; only the
`offline_env:` VALUE changed). No edit needed to those instructions.

---

## 4. Other overview docs scan (clause c)

- `ls docs/ CONTRIBUTING.md CHANGELOG.md` → NONE exist. The only overview docs are README.md and
  tests/ACCEPTANCE.md. ✓
- **Criterion 7 in ACCEPTANCE.md is stale-but-borderline.** It says: `| 7 | ... | partial | ... the
  README is task P2.M1.T2.S1 (pending), which will document ... |`. That references the ORIGINAL
  plan (plan 001's P2.M1.T2.S1). In this bugfix (plan 002) the README clearly EXISTS and is
  comprehensive (install/hotkey/tmux/config/troubleshooting/CPU-only all present). So "partial" is
  stale. BUT criterion 7 is about README completeness, NOT offline/status.sh/mic, so it is borderline
  for this task's scope (clause c names "offline behavior, status.sh, or mic health"). Treat as an
  OPTIONAL coherence fix: the implementer MAY flip criterion 7 to PASS with evidence "README.md
  documents install, hotkey, tmux status, configuration, troubleshooting, and CPU-only mode" (which is
  verifiably true). Not required by the contract; include only if doing a thorough coherence pass.

---

## 5. Style + scope boundaries

- **README voice** (line 7-8): "for two readers: dustin, six months from now, and anyone who clones
  the repo … assumes a Linux power user who wants exact commands, not hand-holding." TERSE,
  command-first, no marketing, no hand-holding. Match in any added prose.
- **ACCEPTANCE.md voice**: factual evidence record, pasted command output, no marketing. Match the
  existing table/bullet style.
- **Scope:** edit README.md + tests/ACCEPTANCE.md ONLY. No source code, no PRD.md/tasks.json/
  prd_snapshot.md/.gitignore, no launch_daemon.sh/status.sh/install.sh/daemon.py (the bugfix code is
  DONE). No new files.
- **No changelog voice.** Don't write "Issue 1 fixed" in user-facing README prose. In ACCEPTANCE.md
  (which IS an evidence record) referencing "bugfix Issue 1" is appropriate (it already does, e.g.
  "this task — direct evidence"), but describe the PROOF mechanism, not the fix history.
- **The README mic-probe edit depends on the parallel task.** Verify `_MIC_PROBE_TTL_S` is in
  daemon.py before finalizing that edit (see §2.3). This task runs LAST per the item ("depends on
  ALL implementing subtasks and runs last"), so P1.M2.T2.S1 should be done.

---

## 6. Validation approach (no test framework for markdown)

- README.md: `grep -nE 'offline|HF_HUB|cloud|network' README.md` (offline note now present);
  `grep -n "re-runs on each arm" README.md` → must be GONE (stale claim removed);
  `grep -c '^```' README.md` stays EVEN.
- ACCEPTANCE.md: `grep -nE 'HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded|ran the entire test under' tests/ACCEPTANCE.md` → must be GONE (circular framing removed);
  `grep -n 'production path\|launch_daemon.sh\|ZERO' tests/ACCEPTANCE.md` → present (non-circular);
  `grep -n 'HTTP Request: GET https://huggingface.co' tests/ACCEPTANCE.md` → present (the grep proof named).
- `git status --porcelain` → only `M README.md` + `M tests/ACCEPTANCE.md`.

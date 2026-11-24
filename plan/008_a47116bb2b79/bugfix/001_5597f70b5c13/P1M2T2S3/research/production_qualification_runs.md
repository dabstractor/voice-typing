# Research — qualify the selected production source on both routes (P1.M2.T2.S3 / BUG-002, PRD R.7 G5)

The PRP (../PRP.md) references this note as its single source of truth. Pins: the gate law and
numbers, the S2 handoff contract, the exact qualification commands, the evidence-file surgery
rules (one parser-compatible CURRENT table + archived tables under different headers), the
M1.T3.S1 CPU-baseline diff procedure, the real-model watch policy, and the honest-failure path.

## 0. What this task IS and IS NOT

**IS**: the *qualification authority* for BUG-002's timing gate. Run the **production selection**
(the UNFLAGGED arm — whatever `_PARTIAL_CALLBACK_ATTR` resolves to after S2's candidate landed;
NEVER `--partial-source plain` as an override) independently on BOTH isolated routes against the
R.7 G5 numbers, then refresh the **authoritative current verdict table** in
`tests/G5_TIMING_EVIDENCE.md`. **A verified bulk source does NOT change default delivery** —
`output.delivery` stays `"stream-edit"`; G6 graduation is a separate gate owned elsewhere
(P1.M2.T3.S1 refreshes `tests/G6_GRADUATION.md` FROM this evidence).

**IS NOT**: a remediation task (S2 owns the candidate; do not tune anything here), a desktop run
(R.7: private compositor/daemon only; the live desktop, service, and clipboard are never touched),
or a G3/G6 claim (a G5 pass never marks a row verified, never implies operator acceptance).

## 1. The gate law (bulk_delivery_gate.md §"Gate and evidence handoff" — verbatim requirements)

Required **independently on both routes** (im-gtk AND pi-ghostty):
- aligned speech-end→word-visible **median ≤500 ms and p95 <1 s**;
- update-ready→first-changed-frame **insertion p95 ≤100 ms, correction p95 ≤50 ms**;
- **≥100 real insertions AND ≥100 real corrections** within the replay budget;
- unchanged ⇒ **zero edits**;
- **no sustained ≥5 outstanding words for ≥2.0 s** (the 57-word backlog class of failure);
- **no sentence-end dump**;
- keep clock sanity/coverage; **report unverifiable metrics rather than imputing a pass**.

Item RESEARCH NOTE (gate doc, binding): **G5 is per route** (each route passes/fails on its own
numbers) **and G6 is separate**. **Target ACKs, editor-poll state, and the no-desktop smoke are
NOT display frames** — an ACK or a 10 ms editor read-poll is never credited as word-visible
(G5 doc's own law: "No sample may be credited merely because target ACKs"; "Do not count lab
smoke as a measurement"). On im-gtk the frame basis was an "editor read-poll proxy (frame NOT
verified)" — if that is still the basis, the frame-specific bars must be labeled unverified, not
passed. The pi-ghostty route has the S5-qualified paint observer (verified).

## 2. The evidence file's surgery rules (THE most fiddly part)

`tests/G5_TIMING_EVIDENCE.md` (571 lines at research time) is read by
`tests/g6_assessment.py:parse_route_verdicts`, which **scans verdict tables and OVERWRITES
duplicate route keys**. Therefore:
1. **Exactly ONE parser-compatible "current" verdict table** (the `## Verdict table` at :14 — same
   column format: `| route | verdict | ins | cor | miss | speech med/p95 ms | worst ms | ready
   ins/cor p95 ms | max out | flags |`) with BOTH expected routes and verdicts from
   `pass | fail(reason) | blocked(reason)` — **use `blocked` for unverified/unrun**, and the file
   must carry a current verdict for both routes EVEN IF A RUN WAS NOT PERFORMED (the item: "pass/
   fail/blocked even when unverified").
2. The 2026-11-23 historical failed baseline + the S6 A/B route-by-source tables move/STAY under
   **different table headers** (archive sections — e.g. the existing "### Route-by-source result"
   heading is fine as an archive; do not re-title it into anything the parser reads as current).
   Historical/A-B tables MUST NOT be parseable as current route verdicts (item DOCS rule).
3. S2's "## Candidate remediation (P1.M2.T2.S2)" section (non-verdict vocabulary) stays as the
   record of what was consumed; this task does not edit it.
4. After the edit, run the parser (Level 3 check) and record the parsed routes/verdicts — proving
   non-interference is part of the deliverable.
5. New sections for this task: refresh `## Verdict table` + a `## Qualification run
   (P1.M2.T2.S3)` provenance section (date/commit, effective source — the resolved callback name,
   exact commands, sample counts, misses, instrumentation limits, frame basis per route), updated
   `## Thresholds vs measured` numbers, and `## Open items` (BUG-002/acceptance #13 status with
   the exact blocker if any route fails/blocked). Keep `## Run commands` current.

## 3. The measured baseline being qualified against (S6, 2026-11-24 @ 9ffc54b)

- im-gtk/stabilized: word-lag med 190.5 / p95 244.3 ms (WITHIN the 500/1000 bars!), useful→field
  2.6 ms — BUT ins/cor = 1/0, miss 872, backlog max 57, dump no → fail on counts/backlog. The
  recognizer cadence dominated; S2's cadence/dispatch fix targets exactly this.
- pi-ghostty (both arms): word-lag med 7786–11983 ms, dump YES, backlog 57 → fail everywhere;
  lag accumulates BEFORE callback/adapter (field paint 4 ms, frames 30–43 ms) — the recognizer +
  writer/delivery complex S1/S2 own.
- pi-ghostty R.8 answer: plain is NOT earlier at the callback boundary (+1.3 ms) and only
  noise-level earlier at the field boundary (−3.3 ms, under the 10 ms poll quantum) — selection
  rests on granularity/churn/burst, NOT latency.
- im-gtk/plain: NOT-RUN (two sanctioned attempts died on `bulk delivery never re-armed`); never
  imputed. Re-completing the im-gtk A/B pair is explicitly left open for T2 — i.e. THIS task if
  the re-comparison condition fires (§4).
- Missing everywhere: coherent ack_ts (update→ack / ack→field splits stay "merged"/absent);
  exact field→frame at first-visible is structurally consumed by S5's baseline — the paint-
  qualified fallback (disclosed) is the frame evidence on pi; im-gtk's frame basis is a read-poll
  proxy (NOT verified).

## 4. The conditional A/B re-comparison (item LOGIC sentence 1)

"Compare both callbacks again under candidate scheduling **if behavior materially changed**."
Decision rule: read S2's candidate section. If S2 changed the recognizer cadence / dispatch
scheduling (anything that alters update volume, burst profile, or which updates become useful),
the S6 A/B conclusion ("no early-plain effect; ~48% no-ops") may no longer hold → re-run the
paired arms (plain + unflagged) per route on the SAME clips/kernel/budget, re-derive the winner
**by visible lag + counts**, and if plain wins, flip the production default (that flip is part of
THIS task's authority — "Select the better qualifying mode internally for bulk only") via
`_PARTIAL_CALLBACK_ATTR` default resolution, then qualify the UNFLAGGED arm. If S2's change is
confined to non-scheduling stages (e.g. adapter waits), the S6 A/B stands — record that reasoning
in one line and go straight to the production runs. **The qualification runs themselves use the
production selection only** — no `--partial-source` override ("no experimental override").

## 5. Exact commands (the qualification procedure)

```bash
cd /home/dustin/projects/voice-typing
# 0. (only if fixtures drifted) one-time alignment fixtures:
CUDA_LIBS="$(.venv/bin/python -c '...nvidia cublas/cudnn dirs...')" && export LD_LIBRARY_PATH="$CUDA_LIBS"
timeout -k 2 900 env G5_ALIGN=1 .venv/bin/python tests/g5_make_alignments.py
# 1. scaffold smoke — WIRING ONLY, never a measurement:
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
# 2. THE QUALIFICATION (production arm, unflagged; one route at a time; NEVER interrupt mid-run):
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" \
    .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty
# (conditional A/B arms, same shape + --partial-source plain, one per route — only per §4)
# Exit 0 pass / 1 honest fail / 2 misuse; ONE JSON verdict line per route on stdout — the artifact
# of record. Copy each run's artifact into this task's research/ dir; delete scratch tmpdirs
# immediately (tmpfs = RAM; AGENTS.md Rule 3).
```
Bash-tool backstop STRICTLY greater than 1500 (S6 used 1560). Each run loads ONE CUDA model
(warm; one discarded warmup; `auto_unload_idle_seconds=0`). Runs are sequential, never parallel.

## 6. The CPU-baseline diff vs P1.M1.T3.S1 (mandatory pre/post check)

Before AND after the evidence edit (the tree may carry S2's production diff):
```bash
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no
```
Diff the FAILED node IDs **by name, never counts** against the canonical 20-name list in
`P1M1T3S1/research/bug004_named_daemon_baseline.md` §1 (test_cfg_to_kwargs_cuda_path …
test_sentinel_consume_clears_on_suppress_since). Set-diff rule: any NEW failure name = a
regression introduced by S1+S2+S3's changes — investigate/fix or record as the blocker; any
missing name = a fix (note it). Also run the fast sweep: `timeout 600 .venv/bin/python -m pytest
tests/ --ignore=tests/test_feed_audio.py -q` — no new failures beyond the documented
classifications (G1_BASELINE.md + the 20-name addendum).

## 7. The real-model watch policy (honor separately; never claim it ran)

The hunt's real-model watch set (`test_streaming.py`, baselined 3P/4F) is a SEPARATE policy:
attempt it bounded (`timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -q --tb=no`),
and record the outcome with provenance — but if the GPU is unavailable/occupied or the run cannot
complete, record "not-run" WITHOUT claiming it ran or borrowing numbers. It is not a gate for
this task; it is context the record must be honest about.

## 8. Safety rails (R.7 + AGENTS.md; non-negotiable)

- Private compositor/daemon only (the lab owns Xvfb/sway, isolated D-Bus, fake key devices, mic
  feed, duck off, no live service/clipboard, bounded scratch, own-process cleanup). NEVER arm the
  live systemd daemon; never foreground a daemon.
- GNU `timeout -k 2 1500` per route + a strictly larger bash-tool timeout; **never interrupt a
  G5 run mid-flight**; re-run-once discipline for aborted arms (an arm that fails twice on
  runner-side errors stands as not-run — no imputation).
- Copy artifacts into `plan/.../P1M2T2S3/research/`, delete scratch immediately.
- Fake transports for pure tests only; the qualification runs are the real transports.
- A verified bulk source does NOT change default delivery; G6/README implications flow to
  P1.M2.T3.S1/P1.M2.T3.S2 — this task hands them the evidence, not the claims.

## 9. Failure path (first-class, per the item)

If a route fails, cannot certify frames (e.g. im-gtk still read-poll-proxy-only and the frame
bars are claimed), or is unrun (two sanctioned attempts): the verdict is `fail(reason)` /
`blocked(reason)`; **retain opt-in** (`output.delivery` default unchanged), **do not promote an
unproven source as the fix**, and **leave BUG-002 / acceptance #13 OPEN** in the evidence with
the exact blocker (which bar, which number, which missing instrument). An honest blocked table is
a successful task outcome; a fabricated pass is the only true failure.

## 10. Mode A docs (daemon.py)

Update (only if the selection/rationale changed this round, or to correct drift): the
`_PARTIAL_CALLBACK_ATTR` / `_PARTIAL_SOURCES` docstring block (daemon.py:219-234) — the selected
callback rationale (R.8: chosen by visible lag + granularity/churn per the S6/S3 measurements;
plain-vs-stabilized boundary findings) with Mode A provenance (dates, numbers, the evidence
file's section). No behavior edit in this task except a possible selection-default flip per §4
(S2's candidate diff is S2's; this task only flips IF the re-comparison says plain wins).

## 11. Scope (do / don't)

DO: run §5 (conditionally §4), update tests/G5_TIMING_EVIDENCE.md per §2, run §6 (+§7), copy
artifacts into research/, hand P1.M2.T3.S1/.S2 the evidence.

DON'T: tune/remediate any stage (S2), edit bulk_controller.py (S1) or S2's candidate section,
change default delivery or graduate anything (G6/T3), touch PRD/tasks.json/prd_snapshot/
.gitignore, run the live desktop, promote an unproven source, merge frame-basis evidence
(exact-pair vs paint-qualified fallback are never merged), or let a historical/A-B table become
parser-current.

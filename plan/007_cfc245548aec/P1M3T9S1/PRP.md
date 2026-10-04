---
name: "P1.M3.T9.S1 — existing-suite adjustments + ACCEPTANCE.md rows for the single-mode + streaming world"
---

## Goal

**Feature Goal**: Bring the two pre-Rev-2 verification suites (`tests/test_idle_and_gpu.sh`,
`tests/test_feed_audio.py`) and the acceptance dossier (`tests/ACCEPTANCE.md`) into line with the
collapsed single-model + streaming reality, so that (a) both suites run GREEN against the current
daemon (they are both currently broken/stale against removed API surface), and (b) the acceptance
table carries all 12 Rev 2 criteria rows with real evidence pointers, including a REGENERATED
`=== ACCEPTANCE EVIDENCE ===` capture proving the single-model GPU lifecycle on `nvidia-smi`.

**Deliverable**:
1. `tests/test_idle_and_gpu.sh` — the stale T7 lite mode-switch roundtrip (L535–~L633) deleted and
   replaced by a **single-model assertion block** (exactly ONE model resident, no large-model
   worker, armed VRAM window widened to ~0.5–3 GB, `voicectl cancel` smoke test); VRAM constants,
   header comments, evidence block, and final result gate updated accordingly.
2. `tests/test_feed_audio.py` — the broken `lite_recorder` fixture (calls removed
   `cfg_to_kwargs(cfg, lite=True)`) and the two lite-vs-normal tests (L653/L679) rewritten as
   single-construction asserts; finals fuzzy bar corrected from 0.80 to 0.70 (small.en is now the
   final model).
3. `tests/ACCEPTANCE.md` — row #4 amended (typed = live partials + commits), row #10 rewritten as
   single-model arming with REGENERATED VRAM evidence, rows #11 (streaming) and #12 (cancel
   fallback) ADDED — each pointing at its T8/shell evidence.

**Success Definition**: All three files updated; `timeout 900 ./tests/test_idle_and_gpu.sh` passes
end-to-end (quiet room, unit stopped first) and its regenerated evidence block is pasted into
`tests/ACCEPTANCE.md`; `timeout 900 .venv/bin/python -m pytest tests/test_feed_audio.py -v` passes
on the CUDA box; the fast sweep (`timeout 300 .venv/bin/python -m pytest tests/test_config.py
tests/test_textproc.py tests/test_daemon.py tests/test_voicectl.py -q` and friends) stays green;
`tests/ACCEPTANCE.md` shows 12 rows whose evidence references name REAL, existing tests/commands.

## User Persona (if applicable)

**Target User**: The project owner (dustin) + any future implementing/QA agent reading the
acceptance dossier to decide whether the Rev 2 milestone is done.

**Use Case**: Running the heavy verification suites and reading `tests/ACCEPTANCE.md` as the
definition-of-done record. A stale suite that dies on `voicectl toggle-lite` (exit 64) or a
`TypeError` in a fixture makes the whole Rev 2 milestone unverifiable.

**Pain Points Addressed**: Both pre-existing suites currently FAIL against the collapsed daemon
(removed `toggle-lite` command; removed `cfg_to_kwargs(..., lite=)` kwarg); the acceptance table
is missing the two Rev 2 rows (#11/#12) and carries a stale pre-Rev-2 evidence block.

## Why

- PRD §7 (Rev 2) defines 12 acceptance criteria; the dossier only has 10 rows, and row #10's own
  text says "VRAM evidence regenerates → P1.M3.T9.S1". This item IS that regeneration.
- The single-mode collapse (P1.M1.T2) and cancel surface (P1.M2.T7.S1) removed API the old tests
  exercise; without this item the milestone cannot close ("all suites green under the single-mode +
  streaming world" — task OUTPUT).
- T8 (P1.M3.T8.S1/S2, Complete) produced the streaming evidence (`tests/test_streaming.py`
  a–g) that rows #4/#11/#12 must point at.

## What

Adjustments only — **no production code changes** (`voice_typing/*` is frozen for this item). If a
suite exposes a real production bug, STOP and report it (do not "fix" the test to hide it — see the
standing note in test_idle_and_gpu.sh: "a FAIL here means a PRODUCTION bug … do NOT weaken the
assertion").

### Success Criteria

- [ ] `tests/test_idle_and_gpu.sh` contains ZERO references to `toggle-lite`, `start-lite`,
      `mode: normal`, or `T7 lite mode-switch`; it DOES contain single-model assertions (one-model
      log grep, no-`distil-large-v3` grep, `mode: lite` status check, VRAM window 512–3072 MiB,
      `voicectl cancel` armed no-op smoke) and passes.
- [ ] `tests/test_feed_audio.py` contains ZERO references to `lite=True`, `lite_recorder`, or
      lite-vs-normal comparisons; single-construction asserts exist (one model resident; finals
      ≥0.70 fuzzy on `utt_simple.wav`); the suite passes on CUDA.
- [ ] `tests/ACCEPTANCE.md` has 12 rows; #4/#10 updated, #11/#12 added; a regenerated evidence
      block (from an actual passing shell run) replaces the pre-Rev-2 historical capture; the
      block no longer prints the removed `models:` status line.
- [ ] No production file under `voice_typing/` modified (verify with `git diff --stat`).

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, would they have everything needed to implement this
successfully?" — Yes: every stale reference is pinned to file+line below, every replacement
assertion is specified with its exact grep/assertion target and the source-of-truth line that
justifies it, and every validation command carries its AGENTS.md-mandated double timeout.

### Documentation & References

```yaml
# MUST READ - Include these in your context window
- file: tests/test_idle_and_gpu.sh
  why: Primary edit target #1. T7 block L535–~L633 (delete+replace), VRAM consts L137-138,
        evidence block ~L700, final gate ~L737-745, header comments L1-100.
  pattern: keep the existing G-* gotcha comment discipline; every changed assertion keeps its
           [PASS]/[FAIL] printing + accumulator (T7_OK) + evidence-echo line so the final gate
           and the ACCEPTANCE paste stay coherent.
  gotcha: voicectl MUST stay wrapped in `timeout` (the shell function at ~L290 does this — use it,
          never the raw binary); the script refuses to start if a daemon is already running.

- file: tests/test_feed_audio.py
  why: Primary edit target #2. `recorder` fixture L253 (already single-model via collapsed
        cfg_to_kwargs), broken `lite_recorder` L311-348, stale tests L653 + L679, fuzzy bar at
        L447 (`test_fuzzy_accuracy`).
  pattern: mirror the `recorder` fixture exactly (lazy `_load_deps()`, `_filter_kwargs_to_signature`,
           skip-on-construction-failure, `_safe_shutdown` on a helper thread with 30s join).
  gotcha: `cfg_to_kwargs(cfg, *, resolved=None)` is the ONLY signature now (daemon.py:169);
          `lite=True` raises TypeError. `pytestmark` skip-guard + lazy deps keep collection
          import-pure (test_voicectl.py asserts that — do not add top-level heavy imports).

- file: tests/ACCEPTANCE.md
  why: Primary edit target #3. Rows 1-10 table, evidence block template (stale `models:` line),
        "How to reproduce" header, method notes (T6 VRAM window text), bottom PASS-lines sample.
  pattern: one table row per PRD §7 criterion with Status + Evidence columns naming real
           test files/functions and LIVE/STATIC evidence types (the existing rows model this).
  gotcha: `voicectl status` NO LONGER prints a `models:` line — current field order is
          listening / mode / phase / partial / last / uptime / device / mic / context-prompt
          (ctl.py:105-115). The evidence template must drop `models:` and add the new lines.

- file: voice_typing/daemon.py
  why: Source of truth for what to assert. cfg_to_kwargs L169-199 (single model fills BOTH slots,
        use_main_model_for_realtime=True, endpointer = lite_post_speech_silence_duration);
        status payload "mode": "lite" constant L2128; startup log line L1106-1109
        ("voice-typing device resolved: device=%s compute_type=%s model=%s" — fires ONCE at
        startup via the driver probe, before/independent of the lazy first-arm model load).
  pattern: READ ONLY for this item.
  gotcha: on CPU fallback the model is tiny.en, not small.en — grep assertions must target the
          resolved log line, not hardcode beyond what the CUDA run guarantees.

- file: tests/test_streaming.py
  why: The T8 evidence rows #4/#10/#11/#12 point at. Tests: test_a_delta_cadence, test_b_commit_
        rewind_exact, test_c_pause_join, test_d_decode_prompts, test_e_cancel, test_f_user_key_
        freeze, test_g_stranded_tail. Fuzzy asserts are ≥0.80 on typed screen content vs pinned
        refs (L979, L1136-1138, L1254, L1477) — SUBSUMES the old T7 ≥0.70 finals bar. VERIFY these
        names/lines before citing them in ACCEPTANCE.md rows.
  pattern: CUDA-gated real-model suite; run via `timeout 900 .venv/bin/python -m pytest
           tests/test_streaming.py -v`.
  gotcha: this item does NOT edit test_streaming.py — the contract's "verify the ≥70% assertion
          lives there, else add" resolves to EXISTS-at-0.80 (stronger). Document that in row #10.

- file: plan/007_cfc245548aec/architecture/substrate_map.md
  why: §10 = the current ACCEPTANCE row inventory (incl. the note that old row 10's "0.5" default
        text is stale → 0.8); §13 = test-file inventory with line refs.
  pattern: background only.

- file: AGENTS.md  (repo root)
  why: HARD run rules: two timeouts on every non-trivial command (inner GNU `timeout` + bash-tool
        timeout above it); voicectl ALWAYS under `timeout 30`; NEVER foreground the daemon; the
        shell suite gets bash-tool timeout 900 and must never be interrupted mid-run; stop the
        systemd unit BEFORE the shell suite (its preflight refuses otherwise); pytest CUDA files
        under `timeout 600-900`; use `.venv/bin/python` and `/home/dustin/.local/bin/uv` (shell
        aliases trap bare `python3`/`pip`).
  pattern: the validation commands below already encode all of this.
  gotcha: the shell test's 120 s armed-silence window listens to the REAL default mic — run it in
          a QUIET room or ambient speech can produce a real final and fail T4 spuriously.
```

### Current Codebase tree (relevant excerpt)

```bash
tests/
├── ACCEPTANCE.md            # EDIT TARGET #3 (10 rows → 12; regenerated evidence block)
├── test_feed_audio.py       # EDIT TARGET #2 (broken lite fixture + 2 stale tests)
├── test_idle_and_gpu.sh     # EDIT TARGET #1 (stale T7 block + VRAM window)
├── test_streaming.py        # READ ONLY — T8 evidence source for rows #4/#10/#11/#12
├── test_daemon.py           # READ ONLY — drain/single-model/rollback-hatch mocked evidence
├── test_key_listener.py     # READ ONLY — cancel listener evidence for row #12
└── test_control_socket.py   # READ ONLY — socket cancel evidence for row #12
voice_typing/
├── daemon.py                # READ ONLY — cfg_to_kwargs L169, mode L2128, device log L1106
└── ctl.py                   # READ ONLY — 6-command surface, status field order
validate.sh                  # OPTIONAL one-line phase-2 addition (see Task 6)
```

### Desired Codebase tree with files to be added and responsibility of file

No new files. All work is edits to the three targets (+ optional validate.sh one-liner).

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: voicectl's control-socket readline() has NO timeout (ctl.py send_command uses
#   sock.makefile) — a wedged daemon blocks it FOREVER. ALWAYS `timeout 30 .venv/bin/voicectl <cmd>`
#   (exit 124 = wedged, do NOT blind-retry; run the AGENTS.md cleanup block first).
# CRITICAL: never exec the daemon in the foreground (blocks until quit/signal). The shell suite
#   manages its own daemon via launch_daemon.sh + trap — give the harness timeout 900 and do not
#   interrupt mid-run; `systemctl --user stop voice-typing` BEFORE starting it (preflight refuses).
# CRITICAL: `cfg_to_kwargs` takes NO `lite` kwarg anymore — signature is (cfg, *, resolved=None).
#   model == realtime_model_type == resolved["model"] (small.en on CUDA; tiny.en on CPU fallback).
# GOTCHA: `voicectl status` field order is listening/mode/phase/partial/last/uptime/device/mic/
#   context-prompt — there is NO `models:` line anymore. grep-based assertions must match these.
# GOTCHA: daemon logs "voice-typing device resolved: device=cuda compute_type=float16 model=small.en"
#   ONCE at startup (driver probe — happens even before the lazy first-arm model load), so the
#   one-model grep is available early in daemon.log.
# GOTCHA: mode is CONSTANT "lite" (daemon.py:2128) — never assert "mode: normal".
# GOTCHA: VRAM window: single small.en resident ≈ 0.5–3 GB → [512, 3072] MiB (the old two-model
#   [1024, 5120] window would spuriously FAIL the single-model arm at the low end and admit a
#   two-model regression at the high end).
# GOTCHA: small.en finals bar is ≥0.70 fuzzy (PRD §6 T7b) — the old ≥0.80 was the distil-large-v3
#   bar; keeping 0.80 for test_feed_audio finals invites flaky failures on espeak fixtures.
# GOTCHA: tests/test_voicectl.py asserts import purity — test_feed_audio.py must keep heavy deps
#   lazily imported inside fixtures (never at module top level).
# GOTCHA: scratch files: the shell suite mktemp -d's under /tmp (tmpfs = RAM) and its trap removes
#   them — do not add unbounded `>> file` loops of your own anywhere.
```

## Implementation Blueprint

### Data models and structure

None — this item changes tests + documentation only. No config, schema, or production-code changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT tests/test_feed_audio.py — collapse the fixtures + rewrite the two stale tests
  - DELETE the `lite_recorder` fixture (L311–348) entirely (its cfg_to_kwargs(cfg, lite=True)
    call is a TypeError against the current signature).
  - KEEP the `recorder` fixture (L253) as the single-model fixture — it already produces the
    collapsed kwargs; UPDATE its header comment to state the single-model reality (model ==
    realtime_model_type == lite_model, use_main_model_for_realtime=True, endpointer =
    lite_post_speech_silence_duration=0.8 default).
  - REWRITE test_lite_feed_audio_utt_simple (L653) → rename to test_single_model_construction
    (or similar): assert on the FILTERED kwargs that use_main_model_for_realtime is True and
    model == realtime_model_type (one construction, no second model), then feed utt_simple.wav
    via the existing _run_utterance harness and assert finals fuzzy ≥0.70 vs the pinned
    "the quick brown fox jumps over the lazy dog" reference (small.en bar, PRD §6 T7b).
    Keep the CUDA skip-guard framing ("real-model integration test").
  - REWRITE test_lite_latency_lower_than_normal (L679) → DELETE the lite-vs-normal comparison
    (no normal mode exists); REPLACE with a single-model latency test (e.g.
    test_single_model_final_latency_within_budget) reusing _final_latency_ms best-of-3 on the
    `recorder` fixture and asserting ≤1500 ms (the PRD §6 T1e budget; small.en is faster than
    the old final model, so the budget holds on GPU; keep the existing G-CPU skip rationale).
  - FIX the fuzzy bar in test_fuzzy_accuracy (L447): 0.80 → 0.70, with a comment citing PRD §6
    T7b (small.en is the final model post-collapse). Sweep the file for any other ≥0.80 finals
    asserts on feed_audio finals and lower them to 0.70 the same way (do NOT touch
    tests/test_streaming.py — its 0.80 is typed-screen-content vs pinned refs, a different,
    already-green contract).
  - UPDATE the module docstring / T7 section banner (L305-309) to the single-model framing;
    grep the file for "lite" and "normal" afterwards — remaining hits must be comments about
    config key names (lite_model, lite_post_speech_silence_duration) only, never mode switches.
  - NAMING/PLACEMENT: keep tests in this file, snake_case test_* names, existing fixture style.
  - VALIDATE: timeout 900 .venv/bin/python -m pytest tests/test_feed_audio.py -v   (bash-tool timeout 950)

Task 2: EDIT tests/test_idle_and_gpu.sh — replace the T7 block with single-model assertions
  - WIDEN the VRAM window: L137-138 → VRAM_MIN_MIB=512 / VRAM_MAX_MIB=3072 (single small.en
    ≈ 0.5–3 GB; update the trailing comments accordingly).
  - DELETE the T7 lite mode-switch roundtrip block (banner L535 through the final
    `voicectl stop >/dev/null 2>&1 || true` at ~L631) — every `toggle-lite` / `mode: normal`
    reference goes.
  - REPLACE it with a SINGLE-MODEL ASSERTION BLOCK (keep the T7_OK accumulator name so the final
    gate and result banner keep working; retitle the banner comment, e.g. "T7 (PRD §4.2quater +
    acceptance #10): single-model arming"). The block, re-using the existing helpers
    (voicectl(), vram_tree_state(), wait_vram_present()):
      1. voicectl start (re-arm; the resident host is already single-model) + wait_vram_present.
      2. ONE-MODEL (log): grep run-1 daemon.log for the startup line
         `voice-typing device resolved: device=cuda compute_type=float16 model=small.en` —
         PASS required; AND `grep -q 'distil-large-v3' run1_log` MUST NOT match (no large-model
         worker anywhere — the loader, cuda_check, and any worker line).
      3. ONE-MODEL (status): `voicectl status` → assert a `^mode: lite` line (constant mode,
         daemon.py:2128) while armed.
      4. VRAM window: assert_vram_present with the new 512–3072 window (this is the
         regenerated ~half-old-VRAM evidence for row #10).
      5. CANCEL SMOKE (row #12 shell evidence): while armed with NO tail in flight,
         `voicectl cancel` must return ok (exit 0), `listening` stays on, and it is a no-op
         (idempotent — PRD §4.2quater). Print a [PASS] line for it.
      6. voicectl stop to disarm (clean state before quit).
  - UPDATE the evidence block (~L700): replace the `T7 normal-armed VRAM` / `T7 lite-armed VRAM`
    echo lines with the new single-model outputs (e.g. `T7 one-model grep: small.en (no
    distil-large-v3)`, `T7 armed VRAM (single-model): <total> <pids>`, `T7 mode: lite`,
    `T7 cancel smoke: ok (no-op, listening on)`); update the block banner to list criteria
    5/6/8/9/10.
  - UPDATE the final result gate (~L737-745) banner text (e.g. "T7 single-model arming") — keep
    the IDLE_OK/T6_OK/T7_OK triple.
  - UPDATE the file header comments (L1-100): T7 description → single-model assertions; note
    the VRAM window change and the cancel smoke; keep all G-* gotcha annotations intact.
  - VALIDATE: bash-tool timeout 900, inner per-command timeouts already in the script; run from
    a quiet room AFTER `systemctl --user stop voice-typing` (preflight refuses otherwise):
      systemctl --user stop voice-typing 2>/dev/null || true
      ./tests/test_idle_and_gpu.sh          # ~5-8 min; do NOT interrupt mid-run
  - GOTCHA: if a FAIL surfaces a REAL production bug (e.g. two models resident, cancel not
    ok), STOP and report — do not weaken the assertion (standing rule in this script).

Task 3: EDIT tests/ACCEPTANCE.md — amend #4, rewrite #10, add #11/#12, regenerate evidence
  - HEADER: "criteria 1–10" → "criteria 1–12"; the regenerate instruction block "5 / 6 / 8 / 9 /
    10" already mentions 10 — verify and fix the prose.
  - ROW #4 (amend): keep the disarm-gate evidence; REPLACE the "streaming-typing evidence
    PENDING → P1.M3.T8/T9" clause with the landed evidence: tests/test_streaming.py
    test_a_delta_cadence (typed deltas ≥1/500 ms while speaking) + test_b_commit_rewind_exact
    (commits revise in place) LIVE on CUDA; nothing-typed-while-off stays the mocked listening
    gate (tests/test_daemon.py) + E2E CRIT4 STATIC.
  - ROW #10 (rewrite, Status → PASS with regenerated evidence): single-model arming only —
    small.en is the sole model (one-model log grep + no distil-large-v3, from the regenerated
    shell block), armed VRAM within 0.5–3 GB on nvidia-smi (the regenerated T7 line), silence
    gate = lite_post_speech_silence_duration (default 0.8), drain unchanged (29 mocked drain
    tests in tests/test_daemon.py — the shell test cannot prove drain without speech), status +
    state.json report mode (constant "lite"). Note explicitly that the old T7 ≥70% finals bar
    is subsumed by tests/test_streaming.py's ≥0.80 typed-content asserts (same real small.en).
  - ROW #11 (ADD — streaming, PRD §7 #11): clauses → tests/test_streaming.py:
    test_a_delta_cadence (≥1 update/500 ms), test_b_commit_rewind_exact (in-place commits),
    test_c_pause_join (no mid-paragraph capital / no spurious trailing period), test_e_cancel
    (Backspace mid-fragment cancels, mic stays armed), test_g_stranded_tail (stranded fragments
    freeze, never auto-delete), rollback hatch → tests/test_daemon.py
    test_on_final_streaming_false_is_verbatim_rev1_hatch (:4510) + test_streaming_commit.py
    disabled-engine commit no-op (:304-308) for output.streaming=false restoring Rev 1.
    Status: PASS (LIVE, CUDA-gated suite; cite the passing `timeout 900 … pytest
    tests/test_streaming.py -v` run).
  - ROW #12 (ADD — cancel fallback, PRD §7 #12): socket cancel performs the identical rewind →
    tests/test_streaming.py test_e_cancel (asserts press_backspace(len(tail)−1), buffered audio
    dropped, listening stays on; second cancel is a no-op) + tests/test_control_socket.py cancel
    cmd coverage; evdev-unavailable fallback → `voicectl cancel` armed no-op smoke from the
    regenerated shell evidence block; listener-failure-logged-once-at-arm → cite the existing
    listener tests (grep tests/test_key_listener.py + tests/test_daemon.py for the exact test
    names BEFORE writing them into the row — never cite a test name you have not grepped).
  - EVIDENCE BLOCK: paste the REGENERATED `=== ACCEPTANCE EVIDENCE ===` output from the Task-2
    shell run verbatim (it replaces the "pre-Rev-2 historical capture"); update the block's
    descriptive template above it: drop the stale `models: distil-large-v3 + small.en (loaded)`
    line (status no longer prints models — use the actual device/mic/context-prompt lines), and
    refresh the bottom "Per-criterion PASS lines" sample to the new script output.
  - METHOD NOTES: update the T6 VRAM window mention ([1024,5120] → [512,3072]) and the T7
    description (mode-switch → single-model assertions + cancel smoke).
  - VALIDATE: every test/command name cited in a row must grep-clean in the repo, e.g.:
      grep -rn "test_on_final_streaming_false_is_verbatim_rev1_hatch" tests/test_daemon.py
      grep -n "test_e_cancel" tests/test_streaming.py
      grep -c "toggle-lite\|mode: normal\|lite_recorder" tests/test_idle_and_gpu.sh tests/test_feed_audio.py   # → 0

Task 4: FULL VALIDATION PASS (see Validation Loop below)
  - Run the fast pytest sweep, the CUDA suites, and (once, quiet room) the shell suite; confirm
    ACCEPTANCE.md citations; `git diff --stat` must show ONLY tests/* (+ optional validate.sh).

Task 5: COMMIT
  - Commit with a message like "Sync idle/GPU + feed-audio suites and acceptance rows to the
    single-mode streaming world". Do not touch PRD.md / tasks.json / plan snapshots (read-only).

Task 6 (OPTIONAL, one line, justified by the item OUTPUT "all suites green"): EDIT validate.sh
  - Phase 2's pytest list is missing tests/test_context_prompt_refresh.py (landed after
    validate.sh was written — verify: file mtime/git log vs 1022277). Add it to the phase-2 list
    if (and only if) it is still absent, so the standard runner executes every fast suite.
    Do NOT add tests/test_streaming.py to phase 3 — the CUDA T8 suite has its own 900 s runner
    command and is out of this item's contract.
```

### Implementation Patterns & Key Details

```bash
# PATTERN: single-model log grep (Task 2, step 2) — the startup line fires ONCE at daemon start
# (driver probe; independent of the lazy first-arm model load), so it is present in run-1's log:
grep -m1 'voice-typing device resolved: device=cuda compute_type=float16 model=small.en' "$RUN1_LOG" \
  || { echo "[FAIL] T7 one-model: startup line missing/wrong model"; T7_OK=1; }
if grep -q 'distil-large-v3' "$RUN1_LOG"; then
  echo "[FAIL] T7 one-model: distil-large-v3 appeared in daemon.log (two-model regression)"; T7_OK=1
else
  echo "[PASS] T7 one-model: small.en sole model (no distil-large-v3 anywhere in daemon.log)"
fi

# PATTERN: cancel smoke (Task 2, step 5) — cancel while armed with NO tail in flight is the
# documented idempotent no-op (PRD §4.2quater); always through the timeout-wrapping helper:
if voicectl cancel >/dev/null 2>&1 \
   && "$VOICECTL" status 2>/dev/null | grep -q '^listening: on'; then
  echo "[PASS] T7 cancel smoke: voicectl cancel ok (no-op, no tail in flight), listening stays on"
else
  echo "[FAIL] T7 cancel smoke: cancel failed or disarmed the mic"; T7_OK=1
fi
# NOTE: use the raw "$VOICECTL" for status (lock-free, never hangs) but the `voicectl` wrapper
# for cancel — mirror the existing convention in the script.

# PATTERN: fuzzy-bar comment (Task 1):
#   # small.en is the final model post-collapse -> PRD §6 T7b bar is >=0.70 (the old 0.80 was
#   # the distil-large-v3 bar from PRD §6 T1d, written when a second model existed).
#   assert best >= 0.70, ...

# GOTCHA: keep every [PASS]/[FAIL] line format + the T7_OK accumulator + the evidence echo line
# so the final gate (IDLE_OK/T6_OK/T7_OK) and the ACCEPTANCE.md paste remain coherent.
```

### Integration Points

```yaml
TESTS:        # the only integration surface — no production code changes
  - tests/test_idle_and_gpu.sh: T7 block replaced; VRAM window 512-3072; evidence block regenerated
  - tests/test_feed_audio.py: lite_recorder deleted; 2 tests rewritten; fuzzy bar 0.80 -> 0.70
  - tests/ACCEPTANCE.md: 12 rows; regenerated evidence block; stale `models:` line removed
CONFIG:       # none — config schema unchanged by this item
DOCS:         # tests/ACCEPTANCE.md is the deliverable doc (PRD §7 Mode A list names it)
OPTIONAL:     # validate.sh phase-2 list += tests/test_context_prompt_refresh.py (one line)
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m ruff check tests/test_feed_audio.py --fix || true   # bash-tool timeout 150
timeout 120 .venv/bin/ruff format --check tests/ 2>/dev/null || true               # repo has no formatter config; ruff check is the gate validate.sh uses
bash -n tests/test_idle_and_gpu.sh                                                  # shell syntax (bash-tool timeout 30)
# Expected: no new lint errors on the edited file; bash -n silent.
```

### Level 2: Unit / Offline ASR Suites

```bash
# Fast sweep (no CUDA load; heavy files skip-guard) — bash-tool timeout 350:
timeout 300 .venv/bin/python -m pytest tests/test_config.py tests/test_textproc.py \
  tests/test_daemon.py tests/test_voicectl.py tests/test_control_socket.py \
  tests/test_key_listener.py tests/test_streaming_commit.py -q

# The rewritten offline ASR suite (real CUDA models) — bash-tool timeout 950:
timeout 900 .venv/bin/python -m pytest tests/test_feed_audio.py -v

# T8 evidence suite re-run (rows #4/#10/#11/#12 cite it; confirm still green) — bash-tool timeout 950:
timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v

# Expected: all green. test_feed_audio must show the renamed single-model tests passing and
# ZERO collection/use of lite_recorder.
```

### Level 3: The Heavy Shell Suite (system validation + evidence regeneration)

```bash
# PRECONDITIONS: quiet room (120 s armed silence on the REAL default mic); unit stopped.
systemctl --user stop voice-typing 2>/dev/null || true
./tests/test_idle_and_gpu.sh        # bash-tool timeout 900; ~5-8 min; do NOT interrupt mid-run
# Expected: exit 0; final banner === IDLE+GPU PASS (criteria 5, 6, 8; T6 a/b/c/d lifecycle; T7
# single-model arming) ===; the printed === ACCEPTANCE EVIDENCE === block gets pasted verbatim
# into tests/ACCEPTANCE.md (Task 3). If exit != 0: read the printed daemon.log tails; a FAIL on
# the one-model grep / VRAM window / cancel smoke is a PRODUCTION regression — report, do not
# weaken. If anything wedged (a timeout 124 on voicectl): run the AGENTS.md cleanup block before
# any retry.
```

### Level 4: Cross-Reference & Scope Validation

```bash
# No stale references remain — bash-tool timeout 30:
grep -n "toggle-lite\|start-lite\|mode: normal\|lite_recorder\|lite=True" \
  tests/test_idle_and_gpu.sh tests/test_feed_audio.py tests/ACCEPTANCE.md   # expect: no matches (or config-key-name comments only)
# Every cited test name exists — bash-tool timeout 30:
grep -rn "test_on_final_streaming_false_is_verbatim_rev1_hatch" tests/test_daemon.py
grep -n  "def test_a_delta_cadence\|def test_b_commit_rewind_exact\|def test_c_pause_join\|def test_e_cancel\|def test_g_stranded_tail" tests/test_streaming.py
# Production code untouched — bash-tool timeout 30:
git diff --stat    # only tests/* (+ validate.sh if Task 6 taken)
# Optional standard runner (phases 1-3) — bash-tool timeout 900:
timeout 850 ./validate.sh
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1: `ruff check` clean on edited Python; `bash -n` clean on the shell script.
- [ ] Level 2: fast sweep green; `tests/test_feed_audio.py` green on CUDA; `tests/test_streaming.py` re-run green.
- [ ] Level 3: `./tests/test_idle_and_gpu.sh` exit 0 (quiet room, unit stopped first, harness timeout 900).
- [ ] Level 4: stale-reference grep returns nothing; all ACCEPTANCE-cited test names grep-clean; `git diff --stat` shows only tests/* (+ optional validate.sh).

### Feature Validation

- [ ] Shell suite asserts: one-model log grep + no-distil grep + `mode: lite` + VRAM ∈ [512,3072] MiB + cancel armed no-op.
- [ ] test_feed_audio: single-construction asserts (use_main_model_for_realtime, model == realtime_model_type), finals ≥0.70 fuzzy, latency ≤1500 ms best-of-3.
- [ ] ACCEPTANCE.md: 12 rows; #4/#10 updated; #11/#12 added; regenerated evidence block pasted; stale `models:` line gone.
- [ ] No production file under `voice_typing/` modified.

### Code Quality Validation

- [ ] Existing G-* gotcha comments and [PASS]/[FAIL] + accumulator + evidence-echo conventions preserved in the shell script.
- [ ] Fixture style (lazy deps, skip-guards, `_safe_shutdown` teardown) preserved in test_feed_audio.py.
- [ ] No new top-level heavy imports (import-purity check in test_voicectl.py stays green).

### Documentation & Deployment

- [ ] ACCEPTANCE.md method notes match the new script behavior (VRAM window, single-model block, cancel smoke).
- [ ] Commit lands on `main` with a descriptive message; PRD.md / tasks.json / plan snapshots untouched.

## Anti-Patterns to Avoid

- ❌ Don't "fix" a failing GPU/lifecycle assertion by widening ranges or deleting checks — a FAIL there is a production regression to report (the script itself says so).
- ❌ Don't run `voicectl` without `timeout 30`, the daemon in the foreground, or the shell suite with a harness timeout < 900 (AGENTS.md hard rules).
- ❌ Don't interrupt the shell suite mid-run (it manages its own daemon + trap; an abort leaves state to clean up).
- ❌ Don't cite a test name in ACCEPTANCE.md that you haven't grepped in this session.
- ❌ Don't keep a ≥0.80 finals bar for small.en feed-audio finals (stale distil bar → flaky); don't touch test_streaming.py's 0.80 (different contract, already green).
- ❌ Don't add `lite=True` anywhere — the kwarg is gone; don't reintroduce `toggle-lite`/`mode: normal` anywhere.
- ❌ Don't edit `voice_typing/*`, `PRD.md`, `tasks.json`, or plan snapshots — tests + ACCEPTANCE.md (+ optional validate.sh one-liner) only.

---

**Confidence Score: 9/10** — every stale reference is pinned to file+line, every replacement
assertion has a source-of-truth citation, and the validation commands are the repo's own proven
runners with AGENTS.md-compliant timeouts. The residual risk is hardware variance in the VRAM
window on the regenerated run (mitigated: 512–3072 MiB is deliberately wide) and ambient-noise
flakes in the 120 s quiet-room window (mitigated: precondition stated in three places).

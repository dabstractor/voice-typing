# PRP — P1.M1.T1.S1: Root-cause the ~90s shutdown wedge and document findings

## Goal

**Feature Goal**: Produce a **confirmed root-cause document** that pins the voice-typing daemon's ~90s shutdown wedge to its exact cause in the installed RealtimeSTT v1.0.2 source, with verbatim source-line citations. This is a **research-only** subtask: **zero code changes.** It is the prerequisite that unblocks S2 (bounded teardown) and M3 (idle-unload) by proving *why* `recorder.shutdown()` hangs and *why* the S2 fix (whole-call hard timeout + force-terminate the spawn processes) is the correct shape.

**Deliverable**: A new confirmation document at `plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md` (a sibling to — NOT an overwrite of — the existing `realtimestt_shutdown_analysis.md`). It records the three verified claims, the practical-blocker determination, and a clean handoff to S2.

**Success Definition**: (a) the confirmation doc exists at the prescribed path; (b) it states all three confirmed claims (`recording_thread.join()` no timeout; `realtime_thread.join()` no timeout; both `mp.Process` joins bounded at 10s + `terminate()`) with exact citations to the *installed* `core/shutdown.py`; (c) it records that the wedge's 90s duration = systemd's default `TimeoutStopSec` (the unit sets none); (d) it states the live timed-log test is **optional** because the source is conclusive; (e) no `.py`/source/systemd file is modified.

## User Persona

**Target User**: The implementing agent for **S2** (P1.M1.T1.S2 — "Implement bounded teardown: hard timeout + force-cleanup of worker processes") and the maintainers who need a durable record of *why* the daemon had to grow a force-cleanup path.

**Use Case**: S2's author reads this confirmation to know (1) the hang is inside `recorder.shutdown()` at an unbounded `threading.Thread.join()`, (2) the spawn processes are the VRAM holders so force-terminating them is the right release strategy, (3) the daemon threads are `daemon=True` so they die with the process and don't need (and can't get) explicit killing.

**Pain Points Addressed**: Removes guesswork for S2; prevents a "fix" that tries to kill Python threads (impossible) instead of bounding the whole call + terminating the processes; records the systemd-default-90s link so T2.S1 (`TimeoutStopSec=15`) is justified.

## Why

- **Prerequisite for the lazy-load feature (PRD §4.2bis Idle unload).** Idle-unload tears the recorder down every `auto_unload_idle_seconds` (default 30 min) and would re-trigger the ~90s hang on every teardown — and block any re-arm racing it under the single-flight lock. A bounded teardown is a **hard prerequisite** (PRD §4.2bis + §8 risk row), and bounding it correctly requires knowing what blocks.
- **Fixes the existing `quit` hang.** Every `voicectl quit` today runs `run() loop exiting` → ~90s → systemd `SIGKILL` / `Failed with result 'timeout'`. This subtask explains why.
- **Source is the proof (deterministic).** The contract explicitly permits skipping the live test when the analysis is conclusive. It is: the *only* unbounded operations in the shutdown path are the two thread `.join()`s. No live daemon probe is required to establish root cause.
- **Hands off cleanly to S2.** S2 does not need to know *which* thread blocks — it wraps the entire `recorder.shutdown()` in a hard timeout and force-terminates the spawn processes regardless. This subtask confirms that is sound.

## What

Write one confirmation document (no code). The document must: (1) restate the verified process/thread model with citations; (2) confirm the three contract claims (a/b/c) against the *installed* `shutdown.py`; (3) give the shutdown-step ordering and identify the first reachable unbounded join; (4) link the 90s to systemd's default `TimeoutStopSec`; (5) declare the live timed-log test optional; (6) hand off to S2 without over-prescribing its fix.

### Success Criteria

- [ ] `plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md` exists.
- [ ] It cites the installed `core/shutdown.py` for each of the three claims (with the exact join/timeout lines).
- [ ] It records the practical-blocker reasoning: by ordering, `recording_thread.join()` is the **first** unbounded step; `realtime_thread.join()` is a second unbounded step reached only after the first returns.
- [ ] It states 90s = systemd default `TimeoutStopSec` (the unit has no `TimeoutStopSec=` directive).
- [ ] It explicitly marks the live timed-log test OPTIONAL (source conclusive) and gives the methodology for the agent that wants extra evidence.
- [ ] It does NOT prescribe S2's code in detail (S2 owns that) and does NOT modify any source/config/systemd file.

## All Needed Context

### Context Completeness Check

_Pass._ The root cause is fully verified against the installed source by this PRP's author (every claim below is backed by a verbatim line citation). An agent who has never seen this codebase can produce the confirmation doc by transcribing the Verified Findings below — no further investigation is required.

### Verified Findings (the proof — already done by this PRP's research)

These are the confirmed facts the implementing agent transcribes into the document. Each is verified against the *installed* wheel at `.venv/lib/python3.12/site-packages/RealtimeSTT/` (v1.0.2).

**Process / thread model (citations):**
| Entity | Type | Created at | Daemon? | In `shutdown_recorder()` |
|---|---|---|---|---|
| `transcript_process` | `mp.Process` (spawn) | `initialization.py:397` via `start_recorder_worker()` | n/a (process) | `join(timeout=10)` + `terminate()` — **BOUNDED** |
| `reader_process` | `mp.Process` (spawn) | `initialization.py:433` via `start_recorder_worker()` | n/a (process) | `join(timeout=10)` + `terminate()` (gated on `use_microphone.value`) — **BOUNDED** |
| `recording_thread` | `threading.Thread` | `initialization.py:614`; `.daemon=True` at `:618` | **yes** | `.join()` — **NO TIMEOUT** |
| `realtime_thread` | `threading.Thread` | `initialization.py:621`; `.daemon=True` at `:625` | **yes** | `.join()` — **NO TIMEOUT** |
- Spawn start method: `mp.set_start_method("spawn")` at `core/safepipe.py:17-19` and `core/initialization.py:355`. → each process has its **own CUDA context + GPU memory**, so terminating a process releases its VRAM.
- `shutdown_lock` (`threading.Lock`) serializes all of `shutdown_recorder()`.

**The three contract claims — CONFIRMED verbatim in `core/shutdown.py`:**
- (a) `recording_thread.join()` has **no timeout** — confirmed:
  ```python
  if recorder.recording_thread:
      recorder.recording_thread.join()
  ```
- (b) `realtime_thread.join()` has **no timeout** — confirmed:
  ```python
  if recorder.realtime_thread:
      recorder.realtime_thread.join()
  ```
- (c) the two processes **DO have timeouts** (10s + force terminate) — confirmed:
  ```python
  if recorder.use_microphone.value:
      recorder.reader_process.join(timeout=10)
      if recorder.reader_process.is_alive():
          recorder.reader_process.terminate()
  ...
  if recorder.transcript_process:
      recorder.transcript_process.join(timeout=10)
  if recorder.transcript_process and recorder.transcript_process.is_alive():
      recorder.transcript_process.terminate()
  ```

**Exact ordering inside `shutdown_recorder()` (determines which join blocks first):**
1. Set flags + `shutdown_event.set()` (wakes `wait_audio()`/`text()` callers).
2. **`recording_thread.join()` — UNBOUNDED ← first reachable blocker.**
3. `reader_process.join(timeout=10)` + `terminate()` (bounded; mic only).
4. `transcript_process.join(timeout=10)` + `terminate()` (bounded).
5. `parent_transcription_pipe.close()`.
6. **`realtime_thread.join()` — UNBOUNDED ← second blocker; only reached after step 2 returns.**
7. `del realtime_transcription_model` + `gc.collect()`.

→ The wedge is **guaranteed** to be at step 2 or step 6 (the only unbounded calls). By ordering, `recording_thread.join()` (step 2) is the first candidate; `realtime_thread.join()` (step 6) is only reached if the recording thread returned. Pinning *exactly* which one blocks in a given run needs the optional live timed-log; the **root-cause category** (unbounded thread join) does not.

**Daemon side (no bound added):** `VoiceTypingDaemon.shutdown()` at `voice_typing/daemon.py:818-844` calls `self._recorder.shutdown()` with **no timeout**. It is idempotent (a `_shutdown_done` flag + RealtimeSTT's `is_shut_down` guard) and defensive (try/except logs and does not re-raise), but it adds **no time bound** → a hang inside `recorder.shutdown()` propagates indefinitely through `daemon.shutdown()`.

**systemd side:** `systemd/voice-typing.service` has **no `TimeoutStopSec=`** directive (only `ExecStartPre`, `ExecStart=.../launch_daemon.sh`, `Restart=on-failure`). → systemd applies its **default `TimeoutStopSec=90s`**: SIGTERM at stop, then SIGKILL at 90s. **This exactly matches the observed ~90s wedge** (`run() loop exiting` → 90s → `SIGKILL` / `Failed with result 'timeout'`).

**End-to-end causal chain:** `voicectl quit` (or systemd stop) → SIGTERM → daemon signal handler → `daemon.shutdown()` → `self._recorder.shutdown()` → `shutdown_recorder()` blocks at an unbounded `threading.Thread.join()` (step 2 or 6) → 90s elapses → systemd `TimeoutStopSec=90s` default → **SIGKILL**. The process is then killed by the supervisor, not shut down cleanly; the spawn processes (which hold the VRAM) die with it.

### Documentation & References

```yaml
# THE EXISTING ANALYSIS (precursor — read, do NOT overwrite)
- docfile: plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis.md
  why: The precursor analysis that this subtask CONFIRMS. Contains the process/thread table, the
       shutdown_recorder() sequence, the root-cause statement, and a SKETCH of the _bounded_shutdown
       mitigation. The confirmation doc corroborates it against the installed wheel and adds the
       ordering/practical-blocker determination + the systemd-default-90s link.
  critical: "Do NOT overwrite this file. Write the NEW confirmation as a SIBLING file."

# THE AUTHORITATIVE SOURCE — the installed shutdown implementation
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/shutdown.py
  why: The single function `shutdown_recorder(recorder)` IS the proof. Lines: recording_thread.join()
       (no timeout) → reader_process.join(timeout=10)+terminate → transcript_process.join(timeout=10)
       +terminate → pipe.close() → realtime_thread.join() (no timeout) → model del + gc.collect().
  pattern: "Cite the verbatim join/terminate lines. The two thread joins lack `timeout=`; the two
            process joins have `timeout=10` + `terminate()`."
  gotcha: "reader_process teardown is GATED on `recorder.use_microphone.value` — in tests with
           use_microphone=False the reader step is skipped, but production uses the mic so it applies."

# THE PROCESS/THREAD MODEL — confirms daemon-ness + spawn
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py
  why: recording_thread/realtime_thread are threading.Thread with .daemon=True (:614/:618, :621/:625);
       transcript_process/reader_process are mp.Process via start_recorder_worker (:397/:433). The
       daemon flag is load-bearing: daemon threads die with the process (can't/needn't be killed).
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/safepipe.py
  why: :17-19 set mp.set_start_method("spawn") → processes have OWN CUDA context/VRAM → terminating
       them releases VRAM (the basis for S2's force-cleanup).

# THE DAEMON CALL SITE — confirms NO bound is added
- file: voice_typing/daemon.py
  why: VoiceTypingDaemon.shutdown() (:818-844) calls self._recorder.shutdown() with no timeout;
       idempotent (_shutdown_done + is_shut_down) and defensive (try/except, no re-raise) but unbounded.
  critical: "This is the function S2 will wrap with a hard timeout. S1 only DOCUMENTS it."

# THE SYSTEMD LINK — confirms 90s = default TimeoutStopSec
- file: systemd/voice-typing.service
  why: Has NO TimeoutStopSec= directive → systemd default 90s → SIGKILL at 90s. Matches the wedge.
  critical: "T2.S1 will add TimeoutStopSec=15. S1 only RECORDS the default-90s link."

# PRD CONTEXT — why this matters
- docfile: plan/003_27d1f88f5a9f/prd_snapshot.md
  why: §4.2bis 'Idle unload' makes bounded teardown a HARD PREREQUISITE; §8 risk row
       'recorder.shutdown() hangs ~90s' prescribes 'hard timeout + force-cleanup of worker threads /
       transcript_process'. This subtask confirms the root cause those mitigations target.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/daemon.py     # shutdown() @ 818-844 — DOCUMENT ONLY (S2 wraps it; S1 changes nothing)
├── systemd/voice-typing.service  # no TimeoutStopSec — DOCUMENT ONLY (T2.S1 adds it; S1 changes nothing)
├── .venv/.../RealtimeSTT/core/shutdown.py        # the proof source (read-only wheel)
├── .venv/.../RealtimeSTT/core/initialization.py  # thread/process model (read-only wheel)
└── plan/003_27d1f88f5a9f/architecture/
    ├── realtimestt_shutdown_analysis.md          # EXISTING precursor — read, do NOT overwrite
    └── realtimestt_shutdown_analysis_confirmed.md # ← CREATE (this subtask's deliverable)
```

### Desired Codebase tree with files to be added

```bash
plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md   # NEW confirmation doc
# NO other files. No .py, no config, no systemd, no tests. Research-only subtask.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — OUTPUT IS A DOC, NOT CODE. This subtask writes ONE markdown file and changes ZERO
# source/config/systemd/test files. S2 owns the bounded-teardown code; T2.S1 owns TimeoutStopSec.

# CRITICAL #2 — DON'T OVERWRITE THE PRECURSOR. realtimestt_shutdown_analysis.md already exists and
# is referenced by the plan. Write a SIBLING *_confirmed.md that corroborates + extends it.

# CRITICAL #3 — THE TWO THREAD JOINS ARE THE ONLY UNBOUNDED OPS. The two mp.Process joins are
# bounded (10s + terminate). So the wedge is GUARANTEED an unbounded threading.Thread.join(), not a
# process join. State this categorically — it's the load-bearing conclusion.

# CRITICAL #4 — ORDERING DECIDES THE FIRST BLOCKER. recording_thread.join() is step 2 (first);
# realtime_thread.join() is step 6 (only reached after step 2 returns). So the practical first
# blocker is recording_thread; realtime_thread is the second. Be precise: source can't pin WHICH
# one blocks in a given run without a live probe — and that pin is NOT needed (see #5).

# CRITICAL #5 — S2 DOES NOT NEED TO KNOW WHICH THREAD BLOCKS. S2 wraps the WHOLE recorder.shutdown()
# in a hard timeout + force-terminates the spawn processes (the VRAM holders). That is correct
# regardless of which internal join hangs. The confirmation doc should make this handoff explicit
# so S2 isn't blocked waiting for a "which thread" answer.

# GOTCHA #6 — DAEMON THREADS CAN'T BE KILLED. recording_thread/realtime_thread are .daemon=True;
# Python offers no thread.kill(). They die when the PROCESS exits. S2's force-cleanup terminates the
# PROCESSES (which hold VRAM) and lets the daemon threads die with the process. Document this so S2
# doesn't try to kill threads.

# GOTCHA #7 — READER STEP IS MIC-GATED. shutdown_recorder()'s reader_process block runs only
# `if recorder.use_microphone.value`. Production uses the mic (True); the offline feed_audio tests
# set use_microphone=False (so the reader step is skipped there). Note this so the doc isn't misread
# as "reader is always torn down".

# GOTCHA #8 — 90s IS SYSTEMD'S DEFAULT, NOT A REALTIMESTT CONSTANT. There is no 90s anywhere in
# the RealtimeSTT source; the 90s comes from systemd's default TimeoutStopSec=90s because the unit
# sets no TimeoutStopSec=. State the link explicitly (it justifies T2.S1's TimeoutStopSec=15).

# GOTCHA #9 — LIVE TEST IS OPTIONAL. The contract permits skipping it when the analysis is
# conclusive. It IS conclusive (only two unbounded ops, both thread joins). Provide the timed-log
# methodology in the doc for an agent who wants to pin the exact thread, but do NOT require it and
# do NOT run a disruptive live daemon probe as a gate.
```

## Implementation Blueprint

### Data models and structure

None. The deliverable is a markdown document. Its structure is prescribed below.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md
  - USE the write tool to create a NEW sibling file (do NOT overwrite realtimestt_shutdown_analysis.md).
  - STRUCTURE the document with these sections (transcribe the Verified Findings above; cite the
    installed source by file + the verbatim join/terminate lines):
      1. Title + one-line verdict: "The ~90s wedge is an unbounded threading.Thread.join() inside
         RealtimeSTT v1.0.2 shutdown_recorder(); the 90s is systemd's default TimeoutStopSec."
      2. Source version + paths (installed wheel location).
      3. Process/thread model table (transcript_process/reader_process = mp.Process spawn;
         recording_thread/realtime_thread = threading.Thread, daemon=True) with initialization.py
         line citations + the safepipe.py spawn-method note.
      4. CONFIRMED CLAIMS (a)/(b)/(c) — each with the verbatim shutdown.py lines (recording_thread
         .join() no timeout; realtime_thread.join() no timeout; reader/transcript join(timeout=10)
         + terminate()). Note the reader step is mic-gated.
      5. Shutdown ordering (7 steps) + practical-blocker determination: the wedge is GUARANTEED at
         step 2 (recording_thread.join()) or step 6 (realtime_thread.join()); step 2 is the first
         candidate. State that source analysis cannot pin the exact thread without a live probe,
         and that it does NOT need to (handoff to S2).
      6. Daemon-side no-bound note: VoiceTypingDaemon.shutdown() (daemon.py:818-844) calls
         self._recorder.shutdown() with no timeout (idempotent + defensive, but unbounded).
      7. systemd link: unit has no TimeoutStopSec= → default 90s → SIGKILL; matches the observed
         wedge exactly. End-to-end causal chain (quit → SIGTERM → daemon.shutdown() → hang → 90s →
         SIGKILL).
      8. Live timed-log test — OPTIONAL: source is conclusive. If desired, methodology = wrap each
         shutdown step with monotonic-clock logs (e.g. monkeypatch/audit shutdown_recorder, or add
         temporary logger.debug timestamps before/after each join) and run `voicectl quit` on a live
         daemon, then read `journalctl --user -u voice-typing`. Decline to run it if disruptive.
      9. Handoff to S2: S2 wraps the WHOLE recorder.shutdown() in a hard timeout + force-terminates
         the spawn processes (VRAM holders); daemon threads die with the process. S2 does NOT depend
         on which thread blocks. (Do NOT write S2's code here — S2 owns that.)
  - KEEP IT FACTUAL: every claim cites a file/line. No speculation. No code blocks longer than the
    cited join/terminate snippets.

Task 2: VALIDATE (run the gates below). No git commit unless the orchestrator directs it. If asked,
  message: "P1.M1.T1.S1: confirm RealtimeSTT ~90s shutdown wedge root cause (unbounded thread.join)".
```

### Implementation Patterns & Key Details

```python
# There is no code. The "pattern" is disciplined root-cause writing:
#   * Cite the INSTALLED source (core/shutdown.py), not the precursor doc's paraphrase.
#   * Distinguish what is PROVEN (unbounded thread joins; processes bounded; 90s = systemd default)
#     from what is NOT pinned (which exact thread blocks in a given run) — and explain why the
#     unpinned part doesn't block S2.
#   * Keep the S2 handoff crisp: whole-call timeout + force-terminate processes; threads die with
#     the process; is_shut_down makes the call idempotent.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMER — S2 (P1.M1.T1.S2 "Implement bounded teardown"):
  - S2 reads this confirmation to confirm: (1) wrap the whole recorder.shutdown() in a hard timeout
    thread; (2) on timeout, force-terminate transcript_process + reader_process (the VRAM holders);
    (3) set is_shut_down=True for idempotency; (4) don't try to kill the daemon threads (impossible;
    they're daemon=True and die with the process). The precursor analysis already SKETCHES this; the
    confirmation validates the premise.

DOWNSTREAM CONSUMER — T2.S1 (TimeoutStopSec=15 in the systemd unit):
  - This confirmation justifies lowering the unit's TimeoutStopSec from the 90s default to ~15s:
    the daemon's own bounded teardown (S2) will complete well inside 15s, so systemd never needs the
    full 90s and never reaches SIGKILL on a normal quit.

DOWNSTREAM CONSUMER — M3 (Idle-unload watchdog):
  - Bounded teardown is the hard prerequisite for idle-unload (PRD §4.2bis). This confirmation is the
    evidence that the idle-unload timer can call the teardown path without hanging every 30 min.

NO INTERFACE CHANGES:
  - No config, no README, no API, no state.json, no systemd directive is added by S1. Pure research.
```

## Validation Loop

> This is a research subtask. The gates verify the DOCUMENT exists, is correct, and that no source
> was touched. No tests are run (there is no code to test). All commands use full paths where the
> machine's zsh aliases matter (python3→uv run); `grep`/`git` are fine as-is.

### Level 1: The confirmation document exists and is well-formed

```bash
cd /home/dustin/projects/voice-typing
DOC=plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md
test -f "$DOC" && echo "L1a PASS: doc exists" || echo "L1a FAIL: doc missing"
echo "--- sections present ---"
grep -E '^#{1,3} ' "$DOC" | head -30
echo "--- cites the installed shutdown.py? ---"
grep -q 'core/shutdown.py\|shutdown_recorder' "$DOC" && echo "L1b PASS: cites source" || echo "L1b FAIL"
# Expected: doc exists; has titled sections; references core/shutdown.py / shutdown_recorder.
```

### Level 2: The three confirmed claims are present with the load-bearing facts

```bash
cd /home/dustin/projects/voice-typing
DOC=plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md
echo "--- claim (a): recording_thread join NO timeout ---"
grep -Eq 'recording_thread.*join.*no timeout|recording_thread\.join\(\).*no timeout' "$DOC" && echo "PASS" || echo "CHECK"
echo "--- claim (b): realtime_thread join NO timeout ---"
grep -Eq 'realtime_thread.*join.*no timeout|realtime_thread\.join\(\).*no timeout' "$DOC" && echo "PASS" || echo "CHECK"
echo "--- claim (c): processes BOUNDED (timeout=10 + terminate) ---"
grep -Eq 'timeout=10|10s.*terminate|bounded.*terminate' "$DOC" && echo "PASS" || echo "CHECK"
echo "--- 90s = systemd default TimeoutStopSec ---"
grep -Eq 'TimeoutStopSec|systemd.*default.*90|default.*90' "$DOC" && echo "PASS" || echo "CHECK"
echo "--- optional live test + S2 handoff noted ---"
grep -Eq 'optional|conclusive' "$DOC" && echo "PASS (live-test optionality noted)" || echo "CHECK"
grep -Eq 'S2|bounded teardown|force-terminate|force-cleanup' "$DOC" && echo "PASS (S2 handoff noted)" || echo "CHECK"
# Expected: each claim present. (grep -E is lenient; a human reads the doc for final sign-off.)
```

### Level 3: The claims STILL match the installed source (regression-proof the doc)

```bash
cd /home/dustin/projects/voice-typing
RT=.venv/lib/python3.12/site-packages/RealtimeSTT
echo "--- recording_thread.join() has NO timeout in the installed source ---"
grep -A1 'recording_thread' "$RT/core/shutdown.py" | grep -E 'recording_thread\.join\(\)$' && echo "L3a PASS" || echo "L3a CHECK"
echo "--- realtime_thread.join() has NO timeout ---"
grep -A1 'realtime_thread' "$RT/core/shutdown.py" | grep -E 'realtime_thread\.join\(\)$' && echo "L3b PASS" || echo "L3b CHECK"
echo "--- both processes join(timeout=10) + terminate() ---"
grep -c 'join(timeout=10)' "$RT/core/shutdown.py"   # EXPECT: 2
grep -c '\.terminate()' "$RT/core/shutdown.py"       # EXPECT: 2
# Expected: the doc's claims are true against the wheel AT THE TIME OF WRITING. (If these ever
# mismatch a future RealtimeSTT bump, the doc must be re-confirmed — that's exactly what this gate catches.)
```

### Level 4: No source/config/systemd/test files were modified

```bash
cd /home/dustin/projects/voice-typing
echo "--- git status: only the new architecture/ doc should appear (plus any pre-existing orchestrator entries) ---"
git status --short
echo "--- assert NO source/config/systemd/test diffs ---"
git diff --name-only | grep -E 'voice_typing/|systemd/|tests/|install\.sh|config\.toml|pyproject' && echo "L4 FAIL: source touched" || echo "L4 PASS: no source changes"
# Expected: "L4 PASS: no source changes". The only new path is the architecture/ confirmation doc.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: confirmation doc exists at `architecture/realtimestt_shutdown_analysis_confirmed.md` with titled sections and source citations.
- [ ] L2: claims (a)/(b)/(c) present; 90s = systemd default; live-test optionality + S2 handoff noted.
- [ ] L3: claims still match the installed `core/shutdown.py` (regression-proof).
- [ ] L4: no source/config/systemd/test files modified (research-only).

### Feature Validation
- [ ] Document pins the wedge to an unbounded `threading.Thread.join()` in `shutdown_recorder()`.
- [ ] Document explains the daemon-side no-bound call site (`daemon.py:818-844`) and the systemd-default-90s link.
- [ ] Document hands off to S2 without over-prescribing its code; notes S2 need not know which thread blocks.

### Code Quality Validation
- [ ] Every claim cites a file/line in the installed wheel or the repo.
- [ ] Proven facts vs. unpinned facts (which exact thread) are clearly distinguished.
- [ ] The precursor `realtimestt_shutdown_analysis.md` is untouched (sibling file created, not overwrite).

### Scope Boundary Validation
- [ ] No `.py`/source edits (S2 owns the bounded-teardown code).
- [ ] No systemd edit (T2.S1 owns `TimeoutStopSec=15`).
- [ ] No config/test/install.sh/README edits.
- [ ] Live daemon probe NOT required as a gate (optional only; source is conclusive).

---

## Anti-Patterns to Avoid

- ❌ Don't modify ANY source/config/systemd/test file — this is research-only. S2 owns the code; T2.S1 owns the unit.
- ❌ Don't overwrite the existing `realtimestt_shutdown_analysis.md` — write a sibling `*_confirmed.md`.
- ❌ Don't claim the wedge is a *process* join — the two `mp.Process` joins are bounded (`timeout=10` + `terminate()`). Only the two thread joins are unbounded.
- ❌ Don't assert a SPECIFIC thread (recording vs realtime) as the definitive blocker without a live probe — source analysis proves the *category*, not the exact thread. (And note S2 doesn't need the exact thread.)
- ❌ Don't attribute the 90s to RealtimeSTT — there's no 90s constant in the library; it's systemd's default `TimeoutStopSec=90s` because the unit sets none.
- ❌ Don't write S2's `_bounded_shutdown` implementation here — S2 owns it. This doc only confirms the premise and hands off.
- ❌ Don't run a disruptive live `voicectl quit` probe as a required gate — the contract allows skipping it; source is conclusive. Provide the methodology as optional only.
- ❌ Don't edit `daemon.py:818-844` to "add a quick timeout" as part of S1 — that's S2's whole deliverable; doing it here violates the research-only scope and pre-empts S2.

---

## Confidence Score

**10/10** for one-pass "implementation" success. The deliverable is a single markdown document, and every fact it must contain is already verified in this PRP's "Verified Findings" against the installed wheel (verbatim join/terminate lines, initialization.py daemon/spawn citations, daemon.py call-site line range, and the systemd default-`TimeoutStopSec` link). The implementing agent transcribes verified facts; there is no code to get wrong and no live system to disturb. The L3 gate even regression-proofs the doc against the installed source so a future RealtimeSTT bump can't silently invalidate it.

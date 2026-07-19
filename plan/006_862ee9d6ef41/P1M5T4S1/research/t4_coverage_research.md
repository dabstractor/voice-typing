# Research — P1.M5.T4.S1: T4 (idle stability) coverage audit

**Method:** STATIC read of `tests/test_idle_and_gpu.sh` + `tests/test_daemon.py` + the mitigation
source (`textproc.py`, `config.toml`, `daemon.py`). NO shell-script run (it loads CUDA ~5-8 min;
owned-out-of-this-item anyway). The mocked pytest command IS run (fast, CUDA-free).

## 1. What T4 requires (PRD §6 T4 / Acceptance #5)

With the daemon listening (armed) and 120 s of silence (no playback), assert ALL THREE:
- (a) **no finals typed** — the hallucination guard works (catches Whisper's silence-hallucination).
- (b) **no crash** — daemon still alive at end of window.
- (c) **CPU < 25 % of ONE core** on average (`pidstat` OR `/proc` sampling — do NOT divide by nproc).

Acceptance #5 wording: "Daemon survives ≥2 min of silence with no hallucinated output and trivial
CPU use."

## 2. Coverage matrix (the audit's core answer)

| T4 sub-check | `test_idle_and_gpu.sh` (RUN 1, real CUDA) | `test_daemon.py` (mocked, CUDA-free) | verdict |
|---|---|---|---|
| (a) no hallucinated finals | ✅ **L473-509**: `IDLE_SECS=120` (L147); capture-pane UNCHANGED (`typed_before==typed_after`) **AND** state.json `last_final` UNCHANGED (`jq -r .last_final`, double-signal). | ⚠️ **logic-only**: `test_on_final_rejects_hallucination` (L667 — feeds "thank you." → `be.typed==[]`); `test_on_final_rejected_hallucination_emits_no_latency_line` (L1532). Proves the blocklist GUARD, not the 120 s real-silence end-to-end. | COVERED (shell = end-to-end; unit = guard logic) |
| (b) CPU < 25 % one core | ✅ **L517-525 + `cpu_tree_seconds()` L176-211**: `/proc/<pid>/stat` fields 14/15 (utime+stime) summed over the PROCESS TREE (`/proc/<pid>/task/<pid>/children` recursive walk) ÷ `CLK_TCK`. `avg_pct=(cpu1-cpu0)/elapsed*100` vs `CPU_LIMIT_PCT=25` (L148). NOT divided by nproc. **pidstat/sysstat NOT installed** → `/proc` is the zero-dep path (G-CPU-SAMPLING). | ❌ none (needs a real running daemon). | COVERED (shell only) |
| (c) no crash | ✅ **L511-516**: `kill -0 "$DAEMON_PID"` after the 120 s window. | ❌ none (needs a real running daemon). | COVERED (shell only) |

**Conclusion:** T4 is **FULLY covered** by `test_idle_and_gpu.sh` RUN 1 (the only place the real 120 s
+ CPU % + no-crash trio is asserted end-to-end against real CUDA + ambient mic). `test_daemon.py`
contributes the **blocklist-guard unit proof** (fast, mocked) — it does NOT, and cannot, assert the
120 s / CPU % / no-crash trio (those require a live daemon + real mic silence). The work-item's "if
only mocked in test_daemon.py, note the full 120 s test is in the shell script" applies: the mocked
tests are a SUPPLEMENT, the shell script is the AUTHORITATIVE T4.

## 3. The mitigation chain (why (a) passes — the hallucination guard)

T4(a) "no finals" is the END RESULT of a two-layer defense. T4 asserts the result; the layers are:
1. **VAD gating** (RealtimeSTT silero/webrtc, §4.4): the recorder only finalizes on detected speech
   onset — pure silence usually produces NO final callback at all. (Configured in recorder kwargs;
   not directly unit-testable without a model.)
2. **blocklist** (`textproc.clean()` step 3, §4.7; `config.toml` `[filter]` L62-67): exact,
   case-insensitive, trailing-punctuation-stripped match drops "thank you.", "thanks for watching.",
   "bye.", "thank you for watching". **NOTE (VT-006):** the bare "you" entry was REMOVED — it is a
   common word users want to type, not a hallucination.

The shell test's double-signal (`last_final` UNCHANGED) is strong: if `last_final` is unchanged,
either no final was produced (VAD worked) OR a final was produced + rejected by the blocklist
(clean → None → on_final early-returns without recording). Both are "guard worked." If the capture-
pane changed, something was TYPED (a real failure).

## 4. The mocked pytest command (work-item step 3) — IS it safe / fast?

```
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'
```

**CONFIRMED CUDA-FREE.** `test_daemon.py` header (L1-10): *"NO real RealtimeSTT / NO model load /
NO CUDA / NO real feedback.py dependency … _construct takes a fake recorder class."* `_make_daemon()`
(L618) wires `_FakeRecorder` (L28) + stub Feedback/Backend. So this runs in SECONDS, not the 5-8 min
heavy load. **BUT** AGENTS.md discipline is non-negotiable: double-timeout (inner `timeout 300` +
bash-tool `timeout` ≥ 360 s) regardless — the AGENTS.md hang-vectors table lists test_daemon.py as a
hang risk (some suites load CUDA); even though THIS file's header says it doesn't, apply the wrapper
as belt-and-suspenders and WATCH the output (if it actually loads CUDA, Ctrl-C + the Cleanup block).

**Tests the `-k` filter matches** (the relevant subset):
- `test_on_final_rejects_hallucination` (L667) — **T4(a) blocklist guard** ✅
- `test_on_final_rejected_hallucination_emits_no_latency_line` (L1532) — guard + no latency line ✅
- `test_auto_stop_disarms_when_idle_beyond_threshold` (L767), `test_idle_watchdog_actually_disarms_in_background` (L818) — auto-stop idle (related to the 30 s handoff)
- `test_idle_unload_*` (L3340-3414) — idle-UNLOAD lifecycle (T6(d), not T4, but matched by 'idle')
- `test_touch_speech_resets_the_idle_clock` (L784), `test_disarm_clears_the_idle_clock` (L810)
- `test_cfg_to_kwargs_cpu_fallback*` (L156,2639,...) — CPU-fallback CONFIG tests (matched by 'cpu' but
  UNRELATED to T4's runtime CPU %; they test cfg_to_kwargs device resolution). Note this in the report
  so the "cpu" match isn't misread as a T4-cpu test.
- `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` (L216) — matched by 'silence' (lite, not T4).

So the `-k` filter is a NET that catches the blocklist guard (the one T4-relevant mocked test) plus
idle/auto-stop/idle-unload neighbors + unrelated cpu-fallback/silence config tests. The report should
clearly separate "T4-relevant" from "collateral matches."

## 5. Correct-design notes (NOT gaps — record in report for honesty)

1. **CPU window AMORTIZES the cold-load spike.** `cpu0` is captured at L474 (just before `voicectl
   start` at L476), and `cpu1` at L496 (after the 120 s `sleep`). The window therefore INCLUDES the
   ~1-3 s cold cuDNN/cuBLAS load (high CPU) — but that spike is amortized over the 120 s+ window, so
   the average is sound. The comment at L394 confirms the original passing run measured ~2.5 %.
2. **auto_stop handoff (ISSUE-3 interaction).** `auto_stop_idle_seconds` default = 30.0 (config.py:65)
   disarms the mic ~30 s into the 120 s window → steady-state VAD-inference CPU drops to near-zero for
   the remaining ~90 s. This is WHY CPU is trivially low. It also means T4's "armed" window is only
   ~30 s of true armed + ~90 s of disarmed-but-resident — but the test's intent (survive 120 s of
   silence, no hallucination, low CPU) is honored either way (disarmed ⟹ even less likely to hallucinate).
   The comment cites this handoff as the source of the low reading. Record as correct, not a gap.
3. **/proc not pidstat (G-CPU-SAMPLING).** pidstat/sysstat is NOT installed on this machine → the
   script's `/proc`-based tree-sum is the correct zero-dep path. PRD §6 T4 says "`pidstat` OR `/proc`
   sampling" — `/proc` satisfies it.
4. **Tree, not single PID (G-CPU-TREE).** The CUDA workers + SafePipe may spawn child processes;
   measuring only the daemon PID would UNDERCOUNT. The recursive `/proc/<pid>/task/<pid>/children`
   walk captures the whole tree. Correct.
5. **`kill -0` is the right crash signal.** It succeeds iff the PID still exists (not reaped). A crash
   (segfault, OOM-kill, assertion) reaps the process → `kill -0` fails → [FAIL]. Correct + sufficient.

## 6. Scope boundary (parallel item P1.M5.T3.S2)

- **P1.M5.T3.S2** audits T6 (GPU lifecycle, nvidia-smi VRAM idle/armed/disarmed/unload) in the SAME
  `test_idle_and_gpu.sh`. Its PRP EXPLICITLY lists T4 as OUT-OF-SCOPE ("→ P1.M5.T4.*").
- **THIS item** audits T4 (no-finals / CPU % / no-crash) in BOTH files + runs the mocked pytest.
- The two items read overlapping sections of RUN 1 (the T6(b) VRAM-present assertion is INTERLEAVED
  with the T4 CPU window at L482-492, inside the `sleep $IDLE_SECS`) but audit DIFFERENT signals: T6 =
  nvidia-smi VRAM presence; T4 = capture-pane/CPU/alive. No conflict — both are read-only, separate
  reports. Do NOT re-audit T6 here (cite P1.M5.T3.S2 for the VRAM slice).

## 7. No existing report / what to create

- `plan/006_862ee9d6ef41/P1M5T4S1/` currently has only `research/` (empty) — no `test_results_t4.md`.
- The deliverable (`test_results_t4.md`) is NEW. Source-side gap docs exist
  (`architecture/gap_textproc.md`, `gap_daemon_loop.md`, `gap_lifecycle.md`) — CITE them, don't
  re-derive.
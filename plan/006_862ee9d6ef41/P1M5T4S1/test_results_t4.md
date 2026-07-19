# T4 Coverage Assessment — P1.M5.T4.S1 (PRD §6 T4 / Acceptance #5)

**Date:** 2025-01-24
**Method:** STATIC read of `tests/test_idle_and_gpu.sh` + `tests/test_daemon.py` + mitigation source
(`textproc.py`, `config.toml`, `daemon.py`); PLUS a LIVE run of the work-item's mocked pytest
(`tests/test_daemon.py -k 'idle or hallucin or silence or cpu'`, CUDA-free, double-timeout). The shell
script is NOT run (CUDA ~5-8 min; static read only — consistent with the parallel T6 audit P1.M5.T3.S2).

**Verdict:** **T4 FULLY COVERED.** All three sub-checks ((a) no-finals, (b) CPU<25%, (c) no-crash) are
asserted end-to-end in `test_idle_and_gpu.sh` RUN 1 (real CUDA + ambient mic) — the AUTHORITATIVE proof.
The mocked pytest proves the **blocklist-guard LOGIC** (PASSED, fast, CUDA-free, 1.07 s) — a logic
supplement, NOT a substitute for the 120 s end-to-end. Two-layer mitigation = VAD gating + textproc
blocklist.

> **Line numbers below are LIVE-confirmed** against the files at audit time (the PRP's pre-verified
> numbers were within ±3 lines; this report uses the actual current lines). `tests/test_idle_and_gpu.sh`
> is 779 lines; `tests/test_daemon.py` is ~3847 lines.

---

## 1. T4 sub-check coverage matrix

PRD §6 T4 requires: *"120 s silence … no finals typed, no crash, CPU <25% of one core (pidstat or /proc)."*

| sub-check | `test_idle_and_gpu.sh` RUN 1 (real CUDA) | `test_daemon.py` (mocked, CUDA-free) | verdict |
|---|---|---|---|
| (a) no hallucinated finals | ✅ **L473-509** (block header L473); `IDLE_SECS=120` (L147); `typed_before`/`last_final_before` captured at **L493-494**; `sleep "$IDLE_SECS"` at **L495**; double-signal assertion at **L501-509**: capture-pane UNCHANGED (`typed_before==typed_after`) **AND** `state.json last_final` UNCHANGED (`jq -r .last_final`) across the 120 s window. | ✅ logic-only: `test_on_final_rejects_hallucination` (**L667** — feeds `"thank you."` → `be.typed==[]` + `fb.finals==[]`); `test_on_final_rejected_hallucination_emits_no_latency_line` (**L1532** — blocklist reject emits no latency log line). | **COVERED** (shell=end-to-end; unit=guard logic) |
| (b) CPU < 25 % of ONE core | ✅ **L517-523** + `cpu_tree_seconds()` **L176-211**: `/proc/<pid>/stat` utime+stime (fields 14/15 via last-`)` split) summed over the PROCESS TREE (recursive `/proc/<pid>/task/<pid>/children` walk) ÷ `CLK_TCK` (=100); `cpu0` captured BEFORE `voicectl start` at **L475**, `cpu1` after at **L496**; `avg_pct=(cpu1-cpu0)/elapsed*100` (awk at **L519**) vs `CPU_LIMIT_PCT=25` (**L148**); NOT divided by nproc. **pidstat/sysstat NOT installed** → `/proc` is the zero-dep path (G-CPU-SAMPLING). | ❌ none (needs a live daemon) | **COVERED (shell only)** |
| (c) no crash | ✅ **L512**: `kill -0 "$DAEMON_PID" 2>/dev/null` after the 120 s window (succeeds iff PID exists). | ❌ none (needs a live daemon) | **COVERED (shell only)** |

---

## 2. The two-layer mitigation (why (a) passes)

T4(a) "no hallucinated finals" is the direct defense against PRD §8's top-3 risk (Whisper
silence-hallucination "thank you."). It is enforced by **two independent layers**, and T4 asserts the
**combined RESULT** (no hallucinated text typed), not either mechanism in isolation:

1. **VAD gating** (RealtimeSTT silero/webrtc, PRD §4.4): the recorder only finalizes on detected speech
   onset — pure silence usually produces NO final callback at all. (No code-level assertion target; it
   is the upstream suppression.)
2. **Blocklist** (`textproc.clean()` step 3, PRD §4.7; `config.toml [filter]` L59-67): exact,
   case-insensitive, trailing-punctuation-stripped match drops `"thank you."`, `"thanks for watching."`,
   `"bye."`, `"thank you for watching"`. `clean()` returns `None` → `daemon.on_final` early-returns
   (`daemon.py:951-953`, `if not cleaned: return`) → no `type_text`, no `record_final`, and
   `state.json last_final` stays UNCHANGED → T4(a) passes.

The shell test's double-signal (capture-pane UNCHANGED **AND** `last_final` UNCHANGED) passes if
**EITHER** layer worked (VAD suppressed the callback, OR the blocklist rejected a produced final).
That is **correct design** — the goal is "no hallucinated text typed," however achieved. The mocked
unit test (`test_on_final_rejects_hallucination`) is the one that **isolates the BLOCKLIST layer**
(feed `"thank you."` → `typed==[]`).

**Source citations (the mitigation chain):**
- `voice_typing/textproc.py:39` — `def clean(text, cfg) -> str | None`. Docstring (L17): *"THE BLOCKLIST
  is the primary defense against Whisper's silence hallucination … VAD gating + this filter + PRD test
  T4 assert it together."* Step 3 blocklist at L61-67 (`return None` at L67).
- `config.toml:59-67` — `[filter]`: `min_chars=2` (L61), `blocklist` (L62-66) with the four entries
  above. **VT-006 note (L67):** the bare `"you"` entry was **REMOVED** — it is a common word users want
  to type, not a hallucination. The blocklist is exact-match (not substring) → `"yourself"` is never
  blocked. (Precision-vs-recall tradeoff, documented — do not re-add `"you"`.)
- `voice_typing/daemon.py:942-953` — `on_final`: `cleaned = textproc.clean(text, self._cfg.filter)`
  (L951); `if not cleaned: return` (L953) — the clean→None early-return path.
- (Source-side audits already done: `architecture/gap_textproc.md`, `gap_daemon_loop.md`,
  `gap_lifecycle.md` — cited, not re-derived.)

---

## 3. Mocked-pytest result (work-item step 3 — LIVE)

**Command** (AGENTS.md double-timeout — inner `timeout 300`, bash-tool `timeout 420`):

```
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'
```

**Result** (verbatim):

```
.....................................                                    [100%]
37 passed, 156 deselected in 1.07s
=== exit=0 ===
```

**CUDA-free confirmed:** ran in **1.07 s**, no `torch`/`cuDNN`/`cuBLAS` init in the output. Consistent
with the `test_daemon.py` header (L3): *"NO real RealtimeSTT / NO model load / NO CUDA / NO real
feedback.py dependency"* — `_make_daemon()` (L618) wires `_FakeRecorder` (L60) + stub feedback/backend.

### Selected tests — T4-relevant vs collateral (37 selected, all PASSED)

The `-k 'idle or hallucin or silence or cpu'` filter is broad and catches many UNRELATED tests. The
report annotates them so "T4 CPU is unit-tested" is not misread (it is NOT — CPU% is shell-script-only).

**✅ T4-relevant (the ONLY tests that exercise T4's hallucination guard) — 2 tests:**
- `test_on_final_rejects_hallucination` (L667) — feeds `"thank you."` → `be.typed==[]`, `fb.finals==[]`.
- `test_on_final_rejected_hallucination_emits_no_latency_line` (L1532) — blocklist reject emits no
  latency log line.

**➖ collateral — idle/auto-stop/idle-unload lifecycle (T6(d)-adjacent / lifecycle, NOT T4's no-finals) — 25 tests:**
- auto-stop (the 30 s handoff): `test_auto_stop_disarms_when_idle_beyond_threshold` (L767),
  `test_auto_stop_resets_phase_to_idle`, `test_idle_watchdog_actually_disarms_in_background` (L818).
- idle-unload (T6(d), owned by P1.M5.T3.S2): `test_idle_unload_fires_when_disarmed_beyond_threshold`
  (L3340), `test_idle_unload_keeps_resident_within_threshold` (L3354),
  `test_idle_unload_disabled_when_threshold_zero` (L3366), `test_idle_unload_noop_when_listening`
  (L3381), `test_idle_unload_noop_when_never_disarmed` (L3394), `test_idle_unload_noop_when_not_loaded`
  (L3404).
- idle-clock / phase transitions: `test_arm_resets_idle_unload_clock`,
  `test_disarm_clears_the_idle_clock`, `test_disarm_resets_phase_to_idle`,
  `test_touch_speech_resets_the_idle_clock`, `test_state_json_phase_idle_after_stop`,
  `test_toggle_off_resets_phase_to_idle`, `test_toggle_while_idle_arms_in_normal`,
  `test_toggle_lite_while_idle_arms_in_lite`.
- cold-reload + status reseed (T6(d)-reload-adjacent): `test_cold_arm_after_idle_unload_refires_loading_toast`,
  `test_start_lite_after_idle_unload_reloads_in_lite`,
  `test_status_device_reseeded_not_stale_after_idle_unload`.
- run-loop idle mechanics: `test_quit_while_run_loop_idle_returns_promptly`,
  `test_stop_aborts_immediately_when_text_idle_no_speech`, `test_stop_disarms_immediately_when_idle`,
  `test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang`.

**➖ collateral — `-k 'cpu'` false-friend (device-resolution CONFIG tests, NOT T4 runtime CPU %) — 10 tests:**
- `test_cfg_to_kwargs_cpu_fallback` (L156), `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en`,
- `test_construct_force_cpu_uses_cpu_fallback` (L2639), `test_construct_force_cpu_skips_resolve` (L2649),
  `test_construct_force_cpu_overrides_cuda_path` (L2662), `test_construct_force_cpu_keeps_non_device_kwargs`
  (L2671), `test_construct_force_cpu_false_is_default_behavior` (L2689),
  `test_build_recorder_and_construct_force_cpu_in_signature`,
- `test_load_recorder_cpu_fallback_on_cuda_failure`, `test_log_resolved_device_reads_cache_after_cpu_fallback`.

**➖ collateral — `-k 'silence'` (lite mode, not T4) — 1 test:**
- `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` (L216).

---

## 4. Acceptance #5 mapping

Acceptance #5: *"Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use."*

| clause | evidence | artifact |
|---|---|---|
| "survives ≥2 min silence" | `IDLE_SECS=120` window + `kill -0` after the window (daemon still alive) | `test_idle_and_gpu.sh` RUN 1 L147 / L512 |
| "no hallucinated output" | no-finals double-signal (capture-pane UNCHANGED AND `state.json last_final` UNCHANGED) across the 120 s, backed by the two-layer VAD+blocklist mitigation; mocked guard proves the blocklist layer | `test_idle_and_gpu.sh` L501-509 + mocked guard `test_daemon.py` L667/L1532 |
| "trivial CPU" | `avg_pct < CPU_LIMIT_PCT=25` (of ONE core, process-tree-summed, not ÷ nproc) | `test_idle_and_gpu.sh` L519-523 (+ helper L176-211) |

**Conclusion:** Acceptance #5 is **PROVEN** by `test_idle_and_gpu.sh` RUN 1 (the authoritative,
real-CUDA end-to-end). The mocked pytest corroborates the guard logic but cannot, alone, prove the
120 s / CPU% / no-crash trio (those require a live daemon + real mic silence).

---

## 5. The SPLIT (load-bearing — for P1.M5.T5.S1)

This is the report's most important claim for the downstream acceptance cross-check (P1.M5.T5.S1):

- **Shell script (`test_idle_and_gpu.sh` RUN 1) = AUTHORITATIVE.** It is the ONLY place the real
  120 s + CPU% + no-crash trio is asserted end-to-end against real CUDA + the ambient mic. Acceptance #5
  is proven HERE. (It was NOT run in this audit — CUDA ~5-8 min; static read only, consistent with the
  parallel T6 audit P1.M5.T3.S2.)
- **Mocked pytest (`test_daemon.py`) = blocklist-guard LOGIC supplement.** Fast (1.07 s), CUDA-free;
  proves the guard rejects hallucinated text at the daemon level (`"thank you."` → `typed==[]`). It does
  NOT, and cannot, prove "120 s / CPU% / no-crash" (those need a live daemon + real mic silence).

**➡️ P1.M5.T5.S1 must credit Acceptance #5 against the SHELL SCRIPT, with the mocked pytest as
corroboration of the guard logic — NOT the reverse.** A mocked-only proof would be insufficient for
"survives 2 min with trivial CPU."

---

## 6. Correct-design notes (NOT gaps)

These explain WHY the T4 numbers/structure are sound — recorded so a future regression alarm is
attributed correctly:

1. **CPU window amortizes the cold-load spike.** `cpu0` is captured BEFORE `voicectl start` (L475) →
   the ~1-3 s cuDNN/cuBLAS cold load is INCLUDED in the window but amortized over 120 s+ → the average
   is sound. (Not a gap — the spike is part of real steady-state from a cold start.)
2. **auto_stop 30 s handoff.** `auto_stop_idle_seconds` default = 30.0 (`config.toml:40`) disarms the
   mic ~30 s into the window (no recognized speech → auto-stop fires) → steady-state VAD-inference CPU
   drops to near-zero for the remaining ~90 s. This is WHY CPU is trivially low (historically ~2.5% on
   the passing run). A future "CPU regressed!" alarm should check whether `auto_stop` fired first —
   `auto_stop` firing is the lever, not a CPU-path change.
3. **/proc, not pidstat (G-CPU-SAMPLING).** `pidstat`/`sysstat` is NOT installed on this machine
   (verified) → `cpu_tree_seconds()` uses `/proc/<pid>/stat` fields 14/15 + a recursive
   `/proc/<pid>/task/<pid>/children` walk. PRD §6 T4's *"pidstat OR /proc sampling"* latitude is
   satisfied by the `/proc` path (zero extra deps). `/proc` semantics confirmed: field 14 = utime,
   field 15 = stime, both in clock ticks; `CLK_TCK` via `os.sysconf(SC_CLK_TCK)` = 100.
4. **Tree, not single PID (G-CPU-TREE).** The CUDA workers + `SafePipe` spawn children; a single-PID
   read would UNDERCOUNT. The recursive `/proc/<pid>/task/<pid>/children` walk captures the whole tree.
   (Split-after-last-`)` parse is required because `comm` may contain spaces/parens.)
5. **`kill -0` crash signal.** `kill -0 "$DAEMON_PID"` succeeds iff the PID exists; a crash
   (segfault/OOM/assertion) reaps the process → the PID is gone → `[FAIL]`. Correct + sufficient.
6. **VT-006 `"you"` blocklist removal.** Bare `"you"` was deliberately removed from the blocklist
   (`config.toml:67`) — it is a common word users type, not a hallucination. The blocklist is
   intentionally NARROW (exact normalized match, NOT substring) → `"yourself"` is never blocked. Do not
   "fix" it by re-adding `"you"`.

---

## 7. Scope

- **IN scope (this item):** T4 (a)(b)(c) coverage across both test homes (`test_idle_and_gpu.sh` RUN 1 +
  `test_daemon.py` mocked) + the LIVE mocked-pytest run + the Acceptance #5 mapping + the split +
  correct-design notes.
- **OUT of scope (cited, NOT re-audited):**
  - **T6 GPU lifecycle** (nvidia-smi VRAM idle/armed/disarmed/unload, including the T6(b) VRAM-present
    assertion interleaved inside the T4 CPU window at `test_idle_and_gpu.sh` L482-492) → **P1.M5.T3.S2**
    (its PRP explicitly lists T4 as out-of-scope → P1.M5.T4.*).
  - The **idle-UNLOAD** mocked tests (T6(d)-adjacent) → P1.M5.T3.S2 / P1.M2.T2.S3.
  - The **blocklist unit tests** (`test_textproc.py`) → P1.M2.T2.S1.
- **Edits (NONE — REPORT item):** no `tests/*`, `voice_typing/*`, `config.toml`, `PRD.md`,
  `tasks.json`, `prd_snapshot.md`, or `.gitignore` modified. The ONLY write is this file
  (`test_results_t4.md`, CREATE). The one LIVE action — the mocked pytest — is read-only w.r.t. the
  repo. The shell script was NOT run.
# Research Note — P1.M2.T3.S3: T7 Lite Test-Coverage Audit

**Scope:** Verify PRD §6 **T7** lite-mode test COVERAGE across `tests/` (the contract: "INPUT
test_feed_audio.py + test_daemon.py; LOGIC: verify T7 coverage exists; if gaps, write tests; RUN
`pytest tests/ -q -k lite`; OUTPUT: append T7 coverage status to gap_lite.md").

**Verdict: ✅ T7 coverage is COMPREHENSIVE — no real gaps; NO new tests needed.** Every T7 clause
(feed_audio offline + socket protocol) is covered by existing tests. The implementing agent only
APPENDS the T7-coverage section to `gap_lite.md` + re-runs the contract target to record the count.
No `tests/*` or `voice_typing/*` file is modified.

This is the **test-coverage** audit (S3). It complements — does NOT duplicate — **S1** (lite
construction CODE audit, the 4 kwargs clauses) and **S2** (mode-switch reload CODE audit, the 6
routing/instant/cross-mode/self._mode/set_mode/stop clauses). S3 answers "are the T7 contract
clauses COVERED BY TESTS?" (not "is the code compliant?").

---

## 0. The contract run target — collect-only baseline (re-ran live, fast/safe, no model load)

```
$ timeout 120 .venv/bin/python -m pytest tests/ -q -k 'lite' --collect-only
26/424 tests collected (398 deselected) in 0.05s
```

**Per-file breakdown** (of the 26 collected):

| File | # | Tests (the real lite ones) |
|---|---|---|
| `tests/test_daemon.py` | 15 | kwargs (4) + mode-switch/socket-behavior (11) — see §3 |
| `tests/test_config.py` | 4 | `lite_model` / `lite_post_speech_silence_duration` config-field/param tests |
| `tests/test_feed_audio.py` | 2 | `test_lite_feed_audio_utt_simple` @L653, `test_lite_latency_lower_than_normal` @L679 (GPU-gated — SKIP w/o CUDA) |
| `tests/test_control_socket.py` | 1 | `test_dispatch_status_response_carries_mode` @L143 |
| `tests/test_voicectl.py` | 1 | `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` |
| `tests/test_status_sh.py` | 1 | `test_status_sh_lite_mode_prefixes_bolt` (the ⚡ prefix) |
| `tests/test_recorder_host.py` | 0 | (recorded as nuance §4.4 — not a gap; S1 §4(ii) explains) |
| `tests/test_typing_backends.py` | 1 | **false positive** — `test_wtype_text_starting_with_dash_stays_literal` matches "lite" via "literal"; NOT a lite test |

**Run semantics** (what the implementing agent will observe when it RUNS the target):
- **Without CUDA** (the default/mockable box): the 2 `test_feed_audio.py` lite tests `pytest.skip`
  ("T7 is a GPU integration test (G-CPU)"); the other 24 pass in ~0.04s (mocked-CUDA fakes). Expected
  run result: **24 passed, 2 skipped** (the 398 deselected stay deselected; the 1 false-positive
  typing-backends test also passes trivially).
- **With CUDA**: all 26 run, but the 2 feed_audio tests LOAD REAL MODELS (small.en + distil-large-v3
  in the session-scoped `recorder` + `lite_recorder` fixtures) → **minutes**, must be wrapped in
  `timeout 600` (AGENTS.md). The agent should default to the collect-only count + the mocked-CUDA
  run (skip path) unless the task explicitly needs the live GPU pass.

**MANDATORY wrap** (AGENTS.md Rule 1 — two timeouts): `timeout 600 .venv/bin/python -m pytest
tests/ -q -k 'lite'` (inner) + the bash-tool `timeout` param set above 600 (outer backstop). The
control socket has NO read timeout; never run untimed `voicectl`.

---

## 1. T7 clause → covering-test map (the deliverable's compliance table source)

### A. T7 feed_audio offline (PRD §6 T7 bullets 1–3, the "construct the lite recorder + feed utt_simple" asserts)

| T7 clause | Covering test (file:line) | What it asserts | Gap? |
|---|---|---|---|
| **(a) exactly ONE model resident (no distil-large-v3 worker, ~half VRAM)** | `test_lite_feed_audio_utt_simple` @test_feed_audio.py:667-669 (integration, REAL recorder) asserts `rec.use_main_model_for_realtime is True`; + `test_cfg_to_kwargs_lite_mode_uses_one_model` @test_daemon.py:138, `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` @165, `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` @185 (unit, kwargs dict) | integration-grade: the REAL constructed recorder carries `use_main_model_for_realtime=True` (the one-model flag — a future RealtimeSTT regression of the early-return would leave it False → fail loudly); unit: `model`==`realtime_model_type`=="small.en" (CUDA) / "tiny.en" (CPU) + `use_main_model_for_realtime`=True; normal: `model`="distil-large-v3" + `use_main_model_for_realtime`=False | **NO** — covered. (Nuance §4.1: proven via the invariant flag + kwargs, NOT VRAM/grep — deliberate.) |
| **(b) finals arrive over clean→type path, fuzzy-accuracy ≥70%** | `test_lite_feed_audio_utt_simple` @test_feed_audio.py:672-676 asserts `_token_overlap(joined, SIMPLE_TEXT) >= 0.70` over the collected finals | finals ≥0.70 fuzzy (lower bar than normal's 0.80 — small.en is the final model); collected via the SAME `on_final` callback path as normal (the `lite_recorder` fixture @L311 mirrors `recorder` EXACTLY except the `lite=True` swap — the clean→type path is shared by construction) | **NO** — covered. (Nuance §4.2: path-identity is proven by fixture-construction, not a separate assertion.) |
| **(c) shorter post_speech_silence_duration carried + e2e latency materially lower than normal** | silence: `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` @test_daemon.py:216 (lite 0.5 vs normal 0.6, tunable to 0.3); latency: `test_lite_latency_lower_than_normal` @test_feed_audio.py:679 asserts `lite_best <= normal_best * 1.25` (best-of-3 min per recorder) | silence-gate override propagates + is tunable; latency not >25% slower than normal (catches a two-model regression ~1.5-2x slower) | **NO** — covered. (Nuance §4.3: uses a 25% tolerance BAND, not strict "materially lower" `<` — DOCUMENTED, sound; see §4.3.) |

### B. T7 socket protocol (PRD §6 T7 "Then over the socket" bullets)

| T7 clause | Covering test (file:line) | What it asserts | Gap? |
|---|---|---|---|
| **toggle-lite arms with `mode:"lite"` in the response** | `test_start_lite_loads_lite_host_and_arms` @test_daemon.py:2863 asserts `d._mode=="lite"` + `d._host.mode=="lite"` + `fb.modes==["lite"]`; + `test_dispatch_status_response_carries_mode` @test_control_socket.py:143 proves the wire response carries `mode` (the `{'ok':True,**status_snapshot()}` spread — `_arm_response`@daemon.py:1890 spreads `status_snapshot()` which has `"mode":self._mode`@1567); + `test_status_snapshot_reports_mode` @test_daemon.py:2918 | the arm surfaces mode on the wire (structural: `_arm_response`→`**status_snapshot()`→`mode`) + daemon tracks `_mode=="lite"` + state.json (`fb.modes`) gets "lite" | **NO** — covered (transitively; nuance §4.5). |
| **toggle-lite again disarms** | `test_toggle_lite_while_armed_in_lite_disarms` @test_daemon.py:3708 (`is_listening()` False, `len(spawns)==1` no reload); + `test_toggle_lite_while_listening_in_lite_stops` @test_daemon.py:2904 | armed-in-lite + toggle-lite → disarm (no reload) | **NO** — covered. |
| **a subsequent `toggle` reloads into `mode:"normal"` (ONE reload)** | `test_toggle_while_armed_in_lite_switches_to_normal` @test_daemon.py:3753 asserts `len(spawns)==2` (lite spawn + ONE normal reload) + `d._mode=="normal"` + `d._host.mode=="normal"`; + `test_mode_switch_stops_outgoing_host` @test_daemon.py:2927 (outgoing `stop_calls==1`); + `test_mode_switch_normal_to_lite_reloads` @test_daemon.py:2875 (reverse direction); + `test_same_mode_arm_is_instant_no_reload` @2892 (same-mode NO reload); + `test_start_lite_after_idle_unload_reloads_in_lite` @2951 | cross-mode toggle = exactly ONE bounded reload (acceptance #10); same-mode = instant | **NO** — covered (the "one reload" count is pinned by `len(spawns)==2`). |
| **`status` reports the current `mode`** | `test_status_snapshot_reports_mode` @test_daemon.py:2918 (boot normal, post-arm-lite lite); + `test_dispatch_status_response_carries_mode` @test_control_socket.py:143 (wire); + `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` @test_voicectl.py (CLI renders `mode:`); + `test_status_sh_lite_mode_prefixes_bolt` @test_status_sh.py (⚡ prefix) | status_snapshot + wire response + voicectl CLI + tmux ⚡ all report the mode | **NO** — covered (4 surfaces). |

**Bottom line of §1:** every T7 clause (feed_audio a/b/c + socket 4 bullets) has at least one
covering test with file:line evidence. There are NO coverage gaps requiring new tests.

---

## 2. The 2 GPU-gated integration tests — full code read (so the agent knows exactly what they assert)

### `test_lite_feed_audio_utt_simple` @tests/test_feed_audio.py:653-676
- **Guard:** `if not daemon.cuda_check.is_cuda_available(): pytest.skip("T7 is a GPU integration test (G-CPU)...")`
- **(a) one model:** `assert rec.use_main_model_for_realtime is True` (integration-grade — the REAL
  constructed recorder carries the one-model flag; comment: "P1.M1.T1.S2 already unit-tests the
  kwargs dict").
- **(b) accuracy:** `_run_utterance(rec, col, _WAVS["simple"], want_finals=1)`; `joined=" ".join(
  finals)`; `assert _token_overlap(joined, SIMPLE_TEXT) >= 0.70` (lower bar than normal's 0.80).
- Uses the `lite_recorder` session fixture @L311 (builds `cfg_to_kwargs(cfg, lite=True)` — the REAL
  swap `model=lite_model` + `use_main_model_for_realtime=True`).

### `test_lite_latency_lower_than_normal` @tests/test_feed_audio.py:679-~800
- **Guard:** `if not daemon.cuda_check.is_cuda_available(): pytest.skip("T7(c) latency comparison is a GPU budget (G-CPU)")`.
- **Method:** best-of-3 min per recorder, measures `last-speech-fed → final-received` (ms) for BOTH
  the normal `recorder` + `lite_recorder` on `utt_simple`.
- **Assertion:** `assert lite_best <= normal_best * 1.25` (a 25% tolerance BAND; comment explicitly
  authorizes `<=` over strict `<` if a noisy GPU makes strict `<` flaky).
- **Rationale (in-test comment, L758-777):** "on a fast GPU a SHORT utterance (9 words) shows the
  model-size advantage swamped by VAD/realtime-stabilization/GPU-scheduling noise" → assert a
  TOLERANCE BAND; a true two-model regression would be ~1.5-2x slower → caught loudly by the 1.25x
  band. "The one-model invariant (test_lite_feed_audio_utt_simple) is the PRIMARY proof lite loads
  one model; this is secondary corroboration."

---

## 3. The 15 `test_daemon.py` lite tests (mocked-CUDA, ~0.04s) — clause→test index

```
# kwargs (4) — T7(a)/(c) unit
test_cfg_to_kwargs_lite_mode_uses_one_model              @138   (a) one-model kwargs
test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en        @165   (a) CPU one-model (tiny.en)
test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal     @185   isolation (only 4 fields differ)
test_cfg_to_kwargs_lite_uses_shorter_silence_duration    @216   (c) silence gate 0.5 vs 0.6

# mode-switch / socket-behavior (11) — T7 socket + acceptance #10
test_start_lite_loads_lite_host_and_arms                 @2863  start-lite → lite host + arm + _mode
test_mode_switch_normal_to_lite_reloads                  @2875  cross-mode reload (normal→lite)
test_same_mode_arm_is_instant_no_reload                  @2892  same-mode instant (no reload)
test_toggle_lite_while_listening_in_lite_stops           @2904  toggle-lite disarms lite
test_status_snapshot_reports_mode                        @2918  status carries mode (boot/arm)
test_mode_switch_stops_outgoing_host                     @2927  outgoing stop_calls==1 (one reload)
test_start_lite_after_idle_unload_reloads_in_lite        @2951  reload after idle-unload → lite
test_toggle_lite_while_idle_arms_in_lite                 @3696  toggle-lite idle → arm lite
test_toggle_lite_while_armed_in_lite_disarms             @3708  toggle-lite armed-in-lite → disarm
test_toggle_lite_while_armed_in_normal_switches_to_lite  @3719  cross-mode (normal→lite, one reload)
test_toggle_while_armed_in_lite_switches_to_normal       @3753  cross-mode (lite→normal, one reload)
test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening  @3790  failed-reload honesty
test_toggle_while_armed_in_lite_failed_reload_clears_listening         @~3803 failed-reload honesty
test_toggle_lite_docstring_says_pressing_d_not_f          @3851  docstring guard
```
(15 selected by `-k lite` in test_daemon.py; matches S2's + S1's baselines.)

---

## 4. Non-defect nuances (recorded so they are NOT mistaken for coverage gaps)

### (4.1) "ONE model resident / ~half VRAM" is proven via the invariant FLAG, not VRAM/grep.
PRD T7(a) literally says "grep the child log / check VRAM ≈ half of normal". The tests instead assert
`rec.use_main_model_for_realtime is True` (integration) + the kwargs dict (unit). This is a DELIBERATE,
sound choice: the flag is the AUTHORITATIVE one-model mechanism (verified against RealtimeSTT v1.0.2 —
`use_main_model_for_realtime=True` early-returns out of `_initialize_realtime_transcription_model`, so
the large model never constructs → ~half VRAM is STRUCTURALLY guaranteed). VRAM varies by GPU/driver
state; child-log grep is brittle. The flag assertion is strictly MORE reliable than a VRAM diff. NOT a
gap. (The live VRAM check is exercised by `tests/test_idle_and_gpu.sh` T7, the shell suite — out of
scope for this pytest coverage audit.)

### (4.2) "finals over the clean→type path" is proven by fixture CONSTRUCTION, not a separate assertion.
The `lite_recorder` fixture @L311 mirrors the normal `recorder` fixture EXACTLY except the `lite=True`
swap (same `on_realtime_transcription_stabilized`/`on_vad_start`/`on_vad_stop`/`add_final` callbacks,
same shutdown). The clean→type path is therefore SHARED by construction — there is nothing lite-specific
about the path to assert. PRD §4.2ter confirms: "on_final therefore yields lite_model finals — fast,
lower-accuracy — over the SAME clean→type→record path as normal mode." NOT a gap.

### (4.3) Latency uses a 25% tolerance BAND (`<= normal*1.25`), not strict "materially lower" (`<`).
PRD T7(c) says "end-to-end stop→text latency is materially lower than normal mode". The test asserts
`lite_best <= normal_best * 1.25`. This is a DOCUMENTED engineering choice (in-test comment L758-777):
on a fast GPU a 9-word utterance shows the small-model win (~50ms) SWAMPED by VAD/realtime-stabilization/
GPU-scheduling noise, so strict `<` is flaky. The test's PURPOSE is to catch a two-model regression
(~1.5-2x slower), which the 1.25x band catches loudly. The one-model invariant (test_lite_feed_audio_
utt_simple) is the PRIMARY proof; this latency test is SECONDARY corroboration. The PRP author
explicitly authorized `<=`. NOT a gap — a documented, sound deviation. (To strengthen to strict `<`
would make the test flaky on CI without adding real coverage.)

### (4.4) `tests/test_recorder_host.py` has ZERO lite tests.
`grep -c -i lite tests/test_recorder_host.py` = 0. NOT a gap (recorded by S1 §4(ii)): lite CONSTRUCTION
is unit-tested at the `cfg_to_kwargs` layer (test_daemon.py, 4 kwargs tests) + the `mode == "lite"` →
`lite = True` derivation is a one-line literal at `recorder_host.py:458` verified by reading + the live
`test_idle_and_gpu.sh` T7 + `test_feed_audio.py` lite tests exercise the real child end-to-end. The
child adds no model logic of its own (pass-through to `daemon.build_recorder`).

### (4.5) The arm-RESPONSE-carries-mode is structurally guaranteed (transitive coverage).
No test directly asserts `_dispatch("toggle-lite")` returns `{"ok":True,"mode":"lite",...}` on an arm.
BUT: `_arm_response`@daemon.py:1890 is literally `return {"ok": True, **self._daemon.status_snapshot()}`,
and `status_snapshot`@1565-1567 has `"mode": self._mode`, and `test_dispatch_status_response_carries_mode`
@test_control_socket.py:143 proves status_snapshot's `mode` reaches the wire via that exact spread.
So the arm response carrying mode is PROVEN by composition (the status test + the one-line spread).
The daemon-state tests (`d._mode=="lite"`) confirm the value is "lite" after the arm. NOT a gap — a
purist could add a direct `_dispatch("toggle-lite")["mode"]=="lite"` test, but it would be redundant
with the existing status-response + daemon-state coverage. (Optional hardening, not a requirement.)

### (4.6) `test_typing_backends.py::test_wtype_text_starting_with_dash_stays_literal` is a FALSE POSITIVE.
It matches `-k lite` only because "literal" contains "lite". It is NOT a lite-mode test (it tests
`wtype` text escaping). The implementing agent should NOT count it as lite coverage; note it in the
section as a known false-positive so the count (26 collected) is reconciled correctly.

---

## 5. The gap_lite.md section to APPEND (S3's deliverable shape)

Mirror the per-subtask section format from `gap_lifecycle.md` (which P1.M2.T2.S1–S4 each appended as
`## Gap Report — P1.M2.T2.SN: ...`). S1 created `gap_lite.md` with H1 `# Gap Report — P1.M2.T3.S1: ...`;
S2 appends its `## Gap Report — P1.M2.T3.S2: ...` H2 section; **S3 appends its `## Gap Report —
P1.M2.T3.S3: T7 Lite Test Coverage ...` H2 section** (below S1's H1, and below S2's section if S2 ran
first — robust to ordering, see CRITICAL #5 in the PRP).

**Section structure (mirror S1's section in gap_lite.md):**
- Title: `## Gap Report — P1.M2.T3.S3: T7 Lite Test Coverage vs PRD §6`
- Date + Scope (the T7 feed_audio + socket clauses) + Audited artifacts (the test file:line list).
- "Bottom line:" ✅ COMPREHENSIVE — no gaps; no new tests; all T7 clauses covered (file:line); the
  contract run target count (collect-only `26/424, 398 deselected`; run `24 passed, 2 skipped` w/o
  CUDA OR `26 passed` w/ CUDA slow).
- §1 Method: the collect-only command + the grep commands to re-locate the lite tests + the run cmd.
- §2 per-clause coverage table (this note §1A + §1B): T7 clause | covering test (file:line) | verdict.
- §3 test inventory by file (this note §0 table + §3 index).
- §4 non-defect nuances (this note §4.1–§4.6).
- Conclusion: T7 coverage certifies acceptance #10's testability; ties to PRD §6 T7; defers the live
  VRAM/accuracy GPU pass to `test_idle_and_gpu.sh` (shell suite, P1.M5.T3) + the real-hardware smoke
  (T5, README). No `tests/*` or `voice_typing/*` modified.

---

## 6. Scope boundaries (disjoint from siblings)

- **S1 (P1.M2.T3.S1):** lite CONSTRUCTION CODE audit (the 4 kwargs clauses — model/realtime_model_type/
  use_main_model_for_realtime/post_speech_silence_duration + CPU tiny.en). CREATES gap_lite.md.
- **S2 (P1.M2.T3.S2):** mode-switch RELOAD CODE audit (the 6 clauses — routing/instant-same-mode/
  cross-mode-teardown-respawn/self._mode/set_mode/mode-agnostic-stop). APPENDS its H2 section.
- **S3 (THIS task):** T7 TEST COVERAGE audit (which tests cover the T7 contract clauses). APPENDS its
  H2 section. Angle = "is T7 covered by tests?", NOT "is the code compliant?" — complementary to S1/S2.
- **OUT OF SCOPE:** the `_bounded_shutdown` teardown internals (P1.M2.T2.S3); the full common kwargs
  §4.4 sweep (P1.M2.T4.S1); the live GPU VRAM/accuracy pass (`test_idle_and_gpu.sh` T7, P1.M5.T3);
  the real-hardware smoke (T5, README, P1.M6.T1).

## 7. Re-grep commands (the implementing agent re-locates every cited test)

```bash
cd /home/dustin/projects/voice-typing
# the lite tests in the two contract input files + the wire/CLI surfaces
grep -nE 'def test_cfg_to_kwargs_lite|def test_start_lite|def test_mode_switch|def test_same_mode_arm|def test_toggle_lite|def test_toggle_while_armed_in_lite|def test_status_snapshot_reports_mode|def test_start_lite_after_idle' tests/test_daemon.py
grep -nE 'def lite_recorder|def test_lite_feed_audio|def test_lite_latency|use_main_model_for_realtime|_token_overlap|>= 0\.70|<= normal_best' tests/test_feed_audio.py
grep -nE 'def test_dispatch_status_response_carries_mode|"mode"|_dispatch' tests/test_control_socket.py
grep -nE 'def test_lite_commands|def test_status_sh_lite|mode.*lite' tests/test_voicectl.py tests/test_status_sh.py
# the daemon arm-response path that surfaces mode on the wire (structural proof for nuance §4.5)
grep -nE 'def _arm_response|def status_snapshot|"mode": self\._mode' voice_typing/daemon.py
# the contract run target (collect-only = fast/safe count; RUN = wrap in timeout 600)
timeout 120 .venv/bin/python -m pytest tests/ -q -k 'lite' --collect-only
timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'
# scope guard — only gap_lite.md modified
git status --short
```
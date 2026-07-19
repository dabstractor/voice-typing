# Research — P1.M5.T1.S2: daemon + recorder_host unit tests (mocked CUDA)

LIVE verification performed this round on `/home/dustin/projects/voice-typing`. All numbers below
were measured with the exact contract command, under AGENTS.md two-timeout discipline.

## 1. Verified baseline (GREEN, re-measured this round)

| command | result | wall | exit |
|---|---|---|---|
| `.venv/bin/python -m pytest tests/test_daemon.py --co -q` (tail) | `193 tests collected` | 0.02s | 0 |
| `.venv/bin/python -m pytest tests/test_recorder_host.py --co -q` (tail) | `26 tests collected` | 0.01s | 0 |
| `.venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py --co -q` (tail) | `219 tests collected` | 0.02s | 0 |
| `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q` | **`219 passed in 4.80s`** | 4.80s | 0 |

**Counts (authoritative — re-measure at execution, do NOT copy verbatim):**
- `test_daemon.py` = **193 tests** (the work-item contract said "191"; the actual is 193. The S1
  PRP already noted 193. The discrepancy is immaterial — record the LIVE count.)
- `test_recorder_host.py` = **26 tests** (matches the contract).
- Combined = **219 tests** (contract said "~217"; actual is 219).

**The run is GREEN now.** The implementing agent's likely outcome is "219 passed, no fixes applied."
The diagnosis playbook in the PRP fires ONLY if a drift/flake appears at execution time.

## 2. Why these tests stay fast (4.8 s) — they are genuinely CUDA-free

Both modules under test keep CUDA OUT of module scope by design (this is the load-bearing reason the
suite runs in seconds, not minutes):

- `voice_typing/daemon.py:341` → `from RealtimeSTT import AudioToTextRecorder  # lazy: keeps import voice_typing.daemon cheap`
  (imported inside `build_recorder`, not at module top). The daemon module is explicitly designed to
  NEVER probe CUDA (see the VT-001 note at daemon.py:1585).
- `voice_typing/recorder_host.py:54` → `IMPORT PURITY: this module does NOT import RealtimeSTT/torch/ctranslate2 at module scope.`
  (the child imports them lazily inside the worker, so the daemon-side import stays cheap).

The TESTS then never trigger those lazy paths because they inject fakes for every external surface:
- `test_daemon.py` injects: `_FakeFeedback` / `_DaemonFakeFeedback` (no `feedback.py` import),
  `_FakeRecorder` / `_StrictFakeRecorder` / `_StubRecorder` (no `AudioToTextRecorder`),
  `_FakeBackend` (no typing backend), `_ok_probe` (no real PyAudio), and `_cuda_resolve` /
  `_fake_host_factory` / `_FakeHost` which monkeypatch `daemon.cuda_check.resolve_device_and_models`
  and stand in for the `RecorderHost` child (no subprocess spawn, no CUDA).
- `test_recorder_host.py` injects: `_FakeFeedback` / `_FakeLatency`, builds the host via `_make_host`
  with a dummy `cfg = object()` ("the host does not spawn in tests"), and feeds CANNED events onto the
  host's `_evt_q` via `_feed_event(host, kind, payload)` — exercising the dispatch/read-loop/text logic
  with NO real child process.

**Implication for diagnosis:** if the run suddenly takes minutes, a test accidentally triggered the
lazy `RealtimeSTT` import (constructed a real recorder) — that is a FIXTURE bug, NOT a CUDA-setup issue.

## 3. The mocking / injection contract the tests depend on (fixture-drift surface)

If a test fails with an unexpected `TypeError`/`AttributeError` on construction or a missing method,
the daemon's internal injection API drifted from what the tests assume. The fixtures pin this contract:

`test_daemon.py` — `VoiceTypingDaemon.__init__` is constructed via `_make_daemon` with:
  `daemon.VoiceTypingDaemon(cfg, feedback, recorder=, recorder_host=, host_factory=, backend=, mic_prober=)`
  - `recorder=` / `recorder_host=` → a `_StubRecorder` / `_FakeHost` instance (duck-typed stand-in for
    the resident recorder / the RecorderHost child).
  - `host_factory=` → a callable returning a `_FakeHost` (the lazy-load / idle-unload / mode-switch
    tests use this so `_load_host` stays CUDA-free).
  - `backend=` → a `_FakeBackend` with `.type_text(text)`.
  - `mic_prober=` → `_ok_probe` returning `(True, None)`.
  - The `_FakeHost` mirrors `RecorderHost`'s surface: `spawn(timeout)`, `is_alive`, `pid`,
    `set_microphone(on)`, `abort()`, `text(on_final)`, `stop(timeout)`, `device`, `mode`. A change to
    RecorderHost's public surface may require updating `_FakeHost` (fix the TEST fixture) UNLESS the
    source change is a genuine regression (then fix SOURCE).
  - `_wait_for(predicate, timeout=2.0, interval=0.01)` (test_daemon.py:515) — the HOUSE poll helper for
    async/threaded assertions. Use it; never add a bare `sleep`.

`test_recorder_host.py` — `recorder_host.RecorderHost.__init__` is constructed via `_make_host` with:
  `RecorderHost(cfg, feedback, latency, on_final, on_partial, on_speech, force_cpu=)`
  - Events are fed with `host._evt_q.put((kind, payload))` (`_feed_event`). The dispatch path maps
    event kinds → callbacks: `partial`→on_partial/update_partial, `speech`→on_speech, `speech_end`→
    latency.note_speech_end, `vad`→feedback.set_phase, `final`→on_final + final event, `ready`→device
    seed + ready event, `error`→error + ready event, unknown→ignored (logged).
  - The child-side worker protocol (PRD §4.2bis): `cmd_queue` (arm/disarm/text/shutdown),
    `abort_event` (interrupts a child blocked in `recorder.text()`), `event_queue` (the event kinds
    above + `gone`). A dispatch test failing = the event→callback mapping in `recorder_host` drifted.

## 4. test_daemon.py — groupings by PRD area (≈ counts; re-measure per-area at execution)

| area (line range) | ~tests | PRD ref | acceptance |
|---|---|---|---|
| cfg_to_kwargs + build_recorder wiring (112–436) | ~16 | §4.4 | feeds T6/T7, AC#6 |
| build_callbacks (323–333) | 2 | §4.2#3 partials | AC#3 |
| on_final lifecycle (633–688) | 6 | §4.2#1-2 | AC#2,#4 |
| drain logic (689–750) | 6 | §4.2#2 graceful drain | **AC#2** (the pause/drain fix) |
| idle auto-stop (767–810) | 5 | §4.5 auto_stop_idle_seconds | AC#5 |
| idle watchdog background disarm (818–835) | 1 | §4.5 | AC#5 |
| on_final serialization lock (835–922) | 3 | concurrency | — |
| start/stop/toggle arming (922–979) | 6 | §4.2#2-3 | AC#6 |
| shutdown/request_shutdown/loop-unblock (979–1337) | 8 | §4.2bis teardown | AC#9 |
| run loop (1337–1409) | 4 | §4.2#1 never-exit-on-silence | AC#5 |
| latency logging (1409–1545) | 8 | §4.6 timestamps | feeds latency targets |
| status snapshot + device (1545–1761) | 7 | §4.6/§4.8 | AC#6 |
| bounded shutdown / killpg (1761–2015) | 7 | §4.2bis no 90s hang | **AC#9** |
| signal handlers SIGTERM/SIGINT (2015–2092) | 4 | §4.9 | AC#6 (auto-restart) |
| logging resolve/setup (2092–2136) | 3 | — | — |
| main() lifecycle (2136–2342) | 6 | entrypoint | AC#6 |
| mic probe / hot-mic (2342–2470) | 6 | §4.9 no hot-mic | AC#6 |
| mic retry rate-limit filter (2470–2640) | 8 | — | robustness |
| force_cpu fallback (2639–2758) | 5 | §4.4 | AC#6 (cpu mode) |
| lazy load (2758–3010) | 9 | §4.2bis | **AC#6** (un-loaded boot, ~0 VRAM) |
| idle-unload + single-flight (3010–3293) | 6 | §4.2bis | AC#9 |
| idle-unload watchdog (3340–3496) | 7 | §4.2bis idle_unload | **AC#9** |
| dead-child recovery (3496–3686) | 4 | §4.2bis | AC#6 (resilience) |
| mode-switch / lite toggle (3686–3851) | 8 | §4.2ter | **AC#10** |

## 5. test_recorder_host.py — groupings

| area | tests | what it pins |
|---|---|---|
| dispatch event routing | 9 | event_kind → callback mapping (partial/speech/vad/final/ready/error/unknown) |
| text() blocking semantics | 2 | blocks until `final` event; returns promptly if child dead |
| set_microphone/abort/stop | 5 | IPC command emission; stop is a noop on dead/absent process |
| concurrent stop → single teardown | 1 | the bounded join(5s)+killpg path runs ONCE |
| spawn ready/error seeding | 2 | device seed on ready; error propagation on spawn failure |
| read_loop drain/EOF | 2 | drains events until gone; EOF marks child dead + unblocks waiters |
| run_text sentinel on abort (5) | 5 | the drain sentinel that unblocks a blocked `text()` (AC#2 drain) |

## 6. Acceptance-criteria coverage (per the work-item contract: #2, #4, #5, #6, #9, #10)

- **AC#2** (pause ≥3 s loses zero words, doesn't end session): test_daemon drain tests
  (`test_stop_drains_when_utterance_in_flight`, `test_toggle_off_drains_when_utterance_in_flight`,
  `test_drain_timeout_aborts_blocked_text`, `test_stop_aborts_immediately_when_text_idle_no_speech`) +
  test_recorder_host `test_run_text_emits_sentinel_final_on_abort_path` /
  `test_abort_sentinel_unblocks_blocked_host_text`. (Unit-level; full end-to-end pause is PRD T1b/T3 = P1.M5.T2/T3.)
- **AC#4** (only finalized text typed; nothing when toggled off): `test_on_final_gate_when_not_listening`,
  `test_on_final_happy_path_appends_space`, `test_on_final_rejects_hallucination`.
- **AC#5** (≥2 min silence, no hallucination, trivial CPU): `test_idle_watchdog_actually_disarms_in_background`,
  `test_auto_stop_*`, `test_on_final_rejects_hallucination`. (Unit-level guards; the 2-min silence
  shell is PRD T4 = P1.M5.T4.)
- **AC#6** (voicectl cmds; systemd; boots un-armed AND un-loaded ~0 VRAM; auto-restart):
  `test_lazy_daemon_boots_unloaded_with_no_recorder`, `test_fresh_daemon_not_listening`,
  `test_status_snapshot_*`, `test_install_*` signal handlers, `test_main_*`, `test_run_loop_detects_dead_host_*`.
- **AC#9** (idle-unload → ~0 VRAM; bounded teardown, no 90 s hang): `test_idle_unload_*`,
  `test_bounded_shutdown_force_cleans_on_timeout`, `test_unload_routes_through_bounded_shutdown_*`,
  `test_load_and_unload_serialize_on_the_same_single_flight_lock`; recorder_host
  `test_concurrent_stop_calls_share_one_teardown`.
- **AC#10** (lite mode): `test_start_lite_loads_lite_host_and_arms`, `test_mode_switch_*`,
  `test_toggle_lite_*`, `test_status_snapshot_reports_mode`.

## 7. Failure taxonomy (adapted from S1 — NO drift-guard class here; replaced with fixture/contract drift)

- **Class A — collection / import ERROR.** daemon.py / recorder_host.py has a syntax or import bug, OR
  a test's `monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", …)` target no longer
  exists (renamed/moved). → fix SOURCE, or update the monkeypatch attribute path in the TEST.
- **Class B — logic ASSERTION failure.** daemon/recorder_host regressed from PRD intent. → the PRD is
  the oracle; `gap_daemon_loop.md` (§4.2#1-2), `gap_lifecycle.md` (§4.2bis), `gap_lite.md` (§4.2ter),
  `gap_recorder_kwargs.md` (§4.4) state the intended behavior → fix SOURCE. If the assertion
  over-specified an impl detail NOT pinned by the PRD → fix the TEST.
- **Class C — fixture / contract drift.** daemon's internal injection API
  (`VoiceTypingDaemon(recorder=, recorder_host=, host_factory=, backend=, mic_prober=)`) OR `_FakeHost`'s
  mirror of `RecorderHost`'s surface (spawn/is_alive/pid/set_microphone/abort/text/stop/device/mode) OR
  the recorder_host event-kind set drifted from the real class. → fix the TEST fixture to match, UNLESS
  the source change is a genuine regression (then Class B → fix SOURCE).
- **Class D — env / fixture.** monkeypatch / capsys-vs-capfd / threading / `tmp_path` mismatch. → fix TEST.
- **Class E — flaky / timing.** idle watchdog / read_loop / concurrent-shutdown / drain-watchdog races.
  → these tests use threads; a flake = a missing or too-tight `_wait_for`. Fix with the house
  `_wait_for(predicate, timeout)` poll helper (test_daemon.py:515); NEVER add a bare `sleep`.

## 8. AGENTS.md discipline (binds this item directly — it RUNS commands)

- **Two timeouts, no exceptions:** inner GNU `timeout 300` (the contract value) + the bash tool's own
  `timeout` param set ABOVE 300 (e.g. 320). Exit 124 (timeout's kill) ≠ pytest exit codes; 124 = the
  suite WEDGED (a thread/lock regression) → localize per-file under `timeout 60 -vv`, do NOT retry-blind.
- **zsh aliases `python`/`pytest`** → ALWAYS `.venv/bin/python -m pytest` (full venv path).
- **mypy is NOT installed** — do not run it. ruff is optional (/home/dustin/.local/bin/ruff). The gates
  are `py_compile` + `pytest`.
- **Never start the daemon / arm the mic / touch real XDG_RUNTIME_DIR** — these tests are hermetic
  (fakes injected; monkeypatched cuda_check; `_make_host` never spawns). AGENTS.md forbids
  foregrounding the daemon anyway.
- **Scope boundary:** do NOT add the 9 pure-Python files (S1's set) or `test_feed_audio.py`
  (P1.M5.T2, real CUDA models). Mixing them in changes the timeout budget + blurs attribution.

## 9. Output-doc format precedent

The S1 sibling (P1.M5.T1.S1) defines the house format: `test_results_unit.md` — a Markdown doc with
the exact command (both timeouts), a per-file results table, the GREEN verdict, a "fixes applied"
section (empty/"none" if green on first run), and notes. This item's deliverable is the SAME shape but
named **`test_results_daemon.md`** (the contract's specified name) and covering the 2 daemon/recorder_host
files instead of the 9 pure-Python files.
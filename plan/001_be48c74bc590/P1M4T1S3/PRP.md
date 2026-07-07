# PRP — P1.M4.T1.S3: Per-utterance latency logging (timestamps the tests read)

## Goal

**Feature Goal**: Add **structured per-utterance latency logging** to `VoiceTypingDaemon` (the S2
class now in `voice_typing/daemon.py`, 134 tests green). For every finalized, typed utterance,
capture **t_speech_end** (when VAD closed — from the `on_vad_stop` callback), **t_final_ready**
(on_final entry), **t_typed** (right after `backend.type_text`), the **final text**, and the
**partial count** — and emit them as a single greppable structured log line that the latency tests
(P1.M7.T2.S1 `test_feed_audio`, P1.M7.T4.S1) parse to assert PRD §6 targets (final-typed ≤1.5 s
after end-of-utterance). Also log the **resolved device/models at daemon startup** (proves CUDA
residency — PRD acceptance T6 + the item's "log device" instruction), and add a **`[log] level`
config knob** so `DEBUG` surfaces the raw monotonic timestamps. Keep a small **bounded ring buffer**
of recent utterance records queryable by `latency.snapshot()` for the future `status` command
(P1.M4.T2.S1) and directly by tests.

**Deliverable** (5 files — 3 MODIFY, 2 ADD-tests; this subtask CREATES NO new module):
1. `voice_typing/daemon.py` — ADD the `LatencyLog` class + `_LATENCY_LOG_PREFIX`/`_LATENCY_RING_SIZE`
   constants + `_ms()` helper + `import collections`; ADD an **optional `latency=None` parameter**
   to `_build_callbacks`/`_construct`/`build_recorder` (threading the latency collector into the
   `on_vad_stop`/partial callbacks — backward-compatible); MODIFY `VoiceTypingDaemon.__init__`
   (create + thread `self._latency`), `run()` (startup device/models log + set log level from
   config), and `on_final` (capture `t_final_ready`/`t_typed`, call `finalize_utterance`, emit the
   structured INFO line + a DEBUG line). **Do NOT change S1/S2 logic or assertions** — every edit is
   additive/optional-default (see "Backward-compatibility proof" in the research doc).
2. `voice_typing/config.py` — ADD `LogConfig` dataclass (`level: str = "INFO"`) + a `log` field on
   `VoiceTypingConfig` (additive; all existing configs unchanged).
3. `config.toml` — ADD a `[log]` section (`level = "INFO"`).
4. `tests/test_config_repo_default.py` — ADD `"log": {"level"}` to the expected schema (the drift
   guard; mirrors the new config section so it still passes).
5. `tests/test_daemon.py` — APPEND ~10 tests: `LatencyLog` unit tests (note_partial/note_speech_end/
   finalize/reset/ring buffer/snapshot), `_build_callbacks(fb, latency)` wiring (partial→note_partial,
   on_vad_stop→note_speech_end, `latency=None` no-op), `on_final` emits the parseable latency line +
   populates the ring buffer (via `caplog` + regex), and `run()` logs the resolved device/models at
   startup. Also `tests/test_config.py` — ADD 1 test that `LogConfig.level` defaults to `"INFO"` and
   is overridable from TOML.

**Success Definition**:
- (a) `voice_typing/daemon.py` + `voice_typing/config.py` + the two test files `py_compile`-clean;
  `import voice_typing.daemon` still binds NO heavy import (`RealtimeSTT`/`torch`/`ctranslate2`) at
  module top (import purity unchanged); `LatencyLog` is a module attribute; `VoiceTypingDaemon` still
  present.
- (b) `LatencyLog` exists with `note_partial(text)`, `note_speech_end()`, `finalize_utterance(*, text,
  t_final_ready, t_typed) -> dict`, `snapshot() -> list[dict]`. `finalize_utterance` returns a record
  whose deltas are correct (`total_ms == (t_typed-t_speech_end)*1000`, rounded to 0.1 ms), resets the
  partial counter + t_speech_end, and appends to a bounded ring buffer (newest last); `snapshot()`
  returns a copy.
- (c) `_build_callbacks(fb, latency)`: when `latency` is a `LatencyLog`, firing
  `on_realtime_transcription_stabilized("x")` increments its partial count AND still calls
  `feedback.update_partial`; firing `on_vad_stop()` records `t_speech_end` AND still calls
  `feedback.set_phase("listening")`. When `latency=None`, behavior is byte-for-byte the S1 behavior
  (S1's `_build_callbacks` tests still pass).
- (d) `VoiceTypingDaemon.on_final` (listening armed, valid text) emits exactly ONE INFO log line
  beginning with the prefix `voice-typing latency: event=utterance_final` and containing the keys
  `speech_end_to_final_ms=`, `final_to_typed_ms=`, `total_ms=`, `partials=`, `ts_epoch=`, `text=`;
  AND appends one record to `self._latency.snapshot()`; AND still types (via backend) + records
  (via feedback) exactly as S2 (`be.typed == ["hello world "]`, `fb.finals == ["hello world"]`).
- (e) When no `on_vad_stop` preceded the final (`t_speech_end is None`), the line still emits with
  `speech_end_to_final_ms=n/a` and `total_ms=n/a` (no crash); `final_to_typed_ms` is always a number.
- (f) `run()` logs at startup a line containing `device=`, `compute_type=`, `final_model=`,
  `realtime_model=` (the resolved config from `_resolve_device_config`); a device-resolution failure
  is caught (try/except) so the loop never breaks. `run()` sets
  `logging.getLogger("voice_typing").setLevel(cfg.log.level.upper())`.
- (g) `[log] level` config: `VoiceTypingConfig().log.level == "INFO"`; parsing a TOML with
  `[log] level = "DEBUG"` yields `level == "DEBUG"`; `<repo>/config.toml` parses with no drift over
  the dataclass defaults (`test_config_repo_default.py` passes with the updated schema).
- (h) **Backward compatibility**: the existing 134 tests pass UNCHANGED (no edits to S1/S2 test
  bodies); S3's ~10 new tests pass; `.venv/bin/python -m pytest tests/ -q` is green (~144 passed).
- (i) **No out-of-scope code:** NO control socket (`socket.socket`/`json.loads`), NO `main()`/`if
  __name__ == "__main__":`, NO signal handlers, NO `logging.basicConfig` (level is set on the
  `voice_typing` namespace logger only; handler/root config is P1.M4.T3.S1), NO
  `recorder.shutdown()`, NO edits to `feedback.py`/`typing_backends.py`/`textproc.py`/`cuda_check.py`/
  `uv.lock`/`pyproject.toml`/`PRD.md`/`tasks.json`/`.gitignore`.

## User Persona

**Target User**: Internal — two future consumers read these artifacts:
1. **P1.M7.T2.S1 (`test_feed_audio.py`)** — feeds WAVs via `recorder.feed_audio()` in-process,
   captures the daemon's log (pytest `caplog` / stderr), and parses the
   `voice-typing latency: event=utterance_final …` line to assert `final callback ≤ 1.5 s` after the
   last speech sample (PRD §6 T1e). It also reads the partial count + the startup `device=` line.
2. **P1.M4.T2.S1 (control socket `status` cmd)** — may later surface `daemon._latency.snapshot()`
   (the ring buffer) as a `latency` field in the status JSON. S3 only PROVIDES `snapshot()`; wiring
   it into the socket is out of scope.

A human operator is the tertiary consumer: under systemd, these INFO lines flow to journald
(`journalctl --user -u voice-typing`); `DEBUG` adds the raw monotonic timestamps for triage when
finals exceed the 1.5 s target (PRD §6: "ensure both models are on CUDA — log device").

**Use Case**: The daemon is running, armed, the user speaks. VAD detects speech end → `on_vad_stop`
fires → `LatencyLog.note_speech_end()` stamps `t_speech_end`. After the 0.6 s segmentation pause the
utterance finalizes → `recorder.text()` returns the final → `on_final(text)` fires →
`t_final_ready = time.monotonic()` → clean → type → `t_typed = time.monotonic()` →
`finalize_utterance()` computes the deltas, appends to the ring buffer, and `on_final` logs the
structured line. The latency test asserts `total_ms ≤ 1500`. If it ever exceeds, the operator reads
the startup `device=cuda` line (proves residency) then tunes per PRD §6.

**Pain Points Addressed**: (1) PRD §6 latency targets are currently UNMEASURABLE — S2 logs only a
bare `final typed: %r`; S3 makes them measurable + assertable. (2) CUDA residency is currently
unproven in logs — S3 logs the resolved device/models at startup (acceptance T6 correlation). (3)
Cross-cutting debuggability — a single greppable line per utterance + a ring buffer the status cmd
can read.

## Why

- **This is the contract the test plan depends on.** PRD §6 T1e asserts "final callback ≤ 1.5 s after
  last speech sample fed"; T6 asserts GPU residency. S2 explicitly DEFERRED the precise timestamps
  (its `on_final` ends with `# NOTE: precise latency timestamps … land in P1.M4.T1.S3.`). S3 is
  where those timestamps become real, parseable, and assertable.
- **t_speech_end is non-trivial to capture.** It lives in the `on_vad_stop` callback, which S1 wired
  inside `_build_callbacks(feedback)` — closed over `feedback` only. Threading an optional
  `LatencyLog` through `_build_callbacks`/`_construct`/`build_recorder` is the ONLY clean, reliable
  way to observe it (feedback-proxy can't distinguish `on_vad_stop` from `on_vad_detect_start`; both
  call `set_phase("listening")`). Research doc §1 documents the rejected alternatives.
- **Ring buffer > ephemeral log for status.** The `[log]` line is for journald + the in-process test;
  the bounded ring buffer (`collections.deque(maxlen=64)`) lets the future `voicectl status` show the
  last N utterances' latencies without scraping logs. S3 provides `snapshot()`; T2.S1 wires it.
- **Config-driven verbosity.** `INFO` ships the per-utterance line (low volume: one per utterance);
  `DEBUG` adds raw monotonic timestamps. This matches PRD §4.2 "logging … at INFO; DEBUG via config"
  without S3 reaching into root-logger/handler setup (T3's job).

## What

Add a `LatencyLog` collector + structured per-utterance + startup logging to the daemon. The
**exact edits** are pinned in "Implementation Tasks" below as surgical oldText→newText blocks against
the LIVE merged `voice_typing/daemon.py` (S1+S2; read it at preflight). All daemon edits are
additive or optional-default so S1/S2 tests stay green (research §6).

### The structured log lines (exact formats — tests depend on these strings)

Per-utterance (INFO, emitted by `on_final` after `record_final`):
```
voice-typing latency: event=utterance_final speech_end_to_final_ms=<num|n/a> final_to_typed_ms=<num> total_ms=<num|n/a> partials=<int> ts_epoch=<float> text=<repr>
```
Per-utterance raw timestamps (DEBUG):
```
voice-typing latency debug: t_speech_end=<float|n/a> t_final_ready=<float> t_typed=<float>
```
Startup device/models (INFO, emitted once by `run()`):
```
voice-typing device resolved: device=<cuda|cpu> compute_type=<float16|int8> final_model=<str> realtime_model=<str>
```

`<repr>` = Python `%r` of the cleaned text (quotes + escapes spaces/punct safely). When
`t_speech_end is None`, the two derived ms fields render `n/a`; `final_to_typed_ms` is always numeric.

### Success Criteria

- [ ] `LatencyLog` has `note_partial`/`note_speech_end`/`finalize_utterance`/`snapshot` with the
  record schema in research §2 (keys: `event, t_speech_end, t_final_ready, t_typed,
  speech_end_to_final_ms, final_to_typed_ms, total_ms, partials, text, ts`).
- [ ] `finalize_utterance` computes correct deltas (round to 0.1 ms), resets partial count +
  t_speech_end to 0/None, and appends to a `deque(maxlen=64)`; `snapshot()` returns newest-last copy.
- [ ] `_build_callbacks(fb, latency)`: partial→note_partial + update_partial; on_vad_stop→
  note_speech_end + set_phase("listening"); `latency=None` ⇒ S1 behavior unchanged.
- [ ] `on_final` (armed + valid text) logs the INFO latency line (prefix
  `voice-typing latency: event=utterance_final`) AND appends a ring-buffer record AND types+records
  exactly as S2.
- [ ] `on_final` with no prior `on_vad_stop` ⇒ line still emits, `*_ms=n/a`, no crash.
- [ ] `run()` logs the resolved device/models line (4 keys present) at startup; resolution failure is
  swallowed (loop unaffected); `run()` sets the `voice_typing` logger level from `cfg.log.level`.
- [ ] `[log] level` config round-trips (default `"INFO"`, overridable to `"DEBUG"`); repo
  `config.toml` has no drift vs dataclass defaults (drift test updated + green).
- [ ] `import voice_typing.daemon` stays import-pure (no heavy module-top imports; `collections`
  added is stdlib-cheap).
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~144 passed); S1+S2 test bodies UNCHANGED.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the work-item contract + the exact
LatencyLog design + the structured log formats are pinned in the research doc (§2/§3); the consumed
APIs (`_build_callbacks`, `_construct`, `build_recorder`, `on_final`, `run`, `_resolve_device_config`,
`VoiceTypingConfig`, the S2 `_make_daemon` test helper) are read at preflight against the LIVE source
below; the edits are specified as surgical oldText→newText blocks; and the validation commands are
executable as written (py_compile, import-purity grep, pytest, a stub-injection log smoke).

### Documentation & References

```yaml
# MUST READ — the work-item contract (verbatim, authoritative design).
- file: plan/001_be48c74bc590/P1M4T1S3/research/latency_logging_design.md
  why: "§1: WHY t_speech_end/partial-count must be threaded through _build_callbacks (the crux) +
        the rejected alternatives (feedback-proxy can't distinguish on_vad_stop from
        on_vad_detect_start; post-construction monkey-patch is brittle). §2: the LatencyLog design
        (verbatim class + record schema + ring buffer + thread-safety). §3: the EXACT structured log
        line formats tests parse. §4: the startup device/models log. §5: the [log] config + blast
        radius. §6: the backward-compat proof (S1/S2 tests stay green). §8: validation gates."
  critical: "This doc IS the spec. The latency line prefix `voice-typing latency:` and the key names
             (speech_end_to_final_ms/final_to_typed_ms/total_ms/partials/ts_epoch/text) are STABLE
             contracts — do not rename them (T1 parses them). `n/a` is the sentinel for a missing
             t_speech_end. finalize_utterance resets counters AFTER reading them (under the lock)."

# MUST READ — the module being MODIFIED (live S1+S2 merged state; 134 tests green).
- file: voice_typing/daemon.py
  why: "The exact starting point. S1 surface: _resolve_device_config, cfg_to_kwargs, _build_callbacks
        (1 param), _filter_kwargs_to_signature, _construct (3 params), build_recorder (2 params),
        _FIXED_KWARGS, _PARTIAL_CALLBACK_ATTR. S2 surface: VoiceTypingDaemon (__init__/run/on_final/
        _arm/_disarm/start/stop/toggle/request_shutdown/is_listening/uptime_s). The imports at top are
        inspect/logging/threading/time/typing + textproc/typing_backends/cuda_check/config. S3 ADDS
        `import collections` + LatencyLog + the optional latency param to the 3 S1 functions + the
        on_final/run/__init__ edits. module-top `logger = logging.getLogger(__name__)` already exists."
  critical: "Apply the EXACT oldText→newText edits in Implementation Tasks — they are pinned to this
             file's current text. Do NOT reorder or rewrite S1/S2 functions; the edits are surgical.
             The on_final edit appends latency capture AFTER the existing record_final call (S2
             behavior preserved). The run() edit ADDS two helper calls before the existing ready log
             line; do NOT change the loop. _resolve_device_config already exists (S1) — reuse it for
             the startup log (do NOT re-probe cuda_check ad hoc)."

# MUST READ — the consumed config (being EXTENDED with [log]).
- file: voice_typing/config.py
  why: "VoiceTypingConfig aggregates AsrConfig/OutputConfig/FeedbackConfig/FilterConfig via
        dataclass fields with default_factory. from_toml() overlays each [section] table onto its
        dataclass via _overlay() — a NEW [log] section works identically (add LogConfig + a `log`
        field + 'log' to from_toml's overlay calls). The repo-default drift test pins the EXACT
        schema, so config.toml + test_config_repo_default.py MUST move in lockstep."
  critical: "Add `log: LogConfig = field(default_factory=LogConfig)` to VoiceTypingConfig AND add
             `log=_overlay(LogConfig, 'log')` to from_toml's return. Unknown TOML keys raise
             TypeError (dataclass __init__) — that's desired (a typo'd [log] key surfaces loudly).
             Do NOT add compute_type here (cuda_check concern, per the module docstring)."

# MUST READ — the S1+S2 tests (the regression baseline S3 must NOT break).
- file: tests/test_daemon.py
  why: "S1 tests: _build_callbacks_keys, test_callback_*, _construct_*, _filter_* (call the S1
        functions with the OLD arg counts — S3's optional latency=None must keep them green). S2
        tests: _DaemonFakeFeedback, _StubRecorder, _FakeBackend, _make_daemon(), test_on_final_*,
        test_start_*/stop_*/toggle_*, test_run_loop_*, test_request_shutdown_* (call VoiceTypingDaemon
        WITHOUT a latency arg → S3 creates a real LatencyLog in __init__; on_final's added finalize
        call + log must not change be.typed/fb.finals assertions). S3 APPENDS ~10 new tests after
        these — do NOT edit the S1/S2 test bodies."
  critical: "The _make_daemon() helper (S2) injects recorder=_StubRecorder + backend=_FakeBackend but
             NO latency → S3's __init__ default `latency=None` → `self._latency = LatencyLog()`. So
             every S2 on_final test now exercises a real LatencyLog.finalize_utterance — it must be
             no-fail (append + return; no exception). The S2 run-loop tests run run() in a thread;
             S3's added _log_resolved_device() (try/except-wrapped) + level set are log-only → do not
             change text_calls/loop-exit assertions. Reuse _make_daemon + _wait_for in S3's tests."

# MUST READ — the RealtimeSTT callback semantics (source of truth for on_vad_stop timing).
- docfile: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "§3 callback table: on_vad_stop() — no-arg — 'voice activity ends' = t_speech_end; fires
        BEFORE the utterance finalizes (final fires after post_speech_silence_duration), so
        t_speech_end ≤ t_final_ready. on_realtime_transcription_stabilized(str) = the partial feed =
        each call increments the partial count. §4: set_microphone/abort (unchanged by S3)."
  critical: "on_vad_stop is the RIGHT hook for t_speech_end (not on_recording_stop, not set_phase).
             Verify in T1 (feed_audio) that on_vad_stop fires once per utterance before the final; if
             the cadence looks off, the implementer checks post_speech_silence_duration semantics, not
             this hook choice. S3 does NOT change which callbacks S1 wired."

# MUST READ — the drift guard being UPDATED (config.toml ↔ config.py lockstep).
- file: tests/test_config_repo_default.py
  why: "Asserts <repo>/config.toml parses to EXACTLY the dataclass defaults (14 keys across 4
        sections). S3 adds a 5th section [log] with 1 key → the expected dict gains
        'log': {'level'} AND VoiceTypingConfig gains the log field (so repo_default == defaults still
        holds). The test's `expected` literal + the `set(data.keys())` assertion both need 'log'."
  critical: "Update BOTH the `expected` dict (add 'log': {'level'}) — the test will FAIL until
             config.py + config.toml + this test all move together. Do not relax the assertion (it's
             the permanent drift guard); extend it."

# Background — the prior subtask PRP (house style + the S2 on_final/run contract S3 edits).
- file: plan/001_be48c74bc590/P1M4T1S2/PRP.md
  why: "The S2 VoiceTypingDaemon design S3 edits: on_final (gate→clean→type→record_final→log), run()
        (start_monotonic, set_listening(False), ready log, loop), __init__ (recorder/backend
        injection). S3's edits are surgical additions to these exact methods. Mirror S2's PRP
        structure + scope-guard-grep style."
  critical: "S2's on_final ends with `logger.info('final typed: %r', cleaned)` + the NOTE comment.
             S3 REPLACES that tail with the latency capture + structured log (the `final typed: %r`
             line is superseded by the richer latency line — drop it, do not double-log). S2's run()
             ready log line is KEPT; S3 adds the device log + level set BEFORE it."

# Downstream — the consumers S3 feeds (do NOT build).
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M4.T2.S1 (control socket): may add `latency` to status by calling daemon._latency.snapshot()
        — S3 PROVIDES it, does not wire the socket. P1.M4.T3.S1 (entry point): reads cfg.log.level in
        basicConfig (handler attach) — S3 only sets the namespace logger level + provides the knob.
        P1.M7.T2.S1 (test_feed_audio): parses the `voice-typing latency:` line + reads partial count +
        the startup `device=` line. Confirms the contract S3 must emit."
  critical: "Do NOT add socket/main/basicConfig/signal/recorder.shutdown() here. The log line prefix
             + key names + record schema are the contract T1 + T2 rely on — do not rename them."
```

### Current Codebase tree (state at P1.M4.T1.S3 start — S1+S2 merged, 134 passing)

```bash
/home/dustin/projects/voice-typing/
├── .git/ .gitignore .venv/        # DO NOT touch .gitignore
├── PRD.md                         # READ-ONLY (§4.2 logging, §6 test targets, §4.4 device)
├── config.toml                    # P1.M2.T1.S2. MODIFY (Task 4): ADD [log] section.
├── pyproject.toml uv.lock         # DO NOT touch (no new deps — collections/logging are stdlib)
├── voice_typing/
│   ├── __init__.py                # DO NOT touch
│   ├── cuda_check.py              # READ ONLY (resolve_device_and_models; used indirectly via _resolve_device_config)
│   ├── launch_daemon.sh prefetch.py status.sh   # unrelated
│   ├── config.py                  # MODIFY (Task 3): ADD LogConfig + log field + from_toml overlay.
│   ├── textproc.py                # READ ONLY (clean — unchanged by S3)
│   ├── typing_backends.py         # READ ONLY (make_backend/type_text — unchanged)
│   ├── feedback.py                # READ ONLY (record_final/set_listening/set_phase — unchanged)
│   └── daemon.py                  # ← MODIFY (Task 2): ADD LatencyLog + collections import + optional
│                                  #   latency param on _build_callbacks/_construct/build_recorder +
│                                  #   VoiceTypingDaemon.__init__/run/on_final edits.
└── tests/
    ├── test_config.py             # MODIFY (Task 5b): ADD 1 LogConfig test.
    ├── test_config_repo_default.py# MODIFY (Task 5a): ADD 'log':{'level'} to expected schema.
    ├── test_textproc.py test_typing_backends.py test_feedback.py  # DO NOT EDIT
    └── test_daemon.py             # ← MODIFY (Task 5c): APPEND ~10 latency tests (S1/S2 tests unchanged).
```

### Desired Codebase tree with files to be added/modified

```bash
# NO new module files. 5 existing files modified (3 source-ish + 3 test = see Task list).
voice_typing/daemon.py             # +LatencyLog, +import collections, +optional latency param, +on_final/run/__init__ edits
voice_typing/config.py             # +LogConfig, +log field, +from_toml overlay
config.toml                        # +[log] section
tests/test_config_repo_default.py  # +'log':{'level'} in expected schema
tests/test_config.py               # +LogConfig default/override test
tests/test_daemon.py               # +~10 latency tests (appended)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — t_speech_end lives in on_vad_stop, wired INSIDE _build_callbacks (S1). The callback
#   closes over `feedback` ONLY. The ONLY clean way for the daemon to observe it is to thread an
#   OPTIONAL LatencyLog through _build_callbacks/_construct/build_recorder. Make the param
#   `latency=None` (default) so S1's _build_callbacks/_construct tests (called with the OLD arg
#   count) keep passing: when latency is None, the partial/on_vad_stop callbacks do NOTHING extra
#   (`if latency is not None: latency.note_*()`). (research §1.)

# CRITICAL #2 — do NOT use a feedback-proxy or post-construction monkey-patch to get t_speech_end.
#   feedback.set_phase("listening") is fired by BOTH on_vad_detect_start AND on_vad_stop →
#   indistinguishable. Monkey-patching recorder.on_vad_stop after construction is undocumented +
#   brittle. Thread the LatencyLog through _build_callbacks instead. (research §1.)

# CRITICAL #3 — on_final is fired by RealtimeSTT in a NEW thread; it must NEVER raise (would kill
#   the worker). S3 ADDS self._latency.finalize_utterance(...) + a logger.info call AFTER the
#   existing record_final. finalize_utterance is a pure compute+append (no I/O, no raise). The log
#   call is wrapped by logging's own exception handling. Do NOT add I/O or subprocess calls here.

# CRITICAL #4 — timestamps for DELTAS use time.monotonic() (immune to NTP jumps; matches S2's
#   uptime_s). The wall-clock `ts_epoch` in the record uses time.time() (for journal correlation).
#   Compute deltas in finalize_utterance from the monotonic values, round to 0.1 ms via _ms().

# CRITICAL #5 — t_speech_end may be None (no on_vad_stop preceded this final — e.g. a unit test
#   calling on_final directly, or a final that arrived without a clean VAD stop). finalize_utterance
#   MUST handle None gracefully: speech_end_to_final_ms and total_ms become None; the LOG line
#   renders them as the literal string `n/a` (so the key is always present for parsing).
#   final_to_typed_ms is ALWAYS present (t_final_ready and t_typed are always set in on_final).

# CRITICAL #6 — backward compatibility is non-negotiable. S1's _build_callbacks/_construct tests
#   and S2's on_final/run tests MUST pass UNCHANGED. Every daemon.py edit is either (a) a NEW
#   symbol (LatencyLog, constants, _ms) or (b) an OPTIONAL trailing param (latency=None) or (c) an
#   ADDITIVE tail inside on_final/run/__init__ that does not alter the S2-asserted behavior
#   (be.typed / fb.finals / text_calls / loop-exit). Re-run the FULL suite after each edit.
#   (research §6 — the proof.)

# CRITICAL #7 — the on_final edit REPLACES S2's trailing `logger.info("final typed: %r", cleaned)`
#   line + its NOTE comment with the richer latency capture + structured line. Do NOT keep BOTH
#   (double-logging per utterance). The cleaned text is still present in the latency line's
#   `text=<repr>`, so no information is lost. record_final(cleaned) stays (feedback owns last_final).

# CRITICAL #8 — the run() startup device log calls _resolve_device_config(cfg) (S1 helper) which
#   probes cuda_check. WRAP IT IN try/except so a probe failure (odd env, missing ctranslate2 in a
#   degraded run) NEVER breaks the listen loop — log a fallback line ("device resolution failed")
#   and continue. S2's run-loop tests run run() with a stub recorder (build_recorder not called) but
#   _resolve_device_config IS called here → the try/except is what keeps those tests green without
#   monkeypatching. (Do NOT move the probe into __init__ — that would make every daemon test hit the
#   real cuda_check at construction; keep it in run(), wrapped.)

# CRITICAL #9 — set the log level on the `voice_typing` NAMESPACE logger (logging.getLogger(
#   "voice_typing")), NOT root, NOT basicConfig. basicConfig (handler + root level) is P1.M4.T3.S1's
#   job. Setting the namespace level is complementary + harmless + makes the cfg.log.level knob
#   functional for descendant DEBUG records once T3 attaches a handler. Guard against an invalid
#   level string (ValueError) — leave the default on error. Tests use pytest caplog (own handler).

# CRITICAL #10 — the config drift test (test_config_repo_default.py) pins the EXACT schema. Adding
#   [log] means config.py (LogConfig + field + from_toml overlay) + config.toml ([log] table) +
#   the test's `expected` dict must ALL move together or the drift test fails. Do not relax the
#   assertion; EXTEND it with 'log': {'level'}.

# CRITICAL #11 — import purity. S3 adds `import collections` (stdlib-cheap) at module top. RealtimeSTT/
#   torch/ctranslate2 stay OUT of module top (lazy inside build_recorder, unchanged). The S1/S2
#   import-purity AST/grep check must still pass. LatencyLog references only collections/threading/time
#   (all stdlib) — no heavy imports.

# CRITICAL #12 — FULL PATHS for tooling (zsh aliases python/pytest). ALWAYS
#   `.venv/bin/python -m pytest` / `.venv/bin/python -m py_compile` (never bare python/pytest).
#   mypy is NOT installed — do NOT list it. ruff is optional (/home/dustin/.local/bin/ruff);
#   py_compile + pytest are the authoritative gates.

# GOTCHA #13 — the latency log line is the T1 PARSE CONTRACT. The prefix `voice-typing latency:` +
#   the key names (event/speech_end_to_final_ms/final_to_typed_ms/total_ms/partials/ts_epoch/text)
#   must be EXACTLY as specified (research §3). T1 will regex these. Do not reorder keys in a way
#   that breaks `key=value` tokenization (each key=value is whitespace-separated; text=<repr> is
#   last because %r may contain spaces).
```

## Implementation Blueprint

### Data models and structure

No persistent data model. `LatencyLog` (new, in `voice_typing/daemon.py`) holds transient state:

```python
self._lock: threading.Lock            # guards _records + _partial_count + _t_speech_end
self._records: collections.deque       # maxlen=64; newest-last; dict records (schema below)
self._partial_count: int               # reset to 0 on each finalize_utterance
self._t_speech_end: float | None       # set by note_speech_end; cleared on finalize_utterance
```

Per-utterance record dict (returned by `finalize_utterance`, stored in the ring buffer, the basis
for the log line):
```python
{"event": "utterance_final",
 "t_speech_end": <monotonic|None>, "t_final_ready": <monotonic>, "t_typed": <monotonic>,
 "speech_end_to_final_ms": <float|None>, "final_to_typed_ms": <float>, "total_ms": <float|None>,
 "partials": <int>, "text": <str>, "ts": <wall epoch float>}
```

`VoiceTypingDaemon` gains one attribute: `self._latency: LatencyLog` (a real one, or injected for tests).

### LatencyLog reference implementation (research §2 — implement this; place ABOVE VoiceTypingDaemon)

```python
import collections  # ADD to module-top imports (Task 2a)

_LATENCY_LOG_PREFIX = "voice-typing latency:"   # STABLE — tests (T1) grep this prefix
_LATENCY_RING_SIZE = 64


def _ms(seconds: float) -> float:
    """Seconds → milliseconds, rounded to 0.1 ms (for log readability + stable parse)."""
    return round(seconds * 1000.0, 1)


class LatencyLog:
    """Per-utterance latency capture for the latency tests (PRD §6 T1/T3; PRD §4.2 logging).

    Fed by RealtimeSTT callbacks (note_partial/note_speech_end — wired via _build_callbacks) and by
    VoiceTypingDaemon.on_final (finalize_utterance). Timestamps are time.monotonic() (delta-safe vs
    NTP); a wall epoch `ts` is added for journal correlation. A bounded ring buffer (deque maxlen)
    of recent records is queryable via snapshot() (future status cmd, P1.M4.T2.S1) + by tests.

    Thread-safe: note_partial fires on the realtime thread, note_speech_end on the VAD thread,
    finalize_utterance on the on_final worker thread, snapshot() on the socket thread — all short,
    guarded by self._lock.
    """

    def __init__(self, *, ring_size: int = _LATENCY_RING_SIZE) -> None:
        self._lock = threading.Lock()
        self._records: collections.deque = collections.deque(maxlen=ring_size)
        self._partial_count = 0
        self._t_speech_end: float | None = None

    def note_partial(self, _text: str) -> None:
        """Count a realtime partial (partial CADENCE is T1's own measurement; we just count)."""
        with self._lock:
            self._partial_count += 1

    def note_speech_end(self) -> None:
        """Record t_speech_end (on_vad_stop — VAD closed = speech ended)."""
        with self._lock:
            self._t_speech_end = time.monotonic()

    def finalize_utterance(self, *, text: str, t_final_ready: float, t_typed: float) -> dict:
        """Build + store the per-utterance record; reset counters; return the record for logging.

        t_speech_end may be None (no on_vad_stop seen) → the two *_ms fields derived from it are None
        (rendered 'n/a' in the log line); final_to_typed_ms is always numeric.
        """
        with self._lock:
            t_speech_end = self._t_speech_end
            partials = self._partial_count
            self._partial_count = 0
            self._t_speech_end = None
        record = {
            "event": "utterance_final",
            "t_speech_end": t_speech_end,
            "t_final_ready": t_final_ready,
            "t_typed": t_typed,
            "speech_end_to_final_ms": _ms(t_final_ready - t_speech_end)
                if t_speech_end is not None else None,
            "final_to_typed_ms": _ms(t_typed - t_final_ready),
            "total_ms": _ms(t_typed - t_speech_end) if t_speech_end is not None else None,
            "partials": partials,
            "text": text,
            "ts": time.time(),
        }
        with self._lock:
            self._records.append(record)
        return record

    def snapshot(self) -> list[dict]:
        """Newest-last copy of the ring buffer (for status + tests)."""
        with self._lock:
            return list(self._records)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the live S1+S2 state + consumed APIs + the 134-test baseline.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/daemon.py   && echo ok
      .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1      # expect "134 passed"
      .venv/bin/python -c "
import sys, voice_typing.daemon as d
from voice_typing.config import VoiceTypingConfig
assert hasattr(d,'VoiceTypingDaemon') and hasattr(d,'build_recorder') and hasattr(d,'_build_callbacks')
assert hasattr(d,'_resolve_device_config') and hasattr(d,'_construct')
assert not [m for m in('RealtimeSTT','torch','ctranslate2') if m in sys.modules], 'import purity broken pre-S3'
import inspect
print('_build_callbacks:', inspect.signature(d._build_callbacks))
print('_construct:', inspect.signature(d._construct))
print('build_recorder:', inspect.signature(d.build_recorder))
print('on_final source tail present:', 'NOTE: precise latency timestamps' in inspect.getsource(d.VoiceTypingDaemon.on_final))
print('cfg has log?', hasattr(VoiceTypingConfig(),'log'))
"
  - EXPECTED: 134 passed; VoiceTypingDaemon+build_recorder+_build_callbacks+_resolve_device_config+_construct present;
    import purity holds; _build_callbacks(fb) / _construct(cfg,fb,cls) / build_recorder(cfg,fb) signatures;
    on_final contains the S2 NOTE comment; cfg has NO log field yet (False).
  - DO NOT create/edit any file, run uv sync/add, or touch any other module.

Task 2: MODIFY voice_typing/daemon.py (apply the 7 surgical edits in "Task 2 SOURCE edits" below).
        Order: (2a) imports + constants + _ms + LatencyLog class; (2b) _build_callbacks optional
        latency; (2c) _construct optional latency; (2d) build_recorder optional latency;
        (2e) __init__ creates+threads self._latency; (2f) run() startup device log + level set;
        (2g) on_final latency capture + structured log (replaces S2's `final typed: %r` tail).
  - FILE: voice_typing/daemon.py (MODIFY — surgical; S1/S2 functions/behavior preserved).
  - DO NOT: change the loop in run(); change _arm/_disarm/start/stop/toggle/request_shutdown;
    rewire which callbacks S1 chose; add socket/main/basicConfig/signal/recorder.shutdown();
    move the cuda probe into __init__ (keep it in run(), wrapped — Critical #8).

Task 3: MODIFY voice_typing/config.py — ADD LogConfig + log field + from_toml overlay.
  - FILE: voice_typing/config.py. ADD (verbatim from "Task 3 SOURCE edit" below).
  - DO NOT: add compute_type; mutate existing sections; change the search order.

Task 4: MODIFY config.toml — ADD the [log] section.
  - FILE: config.toml. APPEND a [log] table (verbatim from "Task 4 SOURCE edit" below).

Task 5: MODIFY tests — (5a) test_config_repo_default.py (+ 'log':{'level'});
        (5b) test_config.py (+ LogConfig default/override test); (5c) test_daemon.py (APPEND ~10
        latency tests — see "Task 5c SOURCE additions"). Write tests FIRST where possible (TDD).
  - FILES: tests/test_config_repo_default.py, tests/test_config.py, tests/test_daemon.py.
  - DO NOT edit S1/S2 test bodies. APPEND only. Reuse _make_daemon/_wait_for/_DaemonFakeFeedback.

Task 6: VALIDATE — run the Validation Loop L1–L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M4.T1.S3: per-utterance latency logging (LatencyLog + structured log + device log + [log] cfg)".
```

#### Task 2 SOURCE edits — `voice_typing/daemon.py` (apply these exact oldText→newText blocks)

**(2a) imports + constants + `_ms` + `LatencyLog` class.** Edit the import block and insert the new
symbols ABOVE `class VoiceTypingDaemon:`.

oldText:
```
import inspect
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable
```
newText:
```
import collections
import inspect
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable
```

Then INSERT (place this block immediately BEFORE `class VoiceTypingDaemon:`):

```python
# --- Per-utterance latency logging (P1.M4.T1.S3; PRD §4.2 logging, §6 latency targets) ---------
# A bounded ring buffer of recent utterance records + a structured log line the latency tests parse.
# t_speech_end comes from the on_vad_stop callback (threaded in via _build_callbacks); t_final_ready
# / t_typed come from on_final. All delta timestamps are time.monotonic() (NTP-safe); ts is wall epoch.
_LATENCY_LOG_PREFIX = "voice-typing latency:"   # STABLE prefix — T1 greps this (do not rename)
_LATENCY_RING_SIZE = 64


def _ms(seconds: float) -> float:
    """Seconds → milliseconds, rounded to 0.1 ms (log readability + stable parse)."""
    return round(seconds * 1000.0, 1)


class LatencyLog:
    """Per-utterance latency capture for the latency tests (PRD §6 T1/T3; PRD §4.2 logging).

    Fed by RealtimeSTT callbacks (note_partial/note_speech_end — wired via _build_callbacks) and by
    VoiceTypingDaemon.on_final (finalize_utterance). Timestamps are time.monotonic() (delta-safe vs
    NTP); a wall epoch `ts` is added for journal correlation. A bounded ring buffer (deque maxlen) of
    recent records is queryable via snapshot() (future status cmd, P1.M4.T2.S1) + by tests.

    Thread-safe: note_partial fires on the realtime thread, note_speech_end on the VAD thread,
    finalize_utterance on the on_final worker thread, snapshot() on the socket thread — all short,
    guarded by self._lock.
    """

    def __init__(self, *, ring_size: int = _LATENCY_RING_SIZE) -> None:
        self._lock = threading.Lock()
        self._records: collections.deque = collections.deque(maxlen=ring_size)
        self._partial_count = 0
        self._t_speech_end: float | None = None

    def note_partial(self, _text: str) -> None:
        """Count a realtime partial (partial CADENCE is T1's own measurement; we just count)."""
        with self._lock:
            self._partial_count += 1

    def note_speech_end(self) -> None:
        """Record t_speech_end (on_vad_stop — VAD closed = speech ended)."""
        with self._lock:
            self._t_speech_end = time.monotonic()

    def finalize_utterance(self, *, text: str, t_final_ready: float, t_typed: float) -> dict:
        """Build + store the per-utterance record; reset counters; return the record for logging.

        t_speech_end may be None (no on_vad_stop seen) → the two *_ms fields derived from it are None
        (rendered 'n/a' in the log line); final_to_typed_ms is always numeric.
        """
        with self._lock:
            t_speech_end = self._t_speech_end
            partials = self._partial_count
            self._partial_count = 0
            self._t_speech_end = None
        record = {
            "event": "utterance_final",
            "t_speech_end": t_speech_end,
            "t_final_ready": t_final_ready,
            "t_typed": t_typed,
            "speech_end_to_final_ms": _ms(t_final_ready - t_speech_end)
                if t_speech_end is not None else None,
            "final_to_typed_ms": _ms(t_typed - t_final_ready),
            "total_ms": _ms(t_typed - t_speech_end) if t_speech_end is not None else None,
            "partials": partials,
            "text": text,
            "ts": time.time(),
        }
        with self._lock:
            self._records.append(record)
        return record

    def snapshot(self) -> list[dict]:
        """Newest-last copy of the ring buffer (for status + tests)."""
        with self._lock:
            return list(self._records)


```

**(2b) `_build_callbacks` — add optional `latency` param + wire partial/on_vad_stop.**

oldText:
```
def _build_callbacks(feedback: "Feedback") -> dict[str, Callable[..., None]]:
    """Wire RealtimeSTT callbacks -> Feedback (PRD §4.2; item contract point 3).

      on_realtime_transcription_stabilized(str) -> feedback.update_partial(text)
      on_vad_detect_start() -> feedback.set_phase("listening")   # system starts listening for VAD
      on_vad_start()        -> feedback.set_phase("speaking")    # voice activity detected
      on_vad_stop()         -> feedback.set_phase("listening")   # voice ended -> back to listening

    Callbacks are simple direct delegations (no try/except) — Feedback is designed robust and the
    on_final typing-error handling belongs to S2, not these partial/VAD hooks.
    """
    return {
        _PARTIAL_CALLBACK_ATTR: lambda text: feedback.update_partial(text),
        "on_vad_detect_start": lambda: feedback.set_phase("listening"),
        "on_vad_start": lambda: feedback.set_phase("speaking"),
        "on_vad_stop": lambda: feedback.set_phase("listening"),
    }
```
newText:
```
def _build_callbacks(
    feedback: "Feedback", latency: "LatencyLog | None" = None
) -> dict[str, Callable[..., None]]:
    """Wire RealtimeSTT callbacks -> Feedback (+ optional LatencyLog; PRD §4.2; P1.M4.T1.S3).

      on_realtime_transcription_stabilized(str) -> feedback.update_partial(text) [+ latency.note_partial]
      on_vad_detect_start() -> feedback.set_phase("listening")   # system starts listening for VAD
      on_vad_start()        -> feedback.set_phase("speaking")    # voice activity detected
      on_vad_stop()         -> feedback.set_phase("listening")   # voice ended -> back to listening
                           [+ latency.note_speech_end  (t_speech_end for the latency log)]

    `latency` is OPTIONAL (default None) so S1's callers (1-arg) keep working unchanged: when None,
    the partial/on_vad_stop callbacks behave exactly as S1 (no extra side effect). VoiceTypingDaemon
    passes its LatencyLog so the per-utterance latency log gets t_speech_end + partial count.
    """
    def _partial(text: str) -> None:
        feedback.update_partial(text)
        if latency is not None:
            latency.note_partial(text)

    def _vad_stop() -> None:
        feedback.set_phase("listening")
        if latency is not None:
            latency.note_speech_end()

    return {
        _PARTIAL_CALLBACK_ATTR: _partial,
        "on_vad_detect_start": lambda: feedback.set_phase("listening"),
        "on_vad_start": lambda: feedback.set_phase("speaking"),
        "on_vad_stop": _vad_stop,
    }
```

**(2c) `_construct` — add optional `latency` param + thread to `_build_callbacks`.**

oldText:
```
def _construct(
    cfg: VoiceTypingConfig, feedback: "Feedback", recorder_cls: type
) -> Any:
    """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

    Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
    RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
    supplies the real AudioToTextRecorder via a lazy import.
    """
    kwargs = cfg_to_kwargs(cfg)
    kwargs.update(_build_callbacks(feedback))
    filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
    return recorder_cls(**filtered)
```
newText:
```
def _construct(
    cfg: VoiceTypingConfig,
    feedback: "Feedback",
    recorder_cls: type,
    latency: "LatencyLog | None" = None,
) -> Any:
    """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

    Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
    RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
    supplies the real AudioToTextRecorder via a lazy import. `latency` (optional, default None) is
    threaded into _build_callbacks so on_vad_stop/partial feed the per-utterance latency log.
    """
    kwargs = cfg_to_kwargs(cfg)
    kwargs.update(_build_callbacks(feedback, latency))
    filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
    return recorder_cls(**filtered)
```

**(2d) `build_recorder` — add optional `latency` param + thread to `_construct`.**

oldText:
```
def build_recorder(cfg: VoiceTypingConfig, feedback: "Feedback") -> Any:
    """Construct ONE AudioToTextRecorder wired to feedback (PRD §4.2, §4.4).

    Resolves device/models (CPU fallback), builds kwargs + callbacks, defensively filters to the
    installed RealtimeSTT signature, then constructs the recorder. Model load happens HERE (in
    __init__) and stays resident — the main loop (P1.M4.T1.S2) reuses this single recorder for the
    daemon's lifetime. Returns the constructed AudioToTextRecorder.

    Heavy: imports RealtimeSTT + loads models on first call (seconds). Unit tests call _construct()
    with a fake class instead; this function is exercised by the feed_audio test (P1.M7.T2.S1) and
    the real daemon startup (P1.M4.T1.S2).
    """
    from RealtimeSTT import AudioToTextRecorder  # lazy: keeps `import voice_typing.daemon` cheap

    return _construct(cfg, feedback, AudioToTextRecorder)
```
newText:
```
def build_recorder(
    cfg: VoiceTypingConfig, feedback: "Feedback", latency: "LatencyLog | None" = None
) -> Any:
    """Construct ONE AudioToTextRecorder wired to feedback (+ optional latency) (PRD §4.2, §4.4).

    Resolves device/models (CPU fallback), builds kwargs + callbacks, defensively filters to the
    installed RealtimeSTT signature, then constructs the recorder. Model load happens HERE (in
    __init__) and stays resident — the main loop (P1.M4.T1.S2) reuses this single recorder for the
    daemon's lifetime. `latency` (optional) threads the per-utterance collector into on_vad_stop/
    partial. Returns the constructed AudioToTextRecorder.

    Heavy: imports RealtimeSTT + loads models on first call (seconds). Unit tests call _construct()
    with a fake class instead; this function is exercised by the feed_audio test (P1.M7.T2.S1) and
    the real daemon startup (P1.M4.T1.S2).
    """
    from RealtimeSTT import AudioToTextRecorder  # lazy: keeps `import voice_typing.daemon` cheap

    return _construct(cfg, feedback, AudioToTextRecorder, latency)
```

**(2e) `VoiceTypingDaemon.__init__` — create + thread `self._latency`.**

oldText:
```
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
        self._shutdown = threading.Event()    # cleared → keep looping
        self._start_monotonic: float | None = None
        # construct-once (PRD §4.2): build recorder ONCE so models stay resident + toggle/start/stop
        # can arm the mic immediately. Injectable for unit tests (fakes → cheap, no RealtimeSTT).
        self._recorder = recorder if recorder is not None else build_recorder(cfg, feedback)
```
newText:
```
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
        self._shutdown = threading.Event()    # cleared → keep looping
        self._start_monotonic: float | None = None
        # Per-utterance latency collector (P1.M4.T1.S3): fed by on_vad_stop/partial (via
        # build_recorder→_build_callbacks) + on_final. Injectable for tests; a real one otherwise.
        self._latency = latency if latency is not None else LatencyLog()
        # construct-once (PRD §4.2): build recorder ONCE so models stay resident + toggle/start/stop
        # can arm the mic immediately. Injectable for unit tests (fakes → cheap, no RealtimeSTT).
        # Pass self._latency so on_vad_stop/partial feed the latency log (PRD §4.2; P1.M4.T1.S3).
        self._recorder = (
            recorder if recorder is not None else build_recorder(cfg, feedback, self._latency)
        )
```

AND update the `__init__` signature to accept `latency`:

oldText:
```
    def __init__(
        self,
        cfg: VoiceTypingConfig,
        feedback: "Feedback",
        *,
        recorder: Any = None,
        backend: "TypingBackend | None" = None,
    ) -> None:
```
newText:
```
    def __init__(
        self,
        cfg: VoiceTypingConfig,
        feedback: "Feedback",
        *,
        recorder: Any = None,
        backend: "TypingBackend | None" = None,
        latency: "LatencyLog | None" = None,
    ) -> None:
```

**(2f) `run()` — set log level from config + log resolved device/models at startup (BEFORE the
existing ready log line; keep the loop unchanged).**

oldText:
```
    def run(self) -> None:
        """The listen-forever loop (main thread, BLOCKS until shutdown)."""
        self._start_monotonic = time.monotonic()
        self._feedback.set_listening(False)   # PRD §4.9: starts NOT listening (no hot-mic on boot)
        logger.info("voice-typing daemon ready (not listening); recorder resident")
        while not self._shutdown.is_set():
```
newText:
```
    def run(self) -> None:
        """The listen-forever loop (main thread, BLOCKS until shutdown)."""
        self._start_monotonic = time.monotonic()
        self._configure_log_level()           # PRD §4.2: DEBUG via config (namespace logger; T3 adds handler)
        self._log_resolved_device()           # PRD §4.2/acceptance T6: prove CUDA residency at startup
        self._feedback.set_listening(False)   # PRD §4.9: starts NOT listening (no hot-mic on boot)
        logger.info("voice-typing daemon ready (not listening); recorder resident")
        while not self._shutdown.is_set():
```

Then ADD these two private helpers (place immediately AFTER `run()`, BEFORE `on_final`):

```python
    def _configure_log_level(self) -> None:
        """Apply cfg.log.level to the `voice_typing` namespace logger (PRD §4.2 'DEBUG via config').

        Namespace-scoped only — NOT basicConfig (handler/root config is P1.M4.T3.S1's job). An invalid
        level string is ignored (leave the default). Tests use pytest caplog (own handler).
        """
        log_cfg = getattr(self._cfg, "log", None)
        level_name = log_cfg.level.upper() if log_cfg is not None else "INFO"
        try:
            logging.getLogger("voice_typing").setLevel(level_name)
        except (ValueError, TypeError):
            logger.warning("invalid log level %r; leaving default", getattr(log_cfg, "level", None))

    def _log_resolved_device(self) -> None:
        """Log the resolved device/models once at startup (CUDA residency proof; PRD acceptance T6).

        Wrapped in try/except so a probe failure (odd env / missing ctranslate2 in a degraded run)
        NEVER breaks the listen loop. Reuses S1's _resolve_device_config (the same resolution
        build_recorder applied), so the logged device matches the recorder's actual device.
        """
        try:
            resolved = _resolve_device_config(self._cfg)
            logger.info(
                "voice-typing device resolved: device=%s compute_type=%s final_model=%s "
                "realtime_model=%s",
                resolved["device"],
                resolved["compute_type"],
                resolved["final_model"],
                resolved["realtime_model"],
            )
        except Exception:
            logger.info("voice-typing device resolved: (resolution failed; see cuda_check logs)")
```

**(2g) `on_final` — capture t_final_ready/t_typed, finalize latency, emit structured INFO + DEBUG
lines (REPLACES S2's `logger.info("final typed: %r", cleaned)` + NOTE comment).**

oldText:
```
    def on_final(self, text: str) -> None:
        """Gate → clean → type → record. Fired by RealtimeSTT in a NEW thread (never raise)."""
        if not self._listening.is_set():       # GATE: race guard (PRD §4.2/§8 — utterance may
            return                             #   complete right after stop)
        cleaned = textproc.clean(text, self._cfg.filter)
        if not cleaned:                        # rejected: blocklist hallucination / below min_chars
            return
        payload = cleaned + (" " if self._cfg.output.append_space else "")
        try:
            self._backend.type_text(payload)   # may raise → caught so the on_final thread survives
        except Exception:
            logger.exception("typing backend failed for final %r", cleaned)
        self._feedback.record_final(cleaned)   # recognition is final regardless of typing success
        logger.info("final typed: %r", cleaned)
        # NOTE: precise latency timestamps (t_speech_end/t_final_ready/t_typed) land in P1.M4.T1.S3.
```
newText:
```
    def on_final(self, text: str) -> None:
        """Gate → clean → type → record + log latency. Fired by RealtimeSTT in a NEW thread."""
        t_final_ready = time.monotonic()       # entry stamp (PRD §4.2 latency logging)
        if not self._listening.is_set():       # GATE: race guard (PRD §4.2/§8 — utterance may
            return                             #   complete right after stop)
        cleaned = textproc.clean(text, self._cfg.filter)
        if not cleaned:                        # rejected: blocklist hallucination / below min_chars
            return
        payload = cleaned + (" " if self._cfg.output.append_space else "")
        try:
            self._backend.type_text(payload)   # may raise → caught so the on_final thread survives
        except Exception:
            logger.exception("typing backend failed for final %r", cleaned)
        t_typed = time.monotonic()             # right after type_text (PRD §4.2 latency logging)
        self._feedback.record_final(cleaned)   # recognition is final regardless of typing success
        record = self._latency.finalize_utterance(
            text=cleaned, t_final_ready=t_final_ready, t_typed=t_typed
        )
        # Structured per-utterance latency line — T1 (test_feed_audio) parses this. Stable prefix +
        # key=value tokens; text=<repr> is LAST (repr may contain spaces). *_ms are 'n/a' when no
        # on_vad_stop preceded this final (t_speech_end is None). (PRD §6 latency targets.)
        logger.info(
            "%s event=%s speech_end_to_final_ms=%s final_to_typed_ms=%s total_ms=%s "
            "partials=%d ts_epoch=%.3f text=%r",
            _LATENCY_LOG_PREFIX,
            record["event"],
            record["speech_end_to_final_ms"] if record["speech_end_to_final_ms"] is not None else "n/a",
            record["final_to_typed_ms"],
            record["total_ms"] if record["total_ms"] is not None else "n/a",
            record["partials"],
            record["ts"],
            cleaned,
        )
        logger.debug(
            "voice-typing latency debug: t_speech_end=%s t_final_ready=%.4f t_typed=%.4f",
            record["t_speech_end"] if record["t_speech_end"] is not None else "n/a",
            record["t_final_ready"],
            record["t_typed"],
        )
```

#### Task 3 SOURCE edit — `voice_typing/config.py`

ADD the `LogConfig` dataclass (place it near the other sub-config dataclasses, e.g. after
`FilterConfig`):

```python
@dataclass
class LogConfig:
    """[log] — daemon logging verbosity (PRD §4.2 'logging … at INFO; DEBUG via config').

    `level` sets the `voice_typing` namespace logger level (applied in VoiceTypingDaemon.run). The
    entry point (P1.M4.T3.S1) also reads this for basicConfig's handler/root level. "INFO" ships the
    per-utterance latency line; "DEBUG" adds the raw monotonic-timestamp line.
    """

    level: str = "INFO"  # "INFO" | "DEBUG" (case-insensitive at apply time)
```

ADD the `log` field to `VoiceTypingConfig` (after the `filter` field):

```python
    filter: FilterConfig = field(default_factory=FilterConfig)
    log: LogConfig = field(default_factory=LogConfig)
```

ADD the overlay in `from_toml` (after the `filter=_overlay(...)` line in the `return cls(...)`):

```python
            filter=_overlay(FilterConfig, "filter"),
            log=_overlay(LogConfig, "log"),
```

#### Task 4 SOURCE edit — `config.toml`

APPEND (at end of file, as a new top-level table):

```toml

[log]
# Daemon logging verbosity (PRD §4.2). "INFO" emits one structured latency line per typed utterance
# + the startup device/models line. "DEBUG" additionally emits the raw monotonic timestamps per
# utterance (use when finals exceed the 1.5s target to see exact t_speech_end/t_final_ready/t_typed).
# Under systemd these flow to journald: `journalctl --user -u voice-typing -f`.
level = "INFO"
```

#### Task 5c SOURCE additions — `tests/test_daemon.py` (APPEND after S2's tests)

```python
# ===========================================================================
# P1.M4.T1.S3 — Per-utterance latency logging (LatencyLog + structured log line + device log)
# (ADDITIVE — everything above is S1+S2; do not change it.)
# ===========================================================================
import re
import time as _time


# --- LatencyLog unit tests ---


def test_latencylog_partial_count_and_reset():
    lat = daemon.LatencyLog()
    lat.note_partial("a")
    lat.note_partial("b")
    rec = lat.finalize_utterance(text="ab", t_final_ready=10.0, t_typed=10.05)
    assert rec["partials"] == 2
    # reset: a new finalize with no partials between reads 0
    rec2 = lat.finalize_utterance(text="x", t_final_ready=11.0, t_typed=11.01)
    assert rec2["partials"] == 0


def test_latencylog_speech_end_and_deltas():
    lat = daemon.LatencyLog()
    t0 = _time.monotonic()
    lat.note_speech_end()
    rec = lat.finalize_utterance(text="hi", t_final_ready=t0 + 0.600, t_typed=t0 + 0.634)
    assert rec["t_speech_end"] is not None
    assert rec["speech_end_to_final_ms"] == 600.0   # 0.600s -> 600.0ms (rounded 0.1)
    assert rec["final_to_typed_ms"] == 34.0          # 0.034s -> 34.0ms
    assert rec["total_ms"] == 634.0


def test_latencylog_no_speech_end_yields_na_deltas():
    lat = daemon.LatencyLog()
    rec = lat.finalize_utterance(text="hi", t_final_ready=5.0, t_typed=5.02)
    assert rec["t_speech_end"] is None
    assert rec["speech_end_to_final_ms"] is None
    assert rec["total_ms"] is None
    assert rec["final_to_typed_ms"] == 20.0          # always present


def test_latencylog_ring_buffer_bounded_and_snapshot_copy():
    lat = daemon.LatencyLog(ring_size=3)
    for i in range(5):
        lat.finalize_utterance(text=str(i), t_final_ready=float(i), t_typed=float(i) + 0.01)
    snap = lat.snapshot()
    assert [r["text"] for r in snap] == ["2", "3", "4"]   # oldest evicted; newest last
    snap.append("mutate")                                  # snapshot is a copy
    assert len(lat.snapshot()) == 3


# --- _build_callbacks(fb, latency) wiring ---


def test_build_callbacks_threads_latency_into_partial_and_vad_stop():
    fb = _FakeFeedback()
    lat = daemon.LatencyLog()
    cb = daemon._build_callbacks(fb, lat)
    cb["on_realtime_transcription_stabilized"]("hello")
    cb["on_realtime_transcription_stabilized"]("hello world")
    cb["on_vad_stop"]()
    assert fb.partials == ["hello", "hello world"]          # feedback still driven
    assert fb.phases == ["listening"]                        # set_phase still driven
    rec = lat.finalize_utterance(text="hello world", t_final_ready=1.0, t_typed=1.02)
    assert rec["partials"] == 2
    assert rec["t_speech_end"] is not None                  # note_speech_end fired


def test_build_callbacks_latency_none_is_noop():
    # S1 behavior preserved: latency=None -> no extra side effect; phases/partials unchanged.
    fb = _FakeFeedback()
    cb = daemon._build_callbacks(fb, None)
    cb["on_realtime_transcription_stabilized"]("hi")
    cb["on_vad_stop"]()
    assert fb.partials == ["hi"]
    assert fb.phases == ["listening"]


# --- on_final emits the structured latency line + populates the ring buffer ---


def _grep_latency_line(messages):
    for m in messages:
        if m.startswith(daemon._LATENCY_LOG_PREFIX) and "event=utterance_final" in m:
            return m
    return None


def test_on_final_emits_structured_latency_line(caplog):
    d, fb, rec, be = _make_daemon()
    d._latency.note_speech_end()
    _time.sleep(0.001)
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.start()
        d.on_final("hello world")
    line = _grep_latency_line([r.getMessage() for r in caplog.records])
    assert line is not None, "no latency line emitted"
    assert line.startswith("voice-typing latency: event=utterance_final")
    assert "final_to_typed_ms=" in line and "total_ms=" in line and "partials=" in line
    assert "speech_end_to_final_ms=" in line and "ts_epoch=" in line
    assert "text='hello world'" in line          # %r of cleaned text
    # total_ms is a number (t_speech_end was set) -> not n/a
    assert re.search(r"total_ms=\d", line)
    # S2 behavior preserved:
    assert be.typed == ["hello world "] and fb.finals == ["hello world"]


def test_on_final_latency_line_na_when_no_vad_stop(caplog):
    d, fb, rec, be = _make_daemon()
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.start()
        d.on_final("quick")              # no note_speech_end -> t_speech_end None
    line = _grep_latency_line([r.getMessage() for r in caplog.records])
    assert line is not None
    assert "speech_end_to_final_ms=n/a" in line
    assert "total_ms=n/a" in line
    assert re.search(r"final_to_typed_ms=\d", line)      # always numeric
    # ring buffer still got a record
    snap = d._latency.snapshot()
    assert len(snap) == 1 and snap[0]["text"] == "quick"


def test_on_final_populates_ring_buffer_snapshot():
    d, _, _, _ = _make_daemon()
    d._latency.note_speech_end()
    d.start()
    d.on_final("one")
    d._latency.note_speech_end()
    d.on_final("two")
    snap = d._latency.snapshot()
    assert [r["text"] for r in snap] == ["one", "two"]


def test_on_final_rejected_hallucination_emits_no_latency_line(caplog):
    d, _, _, _ = _make_daemon()
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.start()
        d.on_final("thank you.")         # blocklist -> clean() None -> early return
    line = _grep_latency_line([r.getMessage() for r in caplog.records])
    assert line is None
    assert d._latency.snapshot() == []


# --- run() logs the resolved device/models at startup ---


def test_run_logs_resolved_device_at_startup(monkeypatch, caplog):
    # Force a deterministic cuda resolution so the startup line is stable + hermetic.
    monkeypatch.setattr(
        daemon.cuda_check,
        "resolve_device_and_models",
        lambda defaults=None: {"device": "cuda", "compute_type": "float16",
                               "final_model": "distil-large-v3", "realtime_model": "small.en"},
    )
    d, _, _, _ = _make_daemon()
    import threading
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: any("device resolved" in r.getMessage() for r in caplog.records)
                  if caplog.records else False, timeout=2.0) or None
        msgs = [r.getMessage() for r in caplog.records]
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)
    assert any("voice-typing device resolved:" in m for m in msgs), msgs
    dev_line = next(m for m in msgs if "device resolved" in m)
    assert "device=cuda" in dev_line and "final_model=distil-large-v3" in dev_line
```

#### Task 5b SOURCE additions — `tests/test_config.py` (APPEND one test)

```python
def test_log_config_default_and_override():
    from voice_typing.config import LogConfig, VoiceTypingConfig
    assert VoiceTypingConfig().log.level == "INFO"
    assert LogConfig(level="DEBUG").level == "DEBUG"
    # round-trips through TOML
    cfg = VoiceTypingConfig.from_toml({"log": {"level": "DEBUG"}})
    assert cfg.log.level == "DEBUG"
```

#### Task 5a SOURCE edit — `tests/test_config_repo_default.py`

In `test_repo_config_toml_has_no_extra_keys`, add the `[log]` section to `expected`:

oldText:
```
        "feedback": {"state_file", "hypr_notify", "notify_ms"},
        "filter": {"min_chars", "blocklist"},
    }
```
newText:
```
        "feedback": {"state_file", "hypr_notify", "notify_ms"},
        "filter": {"min_chars", "blocklist"},
        "log": {"level"},
    }
```

### Implementation Patterns & Key Details

```python
# The t_speech_end capture path (research §1 — the crux):
#   on_vad_stop (RealtimeSTT VAD thread)
#     -> _build_callbacks["on_vad_stop"] = _vad_stop   (S3 wires this when latency is passed)
#     -> feedback.set_phase("listening")  (S1 behavior, preserved)
#     -> latency.note_speech_end()        (S3: self._t_speech_end = time.monotonic())
#   ... 0.6s post_speech_silence_duration passes, utterance finalizes ...
#   recorder.text(self.on_final) returns -> on_final(text) (RealtimeSTT worker thread)
#     -> t_final_ready = time.monotonic()                (S3: entry stamp)
#     -> gate / clean / type / t_typed = time.monotonic()(S3: after type_text)
#     -> feedback.record_final(cleaned)                  (S2, preserved)
#     -> latency.finalize_utterance(...)                 (S3: deltas + ring buffer + reset)
#     -> logger.info("voice-typing latency: event=utterance_final ...")  (S3: T1 parses this)

# The structured line is the CONTRACT — do not rename keys (Critical #13). final_to_typed_ms is
# always numeric; the *_from_speech_end fields are 'n/a' when t_speech_end is None.

# Backward-compat invariant (Critical #6): every daemon.py edit is additive or optional-default.
# After Task 2, RE-RUN the full suite — if any S1/S2 test fails, an edit accidentally changed
# behavior; revert to the surgical oldText→newText blocks above.
```

### Integration Points

```yaml
MODULE-INTERNAL (voice_typing/daemon.py):
  - add to: module-top imports
  - pattern: "import collections" (stdlib-cheap; keeps import purity)
  - add to: above class VoiceTypingDaemon
  - pattern: "_LATENCY_LOG_PREFIX / _LATENCY_RING_SIZE / _ms() / class LatencyLog"
  - modify: _build_callbacks / _construct / build_recorder (optional latency=None param)
  - modify: VoiceTypingDaemon.__init__ (create+thread self._latency; +latency kwarg)
  - modify: VoiceTypingDaemon.run (+_configure_log_level / +_log_resolved_device calls + 2 helpers)
  - modify: VoiceTypingDaemon.on_final (t_final_ready/t_typed capture + finalize + structured log)

CONFIG (voice_typing/config.py + config.toml):
  - add to: config.py — LogConfig dataclass + `log` field + from_toml overlay
  - add to: config.toml — [log] level = "INFO"

EXPOSED FOR DOWNSTREAM (do NOT rename):
  - daemon.LatencyLog (note_partial / note_speech_end / finalize_utterance / snapshot)
  - daemon._LATENCY_LOG_PREFIX ("voice-typing latency:")
  - VoiceTypingDaemon._latency (the instance; status cmd P1.M4.T2.S1 may call .snapshot())
  - the structured log line format (T1 parses it)
  - cfg.log.level (T3's basicConfig reads it)

NO DATABASE / NO ROUTES / NO NEW DEPS. Pure stdlib (collections/logging/threading/time).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing

# py_compile all touched files — fix before proceeding.
.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/config.py \
    tests/test_daemon.py tests/test_config.py tests/test_config_repo_default.py

# Import purity: importing daemon must NOT bind RealtimeSTT/torch/ctranslate2 at module top.
.venv/bin/python -c "
import sys, voice_typing.daemon as d
bad = [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
print('leaked heavy imports:', bad)
assert not bad, f'heavy imports leaked at module top: {bad}'
assert hasattr(d, 'LatencyLog'), 'LatencyLog missing'
assert hasattr(d, 'VoiceTypingDaemon'), 'VoiceTypingDaemon missing (S2 regression!)'
assert hasattr(d, 'build_recorder'), 'S1 build_recorder still present (regression!)'
import inspect
print('_build_callbacks:', inspect.signature(d._build_callbacks))   # (feedback, latency=None)
print('build_recorder:', inspect.signature(d.build_recorder))      # (cfg, feedback, latency=None)
print('ok: import-pure + LatencyLog present + S1/S2 surface intact')
"
# mypy is NOT installed — do NOT run it. ruff is optional (/home/dustin/.local/bin/ruff).
# Expected: py_compile exits 0; purity prints 'leaked heavy imports: []' + 'ok: ...'.
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing

# S3 daemon tests (LatencyLog + callbacks + on_final + run device log).
.venv/bin/python -m pytest tests/test_daemon.py -v

# Config drift + LogConfig tests.
.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -v

# Full suite — must stay green (was 134 passing pre-S3; S3 adds ~11 → ~145; S1/S2 bodies unchanged).
.venv/bin/python -m pytest tests/ -q

# Expected: all pass. If a S1/S2 test fails, an S3 edit changed behavior — diff against the surgical
# oldText→newText blocks (Critical #6); the most likely culprit is the on_final edit accidentally
# altering be.typed/fb.finals, or the run() edit altering the loop. The run device-log test may need
# the cuda_check monkeypatch shown in Task 5c if the env has no GPU (it forces cuda deterministically).
```

### Level 3: Scope Guard (Integration Boundary)

```bash
cd /home/dustin/projects/voice-typing

# Forbidden tokens in daemon.py — NONE of these belong in S3 (socket/main/signal/basicConfig/
# recorder.shutdown). basicConfig is T3's job; S3 sets only the namespace logger level.
echo "=== forbidden token scan (expect no matches) ==="
grep -nE 'socket\.socket|json\.loads|signal\.|def main\(|if __name__|basicConfig' voice_typing/daemon.py \
  || echo "ok: none of socket/main/signal/basicConfig"
echo "=== recorder.shutdown anywhere in daemon.py (expect none — T2.S2 owns teardown) ==="
grep -nE 'recorder\.shutdown|self\._recorder\.shutdown' voice_typing/daemon.py \
  || echo "ok: no recorder.shutdown() calls"
echo "=== the old S2 'final typed: %r' line must be GONE (replaced by the latency line) ==="
grep -nE 'final typed: %r' voice_typing/daemon.py \
  || echo "ok: S2 bare line removed (superseded by the structured latency line)"

# Expected: all three greps print 'ok: ...'. A match means scope creep or a missed edit — fix it.
```

### Level 4: Structured-line + end-to-end smoke (Confidence — the parse contract)

```bash
cd /home/dustin/projects/voice-typing

# (a) LatencyLog + on_final produce the EXACT parseable line (no mic/models — inject stubs).
.venv/bin/python -c "
import logging, time
logging.basicConfig(level=logging.DEBUG, format='%(message)s')
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig
class R:
    def text(self, cb): return ''
    def set_microphone(self, on=True): pass
    def abort(self): pass
class B:
    def __init__(self): self.typed=[]
    def type_text(self, t): self.typed.append(t)
class F:
    def record_final(self, t): pass
    def set_listening(self, b): pass
d = daemon.VoiceTypingDaemon(VoiceTypingConfig(), F(), recorder=R(), backend=B())
d._latency.note_speech_end(); d._latency.note_partial('he'); d._latency.note_partial('hel')
time.sleep(0.001)
d.start(); d.on_final('hello world')
snap = d._latency.snapshot()
assert len(snap) == 1, snap
r = snap[0]
assert r['partials'] == 2 and r['text'] == 'hello world'
assert r['speech_end_to_final_ms'] is not None and r['total_ms'] is not None
print('SNAPSHOT OK:', r)
print('TYPED:', d._backend.typed)
"
# Expected: 'SNAPSHOT OK: {... partials: 2, text: hello world ...}' + 'TYPED: [\"hello world \"]'.

# (b) The no-VAD-stop path renders n/a (no crash).
.venv/bin/python -c "
import logging; logging.basicConfig(level=logging.INFO, format='%(message)s')
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig
class R:
    def text(self, cb): return ''
    def set_microphone(self, on=True): pass
    def abort(self): pass
class B:
    def type_text(self, t): pass
class F:
    def record_final(self, t): pass
    def set_listening(self, b): pass
d = daemon.VoiceTypingDaemon(VoiceTypingConfig(), F(), recorder=R(), backend=B())
d.start(); d.on_final('quick')   # no note_speech_end
"
# Expected: a line containing 'speech_end_to_final_ms=n/a' and 'total_ms=n/a' and 'final_to_typed_ms=<num>'.

# (c) Config round-trip + repo-default drift.
.venv/bin/python -c "
from voice_typing.config import VoiceTypingConfig
assert VoiceTypingConfig().log.level == 'INFO'
assert VoiceTypingConfig.from_toml({'log': {'level': 'DEBUG'}}).log.level == 'DEBUG'
print('config ok')
"
.venv/bin/python -m pytest tests/test_config_repo_default.py -q   # drift guard green
```

## Final Validation Checklist

### Technical Validation

- [ ] L1: `.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/config.py tests/...`
      exits 0.
- [ ] L1: import-purity check prints `leaked heavy imports: []` + `LatencyLog present`.
- [ ] L2: `.venv/bin/python -m pytest tests/test_daemon.py -v` all pass (S1 + S2 + S3).
- [ ] L2: `.venv/bin/python -m pytest tests/ -q` green (no regression; ~145 total; S1/S2 bodies
      unchanged).
- [ ] L3: scope-guard greps print `ok: ...` (no socket/main/signal/basicConfig/recorder.shutdown;
      the S2 `final typed: %r` line is gone).
- [ ] L4: (a) LatencyLog+on_final smoke prints `SNAPSHOT OK`; (b) no-VAD-stop renders `n/a`; (c)
      config round-trip + drift test green.

### Feature Validation

- [ ] `LatencyLog.note_partial`/`note_speech_end`/`finalize_utterance`/`snapshot` behave per research
      §2 (deltas correct to 0.1 ms; reset after finalize; ring buffer bounded + newest-last; snapshot
      is a copy).
- [ ] `_build_callbacks(fb, latency)` wires partial→note_partial + on_vad_stop→note_speech_end while
      STILL driving feedback; `latency=None` is a no-op (S1 behavior).
- [ ] `on_final` (armed + valid text) emits ONE `voice-typing latency: event=utterance_final …` line
      with all keys, appends a ring-buffer record, AND types+records exactly as S2.
- [ ] `on_final` with no prior `on_vad_stop` renders `*_ms=n/a` (no crash); `final_to_typed_ms` numeric.
- [ ] `run()` logs `voice-typing device resolved: device=… compute_type=… final_model=…
      realtime_model=…` once at startup; resolution failure is swallowed.
- [ ] `run()` applies `cfg.log.level` to the `voice_typing` namespace logger.
- [ ] `[log] level` round-trips (default "INFO", overridable "DEBUG"); repo config.toml has no drift.

### Code Quality Validation

- [ ] Follows existing patterns (module docstring CONSUMES/CONSUMED BY/SCOPE; logger;
      `from __future__ import annotations`; TYPE_CHECKING; keyword-only injectable args; surgical
      oldText→newText edits like S1/S2).
- [ ] File placement: `LatencyLog` + constants in the existing `voice_typing/daemon.py`; `[log]` in
      the existing `config.toml` + `LogConfig` in `config.py`; tests APPENDED (no new files).
- [ ] Anti-patterns avoided: no feedback-proxy (Critical #2); no monkey-patch of recorder attrs
      (Critical #2); no probe in `__init__` (Critical #8); no basicConfig (Critical #9); no relaxed
      drift assertion (Critical #10).
- [ ] S1/S2 surface intact: `build_recorder`/`cfg_to_kwargs`/`_build_callbacks`/`_construct`/
      `_filter_kwargs_to_signature`/`_resolve_device_config`/`_FIXED_KWARGS` + `VoiceTypingDaemon`'s
      run/on_final/_arm/_disarm/start/stop/toggle/request_shutdown behavior unchanged (S1/S2 tests green).
- [ ] Dependencies: only `collections` added at module top (stdlib-cheap); no new pip deps.

### Documentation & Deployment

- [ ] Module docstring updated: SCOPE/CONSUMES/CONSUMED BY mention per-utterance latency logging
      (S3) + the `[log]` config + that the socket (T2.S1) may surface `latency.snapshot()` and the
      entry point (T3.S1) reads `cfg.log.level`.
- [ ] The latency log line prefix + key names are the documented T1 parse contract (research §3).
- [ ] No new environment variables (the verbosity knob is `[log] level` in config.toml).

---

## Anti-Patterns to Avoid

- ❌ Don't capture `t_speech_end` via a feedback-proxy or post-construction monkey-patch —
  `set_phase("listening")` is fired by both `on_vad_detect_start` AND `on_vad_stop` (ambiguous), and
  monkey-patching `recorder.on_vad_stop` is undocumented/brittle. Thread `LatencyLog` through
  `_build_callbacks` (Critical #1/#2).
- ❌ Don't make `latency` a REQUIRED param on `_build_callbacks`/`_construct`/`build_recorder` — S1's
  tests call them with the OLD arg count; keep `latency=None` optional so they stay green (Critical #6).
- ❌ Don't double-log per utterance — S3's structured line REPLACES S2's `final typed: %r` (Critical #7).
- ❌ Don't move the device probe into `__init__` — every daemon test would then hit real cuda_check at
  construction; keep it in `run()`, wrapped in try/except (Critical #8).
- ❌ Don't call `logging.basicConfig` — handler/root config is T3's job; set only the `voice_typing`
  namespace logger level (Critical #9).
- ❌ Don't relax the config drift test — extend it with `'log': {'level'}` so config.py + config.toml +
  the test move in lockstep (Critical #10).
- ❌ Don't rename the latency line prefix or keys — T1 (test_feed_audio) greps/regexes them
  (Critical #13).
- ❌ Don't import RealtimeSTT/torch/ctranslate2 at module top — stay lazy inside `build_recorder`
  (Critical #11); `collections` is the only new top-level import (stdlib).
- ❌ Don't touch any S1/S2 test body, `feedback.py`, `typing_backends.py`, `textproc.py`,
  `cuda_check.py`, `pyproject.toml`, `uv.lock`, `PRD.md`, `tasks.json`, or `.gitignore`.

---

## Confidence Score

**9/10** for one-pass implementation success. The design is pinned to the LIVE merged `daemon.py`
(S1+S2, 134 green) with exact surgical oldText→newText blocks; the crux (t_speech_end capture) is
resolved with a backward-compatible optional-param threading (proven non-breaking in research §6);
the structured log line + record schema are the explicit T1 parse contract; the config blast radius
(3 files) is fully enumerated with the drift-test update; and every gate (py_compile, import-purity,
pytest, scope-guard grep, stub smoke) is executable as written. The one residual risk: the `run()`
device-log test depends on monkeypatching `cuda_check` in a no-GPU CI env — the Task 5c test does this
deterministically, but if the implementer skips the monkeypatch, that single test may hit a real probe
(wrapped in try/except, so the loop is safe, but the assertion on `device=cuda` would need the
monkeypatch).

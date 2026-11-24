# Research: partial_source selector across the spawn boundary (P1.M2.T1.S1)

## 1. Why a selector is needed (external_deps.md, verified)

RealtimeSTT 1.0.2 **tries BOTH legacy callbacks in the same eligible decode** (stabilized first
inline; the stabilizer still runs when only plain is registered) — so the plain/stabilized
difference is *visible content + revisions*, not simply invocation time, and only an isolated
paired replay (S6) can choose. PRD R.8 mandates the comparison; today only the laggy stabilized
callback is wired (daemon.py:221 `_PARTIAL_CALLBACK_ATTR`, comment :219 acknowledges the switch).
Because the recorder builds inside a **multiprocessing 'spawn' child**, a parent monkeypatch of the
constant does NOT survive — the selector must travel as **picklable data** through the existing
RecorderHost spawn args into `_worker_main`'s `build_recorder` calls (both the normal and the
force_cpu CPU-fallback retry). Production selection stays internal (no TOML/env/CLI knob);
stream-edit keeps stabilized after release.

## 2. The wiring chain (verified at HEAD)

| Site | Today | Change |
|---|---|---|
| daemon.py:221 `_PARTIAL_CALLBACK_ATTR` | `"on_realtime_transcription_stabilized"` | RETAINED as the default resolved key (8+ tests hardcode it: test_daemon.py:337,346,414,424,446,1831-1845,3259) |
| daemon.py:327 `_build_callbacks(feedback, latency, on_speech)` | returns `{_PARTIAL_CALLBACK_ATTR: _partial, 3 VAD cbs}` | + `partial_source: str = "stabilized"` → maps via a new `_PARTIAL_SOURCES = {"plain": "on_realtime_transcription_update", "stabilized": "on_realtime_transcription_stabilized"}` dict; validates; emits EXACTLY ONE partial key; the `_partial` closure body unchanged (feedback/latency/on_speech preserved) |
| daemon.py:397 `_construct(...)` | cfg_to_kwargs → callbacks → extra_kwargs → `_filter_kwargs_to_signature` → cls(**filtered) | + `partial_source` threaded; AFTER filtering, REJECT if the selected key was dropped (ineffective selection) — a build with NO partial callback is broken, not drift |
| daemon.py:436 `build_recorder(...)` | lazy RealtimeSTT wrapper | + `partial_source: str = "stabilized"` passthrough |
| daemon.py:~1096 `_load_host` | real RecorderHost gets `feed_input=self._feed_input` etc.; fakes keep the old surface | + `partial_source=self._partial_source` on the REAL host only (mirror feed_input/is_listening precedent) |
| VoiceTypingDaemon.__init__ | has the lab seam `feed_input` attr pattern | + keyword-only `partial_source: str = "stabilized"` → `self._partial_source` (private; NOT config) |
| recorder_host.py:140 `__init__(..., *, force_cpu, is_listening, feed_input)` | spawn-arg tail | + keyword-only `partial_source: str = "stabilized"` |
| recorder_host.py spawn() | `ctx.Process(target=_worker_main, args=(cfg, queues, force_cpu, ..., self._feed_q, ...))` | add `self._partial_source` to args (picklable str) |
| recorder_host.py `_worker_main` | calls `build_recorder(...)` in the child (normal + CPU-fallback retry) | pass `partial_source=` to EVERY build_recorder call (find sites by grep `build_recorder` in the file) |
| recorder_host.py ready payload | `("ready", {device, compute_type, model})` | + `"partial_callback": <the installed key>` (lab-ready provenance); expose on the host (attribute/property alongside `.device`) |

## 3. The two rejections (contract: "validated" + "reject an unavailable or ineffective selection")

1. **Invalid value** (`partial_source="loud"`) → `ValueError` at `_build_callbacks` (a bad
   *argument value*, not TOML — config-style TypeError doesn't apply).
2. **Ineffective selection**: the chosen key was DROPPED by `_filter_kwargs_to_signature`
   (recorder_cls lacks it) → `ValueError` from `_construct` ("refusing to build a recorder with no
   partial callback") instead of silent drift. Because build success ⟹ the key survived the
   filter, the ready payload can report the requested key AS the installed key (post-rejection,
   effective == requested).

## 4. Invariants the tests must pin

- Default `"stabilized"` → the callbacks dict is **byte-identical** to today (all 8+ hardcoded-key
  tests stay green; stream-edit unchanged).
- **Exactly one** partial key per build — never both ("no two callbacks delivering to one consumer").
- The `_partial` closure semantics unchanged (update_partial + note_partial + on_speech) and the
  child's `("partial", {text, utterance_id, session_gen})` relay shape/identity unchanged (R.5).
- Hermetic: mock recorder_cls / spawn Process / host / CUDA-device resolution; no real models.

## 5. Consumers (OUTPUT)

P1.M2.T1.S4 (the route runner constructs real builds with each selector), P1.M2.T1.S6 (the paired
comparison), P1.M2.T2.S3 (final selection). The ready-payload `partial_callback` is the G5
provenance field external_deps.md mandates ("Actual selected source and device/cadence must be in
the G5 provenance").

## 6. Scope + parallel

Files: `voice_typing/daemon.py`, `voice_typing/recorder_host.py`, `tests/test_daemon.py` (additive
section), `tests/test_recorder_host.py` (additive). NO config.py/config.toml (no knob), no ctl, no
bulk_controller. Parallel P1.M1.T3.S1 is docs-only (`tests/G1_BASELINE.md`, `AGENTS.md`) — zero
overlap. pytest>=9.1.1; full paths + functional `timeout` (AGENTS.md).

# Research — P1.M4.T1.S3: Per-utterance latency logging

**Status:** Design pinned against the LIVE merged `voice_typing/daemon.py` (S1 + S2, 134 tests
green, `VoiceTypingDaemon` present) + RealtimeSTT v1.0.2 API (architecture/research_realtimestt_api.md).

## 0. The contract (verbatim from the work item)

> Add structured INFO logging (stdlib logging → stderr → journald) per utterance: capture
> t_speech_end (from on_vad_stop callback), t_final_ready (on_final entry), t_typed (after
> backend.type_text), plus final text and partial count. Log the resolved device/models at
> startup (proves CUDA residency). DEBUG level via config. Expose a structured way for tests to
> parse these (recognizable log prefix, OR state file, OR small ring buffer queryable by status).

Consumers: P1.M7.T2.S1 (test_feed_audio latency asserts) + P1.M7.T4.S1. Latency targets
(PRD §6): partial cadence ≤300 ms while speaking; final-typed ≤1.5 s after end-of-utterance
(0.6 s of that is the deliberate post_speech_silence_duration segmentation pause).

## 1. The crux: t_speech_end + partial count are wired INSIDE _build_callbacks

The RealtimeSTT callbacks that carry the signals S3 needs are wired in S1's
`_build_callbacks(feedback)`:

| RealtimeSTT callback | current wiring (S1) | S3 signal needed |
|---|---|---|
| `on_realtime_transcription_stabilized(str)` | `feedback.update_partial(text)` | **partial count** |
| `on_vad_stop()` | `feedback.set_phase("listening")` | **t_speech_end** (VAD closed = speech ended) |
| `on_vad_detect_start` / `on_vad_start` | `set_phase("listening"/"speaking")` | (unused for latency) |

These lambdas close over `feedback` ONLY. `on_vad_stop` (verified, architecture research §3:
"voice activity ends", no-arg) fires when VAD closes — that is exactly t_speech_end. It fires
BEFORE the utterance finalizes (final fires after post_speech_silence_duration), so
`t_speech_end ≤ t_final_ready`.

### Why a feedback-proxy / monkey-patch does NOT work
- **Feedback-proxy** (wrap feedback.set_phase): `set_phase("listening")` is fired by BOTH
  `on_vad_detect_start` AND `on_vad_stop` → cannot distinguish t_speech_end from listen-start.
- **Post-construction monkey-patch** of `recorder.on_vad_stop`: brittle, undocumented, depends on
  RealtimeSTT storing callbacks as settable instance attrs. REJECTED.

### The chosen approach: thread an OPTIONAL LatencyLog through the callback wiring
Modify `_build_callbacks(feedback, latency=None)`, `_construct(..., latency=None)`,
`build_recorder(cfg, feedback, latency=None)`. `latency=None` (default) ⇒ callbacks behave
EXACTLY as S1 (no-op side effects) ⇒ **S1's `_build_callbacks`/`_construct` tests stay green**
(verified by reading tests/test_daemon.py: they call with the OLD arg count + assert phases/
partials unchanged; an optional 2nd param + `if latency is not None:` guard preserves both).

The daemon creates ONE `LatencyLog` in `__init__` and passes it to `build_recorder`, so the
production recorder's on_vad_stop/partial callbacks feed it.

## 2. LatencyLog design (added to voice_typing/daemon.py)

A small, thread-safe collector. Fed by callbacks (`note_partial`/`note_speech_end`) and by
`on_final` (`finalize_utterance`). Keeps a bounded ring buffer (queryable by status T2.S1 +
inspectable by tests) and returns a structured record per utterance.

```python
_LATENCY_LOG_PREFIX = "voice-typing latency:"   # stable, greppable — tests parse this line
_LATENCY_RING_SIZE = 64

def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 1)

class LatencyLog:
    """Per-utterance latency capture for the latency tests (PRD §6 T1/T3; PRD §4.2 logging).

    note_partial()/note_speech_end() are fed by RealtimeSTT callbacks (via _build_callbacks).
    finalize_utterance() is called by VoiceTypingDaemon.on_final with t_final_ready/t_typed.
    Timestamps are time.monotonic() (delta-safe vs NTP); a wall epoch `ts` is added for journal
    correlation. A bounded ring buffer of recent records is queryable via snapshot() (for the
    future status command, P1.M4.T2.S1) and directly by tests.
    """
    def __init__(self, *, ring_size: int = _LATENCY_RING_SIZE) -> None:
        self._lock = threading.Lock()
        self._records: collections.deque[dict] = collections.deque(maxlen=ring_size)
        self._partial_count = 0
        self._t_speech_end: float | None = None

    def note_partial(self, _text: str) -> None:          # partial count (cadence is T1's own measure)
        with self._lock:
            self._partial_count += 1

    def note_speech_end(self) -> None:                   # on_vad_stop → t_speech_end
        with self._lock:
            self._t_speech_end = time.monotonic()

    def finalize_utterance(self, *, text: str, t_final_ready: float, t_typed: float) -> dict:
        with self._lock:
            t_speech_end = self._t_speech_end
            partials = self._partial_count
            self._partial_count = 0                       # reset for next utterance
            self._t_speech_end = None
        record = {
            "event": "utterance_final",
            "t_speech_end": t_speech_end,                 # monotonic, or None (no VAD stop seen)
            "t_final_ready": t_final_ready,
            "t_typed": t_typed,
            "speech_end_to_final_ms": _ms(t_final_ready - t_speech_end) if t_speech_end is not None else None,
            "final_to_typed_ms": _ms(t_typed - t_final_ready),
            "total_ms": _ms(t_typed - t_speech_end) if t_speech_end is not None else None,
            "partials": partials,
            "text": text,
            "ts": time.time(),                            # wall epoch for journal correlation
        }
        with self._lock:
            self._records.append(record)
        return record

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._records)
```

Thread-safety: a `threading.Lock` guards the counters + ring buffer. `note_partial` fires on the
RealtimeSTT realtime thread; `note_speech_end` on the VAD thread; `finalize_utterance` on the
on_final worker thread; `snapshot()` (future status) on the socket thread. All short, non-blocking.

## 3. The structured log line (the thing tests parse)

Recognizable, stable prefix + `key=value` pairs. Emitted at INFO by `on_final`:

```
voice-typing latency: event=utterance_final speech_end_to_final_ms=612.3 final_to_typed_ms=34.1 total_ms=646.4 partials=5 ts_epoch=1783718400.123 text="hello world"
```

- `speech_end_to_final_ms` / `total_ms` are `n/a` when no `on_vad_stop` preceded the final
  (`t_speech_end` is None — e.g. a unit test calling `on_final` with no VAD). `final_to_typed_ms`
  is always present.
- `text` is `%r`-quoted (handles spaces/punctuation/newlines safely).
- A DEBUG line adds the raw monotonic timestamps for deep debugging:
  `voice-typing latency debug: t_speech_end=<m|n/a> t_final_ready=<m> t_typed=<m>`.

Test-parse recipe (T1/test_feed_audio, caplog): `import re; m =
re.search(r"total_ms=(\S+)", line)` etc. The prefix `voice-typing latency: event=utterance_final`
is the anchor.

## 4. Startup device/models log (CUDA residency proof — PRD acceptance T6)

`run()` computes `_resolve_device_config(cfg)` ONCE (wrapped in try/except so it NEVER breaks the
loop — cuda_check probes can raise in odd envs) and logs:

```
voice-typing device resolved: device=cuda compute_type=float16 final_model=distil-large-v3 realtime_model=small.en
```

This is the line T6 (`nvidia-smi` GPU residency) + the item's "log device" requirement both point
at. It proves the daemon BUILT for cuda (acceptance: if finals exceed target, "ensure both models
are on CUDA — log device").

## 5. DEBUG level via config ([log] section)

Add a `[log]` section (config.py `LogConfig.level: str = "INFO"` + config.toml `[log] level =
"INFO"`). `run()` sets `logging.getLogger("voice_typing").setLevel(cfg.log.level.upper())`
(namespace-scoped; NOT basicConfig — that is T3's job, and T3 will also read cfg.log.level to
attach a handler). S3 emits `logger.info` (per-utterance + startup) and `logger.debug` (raw
timestamps); tests capture both via pytest `caplog` (which attaches its own handler at the
requested level — so DEBUG records are verifiable without T3's handler).

Blast radius: config.py (+LogConfig +field), config.toml (+[log]), test_config_repo_default.py
(+`"log": {"level"}` to the expected schema). All additive; the repo-default drift test is
UPDATED as part of S3 (it asserts the EXACT 14→15-key schema).

## 6. Backward-compatibility proof (S1 + S2 tests stay green)

S3's daemon.py edits are purely ADDITIVE / optional-default:
- `_build_callbacks(feedback, latency=None)`: S1 calls it 1-arg → latency None → identical behavior.
- `_construct(cfg, feedback, recorder_cls, latency=None)`, `build_recorder(cfg, feedback, latency=None)`:
  same — optional trailing param.
- `VoiceTypingDaemon.__init__(..., latency=None)`: S2's `_make_daemon` calls without latency → a real
  LatencyLog is created; `on_final` now calls `self._latency.finalize_utterance(...)` (a no-fail
  append) + logs — S2's `on_final` assertions (`be.typed`, `fb.finals`) are unaffected.
- `on_final`: `t_final_ready = time.monotonic()` at entry (cheap), then the S2 body unchanged, then
  `t_typed` + finalize + log appended AFTER `record_final`. S2 tests assert on typed/finals only.
- `run()`: adds `_log_resolved_device()` (try/except-wrapped, log-only) + level set — S2's run()
  tests assert on text_calls/loop-exit only.

Verified: `tests/` is currently 134 passing; S3 adds ~10 tests → ~144, with ZERO changes to S1/S2
assertions.

## 7. Out of scope (NOT in S3)

- Control socket surfacing of `latency.snapshot()` → P1.M4.T2.S1 (`status` cmd may add a
  `latency` field reading the daemon's ring buffer; S3 only PROVIDES snapshot()).
- `logging.basicConfig` / handler attach / stderr format → P1.M4.T3.S1 (entry point).
- `recorder.shutdown()` / quit / signals → P1.M4.T2.S2 / T3.
- Real feed_audio latency measurement → P1.M7.T2.S1 (consumes these log lines).

## 8. Validation gates (executable as written)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/config.py tests/test_daemon.py tests/test_config_repo_default.py
# import purity unchanged
.venv/bin/python -c "import sys,voice_typing.daemon as d; assert not [m for m in('RealtimeSTT','torch','ctranslate2') if m in sys.modules]; assert hasattr(d,'LatencyLog') and hasattr(d,'VoiceTypingDaemon')"
.venv/bin/python -m pytest tests/ -q        # expect ~144 passed, 0 failed
# latency line smoke (no mic/models — inject stubs + a real LatencyLog)
.venv/bin/python -c "
import logging; logging.basicConfig(level=logging.DEBUG)
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig
class R:
  def text(self,cb): return ''
  def set_microphone(self,on=True): pass
  def abort(self): pass
class B:
  def __init__(self): self.t=[]
  def type_text(self,t): self.t.append(t)
class F:
  def record_final(self,t): pass
  def set_listening(self,b): pass
d=daemon.VoiceTypingDaemon(VoiceTypingConfig(),F(),recorder=R(),backend=B())
d._latency.note_speech_end(); d._latency.note_partial('he'); d._latency.note_partial('hel')
import time; time.sleep(0.001)
d.start(); d.on_final('hello world')
print('snapshot:', d._latency.snapshot())
"
```

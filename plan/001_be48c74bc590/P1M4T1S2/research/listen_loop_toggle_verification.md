# Research Brief: P1.M4.T1.S2 — Listen-forever loop + on_final→type + listening gate + toggle

**Status:** VERIFIED live against installed RealtimeSTT v1.0.2 + the codebase (2026-07-06).
This subtask consumes outputs that are ALREADY LANDED (config/textproc/typing_backends/feedback)
or being implemented in parallel (P1.M4.T1.S1 = `build_recorder`). Every contract below is read
from source; every RealtimeSTT method is signature-checked.

---

## 1. RealtimeSTT control API (VERIFIED — `.venv/bin/python -c "inspect.signature(...)"`)

| Method | Signature | Behavior (from `research_realtimestt_api.md` §2 + §4 + live source) |
|---|---|---|
| `recorder.text(on_transcription_finished=None)` | `(self, on_transcription_finished=None)` → delegates `transcribe_text` | **BLOCKS** until ONE utterance finalizes (`post_speech_silence_duration` SEGMENTS only), then if a callback is given it is fired in a **NEW THREAD** with the final `str`, and `text()` returns `""` when shut down / interrupted. The while-loop re-enters → continuous dictation. **THIS IS THE WHISPERX-FLAW FIX (PRD §1 #1).** |
| `recorder.set_microphone(microphone_on=True)` | `(self, microphone_on=True)` | Sets `self.use_microphone.value`. Stops live mic capture WITHOUT destroying recorder/models → models stay resident → instant toggle-on. `False` = mic off, `True` = mic on. |
| `recorder.abort()` | `(self)` | Sets `interrupt_stop_event` + calls `recorder.stop()`. If called while `text()` is blocking in `wait_audio()`, the interrupt makes `text()` return `""` → loop resumes. **Use this to break a blocked `text()` on toggle-off / shutdown.** |
| `recorder.shutdown()` | `(self)` | Full teardown. **ONLY on daemon quit (P1.M4.T2.S2). NEVER on toggle/stop (PRD §4.2).** |
| `recorder.stop(...)` / `recorder.listen()` | `(self, backdate_stop_seconds=0.0, ...)` / `(self)` | Lower-level; NOT needed — `set_microphone` + `abort` cover the toggle contract. |

**Canonical continuous-dictation loop (PRD §4.2, research §2):**
```python
while not shutdown_requested:
    if listening.is_set():
        recorder.text(on_final)   # blocks → 1 utterance → on_final in NEW thread → returns → re-listen
    else:
        time.sleep(0.05)
```
`recorder.text()` returning is **normal segmentation**, NEVER session end. The session ends ONLY on
explicit stop/toggle/quit. ✅ fixes PRD §1 #1.

**MULTIPROCESSING GUARD** (research §2, README:76-78): RealtimeSTT uses multiprocessing for model
work → `main()` (P1.M4.T3.S1) MUST wrap the entry in `if __name__ == "__main__":`. systemd
`ExecStart=.venv/bin/python -m voice_typing.daemon` sets `__name__=="__main__"` correctly. **NOT
S2's concern** — S2 ships the `VoiceTypingDaemon` class, not `main()`.

---

## 2. Consumed contracts (READ from source — DO NOT edit these modules)

### 2a. `build_recorder(cfg, feedback) -> AudioToTextRecorder` (P1.M4.T1.S1 — in parallel)
Located in `voice_typing/daemon.py` (already landed as the S1 construction surface). Signature:
`build_recorder(cfg: VoiceTypingConfig, feedback: "Feedback") -> Any`. Constructs ONE recorder
(models load here, stay resident). **S2 calls this ONCE** to obtain the recorder. For unit tests,
S2 INJECTS a fake recorder (never calls `build_recorder` → no RealtimeSTT import, no model load).

### 2b. `textproc.clean(text, cfg.filter) -> str | None` (P1.M2.T2.S1 — LANDED)
`voice_typing/textproc.py`: `def clean(text: str, cfg: FilterConfig) -> str | None`. Returns the
cleaned text, or `None` if rejected (below `min_chars`, or a blocklist hallucination like
"thank you."). **S2 calls `cleaned = textproc.clean(text, self._cfg.filter)`; if `not cleaned`,
skip typing + record_final.** Never appends a space (caller's job).

### 2c. `typing_backends.make_backend(cfg.output) -> TypingBackend` (P1.M3.T1.S1 — LANDED)
`voice_typing/typing_backends.py`: `make_backend(cfg: OutputConfig) -> TypingBackend`. Returns
`_WtypeWithFallback` (default), `YdotoolBackend`, or `TmuxBackend`. Each has `type_text(text)`
that may RAISE `subprocess.CalledProcessError` / `OSError` (wtype fails → ydotool fallback; if that
also fails, it propagates). **S2 calls `backend.type_text(payload)`; MUST catch+log exceptions so
the on_final thread (fired by RealtimeSTT in a NEW thread) never crashes.**

### 2d. `Feedback` (P1.M3.T2.S1 — LANDED): `record_final(text)` + `set_listening(bool)`
`voice_typing/feedback.py`:
- `record_final(text: str)` → sets `last_final`, writes state file, fires hyprctl `✔ <text>`.
- `set_listening(listening: bool)` → sets the listening gate, writes state file, notifies `● listening`
  / `■ stopped` ON TRANSITION ONLY (False→True / True→False; a no-op same-value call writes but does
  NOT notify → no startup spam).
- `update_partial(text)` / `set_phase(phase)` → wired by S1's callbacks (NOT S2's concern directly).
Thread-safe (tempfile+os.replace atomic write; no lock needed per feedback.py docstring).

### 2e. `VoiceTypingConfig` (P1.M2.T1.S1 — LANDED): the fields S2 reads
- `cfg.output.append_space: bool` (default `True`) → S2 appends one trailing space to each typed final.
- `cfg.filter: FilterConfig` → passed to `textproc.clean`.
No mutation — S2 READS cfg only.

---

## 3. Design — `VoiceTypingDaemon` class (added to `voice_typing/daemon.py`)

### 3a. Constructor — construct-once, injectable for tests
```python
class VoiceTypingDaemon:
    def __init__(self, cfg, feedback, *, recorder=None, backend=None):
        self._cfg = cfg
        self._feedback = feedback
        self._lock = threading.Lock()              # serializes start/stop/toggle/request_shutdown
        self._listening = threading.Event()        # CLEARED at boot -> NOT listening (PRD §4.9 no hot-mic)
        self._shutdown  = threading.Event()        # CLEARED -> keep looping
        self._start_monotonic: float | None = None # uptime baseline (for the socket status cmd)
        # construct-once (PRD §4.2): build the recorder ONCE here so models stay resident and
        # toggle/start/stop can arm the mic immediately. Injectable for unit tests (fakes -> cheap).
        self._recorder = recorder if recorder is not None else build_recorder(cfg, feedback)
        self._backend  = backend  if backend  is not None else typing_backends.make_backend(cfg.output)
```
**Why build in `__init__` (eager), not lazily in `run()`?** Eliminates the race where the control
socket (started by main/T3) sends `toggle` before `run()` has built the recorder. After `__init__`
the recorder exists, so `start()`/`stop()` work immediately. `import voice_typing.daemon` stays
CHEAP (the class definition does not import RealtimeSTT; only instantiating WITHOUT an injected
recorder triggers `build_recorder`'s lazy import). Unit tests ALWAYS inject a fake recorder →
`build_recorder` is never called → no model load, no CUDA.

### 3b. `run()` — the listen-forever loop (main thread, BLOCKS)
```python
def run(self):
    self._start_monotonic = time.monotonic()
    self._feedback.set_listening(False)   # PRD §4.9: starts NOT listening (no hot-mic on boot)
    logger.info("voice-typing daemon ready (not listening); recorder resident")
    while not self._shutdown.is_set():
        if self._listening.is_set():
            self._recorder.text(self.on_final)   # blocks → 1 utterance → on_final NEW thread → re-listen
        else:
            time.sleep(0.05)
    logger.info("shutdown requested; run() loop exiting")
```

### 3c. `on_final(text)` — gate → clean → type → record (fired by RealtimeSTT in a NEW thread)
```python
def on_final(self, text):
    if not self._listening.is_set():              # GATE: race guard (PRD §4.2/§8 — utterance may
        return                                    #   complete right after stop)
    cleaned = textproc.clean(text, self._cfg.filter)
    if not cleaned:                               # rejected: blocklist hallucination / < min_chars
        return
    payload = cleaned + (" " if self._cfg.output.append_space else "")
    try:
        self._backend.type_text(payload)          # may raise -> caught so the on_final thread survives
    except Exception:
        logger.exception("typing backend failed for final %r", cleaned)
    self._feedback.record_final(cleaned)          # recognition is final regardless of typing success
    logger.info("final typed: %r", cleaned)
    # NOTE: precise latency timestamps (t_speech_end/t_final_ready/t_typed) land in P1.M4.T1.S3.
```

### 3d. toggle / start / stop — mic arming via `set_microphone` + `abort`
Private `_arm()` / `_disarm()` (NO lock) so `toggle()` can call them while already holding the lock
(avoids deadlock vs a non-reentrant `Lock`; avoids duplicating the arming logic):
```python
def _arm(self):
    self._listening.set();  self._recorder.set_microphone(True);  self._feedback.set_listening(True)
def _disarm(self):
    self._listening.clear(); self._recorder.set_microphone(False); self._recorder.abort(); self._feedback.set_listening(False)
def start(self):  with self._lock: self._arm()
def stop(self):   with self._lock: self._disarm()
def toggle(self): with self._lock: self._arm() if self._listening.is_set() else self._disarm()  # (inverted: arm if NOT set)
```
Wait — correct toggle: arm when NOT currently listening, disarm when listening. `toggle()`:
`if self._listening.is_set(): self._disarm() else: self._arm()`.
- **stop()** calls `set_microphone(False)` + `abort()` (breaks any blocked `text()` so the loop
  re-checks the now-cleared gate and goes to the sleep branch).
- **start()** calls `set_microphone(True)` (re-arms the mic; models already resident → instant).
- **NEVER `recorder.shutdown()`** on toggle/stop — only on quit (P1.M4.T2.S2).

### 3e. `request_shutdown()` + `is_listening()` + `uptime_s`
```python
def request_shutdown(self):
    self._shutdown.set()                          # loop exits on next check
    with self._lock: self._recorder.abort()       # break any blocked text() so run() can return
    # recorder.shutdown() (full teardown) is wired by the quit handler in P1.M4.T2.S2, NOT here.
def is_listening(self) -> bool: return self._listening.is_set()
@property
def uptime_s(self) -> float: return time.monotonic() - self._start_monotonic if self._start_monotonic else 0.0
```

### 3f. Thread-safety reasoning
- `threading.Event` (`_listening`, `_shutdown`): `set`/`clear`/`is_set` are atomic — the loop and
  `on_final` read them WITHOUT the lock. ✅
- The `_lock` serializes ONLY `start`/`stop`/`toggle`/`request_shutdown` (concurrent control-socket
  commands). It guards the multi-step arming sequence so two toggles can't interleave into
  `listening=cleared` + `mic=on`. None of the guarded calls block (set_microphone sets a Value;
  abort sets an event; feedback writes are fast atomic renames) → no deadlock. ✅
- `run()` does NOT take the lock (it only reads Events + calls `recorder.text()`). ✅

---

## 4. Scope boundaries (what S2 does NOT do — avoid collisions)

| Concern | Owner | Note |
|---|---|---|
| Per-utterance latency timestamps (`t_speech_end`/`t_final_ready`/`t_typed`) | **P1.M4.T1.S3** | S2 logs a basic `final typed: %r`; S3 adds the precise instrumentation the latency test reads. |
| Control socket (JSON-lines, toggle/start/stop/status/quit protocol) | **P1.M4.T2.S1** | S2 exposes `run/toggle/start/stop/is_listening/uptime_s/request_shutdown` for the socket to call. |
| `recorder.shutdown()` + socket close on quit | **P1.M4.T2.S2** | S2's `request_shutdown()` only sets the flag + aborts; the full teardown is T2.S2. |
| `main()` / `if __name__ == "__main__":` / signal handlers / `logging.basicConfig` | **P1.M4.T3.S1** | S2 ships the class only. The pyproject `voice-typing-daemon = "voice_typing.daemon:main"` entry point stays INERT until T3. |
| Recorder construction (`build_recorder`/`cfg_to_kwargs`/callbacks) | **P1.M4.T1.S1** (parallel) | S2 CONSUMES `build_recorder`; does not redefine it. |
| `feed_audio` offline test | **P1.M7.T2.S1** | S2's unit tests inject a fake recorder (no real recorder, no mic). |

---

## 5. Test strategy (NO RealtimeSTT / NO model load / NO mic / NO subprocess)

**File:** EXTEND `tests/test_daemon.py` (the S1 file). Additive only — do NOT break S1's tests.

**Stubs:**
- EXTEND the existing `_FakeFeedback` (S1): ADD `self.finals=[]`, `self.listening_states=[]`,
  `record_final(text)`, `set_listening(on)`. (S1 only checks `partials`/`phases` → still green.)
- ADD `_StubRecorder`: `text(on_transcription_finished=None)` records the callback + returns `""`;
  `set_microphone(on)` appends to `mic`; `abort()` increments `aborts`; `shutdown()` increments
  `shutdowns`. (Distinct name from S1's `_FakeRecorder`, which captures `**kwargs` for construction.)
- ADD `_FakeBackend`: `type_text(text)` appends to `typed` (optionally raises to test error handling).

**Key tests:**
1. `on_final` gate: not-listening → dropped (no type, no record_final).
2. `on_final` happy path: valid text → `type_text(text+" ")` (append_space=True default) + `record_final`.
3. `on_final` append_space=False → no trailing space.
4. `on_final` hallucination reject (`textproc.clean`→None, e.g. "thank you.") → no type, no record.
5. `on_final` typing raises → caught (logged), `record_final` STILL called.
6. `start()` → `_listening` set, `mic==[True]`, `feedback.listening_states==[True]`.
7. `stop()` → `_listening` cleared, `mic==[True,False]`, `aborts>=1`, `feedback.listening_states==[True,False]`.
8. `toggle()` off→on arms; on→off disarms (idempotent-ish: two toggles return to start).
9. `run()` loop: NOT listening → no `text()` calls (sleeps); `start()` → `text()` called repeatedly;
   `request_shutdown()` → loop exits (thread joins). Uses a `_wait_for(predicate, timeout)` helper.
10. boot-no-hot-mic: a freshly constructed daemon has `is_listening()==False`.

**Loop-test robustness:** run `run()` in a daemon thread; `_StubRecorder.text()` returns immediately
(so when listening the loop spins calling `text()` fast → detect `>=2` calls quickly); use a
`_wait_for` poller (not bare `sleep`) and join with a timeout. `request_shutdown()` aborts the fake
(no-op) and sets the flag → loop exits → thread joins.

---

## 6. Validation gates (executable, project-specific)

- **L1 syntax/purity:** `.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py`;
  the S1 import-purity AST check still passes (S2 adds only `threading`/`time`/`textproc`/
  `typing_backends` — all cheap; RealtimeSTT stays lazy inside `build_recorder`).
- **L2 unit:** `.venv/bin/python -m pytest tests/test_daemon.py -v` (S1+S2 tests green);
  `.venv/bin/python -m pytest tests/ -q` (full suite, no regressions — was 118 passing pre-S2).
- **L3 scope guard:** grep `voice_typing/daemon.py` for forbidden tokens (`socket.socket`,
  `json.loads`, `signal.`, `def main(`, `if __name__`, `basicConfig`, `recorder.shutdown(` inside
  start/stop/toggle) → none present.
- mypy is NOT installed — do NOT list it. ruff is optional (`/home/dustin/.local/bin/ruff`); py_compile
  + pytest are authoritative. ALWAYS use `.venv/bin/python -m ...` (zsh aliases bare `python`/`pytest`).

# PRP — P1.M4.T1.S2: Listen-forever loop + on_final→type + listening gate + toggle (set_microphone+abort)

## Goal

**Feature Goal**: Ship the **runtime core** of `voice_typing/daemon.py` (PRD §4.2 items 1+2) — the
`VoiceTypingDaemon` class whose `run()` is the **listen-forever loop** that fixes the WhisperX flaw
(PRD §1 #1: silence may only SEGMENT utterances, never end the session). The loop calls
`recorder.text(on_final)`, which **blocks until ONE utterance finalizes**, fires `on_final` in a NEW
thread, returns, and immediately re-listens — forever, until an explicit toggle/stop/quit. `on_final`
gates on the listening flag (race guard, PRD §4.2/§8), runs `textproc.clean()`, types the result via
the typing backend, and records it on `feedback`. A `threading.Event` `listening` (cleared at boot →
**never hot-mics on boot**, PRD §4.9) is flipped by `start()`/`stop()`/`toggle()`, which arm/disarm the
microphone via `recorder.set_microphone(bool)` + `recorder.abort()` (break any blocked `text()`) —
**models stay resident** (recorder constructed once in S1's `build_recorder`), so toggle-on is instant.

**Deliverable** (TWO artifacts — both MODIFY existing files; this subtask CREATES NO new file):
1. `voice_typing/daemon.py` — **EXTEND** the S1 module (which already has `cfg_to_kwargs`,
   `build_recorder`, `_build_callbacks`, `_filter_kwargs_to_signature`, `_construct`). **ADD** the
   `VoiceTypingDaemon` class: `__init__`, `run`, `on_final`, `_arm`, `_disarm`, `start`, `stop`,
   `toggle`, `request_shutdown`, `is_listening`, `uptime_s`. Add `import threading`, `import time`,
   `import textproc`, `import typing_backends` at module top (all cheap stdlib + already-landed
   modules). **Do NOT touch any S1 function** (regression risk — S1 tests must stay green).
2. `tests/test_daemon.py` — **EXTEND** the S1 test file (additive only). **ADD** `_StubRecorder` (a
   runtime stand-in for the real recorder: `text()`/`set_microphone()`/`abort()`/`shutdown()`), extend
   `_FakeFeedback` with `record_final`/`set_listening`, add `_FakeBackend`, and add ~12 tests covering
   on_final gate/happy/append_space/reject/typing-error, start/stop/toggle, and the `run()` loop.

**Success Definition**:
- (a) `voice_typing/daemon.py` still `py_compile`-clean; `import voice_typing.daemon` still succeeds
  WITHOUT importing RealtimeSTT/torch/ctranslate2 at module top (RealtimeSTT stays lazy inside
  `build_recorder`; the daemon class holds a recorder REFERENCE, never imports the type).
- (b) `VoiceTypingDaemon` exists with the 10 methods/attributes above; `is_listening()` is `False` on a
  freshly constructed daemon (boot-no-hot-mic, PRD §4.9).
- (c) `run()` implements the canonical loop: `while not shutdown.is_set(): if listening.is_set():
  recorder.text(self.on_final) else: time.sleep(0.05)` — `recorder.text()` returning is NORMAL
  segmentation, NEVER session end (the WhisperX-flaw fix, PRD §1 #1).
- (d) `on_final(text)`: **gates** on `listening.is_set()` (returns early if not listening — one
  utterance may complete right after stop, PRD §4.2/§8); runs `textproc.clean(text, cfg.filter)`; if
  non-empty: `backend.type_text(cleaned + (" " if cfg.output.append_space else ""))` inside try/except
  (typing errors are logged, never crash the on_final thread); then `feedback.record_final(cleaned)`.
- (e) `start()` arms: `listening.set()` + `recorder.set_microphone(True)` + `feedback.set_listening(True)`.
- (f) `stop()` disarms: `listening.clear()` + `recorder.set_microphone(False)` + `recorder.abort()`
  (breaks any blocked `text()`) + `feedback.set_listening(False)`.
- (g) `toggle()` flips: if currently listening → `_disarm()`, else `_arm()`. (Uses private helpers so
  the multi-step arming isn't duplicated.)
- (h) `request_shutdown()`: sets `shutdown` event + `recorder.abort()` (so a blocked `text()` returns
  and the loop exits). **NEVER calls `recorder.shutdown()`** — full teardown is P1.M4.T2.S2.
- (i) **No out-of-scope code:** NO control socket (`socket.socket`/`json.loads`), NO `main()`, NO
  `if __name__ == "__main__":`, NO signal handlers, NO `logging.basicConfig`, NO
  `recorder.shutdown()` inside start/stop/toggle, NO per-utterance latency timestamps (those are
  P1.M4.T1.S3 — S2 logs only a basic `final typed: %r`). NO edits to config.py/cuda_check.py/
  feedback.py/typing_backends.py/textproc.py/config.toml/pyproject.toml/uv.lock/PRD.md/tasks.json.
- (j) `tests/test_daemon.py` passes via `.venv/bin/python -m pytest tests/test_daemon.py -v`; full
  suite `.venv/bin/python -m pytest tests/ -q` stays green (S1 tests + the other 5 files — was 118
  passing pre-S2). **No RealtimeSTT import, no model load, no CUDA, no mic** (tests inject a fake
  recorder + fake backend).

## User Persona

**Target User**: Internal — two future consumers drive `VoiceTypingDaemon`: the control socket
(P1.M4.T2.S1) calls `toggle()`/`start()`/`stop()`/`is_listening()`/`uptime_s()`/`request_shutdown()`;
the daemon entry point (P1.M4.T3.S1) calls `run()` from `main()` under the `if __name__ == "__main__":`
guard. There is no end-user surface in S2; the user-facing payoff (toggle-on instant, silence never
ends the session) arrives once T2+T3 wire this class to the socket + entry point.

**Use Case**: At daemon startup, `main()` (T3) constructs `VoiceTypingDaemon(cfg, feedback)` once (the
recorder was built by `build_recorder` in `__init__` → models resident in GPU VRAM), then calls
`run()` on the main thread. `run()` loops. A `voicectl toggle` (T2) reaches the socket → `toggle()` →
`_arm()` sets the listening event + arms the mic → the loop's next iteration calls
`recorder.text(on_final)`. The user speaks; VAD segments on the 0.6s silence pause; `text()` returns
the finalized text via `on_final` in a NEW thread → cleaned → typed → recorded → loop re-listens
immediately. The user pauses mid-sentence: the session does NOT end (it just re-enters `text()`). The
user toggles off: `_disarm()` clears the event + disarms mic + aborts → the loop goes to the sleep
branch. Models stay resident → next toggle-on is instant.

**Pain Points Addressed**: (1) The WhisperX flaw — `text()` returning on silence is normal
segmentation, the loop re-listens (PRD §1 #1). (2) Hot-mic on boot — `listening` is cleared at boot,
explicit `start()`/`toggle()` arms it (PRD §4.9). (3) Toggle-off race typing one last utterance — the
gate inside `on_final` drops a final that completes right after stop (PRD §4.2/§8). (4) Typing backend
failure crashing the daemon — `on_final` catches + logs so the RealtimeSTT-fired thread survives.

## Why

- **This IS the WhisperX-flaw fix (PRD §1 #1).** The single most important behavior in the whole
  project: silence/VAD may only SEGMENT utterances, never end the listening session. The
  `while not shutdown: if listening: recorder.text(on_final)` loop is the literal embodiment of that
  rule. Nothing else in the project delivers this; S2 is where it lives.
- **Continuous dictation feel.** `recorder.text(cb)` blocks until one utterance finalizes, fires the
  callback in a NEW thread (so transcription/typing is off the listen loop), returns, and the loop
  immediately re-listens (research §2). This is how partials + finals stream without dropping the next
  words — the phone-dictation experience PRD §1 #2 demands.
- **Instant toggle-on + GPU residency.** The recorder is constructed ONCE (S1's `build_recorder`) and
  reused for the daemon's lifetime. `start()`/`stop()` flip a `threading.Event` + arm/disarm the mic
  via `set_microphone`/`abort` — they never destroy/rebuild the recorder, so models stay resident in
  VRAM (acceptance T6) and toggle-on is instant (PRD §4.2 "construct once").
- **Boot safety.** `listening` is cleared in `__init__`/`run()`, so the daemon starts NOT listening —
  a systemd auto-start never hot-mics the user (PRD §4.9). `voicectl start`/`toggle` is the explicit
  arm.
- **Unblocks the socket + entry point.** T2 (control socket) calls `toggle`/`start`/`stop`/
  `request_shutdown`/`is_listening`/`uptime_s`; T3 (entry point) calls `run()` + `request_shutdown()`
  on SIGTERM. S2 ships exactly that surface.

## What

`VoiceTypingDaemon` (added to the EXISTING `voice_typing/daemon.py`):

```python
class VoiceTypingDaemon:
    def __init__(self, cfg, feedback, *, recorder=None, backend=None): ...
    def run(self) -> None: ...                 # main thread, BLOCKS
    def on_final(self, text: str) -> None: ... # fired by RealtimeSTT in a NEW thread
    def _arm(self) -> None: ...                # private: set listening + mic on + feedback
    def _disarm(self) -> None: ...             # private: clear listening + mic off + abort + feedback
    def start(self) -> None: ...               # with lock: _arm()
    def stop(self) -> None: ...                # with lock: _disarm()
    def toggle(self) -> None: ...              # with lock: _arm() if not listening else _disarm()
    def request_shutdown(self) -> None: ...    # set shutdown event + abort (loop exits; NO shutdown())
    def is_listening(self) -> bool: ...        # return self._listening.is_set()
    @property
    def uptime_s(self) -> float: ...           # time.monotonic() - _start_monotonic (for status)
```

### Success Criteria

- [ ] `voice_typing/daemon.py` compiles: `.venv/bin/python -m py_compile voice_typing/daemon.py` exits 0.
- [ ] `import voice_typing.daemon` succeeds; `VoiceTypingDaemon` is a class attribute of the module.
- [ ] Module-top import purity holds: no top-level `RealtimeSTT`/`torch`/`ctranslate2` binding
  (RealtimeSTT stays lazy inside `build_recorder`; S2 adds only `threading`/`time`/`textproc`/
  `typing_backends` at the top — all cheap).
- [ ] Fresh daemon: `VoiceTypingDaemon(cfg, fb, recorder=stub, backend=fake).is_listening() is False`.
- [ ] `run()` loop shape exact: NOT listening → no `recorder.text()` calls (sleeps); after `start()` →
  `recorder.text(on_final)` called repeatedly; after `request_shutdown()` → loop exits, thread joins.
- [ ] `on_final` gate: not-listening → early return (no type_text, no record_final).
- [ ] `on_final` happy path: valid text → `backend.type_text(text + " ")` (append_space default True)
  AND `feedback.record_final(text)` (cleaned text, NO trailing space in the recorded value).
- [ ] `on_final` append_space=False → `type_text` gets NO trailing space.
- [ ] `on_final` hallucination (`textproc.clean` → None, e.g. "thank you.") → no type_text, no record.
- [ ] `on_final` typing raises → caught (logged), `record_final` STILL called.
- [ ] `start()` → `listening.is_set()` True, `recorder.set_microphone(True)` called,
  `feedback.set_listening(True)` called.
- [ ] `stop()` → `listening` cleared, `recorder.set_microphone(False)` + `recorder.abort()` called,
  `feedback.set_listening(False)` called.
- [ ] `toggle()` off→on arms (listening set, mic on); on→off disarms (mic off, abort).
- [ ] `request_shutdown()` sets the shutdown event AND calls `recorder.abort()`; does NOT call
  `recorder.shutdown()`.
- [ ] `tests/test_daemon.py` passes; `.venv/bin/python -m pytest tests/ -q` green (118 + new tests).
- [ ] Scope guard grep (L3) finds NONE of: `socket.socket`, `json.loads`, `signal.`, `def main(`,
  `if __name__`, `basicConfig`, `recorder.shutdown(` / `self._recorder.shutdown(` inside
  start/stop/toggle/request_shutdown.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge of this codebase: the consumed contracts
(`build_recorder`, `textproc.clean`, `typing_backends.make_backend`/`type_text`, `Feedback.record_final`/
`set_listening`, `VoiceTypingConfig.output.append_space`/`filter`) are read at preflight and verified
against the live source below; the RealtimeSTT control API (`text`/`set_microphone`/`abort`/`shutdown`)
is signature-checked live; the exact `VoiceTypingDaemon` design (constructor, loop, on_final, arming,
thread-safety) is pinned in the research doc §3; the test strategy (stubs + 12 tests) is pinned in §5;
the S1 module being extended is read in full; and the validation commands (py_compile, import-purity
grep, pytest) are executable as written.

### Documentation & References

```yaml
# MUST READ — the work-item contract (verbatim, authoritative).
- file: plan/001_be48c74bc590/P1M4T1S2/research/listen_loop_toggle_verification.md
  why: "§1: the VERIFIED RealtimeSTT control API table — recorder.text(on_transcription_finished=None)
        blocks until ONE utterance finalizes then fires on_final in a NEW thread and returns '' on
        interrupt; set_microphone(True/False) arms/disarms mic (models stay resident); abort() breaks a
        blocked text() (sets interrupt_stop_event); shutdown() is full teardown (ONLY on quit, NOT S2).
        §2: the 5 consumed contracts with EXACT signatures (build_recorder, textproc.clean, make_backend,
        Feedback.record_final/set_listening, cfg.output.append_space/cfg.filter). §3: the VoiceTypingDaemon
        design — constructor (injectable recorder/backend), run() loop, on_final (gate→clean→type→record),
        _arm/_disarm/start/stop/toggle, request_shutdown/is_listening/uptime_s, thread-safety reasoning.
        §4: scope boundaries (what S2 does NOT do). §5: the test strategy + stubs + 12 tests. §6: the
        validation gates."
  critical: "This research doc IS the spec. The toggle() direction (§3d) is: arm when NOT listening,
             disarm when listening. The on_final gate is `if not listening.is_set(): return` (§3c).
             NEVER recorder.shutdown() on toggle/stop — only on quit (T2.S2). The lock serializes ONLY
             start/stop/toggle/request_shutdown; run() takes no lock."

# MUST READ — the module being EXTENDED (do NOT rewrite it; ADD the class + imports).
- file: voice_typing/daemon.py
  why: "The S1 output: cfg_to_kwargs + _resolve_device_config + _build_callbacks + _filter_kwargs_to_signature
        + _construct + build_recorder, plus _FIXED_KWARGS + _PARTIAL_CALLBACK_ATTR + the module docstring.
        S2 ADDS VoiceTypingDaemon to THIS file. The module already imports inspect/logging/typing +
        cuda_check + VoiceTypingConfig + (TYPE_CHECKING) Feedback + has `logger = logging.getLogger(__name__)`.
        S2 adds: `import threading`, `import time`, `import textproc`, `import typing_backends` (and update
        the module docstring's SCOPE line + CONSUMES/CONSUMED BY)."
  critical: "Do NOT modify, rename, or reorder the S1 functions — test_daemon.py's S1 tests assert their
             exact behavior (118-passing baseline). ADD the class below the existing functions. Keep
             `from __future__ import annotations` at the very top. RealtimeSTT stays lazy inside
             build_recorder — the daemon class holds `self._recorder` as a reference, NEVER imports
             AudioToTextRecorder (so import purity holds). Update the TYPE_CHECKING block to also import
             TypingBackend if you type-hint the backend, OR just leave the backend untyped (injectable)."

# MUST READ — the consumed contracts (READ, do NOT edit).
- file: voice_typing/textproc.py
  why: "`clean(text: str, cfg: FilterConfig) -> str | None`. Returns cleaned text, or None if rejected
        (below min_chars, or a blocklist hallucination like 'thank you.'). Never appends a space (caller's
        job). on_final calls `cleaned = textproc.clean(text, self._cfg.filter)`."
  critical: "Pass `self._cfg.filter` (the FilterConfig), NOT the whole VoiceTypingConfig. `if not cleaned`
             (None OR empty string) → skip typing AND skip record_final."

- file: voice_typing/typing_backends.py
  why: "`make_backend(cfg: OutputConfig) -> TypingBackend`. Each backend has `type_text(text) -> None`
        that MAY raise subprocess.CalledProcessError / OSError (wtype fails → ydotool fallback; if that
        also fails, it propagates). on_final calls `self._backend.type_text(payload)` inside try/except."
  critical: "type_text may RAISE — on_final MUST catch (broad `except Exception` is acceptable here per
             research §3c; log via logger.exception) so the RealtimeSTT-fired thread survives. Pass the
             FULL payload (cleaned + optional space); the backend appends nothing."

- file: voice_typing/feedback.py
  why: "`record_final(text: str)` → sets last_final, writes state file, fires hyprctl '✔ <text>'.
        `set_listening(listening: bool)` → sets the gate, writes state file, notifies '● listening' /
        '■ stopped' ON TRANSITION ONLY (same-value call writes but does not notify → no spam).
        Both are thread-safe (tempfile+os.replace atomic write). on_final calls record_final(cleaned);
        start/stop call set_listening(True/False)."
  critical: "record_final takes the CLEANED text (no trailing space) — the space is a typing-only concern.
             set_listening is idempotent on notifications (same value = no notify) so calling it in both
             _arm and run()'s startup set_listening(False) does not double-notify. Do NOT call
             update_partial/set_phase from S2 (those are wired by S1's _build_callbacks, driven by
             RealtimeSTT, not the daemon)."

- file: voice_typing/config.py
  why: "VoiceTypingConfig fields S2 reads: `cfg.output.append_space: bool` (default True) → append one
        trailing space to each typed final; `cfg.filter: FilterConfig` → passed to textproc.clean;
        `cfg.output: OutputConfig` → passed to typing_backends.make_backend."
  critical: "READ ONLY — S2 never mutates cfg. Do NOT add fields. Pass cfg.output to make_backend (not
             the whole cfg); pass cfg.filter to textproc.clean (not the whole cfg)."

- file: voice_typing/cuda_check.py
  why: "Indirect: build_recorder (S1) calls cuda_check.resolve_device_and_models. S2 does NOT call
        cuda_check directly, but the injected fake recorder in tests means build_recorder is never
        invoked → no CUDA probe in unit tests."
  critical: "Not directly used by S2. Listed so the implementer knows build_recorder's CUDA dependency is
             bypassed by injecting a fake recorder in tests."

# MUST READ — the architecture-level RealtimeSTT research (the source of truth for the API semantics).
- docfile: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "§2: the canonical listen-forever loop `while True: recorder.text(process_text)` — text() blocks
        until one utterance finalizes, fires callback async (NEW thread), loop resumes listening. THIS IS
        THE WHISPERX-FLAW FIX. §2 multiprocessing guard: main() MUST wrap in `if __name__ == '__main__':`
        (NOT S2 — that's T3, but S2 ships the class that runs under it). §4: toggle-off =
        set_microphone(False) + abort() (breaks blocked text()); toggle-on = set_microphone(True); gate
        inside on_final (utterance may complete mid-toggle). shutdown() ONLY on quit. §3: callback
        signatures (already wired by S1; S2 does not re-wire)."
  critical: "§4 is the toggle contract. abort() sets interrupt_stop_event + calls stop() → a blocked
             text() returns '' (nothing typed) → loop resumes and re-checks the now-cleared gate → goes
             to sleep branch. The recorder object is constructed ONCE → models stay resident → instant
             toggle-on. Do NOT call recorder.stop()/listen() directly — set_microphone+abort cover it."

# Background — the prior subtask PRP (the house style for a daemon-module PRP + how S1 phrased scope).
- file: plan/001_be48c74bc590/P1M4T1S1/PRP.md
  why: "Mirror its structure (Goal/Persona/Why/What/Context tree/Gotchas/Validation). Note how S1 pinned
        exact module source verbatim and a verbatim test file. S2 similarly pins the VoiceTypingDaemon
        class design (research §3) and the test additions (research §5). S1's Gotchas about lazy import,
        TYPE_CHECKING Feedback, full paths (.venv/bin/python), no mypy, and the module docstring style
        ALL carry over to S2."
  critical: "S1 already shipped build_recorder/cfg_to_kwargs/_build_callbacks in daemon.py. S2 CONSUMES
             them (calls build_recorder in __init__ when no recorder is injected). Do NOT redefine them."

# Downstream — the consumers S2 feeds (future work, do NOT build).
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M4.T2.S1 (control socket): calls toggle/start/stop/is_listening/uptime_s/request_shutdown.
        P1.M4.T2.S2 (quit/clean-shutdown): calls request_shutdown() THEN recorder.shutdown() + socket close
        (S2's request_shutdown sets the flag + aborts; the full teardown is T2.S2 — so S2 must NOT call
        shutdown() itself, only abort()). P1.M4.T1.S3 (latency logging): adds t_speech_end/t_final_ready/
        t_typed timestamps — S2 logs only a basic `final typed: %r`. P1.M4.T3.S1 (entry point): calls run()
        from main() under __main__ guard + signal handlers. P1.M7.T2.S1 (feed_audio test): real recorder,
        use_microphone=False. Confirms the method surface S2 must expose."
  critical: "Do NOT add socket/main/feed_audio/latency-timestamps/recorder.shutdown() here. The method
             names run/on_final/toggle/start/stop/request_shutdown/is_listening/uptime_s are the contract
             T2+T3 rely on — do not rename or re-shape them."
```

### Current Codebase tree (state at P1.M4.T1.S2 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*'` from repo root. Expected (S1's daemon.py + its test landed; config/cuda_check/textproc/typing_backends/feedback + their tests all green — 118 passing):

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # DO NOT touch
├── .venv/                      # Python 3.12.10; pytest 9.1.1 (dev); realtimestt + nvidia-cublas/cudnn-cu12 installed
├── PRD.md                      # READ-ONLY (§1, §4.2 items 1+2, §4.7, §4.9, §8)
├── config.toml                 # P1.M2.T1.S2 output. DO NOT touch.
├── pyproject.toml              # voice-typing-daemon = "voice_typing.daemon:main" (main() ABSENT until T3). DO NOT touch.
├── uv.lock                     # DO NOT touch
├── voice_typing/
│   ├── __init__.py             # package docstring
│   ├── cuda_check.py           # P1.M1.T2.S2 (indirect via build_recorder). READ, DO NOT EDIT.
│   ├── launch_daemon.sh        # P1.M1.T2.S1 (unrelated)
│   ├── prefetch.py             # P1.M1.T3.S1 (unrelated)
│   ├── config.py               # P1.M2.T1.S1 (CONSUMED: cfg.output/cfg.filter). READ, DO NOT EDIT.
│   ├── textproc.py             # P1.M2.T2.S1 (CONSUMED: clean(text, cfg.filter)). READ, DO NOT EDIT.
│   ├── typing_backends.py      # P1.M3.T1.S1 (CONSUMED: make_backend(cfg.output).type_text(text)). READ, DO NOT EDIT.
│   ├── feedback.py             # P1.M3.T2.S1 (CONSUMED: record_final/set_listening). READ, DO NOT EDIT.
│   ├── status.sh               # P1.M3.T2.S1 (unrelated)
│   └── daemon.py               # ← P1.M4.T1.S1 OUTPUT (EXTEND in S2: ADD VoiceTypingDaemon + imports)
└── tests/
    ├── test_config.py                # P1.M2.T1.S1. DO NOT EDIT.
    ├── test_config_repo_default.py   # P1.M2.T1.S2. DO NOT EDIT.
    ├── test_textproc.py              # P1.M2.T2.S1. DO NOT EDIT.
    ├── test_typing_backends.py       # P1.M3.T1.S2. DO NOT EDIT.
    ├── test_feedback.py              # P1.M3.T2.S1. DO NOT EDIT.
    └── test_daemon.py                # ← P1.M4.T1.S1 OUTPUT (EXTEND in S2: ADD _StubRecorder/_FakeBackend + ~12 tests)
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py               # ← MODIFY (Task 3): ADD VoiceTypingDaemon class + threading/time/textproc/typing_backends imports
└── tests/
    └── test_daemon.py          # ← MODIFY (Task 4): ADD _StubRecorder + _FakeBackend + extend _FakeFeedback + ~12 tests
# NOTHING ELSE. No new files. No socket/main/loop-extras. No edits to any other module.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — recorder.text() semantics (the WHISPERX-FLAW FIX). VERIFIED LIVE
#   (signature: text(self, on_transcription_finished=None)). text() BLOCKS until ONE utterance
#   finalizes (post_speech_silence_duration SEGMENTS only), fires on_transcription_finished in a NEW
#   thread with the final str, and returns "" when shut down / interrupted. The while-loop RE-ENTERS
#   text() → continuous dictation. text() returning is NORMAL SEGMENTATION, NEVER session end. The
#   session ends ONLY on explicit toggle/stop/quit. ACTION: `while not shutdown: if listening:
#   recorder.text(self.on_final) else: sleep(0.05)`. Do NOT break the loop when text() returns.

# CRITICAL #2 — on_final is fired by RealtimeSTT in a NEW thread. It is NOT on the main run() thread.
#   Therefore on_final MUST be safe to run concurrently with the loop (it reads self._listening — an
#   Event, atomic) AND must NEVER raise an unhandled exception (would kill the RealtimeSTT worker
#   thread silently). Wrap the typing call in try/except + logger.exception. The gate check
#   (`if not self._listening.is_set(): return`) is the race guard: a final may complete right after
#   toggle-off (PRD §4.2/§8 "Toggle-off race types one last utterance").

# CRITICAL #3 — toggle mechanics: set_microphone + abort, NEVER shutdown. VERIFIED LIVE
#   (set_microphone(self, microphone_on=True); abort(self)). stop(): set_microphone(False) (mic off,
#   models STAY resident) + abort() (sets interrupt_stop_event → a blocked text() returns "" → loop
#   re-checks the cleared gate → sleep branch). start(): set_microphone(True) (re-arm). NEVER call
#   recorder.shutdown() in stop/toggle/request_shutdown — full teardown is P1.M4.T2.S2's quit handler.
#   request_shutdown() sets the event + abort() (so a blocked text() returns and run() can exit); it
#   does NOT call shutdown().

# CRITICAL #4 — boot-no-hot-mic (PRD §4.9). self._listening is a threading.Event that is CLEARED at
#   construction (threading.Event() starts cleared). run() ALSO calls self._feedback.set_listening(False)
#   at startup to sync the state file + publish the "not listening" state. A freshly constructed daemon
#   has is_listening() == False. Do NOT set _listening in __init__. systemd auto-start must never hot-mic.

# CRITICAL #5 — the _lock serializes ONLY start/stop/toggle/request_shutdown (concurrent control-socket
#   commands). It guards the multi-step arming so two toggles can't interleave into listening=cleared +
#   mic=on. Use a NON-reentrant threading.Lock + PRIVATE _arm()/_disarm() helpers (called while the lock
#   is held) so toggle() doesn't deadlock and arming logic isn't duplicated. run() does NOT take the lock
#   (it only reads Events + calls recorder.text()). The guarded calls (set_microphone sets a Value;
#   abort sets an event; feedback writes are fast atomic renames) do NOT block → no deadlock. Events
#   (_listening, _shutdown) are read WITHOUT the lock (set/clear/is_set are atomic).

# CRITICAL #6 — construct the recorder ONCE in __init__ (eager), injectable for tests.
#   self._recorder = recorder if recorder is not None else build_recorder(cfg, feedback). Building in
#   __init__ (not lazily in run()) eliminates the race where the socket sends toggle before run() built
#   the recorder. Unit tests ALWAYS inject a fake recorder → build_recorder is never called → no
#   RealtimeSTT import, no model load, no CUDA. Similarly inject the backend: self._backend = backend if
#   backend is not None else typing_backends.make_backend(cfg.output).

# CRITICAL #7 — inject BOTH recorder and backend for unit tests. A test passes recorder=_StubRecorder()
#   and backend=_FakeBackend() so __init__ never calls build_recorder/make_backend. Without injection,
#   __init__ would call build_recorder (lazy-imports RealtimeSTT, loads models) and make_backend
#   (returns a real wtype backend). Keyword-only args (`*, recorder=None, backend=None`) keep the
#   production signature clean: production code calls VoiceTypingDaemon(cfg, feedback); tests call
#   VoiceTypingDaemon(cfg, fb, recorder=stub, backend=fake).

# CRITICAL #8 — on_final records the CLEANED text (no trailing space), but TYPES the payload WITH the
#   optional space. record_final(cleaned); type_text(cleaned + (" " if append_space else "")). The space
#   is a typing-output concern (PRD §4.5 output.append_space), NOT a feedback/state concern — the state
#   file's last_final should show what was recognized, not what was typed.

# CRITICAL #9 — append_space reads cfg.output.append_space (default True). on_final builds payload =
#   cleaned + (" " if self._cfg.output.append_space else ""). Read cfg ONCE (stored in __init__) — do not
#   re-read config per utterance (config is immutable at runtime; this is a micro-opt + clarity).

# CRITICAL #10 — the loop-test must not flake. Run run() in a daemon thread; the _StubRecorder.text()
#   returns IMMEDIATELY (records the callback, returns "") so when listening the loop spins calling
#   text() fast. Use a _wait_for(predicate, timeout) poller (loop time.sleep(0.01) until predicate or
#   timeout) — NOT a bare sleep — to detect "text() called >= 2 times". Join the thread with a timeout.
#   request_shutdown() sets the event + abort (fake no-op) → loop exits → thread joins. (research §5.)

# CRITICAL #11 — import purity. S2 adds `import threading`, `import time`, `from voice_typing import
#   textproc`, `from voice_typing import typing_backends` (or `import voice_typing.textproc as textproc`
#   / `import voice_typing.typing_backends as typing_backends`) to daemon.py's top. These are ALL cheap
#   (stdlib + already-landed pure-stdlib modules). RealtimeSTT/torch/ctranslate2 stay OUT of module-top
#   (lazy inside build_recorder). The daemon class references self._recorder as an untyped/hinted ref — it
#   NEVER does `from RealtimeSTT import ...` at module top. The S1 import-purity AST/grep check must
#   still pass.

# CRITICAL #12 — DO NOT re-wire RealtimeSTT callbacks in S2. S1's _build_callbacks already wired
#   on_realtime_transcription_stabilized → update_partial and on_vad_* → set_phase. S2's on_final is the
#   on_transcription_finished callback passed to recorder.text() — a DIFFERENT hook (the per-utterance
#   final callback), NOT a constructor callback. Do NOT add on_final to _build_callbacks or _FIXED_KWARGS.
#   It is a METHOD of VoiceTypingDaemon, passed as self.on_final to recorder.text() in run().

# CRITICAL #13 — uptime_s for the status command. Store self._start_monotonic = time.monotonic() at the
#   top of run() (NOT __init__ — uptime should reflect when the daemon started RUNNING, and a test may
#   construct the daemon without calling run()). uptime_s property returns time.monotonic() -
#   self._start_monotonic if set else 0.0. Use time.monotonic (never time.time — wall clock jumps on NTP).

# CRITICAL #14 — FULL PATHS for tooling (zsh aliases python/pytest). ALWAYS
#   `.venv/bin/python -m pytest` / `.venv/bin/python -m py_compile` (never bare python/pytest). mypy is
#   NOT installed — do NOT list it as a gate. ruff is optional (/home/dustin/.local/bin/ruff); py_compile
#   + pytest are the authoritative gates. (system_context §1; prior tasks' research.)

# GOTCHA #15 — _StubRecorder vs S1's _FakeRecorder. S1's _FakeRecorder captures **kwargs for the
#   CONSTRUCTION test (it's passed to _construct as recorder_cls). S2's _StubRecorder is a RUNTIME
#   stand-in: an INSTANCE held by VoiceTypingDaemon, exposing text()/set_microphone()/abort()/shutdown()
#   that record calls. Different name, different role — do NOT conflate them. Both coexist in
#   test_daemon.py.
```

## Implementation Blueprint

### Data models and structure

No new data model. `VoiceTypingDaemon` consumes the existing `VoiceTypingConfig`, `Feedback`, a
recorder (the `AudioToTextRecorder` from `build_recorder`, or a fake in tests), and a `TypingBackend`
(from `make_backend`, or a fake in tests). Its internal state:

```python
self._cfg: VoiceTypingConfig          # READ ONLY
self._feedback: "Feedback"            # record_final + set_listening (S1 also wires update_partial/set_phase)
self._lock: threading.Lock            # serializes start/stop/toggle/request_shutdown only
self._listening: threading.Event      # cleared at boot (PRD §4.9 no hot-mic); the loop gate
self._shutdown: threading.Event       # cleared → keep looping; set → run() exits
self._start_monotonic: float | None   # set in run(); uptime baseline
self._recorder: Any                   # construct-once (build_recorder) OR injected fake
self._backend: TypingBackend          # make_backend(cfg.output) OR injected fake
```

### VoiceTypingDaemon reference implementation (research §3 — implement this shape)

```python
class VoiceTypingDaemon:
    """The listen-forever daemon core: recorder loop + on_final→type + listening gate + toggle.

    PRD §4.2 items 1+2. run() is the main-thread loop that fixes the WhisperX flaw: recorder.text()
    returning is normal SEGMENTATION, never session end (PRD §1 #1). on_final gates→cleans→types→records.
    start/stop/toggle arm/disarm the mic via set_microphone+abort (models stay resident → instant
    toggle-on). NEVER recorder.shutdown() on toggle/stop — only on quit (P1.M4.T2.S2).
    """

    def __init__(self, cfg: VoiceTypingConfig, feedback: "Feedback", *,
                 recorder: Any = None, backend: "TypingBackend | None" = None) -> None:
        self._cfg = cfg
        self._feedback = feedback
        self._lock = threading.Lock()
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
        self._shutdown = threading.Event()    # cleared → keep looping
        self._start_monotonic: float | None = None
        # construct-once (PRD §4.2): build recorder ONCE so models stay resident + toggle/start/stop
        # can arm the mic immediately. Injectable for unit tests (fakes → cheap, no RealtimeSTT).
        self._recorder = recorder if recorder is not None else build_recorder(cfg, feedback)
        self._backend = backend if backend is not None else typing_backends.make_backend(cfg.output)

    def run(self) -> None:
        """The listen-forever loop (main thread, BLOCKS until shutdown)."""
        self._start_monotonic = time.monotonic()
        self._feedback.set_listening(False)   # PRD §4.9: starts NOT listening (no hot-mic on boot)
        logger.info("voice-typing daemon ready (not listening); recorder resident")
        while not self._shutdown.is_set():
            if self._listening.is_set():
                # blocks until ONE utterance finalizes → on_final in a NEW thread → returns → re-listen.
                # Returning is NORMAL SEGMENTATION, never session end (the WhisperX-flaw fix, PRD §1 #1).
                self._recorder.text(self.on_final)
            else:
                time.sleep(0.05)
        logger.info("shutdown requested; run() loop exiting")

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

    def _arm(self) -> None:
        """Private: arm mic + set listening + notify. Called under the lock by start/toggle."""
        self._listening.set()
        self._recorder.set_microphone(True)
        self._feedback.set_listening(True)

    def _disarm(self) -> None:
        """Private: disarm mic + abort blocked text() + clear listening + notify. Called under lock."""
        self._listening.clear()
        self._recorder.set_microphone(False)
        self._recorder.abort()      # breaks any blocked text() so the loop re-checks the cleared gate
        self._feedback.set_listening(False)

    def start(self) -> None:
        with self._lock:
            self._arm()

    def stop(self) -> None:
        with self._lock:
            self._disarm()

    def toggle(self) -> None:
        with self._lock:
            if self._listening.is_set():
                self._disarm()
            else:
                self._arm()

    def request_shutdown(self) -> None:
        """Signal run() to exit. Sets the event + aborts (breaks a blocked text()). NO shutdown()."""
        self._shutdown.set()
        with self._lock:
            self._recorder.abort()    # break any blocked text() so run() can return
        # recorder.shutdown() (full teardown) is wired by the quit handler in P1.M4.T2.S2, NOT here.

    def is_listening(self) -> bool:
        return self._listening.is_set()

    @property
    def uptime_s(self) -> float:
        return time.monotonic() - self._start_monotonic if self._start_monotonic is not None else 0.0
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm inputs exist, the consumed APIs are callable, and the S1 baseline is green.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/daemon.py     && echo "ok: daemon.py (S1 build_recorder present)"  || echo "PREFLIGHT FAIL"
      test -f voice_typing/textproc.py   && echo "ok: textproc.py (clean)"                   || echo "PREFLIGHT FAIL"
      test -f voice_typing/typing_backends.py && echo "ok: typing_backends.py (make_backend)"|| echo "PREFLIGHT FAIL"
      test -f voice_typing/feedback.py   && echo "ok: feedback.py (record_final/set_listening)" || echo "PREFLIGHT FAIL"
      .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1   # expect "118 passed"
      .venv/bin/python -c "
from voice_typing import daemon
print('build_recorder:', callable(daemon.build_recorder))
from voice_typing import textproc, typing_backends
from voice_typing.config import VoiceTypingConfig
from voice_typing.feedback import Feedback
c = VoiceTypingConfig()
print('append_space:', c.output.append_space, '| filter:', type(c.filter).__name__)
import inspect
print('clean sig:', inspect.signature(textproc.clean))
print('make_backend sig:', inspect.signature(typing_backends.make_backend))
print('Feedback record_final:', callable(Feedback.record_final), '| set_listening:', callable(Feedback.set_listening))
import RealtimeSTT, inspect
for m in ['text','set_microphone','abort','shutdown']:
    print(m, inspect.signature(getattr(RealtimeSTT.AudioToTextRecorder, m)))
" || echo "PREFLIGHT FAIL"
  - EXPECTED: all 4 modules present; 118 passed; build_recorder callable; append_space True, filter FilterConfig;
    clean(text, cfg) sig; make_backend(cfg) sig; record_final+set_listening callable; the 4 RealtimeSTT sigs
    (text(self, on_transcription_finished=None); set_microphone(self, microphone_on=True); abort(self); shutdown(self)).
  - DO NOT: create/edit any file, run uv sync/add, or touch any other module.

Task 2: WRITE the test additions FIRST (TDD — RED until daemon.py gains VoiceTypingDaemon in Task 3).
        APPEND to tests/test_daemon.py: extend _FakeFeedback (record_final/set_listening + finals/
        listening_states), ADD _StubRecorder (text/set_microphone/abort/shutdown), ADD _FakeBackend
        (type_text, optional raise), ADD the ~12 tests from research §5 (on_final gate/happy/
        append_space/reject/typing-error; start/stop/toggle; run() loop; boot-no-hot-mic). See
        "Task 4 SOURCE additions" below for the verbatim additions.
  - FILE: tests/test_daemon.py (APPEND — do NOT remove or reorder S1's tests/stubs).
  - DO NOT: import RealtimeSTT/torch/ctranslate2 (Gotcha #11); import build_recorder's real path
    (inject the fake recorder — Gotcha #6/#7); use bare sleep in loop tests (Gotcha #10).

Task 3: MODIFY voice_typing/daemon.py — ADD `import threading`, `import time`, and the textproc/
        typing_backends imports to the top; UPDATE the module docstring's SCOPE/CONSUMES/CONSUMED BY
        lines to reflect the loop+on_final+gate+toggle; APPEND the VoiceTypingDaemon class (verbatim
        from "VoiceTypingDaemon reference implementation" above) BELOW the existing S1 functions.
        This turns the Task 2 tests GREEN.
  - FILE: voice_typing/daemon.py (MODIFY — additive; do NOT touch S1 functions).
  - DO NOT: call recorder.shutdown() in start/stop/toggle/request_shutdown (Critical #3/#8); set
    _listening in __init__ (Critical #4); forget the gate in on_final (Critical #2); take the lock in
    run() (Critical #5); import RealtimeSTT at module top (Critical #11); re-wire on_final as a
    constructor callback (Critical #12); add socket/main/signal/basicConfig/latency-timestamps
    (Success (i)).

Task 4: VALIDATE — run the Validation Loop L1 (py_compile + import purity), L2 (pytest daemon + full
        suite), L3 (scope guard grep), L4 (manual API smoke). Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M4.T1.S2: VoiceTypingDaemon listen-forever loop + on_final→type + listening gate + toggle + tests".
```

#### Task 4 SOURCE additions — `tests/test_daemon.py` (APPEND verbatim)

```python
# ===========================================================================
# P1.M4.T1.S2 — VoiceTypingDaemon: listen-forever loop + on_final + gate + toggle
# (ADDITIVE — everything above is S1; do not change it.)
# ===========================================================================
import threading
import time as _time


class _DaemonFakeFeedback(_FakeFeedback):
    """Extends S1's _FakeFeedback with record_final + set_listening (S2's contract)."""

    def __init__(self) -> None:
        super().__init__()
        self.finals: list[str] = []
        self.listening_states: list[bool] = []

    def record_final(self, text: str) -> None:
        self.finals.append(text)

    def set_listening(self, listening: bool) -> None:
        self.listening_states.append(listening)


class _StubRecorder:
    """Runtime stand-in for AudioToTextRecorder (held by VoiceTypingDaemon as an INSTANCE).
    Distinct from S1's _FakeRecorder (which captures **kwargs for construction). text() returns
    immediately so the loop spins fast when listening (loop-test friendliness — research §5)."""

    def __init__(self) -> None:
        self.text_calls = 0
        self.last_callback = None
        self.mic: list[bool] = []
        self.aborts = 0
        self.shutdowns = 0

    def text(self, on_transcription_finished=None):
        self.text_calls += 1
        self.last_callback = on_transcription_finished
        return ""   # mimic RealtimeSTT: returns "" when interrupted/idle; loop re-enters

    def set_microphone(self, microphone_on=True):
        self.mic.append(microphone_on)

    def abort(self):
        self.aborts += 1

    def shutdown(self):
        self.shutdowns += 1


class _FakeBackend:
    """Records type_text calls; optionally raises to test on_final error handling."""

    def __init__(self, *, raise_on: str | None = None) -> None:
        self.typed: list[str] = []
        self._raise_on = raise_on

    def type_text(self, text: str) -> None:
        if self._raise_on is not None and text == self._raise_on:
            raise RuntimeError("boom (test)")
        self.typed.append(text)


def _wait_for(predicate, timeout=2.0, interval=0.01):
    """Poll until predicate() is truthy or timeout (s). Returns True if predicate became truthy."""
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if predicate():
            return True
        _time.sleep(interval)
    return predicate()


def _make_daemon(*, recorder=None, backend=None, cfg=None):
    cfg = cfg or VoiceTypingConfig()
    fb = _DaemonFakeFeedback()
    rec = recorder if recorder is not None else _StubRecorder()
    be = backend if backend is not None else _FakeBackend()
    d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be)
    return d, fb, rec, be


# --- boot: no hot-mic (PRD §4.9) ---


def test_fresh_daemon_not_listening():
    d, _, _, _ = _make_daemon()
    assert d.is_listening() is False


# --- on_final: gate / happy / append_space / reject / typing-error ---


def test_on_final_gate_when_not_listening():
    d, fb, rec, be = _make_daemon()
    # listening is False at boot → on_final drops everything
    d.on_final("hello world")
    assert be.typed == []
    assert fb.finals == []


def test_on_final_happy_path_appends_space():
    d, fb, rec, be = _make_daemon()
    d.start()   # arm
    d.on_final("hello world")
    assert be.typed == ["hello world "]   # append_space default True
    assert fb.finals == ["hello world"]   # recorded WITHOUT the trailing space


def test_on_final_append_space_false():
    cfg = VoiceTypingConfig()
    cfg.output.append_space = False
    d, fb, rec, be = _make_daemon(cfg=cfg)
    d.start()
    d.on_final("hello world")
    assert be.typed == ["hello world"]
    assert fb.finals == ["hello world"]


def test_on_final_rejects_hallucination():
    d, fb, rec, be = _make_daemon()
    d.start()
    d.on_final("thank you.")   # blocklist entry → textproc.clean returns None
    assert be.typed == []
    assert fb.finals == []


def test_on_final_typing_raises_is_caught_and_record_still_happens():
    d, fb, rec, be = _make_daemon(backend=_FakeBackend(raise_on="boom "))
    d.start()
    d.on_final("boom")   # payload "boom " matches raise_on → type_text raises
    assert be.typed == []          # nothing typed (it raised)
    assert fb.finals == ["boom"]   # record_final STILL called (recognition is final regardless)


# --- start / stop / toggle ---


def test_start_arms():
    d, fb, rec, be = _make_daemon()
    d.start()
    assert d.is_listening() is True
    assert rec.mic == [True]
    assert fb.listening_states == [True]


def test_stop_disarms_and_aborts():
    d, fb, rec, be = _make_daemon()
    d.start()
    d.stop()
    assert d.is_listening() is False
    assert rec.mic == [True, False]
    assert rec.aborts >= 1
    assert fb.listening_states == [True, False]


def test_toggle_off_to_on_arms():
    d, fb, rec, be = _make_daemon()
    assert d.is_listening() is False
    d.toggle()
    assert d.is_listening() is True
    assert rec.mic == [True]


def test_toggle_on_to_off_disarms():
    d, fb, rec, be = _make_daemon()
    d.start()
    d.toggle()
    assert d.is_listening() is False
    assert rec.mic == [True, False]
    assert rec.aborts >= 1


def test_toggle_is_an_invololution():
    d, _, _, _ = _make_daemon()
    before = d.is_listening()
    d.toggle(); d.toggle()
    assert d.is_listening() is before


def test_stop_never_calls_recorder_shutdown():
    d, fb, rec, be = _make_daemon()
    d.start(); d.stop()
    assert rec.shutdowns == 0   # Critical #3: shutdown() is ONLY for quit (P1.M4.T2.S2)


# --- request_shutdown ---


def test_request_shutdown_sets_event_and_aborts_not_shutdown():
    d, fb, rec, be = _make_daemon()
    d.request_shutdown()
    assert rec.aborts >= 1
    assert rec.shutdowns == 0   # NO full teardown here (P1.M4.T2.S2 owns it)


# --- run() loop ---


def test_run_loop_not_listening_does_not_call_text():
    d, fb, rec, be = _make_daemon()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: True, timeout=0.2)   # let it sleep-loop a moment
        assert rec.text_calls == 0             # not listening → never calls text()
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)
    assert not t.is_alive()


def test_run_loop_calls_text_when_listening_then_exits_on_shutdown():
    d, fb, rec, be = _make_daemon()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        d.start()
        assert _wait_for(lambda: rec.text_calls >= 2, timeout=2.0), rec.text_calls
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)
    assert not t.is_alive()


def test_run_sets_uptime_after_start():
    d, fb, rec, be = _make_daemon()
    assert d.uptime_s == 0.0   # not started yet
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d.uptime_s >= 0.0 and d._start_monotonic is not None, timeout=1.0)
        assert d.uptime_s >= 0.0
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)
```

### Implementation Patterns & Key Details

```python
# The loop (PRD §4.2 item 1 — the WhisperX-flaw fix):
while not self._shutdown.is_set():
    if self._listening.is_set():
        self._recorder.text(self.on_final)   # blocks → 1 utterance → on_final NEW thread → returns → re-listen
    else:
        time.sleep(0.05)
# CRITICAL: text() returning is NORMAL SEGMENTATION, never session end. Do NOT break on return.

# on_final (fired by RealtimeSTT in a NEW thread — never raise):
def on_final(self, text):
    if not self._listening.is_set(): return      # GATE: race guard (toggle-off race, PRD §4.2/§8)
    cleaned = textproc.clean(text, self._cfg.filter)
    if not cleaned: return                        # None (reject) or "" → drop
    payload = cleaned + (" " if self._cfg.output.append_space else "")
    try:
        self._backend.type_text(payload)          # may raise → caught (thread survives)
    except Exception:
        logger.exception("typing backend failed for final %r", cleaned)
    self._feedback.record_final(cleaned)          # cleaned, NO trailing space (state-file concern)

# Arming (PRD §4.2 item 2; research §4) — private helpers under the lock:
def _arm(self):
    self._listening.set(); self._recorder.set_microphone(True); self._feedback.set_listening(True)
def _disarm(self):
    self._listening.clear(); self._recorder.set_microphone(False)
    self._recorder.abort()    # break any blocked text() → loop re-checks gate → sleep branch
    self._feedback.set_listening(False)
def toggle(self):
    with self._lock:
        if self._listening.is_set(): self._disarm()
        else: self._arm()
```

### Integration Points

```yaml
MODULE-INTERNAL:
  - add to: voice_typing/daemon.py (top imports)
  - pattern: "import threading\nimport time\nimport voice_typing.textproc as textproc\nimport voice_typing.typing_backends as typing_backends"
  - note: "RealtimeSTT stays lazy inside build_recorder (S1). The daemon class holds self._recorder as a ref, never imports AudioToTextRecorder."
  - add to: voice_typing/daemon.py (below S1 functions)
  - pattern: "class VoiceTypingDaemon: ... (verbatim from reference implementation)"
  - update: module docstring SCOPE/CONSUMES/CONSUMED BY lines to mention the loop+on_final+gate+toggle.

CONSUMED (READ ONLY — do NOT edit):
  - build_recorder(cfg, feedback) -> recorder   # S1, already in daemon.py
  - textproc.clean(text, cfg.filter) -> str|None
  - typing_backends.make_backend(cfg.output) -> TypingBackend ; .type_text(text)
  - Feedback.record_final(text) / Feedback.set_listening(bool)

EXPOSED FOR DOWNSTREAM (do NOT rename):
  - run() / on_final() / start() / stop() / toggle() / request_shutdown() / is_listening() / uptime_s
  - consumed by: P1.M4.T2.S1 (socket), P1.M4.T3.S1 (entry point), P1.M7.T2.S1 (feed_audio test)

NO DATABASE / NO CONFIG EDITS / NO ROUTES. This is a pure-Python daemon class.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing

# py_compile after editing daemon.py + test_daemon.py — fix before proceeding.
.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py

# Import purity: importing daemon must NOT bind RealtimeSTT/torch/ctranslate2 at module top.
.venv/bin/python -c "
import sys, voice_typing.daemon as d
bad = [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
print('leaked heavy imports:', bad)
assert not bad, f'heavy imports leaked at module top: {bad}'
assert hasattr(d, 'VoiceTypingDaemon'), 'VoiceTypingDaemon missing'
assert hasattr(d, 'build_recorder'), 'S1 build_recorder still present (regression!)'
print('ok: import-pure + VoiceTypingDaemon present + S1 surface intact')
"
# mypy is NOT installed — do NOT run it. ruff is optional (/home/dustin/.local/bin/ruff).
# Expected: py_compile exits 0; purity prints 'leaked heavy imports: []' + 'ok: ...'.
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing

# S2 + S1 daemon tests (the extended file).
.venv/bin/python -m pytest tests/test_daemon.py -v

# Full suite — must stay green (was 118 passing pre-S2; S2 adds ~14 → ~132).
.venv/bin/python -m pytest tests/ -q

# Expected: all pass. If a loop test flakes, it's a _wait_for timeout — re-run once; if it persists,
# the loop/abort logic is wrong (debug run()/request_shutdown, not the test). S1's tests MUST stay
# green (they assert build_recorder/cfg_to_kwargs/callbacks unchanged).
```

### Level 3: Scope Guard (Integration Boundary)

```bash
cd /home/dustin/projects/voice-typing

# Forbidden tokens in daemon.py — NONE of these belong in S2 (socket/main/signal/basicConfig/
# recorder.shutdown inside toggle/stop/start/request_shutdown).
echo "=== forbidden token scan (expect no matches) ==="
grep -nE 'socket\.socket|json\.loads|signal\.|def main\(|if __name__|basicConfig' voice_typing/daemon.py || echo "ok: none of socket/main/signal/basicConfig"
echo "=== recorder.shutdown inside toggle/stop/start/request_shutdown (expect none) ==="
grep -nE 'recorder\.shutdown|self\._recorder\.shutdown' voice_typing/daemon.py || echo "ok: no recorder.shutdown() calls anywhere (correct — T2.S2 owns teardown)"

# Expected: both greps print 'ok: ...' (no matches). A match means scope creep — remove it.
```

### Level 4: Live API Smoke (Confidence — the RealtimeSTT contract)

```bash
cd /home/dustin/projects/voice-typing

# Re-confirm the RealtimeSTT control-API signatures S2 relies on (text/set_microphone/abort/shutdown).
# These are the methods VoiceTypingDaemon calls; a drift here is the #1 project risk (PRD §8 #5).
.venv/bin/python -c "
import inspect
from RealtimeSTT import AudioToTextRecorder
for m in ['text','set_microphone','abort','shutdown']:
    print(m, inspect.signature(getattr(AudioToTextRecorder, m)))
"
# Expected:
#   text (self, on_transcription_finished=None)
#   set_microphone (self, microphone_on=True)
#   abort (self)
#   shutdown (self)
# If these differ, STOP and reconcile with research §1 before proceeding (API drift).

# Manual daemon-class smoke (no mic, no models — inject a stub):
.venv/bin/python -c "
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig

class StubRec:
    def __init__(self): self.calls=0; self.mic=[]; self.aborts=0
    def text(self, cb=None): self.calls+=1; return ''
    def set_microphone(self, on=True): self.mic.append(on)
    def abort(self): self.aborts+=1
class StubBe:
    def __init__(self): self.typed=[]
    def type_text(self, t): self.typed.append(t)
class StubFb:
    def __init__(self): self.finals=[]; self.ls=[]
    def record_final(self, t): self.finals.append(t)
    def set_listening(self, b): self.ls.append(b)

r=StubRec(); d=daemon.VoiceTypingDaemon(VoiceTypingConfig(), StubFb(), recorder=r, backend=StubBe())
assert d.is_listening() is False, 'boot hot-mic!'
d.start(); assert d.is_listening() is True
d.on_final('hello world')   # would type via the stub backend
d.stop(); assert d.is_listening() is False; assert r.aborts>=1
print('manual smoke ok: boot-no-hot-mic + start + on_final + stop(all green)')
"
# Expected: 'manual smoke ok: ...'. Exercises the real VoiceTypingDaemon end-to-end (stub deps).
```

## Final Validation Checklist

### Technical Validation

- [ ] All 4 validation levels completed successfully.
- [ ] L1: `.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py` exits 0.
- [ ] L1: import-purity check prints `leaked heavy imports: []` + `VoiceTypingDaemon present`.
- [ ] L2: `.venv/bin/python -m pytest tests/test_daemon.py -v` all pass (S1 + S2).
- [ ] L2: `.venv/bin/python -m pytest tests/ -q` green (no regression to the other 5 files; ~132 total).
- [ ] L3: scope-guard greps print `ok: ...` (no socket/main/signal/basicConfig/recorder.shutdown in S2).
- [ ] L4: live RealtimeSTT signature smoke matches the 4 expected signatures.
- [ ] L4: manual daemon-class smoke prints `manual smoke ok: ...`.

### Feature Validation

- [ ] `VoiceTypingDaemon` exists with run/on_final/_arm/_disarm/start/stop/toggle/request_shutdown/
      is_listening/uptime_s.
- [ ] Boot-no-hot-mic: `is_listening()` is `False` on a freshly constructed daemon (PRD §4.9).
- [ ] `run()` loop shape exact: NOT listening → no `text()` calls; listening → `text()` called; shutdown
      → loop exits, thread joins.
- [ ] `on_final` gate drops finals when not listening (toggle-off race guard, PRD §4.2/§8).
- [ ] `on_final` happy path types `text + " "` and records cleaned `text` (no trailing space).
- [ ] `on_final` typing failure is caught + logged; `record_final` STILL called.
- [ ] `start`/`stop`/`toggle` arm/disarm via `set_microphone`(+`abort` on disarm); models stay resident.
- [ ] `request_shutdown` sets the event + aborts; does NOT call `recorder.shutdown()`.

### Code Quality Validation

- [ ] Follows existing codebase patterns (module docstring CONSUMES/CONSUMED BY/SCOPE style; logger;
      `from __future__ import annotations`; TYPE_CHECKING Feedback; keyword-only injectable args).
- [ ] File placement: class ADDED to the existing `voice_typing/daemon.py`; tests APPENDED to the
      existing `tests/test_daemon.py` (no new files).
- [ ] Anti-patterns avoided: no `recorder.shutdown()` on toggle (Critical #3); no lock in `run()`
  (Critical #5); no RealtimeSTT import at module top (Critical #11); no re-wiring on_final as a
  constructor callback (Critical #12).
- [ ] S1 surface intact: `build_recorder`/`cfg_to_kwargs`/`_build_callbacks`/`_filter_kwargs_to_signature`/
      `_construct`/`_FIXED_KWARGS` unchanged (S1 tests green).
- [ ] Dependencies: only `threading`/`time`/`textproc`/`typing_backends` added at module top (all cheap).

### Documentation & Deployment

- [ ] Module docstring updated: SCOPE/CONSUMES/CONSUMED BY mention the loop+on_final+gate+toggle and
      the later subtasks that complete the daemon (socket T2.S1, quit T2.S2, main T3, latency S3).
- [ ] `run()` logs "voice-typing daemon ready (not listening)" at start + "shutdown requested" at exit.
- [ ] `on_final` logs "final typed: %r" (per-utterance; precise timestamps are S3).
- [ ] No new environment variables (this is a pure-Python class).

---

## Anti-Patterns to Avoid

- ❌ Don't `recorder.shutdown()` on toggle/stop — it destroys models; only `abort()` (Critical #3).
- ❌ Don't `break` the loop when `recorder.text()` returns — that returning is normal segmentation, the
  whole point of the WhisperX-flaw fix (Critical #1). Only `_shutdown.is_set()` ends the loop.
- ❌ Don't skip the gate in `on_final` — a final completing right after toggle-off would type one last
  utterance (PRD §4.2/§8 toggle-off race) (Critical #2).
- ❌ Don't let `on_final` raise unhandled — it runs in a RealtimeSTT worker thread; wrap typing in
  try/except + logger.exception (Critical #2).
- ❌ Don't take the lock in `run()` — it only reads Events + calls `recorder.text()`; the lock is for
  start/stop/toggle/request_shutdown only (Critical #5).
- ❌ Don't build the recorder lazily in `run()` — construct it ONCE in `__init__` (eager) so the socket
  can arm before `run()` starts, and inject a fake in tests (Critical #6/#7).
- ❌ Don't import RealtimeSTT at module top — it stays lazy inside `build_recorder` (Critical #11).
- ❌ Don't re-wire `on_final` as a constructor callback or add it to `_FIXED_KWARGS` — it's the
  `on_transcription_finished` arg to `recorder.text()`, a DIFFERENT hook (Critical #12).
- ❌ Don't touch any S1 function or any other module — this subtask is purely ADDITIVE to daemon.py +
  test_daemon.py (Success (i)).
- ❌ Don't hardcode the space or min_chars — read `cfg.output.append_space` / pass `cfg.filter` to
  `textproc.clean` (Critical #8/#9).

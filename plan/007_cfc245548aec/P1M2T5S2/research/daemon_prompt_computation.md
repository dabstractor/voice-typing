# Research — P1.M2.T5.S2: daemon-side prompt computation + commit-time refresh

Codebase state verified by direct read (anchors are current-tree line numbers).

## What already exists (do NOT rebuild)

### Child side — P1.M2.T5.S1 (Complete)
- `voice_typing/prompt_engine.py`
  - `_PROMPT_TOKEN_CAP = 200` (~line 51) — THE code constant (PRD: Whisper ~224-token budget; 200 whitespace words = conservative proxy).
  - `trim_prompt(text, cap=200)` (~line 95) — pure: whitespace-normalize, keep NEWEST `cap` tokens.
  - `PromptedExecutor` — CUDA object, child-only; `set_prompt()` clears on ""/None.
  - Module scope is stdlib-only → **importable daemon-side** (docstring: "IMPORT PURITY: this module is importable ANYWHERE").
- `voice_typing/recorder_host.py`
  - `RecorderHost.set_prompt(text)` (~259-271) — daemon→child proxy: `cmd_q.put(("prompt", {"text": text}))`, best-effort, never blocks long.
  - Child cmd dispatch (~716-725): `("prompt", {...})` → `prompt_executor.set_prompt(...)`; DEBUG-ignored when degraded.
  - `_ready_payload` (~810-819): ready dict gains `context_prompt: bool`; exposed via `RecorderHost.device` property (~183-186).
  - Delivery timing (documented in-module): the child reads cmd_queue only BETWEEN `text()` blocks → commit-time sends land before the next utterance's decode. No watcher thread allowed.

### Daemon side — thin seam landed by T6.S2 (Complete)
- `voice_typing/daemon.py`
  - `on_final` (~1006-1105): listening gate → cancel-suppress → `textproc.clean` → rejected-final freeze path → streaming `self._stream.commit(cleaned)` (~1057) → `reset_boundary()` (~1101) → **`self._refresh_context_prompt()` (~1105)** — all inside `with self._on_final_lock:`.
  - Rev 1 branch (`output.streaming=false`): types payload via backend directly, does NOT touch the engine, does NOT refresh the prompt (gap).
  - `_refresh_context_prompt()` (~1353-1375): `text = streaming.context_after_last_boundary(self._stream.committed)`; `setter = getattr(self._host, "set_prompt", None)`; defensive, never raises. NOT gated on `cfg.asr.context_prompt`, not gated on child degrade.
  - `_arm()` (~1107-1129): resets flags, `stream_reset()` = `StreamingOutput.reset_session()` via getattr seam (~1117-1120); then arms mic. **No child prompt clear** → warm re-arm keeps the previous session's prompt in the resident child (bug this task fixes).
  - `_load_host` (~770-820): `factory = self._host_factory or RecorderHost` (~775) — the fake-host injection seam used by fast tests; on ready: `self._resolved_device_cache = host.device` (~797-800) — the ready dict (incl. `context_prompt`) is already in hand here.
  - `status_snapshot()` — builds control-socket status payload (consumed by ctl.py via `.get`).
- `voice_typing/streaming.py`
  - `context_after_last_boundary(committed)` (~44-62): returns `committed[last+1:].strip()` where last = max rfind of `.!?`; **returns `""` when NO boundary exists** — thin-seam semantics; docstring defers the formal computation to T5.S2.
  - `StreamingOutput.committed` property (~168) — the streaming-mode prompt source.
- `voice_typing/textproc.py`: `_SENTENCE_TERMINALS = ".!?"` (~79) + `apply_streaming_guards` (~82) — boundary set must stay consistent (streaming.py pins its copy "verbatim" to this).
- `voice_typing/config.py:63`: `AsrConfig.context_prompt: bool = True` (validated bool at ~109-114).
- `voice_typing/ctl.py` (~64-90): status multi-line printer reads response via `.get` — additive keys are safe.
- Tests: `tests/test_streaming_commit.py` (RecordingBackend/FakeFeedback/FakeClock doubles + slicer tests), `tests/test_prompt_engine.py` (S1), `tests/test_control_socket.py` (daemon with fake factory, no CUDA). `tests/test_daemon.py` / `test_recorder_host.py` / `test_feed_audio.py` are HEAVY (CUDA, `timeout 600`).

## Semantic decision (PRD §4.2quater, load-bearing for T8c)

"conditioned on the committed text **back to the last sentence boundary** (last `.`/`!`/`?`), capped at ~200 tokens":
- boundary exists mid-string → prompt = text AFTER it (current-in-progress sentence);
- committed ENDS with a terminator → prompt = "" (fresh sentence — decoder may capitalize);
- **NO terminator anywhere → prompt = the WHOLE committed text** (capped) — the seam's current `""` return is wrong. Proof it matters: `utt_pause.wav` first half ("I want to test whether this system") has no terminator; with `""` the post-pause half decodes context-free → mid-sentence capital + spurious period → **T8c fails**.
- Cap = reuse `prompt_engine.trim_prompt` (newest-200-tokens); child caps again (defense in depth).

**Composition trap:** `context_after_last_boundary(c) or trim_prompt(c)` is WRONG — `""` is ambiguous between "ends with terminator" (prompt must stay empty) and "no terminator" (prompt must be everything). The rfind must live inside the single formal function.

## Gaps S2 must close
1. Formal pure function `rolling_context_prompt(committed)` (home: `prompt_engine.py`).
2. Formalize `_refresh_context_prompt`: gate on `cfg.asr.context_prompt` AND child-ready `context_prompt` flag; source selector (streaming `committed` vs Rev 1 accumulator).
3. Arm-time clear: `host.set_prompt("")` queued BEFORE the arm cmd (FIFO ⇒ child clears before blocking in `text()`); reset trackers on arm.
4. Rev 1 rollback mode: daemon-side committed accumulator so `context_prompt=true` + `streaming=false` still conditions decodes.
5. Surface `context_prompt` in `status_snapshot()` + one ctl status line (explicitly handed over by S1's PRP: "daemon/status consumption is T5.S2").
6. Deliberate no-ops to document: rejected finals, cancel, and unload teardown do NOT refresh (committed unchanged / fragment never committed).

## Concurrency notes
- Refresh stays inside `_on_final_lock` (serializes with commit; `host.set_prompt` is a fast queue put).
- `_arm` runs under `self._lock`; NEVER take `self._lock` from the on_final path (existing lock-ordering rule).
- Never raise out of the refresh path (on_final thread must survive) — existing contract, keep.

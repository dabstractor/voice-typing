# Research — child-side dynamic prompt mechanism (P1.M2.T5.S1 / PRD §4.2quater R5)

The PRP (../PRP.md) is the runbook. This note records the verified library facts, the
**two premise corrections** to the item's RESEARCH NOTE, the design, and the test plan.

## 1. ★ TWO PREMISE CORRECTIONS (verified against the installed tree — override the item prose) ★

**(i) The RealtimeSTT "worker subprocess" is a THREAD on Linux — not a process.**
`RealtimeSTT/core/runtime.py:25-33` `start_recorder_worker`: on Linux it starts a
`threading.Thread`; only non-Linux uses `mp.Process`. So the engine created inside
`TranscriptionWorker.run()` (`core/transcription.py:93-107`) lives **in the
recorder-host child's own process**. Consequences:
- A monkeypatch applied in the child (before or after `build_recorder`) directly
  governs the engine thread — no cross-process patch-carrying, no fork-window race.
- The captured engine reference is directly mutable from any child thread
  (`engine.config.initial_prompt = text` is a plain attribute store).
- The item's "Linux fork start method carries both the patch and the shared value
  into the worker process" rationale dissolves — the mechanism is SIMPLER and MORE
  ROBUST than the item feared.

**(ii) The daemon→child context is `spawn`, not fork.**
`voice_typing/recorder_host.py:136` `ctx = mp.get_context("spawn")` (queues, abort
Event, and Process all spawn-context — required because RealtimeSTT's grandchildren
also spawn). So nothing is "fork-inherited" from the daemon either; any shared value
must be passed as a **spawn-process arg** (mp.Array supports this — mp re-creates the
shared-memory handle in the child; verified conceptually by the spawn-context Event at
:142 which is passed the same way). `mp.Array(ctypes.c_wchar, 2048)` roundtrips
strings (verified live: `.value = "…" / .value`).

## 2. Verified library seams (installed 1.0.2, all read live)

| fact | source |
|---|---|
| `create_transcription_engine` is a module-level symbol, wrappable | `core/transcription.py:15-17` (`from ..transcription_engines import create_transcription_engine`), called at `:93`. **Verified live: wrap fires, symbol replaceable.** |
| Engine prompt read PER CALL | `transcription_engines/base.py:163-166` `_get_prompt` returns `self.config.initial_prompt` → mutating `engine.config.initial_prompt` affects the next transcribe call. `BaseTranscriptionEngine` importable + has `_get_prompt` (verified). |
| `use_prompt=True` on BOTH paths | finals: `core/transcription_api.py:72` `perform_final_transcription(..., use_prompt=True)`; realtime: `core/realtime.py:306,371` `use_prompt=True`. |
| Single engine serves both paths | post-collapse construction `use_main_model_for_realtime=True` (P1.M1.T2.S2) → realtime round-trips the SAME worker pipe (`core/realtime.py:239-275`) → ONE captured engine covers partials AND finals. |
| Neither plain poke works | finals config baked in the worker (`core/transcription.py:93-107`, rebuilt never); the realtime poke seam (`recorder.realtime_transcription_model`) is SKIPPED when `use_main_model_for_realtime=True` (`core/initialization.py:434-437`). ⇒ the patch is REQUIRED. |

## 3. recorder_host.py seams (current, post-M1 collapse)

- `RecorderHost.__init__` (:103): creates `ctx = mp.get_context("spawn")` (:136), `self._cmd_q/self._evt_q = ctx.Queue()` (:137-138), `self._abort_event = ctx.Event()` (:142), `self._proc` (:143).
- `spawn()` (:172): `args=(self._cfg, self._cmd_q, self._evt_q, self._abort_event, self._force_cpu)` (:186).
- `_worker_main(cfg, cmd_q, evt_q, abort_event, force_cpu)` (:412): builds via `build_recorder(cfg, relay_fb, relay_lat, on_speech=...)` (+ force_cpu retry) (:462-472); `_abort_handler` thread (:502-513) polls `abort_event.wait(timeout=0.2)` → `recorder.abort()` — **the watcher pattern to mirror**; cmd loop `while running: kind, payload = cmd_q.get()` (:517-546) handling text/arm/disarm/abort/shutdown; `_safe_put(evt_q, item)` (:563) for events.
- Daemon-side `_dispatch(kind, payload)` (:345): kinds ready/error/final/partial/speech/speech_end/vad/gone — **add `prompt_mode`**.
- Module top is DAEMON-pure (only mp+threading+stdlib, :56) ⇒ the RealtimeSTT import for the patch MUST be LAZY (inside the child-side function).
- `cfg.asr.context_prompt: bool = True` exists (config.py:63, bool-guard :109-114; config.toml:37).

## 4. The design (mechanism, transport, probe, degrade, gate)

**Patch (child, before build_recorder, gated on cfg.asr.context_prompt):**
`_install_prompt_patch()` lazily imports `RealtimeSTT.core.transcription`, wraps
`create_transcription_engine` with a capture: `eng = orig(...); _PROMPT_STATE["engine"]
= eng; return eng`. Also imports `RealtimeSTT.transcription_engines.base` (assert
`_get_prompt` exists — a cheap forward-compat tripwire). The WHOLE patch install is
try/except: any failure (renamed symbol, import error) ⇒ leave unpatched ⇒ the probe
then degrades. Never raises into the child.

**Transport (daemon→child):** `mp.Array(ctypes.c_wchar, _PROMPT_ARR_LEN=2048)` +
`mp.Event prompt_event`, both spawn-ctx, created in `RecorderHost.__init__`, passed as
TWO extra args to `_worker_main`. `RecorderHost.set_prompt(text)` (new public method)
stores `arr.value = text[:_PROMPT_ARR_LEN-4]` then sets `prompt_event`. This bypasses
cmd_q entirely — the child's main loop BLOCKS in `text()` while armed, exactly when
prompts must flow (between partial decodes). This is the direct analog of
`abort_event` (:142 rationale comment).

**Apply (child):** `_prompt_watcher` thread (mirror `_abort_handler`): waits on
`prompt_event` (timeout 0.2 poll, also clears), reads `arr.value`, and if changed
applies `_set_engine_prompt(text)`: `eng = _PROMPT_STATE.get("engine"); if eng is not
None: eng.config.initial_prompt = text` (plain attribute store; the per-call
`_get_prompt` makes it live on the next decode — ≤ realtime_processing_pause for
partials, next final otherwise). ALSO a `('prompt', {'text': str})` cmd_q branch
(item-mandated): applies `_set_engine_prompt(payload["text"])` directly when the loop
is free (between utterances) — belt-and-braces with the watcher.

**Probe (child, after build_recorder + ready):** `_PROMPT_STATE["engine"] is not None`
⇒ our patched factory was actually used to build the engine (a future RealtimeSTT
rename would bypass the wrap ⇒ capture stays empty ⇒ degrade). NO decode needed.
Emit `("prompt_mode", {"dynamic": bool})` via `_safe_put`. On degrade: `logger.`
`warning(...)` ONCE (module-level `_PROMPT_STATE["degrade_logged"]` guard) — keep
decoding context-free; never crash, never wedge.

**Gate:** `cfg.asr.context_prompt` False ⇒ child never installs the patch, never
starts the watcher, ignores `('prompt',...)` cmds; daemon-side `set_prompt` no-ops.
(Whether the daemon ever CALLS set_prompt is T5.S2's concern.)

**Daemon surface (minimal):** `_dispatch` gains `elif kind == "prompt_mode":` → store
`self._prompt_mode = payload.get("dynamic")` + `logger.info` once. Exposed for
status/tests later (M3); T5.S2 consumes `set_prompt`.

## 5. Unit tests (tests/test_recorder_host.py — copy the established patterns; NO CUDA)

Follow the file's idioms: `_make_host` (:56), `_feed_event(host, kind, payload)` (:72),
`test_dispatch_*` (:82-158), fakes `_AbortFakeRecorder`/`_NormalFakeRecorder` (:393/:409),
monkeypatch (as :262-263). The child-side logic is factored into module-level functions
so they test WITHOUT spawning a process:
1. `test_prompt_cmd_applies_to_captured_engine` — `_PROMPT_STATE["engine"] = fake`
   (a tiny object with `.config.initial_prompt`); call the apply fn / drive the cmd
   branch; assert the attribute changed.
2. `test_prompt_patch_captures_engine` — monkeypatch the lazy RealtimeSTT import seam
   (a fake `t` module object with `create_transcription_engine`) → install patch → call
   the wrapped factory → engine captured.
3. `test_probe_degrades_when_no_engine_captured` — no capture ⇒ `_probe...` False; the
   degrade log fires exactly ONCE across two calls (caplog), nothing raises.
4. `test_context_prompt_false_disables_everything` — the install/watcher gate fn returns
   disabled; set_prompt on a host with the flag off puts nothing on cmd_q / writes no Array.
5. `test_set_prompt_writes_shared_array` — a real (spawn-ctx) Array: `set_prompt("abc")`
   ⇒ `arr.value == "abc"` + prompt_event set.
6. `test_dispatch_prompt_mode_stores_flag` — `_feed_event(host, "prompt_mode",
   {"dynamic": True})` ⇒ `host._prompt_mode is True` (mirror test_dispatch_ready :120).
No `build_recorder`/RealtimeSTT import in tests (the patch fn's import is monkeypatched).

## 6. Scope boundaries

DO: `voice_typing/recorder_host.py` (Array/event transport + spawn args + `set_prompt` +
`_dispatch` branch + child patch/watcher/cmd-branch/probe/degrade + module state) and
`tests/test_recorder_host.py` (the 6 tests).
DON'T: compute WHEN prompts ship (T5.S2 daemon-side), touch `daemon.py` (beyond nothing
— the dispatch branch is in recorder_host), touch `textproc` guards (T4.S1), the
streaming state machine (T6), cancel (T7), config schema (landed M1.T1.S1), README
(M3.T10). No new deps (mp/ctypes are stdlib).

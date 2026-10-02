# PRP — P1.M2.T5.S1 (dir P1M2T2S1): Child-side dynamic prompt mechanism + capability probe + degrade

## Goal

**Feature Goal**: Make the recorder-host child's single Whisper engine condition **both partial and final decodes** on a daemon-supplied rolling context prompt (PRD §4.2quater "Rolling context prompt"; risk row §8 "constructor-static in 1.0.2 → child updates between utterances; on failure degrade, never crash"). Both `initial_prompt`/`initial_prompt_realtime` are constructor-static in installed RealtimeSTT 1.0.2, and the single-model construction (`use_main_model_for_realtime=True`, P1.M1.T2.S2) routes BOTH paths through one worker-side engine whose config is baked at worker start — so a **child-side monkeypatch + shared-memory transport** is required, with a startup **capability probe** and a logged-once **degrade** to context-free decoding.

> **Two premise corrections (verified live — supersede the item's RESEARCH NOTE prose; research §1):** (i) RealtimeSTT's "worker subprocess" is a **thread** on Linux (`core/runtime.py:25-33`) — the engine lives in the recorder-host child's own process, so a patch applied in the child directly governs the engine thread and the captured reference is plainly mutable. (ii) The daemon→child context is **spawn** (`recorder_host.py:136`), not fork — the shared value is passed as a spawn-process arg (same as the existing `abort_event`). Both make the mechanism simpler and more robust than the item assumed.

**Deliverable** (2 files; no new deps — `multiprocessing`/`ctypes` are stdlib):
1. `voice_typing/recorder_host.py` — (a) fork/spawn-shared prompt transport: `mp.Array(ctypes.c_wchar, 2048)` + `prompt_event`, created in `RecorderHost.__init__` (spawn ctx), passed to `_worker_main`; new public `RecorderHost.set_prompt(text)`; (b) child-side `_install_prompt_patch()` (lazy-import `RealtimeSTT.core.transcription`, wrap `create_transcription_engine` to capture the engine; fully try/except), `_set_engine_prompt(text)` (mutates `engine.config.initial_prompt` — read per call at `base.py:163-166`), `_prompt_watcher` thread (mirror `_abort_handler`), a `('prompt', {'text': str})` cmd_q branch, a post-build capability probe, and a degrade path that logs ONCE; (c) gate everything on `cfg.asr.context_prompt` (False ⇒ never patch, never ship, watcher not started); (d) `('prompt_mode', {'dynamic': bool})` event on `evt_q` + a daemon `_dispatch` branch storing `self._prompt_mode`.
2. `tests/test_recorder_host.py` — 6 unit tests (fake engine/module; **no CUDA, no RealtimeSTT import, no process spawn**): patch-captures-engine, prompt-applies-to-poke-seam, degrade-logs-once-and-keeps-going, context_prompt=False disables entirely, set_prompt writes the shared array, dispatch stores prompt_mode.

**Success Definition**:
- (a) With `context_prompt=True` (default) and the probe passing, `host.set_prompt("…committed context…")` becomes visible to the child's engine as `engine.config.initial_prompt` within one watcher tick (≤0.25 s) or immediately when the child loop is free — affecting the NEXT partial decode (≤ `realtime_processing_pause`) and every subsequent final (`use_prompt=True` on both paths, verified `core/transcription_api.py:72` + `core/realtime.py:306,371`).
- (b) Probe failure (e.g. a future RealtimeSTT renames the factory so the wrap never fires) ⇒ `('prompt_mode', {'dynamic': False})` + exactly ONE warning log; decoding continues context-free; the child never crashes or wedges.
- (c) `context_prompt=False` ⇒ no patch install, no watcher thread, `('prompt',…)` cmd ignored, `set_prompt` a no-op.
- (d) `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q` → all pass (existing + 6 new); `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- (e) Daemon-process import purity preserved: the RealtimeSTT import stays LAZY inside the child-side patch function (module top of recorder_host.py remains mp+threading+stdlib only).
- (f) No out-of-scope files: no `daemon.py` (the dispatch branch lives in recorder_host `_dispatch`), no config schema (landed P1.M1.T1.S1), no T5.S2/T6/T7 work.

## User Persona

Not applicable (internal engine mechanism; DOCS: none beyond code comments — config.toml's `context_prompt` comment already landed). Beneficiaries: the end user (mid-paragraph continuations decode coherently — §4.2quater's stated primary fix for wrongly-capitalized/punctuated fragments) and T5.S2 (consumes `set_prompt`), P1.M3.T8.S1 assert (d) (asserts the prompt path).

## Why

- **§4.2quater's primary accuracy fix.** "Every decode is conditioned on the committed text back to the last sentence boundary (~200-token cap)… This is the primary fix for mid-paragraph fragments starting capitalized or acquiring spurious trailing periods." Without this task there is NO mechanism to deliver that conditioning — both prompt kwargs are constructor-static and the single-model path defeats the one live poke seam (verified, research §2).
- **Risk row §8 prescribes exactly this.** "`initial_prompt`/`initial_prompt_realtime` are constructor-static (verified) → child updates them between utterances (small local patch); on failure degrade to context-free decoding + log, never crash."
- **The patched seam is verified live.** `create_transcription_engine` is a wrappable module symbol (`core/transcription.py:15-17`, called at `:93`); the engine re-reads `self.config.initial_prompt` per call (`base.py:163-166`); the Linux worker is a thread in the child (research §1) — so capture+mutate works with no cross-process gymnastics. The probe (capture flag) needs no decode.
- **Degrade-first safety.** The patch is belt-and-braces AROUND an unmodified decode path: if anything drifts, the probe reports degraded and behavior is exactly today's context-free decoding — a strictly-additive feature that cannot regress transcription.

## What

Add to `recorder_host.py`: a spawn-shared prompt channel (Array + Event) with a public `set_prompt`; a child-side lazy monkeypatch that captures the engine via the factory wrap; a prompt-watcher thread + a `('prompt',…)` cmd branch that write `engine.config.initial_prompt`; a post-build capability probe emitting `('prompt_mode', {'dynamic': bool})`; a log-once degrade; all gated on `cfg.asr.context_prompt`. Plus 6 hermetic unit tests.

### Success Criteria

- [ ] `RecorderHost.__init__` creates `_prompt_arr = ctx.Array(ctypes.c_wchar, 2048)` + `_prompt_event = ctx.Event()` (spawn ctx, same as the queues/abort_event) and `spawn()` passes both as extra args to `_worker_main`.
- [ ] `RecorderHost.set_prompt(text)` truncates to the array bound, writes `arr.value`, sets `_prompt_event`; no-op when `cfg.asr.context_prompt` is False.
- [ ] Child: `_install_prompt_patch()` (lazy RealtimeSTT import; wrap-capture; try/except-everything) is called before `build_recorder` ONLY when `cfg.asr.context_prompt`; `_prompt_watcher` thread mirrors `_abort_handler` (event-wait 0.2 s poll → read array → `_set_engine_prompt`); a `('prompt', {'text'})` cmd branch applies directly.
- [ ] `_set_engine_prompt` mutates the captured `engine.config.initial_prompt` (guard: engine not captured ⇒ silent no-op so the degraded child never errors).
- [ ] After the recorder builds (ready), the probe emits `("prompt_mode", {"dynamic": captured})`; on False exactly ONE warning logs (repeat calls never re-log); nothing raises.
- [ ] `_dispatch` gains `elif kind == "prompt_mode":` storing `self._prompt_mode` + one INFO log; unknown-kind tolerance unchanged.
- [ ] 6 new tests pass; existing `test_recorder_host.py` tests pass unchanged; fast suite green.
- [ ] `git status --short` == `voice_typing/recorder_host.py` + `tests/test_recorder_host.py` only.

## All Needed Context

### Context Completeness Check

_Pass._ The two premise corrections (Linux worker = thread; spawn ctx) are verified with file:line and change the risk calculus — documented up front (research §1). Every library seam is verified live (wrappable factory symbol; per-call prompt read; `use_prompt=True` both paths; single-engine routing) with file:line (research §2). The recorder_host integration points (init :136-143, spawn args :186, `_worker_main` :412/:462-472/:517-546, `_abort_handler` :502-513, `_safe_put` :563, `_dispatch` :345) are pinned. The full child-side code is given verbatim in the blueprint; the 6 tests follow the file's established fakes/idioms (research §5). A live smoke of the exact patch mechanics (wrap + Array roundtrip) passed.

### Documentation & References

```yaml
- docfile: plan/007_cfc245548aec/P1M2T2S1/research/child_dynamic_prompt.md
  why: "§1 THE TWO PREMISE CORRECTIONS (thread-not-process; spawn-not-fork) with file:line. §2 verified
        library seams table (factory :15-17/:93; per-call read :163-166; use_prompt both paths;
        single-engine; why plain pokes fail). §3 recorder_host integration points. §4 the design
        (patch/transport/apply/probe/degrade/gate). §5 the 6 tests. §6 scope."
  critical: "Design §4 is the contract: Array+Event transport (NOT cmd_q-only — the loop blocks in text());
             lazy import; try/except-everything patch; probe = capture flag; log-once degrade."
- file: voice_typing/recorder_host.py
  why: "The file being edited. Module top must STAY daemon-pure (:56 comment) — RealtimeSTT import stays
        lazy. Integration sites: __init__ spawn-ctx block (:136-143), spawn args (:186), _worker_main
        (:412; build :462-472; cmd loop :517-546), _abort_handler (:502-513 — the watcher template),
        _safe_put (:563), _dispatch (:345-384)."
  critical: "Mirror _abort_handler's structure exactly for _prompt_watcher (daemon thread, event.wait(0.2),
             clear). Keep the Array write under its built-in lock semantics (.value assignment). Pass the
             Array+Event as spawn args — do NOT use globals for daemon→child transport."
- file: tests/test_recorder_host.py
  why: "The established idioms: _make_host (:56), _feed_event (:72), test_dispatch_* (:82-158),
        _AbortFakeRecorder/_NormalFakeRecorder (:393/:409), monkeypatch (:262-263)."
  critical: "NO RealtimeSTT import, NO build_recorder call, NO process spawn in the new tests — monkeypatch
             the lazy-import seam with a fake module object."
- file: voice_typing/config.py
  why: "cfg.asr.context_prompt: bool = True (:63, bool-guard :109-114) — the gate flag (landed M1.T1.S1)."
  critical: "Read the flag in BOTH processes (host-side set_prompt gate + child-side install gate)."
- docfile: plan/007_cfc245548aec/architecture/realtimestt_internals.md
  why: "§3 the prompt-consumption verdicts (finals baked in worker :93-107; realtime poke seam skipped
        under use_main_model_for_realtime); §5 abort/clear primitives; §7 the poke-slot discussion this
        task implements."
  critical: "The internals doc's 'worker subprocess' framing predates the runtime.py:25-33 thread discovery —
             research §1 supersedes it for Linux."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/recorder_host.py   # EDIT: transport + patch + watcher + cmd branch + probe + dispatch branch.
tests/test_recorder_host.py     # EDIT: +6 tests (hermetic).
# daemon.py / config.py / config.toml / textproc / typing_backends — UNCHANGED (T5.S2/T4/T6/M1 own them).
```

### Known Gotchas

```python
# CRITICAL #1 — THE LOOP BLOCKS IN text(): cmd_q alone CANNOT deliver prompts mid-utterance. The
#   Array+prompt_event side channel (mirroring abort_event) is the transport; the cmd_q ('prompt',…)
#   branch is the belt-and-braces apply when the loop is free. Do NOT ship cmd_q-only.
# CRITICAL #2 — LAZY IMPORT. recorder_host.py's module top is imported by the daemon and must stay
#   mp+threading+stdlib. The RealtimeSTT import happens INSIDE _install_prompt_patch (child only).
# CRITICAL #3 — TRY/EXCEPT-EVERYTHING around the patch install and the engine poke. A future RealtimeSTT
#   rename must degrade (probe False), never raise into _worker_main. _set_engine_prompt guards
#   engine-is-None. The degrade log fires EXACTLY ONCE (module-state flag).
# CRITICAL #4 — SPAWN CTX for the Array+Event (ctx.Array/ctx.Event with the SAME get_context("spawn")).
#   Truncate text to the array bound minus headroom before .value assignment.
# CRITICAL #5 — AGENTS.md: wrap every pytest run in `timeout N` (inner) + bash-tool timeout (outer).
#   Never run the daemon/voicectl un-timed. No CUDA in unit tests (monkeypatch the import seam).
# CRITICAL #6 — Don't touch daemon.py: the dispatch branch for prompt_mode lives in recorder_host
#   (_dispatch). Don't add config fields, don't compute prompt text (T5.S2), no streaming-state work (T6).
```

## Implementation Blueprint

### Data models and structure

Module-level child state (recorder_host.py, defined near `_worker_main`):

```python
_PROMPT_ARR_LEN = 2048  # ~2 KB c_wchar buffer for the rolling context prompt (item contract)

_PROMPT_STATE: dict = {"engine": None, "degrade_logged": False}  # child-process-local (thread-shared)
```

Transport objects (daemon-side init, child receives as args): `ctx.Array(ctypes.c_wchar, _PROMPT_ARR_LEN)` + `ctx.Event()`.

### Implementation Tasks (dependency-ordered)

```yaml
Task 1: recorder_host.py — transport + host API
  - INIT: after self._abort_event (:142) add self._prompt_arr/self._prompt_event (spawn ctx).
  - SPAWN args (:186): append self._prompt_arr, self._prompt_event.
  - PUBLIC: set_prompt(text) — gate cfg.asr.context_prompt; truncate; arr.value=…; prompt_event.set().

Task 2: recorder_host.py — child patch + apply + watcher + cmd branch + probe + degrade
  - Add the module functions (verbatim block below) BEFORE _worker_main.
  - _worker_main: accept (cfg, cmd_q, evt_q, abort_event, force_cpu, prompt_arr, prompt_event);
    if cfg.asr.context_prompt: _install_prompt_patch(); after build succeeds + before the cmd loop,
    start the _prompt_watcher thread (mirror _abort_handler :502-513); probe: _safe_put(evt_q,
    ("prompt_mode", {"dynamic": _PROMPT_STATE["engine"] is not None})) — on False log the ONE warning.
  - CMD LOOP: add `elif kind == "prompt":` → _set_engine_prompt(str(payload.get("text", ""))).

Task 3: recorder_host.py — daemon dispatch
  - _dispatch: add `elif kind == "prompt_mode":` → self._prompt_mode = bool(payload.get("dynamic"));
    logger.info once. (Init self._prompt_mode = None in __init__.)

Task 4: tests/test_recorder_host.py — the 6 tests (verbatim specs in research §5)
```

### Child-side code (verbatim)

```python
_PROMPT_ARR_LEN = 2048  # ~2 KB c_wchar rolling-context-prompt buffer (PRD §4.2quater / P1.M2.T5.S1)
# Child-process-local patch state (the RealtimeSTT "worker" is a THREAD on Linux — core/runtime.py:25-33 —
# so this dict and the captured engine reference are shared with the transcribe thread directly).
_PROMPT_STATE: dict = {"engine": None, "degrade_logged": False}


def _install_prompt_patch() -> bool:
    """Child-only: wrap the engine factory so we can capture (and later re-prompt) the engine.

    RealtimeSTT 1.0.2 bakes initial_prompt into a TranscriptionEngineConfig at worker start
    (core/transcription.py:93-107) and the engine re-reads self.config.initial_prompt on EVERY
    transcribe (transcription_engines/base.py:163-166). Capturing the engine lets us mutate that
    config between utterances -> dynamic prompt for BOTH partials and finals (single engine under
    use_main_model_for_realtime=True; use_prompt=True on both paths). LAZY import: the daemon
    imports this module too and must stay RealtimeSTT-free. NEVER raises — any drift (renamed
    symbol, import error) leaves the child unpatched so the capability probe degrades cleanly.
    """
    try:
        import RealtimeSTT.core.transcription as _t
        if getattr(_t, "_vt_prompt_patch", False):
            return True  # idempotent
        _orig = _t.create_transcription_engine

        def _capturing_factory(*args, **kwargs):
            engine = _orig(*args, **kwargs)
            try:
                _PROMPT_STATE["engine"] = engine
            except Exception:
                pass
            return engine

        _t.create_transcription_engine = _capturing_factory
        _t._vt_prompt_patch = True
        return True
    except Exception:
        return False


def _set_engine_prompt(text: str) -> None:
    """Apply the rolling prompt to the captured engine (child thread-safe: plain attr store)."""
    engine = _PROMPT_STATE.get("engine")
    if engine is None:
        return  # degraded (probe not yet passed / patch drifted): decode context-free, never error
    try:
        engine.config.initial_prompt = text or None  # "" -> None -> _get_prompt yields no prompt
    except Exception:
        pass


def _prompt_degrade_log_once() -> None:
    """Log the dynamic-prompt degrade exactly once per child process (never spam, never crash)."""
    if not _PROMPT_STATE["degrade_logged"]:
        _PROMPT_STATE["degrade_logged"] = True
        logger.warning(
            "dynamic context prompt unavailable (engine not captured); "
            "decoding without context (degraded, transcription continues)"
        )


def _prompt_watcher(prompt_arr: Any, prompt_event: Any) -> None:
    """Child thread: mirror of _abort_handler — apply prompt updates while the main loop blocks in text()."""
    last = None
    while True:
        if prompt_event.wait(timeout=0.2):
            try:
                prompt_event.clear()
                text = prompt_arr.value
                if text != last:
                    _set_engine_prompt(text)
                    last = text
            except Exception:
                pass  # a prompt update must never take down the child
```

`_worker_main` wiring (precise placements):
- signature → `(cfg, cmd_q, evt_q, abort_event, force_cpu, prompt_arr, prompt_event)`;
- after the build succeeds (recorder is not None), before the cmd loop:
```python
    if getattr(cfg.asr, "context_prompt", False):
        _install_prompt_patch()  # NOTE: must run BEFORE build_recorder — see ordering below
```
  **Ordering:** the patch must be installed BEFORE `build_recorder(...)` (the worker thread + engine are
  created inside construction; the wrap must be live at factory-call time). So place the
  `_install_prompt_patch()` call immediately BEFORE the first `try: recorder = build_recorder(...)` block
  (:461), gated on the flag; then AFTER the build succeeds:
```python
        threading.Thread(target=_prompt_watcher, args=(prompt_arr, prompt_event),
                         name="vt-child-prompt", daemon=True).start()
        _safe_put(evt_q, ("prompt_mode", {"dynamic": _PROMPT_STATE["engine"] is not None}))
        if _PROMPT_STATE["engine"] is None:
            _prompt_degrade_log_once()
```
- cmd loop branch (alongside `elif kind == "arm":` etc.):
```python
                elif kind == "prompt":
                    if getattr(cfg.asr, "context_prompt", False):
                        _set_engine_prompt(str(payload.get("text", "")))
```
Host side: `_dispatch` branch + `self._prompt_mode: bool | None = None` in `__init__`; `set_prompt`:
```python
    def set_prompt(self, text: str) -> None:
        """Ship a rolling context prompt to the child (no-op when cfg.asr.context_prompt is False)."""
        if not getattr(self._cfg.asr, "context_prompt", False):
            return
        try:
            self._prompt_arr.value = text[: _PROMPT_ARR_LEN - 4]
            self._prompt_event.set()
        except Exception:
            logger.debug("set_prompt failed (child gone?); ignored", exc_info=True)
```
(needs `import ctypes` at module top — stdlib, daemon-pure OK.)

### Integration Points

```yaml
IPC:
  - add: "cmd_q kind 'prompt' {'text': str}; evt_q kind 'prompt_mode' {'dynamic': bool}"
  - transport: "spawn-ctx mp.Array(c_wchar, 2048) + prompt_event (mirror abort_event :142)"
API:
  - add: "RecorderHost.set_prompt(text) -> None  (consumed by P1.M2.T5.S2 daemon prompt computation)"
STATE:
  - add: "self._prompt_mode: bool | None (daemon-side, set by the prompt_mode dispatch)"
```

## Validation Loop

### Level 1–2 (style + unit — THE gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q        # all pass (existing + 6 new)
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # 0 failed
# Optional: /home/dustin/.local/bin/ruff check voice_typing/recorder_host.py tests/test_recorder_host.py
```

### Level 3 (mechanism probe — child-process reality, NO model load)

```bash
# A live end-to-end of the patch+Array mechanics WITHOUT CUDA: build a fake cfg, install the patch
# against a stub RealtimeSTT module… (covered by the unit tests) — PLUS a real-child smoke using a
# monkeypatched build_recorder is OUT OF SCOPE here (T8 does the integration asserts). The unit
# tests + the verified seam facts (research §2) are the gate for this task.
```

### Level 4 (scope guard)

```bash
git status --short   # == voice_typing/recorder_host.py + tests/test_recorder_host.py only
grep -n "import" voice_typing/recorder_host.py | head -5   # module top stays mp/threading/stdlib/ctypes
```

## Final Validation Checklist

- [ ] 6 new tests pass; whole fast suite 0 failed (both under `timeout`).
- [ ] Patch is installed BEFORE `build_recorder`; probe emits `prompt_mode` after ready; degrade logs once.
- [ ] `context_prompt=False`: no patch, no watcher, cmd ignored, `set_prompt` no-op (tested).
- [ ] Module top stays daemon-pure (lazy RealtimeSTT import only).
- [ ] Only the 2 files changed.

## Anti-Patterns to Avoid

- ❌ Don't ship cmd_q-only prompt delivery — the loop blocks in `text()`; the Array+Event side channel is the real transport (Critical #1).
- ❌ Don't import RealtimeSTT at module top (daemon purity) or in unit tests (Critical #2/#5).
- ❌ Don't let any patch/poke/degrade path raise into `_worker_main` (Critical #3).
- ❌ Don't use fork-ctx objects or module globals for daemon→child transport (spawn ctx, process args) (Critical #4).
- ❌ Don't touch daemon.py/config/T5.S2/T6 concerns (Critical #6). Don't run un-timed commands (Critical #5).

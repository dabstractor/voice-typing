# Research — P1.M1.T3.S2: construction-failure → CPU retry in main()

## 0. Status of the upstream contract (P1.M1.T3.S1) — LANDED

S1 was running in parallel and is now **implemented in the working tree (uncommitted)**.
Verified live:
- `voice_typing/daemon.py`:
  - `cfg_to_kwargs(cfg, *, resolved: dict[str,str] | None = None)` (line ~134) — `resolved` is the
    injection point; when given, `_resolve_device_config` is NOT called.
  - `_construct(cfg, feedback, recorder_cls, latency=None, force_cpu=False)` (line ~233) —
    `resolved = dict(cuda_check.CPU_FALLBACK) if force_cpu else None` then `cfg_to_kwargs(cfg, resolved=resolved)`.
  - `build_recorder(cfg, feedback, latency=None, force_cpu=False)` (line ~263) — threads
    `force_cpu=force_cpu` into `_construct`.
- `tests/test_daemon.py` lines ~1490-1590: the 6 S1 force_cpu tests exist and PASS
  (`.venv/bin/python -m pytest tests/test_daemon.py -k force_cpu` → 6 passed).

**CONCLUSION:** S2 can consume the SANCTIONED call documented in S1's Integration Points:
```python
rec = build_recorder(cfg, feedback, latency, force_cpu=True)   # CPU config, skips cuda_check
daemon = VoiceTypingDaemon(cfg, feedback, latency=latency, recorder=rec)
```
No change to `build_recorder` / `_construct` / `cfg_to_kwargs` / `cuda_check` is needed or wanted.

## 1. The exact construction site in main() (current, post-S1 line numbers)

`main()` is at daemon.py ~line 1075. The construction block (verified verbatim, lines ~1119-1124):
```python
        from voice_typing.feedback import Feedback

        daemon = VoiceTypingDaemon(cfg, Feedback(cfg.feedback))
        # quit path: ControlServer._dispatch("quit") -> ...
        server = ControlServer(daemon, on_quit=daemon.shutdown)
        restore = install_shutdown_signal_handlers(daemon)
        server.start()
        daemon.run()
    except Exception:
        logger.exception("fatal error during daemon lifecycle; exiting")
        return 1
    finally:
        ... (restore(); daemon.shutdown() if daemon is not None; server.stop())
```
- `daemon = None` / `server = None` / `restore = None` are initialised BEFORE the `try` (line ~1116).
- `VoiceTypingDaemon.__init__` calls `build_recorder(cfg, feedback, self._latency)` when `recorder is None`
  (line ~399) → that is where cuDNN loads. A missing `libcudnn_ops.so.9` raises HERE.
- The broad `except Exception` → `return 1`. systemd `Restart=on-failure` → crash-loop. This is the bug.

## 2. The device-reporting chain (why "say so in status" needs a cache seed)

Two daemon methods re-probe the CUDA DRIVER (which still sees the GPU after a cuDNN failure):
- `status_snapshot()` → `_resolved_device()` (line ~700) → on first call `_resolve_device_config(cfg)`
  → `cuda_check.resolve_device_and_models` → returns `cuda`. **Cached** in `self._resolved_device_cache`
  (set via `getattr`/setattr — documented as "Lazily cached via getattr (no __init__ edit)").
- `run()` → `_log_resolved_device()` (line ~467) → calls `_resolve_device_config(self._cfg)` **directly**
  (NOT via the cache) → logs `device=cuda`.

So after a CPU fallback, BOTH would report `cuda` — contradicting the fallback WARNING and violating
PRD §4.4 "say so in status". **Fix (sanctioned extension point):** main() seeds
`daemon._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)` after a successful CPU retry, AND
`_log_resolved_device` is refactored to read `self._resolved_device()` (the cache) so the startup log
and `status_snapshot` agree. `CPU_FALLBACK` keys (`device,compute_type,final_model,realtime_model`)
exactly match what `_resolved_device()` returns → safe.

This is exactly what S1's Integration Points deferred: "T3.S2 may need to make the daemon's
self-reported device reflect the actual built recorder; that's T3.S2's concern."

## 3. The latency-sharing invariant (why main() must create the LatencyLog)

`VoiceTypingDaemon.__init__` (line ~399): `self._latency = latency if latency is not None else LatencyLog()`
then `build_recorder(cfg, feedback, self._latency)`. The recorder's `on_vad_stop`/partial callbacks
are wired to the SAME `LatencyLog` that `on_final.finalize_utterance` reads.

For the retry path, main() builds the recorder ITSELF via `build_recorder(cfg, feedback, latency, force_cpu=True)`
then injects it via `recorder=`. To keep the callbacks and `finalize_utterance` on the SAME collector,
main() must create ONE `latency = LatencyLog()` and pass `latency=latency` to BOTH `build_recorder`
(retry) and `VoiceTypingDaemon` (both attempts). This is fully supported (`latency=` is an injectable
keyword-only param). On the normal path the first attempt's `VoiceTypingDaemon(cfg, feedback, latency=latency)`
uses the same shared latency.

## 4. The test seams (test_daemon.py) + the hermeticity problem

`_patch_main_lifecycle(monkeypatch, ...)` (line ~895) patches `daemon.VoiceTypingConfig`,
`daemon.VoiceTypingDaemon`, `daemon.ControlServer`, `daemon.install_shutdown_signal_handlers`,
`voice_typing.feedback.Feedback`, and `logging.basicConfig`. It does NOT patch
`daemon._resolve_device_config` or `daemon.build_recorder`.

`test_main_returns_one_on_daemon_construction_failure` (line ~979) uses `BoomDaemon` (raises in `__init__`).
**PROBLEM with the restructured main():** on a GPU machine `_resolve_device_config(cfg)` returns `cuda`
→ the retry branch calls the REAL `build_recorder(..., force_cpu=True)` → imports RealtimeSTT + loads CPU
Whisper models (seconds, spawns workers). The existing test is therefore no longer hermetic on a GPU host
(this dev machine HAS a GPU — PRD says `device: cuda`). **It MUST be updated** to monkeypatch
`_resolve_device_config` (→cuda, deterministic) and `build_recorder` (→fake recorder, no model load) so it
deterministically exercises "both attempts fail → return 1". The `assert daemon.main() == 1` assertion is
PRESERVED (semantics unchanged); only hermeticity monkeypatches are added. This is the correct fix — the
un-modified test would load real models on GPU hosts.

`_MainFakeDaemon.__init__(self, cfg, fb, **kw)` absorbs `latency=`/`recorder=` kwargs → normal-path
main() tests keep passing with `latency=latency` added (first attempt succeeds, retry branch never entered,
`_resolve_device_config` never called on the success path).

For the NEW success-fallback test we need a daemon that **raises on the 1st construction, succeeds on the
2nd** (stateful). Pattern: a small `_RaiseOnceDaemon` whose `__init__` raises when `len(self._seen) == 1`
and stores `recorder=`/`latency=` kwargs otherwise. Plus a `build_recorder` capture that records
`force_cpu` and returns a `_StubRecorder`.

## 5. Design decision: recorder= injection (S1 option 2), NOT force_cpu on __init__

The item CONTRACT offers two options; S1's PRP Integration Points + Gotcha #7 explicitly recommend
option 2 ("build a forced-CPU recorder via build_recorder(force_cpu=True) and inject it through the
EXISTING recorder= kwarg; No __init__ change is needed or wanted"). Choose option 2 because:
(a) S1 built `build_recorder(force_cpu=)` specifically for this; (b) it honours S1's "no __init__ change";
(c) the BoomDaemon test update is a hermeticity improvement (correct on GPU hosts), not a contract change.

## 6. README update sites (Mode A — README only)

- `README.md` "## CPU-only mode" (line ~146): currently "There are two ways". Add a #3
  construction-failure fallback paragraph (driver probe sees GPU but cuDNN load fails → one CPU retry,
  `journalctl` shows the WARNING + `daemon started in degraded CPU mode`, `voicectl status` reports
  `device: cpu (int8)`, no crash-loop).
- `README.md` "### cuDNN load error (`libcudnn_ops.so.9`)" (line ~166, under Troubleshooting): add a
  closing sentence that if cuDNN still can't load the daemon now degrades to CPU automatically instead of
  crash-looping; fix the lib path + restart to return to GPU.

## 7. Tooling

This project uses **pytest** (NO ruff/mypy in pyproject — `pyproject.toml` has only
`[dependency-groups] dev=["pytest>=9.1.1"]`). Validation = `py_compile` + `pytest`. Invoke
`.venv/bin/python` and `.venv/bin/python -m pytest` explicitly (this machine aliases python3→uv run,
pip→alias; bare python/pytest/uv are unsafe).

## 8. Parallel/sibling awareness (scope boundaries)

- S1 (force_cpu capability) — LANDED. S2 CONSUMES it; does NOT re-edit `build_recorder`/`_construct`/
  `cfg_to_kwargs`/`cuda_check.py`.
- P1.M3.T1.S1 (README changeset doc) is PLANNED (not started). S2's README edits are the Mode A
  "document this specific behavior" edits scoped to this item; they do not conflict with a later
  full-changeset README sync (additive paragraphs).
- `_resolve_device_config` and `cuda_check.py` stay byte-identical (S1's negative constraint carries over).

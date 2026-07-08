# Research: polluting-tests root cause + monkeypatch fix (P1.M2.T1.S1)

Target: `tests/test_daemon.py` — fix 4 tests that call the REAL
`cuda_check.resolve_device_and_models()` without monkeypatching, polluting
`sys.modules` with `ctranslate2`/`torch` and breaking the order-dependent
`tests/test_voicectl.py::test_ctl_module_present_and_imports_pure`.

This is bugfix **Issue 4** (Minor). Option (a) of the suggested fix: make the
polluting tests monkeypatch the resolver (root-cause fix). The sibling subtask
P1.M2.T1.S2 takes option (b): harden the purity test (defense-in-depth). Both
are complementary; THIS task does NOT touch `test_voicectl.py`.

---

## 1. The defect (verified + reproduced)

`pytest tests/ --ignore=tests/test_feed_audio.py` (the documented fast sweep) is
**order-dependent**. pytest collects files alphabetically, so `test_daemon.py`
runs BEFORE `test_voicectl.py`. `test_ctl_module_present_and_imports_pure`
(test_voicectl.py:200-203) asserts a GLOBAL invariant:

```python
def test_ctl_module_present_and_imports_pure():
    assert importlib.util.find_spec("voice_typing.ctl") is not None
    assert not [m for m in ("RealtimeSTT", "torch", "ctranslate2") if m in sys.modules]
```

This is a global `sys.modules` assertion — it fails if ANY earlier test imported
`ctranslate2`/`torch`. Minimal reproduction (proven live):

```
.venv/bin/python -m pytest \
  "tests/test_daemon.py::test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set" \
  "tests/test_voicectl.py::test_ctl_module_present_and_imports_pure" -q
# => FAILED ... AssertionError: assert not ['torch', 'ctranslate2']
# Running test_voicectl.py alone (or first) PASSES.
```

## 2. Root-cause chain (exact code paths; line numbers as of current tree)

The real resolver `cuda_check.resolve_device_and_models()` imports `ctranslate2`
(which imports `torch`) to probe the CUDA driver. Two call sites in `daemon.py`
reach it WITHOUT a monkeypatch in the 4 polluting tests:

**(A) `cfg_to_kwargs` path** — `daemon.cfg_to_kwargs(cfg)` (daemon.py:134)
calls `_resolve_device_config(cfg)` (daemon.py:117-131) which calls
`cuda_check.resolve_device_and_models(defaults)` (daemon.py:131). Reached by:
- `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` (test_daemon.py:98)
  — signature `def ...(cfg):` (NO `monkeypatch`), body's first line is
  `kw = daemon.cfg_to_kwargs(cfg)` with no `_cuda_resolve` call.

**(B) `run()` path** — `daemon.run()` (daemon.py:438) calls
`_log_resolved_device()` (daemon.py:467), which reads `self._resolved_device()`
(the cache) — lazily populated by `_resolve_device_config(self._cfg)` → the real
resolver. Reached by the three run-loop tests, each `def ...():` (NO
`monkeypatch`) that threads `d.run()`:
- `test_run_loop_not_listening_does_not_call_text` (test_daemon.py:537)
- `test_run_loop_calls_text_when_listening_then_exits_on_shutdown` (test_daemon.py:549)
- `test_run_sets_uptime_after_start` (test_daemon.py:563)

NOTE on construction: `_make_daemon()` (test_daemon.py:411) injects a
`_StubRecorder` + `_ok_probe` mic prober, so `VoiceTypingDaemon.__init__` does
NOT call cuda_check (it skips `build_recorder`). So construction is CLEAN; the
pollution is purely from (A) `cfg_to_kwargs` and (B) `run()`.

NOTE on T3.S2: the current `daemon.py` already reflects T3.S2 (`_log_resolved_device`
reads `self._resolved_device()` at line 471; `main()` has the cuda-retry at
line 1144). This does NOT change the fix: `_resolved_device()` STILL calls
`_resolve_device_config` → `cuda_check.resolve_device_and_models` on its first
(cache-miss) call. So the run-loop tests still pollute via (B); the fix is the
same.

## 3. The fix (proven mechanism)

The file already has a helper that does EXACTLY the right monkeypatch —
`_cuda_resolve(monkeypatch, mapping)` (test_daemon.py:66-91):

```python
def _cuda_resolve(monkeypatch, mapping):
    is_fallback = mapping is daemon.cuda_check.CPU_FALLBACK
    def _resolve(defaults=None):
        if is_fallback:
            return dict(mapping)
        return dict(defaults) if defaults is not None else dict(mapping)
    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)
```

It patches `daemon.cuda_check.resolve_device_and_models` — the exact attribute
`_resolve_device_config` calls (daemon.py:131). The cuda-path closure echoes
`dict(defaults)` (the cfg-derived values), faithfully emulating the real
function's cuda branch so cfg-derived values still flow through.

**The hermetic siblings already use it** (test_daemon.py:113-165): every other
`test_cfg_to_kwargs_*` test starts with
`_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)`. And the correctly
hermetic run-loop sibling `test_run_logs_resolved_device_at_startup`
(test_daemon.py:701) does the equivalent (`monkeypatch.setattr(daemon.cuda_check,
"resolve_device_and_models", ...)` at the top of its body, before `d.run()`).

**Mechanism proof (live, no codebase edit):** with
`daemon.cuda_check.resolve_device_and_models` replaced by the same closure,
calling `daemon.cfg_to_kwargs(cfg)` AND `daemon._resolve_device_config(cfg)`
leaves `sys.modules` free of `RealtimeSTT`/`torch`/`ctranslate2`. Confirmed:
`after cfg_to_kwargs with resolver monkeypatched -> polluted: []`.

**The fix for each of the 4 tests:** add a `monkeypatch` parameter to the
signature and call `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)`
as the first line of the body — mirroring the hermetic siblings. pytest
auto-restores the monkeypatch at teardown, so it is hermetic and order-safe.

For the run-loop tests, the monkeypatch must be in place BEFORE `d.run()` is
threaded (so `_log_resolved_device()`'s first/cache-miss resolve uses the stub).
Putting it at the top of the body (before `_make_daemon()`) satisfies this and
mirrors `test_run_logs_resolved_device_at_startup`.

## 4. Scope boundaries (do NOT cross)

- **Do NOT touch `test_voicectl.py`** — that is P1.M2.T1.S2's job (option (b):
  harden the purity test to snapshot sys.modules before/after the import). This
  task is option (a): fix the polluters at the root cause. Complementary, not
  overlapping.
- **Do NOT touch the `test_main_returns_one_on_daemon_construction_failure`
  test** (test_daemon.py ~979) or any main()-lifecycle test — T3.S2 owns those
  (its PART A makes the BoomDaemon test hermetic by monkeypatching
  `daemon._resolve_device_config` + `daemon.build_recorder`). The 4 targets here
  are DISTINCT tests (cfg_to_kwargs + run-loop). No overlap.
- **Do NOT modify `daemon.py`, `cuda_check.py`, or any source.** This is a
  test-only change.
- **Do NOT add new tests / fixtures / imports.** The 4 edits reuse the existing
  `_cuda_resolve` helper and the builtin `monkeypatch` fixture, both already in
  the file. Pure signature + 1-line-body additions.

## 5. Validation strategy

1. **Static:** grep the 4 tests → each now has `monkeypatch` in its signature
   and a `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)` first
   line.
2. **Minimal order-trigger (the bug):** run the polluting test then the purity
   test in one session → MUST pass (currently fails with `['torch',
   'ctranslate2']`).
3. **Full fast suite:** `pytest tests/ --ignore=tests/test_feed_audio.py` →
   **0 failed**. Current count is **246 collected** (NOT 211 — the item
   description's "211/211" predates T3.S2/other additions; assert by
   pass/fail, not a hard count).
4. **No pollution guard:** a targeted run of `tests/test_daemon.py` followed by
   an in-process `ctranslate2 not in sys.modules` check (the purity test itself
   is this guard when run in alphabetical order).
5. **No regression:** the 4 tests' own assertions are unchanged (key-set check,
   text-call counts, uptime) — only the resolver is stubbed, which returns the
   same cfg-derived values.

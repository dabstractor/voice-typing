# PRP — P1.M1.T2.S1: cuda_check single-model contract

## Goal

**Feature Goal**: Collapse `voice_typing/cuda_check.py` to the Rev 2 **single-model contract**: `resolve_device_and_models()` returns exactly `{device, compute_type, model}` — CUDA: `{cuda, float16, 'small.en'}` (the cfg `lite_model` default); CPU fallback: `{cpu, int8, 'tiny.en'}` (the existing lite fallback logic). The old 4-key dict (`final_model` + `realtime_model`) is **removed**. Update `CUDA_DEFAULTS`/`CPU_FALLBACK`, the module docstring, and `_main()`'s user-facing VERDICT/resolved print; update the tests that pin the old dict shape (the test_config parity test + two test_daemon CPU_FALLBACK sites); add a new dedicated `tests/test_cuda_check.py` (none exists today).

**Deliverable** (three files edited + one new):
1. `voice_typing/cuda_check.py` — 3-key `CUDA_DEFAULTS`/`CPU_FALLBACK`; `resolve_device_and_models()` → 3 keys; module docstring + `_main()` print rewritten (Mode A).
2. `tests/test_cuda_check.py` — **NEW** (~8 hermetic tests, monkeypatched — no real CUDA probe).
3. `tests/test_config.py` — `test_defaults_match_cuda_check` re-pinned to `lite_model` + the 3-key shape.
4. `tests/test_daemon.py` — the two CPU_FALLBACK-mapping sites updated to the end-state 3-key expectations.

**Success Definition** (the TRANSIENT contract — read carefully):
- (a) `set(cuda_check.CUDA_DEFAULTS) == {"device", "compute_type", "model"}`; values `cuda/float16/small.en`. `CPU_FALLBACK` → `cpu/int8/tiny.en`.
- (b) `resolve_device_and_models()` never mentions `final_model`/`realtime_model`; CUDA → `dict(defaults or CUDA_DEFAULTS)`, CPU → `dict(CPU_FALLBACK)` (semantics unchanged, shape 3-key, always a fresh dict).
- (c) `_main()` prints `# resolved: device=.. compute_type=.. model=..` (no `final_model=`/`realtime_model=` anywhere in its output).
- (d) **The focused gate is green**: `timeout 600 .venv/bin/python -m pytest tests/test_cuda_check.py -q` (new, all pass) AND `timeout 600 .venv/bin/python -m pytest tests/test_config.py -k 'defaults or cuda' -q` (all pass).
- (e) **The broader suite is EXPECTED RED until P1.M1.T2.S2 lands** — `daemon.py` (`_resolve_device_config`/`cfg_to_kwargs` still read `resolved["final_model"]` → KeyError), `recorder_host.py` ready payload, `ctl.py` status all reference removed keys. This is the **intended transient**; DO NOT paper over it (no shim keys, no compat aliases, no daemon edits). T2.S2 rewrites the consumers; the updated test_daemon expectations go green then.
- (f) `git diff --name-only` ⊆ `{voice_typing/cuda_check.py, tests/test_cuda_check.py (new), tests/test_config.py, tests/test_daemon.py}`.

## User Persona

**Target User**: The maintainer running `python -m voice_typing.cuda_check` (the install.sh CUDA smoke; the printed VERDICT + resolved line is the user-facing degraded-mode signal), and the downstream consumers (T2.S2's daemon/recorder_host/ctl rewrite) that consume the 3-key dict.

**Use Case**: install.sh runs the smoke check; the user sees `VERDICT=cuda-ok` + `resolved: device=cuda compute_type=float16 model=small.en` (or the cpu/tiny.en degraded line). T2.S2's `daemon._resolve_device_config` builds cfg-derived `{device, compute_type, model: cfg.asr.lite_model}` defaults and feeds `resolve_device_and_models()`.

**Pain Points Addressed**: Removes the dead two-model resolution substrate of the Rev 1 dual-mode design; gives Rev 2's single-mode (small.en both partials+finals; tiny.en on CPU) one authoritative resolver + a dedicated test file (none existed — coverage was incidental in test_daemon/test_config).

## Why

- **Rev 2 single-mode collapse (PRD §4.2ter/§4.2quater):** the project now runs ONE model (the small model) for both realtime partials and finals; `distil-large-v3` never loads. T1.S1 already removed `final_model`/`realtime_model` from `AsrConfig` (`lite_model` is the only model field). cuda_check's 4-key dict is the last substrate piece pinning the two-model shape; this subtask collapses it to `{device, compute_type, model}` so T2.S2 can rewrite the consumers against the end-state contract in one pass.
- **Sequenced, not atomic:** the plan deliberately splits the collapse — T2.S1 (this) lands the resolver + its tests; T2.S2 rewrites `daemon.py`/`recorder_host.py`/`ctl.py`. Between the two, the consumers reference removed keys (KeyError at the `resolved[...]` reads). That red window is **intended**: fixing it here would mean editing daemon.py (T2.S2's file) or leaving compat keys (which would defeat the collapse). The contract is explicit: *"do not paper over it; keep THIS subtask's own tests green."*
- **Closes the dedicated-test gap:** substrate_map §3 notes "No tests/test_cuda_check.py exists" — the module's coverage was incidental (test_daemon's CPU_FALLBACK asserts + the test_config parity pin). A new hermetic test file pins the 3-key contract, the fallback-wins-over-defaults rule, the fresh-dict rule, and the `_main()` output shape — none of which need a real GPU (monkeypatch `is_cuda_available`).
- **Scope discipline:** T2.S1 owns ONLY `cuda_check.py` + its new test + the 2 cited stale test sites. It does NOT touch `daemon.py`/`recorder_host.py`/`ctl.py` (T2.S2), `ctl` command surface (T2.S3), `prefetch.py` CORE_REPOS / hypr-binds / ACCEPTANCE (T2.S4), or config schema (T1.S1).

## What

Rewrite cuda_check's model resolution to 3 keys; re-pin the stale tests; add `tests/test_cuda_check.py`.

### The new contract (exact)

```python
CUDA_DEFAULTS: dict[str, str] = {
    "device": "cuda",
    "compute_type": "float16",
    "model": "small.en",   # the single model (Rev 2 §4.2ter/§4.2quater): partials + finals
}
CPU_FALLBACK: dict[str, str] = {
    "device": "cpu",
    "compute_type": "int8",
    "model": "tiny.en",    # the approved CPU substitute (small.en -> tiny.en)
}
# resolve_device_and_models(defaults=None) -> dict[str, str]:
#   cuda available -> dict(defaults or CUDA_DEFAULTS); else dict(CPU_FALLBACK) regardless of defaults.
```

### Success Criteria

- [ ] `CUDA_DEFAULTS`/`CPU_FALLBACK` are exactly 3 keys; values per above; `final_model`/`realtime_model` absent from cuda_check.py entirely.
- [ ] `resolve_device_and_models()` docstring + module docstring describe the single-model contract (Mode A).
- [ ] `_main()`'s resolved line + its docstring's output-list show `model=` only; exit codes unchanged (0=cuda-ok, 1=cpu-fallback-required).
- [ ] `tests/test_cuda_check.py` exists, ~8 tests, all hermetic (monkeypatched probes — zero real ctranslate2/torch loads), all pass.
- [ ] `timeout 600 .venv/bin/python -m pytest tests/test_config.py -k 'defaults or cuda' -q` → all pass (parity test re-pinned).
- [ ] The two test_daemon sites (~2740-2747, ~2813-2849) updated to the 3-key end-state expectations (red-transient until T2.S2 — documented in a comment).
- [ ] NO edits to daemon.py / recorder_host.py / ctl.py / prefetch.py / config.py / config.toml.
- [ ] Broader suite (test_daemon etc.) acknowledged RED-transient; not fixed here.

## All Needed Context

### Context Completeness Check

_Pass._ The verbatim current cuda_check.py (all 168 lines read), the exact stale test sites with line numbers, T1.S1's schema contract (`lite_model` is the only model field; its interim parity-test edit which this subtask supersedes), the T1.S1/T2.S2 split of the ~14 cuda_check key references, and the no-dedicated-test-file fact are all verified below. An agent new to this repo can implement from this PRP alone. All gates are hermetic/fast except the optional live CLI smoke.

### Documentation & References

```yaml
# THE SOURCE MAP (line-verified) — what exists today
- docfile: plan/007_cfc245548aec/architecture/substrate_map.md
  why: §3 maps cuda_check.py exactly: CUDA_DEFAULTS:46-52 (4 keys), CPU_FALLBACK:54-59 (4 keys),
       resolve_device_and_models:114-130 (returns the 4-key dict), _main():135-165 (VERDICT print names
       the models), and — load-bearing — "No tests/test_cuda_check.py exists; coverage lives in
       tests/test_daemon.py (e.g. lines 2747, 2813-2849) and tests/test_config.py:66-77".
  critical: "The contract's exact stale-test line cites come from here. Also §3's note that consumers
            daemon.py:144-197 + recorder_host.py:681-714 + ctl.py status are T2.S2's rewrite."

# THE SCHEMA INPUT (T1.S1 — Implementing; treat as the contract)
- docfile: plan/007_cfc245548aec/P1M1T1S1/PRP.md
  why: Defines the end-state schema: AsrConfig DROPS final_model/realtime_model (lite_model is the ONLY
       model field); lite_post 0.5->0.8; +context_prompt/streaming/cancel. Its PRP explicitly leaves
       downstream suites red until P1.M1.T2 (same transient philosophy) and says of the parity test:
       "drop only the final_model/realtime_model asserts (keep device)" — an INTERIM state that THIS
       subtask supersedes (we re-pin to lite_model + the 3-key shape).
  critical: "Whether T1.S1 has landed or not, the END-STATE parity test is the same (lite_model exists in
            both states). If T1.S1 hasn't landed, ALSO expect test_config's other final/realtime asserts —
            NOT yours to fix (T1.S1 owns them); the -k 'defaults or cuda' gate covers the parity test."

# THE FILE UNDER EDIT (verbatim current state)
- file: voice_typing/cuda_check.py
  why: 168 lines. CUDA_DEFAULTS @45-50; CPU_FALLBACK @53-58; _cuda_device_count @61-82 (wrapped import +
        call — UNCHANGED); is_cuda_available @105-111 (UNCHANGED); resolve_device_and_models @114-131;
        _main() @138-164 (the resolved print @160-163 reads cfg['final_model']/cfg['realtime_model'] —
        would KeyError on the 3-key dict, so it MUST be updated in the same edit).
  pattern: "Keep the probe machinery (_cuda_device_count/_ctranslate2_version/_torch_cuda_available/
            is_cuda_available/_verdict) byte-identical — only the MODEL contract changes. The lazy
            ctranslate2 import stays inside _cuda_device_count (import purity)."
  gotcha: "_main() reads cfg['final_model'] — updating the dicts WITHOUT updating _main() breaks the CLI
          with KeyError. Same for the docstrings' output-line list. All in ONE edit."

# THE STALE TESTS TO RE-PIN (verbatim sites)
- file: tests/test_config.py
  why: test_defaults_match_cuda_check @66-78: asserts AsrConfig().final_model == CUDA_DEFAULTS["final_model"],
        realtime_model likewise, device likewise. T1.S1 (if landed) kept only the device assert. END STATE
        (this subtask): pin set(CUDA_DEFAULTS)==3 keys + lite_model==CUDA_DEFAULTS["model"] + device +
        CPU_FALLBACK["model"]=="tiny.en".
  pattern: "Keep the test name + drift-guard docstring intent; change the asserts to the single-model pin."
- file: tests/test_daemon.py
  why: Two sites pin the OLD dict shape THROUGH daemon (which T2.S2 rewrites):
        (1) test_construct_force_cpu_uses_cpu_fallback @~2740-2747 — asserts kw["model"]=="small.en",
            kw["realtime_model_type"]=="tiny.en" (the two-model CPU mapping). END STATE: both slots
            "tiny.en" (single model feeds model= AND realtime_model_type= after T2.S2).
        (2) The resolved-injection site @~2813-2820 (cfg_to_kwargs with resolved={...final_model:
            "small.en", realtime_model:"tiny.en"}) + test_log_resolved_device_reads_cache_after_cpu_
            fallback @~2837-2849 (seeds dict(daemon.cuda_check.CPU_FALLBACK); asserts final_model=small.en
            in the line). END STATE: 3-key resolved dicts; "model=tiny.en" in the log line.
  pattern: "Update the EXPECTATIONS to the end-state contract; add a one-line comment at each site:
            'single-mode collapse (P1.M1.T2.S1): red-transient until P1.M1.T2.S2 rewires cfg_to_kwargs/
            _log_resolved_device — DO NOT shim.' These tests go green when T2.S2 lands."
  critical: "You CANNOT make these green now (daemon.cfg_to_kwargs reads resolved['final_model'] ->
            KeyError). That is the documented transient. Do not edit daemon.py to 'fix' the test."

# THE PARALLEL ITEM (no-conflict boundary)
- docfile: plan/007_cfc245548aec/P1M1T1S2/PRP.md
  why: T1.S2 (parallel) adds the evdev dependency — pyproject.toml + uv.lock ONLY. Zero overlap with
        cuda_check.py/tests. T1.S1 (schema) touches test_config.py's OTHER tests (defaults/types/guards)
        — adjacent file, disjoint tests; coordinate via the -k 'defaults or cuda' gate being green at YOUR
        end regardless of T1.S1's landing order (lite_model/device exist in both schema states).
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/cuda_check.py       # 168 lines, 4-key dicts. ← EDIT (the core deliverable)
tests/test_config.py             # test_defaults_match_cuda_check @66-78. ← EDIT (re-pin)
tests/test_daemon.py             # ~2740-2747 + ~2813-2849 CPU_FALLBACK sites. ← EDIT (end-state; red-transient)
tests/test_cuda_check.py         # ← CREATE (~8 hermetic tests; none exists today)
# UNTOUCHED: daemon.py/recorder_host.py/ctl.py (T2.S2), ctl surface (T2.S3), prefetch/binds/ACCEPTANCE (T2.S4),
#            config.py/config.toml (T1.S1), pyproject/uv.lock (T1.S2).
```

### Desired Codebase tree with files to be added/changed

```bash
voice_typing/cuda_check.py       # MODIFY: 3-key CUDA_DEFAULTS/CPU_FALLBACK + resolve + docstrings + _main print.
tests/test_cuda_check.py         # NEW: ~8 hermetic tests (monkeypatched is_cuda_available/_cuda_device_count).
tests/test_config.py             # MODIFY: parity test → lite_model + 3-key shape + CPU tiny.en pin.
tests/test_daemon.py             # MODIFY: 2 sites → end-state expectations + red-transient comments.
# No new deps; no daemon/recorder_host/ctl/config/prefetch edits.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE TRANSIENT IS THE CONTRACT. After this subtask, daemon.cfg_to_kwargs /
# _log_resolved_device / recorder_host ready payload / ctl status read removed keys -> KeyError ->
# test_daemon/test_recorder_host/test_control_socket/test_voicectl (parts) go RED. That is INTENDED
# until P1.M1.T2.S2. Do NOT: add final_model/realtime_model back as aliases, edit daemon.py, or
# delete the broken consumer tests. The ONLY green gates are the focused ones (Success d).

# CRITICAL #2 — _main() AND THE DICTS MUST MOVE IN ONE EDIT. _main() @160-163 reads
# cfg['final_model']/cfg['realtime_model'] — updating only the dicts KeyErrors the CLI (install.sh's
# smoke step). Update dicts + resolve docstring + module docstring + _main() print + _main() docstring
# output-list atomically. Grep gate: `grep -c 'final_model\|realtime_model' voice_typing/cuda_check.py` == 0.

# CRITICAL #3 — KEEP THE PROBE MACHINERY IDENTICAL. _cuda_device_count (wrapped import + call, any
# failure -> 0), _ctranslate2_version, _torch_cuda_available (diagnostics-only), is_cuda_available,
# _verdict, exit codes (0=cuda-ok / 1=cpu-fallback-required), and the LD_LIBRARY_PATH docstring warning
# are UNCHANGED. Only the model contract (the dicts + their docstrings + the resolved print) changes.

# CRITICAL #4 — CPU FALLBACK WINS OVER defaults (unchanged semantics). resolve() returns
# dict(CPU_FALLBACK) REGARDLESS of the caller's defaults when no CUDA — test_daemon's force_cpu path and
# T2.S2 rely on this. Only the SHAPE changes. Pin it in the new test file (monkeypatch is_cuda_available
# -> False; pass custom 3-key defaults; assert == CPU_FALLBACK).

# CRITICAL #5 — NEW TESTS MUST BE HERMETIC. Monkeypatch cuda_check.is_cuda_available (and
# _cuda_device_count/_torch_cuda_available for the _main tests) — NEVER trigger a real ctranslate2 import
# in the fast suite (AGENTS.md: heavy CUDA loads are minutes; the codebase keeps unit tests CUDA-free).
# Use capsys for the _main output-shape tests; assert 'final_model=' NOT in stdout.

# CRITICAL #6 — THE PARITY TEST WORKS IN BOTH T1.S1 STATES. If T1.S1 has landed, AsrConfig has no
# final_model; if not, it does. Your re-pinned test only references lite_model + device (+ CPU_FALLBACK
# pin) — both exist in either state. Do NOT touch T1.S1's other test_config edits (defaults/types/guards);
# your gate is `-k 'defaults or cuda'`, and test_defaults_match_prd_4_5 is T1.S1's to fix (it stays green
# in whichever state T1.S1 left it — verify, don't edit).

# GOTCHA #7 — FULL PATHS + TIMEOUTS. Machine aliases python3->uv run; AGENTS.md requires an inner
# timeout on every non-trivial command: `timeout 600 .venv/bin/python -m pytest ...`. The optional live
# CLI smoke: `timeout 30 .venv/bin/python -m voice_typing.cuda_check` (device-count probe is driver-only;
# runs without the launch wrapper — exit 1 on cpu is VALID, use `|| true` under set -e).

# GOTCHA #8 — NO DEDICATED TEST FILE EXISTS TODAY. Create tests/test_cuda_check.py (substrate_map §3).
# Follow the repo's test-file style: module docstring with the Run: command, `from voice_typing import
# cuda_check`, plain functions, pytest.raises where needed. Name: test_cuda_check.py (matches module).
```

## Implementation Blueprint

### Data models and structure

The only "model" is the 3-key `dict[str, str]` contract (`{device, compute_type, model}`) — CUDA_DEFAULTS / CPU_FALLBACK / resolve's return. No ORM/pydantic; no config schema change (T1.S1 owns that).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/cuda_check.py — the single-model contract (ONE atomic edit)
  - REPLACE CUDA_DEFAULTS (@45-50):
        # PRD §4.4/§4.2ter (Rev 2 single-mode) — the config the daemon WANTS when CUDA works.
        # ONE model (the small model) serves BOTH realtime partials and final transcription.
        CUDA_DEFAULTS: dict[str, str] = {
            "device": "cuda",
            "compute_type": "float16",
            "model": "small.en",
        }
  - REPLACE CPU_FALLBACK (@53-58):
        # PRD §4.4 — the degraded config applied when ctranslate2 sees no CUDA device.
        # The approved CPU substitute for the single small model is tiny.en.
        CPU_FALLBACK: dict[str, str] = {
            "device": "cpu",
            "compute_type": "int8",
            "model": "tiny.en",
        }
  - REWRITE the module docstring's model language (Mode A): cuda path = device="cuda",
    compute_type="float16", model="small.en" (the single model — partials AND finals, §4.2ter/§4.2quater);
    CPU fallback = device="cpu", compute_type="int8", model="tiny.en". Update the DEGRADED-MODE KNOB
    block + the P1.M4.T1.S1 mapping note to: "maps model -> model= AND realtime_model_type= (single
    model, both slots)". KEEP: the LD_LIBRARY_PATH/launch_daemon.sh warning, the ctranslate2-must-have/
    torch-nice-to-have text, and the cuDNN LIMITATION paragraph verbatim.
  - UPDATE resolve_device_and_models (@114-131): docstring → "Resolve {device, compute_type, model} —
    the SINGLE model (Rev 2 §4.2ter) used for both realtime partials and finals. If ctranslate2 CUDA is
    available, return a copy of `defaults` (or CUDA_DEFAULTS when None). Otherwise apply the PRD §4.4
    CPU fallback (CPU_FALLBACK) REGARDLESS of `defaults`. Always a fresh dict the caller may mutate."
    BODY UNCHANGED (the dict(defaults-or-CUDA_DEFAULTS)/dict(CPU_FALLBACK) logic already fits 3 keys).
  - UPDATE _main() (@138-164): docstring output-list line → "# resolved: device=.. compute_type=..
    model=.."; the print (@160-163) → f"# resolved: device={cfg['device']} compute_type=
    {cfg['compute_type']} model={cfg['model']}". Exit codes + all other prints UNCHANGED.
  - GATE: grep -c 'final_model\|realtime_model' voice_typing/cuda_check.py  → 0.

Task 2: CREATE tests/test_cuda_check.py — ~8 hermetic tests (the new dedicated file)
  - HEADER (repo style): docstring citing P1.M1.T2.S1 + the single-model contract + "Run: timeout 600
    .venv/bin/python -m pytest tests/test_cuda_check.py -q". Imports: pytest, from voice_typing import
    cuda_check.
  - TESTS (copy-ready shapes; all hermetic via monkeypatch):
        def test_cuda_defaults_is_three_key_single_model():
            assert set(cuda_check.CUDA_DEFAULTS) == {"device", "compute_type", "model"}
            assert cuda_check.CUDA_DEFAULTS == {"device": "cuda", "compute_type": "float16", "model": "small.en"}

        def test_cpu_fallback_is_three_key_single_model():
            assert set(cuda_check.CPU_FALLBACK) == {"device", "compute_type", "model"}
            assert cuda_check.CPU_FALLBACK == {"device": "cpu", "compute_type": "int8", "model": "tiny.en"}

        def test_resolve_cuda_returns_fresh_copy_of_defaults(monkeypatch):
            monkeypatch.setattr(cuda_check, "is_cuda_available", lambda: True)
            r = cuda_check.resolve_device_and_models()
            assert r == cuda_check.CUDA_DEFAULTS and r is not cuda_check.CUDA_DEFAULTS
            r["model"] = "mutated"   # caller may mutate freely
            assert cuda_check.CUDA_DEFAULTS["model"] == "small.en"

        def test_resolve_cpu_returns_fallback_regardless_of_defaults(monkeypatch):
            monkeypatch.setattr(cuda_check, "is_cuda_available", lambda: False)
            custom = {"device": "cuda", "compute_type": "float16", "model": "base.en"}
            assert cuda_check.resolve_device_and_models(custom) == cuda_check.CPU_FALLBACK
            assert cuda_check.resolve_device_and_models() == cuda_check.CPU_FALLBACK

        def test_resolve_custom_defaults_pass_through_on_cuda(monkeypatch):
            monkeypatch.setattr(cuda_check, "is_cuda_available", lambda: True)
            custom = {"device": "cuda", "compute_type": "float16", "model": "base.en"}
            assert cuda_check.resolve_device_and_models(custom) == custom

        def test_main_cuda_prints_verdict_and_single_model_line(monkeypatch, capsys):
            monkeypatch.setattr(cuda_check, "_cuda_device_count", lambda: (1, "1 cuda device(s) visible to ctranslate2"))
            monkeypatch.setattr(cuda_check, "_torch_cuda_available", lambda: True)
            monkeypatch.setattr(cuda_check, "_ctranslate2_version", lambda: "4.x-test")
            rc = cuda_check._main()
            out = capsys.readouterr().out
            assert rc == 0
            assert "ctranslate2_version=4.x-test" in out and "cuda_device_count=1" in out
            assert "VERDICT=cuda-ok" in out
            assert "resolved: device=cuda compute_type=float16 model=small.en" in out
            assert "final_model" not in out and "realtime_model" not in out   # the collapse

        def test_main_cpu_verdict_exit_1_and_tiny_en(monkeypatch, capsys):
            monkeypatch.setattr(cuda_check, "_cuda_device_count", lambda: (0, "no CUDA-capable device/driver visible to ctranslate2"))
            monkeypatch.setattr(cuda_check, "_torch_cuda_available", lambda: False)
            rc = cuda_check._main()
            out = capsys.readouterr().out
            assert rc == 1
            assert "VERDICT=cpu-fallback-required" in out
            assert "resolved: device=cpu compute_type=int8 model=tiny.en" in out

        def test_module_import_stays_cuda_free():
            import subprocess, sys   # hermetic: a fresh interpreter never loads ctranslate2
            code = "import sys, voice_typing.cuda_check; sys.exit(0 if 'ctranslate2' not in sys.modules else 1)"
            subprocess.run([sys.executable, "-c", code], check=True)
  - CONSTRAINTS: monkeypatch the PROBES (is_cuda_available/_cuda_device_count/_torch_cuda_available/
    _ctranslate2_version) — never the functions under test; capsys for output; no real CUDA/torch import
    in-process (CRITICAL #5).

Task 3: EDIT tests/test_config.py — re-pin test_defaults_match_cuda_check (@66-78)
  - REPLACE the body (works whether or not T1.S1's interim edit landed):
        def test_defaults_match_cuda_check():
            """Drift guard: the asr single-model/device defaults must equal cuda_check.CUDA_DEFAULTS.

            Single-model contract (Rev 2 / P1.M1.T2.S1): cuda_check resolves exactly
            {device, compute_type, model}; config's lite_model is THE model and must equal
            CUDA_DEFAULTS["model"]; the CPU substitute is tiny.en.
            """
            from voice_typing.cuda_check import CPU_FALLBACK, CUDA_DEFAULTS

            assert set(CUDA_DEFAULTS) == {"device", "compute_type", "model"}
            assert AsrConfig().lite_model == CUDA_DEFAULTS["model"]
            assert AsrConfig().device == CUDA_DEFAULTS["device"]
            assert CPU_FALLBACK["model"] == "tiny.en"   # the approved CPU substitute
  - DO NOT touch T1.S1's other test_config edits (defaults/types/guards) — verify `-k 'defaults or cuda'`
    is green; if test_defaults_match_prd_4_5 references removed fields (T1.S1 not yet landed... it won't —
    it lands first), leave it to T1.S1 (CRITICAL #6).

Task 4: EDIT tests/test_daemon.py — the two CPU_FALLBACK sites → end-state expectations (red-transient)
  - SITE 1 test_construct_force_cpu_uses_cpu_fallback (@~2740-2747): keep the device/compute_type
    asserts; change the model asserts to the single-model mapping:
        assert kw["model"] == "tiny.en"
        assert kw["realtime_model_type"] == "tiny.en"   # single model fills BOTH slots (P1.M1.T2.S2)
    Add the comment: "# P1.M1.T2.S1 single-mode collapse: RED-TRANSIENT until P1.M1.T2.S2 rewires
    #  cfg_to_kwargs to map resolved['model'] to both model= and realtime_model_type=. Do NOT shim."
  - SITE 2 (@~2813-2820): the injected resolved dict becomes 3-key:
        kw = daemon.cfg_to_kwargs(
            cfg, resolved={"device": "cpu", "compute_type": "int8", "model": "tiny.en"}
        )
        assert kw["device"] == "cpu" and kw["model"] == "tiny.en"
        assert kw["realtime_model_type"] == "tiny.en" and kw["compute_type"] == "int8"
  - SITE 2b test_log_resolved_device_reads_cache_after_cpu_fallback (@~2837-2849): keep the seed
    (`dict(daemon.cuda_check.CPU_FALLBACK)` — now 3-key); change the last assert to
    `assert "model=tiny.en" in line` (drop final_model=/realtime_model= asserts). Same red-transient comment.
  - EXPECTED: these stay RED (KeyError at daemon's resolved['final_model'] reads) until T2.S2 — that is
    the documented transient (CRITICAL #1). Do NOT edit daemon.py.

Task 5: VALIDATE — run the Validation Loop L1-L3. No git commit unless the orchestrator directs it.
  If asked: "P1.M1.T2.S1: cuda_check single-model contract ({device,compute_type,model}; cuda=small.en,
  cpu=tiny.en) + dedicated tests; consumers rewired in T2.S2 (transient red intended)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the collapse edit is atomic across cuda_check.py: dicts + module docstring + resolve
# docstring + _main print + _main docstring output-list. Anything less KeyErrors the CLI (install.sh's
# smoke step) or leaves stale docs. Gate: grep final_model|realtime_model in cuda_check.py == 0.

# PATTERN 2 — hermetic probe monkeypatching (the new test file). Never patch the function under test;
# patch the PROBES it calls. For _main, patch _cuda_device_count/_torch_cuda_available/
# _ctranslate2_version and capture stdout with capsys; assert the VERDICT line + the exact resolved
# substring + (load-bearing) that 'final_model'/'realtime_model' do NOT appear.

# PATTERN 3 — red-transient test updates. The two test_daemon sites are updated to the END-state
# expectations + a DO-NOT-SHIM comment. They cannot pass until T2.S2 rewires daemon.cfg_to_kwargs/
# _log_resolved_device (which read resolved['final_model'] -> KeyError on the 3-key dict). Fixing them
# here would mean editing daemon.py (T2.S2's file) — the exact "papering over" the contract forbids.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T2.S2 (daemon.py + recorder_host.py mode collapse; the paired consumer rewrite):
  - T2.S2 rewrites daemon._resolve_device_config to build {device, compute_type, model: cfg.asr.lite_model}
    defaults, cfg_to_kwargs to map resolved["model"] -> BOTH model= and realtime_model_type= (single model),
    _log_resolved_device to print model=, recorder_host's _child_resolved_device/ready payload to the 3-key
    shape, and ctl.py status accordingly. The two test_daemon sites updated here go GREEN in T2.S2.
  - The 3-key contract + the CPU-wins-over-defaults rule + the fresh-dict rule are pinned by the new
    tests/test_cuda_check.py so T2.S2 codes against a tested substrate.

SIBLING BOUNDARIES:
  - T2.S3 (ctl command surface, drop lite cmds), T2.S4 (prefetch CORE_REPOS slim-down, hypr-binds collapse,
    ACCEPTANCE #10) — no file overlap with T2.S1.
  - T1.S1 (config schema) owns AsrConfig + config.toml + the other test_config edits; T1.S2 (evdev) owns
    pyproject/uv.lock. The parity test is the ONE shared site — this PRP's end-state pin (lite_model +
    3-key shape) is final in both landing orders.

INSTALL.SH SMOKE (unwired here):
  - install.sh invokes `python -m voice_typing.cuda_check` and greps VERDICT=; the CLI keeps that
    contract (same lines, exit codes) — only the resolved line's model fields collapse. T2.S4 owns any
    install.sh text sweep.
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). L1/L2 are hermetic (no CUDA/daemon); L3 documents the intended
> transient. Run from `/home/dustin/projects/voice-typing`.

### Level 1: The collapse is in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L1a: no final_model/realtime_model anywhere in cuda_check.py ---"
n=$(grep -c 'final_model\|realtime_model' voice_typing/cuda_check.py); echo "count=$n"
[ "$n" -eq 0 ] && echo "L1a PASS" || echo "L1a FAIL: $n stale refs (finish the atomic edit)"
echo "--- L1b: the 3-key dicts + resolved print ---"
grep -q '"model": "small.en"' voice_typing/cuda_check.py && grep -q '"model": "tiny.en"' voice_typing/cuda_check.py \
  && grep -q "model={cfg\['model'\]}" voice_typing/cuda_check.py && echo "L1b PASS" || echo "L1b FAIL"
echo "--- L1c: parses + probe machinery intact ---"
.venv/bin/python -c "import ast; ast.parse(open('voice_typing/cuda_check.py').read()); import voice_typing.cuda_check as c; assert set(c.CUDA_DEFAULTS)=={'device','compute_type','model'}; assert set(c.CPU_FALLBACK)=={'device','compute_type','model'}; assert callable(c.resolve_device_and_models); assert callable(c.is_cuda_available); print('L1c PASS')"
# Expected: 0 stale refs; small.en/tiny.en model keys + the model= print; parses; both dicts 3-key.
```

### Level 2: The focused gates are green (the contract's own tests)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L2a: the NEW dedicated cuda_check suite ---"
timeout 600 .venv/bin/python -m pytest tests/test_cuda_check.py -q 2>&1 | tail -3
echo "--- L2b: the contract's focused config gate (verbatim from the contract) ---"
timeout 600 .venv/bin/python -m pytest tests/test_config.py -k 'defaults or cuda' -q 2>&1 | tail -3
# Expected: L2a all pass (~8); L2b all pass (incl. the re-pinned test_defaults_match_cuda_check +
# test_defaults_match_prd_4_5 + test_from_toml_empty_dict_is_all_defaults). If L2b fails on a
# final_model assert in test_defaults_match_prd_4_5: that is T1.S1's site, not yours (CRITICAL #6) —
# coordinate; do not edit. If L2a's _main tests fail on the resolved substring: re-check Task 1's print.
```

### Level 3: Scope + the documented transient (do NOT fix the red)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L3a: only the 4 expected files changed ---"
git status --short | grep -vE 'cuda_check|test_config|test_daemon' && echo "L3a FAIL: out-of-scope file" || echo "L3a PASS"
git diff --quiet voice_typing/daemon.py voice_typing/recorder_host.py voice_typing/ctl.py voice_typing/prefetch.py voice_typing/config.py config.toml pyproject.toml 2>/dev/null \
  && echo "L3a PASS: consumer/schema files untouched" || echo "L3a FAIL: consumer edited (T2.S2's file!)"
echo "--- L3b: document the intended transient (broader suite red is EXPECTED until T2.S2) ---"
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -2
echo "  ^ red here is the INTENDED transient (KeyError at resolved['final_model']) — resolved by P1.M1.T2.S2."
echo "--- L3c (optional, live CLI): VERDICT + the 3-key resolved line ---"
timeout 30 .venv/bin/python -m voice_typing.cuda_check 2>/dev/null || true   # exit 1 on cpu-fallback is VALID
# Expected: the last line shows device/compute_type/model= (no final_model=); VERDICT greppable either way.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: zero `final_model`/`realtime_model` in cuda_check.py; both dicts exactly 3 keys; the `model={cfg['model']}` print; parses; probes intact.
- [ ] L2a: new `tests/test_cuda_check.py` all pass (hermetic; incl. fresh-copy, CPU-wins, `_main` output shape, CUDA-free import).
- [ ] L2b: `timeout 600 .venv/bin/python -m pytest tests/test_config.py -k 'defaults or cuda' -q` green.
- [ ] L3a: diff ⊆ {cuda_check.py, test_cuda_check.py(new), test_config.py, test_daemon.py}; daemon/recorder_host/ctl/prefetch/config/pyproject untouched.
- [ ] L3b: broader-suite red documented as the intended transient (not fixed).

### Feature Validation
- [ ] CUDA: `{cuda, float16, small.en}`; CPU: `{cpu, int8, tiny.en}`; resolve semantics (defaults-passthrough / CPU-override / fresh dict) unchanged.
- [ ] `_main()` prints the 3-key resolved line; VERDICT + exit codes unchanged.
- [ ] Module + resolve docstrings describe the single-model contract (Mode A).
- [ ] The parity test pins `lite_model == CUDA_DEFAULTS["model"]` + the 3-key shape + `CPU_FALLBACK["model"] == "tiny.en"`.

### Code Quality Validation
- [ ] Probe machinery (`_cuda_device_count`/`is_cuda_available`/etc.) byte-identical; lazy ctranslate2 import preserved.
- [ ] New tests follow repo style (docstring + Run: line); monkeypatch probes only; capsys for CLI output.
- [ ] The two test_daemon sites carry the DO-NOT-SHIM red-transient comments.

### Scope Boundary Validation
- [ ] No daemon.py/recorder_host.py/ctl.py edits (T2.S2); no ctl-surface work (T2.S3); no prefetch/binds/ACCEPTANCE (T2.S4); no config schema (T1.S1); no pyproject (T1.S2).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore untouched.

### Documentation & Deployment
- [ ] Mode A: cuda_check.py docstring + `_main()` output ARE the docs (ride with the work).
- [ ] Commit message (if directed) names the transient ("consumers rewired in T2.S2; red intended").

---

## Anti-Patterns to Avoid

- ❌ Don't paper over the transient — no `final_model`/`realtime_model` compat keys in the dicts, no daemon.py edits, no deleted consumer tests. The red window until T2.S2 IS the plan (CRITICAL #1).
- ❌ Don't update the dicts without `_main()` (KeyErrors the CLI — install.sh's smoke step) or the docstrings. One atomic edit; gate with the zero-stale-refs grep (CRITICAL #2).
- ❌ Don't touch the probe machinery — only the model contract changes. The wrapped ctranslate2 import, driver-only-count semantics, torch-as-diagnostics, exit codes, and the LD_LIBRARY_PATH warning stay verbatim (CRITICAL #3).
- ❌ Don't write a test that really imports ctranslate2/torch — monkeypatch `is_cuda_available`/`_cuda_device_count` (CRITICAL #5); the fast suite must stay CUDA-free (AGENTS.md: minutes-long cold loads).
- ❌ Don't break the CPU-override rule — `resolve(custom_defaults)` on no-CUDA returns `dict(CPU_FALLBACK)` regardless of defaults; pin it (CRITICAL #4).
- ❌ Don't edit test_defaults_match_prd_4_5 or T1.S1's other test_config sites — your gate is `-k 'defaults or cuda'`; the prd-parity test's final/realtime asserts are T1.S1's (CRITICAL #6).
- ❌ Don't make the two test_daemon sites green by weakening them to the OLD shape — pin the END-state (tiny.en in both model slots; 3-key resolved dicts; `model=tiny.en` in the log line) with the red-transient comment.
- ❌ Don't drop the inner `timeout` on pytest/CLI commands (AGENTS.md); use `.venv/bin/python` full paths (Gotcha #7).
- ❌ Don't create the new tests anywhere but `tests/test_cuda_check.py` (no dedicated file exists; the name matches the module — Gotcha #8).

---

## Confidence Score

**9/10** for one-pass implementation success. The change is a well-bounded contract collapse (~30 lines of one module + one new hermetic test file + three surgical test re-pins), and every load-bearing fact is verified against the live tree: the verbatim current cuda_check.py (dicts @45-58, resolve @114-131, `_main`'s `cfg['final_model']` read @161 — the atomicity trap), the exact stale-test sites with line numbers (test_config @66-78; test_daemon ~2740-2747 + ~2813-2849, read in full), the no-dedicated-test-file fact (substrate_map §3), T1.S1's schema contract + its interim parity-test edit (which mine supersedes, order-independent), and the T2.S2 consumer-rewrite split that makes the red window intentional. The hermetic test design (probe monkeypatching + capsys) follows the repo's established patterns, so the focused gates run in seconds without CUDA. The −1 is inherent to the **staged transient**: the two test_daemon sites cannot be verified green here (they're correct-for-T2.S2 but red until it lands), so their end-state correctness is only fully confirmed downstream — mitigated by the DO-NOT-SHIM comments + the exact expected assertions being specified, and by T2.S2's paired PRP (per the plan) consuming this exact 3-key contract.

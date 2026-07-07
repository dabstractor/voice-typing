# PRP — P1.M2.T1.S1: Config dataclasses + tomllib loader + search order + unit tests

## Goal

**Feature Goal**: Produce `voice_typing/config.py` — a **pure-stdlib** module (`os`, `pathlib`, `dataclasses`, `tomllib`) that parses user TOML config into nested dataclasses exactly matching PRD §4.5, and a `load(path=None)` implementing the documented search order (`$XDG_CONFIG_HOME/voice-typing/config.toml` → repo `config.toml` → built-in defaults). Also produce `tests/test_config.py` — the project's **first** unit-test module (TDD: tests written first, then config.py), establishing the pytest pattern every downstream test task reuses.

**Deliverable** (exactly three artifacts):
1. `voice_typing/config.py` — exports `VoiceTypingConfig`, `AsrConfig`, `OutputConfig`, `FeedbackConfig`, `FilterConfig`, `VoiceTypingConfig.load()`/`from_toml()`/`from_toml_file()`, `FeedbackConfig.resolved_state_file()`, and a module-level `load()` (verbatim source in Implementation Blueprint → Task 3).
2. `tests/test_config.py` — pytest unit tests covering defaults, search-order precedence, missing-file fallback, lazy `state_file` resolution, blocklist isolation, and unknown-key rejection (verbatim source in Implementation Blueprint → Task 2).
3. **`pyproject.toml` + `uv.lock` change** — add `pytest` as a dev dependency (`uv add --dev pytest`), because this is the first test and there is currently no test runner in the venv (`.venv/bin/python -c "import pytest"` → ModuleNotFoundError, verified). This single change establishes the runner for the whole test plan (P1.M2.T2.S1, P1.M3.T1.S2, P1.M7).

**Success Definition**:
- (a) `voice_typing/config.py` exists, `py_compile`-clean, and `import voice_typing.config` succeeds importing **only stdlib** (no `ctranslate2`/`torch`/`cuda_check`/`realtimestt`).
- (b) `VoiceTypingConfig()` (no file) returns **every PRD §4.5 default exactly** (backend="wtype", final_model="distil-large-v3", realtime_model="small.en", language="en", device="cuda", post_speech_silence_duration=0.6, realtime_processing_pause=0.15, min_chars=2, blocklist=[...5 entries...], hypr_notify=True, notify_ms=2500, append_space=True, tmux_target="", state_file="").
- (c) `VoiceTypingConfig.load(path=None)` implements the search order: XDG candidate (wins) → repo candidate → built-ins; an explicit `path=` bypasses the search.
- (d) `FeedbackConfig.resolved_state_file()` resolves empty `state_file` lazily to `$XDG_RUNTIME_DIR/voice-typing/state.json`, raising `RuntimeError` when `XDG_RUNTIME_DIR` is unset.
- (e) `.venv/bin/python -m pytest tests/test_config.py -v` → **all tests pass** (after `uv add --dev pytest`).
- (f) No out-of-scope files: no `daemon.py`, no `textproc.py`, no `config.toml` (that is P1.M2.T1.S2), no `feedback.py`, no `typing_backends.py`, no `install.sh`, no systemd, no edits to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`.

## User Persona

Not applicable (no end-user surface). This is internal plumbing consumed by `textproc` (P1.M2.T2.S1), `typing_backends` (P1.M3.T1.S1), `feedback` (P1.M3.T2.S1), and `daemon` (P1.M4.T1.S1). DOCS: **Mode A** — `config.toml` (created in S2, downstream) IS the user-facing config reference; this task's defaults must stay byte-identical to S2's `config.toml` so the comments and the code never drift.

## Why

- **One source of truth for runtime tuning.** Every tunable knob (silence duration, partial cadence, backend, blocklist, notify duration) flows from `VoiceTypingConfig` into the daemon + its subsystems. Centralizing it in dataclasses means a user edits ONE `config.toml` and the daemon, textproc, typing backend, and feedback all see the new value with no rewiring. (PRD §4.5; §4.7 textproc consumes `cfg.filter`; §4.3 backend consumes `cfg.output`.)
- **Hallucination filter config lives here.** `FilterConfig.blocklist` (the 5 Whisper silence-hallucination phrases) is a top-3 project risk (PRD §8). `textproc.clean()` (P1.M2.T2.S1) reads it from config — so the schema + defaults must be correct and unit-tested NOW, before any GPU/STT code exists. This task is **pure-Python and GPU-free**: it can be built + fully validated with zero CUDA/audio deps.
- **Decouples config from CUDA availability.** `config.py` holds the user's *desired* `device="cuda"`. Whether CUDA is *actually* present is decided by `cuda_check.resolve_device_and_models()` (P1.M1.T2.S2) and *applied* by the daemon (P1.M4.T1.S1) as an override. Keeping config pure-stdlib means it loads in tests, CPU-only contexts, and before ctranslate2 is installed — no heavy/optional imports.

## What

Create `voice_typing/config.py` (verbatim source in Implementation Blueprint → Task 3): five `@dataclass`es (`AsrConfig`, `OutputConfig`, `FeedbackConfig`, `FilterConfig`, aggregating `VoiceTypingConfig`) with PRD §4.5 defaults, a `from_toml(data)`/`from_toml_file(path)`/`load(path=None)` constructor trio, lazy `FeedbackConfig.resolved_state_file()`, and module-level `_candidate_paths()`/`_xdg_config_path()`/`_repo_config_path()`/`load()` helpers. Then `tests/test_config.py` (verbatim source in Implementation Blueprint → Task 2) exercising defaults, the three search-order branches, lazy state-file resolution, blocklist isolation, unknown-key rejection, and malformed-TOML propagation.

### Success Criteria

- [ ] `voice_typing/config.py` exists; `.venv/bin/python -m py_compile voice_typing/config.py` exits 0.
- [ ] `import voice_typing.config` imports **only** `os`/`pathlib`/`dataclasses`/`tomllib` (grep-clean of `ctranslate2`/`torch`/`cuda_check`/`realtimestt`/`fastapi`).
- [ ] `VoiceTypingConfig()` equals every PRD §4.5 default (pinned by `test_defaults_match_prd_4_5`).
- [ ] `AsrConfig()` defaults for `final_model`/`realtime_model`/`device` equal `voice_typing.cuda_check.CUDA_DEFAULTS` (drift guard — `test_defaults_match_cuda_check`).
- [ ] `load(path=None)` returns the XDG file when both XDG + repo exist; repo when only repo exists; built-in defaults when neither exists (`test_search_order_*`).
- [ ] `load(path=explicit)` loads that one file and bypasses the search.
- [ ] `FeedbackConfig().resolved_state_file()` returns `$XDG_RUNTIME_DIR/voice-typing/state.json` when `state_file` empty + `XDG_RUNTIME_DIR` set; raises `RuntimeError` when both unset.
- [ ] Unknown TOML key in a section raises `TypeError` (loud, not silently ignored).
- [ ] Malformed TOML raises `tomllib.TOMLDecodeError` (propagates, not swallowed).
- [ ] `blocklist` is not shared across `FilterConfig()` instances (`default_factory` works).
- [ ] `.venv/bin/python -m pytest tests/test_config.py -v` → **all green**.
- [ ] Only new files: `voice_typing/config.py`, `tests/test_config.py`. `pyproject.toml`/`uv.lock` gain ONLY the pytest dev dep. No other files touched.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement this from the PRP + the referenced research. The full `config.py` and `tests/test_config.py` source is given verbatim; every default is pinned to PRD §4.5; the tomllib API (binary-mode `load`, `TOMLDecodeError`) + dataclass mutable-default rule + XDG fallback rule are documented against the canonical docs in `research/tomllib_dataclasses_xdg.md`; and the machine preconditions (Python 3.12.10, tomllib present, `voice_typing` editable-importable, pytest absent) are verified live.

### Documentation & References

```yaml
# MUST READ — the authoritative schema + every default value (the contract for this task)
- file: PRD.md
  why: "§4.5 is the authoritative TOML schema + defaults. §4.1 repo layout (config.py location; tests/
        test_textproc.py as the unit-test pattern). §4.7 textproc consumes cfg.filter (min_chars, blocklist).
        §4.3 typing backend consumes cfg.output (backend, tmux_target). §4.6 feedback consumes cfg.feedback
        (state_file→XDG_RUNTIME_DIR, hypr_notify, notify_ms). §4.4 device/compute_type (compute_type is a
        cuda_check concern, NOT a config field)."
  critical: "§4.5 defaults must be reproduced EXACTLY (incl. the 5 blocklist entries and their trailing
             periods). device='cuda' is the DESIRED value; cuda_check may override at daemon runtime."

# MUST READ — verified machine facts + the corrected decisions (READ-ONLY context)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1: Python 3.12.10, shell aliases → ALWAYS full paths (.venv/bin/python, /home/dustin/.local/bin/uv);
        XDG_RUNTIME_DIR semantics under pam_systemd. §4 decision #6/#7: daemon applies cuda_check override
        (config stays pure). §2 file map (config.py + tests/ locations)."
  critical: "Use .venv/bin/python + /home/dustin/.local/bin/uv explicitly; never bare python/uv/tmux
             (zsh aliases shadow them). Python 3.12 → `str | None` unions + stdlib tomllib are native."

# MUST READ — tomllib API + dataclass gotchas + XDG spec (this task's own research; load-bearing)
- docfile: plan/001_be48c74bc590/P1M2T1S1/research/tomllib_dataclasses_xdg.md
  why: "§1 tomllib: binary-mode load() requirement, TOMLDecodeError propagation decision, TOML→Python type
        map (0.6→float, 2→int, true→bool), pure-stdlib/dependency-free. §2 dataclasses: mutable-default
        field(default_factory=...) rule, nested-config default_factory, unknown-kwarg TypeError exploitation,
        mutability (NOT frozen) for daemon override, `from __future__ import annotations` needed for bare
        classmethod self-returns. §3 XDG: XDG_CONFIG_HOME unset/empty→~/.config; XDG_RUNTIME_DIR unset
        outside sessions (why state_file is lazy); module-relative repo path; first-existing-wins. §4 the
        pytest-as-dev-dep decision + hermetic monkeypatch strategy. §5 scope coupling (cuda_check, no
        compute_type, blocklist verbatim)."
  section: "ALL sections load-bearing. §1, §2 (default_factory), §3 (XDG), §4 (pytest), §5 (coupling)."

# Background — the sibling module whose MODEL NAMES config defaults must match (drift guard)
- file: voice_typing/cuda_check.py
  why: "CUDA_DEFAULTS = {device:'cuda', compute_type:'float16', final_model:'distil-large-v3',
        realtime_model:'small.en'}. config.AsrConfig defaults for final_model/realtime_model/device MUST
        equal these (test_defaults_match_cuda_check pins it). cuda_check.resolve_device_and_models() is what
        the daemon calls to OVERRIDE config at runtime; config.py does NOT call it (keeps config pure-stdlib).
        Mirror its conventions: `from __future__ import annotations`, module docstring, lazy heavy imports."
  critical: "compute_type is cuda_check's field, NOT config's. config has device/final_model/realtime_model
             but NO compute_type. Do not 'helpfully' add compute_type to AsrConfig (PRD §4.5 has no such key)."

# Background — the concurrent task whose OUTPUT (prefetch.py) is unrelated but present in voice_typing/
- file: plan/001_be48c74bc590/P1M1T3S1/PRP.md
  why: "P1.M1.T3.S1 (running in parallel) creates voice_typing/prefetch.py and does NOT touch pyproject.toml
        or uv.lock (its Anti-Patterns forbid uv sync/add). So this task's `uv add --dev pytest` is the ONLY
        concurrent writer of pyproject/uv.lock — safe. prefetch.py is UNRELATED to config.py; just don't be
        confused by its presence in voice_typing/."
  critical: "Do NOT import prefetch in config.py. Do NOT block on T3.S1. The two modules are independent."

# Downstream — the test runner decision's consumers (why pytest-as-dev-dep is the right foundation)
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M2.T2.S1 (tests/test_textproc.py), P1.M3.T1.S2 (typing-backend unit tests), P1.M7 (full test
        suite) ALL need a unit-test runner. Adding pytest once HERE (the first test task) is the correct
        foundation; those tasks reuse `uv add --dev pytest`'s result."
  critical: "This is the FIRST test; it sets the pattern. Do not invent a one-off runner."
```

### Current Codebase tree (state at P1.M2.T1.S1 start — S1 + T2.* done, T3.S1 in parallel)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*'` from repo root. Expected:

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores dist/, *.pyc, __pycache__/, .venv/, .pi-subagents/ (DO NOT touch)
├── .venv/                      # Python 3.12.10; realtimestt + nvidia-* + huggingface_hub installed (S2)
│   │                             pytest is NOT installed yet — Task 1 adds it as a dev dep.
│   └── bin/python              # the python everything runs under
├── PRD.md                      # READ-ONLY
├── pyproject.toml              # ← S1's output (4 deps; [project.scripts] voicectl/daemon). Task 1 ADDS pytest dev dep.
├── uv.lock                     # ← S2's output. Task 1 updates it (uv add --dev pytest).
└── voice_typing/
    ├── __init__.py             # ← S1's output (package docstring)
    ├── cuda_check.py           # ← T2.S2's output (CUDA_DEFAULTS/CPU_FALLBACK — the drift-guard target)
    ├── launch_daemon.sh        # ← T2.S1's output (LD_LIBRARY_PATH wrapper — NOT used by config/tests)
    └── prefetch.py             # ← P1.M1.T3.S1 (parallel) MAY have created this — UNRELATED to config; ignore.
# NO voice_typing/config.py yet — Task 3 creates it (the only new SOURCE file).
# NO tests/ dir yet — Task 2 creates tests/test_config.py (the first test file).
# NO config.toml yet — that is P1.M2.T1.S2 (DOWNSTREAM, depends on THIS task's defaults).
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
├── pyproject.toml              # MODIFY: add [dependency-groups] dev = ["pytest"] (via `uv add --dev pytest`)
├── uv.lock                     # MODIFY: updated by uv add (pytest + its small dep tree)
├── voice_typing/
│   └── config.py               # ← CREATE (the importable loader module; the only new SOURCE file)
└── tests/
    └── test_config.py          # ← CREATE (pytest unit tests; the project's first test module)
# NOTHING ELSE. No __init__.py in tests/ (pytest discovers test_*.py without it; the package is
# editable-installed so `from voice_typing.config import ...` resolves). No config.toml (S2). No daemon/
# textproc/feedback/typing_backends (later tasks). No install.sh/systemd (P1.M6).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — tomllib.load() REQUIRES BINARY MODE.
#   `tomllib.load(open(path))` (text mode) raises TypeError. Use `with open(path, "rb") as fh: tomllib.load(fh)`.
#   tomllib is stdlib since 3.11; we require >=3.12 so NO tomli backport, NO try/except. (Research §1.)

# CRITICAL #2 — MUTABLE DEFAULTS NEED field(default_factory=...).
#   `blocklist: list[str] = [...]` is a ValueError at class-definition time. Use
#   `field(default_factory=lambda: [...])` so each instance gets its OWN list. Likewise nested configs:
#   `asr: AsrConfig = field(default_factory=AsrConfig)` (NOT `asr: AsrConfig = AsrConfig()`). (Research §2.)
#   The test test_blocklist_not_shared_between_instances guards this.

# CRITICAL #3 — `from __future__ import annotations` IS REQUIRED (not just conventional) here.
#   The classmethods return `-> VoiceTypingConfig` from INSIDE the VoiceTypingConfig class body. Without
#   the future import, 3.12 evaluates annotations eagerly at def-time → NameError (the class name isn't
#   bound until the class body finishes). With it, annotations are strings → safe. cuda_check.py uses it
#   too; match that. (Research §2.4.)

# CRITICAL #4 — config.py MUST STAY PURE-STDLIB. Do NOT import cuda_check/ctranslate2/torch/realtimestt.
#   config loads in tests and CPU-only contexts and before any CUDA dep. The device="cuda" default is the
#   user's DESIRED value; the daemon (P1.M4.T1.S1) calls cuda_check.resolve_device_and_models() and applies
#   the override (cfg.asr.device = "cpu") ITSELF. Wiring cuda_check into config would (a) add a heavy dep
#   and (b) be wrong scope. (system_context.md §4 #6; research §5.) The dataclasses are deliberately NOT
#   frozen so the daemon can mutate them for the fallback.

# CRITICAL #5 — NO `compute_type` FIELD. PRD §4.5 has no compute_type key; it is a cuda_check concern
#   (§4.4). Adding it to AsrConfig would desync from the TOML schema that S2 writes. (Research §5.)

# CRITICAL #6 — XDG_RUNTIME_DIR IS UNSET OUTSIDE LOGIN SESSIONS. That is why FeedbackConfig.state_file
#   resolution is LAZY (resolved_state_file() called at write time by feedback.py), NOT at load() time.
#   If state_file is empty AND XDG_RUNTIME_DIR unset → raise RuntimeError (no safe default; silently
#   writing to /tmp or ~ would be a bug). Tests cover both branches. (Research §3.2.)

# CRITICAL #7 — XDG_CONFIG_HOME unset OR empty → ~/.config (spec mandates BOTH → default). Use
#   `os.environ.get("XDG_CONFIG_HOME", "").strip() or os.path.expanduser("~/.config")` (the .strip()
#   handles whitespace-only; the `or` handles empty). (Research §3.1.)

# CRITICAL #8 — REPO config path MUST be MODULE-RELATIVE, not CWD-relative. Use
#   `Path(__file__).resolve().parent.parent / "config.toml"` (config.py → voice_typing/ → repo root).
#   A bare "./config.toml" depends on CWD and breaks under systemd ExecStart. Do NOT hardcode
#   /home/dustin/projects/voice-typing (not portable). (Research §3.3.) NOTE: config.toml is NOT in the
#   wheel (packages=["voice_typing"]); for installed runs the repo candidate won't exist — that's fine,
#   install.sh copies it to the XDG candidate which wins anyway.

# CRITICAL #9 — SEARCH ORDER: FIRST EXISTING FILE WINS; built-ins are the FINAL fallback (not an error).
#   `load(path=None)` iterates _candidate_paths() = [xdg, repo], returns on first os.path.isfile(). If
#   none exist → VoiceTypingConfig(). An explicit path= BYPASSES the search (loads that one file).
#   (Research §3.4.)

# CRITICAL #10 — UNKNOWN TOML KEYS MUST RAISE (not be silently dropped). `AsrConfig(**{"bakcend":1})`
#   raises TypeError (dataclass __init__ rejects unknown kwargs). We EXPLOIT this: from_toml passes each
#   section's dict as **kwargs, so a typo'd key surfaces loudly. Do NOT pre-filter keys. (Research §2.3.)
#   Likewise a scalar where a table is expected ([asr] = "x") → from_toml raises TypeError (isinstance
#   Mapping check). Malformed TOML → tomllib.TOMLDecodeError propagates (do NOT swallow into defaults).

# GOTCHA #11 — `filter` SHADOWS THE BUILTIN. VoiceTypingConfig.filter matches the TOML [filter] key and
#   from_toml's data.get("filter"). config.py never calls the builtin filter(), so the shadow is harmless.
#   Keep `filter` (do NOT rename to filter_cfg — that decouples from the TOML key). ruff is not configured
#   in this project and does not flag attribute shadowing by default. (Research §2.6.)

# GOTCHA #12 — pytest IS NOT INSTALLED; THIS TASK ADDS IT. `uv add --dev pytest` writes
#   [dependency-groups] dev = ["pytest"] in pyproject.toml + updates uv.lock + installs into .venv. This
#   is the ONLY pyproject/uv.lock change in scope, justified because it's the first test (establishes the
#   runner for the whole plan). The parallel P1.M1.T3.S1 does NOT touch pyproject/uv.lock (its PRP forbids
#   uv sync/add) → no concurrent-writer conflict. (Research §4.) Run tests with FULL PATHS:
#   `.venv/bin/python -m pytest tests/test_config.py -v`.

# GOTCHA #13 — TESTS MUST BE HERMETIC. Manipulate XDG_CONFIG_HOME / XDG_RUNTIME_DIR via pytest's
#   `monkeypatch` (auto-restores) and monkeypatch voice_typing.config._xdg_config_path / _repo_config_path
#   to temp paths (so the search-order test doesn't depend on the real repo config.toml, which doesn't
#   exist yet during S1). Use `tmp_path` for temp TOML files (auto-cleaned). Do NOT mutate os.environ
#   directly (leaks across tests). (Research §4.)

# GOTCHA #14 — FULL PATHS in every bash call. This machine aliases python3→uv run, pip→alias, tmux→zsh
#   plugin. Invoke .venv/bin/python and /home/dustin/.local/bin/uv explicitly. (system_context.md §1.)

# GOTCHA #15 — blocklist STORED VERBATIM. Lowercasing + trailing-punctuation stripping is textproc's job
#   at COMPARE time (PRD §4.7, P1.M2.T2.S1). config.py does not transform blocklist. Defaults are already
#   lowercase per §4.5. (Research §5.)

# GOTCHA #16 — ruff/mypy ARE NOT INSTALLED and not configured. Do NOT make them blocking validation
#   gates. Use py_compile + pytest for validation. (Verified: .venv has neither.) Mentioning them as
#   "optional, if installed" is fine; requiring them would fail the gate.
```

## Implementation Blueprint

### Data models and structure

Five `@dataclass`es (stdlib only). **NOT frozen** — the daemon (P1.M4.T1.S1) mutates them for the cuda_check CPU-fallback override (`cfg.asr.device = "cpu"`). Nested configs use `field(default_factory=...)` (Gotcha #2). The schema is PRD §4.5 verbatim:

```python
AsrConfig:        final_model="distil-large-v3", realtime_model="small.en", language="en",
                  device="cuda", post_speech_silence_duration=0.6 (float), realtime_processing_pause=0.15 (float)
OutputConfig:     backend="wtype", tmux_target="", append_space=True (bool)
FeedbackConfig:   state_file="", hypr_notify=True (bool), notify_ms=2500 (int)  + resolved_state_file() method
FilterConfig:     min_chars=2 (int), blocklist=["thank you.","thanks for watching.","you","bye.","thank you for watching"] (list[str])
VoiceTypingConfig: asr/output/feedback/filter sub-configs (each via default_factory) + classmethods
```

No ORM/pydantic — plain dataclasses (matches `cuda_check.py`'s plain-dict style; keeps zero third-party deps).

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST, then config.py)

```yaml
Task 0: PREFLIGHT — confirm inputs + that targets don't yet exist (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/__init__.py && echo "ok: package exists (S1)" || echo "PREFLIGHT FAIL"
      test -f voice_typing/cuda_check.py && echo "ok: cuda_check exists (drift-guard target)" || echo "PREFLIGHT FAIL: cuda_check missing"
      test ! -e voice_typing/config.py && echo "ok: config.py not yet created" || echo "PREFLIGHT FAIL: config.py exists"
      test ! -e tests/test_config.py && echo "ok: tests/test_config.py not yet created" || echo "PREFLIGHT FAIL"
      .venv/bin/python -c "import voice_typing, voice_typing.cuda_check; print('import OK')" || echo "PREFLIGHT FAIL: package not editable-installed"
      .venv/bin/python -c "import tomllib; print('tomllib OK', __import__('sys').version.split()[0])" || echo "PREFLIGHT FAIL: no tomllib (need 3.11+)"
      .venv/bin/python -c "import pytest" 2>/dev/null && echo "note: pytest already installed" || echo "note: pytest NOT installed (Task 1 adds it)"
  - EXPECTED: package + cuda_check present; config.py + tests/test_config.py absent; import OK; tomllib OK
    (3.12.10); pytest absent (Task 1 will add it).
  - DO NOT: create config.py yet, run uv sync/add, or touch any other file.

Task 1: ADD pytest AS A DEV DEPENDENCY (the test runner — first test in the project)
  - RUN (from /home/dustin/projects/voice-typing):
      /home/dustin/.local/bin/uv add --dev pytest
      .venv/bin/python -c "import pytest; print('pytest', pytest.__version__)"
  - WHY: there is NO test runner yet (verified). This is the first test; it establishes pytest for the
    whole plan. uv 0.7.11 writes [dependency-groups] dev = ["pytest"] in pyproject.toml + updates uv.lock
    + installs pytest into .venv. The parallel P1.M1.T3.S1 does NOT touch pyproject/uv.lock → no conflict.
  - EXPECTED: pyproject.toml gains a [dependency-groups] dev = ["pytest"] (or equivalent) section; uv.lock
    updates; `import pytest` prints a version (e.g. 8.x). NO change to [project].dependencies or
    [project.scripts] (those stay exactly as S1 left them).
  - DO NOT: add pytest to the main [project].dependencies (it must be a DEV/group dep, not shipped in the
    wheel); add ruff/mypy (not in scope; not configured); edit pyproject.toml by hand (let `uv add` do it).

Task 2: CREATE tests/test_config.py FIRST (TDD) — use the `write` tool with EXACTLY the content in
        "Task 2 SOURCE" below. These tests are RED until Task 3 lands config.py.
  - FILE: tests/test_config.py
  - WHY FIRST: the task contract mandates TDD ("write tests/test_config.py first"). The tests pin every
    PRD §4.5 default + the 3 search-order branches + lazy state_file + blocklist isolation, so config.py
    is implemented AGAINST an executable spec. Run them after Task 3; expect all green.
  - DO NOT: import cuda_check/ctranslate2 in the test (keep it pure); mutate os.environ directly (use
    monkeypatch); depend on a real repo config.toml existing (monkeypatch the path helpers).

Task 3: CREATE voice_typing/config.py — use the `write` tool with EXACTLY the content in "Task 3 SOURCE".
  - FILE: voice_typing/config.py
  - CONTENT: see "Task 3 SOURCE" below (verbatim — module docstring + 5 dataclasses + classmethods +
    search-order helpers + module-level load()).
  - DO NOT: import cuda_check/ctranslate2/torch/realtimestt (Gotcha #4); add compute_type (Gotcha #5);
    freeze the dataclasses (daemon needs to mutate); swallow TOMLDecodeError (Gotcha #10); pre-filter
    unknown keys (Gotcha #10); resolve state_file at load time (Gotcha #6); rename `filter` (Gotcha #11).

Task 4: VALIDATE — run the Validation Loop L1–L5 below. Iterate until all gates pass (tests RED→GREEN).
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M2.T1.S1: config.py (dataclasses + tomllib loader + XDG search order) + tests/test_config.py + pytest dev dep".
```

#### Task 2 SOURCE — `tests/test_config.py` (write verbatim)

```python
"""Unit tests for voice_typing.config (PRD §4.5 — config schema + search order).

Pure-Python: no network, no GPU, no audio. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_config.py -v

These are the project's FIRST unit tests; they establish the pytest pattern every
downstream test task (test_textproc, typing-backend tests, P1.M7 suite) reuses.
"""
from __future__ import annotations

import os

import pytest

import voice_typing.config as cfgmod
from voice_typing.config import (
    AsrConfig,
    FeedbackConfig,
    FilterConfig,
    OutputConfig,
    VoiceTypingConfig,
)

# PRD §4.5 authoritative blocklist (pinned verbatim, incl. trailing periods).
_PRD_BLOCKLIST = [
    "thank you.",
    "thanks for watching.",
    "you",
    "bye.",
    "thank you for watching",
]


# ---------------------------------------------------------------------------
# Defaults (PRD §4.5) — the single source of truth these tests pin
# ---------------------------------------------------------------------------

def test_defaults_match_prd_4_5():
    """A bare VoiceTypingConfig() must equal PRD §4.5 defaults exactly."""
    cfg = VoiceTypingConfig()
    # [asr]
    assert cfg.asr.final_model == "distil-large-v3"
    assert cfg.asr.realtime_model == "small.en"
    assert cfg.asr.language == "en"
    assert cfg.asr.device == "cuda"
    assert cfg.asr.post_speech_silence_duration == 0.6
    assert cfg.asr.realtime_processing_pause == 0.15
    # [output]
    assert cfg.output.backend == "wtype"
    assert cfg.output.tmux_target == ""
    assert cfg.output.append_space is True
    # [feedback]
    assert cfg.feedback.state_file == ""
    assert cfg.feedback.hypr_notify is True
    assert cfg.feedback.notify_ms == 2500
    # [filter]
    assert cfg.filter.min_chars == 2
    assert cfg.filter.blocklist == _PRD_BLOCKLIST


def test_defaults_match_cuda_check():
    """Drift guard: asr model/device defaults must equal cuda_check.CUDA_DEFAULTS.

    config holds the DESIRED values; cuda_check holds the same values as its CUDA
    path. If these drift, the daemon's cuda_check override (P1.M4.T1.S1) would
    contradict the config defaults.
    """
    from voice_typing.cuda_check import CUDA_DEFAULTS

    assert AsrConfig().final_model == CUDA_DEFAULTS["final_model"]
    assert AsrConfig().realtime_model == CUDA_DEFAULTS["realtime_model"]
    assert AsrConfig().device == CUDA_DEFAULTS["device"]


def test_field_types_are_tomllib_natural_types():
    """Defaults carry the Python types tomllib yields (float for 0.6, int, bool)."""
    cfg = VoiceTypingConfig()
    assert isinstance(cfg.asr.post_speech_silence_duration, float)  # 0.6, not int 0
    assert isinstance(cfg.asr.realtime_processing_pause, float)
    assert isinstance(cfg.filter.min_chars, int)
    assert isinstance(cfg.feedback.notify_ms, int)
    assert isinstance(cfg.output.append_space, bool)
    assert isinstance(cfg.filter.blocklist, list)


def test_blocklist_not_shared_between_instances():
    """default_factory must give each FilterConfig its OWN list (no shared state)."""
    a = FilterConfig()
    b = FilterConfig()
    a.blocklist.append("mutated")
    assert "mutated" not in b.blocklist
    assert b.blocklist == _PRD_BLOCKLIST


# ---------------------------------------------------------------------------
# from_toml / from_toml_file
# ---------------------------------------------------------------------------

def test_from_toml_partial_table_keeps_other_defaults():
    """A TOML with only one overridden key keeps every other default."""
    cfg = VoiceTypingConfig.from_toml({"asr": {"language": "es"}})
    assert cfg.asr.language == "es"                  # overridden
    assert cfg.asr.final_model == "distil-large-v3"  # same-section default kept
    assert cfg.output.backend == "wtype"             # other section untouched
    assert cfg.filter.min_chars == 2                 # other section untouched


def test_from_toml_empty_dict_is_all_defaults():
    """An empty TOML mapping yields pure defaults (no tables present)."""
    assert VoiceTypingConfig.from_toml({}) == VoiceTypingConfig()


def test_from_toml_unknown_key_raises():
    """A typo'd key must surface as a loud TypeError, not be silently ignored."""
    with pytest.raises(TypeError):
        VoiceTypingConfig.from_toml({"output": {"bakcend": "tmux"}})


def test_from_toml_section_not_a_table_raises():
    """A scalar where a TOML table is expected must raise (not silently default)."""
    with pytest.raises(TypeError):
        VoiceTypingConfig.from_toml({"asr": "not-a-table"})


def test_from_toml_file_reads_toml(tmp_path):
    """from_toml_file parses a real TOML file (binary mode — tomllib requirement)."""
    f = tmp_path / "c.toml"
    f.write_text(
        '[asr]\nlanguage = "fr"\n[output]\nbackend = "tmux"\ntmux_target = "voicetest:0.0"\n',
        encoding="utf-8",
    )
    cfg = VoiceTypingConfig.from_toml_file(f)
    assert cfg.asr.language == "fr"
    assert cfg.output.backend == "tmux"
    assert cfg.output.tmux_target == "voicetest:0.0"


def test_invalid_toml_propagates(tmp_path):
    """Malformed TOML raises tomllib.TOMLDecodeError (fail loud, not silent default)."""
    import tomllib

    f = tmp_path / "bad.toml"
    f.write_text('bad = "unterminated string\n', encoding="utf-8")
    with pytest.raises(tomllib.TOMLDecodeError):
        VoiceTypingConfig.from_toml_file(f)


# ---------------------------------------------------------------------------
# load(path=None) — the PRD §4.5 search order
# ---------------------------------------------------------------------------

def test_load_with_explicit_path_bypasses_search(tmp_path):
    """load(path=...) loads that one file and skips the search order."""
    f = tmp_path / "explicit.toml"
    f.write_text('[asr]\ndevice = "cpu"\n', encoding="utf-8")
    cfg = VoiceTypingConfig.load(f)
    assert cfg.asr.device == "cpu"
    assert cfg.asr.final_model == "distil-large-v3"  # non-overridden default kept


def test_search_order_xdg_wins_over_repo(tmp_path, monkeypatch):
    """PRD §4.5: XDG config wins over repo config when BOTH exist."""
    xdg_file = tmp_path / "xdg.toml"
    repo_file = tmp_path / "repo.toml"
    xdg_file.write_text('[asr]\nlanguage = "de"\n', encoding="utf-8")   # XDG marker
    repo_file.write_text('[asr]\nlanguage = "ja"\n', encoding="utf-8")  # repo marker
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(xdg_file))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(repo_file))
    cfg = VoiceTypingConfig.load(None)
    assert cfg.asr.language == "de"  # XDG won


def test_search_order_repo_used_when_xdg_absent(tmp_path, monkeypatch):
    """When the XDG candidate does not exist, the repo candidate is used."""
    repo_file = tmp_path / "repo.toml"
    repo_file.write_text('[asr]\nlanguage = "ja"\n', encoding="utf-8")
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(tmp_path / "missing-xdg.toml"))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(repo_file))
    cfg = VoiceTypingConfig.load(None)
    assert cfg.asr.language == "ja"


def test_search_order_missing_file_falls_back_to_defaults(tmp_path, monkeypatch):
    """No candidate exists → built-in dataclass defaults (NOT an error)."""
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(tmp_path / "no-xdg.toml"))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(tmp_path / "no-repo.toml"))
    cfg = VoiceTypingConfig.load(None)
    assert cfg == VoiceTypingConfig()  # pure defaults


def test_xdg_config_path_falls_back_to_home_when_unset(monkeypatch):
    """XDG_CONFIG_HOME unset/empty → ~/.config/voice-typing/config.toml (XDG spec)."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    expected = os.path.join(os.path.expanduser("~/.config"), "voice-typing", "config.toml")
    assert cfgmod._xdg_config_path() == expected


def test_xdg_config_path_respects_env(monkeypatch):
    """XDG_CONFIG_HOME set → used verbatim (with the voice-typing/config.toml suffix)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/xdg")
    assert cfgmod._xdg_config_path() == "/custom/xdg/voice-typing/config.toml"


# ---------------------------------------------------------------------------
# FeedbackConfig.resolved_state_file() — lazy XDG_RUNTIME_DIR resolution
# ---------------------------------------------------------------------------

def test_resolved_state_file_uses_xdg_runtime_dir(monkeypatch):
    """Empty state_file + XDG_RUNTIME_DIR set → <RUNTIME>/voice-typing/state.json."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert FeedbackConfig().resolved_state_file() == "/run/user/1000/voice-typing/state.json"


def test_resolved_state_file_explicit_path_returned_as_is():
    """Non-empty state_file is returned verbatim (no XDG resolution)."""
    fb = FeedbackConfig(state_file="/tmp/custom-state.json")
    assert fb.resolved_state_file() == "/tmp/custom-state.json"


def test_resolved_state_file_raises_when_xdg_runtime_unset(monkeypatch):
    """Empty state_file + XDG_RUNTIME_DIR unset → RuntimeError (no safe default)."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    with pytest.raises(RuntimeError):
        FeedbackConfig().resolved_state_file()


# ---------------------------------------------------------------------------
# Module-level load() wrapper
# ---------------------------------------------------------------------------

def test_module_level_load_matches_classmethod(tmp_path, monkeypatch):
    """voice_typing.config.load() is a thin wrapper over VoiceTypingConfig.load()."""
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(tmp_path / "x.toml"))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(tmp_path / "r.toml"))
    assert cfgmod.load() == VoiceTypingConfig()
```

#### Task 3 SOURCE — `voice_typing/config.py` (write verbatim)

```python
"""voice-typing configuration: dataclasses + stdlib tomllib loader (PRD §4.5).

Loads user config from TOML into nested dataclasses. The schema and every default
below mirror config.toml (P1.M2.T1.S2) and PRD §4.5 EXACTLY — they are the single
source of truth for runtime tuning.

SEARCH ORDER (PRD §4.5), implemented by VoiceTypingConfig.load(path=None):
  1. $XDG_CONFIG_HOME/voice-typing/config.toml   (XDG_CONFIG_HOME unset/empty → ~/.config/...)
  2. <repo>/config.toml                          (module-relative; parent dir of voice_typing/)
  3. built-in dataclass defaults                 (no candidate found → VoiceTypingConfig())
The FIRST existing file wins. An explicit `path=` disables the search and loads
that one file (used by tests and a future --config flag).

THIS MODULE IS PURE DATA + A LOADER (stdlib only: os, pathlib, dataclasses,
tomllib). It must NOT import cuda_check / ctranslate2 / torch / realtimestt —
config must load in CPU-only and test contexts. The `device="cuda"` default is the
user's DESIRED setting; whether CUDA is actually available is decided at daemon
startup by voice_typing.cuda_check.resolve_device_and_models() (P1.M1.T2.S2),
which the daemon (P1.M4.T1.S1) APPLIES as an override on the loaded config
(e.g. `cfg.asr.device = "cpu"`). `compute_type` is NOT a config field (it is a
cuda_check concern per §4.4); do not add it here.

state_file LAZY RESOLUTION: FeedbackConfig.state_file defaults to "" (empty).
Its effective path ($XDG_RUNTIME_DIR/voice-typing/state.json when empty) is
resolved lazily by FeedbackConfig.resolved_state_file() — NOT at load time —
because XDG_RUNTIME_DIR is unset outside real login sessions (cron, tests,
non-interactive shells). feedback.py (P1.M3.T2.S1) calls resolved_state_file()
at write time; if state_file is empty AND XDG_RUNTIME_DIR is unset it raises
RuntimeError (no safe default — fail clearly rather than write to a wrong path).

CONSUMERS: textproc.clean(cfg.filter) (P1.M2.T2.S1), typing_backends (cfg.output)
(P1.M3.T1.S1), feedback (cfg.feedback) (P1.M3.T2.S1), daemon (whole cfg + the
cuda_check override) (P1.M4.T1.S1).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Sub-config dataclasses (PRD §4.5 — defaults mirror config.toml EXACTLY)
# ---------------------------------------------------------------------------

@dataclass
class AsrConfig:
    """[asr] — ASR model + device settings. `device` may be overridden by cuda_check."""

    final_model: str = "distil-large-v3"
    realtime_model: str = "small.en"
    language: str = "en"
    device: str = "cuda"  # "cuda" | "cpu" (daemon may override via cuda_check at startup)
    post_speech_silence_duration: float = 0.6  # VAD: finalize after this much silence (seconds)
    realtime_processing_pause: float = 0.15    # partials cadence (seconds)


@dataclass
class OutputConfig:
    """[output] — typing-output backend selection."""

    backend: str = "wtype"     # "wtype" | "ydotool" | "tmux"
    tmux_target: str = ""      # used only when backend == "tmux", e.g. "voicetest:0.0"
    append_space: bool = True  # daemon appends one trailing space to each final


@dataclass
class FeedbackConfig:
    """[feedback] — state file + Hyprland notification settings."""

    state_file: str = ""       # "" → resolved lazily to $XDG_RUNTIME_DIR/voice-typing/state.json
    hypr_notify: bool = True   # hyprctl notify one-liner for start/final/stop
    notify_ms: int = 2500      # hyprctl notify duration (ms)

    def resolved_state_file(self) -> str:
        """Return the effective state-file path (lazy XDG_RUNTIME_DIR resolution).

        Non-empty state_file → returned verbatim. Empty →
        $XDG_RUNTIME_DIR/voice-typing/state.json. Raises RuntimeError if empty
        AND XDG_RUNTIME_DIR is unset/empty (no safe default — fail clearly).
        """
        if self.state_file:
            return self.state_file
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        if not xdg_runtime:
            raise RuntimeError(
                "feedback.state_file is empty and XDG_RUNTIME_DIR is not set; "
                "cannot determine the state-file path. Set state_file in config "
                "or run under a session that exports XDG_RUNTIME_DIR (systemd "
                "user sessions set it)."
            )
        return os.path.join(xdg_runtime, "voice-typing", "state.json")


@dataclass
class FilterConfig:
    """[filter] — post-recognition text filter. Consumed by textproc.clean()."""

    min_chars: int = 2
    # default_factory: each FilterConfig gets its OWN list (mutable-default guard).
    # Stored VERBATIM; textproc lowercases + strips trailing punctuation at compare
    # time (PRD §4.7). Defaults are already lowercase per §4.5.
    blocklist: list[str] = field(
        default_factory=lambda: [
            "thank you.",
            "thanks for watching.",
            "you",
            "bye.",
            "thank you for watching",
        ]
    )


@dataclass
class VoiceTypingConfig:
    """Top-level config aggregating all PRD §4.5 sub-sections."""

    asr: AsrConfig = field(default_factory=AsrConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)

    # --- construction from parsed TOML / files ---

    @classmethod
    def from_toml(cls, data: Mapping[str, Any]) -> VoiceTypingConfig:
        """Build a config from an already-parsed TOML mapping.

        Each table ([asr]/[output]/[feedback]/[filter]) overlays its dataclass
        defaults — only present keys override; missing tables/keys keep defaults.
        Unknown keys raise TypeError (dataclass __init__ rejects them) so a typo'd
        config key surfaces loudly instead of being silently ignored. Malformed
        TOML is caught upstream by tomllib (TOMLDecodeError); a scalar where a
        table is expected raises TypeError via the Mapping check here.
        """

        def _overlay(section_cls, table_name):
            section = data.get(table_name, {})
            if not isinstance(section, Mapping):
                raise TypeError(
                    f"[{table_name}] must be a TOML table, got {type(section).__name__}"
                )
            return section_cls(**section)

        return cls(
            asr=_overlay(AsrConfig, "asr"),
            output=_overlay(OutputConfig, "output"),
            feedback=_overlay(FeedbackConfig, "feedback"),
            filter=_overlay(FilterConfig, "filter"),
        )

    @classmethod
    def from_toml_file(cls, path: str | os.PathLike[str]) -> VoiceTypingConfig:
        """Read + parse a TOML file → config. tomllib requires BINARY mode."""
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls.from_toml(data)

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> VoiceTypingConfig:
        """Load from `path`, or via the PRD §4.5 search order when path is None.

        Search order (first EXISTING file wins):
          1. $XDG_CONFIG_HOME/voice-typing/config.toml (unset/empty → ~/.config/...)
          2. <repo>/config.toml (module-relative: parent dir of voice_typing/)
          3. built-in dataclass defaults (no candidate exists)
        An explicit path= bypasses the search and loads that one file.
        """
        if path is not None:
            return cls.from_toml_file(path)
        for candidate in _candidate_paths():
            if os.path.isfile(candidate):
                return cls.from_toml_file(candidate)
        return cls()  # built-in defaults


# ---------------------------------------------------------------------------
# Search-order helpers (module-level so tests can monkeypatch them for hermeticity)
# ---------------------------------------------------------------------------

def _xdg_config_path() -> str:
    """$XDG_CONFIG_HOME/voice-typing/config.toml (XDG unset/empty → ~/.config/...)."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not xdg_config:
        xdg_config = os.path.expanduser("~/.config")
    return os.path.join(xdg_config, "voice-typing", "config.toml")


def _repo_config_path() -> str:
    """<repo>/config.toml — module-relative so it resolves regardless of CWD.

    voice_typing/config.py → parent = voice_typing/ → parent = repo root.
    config.toml is NOT packaged in the wheel (packages=["voice_typing"]); for
    installed runs this candidate won't exist — install.sh copies it to XDG.
    """
    return str(Path(__file__).resolve().parent.parent / "config.toml")


def _candidate_paths() -> list[str]:
    """Ordered search candidates: XDG first, then repo. Defaults are the fallback."""
    return [_xdg_config_path(), _repo_config_path()]


def load(path: str | os.PathLike[str] | None = None) -> VoiceTypingConfig:
    """Module-level convenience wrapper around VoiceTypingConfig.load()."""
    return VoiceTypingConfig.load(path)
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — mutable-default guard via field(default_factory=...). Both for the list (blocklist) AND for
# nested sub-configs. Without this, `blocklist: list[str] = [...]` is a ValueError, and
# `asr: AsrConfig = AsrConfig()` shares ONE AsrConfig across every VoiceTypingConfig (mutation leak).
blocklist: list[str] = field(default_factory=lambda: ["thank you.", ...])
asr: AsrConfig = field(default_factory=AsrConfig)

# PATTERN 2 — overlay-on-defaults via **kwargs (exploits dataclass unknown-kwarg rejection). Each TOML
# section's dict becomes kwargs to the sub-config constructor; present keys override, absent keys keep
# defaults, and a TYPO raises TypeError loudly. Do NOT pre-filter keys (that would hide typos).
section = data.get("asr", {})          # {} when [asr] absent → all defaults
return AsrConfig(**section)            # AsrConfig(language="es") overrides only language

# PATTERN 3 — binary-mode tomllib load + fail-loud parse errors. tomllib.load requires "rb"; invalid TOML
# raises TOMLDecodeError which we LET PROPAGATE (the daemon logs it; config is a pure loader).
with open(path, "rb") as fh:
    data = tomllib.load(fh)            # TOMLDecodeError propagates — never swallow into defaults

# PATTERN 4 — lazy XDG_RUNTIME_DIR resolution (deferred to write time). state_file="" stays empty in the
# config object; the EFFECTIVE path is computed on demand so config can load when XDG_RUNTIME_DIR is unset.
def resolved_state_file(self):
    if self.state_file:
        return self.state_file
    xdg = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if not xdg:
        raise RuntimeError("state_file empty and XDG_RUNTIME_DIR unset")  # no silent wrong path
    return os.path.join(xdg, "voice-typing", "state.json")

# PATTERN 5 — module-level search-path helpers (monkeypatchable for hermetic tests). _candidate_paths()
# returns [xdg, repo]; load() returns the first existing; tests redirect these to tmp_path so the search-
# order behavior is proven without depending on the real repo config.toml (absent during S1).
def _candidate_paths():
    return [_xdg_config_path(), _repo_config_path()]
```

### Integration Points

```yaml
DOWNSTREAM — P1.M2.T1.S2 (config.toml; THE doc):
  - S2 writes config.toml with [asr]/[output]/[feedback]/[filter] tables whose VALUES equal this task's
    dataclass defaults EXACTLY. If a default is ever changed in config.py, the matching line + comment in
    config.toml MUST change in lockstep (Mode A: config.toml IS the user-facing config reference). S2 will
    verify load("config.toml") returns no overrides (== VoiceTypingConfig()).

DOWNSTREAM — P1.M2.T2.S1 (textproc.clean): consumes cfg.filter (FilterConfig: min_chars, blocklist).
  - clean(text, cfg.filter) uses cfg.filter.min_chars and cfg.filter.blocklist (stored verbatim; textproc
    lowercases + strips trailing punctuation at compare time). The schema + defaults pinned here are the
    contract textproc codes against.

DOWNSTREAM — P1.M3.T1.S1 (typing_backends): consumes cfg.output (backend, tmux_target, append_space).
  - backend ∈ {"wtype","ydotool","tmux"} selects the impl; tmux_target used only when backend=="tmux";
    append_space tells the daemon to append one trailing space to each final (daemon's job, not the backend's).

DOWNSTREAM — P1.M3.T2.S1 (feedback): consumes cfg.feedback (state_file, hypr_notify, notify_ms).
  - Calls cfg.feedback.resolved_state_file() at WRITE time (lazy XDG_RUNTIME_DIR resolution). hypr_notify +
    notify_ms gate/duration the hyprctl notify one-liner.

DOWNSTREAM — P1.M4.T1.S1 (daemon): consumes the WHOLE VoiceTypingConfig + applies the cuda_check override.
  - cfg = VoiceTypingConfig.load(); resolved = cuda_check.resolve_device_and_models(); if CPU fallback:
    cfg.asr.device = resolved["device"]; cfg.asr.final_model = resolved["final_model"];
    cfg.asr.realtime_model = resolved["realtime_model"]. compute_type comes from cuda_check (NOT config).
    The dataclasses are deliberately NOT frozen so this mutation works.

PARALLEL — P1.M1.T3.S1 (prefetch.py): UNRELATED. Its PRP does NOT touch pyproject.toml/uv.lock (forbids
  uv sync/add), so this task's `uv add --dev pytest` is the sole concurrent writer of those files → safe.
  Do NOT import prefetch in config.py.

CONDITIONAL — this task modifies ONLY pyproject.toml (adds [dependency-groups] dev = ["pytest"]) + uv.lock
  (uv add updates it) via `uv add --dev pytest`, and creates voice_typing/config.py + tests/test_config.py.
  It does NOT touch PRD.md, tasks.json, prd_snapshot.md, .gitignore, uv.lock beyond the pytest update, or
  any other source file. No config.toml (S2), no daemon/textproc/feedback/typing_backends (later tasks).
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases — system_context.md §1). Run from
> `/home/dustin/projects/voice-typing`. L1 is instant. L2 runs the unit tests (the contract).
> L3 is a manual smoke of the real search order. L4 is the scope guard.

### Level 1: Syntax + import-cleanness (no deps needed beyond stdlib)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f voice_typing/config.py && echo "L1 file present" || echo "L1 FAIL: config.py missing"
"$PY" -m py_compile voice_typing/config.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
# THE KEY IMPORT TEST: importing config must pull ONLY stdlib (no cuda_check/ctranslate2/torch/realtimestt):
"$PY" -c "import voice_typing.config as m; print('L1 import OK'); print(' classes:', [c for c in dir(m) if c[0].isupper()]); print(' load:', m.load, m.VoiceTypingConfig.load)" \
  && echo "L1 PASS: importable, pure-stdlib" \
  || echo "L1 FAIL: import raised (heavy dep leaked?)"
# Verify NO forbidden imports (config must be pure stdlib):
! grep -nE '^[[:space:]]*(import|from) (cuda_check|ctranslate2|faster_whisper|torch|realtimestt|fastapi|pydantic)' voice_typing/config.py \
  && echo "L1 PASS: no forbidden imports (pure stdlib)" \
  || echo "L1 FAIL: forbidden import found (Gotcha #4)"
# Expected: file present, py_compile clean, import OK listing AsrConfig/OutputConfig/FeedbackConfig/
# FilterConfig/VoiceTypingConfig + load, no forbidden imports.
```

### Level 2: Unit tests (the contract — TDD RED→GREEN)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# pytest must be installed (Task 1). If not, run: /home/dustin/.local/bin/uv add --dev pytest
"$PY" -c "import pytest; print('pytest', pytest.__version__)" || { echo "L2 BLOCKED: pytest missing — run Task 1"; exit 1; }
"$PY" -m pytest tests/test_config.py -v
# Expected: ALL tests pass (defaults, search-order x3, lazy state_file x3, blocklist isolation, unknown-key
# raises, malformed-TOML propagates, module-level load). Exit 0. Any failure → READ the failure, fix
# config.py (NOT the test, unless the test itself is wrong), re-run.
# Full-project test run (should be just this file for now):
"$PY" -m pytest -q
# Expected: only tests/test_config.py collected; all pass; exit 0.
```

### Level 3: Real search-order smoke (proves load() against the actual filesystem)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) No XDG config, no repo config (repo config.toml doesn't exist yet — S2 creates it) → built-in defaults:
"$PY" - <<'PYEOF'
import os
os.environ.pop("XDG_CONFIG_HOME", None)  # use ~/.config default
from voice_typing.config import VoiceTypingConfig, _repo_config_path
import os.path
cfg = VoiceTypingConfig.load(None)
assert cfg.asr.final_model == "distil-large-v3", cfg.asr.final_model
assert cfg.output.backend == "wtype"
print("L3a PASS: load(None) with no files → built-in defaults (final_model=%s)" % cfg.asr.final_model)
print("   repo candidate present?", os.path.isfile(_repo_config_path()), "(", _repo_config_path(), ")")
PYEOF
# (b) Explicit path bypasses search:
TMPF=$(mktemp /tmp/vt-cfg-XXXX.toml)
printf '[asr]\nlanguage = "fr"\n[output]\nbackend = "tmux"\ntmux_target = "voicetest:0.0"\n' > "$TMPF"
"$PY" - "$TMPF" <<'PYEOF'
import sys
from voice_typing.config import VoiceTypingConfig
cfg = VoiceTypingConfig.load(sys.argv[1])
assert cfg.asr.language == "fr" and cfg.output.backend == "tmux" and cfg.output.tmux_target == "voicetest:0.0"
print("L3b PASS: load(path=explicit) → language=%s backend=%s target=%s" % (cfg.asr.language, cfg.output.backend, cfg.output.tmux_target))
PYEOF
rm -f "$TMPF"
# (c) Lazy state_file resolution under a fake XDG_RUNTIME_DIR:
XDG_RUNTIME_DIR=/run/user/fake "$PY" - <<'PYEOF'
from voice_typing.config import FeedbackConfig
print("L3c PASS: resolved_state_file() ->", FeedbackConfig().resolved_state_file())
assert FeedbackConfig().resolved_state_file() == "/run/user/fake/voice-typing/state.json"
PYEOF
# Expected: L3a defaults, L3b explicit-path parse, L3c /run/user/fake/voice-typing/state.json.
```

### Level 4: Scope guards — only config.py + tests/test_config.py created; read-only files untouched

```bash
cd /home/dustin/projects/voice-typing
# Only NEW source files are voice_typing/config.py + tests/test_config.py:
ls voice_typing/   # expect: __init__.py  config.py  cuda_check.py  launch_daemon.sh  [prefetch.py]
ls tests/          # expect: test_config.py
# Read-only / out-of-scope files UNCHANGED or ABSENT:
for f in PRD.md tasks.json prd_snapshot.md .gitignore; do
  test -f "plan/001_be48c74bc590/$f" && echo "present (verify unchanged): plan/.../$f" || echo "absent (ok): $f"
done
# config.toml must NOT exist yet (it is P1.M2.T1.S2 — DOWNSTREAM):
test ! -e config.toml && echo "L4 PASS: config.toml correctly absent (S2's job)" || echo "L4 FAIL: config.toml created out of scope"
# daemon/textproc/feedback/typing_backends must NOT exist yet:
for f in voice_typing/daemon.py voice_typing/textproc.py voice_typing/feedback.py voice_typing/typing_backends.py voice_typing/ctl.py install.sh systemd; do
  test ! -e "$f" && echo "absent (ok): $f" || echo "L4 WARN: $f exists (verify not created by this task)"
done
# pyproject.toml gained ONLY the pytest dev dep (main deps + scripts unchanged):
grep -nE '^(realtimestt|nvidia-cublas-cu12|nvidia-cudnn-cu12|huggingface_hub|voicectl|voice-typing-daemon)' pyproject.toml
grep -nA2 'dependency-groups' pyproject.toml && echo "L4 PASS: pytest dev dep present" || echo "L4 FAIL: no [dependency-groups]"
git status --short
# Expected: git status shows voice_typing/config.py (new), tests/test_config.py (new), pyproject.toml
# (modified: +pytest dev dep), uv.lock (modified). Nothing else.
```

### Level 5: Downstream-readiness sanity (proves the contract the next tasks rely on)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" - <<'PYEOF'
# The exact attribute paths downstream tasks will use (catch a rename before they code against it):
from voice_typing.config import VoiceTypingConfig
cfg = VoiceTypingConfig()
# textproc (P1.M2.T2.S1):
assert cfg.filter.min_chars == 2 and isinstance(cfg.filter.blocklist, list)
# typing_backends (P1.M3.T1.S1):
assert cfg.output.backend == "wtype" and cfg.output.tmux_target == "" and cfg.output.append_space is True
# feedback (P1.M3.T2.S1):
assert cfg.feedback.hypr_notify is True and cfg.feedback.notify_ms == 2500
assert hasattr(cfg.feedback, "resolved_state_file")
# daemon (P1.M4.T1.S1) — mutable so the cuda_check override works:
cfg.asr.device = "cpu"; cfg.asr.final_model = "small.en"   # must not raise (NOT frozen)
assert cfg.asr.device == "cpu"
print("L5 PASS: all downstream attribute paths resolve; dataclasses are mutable (cuda_check override works)")
PYEOF
# Expected: L5 PASS. If a `dataclasses.FrozenInstanceError` fires on the assignment, the dataclasses were
# frozen by mistake — remove frozen=True (Gotcha: daemon mutates config for fallback).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 `py_compile` clean + `import voice_typing.config` succeeds importing ONLY stdlib (grep-clean).
- [ ] L2 `.venv/bin/python -m pytest tests/test_config.py -v` → **all tests pass** (exit 0).
- [ ] L3 real search-order smoke: no-file→defaults, explicit-path parse, lazy state_file resolution.
- [ ] L4 only `voice_typing/config.py` + `tests/test_config.py` created; `pyproject.toml`/`uv.lock` gained ONLY pytest dev dep; read-only files untouched; no config.toml/daemon/etc. created.
- [ ] L5 all downstream attribute paths (`cfg.filter.*`, `cfg.output.*`, `cfg.feedback.*`, `cfg.asr.*`) resolve; dataclasses mutable (cuda_check override assignment works).

### Feature Validation
- [ ] `VoiceTypingConfig()` equals every PRD §4.5 default (`test_defaults_match_prd_4_5`).
- [ ] `AsrConfig()` defaults match `cuda_check.CUDA_DEFAULTS` (`test_defaults_match_cuda_check` — drift guard).
- [ ] `load(path=None)` search order: XDG wins → repo → built-ins (`test_search_order_*` x3).
- [ ] `load(path=explicit)` bypasses the search.
- [ ] `FeedbackConfig.resolved_state_file()` lazy + raises when XDG_RUNTIME_DIR unset.
- [ ] Unknown TOML key raises `TypeError`; malformed TOML raises `tomllib.TOMLDecodeError`.
- [ ] `blocklist` not shared across instances (`default_factory` works).

### Code Quality Validation
- [ ] `config.py` imports ONLY `os`/`pathlib`/`dataclasses`/`tomllib` (no cuda_check/ctranslate2/torch/realtimestt).
- [ ] No `compute_type` field (it is cuda_check's concern, not config's).
- [ ] Dataclasses NOT frozen (daemon mutates for the cuda_check fallback).
- [ ] `from __future__ import annotations` present (required for bare `-> VoiceTypingConfig` classmethod returns).
- [ ] Defaults match PRD §4.5 byte-for-byte (incl. the 5 blocklist entries + trailing periods).
- [ ] Full paths used in every bash command (`.venv/bin/python`, `/home/dustin/.local/bin/uv`).

### Documentation & Deployment
- [ ] Module docstring documents: schema source (§4.5), search order, pure-stdlib constraint, the cuda_check-override division of responsibility, lazy state_file resolution, and all consumers.
- [ ] `config.toml` (S2) will mirror these defaults — if any default changes here, S2's config.toml must change in lockstep (Mode A).

### Scope Boundary Validation
- [ ] No `config.toml` created (P1.M2.T1.S2), no `daemon.py`/`textproc.py`/`feedback.py`/`typing_backends.py`/`ctl.py`, no `install.sh`, no systemd.
- [ ] No edits to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`.
- [ ] `pyproject.toml` changed ONLY by `uv add --dev pytest` (main `[project].dependencies` + `[project.scripts]` untouched).
- [ ] pytest added as a DEV/group dependency (NOT in main `[project].dependencies`).

---

## Anti-Patterns to Avoid

- ❌ Don't import `cuda_check`/`ctranslate2`/`torch`/`realtimestt` in `config.py` — config must stay pure-stdlib (loads in tests/CPU-only/before-CUDA). The cuda_check override is the daemon's job (P1.M4.T1.S1).
- ❌ Don't add `compute_type` to `AsrConfig` — PRD §4.5 has no such key; it's a cuda_check concern (§4.4).
- ❌ Don't freeze the dataclasses — the daemon mutates `cfg.asr.device`/`final_model`/`realtime_model` for the CPU fallback.
- ❌ Don't use a class-level mutable default (`blocklist: list = [...]` or `asr: AsrConfig = AsrConfig()`) — use `field(default_factory=...)` or you get a ValueError / shared-state bug.
- ❌ Don't open the TOML file in text mode — `tomllib.load` requires `"rb"`.
- ❌ Don't swallow `tomllib.TOMLDecodeError` into defaults — malformed user config must fail loud (the daemon logs it).
- ❌ Don't pre-filter unknown TOML keys — `AsrConfig(**section)` rejecting them IS the typo-detection feature.
- ❌ Don't resolve `state_file` to `$XDG_RUNTIME_DIR` at load() time — it's lazy (XDG_RUNTIME_DIR may be unset). Resolve in `resolved_state_file()` and RAISE if empty + unset (don't guess `/tmp`).
- ❌ Don't use a CWD-relative `"./config.toml"` for the repo candidate — use `Path(__file__).resolve().parent.parent` (CWD-independent; works under systemd). Don't hardcode `/home/dustin/...`.
- ❌ Don't rename `filter` to `filter_cfg` — it must match the TOML `[filter]` key (the builtin shadow is harmless; `filter()` is unused in config.py).
- ❌ Don't add pytest to the main `[project].dependencies` — it's a dev/group dep (`uv add --dev pytest`), not shipped in the wheel.
- ❌ Don't create `config.toml`, `daemon.py`, `textproc.py`, etc. — those are downstream tasks.
- ❌ Don't edit `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`.
- ❌ Don't use bare `python`/`pip`/`uv`/`tmux` (zsh aliases shadow them on this machine) — use full paths.
- ❌ Don't make ruff/mypy blocking gates — neither is installed or configured in this project; use `py_compile` + `pytest`.

---

## Confidence Score

**9/10** for one-pass implementation success. The full `config.py` and `tests/test_config.py` source is given verbatim; every default is pinned to PRD §4.5 and cross-checked against `cuda_check.CUDA_DEFAULTS` (a live, importable module); the tomllib binary-mode requirement, dataclass `default_factory` rule, XDG fallback rule, and lazy `state_file` semantics are documented against canonical docs in `research/tomllib_dataclasses_xdg.md`; and the machine preconditions (Python 3.12.10, tomllib present, `voice_typing` editable-importable, pytest absent-but-addable) are verified live. The residual uncertainty (−1) is the `uv add --dev pytest` step: uv 0.7.11 supports `[dependency-groups]` (PEP 735) and the parallel P1.M1.T3.S1 does not touch pyproject/uv.lock, so no conflict is expected — but if uv emits an unexpected resolution error, the fallback is to add `[dependency-groups]\ndev = ["pytest"]` to pyproject.toml by hand and run `uv sync`, which is mechanical, not a re-design.

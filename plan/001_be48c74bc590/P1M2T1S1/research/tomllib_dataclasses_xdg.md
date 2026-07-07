# Research: tomllib loader + dataclasses + XDG search order (P1.M2.T1.S1)

Authored for `voice_typing/config.py`. All facts verified against Python 3.12.10
on this machine (`.venv/bin/python`) and the canonical docs below. This is the
load-bearing reference for the PRP's verbatim source + gotchas.

---

## 1. tomllib (stdlib, Python ≥3.11) — the only parser we use

Canonical docs: https://docs.python.org/3.12/library/tomllib.html

**Load-bearing API + gotchas:**

| Concern | Truth | Source |
|---|---|---|
| Open mode | `tomllib.load(fp)` requires the file opened in **BINARY** mode (`open(path, "rb")`). Text mode raises `TypeError: File must be opened in binary mode.` | docs "Loading TOML" — "Since the TOML spec requires UTF-8, this module's API only accepts binary mode" |
| String input | `tomllib.loads(s)` parses a `str` (NOT bytes). We don't need it — we always read a file. | docs |
| Read-only | tomllib has **no writer** (`tomllib.dump`/`dumps` do not exist). That is fine: we only READ config. Writing `config.toml` is a human/install.sh job, never ours. | docs (only `load`/`loads` exported) |
| Parse error | Invalid TOML raises `tomllib.TOMLDecodeError` (subclass of `ValueError`). Decision: **let it propagate** (fail loud). The daemon (P1.M4) should catch + log it; config.py is a pure loader. Do NOT swallow it into a default — a malformed user config must surface, not silently fall back to built-ins. | docs "Exceptions" |
| Availability | `import tomllib` works on 3.11+. We require `>=3.12,<3.13` (pyproject), so NO `tomli` backport, NO try/except fallback is needed. Verified: `.venv/bin/python -c "import tomllib"` → OK (3.12.10). | docs "Module Contents"; system_context.md §1 |
| No C ext | tomllib is pure-Python (vendored tomli). Import is instant + dependency-free — keeps `config.py` importable with zero third-party deps (critical: config must load in CPU-only/test contexts). | docs |

**TOML → Python type mapping (determines our dataclass field types):**

| TOML literal | Python type | Config field |
|---|---|---|
| `final_model = "distil-large-v3"` | `str` | `AsrConfig.final_model: str` |
| `post_speech_silence_duration = 0.6` | `float` | `AsrConfig.post_speech_silence_duration: float` |
| `realtime_processing_pause = 0.15` | `float` | `AsrConfig.realtime_processing_pause: float` |
| `min_chars = 2` | `int` | `FilterConfig.min_chars: int` |
| `append_space = true` | `bool` | `OutputConfig.append_space: bool` |
| `hypr_notify = true` | `bool` | `FeedbackConfig.hypr_notify: bool` |
| `notify_ms = 2500` | `int` | `FeedbackConfig.notify_ms: int` |
| `blocklist = ["thank you.", ...]` | `list[str]` | `FilterConfig.blocklist: list[str]` |

⚠️ `device = "cuda"` has a TOML comment (`# "cuda" | "cpu"`) — comments are NOT
returned by the parser, so `data["asr"]["device"]` is just `"cuda"`. Good.

---

## 2. dataclasses — the schema layer

Canonical docs: https://docs.python.org/3.12/library/dataclasses.html

**Load-bearing patterns + gotchas for THIS module:**

1. **Mutable defaults MUST use `field(default_factory=...)`.**
   `blocklist: list[str] = [...]` is a `ValueError` (mutable default). Use
   `field(default_factory=lambda: ["thank you.", ...])` so each instance gets its
   OWN list (no shared-state bug across `VoiceTypingConfig()` instances).
   Docs: https://docs.python.org/3.12/library/dataclasses.html#default-values
   ("This has the same meaning as the default parameter ... If the default value
   of a field is specified by a call to field(), ... default_factory ...").

2. **Nested dataclasses need `default_factory` for the parent.**
   `VoiceTypingConfig.asr: AsrConfig = field(default_factory=AsrConfig)` —
   constructing an `AsrConfig` instance as a class-level default is ALSO a
   mutable-default error. `default_factory=AsrConfig` builds a fresh sub-config
   per `VoiceTypingConfig()`. Same for output/feedback/filter.

3. **`@dataclass` rejects unknown kwargs in `__init__`.**
   `AsrConfig(unknown_key=1)` raises `TypeError: __init__() got an unexpected
   keyword argument 'unknown_key'`. We EXPLOIT this: `from_toml` does
   `AsrConfig(**section_data)`, so a typo'd key in the user's TOML (e.g.
   `backend = wtype` without quotes is a TOML error anyway, but `bakcend="wtype"`
   with quotes) surfaces as a loud TypeError instead of being silently ignored.
   This is the right default for config — do NOT pre-filter keys.
   Docs: https://docs.python.org/3.12/library/dataclasses.html#dataclasses.dataclass

4. **`from __future__ import annotations` stringizes annotations.**
   With it, `str | os.PathLike[str] | None` is never evaluated at runtime — safe
   on 3.12. dataclasses do NOT need to evaluate annotations to build `__init__`
   (they read defaults, not types). So `from __future__ import annotations` is
   fully compatible. (Matches `cuda_check.py`'s existing convention.)
   Docs: https://docs.python.org/3.12/library/dataclasses.html#module-level-decorators-functions

5. **Mutability choice: NOT frozen.**
   We deliberately leave the dataclasses mutable (no `frozen=True`). The daemon
   (P1.M4.T1.S1) applies the cuda_check CPU-fallback OVERRIDE by direct
   assignment: `cfg.asr.device = "cpu"; cfg.asr.final_model = "small.en"`. With
   frozen dataclasses that would need `dataclasses.replace(...)` chaining — more
   verbose, no benefit here. (Mirrors `cuda_check.resolve_device_and_models()`
   returning a fresh mutable dict.)

6. **`filter` as a field name shadows the builtin — acceptable here.**
   `VoiceTypingConfig.filter` matches the TOML table key `[filter]` and
   `from_toml`'s `data.get("filter")`. The builtin `filter()` is not used inside
   `config.py`, so the shadow is harmless. ruff (not yet configured in this
   project) does not flag attribute-name shadowing by default. Keep `filter` for
   TOML-key alignment; do NOT rename to `filter_cfg`.

---

## 3. XDG Base Directory — the search order

Spec: https://specifications.freedesktop.org/basedir-spec/latest/
Python platform docs (XDG vars): https://docs.python.org/3.12/library/os.html#os.environ

**PRD §4.5 search order (authoritative):**
`$XDG_CONFIG_HOME/voice-typing/config.toml` → repo `config.toml` → built-in defaults.

**Load-bearing interpretation:**

1. **XDG_CONFIG_HOME fallback.**
   Spec: "If `$XDG_CONFIG_HOME` is either not set or empty, a default equal to
   `$HOME/.config` should be used."
   → `xdg = os.environ.get("XDG_CONFIG_HOME", "").strip() or os.path.expanduser("~/.config")`.
   The `.strip()` handles a whitespace-only value; the `or` handles both unset
   AND empty (spec mandates both → default). Path component is `voice-typing/config.toml`.
   Spec: https://specifications.freedesktop.org/basedir-spec/latest/#variables

2. **XDG_RUNTIME_DIR is DIFFERENT — and may be unset.**
   Spec: "If `$XDG_RUNTIME_DIR` is not set, applications should fall back to a
   replacement ... Applications should warn the user." Critically, XDG_RUNTIME_DIR
   is set by `pam_systemd` for REAL login sessions but is **NOT** set in: cron
   jobs, non-interactive shells, many CI/test contexts, or `uv run` without a
   session. This is exactly why `state_file` resolution must be LAZY (deferred to
   `resolved_state_file()`, not done at `load()` time). Decision: if state_file
   is empty AND XDG_RUNTIME_DIR is unset, `resolved_state_file()` RAISES
   `RuntimeError` with a clear message — there is no safe default path, and
   silently writing to `/tmp/...` or `~` would be a bug.
   Spec: https://specifications.freedesktop.org/basedir-spec/latest/#variables

3. **Repo config path must be module-relative (CWD-independent).**
   `Path(__file__).resolve().parent.parent / "config.toml"`: `config.py`'s dir is
   `voice_typing/`, its parent is the repo root where `config.toml` lives (PRD
   §4.1). This resolves correctly whether the daemon is launched from the repo
   root (systemd `ExecStart`) or elsewhere. Do NOT use a bare `"./config.toml"`
   (CWD-dependent → flaky under systemd). Do NOT hardcode
   `/home/dustin/projects/voice-typing` (not portable).
   NOTE: `config.toml` is NOT packaged in the wheel (`packages=["voice_typing"]`
   in pyproject → only the package dir ships). For installed-package runs the
   repo candidate won't exist — that's fine: install.sh (P1.M6.T1.S1) copies it
   to the XDG candidate (which wins anyway).

4. **First EXISTING file wins; built-ins are the final fallback.**
   `_candidate_paths()` returns `[xdg, repo]`; `load()` iterates and returns on
   the first `os.path.isfile(...)`. If neither exists → `VoiceTypingConfig()`
   (pure dataclass defaults). An explicit `path=` argument BYPASSES the search
   and loads that one file (this is how tests pin a specific file and how a
   future `--config` CLI flag would work).

---

## 4. Test framework decision: pytest as a dev dependency

**Facts:**
- There are NO tests in the repo yet (`find tests/` → none). This is the FIRST
  test module. `tests/test_config.py` is the canonical pure-Python unit-test
  pattern the PRD §4.1 layout establishes (it lists `tests/test_textproc.py`).
- pytest is NOT installed (`.venv/bin/python -c "import pytest"` → ModuleNotFoundError).
- `voice_typing` IS importable (editable install via uv sync): `.venv/bin/python
  -c "import voice_typing"` → resolves to repo's `voice_typing/__init__.py`. So
  tests can `from voice_typing.config import VoiceTypingConfig` with no
  `sys.path` hacks.
- ruff/mypy are NOT installed and NOT configured (no `[tool.ruff]`/`[tool.mypy]`
  in pyproject). Do NOT make them blocking validation gates.

**Decision:** add pytest as a **dev dependency** via
`uv add --dev pytest` (uv 0.7.11 → writes `[dependency-groups] dev = ["pytest"]`
in pyproject.toml + updates uv.lock + installs into `.venv`). Justification:
- This is the FIRST test task; it establishes the runner the WHOLE plan reuses
  (P1.M2.T2.S1 test_textproc, P1.M3.T1.S2 typing-backend tests, P1.M7 test
  suite). Adding it once now is the correct foundation.
- pytest is lightweight (pulls iniconfig/packaging/pluggy/exceptiongroup only;
  `tomli` is pulled but redundant on 3.12 — harmless). ~small install.
- No conflict with the parallel P1.M1.T3.S1: its PRP (read in full) explicitly
  does NOT touch pyproject.toml or uv.lock (its Anti-Patterns: "Don't edit
  pyproject.toml / uv.lock ... No uv sync/uv build/uv add"). So a single
  `uv add --dev pytest` here is the only concurrent writer of those files — safe.

pytest fixtures used by the tests (all built-in):
- `tmp_path` (pytest.Pathy) → temp config files; auto-cleaned.
- `monkeypatch` → set/restore `XDG_CONFIG_HOME`, `XDG_RUNTIME_DIR`, and
  monkeypatch `voice_typing.config._repo_config_path` / `_xdg_config_path` so the
  search-order test is hermetic (doesn't depend on the real repo config.toml,
  which doesn't exist yet during S1 and is created in S2).

Docs: https://docs.pytest.org/en/stable/how-to/tmp_path.html ,
https://docs.pytest.org/en/stable/how-to/monkeypatch.html

**Run command (full paths, no bare python/uv — system_context.md §1):**
`cd /home/dustin/projects/voice-typing && .venv/bin/python -m pytest tests/test_config.py -v`
(`uv run pytest` also works post-`uv add`.)

---

## 5. Scope coupling (do NOT get these wrong)

- **config.py defaults ↔ cuda_check.py model names.** `AsrConfig` defaults
  (`final_model="distil-large-v3"`, `realtime_model="small.en"`, `device="cuda"`)
  MUST equal `cuda_check.CUDA_DEFAULTS["final_model"|"realtime_model"|"device"]`
  (P1.M1.T2.S2). They are the same PRD §4.4/§4.5 values. config.py holds the
  user's DESIRED config; cuda_check decides AVAILABILITY and the daemon
  (P1.M4.T1.S1) APPLIES the override. config.py must NOT import cuda_check (that
  pulls ctranslate2/torch — config stays pure-stdlib). The L2 test asserts these
  string equalities as a drift guard.
- **`compute_type` lives in cuda_check, NOT in config.** PRD §4.5 has no
  `compute_type` key (it's a RealtimeSTT kwarg, §4.4, decided by cuda_check).
  Do NOT add `compute_type` to `AsrConfig`.
- **blocklist is stored VERBATIM.** Lowercasing + trailing-punctuation stripping
  is textproc's job at COMPARE time (PRD §4.7, P1.M2.T2.S1). config.py does not
  transform blocklist. The defaults are already lowercase per §4.5.
- **DOCS (Mode A).** `config.toml` (P1.M2.T1.S2) IS the user-facing config
  reference — its comments document each key. If a default is changed in
  `config.py` here, the matching default + comment in `config.toml` (S2) MUST be
  kept in sync. (This task's defaults ARE the §4.5 defaults, so S2 mirrors them.)

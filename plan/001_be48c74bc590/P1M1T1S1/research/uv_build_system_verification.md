# Research Note — uv build-system behavior (verified for P1.M1.T1.S1)

**Date:** 2026-07-06
**Method:** Throwaway experiments in `/tmp` (the real repo was NOT modified). uv 0.7.11 at `/home/dustin/.local/bin/uv`, Python 3.12.10.
**Purpose:** De-risk the single non-obvious decision in S1 — whether `uv init --bare` + `[project.scripts]` is enough, or whether a `[build-system]` is required.

---

## Finding #1 — `uv init --bare --python 3.12` output

Ran in an empty dir. Result:

```
$ uv init --bare --python 3.12
Initialized project `uv-init-experiment`
```

Files created: **ONLY `pyproject.toml`**. No `.python-version`, no `uv.lock`, no `.venv` change, no sample `main.py`, no `README.md`.

`pyproject.toml` content (verbatim):
```toml
[project]
name = "uv-init-experiment"   # = directory name (dashes preserved)
version = "0.1.0"
requires-python = ">=3.12"    # ← NOTE: not "<3.13"; contract requires editing this
dependencies = []
```

**No `[build-system]` block.** uv classifies the result as a "virtual application", not a buildable package.

→ For the `voice-typing` dir, name would be `voice-typing`. Irrelevant after the authored overwrite (Task 2 sets name explicitly).

---

## Finding #2 (LOAD-BEARING) — `[project.scripts]` are IGNORED without a `[build-system]`

A bare-app pyproject (no build-system) means `uv sync` installs dependencies into the venv but does **not** build/install the project itself, and `[project.scripts]` are **never** turned into `.venv/bin/*` commands. That breaks PRD §4.8 ("installed console-script entry point") and the Phase-2 `hypr-binds.conf` call to `.venv/bin/voicectl`.

**Fix (verified):** add
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["voice_typing"]
```
With this present, `uv sync` (tested with `dependencies = []`, fully offline) **built** `voice_typing` and **created** both wrappers:
```
.venv/bin/voicectl             # executable, shebang -> .venv/bin/python
.venv/bin/voice-typing-daemon  # executable
```
Wrapper body (`voicectl`):
```python
#!/…/.venv/bin/python
import sys
from voice_typing.ctl import main
if __name__ == "__main__":
    sys.exit(main())
```

---

## Finding #3 (LOAD-BEARING) — entry points may target modules that don't exist yet

Experiment 2 had `voice_typing/__init__.py` **only** — no `ctl.py`, no `daemon.py`. Yet `uv sync` built the wheel, installed it, and created both script wrappers with exit code 0.

**Why:** wheel/hatchling entry points are written into `entry_points.txt` and are **not validated** at build or install time. The wrapper's `from voice_typing.ctl import main` runs only when the script is **executed**. So S1 may declare the scripts now; they become functional once `ctl.py`/`daemon.py` land in P1.M5/P1.M4 and a `uv sync` (or install.sh) re-installs the package.

---

## Finding #4 — `uv build` is the correct offline build-soundness gate

`uv sync --no-deps` is **NOT** a valid flag in uv 0.7.11 (`error: unexpected argument '--no-deps'`; only `--no-dev` exists). So there is no "build project, skip deps" via `uv sync`.

Instead, `uv build` builds an sdist + wheel in an **isolated** environment that installs **only** the build-backend (`hatchling`) — never `realtimestt`/cuda/torch. Verified output with the full 4-dep `pyproject.toml`:
```
Building source distribution...
Building wheel from source distribution...
Successfully built dist/voice_typing-0.1.0.tar.gz
Successfully built dist/voice_typing-0.1.0-py3-none-any.whl
```

Wheel `entry_points.txt`:
```ini
[console_scripts]
voice-typing-daemon = voice_typing.daemon:main
voicectl = voice_typing.ctl:main
```

Wheel `METADATA` (excerpt):
```
Requires-Python: <3.13,>=3.12
Requires-Dist: huggingface-hub>=0.23
Requires-Dist: nvidia-cublas-cu12
Requires-Dist: nvidia-cudnn-cu12==9.*
Requires-Dist: realtimestt
```

Notes:
- `huggingface_hub` (underscore, as written) normalizes to `huggingface-hub` (PEP 503) in metadata — same package, both resolve.
- `nvidia-cudnn-cu12==9.*` is preserved verbatim — valid PEP 440 prefix match.
- `dist/` is already gitignored; safe to `rm -rf dist/` after the check.

---

## Finding #5 — stdlib `tomllib` parse + `import voice_typing` both work with no install

- `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` → parses (Python 3.11+ stdlib; 3.12.10 OK). No deps, no network.
- `python -c "import voice_typing"` from repo root → succeeds. (`python -c` puts cwd on `sys.path[0]`.) Validates package placement without any install.

These two + `uv build` (Finding #4) form the deterministic, network-light S1 validation triplet (PRP Validation L1–L3).

---

## Implications encoded in the PRP

| Behavior | PRP section |
|---|---|
| `uv init --bare` stub has no build-system & `>=3.12` only | Gotcha #1, #3; Task 2 overwrites both |
| `[build-system]` hatchling required for scripts | Gotcha #1; Task 2; Validation L3 |
| Lazy entry-point resolution (modules may be absent) | Gotcha #2; Task 2 note; Integration Points |
| `uv sync --no-deps` invalid → use `uv build` | Gotcha #7; Validation L3 |
| cuDNN `==9.*` mandatory | Gotcha #4; Task 2; Validation L1 |
| No torch in S1 | Gotcha #5; Success Criteria |
| Full paths everywhere | Gotcha #6; all command blocks |

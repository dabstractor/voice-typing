# Research Note: adding the evdev dependency (P1.M1.T1.S2)

**Status:** EMPIRICALLY RE-VERIFIED against the live repo + live PyPI on July 19 2026.
**Purpose:** Pin the current pyproject/lock state, the evdev version situation (the architecture note is now stale), and the exact verification commands.

---

## §1. Live state (re-verified)

- `pyproject.toml` `[project]` dependencies at **:9-13** (matches the contract's citation): `realtimestt[faster-whisper,silero-vad]`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12==9.*`, `huggingface_hub>=0.23`. `[project.scripts]` voicectl + voice-typing-daemon (:16-18). `[tool.hatch...] packages=["voice_typing"]` (:20-21). `[dependency-groups] dev = ["pytest>=9.1.1"]` (:23-26). **`evdev` is NOT present.**
- `uv.lock` EXISTS (97,460 bytes, mtime Jul 7 — 12 days stale; `grep -c 'name = "evdev"'` → 0).
- `.venv/bin/python` = 3.12.10; `/home/dustin/.local/bin/uv` = **0.7.11**.
- **Probe: `import evdev` → `ModuleNotFoundError: No module named 'evdev'`** — confirms NOT importable (the precondition).

## §2. THE VERSION DISCREPANCY — external_deps.md is STALE on the version

- external_deps.md §1 says latest evdev = **1.9.3 (Feb 2025)**. **LIVE PyPI probe today: latest = 2.0.0 (Aug 23, 2026)**, `requires_python: >=3.11` (still compatible with 3.12.10).
- The contract's command is **unpinned**: `/home/dustin/.local/bin/uv add evdev` (mirrors PRD §5 step 4 verbatim). → it will resolve **2.0.0**, not 1.9.3. The "1.9.3" in the contract/notes is stale CONTEXT, not a pin. **Do not pin to 1.9.3 by default** — the PRD install step and the contract both specify unpinned `evdev`.
- Verification is version-agnostic: `import evdev; print(evdev.__version__)` must succeed (whatever it prints — expected 2.0.0).

## §3. evdev 2.0.0 packaging facts (from the live PyPI JSON)

- `requires_dist: None` → **ZERO runtime dependencies** (standalone package). The lock diff should contain evdev and nothing else.
- **files: `['evdev-2.0.0.tar.gz']` → 2.0.0 ships sdist ONLY (no wheels).** Installing it **compiles a small C extension** (uv builds it in isolation; needs `gcc` — present on this Arch box, which also has cargo/go tooling). This is the ONE operational surprise vs the note's 1.9.3-era "wheels" assumption.
- **Documented contingency (NOT the default):** if the sdist build fails on this machine, fall back to `uv add "evdev==1.9.3"` (the research-note-era release, which shipped wheels) and record the pin. Do not reach for this unless the unpinned add actually fails.

## §4. 2.0.0 changelog vs the downstream listener's API surface (P1.M2.T7.S2)

Changelog (live fetch) for 2.0.0 — checked against every call the listener will use:
- `upload_effect` writeback-id change — **irrelevant** (force-feedback, not used).
- **`InputDevice(..., readonly=...)` ADDED** — opens without attempting O_RDWR. This is a BONUS for the passive listener (external_deps.md §1 noted InputDevice opens O_RDWR by default; `readonly` matches the never-grab/passive intent of PRD §4.2quater even better).
- `list_devices(..., writable=...)` / `is_device(..., writable=...)` params ADDED — additive; plain `list_devices()` still works.
- free-threaded-mode support, asyncio deprecations fixed, min-Python 3.11, UInput EV_REP — none break `list_devices/InputDevice/capabilities/read_loop/ecodes`.
- → **No breaking change to the API surface P1.M2.T7.S2 consumes.** Downstream note: prefer `InputDevice(path, readonly=True)`-style opening if desired (2.0.0+ only — do NOT use it in code that must also run on 1.9.3; the fallback pin in §3 makes 2.0.0 the expected runtime, so readonly is available).

## §5. Lock/uv behavior gotchas (uv 0.7.11)

- `uv add evdev` does: (1) append `evdev` to `[project]` dependencies, (2) re-lock, (3) sync `.venv` (also rebuilds the `voice_typing` package — harmless; **wheel building does NOT import the package**, so S1's parallel config-schema edits and its intentional downstream breakage cannot affect the build).
- **Incremental resolution**: uv reuses the existing lock for existing packages, so the uv.lock diff should show evdev (+ nothing else — evdev has no deps). If the diff shows *unexpected version bumps* of existing packages, investigate before accepting (stale-lock re-resolution anomaly), don't blind-commit.
- No FILE overlap with S1 (which owns config.py/config.toml/tests/test_config*.py). S2 touches only pyproject.toml + uv.lock + .venv.
- `UV_HTTP_TIMEOUT`: evdev's sdist is tiny (~100 KB) and the existing tree resolves from the lock/cache, so the default 30 s is fine here — but exporting `UV_HTTP_TIMEOUT=300` is free insurance (this repo historically hit the 30 s default on multi-hundred-MB wheels).

## §6. AGENTS.md discipline (this repo's standing rules)

- **Two timeouts** on every non-trivial command: inner `timeout 120` around `uv add` (per contract), bash-tool timeout above that; `timeout 30` around the import probe.
- Full path `/home/dustin/.local/bin/uv` (zsh aliases python3→uv run); `.venv/bin/python` explicitly.
- **No daemon runs, no pytest** for this subtask (per contract) — note S1's parallel work INTENTIONALLY leaves daemon-side suites red until P1.M1.T2; that is not S2's gate and must not be "investigated" here.

## SUMMARY

1. ✅ Preconditions confirmed: deps at :9-13, no evdev anywhere, lock exists (stale), venv 3.12.10, uv 0.7.11.
2. ⚠️ **Version discrepancy**: latest is 2.0.0 (sdist-only, C-compile), NOT the note's 1.9.3. Contract command is UNPINNED → expect 2.0.0. Contingency pin `==1.9.3` only if the build fails.
3. ✅ evdev has zero runtime deps → lock diff should be evdev-only.
4. ✅ 2.0.0 is API-compatible with the downstream listener (additive `readonly`/`writable` params are a bonus).
5. ✅ No file overlap with S1; uv add's package rebuild is import-free and safe.
6. ⚠️ AGENTS.md: timeouts, full paths, no daemon, no pytest (S1's transitional red suites are expected).

# S3 Research Findings — Verify config search-order & XDG resolution path

## 0. Task restatement (one line)

Trace `_candidate_paths()` order and verify `_xdg_config_path()` /
`_repo_config_path()` / `VoiceTypingConfig.load()` implement the PRD §4.5 search order
(`$XDG_CONFIG_HOME/voice-typing/config.toml` → repo `config.toml` → built-in defaults),
run the dedicated search-order tests, and APPEND a pass/fail section to
`plan/006_862ee9d6ef41/architecture/gap_config.md`. Distinct from S1 (field/default
compliance) and S2 (lockstep/blocklist/Mode-A doc).

## 1. The functions under audit (live line numbers, grep-verified)

`voice_typing/config.py` exposes four module-level helpers + one classmethod + one
module-level wrapper:

| Function | config.py line | Behavior |
|---|---|---|
| `VoiceTypingConfig.load(path=None)` | 262 (def); `return cls()` defaults @276 | explicit path → `from_toml_file(path)` (bypasses search); else iterate `_candidate_paths()`, return FIRST existing; else `cls()` (built-in dataclass defaults) |
| `_xdg_config_path()` | 283 (def); body 285-288 | `XDG_CONFIG_HOME` (stripped); unset/empty → `~/.config`; returns `<base>/voice-typing/config.toml` |
| `_repo_config_path()` | 291 (def); `return` @298 | `Path(__file__).resolve().parent.parent / "config.toml"` = repo root config.toml (module-relative, CWD-independent) |
| `_candidate_paths()` | 301 (def); `return` @303 | `[_xdg_config_path(), _repo_config_path()]` — **XDG first, repo second** |
| `load(path=None)` (module-level wrapper) | 306 (def) | thin wrapper over `VoiceTypingConfig.load()` |

The helpers are MODULE-LEVEL (not methods) specifically so tests can `monkeypatch` them
for hermeticity (the test docstring at test_config.py:289 confirms this design).

## 2. LIVE VERIFICATION (executed — transcribe into the gap_config.md section)

### 2.1 `_candidate_paths()` order = [XDG, repo] ✓

```
>>> _candidate_paths()  # abridged
['.../voice-typing/config.toml'  (XDG),
 '/home/dustin/projects/voice-typing/config.toml'  (repo)]
```
- `[0]` is XDG-derived (ends `voice-typing/config.toml` under the XDG base).
- `[1]` is the repo config.toml (`Path(__file__).parent.parent`), which EXISTS.
- **Matches PRD §4.5 order: XDG first, repo second.** PASS.

### 2.2 `_xdg_config_path()` resolution ✓

| `XDG_CONFIG_HOME` | resolved path |
|---|---|
| set `/custom/xdg` | `/custom/xdg/voice-typing/config.toml` |
| unset | `/home/dustin/.config/voice-typing/config.toml` (= `~/.config/...`) |
| empty `""` | `/home/dustin/.config/voice-typing/config.toml` |
| whitespace `"   "` | `/home/dustin/.config/voice-typing/config.toml` (the `.strip()` → fallback) |

- The `os.environ.get("XDG_CONFIG_HOME", "").strip()` (config.py:285) + `if not xdg_config:`
  fallback to `os.path.expanduser("~/.config")` (286-287) + `os.path.join(base,
  "voice-typing", "config.toml")` (288) implement EXACTLY the PRD §4.5 resolution:
  `$XDG_CONFIG_HOME/voice-typing/config.toml`, or `~/.config/voice-typing/config.toml` when
  unset/empty.
- **PASS.** (Nuance: `.strip()` also collapses whitespace-only values to the fallback —
  strictly MORE robust than the PRD literal text requires, and correct per the XDG Base
  Directory Specification's intent that an invalid/empty value defaults to `$HOME/.config`.)

### 2.3 `_repo_config_path()` ✓

- `str(Path(__file__).resolve().parent.parent / "config.toml")` (config.py:298) resolves
  to `/home/dustin/projects/voice-typing/config.toml` and `os.path.isfile(...)` → **True**.
- Module-relative → resolves correctly regardless of CWD (systemd's ExecStart, a manual run,
  pytest from the repo — all get the same path). This matches the design note (config.py:292-297):
  config.toml is NOT packaged in the wheel (`packages=["voice_typing"]`), so for pip-installed
  runs this candidate won't exist — `install.sh` copies it to XDG (which is then candidate #1).
- **PASS.**

### 2.4 `load()` defaults fallback ✓

- With BOTH candidates pointed at nonexistent paths (monkeypatched), `VoiceTypingConfig.load(None)`
  → `cls()` (the `return cls()  # built-in defaults` at config.py:276) == `VoiceTypingConfig()`.
- **PASS** — no exception; pure dataclass defaults. Matches PRD §4.5 "built-in defaults" tier.
- (Verified live: `cfg == VoiceTypingConfig()` → True.)

## 3. Test coverage — 7 dedicated search-order tests (all PASS)

`tests/test_config.py` (pure-Python, no CUDA) has 7 tests directly covering the search-order
path logic (line numbers grep-verified):

| Test | test_config.py line | Asserts |
|---|---|---|
| `test_load_with_explicit_path_bypasses_search` | 280 | explicit `path=` skips the search (loads that one file) |
| `test_search_order_xdg_wins_over_repo` | 289 | XDG candidate wins when BOTH exist (PRD §4.5 precedence) |
| `test_search_order_repo_used_when_xdg_absent` | 301 | repo candidate used when XDG file missing |
| `test_search_order_missing_file_falls_back_to_defaults` | 311 | no candidate → built-in dataclass defaults |
| `test_xdg_config_path_falls_back_to_home_when_unset` | 319 | XDG unset → `~/.config/voice-typing/config.toml` (real env, real function) |
| `test_xdg_config_path_respects_env` | 326 | XDG set → used verbatim + `voice-typing/config.toml` suffix |
| `test_module_level_load_matches_classmethod` | 359 | module-level `load()` == `VoiceTypingConfig.load()` |

Live run: `pytest tests/test_config.py -q -k "search_order or load_with_explicit or xdg_config_path or module_level_load or missing_file_falls"` → **7 passed, 27 deselected**.
Full config suite: `pytest tests/test_config.py tests/test_config_repo_default.py -q` → **37 passed**
(34 in test_config.py + 3 in test_config_repo_default.py — matches S1/S2's count).

The tests use `monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: ...)` /
`"_repo_config_path"` (test_config.py:295-297, 307-308, 317-318) to make the search-order
assertions hermetic — they don't depend on the machine's real XDG_CONFIG_HOME or on the repo
config.toml existing. This is exactly why the helpers are module-level (not methods).

## 4. CONCLUSION — ALL PASS, no fix needed

The search-order & XDG resolution logic is fully PRD §4.5-compliant and well-tested:
- `_candidate_paths()` order = [XDG, repo] ✓ (PRD §4.5 precedence)
- `_xdg_config_path()` resolves set/unset/empty correctly ✓
- `_repo_config_path()` is module-relative + exists ✓
- `load()` falls back to dataclass defaults when no candidate exists ✓
- 7 dedicated tests pass (37 total) ✓

**No code changes required.** S3 records the pass/fail in an appended gap_config.md section.

## 5. The APPEND target — gap_config.md state (live, pre-S3)

`plan/006_862ee9d6ef41/architecture/gap_config.md` EXISTS (384 lines):
- S1's report: sections §1-8 (lines 1-234) — field/default compliance, VT-006, validation logic.
- S2's section: `## Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)` (line 235 → ~384) —
  already present (S2 landed it).
- **S3 APPENDS its section at EOF** (after S2's section). If S2's section were somehow absent
  (race), S3 still appends at EOF (after S1's §8 Conclusion) — robust either way.

## 6. Scope boundary (distinct from S1/S2)

- S1 = field/default PRD §4.5 **compliance** (does config.py match the PRD schema?).
- S2 = config.toml ↔ config.py **lockstep** (drift) + blocklist correctness + Mode A doc accuracy.
- S3 = **search-order & XDG resolution path** (does `load()` find the right file in the right
  order? does `_xdg_config_path()` resolve correctly?).

S3 does NOT re-derive S1's field table or S2's lockstep result. It appends a focused
search-order section. No config.py / config.toml / test edits (no defect found).

## 7. Anti-patterns to avoid

- ❌ Don't duplicate S1's field table or S2's lockstep result — S3 is path-resolution only.
- ❌ Don't flag the `.strip()` (whitespace → fallback) as a defect — it's more robust than the
  PRD literal requires, and correct per XDG spec intent.
- ❌ Don't flag the absence of a relative-XDG_CONFIG_HOME check — the PRD doesn't require it; the
  XDG spec says the var should be absolute but doesn't mandate rejection of relative values.
- ❌ Don't flag the repo candidate as "won't exist for pip installs" — that's by DESIGN
  (config.toml isn't packaged; install.sh copies it to XDG, which is candidate #1). Documented
  at config.py:292-297.
- ❌ Don't OVERWRITE gap_config.md — APPEND the S3 section. S1 + S2 content must remain intact.
- ❌ Don't edit config.py / config.toml / tests — no defect found. Source edits are the
  unexpected branch only (which is not triggered here).
- ❌ Don't invoke ruff/mypy (not configured). Use `.venv/bin/python -m pytest`.
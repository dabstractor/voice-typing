name: "P1.M1.T1.S3 — Verify config search-order & XDG resolution path"
description: |

---

## Goal

**Feature Goal**: Verify that `voice_typing/config.py`'s config-discovery logic — `_xdg_config_path()`, `_repo_config_path()`, `_candidate_paths()`, and `VoiceTypingConfig.load()` — implements the PRD §4.5 search order **exactly**: `$XDG_CONFIG_HOME/voice-typing/config.toml` → repo `config.toml` → built-in dataclass defaults (first existing file wins; explicit `path=` bypasses the search). Record the result by **appending a Search-Order & XDG Resolution section to S1/S2's `gap_config.md`**. This is a **verification/audit** subtask: the deliverable is the recorded result; code changes happen ONLY if a real defect is found (none exists).

**Deliverable**: An appended section (`## Search-Order & XDG Resolution Verification (P1.M1.T1.S3)`) in `plan/006_862ee9d6ef41/architecture/gap_config.md` recording: (a) the `_candidate_paths()` order check; (b) the `_xdg_config_path()` resolution check (set / unset / empty); (c) the `_repo_config_path()` module-relative check; (d) the `load()` defaults-fallback check; (e) the 7 dedicated search-order test results; (f) the conclusion (all pass → no fix). No source changes expected.

**Success Definition**:
- (a) `gap_config.md` contains the appended S3 search-order section with all required findings, citing config.py file:line for every claim.
- (b) The recorded findings match the live verification: `_candidate_paths()` == `[_xdg_config_path(), _repo_config_path()]` (XDG first); `_xdg_config_path()` resolves set→`$XDG/voice-typing/config.toml` and unset/empty→`~/.config/voice-typing/config.toml`; `load(None)` with no candidates → `VoiceTypingConfig()` (defaults); 7 search-order tests pass; full suite → **37 passed**.
- (c) **No source files are modified** (because no defect exists — the search-order logic is fully PRD §4.5-compliant).
- (d) S3 does NOT duplicate S1's field-compliance table or S2's lockstep section (it appends a distinct path-resolution section).

> **Scope note:** this is a pure-Python verification (config.py loads in CPU-only/test contexts; the tests have no CUDA/network/audio dependency). The AGENTS.md timeout/hang rules do NOT apply here — these commands return in milliseconds.

## User Persona

**Target User**: The verification round's orchestrator + future maintainers who need an evidence-backed record that the daemon finds its config file via the correct, PRD-mandated precedence — and falls back to safe defaults when none exists.

**Use Case**: Reviewing `gap_config.md` to confirm the config-discovery path is correct before declaring the config audit (S1+S2+S3) complete. A future change to `_candidate_paths()` order or `_xdg_config_path()` resolution would be caught by the 7 tests S3 cites.

**Pain Points Addressed**: A wrong search order (e.g. repo-before-XDG, or XDG unset resolving to a wrong path) would silently load the wrong config or — worse — fail to find a user override. S3 closes the "does the loader find the right file?" question with recorded evidence.

## Why

- **Verification round mandate.** This round is "verification, gap-analysis, and remediation — NOT greenfield build." S3 confirms the existing config-discovery logic matches PRD §4.5 before relying on it.
- **Distinct from S1 and S2.** S1 = PRD §4.5 field/default **compliance**. S2 = config.toml↔config.py **lockstep** + blocklist + Mode A doc. S3 = **search-order & path resolution** (which file is found, in what order, and what happens when none exists). All three are needed; none subsumes the others.
- **Lowest-risk outcome.** The live verification (this PRP's author) finds the search-order logic fully compliant → no code changes → zero regression risk.
- **The "fail-safe defaults" guarantee.** PRD §4.5 tier 3 ("built-in dataclass defaults") is the safety net when no config file exists (e.g. a fresh checkout with no XDG copy, or a test context). S3 verifies `load()` reaches `cls()` cleanly with no exception — a silent failure here would mean the daemon crashes on a configless boot.

## What

Trace `_candidate_paths()` and verify each resolution helper against PRD §4.5; run the 7 dedicated search-order tests + the full config suite; append the result to `gap_config.md`. **No code changes expected** (the audit finds all-compliant). If — and only if — the re-verification surfaces a REAL defect (e.g. wrong candidate order, wrong XDG fallback path, `load()` raising instead of returning defaults), fix it in config.py and record the fix; otherwise record "none — search-order logic is PRD §4.5-compliant per audit."

### Success Criteria

- [ ] `.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q` → 37 passed (reproduced).
- [ ] `.venv/bin/python -m pytest tests/test_config.py -q -k "search_order or load_with_explicit or xdg_config_path or module_level_load or missing_file_falls"` → 7 passed (the dedicated search-order subset).
- [ ] `_candidate_paths()` returns `[_xdg_config_path(), _repo_config_path()]` (XDG first, repo second — PRD §4.5 order).
- [ ] `_xdg_config_path()` set → `$XDG/voice-typing/config.toml`; unset/empty → `~/.config/voice-typing/config.toml`.
- [ ] `load(None)` with no existing candidate → `VoiceTypingConfig()` (built-in defaults, no exception).
- [ ] `gap_config.md` has the appended S3 search-order section citing config.py:line for every claim.
- [ ] No source files modified (config.py/config.toml/tests unchanged) UNLESS a real defect is found (not expected).

## All Needed Context

### Context Completeness Check

_Pass._ This PRP's author has already executed the full verification against the live code; every finding below is verified with the exact command and value (see "VERIFIED FINDINGS"). The implementing agent re-runs the commands to confirm, then transcribes the results into the appended section. No further investigation is required.

### VERIFIED FINDINGS (already performed — transcribe into the gap_config.md section)

**1. `_candidate_paths()` order = [XDG, repo] ✓** (config.py:301-303)
```python
def _candidate_paths() -> list[str]:
    """Ordered search candidates: XDG first, then repo. Defaults are the fallback."""
    return [_xdg_config_path(), _repo_config_path()]
```
Live dump: `[0]` is the XDG-derived path (ends `voice-typing/config.toml` under the XDG base); `[1]` is the repo config.toml (`/home/dustin/projects/voice-typing/config.toml`), which `os.path.isfile` → True. **Matches PRD §4.5 precedence: XDG first, repo second.**

**2. `_xdg_config_path()` resolution ✓** (config.py:283-288)
```python
def _xdg_config_path() -> str:
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()   # :285 — .strip() collapses whitespace
    if not xdg_config:                                            # :286
        xdg_config = os.path.expanduser("~/.config")             # :287
    return os.path.join(xdg_config, "voice-typing", "config.toml")  # :288
```
| `XDG_CONFIG_HOME` | resolved |
|---|---|
| set `/custom/xdg` | `/custom/xdg/voice-typing/config.toml` |
| unset | `/home/dustin/.config/voice-typing/config.toml` |
| empty `""` | `/home/dustin/.config/voice-typing/config.toml` |
| whitespace `"   "` | `/home/dustin/.config/voice-typing/config.toml` |

**Matches PRD §4.5:** `$XDG_CONFIG_HOME/voice-typing/config.toml`, or `~/.config/voice-typing/config.toml` when unset/empty. (The `.strip()` → fallback for whitespace-only is strictly MORE robust than the PRD literal text requires; correct per the XDG Base Directory Specification's intent.)

**3. `_repo_config_path()` ✓** (config.py:291-298)
```python
def _repo_config_path() -> str:
    # voice_typing/config.py → parent = voice_typing/ → parent = repo root.
    return str(Path(__file__).resolve().parent.parent / "config.toml")   # :298
```
Resolves to `/home/dustin/projects/voice-typing/config.toml`; exists. **Module-relative → CWD-independent** (systemd ExecStart, manual run, pytest all resolve identically). config.toml is NOT packaged in the wheel (`packages=["voice_typing"]`), so for pip-installed runs this candidate won't exist — `install.sh` copies it to XDG (candidate #1). This is by design (config.py:292-297).

**4. `load()` defaults fallback ✓** (config.py:262-281; `return cls()` @276)
```python
@classmethod
def load(cls, path=None):
    if path is not None:
        return cls.from_toml_file(path)        # explicit path bypasses search
    for candidate in _candidate_paths():        # first EXISTING file wins
        if os.path.isfile(candidate):
            return cls.from_toml_file(candidate)
    return cls()  # built-in defaults           # :276 — tier 3 fallback
```
Live: with both candidates monkeypatched to nonexistent paths, `VoiceTypingConfig.load(None) == VoiceTypingConfig()` → **True** (no exception; pure dataclass defaults). **Matches PRD §4.5 tier 3.**

**5. Test coverage — 7 dedicated search-order tests, all PASS** (tests/test_config.py):

| Test | line | Asserts |
|---|---|---|
| `test_load_with_explicit_path_bypasses_search` | 280 | explicit `path=` skips the search |
| `test_search_order_xdg_wins_over_repo` | 289 | XDG wins when BOTH exist (precedence) |
| `test_search_order_repo_used_when_xdg_absent` | 301 | repo used when XDG file missing |
| `test_search_order_missing_file_falls_back_to_defaults` | 311 | no candidate → dataclass defaults |
| `test_xdg_config_path_falls_back_to_home_when_unset` | 319 | XDG unset → `~/.config/voice-typing/config.toml` (real env + real fn) |
| `test_xdg_config_path_respects_env` | 326 | XDG set → used verbatim + suffix |
| `test_module_level_load_matches_classmethod` | 359 | module-level `load()` == classmethod |

Live: `-k` filter → **7 passed, 27 deselected**. Full suite → **37 passed** (34 test_config.py + 3 test_config_repo_default.py). The tests use `monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: ...)` / `"_repo_config_path"` for hermeticity — exactly why the helpers are module-level (not methods).

**6. CONCLUSION:** The search-order & XDG resolution logic is fully PRD §4.5-compliant and well-tested. **No code changes required.**

### Documentation & References

```yaml
# THE SPEC
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: §4.5 "Config file search order: $XDG_CONFIG_HOME/voice-typing/config.toml, then repo
       config.toml, then built-in defaults" is the authoritative requirement S3 verifies.
  critical: "PRD §4.5 says 'unset/empty → ~/.config'. config.py also strips whitespace (more robust).
            Do NOT call the .strip() a defect — it's correct per XDG-spec intent."

# THE CODE UNDER AUDIT
- file: voice_typing/config.py
  why: The four functions under audit: VoiceTypingConfig.load (262, defaults-return @276),
        _xdg_config_path (283-288), _repo_config_path (291-298), _candidate_paths (301-303),
        module-level load wrapper (306). The module docstring (8-12) documents the search order.
  pattern: "Helpers are MODULE-LEVEL (not methods) so tests can monkeypatch them for hermeticity.
            load() iterates _candidate_paths() and returns the first isfile() hit; else cls()."
  gotcha: "config.toml is NOT in the wheel (packages=['voice_typing']); the repo candidate only
           exists for git checkouts. install.sh copies it to XDG (candidate #1). By design (292-297)."

# THE TESTS (the proof)
- file: tests/test_config.py
  why: 7 search-order tests (lines 280/289/301/311/319/326/359) directly cover path resolution.
        monkeypatch.setattr on _xdg_config_path/_repo_config_path makes them hermetic.
  critical: "test_xdg_config_path_falls_back_to_home_when_unset (319) + test_xdg_config_path_
            respects_env (326) exercise the REAL _xdg_config_path with real env manipulation —
            they are the direct proof of the XDG resolution contract, not just a monkeypatched stub."

# THE APPEND TARGET
- file: plan/006_862ee9d6ef41/architecture/gap_config.md
  why: S1 created this report (field/default compliance, §1-8); S2 appended its lockstep section
        (## Lockstep & Mode-A Doc Verification, ~line 235). S3 APPENDS its search-order section at
        EOF. The three sections together form the complete config audit.
  critical: "APPEND only — do NOT overwrite S1/S2 content. S3's section is distinct (path resolution)."

# THE PREVIOUS/SIBLING PRPs (the contract chain)
- file: plan/006_862ee9d6ef41/P1M1T1S1/PRP.md
  why: S1 created gap_config.md (the report S3 appends to). S1 = field/default PRD compliance.
       S3 must not duplicate S1's table.
- file: plan/006_862ee9d6ef41/P1M1T1S2/PRP.md
  why: S2 (in parallel) appended the lockstep section to gap_config.md. S2 = drift + blocklist + Mode A.
       S3 must not duplicate S2's section. (S2's section is already present in the live gap_config.md.)

# THIS SUBTASK'S OWN RESEARCH NOTE
- docfile: plan/006_862ee9d6ef41/P1M1T1S3/research/search_order_findings.md
  why: §2 the live verification (candidate order, xdg resolution table, repo path, defaults fallback);
       §3 the 7-test coverage map; §5 the gap_config.md APPEND shape; §6 the S1/S2/S3 distinction.
  section: "§2 (live verification) and §3 (test coverage) are load-bearing."

# THE PROJECT CONTEXT
- docfile: plan/006_862ee9d6ef41/architecture/system_context.md
  why: States this round is verification/gap-analysis, not greenfield. Confirms S3's scope (verify,
       don't rebuild). Config layer is "Fully implemented."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/config.py          # load()@262 + _xdg_config_path@283 + _repo_config_path@291 + _candidate_paths@301   ← AUDIT (read-only)
├── tests/test_config.py            # 7 search-order tests (280/289/301/311/319/326/359)                                 ← RUN (read-only)
├── tests/test_config_repo_default.py  # drift guard (config.py↔config.toml)                                             ← RUN (read-only)
├── config.toml                     # repo default (the repo candidate _repo_config_path() resolves to)                ← AUDIT (read-only)
└── plan/006_862ee9d6ef41/architecture/
    └── gap_config.md               # S1 §1-8 + S2 lockstep section ← S3 APPENDS its search-order section here
```

### Desired Codebase tree with files to be changed

```bash
plan/006_862ee9d6ef41/architecture/gap_config.md   # MODIFY: APPEND the "## Search-Order & XDG Resolution Verification (P1.M1.T1.S3)" section.
# NO source changes expected (no defect found). config.py/config.toml/tests UNCHANGED.
# (Only if the re-verification finds a REAL defect — wrong order, wrong path, load() raising — would
#  config.py be edited + the fix recorded. Expected: this branch is NOT taken.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — S3 ≠ S1 ≠ S2. S1 = field/default PRD compliance; S2 = lockstep + blocklist + Mode A;
# S3 = search-order & XDG resolution. Do NOT duplicate S1's table or S2's section. APPEND a focused
# path-resolution section to gap_config.md.

# CRITICAL #2 — THE HELPERS ARE MODULE-LEVEL ON PURPOSE (not methods), so tests can monkeypatch them.
# _xdg_config_path / _repo_config_path / _candidate_paths are module-level functions; load() is both a
# VoiceTypingConfig classmethod (262) and a module-level wrapper (306). The tests monkeypatch the
# module-level helpers (test_config.py:295-297) for hermetic search-order assertions. Do NOT "refactor"
# them into methods — it would break the tests' monkeypatching.

# CRITICAL #3 — THE .strip() ON XDG_CONFIG_HOME IS NOT A DEFECT. config.py:285 does
# os.environ.get("XDG_CONFIG_HOME","").strip() — a whitespace-only value collapses to "" → falls back
# to ~/.config. This is MORE robust than PRD §4.5's literal "unset/empty" wording and is correct per
# the XDG Base Directory Specification (an invalid/whitespace value should default to $HOME/.config).
# Record it as robust-by-design, NOT a gap.

# CRITICAL #4 — THE REPO CANDIDATE WON'T EXIST FOR PIP INSTALLS — BY DESIGN. config.toml is NOT
# packaged (packages=["voice_typing"]); _repo_config_path() (298) resolves to the repo-root config.toml,
# which only exists for git checkouts. install.sh copies it to XDG (candidate #1). For a pip-installed
# run with no XDG copy, load() falls through to tier-3 defaults (cls()). Documented at config.py:292-297.
# Do NOT flag this as a defect.

# GOTCHA #5 — NO RELATIVE-XDG CHECK EXISTS, AND THAT'S OK. The XDG spec says XDG_CONFIG_HOME should be
# absolute, but config.py does not reject a relative value. The PRD does NOT require relative-path
# rejection. This is a theoretical edge case (no real user sets a relative XDG_CONFIG_HOME); do NOT flag
# it as a gap or add validation — it's out of scope and would be gold-plating.

# GOTCHA #6 — load() WITH NO CANDIDATE RETURNS cls(), IT DOES NOT RAISE. This is the PRD §4.5 tier-3
# "built-in defaults" guarantee — a configless boot (fresh checkout, no XDG copy, test context) must
# NOT crash. The verification confirms load(None) with nonexistent candidates == VoiceTypingConfig().
# This is the load-bearing safety property; record it explicitly.

# GOTCHA #7 — APPEND, DON'T OVERWRITE gap_config.md. It carries S1 (§1-8) + S2 (lockstep section).
# APPEND the S3 section at EOF. The three sections together = the complete config audit. If gap_config.md
# did NOT exist (it does), create a minimal one with a pending-S1/S2 placeholder — but it DOES exist, so
# just append.

# GOTCHA #8 — REPORT-FIRST. The deliverable is the appended section. Do NOT edit config.py/config.toml/
# tests unless the re-verification finds a REAL defect (wrong order, wrong path, load() raising). If all
# compliant (expected), record "none — search-order logic is PRD §4.5-compliant per audit."

# GOTCHA #9 — FULL-PATH DISCIPLINE + NO TIMEOUT NEEDED. Machine aliases python3->uv run; use
# .venv/bin/python for the dump + .venv/bin/python -m pytest for tests. These are pure-Python (config.py
# loads in CPU/test contexts; no CUDA/network/audio) and return in milliseconds — the AGENTS.md
# daemon/voicectl timeout rules do NOT apply. No ruff/mypy in this project.
```

## Implementation Blueprint

### Data models and structure

This task audits path-resolution logic; it does not change data models. Under audit: `_candidate_paths() -> list[str]` (returns `[xdg, repo]`), `_xdg_config_path() -> str`, `_repo_config_path() -> str`, `VoiceTypingConfig.load(path=None) -> VoiceTypingConfig`, and the module-level `load()` wrapper. No dataclass changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the search-order logic (reproduce the findings; do not trust them blindly).
  - RUN the search-order subset + full config suite:
        .venv/bin/python -m pytest tests/test_config.py -q \
          -k "search_order or load_with_explicit or xdg_config_path or module_level_load or missing_file_falls"
        .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q
    EXPECT: 7 passed (subset); 37 passed (full).
  - RUN the live resolution dump:
        .venv/bin/python - <<'PY'
        import os
        from voice_typing import config as c
        from voice_typing.config import VoiceTypingConfig, _candidate_paths, _repo_config_path
        # 1. candidate order
        print("candidate order:", _candidate_paths())
        print("  repo candidate exists:", os.path.isfile(_repo_config_path()))
        # 2. xdg resolution (set/unset/empty/whitespace)
        for label, v in [("set", "/custom/xdg"), ("unset", None), ("empty", ""), ("ws", "   ")]:
            if v is None: os.environ.pop("XDG_CONFIG_HOME", None)
            else: os.environ["XDG_CONFIG_HOME"] = v
            print(f"  XDG {label:5} -> {c._xdg_config_path()}")
        os.environ.pop("XDG_CONFIG_HOME", None)
        # 3. load() defaults fallback (point both candidates nowhere)
        ox, orc = c._xdg_config_path, c._repo_config_path
        c._xdg_config_path = lambda: "/no/xdg.toml"
        c._repo_config_path = lambda: "/no/repo.toml"
        try:
            print("load(None) no candidates == defaults:", VoiceTypingConfig.load(None) == VoiceTypingConfig())
        finally:
            c._xdg_config_path, c._repo_config_path = ox, orc
        PY
    EXPECT: order [xdg, repo]; repo exists; XDG set/unset/empty/ws resolve as in the findings table;
            load(None) == defaults → True.
  - If ANY check differs from the findings above, INVESTIGATE before writing the section (the tree may
    have moved; reconcile the report with what you observe). A real defect would be: wrong candidate
    order, XDG unset resolving somewhere other than ~/.config/voice-typing/config.toml, or load(None)
    raising instead of returning defaults. (Expected: none of these occur.)

Task 2: APPEND the S3 section to plan/006_862ee9d6ef41/architecture/gap_config.md.
  - gap_config.md EXISTS (S1 §1-8 + S2 lockstep section). Use the edit tool to APPEND (after the last
    line / S2's section) a new top-level section:
        ## Search-Order & XDG Resolution Verification (P1.M1.T1.S3)
  - (Fallback: if for any reason S2's section is absent, still APPEND at EOF — after S1's §8 Conclusion.
     Do NOT overwrite or reorder existing content.)
  - STRUCTURE the S3 section with:
      1. Scope statement: "Verify VoiceTypingConfig.load() + _candidate_paths() + _xdg_config_path() +
         _repo_config_path() implement the PRD §4.5 search order. Distinct from S1 (field/default
         compliance) and S2 (lockstep/blocklist/Mode A)."
      2. `_candidate_paths()` order: "config.py:301-303 returns [_xdg_config_path(), _repo_config_path()]
         = XDG first, repo second. Matches PRD §4.5 precedence. PASS." Cite the live order.
      3. `_xdg_config_path()` resolution: "config.py:283-288. set → $XDG/voice-typing/config.toml;
         unset/empty/whitespace → ~/.config/voice-typing/config.toml (the .strip() collapses whitespace —
         more robust than the PRD literal; correct per XDG-spec intent). PASS." Include the 4-row table.
      4. `_repo_config_path()`: "config.py:291-298. Path(__file__).parent.parent/config.toml — module-
         relative, CWD-independent. Resolves to <repo>/config.toml and exists. Not packaged in the wheel
         (install.sh copies it to XDG for pip installs — by design, config.py:292-297). PASS."
      5. `load()` defaults fallback: "config.py:262-281 (return cls() @276). Explicit path bypasses the
         search; else first existing candidate wins; else VoiceTypingConfig() built-in defaults — NO
         exception (the PRD §4.5 tier-3 configless-boot safety guarantee). PASS."
      6. Test coverage: "7 dedicated search-order tests in tests/test_config.py (lines 280, 289, 301,
         311, 319, 326, 359) — explicit-path bypass, XDG-wins, repo-fallback, defaults-fallback, XDG-
         unset→home (real env+fn), XDG-set→env, module-level wrapper. monkeypatch makes them hermetic.
         7 passed (subset); 37 passed (full suite incl. test_config_repo_default.py)."
      7. Conclusion: "Search-order & XDG resolution logic is fully PRD §4.5-compliant and well-tested.
         No defects found. NO code changes required."
  - KEEP IT FACTUAL: cite config.py:line for every claim. No speculation. No duplication of S1's table
    or S2's lockstep result.

Task 3: VALIDATE (run the gates below). No git commit unless the orchestrator directs it. If asked,
  message: "P1.M1.T1.S3: config search-order & XDG resolution verified (PRD §4.5-compliant); no defects".
  IF (and only if) Task 1 surfaced a REAL defect: fix it in config.py (e.g. correct the candidate order,
  fix the XDG fallback path, or ensure load() returns cls() rather than raising), update/confirm the
  tests reflect the fix, and record the fix in the section's Conclusion. (Expected: this branch is NOT
  taken — the logic is compliant.)
```

### Implementation Patterns & Key Details

```python
# This is an audit/report task. The "pattern" is disciplined verification + honest reporting:
#   * Trace _candidate_paths() ORDER (not just existence) — PRD §4.5 mandates XDG-before-repo.
#   * Exercise _xdg_config_path() with set/unset/empty/whitespace env (the .strip() is a real behavior).
#   * Confirm _repo_config_path() is module-relative (Path(__file__)) so it's CWD-independent.
#   * Confirm load(None) with NO candidate returns cls() (defaults) WITHOUT raising — the tier-3
#     configless-boot safety guarantee.
#   * Cite the 7 dedicated tests by name + line; note they use monkeypatch for hermeticity.
#   * Distinguish a REAL defect (none) from ROBUST-BY-DESIGN behaviors (.strip(), repo-candidate-
#     absent-for-pip-installs, no relative-XDG check). Only the former gets a fix.
#
# The trap to avoid: flagging the .strip() or the "repo candidate absent for pip installs" as defects.
# Both are deliberate, documented design choices (config.py:285 .strip(); config.py:292-297 wheel note).
# The section's job is to record them as compliant/robust-by-design, NOT gaps.
```

### Integration Points

```yaml
DOWNSTREAM / SIBLING:
  - S1 (P1.M1.T1.S1) created gap_config.md (field/default PRD compliance, §1-8). S3 APPENDS its
    search-order section to that same file. The three sections (S1 + S2 + S3) together form the
    complete config audit: S1 = field compliance, S2 = lockstep/blocklist/Mode A, S3 = path resolution.
  - S2 (P1.M1.T1.S2, in parallel) appended the lockstep section. S2's section is already present in the
    live gap_config.md; S3 appends after it (at EOF). Different concern — no collision.

CONFIG LAYER (voice_typing/config.py + config.toml):
  - UNCHANGED by S3 (expected). The verification confirms the search-order logic already complies with
    PRD §4.5. If a real fix were needed, only config.py would change (path logic lives there) — but no
    fix is expected.

TEST SUITE:
  - tests/test_config.py (7 search-order tests) + tests/test_config_repo_default.py (drift guard) are the
    existing guards. S3's section documents that the 7 search-order tests directly cover the path-
    resolution contract (including the real-env _xdg_config_path checks at lines 319/326).
```

## Validation Loop

> Full paths for python (machine aliases python3→uv run). No ruff/mypy. No timeout needed — these are
> pure-Python (no CUDA/network/audio); they return in milliseconds. The gates verify the APPENDED
> section exists + is accurate + that NO source was changed (expected). All commands read-only except
> appending the section.

### Level 1: The S3 section is appended to gap_config.md and well-formed

```bash
cd /home/dustin/projects/voice-typing
DOC=plan/006_862ee9d6ef41/architecture/gap_config.md
test -f "$DOC" && echo "L1a PASS: gap_config.md exists" || echo "L1a FAIL"
echo "--- S1 + S2 sections still intact (not overwritten) ---"
grep -q 'P1.M1.T1.S1' "$DOC" && grep -q 'Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)' "$DOC" \
  && echo "L1b PASS: S1 + S2 sections intact" || echo "L1b FAIL: a prior section was clobbered"
echo "--- S3 section present ---"
grep -q 'Search-Order & XDG Resolution Verification (P1.M1.T1.S3)' "$DOC" && echo "L1c PASS" || echo "L1c FAIL: S3 section missing"
echo "--- section cites the key findings ---"
grep -qi 'candidate.*order\|XDG first' "$DOC" && echo "L1d PASS (candidate order cited)" || echo "L1d CHECK"
grep -qi 'no.*defect\|PRD.*compliant\|compliant per audit' "$DOC" && echo "L1e PASS (compliance conclusion)" || echo "L1e CHECK"
grep -qi '37 passed\|7 passed\|test_config' "$DOC" && echo "L1f PASS (test evidence cited)" || echo "L1f CHECK"
grep -qi 'config.py:30\|config.py:28\|config.py:26' "$DOC" && echo "L1g PASS (config.py:line citations)" || echo "L1g CHECK"
# Expected: gap_config.md exists; S1+S2 intact; S3 section present; cites order, compliance, tests, config.py:line.
```

### Level 2: The section's findings are reproducible (re-verify the search-order logic)

```bash
cd /home/dustin/projects/voice-typing
echo "--- re-run the search-order subset (section claims 7 passed) ---"
.venv/bin/python -m pytest tests/test_config.py -q \
  -k "search_order or load_with_explicit or xdg_config_path or module_level_load or missing_file_falls" 2>&1 | tail -2
echo "--- re-run the full config suite (section claims 37 passed) ---"
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q 2>&1 | tail -2
echo "--- re-verify: candidate order + xdg resolution + defaults fallback ---"
.venv/bin/python - <<'PY'
import os
from voice_typing import config as c
from voice_typing.config import VoiceTypingConfig, _candidate_paths, _repo_config_path
# order: XDG first, repo second
assert _candidate_paths() == [c._xdg_config_path(), c._repo_config_path()], "candidate order wrong"
assert os.path.isfile(_repo_config_path()), "repo candidate missing"
# xdg resolution
os.environ["XDG_CONFIG_HOME"] = "/custom/xdg"
assert c._xdg_config_path() == "/custom/xdg/voice-typing/config.toml"
os.environ.pop("XDG_CONFIG_HOME", None)
assert c._xdg_config_path() == os.path.join(os.path.expanduser("~/.config"), "voice-typing", "config.toml")
# defaults fallback (point both candidates nowhere)
ox, orc = c._xdg_config_path, c._repo_config_path
c._xdg_config_path = lambda: "/no/xdg.toml"; c._repo_config_path = lambda: "/no/repo.toml"
try:
    assert VoiceTypingConfig.load(None) == VoiceTypingConfig(), "load(None) should return defaults"
finally:
    c._xdg_config_path, c._repo_config_path = ox, orc
print("L2 PASS: order [xdg,repo]; xdg set/unset correct; repo exists; load(None)→defaults; no exception")
PY
# Expected: 7 passed; 37 passed; L2 PASS. Confirms the section's claims match the live code.
```

### Level 3: No source modified (expected — no defect found)

```bash
cd /home/dustin/projects/voice-typing
echo "--- git status: ONLY gap_config.md under plan/ should appear (no config.py/config.toml/tests) ---"
git status --short
echo "--- assert config.py + config.toml + tests UNCHANGED ---"
git diff --name-only | grep -E 'voice_typing/config\.py|config\.toml|tests/test_config' \
  && echo "L3 FAIL: source modified (unexpected — see Task 3 branch)" \
  || echo "L3 PASS: no source changes (no defect found)"
# Expected: "no source changes". If this FAILs, either a real defect was found+fixed (legitimate — verify
# the fix is correct AND the 37-test suite still passes), or the agent made an unrequested edit (revert).
```

### Level 4: The robust-by-design behaviors are recorded (not flagged as defects)

```bash
cd /home/dustin/projects/voice-typing
DOC=plan/006_862ee9d6ef41/architecture/gap_config.md
echo "--- the .strip() robustness is documented, not flagged as a defect ---"
grep -qi 'strip\|whitespace' "$DOC" && echo "L4a PASS (.strip() documented)" || echo "L4a CHECK"
echo "--- the repo-candidate-absent-for-pip design note is recorded ---"
grep -qi 'wheel\|pip\|install.sh copies\|not packaged' "$DOC" && echo "L4b PASS (wheel note)" || echo "L4b CHECK"
echo "--- config.py is byte-identical to git (the .strip() was NOT 'fixed') ---"
git diff --quiet voice_typing/config.py && echo "L4c PASS: config.py unchanged" || echo "L4c FAIL: config.py modified (unexpected)"
# Expected: the section records the .strip() + wheel design notes as robust-by-design; config.py unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: gap_config.md has the appended S3 section; S1 + S2 sections intact; cites order, compliance, tests, config.py:line.
- [ ] L2: 7 search-order tests pass; 37 full-suite pass; live re-check confirms order [xdg,repo], xdg resolution, repo exists, load(None)→defaults.
- [ ] L3: no source modified (config.py/config.toml/tests unchanged) — expected outcome.
- [ ] L4: the .strip() + repo-candidate-absent-for-pip behaviors are recorded as robust-by-design; config.py unchanged.

### Feature Validation
- [ ] Section records `_candidate_paths()` order = [XDG, repo] (PRD §4.5 precedence).
- [ ] Section records `_xdg_config_path()` resolution: set → `$XDG/...`; unset/empty → `~/.config/...`.
- [ ] Section records `_repo_config_path()` module-relative + exists.
- [ ] Section records `load(None)` with no candidate → `VoiceTypingConfig()` defaults (no exception — tier-3 safety).
- [ ] Section cites the 7 dedicated search-order tests by name/line + the 37-passed full count.

### Code Quality Validation
- [ ] Every claim in the section cites a config.py:line (262/276/283-288/291-298/301-303/306).
- [ ] Section distinguishes REAL defects (none) from ROBUST-BY-DESIGN behaviors (.strip(), wheel note).
- [ ] Section does NOT duplicate S1's field table or S2's lockstep result (appends a distinct path-resolution section).

### Scope Boundary Validation
- [ ] No config.py/config.toml edits (unless a real defect is found — not expected).
- [ ] No edits to test files, daemon.py, or any other module.
- [ ] Only `plan/006_862ee9d6ef41/architecture/gap_config.md` is modified (the appended S3 section).
- [ ] S3 does NOT do S1's job (field compliance) or S2's job (lockstep/blocklist/Mode A).

### Documentation & Deployment
- [ ] (The gap_config.md section IS the documentation deliverable.) It records the verification result durably.
- [ ] If asked to commit: message references search-order + XDG resolution verification + PRD §4.5 compliance.

---

## Anti-Patterns to Avoid

- ❌ **Don't duplicate S1's field table or S2's lockstep section.** S3's scope is search-order & XDG resolution (which file is found, in what order). APPEND a focused section; don't re-derive S1/S2.
- ❌ **Don't flag the `.strip()` as a defect.** `config.py:285` does `os.environ.get("XDG_CONFIG_HOME","").strip()` — collapsing whitespace-only values to the `~/.config` fallback is MORE robust than PRD §4.5's literal "unset/empty" wording and is correct per XDG-spec intent. Record it as robust-by-design.
- ❌ **Don't flag the repo candidate as "missing for pip installs".** config.toml isn't packaged in the wheel; `install.sh` copies it to XDG (candidate #1). By design (config.py:292-297).
- ❌ **Don't add relative-XDG_CONFIG_HOME validation.** The PRD doesn't require it; the XDG spec says the var should be absolute but doesn't mandate rejection. Adding it is gold-plating, out of scope.
- ❌ **Don't "refactor" the module-level helpers into methods.** They're module-level on purpose so tests can `monkeypatch` them (test_config.py:295-297). Refactoring breaks the tests.
- ❌ **Don't trust the findings blindly — re-run them.** The implementing agent re-runs the pytest + the live resolution dump before transcribing, in case the tree moved since this audit.
- ❌ Don't edit config.py / config.toml / tests if no defect — the contract says record "none — search-order logic is PRD §4.5-compliant per audit." Source edits are the unexpected branch only.
- ❌ Don't OVERWRITE gap_config.md — it carries S1 (§1-8) + S2 (lockstep). APPEND the S3 section at EOF.
- ❌ Don't invoke ruff/mypy (not configured). Don't add timeout wrappers (these are millisecond pure-Python commands; the AGENTS.md daemon rules don't apply).

---

## Confidence Score

**9.5/10** for one-pass "implementation" success. The deliverable is one appended report section whose every finding is already verified in this PRP (the live search-order check is done: candidate order [xdg,repo], XDG resolution set/unset/empty/whitespace all correct, repo path module-relative + exists, `load(None)`→defaults with no exception, 7 dedicated tests pass, 37 full-suite pass). The implementing agent re-runs three read-only commands to confirm, then transcribes into the appended section. The −0.5 is the single most likely implementation error — an agent could mistake the `.strip()` (whitespace→fallback) or the "repo candidate absent for pip installs" (by-design wheel note) for defects and "fix" them, introducing a real regression. That trap is called out as Anti-Patterns #3/#4 and guarded by validation L4 (robust-by-design behaviors recorded; config.py byte-identical to git) + the explicit "do NOT flag" instructions with their config.py:line citations. A secondary minor risk is the APPEND-vs-existing-content decision, mitigated by the L1b gate (S1 + S2 sections intact) + Gotcha #7.
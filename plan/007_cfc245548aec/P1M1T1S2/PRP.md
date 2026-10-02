# PRP — P1.M1.T1.S2: Add evdev dependency (uv add + lock)

## Goal

**Feature Goal**: Add the `evdev` (python-evdev) runtime dependency — the implementation dep for Rev 2's passive Backspace-cancel keyboard listener (PRD §4.2quater: "python-evdev is the implementation dep") — to `pyproject.toml` + `uv.lock` + `.venv`, verified importable. Dependency-only: **no source imports, no daemon, no tests** in this subtask (the `import evdev` lands with the listener in P1.M2.T7.S2).

**Deliverable**: (1) `pyproject.toml` `[project]` dependencies gains `evdev` (uv writes it); (2) `uv.lock` regenerated with evdev; (3) `import evdev` works in `.venv`. Nothing else.

**Success Definition**: (a) `timeout 120 /home/dustin/.local/bin/uv add evdev` exits 0; (b) the `uv.lock` diff contains evdev (and ideally nothing else — evdev has zero runtime deps); (c) `timeout 30 .venv/bin/python -c 'import evdev; print(evdev.__version__)'` succeeds (**expected `2.0.0`** — see Gotcha #1); (d) no source file, config, test, or bind file is touched; (e) no daemon run, no pytest (per contract).

## User Persona

Not applicable (dependency-manifest subtask; no user-facing surface — the README surface is P1.M3.T10.S1).

## Why

- **Rev 2 substrate (PRD §4.2quater + §5 step 4).** Backspace-cancel needs a passive, read-only evdev listener over `/dev/input/event*` in the daemon process. PRD §5's install step lists `evdev` in the `uv add` line; P1.M2.T7.S2 writes the listener and will `import evdev` — this subtask guarantees that import resolves.
- **Cheap, isolated, zero-conflict.** `uv add` touches only pyproject.toml + uv.lock + .venv. The parallel S1 (config schema delta) owns config.py/config.toml/tests/test_config*.py — **no file overlap**. uv's incremental lock reuse keeps the diff minimal (evdev has no dependencies).
- **Do it now, not inside T7.S2.** Keeping the manifest change separate from the listener code means the (small) resolution/build risk is retired before the heavy listener task starts.

## What

Run the one contract command, then verify the three artifacts. No code, no imports added to `voice_typing/`, no config, no tests.

### Success Criteria

- [ ] `timeout 120 /home/dustin/.local/bin/uv add evdev` exits 0 (with `UV_HTTP_TIMEOUT=300` as free insurance).
- [ ] `pyproject.toml` dependencies (currently :9-13) now include `evdev`.
- [ ] `uv.lock` diff contains `name = "evdev"`; ideally the ONLY change (no unexplained bumps of existing packages).
- [ ] `timeout 30 .venv/bin/python -c 'import evdev; print(evdev.__version__)'` prints a version (expected **2.0.0**).
- [ ] `git diff --name-only` == exactly `pyproject.toml` + `uv.lock`.
- [ ] No daemon run; no pytest (S1's parallel work intentionally leaves daemon-side suites red until P1.M1.T2 — not this subtask's gate).

## All Needed Context

### Context Completeness Check

_Pass._ The exact current dependency block, the live preconditions (evdev absent everywhere), the version reality (2.0.0 now, not the notes' 1.9.3), the sdist-compile consequence, and the exact verification commands are all verified below. An agent new to this repo needs nothing else.

### Documentation & References

```yaml
# THE PACKAGING FACTS (deps at :9-13, lock exists, venv 3.12.10)
- docfile: plan/007_cfc245548aec/architecture/substrate_map.md
  why: §7 "Packaging / environment" — the pyproject block verbatim + "**evdev must be added here +
        uv.lock regenerated**". (NOTE: the contract cites "§6"; the packaging section is §7 in the
        live file — §6 is textproc. Same facts either way.)
  critical: "deps live at pyproject.toml:9-13; uv.lock exists; venv Python 3.12.10."

# THE LIBRARY FACTS (API contract + the version note — NOW STALE)
- docfile: plan/007_cfc245548aec/architecture/external_deps.md
  why: §1 documents evdev: requires-python >=3.11 (venv 3.12.10 compatible), NOT currently importable,
        permissions (user in `input` group), and the API contract P1.M2.T7.S2 will consume.
  critical: "Its 'latest = 1.9.3' claim is STALE — live PyPI says 2.0.0 (Aug 2026). The contract's
        command is UNPINNED; expect 2.0.0. Do NOT pin to 1.9.3 by default (Gotcha #1)."

# THIS SUBTASK'S RESEARCH NOTE — live re-verification + the version discrepancy
- docfile: plan/007_cfc245548aec/P1M1T1S2/research/evdev_dependency_findings.md
  why: §1 live preconditions; §2 the 2.0.0-vs-1.9.3 discrepancy; §3 sdist-only packaging + the 1.9.3
        contingency; §4 2.0.0-vs-listener API compatibility; §5 uv/lock behavior; §6 AGENTS.md discipline.
  section: "§2 (version) and §3 (sdist compile) are load-bearing."

# THE SPEC (install-step source + what the dep is for)
- docfile: plan/007_cfc245548aec/prd_snapshot.md
  why: §5 step 4 lists evdev in the `uv add` line (unpinned) + the alias warning (full-path uv).
        §4.2quater Backspace-cancel defines the listener that will consume it (P1.M2.T7.S2).

# THE SIBLING CONTRACT (parallel S1 — confirms zero overlap)
- file: plan/007_cfc245548aec/P1M1T1S1/PRP.md
  why: S1 owns voice_typing/config.py + config.toml + tests/test_config.py + tests/test_config_repo_default.py.
        This subtask touches pyproject.toml/uv.lock/.venv ONLY — no conflict. S1's transitional red
        suites are expected and NOT this task's concern.

# THE EDIT SITE (what uv add will rewrite)
- file: pyproject.toml
  why: [project] dependencies at :9-13 (4 entries today). `uv add evdev` appends `"evdev"` there.
        [dependency-groups] dev (pytest) is NOT touched — evdev is a runtime dep (correct default group).
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── pyproject.toml        # deps :9-13 (4 entries; NO evdev)   ← MODIFIED BY `uv add` (tool-written)
├── uv.lock               # exists, 97 KB, mtime Jul 7 (stale)  ← REGENERATED BY `uv add`
└── .venv/                # Python 3.12.10; evdev NOT installed (ModuleNotFoundError probe)
```

### Desired Codebase tree with files to be changed

```bash
pyproject.toml   # MODIFY (via uv): dependencies += "evdev"
uv.lock          # REGENERATE (via uv): evdev entry (+ nothing else expected)
# NOTHING ELSE. No voice_typing/ source, no config.toml, no tests, no binds, no README.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — EXPECT evdev 2.0.0, NOT 1.9.3. external_deps.md §1 (and the contract's context) say
# "latest 1.9.3" — that is STALE. Live PyPI (probed): latest = 2.0.0 (Aug 2026), requires-python
# >=3.11 (compatible). The contract's command is UNPINNED (`uv add evdev`, mirroring PRD §5 verbatim),
# so it resolves 2.0.0. Verification is version-agnostic (the import must succeed; expect "2.0.0").
# Do NOT "fix" the version toward 1.9.3 by default.

# CRITICAL #2 — 2.0.0 SHIPS SDIST ONLY (no wheels): `uv add evdev` COMPILES a small C extension.
# Needs gcc (present on this Arch box). uv builds in isolation; expect a slightly longer add + build
# output mentioning evdev's setup. If the build genuinely FAILS on this machine, the documented
# contingency is `timeout 120 /home/dustin/.local/bin/uv add "evdev==1.9.3"` (wheel-era release) —
# record the pin in the wrap-up. This is the fallback ONLY; try unpinned first.

# CRITICAL #3 — THE LOCK DIFF SHOULD BE evdev-ONLY. evdev has ZERO runtime dependencies
# (requires_dist: None) and uv reuses the existing lock for existing packages. If `git diff uv.lock`
# shows UNEXPLAINED version bumps of existing packages, investigate before accepting — do not
# blind-commit a surprise mass-bump.

# CRITICAL #4 — TWO TIMEOUTS, FULL PATHS (repo AGENTS.md). Inner `timeout 120` around `uv add`;
# bash-tool timeout above it; `timeout 30` around the import probe. Always
# /home/dustin/.local/bin/uv and .venv/bin/python (zsh aliases python3→uv run). Optionally export
# UV_HTTP_TIMEOUT=300 (free insurance; evdev's sdist is tiny so the 30s default is likely fine).

# GOTCHA #5 — NO DAEMON, NO PYTEST (per contract). S1's parallel config-schema delta INTENTIONALLY
# leaves daemon-side suites red until P1.M1.T2; do not run, chase, or "investigate" them here.

# GOTCHA #6 — uv add ALSO RE-SYNCS .venv (rebuilds the voice_typing package). Harmless and expected:
# wheel building does NOT import the package, so S1's in-flight source edits cannot break it. Only
# pyproject.toml + uv.lock should appear in `git diff --name-only` (.venv is gitignored).

# GOTCHA #7 — DON'T PRE-IMPORT. No `import evdev` anywhere in voice_typing/ source — the import
# lands with the listener in P1.M2.T7.S2. This subtask proves availability only.
```

## Implementation Blueprint

### Data models and structure

None. A one-command dependency addition; uv authors both file changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the precondition (one read-only probe).
  - RUN: cd /home/dustin/projects/voice-typing && timeout 30 .venv/bin/python -c 'import evdev; print(evdev.__version__)'
  - EXPECT: ModuleNotFoundError (evdev not yet installed). If it IMPORTS, a concurrent process
    already added it — verify Task 2's artifacts instead of re-adding.

Task 2: ADD the dependency (the one contract command).
  - RUN:
        cd /home/dustin/projects/voice-typing
        UV_HTTP_TIMEOUT=300 timeout 120 /home/dustin/.local/bin/uv add evdev
  - EXPECT: exit 0; uv appends "evdev" to [project] dependencies, re-locks, installs (compiles the
    small C extension from the 2.0.0 sdist — Gotcha #2). IF it fails on the build: use the
    documented contingency `UV_HTTP_TIMEOUT=300 timeout 120 /home/dustin/.local/bin/uv add "evdev==1.9.3"`
    and note the pin in the wrap-up.

Task 3: VERIFY the three artifacts.
  - RUN (all under timeout):
        timeout 30 .venv/bin/python -c 'import evdev; print(evdev.__version__)'   # expect 2.0.0 (or 1.9.3 on contingency)
        grep -n '"evdev"' pyproject.toml                                            # present in [project] dependencies
        grep -n 'name = "evdev"' uv.lock                                            # present in the lock
        git diff --name-only                                                        # exactly pyproject.toml + uv.lock
        git diff --stat uv.lock                                                     # small, evdev-focused
  - EXPECT: import prints a version; both files list evdev; the diff touches ONLY pyproject.toml +
    uv.lock; the lock diff is evdev-only (Gotcha #3 — if unrelated packages bumped, investigate).

Task 4: WRAP UP. No pytest, no daemon, no source imports (contract). No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T1.S2: add evdev dependency (uv add + lock; resolves 2.0.0) for the Rev 2 backspace-cancel listener".
```

### Implementation Patterns & Key Details

```bash
# The whole task is one tool-driven manifest change + three verification probes. The two things an
# agent could get wrong are BOTH assumptions, not commands:
#   (1) expecting 1.9.3 (stale note) and treating the resolved 2.0.0 as an error — it is not; the
#       contract command is unpinned and PyPI now serves 2.0.0;
#   (2) not noticing a mass-bump in the uv.lock diff — evdev has zero deps, so anything beyond
#       evdev in the diff is a stale-lock re-resolution anomaly worth investigating before commit.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMER — P1.M2.T7.S2 (evdev passive listener):
  - Will `import evdev` and use: list_devices(), InputDevice(path), capabilities(),
    ecodes.EV_KEY/KEY_BACKSPACE, read_loop()/read_one(). Verified (research note §4): 2.0.0 is
    API-compatible with all of these (changes are additive). BONUS for that task: 2.0.0 adds
    InputDevice(..., readonly=...) — an even better fit for the passive/never-grab listener.
  - NOTE for T7.S2: readonly= requires 2.0.0 — fine on the expected path, unavailable on the 1.9.3
    contingency pin.

SIBLING (parallel S1 — config schema delta): zero file overlap (config.py/config.toml/tests vs
  pyproject.toml/uv.lock). uv's package rebuild is import-free, so S1's edits cannot break Task 2.

PRD §5 INSTALL STEP: this closes the last item of the `uv add` dependency line (realtimestt + nvidia
  wheels + huggingface_hub were already present; evdev was the only missing entry).
```

## Validation Loop

> Repo AGENTS.md: two timeouts on every non-trivial command; full-path uv/python; no daemon; no pytest. All gates are fast.

### Level 1: The dependency is importable (the core gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 30 .venv/bin/python -c 'import evdev; print("L1 PASS:", evdev.__version__)'
# Expected: "L1 PASS: 2.0.0" (or 1.9.3 if the contingency pin was required — record which).
```

### Level 2: Both manifest files carry evdev, and only them changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- pyproject [project] dependencies ---"
grep -n '"evdev"' pyproject.toml && echo "L2a PASS: pyproject has evdev" || echo "L2a FAIL"
echo "--- uv.lock has the evdev entry ---"
grep -q 'name = "evdev"' uv.lock && echo "L2b PASS: lock has evdev" || echo "L2b FAIL"
echo "--- ONLY pyproject.toml + uv.lock changed ---"
git diff --name-only
test "$(git diff --name-only | grep -vE '^(pyproject\.toml|uv\.lock)$' | wc -l)" -eq 0 \
  && echo "L2c PASS: only pyproject.toml + uv.lock" || echo "L2c FAIL: out-of-scope file changed"
echo "--- lock diff is evdev-focused (no unexplained mass-bump) ---"
git diff --stat uv.lock
git diff uv.lock | grep -c '^\+' | xargs echo "added lock lines:"
# Expected: L2a/L2b/L2c PASS; the lock diff is small and evdev-centered. If the diff shows other
# packages' versions changing, READ it and decide (Gotcha #3) before accepting.
```

### Level 3: No daemon ran, no source touched, scope clean

```bash
cd /home/dustin/projects/voice-typing
echo "--- no voice_typing/ source or config/test/binds edits ---"
git diff --name-only | grep -E 'voice_typing/|config\.toml|tests/|hypr-binds|install\.sh|systemd/' \
  && echo "L3 FAIL: source touched" || echo "L3 PASS: no source/config/test/binds changes"
echo "--- no evdev import landed in source (P1.M2.T7.S2 owns it) ---"
grep -rn 'import evdev' voice_typing/ && echo "L3 FAIL: premature import" || echo "L3 PASS: no premature import"
```

## Final Validation Checklist

### Technical Validation
- [ ] `uv add evdev` exited 0 under `timeout 120` with full-path uv.
- [ ] `import evdev` prints a version (expected 2.0.0; 1.9.3 only via the documented contingency).
- [ ] `uv.lock` contains evdev; the lock diff is evdev-only (no unexplained bumps).
- [ ] `git diff --name-only` == `pyproject.toml` + `uv.lock`.

### Feature Validation
- [ ] evdev is available to P1.M2.T7.S2 (the import resolves in .venv).
- [ ] No `import evdev` added to `voice_typing/` source (dependency-only, per contract).

### Code Quality / Scope Validation
- [ ] No daemon run; no pytest invoked (per contract; S1's transitional red suites not chased).
- [ ] No source/config/test/binds/install.sh/systemd changes.
- [ ] Any contingency pin (`evdev==1.9.3`) recorded in the wrap-up if used.

### Documentation & Deployment
- [ ] None (README surface is P1.M3.T10.S1).

---

## Anti-Patterns to Avoid

- ❌ Don't pin `evdev==1.9.3` by default — the stale note's version is context, not an instruction; the contract/PRD command is unpinned and PyPI now serves 2.0.0. Pin ONLY as the documented build-failure contingency.
- ❌ Don't treat the resolved 2.0.0 as an error or "wrong version" — the verification is `import evdev` succeeds, not a specific version string.
- ❌ Don't blind-commit a uv.lock diff containing unexplained version bumps — evdev has zero deps; anything beyond evdev deserves a read first.
- ❌ Don't add `import evdev` to any `voice_typing/` source — the import lands in P1.M2.T7.S2.
- ❌ Don't run the daemon or pytest (contract says none needed; S1's parallel breakage makes daemon suites red by design — not this task's gate).
- ❌ Don't run `uv add` (or the import probe) without the inner `timeout` + full paths (`/home/dustin/.local/bin/uv`, `.venv/bin/python` — zsh aliases).
- ❌ Don't touch `[dependency-groups]` or add evdev to dev — it's a runtime dep; uv's default group is correct.

---

## Confidence Score

**9.5/10** for one-pass implementation success. It is a single tool-driven command whose preconditions are live-verified (deps at pyproject.toml:9-13, evdev absent from venv/lock/pyproject, uv 0.7.11, Python 3.12.10) and whose only two failure modes are anticipated with explicit handling: the version discrepancy (stale 1.9.3 note vs live 2.0.0 — Gotcha #1 tells the agent 2.0.0 is expected, so it won't "fix" it) and the sdist-only C compile (Gotcha #2 + the 1.9.3 contingency). No file overlap with the parallel S1, and uv's package rebuild cannot be broken by S1's source edits (wheel builds don't import). The −0.5 is the sdist compile on this box being live-untested here (gcc is present per machine facts, but the build itself is the one step not pre-run by this PRP's author — the contingency covers a failure).

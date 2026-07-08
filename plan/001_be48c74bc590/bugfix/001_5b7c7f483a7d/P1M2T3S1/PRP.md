# PRP — P1.M2.T3.S1: Add portaudio preflight check to install.sh

## Goal

**Feature Goal**: Fix bugfix Issue 6 (PRD §5 step 2; selected h3.5) by adding a **portaudio
preflight check** to `install.sh` that runs *before* `uv sync`. On a fresh Arch clone without
the `portaudio` system library, `uv sync` still installs the PyAudio wheel, but the daemon then
fails at PyAudio construction (`libportaudio` dlopen) and `install.sh` only prints the confusing
`"voice-typing.service: NOT active — check journalctl"`. This task turns that confusing late
failure into an **actionable, early stderr message + `exit 1`** with the exact remediation
command, mirroring the existing preflight idiom.

**Deliverable** (one surgical insertion in `install.sh`; no logic change elsewhere, no new files):
- Insert a `portaudio`/`pacman` preflight block **immediately after `install.sh:42`** (the
  `systemctl` check), before `uv sync`. The block: (a) warns-and-continues on non-Arch hosts
  (`pacman` absent); (b) when `pacman` is present and `pacman -Q portaudio` reports the package
  absent, prints the actionable message to stderr and `exit 1`.

**Success Definition**:
- (a) On a host **with** `pacman` and **with** `portaudio` installed (this machine), the new
  block is a silent no-op and `install.sh` proceeds normally to `uv sync` (`[1/7] uv sync` reached).
- (b) On a host **with** `pacman` but **without** `portaudio`, `install.sh` prints exactly
  `install.sh: portaudio not installed (PyAudio system dependency). Run: sudo pacman -S --noconfirm portaudio, then re-run ./install.sh` to **stderr** and exits `1` — *before* `uv sync`.
- (c) On a non-Arch host (**no** `pacman`), `install.sh` prints a warning to stderr and
  **continues** (does not exit) so non-Arch users aren't hard-blocked by an Arch-only check.
- (d) The new block does NOT trip `set -euo pipefail` (`install.sh:25`) — the `pacman -Q` failure
  return code is consumed inside `if !`/`elif !` condition position.
- (e) `bash -n install.sh` passes; `shellcheck install.sh` reports no new errors from the block.
- (f) `git status --short` shows **only** `install.sh` modified (no other files; the in-flight
  sibling P1.M2.T2.S2 edits `feedback.py`/`typing_backends.py` and is disjoint).

## User Persona

**Target User**: A Linux power user cloning the repo and running `./install.sh` on a fresh Arch box.

**Use Case**: First-time install on a host where `portaudio` was not pre-installed.

**User Journey**: `git clone` → `./install.sh` → (portaudio missing) → sees one clear stderr line
naming the exact `sudo pacman -S --noconfirm portaudio` command → runs it → re-runs `./install.sh` → succeeds.

**Pain Points Addressed**: Today the same user reaches a cryptic `voice-typing.service: NOT active — check journalctl` (the real cause being a PyAudio `dlopen: libportaudio.so` failure buried in the journal) with no hint that a missing system package is the cause.

## Why

- **PRD §5 step 2 mandates it**: `pacman -Q portaudio || sudo pacman -S --noconfirm portaudio`. PRD §2 notes that when `sudo` is not available non-interactively, the user should be *asked to run it manually* — which is exactly the actionable-message + re-run design here (we never attempt `sudo` from the script).
- **PyAudio (a RealtimeSTT dep) dynamically links `libportaudio`** at construction; the `uv sync` PyAudio *wheel* installs fine without the system lib, so the failure is deferred and opaque. Catching it as a preflight makes the error proportional and located at its true cause.
- **Minimal, low-risk**: a pure preflight guard with no behavior change on the happy path; the only new `exit 1` path fires only when the install *would already fail* — it just fails earlier and clearly.

## What

Insert the block below after `install.sh:42`. The block mirrors the existing preflight idiom
(`install.sh:`-prefixed messages to stderr, `exit 1` on hard failure) and uses the `if ! … >/dev/null 2>&1`
condition form mandated by the contract so the `pacman -Q` non-zero return code cannot abort the
script under `set -euo pipefail`.

### Success Criteria

- [ ] `install.sh` contains a `portaudio` check between the `systemctl` check (line 42) and the `# XDG_CONFIG_HOME …` line (currently line 44), i.e. **before** `echo "==> [1/7] uv sync"`.
- [ ] The check uses `if ! command -v pacman >/dev/null 2>&1; then … elif ! pacman -Q portaudio >/dev/null 2>&1; then … exit 1; fi`.
- [ ] Missing-portaudio message is byte-exact (see Implementation Blueprint) and goes to **stderr** (`>&2`), followed by `exit 1`.
- [ ] pacman-absent (non-Arch) path prints a warning to stderr and **does not** `exit 1`.
- [ ] `bash -n install.sh` exits 0; `shellcheck install.sh` introduces no new error for the block.
- [ ] `git status --short` shows only `install.sh` changed.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement this from this PRP + the two
research notes: the exact insertion anchor (the `systemctl` one-liner at line 42, reproduced
verbatim below), the exact new block (copy-paste ready), the `set -e` analysis proving the
`if !`/`elif !` form is safe, and the exact validation commands (bash/shellcheck + three
scratch-shell branch simulations that are independent of whether portaudio is installed here).

### Documentation & References

```yaml
# MUST READ — exact preflight structure, exact insertion point (after line 42), set -e analysis,
# exact byte-exact message, em-dash gotcha, README-scope decision, sibling disjointness.
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T3S1/research/install_sh_preflight_structure.md
  why: "§1 exact lines 36-42 + the anchor for the edit. §2 the existing preflight idiom (stderr +
        exit 1; stdout reserved for the quick-start). §3 WHY the if!/elif! form is required under
        set -euo pipefail (line 25) — pacman -Q returns non-zero when absent and would abort a bare
        call. §4 the byte-exact messages. §5 the em-dash '—' byte-exact gotcha. §6 why README is
        OUT of scope (line 18 already documents portaudio; conditional DOCS clause does not fire;
        README changeset sync owned by P1.M3.T1.S1). §7 disjoint from P1.M2.T2.S2."
  section: "ALL (§1–§7)."

# MUST READ — validation: install.sh is a BASH script (no pytest); bash -n + shellcheck; and the
# three scratch-shell branch simulations (happy / missing-portaudio / non-Arch) that prove the
# control flow without mutating the system.
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T3S1/research/validation_approach.md
  why: "§1 shellcheck IS installed (/usr/bin/shellcheck); shfmt is NOT. §2 mandatory lint. §3 the
        three branch simulations (the real logic test, since portaudio is installed on this box).
        §4 optional happy-path end-to-end. §5 what NOT to do (don't uninstall system portaudio)."
  section: "ALL (§1–§5)."

# MUST READ — the file being edited (verbatim source for the exact edit anchor).
- file: install.sh
  why: "The edit anchor is line 42: 'command -v systemctl >/dev/null 2>&1 || { echo \"install.sh:
        systemctl not found\" >&2; exit 1; }'. The new block is inserted directly AFTER it, before
        the blank line that precedes '# XDG_CONFIG_HOME, mirroring voice_typing/config.py …'."
  pattern: "Existing preflight idiom: one-liner 'command -v X >/dev/null 2>&1 || { echo
            \"install.sh: …\" >&2; exit 1; }'. Mirror it; but the portaudio check is two-staged
            (pacman presence THEN portaudio presence) so use the multi-line if!/elif!/fi form."
  gotcha: "install.sh:25 has 'set -euo pipefail'. A bare 'pacman -Q portaudio' that fails (package
           absent) would ABORT the script — it MUST be inside 'if !'/'elif !' condition position
           (errexit-exempt). Also: existing echo messages use an EM DASH '—' (U+2014), e.g. line 38;
           reproduce '—' exactly, not '-'. stdout is reserved for the user-facing quick-start
           (Mode A docs) — error/warn messages MUST go to stderr (>&2)."

# SHOULD READ — PRD §5 step 2 (the mandated portaudio command) and §2 (non-interactive-sudo note).
- docfile: PRD.md
  why: "§5 step 2: 'pacman -Q portaudio || sudo pacman -S --noconfirm portaudio'. §2: if sudo is
        unavailable non-interactively, ask the user to run it manually — which is exactly this
        design (we print the command; we never invoke sudo)."
  section: "§5 step 2 (around PRD.md:261), §2."

# CONTEXT — README is OUT of scope for this task (see research §6).
- file: README.md
  why: "README.md:18 already documents portaudio ('- portaudio (PyAudio build dep). Check it with
        pacman -Q portaudio.'). The Install section's numbered step list (~lines 30-37) starts at
        '1. uv sync' and does NOT enumerate preflight checks, so the item's conditional DOCS clause
        does not fire. README changeset-wide sync is owned by P1.M3.T1.S1."
  critical: "Do NOT edit README.md in this task. Nothing there is now stale (line 18 still correct)."

# CONTEXT — the in-flight sibling (disjoint files; no conflict).
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T2S2/PRP.md
  why: "P1.M2.T2.S2 edits voice_typing/feedback.py, voice_typing/typing_backends.py, and their
        tests. This task edits install.sh ONLY. Zero file overlap -> no merge conflict."
```

### Current Codebase tree (run `tree` in the repo root, or `ls -1`)

```bash
$ ls -1   # only the files relevant to this task
install.sh          # <-- the ONLY file this task edits
README.md           # (out of scope; line 18 already documents portaudio)
PRD.md              # (READ-ONLY reference)
systemd/voice-typing.service
voice_typing/       # (untouched here)
...
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
install.sh          # MODIFIED: +1 preflight block (~10 lines) inserted after the systemctl check.
                     #   No new files. No other file changed.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL: install.sh:25 is 'set -euo pipefail'. A bare 'pacman -Q portaudio' returns non-zero
# when the package is absent and would ABORT the script. It MUST sit inside 'if !'/'elif !'
# condition position (command lists in an if/elif condition, and '!' negation there, are exempt
# from errexit under bash 5.3). Verified in research/install_sh_preflight_structure.md §3.

# CRITICAL: install.sh's STDOUT is the user-facing install/usage quick-start (Mode A docs — see
# the header comment). ALL error/warn messages MUST go to stderr (>&2), matching every existing
# preflight message (lines 38, 41, 42). Do not echo the actionable message to stdout.

# GOTCHA (byte-exact editing): install.sh's echo messages use an EM DASH '—' (U+2014), e.g. line 38.
# The new non-Arch warning line uses '—' too. Reproduce '—' exactly in newText (NOT '-' or '->').
# The edit ANCHOR (the systemctl line) is pure ASCII, so oldText matching is byte-safe.

# GOTCHA: 'pacman -Q portaudio' on an absent package prints "error: package 'portaudio' was not
# found" to stderr. The '>/dev/null 2>&1' suppression keeps that noise off-screen so only
# install.sh's own actionable message shows.

# GOTCHA: portaudio IS installed on this machine (1:19.7.0-4), so the happy path is silent and the
# failure branches CANNOT be exercised by running the real installer — validate them with the
# scratch-shell simulations in research/validation_approach.md §3 (do NOT uninstall the system pkg).
```

## Implementation Blueprint

### Data models and structure

Not applicable — this is a shell-script edit. No data models, no ORM, no Pydantic.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY install.sh — insert the portaudio preflight block
  - ANCHOR: the systemctl one-liner at install.sh:42
        command -v systemctl >/dev/null 2>&1 || { echo "install.sh: systemctl not found" >&2; exit 1; }
  - INSERT directly AFTER that line (before the blank line that precedes the
    '# XDG_CONFIG_HOME, mirroring voice_typing/config.py …' comment). The exact block to add:

        # --- preflight: PyAudio needs the portaudio system library (PRD §5 step 2). On a fresh
        #     clone without it, uv sync installs the wheel but the daemon later fails at PyAudio
        #     dlopen with a confusing "NOT active — check journalctl". Catch it here with an
        #     actionable message. pacman -Q returns non-zero when the package is absent; the
        #     `if !`/`elif !` guards keep its return code from aborting the script under set -e.
        #     Non-Arch hosts (no pacman) get a warn-and-continue. ---
        if ! command -v pacman >/dev/null 2>&1; then
          echo "install.sh: pacman not found — skipping portaudio check (non-Arch host). Install PyAudio's portaudio dependency manually." >&2
        elif ! pacman -Q portaudio >/dev/null 2>&1; then
          echo "install.sh: portaudio not installed (PyAudio system dependency). Run: sudo pacman -S --noconfirm portaudio, then re-run ./install.sh" >&2
          exit 1
        fi

  - FOLLOW pattern: existing preflight idiom (install.sh:41-42 one-liners + the XDG multi-line
    if/fi at 37-40) — stderr message, `exit 1` on hard failure.
  - NAMING/STYLE: message prefix "install.sh: " (matches all existing messages); em dash '—'
    for the non-Arch warning (matches line 38's style).
  - PLACEMENT: immediately after line 42; this is the LAST preflight check, right before uv sync
    (echo "==> [1/7] uv sync"). It MUST precede uv sync so a missing portaudio is caught before
    the PyAudio wheel is installed.
  - PRESERVE: everything else in install.sh unchanged. Do NOT reorder existing preflight checks.

Task 2: VALIDATE (no file change — see Validation Loop)
  - bash -n install.sh ; shellcheck install.sh ; the three scratch-shell branch simulations.
```

### Implementation Patterns & Key Details

```bash
# The ONLY edit. oldText = the systemctl line (unique in the file). newText = that line + the block.
#
# oldText (exact, line 42):
#   command -v systemctl >/dev/null 2>&1 || { echo "install.sh: systemctl not found" >&2; exit 1; }
#
# newText: the SAME line, then a blank line, then the comment header + the if!/elif!/fi block
# from Task 1 above.
#
# Why if!/elif! and not the one-liner '|| { …; exit 1; }' idiom:
#   The portaudio check is TWO-STAGED: (1) is pacman present? (2) if so, is portaudio present?
#   Stage (2) is the one whose non-zero return code must not trip errexit — placing it in an
#   'elif !' condition makes it errexit-exempt. The one-liner idiom cannot express the
#   "warn-and-continue if no pacman, else hard-fail if no portaudio" branching cleanly.
```

### Integration Points

```yaml
NO integration points beyond install.sh itself.
  - DATABASE: none.
  - CONFIG: none (config.toml untouched; this runs before config copy).
  - ROUTES: none.
  - DEPENDENCIES: none (shell only; pacman is probed, not added).
  - SYSTEMD: none (this runs before the systemd unit install).
  - README: out of scope (line 18 already documents portaudio; changeset-wide README sync is
            P1.M3.T1.S1).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback — MANDATORY)

```bash
# Run after the edit. install.sh is a bash script (no ruff/mypy/pytest here).
bash -n install.sh            # parse/syntax check; expect exit 0
shellcheck install.sh         # static lint; expect NO new error from the new block
# Expected: both pass. shellcheck may emit informational SC2312 ("consider invoking this command
# separately") for the '>/dev/null 2>&1' suppression — that is acceptable style noise, NOT an
# error; the 'if !' form is the intentional idiomatic suppression. If any real error (e.g.
# SC2086 unquoted variable) appears, READ it and fix before proceeding.
```

### Level 2: Branch Simulation (the real logic test — MANDATORY)

Because `portaudio` IS installed on this machine, the failure branches cannot be hit by running
the real installer. Exercise all three branches in throwaway subshells (these do NOT touch the
system or install.sh):

```bash
# (a) HAPPY PATH (portaudio present) — must continue silently:
bash -c 'set -euo pipefail
if ! command -v pacman >/dev/null 2>&1; then echo "WARN non-arch"
elif ! pacman -Q portaudio >/dev/null 2>&1; then echo "MISSING"; exit 1
fi
echo "PASSED-THROUGH ok"'
# Expected stdout: "PASSED-THROUGH ok" (elif skipped). Exit 0.

# (b) MISSING-PORTAUDIO BRANCH — simulate absence with a nonexistent package name:
bash -c 'set -euo pipefail
if ! command -v pacman >/dev/null 2>&1; then echo "WARN non-arch"
elif ! pacman -Q __definitely_not_a_real_pkg__ >/dev/null 2>&1; then
  echo "install.sh: portaudio not installed (PyAudio system dependency). Run: sudo pacman -S --noconfirm portaudio, then re-run ./install.sh" >&2
  exit 1
fi
echo "should-NOT-reach"'; echo "rc=$?"
# Expected: the actionable message on STDERR, then rc=1, and "should-NOT-reach" NOT printed.

# (c) NON-ARCH BRANCH (pacman absent) — simulate with a nonexistent tool name in the condition:
bash -c 'set -euo pipefail
if ! command -v __no_such_pacman_binary__ >/dev/null 2>&1; then
  echo "install.sh: pacman not found — skipping portaudio check (non-Arch host). Install PyAudio portaudio dependency manually." >&2
elif ! pacman -Q portaudio >/dev/null 2>&1; then echo "MISSING"; exit 1
fi
echo "CONTINUED ok"'; echo "rc=$?"
# Expected: the non-Arch warning on STDERR, then "CONTINUED ok", rc=0 (does NOT exit 1).
```

All three must behave as specified. These prove the control flow independent of this machine's
actual portaudio state.

### Level 3: Integration Testing (System Validation — optional, low-risk)

```bash
# Only if Level 1+2 leave any doubt. Because portaudio is installed here, running the real
# installer exercises the new happy-path branch and confirms the script still proceeds.
./install.sh
# Expected: it reaches "==> [1/7] uv sync" (the new check did NOT exit early), runs through to
# "==> [7/7] done", and reports voice-typing.service: active. (The installer is idempotent by
# design — it refreshes deps and restarts the unit; safe to re-run.)
```

### Level 4: Creative & Domain-Specific Validation

Not applicable (a shell preflight guard; no web UI, no MCP, no perf/security targets).

## Final Validation Checklist

### Technical Validation

- [ ] `bash -n install.sh` exits 0.
- [ ] `shellcheck install.sh` introduces no new error for the block (informational SC2312 acceptable).
- [ ] Level 2 simulation (a) prints `PASSED-THROUGH ok` and exits 0.
- [ ] Level 2 simulation (b) prints the exact actionable message to stderr and exits 1; never reaches the success echo.
- [ ] Level 2 simulation (c) prints the non-Arch warning to stderr and exits 0 (continues).

### Feature Validation

- [ ] The portaudio check sits after the `systemctl` check and BEFORE `echo "==> [1/7] uv sync"`.
- [ ] Missing-portaudio message is byte-exact (incl. `sudo pacman -S --noconfirm portaudio, then re-run ./install.sh`) and on **stderr**.
- [ ] pacman-absent (non-Arch) path warns and does **not** `exit 1`.
- [ ] The new block does not abort `install.sh` under `set -euo pipefail` on the happy path (the `pacman -Q` return code is consumed in `elif !` position).

### Code Quality Validation

- [ ] Mirrors the existing preflight idiom (`install.sh:` prefix, stderr, `exit 1`).
- [ ] Em dash `—` reproduced byte-exactly in the non-Arch warning line (matches line 38's style).
- [ ] The edit anchor (systemctl line) is left intact and unchanged.

### Documentation & Deployment

- [ ] No new environment variables (pacman is probed, not configured).
- [ ] README left untouched (line 18 already documents portaudio; changeset-wide README sync is P1.M3.T1.S1).

---

## Anti-Patterns to Avoid

- ❌ Don't call `sudo pacman -S …` from inside `install.sh` — PRD §2 says ask the user to run it manually (non-interactive sudo is not assumed). Print the command; never invoke sudo.
- ❌ Don't put a bare `pacman -Q portaudio` outside an `if !`/`elif !` condition — under `set -euo pipefail` its non-zero return on an absent package would abort the script before the message prints.
- ❌ Don't echo the actionable message to stdout — stdout is the user-facing quick-start (Mode A docs); errors/warnings go to stderr (`>&2`), matching every existing preflight line.
- ❌ Don't `exit 1` on the non-Arch (pacman-absent) path — the contract mandates warn-and-continue so non-Arch hosts aren't hard-blocked by an Arch-only check.
- ❌ Don't edit README.md here — line 18 already documents portaudio and the conditional DOCS clause does not fire; README changeset sync belongs to P1.M3.T1.S1.
- ❌ Don't uninstall/reinstall the system `portaudio` to test — use the scratch-shell simulations (Level 2) instead.
- ❌ Don't add a pytest test for a shell script (mismatched tooling).

---

**Confidence Score: 9.5/10** for one-pass success. The change is a single, fully-specified,
copy-paste-ready preflight block with a byte-exact anchor, a verified-safe `set -e` form,
available linters (`bash -n`, `shellcheck`), and three branch simulations that validate the
logic independent of the machine's portaudio state. The only residual risk is a shellcheck
informational note (SC2312), which is explicitly acceptable.

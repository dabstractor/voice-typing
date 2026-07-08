# Research — install.sh preflight structure & insertion point

## 1. Exact preflight block (install.sh:36-42, verified live)

```
36: # --- preflight: we need a login session for `systemctl --user` + the daemon's own XDG_RUNTIME_DIR ---
37: if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
38:   echo "install.sh: XDG_RUNTIME_DIR is not set — run this from a login session (systemctl --user needs it)." >&2
39:   exit 1
40: fi
41: command -v "$UV" >/dev/null 2>&1 || { echo "install.sh: uv not found at $UV" >&2; exit 1; }
42: command -v systemctl >/dev/null 2>&1 || { echo "install.sh: systemctl not found" >&2; exit 1; }
43: (blank)
44: # XDG_CONFIG_HOME, mirroring voice_typing/config.py (unset/empty -> ~/.config).
45: XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
46: (blank)
47: # --- (2) uv sync -----------------------------------------------------------------
48: echo "==> [1/7] uv sync"
```

- `set -euo pipefail` is at **install.sh:25**.
- The portaudio preflight is inserted **immediately after line 42** (the `systemctl` check),
  before the blank line 43, i.e. it is the LAST preflight check, right before `uv sync`.
- It must run BEFORE `uv sync` (line 48) so a missing `portaudio` is caught before the
  PyAudio wheel is installed (which would otherwise succeed but dlopen-fail at runtime).

## 2. Existing preflight idiom to mirror

Two idioms are used:

- Multi-line `if ...; then echo ... >&2; exit 1; fi` (XDG_RUNTIME_DIR, lines 37-40).
- One-liner `command -v X >/dev/null 2>&1 || { echo "..." >&2; exit 1; }` (uv/systemctl, 41-42).

All error messages:
- Are prefixed `install.sh: `.
- Go to **stderr** (`>&2`).
- Are followed by `exit 1`.
- install.sh's stdout is reserved for the user-facing install/usage quick-start (Mode A docs,
  see install.sh header comment) — so the actionable error MUST be on stderr.

## 3. set -e (errexit) analysis for the new check

`pacman -Q portaudio` returns **non-zero** when the package is NOT installed. Under
`set -euo pipefail`, a bare `pacman -Q portaudio` that fails would abort the script. The
contract therefore mandates the `if ! ... >/dev/null 2>&1; then ...; fi` form, which is
**exempt from errexit** (command lists in an `if`/`elif` condition are never subject to
errexit, and `!` negation in a condition is also exempt). Verified: bash 5.3.15.

So the safe structure is:

```
if ! command -v pacman >/dev/null 2>&1; then
  <warn, non-Arch host, continue>
elif ! pacman -Q portaudio >/dev/null 2>&1; then
  <actionable stderr message>; exit 1
fi
```

Both failing commands (`command -v pacman`, `pacman -Q portaudio`) sit in condition
position, so neither can trip errexit. `>/dev/null 2>&1` suppresses pacman's "error:
package 'portaudio' was not found" stderr noise so the script's own message is what shows.

## 4. Exact message to emit (from the item CONTRACT, verbatim)

On stderr, when pacman is present but portaudio is absent:

```
install.sh: portaudio not installed (PyAudio system dependency). Run: sudo pacman -S --noconfirm portaudio, then re-run ./install.sh
```

When pacman itself is absent (non-Arch host) — warn and CONTINUE (no exit):

```
install.sh: pacman not found — skipping portaudio check (non-Arch host). Install PyAudio's portaudio dependency manually.
```

Note: install.sh's existing echo messages use an **em dash** `—` (U+2014), e.g. line 38
("is not set — run this..."). The non-Arch warning message above uses `—` for consistency.
Reproduce `—` exactly in edits (NOT `-` or `->`).

## 5. Em dash / byte-exact editing gotcha

install.sh line 38 and 42-area use `—` (U+2014). The edit tool matches exact bytes. The
new block's stderr warning line uses `—` too. When writing oldText/newText, reproduce
`—` exactly. The insertion anchor (`command -v systemctl ...` line) contains no em dash,
so the anchor itself is ASCII-safe; only the NEW warning line carries `—`.

## 6. README scope decision

- README.md:18 already documents portaudio: `` - `portaudio` (PyAudio build dep). Check it with `pacman -Q portaudio`. ``
- The Install section's numbered step list (README.md ~30-37) starts at "1. uv sync" and
  does NOT list preflight checks (XDG/uv/systemctl/portaudio are not enumerated).
- The item's DOCS clause is conditional: "If the README's Install section mentions preflight
  checks, note that install.sh now verifies portaudio automatically." Since it does NOT
  mention preflight, the conditional does not fire → **no README change is required** for
  this task. The installer's own stdout/stderr is the primary user-facing doc.
- README changeset-wide sync is owned by a later task, **P1.M3.T1.S1** ("Update README.md
  sections spanning the full changeset"). To avoid a conflict/overlap, this task leaves
  README untouched. (line 18 already covers portaudio; nothing is now stale.)

## 7. Disjointness from in-flight sibling P1.M2.T2.S2

P1.M2.T2.S2 edits `voice_typing/feedback.py`, `voice_typing/typing_backends.py`, and their
tests. This task edits **install.sh only**. Zero file overlap → no merge conflict.
(git status at research time: feedback.py, typing_backends.py, their tests, and
tasks.json are modified by the sibling/orchestrator; install.sh is clean.)

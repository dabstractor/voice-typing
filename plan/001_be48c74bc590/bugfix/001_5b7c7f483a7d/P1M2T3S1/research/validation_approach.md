# Research — validation approach for the install.sh portaudio preflight

## 1. install.sh is a BASH script, not Python — no pytest coverage

There is no automated test for install.sh. The repo's pytest suite (tests/) covers the
Python daemon/config/tools only. install.sh is validated with shell tooling, NOT pytest.

Tool availability (verified live):
- `bash --version` → GNU bash 5.3.15(1)-release.
- `/usr/bin/shellcheck` → present (ShellCheck static analyzer).
- `shfmt` → NOT installed. (Do not require it; skip formatting-via-shfmt.)

## 2. Level 1 — syntax + lint (mandatory, run after the edit)

```bash
bash -n install.sh          # parse/syntax check (no execution)
shellcheck install.sh       # static lint; expect 0 findings for the new block
```

The new block must be shellcheck-clean. Things to confirm:
- No SC2086 (word-splitting) — `portaudio` is a literal package name, no unquoted vars.
- No SC2312 ("consider invoking this command separately") from `>/dev/null 2>&1` — that's
  a style hint, not an error; the `if !`/`elif !` form intentionally suppresses output.
  If SC2312 appears it is informational and acceptable, but the preferred block form
  (`if ! cmd >/dev/null 2>&1; then`) is already the idiomatic suppression.

## 3. Level 2 — branch simulation in a scratch shell (the real logic test)

Because portaudio IS installed on this machine (`pacman -Q portaudio` →
`portaudio 1:19.7.0-4`, exit 0), the happy path runs silently. The two failure branches
MUST be exercised by simulation so we know they fire correctly.

### (a) Happy path (portaudio present) — should continue silently
```bash
set -euo pipefail
if ! command -v pacman >/dev/null 2>&1; then echo "WARN non-arch"
elif ! pacman -Q portaudio >/dev/null 2>&1; then echo "MISSING"; exit 1
fi
echo "PASSED-THROUGH ok"
```
Expected output: `PASSED-THROUGH ok` (the elif condition is false → block is skipped).

### (b) Missing-portaudio branch — should print message + exit 1
Simulate "portaudio absent" by querying a package that does not exist:
```bash
set -euo pipefail
if ! command -v pacman >/dev/null 2>&1; then echo "WARN non-arch"
elif ! pacman -Q __definitely_not_a_real_pkg__ >/dev/null 2>&1; then
  echo "install.sh: portaudio not installed (PyAudio system dependency). Run: sudo pacman -S --noconfirm portaudio, then re-run ./install.sh" >&2
  exit 1
fi
echo "should-NOT-reach"
echo "rc=$?"
```
Expected: the actionable message on stderr, then the shell exits 1; "should-NOT-reach"
is NOT printed. `echo "rc=$?"` confirms exit code 1.

### (c) Non-Arch host branch (pacman absent) — should warn and CONTINUE
Simulate "pacman absent" by shadowing it in PATH (or use a nonexistent tool name in the
condition):
```bash
set -euo pipefail
if ! command -v __no_such_pacman_binary__ >/dev/null 2>&1; then
  echo "install.sh: pacman not found — skipping portaudio check (non-Arch host). Install PyAudio's portaudio dependency manually." >&2
elif ! pacman -Q portaudio >/dev/null 2>&1; then echo "MISSING"; exit 1
fi
echo "CONTINUED ok"
```
Expected: the non-Arch warning on stderr, then `CONTINUED ok` (does NOT exit 1).

All three simulations prove the control flow independently of the machine's actual
portaudio state. The implementer runs these in throwaway subshells (NOT against the real
install.sh) to verify the logic, then runs the real install.sh once for the happy path.

## 4. Level 3 — happy-path end-to-end (optional, low-risk)

Because portaudio is installed on this box, running `./install.sh` for real exercises the
new happy-path branch and confirms the script still proceeds to `uv sync` and beyond. This
re-runs the whole installer (idempotent by design — it refreshes deps, restarts the unit).
Only needed if Level 1+2 leave any doubt; not strictly required for a preflight-only change.
If run: confirm the `[1/7] uv sync` line is reached (portaudio check did not exit early)
and the daemon reports active at the end.

## 5. What NOT to do

- Do not uninstall/reinstall the system portaudio package to test (system mutation, needs
  sudo, risks breaking the working daemon). Use the scratch-shell simulation instead.
- Do not add a pytest test for a shell script (mismatched tooling).
- Do not gate on `shfmt` (not installed).

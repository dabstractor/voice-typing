# Research — P1.M4.T2.S1: Audit launch_daemon.sh (LD_LIBRARY_PATH wrapper & cuDNN discovery vs PRD §4.4)

The design + verification record for the `voice_typing/launch_daemon.sh` compliance audit. The
deliverable is a NEW `gap_launch_daemon.md` report (CREATE, mirroring `gap_typing.md` /
`gap_systemd.md`). Everything below was verified against the LIVE tree (`voice_typing/launch_daemon.sh`,
103 lines; `tests/test_systemd_unit.py`, 15 tests **passing**) + a live lib-discovery probe under
`.venv/bin/python`.

---

## 0. THE VERIFIED VERDICT — `launch_daemon.sh` is COMPLIANT with PRD §4.4 + the work-item contract

All 5 contract points pass (each with file:line evidence below). The wrapper:
1. ✅ **dynamically discovers** the cuBLAS + cuDNN lib dirs from the LIVE installed wheels
   (`"$PY" -c 'import ... nvidia.cublas.lib ... nvidia.cudnn.lib ...'`, launch_daemon.sh:48-52) —
   NOT baked. The live probe resolves both dirs + confirms `libcudnn_ops*.so` + `libcublas*.so` exist
   inside them (§3).
2. ✅ **prepends** them to `LD_LIBRARY_PATH` (launch_daemon.sh:53) with the `${...:+:...}` idiom that
   preserves any pre-existing path + appends `os.pathsep`-correctly.
3. ✅ **exports `HF_HUB_OFFLINE=1`** (launch_daemon.sh:71) — the acceptance-#8 (no network at runtime)
   mechanism.
4. ✅ **re-fetches `WAYLAND_DISPLAY`/`DISPLAY`** from `systemctl --user show-environment`
   (launch_daemon.sh:93-95) — the boot-order-robust fix for the wtype-on-cold-boot regression.
5. ✅ **execs** `"$PY" -m voice_typing.daemon "$@"` (launch_daemon.sh:103).
6. ✅ **NO baked/stale `LD_LIBRARY_PATH`** — the only `LD_LIBRARY_PATH` assignment is the dynamic
   `$CUDA_LIBS` (line 53); the only `/home/` or `site-packages` literal is in a comment (line 22, the
   `ldd` triage hint), never an assignment.

The suite is green: `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` → **15 passed
in 0.01s** (re-run live this round).

**HEADLINE NUANCE (the audit's value-add, mirroring `KillMode=mixed` in gap_systemd.md):** the wrapper's
*NAMESAKE* feature — the dynamic cuBLAS/cuDNN discovery + `LD_LIBRARY_PATH` prepend (contract points 1+2,
the wrapper's literal reason-to-exist per PRD §4.4) — has **NO test coverage**. The two cross-file tests
pin only the LATER bugfix additions (offline vars `:115`; WAYLAND fetch `:164`). A regression on the lib
discovery (a reverted `import nvidia.cublas.lib`, a stale baked path, a broken `_d()` fallback) would
pass the suite silently. This is a **coverage gap, not a code defect** (the code is correct by read +
live probe). §4 documents it as non-blocking — this audit IS the compliance check the suite can't perform.

---

## 1. Per-contract-point evidence table (file:line, re-verified live)

| # | contract requirement (PRD §4.4 / work item) | actual (`voice_typing/launch_daemon.sh`:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|
| 1 | **(a)** discover `nvidia.cublas.lib` + `nvidia.cudnn.lib` paths **dynamically** (not baked) | `CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b ...')"` (:48-52) with the `_d()` namespace-package fallback (`__file__ is None → __path__[0]`, :50-51) | **NONE** — coverage gap §4.1 (the HEADLINE nuance) | ✅ |
| 2 | **(b)** export `LD_LIBRARY_PATH` with those dirs **prepended** | `export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"` (:53) — prepends `$CUDA_LIBS`, preserves any existing path | **NONE** — coverage gap §4.1 | ✅ |
| 3 | **(c)** export `HF_HUB_OFFLINE=1` (acceptance #8) | `export HF_HUB_OFFLINE=1` (:71) + `export TRANSFORMERS_OFFLINE=1` (:72, belt-and-suspenders) | `test_launch_daemon_exports_offline_vars` (:115) — asserts BOTH present + BEFORE exec | ✅ |
| 4 | **(d)** re-fetch `WAYLAND_DISPLAY`/`DISPLAY` from `systemctl --user show-environment` | `for _v in WAYLAND_DISPLAY DISPLAY; do ... systemctl --user show-environment -p "$_v" --value ...` (:93-95) | `test_launch_daemon_fetches_wayland_display_from_manager` (:164) — asserts the fetch + var + BEFORE exec | ✅ |
| 5 | **(e)** exec `python -m voice_typing.daemon` | `exec "$PY" -m voice_typing.daemon "$@"` (:103) | `test_execstart_points_at_launch_daemon_wrapper` (:71, unit-side) + the exec-line assertion in BOTH `:115` + `:164` | ✅ |
| 6 | **no baked/stale `LD_LIBRARY_PATH`** (must survive `uv sync`) | the ONLY `LD_LIBRARY_PATH` assignment is `$CUDA_LIBS` (:53, dynamic); no literal `/home/`/`site-packages` path in any assignment (the only such literal is a comment at :22) | **NONE** — coverage gap §4.1 (but provable by `grep`) | ✅ |

---

## 2. The wrapper's robustness features BEYOND the contract (record so they're not "simplified" away)

These are not strictly required by the 5 contract points but are load-bearing for production correctness.
The audit should note them as compliant extras (not gaps):

- **`set -euo pipefail`** (:30) — fail-fast on any error / unset var / broken pipe (the standard
  shell-discipline guard; the AGENTS.md "PATH shim recurses infinitely" caution is the anti-pattern this
  prevents). Untested.
- **CWD-independent path resolution** (:34-36): `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` →
  `VENV_DIR="$(dirname "$SCRIPT_DIR")"` → `PY="$VENV_DIR/.venv/bin/python"`. Works whether systemd calls
  the absolute ExecStart or a user runs `./launch_daemon.sh` from any cwd. Untested.
- **The `_d()` namespace-package fallback** (:50-51): the faster-whisper README one-liner
  `os.path.dirname(nvidia.cublas.lib.__file__)` would CRASH (`TypeError: expected str, got None`)
  because the `nvidia-*-cu12` wheels ship `nvidia/cublas/lib` + `nvidia/cudnn/lib` as NAMESPACE
  packages (no `__init__.py`, so `.__file__ is None`). `_d()` uses `__file__` for regular packages and
  falls back to `next(iter(m.__path__))` (the lib dir itself) for namespace packages. **This is the
  non-obvious correctness detail** — without it, the wrapper would emit the CPU-fallback warning on
  EVERY launch and cuDNN would never load. Untested (the headline nuance, §4.1).
- **The CPU-fallback `else` branch** (:54-58): if the nvidia wheels can't import (no-GPU host / not yet
  installed), the wrapper logs a clear WARNING + execs python WITHOUT the LD_LIBRARY_PATH override — the
  daemon then detects CUDA failure + falls back to `device=cpu` (PRD §4.4). Untested.
- **`${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` idiom** (:53) — appends `:$existing` only if existing is
  non-empty (avoids a spurious trailing `:`); `os.pathsep`-correct.
- **Idempotent + non-fatal var fetch** (:93-101): `${!_v:-}` (only set if unset — honors an explicit
  override) + `|| true` + `2>/dev/null` (a missing var in the manager env is non-fatal). Untested.
- **TRANSFORMERS_OFFLINE=1** (:72) — belt-and-suspenders (faster-whisper has no transformers dep, but
  harmless + future-proof). Pinned (:115).

---

## 3. Live lib-discovery probe (the empirical proof the dynamic path resolves — run under `.venv/bin/python`)

```
$ timeout 60 .venv/bin/python -c '
import os, nvidia.cublas.lib as a, nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None)
    return os.path.dirname(f) if f else next(iter(m.__path__))
print("cublas:", _d(a)); print("cudnn :", _d(b))
import glob
print("libcudnn_ops present:", bool(glob.glob(os.path.join(_d(b),"libcudnn_ops*.so*"))))
print("libcublas present:", bool(glob.glob(os.path.join(_d(a),"libcublas*.so*"))))'
cublas: /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cublas/lib
cudnn : /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib
libcudnn_ops present: True
libcublas present: True
```

→ The exact `python -c` the wrapper runs (`launch_daemon.sh:48-52`) resolves BOTH lib dirs on the live
machine, AND the `libcudnn_ops*.so` + `libcublas*.so` the daemon's cuDNN/cuBLAS load NEEDS are present
inside them. This is the runtime proof that the dynamic discovery (contract points 1+2) actually works —
which NO test exercises (§4.1). The dirs the wrapper would compute (`/home/.../nvidia/cublas/lib` +
`/home/.../nvidia/cudnn/lib`) are exactly the two `LD_LIBRARY_PATH` entries.

---

## 4. Non-defect nuances (so they are not mistaken for gaps)

### 4.1 THE HEADLINE — the cuBLAS/cuDNN discovery + `LD_LIBRARY_PATH` prepend has NO test coverage

The wrapper exists *for* the `LD_LIBRARY_PATH` override (PRD §4.4 + §8 risk row #1 "cuDNN 'cannot load
libcudnn_ops'"). Yet the two cross-file tests in `test_systemd_unit.py` pin ONLY:
- `test_launch_daemon_exports_offline_vars` (:115) → `^export HF_HUB_OFFLINE=1` + `^export
  TRANSFORMERS_OFFLINE=1` present + BEFORE `exec` (contract point 3).
- `test_launch_daemon_fetches_wayland_display_from_manager` (:164) → `systemctl --user show-environment`
  + `WAYLAND_DISPLAY` present + BEFORE `exec` (contract point 4).

**NEITHER test references `nvidia.cublas.lib` / `nvidia.cudnn.lib` / `CUDA_LIBS` / `LD_LIBRARY_PATH`.**
So a regression on the wrapper's PRIMARY function — a reverted `import nvidia.cublas.lib`, a stale
hardcoded lib path, a broken `_d()` namespace fallback, a dropped `export LD_LIBRARY_PATH=` — would pass
the 15-test suite silently. **This is a coverage gap, not a code defect**: the code is correct (verified
by read §1 + live probe §3). This audit (S1) IS the PRD-§4.4 compliance check the suite cannot perform —
exactly the role `gap_systemd.md`'s `KillMode=mixed` nuance plays for the untested unit directives. A
future test-hardening pass COULD add a `test_launch_daemon_discovers_cuda_libs_dynamically` that greps
for the `import nvidia.cublas.lib` + `export LD_LIBRARY_PATH="$CUDA_LIBS` + absence of a literal lib
path — **out of scope for this read-only audit** (do NOT add a test here; consistent with every
round-006 audit's "read-only, no new tests" discipline).

### 4.2 `LD_LIBRARY_PATH` is read at execve(2) — why it MUST live in the wrapper, not `os.environ`

The dynamic linker (`ld.so(8)`) reads `LD_LIBRARY_PATH` ONLY at process start. Mutating `os.environ`
inside `daemon.py` (after python has started) has NO effect on the already-loaded process — so the
override CANNOT live in daemon.py. The wrapper exports it BEFORE `exec "$PY"` (launch_daemon.sh:53 →
:103), which is the exec point. This is why PRD §4.4 prescribes "a launcher wrapper" and forbids baking
`Environment=LD_LIBRARY_PATH=` in the systemd unit (it would go stale on `uv sync`). Same read-at-start
semantics apply to `HF_HUB_OFFLINE=1` (huggingface_hub latches it at IMPORT TIME, `constants.py`) —
hence it lives in the wrapper, not daemon.py. Both cross-file tests (:115/:164) enforce the BEFORE-exec
ordering for this reason.

### 4.3 `systemctl --user show-environment` is belt-and-suspenders for the cold-boot WAYLAND race

The systemd unit (PRD §4.9, VT-004) is `After=graphical-session.target` + `ExecStartPre=import-environment
WAYLAND_DISPLAY DISPLAY`. But the wrapper's show-environment fetch (:93-95) is the *real* workaround
regardless of boot order: the wrapper is exec'd at daemon start, by which point the compositor has
invariably imported the vars. It's also robust to a manual launch from a stripped environment. Each var
is only set if unset (`${!_v:-}`), so an explicit override wins. A missing var is non-fatal. Pinned
(:164) — this is the validation-Issue-1 wtype-on-cold-boot fix.

### 4.4 The CPU-fallback `else` branch is the no-GPU escape hatch

If the nvidia wheels aren't importable (no-GPU host / pre-`install.sh`), the `if CUDA_LIBS=...; then
...; else ... fi` (:48-58) logs a WARNING + execs python WITHOUT the override. The daemon then probes
cuda_check → `device=cpu, compute_type=int8` (PRD §4.4; the degraded DECISION is cuda_check/daemon's,
P1.M1.T4.S1 — NOT the wrapper's). This keeps the wrapper from hard-failing on a CPU-only box. Untested
but low-risk (the `else` is a single `echo` warning; the `exec` still runs).

---

## 5. Scope discipline + parallel no-conflict

**IN scope (this audit):** `voice_typing/launch_daemon.sh` (all 103 lines — the 5 contract points + the
robustness extras); `tests/test_systemd_unit.py` (the 2 cross-file launch_daemon tests to cite +
re-run); the deliverable `gap_launch_daemon.md`.

**OUT of scope (do NOT touch):**
- `systemd/voice-typing.service` directives → **P1.M4.T1.S1** (`gap_systemd.md`; the parallel sibling —
  it audits the UNIT, this task audits the WRAPPER the unit's ExecStart points at; disjoint files).
- `install.sh` idempotency/prefetch/service-install → **P1.M4.T3.S1**.
- `hypr-binds.conf` → **P1.M4.T4.S1**.
- cuda_check's probe/fallback logic → **P1.M1.T4.S1** (`gap_cuda_check.md` — it records the cuDNN
  limitation as cross-referenced here; the wrapper is cuDNN's *remediation*).
- The daemon teardown mechanism → **P1.M2.T2.S3** (`gap_lifecycle.md`).

**Parallel — P1.M4.T1.S1 (systemd-unit audit, in flight):** DISJOINT files (launch_daemon.sh vs
systemd/voice-typing.service). Both CREATE a `gap_<area>.md` under `architecture/`
(`gap_launch_daemon.md` vs `gap_systemd.md`). No merge conflict. The two cross-file launch_daemon tests
are cited by BOTH reports as evidence (corroborating for the unit's ExecStart; primary for this audit).

---

## 6. Output location + format

- **CREATE** `plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md` (NEW; no prior file). Mirror the
  `gap_typing.md` / `gap_systemd.md` / `gap_cuda_check.md` structure: title → Date → Scope → Audited
  artifacts (read-only) → Bottom line (✅) → §1 Method (commands run + observed output) → §2 per-point
  compliance TABLE (contract req | expected | actual file:line | pinning test | ✅) → §3 live probe →
  §4 Test results (the live count) → §5 Non-defect nuances (§5.1 the headline lib-discovery coverage
  gap; §5.2 read-at-exec; §5.3 WAYLAND belt-and-suspenders; §5.4 CPU-fallback else) → §6 Conclusion
  (PASS; ties to acceptance #8).
- **Do NOT** edit `launch_daemon.sh` / `test_systemd_unit.py` / `PRD.md` / `tasks.json` / any source.
  The wrapper is compliant — read-only audit. The ONLY artifact change is CREATING `gap_launch_daemon.md`.
- Re-verify line numbers live (grep -n) — do NOT copy the PRP's numbers blindly (the file may have
  shifted). Record the LIVE count from the pytest re-run (this research: **15 passed in 0.01s**).

---

## 7. Tooling (AGENTS.md discipline — full paths, two timeouts)

- ALWAYS `.venv/bin/python -m pytest` / `.venv/bin/python` (zsh aliases `python`/`pytest` → uv run).
  `/home/dustin/.local/bin/uv` if needed. NEVER run `voice-typing-daemon` / `launch_daemon.sh` in the
  foreground (Rule 2 — it blocks forever). This audit does NOT exec the wrapper — it READS it + runs the
  pure-stdlib test suite + one `python -c` lib-discovery probe (no daemon, no mic, no GPU model load).
- TWO TIMEOUTS per AGENTS.md Rule 1 on every non-trivial command: inner GNU `timeout 60` + the bash-tool
  `timeout` param above it. The suite is sub-second + pure-stdlib; the lib probe imports ctranslate2?
  NO — only `nvidia.cublas.lib`/`nvidia.cudnn.lib` (cheap namespace packages; ~0.1s). Safe + bounded.
- mypy NOT installed (skip). ruff at `/home/dustin/.local/bin/ruff` is OPTIONAL (the wrapper is bash —
  ruff/mypy/shellcheck do not apply to it; if `shellcheck` is present it's a nice-to-have, not a gate).
- Do NOT create a `tests/__init__.py` or edit any test. The audit only READS test_systemd_unit.py (to
  cite pinning tests) + RUNS it. No new files except `gap_launch_daemon.md`.
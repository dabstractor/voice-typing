# Gap Report — P1.M4.T2.S1: launch_daemon.sh LD_LIBRARY_PATH wrapper & cuDNN discovery vs PRD §4.4

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/launch_daemon.sh` — the systemd ExecStart LD_LIBRARY_PATH wrapper (PRD §4.4
"Realized approach" + §4.9 `ExecStart=__REPO__/voice_typing/launch_daemon.sh` + §8 risk row #1) — against
ALL work-item contract points: (a) **dynamically discovers** `nvidia.cublas.lib` + `nvidia.cudnn.lib` lib
dirs (not baked); (b) **prepends** them to `LD_LIBRARY_PATH`; (c) **exports `HF_HUB_OFFLINE=1`** (acceptance
#8 no-network); (d) **re-fetches `WAYLAND_DISPLAY`/`DISPLAY`** from `systemctl --user show-environment`;
(e) **execs** `python -m voice_typing.daemon`; + **NO baked/stale `LD_LIBRARY_PATH`** — re-verified live
via grep + a live lib-discovery probe (the exact `python -c` the wrapper runs) + the pure-Python
`tests/test_systemd_unit.py` re-run. Subtask **P1.M4.T2.S1** of verification round `006_862ee9d6ef41`.
Satisfies **Acceptance #8** ("no network at runtime — `HF_HUB_OFFLINE=1` is the mechanism the wrapper exports").
**Audited artifacts (all read-only):**
- `voice_typing/launch_daemon.sh` — the 103-line bash wrapper. `set -euo pipefail` (`:30`); CWD-independent
  resolution `SCRIPT_DIR`/`VENV_DIR`/`PY` (`:34`-`:36`); the dynamic discovery
  `CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b ...')"` (`:48`-`:52`)
  with the `_d()` namespace-package fallback (`__file__ is None → __path__[0]`, `:50`-`:51`);
  `export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"` (`:53`); the CPU-fallback
  `else` (WARNING + exec without override, `:54`-`:58`); `export HF_HUB_OFFLINE=1` (`:71`) +
  `export TRANSFORMERS_OFFLINE=1` (`:72`); the `for _v in WAYLAND_DISPLAY DISPLAY; do ... systemctl --user
  show-environment -p "$_v" --value ...` loop (`:93`-`:95`); `exec "$PY" -m voice_typing.daemon "$@"`
  (`:103`). The header comment (`:1`-`28`) documents the WHY (`ld.so` reads `LD_LIBRARY_PATH` at exec;
  the cuDNN `libcudnn_ops` split-sublib triage).
- `tests/test_systemd_unit.py` — the 15-test suite (the contract's run command); pure-stdlib re+pathlib
  (parses the unit + wrapper/install/binds files; NO live systemd/GPU/CUDA/daemon/mic).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.4 (the cuDNN/cuBLAS "launcher wrapper" contract +
  "no baked `Environment=LD_LIBRARY_PATH=`") + §8 risk row #1 (the cuDNN load failure) + §1/§7.8 (100% local /
  acceptance #8) + §4.9 (`ExecStart=__REPO__/voice_typing/launch_daemon.sh`).

**Bottom line:** ✅ `voice_typing/launch_daemon.sh` is **COMPLIANT** with PRD §4.4 + the work-item contract
— all 5 contract points present + correct, NO baked/stale `LD_LIBRARY_PATH` (the only assignment is the
dynamic `$CUDA_LIBS`), the live lib-discovery probe resolves BOTH lib dirs + confirms `libcudnn_ops`/
`libcublas` are present inside them, and the suite is green (**15 passed in 0.01s**, re-run live).
**No source files were modified** — the wrapper faithfully implements the spec. The audit's value-add = the
**headline nuance (§5.1)**: the wrapper's *NAMESAKE* feature (the dynamic cuBLAS/cuDNN discovery +
`LD_LIBRARY_PATH` prepend — PRD §4.4) has **NO test coverage** (the 2 cross-file tests pin only the later
offline-vars + WAYLAND-fetch additions) — so this audit IS the PRD-§4.4 compliance check the suite cannot
perform, recording the gap so a regression (a reverted `import nvidia.cublas.lib`, a stale baked path) cannot
ship silently. Acceptance #8 (no network at runtime) is met: `HF_HUB_OFFLINE=1` (`:71`) is exported
BEFORE `exec` (pinned by `test_launch_daemon_exports_offline_vars`).

---

## 1. Method

Each of the 5 work-item contract points + the no-baked-path check was mapped 1:1 to its
`voice_typing/launch_daemon.sh` implementation by `grep -nE` (the file:line evidence), the header comment
explaining the non-obvious parts (`ld.so` reads `LD_LIBRARY_PATH` at exec; the namespace-package `_d()`
fallback) was read directly, and the dynamic discovery was verified **empirically** — the exact `python -c`
the wrapper runs (`launch_daemon.sh:48`-`52`) was re-executed live to resolve both lib dirs + confirm the
`libcudnn_ops`/`libcublas` shared objects exist inside them (§3). The full `tests/test_systemd_unit.py` suite
was then **re-run live** to record the actual pass count + timing. Nothing was assumed from the PRP's
embedded numbers — every line number + the pass count + the probe output below was re-verified this round
(the suite is pure-stdlib `re`/`pathlib`; the probe imports only the cheap `nvidia.cublas.lib`/`nvidia.cudnn.lib`
namespace packages — no GPU/CUDA/daemon/mic/model-load required).

### Commands run (re-verification)

```bash
# (a)-(e): launch_daemon.sh — the 5 contract points (line-numbered)
grep -nE 'CUDA_LIBS=|nvidia\.cublas\.lib|nvidia\.cudnn\.lib|__path__' voice_typing/launch_daemon.sh          # (a) dynamic discovery + _d() fallback
grep -nE 'export LD_LIBRARY_PATH' voice_typing/launch_daemon.sh                                                # (b) LD_LIBRARY_PATH prepend
grep -nE 'export HF_HUB_OFFLINE=1|export TRANSFORMERS_OFFLINE=1' voice_typing/launch_daemon.sh                 # (c) offline vars
grep -nE 'for _v in WAYLAND_DISPLAY DISPLAY|show-environment' voice_typing/launch_daemon.sh                    # (d) WAYLAND fetch
grep -nE 'exec "\$PY" -m voice_typing\.daemon' voice_typing/launch_daemon.sh                                   # (e) exec
# the no-baked-path check — the ONLY LD_LIBRARY_PATH assignment must be the dynamic $CUDA_LIBS:
grep -nE '^[^#]*LD_LIBRARY_PATH' voice_typing/launch_daemon.sh                                                 # expect: the :53 export ONLY
grep -nE '/home/|site-packages' voice_typing/launch_daemon.sh | grep -v '^[0-9]*:#' || echo "ok: no non-comment /home or site-packages literal"
# the launch_daemon cross-file test functions (coverage to cite):
grep -nE '^def test_(execstart_points_at_launch_daemon_wrapper|launch_daemon_exports_offline_vars|launch_daemon_fetches_wayland_display_from_manager)' tests/test_systemd_unit.py
# confirm the lib-discovery has NO test (the headline coverage gap §5.1):
grep -qE 'def test_.*(cuda_lib|cublas|cudnn|LD_LIBRARY|CUDA_LIBS)' tests/test_systemd_unit.py && echo "a test exists (update §5.1)" || echo "no lib-discovery/LD_LIBRARY_PATH test (coverage gap §5.1)"
# the LIVE lib-discovery probe (the exact python -c the wrapper runs) + the contract's run command (two timeouts per AGENTS.md Rule 1)
timeout 60 .venv/bin/python -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None); return os.path.dirname(f) if f else next(iter(m.__path__))
import glob
print("cublas:",_d(a)); print("cudnn :",_d(b))
print("libcudnn_ops present:",bool(glob.glob(os.path.join(_d(b),"libcudnn_ops*.so*"))))
print("libcublas present:",bool(glob.glob(os.path.join(_d(a),"libcublas*.so*"))))'
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
```

### Observed output (abridged — replace with the LIVE re-verification)

```
set -euo pipefail                                                                     :30
CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b ...')   :48-52
    return os.path.dirname(f) if f else next(iter(m.__path__))   # _d() ns-pkg fallback :50-51
export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"              :53   (ONLY assignment)
export HF_HUB_OFFLINE=1                                                               :71
export TRANSFORMERS_OFFLINE=1                                                         :72
for _v in WAYLAND_DISPLAY DISPLAY; do ... systemctl --user show-environment ...       :93-95
exec "$PY" -m voice_typing.daemon "$@"                                                :103
(no non-comment /home or site-packages literal — no baked path)
(no lib-discovery/LD_LIBRARY_PATH test — coverage gap §5.1)
cublas: /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cublas/lib
cudnn : /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib
libcudnn_ops present: True
libcublas present: True
15 passed in 0.01s
```

---

## 2. Per-contract-point Compliance Table (work-item contract / PRD §4.4 vs `voice_typing/launch_daemon.sh`)

| # | contract requirement | expected | actual (file:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| (a) | **discover** `nvidia.cublas.lib` + `nvidia.cudnn.lib` paths **dynamically** (not baked) | a `python -c` import computing the dirs from the LIVE wheels (survives `uv sync`) | `CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b …')"` (`:48`-`:52`) + the `_d()` namespace-package fallback (`:50`-`:51`) | (none — **coverage gap §5.1**, the HEADLINE nuance) | ✅ |
| (b) | **prepend** those dirs to `LD_LIBRARY_PATH` | `export LD_LIBRARY_PATH="<dirs>${existing:+:$existing}"` | `export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"` (`:53`) — prepends `$CUDA_LIBS`, preserves any existing path (the `:+` idiom avoids a spurious trailing `:`) | (none — **coverage gap §5.1**) | ✅ |
| (c) | **export `HF_HUB_OFFLINE=1`** (acceptance #8) | `export HF_HUB_OFFLINE=1` BEFORE exec | `export HF_HUB_OFFLINE=1` (`:71`) + `export TRANSFORMERS_OFFLINE=1` (`:72`, belt-and-suspenders) | `test_launch_daemon_exports_offline_vars` (`:115`) — asserts BOTH present (`^export`-anchored) + BEFORE `exec` | ✅ |
| (d) | **re-fetch** `WAYLAND_DISPLAY`/`DISPLAY` from `systemctl --user show-environment` | a fetch loop reading the user-manager env | `for _v in WAYLAND_DISPLAY DISPLAY; do … _val="$(systemctl --user show-environment -p "$_v" --value …)" …` (`:93`-`:95`) — idempotent (`${!_v:-}`) + non-fatal (`|| true`) | `test_launch_daemon_fetches_wayland_display_from_manager` (`:164`) — asserts the fetch + `WAYLAND_DISPLAY` + BEFORE `exec` | ✅ |
| (e) | **exec** `python -m voice_typing.daemon` | `exec "$PY" -m voice_typing.daemon "$@"` | `exec "$PY" -m voice_typing.daemon "$@"` (`:103`) | `test_execstart_points_at_launch_daemon_wrapper` (`:71`, unit-side) + the exec-line assertion in BOTH `:115` + `:164` | ✅ |
| (f) | **NO baked/stale `LD_LIBRARY_PATH`** | the only `LD_LIBRARY_PATH` assignment is the dynamic `$CUDA_LIBS`; no literal lib path | CONFIRMED: `grep -nE '^[^#]*LD_LIBRARY_PATH'` → the `:53` export ONLY (the only other hit is `:56`, inside the quoted WARNING `echo` message of the CPU-fallback `else` branch — not an assignment); the only `/home/`/`site-packages` literal is a COMMENT (`:22`, the `ldd` triage hint), never an assignment | (none — coverage gap §5.1, but provable by grep) | ✅ |

> All contract points **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this round.
> The two untested points (a)+(b)+(f) are confirmed correct by direct read + the live lib probe (§3); the
> gap is recorded as a non-blocking coverage observation in §5.1.

### Robustness extras (compliant, beyond the 5 contract points — recorded so they are not "simplified" away)

| extra | actual (file:line) | why it matters | tested? |
|---|---|---|---|
| `set -euo pipefail` | `:30` | fail-fast on any error / unset var / broken pipe (the AGENTS.md PATH-shim anti-pattern this prevents) | no |
| CWD-independent path resolution (`SCRIPT_DIR`/`VENV_DIR`/`PY`) | `:34`-`:36` | works whether systemd calls the absolute ExecStart or a user runs `./launch_daemon.sh` from any cwd | no |
| the `_d()` namespace-package fallback (`__file__ is None → __path__[0]`) | `:50`-`:51` | WITHOUT it the faster-whisper README one-liner `os.path.dirname(nvidia.cublas.lib.__file__)` would CRASH (`TypeError`: `__file__` is `None` for the namespace-package `nvidia/cublas/lib`) → cuDNN would never load | no |
| `${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` idiom | `:53` | appends `:$existing` only if non-empty (no spurious trailing `:`); `os.pathsep`-correct | no |
| CPU-fallback `else` branch (WARNING + exec without override) | `:54`-`:58` | if the nvidia wheels aren't importable (no-GPU host), exec python WITHOUT the override → the daemon falls back to `device=cpu` (PRD §4.4) | no |
| TRANSFORMERS_OFFLINE=1 | `:72` | belt-and-suspenders (faster-whisper has no transformers dep, but harmless + future-proof) | yes (`:115`) |

---

## 3. Live lib-discovery probe (the runtime proof contract points (a)+(b) work — which NO test exercises)

```
$ timeout 60 .venv/bin/python -c '
import os, nvidia.cublas.lib as a, nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None); return os.path.dirname(f) if f else next(iter(m.__path__))
import glob
print("cublas:", _d(a)); print("cudnn :", _d(b))
print("libcudnn_ops present:", bool(glob.glob(os.path.join(_d(b),"libcudnn_ops*.so*"))))
print("libcublas present:", bool(glob.glob(os.path.join(_d(a),"libcublas*.so*"))))'
cublas: /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cublas/lib
cudnn : /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib
libcudnn_ops present: True
libcublas present: True
```

→ The exact `python -c` the wrapper runs (`launch_daemon.sh:48`-`52`) resolves BOTH lib dirs on the live
machine, AND the `libcudnn_ops*.so` + `libcublas*.so` the daemon's cuDNN/cuBLAS load NEEDS are present inside
them. The dirs the wrapper would compute (printed above) are exactly the two `LD_LIBRARY_PATH` entries it
prepends. **This is the runtime proof contract points (a)+(b) actually work** — which no unit test exercises
(§5.1). (If the probe can't import the wheels on this host — no nvidia packages installed — record that +
note the wrapper's CPU-fallback `else` branch §5.4 still applies; the daemon would then run `device=cpu`.)

---

## 4. Test results (the contract's run command, LIVE)

```
$ timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
...............                                                          [100%]
15 passed in 0.01s
```

The suite (440 lines, 15 tests) is pure-stdlib `re`/`pathlib`: it parses `systemd/voice-typing.service` +
`voice_typing/launch_daemon.sh` + `install.sh` + `hypr-binds.conf` — no GPU/CUDA/daemon/mic. **3 tests pin
this wrapper's behavior**: `test_launch_daemon_exports_offline_vars` (`:115`, contract point (c) +
BEFORE-exec ordering), `test_launch_daemon_fetches_wayland_display_from_manager` (`:164`, contract point
(d) + BEFORE-exec ordering), `test_execstart_points_at_launch_daemon_wrapper` (`:71`, the unit-side
ExecStart→wrapper assertion). **Coverage gap**: NO test pins contract points (a) the dynamic discovery,
(b) the `LD_LIBRARY_PATH` prepend, or (f) the no-baked-path check (§5.1) — the wrapper's PRIMARY function.

---

## 5. Non-defect nuances (so they are not mistaken for gaps)

### 5.1 THE HEADLINE — the cuBLAS/cuDNN discovery + `LD_LIBRARY_PATH` prepend has NO test coverage (coverage gap, NOT a code defect)
The wrapper exists *for* the `LD_LIBRARY_PATH` override (PRD §4.4 + §8 risk row #1 "cuDNN 'cannot load
libcudnn_ops' at runtime"). Yet the two cross-file tests in `test_systemd_unit.py` pin ONLY:
`test_launch_daemon_exports_offline_vars` (`:115`) → `^export HF_HUB_OFFLINE=1` + `^export
TRANSFORMERS_OFFLINE=1` present + BEFORE `exec` (contract point (c)); and
`test_launch_daemon_fetches_wayland_display_from_manager` (`:164`) → `systemctl --user show-environment`
+ `WAYLAND_DISPLAY` present + BEFORE `exec` (contract point (d)). **NEITHER references `nvidia.cublas.lib` /
`nvidia.cudnn.lib` / `CUDA_LIBS` / `LD_LIBRARY_PATH`.** So a regression on the wrapper's PRIMARY function —
a reverted `import nvidia.cublas.lib`, a stale hardcoded lib path, a broken `_d()` namespace fallback, a
dropped `export LD_LIBRARY_PATH=` — would pass the 15-test suite silently. **This is a coverage gap, not a
code defect**: the code is correct (verified by read §2 + live probe §3). This audit (S1) IS the PRD-§4.4
compliance check the suite cannot perform — exactly the role `gap_systemd.md`'s `KillMode=mixed` nuance plays
for the untested unit directives. A future test-hardening pass COULD add a
`test_launch_daemon_discovers_cuda_libs_dynamically` (grep for `import … nvidia.cublas.lib` +
`export LD_LIBRARY_PATH="$CUDA_LIBS` + the absence of a literal lib path) — **out of scope for this
read-only audit** (do NOT add a test here; consistent with every round-006 audit's "read-only, no new tests"
discipline). ✅

### 5.2 `LD_LIBRARY_PATH` + `HF_HUB_OFFLINE` are read at execve/import time — why they MUST live in the wrapper, not `os.environ`
The dynamic linker (`ld.so(8)`) reads `LD_LIBRARY_PATH` ONLY at process start. Mutating `os.environ` inside
`daemon.py` (after python has started) has NO effect on the already-loaded process — so the override CANNOT
live in daemon.py. The wrapper exports it BEFORE `exec "$PY"` (`:53` → `:103`), which is the execve
point. This is why PRD §4.4 prescribes "a launcher wrapper" and forbids baking
`Environment=LD_LIBRARY_PATH=` in the systemd unit (it would go stale on `uv sync`). Same read-at-start
semantics apply to `HF_HUB_OFFLINE=1` (`huggingface_hub` latches it at IMPORT TIME, `constants.py`) — hence
it lives in the wrapper, not daemon.py. Both cross-file tests (`:115` / `:164`) enforce the BEFORE-exec
ordering for this reason. ✅

### 5.3 The WAYLAND `show-environment` fetch is belt-and-suspenders for the cold-boot race
The systemd unit (PRD §4.9, VT-004) is `After=graphical-session.target` + `ExecStartPre=import-environment
WAYLAND_DISPLAY DISPLAY`. But the wrapper's `show-environment` fetch (`:93`-`:95`) is the *real*
workaround regardless of boot order: the wrapper is exec'd at daemon start, by which point the compositor
has invariably imported the vars. It is also robust to a manual launch from a stripped environment. Each var
is only set if unset (`${!_v:-}`, `:97`), so an explicit override wins; a missing var is non-fatal
(`|| true`, `:95`). Pinned (`:164`) — this is the validation-Issue-1 wtype-on-cold-boot fix. ✅

### 5.4 The CPU-fallback `else` branch is the no-GPU escape hatch
If the nvidia wheels aren't importable (no-GPU host / pre-`install.sh`), the `if CUDA_LIBS=…; then …; else
…; fi` (`:48`-`:58`) logs a clear WARNING + execs python WITHOUT the override. The daemon then probes
`cuda_check` → `device=cpu, compute_type=int8` (PRD §4.4; the degraded DECISION is cuda_check/daemon's,
P1.M1.T4.S1 → `gap_cuda_check.md` — NOT the wrapper's). This keeps the wrapper from hard-failing on a
CPU-only box. Untested but low-risk (the `else` is a single `echo` warning; the `exec` still runs). ✅

---

## 6. Conclusion

**PASS.** `voice_typing/launch_daemon.sh` is compliant with PRD §4.4 + the work-item contract on all 5
points + the no-baked-path check. It dynamically discovers the cuBLAS/cuDNN lib dirs from the LIVE installed
wheels (`:48`-`:52`, with the `_d()` namespace-package fallback `:50`-`:51`), prepends them to
`LD_LIBRARY_PATH` (`:53`), exports `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` (`:71`-`:72`),
re-fetches `WAYLAND_DISPLAY`/`DISPLAY` from the user manager (`:93`-`:95`), and execs the daemon
(`:103`) — with NO baked `LD_LIBRARY_PATH` (the only assignment is the dynamic `$CUDA_LIBS`). The live
lib-discovery probe (§3) resolves both dirs + confirms `libcudnn_ops`/`libcublas` are present; the 15-test
suite pins the offline vars + WAYLAND fetch + ExecStart→wrapper (the BEFORE-exec ordering enforced). The
**headline nuance (§5.1)**: the wrapper's PRIMARY function (the cuBLAS/cuDNN discovery + `LD_LIBRARY_PATH`
prepend) has NO test coverage — this audit IS that compliance check. **No source files were modified**
(read-only audit); the sole artifact is this report.

Acceptance #8 ("no network at runtime") is met: `HF_HUB_OFFLINE=1` (`:71`) is the mechanism. Scope is
`launch_daemon.sh` ONLY — the systemd unit directives are P1.M4.T1.S1 (`gap_systemd.md`), `install.sh` is
P1.M4.T3.S1, `hypr-binds.conf` is P1.M4.T4.S1, cuda_check's probe is P1.M1.T4.S1 (`gap_cuda_check.md` §6-obs1,
which records the cuDNN limitation THIS wrapper remediates), and the daemon teardown is P1.M2.T2.S3
(`gap_lifecycle.md`).
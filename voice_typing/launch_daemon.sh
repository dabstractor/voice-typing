#!/usr/bin/env bash
#
# launch_daemon.sh — LD_LIBRARY_PATH wrapper for the voice-typing daemon.
#
# WHY: faster-whisper / ctranslate2 load the cuBLAS + cuDNN 9 shared libraries that ship
# inside the `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` pip wheels. The dynamic linker
# reads LD_LIBRARY_PATH ONLY at process exec (ld.so(8)), so it must be exported BEFORE
# python starts — mutating os.environ inside daemon.py has NO effect on the running
# process. This wrapper is the sanctioned fix (PRD §8 risk row #1:
# "cuDNN 'cannot load libcudnn_ops' at runtime → LD_LIBRARY_PATH wrapper per §4.4").
#
# The lib dirs are recomputed from the LIVE installed wheels on every launch, so this
# script survives `uv sync` reinstalls and version bumps without edits.
#
# DEBUGGING "cannot open shared object file: libcudnn_ops.so.9" (also libcudnn.so.9,
# libcublas.so.12): cuDNN 9's split sub-libs (libcudnn_ops/cnn/eng/...) are resolved
# transitively by the loader and the wheels lack a $ORIGIN RUNPATH for them, so they
# MUST be on LD_LIBRARY_PATH. Triage, fastest first:
#   1. journalctl --user -u voice-typing -e                  # wrapper stderr + python logs
#   2. systemctl --user show voice-typing -p Environment     # is LD_LIBRARY_PATH set?
#   3. LD_DEBUG=libs voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn
#   4. ldd .venv/lib/python3.12/site-packages/nvidia/cudnn/lib/libcudnn.so.9   # NEEDED not found?
#   5. strace -f -e openat voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn
# (See PRD §8 "cuDNN cannot load libcudnn_ops" risk row.)
#
# CPU FALLBACK: if the nvidia wheels aren't importable (no-GPU host / not yet installed),
# this script logs a clear warning and execs python WITHOUT the override. The daemon then
# detects CUDA failure and runs device="cpu", compute_type="int8" (PRD §4.4; the
# degraded-mode DECISION is made in P1.M1.T2.S2, not here).
set -euo pipefail

# Resolve own location CWD-independently (systemd calls us via absolute ExecStart; this
# also works for a manual `./launch_daemon.sh` from any working directory).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"   # .../voice_typing  (this file's dir)
VENV_DIR="$(dirname "$SCRIPT_DIR")"            # repo root          (parent of voice_typing/)
PY="$VENV_DIR/.venv/bin/python"

# Compute the cuBLAS + cuDNN lib dirs from the LIVE installed wheels.
#
# ACCESSOR NOTE: the faster-whisper README one-liner is
#   os.path.dirname(nvidia.cublas.lib.__file__)
# but the nvidia-*-cu12 wheels ship nvidia/cublas/lib and nvidia/cudnn/lib as NAMESPACE
# packages (no __init__.py), so .__file__ is None there and os.path.dirname(None) raises
# TypeError while the IMPORT itself succeeds. _d() therefore uses __file__ when the module
# is a regular package, and falls back to __path__[0] (the lib dir itself) for namespace
# packages. This still computes from the live import — it survives `uv sync` (Gotcha #4
# intent) and is NOT hardcoded.
if CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None)
    return os.path.dirname(f) if f else next(iter(m.__path__))
print(_d(a)+":"+_d(b))' 2>/dev/null)"; then
    export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
else
    echo "voice-typing: WARNING — could not import nvidia.cublas.lib / nvidia.cudnn.lib;" \
         "continuing WITHOUT the LD_LIBRARY_PATH override (CPU fallback path)." \
         "Expect CUDA init to fail; the daemon should fall back to device=cpu." >&2
fi

# HF offline guarantee (PRD §1 "100% local" + acceptance §7.8; bugfix Issue 1). Models are
# prefetched at install time (install.sh -> prefetch.py -> ~/.cache/huggingface/hub), so the
# daemon loads them from cache with ZERO network. HF_HUB_OFFLINE=1 makes huggingface_hub
# (hence faster-whisper / RealtimeSTT) cache-only — it skips the freshness GET to
# https://huggingface.co that online mode fires every startup (journal proved 2 GETs/startup,
# one per model). huggingface_hub reads this flag at IMPORT TIME (constants.py), so it MUST be
# in the env BEFORE python starts; exporting here is strictly more correct than os.environ in
# daemon.py (same reason LD_LIBRARY_PATH lives here). Uncached model -> fail-fast
# LocalEntryNotFoundError by design (no lazy download). TRANSFORMERS_OFFLINE=1 is harmless
# belt-and-suspenders (faster-whisper has no transformers dep). Keep in the wrapper, NOT the
# systemd unit Environment= (unit line 29 forbids it; wrapper is the single env source).
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

exec "$PY" -m voice_typing.daemon "$@"

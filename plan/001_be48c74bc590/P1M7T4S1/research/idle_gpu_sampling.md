# Research — P1.M7.T4.S1: idle-stability (T4) + GPU-residency (T6) + acceptance

Scope: the empirical facts + external citations that `tests/test_idle_and_gpu.sh` and
`tests/ACCEPTANCE.md` depend on. Every "Verified" claim was run on this machine
(Arch Linux, kernel 7.0.12-arch1-1, NVIDIA RTX 3080 Ti / driver 610.43.02). No daemon was
running while these checks were taken (the GPU showed unrelated Chrome + a transient
`.venv/bin/python` from the parallel T3 run — itself evidence for G-OTHER-APPS below).

---

## 1. CPU averaging via /proc (no pidstat available)

**Problem.** `pidstat` (sysstat) is NOT installed (`which pidstat` → empty). PRD §6 T4 allows
"`pidstat` OR /proc sampling" — we use /proc (zero deps, guaranteed present).

**Verified facts.**

- `getconf CLK_TCK` → **100**. So `cpu_seconds = ticks / 100`.
- `/proc/self/stat` parse: field (2) `comm` is in parens and MAY contain spaces/parens; the only
  robust parse is to split on the LAST `)`, then split the remainder by whitespace. After that
  split, the remainder index map is: `rest[0]`=field(3) state, `rest[1]`=field(4) ppid, …
  `rest[11]`=**field(14) utime**, `rest[12]`=**field(15) stime**. Verified: for a fresh `cat`,
  `rest[11]=1, rest[12]=0`.
- For a **multithreaded** process, `/proc/<pid>/stat` utime+stime ALREADY aggregates all threads of
  the process (same task group). See §4 below — on Linux RealtimeSTT workers are THREADS, so the
  daemon PID's stat already includes their CPU. We STILL sum over the process tree (defensive —
  SafePipe may spawn a real process; see §4).
- `/proc/<pid>/task/<pid>/children` lists DIRECT children (recurse to get the tree). pgrep -P also
  works (`/usr/bin/pgrep`, `/usr/bin/pstree` both present). The python helper in the PRP reads
  /proc directly (no external dep).

**External citation.** `man 5 proc_pid_stat` — man7.org/linux/man-pages:
https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html
> "(14) utime  %lu  Amount of time that this process has been scheduled in user mode, measured in
> clock ticks (divide by sysconf(_SC_CLK_TCK)). … (15) stime  %lu  Amount of time … in kernel mode …"

**Threshold math.** PRD §6 T4: "CPU < 25% of ONE core on average". nproc=24, but the unit is ONE
core, so:
```
avg_pct_of_one_core = (Σ Δticks over daemon tree / CLK_TCK) / wall_elapsed_s * 100   # assert < 25
```
(Do NOT divide by nproc — it is % of one core, not % of all cores.)

**Implication for the test:** read utime+stime (fields 14/15 via last-`)` split) for the daemon PID
+ every descendant at T0 (right after `voicectl start`, armed) and T1 (after the 120 s window);
divide the summed-tick delta by 100 and by elapsed wall seconds; assert < 25.

---

## 2. nvidia-smi --query-compute-apps (T6 residency)

**Verified output format (real run on this machine).**
```
$ nvidia-smi --query-compute-apps=pid,used_memory --format=csv
pid, used_gpu_memory [MiB]
2624394, 164 MiB
3664501, 2804 MiB
```
- Header line = `pid, used_gpu_memory [MiB]`; value rows = `<pid>, <int> MiB`.
- `--format=csv,noheader` drops the header.
- **GOTCHA (G-VRAM-COMMAS):** adding `process_name` to the query can emit a field containing
  COMMAS (observed: Chrome's `--type=gpu-process …` cmdline is one giant comma-laden CSV field),
  which breaks naive `cut -d,` parsing. ⇒ Query ONLY `pid,used_memory`. Strip ` MiB` from the
  second column and `int()` it.

**Per-process semantics.** nvidia-smi reports, per row, the process that **owns the CUDA context /
made the allocation** (the "used_gpu_memory" per-process value), in MiB. NVIDIA developer forum:
https://forums.developer.nvidia.com/t/unified-memory-nvidia-smi-memory-usage-interpretation/177372
> "GPU Memory Usage (the bottom value, that is per-process) represents the size of the CUDA context
> (in the range of a few 100s of MiBs). …"

**Implication:** a process that spawns subprocesses which each create their OWN CUDA context
appears as SEPARATE rows. ⇒ Match the daemon's whole process tree against the compute-apps PIDs and
**sum** `used_memory` over the matched rows (see §4: on Linux the workers are threads so it is one
row, but the tree-match is the robust, version-proof approach).

**Other apps are present (G-OTHER-APPS).** At test time the GPU routinely hosts unrelated compute
apps (Chrome GPU process 164 MiB; observed a `.venv/bin/python` at 2804 MiB during the parallel T3
run). The test MUST filter by the daemon's PID tree and NEVER assert on an arbitrary row.

**Range (T6).** PRD §6 T6: used_memory "~1 and ~5 GB". distil-large-v3 (float16) ≈ 1.5–2.5 GiB +
small.en ≈ 0.5 GiB ⇒ typically ~2–3 GiB total. Assert: ≥1 matched compute-app row in the daemon
tree AND Σ used_memory ∈ [1024, 5120] MiB.

---

## 3. HF_HUB_OFFLINE = criterion 8 proof (no network at runtime)

**Verified machine fact.** All four repos are cached locally:
```
~/.cache/huggingface/hub/
  models--Systran--faster-distil-whisper-large-v3   # distil-large-v3 (FINAL, CUDA)
  models--Systran--faster-whisper-small.en          # small.en (REALTIME / CPU-fallback FINAL)
  models--Systran--faster-whisper-tiny.en           # tiny.en (CPU-fallback REALTIME)
  models--mobiuslabsgmbh--faster-whisper-large-v3-turbo
```
(prefetched by install.sh → `python -m voice_typing.prefetch`; idempotent; re-runs skip cached
blobs). faster-whisper's `WhisperModel(model="distil-large-v3", device="cuda", …)` resolves the
short name → repo_id and finds the weights in this cache.

**External citation.** huggingface_hub docs:
https://huggingface.co/docs/huggingface_hub/package_reference/utilities
> "You can programmatically check if offline mode is enabled using is_offline_mode. Offline mode is
> enabled by setting HF_HUB_OFFLINE=1 as environment variable."

And huggingface_hub issue #2590 (https://github.com/huggingface/huggingface_hub/issues/2590): with
`HF_HUB_OFFLINE=1`, any HfApi network method raises `OfflineModeIsEnabled` — i.e. it is a HARD
offline switch (no HTTP; cache-only). `TRANSFORMERS_OFFLINE=1` is the transformers-library twin.

**Implication (G-OFFLINE):** launch the daemon with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` in its
env. If the daemon STARTS, goes ready (`voicectl status` answers), and survives the 120 s armed-idle
window, that is empirical proof the models load from cache with ZERO network access ⇒ criterion 8.
If it cannot (a repo is missing), it fails at startup — a real, machine-checked failure, not a
claim. (This is stronger than merely `ls`-ing the cache: it proves the daemon's actual load path is
offline-clean.)

---

## 4. RealtimeSTT worker model — threads on Linux (KEY nuance)

**Verified from the INSTALLED package** (`.venv/lib/python3.12/site-packages/RealtimeSTT/`):

`core/runtime.py:25-37` — `start_recorder_worker`:
```python
def start_recorder_worker(target=None, args=()):
    if (platform.system() == 'Linux'):
        thread = threading.Thread(target=target, args=args)
        thread.deamon = True          # NOTE: library typo "deamon"; daemon thread
        thread.start()
        return thread
    else:
        thread = mp.Process(target=target, args=args)
        thread.start()
        return thread
```
⇒ **On Linux the `transcript_process` and `reader_process` are THREADS, not processes.** They run in
the SAME process (the daemon's main python PID). The CUDA context / `WhisperModel` is created inside
that same process (the transcription worker thread calls
`faster_whisper.WhisperModel(device=self.config.device, …)` — `transcription_engines/
faster_whisper_engine.py:45`). Therefore, on this machine **nvidia-smi reports the daemon's MAIN
python PID** for the compute-app row, and the daemon PID's `/proc/<pid>/stat` utime+stime already
includes the worker threads' CPU.

**BUT** `core/initialization.py:390-396` calls `SafePipe()` unconditionally, and
`core/safepipe.py:196` does `p = mp.Process(target=child_process_code, …)` (with
`set_start_method("spawn")` at safepipe.py:17/19 and initialization.py:355). So a REAL child process
MAY exist (the stdout-forwarding pipe). That child does NOT create a CUDA context, but it IS a
descendant process whose CPU should be counted.

`daemon.py`'s docstring ("spawn-started multiprocessing workers") describes the NON-Linux path and
is precautionary (the `if __name__ == "__main__":` guard is still correct to keep). On Linux it is
over-conservative but harmless.

**Implication for the test:** treat the daemon as a PROCESS TREE (PID + all descendants) for BOTH
the CPU sum and the VRAM match. On Linux this is effectively the single daemon PID (workers are
threads), but the tree-match is correct whether workers are threads or processes and survives any
future RealtimeSTT change. (This is why the PRP uses a descendant walk, not a bare `pgrep -f
voice_typing`.)

---

## 5. system facts reused (corroborated, not re-derived)

From `architecture/system_context.md` + direct checks:
- `/usr/bin/nvidia-smi` present (610.43.02). `/usr/bin/pgrep`, `/usr/bin/pstree` present.
- `/usr/bin/tmux` (zsh aliases tmux → always full path). `.venv/bin/voicectl`, `.venv/bin/python`.
- GPU = RTX 3080 Ti, 12 GiB VRAM. Budget for both models ≈ 2–4 GiB float16.
- Daemon starts NOT-listening (PRD §4.9; `daemon.py` `self._listening = threading.Event()` cleared
  at boot) ⇒ `voicectl status` shows `listening: off` right after ready — this is the criterion-6
  "starts un-armed" evidence.
- systemd unit `systemd/voice-typing.service`: `ExecStart=…/launch_daemon.sh`, `Restart=on-failure`,
  `RestartSec=2`. "auto-restart on failure" = `Restart=on-failure`; the unit boots un-armed (above).
- Control socket is pinned to `$XDG_RUNTIME_DIR/voice-typing/control.sock` (no override without
  editing daemon.py) ⇒ PREFLIGHT: refuse if a daemon is already running (reuse T3's preflight).
- This test does NOT swap the default audio source (no null-sink — it listens to ambient silence via
  the real mic). ⇒ the trap is simpler than T3's (no source restore); but it DOES touch the real
  control socket + a tmux pane + a temp config ⇒ preflight + tmux-session-name isolation still apply.

## 6. what T4/T6 actually assert (the contract)

- **T4 (idle stability, criterion 5 — CRITICAL):** armed + 120 s silence → (a) no finals typed
  (capture-pane via the tmux backend UNCHANGED + `state.json last_final` UNCHANGED from its
  initial `""` — the hallucination guard: the P1.M2.T2.S1 blocklist + VAD gating suppress Whisper's
  silence-hallucination); (b) daemon alive after 120 s (no crash, `kill -0`); (c) avg CPU < 25% of
  one core (§1 math).
- **T6 (GPU residency):** `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`;
  ≥1 daemon-tree PID present AND Σ used_memory ∈ [1024, 5120] MiB.
- **criterion 6 (CRITICAL):** `voicectl toggle/start/stop/status/quit` all run + return ok; the
  unit file shows `ExecStart → launch_daemon.sh` + `Restart=on-failure`; the post-ready status
  shows `listening: off` (starts un-armed).
- **criterion 8 (CRITICAL, no-network):** the daemon ran the whole test under
  `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` and loaded the cached models (§3).
- **criteria 1, 2, 3, 4, 7:** ACCEPTANCE.md references the sibling tests (T1=`test_feed_audio.py`,
  T2=`test_textproc.py`, T3=`e2e_virtual_mic.sh`) for 1–4 and `git status`/README-pending for 7.

# Research — P1.M4.T3.S2: prefetch.py model download logic audit (§4.4)

**Task:** READ-ONLY audit of `voice_typing/prefetch.py` (168 lines) — the install-time model
prefetch that guarantees Acceptance #8 ("No network access needed at runtime (models cached by
install)"). Deliverable: `plan/006_862ee9d6ef41/architecture/gap_prefetch.md`.
**Verdict (research): ✅ prefetch.py is COMPLIANT** with PRD §4.4 + the work-item contract (a)-(e).
All 4 repos verified cached; the short-name→repo_id chain is load-bearing-correct; no test exists
(coverage gap, not a defect).

---

## §0. THE VERIFIED VERDICT — prefetch.py COMPLIANT

All 5 contract points (a)-(e) PASS with file:line evidence. prefetch.py is a **STRICT SUPERSET**
of the PRD §4.4 install-time minimum: it downloads **4 repos**, not the 2 the work-item/PRD §4.4
note literally name (those 2 + tiny.en for the CPU-fallback path + large-v3-turbo for the approved
substitute). This is MORE correct, not less — see Nuance §4.1 (the headline).

### Live cache verification (this research — `os.path.getsize` follows the snapshot symlink)

```
~/.cache/huggingface/hub/
├── models--Systran--faster-distil-whisper-large-v3       model.bin = 1.51 GB   ✅ (CORE, FINAL, CUDA default)
├── models--Systran--faster-whisper-small.en               model.bin = 0.48 GB   ✅ (CORE, REALTIME/partials + CPU-fallback FINAL + lite default)
├── models--Systran--faster-whisper-tiny.en                model.bin = 0.08 GB   ✅ (CORE, CPU-fallback REALTIME)
└── models--mobiuslabsgmbh--faster-whisper-large-v3-turbo  model.bin = 1.62 GB   ✅ (OPTIONAL, approved substitute)
                                                                    TOTAL ≈ 3.69 GB cached
```
→ Acceptance #8 ("no network at runtime, models cached by install") SATISFIED for ALL paths
(CUDA, CPU-fallback, lite, and the turbo substitute). NOTE: a bare `find -name model.bin -printf
%s` reports the **symlink stub size** (~76 B = the `../../../blobs/<sha>` path length), NOT the real
blob — use `os.path.getsize` (which follows symlinks) or `stat -L` for the true size. This is the
same path prefetch.py's `_model_bin_size()` (prefetch.py:86-92) takes.

---

## §1. THE 5-CONTRACT-POINT TABLE (prefetch.py vs work-item contract / PRD §4.4)

| # | contract requirement | code actual (prefetch.py:line — re-verified live) | verdict |
|---|---|---|---|
| (a) | downloads both model repos via `snapshot_download` | `from huggingface_hub import snapshot_download` (lazy, :68) + `snapshot_download(repo_id=repo_id, repo_type="model")` (:76) iterated over CORE+OPTIONAL (4 repos). EXCEEDS the 2-repo minimum (Nuance §4.1) | ✅ |
| (b) | models land in `~/.cache/huggingface` | `cache_dir=None` default (:76 — load-bearing per docstring :64-66 "cache_dir/local_dir/token stay None") → default `~/.cache/huggingface/hub`. VERIFIED live: all 4 repos cached there (§0) | ✅ |
| (c) | called by `install.sh` | `install.sh:102` `"$PY" -m voice_typing.prefetch` (`==> [3/7] prefetch models` :101; warn-only `if !` :103) | ✅ |
| (d) | handles already-cached models gracefully (idempotent) | `force_download=False` default (:76 — snapshot_download skips blobs whose cached etag matches); `_local_snapshot()` uses `local_files_only=True` (:162) for the summary re-resolve (NO download — cache-hit only). VERIFIED: re-run resolves all 4 offline (§6) | ✅ |
| (e) | if distil-large-v3 fails, note the approved substitute `large-v3-turbo` (PRD §3) | `OPTIONAL_REPOS` (:44-48) caches `mobiuslabsgmbh/faster-whisper-large-v3-turbo` as WARN-ONLY (NOT fatal — :129-135, `opt_fail`, exit 0). VERIFIED it is the SAME repo faster-whisper's `_MODELS["large-v3-turbo"]` resolves to (§3) | ✅ |

> PRD §4.4 (the authority): *"install.sh MUST prefetch (construct recorder once, or
> `huggingface_hub.snapshot_download` of `Systran/faster-distil-whisper-large-v3` and
> `Systran/faster-whisper-small.en`) so the first arm never does a network download."* PRD §3:
> *"If distil-large-v3 downloads or runs poorly, large-v3-turbo is the approved substitute."*

---

## §2. prefetch.py STRUCTURE (the 168-line file)

- **Module docstring** (:1-27): states the purpose (pre-download CTranslate2 models into HF cache),
  the lazy-import discipline (only `huggingface_hub` is imported, inside `prefetch()`, so
  `import voice_typing.prefetch` triggers NO network/CUDA/ctranslate2 — can run BEFORE T2.S2 installs
  ctranslate2), and the trap-avoidance ("Do NOT prefetch distil-whisper/distil-large-v3 (raw
  PyTorch — CTranslate2 cannot load it)").
- **`CORE_REPOS`** (:38-42) — 3 required repos:
  - `distil-large-v3` → `Systran/faster-distil-whisper-large-v3` (FINAL, CUDA default)
  - `small.en` → `Systran/faster-whisper-small.en` (REALTIME/partials; also CPU-fallback FINAL; lite default)
  - `tiny.en` → `Systran/faster-whisper-tiny.en` (CPU-fallback REALTIME, degraded mode)
- **`OPTIONAL_REPOS`** (:44-48) — 1 substitute repo:
  - `large-v3-turbo` → `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (PRD §3 approved substitute;
    DIFFERENT owner — the trap-avoidance)
- **`prefetch(short_to_repo=None)`** (:50-83): the worker. Defaults to `{**CORE_REPOS, **OPTIONAL_REPOS}`
  (all 4). Per-repo: `snapshot_download(repo_id, repo_type="model")` (:76) → records `local_path`
  → `_model_bin_size()` check (:79) → prints path + size. Re-raises the FIRST failing repo's exception
  (the CLI catches per-repo). Defaults are **load-bearing** (cache_dir/local_dir/token=None → default
  cache; force_download=False → idempotent) — docstring :64-66 + the inline comment.
- **`_model_bin_size(snapshot_path)`** (:86-92): `os.path.getsize(os.path.join(path, "model.bin"))`
  → int|None. The "model.bin present" check = broken/partial-repo signal (CTranslate2 models always
  have model.bin).
- **`_human_bytes(n)`** (:95-101): size formatter.
- **`_main()`** (:103-156): the CLI. Sets `HF_HUB_DISABLE_TELEMETRY=1` (:110, local-first). Downloads
  CORE (any fail → `core_fail`, exit 1) then OPTIONAL (any fail → `opt_fail`, warning, NOT fatal).
  Summary sums `model.bin` sizes via a **no-download** `_local_snapshot()` re-resolve (local_files_only).
  Exit 0 iff all CORE succeeded; prints the turbo-failed NOTE if opt failed.
- **`_local_snapshot(repo_id)`** (:159-165): `snapshot_download(repo_id, repo_type="model",
  local_files_only=True)` — cache-hit-only path resolution (raises→None). Used for the summary so it
  never re-downloads.
- **`__main__`** (:167-168): `sys.exit(_main())`.

---

## §3. THE SHORT-NAME → REPO_ID CHAIN — VERIFIED LOAD-BEARING

The docstring's central claim (:30-37): *"The short-name KEYS match what RealtimeSTT passes
(`model="distil-large-v3"`, `realtime_model_type="small.en"`, ...) and what cuda_check.py returns
(final_model/realtime_model) — faster-whisper's `_MODELS` resolves them to these repo_ids."*
VERIFIED against the live venv's `faster_whisper/utils.py:_MODELS` (the authoritative resolver):

| prefetch.py short name (KEY) | prefetch.py repo_id (VALUE) | faster-whisper `_MODELS[key]` | MATCH? |
|---|---|---|---|
| `distil-large-v3` | `Systran/faster-distil-whisper-large-v3` | `Systran/faster-distil-whisper-large-v3` | ✅ |
| `small.en` | `Systran/faster-whisper-small.en` | `Systran/faster-whisper-small.en` | ✅ |
| `tiny.en` | `Systran/faster-whisper-tiny.en` | `Systran/faster-whisper-tiny.en` | ✅ |
| `large-v3-turbo` | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` | ✅ |

→ The daemon (RealtimeSTT → faster-whisper `WhisperModel(model_size_or_path)`) resolves EVERY short
name it can be told (via `cuda_check.resolve_device_and_models()` → final_model/realtime_model, or
`config.toml` asr.final_model/realtime_model/lite_model overrides) to a repo_id that prefetch.py has
ALREADY cached. Contract (a)'s "daemon finds a cached weight for every name" holds. NOTE:
`large-v3-turbo` IS a recognized faster-whisper short name (verified — `_MODELS["large-v3-turbo"]`
+ `_MODELS["turbo"]` both exist), so a user can set `final_model = "large-v3-turbo"` in config.toml
and it resolves to the cached mobiuslabs repo. (config.toml:32-34 defaults: final=distil-large-v3,
realtime=small.en, lite=small.en.)

### Resolution flow (how a cached weight is found at runtime, NO network)
```
config.toml asr.final_model="distil-large-v3"
  → cuda_check.resolve_device_and_models() final_model="distil-large-v3" (CUDA path)
     → daemon.cfg_to_kwargs() model="distil-large-v3"
        → RealtimeSTT AudioToTextRecorder(model="distil-large-v3", ...)
           → faster-whisper WhisperModel("distil-large-v3")
              → _MODELS["distil-large-v3"] = "Systran/faster-distil-whisper-large-v3"
                 → huggingface_hub.snapshot_download(..., local_files_only=HF_HUB_OFFLINE)
                    → ~/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/snapshots/<rev>/
                       (FOUND IN CACHE — no download; HF_HUB_OFFLINE=1 forbids it)
```

---

## §4. NON-DEFECT NUANCES (record so they are not mistaken for gaps or "fixed")

### §4.1 — HEADLINE: prefetch.py downloads 4 repos, NOT the 2 the work-item/PRD §4.4 minimum names
The work-item + PRD §4.4 note literally name 2 repos (`Systran/faster-distil-whisper-large-v3` +
`Systran/faster-whisper-small.en`). prefetch.py downloads **4**: those 2 PLUS:
- **`tiny.en`** — REQUIRED by the CPU-fallback path PRD §4.4 mandates (`realtime_model_type=tiny.en`
  when CUDA fails — cuda_check `CPU_FALLBACK`). Without it prefetched, a CPU-fallback daemon would
  download tiny.en on first arm → violates Acceptance #8.
- **`large-v3-turbo`** — the PRD §3 approved substitute (if distil-large-v3 "downloads or runs
  poorly"). Prefetched as OPTIONAL so the substitute is on disk if needed.
This is a **STRICT SUPERSET** of the PRD minimum — more correct, not less. NOT a defect.

### §4.2 — CORE vs OPTIONAL split + exit-code semantics
- CORE (distil-large-v3/small.en/tiny.en): any failure → `core_fail` → `_main()` exits **1** (the
  daemon "cannot start without them" — :152-154). Correct: these are mandatory.
- OPTIONAL (large-v3-turbo): failure → `opt_fail` → warning + exit **0** (:129-135, :154-156).
  Correct: the substitute is a precaution, not mandatory.
- **install.sh interaction** (cross-file, NOT prefetch.py's logic): `install.sh:102` runs prefetch
  under `if !` (:103) — warn-only, so a CORE prefetch failure does NOT abort install. install.sh's
  warning message says *"the daemon will download missing models on first run"* — but
  `launch_daemon.sh:71` exports `HF_HUB_OFFLINE=1`, so at runtime a missing CORE model would
  **fail-fast `LocalEntryNotFoundError`**, NOT lazy-download. ⇒ the install.sh warning's "lazy
  download" framing is technically inaccurate under HF_HUB_OFFLINE=1. This is an **install.sh message
  nuance** (P1.M4.T3.S1 scope), NOT a prefetch.py defect — prefetch.py's own exit-code semantics are
  correct. Cross-reference only; do NOT re-audit install.sh.

### §4.3 — prefetch.py imports ONLY huggingface_hub (lazy) — runs before ctranslate2 is installed
Docstring :21-26 + the lazy `from huggingface_hub import snapshot_download` inside `prefetch()` (:68).
`import voice_typing.prefetch` triggers NO network call and needs NO CUDA/ctranslate2/faster_whisper.
Deliberate: prefetch is an install-time step that can run (and this audit can complete) before the
CUDA stack is installed. NOT a defect — a deliberate ordering enabler.

### §4.4 — NO prefetch test exists (COVERAGE GAP, not a defect)
`ls tests/test_prefetch*` → none. `grep prefetch tests/*.py` → only ACCEPTANCE.md (precondition
comment) + test_feed_audio.py:280 (a comment). So prefetch.py's download logic is verified by:
(1) reading the source, (2) the live cache check (§0), (3) the offline `local_files_only` resolution
test (§6), (4) the daemon's HF_HUB_OFFLINE=1 + fail-fast at runtime. This audit IS the §4.4
prefetch-compliance check the suite cannot perform (mirror of gap_cuda_check.md §4's "coverage
boundary" + S1's §5.4 "core-flow coverage gap"). Record as a coverage gap; do NOT add a test here
(read-only audit).

### §4.5 — `HF_HUB_DISABLE_TELEMETRY=1` (local-first)
`_main()` sets it via `os.environ.setdefault` (:110). Opts out of huggingface_hub's anonymous
telemetry (no-op if already set). Good practice. Non-blocking.

### §4.6 — `model.bin` presence check (`_model_bin_size`)
prefetch.py reports the model.bin size per repo (:79-82) and warns if absent ("WARNING: model.bin
NOT FOUND in snapshot"). CTranslate2 models always ship model.bin; its absence signals a
broken/partial repo. Safety net. Non-blocking.

---

## §5. RUNTIME GUARANTEE — why "no network at runtime" holds (the cross-file chain)

Acceptance #8 ("No network access needed at runtime") is a JOINT property of prefetch.py + the
daemon runtime. prefetch.py owns the INSTALL-TIME half (cache the models); `launch_daemon.sh` owns
the RUNTIME half (forbid the network). Both verified:

| half | owner | mechanism | evidence |
|---|---|---|---|
| install-time cache | **prefetch.py** (THIS audit) | `snapshot_download` of all 4 repos to `~/.cache/huggingface/hub` | §0 (all 4 cached, 3.69 GB) |
| runtime offline | `launch_daemon.sh` (P1.M4.T2.S1) | `export HF_HUB_OFFLINE=1` (:71) + `TRANSFORMERS_OFFLINE=1` (:72), read by huggingface_hub at IMPORT TIME (`constants.py:202`) → all HTTP → `OfflineModeIsEnabledError`; uncached model → `LocalEntryNotFoundError` fail-fast (NO lazy download) | launch_daemon.sh:61-72 (cross-file, P1.M4.T2.S1) |

⇒ Together: the daemon finds every model in cache (prefetch.py) and is forbidden from the network
(launch_daemon.sh HF_HUB_OFFLINE=1). A missing cache entry fails FAST (no silent runtime download) —
exactly the §4.4 / Acceptance #8 contract.

---

## §6. VALIDATION COMMANDS (safe, no download — two timeouts per AGENTS.md Rule 1)

```bash
cd /home/dustin/projects/voice-typing
# (1) the contract points (line-numbered) — re-grep, record actual lines:
grep -nE 'snapshot_download|CORE_REPOS|OPTIONAL_REPOS|local_files_only|force_download|model\.bin|_main|HF_HUB' voice_typing/prefetch.py
grep -nE '\-m voice_typing\.prefetch|==> \[3/7\]' install.sh
# (2) LIVE cache state (os.path.getsize follows symlink -> real blob size):
timeout 30 .venv/bin/python - <<'PY'
import os, glob
for short, repo in [("distil-large-v3","Systran/faster-distil-whisper-large-v3"),
                    ("small.en","Systran/faster-whisper-small.en"),
                    ("tiny.en","Systran/faster-whisper-tiny.en"),
                    ("large-v3-turbo","mobiuslabsgmbh/faster-whisper-large-v3-turbo")]:
    base=os.path.expanduser(f"~/.cache/huggingface/hub/models--{repo.replace('/','--')}")
    sn=sorted(glob.glob(f"{base}/snapshots/*"))
    mb=os.path.join(sn[0],"model.bin") if sn else ""
    print(f"{short:16s}: {('%.2f GB'%(os.path.getsize(mb)/1e9)) if mb and os.path.exists(mb) else 'MISSING'}")
PY
# (3) the short-name -> repo_id chain (load-bearing alignment with faster-whisper _MODELS):
timeout 30 .venv/bin/python -c "from faster_whisper.utils import _MODELS as m; [print(f'{k:16s} -> {m[k]}') for k in ('distil-large-v3','small.en','tiny.en','large-v3-turbo')]"
# (4) HF_HUB_OFFLINE is read at IMPORT TIME (constants.py) — the runtime-forbid mechanism:
grep -nE 'HF_HUB_OFFLINE|def is_offline_mode' .venv/lib/python3.*/site-packages/huggingface_hub/constants.py
# (5) the NO-NETWORK offline resolution (proves Acceptance #8 — cache resolves w/o download):
timeout 60 env HF_HUB_OFFLINE=1 .venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
for r in ["Systran/faster-distil-whisper-large-v3","Systran/faster-whisper-small.en",
          "Systran/faster-whisper-tiny.en","mobiuslabsgmbh/faster-whisper-large-v3-turbo"]:
    p=snapshot_download(repo_id=r, repo_type="model", local_files_only=True)
    print(f"OK  {r} -> {p}")
PY
# (6) CONFIRM no prefetch test (coverage gap §4.4):
ls tests/test_prefetch* 2>/dev/null || echo "NO tests/test_prefetch* (coverage gap §4.4 confirmed)"
```

**DO NOT** run `python -m voice_typing.prefetch` blindly (it does per-file etag HEAD checks over
the network unless HF_HUB_OFFLINE=1; harmless if cached but unnecessary for this audit). If you want
the CLI summary, wrap it: `timeout 120 env HF_HUB_OFFLINE=1 .venv/bin/python -m voice_typing.prefetch`
(offline → cache-only → fast). The local_files_only test (5) is the authoritative Acceptance-#8
proof and needs NO network.

---

## §7. SCOPE BOUNDARIES

- **IN scope (this audit):** `voice_typing/prefetch.py` (the 168-line prefetch logic — CORE/OPTIONAL
  repos, snapshot_download defaults, idempotency, exit-code semantics, _main CLI, _local_snapshot).
  Cross-FILE evidence cited, NOT re-audited: install.sh (:102 invocation — P1.M4.T3.S1),
  launch_daemon.sh (:71 HF_HUB_OFFLINE — P1.M4.T2.S1), cuda_check.py (CPU_FALLBACK tiny.en —
  P1.M1.T4.S1), faster_whisper _MODELS (the resolver), config.toml (model-name overrides).
- **OUT of scope:** install.sh internals (S1), launch_daemon.sh LD_LIBRARY_PATH/HF env (P1.M4.T2.S1),
  cuda_check probe (P1.M1.T4.S1), the daemon's model-load lifecycle (P1.M2.T2), the systemd unit
  (P1.M4.T1.S1). The deliverable is `architecture/gap_prefetch.md` (NEW file — there is NO existing
  `gap_prefetch.md`; `ls architecture/` confirms). No source modified (read-only audit).
# Gap Report — P1.M4.T3.S2: prefetch.py model download logic vs PRD §4.4

**Date:** 2026-07-19 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/prefetch.py` — the install-time model prefetch (PRD §4.4: *"install.sh
MUST prefetch (construct recorder once, or `huggingface_hub.snapshot_download` of `Systran/faster-distil-
whisper-large-v3` and `Systran/faster-whisper-small.en`) so the first arm never does a network download"*
+ Acceptance #8: *"No network access needed at runtime (models cached by install)"*) — against ALL
work-item contract points: (a) downloads the model repos via `snapshot_download`; (b) models land in
`~/.cache/huggingface`; (c) called by `install.sh`; (d) handles already-cached models gracefully
(idempotent); (e) caches the approved substitute `large-v3-turbo` (PRD §3) if `distil-large-v3` fails —
re-verified live via grep + the live-cache `os.path.getsize` check + faster-whisper's `_MODELS` resolver
read + the `HF_HUB_OFFLINE=1 ... local_files_only=True` offline-resolution test. Subtask **P1.M4.T3.S2**
of verification round `006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/prefetch.py` — the 168-line install-time prefetch. Module docstring (`:1`-`:27`:
  purpose + the lazy huggingface_hub-only import + the raw-PyTorch `distil-whisper/distil-large-v3`
  trap-avoidance). `CORE_REPOS` (`:38`-`:42`: distil-large-v3/small.en/tiny.en).
  `OPTIONAL_REPOS` (`:44`-`:48`: large-v3-turbo, `mobiuslabsgmbh` owner). `prefetch()`
  (`:51`-`:83`: the worker; `snapshot_download(repo_id, repo_type="model")` `:76`; load-bearing
  `cache_dir=None`/`force_download=False` per docstring `:64`-`:66`; `_model_bin_size` check
  `:79`). `_model_bin_size()` (`:86`-`:92`). `_main()` (`:103`-`:156`:
  `HF_HUB_DISABLE_TELEMETRY=1` `:110`; CORE loop `:118` / OPTIONAL loop `:129`; summary via
  `local_files_only` `:137`-`:142`; exit 1 on `core_fail` `:152`, turbo warn `:153`-`:156`,
  `return 0` `:156`). `_local_snapshot()` (`:158`-`:164`: `local_files_only=True` cache-hit probe).
- `install.sh` (read for the prefetch INVOCATION ONLY — `:102` `"$PY" -m voice_typing.prefetch`;
  internals audited by P1.M4.T3.S1).
- `voice_typing/launch_daemon.sh` (read for `HF_HUB_OFFLINE=1` `:71` ONLY — the runtime-forbid
  mechanism; internals audited by P1.M4.T2.S1).
- `voice_typing/cuda_check.py` (read for `CPU_FALLBACK` `:53`-`:58` ONLY — the tiny.en consumer;
  probe audited by P1.M1.T4.S1).
- `.venv/.../faster_whisper/utils.py` — the `_MODELS` short-name → repo_id resolver (the load-bearing
  chain to verify).
- `~/.cache/huggingface/hub/` — the LIVE cache (the 4 cached repos + `model.bin` blob sizes).

**Bottom line:** ✅ `prefetch.py` is **COMPLIANT** with PRD §4.4 + the work-item contract + Acceptance
#8 — all 5 contract points present + correct, the live cache confirms all 4 repos cached (≈3.69 GB
total), the short-name → repo_id chain is load-bearing-aligned with faster-whisper's `_MODELS`, and the
`HF_HUB_OFFLINE=1 ... local_files_only=True` offline resolution proves zero-network resolution (the
runtime guarantee). **No source files were modified** — prefetch.py faithfully implements the spec.
The audit's value-add = the **headline nuance (§5.1)**: prefetch.py downloads a **4-repo STRICT
SUPERSET** of the 2-repo PRD §4.4 minimum (adds `tiny.en` for the CPU-fallback path + `large-v3-turbo`
for the approved substitute) — AND there is **NO `tests/test_prefetch*.py`** (§5.4 coverage gap), so this
audit IS the §4.4 prefetch-compliance check the suite cannot perform.

---

## 1. Method

Each of the 5 work-item contract points (a)-(e) was mapped 1:1 to its `prefetch.py` implementation by
`grep -nE` (the file:line evidence), the module docstring (the load-bearing-defaults explanation) was
read directly, the **live cache** was probed via `os.path.getsize` (follows the snapshot symlink → the
real blob size), the **short-name → repo_id chain** was verified against the live venv's
`faster_whisper.utils._MODELS` (the authoritative resolver), and the **Acceptance-#8 offline guarantee**
was proven by an `HF_HUB_OFFLINE=1 ... local_files_only=True` resolution of all 4 repos (zero network).
Nothing was assumed from the PRP's embedded numbers/sizes — every line number + blob size + resolver
output below was re-verified this round.

### Commands run (re-verification)

```bash
wc -l voice_typing/prefetch.py                                                     # 168 lines
# (a)-(e): prefetch.py — the 5 contract points
grep -nE 'CORE_REPOS|OPTIONAL_REPOS' voice_typing/prefetch.py                      # the 4 repos
grep -nE 'snapshot_download|repo_type="model"' voice_typing/prefetch.py            # (a) the call
grep -nE 'cache_dir|local_dir|force_download|local_files_only' voice_typing/prefetch.py  # (b)/(d) defaults
grep -nE '_local_snapshot|local_files_only=True' voice_typing/prefetch.py          # (d) idempotent summary
grep -nE 'core_fail|opt_fail|return 1|return 0' voice_typing/prefetch.py           # (e) CORE/OPTIONAL exit
# cross-file callers (cite, do NOT re-audit):
grep -nE '\-m voice_typing\.prefetch|==> \[3/7\]' install.sh                       # (c) install.sh invokes
grep -nE 'HF_HUB_OFFLINE|TRANSFORMERS_OFFLINE' voice_typing/launch_daemon.sh       # runtime forbid
grep -nE 'CPU_FALLBACK|"tiny\.en"|"small\.en"' voice_typing/cuda_check.py          # tiny.en consumer
# confirm NO prefetch test (coverage gap §5.4):
ls tests/test_prefetch* 2>/dev/null || echo "NO tests/test_prefetch* (coverage gap §5.4 confirmed)"
# the LIVE evidence (§3) — two timeouts per AGENTS.md Rule 1:
timeout 30 .venv/bin/python - <<'PY'   # (step 2) live cache blob sizes (os.path.getsize follows symlink)
import os, glob
for short, repo in [("distil-large-v3","Systran/faster-distil-whisper-large-v3"),
                    ("small.en","Systran/faster-whisper-small.en"),
                    ("tiny.en","Systran/faster-whisper-tiny.en"),
                    ("large-v3-turbo","mobiuslabsgmbh/faster-whisper-large-v3-turbo")]:
    base=os.path.expanduser(f"~/.cache/huggingface/hub/models--{repo.replace('/','--')}")
    sn=sorted(glob.glob(f"{base}/snapshots/*")); mb=os.path.join(sn[0],"model.bin") if sn else ""
    print(f"{short:16s}: {('%.2f GB'%(os.path.getsize(mb)/1e9)) if mb and os.path.exists(mb) else 'MISSING'}")
PY
timeout 30 .venv/bin/python -c "from faster_whisper.utils import _MODELS as m; [print(f'{k:16s} -> {m[k]}') for k in ('distil-large-v3','small.en','tiny.en','large-v3-turbo')]"  # (step 3) _MODELS chain
grep -nE 'HF_HUB_OFFLINE|def is_offline_mode' .venv/lib/python3.*/site-packages/huggingface_hub/constants.py  # (step 4) import-time read
timeout 60 env HF_HUB_OFFLINE=1 .venv/bin/python - <<'PY'   # (step 5) Acceptance-#8 offline proof
from huggingface_hub import snapshot_download
for r in ["Systran/faster-distil-whisper-large-v3","Systran/faster-whisper-small.en",
          "Systran/faster-whisper-tiny.en","mobiuslabsgmbh/faster-whisper-large-v3-turbo"]:
    p=snapshot_download(repo_id=r, repo_type="model", local_files_only=True); print(f"OK  {r} -> {p}")
PY
```

---

## 2. Per-contract-point Compliance Table (work-item contract / PRD §4.4 vs `prefetch.py`)

| # | contract requirement | expected | actual (prefetch.py:line) | pinning test | verdict |
|---|---|---|---|---|---|
| (a) | downloads the model repos via `snapshot_download` | `huggingface_hub.snapshot_download` over the repos | `snapshot_download(repo_id=repo_id, repo_type="model")` (`:76`, lazy import `:68`) iterated over CORE+OPTIONAL (4 repos) | none — **coverage gap §5.4** | ✅ |
| (b) | models land in `~/.cache/huggingface` | default cache_dir=None → `~/.cache/huggingface/hub` | `cache_dir=None` default (load-bearing per docstring `:64`-`:66` "cache_dir/local_dir/token stay None"); VERIFIED live (§3.1) all 4 repos cached there | none — **coverage gap §5.4** (live cache = the proof) | ✅ |
| (c) | called by `install.sh` | `python -m voice_typing.prefetch` | `install.sh:102` `"$PY" -m voice_typing.prefetch` (`==> [3/7] prefetch models` `:101`, warn-only `if !` `:102`) | none — **coverage gap §5.4** (install.sh internals = P1.M4.T3.S1) | ✅ |
| (d) | handles already-cached models gracefully (idempotent) | skip cached blobs; re-runs free | `force_download=False` default (`:76` — snapshot_download skips blobs whose cached etag matches); `_local_snapshot()` uses `local_files_only=True` (`:162`) for the summary re-resolve (NO download) | none — **coverage gap §5.4** (offline-resolution test = the proof, §3.3) | ✅ |
| (e) | if distil-large-v3 fails, cache the approved substitute `large-v3-turbo` (PRD §3) | the substitute repo cached (warn-only, not fatal) | `OPTIONAL_REPOS` (`:44`-`:48`) caches `mobiuslabsgmbh/faster-whisper-large-v3-turbo` WARN-ONLY (NOT fatal — `:129`-`:135`, `opt_fail`, exit 0 `:156`); VERIFIED it is the SAME repo faster-whisper's `_MODELS["large-v3-turbo"]` resolves to (§3.2) | none — **coverage gap §5.4** | ✅ |

> All 5 contract points **PASS**. The `prefetch.py:line` numbers above are `grep -n`-verified against
> the live tree this round. There is NO `tests/test_prefetch*.py`; the 5 points are confirmed by direct
> read + the live cache (§3.1) + the offline-resolution proof (§3.3) + the daemon's fail-fast at
> runtime (the gap is recorded as a non-blocking coverage observation in §5.4).

---

## 3. Live Evidence — the cache + the short-name → repo_id chain + the offline proof

### 3.1 The live cache (Acceptance #8's install-time half) — `os.path.getsize` (follows symlink)

```
~/.cache/huggingface/hub/
├── models--Systran--faster-distil-whisper-large-v3       model.bin = 1.51 GB   ✅ CORE, FINAL (CUDA default)
├── models--Systran--faster-whisper-small.en               model.bin = 0.48 GB   ✅ CORE, REALTIME/partials + CPU-fallback FINAL + lite default
├── models--Systran--faster-whisper-tiny.en                model.bin = 0.08 GB   ✅ CORE, CPU-fallback REALTIME
└── models--mobiuslabsgmbh--faster-whisper-large-v3-turbo  model.bin = 1.62 GB   ✅ OPTIONAL, approved substitute (PRD §3)
                                                                    TOTAL ≈ 3.69 GB cached
```
→ All 4 repos cached. NOTE: a bare `find -name model.bin -printf '%s'` reports the symlink STUB size
(~76 B = the `../../../blobs/<sha>` path), NOT the blob; `os.path.getsize` (which prefetch.py's
`_model_bin_size` uses) follows the symlink → the real size.

### 3.2 The short-name → repo_id chain (contract (a)'s "daemon finds a cached weight for every name")

`faster_whisper.utils._MODELS` (the authoritative resolver) vs prefetch.py's repo_id VALUE — all 4 MATCH:

| prefetch.py short name (KEY) | prefetch.py repo_id (VALUE) | faster-whisper `_MODELS[KEY]` | MATCH? |
|---|---|---|---|
| `distil-large-v3` | `Systran/faster-distil-whisper-large-v3` | `Systran/faster-distil-whisper-large-v3` | ✅ |
| `small.en` | `Systran/faster-whisper-small.en` | `Systran/faster-whisper-small.en` | ✅ |
| `tiny.en` | `Systran/faster-whisper-tiny.en` | `Systran/faster-whisper-tiny.en` | ✅ |
| `large-v3-turbo` | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` | ✅ |

→ The daemon (RealtimeSTT → faster-whisper `WhisperModel(model_size_or_path)`) resolves EVERY short
name it can be told (via `cuda_check.resolve_device_and_models()` → final_model/realtime_model, or
`config.toml` asr.final_model/realtime_model/lite_model overrides) to a repo_id prefetch.py has ALREADY
cached. (config.toml defaults: final=distil-large-v3, realtime=small.en, lite=small.en.)

### 3.3 The offline-resolution proof (Acceptance #8 — zero network)

```
$ timeout 60 env HF_HUB_OFFLINE=1 .venv/bin/python -c "...snapshot_download(repo_id=r, repo_type='model', local_files_only=True)..."
OK  Systran/faster-distil-whisper-large-v3       -> ~/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/snapshots/c3058b475261292e64a0412df1d2681c06260fab
OK  Systran/faster-whisper-small.en              -> ~/.cache/huggingface/hub/models--Systran--faster-whisper-small.en/snapshots/d1d751a5f8271d482d14ca55d9e2deeebbae577f
OK  Systran/faster-whisper-tiny.en               -> ~/.cache/huggingface/hub/models--Systran--faster-whisper-tiny.en/snapshots/0d3d19a32d3338f10357c0889762bd8d64bbdeba
OK  mobiuslabsgmbh/faster-whisper-large-v3-turbo -> ~/.cache/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/snapshots/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf
```
→ All 4 resolve from cache with `HF_HUB_OFFLINE=1` + `local_files_only=True` (NO network). This is the
Acceptance-#8 proof. The runtime half is `launch_daemon.sh:71` `export HF_HUB_OFFLINE=1` (read by
huggingface_hub at IMPORT TIME, `constants.py:202` `HF_HUB_OFFLINE = _is_true(os.environ.get(...) or
os.environ.get("TRANSFORMERS_OFFLINE"))`) → cache-only → an uncached miss fail-fasts
`LocalEntryNotFoundError` (NO lazy download).

---

## 4. Test-Suite Result (the coverage boundary)

```
$ ls tests/test_prefetch*
NO tests/test_prefetch* (coverage gap §5.4 confirmed)
```

**There is NO `tests/test_prefetch*.py`.** `grep -rn "voice_typing.prefetch\|import prefetch"
tests/` returns nothing — no import, no test. prefetch.py's download logic is therefore verified by:
(1) reading the source (§2), (2) the live cache (§3.1), (3) the `_MODELS` resolver alignment (§3.2), (4)
the offline-resolution proof (§3.3), (5) the daemon's `HF_HUB_OFFLINE=1` + `LocalEntryNotFoundError`
fail-fast at runtime (cross-file, P1.M2.T2/P1.M4.T2). **This audit IS the PRD-§4.4 prefetch-compliance
check the unit suite cannot perform** (the mirror of `gap_cuda_check.md` §4's "coverage boundary" +
`gap_install.md` §5.4's "core-flow coverage gap"). Recorded as a **coverage gap, NOT a code defect**
(the code is correct: read §1-§3). A future `tests/test_prefetch.py` could mock `snapshot_download`
and assert CORE/OPTIONAL split + exit codes, but is not required for §4.4 compliance.

---

## 5. Non-defect Nuances (record so they are not mistaken for gaps or "fixed")

### 5.1 — HEADLINE: prefetch.py downloads 4 repos, NOT the 2 the work-item/PRD §4.4 minimum literally name
The work-item + PRD §4.4 note name only `Systran/faster-distil-whisper-large-v3` +
`Systran/faster-whisper-small.en`. prefetch.py downloads a **STRICT SUPERSET** — those 2 PLUS:
- **`Systran/faster-whisper-tiny.en`** — REQUIRED by the CPU-fallback path PRD §4.4 mandates
  (`realtime_model_type=tiny.en` when CUDA fails — `cuda_check.CPU_FALLBACK` `:53`-`:58`). Without
  it prefetched, a CPU-fallback daemon would download `tiny.en` on first arm → **violates Acceptance #8**.
- **`mobiuslabsgmbh/faster-whisper-large-v3-turbo`** — the PRD §3 approved substitute (if distil-large-v3
  "downloads or runs poorly"). Prefetched as OPTIONAL so the `config.toml` override
  `final_model="large-v3-turbo"` works offline.
This is **more correct, not less**. NOT a defect.

### 5.2 — CORE vs OPTIONAL split + the install.sh message caveat under HF_HUB_OFFLINE=1
- CORE (distil-large-v3/small.en/tiny.en): any failure → `core_fail` → `_main()` exits **1**
  (`:152`, "daemon cannot start without them"). Correct.
- OPTIONAL (large-v3-turbo): failure → `opt_fail` → warning + exit **0** (`:129`-`:135`,
  `:153`-`:156`). Correct.
- **install.sh message caveat (cross-file, NOT prefetch.py's logic):** `install.sh:102` runs prefetch
  warn-only and prints *"the daemon will download missing models on first run"*. But
  `launch_daemon.sh:71` exports `HF_HUB_OFFLINE=1`, so at runtime a missing CORE model would
  **fail-fast `LocalEntryNotFoundError`**, NOT lazy-download. ⇒ the install.sh warning's "lazy download"
  framing is technically inaccurate under `HF_HUB_OFFLINE=1`. This is an **install.sh message nuance**
  (P1.M4.T3.S1 scope), NOT a prefetch.py defect — prefetch.py's own exit-code semantics are correct.
  Cross-reference only; do NOT re-audit install.sh.

### 5.3 — prefetch.py imports ONLY huggingface_hub (lazy) — runs before ctranslate2 is installed
Docstring (`:21`-`:26`) + the lazy `from huggingface_hub import snapshot_download` inside
`prefetch()` (`:68`). `import voice_typing.prefetch` triggers NO network call and needs NO
CUDA/ctranslate2/faster_whisper. Deliberate: prefetch is an install-time step that can run (and this
audit can complete) before the CUDA stack is installed. NOT a defect — a deliberate ordering enabler.

### 5.4 — NO prefetch test exists (COVERAGE GAP, not a defect)
See §4. This audit IS the §4.4 prefetch-compliance check. Do NOT add a test here (read-only audit).

### 5.5 — `HF_HUB_DISABLE_TELEMETRY=1` (local-first)
`_main()` sets it via `os.environ.setdefault` (`:110`). Opts out of huggingface_hub's anonymous
telemetry (no-op if already set). Good practice. Non-blocking.

### 5.6 — `model.bin` presence check (`_model_bin_size`)
prefetch.py reports the `model.bin` size per repo (`:79`-`:82`) and warns if absent
("WARNING: model.bin NOT FOUND in snapshot"). CTranslate2 models always ship `model.bin`; its absence
signals a broken/partial repo. Safety net. Non-blocking.

---

## 6. Mismatches / Drift / Non-Blocking Observations

**None — fully PRD §4.4 + Acceptance-#8-compliant.** All 5 contract points (a)-(e) pass with file:line
evidence (§2); the live cache confirms all 4 repos cached ≈3.69 GB (§3.1); the short-name → repo_id
chain is aligned with faster-whisper's `_MODELS` (§3.2); the offline resolution proves zero-network
(§3.3); the 6 nuances (§5.1-§5.6) are documented so they are not mistaken for defects. **No source
files were modified.** The only cross-file caveat (§5.2: install.sh's "lazy download" message under
HF_HUB_OFFLINE=1) is install.sh's concern (P1.M4.T3.S1), not prefetch.py's.

---

## 7. Scope Discipline & Parallel No-Conflict

**IN scope (this audit):**
- `voice_typing/prefetch.py` (the 168-line prefetch logic — CORE/OPTIONAL repos, snapshot_download
  defaults, idempotency, exit-code semantics, `_main` CLI, `_local_snapshot`, `_model_bin_size`).
- The deliverable: this report (`plan/006_862ee9d6ef41/architecture/gap_prefetch.md`).
**OUT of scope (cite as evidence, do NOT re-audit):**
- `install.sh` internals → **P1.M4.T3.S1** (gap_install.md). Cite the `:102` invocation + the §5.2 caveat.
- `launch_daemon.sh` LD_LIBRARY_PATH/HF env → **P1.M4.T2.S1** (gap_launch_daemon.md). Cite the `:71`
  HF_HUB_OFFLINE=1 export as the runtime-forbid mechanism.
- `cuda_check.py` probe → **P1.M1.T4.S1** (gap_cuda_check.md). Cite `CPU_FALLBACK` as the tiny.en consumer.
- the daemon's model-load lifecycle → **P1.M2.T2** (gap_lifecycle.md).
- Read-only: `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`.
**Parallel — P1.M4.T3.S1 (install.sh audit, in flight):** **DISJOINT files** (prefetch.py vs install.sh).
Both write a `gap_<module>.md` under `architecture/` (`gap_prefetch.md` vs `gap_install.md`). **No merge
conflict.**

---

## 8. Conclusion

`voice_typing/prefetch.py` is **PRD §4.4 + Acceptance-#8-compliant** on all 5 contract points (each with
file:line evidence in §2 + live-cache evidence in §3): it downloads the model repos via
`huggingface_hub.snapshot_download` (`:76`); lands them in the default `~/.cache/huggingface/hub`
(cache_dir=None, load-bearing per docstring `:64`-`:66`); is invoked by `install.sh:102`; is
idempotent (`force_download=False` + `local_files_only=True` summary); and caches the approved
`large-v3-turbo` substitute as OPTIONAL/warn-only. The live cache confirms all 4 repos cached (≈3.69 GB);
the short-name → repo_id chain is aligned with faster-whisper's `_MODELS`; the `HF_HUB_OFFLINE=1
local_files_only=True` offline resolution proves zero-network (Acceptance #8). The **headline nuance**
(§5.1: the 4-repo STRICT SUPERSET over the 2-repo PRD minimum — adds `tiny.en` for CPU fallback +
`large-v3-turbo` for the substitute) and the **coverage gap** (§5.4: NO prefetch test — this audit IS
the compliance check) are documented so they are not mistaken for defects. Together with
`launch_daemon.sh`'s `HF_HUB_OFFLINE=1` (P1.M4.T2.S1), prefetch.py guarantees **no network at runtime**.

**No code changes were required and none were made.** `voice_typing/prefetch.py` is **unchanged** — the
audit confirms it is already fully PRD §4.4 + Acceptance-#8-compliant. This closes **P1.M4.T3.S2**.
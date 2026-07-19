# PRP — P1.M4.T3.S2: Audit prefetch.py model download logic (§4.4)

## Goal

**Feature Goal**: Produce the authoritative **`prefetch.py` download-logic compliance audit** as a NEW
`gap_prefetch.md` report — verifying **ALL** work-item contract points (a)–(e) against the LIVE 168-line
`voice_typing/prefetch.py` + the LIVE `~/.cache/huggingface/hub` cache + faster-whisper's `_MODELS`
resolver: (a) downloads the model repos via `huggingface_hub.snapshot_download`; (b) models land in
`~/.cache/huggingface`; (c) is called by `install.sh`; (d) handles already-cached models gracefully
(idempotent); (e) caches the approved substitute `large-v3-turbo` (PRD §3) if `distil-large-v3` fails —
all tied to **PRD §4.4** ("install.sh MUST prefetch (construct recorder once, or
`huggingface_hub.snapshot_download` of `Systran/faster-distil-whisper-large-v3` and
`Systran/faster-whisper-small.en`) so the first arm never does a network download") and **Acceptance #8**
("No network access needed at runtime (models cached by install)"). This is a **READ-ONLY AUDIT**: the
deliverable is the report file; NO source is modified (prefetch.py is compliant — this PRP's research
verified all 5 contract points + the live cache + the short-name→repo_id chain; the audit re-confirms
live).

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_prefetch.md` — a NEW self-contained `# Gap Report —
  P1.M4.T3.S2: …` file (there is NO existing `gap_prefetch.md`; `ls architecture/` confirms — this
  subtask creates it). Format mirrors `gap_cuda_check.md` (the model-name sibling, P1.M1.T4.S1) /
  `gap_systemd.md` / `gap_install.md` (P1.M4.T3.S1). Verbatim content in the Implementation Blueprint →
  Task 3 (evidence pre-filled from verified `prefetch.py:line` + the live cache sizes + the
  `_MODELS` alignment table + the offline `local_files_only` resolution proof; the auditor re-confirms
  the line numbers + cache state live).

> **VERIFIED VERDICT (this PRP's research): `prefetch.py` is COMPLIANT** with PRD §4.4 + the work-item
> contract + Acceptance #8 — no fix needed. All 5 contract points pass: (a) `snapshot_download(repo_id,
> repo_type="model")` (`prefetch.py:76`) over CORE+OPTIONAL; (b) `cache_dir=None` default (load-bearing
> per docstring `:64`-`66`) → `~/.cache/huggingface/hub` — **LIVE-VERIFIED all 4 repos cached** (distil-
> large-v3 1.51 GB, small.en 0.48 GB, tiny.en 0.08 GB, large-v3-turbo 1.62 GB; ≈3.69 GB); (c)
> `install.sh:102` `"$PY" -m voice_typing.prefetch` (warn-only); (d) `force_download=False` default +
> `local_files_only=True` summary re-resolve (`:76`/`:162`) → idempotent; (e) `OPTIONAL_REPOS` caches
> `mobiuslabsgmbh/faster-whisper-large-v3-turbo` warn-only (`:44`-`48`) — **VERIFIED it is the same repo
> faster-whisper's `_MODELS["large-v3-turbo"]` resolves to**. The runtime offline half is
> `launch_daemon.sh:71` `export HF_HUB_OFFLINE=1` (read by huggingface_hub at IMPORT TIME,
> `constants.py:202`) → cache-only → uncached miss fail-fasts `LocalEntryNotFoundError` (NO lazy download).
>
> **The audit's value-add (HEADLINE NUANCE): prefetch.py downloads 4 repos, NOT the 2 the work-item /
> PRD §4.4 minimum literally name.** The contract + PRD §4.4 name only `Systran/faster-distil-whisper-
> large-v3` + `Systran/faster-whisper-small.en`. prefetch.py downloads a **STRICT SUPERSET** — those 2
> PLUS `Systran/faster-whisper-tiny.en` (REQUIRED by the CPU-fallback path PRD §4.4 mandates:
> `realtime_model_type=tiny.en` via cuda_check `CPU_FALLBACK`) PLUS `mobiuslabsgmbh/faster-whisper-
> large-v3-turbo` (the PRD §3 approved substitute). This is **more correct, not less** — without `tiny.en`
> prefetched, a CPU-fallback daemon would download it on first arm, violating Acceptance #8. AND there
> is **NO `tests/test_prefetch*.py`** (coverage gap — this audit IS the §4.4 prefetch-compliance check
> the suite cannot perform, mirroring `gap_cuda_check.md` §4 + `gap_install.md` §5.4).

**Success Definition**:
- (a) The report verifies **all 5** contract points (a)-(e) against the LIVE `prefetch.py` (re-grep —
      not trusting this PRP's line numbers blindly) and records a ✅ verdict + `prefetch.py:line`
      evidence + (where applicable) the live cache fact / the `_MODELS` alignment / the pinning-test-or-
      coverage-gap note for each.
- (b) The **live cache** is re-checked (Task 2): all 4 repos present in `~/.cache/huggingface/hub` with
      the `model.bin` blob sizes recorded via `os.path.getsize` (follows the snapshot symlink — NOT the
      bare `find -printf %s` symlink-stub size).
- (c) The **short-name → repo_id chain** is re-verified against the live venv's `faster_whisper.utils._MODELS`:
      all 4 prefetch short names resolve to the same repo_id prefetch.py downloads (contract (a)'s
      "daemon finds a cached weight for every name it can be told to load").
- (d) The **Acceptance #8 proof** is recorded: the `HF_HUB_OFFLINE=1 ... local_files_only=True` offline
      resolution of all 4 repos (Task 2 step 5) — demonstrating zero-network resolution (the runtime
      guarantee), + the cross-file chain (prefetch.py installs / `launch_daemon.sh` HF_HUB_OFFLINE=1
      forbids runtime download).
- (e) The report documents the **headline nuance** (§5.1: the 4-repo superset) + the other non-defect
      nuances (§5.2 CORE/OPTIONAL exit-code split + the install.sh "lazy download" message caveat under
      HF_HUB_OFFLINE=1; §5.3 the lazy huggingface_hub-only import; §5.4 the NO-test coverage gap;
      §5.5 `HF_HUB_DISABLE_TELEMETRY=1`; §5.6 the `model.bin` presence check).
- (f) **No source files are modified** — `prefetch.py` / `install.sh` / `launch_daemon.sh` / `daemon.py`
      / `cuda_check.py` / `config.toml` / `PRD.md` are read-only; the only artifact change is CREATING
      `gap_prefetch.md`. `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_prefetch.md`.
- (g) The report's scope is **`prefetch.py` download logic ONLY** — NOT install.sh internals
      (P1.M4.T3.S1 → `gap_install.md`), NOT launch_daemon.sh's HF_HUB_OFFLINE/LD_LIBRARY_PATH
      (P1.M4.T2.S1 → `gap_launch_daemon.md`), NOT cuda_check's probe (P1.M1.T4.S1 → `gap_cuda_check.md`),
      NOT the daemon's model-load lifecycle (P1.M2.T2 → `gap_lifecycle.md`). The cross-file artifacts
      are cited as evidence the prefetch has correct targets/consumers, NOT re-audited.

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance cross-check,
which maps Acceptance #8 to the audit evidence) who needs an authoritative, file:line-evidenced +
live-cache-evidenced record that `prefetch.py` matches PRD §4.4 + the item contract on every point —
incl. that the 2 PRD-named repos (distil-large-v3, small.en) AND the CPU-fallback path (tiny.en) AND
the approved substitute (large-v3-turbo) are all cached at install time, that re-runs are idempotent
(no redundant re-download), and that the daemon's model short names all resolve to pre-cached repos —
so a regression (a wrong repo_id, a `local_dir=` that lands weights where faster-whisper won't read
them, a missing tiny.en that breaks CPU fallback, a non-idempotent re-download, an uncached substitute
path) cannot ship silently and break Acceptance #8 ("no network at runtime").

**Use Case**: A reviewer asks "does prefetch.py (a) download the models via snapshot_download, (b) into
~/.cache/huggingface, (c) get called by install.sh, (d) skip already-cached models, (e) cache the
approved large-v3-turbo substitute — exactly as PRD §4.4 + Acceptance #8 say?" The report answers
yes/no per point with the exact source line + the live cache blob size + the `_MODELS` resolver match
+ the offline-resolution proof.

**Pain Points Addressed**: Without this audit, prefetch.py's download logic is invisible — no test
pins it, so a regression (a swapped repo_id, a `force_download=True`, a `local_dir=` override, a dropped
tiny.en/turbo repo) would pass CI and surface only at runtime as a `LocalEntryNotFoundError` under
`HF_HUB_OFFLINE=1` (a broken first arm). The audit pins contract points to PRD §4.4 + Acceptance #8
with read evidence + live cache proof + records the coverage gap, closing the verification hole the
test suite leaves open.

## Why

- **prefetch.py is the install-time half of Acceptance #8** ("No network access needed at runtime
  (models cached by install)"). The runtime half is `launch_daemon.sh`'s `HF_HUB_OFFLINE=1`
  (P1.M4.T2.S1). Together they guarantee zero network at runtime; prefetch.py owning the cache means a
  missing repo here is a fail-fast at the first arm, not a graceful lazy download. The audit certifies
  all 4 repos are cached + the short-name chain resolves.
- **The 4-repo SUPERSET is load-bearing, not incidental.** The CPU-fallback path (PRD §4.4:
  `realtime_model_type=tiny.en` via cuda_check `CPU_FALLBACK`) REQUIRES `tiny.en` cached — without it a
  CPU-fallback daemon would download on first arm, violating Acceptance #8. The substitute (large-v3-
  turbo, PRD §3) must be cached so the config override `final_model="large-v3-turbo"` works offline.
  prefetch.py caches BOTH beyond the 2-repo PRD minimum — the audit records why this is correct.
- **The short-name → repo_id chain is the contract's central claim.** prefetch.py's docstring asserts
  its short-name KEYS match what RealtimeSTT/cuda_check pass AND what faster-whisper's `_MODELS`
  resolves. A drift here (e.g. prefetching `distil-whisper/distil-large-v3` — raw PyTorch, no model.bin,
  CTranslate2 cannot load it) would cache a useless repo. The audit verifies all 4 KEYS map to the same
  repo_id `_MODELS` resolves them to.
- **No prefetch test exists** (coverage gap). prefetch.py is verified by reading the source + the live
  cache + the offline-resolution test + the daemon's fail-fast at runtime. This audit IS the §4.4
  prefetch-compliance check the suite cannot perform.
- **Read-only + parallel-safe.** The audit reads `prefetch.py` + `install.sh` (invocation only) +
  `launch_daemon.sh` (HF_HUB_OFFLINE cross-reference only) + `cuda_check.py` (CPU_FALLBACK cross-ref) +
  the venv's `faster_whisper/utils.py` + the HF cache + `config.toml`, and CREATES `gap_prefetch.md`.
  No source edits → no conflict with the in-flight P1.M4.T3.S1 (`install.sh` audit — disjoint: it
  writes `gap_install.md`, this writes `gap_prefetch.md`).

## What

A read-only verification of `voice_typing/prefetch.py` (the 168-line install-time prefetch, PRD §4.4)
— re-confirmed live via grep + the live-cache `os.path.getsize` check + the `_MODELS` resolver read +
the `HF_HUB_OFFLINE=1 local_files_only=True` offline-resolution test, then documented as a new
`gap_prefetch.md` (mirroring `gap_cuda_check.md`'s format). The 5 contract points + the headline
4-repo-superset nuance + the other nuances + the Acceptance #8 cross-file chain.

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_prefetch.md` exists, titled
      `# Gap Report — P1.M4.T3.S2: prefetch.py model download logic vs PRD §4.4`.
- [ ] The report records a ✅ verdict + `prefetch.py:line` for each of the 5 contract points (a)-(e).
- [ ] The live cache is re-checked (Task 2 step 2) and the 4 `model.bin` blob sizes recorded (via
      `os.path.getsize`, NOT bare `find -printf %s`).
- [ ] The `_MODELS` short-name → repo_id alignment is re-verified (Task 2 step 3) — all 4 MATCH.
- [ ] The `HF_HUB_OFFLINE=1 ... local_files_only=True` offline resolution of all 4 repos is run
      (Task 2 step 5) + recorded as the Acceptance #8 proof.
- [ ] The headline nuance (§5.1: the 4-repo superset over the 2-repo PRD minimum) is documented.
- [ ] The other nuances (§5.2 CORE/OPTIONAL split + install.sh message caveat; §5.3 lazy import;
      §5.4 the NO-test coverage gap; §5.5 telemetry opt-out; §5.6 model.bin presence check) are documented.
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_prefetch.md` — NO source modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research notes: the
task nature (read-only audit → new report file), the `gap_cuda_check.md` / `gap_install.md` FORMAT
template, the verified verdict (compliant) + the `prefetch.py:line` evidence + the live cache sizes +
the `_MODELS` alignment table + the offline-resolution proof for all 5 contract points, the exact
validation commands, the verbatim report body (Task 3), and the scope boundaries are all pinned. The
audit re-verifies live (re-grep + re-cache-check + re-resolve) rather than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + line-numbered evidence + the nuances + scope boundaries
- docfile: plan/006_862ee9d6ef41/P1M4T3S2/research/prefetch_audit.md
  why: "§0 THE VERIFIED VERDICT: prefetch.py COMPLIANT (5/5 + live cache 3.69 GB + _MODELS aligned).
        §1 the 5-point contract TABLE (each -> prefetch.py:line -> ✅). §2 the 168-line file STRUCTURE
        (CORE_REPOS/OPTIONAL_REPOS/prefetch/_main/_local_snapshot/_model_bin_size). §3 the short-name
        -> repo_id chain (all 4 prefetch KEYS == faster-whisper _MODELS values). §4 the NON-DEFECT
        nuances (§4.1 HEADLINE: 4-repo superset; §4.2 CORE/OPTIONAL exit-code + install.sh message
        caveat under HF_HUB_OFFLINE=1; §4.3 lazy huggingface_hub-only import; §4.4 NO test = coverage
        gap; §4.5 HF_HUB_DISABLE_TELEMETRY; §4.6 model.bin presence check). §5 the RUNTIME chain
        (prefetch installs / launch_daemon.sh HF_HUB_OFFLINE=1 forbids). §6 the VALIDATION commands.
        §7 scope boundaries."
  section: "ALL load-bearing. §1 (verdict+evidence), §3 (the chain), §4.1 (the headline), §4.4 (coverage gap)."

# MUST READ — the external huggingface_hub docs backing each load-bearing default (URLs + gotchas)
- docfile: plan/006_862ee9d6ef41/P1M4T3S2/research/huggingface_hub_snapshot_download.md
  why: "Authoritative docs (web-verified 2026-07-19) for the 6 load-bearing snapshot_download/cache
        behaviors: §1 default cache ~/.cache/huggingface/hub (blobs+snapshots+symlinks) — why
        cache_dir=None is CORRECT; §2 force_download=False idempotency (no re-download, but per-file
        etag HEAD unless offline); §3 local_files_only=True -> LocalEntryNotFoundError; §4 HF_HUB_OFFLINE=1
        read at IMPORT TIME (constants.py) -> cache-only -> miss fail-fasts; §5 cache_dir vs local_dir
        (local_dir = 2x-disk plain copy faster-whisper won't auto-read -> local_dir=None is CORRECT);
        §6 faster-whisper reads the SAME default cache (the short-name -> _MODELS -> snapshot_download
        chain). + the trap-avoidance (raw-PyTorch distil-whisper repo / the deepdml-vs-mobiuslabs turbo)."
  section: "ALL 6 points. Cite the URLs (huggingface.co/docs/huggingface_hub/en/...) in the report."

# MUST READ — the file being audited (prefetch.py — the 5 contract points)
- file: voice_typing/prefetch.py
  why: "AUDIT TARGET (read-only, 168 lines). Module docstring (:1-27 — purpose + lazy-import discipline
        + the distil-whisper raw-PyTorch trap-avoidance). CORE_REPOS (:38-42: distil-large-v3/small.en/
        tiny.en). OPTIONAL_REPOS (:44-48: large-v3-turbo, mobiuslabs owner). prefetch() (:50-83 — the
        worker; snapshot_download(repo_id, repo_type='model') :76; load-bearing cache_dir=None/force_
        download=False docstring :64-66; _model_bin_size check :79). _model_bin_size (:86-92). _main
        (:103-156 — HF_HUB_DISABLE_TELEMETRY=1 :110; CORE loop :118 / OPTIONAL loop :129; summary via
        local_files_only :137-142; exit 1 on core_fail :153, turbo warn :154-156). _local_snapshot
        (:159-165 — local_files_only=True cache-hit probe). __main__ (:167-168)."
  critical: "RE-VERIFY by grep (Task 1) — do NOT trust the line numbers blindly (re-locate them live).
             The audit READS this file; it does NOT edit it (compliant code = no modification). Do NOT
             run `python -m voice_typing.prefetch` blindly (per-file etag HEAD over network unless
             HF_HUB_OFFLINE=1; harmless if cached but unnecessary — the local_files_only offline test
             is the authoritative Acceptance-#8 proof)."

# MUST READ — the cross-file callers/consumers (cite as evidence; do NOT re-audit their internals)
- file: install.sh
  why: "installs.sh:102 `\"$PY\" -m voice_typing.prefetch` (contract point (c); `==> [3/7] prefetch
        models` :101; warn-only `if !` :103). The warning message (:103) says 'the daemon will download
        missing models on first run' — NOTE this is technically inaccurate under HF_HUB_OFFLINE=1 (a
        miss fail-fasts LocalEntryNotFoundError, NOT a lazy download); this is an install.sh message
        nuance (P1.M4.T3.S1 scope), NOT prefetch.py's logic."
  critical: "Confirm ONLY the invocation (:102) + warn-only handling. install.sh INTERNALS are P1.M4.T3.S1.
             Do NOT re-audit install.sh."

- file: voice_typing/launch_daemon.sh
  why: "launch_daemon.sh:71 `export HF_HUB_OFFLINE=1` + :72 `export TRANSFORMERS_OFFLINE=1` — the
        RUNTIME half of Acceptance #8 (read by huggingface_hub at IMPORT TIME, constants.py:202 ->
        cache-only -> uncached miss fail-fasts LocalEntryNotFoundError). Comment block :61-68 explains
        it. This is the cross-file evidence that 'no network at runtime' is enforced; prefetch.py owns
        the install-time cache half."
  critical: "launch_daemon.sh INTERNALS are P1.M4.T2.S1 (gap_launch_daemon.md). Cite the HF_HUB_OFFLINE
             export as the runtime-forbid mechanism; do NOT re-audit launch_daemon.sh's LD_LIBRARY_PATH."

- file: voice_typing/cuda_check.py
  why: "CPU_FALLBACK (cuda_check.py:53-58: device=cpu/compute_type=int8/final_model=small.en/
        realtime_model=tiny.en) — the path that REQUIRES tiny.en prefetched (why prefetch.py's 4-repo
        superset is load-bearing, not incidental). CUDA_DEFAULTS (:48-49: final_model=distil-large-v3/
        realtime_model=small.en)."
  critical: "cuda_check's PROBE is P1.M1.T4.S1 (gap_cuda_check.md). Cite CPU_FALLBACK as the tiny.en
             consumer; do NOT re-audit the probe."

# MUST READ — the gap-report FORMAT template (mirror its structure for the new file)
- file: plan/006_862ee9d6ef41/architecture/gap_cuda_check.md
  why: "The closest sibling format (model-name-adjacent, single-file CREATE, recently created
        P1.M1.T4.S1). Structure: title (# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X) + Date + Scope +
        Audited artifacts (read-only) + Bottom line (✅) + §1 Method (commands run + observed output) +
        §2 per-point compliance TABLE (contract req | expected | actual file:line | ✅) + §3 a focused
        live-evidence section (here: the cache + _MODELS chain) + §4 Test results (or the coverage-gap
        note) + §5 Architectural note / non-defect nuances (incl. the headline) + §6 Mismatches/drift
        (none) + §7 Scope discipline + §8 Conclusion. Mirror it EXACTLY. gap_prefetch.md is a NEW file."
  critical: "Mirror the structure. Cite prefetch.py:line per contract point. gap_install.md (P1.M4.T3.S1)
             + gap_systemd.md are the other format references (same single-file CREATE pattern)."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.4 RealtimeSTT recorder configuration note: 'install.sh MUST prefetch (construct recorder
        once, or huggingface_hub.snapshot_download of Systran/faster-distil-whisper-large-v3 and
        Systran/faster-whisper-small.en) so the first arm never does a network download.' §3 engine
        decision: 'If distil-large-v3 downloads or runs poorly, large-v3-turbo is the approved
        substitute.' §4.4 CPU fallback: 'device=cpu, compute_type=int8 with realtime_model_type=tiny.en,
        model small.en' (the path that requires tiny.en prefetched). §7 Acceptance #8: 'No network
        access needed at runtime (models cached by install).' This is the spec each contract point is
        verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.4 + §3 + §7 #8 as the contract."

# CONTEXT — the sibling audit PRP (the CREATE-new-gap-file precedent + the parallel contract)
- docfile: plan/006_862ee9d6ef41/P1M4T3S1/PRP.md
  why: "The install.sh audit (P1.M4.T3.S1) is the EXACT sibling: same single-file-CREATE pattern, same
        read-only-audit discipline, same gap-report structure, same 'headline coverage-gap nuance'
        framing (its core-flow gap == this task's no-prefetch-test gap). It defines gap_install.md;
        this task defines gap_prefetch.md — DISJOINT files (install.sh vs prefetch.py), no merge
        conflict. It confirms install.sh:102 invokes prefetch + is warn-only (this audit's contract
        point (c) evidence). Treat it as a contract (it is being implemented in parallel)."
  critical: "gap_prefetch.md is INDEPENDENT of gap_install.md (different files, different audit areas).
             CREATE the file fresh. Do NOT duplicate the install.sh findings. install.sh INVOKES
             prefetch.py (:102) — cite the invocation; prefetch.py's download logic is THIS audit."
```

### Current Codebase tree (state at P1.M4.T3.S2 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── prefetch.py               # AUDIT TARGET (read-only — the 5 contract points, 168 lines)
│   ├── cuda_check.py             # CROSS-FILE (CPU_FALLBACK tiny.en consumer; audited by P1.M1.T4.S1)
│   ├── launch_daemon.sh          # CROSS-FILE (HF_HUB_OFFLINE=1 runtime half; audited by P1.M4.T2.S1)
│   └── daemon.py                 # CROSS-FILE (model-load lifecycle; audited by P1.M2.T2)
├── install.sh                    # CROSS-FILE (invokes prefetch.py :102; audited by P1.M4.T3.S1)
├── config.toml                   # CROSS-FILE (final_model/realtime_model/lite_model overrides :32-34)
├── .venv/.../faster_whisper/utils.py  # CROSS-FILE (the _MODELS resolver — the chain to verify)
└── ~/.cache/huggingface/hub/     # LIVE EVIDENCE (the 4 cached repos + model.bin blob sizes)
    ├── models--Systran--faster-distil-whisper-large-v3   (1.51 GB)
    ├── models--Systran--faster-whisper-small.en           (0.48 GB)
    ├── models--Systran--faster-whisper-tiny.en            (0.08 GB)
    └── models--mobiuslabsgmbh--faster-whisper-large-v3-turbo (1.62 GB)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_cuda_check.md         # FORMAT TEMPLATE + SIBLING (P1.M1.T4.S1 — model-name-adjacent)
    ├── gap_install.md            # SIBLING REFERENCE (P1.M4.T3.S1 — being created in parallel)
    ├── gap_launch_daemon.md      # CROSS-REFERENCE (the HF_HUB_OFFLINE runtime half; P1.M4.T2.S1)
    ├── gap_systemd.md            # FORMAT REFERENCE (P1.M4.T1.S1)
    └── gap_prefetch.md           # <-- CREATE (NEW file; no prior prefetch gap report exists)
# NO source/test/doc files modified. The only artifact change is creating gap_prefetch.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_prefetch.md   # CREATE (NEW): the P1.M4.T3.S2 prefetch.py audit
                                                   #   (5-contract-point compliance table + live cache sizes +
                                                   #    _MODELS short-name->repo_id alignment + HF_HUB_OFFLINE
                                                   #    offline-resolution Acceptance-#8 proof + 6 nuances
                                                   #    [THE HEADLINE: 4-repo superset / CORE-OPTIONAL split +
                                                    install.sh message caveat / lazy import / NO-test coverage
                                                    gap / telemetry opt-out / model.bin presence check]
                                                   #   + conclusion tied to PRD §4.4 / Acceptance #8).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```sh
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT; DO NOT EDIT voice_typing/prefetch.py / install.sh /
#   voice_typing/launch_daemon.sh / voice_typing/cuda_check.py / voice_typing/daemon.py / config.toml /
#   PRD.md / any source. prefetch.py is COMPLIANT (this PRP's research verified all 5 contract points +
#   the live cache + the _MODELS chain). The ONLY artifact change is CREATING gap_prefetch.md. If a
#   contract point fails on re-read, document it as a real gap for a SEPARATE remediation task — do NOT
#   fix prefetch.py here (consistent with every round-006 audit). (Research §0/§4.)

# CRITICAL #2 — RE-VERIFY THE LINE NUMBERS + CACHE STATE LIVE. This PRP cites prefetch.py's elements at
#   :38-42/:44-48/:68/:76/:86-92/:103-156/:159-165/:167-168 + install.sh:102 + launch_daemon.sh:71-72 +
#   cuda_check.py:53-58. These were correct at research time but the file may have shifted — re-grep
#   (Task 1) + re-run the cache check (Task 2 step 2) and record the ACTUAL line numbers + blob sizes in
#   the report. Do NOT copy the PRP's numbers blind. (Research §6.)

# CRITICAL #3 — MEASURE model.bin WITH os.path.getsize, NOT bare `find -printf %s`. The snapshot's
#   model.bin is a SYMLINK into ../../blobs/<sha>. `find -name model.bin -printf '%s'` reports the
#   symlink STUB size (~76 B = the relative path string), NOT the blob. Use `os.path.getsize()` (follows
#   symlinks, like prefetch.py's _model_bin_size) or `stat -L`. The Task-2 script uses os.path.getsize.
#   (Research §1 gotcha.)

# CRITICAL #4 — THE 4-REPO SUPERSET IS THE HEADLINE NUANCE (§5.1), NOT a defect. The work-item + PRD
#   §4.4 literally name 2 repos (distil-large-v3 + small.en). prefetch.py downloads 4 (those 2 + tiny.en
#   for the CPU-fallback path + large-v3-turbo for the substitute). This is MORE correct (without tiny.en
#   a CPU-fallback daemon would download on first arm → violates Acceptance #8), NOT less. Do NOT flag it
#   as "prefetch downloads extra/unwanted repos" — record it as the deliberate superset it is.

# CRITICAL #5 — NO prefetch TEST EXISTS (§5.4 coverage gap), NOT a defect. `ls tests/test_prefetch*` →
#   none. prefetch.py is verified by reading the source + the live cache + the offline-resolution test +
#   the daemon's fail-fast at runtime. This audit IS the §4.4 prefetch-compliance check the suite cannot
#   perform. Do NOT add a test here (read-only audit). Record the gap.

# CRITICAL #6 — THE OFFLINE-RESOLUTION TEST (Task 2 step 5) IS THE ACCEPTANCE-#8 PROOF. Run
#   `timeout 60 env HF_HUB_OFFLINE=1 .venv/bin/python -c "...snapshot_download(..., local_files_only=True)..."`
#   for all 4 repos. It MUST resolve all 4 from cache with zero network (the runtime guarantee). If any
#   raises LocalEntryNotFoundError, that repo is NOT cached — record a REAL gap (do NOT fix prefetch.py;
#   the models may just not be downloaded on this machine yet — note it). (Research §6 step 5.)

# CRITICAL #7 — SCOPE IS prefetch.py DOWNLOAD LOGIC ONLY. Do NOT audit install.sh internals (P1.M4.T3.S1
#   — confirm install.sh INVOKES prefetch :102 + cite the warn-only message caveat under HF_HUB_OFFLINE=1,
#   DEFER the deep audit), launch_daemon.sh's LD_LIBRARY_PATH/HF env internals (P1.M4.T2.S1 — cite the
#   HF_HUB_OFFLINE=1 export as the runtime-forbid mechanism), cuda_check's probe (P1.M1.T4.S1 — cite
#   CPU_FALLBACK as the tiny.en consumer), the daemon's model-load lifecycle (P1.M2.T2), or the systemd
#   unit (P1.M4.T1.S1). The cross-file artifacts are the TARGETS/CONSUMERS prefetch.py serves — cite
#   them as evidence, NOT re-audited.

# GOTCHA #8 — DO NOT run `python -m voice_typing.prefetch` blindly. With models cached it does per-file
#   etag HEAD freshness checks over the network (unless HF_HUB_OFFLINE=1 is set) — harmless but
#   unnecessary and a (small) network hit. The local_files_only offline test (Critical #6) is the
#   authoritative Acceptance-#8 proof and needs NO network. If you WANT the CLI summary, wrap it:
#   `timeout 120 env HF_HUB_OFFLINE=1 .venv/bin/python -m voice_typing.prefetch` (offline → cache-only
#   → fast → prints the summary). Optional, not required.

# GOTCHA #9 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always `.venv/bin/python -c ...`
#   / `.venv/bin/python -m ...`. mypy NOT installed (skip). ruff at /home/dustin/.local/bin/ruff is
#   OPTIONAL (not a gate; prefetch.py is small + already clean). (Research §7.)

# GOTCHA #10 — TWO TIMEOUTS PER AGENTS.md RULE 1. Every validation command (grep is instant, but the
#   python cache-check + the offline-resolution test still get): inner `timeout N` + the bash-tool
#   `timeout` param above N. The offline-resolution test is sub-second (local_files_only, no download)
#   but STILL wrap it (`timeout 60`). This research did exactly that.

# GOTCHA #11 — gap_prefetch.md is a NEW file. `ls plan/006_862ee9d6ef41/architecture/` shows gap_config/
#   cuda_check/daemon_loop/feedback/install/launch_daemon/lifecycle/lite/recorder_kwargs/socket/status_sh/
#   systemd/textproc/typing/voicectl but NO gap_prefetch (confirmed). CREATE it fresh; do NOT append to a
#   sibling. (Research §7.)
```

## Implementation Blueprint

### Data models and structure

No production data model. The deliverable is a Markdown gap-report file mirroring `gap_cuda_check.md`'s
structure. No code changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — re-verify the contract + locate the live line numbers (no mutation)
  - RUN (from /home/dustin/projects/voice-typing) — the research §6 commands:
      test -f voice_typing/prefetch.py && echo "ok: prefetch.py present" || echo "PREFLIGHT FAIL"
      wc -l voice_typing/prefetch.py                                  # expect 168 (record actual)
      # the 5 contract points (line-numbered):
      grep -nE 'CORE_REPOS|OPTIONAL_REPOS' voice_typing/prefetch.py   # the 4 repos (a)/(e)
      grep -nE 'snapshot_download|repo_type="model"' voice_typing/prefetch.py  # (a) the download call
      grep -nE 'cache_dir|local_dir|force_download|local_files_only' voice_typing/prefetch.py  # (b)/(d) defaults
      grep -nE '_local_snapshot|local_files_only=True' voice_typing/prefetch.py  # (d) the idempotent summary
      grep -nE 'core_fail|opt_fail|return 1|return 0' voice_typing/prefetch.py  # (e) CORE/OPTIONAL exit semantics
      # cross-file callers (cite, do NOT re-audit):
      grep -nE '\-m voice_typing\.prefetch|==> \[3/7\]' install.sh   # (c) install.sh invokes it
      grep -nE 'HF_HUB_OFFLINE|TRANSFORMERS_OFFLINE' voice_typing/launch_daemon.sh  # runtime forbid
      grep -nE 'CPU_FALLBACK|"tiny\.en"|"small\.en"' voice_typing/cuda_check.py  # tiny.en consumer
      # confirm NO prefetch test (coverage gap §5.4):
      ls tests/test_prefetch* 2>/dev/null || echo "NO tests/test_prefetch* (coverage gap §5.4 confirmed)"
      grep -rn "voice_typing.prefetch\|import prefetch" tests/*.py || echo "(no prefetch import in tests/*.py)"
  - EXPECTED: prefetch.py present (168 lines); the 4 repos at CORE_REPOS (:38-42) + OPTIONAL_REPOS (:44-48);
    snapshot_download at :76; cache_dir/local_dir/force_download defaults load-bearing (docstring :64-66);
    _local_snapshot local_files_only at :162; CORE fatal (return 1 :153) / OPTIONAL warn (return 0);
    install.sh:102 invokes it; launch_daemon.sh:71 HF_HUB_OFFLINE=1; cuda_check CPU_FALLBACK tiny.en;
    NO prefetch test (coverage gap confirmed). RECORD the actual line numbers.
  - DO NOT: edit anything yet, run install.sh, run `python -m voice_typing.prefetch` (blindly), or touch
    any source/test/doc file.

Task 2: RUN the live-evidence checks (record §3/§4) — TWO TIMEOUTS per AGENTS.md Rule 1
  - RUN (each wrapped in `timeout`; set the bash-tool `timeout` param above each inner backstop):
    # (step 2) LIVE cache state — model.bin blob sizes via os.path.getsize (follows symlink -> real size):
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
    # (step 3) the short-name -> repo_id chain (load-bearing alignment with faster-whisper _MODELS):
    timeout 30 .venv/bin/python -c "from faster_whisper.utils import _MODELS as m; [print(f'{k:16s} -> {m[k]}') for k in ('distil-large-v3','small.en','tiny.en','large-v3-turbo')]"
    # (step 4) HF_HUB_OFFLINE is read at IMPORT TIME (constants.py) — the runtime-forbid mechanism:
    grep -nE 'HF_HUB_OFFLINE|def is_offline_mode' .venv/lib/python3.*/site-packages/huggingface_hub/constants.py
    # (step 5) the NO-NETWORK offline resolution (Acceptance-#8 proof — cache resolves w/o download):
    timeout 60 env HF_HUB_OFFLINE=1 .venv/bin/python - <<'PY'
    from huggingface_hub import snapshot_download
    for r in ["Systran/faster-distil-whisper-large-v3","Systran/faster-whisper-small.en",
              "Systran/faster-whisper-tiny.en","mobiuslabsgmbh/faster-whisper-large-v3-turbo"]:
        p=snapshot_download(repo_id=r, repo_type="model", local_files_only=True)
        print(f"OK  {r} -> {p}")
    PY
  - EXPECTED: (step 2) all 4 repos cached with model.bin (distil-large-v3 ~1.51 GB, small.en ~0.48 GB,
    tiny.en ~0.08 GB, large-v3-turbo ~1.62 GB; total ~3.69 GB); (step 3) all 4 short names resolve to the
    SAME repo_id prefetch.py downloads (MATCH); (step 4) constants.py line `HF_HUB_OFFLINE = _is_true(...)`;
    (step 5) all 4 resolve offline (OK, no LocalEntryNotFoundError). RECORD the actual sizes + the resolver
    output. If step 2/5 shows a repo MISSING/uncached: record a REAL gap (the models may not be downloaded
    on this machine — note it; do NOT fix prefetch.py; do NOT run prefetch to download unless explicitly asked).
    (Critical #2/#3/#6; Gotcha #10.)

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_prefetch.md — write the report body from
        "Task 3 SOURCE" below, REPLACING the <...> placeholders with the LIVE line numbers from Task 1
        and the LIVE cache sizes + resolver output from Task 2 (§3/§4). Mirror gap_cuda_check.md's structure.
  - FILE: plan/006_862ee9d6ef41/architecture/gap_prefetch.md (NEW — CREATE, do not append).
  - DO NOT: edit prefetch.py/install.sh/launch_daemon.sh/cuda_check.py/daemon.py/config.toml/PRD.md
    (Critical #1); hard-code the cache sizes (Critical #2); use find -printf %s for sizes (Critical #3);
    flag the 4-repo superset as a defect (Critical #4); add a prefetch test (Critical #5); audit the
    cross-file internals (Critical #7).

Task 4: VALIDATE — L1 (file exists + markdown sanity) + L2 (the cache sizes + _MODELS match are in §3,
        the offline-resolution proof is in §3/§4) + L3 (scope guard: ONLY gap_prefetch.md created; no source
        modified) + L4 (evidence spot-check). No git commit unless the orchestrator directs it. If asked:
        message "P1.M4.T3.S2: prefetch.py audit (compliant; gap_prefetch.md created; no code changes)".
```

#### Task 3 SOURCE — `gap_prefetch.md` (write this body; replace `<...>` with LIVE values from Task 1/2)

````markdown
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
- `voice_typing/prefetch.py` — the 168-line install-time prefetch. Module docstring (`:<L1>`-`<L27>`:
  purpose + the lazy huggingface_hub-only import + the raw-PyTorch `distil-whisper/distil-large-v3`
  trap-avoidance). `CORE_REPOS` (`:<L38>`-`<L42>`: distil-large-v3/small.en/tiny.en).
  `OPTIONAL_REPOS` (`:<L44>`-`<L48>`: large-v3-turbo, `mobiuslabsgmbh` owner). `prefetch()`
  (`:<L50>`-`<L83>`: the worker; `snapshot_download(repo_id, repo_type="model")` `:<L76>`; load-bearing
  `cache_dir=None`/`force_download=False` per docstring `:<L64>`-`<L66>`; `_model_bin_size` check
  `:<L79>`). `_model_bin_size()` (`:<L86>`-`<L92>`). `_main()` (`:<L103>`-`<L156>`:
  `HF_HUB_DISABLE_TELEMETRY=1` `:<L110>`; CORE loop `:<L118>` / OPTIONAL loop `:<L129>`; summary via
  `local_files_only` `:<L137>`-`<L142>`; exit 1 on `core_fail` `:<L153>`, turbo warn `:<L154>`-`<L156>`).
  `_local_snapshot()` (`:<L159>`-`<L165>`: `local_files_only=True` cache-hit probe).
- `install.sh` (read for the prefetch INVOCATION ONLY — `:<L102>` `"$PY" -m voice_typing.prefetch`;
  internals audited by P1.M4.T3.S1).
- `voice_typing/launch_daemon.sh` (read for `HF_HUB_OFFLINE=1` `:<L71>` ONLY — the runtime-forbid
  mechanism; internals audited by P1.M4.T2.S1).
- `voice_typing/cuda_check.py` (read for `CPU_FALLBACK` `:<L53>`-`<L58>` ONLY — the tiny.en consumer;
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
| (a) | downloads the model repos via `snapshot_download` | `huggingface_hub.snapshot_download` over the repos | `snapshot_download(repo_id=repo_id, repo_type="model")` (`:<L76>`, lazy import `:<L68>`) iterated over CORE+OPTIONAL (4 repos) | none — **coverage gap §5.4** | ✅ |
| (b) | models land in `~/.cache/huggingface` | default cache_dir=None → `~/.cache/huggingface/hub` | `cache_dir=None` default (load-bearing per docstring `:<L64>`-`<L66>` "cache_dir/local_dir/token stay None"); VERIFIED live (§3) all 4 repos cached there | none — **coverage gap §5.4** (live cache = the proof) | ✅ |
| (c) | called by `install.sh` | `python -m voice_typing.prefetch` | `install.sh:<L102>` `"$PY" -m voice_typing.prefetch` (`==> [3/7] prefetch models` `:<L101>`, warn-only `if !` `:<L103>`) | none — **coverage gap §5.4** (install.sh internals = P1.M4.T3.S1) | ✅ |
| (d) | handles already-cached models gracefully (idempotent) | skip cached blobs; re-runs free | `force_download=False` default (`:<L76>` — snapshot_download skips blobs whose cached etag matches); `_local_snapshot()` uses `local_files_only=True` (`:<L162>`) for the summary re-resolve (NO download) | none — **coverage gap §5.4** (offline-resolution test = the proof, §3 step 5) | ✅ |
| (e) | if distil-large-v3 fails, cache the approved substitute `large-v3-turbo` (PRD §3) | the substitute repo cached (warn-only, not fatal) | `OPTIONAL_REPOS` (`:<L44>`-`<L48>`) caches `mobiuslabsgmbh/faster-whisper-large-v3-turbo` WARN-ONLY (NOT fatal — `:<L129>`-`<L135>`, `opt_fail`, exit 0); VERIFIED it is the SAME repo faster-whisper's `_MODELS["large-v3-turbo"]` resolves to (§3) | none — **coverage gap §5.4** | ✅ |

> All 5 contract points **PASS**. The `prefetch.py:line` numbers above are `grep -n`-verified against
> the live tree this round. There is NO `tests/test_prefetch*.py`; the 5 points are confirmed by direct
> read + the live cache (§3) + the offline-resolution proof (§3 step 5) + the daemon's fail-fast at
> runtime (the gap is recorded as a non-blocking coverage observation in §5.4).

---

## 3. Live Evidence — the cache + the short-name → repo_id chain + the offline proof

### 3.1 The live cache (Acceptance #8's install-time half) — `os.path.getsize` (follows symlink)

```
~/.cache/huggingface/hub/
├── models--Systran--faster-distil-whisper-large-v3       model.bin = <1.51> GB   ✅ CORE, FINAL (CUDA default)
├── models--Systran--faster-whisper-small.en               model.bin = <0.48> GB   ✅ CORE, REALTIME/partials + CPU-fallback FINAL + lite default
├── models--Systran--faster-whisper-tiny.en                model.bin = <0.08> GB   ✅ CORE, CPU-fallback REALTIME
└── models--mobiuslabsgmbh--faster-whisper-large-v3-turbo  model.bin = <1.62> GB   ✅ OPTIONAL, approved substitute (PRD §3)
                                                                    TOTAL ≈ <3.69> GB cached
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
OK  Systran/faster-distil-whisper-large-v3 -> ~/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/snapshots/<rev>
OK  Systran/faster-whisper-small.en         -> ...
OK  Systran/faster-whisper-tiny.en          -> ...
OK  mobiuslabsgmbh/faster-whisper-large-v3-turbo -> ...
```
→ All 4 resolve from cache with `HF_HUB_OFFLINE=1` + `local_files_only=True` (NO network). This is the
Acceptance-#8 proof. The runtime half is `launch_daemon.sh:<L71>` `export HF_HUB_OFFLINE=1` (read by
huggingface_hub at IMPORT TIME, `constants.py` line `HF_HUB_OFFLINE = _is_true(os.environ.get(...) or
os.environ.get("TRANSFORMERS_OFFLINE"))`) → cache-only → an uncached miss fail-fasts
`LocalEntryNotFoundError` (NO lazy download).

---

## 4. Test-Suite Result (the coverage boundary)

```
$ ls tests/test_prefetch*
NO tests/test_prefetch* (coverage gap §5.4 confirmed)
```

**There is NO `tests/test_prefetch*.py`.** `grep -rn "voice_typing.prefetch\|import prefetch"
tests/*.py` returns only `tests/ACCEPTANCE.md` (a precondition comment) + `tests/test_feed_audio.py`
(a comment) — no import, no test. prefetch.py's download logic is therefore verified by: (1) reading
the source (§2), (2) the live cache (§3.1), (3) the `_MODELS` resolver alignment (§3.2), (4) the
offline-resolution proof (§3.3), (5) the daemon's `HF_HUB_OFFLINE=1` + `LocalEntryNotFoundError`
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
  (`realtime_model_type=tiny.en` when CUDA fails — `cuda_check.CPU_FALLBACK` `:<L53>`-`<L58>`). Without
  it prefetched, a CPU-fallback daemon would download `tiny.en` on first arm → **violates Acceptance #8**.
- **`mobiuslabsgmbh/faster-whisper-large-v3-turbo`** — the PRD §3 approved substitute (if distil-large-v3
  "downloads or runs poorly"). Prefetched as OPTIONAL so the `config.toml` override
  `final_model="large-v3-turbo"` works offline.
This is **more correct, not less**. NOT a defect.

### 5.2 — CORE vs OPTIONAL split + the install.sh message caveat under HF_HUB_OFFLINE=1
- CORE (distil-large-v3/small.en/tiny.en): any failure → `core_fail` → `_main()` exits **1**
  (`:<L153>`-`<L154>`, "daemon cannot start without them"). Correct.
- OPTIONAL (large-v3-turbo): failure → `opt_fail` → warning + exit **0** (`:<L129>`-`<L135>`,
  `:<L154>`-`<L156>`). Correct.
- **install.sh message caveat (cross-file, NOT prefetch.py's logic):** `install.sh:<L103>` runs prefetch
  warn-only and prints *"the daemon will download missing models on first run"*. But
  `launch_daemon.sh:<L71>` exports `HF_HUB_OFFLINE=1`, so at runtime a missing CORE model would
  **fail-fast `LocalEntryNotFoundError`**, NOT lazy-download. ⇒ the install.sh warning's "lazy download"
  framing is technically inaccurate under `HF_HUB_OFFLINE=1`. This is an **install.sh message nuance**
  (P1.M4.T3.S1 scope), NOT a prefetch.py defect — prefetch.py's own exit-code semantics are correct.
  Cross-reference only; do NOT re-audit install.sh.

### 5.3 — prefetch.py imports ONLY huggingface_hub (lazy) — runs before ctranslate2 is installed
Docstring (`:<L21>`-`<L26>`) + the lazy `from huggingface_hub import snapshot_download` inside
`prefetch()` (`:<L68>`). `import voice_typing.prefetch` triggers NO network call and needs NO
CUDA/ctranslate2/faster_whisper. Deliberate: prefetch is an install-time step that can run (and this
audit can complete) before the CUDA stack is installed. NOT a defect — a deliberate ordering enabler.

### 5.4 — NO prefetch test exists (COVERAGE GAP, not a defect)
See §4. This audit IS the §4.4 prefetch-compliance check. Do NOT add a test here (read-only audit).

### 5.5 — `HF_HUB_DISABLE_TELEMETRY=1` (local-first)
`_main()` sets it via `os.environ.setdefault` (`:<L110>`). Opts out of huggingface_hub's anonymous
telemetry (no-op if already set). Good practice. Non-blocking.

### 5.6 — `model.bin` presence check (`_model_bin_size`)
prefetch.py reports the `model.bin` size per repo (`:<L79>`-`<L82>`) and warns if absent
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
`huggingface_hub.snapshot_download` (`:<L76>`); lands them in the default `~/.cache/huggingface/hub`
(cache_dir=None, load-bearing per docstring `:<L64>`-`<L66>`); is invoked by `install.sh:<L102>`; is
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
````

### Implementation Patterns & Key Details

```python
# This is a READ-ONLY AUDIT — no production code is written. The "pattern" is the gap-report format
# (mirror gap_cuda_check.md). The only "code" run is the validation probes (Task 2), all of which are
# safe read-only checks (no download, no mutation):
#
#   - os.path.getsize(model.bin)  # follows the snapshot symlink -> real blob size (NOT find -printf %s)
#   - faster_whisper.utils._MODELS[k]  # the authoritative short-name -> repo_id resolver (read-only dict)
#   - snapshot_download(repo_id, repo_type="model", local_files_only=True)  # cache-hit-only (NO network
#     when HF_HUB_OFFLINE=1; raises LocalEntryNotFoundError if absent — the fail-fast the daemon relies on)
#
# The CRITICAL invariant being verified (not coded): prefetch.py's short-name KEYS (CORE_REPOS +
# OPTIONAL_REPOS keys) MUST equal the keys faster-whisper's _MODELS resolves for the names the daemon
# passes (model="distil-large-v3", realtime_model_type="small.en"/"tiny.en", or the config override
# "large-v3-turbo"). A drift here = a useless cached repo. §3.2 verifies all 4 MATCH.
```

### Integration Points

```yaml
N/A — read-only audit. No config/routes/database changes. The ONLY integration is the report file's
role as the Acceptance-#8 evidence for the downstream P1.M5.T5 acceptance cross-check (which maps PRD
§7 acceptance criteria #8 to the audit findings: prefetch.py = the install-time cache half;
launch_daemon.sh HF_HUB_OFFLINE=1 = the runtime-forbid half; together = "no network at runtime").
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The deliverable is a Markdown report — validate structure/sanity (no ruff/mypy apply to .md):
test -f plan/006_862ee9d6ef41/architecture/gap_prefetch.md && echo "ok: report created"
head -1 plan/006_862ee9d6ef41/architecture/gap_prefetch.md   # expect: "# Gap Report — P1.M4.T3.S2: prefetch.py ..."
grep -c '^| (' plan/006_862ee9d6ef41/architecture/gap_prefetch.md  # expect: 5 (the contract-point table rows)
# prefetch.py is unchanged — ruff/mypy are OPTIONAL (not a gate; small + already clean):
#   /home/dustin/.local/bin/ruff check voice_typing/prefetch.py   # optional, expect 0 errors
# Expected: file exists, title correct, 5 contract-point rows present.
```

### Level 2: Live-Evidence Validation (the §3 proof — re-runnable)

```bash
# (these ARE the Task-2 checks; re-run to confirm §3 numbers are live, not hard-coded)
timeout 30 .venv/bin/python - <<'PY'   # §3.1 cache — expect 4 repos, model.bin present
import os, glob
for short, repo in [("distil-large-v3","Systran/faster-distil-whisper-large-v3"),
                    ("small.en","Systran/faster-whisper-small.en"),
                    ("tiny.en","Systran/faster-whisper-tiny.en"),
                    ("large-v3-turbo","mobiuslabsgmbh/faster-whisper-large-v3-turbo")]:
    base=os.path.expanduser(f"~/.cache/huggingface/hub/models--{repo.replace('/','--')}")
    sn=sorted(glob.glob(f"{base}/snapshots/*")); mb=os.path.join(sn[0],"model.bin") if sn else ""
    print(f"{short:16s}: {('%.2f GB'%(os.path.getsize(mb)/1e9)) if mb and os.path.exists(mb) else 'MISSING'}")
PY
timeout 30 .venv/bin/python -c "from faster_whisper.utils import _MODELS as m; assert all(m[k]==v for k,v in [('distil-large-v3','Systran/faster-distil-whisper-large-v3'),('small.en','Systran/faster-whisper-small.en'),('tiny.en','Systran/faster-whisper-tiny.en'),('large-v3-turbo','mobiuslabsgmbh/faster-whisper-large-v3-turbo')]); print('ok: all 4 _MODELS aligned')"
timeout 60 env HF_HUB_OFFLINE=1 .venv/bin/python - <<'PY'   # §3.3 offline proof — expect 4x OK
from huggingface_hub import snapshot_download
for r in ["Systran/faster-distil-whisper-large-v3","Systran/faster-whisper-small.en","Systran/faster-whisper-tiny.en","mobiuslabsgmbh/faster-whisper-large-v3-turbo"]:
    snapshot_download(repo_id=r, repo_type="model", local_files_only=True); print(f"OK {r}")
PY
# Expected: 4 repos cached (sizes match §3.1); _MODELS assert passes; 4x offline OK. (Two timeouts per AGENTS.md Rule 1.)
```

### Level 3: Scope-Guard Validation (no source modified)

```bash
git status --short   # Expected: ONLY plan/006_862ee9d6ef41/architecture/gap_prefetch.md (NEW/untracked).
# Confirm NO source/test/doc touched:
git diff --name-only voice_typing/ install.sh voice_typing/launch_daemon.sh voice_typing/cuda_check.py config.toml PRD.md tests/ 2>/dev/null
# Expected: empty (no changes). prefetch.py + cross-files are READ-ONLY.
```

### Level 4: Domain-Specific Validation (Acceptance-#8 mapping)

```bash
# Map Acceptance #8 ("No network access needed at runtime (models cached by install)") to the evidence:
grep -nE "Acceptance.?8|no network|models cached" plan/006_862ee9d6ef41/architecture/gap_prefetch.md
# Expected: the report ties prefetch.py (install-time cache half) + launch_daemon.sh HF_HUB_OFFLINE=1
# (runtime-forbid half) to Acceptance #8 (§3.3 + §8). The offline-resolution test (Level 2) IS the proof.
```

## Final Validation Checklist

### Technical Validation

- [ ] All validation levels completed (L1 report sanity; L2 live-evidence re-run; L3 scope guard; L4 Acceptance-#8 mapping).
- [ ] `test -f plan/006_862ee9d6ef41/architecture/gap_prefetch.md` → exists; title correct.
- [ ] The 5 contract-point table rows are present (§2); the live cache sizes (§3.1) + `_MODELS` alignment (§3.2) + offline proof (§3.3) are recorded with LIVE values (not hard-coded).
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_prefetch.md` — NO source/test/doc modified.

### Feature Validation

- [ ] All 5 contract points (a)-(e) ✅ with `prefetch.py:line` evidence.
- [ ] The headline nuance (§5.1: 4-repo superset) documented as correct-by-design, NOT a defect.
- [ ] The coverage gap (§5.4: NO prefetch test) documented as a coverage observation, NOT a code defect.
- [ ] The Acceptance-#8 cross-file chain (prefetch.py installs / launch_daemon.sh HF_HUB_OFFLINE=1 forbids) documented (§3.3/§8).
- [ ] Scope boundaries respected (install.sh/launch_daemon.sh/cuda_check/daemon internals NOT re-audited — cited only).

### Code Quality Validation

- [ ] Report mirrors `gap_cuda_check.md` / `gap_install.md` structure (single-file CREATE, §1 Method → §2 Table → §3 Evidence → §4 Tests/gap → §5 Nuances → §6 Mismatches → §7 Scope → §8 Conclusion).
- [ ] File placement matches the desired codebase tree (`plan/006_862ee9d6ef41/architecture/gap_prefetch.md`).
- [ ] No anti-patterns (did not "fix" compliant code; did not add a test to a read-only audit; did not run prefetch.py blindly; did not use `find -printf %s` for blob sizes).

### Documentation & Deployment

- [ ] Report is self-documenting (re-runnable commands in §1; live values in §3).
- [ ] External doc URLs (huggingface.co/docs/huggingface_hub/en/...) cited where load-bearing (§3.3 offline mechanism).
- [ ] No new env vars / config introduced (read-only audit).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `prefetch.py` / `install.sh` / `launch_daemon.sh` / `cuda_check.py` / `daemon.py` / `config.toml` / `PRD.md` — this is a READ-ONLY audit (compliant code = no modification).
- ❌ Don't hard-code the cache sizes / line numbers — re-verify them LIVE (Task 1/2) and record the actual values.
- ❌ Don't measure `model.bin` with `find -name model.bin -printf '%s'` (reports the symlink stub ~76 B, not the blob) — use `os.path.getsize` (follows symlink).
- ❌ Don't flag the 4-repo superset (§5.1) as "extra/unwanted repos" — it is the deliberate, MORE-correct superset (tiny.en is required by the CPU-fallback path).
- ❌ Don't flag the missing prefetch test (§5.4) as a code defect — it is a coverage gap; this audit IS the compliance check.
- ❌ Don't run `python -m voice_typing.prefetch` blindly (per-file etag HEAD over network unless HF_HUB_OFFLINE=1) — the `local_files_only` offline test is the authoritative Acceptance-#8 proof and needs NO network.
- ❌ Don't re-audit install.sh / launch_daemon.sh / cuda_check / daemon internals — cite them as the targets/consumers prefetch.py serves (each has its own owner audit).
- ❌ Don't add a test in this read-only audit — record the coverage gap (§5.4) instead.

---

## Success Metrics

**Confidence Score: 9/10** for one-pass implementation success. The research pre-mapped every contract
point to its `prefetch.py:line` + live-cache fact + `_MODELS` alignment + the offline-resolution proof;
the verbatim report body (Task 3 SOURCE) is pre-filled with the evidence (placeholders for the 4-5 LIVE
values the auditor re-verifies). The only residual risk: a repo not being cached on the audit machine
(step 2/5 MISSING) — handled by "record a REAL gap, do NOT fix prefetch.py, do NOT download unless asked."
The -1 is for the unavoidable re-verification of line numbers/sizes (the auditor must re-grep + re-run,
not copy the PRP blind).
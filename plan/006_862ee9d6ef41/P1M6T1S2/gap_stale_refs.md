# Stale-reference audit — P1.M6.T1.S2 (BUGS.md / VT-* doc drift)

**Date:** 2026-07-18
**Verdict:** **PASS.** BUGS.md is absent from the repo (the only reference is a dangling `PRD.md:144`
clause, read-only). All `VT-001`..`VT-008` references in the shipped tree (`voice_typing/`, `tests/`,
`README.md`, `config.toml`, `install.sh`, `systemd/`, `hypr-binds.conf`) are **explanatory comments
documenting RESOLVED, test-pinned fixes** — there are **zero unresolved VT-* bugs**. The changeset docs
(README + the `# VT-0NN` comments) are **clean / correct, not stale**. Three stale references live in the
**read-only PRD** and are routed for a human PRD edit (out of this task's scope). No remediation task was
created. Scope: stale-reference hygiene ONLY; README-completeness → P1.M6.T1.S1; commit readiness →
P1.M6.T1.S3.

## 1. Audit command + scope

```bash
find . -name BUGS.md                                 # → none
grep -rn 'BUGS\.md'   voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf   # → 0 hits
grep -rn 'VT-00[0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf   # → the VT-* list below
grep -rn 'VT-0[0-9][0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf # → same set (no VT-010+)
```
Scope = the shipped tree only (NOT `plan/` research/gap docs, NOT `.pi-subagents/`, NOT `.venv/` —
those legitimately cite VT-* and are out of scope). All line numbers below were re-grepped LIVE against
the tree at `/home/dustin/projects/voice-typing` on 2026-07-18.

## 2. BUGS.md — absent (dangling PRD reference only)

- `find . -name BUGS.md` → **none**. No shipped file references BUGS.md (grep over the contract input
  set → 0 hits, exit 1).
- The ONLY BUGS.md reference is **`PRD.md:144`** (§4.2bis): *"caveat: `voicectl status` currently
  violates this; see BUGS.md VT-001."* — a dangling reference in the **read-only** PRD.
  (`.pi-subagents/artifacts/*` also mentions it; that is agent scratch, not a shipped artifact.)
- **Classification:** doc drift, READ-ONLY. BUGS.md is NOT created (it would paper over the drift); the
  proper fix is a human PRD edit (routed §6).

## 3. VT-001..VT-008 classification — ALL RESOLVED + test-pinned

| VT | Meaning | Resolution site (shipped) | Pinning test(s) | Verdict |
|----|---------|----------------------------|-----------------|---------|
| **VT-001** | daemon process never probes CUDA / "status imports CUDA" (PRD §4.2bis caveat) | `daemon.py:566` comment + `daemon.py:573` `self._resolved_device_cache = self._unprobed_device_config()` (seed in `__init__`); `daemon.py:1585` docstring; recorder-host subprocess (`recorder_host.py`) owns all CUDA contexts | `test_daemon.py:1621` `calls["n"]==0`; `test_daemon.py:1654`; `test_daemon.py:1697`; `test_daemon.py:1720`/`1745` (VT-008 guard) | **RESOLVED** |
| **VT-002** | reseed device cache to un-probed config on host death / idle-unload (never stale, never None → would reintroduce VT-001) | `daemon.py:899-904` (host-death reseed at `self._resolved_device_cache = self._unprobed_device_config()`); `daemon.py:1244-1248` (idle-unload reseed); `daemon.py:1590` docstring | `test_daemon.py:3610` (host-death reseed), `test_daemon.py:3648` (idle-unload reseed); assertions at 3637 + 3675 | **RESOLVED** |
| **VT-003** | `__REPO__` placeholder + stable `$HOME/.local/bin/voicectl` launcher (no hardcoded `/home/<user>`) | `systemd/voice-typing.service:47` (placeholder comment); `install.sh:28` (UV override), `:116` (`sed __REPO__→$REPO`), `:174` (voicectl symlink); `hypr-binds.conf:21` (stable launcher) | `test_systemd_unit.py:258-330` (ExecStart `__REPO__`; install.sh `sed`/UV override/`ln -s` launcher; hypr bind path) | **RESOLVED** |
| **VT-004** | graphical-session.target After/PartOf/WantedBy (was default.target → cold-boot race past the compositor) | `systemd/voice-typing.service:3` (After), `:81` (WantedBy), `:84` (PartOf note); `install.sh:121` (removes stale `default.target.wants` symlink) | `test_systemd_unit.py:336-370` (After/PartOf/WantedBy = graphical-session.target; `rm -f` stale symlink) | **RESOLVED** |
| **VT-005** | `asr.device` value validation — only `cuda` \| `cpu` accepted (ValueError on typo) | `config.py:105` (device-value validation) | `test_config.py:164` (test header), `:173` (rejected + ValueError), `:180` (cuda/cpu round-trip) | **RESOLVED** |
| **VT-006** | bare `"you"` removed from blocklist defaults (common word, not a hallucination) | `config.py:191` (`NOTE (VT-006)`), `config.toml:67` (`NOTE (VT-006)`) | `test_config.py:25` (`_PRD_BLOCKLIST` 4-entry list); `test_textproc.py:94`, `:103` | **RESOLVED** |
| **VT-007** | abort-path unblock sentinel (API-drift robustness: a None-returning abort still unblocks the `text()` loop) | `recorder_host.py:511` (`aborted` flag), `:522` (`aborted.set()`), `:543` (clear), `:660` (docstring), `:675` (sentinel) | `test_recorder_host.py:494` (None-returning abort), `:511` (regression), `:529` (assertion), `:534` (complement: normal path does not emit) | **RESOLVED** |
| **VT-008** | daemon never imports `ctranslate2`/`torch` — VT-001 automated regression guard | (test-only guard; the invariant it guards is VT-001's `_resolved_device_cache` seed at `daemon.py:573`, commented from `:566`) | `test_daemon.py:1720` (docstring), `:1733` (assert), `:1745` (`"(VT-001/VT-008: the daemon must stay CUDA-free)"`) | **RESOLVED** |

**No VT-010+** references exist (the broader `VT-0[0-9][0-9]` grep returned the identical set above).

## 4. VT-001 headline resolution (the contract's explicit flag)

PRD §4.2bis (`PRD.md:144`) says *"voicectl status currently violates this [the daemon never imports
RealtimeSTT/torch/ctranslate2]; see BUGS.md VT-001."* **This violation NO LONGER EXISTS.**
- `daemon.py:573`: `self._resolved_device_cache: dict[str, str] = self._unprobed_device_config()` (the
  `# VT-001` comment block opens at `daemon.py:566`) — the cache is seeded in `__init__` with UN-PROBED
  config values, so the first `voicectl status` (and
  `install.sh`'s readiness poll) reads cached config and **never calls**
  `cuda_check.resolve_device_and_models`.
- `daemon.py:1585-1609` (`_resolved_device()` docstring): explicitly states *"VT-001: the daemon process
  MUST NEVER probe CUDA"* and that the method ONLY returns the cache / falls back to the UN-PROBED config
  (`daemon.py:1599`) — NEVER `cuda_check`.
- The **recorder-host subprocess** (`voice_typing/recorder_host.py`) owns the recorder + ALL CUDA
  contexts (the P1.M3.T2.S2 re-plan note at `daemon.py:573`); the daemon process never imports
  torch/ctranslate2/creates a CUDA context.
- `test_daemon.py:1621`: `assert calls["n"] == 0, "status_snapshot must NOT call
  cuda_check.resolve_device_and_models (VT-001)"` (also `:1654`, `:1697`).
- `test_daemon.py:1720`-`1745` (**VT-008**): a fresh-subprocess import-purity guard asserts the daemon
  process never has `ctranslate2`/`torch` in `sys.modules` — the **automated regression guard** so a
  future status field cannot reintroduce the import (`:1745` `"(VT-001/VT-008: the daemon must stay
  CUDA-free)"`).
- `gap_voicectl.md` §4.1 concurs (4 `VT-001` mentions): BUGS.md is absent (doc drift); the CLIENT `ctl.py`
  is import-clean; the daemon-side status path is fixed by the recorder-host model.
- `architecture/external_deps.md:34` registry: *"VT-001: `voicectl status` was reported as importing CUDA
  in the daemon process"* — classified RESOLVED.

**Verdict: VT-001 RESOLVED + test-pinned + regression-guarded.** The PRD caveat is the stale part
(read-only — routed §6).

## 5. Changeset-doc cleanliness — README + comments are CORRECT, not stale

- **README.md:** `grep -cni 'bugs\|VT-0' README.md` → **0.** The `### Model lifecycle & VRAM` section
  (`README.md:333`) already documents the recorder-host subprocess model + the bounded (`killpg` after
  5 s join) teardown — the VT-001-relevant architecture — in user-facing prose, without citing VT-* IDs.
  **No edit.** (Out of this task's lane regardless — README-completeness is P1.M6.T1.S1.)
- **`# VT-0NN` / `NOTE (VT-0NN)` source comments** (`daemon.py`, `recorder_host.py`, `config.py`,
  `systemd/voice-typing.service`, `install.sh`, `hypr-binds.conf`, `config.toml`): every one is an
  explanatory comment documenting a RESOLVED fix (the contract's acceptable state). **Removing them
  would LOSE the fix rationale + break the test↔comment↔code traceability the 17 gap audits rely on. Do
  NOT "clean up" the VT-* comments.** They are documentation, not drift.
- **`tests/`** VT-* references (`test_daemon.py`, `test_systemd_unit.py`, `test_config.py`,
  `test_recorder_host.py`, `test_textproc.py`, `ACCEPTANCE.md`): test names/docstrings + assertions that
  PIN the fixes (e.g. `test_daemon.py` VT-001/VT-008, `test_systemd_unit.py` VT-003/VT-004). Correct, not
  stale.

## 6. Read-only PRD drift register (routed for a human PRD edit — out of this task's scope)

| PRD location | Stale text | Why stale | Owner |
|---|---|---|---|
| `PRD.md:144` (§4.2bis) | "see BUGS.md VT-001" | BUGS.md does not exist (dangling ref) | human PRD edit (read-only here) |
| `PRD.md:144` (§4.2bis) | "voicectl status currently violates this" | VT-001/VT-008 FIXED it (status never probes CUDA; see §4) | human PRD edit (read-only here) |
| `PRD.md:261` (§4.5 blocklist) | still lists bare `"you"` | VT-006 removed it from code (`config.py:191`) + config (`config.toml:67`) + tests (`test_config.py:25`) | human PRD edit (read-only here) |

These are flagged as known doc drift, NOT defects in the shipped artifacts (which are clean). The
implementer cannot edit PRD.md (FORBIDDEN OPERATIONS); the recommendation is a PRD-only changeset by a
human.

## 7. Remediation — NONE required

The contract: *"If any unresolved VT-* issues found, create remediation tasks."* **No unresolved VT-*
issues exist** (§3: all eight RESOLVED + test-pinned; §5: changeset docs clean). Therefore:
- **No code remediation** (editing the resolved code/tests would REINTRODUCE the bugs + break the pinning
  tests).
- **No BUGS.md creation** (creating it would paper over the dangling PRD ref; the proper fix is a human
  PRD edit removing the "see BUGS.md VT-001" clause now that VT-001 is resolved).
- **One routed recommendation** (non-blocking): the read-only PRD drift (§6) should be fixed by a human
  in a PRD-only changeset. This is recorded, not executed.

## 8. Scope

- **IN scope (this task):** stale-reference audit + `gap_stale_refs.md` (the only write).
- **OUT of scope (cited, not duplicated):**
  - **README-completeness → P1.M6.T1.S1** (parallel; this task does NOT edit README — routed to avoid a
    parallel writer conflict; any optional README note is recorded here, not applied).
  - **Commit readiness → P1.M6.T1.S3** (final `git status` / integration commit; this task does not judge
    git cleanliness).
  - **PRD.md / tasks.json / prd_snapshot.md edits → human/orchestrator** (read-only here).
  - No source/test/script/config edit; no pytest; no heavy shell script (`test_idle_and_gpu.sh` /
    `e2e_virtual_mic.sh` are irrelevant to a doc-reference audit and forbidden by AGENTS.md unless
    explicitly required).
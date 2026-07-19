# Stale-Reference Audit Findings — P1.M6.T1.S2 (BUGS.md / VT-* doc drift)

**Status:** VERIFIED against the live tree (`/home/dustin/projects/voice-typing`, 2026-07-18).
**Purpose:** Pin the audit verdict + per-VT classification + the grep commands + the scope boundaries so
the PRP is one-pass implementable. The implementer RE-CONFIRMS these live (line numbers may have drifted).

---

## 0. The audit command (the contract's grep, authoritative)

```bash
# The exact input set the item contract specifies (source/tests/docs/config — NOT plan/, NOT .venv):
grep -rn 'BUGS\.md\|VT-00[0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf
# Broader (catches VT-010+; none expected):
grep -rn 'VT-0[0-9][0-9]' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf
```

Re-verify these EXACT sets at audit time. (The `plan/` research/gap docs + `.pi-subagents/artifacts/`
agent scratch contain VT-* references too, but those are NOT in scope — the contract scopes the audit to
the shipped source/tests/docs/config/install/systemd/hypr files.)

---

## 1. BUGS.md — does NOT exist (dangling PRD reference only)

- `find . -name BUGS.md` → **none** (verified). BUGS.md is absent from the entire repo tree.
- `grep -rn 'BUGS\.md' voice_typing/ tests/ README.md config.toml install.sh systemd/ hypr-binds.conf` →
  **ZERO hits.** No shipped file references BUGS.md.
- The ONLY BUGS.md reference is **PRD.md:144** (read-only): *"caveat: `voicectl status` currently
  violates this; see BUGS.md VT-001."* This is a **dangling reference** (the file it points to doesn't
  exist) inside the read-only PRD. `.pi-subagents/artifacts/42bab722_scout_1_output.md` also mentions it,
  but that is agent scratch, not a shipped artifact.
- **Classification:** doc drift, READ-ONLY (PRD.md is in the FORBIDDEN-TO-EDIT list). The implementer
  CANNOT create BUGS.md (it would paper over the drift) and CANNOT edit the PRD. → route to "human PRD
  edit (out of task scope)" in gap_stale_refs.md.

## 2. VT-* inventory — ALL are RESOLVED-in-code + test-pinned. ZERO unresolved bugs.

Every `VT-0NN` hit in the shipped tree is an **explanatory comment (or test name/docstring) documenting a
RESOLVED fix**, each backed by ≥1 pinning test. This is the contract's ACCEPTABLE state ("resolved in
code with comments explaining the fix"). There is **no unresolved VT-* issue in the code.**

| VT | One-line meaning | Resolution site (shipped) | Pinning test(s) | Verdict |
|----|------------------|----------------------------|-----------------|---------|
| **VT-001** | daemon process MUST NEVER probe CUDA / import ctranslate2/torch (PRD §4.2bis caveat says `voicectl status` "currently violates this") | `daemon.py:566` seeds `_resolved_device_cache` with the **UN-PROBED** config (status never calls `cuda_check`); `daemon.py:1585` docstring; the **recorder-host subprocess** (`recorder_host.py`) owns ALL CUDA contexts — the daemon process never creates one | `test_daemon.py:1596-1710` (status_snapshot NEVER calls cuda_check.resolve_device_and_models — `calls["n"]==0`); **`test_daemon.py:1720` VT-008** automated guard asserts the daemon process NEVER has `ctranslate2`/`torch` in `sys.modules` | **RESOLVED.** The PRD caveat is STALE (the violation no longer exists). |
| **VT-002** | after host death / idle-unload, the resolved-device cache must be RESEEDED to the un-probed config (not retained stale, not None → would reintroduce VT-001) | `daemon.py:899` (host-death reseed), `daemon.py:1244` (idle-unload reseed) | `test_daemon.py:3610-3675` (reseeded to CONFIGURED device, not the dead/unloaded child's cpu) | **RESOLVED** (derived invariant of VT-001). |
| **VT-003** | `__REPO__` placeholder in the systemd unit (portability across users/repo locations) + a STABLE `$HOME/.local/bin/voicectl` launcher (so Hyprland binds survive venv moves) | `systemd/voice-typing.service:47` (placeholder comment); `install.sh:28` (UV override), `:116` (`sed __REPO__→$REPO`), `:174` (voicectl symlink); `hypr-binds.conf:21` (bind uses the stable launcher) | `test_systemd_unit.py:258-330` (ExecStart uses __REPO__; install.sh substitutes it; no hardcoded /home/dustin; UV override; voicectl launcher; hypr bind path) | **RESOLVED.** |
| **VT-004** | the unit must order after + bind its lifecycle to `graphical-session.target` (was `default.target` → cold-boot race past the compositor exporting WAYLAND_DISPLAY) | `systemd/voice-typing.service:3,81,84` (After/PartOf/WantedBy = graphical-session.target); `install.sh:121` (removes stale default.target.wants symlink) | `test_systemd_unit.py:336-370` (After includes graphical-session.target; PartOf=; WantedBy=; install.sh `rm -f` stale symlink) | **RESOLVED.** |
| **VT-005** | `asr.device` value validation — only `"cuda"` \| `"cpu"` accepted (reject typos at load with a clear ValueError) | `config.py:105` (ValueError on invalid device) | `test_config.py:164-180` (rejected + round-trips cuda/cpu) | **RESOLVED** (hardening beyond the PRD §4.5 type check). |
| **VT-006** | bare `"you"` REMOVED from the blocklist defaults (it silently dropped the legitimate standalone word "you") | `config.py:191` (NOTE comment); `config.toml:67` (NOTE comment) | `test_config.py:25` (`_PRD_BLOCKLIST` 4-entry list); `test_textproc.py:94,103` | **RESOLVED.** (PRD §4.5 still lists "you" — read-only PRD drift; code/config/test are consistent.) |
| **VT-007** | abort-path unblock sentinel (API-drift robustness: if a future RealtimeSTT's abort returns None instead of '', a sentinel still unblocks the `text()` loop) | `recorder_host.py:511,522,543,660,675` (the `aborted` flag + the `('final',{text:''})` sentinel) | `test_recorder_host.py:494-534` (hypothetical None-returning abort still emits the sentinel; normal path does not) | **RESOLVED.** |
| **VT-008** | the daemon process must NEVER import `ctranslate2`/`torch` — the AUTOMATED regression guard for VT-001 (so a future status field cannot reintroduce the CUDA import) | (test-only guard; the invariant it guards is VT-001's `_resolved_device_cache` seed) | `test_daemon.py:1720-1745` (fresh-subprocess import-purity assertion) | **RESOLVED** (the guard; it pins VT-001). |

### VT-001 — the one the contract specifically flags ("If VT-001 is still present in code, flag it")

**VT-001 is NOT present in the code.** The "voicectl status imports CUDA in the daemon process" violation
the PRD §4.2bis caveat describes has been FIXED by the recorder-host subprocess architecture + the
un-probed device cache, and is regression-guarded by VT-008. Concrete proof (re-verify live):
- `daemon.py:566` — `self._resolved_device_cache = self._unprobed_device_config()` (seeded BEFORE any
  arm, so the first `status` never probes).
- `daemon.py:1585` docstring — "VT-001: the daemon process MUST NEVER probe CUDA (import ctranslate2 /
  torch / create a CUDA context)."
- `test_daemon.py:1621` — `assert calls["n"] == 0, "status_snapshot must NOT call
  cuda_check.resolve_device_and_models (VT-001)"`.
- `test_daemon.py:1745` — `"(VT-001/VT-008: the daemon must stay CUDA-free)"` (the automated guard).

**Verdict for VT-001: RESOLVED + test-pinned + regression-guarded.** The PRD caveat is the stale part
(read-only). gap_stale_refs.md must record this verdict explicitly (it is the headline finding).

## 3. The changeset docs (README/source/config) are CLEAN of stale references

- `grep -ni 'bugs\|VT-0' README.md` → **ZERO hits.** README has no stale BUGS.md/VT-* references.
- README's `### Model lifecycle & VRAM` section (L333) already documents the recorder-host subprocess
  model + the bounded (`killpg` after 5 s join) teardown — i.e. the VT-001-relevant architecture — in
  user-facing prose. It does NOT (and need not) cite VT-* issue IDs.
- Every `# VT-0NN` / `NOTE (VT-0NN)` comment in the source is a CORRECT explanatory comment (the
  contract's acceptable "resolved in code with a comment" state), NOT a stale reference. Removing them
  would LOSE the fix rationale + break the test ↔ comment ↔ code traceability the gap audits rely on.
  → **Do NOT "clean up" the VT-* comments. They are documentation, not drift.**

## 4. The only genuinely stale references are in the READ-ONLY PRD

| PRD location | Stale text | Why it's stale | Fixable here? |
|---|---|---|---|
| `PRD.md:144` (§4.2bis) | "see BUGS.md VT-001" | BUGS.md does not exist (dangling ref) | ❌ PRD is read-only |
| `PRD.md:144` (§4.2bis) | "`voicectl status` currently violates this" | VT-001/VT-008 FIXED it (status never probes CUDA) | ❌ PRD is read-only |
| `PRD.md` §4.5 blocklist | still lists bare `"you"` | VT-006 removed it from code + config + test | ❌ PRD is read-only |

→ These are **flagged for a human PRD edit** in gap_stale_refs.md (out of this task's scope — the
FORBIDDEN OPERATIONS list forbids editing PRD.md). The implementer records them as known doc drift, not
as a defect in the shipped artifacts.

## 5. Remediation tasks — NONE required

The contract: *"If any unresolved VT-* issues found, create remediation tasks."* **No unresolved VT-*
issues exist** (§2: all eight are RESOLVED + test-pinned; §3: the changeset docs are clean). Therefore:
- **NO code remediation tasks.** (Editing the resolved code/tests would REINTRODUCE the bugs.)
- **NO BUGS.md creation.** (Creating it would paper over the dangling ref; the proper fix is a human PRD
  edit removing the "see BUGS.md VT-001" clause now that VT-001 is resolved.)
- **ONE routed recommendation** (non-blocking): the read-only PRD drift (§4) should be fixed by a human
  in a PRD-only changeset. gap_stale_refs.md records this; it is NOT a task this item creates in the
  shipped tree.

## 6. [Mode B] doc resolution — the changeset-level sweep verdict

The item's DOCS note: *"[Mode B] Resolve any stale documentation references as part of the changeset-
level sweep."* The sweep finds:
- **README** — clean (no BUGS.md/VT-* refs); the VT-001-relevant architecture is already documented in
  the Model lifecycle section. **No edit required.**
- **Source/config comments** — all `VT-0NN`/`NOTE (VT-0NN)` comments are CORRECT fix-rationale
  documentation. **No edit required** (removing them would be destructive).
- **PRD** — stale (§4), but READ-ONLY. **Routed to a human PRD edit (out of scope).**

→ [Mode B] is SATISFIED by the CLEAN verdict in gap_stale_refs.md + the routed PRD-drift note. This is a
REPORT task; the shipped tree needs no edit.

## 7. Scope boundaries + sibling coordination (CRITICAL)

- **S1 (P1.M6.T1.S1, parallel)** owns README-COMPLETENESS (it audits README against §7 #7 + the 8-point
  checklist; it MAY apply an optional 1-row README edit). To avoid a README-writer conflict with the
  parallel S1, **this task does NOT edit README** — any optional README enhancement is RECORDED in
  gap_stale_refs.md as a routed recommendation, not applied here. (S1's PRP explicitly routes
  VT-001/stale-refs to THIS task, so the boundary is mutual.)
- **S3 (P1.M6.T1.S3)** owns the final commit readiness / `git status` check. This task does NOT judge
  git cleanliness or create the commit.
- **P1.M5.T5.S1 (acceptance gate)** already asserted "VT-003/VT-004 fixed in-source; VT-001 = doc-drift
  only (→ P1.M6.T1.S2)" (tests/ACCEPTANCE.md:37). gap_stale_refs.md is the deeper, per-VT confirmation
  the gate routed here.
- This task writes ONLY `plan/006_862ee9d6ef41/P1M6T1S2/gap_stale_refs.md`. It does NOT edit PRD.md,
  tasks.json, prd_snapshot.md, .gitignore, README.md, or any source/test/script/config file.

## 8. Validation approach — grep only (no pytest, no heavy script)

The audit is pure grep + read (fast, safe, no AGENTS.md timeout needed). The pinning tests are CITED
(file:line), not re-run — running them would load CUDA models (test_daemon.py / test_recorder_host.py)
and AGENTS.md forbids that unless explicitly required. The grep hits + the file:line citations are the
evidence; the tests' existence (already LIVE-green per the gap audits) is the proof the fixes hold.
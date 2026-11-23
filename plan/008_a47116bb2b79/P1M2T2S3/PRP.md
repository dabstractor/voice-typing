# PRP — P1.M2.T2.S3: Volume tier — wpctl snapshot + conditional restore

## Goal

**Feature Goal**: Implement the **sink-volume ducking backend** for PRD §4.2quinquies (D1): `voice_typing/ducking_volume.py` with `WpctlVolumeBackend`, the concrete subprocess tier that realizes the two volume primitives of S1's `DuckBackend` protocol (`get_sink_volume_pct` / `set_sink_volume_pct`) over **`wpctl` argv** (`/usr/bin/wpctl`, verified present). The compare-before-restore BOOKKEEPING stays in S1's `AudioDucker` (landed, verified); this backend is bounded subprocess primitives + the **concrete-node-id pinning** the tech notes prescribe (§4.4: `@DEFAULT_AUDIO_SINK@` re-resolves per invocation, so a restore-by-selector could hit the WRONG sink — snapshot the concrete node id at engage and restore **by id**, skipping gracefully if the node is gone). This delivers PRD test case (b) end-to-end: *volume restore skipped when the user changed volume mid-dictation*.

> **LIVE-VERIFIED this run** (research §1): `wpctl get-volume <id>` works by numeric node id; a gone node prints `Node 'N' not found` with **rc=0** (detection must be output-parse, not rc); volume floats can exceed 1.0 (observed 1.05 = 105%); the Sinks block of `wpctl status` carries the `*` default marker (and the Sources block has its OWN `*` — the parse must be scoped).

**Deliverable** (2 NEW files; no edits to existing sources — S1 owns `audio_ducking.py` [landed], S2 owns `ducking_mpris.py` [parallel]):
1. `voice_typing/ducking_volume.py` — module docstring (tier design + the node-id rationale + the mute decision), `WpctlVolumeBackend` (the sequence-driven node-pin state machine), the `_run(argv)` bounded-subprocess helper, `_resolve_default_node()` status parser, MPRIS protocol stubs (symmetric to S2's volume stubs).
2. `tests/test_ducking_volume.py` — 14 fake-runner tests (monkeypatched `subprocess.run`, ZERO real wpctl), including the **PRD case-(b) pin at the tier level** through S1's real `AudioDucker`.

**Success Definition**:
- (a) `get_sink_volume_pct()` resolves the default sink's concrete node id (Sinks-block `*` parse of `wpctl status`), reads its volume by id, parses `Volume: <float>[ MUTED]` → **pct** (`float × 100`, no clamp — 1.05 → 105.0); parse miss (`Node 'N' not found`, rc=0) → `None` + graceful unpin.
- (b) `set_sink_volume_pct(pct)` applies `wpctl set-volume <node-id> <pct>%` — **absolute** (no `+`/`-` prefix) — to the pinned node id; `True` on success, `False` swallowed.
- (c) The node pin is **sequence-driven** across the ducker's observable call grammar (`get, set(D) [, get, set(V0)]`): pinned at the engage-get, read-pinned at the release-get (compare-before-restore hits the DUCKED device, not a newly-selected sink), cleared after the release-set — correct even when `D == V0`.
- (d) Every wpctl call runs under `timeout=1.0`, `check=False`, `stderr=DEVNULL`; `TimeoutExpired`/`OSError`/`SubprocessError` → exactly ONE WARNING, safe default, nothing propagates; the tier **never issues `set-mute`** (mute sovereignty is structural — see Gotcha #4).
- (e) The MPRIS primitives are documented protocol-completeness stubs (`[]`/`False`, zero subprocess calls) — S2's backend owns the real ones; `mode="volume"` never calls them.
- (f) `timeout 300 .venv/bin/python -m pytest tests/test_ducking_volume.py -q` → **14 passed**; `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → **no new failures** beyond the recorded G1 classification (`tests/G1_BASELINE.md`); `git status --short` == the 2 new files only (plus any parallel siblings' files).

## User Persona

Not a user surface yet (`duck_mode` ships `"off"`; T4 flips the default to `"mpris"` with evidence — `"volume"` is the user-selectable fallback tier for non-MPRIS audio, e.g. a browser video without MPRIS). DOCS: **Mode A** — the module docstring carries the design (mirroring S1/S2). Beneficiaries: **T3** (wires `AudioDucker.from_config(cfg, backend)` — for `mode="volume"` the backend is `WpctlVolumeBackend`), **T4** (acceptance evidence: "video in a non-MPRIS app with `duck_mode="volume"` → volume ducks to 15% and restores exactly"), and the end user once enabled: speakers duck at arm, restore at stop, and a volume the user touched mid-dictation is never overridden.

## Why

- **PRD §4.2quinquies tier 2 is the non-MPRIS fallback.** MPRIS pause covers media players; the volume duck covers everything else playing through the default sink (browser games, notification-heavy apps). The PRD's core demand — "put it back EXACTLY as it found it" and "a restore that clobbers a user's manual change is worse than not ducking" — is delivered by S1's compare-before-restore + this tier's honest by-id read/write.
- **The selector re-resolution hazard is real and solved by node-id pinning.** `@DEFAULT_AUDIO_SINK@` is resolved by the session manager **per wpctl invocation** (tech notes §4.4, high confidence): if the user switches sinks mid-dictation, a restore-by-selector targets the NEW device (clobbering it) while the ducked one stays at 15%. Pinning the concrete node id at engage (tech notes' explicit design implication, and this item's RESEARCH NOTE) fixes both directions: the release-time compare reads the ducked node, and the restore targets the ducked node by id.
- **The rc=0 trap is live-verified.** A gone node returns rc=0 with `Node 'N' not found` — an rc-checking implementation would treat it as success and parse garbage. The grammar-parse + graceful-unpin design (research §2) implements the item's "skip gracefully if the node is gone".
- **No new dependencies, parallel-safe.** `wpctl` at `/usr/bin/wpctl` (verified); subprocess argv keeps the venv frozen. A separate `ducking_volume.py` keeps S1/S2/S3 disjoint in `git status` while S1's protocol and tests stay frozen (S2's PRP pins its own scope to its 2 files).

## What

A new `ducking_volume.py` implementing the 2 volume primitives of S1's `DuckBackend` over bounded wpctl subprocess calls, with a **sequence-driven node-pin state machine** (research §2 verbatim): the engage-time `get` resolves and pins the default sink's concrete node id; the engage `set` applies the absolute duck percent to that id; the release-time `get` reads the **pinned** node (so the ducker's compare-before-restore judges the ducked device); the release `set` restores the snapshot to the pinned id and clears the pin; a gone/parse-miss read unpins gracefully so the next engage re-resolves. Mute is snapshotted for the log but **never written** (structural sovereignty). MPRIS primitives are stubs. Plus `tests/test_ducking_volume.py` (14 fake-runner tests per research §7, mirroring S2's test style).

### Success Criteria

- [ ] `voice_typing/ducking_volume.py` exists; imports = `logging`, `re`, `subprocess` (+ `PlayerState` for typing only, mirroring S2).
- [ ] The 3 argv forms from research §6 are reproduced verbatim (tests pin them byte-for-byte): `get-volume <id|selector>`, `set-volume <id|selector> <pct>%` (absolute), `status`.
- [ ] `get_sink_volume_pct` / `set_sink_volume_pct` behave per Success Definition (a)-(c); the state machine matches the research §2 state table (all 6 rows pinned by tests).
- [ ] Every call bounded ≤1 s; failures journal exactly one line; nothing raises; **no `set-mute` argv ever appears**.
- [ ] MPRIS methods stubbed + documented (zero subprocess calls).
- [ ] 14 tests pass (incl. the case-(b) end-to-end pin through S1's real `AudioDucker`); fast suite shows no new failures; only the 2 new files in `git status`.

## All Needed Context

### Context Completeness Check

_Pass._ The design is fully pre-verified: S1's protocol is LANDED and was read line-by-line (the ducker's exact engage/release call sequences at `audio_ducking.py:148-176` drive the state machine); the wpctl grammar/argv/node-id/rc facts are **live-verified this run** (research §1, upgrading the tech notes' confidence); the state machine is spelled out with a state table + verbatim implementation skeleton (research §2); the subprocess helper, the status parser (scoped to the Sinks block — the Sources `*` trap), the mute decision, the exact argv forms, and all 14 tests are enumerated (research §3-§7). A developer new to the repo needs nothing beyond the research note + S1's 183-line `audio_ducking.py`.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/P1M2T2S3/research/wpctl_volume_tier.md
  why: "§0 S1's landed protocol + the ducker's exact call sequences. §1 ★ LIVE-VERIFIED wpctl facts (numeric-id
        get works; gone node rc=0 'Node not found'; vol can exceed 1.0; Sources has its own '*'). §2 the
        sequence-driven node-pin state machine (verbatim skeleton + 6-row state table). §3 the mute decision
        (never set-mute). §4 the _run subprocess discipline. §5 the Sinks-scoped status parser. §6 the exact
        argv forms. §7 the 14-test matrix. §8 tooling + the LIVE-SET-FORBIDDEN rule."
  critical: "§1 (rc=0 trap), §2 (state machine — the core), §7 (the tests) are load-bearing."
- docfile: plan/008_a47116bb2b79/architecture/external_tech_notes.md
  why: "§4 wpctl volume: grammar (4.1), absolute-vs-relative percent (4.2), float round-trip + independent mute
        (4.3), the per-invocation selector re-resolution that motivates node-id pinning (4.4 — this item's
        RESEARCH NOTE). §3.5 the sovereignty design this tier slots into."
  critical: "§4.2: bare '<pct>%' = ABSOLUTE set — never emit a +/- prefix. §4.4: restore by concrete id."
- docfile: plan/008_a47116bb2b79/P1M2T2S1/PRP.md
  why: "S1's contract: the DuckBackend protocol (5 primitives), the AudioDucker bookkeeping (ledger +
        compare-before-restore with _VOL_EPS=0.5 pct), the failure discipline, and the explicit S2/S3/T3/T4
        deferrals. S1 is LANDED (audio_ducking.py:183L, test_ducking.py:250L — verified in the tree)."
  critical: "Do NOT edit audio_ducking.py or its tests — the protocol is frozen. The ducker owns ALL
             bookkeeping; the tier is primitives + node pinning only."
- docfile: plan/008_a47116bb2b79/P1M2T2S2/PRP.md
  why: "The sibling tier PRP to MIRROR: ducking_mpris.py structure (module docstring + _run helper + stubs for
        the OTHER tier's primitives + fake-runner tests pinning exact argv), and its Success-Definition (e)
        handoff: 'the volume methods are documented stubs — S3's wpctl backend owns the real ones'."
  critical: "Symmetry: S3 stubs the MPRIS primitives exactly as S2 stubs the volume ones. Do NOT touch
             ducking_mpris.py (parallel task, its own git scope)."
- docfile: plan/008_a47116bb2b79/architecture/d1_ducking_seams.md
  why: "§1e the subprocess-with-timeout pattern for the tiers (S2/S3 own the subprocess imports — S1 stays
        stdlib-only). §1c/§1d the engage/release choke points are T3's. §5 tests/test_ducking*.py with pure
        fakes is the seam."
  critical: "Do NOT wire the daemon (T3), flip the default (T4), or add config keys (P1.M2.T1.S1 landed)."
- file: voice_typing/audio_ducking.py
  why: "READ-ONLY. The landed protocol surface (L44-57) + the ducker's volume sequences (_engage_volume L148-158,
        _release_volume L160-176: get → set(D); get → compare-vs-D(±0.5pct) → maybe set(V0)) that define the
        backend's observable call grammar. _call (L177) is the swallow precedent above the backend's own."
  critical: "The backend's state machine is driven ONLY by this call sequence — no new protocol methods."
- file: PRD.md   # §4.2quinquies (Media ducking)
  why: "Tier-2 spec: 'At arm: read and store the default sink's current volume (wpctl get-volume
        @DEFAULT_AUDIO_SINK@), then set duck_volume_pct. At disarm: restore the stored value ONLY if the
        current volume still equals what we last set.' + the failure discipline + test case (b)."
  critical: "The PRD's selector-level wording is REFINED by the tech notes §4.4 / the item contract to
             concrete-node-id pinning — implement the refinement."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── audio_ducking.py     # LANDED (S1) — READ-ONLY: PlayerState + DuckBackend + AudioDucker.
├── ducking_mpris.py     # S2 (parallel) — READ-ONLY: the busctl tier + its volume stubs.
└── ducking_volume.py    # CREATE (this task): WpctlVolumeBackend + _run + _resolve_default_node + MPRIS stubs.
tests/
├── test_ducking.py      # LANDED (S1) — READ-ONLY (12 fake-backend tests).
├── test_ducking_mpris.py# S2 (parallel) — READ-ONLY.
└── test_ducking_volume.py # CREATE (this task): 14 fake-runner tests + the case-(b) end-to-end pin.
```

### Desired Codebase tree (unchanged structure — 2 new files)

```bash
# Same tree + voice_typing/ducking_volume.py + tests/test_ducking_volume.py. Nothing else changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ★ rc LIES ON A GONE NODE (live-verified). `wpctl get-volume 99999` prints
#   "Node '99999' not found" with rc=0. Failure detection MUST be the output grammar
#   (re.match(r"^Volume:\s*(\d+(?:\.\d+)?)")) — NEVER the return code. On a pinned-node miss, ALSO clear the
#   pin (graceful skip + self-heal so the next engage re-resolves). (Research §1/§2.)
# CRITICAL #2 — THE NODE PIN IS SEQUENCE-DRIVEN, NOT VALUE-DRIVEN. The backend cannot see engage/release; it
#   infers them from S1's ducker call grammar (get, set(D) [, get, set(V0)]). Pin at the fresh get; read the
#   pin at the ducked get; clear after the second successful set. A value-driven hack (compare pct to the duck
#   target) breaks when D == V0 (sink already at 15%) — the sequence design does not. Follow research §2's
#   state table exactly; all 6 rows are pinned by tests. (Research §2.)
# CRITICAL #3 — PERCENT IS ABSOLUTE AND UNCLAMPED. Emit f"{pct:.0f}%" with NO +/- prefix (a '+' would make it
#   relative). Parse-side: vol floats can exceed 1.0 (live 1.05) — pct = float*100, never clamp; the ducker's
#   0.5-pct epsilon handles float dust. (Research §1, tech notes §4.2.)
# CRITICAL #4 — NEVER ISSUE set-mute. wpctl set-volume does not touch mute, so mute cannot change by our hand;
#   restoring it would require writing it, which would fight a user who muted/unmuted mid-dictation (the exact
#   §4.2quinquies violation). Snapshot the [MUTED] flag for the engage log ONLY. The item's "restore ... mute"
#   is satisfied vacuously — document it in the docstring so nobody "completes" it with a set-mute pair. (§3.)
# CRITICAL #5 — THE STATUS PARSE IS SINKS-SCOPED. wpctl status has a '*' default marker in the Sinks block AND
#   another in Sources (live-observed 72 vs 74). Parse only between "Sinks:" and "Sources:"; the Sources '*'
#   must never be picked. No '*' in Sinks → None → the get falls back to the @DEFAULT_AUDIO_SINK@ selector
#   (correct for a one-shot read; log DEBUG). (Research §5.)
# CRITICAL #6 — LIVE `wpctl set-volume` IS FORBIDDEN IN VALIDATION. It would mutate the operator's real audio.
#   Unit tests use a fake runner (monkeypatched subprocess.run, ZERO real wpctl); live probes are READ-ONLY
#   (get-volume/status). The live duck+restore is T4's acceptance evidence. (Research §8.)
# CRITICAL #7 — SUBPROCESS DISCIPLINE (mirror S2): timeout=1.0, check=False, stderr=DEVNULL, capture stdout;
#   TimeoutExpired/OSError/SubprocessError → ONE warning (no exc_info), safe default, never raises. This is
#   the fourth subprocess site (feedback.py, typing_backends.py, ducking_mpris.py) — keep it in THIS module.
# CRITICAL #8 — SCOPE: no audio_ducking.py edits (S1, frozen), no ducking_mpris.py edits (S2, parallel), no
#   daemon/config/feedback/systemd edits (T3/T4/P1.M2.T1.S1), no new deps, no PRD/tasks/snapshot/.gitignore.
#   AGENTS.md: every pytest under `timeout N` + the bash-tool timeout; FULL tool paths (.venv/bin/python).
```

## Implementation Blueprint

### Data models and structure

```python
class WpctlVolumeBackend:            # implements S1's DuckBackend (runtime_checkable — no inheritance needed)
    _node: int | None                # the pinned (engaged) default-sink node id
    _ducked: bool                    # True between the engage-set and the release-set
    _muted_at_engage: bool | None    # diagnostics only (never written back — Critical #4)
    # MPRIS stubs: list_players -> [], pause/resume -> False (zero subprocess) — symmetric to S2's volume stubs
```

### Implementation Tasks (ordered)

```yaml
Task 1: CREATE voice_typing/ducking_volume.py (mirror ducking_mpris.py's structure)
  - MODULE DOCSTRING (Mode A): the tier design (wpctl snapshot + conditional restore), the node-id rationale
    (§4.4 selector re-resolution → pin the concrete id, restore by id, skip gracefully when gone), the mute
    decision (never set-mute — sovereignty is structural), the rc=0 trap, and the S1/S2/T3/T4 ownership map.
  - IMPLEMENT per research §2/§4/§5 verbatim skeletons: _run/_run_ok, _resolve_default_node (Sinks-scoped),
    get_sink_volume_pct (pin-or-read-pinned + grammar parse + gone-node unpin), set_sink_volume_pct (absolute
    pct to the pinned id; sequence-driven ducked/pin transitions), MPRIS stubs.
Task 2: CREATE tests/test_ducking_volume.py (14 tests per research §7; repo docstring/banner style)
  - _FakeRunner: records argv (the pin target/value assertions), canned stdout/rc/raise per argv, mid-session
    mutation hooks (volume change, status default swap). ZERO real subprocess.
  - Include test_case_b_end_to_end_user_changed_volume_no_write through S1's REAL AudioDucker (the PRD pin).
Task 3: VALIDATE
  - timeout 300 .venv/bin/python -m pytest tests/test_ducking_volume.py -q   → 14 passed
  - timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q  → no new failures
  - (Optional) /home/dustin/.local/bin/ruff check voice_typing/ducking_volume.py tests/test_ducking_volume.py
  - git status --short == the 2 new files (+ parallel siblings' files only)
```

### Implementation Patterns & Key Details

```python
# (1) The engage/release state machine over S1's ducker call grammar (Critical #2 — sequence-driven):
#     ducker: get ──► set(D) ──► get ──► set(V0) | (user changed: no set) | (node gone: no set)
#     backend: pin default at the fresh get; _ducked=True after the 1st successful set; the ducked get reads
#     the PIN; _ducked=False + pin=None after the 2nd successful set. Parse-miss on a pinned node unpins.

# (2) The get (grammar parse, NEVER rc — Critical #1):
out = self._run(["wpctl", "get-volume", str(target)])
m = re.match(r"^Volume:\s*(\d+(?:\.\d+)?)", out or "")
if m is None:
    if self._ducked and self._node is not None:   # gone node → graceful skip + self-heal
        logger.info("ducking(volume): sink node %s gone; unpinning", self._node)
        self._node, self._ducked = None, False
    return None
return float(m.group(1)) * 100.0                  # unclamped (1.05 → 105.0 — Critical #3)

# (3) The set (absolute, by pinned id — Critical #3):
ok = self._run_ok(["wpctl", "set-volume", target, f"{pct:.0f}%"])   # NEVER "+15%" / "-15%"
#     ...on success: flip the sequence state (research §2 state table)...

# (4) The status parse is scoped to the Sinks block (Critical #5) — the Sources '*' (74) must never win.
```

### Integration Points

```yaml
CONSUMED-BY (later D1 tasks — do not implement):
  - T3: 'daemon wiring: for duck_mode="volume", AudioDucker.from_config(cfg, WpctlVolumeBackend())'
  - T4: 'the default-flip acceptance evidence runs this tier (video in a non-MPRIS app ducks + restores)'
PROTOCOL (frozen, S1):
  - implements: 'DuckBackend.get_sink_volume_pct / set_sink_volume_pct (+ 3 MPRIS stubs)'
  - consumed-by-ducker: '_engage_volume (get→set(D)) / _release_volume (get→compare±0.5pct→maybe set(V0))'
ENVIRONMENT:
  - binary: '/usr/bin/wpctl (verified present); no new python deps'
SYMmetry:
  - mirrors: 'ducking_mpris.py (S2) — module shape, _run discipline, other-tier stubs, fake-runner tests'
```

## Validation Loop

### Level 1–2 (the gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_ducking_volume.py -v                  # 14 passed
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q      # no NEW failures
# Optional: /home/dustin/.local/bin/ruff check voice_typing/ducking_volume.py tests/test_ducking_volume.py
```

### Level 3 (protocol conformance smoke — in-process, NO real wpctl)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python - <<'PY'
# Proves: S1's real AudioDucker drives this backend end-to-end with a fake runner (case b included).
import subprocess
from voice_typing.audio_ducking import AudioDucker
from voice_typing.ducking_volume import WpctlVolumeBackend

calls = []
state = {"vol": 0.50}   # the fake sink: 50%
def fake_run(argv, **kw):
    calls.append(list(argv))
    a0 = " ".join(argv)
    if argv[1] == "status":
        return subprocess.CompletedProcess(argv, 0, "Audio\n ├─ Sinks:\n │  *   72. Fake Sink [vol: 1.00]\n ├─ Sources:\n │  *   74. Mic\n", "")
    if argv[1:2] == ["get-volume"]:
        if argv[2] == "99999":
            return subprocess.CompletedProcess(argv, 0, "Node '99999' not found", "")   # rc=0 trap
        return subprocess.CompletedProcess(argv, 0, f"Volume: {state['vol']:.2f}\n", "")
    if argv[1:2] == ["set-volume"]:
        state["vol"] = float(argv[-1].rstrip("%")) / 100.0
        return subprocess.CompletedProcess(argv, 0, "", "")
    raise AssertionError(a0)
subprocess.run = fake_run

b = WpctlVolumeBackend()
d = AudioDucker(b, mode="volume", volume_pct=15)
d.engage(); d.engage()                                  # idempotent
sets = [c for c in calls if c[1] == "set-volume"]
assert sets == [["wpctl", "set-volume", "72", "15%"]], sets   # pinned id, absolute, ONE set
assert b._node == 72 and b._ducked is True
d.release()                                             # untouched volume → restore
assert calls[-1] == ["wpctl", "set-volume", "72", "50%"]      # restore by pinned id
assert b._node is None and b._ducked is False
state["vol"] = 0.80                                     # case (b): the fake engage-set left vol=0.15;
d.engage(); state["vol"] = 0.80; d.release()            # the user then changed it to 80 mid-dictation
sets = [c for c in calls if c[1] == "set-volume"]
assert sets[-1] == ["wpctl", "set-volume", "72", "15%"]       # NO restore write after the engage set
print("OK: volume-tier smoke (pin/absolute/idempotent/case-b) passed")
PY
```

### Level 4 (scope guard)

```bash
git status --short   # == voice_typing/ducking_volume.py + tests/test_ducking_volume.py (new; parallel siblings'
                     #    files only besides). NO audio_ducking.py / ducking_mpris.py / daemon / config edits.
grep -c "set-mute" voice_typing/ducking_volume.py   # 1 — the docstring's "never set-mute" note ONLY (no argv).
```

## Final Validation Checklist

- [ ] 14 tests pass; fast suite shows no new failures (both under `timeout`; G1 classification unchanged).
- [ ] Level-3 smoke prints OK (pin/absolute/idempotence/case-b end-to-end over S1's real ducker).
- [ ] Module docstring states the tier design, node-id rationale, mute decision, rc=0 trap (Mode A).
- [ ] No `set-mute` argv anywhere; no live `wpctl set-volume` executed at any validation level.
- [ ] Only the 2 new files in `git status --short`.

## Anti-Patterns to Avoid

- ❌ Don't detect failure by return code — the gone-node path is rc=0 (Critical #1).
- ❌ Don't drive the node pin by VALUES ("is this pct the duck target?") — it breaks when D == V0; drive it by the call SEQUENCE (Critical #2).
- ❌ Don't emit `+`/`-` percent prefixes (relative-set hazard) and don't clamp parsed volume to 1.0 (Critical #3).
- ❌ Don't add mute write-back — sovereignty is structural (Critical #4).
- ❌ Don't parse the Sources block's `*` — scope to Sinks (Critical #5).
- ❌ Don't run a live `wpctl set-volume` in any validation (Critical #6) — that's T4's acceptance run.
- ❌ Don't edit `audio_ducking.py` / S1's tests (frozen), `ducking_mpris.py` (S2, parallel), or daemon/config (T3/T4) (Critical #8).
- ❌ Don't let anything raise out of a protocol method or log more than one line per failure (Critical #7).
- ❌ Don't run un-timed commands or bare `python`/`pytest` (AGENTS.md; Critical #8).

---

## Confidence Score

**9/10** — one-pass success likelihood. The protocol consumer (S1's `AudioDucker`) is LANDED and its exact call sequences were read line-by-line; the wpctl grammar, numeric-id targeting, rc=0 gone-node behavior, >1.0 volumes, and the Sinks/Sources `*` trap are **live-verified on this machine** (research §1); the state machine is fully specified with a 6-row state table + verbatim skeleton and every row is pinned by an enumerated test; the case-(b) PRD pin is proven end-to-end in the Level-3 smoke design. Residual risk: the state-machine flip logic (`set` success transitions) is the one fiddly spot — mitigated by the verbatim skeleton, the state table, and the degenerate-case test (row 6 / test 14).

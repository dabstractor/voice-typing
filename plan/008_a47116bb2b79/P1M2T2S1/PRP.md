# PRP — P1.M2.T2.S1: AudioDucker core + Backend protocol + bookkeeping

## Goal

**Feature Goal**: Create `voice_typing/audio_ducking.py` — the **AudioDucker** orchestration core for media ducking (PRD §4.2quinquies, D1): `engage()`/`release()` over an **injectable `DuckBackend` protocol**, idempotent in both directions, release-without-engage = no-op, `duck_mode="off"` = byte-identical no-op. The ducker owns the **bookkeeping** — the paused-player ledger (name + was-`Playing`, captured at engage) and the pre-duck volume snapshot — and enforces the PRD's **user-sovereignty rules** at release: MPRIS resume-ONLY players (a) we paused, (b) that were `Playing` before, (c) that are STILL `Paused` now; volume restore ONLY if the current volume still equals what we set (compare-before-restore). The concrete subprocess backends are the sibling tiers: **S2** (busctl MPRIS) and **S3** (wpctl volume) implement the protocol; **S4** hardens the arm-latency bound; **T3** wires the daemon lifecycle. This task is the protocol + core + pure unit tests only.

**Deliverable** (2 NEW files; no edits to existing sources):
1. `voice_typing/audio_ducking.py` — module docstring (Mode A: tiers + sovereignty rules), `PlayerState` dataclass, `DuckBackend` Protocol (5 methods), `AudioDucker` (bookkeeping + engage/release + `from_config`), stdlib-only top.
2. `tests/test_ducking.py` — 12 pure unit tests over a `_FakeBackend` (no subprocess, no daemon, no CUDA).

**Success Definition**:
- (a) `AudioDucker(backend, mode="mpris").engage()` pauses exactly the `Playing` players and ledgers them; `.release()` resumes ONLY ledger names that still exist and are still not playing — a player the user resumed stays playing, a player the user paused themselves is never touched.
- (b) `mode="volume"`: engage snapshots the current sink volume and sets `duck_volume_pct`; release restores the snapshot ONLY when the current volume still equals `duck_volume_pct` (user change ⇒ no write, one INFO line).
- (c) Idempotence: double-engage performs ONE pause set / preserves the ORIGINAL snapshot; release-without-engage makes ZERO backend calls; `mode="off"` makes ZERO backend calls across engage+release.
- (d) A backend method raising is swallowed (one WARNING, never propagates); a failed volume read leaves no snapshot so release no-ops.
- (e) `timeout 300 .venv/bin/python -m pytest tests/test_ducking.py -q` → all pass; `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (plus the suites' current known-red classification stays unchanged — new file adds only greens).
- (f) Only the 2 new files exist in `git status --short`; no daemon/config/feedback/systemd edits (S2/S3/S4/T3/T4 own those).

## User Persona

Not applicable as a user surface yet (`duck_mode` ships `"off"` per the parallel config task P1.M2.T1.S1; the default flips to `"mpris"` only in T4 with evidence). DOCS: **Mode A** — the module docstring states the two tiers + the sovereignty rules; the user-facing `config.toml [audio]` comments already ride with P1.M2.T1.S1. Beneficiaries: S2/S3 (implement the protocol this task defines), S4/T3 (consume `engage`/`release`/`engaged`), and the end user once enabled (music pauses at arm, resumes at stop, user changes never overridden).

## Why

- **§4.2quinquies is the spec, and its sovereignty rules are the product.** Media bleed is a leading "wrong words that change meaning" source; but the PRD's core demand is *put it back EXACTLY as found* — "a restore that clobbers a user's manual change is worse than not ducking". The ledger + compare-before-restore bookkeeping IS that guarantee, and it must live in ONE place (the ducker), not be re-derived by each tier.
- **The protocol seam unblocks three parallel tasks.** S2 (busctl) and S3 (wpctl) need only implement the 5 primitives; S4/T3 need only the engage/release/engaged surface. Defining it now (with the exact sovereignty semantics baked into the ducker) means the tiers stay thin subprocess wrappers and can't get the restore rules wrong.
- **The failure discipline starts here.** Ducking is NEVER a gate: the ducker's own `_call()` swallow (mirroring `feedback.py:247-261`'s `_notify` discipline — the only subprocess-swallow precedent in the repo, verified: zero `subprocess.run(..., timeout=)` exist today) guarantees a misbehaving backend can never break an arm or disarm path.
- **Cheap, pure, zero-risk to land.** stdlib-only module + fake-backend tests; nothing existing changes (`off` default). Even before S2/S3 land, the core is fully testable and the protocol is frozen for the tiers.

## What

A new `audio_ducking.py`: `PlayerState` frozen dataclass (`name`, `playing`); `DuckBackend` runtime-checkable Protocol (`list_players() -> list[PlayerState]`, `pause_player(name) -> bool`, `resume_player(name) -> bool`, `get_sink_volume_pct() -> float | None`, `set_sink_volume_pct(pct) -> bool` — every method bounded ≤1 s, best-effort, never raises); `AudioDucker(backend, *, mode, volume_pct)` with `engage()`/`release()`/`engaged` property/`from_config(cfg, backend)` classmethod; bookkeeping under one `threading.Lock`; a `_call(description, fn, default)` swallow helper (one WARNING per failure, no traceback spam). Plus `tests/test_ducking.py` (12 tests, `_FakeBackend`).

### Success Criteria

- [ ] `voice_typing/audio_ducking.py` exists; module top is stdlib-only (`logging`, `threading`, `dataclasses`, `typing`).
- [ ] `PlayerState` + `DuckBackend` Protocol + `AudioDucker` as specified; `from_config` reads `cfg.audio.duck_mode` / `cfg.audio.duck_volume_pct` (the P1.M2.T1.S1 contract).
- [ ] engage: mpris tier pauses only-`Playing` players into the ledger; volume tier snapshots-then-sets, storing the snapshot only on a successful set.
- [ ] release: mpris resumes only (ledger ∧ still-present ∧ not-currently-playing); volume restores only when current == `duck_volume_pct` (±0.5 pct eps); both clear bookkeeping.
- [ ] Idempotence + no-op gates verified (double-engage, release-without-engage, off-mode) with the fake's call log.
- [ ] Backend exceptions swallowed with exactly ONE warning (caplog), never propagating.
- [ ] 12 tests pass; fast suite 0 failed beyond the pre-existing classified reds; only the 2 new files in `git status`.

## All Needed Context

### Context Completeness Check

_Pass._ The design is fully specified with verbatim source (Implementation Blueprint) verified against: the PRD §4.2quinquies sovereignty rules (quoted in the research §1), the seams doc §1e subprocess facts (only feedback.py:66 + typing_backends.py:47 import subprocess; zero `timeout=` on run calls today — grep-confirmed), the parallel config contract (P1.M2.T1.S1 PRP: `AudioConfig(duck_mode="off", duck_volume_pct=15)` as `cfg.audio.*`), and the D1 task boundary (S2/S3/S4/T3/T4 deferrals). The 12 tests are enumerated with their exact assertions. No daemon, config, or feedback knowledge is required — the core is self-contained.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/P1M2T2S1/research/audio_ducker_core.md
  why: "§1 verified facts (subprocess discipline, config contract, PRD sovereignty rules, the D1 task boundary).
        §2 the design (protocol + bookkeeping + engage/release semantics + _call swallow). §3 the 12 tests. §4 tooling."
  critical: "§2 is the contract: ONE protocol (5 primitives), ledger filled only with was-Playing names at engage,
             compare-before-restore at release, _engaged set FIRST so a partial engage still unwinds."
- docfile: plan/008_a47116bb2b79/architecture/d1_ducking_seams.md
  why: "§1e: the subprocess-with-timeout pattern for the TIER backends (S2/S3) + the fact that this task's module
        keeps the third subprocess import local (S2/S3 add it, not S1 — S1 is stdlib-only). §1c/§1d: the engage/
        release choke points + lock discipline are T3's (do not implement them here). §2: the ducked feedback flag
        is T3.S2's. §5: confirms tests/test_ducking.py with pure fakes is the seam for this layer."
  critical: "Do NOT wire the daemon, add the ducked flag, or write any subprocess call — those are T3/S2/S3/S4."
- docfile: plan/008_a47116bb2b79/P1M2T1S1/PRP.md
  why: "The config contract this task consumes: AudioConfig(duck_mode: str = 'off' (off|mpris|volume, TypeError
        guard), duck_volume_pct: int = 15 (non-bool-int guard)) exposed as cfg.audio.* — parallel task; assume
        landed exactly as specified."
  critical: "from_config reads cfg.audio.duck_mode / cfg.audio.duck_volume_pct. The plain constructor
             (backend, mode=, volume_pct=) keeps unit tests independent of the config module."
- file: voice_typing/feedback.py
  why: ":247-261 _notify — the swallow-discipline pattern the ducker's _call() mirrors at the orchestration layer
        (check=False style adapted to 'never raises' protocol methods + one log line, no traceback)."
  critical: "Mirror the DISCIPLINE, not the subprocess call — S1 makes zero subprocess calls."
- file: PRD.md   # §4.2quinquies (Media ducking while listening)
  why: "The authoritative spec: the two tiers, the sovereignty rules ((a)(b)(c) + compare-before-restore), the
        failure discipline ('an enhancement, NEVER a gate', idempotent, one-line failures), and the test list (a)
        (b) (e) that this layer's unit tests cover at the fake-backend level."
  critical: "Sovereignty is enforced by the BOOKKEEPING in the ducker, not by the tiers — that placement is the
             point of this task."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── audio_ducking.py   # CREATE (module: PlayerState + DuckBackend + AudioDucker; stdlib-only top).
└── ...                # daemon.py / config.py / feedback.py — UNCHANGED (T3 + parallel S1-config own them).
tests/
└── test_ducking.py    # CREATE (12 pure tests + _FakeBackend; mirrors the repo's docstring/banner style).
```

### Known Gotchas

```python
# CRITICAL #1 — SET _engaged FIRST inside engage (under the lock), THEN do the tier work. A partially-failed
#   engage (player A paused, player B's pause raised) must still unwind via release() — the ledger holds A.
#   Symmetrically, only a SUCCESSFUL volume set stores the snapshot (a failed set changed nothing → release no-ops).
# CRITICAL #2 — THE LEDGER IS THE (a)+(b) GUARANTEE. Fill it ONLY with names that were `Playing` at engage AND
#   whose pause succeeded. Rule (c) (still-Paused-now) is checked at release against a FRESH list_players(). A
#   player the user paused themselves is never in the ledger → never resumed → never fought.
# CRITICAL #3 — COMPARE-BEFORE-RESTORE against WHAT WE LAST SET (duck_volume_pct), with a small epsilon
#   (0.5 pct) — NOT float equality. User-touched volume ⇒ log one INFO ("keeping user value") and write NOTHING.
# CRITICAL #4 — NEVER RAISE OUT OF engage()/release(). _call() swallows any backend exception → ONE warning
#   (no exc_info traceback — the PRD's "one line and otherwise invisible"). Idempotence + the off/no-op gates
#   must also hold on the failure paths.
# CRITICAL #5 — HOLD the single threading.Lock across each whole engage()/release() body (it serializes the two
#   and makes idempotence trivial). Backend calls are ≤1 s by contract, T3 calls engage/release from spawned
#   threads, so lock-held-during-calls is safe; do NOT introduce a second lock.
# CRITICAL #6 — SCOPE: no daemon wiring (T3), no busctl/wpctl subprocess calls (S2/S3 — S1 imports no
#   subprocess), no ducked feedback flag (T3.S2), no default flip (T4), no config edits (parallel P1.M2.T1.S1).
# CRITICAL #7 — AGENTS.md: every pytest run under `timeout N` (inner) + bash-tool timeout (outer). Full paths.
```

## Implementation Blueprint

### Data models and structure

```python
@dataclass(frozen=True)
class PlayerState:
    name: str
    playing: bool

@runtime_checkable
class DuckBackend(Protocol):
    def list_players(self) -> list[PlayerState]: ...
    def pause_player(self, name: str) -> bool: ...
    def resume_player(self, name: str) -> bool: ...
    def get_sink_volume_pct(self) -> float | None: ...
    def set_sink_volume_pct(self, pct: float) -> bool: ...

class AudioDucker:
    _engaged: bool; _paused_players: list[str]; _volume_snapshot: float | None
    _lock: threading.Lock; _backend; _mode: str; _volume_pct: float
```

### Implementation Tasks (ordered)

```yaml
Task 1: CREATE voice_typing/audio_ducking.py
  - MODULE DOCSTRING (Mode A): the two tiers (MPRIS pause primary / sink-volume duck fallback), the sovereignty
    rules VERBATIM from §4.2quinquies, the failure discipline (bounded, one-line, never a gate, idempotent),
    and the S2/S3 ownership note (the subprocess backends implement DuckBackend elsewhere).
  - Implement per the verbatim block below. Stdlib-only top. No daemon/config imports in the module body
    (from_config takes the cfg object duck-typed).
Task 2: CREATE tests/test_ducking.py (12 tests per research §3; repo docstring/banner style; _FakeBackend)
Task 3: VALIDATE (pytest under timeout; fast suite; git status)
```

### Verbatim module (audio_ducking.py — the functional core)

```python
"""voice_typing.audio_ducking — media ducking while listening (PRD §4.2quinquies, D1).

TWO TIERS (best-effort, strictly an enhancement — NEVER a gate on arming):
  1. MPRIS pause (primary): at engage, pause every MPRIS player that is `Playing`;
     at release, resume them. Implemented over the DuckBackend protocol; the concrete
     busctl subprocess backend is a sibling task (P1.M2.T2.S2).
  2. Sink-volume duck (fallback, non-MPRIS audio): snapshot the default sink volume,
     set duck_volume_pct, restore at release. wpctl backend = P1.M2.T2.S3.

USER SOVEREIGNTY (the product — PRD §4.2quinquies, enforced HERE by the bookkeeping):
  - Resume ONLY players (a) that WE paused, (b) that were `Playing` before we paused
    them (the ledger records only those), and (c) that are STILL `Paused` at release.
    If the user resumed a player mid-dictation, or paused a different one, we never
    fight them — restore is additive, never destructive.
  - Volume restore ONLY if the current volume still equals what we last set
    (compare-before-restore). If the user touched the volume mid-dictation, THEIR
    value wins and we write nothing.

FAILURE DISCIPLINE: engage/release are idempotent, release-without-engage is a no-op,
duck_mode="off" touches nothing, and every backend call is swallowed into ONE warning
line (a ducking failure must never break an arm or disarm path).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_VOL_EPS = 0.5  # pct tolerance for the compare-before-restore check


@dataclass(frozen=True)
class PlayerState:
    """One MPRIS player as seen by list_players(): bus name + PlaybackStatus."""

    name: str
    playing: bool


@runtime_checkable
class DuckBackend(Protocol):
    """Subprocess seam the tier backends implement (S2: busctl MPRIS; S3: wpctl volume).

    Contract: every method is bounded (<=1 s), best-effort, and NEVER raises —
    failure is signaled by the default return ([] / False / None) plus one journal
    line inside the backend. The AudioDucker additionally wraps each call in its
    own swallow so a misbehaving backend cannot break engage/release.
    """

    def list_players(self) -> list[PlayerState]: ...
    def pause_player(self, name: str) -> bool: ...
    def resume_player(self, name: str) -> bool: ...
    def get_sink_volume_pct(self) -> float | None: ...
    def set_sink_volume_pct(self, pct: float) -> bool: ...


class AudioDucker:
    """Ducking orchestrator: bookkeeping + sovereignty rules over a DuckBackend.

    Holds the paused-player ledger and the volume snapshot; the tiers only provide
    the primitives. engage()/release() are idempotent, never raise, and no-op when
    duck_mode == "off" (or when never engaged). Thread-safe: one internal lock
    serializes engage/release (callers spawn threads; see the daemon wiring task).
    """

    def __init__(self, backend: DuckBackend, *, mode: str = "off", volume_pct: float = 15.0) -> None:
        self._backend = backend
        self._mode = mode
        self._volume_pct = float(volume_pct)
        self._lock = threading.Lock()
        self._engaged = False
        self._paused_players: list[str] = []      # names WE paused (all were Playing at engage)
        self._volume_snapshot: float | None = None  # pre-duck volume to restore (only set on a successful duck)

    @classmethod
    def from_config(cls, cfg, backend: DuckBackend) -> "AudioDucker":
        """Build from VoiceTypingConfig (reads cfg.audio.duck_mode / duck_volume_pct)."""
        audio = getattr(cfg, "audio", None)
        return cls(
            backend,
            mode=getattr(audio, "duck_mode", "off"),
            volume_pct=getattr(audio, "duck_volume_pct", 15),
        )

    @property
    def engaged(self) -> bool:
        with self._lock:
            return self._engaged

    # --- public API ---

    def engage(self) -> None:
        """Duck media for an arming. Idempotent; no-op when off or already engaged."""
        with self._lock:
            if self._engaged or self._mode == "off":
                return
            self._engaged = True  # set FIRST: a partially-failed engage must still unwind via release()
            if self._mode == "mpris":
                self._engage_mpris()
            else:  # "volume" (config guards the enum)
                self._engage_volume()

    def release(self) -> None:
        """Unduck on ANY disarm path. Idempotent; no-op without a prior engage."""
        with self._lock:
            if not self._engaged:
                return
            self._engaged = False
            if self._mode == "mpris":
                self._release_mpris()
            elif self._mode == "volume":
                self._release_volume()

    # --- tiers ---

    def _engage_mpris(self) -> None:
        players = self._call("list_players", self._backend.list_players, [])
        paused: list[str] = []
        for p in players:
            if not p.playing:
                continue  # rule (b): only `Playing` players enter the ledger
            if self._call(f"pause_player({p.name})", lambda n=p.name: self._backend.pause_player(n), False):
                paused.append(p.name)
        self._paused_players = paused
        if paused:
            logger.info("ducking: paused MPRIS player(s): %s", ", ".join(paused))

    def _release_mpris(self) -> None:
        ledger, self._paused_players = self._paused_players, []
        if not ledger:
            return
        fresh = {p.name: p for p in self._call("list_players", self._backend.list_players, [])}
        resumed: list[str] = []
        for name in ledger:
            state = fresh.get(name)
            if state is None:
                continue  # player gone — nothing to resume
            if state.playing:
                continue  # rule (c): the USER resumed it mid-dictation — never fight them
            if self._call(f"resume_player({name})", lambda n=name: self._backend.resume_player(n), False):
                resumed.append(name)
        if resumed:
            logger.info("ducking: resumed MPRIS player(s): %s", ", ".join(resumed))

    def _engage_volume(self) -> None:
        snapshot = self._call("get_sink_volume_pct", self._backend.get_sink_volume_pct, None)
        if snapshot is None:
            logger.warning("ducking: could not read sink volume; not ducking")
            return
        ok = self._call(
            "set_sink_volume_pct", lambda: self._backend.set_sink_volume_pct(self._volume_pct), False
        )
        if ok:
            self._volume_snapshot = snapshot  # stored ONLY on a successful set (release no-ops otherwise)
            logger.info("ducking: sink volume %.0f%% -> %.0f%%", snapshot, self._volume_pct)

    def _release_volume(self) -> None:
        snapshot, self._volume_snapshot = self._volume_snapshot, None
        if snapshot is None:
            return  # engage never actually ducked — nothing to restore
        current = self._call("get_sink_volume_pct", self._backend.get_sink_volume_pct, None)
        if current is None:
            logger.warning("ducking: could not re-read sink volume; leaving %.0f%%", self._volume_pct)
            return
        if abs(current - self._volume_pct) > _VOL_EPS:
            # compare-before-restore: the user changed the volume mid-dictation — THEIR value wins.
            logger.info("ducking: volume was changed mid-dictation (%.0f%%); keeping user value", current)
            return
        self._call("set_sink_volume_pct", lambda: self._backend.set_sink_volume_pct(snapshot), False)
        logger.info("ducking: restored sink volume %.0f%%", snapshot)

    # --- discipline ---

    def _call(self, description: str, fn, default):
        """Run one backend primitive; swallow ANY failure into a single warning line."""
        try:
            return fn()
        except Exception:
            logger.warning("ducking: %s failed; continuing", description)
            return default
```

### Unit tests (tests/test_ducking.py — 12 tests; `_FakeBackend` records every call)

`_FakeBackend` records calls (`paused`, `resumed`, `set_calls`, `call_log`), holds
mutable `players: list[PlayerState]` + `volume: float | None`, optional `fail: {"pause_player", ...}`
(raising) — the file's only fixture machinery. **CRITICAL: `pause_player`/`resume_player` MUST flip
the player's `playing` state in `self.players`** (a log-only fake leaves players `Playing`, so rule (c)
correctly skips every resume and the normal-path tests fail — QA-verified). `set_sink_volume_pct`
likewise stores the value. The ducker is exercised purely through the protocol.
1. `test_engage_mpris_pauses_only_playing_players` — players A(playing)/B(paused) → `paused == ["A"]`, ledger
   via behavior (release resumes A), B untouched.
2. `test_release_resumes_only_we_paused_and_still_paused` — engage pauses A,C; mutate: A→playing (user resumed),
   B→paused (user paused it); release → `resumed == ["C"]` only.
3. `test_release_player_gone_is_skipped` — ledger name absent from the fresh list → no resume call, no error.
4. `test_volume_engage_snapshots_and_ducks` — volume 50 → `set_calls == [15.0]`.
5. `test_volume_release_restores_when_untouched` — `set_calls == [15.0, 50.0]`.
6. `test_volume_release_skips_restore_when_user_changed` — user sets 80 mid-dictation → release makes NO set
   call (`set_calls == [15.0]`) + one INFO in caplog ("keeping user value").
7. `test_engage_idempotent_double_engage` — mpris: `paused == ["A"]` after two engages; volume: snapshot stays
   50 (release restores 50, proving 15 never overwrote it).
8. `test_release_without_engage_is_noop` — `call_log == []`.
9. `test_off_mode_never_calls_backend` — engage+release → `call_log == []`.
10. `test_backend_exception_swallowed_logged_once` — `fail={"pause_player"}` → engage returns normally; exactly
    ONE warning in caplog; ledger empty → release no-ops. (The raising pause leaves the player `Playing` — not
    ledgered — which is itself rule (a)/(b) correctness.)
11. `test_volume_engage_read_failure_leaves_no_snapshot` — `volume=None` → no set call; release no-ops.
12. `test_from_config_reads_audio_section` — `VoiceTypingConfig(audio=AudioConfig(duck_mode="volume",
    duck_volume_pct=25))` → `from_config` wires mode/volume (imports from `voice_typing.config`; the parallel
    P1.M2.T1.S1 contract guarantees `AudioConfig` exists — if it somehow has not landed, defer ONLY this test
    with a skipif on `hasattr(voice_typing.config, "AudioConfig")`, never delete it).

### Integration Points

```yaml
CONSUMED-BY (later D1 tasks — do not implement):
  - S2: "busctl MPRIS backend implementing list_players/pause_player/resume_player (subprocess, timeout=1.0)"
  - S3: "wpctl volume backend implementing get/set_sink_volume_pct (same discipline)"
  - S4: "arm-latency bound hardening over engage() (hung backend cannot delay arm)"
  - T3: "daemon wiring: AudioDucker.from_config(cfg, backend) at boot; engage() spawned at _arm() toast site
         (daemon.py:1415); release() spawned at _disarm() (:1454) + request_shutdown() (:2177); ducked state flag"
CONFIG:
  - consumes: "cfg.audio.duck_mode ('off'|'mpris'|'volume') + cfg.audio.duck_volume_pct (P1.M2.T1.S1 contract)"
STATE:
  - exposes: "engaged property (read under lock) — T3/S4/status consume"
```

## Validation Loop

### Level 1–2 (the gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_ducking.py -v                 # 12 passed
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # no NEW failures
# Optional: /home/dustin/.local/bin/ruff check voice_typing/audio_ducking.py tests/test_ducking.py
```

### Level 3 (protocol conformance smoke)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python - <<'PY'
from voice_typing.audio_ducking import AudioDucker, DuckBackend, PlayerState
class B:  # minimal in-process backend (NOT a tier — proves protocol + sovereignty)
    def __init__(self): self.players=[PlayerState("mpd", True), PlayerState("vlc", False)]; self.vol=50.0; self.log=[]
    def list_players(self): self.log.append("list"); return list(self.players)
    def pause_player(self, n): self.log.append(f"pause:{n}"); return True
    def resume_player(self, n): self.log.append(f"resume:{n}"); return True
    def get_sink_volume_pct(self): self.log.append("get"); return self.vol
    def set_sink_volume_pct(self, p): self.log.append(f"set:{p:.0f}"); self.vol=p; return True
b = B(); d = AudioDucker(b, mode="mpris")
d.engage(); d.engage()                      # idempotent
assert b.log.count("pause:mpd") == 1, b.log # single pause, only the playing player
b.players = [PlayerState("mpd", True)]      # user resumed mpd mid-dictation
d.release(); assert "resume:mpd" not in b.log  # rule (c): never fight the user
assert d.engaged is False
v = AudioDucker(B(), mode="volume", volume_pct=15); v.engage(); v.release()
print("OK: protocol + sovereignty smoke passed")
PY
```

### Level 4 (scope guard)

```bash
git status --short   # == voice_typing/audio_ducking.py + tests/test_ducking.py (both new) — nothing else
```

## Final Validation Checklist

- [ ] 12 tests pass; fast suite shows no new failures (both under `timeout`).
- [ ] Level-3 smoke prints OK (idempotence + rule (c) + volume round-trip).
- [ ] Module docstring states tiers + sovereignty rules (Mode A); stdlib-only module top.
- [ ] `from_config` consumes `cfg.audio.*`; plain constructor used by tests.
- [ ] Only the 2 new files in `git status --short`.

## Anti-Patterns to Avoid

- ❌ Don't wire the daemon / add the ducked flag / flip the default — T3/T4 (Critical #6).
- ❌ Don't write subprocess calls or import subprocess — the tiers (S2/S3) own them; S1 is stdlib-only.
- ❌ Don't fill the ledger with non-Playing players or failed pauses — the ledger IS rules (a)+(b) (Critical #2).
- ❌ Don't store the volume snapshot when the set failed, and don't restore without the compare (Criticals #1/#3).
- ❌ Don't let anything raise out of engage/release, and don't log more than one line per failure (Critical #4).
- ❌ Don't add a second lock or check-then-act outside the single `threading.Lock` (Critical #5).
- ❌ Don't run un-timed commands (Critical #7 / AGENTS.md).

# PRP — P1.M2.T2.S2: MPRIS tier — tracked pause set via busctl

## Goal

**Feature Goal**: Implement the **MPRIS ducking backend** for PRD §4.2quinquies (D1): `voice_typing/ducking_mpris.py` with `MprisBusctlBackend`, the concrete subprocess tier that realizes the three MPRIS primitives of S1's `DuckBackend` protocol (`list_players` / `pause_player` / `resume_player`) over **`busctl --user` argv** (NO D-Bus bindings exist in `.venv` — probed; NO playerctl — `--all-players pause` + bare `play` are RESEARCH-FORBIDDEN as unsafe for exact restore). The tracked-pause-set BOOKKEEPING stays in S1's `AudioDucker` (landed, verified); this backend is **stateless primitives only**: bounded (`timeout=1.0` per call), best-effort, never raises, one journal line per failure. Safety gates baked in: `pause_player` respects `CanPause`; `resume_player` issues `Play()` **only when PlaybackStatus is exactly `"Paused"`** — never restarting a `Stopped` player (the user-sovereignty hazard).

**Deliverable** (2 NEW files; no edits to existing sources — S1 owns `audio_ducking.py` and is landing in parallel):
1. `voice_typing/ducking_mpris.py` — module docstring (tier design + why busctl + the sovereignty gates), `MprisBusctlBackend`, the `_run(argv) -> str | None` bounded-subprocess helper + three regex parsers. The ONLY third `import subprocess` site (seams §1e).
2. `tests/test_ducking_mpris.py` — 14 fake-runner tests (monkeypatched `subprocess.run`, zero real busctl/audio), including the **PRD case-(a) pin at the tier level** through S1's real `AudioDucker`.

**Success Definition**:
- (a) `list_players()` returns `PlayerState`s for exactly the `org.mpris.MediaPlayer2.*` names (fresh `ListNames`), `playing=(PlaybackStatus=="Playing")`; names whose status read fails are omitted, never crash.
- (b) `pause_player(name)` reads `CanPause` first; `true` → the exact `Pause` argv → `True`; `false`/unreadable → NO Pause call, `False` (the ducker therefore never ledgers it).
- (c) `resume_player(name)` re-reads `PlaybackStatus`; `Play()` fires ONLY on exactly `"Paused"`; `"Stopped"` (restart hazard) and `"Playing"` (already resumed) → no call, `False`.
- (d) Every busctl call runs under `timeout=1.0`, `check=False`, `stderr=DEVNULL`; `TimeoutExpired`/`OSError`/`SubprocessError` → exactly ONE WARNING, safe default, nothing propagates; per-player `rc!=0` → one DEBUG (normal player churn).
- (e) The volume methods are documented protocol-completeness stubs (`None`/`False`, zero busctl calls) — S3's wpctl backend owns the real ones; `mode="mpris"` never calls them.
- (f) `timeout 300 .venv/bin/python -m pytest tests/test_ducking_mpris.py -q` → **14 passed**; `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → **no new failures** beyond the recorded G1 classification (`tests/G1_BASELINE.md`); `git status --short` == the 2 new files only.

## User Persona

Not a user surface yet (`duck_mode` ships `"off"`; T4 flips the default to `"mpris"` with evidence). DOCS: **Mode A** — the module docstring carries the design. Beneficiaries: **T3** (wires `AudioDucker.from_config(cfg, MprisBusctlBackend())` into the daemon lifecycle), **T4** (the default-flip evidence runs this tier), and the end user once enabled: music pauses within ~1 s of arming and resumes at stop, and a player the user started/resumed/stopped mid-dictation is never fought.

## Why

- **PRD §4.2quinquies tier 1 is the primary ducking mechanism.** Media bleed is a leading "wrong words that change meaning" source; MPRIS pause is the exact fix for the dominant case (media players). The PRD's core demand — "put it back EXACTLY as it found it" — is delivered by S1's ledger + this tier's honest primitives.
- **The unsafe shortcuts are banned by research.** `playerctl --all-players pause` acts on the player set present at invocation (a late player is missed); bare `playerctl play` targets the most-recently-active player only. Exact restore requires the tracked-pause-set: enumerate at duck time, pause only `Playing` (+`CanPause`) players, and at release intersect the stored set with a fresh `ListNames` + still-`Paused` check (external_tech_notes §3.4-§3.5). The backend provides exactly the primitives that design needs.
- **No new dependencies.** `dbus`/`pydbus`/`jeepney` are absent from `.venv` (probed); `busctl` at `/usr/bin/busctl` is present and its `call`/`get-property` verbs are standard. Subprocess argv keeps the venv frozen and the module testable with a fake runner.
- **Parallel-safe.** S1's `audio_ducking.py` is stdlib-only and S1's scope guard pins its `git status` to its 2 files — a separate `ducking_mpris.py` makes S1/S2 disjoint while S1's tests still land.

## What

A stateless `MprisBusctlBackend` implementing the MPRIS subset of S1's `DuckBackend` protocol over five exact busctl argv forms (`ListNames`, `PlaybackStatus`, `CanPause`, `Pause`, `Play` — from external_tech_notes §3.3), one bounded `_run` helper (`timeout=1.0`, swallow → one line), three regex parsers, and documented volume-method stubs for protocol completeness. Plus 14 fake-runner unit tests pinning the argv forms, the parsing, both sovereignty gates, the timeout/missing-binary discipline, and PRD test case (a) at the tier level through the real `AudioDucker`.

### Success Criteria

- [ ] `voice_typing/ducking_mpris.py` exists; imports = `logging`, `subprocess`, `re`, `typing` (+ S1's `PlayerState` for typing only).
- [ ] The 5 exact argv forms from external_tech_notes §3.3 are reproduced verbatim in the code (tests pin them).
- [ ] `list_players` / `pause_player` / `resume_player` behave per Success Definition (a)-(c).
- [ ] Every call bounded ≤1 s; failures journal exactly one line (WARNING hard / DEBUG per-player-churn); nothing raises.
- [ ] Volume methods stubbed + documented (zero busctl calls).
- [ ] 14 tests pass; fast suite shows no new failures; only the 2 new files in `git status --short`.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo gets: the exact busctl argv forms (external_tech_notes §3.3, quoted in research §1.2), the exact output shapes + robust regexes for each (research §3 table), the verified S1 protocol surface it implements (file:line, verified at HEAD), the two safety gates with their rationale (`CanPause`; `Play()`-only-on-`Paused` vs the Stopped-restart hazard — tech-notes §3.1), the subprocess discipline precedent (`feedback.py:247-261` + the NEW `timeout=1.0` pattern blessed by seams §1e), the absolute-path convention (`typing_backends.py` `_TMUX`), the fake-runner test precedent (`test_typing_backends.py` `_Recorder` monkeypatches `subprocess.run`), and a verbatim module skeleton in the Blueprint. No daemon/config knowledge needed — T3 wires it later.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/P1M2T2S2/research/mpris_busctl_tier.md
  why: "§1 contract inputs (S1's landed protocol w/ file:line; the 5 argv forms; env facts; the
        subprocess precedent). §2 the design decisions (busctl-only; new module; the 2 safety gates;
        WARNING-vs-DEBUG discipline; volume stubs; latency shape). §3 the output-parsing table
        (exact shapes + regexes). §4 the 14-test design incl. the case-(a) tier pin. §5 scope+gates."
  critical: "§2.3 (the resume-only-if-Paused gate) and §2.4 (one-line discipline) are load-bearing."

- docfile: plan/008_a47116bb2b79/architecture/external_tech_notes.md
  why: "§3.3 the exact busctl argv forms (the contract's prescribed forms). §3.1 PlaybackStatus
        semantics + 'Play() on a stopped player restarts'. §3.4 the playerctl pitfalls (why FORBIDDEN).
        §3.5 the tracked-pause-set design this tier serves."
  critical: "Do NOT substitute playerctl forms. Do NOT issue Play() without the Paused check."

- docfile: plan/008_a47116bb2b79/architecture/d1_ducking_seams.md
  why: "§1e: the subprocess-with-timeout pattern to copy (feedback.py:247-261 swallow + NEW
        timeout=1.0; the third subprocess import is local to this module). §5: the fake-backend test
        seam. §6: /usr/bin/busctl verified; NO dbus/gi in .venv."
  critical: "Do NOT wire the daemon (T3), do NOT add the ducked flag (T3.S2), do NOT touch volume
             (S3's wpctl)."

- file: voice_typing/audio_ducking.py
  why: "S1's LANDED contract this tier implements: PlayerState (L36), DuckBackend Protocol (L44-57),
        AudioDucker's engage/release flow (L95-143) showing EXACTLY which primitives are called and
        when (release re-lists + skips playing players — L135-142). Stdlib-only top — the reason this
        tier is a separate module."
  critical: "READ-ONLY (S1 owns it; parallel). Import PlayerState for typing; never edit this file.
             The backend keeps NO ledger — sovereignty lives in the ducker."

- file: voice_typing/feedback.py
  why: ":247-261 _notify — the swallow-discipline shape _run() mirrors (check=False, DEVNULL, bounded
        try/except, one log line, never re-raise)."
  critical: "Mirror the discipline; ADD timeout=1.0 (new pattern) and stdout=PIPE (we parse stdout)."

- file: tests/test_typing_backends.py
  why: "The fake-runner precedent: _Recorder monkeypatches subprocess.run (captures argv+kwargs,
        returns canned results, never touches the OS) — tests/test_ducking_mpris.py mirrors it."
  critical: "Same mechanic: monkeypatch ducking_mpris.subprocess.run. Assertions pin EXACT argv."

- file: PRD.md   # §4.2quinquies
  why: "Tier 1 spec: enumerate players, pause Playing ones at arm, resume at stop; the (a)(b)(c)
        sovereignty rules; the failure discipline (timeout ≤1 s, one line, never a gate); test case
        (a) 'a player the user paused mid-dictation stays paused'."
  critical: "Rules (a)+(b) are enforced by S1's ducker; rule (c)'s Stopped-vs-Paused hazard is closed
             HERE by the resume gate."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── audio_ducking.py     # S1, LANDED, READ-ONLY (PlayerState + DuckBackend + AudioDucker; stdlib-only).
├── ducking_mpris.py     # CREATE (MprisBusctlBackend + _run + parsers; the subprocess import lives here).
└── ...                  # daemon.py (T3), config.py (landed AudioConfig), feedback.py — UNCHANGED.
tests/
└── test_ducking_mpris.py  # CREATE (14 fake-runner tests; S1 owns tests/test_ducking.py separately).
```

### Desired Codebase tree with responsibility

```bash
voice_typing/ducking_mpris.py    # MPRIS tier: stateless busctl primitives for DuckBackend.
tests/test_ducking_mpris.py      # argv/parse/gate/discipline/case-(a) tests over a fake runner.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — busctl ONLY. playerctl --all-players pause + bare play are RESEARCH-FORBIDDEN
#   (external_tech_notes §3.4: --all-players misses late players; bare play targets most-recent only).
#   Even "individual ops" via playerctl add nothing busctl doesn't — use the 5 argv forms verbatim.
# CRITICAL #2 — resume_player MUST re-read PlaybackStatus and issue Play() ONLY on exactly "Paused".
#   Play() on a Stopped player RESTARTS it (§3.1) = fighting the user; "Playing" = the user already
#   resumed = double-play race. The ducker's rule (c) checks not-playing (Paused OR Stopped) — this
#   backend gate is what closes the Stopped hazard.
# CRITICAL #3 — pause_player MUST read CanPause first (contract: "respect CanPause"). false/unreadable
#   → return False with NO Pause call → the ducker never ledgers an unpausable player.
# CRITICAL #4 — NEVER RAISE. _run swallows TimeoutExpired/OSError/SubprocessError → ONE WARNING, safe
#   default (None → caller maps to [] / False / omit-player). rc!=0 → ONE DEBUG (player churn is
#   normal; per-player WARNINGs would spam every engage). S1's ducker _call is the second net.
# CRITICAL #5 — timeout=1.0 is a NEW pattern in this repo (zero existing subprocess.run timeouts).
#   check=False + stdout=PIPE + stderr=DEVNULL + text=True. Absolute path /usr/bin/busctl
#   (typing_backends _TMUX convention — zsh aliases).
# CRITICAL #6 — PARSE WITH REGEX over the whole stdout (research §3): ListNames prints the array
#   count + quoted names ("as 42 \"org.mpris...\""); get-property prints "s \"Playing\"" / "b true".
#   Token-splitting breaks on the count token / wrapping; the quoted-pattern regexes are stable.
# CRITICAL #7 — NO state in the backend (no ledger, no cache, no remembered names). All bookkeeping
#   is S1's AudioDucker; duplicating it here would fork the sovereignty rules.
# CRITICAL #8 — SCOPE: no daemon wiring (T3), no ducked flag (T3.S2), no wpctl/volume (S3), no config
#   edits, no edits to audio_ducking.py, no default flip (T4).
# CRITICAL #9 — AGENTS.md: every pytest under `timeout N` (inner) + bash-tool timeout (outer); full
#   tool paths (.venv/bin/python -m pytest). Never run the daemon in the foreground.
```

## Implementation Blueprint

### Data models and structure

No new data types: `PlayerState` is imported from S1's `audio_ducking` (typing only — the backend
constructs it). The backend itself holds ZERO state (no `__init__` beyond nothing / a docstring).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/ducking_mpris.py
  - MODULE DOCSTRING (Mode A): tier-1 design; why busctl (no venv D-Bus libs; playerctl unsafe for
    exact restore — the two pitfalls); the two safety gates (CanPause; Play-only-on-Paused); the
    failure discipline (≤1 s, one line, never a gate); "stateless by design — the tracked-pause-set
    ledger lives in AudioDucker (audio_ducking.py)"; the latency note (per-player calls sequential,
    each ≤1 s; the daemon spawns engage so arm latency is unaffected — T3/S4 own that bound).
  - _BUSCTL = "/usr/bin/busctl"; _TIMEOUT_S = 1.0.
  - _run(argv) -> str | None per Critical #4/#5. _parse_names/_parse_status/_parse_bool per §3 regexes.
  - MprisBusctlBackend per the verbatim block below (5 methods: 3 real, 2 documented stubs).
Task 2: CREATE tests/test_ducking_mpris.py (14 tests per research §4; _Runner fake monkeypatching
  ducking_mpris.subprocess.run; repo docstring/banner style; case-(a) pin imports the real AudioDucker).
Task 3: VALIDATE (Level 1-4 below).
```

### Verbatim module (ducking_mpris.py — the functional core)

```python
"""voice_typing.ducking_mpris — MPRIS ducking tier via busctl (PRD §4.2quinquies, D1 / P1.M2.T2.S2).

Tier 1 of media ducking: pause every MPRIS player that is Playing when the mic arms, resume them at
disarm. Implemented as STATELESS primitives for the DuckBackend protocol (audio_ducking.py) — the
tracked-pause-set LEDGER and the sovereignty rules live in AudioDucker, never here.

WHY BUSCTL (external_tech_notes §3): no D-Bus bindings exist in .venv (dbus/pydbus/jeepney absent —
probed), and playerctl is UNSAFE for exact restore: `--all-players pause` acts on the player set
present at invocation (a player starting later is missed) and a bare `play` targets the
most-recently-active player only. Exact restore needs the tracked set + fresh re-enumeration +
still-Paused checks — exactly the primitives this backend provides.

SAFETY GATES (user sovereignty, belt-and-suspenders on AudioDucker's rules):
  - pause_player reads CanPause first; false/unreadable → NO Pause call → never ledgered.
  - resume_player re-reads PlaybackStatus and issues Play() ONLY on exactly "Paused". Play() on a
    Stopped player RESTARTS it (MPRIS spec) and "Playing" means the user already resumed — in both
    cases we must not fight the user, so no call is made.

FAILURE DISCIPLINE: every busctl call is subprocess, timeout=1.0, check=False, stderr=DEVNULL.
TimeoutExpired/OSError/SubprocessError → ONE WARNING + safe default; a per-player nonzero rc → ONE
DEBUG (players appear/vanish constantly — a vanished name is normal churn, not a warning). Nothing
ever raises out of a protocol method. Per-player calls are sequential; engage latency is owned by
the daemon wiring (spawned, never under the arm) — see P1.M2.T3/S4.
"""
from __future__ import annotations

import logging
import re
import subprocess

from voice_typing.audio_ducking import PlayerState

logger = logging.getLogger(__name__)

_BUSCTL = "/usr/bin/busctl"  # absolute path (zsh aliases; typing_backends._TMUX convention)
_TIMEOUT_S = 1.0             # PRD §4.2quinquies: every audio call bounded <=1 s

_MPRIS_PREFIX = "org.mpris.MediaPlayer2."
_PLAYER_PATH = "/org/mpris/MediaPlayer2"
_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
_RE_MPRIS_NAME = re.compile(r'"(org\.mpris\.MediaPlayer2\.[A-Za-z0-9_.]+)"')
_RE_STATUS = re.compile(r'"(Playing|Paused|Stopped)"')
_RE_BOOL = re.compile(r"\b(true|false)\b")


def _run(argv: list[str]) -> str | None:
    """One bounded busctl call. Never raises; None = failed (one journal line)."""
    try:
        cp = subprocess.run(
            [_BUSCTL, *argv],
            timeout=_TIMEOUT_S,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ducking-mpris: busctl %s timed out (>%.1fs); skipping", argv[0:2], _TIMEOUT_S)
        return None
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ducking-mpris: busctl %s failed (%s); skipping", argv[0:2], exc)
        return None
    if cp.returncode != 0:
        # Per-player nonzero is normal churn (name vanished between calls) — DEBUG, not WARNING.
        logger.debug("ducking-mpris: busctl %s rc=%d (normal churn?); skipping", argv[0:2], cp.returncode)
        return None
    return cp.stdout


def _get_property(name: str, prop: str) -> str | None:
    out = _run(["--user", "get-property", name, _PLAYER_PATH, _PLAYER_IFACE, prop])
    return out  # None = unreadable


class MprisBusctlBackend:
    """DuckBackend MPRIS tier over busctl (stateless; the ledger lives in AudioDucker).

    Protocol completeness: the two volume methods are documented stubs returning the failure
    defaults — S3's wpctl backend owns the real ones, and duck_mode="mpris" never calls them.
    """

    # --- MPRIS primitives ---

    def list_players(self) -> list[PlayerState]:
        out = _run(
            ["--user", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
             "org.freedesktop.DBus", "ListNames"]
        )
        if out is None:
            logger.warning("ducking-mpris: ListNames failed; treating as no players")
            return []
        players: list[PlayerState] = []
        for m in _RE_MPRIS_NAME.finditer(out):
            name = m.group(1)
            status_out = _get_property(name, "PlaybackStatus")
            if status_out is None:
                continue  # unreadable player: omit (we cannot pause what we cannot read)
            sm = _RE_STATUS.search(status_out)
            players.append(PlayerState(name=name, playing=bool(sm and sm.group(1) == "Playing")))
        return players

    def pause_player(self, name: str) -> bool:
        can = _get_property(name, "CanPause")
        cm = _RE_BOOL.search(can) if can else None
        if not can or not cm or cm.group(1) != "true":
            return False  # not pausable (or unreadable) -> the ducker never ledgers it
        out = _run(["--user", "call", name, _PLAYER_PATH, _PLAYER_IFACE, "Pause"])
        return out is not None

    def resume_player(self, name: str) -> bool:
        status = _get_property(name, "PlaybackStatus")
        sm = _RE_STATUS.search(status) if status else None
        if not sm or sm.group(1) != "Paused":
            return False  # only exactly-Paused: Play() would RESTART a Stopped player; Playing = user resumed
        out = _run(["--user", "call", name, _PLAYER_PATH, _PLAYER_IFACE, "Play"])
        return out is not None

    # --- volume tier stubs (S3: ducking_wpctl.py owns the real ones) ---

    def get_sink_volume_pct(self) -> float | None:
        return None  # not this tier (wpctl); duck_mode="mpris" never calls this

    def set_sink_volume_pct(self, pct: float) -> bool:
        return False  # not this tier (wpctl); duck_mode="mpris" never calls this
```

### Implementation Patterns & Key Details

```python
# (1) The five exact argv forms (external_tech_notes §3.3 — tests pin them byte-for-byte):
#   ["--user","call","org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","ListNames"]
#   ["--user","get-property",name,"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2.Player","PlaybackStatus"]
#   ["--user","get-property",name,"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2.Player","CanPause"]
#   ["--user","call",name,"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2.Player","Pause"]
#   ["--user","call",name,"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2.Player","Play"]

# (2) The _Runner test fake (mirrors test_typing_backends._Recorder's monkeypatch mechanic):
class _Runner:                      # installed via monkeypatch.setattr(ducking_mpris.subprocess, "run", r)
    def __init__(self): self.calls = []; self.out = {}; self.raise_on = {}
    def __call__(self, argv, **kw):        # pattern-match argv tail -> canned stdout / rc / raise
        ...

# (3) Case-(a) pin runs the REAL AudioDucker over MprisBusctlBackend + the fake runner — proving the
#     tier + core compose: engage pauses only Playing; release resumes only ledger∧present∧paused.
```

### Integration Points

```yaml
CONSUMED-BY (later D1 tasks — do not implement here):
  - T3: "AudioDucker.from_config(cfg, MprisBusctlBackend()) when cfg.audio.duck_mode == 'mpris';
         engage/release spawned at the arm/disarm seams; ducked state flag"
  - T4: "default flip to 'mpris' runs THIS tier for the acceptance evidence"
  - S3: "lands ducking_wpctl.py for get/set_sink_volume_pct the same way (parallel-safe)"
PROTOCOL:
  - implements: "the 3 MPRIS methods of voice_typing.audio_ducking.DuckBackend (verified at HEAD)"
  - invariant: "stateless — no ledger, no cache; all sovereignty bookkeeping is AudioDucker's"
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -c "from voice_typing.ducking_mpris import MprisBusctlBackend; print('import OK')"
# Optional: /home/dustin/.local/bin/ruff check voice_typing/ducking_mpris.py tests/test_ducking_mpris.py || true
```

### Level 2: Unit Tests (THE gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_ducking_mpris.py -v          # 14 passed
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: no NEW failures beyond the recorded G1 classification (tests/G1_BASELINE.md).
```

### Level 3: Live read-only smoke (NEVER Pause/Play the user's real players)

```bash
cd /home/dustin/projects/voice-typing
timeout 30 .venv/bin/python - <<'PY'
from voice_typing.ducking_mpris import MprisBusctlBackend
players = MprisBusctlBackend().list_players()
print("live MPRIS players:", [(p.name, p.playing) for p in players])
# Acceptable outcomes: a list of players (each with a sane playing flag) OR [] on a headless
# session — BOTH pass the smoke (the [] path exercises the swallow). NO pause/resume calls here.
PY
```

### Level 4: Scope guard

```bash
git status --short   # == voice_typing/ducking_mpris.py + tests/test_ducking_mpris.py (both new)
```

## Final Validation Checklist

### Technical Validation
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_ducking_mpris.py -q` → 14 passed.
- [ ] Fast suite → no new failures vs `tests/G1_BASELINE.md` (both runs under `timeout`).
- [ ] Level-3 read-only smoke prints the player list (or `[]`) without touching playback.

### Feature Validation
- [ ] The 5 exact argv forms pinned byte-for-byte by tests (external_tech_notes §3.3).
- [ ] `pause_player` respects `CanPause`; `resume_player` fires `Play()` ONLY on exactly `"Paused"` (Stopped/Playing → no call).
- [ ] Every call ≤1 s; timeout/OSError → exactly ONE WARNING; per-player rc!=0 → one DEBUG; nothing raises.
- [ ] PRD case (a) pinned at the tier level through the real `AudioDucker` (test 14).
- [ ] Volume methods stubbed with zero busctl calls.

### Code Quality Validation
- [ ] Backend is stateless (no ledger/cache) — sovereignty stays in `audio_ducking.AudioDucker`.
- [ ] Module docstring covers: busctl rationale, both safety gates, failure discipline, latency note (Mode A).
- [ ] Regex parsing per research §3 (no token-splitting).
- [ ] Only the 2 new files in `git status --short`.

### Documentation & Deployment
- [ ] No config/daemon/feedback/systemd changes (T3/S3/S4/T4 own those); no new env vars.

---

## Anti-Patterns to Avoid

- ❌ Don't use playerctl anywhere — `--all-players pause` + bare `play` are research-forbidden; busctl only (Critical #1).
- ❌ Don't issue `Play()` without re-reading PlaybackStatus — a Stopped player would RESTART (Critical #2).
- ❌ Don't skip the `CanPause` read — an unpausable player must never receive Pause (Critical #3).
- ❌ Don't raise, don't log tracebacks, don't WARN per-player on nonzero rc (churn is normal — Critical #4).
- ❌ Don't add a ledger/cache to the backend — the tracked-pause-set bookkeeping is S1's AudioDucker (Critical #7).
- ❌ Don't edit `audio_ducking.py` (S1's, parallel), daemon.py (T3), config.py, or implement volume ops (S3) (Critical #8).
- ❌ Don't parse busctl output by token-splitting — use the quoted-pattern regexes (Critical #6).
- ❌ Don't run un-timed commands; never Pause/Play real players in validation (Critical #9 / Level 3).

---

## Confidence Score

**9/10** — the S1 protocol it implements is LANDED and verified at HEAD (file:line pinned); the argv forms, output shapes, and parsing rules come from verified research (external_tech_notes §3 + the live host probe); the module skeleton is given verbatim; and the 14 tests (incl. the case-(a) tier pin over the real ducker) are enumerated with exact assertions. Residual risk: minor busctl output-format drift on exotic players — absorbed by the regex-over-stdout parsers and the never-raise defaults.

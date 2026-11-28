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

_BUSCTL = "/usr/bin/busctl"  # absolute path, independent of the service's PATH
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

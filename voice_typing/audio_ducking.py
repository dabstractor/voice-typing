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

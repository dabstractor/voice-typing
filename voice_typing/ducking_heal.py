"""voice_typing.ducking_heal — crash-safety heal for ducked media (PRD §4.2quinquies, P1.M2.T3.S2).

TWO consumers share this module:
  - the daemon's BOOT self-heal: VoiceTypingDaemon.__init__ reads the persisted `ducked` flag
    BEFORE its first Feedback write (the boot set_models_loaded write resets `ducked` to the
    seeded False and would clobber it) and, when set, spawns a one-shot `vt-duck-heal` thread
    running heal(cfg, force=True);
  - systemd's ExecStopPost: `python -m voice_typing.ducking_heal` runs main() on EVERY stop
    (clean exit, failure, AND SIGKILL/timeout — standard ExecStopPost semantics).

Post-crash the ducker's in-memory restore bookkeeping (MPRIS pause-ledger + volume snapshot)
is GONE — ordinary AudioDucker.release() is a no-op (audio_ducking.py; ledger/snapshot die with
the process). The heal is therefore heuristic and mode-agnostic (the crashed session's tier is
unknowable):
  1. GATE on the persisted flag (cfg.feedback.resolved_state_file() — the SINGLE path source of
     truth): `ducked` not exactly True → return with ZERO backend calls. This is also the
     clean-stop case: quit already released + flushed in-process, the flag is False, so
     ExecStopPost no-ops on every clean stop and never fights the daemon's own restore.
  2. MPRIS heal: resume EVERY currently-Paused player. False positives (a player the user
     paused themselves) are re-pausable; false negatives leave music stuck — resuming is the
     least-bad direction. One INFO line per resume.
  3. Volume heal — WARN-ONLY (documented decision): if the sink sits at duck_volume_pct, log
     ONE warning; NEVER set a guessed restore. Post-crash the pre-duck volume is unknowable;
     a guessed restore (e.g. 100%) can blast audio — "a restore that clobbers is worse than
     not ducking" (PRD §4.2quinquies). A journal warning + manual bump is safer.

DISCIPLINE: every backend call is bounded ≤1 s (MprisBusctlBackend's subprocess budget) and
swallow-to-one-warning (clones AudioDucker._call); this module ALWAYS exits 0 and never raises
into its callers — an ExecStopPost failure is journal noise only, and the daemon's boot thread
must never crash the daemon. Ducking is an enhancement, never a gate.

STDLIB-LIGHT (json/logging + config + ducking_mpris/audio_ducking): runs via
`.venv/bin/python -m voice_typing.ducking_heal` WITHOUT launch_daemon.sh's LD_LIBRARY_PATH —
NEVER import daemon.py / recorder_host / anything CUDA-adjacent here.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

from voice_typing.audio_ducking import _VOL_EPS
from voice_typing.config import VoiceTypingConfig
from voice_typing.ducking_mpris import MprisBusctlBackend

logger = logging.getLogger(__name__)


def read_ducked_flag(cfg: VoiceTypingConfig) -> bool:
    """Best-effort read of the persisted `ducked` flag; True ONLY when exactly JSON true.

    Missing file / unreadable JSON / unresolvable path (state_file empty AND XDG_RUNTIME_DIR
    unset — i.e. outside a real session) → False. NEVER raises: a boot read or an ExecStopPost
    run must not die on a state-file problem (treat "can't read" as "not flagged").
    """
    try:
        path = cfg.feedback.resolved_state_file()
    except Exception:  # RuntimeError per FeedbackConfig.resolved_state_file; keep it total
        logger.debug(
            "ducking-heal: state path unresolved (XDG_RUNTIME_DIR unset?); treating as unflagged"
        )
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        logger.warning("ducking-heal: unreadable state file %s; treating as unflagged", path)
        return False
    return state.get("ducked") is True


def _call(description: str, fn, default):
    """One backend call, swallow-to-one-warning (clones AudioDucker._call's discipline)."""
    try:
        return fn()
    except Exception:  # pylint: disable=broad-except — ducking is never a gate
        logger.warning("ducking-heal: %s failed; continuing", description)
        return default


def heal(cfg: VoiceTypingConfig, *, force: bool = False, backend: Any = None) -> None:
    """Best-effort post-crash media restore. Never raises; bounded; always safe to re-run.

    force=True skips the flag re-read: the daemon boot ALREADY read the flag before its first
    Feedback write, and that write resets `ducked` to the seeded False — a re-read inside the
    heal thread could race the clobber and silently no-op (ExecStopPost's main() keeps the
    default fresh-read gate: the flag on disk is the crash signal there). backend= injects a
    test double (same seam pattern as the daemon's ducker=/key_listener=); default
    MprisBusctlBackend.
    """
    if not force and not read_ducked_flag(cfg):
        return  # clean stop / no crash: ZERO backend calls (exit 0, quiet)
    if backend is None:
        backend = MprisBusctlBackend()
    players = _call("list_players", backend.list_players, [])
    for p in players:
        if p.playing:
            continue  # already playing — never fight the user
        if _call(f"resume_player({p.name})", lambda n=p.name: backend.resume_player(n), False):
            logger.info("ducking-heal: resumed %s", p.name)
    cur = _call("get_sink_volume_pct", backend.get_sink_volume_pct, None)
    if cur is not None and abs(cur - cfg.audio.duck_volume_pct) <= _VOL_EPS:
        # WARN-ONLY (documented decision): post-crash the pre-duck volume is unknowable; a
        # guessed restore could blast audio — worse than a manual bump ("a restore that
        # clobbers is worse than not ducking", PRD §4.2quinquies). Never call set_sink_volume_pct.
        logger.warning(
            "ducking-heal: sink left at duck level %.0f%% by a crash; "
            "restore it manually if unintended",
            cur,
        )


def main() -> int:
    """`python -m voice_typing.ducking_heal` (ExecStopPost entry): heal, then ALWAYS exit 0."""
    try:
        cfg = VoiceTypingConfig.load()
    except Exception:  # pylint: disable=broad-except — never a gate (journal noise only)
        logger.warning("ducking-heal: config load failed; nothing to heal")
        return 0
    try:
        heal(cfg)
    except Exception:  # belt-and-suspenders: heal() is swallow-all by construction
        logger.warning("ducking-heal: heal raised (ignored)")
    return 0


if __name__ == "__main__":
    # ExecStopPost runs us WITHOUT the daemon's logging setup: basicConfig so the INFO resume
    # lines + the warn-only volume warning reach stderr → journald. Quiet (exit 0) when unflagged.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())

"""voice_typing.ducking_volume — sink-volume ducking tier via wpctl (PRD §4.2quinquies, D1 / P1.M2.T2.S3).

Tier 2 of media ducking — the fallback for audio with no MPRIS player (browser games,
notification-heavy apps): at arm, read + store the default sink's volume and duck it to
duck_volume_pct; at disarm, restore it ONLY if it still equals what we last set. The two
DuckBackend primitives below are deliberately THIN: the snapshot ledger, the
compare-before-restore rule (±0.5 pct) and all user-sovereignty decisions live in
AudioDucker (audio_ducking.py, P1.M2.T2.S1) — never here.

WHY CONCRETE-NODE PINNING (external_tech_notes §4.4; live-verified): wpctl resolves
`@DEFAULT_AUDIO_SINK@` PER INVOCATION, so a restore-by-selector would hit whatever sink
the user switched TO mid-dictation while the ducked one stayed at 15%. So the backend
pins the concrete node id (the `*` line of the Sinks block of `wpctl status`): the
engage-get pins + reads it, the engage-set ducks it by id, the release-get re-reads THE
PINNED node for the ducker's compare, and the release-set restores by id and clears the
pin. A pinned node that has gone away prints "Node 'N' not found" WITH rc=0 (the rc
LIES — live-verified), so failure detection is the output-grammar parse
(`^Volume:\\s*<float>`), never the return code; a parse miss on a pinned node unpins
gracefully so the next engage re-resolves the (possibly new) default.

THE PIN IS SEQUENCE-DRIVEN, NOT VALUE-DRIVEN: the frozen protocol has no engage/release
signal, so the tier infers them from the ducker's observable call grammar per session —
`get, set(D) [, get, set(V0)]`. The fresh get pins; successful sets ALTERNATE: the
first marks _ducked (the engage duck), the second is the release restore and clears the
pin. A restore skipped because the user changed the volume leaves the flag set; the
call stream is then indistinguishable from a fresh session, so sets keep alternating —
the next session's engage-get reads the pinned (still-ducked) node, and its completed
release still restores the snapshot by id, re-syncing the state. Driving the state by
comparing pct VALUES would break when D == V0 (sink already sitting at the duck level).

MUTE DECISION (structural — do not "complete" it): this tier NEVER issues `set-mute`.
`wpctl set-volume` does not touch mute (independent node state), so mute cannot change
by our hand during a duck — the item's "restore the stored mute" is satisfied vacuously
and safely. Writing mute back would fight a user who muted/unmuted mid-dictation — the
exact §4.2quinquies violation. The `[MUTED]` suffix is recorded (_muted_at_engage) for
the engage log line only, never written back.

PERCENT DISCIPLINE: the set value is ABSOLUTE — exactly f"{pct:.0f}%", never a `+`/`-`
prefix (that makes wpctl treat it as a relative change). Parsed floats can exceed 1.0
(live 1.05 = 105%) and are never clamped; the ducker's 0.5-pct epsilon absorbs float dust.

FAILURE DISCIPLINE (mirrors ducking_mpris.py): every wpctl call is a subprocess with
timeout=1.0, check=False, stderr=DEVNULL; TimeoutExpired/OSError/SubprocessError → ONE
warning line + safe default; nothing ever raises out of a protocol method.

OWNERSHIP: S1 audio_ducking.py = protocol + AudioDucker (frozen). S2 ducking_mpris.py =
the busctl MPRIS tier (parallel — it stubs THESE volume primitives as this file stubs
its MPRIS ones). T3 wires AudioDucker.from_config for duck_mode="volume"; T4 flips the
default and runs the LIVE duck+restore acceptance evidence (a live `wpctl set-volume`
is FORBIDDEN in this task's validation — it would mutate the operator's real audio).
"""
from __future__ import annotations

import logging
import re
import subprocess

from voice_typing.audio_ducking import PlayerState

logger = logging.getLogger(__name__)

_WPCTL = "wpctl"       # research §6 pins the argv form ("wpctl", verb, ...) byte-for-byte
_TIMEOUT_S = 1.0       # PRD §4.2quinquies: every audio call bounded <=1 s
_DEFAULT_SINK_SELECTOR = "@DEFAULT_AUDIO_SINK@"
_RE_VOLUME = re.compile(r"^Volume:\s*(\d+(?:\.\d+)?)")
_RE_DEFAULT_SINK = re.compile(r"\*\s+(\d+)\.")  # "*   72. Local Analog Stereo ..."


class WpctlVolumeBackend:
    """DuckBackend volume tier over wpctl (stateful about the node; bookkeeping stays in AudioDucker).

    The instance observes ONLY the ducker's call grammar (get, set(D) [, get, set(V0)])
    and carries the pinned node id + ducked flag across those calls; every method is
    bounded (<=1 s), best-effort, and NEVER raises — failure is one journal line plus
    the safe default (None / False). Protocol completeness: the three MPRIS methods are
    documented stubs — S2's ducking_mpris.py owns the real ones, and duck_mode="volume"
    never calls them.
    """

    def __init__(self) -> None:
        self._node: int | None = None  # pinned (engaged) default-sink node id
        self._ducked: bool = False     # True between the engage-set and the release-set
        self._muted_at_engage: bool | None = None  # diagnostics only — NEVER written back

    # --- volume primitives (the real tier) ---

    def get_sink_volume_pct(self) -> float | None:
        """Read a sink volume in percent (float × 100, unclamped) — pinning per the sequence.

        Engage-time (not yet ducked): resolve + pin the default sink's concrete node id.
        Release-time (ducked): read THE PINNED node so the ducker's compare-before-restore
        judges the ducked device even if the default changed mid-dictation. Returns None
        on any failure; a pinned-node grammar miss (the rc=0 "Node 'N' not found" trap)
        also unpins, so the next engage re-resolves.
        """
        if self._ducked and self._node is not None:
            target = self._node  # release-time compare: the DUCKED node, not a newly-selected sink
        else:
            self._node = self._resolve_default_node()  # engage-time: pin the CONCRETE id
            target = self._node if self._node is not None else _DEFAULT_SINK_SELECTOR
            if self._node is None:
                logger.debug("ducking(volume): no default sink in wpctl status; using the selector")
        out = self._run([_WPCTL, "get-volume", str(target)])
        m = _RE_VOLUME.match(out or "")
        if m is None:
            # rc LIES: a gone node answers rc=0 with "Node 'N' not found" — detect by grammar only.
            if self._ducked and self._node is not None:
                logger.info("ducking(volume): sink node %s gone; unpinning", self._node)
                self._node, self._ducked = None, False  # graceful skip + self-heal
            return None
        if not self._ducked:
            self._muted_at_engage = "[MUTED]" in out  # engage-log diagnostics only
        return float(m.group(1)) * 100.0

    def set_sink_volume_pct(self, pct: float) -> bool:
        """Set a sink volume in percent — ABSOLUTE (no +/- prefix) — on the pinned node id.

        Sequence transitions (research §2 state table): successful sets alternate — the
        first of a sequence is the engage duck (marks _ducked), the second is the
        release restore (clears the pin so the next engage re-resolves the
        then-current default). A restore skipped by the ducker's sovereignty rule
        leaves the flag set; the next completed set pair re-syncs it. Failed sets
        change no state.
        """
        target = str(self._node) if self._node is not None else _DEFAULT_SINK_SELECTOR
        if self._node is None:
            logger.debug("ducking(volume): unpinned; set-volume targets the selector (degraded)")
        ok = self._run_ok([_WPCTL, "set-volume", target, f"{pct:.0f}%"])
        if ok:
            self._ducked = not self._ducked  # engage duck / release restore, in sequence
            if not self._ducked:
                self._node = None  # release restore — re-pin at the next engage
        return ok

    # --- default-sink resolution ---

    def _resolve_default_node(self) -> int | None:
        """The default sink's concrete node id: the `*` line of `wpctl status`'s Sinks block.

        Scoped STRICTLY to the Sinks block (Sources has its OWN `*` — live-verified) and
        tolerant of the tree-glyph prefixes ("├─ Sinks:", "│  *   72. ..."). No marker →
        None → callers fall back to the @DEFAULT_AUDIO_SINK@ selector (degraded, not broken).
        """
        out = self._run([_WPCTL, "status"])
        if out is None:
            return None
        in_sinks = False
        for line in out.splitlines():
            s = line.strip()
            if s.endswith("Sinks:"):
                in_sinks = True
                continue
            if s.endswith("Sources:"):
                break  # the Sinks block ended — the Sources '*' must never win
            if in_sinks:
                m = _RE_DEFAULT_SINK.search(s)
                if m:
                    return int(m.group(1))
        return None

    # --- bounded subprocess helpers (mirrors ducking_mpris._run) ---

    def _run(self, argv: list[str]) -> str | None:
        """One bounded wpctl call: stripped stdout on rc==0, else None. Never raises."""
        try:
            cp = subprocess.run(
                argv,
                timeout=_TIMEOUT_S,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "ducking(volume): wpctl %s timed out (>%.1fs); continuing",
                " ".join(argv[1:2]), _TIMEOUT_S,
            )
            return None
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("ducking(volume): wpctl %s failed (%s); continuing", " ".join(argv[1:2]), exc)
            return None
        # rc==0 can still be a grammar miss ("Node 'N' not found") — the caller regexes stdout.
        return cp.stdout.strip() if cp.returncode == 0 else None

    def _run_ok(self, argv: list[str]) -> bool:
        """One bounded wpctl call, boolean form: True iff rc==0 (see _run)."""
        return self._run(argv) is not None

    # --- MPRIS tier stubs (S2: ducking_mpris.py owns the real ones) ---
    # Protocol completeness ONLY — zero subprocess calls. AudioDucker dispatches on
    # duck_mode, so "volume" never reaches these; symmetric to S2's volume stubs.

    def list_players(self) -> list[PlayerState]:
        return []  # not this tier (busctl); the volume duck needs no player enumeration

    def pause_player(self, name: str) -> bool:
        return False  # not this tier (busctl); duck_mode="volume" never calls this

    def resume_player(self, name: str) -> bool:
        return False  # not this tier (busctl); duck_mode="volume" never calls this

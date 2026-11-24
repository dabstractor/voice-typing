#!/usr/bin/env python3
"""g5_ab_compare — paired callback A/B analysis + stage diagnosis (S6).

SCOPE (P1.M2.T1.S6): consume the artifacts produced by tests/g5_timing_lab.py
(S4 runner, one arm per run) and produce the route-by-source comparison plus
the per-replay stage decomposition the metrics don't carry:

    speech_end → first USEFUL update   (recognizer + callback stage)
    useful update → ack                (relay + queue + dispatch + adapter)
    ack → field change                 (adapter paint; split only where the
                                        runner recorded coherent ack_ts)
    field change → paint-qualified frame  (pi only, ONLY when S5's
                                        frame_observer.status == "verified";
                                        otherwise a labelled read-poll proxy)

The module is PURE STDLIB analysis over `g5_timing_support` dataclasses
(imported read-only). It owns NO thresholds, NO verdicts and NO replay
logic: statuses are only measured / not-run / unverified-clock — never
pass/fail/blocked (the g6 parser owns those tokens; tables here must stay
parser-invisible). Churn scalars (insertions, corrections, misses, backlog,
updates_*) are copied VERBATIM from artifact["metrics"] — never recomputed,
never averaged away.

LIMITS (stated in every rendered section):
  - stage numbers are medians over replays; a single-replay arm carries n=1
    and no p95; p95 is reported only when n >= 5 (nearest-rank, never
    extrapolated);
  - a missing, corrupt or pre-S6 artifact renders a not-run row with its
    reason — never zeros, never a borrowed number;
  - heartbeat_ok false or clock_failures > 0 degrades the arm to
    unverified-clock (numbers shown, explicitly labelled);
  - misses are counted, never imputed (S3 law); capped replays are carried,
    not dropped;
  - plain is NOT assumed earlier: RealtimeSTT 1.0.2 fires both callbacks in
    the same eligible decode (stabilized first inline) — only the measured
    first-useful delta carries sign information.

Run as a module to rebuild the section from the S6 research artifacts:
    timeout 120 .venv/bin/python -m tests.g5_ab_compare
(or `.venv/bin/python tests/g5_ab_compare.py` from the repo root).
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g5_timing_support as g5  # noqa: E402  (read-only: S3 engine)

# --------------------------------------------------------------------------
# vocabulary (parser-safety: g6 owns pass/fail/blocked; we never emit them)
# --------------------------------------------------------------------------

STATUS_MEASURED = "measured"
STATUS_NOT_RUN = "not-run"
STATUS_UNVERIFIED_CLOCK = "unverified-clock"

FRAME_QUALIFIED_LABEL = "paint-qualified frame (S5 observer verified)"
FRAME_PAINT_FALLBACK_LABEL = (
    "S5-qualified paint, post-update boundary (disclosed fallback)"
)
FRAME_PROXY_LABEL = "editor read-poll proxy (frame NOT verified)"

#: sentinel for tests: "this provenance key must be ABSENT"
MISSING = object()

#: provenance keys that must agree across the arms of one route-pair
_COMPARABILITY_KEYS = (
    "clips",
    "device",
    "realtimestt_version",
    "python",
    "kernel",
    "replay_budget",
    "warm",
)

SECTION_HEADING = (
    "## Paired callback comparison and stage diagnosis (P1.M2.T1.S6)"
)

_EMDASH = "—"


# --------------------------------------------------------------------------
# per-replay stage decomposition
# --------------------------------------------------------------------------


def _as_ready(ev) -> g5.ReadyEvent:
    """Lossless coercion of legacy (t, text, kind[, ...]) tuples to
    ReadyEvent (S3 contract: every existing shape stays valid)."""
    if isinstance(ev, g5.ReadyEvent):
        return ev
    t, text, kind = ev[0], ev[1], ev[2]
    ack = ev[3] if len(ev) > 3 else None
    return g5.ReadyEvent(t=float(t), text=str(text), kind=str(kind),
                         ack_ts=None if ack is None else float(ack))


def _nearest_rank(sorted_vals: list[float], q: float) -> float:
    """Nearest-rank percentile over a pre-sorted list (pure stdlib)."""
    idx = max(0, math.ceil(q * len(sorted_vals)) - 1)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def _stage_block(values_ms: list[float]) -> dict | None:
    """{"med", "p95", "n"} — p95 ONLY when n >= 5 (Gotcha #3: never
    extrapolate; always print n)."""
    if not values_ms:
        return None
    srt = sorted(values_ms)
    block = {
        "med": round(statistics.median(srt), 1),
        "p95": round(_nearest_rank(srt, 0.95), 1) if len(srt) >= 5 else None,
        "n": len(srt),
    }
    return block


def _qualified_by_clip(frame_qualified) -> dict[str, list[dict]]:
    """Normalize S5's frame_qualified into {clip: [entry, ...]}.

    Accepts the artifact shape ([{"clip", "qualified"}, …]) or an already
    normalized dict. Entries carry {field_t, ack_ts, frame_t, class,
    latency_ms} (misses carry frame_t=None — never imputed)."""
    if not frame_qualified:
        return {}
    if isinstance(frame_qualified, dict):
        return frame_qualified
    out: dict[str, list[dict]] = {}
    for item in frame_qualified:
        if isinstance(item, dict) and "clip" in item:
            out.setdefault(item["clip"], []).extend(
                q for q in item.get("qualified", []) if isinstance(q, dict)
            )
    return out


def _replay_stages(rec: g5.ReplayRecord) -> dict:
    """One replay's boundary timestamps (monotonic seconds) + warnings.

    - speech_end = feed_start + words[-1].end (pacer maps audio-time to
      wall-time linearly; Gotcha #11 — never mix time.time() in);
    - first USEFUL update = first partial after feed_start whose text grows
      beyond the rolling hypothesis (changed span non-empty; a same-text
      repeat or no-op is NOT useful — S3 no_op law);
    - first VISIBLE field event = first field change at/after the useful
      update that adds replay content over the pre-replay anchor (field
      snapshots are truth — R.5 #3; ACK is never a frame);
    - ack splits ONLY when useful_t <= ack_ts <= vis_t (an ack outside the
      sanity window is a provenance warning, never a negative latency)."""
    warnings: list[str] = []
    speech_end = (
        rec.feed_start + rec.words[-1].end if rec.words else None
    )

    useful = None  # the first useful ReadyEvent
    running = rec.anchor_text or ""
    for ev in sorted(
        (_as_ready(e) for e in rec.update_ready), key=lambda e: e.t
    ):
        if ev.t < rec.feed_start or ev.kind != "partial":
            continue
        if g5.changed_spans(running, ev.text):
            useful = ev
            break
        running = ev.text  # no-op/repeat: not useful; keep rolling

    vis_fe = None
    if useful is not None:
        anchor = rec.anchor_text or ""
        for fe in sorted(rec.field_events, key=lambda f: f.t):
            if fe.t < useful.t:
                continue
            if g5.changed_spans(anchor, fe.text):
                vis_fe = fe
                break

    ack_t = None
    if useful is not None and useful.ack_ts is not None:
        a = useful.ack_ts
        if a >= useful.t and (vis_fe is None or a <= vis_fe.t):
            ack_t = a
        elif vis_fe is not None and a > vis_fe.t:
            warnings.append(
                f"ack_ts {a:.3f} after field ts {vis_fe.t:.3f} on clip "
                f"{rec.clip!r} — ack ignored for the split"
            )
        else:
            warnings.append(
                f"ack_ts {a:.3f} before useful update on clip {rec.clip!r} "
                "— ack ignored for the split"
            )

    return {
        "clip": rec.clip,
        "speech_end": speech_end,
        "useful": useful,
        "vis_fe": vis_fe,
        "ack_t": ack_t,
        "warnings": warnings,
        "capped": bool(rec.capped),
    }


def stage_summary(
    records: list[g5.ReplayRecord],
    *,
    frame_observer: dict | None = None,
    frame_qualified=None,
) -> dict:
    """The per-run additive stage decomposition over measured replays.

    Returns a JSON-safe dict: route/arm labels, per-stage {"med","p95","n"}
    blocks (None where the boundary was never observed), churn/cap scalars,
    and provenance warnings. The field→frame stage exists ONLY when S5's
    frame_observer reports status "verified" AND a paint-qualified
    frame_qualified entry matches the visible field event; otherwise it is
    None with the proxy label (an ACK never upgrades it — R.5 #3).
    Medians only describe THIS run's samples; p95 appears at n >= 5."""
    st = [_replay_stages(r) for r in records]
    warnings = [w for s in st for w in s["warnings"]]

    speech_to_useful: list[float] = []
    speech_to_visible: list[float] = []
    useful_to_ack: list[float] = []
    ack_to_field: list[float] = []
    useful_to_field: list[float] = []
    field_to_frame: list[float] = []

    verified = bool(
        isinstance(frame_observer, dict)
        and frame_observer.get("status") == "verified"
    )
    # Record-ALIGNED list form (the artifact shape, index-matched to
    # records) when lengths agree; otherwise a clip-keyed pool. Alignment
    # matters for the post-update fallback below: pooled same-clip entries
    # from OTHER replays must never satisfy this replay's window.
    aligned: list[list[dict]] | None = None
    if verified and isinstance(frame_qualified, list) and len(
        frame_qualified
    ) == len(records):
        aligned = [
            [
                q
                for q in (item.get("qualified") or [])
                if isinstance(q, dict)
            ]
            if isinstance(item, dict)
            else []
            for item in frame_qualified
        ]
    fq = _qualified_by_clip(frame_qualified) if verified else {}

    paint_qualified: list[float] = []  # S5 pairs' OWN paint latency (fallback)
    n_frame_exact = 0
    n_frame_fallback = 0

    for i, (rec, s) in enumerate(zip(records, st)):
        useful, vis_fe, ack_t, speech_end = (
            s["useful"], s["vis_fe"], s["ack_t"], s["speech_end"],
        )
        if speech_end is not None and useful is not None:
            speech_to_useful.append((useful.t - speech_end) * 1000.0)
        if speech_end is not None and vis_fe is not None:
            speech_to_visible.append((vis_fe.t - speech_end) * 1000.0)
        if useful is not None and ack_t is not None:
            useful_to_ack.append((ack_t - useful.t) * 1000.0)
        if vis_fe is not None and ack_t is not None:
            ack_to_field.append((vis_fe.t - ack_t) * 1000.0)
        # merged update→field ONLY where this replay had no coherent ack
        # (the split replaces the merged cell — never both)
        if useful is not None and vis_fe is not None and ack_t is None:
            useful_to_field.append((vis_fe.t - useful.t) * 1000.0)
        if vis_fe is not None and verified:
            # the boundary's OWN qualified entry first (exact paint pairing)
            entries = (
                aligned[i] if aligned is not None else fq.get(rec.clip, [])
            )
            matched = False
            for q in entries:
                ft = q.get("field_t")
                if (
                    ft is not None
                    and abs(float(ft) - vis_fe.t) <= 1e-4
                    and q.get("frame_t") is not None
                ):
                    field_to_frame.append(
                        (float(q["frame_t"]) - vis_fe.t) * 1000.0
                    )
                    n_frame_exact += 1
                    matched = True
                    break
            if not matched:
                # S5's correlator treats the replay's first drained event as
                # its baseline, and the first-visible paint usually IS that
                # event — so the exact pair is often structurally absent.
                # Fallback (disclosed, never merged into the exact cell):
                # the earliest paint-QUALIFIED change at/after the useful
                # update, using the pair's own (field_t → frame_t) latency.
                cands = [
                    q
                    for q in entries
                    if q.get("field_t") is not None
                    and useful is not None
                    and float(q["field_t"]) >= useful.t
                    and q.get("frame_t") is not None
                ]
                if cands:
                    q0 = min(cands, key=lambda q: float(q["field_t"]))
                    paint_qualified.append(
                        (float(q0["frame_t"]) - float(q0["field_t"]))
                        * 1000.0
                    )
                    n_frame_fallback += 1

    arms = {getattr(r, "partial_source", "") for r in records}
    routes = {getattr(r, "route", "") for r in records}
    n_updates = sum(
        1
        for r in records
        for e in (_as_ready(x) for x in r.update_ready)
        if e.kind == "partial" and e.t >= r.feed_start
    )

    f2f_block = _stage_block(field_to_frame)
    return {
        "route": next(iter(routes)) if len(routes) == 1 else "",
        "arm": next(iter(arms)) if len(arms) == 1 else "",
        "speech_to_useful_ms": _stage_block(speech_to_useful)
        or {"med": None, "p95": None, "n": 0},
        "speech_to_visible_ms": _stage_block(speech_to_visible)
        or {"med": None, "p95": None, "n": 0},
        "useful_to_ack_ms": _stage_block(useful_to_ack),
        "ack_to_field_ms": _stage_block(ack_to_field),
        "useful_to_field_ms": _stage_block(useful_to_field),
        "ack_split": bool(useful_to_ack),
        "field_to_frame_ms": f2f_block,
        "paint_qualified_ms": _stage_block(paint_qualified),
        "frame_match": (
            "exact-first-visible" if n_frame_exact
            else (
                "post-update-qualified" if n_frame_fallback else "none"
            )
        ),
        "n_frame_exact": n_frame_exact,
        "n_frame_fallback": n_frame_fallback,
        "frame_verified": verified,
        # the basis label describes the CELL: an exact boundary pair, the
        # disclosed post-update fallback, or the proxy — observer
        # verification alone never upgrades a missing cell (CRITICAL #6;
        # an ACK never upgrades it either, R.5 #3)
        "frame_basis": (
            FRAME_QUALIFIED_LABEL if f2f_block
            else (
                FRAME_PAINT_FALLBACK_LABEL if _stage_block(paint_qualified)
                else FRAME_PROXY_LABEL
            )
        ),
        "n_replays": len(records),
        "n_updates": n_updates,
        "n_acks": len(useful_to_ack),
        "provenance_warnings": warnings,
        "capped_replays": sum(1 for s in st if s["capped"]),
    }


# --------------------------------------------------------------------------
# artifact loading + cross-arm provenance gate
# --------------------------------------------------------------------------


def load_artifact(path) -> dict:
    """JSON-parse an S4/S6 artifact; OSError/JSONDecodeError → {} (the
    caller renders a not-run row — never zeros, CRITICAL #3)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _device_confound(d: dict) -> dict:
    """Device dict minus the arm's own treatment label.

    The runner embeds `partial_callback` (the arm's installed callback —
    the TREATMENT variable) inside `provenance.device`; it MUST differ
    across arms by design. Comparability therefore excludes that one key:
    everything else in the dict (device, compute_type, model,
    context_prompt, …) must match exactly."""
    d = dict(d or {})
    d.pop("partial_callback", None)
    return d


def check_comparable(arts: dict[tuple[str, str], dict]) -> list[str]:
    """Fail-closed cross-arm provenance gate, PER ROUTE-PAIR (Gotcha #8).

    Every violation — clip set, device dict, RealtimeSTT version, python,
    kernel, replay budget, warm policy, missing key, heartbeat sanity, or
    both arms reporting the same effective source — becomes one reason
    string. Reasons must surface in the rendered limits; none is ever
    silently dropped. Empty dicts (not-run arms) are skipped: an absent run
    is a not-run row, not a comparability violation. Cross-route rows are
    never compared."""
    by_route: dict[str, list[tuple[str, dict]]] = {}
    for (route, arm), art in arts.items():
        if art:
            by_route.setdefault(route, []).append((arm, art))
    reasons: list[str] = []
    for route, members in sorted(by_route.items()):
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                arm_a, a = members[i]
                arm_b, b = members[j]
                pa = a.get("provenance") or {}
                pb = b.get("provenance") or {}
                for key in _COMPARABILITY_KEYS:
                    va, vb = pa.get(key, MISSING_SENTINEL), pb.get(
                        key, MISSING_SENTINEL
                    )
                    if key == "device":
                        # exclude the arm's own treatment label (see
                        # _device_confound — it differs across arms BY
                        # DESIGN); the rest must match exactly
                        va = _device_confound(va) if isinstance(va, dict) else va
                        vb = _device_confound(vb) if isinstance(vb, dict) else vb
                    if va is MISSING_SENTINEL or vb is MISSING_SENTINEL:
                        reasons.append(
                            f"{route}: provenance {key!r} missing from an "
                            f"arm ({arm_a} vs {arm_b})"
                        )
                    elif va != vb:
                        reasons.append(
                            f"{route}: {key} differs across arms "
                            f"({arm_a} vs {arm_b})"
                        )
                ha, hb = a.get("heartbeat_ok"), b.get("heartbeat_ok")
                if ha is False or hb is False:
                    reasons.append(
                        f"{route}: heartbeat_ok false (clock unverified; "
                        f"{arm_a} vs {arm_b})"
                    )
                eff_a = pa.get("partial_callback_effective", "")
                eff_b = pb.get("partial_callback_effective", "")
                if eff_a and eff_a == eff_b:
                    reasons.append(
                        f"{route}: both arms report effective source "
                        f"{eff_a!r} — the pair cannot contrast callbacks"
                    )
    return reasons


MISSING_SENTINEL = MISSING  # internal alias (same object)


# --------------------------------------------------------------------------
# the route-by-source assembly
# --------------------------------------------------------------------------


@dataclasses.dataclass
class StageRow:
    """One arm's row: stage decomposition + verbatim metric scalars.

    `status` is ONLY measured / not-run / unverified-clock — never a g6
    verdict token (parser safety, CRITICAL #2). Numeric fields are None
    when the artifact is missing/corrupt/pre-S6: a not-run row never
    carries zeros (CRITICAL #3)."""

    route: str
    arm: str
    status: str
    reason: str = ""

    # stage decomposition (medians ms; p95 when n>=5)
    speech_to_useful_med_ms: float | None = None
    speech_to_useful_p95_ms: float | None = None
    speech_to_visible_med_ms: float | None = None
    speech_to_visible_p95_ms: float | None = None
    useful_to_ack_med_ms: float | None = None
    ack_to_field_med_ms: float | None = None
    useful_to_field_med_ms: float | None = None
    field_to_frame_med_ms: float | None = None
    paint_qualified_med_ms: float | None = None  # S5 fallback (own-pair)
    frame_verified: bool = False
    frame_basis: str = FRAME_PROXY_LABEL
    ack_split: bool = False

    # sample counts (always printed alongside every percentile)
    n_replays: int = 0
    n_updates: int = 0
    n_acks: int = 0
    replays_measured: int = 0

    # churn/backlog scalars — copied VERBATIM from artifact["metrics"]
    speech_med_ms: float | None = None
    speech_p95_ms: float | None = None
    insertions: int = 0
    corrections: int = 0
    misses: int = 0
    updates_total: int = 0
    updates_matched: int = 0
    updates_superseded: int = 0
    updates_no_op: int = 0
    updates_ambiguous: int = 0
    max_words_outstanding: int = 0
    backlog_sustained: bool = False
    sentence_end_dump: bool = False
    worst_gap_ms: float | None = None
    clock_failures: int = 0
    capped_replays: int = 0
    capped_in_runner: int = 0  # stage-block view (records with capped=True)


def _row_from_artifact(route: str, arm: str, art: dict) -> StageRow:
    stage = art.get("stage_summary") or {}
    metrics = art.get("metrics") or {}

    def _med(key):
        blk = stage.get(key)
        return blk.get("med") if isinstance(blk, dict) else None

    def _p95(key):
        blk = stage.get(key)
        return blk.get("p95") if isinstance(blk, dict) else None

    f2f_blk = stage.get("field_to_frame_ms")
    pq_blk = stage.get("paint_qualified_ms")
    # re-DERIVE the basis from cell presence (older artifacts may carry a
    # stale baked label; the cells are the truth)
    if isinstance(f2f_blk, dict) and f2f_blk.get("med") is not None:
        basis = FRAME_QUALIFIED_LABEL
    elif isinstance(pq_blk, dict) and pq_blk.get("med") is not None:
        basis = FRAME_PAINT_FALLBACK_LABEL
    else:
        basis = FRAME_PROXY_LABEL

    status, reason = STATUS_MEASURED, ""
    if art.get("heartbeat_ok") is False:
        status, reason = STATUS_UNVERIFIED_CLOCK, "heartbeat_ok false"
    elif int(metrics.get("clock_failures") or 0) > 0:
        status = STATUS_UNVERIFIED_CLOCK
        reason = f"clock failures: {metrics.get('clock_failures')}"

    return StageRow(
        route=route,
        arm=arm,
        status=status,
        reason=reason,
        speech_to_useful_med_ms=_med("speech_to_useful_ms"),
        speech_to_useful_p95_ms=_p95("speech_to_useful_ms"),
        speech_to_visible_med_ms=_med("speech_to_visible_ms"),
        speech_to_visible_p95_ms=_p95("speech_to_visible_ms"),
        useful_to_ack_med_ms=_med("useful_to_ack_ms"),
        ack_to_field_med_ms=_med("ack_to_field_ms"),
        useful_to_field_med_ms=_med("useful_to_field_ms"),
        field_to_frame_med_ms=_med("field_to_frame_ms"),
        paint_qualified_med_ms=_med("paint_qualified_ms"),
        frame_verified=bool(stage.get("frame_verified")),
        frame_basis=basis,
        ack_split=bool(stage.get("ack_split")),
        n_replays=int(stage.get("n_replays") or 0),
        n_updates=int(stage.get("n_updates") or 0),
        n_acks=int(stage.get("n_acks") or 0),
        replays_measured=int(metrics.get("replays") or 0),
        speech_med_ms=metrics.get("speech_med_ms"),
        speech_p95_ms=metrics.get("speech_p95_ms"),
        insertions=int(metrics.get("insertions") or 0),
        corrections=int(metrics.get("corrections") or 0),
        misses=int(metrics.get("misses") or 0),
        updates_total=int(metrics.get("updates_total") or 0),
        updates_matched=int(metrics.get("updates_matched") or 0),
        updates_superseded=int(metrics.get("updates_superseded") or 0),
        updates_no_op=int(metrics.get("updates_no_op") or 0),
        updates_ambiguous=int(metrics.get("updates_ambiguous") or 0),
        max_words_outstanding=int(metrics.get("max_words_outstanding") or 0),
        backlog_sustained=bool(metrics.get("backlog_sustained")),
        sentence_end_dump=bool(metrics.get("sentence_end_dump")),
        worst_gap_ms=metrics.get("worst_gap_ms"),
        clock_failures=int(metrics.get("clock_failures") or 0),
        capped_replays=int(metrics.get("cap_failures") or 0),
        capped_in_runner=int(stage.get("capped_replays") or 0),
    )


def _not_run_row(route: str, arm: str, reason: str) -> StageRow:
    return StageRow(route=route, arm=arm, status=STATUS_NOT_RUN, reason=reason)


def compare(artifact_paths: dict[tuple[str, str], Path]) -> list[StageRow]:
    """Load each arm's artifact and assemble the route-by-source rows.

    Labels (never g6 verdicts): measured (parsed, heartbeat ok, no clock
    failures) / unverified-clock (heartbeat or clock sanity doubts —
    numbers still shown, labelled) / not-run (missing, corrupt, empty or
    pre-S6 artifact — all numeric fields None, reason set)."""
    rows: list[StageRow] = []
    for (route, arm), path in sorted(artifact_paths.items()):
        if not Path(path).is_file():
            rows.append(
                _not_run_row(route, arm, f"artifact file missing: {path}")
            )
            continue
        art = load_artifact(path)
        if not art:
            rows.append(
                _not_run_row(
                    route, arm, f"artifact not parseable as JSON: {path}"
                )
            )
            continue
        if not art.get("provenance"):
            rows.append(
                _not_run_row(route, arm, "artifact lacks provenance block")
            )
            continue
        if "stage_summary" not in art:
            rows.append(
                _not_run_row(
                    route,
                    arm,
                    "artifact lacks the stage decomposition "
                    "(pre-S6 runner output)",
                )
            )
            continue
        rows.append(_row_from_artifact(route, arm, art))
    return rows


# --------------------------------------------------------------------------
# rendering (dated, non-verdict, limits-forward)
# --------------------------------------------------------------------------


def _fmt(v, unit="") -> str:
    if v is None:
        return _EMDASH
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.1f}{unit}"
    return str(v)


def _delta_line(route: str, plain: StageRow, stab: StageRow) -> list[str]:
    """Early-callback vs early-visibility deltas (sign carried, never
    assumed — CRITICAL #7)."""
    lines: list[str] = []
    if plain.status != STATUS_MEASURED or stab.status != STATUS_MEASURED:
        return lines
    for label, attr in (
        ("first-useful-update", "speech_to_useful_med_ms"),
        ("first-visible-word", "speech_to_visible_med_ms"),
    ):
        a, b = getattr(plain, attr), getattr(stab, attr)
        if a is None or b is None:
            continue
        d = a - b
        who = "plain EARLIER" if d < 0 else "plain NOT earlier"
        lines.append(
            f"- {route}: plain-vs-stabilized {label} median delta = "
            f"{d:+.1f} ms ({who} at the "
            f"{'callback' if 'useful' in attr else 'field'} boundary)"
        )
    return lines


def _dominant_lines(rows: list[StageRow]) -> list[str]:
    """Dominant POST-CALLBACK stage per measured arm (the only stages that
    are latencies). The speech-anchored cell is a boundary OFFSET — the
    first useful update arrives mid-clip, before the clip's speech_end, so
    it is negative by construction and never ranked; the per-word visible
    lag it proxies lives in metrics.speech_med_ms (verbatim)."""
    lines: list[str] = []
    for r in rows:
        if r.status != STATUS_MEASURED:
            continue
        stages = {
            "update→ack": r.useful_to_ack_med_ms,
            "ack→field": r.ack_to_field_med_ms,
            "useful→field (merged)": r.useful_to_field_med_ms,
            "field→frame": r.field_to_frame_med_ms,
            "paint-qualified (S5)": r.paint_qualified_med_ms,
        }
        named = {k: v for k, v in stages.items() if v is not None}
        if named:
            dom = max(named, key=lambda k: named[k])
            lines.append(
                f"- {r.route}/{r.arm}: dominant post-callback stage = {dom} "
                f"at {named[dom]:.1f} ms median (n={r.n_replays})"
            )
        else:
            lines.append(
                f"- {r.route}/{r.arm}: no post-callback stage measured"
            )
        if r.speech_med_ms is not None:
            lines.append(
                f"  · per-word speech→visible lag (verbatim metrics): "
                f"med {r.speech_med_ms:.1f} ms / p95 "
                f"{r.speech_p95_ms if r.speech_p95_ms is not None else '—'} ms"
                " — everything above that is accumulated BEFORE the "
                "callback/adapter stages"
            )
    return lines


def render_markdown(rows: list[StageRow], *, meta: dict) -> str:
    """The dated evidence section (Mode A). Non-verdict vocabulary ONLY in
    tables: g6's parser owns pass/fail/blocked; appending this section to
    the evidence doc must leave parse_route_verdicts byte-identical.
    Provenance, four arm rows, stage decomposition, deltas, dominant stage,
    candidate criteria pointers, and limits (incl. every comparability
    reason and every not-run reason)."""
    out: list[str] = [SECTION_HEADING, ""]

    # provenance block
    out.append("### Provenance")
    out.append("")
    pairs = (
        ("Date", meta.get("date")),
        ("HEAD commit", meta.get("commit")),
        ("RealtimeSTT version", meta.get("realtimestt_version")),
        ("Model / device", meta.get("device")),
        ("Cadence", meta.get("cadence")),
        ("Replay budget", meta.get("budget")),
        ("Warm policy", meta.get("warm")),
        ("Pi frame observer", meta.get("observer")),
    )
    for label, v in pairs:
        if v:
            out.append(f"- {label}: {v}")
    commands = meta.get("commands") or []
    if commands:
        out.append("")
        out.append("Exact commands (sequential, one arm at a time):")
        out.append("")
        out.append("```bash")
        out.extend(commands)
        out.append("```")
    out.append("")

    # route-by-source table
    out.append("### Route-by-source result")
    out.append("")
    out.append(
        "| Route | Arm | Status | 1st useful (med ms) | 1st useful (p95 ms) "
        "| 1st visible (med ms) | word lag med/p95 (ms) "
        "| upd matched/sup/no-op | ins/cor | miss "
        "| backlog max | dump | n |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.status == STATUS_NOT_RUN:
            # a not-run row never carries zeros (CRITICAL #3): every
            # numeric cell is an em-dash; only the reason surfaces (limits)
            out.append(
                f"| {r.route} | {r.arm} | {r.status} | {_EMDASH} | {_EMDASH} "
                f"| {_EMDASH} | {_EMDASH} | {_EMDASH} | {_EMDASH} | {_EMDASH} "
                f"| {_EMDASH} | {_EMDASH} | {_EMDASH} |"
            )
            continue
        lag = (
            f"{_fmt(r.speech_med_ms)}/{_fmt(r.speech_p95_ms)}"
            if r.speech_med_ms is not None
            else _EMDASH
        )
        out.append(
            f"| {r.route} | {r.arm} | {r.status} "
            f"| {_fmt(r.speech_to_useful_med_ms)} "
            f"| {_fmt(r.speech_to_useful_p95_ms)} "
            f"| {_fmt(r.speech_to_visible_med_ms)} "
            f"| {lag} "
            f"| {r.updates_matched}/{r.updates_superseded}/{r.updates_no_op} "
            f"| {r.insertions}/{r.corrections} | {r.misses} "
            f"| {r.max_words_outstanding} "
            f"| {'yes' if r.sentence_end_dump else 'no'} | {r.n_replays} |"
        )
    out.append("")
    out.append(
        "`1st useful`/`1st visible` are speech-end-anchored boundary "
        "offsets: the first useful update fires mid-clip, so the cell is "
        "NEGATIVE by construction (its magnitude is when the first words "
        "were recognized relative to the clip's final word end). Cross-arm "
        "deltas at these cells are the early-callback/early-visibility "
        "signal (same clips ⇒ same anchors, deltas cancel the anchor). The "
        "per-word VISIBLE lag is the verbatim `word lag med/p95` column."
    )
    out.append("")

    # stage decomposition table
    out.append("### Stage decomposition (medians; p95 at n≥5)")
    out.append("")
    out.append(
        "| Route | Arm | speech→update | update→ack | ack→field "
        "| useful→field (merged) | field→frame | paint-qualified (S5) "
        "| frame basis | n |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.status == STATUS_NOT_RUN:
            out.append(
                f"| {r.route} | {r.arm} | {_EMDASH} | {_EMDASH} | {_EMDASH} "
                f"| {_EMDASH} | {_EMDASH} | {_EMDASH} | {_EMDASH} | {_EMDASH} |"
            )
            continue
        out.append(
            f"| {r.route} | {r.arm} "
            f"| {_fmt(r.speech_to_useful_med_ms, ' ms')} "
            f"| {_fmt(r.useful_to_ack_med_ms, ' ms')} "
            f"| {_fmt(r.ack_to_field_med_ms, ' ms')} "
            f"| {_fmt(r.useful_to_field_med_ms, ' ms')} "
            f"| {_fmt(r.field_to_frame_med_ms, ' ms')} "
            f"| {_fmt(r.paint_qualified_med_ms, ' ms')} "
            f"| {r.frame_basis} | {r.n_replays} |"
        )
    out.append("")
    out.append(
        "Rows labelled `merged` carry the update→field latency in one cell "
        "(the runner recorded no coherent ack_ts for that arm); `ack→field` "
        "and `update→ack` are then absent. The `field→frame` cell is the "
        "EXACT first-visible-paint pairing — usually structurally absent "
        "because S5's correlator treats each replay's first drained event "
        "as baseline, and that event is usually the first-visible paint "
        "itself. `paint-qualified (S5)` is the disclosed fallback: the "
        "earliest S5-qualified paint at/after the useful update, using the "
        "pair's own (field→frame) latency — real measured pairs, boundary "
        "choice disclosed; the two cells are never merged. When neither "
        "exists the stage stays the labelled proxy: "
        f"{FRAME_PROXY_LABEL}."
    )
    out.append("")

    # deltas + dominant stage (mechanical, sign carried)
    out.append("### Early callback vs early field visibility")
    out.append("")
    by_route: dict[str, dict[str, StageRow]] = {}
    for r in rows:
        by_route.setdefault(r.route, {})[r.arm] = r
    delta_lines: list[str] = []
    for route, arms in sorted(by_route.items()):
        plain, stab = arms.get("plain"), arms.get("stabilized")
        if plain and stab:
            delta_lines.extend(_delta_line(route, plain, stab))
    out.extend(delta_lines or ["- (no route has both arms measured)"])
    out.append("")
    out.append("### Dominant stage per arm")
    out.append("")
    out.extend(_dominant_lines(rows) or ["- (no measured arms)"])
    out.append("")
    out.append(
        "Candidate criteria for the T2 subtasks: the winning arm's "
        "update volume/burst profile (updates_total, superseded/no-op "
        "shares, worst_gap_ms above) sizes P1.M2.T2.S1's dispatch-"
        "promptness + burst fail-closed design; the dominant stage and its "
        "magnitude name what P1.M2.T2.S2's remediation must move."
    )
    out.append("")

    # limits
    out.append("### Instrumentation limits")
    out.append("")
    reasons = list(meta.get("limits") or [])
    for r in rows:
        if r.status != STATUS_MEASURED:
            head = f"{r.route}/{r.arm}: {r.status}"
            if r.reason:
                head += f" ({r.reason})"
            reasons.append(head)
        if r.capped_replays or r.capped_in_runner:
            reasons.append(
                f"{r.route}/{r.arm}: capped records carried "
                f"(runner {r.capped_in_runner}, metrics {r.capped_replays}) "
                "— never dropped"
            )
    out.extend(f"- {x}" for x in reasons)
    out.append(
        "- Stage shares are medians over replays; p95 only at n≥5; misses "
        "counted, never imputed; replay counts may differ across arms "
        "(early budget break) — a disclosed limit, not pooled."
    )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# __main__: rebuild the S6 section from the research artifacts
# --------------------------------------------------------------------------

_PAIRS = (
    ("im-gtk", "plain"),
    ("im-gtk", "stabilized"),
    ("pi-ghostty", "plain"),
    ("pi-ghostty", "stabilized"),
)


def _head_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _realtimestt_version() -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version("RealtimeSTT")
    except Exception:
        return "unavailable"


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    research = (
        repo
        / "plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/research"
    )
    paths = {
        (route, arm): research / f"artifact-{route}-{arm}.json"
        for route, arm in _PAIRS
    }
    arts = {k: load_artifact(v) for k, v in paths.items()}
    rows = compare(paths)
    reasons = check_comparable(arts)

    provenance = next(
        (a.get("provenance") or {} for a in arts.values() if a), {}
    )
    observer = {}
    for (route, _arm), a in arts.items():
        blk = a.get("frame_observer") or {}
        if route == "pi-ghostty" and blk.get("status"):
            observer[route] = str(blk.get("status"))
    replays_note = ", ".join(
        f"{r}/{a}: {row.replays_measured}"
        for (r, a), row in zip(sorted(paths), sorted(rows, key=lambda x: (x.route, x.arm)))
        if row.replays_measured
    )
    meta = {
        "date": datetime.date.today().isoformat(),
        "commit": _head_commit(),
        "realtimestt_version": _realtimestt_version(),
        "device": json.dumps(provenance.get("device"), sort_keys=True)
        if provenance.get("device")
        else "",
        "cadence": (
            "audio fed in real time: 32 ms chunks sleep-to-target on "
            "time.monotonic() + 1.6 s trailing silence (paced_feed)"
        ),
        "budget": f"g5.REPLAY_BUDGET={g5.REPLAY_BUDGET} "
        f"(actual replays — {replays_note or 'none recorded'})",
        "warm": provenance.get("warm", ""),
        "observer": observer,
        "commands": [
            "timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 "
            ".venv/bin/python tests/g5_timing_lab.py --route im-gtk "
            "--partial-source plain",
            "timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 "
            ".venv/bin/python tests/g5_timing_lab.py --route im-gtk",
            "timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 "
            "PI_BIN=\"$(command -v pi)\" .venv/bin/python "
            "tests/g5_timing_lab.py --route pi-ghostty --partial-source plain",
            "timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 "
            "PI_BIN=\"$(command -v pi)\" .venv/bin/python "
            "tests/g5_timing_lab.py --route pi-ghostty",
        ],
        "limits": reasons
        + [
            "single machine / single session scope; editor read-poll "
            "instrumentation on the pi route (10 ms poll)",
        ],
    }
    section = render_markdown(rows, meta=meta)
    out_path = research / "ab_section.md"
    out_path.write_text(section, encoding="utf-8")
    print(section)
    print(f"[g5_ab_compare] wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""g5_timing_support — the pure-stdlib G5 metrics engine (P1.M6.T4.S1).

NO CUDA, NO desktop, NO subprocess: this module is imported by the collected
unit tests (tests/test_g5_timing_support.py, venv python, fast) AND by the
live lab (tests/g5_timing_lab.py, inside the private desktop session). It
turns replay records (alignment fixture + field change log + update-ready
timestamps) into per-route RouteMetrics + a verdict, per PRD §4.2sexies R.7
G5:

  - speech clock = word-aligned replay of the real-voice clips (the alignment
    fixture mapped through the pacer's monotonic replay clock). NO G5 number
    derives from callback cadence or VAD/silence timing (Gotcha #1).
  - visibility truth = the FIELD's own change events (R.5 value #3). Wire
    timestamps / on_applied elapsed_ms are cross-checks, never the source.
  - misses are misses: excluded from latency stats, never zero-latency
    samples (Gotcha #7).
  - hard-fail rules override medians (Gotcha #8): sustained ≥5-word backlog,
    sentence-end dump, threshold breach, count shortfall — each spelled out
    in `failures`, never averaged away.

Lineage/shape mirrors tests/ime_g3_support.py (pure, dual-imported) and the
word normalization reuses tools/asr-lab/common.py's norm_words rules (the
same matching space as the alignment generator's cross-check).
"""

from __future__ import annotations

import json
import math
import re
import statistics
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

# --- G5 thresholds (PRD §4.2sexies R.7, verbatim numbers; Gotcha #8/#9) -------
SPEECH_MED_MS = 500.0  # speech-end→word-visible median ≤ 500 ms
SPEECH_P95_MS = 1000.0  # speech-end→word-visible p95 < 1 s (≥ 1000 fails)
READY_P95_INSERT_MS = 100.0  # update-ready→first-changed-frame p95, insertion
READY_P95_CORRECT_MS = 50.0  # ... correction
MIN_COUNT = 100  # ≥ 100 insertions AND ≥ 100 corrections per claimed route
SUSTAIN_WORDS = 5  # backlog ≥ 5 words outstanding...
SUSTAIN_WINDOW_S = 2.0  # ...held ≥ 2.0 s ⇒ route FAIL regardless of medians
DUMP_MIN_WORDS = 5  # utterance of ≥ 5 words with...
DUMP_MAX_PRE_FINALIZE = 1  # ...< 2 visible before its finalize ⇒ FAIL
UTTERANCE_GAP_S = 0.6  # alignment inter-word gap that splits utterances
REPLAY_BUDGET = 20  # max measured replays per route (count floors need budget)
TRAILING_SILENCE_S = 1.6  # zero-slice trailing feed (> 0.6+0.16 s gate)

# --- data model (PRP blueprint) ------------------------------------------------


@dataclass
class WordAlign:
    """One row of <clip>.words.json: word + its [start, end] seconds in the clip."""

    word: str
    start: float
    end: float


@dataclass
class FieldEvent:
    """One field text-change observation (the ONLY visibility truth — R.5 #3)."""

    t: float  # time.monotonic() at the field's own change callback
    text: str  # full rendered text after the change
    kind: str = ""  # producer hint ("changed"|"frame"|...) — never used for truth


@dataclass
class ReplayRecord:
    """One measured replay (warmup replays are discarded before any record)."""

    route: str
    clip: str
    feed_start: float  # pacer's time.monotonic() when audio-time 0 hit the queue
    words: list[WordAlign]
    field_events: list[FieldEvent]  # THIS replay's slice of the field log
    update_ready: list[tuple[float, str, str]]  # (mono ts, text, "partial"|"final")
    finals_ts: list[float] = field(default_factory=list)  # final dispatch times
    anchor: int = 0  # normalized-token count of the field text at replay start


@dataclass
class FrameSample:
    """One update-ready→first-changed-frame pairing."""

    delta_ms: float
    cls: str  # "insert" | "correct"


@dataclass
class RouteMetrics:
    """The published per-route aggregate (every breach spelled out, none averaged)."""

    route: str
    insertions: int = 0
    corrections: int = 0
    misses: int = 0
    speech_to_visible_med_ms: float | None = None
    speech_to_visible_p95_ms: float | None = None
    worst_gap_ms: float | None = None
    ready_p95_insert_ms: float | None = None
    ready_p95_correct_ms: float | None = None
    max_words_outstanding: int = 0
    backlog_sustained: bool = False
    sentence_end_dump: bool = False
    unchanged_zero_edit_ok: bool = True
    replays: int = 0
    verdict: str = "fail"
    failures: list[str] = field(default_factory=list)


# --- normalization (tools/asr-lab/common.py norm_words rules) ------------------


def normalize_token(word: str) -> str:
    """One word → the shared matching space (NFKC, lower, [a-z0-9'] only)."""
    s = unicodedata.normalize("NFKC", word).lower()
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    return " ".join(s.split())


def normalize_tokens(text: str) -> list[str]:
    """Full rendered text → normalized token list (norm_words semantics)."""
    s = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^a-z0-9' ]", " ", s).split()


# --- IO (small committed fixtures + the field's bounded JSONL log) -------------


def load_alignments(path: str | Path) -> list[WordAlign]:
    """Parse tools/asr-lab/voice/<name>.words.json ([{word, start, end}, ...])."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        WordAlign(word=str(r["word"]), start=float(r["start"]), end=float(r["end"]))
        for r in rows
    ]


def parse_field_log(
    path: str | Path | None = None, records: list[dict] | None = None
) -> list[FieldEvent]:
    """Parse the field timing log (JSONL {t_mono, text, ...}) into FieldEvents.

    Accepts a path OR pre-parsed dicts (the lab drains JSONL incrementally and
    hands dicts here — the file-never-touched rule keeps the engine testable).
    t is the field's own time.monotonic() (seconds).
    """
    if records is None:
        lines = Path(path or "").read_text(encoding="utf-8").splitlines()
        records = [json.loads(ln) for ln in lines if ln.strip()]
    return [
        FieldEvent(
            t=float(r["t_mono"]),
            text=str(r.get("text", "")),
            kind=str(r.get("kind", "")),
        )
        for r in records
    ]


# --- visibility resolution (the heart of the speech clock) ---------------------


def resolve_visibility(
    words: list[WordAlign],
    field_events: list[FieldEvent],
    anchor: int = 0,
    window_fwd: int = 12,
    window_back: int = 24,
) -> list[float | None]:
    """Per-word FIRST-visible monotonic ts (None = never visible → a miss).

    Longest-prefix positional match (research §9): at each field event, find
    the contiguous block of reference words inside the event's normalized
    tokens that extends the matched frontier FURTHEST, where the block may
    re-anchor at or before the frontier (corrections retract) and must occur
    at token position >= `anchor` (this replay renders at/after the text the
    field already held — a previous replay's identical words sit at positions
    < anchor and can never match). A word visible only in a LATER corrected
    hypothesis keeps its FIRST appearance time (seen[] is write-once).

    BOUNDED SCAN: reference word s renders at token ≥ anchor+s−window_back
    (in-order render, minus the shrinkage a correction leaves behind — a
    replaced span can render the following words up to window_back tokens
    earlier), and a block whose start lies > anchor+frontier+window_fwd
    tokens past the expected frontier is beyond the hallucination tolerance —
    such words stay honestly unmatched. This keeps the scan O(frontier × fwd)
    per event across long accumulating field texts (20 replays ≈ 1k tokens).
    """
    n = len(words)
    norms = [normalize_token(w.word) for w in words]
    seen: list[float | None] = [None] * n
    frontier = 0  # reference words matched so far (may regress on re-anchor)
    for ev in field_events:
        toks = normalize_tokens(ev.text)
        # (A) longest contiguous block of reference words inside the event's
        # tokens: any start ≤ frontier (corrections may re-anchor earlier),
        # token position ≥ anchor (the previous replay's copy sits < anchor).
        best_start, best_end, best_pos = frontier, frontier, None
        exp = anchor + frontier  # where the next reference word should render
        pos_hi = min(len(toks) - 1, exp + window_fwd)
        for start in range(0, min(frontier + 1, n)):
            if not norms[start]:
                continue
            pos_lo = max(anchor, anchor + start - window_back)
            for pos in range(pos_lo, pos_hi + 1):
                k = 0
                while (
                    start + k < n
                    and pos + k < len(toks)
                    and norms[start + k]
                    and toks[pos + k] == norms[start + k]
                ):
                    k += 1
                if k > 0 and start + k > best_end:
                    best_start, best_end, best_pos = start, start + k, pos
        if best_pos is not None:
            for i in range(best_start, best_end):
                if seen[i] is None:
                    seen[i] = ev.t
            frontier = max(frontier, best_end)
            ti = best_pos + (best_end - best_start)
            ri = best_end
        else:
            ti = anchor
            ri = frontier
        # (B) substitution rescue: ONE misrecognized reference word must not
        # strand every later word into misses — if the token after the failed
        # position matches the NEXT reference word, credit that word (the
        # substituted one stays unseen = an honest single miss).
        while ti < len(toks) and ri < n:
            if toks[ti] == norms[ri]:
                if seen[ri] is None:
                    seen[ri] = ev.t
                ri += 1
                ti += 1
            elif ri + 1 < n and toks[ti] == norms[ri + 1]:
                if seen[ri + 1] is None:
                    seen[ri + 1] = ev.t
                ri += 2
                ti += 1
            else:
                ti += 1
        frontier = max(frontier, ri)
    return seen


def classify_pair(old: str, new: str) -> str:
    """Insertion = new extends old at the cursor; correction = anything else
    (retraction, mid-string change, shrink) — from the FIELD log's old→new
    pair, never from controller intent (Gotcha #6)."""
    if len(new) > len(old) and new.startswith(old):
        return "insert"
    return "correct"


def classify_events(field_events: list[FieldEvent]) -> list[tuple[FieldEvent, str]]:
    """Pairwise classification of consecutive field texts (cross-check view)."""
    out: list[tuple[FieldEvent, str]] = []
    prev = ""
    for ev in field_events:
        if ev.text != prev:
            out.append((ev, classify_pair(prev, ev.text)))
        prev = ev.text
    return out


# --- per-replay metric kernels -------------------------------------------------


def speech_to_visible(
    words: list[WordAlign], visibility: list[float | None], feed_start: float
) -> tuple[list[float], list[int]]:
    """speech-end→visible samples in ms + the indexes of never-visible words.

    Misses NEVER enter the sample list (Gotcha #7): they are returned apart
    and only ever appear in the misses column.
    """
    samples: list[float] = []
    misses: list[int] = []
    for i, w in enumerate(words):
        ts = visibility[i]
        if ts is None:
            misses.append(i)
        else:
            samples.append((ts - (feed_start + w.end)) * 1000.0)
    return samples, misses


def ready_to_frame(
    update_ready: list[tuple[float, str, str]], field_events: list[FieldEvent]
) -> tuple[list[FrameSample], int]:
    """Pair each update dispatch with its first CHANGED frame; classify it.

    A update's window runs from its dispatch ts to the next dispatch ts. The
    frame is the first field event in the window whose text differs from the
    rendered text just before the window. An IDENTICAL update (text == the
    previous update's text) must produce ZERO changed frames (the zero-diff
    law); a changed frame inside an identical-update window is a violation
    (returned as the second tuple element's count).
    """
    out: list[FrameSample] = []
    violations = 0
    ei = 0  # rolling cursor over field_events (sorted by t)
    for i, (ts, text, _kind) in enumerate(update_ready):
        nxt = update_ready[i + 1][0] if i + 1 < len(update_ready) else math.inf
        prev_text = ""
        # advance ei to the last event at or before ts
        while ei < len(field_events) and field_events[ei].t <= ts:
            prev_text = field_events[ei].text
            ei += 1
        j = ei
        first_change: FieldEvent | None = None
        while j < len(field_events) and field_events[j].t < nxt:
            if field_events[j].text != prev_text:
                first_change = field_events[j]
                break
            j += 1
        identical = i > 0 and text == update_ready[i - 1][1]
        if identical:
            if first_change is not None:
                violations += 1
            # rewind nothing: ei stays at win_start (events in the window are
            # re-scanned by the NEXT update if it starts inside this one)
            continue
        if first_change is not None:
            out.append(
                FrameSample(
                    (first_change.t - ts) * 1000.0,
                    classify_pair(prev_text, first_change.text),
                )
            )
    return out, violations


def outstanding_series(
    words: list[WordAlign],
    visibility: list[float | None],
    feed_start: float,
    field_events: list[FieldEvent],
) -> tuple[int, bool]:
    """Max words outstanding + the ≥SUSTAIN_WORDS-for-≥SUSTAIN_WINDOW_S flag.

    Outstanding = words whose aligned speech-end has passed − words visible.
    Sampled at EVERY word speech-end and EVERY field event (the value is
    piecewise-constant between those points, so samples fully determine it).
    A run of consecutive samples ≥ SUSTAIN_WORDS spanning ≥ SUSTAIN_WINDOW_S
    of wall clock means the backlog was SUSTAINED (Gotcha #8 ⇒ route FAIL).
    """
    ends = sorted(feed_start + w.end for w in words)
    vis = sorted(t for t in visibility if t is not None)
    # NO rounding: stamps must compare equal to the raw end/visibility values
    # (a rounded stamp sorts BEFORE its unrounded source and bisect misses it).
    stamps = sorted(set(ends) | {ev.t for ev in field_events})
    max_out = 0
    sustained = False
    run_start: float | None = None
    prev_t: float | None = None
    for t in stamps:
        spoken = bisect_right(ends, t)
        visible = bisect_right(vis, t)
        out = spoken - visible
        if out > max_out:
            max_out = out
        if out >= SUSTAIN_WORDS:
            if run_start is None:
                run_start = t  # the value crosses AT a sample, never between
        else:
            # the ≥SUSTAIN_WORDS value HELD from run_start until THIS drop
            if run_start is not None and t - run_start >= SUSTAIN_WINDOW_S:
                sustained = True
            run_start = None
        prev_t = t
    if (
        run_start is not None
        and prev_t is not None
        and prev_t - run_start >= SUSTAIN_WINDOW_S
    ):
        sustained = True  # still held at the last observed sample
    return max_out, sustained


def split_utterances(words: list[WordAlign]) -> list[list[int]]:
    """Utterances = reference word runs split at ≥UTTERANCE_GAP_S alignment gaps."""
    utts: list[list[int]] = []
    cur: list[int] = []
    for i, w in enumerate(words):
        if cur and (w.start - words[cur[-1]].end) >= UTTERANCE_GAP_S:
            utts.append(cur)
            cur = []
        cur.append(i)
    if cur:
        utts.append(cur)
    return utts


def sentence_end_dump(
    words: list[WordAlign],
    visibility: list[float | None],
    finals_ts: list[float],
    feed_start: float,
) -> bool:
    """True when any ≥DUMP_MIN_WORDS utterance landed as one final dump.

    Dump = < 2 of the utterance's words visible strictly before its
    finalize-class event (the first final dispatch at/after the utterance's
    last aligned speech-end). Gotcha #8: this fails the route regardless of
    medians.
    """
    finals = sorted(finals_ts)
    for utt in split_utterances(words):
        if len(utt) < DUMP_MIN_WORDS or not finals:
            continue
        last_end = feed_start + words[utt[-1]].end
        fin = next((t for t in finals if t >= last_end), None)
        if fin is None:
            continue  # never finalized — misses/shortfall territory, not a dump
        pre = sum(1 for i in utt if visibility[i] is not None and visibility[i] < fin)
        if pre <= DUMP_MAX_PRE_FINALIZE:
            return True
    return False


# --- clock sanity (Gotcha #4) ---------------------------------------------------


def heartbeat_ok(pairs: list[tuple[float, float]], tol_s: float = 0.25) -> bool:
    """(monotonic, wall) pairs from one participant agree pairwise within tol.

    Catches accidental clock-source mixing: CLOCK_MONOTONIC shares one epoch
    across processes on this host, so pairwise deltas must track wall deltas.
    """
    if len(pairs) < 2:
        return True
    ps = sorted(pairs)
    for (m0, w0), (m1, w1) in zip(ps, ps[1:]):
        if abs((m1 - m0) - (w1 - w0)) > tol_s:
            return False
    return True


# --- aggregation (failures accumulate; medians never veto them) -----------------


def _median(samples: list[float]) -> float | None:
    return statistics.median(samples) if samples else None


def _p95(samples: list[float]) -> float | None:
    """Nearest-rank p95 (deterministic; n=100 → the 95th sorted value)."""
    if not samples:
        return None
    s = sorted(samples)
    rank = max(1, math.ceil(0.95 * len(s)))
    return s[min(len(s) - 1, rank - 1)]


def aggregate(records: list[ReplayRecord], route: str = "") -> RouteMetrics:
    """Fold measured replays into one RouteMetrics + honest verdict."""
    m = RouteMetrics(
        route=route or (records[0].route if records else ""), replays=len(records)
    )
    all_samples: list[float] = []
    ready_insert: list[float] = []
    ready_correct: list[float] = []
    for r in records:
        vis = resolve_visibility(r.words, r.field_events, anchor=r.anchor)
        samples, misses = speech_to_visible(r.words, vis, r.feed_start)
        all_samples.extend(samples)
        m.misses += len(misses)
        pairs, violations = ready_to_frame(r.update_ready, r.field_events)
        for p in pairs:
            if p.cls == "insert":
                m.insertions += 1
                ready_insert.append(p.delta_ms)
            else:
                m.corrections += 1
                ready_correct.append(p.delta_ms)
        if violations:
            m.unchanged_zero_edit_ok = False
        max_out, sustained = outstanding_series(
            r.words, vis, r.feed_start, r.field_events
        )
        m.max_words_outstanding = max(m.max_words_outstanding, max_out)
        m.backlog_sustained = m.backlog_sustained or sustained
        m.sentence_end_dump = m.sentence_end_dump or sentence_end_dump(
            r.words, vis, r.finals_ts, r.feed_start
        )
    m.speech_to_visible_med_ms = _median(all_samples)
    m.speech_to_visible_p95_ms = _p95(all_samples)
    m.worst_gap_ms = max(all_samples) if all_samples else None
    m.ready_p95_insert_ms = _p95(ready_insert)
    m.ready_p95_correct_ms = _p95(ready_correct)

    failures: list[str] = []
    med = m.speech_to_visible_med_ms
    if med is None or med > SPEECH_MED_MS:
        failures.append(f"speech→visible median {med} ms > {SPEECH_MED_MS} ms")
    p95 = m.speech_to_visible_p95_ms
    if p95 is None or p95 >= SPEECH_P95_MS:
        failures.append(f"speech→visible p95 {p95} ms >= {SPEECH_P95_MS} ms")
    if m.ready_p95_insert_ms is None or m.ready_p95_insert_ms > READY_P95_INSERT_MS:
        failures.append(
            f"ready→frame insertion p95 {m.ready_p95_insert_ms} ms > {READY_P95_INSERT_MS} ms"
        )
    if m.ready_p95_correct_ms is None or m.ready_p95_correct_ms > READY_P95_CORRECT_MS:
        failures.append(
            f"ready→frame correction p95 {m.ready_p95_correct_ms} ms > {READY_P95_CORRECT_MS} ms"
        )
    if m.backlog_sustained:
        failures.append(
            f"backlog ≥{SUSTAIN_WORDS} words sustained ≥{SUSTAIN_WINDOW_S} s "
            f"(max outstanding {m.max_words_outstanding})"
        )
    if m.sentence_end_dump:
        failures.append("sentence-end dump (an utterance delivered as one final edit)")
    if m.insertions < MIN_COUNT or m.corrections < MIN_COUNT:
        failures.append(
            f"counts {m.insertions}/{m.corrections} < {MIN_COUNT} after replay budget"
        )
    if not m.unchanged_zero_edit_ok:
        failures.append("zero-diff violation: unchanged update produced a field change")
    m.failures = failures
    m.verdict = "pass" if not failures else "fail"
    return m


# --- bounded rendering ----------------------------------------------------------

MAX_REPORT_LINES = 120


def render_report_row(m: RouteMetrics) -> str:
    """ONE compact JSON verdict line (the durable artifact row; bounded)."""
    d = {
        "route": m.route,
        "verdict": m.verdict,
        "insertions": m.insertions,
        "corrections": m.corrections,
        "misses": m.misses,
        "speech_med_ms": round(m.speech_to_visible_med_ms, 1)
        if m.speech_to_visible_med_ms is not None
        else None,
        "speech_p95_ms": round(m.speech_to_visible_p95_ms, 1)
        if m.speech_to_visible_p95_ms is not None
        else None,
        "worst_gap_ms": round(m.worst_gap_ms, 1)
        if m.worst_gap_ms is not None
        else None,
        "ready_insert_p95_ms": round(m.ready_p95_insert_ms, 1)
        if m.ready_p95_insert_ms is not None
        else None,
        "ready_correct_p95_ms": round(m.ready_p95_correct_ms, 1)
        if m.ready_p95_correct_ms is not None
        else None,
        "max_words_outstanding": m.max_words_outstanding,
        "backlog_sustained": m.backlog_sustained,
        "sentence_end_dump": m.sentence_end_dump,
        "unchanged_zero_edit_ok": m.unchanged_zero_edit_ok,
        "replays": m.replays,
        "failures": m.failures,
    }
    return json.dumps(d, ensure_ascii=False)


def render_markdown(metrics: list[RouteMetrics], meta: dict) -> str:
    """The bounded evidence-report fragment (G1_BASELINE/D1_DUCK tone).

    meta: {date, head, command, provenance: {gpu, model, compute_type, versions...}}
    Honest labels only: pass | fail(reason) | blocked(reason) — a lab that
    never ran is 'not run', never 'passed' (the report consumer's rule).
    """
    lines: list[str] = [
        f"- Date: {meta.get('date', 'unknown')}  |  HEAD: {meta.get('head', 'unknown')}",
        f"- Command: `{meta.get('command', 'n/a')}`",
    ]
    for k, v in (meta.get("provenance") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append(
        "| route | verdict | ins | cor | miss | speech med/p95 ms | worst ms | ready ins/cor p95 ms | max out | flags |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for m in metrics:
        flags = []
        if m.backlog_sustained:
            flags.append("backlog-sustained")
        if m.sentence_end_dump:
            flags.append("dump")
        if not m.unchanged_zero_edit_ok:
            flags.append("zero-diff")
        med = (
            "-"
            if m.speech_to_visible_med_ms is None
            else f"{m.speech_to_visible_med_ms:.0f}/{m.speech_to_visible_p95_ms:.0f}"
        )
        worst = "-" if m.worst_gap_ms is None else f"{m.worst_gap_ms:.0f}"
        ri = "-" if m.ready_p95_insert_ms is None else f"{m.ready_p95_insert_ms:.0f}"
        rc = "-" if m.ready_p95_correct_ms is None else f"{m.ready_p95_correct_ms:.0f}"
        lines.append(
            f"| {m.route} | {m.verdict} | {m.insertions} | {m.corrections} | {m.misses} "
            f"| {med} | {worst} | {ri}/{rc} | {m.max_words_outstanding} "
            f"| {', '.join(flags) or '—'} |"
        )
    for m in metrics:
        if m.failures:
            lines.append("")
            lines.append(f"### {m.route} failure register")
            for f_ in m.failures:
                lines.append(f"- {f_}")
    return "\n".join(lines[:MAX_REPORT_LINES])

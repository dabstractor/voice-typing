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

P1.M2.T1.S3 (changed-span attribution): update observations are labeled
(matched / missing / superseded / no_op / ambiguous; orphan frames counted as
unpaired) by `attribute_updates` — a frame charges to the OLDEST PENDING
update by changed-span content, never by callback-window ownership. Word
visibility aligns changed spans against independent field snapshots
(`resolve_visibility_detailed`; `resolve_visibility` is exactly its .ts
projection). Pure stdlib; no voice_typing imports; a target ACK (ack_ts) is
a cross-check, never a frame (R.5 #3).
"""

from __future__ import annotations

import difflib
import json
import math
import re
import statistics
import unicodedata
from bisect import bisect_right
from collections import Counter
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
class ReadyEvent:
    """One update-ready checkpoint, coerced losslessly from legacy tuples.

    The legacy shape is (t, text, kind); every further field is defaulted so
    tuple-based callers keep working untouched (P1.M2.T1.S3 contract):
      - stage: "producer" stamps arrive before IPC — a separate checkpoint,
        never mixed into daemon-stage frame pairing (R.7);
      - gen/utt/seq: relay identity where available (recorder_host _RelayIds
        + daemon _bulk_next_seq); match/supersede by it when present;
      - disposition: controller fate ("" | "dispatched" | "coalesced" |
        "dropped" | "replaced") where recorded;
      - ack_ts: target APPLIED cross-check ONLY — never a frame (R.5 #3)."""

    t: float  # monotonic dispatch/checkpoint ts
    text: str  # full rendered text the update announces
    kind: str  # "partial" | "final"
    stage: str = "daemon"
    gen: int | None = None
    utt: int | None = None
    seq: int | None = None
    disposition: str = ""
    ack_ts: float | None = None


@dataclass
class ReplayRecord:
    """One measured replay (warmup replays are discarded before any record).

    S3 provenance (all defaulted — every existing constructor stays valid):
    partial_source echoes S1's installed-callback provenance for the S6 A/B;
    anchor_text seeds the span diffs with the pre-replay field state; capped
    flags a field-log cap hit; heartbeats carry (monotonic, wall) pairs for
    the clock sanity cross-check."""

    route: str
    clip: str
    feed_start: float  # pacer's time.monotonic() when audio-time 0 hit the queue
    words: list[WordAlign]
    field_events: list[FieldEvent]  # THIS replay's slice of the field log
    update_ready: list[tuple[float, str, str]] | list[ReadyEvent]
    finals_ts: list[float] = field(default_factory=list)  # final dispatch times
    anchor: int = 0  # normalized-token count of the field text at replay start
    partial_source: str = ""  # installed partial-source provenance (S1; S6 A/B)
    anchor_text: str = ""  # field text at replay start (seed for span diffs)
    capped: bool = False  # field log hit its deque cap (frames may be lost)
    heartbeats: list[tuple[float, float]] = field(default_factory=list)  # (mono, wall)


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
    # --- changed-span attribution counters (S3; additive, all default 0) ----
    updates_total: int = 0
    updates_matched: int = 0
    updates_missing: int = 0
    updates_superseded: int = 0
    updates_no_op: int = 0
    updates_ambiguous: int = 0
    frames_unpaired: int = 0
    words_ambiguous: int = 0
    clock_failures: int = 0
    cap_failures: int = 0
    # Reported evidence (clock/cap failures etc.): never averaged away and
    # never imputed as a pass, but NOT in `failures` — a clock/cap flag alone
    # does not flip the verdict; the miss/count floors handle lost samples.
    provenance_warnings: list[str] = field(default_factory=list)


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


@dataclass
class AddedSpan:
    """One added/replaced token region between two consecutive field snapshots.

    `pos` is the region's token position in the NEW snapshot's normalized
    token list; `tokens` are its normalized tokens. Pre-existing text never
    appears in a span — that is how initial anchored text is distinguished
    from new insertions (P1.M2.T1.S3)."""

    pos: int
    tokens: list[str]


def changed_spans(old_text: str, new_text: str) -> list[AddedSpan]:
    """The added/replaced regions between two INDEPENDENT field snapshots.

    Pure-stdlib diff over normalize_tokens lists (difflib.SequenceMatcher,
    autojunk off so frequent words stay in the matching space). Deletions
    produce NO span (removed content is not an addition); a raw text change
    whose normalized tokens are identical produces no spans at all.
    Deterministic: the same (old, new) pair always yields the same spans."""
    old_toks = normalize_tokens(old_text)
    new_toks = normalize_tokens(new_text)
    if old_toks == new_toks:
        return []
    sm = difflib.SequenceMatcher(a=old_toks, b=new_toks, autojunk=False)
    return [
        AddedSpan(pos=j1, tokens=new_toks[j1:j2])
        for tag, _i1, _i2, j1, j2 in sm.get_opcodes()
        if tag in ("insert", "replace") and j2 > j1
    ]


@dataclass
class VisibilityResult:
    """Span-aware first-visibility result (P1.M2.T1.S3).

    `.ts` is EXACTLY the historical resolve_visibility return (per-word
    first-visible monotonic ts; None = never visible → a miss).
    `.ambiguous` lists reference words whose appearance was genuinely
    indeterminate at some event — the same normalized token added in multiple
    DISTINCT AddedSpans of one snapshot — counted (`words_ambiguous`), never
    guessed; such words stay eligible for later, unambiguous evidence (seen
    is write-once, so a later resolution records that later ts)."""

    ts: list[float | None]
    ambiguous: list[int] = field(default_factory=list)


def _span_occurrences(spans: list[AddedSpan]) -> dict[str, list[tuple[int, int]]]:
    """Token → [(span index, absolute token position), ...] in event order."""
    occ: dict[str, list[tuple[int, int]]] = {}
    for si, span in enumerate(spans):
        for k, tok in enumerate(span.tokens):
            occ.setdefault(tok, []).append((si, span.pos + k))
    return occ


def resolve_visibility_detailed(
    words: list[WordAlign],
    field_events: list[FieldEvent],
    anchor: int = 0,
    anchor_text: str = "",
    window_fwd: int = 12,
    window_back: int = 24,
) -> VisibilityResult:
    """Per-word FIRST visibility by changed-span alignment (P1.M2.T1.S3).

    Replaces the positional contiguous-block matcher (which assumed words
    keep their token positions and could overstate Pi delay on rewrites).
    Per event, the added regions are computed against the PREVIOUS snapshot —
    the rolling snapshot is seeded with `anchor_text`, never "" (a previous
    state can no longer be lost) — and a reference word becomes first-visible
    when its normalized token appears in an AddedSpan at an ELIGIBLE position:

      - position floor: token position >= `anchor` (this replay renders
        at/after the text the field already held — a previous replay's copy
        sits below the floor and can never match);
      - bounded window: anchor + i - window_back <= pos <=
        anchor + i + window_fwd (a rewrite can render following words up to
        window_back tokens early; positions beyond the hallucination
        tolerance stay honestly unmatched). The scan stays O(words × window)
        per event across long accumulating field texts.

    WRITE-ONCE: a retraction, repeat or reset never un-sees a word and never
    overwrites its first ts. RESETS: an event whose text reverts to/below the
    anchor baseline (normalized token count <= the baseline's) is skipped —
    no phantom visibility, no phantom misses; re-added copies after a reset
    are matched by ordered position within the bounded window else marked
    ambiguous. REPEATS: within one span the earliest eligible position takes
    the earliest unseen reference word (ordered resolution); the same token
    added in multiple DISTINCT spans of one event is genuinely indeterminate
    → all its unseen candidate words are marked ambiguous (counted, no
    guessed ts)."""
    n = len(words)
    norms = [normalize_token(w.word) for w in words]
    seen: list[float | None] = [None] * n
    ambiguous: set[int] = set()
    baseline = normalize_tokens(anchor_text)
    baseline_len = len(baseline) if anchor_text else anchor
    prev_text = anchor_text  # rolling previous snapshot — seeded, never lost
    for ev in field_events:
        reset = len(normalize_tokens(ev.text)) <= baseline_len
        if not reset and n:
            for tok, occ in _span_occurrences(changed_spans(prev_text, ev.text)).items():
                cand_words = [i for i in range(n) if seen[i] is None and norms[i] == tok]
                if not cand_words:
                    continue
                eligible = [
                    (si, p)
                    for si, p in occ
                    if p >= anchor
                    and any(
                        anchor + i - window_back <= p <= anchor + i + window_fwd
                        for i in cand_words
                    )
                ]
                if len({si for si, _p in eligible}) >= 2:
                    ambiguous.update(cand_words)  # multi-span repeat: no guess
                    continue
                for _si, p in sorted(eligible, key=lambda sp: sp[1]):
                    for i in cand_words:
                        if (
                            seen[i] is None
                            and anchor + i - window_back <= p <= anchor + i + window_fwd
                        ):
                            seen[i] = ev.t
                            break
        prev_text = ev.text
    return VisibilityResult(ts=seen, ambiguous=sorted(ambiguous))


def resolve_visibility(
    words: list[WordAlign],
    field_events: list[FieldEvent],
    anchor: int = 0,
    window_fwd: int = 12,
    window_back: int = 24,
) -> list[float | None]:
    """Per-word FIRST-visible monotonic ts (None = never visible → a miss).

    Historical entry point; EXACTLY the `.ts` projection of
    `resolve_visibility_detailed` — the two cannot drift. See that function
    for the changed-span alignment contract (write-once first appearance,
    anchor floor, bounded window_fwd/window_back scan, reset handling,
    ordered-or-ambiguous repeats)."""
    return resolve_visibility_detailed(
        words, field_events, anchor=anchor, window_fwd=window_fwd, window_back=window_back
    ).ts


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


# --- update attribution: changed-span matching (P1.M2.T1.S3) -------------------

SUPERSEDE_DISPOSITIONS = frozenset({"coalesced", "dropped", "replaced"})


@dataclass
class Observation:
    """Calibrated label for ONE ReadyEvent (one observation per event).

    label: matched | missing | superseded | no_op | ambiguous. `frame_ts` is
    the first attributable changed-frame ts (matched only). `detail` carries
    the calibrated why — e.g. "disposition='coalesced'...", "subsumed by ..."
    or a producer→daemon relay delta — so downstream consumers (S4/S6/T2.S3)
    can distinguish lost-during-coalescing from late-upstream-partial from
    late-field-visibility."""

    index: int
    label: str
    frame_ts: float | None = None
    detail: str = ""


@dataclass
class AttributionResult:
    """attribute_updates' result: per-event observations + counters + the
    historical (FrameSample, violations) projection (what ready_to_frame
    returns — a thin projection of this, so the two cannot drift)."""

    observations: list[Observation]
    frames_unpaired: int
    samples: list[FrameSample] = field(default_factory=list)
    violations: int = 0


@dataclass
class _ChangedFrame:
    """One changed frame: a field snapshot differing from the previous one."""

    t: float
    text: str
    prev_text: str
    spans: list[AddedSpan]
    normalized_equal: bool  # raw change, identical rendered content (phantom)

    @property
    def added(self) -> list[str]:
        """The frame's added normalized tokens, in span/position order."""
        return [tok for span in self.spans for tok in span.tokens]


def _to_ready_events(update_ready) -> list[ReadyEvent]:
    """Coerce update stamps to ReadyEvents — total and lossless for the legacy
    (ts, text, kind) tuple shape; ReadyEvent instances pass through."""
    out: list[ReadyEvent] = []
    for u in update_ready:
        if isinstance(u, ReadyEvent):
            out.append(u)
        else:
            t, text, kind = u
            out.append(ReadyEvent(t=float(t), text=str(text), kind=str(kind)))
    return out


def _changed_frames(
    field_events: list[FieldEvent], anchor_text: str = ""
) -> list[_ChangedFrame]:
    """The changed-frame series: consecutive INDEPENDENT field snapshots.

    The rolling previous snapshot is seeded with `anchor_text` (NOT "") so the
    pre-replay field state is never lost; `a.text != b.text` (raw) makes a
    frame at b.t carrying its AddedSpans plus a normalized-equal flag (a raw
    change with identical rendered content is a phantom — zero-diff evidence)."""
    frames: list[_ChangedFrame] = []
    prev_text = anchor_text
    for ev in field_events:
        if ev.text != prev_text:
            frames.append(
                _ChangedFrame(
                    t=ev.t,
                    text=ev.text,
                    prev_text=prev_text,
                    spans=changed_spans(prev_text, ev.text),
                    normalized_equal=normalize_tokens(prev_text)
                    == normalize_tokens(ev.text),
                )
            )
            prev_text = ev.text
    return frames


def _expected_added(norm_tokens: list[str], observed: Counter) -> list[str]:
    """An update's expected ADDED content: its normalized tokens MINUS the
    multiset already observed in the field at its dispatch (order-preserving),
    so append-only and rewrite routes reduce to the same comparison space."""
    have = Counter(observed)
    out: list[str] = []
    for tok in norm_tokens:
        if have[tok] > 0:
            have[tok] -= 1
        else:
            out.append(tok)
    return out


def attribute_updates(
    update_ready: list[tuple[float, str, str]] | list[ReadyEvent],
    field_events: list[FieldEvent],
    anchor_text: str = "",
) -> AttributionResult:
    """Label every update-ready checkpoint against the field's changed frames.

    Core rule (P1.M2.T1.S3): a changed frame is charged to the OLDEST PENDING
    update whose expected added content matches the frame's AddedSpans —
    content matching over normalized tokens, NOT [ts, next-ts) window
    ownership. "Pending" = dispatched (daemon stage), not yet matched and not
    superseded. Consequences that are TESTED rules, not comments:

      - a late frame lands on its true (older) update; a newer identical
        callback ends no_op with NO zero-diff violation (the delayed-frame
        carve-out: a frame matching an older pending span is never billed to
        the newer identical callback);
      - a burst's single frame may satisfy several pending updates whose
        combined spans it paints (all matched, one frame ts);
      - the same token added in multiple distinct spans of one frame while
        ≥2 pending updates match is genuinely inseparable → all charged
        updates are `ambiguous` (counted, excluded from latency samples).

    Labels: matched (frame charged; one FrameSample per matched update) /
    missing (dispatched, never painted; NEVER a zero-latency sample) /
    superseded (controller disposition coalesced|dropped|replaced, or — only
    when (gen,utt) identity is present — a later same-identity update whose
    text subsumes the older's expected added content as a proper normalized
    prefix; the coalesced-away update is superseded, NOT missing) / no_op
    (expected added content empty or fully contained in the final observed
    state — nothing new was required; a phantom frame while it watches is a
    zero-diff violation) / ambiguous. A pure retraction frame paints the
    oldest pending update whose text equals the rendered result. A changed
    frame no pending update claims is counted `frames_unpaired` (before the
    first update or after all settled) — never a fast sample.

    Producer-stage events are a separate checkpoint (R.7): they never enter
    the frame-pairing queue; each is paired to its daemon twin by (gen,utt,
    seq) and carries the producer→daemon relay delta in `detail`; an unpaired
    producer event is a relay loss (missing). ack_ts is recorded on the event
    for cross-checks and is NEVER a frame. Legacy (ts,text,kind) tuples are
    coerced losslessly, so legacy streams behave exactly as before."""
    evs = _to_ready_events(update_ready)
    n = len(evs)
    observations: list[Observation | None] = [None] * n
    queue: list[int] = []  # daemon-stage updates eligible to pair frames
    for i, e in enumerate(evs):
        if e.stage == "producer":
            continue  # separate checkpoint — paired to its daemon twin below
        if e.disposition in SUPERSEDE_DISPOSITIONS:
            observations[i] = Observation(
                i,
                "superseded",
                detail=f"disposition={e.disposition!r}: never required to paint",
            )
            continue
        queue.append(i)
    frames = _changed_frames(field_events, anchor_text)

    def observed_tokens_at(ts: float) -> list[str]:
        prev = anchor_text
        for f in frames:
            if f.t > ts:
                break
            prev = f.text
        return normalize_tokens(prev)

    expected = {
        u: _expected_added(
            normalize_tokens(evs[u].text), Counter(observed_tokens_at(evs[u].t))
        )
        for u in queue
    }

    labels: dict[int, str] = {}
    samples: list[FrameSample] = []
    violations = 0
    frames_unpaired = 0
    for f in frames:
        added = f.added
        tok_spans: dict[str, set[int]] = {}
        for si, span in enumerate(f.spans):
            for tok in span.tokens:
                tok_spans.setdefault(tok, set()).add(si)
        multi_span_dup = any(len(sset) >= 2 for sset in tok_spans.values())
        # charge pass: oldest-pending chain over the frame's added tokens
        charged: list[int] = []
        rem = added
        for u in queue:
            if u in labels or not rem or evs[u].t > f.t:
                continue
            e_u = expected[u]
            if not e_u or rem[: len(e_u)] != e_u:
                continue
            charged.append(u)
            rem = rem[len(e_u):]
        if charged and multi_span_dup and len(charged) >= 2:
            for u in charged:
                labels[u] = "ambiguous"
                observations[u] = Observation(
                    u,
                    "ambiguous",
                    frame_ts=None,
                    detail="repeat paint across multiple added spans: latency not guessed",
                )
            continue
        if charged:
            for u in charged:
                labels[u] = "matched"
                observations[u] = Observation(u, "matched", frame_ts=f.t)
                samples.append(
                    FrameSample(
                        (f.t - evs[u].t) * 1000.0,
                        classify_pair(f.prev_text, f.text),
                    )
                )
            continue
        if not added:
            if f.normalized_equal:
                # phantom frame (raw change, identical content): a zero-diff
                # violation of the oldest dispatched no-op announcement
                blame = next(
                    (
                        u
                        for u in queue
                        if u not in labels and not expected[u] and evs[u].t <= f.t
                    ),
                    None,
                )
                if blame is not None:
                    violations += 1
                else:
                    frames_unpaired += 1
            else:
                # pure retraction/deletion: paints the oldest pending update
                # whose text equals the rendered result
                tgt = next(
                    (
                        u
                        for u in queue
                        if u not in labels
                        and evs[u].t <= f.t
                        and normalize_tokens(evs[u].text) == normalize_tokens(f.text)
                    ),
                    None,
                )
                if tgt is not None:
                    labels[tgt] = "matched"
                    observations[tgt] = Observation(
                        tgt, "matched", frame_ts=f.t, detail="retraction paint"
                    )
                    samples.append(
                        FrameSample(
                            (f.t - evs[tgt].t) * 1000.0,
                            classify_pair(f.prev_text, f.text),
                        )
                    )
                else:
                    frames_unpaired += 1
        else:
            frames_unpaired += 1  # no attributable pending update: counted only

    final_counter = Counter(
        normalize_tokens(field_events[-1].text) if field_events else anchor_text
    )
    for pos, u in enumerate(queue):
        if u in labels:
            continue
        e_u = expected[u]
        sup = None
        if evs[u].gen is not None and evs[u].utt is not None:
            for v in queue[pos + 1:]:
                if v in labels:
                    continue
                if evs[v].gen == evs[u].gen and evs[v].utt == evs[u].utt:
                    v_toks = normalize_tokens(evs[v].text)
                    if e_u and v_toks[: len(e_u)] == e_u and len(v_toks) > len(e_u):
                        sup = v
                        break
        if sup is not None:
            observations[u] = Observation(
                u, "superseded", detail=f"subsumed by update {sup} (prefix)"
            )
        elif not e_u or Counter(e_u) <= final_counter:
            observations[u] = Observation(
                u,
                "no_op",
                detail=(
                    "nothing new over the observed field state"
                    if not e_u
                    else "content painted via an older pending update"
                ),
            )
        else:
            observations[u] = Observation(
                u,
                "missing",
                detail="dispatched; no matching field change before end of record",
            )

    # producer-stage events: pair to the daemon twin by (gen,utt,seq)
    for i, e in enumerate(evs):
        if observations[i] is not None:
            continue
        twin = None
        if e.gen is not None and e.utt is not None and e.seq is not None:
            for v, ev2 in enumerate(evs):
                if (
                    v != i
                    and ev2.stage != "producer"
                    and ev2.gen == e.gen
                    and ev2.utt == e.utt
                    and ev2.seq == e.seq
                ):
                    twin = v
                    break
        if twin is not None:
            twin_obs = observations[twin]
            relay_ms = (evs[twin].t - e.t) * 1000.0
            observations[i] = Observation(
                i,
                twin_obs.label if twin_obs is not None else "missing",
                frame_ts=None,
                detail=(
                    f"producer checkpoint seq={e.seq}; "
                    f"relay to daemon receipt {relay_ms:+.0f} ms"
                ),
            )
        else:
            observations[i] = Observation(
                i,
                "missing",
                frame_ts=None,
                detail="producer-stage event never reached the daemon (relay loss)",
            )
    return AttributionResult(
        observations=[obs for obs in observations if obs is not None],
        frames_unpaired=frames_unpaired,
        samples=samples,
        violations=violations,
    )


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
    update_ready: list[tuple[float, str, str]] | list[ReadyEvent],
    field_events: list[FieldEvent],
    anchor_text: str = "",
) -> tuple[list[FrameSample], int]:
    """Pair each update dispatch with its first CHANGED frame; classify it.

    Historical entry point; a THIN projection of
    `attribute_updates(...).samples/.violations` — the two cannot drift, and
    every case the existing tests define returns identical results. The
    pairing is oldest-pending changed-span matching (not window ownership):
    a late frame charges its true (older) update, and a newer identical
    callback produces zero frames unless a changed frame is genuinely
    attributable to it (the zero-diff law, with the delayed-frame carve-out).
    `anchor_text` seeds the frame-series diff like the replay's own seed."""
    attr = attribute_updates(update_ready, field_events, anchor_text=anchor_text)
    return attr.samples, attr.violations


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
    """Fold measured replays into one RouteMetrics + honest verdict.

    S3: visibility comes from `resolve_visibility_detailed` (word ambiguity
    counted), ready→frame pairing from `attribute_updates` (labels folded
    into the additive updates_* counters; frames_unpaired accumulated), and
    per-record clock/cap failures increment clock_failures/cap_failures and
    are REPORTED via provenance_warnings — never averaged away, never imputed
    as a pass, and never by themselves flipping the verdict (the miss/count
    floors still fail honestly when samples are lost)."""
    m = RouteMetrics(
        route=route or (records[0].route if records else ""), replays=len(records)
    )
    all_samples: list[float] = []
    ready_insert: list[float] = []
    ready_correct: list[float] = []
    for r in records:
        vis_d = resolve_visibility_detailed(
            r.words, r.field_events, anchor=r.anchor, anchor_text=r.anchor_text
        )
        vis = vis_d.ts
        m.words_ambiguous += len(vis_d.ambiguous)
        samples, misses = speech_to_visible(r.words, vis, r.feed_start)
        all_samples.extend(samples)
        m.misses += len(misses)
        attr = attribute_updates(r.update_ready, r.field_events, anchor_text=r.anchor_text)
        pairs, violations = attr.samples, attr.violations
        m.updates_total += len(attr.observations)
        m.frames_unpaired += attr.frames_unpaired
        for obs in attr.observations:
            if obs.label == "matched":
                m.updates_matched += 1
            elif obs.label == "missing":
                m.updates_missing += 1
            elif obs.label == "superseded":
                m.updates_superseded += 1
            elif obs.label == "no_op":
                m.updates_no_op += 1
            elif obs.label == "ambiguous":
                m.updates_ambiguous += 1
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
        if r.heartbeats and not heartbeat_ok(r.heartbeats):
            m.clock_failures += 1
            m.provenance_warnings.append(
                f"clock heartbeat mismatch on clip {r.clip!r}: timing evidence unverifiable"
            )
        if r.capped:
            m.cap_failures += 1
            m.provenance_warnings.append(
                f"field log cap reached on clip {r.clip!r}: frames may be unpaired"
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
        "updates_total": m.updates_total,
        "updates_matched": m.updates_matched,
        "updates_missing": m.updates_missing,
        "updates_superseded": m.updates_superseded,
        "updates_no_op": m.updates_no_op,
        "updates_ambiguous": m.updates_ambiguous,
        "frames_unpaired": m.frames_unpaired,
        "words_ambiguous": m.words_ambiguous,
        "clock_failures": m.clock_failures,
        "cap_failures": m.cap_failures,
        "provenance_warnings": m.provenance_warnings,
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
        "| route | verdict | ins | cor | miss | speech med/p95 ms | worst ms | ready ins/cor p95 ms | max out | flags | upd m/miss/sup/nop/amb |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
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
        upd = (
            f"{m.updates_matched}/{m.updates_missing}/{m.updates_superseded}"
            f"/{m.updates_no_op}/{m.updates_ambiguous}"
        )
        lines.append(
            f"| {m.route} | {m.verdict} | {m.insertions} | {m.corrections} | {m.misses} "
            f"| {med} | {worst} | {ri}/{rc} | {m.max_words_outstanding} "
            f"| {', '.join(flags) or '—'} | {upd} |"
        )
    for m in metrics:
        if m.failures:
            lines.append("")
            lines.append(f"### {m.route} failure register")
            for f_ in m.failures:
                lines.append(f"- {f_}")
    for m in metrics:
        if m.provenance_warnings:
            lines.append("")
            lines.append(f"### {m.route} provenance warnings")
            for w in m.provenance_warnings:
                lines.append(f"- {w}")
    return "\n".join(lines[:MAX_REPORT_LINES])

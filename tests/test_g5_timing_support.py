"""Tests for the G5 metrics engine (tests/g5_timing_support.py) — P1.M6.T4.S1.

Pure-python synthetic-stream tests: no CUDA, no desktop, no subprocess, fast
(the same discipline as tests/test_g3_matrix_support.py). Verdict logic is
proven HERE so the live lab only measures — never re-decides:

    timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -v

Covered (PRP Task 5 case list): median/p95 math, miss accounting (never a
0 ms sample), backlog sustain window, transient backlog, sentence-end dump,
live-stream no-dump, zero-diff law, insertion/correction split + p95s, count
shortfall after budget, first-visibility retention across retraction, and
the bounded markdown renderer — plus the previous-replay anchor exclusion
that makes multi-replay counting sound.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import g5_timing_support as g5

FEED = 1000.0  # one feed_start; every ts below is feed_start + offset


def mk_words(
    texts: list[str],
    step: float = 0.3,
    dur: float = 0.25,
    gap_after: list[int] | None = None,
):
    """Aligned words: word i spans [i*step, i*step+dur]; optional 0.8 s gaps
    after the given word indexes (splitting utterances for dump tests)."""
    out = []
    t = 0.0
    for i, w in enumerate(texts):
        out.append(g5.WordAlign(word=w, start=t, end=t + dur))
        t += step
        if gap_after and i in gap_after:
            t += 0.8
    return out


def mk_events(vis_offsets: list[float], texts: list[str]) -> list[g5.FieldEvent]:
    """Field events at FEED+offset showing the given FULL rendered text."""
    return [
        g5.FieldEvent(t=FEED + off, text=txt) for off, txt in zip(vis_offsets, texts)
    ]


def mk_record(**kw) -> g5.ReplayRecord:
    base = dict(
        route="synthetic",
        clip="clip",
        feed_start=FEED,
        words=[],
        field_events=[],
        update_ready=[],
        finals_ts=[],
        anchor=0,
    )
    base.update(kw)
    return g5.ReplayRecord(**base)


def growing_events(words, lag_s: float, upto: int | None = None):
    """One event per word: text grows by one word, visible lag_s after its
    aligned speech-end (the canonical synthetic live stream)."""
    n = len(words) if upto is None else upto
    offs, texts = [], []
    for i in range(n):
        offs.append(words[i].end + lag_s)
        texts.append(" ".join(w.word for w in words[: i + 1]))
    return mk_events(offs, texts)


# 1. speech_to_visible basic median/p95 ------------------------------------------------


def test_speech_to_visible_basic_median_and_p95():
    words = mk_words([f"w{i:03d}" for i in range(100)])
    events = growing_events(words, lag_s=0.0)
    # override: visible ts = speech-end + (100+i) ms for exact stats
    events = mk_events(
        [words[i].end + (0.100 + i * 0.001) for i in range(100)],
        [" ".join(w.word for w in words[: i + 1]) for i in range(100)],
    )
    vis = g5.resolve_visibility(words, events)
    samples, misses = g5.speech_to_visible(words, vis, FEED)
    assert misses == []
    assert len(samples) == 100
    ms = sorted(round(s, 3) for s in samples)
    assert ms == [100.0 + i for i in range(100)]  # exact per-word samples
    med = g5.aggregate(
        [mk_record(words=words, field_events=events)]
    ).speech_to_visible_med_ms
    p95 = g5.aggregate(
        [mk_record(words=words, field_events=events)]
    ).speech_to_visible_p95_ms
    assert abs(med - 149.5) < 0.01  # median of [100..199]
    assert abs(p95 - 194.0) < 0.01  # nearest-rank p95 = 95th sorted value


# 2. missing word is a miss, never a zero-latency sample -------------------------------


def test_missing_word_is_miss_not_zero():
    words = mk_words(["alpha", "beta", "gamma", "delta"])
    # "gamma" is misrecognized as "gama" → never matches its reference form
    texts = ["alpha", "alpha beta", "alpha beta gama", "alpha beta gama delta"]
    events = mk_events(
        [words[i].end + 0.2 for i in range(4)],
        texts,
    )
    vis = g5.resolve_visibility(words, events)
    samples, misses = g5.speech_to_visible(words, vis, FEED)
    assert misses == [2]
    assert len(samples) == 3  # the miss is NOT counted as a sample
    assert all(s > 0 for s in samples)  # no 0 ms laundering
    rec = mk_record(words=words, field_events=events)
    m = g5.aggregate([rec])
    assert m.misses == 1
    assert m.speech_to_visible_med_ms is not None and m.speech_to_visible_med_ms > 0


# 3. sustained backlog fails the route -------------------------------------------------


def test_backlog_sustain_fails():
    # 10 words spoken within 1 s, ALL visible only at t=+3.5 s: ≥5 outstanding
    # held ≥2.0 s (Gotcha #8: fails regardless of anything else).
    words = mk_words([f"b{i}" for i in range(10)], step=0.1, dur=0.08)
    events = mk_events([3.5], [" ".join(w.word for w in words)])
    rec = mk_record(
        words=words, field_events=events, update_ready=[], finals_ts=[FEED + 3.5]
    )
    m = g5.aggregate([rec])
    assert m.max_words_outstanding >= 6
    assert m.backlog_sustained is True
    assert any("backlog" in f for f in m.failures)
    assert m.verdict == "fail"


# 4. transient backlog does not fail ---------------------------------------------------


def test_backlog_transient_does_not_fail():
    # 5 words, all visible 0.5 s after the last speech-end: outstanding hits 5
    # but holds < SUSTAIN_WINDOW_S → no sustain flag from the backlog rule.
    words = mk_words([f"t{i}" for i in range(5)], step=0.1, dur=0.08)
    events = mk_events([1.0], [" ".join(w.word for w in words)])
    rec = mk_record(words=words, field_events=events, finals_ts=[FEED + 1.0])
    max_out, sustained = g5.outstanding_series(
        words, g5.resolve_visibility(words, events), FEED, events
    )
    assert max_out >= 5
    assert sustained is False
    assert not any("backlog" in f for f in g5.aggregate([rec]).failures)


# 5. sentence-end dump fails -----------------------------------------------------------


def test_sentence_end_dump_fails():
    # 8-word utterance delivered as ONE event at finalize time: 0 words visible
    # before the final → dump (Gotcha #8).
    words = mk_words([f"d{i}" for i in range(8)], step=0.25)
    events = mk_events([5.0], [" ".join(w.word for w in words)])
    rec = mk_record(
        words=words,
        field_events=events,
        update_ready=[(FEED + 4.9, " ".join(w.word for w in words), "final")],
        finals_ts=[FEED + 4.9],
    )
    m = g5.aggregate([rec])
    assert m.sentence_end_dump is True
    assert any("dump" in f for f in m.failures)
    assert m.verdict == "fail"


# 6. the same utterance streamed live does NOT dump ------------------------------------


def test_live_stream_no_dump():
    words = mk_words([f"d{i}" for i in range(8)], step=0.25)
    events = growing_events(
        words, lag_s=0.2
    )  # each word visible just after its speech-end
    rec = mk_record(
        words=words,
        field_events=events,
        update_ready=[
            (
                FEED + words[i].end + 0.1,
                " ".join(w.word for w in words[: i + 1]),
                "partial",
            )
            for i in range(8)
        ]
        + [(FEED + 5.0, " ".join(w.word for w in words), "final")],
        finals_ts=[FEED + 5.0],
    )
    vis = g5.resolve_visibility(words, events)
    assert g5.sentence_end_dump(words, vis, rec.finals_ts, FEED) is False
    assert g5.aggregate([rec]).sentence_end_dump is False


# 7. unchanged ⇒ zero edits (the zero-diff law) ----------------------------------------


def test_unchanged_zero_edit():
    updates = [
        (FEED + 1.0, "hello world", "partial"),
        (FEED + 2.0, "hello world", "partial"),  # identical update
    ]
    # a field event with IDENTICAL text inside the window is NOT a change
    ok_events = [g5.FieldEvent(t=FEED + 1.05, text="hello world")]
    pairs, violations = g5.ready_to_frame(updates, ok_events)
    assert violations == 0
    rec = mk_record(
        words=mk_words(["hello", "world"]), field_events=ok_events, update_ready=updates
    )
    assert g5.aggregate([rec]).unchanged_zero_edit_ok is True

    # a spurious CHANGED frame for the identical update violates the law
    bad_events = [
        g5.FieldEvent(t=FEED + 1.05, text="hello world"),
        g5.FieldEvent(t=FEED + 2.05, text="hello world!"),
    ]
    pairs, violations = g5.ready_to_frame(updates, bad_events)
    assert violations == 1
    rec = mk_record(
        words=mk_words(["hello", "world"]),
        field_events=bad_events,
        update_ready=updates,
    )
    m = g5.aggregate([rec])
    assert m.unchanged_zero_edit_ok is False
    assert any("zero-diff" in f for f in m.failures)


# 8. ready→frame insertion/correction split --------------------------------------------


def test_ready_to_frame_split():
    updates = [
        (FEED + 1.00, "hello", "partial"),
        (FEED + 2.00, "hello wor", "partial"),  # extend → insert
        (FEED + 3.00, "hello wol", "partial"),  # mid-string change → correction
        (FEED + 4.00, "hello world", "final"),  # extend → insert
    ]
    events = [
        g5.FieldEvent(t=FEED + 1.03, text="hello"),
        g5.FieldEvent(t=FEED + 2.02, text="hello wor"),
        g5.FieldEvent(t=FEED + 3.02, text="hello wol"),
        g5.FieldEvent(t=FEED + 4.02, text="hello world"),
    ]
    pairs, violations = g5.ready_to_frame(updates, events)
    assert violations == 0
    assert [p.cls for p in pairs] == [
        "insert",
        "insert",
        "correct",
        "correct",
    ]  # wol→world is a mid-string fix
    assert abs(pairs[0].delta_ms - 30.0) < 1e-6
    assert abs(pairs[1].delta_ms - 20.0) < 1e-6
    rec = mk_record(
        words=mk_words(["hello", "world"]), field_events=events, update_ready=updates
    )
    m = g5.aggregate([rec])
    assert m.insertions == 2 and m.corrections == 2
    assert abs(m.ready_p95_insert_ms - 30.0) < 1e-6
    assert abs(m.ready_p95_correct_ms - 20.0) < 1e-6


# 9. count shortfall after budget is a REPORTED failure --------------------------------


def test_count_shortfall_after_budget():
    words = mk_words(["alpha", "beta", "gamma"])
    events = growing_events(words, lag_s=0.15)
    updates = [
        (
            FEED + words[i].end + 0.05,
            " ".join(w.word for w in words[: i + 1]),
            "partial",
        )
        for i in range(3)
    ]
    rec = mk_record(
        words=words, field_events=events, update_ready=updates, finals_ts=[FEED + 4.0]
    )
    m = g5.aggregate([rec])
    assert m.insertions < g5.MIN_COUNT and m.corrections < g5.MIN_COUNT
    assert any(
        f"counts {m.insertions}/{m.corrections} < {g5.MIN_COUNT}" in f
        for f in m.failures
    )
    assert m.verdict == "fail"


# 10. a corrected word keeps its FIRST visibility ---------------------------------------


def test_correction_word_keeps_first_visibility():
    words = mk_words(["alpha", "beta", "gamma", "delta"])
    events = mk_events(
        [1.0, 2.0, 3.0, 4.0],
        [
            "alpha beta gamma",  # gamma first visible at +1.0
            "alpha beta",  # hypothesis retracts gamma
            "alpha beta gamma delta",  # re-added (later)
        ],
    )
    vis = g5.resolve_visibility(words, events)
    assert vis[0] == FEED + 1.0
    assert vis[2] == FEED + 1.0  # FIRST appearance retained, not the re-add time
    assert vis[3] == FEED + 3.0


# 11. the markdown renderer is complete + bounded ---------------------------------------


def test_render_markdown_bounded():
    words = mk_words(["alpha", "beta", "gamma"])
    events = growing_events(words, lag_s=0.15)
    rec = mk_record(words=words, field_events=events, finals_ts=[FEED + 4.0])
    m = g5.aggregate([rec], route="synthetic")
    md = g5.render_markdown(
        [m],
        {
            "date": "2026-01-01",
            "head": "deadbeef",
            "command": "g5",
            "provenance": {"gpu": "test", "model": "small.en"},
        },
    )
    for needle in (
        "| synthetic |",
        "miss",
        "speech med/p95",
        "ready ins/cor",
        "max out",
        "2026-01-01",
        "small.en",
        "verdict",
    ):
        assert needle in md
    assert len(md.splitlines()) <= g5.MAX_REPORT_LINES
    row = g5.render_report_row(m)
    assert '"verdict"' in row and '"misses"' in row


# 12. the previous-replay anchor excludes the old copy ----------------------------------


def test_resolve_visibility_anchor_excludes_previous_replay():
    """Same clip replayed: the old copy sits at token positions < anchor and
    must never match — otherwise replay k+1 would 'see' everything instantly."""
    words = mk_words(["alpha", "beta", "gamma"])
    prev_text = "alpha beta gamma"  # rendered by the PREVIOUS replay
    # replay 2's events: text grows by appending the new copy after the old one
    events = [
        g5.FieldEvent(t=FEED + 1.0, text=prev_text + " alpha"),
        g5.FieldEvent(t=FEED + 2.0, text=prev_text + " alpha beta"),
        g5.FieldEvent(t=FEED + 3.0, text=prev_text + " alpha beta gamma"),
    ]
    anchor = len(g5.normalize_tokens(prev_text))  # 3 — the harness computes this
    vis = g5.resolve_visibility(words, events, anchor=anchor)
    assert vis == [FEED + 1.0, FEED + 2.0, FEED + 3.0]
    # WITHOUT the anchor the old copy would match instantly (documenting why it exists)
    vis_no_anchor = g5.resolve_visibility(words, events, anchor=0)
    assert vis_no_anchor == [FEED + 1.0, FEED + 1.0, FEED + 1.0]


# 13. heartbeat sanity (clock-source mixing detector) -----------------------------------


def test_heartbeat_ok():
    assert g5.heartbeat_ok([(0.0, 100.0), (1.0, 101.0), (2.5, 102.5)]) is True
    assert g5.heartbeat_ok([(0.0, 100.0), (1.0, 105.0)]) is False  # wall jumped 5 s
    assert g5.heartbeat_ok([(0.0, 100.0)]) is True  # too few pairs → vacuous ok


# 14. a shrinking correction must not strand later words (pi-route revising case)


def test_resolve_visibility_survives_shrinking_correction():
    """In-place corrections shrink the rendered text; the following reference
    words render EARLIER than anchor+start — the scan's backward slack must
    still find them (the pi route revises in place; the append-only GTK route
    is unaffected)."""
    words = mk_words(["alpha", "beta", "gamma", "delta", "epsilon", "zeta"])
    # 1) append normally; 2) a correction REPLACES the last two words with one
    #    shorter word (text SHRINKS); 3) the next reference word renders early.
    events = [
        g5.FieldEvent(t=FEED + 1.0, text="alpha beta gamma delta epsilon"),
        g5.FieldEvent(t=FEED + 2.0, text="alpha beta gamma delta zeta"),  # shrink by 1
        g5.FieldEvent(t=FEED + 3.0, text="alpha beta gamma delta zeta eta"),  # regrow
    ]
    # reference: alpha beta gamma delta epsilon zeta eta
    words = mk_words(["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"])
    vis = g5.resolve_visibility(words, events)
    assert vis[0:4] == [FEED + 1.0] * 4  # prefix matched at the first event
    assert vis[5] == FEED + 2.0  # zeta visible at the shrink event
    assert vis[6] == FEED + 3.0  # eta at the regrow event
    # epsilon WAS visible at +1.0 before the correction retracted it — the
    # first-visibility law keeps that time (a retraction is not un-seeing).
    assert vis[4] == FEED + 1.0


# =============================================================================
# P1.M2.T1.S3 — ADDITIVE SECTION: changed-span attribution (synthetic only).
# Everything below is new-contract coverage; the 14 tests above are the
# historical-comparability contract and were NOT edited.
# =============================================================================

import json


def _labels(attr):
    """Observation labels in ReadyEvent order (the calibrated taxonomy)."""
    return [o.label for o in attr.observations]


def mk_ready(rows, gen=None, utt=None, stage="daemon", seq_start=None):
    """ReadyEvent stream from (offset, text, kind) rows + optional identity.

    seq (when seq_start is given) is stamped per row, mirroring the daemon's
    per-(gen, utterance) counter (_bulk_next_seq)."""
    return [
        g5.ReadyEvent(
            t=FEED + off,
            text=text,
            kind=kind,
            stage=stage,
            gen=gen,
            utt=utt,
            seq=(seq_start + i) if seq_start is not None else None,
        )
        for i, (off, text, kind) in enumerate(rows)
    ]


# S3-1. a dispatched update the field never paints is MISSING, never a sample --


def test_attribution_lost_frame_is_missing():
    u = mk_ready([(1.0, "alpha beta", "partial")])
    attr = g5.attribute_updates(u, [])  # dispatched; no field change at all
    assert _labels(attr) == ["missing"]
    assert attr.samples == [] and attr.violations == 0
    assert attr.frames_unpaired == 0
    m = g5.aggregate([mk_record(update_ready=u)], route="synthetic")
    assert m.updates_total == 1 and m.updates_missing == 1
    assert m.updates_matched == 0


# S3-2. a rewrite keeps FIRST visibility; retraction/re-add paints honestly ----


def test_span_visibility_revision_keeps_first_appearance():
    words = mk_words(["alpha", "beta"])
    events = mk_events([1.5, 2.5, 3.5], ["alpha beta", "alpha", "alpha beta"])
    vis = g5.resolve_visibility(words, events)
    assert vis == [FEED + 1.5, FEED + 1.5]  # first paint, NOT the late re-add
    det = g5.resolve_visibility_detailed(words, events)
    assert det.ts == vis and det.ambiguous == []
    u = mk_ready(
        [
            (1.0, "alpha beta", "partial"),
            (2.0, "alpha", "partial"),  # retraction
            (3.0, "alpha beta", "final"),  # re-add
        ]
    )
    attr = g5.attribute_updates(u, events)
    assert _labels(attr) == ["matched", "matched", "matched"]
    assert [round(s.delta_ms) for s in attr.samples] == [500, 500, 500]
    assert [s.cls for s in attr.samples] == ["insert", "correct", "insert"]


# S3-3. one token added in multiple AddedSpans => word ambiguity, no guess -----


def test_span_visibility_repeat_token_multi_span_ambiguous():
    words = mk_words(["dup", "dup"])
    events = mk_events([1.0, 2.0], ["x y", "x dup y dup"])
    det = g5.resolve_visibility_detailed(words, events)
    assert det.ts == [None, None]  # no guessed ts
    assert det.ambiguous == [0, 1]
    m = g5.aggregate([mk_record(words=words, field_events=events)])
    assert m.words_ambiguous == 2


def test_attribution_repeat_paint_multi_span_is_ambiguous():
    u = [
        g5.ReadyEvent(t=FEED + 1.0, text="dup", kind="partial", gen=7, utt=7, seq=1),
        g5.ReadyEvent(t=FEED + 1.05, text="dup", kind="partial", gen=7, utt=7, seq=2),
    ]
    events = mk_events([0.5, 1.5], ["x y", "x dup y dup"])
    attr = g5.attribute_updates(u, events)
    assert _labels(attr) == ["ambiguous", "ambiguous"]
    assert attr.samples == [] and attr.violations == 0
    assert attr.frames_unpaired == 1  # the pre-update "x y" frame
    m = g5.aggregate([mk_record(update_ready=u, field_events=events)])
    assert m.updates_ambiguous == 2 and m.updates_matched == 0
    assert m.frames_unpaired == 1


# S3-4a. burst + one late frame: charged to the OLDEST pending update; the
# newer identical callback gets NO false zero-diff violation (carve-out) ------


def test_attribution_burst_late_frame_charged_to_oldest():
    u = [
        g5.ReadyEvent(t=FEED + 1.0, text="alpha", kind="partial", gen=1, utt=1, seq=1),
        g5.ReadyEvent(t=FEED + 1.05, text="alpha", kind="partial", gen=1, utt=1, seq=2),
        g5.ReadyEvent(t=FEED + 1.1, text="alpha beta", kind="final", gen=1, utt=1, seq=3),
    ]
    events = mk_events([1.5], ["alpha beta"])  # ONE late frame paints everything
    attr = g5.attribute_updates(u, events)
    assert _labels(attr) == ["matched", "superseded", "no_op"]
    assert len(attr.samples) == 1
    assert round(attr.samples[0].delta_ms) == 500  # the OLDEST update's latency
    assert attr.violations == 0
    m = g5.aggregate([mk_record(update_ready=u, field_events=events)])
    assert m.updates_matched == 1
    assert m.updates_superseded == 1 and m.updates_no_op == 1
    assert m.unchanged_zero_edit_ok is True


# S3-4b. a burst frame may paint several pending updates' combined span -------


def test_attribution_burst_combined_span_all_matched():
    u = mk_ready([(1.0, "a b", "partial"), (1.02, "c d", "partial")])
    events = mk_events([1.5], ["a b c d"])
    attr = g5.attribute_updates(u, events)
    assert _labels(attr) == ["matched", "matched"]
    assert len(attr.samples) == 2
    assert [round(s.delta_ms) for s in attr.samples] == [500, 480]  # one frame ts


# S3-5. superseded: explicit (controller disposition) and inferred (identity) --


def test_attribution_superseded_explicit_and_inferred():
    # explicit: the controller recorded the coalesce
    u0 = g5.ReadyEvent(t=FEED + 1.0, text="alpha", kind="partial", disposition="coalesced")
    u1 = g5.ReadyEvent(t=FEED + 1.2, text="alpha beta", kind="partial")
    attr = g5.attribute_updates([u0, u1], mk_events([1.5], ["alpha beta"]))
    assert _labels(attr) == ["superseded", "matched"]
    assert len(attr.samples) == 1

    # inferred: same (gen,utt); the later text subsumes the older's new content
    # as a normalized prefix => coalesced-away, counted, NOT missing
    ua = g5.ReadyEvent(t=FEED + 1.0, text="alpha", kind="partial", gen=1, utt=1, seq=1)
    ub = g5.ReadyEvent(t=FEED + 1.2, text="alpha beta", kind="partial", gen=1, utt=1, seq=2)
    attr2 = g5.attribute_updates([ua, ub], [])
    assert _labels(attr2) == ["superseded", "missing"]
    assert attr2.samples == []

    # identity differs => the inference must NOT fire (honest default: missing)
    uc = g5.ReadyEvent(t=FEED + 1.0, text="alpha", kind="partial", gen=1, utt=1)
    ud = g5.ReadyEvent(t=FEED + 1.2, text="alpha beta", kind="partial", gen=2, utt=1)
    attr3 = g5.attribute_updates([uc, ud], [])
    assert _labels(attr3) == ["missing", "missing"]


# S3-6. unpaired frames (before the first update / after all settled) ----------


def test_attribution_unpaired_frames_never_samples():
    u = mk_ready([(1.0, "alpha", "partial")])
    events = mk_events([0.5, 1.5, 2.5], ["zzz", "alpha", "alpha beta"])
    attr = g5.attribute_updates(u, events)
    assert attr.frames_unpaired == 2
    assert _labels(attr) == ["matched"]
    assert len(attr.samples) == 1 and round(attr.samples[0].delta_ms) == 500
    m = g5.aggregate([mk_record(update_ready=u, field_events=events)])
    assert m.frames_unpaired == 2 and m.updates_matched == 1


# S3-7. anchor text + resets: never un-see, no phantom misses, anchored text
# never counts as first appearance ----------------------------------------------


def test_span_anchor_reset_and_first_visibility():
    anchor_text = "seed words"
    words = mk_words(["alpha", "beta"])
    events = [
        g5.FieldEvent(t=FEED + 1.5, text="seed words alpha beta"),
        g5.FieldEvent(t=FEED + 2.0, text="seed words"),  # reset to the baseline
        g5.FieldEvent(t=FEED + 2.5, text="seed words alpha beta"),  # re-add
    ]
    det = g5.resolve_visibility_detailed(words, events, anchor=2, anchor_text=anchor_text)
    assert det.ts == [FEED + 1.5, FEED + 1.5]  # reset never un-sees
    assert det.ambiguous == []
    words2 = mk_words(["seed", "words", "alpha"])
    det2 = g5.resolve_visibility_detailed(words2, [events[0]], anchor=2, anchor_text=anchor_text)
    assert det2.ts == [None, None, FEED + 1.5]  # anchor text is not an appearance

    u = mk_ready([(1.0, "alpha beta", "partial")])
    attr = g5.attribute_updates(u, events, anchor_text=anchor_text)
    assert _labels(attr) == ["matched"]
    assert len(attr.samples) == 1 and round(attr.samples[0].delta_ms) == 500
    assert attr.violations == 0  # reset/retract frames are not zero-diff violations
    assert attr.frames_unpaired == 2  # reset + re-add frames: counted, no sample


# S3-8. zero-edit oracle + the delayed-frame carve-out -------------------------


def test_attribution_zero_diff_carveout():
    u = mk_ready([(1.0, "alpha", "partial"), (2.0, "alpha", "partial")])
    # a delayed frame matching the OLDER pending span charges the older update;
    # the newer identical callback is no_op and violates nothing (carve-out)
    attr = g5.attribute_updates(u, mk_events([2.5], ["alpha"]))
    assert _labels(attr) == ["matched", "no_op"]
    assert attr.violations == 0
    assert [round(s.delta_ms) for s in attr.samples] == [1500]
    m = g5.aggregate([mk_record(update_ready=u, field_events=mk_events([2.5], ["alpha"]))])
    assert m.unchanged_zero_edit_ok is True

    # the oracle itself: a raw-changed, content-identical frame during the
    # identical update's watch is still a zero-diff violation
    bad = mk_events([1.05, 2.05], ["alpha", "alpha!"])
    attr2 = g5.attribute_updates(u, bad)
    assert _labels(attr2) == ["matched", "no_op"]
    assert attr2.violations == 1
    assert [round(s.delta_ms) for s in attr2.samples] == [50]
    mm = g5.aggregate([mk_record(update_ready=u, field_events=bad)])
    assert mm.unchanged_zero_edit_ok is False
    assert any("zero-diff" in f for f in mm.failures)


# S3-9. producer/daemon stages pair by (gen,utt,seq); stages never mix ---------


def test_attribution_stage_identity_pairing():
    prod = g5.ReadyEvent(t=FEED + 1.0, text="alpha", kind="partial", stage="producer", gen=1, utt=1, seq=1)
    dmon = g5.ReadyEvent(t=FEED + 1.2, text="alpha", kind="partial", stage="daemon", gen=1, utt=1, seq=1)
    events = mk_events([1.5], ["alpha"])
    attr = g5.attribute_updates([prod, dmon], events)
    assert _labels(attr) == ["matched", "matched"]
    assert len(attr.samples) == 1  # only the daemon checkpoint pairs frames
    assert round(attr.samples[0].delta_ms) == 300
    assert attr.observations[0].frame_ts is None
    assert "relay" in attr.observations[0].detail and "200" in attr.observations[0].detail
    assert attr.observations[1].frame_ts == FEED + 1.5

    lost = g5.ReadyEvent(t=FEED + 2.0, text="beta", kind="partial", stage="producer", gen=1, utt=2, seq=2)
    attr2 = g5.attribute_updates([prod, dmon, lost], events)
    assert _labels(attr2) == ["matched", "matched", "missing"]
    assert "relay" in attr2.observations[2].detail


# S3-10. clock/cap failures: counted + reported, never averaged away ----------


def test_attribution_clock_and_cap_counters_reported():
    words = mk_words(["alpha"])
    events = growing_events(words, lag_s=0.1)
    rec = mk_record(
        words=words,
        field_events=events,
        heartbeats=[(0.0, 100.0), (1.0, 105.0)],  # wall jumped => heartbeat_ok False
        capped=True,
    )
    m = g5.aggregate([rec], route="synthetic")
    assert m.clock_failures == 1 and m.cap_failures == 1
    # reported as evidence, but a clock/cap flag alone does not flip the verdict
    assert not any("heartbeat" in f or "cap " in f for f in m.failures)
    assert len(m.provenance_warnings) == 2
    row = json.loads(g5.render_report_row(m))
    assert row["clock_failures"] == 1 and row["cap_failures"] == 1
    assert any("heartbeat" in w for w in row["provenance_warnings"])
    assert any("cap" in w for w in row["provenance_warnings"])


# S3-11. compat: legacy tuples drive everything; visibility is the .ts view ----


def test_compat_legacy_tuples_and_visibility_equivalence():
    updates = [(FEED + 1.0, "hello", "partial"), (FEED + 2.0, "hello wor", "partial")]
    events = [
        g5.FieldEvent(t=FEED + 1.03, text="hello"),
        g5.FieldEvent(t=FEED + 2.02, text="hello wor"),
    ]
    attr = g5.attribute_updates(updates, events)
    assert _labels(attr) == ["matched", "matched"]
    assert [round(s.delta_ms) for s in attr.samples] == [30, 20]
    assert g5.ready_to_frame(updates, events) == (attr.samples, attr.violations)
    words = mk_words(["hello", "world"])
    more = mk_events([1.0, 2.0, 3.0], ["hello", "hello world", "hello"])
    assert g5.resolve_visibility(words, more) == g5.resolve_visibility_detailed(words, more).ts
    assert g5.resolve_visibility(words, more) == [FEED + 1.0, FEED + 2.0]
    r = mk_record(update_ready=updates)
    assert r.partial_source == "" and r.anchor_text == ""
    assert r.capped is False and r.heartbeats == []


# S3-12. renderers: additive counters; route/verdict stay first -----------------


def test_renderer_counter_keys_additive():
    words = mk_words(["alpha", "beta"])
    events = growing_events(words, lag_s=0.1)
    u = mk_ready([(0.15, "alpha", "partial"), (0.45, "alpha beta", "partial")])
    m = g5.aggregate(
        [mk_record(words=words, field_events=events, update_ready=u)], route="synthetic"
    )
    row = json.loads(g5.render_report_row(m))
    for key in (
        "updates_total", "updates_matched", "updates_missing", "updates_superseded",
        "updates_no_op", "updates_ambiguous", "frames_unpaired", "words_ambiguous",
        "clock_failures", "cap_failures",
    ):
        assert key in row and isinstance(row[key], int)
    assert row["updates_matched"] == 2
    for key in ("route", "verdict", "insertions", "corrections", "misses", "replays", "failures"):
        assert key in row
    md = g5.render_markdown([m], {"date": "d", "head": "h", "command": "c", "provenance": {}})
    data_rows = [ln for ln in md.splitlines() if ln.startswith("| synthetic")]
    assert data_rows, "route row missing"
    cells = [c.strip() for c in data_rows[0].strip("|").split("|")]
    assert cells[0] == "synthetic" and cells[1] in ("pass", "fail")
    assert len(md.splitlines()) <= g5.MAX_REPORT_LINES


# S3-13. ReadyEvent coercion is total and lossless for the legacy tuple shape --


def test_ready_event_coercion_lossless():
    evs = g5._to_ready_events([(1.0, "a", "partial"), (2.5, "a b", "final")])
    assert [(e.t, e.text, e.kind) for e in evs] == [(1.0, "a", "partial"), (2.5, "a b", "final")]
    assert all(
        e.stage == "daemon" and e.gen is None and e.utt is None and e.seq is None
        and e.disposition == "" and e.ack_ts is None
        for e in evs
    )
    ready = [
        g5.ReadyEvent(t=3.0, text="x", kind="partial", stage="producer", gen=1,
                      utt=2, seq=3, disposition="dispatched", ack_ts=3.01)
    ]
    assert g5._to_ready_events(ready) == ready

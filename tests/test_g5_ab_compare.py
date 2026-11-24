#!/usr/bin/env python3
"""Hermetic unit contract for tests/g5_ab_compare.py (P1.M2.T1.S6).

Pure-mock: synthetic ReplayRecords on a fake monotonic clock, minimal
artifact dicts shaped exactly like run_inner's assembly (:1430-1467), a
corrupt-JSON tmp_path file, and the live evidence doc as the g6
non-interference fixture. NO CUDA, NO compositor, NO sockets, NO daemon
import beyond the g5 lab modules. Measured samples never enter here —
every number in this file is a labelled synthetic fixture (CRITICAL #3).

Run: timeout 200 .venv/bin/python -m pytest tests/test_g5_ab_compare.py -q
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import g5_ab_compare as abc  # noqa: E402
import g5_timing_support as g5  # noqa: E402
import g6_assessment  # noqa: E402


# --------------------------------------------------------------------------
# synthetic fixtures (fake monotonic clock: feed_start = 100.0 s)
# --------------------------------------------------------------------------

FEED = 100.0
WORDS = [
    g5.WordAlign(word="alpha", start=0.0, end=0.5),
    g5.WordAlign(word="beta", start=0.5, end=1.0),
]


def _ready(t, text, kind="partial", ack_ts=None):
    return g5.ReadyEvent(t=t, text=text, kind=kind, ack_ts=ack_ts)


def _field(t, text):
    return g5.FieldEvent(t=t, text=text, kind="changed")


def make_rec(
    *,
    updates=None,
    fields=None,
    anchor_text="",
    words=None,
    capped=False,
    clip="clip-a",
    route="im-gtk",
    partial_source="plain",
):
    return g5.ReplayRecord(
        route=route,
        clip=clip,
        feed_start=FEED,
        words=list(WORDS) if words is None else words,
        field_events=list(fields or []),
        update_ready=list(updates or []),
        anchor_text=anchor_text,
        partial_source=partial_source,
        capped=capped,
    )


def base_rec(**kw):
    """One replay with every stage present and coherent:
    speech_end=101.0, useful=102.0, ack=102.2, visible=102.5."""
    updates = kw.pop(
        "updates",
        [
            _ready(101.0, ""),                    # no-op vs anchor ""
            _ready(102.0, "alpha", ack_ts=102.2),  # FIRST USEFUL
            _ready(103.0, "alpha beta"),
        ],
    )
    fields = kw.pop(
        "fields",
        [_field(102.5, "alpha"), _field(103.6, "alpha beta")],
    )
    return make_rec(updates=updates, fields=fields, **kw)


def qualified_block(field_t, frame_t, cls="visible_insert"):
    return [
        {
            "field_t": round(field_t, 6),
            "ack_ts": None,
            "frame_t": frame_t,
            "class": cls,
            "latency_ms": (
                round((frame_t - field_t) * 1000.0, 3)
                if frame_t is not None
                else None
            ),
        }
    ]


def artifact_dict(**over):
    """Minimal artifact shaped like run_inner's (:1430-1467)."""
    art = {
        "route": "im-gtk",
        "metrics": json.loads(
            g5.render_report_row(_metrics())
        ),
        "replays": ["clip-a"],
        "heartbeat_ok": True,
        "field_log_pair_count": 4,
        "provenance": {
            "kernel": "6.8.0-test",
            "python": "3.12.0",
            "partial_source_requested": "plain",
            "partial_callback_effective": "plain",
            "device": {"device": "cuda", "model": "small"},
            "warm": "resident (auto_unload_idle_seconds=0; one discarded warmup)",
            "clips": ["a.wav", "b.wav"],
            "route_note": "test",
            "field_instrument": "GTK field G5_FIELD_TIMING change log",
            "realtimestt_version": "1.0.2",
            "replay_budget": 20,
        },
        "stage_summary": {
            "route": "im-gtk",
            "arm": "plain",
            "speech_to_useful_ms": {"med": 1000.0, "p95": None, "n": 1},
            "speech_to_visible_ms": {"med": 1500.0, "p95": None, "n": 1},
            "useful_to_ack_ms": {"med": 200.0, "p95": None, "n": 1},
            "ack_to_field_ms": {"med": 300.0, "p95": None, "n": 1},
            "useful_to_field_ms": None,
            "ack_split": True,
            "field_to_frame_ms": None,
            "frame_verified": False,
            "frame_basis": abc.FRAME_PROXY_LABEL,
            "n_replays": 1,
            "n_updates": 2,
            "n_acks": 1,
            "provenance_warnings": [],
            "capped_replays": 0,
        },
    }
    art.update(over)
    return art


def _metrics(**over):
    m = g5.RouteMetrics(route="im-gtk", verdict="fail")
    m.insertions = 3
    m.misses = 0
    m.speech_to_visible_med_ms = 1500.0
    m.speech_to_visible_p95_ms = None
    m.worst_gap_ms = 900.0
    m.max_words_outstanding = 2
    m.backlog_sustained = False
    m.sentence_end_dump = False
    m.replays = 1
    m.updates_total = 3
    m.updates_matched = 2
    m.updates_superseded = 1
    m.updates_no_op = 1
    m.clock_failures = 0
    m.cap_failures = 0
    for k, v in over.items():
        setattr(m, k, v)
    return m


# --------------------------------------------------------------------------
# (1) stage math: exact medians on known timestamps; p95 only when n>=5
# --------------------------------------------------------------------------


class TestStageMath:
    def test_exact_stages_single_replay(self):
        s = abc.stage_summary([base_rec()])
        assert s["speech_to_useful_ms"]["med"] == pytest.approx(1000.0)
        assert s["speech_to_visible_ms"]["med"] == pytest.approx(1500.0)
        assert s["useful_to_ack_ms"]["med"] == pytest.approx(200.0)
        assert s["ack_to_field_ms"]["med"] == pytest.approx(300.0)
        assert s["ack_split"] is True
        assert s["speech_to_useful_ms"]["n"] == 1
        # p95 skipped below n>=5 (never extrapolated)
        assert s["speech_to_useful_ms"]["p95"] is None

    def test_speech_end_is_feed_start_plus_last_word_end(self):
        rec = make_rec(
            updates=[_ready(102.5, "alpha")],
            fields=[_field(102.75, "alpha")],
            words=[g5.WordAlign("x", 0.0, 2.25)],
        )
        s = abc.stage_summary([rec])
        # speech_end = 100.0 + 2.25 = 102.25 → useful at 102.5 (+250 ms),
        # visible at 102.75 (+500 ms)
        assert s["speech_to_useful_ms"]["med"] == pytest.approx(250.0)
        assert s["speech_to_useful_ms"]["n"] == 1
        assert s["speech_to_visible_ms"]["med"] == pytest.approx(500.0)

    def test_p95_reported_only_at_five_plus_samples(self):
        recs = []
        for i in range(5):
            off = i * 0.010  # useful at 102.00..102.04
            recs.append(
                make_rec(
                    updates=[
                        _ready(102.0 + off, "alpha", ack_ts=102.2 + off),
                    ],
                    fields=[_field(102.5 + off, "alpha")],
                    clip=f"c{i}",
                )
            )
        s = abc.stage_summary(recs)
        assert s["speech_to_useful_ms"]["n"] == 5
        assert s["speech_to_useful_ms"]["p95"] is not None
        # nearest-rank p95 of [1000..1040] ms = 1040
        assert s["speech_to_useful_ms"]["p95"] == pytest.approx(1040.0)
        assert s["useful_to_ack_ms"]["p95"] is not None

    def test_empty_records_give_zeroed_none_summary_not_crash(self):
        s = abc.stage_summary([])
        assert s["n_replays"] == 0
        assert s["speech_to_useful_ms"] is None or (
            s["speech_to_useful_ms"] is not None
            and s["speech_to_useful_ms"]["n"] == 0
        )

    def test_no_words_replay_excluded_not_imputed(self):
        rec = make_rec(words=[], updates=[_ready(102.0, "alpha")],
                       fields=[_field(102.5, "alpha")])
        s = abc.stage_summary([rec])
        assert s["speech_to_useful_ms"]["n"] == 0
        assert s["speech_to_useful_ms"]["med"] is None


# --------------------------------------------------------------------------
# (2) first-useful rule (Gotcha #10): no-op/repeat partials never win
# --------------------------------------------------------------------------


class TestFirstUseful:
    def test_noop_then_growing_partial_wins(self):
        rec = base_rec()  # "" no-op at 101.0; "alpha" useful at 102.0
        s = abc.stage_summary([rec])
        assert s["speech_to_useful_ms"]["med"] == pytest.approx(1000.0)

    def test_same_text_repeat_is_not_useful(self):
        rec = make_rec(
            updates=[
                _ready(101.5, ""),        # no-op vs anchor ""
                _ready(102.0, "alpha"),   # FIRST USEFUL
                _ready(103.0, "alpha"),   # repeat — must NOT re-anchor useful
            ],
            fields=[_field(102.4, "alpha")],
        )
        s = abc.stage_summary([rec])
        assert s["speech_to_useful_ms"]["med"] == pytest.approx(1000.0)
        assert s["speech_to_visible_ms"]["med"] == pytest.approx(1400.0)

    def test_anchored_seed_excludes_pre_existing_text(self):
        rec = make_rec(
            anchor_text="seed text",
            updates=[_ready(101.5, "seed text"), _ready(102.0, "seed text more")],
            fields=[_field(102.4, "seed text more")],
        )
        s = abc.stage_summary([rec])
        assert s["speech_to_useful_ms"]["med"] == pytest.approx(1000.0)

    def test_events_before_feed_start_ignored(self):
        rec = make_rec(
            updates=[_ready(99.0, "alpha", ack_ts=99.1),  # pre-replay
                     _ready(102.0, "alpha", ack_ts=102.2)],
            fields=[_field(99.2, "alpha"), _field(102.5, "alpha")],
        )
        s = abc.stage_summary([rec])
        assert s["speech_to_useful_ms"]["med"] == pytest.approx(1000.0)


# --------------------------------------------------------------------------
# (3) ack split: present/absent/incoherent
# --------------------------------------------------------------------------


class TestAckSplit:
    def test_ack_present_splits(self):
        s = abc.stage_summary([base_rec()])
        assert s["ack_split"] is True
        assert s["useful_to_ack_ms"]["med"] == pytest.approx(200.0)
        assert s["ack_to_field_ms"]["med"] == pytest.approx(300.0)
        assert s["useful_to_field_ms"] is None
        assert s["n_acks"] == 1

    def test_ack_absent_merges(self):
        rec = make_rec(
            updates=[_ready(102.0, "alpha")],  # no ack_ts
            fields=[_field(102.6, "alpha")],
        )
        s = abc.stage_summary([rec])
        assert s["ack_split"] is False
        assert s["useful_to_ack_ms"] is None
        assert s["ack_to_field_ms"] is None
        assert s["useful_to_field_ms"]["med"] == pytest.approx(600.0)
        assert s["n_acks"] == 0

    def test_ack_outside_sanity_window_ignored_with_warning(self):
        rec = make_rec(
            updates=[_ready(102.0, "alpha", ack_ts=104.0)],  # after vis 102.5
            fields=[_field(102.5, "alpha")],
        )
        s = abc.stage_summary([rec])
        assert s["ack_split"] is False
        assert s["n_acks"] == 0
        assert s["useful_to_field_ms"]["med"] == pytest.approx(500.0)
        assert any("ack" in w.lower() for w in s["provenance_warnings"])

    def test_ack_before_update_ignored(self):
        rec = make_rec(
            updates=[_ready(102.0, "alpha", ack_ts=101.5)],  # before useful
            fields=[_field(102.5, "alpha")],
        )
        s = abc.stage_summary([rec])
        assert s["ack_split"] is False
        assert s["n_acks"] == 0

    def test_legacy_tuple_records_coerced(self):
        rec = make_rec(
            updates=[(102.0, "alpha", "partial"), (103.0, "alpha beta", "partial")],
            fields=[_field(102.5, "alpha")],
        )
        s = abc.stage_summary([rec])
        assert s["speech_to_useful_ms"]["med"] == pytest.approx(1000.0)


# --------------------------------------------------------------------------
# (4) frame split: only under S5 verification, from frame_qualified
# --------------------------------------------------------------------------


class TestFrameSplit:
    def _rec(self):
        return base_rec()

    def test_verified_observer_yields_field_to_frame(self):
        fq = {"clip-a": qualified_block(102.5, 102.55)}
        s = abc.stage_summary(
            [self._rec()],
            frame_observer={"status": "verified"},
            frame_qualified=fq,
        )
        assert s["field_to_frame_ms"]["med"] == pytest.approx(50.0)
        assert s["field_to_frame_ms"]["n"] == 1
        assert s["frame_verified"] is True
        assert s["frame_basis"] == abc.FRAME_QUALIFIED_LABEL

    def test_unverified_status_gives_none_and_proxy_label(self):
        for status in ("unverified", "blocked", None):
            fq = {"clip-a": qualified_block(102.5, 102.55)}
            kw = {"frame_qualified": fq}
            if status is not None:
                kw["frame_observer"] = {"status": status}
            s = abc.stage_summary([self._rec()], **kw)
            assert s["field_to_frame_ms"] is None
            assert s["frame_verified"] is False
            assert s["frame_basis"] == abc.FRAME_PROXY_LABEL

    def test_qualified_miss_is_not_a_frame(self):
        fq = {"clip-a": qualified_block(102.5, None,
                                        cls="missed_below_resolution")}
        s = abc.stage_summary(
            [self._rec()],
            frame_observer={"status": "verified"},
            frame_qualified=fq,
        )
        assert s["field_to_frame_ms"] is None
        assert s["frame_verified"] is True  # observer verified, this word missed
        assert s["n_replays"] == 1

    def test_frame_list_artifact_shape_accepted(self):
        # artifact shape: [{"clip": ..., "qualified": [...]}]
        fq = [{"clip": "clip-a", "qualified": qualified_block(102.5, 102.55)}]
        s = abc.stage_summary(
            [self._rec()],
            frame_observer={"status": "verified"},
            frame_qualified=fq,
        )
        assert s["field_to_frame_ms"]["med"] == pytest.approx(50.0)

    def test_repeated_clip_entries_do_not_collide(self):
        # two replays of the SAME clip: the qualified pool holds both
        # replays' entries; each replay must match its OWN boundary ts
        rec_a = base_rec(clip="jargon")
        rec_b = make_rec(
            updates=[_ready(202.0, "alpha", ack_ts=202.2)],
            fields=[_field(202.5, "alpha")],
            clip="jargon",
        )
        rec_b.feed_start = 200.0
        fq = {
            "jargon": qualified_block(102.5, 102.55)
            + qualified_block(202.5, 202.6)
        }
        s = abc.stage_summary(
            [rec_a, rec_b],
            frame_observer={"status": "verified"},
            frame_qualified=fq,
        )
        assert s["field_to_frame_ms"]["n"] == 2
        assert s["field_to_frame_ms"]["med"] == pytest.approx(75.0)

    def test_verified_observer_with_zero_matches_still_proxy_label(self):
        # CRITICAL #6: a missing cell is never upgraded by observer status
        fq = {"other-clip": qualified_block(102.5, 102.55)}
        s = abc.stage_summary(
            [self._rec()],
            frame_observer={"status": "verified"},
            frame_qualified=fq,
        )
        assert s["field_to_frame_ms"] is None
        assert s["frame_basis"] == abc.FRAME_PROXY_LABEL
        assert s["frame_verified"] is True

    def test_post_update_fallback_labelled_and_separate(self):
        # the first-visible paint is S5's baseline (never qualified); the
        # earliest qualified pair at/after the useful update carries its
        # OWN paint latency in paint_qualified_ms — never merged into the
        # exact field_to_frame cell
        rec = self._rec()
        fq = [
            {
                "clip": rec.clip,
                "qualified": qualified_block(103.6, 103.66),
            }
        ]
        s = abc.stage_summary(
            [rec],
            frame_observer={"status": "verified"},
            frame_qualified=fq,
        )
        assert s["field_to_frame_ms"] is None
        assert s["paint_qualified_ms"]["med"] == pytest.approx(60.0)
        assert s["paint_qualified_ms"]["n"] == 1
        assert s["frame_match"] == "post-update-qualified"
        assert s["frame_basis"] == abc.FRAME_PAINT_FALLBACK_LABEL
        assert s["frame_verified"] is True

    def test_aligned_list_form_matches_per_record(self):
        # artifact/list shape aligned by index: two same-clip replays, each
        # matches its OWN boundary even though clips collide
        rec_a = base_rec(clip="jargon")
        rec_b = make_rec(
            updates=[_ready(202.0, "alpha", ack_ts=202.2)],
            fields=[_field(202.5, "alpha")],
            clip="jargon",
        )
        rec_b.feed_start = 200.0
        fq = [
            {"clip": "jargon", "qualified": qualified_block(102.5, 102.55)},
            {"clip": "jargon", "qualified": qualified_block(202.5, 202.6)},
        ]
        s = abc.stage_summary(
            [rec_a, rec_b],
            frame_observer={"status": "verified"},
            frame_qualified=fq,
        )
        assert s["field_to_frame_ms"]["n"] == 2
        assert s["field_to_frame_ms"]["med"] == pytest.approx(75.0)
        assert s["frame_match"] == "exact-first-visible"


# --------------------------------------------------------------------------
# (5) capped/clock flags propagate; misses never imputed
# --------------------------------------------------------------------------


class TestFlagsCarried:
    def test_capped_counted(self):
        s = abc.stage_summary([base_rec(), base_rec(capped=True, clip="b")])
        assert s["capped_replays"] == 1

    def test_metrics_verbatim_in_row(self, tmp_path):
        p = tmp_path / "artifact-im-gtk.json"
        art = artifact_dict()
        art["metrics"]["misses"] = 7
        art["metrics"]["clock_failures"] = 2
        art["metrics"]["cap_failures"] = 1
        p.write_text(json.dumps(art))
        rows = abc.compare({("im-gtk", "plain"): p})
        row = rows[0]
        assert row.misses == 7  # counted verbatim, never imputed/averaged
        assert row.clock_failures == 2
        assert row.capped_replays == 1
        assert row.updates_superseded == 1
        assert row.status == "unverified-clock"


# --------------------------------------------------------------------------
# (6) check_comparable matrix
# --------------------------------------------------------------------------


class TestComparability:
    def two_arts(self, **over_a):
        a = artifact_dict()
        b = json.loads(json.dumps(artifact_dict()))
        b["provenance"]["partial_source_requested"] = "default"
        b["provenance"]["partial_callback_effective"] = "stabilized"
        b["stage_summary"]["arm"] = "stabilized"
        for k, v in over_a.items():
            if k in ("heartbeat_ok",):
                a[k] = v
            elif k.startswith("prov:"):
                key = k[len("prov:"):]
                if v is abc.MISSING:
                    a["provenance"].pop(key, None)
                else:
                    a["provenance"][key] = v
            else:
                a[k] = v
        return {("im-gtk", "plain"): a, ("im-gtk", "stabilized"): b}

    def test_matched_pair_has_no_reasons(self):
        assert abc.check_comparable(self.two_arts()) == []

    def test_clip_mismatch_flagged(self):
        reasons = abc.check_comparable(
            self.two_arts(**{"prov:clips": ["a.wav"]})
        )
        assert any("clips" in r for r in reasons)

    def test_device_mismatch_flagged(self):
        reasons = abc.check_comparable(
            self.two_arts(**{"prov:device": {"device": "cpu"}})
        )
        assert any("device" in r for r in reasons)

    def test_version_mismatch_flagged(self):
        reasons = abc.check_comparable(
            self.two_arts(**{"prov:realtimestt_version": "1.0.1"})
        )
        assert any("realtimestt_version" in r for r in reasons)

    def test_python_and_kernel_mismatch_flagged(self):
        reasons = abc.check_comparable(
            self.two_arts(**{"prov:python": "3.11.0",
                             "prov:kernel": "6.1.0-x"})
        )
        assert any("python" in r for r in reasons)
        assert any("kernel" in r for r in reasons)

    def test_budget_mismatch_and_missing_flagged(self):
        reasons = abc.check_comparable(
            self.two_arts(**{"prov:replay_budget": 10})
        )
        assert any("replay_budget" in r for r in reasons)
        reasons = abc.check_comparable(
            self.two_arts(**{"prov:replay_budget": abc.MISSING})
        )
        assert any("replay_budget" in r for r in reasons)

    def test_warm_mismatch_flagged(self):
        reasons = abc.check_comparable(
            self.two_arts(**{"prov:warm": "cold"})
        )
        assert any("warm" in r for r in reasons)

    def test_heartbeat_false_flagged(self):
        reasons = abc.check_comparable(self.two_arts(heartbeat_ok=False))
        assert any("heartbeat" in r for r in reasons)

    def test_same_effective_source_flagged(self):
        arts = self.two_arts()
        arts[("im-gtk", "stabilized")]["provenance"][
            "partial_callback_effective"
        ] = "plain"
        reasons = abc.check_comparable(arts)
        assert any("plain" in r for r in reasons)

    def test_device_treatment_key_is_excluded(self):
        # the arm's own partial_callback INSIDE device differs BY DESIGN
        # (it is the treatment); the rest of the device dict must match
        arts = self.two_arts()
        arts[("im-gtk", "plain")]["provenance"]["device"][
            "partial_callback"
        ] = "on_realtime_transcription_update"
        arts[("im-gtk", "stabilized")]["provenance"]["device"][
            "partial_callback"
        ] = "on_realtime_transcription_stabilized"
        assert abc.check_comparable(arts) == []
        # but a REAL device difference still counts
        arts[("im-gtk", "stabilized")]["provenance"]["device"]["model"] = "base.en"
        reasons = abc.check_comparable(arts)
        assert any("device" in r for r in reasons)

    def test_cross_route_pairs_not_compared(self):
        arts = self.two_arts()
        pi = json.loads(json.dumps(artifact_dict()))
        pi["route"] = "pi-ghostty"
        pi["provenance"]["clips"] = ["totally-different.wav"]
        arts[("pi-ghostty", "plain")] = pi
        # only the im-gtk pair shares a route; pi has no partner → no reasons
        assert abc.check_comparable(arts) == []


# --------------------------------------------------------------------------
# (7) compare labels: missing/corrupt/empty → not-run with reason, no zeros
# --------------------------------------------------------------------------


class TestCompareLabels:
    def test_missing_file_is_not_run(self, tmp_path):
        rows = abc.compare({("im-gtk", "plain"): tmp_path / "nope.json"})
        r = rows[0]
        assert r.status == "not-run"
        assert r.reason
        assert r.speech_to_useful_med_ms is None
        assert r.speech_to_visible_med_ms is None
        assert r.n_replays == 0

    def test_corrupt_json_is_not_run(self, tmp_path):
        p = tmp_path / "artifact-im-gtk.json"
        p.write_text("{not json at all")
        rows = abc.compare({("im-gtk", "plain"): p})
        assert rows[0].status == "not-run"
        assert rows[0].reason

    def test_empty_artifact_is_not_run(self, tmp_path):
        p = tmp_path / "artifact-im-gtk.json"
        p.write_text("{}")
        rows = abc.compare({("im-gtk", "plain"): p})
        assert rows[0].status == "not-run"

    def test_pre_s6_artifact_without_stages_is_not_run(self, tmp_path):
        p = tmp_path / "artifact-im-gtk.json"
        art = artifact_dict()
        art.pop("stage_summary")
        p.write_text(json.dumps(art))
        rows = abc.compare({("im-gtk", "plain"): p})
        assert rows[0].status == "not-run"
        assert "stage" in rows[0].reason

    def test_heartbeat_false_is_unverified_clock_with_numbers(self, tmp_path):
        p = tmp_path / "artifact-im-gtk.json"
        art = artifact_dict()
        art["heartbeat_ok"] = False
        p.write_text(json.dumps(art))
        rows = abc.compare({("im-gtk", "plain"): p})
        r = rows[0]
        assert r.status == "unverified-clock"
        assert r.speech_to_useful_med_ms == pytest.approx(1000.0)

    def test_measured_happy_path(self, tmp_path):
        p = tmp_path / "artifact-im-gtk.json"
        p.write_text(json.dumps(artifact_dict()))
        rows = abc.compare({("im-gtk", "plain"): p})
        r = rows[0]
        assert r.status == "measured"
        assert r.reason == ""
        assert r.speech_to_useful_med_ms == pytest.approx(1000.0)
        assert r.ack_to_field_med_ms == pytest.approx(300.0)
        assert r.insertions == 3


# --------------------------------------------------------------------------
# (8) g6 non-interference: appending the rendered section changes nothing
# --------------------------------------------------------------------------


class TestG6NonInterference:
    DOC = Path(__file__).parent / "G5_TIMING_EVIDENCE.md"

    def test_append_leaves_parse_route_verdicts_unchanged(self):
        doc_text = self.DOC.read_text(encoding="utf-8")
        before = g6_assessment.parse_route_verdicts(doc_text)
        assert before, "fixture doc must itself parse (guard the guard)"
        rows = abc.compare({})  # no artifacts → honest not-run rows? (empty)
        section = abc.render_markdown(
            rows or self._demo_rows(),
            meta=self._demo_meta(),
        )
        after = g6_assessment.parse_route_verdicts(doc_text + "\n" + section)
        assert after == before

    @staticmethod
    def _demo_rows():
        a = abc.StageRow(
            route="im-gtk", arm="plain", status="measured",
            speech_to_useful_med_ms=900.0, speech_to_visible_med_ms=1400.0,
            n_replays=20, updates_total=40, updates_matched=30,
            updates_superseded=5, updates_no_op=3, insertions=10,
            corrections=4, misses=1, max_words_outstanding=2,
        )
        b = abc.StageRow(
            route="im-gtk", arm="stabilized", status="measured",
            speech_to_useful_med_ms=950.0, speech_to_visible_med_ms=1450.0,
            n_replays=20, updates_total=22, updates_matched=20,
            updates_superseded=1, updates_no_op=1, insertions=10,
            corrections=4, misses=1, max_words_outstanding=2,
        )
        return [a, b]

    @staticmethod
    def _demo_meta():
        return {
            "date": "2025-01-01",
            "commit": "86ba158",
            "realtimestt_version": "1.0.2",
            "cadence": "32 ms chunks paced in real time",
            "budget": "20",
            "warm": "one discarded warmup, resident model",
            "limits": [],
        }


# --------------------------------------------------------------------------
# (9) render invariants: verdict-token ban in tables, n everywhere,
#     provenance block present
# --------------------------------------------------------------------------

_VERDICT_TOKEN_RE = re.compile(r"(?i)\*{0,2}(pass|fail|blocked)\*{0,2}")


class TestRenderInvariants:
    def test_no_verdict_tokens_in_any_table_row(self):
        section = abc.render_markdown(
            TestG6NonInterference._demo_rows(),
            meta=TestG6NonInterference._demo_meta(),
        )
        table_lines = [
            ln for ln in section.splitlines() if ln.lstrip().startswith("|")
        ]
        assert table_lines, "render must contain tables"
        for ln in table_lines:
            assert not _VERDICT_TOKEN_RE.search(ln), f"verdict token: {ln}"

    def test_provenance_keys_present(self):
        section = abc.render_markdown(
            TestG6NonInterference._demo_rows(),
            meta=TestG6NonInterference._demo_meta(),
        )
        for key in ("2025-01-01", "86ba158", "1.0.2"):
            assert key in section

    def test_section_heading_matches_evidence_plan(self):
        section = abc.render_markdown([], meta={"date": "d"})
        assert "## Paired callback comparison and stage diagnosis" in section
        assert "P1.M2.T1.S6" in section

    def test_not_run_rows_render_reason_never_zeros(self):
        rows = abc.compare({("pi-ghostty", "plain"): Path("/nonexistent/x")})
        section = abc.render_markdown(
            rows, meta={"date": "d", "limits": []}
        )
        assert "/nonexistent/x" in section or "missing" in section
        table_lines = [
            ln for ln in section.splitlines() if ln.lstrip().startswith("|")
        ]
        data = [ln for ln in table_lines if "pi-ghostty" in ln]
        assert data
        assert not re.search(r"\b0\.0\b", " ".join(data))

    def test_limits_surface_comparability_reasons(self):
        rows = []
        section = abc.render_markdown(
            rows,
            meta={
                "date": "d",
                "limits": ["im-gtk: clips differ across arms"],
            },
        )
        assert "im-gtk: clips differ across arms" in section

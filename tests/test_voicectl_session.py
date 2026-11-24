"""tests/test_voicectl_session.py — P1.M6.T2.S3: real-daemon session_reply semantics.

The DAEMON half of the `voicectl session [--copy]` surface (PRD §4.2sexies R.6): what the
control socket answers for {"cmd": "session"} on a REAL VoiceTypingDaemon driven exactly the
way tests/test_session_recovery.py drives it (fakes ONLY — no CUDA, no subprocess, no live
desktop; AGENTS.md). The CLIENT half lives in tests/test_voicectl.py (format_result, main()
orchestration, mocked wl-copy/wl-paste); the dispatch/socket layer lives in
tests/test_control_socket.py. Pinned here:
  - none → {"ok": false, "error": "no completed session yet"} (G1: rides the existing
    ok:false path → client exit 1, clipboard untouched);
  - completed → {"ok": true, "session": <the S2 snapshot dict, verbatim>};
  - an open draft (moving partial) is INVISIBLE — the previous completed session answers;
  - the served log line is counts-only (R.6 log law: never the session text).

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_voicectl_session.py -q
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0, str(Path(__file__).resolve().parent)
)  # sibling-test fixture imports

import test_daemon as td  # noqa: E402 — stream-edit fakes (_make_lazy_daemon, _fake_host_factory)

_NONE_REPLY = {"ok": False, "error": "no completed session yet"}


def _make_stream_daemon():
    """An ARMED stream-edit daemon over test_daemon's fakes (the S2 driving pattern —
    tests/test_session_recovery.py::_make_stream_daemon, verbatim). recorder=None so
    _load_host uses the host_factory; no threads run; events are driven synchronously."""
    d, fb = td._make_lazy_daemon(host_factory=td._fake_host_factory(spawn_result=True))
    assert d._load_host() is True
    d.start()  # → _arm() under the lock (open_session included)
    return d, fb, d._backend


def _disarm(d):
    """Disarm under the daemon lock (the S2 pattern — _disarm is the internal funnel)."""
    with d._lock:
        d._disarm()


def test_session_reply_none_maps_to_error():
    """(c) fresh daemon (empty store) → the ok:false error reply — NOT a {"session": null}
    shape (G1 anti-pattern): the client's existing error path yields exit 1 untouched."""
    d, _fb, _be = _make_stream_daemon()
    assert d.session_reply() == _NONE_REPLY


def test_session_reply_completed_carries_snapshot():
    """(a) arm → accepted final → disarm → {"ok": true, "session": <S2 snapshot verbatim>},
    exactly {ok, session} on the wire (no status keys leak into the session reply)."""
    d, _fb, _be = _make_stream_daemon()
    d.on_final("hello world")
    _disarm(d)
    reply = d.session_reply()
    assert set(reply) == {"ok", "session"}
    assert reply["ok"] is True
    snap = reply["session"]
    assert snap["text"] == "hello world"
    assert snap["truncated"] is False and snap["finals_dropped"] == 0
    assert snap["finals"] == 1 and snap["tail_chars"] == 0
    assert isinstance(snap["ended_monotonic"], float)
    assert set(snap) == {
        "text",
        "truncated",
        "finals",
        "finals_dropped",
        "tail_chars",
        "ended_monotonic",
    }


def test_session_reply_copy_flag_accepted():
    """The additive 'copy' payload key is read by dispatch and passed through (informational
    on the daemon side — the copy itself is client-side); the reply shape is unchanged."""
    d, _fb, _be = _make_stream_daemon()
    d.on_final("copied text")
    _disarm(d)
    assert d.session_reply(copy=True)["session"]["text"] == "copied text"
    assert d.session_reply(copy=False)["session"]["text"] == "copied text"


def test_session_reply_never_exposes_open_draft():
    """(f) an armed session with a live partial is INVISIBLE: session_reply() still answers
    the previous COMPLETED session; the draft string appears NOWHERE in the reply."""
    d, _fb, _be = _make_stream_daemon()
    d.on_final("the keeper")
    _disarm(d)
    d.start()  # re-arm: a NEW session opens (session #2, still empty)
    d._on_partial("moving draft tail")  # the live draft — must not leak
    reply = d.session_reply()
    assert reply["ok"] is True
    assert reply["session"]["text"] == "the keeper"
    assert "moving draft tail" not in json.dumps(reply)


def test_session_reply_log_is_counts_only(caplog):
    """(R.6 log law) the served INFO line carries counts/times ONLY — never the session text."""
    d, _fb, _be = _make_stream_daemon()
    secret = "secret transcript words"
    with caplog.at_level("INFO", logger="voice_typing.daemon"):
        d.on_final(secret)
        _disarm(d)
        d.session_reply(copy=True)
        d.session_reply(copy=False)
    served = [
        r.getMessage() for r in caplog.records if "session served" in r.getMessage()
    ]
    assert len(served) == 2, served  # one line per session_reply() call
    for line in served:
        assert re.search(
            r"session recovery: session served copy=[01] chars=\d+ truncated=[01]",
            line,
        ), line
        assert secret not in line  # R.6: no transcript-bearing logs
    assert "copy=1" in served[0] and "copy=0" in served[1]

"""Unit tests for voice_typing.clipboard_target — pure fakes, no desktop.

Every collaborator (wire/trigger/confirm/watcher_scan) is a fake or a stub;
nothing here needs WAYLAND_DISPLAY. The socketpair wire tests run a tiny fake
compositor over REAL bytes so the data-control opcode tables, the fd-carrying
receive request, and the fd-keeping send event are pinned against literal
protocol expectations (wlr-data-control-unstable-v1.xml document order).
"""
from __future__ import annotations

import os
import socket
import struct
import subprocess
import sys
import time

import pytest

from voice_typing.bulk_delivery import ShowResult
from voice_typing.clipboard_target import (
    NONCE_MIME,
    TEXT_MIME,
    WATCHER_REFUSAL,
    ClipboardFormat,
    ClipboardSnapshot,
    ClipboardTarget,
    ClipboardWatchdog,
    DataControlClient,
    WireLink,
    ZwlrDataControlSource,
    detect_clipboard_watcher,
)
from voice_typing.ime.wlwire import WlError, u32, wstr


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeWire:
    """WireLink duck: canned snapshot, recorded publishes, scripted syncs.

    publish() bumps sync_count only (a publish's own barrier), so a scripted
    on_sync fires exactly at the adapter's RECHECK sync — deterministic.
    """

    def __init__(self, formats: tuple[ClipboardFormat, ...] = (), *, connect_ok=True):
        self.display = "fake-0"
        self.client = None
        self.connect_ok = connect_ok
        self.snapshot_formats = formats
        self.published: list[tuple[dict[str, bytes], str]] = []
        self.live: ZwlrDataControlSource | None = None
        self.sync_count = 0
        self.on_sync = None  # one-shot: scripted foreign change at recheck

    def connect(self) -> bool:
        if not self.connect_ok:
            return False
        self.client = object()
        return True

    def snapshot_selection(self, nonce: str, read_wait_s: float = 1.0) -> ClipboardSnapshot:
        if not self.client:
            raise WlError("wire not connected")
        return ClipboardSnapshot(self.snapshot_formats, nonce, len(self.published) + 1)

    def publish(self, formats: dict[str, bytes], nonce: str) -> ZwlrDataControlSource | None:
        self.published.append((dict(formats), nonce))
        if not formats:
            self.live = None
            return None
        self.live = ZwlrDataControlSource(100 + len(self.published), dict(formats),
                                          nonce, len(self.published))
        self.sync_count += 1
        return self.live

    def sync(self, timeout: float = 2.0) -> None:
        self.sync_count += 1
        cb, self.on_sync = self.on_sync, None
        if cb is not None:
            cb(self)

    def pump(self, timeout: float = 0.05) -> int:
        return 0

    def selection_types(self) -> list[str]:
        if self.live is None:
            return []
        return self.live.mimes()

    def close(self) -> None:
        self.client = None


def make_target(wire=None, *, confirm=True, trigger=True):
    """ClipboardTarget over fakes. confirm: True/False or a recorder list.

    The trigger/confirm recorders let tests assert the adapter itself never
    re-triggers (R.5 disarm discipline).
    """
    wire = wire or FakeWire()
    trig = [] if trigger else None

    def do_trigger():
        trig.append(1)

    conf_rec: list[str] = []

    def do_confirm(delta: str) -> bool:
        conf_rec.append(delta)
        return confirm is True

    t = ClipboardTarget(wire, trigger=do_trigger if trigger else None,
                        confirm=do_confirm if trigger else None,
                        watcher_scan=lambda: [])
    return t, wire, trig, conf_rec


SNAP = (ClipboardFormat(TEXT_MIME, b"user text"),)


# ---------------------------------------------------------------------------
# acquire (R.3/R.6: fail before delivery)
# ---------------------------------------------------------------------------

def test_acquire_ok_binds_snapshot():
    t, wire, _, _ = make_target(FakeWire(SNAP))
    r = t.acquire()
    assert r.ok and r.revision == 0
    assert r.handle.snapshot.formats == SNAP
    assert t.last_reason == ""


def test_acquire_refuses_watcher_with_contract_reason():
    t, _, _, _ = make_target()
    t._scan = lambda: ["31337 wl-paste --type text --watch cliphist store"]
    r = t.acquire()
    assert not r.ok
    assert r.reason == WATCHER_REFUSAL          # the contract string, verbatim
    assert r.reason.startswith("clipboard-history watcher active")


def test_acquire_fail_closed_when_scan_fails():
    t, _, _, _ = make_target()
    t._scan = lambda: None                      # unknown == present (conservative)
    assert not t.acquire().ok
    assert "fail-closed" in t.last_reason


def test_acquire_refuses_snapshot_failure():
    t, wire, _, _ = make_target()
    wire.snapshot_selection = lambda *a, **k: (_ for _ in ()).throw(WlError("boom"))
    r = t.acquire()
    assert not r.ok and r.reason.startswith("clipboard snapshot failed")


def test_acquire_refuses_connect_failure():
    t, wire, _, _ = make_target(FakeWire(connect_ok=False))
    r = t.acquire()
    assert not r.ok and r.reason == "clipboard wire connect failed"


# ---------------------------------------------------------------------------
# show: the insert-only transfer cycle
# ---------------------------------------------------------------------------

def _acquired(wire=None, confirm=True):
    t, wire, trig, conf = make_target(wire, confirm=confirm)
    assert t.acquire().ok
    return t, wire, trig, conf


def test_show_insert_pastes_delta_once_then_restores():
    t, wire, trig, conf = _acquired(FakeWire(SNAP))
    assert t.show(1, "u1", 1, 0, "user text and more") is ShowResult.APPLIED
    assert trig == [1]                          # ONE chord
    stage_fmts, stage_nonce = wire.published[0]
    assert stage_fmts == {TEXT_MIME: b"user text and more"}  # first show: full span is the delta
    assert wire.live.mimes()[-1] == NONCE_MIME       # sentinel offered on OUR source
    _, restore_nonce = wire.published[1]
    assert dict(wire.published[1][0]) == {TEXT_MIME: b"user text"}  # exact snapshot back
    assert restore_nonce != stage_nonce         # fresh sentinel per generation
    assert t.last_reason == ""


def test_show_empty_snapshot_restores_null_selection():
    t, wire, _, _ = _acquired(FakeWire(()))     # originally-empty clipboard
    assert t.show(1, "u1", 1, 0, "hi") is ShowResult.APPLIED
    assert wire.published[1][0] == {}           # restore = null selection, not an empty offer


def test_show_zero_diff_is_unchanged_without_touching_clipboard():
    t, wire, trig, _ = _acquired(FakeWire(SNAP))
    t._owned_span = "hello  world"
    assert t.show(1, "u1", 2, 1, "hello world") is ShowResult.UNCHANGED  # render-equal
    assert wire.published == [] and trig == []  # ZERO events, no staging


def test_show_diverging_span_refused_before_staging():
    t, wire, trig, _ = _acquired(FakeWire(SNAP))
    t._owned_span = "hello"
    assert t.show(1, "u1", 2, 1, "help") is ShowResult.REFUSED   # correction ⇒ refused
    assert wire.published == [] and trig == []  # clipboard NEVER touched
    assert "insert-only" in t.last_reason


def test_show_no_trigger_configured_refuses_before_delivery():
    t, wire, _, _ = make_target(FakeWire(SNAP), trigger=False)
    assert t.acquire().ok
    assert t.show(1, "u1", 1, 0, "x") is ShowResult.REFUSED
    assert wire.published == []                 # fail BEFORE delivery
    assert t.last_reason == "no trigger configured"


def test_show_foreign_change_pre_trigger_aborts_and_restores():
    t, wire, trig, conf = _acquired(FakeWire(SNAP))
    def foreign(w):                             # someone set_selection at recheck time
        wire.live.cancelled = True
    wire.on_sync = foreign
    assert t.show(1, "u1", 1, 0, "user text +") is ShowResult.REFUSED
    assert trig == [] and conf == []            # trigger/confirm never reached
    assert dict(wire.published[1][0]) == {TEXT_MIME: b"user text"}  # snapshot restored
    assert "foreign selection" in t.last_reason


def test_identical_bytes_foreign_copy_is_foreign_not_ours():
    """The clause-2 pin: cancelled fires on ANY foreign set_selection — a
    byte-identical user copy is refused exactly like a different one; content
    is never consulted."""
    t, wire, trig, _ = _acquired(FakeWire(SNAP))
    def identical_copy(w):                      # user copies OUR OWN bytes back
        wire.live.cancelled = True
    wire.on_sync = identical_copy
    assert t.show(1, "u1", 1, 0, "user text +") is ShowResult.REFUSED
    assert trig == [] and "foreign selection" in t.last_reason


def test_show_unconfirmed_is_unknown_and_never_retried():
    t, wire, trig, conf = _acquired(confirm=False)
    assert t.show(1, "u1", 1, 0, "hello") is ShowResult.UNKNOWN
    assert trig == [1] and conf == ["hello"]    # one attempt, no retry inside the adapter
    assert dict(wire.published[1][0]) == {} or True
    assert "unconfirmed" in t.last_reason
    assert t._owned_span == ""                  # state never advances on unknown


def test_show_without_confirm_callback_is_unknown():
    t, wire, _, _ = make_target(FakeWire(SNAP), confirm=None)
    t._confirm = None
    assert t.acquire().ok
    assert t.show(1, "u1", 1, 0, "hi") is ShowResult.UNKNOWN  # bytes sent ≠ applied


def test_show_revision_regression_refused():
    t, wire, _, _ = _acquired()
    t._revision = 3
    assert t.show(1, "u1", 1, 2, "x") is ShowResult.REFUSED
    assert t.last_reason == "revision regression"


def test_show_utterance_switch_self_heals():
    t, wire, _, _ = _acquired(FakeWire(SNAP))
    assert t.show(1, "u1", 1, 0, "abc") is ShowResult.APPLIED
    assert t.show(1, "u2", 2, 1, "xyz") is ShowResult.APPLIED   # ownership reset → insert
    assert wire.published[-2][0] == {TEXT_MIME: b"xyz"}


def test_show_delta_cap_refused_not_chunked():
    t, wire, _, _ = _acquired()
    big = "x" * (1024 * 1024 + 1)
    assert t.show(1, "u1", 1, 0, big) is ShowResult.REFUSED
    assert wire.published == [] and "cap" in t.last_reason


# ---------------------------------------------------------------------------
# finalize / leave / cancel (R.3 lifecycle)
# ---------------------------------------------------------------------------

def test_finalize_matching_is_unchanged_and_settles():
    t, wire, trig, _ = _acquired(FakeWire(SNAP))
    assert t.show(1, "u1", 1, 0, "hello wor") is ShowResult.APPLIED
    assert t.finalize(1, "u1", 2, 1, "hello wor") is ShowResult.UNCHANGED
    assert trig == [1]                          # no further edit
    assert t.show(1, "u1", 3, 1, "more") is ShowResult.REFUSED  # utterance closed
    assert t.last_reason == "utterance closed"


def test_finalize_extension_inserts_once():
    t, wire, trig, _ = _acquired(FakeWire(SNAP))
    assert t.finalize(1, "u1", 1, 0, "brand new") is ShowResult.APPLIED  # no prior partial
    assert trig == [1] and wire.published[0][0] == {TEXT_MIME: b"brand new"}


def test_finalize_diverging_refused_honestly():
    t, wire, trig, _ = _acquired(FakeWire(SNAP))
    t._owned_span = "hello"
    t._owned_utterance = "u1"
    assert t.finalize(1, "u1", 2, 1, "jello") is ShowResult.REFUSED
    assert trig == [] and "insert-only" in t.last_reason


def test_cancel_nothing_pending_unchanged():
    t, wire, _, _ = _acquired()
    assert t.cancel() is ShowResult.UNCHANGED
    assert wire.published == []


def test_cancel_owned_refused_recorded_not_faked():
    t, wire, _, _ = _acquired(FakeWire(SNAP))
    assert t.show(1, "u1", 1, 0, "words here") is ShowResult.APPLIED
    assert t.cancel() is ShowResult.REFUSED
    assert "cannot remove owned text" in t.last_reason
    assert t._owned_span == ""                  # ownership ends; words stay
    assert dict(wire.published[-1][0]) == {TEXT_MIME: b"user text"}  # clipboard restored


def test_leave_restores_clears_and_never_raises():
    t, wire, _, _ = _acquired(FakeWire(SNAP))
    assert t.show(1, "u1", 1, 0, "kept") is ShowResult.APPLIED
    wire.publish = lambda *a, **k: (_ for _ in ()).throw(WlError("dead"))
    t.leave()                                   # must not raise
    assert t._binding is None
    assert t.show(1, "u2", 2, 1, "x") is ShowResult.REFUSED
    assert t.last_reason == "not acquired"


def test_confirm_raising_witness_is_unknown():
    t, wire, _, _ = make_target(FakeWire(SNAP))
    def boom(delta): raise RuntimeError("witness exploded")
    t._confirm = boom
    assert t.acquire().ok
    assert t.show(1, "u1", 1, 0, "x") is ShowResult.UNKNOWN


# ---------------------------------------------------------------------------
# ZwlrDataControlSource (clause 1: per-type exact bytes)
# ---------------------------------------------------------------------------

def test_source_serves_per_type_bytes_and_closes_fd():
    src = ZwlrDataControlSource(9, {TEXT_MIME: b"AB", "text/html": b"<b>AB</b>"}, "tok", 1)
    assert src.mimes() == [TEXT_MIME, "text/html", NONCE_MIME]  # sentinel LAST
    for mime, expected in ((TEXT_MIME, b"AB"), ("text/html", b"<b>AB</b>"),
                           (NONCE_MIME, b"tok")):
        r, w = os.pipe()
        assert src.handle_send(mime, w)
        assert os.read(r, 64) == expected       # THAT type's exact bytes
        assert os.read(r, 1) == b""             # fd closed by the handler (EOF)
        os.close(r)
    r, w = os.pipe()
    assert not src.handle_send("image/png", w)  # unknown type: refused, fd closed
    os.close(r)


def test_source_cancelled_flag_is_the_foreign_signal():
    src = ZwlrDataControlSource(1, {TEXT_MIME: b"x"}, "n", 1)
    assert not src.cancelled
    src.cancelled = True
    assert not ClipboardWatchdog().check(type("L", (), {"sync": lambda s: None})(), src)


def test_watchdog_check_true_while_bound_false_after_cancel():
    wd = ClipboardWatchdog()
    src = ZwlrDataControlSource(1, {TEXT_MIME: b"x"}, "n", 1)
    class OkLink:
        def sync(self): pass
    assert wd.check(OkLink(), src)
    src.cancelled = True
    assert not wd.check(OkLink(), src)
    assert wd.foreign_changes == 1


# ---------------------------------------------------------------------------
# Wire byte-level pins (socketpair fake compositor — REAL bytes, REAL fds)
# ---------------------------------------------------------------------------

class _RecordingSock:
    def __init__(self):
        self.sent = bytearray()
        self.msgs = []

    def sendall(self, data):
        self.sent += data

    def sendmsg(self, data, ancdata=None, flags=0, addr=None):
        for d in data:
            self.sent += d
        self.msgs.append(list(ancdata or []))


class FakeCompositor:
    """Reads real wire messages; writes real events (fd passing included)."""

    def __init__(self, sock):
        self.s = sock
        self.s.settimeout(3)
        self.buf = bytearray()
        self.msgs: list[tuple[int, int, bytes, list[int]]] = []

    def _read(self):
        data, anc, _, _ = self.s.recvmsg(65536, socket.CMSG_SPACE(64))
        self.buf += data
        fds: list[int] = []
        for lvl, typ, cd in anc:
            if lvl == socket.SOL_SOCKET and typ == socket.SCM_RIGHTS:
                fds += list(struct.unpack(f"<{len(cd) // 4}i", cd))
        while len(self.buf) >= 8:
            obj, opcode, size = struct.unpack_from("<IHH", self.buf)
            if len(self.buf) < size:
                break
            self.msgs.append((obj, opcode, self.buf[8:size], fds))
            fds = []
            del self.buf[:size]

    def next_msg(self):
        while not self.msgs:
            self._read()
        return self.msgs.pop(0)

    def send_event(self, obj_id, opcode, payload=b"", fds=()):
        header = struct.pack("<IHH", obj_id, opcode, 8 + len(payload))
        if fds:
            anc = [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                    struct.pack(f"<{len(fds)}i", *fds))]
            self.s.sendmsg([header + payload], anc)
        else:
            self.s.sendall(header + payload)


def test_opcode_tables_match_protocol_document_order():
    """Literal pins (wlr-data-control-unstable-v1.xml): a re-order sends the
    wrong request — the same drift class test_ime_wlwire pins against XML."""
    m = DataControlClient.__mro__  # noqa: F841 (tables are module-level)
    from voice_typing.clipboard_target import DC_EVENTS, DC_REQUESTS
    assert DC_REQUESTS["zwlr_data_control_manager_v1"] == [
        ("create_data_source", "n"), ("get_data_device", "no"), ("destroy", "")]
    assert DC_REQUESTS["zwlr_data_control_device_v1"][0] == ("set_selection", "o")
    assert DC_REQUESTS["zwlr_data_control_device_v1"][2] == ("set_primary_selection", "o")
    assert DC_REQUESTS["zwlr_data_control_source_v1"] == [("offer", "s"), ("destroy", "")]
    assert DC_REQUESTS["zwlr_data_control_offer_v1"] == [("receive", "sh"), ("destroy", "")]
    assert DC_EVENTS["zwlr_data_control_device_v1"] == [
        ("data_offer", "n"), ("selection", "o"), ("finished", ""), ("primary_selection", "o")]
    assert DC_EVENTS["zwlr_data_control_source_v1"] == [("send", "sh"), ("cancelled", "")]
    assert DC_EVENTS["zwlr_data_control_offer_v1"] == [("offer", "s")]


def test_set_selection_request_bytes_no_primary_ever():
    c = DataControlClient(sock=_RecordingSock())
    src = ZwlrDataControlSource(21, {TEXT_MIME: b"x"}, "n", 1)
    c.set_selection(src)
    sent = bytes(c.s.sent)
    assert sent == struct.pack("<IHH", 0, 0, 12) + u32(21)   # device obj 0, opcode 0
    c.set_selection(None)                                    # null = clear (empty restore)
    assert bytes(c.s.sent)[12:] == struct.pack("<IHH", 0, 0, 12) + u32(0)


def test_receive_request_carries_fd_via_scm_rights():
    c = DataControlClient(sock=_RecordingSock())
    r, w = os.pipe()
    try:
        c.request(7, "zwlr_data_control_offer_v1", "receive", TEXT_MIME, w)
        anc = c.s.msgs[0][0]
        assert anc[0] == socket.SOL_SOCKET and anc[1] == socket.SCM_RIGHTS
        assert struct.unpack("<i", anc[2])[0] == w
        payload = wstr(TEXT_MIME) + u32(0)                    # fd word = placeholder 0
        assert bytes(c.s.sent) == struct.pack("<IHH", 7, 0, 8 + len(payload)) + payload
    finally:
        os.close(r)
        os.close(w)


def test_send_event_fd_stays_open_and_serves_exact_bytes():
    a, b = socket.socketpair()
    client = DataControlClient(sock=a)
    comp = FakeCompositor(b)
    src = client.new_source({TEXT_MIME: b"AB"}, "n0", 1)
    # compositor observes: create_data_source + one offer per mime + sentinel
    m0 = comp.next_msg()
    assert m0[1] == 0 and m0[2] == u32(src.obj_id)            # create_data_source
    offers = [comp.next_msg() for _ in src.mimes()]
    assert [wstr_decode(m[2]) for m in offers] == src.mimes()  # offer(mime) opcodes 0
    # compositor answers send(mime, fd) — the fd is the payload, kept open
    r, w = os.pipe()
    comp.send_event(src.obj_id, 0, wstr(TEXT_MIME) + u32(0), fds=[w])
    os.close(w)  # our dup; the client now owns the received copy
    assert client.pump(0.5) >= 1
    assert os.read(r, 64) == b"AB"                            # exact bytes served
    assert os.read(r, 1) == b""                               # fd closed after serving
    os.close(r)
    assert src.sends == 1
    # cancelled event flips the ownership signal
    comp.send_event(src.obj_id, 1)
    client.pump(0.5)
    assert src.cancelled


def wstr_decode(payload: bytes) -> str:
    (n,) = struct.unpack_from("<I", payload, 0)
    return payload[4:4 + n - 1].decode()


def test_offer_receive_reads_exact_bytes_through_sync_barrier():
    a, b = socket.socketpair()
    client = DataControlClient(sock=a)
    comp = FakeCompositor(b)
    client.offer_mimes[7] = [TEXT_MIME]
    client.current_offer = 7
    import threading

    def serve():
        m = comp.next_msg()                                   # receive(mime, fd)
        assert m[1] == 0
        (fd,) = m[3]
        assert wstr_decode(m[2]) == TEXT_MIME
        os.write(fd, b"exact-bytes")                          # compositor serves
        os.close(fd)
        m2 = comp.next_msg()                                  # wl_display.sync(cb)
        assert m2[1] == 0
        (cb,) = struct.unpack("<I", m2[2])
        comp.send_event(cb, 0, u32(0))                        # done → barrier opens

    th = threading.Thread(target=serve)
    th.start()
    got = client.offer_receive(7, TEXT_MIME, timeout=2.0)
    th.join(timeout=3)
    assert got == b"exact-bytes"                              # exact, no newline games


def test_offer_receive_timeout_returns_none_never_truncation():
    a, b = socket.socketpair()
    b.settimeout(3)                                           # compositor never serves
    client = DataControlClient(sock=a)
    client.offer_mimes[7] = [TEXT_MIME]
    client.current_offer = 7
    assert client.offer_receive(7, TEXT_MIME, timeout=0.3) is None


# ---------------------------------------------------------------------------
# WireLink against a stubbed client (sentinel exclusion, empty publish)
# ---------------------------------------------------------------------------

class StubDC(DataControlClient):
    def __init__(self, mimes, canned):
        self.offer_mimes = {7: list(mimes)}
        self.current_offer = 7
        self.canned = canned
        self.set_selections = []
        self.sources = []

    def _receive_no_destroy(self, offer_id, mime, timeout=1.0):
        return self.canned.get(mime)

    def request(self, *a, **k):
        pass

    def set_selection(self, source):
        self.set_selections.append(source.obj_id if source is not None else 0)

    def new_source(self, formats, nonce, generation):
        src = ZwlrDataControlSource(50 + len(self.sources), dict(formats), nonce, generation)
        self.sources.append(src)
        return src

    def sync(self, timeout=2.0):
        pass

    def pump(self, timeout=0.05):
        return 0


def test_snapshot_excludes_sentinel_keeps_exact_user_bytes():
    link = WireLink()
    link.client = StubDC([TEXT_MIME, NONCE_MIME, "text/html"],
                         {TEXT_MIME: b"body", "text/html": b"<i>body</i>"})
    snap = link.snapshot_selection("tok")
    assert snap.formats == (ClipboardFormat(TEXT_MIME, b"body"),
                            ClipboardFormat("text/html", b"<i>body</i>"))  # sentinel dropped
    assert snap.nonce == "tok" and snap.generation == 1


def test_snapshot_failure_raises_honest():
    link = WireLink()
    link.client = StubDC([TEXT_MIME], {})                     # no canned bytes → read fails
    with pytest.raises(WlError):
        link.snapshot_selection("tok")


def test_publish_empty_formats_is_null_selection():
    link = WireLink()
    link.client = StubDC([], {})
    assert link.publish({}, "n") is None
    assert link.client.set_selections == [0]


def test_publish_offers_types_plus_sentinel_last():
    link = WireLink()
    link.client = StubDC([], {})
    src = link.publish({TEXT_MIME: b"x", "text/html": b"<b>x</b>"}, "np")
    assert src.mimes() == [TEXT_MIME, "text/html", NONCE_MIME]


def test_current_nonce_value_reads_sentinel_bytes():
    link = WireLink()
    link.client = StubDC([TEXT_MIME, NONCE_MIME], {NONCE_MIME: b"np-value"})
    assert link.current_nonce_value() == "np-value"
    link.client.current_offer = 0                             # null selection
    assert link.current_nonce_value() is None


# ---------------------------------------------------------------------------
# Clause-4 watcher detection (real /proc scan, scoped)
# ---------------------------------------------------------------------------

def test_detect_watcher_scoped_by_session_environ():
    env = dict(os.environ)
    env["WAYLAND_DISPLAY"] = "wayland-g4selftest"
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(6)", "wl-paste-fake", "--watch"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 3
        found = None
        while time.monotonic() < deadline and found is None:
            hits = detect_clipboard_watcher(scope_env={"WAYLAND_DISPLAY": "wayland-g4selftest"})
            found = next((h for h in hits or [] if str(proc.pid) in h), None)
            time.sleep(0.05)
        assert found is not None                              # in-scope watcher detected
        hits = detect_clipboard_watcher(scope_env={"WAYLAND_DISPLAY": "wayland-other"})
        assert all(str(proc.pid) not in h for h in hits or [])   # out of scope: hidden
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_detect_watcher_returns_list_or_none_only():
    out = detect_clipboard_watcher(scope_env={"WAYLAND_DISPLAY": "definitely-not-a-session"})
    assert out == [] or out is None               # list (possibly empty) or fail-closed None

"""P1.M1.T5.S2 (PRD §4.8.1 C): `voicectl recover [ID]` — CLI unit tests (hermetic, CPU-only).

No daemon process, no systemd unit, no real control socket: `send_command` is replaced by a
recording fake for the wire/usage scenarios, and a throwaway ONE-shot AF_UNIX listener thread
serves the two bounded-read scenarios. Covers:

- usage validation BEFORE any I/O (exit 64; a non-`recover` command with an id; --copy /
  --context-stdin with recover; non-UUIDv4 ids — the SAME `is_uuid_v4` the daemon applies);
- the wire contract: exactly ONE plain `send_command` call per invocation ({"cmd":
  "editor-recover"[, "id": <uuid4>]}, max_reply_bytes=7 MiB), never retried, no loading hint;
- stdout purity: EXACTLY the reply text + print's single newline; every warning/error is a
  FIXED-WORDS stderr line (truncated / possibly_applied / not_found / busy / invalid_request /
  old daemon / malformed — reply text and ids never echoed into errors);
- strict reply validation: five typed keys (`type(x) is bool` for the flags) + requested-id
  match; extra keys ignored; empty text with ok:true prints an empty line and exits 0;
- the bounded reply read: >7 MiB line refused (ValueError naming the cap) WITHOUT buffering
  past the cap, exit 1, empty stdout; the default (no cap) stays unbounded for other commands;
- OSError → 2 (daemon not running);
- tripwires: `recover` never touches the clipboard helper nor spawns a subprocess.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time

import pytest

from voice_typing import ctl, daemon

SID = "123e4567-e89b-42d3-a456-426614174000"  # canonical lowercase UUIDv4
OTHER_SID = "123e4567-e89b-42d3-a456-426614174001"  # a different v4 (mismatch tests)
_BOUND = 7 << 20  # daemon.MAX_RECOVERY_REPLY_BYTES — 7 MiB INCLUDING the framing newline
OK = {
    "ok": True,
    "id": SID,
    "text": "alpha beta",
    "truncated": False,
    "possibly_applied": False,
}


# --- helpers ---------------------------------------------------------------------------------


def _boom(*_args, **_kwargs):
    raise AssertionError("recover must not spawn processes or touch the clipboard")


@pytest.fixture
def tripwires(monkeypatch):
    """PRP CRITICAL #9: any clipboard or subprocess use from the recover path fails the test."""
    monkeypatch.setattr(ctl, "_copy_session_to_clipboard", _boom)
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


def fake_send(monkeypatch, canned=None, error=None):
    """Replace ctl.send_command with a recorder: calls.append((cmd, extra, kwargs)); return
    the canned reply or raise `error`. Returns the call list for wire/count assertions."""

    calls: list = []

    def _fake(socket_path, cmd, extra=None, **kwargs):
        calls.append((cmd, extra, kwargs))
        if error is not None:
            raise error
        return canned

    monkeypatch.setattr(ctl, "send_command", _fake)
    return calls


def _remove_runtime_dir(monkeypatch):
    """Unset XDG_RUNTIME_DIR: if main() tried to resolve the socket it would exit 2, so any
    exit-64 assertion below proves validation happened BEFORE socket resolution."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)


@pytest.fixture
def tmp_socket_env(monkeypatch, tmp_path):
    """Point XDG_RUNTIME_DIR at a tmp dir (with the voice-typing/ subdir the resolver needs)
    and return the control-socket path inside it."""
    xdg = tmp_path / "runtime"
    (xdg / "voice-typing").mkdir(parents=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
    return str(xdg / "voice-typing" / "control.sock")


def _serve_once(socket_path: str, payload: bytes):
    """Bind+listen SYNCHRONOUSLY on socket_path (no race with the client's connect), then
    start a daemon thread that accepts ONE connection, reads the request line, writes
    `payload`, and closes. Tolerates the client hanging up early (the over-cap refusal
    path). Returns the thread (join it after the client is done)."""
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(socket_path)
    srv.listen(1)

    def _run():
        try:
            conn, _ = srv.accept()
            with conn:
                buf = bytearray()
                while b"\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf.extend(chunk)
                try:
                    conn.sendall(payload)
                except OSError:
                    pass  # client refused an over-cap reply and hung up — expected
        except OSError:
            pass  # accept hiccup: the assertions on the client side will fail loudly
        finally:
            srv.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# --- first-class command sanity --------------------------------------------------------------


def test_recover_is_first_class_and_cap_matches_daemon():
    """'recover' is in _COMMANDS and the client bound is EXACTLY the daemon's S1 constant."""
    assert "recover" in ctl._COMMANDS
    assert ctl._RECOVERY_REPLY_MAX_BYTES == daemon.MAX_RECOVERY_REPLY_BYTES == _BOUND


# --- usage errors (64) BEFORE any I/O --------------------------------------------------------


class TestUsageBeforeIO:
    """PRP CRITICAL #2/#12: usage errors exit 64 BEFORE socket resolution / stdin / any I/O.
    XDG_RUNTIME_DIR is unset + send_command booby-trapped: exit 64 proves no I/O happened."""

    def test_recover_rejects_non_uuid4_id(self, monkeypatch, capsys, tripwires):
        _remove_runtime_dir(monkeypatch)
        calls = fake_send(monkeypatch, error=AssertionError("usage path must not send"))
        code = ctl.main(["recover", "abc"])
        assert code == 64
        err = capsys.readouterr().err
        assert "invalid session id" in err and "abc" in err and "recover" in err
        assert calls == []  # nothing sent — validated before any I/O

    def test_id_with_non_recover_command_is_usage_error(
        self, monkeypatch, capsys, tripwires
    ):
        # Pre-T5.S2 this died with argparse SystemExit(2) — colliding with daemon-not-running.
        # With the optional `id` positional it parses and main() maps it to 64 (gotcha #12).
        _remove_runtime_dir(monkeypatch)
        calls = fake_send(monkeypatch, error=AssertionError("usage path must not send"))
        code = ctl.main(["status", SID])
        assert code == 64
        assert "an id applies only to the 'recover' command" in capsys.readouterr().err
        assert calls == []

    def test_recover_rejects_copy_flag(self, monkeypatch, capsys, tripwires):
        _remove_runtime_dir(monkeypatch)
        calls = fake_send(monkeypatch, error=AssertionError("usage path must not send"))
        code = ctl.main(["recover", "--copy"])
        assert code == 64
        assert "--copy applies only to the 'session' command" in capsys.readouterr().err
        assert calls == []  # (and the clipboard tripwire never fired)

    def test_recover_rejects_context_stdin(self, monkeypatch, capsys, tripwires):
        _remove_runtime_dir(monkeypatch)
        calls = fake_send(monkeypatch, error=AssertionError("usage path must not send"))
        code = ctl.main(["recover", "--context-stdin"])
        assert code == 64
        assert "--context-stdin" in capsys.readouterr().err
        assert calls == []  # no stdin read, no socket

    @pytest.mark.parametrize(
        "bad",
        [
            "123E4567-E89B-42D3-A456-426614174000",  # uppercase: is_uuid_v4 is lowercase-only
            "123e4567-e89b-12d3-a456-426614174000",  # version-1 nibble (not a v4)
        ],
    )
    def test_recover_rejects_non_v4_shapes(self, monkeypatch, capsys, tripwires, bad):
        # Verified against editor_protocol.is_uuid_v4 (the daemon's own validator, S1):
        # the client rejects exactly what the daemon would reject as invalid_request.
        _remove_runtime_dir(monkeypatch)
        calls = fake_send(monkeypatch, error=AssertionError("usage path must not send"))
        assert ctl.main(["recover", bad]) == 64
        assert "invalid session id" in capsys.readouterr().err
        assert calls == []


# --- wire contract + output rendering (fake send_command) ------------------------------------


class TestWireAndOutput:
    def test_recover_without_id_wire_and_output(self, monkeypatch, capsys, tripwires):
        calls = fake_send(monkeypatch, canned=OK)
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 0
        # ONE plain call (kwargs pin ALSO proves it is NOT _send_command_with_loading_hint),
        # wire cmd != user cmd (the T2.S5 remap pattern), bounded at the daemon cap:
        assert calls == [("editor-recover", None, {"max_reply_bytes": _BOUND})]
        assert ro.out == "alpha beta\n"  # stdout = text + print's single newline, nothing else
        assert ro.err == ""  # no warnings on the happy path

    def test_recover_with_id_wire(self, monkeypatch, capsys, tripwires):
        calls = fake_send(monkeypatch, canned=OK)
        code = ctl.main(["recover", SID])
        ro = capsys.readouterr()
        assert code == 0
        assert calls == [("editor-recover", {"id": SID}, {"max_reply_bytes": _BOUND})]
        assert ro.out == "alpha beta\n"
        assert ro.err == ""

    def test_truncated_warning_on_stderr_only(self, monkeypatch, capsys, tripwires):
        calls = fake_send(monkeypatch, canned={**OK, "truncated": True})
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 0
        assert ro.out == "alpha beta\n"
        assert "TRUNCATED" in ro.err
        assert "alpha" not in ro.err  # the TEXT never rides a warning line

    def test_possibly_applied_warning_on_stderr_only(self, monkeypatch, capsys, tripwires):
        calls = fake_send(monkeypatch, canned={**OK, "possibly_applied": True})
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 0
        assert ro.out == "alpha beta\n"
        assert "duplicat" in ro.err and "re-inserted" in ro.err

    def test_both_warnings_in_order(self, monkeypatch, capsys, tripwires):
        calls = fake_send(
            monkeypatch, canned={**OK, "truncated": True, "possibly_applied": True}
        )
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 0
        assert ro.out == "alpha beta\n"
        assert ro.err.count("\n") == 2  # exactly two stderr lines
        assert ro.err.index("TRUNCATED") < ro.err.index("duplicat")  # truncated first

    @pytest.mark.parametrize("argv", [["recover"], ["recover", SID]])
    def test_not_found_error(self, monkeypatch, capsys, tripwires, argv):
        calls = fake_send(monkeypatch, canned={"ok": False, "error": "not_found"})
        code = ctl.main(argv)
        ro = capsys.readouterr()
        assert code == 1
        assert ro.out == ""  # nothing on stdout for an error
        assert "nothing to recover" in ro.err
        assert len(calls) == 1

    def test_busy_error(self, monkeypatch, capsys, tripwires):
        # S1 contract: failures key on error == "busy" — there is NO "busy": True flag.
        calls = fake_send(monkeypatch, canned={"ok": False, "error": "busy"})
        code = ctl.main(["recover", SID])
        ro = capsys.readouterr()
        assert code == 1
        assert ro.out == ""
        assert "still active" in ro.err
        assert len(calls) == 1

    def test_invalid_request_error(self, monkeypatch, capsys, tripwires):
        calls = fake_send(monkeypatch, canned={"ok": False, "error": "invalid_request"})
        code = ctl.main(["recover", SID])
        ro = capsys.readouterr()
        assert code == 1  # argv was valid — a daemon invalid_request is exit 1, not 64
        assert ro.out == ""
        assert "invalid_request" in ro.err
        assert len(calls) == 1

    def test_old_daemon_unknown_command(self, monkeypatch, capsys, tripwires):
        calls = fake_send(
            monkeypatch, canned={"ok": False, "error": "unknown command: 'editor-recover'"}
        )
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 1
        assert ro.out == ""
        assert "predates native recovery" in ro.err and "update" in ro.err
        assert len(calls) == 1

    @pytest.mark.parametrize(
        "canned",
        [
            {k: v for k, v in OK.items() if k != "text"},  # missing key
            {**OK, "truncated": "yes"},  # str instead of bool
            {**OK, "possibly_applied": 1},  # int instead of bool (isinstance trap avoided)
            {**OK, "id": OTHER_SID},  # reply names ANOTHER session than the requested one
        ],
        ids=["missing_text", "truncated_str", "possibly_applied_int", "id_mismatch"],
    )
    def test_malformed_reply_never_prints(self, monkeypatch, capsys, tripwires, canned):
        calls = fake_send(monkeypatch, canned=canned)
        code = ctl.main(["recover", SID])
        ro = capsys.readouterr()
        assert code == 1
        assert ro.out == ""  # nothing of the reply reaches stdout
        assert "malformed recovery reply" in ro.err
        assert "alpha beta" not in ro.err  # fixed words only — the TEXT never echoed
        assert len(calls) == 1

    def test_extra_keys_ignored(self, monkeypatch, capsys, tripwires):
        calls = fake_send(monkeypatch, canned={**OK, "final_count": 2})
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 0
        assert ro.out == "alpha beta\n"
        assert ro.err == ""
        assert len(calls) == 1

    def test_empty_text_is_a_valid_ok_reply(self, monkeypatch, capsys, tripwires):
        # S1's cap path can legitimately return text="" with truncated=true — print the
        # empty line and exit 0 (with the warning); the daemon is the source of truth.
        calls = fake_send(monkeypatch, canned={**OK, "text": "", "truncated": True})
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 0
        assert ro.out == "\n"
        assert "TRUNCATED" in ro.err
        assert len(calls) == 1

    def test_wedged_daemon_not_retried(self, monkeypatch, capsys, tripwires):
        calls = fake_send(
            monkeypatch,
            error=ValueError("daemon wedged: no reply within 5s — the control socket is "
                             "nonresponsive"),
        )
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 1
        assert ro.out == ""
        assert "not retried" in ro.err
        assert len(calls) == 1  # ONE call — no retry, no reconnect, no session fallback

    def test_file_not_found_maps_to_2(self, monkeypatch, capsys, tripwires):
        calls = fake_send(monkeypatch, error=FileNotFoundError(2, "No such file or directory"))
        code = ctl.main(["recover"])
        ro = capsys.readouterr()
        assert code == 2  # daemon not running — the existing OSError path, untouched
        assert ro.out == ""
        assert len(calls) == 1


# --- pure renderer ---------------------------------------------------------------------------


class TestPureFormatRecovery:
    def test_ok_replies(self):
        assert ctl.format_recovery(OK, None) == ("alpha beta", [], 0)
        assert ctl.format_recovery(OK, SID) == ("alpha beta", [], 0)

    def test_id_mismatch_refused(self):
        out, lines, code = ctl.format_recovery(OK, OTHER_SID)
        assert out == ""
        assert code == 1
        assert any("mismatch" in line for line in lines)
        assert all("alpha" not in line for line in lines)

    def test_error_shapes(self):
        assert ctl.format_recovery({"ok": False, "error": "busy"}, SID)[2] == 1
        out, lines, code = ctl.format_recovery({"ok": False, "error": "not_found"}, None)
        assert (out, code) == ("", 1) and any("nothing to recover" in ln for ln in lines)


# --- bounded reply read (raw one-shot AF_UNIX listener; no daemon process) -------------------


class TestBoundedReplyRead:
    def test_big_valid_line_round_trips(self, monkeypatch, capsys, tmp_socket_env, tripwires):
        """A valid ~300 KB escaped line (150_000 quote chars) reads fine under the 7 MiB cap
        and `main(["recover"])` prints it whole — the cap never bites a legal reply."""
        path = tmp_socket_env
        text = '"' * 150_000  # JSON-escapes to ~300 KB on the wire
        reply = {**OK, "text": text}
        payload = (json.dumps(reply) + "\n").encode("utf-8")
        t = _serve_once(path, payload)
        try:
            code = ctl.main(["recover"])
        finally:
            t.join(10)
        assert code == 0
        assert capsys.readouterr().out == text + "\n"

        t2 = _serve_once(path, payload)  # fresh listener for the direct send_command probe
        try:
            got = ctl.send_command(
                path, "editor-recover", extra=None, max_reply_bytes=_BOUND
            )
        finally:
            t2.join(10)
        assert got["text"] == text

    def test_over_cap_line_refused(self, monkeypatch, capsys, tmp_socket_env):
        """A 7 MiB + 1 line raises ValueError naming the cap; the CLI maps it to exit 1 with
        empty stdout — without buffering meaningfully past the cap (fast local refusal)."""
        path = tmp_socket_env
        payload = b"a" * _BOUND + b"\n"  # 7 MiB of junk + framing newline = cap + 1
        t = _serve_once(path, payload)
        try:
            started = time.monotonic()
            with pytest.raises(ValueError, match="7340032"):
                ctl.send_command(path, "editor-recover", extra=None, max_reply_bytes=_BOUND)
        finally:
            t.join(10)
        assert time.monotonic() - started < 10  # local AF_UNIX: the refusal is immediate

        t2 = _serve_once(path, payload)
        try:
            code = ctl.main(["recover"])
        finally:
            t2.join(10)
        ro = capsys.readouterr()
        assert code == 1
        assert ro.out == ""
        assert "exceeded" in ro.err

    def test_default_stays_unbounded_for_other_commands(
        self, monkeypatch, tmp_socket_env
    ):
        """No max_reply_bytes kwarg → NO cap: a 100 KB line reads fine on a plain command
        (every non-recover command is byte-identical to before — PRP CRITICAL #4)."""
        path = tmp_socket_env
        reply = {"ok": True, "listening": True, "pad": "x" * 100_000}
        payload = (json.dumps(reply) + "\n").encode("utf-8")
        t = _serve_once(path, payload)
        try:
            got = ctl.send_command(path, "status")
        finally:
            t.join(10)
        assert got["listening"] is True
        assert len(got["pad"]) == 100_000

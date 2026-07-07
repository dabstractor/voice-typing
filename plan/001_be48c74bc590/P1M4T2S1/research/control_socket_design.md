# Research — P1.M4.T2.S1: Control socket server (JSON-lines over AF_UNIX)

This doc is the design + verification record for `ControlServer` (the `voicectl`↔daemon
wire protocol). It is the spec the PRP pins. Everything below was either (a) read from the
live codebase at `voice_typing/{daemon,feedback,config,cuda_check}.py` + `tests/test_*.py`
(S1+S2 merged, **134 passing**), (b) verified empirically with a throwaway AF_UNIX server
run under `.venv/bin/python` (see §6 — the verbatim output), or (c) cross-checked against
the Python stdlib + Linux man-page references in §7.

---

## 1. The deliverable + boundaries (what S1 ships vs. what it does NOT)

**Ship:** a standalone `ControlServer` class in `voice_typing/daemon.py` that:
- listens on `$XDG_RUNTIME_DIR/voice-typing/control.sock` (AF_UNIX, SOCK_STREAM);
- accepts connections in a background daemon thread, one daemon worker per connection;
- speaks one-JSON-object-per-line in / one-per-line out (the PRD §4.2 protocol);
- dispatches `toggle`/`start`/`stop`/`status`/`quit` to the daemon and replies;
- is robust to malformed JSON (`{"ok":false,"error":...}`);
- exposes `start()` / `stop()` and survives a stale `.sock` (unlink-before-bind).

**Also ship (minimal additive helpers, see §4):**
- `VoiceTypingDaemon.status_snapshot() -> dict` — the status payload authority
  (listening/partial/last_final/uptime_s/device/models).
- `Feedback.snapshot() -> dict` — public read of the live in-memory state (partial/last_final).

**Do NOT ship (out of scope — owned by later items):**
- `main()` / `if __name__ == "__main__":` / signal handlers → **P1.M4.T3.S1**.
- `recorder.shutdown()` + full clean teardown on quit → **P1.M4.T2.S2** (S1's `quit` only
  calls `daemon.request_shutdown()` + replies; S2 wires the recorder teardown).
- auto-wiring `ControlServer` into `VoiceTypingDaemon.run()`/`__init__` → **T3** constructs +
  starts it in `main()`. S1 keeps the daemon socket-agnostic (cleaner separation; every test
  builds `ControlServer` explicitly).
- `voicectl` client (`voice_typing/ctl.py`) → **P1.M5.T1.S1**.

### Parallel-context contract: P1.M4.T1.S3 (latency logging) is being implemented NOW

S3 is the immediately-preceding item and edits `voice_typing/daemon.py` + `config.py`. S1
runs AFTER S3 merges, so the live source S1 edits is the **post-S3** file. S3's edits S1
must coexist with (from S3's PRP, treated as a contract):
- adds `import collections`; adds module-level `LatencyLog`, `_LATENCY_LOG_PREFIX`,
  `_LATENCY_RING_SIZE`, `_ms()`.
- `_build_callbacks(fb, latency=None)`, `_construct(cfg, fb, cls, latency=None)`,
  `build_recorder(cfg, fb, latency=None)` — optional trailing `latency` param (default None).
- `VoiceTypingDaemon.__init__(..., latency=None)` creates `self._latency`.
- `run()` calls `self._configure_log_level()` + `self._log_resolved_device()` before the loop.
- `on_final` tail is replaced with latency capture + the `voice-typing latency:` structured log.
- `config.py` gains `LogConfig` + a `log` field; `config.toml` gains `[log]`.

**S1's edits are 100% ADDITIVE and do NOT touch any symbol S3 edits** (no `__init__`/`run()`/
`on_final`/`_build_callbacks`/`_construct`/`build_recorder` change; no `config.py`/`config.toml`
change). S1 only: (a) adds stdlib imports, (b) adds `_default_control_socket_path()`, (c) adds
`VoiceTypingDaemon.status_snapshot()` + `_resolved_device()` (new methods, no existing-method
edit), (d) adds the `ControlServer` class at module end. **Zero overlap with S3 → no merge
conflict possible.** (§5 proves S1/S2/S3 tests stay green.)

---

## 2. The wire protocol (EXACT responses — tests + voicectl depend on these)

PRD §4.2 + the work-item contract. S1 returns a **uniform status payload** for
`toggle`/`start`/`status`/`stop`: every one replies `{"ok": true, **status_snapshot()}`.
The PRD's minimal shapes (`{"ok":true,"listening":true}` for toggle; `...,"partial","uptime_s"`
for start/stop/status) are a **SUBSET** of S1's payload — extra keys (`last_final`, `device`,
`final_model`, `realtime_model`, `compute_type`) are additive and JSON clients ignore unknown
keys, so voicectl (T5) simply selects the keys it formats. Uniform payload = one response
builder = easy to pin in tests + uniformly useful to `voicectl` after ANY command.

```
REQUEST (one JSON object per line)              RESPONSE (one JSON object per line)
-------------------------------------------     ---------------------------------------------------------
{"cmd":"toggle"}                                {"ok":true,"listening":<new>,"partial":"..","last_final":"..",
                                                 "uptime_s":<float>,"device":"..","compute_type":"..",
                                                 "final_model":"..","realtime_model":".."}
{"cmd":"start"}                                 {"ok":true,"listening":true, ...<same status keys>...}
{"cmd":"stop"}                                  {"ok":true,"listening":false, ...<same status keys>...}
{"cmd":"status"}                                {"ok":true, ...<same status keys>...}   (read-only; no state change)
{"cmd":"quit"}                                  {"ok":true,"shutting_down":true}        (→ daemon.request_shutdown())
<not a JSON object, e.g. "hi" or 5 or [1]>      {"ok":false,"error":"request must be a JSON object"}
<malformed JSON, e.g. "not json{">              {"ok":false,"error":"malformed JSON: Expecting value: ..."}
<unknown / missing cmd>                         {"ok":false,"error":"unknown command: 'foo'"} / "unknown command: None"
```

`status_snapshot()` key semantics:
- `listening` — `daemon.is_listening()` (bool).
- `partial` / `last_final` — from `Feedback.snapshot()` (the **live in-memory** state, NOT the
  throttled state.json on disk — disk lags ≥10 Hz; memory is always current).
- `uptime_s` — `round(daemon.uptime_s, 3)` (seconds since `run()` set `_start_monotonic`; 0.0
  before `run()`).
- `device` / `compute_type` / `final_model` / `realtime_model` — from `_resolve_device_config(cfg)`
  (the SAME resolution `build_recorder` used to construct the recorder → status matches the
  actually-loaded models), **cached on first call** (cuda_check probes once; see §4).
- `quit` replies `{"ok":true,"shutting_down":true}` (no status keys — the daemon is going down).

**One connection may carry MANY lines** (the readline loop): each non-empty line gets exactly
one response line; empty lines are skipped (continue, no response). voicectl is one-shot
(one line → one response → close); a persistent client issuing several commands in one
connection also works. On `quit`, the worker writes the reply, flushes, then breaks the loop.

---

## 3. The accept loop — `select()` polling, NOT close-to-unblock (CRITICAL)

### The empirical finding (verified, §6)

Sockets 101 says "close the listening socket from `stop()` to unblock a blocked `accept()`".
**That does NOT work reliably here.** A throwaway server closed its listening socket from the
main thread; `accept()` in the worker **did not raise** — the loop never exited
(`accept loop exited: False`). This matches the Linux `close(2)` NOTES: closing an fd another
thread is blocked on is *unspecified*, and the freed fd number can be reused before the woken
syscall re-reads it (fd-reuse race). So **close-to-unblock is unsafe as the sole stop path.**

### The fix: `select.select([sock], [], [], timeout)` + a stop `threading.Event`

```python
def _accept_loop(self) -> None:
    sock = self._sock
    while not self._stop.is_set():
        try:
            ready, _, _ = select.select([sock], [], [], self._accept_timeout)  # 0.3–0.5 s
        except (OSError, ValueError):
            break                       # listening socket closed (stop()) → select raises
        if not ready:
            continue                    # poll timeout → re-check the stop event
        try:
            conn, _ = sock.accept()
        except OSError:
            break                       # socket closed between select and accept
        threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
```

`select` with a short timeout returns either a ready socket (accept it) or nothing (re-check
`_stop`). `stop()` sets the event → the next `select` tick returns within `_accept_timeout` and
the loop checks the event and exits. Verified clean: the worker thread **returns within 1 s of
`stop()`** with no socket close required (§6). `stop()` ALSO closes the socket (belt-and-
suspenders: makes any blocked `select`/`accept` raise immediately) + `join(timeout=2.0)`.

### Why `select` and NOT `socket.settimeout` (a subtle makefile trap)

`socket.makefile()` **raises `OSError` if the socket has a timeout set** ("the socket must be
in blocking mode" — Python docs). If we `settimeout` on the *listening* socket, the connection
sockets returned by `accept()` would risk inheriting it and `makefile` would break. `select`
leaves the socket in **blocking mode** → every accepted `conn` is blocking → `makefile("r")`/
`("w")` work cleanly. (Verified in §6: makefile readline + flush round-trips on every path.)

This mirrors the stdlib `socketserver.serve_forever`/`shutdown()` design (a `selectors` loop +
an internal stop flag) — the only documented-portable way to `stop()` a blocking server cleanly.

---

## 4. `status_snapshot()` + `Feedback.snapshot()` + the lazy device cache

### `Feedback.snapshot()` (additive, `feedback.py`)
```python
def snapshot(self) -> dict:
    """A shallow copy of the live in-memory state (listening/phase/partial/last_final/ts).

    For low-latency status reads (control socket `status` cmd) WITHOUT hitting the throttled
    state.json on disk. Safe to call from any thread (CPython dict copy is atomic here)."""
    return dict(self._state)
```
`feedback._state` is the single source of truth for `partial`/`last_final`; reading it via a
public accessor (not reaching into `daemon._feedback._state`) keeps encapsulation clean. The
disk `state.json` is throttled (≥10 Hz write cap, P1.M3.T2.S1) and may lag — status must show
the CURRENT partial, so the in-memory snapshot is correct. Additive → `test_feedback.py` stays
green (existing assertions unchanged); 1–2 new snapshot tests appended.

### `VoiceTypingDaemon.status_snapshot()` (additive, `daemon.py`)
```python
def status_snapshot(self) -> dict:
    snap = self._feedback.snapshot()
    dev = self._resolved_device()
    return {
        "listening": self.is_listening(),
        "partial": snap.get("partial", ""),
        "last_final": snap.get("last_final", ""),
        "uptime_s": round(self.uptime_s, 3),
        "device": dev.get("device", "unknown"),
        "compute_type": dev.get("compute_type", "unknown"),
        "final_model": dev.get("final_model", "unknown"),
        "realtime_model": dev.get("realtime_model", "unknown"),
    }
```
**No `__init__` / `run()` / `on_final` edit** — purely a new method, so zero S2/S3 conflict.

### `_resolved_device()` — lazy cache via `getattr` (no `__init__` edit)
`_resolve_device_config(cfg)` → `cuda_check.resolve_device_and_models()` → imports
`ctranslate2` + calls `get_cuda_device_count()`. That probe is **expensive** (heavy import) and
must run **at most once** — never per-status-call. Caching via `getattr`/`setattr` avoids
touching `__init__` (which S3 edits; no overlap = no conflict):
```python
def _resolved_device(self) -> dict[str, str]:
    resolved = getattr(self, "_resolved_device_cache", None)
    if resolved is None:
        try:
            resolved = _resolve_device_config(self._cfg)   # cuda_check probe (once)
        except Exception as exc:                           # any probe failure → degrade gracefully
            logger.warning("status: device resolution failed (%s); reporting 'unknown'", exc)
            resolved = {"device": "unknown", "compute_type": "unknown",
                        "final_model": "unknown", "realtime_model": "unknown"}
        self._resolved_device_cache = resolved
    return resolved
```
- **Production:** `ctranslate2` is already imported by `build_recorder` at daemon start, so the
  first `status` is fast (just `get_cuda_device_count()`).
- **Tests:** `status_snapshot()` unit tests monkeypatch `daemon._resolve_device_config` (or
  `daemon.cuda_check.resolve_device_and_models`) for hermeticity — the SAME `_cuda_resolve`
  helper S1's tests use. The `try/except` is the production safety net, not the test tool.
- Why match `build_recorder`'s resolution (not re-probe ad hoc): status must report the models
  the recorder ACTUALLY loaded. Reusing `_resolve_device_config(cfg)` (the S1 module helper)
  guarantees status == build-time device/models.

---

## 5. Backward compatibility (S1+S2+S3 tests stay green; full suite grows ~25 tests)

- `VoiceTypingDaemon` gains 2 methods (`status_snapshot`, `_resolved_device`); NO existing
  method changes → all 134 S1/S2 (+~10 S3) assertions unchanged.
- `import voice_typing.daemon` stays import-pure: S1 adds only `json`/`os`/`select`/`socket`
  (all stdlib-cheap). `RealtimeSTT`/`torch`/`ctranslate2` remain lazily imported inside
  `build_recorder` (unchanged). The import-purity AST/grep gate still passes.
- `Feedback.snapshot()` is additive → `test_feedback.py` (existing assertions) unchanged.
- `ControlServer` is a NEW top-level class (no symbol collision). Tests construct it with a
  stub daemon (dispatch) or a real daemon + `_StubRecorder` + explicit `socket_path=tmp_path`
  (round-trip). No real mic, no RealtimeSTT, no CUDA.
- `_default_control_socket_path()` mirrors `FeedbackConfig.resolved_state_file()`: raises
  `RuntimeError` if `XDG_RUNTIME_DIR` is unset (no safe default — fail clearly). Tests pass an
  explicit `socket_path` so they never depend on `XDG_RUNTIME_DIR`.
- Expected final count: 134 (S1+S2) + ~10 (S3) + ~25 (S1 of T2) ≈ **169 passed**.

---

## 6. Empirical verification (run under `.venv/bin/python`; verbatim output)

### Run 1 — close-to-unblock FAILS (why we use `select`)
```
toggle: {'ok': True, 'echo': {'cmd': 'toggle'}}     # makefile round-trip OK
accept loop exited: False                            # ← srv.close() did NOT unblock accept()!
stale file exists after close: True                  # close leaves the .sock file (unlink needed)
bind without unlink raised: OSError                  # stale .sock blocks re-bind
bind after unlink: OK                                # unlink-before-bind recovers
```

### Run 2 — `select`-based accept + stop + makefile (the chosen design)
```
status:        {"ok": true, "cmd": "status"}                      # happy path
malformed:     {"ok": false, "error": "malformed: Expecting value: ..."}   # json error
non-dict:      {"ok": false, "error": "not an object"}            # bare number → error
empty-then-cmd:{"ok": true, "cmd": "toggle"}                      # empty line skipped
multi-line:    {"ok": true, "cmd": "start"}  {"ok": true, "cmd": "stop"}    # 2 lines → 2 responses
accept loop RETURNED cleanly                                      # ← stop.set() → loop exited
accept thread exited within 1s: True    thread alive after stop: False        # clean shutdown!
socket perms: 0o600                                               # chmod after bind works
```
**Conclusion:** `select` + stop-Event is correct + clean; close-to-unblock is unreliable.

---

## 7. Best-practice references (URLs)

```yaml
- url: https://docs.python.org/3/library/socket.html#socket.socket.makefile
  why: makefile returns a buffered file object over the socket; ONLY valid in blocking mode
       (raises OSError if a timeout is set). Separate makefile("r") + makefile("w") over one
       socket are independent. Closing a file object does NOT replace socket.close().
  critical: this is why we use select (no socket timeout) instead of settimeout — settimeout
            would make makefile raise on the accepted connection sockets.

- url: https://docs.python.org/3/library/socket.html#socket.socket.bind
  why: AF_UNIX bind() takes a filesystem path; binding an EXISTING path → OSError EADDRINUSE.
        Fix is unlink-before-bind (try/except FileNotFoundError), NOT SO_REUSEADDR (no-op on
        AF_UNIX path sockets — unix(7)).
  critical: SO_REUSEADDR is meaningless for unix path sockets; the file MUST be unlinked.

- url: https://man7.org/linux/man-pages/man7/unix.7.html
  why: authoritative OS semantics — unix socket address is a pathname; access is gated by the
        socket-file perms + every dir traversed to reach it (so dir 0700 + file 0600 both matter).
  critical: chmod the socket 0600 after bind + keep $XDG_RUNTIME_DIR/voice-typing/ at 0700.

- url: https://man7.org/linux/man-pages/man2/close.2.html#NOTES
  why: close(2) NOTES — closing an fd another thread is blocked on is UNSPECIFIED; the fd number
        may be reused before the woken syscall re-reads it (fd-reuse race).
  critical: do NOT rely on close-to-unblock accept(). Use select()+stop-Event (Run 2 proves it).

- url: https://docs.python.org/3/library/socketserver.html#socketserver.BaseServer.serve_forever
  why: serve_forever()/shutdown() is the canonical clean-stop design — a selectors loop + poll
        interval + an internal stop flag (exactly our select()+Event approach).
  critical: this is the pattern we mirror by hand (hand-rolled gives start()/stop() + direct
            JSON dispatch control; ThreadingUnixStreamServer is the heavier alternative).

- url: https://docs.python.org/3/library/json.html#json.JSONDecodeError
  why: malformed-JSON handling — catch json.JSONDecodeError, reply {"ok":false,"error":...}.
  critical: also reject non-dict JSON (bare string/number/array) — request must be a JSON object.

- url: https://docs.python.org/3/library/os.html#os.unlink
  why: stale-socket cleanup (unlink, tolerating FileNotFoundError) + os.chmod (0600 hardening).

- url: https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
  why: $XDG_RUNTIME_DIR is the correct, owner-only (0700, pam_systemd-managed) location for a
        per-user runtime socket (/run/user/$UID/voice-typing/control.sock).
```

---

## 8. Test strategy (mirrors S1/S2 house style — stubs, tmp_path, monkeypatch, _wait_for)

Three layers (all in `tests/test_control_socket.py`, a NEW file — do NOT edit S1/S2/S3 test bodies):

**A. Dispatch logic (no socket).** A `_StubDaemon` duck-type (records toggle/start/stop/quit +
canned `status_snapshot`/`is_listening`/`uptime_s`). Call `ControlServer._dispatch(json_str)`
directly; assert the returned dict for: toggle/start/stop/status/quit/unknown-cmd/missing-cmd/
malformed-JSON/non-dict-JSON/empty-handling. Fast, deterministic, no I/O.

**B. Real socket round-trip (tmp_path socket_path, stub daemon).** `ControlServer(stub,
socket_path=tmp_path/"c.sock").start()`; a client connects, sends `{"cmd":"status"}\n`, reads
one line, `json.loads`, asserts shape. Also: multi-line-in-one-connection → N responses; quit
replies `{"ok":true,"shutting_down":true}` + calls `daemon.request_shutdown()`; malformed JSON
over the wire → `{"ok":false,"error":...}`. Reuse the `_send(path, msg)` helper.

**C. Lifecycle + hardening.** `start()` is idempotent (double-start = one thread); `start()`
creates dir 0700 + socket 0600; stale `.sock` recovery (pre-create a file at the path → start()
unlinks + binds cleanly); `stop()` joins the accept thread within ~1 s (select-poll) and the
socket file is gone; `_default_control_socket_path()` honors `XDG_RUNTIME_DIR` (monkeypatch) and
raises `RuntimeError` when unset. Use the existing `_wait_for(predicate, timeout=2.0)` helper
(from `tests/test_daemon.py`) for the thread-join assertions.

**D. status_snapshot unit tests (`tests/test_daemon.py`, APPENDED).** Use `_make_daemon()` (the
S2 helper) + monkeypatch `daemon._resolve_device_config` (cuda path) → assert snapshot keys +
values (listening mirrors `is_listening()`, partial/last_final from feedback, uptime_s≈0 before
run, device=cuda/float16/distil-large-v3/small.en; cpu path → the CPU_FALLBACK models). Also:
`_resolved_device()` caches (resolve called once across two snapshots); a resolve failure →
device="unknown" (no crash).

Validation gates: `.venv/bin/python -m py_compile`, import-purity grep, `.venv/bin/python -m
pytest tests/ -q` (no `mypy` — not installed; `ruff` optional at /home/dustin/.local/bin/ruff).
FULL PATHS always (zsh aliases `python`/`pytest`).

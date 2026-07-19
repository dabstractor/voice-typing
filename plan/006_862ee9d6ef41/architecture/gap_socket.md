# Gap Report — P1.M3.T2.S1: Control socket protocol vs PRD §4.2(3) / §4.8

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/daemon.py`'s **control socket** — the `voicectl`↔daemon AF_UNIX
`SOCK_STREAM` wire surface (PRD §4.2(3), §4.8) — on the **7 item checks (a)-(g)**: (a) socket path
resolves to `$XDG_RUNTIME_DIR/voice-typing/control.sock`; (b) parent dir `mkdir 0700`; (c) stale
socket unlinked before bind; (d) all 7 commands (`toggle`/`start`/`stop`/`status`/`toggle-lite`/
`start-lite`/`quit`) produce correct JSON responses; (e) status includes `phase`/`models_loaded`/
`mode`/`partial`/`uptime_s`; (f) unknown cmd → `{ok:false,error}`; (g) start/toggle block during load
(single-flight) + the response includes `listening` after arm. The audited code regions are:
`_default_control_socket_path` (path), `ControlServer.start` (mkdir 0700 + stale-unlink + bind +
chmod 0600 + listen), `ControlServer._dispatch` (the 7 commands + unknown/malformed/non-dict errors),
`VoiceTypingDaemon.status_snapshot` (the status payload), and `ControlServer._arm_response`
(single-flight-aware post-arm response). Subtask **P1.M3.T2.S1** of verification round `006_862ee9d6ef41`.

**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `_CONTROL_SOCKET_SUBPATH = ("voice-typing","control.sock")` (:352) +
  `_default_control_socket_path()` (:355 → `os.path.join(xdg,*subpath)` :370; raises RuntimeError if
  XDG unset :361); `ControlServer.start()` (:1762 → `os.makedirs(directory, exist_ok=True, mode=0o700)`
  :1773; stale-unlink `try: os.unlink(self._socket_path) except FileNotFoundError: pass` :1774-1776
  BEFORE `sock.bind()` :1781; `os.chmod(self._socket_path, 0o600)` :1787; `sock.listen(8)` :1788);
  `ControlServer._dispatch(line)` (:1892 → toggle :1901 / start :1913 / start-lite :1916 / toggle-lite
  :1919 / stop :1926 / status :1929 / quit :1931→`{"ok":true,"shutting_down":true}`; unknown :1939;
  malformed JSON :1897; non-dict :1899); `status_snapshot()` (:1548 → keys incl `mode` :1567, `phase`
  :1568, `models_loaded` :1569, `partial` :1571, `uptime_s` :1573); `_arm_response()` (:1875 →
  `{"ok":False,"error":f"model load failed: {load_error}"}` on load_failure+not_listening :1889;
  else `{"ok":True,**status_snapshot()}` :1891).
- `tests/test_control_socket.py` + `tests/test_daemon.py` — the contract's run targets (the `-k` filter;
  re-ran live). Coverage characterized in §2 + §4.

**Bottom line:** ✅ `daemon.py`'s control socket is **COMPLIANT** with PRD §4.2(3)/§4.8 on all 7 checks
— each mapped to a `daemon.py` file:line + a pinning test (in `test_control_socket.py` OR
`test_daemon.py`), and the contract's `-k` suite is **35 passed** (GPU-free, 2.69s). **No source files
were modified.** Two non-blocking test-coverage observations (the socket `_StubDaemon`'s reduced key
set; the single-flight/load-failure coverage living in `test_daemon.py`) are recorded in §4 so they are
not mistaken for defects.

---

## 1. Method

Each of the 7 checks was mapped 1:1 to its `voice_typing/daemon.py` implementation by `grep -n` (the
file:line evidence), the 7 command branches were read in `_dispatch` (:1892-1939), the status payload
was read in `status_snapshot` (:1548-1582), the `_arm_response` load-failure path was read (:1875-1891),
and the contract's `-k` suite (`tests/test_control_socket.py tests/test_daemon.py -k 'socket or control
or cmd or dispatch or status'`) was **re-run live** to record the actual pass count. Nothing was assumed
from the PRP's embedded numbers — every figure + line below was re-verified this round (pure stdlib:
`json`/`os`/`select`/`socket`/`threading`; no GPU/recorder required).

### Commands run (re-verification)

```bash
# (a) path; (b) mkdir 0700 + chmod 0600; (c) stale-unlink-before-bind
grep -nE '_CONTROL_SOCKET_SUBPATH|def _default_control_socket_path' voice_typing/daemon.py
grep -nE 'os\.makedirs\(directory.*0o700|os\.unlink\(self\._socket_path\)|sock\.bind|os\.chmod\(self\._socket_path' voice_typing/daemon.py
# (d) the 7 command branches + (f) unknown/malformed/non-dict errors
grep -nE 'cmd == "(toggle|start|start-lite|toggle-lite|stop|status|quit)"|unknown command|malformed JSON|request must be a JSON object' voice_typing/daemon.py
# (e) the status payload keys + (g) the _arm_response load-failure path
grep -nE 'def status_snapshot|"mode"|"phase"|"models_loaded"|"partial"|"uptime_s"|def _arm_response|model load failed' voice_typing/daemon.py
# the contract's run command, LIVE
timeout 120 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'
```

## 2. Per-check compliance table (PRD §4.2(3)/§4.8 vs `daemon.py`)

| # | PRD requirement | `daemon.py` actual | file:line | Pinning test | Verdict |
|---|---|---|---|---|---|
| **(a)** | socket at `$XDG_RUNTIME_DIR/voice-typing/control.sock` | `_default_control_socket_path()` joins `XDG_RUNTIME_DIR` + `("voice-typing","control.sock")`; raises `RuntimeError` if XDG unset (no safe default — fail clearly) | `_CONTROL_SOCKET_SUBPATH` `:352`; `_default_control_socket_path` `:355`; join `:370`; RuntimeError `:361` | `test_default_socket_path_honors_xdg` `:266`; `test_default_socket_path_raises_when_xdg_unset` `:271` (test_control_socket.py) | ✅ |
| **(b)** | parent dir `mkdir 0700` | `ControlServer.start()` does `os.makedirs(directory, exist_ok=True, mode=0o700)` then, after bind, `os.chmod(self._socket_path, 0o600)` (belt-and-suspenders owner-only on the 0700 dir) | `start` `:1762`; `makedirs 0o700` `:1773`; `chmod 0o600` `:1787` | `test_start_creates_dir_0700_and_socket_0600` `:224` (asserts dir `0o700` + socket `0o600`) | ✅ |
| **(c)** | stale socket removed before bind | `start()` `try: os.unlink(self._socket_path) except FileNotFoundError: pass` BEFORE `sock.bind()` (SO_REUSEADDR is meaningless for AF_UNIX path sockets) | unlink `:1774-1776`; bind `:1781` | `test_start_recovers_stale_socket_file` `:235` (pre-creates a stale file → start recovers) | ✅ |
| **(d)** | all 7 commands → correct JSON | `_dispatch` branches: `toggle`→arm_response-or-status; `start`→`_arm_response()`; `start-lite`→`_arm_response()`; `toggle-lite`→arm-or-status; `stop`→`{ok:true,**status}`; `status`→`{ok:true,**status}`; `quit`→`{ok:true,"shutting_down":true}` (+request_shutdown). Successful cmds share the uniform `{ok:true,**status_snapshot()}` spread | `_dispatch` `:1892`; toggle `:1901`; start `:1913`; start-lite `:1916`; toggle-lite `:1919`; stop `:1926`; status `:1929`; quit `:1931` | `test_dispatch_toggle` `:115`; `test_dispatch_status_has_all_keys` `:120`; `test_dispatch_start_stop_set_listening` `:126`; `test_dispatch_lite_commands_call_daemon` `:131`; `test_dispatch_status_response_carries_mode` `:143`; `test_dispatch_quit_calls_request_shutdown` `:161`; round-trips `:189-219` | ✅ |
| **(e)** | status has `phase`/`models_loaded`/`mode`/`partial`/`uptime_s` | `status_snapshot()` returns a 14-key dict incl `mode` (`self._mode`), `phase` (from `feedback.snapshot()`), `models_loaded`, `partial`, `last_final`, `uptime_s` (round(uptime_s,3)), + `load_error`/`device`/`compute_type`/`final_model`/`realtime_model`/`mic_ok`/`mic_error`. ALL 5 required fields present | `status_snapshot` `:1548`; `mode` `:1567`; `phase` `:1568`; `models_loaded` `:1569`; `partial` `:1571`; `uptime_s` `:1573` | REAL 14-key set: `test_status_snapshot_keys_and_cuda_values` `test_daemon.py:1595` (asserts the exact 14 keys `:1610-1613`); mode-on-wire: `test_dispatch_status_response_carries_mode` `:143` (test_control_socket.py) | ✅ |
| **(f)** | unknown cmd → `{ok:false,error}` | `_dispatch` falls through to `return {"ok":False,"error":f"unknown command: {cmd!r}"}` (also hit by a MISSING cmd — `msg.get("cmd")` is None). Malformed JSON + non-dict JSON also → `{ok:false,error}` | unknown `:1939`; malformed `:1897`; non-dict `:1899` | `test_dispatch_unknown_command` `:169`; `test_dispatch_missing_cmd` `:173`; `test_dispatch_malformed_json` `:177`; `test_dispatch_non_dict_json` `:182` (test_control_socket.py) | ✅ |
| **(g)** | start/toggle BLOCK during load (single-flight) + response has `listening` after arm | `start`→`self._daemon.start()` (daemon `start()` :1365 → `_load_host` :698, single-flight `with self._lock:` :714 — a concurrent caller WAITS on the in-flight load)→`_arm_response()`. `_arm_response` returns `{ok:false,error}` if the load failed (load_error set AND not listening), else `{ok:true,**status}` (carrying `listening`). toggle takes the same arm path when arming | `_dispatch` start `:1913`; `_arm_response` `:1875` (ok:false `:1889`); `_load_host` single-flight `:698`/`:714` | single-flight: `test_load_recorder_single_flight_one_build_under_concurrency` `test_daemon.py:3010` + `test_load_and_unload_serialize_on_the_same_single_flight_lock` `:3198`; post-arm listening: `test_dispatch_start_stop_set_listening` `:126`; load-failure suppression: `test_start_suppressed_when_load_fails` `test_daemon.py:2994` | ✅ |

> All 7 checks **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this
> round. The `_dispatch` branches are exhaustive (the 7 known commands + the unknown fallthrough), and
> the status payload's 5 required fields are all present in `status_snapshot`.

## 3. Test results

```
.venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'
...................................                                      [100%]
35 passed, 179 deselected in 2.69s
```

**35 passed, 0 failed, 0 errors.** The `-k` filter spans BOTH files by design: `socket`/`control`/
`dispatch`/`cmd` select the `test_control_socket.py` suite (path, mkdir, stale-unlink, the 7 command
branches, the error paths, the real-socket round-trips), and `status` selects `test_daemon.py`'s
`test_status_snapshot_*` tests (the REAL 14-key status payload — see nuance §4.1) + the single-flight
tests (nuance §4.2). Every one of the 7 checks has at least one dedicated pinning test.

## 4. Non-defect test-coverage nuances (recorded so they are NOT mistaken for code gaps)

### 4.1 (e) the socket `_StubDaemon` uses a REDUCED key set — the REAL key set is pinned in test_daemon.py

`tests/test_control_socket.py:_StubDaemon.status_snapshot()` (`:45`) returns the stub's `_snapshot`
dict, whose **default** (`_StubDaemon.__init__`, `:34`) is an **8-key** dict
(`{listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model}`) — it
OMITS `phase`/`models_loaded`/`mode`/`load_error`/`mic_ok`/`mic_error`. Consequently
`test_dispatch_status_has_all_keys` (`:120`) pins that **reduced 8-key set on the WIRE**, NOT the real
daemon's 14-key set. The REAL `status_snapshot()` key set is pinned by
`test_status_snapshot_keys_and_cuda_values` in **`test_daemon.py:1595`** (asserts the exact 14 keys at
`:1610-1613`, incl `phase`/`models_loaded`/`mode`/`load_error`/`mic_ok`/`mic_error`). And
`test_dispatch_status_response_carries_mode` (`:143`) subclass-proves the wire spread surfaces `mode`
when the daemon emits it. **NON-DEFECT**: the socket layer is tested with a duck-typed stub (no
recorder, no lifecycle fields); the real key set is covered in `test_daemon.py`. The CODE is compliant
(`status_snapshot` has all 5 clause-(e) fields). This mirrors the "compliant-by-design" recording
convention used in `gap_feedback.md` §4 + `gap_typing.md` §4.1.

> **Accuracy note:** this re-verification CORRECTS the research note + the PRP's embedded verdict, both
> of which stated the stub returned a "9-key" set. The live tree shows the default `_snapshot` is
> **8 keys** (`_StubDaemon.__init__` `:34-40`). This is the value of the PRP's Critical #2 ("RE-VERIFY
> LIVE; DON'T TRUST THE LINE NUMBERS BLINDLY") — the research note's count was off by one; the live
> audit supersedes it. (The verdict — REDUCED stub set vs. REAL 14-key set — is unchanged.)

### 4.2 (g) single-flight + load-failure-arm-response coverage lives in test_daemon.py, not test_control_socket.py

The socket tests use `_StubDaemon` (no `_load_host`, no `_load_error`) — they prove **dispatch wiring**
+ **post-arm `listening`** + the `{ok:true,**status}` spread, NOT the single-flight load or the
`_arm_response` ok:false path. The single-flight (`start`/`toggle` block during a load — a concurrent
caller waits on the in-flight load) is a **daemon** concern, tested in `test_daemon.py`
(`test_load_recorder_single_flight_one_build_under_concurrency` `:3010`;
`test_load_and_unload_serialize_on_the_same_single_flight_lock` `:3198`); the load-failure arm
suppression is `test_start_suppressed_when_load_fails` (`:2994`). The `_arm_response` ok:false path is
exercised through those (the daemon sets `_load_error`; `_arm_response` reads it via `getattr`). **NON-
DEFECT**: the coverage is split across the two test files by responsibility (socket wiring vs. daemon
load lifecycle). The CODE is compliant (`start`→single-flight `_load_host`→`_arm`→`_arm_response` with
`listening`).

## 5. Conclusion

**PASS — no fix required.** `voice_typing/daemon.py`'s control socket is PRD §4.2(3)/§4.8-compliant on
all 7 checks: the path resolves to `$XDG_RUNTIME_DIR/voice-typing/control.sock` (`:355`) with a clear
RuntimeError when XDG is unset (a); the parent dir is `mkdir 0o700` + the socket `chmod 0o600` (`:1773`/
`:1787`) (b); a stale socket is `os.unlink`'d before `bind` (`:1774-1776`) (c); all 7 commands
(`toggle`/`start`/`stop`/`status`/`toggle-lite`/`start-lite`/`quit`) dispatch to the right daemon method
+ return the correct JSON (`_dispatch` `:1892-1939`) (d); `status_snapshot` carries all 5 required
fields (`phase`/`models_loaded`/`mode`/`partial`/`uptime_s`, `:1548-1582`) (e); an unknown/missing
command returns `{ok:false,error}` (`:1939`) (f); and `start`/`toggle` block on the single-flight load
then respond with `listening` after arm (`_arm_response` `:1875`) (g). The contract's `-k` suite is
**35 passed**.

The two recorded non-defect nuances are test-coverage observations, not code gaps: the socket
`_StubDaemon`'s reduced 8-key status (the real 14-key set is pinned in `test_daemon.py:1595` — §4.1),
and the single-flight/load-failure coverage living in `test_daemon.py` (the socket tests use a stub —
§4.2). The code is compliant regardless.

**No source changes were required and none were made.** This report is the only artifact produced by
this subtask. Adjacent concerns are correctly deferred: the **`ctl.py` client** (rendering, exit codes,
the client-side "loading models…" hint) is **P1.M3.T2.S2**; **`status.sh`** is **P1.M3.T2.S3**; the
**recorder-host subprocess lifecycle** (the load the single-flight serializes) is **P1.M2.***
(Complete). Downstream **P1.M5.T5** (acceptance cross-check) can consume this report as the evidence
that **Acceptance #6** ("`voicectl toggle/start/stop/status/quit` all work") is met at the daemon side.
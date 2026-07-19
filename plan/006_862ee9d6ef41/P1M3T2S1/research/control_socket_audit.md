# Research — P1.M3.T2.S1: Control-socket protocol audit (path / mkdir / stale / 7 cmds / status / errors / single-flight)

Verified live on the target machine (2026-07-18). Authoritative for the PRP.

## 0. Task nature + deliverable

**READ-ONLY AUDIT** (the code is COMPLIANT — this research verified it). The deliverable is a NEW file
`plan/006_862ee9d6ef41/architecture/gap_socket.md` (there is NO existing gap_socket.md; P1.M3.T2.S1
creates it — unlike the feedback audits which split S1/S2 into one file). Format mirrors
`gap_feedback.md` (title + date + scope + audited artifacts + bottom line + §1 method + §2 per-check
compliance TABLE + §3 test results + §4 non-defect nuances + §5 conclusion). NO source code modified.

## 1. The audited code (voice_typing/daemon.py) — per-check file:line

| Check | Code region (daemon.py) | Verdict |
|---|---|---|
| (a) path → `$XDG_RUNTIME_DIR/voice-typing/control.sock` | `_CONTROL_SOCKET_SUBPATH = ("voice-typing","control.sock")` :352; `_default_control_socket_path()` :355 → `os.path.join(xdg, *subpath)` :370; raises RuntimeError if XDG unset :361 | ✅ |
| (b) mkdir 0700 | `ControlServer.start()` :1762 → `os.makedirs(directory, exist_ok=True, mode=0o700)` :1773; `os.chmod(self._socket_path, 0o600)` :1787 (belt-and-suspenders on the 0700 dir) | ✅ |
| (c) stale socket unlinked before bind | `start()` :1774-1776 `try: os.unlink(self._socket_path) except FileNotFoundError: pass` BEFORE `sock.bind()` :1779 (SO_REUSEADDR is meaningless for AF_UNIX path sockets — comment :1775) | ✅ |
| (d) all 7 commands → correct JSON | `_dispatch(line)` :1892 → toggle :1898 / start :1908 / start-lite :1911 / toggle-lite :1915 / stop :1922 / status :1924 / quit :1926→`{"ok":true,"shutting_down":true}`. Arms return `_arm_response()`; stop/status return `{"ok":true,**status_snapshot()}` | ✅ |
| (e) status has phase, models_loaded, mode, partial, uptime_s | `status_snapshot()` :1548 returns {listening, **mode** :1564, **phase** :1565, **models_loaded** :1566, load_error, **partial** :1569, last_final, **uptime_s** :1571, device, compute_type, final_model, realtime_model, mic_ok, mic_error} — ALL 5 required fields present | ✅ |
| (f) unknown cmd → {ok:false,error} | `_dispatch` :1965 `return {"ok":False,"error":f"unknown command: {cmd!r}"}` (also hit by missing cmd — `msg.get("cmd")` is None → falls through to this). Plus malformed JSON :1896 + non-dict :1899 → {ok:false,error} | ✅ |
| (g) start/toggle block during load (single-flight) + response has listening after arm | `_dispatch` start :1908 → `self._daemon.start()` (calls `_load_host` :698 / single-flight under `_lock`) → `_arm_response()` :1875 (load failure + not listening → `{"ok":False,"error":...}` :1889; else `{ok:true,**status}` with `listening`). toggle :1898 same arm path when arming | ✅ |

**`_arm_response()` (daemon.py:1875):** `load_error = getattr(self._daemon,"_load_error",None); if load_error and not is_listening(): return {"ok":False,"error":f"model load failed: {load_error}"}; return {"ok":True,**status_snapshot()}`. The `getattr(...,None)` keeps the duck-typed test `_StubDaemon` (no `_load_error`) on the ok:true path.

## 2. Test coverage map (tests/test_control_socket.py + tests/test_daemon.py)

| Check | Pinning test(s) | File:line |
|---|---|---|
| (a) path | `test_default_socket_path_honors_xdg`; `test_default_socket_path_raises_when_xdg_unset` | test_control_socket.py:266; :271 |
| (b) mkdir 0700 | `test_start_creates_dir_0700_and_socket_0600` (asserts dir `0o700` + socket `0o600`) | :224 |
| (c) stale unlink | `test_start_recovers_stale_socket_file` (pre-creates a stale file → start recovers) | :235 |
| (d) 7 commands | `test_dispatch_toggle` :115; `test_dispatch_status_has_all_keys` :120; `test_dispatch_start_stop_set_listening` :126; `test_dispatch_lite_commands_call_daemon` :131; `test_dispatch_status_response_carries_mode` :143; `test_dispatch_quit_calls_request_shutdown` :161; round-trips :189-219 | test_control_socket.py |
| (e) status fields | REAL key set: `test_status_snapshot_keys_and_cuda_values` (asserts EXACTLY the 14-key set incl phase/models_loaded/mode/load_error/mic_ok/mic_error) | **test_daemon.py:1595/1610-1612** |
| (f) unknown/missing | `test_dispatch_unknown_command`; `test_dispatch_missing_cmd` (also `test_dispatch_malformed_json` :177, `test_dispatch_non_dict_json` :182) | test_control_socket.py:169; :173 |
| (g) single-flight + post-arm listening | single-flight: `test_load_recorder_single_flight_one_build_under_concurrency` + `test_load_and_unload_serialize_on_the_same_single_flight_lock`; post-arm listening on wire: `test_dispatch_start_stop_set_listening`; load-failure suppression: `test_start_suppressed_when_load_fails` | test_daemon.py:3010; :3198; :2994 — and test_control_socket.py:126 |

## 3. The contract's run command (re-run LIVE 2026-07-18)

```
.venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'
...................................                                      [100%]
35 passed, 179 deselected in 3.01s
```

→ **35 passed**. Record this count verbatim in the gap report §3.

## 4. The 2 NON-DEFECT test-coverage nuances (record so they are NOT mistaken for gaps)

### 4.1 (e) the socket test's `_StubDaemon` uses a REDUCED key set — the REAL key set is pinned in test_daemon.py
`tests/test_control_socket.py:_StubDaemon.status_snapshot()` (line 45) returns a 9-key dict
{listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model} — it
OMITS phase/models_loaded/mode/load_error/mic_ok/mic_error. Consequently
`test_dispatch_status_has_all_keys` (:120) pins that REDUCED 9-key set on the WIRE, NOT the real
daemon's 14-key set. The REAL `status_snapshot()` key set (with phase/models_loaded/mode) is pinned
by `test_status_snapshot_keys_and_cuda_values` in **test_daemon.py:1595** (asserts the exact 14 keys,
line 1610-1612). And `test_dispatch_status_response_carries_mode` (:143) subclass-proves the wire
spread surfaces `mode` when the daemon emits it. **NON-DEFECT**: the socket layer is tested with a
duck-typed stub (no recorder); the real key set is covered in test_daemon.py. The CODE is compliant
(status_snapshot has all 5 clause-(e) fields).

### 4.2 (g) single-flight + load-failure-arm-response coverage lives in test_daemon.py, not test_control_socket.py
The socket tests use `_StubDaemon` (no `_load_host`, no `_load_error`) — they prove DISPATCH WIRING +
post-arm `listening` + the `{ok:true,**status}` spread, NOT the single-flight load or the
load-failure `_arm_response` ok:false path. The single-flight (start/toggle block during a load) is a
DAEMON concern, tested in test_daemon.py (`test_load_recorder_single_flight_one_build_under_
concurrency` :3010; `test_load_and_unload_serialize_on_the_same_single_flight_lock` :3198); the
load-failure arm suppression is `test_start_suppressed_when_load_fails` (:2994). The `_arm_response`
ok:false path is exercised through those (the daemon sets `_load_error`; `_arm_response` reads it).
**NON-DEFECT**: the coverage is split across the two test files by responsibility (socket wiring vs.
daemon load lifecycle). The CODE is compliant (start→single-flight load→arm→status-with-listening).

## 5. Scope boundaries (recorded for boundary clarity)

- **voicectl CLI (`ctl.py`) is P1.M3.T2.S2** (the NEXT subtask). This audit is the DAEMON-side
  socket (path/protocol/commands/errors) only — NOT the client's rendering, exit codes, or the
  "loading models…" client-side hint (which ctl.py prints during the block).
- **status.sh is P1.M3.T2.S3.** NOT here.
- **No source modified.** daemon.py / test_control_socket.py / test_daemon.py are READ-ONLY. The only
  new artifact is gap_socket.md.
- **gap_socket.md is a NEW file** (CREATE, not append). The parallel P1.M3.T1.S2 (feedback) touches
  gap_feedback.md — a DIFFERENT file; no conflict.

## 6. Tooling reality (confirmed live 2026-07-18)

- Run via `.venv/bin/python` (zsh aliases python → uv run). mypy NOT installed (skip). ruff optional
  (not a gate). The -k suite is GPU-free (`_StubDaemon` + monkeypatched cuda_check) — ~3s.
- Line numbers above are `grep -n`-verified this round but the audit must RE-VERIFY live (line numbers
  drift) — mirrors gap_feedback.md / gap_typing.md "re-verified against the live tree" discipline.
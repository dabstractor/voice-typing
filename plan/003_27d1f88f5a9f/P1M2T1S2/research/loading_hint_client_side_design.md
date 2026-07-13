# Research — P1.M2.T1.S2: Thread the "loading models…" hint through ctl.py + status during first arm

> Purpose: pin down (a) the exact 3-way task boundary (T1.S1 vs T1.S2 vs T2.S1) so this task
> neither duplicates nor conflicts with siblings; (b) the timing proof that the hint MUST be
> client-side; (c) the concrete design (timer-based stderr hint + `_dispatch` ok:false on load
> failure); (d) the test plan. All facts verified on the live tree (plan 003 delta over the
> plan-001 codebase; Python 3.12.10; `.venv/bin/python`).

## 1. The 3-way boundary (authoritative: delta_prd.md)

The lazy-load feature spans three subtasks. The delta_prd assigns them disjoint scopes:

| Subtask | Owns (delta_prd citation) | Edits |
|---|---|---|
| **P1.M2.T1.S1** (parallel, "Ready") | the load MECHANISM: lazy `__init__`, `_load_recorder()` single-flight, 8 None-guards, CPU-fallback migration, drives `phase` via `feedback.set_phase`. Adds daemon attrs `_recorder/_models_loaded/_loading/_load_error/_load_cond`. `start()` returns None. **Does NOT edit feedback.py or `_dispatch`.** | `daemon.py`, `test_daemon.py` |
| **P1.M2.T1.S2 (THIS TASK)** | the USER-FACING hint: "Thread the `loading models…` hint through `ctl.py` … ensure `voicectl` prints it **while the first arm blocks**" (delta_prd line 70) + the PRD §4.2bis arm-failure response `{"ok":false,"error":...}` (delta_prd line 67, not assigned to T1.S1 — its PRP leaves `start()` returning None and never touches `_dispatch`). | `ctl.py`, `daemon.py` (`_dispatch` only) |
| **P1.M2.T2.S1** (later) | "Expose `phase` + `models_loaded` from `status_snapshot()` and render them in `ctl.py` **status**" (delta_prd line 74) + `feedback.py` `models_loaded` field (delta_prd line 72). | `daemon.py` (`status_snapshot`), `feedback.py`, `ctl.py` (`status` branch) |

**This task's lane (no overlap):** the **start/toggle arm** experience — (1) a "loading models…"
progress hint while the first arm blocks, and (2) surfacing a model-load failure as
`{"ok":false,"error":...}`. It does NOT add `phase`/`models_loaded` to `status_snapshot()`, does
NOT render the `status` command's model/phase lines, and does NOT edit `feedback.py` — all T2.S1.

## 2. Timing proof: the hint MUST be client-side

`voicectl start` flow today (and after T1.S1):

```
ctl.main(["start"]) -> send_command(sock, "start")  -- sends {"cmd":"start"}\n, BLOCKS on readline
                         ^
daemon ControlServer._handle -> _dispatch("start") -> self._daemon.start()
                                                     -> (T1.S1) self._load_recorder()  # BLOCKS ~1–3 s
                                                     -> self._arm()
                              -> returns {"ok":True, **status_snapshot()}   # ONLY AFTER load completes
send_command returns the dict -> format_result -> "listening: on"
```

**The response is produced only AFTER `_load_recorder()` returns.** So:

- The response can NEVER carry `phase:"loading"` on a *successful* load — by the time `_dispatch`
  builds the response, `phase` is already `"idle"` (T1.S1 sets it in `_load_recorder`'s success
  path). The item description's part (c) ("if phase='loading', augment to 'listening: on (loading
  models…)'") cannot fire on success — it would be dead code. The delta_prd's wording is the
  correct one: voicectl "prints it **while the first arm blocks**" — i.e. DURING the wait, before
  the response exists. That is necessarily a CLIENT-SIDE print, not a response-render.
- The protocol is strictly one-line-request / one-line-response (`send_command` reads exactly ONE
  line; ctl.py docstring). A daemon-sent interim "loading" line would break the protocol on both
  sides. So an in-band loading signal is out. Client-side it is.

**How the client knows it's loading (not just slow):** it can't know for certain, but the ONLY
reason a `start`/`toggle` takes more than a few hundred ms is a model load (resident arms reply in
ms; the recorder is either loaded-and-instant or loading-for-seconds — there is no middle ground).
So a **delay-thresholded** stderr hint (print only if no reply within ~0.3 s) is accurate: it fires
exactly on a real load and never flickers on an instant (resident) arm.

## 3. Why `threading.Timer`, not `socket.settimeout`

`send_command` (ctl.py) uses `sock.makefile("r", ...).readline()`. Its own docstring states:
"Uses makefile('r') (NOT settimeout — makefile raises if the socket has a timeout, P1.M4.T2.S1 §3)."
So the delay-thresholded hint CANNOT use a socket timeout (it would break `send_command`). The
clean approach is a **`threading.Timer`** started before `send_command`, printing the hint to
stderr after the threshold, and **cancelled** in a `finally` when `send_command` returns. The timer
thread is a daemon thread (never blocks process exit). `send_command` itself is UNCHANGED (it is
unit-tested directly); a thin wrapper `_send_command_with_loading_hint` adds the timer for
`start`/`toggle` only.

## 4. The `_dispatch` ok:false-on-failure change (PRD §4.2bis)

Today `_dispatch` (daemon.py:1079-1107) for `start`/`toggle`/`stop` ALWAYS returns
`{"ok":True, **status_snapshot()}` — even when (after T1.S1) `start()`'s `_load_recorder()` failed
and suppressed the arm. PRD §4.2bis mandates: "If the load fails … the arm command returns
`{"ok":false,"error":"..."}`." T1.S1's PRP leaves `start()` returning `None` and never edits
`_dispatch`, so this falls to T1.S2 (it is the "thread through ctl + response" surface).

Design: after calling `start()`/`toggle()`, `_dispatch` reads `getattr(self._daemon, "_load_error",
None)` (the attr T1.S1 adds; `getattr` default keeps the duck-typed `_StubDaemon` in tests working
— it has no such attr → None → ok:true path). On a set `_load_error` with the daemon left
not-listening, return `{"ok":False, "error": f"model load failed: {_load_error}"}`. `format_result`
ALREADY handles `ok:false` → `"error: ..."` (exit 1), so NO `format_result` change is needed for
the failure path.

### 4.1 `_load_error` staleness — why the check is sound

`_load_recorder()` (T1.S1) resets `self._load_error = None` at the start of each fresh load attempt
and sets it only on a fresh failure. The only `_dispatch` paths that read it are ARM attempts
(`start`, and `toggle` when it arms — detected via `is_listening()` before the call). A disarm
`toggle` requires the daemon to have been listening, which requires a PRIOR successful load
(`_load_error=None`); a failed-load state is never listening, so a `toggle` there ARMS (re-runs
`_load_recorder`, resetting `_load_error`). Therefore a set `_load_error` read on an arm attempt is
always THIS attempt's fresh failure — never stale. (Idle-unload, P1.M3, is a clean teardown that
won't set `_load_error`; and it isn't built yet, so not a current concern.)

### 4.2 `toggle` arm-vs-disarm detection

`toggle` either arms or disarms. Only the ARM path can fail to load. `_dispatch` captures
`was_listening = self._daemon.is_listening()` BEFORE `toggle()`; if `not was_listening`, this
toggle attempted to arm → run the failure check. If `was_listening`, it disarmed (fast, no load) →
always ok:true+status. (`start` is always an arm attempt.)

## 5. Verified code facts (live)

- `ctl.py` is stdlib-only (`argparse/json/socket/sys` + `_default_control_socket_path`); `format_result`
  is PURE (no I/O); `send_command` uses `makefile("r")` (no settimeout); `main` does
  parse→validate→resolve→send→format→print. Adding `import threading` + a wrapper + a `main` branch
  for start/toggle is the entire ctl.py change. `format_result` is UNCHANGED.
- `daemon.py:1079 _dispatch` structure confirmed (start/toggle/stop → `{"ok":True,
  **status_snapshot()}`; quit → `{"ok":True,"shutting_down":True}`; errors → `{"ok":False,
  "error":...}`). The change is localized to the `start` and `toggle` branches.
- `tests/test_voicectl.py`: `_StubDaemon` (duck-type, has start/toggle/stop/request_shutdown/
  is_listening/status_snapshot; NO `_load_error`); `running_server` fixture builds a
  `ControlServer(_StubDaemon(), ...)` on a tmp socket. Layer B tests use the FAST stub (ms replies)
  → the 0.3 s hint never fires → those tests pass UNCHANGED. New tests need a SLOW stub (sleeps in
  `start`) and a FAILING stub (`start` doesn't arm + `_load_error` set).
- `ControlServer` handles each connection in its own thread (T1.S1 note: "spawns one thread per
  connection"), so a stub whose `start()` sleeps blocks only that handler thread — voicectl's
  `send_command` blocks on `readline` until the stub replies. This is exactly the real first-arm
  timing, hermetically.

## 6. Test plan (all FAST, no GPU, no RealtimeSTT — stub daemons)

1. **Existing Layer A (format_result) + Layer B (round-trip) tests pass UNCHANGED** — fast stub,
   hint never fires, format_result untouched.
2. **NEW: hint fires for a slow start** — `_SlowStartStubDaemon` (sleeps 0.4 s in `start`),
   monkeypatch `ctl._LOADING_HINT_DELAY = 0.02`, `ctl.main(["start"])` → assert `"loading models"`
   in stderr (`capfd`) AND the correct `"listening: on"` result on stdout AND exit 0.
3. **NEW: hint does NOT fire for a fast arm** — `running_server` (fast stub), `ctl.main(["start"])`
   → assert `"loading models"` NOT in stderr (deterministic: stub replies in ms ≪ 0.3 s).
4. **NEW: hint only on start/toggle, not stop/status** — `ctl.main(["status"])` and `["stop"]` →
   no `"loading models"` in stderr (they use plain `send_command`).
5. **NEW: load failure → ok:false, exit 1, error shown** — `_FailingLoadStubDaemon` (start sets
   `_load_error`, doesn't arm), `ctl.main(["start"])` → exit 1, `"error"` + `"model load failed"`
   in stdout (`capsys`). Also a `_dispatch` unit test: failing stub → `_dispatch("start")` returns
   `{"ok":False,"error":...}`.
6. **NEW: toggle arm-failure path** — `_FailingLoadStubDaemon`, was_listening False,
   `_dispatch("toggle")` → `{"ok":False,...}`; a listening+failed scenario is impossible (see §4.1).
7. **Fast suite green** — `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`.

## 7. Scope boundaries (no conflict with siblings)

- **vs T1.S1 (parallel, "Ready"):** T1.S1 edits `__init__`/`_load_recorder`/8 guards/`run`/`main`/
  docstrings + test_daemon.py. This task edits `_dispatch` (start/toggle branches only) + ctl.py.
  Different regions of daemon.py; the `_load_error` attr is CONSUMED (read) here, owned there.
- **vs T2.S1 (later):** T2.S1 adds `phase`/`models_loaded` to `status_snapshot()` + feedback.py +
  ctl `status` rendering. This task does NOT touch `status_snapshot()`'s field set, `feedback.py`,
  or the `status` branch of `format_result`. When T2.S1 later adds fields, `_arm_response`'s
  `**status_snapshot()` spread carries them automatically — complementary, not conflicting.
- **No source files beyond `ctl.py` + `daemon.py` (`_dispatch` only).** No config.py/config.toml
  (M3.T1), no README (M3.T3), no systemd (M1.T2.S1), no feedback.py (T2.S1).

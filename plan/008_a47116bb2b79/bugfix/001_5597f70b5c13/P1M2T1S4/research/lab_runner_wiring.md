# Research — P1.M2.T1.S4: Wire the isolated route runner to compare real recorder builds

Verified against HEAD 20ca3cc + the in-flight worktree (S2's `_BulkTargetBundle.start()` already
visible in `daemon.py`). Line anchors are from that state; **find by marker, not absolute line**.

## 1. What exists today (tests/g5_timing_lab.py, 1238 lines)

| Anchor | What | S4 relevance |
|---|---|---|
| `main()` :1210 | outer argparse: `--route` (required, `sorted(ROUTES)+["all"]`); env-gate `GATE_ENV` check; `smoke = G5_NO_DESKTOP=1`; loops `run_route(r, smoke)` | add `--partial-source` |
| inner `"run"` parser :1212-1219 | `run <root> --route X [--smoke]` → `run_inner` | add `--partial-source` + thread |
| `run_route()` :1129 | outer phase: mkdtemp `PREFIX`, private dbus conf, builds `argv` (:1149-1156), `xvfb-run -a dbus-run-session -- python ... run folder --route X [--smoke]`; smoke branch runs `run_inner` in-place; `timeout_s = 240 if smoke else 1440`; SIGTERM→SIGKILL escalation; scratch rmtree retry ×10 (or `G5_KEEP_SCRATCH=1`) | thread flag into argv; **new preflight before any spawn** |
| `run_inner()` :766 | env guard (`root == $XDG_RUNTIME_DIR`, name startswith `g5-timing-lab-`, `WLR_BACKENDS=x11` unless smoke — "Refusing to run outside the disposable environment"); logging.basicConfig INFO→stderr; boots sway + route (non-smoke); CUDA LD set AFTER desktop up; `start_daemon(smoke, route.bulk_target_factory() if route else None)`; `ready` deque maxlen=20000; `wrap_ready`; arm()/warmup (ONE discarded replay); measured replays per REPLAY_BUDGET; record build; artifact JSON; `hb` (mono,wall) pairs; heartbeat check fails run; finally: ctl quit → `d.shutdown()` → `srv.stop()` → `route._poll_stop.set()` → `lab.kill_all()` | thread `partial_source`; effective-source fail-closed; ReadyEvent upgrade; truncation flags; scrub raw speech |
| `build_cfg(smoke)` :641 | measured: `output.delivery=bulk-text`, `backend=null`, hypr_notify off, cancel.devices=[/nonexistent/...], `duck_mode=off`, auto_stop_idle=0, auto_unload_idle=0; smoke: stream-edit + same inert surfaces | UNCHANGED (the paired fixture settings) |
| `control_send` :674 | ONE JSON line over the REAL private control socket (`$XDG_RUNTIME_DIR/voice-typing/control.sock`), total-deadline retries | the "control" surface to mock in unit tests |
| `start_daemon(smoke, factory)` :719 | `Feedback(cfg.feedback)` + `VoiceTypingDaemon(cfg, fb, latency=LatencyLog(), mic_prober=lambda:(True,None), bulk_target_factory=factory, feed_input=True)` + `ControlServer` + run thread. Function-local imports of `voice_typing.daemon`/`feedback` (monkeypatchable at module attrs) | gains `partial_source` param → daemon kwarg (S1 seam, daemon.py :904/:951) |
| `wrap_ready(d, ready, lock)` :741 | wraps `d.on_final` / `d._on_partial` BEFORE first arm (child relays to whatever `_load_host` captured); appends `(t, text, kind)` tuples under lock | upgrade to `g5.ReadyEvent` with stage/gen/utt/seq (§3) |
| warmup block ~:903-935 | paced_feed clips[0]; wait ≥1 final; `wkinds` counts; **`first_partial = x[:60]` (raw speech!)**; `flog.drain()` discards warmup; `ready.clear()`; `hb.append`; `log({"stage":"warm", ..., "first_partial": first_partial})`; smoke returns 0 here | effective-source resolution + log HERE; scrub snippet |
| measured loop ~:975-1035 | per replay: stop→wait gone→start→wait active; `anchor = flog.anchor()` (token count); `flog.drain()`; `fs = paced_feed(...)`; wait final + quiescence (SETTLE_S=4); `evs` filtered `[fs-0.5, end_t]`; `win` filtered from ready; `wk`/`fp = x[:50]` (**raw speech**); `rec = g5.ReplayRecord(route, clip, feed_start, words, field_events=evs, update_ready=win, finals_ts, anchor)`; aggregate; replay log line (has `first_partial`) | populate S3 fields (`partial_source`, `anchor_text`, `capped`, `heartbeats`); ReadyEvent attr access; scrub `fp` |
| artifact ~:1035-1065 | `{"route", "metrics" (render_report_row), "replays", "heartbeat_ok", "field_log_pair_count", "provenance": {kernel, python, device, warm, clips, route_note, field_instrument}}` written `artifact-<route>.json` (scratch) + `log(metrics)` | provenance += requested/effective source |
| `paced_feed` :120 | sleep-to-target monotonic chunk feed + trailing zero slices; returns feed_start | UNCHANGED |
| `FieldLog` :159 | incremental JSONL drain → deque maxlen=4000 (`cap`), `anchor()` = token count of last event text | add `anchor_text()` + cap detection |
| `_Lab` :225 | `spawn` (start_new_session=True, tracked), `kill`/`kill_all` (killpg OWN groups, wait ≤2s), `err_head` | UNCHANGED (the "process runner" to mock) |
| `GtkRoute` :297 | docstring NOTE :303-311 admits the lab-side bridge; `bulk_target_factory()` :363-400 = ImeProcess(log_path=ime_host.jsonl)+spawn+60s ping-activation pump → `_BulkTargetBundle` (**the bridge to DROP**) | DELETE method → inherit `_Route.bulk_target_factory` = None = DEFAULT route |
| `PiGhosttyRoute` :401 | boots ghostty+pi (HOME delta), extension socket, `_poll_loop` (10 ms read-poll → JSONL, bounded writes), `bulk_target_factory()` :562-637 = `_G5PiBundle` with `_CancelOnLeaveTarget` (cancel-on-leave instrument reset; `self._client` resolves via `__getattr__` delegation) + `PiEditorTakeoverWatch`; `preflight_note` | KEEP VERBATIM (S5's seam); do not count reset edits (anchor_text + S3 reset rules) |
| `desktop_env` :1070 | private XDG_RUNTIME_DIR/XDG_CONFIG_HOME/TMPDIR/HOME (=folder), WLR_BACKENDS=x11, pixman, LIBGL software, no CUDA LD (set later for the child only), OMP/MKL caps; needs_pi → REAL HOME (documented delta) + PI_BIN | UNCHANGED |
| ROUTES :639, constants :73-89 | GATE_ENV="G5_TIMING_LAB", NO_DESKTOP_ENV="G5_NO_DESKTOP", PREFIX, SETTLE_S=4, ARM_TIMEOUT_S=180, WARM_WAIT_S=90, FINAL_TIMEOUT_S=45 | UNCHANGED |

Module-level imports are stdlib-only + `g5_timing_support` (path-inserted) — **import-safe for unit
tests**; heavy imports (`voice_typing.*`) are function-local. No env gate at import time.

## 2. Sibling contracts consumed (all verified in worktree/PRPs)

- **S1 (LANDED, 20ca3cc)**: `VoiceTypingDaemon.__init__(..., partial_source="stabilized")`
  (keyword-only) → `_load_host` → real `RecorderHost(partial_source=...)` → spawn args →
  `_worker_main` → both build paths. Host property `partial_callback` (recorder_host.py :247) = the
  INSTALLED key from the child's ready payload ("" until ready; additive key, legacy-child safe).
  `_PARTIAL_SOURCES = {"plain": "on_realtime_transcription_update", "stabilized":
  "on_realtime_transcription_stabilized"}` (daemon.py :232). Invalid value → ValueError.
- **S2 (in worktree, essentially landed)**: `_BulkTargetBundle.start()` = spawn + bounded read-only
  ping-activation pump (`_IME_ACTIVATE_TIMEOUT_S=2.0`, poll 0.05 s) on the vt-bulk-arm thread;
  `_build_default_bulk_target` stays PURE, constructs `ImeProcess(on_delivery_state=...)` (NO
  log_path ⇒ no `ime_host.jsonl` capture on the default route — diagnostics = daemon INFO lines +
  set_delivery_state reasons). Arm failures → `unsupported` + stays armed. The lab's `arm()`
  3-attempt retry loop (cold GTK loop can stall the first activate) is the compensating control for
  the 2 s pump (the old lab bridge allowed 60 s).
- **S3 (parallel, PRP = contract)**: `g5.ReadyEvent(t, text, kind, stage="daemon", gen, utt, seq,
  disposition="", ack_ts=None)`; legacy tuples coerce; `ReplayRecord` gains `partial_source="",
  anchor_text="", capped=False, heartbeats=[]`; `RouteMetrics` gains coverage/miss counters +
  clock/cap failures; `aggregate`/`render_report_row` additive keys; **the 14 existing
  test_g5_timing_support tests stay green unedited**. resolve_visibility/ready_to_frame semantics
  preserved (ready_to_frame = projection of attribute_updates).

## 3. Identity availability at the daemon boundary (verified)

`d.on_final`/`d._on_partial` run ON the host reader thread INSIDE `RecorderHost._dispatch`, and
`VoiceTypingDaemon._bulk_identity()` (daemon.py :2070) is documented **valid inside them** — it
returns the current event's `_RelayIdentity(session_gen, utterance_id)` snapshot (None fields on
id-less payloads; degrades via getattr on legacy fakes). The daemon-synthesized seq is
`_bulk_next_seq(gen, uid)` (:2092) — a plain dict `self._bulk_seq` keyed (gen, uid), incremented
INSIDE `_bulk_handle_partial`/`_bulk_handle_final`. So the lab wrapper (which replaces those
attributes before first arm) can stamp: identity BEFORE calling orig; seq by reading
`d._bulk_seq.get((gen, uid))` AFTER orig returns (None when the listening gate dropped the event).
No production change needed. disposition stays "" (S3's inferred supersession handles it — honest
gap, documented).

## 4. Fail-closed / blocked design (from the item + architecture doc)

- **Unsafe env**: existing guard (refuse outside disposable runtime) — keep.
- **Missing preflight → BLOCKED** (not a harness crash): today PI_BIN/ghostty/clips/sway misses
  raise mid-run and surface as `{"stage":"harness","pass":false}`. Add `preflight(route_name) ->
  str | None` checked in `run_route` BEFORE any spawn (shutil.which sway/xvfb-run[/ghostty,
  PI_BIN for needs_pi], VOICE_DIR *.wav + matching .words.json, SYSTEM_PY): reason string →
  `log({"stage":"preflight","verdict":"blocked","route":...,"reason":...})`, rc 1, nothing spawned.
- **Wrong arm → refuse to measure**: requested selector set but host's installed
  `partial_callback` != `_PARTIAL_SOURCES[requested]` (or reverse-lookup of the effective key
  fails) → RuntimeError → honest harness-fail line. Never measure a mislabeled arm.
- **Truncated evidence**: `len(ready) >= ready.maxlen` → RuntimeError (cannot attribute);
  `len(flog.events) >= flog.cap` → `record.capped=True` (S3 reports it; does not impute).
- **Raw speech**: remove `first_partial` snippets (warm + replay log lines) — counts only.
  Internal records keep text (metrics input); stdout stays pasteable into evidence.

## 5. Consumer handoffs

- **S5** (Pi prompt frame observation): keeps `PiGhosttyRoute.bulk_target_factory` (injected
  adapter + `_CancelOnLeaveTarget` reset), the poll loop/`field_log`, `preflight_note`
  ("10 ms read-poll granularity"); reset edits excluded via `anchor_text` + S3 reset rules.
- **S6** (paired comparison): runs `--partial-source plain` vs omitted (default) per route; each
  run's stdout verdict line + artifact carry requested/effective provenance; matched fixture
  settings = `build_cfg` untouched, same clips/cadence/warmup discipline.
- **T2.S3** (qualification): cites the S3 counters now populated by the runner.

## 6. Test-file facts

- No `tests/test_g5_timing_lab.py` exists (ls: only g5_make_alignments.py, g5_timing_lab.py,
  g5_timing_support.py, g6_assessment.py + test_g5_timing_support/test_g6_assessment).
- Import pattern (test_g5_timing_support.py :22-24): `sys.path.insert(0, str(Path(__file__).resolve().
  parent))` then `import g5_timing_support as g5` → same works for `import g5_timing_lab as lab`.
- g6_assessment.parse_route_verdicts (:289, regex :80) accepts `pass|fail|blocked` — but S4's doc
  edit adds NO new verdict-shaped table (one current table only).
- Evidence doc: run commands :28-47, verdict table :14-19, "Lab-side bridges" :128, Hygiene :167.

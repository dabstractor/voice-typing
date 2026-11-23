# P1.M6.T2.S1 research — dispatch wiring + bulk cancel intercept (verified live @ HEAD)

All cites verified against the working tree this session (post-`2335a9e`; the item contract's
line cites have DRIFTED — mapping below). No code was modified.

## 1. Line-cite drift map (contract → current HEAD)

| Contract cite | Current | What |
|---|---|---|
| daemon.py:1142 | **:1246** | `def on_final` |
| daemon.py:1281 | **:1422** | `self._stream.commit(cleaned)` |
| daemon.py:1500 / :1516 | **:1684 / :1700** | `def _on_partial` / `self._stream.on_partial(text)` |
| daemon.py:780-785 | **:857-862** | `StreamingOutput(...)` ctor |
| daemon.py:1754 | **:1938** | `def cancel()` |
| daemon.py:1775-1778 | **:1961-1964** | not-armed idempotent return |
| daemon.py:1779 | **:1966** | `n = max(tail_len - 1, 0)` |
| daemon.py:1781 | **:1968** | `self._backend.press_backspace(n)` (the intercept target) |
| daemon.py:1621-1630 | **:1805-1814** | `_on_cancel_backspace` |
| daemon.py:2691-2694 | **:2931-2935** | ControlServer `cmd == "cancel"` → `self._daemon.cancel()` |

Other pinned sites: `cleaned = textproc.clean` **:1360**; rejected-final block :1362-1403;
`record_final` **:1451**; `_arm` **:1541** (set_microphone(True) :1593); `_disarm` **:1603**
(set_microphone(False) :1636); `_request_stop` **:1703**; `_reset_stream_after_cancel` **:1753**;
`note_user_keypress` **:1765**; `_on_cancel_backspace` **:1805**; `_refresh_context_prompt`
**:1890**; `_complete_drain` :1996; `_handle_dead_host` :1153; `request_shutdown` **:2341**;
`status_snapshot` **:2463-2523**; daemon ctor **:661-672** (injection seams: recorder,
recorder_host, host_factory, backend, latency, mic_prober, key_listener, ducker);
`_build_default_ducker` :146 (the factory precedent). Out-of-lock `_safe_abort()` call sites
(the post-disarm choke points): **:1736** (_request_stop immediate), **:1796** (HALT keypress),
:2037 (drain watchdog), :2067 (idle auto-stop), :2395 (shutdown). RecorderHost callback wiring:
`_load_host` :930, factory call :961-982 (`self.on_final, self._on_partial, self._touch_speech`).

## 2. The landed controller API (voice_typing/bulk_controller.py — G2-passed)

- Ctor `BulkController(target, *, queue_size=32, on_stopped=None, op_deadline=0.25)` (:219).
  `on_stopped` fires EXACTLY ONCE per delivery lifetime with ONE reason word:
  `queue-overflow | op-deadline | refused | unknown | target-error | stopped` or the
  acquire-failure reason / `takeover: <reason>` — "the disarm seam the daemon consumes
  (P1.M6.T2.S1 wires it to the bulk AND recording disarm)" (ctor docstring, verbatim).
- Lifecycle (daemon-thread calls): `acquire()->bool` (:288), `start()` (:313, launches the ONE
  writer thread), `stop(*, leave=True)` (:331 — joins writer ≤5 s, runner shutdown(wait=False),
  `target.leave()` exactly once; IDEMPOTENT), `halt_for_takeover(reason)` (:368),
  `cancel(*, gen=None)->bool` (:385 — ONE `target.cancel` op under the same deadline; nothing
  pending ⇒ True with ZERO target calls; refused/unknown/deadline ⇒ False via the stop path;
  "NO physical-character compensation … P1.M6.T2.S1's intercept routes here" — verbatim),
  `arm(gen)->bool` (:471 — SESSION_BEGIN barrier; resets per-gen state; events with gen ≠
  session_gen are discarded).
- Event entries (reader threads; **enqueue-and-return ONLY**): `on_partial(span, *, utterance,
  seq, gen)` (:500 — coalesce newest-wins), `on_final(span, *, utterance, seq, gen)` (:539 —
  ordered barrier), `on_final_dropped(*, utterance, gen)` (:571 — boundary with NO finalize).
- State: `is_active()` :599, `latest_recognized()` :604, `accepted_final()` :611,
  `confirmed_visible()` :618, `stats()` :626 (counts+reasons, never text).
- `utterance` is a **str**; `seq` a per-(gen,utterance) monotonic int (late seq discarded);
  the relay gives NO seq — the daemon must synthesize one (per-(gen,uid) counter).
- **Gap found**: no per-op callback — `feedback.record_confirmed_op` ("Called by the bulk
  wiring on each in-time ShowResult.APPLIED", feedback.py:261) cannot be driven without a tiny
  additive `on_applied` ctor kwarg fired at the APPLIED branches (:459 cancel, :737-741
  _process_next). Default None ⇒ G2 suite unaffected.

## 3. Adapters + takeover (all landed, duck-typed `DeliveryTarget`)

- `ime/target.py:75 ImeTarget(proc)` — acquire :97 / show :151 / finalize :282 / leave :312 /
  cancel :331; `last_reason`; units UTF8_BYTES.
- `ime/manager.py:86 ImeProcess(on_delivery_state=None, on_event=None, python_exe=None,
  log_path=None, spawn_timeout, stop_timeout, _popen=None)` — spawn()/request()/stop()/
  healthy()/state. **on_delivery_state is the ready-made M6 feedback seam** (unsupported/fault
  ONLY, per its docstring).
- `ime/takeover.py:196 TakeoverWatch(proc=None, target=None, controller=None, detector=None)`
  — leave() FIRST then `controller.halt_for_takeover(reason)`, one-shot latch; attach(proc).
- `pi_editor.py:352 PiEditorTarget(client)`; `PiEditorClient(sock_path=None, on_event=None)`
  :158; `PiEditorTakeoverWatch(controller=, target=)` :720 (attach(client)/close()).
- Zero daemon-side wiring exists today: `grep -rn 'ImeTarget\|PiEditorTarget\|BulkController'
  voice_typing/daemon.py` → nothing. status_snapshot's 4 delivery keys are read via feedback
  `.get` with seeds and are documented "written ONLY by the bulk wiring (P1.M6.T2.S1)" (:2505-2520).

## 4. Config + feedback surface (landed by P1.M3.T3.S1/S2 — this item only WRITES)

- config.py:147 `delivery: str = "stream-edit"`; value validation :174-186; **precondition
  triple** :416-433 (bulk-text ⇒ streaming=true, graceful_stop=false, keypress_action="disarm",
  ONE ValueError listing all violations).
- feedback.py: `set_delivery_mode(mode)` :216 (daemon calls at boot with the [output] delivery
  value — docstring says P1.M6.T2.S1), `set_delivery_state(state, reason="")` :234 (taxonomy
  inactive|active|unsupported|fault; controller stop reasons → fault; clean stop → inactive;
  acquire failure → unsupported; reason ALWAYS overwritten, sanitized ≤160 chars),
  `record_confirmed_op(op)` :261 (descriptor = counts+times, e.g. "insert utt=3 seq=7 rev=12
  +34ch 41ms"). ctl.py :130-153 already renders all four.

## 5. Structural facts that shape the design

- **on_final order** (:1246): listening gate → `_on_final_lock` → cancel-suppression window
  (:1262-1359; early-returns for dropped/sentinel finals; its `_stream.freeze` absorb calls are
  gated on `_pending_tail_len() > 0` → always 0 in bulk mode since the bulk branch never feeds
  `_stream`) → `cleaned = textproc.clean` :1360 → rejected-final block :1362-1403 → streaming
  commit :1418-1424 / Rev1 type :1426+ → `record_final` :1451 → latency INFO line (carries
  `text=<repr>` — R.5 forbids recognition text in NEW bulk logs) → reset_boundary +
  `_refresh_context_prompt` (reads `_stream.committed` — stays empty in bulk mode; the prompt
  source decoupling is P1.M6.T3.S1, NOT this item).
- **cancel()** (:1938): `with self._lock:` → not-armed return → `tail_len` :1965 → `n` :1966 →
  `press_backspace(n)` :1968 → host.cancel + suppress latch :1969-1979 (gated on
  `_text_in_flight`) → `_reset_stream_after_cancel()` :1980 (also clears the Feedback partial
  mirror — worth keeping in bulk). The bulk intercept must branch BEFORE :1965 and must NOT run
  `controller.cancel()` under `_lock` (it can fire `on_stopped` synchronously → the handler
  takes `_lock` → **deadlock**). Entries (socket :2931, evdev :1805) need NO change — they call
  `cancel()`.
- **Locks**: `_lock` :709 (cancel/arm/disarm); `_on_final_lock` :716 (clean→type→record). NEW-2
  lesson (in `_disarm` docstring): nothing blocking under `_lock`. Controller `stop()` joins the
  writer ≤5 s and `leave()` is a subprocess round-trip ⇒ bulk teardown must be OUT of lock —
  solved with a coalesced stopper daemon thread scheduled from `_disarm()` (thread spawn under
  lock is the ducking-heal precedent, __init__ :904-913).
- **_arm()/_disarm()** run under `_lock`; `_safe_abort()` is called AFTER release at the five
  sites in §1. Ducking engage precedent: `_duck_engage()` called from `_arm()` under lock,
  dispatches async (AsyncDucker) — the bulk arm (acquire is a subprocess round-trip) must use
  the same shape: schedule a short-lived "vt-bulk-arm" thread from `_arm()`.
- **relay_identity** (P1.M6.T1.S1, landing in parallel — treated as contract): `host.relay_identity`
  read inside on_final/_on_partial (they run ON the reader thread where it is valid); events
  carry additive `utterance_id`/`session_gen`; child bumps session_gen per arm cmd — the daemon
  sends exactly one arm cmd per `_arm()` (set_microphone(True) :1593 → `("arm", {})`,
  recorder_host.py:258), so a daemon-side counter bumped in `_arm()` before the cmd put stays
  1:1 with the child's stamps (both start effectively at 1 on first arm).
- **Test patterns**: test_daemon.py `_FakeHost` :561 / `_fake_host_factory` :665 / `_make` :683
  (kwargs incl. cfg=, backend=, host_factory=); test_g2_bulk_gate.py `G2FakeTarget` :107 +
  `_controller(fake, ...)` :240 + `_wait_until` :248 (reuse for the dispatch tests' fake
  target); `_no_legacy_backend` monkeypatch :77 (the zero-legacy-backend-calls assertion idiom).

## 6. Design decisions (the recipe the PRP encodes)

D1. Branch gates: everything keyed on `self._cfg.output.delivery == "bulk-text"`; inert
    otherwise (G1 byte-identical default).
D2. on_final: insert the bulk branch right after :1360 (`cleaned`), BEFORE the rejected-final
    block; it handles rejection via `on_final_dropped`, acceptance via `on_final` +
    `record_final` + drain-flag bookkeeping + a counts-only INFO line; returns before every
    `_stream`/legacy-backend/latency-text path. Suppression-window early-returns (:1262-1359)
    stay AHEAD of it by design (the cancelled utterance was already purged+closed
    controller-side by `cancel()`; `ctrl.cancel`'s purge makes the racing final a dup-discard).
D3. _on_partial: after the listening gate, bulk branch → `ctrl.on_partial` +
    `feedback.update_partial(text)` + `latency.note_partial(text)`; never `_stream.on_partial`.
D4. Identity: `getattr(host, "relay_identity", None)`; missing identity in bulk mode ⇒
    drop-and-count (a `_bulk_dropped_no_id` counter) — R.5 ordering cannot be honored without
    identity; boundary/drain flags still cleared.
D5. seq synthesis: daemon-side per-(gen,uid) counter (`_bulk_next_seq`), lazily cleared on gen
    advance; final takes last+1.
D6. Arm: `_arm()` bumps `self._bulk_gen` (cheap, in lock) + schedules the "vt-bulk-arm" thread
    (epoch-captured): lazily build the bundle (default = IM route per R.4) → `ctrl.acquire()` →
    `ctrl.arm(gen)` → `ctrl.start()` → feedback active / unsupported+reason. Partials racing the
    acquire are dropped-with-count (controller rejects inactive events by design).
D7. Disarm: `_disarm()` (in lock) flips `delivery_state`→inactive ONLY when the daemon-side
    active flag is set, and schedules the coalesced epoch-guarded "vt-bulk-stop" stopper thread
    running `ctrl.stop(leave=True)` + watch detach (never under `_lock` — NEW-2). Fault path:
    `on_stopped` handler clears the active flag FIRST, writes fault+reason, then disarms
    recording (`with _lock: _disarm()` + out-of-lock `_safe_abort()`).
D8. Cancel: `cancel()` branches at the very top on bulk mode BEFORE acquiring `_lock`;
    `_bulk_cancel()` = ctrl.cancel(gen) OUT of lock → the SHARED recognition-side cancel under
    `_lock` (suppress latch + host.cancel, re-check listening) → `_reset_stream_after_cancel()`
    (clears the partial mirror) → reply. NO press_backspace, NO tail math.
D9. `on_applied` additive hook on BulkController (ctor kwarg, default None; fired outside
    `_cond` at both APPLIED branches with (kind, gen, utterance, seq, revision, chars,
    elapsed_ms)) → daemon formats + `feedback.record_confirmed_op(...)`. G2 suite re-run is a
    hard gate.
D10. Adapter bundle seam: ctor kwarg `bulk_target_factory=` (pattern: ducker=/host_factory=);
     default `_build_default_bulk_target(cfg)` = IM bundle (ImeProcess + ImeTarget +
     TakeoverWatch; ImeProcess.on_delivery_state → feedback.set_delivery_state). The
     pi-editor bundle (PiEditorClient/PiEditorTarget/PiEditorTakeoverWatch) is available via
     the seam; NO new config keys in this item (adapter selection by config is out of scope).
D11. Teardown on quit: `request_shutdown()` schedules the stopper + bounded join (≤1 s) so the
     adapter subprocess (ImeProcess) is terminated deterministically.
D12. Docs: daemon.py module docstring (Mode A) gains the delivery-wiring note; scope boundaries
     honored (no streaming.py/typing_backends.py/ime/pi_editor edits; bulk_controller.py gets
     ONLY the additive hook).

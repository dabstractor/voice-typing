# PRP — P1.M2.T7.S1: `cancel` — control socket + recorder abort/discard + ctl + keybind + install usage

---

## Goal

**Feature Goal**: A socket-level `cancel` command that, while armed with a pending streaming `tail`,
deletes the tentative tail (compensating for the physical Backspace keystroke), discards the child's
buffered/in-flight audio so NO late final can land, suppresses the abort sentinel final (nothing
typed, nothing recorded), keeps the daemon listening, and is fully idempotent when no tail is
pending. Exposed end-to-end: daemon `_dispatch` case, `voicectl cancel`, a Hyprland
`SUPER ALT, Backspace` fallback bind, and install.sh usage text.

**Deliverable**:
1. `RecorderHost.cancel()` + child-side cancel-aware abort path (discard + marked sentinel) in `voice_typing/recorder_host.py` — plain `abort()` (drain watchdog) behavior UNCHANGED.
2. `VoiceTypingDaemon.cancel()` + `_dispatch` `'cancel'` case in `voice_typing/daemon.py`.
3. `voice_typing/ctl.py`: `cancel` in `_COMMANDS`, docstring, epilog/usage.
4. `hypr-binds.conf`: activate the `SUPER ALT, Backspace` bind + doc comment.
5. `install.sh`: usage line gains `cancel` + Backspace bind mention.
6. Tests in `tests/test_recorder_host.py`, `tests/test_daemon.py`, `tests/test_control_socket.py`, `tests/test_voicectl.py`.

**Success Definition**: All new + existing unit tests pass (`timeout 600 uv run pytest <file> -q`); `voicectl cancel` returns `{"ok": true, "listening": true}` (renders `listening: on`, exit 0); a repeated cancel with no pending tail is a no-op; the cancelled sentinel is dropped by the daemon (no typing, no `record_final`); the child's audio buffers are cleared (fake-recorder assert); plain abort/drain semantics are bit-identical to before.

## User Persona (if applicable)

**Target User**: The dictating user (owner of this machine).

**Use Case**: Mid-dictation, the recognizer has typed a wrong/garbage tentative fragment. The user presses Backspace (or `SUPER ALT, Backspace` when evdev can't open a keyboard): the fragment vanishes, the in-flight utterance is dropped, the mic stays hot — just say the sentence again.

**User Journey**: arm → speak → partial tail appears (typed) → recognizer wobbles → user hits Backspace → tail rewound (`len(tail)−1` chars, the keystroke deleted the 1st) → daemon still listening → next utterance transcribes fresh (no stale "flushed out the last of what got cut off" double-type).

**Pain Points Addressed**: wrong tentative text persisting; stale buffered audio re-typed after abort; needing a full stop/start cycle to recover.

## Why

- PRD §4.2quater "Backspace-cancel": the ONLY mechanism allowed to delete typed text (stranded tails FREEZE, never delete). `voicectl cancel` is the keybind fallback when the evdev listener (P1.M2.T7.S2) cannot open a keyboard node, and the automated-test seam (T8e).
- Unblocks P1.M2.T7.S2 (evdev trigger calls the same daemon path) and P1.M3.T8.S2 assert (e).
- Removes the daemon↔child race where a cancel-intent abort still lets a queued final land (the documented double-type bug class, recorder_host.py:545-549).

## What

User-visible:
- `voicectl cancel` (or a `{"cmd":"cancel"}` socket line): if armed AND a tail is pending → rewind `max(len(tail)−1, 0)` chars via `press_backspace`, drop the child's in-flight utterance (abort + discard buffered audio), reset streaming state to a fresh tail at the current cursor (`committed` unchanged — the fragment is GONE, not committed), keep listening. Response `{"ok": true, "listening": true, ...status}`.
- If NOT armed or NO pending tail → no-op response (idempotent; further Backspaces are plain user edits, never compensated).
- `SUPER ALT, Backspace` Hyprland bind runs `voicectl cancel` (fallback when no keyboard node is readable).
- `install.sh` usage text lists `cancel`.

### Success Criteria

- [ ] `_dispatch("cancel")` routes to `VoiceTypingDaemon.cancel()` and returns `{"ok":True,"listening":True,...}` when armed with a tail.
- [ ] Cancel with no tail / disarmed returns `ok:true` WITHOUT issuing any `press_backspace` (idempotent).
- [ ] `backend.press_backspace(max(len(tail)-1, 0))` called exactly once per real cancel; never any `type_text` of the cancelled fragment; `feedback.record_final` NOT called for the cancelled utterance.
- [ ] Child: cancel path unblocks `host.text()` (sentinel still emitted) but the sentinel is marked cancelled and the daemon DROPS it; a real final racing the cancel is also dropped (suppression flag cleared only by the marked sentinel).
- [ ] Child: `_clear_recorder_audio` invoked on the cancel path (fake-recorder assert: `clear_audio_queue` + drain of `recorded_audio_queue`).
- [ ] Plain `abort()` path (drain watchdog `_safe_abort`) behavior unchanged: sentinel `("final", {"text": ""})` unmarked, existing tests untouched and passing.
- [ ] `ctl.py` `_COMMANDS == ("toggle","start","stop","status","quit","cancel")`; docstring/epilog/usage updated; `voicectl cancel` renders `listening: on`, exit 0; unknown-cmd still exits 64.
- [ ] `hypr-binds.conf` contains active `bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel` + explanatory comment; `install.sh` usage line includes `cancel` and mentions the Backspace bind.

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, could they implement this successfully?" — Yes: every edit site is pinned below with line numbers, exact existing patterns to copy, the child-blocking constraint that forbids a queue-only cancel command, and the VT-007 sentinel contract.

### Documentation & References

```yaml
- docfile: plan/007_cfc245548aec/architecture/daemon_control_map.md
  why: Authoritative map of stop/drain/abort, ControlServer._dispatch, ctl.py surface, test seams
  section: "§3 Stop/drain/abort", "§4 Control socket", "§6 Test seams"
  critical: abort_event polling thread is the ONLY cross-process unblock; _dispatch 'stop' is the template; _safe_abort skips unless _text_in_flight

- file: voice_typing/recorder_host.py
  why: All child-side edits live here
  pattern: abort() :237-246; _abort_handler :517-524; cmd loop :526-561 ('disarm' discard :549-554); _clear_recorder_audio :586-620; _run_text_and_emit_final :~623-646
  gotcha: the child BLOCKS in recorder.text() — a queued ('cancel',{}) command would never be read while blocked; cancel MUST ride the polled-event mechanism

- file: voice_typing/daemon.py
  why: _dispatch + daemon.cancel()
  pattern: _dispatch :1852-1885 ('stop' case :1874 is the template); _safe_abort :1400-1428; _request_stop :1105-1130 (locking pattern); on_final pipeline :980-1005; status_snapshot :1613-1646
  gotcha: never call host.abort()/cancel() when NOT _text_in_flight (abort blocks on was_interrupted.wait() in RealtimeSTT)

- file: voice_typing/ctl.py
  why: command surface + rendering
  pattern: _COMMANDS :37 (comment already says 'cancel' is appended by this task); docstring :26-28; format_result ok/shutting_down/status/default branches :47+
  gotcha: cancel is NOT an arm command — no _LOADING_HINT_DELAY wrapping; exit codes 0/1/2/64 must stay exclusive

- file: voice_typing/typing_backends.py
  why: press_backspace(n) primitive (complete since P1.M1.T3.S1)
  pattern: ABC :69, wtype :88, ydotool :107, fallback :159
  gotcha: batched; n=0 must be a safe no-op (verify existing impl — if it shells out for n=0, guard in daemon.cancel with `if n > 0`)

- file: hypr-binds.conf
  why: commented placeholder for this exact bind already exists at EOF
  pattern: last 2 lines "(P1.M2.T7.S1) cancel fallback bind — ADDED by that task:" + commented bind
  gotcha: file is SOURCED by users' hyprland.conf — comments ARE the docs (Mode A)

- file: install.sh
  why: usage lines :209-210 must gain cancel + Backspace bind mention
  pattern: echo usage :209; bind mention :210-213
  gotcha: README (P2 task) copies these snippets verbatim — keep them stable

- file: tests/test_daemon.py
  why: _FakeHost :532-613, _FakeBackend :493-504, _make_lazy_daemon :2859-2867, mic_prober=_ok_probe :506-513
  pattern: extend the fakes (cancel recording, press_backspace recording) rather than new harness
  gotcha: never load real CUDA in unit tests

- file: tests/test_recorder_host.py
  why: fake-recorder pattern for abort/sentinel unit tests — reuse for cancelled-sentinel + discard asserts
- file: tests/test_control_socket.py
  why: _dispatch unit tests; fake-daemon-object pattern (:131)
- file: tests/test_voicectl.py
  why: _COMMANDS surface + format_result tests
```

### Current Codebase tree (relevant excerpt)

```bash
voice_typing/
  config.py            # complete (P1.M1.T1.S1); [cancel].devices field already there for T7.S2
  ctl.py               # 5 commands; cancel slot reserved
  daemon.py            # no streaming state yet (P1.M2.T6 planned) — cancel needs a narrow seam
  recorder_host.py     # abort/sentinel/discard primitives all present
  typing_backends.py   # press_backspace(n) done
hypr-binds.conf        # cancel bind pre-stubbed as comments
install.sh             # usage lines :209-210
tests/                 # test_recorder_host.py test_daemon.py test_control_socket.py test_voicectl.py
```

### Desired Codebase tree with files to be added/modified

```bash
voice_typing/recorder_host.py    # MODIFY: RecorderHost.cancel(); child cancel_event; marked sentinel; discard on cancel
voice_typing/daemon.py           # MODIFY: VoiceTypingDaemon.cancel(); _dispatch 'cancel' case; on_final suppression
voice_typing/ctl.py              # MODIFY: _COMMANDS + docstring + epilog
hypr-binds.conf                  # MODIFY: activate bind + comment
install.sh                       # MODIFY: usage lines
tests/test_recorder_host.py      # MODIFY/ADD: cancelled-sentinel + discard tests
tests/test_daemon.py             # ADD: daemon.cancel() semantics tests (backspace math, idempotence, suppression)
tests/test_control_socket.py     # ADD: dispatch cancel + response shape
tests/test_voicectl.py           # ADD: cancel accepted + rendered
plan/007_cfc245548aec/P1M2T7S1/research/  # already written (cancel_edit_sites.md)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: the child's command loop BLOCKS inside recorder.text() while listening — a queued
#   ("cancel", {}) cmd_q command is NEVER read until text() returns. Cancel must be signaled via a
#   polled cross-process Event exactly like abort_event (recorder_host.py:517-524 pattern).
# CRITICAL: RealtimeSTT recorder.abort() blocks on was_interrupted.wait() if text() is not in
#   flight — mirror _safe_abort's gate: only touch host.cancel() when _text_in_flight (daemon.py:1423-1424).
# CRITICAL: the abort-sentinel MUST still be emitted on cancel or host.text() wedges the run loop
#   forever (the VT-007 regression) — cancel changes its PAYLOAD (add "cancelled": True), never its existence.
# RACE: a REAL final can be emitted by the recorder's on_final thread just before abort takes
#   effect — the daemon needs a suppression flag set at cancel time, cleared only by the marked
#   sentinel, so any final in that window is dropped (textproc.clean('') rejection is NOT race-safe).
# The evdev listener is P1.M2.T7.S2 — do NOT implement it here; this PRP is socket/daemon/child/CLI only.
# voicectl calls have NO socket read timeout (AGENTS.md) — tests use the direct _dispatch/format_result
#   seams; any live check is `timeout 30 .venv/bin/voicectl ...`.
# hypr-binds.conf is sourced by users' configs — keep the existing header structure; append/activate, don't restructure.
```

## Implementation Blueprint

### Data models and structure

No config/schema changes (the `[cancel]` table already exists from P1.M1.T1.S1; `devices` is T7.S2's concern). New runtime state only:

```python
# recorder_host.py — RecorderHost.__init__: add alongside _abort_event
self._cancel_event = <same MP-event construction as _abort_event>   # cross-process, polled by child

# daemon.py — VoiceTypingDaemon.__init__
self._cancel_suppress_final = False   # set on cancel; cleared by the cancelled sentinel
```

Streaming seam (dependency on P1.M2.T6, which is PLANNED — code defensively):

```python
# daemon.cancel() interacts with the streaming state ONLY through this narrow seam.
# If P1.M2.T6 has landed, adapt at this single call site to its real API.
def _pending_tail_len(self) -> int:
    """Chars of the tentative tail typed since the last commit checkpoint. 0 = nothing pending."""
    stream = getattr(self, "_stream", None)          # StreamingOutput (P1.M2.T6) — may not exist yet
    if stream is None or not self._listening.is_set():
        return 0
    getter = getattr(stream, "pending_tail_len", None)
    return int(getter()) if callable(getter) else 0

def _reset_stream_after_cancel(self) -> None:
    """Fresh tail at the current cursor; committed unchanged. No-op pre-T6."""
    stream = getattr(self, "_stream", None)
    reset = getattr(stream, "reset_after_cancel", None)
    if callable(reset):
        reset()   # T6: clears tail, suppresses pending partial typing until next utterance boundary
    self._feedback.update_partial("")
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/recorder_host.py — child-side cancel
  - ADD: self._cancel_event (same construction as _abort_event; it must be visible to the CHILD,
    i.e. if abort_event is a multiprocessing.Event passed to the child, cancel_event uses the identical
    mechanism — follow how _abort_event is created/inherited, ~recorder_host.py:103-152).
  - MODIFY child _abort_handler (:517-524): ALSO poll _cancel_event; when set:
      cancel_event.clear(); aborted.set(); cancelled_event.set(); then recorder.abort() (same
      try/except best-effort). cancelled = the existing local `aborted`-style threading.Event pattern
      — add a sibling `cancelled = threading.Event()` next to `aborted` (:507) and pass BOTH into
      _run_text_and_emit_final.
  - MODIFY the 'text' command case (:529-536): clear cancelled alongside aborted/abort_event.
  - MODIFY _run_text_and_emit_final (~:623-646): new param `cancelled: threading.Event | None = None`;
    on the abort path, if cancelled is set: call _clear_recorder_audio(recorder) (import/call the
    existing :586-620 helper — defensive, never raises) and emit
    _safe_put(evt_q, ("final", {"text": "", "cancelled": True})); else keep the existing unmarked
    sentinel EXACTLY as-is (drain-watchdog path unchanged). Docstring: extend the VT-007 note.
  - ADD RecorderHost.cancel() (next to abort(), ~:247): set _cancel_event AND _abort_event in that
    order (abort_event alone would unblock without discard; cancel_event alone is never polled fast
    enough alone — both together); same best-effort try/except (OSError, EOFError) → self._dead = True.
    Docstring states the contract: unblocks text(), discards buffered audio, sentinel is marked
    cancelled; abort() semantics untouched.
  - NAMING: cancel_event / cancel() / "cancelled": True (payload key, past participle — matches the
    'final'/'aborted' house style).

Task 2: MODIFY voice_typing/daemon.py — daemon.cancel() + suppression
  - ADD VoiceTypingDaemon.cancel() -> dict (place next to _request_stop, ~:1105):
      with self._lock:
          if not self._listening.is_set():
              return {"ok": True, **self.status_snapshot()}          # not armed -> idempotent no-op
          tail_len = self._pending_tail_len()
          n = max(tail_len - 1, 0)                                   # physical keystroke already deleted 1
          if n > 0:
              self._backend.press_backspace(n)                       # compensate by subtraction, NEVER re-type
          if self._text_in_flight and self._host is not None:
              self._cancel_suppress_final = True                     # drop the racing real final AND the sentinel
              self._host.cancel()
          self._reset_stream_after_cancel()                          # committed unchanged; partial mirror cleared
      return {"ok": True, "listening": True, **self.status_snapshot()}
    Docstring: idempotence + the max(len(tail)-1,0) math + freeze-rule context (PRD §4.2quater).
  - MODIFY on_final pipeline (~:980-1005), FIRST (before the listening gate or immediately after it,
    under the same _on_final_lock):
      if self._cancel_suppress_final:
          if <this final is the cancelled sentinel>: self._cancel_suppress_final = False
          return  # drop everything: no clean, no type_text, no record_final
    How the daemon sees the marker: the reader thread in recorder_host currently passes only the
    text string to on_final. Extend minimally: the reader (find the 'final' event handling in
    recorder_host.py that invokes self._on_final) checks payload.get("cancelled") and either
    (a) exposes host.take_cancelled() / a last-event flag the daemon polls, or (b) preferred: change
    the internal hook so on_final receives the sentinel as the EMPTY string and add a
    RecorderHost.consume_cancel_mark() -> bool (reader sets a host-side flag when it relays a
    marked final; daemon's on_final checks/clears it). Choose (b)-style: smallest blast radius;
    keep the public host.text(on_final) signature unchanged.
  - MODIFY ControlServer._dispatch (template: the 'stop' case :1874):
      if cmd == "cancel":
          return self._daemon.cancel()
    Update the protocol docstring (:1696-1697) with the cancel line + response shape.

Task 3: MODIFY voice_typing/ctl.py
  - _COMMANDS (:37): ("toggle","start","stop","status","quit","cancel") — replace the trailing
    comment. Update module docstring Subcommands block + Usage line + argparse epilog in
    _build_parser: `cancel  drop the pending dictation fragment and keep listening (Backspace keybind fallback)`.
  - format_result: cancel falls through the default branch ("listening: on/off") — verify via test;
    no loading-hint wrapping (not an arm command).

Task 4: MODIFY hypr-binds.conf
  - Activate the placeholder: replace the final two comment lines with
      # Cancel fallback (PRD §4.2quater / P1.M2.T7.S1): SUPER+ALT+Backspace runs the SAME cancel path
      # as the daemon's passive evdev Backspace listener (P1.M2.T7.S2). Use this bind when evdev
      # cannot open a keyboard node; also the automated-test seam.
      bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel
  - Keep the rest of the file byte-identical.

Task 5: MODIFY install.sh
  - Line :209 usage gains cancel: `voicectl toggle|start|stop|status|cancel|quit`
  - Add one echo line after :210 mentioning `SUPER+ALT+Backspace -> voicectl cancel (drops the pending fragment; see hypr-binds.conf)`.

Task 6: MODIFY tests/test_recorder_host.py — child contract
  - test cancel() sets both events (host-level, MP-event fakes or real Events).
  - test _run_text_and_emit_final with cancelled set: fake recorder records clear_audio_queue
    calls; assert sentinel ("final", {"text":"", "cancelled":True}) and that clear_audio_queue +
    recorded_audio_queue drain happened (reuse the existing fake-recorder pattern for the disarm
    discard test if present; else build per _clear_recorder_audio :586-620 attribute list).
  - test plain abort (cancelled unset) still emits ("final", {"text": ""}) UNMARKED and does NOT
    clear audio — regression guard for the drain-watchdog path.

Task 7: ADD tests in tests/test_daemon.py — daemon.cancel() semantics
  - Extend _FakeHost with cancel() (records calls; synthesizes a marked sentinel via the same
    mechanism the fake uses for finals) and _FakeBackend with press_backspace recording (append
    ('bs', n) alongside typed).
  - test_cancel_with_pending_tail_presses_len_minus_1: fake stream seam
    (daemon._stream stub with pending_tail_len/reset_after_cancel) → assert press_backspace called
    with max(len-1,0); type_text NEVER called with the fragment; record_final NOT called.
  - test_cancel_without_tail_is_noop: no _stream → no press_backspace, ok:true.
  - test_cancel_when_disarmed_is_noop: listening cleared → ok:true, host.cancel NOT called.
  - test_cancel_suppression_drops_racing_final_and_clears_on_sentinel: set up cancel, feed a REAL
    final then the marked sentinel through on_final → both dropped, flag cleared afterwards, a
    subsequent normal final flows through the pipeline normally.
  - test_cancel_keeps_listening: _listening still set after; status_snapshot listening true.

Task 8: ADD tests/test_control_socket.py — dispatch
  - test_dispatch_cancel_calls_daemon_cancel_and_returns_shape (fake daemon object, pattern :131):
    `{"cmd":"cancel"}` → daemon.cancel called once; response ok:true, listening true.
  - test_dispatch_cancel_unknown_still_rejected (guards the unknown-command fallthrough ordering).

Task 9: ADD tests/test_voicectl.py — CLI surface
  - test_cancel_in_commands_and_docstring/epilog; test 'voicectl cancel' routes (monkeypatched
    _send_command) and format_result('cancel', {"ok":True,"listening":True}) == ("listening: on", 0).
  - Unknown command still exits 64 (existing test suffices; keep passing).
```

### Implementation Patterns & Key Details

```python
# recorder_host.py — child cancel handling in _abort_handler (extend, don't replace)
while not stop_abort_thread.is_set():
    if cancel_event.wait(timeout=0.2):
        cancel_event.clear(); aborted.set(); cancelled.set()
        try: recorder.abort()
        except Exception: logger.exception(...)      # same best-effort posture
        continue                                      # re-loop; abort_event handled by the wait below
    if abort_event.wait(timeout=0.2):
        abort_event.clear(); aborted.set()
        ... # existing body unchanged

# _run_text_and_emit_final — cancel branch (before the existing sentinel put)
result = recorder.text(on_final)
if (aborted is not None and aborted.is_set()) or result is not None:
    if cancelled is not None and cancelled.is_set():
        _clear_recorder_audio(recorder)               # never raises (all-defensive helper :586-620)
        _safe_put(evt_q, ("final", {"text": "", "cancelled": True}))
    else:
        _safe_put(evt_q, ("final", {"text": ""}))     # UNCHANGED drain-watchdog path

# daemon.on_final — suppression head (runs under _on_final_lock, before any pipeline work)
if self._cancel_suppress_final:
    if self._host is not None and self._host.consume_cancel_mark():
        self._cancel_suppress_final = False           # sentinel seen; re-arm the pipeline
    return                                            # drop real final AND sentinel alike
```

### Integration Points

```yaml
SOCKET:
  - daemon.py _dispatch: add 'cancel' case (template 'stop' :1874); update protocol docstring :1696
STREAMING (P1.M2.T6 — planned, do not implement here):
  - seam: daemon._stream.pending_tail_len() / reset_after_cancel(); defensive getattr in this task
  - P1.M2.T7.S2 (evdev) will call the SAME VoiceTypingDaemon.cancel(); keep it lock-safe + fast
FEEDBACK:
  - feedback.update_partial("") after reset (state.json partial mirrors the now-empty tail)
DOCS (Mode A — rides with the work):
  - ctl.py docstring/--help; hypr-binds.conf comment; install.sh printed usage
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
ruff check voice_typing/ --fix && ruff format voice_typing/
ruff check tests/ --fix && ruff format tests/
# Expected: zero errors. (No mypy config in repo; ruff is the gate.)
```

### Level 2: Unit Tests (Component Validation)

```bash
# Per AGENTS.md: ALWAYS two timeouts; unit files only (no CUDA)
timeout 600 uv run pytest tests/test_recorder_host.py tests/test_control_socket.py tests/test_voicectl.py -q
timeout 600 uv run pytest tests/test_daemon.py -q -k 'cancel'
timeout 600 uv run pytest tests/test_daemon.py -q          # full file; existing behavior must be intact
# Expected: all pass; abort/drain/sentinel regression tests untouched and green.
```

### Level 3: Integration Testing (System Validation)

```bash
# Only if a daemon is already running under systemd; EVERY voicectl call under timeout 30:
timeout 30 .venv/bin/voicectl status
timeout 30 .venv/bin/voicectl cancel      # while idle -> ok, "listening: off" or on per state; exit 0
timeout 30 .venv/bin/voicectl cancel      # repeat -> identical (idempotence)
timeout 30 .venv/bin/voicectl badcmd; echo "exit=$?"   # 64
# Live armed-with-tail cancel (needs real mic + speech) is covered later by P1.M3.T8.S2 assert (e) — do NOT attempt here.
```

### Level 4: Docs/Usage Validation

```bash
grep -n 'cancel' voice_typing/ctl.py hypr-binds.conf install.sh   # all three surfaces list it
grep -c '^bind' hypr-binds.conf                                    # exactly 2 active binds
bash -n install.sh                                                 # syntax
timeout 600 uv run pytest tests/test_config_repo_default.py -q     # binds/config asserts still green
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1-4 all pass; `timeout 600 uv run pytest tests/test_recorder_host.py tests/test_daemon.py tests/test_control_socket.py tests/test_voicectl.py -q` green
- [ ] `ruff check voice_typing/ tests/` and `ruff format --check` clean

### Feature Validation

- [ ] All "Success Criteria" boxes above demonstrably true (each maps to a named test)
- [ ] Plain abort path verified unchanged (unmarked sentinel, no audio clear)
- [ ] Idempotence: cancel ×2 with no tail → no press_backspace, ok:true
- [ ] Response shape `{"ok":true,"listening":true}` at the socket

### Code Quality Validation

- [ ] No new patterns invented — cancel rides abort's event mechanism, 'stop' dispatch template, existing fakes extended
- [ ] Locking: `_lock` in cancel(); suppression checked under `_on_final_lock`
- [ ] Best-effort posture (never raises across IPC) matches set_microphone/abort style

### Documentation & Deployment

- [ ] ctl.py docstring/epilog list cancel; hypr-binds.conf bind active + commented; install.sh usage updated
- [ ] No changes to PRD.md, tasks.json, users' configs

## Anti-Patterns to Avoid

- ❌ Signaling cancel ONLY via the command queue — the child is blocked in `text()` and will never read it
- ❌ Skipping the sentinel on the cancel path — host.text() wedges forever (VT-007 regression)
- ❌ Dropping the sentinel via `textproc.clean('')` rejection alone — racy; use the explicit suppression flag
- ❌ Compensating with `len(tail)` backspaces or re-typing the tail — the keystroke already deleted one; subtract, never re-type
- ❌ Touching `abort()`'s existing behavior (drain watchdog `_safe_abort` depends on it)
- ❌ Implementing the evdev listener here — that is P1.M2.T7.S2
- ❌ Running the daemon in the foreground or an untimed `voicectl` (AGENTS.md Rules 1-2)

---

**Confidence Score**: 8/10 — every edit site is pinned with line numbers and verified patterns; the one soft spot is the P1.M2.T6 streaming seam (planned, not landed), handled via defensive getattr accessors so this task lands standalone and T6/T7.S2 snap onto the same `cancel()` entry point.

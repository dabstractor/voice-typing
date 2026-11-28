# PRP — P1.M1.T2.S5: Expose bounded focus-based context starts

## Goal

**Feature Goal**: Expose the §4.8.1 A **context-only start** on the existing control socket and CLI —
`{"cmd":"start-context","context":"...","mode":"block"|"stream"}` and
`voicectl start|start-block|start-stream --context-stdin` — as a *bounded, fail-closed* route into
S3's fenced start seam (`_start_fenced` / `start_with_seed`, with S4's first-accepted-final handoff
consuming the seed). It arms the EXISTING focus-based delivery (keyboard injection into the focused
window) with a first-utterance decode seed; it is **not** a pinned native editor session. It rejects
busy daemons atomically, reports `context_seeded` only on the child's bounded acknowledgement, never
echoes the seed, and on an old daemon / timeout / uncertain input reports the error with **no retry
and no fallback** to a plain start.

**Deliverable** (2 source files + 3 test files edited; no new files):
1. `voice_typing/daemon.py` — (a) `reject_busy: bool = False` keyword on `_start_fenced` (busy
   check inside S3's reserve block under `_lock`); (b) module constant `_CONTEXT_MAX_BYTES = 4096` +
   `_normalize_context()`; (c) `VoiceTypingDaemon.start_context()` + `_context_reply()` directly
   below `start_with_seed`; (d) the `start-context` route in `ControlServer._dispatch`; (e) Mode A
   protocol docstring lines distinguishing focus delivery from pinned native sessions.
2. `voice_typing/ctl.py` — (a) `--context-stdin` flag + help/epilog/module-docstring text;
   (b) `_utf8_suffix()` + `_read_context_stdin()` (memory- and monotonic-deadline-bounded);
   (c) `extra` pass-through on `_send_command_with_loading_hint`; (d) `start-context` branch in
   `format_result`; (e) `main()` wiring: flag validation (64) → socket path (2) → stdin read (1) →
   ONE send → old-daemon hint / uncertain-outcome line (1).
3. `tests/test_voicectl.py`, `tests/test_control_socket.py`, `tests/test_daemon.py` — the sections
   listed under Implementation Tasks (mock stdin, monotonic deadline, fake child, stub/legacy daemon).

**Success Definition**:
- (a) Wire/CLI parity: each of `start`, `start-block`, `start-stream` with `--context-stdin` sends
  exactly one `{"cmd":"start-context","context":<str>[,"mode":...]}` line (`mode` absent / `"block"` /
  `"stream"`); stdout is `listening: on` + `context: seeded` | `context: unseeded (<reason>)`; exit 0.
- (b) Seeded start: capture opens only after the child's confirmed prime (S2/S3); reply
  `context_seeded:true` + `context_tokens`; the seed string is absent from the reply, status
  snapshot, and DEBUG logs.
- (c) Empty / whitespace-only → `context_reason:"empty"`; `asr.context_prompt` off → `"disabled"`;
  host without the confirmed channel → `"unavailable"` (never `context_seeded:true` — a best-effort
  put is not confirmation). All three start UNSEEDED via the plain fenced arm (known-clear-or-no-
  executor guarantee inherited from S3).
- (d) Busy: while arming (`_arming` set / loading), listening, or draining → `ok:false`,
  `error:"start-context rejected: busy (arming, listening or draining)"`; no reservation taken, no
  prime call, mic untouched, the in-flight arm / live session unaffected.
- (e) Unconfirmed seed / unknown prompt / load failure → `ok:false`, `context_seeded:false`, fixed
  error text, not armed.
- (f) Client: flag on any other command → 64 (nothing sent); stdin not at EOF within
  `_STDIN_DEADLINE_S` (2 s) or unreadable → 1 BEFORE the socket, nothing sent; old daemon
  (`unknown command`) → 1 + hint; socket timeout / malformed reply → 1 + "outcome unknown — not
  retried"; exactly one send on every path; the seed never appears in stdout/stderr.
- (g) Ordinary commands unchanged: `toggle`/`start`/`start-*`/`stop`/`status`/`quit`/`cancel`/
  `session` behavior, help for the existing flags, and every pre-existing test are byte-identical;
  `_start_fenced`'s default (`reject_busy=False`) keeps S3's supersede semantics for
  `start`/`toggle`/`start_with_seed`.
- (h) `timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_control_socket.py -q`
  green; `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q` shows no NEW failures vs
  `tests/G1_BASELINE.md` (CPU addendum); `git diff --name-only` == the five files.

## User Persona

**Target User**: the opt-in editor-integration user (§4.8.1) and the non-integrated script/adapter
author who wants a mid-paragraph continuation to decode lower-case and unpunctuated, without a
native editor adapter yet.

**Use Case**: An editor action (or a shell one-liner) pipes the newest pre-caret text into
`voicectl start-block --context-stdin`; the daemon confirms the seed on both decode lanes before
opening the mic; the user dictates; the first accepted final hands off to rolling context (S4).

**User Journey**:
1. User triggers Start in the editor → adapter snapshots ≤ 4 KiB of text before the caret → pipes it.
2. voicectl validates the flag pairing, reads stdin to EOF within 2 s (newest 4 KiB, code-point
   boundary), sends ONE `start-context` line.
3. Daemon: busy? → reject. Empty/disabled/unavailable? → plain fenced arm, unseeded + reason.
   Else → fenced seed arm: load (if cold) → confirmed prime → capture.
4. voicectl prints `listening: on` + `context: seeded` (exit 0), or the fixed error (exit 1).

**Pain Points Addressed**: a stale/old daemon silently arming without context; a seeded start
clobbering an in-flight arm or a live session; an unconfirmed prompt being reported as seeded;
seed text leaking into errors, logs, or status; a hung stdin producer hanging the keybind.

## Why

- **PRD mandate** (§4.8.1 A): "Preserve the context-only API for non-integrated callers … This is
  the existing focus-based delivery mode with a decode seed, **not** a safe editor integration.
  Reject while arming/listening/draining. Distinct commands ensure an old daemon rejects the
  request instead of silently arming without context. On timeout/old daemon, report the error; do
  not retry or fall back."
- **Downstream consumers**: P1.M1.T3.S1 (bounded control framing) and T10a CPU qualification need
  this route to exist; P1.M1.T3.S4 / P1.M1.T4.S7 build the native owner/lease as a *separate*
  command family on the same socket — this task must leave that layer untouched.
- **Gap today**: `ctl.py` has no context input; `ControlServer._dispatch` has no `start-context`;
  S3's seam *supersedes* an in-flight arm (right for keybind toggles, wrong for an explicit context
  start) and returns `context_seeded=True` even on a host without `prime_prompt`.

## What

- Daemon: `start_context(context, *, streaming, timeout) -> dict` — normalize (newest ≤ 4096 bytes
  UTF-8, code-point boundary, `strip()`), classify empty/disabled, call `_start_fenced(...,
  reject_busy=True)`, shape a sanitized reply. `_dispatch` validates `mode` ∈ {block, stream, absent}
  and `context` is a str/None (never `str()`-coerced; never echoed) before calling it.
- `_start_fenced(..., reject_busy=False)`: when True, the reserve block returns
  `ArmOutcome(False, False, "busy", None, None, self._arm_seq)` if `_arming is not None or
  _loading or _listening.is_set() or _drain` — before taking a reservation.
- CLI: `--context-stdin` valid only with `start`/`start-block`/`start-stream`; stdin read via a
  daemon pump thread joined with a monotonic deadline, keeping only the newest 4 KiB; wire cmd
  `start-context` with `{"context": ..., ["mode": ...]}`; loading-hint path; `format_result`
  branch; old-daemon and uncertain-outcome stderr lines.
- Docs [Mode A]: `ctl.py` module docstring / `--help` epilog / flag help describe the route, its
  exit codes, and that it is focus-based delivery (not an editor integration);
  `ControlServer` protocol docstring gains the `start-context` line + the focus-vs-native sentence.

### Success Criteria

- [ ] (a)–(h) under Success Definition hold, demonstrated by test output.
- [ ] `start_context` never raises; every reply is a dict with `ok`, `context_seeded`, and either
      `context_reason` or `error` (fixed codes only).
- [ ] No new daemon state; `_seed_active` is never written by this task; S4's hook is untouched.
- [ ] `_handle` (server read loop), `recorder_host.py`, `prompt_engine.py`, `cancel`, and every
      existing command's response shape are untouched.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs: the §4.8.1 A text (quoted in Why/What), the S3 seam's exact reserve
block and `ArmOutcome` shape (pinned from the S3 PRP — gate at Task 0), the current `ctl.py`
(`main` step order, `send_command`'s `extra` merge, `_send_command_with_loading_hint`,
`format_result` branch order, exit-code contract 0/1/2/64), `_dispatch`'s command blocks and
`_cmd_streaming`, the server's thread-per-connection `makefile` read (unbounded lines are fine for a
≤ 10 KiB frame), the three test files' idioms (`running_server`/`_StubDaemon` in test_voicectl,
`_disp`/`server` in test_control_socket, `_make_lazy_daemon`/`_PrimeableFakeHost`/`_wait_for` in
test_daemon), and the verbatim code + test matrix in the research note. An agent new to the repo can
implement from this PRP + the research note + the landed S3/S4 code.

### Documentation & References

```yaml
# MUST READ — the contract (quote is in this PRP's Why; read the full section once)
- docfile: PRD.md
  why: "§4.8.1 A 'Shared context and optional context-only CLI' (lines ~440-447): the wire shape,
        busy rejection, old-daemon/no-retry rule, context_seeded semantics + reason codes,
        ephemeral-seed rule. §4.8 (line ~432) for the exit-code contract; §4.10 for 'no bindings'."
  section: "##### A. Shared context and optional context-only CLI"
  critical: "READ-ONLY file. 'A context_seeded:true response requires a bounded acknowledgement from
            the child … a best-effort queue put is not confirmation' and 'If the child state is
            unknown, fail without arming' are the two sentences the daemon-side reply logic enforces."

# MUST READ — this task's design with verbatim code + the full test matrix
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S5/research/context_start_design.md
  why: "§2 the policy table (why each branch exists, incl. the S3 context_seeded=True-on-legacy-host
        hazard), the client outcome table, the worst-case frame size; §3 VERBATIM code for every
        edit in ctl.py and daemon.py (busy check, _normalize_context, start_context,
        _context_reply, _dispatch route, docstring lines, _read_context_stdin, _utf8_suffix,
        format_result branch, main() diff); §4 the test matrix per file."
  critical: "§3.2's busy check MUST sit inside S3's existing `with self._lock:` reserve block and
            return BEFORE the `try:` — no reservation, no finally interaction. §3.1's main() diff
            reuses the single `extra`/`wire_cmd` pair so `session --copy` keeps its own extra."

# INPUT CONTRACT (sequential dependency; assume landed exactly as specified)
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S3/PRP.md
  why: "Defines ArmOutcome(ok, listening, reason, context_seeded, tokens, arm_seq), _arm_seq/_arming/
        _seed_active, _start_fenced(seed, *, streaming, timeout) with the reserve→load→prime→
        revalidate→arm shape, start_with_seed(seed), reasons 'ok'|'seed-applied'|'seed-clear'|
        'seed-unconfirmed'|'prompt-unconfirmed'|'load-failed'|'aborted'|'superseded', and the
        _PrimeableFakeHost test fake."
  critical: "S3's seam SUPERSEDES an in-flight arm (newer reservation wins) and returns
            context_seeded=True whenever want_seed — even with no prime_prompt on the host. Both are
            corrected here (reject_busy; the 'unavailable' downgrade), NOT by editing S3's logic."
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S4/PRP.md
  why: "The one-line `self._seed_handoff_pending = True` beside `_seed_active = True` in
        _start_fenced; the seed is replaced at the first accepted final. This task relies on it and
        must not touch it."
  critical: "S4 reads ArmOutcome.context_seeded — S5's reply must report the DOWNGRADED truth
            (unavailable), while ArmOutcome itself stays as S3 produced it."

# EDIT SITES
- file: voice_typing/ctl.py
  why: "Whole file (512 lines) read. main() steps: parse → _ALIASES → _COMMANDS check (64) →
        --copy check (64) → _default_control_socket_path (2) → send (OSError→2, ValueError→1) →
        format_result → print. send_command(socket_path, cmd, extra=None) merges extra after 'cmd'.
        _send_command_with_loading_hint(socket_path, cmd) has NO extra param (add one).
        format_result order: ok:false → shutting_down → status → session → default 'listening:'."
  pattern: "Mirror the --copy check for --context-stdin (64 before anything else); mirror the
            session/copy extra handling for the context extra; keep stderr for hints, stdout for
            the structured result."
  gotcha: "Never read sys.stdin directly in tests — pytest's capture replaces it; pass BytesIO /
          fakes to _read_context_stdin(stream). main() uses getattr(sys.stdin, 'buffer', sys.stdin)."

- file: voice_typing/daemon.py
  why: "_cmd_streaming ~2956 (unchanged); ControlServer class docstring ~2974 ('Protocol (PRD
        §4.2(3)…)' block — add the start-context lines); _arm_response ~3131; _dispatch ~3148
        (toggle block → start block → stop → cancel → status → quit → session → unknown); the
        start/start-stream/start-block block is where the new route goes, right after it."
  pattern: "Follow the existing blocks: read msg.get(...) defensively, return a dict, never raise.
            Reuse S3's ArmOutcome positional order (ok, listening, reason, context_seeded, tokens,
            arm_seq). Log with logger.exception('start-context failed (not armed)') — no data."
  gotcha: "Per-connection handler threads block while the seam waits for load/prime — that is by
           design (thread per connection; status/stop stay responsive). Do not add a timeout to the
           server side; the client's VOICECTL_TIMEOUT is the bound."

- file: tests/test_voicectl.py
  why: "_StubDaemon ~194 (extend with start_context recording), running_server fixture,
        _server_for(stub, monkeypatch, tmp_path) ~387, exit-2 tests ~275-291 (monkeypatch of the
        socket-path resolver), test_start_prints_loading_hint_when_arm_is_slow ~396 (how the
        loading-hint path is driven)."
  pattern: "Pure format_result tests at top; main()-level tests monkeypatch ctl.send_command /
            ctl._send_command_with_loading_hint / ctl._default_control_socket_path and use capsys."
- file: tests/test_control_socket.py
  why: "_StubDaemon ~27 (calls list + start/toggle/stop/cancel/status_snapshot/session_reply),
        _disp(msg) ~122 (in-process _dispatch), _send/_send_lines ~71/89 + the `server` fixture
        for wire round-trips."
  pattern: "Add start_context(self, context, *, streaming=None) to _StubDaemon recording the call
            and returning a canned dict; assert passthrough + the two validation rejections."
- file: tests/test_daemon.py
  why: "_make_daemon ~903, _wait_for ~765, _PromptRecordingHost ~5028; S3's _PrimeableFakeHost /
        _PrimeResult / _primeable_factory (gate, raise, scripted results, prime_calls,
        recorder.mic) — confirm names at Task 0."
  pattern: "Drive d.start_context(...) on a _make_lazy_daemon(host_factory=_primeable_factory(...))
            daemon; assert on host.prime_calls, host.recorder.mic, d.is_listening(), the reply dict,
            and caplog at DEBUG."

# EXTERNAL — none required. Stdlib only (argparse, json, socket, threading, time). No new deps,
# no library docs to consult. The wire/CLI surface is fully specified by PRD §4.8.1 A.
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/ctl.py                 # ← EDIT: --context-stdin, _utf8_suffix, _read_context_stdin,
                                    #   extra pass-through, start-context format branch, main() wiring,
                                    #   help/epilog/module docstring.
voice_typing/daemon.py              # ← EDIT: _start_fenced(reject_busy=), _CONTEXT_MAX_BYTES,
                                    #   _normalize_context, start_context, _context_reply,
                                    #   _dispatch "start-context" route, ControlServer protocol docstring.
tests/test_voicectl.py              # ← EDIT: + "P1.M1.T2.S5 — context starts" section.
tests/test_control_socket.py        # ← EDIT: _StubDaemon.start_context + 3 dispatch tests.
tests/test_daemon.py                # ← EDIT: + "P1.M1.T2.S5 — context starts (policy/busy)" section.
voice_typing/recorder_host.py       # S2's — UNTOUCHED (prime_prompt consumed via S3's seam).
voice_typing/prompt_engine.py       # S1's — UNTOUCHED (fit happens in the child).
README.md                           # UNTOUCHED (P1.M2.T4.S1 refreshes it across the changeset).
```

### Desired Codebase tree with files to be changed

```bash
# (same five files; no new files, no new modules)
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — GATE ON S3/S4. They were NOT landed at research time (HEAD 55cf034 = S2). Task 0
# greps for `def _start_fenced`, `def start_with_seed`, `class ArmOutcome`, `self._seed_active = True`.
# Missing ⇒ STOP and report; do not re-implement S3 here.

# CRITICAL #2 — BUSY MUST BE ATOMIC WITH THE RESERVATION. A check in start_context BEFORE calling
# the seam has a check-then-act race with another arm's reserve. The check lives INSIDE S3's
# `with self._lock:` reserve block, returns before `try:`, so no _arming token is taken and S3's
# finally never runs. Default reject_busy=False keeps start/toggle/start_with_seed byte-identical.

# CRITICAL #3 — NEVER REPORT context_seeded:true WITHOUT THE CHANNEL. S3's seam returns
# context_seeded=True whenever want_seed, even if getattr(host, "prime_prompt", None) is not callable
# (legacy/fake hosts). _context_reply requires BOTH out.context_seeded is True AND a callable
# prime_prompt on self._host; otherwise context_seeded:false + context_reason:"unavailable".

# CRITICAL #4 — "UNAVAILABLE" IS *KNOWN* NO-CHANNEL; "UNCONFIRMED" IS *UNKNOWN*. Known no-channel
# (or config-disabled, or empty) ⇒ start UNSEEDED through the plain fenced arm and say why.
# Unknown (ArmOutcome ok=False: seed-unconfirmed / prompt-unconfirmed / load-failed) ⇒ ok:false,
# not armed. Never convert an unknown into "unavailable" and arm anyway.

# CRITICAL #5 — UNSEEDED BRANCHES STILL GO THROUGH THE SEED (plain). _start_fenced(None,
# reject_busy=True) is what guarantees "known clear or no prompt executor" after a previous seeded
# session (S3's confirmed clear / isolation). Do not bypass it with a bare start().

# CRITICAL #6 — THE SEED STRING GOES NOWHERE BUT prime_prompt. Not into reply keys, error text,
# log messages, status_snapshot, ArmOutcome (S3 already made it text-free), exceptions, or the
# client's stdout/stderr. Messages carry fixed codes; the stdin failure carries the exception TYPE
# name only. Tests assert a marker string's absence via json.dumps(reply) and caplog.text.

# CRITICAL #7 — SERVER RE-VALIDATES THE CLIENT. _normalize_context runs daemon-side on the wire
# value (any same-user process can hit the socket): newest ≤ 4096 BYTES, drop ≤ 3 leading
# continuation bytes (0x80..0xBF) after the cut, decode errors="replace", then .strip() for both
# emptiness and the value (an `echo` trailing newline must not reach the prompt; interior newlines
# stay). ctl._utf8_suffix is the same idea minus strip — deliberate duplication (ctl stays
# self-contained besides the socket-path resolver import).

# CRITICAL #8 — STDIN IS BOUNDED BY MEMORY AND TIME, AND UNCERTAIN ⇒ SEND NOTHING. Keep only the
# newest 4 KiB in a rolling suffix (a producer may write gigabytes; /tmp is RAM here). Pump in a
# daemon thread and join(deadline) — a pipe whose writer never closes must not hang the keybind;
# if the thread is still alive at the deadline, raise ValueError BEFORE the socket. Never sleep.
# Empty stdin is VALID ("" → unseeded/"empty"), not an error.

# CRITICAL #9 — ONE SEND, NO RETRY, NO FALLBACK. Old daemon ⇒ {"ok":false,"error":"unknown
# command: 'start-context'"} ⇒ exit 1 (+ stderr hint). Socket timeout / malformed reply ⇒ the
# daemon MAY still complete its fenced start ⇒ exit 1 + "outcome unknown — not retried". Never
# re-send, never downgrade to plain `start`, never fall back to typing a seed via argv/env.

# CRITICAL #10 — FLAG PAIRING IS 64, NOT 1. --context-stdin with toggle/toggle-*/stop/status/quit/
# cancel/session (or --copy together with it) is a usage error: print to stderr, return _EX_USAGE,
# and do NOT touch the socket. Mirror the existing --copy check.

# CRITICAL #11 — PASS wire_cmd ("start-context") TO format_result AND to the send. format_result's
# start-context branch sits after `session`, before the default; ok:false is handled by the first
# branch (error: ...). The loading hint applies (cold load ~1–3 s).

# CRITICAL #12 — _dispatch VALIDATES WITHOUT COERCION OR ECHO. mode ∉ {None,"block","stream"} ⇒
# ok:false with a fixed message (do not include the bad value); "context" absent or not str/None ⇒
# ok:false. Never str(msg["context"]) for dicts/numbers. The stub daemon in test_control_socket
# needs start_context (direct call style — no getattr guard — matching session_reply).

# GOTCHA #13 — FRAME SIZE. ensure_ascii JSON of 4 KiB UTF-8 is ≤ ~10 KiB (emoji ×10, CJK ×6). The
# server's makefile readline is unbounded today; T3.S1 will cap at 32 KiB. Do not raise
# _CONTEXT_MAX_BYTES.

# GOTCHA #14 — AGENTS.md: full paths + inner timeouts (timeout 300 … test_voicectl.py
# tests/test_control_socket.py; timeout 600 … test_daemon.py; bash tool timeout above them). No
# ruff/mypy. Hermetic fakes only — no real daemon, mic, CUDA, or systemd. test_daemon.py's legacy
# reds are classified in tests/G1_BASELINE.md: diff FAILED names against it; no NEW reds allowed.
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/daemon.py — module level (beside _cmd_streaming)
_CONTEXT_MAX_BYTES: int = 4096        # §4.8.1 A: newest <= 4 KiB of pre-caret text

def _normalize_context(text: object) -> str   # "" | newest <= 4 KiB UTF-8, code-point cut, .strip()

# VoiceTypingDaemon._start_fenced signature after this task:
def _start_fenced(self, seed: str | None, *, streaming: bool | None = None,
                  timeout: float = _START_DEADLINE_S, reject_busy: bool = False) -> ArmOutcome

# New public entry — returns a plain dict (sanitized), never raises:
def start_context(self, context: str | None, *, streaming: bool | None = None,
                  timeout: float = _START_DEADLINE_S) -> dict

# Reply shapes (the ONLY three):
{"ok": True,  "context_seeded": True,  "context_tokens": <int>,      **status_snapshot()}
{"ok": True,  "context_seeded": False, "context_reason": "empty"|"disabled"|"unavailable", **status_snapshot()}
{"ok": False, "listening": False, "context_seeded": False, "error": "<fixed text>"}

# voice_typing/ctl.py — module level
_CONTEXT_MAX_BYTES: int = 4096
_CONTEXT_CHUNK_BYTES: int = 65536
_STDIN_DEADLINE_S: float = 2.0
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE on S3/S4 + confirm names + baseline
  - RUN (cwd /home/dustin/projects/voice-typing):
      grep -n 'def _start_fenced\|def start_with_seed\|class ArmOutcome\|self._seed_active = True\|_seed_handoff_pending' voice_typing/daemon.py
      grep -n 'def prime_prompt' voice_typing/recorder_host.py
      grep -n 'asr.context_prompt\|self._drain\b' voice_typing/daemon.py | head -8        # config attr + drain flag spelling
      grep -n 'class _PrimeableFakeHost\|class _PrimeResult\|def _primeable_factory\|def _make_lazy_daemon' tests/test_daemon.py
      grep -n '"output_mode"\|output_mode' voice_typing/daemon.py | head -4                 # how mode is observed
      timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_control_socket.py -q 2>&1 | tail -1
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -1          # record the FAILED set vs G1_BASELINE
  - If _start_fenced / start_with_seed / ArmOutcome are MISSING: STOP — report "S3 not landed";
    this task cannot proceed (it is a thin layer over S3's seam).

Task 1: EDIT voice_typing/daemon.py — reject_busy in the fenced seam
  - ADD the `reject_busy: bool = False` keyword to _start_fenced's signature; inside the EXISTING
    `with self._lock:` reserve block, BEFORE `self._arm_seq += 1`, insert research §3.2's busy
    check returning ArmOutcome(False, False, "busy", None, None, self._arm_seq).
  - EXTEND the docstring by two sentences (Mode A): context starts reject instead of superseding;
    nothing is reserved on 'busy'.
  - Do NOT change any other line of the seam; start()/toggle()/start_with_seed() keep the default.

Task 2: EDIT voice_typing/daemon.py — _normalize_context + start_context + _context_reply
  - ADD `_CONTEXT_MAX_BYTES` and `_normalize_context` (research §3.2, verbatim).
  - ADD `start_context` and `_context_reply` directly BELOW `start_with_seed` (research §3.2,
    verbatim; the config attribute name per Task 0). Whole body in try/Exception → fixed
    "internal error" reply; logger.exception with no data.
  - Docstrings (Mode A) as given: focus-based delivery vs pinned native session; busy; the three
    unseeded reasons; confirmation requirement; ephemeral seed.

Task 3: EDIT voice_typing/daemon.py — _dispatch route + protocol docstring
  - INSERT the `if cmd == "start-context":` block (research §3.2) right AFTER the existing
    `if cmd in ("start", "start-stream", "start-block"):` block.
  - EXTEND the ControlServer class docstring's Protocol block with the start-context lines
    (research §3.2, verbatim).

Task 4: EDIT voice_typing/ctl.py — bounded stdin reader + helper + pass-through
  - ADD the three constants, `_utf8_suffix`, `_read_context_stdin` (research §3.1, verbatim).
  - ADD `extra: dict | None = None` to `_send_command_with_loading_hint` and forward it to
    send_command. Update its docstring's stale "makefile('r')" sentence while there (one line).

Task 5: EDIT voice_typing/ctl.py — parser, format_result, main()
  - ADD the `--context-stdin` argument and the epilog paragraph (research §3.1).
  - ADD the `start-context` branch to format_result after the `session` branch.
  - EDIT main() per research §3.1's diff: flag pairing (64) right after the --copy check; stdin
    read + wire_cmd/extra after socket-path resolution; send with extra; uncertain-outcome line;
    old-daemon hint; format_result(wire_cmd, response).
  - UPDATE the module docstring: subcommand list line for `--context-stdin`, the focus-vs-native
    sentence, and the new exit-1 outcomes.

Task 6: EDIT tests/test_voicectl.py — context-start section (research §4; write tests FIRST where
        practical, then make them pass)
  - Pure: _utf8_suffix boundary cases; format_result seeded/unseeded/unknown.
  - main()-level (monkeypatch send paths; capsys): pairing 64 with no send; deadline → 1 within
    bound, no send; unreadable stream → 1; wire (cmd, extra.mode) for the three commands; old-daemon
    hint; timeout "outcome unknown" with exactly one send; busy reply → 1; seed marker absent from
    stdout+stderr on every failure path; one real-server round trip via running_server/_server_for.

Task 7: EDIT tests/test_control_socket.py — _StubDaemon.start_context + 3 tests
  - routes with mode / default None; bad mode rejected without echo; missing/non-string context.

Task 8: EDIT tests/test_daemon.py — policy/busy section (research §4 list)
  - Requires S3's _PrimeableFakeHost. Cover: seeded confirm→capture (and no seed in reply/status/
    logs); block/stream mode; empty/whitespace; disabled; unavailable (plain _make_daemon host);
    busy while listening / arming (gated prime) / draining (set the drain flag under _lock, reset
    in finally); unconfirmed → not armed; newest-4 KiB normalization (ASCII + CJK); load failed;
    re-prime after a previous seeded session.

Task 9: VALIDATE (below); confirm `git diff --name-only` == the five files. No commit unless asked.
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — atomic busy rejection (inside S3's reserve block):
with self._lock:
    if reject_busy and (self._arming is not None or self._loading
                        or self._listening.is_set() or self._drain):
        return ArmOutcome(False, False, "busy", None, None, self._arm_seq)
    self._arm_seq += 1; tok = self._arm_seq; self._arming = tok

# PATTERN 2 — classify, then one seam call; truthfully downgrade:
seed = _normalize_context(context); reason = None
if not seed:                              seed, reason = None, "empty"
elif not <cfg>.asr.context_prompt:        seed, reason = None, "disabled"
out = self._start_fenced(seed, streaming=streaming, timeout=timeout, reject_busy=True)
confirmed = out.ok and out.context_seeded is True and callable(getattr(self._host, "prime_prompt", None))

# PATTERN 3 — bounded stdin (memory: rolling suffix; time: join(deadline); uncertain ⇒ raise):
tail = (tail + chunk)[-_CONTEXT_MAX_BYTES:]        # whatever the producer writes
t.join(deadline_s); if t.is_alive(): raise ValueError(<fixed message>)

# PATTERN 4 — one send, fixed outcomes:
wire_cmd, extra = "start-context", {"context": text, **({"mode": m} if m else {})}
response = _send_command_with_loading_hint(socket_path, wire_cmd, extra=extra)
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S3 (fenced seam; INPUT): _start_fenced / start_with_seed / ArmOutcome /
           _arming / _loading / _drain / _seed_active. This task adds ONE keyword and ONE early
           return inside the reserve block; everything else in the seam is untouched.
UPSTREAM — P1.M1.T2.S4 (handoff; INPUT): consumes ArmOutcome.context_seeded semantics; S5 does not
           write _seed_active or _seed_handoff_pending.
UPSTREAM — P1.M1.T2.S2 / S1: prime_prompt / PrimeResult (confirmed install, token/generation
           fence); fit of the seed to the model budget happens in the child — S5 only bounds bytes.
DOWNSTREAM — P1.M1.T3.S1 (bounded framing): the server read loop is untouched; start-context
           frames are ≤ ~10 KiB escaped — must fit its 32 KiB cap.
DOWNSTREAM — P1.M1.T3.S4 / P1.M1.T4.S7 (native owner/lease; native v1 on the same socket): a
           SEPARATE command family; they must preserve reject_busy inside the reserve block.
DOWNSTREAM — P1.M2.T3.S1 (T10a CPU qualification): uses this CLI/wire route.
CONFIG: none. ENV: none (VOICECTL_TIMEOUT applies as today). ROUTES: one control-socket cmd.
DOCS: Mode A only — ctl.py help/exit text + ControlServer protocol docstring. README untouched.
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic fakes only. Run from
> `/home/dustin/projects/voice-typing`. Navigate by symbol — S3/S4 shift lines.

### Level 1: Syntax & static shape

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -c "import ast; [ast.parse(open(f).read()) for f in ('voice_typing/daemon.py','voice_typing/ctl.py')]; print('L1 PASS: parses')"
grep -n 'reject_busy' voice_typing/daemon.py | head                  # keyword + busy check + start_context call
awk '/    def _start_fenced/,/^    def [a-z_]+\(/' voice_typing/daemon.py | grep -n '"busy"'   # exactly one, before the try
grep -n 'def start_context\|def _context_reply\|def _normalize_context\|_CONTEXT_MAX_BYTES' voice_typing/daemon.py
grep -n 'cmd == "start-context"' voice_typing/daemon.py               # exactly one
grep -n '_read_context_stdin\|_utf8_suffix\|--context-stdin\|"start-context"' voice_typing/ctl.py | head -12
# Expected: parses; one busy check inside the reserve block; one dispatch route; ctl has reader,
# helper, flag, wire cmd, format branch.
```

### Level 2: Unit tests — the deliverable

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_control_socket.py -q -k "context or utf8_suffix" -v 2>&1 | tail -30
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k "start_context" -v 2>&1 | tail -20
# Expected: all PASSED. Load-bearing: busy-while-listening shows NO new prime call and the session
# still listening; unavailable shows context_seeded False (not True) on a host without prime_prompt;
# deadline test returns 1 within the bound with zero sends; old-daemon + timeout paths send exactly
# once; the seed marker is absent from reply/status/caplog/stdout/stderr.
```

### Level 3: No regressions (ordinary commands byte-identical)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_control_socket.py -q 2>&1 | tail -2
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -2
# Diff the FAILED names against tests/G1_BASELINE.md (CPU addendum) — no NEW reds. A new red in an
# existing arm test means the default reject_busy path diverged (CRITICAL #2) — check that the busy
# check is gated by `reject_busy and` and sits before `self._arm_seq += 1`.
timeout 30 .venv/bin/voicectl --help | grep -n 'context-stdin'      # help shows the flag
timeout 10 .venv/bin/voicectl toggle --context-stdin; echo "exit=$?"   # expect usage error + exit 64, no socket I/O
# Expected: suites at baseline; help lists the flag; misuse exits 64.
```

### Level 4: Scope guards + hermetic end-to-end

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'voice_typing/daemon.py|voice_typing/ctl.py|tests/test_daemon.py|tests/test_voicectl.py|tests/test_control_socket.py' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS"
git diff --quiet voice_typing/recorder_host.py voice_typing/prompt_engine.py voice_typing/config.py README.md && echo "L4 PASS: siblings untouched" || echo "L4 FAIL: sibling edited"
git diff --exit-code -- PRD.md plan/009_ef3b49b0fc0d/tasks.json plan/009_ef3b49b0fc0d/prd_snapshot.md .gitignore && echo "L4 PASS: read-only unchanged" || echo "L4 NOTE: orchestrator bookkeeping"
git diff voice_typing/daemon.py | grep -E '^\+' | grep -vE '^\+\+\+' | grep -nE '_seed_active\s*=|_seed_handoff_pending\s*=|def _handle|makefile' && echo "L4 FAIL: touched S3/S4/T3 territory" || echo "L4 PASS: seam/S4/handle untouched"
# Expected: diff ⊆ five files; siblings + read-only untouched; no writes to S3/S4 state; _handle unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: parses; one `reject_busy` busy check inside the reserve block; one `start-context` route; ctl has reader/helper/flag/format branch.
- [ ] L2: all context-start tests pass in the three files.
- [ ] L3: no new failures vs the G1 baseline; `--help` shows the flag; misuse exits 64.
- [ ] L4: diff == five files; no sibling/read-only edits; no `_seed_active`/`_seed_handoff_pending`/`_handle` changes.

### Feature Validation
- [ ] Wire/CLI parity for `start`/`start-block`/`start-stream --context-stdin` (mode absent/block/stream).
- [ ] `context_seeded:true` only with a confirmed channel + applied prime; `empty`/`disabled`/`unavailable` start unseeded through the seam and say why.
- [ ] Busy rejected atomically while arming/listening/draining; in-flight arm and live session unaffected.
- [ ] Old daemon / timeout / stdin-not-at-EOF → exit 1 with the right stderr line; exactly one send (or none); never a plain-start fallback.
- [ ] Seed absent from replies, status, logs, stdout, stderr, exceptions.

### Code Quality Validation
- [ ] Mirrors existing `_dispatch` blocks and `main()` step order; 64/2/1 exit-code contract preserved.
- [ ] Mode A docstrings on `_start_fenced`, `start_context`, the ControlServer protocol, and ctl help.
- [ ] No new imports beyond stdlib already in use; no new daemon state; no sleeps in tests (bounded joins / Events).

### Scope Boundary Validation
- [ ] `recorder_host.py`, `prompt_engine.py`, `config.py`, `README.md` untouched; no argv/env seed; no editor detection; no native v1 commands.

### Documentation & Deployment
- [ ] ctl.py module docstring / `--help` / flag help describe the route, outcomes, and focus-vs-native distinction.
- [ ] ControlServer protocol docstring lists `start-context` with its three reply shapes.

---

## Anti-Patterns to Avoid

- ❌ Don't check busy in `start_context` before calling the seam (check-then-act race) — it belongs inside the reserve block under `_lock`.
- ❌ Don't change S3's default supersede semantics for `start`/`toggle`/`start_with_seed`.
- ❌ Don't report `context_seeded:true` because `ArmOutcome` said so — verify the channel; a best-effort put is not confirmation.
- ❌ Don't arm on an *unknown* prompt state, and don't fail a *known* no-channel/disabled/empty start — unknown ⇒ fail, known ⇒ unseeded with reason.
- ❌ Don't read the seed from argv or an env var; don't add a `voicectl start-context` subcommand; don't add automatic editor detection.
- ❌ Don't retry, re-send, or downgrade to a plain `start` on old daemon / timeout / uncertain stdin.
- ❌ Don't `read()` stdin unbounded or without a deadline; don't treat empty stdin as an error.
- ❌ Don't put the seed (or request fragments, or exception messages carrying data) into replies, logs, status, or stderr.
- ❌ Don't touch `_handle`'s read loop, `recorder_host.py`, `prompt_engine.py`, `_seed_active`, `_seed_handoff_pending`, or PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**7.5/10** for one-pass implementation success. The route is small and fully specified (verbatim
code for every edit, a named test per branch, the three reply shapes), and the client's exit-code
contract is preserved by construction. The −2.5 is the sequential dependency: S3 and S4 were still
in flight at research time, so three private spellings (the daemon's config attribute, the drain
flag, S3's `_PrimeableFakeHost` names) must be confirmed at Task 0, and S3's seam currently reports
`context_seeded=True` on hosts without `prime_prompt` — this PRP neutralizes that in the reply layer
(CRITICAL #3) rather than by editing S3, which depends on S3 landing exactly as its PRP specifies.

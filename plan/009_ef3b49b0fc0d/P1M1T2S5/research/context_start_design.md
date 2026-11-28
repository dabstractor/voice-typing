# P1.M1.T2.S5 — bounded focus-based context starts: design note

Researched at HEAD `55cf034` (S2 landed; S3/S4 in flight). Contract: PRD §4.8.1 A (quoted in the
PRP), `architecture/system_context.md`, the S3 PRP (`_start_fenced`, `start_with_seed`,
`ArmOutcome`) and the S4 PRP (`_seed_handoff_pending` hook beside `_seed_active = True`).

## 1. Site map (navigate by symbol — S3/S4 shift lines)

| File | Symbol | Role in this task |
|---|---|---|
| `voice_typing/ctl.py` | `_COMMANDS`, `_build_parser`, `main`, `format_result`, `send_command`, `_send_command_with_loading_hint` | add `--context-stdin`, the bounded stdin reader, the `start-context` wire route, help/exit text |
| `voice_typing/daemon.py` | `_cmd_streaming` (~2956) | unchanged: `-stream`/`-block` → `True`/`False`/`None` |
| `voice_typing/daemon.py` | `VoiceTypingDaemon._start_fenced` (S3), `start_with_seed` (S3) | add `reject_busy` keyword (default False); call from the new entry |
| `voice_typing/daemon.py` | `VoiceTypingDaemon.status_snapshot` (~2697), `_load_error` | reply fields + the load-failed error text |
| `voice_typing/daemon.py` | `ControlServer` class docstring (~2974) + `_dispatch` (~3148) | protocol doc line + the `start-context` route |
| `voice_typing/daemon.py` | `_handle` (makefile readline loop) | UNTOUCHED (framing bound is P1.M1.T3.S1) |
| `tests/test_voicectl.py` | `_StubDaemon` (~194), `running_server`, `_server_for` (~387) | CLI tests |
| `tests/test_control_socket.py` | `_StubDaemon` (~27), `_disp` (~122), `server` fixture | dispatch tests |
| `tests/test_daemon.py` | `_make_lazy_daemon`, `_PrimeableFakeHost` (S3), `_PromptRecordingHost`, `_wait_for` | policy/busy tests |

Task-0 checks whose exact spelling must be confirmed in the landed tree (they are S3/S4 names or
private fields this note could not read at HEAD): the daemon's config attribute (`cfg.asr.context_prompt`),
the drain flag (`self._drain`), `_PrimeableFakeHost` + `_PrimeResult`, and the status key that
reports the session output mode (`output_mode`).

## 2. Settled design

### 2.1 Wire + CLI surface (PRD §4.8.1 A, verbatim requirements)

- Wire: `{"cmd":"start-context","context":"<str>","mode":"block"|"stream"}` — `mode` optional
  (absent = config default). `context` REQUIRED, a string (or null); never `str()`-coced from other
  types. Distinct command ⇒ an old daemon answers `unknown command` instead of silently arming.
- CLI: `voicectl start | start-block | start-stream --context-stdin` — context from stdin, NEVER
  argv. Any other command + the flag ⇒ usage error 64 (nothing sent). No new subcommand.
- Delivery is the EXISTING focus-based keyboard path with a decode seed. It is NOT a pinned native
  editor session (§4.8.1 B; the native owner arrives with P1.M1.T3.S4 / P1.M1.T4.S7).

### 2.2 Daemon policy (why each branch exists)

`start-context` is a *focus start that must never silently become something else*:

| Situation | Result | Source of the rule |
|---|---|---|
| arming / listening / draining | `ok:false`, error `busy`; **no reservation, no prime, no mic** — atomic with the reservation | PRD "Reject while arming/listening/draining"; S3's default is *supersede*, which is wrong here |
| context empty / whitespace-only | unseeded plain fenced arm; `context_seeded:false`, `context_reason:"empty"` | PRD "Empty/whitespace-only is valid and unseeded" |
| `asr.context_prompt` off | unseeded plain fenced arm; `context_reason:"disabled"` | PRD reason code |
| non-empty + enabled | `start_with_seed(seed)`-equivalent fenced arm; `context_seeded:true` ONLY if the host exposes the confirmed channel (`prime_prompt`) | PRD "best-effort queue put is not confirmation" — S3's seam returns `context_seeded=True` even when the host lacks `prime_prompt` (its `seeded = True if want_seed`), so S5 must downgrade that case to `context_reason:"unavailable"` (unseeded; "or no prompt executor") |
| seed unconfirmable / prompt unknown / load failed / aborted | `ok:false`, `context_seeded:false`, fixed error text, not armed | PRD "If the child state is unknown, fail without arming" |

Unseeded branches go through `_start_fenced(None, reject_busy=True)`: S3's plain arm already
guarantees "known clear or no prompt executor" (confirmed clear after a seeded session, provably
None otherwise, isolation when unconfirmable). S5 adds no state and never writes `_seed_active`.

### 2.3 Seed normalization (both ends, deliberately duplicated)

The client bounds stdin for UX; the server bounds the wire value because any same-user process can
reach the socket. Newest ≤ 4096 **bytes** of UTF-8, leading continuation bytes (`0x80..0xBF`, ≤ 3)
dropped so the cut is on a code-point boundary; `.strip()` decides emptiness and is the seed value
(an `echo`-style trailing newline must not become part of the prompt; interior newlines survive).
Lone surrogates / invalid sequences become U+FFFD via `errors="replace"` — never an exception.

### 2.4 Client outcome table

| Outcome | Exit | Notes |
|---|---|---|
| flag on a non-start command / missing command | 64 | before anything else |
| daemon unreachable / XDG unset | 2 | unchanged |
| stdin unreadable, or EOF not reached within `_STDIN_DEADLINE_S` (2 s) | 1 | BEFORE the socket; nothing sent; message carries the exception TYPE only |
| `ok:true` | 0 | `listening: on` + `context: seeded` | `context: unseeded (<reason>)` |
| `ok:false` (busy / unconfirmed / load failed) | 1 | `error: <daemon text>` |
| `ok:false` + error starts with `unknown command` (old daemon) | 1 | extra stderr hint: daemon predates context starts; nothing armed |
| socket timeout / malformed reply (`ValueError` from `send_command`) | 1 | "outcome unknown — not retried; check voicectl status" |

Exactly one `send` per invocation on every path. No retry, no fallback to a plain `start`.

### 2.5 Worst-case frame size (for T3.S1's later 32 KiB cap)

`json.dumps` default `ensure_ascii=True`: 4096 bytes of 3-byte CJK = 1365 chars × 6 = ~8 KiB; of
4-byte emoji = 1024 × 10 = ~10 KiB. Do not raise `_CONTEXT_MAX_BYTES`.

## 3. Verbatim code

### 3.1 `voice_typing/ctl.py`

```python
# P1.M1.T2.S5 (§4.8.1 A): context-only starts read the pre-caret seed from STDIN (never argv).
# Bounded twice: memory (only the newest _CONTEXT_MAX_BYTES are retained whatever the producer
# writes) and time (monotonic _STDIN_DEADLINE_S to reach EOF — a producer that never closes its
# pipe is an UNCERTAIN input: fail before the socket, send nothing).
_CONTEXT_MAX_BYTES: int = 4096      # newest UTF-8 suffix, cut on a code-point boundary
_CONTEXT_CHUNK_BYTES: int = 65536   # per read; the rolling suffix keeps memory at <= 4 KiB + chunk
_STDIN_DEADLINE_S: float = 2.0      # monotonic budget for stdin to reach EOF


def _utf8_suffix(raw: bytes, max_bytes: int = _CONTEXT_MAX_BYTES) -> str:
    """Newest <= max_bytes of `raw` decoded as UTF-8, cut on a code-point boundary. Never raises."""
    if len(raw) > max_bytes:
        raw = raw[-max_bytes:]
        i = 0
        while i < 3 and i < len(raw) and 0x80 <= raw[i] <= 0xBF:   # drop a cut continuation byte
            i += 1
        raw = raw[i:]
    return raw.decode("utf-8", errors="replace")


def _read_context_stdin(
    stream: object, *, deadline_s: float = _STDIN_DEADLINE_S
) -> str:
    """Read `stream` (bytes) to EOF; return the newest <= 4 KiB as str ("" is valid → unseeded).

    Raises ValueError with a FIXED message (exception TYPE only, never stream content) when the
    stream cannot be read or EOF is not reached within `deadline_s`. The pump thread is a daemon:
    voicectl is one-shot, so a stuck producer cannot keep the process alive.
    """
    box: dict[str, object] = {}

    def _pump() -> None:
        try:
            tail = b""
            read = getattr(stream, "read", None)
            if not callable(read):
                raise TypeError("stdin is not readable")
            while True:
                chunk = read(_CONTEXT_CHUNK_BYTES)
                if not chunk:
                    break
                tail = (tail + chunk)[-_CONTEXT_MAX_BYTES:]
            box["tail"] = tail
        except Exception as exc:                      # OSError / TypeError / non-bytes
            box["error"] = type(exc).__name__

    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    t.join(deadline_s)
    if "error" in box:
        raise ValueError(f"context stdin could not be read ({box['error']})")
    if t.is_alive():
        raise ValueError(
            f"context stdin did not reach EOF within {deadline_s:.0f}s — "
            "pipe or redirect the seed text; nothing was sent"
        )
    return _utf8_suffix(box["tail"])  # type: ignore[arg-type]
```

`_send_command_with_loading_hint` gains a pass-through (backward compatible):

```python
def _send_command_with_loading_hint(
    socket_path: str, cmd: str, extra: dict | None = None
) -> dict:
    ...
    try:
        return send_command(socket_path, cmd, extra=extra)
    finally:
        timer.cancel()
```

`format_result` — new branch placed AFTER the `session` branch and BEFORE the default:

```python
    if cmd == "start-context":
        # P1.M1.T2.S5 (§4.8.1 A): focus-based start with a decode seed. Only fixed words below —
        # the seed never appears in any reply, error or this text.
        listening = "on" if response.get("listening") else "off"
        if response.get("context_seeded") is True:
            ctx = "seeded"
        else:
            ctx = f"unseeded ({response.get('context_reason') or 'unknown'})"
        return f"listening: {listening}\ncontext: {ctx}", 0
```

`_build_parser` — add the flag + epilog lines:

```python
    parser.add_argument(
        "--context-stdin",
        action="store_true",
        help="with start | start-block | start-stream: read the pre-caret seed (newest 4 KiB) "
        "from stdin — piped/redirected only, never argv — and arm FOCUS-based dictation with it",
    )
```

epilog addition:

```
"context starts (focus-based delivery — NOT a safe editor integration):\n"
"  start | start-block | start-stream --context-stdin   seed = newest 4 KiB read from stdin\n"
"  (piped/redirected stdin only). Reply 'context: seeded' means the recognizer child confirmed\n"
"  the seed on both decode lanes; 'context: unseeded (empty|disabled|unavailable)' starts without\n"
"  one. Rejected (exit 1) while arming/listening/draining, by an old daemon, or on timeout —\n"
"  never retried, never downgraded to a plain start.\n"
```

`main()` — the diff (flag validation BEFORE the socket; stdin read before the send; one send):

```python
    # after the --copy check:
    context_route = bool(args.context_stdin)
    if context_route and cmd not in ("start", "start-block", "start-stream"):
        print(
            "voicectl: --context-stdin applies only to start, start-block or start-stream",
            file=sys.stderr,
        )
        return _EX_USAGE
    # ... socket_path resolution unchanged (RuntimeError -> 2) ...
    extra = {"copy": True} if (cmd == "session" and args.copy) else None
    wire_cmd = cmd
    if context_route:
        try:   # P1.M1.T2.S5: bounded stdin read BEFORE any socket I/O
            text_in = _read_context_stdin(getattr(sys.stdin, "buffer", sys.stdin))
        except ValueError as exc:
            print(f"voicectl: {exc}", file=sys.stderr)
            return 1
        wire_cmd = "start-context"
        extra = {"context": text_in}
        if cmd == "start-block":
            extra["mode"] = "block"
        elif cmd == "start-stream":
            extra["mode"] = "stream"
    try:
        if wire_cmd in ("start", "toggle", "start-context") or wire_cmd.startswith(
            ("start-", "toggle-")
        ):
            response = _send_command_with_loading_hint(socket_path, wire_cmd, extra=extra)
        else:
            response = send_command(socket_path, wire_cmd, extra=extra)
    except OSError as exc:
        print(f"voicectl: daemon not running ({exc.strerror or exc})", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"voicectl: {exc}", file=sys.stderr)
        if context_route:
            # UNCERTAIN (timeout / malformed reply): the daemon may still complete its fenced
            # start — report, never retry, never fall back to a plain start (§4.8.1 A).
            print(
                "voicectl: context start outcome unknown — not retried; "
                "check 'voicectl status'",
                file=sys.stderr,
            )
        return 1
    text, code = format_result(wire_cmd, response)
    if (
        context_route
        and response.get("ok") is not True
        and str(response.get("error", "")).startswith("unknown command")
    ):
        print(
            "voicectl: this daemon predates context starts (start-context) — update "
            "voice-typing and restart the unit; nothing was armed",
            file=sys.stderr,
        )
```

Module docstring: add a `start | start-block | start-stream --context-stdin` line to the
subcommand list + the "focus-based delivery with a decode seed, not a safe editor integration"
sentence, and the exit-1 outcomes (busy / old daemon / timeout / stdin not at EOF).

### 3.2 `voice_typing/daemon.py`

Busy rejection INSIDE S3's reserve block (the only atomic place). Default False ⇒ S3 behavior
byte-identical for `start`/`toggle`/`start_with_seed`:

```python
    def _start_fenced(
        self,
        seed: str | None,
        *,
        streaming: bool | None = None,
        timeout: float = _START_DEADLINE_S,
        reject_busy: bool = False,          # P1.M1.T2.S5: context starts reject instead of superseding
    ) -> ArmOutcome:
        t0 = time.monotonic()
        with self._lock:
            if reject_busy and (
                self._arming is not None      # an arm is in flight (S3's reservation token)
                or self._loading              # a recorder load is in flight
                or self._listening.is_set()   # already armed
                or self._drain                # graceful drain in progress
            ):
                # No reservation is taken: the in-flight arm / live session is untouched.
                return ArmOutcome(False, False, "busy", None, None, self._arm_seq)
            self._arm_seq += 1
            tok = self._arm_seq
            self._arming = tok
        # ... rest of S3's seam unchanged ...
```

New module helper + entries (place `_normalize_context` beside `_cmd_streaming`; the methods
directly BELOW `start_with_seed`):

```python
_CONTEXT_MAX_BYTES: int = 4096   # §4.8.1 A: newest <= 4 KiB of pre-caret text (code-point boundary)


def _normalize_context(text: object) -> str:
    """Newest <= _CONTEXT_MAX_BYTES of `text`, UTF-8-safe, stripped; "" for anything non-str/empty.
    Deliberately duplicated with ctl._utf8_suffix: the server must not trust the client. Never raises."""
    if not isinstance(text, str) or not text:
        return ""
    raw = text.encode("utf-8", errors="replace")
    if len(raw) > _CONTEXT_MAX_BYTES:
        raw = raw[-_CONTEXT_MAX_BYTES:]
        i = 0
        while i < 3 and i < len(raw) and 0x80 <= raw[i] <= 0xBF:
            i += 1
        raw = raw[i:]
    return raw.decode("utf-8", errors="replace").strip()


# in VoiceTypingDaemon:
    def start_context(
        self,
        context: str | None,
        *,
        streaming: bool | None = None,
        timeout: float = _START_DEADLINE_S,
    ) -> dict:
        """§4.8.1 A context-only start for NON-integrated callers (P1.M1.T2.S5; Mode A docs).

        Arms the EXISTING focus-based delivery (keyboard injection into the focused window) with
        `context` as the first-utterance decode seed — this is NOT a pinned native editor session
        (§4.8.1 B). Rejected (error 'busy', nothing reserved or armed) while arming, listening or
        draining. Empty / whitespace-only, config-disabled, or unavailable prompting starts
        UNSEEDED through the plain fenced arm (which guarantees a known-clear prompt or no prompt
        executor) and says so via context_seeded:false + context_reason. A non-empty enabled seed
        captures only on the child's bounded acknowledgement (S2/S3); unknown ⇒ fail, not armed.
        Returns a sanitized dict (fixed codes, counts, status) — the seed never appears in it, in
        logs, or in status. Never raises.
        """
        try:
            seed = _normalize_context(context)
            unseeded_reason: str | None = None
            if not seed:
                seed, unseeded_reason = None, "empty"
            elif not self._cfg.asr.context_prompt:      # CONFIRM the daemon's config attribute at Task 0
                seed, unseeded_reason = None, "disabled"
            out = self._start_fenced(
                seed, streaming=streaming, timeout=timeout, reject_busy=True
            )
            return self._context_reply(out, unseeded_reason=unseeded_reason)
        except Exception:
            logger.exception("start-context failed (not armed)")   # no request data in the message
            return {"ok": False, "listening": False, "context_seeded": False,
                    "error": "start-context failed: internal error"}

    def _context_reply(self, out: ArmOutcome, *, unseeded_reason: str | None) -> dict:
        """Sanitized reply for start-context. Fixed error text per ArmOutcome.reason; no request data."""
        if not out.ok:
            errors = {
                "busy": "start-context rejected: busy (arming, listening or draining)",
                "seed-unconfirmed": "start-context failed: context seed unconfirmed (not armed)",
                "prompt-unconfirmed": "start-context failed: prompt state unknown (not armed)",
                "load-failed": f"model load failed: {self._load_error}",
                "aborted": "start-context aborted",
                "superseded": "start-context superseded",
            }
            error = errors.get(out.reason, f"start-context failed: {out.reason}")
            return {"ok": False, "listening": False, "context_seeded": False, "error": error}
        confirmed = out.context_seeded is True and callable(
            getattr(self._host, "prime_prompt", None)
        )
        if confirmed:      # a best-effort put is NOT confirmation (§4.8.1 A)
            reply = {"ok": True, "context_seeded": True}
            if out.tokens is not None:
                reply["context_tokens"] = out.tokens      # opaque count, never text
            return {**reply, **self.status_snapshot()}
        return {"ok": True, "context_seeded": False,
                "context_reason": unseeded_reason or "unavailable", **self.status_snapshot()}
```

`ControlServer._dispatch` — the route, placed after the `start`/`start-stream`/`start-block` block:

```python
        if cmd == "start-context":   # P1.M1.T2.S5 (§4.8.1 A): context-only FOCUS start
            mode_name = msg.get("mode")
            if mode_name is not None and mode_name not in ("block", "stream"):
                return {"ok": False, "listening": False, "context_seeded": False,
                        "error": "start-context rejected: mode must be 'block' or 'stream'"}
            if "context" not in msg or not isinstance(msg.get("context"), (str, type(None))):
                return {"ok": False, "listening": False, "context_seeded": False,
                        "error": "start-context rejected: 'context' must be a string"}
            streaming = None if mode_name is None else (mode_name == "stream")
            return self._daemon.start_context(msg["context"], streaming=streaming)
```

`ControlServer` class docstring — protocol lines (Mode A):

```
      {"cmd":"start-context","context":"...","mode":"block"|"stream"}
                                   -> §4.8.1 A context-only start (P1.M1.T2.S5): the EXISTING
                                      focus-based delivery (keyboard injection into the focused
                                      window) with a first-utterance decode seed — NOT a pinned
                                      native editor session (§4.8.1 B; the native v1 owner/lease is
                                      P1.M1.T3.S4 / P1.M1.T4.S7).
                                      {"ok":true,"context_seeded":true,"context_tokens":N,**status}
                                      | {"ok":true,"context_seeded":false,
                                         "context_reason":"empty"|"disabled"|"unavailable",**status}
                                      | {"ok":false,"listening":false,"context_seeded":false,"error":"..."}
                                      'busy' while arming/listening/draining; the seed is never echoed.
```

## 4. Test matrix

### tests/test_voicectl.py (append a "P1.M1.T2.S5 — context starts" section)

- `test_context_flag_on_non_start_commands_is_usage_error` — `toggle`, `status`, `stop` + flag → 64;
  `send_command` monkeypatched to raise AssertionError if called.
- `test_utf8_suffix_keeps_newest_4k_on_codepoint_boundary` — `"é" * 3000` (6000 bytes) → encoded
  length ≤ 4096, equal to the newest suffix, starts with "é"; `"😀" * 2000` likewise.
- `test_read_context_stdin_multiline_unicode_and_empty` — `io.BytesIO("a\nb\n日本語".encode())`
  round-trips; `io.BytesIO(b"")` → `""`.
- `test_read_context_stdin_deadline_is_uncertain_and_sends_nothing` — a stream whose `read` blocks
  on an `threading.Event` (never set); `ctl.main(["start-block", "--context-stdin"])` with
  `ctl._STDIN_DEADLINE_S` monkeypatched to 0.2 → returns 1 within < 2 s; `send_command` never
  called; the seed marker is absent from capsys output.
- `test_read_context_stdin_unreadable_stream_is_exit_1` — stream without `read` → 1, "TypeError".
- `test_context_start_wires_start_context_with_mode` — parametrize over the three commands:
  monkeypatch `ctl._send_command_with_loading_hint` to capture `(path, cmd, extra)` and return
  `{"ok": True, "listening": True, "context_seeded": True, "context_tokens": 7}` → `cmd ==
  "start-context"`, `extra["context"] == "hello"`, `extra.get("mode")` ∈ {None, "block", "stream"};
  stdout `listening: on\ncontext: seeded\n`; exit 0; exactly one send.
- `test_context_start_old_daemon_hint_exit_1` — reply `{"ok": False, "error": "unknown command:
  'start-context'"}` → 1; stderr contains "predates context starts"; one send.
- `test_context_start_timeout_is_uncertain_no_retry` — send raises `ValueError("daemon wedged…")`
  → 1; stderr contains "outcome unknown"; send called exactly once.
- `test_context_start_busy_reply_exit_1` — `{"ok": False, "listening": False, "context_seeded":
  False, "error": "start-context rejected: busy (arming, listening or draining)"}` → 1, `error:` line.
- `test_format_start_context_unseeded_reasons` — pure `format_result` for the three reasons and a
  missing one (`unseeded (unknown)`).
- `test_context_seed_never_in_output` — on every failure path above, the seed string is absent
  from captured stdout+stderr.
- `test_context_round_trip_over_real_server` — `running_server` idiom with `_StubDaemon` extended
  to answer `start-context`; `ctl.main(["start", "--context-stdin"])` with stdin = `BytesIO` → 0.

### tests/test_control_socket.py

- `test_dispatch_start_context_routes_with_mode` / `..._default_mode_passes_none` — stub records
  `(context, streaming)`; reply passes through untouched.
- `test_dispatch_start_context_rejects_bad_mode_without_echo` — mode `"Stream"` → `ok:false`;
  the bad value is absent from `json.dumps(reply)`; stub not called.
- `test_dispatch_start_context_rejects_missing_or_non_string_context` — absent / `123` / `{}`.

### tests/test_daemon.py (policy; needs S3's `_PrimeableFakeHost`)

- `test_start_context_seeded_confirms_then_captures` — `d.start_context("Hello world")` → `ok`,
  `context_seeded`, `context_tokens == 7`; `host.prime_calls[0][0] == "Hello world"`;
  `host.recorder.mic == [True]` (after the prime); `"Hello world"` absent from
  `json.dumps(reply)`, `json.dumps(d.status_snapshot())`, `caplog.text` (DEBUG).
- `test_start_context_block_and_stream_modes` — `mode` → the session's streaming flag (assert the
  same way the existing `start-block`/`start-stream` daemon tests do).
- `test_start_context_empty_and_whitespace_unseeded` — `""`, `"   \n"` → `context_reason ==
  "empty"`, `host.prime_calls == []`, listening.
- `test_start_context_disabled_by_config_unseeded` — `cfg.asr.context_prompt = False` →
  `"disabled"`, no prime call, listening.
- `test_start_context_unavailable_on_host_without_prime_channel` — plain `_make_daemon()` host →
  `ok`, `context_seeded is False`, `"unavailable"`, listening, no `_seed_active`-driven clear.
- `test_start_context_busy_while_listening` — `d.start()` then `d.start_context("x")` → `ok False`,
  `"busy"` in error, `prime_calls` unchanged, still listening, `d._arming is None`.
- `test_start_context_busy_while_arming` — gated `prime_prompt` on `start_with_seed("a")` in a
  thread; `start_context("b")` → busy; release the gate; the first arm completes as S3 specifies.
- `test_start_context_busy_while_draining` — set the drain flag directly (`d._drain = True`, under
  `_lock`) with listening set → busy; reset in `finally`.
- `test_start_context_unconfirmed_seed_not_armed` — scripted `unconfirmed` → `ok False`,
  `"unconfirmed"` in error, `host.recorder.mic == []`, `d.is_listening() is False`.
- `test_start_context_normalizes_newest_4k` — `"x" * 6000` → `prime_calls[0][0]` is the newest
  ≤ 4096 chars; CJK variant lands on a code-point boundary.
- `test_start_context_load_failed_reports_load_error` — `spawn_result = False` → `ok False`,
  error starts with `model load failed`.
- `test_start_context_after_seeded_session_reprimes` — seeded arm, stop, `start_context("new")`
  → `prime_calls[-1][0] == "new"` (S3 re-prime; no clear in between).

## 5. Boundaries

- IN scope: `voice_typing/ctl.py`, `voice_typing/daemon.py` (`_start_fenced` keyword, the two
  methods + helper, the dispatch route, the protocol docstring), the three test files.
- OUT of scope: `_handle` framing (T3.S1), native v1 commands/lease (T3.S4, T4.S7),
  `recorder_host.py`, `prompt_engine.py`, the S4 handoff, `cancel` semantics, README (P1.M2.T4.S1),
  any editor adapter, argv context, env-var context, automatic editor detection.

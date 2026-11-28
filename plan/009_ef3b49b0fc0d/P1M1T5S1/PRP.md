# PRP — P1.M1.T5.S1: Serve an owner-only capped recovery reply (`editor-recover`)

## Goal

**Feature Goal**: Add the PRD §4.8.1 C one-shot recovery read to the production `ControlServer`
(`voice_typing/daemon.py`): a client opens a **separate** connection to the existing owner-only
control socket and sends `{"cmd":"editor-recover"}` or `{"cmd":"editor-recover","id":"<UUIDv4>"}`; the
daemon answers ONE reply and nothing is replayed, re-inserted, copied, or written to any generic
output:
- `{"ok":true,"id":sid,"text":text,"truncated":bool,"possibly_applied":bool}` — text = the
  unacknowledged accepted finals in seq order, single-space joined (straight from
  `NativeRecoverySnapshot`); `truncated` = the store's flag OR the wire-cap clip;
- `{"ok":false,"error":"busy"}` — the id is the ACTIVE session;
- `{"ok":false,"error":"not_found"}` — no retained recovery (absent id, nothing ended, daemon restarted);
- `{"ok":false,"error":"invalid_request"}` — malformed shape (extra keys, non-UUIDv4 `id`).
Omitting `id` selects the LATEST ENDED session (never the active one). The reply is **non-consuming**
(a repeat read returns the same snapshot) and its **escaped JSON line is bounded separately at 7 MiB
including the newline** (NOT the 32 KiB live-frame limit), clipped UTF-8-safely keeping the start with
`truncated=true`. The read never touches `status`, `state.json`, `voicectl session`, feedback, the
typing backend, clipboard, or subprocesses, and never logs text.

**Deliverable** (1 source file with code, 2 doc-only touches, 1 new test file):
1. `voice_typing/daemon.py` — `MAX_RECOVERY_REPLY_BYTES`, pure `build_recovery_reply(snapshot) -> dict`,
   pure `select_native_recovery(store, session_id|None) -> tuple[str, dict]`-style selector, and a
   `ControlServer._dispatch` branch for `editor-recover` that returns the reply; the recovery reply is
   written through `editor_protocol.send_line_capped` (2 s whole-write cap) — never an uncapped write.
   [Mode A] docstrings on the three new symbols.
2. `voice_typing/editor_protocol.py` — **docs only**: module docstring gains a "Recovery reply
   (P1.M1.T5.S1)" block: request shape, reply shapes, selection order, the separate 7 MiB bound and
   why `encode_line` (32 KiB) does not apply, write cap, non-consuming semantics.
3. `voice_typing/session_recovery.py` — **docs only**: `NativeRecovery.recover()` / `active_id()` /
   `NativeRecoverySnapshot` docstrings state the wire selection + privacy rules (who may read: the
   owner socket only; busy/not_found derivation; last three fields never on the wire).
4. `tests/test_native_recover.py` — hermetic CPU-only: private temp socket + real `VoiceTypingDaemon`
   with a directly seeded `NativeRecovery`, plus direct unit tests of the pure builder/selector
   including high-escaping Unicode/control-character cases and the 7 MiB cap path.

**Success Definition**:
- (a) **Selection**: no id → latest ENDED snapshot; explicit ended id → that snapshot; active id →
  `busy`; unknown id / empty store → `not_found`; non-UUIDv4 id, extra key, non-object, wrong types →
  `invalid_request`. Precedence: shape (`invalid_request`) → `busy` → `not_found` → reply.
- (b) **Reply shape**: success has EXACTLY the keys `{ok, id, text, truncated, possibly_applied}`;
  failures are EXACTLY `{"ok": false, "error": <code>}` (`native_error_reply`). `text` byte-equals
  `snapshot.text`; `truncated` is `snapshot.truncated or wire_clipped`.
- (c) **7 MiB bound**: `len(json.dumps(reply, ensure_ascii=False).encode() + b"\n") <= 7<<20` for every
  reply, including a crafted snapshot whose minimal encoding exceeds the cap (then `text` is a prefix of
  the original at a UTF-8 codepoint boundary and `truncated` is true). The builder always terminates.
- (d) **Bounded write**: the reply line is written with `send_line_capped` (2 s); a client that stops
  reading never blocks the connection thread beyond the cap; the daemon logs one codes-only line.
- (e) **No side effects**: repeat request → identical reply; nothing armed/disarmed; no backend call
  (tripwire), no `subprocess` (patched to raise), no clipboard/evdev; `status`, `state.json`,
  feedback, `voicectl session` unchanged; `caplog` contains neither the context nor the recovery text.
- (f) **Isolation from generic frames**: a plain `voicectl status` on the same connection before/after
  still gets its ordinary reply (one reply per line); an `editor-recover` FIRST frame does NOT make the
  connection a native owner (S7's first-frame rule keys on `editor-start` only).
- (g) `git diff --name-only` == `{voice_typing/daemon.py, voice_typing/editor_protocol.py,
  voice_typing/session_recovery.py, tests/test_native_recover.py}`; the two protocol/store diffs are
  docstrings only.
- (h) `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no` FAILED set ==
  G1 CPU addendum; `test_control_socket.py`, `test_editor_protocol*.py`, `test_native_recovery.py`,
  `test_native_teardown.py`, `test_native_socket.py` (S7, landed) green.

## User Persona

**Target User**: the dictation user whose native editor session ended with unconfirmed words (target
lost, ACK timeout, editor crash) — reached via `voicectl recover [ID]` (P1.M1.T5.S2) and, later, the
editor adapters (P1.M2.T1/T2) that show "Unconfirmed text: voicectl recover <id>".
**Use Case**: after an `ended{target_lost, recoverable:true}` the user runs the recovery command; the
CLI opens a fresh connection, sends `editor-recover`, prints the text to stdout, warns on stderr when
`truncated` / `possibly_applied` (an edit may already have landed — never auto-replay).
**User Journey**: editor dies → daemon ends session + retains unacknowledged finals → status hint
names the id → `voicectl recover <id>` → one reply → user pastes/proofreads manually.
**Pain Points Addressed**: today the retained snapshot is unreachable from the wire (S6 handoff:
"`voicectl recover` — T5.S1/S2"); a lost ACK cannot be inspected without it.

## Why

- PRD §4.8.1 C (PRD.md:475) specifies the request/reply verbatim and the separate 7 MiB escaped bound.
- system_context.md L26/L28: separate the 32 KiB live framing from "the exceptional recovery reply";
  "limit *serialized* response to 7 MiB, including escaping and framing"; "one-shot explicit read …
  non-consuming … entirely separate from `voicectl session [--copy]`. Never automatically replay."
- Chain already landed: T4.S1 `NativeRecovery` (leaf store, frozen snapshots, `active_id()`),
  T3.S1 `FrameReader` (32 KiB bound), T4.S7 (parallel; lands first) the routed v1 owner endpoint.
  S6's `NativeEndState` docstring hands this item its exact rule ("no new API").
- Scope: this item is the WIRE reply only. `voicectl recover` printing/exit codes are **P1.M1.T5.S2**.

## What

### Success Criteria
- [ ] `editor-recover` handled in `ControlServer._dispatch` (generic path) with the four outcomes and
      the precedence in (a); request validation in the daemon (no `_REQUEST_SPECS` change).
- [ ] `build_recovery_reply` enforces the 7 MiB line bound, UTF-8-safe start-preserving clip, terminates.
- [ ] The reply is written via `send_line_capped`; no other write path changes.
- [ ] (b)–(h) hold; [Mode A] docs in `editor_protocol.py` and `session_recovery.py`.
- [ ] **Not in scope**: `ctl.py` / `voicectl recover` (T5.S2); adapters (P1.M2.T1/T2); the owner
      connection/`_NativeSession` loop (S7); `editor_session.py`; `recorder_host.py`; `feedback.py`;
      config; README (P1.M2.T4.S1); any `_REQUEST_SPECS`/`validate_request` code change.

## All Needed Context

### Context Completeness Check

_Pass._ The request/reply grammar, selection order and precedence, the 7 MiB rule and why it is
defence-in-depth (6× worst-case escape × 1 MiB store), the exact store API and snapshot fields, the
existing codec helpers to reuse (`native_error_reply`, `send_line_capped`, `is_uuid_v4`,
`truncate_utf8_suffix`) and the one NOT to reuse (`encode_line` — 32 KiB), the S7 interaction (generic
path, first-frame rule, concurrent edit of `_handle`/`_dispatch`), the test harness to copy, and the
T5.S2 handoff are all below with line anchors.

### Documentation & References

```yaml
- docfile: plan/009_ef3b49b0fc0d/P1M1T5S1/research/editor_recover_reply.md
  why: "§0 contract quotes; §1 every input with line anchors (store API, S6 handoff, codec helpers,
        _dispatch/_handle, why _REQUEST_SPECS is untouched); §2 the six design decisions (validation in
        the daemon, selection order, cap algorithm + worst-case 6× ratio + 'test via crafted snapshot',
        capped write, privacy, failure shape) + the T5.S2 mapping; §3 harness facts."
  critical: "§2.3 — the 7 MiB cap is UNREACHABLE through the default store (≤ ~6.01 MiB escaped); the
            cap path must be unit-tested by calling the pure builder with a crafted snapshot. §2.4 —
            never sendall the reply uncapped."

- file: voice_typing/daemon.py
  why: "THE module edited. native_end_hint :295; NativeEndState docstring :~316-345 (S6 HANDOFF →
        this item: active_id()==id → busy; recover → None → not_found; else 5-key reply from the
        snapshot; 'Use state.hint only for hints, never for the reply'); self._native_recovery = 
        session_recovery.NativeRecovery() :1215; ControlServer :4567; _handle :4714 (FrameReader +
        makefile writer, no write deadline); _dispatch :4798 (returns dict; busy shape at :~28-38:
        {'ok': False, 'busy': True, 'error': 'busy: …'} for GENERIC arms — the native error shape is
        native_error_reply(code), use THAT); _default_control_socket_path :595 (0700 dir / 0600 sock)."
  pattern: "Pure helpers as module-level functions near native_end_hint (docstring → 'P1.M1.T5.S1
            (pure)'); the branch in _dispatch returns the dict; the capped write in _handle keyed on
            the request cmd. Anchor by SYMBOL — S7 lands concurrently and shifts lines."
  gotcha: "S7 edits _handle/_dispatch too. It lands BEFORE this item starts: Task 0 re-reads both at the
           new HEAD and places the recovery write so it does not disturb the editor-start handoff or
           the BUG-005 one-reply-per-line contract."

- file: voice_typing/session_recovery.py
  why: "NativeRecoverySnapshot :289 (session_id, text, truncated, possibly_applied, final_count,
        end_reason, ended_monotonic — 'the 1:1 source of T5.S1's {ok, id, text, truncated,
        possibly_applied} reply'); NativeRecovery :304; retain_final :334; end_session :409 (empty
        endings are DISCARDED → never noticable via recover); recover :428 (None → latest ENDED, never
        active; active id → live snapshot); active_id :448; counts :454; clear :463; _fit_text :66
        (UTF-8-safe clip keeping START — reuse). DOCS ONLY here."
  pattern: "recover()/active_id()/snapshot docstrings gain a 'WIRE (P1.M1.T5.S1)' paragraph."
  gotcha: "The store NEVER raises for bad input and never logs; keep the wire layer equally silent on
           content. Do not add a 'consume' flag — the read is non-consuming by contract."

- file: voice_typing/editor_protocol.py
  why: "native_error_reply :165 ({'ok':False,'error':code}); is_uuid_v4 :170; truncate_utf8_suffix :204
        (codepoint-aligned suffix clip, default 4 KiB — call with an explicit byte budget); ProtocolError
        :156; send_line_capped(conn, line, cap_s=WRITE_CAP_S) :472 (whole-line 2 s cap);
        write_reject :518; encode_line :98 (32 KiB — NOT for the recovery reply); _REQUEST_SPECS :259
        (no editor-recover; pinned by tests/test_editor_protocol_vectors.py). DOCS ONLY here."
  pattern: "Module docstring: add a 'Recovery reply (P1.M1.T5.S1)' block after the frame-limit text."
  gotcha: "Adding 'editor-recover' to _REQUEST_SPECS would change validate_request semantics for every
           client and the shared vectors — out of scope. Validate in the daemon."

- docfile: PRD.md
  why: ":475 §4.8.1 C — the request/reply verbatim, not_found/busy, 7 MiB escaped+newline bound,
        'never auto-inserts', 'No durable recovery promised after daemon restart'; :448-472 §4.8.1 B —
        socket is owner-only; error reply shape {'ok':false,'error':'<code>'}."
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "L26/L28 — separate the 32 KiB framing from the exceptional recovery reply; 7 MiB serialized
        limit; one-shot, non-consuming, separate from voicectl session; never replay."
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S7/PRP.md
  why: "CONTRACT (lands first): first-frame rule keys ONLY on cmd=='editor-start'; every other first
        frame stays generic (one reply per line); _dispatch(line)->dict signature is preserved; the
        native owner path is disjoint from the generic loop."
- file: tests/test_control_socket.py
  why: "Pattern to copy: ControlServer on a mkdtemp socket path (short /tmp path), client with
        settimeout, send line / recv line, EXIT-trap cleanup."
- file: tests/test_native_teardown.py
  why: "`import test_daemon as td` (:39); FakeClock/ManualTimers (:50/:61); _NoBackend tripwire
        (:80); _make() (:124) builds a real hermetic VoiceTypingDaemon. Copy the tripwire + make idiom."
- file: tests/test_native_recovery.py
  why: "17 store tests — the seeding idiom (retain_final/end_session/recover) and the high-escaping
        fixtures already used for the 1 MiB cap."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py             # ControlServer :4567; _handle :4714; _dispatch :4798; native_end_hint :295   ← CODE + DOCS
voice_typing/editor_protocol.py    # codec/validators/pump (T3)                                                            ← DOCS ONLY
voice_typing/session_recovery.py   # NativeRecovery (T4.S1)                                                               ← DOCS ONLY
voice_typing/ctl.py                # `session` path :310; status hint :290-308 ("voicectl recover <sid>")          READ ONLY (T5.S2 edits)
tests/test_control_socket.py       # temp-socket pattern                                                                  KEEP GREEN
tests/test_native_recovery.py      # store tests + escaping fixtures                                                     KEEP GREEN
tests/test_native_socket.py        # S7 (landing now)                                                                     KEEP GREEN
tests/test_native_recover.py                                                                                             ← CREATE
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py
  + MAX_RECOVERY_REPLY_BYTES: int = 7 << 20          # §4.8.1 C: escaped JSON line INCLUDING newline (code constant)
  + def build_recovery_reply(snapshot, *, max_bytes=MAX_RECOVERY_REPLY_BYTES) -> dict
        # {ok, id, text, truncated, possibly_applied}; clips text (start-preserving, codepoint-safe) and sets
        # truncated=True until the encoded line fits; deterministic; terminates (≤64 iterations).
  + def select_native_recovery(store, session_id: str | None) -> tuple[str, object]
        # ("invalid_request", None) handled by the caller's shape check; here: ("busy", None) when
        #  store.active_id() == session_id; ("not_found", None) when store.recover(id) is None;
        #  else ("ok", snapshot). Pure w.r.t. the store's public API; no I/O, no logs.
  ~ ControlServer._dispatch   + `if cmd == "editor-recover": return self._recover_reply(msg)`
  + ControlServer._recover_reply(msg) -> dict     # shape check → select → build; one codes-only log line
  ~ ControlServer._handle     + write the recovery reply via send_line_capped(conn, line) (2 s), then continue
voice_typing/editor_protocol.py    ~ module docstring: "Recovery reply (P1.M1.T5.S1)" block                          ← DOCS ONLY
voice_typing/session_recovery.py   ~ recover()/active_id()/NativeRecoverySnapshot docstrings: WIRE selection/privacy ← DOCS ONLY
tests/test_native_recover.py       — pure builder/selector unit tests + private-socket wire tests
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT USE encode_line() FOR THE RECOVERY REPLY. It is bounded by MAX_FRAME_BYTES
# (32 KiB incl. newline) for live frames. The recovery reply has its OWN bound (7 MiB) and must be
# encoded with json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n" inside build_recovery_reply.
# CRITICAL #2 — THE 7 MiB CAP IS UNREACHABLE THROUGH THE DEFAULT STORE. Worst-case escaping is 6×
# (a 1-byte control char becomes the 6-byte \u00XX sequence); the store caps text at 1 MiB UTF-8, so
# the largest possible default reply is ~6.01 MiB < 7 MiB. The cap is defence-in-depth (the store cap
# is injectable). THEREFORE the cap path is unit-tested by calling build_recovery_reply with a CRAFTED
# NativeRecoverySnapshot (frozen dataclass — construct directly) whose minimal encoding exceeds 7 MiB.
# Do not "test" it via the default store (it cannot get there) and do not lower the constant to force it.
# CRITICAL #3 — NEVER sendall() THE REPLY UN CAPPED. _handle's generic writer has no deadline; a 6 MiB
# line to a client that stopped reading would wedge the connection thread (the AGENTS.md hang class).
# Write with editor_protocol.send_line_capped(conn, line) (whole-line 2 s). On timeout/error: log ONE
# debug line (code + byte count) and move on; the daemon owes that client nothing further.
# CRITICAL #4 — S7 LANDS FIRST AND EDITS _handle/_dispatch. Anchor by symbol at the new HEAD. Do NOT
# restructure _handle; add the smallest branch that routes ONLY the editor-recover reply to the capped
# writer and leaves (i) the editor-start first-frame handoff, (ii) the BUG-005 one-reply-per-line
# contract, (iii) every ordinary command byte-identical.
# CRITICAL #5 — FIRST-FRAME RULE: `editor-recover` as a first frame does NOT become an owner. S7 keys
# the handoff on cmd == "editor-start" only. Add a test that an editor-recover-first connection then
# answers an ordinary `status` (still generic).
# CRITICAL #6 — SELECTION ORDER IS THE CONTRACT: shape → busy → not_found → reply. busy is decided by
# store.active_id() == id (NOT by recover(), which returns a live snapshot for the active id).
# omitted id → store.recover(None) → LATEST ENDED only (an active session is never returned).
# CRITICAL #7 — FAILURE SHAPE = native_error_reply(code) = {"ok": false, "error": code} — exactly two
# keys, NO "busy": True flag (that flag belongs to the generic arm replies in _dispatch; T5.S2 keys on
# error == "busy"). Success = exactly five keys; never add final_count/end_reason/ended_monotonic.
# CRITICAL #8 — SHAPE CHECK IN THE DAEMON: msg must be a dict; keys ⊆ {"cmd","id"}; if "id" present it
# must be a str satisfying editor_protocol.is_uuid_v4. Anything else → invalid_request. The generic
# _dispatch already turns malformed JSON / non-object into its own errors before the branch.
# CRITICAL #9 — PRIVACY: one log line per request with code, id, encoded byte length, truncated,
# possibly_applied — NEVER text, NEVER the context. status/state.json/feedback/`session` untouched.
# Patch subprocess.run/Popen to raise in the test module (no notify, no wtype, no clipboard).
# CRITICAL #10 — NON-CONSUMING. Never call clear(), never remove finals, never settle. A second
# request returns an equal reply. Daemon exit (existing clear()) is the only erasure.
# CRITICAL #11 — CLIP ALGORITHM MUST TERMINATE AND STAY UTF-8-SAFE. Loop: encode → fits? done;
# else text = _fit_text(text, max(utf8_len(text) // 2, 0)), truncated = True, iterations += 1,
# assert iterations < 64. _fit_text keeps the START (codepoint boundary). An empty text still encodes
# (ok=true, text="", truncated=true) — allowed only on the cap path.
# CRITICAL #12 — NO CODE CHANGE IN editor_protocol.py / session_recovery.py (docstrings only:
# `git diff -w` shows comment/docstring lines only). Do NOT touch ctl.py (T5.S2), editor_session.py,
# recorder_host.py, feedback.py, config*, README, plan files, PRD.md, tasks.json.
# CRITICAL #13 — AGENTS.M1 discipline: every command under `timeout`; bash-tool timeout above it;
# .venv/bin/python (zsh aliases shadow python3); test_daemon.py = `timeout 500 … --tb=no`, bash ≥ 560;
# never run the live daemon/voicectl; mkdtemp socket dirs under /tmp with an EXIT trap, short paths.
# CRITICAL #14 — The connection is NOT closed by the daemon after the reply (the client owns its
# one-shot close). Document that the daemon owes no further frames and that adapters/CLI should close.
```

## Implementation Blueprint

### Data models and structure

```python
MAX_RECOVERY_REPLY_BYTES: int = 7 << 20   # §4.8.1 C — escaped JSON line INCLUDING '\n' (code constant, NOT config)
_RECOVER_KEYS = frozenset({"cmd", "id"})

def _encode_reply_line(reply: dict) -> bytes:            # the recovery reply's OWN encoding (not encode_line)
    return (json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8")

def build_recovery_reply(snapshot, *, max_bytes: int = MAX_RECOVERY_REPLY_BYTES) -> dict:
    """P1.M1.T5.S1 (pure): the §4.8.1 C recovery reply from a NativeRecoverySnapshot — EXACTLY
    {ok, id, text, truncated, possibly_applied}. The encoded line (escaped JSON + '\\n') is bounded
    at max_bytes: while it does not fit, clip `text` UTF-8-safely keeping its START (session_recovery
    ._fit_text) and force truncated=True. Deterministic; terminates (each pass at least halves text)."""
    reply = {"ok": True, "id": snapshot.session_id, "text": snapshot.text,
             "truncated": bool(snapshot.truncated), "possibly_applied": bool(snapshot.possibly_applied)}
    for _ in range(64):
        if len(_encode_reply_line(reply)) <= max_bytes:
            return reply
        text = reply["text"]
        reply["text"] = session_recovery._fit_text(text, len(text.encode("utf-8")) // 2)
        reply["truncated"] = True
    raise AssertionError("recovery reply did not converge")   # unreachable: 1 MiB halves to 0 in ≤21 passes

def select_native_recovery(store, session_id: str | None) -> tuple[str, "session_recovery.NativeRecoverySnapshot | None"]:
    """P1.M1.T5.S1 (pure w.r.t. the store API; no I/O, no logs): ("busy", None) when
    store.active_id() == session_id; ("not_found", None) when store.recover(session_id) is None;
    else ("ok", snapshot). Omitted id → the store's LATEST ENDED (never the active session)."""
    if session_id is not None and store.active_id() == session_id:
        return "busy", None
    snapshot = store.recover(session_id)
    return ("ok", snapshot) if snapshot is not None else ("not_found", None)
```

### Implementation Tasks (ordered — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT (read-only; S7 MUST have landed — else STOP and report):
  git log --oneline -1; git status --short | head
  grep -nE "def (_handle|_dispatch|send_line_capped|encode_line|native_error_reply|is_uuid_v4|_fit_text)\b|^class ControlServer|_native_recovery = " voice_typing/daemon.py voice_typing/editor_protocol.py voice_typing/session_recovery.py
  grep -nE "editor-start|editor-recover" voice_typing/daemon.py | head          # S7 handoff present; NO editor-recover yet
  sed -n '<_handle>p' voice_typing/daemon.py                                    # new shape: where/how replies are written
  grep -nE "editor-recover" tests/test_editor_protocol_vectors.py voice_typing/editor_protocol.py   # expect nothing
  sed -n '1,70p' tests/test_control_socket.py;  sed -n '36,150p' tests/test_native_teardown.py  # harness to copy
  grep -nE "x01|\\\\u|escape|1 << 20|max_session_bytes" tests/test_native_recovery.py | head    # escaping fixtures
  timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_native_recovery.py tests/test_native_socket.py -q   # green BEFORE
  timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40     # baseline (bash ≥ 560)

Task 1: CREATE tests/test_native_recover.py (RED first). CPU-only; ONE private mkdtemp socket (prefix
  "vt-rc-", EXIT trap); `import test_daemon as td`; `d = td._make_daemon(...)` with the tripwire backend;
  patch subprocess.run/Popen to raise for the module; ControlServer(d, socket_path=…, accept_timeout=0.05).
  Helper `ask(sock_path, obj) -> dict` (connect, send one line, recv until newline — the reader must
  accept lines > 32 KiB: recv-loop until b"\n", settimeout(5)). Seed the store DIRECTLY:
  SID = a UUIDv4; d._native_recovery.retain_final(SID, 1, "alpha"); retain_final(SID, 2, "beta");
  d._native_recovery.mark_offer_attempted(SID, 1); end_session(SID, "target_lost").
  UNIT (pure, no socket):
   u1 build: five keys exactly; text == snapshot.text ("alpha beta"); flags mirror the snapshot.
   u2 escaping is lossless: text with '"', '\\', '\n', '\x00', '\x1f', 'é', '中', '\u2028' round-trips
      through json.loads(_encode_reply_line(...)).
   u3 CAP: crafted snapshot text = ("\x01" * (2 << 20)) (minimal JSON > 7 MiB: 6 B per char) →
      reply fits (len(line) <= 7<<20), truncated is True, text is a prefix of the original, decodes
      strictly, len(text) > 0; a snapshot with truncated=True and short text keeps truncated=True.
   u4 cap does not fire near the boundary: text of ("\x01" * (1 << 20)) (≈6.01 MiB) → text unchanged.
   u5 select: active id → ("busy", None); latest ended when id None; explicit ended id; unknown id →
      not_found; empty store → not_found.
  WIRE (private socket, real ControlServer):
   w1 no id → {"ok":true,"id":SID,"text":"alpha beta","truncated":false,"possibly_applied":true}; repeat → identical.
   w2 explicit id → same; unknown UUIDv4 → {"ok":false,"error":"not_found"} (2 keys).
   w3 active id (retain_final(SID2,1,"x") WITHOUT end_session) → busy; omitted id → the ENDED session (never SID2).
   w4 invalid shapes (parametrized): id "abc", id 5, extra key, id "" → {"ok":false,"error":"invalid_request"}.
   w5 big reply: ended session whose text ≈ 600 KiB of '"\\' → reply arrives whole on the socket.
   w6 stalled reader: client sends the request and never reads; the connection thread must finish the
      write attempt ≤ ~3 s (send_line_capped) and the server keeps serving a second client (status ok).
   w7 generic isolation: on ONE connection send {"cmd":"status"} then editor-recover then status → three
      ordinary replies in order; a connection whose FIRST frame is editor-recover is not an owner
      (status still generic; d._native is None).
   w8 privacy/no-side-effects on every wire case: backend 0 calls, subprocess 0, caplog has neither
      "alpha"/"beta" nor any recovery text, d.status_snapshot() unchanged before/after, store counts unchanged.
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_recover.py -q   → RED (bash 360)

Task 2: EDIT voice_typing/daemon.py — code (anchor by symbol):
  - add MAX_RECOVERY_REPLY_BYTES, _encode_reply_line, build_recovery_reply, select_native_recovery
    next to native_end_hint (module level, before the daemon class). [Mode A] docstrings as above.
  - ControlServer._recover_reply(self, msg) -> dict:
        if not isinstance(msg, dict) or not set(msg) <= _RECOVER_KEYS: return native_error_reply("invalid_request")
        sid = msg.get("id")
        if sid is not None and not (isinstance(sid, str) and is_uuid_v4(sid)): return native_error_reply("invalid_request")
        code, snap = select_native_recovery(self._daemon._native_recovery, sid)
        if code != "ok":
            logger.info("native recover: %s id=%s", code, sid or "latest"); return native_error_reply(code)
        reply = build_recovery_reply(snap)
        logger.info("native recover: ok id=%s bytes=%d truncated=%s possibly_applied=%s",
                    snap.session_id, len(_encode_reply_line(reply)), reply["truncated"], reply["possibly_applied"])
        self._last_recovery_reply = reply          # (or return a marker — see Task 0's _handle shape)
        return reply
  - _dispatch: `if cmd == "editor-recover": return self._recover_reply(msg)` — placed BEFORE any arm branch.
  - _handle: after dispatch, when the request's cmd == "editor-recover": write with
        send_line_capped(conn, _encode_reply_line(reply)) inside try/except (log debug, code only) and
        continue the loop — the ONLY change to the write path. Keep the editor-start handoff and every
        ordinary reply exactly as S7 left them.
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_recover.py -q → GREEN (bash 360)

Task 3: DOCS ONLY — voice_typing/editor_protocol.py (module docstring block "Recovery reply
  (P1.M1.T5.S1)": request shapes; the four replies; selection order; why MAX_FRAME_BYTES/encode_line do
  not apply and MAX_RECOVERY_REPLY_BYTES = 7 MiB incl. newline does; whole-write 2 s cap; non-consuming;
  close after reading) and voice_typing/session_recovery.py (recover/active_id/snapshot docstrings:
  WIRE selection + privacy — owner socket only, busy/not_found derivation, diagnostics never on the wire).
  RUN: timeout 120 .venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/editor_protocol.py voice_typing/session_recovery.py tests/test_native_recover.py && echo L1 PASS
       git diff -w --stat voice_typing/editor_protocol.py voice_typing/session_recovery.py   # docs-only review

Task 4: FULL GATES (Level 2/3) + `git diff --name-only` == the four files.
  HANDOFF → P1.M1.T5.S2 (voicectl recover): send {"cmd":"editor-recover"} / {"cmd":"editor-recover","id":ID} on a
  fresh connection; ok → print `text` exactly to stdout, stderr warnings when `truncated` / `possibly_applied`;
  error not_found → exit 1 "nothing to recover"; busy → exit 1 "session still active"; invalid_request → usage.
  Adapters (P1.M2): after reading the reply, close the connection; never auto-insert.
```

### Implementation Patterns & Key Details

```python
# PATTERN — the read is a pure function of an immutable snapshot; the only "logic" on the wire is selection.
code, snap = select_native_recovery(self._daemon._native_recovery, sid)   # busy / not_found / ok
reply = build_recovery_reply(snap) if code == "ok" else native_error_reply(code)
send_line_capped(conn, _encode_reply_line(reply))                        # bounded whole write (2 s)

# GOTCHA — a 600 KiB reply does not fit one recv(); the test client loops until b"\n" (and so must T5.S2,
# which already reads via sock.makefile — confirm it has no 32 KiB assumption; that is T5.S2's check, not ours).
```

```yaml
INTEGRATION POINTS:
  SOCKET:  none new — existing $XDG_RUNTIME_DIR/voice-typing/control.sock (0700 dir / 0600 socket, owner-only)
  CONFIG:  none (7 MiB, 2 s, key set = code constants)
  CODEC:   none — _REQUEST_SPECS/_EVENT_SPECS/validate_request/validate_event unchanged; shared vectors unchanged
  GENERIC: _dispatch gains one branch; _handle gains one capped-write branch; everything else byte-identical
  STORE:   no new API (S6 handoff) — read-only use of recover()/active_id()
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 120 .venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/editor_protocol.py voice_typing/session_recovery.py tests/test_native_recover.py && echo "L1 PASS"
# docs-only proof for the two touched protocol/store files:
git diff -w --stat voice_typing/editor_protocol.py voice_typing/session_recovery.py   # review: docstring lines only
# ruff/mypy only if pyproject configures them (Task 0) — else "not configured — skipped"
```

### Level 2: Unit Tests

```bash
timeout 300 .venv/bin/python -m pytest tests/test_native_recover.py -q                                     # bash 360
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_editor_protocol.py \
   tests/test_editor_protocol_vectors.py tests/test_editor_pump.py tests/test_native_recovery.py \
   tests/test_native_teardown.py tests/test_native_socket.py tests/test_voicectl_session.py -q   # bash 360
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40                     # bash ≥ 560; set-diff vs G1
# Expected: all green; test_daemon FAILED set == tests/G1_BASELINE.md CPU addendum
```

### Level 3: Integration (production boundary, no live daemon)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_native_recover.py -q -k "wire or big or stalled or isolation" -v   # bash 360
pgrep -af "voice-typing-daemon" || echo "no daemon touched"; ls /tmp | grep -c "^vt-rc-" || true   # 0 leftovers
# Expected: big reply arrives whole; stalled reader released within the write cap; no leftovers.
```

### Level 4: Creative & Domain-Specific

```bash
timeout 120 .venv/bin/python - <<'EOF'
import json
from voice_typing import daemon as dm
from voice_typing.session_recovery import NativeRecoverySnapshot as S
sid = "123e4567-e89b-42d3-a456-426614174000"
big = S(sid, "\x01" * (2 << 20), False, True, 1, "target_lost", 0.0)
r = dm.build_recovery_reply(big); line = (json.dumps(r, ensure_ascii=False) + "\n").encode()
print("fits", len(line) <= dm.MAX_RECOVERY_REPLY_BYTES, "truncated", r["truncated"], "keys", sorted(r))
small = S(sid, "\x01" * (1 << 20), False, False, 1, "stopped", 0.0)
r2 = dm.build_recovery_reply(small); print("untouched", r2["text"] == small.text, r2["truncated"])
EOF
# Expected: fits True truncated True keys ['id','ok','possibly_applied','text','truncated']; untouched True False
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 pass; `tests/test_native_recover.py` green; test_daemon FAILED set == G1 CPU addendum; S2–S7 suites green
- [ ] `git diff --name-only` == the four files; `editor_protocol.py` / `session_recovery.py` diffs are docstrings only
- [ ] No `_REQUEST_SPECS`/`validate_request`/`ctl.py`/config change

### Feature Validation
- [ ] (a) selection + precedence; (b) exact key sets; (c) 7 MiB bound incl. newline, start-preserving clip, terminates
- [ ] (d) capped write; (e) non-consuming, no output/side effects/logs-with-text; (f) generic isolation, first-frame rule intact
- [ ] Handoff to T5.S2 written in the completion message (reply shapes + error-code → exit mapping)

### Code Quality / Documentation
- [ ] Pure helpers module-level near `native_end_hint`, duck-typed store access via `self._daemon._native_recovery` (guard with `getattr` for stub daemons → `not_found`)
- [ ] [Mode A] docs: three new symbols; `editor_protocol.py` recovery block; `session_recovery.py` wire selection/privacy
- [ ] Logs codes/ids/byte counts only; no new env vars; no README change

## Anti-Patterns to Avoid

- ❌ Using `encode_line()` (32 KiB) for the recovery reply, or raising the 32 KiB live-frame limit
- ❌ An uncapped `sendall`/`wfile.write` of a multi-MiB reply on the connection thread
- ❌ Letting `recover()` decide `busy` (it returns a live snapshot for the active id) — check `active_id()` first
- ❌ Adding `busy: True` flags, `final_count`, `end_reason`, or any sixth key to the reply
- ❌ Adding `editor-recover` to `_REQUEST_SPECS` / changing `validate_request` (shared vectors; TS/Lua parity)
- ❌ Consuming, clearing, settling, replaying, copying, or typing the recovered text; logging it; putting it in `status`/`state.json`/`session`
- ❌ Restructuring `_handle`/`_dispatch` beyond the two small branches (S7 owns the handoff; BUG-005 owns one-reply-per-line)
- ❌ Lowering the 7 MiB constant or inflating the store cap to "make the cap testable" through the default store — test the builder with a crafted snapshot
- ❌ Editing `ctl.py` (T5.S2), adapters (P1.M2), README (P1.M2.T4.S1), or any read-only/plan file; running the live daemon/voicectl

---

## Confidence Score

**9/10**. The contract is verbatim in PRD.md:475 and S6's handoff, the store API and snapshot fields are
exactly the reply's source, the pure builder/selector are fully specified with a proven-terminating clip
loop, the non-obvious points are pinned as gotchas (32 KiB vs 7 MiB encoders, `active_id()` for `busy`,
native_error_reply shape, capped write, cap reachable only via a crafted snapshot, S7's concurrent edit of
`_handle`/`_dispatch`). The −1 is the S7 interaction: the exact `_handle` write shape is unknown until S7
lands, so Task 0 re-anchors by symbol and the write branch is prescribed by intent (smallest change, capped
writer only for this reply) rather than by line — plus the T5.S2 client reader needing to accept lines
beyond 32 KiB, which is handed off explicitly.

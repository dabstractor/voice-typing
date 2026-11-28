# Research — P1.M1.T5.S1: owner-only capped one-shot `editor-recover` reply

## §0 — Contract (PRD §4.8.1 C, PRD.md:475; architecture/system_context.md L26/L28)
- `{"cmd":"editor-recover","id":"..."}` on a SEPARATE one-shot connection →
  `{"ok":true,"id":sid,"text":text,"truncated":bool,"possibly_applied":bool}` for a retained id;
  omitting id selects the LATEST ENDED. Text = unacknowledged accepted finals in seq order joined by a
  single space. `not_found` if absent, `busy` for the ACTIVE id. Escaped JSON reply bounded separately at
  **7 MiB including the newline**. Non-consuming (a second read returns the same snapshot). No replay,
  no generic output, no copy. Separate from `voicectl session [--copy]` (R.6 path, ctl.py:310).
- system_context L26: "Separate a 32 KiB byte-bounded strict UTF-8 reader/live writer from the
  exceptional recovery reply" — i.e. the reply is NOT subject to MAX_FRAME_BYTES (32 KiB); it has its own cap.

## §1 — Inputs that exist at HEAD (verified)
- `session_recovery.NativeRecovery` (T4.S1, :304): `recover(id|None) -> NativeRecoverySnapshot|None`
  (:428; None → latest ENDED, never active; active id → live snapshot), `active_id()` (:448),
  `clear()` (:463). Snapshot fields (:289): `session_id, text, truncated, possibly_applied, final_count,
  end_reason, ended_monotonic` — the last three are diagnostics, NEVER on the wire (its own docstring says
  it is "the 1:1 source of T5.S1's {ok, id, text, truncated, possibly_applied} reply").
- S6 handoff (daemon.py NativeEndState docstring, ~:329-345): "P1.M1.T5.S1 (owner-only capped recovery
  reply): no new API — active_id() == id → busy; recover(id or None) → None → not_found; else
  {ok, id, text, truncated, possibly_applied} from NativeRecoverySnapshot (≤ 1 MiB escaped). Daemon exit
  clears the store. Use state.hint only for hints, never for the reply."
- `daemon._native_recovery` created in `__init__` (:1215), daemon-wide. `editor_protocol`: `encode_line`
  (:98, ensure_ascii=False + "\n", raises/limits at 32 KiB — NOT usable for a >32 KiB reply),
  `send_line_capped(conn, line, cap_s=WRITE_CAP_S=2.0)` (:472), `write_reject` (:518),
  `native_error_reply(code)` → `{"ok":False,"error":code}` (:165), `is_uuid_v4` (:170),
  `truncate_utf8_suffix` (:204), `ProtocolError(code, detail)` (:156). `session_recovery._fit_text`
  (:66) is UTF-8-safe clipping keeping the START. `_REQUEST_SPECS` (:259) does NOT contain
  `editor-recover`; `validate_request` would reject it ("unknown native command") — pinned by
  tests/test_editor_protocol_vectors.py (TS/Lua must match). S7's first-frame detection keys ONLY on
  `cmd == "editor-start"`, so an `editor-recover` first frame falls through to the generic
  `_dispatch` path (one reply per line) — exactly the "separate one-shot connection" semantics.
- `ControlServer._dispatch(line)` (daemon.py:4798) returns a dict; `_handle` (:4714) writes it.
  S7 (parallel, lands FIRST) edits `_handle`/`_dispatch`; re-anchor by symbol at the new HEAD.

## §2 — Design decisions
1. **Request validation lives in the daemon** (`_dispatch` branch), NOT in `_REQUEST_SPECS` — keeps
   `editor_protocol.py` docs-only for this item and the shared vectors untouched. Rules: unknown extra
   keys → `invalid_request`; `id` optional; when present must satisfy `is_uuid_v4` else `invalid_request`.
2. **Selection order**: `active_id() == id` → `busy` (even if non-empty); `recover(id or None)` → None →
   `not_found`; else build reply. `id` omitted never returns the active session (store guarantee).
3. **Cap** `MAX_RECOVERY_REPLY_BYTES = 7 << 20` (daemon.py code constant, NOT config) on the FULL encoded
   line including "\n", escaped. Builder: encode `json.dumps(reply, ensure_ascii=False)`; while over cap:
   clip `text` with `_fit_text(text, max(len_bytes(text)//2, 0))` keeping start, force `truncated=True`,
   re-encode; bound the loop (≤ 64 iterations; 1 MiB → 0 in ≤ 21 halvings). Deterministic.
   Worst-case escape ratio is 6× (1-byte control chars → `\u0001`), so with the default 1 MiB store cap
   the escaped reply is ≤ ~6.01 MiB — under 7 MiB. The cap is DEFENCE-IN-DEPTH (the store cap is
   injectable via `NativeRecovery(max_session_bytes=…)`); therefore the cap path is unit-tested by calling
   the pure builder with a crafted snapshot, not through the default store.
4. **Write**: the reply may be megabytes; `_handle`'s generic write has no deadline. Write the recovery
   reply with `send_line_capped(conn, line)` (2 s whole-write cap) and then return — never an uncapped
   sendall on the control-socket thread (AGENTS.md wedge class). `send_line_capped` raises/returns on
   timeout; swallow as a debug line (codes only). The connection is NOT force-closed by the daemon
   (client owns the one-shot close), but nothing else is owed to it.
5. **Privacy**: text flows only to the requesting socket (0600, same owner). Logs: one line with
   code + id + byte count + flags — never text. `status`, `state.json`, `voicectl session`, feedback
   untouched. No clipboard/subprocess/typing backend.
6. **Success reply has NO "error" key; failure replies are `native_error_reply(code)`** (S2 shape,
   same as refusals) — T5.S2 maps: ok → print text (stderr warnings on truncated/possibly_applied),
   not_found → exit 1, busy → exit 1 with "still active", invalid_request → usage error.

## §3 — Test harness facts
- `tests/test_control_socket.py`: ControlServer on a `mkdtemp` socket with a stub daemon — copy the
  pattern (short /tmp path, sun_path 108 B, EXIT trap cleanup).
- `tests/test_native_teardown.py:39-150`: `import test_daemon as td`, FakeClock/ManualTimers, `_make()`,
  `_NoBackend` tripwire; `td._make_daemon(...)` builds a REAL VoiceTypingDaemon (hermetic, CPU).
  Seeding the store directly (`d._native_recovery.retain_final(sid, seq, text)` then
  `end_session(sid, "target_lost")`) needs no host — the store is a leaf (tests/test_native_recovery.py).
- `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no` baseline per tests/G1_BASELINE.md.

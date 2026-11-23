# Research — P1.M5.T1.S2: daemon-side cooperating-editor TargetAdapter

## 1. Verified sources read this session
- `voice_typing/bulk_delivery.py` (234 L) — `DeliveryTarget` Protocol (acquire/show/finalize/leave/cancel),
  `ShowResult` (applied|unchanged|refused|unknown), `AcquireResult(ok,handle,revision,reason)`,
  `TargetUnits` (UTF16_UNITS exists), `map_span(text,start,end,UTF16_UNITS)` (surrogate-pair aware,
  original string only), `rendered_equal` (whitespace-only fold; never case/punct).
- `voice_typing/ime/target.py` (385 L) — ImeTarget: THE structural template (module docstring = Mode A
  R.3 contract; units class-attr; FieldBinding frozen dataclass; `last_reason` machine-readable
  refusal taxonomy; `_last_applied_span` + byte accounting advanced ONLY on applied;
  `_owned_utterance`/`_closed_utterances` bookkeeping; zero-diff guard FIRST (no request);
  revision-regression guard; insert-vs-correction branch; `recheck()` never mutates; None-reply →
  UNKNOWN "never retried by the caller"; finalize settles ownership; leave clears binding FIRST,
  best-effort, idempotent; cancel: nothing-pending → UNCHANGED with NO request, uncertain → REFUSED).
- `voice_typing/bulk_controller.py` (875 L, surface) — BulkController `__init__(target, on_stopped,
  op_deadline=0.25 …)`: **the controller IS the receiver and owns the 250 ms deadline; the adapter is
  never trusted to self-timeout**; stop reasons "queue-overflow"|"op-deadline"|"refused"|…;
  `halt_for_takeover(reason)`; single-worker runner. Failure-complete per P1.M3.T2.S2 — DO NOT modify.
- `voice_typing/ime/takeover.py` (272 L, surface) — TakeoverDetector.feed(ev)→reason|None (policy),
  TakeoverWatch: exactly ONE leave + ONE halt + ONE reason per watch (latched), logs carry
  counts/times/reasons only, never recognition text.
- `voice_typing/ime/manager.py` — ImeProcess: request(cmd,timeout,**fields)->dict|None; reader thread
  `_read_loop`/`_dispatch` splits id-echoed replies (resolve pending) from id-less events (callback).
- `voice_typing/ime/protocol.py` — encode/decode JSONL + make_reply/make_event + validate_request.
- `tests/test_ime_target.py` (943 L, surface) — `_FakeProc` duck with scripted `request()` returns;
  `_RaisingProc`; branch-pinned refusal tests. THE test pattern to mirror (no real sockets needed).
- `tests/test_control_socket.py` (from earlier plan rounds) — real in-process AF_UNIX JSONL server on
  tmp_path + `_wait_for` poll helper: the socket-level test pattern.
- S1 PRP (plan/008_a47116bb2b79/P1M5T1S1/PRP.md) — the socket contract (below). S1 in flight:
  no `.pi/extensions/`, no `pi_seam_proof.md` yet — consume as CONTRACT, not as existing code.

## 2. The S1 socket contract (from its PRP; stable v1)
- Path `$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock`, AF_UNIX SOCK_STREAM, JSONL, one line in → one line out.
- Ops: `{"op":"insert","text"}` (at caret, atomic-undo); `{"op":"replace","start","end","text"}` (ONE
  atomic range replacement, **UTF-16 offsets**); `{"op":"cancel"}` (remove owned range in ONE op);
  `{"op":"read"}` → `{text, cursor:{row,col}, owned:{start,end}|null, dirty:bool, units:"utf-16"}`.
- Replies: `{"ok":true,"result":"applied"|"unchanged"|"refused","cursor":…,"changes":N}` (refused adds
  `reason`), errors `{"ok":false,"error":…}`. **NO id echo** — strictly one request in flight.
- Events (unsolicited, id-less): `{"event":"takeover","source":"key"}` — fired once per owned fragment
  on a delegated REAL keystroke; our own writes never emit it. dirty flips true.
- Extension-side ownership: owned=[start,end) UTF-16 it wrote since last boundary; replace refused when
  range not within owned / dirty / out_of_bounds.

## 3. Key design decisions for the S2 adapter
- Module `voice_typing/pi_editor.py`, class `PiEditorTarget` (mirrors ImeTarget) + `PiEditorClient`
  transport duck (`request(op, timeout, **fields)->dict|None`, `on_event` callback / `start_events()`).
  Split like ime: client (socket+reader thread) / target (DeliveryTarget) in ONE module — small enough.
- units = `TargetUnits.UTF16_UNITS`; ALL char→offset math via `bulk_delivery.map_span` (astral 🫡 = 2 units).
- Refusal taxonomy (acquire, fail-before-delivery): "pi socket absent" (ENOENT — no pi/extension),
  "pi socket no reply", "editor dirty", "editor owns fragment" (stale owned), "read missing fields",
  "inconsistent owned range". Password/selection: NO signal in protocol v1 → documented limitation
  (mirrors ImeTarget's honest password gap).
- show(): zero-diff FIRST (rendered_equal, no request); extension of `_last_applied_span` → insert delta;
  else replace over [owned_start, owned_start+utf16len(owned)] with the full span; reply None/timeout →
  UNKNOWN (never retry — controller disarms); `{"ok":false}` → REFUSED with reason.
- Cancel semantics: `{"op":"cancel"}` ONE op; nothing pending → UNCHANGED, no request (G2 trace_07 pin).
- Takeover mapping: event → ONE `halt_for_takeover("pi-editor key takeover")` via a TakeoverWatch-style
  latch (exactly one halt/leave/reason per watch). Daemon wiring is P1.M6.T2.S1 — NOT this item.
- The controller owns the 250 ms deadline; the adapter uses short socket timeouts (~0.25 s reads) and
  honest UNKNOWN on expiry.

## 4. Scope fences (from the task tree)
- Consumes: S1 socket (contract above), BulkController (failure-complete — read-only), bulk_delivery.
- Produces: `voice_typing/pi_editor.py` + `tests/test_pi_editor.py` (+ this research). Mode A docstring.
- Does NOT touch: daemon.py (M6.T2 wiring), bulk_controller.py, `.pi/**` (S1's), tests/ime_*/G3 labs
  (M4.T5 done; M5.T2 owns the pi-prompt G3 row that will USE this adapter).
- Parallel-safe with S1 (in flight): S1 writes `.pi/extensions/*`, `tests/pi_seam_*`,
  `architecture/pi_seam_proof.md` — zero overlap with this item's files.

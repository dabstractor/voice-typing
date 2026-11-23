# voice-editor.ts — pi prompt-editor control socket (Mode A)

P1.M5.T1.S1. This extension wraps pi's prompt editor with a `CustomEditor`
subclass and serves an AF_UNIX JSONL control socket so the voice-typing daemon
(P1.M5.T1.S2 `TargetAdapter`) can place and revise dictated text in the real
prompt with **zero synthesized keystrokes** (buffer-API edits only).

## Socket

- Path: `$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock` (falls back to
  `os.tmpdir()/voice-typing/pi-editor.sock` when `XDG_RUNTIME_DIR` is unset).
- Transport: AF_UNIX SOCK_STREAM, **JSONL framing** — one JSON object per line
  in, exactly one JSON line out per request (events are the exception; see
  below). UTF-8 encoded.
- Created on `session_start` (interactive UI only); stale files are unlinked
  before bind; file mode `0600`.
- **One pi per runtime dir**: the path is fixed, so a second interactive pi in
  the same `XDG_RUNTIME_DIR` steals the file (its startup unlinks and rebinds).
  Clients must treat connection loss as "reconnect" (see Lifecycle).

## Units — READ THIS BEFORE WRITING A CLIENT

All offsets and lengths (`start`, `end`, `owned.{start,end}`, cursor columns)
are **UTF-16 code units** of the editor's `getText()` string — JavaScript
string indices, not bytes and not grapheme clusters. Every `read` reply
carries `"units":"utf-16"`. Emoji outside the BMP count as **2** units.

## Requests (client → server)

```jsonc
{"op":"insert","text":"…"}                      // insert at caret; atomic for undo
{"op":"replace","start":12,"end":18,"text":"…"} // ONE atomic range replacement (UTF-16 units)
{"op":"cancel"}                                 // remove the owned range in ONE op
{"op":"read"}                                   // full state (see reply below)
```

## Replies (server → client, one per request)

Results mirror `voice_typing.bulk_delivery.ShowResult`:
`applied | unchanged | refused`. (`unknown` is reserved for the adapter's
deadline layer — socket ops are synchronous on pi's loop and never `unknown`.)

```jsonc
{"ok":true,"result":"applied","cursor":{"line":0,"col":5},"changes":1}
{"ok":true,"result":"unchanged","cursor":{"line":0,"col":5},"changes":0}   // zero-diff → ZERO events (R.1)
{"ok":true,"result":"refused","reason":"range not owned|dirty|out_of_bounds","cursor":{…},"changes":0}
{"ok":true,"result":"applied","text":"…","cursor":{"line":n,"col":n},"owned":{"start":s,"end":e}|null,
 "dirty":false,"units":"utf-16","changes":n}                               // read
{"ok":false,"error":"malformed JSON: …|request must be a JSON object|unknown op: …|editor not ready|…"}
```

- `cursor` is `{line, col}` — **the editor's own cursor shape** (`line` is the
  row index, `col` the UTF-16 column within that line). Note: not `{row, col}`.
- `changes` = per-op `onChange` fire count (proof instrumentation; `0` for
  zero-diff). `read` reports the cumulative counter.
- `refused` reasons: `range not owned` (no owned span or the requested range
  escapes it), `dirty` (a real keystroke arrived — see takeover), and
  `out_of_bounds` (non-integer/negative start, `end > len`, or `start > end`).

## Events (server → client, unrequested, no reply)

```jsonc
{"event":"takeover","source":"key"}
```

Emitted **once** when the first delegated real keystroke reaches the editor
while an owned fragment exists; ownership flips `dirty` and further `replace`
/`cancel` are refused with `"dirty"` until the next ownership boundary.
Inserts the client makes itself can never trigger it (they bypass
`handleInput` entirely).

## Ownership model

`owned` = the `[start, end)` UTF-16 span the extension wrote since the last
boundary. `insert` extends it when contiguous (caret at `owned.end`), or
starts a fresh span. `replace` rewrites it. `cancel` removes it and clears it.
A delegated keystroke while owned ⇒ `dirty` + one takeover event.

## Caret behavior (measured — see plan/008_a47116bb2b79/architecture/pi_seam_proof.md)

- `insert` leaves the caret at end-of-insert (protocol-favorable for dictation).
- `replace` (implemented as whole-buffer `setText`) moves the caret to
  **end-of-buffer**. The reply reports the resulting cursor; adapters that
  need the caret elsewhere must not assume it is preserved.

## Lifecycle

- Installs on `session_start`, **gated on `ctx.hasUI`** — headless runs
  (`pi -p`, RPC) never create the socket and never error.
- pi fires `session_start` multiple times per process (startup, resume, new).
  The extension claims the editor slot **deferred** (setTimeout 0) and
  **re-asserts on every wave** — other editor extensions (e.g. pi-vim) claim
  the single slot synchronously and later waves would otherwise orphan us.
  Ownership state lives at module level and survives editor swaps.
- `/reload` re-evaluates the module; the previous instance's server is closed
  and the socket rebound. Clients: connection drop ⇒ reconnect to the path.
- All setup is wrapped: a bind/setup failure logs ONE console.error line and
  never breaks pi startup.

## Client recipe (S2 adapter sketch)

```python
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sock.connect(PATH)
def rpc(obj):
    sock.sendall((json.dumps(obj) + "\n").encode())
    return json.loads(makefile.readline())
state = rpc({"op": "read"})                    # text/cursor/owned/dirty
rpc({"op": "insert", "text": "hello"})         # applied
rpc({"op": "replace", "start": 6, "end": 11, "text": "world"})  # applied|unchanged|refused
rpc({"op": "cancel"})                          # remove owned span
# watch for {"event":"takeover","source":"key"} between replies → disarm delivery (R.5)
```

## Debug / off switch

There is none in v1 by design (the editor slot is single; a second extension
claiming it wins). Removing `.pi/extensions/voice-editor.ts` (or `/reload`
after removal) restores pi's default editor.

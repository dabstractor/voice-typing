# P1.M5.T1.S1 research — pi CustomEditor extension + AF_UNIX control socket

## §0 The pinned seam doc (contract point 1 — RESOLVED)

The contract's glob `@mariozechner/pi-coding-agent-*/docs/extensions.md` resolves on this machine to:

```
/home/dustin/.pi/agent/npm/node_modules/@mariozechner/.pi-coding-agent-e74iH7Md/docs/extensions.md   (2596 lines)
```

(hashed dir `.pi-coding-agent-e74iH7Md`; d2_bulk_delivery_map.md §7 records the same). The
`@earendil-works/pi-coding-agent` copy under `~/.local/lib/node_modules` is a DIFFERENT, much
shorter doc (274 lines) and does NOT contain the editor seam — the @mariozechner install is the
live agent's; the d2 map already flagged the two copies. **Use the @mariozechner doc + its .d.ts
files as ground truth.** Note the hashed suffix drifts on install — cite symbols, not raw paths.

## §1 Verified API surface (read from the pinned doc + .d.ts this session)

**Extension basics** (doc :5-:58, :108-133): extensions are TypeScript modules;
`~/.pi/agent/extensions/*.ts` (global) or **`.pi/extensions/*.ts` (project-local)** auto-discovered
(and `/reload`-able). Standard hook: `pi.on("session_start", (event, ctx) => …)`. **Gate UI installs
on `ctx.hasUI`** (doc :860 via d2 map) — extensions can run headless. Imports available:
`@mariozechner/pi-coding-agent` (ExtensionAPI, CustomEditor), `@mariozechner/pi-tui`, node builtins.
No package.json needed for node-builtin-only code.

**The editor seam** (doc :2258-2268 code block + :2387-2440 "Custom Editor" section, both read verbatim):
- `ctx.ui.setEditorComponent((tui, theme, keybindings) => new MyEditor(tui, theme, keybindings))`
- `const current = ctx.ui.getEditorComponent()` — capture the previous factory BEFORE setting yours
  (single slot; **compose by wrapping**, not replacing): `new Wrapped(tui,theme,kb, current?.(tui,theme,kb))`
- `ctx.ui.setEditorComponent(undefined)` restores the default editor.
- **Extend `CustomEditor` (NOT base `Editor`)** — CustomEditor is "Custom editor that handles
  app-level keybindings for coding-agent" (escape-to-abort, ctrl+d, model switching, extension
  shortcuts). **Call `super.handleInput(data)` for every key you don't handle.** Factory receives
  `theme` + `keybindings` from the app.

**CustomEditor** (`dist/modes/interactive/components/custom-editor.d.ts`, read in full): 
`class CustomEditor extends Editor` — ctor `(tui: TUI, theme: EditorTheme, keybindings:
KeybindingsManager, options?: EditorOptions)`; public: `onAction(action, handler)`,
`handleInput(data)`, `onEscape?`, `onCtrlD?`, `onPasteImage?`, `onExtensionShortcut?`.

**Base Editor buffer/caret surface** (`@mariozechner/.pi-tui-QCt45CRG/dist/components/editor.d.ts`,
class Editor block): 
- `getText(): string` / `getExpandedText()` (paste markers expanded) / `getLines(): string[]`
- `getCursor(): {…row/col}` (public read)
- `setText(text): void` — whole-buffer set
- **`insertTextAtCursor(text): void`** — doc comment: "Insert text at the current cursor position.
  Used for programmatic insertion (e.g., clipboard image markers). **This is atomic for undo** —
  single undo restores entire pre-insert state." ← the sanctioned programmatic-write primitive.
- `render(width): string[]`, `handleInput(data)`, `onSubmit?`, `onChange?`, `addToHistory(text)`
- cursor MUTATORS are private (`setCursorCol`, `moveToVisualLine`, …) — **programmatic caret
  placement beyond insert-at-cursor is NOT in the public surface.** This is exactly the
  "exact write/caret control NOT yet exercised" the contract flags → the minimal proof (§4) must
  MEASURE what setText does to the caret and what re-render requires, before the full build.

**Not the tool for this:** `ctx.fork(entryId, {position:"before"})` (doc :1024-1052) is a
session-tree restore primitive (fork before an existing entry + restore that prompt into the editor)
— NOT a text-injection API. The adapter injects text via its OWN editor methods (above).

## §2 The consumed contract — P1.M3.T1.S1 bulk-delivery results (verified in voice_typing/bulk_delivery.py)

`ShowResult` taxonomy (bulk_delivery.py :77-88): **applied | unchanged | refused | unknown**;
"Bytes sent is not 'applied'; 'unknown' is not 'delivered'". The socket op replies mirror this
(applied / unchanged (zero-diff) / refused (bad range/not owned)); `unknown` is reserved for the
S2 adapter's deadline layer (socket ops here are synchronous on the loop → not needed in S1, but
the vocabulary must match so S2 maps 1:1). Zero-diff guard also lives there (:31-34 + guard fn).

## §3 Design (the contract's LOGIC point, concretized)

File: **`.pi/extensions/voice-editor.ts`** (project-local, auto-discovered). No npm deps (node
`net`/`fs`/`os`/`path` only). Everything wrapped in try/catch so a socket/bind failure can NEVER
break pi startup (extension errors surface loudly otherwise).

```
session_start(event, ctx):
  if (!ctx.hasUI) return                       # headless (pi -p / RPC) — no editor to own
  const previous = ctx.ui.getEditorComponent() # single slot — capture to wrap
  ctx.ui.setEditorComponent((tui, theme, keybindings) =>
      new VoiceEditor(tui, theme, keybindings, previous))
```

`class VoiceEditor extends CustomEditor`:
- holds `tui` (for `requestRender()` after programmatic edits) + the wrapped previous editor
  instance (instantiated via the captured factory; not otherwise used — we ARE the editor).
- `handleInput(data)`: pure pass-through — if an owned fragment exists, first push
  `{"event":"takeover","source":"key"}` to socket clients and mark ownership dirty, THEN
  `super.handleInput(data)` always (we consume NOTHING; app keybindings intact).
- Ownership: tracks the [start,end) UTF-16 range it wrote (anchor = buffer prefix hash at insert
  time; re-derive on read). Any delegated keystroke while owned ⇒ dirty + event (R.5's
  at-the-target revocation signal — the daemon/S2 owns the HALT decision, we only report).
- Socket: `net.createServer().listen(sockPath)` — **`$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock`**
  (mkdir -p the dir; unlink stale file first; chmod 0600 best-effort — house ControlServer pattern).
  JSONL, one line in → one line out. Ops applied SYNCHRONOUSLY in the socket data handler (same
  Node event loop that drives the TUI — pi's loop, per the contract; no cross-thread issue):
  * `{"op":"insert","text":T}`    → `insertTextAtCursor(T)` → `{"ok":true,"result":"applied","cursor":…}`
  * `{"op":"replace","start":s,"end":e,"text":T}` → true range replacement: compute
    `newText = text.slice(0,s)+T+text.slice(e)`, `setText(newText)` → applied | unchanged (zero-diff)
    | refused (range not owned / out of bounds / dirty)
  * `{"op":"cancel"}`            → remove the owned range in ONE op → applied | unchanged
  * `{"op":"read"}`              → `{"ok":true,"text":…,"cursor":{row,col},"owned":{start,end}|null,"dirty":bool}`
  * malformed/non-dict/unknown op → `{"ok":false,"error":"…"}` (voicectl/ControlServer house shape)
- **UNITS = UTF-16 code units** (JS strings — R.3 "the adapter maps positions to the target's own
  units"); documented loudly in the README + `read` includes `"units":"utf-16"`.
- Zero keystrokes BY CONSTRUCTION: edits only via `insertTextAtCursor`/`setText`; `handleInput` is
  never synthesized. After each mutation: `tui.requestRender()` (tui.md: state change → invalidate
  → requestRender; the proof asserts the render path actually refreshes).

## §4 The minimal proof FIRST (contract: "prove it with a minimal proof FIRST (R.2 'prove at G3')")

Build order enforces it: a minimal skeleton (install + insert + read only) is proven in a
**detached tmux pane running real `pi`**, BEFORE the full op set lands. The proof (Python driver,
house env-gated lab pattern):
1. `tmux new-session -d -s vtseam 'pi'` (find pi via `shutil.which("pi")`, `PI_BIN` override; pi
   needs no model — session_start + editor work without any message send).
2. Poll ≤20 s for `$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock` (extension loaded).
3. Op matrix over the socket: insert "hello" → `read` asserts buffer endswith it + cursor advanced;
   insert unicode (Zoë — 日本語 🫡) → byte/unit roundtrip; replace tail "hello"→"world" → `read`
   asserts exact buffer + ONE applied; zero-diff replace → `unchanged`; replace out-of-owned-range →
   `refused`; cancel → owned range gone; a delegated keystroke via `tmux send-keys` → `takeover`
   event observed + owned→dirty.
4. Visible-render check: `tmux capture-pane -p` contains the inserted text (the buffer is REALLY
   rendered, not just mutated).
5. Teardown ALWAYS: kill-session + unlink socket; inner `timeout 240` + bash-tool timeout 300
   (AGENTS.md discipline); scratch = one mktemp dir, bounded.

What the proof specifically MEASURES (the unexercised unknowns): does `setText` preserve or reset
the caret (record actual behavior; the protocol reports the resulting cursor — dictation wants
caret-at-end-of-insert, which `insertTextAtCursor` gives by construction); does `tui.requestRender()`
suffice to refresh (vs needing invalidate); does onChange fire once per programmatic op (wire a
counter into `read`'s reply as `"changes":n` for the proof run). Failures here are bugs to fix in
the extension — this is OUR seam (unlike the field-matrix labs, there is no external software to
measure-honestly; the proof PASSES or the code is wrong).

Boundary: single-VISIBLE-edit/no-blank-frame assertions at the frame level are P1.M5.T2.S1's G3
row (isolated Ghostty + real render loop). S1 proves mechanism: buffer truth + one applied op +
visible text present + zero keystrokes.

## §5 Deliverables + consumers

1. `.pi/extensions/voice-editor.ts` — the extension.
2. `.pi/extensions/README.md` — Mode A: protocol (ops/args/replies/events, units, socket path,
   lifecycle, hasUI gating, error posture).
3. `tests/pi_seam_support.py` — pure helpers (payload builders, reply classifier vs ShowResult
   vocabulary, proof-oracle expectations) — stdlib only, collected without pi.
4. `tests/test_pi_seam_support.py` — unit tests for (3).
5. `tests/pi_seam_lab.py` — env-gated proof driver (`PI_SEAM_LAB=1`; spawns tmux+pi; NOT
   pytest-collected).
6. `plan/008_a47116bb2b79/architecture/pi_seam_proof.md` — evidence record (house style: method,
   op matrix results, measured caret/render findings, versions) — **the artifact S2's PRP cites**.

Consumer: P1.M5.T1.S2 (daemon-side cooperating-editor TargetAdapter) speaks this socket; the
sockPath + op vocabulary + units + ShowResult mirroring are ITS input contract — keep stable.
P1.M5.T2.S1 (Ghostty G3 row) runs the visible-field proof on top.

## §6 Gotchas

- G1: single editor SLOT — must capture `getEditorComponent()` BEFORE `setEditorComponent` and
  wrap; never assume you're the first.
- G2: `ctx.hasUI` gate mandatory (headless `pi -p` has no editor; installing would throw).
- G3: extend CustomEditor NOT Editor, else app keybindings (escape/ctrl+d/model switch) die.
- G4: ALWAYS `super.handleInput(data)` — we consume zero keys (pure observer + socket writer).
- G5: stale socket file blocks listen — unlink before bind (AF_UNIX; ControlServer precedent).
- G6: /tmp is RAM (AGENTS.md R3) — lab scratch = ONE mktemp dir, removed in finally; no unbounded logs.
- G7: tmux-driven pi inherits XDG_RUNTIME_DIR from the invoking shell — the lab must export it
  explicitly (tmux server may predate the env).
- G8: extension load failure must not break pi: wrap socket setup in try/catch + log one line.
- G9: `pi` binary discovery — `shutil.which("pi")`, `PI_BIN` override; never a hardcoded path.
- G10: UTF-16 units (not bytes/graphemes) — S2 must convert; the protocol states it explicitly.
- G11: two doc copies exist — @mariozechner (2596 lines, the live agent's, has the seam) vs
  @earendil-works (274 lines, does NOT). Cite symbols + the d2 map §7 reconciliation.
- G12: hashed package dir suffix drifts between installs — resolve via `find`, don't hardcode.
- G13: AGENTS.md two-timeout discipline on EVERY lab run; teardown (tmux kill + socket unlink) on
  every exit path including timeout-124.

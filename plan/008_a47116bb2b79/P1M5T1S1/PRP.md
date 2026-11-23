# PRP — P1.M5.T1.S1: pi extension — CustomEditor + AF_UNIX control socket (the cooperating-editor seam)

## Goal

**Feature Goal**: Build the **pi coding-agent side of the cooperating-editor seam** (PRD §4.2sexies
R.3 "the terminal chat prompt is the first milestone … a documented extension/input seam preferred
over a fork"): a project-local TypeScript extension `.pi/extensions/voice-editor.ts` that, on
`session_start` (gated on `ctx.hasUI`), **wraps pi's prompt editor** with a `CustomEditor` subclass
and serves an **AF_UNIX control socket** (`$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock`) speaking
one-JSON-line ops — **insert / replace / cancel / read** — applied as direct buffer mutations on
pi's event loop: **true range replacement, ZERO keystrokes** (never synthesized `handleInput`).
Replies mirror the P1.M3.T1.S1 `ShowResult` taxonomy (applied | unchanged | refused) so the
daemon-side adapter (P1.M5.T1.S2) maps 1:1. The contract's explicit unknown — "the API's exact
write/caret control is NOT yet exercised" — is retired by a **minimal proof FIRST** (R.2: "prove at
G3"): a real `pi` in a detached tmux pane, driven over the socket, asserting buffer + caret +
visible render, BEFORE the full op set lands.

**Deliverable** (6 NEW files; **ZERO modifications** to `voice_typing/**`, `tools/**`, existing
tests, `pyproject.toml`, `.gitignore`, any P1.M4.T5 file):
1. `.pi/extensions/voice-editor.ts` — the extension: `VoiceEditor extends CustomEditor`
   (captures/wraps the previous editor factory — single slot; pure `super.handleInput` pass-through
   with takeover observation) + the JSONL socket server + op handlers.
2. `.pi/extensions/README.md` — Mode A docs: the socket protocol (ops/args/replies/events,
   **units = UTF-16 code units**, socket path, lifecycle, `hasUI` gating, error posture).
3. `tests/pi_seam_support.py` — pure stdlib helpers: payload builders, reply classifier against the
   ShowResult vocabulary, proof-oracle expectations (collected without pi/TS).
4. `tests/test_pi_seam_support.py` — unit tests for (3).
5. `tests/pi_seam_lab.py` — env-gated proof driver (`PI_SEAM_LAB=1`): spawns tmux + real `pi`,
   polls the socket, runs the op matrix (insert/unicode/replace/zero-diff/refuse/cancel/takeover),
   asserts `read` back-truth + `tmux capture-pane` visibility, bounded teardown. NOT pytest-collected.
6. `plan/008_a47116bb2b79/architecture/pi_seam_proof.md` — the evidence record (op-matrix results,
   measured caret/render/onChange findings, versions) — **the artifact P1.M5.T1.S2's PRP cites**.

**Success Definition**:
- (a) With the extension present, `pi` (TUI) starts normally, keeps ALL app keybindings
      (escape/ctrl+d/model switching — CustomEditor, not base Editor), and the socket appears at
      `$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock`. Headless (`pi -p` / no UI) installs nothing
      (`ctx.hasUI` gate) and never errors.
- (b) Op matrix over the socket: `insert` places text at the caret (`applied`, cursor reported);
      `replace` performs ONE atomic range replacement (`applied`), zero-diff → `unchanged`, a range
      outside the owned/dirty fragment → `refused`; `cancel` removes the owned range in ONE op;
      `read` returns exact `{text, cursor, owned, dirty, units:"utf-16"}`. Unicode round-trips.
      All edits are buffer-API only — zero key events (by construction; asserted via the takeover
      event NOT firing on our own writes).
- (c) A delegated real keystroke (`tmux send-keys`) while an owned fragment exists pushes
      `{"event":"takeover","source":"key"}` and flips `dirty` — the R.5 at-the-target revocation
      signal for S2. Our own socket writes never emit it.
- (d) `tmux capture-pane -p` shows the inserted text — the buffer is really rendered, not just
      mutated. The proof MEASURES and records: caret behavior after `setText`, whether
      `tui.requestRender()` suffices to refresh, onChange count per op.
- (e) `timeout 120 .venv/bin/python -m pytest tests/test_pi_seam_support.py -q` green; the repo's
      existing suites green (this task adds files only); `git status --porcelain` shows ONLY the
      six new files.
- (f) A socket bind/setup failure inside the extension logs ONE line and NEVER breaks pi startup.

## User Persona

**Target User**: Internal — two consumers:
1. **P1.M5.T1.S2 (daemon-side cooperating-editor TargetAdapter)** — speaks this socket: connects,
   `read`s state, `show()`s via insert/replace, `cancel`s, consumes takeover events. The sockPath,
   op vocabulary, UTF-16 units, and ShowResult-mirrored replies are its input contract.
2. **P1.M5.T2.S1 (G3 row: pi prompt in isolated Ghostty)** — runs the visible-field proof (single
   visible edit, no blank frames) on top of this seam; S1's evidence record tells it which
   mechanism facts are already proven.

**Use Case**: The daemon (bulk-text mode) recognizes speech and must place/revise words in pi's
prompt editor. Its adapter connects to `pi-editor.sock`, `read`s the owned range, and on each
recognition update sends ONE `insert` (delta) or `replace` (minimal-diff correction) — the editor
applies it synchronously on pi's loop, replies `applied`, and the words are visible in the real
prompt. The user presses any key → the editor reports `takeover` → the adapter disarms delivery
(R.5) without ever having synthesized a keystroke.

**Pain Points Addressed**: (1) The IM-v2 route is DEAD on ghostty 1.3.1/1.4.0 (R.2 matrix) — the
pi prompt (the actual chat target) needs a route that does insert AND correct; the extension seam
gives both with native buffer truth. (2) Synthesized keystroke/Backspace chains are FORBIDDEN in
bulk mode (R.1 event-count law) — buffer edits make insertion and correction each exactly ONE op.
(3) The seam is documented but its write/caret control was never exercised — this item converts
"documented" into "proven with evidence".

## Why

- **PRD §4.2sexies R.3** names the terminal chat prompt as the first bulk-delivery milestone and
  prefers "a documented extension/input seam … over a fork"; R.2's evidence table records the seam
  (`ctx.ui.setEditorComponent()` / fork) with the explicit caveat "the API's exact write/caret
  control is not yet exercised by code — prove at G3". This item IS that proof + the adapter's
  server half.
- **It unblocks two leaves** (S2 daemon adapter, M5.T2 G3 rows) and feeds P1.M7.T1's G6 graduation
  evidence ("verified G3 rows for the pi prompt in Ghostty…").
- **Ownership-verifiable by construction**: the editor knows exactly what it wrote (unlike
  terminals that never send `surrounding_text` — R.2 matrix), so `replace` can refuse non-owned
  ranges and report takeover at the target — R.5's strongest form.
- **Zero-keystroke + one-edit** is native here: `insertTextAtCursor` is documented as atomic-for-
  undo programmatic insertion; `setText` is a whole-buffer set — one mutation, one render, no
  per-character typing, no Backspace chains.

## What

One TS extension + its protocol + a proof harness. The extension wraps (not replaces) pi's editor,
serves JSONL ops, tracks the owned range, observes (never consumes) keystrokes for takeover
reporting, and reports full state on `read`. The proof lab drives a real pi in tmux through the
complete op matrix and records the measured mechanism facts.

### Success Criteria

- [ ] (a)–(f) of the Success Definition, verified by the Validation Loop below.
- [ ] Extension is project-local (`.pi/extensions/`), auto-discovered, `/reload`-compatible, node-builtin-only.
- [ ] Protocol documented in `.pi/extensions/README.md` incl. units, replies, events, error shapes.
- [ ] Evidence record written with LIVE-measured findings (caret after setText; render refresh path;
      onChange per op) + versions (pi, node, OS, date, HEAD).
- [ ] `git status --porcelain` = exactly the six new files; no existing file touched.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer gets: the pinned doc path + verified line numbers for every seam symbol;
the exact CustomEditor/Editor public surface (read from the installed `.d.ts` this session); the
consumed ShowResult taxonomy; a copy-pasteable TS skeleton; the proof-lab flow with the repo's
timeout/teardown discipline; and the S2-facing contract surface to keep stable. No inference about
the pi API is left to the implementer — every method cited below was verified against the installed
package this session.

### Documentation & References

```yaml
# MUST READ — this item's own research (verified this session; THE spec companion).
- docfile: plan/008_a47116bb2b79/P1M5T1S1/research/pi_custom_editor_seam.md
  why: "§0 resolves the pinned doc (hashed dir .pi-coding-agent-e74iH7Md; the @earendil-works copy
        is a DIFFERENT 274-line doc WITHOUT the seam — use @mariozechner). §1 the verified API
        surface incl. the Editor buffer/caret methods. §3 the design. §4 the proof-first flow + what
        it measures. §5 deliverables/consumers. §6 gotchas G1-G13."

# MUST READ — the pinned seam doc (resolve the hashed dir via find; symbols stable, path is not).
- file: /home/dustin/.pi/agent/npm/node_modules/@mariozechner/.pi-coding-agent-e74iH7Md/docs/extensions.md
  why: "THE doc. Extension basics :5-:58 + locations :108-133 (project-local .pi/extensions/*.ts,
        /reload). session_start lifecycle. ctx.hasUI :860 (gate UI installs — headless exists).
        The editor seam :2258-2268 (setEditorComponent / getEditorComponent / wrap pattern /
        undefined-restore) + the Custom Editor section :2387-2440 (extend CustomEditor NOT Editor;
        super.handleInput for unhandled keys; capture-previous-to-wrap example verbatim)."
  gotcha: "hashed suffix drifts between installs — `find /home/dustin/.pi/agent/npm/node_modules
           -name extensions.md -path '*mariozechner*'`. The @earendil-works copy lacks the seam."
  critical: "fork (ctx.fork(entryId,{position:\"before\"}) :1024-1052) is a session-tree restore
             primitive, NOT text injection — do not use it for ops."

# MUST READ — the class surfaces (read from the installed .d.ts; the ONLY ground truth for methods).
- file: <mariozechner pkg>/dist/modes/interactive/components/custom-editor.d.ts
  why: "class CustomEditor extends Editor; ctor (tui: TUI, theme: EditorTheme, keybindings:
        KeybindingsManager, options?: EditorOptions); public onAction/handleInput/onEscape?/
        onCtrlD?/onPasteImage?/onExtensionShortcut?. 'handles app-level keybindings' — why we
        extend IT, not base Editor."
- file: <mariozechner pi-tui pkg>/dist/components/editor.d.ts   # e.g. @mariozechner/.pi-tui-QCt45CRG
  why: "class Editor public buffer/caret surface: getText()/getExpandedText()/getLines()/
        getCursor():{row,col}/setText(text)/insertTextAtCursor(text) — the latter documented
        'Insert text at the current cursor position. Used for programmatic insertion … atomic for
        undo'. render(width):string[]; handleInput(data); onSubmit?; onChange?. Cursor MUTATORS are
        private — caret control beyond insert-at-cursor is NOT public (the proof measures what
        setText does to the caret)."
  critical: "resolve the pi-tui dir via find too (hashed suffix); cite symbols not raw paths."

# MUST READ — the TUI component contract (render/focus/invalidate discipline).
- file: <mariozechner pkg>/docs/tui.md
  why: "Component interface: render(width) (lines must not exceed width), handleInput?(data),
        invalidate() on theme change; 'Call invalidate() when state changes, then
        handle.requestRender() to trigger re-render' — the refresh path after programmatic edits."

# MUST READ — the consumed result taxonomy (protocol vocabulary must mirror it 1:1).
- file: voice_typing/bulk_delivery.py
  why: "ShowResult (:77-88): applied | unchanged | refused | unknown; 'Bytes sent is not applied;
        unknown is not delivered'. The socket replies use applied/unchanged/refused; `unknown` stays
        reserved for S2's deadline layer (socket ops are synchronous → not needed in S1). The
        zero-diff guard precedent lives here too."

# MUST READ — the seam reconciliation + recipe this design implements.
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§7 pins the seam summary (doc path, line cites, the two-copies note, fork-is-not-injection,
        and the cooperating-editor recipe this PRP implements); §6 the environment facts."

# Working examples to mirror (extension shape/imports — read 2-3, don't copy features).
- file: <mariozechner pkg>/examples/extensions/   # e.g. border-status-editor.ts (editor-area render),
        custom-footer.ts, commands.ts
  why: "house TS style: `export default function (pi: ExtensionAPI) { pi.on("session_start", …) }`,
        imports from "@mariozechner/pi-coding-agent" / "@mariozechner/pi-tui" / node builtins."

# PRD ground truth.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.1 (event-count law: insertion=1, correction=1, zero-diff=0; synthesized typing
        FORBIDDEN), R.2 (evidence limits — a passing probe never flips unverified claims; 'prove at
        G3'), R.3 (TargetAdapter contract + 'extension/input seam preferred over a fork'), R.5
        (takeover at the target; stop never flushes late), R.7 (G-gates; automation isolation)."

# External — Node AF_UNIX + JSONL mechanics (the socket half).
- url: https://nodejs.org/api/net.html#serverlistenpath-callback
  why: "net.createServer().listen(path) binds an AF_UNIX socket; EADDRINUSE on a stale file —
        unlink before bind (fs.rmSync(sockPath, {force:true}))."
- url: https://nodejs.org/api/net.html#socketwriteencoding-callback
  why: "one reply line per request: socket.write(JSON.stringify(reply)+'\n'); setEncoding('utf8')
        + newline framing (the ControlServer/voicectl house pattern, TS-side)."

# Parallel context (in flight; ZERO file overlap — different dirs and file names entirely).
- file: plan/008_a47116bb2b79/P1M4T5S2/PRP.md
  why: "produces tests/ime_g3_matrix_*.py + architecture/g3_field_matrix.md — none of which this
        item reads or writes (its route table concerns the clipboard fallback decision M5.T3, not
        the pi seam). Do not duplicate its terminal-matrix work; do not touch its files."
```

### Current Codebase tree (relevant slice)

```bash
.pi/                            # exists (contains remote-pi/); NO .pi/extensions/ yet — this item creates it
voice_typing/                   # READ-ONLY (bulk_delivery.py supplies the ShowResult vocabulary)
tests/                          # existing suites (ime_*, bulk, streaming, …) — untouched
plan/008_a47116bb2b79/architecture/   # d2_bulk_delivery_map.md (§7 seam summary) + evidence-record style
tools/im-lab/                   # READ-ONLY precedent (env-gated lab + evidence discipline)
# The pinned pi install (hashed dirs — resolve via find):
#   /home/dustin/.pi/agent/npm/node_modules/@mariozechner/.pi-coding-agent-e74iH7Md/
#   /home/dustin/.pi/agent/npm/node_modules/@mariozechner/.pi-tui-QCt45CRG/
```

### Desired Codebase tree with files to be added

```bash
.pi/extensions/voice-editor.ts        # NEW — VoiceEditor(CustomEditor) + AF_UNIX JSONL op server
.pi/extensions/README.md              # NEW — Mode A protocol doc (ops/units/replies/events/lifecycle)
tests/pi_seam_support.py              # NEW — pure: payloads, reply classifier, proof oracle
tests/test_pi_seam_support.py         # NEW — unit tests (collected; no pi/TS needed)
tests/pi_seam_lab.py                  # NEW — env-gated proof driver (PI_SEAM_LAB=1; tmux + real pi)
plan/008_a47116bb2b79/architecture/pi_seam_proof.md   # NEW — evidence record (S2's input artifact)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TWO pi doc copies exist. @mariozechner/.pi-coding-agent-<hash>/docs/extensions.md
#   (2596 lines) is the LIVE agent's and HAS the seam; @earendil-works/... (274 lines) does NOT.
#   Resolve the hashed dir via find every time (suffix drifts); cite symbols, not raw paths.

# CRITICAL #2 — extend CustomEditor, NOT base Editor (doc :2387-2440). Base Editor loses app
#   keybindings (escape-to-abort, ctrl+d, model switching, extension shortcuts) — an unusable pi.

# CRITICAL #3 — the editor slot is SINGLE. ctx.ui.getEditorComponent() BEFORE setEditorComponent,
#   and wrap the previous factory (compose, don't replace). setEditorComponent(undefined) restores
#   the default — only meaningful as a debug/off switch; do not call it on session teardown.

# CRITICAL #4 — handleInput is PURE pass-through: we consume ZERO keys (observe for takeover, then
#   ALWAYS super.handleInput(data)). Synthesizing handleInput to "type" is FORBIDDEN anyway (R.1).

# CRITICAL #5 — ctx.hasUI gate is mandatory (doc :860): headless pi (pi -p / RPC clients) must
#   install nothing and never throw. Wrap the whole session_start body in try/catch regardless —
#   a socket/bind failure must log ONE line, never break pi startup.

# CRITICAL #6 — UNITS are UTF-16 code units (JS strings). Not bytes, not graphemes. The protocol
#   states "units":"utf-16" in read replies; README documents it; S2 converts. Never slice via a
#   normalized/lowercased copy (R.3).

# CRITICAL #7 — stale socket file → EADDRINUSE. fs.rmSync(sockPath, {force:true}) before listen
#   (AF_UNIX: the file must be unlinked — same rule as the daemon's ControlServer).

# CRITICAL #8 — the lab runs REAL pi in tmux: pi needs NO model/API key for this proof (extension
#   + editor work before any message is sent — never send one). Find pi via shutil.which("pi")
#   with a PI_BIN env override. tmux server may predate the shell env — export XDG_RUNTIME_DIR
#   explicitly to the pane (G7 in research §6).

# CRITICAL #9 (AGENTS.md) — TWO timeouts on every lab run (inner GNU timeout 240 + bash-tool 300)
#   and a guaranteed teardown on EVERY exit path incl. 124: tmux kill-session + socket unlink.
#   /tmp is a 32 GB tmpfs: ONE mktemp scratch dir, removed in finally; no unbounded logs (cap the
#   lab's capture at what the evidence record needs).

# CRITICAL #10 — this task NEVER talks to the voice-typing daemon, voicectl, the live desktop,
#   clipboard, or mic (R.7 isolation). The socket the extension serves is pi-LOCAL. Do not wire
#   anything daemon-side — that is S2.

# CRITICAL #11 — cursor mutators are PRIVATE on Editor. Programmatic caret control =
#   insertTextAtCursor (inserts AT the caret; atomic for undo) + setText (whole buffer). The
#   proof MEASURES setText's caret behavior and records it; do not invent a caret API.

# CRITICAL #12 — do not re-run or extend the terminal field-matrix work (P1.M4.T5 owns it); do not
#   touch .gitignore/pyproject/package.json (node builtins only — no npm deps, no TS toolchain
#   needed: pi compiles extension TS at load).
```

## Implementation Blueprint

### Data models and structure

**The socket protocol (v1 — S2's contract; keep stable):**

```jsonl
// path: $XDG_RUNTIME_DIR/voice-typing/pi-editor.sock  (AF_UNIX SOCK_STREAM; JSONL; one line in → one line out)

// OPS (client → server). Replies mirror ShowResult: result ∈ applied|unchanged|refused
{"op":"insert","text":"…"}                     // insert at caret (insertTextAtCursor; atomic-undo)
{"op":"replace","start":12,"end":18,"text":"…"} // ONE atomic range replacement (UTF-16 offsets)
{"op":"cancel"}                                 // remove the owned range in ONE op (keep listening)
{"op":"read"}                                   // full state (see reply)

// REPLIES (server → client)
{"ok":true,"result":"applied","cursor":{"row":0,"col":5},"changes":1}   // changes = onChange count for THIS op (proof instrumentation)
{"ok":true,"result":"unchanged","cursor":{…},"changes":0}               // zero-diff (render-equal)
{"ok":true,"result":"refused","reason":"range not owned|dirty|out_of_bounds"}
{"ok":true,"result":"applied","text":"…","cursor":{…},"owned":{"start":0,"end":11},"dirty":false,"units":"utf-16"}  // read
{"ok":false,"error":"malformed JSON: …|request must be a JSON object|unknown op: …"}                   // house error shape

// EVENTS (server → client, unrequested; no reply)
{"event":"takeover","source":"key"}             // a delegated REAL keystroke while owned != null (R.5 signal)

// OWNERSHIP: owned = [start,end) UTF-16 range this extension wrote since the last boundary;
// any delegated keystroke while owned → dirty=true + ONE takeover event. insert/replace extend/
// rewrite owned; cancel clears it. refused when the requested range is not within owned or dirty.
```

**Python support model (`tests/pi_seam_support.py`)** — frozen dataclasses `OpRequest`/`OpReply`,
`classify_reply(raw: dict) -> OpReply` validating the closed vocabularies, `expected_matrix()` (the
proof oracle: op → legal reply set), `build_probe_payloads()` (ASCII, unicode "Zoë — naïve 日本語 🫡",
replace/zero-diff/refuse cases), `render_proof_table(results)` (bounded, ≤120 lines).

### Implementation Tasks (ordered by dependencies — proof FIRST per the contract)

```yaml
Task 0: PREFLIGHT — resolve the live install + confirm the seam + the baseline.
  - RUN:
      DOC=$(find /home/dustin/.pi/agent/npm/node_modules -name extensions.md -path '*mariozechner*' | head -1); echo "$DOC"
      grep -n 'setEditorComponent\|getEditorComponent' "$DOC" | head        # :2258-2268 area
      sed -n '2387,2440p' "$DOC" | grep -n 'CustomEditor\|super.handleInput'
      ED=$(find /home/dustin/.pi/agent/npm/node_modules -name editor.d.ts -path '*pi-tui*' | head -1)
      grep -n 'getText()\|getCursor()\|setText(\|insertTextAtCursor(' "$ED"
      which pi || echo "pi not on PATH — set PI_BIN for the lab"
      timeout 120 .venv/bin/python -m pytest tests/test_pi_seam_support.py -q 2>/dev/null || echo "(tests not created yet — expected)"
      test ! -e .pi/extensions && echo "(no .pi/extensions yet — expected)"
  - EXPECTED: the doc resolves; all four seam symbols present; the four Editor methods present;
    `pi` locatable (else PI_BIN); no existing .pi/extensions. DO NOT create/edit anything else.

Task 1: CREATE .pi/extensions/voice-editor.ts — MINIMAL SKELETON FIRST (install + insert + read only).
  - IMPLEMENT: export-default extension; session_start gated on ctx.hasUI, whole body try/catch
    (one console.error line on failure); capture previous factory; setEditorComponent wrapping it;
    VoiceEditor extends CustomEditor holding tui + a changes counter wired to onChange; socket
    server (unlink-stale → listen; chmod best-effort) with insert/read + the house error shapes.
    Follow the skeleton in "Implementation Patterns" verbatim for structure/naming.
  - PROVE-BEFORE-EXTENDING: Task 2 must pass on THIS skeleton before Tasks 3-4 add the rest.
  - DO NOT: touch any other file; add npm deps (node builtins only); synthesize handleInput.

Task 2: CREATE tests/pi_seam_lab.py + RUN the minimal proof (the contract's "prove FIRST").
  - IMPLEMENT (see patterns): GATE_ENV="PI_SEAM_LAB"; tmux new-session running real pi; poll the
    socket ≤20s; minimal matrix: insert ASCII → read asserts text+cursor; insert unicode → read;
    capture-pane contains the text; teardown (finally: kill-session, unlink socket, rmtree scratch).
  - RUN: timeout 240 env PI_SEAM_LAB=1 .venv/bin/python tests/pi_seam_lab.py   (bash timeout 300)
  - EXPECTED: exit 0. This MEASURES the unknowns — record: caret after insert (by construction at
    end-of-insert), render refresh via tui.requestRender(), changes-per-op. A failure here is a
    bug in OUR skeleton — fix and re-run (this is a proof of our own seam, not an external
    measurement; there is no "legal blocked branch" for insert/read).
  - IF pi fails to render under tmux: record the error, fix the pane env (TERM), re-run. Never
    leave the tmux session or socket behind (teardown in finally; verify with tmux ls / ls $XDG_RUNTIME_DIR/voice-typing).

Task 3: EXTEND .pi/extensions/voice-editor.ts — full ops + ownership + takeover events.
  - IMPLEMENT: replace (compute newText from getText() slices → setText; zero-diff → unchanged;
    not-owned/dirty/OOB → refused with reason), cancel (remove owned in ONE op), read's
    owned/dirty/units fields, takeover event push on delegated keystrokes while owned (observe
    BEFORE super.handleInput; consume nothing; emit once per owned fragment), changes counter in
    every applied/unchanged reply.
  - RE-RUN Task 2's lab (now the FULL matrix: replace applied / zero-diff unchanged / refused /
    cancel / takeover via tmux send-keys → event observed + dirty=true; our own writes NEVER emit
    takeover). Fix until green.

Task 4: CREATE tests/pi_seam_support.py + tests/test_pi_seam_support.py.
  - IMPLEMENT: the data model above (pure stdlib; frozen dataclasses; closed vocabularies; bounded
    renderer). Tests: classifier over every legal/illegal reply; payload builders byte-exact;
    oracle completeness (every matrix row's legal set non-empty + closed); renderer bound; no pi/
    tmux/socket imports (collectable anywhere).
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_pi_seam_support.py -q   (bash timeout 180)

Task 5: WRITE .pi/extensions/README.md (Mode A) + the evidence record.
  - README: protocol v1 verbatim (ops/replies/events/units/socket path), lifecycle (session_start/
    hasUI/restore semantics), error posture, /reload note, S2 integration sketch (one connect-
    read-show-cancel cycle), NO daemon-side claims.
  - EVIDENCE: plan/008_a47116bb2b79/architecture/pi_seam_proof.md — method, LIVE op-matrix results
    table (from the Task 3 lab run), the MEASURED findings (caret/render/onChange), versions
    (pi --version or package.json, node --version, uname -r, date, git HEAD), boundary statement
    ("frame-level single-visible-edit is M5.T2's G3 row — this proves mechanism"), ≤120 lines.

Task 6: VALIDATE — the full Validation Loop L1-L4. No git commit unless directed; if asked:
  "P1.M5.T1.S1: pi CustomEditor extension + AF_UNIX control socket (cooperating-editor seam, proof-first)".
```

### Implementation Patterns & Key Details

```typescript
// .pi/extensions/voice-editor.ts — structural skeleton (names/shapes are the contract; fill verbatim)
import * as net from "net";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { CustomEditor, type ExtensionAPI } from "@mariozechner/pi-coding-agent";
import type { TUI } from "@mariozechner/pi-tui";

const SOCK_PATH = path.join(os.environ.XDG_RUNTIME_DIR ?? os.tmpdir(), "voice-typing", "pi-editor.sock");

class VoiceEditor extends CustomEditor {
  private owned: { start: number; end: number } | null = null;  // UTF-16 offsets
  private dirty = false;
  private changeCount = 0;
  constructor(tui: TUI, theme: any, keybindings: any, previous: any) {
    super(tui, theme, keybindings);            // CRITICAL #2: CustomEditor, not Editor
    this.tui = tui;                            // retained for requestRender() after programmatic edits
    this.onChange = (t) => { this.changeCount++; };   // proof instrumentation (fires for user edits AND ours)
  }
  handleInput(data: string): void {            // CRITICAL #4: observe, then ALWAYS delegate
    if (this.owned && !this.dirty) { this.dirty = true; pushEvent({ event: "takeover", source: "key" }); }
    super.handleInput(data);                   // app keybindings + text editing intact
  }
  // ops (called synchronously from the socket data handler — same Node loop as the TUI):
  opInsert(text: string)  { this.insertTextAtCursor(text); this.bumpOwned(); this.tui.requestRender(); return "applied"; }
  opReplace(start: number, end: number, text: string): "applied"|"unchanged"|"refused" {
    const cur = this.getText();
    if (start < 0 || end > cur.length || start > end) return "refused";
    if (!this.owned || this.dirty || start < this.owned.start || end > this.owned.end) return "refused";
    const next = cur.slice(0, start) + text + cur.slice(end);
    if (next === cur) return "unchanged";      // zero-diff → ZERO events (R.1)
    this.setText(next);                        // ONE atomic whole-buffer set (caret behavior MEASURED in the proof)
    this.owned = { start, end: start + text.length }; this.tui.requestRender(); return "applied";
  }
  // read()/opCancel() analogous; read returns { text, cursor: this.getCursor(), owned, dirty, units:"utf-16", changes }
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", (_event, ctx) => {
    try {
      if (!ctx.hasUI) return;                  // CRITICAL #5: headless installs nothing
      const previous = ctx.ui.getEditorComponent();      // CRITICAL #3: capture BEFORE set (single slot)
      ctx.ui.setEditorComponent((tui, theme, keybindings) =>
        new VoiceEditor(tui, theme, keybindings, previous?.(tui, theme, keybindings)));
      startServer();                           // unlink-stale → listen → JSONL dispatch (house error shapes)
    } catch (err) { console.error("voice-editor: setup failed:", err); }   // never break pi startup
  });
}
// startServer(): net.createServer; fs.rmSync(SOCK_PATH, {force:true}); fs.mkdirSync(dir,{recursive:true});
// server.listen(SOCK_PATH); connection → setEncoding("utf8"), split on "\n", json.loads per line,
// dispatch op, socket.write(JSON.stringify(reply) + "\n"). Malformed/non-dict/unknown-op →
// {"ok":false,"error": "malformed JSON: …" | "request must be a JSON object" | "unknown op: '…'"}.
// pushEvent(): best-effort write to all connected sockets; NEVER throws into the editor.
```

```python
# tests/pi_seam_lab.py — the proof driver (house env-gated lab pattern; NOT pytest-collected)
GATE_ENV = "PI_SEAM_LAB"          # without it: usage + exit 2
# flow: scratch = mkdtemp under /tmp (ONE dir) → tmux new-session -d -s vtseam "<PI_BIN>"
#   (PI_BIN = os.environ.get("PI_BIN") or shutil.which("pi"); export TERM/xterm-256color +
#    XDG_RUNTIME_DIR into the pane env) → poll (sock exists + accepts) ≤20 s → run matrix from
#    tests/pi_seam_support.py payloads over a plain socket (send JSONL, read one line):
#      1 insert ascii "hello from pi seam"   → reply result=="applied"; read text endswith payload
#      2 insert unicode "Zoë — naïve 日本語 🫡" → read round-trips EXACTLY (UTF-16 offsets intact)
#      3 replace tail (owned) "pi seam"→"edge seam" → applied; read text exact
#      4 replace same range with identical text → unchanged; changes==0 (zero-diff ⇒ zero events)
#      5 replace outside owned (start 0 len+10) → refused
#      6 cancel → owned==null; text intact outside the removed range
#      7 tmux send-keys -t vtseam "x" → a takeover event arrives (≤3 s) AND read.dirty==true
#      8 capture-pane -p → contains "edge seam" (really rendered)
#    finally (EVERY path incl. timeout): tmux kill-session -t vtseam; unlink sock; rmtree scratch
# discipline: two timeouts (inner 240 / bash 300); every wait is a bounded poll; assertions use
#    the CLOSED vocabularies from pi_seam_support (no string sniffing outside them).
```

### Integration Points

```yaml
CONSUMES (read-only):
  - the pinned pi extension API (doc + .d.ts surfaces, above)   # setEditorComponent/getEditorComponent/CustomEditor/Editor
  - voice_typing/bulk_delivery.py ShowResult vocabulary         # reply taxonomy mirrored 1:1
  - plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md §7   # the seam recipe this implements
PRODUCES (the S2 contract — keep stable once landed):
  - $XDG_RUNTIME_DIR/voice-typing/pi-editor.sock + protocol v1 (ops/units/replies/events)
  - plan/008_a47116bb2b79/architecture/pi_seam_proof.md         # S2's PRP cites the measured findings
DOES NOT TOUCH:
  - voice_typing/**, tools/**, every existing test, pyproject.toml, .gitignore, package.json (none
    created), P1.M4.T5.S1/S2 files (tests/ime_g3_*, g3_*.md — zero name overlap), the live desktop,
    clipboard, mic, daemon, voicectl.
PARALLEL-SAFE: P1.M4.T5.S2 (in flight) writes tests/ime_g3_matrix_*.py + g3_field_matrix.md —
  disjoint paths; neither reads the other.
```

## Validation Loop

### Level 1: Syntax & Style (immediate — "does pi even load it")

```bash
# pi compiles extension TS at load; the ONLY syntax gate that matters is a clean start:
DOC=$(find /home/dustin/.pi/agent/npm/node_modules -name extensions.md -path '*mariozechner*' | head -1)
grep -n 'class VoiceEditor extends CustomEditor\|super.handleInput\|ctx.hasUI\|getEditorComponent' .pi/extensions/voice-editor.ts
# Expected: all four present (CustomEditor not Editor; delegation; gate; wrap). No TS toolchain —
# do NOT add one. (Python files:) ruff check tests/pi_seam_support.py tests/pi_seam_lab.py --fix
# && ruff format them — zero errors (repo gate; no mypy config).
```

### Level 2: Unit Tests (component, compositor-free)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_pi_seam_support.py -q        # (bash timeout 180)
# Regression: this task adds files only — the neighboring suites must stay green:
timeout 180 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_bulk_controller.py \
  tests/test_g2_bulk_gate.py -q                                                # (bash timeout 240)
```

### Level 3: The proof lab (the deliverable's proof — run after Task 3, re-run after any edit)

```bash
timeout 240 env PI_SEAM_LAB=1 .venv/bin/python tests/pi_seam_lab.py; echo "exit=$?"   # (bash timeout 300)
# Expected: exit 0, full matrix (8 steps) green. exit 124 → wedged: check `tmux ls` + kill
# vtseam + unlink the sock BEFORE re-running (AGENTS.md: never retry-blind into a held socket).
# THEN hand-finish plan/008_a47116bb2b79/architecture/pi_seam_proof.md from this run (Task 5).
# Isolation: no voicectl/systemctl/pactl/wl-copy anywhere in the lab (grep gate below).
```

### Level 4: Contract audit (grep-provable invariants)

```bash
grep -nE 'extends Editor[^C]' .pi/extensions/voice-editor.ts || echo "ok: CustomEditor"
grep -c 'super.handleInput' .pi/extensions/voice-editor.ts                 # ≥1 (delegation)
grep -n 'hasUI' .pi/extensions/voice-editor.ts                            # gate present
grep -nE 'voicectl|systemctl|pactl|wl-copy|wtype|ydotool' .pi/extensions/voice-editor.ts tests/pi_seam_lab.py || echo "ok: isolated"
grep -n '"utf-16"' .pi/extensions/voice-editor.ts                          # units declared
wc -l plan/008_a47116bb2b79/architecture/pi_seam_proof.md                  # ≤120
git status --porcelain    # exactly: .pi/extensions/{voice-editor.ts,README.md}, tests/pi_seam_*, the evidence file
tmux ls 2>/dev/null | grep -c vtseam || echo "ok: no leaked session"; ls $XDG_RUNTIME_DIR/voice-typing/pi-editor.sock 2>/dev/null || echo "ok: sock cleaned (or live pi owns it — note which)"
```

## Final Validation Checklist

### Technical Validation

- [ ] L1 greps clean (CustomEditor/delegation/gate/units); ruff clean on the two Python support files.
- [ ] L2: `test_pi_seam_support.py` green; neighboring bulk suites green.
- [ ] L3: proof lab exit 0 — all 8 matrix steps; teardown verified (no vtseam session; sock state noted).
- [ ] L4: isolation greps clean; `git status --porcelain` = exactly the six new files.

### Feature Validation

- [ ] All Success Definition points (a)–(f) demonstrated by the lab run + recorded in the evidence doc.
- [ ] Measured findings present: caret after setText, render-refresh path, changes-per-op.
- [ ] App keybindings intact (lab step 7's delegated key still edits normally — dirty but functional).
- [ ] Headless path: extension present + `pi -p` one-liner (e.g. `echo hi | pi -p` under timeout)
      completes without socket or error — OR recorded as not-exercised with reason.

### Code Quality Validation

- [ ] TS mirrors the examples' import/style conventions; no npm deps; single-file extension.
- [ ] Support module pure stdlib, frozen dataclasses, closed vocabularies, ≤120-line renderer.
- [ ] Anti-patterns below avoided.

### Documentation & Deployment

- [ ] `.pi/extensions/README.md` documents protocol v1 fully (a client author needs nothing else).
- [ ] Evidence record carries versions + HEAD + the boundary statement (frame-level = M5.T2).

---

## Anti-Patterns to Avoid

- ❌ Don't extend base `Editor` (kills app keybindings) and don't skip `super.handleInput` for any key.
- ❌ Don't set the editor component before reading `getEditorComponent()` (single slot — you'd orphan
  the previous one), and don't call `setEditorComponent(undefined)` outside a deliberate off-switch.
- ❌ Don't skip the `ctx.hasUI` gate, and don't let any setup error propagate out of session_start.
- ❌ Don't synthesize `handleInput`/keystrokes to deliver text (R.1 event-count law; zero-keystrokes
  is the whole point) — buffer APIs only (`insertTextAtCursor`/`setText`).
- ❌ Don't return `applied` for bytes-written or for a zero-diff (that's `unchanged`); don't retry or
  re-write after any refused/unknown-shaped outcome; keep `unknown` reserved for S2's deadline layer.
- ❌ Don't use `ctx.fork` for text injection (session-tree primitive, not an input API).
- ❌ Don't add npm/package.json/TS toolchain; don't touch `voice_typing/**`, existing tests, the
  P1.M4.T5 files, pyproject, or .gitignore.
- ❌ Don't run the lab without both timeouts or without the finally-teardown; don't leave a vtseam
  tmux session or a stale socket behind (124 must be cleaned before any re-run).
- ❌ Don't touch the live desktop/clipboard/mic/daemon (R.7); don't claim frame-level single-edit
  proof (that's M5.T2's G3 row) — record the boundary honestly.
- ❌ Don't hardcode the hashed pi package path (find it), and don't cite the @earendil-works doc copy
  for the seam (it lacks the section).

---

## Confidence Score

**8/10.** Every API symbol this PRP pins was verified against the installed packages this session
(the doc's seam section read verbatim; CustomEditor + Editor `.d.ts` surfaces extracted; the
ShowResult taxonomy read from source), and the deliverable structure follows the repo's proven
env-gated-lab + evidence-record pattern. Residual risks, all with named mitigations: (1) pi's
runtime behavior for `setText` caret/`requestRender` refresh is unmeasured until the proof — that
is exactly why Task 2 runs the minimal proof BEFORE the full build (a bad surprise costs a skeleton
rework, not a finished feature); (2) pi may not render cleanly under a detached tmux pane on first
try (TERM/env — the lab exports them explicitly and records errors); (3) headless `pi -p`
acceptance is best-effort with an honest not-exercised fallback. The protocol surface is small,
self-contained, and consumed by exactly one downstream leaf whose PRP cites this one's evidence.

// voice-editor.ts — P1.M5.T1.S1 cooperating-editor seam (pi side).
//
// Wraps pi's prompt editor with a CustomEditor subclass and serves an AF_UNIX
// JSONL control socket ($XDG_RUNTIME_DIR/voice-typing/pi-editor.sock) so the
// voice-typing daemon (P1.M5.T1.S2 adapter) can place/revise text in the real
// prompt with ZERO synthesized keystrokes (R.1): buffer-API edits only
// (insertTextAtCursor / setText), applied synchronously on pi's event loop.
//
// Protocol v1 (S2 contract — keep stable; full doc in ./README.md):
//   units are UTF-16 code units; replies mirror bulk_delivery.ShowResult:
//   applied | unchanged | refused ("unknown" stays reserved for S2's deadline layer).
//
// House rules honored here:
//   - extends CustomEditor (NOT base Editor) so app keybindings survive;
//   - handleInput is a pure pass-through (observe, never consume);
//   - ctx.hasUI gate + full try/catch: a socket failure logs ONE line and
//     never breaks pi startup;
//   - node builtins only — pi compiles extension TS at load.
//
// Editor-slot reality (measured, see plan/…/pi_seam_proof.md): the slot is
// single and LAST WRITER WINS. Other editor extensions in this environment
// (pi-vim) claim it synchronously inside their session_start handler, AFTER
// project-local handlers run. We therefore (a) claim the slot DEFERRED
// (setTimeout 0 — after every synchronous handler of the same session_start
// wave), (b) re-assert on EVERY session_start wave (pi refires it on
// startup/resume/new), and (c) CAPTURE the previous factory without invoking
// it — invoking it builds a hidden duplicate editor whose buffer diverges
// from the mounted one (the ghost-editor bug this extension originally had).
//
// OWNERSHIP (R.5): owned = the [start,end) UTF-16 span this extension wrote
// since the last boundary. insert extends it (contiguous), replace rewrites
// it, cancel clears it. The FIRST delegated keystroke while owned flips
// dirty=true and pushes exactly one {"event":"takeover","source":"key"} to
// socket clients — the at-the-target revocation signal. Our own socket writes
// never pass through handleInput, so they can never emit takeover.

import * as net from "net";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { CustomEditor } from "@mariozechner/pi-coding-agent";
import type { ExtensionAPI, KeybindingsManager } from "@mariozechner/pi-coding-agent";
import type { EditorComponent, EditorTheme, TUI } from "@mariozechner/pi-tui";

const SOCK_PATH = path.join(
	process.env.XDG_RUNTIME_DIR ?? os.tmpdir(),
	"voice-typing",
	"pi-editor.sock",
);

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------

type ChangeHandler = (text: string) => void;
type Owned = { start: number; end: number }; // UTF-16 code-unit offsets, [start, end)

/** Ownership lives at MODULE level, not per editor instance: pi re-fires
 * session_start on resume/new waves and every wave may swap the editor
 * instance (ours or a wrapper's); the seam's ownership/dirty/counter state
 * must survive the swap. All VoiceEditor instances share this one state. */
const seamState = {
	owned: null as Owned | null,
	dirty: false,
	changes: 0,
};

interface OpOk {
	ok: true;
	result: "applied" | "unchanged" | "refused";
	reason?: string;
}
interface OpErr {
	ok: false;
	error: string;
}
type OpResult = OpOk | OpErr;

class VoiceEditor extends CustomEditor {
	tui: TUI;
	/** onChange fire counter — proof instrumentation. The app REASSIGNS
	 * `editor.onChange` after the factory returns (interactive-mode wires
	 * `newEditor.onChange = defaultEditor.onChange`), so a ctor assignment
	 * would be lost; instead we intercept assignment and chain: every fire
	 * increments our counter AND delegates to the app's handler. Backed by
	 * seamState.changes so it survives editor swaps across session waves. */
	get changeCount(): number {
		return seamState.changes;
	}
	private externalOnChange?: ChangeHandler;

	/** The span we wrote since the last boundary; null once canceled/consumed. */
	get owned(): Owned | null {
		return seamState.owned;
	}
	set owned(v: Owned | null) {
		seamState.owned = v;
	}
	/** A delegated REAL keystroke arrived while owned — the user took over. */
	get dirty(): boolean {
		return seamState.dirty;
	}
	set dirty(v: boolean) {
		seamState.dirty = v;
	}
	/** Socket clients that get unrequested takeover events. */
	clients = new Set<net.Socket>();

	constructor(tui: TUI, theme: EditorTheme, keybindings: KeybindingsManager) {
		super(tui, theme, keybindings); // CustomEditor, not Editor: app keybindings intact
		this.tui = tui;
		const self = this;
		Object.defineProperty(this, "onChange", {
			configurable: true,
			enumerable: true,
			get: () => (text: string) => {
				seamState.changes++;
				self.externalOnChange?.(text);
			},
			set: (fn: ChangeHandler | undefined) => {
				self.externalOnChange = fn;
			},
		});
	}

	/** Pure pass-through — we consume ZERO keys (app keybindings + text editing
	 * stay native). While an owned fragment exists, the FIRST delegated key
	 * flips dirty and emits ONE takeover event (R.5); after that the user owns
	 * the buffer and we stay silent. Our own ops never come through here. */
	handleInput(data: string): void {
		if (this.owned && !this.dirty) {
			this.dirty = true;
			pushEvent({ event: "takeover", source: "key" });
		}
		super.handleInput(data);
	}

	/** Absolute UTF-16 offset of the caret within getText(). */
	cursorOffset(): number {
		const lines = this.getLines();
		const { line, col } = this.getCursor();
		let off = 0;
		for (let i = 0; i < line && i < lines.length; i++) off += lines[i].length + 1; // +1 = "\n"
		return off + col;
	}

	// -- ops (synchronous, called from the socket data handler = pi's loop) --

	opInsert(text: string): OpResult {
		const caretBefore = this.cursorOffset();
		this.insertTextAtCursor(text); // atomic for undo; caret lands end-of-insert
		const caretAfter = this.cursorOffset();
		// Extend contiguous ownership, else the new span disowns the old.
		if (this.owned && !this.dirty && caretBefore === this.owned.end) {
			this.owned = { start: this.owned.start, end: caretAfter };
		} else if (this.owned && !this.dirty && caretBefore === this.owned.start) {
			this.owned = { start: caretBefore, end: this.owned.end - this.owned.start + caretAfter };
		} else {
			this.owned = { start: caretBefore, end: caretAfter };
		}
		this.tui.requestRender();
		return { ok: true, result: "applied" };
	}

	opReplace(start: number, end: number, text: string): OpResult {
		const cur = this.getText();
		if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end > cur.length || start > end) {
			return { ok: true, result: "refused", reason: "out_of_bounds" };
		}
		if (!this.owned) return { ok: true, result: "refused", reason: "range not owned" };
		if (this.dirty) return { ok: true, result: "refused", reason: "dirty" };
		if (start < this.owned.start || end > this.owned.end) {
			return { ok: true, result: "refused", reason: "range not owned" };
		}
		const next = cur.slice(0, start) + text + cur.slice(end);
		if (next === cur) return { ok: true, result: "unchanged" }; // zero-diff -> ZERO events (R.1)
		this.setText(next); // ONE atomic whole-buffer set (caret lands end-of-buffer — measured)
		this.owned = { start, end: start + text.length };
		this.tui.requestRender();
		return { ok: true, result: "applied" };
	}

	opCancel(): OpResult {
		if (!this.owned) return { ok: true, result: "refused", reason: "range not owned" };
		if (this.dirty) return { ok: true, result: "refused", reason: "dirty" };
		const cur = this.getText();
		const next = cur.slice(0, this.owned.start) + cur.slice(this.owned.end);
		if (next === cur) {
			this.owned = null;
			return { ok: true, result: "unchanged" };
		}
		this.setText(next); // removes the owned range in ONE op
		this.owned = null;
		this.tui.requestRender();
		return { ok: true, result: "applied" };
	}

	readState(): {
		text: string;
		cursor: { line: number; col: number };
		owned: Owned | null;
		dirty: boolean;
		changes: number;
	} {
		return {
			text: this.getText(),
			cursor: this.getCursor(),
			owned: this.owned,
			dirty: this.dirty,
			changes: this.changeCount,
		};
	}
}

// ---------------------------------------------------------------------------
// Socket server (AF_UNIX, JSONL: one request line -> one reply line)
// ---------------------------------------------------------------------------

/** The live editor instance — updated every time the app invokes our factory. */
let editor: VoiceEditor | null = null;
let server: net.Server | null = null;
/** Our factory's identity, so session_start waves can tell "slot is ours" from
 * "another extension (e.g. pi-vim) took the slot". */
let myFactory: EditorFactory | undefined;
/** The foreign factory that held the slot before us (restore path only — never
 * invoked: invoking it would build a hidden duplicate editor). */
let previousFactory: EditorFactory | undefined;

type EditorFactory = (
	tui: TUI,
	theme: EditorTheme,
	keybindings: KeybindingsManager,
) => EditorComponent;

// ---------------------------------------------------------------------------
// Socket server (AF_UNIX, JSONL: one request line -> one reply line)
// ---------------------------------------------------------------------------

/** Best-effort fan-out of unrequested events; never throws into the editor. */
function pushEvent(obj: unknown): void {
	const line = JSON.stringify(obj) + "\n";
	for (const sock of editor?.clients ?? []) {
		try {
			sock.write(line);
		} catch {
			editor?.clients.delete(sock);
		}
	}
}

function reply(sock: net.Socket, obj: unknown): void {
	try {
		sock.write(JSON.stringify(obj) + "\n");
	} catch {
		/* client gone mid-write — never propagate into the editor */
	}
}

function dispatch(sock: net.Socket, line: string): void {
	let req: unknown;
	try {
		req = JSON.parse(line);
	} catch (err) {
		reply(sock, { ok: false, error: `malformed JSON: ${(err as Error).message}` });
		return;
	}
	if (typeof req !== "object" || req === null || Array.isArray(req)) {
		reply(sock, { ok: false, error: "request must be a JSON object" });
		return;
	}
	const op = (req as Record<string, unknown>).op;
	if (!editor) {
		reply(sock, { ok: false, error: "editor not ready" });
		return;
	}
	const r = req as Record<string, unknown>;
	if (op === "insert") {
		if (typeof r.text !== "string") {
			reply(sock, { ok: false, error: "insert: 'text' must be a string" });
			return;
		}
		const before = editor.changeCount;
		finish(sock, editor.opInsert(r.text), editor.changeCount - before);
		return;
	}
	if (op === "replace") {
		const { start, end, text } = r;
		if (typeof text !== "string" || typeof start !== "number" || typeof end !== "number") {
			reply(sock, { ok: false, error: "replace: 'start', 'end' (numbers) and 'text' (string) required" });
			return;
		}
		const before = editor.changeCount;
		finish(sock, editor.opReplace(start, end, text), editor.changeCount - before);
		return;
	}
	if (op === "cancel") {
		const before = editor.changeCount;
		finish(sock, editor.opCancel(), editor.changeCount - before);
		return;
	}
	if (op === "read") {
		const s = editor.readState();
		reply(sock, {
			ok: true,
			result: "applied",
			text: s.text,
			cursor: s.cursor,
			owned: s.owned,
			dirty: s.dirty,
			units: "utf-16",
			changes: s.changes,
		});
		return;
	}
	reply(sock, { ok: false, error: `unknown op: ${JSON.stringify(op)}` });
}

/** Applied/unchanged/refused replies all carry the cursor and the per-op
 * onChange delta (proof instrumentation; zero-diff ops report 0). */
function finish(sock: net.Socket, res: OpResult, delta: number): void {
	if (!res.ok) {
		reply(sock, res);
		return;
	}
	reply(sock, { ...res, cursor: editor?.getCursor(), changes: delta });
}

function startServer(onLine: (sock: net.Socket, line: string) => void): void {
	if (server) return; // already serving in this module instance
	fs.mkdirSync(path.dirname(SOCK_PATH), { recursive: true });
	fs.rmSync(SOCK_PATH, { force: true }); // stale AF_UNIX file -> EADDRINUSE otherwise
	server = net.createServer((sock) => {
		sock.setEncoding("utf8");
		editor?.clients.add(sock);
		sock.on("close", () => editor?.clients.delete(sock));
		let buf = "";
		sock.on("data", (chunk: string) => {
			buf += chunk;
			for (;;) {
				const i = buf.indexOf("\n");
				if (i === -1) break;
				const line = buf.slice(0, i);
				buf = buf.slice(i + 1);
				if (!line.trim()) continue;
				try {
					onLine(sock, line); // an op exception must never kill pi
				} catch (err) {
					reply(sock, { ok: false, error: `op failed: ${(err as Error).message}` });
				}
			}
		});
	});
	server.listen(SOCK_PATH, () => {
		try {
			fs.chmodSync(SOCK_PATH, 0o600);
		} catch {
			/* best effort */
		}
	});
	server.on("error", (err) => {
		console.error(`voice-editor: socket error: ${err}`);
		server = null;
	});
}

function stopServer(): void {
	try {
		server?.close();
	} catch {
		/* ignore */
	}
	server = null;
	try {
		fs.rmSync(SOCK_PATH, { force: true });
	} catch {
		/* ignore */
	}
	editor = null;
}

/** Cross-/reload teardown handle: a re-evaluated module instance closes the
 * PREVIOUS instance's server (module-level `let`s reset on re-import, but
 * globalThis survives). */
const INSTANCE_ID = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
interface SeamGlobal {
	__voiceEditorSeam?: { id: string; stop: () => void };
}
const g = globalThis as typeof globalThis & SeamGlobal;

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export default function (pi: ExtensionAPI) {
	pi.on("session_start", (_event, ctx) => {
		try {
			if (!ctx.hasUI) return; // headless (pi -p / RPC): install nothing
			// /reload re-evaluated this file? Close the previous instance's server.
			if (g.__voiceEditorSeam && g.__voiceEditorSeam.id !== INSTANCE_ID) {
				g.__voiceEditorSeam.stop();
			}
			g.__voiceEditorSeam = { id: INSTANCE_ID, stop: stopServer };

			const current = ctx.ui.getEditorComponent();
			if (current !== myFactory && current !== undefined) {
				previousFactory = current; // capture foreign factory (restore path only)
			}
			if (!server) startServer((sock, line) => dispatch(sock, line));

			// Claim the slot DEFERRED: every synchronous session_start handler of
			// this wave (including pi-vim's) runs first; last writer wins.
			myFactory = (tui, theme, keybindings) => {
				editor = new VoiceEditor(tui, theme, keybindings);
				return editor;
			};
			const factory = myFactory;
			setTimeout(() => {
				try {
					ctx.ui.setEditorComponent(factory);
				} catch (err) {
					console.error("voice-editor: install failed:", err); // ONE line
				}
			}, 0);
		} catch (err) {
			console.error("voice-editor: setup failed:", err); // ONE line; never break pi
		}
	});
}

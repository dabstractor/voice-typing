# pi_seam_proof.md — P1.M5.T1.S1 evidence record

Proof that the pi cooperating-editor seam (`.pi/extensions/voice-editor.ts`,
`$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock`, protocol v1) works against a
**real pi** in a detached tmux pane: buffer truth, visible render, zero
keystrokes, ownership, takeover. This is the artifact P1.M5.T1.S2 (daemon
adapter) cites for mechanism facts. Frame-level single-visible-edit/no-blank
frames is **P1.M5.T2's G3 row** — this record proves mechanism only (R.2:
a passing probe never flips unverified claims).

- Date: 2026-11-23 · git HEAD: `34dca3b` · OS: Arch Linux, `7.2.7-arch1-1`
- pi CLI: 1.0.2 (`/home/dustin/.local/bin/pi`) · node: v24.22.0
- Pinned install: `@mariozechner/pi-coding-agent` 0.73.1
  (hashed dir `.pi-coding-agent-e74iH7Md`) · `@mariozechner/pi-tui` 0.73.1
  (hashed dir `.pi-tui-QCt45CRG`)
- Method: `timeout 240 env PI_SEAM_LAB=1 .venv/bin/python tests/pi_seam_lab.py`
  (env-gated lab; tmux `-L vtseam` dedicated server socket, `-x 160 -y 60`;
  inner waits bounded; teardown on every exit path). Final state: **exit 0,
  3/3 consecutive green runs** after fixes (two earlier runs exposed a
  startup-wave race and a lab-oracle bug — both fixed, see Findings).

## Op matrix (wire results, last green run)

| step | request | reply | measured detail |
|---|---|---|---|
| install | socket poll ≤20 s | pass | socket accepts ≈2–3 s after pi launch |
| 0 | read | applied | baseline `text='' cursor={line:0,col:0} owned=null dirty=false units=utf-16` |
| 1 | insert `"hello from pi seam"` | applied | `cursor={0,18}` (end-of-insert), `changes=1` |
| 2 | insert `"Zoë — naïve 日本語 🫡"` | applied | read round-trips EXACTLY; cursor `{0,36}` (36 UTF-16 units) |
| 3 | replace `[11,18)→"edge seam"` | applied | ONE op; read text exact; cursor `{0,38}`; `changes=1` |
| 4 | replace `[11,20)→"edge seam"` (identical) | unchanged | zero-diff ⇒ `changes=0` (R.1: zero events) |
| 5 | replace `[0,30)` (outside owned `[11,20)`) | refused | reason `range not owned`; cursor/changes instrumentation still reported |
| 6 | capture-pane | pass | `"edge seam"` visibly rendered in the pane |
| 7 | cancel | applied | owned range removed in ONE op; buffer == pre-cancel minus owned; `owned=null dirty=false` |
| 8 | insert `"again"` + `tmux send-keys "x"` | pass | exactly ONE `{"event":"takeover","source":"key"}` ≤3 s; read `dirty=true`; own writes emitted NO takeover |
| 9 | read final | applied | `text='hello from Zoë — naïve 日本語 🫡againx'`, `owned=(29,34)`, `dirty=true` |

Unicode note: the 🫡 emoji is 2 UTF-16 units — offsets stayed correct through
insert → replace → cancel (R.3 units discipline verified on the wire).

## Measured findings (the contract's retired unknowns)

1. **Caret after `setText`**: moves to **end-of-buffer** (source: pi-tui
   `Editor.setTextInternal` sets `cursorLine=lines.length-1, cursorCol=last
   length`; lab confirms `cursor={0,38}` on a 38-unit buffer). It is neither
   preserved nor reset-to-zero. S2 must read the cursor from the reply, not
   assume. `insertTextAtCursor` leaves the caret at end-of-insert (dictation
   path — protocol-favorable).
2. **Render refresh**: `tui.requestRender()` (non-force, diff-based repaint)
   **suffices** after programmatic edits — `capture-pane` assertions passed in
   every green run; `invalidate()` is not needed (pi-tui's `Editor.invalidate`
   is a documented no-op today). The earlier "blank render" was the ghost
   editor (finding 5), not a refresh-path problem.
3. **onChange per op**: fires **once** per programmatic op (`insertTextAtCursor`
   → 1, `setText` → 1); zero-diff → 0. pi's app **overwrites** `editor.onChange`
   after the factory returns (`interactive-mode.js` wires
   `newEditor.onChange = defaultEditor.onChange`), so instrumentation must
   intercept the property assignment (defineProperty chain), not assign it.
4. **Editor slot is single, last-writer-wins, and pi-vim contests it**:
   project-local extensions' `session_start` handlers run BEFORE user-level
   ones; pi-vim claims the slot synchronously in its handler. Fix: claim
   deferred (`setTimeout 0`) and re-assert on every wave. Startup fires
   `session_start` more than once (startup + resume re-emit via
   `bindExtensions`) — install must be idempotent and ownership state must
   live at module level to survive editor swaps.
5. **Ghost-editor hazard**: invoking the captured previous factory builds a
   hidden duplicate editor whose buffer diverges from the mounted one (this
   extension's original bug: socket ops landed in the orphan; typed keys in
   the mounted editor). Capture the previous factory, never invoke it. A
   wrapper extension re-invoking our factory (doc's compose pattern) is
   harmless — our instance stays in the mounted chain.
6. **Startup quiescence**: extension waves settle within ~6 s of socket
   appearance; the lab waits `SETTLE_S=6` before the matrix and uses 10 s
   request deadlines. Requests during a wave can starve; clients should
   reconnect on timeout (S2 guidance).
7. **Dev note**: pi compiles extension TS via jiti with a cache at
   `/tmp/jiti`; after editing the extension, a stale compile can be served.
   Nuking `/tmp/jiti/extensions-voice-editor.*.mjs` forces a fresh compile
   (hit once during development).

## Boundary statement

Proven here: buffer truth, one-op insert/replace/cancel, zero-diff and refusal
semantics, ownership + at-the-target takeover, zero synthesized keystrokes,
visible render in tmux. NOT proven here: frame-level single-visible-edit /
no-blank-frames in a real GPU terminal (isolated Ghostty) — that is
P1.M5.T2.S1's G3 row; and the daemon-side adapter itself is P1.M5.T1.S2.

## Deliverables (all NEW; no existing file touched)

`.pi/extensions/voice-editor.ts` · `.pi/extensions/README.md` (protocol v1) ·
`tests/pi_seam_support.py` · `tests/test_pi_seam_support.py` (43 tests) ·
`tests/pi_seam_lab.py` (env-gated `PI_SEAM_LAB=1`) · this record.
Isolation: no voicectl/systemctl/pactl/clipboard/mic anywhere in the lab
(grep-gated); the socket is pi-local (R.7).

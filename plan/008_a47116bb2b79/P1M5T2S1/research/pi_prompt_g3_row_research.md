# Research — P1.M5.T2.S1: G3 row "pi prompt in isolated Ghostty"

## §1 The two INPUT contracts (what exists when implementation starts)

### S1 — pi extension (LANDED, verified this session)
- `.pi/extensions/voice-editor.ts` EXISTS at repo root (confirmed). S1 status: Implementing/Complete
  at PRP-write time — the file is on disk.
- Socket protocol v1 (S1 PRP :285-310, reproduced verbatim — STABLE contract):
  - Path: `$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock` (AF_UNIX SOCK_STREAM, JSONL, one line in →
    one line out; stale file unlinked before listen).
  - Ops: `{"op":"insert","text":…}` (insertTextAtCursor, atomic-undo), `{"op":"replace","start":…,
    "end":…,"text":…}` (ONE atomic range replacement, UTF-16 offsets), `{"op":"cancel"}` (remove
    owned range in ONE op), `{"op":"read"}` (full state).
  - Replies: `{"ok":true,"result":"applied","cursor":{"row","col"},"changes":N}` — **`changes` =
    the extension's onChange count for THIS op (proof instrumentation — the edit-count witness)**;
    `unchanged` with `changes:0` (zero-diff); `refused` with reason
    `range not owned|dirty|out_of_bounds`; read replies carry
    `{"text":…,"cursor":{…},"owned":{"start","end"},"dirty":bool,"units":"utf-16"}`;
    `{"ok":false,"error":…}` for malformed/unknown ops.
  - Events (unsolicited): `{"event":"takeover","source":"key"}` — a delegated REAL keystroke while
    owned != null (the R.5 takeover signal). Any delegated keystroke while owned → dirty=true + ONE
    takeover event.
  - Ownership: `owned = [start,end)` UTF-16 range the extension wrote since the last boundary;
    insert/replace extend/rewrite it; cancel clears it; ops refused when range not within owned or
    dirty.
- **NO id echo** in replies → S2's client serializes one request in flight; `{"event":…}` lines
  route to the takeover callback, never to a pending reply.
- pi needs **NO model/API key** for editor+extension work (S1 CRITICAL #8) — never send a message.
- pi located via `shutil.which("pi")` with a `PI_BIN` env override.
- Extensions auto-discover from **project-local `.pi/extensions/*.ts`** (cwd) — no package.json
  needed for node-builtin-only code. Gate on `ctx.hasUI`.
- Editor seam: `ctx.ui.setEditorComponent((tui,theme,kb)=>new MyEditor(...))` extending
  `CustomEditor`; unhandled keys → `super.handleInput(data)`. Cursor mutators are PRIVATE on
  Editor; programmatic writes = `insertTextAtCursor` (at caret) + `setText`. Read side:
  `getText()/getCursor()`.
- S1's proof ran real pi in **tmux** (real desktop, XDG_RUNTIME_DIR exported to the pane). THIS row
  upgrades to the **isolated Ghostty** disposable desktop — the milestone requirement (R.3/R.4:
  "prove pi's real input editor inside isolated Ghostty").

### S2 — daemon-side adapter (IN FLIGHT — treat as contract)
- `voice_typing/pi_editor.py`: `PiEditorClient` (transport duck: connect/request/on_event split,
  one-in-flight, bounded reads), `PiEditorTarget` (implements `bulk_delivery.DeliveryTarget`:
  acquire/show/finalize/leave/cancel; zero-diff-first with NO request; insert-vs-replace op
  selection over the owned UTF-16 range via `map_span`; None/timeout reply ⇒ `ShowResult.UNKNOWN`,
  never retried; refusal taxonomy: "pi socket absent" / "pi socket no reply" / "editor dirty" /
  "editor owns fragment" / "read missing fields" / "inconsistent owned range" / "not acquired" /
  "utterance closed" / "revision regression"), `PiEditorTakeoverWatch` (exactly ONE
  `halt_for_takeover("pi-editor key takeover")`, latched; duck-typed controller — never imported).
- `tests/test_pi_editor.py` (fake-client + in-process fake-extension socket tests).
- **This row drives the REAL pi through S2's `PiEditorTarget`** — not raw sockets. That is the
  item's INPUT: "adapter from P1.M5.T1.S2".

## §2 The matrix verdict (INPUT #2 — P1.M4.T5.S2, architecture/g3_field_matrix.md)

- Re-run 2026-11-23 at HEAD 148aeda; versions: ghostty **1.4.0-2**, sway 1.12, foot 1.28.0-2,
  kitty 0.51.0-1, hyprland 0.57.2-1, gtk4 4.24.1-1.
- **ghostty row: `blocked (activate not_activated at 1.4.0-2 — IM route unavailable for this
  class)`** — ghostty 1.4.0 did NOT grow usable IM support (text-input activates but no byte
  reaches the pty, matching ghostty's IME tracker).
- Route table verdict: ghostty → **cooperating-editor seam (M5.T1)**; "terminal corrections ride
  the cooperating-editor seam, NEVER IM delete" — confirmed by the refreshed matrix. The clipboard
  insert-fallback (R.6, P1.M5.T3) is a SEPARATE row for ghostty-class INSERT — not this item.
- Hyprland relay: blocked (nested Hyprland aquamarine abort — do NOT attempt; private **Sway** is
  the lab compositor).
- "A G2/lab pass never marks a row verified. Only app-side witnesses record a row, and only with
  live versions attached."
- Command precedent: `timeout 420 env IME_G3_MATRIX_LAB=1 .venv/bin/python tests/ime_g3_matrix_lab.py`
  (env-gated lab; t_ms values are mechanism-level, NEVER G5 timing).

## §3 The paste-lab disposable-desktop recipe (tools/paste-lab/ghostty_probe.py — reuse verbatim)

The "private headless Sway + ghostty launch pattern" the contract mandates:
- Root: a private temp folder (`root`), guarded so `root == XDG_RUNTIME_DIR` and it lives under the
  temp tree; everything scoped inside it (sway.conf, sockets, TMPDIR).
- Outer env: `PATH=/usr/local/bin:/usr/bin:/bin`, `HOME=folder`, `XDG_RUNTIME_DIR=folder`,
  `XDG_CONFIG_HOME=folder`, `TMPDIR=folder`, `GDK_BACKEND=wayland`, `WLR_BACKENDS=x11`,
  `WLR_LIBINPUT_NO_DEVICES=1`, `WLR_RENDERER=pixman`, `LIBGL_ALWAYS_SOFTWARE=1`,
  `XDG_SESSION_TYPE=wayland`, `LANG=C.UTF-8`, `GTK_A11Y=none`, `GIO_USE_VFS=local`.
- Launch chain: `xvfb-run -a dbus-run-session --config-file=<bus> -- python <self> run <folder>`
  (timeout 21 s outer; GNU `timeout -k 2 25` wrapper at the doc line 1).
- Inside: write `sway.conf`; spawn `sway -c conf`; wait for `sway-ipc.*.sock` +
  `wayland-*` socket; set `SWAYSOCK`/`WAYLAND_DISPLAY`.
- Spawn `ghostty --gtk-single-instance=false --shell-integration=none …` (isolation flags; NOT
  paste-safeguard reconfiguration — the socket route never pastes).
- Find the window: `xdotool search --onlyvisible --maxdepth 1 --name '.*'` (last line = window id).
- Cleanup: EXIT/child-trap unwinds (term.wait(timeout=2), kill groups) even when GNU timeout fires.

**DELTA for this row (document, don't silently diverge):** paste-lab sets `HOME=folder`, but **pi
needs its real home** (node install + `~/.pi` agent dir are home-resident; S1's seam doc lives at
`~/.pi/agent/npm/node_modules/@mariozechner/...`). Resolution: keep `HOME` REAL (read-only usage),
isolate `XDG_RUNTIME_DIR`/`XDG_CONFIG_HOME`/`TMPDIR` + all Wayland surfaces; run pi with
`cwd=<temp project dir>` containing `.pi/extensions/voice-editor.ts` (copied from the repo) so the
extension auto-loads project-locally; export `XDG_RUNTIME_DIR` explicitly into ghostty's shell env
so the socket lands in the private dir (S1 CRITICAL #8's tmux lesson applies to any server that
may predate the shell env). Verify afterwards that nothing under the real HOME config changed that
matters (`git status` in the repo stays clean; no service/config/binding touched — R.4).
Ghostty config: do NOT disable paste safeguards (none are touched); `--gtk-single-instance=false`
guarantees an isolated instance.

## §4 The G3 row content (R.7 G3 + the item contract, scoped to one isolated window)

Scripted partials/finals driven through `PiEditorTarget` (S2) against real pi in isolated Ghostty:

1. **Short updates** — several sequential inserts (delta-only; each = 1 edit, `changes:1`).
2. **Correction** — first-word change (replace over the owned UTF-16 range = 1 atomic edit,
   `changes:1`, no delete/retype frame pair). The full "20-sentence first-word correction" may be
   scoped down IF the extension's owned-range model caps it — record what was run.
3. **Repeated identical finals** — zero-diff ⇒ `unchanged`, `changes:0`, ZERO socket requests
   (S2's zero-diff-first guard).
4. **Long + Unicode payloads** — e.g. the S1 probe set: ASCII + "Zoë — naïve 日本語 🫡" (astral 🫡 =
   2 UTF-16 units; offsets via `map_span`, never `len()`); a ~1 KB payload.
5. **Takeover** — mid-owned-fragment, `xdotool key` a REAL ordinary key into the ghostty window →
   extension pushes `{"event":"takeover","source":"key"}` → S2's watch fires `halt_for_takeover`
   EXACTLY once (duck controller records the call); afterwards `dirty:true` and ops REFUSED.
6. **Focus/window switch** — open/focus a second sway window mid-operation → handle revoked at the
   target (dirty/takeover or refused), never a post-takeover mutation. ("Pane/tab switch" does not
   apply to a single ghostty window — record as N/A in the row.)
7. **Refusing target** — out-of-owned-range replace (`refused: range not owned`), dirty-state op
   (`refused: dirty`), cancel with nothing pending (`unchanged`, no request).

**Assert (the item's four assertions):**
- **The editor's own text + caret** — witness = the extension's `read` op (`getText()` +
  `getCursor()` — the editor's own state; NOT a pty byte reader, NOT scrollback, NOT a fake
  editor). Assert exact expected text + cursor after every step.
- **The visible prompt** — requires visibility instrumentation. What exists: per-op `changes`
  (onChange count = the edit-count witness: applied=1, unchanged=0 — pins "no transient
  delete/retype frames" at the editor level). If NO rendered-prompt instrumentation exists (no
  render/screen dump), the row verdict is **"not verified"** for that leg — "missing visibility
  instrumentation means 'not verified', not 'passed'" (item contract; R.4 #1's wording). Optional
  supplementary (never the gate): a `grim` screenshot of the ghostty window kept as evidence.
- **No folded-paste placeholders** — assert the read-back editor text contains NO bracketed-paste
  markers (`\x1b[200~` / `\x1b[201~`) and no control bytes/tabs/newlines in the inserted prose
  (R.3: recognized prose line breaks normalize to a space — payloads use no newlines anyway).
- **No shortcut execution/submission** — driving ops never submits: the editor still holds the
  text (read-back), the buffer is never cleared, no Enter/newline is ever inserted (insert-only at
  caret), changes counts match exactly the expected per-op edit counts. Nothing message-shaped
  leaves the editor (no session transcript growth — pi is never given a model/key).
- **No neighbor changes** — the private desktop's sway tree contains exactly the expected window
  set (1 window, 2 during the focus-switch leg); assert via `swaymsg -r get_tree` (or xdotool
  window count) before/after; the ONLY channel into the desktop is our socket + scripted xdotool.

**Verdict vocabulary** (R.7): `untested | insert-only | blocked (reason) | verified (versions +
evidence links)` + this item's explicit `not verified (visibility instrumentation absent)` middle
case. The deliverable is ONE of: **verified | blocked (reason)** — with the not-verified case
recorded honestly if the visible-prompt leg lacks instrumentation.

## §5 Harness shape (mirror the ime_g3 trio)

- `tests/ime_g3_matrix_lab.py` + `ime_g3_matrix_support.py` + `test_ime_g3_matrix_support.py` is
  the house pattern: an **env-gated lab** (runs only under e.g. `PI_G3_ROW_LAB=1` so plain
  `pytest tests/` never boots a desktop) + **pure support helpers** (verdict row model, payload
  builders, bounded table renderer) + **pure unit tests** for the helpers (always run).
- This row adds the same trio: `tests/pi_g3_row_lab.py`, `tests/pi_g3_row_support.py`,
  `tests/test_pi_g3_row_support.py`. The lab drives S2's `PiEditorTarget`/`PiEditorClient`/
  `PiEditorTakeoverWatch` with a duck controller that records `halt_for_takeover` calls.
- Evidence output: bounded row report `plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md`
  (house precedent: `architecture/g3_gtk_rows.md`, `g3_field_matrix.md`) + a machine-readable
  `pi_row_verdicts.jsonl` beside it (the matrix's verdicts.jsonl convention). Only bounded evidence
  enters version control; the temp desktop is trap-removed.
- Run shape: `timeout -k 2 240 env PI_G3_ROW_LAB=1 .venv/bin/python tests/pi_g3_row_lab.py`
  (bash-tool timeout 300) — under BOTH AGENTS.md timeouts; every socket read bounded
  (never an unbounded makefile read — the ctl.py hang).

## §6 Gotchas distilled

1. pi under isolated HOME won't boot (node install + ~/.pi are home-resident) → keep HOME real,
   isolate the rest (§3 delta). Record the divergence in the report.
2. The extension auto-loads from PROJECT-LOCAL `.pi/extensions/` → copy `voice-editor.ts` into the
   temp project cwd; `git status` in the repo must stay clean.
3. Socket path is `$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock` — export the private
   XDG_RUNTIME_DIR into ghostty's shell (server may predate env — S1's tmux lesson).
4. Stale socket file → EADDRINUSE is handled extension-side (unlink before listen); the CLIENT
   side maps FileNotFoundError → "pi socket absent", no-reply → UNKNOWN (S2 taxonomy).
5. UTF-16 units everywhere; 🫡 = 2 units; all offsets via `bulk_delivery.map_span`.
6. No id echo: one request in flight; dispatch on `"event"` FIRST (takeover lines are not replies).
7. Never retry after UNKNOWN (S2/controller rule); the lab's duck controller records halts.
8. The 250 ms op deadline is the CONTROLLER's in production; in the lab, S2's own honest timeouts
   apply — record t_ms as mechanism-level info only (NEVER G5 timing claims).
9. Hyprland nested boot is DEAD (matrix) — use private Sway, do not re-attempt, do not re-run
   route discovery (R.4 #2: the route assignment is DECIDED).
10. Bounded everything: temp root under /tmp is RAM (AGENTS.md Rule 3) — the lab's EXIT trap must
    remove the desktop tree; logs/verdicts are line-bounded.
11. AGENTS.md: every command under inner GNU timeout + outer bash-tool timeout; `.venv/bin/python`
    never bare `python`; never run the real daemon/voicectl; no live desktop/clipboard/mic/service.
12. If S1's extension lacks a rendered-prompt dump, "visible prompt" is uninstrumented → verdict
    "not verified (…)" for that leg — an honest, contract-sanctioned outcome; NEVER mark verified
    from buffer-state alone when the contract demands the visible prompt.

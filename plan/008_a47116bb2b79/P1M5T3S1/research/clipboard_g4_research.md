# Research — P1.M5.T3.S1: Conditional clipboard insert-fallback + G4 gate

## 1. The decision INPUT is already recorded: NEEDED
`plan/008_a47116bb2b79/architecture/g3_field_matrix.md` (P1.M4.T5.S2, 2026-11-23, HEAD 148aeda):
- ghostty 1.4.0-2 row = **blocked** ("activate not_activated at 1.4.0-2 — IM route unavailable for this class"). 1.4.0 measured WORSE than the 1.3.1 baseline.
- Route table (derived + unit-tested via `tests/ime_g3_matrix_support.py::derive_route_table`):
  `clipboard_fallback_m5t3: "needed (ghostty-class insert blocked at 1.4.0-2)"`; ghostty route =
  "clipboard insert-fallback (R.6)"; foot/kitty = im-v2 insert-only + cooperating-editor seam for
  corrections; gtk = im-v2 full.
- Open item: ghostty 1.5.0 watch (PR #15246) — retest at 1.5.0; the ELSE branch (recorded skip)
  stays alive for a future matrix flip, but at HEAD the condition HOLDS → implement + G4.

## 2. Contract surface the adapter implements (landed, adds-only rule)
- `voice_typing/bulk_delivery.py` (PURE contracts): `DeliveryTarget` Protocol —
  `acquire()->AcquireResult(ok,handle,revision,reason)`, `show(session,utterance,seq,expected_revision,
  span)->ShowResult`, `finalize(...)`, `leave()`, `cancel()`. Taxonomy `applied|unchanged|refused|unknown`;
  refused/unknown disarm, unknown never retried. `rendered_equal` = zero-diff guard.
- Adapter exemplars: `voice_typing/ime/target.py::ImeTarget` (FieldBinding + recheck + insert-only
  handling), `voice_typing/pi_editor.py::PiEditorTarget` (client + binding + takeover watch). Both
  re-check at mutation time; controller (`bulk_controller.py`) owns deadlines — "the adapter is never
  trusted to self-timeout".
- Wire lineage: `voice_typing/ime/wlwire.py` (stdlib hand-rolled Wayland wire client; `Client`,
  `Event`, u32/i32/wstr) — the reuse skeleton for a `zwlr_data_control_manager_v1` source. Data-control
  v2 is ADVERTISED (im-lab README:79-84, private sway + live Hyprland).
- Daemon dispatch wiring is P1.M6.T2's job — this item ships the adapter + G4 evidence, no daemon edits.

## 3. R.6 clauses → mechanism map (what G4 must prove)
1. **Preserve ALL prior formats AND bytes.** wl-copy CANNOT restore multi-format offers (one stream
   under many `-t` types; save/restore via `wl-paste|wl-copy` collapses to one type —
   external_tech_notes §5.4). → Snapshot EVERY MIME type + exact bytes (`wl-paste --list-types` +
   per-type reads), and RESTORE via a data-control SOURCE that serves per-type bytes on `send`
   (zwlr_data_control_source_v1: offer(mime)+send(mime,fd) per type — protocol-level per-type bytes;
   XML: wlr-protocols unstable/wlr-data-control-unstable-v1.xml). wl-copy single-type restore is
   insufficient; the data-control source is the required mechanism.
2. **Distinguish original ownership from a later identical copy.** Content comparison cannot do this
   (PRD names compare-before-restore INSUFFICIENT). → Our staged/restored source offers a private
   sentinel MIME (`x-voice-typing/nonce`, random token). A selection event whose offer carries our
   current nonce = ours; identical bytes WITHOUT the nonce = a later user copy → never treated as ours.
3. **Protect a simultaneous user paste.** → Mutation-time recheck: verify the selection still carries
   our nonce immediately before the trigger chord; after trigger, confirm the TARGET received our
   bytes (byte-reader witness). A selection change mid-window (someone else set_selection, incl.
   identical bytes) → abort (refused), never paste foreign content. A real user keypress mid-transfer
   → the existing Rev 3 HALT path + adapter refuses queued ops.
4. **Keep partials out of the configured clipboard-history watcher.** Managers watch via data-control
   (`wl-paste --watch cliphist store`) and snapshot EVERY offer (§5.5) — NO protocol-level hiding
   exists. → The honest design: DETECT a running watcher (pgrep/known-manager scan; data-control
   exposes no peer list); if one runs, `acquire()` fails `reason="clipboard-history watcher active —
   R.6 partials-out-of-history unprovable"` → adapter UNAVAILABLE (R.6: "never disable the manager").
   Without a watcher: full live inserts. G4 leg 1 measures exactly this with a PRIVATE manager.
5. **PRIMARY untouched.** wl-copy/wl-paste default to the clipboard selection; data-control
   `set_selection` on the zwlr device = clipboard. Never bind zwp_primary_selection. G4 asserts
   PRIMARY unchanged.
6. If ANY clause is unprovable with the local manager → adapter UNAVAILABLE, never disable the
   manager. **An honest UNAVAILABLE-under-watcher verdict is a SUCCESS of this item.**

## 4. Paste mechanism (paste-lab evidence, tools/paste-lab/ghostty_probe.py — never edit)
- Disposable desktop: xvfb-run + dbus-run-session (private bus conf) + sway `-c` (xwayland disable,
  focus_follows_mouse no), WLR_BACKENDS=x11, WLR_RENDERER=pixman, private HOME/XDG dirs; refusal guard
  if not inside the disposable root.
- Staging: `wl-copy --foreground --type text/plain;charset=utf-8` (stdin bytes; keep-alive serves the
  offer). Verify via `wl-paste --no-newline` == data. Trigger: `xdotool key --delay 10 ctrl+shift+v`
  (ghostty paste chord) after focusing the compositor's X window. NO `--paste-once` — "a read by a
  history manager isn't a target acknowledgement" (probe comment :104).
- Target witness: ghostty `-e python probe.py receive` byte reader with bracketed-paste marks
  (ESC[200~/ESC[201~), atomic result publish via tmp+rename.
- Results: 951-B Unicode = ONE exact bracketed paste, 153/175 ms trigger→bytes (mechanism only, NOT
  G5); pasted 0x08 0x08 → two SPACES + "end" ⇒ bulk-Backspace-over-paste DEAD ⇒ **insert-only by
  design** (corrections for ghostty-class = cooperating-editor seam M5.T1, NOT this route).

## 5. Insert-only semantics over DeliveryTarget
- `show(span)`: span extends owned prefix (common-prefix = owned) → paste ONLY the delta (1 op);
  span diverges (correction requested) → REFUSED honestly (row is insert-only). Pure extension with
  zero delta → UNCHANGED (rendered_equal). `finalize`: matching → UNCHANGED (ownership ends, no
  edit); differing → REFUSED (cannot replace) — recorded, never retried.
- No `type_character`/`press_backspace` surface; no legacy-backend fallback. One trigger chord is the
  sanctioned paste mechanism (R.2 shortcut-trigger evidence); per-char typing is FORBIDDEN.

## 6. G4 legs (each = contents/history/formats/target assertions, NEVER exit codes)
1. private manager (text+image watchers: `wl-paste --watch` store script in the disposable desktop)
   → do partials land in history? (clause 4 verdict)
2. simultaneous copies incl identical bytes → nonce distinguishes; adapter aborts cleanly.
3. user paste during transfer (synthetic real key mid-window) → HALT/refuse; no second paste.
4. empty / rich-text (text/plain+text/html) / image (image/png) originals → snapshot+restore exact.
5. failure before/after the data request (target dies pre-read; adapter dies post-send) → unknown
   class; contents intact; never falsely applied.
6. process death mid-cycle (SIGKILL adapter) → user clipboard ends restored-or-visibly-faulted;
   PRIMARY + history verified.
- Harness pattern: env-gated lab (`GATE_ENV` precedent `IME_G3_MATRIX_LAB`, `PI_G3_ROW_LAB`) →
  `CLIPBOARD_G4_LAB=1`, two-phase boot, verdicts.jsonl, EXIT-trap teardown, ≤150-line report.
- Run form: `timeout 420 env CLIPBOARD_G4_LAB=1 .venv/bin/python tests/clipboard_g4_lab.py`
  (bash-tool timeout 480). Unit: `timeout 120 .venv/bin/python -m pytest tests/test_clipboard_target.py
  tests/test_clipboard_g4_support.py -q`.

## 7. Scope boundaries
- Adds-only: no edits to bulk_delivery/bulk_controller/ime/**/pi_editor/daemon/config/matrix labs.
- P1.M5.T2.S1 (pi row, in flight) + P1.M5.T2.S2 (editor/browser rows, in flight) are parallel — zero
  file overlap; M5.T2.S2's browser verdict may EXTEND the need (browser-class insert fallback) but
  never blocks this item; the matrix doc is the single decision input.
- G5 timing is NOT this item (mechanism ms are recorded, never claimed as G5).
- ghostty 1.5.0 retest belongs to the matrix watch, not here.

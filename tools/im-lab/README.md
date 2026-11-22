# im-lab — §4.2sexies bulk-text-delivery capability spike (Rev 4 pre-implementation)

**Question:** which delivery route from PRD §4.2sexies R.4 actually exists on this
machine — input-method composition, cooperating-editor range replacement, or
clipboard paste — proven with running code against real editable fields in an
isolated desktop, asserting byte-exact editor state. **This is a spike: it
answers capability questions and sets the route for implementation. It is NOT
G3/G5 acceptance evidence** (no real speech, no live desktop, no mic).

Run (bounded, ~90 s, isolated disposable desktop — same recipe as paste-lab):

```sh
timeout -k 2 150 python3 tools/im-lab/imlab_run.py [--keep DIR]
timeout -k 2 150 python3 tools/im-lab/hypr_nest.py        # nested-Hyprland attempt
WAYLAND_DISPLAY=<sock> python3 tools/im-lab/globals.py    # passive registry dump
```

## Files

| File | Role |
|---|---|
| `wlwire.py` | Minimal Wayland wire client, stdlib only (no pywayland on this box). Core + `zwp_input_method_v2` + keyboard grab. Opcode tables must match the protocol XML (provenance below). |
| `im_probe.py` | Becomes the seat input method; JSON command socket (`insert`/`replace`/`preedit`/`endpreedit`/`grab`); size-capped event log `im.jsonl` (64 KiB). |
| `field_gtk.py` | Real GTK4 `Gtk.Entry` dumping text+cursor+edit-count atomically (`cseq` counts document edits only). |
| `field_term.py` | Real GNU-readline line editor inside the terminal under test, dumping its live buffer. |
| `imlab_run.py` | Orchestrator: private Xvfb seat + private D-Bus + Sway (x11 backend), scripted rows, verdicts to stdout + `verdicts.jsonl`. |
| `hypr_nest.py` | Same rows against a nested Hyprland (see open items). |

Protocol provenance: `zwp_input_method_v2` wire format from the XML vendored by
Hyprland itself (`hyprwm/Hyprland protocols/input-method-unstable-v2.xml`,
wlr-protocols lineage). It carries `commit_string`, `set_preedit_string`,
`delete_surrounding_text(before,after)` and an atomic `commit(serial)` whose
evaluation order is preedit-replace → delete-surrounding → insert-commit.

## Results (2026-11-22, sway 1.12 / foot 1.28 / kitty 0.49.1 / ghostty 1.3.1 / GTK 4)

Final run: **29 rows, 24 pass** — all 5 failures are capability findings, not
harness bugs. Evidence: `verdicts.jsonl` + `im.jsonl` + screenshot-hash pairs.

| Field | insert | correct (one atomic edit) | preedit | surrounding-text (verified text channel) |
|---|---|---|---|---|
| GTK4 Entry | ✅ 26–40 ms cmd→field, cursor at end | ✅ exact, **whole-span 1024 B in one commit**, 1–2 internal `changed` signals in one commit cycle | ✅ zero document edits; final-after-preedit = single atomic transition | ✅ byte-exact cursor/anchor, up to 1024 B, 14+ events |
| foot 1.28 | ✅ 20 ms, exact, no paste markers | ❌ `delete_surrounding_text` **silently ignored**; never sends surrounding text | ✅ rendered (stable-shot hash diff), app receives zero bytes | ❌ none sent |
| kitty 0.49 | ✅ | ❌ ignored (same as foot) | app-side ✅ (render unproven — caret blink) | ❌ none sent |
| ghostty 1.3.1 | ❌ text-input **activates** but commit never reaches the pty (also via preedit cycle) | ❌ | ❌ | ❌ |
| Takeover channel (`grab_keyboard`) | — keymap delivered, synthetic `b` captured (keycode 48), field untouched while grabbed; **commit_string generates zero key events** → delivery cannot self-trigger HALT | | | |

Unicode payload `Zoë — naïve résumé … 日本語のテストです 🫡 café` and the
951-byte paste-lab sample round-trip byte-exact. Zero-diff row: zero events.
ghostty's gap matches its own tracker (IME commit lost, gtk-ime fix branch
pending as of 2026-10) — a version watch, not a dead end.

Compositor advertisement (passive, read-only registry listing):

- **Live Hyprland 0.56.2** (the operator's session): `zwp_input_method_manager_v2 v1`,
  `zwp_text_input_manager_v3 v1`, `zwp_virtual_keyboard_manager_v1`,
  `zwlr_data_control_manager_v1 v2`, `zwp_primary_selection_device_manager_v1`.
- Private Sway 1.12: same. (71 vs 55 globals total; injection set identical.)

## Route decision (per R.4 priority order)

1. **Input-method-v2 is the primary route — it exists and is capable.** The PRD's
   event-count law maps 1:1 onto the protocol: insertion = one `commit_string`
   + `commit`; correction = one `delete_surrounding_text(before,0)` +
   `commit_string` + `commit` (atomic by protocol definition); zero-diff = send
   nothing. `surrounding_text` events give the adapter **target-confirmed
   visible text** — exactly R.5's "last target-CONFIRMED visible text" — and the
   keyboard grab gives target-side takeover sensing that delivery itself cannot
   trip (measured: 0 self-key-events).
2. **Coverage is field-class-dependent** (legitimate blocked rows per R.4):
   - GTK-class fields (and any text-input-v3 app that implements surrounding
     text): full insert+correct+verify.
   - foot/kitty terminals: insert-only via IM; corrections need the
     cooperating-editor seam.
   - ghostty 1.3.1: IM route dead; insert falls back to the paste-lab clipboard
     route; corrections need the cooperating-editor seam.
3. **Cooperating-editor seam for the pi milestone exists without a fork**: pi
   extensions offer `ctx.ui.setEditorComponent()` (install a custom editor) and
   prompt-restore paths (`ctx.fork({position:"before"})` restores text into the
   editor). An extension exposing a control socket = the R.3 TargetAdapter for
   the terminal chat prompt, with range replacement on the target's event loop.
4. Clipboard route: untouched here by design — R.6 constraints stand; paste-lab
   already carries the insert evidence for terminals.

Timing (mechanism-level only, NOT G5 speech evidence): cmd→visible-field
20–40 ms on GTK and foot — the transport layer sits far inside G5's 100 ms
update-frame budget; recognition cadence will dominate.

## Open items for implementation

- **Hyprland behavior matrix**: nested Hyprland failed to boot under the
  software-rendered disposable desktop (aquamarine `CBackend::create()`); only
  advertisement is verified. G3 needs an isolated real Hyprland session row
  before any "works on the operator's desktop" claim.
- **One-IM-per-seat**: the tool becomes the seat's only input method; a user
  IME (fcitx5 etc.) collides (`unavailable` event must be handled). Not an
  issue today (no IME installed) but must degrade gracefully.
- **4000-byte commit cap** (protocol): corrections larger than one commit must
  chunk — check against R.1's one-edit rule for pathological finals.
- Terminals send no surrounding text → ownership/position verification in
  terminals must come from the app side (readline state, pi seam), matching
  R.3's "adapter maps text positions to the target's own units".
- GTK decomposes a correcting commit into delete+insert internally (1–2
  `changed` signals in one commit cycle); whether that is ONE rendered frame
  needs frame-level instrumentation in G3.
- ghostty version watch: retest IM rows when its gtk-ime work lands.
- `E`-row idle check and `O` grab rows run while GTK field holds text-input;
  ordering matters if rows are extended.

## Hygiene

All runs use `mktemp`-owned disposable dirs (auto-removed), logs size-capped
(64 KiB), GNU `timeout` inside + harness timeout outside, teardown kills every
process group. No live desktop input/clipboard/mic is exercised; the live
Hyprland socket is only listed passively (registry read, no binds).

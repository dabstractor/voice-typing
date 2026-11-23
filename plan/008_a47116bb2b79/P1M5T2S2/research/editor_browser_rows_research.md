# Research — P1.M5.T2.S2: Graphical editor + browser text field G3 rows

Written 2026-11-24 from read-only codebase analysis at HEAD `de20669` + one web search.
All file:line refs verified this session. Nothing in this note was modified.

## 1. Inputs (all LANDED — verified via git log)

- **Harness (P1.M4.T5.S1)** — commit `148aeda`: `tests/ime_g3_lab.py` (453+ lines),
  `tests/ime_g3_field_gtk.py`, `tests/ime_g3_support.py`, `tests/test_ime_g3_support.py`,
  `plan/008_a47116bb2b79/architecture/g3_gtk_rows.md`.
- **Adapter (P1.M4.T3.S3 finalize/leave/cancel)** — commits `7e9883a` + `41e0f18`/`e96cfeb`
  (show insert/correction): `voice_typing/ime/target.py` (ImeTarget), `manager.py` (ImeProcess),
  `ime_host.py` (JSONL host), `protocol.py`. Takeover: M4.T4.S1 `8d8b439` — grab lives in the
  host (`grab` cmd → `zwp_input_method_keyboard_grab_v2`; grabbed keys arrive as `grab_key`
  events and are NOT forwarded to the app); the revocation POLICY is daemon-side in
  `voice_typing/ime/takeover.py` (read it for the exact TakeoverWatch API; unit tests in
  `tests/test_ime_takeover.py` show `halt_for_takeover(reason)` consumption).
- **Parallel sibling (P1.M5.T2.S1)** — in flight; produces `tests/pi_g3_row_{lab,support}.py`,
  `tests/test_pi_g3_row_support.py`, `architecture/g3_pi_prompt_row.md`. NO file overlap with
  this item; both labs boot their own disposable desktop (xvfb-run -a picks a free display).
- Matrix re-run (M4.T5.S2) `34dca3b`: `architecture/g3_field_matrix.md` — gtk full, foot/kitty
  insert-only, ghostty blocked, Hyprland relay blocked (never attempt nested Hyprland).

## 2. Harness digest (tests/ime_g3_lab.py)

- **Gate + run line**: `GATE_ENV = "IME_G3_LAB"`; docstring: `timeout 300 env IME_G3_LAB=1
  .venv/bin/python tests/ime_g3_lab.py`. Without the env var: print skipped, exit 0. Exit
  codes: 0 all pass, 1 any row fail, 2 gate misuse.
- **Boot (two-phase)**: outer re-exec under `xvfb-run -a` + `dbus-run-session
  --config-file=<private bus config>`; disposable root = ONE TemporaryDirectory (PREFIX
  `ime-g3-lab-`) holding HOME/XDG_RUNTIME_DIR/TMPDIR; `start_desktop()` writes sway.conf,
  spawns `sway -c <conf>` (WLR_BACKENDS=x11, pixman renderer), polls
  `root/sway-ipc.*.sock` (≤7 s), exports SWAYSOCK/WAYLAND_DISPLAY into lab.env; teardown
  killpg's spawned session groups; never pattern-sweeps.
- **Lab class**: `spawn(args, stderr_name=...)` (DEPRAVNULL stdio), `cmd(args, timeout=5)`
  (bounded subprocess), `focus(criteria)` (`swaymsg -r <criteria> focus`), `verdict(row, ok,
  sub, checks, t_ms, **kw)` → JSON verdict line mirrored to `<root>/verdicts.jsonl`,
  `shot(name)` (grim screenshot, optional), `teardown()`, `err_head(name)`.
- **Field spawn**: SYSTEM python3 (`shutil.which("python3")` — the venv has NO `gi`);
  `python3 tests/ime_g3_field_gtk.py <root> [--readonly] [--tag NAME]`; ready flag =
  `field{suffix}.ready` file (≤8 s poll); window title `imlab-g3-field-gtk`.
- **Field dump protocol** (atomic `field{suffix}.tmp` + `os.replace` → `field{suffix}.json`):
  `{seq, cseq, kind, text, pos, t, frames, activated, keys, editable, gtk, pygobject,
  ring_rle, dump_capped}`; 2000-dump cap; RING_MAX=256 per-frame samples, RLE_CAP=64 pairs
  per dump. Frame oracle: `add_tick_callback` on the entry samples `(sha1(text)[:8], pos,
  cseq, t)` every painted frame; a dump also fires on tick when the text hash changed
  (kind="frame"). `activated` = Enter counter (must stay 0), `keys` = received-key counter
  (must stay 0 — IM commits generate zero key events).
- **Adapter**: `ImeProcess(log_path=<root>/ime_host.jsonl, on_event=collector)`; `.spawn(
  timeout=15)`; readiness = host log exists + contains "globals"; `proc.request(cmd,
  timeout=…, **fields)`; `ping` → `{activated, dones}`. Host event log EventLogWriter-capped
  64 KiB. ImeTarget(proc): `acquire() -> AcquireResult`; `recheck(binding,
  inserted_bytes=0) -> (bool, str, int)`; `show(session, utterance, seq, expected_revision,
  span) -> ShowResult` (render-equal → UNCHANGED zero events; >4000 B delta → REFUSED never
  chunked; INSERT vs CORRECTION by prefix; correction verifies `_owned_region_intact`
  BEFORE the wire); `finalize(session, utterance, seq, …)`; `leave()`; `cancel() ->
  ShowResult`. Timeouts: `_ACQUIRE_TIMEOUT_S=2.5`, `_SHOW_TIMEOUT_S=0.25`.
- **Rows R1–R5**: r1 6 short inserts (applied, byte-exact, cursor end, cseq Δ∈(1,2), oracle
  = exactly 1 text transition); r2 20-sentence span (~1544 B) + first-word correction in ONE
  commit (delete_surrounding(before=owned)+commit_string+ONE wire commit; single visible
  edit; reach ≫ utterance); r3 identical finals ×3 (UNCHANGED, cseq Δ0, dones unchanged —
  zero-diff law); r4 unicode_951b + mixed_3500b + overcap_4500b REFUSED at cap; r5 readonly
  refusing field, then a fresh writable field takes one insert (adapter not wedged).
  `_verify_agrees()`: GTK caps surrounding_text near the cursor (~3999 B measured) →
  agreement asserted on the byte-exact SUFFIX when snapshot < field.
- **Payloads (ime_g3_support.build_payloads())**: keys `short` (list), `twenty_committed`
  ("Thier " + 20 sentences — first word deliberately wrong), `twenty_corrected` ("Their …"),
  `unicode_951b` (951 B multilingual, paste-lab lineage), `mixed_3500b` (3500 B),
  `overcap_4500b` (4500 B, contains \n, never applied). `single_edit_analysis(before, after,
  expect=…)` = the frame-oracle verdict helper; `text_hash8(text)`; `ROW_STATUSES =
  ("untested","insert-only","blocked","verified")`; `row_status(…)` mapper;
  `render_report(versions, rows, meta)` bounded MAX_REPORT_LINES=150, evidence cap 8/row.
- **Report format** (`g3_gtk_rows.md`): date/HEAD/command header, live versions (kernel,
  sway, gtk, pygobject), the R.7 G3 quote verbatim, the "A G2 pass never marks a row
  verified" banner, a `| row | pass | status |` table, then one evidence section per row.
- **bulk_delivery.py**: `ShowResult` (applied|unchanged|refused|unknown), `AcquireResult`,
  `TargetUnits` enum, `map_span(text, start_char, end_char, units)` — use the UTF-16 member
  for DOM cursor math (JS strings are UTF-16 code units); `rendered_equal(old, new)`.

## 3. App inventory on this box (checked this session)

- `/usr/bin/chromium` = **Chromium 158.0.8127.36** (Arch). `/usr/bin/firefox` = **Firefox
  160.0.1**. `code` (VS Code, Electron/Chromium IM class — redundant with the browser row,
  heavy under pixman sway).
- NO gedit / gnome-text-editor / kate / mousepad / epiphany. M4.T5.S1 precedent:
  "gtk4-demo/gtk3-demo are MISSING on this box — hand-written field apps only." → the
  graphical-editor row = a hand-written **Gtk.TextView** editor app (the document-editor
  widget class real GTK editors are built on — a genuinely different IM consumer from
  Gtk.Entry: buffer-based, preedit-in-view, its own surrounding-text path).
- pyproject deps: no websocket/requests libs → the browser witness must be dependency-free
  (HTTP push + document.title channels, below).

## 4. Design decisions

1. **Graphical editor row** = fork of `tests/ime_g3_field_gtk.py` into
   `tests/ime_g3_field_edit.py`: Gtk.TextView in a ScrolledWindow, buffer `changed` signal,
   cursor = `buffer.get_iter_at_mark(buffer.get_insert()).get_offset()` (chars), same dump
   schema/atomic-write/ready-flag/dump-cap, frame oracle via add_tick_callback on the view,
   `keys` counter via EventControllerKey, `activated` repurposed as Enter-press counter
   (still must stay 0), `--readonly` → `set_editable(False)`. Title `vtg3-editor`.
2. **Browser row** = real Chromium 158 in the SAME disposable sway, loading a repo HTML
   fixture with a real DOM `<input>` (autofocused — no synthetic click needed; DOM focus is
   what triggers text-input enable). Flags: `--ozone-platform=wayland --enable-wayland-ime
   --wayland-text-input-version=3 --user-data-dir=<root>/chromium-profile --no-first-run
   --no-default-browser-check --disable-gpu --password-store=basic`. App-side witness = the
   page's OWN JS: on every `input`/`selectionchange`/keydown + 200 ms heartbeat it POSTs
   full state JSON (`text/plain`, no preflight) to a lab-owned `127.0.0.1` HTTP server
   (ACAO:* → works from file:// null origin): `{n:inputEvents, k:keyEvents, sel:[s,e],
   len, text (≤8 KiB), ring: last-32 (beforeHash,afterHash,lens), frames: last-64 rAF
   value-hashes, f:frameCount}`. Fallback channel if fetch is blocked: `document.title`
   (counts + hashes only, ≤~200 chars) read via `swaymsg get_tree`. Event-count law on a
   browser: insert=1 input event, correction=1 input event with (before→after) matching the
   full delta, zero-diff=0 input events; no intermediate value hashes in the rAF ring.
3. **Contingency**: if Chromium never activates text-input (blocked at activation), ONE
   bounded Firefox sub-row may be attempted (MOZ_ENABLE_WAYLAND=1, same fixture, title
   channel) before declaring the class blocked; otherwise Firefox records `untested`.
4. Both classes ride the IM-v2 adapter (the item's INPUT contract); rows mirror R1–R5 +
   a live takeover leg (xdotool real key mid-owned-fragment → host `grab_key` event →
   takeover detector `halt_for_takeover` exactly once → next op refused, field counters
   frozen). Insert-only for the browser is a LIKELY legitimate outcome (whether Chromium's
   text-input-v3 client sends surrounding_text / honors delete_surrounding_text is exactly
   what this row measures — no prior evidence exists in R.2's matrix).

## 5. External references (web search 2026-11-24)

- Chromium ozone-wayland text_input_v3 support tracker: https://issues.chromium.org/40113488
- Flag combo in the wild (135+ requires the text-input-v3 flag for IME on ozone/wayland):
  https://github.com/brave/brave-browser/issues/45183
- `--ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3`:
  https://discourse.nixos.org/t/ibus-not-working-with-electron-apps/64128
- Without `--enable-wayland-ime` the IME pipe never initializes even in Wayland mode
  (Arch wiki summary hit; verify flags at runtime, record `chromium --version`).

## 6. Gotchas (beyond §2)

- One ImeProcess per seat (input-method singleton: "another input method holds the seat").
  Rows share the adapter; `leave()` between rows; re-acquire per field.
- Sway focus ≠ DOM focus for Chromium: the fixture autofocuses the input (page JS
  `focus()`), which is what drives text-input enable; the lab still `swaymsg focus`es the
  window before acquire.
- UTF-16 vs UTF-8 vs chars: DOM cursor/length = UTF-16 units; GTK TextView pos = chars;
  adapter/verify = bytes. All expected offsets via `bulk_delivery.map_span`; never len().
- Chromium under WLR_RENDERER=pixman sway: `--disable-gpu`; user-data-dir MUST live in the
  temp root (isolation — never the real profile); `--password-store=basic` avoids keyring
  D-Bus hangs. Record app_id (usually `chromium`) + window title from get_tree.
- Grabbed keys do NOT reach the app (host comment, im-lab row O): during the takeover leg
  the field `keys` counter must NOT move — the grab consumed the key; the `grab_key` event
  in the host log is the takeover evidence.
- All waits bounded (`until()`); every subprocess under GNU timeout; EXIT trap removes the
  temp root (tmpfs = RAM); scratch caps: dumps ≤2000, pushes ≤256×8 KiB, verdicts.jsonl
  per-row lines, report ≤150 lines (render_report enforces).
- Adds-only fences: do NOT touch ime_g3_lab/field/support/matrix files, voice_typing/**,
  pi_g3_row_* (S1 in flight), pyproject, .gitignore, config.toml.

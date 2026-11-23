# im-lab Pattern Research — PRP Input (P1M4T5S1)

Self-contained structural notes on `tools/im-lab/` (§4.2sexies bulk-text-delivery capability spike,
Rev 4 pre-implementation). Source of truth: the 8 files read in full; nothing here requires re-reading
them for structural facts. Verbatim excerpts are included where they are copy-paste starting points.

---

## 0. Repo map & roles

| File | ~LOC | Role |
|---|---|---|
| `imlab_run.py` | ~430 | Orchestrator: disposable desktop + scripted rows + verdicts |
| `wlwire.py` | ~210 | Stdlib-only Wayland wire client (no pywayland) |
| `im_probe.py` | ~200 | Becomes the seat input method; JSON ctl socket; event log |
| `field_gtk.py` | ~60 | GTK4 `Gtk.Entry` state dumper (atomic field.json) |
| `field_term.py` | ~60 | GNU-readline line dumper inside terminal under test |
| `globals.py` | ~55 | Passive registry listing (no binds) |
| `hypr_nest.py` | ~170 | Same rows against nested Hyprland (failed to boot — see §7) |
| `README.md` | — | Results (29 rows / 24 pass, 2026-11-22), route decision |

---

## 1. `imlab_run.py` — the runner

### Boot chain (outer → inner)

Entry: `main()` with **no args** (or `--keep DIR`). Two-phase re-exec:

1. Outer (host) phase:
   - `tempfile.TemporaryDirectory(prefix="imlab-")` — disposable root; auto-removed unless `--keep DIR`
     (keep copies only `*.png`, `im.jsonl`, `gtk.err`, `verdicts.jsonl` out).
   - Writes `<root>/private-bus.conf` (hand-rolled dbus-daemon config: session bus, `unix:tmpdir=<root>`,
     allow-all policy) — **not a bare `dbus-run-session`; it uses `dbus-run-session --config-file=`**
     so the bus socket lives in the disposable dir.
   - Fixed env dict (exact, from source):
     ```python
     env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": folder, "XDG_RUNTIME_DIR": folder,
            "XDG_CONFIG_HOME": folder, "TMPDIR": folder, "GDK_BACKEND": "wayland", "WLR_BACKENDS": "x11",
            "WLR_LIBINPUT_NO_DEVICES": "1", "WLR_RENDERER": "pixman", "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_SHADER_CACHE_DISABLE": "true",
            "XDG_SESSION_TYPE": "wayland", "LANG": "C.UTF-8", "GTK_A11Y": "none", "GIO_USE_VFS": "local"}
     ```
   - Launch: `xvfb-run -a dbus-run-session --config-file=<bus.conf> -- python3 imlab_run.py run <folder>`
     with `sp.run(..., timeout=140)` as the outer hard stop.
2. Inner (`run(root)`) guards itself: refuses unless `root == $XDG_RUNTIME_DIR == $HOME`,
   `root.name.startswith("imlab-")`, and `$WLR_BACKENDS == "x11"`.

### Desktop start (`start_desktop(lab)`)

- `sway.conf` = `xwayland disable\nfocus_follows_mouse no\n` (2 lines, written to root).
- `lab.spawn(["sway", "-c", conf])` — Sway **x11 backend on the Xvfb display** (`xvfb-run -a` picks a free
  display; `-a` = auto display number, so no hardcoded `:99`).
- Readiness: `until(...)` polls (20 ms tick) for `<root>/sway-ipc.*.sock` (7 s) then sets `SWAYSOCK`;
  polls `root.glob("wayland-*")` for a socket → `WAYLAND_DISPLAY` (7 s). Fails fast if sway died.
- Focus via real X tools: `xdotool search --onlyvisible --maxdepth 1 --name '.*'` → `xdotool windowfocus`.
- Spawns `im_probe.py <root>` (stderr → `im_probe.err`), waits 7 s for `<root>/ctl.sock`, then connects
  a `socket.AF_UNIX/SOCK_STREAM` to it → `lab.ctl`.

### Cleanup / traps

- `SIGTERM` handler in inner phase: `sys.exit(143)` — so the outer GNU `timeout -k 2 150` kills cleanly.
- `run()` has `finally: lab.teardown()`. `Lab.teardown()`:
  - `ctl_send({"cmd":"quit"})` (best-effort) then closes the ctl socket;
  - iterates `self.procs` **in reverse** (newest first), `os.killpg(p.pid, SIGKILL)` (procs were spawned
    with `start_new_session=True`, so each has its own pgid), then `p.wait(timeout=2)`.
- No other signal traps; the TemporaryDirectory context manager removes the root.

### Evidence writing (paths, format, bounding)

- `verdicts.jsonl` — one JSON object per row, appended; each verdict also printed to stdout
  (`print(json.dumps(v, ensure_ascii=False), flush=True)`). Unbounded in count but rows are finite.
- `im.jsonl` — probe event log, **hard-capped at 64 KiB** (`LOG_CAP = 64 * 1024` in im_probe.py; log()
  silently drops lines once `log_bytes >= LOG_CAP`).
- `field.json` / `term.json` — atomic state dumps, capped at `MAX_DUMPS = 2000` writes each.
- Screenshots via `grim` → sha256[:16] hash pairs for stability checks (stable = two identical shots).
- `*.err` files per spawned process (`im_probe.err`, `gtk.err`, `term-<tag>.err`).
- `err_head(name, n=300)` truncates stderr when embedding into verdicts.

### CLI flags

Only `[--keep DIR]`. No other flags. Usage line in README:
`timeout -k 2 150 python3 tools/im-lab/imlab_run.py [--keep DIR]`.

### Rows and execution

Rows are just sequential Python blocks, each ending in `lab.verdict(row, ok, **kw)`:
- `A globals`, `B gtk-boot`, `B gtk-insert`, `C gtk-correct`, `D gtk-preedit`, `D2 gtk-preedit-clear`,
  `D3 gtk-preedit-final`, `E gtk-zero-diff`, `F gtk-unicode`, `G gtk-951B`, `G2 gtk-whole-span-correct`,
  `H gtk-surrounding-text` (function `gtk_rows`);
- per-terminal (`term_rows`): `{tag} text-input`, `insert`, `insert-via-preedit`, `correct`, `preedit`
  for tags `I foot`, `K kitty`, `L ghostty` (spawn args / app_ids:
  `foot -T imlab-foot` / `foot`; `kitty --class imlab-kitty` / `imlab-kitty`;
  `ghostty --gtk-single-instance=false --shell-integration=none -e` / `com.mitchellh.ghostty`);
- `O grab-takeover`, `O2 grab-no-self-trigger` (`grab_rows`, run only if GTK field re-activates).
- Each block wrapped in try/except → `verdict("<tag> block", False, error=repr(e))` — one bad block
  never kills the run. Terminals are SIGKILLed (killpg) after their rows.

### Result aggregation & exit codes

Final line: `{"rows": N, "passed": P, "failed": F, "failed_rows": [...]}`; `raise SystemExit(1)` if any
`pass is False`. Outer timeout prints `{"row":"harness","pass":false,"error":"outer timeout"}`.
README records the final run: **29 rows, 24 pass** (5 failures = capability findings: foot/kitty correct
ignored, foot surrounding-text none, ghostty insert/preedit dead). Runtime: README says **~90 s bounded**
(outer budget 150 s / inner 140 s).

### Key Lab helpers (copy-paste surface)

- `until(probe, seconds=3)` — 20 ms-tick poll returning first truthy probe result (None on timeout).
- `wait_field(pred, seconds=3, field="field.json")` → `(state|None, ms)` — polls the JSON dump.
- `wait_log_since(base, pred, seconds=3)` — scans `im.jsonl` rows from index `base`.
- `ctl_send(payload)` → JSON reply over the unix socket, 3 s select-based read timeout.
- `focus(criteria)` — `swaymsg <criteria> focus` + poll `focused_app_id` (parses `swaymsg -t get_tree`,
  walks `nodes`/`floating_nodes` for `focused`, returns `app_id` or `name`).
- `shot(name)` — `grim` screenshot + sha256[:16].

---

## 2. `field_gtk.py` — the GTK4 field

- `gi.require_version("Gtk", "4.0")`; `Gtk.Application(application_id="org.imlab.field")`;
  window titled `imlab-field-gtk` (this exact title is the sway focus criterion).
- One `Gtk.Entry(hexpand=True, placeholder_text="spike field", width_request=600)` in a vertical
  `Gtk.Box` with `margin_top=40`.
- **Signals connected (only two):**
  ```python
  entry.connect("changed", lambda e: dump("changed", e))
  entry.connect("notify::cursor-position", lambda e, _p: dump("cursor", e))
  ```
- **State-dump protocol:** write JSON to `<root>/field.tmp` then `os.replace(tmp, root/"field.json")`
  (atomic rename). State schema:
  ```python
  {"seq": all_dumps, "cseq": changed_dumps, "kind": "changed"|"cursor",
   "text": entry.get_text(), "pos": entry.get_position(),
   "t": round(time.monotonic()*1000, 3)}
  ```
  plus optional `"preedit"` key (defined in the dump signature but never populated by current code —
  no preedit signal is actually connected).
- **Edit counting:** `cseq` increments only on `changed` (document edits); `seq` counts all dumps.
  The harness's one-edit assertions are `edits in (1, 2)` for corrections and `edits == 0` for
  preedit/zero-diff — because **GTK internally decomposes a correcting commit into delete+insert,
  firing 1–2 `changed` signals within a single commit cycle** (measured, README row C note).
- Bounded: `MAX_DUMPS = 2000`, dump() early-returns after that.
- Readiness: `GLib.idle_add(lambda: (root/"field.ready").touch() or False)` after `win.present()` —
  harness polls for `field.ready` (8 s).
- **Frame-level single-edit instrumentation** would need: (a) counting `changed` signals per commit
  cycle (already have via cseq — but it can't distinguish 1 frame from 2), plus (b) something tied to
  the render cycle — e.g. `Gtk.Entry`'s `preedit-changed` signal, a `snapshot`/`GtkWidget::compute-size`
  hook, or a frame-clock callback (`Gdk.FrameClock`/"paint" phase) recorded per cseq step, proving both
  changed emissions land inside one presentation. Currently absent; README flags exactly this as a G3
  open item.

---

## 3. `wlwire.py` — the wire client

Stdlib-only (`socket`, `struct`, `select`). No pywayland (not installed on the box).

- **Connection:** `Client()` resolves `$WAYLAND_DISPLAY` against `$XDG_RUNTIME_DIR`
  (absolute path honored), connects `AF_UNIX/SOCK_STREAM`. ID allocation from `next_id=1`
  (`wl_display` is id 1), `ifaces: dict[id→name]`, id-space cap `0xFF000000`.
- **Opcode tables** `REQUESTS` / `EVENTS` are literal `(name, arg-kind-string)` lists where
  **opcode = list index**; arg kinds `u/i/s/o/n/h`. Covers exactly: `wl_display`, `wl_registry`,
  `wl_seat`, `zwp_input_method_manager_v2`, `zwp_input_method_v2`, `zwp_input_method_keyboard_grab_v2`.
  IM-v2 requests in XML order:
  ```python
  "zwp_input_method_v2": [
      ("commit_string", "s"), ("set_preedit_string", "sii"),
      ("delete_surrounding_text", "uu"), ("commit", "u"),
      ("get_input_popup_surface", "no"), ("grab_keyboard", "n"), ("destroy", "")],
  ```
  Events: `activate, deactivate, surrounding_text(suu), text_change_cause(u), content_type(uu),
  done, unavailable` and grab `keymap(uhu), key(uuuu), modifiers(uuuuu), repeat_info(ii)`.
  **Gotcha: these must match the protocol XML (Hyprland-vendored input-method-unstable-v2.xml) —
  adding any request means inserting it at the right index or every opcode shifts.**
- `request(obj, iface, name, *args)` — looks up opcode, packs payload (`wstr` = padded length-prefixed
  NUL-terminated string), header `struct.pack("<IHH", obj, opcode, size)`.
- `next_event(timeout=0.5)` — reads via `recvmsg` with `SCM_RIGHTS` fd collection (`pending_fds`);
  **keymap fds are immediately `os.close`d** (spike keeps no keymap).
- `roundtrip(timeout=5.0)` — `wl_display.sync` to a fresh `wl_callback`, pumps `next_event` +
  `handle()` until that callback fires; raises `WlError` on timeout.
- `handle()` — default handler fills `self.globals[name_id] = (iface, version)` from `wl_registry.global`
  and raises `WlError` on `wl_display.error`.
- It is a **Python API, not JSONL-driven** — the JSON command layer lives in `im_probe.py`.

### `im_probe.py` (the driver built on wlwire)

- Boot: `wl_registry.get_registry` → `roundtrip` → logs a `globals` event (`manager_v2`,
  `text_input_v3` booleans + `n_globals`). `become_im()`: binds `zwp_input_method_manager_v2` v1 and
  `wl_seat` v1, calls `get_input_method(seat, new_id)` → `zwp_input_method_v2`, then **two roundtrips**
  to drain early activate events before the ctl socket exists.
- **Command socket:** `<root>/ctl.sock`, one JSON line per command, JSON reply line. Commands:
  `state | insert{text} | replace{before,after,text} | preedit{text,begin=0,end=-1} |
  endpreedit{text=""} | grab | quit`.
- Request mapping (atomic per `commit(serial)`):
  - `insert` → `commit_string(text)` + `commit(dones)`
  - `replace` → `delete_surrounding_text(before, after)` + `commit_string(text)` + `commit(dones)`
    (protocol evaluation order: preedit-replace → delete-surrounding → insert)
  - `preedit` → `set_preedit_string(text, begin, end)` + commit
  - `endpreedit` → `commit_string("")` (or text) + commit
  - `grab` → new `zwp_input_method_keyboard_grab_v2` via `grab_keyboard` (no commit)
- Guards: every mutating cmd (except `state`) requires `self.activated` else
  `{"error": "not activated (no text-input focused)"}`. `commit` uses `self.dones` (count of `done`
  events seen) as the serial.
- Event handling → `im.jsonl` rows: `activate/deactivate/done/surrounding_text` (text, cursor, anchor,
  bytes, head=first 80 chars)/`grab_key` (keycode=ev.args[2], state=ev.args[3])/`keymap/modifiers/
  repeat_info/content_type/text_change_cause`. `unavailable` → logged then `WlError("input method slot
  taken (another IME is running)")` — the **one-IM-per-seat** collision guard.
- Main loop `serve()`: single-threaded `select.select([wayland sock, ctl listener, conn], ..., 0.2)`
  then drain remaining events with `next_event(0)`. Robust to bad commands (error reply, keep going).
- **Cursor/text assertion via surrounding_text** is done by the *harness* (row H): it triggers a field
  edit, then scans `im.jsonl` for `ev == "surrounding_text"` rows and asserts cursor/anchor/bytes —
  wlwire just decodes `surrounding_text(suu)`.

---

## 4. `globals.py` — passive probe

Connect, `get_registry`, one `roundtrip`, print. `INTEREST` tuple covers the 4 injection routes
(IM-v2/v1, text-input-v3, virtual-keyboard, data-control/clipboard, primary-selection, wl_seat).
Arg `json` prints `{"globals": [...], "text_injection": {...}}`, else a compact summary +
`total globals`. No binds of functional interfaces — safe against the live desktop.
Results: live Hyprland 0.56.2 and private Sway 1.12 advertise identical injection sets (71 vs 55 globals).

## 5. `field_term.py` — terminal-side field

Runs *inside* the pty of the terminal under test (spawned as the terminal's command). Uses GNU
readline: a 5 ms poll thread reads `readline.get_line_buffer()` and on change atomically replaces
`term.json` (`{"line","seq","t"}`), capped 2000 dumps. Touches `term.ready` before starting; writes
`term.final` on EOF. Detects: delivered bytes (line growth), bracketed-paste markers (would appear in
line), and zero-byte delivery (seq unchanged).

## 6. `hypr_nest.py` — nested Hyprland attempt

Reuses `Lab`/`until` imported **from imlab_run**. Chain: Xvfb → Sway (x11) → nested `Hyprland`
(Wayland backend on sway's socket). Waits 25 s for `hypr/<sig>/.wl_socket`, focuses via
`hyprctl --sig <sig> dispatch focuswindow class:org.imlab.field`, runs HY rows (text-input/insert/
correct/preedit/surrounding-text). Same outer env dict + `xvfb-run -a dbus-run-session` wrapper.
**Result: nested Hyprland fails to boot under software rendering (aquamarine `CBackend::create()`)**
— only advertisement (globals.py) is verified on Hyprland.

---

## 7. Hardcoded paths / pins / sleeps / gotchas

- **No hardcoded display numbers** (`xvfb-run -a`), no absolute repo paths (all `Path(__file__).parent`).
- Fixed PATH `/usr/local/bin:/usr/bin:/bin`; hard pins on behavior, not versions: sway 1.12, foot 1.28,
  kitty 0.49, ghostty 1.3.1, GTK 4, Hyprland 0.56.2 are *observed* versions in the README results,
  not enforced in code. ghostty IM path is broken at 1.3.1 (tracker: gtk-ime pending) — version watch.
- Sleeps: 0.02 poll tick; stability pairs use `time.sleep(0.4)` between `grim` shots; 0.3–0.5 s around
  preedit ops; readiness windows 2–8 s; sway socket 7 s; Hyprland socket 25 s; ctl reply timeout 3 s;
  inner `sp.run` timeout 140 s; outer recommended `timeout -k 2 150`.
- Gotchas:
  - GTK fires **1–2 `changed` signals per correcting commit cycle** → one-edit assertions must allow
    `edits in (1, 2)`; "one rendered frame" is unproven without frame-level instrumentation.
  - foot/kitty **silently ignore `delete_surrounding_text`** and never send surrounding text → correct/
    verify rows legitimately fail there.
  - Protocol **4000-byte commit cap** — larger corrections must chunk.
  - One IM per seat; user IME (fcitx5) collision → `unavailable`.
  - Row ordering: `E`/`O` rows assume the GTK field still holds text-input activation.
  - Keymap fds closed on receipt; key events under grab carry keycode only (grab row used keycode 48 = 'b').

---

## 8. Reuse assessment — turning this into a repo test harness

**Productizable (keep, promote):**
- `wlwire.py` — clean, stdlib-only, testable wire client. Promote to the real adapter's transport or a
  shared test util; extend REQUESTS/EVENTS tables as needed. This is the core value.
- `field_gtk.py` / `field_term.py` — near-ideal assert targets for tests/g3_*; add `preedit-changed`
  and frame-clock hooks for single-frame proof.
- The disposable-desktop boot recipe (env dict + private-bus.conf + xvfb-run + dbus-run-session +
  x11 sway + readiness polls) — proven ~90 s; reusable verbatim as a test fixture.
- `im_probe.py`'s event log + row-verdict conventions (jsonl evidence, cseq-based edit counting).

**Throwaway (spike-only):** `im_probe.py` as the delivery engine (its docstring says so itself),
`hypr_nest.py` (nested boot broken), `globals.py` (one-shot research, though harmless to keep as a
diagnostic).

**To drive the REAL adapter from `voice_typing/ime/` instead of im_probe.py:**
1. Extract the boot recipe from `imlab_run.main()`/`start_desktop()` into a pytest fixture
   (tests/g3_*.py style): disposable dir, private bus, xvfb+sway, `field.ready`/`ctl` readiness
   replaced by "adapter control port up" polling.
2. Replace the `lab.ctl_send({"cmd": ...})` probe protocol with whatever control surface the real
   adapter exposes (its existing daemon ctl socket or a test-only injection point); keep `field.json`
   cseq assertions as the acceptance oracle.
3. The adapter, not the harness, becomes the `zwp_input_method_manager_v2` client — so wlwire's IM-v2
   tables move into (or are vendored by) the adapter; the harness keeps only registry/diagnostic pieces
   of wlwire for `globals`-style checks.
4. Keep `until`/`wait_field`/`wait_log_since` as harness helpers; convert `verdict()` rows into pytest
   asserts + a jsonl evidence artifact under the test's tmp dir (bounded as today).
5. Handle the probe-specific guards in the adapter: `unavailable` degradation, activation gating,
   surrounding-text-driven confirmation (R.5 semantics), chunking past 4000 B.
6. Frame-level single-edit instrumentation (README open item): add `preedit-changed` + frame-clock
   recording to field_gtk before claiming "one rendered frame".

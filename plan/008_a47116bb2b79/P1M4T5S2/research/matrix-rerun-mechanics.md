# Codebase research — terminal-row + Hyprland-row re-run mechanics (2026-11-23)

Scope: what P1.M4.T5.S2 must drive, with what evidence posture, at installed versions
(pacman -Q re-confirmed today): **hyprland 0.57.2-1, sway 1:1.12-4, foot 1.28.0-2,
kitty 0.51.0-1, ghostty 1.4.0-2, gtk4 1:4.24.1-1** — drift vs the im-lab measurement set
(hyprland 0.56.2 / kitty 0.49.1 / ghostty 1.3.1) is real for kitty + ghostty + hyprland.
foot and sway are UNCHANGED (row re-run is cheap confirmation).

## 1. The measured matrix being refreshed (tools/im-lab/README.md:41-84, run 2026-11-22)

| Field | insert | correct | preedit | surrounding_text |
|---|---|---|---|---|
| GTK4 Entry | ✅ 26–40 ms | ✅ one atomic commit | ✅ zero doc edits | ✅ byte-exact |
| foot 1.28 | ✅ 20 ms | ❌ delete_surrounding silently ignored | rendered | ❌ never sent |
| kitty 0.49 | ✅ | ❌ ignored (same) | app-side | ❌ never sent |
| ghostty 1.3.1 | ❌ activates text-input, commit never reaches pty | ❌ | ❌ | ❌ |
| Hyprland 0.56.2 | advertisement only (passive registry) — relay row MISSING | | | |

## 2. How im-lab drove terminal rows (tools/im-lab/imlab_run.py)

- `term_rows(lab, spawn_args, app_id, tag)` `:289` — per terminal: spawn
  `[<term args>] + [python, field_term.py, root]` (`:297-299`), wait `term.ready` (8 s),
  focus via sway criteria (`lab.focus('[app_id="…"]')`), then:
  - **activation**: `wait_log_since(base, ev=="activate", 4)` — the IM host event log
  - **insert**: `ctl_send({"cmd":"insert","text":"hello from im"})` → wait `term.json`
    `line == "hello from im"` (APP-SIDE witness; bracketed-paste markers would appear here)
  - **insert-via-preedit** diagnostic (`preedit`+`endpreedit` cycle)
  - **correct**: `ctl_send({"cmd":"replace","before":len(" im".encode()),"text":"v2"})` →
    expect `line == "hello fromv2"` (delete_surrounding honored or not)
  - **preedit**: screenshot-hash pairs; app-saw-no-bytes via `term.json` seq unchanged
  - killpg the terminal per-row (`:351-355`)
- Terminal spawn recipes (`run()` `:387-390`): `foot -T imlab-foot` / app_id `foot`;
  `kitty --class imlab-kitty` / `imlab-kitty`; `ghostty --gtk-single-instance=false
  --shell-integration=none -e` / `com.mitchellh.ghostty`.
- `field_term.py` (56 lines): GNU readline in the terminal under test; poll thread (5 ms)
  dumps `{line, seq, t}` to `term.json` atomic-replace, capped 2000 writes; `term.ready`
  flag; final buffer to `term.final` at EOF.

## 3. The product adapter surface S2 must drive instead of im_probe

- `voice_typing/ime/manager.py` `ImeProcess`: spawn `sys.executable -m voice_typing.ime.ime_host
  [log]`, `request(cmd, timeout=…, **fields)`, `on_event` reader thread, `healthy()`,
  `stop()` killpg. Child needs repo root importable + seat env.
- `voice_typing/ime/ime_host.py` commands: `acquire/show/cancel/grab/verify/leave/ping`
  (`_dispatch :137`). **Host-level `show` does NOT require acquire** (`_show :180`):
  `if not activated → refused`; else `before` bytes → `delete_surrounding_text(before,0)`
  + `commit_string(text)` + `commit`; bounded `SHOW_CONFIRM_WAIT=0.22 s` done-bump loop →
  `applied | unknown`; wire-send failure → `unknown` (never retried, R.5).
- **Host-level `acquire` (`:156`) IS terminal-diagnostic gold**: replies
  `reason="not activated"` OR waits `_SURROUND_WAIT_S` for a pushed snapshot →
  `reason="no surrounding text"` on terminals (foot/kitty) — the reason taxonomy itself is
  matrix evidence.
- **`ImeTarget` (daemon-side policy, target.py:75) CANNOT drive terminal rows**:
  `acquire()` refuses without a surrounding-text snapshot and `show()` refuses with
  `"not acquired"` when `self._binding` is unset (`:167`). Terminal rows therefore drive the
  HOST transport directly via `proc.request(...)` — exactly the lab posture
  (tests/ime_*_lab.py speak host commands); ImeTarget stays the GTK-class surface (S1 rows).
- One-IM-per-seat: the host is the seat's only input method; `unavailable` event → host
  exits 0 → row `passed:null` (`untested (infra)`), never a false pass.

## 4. The nested-Hyprland failure — probable root cause found in hypr_nest.py

`hypr_nest.py:146-155`: `hypr_env = dict(lab.env)` — **inherits `WLR_BACKENDS=x11`** from
the disposable-desktop env (`:96`), then spawns `Hyprland` nested on sway's Wayland socket.
Aquamarine (Hyprland's wlroots successor) has NO x11 backend → `CBackend::create()` fails.
The README records "nested Hyprland failed under software rendering" but the inherited
`WLR_BACKENDS=x11` is the more precise suspect. S2's re-attempt variants, in order:
1. `WLR_BACKENDS=wayland` (drop the x11 inheritance), `WLR_RENDERER=pixman`,
   `LIBGL_ALWAYS_SOFTWARE=1`, `MESA_SHADER_CACHE_DISABLE=true` — nested Wayland backend.
2. Same but `WLR_RENDERER=llvmpipe` (drop pixman) if aquamarine rejects pixman.
3. Legacy posture verbatim (x11) — only to re-confirm the recorded failure shape.
Each attempt: ≤25 s socket wait (`hypr/<sig>/.wl_socket` glob under XDG_RUNTIME_DIR),
capture `hypr.err` head (400 B) on failure. Boot success → run GTK-field insert/correct/
preedit/surrounding rows against the Hyprland socket (drive ime_host with
`WAYLAND_DISPLAY=hypr/<sig>/.wl_socket`, focus via `hyprctl --sig <sig> dispatch
focuswindow class:…` INSIDE the disposable seat — hyprctl scoped to the private instance
signature is not the live desktop). Failure → row `blocked (nested Hyprland: aquamarine
CBackend::create … @ <variant>)` — legitimate per d2 map §9.2.
If ALL variants fail: fall back to passive live-registry listing ONLY (im-lab posture:
connect to the live socket, registry listing, no binds — tools/im-lab/globals.py) to
refresh 0.56.2 → 0.57.2 advertisement; that NEVER flips the relay row off `untested`.

## 5. S1 contract surfaces S2 reuses (plan/008_a47116bb2b79/P1M4T5S1/PRP.md)

- `tests/ime_g3_support.py` (pure, stable seam): ROW_STATUSES closed vocabulary, RowVerdict,
  `single_edit_analysis`, `build_payloads`, `render_report` (≤150-line cap), dump-hash helper.
- `tests/ime_g3_lab.py` boot pattern (two-phase re-exec, GATE_ENV=IME_G3_LAB) — S2 FORKS the
  skeleton into its own lab file (parallel-landing safety: S1 is in-flight; never edit S1's
  files). `tests/ime_g3_field_gtk.py` stays S1's GTK oracle; S2 forks `field_term.py` instead.
- S1's report `plan/008_a47116bb2b79/architecture/g3_gtk_rows.md` = the GTK-class rows of the
  refreshed matrix (S2 references, never re-runs, never edits).

## 6. Constraints pinned by the item contract + PRD

- Rows report `untested | insert-only | blocked (reason) | verified (versions + evidence)`.
- Insert-only rows NEVER run as full dictation (capability probes only — no streaming
  session, no partials cadence, nothing that could be read as G5/dictation evidence).
- Terminal verification is APP-SIDE ONLY (term.json readline buffer) — terminals never send
  surrounding_text; IM-side `verify` is evidence of its absence, not a text channel.
- OUTPUT = refreshed matrix + the ROUTE TABLE deciding whether P1.M5.T3 (clipboard
  insert-fallback) is needed at all: ghostty-class insert now working ⇒ M5.T3 records a
  skip; still dead ⇒ M5.T3 proceeds under R.6.
- No route re-discovery (R.4): IM-v2 stays primary; this re-run refreshes COVERAGE, it does
  not re-pick the route. A G2/lab pass never marks a row verified.
- Automation never exercises the live desktop/clipboard/mic/service (R.7) — the ONE
  documented exception posture (im-lab README:79-84) is a passive registry listing of the
  live Hyprland socket: connect, list globals, exit. No binds, no input, no hyprctl on the
  live instance.

# P1.M1.T1.S4 — usage-surface findings (ctl.py help + install.sh printouts)

Verified at HEAD `ae7db9f` (S1 landed; S2 daemon detach + S3 recorder detach in flight, disjoint edit sets).

## 1. Live state of the two surfaces (line map)

### `voice_typing/ctl.py` (480 lines)
| Site | Lines | Today | S4 action |
|---|---|---|---|
| Module docstring (rendered nowhere by argparse; pinned by tests) | :10-34 | Lists toggle/start/`*-block`/`*-stream`/stop/status/quit/cancel/session. `status` line advertises **"delivery (mode/state, reason/op when present)"** — the retired Rev-4 bulk status shape. No troubleshooting, no wedged-socket remedy, no keybind statement. | Reword the `status` line; add a Troubleshooting block (out-of-band stop, journal, S1 migration wording) + user-owned-keybind sentence. |
| `_COMMANDS` | :56-68 | toggle, start, stop, status, quit, cancel, session, toggle-block, toggle-stream, start-block, start-stream | UNCHANGED (no command changes in S4) |
| `_ALIASES` | :80 | `{"toggle-lite": "toggle"}` — working migration alias; undocumented in help on purpose (`test_help_surfaces_list_all_commands` forbids `toggle-lite` in help/docstring) | UNCHANGED |
| `VOICECTL_TIMEOUT` resolver | :105-112 | client-side connect+read deadline | UNCHANGED |
| `format_result` delivery fields | :170-176 | comment cites "P1.M3.T3.S2: bulk-delivery status surface (PRD §4.2sexies R.5)"; renders `delivery: stream-edit (inactive)` | Relabel comment (no "bulk" token); **rendering KEPT** (S2 Critical #3) |
| `send_command` wedged raise | :243-247 | `"daemon wedged: no reply within Ns (systemctl --user restart voice-typing to recover)"` | Keep the `daemon wedged: no reply within` prefix; make the remedy **`systemctl --user stop voice-typing`** (out-of-band), restart secondary |
| `_build_parser` epilog | :355-362 | subcommands line + per-session output-mode paragraph; **no** systemctl / stop / migration / keybind text (verified: `voicectl --help \| grep -i "systemctl\|bulk\|delivery"` → no hits) | Append: nonresponsive-socket stop, S1 migration line, keybinds-user-owned line |

### `install.sh` (213 lines; `bash -n` clean)
| Site | Lines | Today | S4 action |
|---|---|---|---|
| Header comment | :21-22 | "stdout IS the user-facing install/usage quick-start (Mode A docs). README (P2.M1.T2.S1) …" — stale plan id | Comment-only: cite P1.M2.T4.S1 |
| Step (7) status | :194-198 | `systemctl --user is-active --quiet` → "active" / "NOT active — check 'journalctl … -e'" (stderr) | Add ONE stderr line with S1's migration wording for a failed start |
| Usage block | :206-209 | `toggle\|start\|stop\|status\|cancel\|session\|quit`; block/stream examples; `voicectl cancel drops the pending fragment`; `voicectl session [--copy] … 'copied N chars'` | KEEP verbatim (the working examples the item says to keep) |
| Wedged line | :210 | `stop a wedged service: systemctl --user stop voice-typing` — **already present** | KEEP; append the "(out-of-band stop when voicectl reports 'daemon wedged')" clarifier |
| Config line | :213 | `config : $CFG_DIR/config.toml` | Append S1 migration wording (keeps a single `config :` line) |
| — | — | No shortcut/keybind/hotkey text anywhere; no "bulk" token anywhere (grep-verified) | Add the user-owned-keybind line; pin both facts statically |

### `systemd/voice-typing.service` (93 lines) — READ-ONLY
`Restart=on-failure` (:51), `KillMode=mixed` (:74), `TimeoutStopSec=15` (:85), `ExecStopPost=… ducking_heal` (:59), `WantedBy=graphical-session.target` (:93). An explicit `systemctl --user stop` is never overridden by `Restart=on-failure`, which is why it — not `restart` — is the dependable out-of-band stop. No shortcut/hotkey text in the unit.

## 2. The gap, stated precisely

1. **"Shipped shortcut" claims do not exist today** in ctl.py / install.sh / the unit (grep: shortcut|hotkey|binds|hyprland.conf → nothing user-facing). The item's "remove" therefore reduces to: say explicitly that keybinds are user-owned (PRD §4.10) and **pin** it so none can return. Descriptive "second keybind"/"two keybinds" prose in ctl.py describes the USER's own binds — keep.
2. **Stale bulk claims**: (a) the `status` help line's "delivery (mode/state, reason/op when present)" advertises a surface that is constant since S2 (`stream-edit` / `inactive`); (b) the `:170` code comment names the retired experiment. The rendering itself stays (S2 Critical #3, :147-148 and :393).
3. **Wedged socket**: install.sh already shows `systemctl --user stop voice-typing`; ctl.py's runtime hint says only `restart … to recover` and `--help` says nothing. S4 makes `stop` the named out-of-band remedy in both the runtime hint and `--help`.
4. **Migration wording**: S1's message (`config.py:204-207`) is `output.delivery="bulk-text" is retired: remove the key (default "stream-edit") or set delivery = "stream-edit"`. S1 (:147-149, :267) and S2 (:280-281) both hand the reuse of this wording to S4. Neither surface carries it today.

## 3. Existing test seams (follow, don't duplicate)

- `tests/test_voicectl.py` (CPU-only, fake control socket):
  - `test_help_surfaces_list_all_commands` (≈:464-498) — every `_COMMANDS` entry must appear in `_build_parser().format_help()` **and** `ctl.__doc__`; `toggle-lite`/`start-lite` must appear in neither.
  - `test_cancel_in_commands_docstring_and_epilog` (≈:500-510) — `_COMMANDS` exact tuple; `cancel` in docstring + epilog.
  - `test_format_cancel_renders_listening_on_and_off` (≈:512).
- `tests/test_systemd_unit.py`: an install.sh path helper (≈:60-64, `Path(__file__).resolve().parent.parent / "install.sh"`) and `test_install_sh_offline_grep_and_summary` (:201-215) — **static text assertions on install.sh**; the precedent for never executing the installer in tests.
- Baseline this session: `tests/test_voicectl.py tests/test_voicectl_session.py` → **59 passed in 4.74s**. Record `tests/test_systemd_unit.py`'s count before editing.

## 4. The usage-baseline contract (output for P1.M1.T2.S5)

A voicectl command is fully "published" only when it appears in FOUR places: (1) `_COMMANDS` (ctl.py:56-68); (2) the module docstring Subcommands block (:13-29); (3) the argparse epilog `subcommands:` line (:356); (4) install.sh's `usage  :` line (:206). `test_help_surfaces_list_all_commands` sweeps (1)→(2)+(3); S4's new install.sh test pins (4) as a literal, so T2.S5 (focus-based context starts) must update that literal alongside (1)-(3).

## 5. Handoff to the final README sync (P1.M2.T4.S1) — NOT S4's edit

`README.md` still carries the retired experiment: `## Bulk text delivery (opt-in, experimental)` (:230), `:233` ("remains opt-in and unverified"), `:248`, `:258` (`delivery: bulk-text (inactive|active|unsupported|fault)`), `:262`; 28 case-insensitive hits for bulk|shortcut|keybind in total; sections `## Dictation commands and optional shortcuts` (:80) and `## Troubleshooting` (:436) need to mirror S4's final wording. ctl.py's epilog/docstring point at "the project README for the full usage table" — that pointer stays; the README is what changes.

## 6. Validation recipe decisions

- **Static over execution** for install.sh: the full script restarts the user's unit, runs `uv sync`, prefetches models and writes a launcher symlink → never run. Assert on file text; plus an OPTIONAL render of ONLY the step-(7) print tail (`sed -n '/^# --- (7) print usage/,$p'`) with a 2-line `systemctl` stub (`exit "${SYSTEMCTL_STUB_RC:-0}"`, no `exec` → no recursion vector), `PATH` prepended for that one `bash` call only, `mktemp -d` + `EXIT` trap.
- **Behavior gate for the wedged hint**: in-process, fake unix socket that accepts and never replies, `VOICECTL_TIMEOUT=1`, patched socket path — following the fake-socket pattern already in `tests/test_voicectl.py` (grep `wedged` there first).
- **"No installer behavior change" gate**: `git diff -U0 install.sh` changed lines must all be `#` comments or `echo` lines.

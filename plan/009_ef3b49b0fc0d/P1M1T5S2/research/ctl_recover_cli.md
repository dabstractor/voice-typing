# Research — P1.M1.T5.S2: `voicectl recover [ID]` (print native recovery text + stderr warnings)

Scope: the CLIENT surface of the §4.8.1 C recovery read. The wire reply is P1.M1.T5.S1 (contract:
`plan/009_ef3b49b0fc0d/P1M1T5S1/PRP.md`). No daemon/protocol/store code is touched here.

## 0. Contract quotes (do not re-derive)

- PRD.md:475 (§4.8.1 C): "`{"cmd":"editor-recover","id":"..."}` on a separate one-shot connection returns
  `{"ok":true,"id":"...","text":"...","truncated":false,"possibly_applied":true}` for a retained id (omitting id
  selects latest). … Return `not_found` if absent, `busy` for the active id. Bound the escaped JSON recovery reply
  separately (7 MiB including newline). **`voicectl recover [ID]` prints only text to stdout and warns of
  truncation/possible duplication on stderr; never auto-inserts.** … No durable recovery promised after daemon
  restart."
- PRD.md §4.8.1 B table: "An old daemon's unknown-command reply means unsupported."
- architecture/system_context.md (Buffer ownership and recovery): "limit *serialized* response to 7 MiB, including
  escaping and framing. Recovery is one-shot explicit read (`voicectl recover [ID]`, **no copy, stdout text only,
  warnings stderr**), non-consuming as the contract directs, entirely separate from `voicectl session [--copy]`.
  **Never automatically replay.**"
- S1 PRP handoff → this item: "send `{"cmd":"editor-recover"}` / `{"cmd":"editor-recover","id":ID}` on a fresh
  connection; ok → print `text` exactly to stdout, stderr warnings when `truncated` / `possibly_applied`; error
  not_found → exit 1 'nothing to recover'; busy → exit 1 'session still active'; invalid_request → usage."
  Failure replies are EXACTLY `{"ok": false, "error": <code>}` (no `busy: True` flag); success is EXACTLY the
  five keys. The daemon does NOT close the connection after the reply — the client owns the one-shot close.

## 1. Inputs with line anchors (HEAD 1987f27 + staged S7 work)

`voice_typing/ctl.py` (672 lines) — THE module edited:
- `_COMMANDS` :83-95 — `'session'` is the R.6 recovery surface; **`recover` is absent** → add. Comment :96-99 says
  "the six commands above" → becomes seven.
- Module docstring :1-68 — `Usage:` line :60, subcommands list :29-32 (`session` entry is the model for the
  `recover [ID]` entry).
- `format_result` :205-328 — PURE `(text, code)`; every command's stdout text comes from here; `session` branch
  :310-315 ("stdout is EXACTLY the recovered text (print adds the single terminal newline); truncation is reported
  on stderr by main(), never here"). Status branch :290-308 already prints the hint
  `unconfirmed text: voicectl recover {sid}` / `… (may already be partially typed)` — the id in that hint is the
  positional this item consumes.
- `send_command` :330-372 — ONE line out, recv(4096) loop **until `b"\n"`** (no 32 KiB assumption — a multi-MiB
  reply already arrives whole), `sock.settimeout(timeout)` bounds connect AND every recv (VT-009), OSError on
  connect failure, ValueError on wedge/empty/non-JSON. **`buf` is UNBOUNDED** — system_context.md names this
  ("unbounded one-shot reply accumulation"). Signature `(socket_path, cmd, extra=None)`.
- `_send_command_with_loading_hint` :375-400 — arm commands only (not for recover).
- `_copy_session_to_clipboard` :410-462 — the ONLY clipboard helper (`session --copy`); must stay untouched and
  must never be reached from `recover`.
- `_build_parser` :465-522 — ONE optional positional `cmd` (`nargs="?"`), `--copy`, `--context-stdin`; epilog
  lists "subcommands: toggle, start, stop, status, quit, cancel, session [--copy]" and a native-editor paragraph
  (:498-500) that already says "`voicectl recover` is the explicit read".
- `main` :525-667 — usage errors → 64 BEFORE socket I/O (`--copy` with non-session :563-565; `--context-stdin`
  with non-arm :568-573); socket resolve → 2; OSError → 2; ValueError → 1 (+ the T2.S5 "outcome unknown — not
  retried" hint :605-614); old-daemon detection = `error.startswith("unknown command")` :618-629 (T2.S5 pattern);
  wire-cmd remap pattern (`start --context-stdin` → wire `start-context`) :590-607; `session` stderr-only
  truncation warning :646-658; final `print(text)` :665.

`voice_typing/daemon.py`: unknown cmd reply = `{"ok": False, "error": f"unknown command: {cmd!r}"}` :5114 → for
this item the text is `unknown command: 'editor-recover'`. `MAX_RECOVERY_REPLY_BYTES = 7 << 20` arrives with S1.

`voice_typing/editor_protocol.py`: `is_uuid_v4` (T3.S2, landed) — the ONE validator; the daemon uses the same in
S1's shape check, so client and daemon agree on what a valid id is.

`install.sh` :191-215 — the "[Mode A]" printed quick-start (stdout IS the user-facing usage). `usage :` line :207
`toggle|start|stop|status|cancel|session|quit`; :210 is the `session [--copy]` explanation line to sit the
`recover [ID]` line next to. Pure `echo` lines — no logic.

`tests/test_voicectl.py` — harness to copy: `_StubDaemon` :195 (duck-typed daemon, `calls` list, canned
replies), `running_server` fixture :247 (ControlServer on a tmp socket, `XDG_RUNTIME_DIR` → tmp_path),
`ctl.main([...])` + `capsys.readouterr()` + exit-code asserts; session tests :622-731 are the 1:1 model
(`test_main_session_truncation_warns_on_stderr` :665, `test_main_copy_flag_requires_session` :722).
`tests/test_voicectl_session.py` — daemon-side session reply tests (keep green; untouched).
`tests/G1_BASELINE.md` — test_daemon.py legacy reds (set-diff rule).

Downstream: P1.M2.T1.S5 (Pi actions) and P1.M2.T2.S4 (Neovim actions) show the PRD's warning
"Unconfirmed text: `voicectl recover <id>`" — they only need: the command name, optional positional UUIDv4 id,
stdout = text + one newline, exit 0/1/2/64, warnings on stderr. tasks.json T5 description: "Add the bounded
one-shot recovery API and CLI, separate from ordinary session recovery and clipboard copy."

## 2. Design decisions

1. **Argparse**: second optional positional `id` (`nargs="?"`). `id` with a non-`recover` command → 64 ("an id
   applies only to the 'recover' command"); `recover <non-UUIDv4>` → 64 — both BEFORE socket I/O, mirroring
   `--copy`/`--context-stdin`. Side effect: `voicectl status <x>` now returns 64 (argparse used to SystemExit(2),
   colliding with daemon-not-running) — an improvement; three positionals still hit argparse (pre-existing).
2. **Flags**: `recover --copy` and `recover --context-stdin` are already rejected by the existing checks (cmd !=
   "session" / not an arm command) → pin with tests, no new code. `session --copy` is byte-identical.
3. **Wire**: plain `send_command(socket_path, "editor-recover", extra={"id": sid} if sid else None)` — no
   loading hint (not an arm), one call, never retried (the T2.S5 "UNCERTAIN — not retried" wording on timeout).
4. **Bounded reply**: `send_command` gains a keyword-only `max_reply_bytes: int | None = None`; after each
   `buf.extend(chunk)`, `len(buf) > max_reply_bytes` → ValueError (fixed text, no content) → exit 1. Default
   None keeps every other command byte-identical. `recover` passes `daemon.MAX_RECOVERY_REPLY_BYTES` (7 MiB incl.
   newline — S1's constant, imported beside `_default_control_socket_path`; a test asserts parity).
5. **Strict reply**: the five keys must be present with exact types (str/str/bool/bool); extra keys ignored
   (forward-compat, like status); `id` must equal the requested id when one was given (never print another
   session's words). Any violation → exit 1 "malformed recovery reply" (fixed reason code; never values).
6. **Rendering**: a PURE `format_recovery(response, requested_id) -> (stdout_text, stderr_lines, code)`, used
   only by the `recover` branch — `format_result` is untouched (its error branch would put text on stdout).
   Stdout is `text` + the single `print` newline (session precedent); nothing else ever reaches stdout.
7. **Exit mapping**: ok → 0 (even when warnings are printed); `not_found` → 1 "nothing to recover";
   `busy` → 1 "still active"; `invalid_request` → 1 (argv was already validated client-side → a daemon/client
   mismatch, not the user's usage error — deliberate refinement of S1's handoff line); `unknown command …` → 1
   "this daemon predates native recovery (editor-recover) — update voice-typing and restart the unit; nothing
   was read" (T2.S5 pattern); other errors → 1; OSError → 2 (unchanged path).
8. **Warnings (ok path, stderr, before stdout)**: `truncated` → "TRUNCATED — some unconfirmed words were not
   retained (recovery keeps at most 1 MiB per session)"; `possibly_applied` → "may already be (partially)
   inserted in the editor — check for duplication before pasting; nothing was re-inserted".
9. **No side effects**: no `_copy_session_to_clipboard`, no subprocess, no typing, no clipboard, no retry, no
   cache; `session [--copy]` path unchanged. Tests patch the clipboard helper and `subprocess.run/Popen` to raise.
10. **Docs [Mode A]**: ctl.py module docstring (subcommand entry + `Usage:`), `_build_parser` epilog ("subcommands"
    line + an "ordinary copy vs explicit recovery" sentence), `cmd` positional help, `_COMMANDS` comment;
    install.sh printed help (`usage :` line + one explanation `echo`). README is P1.M2.T4.S1 (out of scope).

## 3. Harness facts
- Run tests with `.venv/bin/python -m pytest` (zsh aliases shadow `python3`); everything under `timeout`.
- `ctl.main([...])` never raises on the usage path; `capsys` separates stdout/stderr. `monkeypatch.setattr(ctl,
  "send_command", fake)` is the cheapest way to pin wire args + count calls (no retry).
- `install.sh` must NEVER be executed (it installs/restarts the user unit): `bash -n install.sh` only.
- `voicectl --help` exits 0 inside argparse before any socket — safe under `timeout 15` for the L3 check.
- pyproject has `[tool.pytest.ini_options]` only — ruff/mypy are not configured ("skipped" unless Task 0 finds them).
- External research: not needed — the feature is a print layer over an internal protocol whose grammar is fully
  specified by PRD §4.8.1 C and the S1 contract; argparse `nargs="?"` + `RawDescriptionHelpFormatter` are already
  in use in this file.

# PRP — P1.M1.T5.S2: Print native recovery text and stderr warnings (`voicectl recover [ID]`)

## Goal

**Feature Goal**: add the explicit, read-only recovery command PRD §4.8.1 C names — `voicectl recover [ID]` — to
`voice_typing/ctl.py`. It opens ONE fresh control-socket connection, sends `{"cmd":"editor-recover"}` or
`{"cmd":"editor-recover","id":"<UUIDv4>"}` (the P1.M1.T5.S1 wire contract), reads ONE **bounded, strictly
validated** reply, prints the recovered text — and nothing else — on **stdout**, prints warnings about truncation
and possible prior insertion on **stderr**, and exits. It never retries, never replays/re-inserts, never copies to
the clipboard, never touches the typing backend, and is entirely separate from `voicectl session [--copy]`
(which stays byte-identical).

Reply → behaviour (daemon contract, P1.M1.T5.S1):

| daemon reply | stdout | stderr | exit |
|---|---|---|---|
| `{"ok":true,"id","text","truncated":F,"possibly_applied":F}` | `text` + `\n` | — | 0 |
| same, `truncated:true` | `text` + `\n` | truncation warning | 0 |
| same, `possibly_applied:true` | `text` + `\n` | possible-duplication warning | 0 |
| `{"ok":false,"error":"not_found"}` | — | "nothing to recover …" | 1 |
| `{"ok":false,"error":"busy"}` | — | "session … still active …" | 1 |
| `{"ok":false,"error":"invalid_request"}` | — | "daemon rejected … invalid_request" | 1 |
| `{"ok":false,"error":"unknown command: 'editor-recover'"}` (old daemon) | — | "this daemon predates native recovery … update … nothing was read" | 1 |
| malformed / wrong-shape / other-session `id` / over-cap line / wedge | — | fixed reason, never reply values | 1 |
| socket absent / refused / `XDG_RUNTIME_DIR` unset | — | existing "daemon not running" text | 2 |
| bad argv (`recover abc`, `status <id>`, `recover --copy`, `recover --context-stdin`) | — | usage text | 64 |

**Deliverable** (2 files edited, 1 new test file):
1. `voice_typing/ctl.py` — `"recover"` in `_COMMANDS`; optional positional `id`; `_RECOVERY_REPLY_MAX_BYTES`
   (= the daemon's 7 MiB constant, imported); `send_command(..., *, max_reply_bytes=None)` bounded read;
   pure `format_recovery(response, requested_id) -> (stdout_text, stderr_lines, exit_code)`; the `recover`
   branch in `main()` (usage checks before any I/O → one `send_command` → render → stderr then stdout → code).
   [Mode A] usage docs: module docstring, `_build_parser` epilog + positional help, `_COMMANDS` comment.
2. `install.sh` — [Mode A] printed help ONLY: the `usage :` line gains `recover`, plus one explanation `echo`
   line distinguishing `session [--copy]` (ordinary, keyboard-typed dictation; clipboard) from
   `recover [ID]` (unconfirmed words of an ended native editor session; read-only; no `--copy`).
3. `tests/test_voicectl_recover.py` — hermetic CPU-only unit tests: mocked `send_command` (canned replies,
   call recording), `capsys` for stdout/stderr, clipboard helper + `subprocess.run/Popen` patched to raise,
   and one raw-socket listener for the > 7 MiB refusal and the > 32 KiB-but-valid reply.

**Success Definition**:
- (a) `voicectl recover` → wire `{"cmd":"editor-recover"}`; `voicectl recover <uuid4>` → wire
  `{"cmd":"editor-recover","id":"<uuid4>"}`; exactly ONE `send_command` call per invocation (no retry), plain
  `send_command` (no loading-hint wrapper).
- (b) stdout is EXACTLY the reply's `text` plus the single `print` newline — no banner, id, count or warning ever
  reaches stdout; stderr carries only the fixed warnings/errors below.
- (c) exit codes per the table; the `not_found`/`busy`/old-daemon messages name the situation and the next step;
  an `invalid_request` from the daemon exits 1 (argv was already validated client-side).
- (d) strictness: a reply missing any of the five keys, with a wrong type, or whose `id` ≠ the requested id →
  exit 1, empty stdout, "malformed recovery reply" on stderr (fixed reason words; never reply values). Extra keys
  are ignored.
- (e) bounded: `send_command(..., max_reply_bytes=7<<20)` refuses a line longer than 7 MiB (incl. newline)
  with exit 1 and empty stdout, without buffering beyond one 4096-byte chunk past the cap; the default
  (`None`) leaves every other command byte-identical.
- (f) `session [--copy]` unchanged: existing `tests/test_voicectl.py` + `tests/test_voicectl_session.py`
  green; `_copy_session_to_clipboard` is never called from `recover` (tripwire); `subprocess` never called.
- (g) usage errors (64) happen BEFORE socket resolution / stdin / any I/O: `recover <not-uuid4>`,
  `<any other cmd> <id>`, `recover --copy`, `recover --context-stdin`; `voicectl recover` with no daemon → 2.
- (h) `git diff --name-only` == `{voice_typing/ctl.py, install.sh, tests/test_voicectl_recover.py}`;
  `bash -n install.sh` clean; `voicectl --help` lists `recover [ID]`.
- (i) `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no` FAILED set == G1 CPU addendum.

## User Persona

**Target User**: the dictation user whose native editor session (Pi/Neovim adapter, P1.M2) ended with
unconfirmed words — target lost, ACK timeout, editor crash — and who saw the editor/status warning
"Unconfirmed text: `voicectl recover <id>`".
**Use Case**: run the command from a terminal (or an editor action that shells out to it exactly once), read the
words, paste/proofread them manually.
**User Journey**: editor dies → daemon ends the session and retains the unacknowledged finals → status shows
`native end: target_lost  recovery: unconfirmed text: voicectl recover <sid>` → user runs it → stderr warns
"may already be partially inserted" when an edit was attempted → stdout prints the text → user decides.
**Pain Points Addressed**: before this item the retained snapshot is on the wire (S1) but unreachable for a human;
after it, recovery is one command with honest warnings and zero risk of automatic duplication.

## Why

- PRD.md:475 (§4.8.1 C) specifies the sentence verbatim: "`voicectl recover [ID]` prints only text to stdout and
  warns of truncation/possible duplication on stderr; never auto-inserts."
- architecture/system_context.md: "Recovery is one-shot explicit read (`voicectl recover [ID]`, no copy, stdout
  text only, warnings stderr), non-consuming … entirely separate from `voicectl session [--copy]`. Never
  automatically replay." It also names ctl.py's "unbounded one-shot reply accumulation" — fixed here with a
  client-side cap for the one command whose reply can reach 7 MiB.
- S1 (parallel, lands first) hands off exactly this CLI; P1.M2.T1.S5 / P1.M2.T2.S4 (editor actions) and the
  acceptance checklist reference `voicectl recover <id>` by name.
- Scope boundary: this item is the CLIENT only. Daemon/protocol/store are S1's; README sync is P1.M2.T4.S1.

## What

### Success Criteria
- [ ] `recover` is a first-class command (`_COMMANDS`, usage, `--help`, install.sh quick-start) taking an optional
      UUIDv4 positional; the wire command is `editor-recover` on a fresh connection; one call, never retried.
- [ ] stdout = text only; stderr = fixed warnings for `truncated` / `possibly_applied` and fixed, actionable
      errors for `not_found` / `busy` / `invalid_request` / old daemon / malformed / over-cap / wedge.
- [ ] Exit codes 0 / 1 / 2 / 64 as in the table; all argv validation before I/O.
- [ ] Reply read is bounded at 7 MiB for `recover` only; strict five-key validation; requested-id match.
- [ ] `session [--copy]` and every other command byte-identical in behaviour (existing suites green).
- [ ] **Not in scope**: `voice_typing/daemon.py`, `editor_protocol.py`, `session_recovery.py` (S1);
      `format_result` internals for other commands; README (P1.M2.T4.S1); adapters (P1.M2.T1/T2); clipboard
      changes; any new env var/config; any total-deadline change to `send_command` beyond the byte cap.

## All Needed Context

### Context Completeness Check

_Pass._ The wire grammar and every reply shape come verbatim from S1/PRD; the module to edit is read in full
below with line anchors; the argparse idiom (`nargs="?"`, usage errors → 64 before I/O), the T2.S5 patterns to
reuse (wire-cmd remap, old-daemon detection, "not retried" wording), the stderr-only warning precedent
(`session` truncation), the test harness to copy, and the install.sh echo block are all pinned. The only
dependency on S1 is one constant + one validator, both verified in Task 0.

### Documentation & References

```yaml
- docfile: plan/009_ef3b49b0fc0d/P1M1T5S2/research/ctl_recover_cli.md
  why: "§0 contract quotes; §1 line anchors for every ctl.py symbol touched; §2 the ten design decisions
        (argparse positional, flags, wire, bounded read, strictness, rendering, exit mapping, warnings,
        no side effects, docs); §3 harness facts."
  critical: "§2.4 — bound ONLY the recover read (max_reply_bytes=None default); §2.5 — strict five keys +
            requested-id match; §2.7 — the exit table (invalid_request from the daemon = 1, argv errors = 64)."

- docfile: plan/009_ef3b49b0fc0d/P1M1T5S1/PRP.md
  why: "CONTRACT (lands first): request shapes {cmd: editor-recover[, id]}; success = EXACTLY
        {ok,id,text,truncated,possibly_applied}; failures EXACTLY {ok:false,error:<not_found|busy|invalid_request>};
        MAX_RECOVERY_REPLY_BYTES = 7<<20 incl. newline (code constant in voice_typing/daemon.py); the daemon
        does NOT close the connection (client owns the close); the read is non-consuming; old daemons answer
        'unknown command'. Its Task 4 handoff → this item."
  critical: "Failure replies carry NO 'busy': True flag (that belongs to generic arm replies) — key on
             error == 'busy'. The cap path can legitimately return text='' with truncated=true."

- file: voice_typing/ctl.py
  why: "THE module edited (672 lines, read in full during research). _COMMANDS :83-95 (+ 'recover'); module
        docstring :1-68 (Usage: :60, subcommands :29-32 — the `session` entry is the model); format_result
        :205-328 (PURE; DO NOT route recover through it — its error branch returns text for stdout; `session`
        branch :310-315 = the 'stdout is EXACTLY the text' precedent); status hint :290-308 already names
        `voicectl recover <sid>`; send_command :330-372 (recv(4096) loop until b'\\n' — NO 32 KiB assumption;
        buf UNBOUNDED; settimeout bounds connect+each recv); _copy_session_to_clipboard :410-462 (never from
        recover); _build_parser :465-522 (one nargs='?' positional; RawDescriptionHelpFormatter; epilog
        'subcommands:' line + native-editor paragraph :498-500); main :525-667 (usage→64 before I/O :563-573;
        OSError→2 / ValueError→1 :616-630; old-daemon detection startswith('unknown command') :618-629;
        wire-cmd remap :590-607; session stderr-only truncation warning :646-658; final print(text) :665)."
  pattern: "Follow the `session` command end to end: positional/flag validation first, one send_command, a PURE
            renderer, warnings to stderr BEFORE the stdout print, return the int code. Follow `start-context`
            for the wire-cmd remap (user-facing name ≠ wire cmd) and the old-daemon hint."
  gotcha: "`voicectl <cmd> <extra>` currently dies with argparse SystemExit(2) (collides with daemon-not-running);
           adding the positional turns the two-positional case into a proper 64 — pin it with a test. Three
           positionals still hit argparse (pre-existing, out of scope)."

- file: voice_typing/daemon.py
  why: "MAX_RECOVERY_REPLY_BYTES: int = 7 << 20 (S1) — import it beside _default_control_socket_path (ctl is
        already 'stdlib-only + the shared resolver from voice_typing.daemon'); unknown-cmd reply :5114
        {'ok': False, 'error': f'unknown command: {cmd!r}'} → the unsupported-daemon signature."
  gotcha: "S1 must have landed (Task 0 asserts the constant exists). Do NOT edit daemon.py."

- file: voice_typing/editor_protocol.py
  why: "is_uuid_v4 (T3.S2) — the ONE id validator; S1's daemon-side shape check uses the same function, so the
        client rejects exactly what the daemon would reject (before any I/O)."

- file: install.sh
  why: "[Mode A] printed quick-start :191-215: 'usage :' :207, the session [--copy] explanation :210 — add the
        recover explanation as the next echo line."
  gotcha: "NEVER run install.sh (installs/restarts the user's systemd unit). Validate with `bash -n install.sh`."

- file: tests/test_voicectl.py
  why: "Harness to copy: _StubDaemon :195 (canned replies, `calls`), running_server fixture :247 (ControlServer on
        a tmp socket; XDG_RUNTIME_DIR → tmp_path), ctl.main([...]) + capsys + code asserts; session tests
        :622-731 are the 1:1 model (truncation-on-stderr :665, --copy requires session :722)."
  pattern: "monkeypatch.setattr(ctl, 'send_command', fake) for canned replies + call recording (asserts the wire
            cmd, extra, max_reply_bytes and the call COUNT = no retry); capsys.readouterr() separates streams."
- file: tests/test_voicectl_session.py
  why: "Daemon-side session reply tests — must stay green (session --copy untouched)."

- docfile: PRD.md
  why: ":475 §4.8.1 C (sentence quoted in Why); §4.8.1 B 'An old daemon's unknown-command reply means
        unsupported'; §4.8.1 C warning string 'Unconfirmed text: `voicectl recover <id>`' that adapters show."
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Buffer ownership and recovery': one-shot explicit read, no copy, stdout text only, warnings stderr,
        non-consuming, separate from session [--copy], never replay; 7 MiB serialized limit incl. framing."
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S5/PRP.md
  why: "Source of the patterns reused here: bounded stdin read BEFORE socket I/O, wire-cmd remap, old-daemon
        'unknown command' hint, 'UNCERTAIN — not retried' wording, exit-code discipline (64 before I/O)."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/ctl.py                 # _COMMANDS :83; send_command :330; _build_parser :465; main :525        ← CODE + [Mode A] DOCS
voice_typing/daemon.py              # MAX_RECOVERY_REPLY_BYTES (S1), unknown-cmd reply :5114                   READ ONLY
voice_typing/editor_protocol.py     # is_uuid_v4                                                                  READ ONLY
install.sh                          # printed quick-start :191-215                                                  ← [Mode A] echo lines only
tests/test_voicectl.py              # CLI harness + session tests                                                   KEEP GREEN
tests/test_voicectl_session.py      # daemon-side session reply                                                     KEEP GREEN
tests/test_voicectl_recover.py                                                                                     ← CREATE
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/ctl.py
  ~ from voice_typing.daemon import (MAX_RECOVERY_REPLY_BYTES, _default_control_socket_path)
  ~ from voice_typing.editor_protocol import is_uuid_v4
  ~ _COMMANDS                      + "recover"            # and the comment "the six commands above" → seven
  + _RECOVERY_REPLY_MAX_BYTES = MAX_RECOVERY_REPLY_BYTES   # 7 MiB incl. newline — parity with the daemon cap (S1)
  ~ send_command(socket_path, cmd, extra=None, *, max_reply_bytes: int | None = None) -> dict
        # after buf.extend(chunk): if max_reply_bytes is not None and len(buf) > max_reply_bytes:
        #     raise ValueError(f"daemon reply exceeded {max_reply_bytes} bytes before its newline — refused")
        # default None → every existing caller byte-identical
  + def format_recovery(response: dict, requested_id: str | None) -> tuple[str, list[str], int]
        # PURE. (stdout_text, stderr_lines, exit_code) per the Goal table; strict five-key check; id match
  ~ _build_parser
        + parser.add_argument("id", nargs="?", help="with 'recover': the native session id (UUIDv4) …")
        ~ cmd positional help: "… | session | recover"; epilog "subcommands: …, session [--copy], recover [ID]"
        ~ epilog: one sentence "ordinary copy vs explicit recovery" (see Task 3)
  ~ main
        + after the --copy/--context-stdin checks: id-with-non-recover → 64; recover + non-UUIDv4 id → 64
        + in the step-2 try: if cmd == "recover": response = send_command(socket_path, "editor-recover",
              extra={"id": sid} if sid else None, max_reply_bytes=_RECOVERY_REPLY_MAX_BYTES)
        + in the ValueError handler: recover → extra stderr line "recovery read outcome unknown — not retried;
              the read is non-consuming, run it again"
        + step 3: if cmd == "recover": for line in stderr_lines: print(line, file=sys.stderr); print(stdout_text); return code
  ~ module docstring: `recover [ID]` subcommand entry + Usage line + "ordinary copy vs explicit recovery"
install.sh
  ~ echo "usage  : … toggle|start|stop|status|cancel|session|recover|quit"
  + echo "          (voicectl recover [ID] prints the UNCONFIRMED words of an ended native editor session — read-only, never re-inserted, no --copy; exit 1 when nothing is retained)"
tests/test_voicectl_recover.py     — unit tests (mocked send_command, capsys, tripwires, raw-socket bound tests)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — STDOUT IS TEXT ONLY. Never route `recover` through format_result(): its ok:false branch RETURNS
# "error: …" as stdout text. Use the new pure format_recovery() and print stderr_lines to sys.stderr yourself,
# then print(text) (one trailing newline, exactly like `session`). No "recovered N chars", no id, on stdout.
# CRITICAL #2 — USAGE ERRORS BEFORE ANY I/O (exit 64, BSD EX_USAGE; 2 stays exclusive to daemon-not-running):
#   recover <not-UUIDv4> → 64; <other cmd> <id> → 64; recover --copy → 64 (existing check: cmd != "session");
#   recover --context-stdin → 64 (existing check). Validate with editor_protocol.is_uuid_v4 — the SAME function
#   the daemon uses in S1 — so the client never sends what the daemon would reject as invalid_request.
# CRITICAL #3 — ONE CALL, NEVER RETRIED. Plain send_command (NOT _send_command_with_loading_hint: recover is not
# an arm). On ValueError (wedge/empty/non-JSON/over-cap) → exit 1 + "not retried" line. Do not loop, do not
# re-connect, do not fall back to `session`. A test counts send_command calls == 1 in every scenario.
# CRITICAL #4 — BOUND ONLY THE recover READ. send_command(max_reply_bytes=None) by default; `recover` passes
# _RECOVERY_REPLY_MAX_BYTES (= daemon.MAX_RECOVERY_REPLY_BYTES, 7<<20, INCLUDING the newline). Check
# `len(buf) > max_reply_bytes` right after buf.extend(chunk) — a valid 7 MiB line never exceeds it (the loop
# stops at the newline; the daemon writes exactly one line). The ValueError text carries the bound, never content.
# CRITICAL #5 — STRICT FIVE-KEY REPLY. Required: ok, id (str), text (str), truncated (bool), possibly_applied
# (bool) — use `type(x) is bool` (isinstance(True, int) tricks); extra keys are IGNORED (forward-compat, same
# as status). When an id was requested, reply["id"] MUST equal it — never print another session's words.
# Any violation → exit 1, stdout EMPTY, stderr "voicectl: malformed recovery reply from the daemon (<reason>)"
# with reason ∈ {missing key, bad type, session id mismatch} — fixed words, never values.
# CRITICAL #6 — ERROR SHAPE FROM S1 IS {"ok": false, "error": <code>} — key on error == "busy" (NO "busy": True
# flag; that flag exists only on generic arm replies). not_found / busy / invalid_request are exact codes.
# CRITICAL #7 — OLD DAEMON = "unknown command: 'editor-recover'" (daemon.py:5114). Detect with
# str(error).startswith("unknown command") (the T2.S5 idiom at ctl.py:618-629) → exit 1 + "this daemon
# predates native recovery (editor-recover) — update voice-typing and restart the unit; nothing was read".
# CRITICAL #8 — EXIT MAPPING (deliberate refinement of S1's handoff "invalid_request → usage"): argv problems
# are the USER's usage error → 64 BEFORE I/O; a daemon invalid_request AFTER valid argv is a daemon/client
# mismatch → 1. ok → 0 even with warnings; other ok:false → 1; OSError → 2 (existing path, untouched).
# CRITICAL #9 — NEVER: _copy_session_to_clipboard, subprocess, typing backend, wl-copy, a cache file, a second
# request, a "consume" flag. `session --copy` and its tests must stay byte-identical. Tests patch
# ctl._copy_session_to_clipboard AND subprocess.run/Popen to raise (tripwire).
# CRITICAL #10 — WARNINGS ARE FIXED WORDS ON STDERR, PRINTED BEFORE THE STDOUT TEXT (a `voicectl recover | pbcopy`
# user must still see them). truncated → "… TRUNCATED — some unconfirmed words were not retained (recovery
# keeps at most 1 MiB per session) …"; possibly_applied → "… may already be (partially) inserted in the editor —
# check for duplication before pasting; nothing was re-inserted". Never put the text or the id in a warning.
# CRITICAL #11 — text == "" WITH ok:true IS POSSIBLE (S1 cap path) → print "" (an empty line) and exit 0 with the
# warnings; do not "fix" it into an error — the daemon is the source of truth.
# CRITICAL #12 — ARGPARSE SIDE EFFECT: today `voicectl status foo` exits 2 via argparse ("unrecognized
# arguments"), colliding with daemon-not-running. With the new optional `id` positional it parses and main()
# returns 64 — pin it. Three positionals still hit argparse (pre-existing; leave it).
# CRITICAL #13 — SCOPE: edit ONLY ctl.py (code + [Mode A] docs), install.sh (echo lines only; `bash -n`, NEVER
# run it), tests/test_voicectl_recover.py. No daemon.py/editor_protocol.py/session_recovery.py/README/plan
# file/PRD.md/tasks.json change. S1 owns the daemon; README is P1.M2.T4.S1.
# CRITICAL #14 — AGENTS.md discipline: every command under `timeout` with the bash-tool timeout above it;
# .venv/bin/python (zsh aliases shadow python3); test_daemon.py = `timeout 500 … --tb=no`, bash ≥ 560; never run
# the live daemon; `voicectl --help` only under `timeout 15` (argparse exits before any socket); never run
# install.sh. Any tmp socket dir: mkdtemp under /tmp with an EXIT trap and a short path.
# CRITICAL #15 — SOCK TIMEOUT SEMANTICS: settimeout bounds EACH recv, not the whole reply; a pathological
# trickle could take long but can never hang (4096 B chunks, ≤ 7 MiB). A total deadline is out of scope.
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/ctl.py — additions (stdlib + the two shared symbols; no new deps)
from voice_typing.daemon import MAX_RECOVERY_REPLY_BYTES, _default_control_socket_path
from voice_typing.editor_protocol import is_uuid_v4

_RECOVERY_REPLY_MAX_BYTES: int = MAX_RECOVERY_REPLY_BYTES   # 7 MiB incl. newline (P1.M1.T5.S1)

_RECOVER_OK_KEYS = ("ok", "id", "text", "truncated", "possibly_applied")

def format_recovery(response: dict, requested_id: str | None) -> tuple[str, list[str], int]:
    """P1.M1.T5.S2 (pure; no I/O): render an `editor-recover` reply as (stdout_text, stderr_lines, exit_code).
    stdout carries ONLY the recovered text (main() adds the single newline); every warning/error is a fixed
    stderr line (never reply values). Strict: ok replies must carry id/text (str) + truncated/possibly_applied
    (bool); when an id was requested the reply's id must match. See the PRP table for the mapping."""
    if response.get("ok") is not True:
        err = str(response.get("error", ""))
        if err.startswith("unknown command"):
            return "", ["voicectl: this daemon predates native recovery (editor-recover) — update "
                        "voice-typing and restart the unit; nothing was read"], 1
        if err == "not_found":
            what = f"session {requested_id}" if requested_id else "any ended native editor session"
            return "", [f"voicectl: nothing to recover (no retained unconfirmed text for {what}; "
                        "recovery is not kept across daemon restarts)"], 1
        if err == "busy":
            return "", ["voicectl: that native editor session is still active — stop it first "
                        "(the editor's Stop or 'voicectl stop'); nothing was read"], 1
        if err == "invalid_request":
            return "", ["voicectl: daemon rejected the recovery request (invalid_request) — "
                        "re-check the session id from 'voicectl status'"], 1
        return "", [f"voicectl: recovery failed ({err or 'unknown error'})"], 1
    reason = _recovery_shape_error(response, requested_id)      # "missing key: …" / "bad type: …" / "session id mismatch" / ""
    if reason:
        return "", [f"voicectl: malformed recovery reply from the daemon ({reason}); nothing printed"], 1
    lines: list[str] = []
    if response["truncated"]:
        lines.append("voicectl: recovery text is TRUNCATED — some unconfirmed words were not retained "
                     "(recovery keeps at most 1 MiB per session); proofread against the editor")
    if response["possibly_applied"]:
        lines.append("voicectl: this text MAY ALREADY BE (partially) inserted in the editor — an edit was "
                     "attempted without a confirmed acknowledgement; check for duplication before pasting. "
                     "Nothing was re-inserted.")
    return response["text"], lines, 0

def _recovery_shape_error(response: dict, requested_id: str | None) -> str:
    """Fixed reason words only — never reply values. ok:true is checked by the caller."""
    for key in ("id", "text"):
        if key not in response:
            return f"missing key: {key}"
    for key in ("truncated", "possibly_applied"):
        if key not in response:
            return f"missing key: {key}"
    if not isinstance(response["id"], str) or not isinstance(response["text"], str):
        return "bad type: id/text"
    if type(response["truncated"]) is not bool or type(response["possibly_applied"]) is not bool:
        return "bad type: truncated/possibly_applied"
    if requested_id is not None and response["id"] != requested_id:
        return "session id mismatch"
    return ""
```

### Implementation Tasks (ordered — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT (read-only; S1 MUST have landed — else STOP and report, do not improvise its constant):
  git log --oneline -3; git status --short | head
  grep -nE "MAX_RECOVERY_REPLY_BYTES|editor-recover" voice_typing/daemon.py | head        # S1 present
  grep -nE "^def is_uuid_v4" voice_typing/editor_protocol.py
  grep -nE "_COMMANDS|def send_command|def format_result|def _build_parser|def main|nargs=|subcommands:|def _copy_session_to_clipboard" voice_typing/ctl.py
  grep -nE "choose from|_COMMANDS" tests/test_voicectl.py | head                           # any exact-list pin? update in-task
  sed -n '191,215p' install.sh
  timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_voicectl_session.py tests/test_native_recover.py -q   # green BEFORE (bash 360)
  timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -30    # baseline (bash ≥ 560)

Task 1: CREATE tests/test_voicectl_recover.py (RED first). CPU-only, no daemon process.
  Module head: `from voice_typing import ctl, daemon`; `import socket, threading, subprocess`; pytest.
  Fixtures/helpers:
    - `tripwires(monkeypatch)`: monkeypatch.setattr(ctl, "_copy_session_to_clipboard", raise_) and
      subprocess.run / subprocess.Popen → raise_ (AssertionError("recover must not spawn processes")).
    - `fake_send(canned, error=None)`: replaces ctl.send_command with a recorder: calls.append((cmd, extra, kwargs));
      returns `canned` or raises `error`. Returns the list.
  SID = "123e4567-e89b-42d3-a456-426614174000" (UUIDv4); OK = {"ok": True, "id": SID, "text": "alpha beta",
  "truncated": False, "possibly_applied": False}.
  USAGE (no I/O — fake_send raises if called; XDG_RUNTIME_DIR unset to prove no socket resolve):
   u1 main(["recover", "abc"]) → 64; stderr mentions recover + id; no send.
   u2 main(["status", SID]) → 64; "--copy"-style: "an id applies only to the 'recover' command".
   u3 main(["recover", "--copy"]) → 64; "--copy applies only to the 'session' command"; clipboard helper NOT called.
   u4 main(["recover", "--context-stdin"]) → 64; no stdin read.
   u5 (parametrized) main(["recover", "123E4567-E89B-42D3-A456-426614174000"]) (uppercase) and
      main(["recover", "123e4567-e89b-12d3-a456-426614174000"]) (version-1 nibble) → 64, no send.
      VERIFIED at research time (HEAD 1987f27): is_uuid_v4 returns False for both — it accepts lowercase
      UUIDv4 only, so the client-side check rejects exactly what S1's daemon-side check rejects.
  WIRE (fake_send):
   w1 main(["recover"]) → call == [("editor-recover", None, {"max_reply_bytes": 7 << 20})]; code 0; out == "alpha beta\n"; err == "".
   w2 main(["recover", SID]) → extra == {"id": SID}; out == "alpha beta\n".
   w3 truncated → code 0, out == "alpha beta\n", "TRUNCATED" in err, "alpha" not in err.
   w4 possibly_applied → code 0, "duplicat" in err and "re-inserted" in err; out exact.
   w5 both flags → two warning lines, in that order; out exact.
   w6 not_found (with and without id) → 1, out == "", "nothing to recover" in err.
   w7 busy → 1, out == "", "still active" in err.   w8 invalid_request → 1, "invalid_request" in err.
   w9 {"ok": False, "error": "unknown command: 'editor-recover'"} → 1, "predates native recovery" + "update" in err.
   w10 malformed (parametrized): missing text; truncated = "yes" (str); possibly_applied = 1 (int); ok reply
       with id != requested → 1, out == "", "malformed recovery reply" in err, and the canned TEXT never in err.
   w11 extra key ignored: {**OK, "final_count": 2} → 0, out exact.
   w12 empty text ok reply {"text": "", "truncated": True} → 0, out == "\n".
   w13 fake_send raises ValueError("daemon wedged: …") → 1, out == "", "not retried" in err, exactly ONE call.
   w14 fake_send raises FileNotFoundError → 2, out == "" (existing path).
   w15 count: every scenario above made exactly one send_command call (assert inside the recorder on teardown).
  PURE: format_recovery(OK, None) == ("alpha beta", [], 0); format_recovery(OK, SID) same; format_recovery(OK, OTHER_UUID)
       → ("", […"mismatch"…], 1); format_recovery({"ok": False, "error": "busy"}, SID)[2] == 1.
  SEND_COMMAND BOUND (raw listener thread on a mkdtemp socket path — EXIT trap; listener: accept, read the
  request line, write the scripted bytes, close):
   b1 valid big line: text of 150_000 chars ('"' * 150_000 → ~300 KB escaped) → send_command(..., "editor-recover",
       max_reply_bytes=7<<20) returns the dict; ctl.main(["recover"]) prints it whole (out == text + "\n").
   b2 over-cap: write b"a" * (7 << 20) + b"\n" (7 MiB + 1) → send_command(..., max_reply_bytes=7<<20) raises
       ValueError mentioning "7340032"; main(["recover"]) → 1, out == "", "exceeded" in err; finishes < 10 s.
   b3 default unbounded: send_command(path, "status") against a listener writing a 100 KB line → returns fine
       (proves the default is None and other commands are untouched).
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_voicectl_recover.py -q   → RED (bash 360)

Task 2: EDIT voice_typing/ctl.py — code (anchor by symbol):
  - imports; _RECOVERY_REPLY_MAX_BYTES; "recover" in _COMMANDS (+ comment "seven commands above").
  - send_command: keyword-only max_reply_bytes=None; the one check after buf.extend(chunk) (CRITICAL #4);
    docstring gains a line about the optional bound and that the text never carries reply content.
  - format_recovery + _recovery_shape_error exactly as in the blueprint (module level, after format_result).
  - _build_parser: `parser.add_argument("id", nargs="?", help="with 'recover': the native session id (UUIDv4) "
    "shown by 'voicectl status'")`; cmd help adds "recover".
  - main(): after the --context-stdin check:
        if args.id is not None and cmd != "recover":
            print("voicectl: an id applies only to the 'recover' command", file=sys.stderr); return _EX_USAGE
        if cmd == "recover" and args.id is not None and not is_uuid_v4(args.id):
            print(f"voicectl: invalid session id {args.id!r} — expected the UUIDv4 from 'voicectl status'",
                  file=sys.stderr); return _EX_USAGE
    step 2 (inside the existing try): if cmd == "recover": response = send_command(socket_path, "editor-recover",
        extra={"id": args.id} if args.id is not None else None, max_reply_bytes=_RECOVERY_REPLY_MAX_BYTES) — else
        the existing arm/plain dispatch unchanged. In the ValueError handler add: if cmd == "recover": print(
        "voicectl: recovery read outcome unknown — not retried; the read is non-consuming, run it again",
        file=sys.stderr).
    step 3, BEFORE format_result: if cmd == "recover": out, lines, code = format_recovery(response, args.id);
        for line in lines: print(line, file=sys.stderr); print(out); return code
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_voicectl_recover.py -q → GREEN (bash 360)

Task 3: [Mode A] DOCS — ctl.py: module docstring (subcommand entry "recover [ID]  print the UNCONFIRMED words of an
  ended native editor session (PRD §4.8.1 C) — stdout is exactly the text; warnings (truncation / may already be
  inserted) on stderr; never re-inserted, never copied; exit 1 when nothing is retained, 64 for a bad id/flags";
  Usage: line gains recover [ID]; a two-line "ordinary copy vs explicit recovery" note: `session [--copy]` = the
  last COMPLETED keyboard-typed dictation (ordinary recovery; --copy = clipboard), `recover [ID]` = unconfirmed
  words of an ended NATIVE EDITOR session, read-only, no --copy); epilog "subcommands:" line + the same note;
  main() docstring paragraph. install.sh: `usage :` line + one explanation echo (exact text in the Desired tree).
  RUN: timeout 120 .venv/bin/python -m py_compile voice_typing/ctl.py tests/test_voicectl_recover.py && bash -n install.sh && echo L1 PASS
       timeout 15 .venv/bin/voicectl --help | grep -nE "recover"      # both the positional help and the epilog

Task 4: FULL GATES (Level 2/3) + `git diff --name-only` == the three files; install.sh diff = echo lines only.
  HANDOFF → P1.M2.T1.S5 / P1.M2.T2.S4 (editor actions) and acceptance: `voicectl recover <id>` prints text + one
  newline on stdout, warnings on stderr, exit 0/1/2/64 as in the Goal table; adapters show
  "Unconfirmed text: `voicectl recover <id>`" and never shell out per utterance; README sync is P1.M2.T4.S1.
```

### Implementation Patterns & Key Details

```python
# PATTERN — the recover branch in main() is three lines at each step; everything else is untouched.
# step 1 (usage, before I/O):        see Task 2
# step 2 (wire):                     one plain send_command on a fresh connection; wire cmd ≠ user cmd (like start-context)
# step 3 (render):                   stderr first, stdout last, return the code
out, lines, code = format_recovery(response, args.id)
for line in lines:
    print(line, file=sys.stderr)
print(out)            # text + the single terminal newline — stdout is NOTHING else
return code

# GOTCHA — send_command's recv loop already handles multi-MiB lines (4096-byte chunks until b"\n"); the ONLY
# change is the optional cap, checked after extend, before the loop re-test:
buf.extend(chunk)
if max_reply_bytes is not None and len(buf) > max_reply_bytes:
    raise ValueError(f"daemon reply exceeded {max_reply_bytes} bytes before its newline — refused")
```

```yaml
INTEGRATION POINTS:
  SOCKET:  none new — existing $XDG_RUNTIME_DIR/voice-typing/control.sock via _default_control_socket_path(); fresh connection per run
  WIRE:    {"cmd":"editor-recover"} | {"cmd":"editor-recover","id":"<uuid4>"}  (P1.M1.T5.S1 grammar; nothing added to the protocol)
  CONFIG:  none (7 MiB is S1's code constant, re-exported as ctl._RECOVERY_REPLY_MAX_BYTES)
  CLIPBOARD: none — _copy_session_to_clipboard untouched; `recover` never calls it
  DOCS:    ctl.py usage surfaces + install.sh quick-start ([Mode A]); README deferred to P1.M2.T4.S1
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 120 .venv/bin/python -m py_compile voice_typing/ctl.py tests/test_voicectl_recover.py && echo "L1 PASS"
timeout 60 bash -n install.sh && echo "install.sh syntax OK"          # NEVER execute install.sh
timeout 15 .venv/bin/voicectl --help | grep -c recover                 # ≥ 2 (positional help + epilog); exits before any socket
git diff --stat -- install.sh                                           # echo lines only (review)
# ruff/mypy: not configured in pyproject ([tool.hatch…], [tool.pytest…] only) — "skipped" unless Task 0 finds them
```

### Level 2: Unit Tests

```bash
timeout 300 .venv/bin/python -m pytest tests/test_voicectl_recover.py -q                                        # bash 360
timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_voicectl_session.py tests/test_native_recover.py -q   # bash 360; session --copy untouched
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -30                           # bash ≥ 560; FAILED set == G1 CPU addendum
# Expected: all green; test_daemon FAILED set == tests/G1_BASELINE.md CPU addendum
```

### Level 3: Integration (production boundary, no live daemon)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_voicectl_recover.py -q -k "bound or big or over_cap or default_unbounded" -v   # bash 360
timeout 60 env -i PATH="$PATH" .venv/bin/voicectl recover; echo "exit=$?"          # no XDG_RUNTIME_DIR → exit 2, stderr only, no hang
timeout 60 .venv/bin/voicectl recover abc; echo "exit=$?"                           # → exit 64 before any socket
timeout 60 .venv/bin/voicectl recover --copy; echo "exit=$?"                        # → exit 64
pgrep -af "voice-typing-daemon" || echo "no daemon touched"; ls /tmp | grep -c "^vt-rc-" || true   # 0 leftovers
# Expected: exit codes 2 / 64 / 64; nothing on stdout; no stray sockets; no daemon was started or contacted.
```

### Level 4: Creative & Domain-Specific

```bash
timeout 120 .venv/bin/python - <<'EOF'
import json
from voice_typing import ctl, daemon
assert ctl._RECOVERY_REPLY_MAX_BYTES == daemon.MAX_RECOVERY_REPLY_BYTES == 7 << 20
SID = "123e4567-e89b-42d3-a456-426614174000"
ok = {"ok": True, "id": SID, "text": "hello world", "truncated": True, "possibly_applied": True}
out, lines, code = ctl.format_recovery(ok, SID)
assert (out, code) == ("hello world", 0) and len(lines) == 2 and "hello" not in " ".join(lines)
assert ctl.format_recovery(ok, "123e4567-e89b-42d3-a456-426614174001")[2] == 1          # id mismatch
import inspect; src = inspect.getsource(ctl.send_command); assert "max_reply_bytes" in src
print("L4 OK")
EOF
# Expected: "L4 OK" — parity with the daemon cap, warnings never carry text, mismatch refused, bound present.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 pass; `tests/test_voicectl_recover.py` green; `test_voicectl.py`, `test_voicectl_session.py`,
      `test_native_recover.py` green; test_daemon FAILED set == G1 CPU addendum
- [ ] `git diff --name-only` == `{voice_typing/ctl.py, install.sh, tests/test_voicectl_recover.py}`; install.sh
      diff is echo lines only; `bash -n install.sh` clean
- [ ] No daemon/protocol/store/README/plan change; no new env var/config/dependency

### Feature Validation
- [ ] (a) wire shapes + exactly one call, plain send_command; (b) stdout = text + newline only; (c) exit table;
      (d) strict five keys + id match; (e) 7 MiB bound only for recover; (f) `session [--copy]` byte-identical,
      no clipboard/subprocess from recover; (g) usage errors 64 before I/O; (h)–(i) hold
- [ ] `voicectl --help` and the install.sh quick-start list `recover [ID]` and contrast it with `session [--copy]`
- [ ] Handoff to P1.M2.T1.S5 / P1.M2.T2.S4 written in the completion message (command, stdout/exit contract)

### Code Quality / Documentation
- [ ] `format_recovery` is pure and unit-tested; `format_result` untouched; main() changes are the three small
      branch inserts; fixed-word messages (no reply values in stderr); [Mode A] docstrings/usage updated
- [ ] `_COMMANDS` comment updated; no "retry"/"consume"/"copy" code anywhere in the recover path

## Anti-Patterns to Avoid

- ❌ Routing `recover` through `format_result` (its error text would land on stdout) or printing an id/count/banner
- ❌ Retrying, reconnecting, falling back to `session`, or "consuming" the snapshot; any clipboard/typing/subprocess
- ❌ `isinstance(x, bool)` checks that let `1`/`"yes"` pass as flags; `.get("text", "")` defaults that turn a
      malformed reply into an empty successful print; printing a reply whose `id` ≠ the requested one
- ❌ Bounding every command's reply (only `recover` passes the cap); lowering/raising the 7 MiB constant locally
- ❌ Validating the id after connecting; sending a non-UUIDv4 to see what the daemon says; letting `recover --copy`
      or `recover --context-stdin` through
- ❌ Running `install.sh` (or the live daemon/voicectl against the user's unit) to "check the help text"
- ❌ Editing `daemon.py`/`editor_protocol.py`/`session_recovery.py` (S1), README (P1.M2.T4.S1), plan files,
      PRD.md, tasks.json

---

## Confidence Score

**9/10.** The wire grammar and every reply shape are fixed by S1/PRD and quoted; the module is fully read with
line anchors; the argparse idiom, the T2.S5 patterns (wire remap, old-daemon detection, "not retried"), the
stderr-only warning precedent and the test harness are all existing code to copy; the non-obvious points are
pinned as gotchas (format_result would pollute stdout, the `busy` flag trap, strict typed flags, requested-id
match, cap only for recover, the argparse two-positional side effect, install.sh never executed). The −1 is the
S1 dependency: Task 0 verifies `MAX_RECOVERY_REPLY_BYTES` landed as specified and stops otherwise.

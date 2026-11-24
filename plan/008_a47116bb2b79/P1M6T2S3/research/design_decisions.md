# Design decisions — voicectl session [--copy] (P1.M6.T2.S3)

Inputs consumed: `daemon_dispatch_sitemap.md` + `clipboard_local_evidence.md` +
`wlclipboard_external.md` (this directory) and the S2 PRP contract. Each decision cites its
source. These decisions are normative for the PRP.

## D1 — Wire protocol (`session` cmd + reply shape)
Request `{"cmd": "session"}` (optionally `{"cmd": "session", "copy": true}`).
Reply via NEW daemon method `session_reply(copy=False)` (d2 §4 step 2: daemon method, NOT via
`_arm_response`), built on S2's `session_snapshot()`:
- none → `{"ok": false, "error": "no completed session yet"}` — the none-case RIDES the
  existing `format_result` ok:false→exit-1 branch, so "exit 1 with clipboard untouched" falls
  out with zero new logic (copy code is only reached when ok).
- present → `{"ok": true, "session": {text, truncated, finals, finals_dropped, tail_chars,
  ended_monotonic}}` — S2's snapshot dict verbatim (text-field precedent: status already
  carries partial/last_final). No status_snapshot spread (dedicated shape like `cancel`).
Extra request keys are ignored by today's `_dispatch` (reads only `msg.get("cmd")`,
daemon_dispatch_sitemap §1) → old daemons fail safe to unknown-command → exit 1 (d2 §9 risk 9).

## D2 — `send_command` extension (required by the item contract)
`send_command(socket_path, cmd, extra=None)` → wire payload `{"cmd": cmd, **(extra or {})}` —
exact signature from d2 §4 step 1. `voicectl session --copy` sends `extra={"copy": True}`; the
daemon logs/reports it (counts only). All existing callers unchanged.

## D3 — stdout purity; format_result stays PURE
`format_result` gains a `session` branch (d2 §4 step 3) returning exactly
`(session["text"], 0)` — stdout = the session text + print()'s single terminal newline,
script-pipeable. Truncation warning + `--copy` orchestration are I/O → they live in `main()`;
`format_result`'s "PURE, no I/O" docstring stays true.

## D4 — Copy is CLIENT-side; fork-mode wl-copy + verify (deviation from d2's --foreground letter)
d2 §4 step 4 prescribes `--foreground` (the ghostty_probe lab pattern, where the harness owns
the process tree). Web research (wlclipboard_external.md, source-verified): wl-copy's DEFAULT
fork happens only AFTER `set_selection` + a protocol roundtrip — parent exit 0 ⇒ the
selection is already registered (no race); `--foreground` blocks until the selection is
replaced = a hang risk in a CLI. Decision: `subprocess.run([wl-copy, --type, MIME], input=
exact_utf8_bytes, check=True, timeout=5)` in fork mode, then a bounded verify poll
(`wl-paste --no-newline` stdout must byte-equal the staged bytes; wl-paste appends `\n` ALWAYS
without `--no-newline` — no isatty check in any version). The poll (deadline ~2 s, ~25 ms
interval) covers new-connection selection-advertisement lag; it is the ghostty_probe
`until(offered)` gate idiom in production form. Keep the substance of d2/§5.7 (explicit MIME,
CLIPBOARD-only, byte verify), drop the `--foreground` letter. Never `--paste-once` (a
history-manager read would consume the offer — probe comment :100-101), never `--primary`,
never `--trim-newline` (we add no newline; the flag would eat a legitimate trailing `\n`).

## D5 — MIME + binaries
`--type text/plain;charset=utf-8` (d2/probe form; explicit UTF-8 for non-ASCII text).
Binaries: `/usr/bin/wl-copy`, `/usr/bin/wl-paste` (verified present, this machine), with a
`shutil.which` fallback; missing → clean stderr error, exit 1, clipboard untouched.

## D6 — Exit-code table (session)
| case | stdout | stderr | exit |
|---|---|---|---|
| print, ok | session text | truncation warning if truncated | 0 |
| --copy ok | `copied N chars` | truncation warning if truncated | 0 |
| --copy failed | — | failure detail | 1 |
| no completed session | `error: no completed session yet` | — | 1 (no subprocess run) |
| old daemon (unknown cmd) | `error: unknown command: 'session'` | — | 1 |
| daemon down / usage | existing 2 / 64 paths unchanged | | |

`--copy` with a non-session cmd → usage error 64 (validated in main() after cmd validation).

## D7 — Daemon side
`session_reply(copy=False)` on VoiceTypingDaemon beside S2's `session_snapshot()`
(S2 contract point). `_dispatch` branch before the unknown fallthrough (live site
daemon.py:3005-3051, pre-S2 anchors). One INFO log line, counts/times only (R.6 log law):
`session recovery: session served copy=%d chars=%d truncated=%d`. ControlServer class
docstring protocol block (daemon.py:2826-2845) gains the session line (one-line Mode A touch).

## D8 — Tests (three layers)
- tests/test_control_socket.py: dispatch + real-socket round-trip; extend its `_StubDaemon`
  with a canned `session` param + `session_reply()` (records the copy flag).
- tests/test_voicectl.py: format_result unit, main() orchestration with monkeypatched
  clipboard helper, running_server fixture gains optional `session=` passthrough; its own
  `_StubDaemon` (:192) gains the same method.
- tests/test_voicectl_session.py (NEW): real-daemon `session_reply` semantics via S2's
  daemon-driving pattern (none→error; completed→payload; open draft invisible).

## D9 — Scope walls
No hypr-binds.conf / install.sh changes (bind is USER-assigned — item contract; R.6 "never
installed over an existing one"). No README edits (P1.M7.T2.S1 owns). No config keys, no
state.json, no feedback.py, no S1/S2 file edits. `wl-copy` absence / non-Wayland = reported
failure, never a typing fallback (R.3: no fallback to typing backends).

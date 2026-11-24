---
name: "P1.M6.T2.S3 — voicectl session [--copy]: the R.6 recovery surface (print + Wayland clipboard copy)"
description: "Add the `session` command to voicectl and the daemon control protocol: `voicectl session` prints the most recent COMPLETED dictation session from P1.M6.T2.S2's recovery store; `--copy` stages exactly that text on the Wayland CLIPBOARD (explicit MIME, no added newline, byte-verified, PRIMARY untouched, never types/erases/submits). Daemon-side `session_reply` in `_dispatch`; `send_command` gains additive extra payload keys; truncation reported on stderr and in the reply; exit 1 with the clipboard untouched when no session exists. Unit + socket tests green; Mode A docs (ctl.py docstring + --help epilog)."
---

# PRP — P1.M6.T2.S3: `voicectl session [--copy]`

## Goal

**Feature Goal**: A user-facing recovery surface over P1.M6.T2.S2's daemon-side session store:
`voicectl session` prints the **most recent COMPLETED** arm→disarm session (never a moving
draft), and `voicectl session --copy` puts **exactly that text** on the Wayland CLIPBOARD —
explicit MIME `text/plain;charset=utf-8`, **no added newline**, byte-verified via
`wl-paste --no-newline`, PRIMARY selection untouched, and **never types/erases/submits**
anything. When no completed session exists: exit 1 with the clipboard untouched. Truncation
(store cap) is reported on stderr and carried in the daemon reply. The recovery keybind, if
any, is **USER-assigned** — this item never installs one and never touches `hypr-binds.conf`.

**Deliverable** (2 MODIFY + 2 MODIFY-tests + 1 CREATE-test):
1. `voice_typing/daemon.py` — MODIFY: `VoiceTypingDaemon.session_reply(copy=False)` beside
   S2's `session_snapshot()`; one `session` branch in `ControlServer._dispatch`; one line in
   the ControlServer protocol docstring.
2. `voice_typing/ctl.py` — MODIFY: `"session"` in `_COMMANDS`; `send_command(..., extra=None)`
   additive-payload extension; `format_result` session branch; `_copy_session_to_clipboard()`
   stage→verify helper (+ wl-clipboard constants/resolver); argparse `--copy` flag +
   `--copy`-only-with-session validation; session flow in `main()`; Mode A doc updates
   (module docstring, `--help` epilog, positional help).
3. `tests/test_control_socket.py` — MODIFY: `_StubDaemon.session_reply()` + dispatch-layer
   and real-socket session tests.
4. `tests/test_voicectl.py` — MODIFY: its `_StubDaemon.session_reply()`; format_result unit
   tests; `main()` orchestration tests (mocked clipboard helper); exit-code/table pins.
5. `tests/test_voicectl_session.py` — CREATE: real-daemon `session_reply` semantics
   (none→error, completed→payload, open-draft invisibility, counts-only log).

**Success Definition**:
- (a) With a completed session in the store: `voicectl session` → stdout is EXACTLY the
  session text plus print()'s single terminal newline, exit 0.
- (b) `voicectl session --copy` → the CLIPBOARD holds byte-identical UTF-8 (no trailing
  newline added), stdout `copied N chars`, exit 0; the only subprocesses ever spawned are
  `wl-copy` and `wl-paste` (never wtype/ydotool — nothing is typed, erased, or submitted).
- (c) No completed session → `{"ok":false,"error":"no completed session yet"}` → stdout
  `error: no completed session yet`, exit 1, and **no subprocess runs** (clipboard untouched).
- (d) Truncated session → daemon reply carries `truncated:true` + `finals_dropped`; the
  client prints a stderr warning; `--copy` still copies the truncated text (exit 0).
- (e) Copy failures (wl-copy absent, not-on-Wayland exit 1 from wl-copy, verify timeout) →
  stderr detail, exit 1.
- (f) An armed session with a live partial (moving draft) is INVISIBLE: `session` still
  answers the previous completed session.
- (g) `--copy` with a non-session command → usage error 64; unknown/missing command → 64;
  daemon down → 2 (all existing codes unchanged). An OLD daemon (no session branch) replies
  `unknown command: 'session'` → client exits 1, clipboard untouched (fail-safe).
- (h) G1 watch set + `tests/test_session_recovery.py` (S2) + `tests/test_bulk_dispatch.py`
  (S1) report identical/green numbers; no config keys, no state.json, no feedback.py, no
  hypr-binds.conf/install.sh/README changes.

## User Persona

**Target User**: the **operator** mid-writing-flow: they dictated, disarmed (or the HALT/idle
path fired) mid-thought, and want the words back — either to read (`voicectl session`) or to
paste somewhere (`voicectl session --copy`, bound by the USER to their own key if desired).
Secondary: **scripts** consuming stdout (stdout purity matters: text and nothing else).

**Use Case**: dictate three sentences + a partial → stop → realize the tail mattered →
`voicectl session` (see it) or `voicectl session --copy` then Ctrl+V (reuse it).

**User Journey**: 1) run `voicectl session` → the completed session text prints, or a clean
`error: no completed session yet` + exit 1 when the store is empty (e.g. right after daemon
restart — no crash persistence by design). 2) `voicectl session --copy` → `copied 123 chars`;
the clipboard now pastes exactly what was dictated. 3) If the store capped the session, a
stderr line says so while stdout/clipboard still deliver the newest text that fits.

**Pain Points Addressed**: today a mid-thought disarm loses the tail permanently — the store
(S2) exists but has NO user surface; and ad-hoc clipboard copies (mouse selection, echo |
wl-copy) add newlines / touch PRIMARY / are unverified — this item is the one sanctioned,
exact-bytes path.

## Why

- **PRD §4.2sexies R.6** (verbatim clause this item completes): "`voicectl session` prints the
  most recent COMPLETED session (never a moving draft); `voicectl session --copy` copies
  exactly that text — no added newline, never types/erases/submits, exit 1 with the clipboard
  untouched when none exists; truncation is reported on stderr and in the reply. Any bind for
  it is user-assigned, never installed over an existing one."
- **Everything upstream is contract-stable**: S2's PRP defines
  `daemon.session_snapshot() -> None | {text, truncated, finals, finals_dropped, tail_chars,
  ended_monotonic}` and explicitly reserves the voicectl surface for THIS item ("no ctl.py
  changes, no socket commands (S3 owns `voicectl session`)"). S2 is landing in parallel; its
  PRP is the contract.
- **The architecture doc already prescribes the recipe**: `plan/008_a47116bb2b79/architecture/
  d2_bulk_delivery_map.md` §4 (quoted verbatim in research/) — `_COMMANDS` addition,
  `send_command(socket_path, cmd, extra=None)`, `_dispatch` → `self._daemon.session_reply(...)`
  (NOT via `_arm_response`), `format_result` session branch, client-side wl-copy staging with
  `wl-paste --no-newline` verify (ghostty_probe pattern), and §9 risk 9 (additive payload keys
  are ignored by old daemons → fail-safe).
- **Clipboard mechanics are pre-verified** (research/wlclipboard_external.md,
  source-verified against wl-clipboard master + v2.2.1): wl-copy's default fork happens only
  AFTER `set_selection` + roundtrip → parent exit 0 ⇒ selection registered (no race);
  wl-paste appends `\n` ALWAYS without `--no-newline`; not-on-Wayland → stderr `Failed to
  connect to a Wayland server`, exit 1. `--foreground` blocks until the selection is replaced
  — a hang risk in a CLI, hence deliberately NOT used (see D4 in research/design_decisions.md).

## What

Client `voicectl session [--copy]` + daemon `{"cmd":"session"}` protocol branch, per the
exit-code table:

| case | stdout | stderr | exit |
|---|---|---|---|
| print, ok | session text (+ terminal newline from print) | truncation warning if truncated | 0 |
| `--copy`, ok | `copied N chars` | truncation warning if truncated | 0 |
| `--copy`, failed | — | failure detail | 1 |
| no completed session | `error: no completed session yet` | — | 1 (no subprocess run) |
| old daemon (unknown cmd) | `error: unknown command: 'session'` | — | 1 |
| daemon down / XDG unset | — | existing messages | 2 |
| `--copy` with non-session cmd / bad cmd | — | usage message | 64 |

Wire protocol: request `{"cmd": "session"}` (+ `"copy": true` when `--copy`); reply
`{"ok": true, "session": <S2 snapshot dict>}` or `{"ok": false, "error": "no completed
session yet"}`. Copy semantics: stage exact UTF-8 bytes on the CLIPBOARD selection via
fork-mode `wl-copy --type text/plain;charset=utf-8`; verify by byte-equality against
`wl-paste --no-newline` (bounded poll); never `--primary`, `--paste-once`, or
`--trim-newline`; only wl-copy/wl-paste subprocesses; every subprocess timeout-bounded.

### Success Criteria

- [ ] (a)–(h) above hold, each pinned by ≥1 named test (test inventory in Implementation
      Tasks 3–5).
- [ ] Mode A docs: ctl.py module docstring (Subcommands + Usage) and `--help` epilog list
      `session [--copy]`; positional help mentions session; ControlServer protocol docstring
      gains the session line.
- [ ] Scope walls respected: no hypr-binds.conf, no install.sh, no README (P1.M7.T2 owns), no
      config keys, no state.json/feedback.py, no edits to S1/S2 implementation files beyond
      the daemon additions above.

## All Needed Context

### Context Completeness Check

_Pass._ The exact daemon dispatch site + stub shapes (live-verified anchors), the S2 snapshot
contract, the d2 §4 recipe (quoted verbatim), the source-verified wl-clipboard behavior, the
full reply/exit-code table, the copy helper's complete code sketch, and executable validation
commands are all below. The implementing agent needs no other document beyond the files cited.

### Documentation & References

```yaml
# MUST READ — the parallel-predecessor CONTRACT (assume it landed exactly as specified).
- file: plan/008_a47116bb2b79/P1M6T2S2/PRP.md
  why: "Defines this item's INPUT: daemon.session_snapshot() -> None | {text, truncated,
        finals, finals_dropped, tail_chars, ended_monotonic} (Task 5 / Integration Points
        'S3 CONSUMPTION'). S2 explicitly reserves voicectl session for this item; its suite
        tests/test_session_recovery.py must stay green."
  critical: "session_snapshot() returns the LATEST COMPLETED session only — draft
             invisibility is inherited; do NOT read the store any other way."

# MUST READ — this item's verified research (all in plan/008_a47116bb2b79/P1M6T2S3/research/).
- file: plan/008_a47116bb2b79/P1M6T2S3/research/design_decisions.md
  why: "D1–D9: wire protocol, send_command extension, stdout purity, fork-mode wl-copy +
        verify (and why NOT --foreground), MIME/binary resolution, exit-code table, test
        layers, scope walls. Normative for this PRP."
- file: plan/008_a47116bb2b79/P1M6T2S3/research/daemon_dispatch_sitemap.md
  why: "Live site map: ControlServer._dispatch daemon.py:3005-3051 (unknown fallthrough
        :3050 reads ONLY msg.get('cmd')); status_snapshot :2568-2624; _StubDaemon
        tests/test_control_socket.py:33; test three-layer structure; server threading (no
        read timeout by design)."
- file: plan/008_a47116bb2b79/P1M6T2S3/research/clipboard_local_evidence.md
  why: "Verbatim quotes: d2_bulk_delivery_map.md §4 (the recipe + §9 risk 9),
        external_tech_notes.md §5.1–5.7 (CLIPBOARD-only, fork lifetime, --paste-once trap,
        multi-format loss, cliphist watchers, 'printf %s | wl-copy -t text/plain' safest
        pattern), ghostty_probe.py:80-141 (stage stdin pattern :102, 'wl-paste --no-newline'
        byte-verify :109, until(offered) gate, timeout/kill-tree discipline)."
- file: plan/008_a47116bb2b79/P1M6T2S3/research/wlclipboard_external.md
  why: "Source-verified wl-clipboard facts: fork AFTER set_selection+roundtrip (parent exit 0
        ⇒ registered); --foreground blocks until replaced (hang risk); --trim-newline removes
        exactly one trailing \\n; wl-paste appends \\n always (no isatty); empty clipboard →
        'Nothing is copied' exit 1; not-on-Wayland error + exit 1; one real MIME + aliases."

# MUST READ — the PRD clause + the client's own spec.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.6 (recovery paragraph — the verbatim contract, quoted in Why); R.5
        ('never the surrounding user document'); §4.8 (voicectl exit codes 0/1/2/64, one JSON
        line each way); §4.2 (control socket protocol)."
- file: voice_typing/ctl.py
  why: "THE client file. _COMMANDS tuple (~:42-49); format_result (~:82, PURE, ok:false→
        ('error: ...',1) first branch, status branch pattern); send_command (~:167-210,
        sock.settimeout bounds connect+recv); _build_parser (~:236, choices deliberately OFF
        so usage errors exit 64); main (~:262-301, alias remap → validate → resolve → send →
        format → print); _ALIASES untouched."
  gotcha: "format_result is documented PURE (no I/O) — truncation stderr + --copy are main()'s
           job. Do not use argparse choices= (would exit 2, colliding with daemon-down)."

- file: voice_typing/daemon.py
  why: "(1) ControlServer._dispatch :3005-3051 — add the session branch after 'quit', before
        the unknown fallthrough :3050. (2) VoiceTypingDaemon — session_reply() goes BESIDE S2's
        session_snapshot() (beside status_snapshot :2568-2624 pre-S2). (3) Module logger
        'logger = logging.getLogger(__name__)' :178. (4) ControlServer class docstring +
        protocol block :2826-2845 — one-line addition. ALL anchors pre-S2 — re-grep (Task 0)."
  critical: "_dispatch must keep its never-raises contract; session_reply is lock-safe and
             non-blocking (S2's store leaf lock; snapshot is a bounded dict build)."

- file: tests/test_control_socket.py
  why: "Layer A dispatch tests via _disp() + _StubDaemon (:33, duck-typed, canned
        status_snapshot); Layer B real AF_UNIX round-trip via server fixture + _send();
        test_dispatch_status_has_all_keys pins the EXACT status key set (do not change the
        status reply); test_dispatch_unknown_command pins the error format."
- file: tests/test_voicectl.py
  why: "format_result unit tests; its own _StubDaemon (:192); running_server fixture (:226,
        ControlServer on tmp socket, XDG_RUNTIME_DIR → tmp_path); main() tests with capsys;
        loading-hint tests show the monkeypatch discipline (ctl._LOADING_HINT_DELAY)."
- file: tests/test_session_recovery.py
  why: "S2's landed suite (exists at implementation time): the daemon-driving pattern for the
        real VoiceTypingDaemon WITHOUT CUDA (fake host, direct method calls) — mirror it for
        tests/test_voicectl_session.py. It must stay green after the daemon additions."
  gotcha: "If S2's fixtures differ from its PRP, adapt — the pattern (real daemon + fake
           host, drive arm/on_final/_on_partial/disarm synchronously) is the contract."

- url: https://github.com/bugaevc/wl-clipboard/blob/master/data/wl-clipboard.1
  why: "The man page with the authoritative flag docs (-t/--type, -f/--foreground,
        --trim-newline, -p/--primary, --paste-once; wl-paste --no-newline)."
- url: https://github.com/bugaevc/wl-clipboard
  why: "Canonical README: fork/foreground semantics, selection lifetimes."

# Hard rules.
- file: AGENTS.md
  why: "Two timeouts on every non-trivial command (inner GNU timeout + bash-tool timeout);
        voicectl always under timeout; NEVER run the daemon in the foreground; tests with
        fakes only — no CUDA, no live desktop, and (this item) never touch the REAL
        clipboard in automated validation."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── ctl.py              # ← MODIFY: session command, --copy, send_command extra, copy helper, docs
├── daemon.py           # ← MODIFY: session_reply() + _dispatch branch + protocol docstring line
│                       #    (S2 lands session_snapshot() + store here first — re-grep in Task 0)
└── session_recovery.py # S2's store (READ ONLY — consume via session_snapshot() only)
tests/
├── test_control_socket.py   # ← MODIFY: stub + dispatch/socket session tests
├── test_voicectl.py         # ← MODIFY: stub + CLI unit/orchestration tests
├── test_voicectl_session.py # ← CREATE: real-daemon session_reply semantics
├── test_session_recovery.py # S2's suite — must stay green (untouched)
└── test_bulk_dispatch.py    # S1's suite — must stay green (untouched)
```

### Desired Codebase tree with files to be added

```bash
voice_typing/ctl.py              # + ~120 lines: --copy flag, _copy_session_to_clipboard(),
                                 #   _resolve_tool + _WL_* constants, send_command extra=,
                                 #   format_result session branch, main() session flow, docs
voice_typing/daemon.py           # + ~20 lines: session_reply() (~14 incl. docstring),
                                 #   _dispatch session branch (2), protocol docstring line (1)
tests/test_control_socket.py     # + ~60 lines: stub session_reply + 4 tests
tests/test_voicectl.py           # + ~150 lines: stub session_reply + ~13 tests
tests/test_voicectl_session.py   # + ~120 lines: 4 real-daemon tests (S2's driving pattern)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G1) — THE NONE-CASE MUST RIDE THE EXISTING ok:false PATH: daemon replies
#   {"ok": false, "error": "no completed session yet"}; format_result's FIRST branch already
#   maps any ok:false to ("error: ...", 1). Therefore --copy code (main()) is unreachable in
#   the none-case → "exit 1 with clipboard untouched" holds BY CONSTRUCTION. Do not invent a
#   {"ok": true, "session": null} shape — it would need new none-handling in two places.

# CRITICAL #2 (G2) — STDOUT PURITY: `voicectl session` stdout is EXACTLY the session text
#   (print() adds the single terminal newline — that's the shell idiom, keep it). NO metadata
#   lines on stdout. Truncation warning → stderr. format_result stays PURE (its docstring
#   says so); the warning + copy orchestration live in main().

# CRITICAL #3 (G3) — wl-copy INVOCATION LAW: fork mode via subprocess.run (NOT --foreground —
#   it blocks until the selection is replaced = CLI hang risk; the ghostty_probe lab used it
#   only because the harness owns its process tree). argv must contain "--type",
#   "text/plain;charset=utf-8" and must NOT contain "--primary", "--paste-once" (a
#   clipboard-history manager's read would consume a one-shot offer without any target
#   acknowledging — ghostty_probe comment :100-101), or "--trim-newline" (we add no newline;
#   the flag would eat a LEGITIMATE trailing newline). input= is the EXACT UTF-8 bytes —
#   never + b"\n". stdin is a byte pipe, never a shell string.

# CRITICAL #4 (G4) — VERIFY WITH --no-newline OR NOT AT ALL: wl-paste appends "\n" ALWAYS
#   (no isatty check in any version) — byte-equality is only meaningful with --no-newline.
#   The verify is a bounded poll (~2 s deadline, ~25 ms interval): parent-exit-0 already
#   proves registration on wl-copy's connection, but a FRESH wl-paste connection can see the
#   new selection one compositor event-loop turn later; empty clipboard → wl-paste exit 1
#   ("Nothing is copied") → keep polling until the deadline, then fail.

# CRITICAL #5 (G5) — TIMEOUT DISCIPLINE (AGENTS.md): every wl subprocess is bounded
#   (wl-copy stage timeout 5 s; each wl-paste attempt 1 s; verify deadline 2 s). send_command
#   keeps its VOICECTL_TIMEOUT socket guard unchanged. The session flow never blocks on the
#   daemon socket longer than any other command.

# CRITICAL #6 (G6) — NEVER TYPES/ERASES/SUBMIT: the ONLY subprocesses this feature may spawn
#   are wl-copy and wl-paste. Never import/call typing_backends, wtype, ydotool. Copy
#   failure is a REPORTED failure (exit 1) — there is NO typing fallback (PRD R.3).

# CRITICAL #7 (G7) — SCOPE WALLS: do NOT touch hypr-binds.conf or install.sh (the recovery
#   bind is USER-assigned — R.6 "never installed over an existing one"); do NOT touch README
#   (P1.M7.T2.S1 owns doc sync); no config keys, no state.json, no feedback.py, no
#   streaming/bulk_controller/session_recovery edits. tests/G1_BASELINE.md records the
#   pre-existing test_streaming_commit reds — reconcile, never "fix" them here.

# CRITICAL #8 (G8) — S2 CO-MODIFICATION DRIFT: daemon.py anchors below are PRE-S2 (verified:
#   session_snapshot not yet in tree at research time). S2 lands first and shifts lines —
#   Task 0 re-greps. The CONTRACT is session_snapshot()'s shape, not its line number.

# CRITICAL #9 (G9) — STUB COVERAGE: ControlServer._dispatch will call
#   self._daemon.session_reply(...) — BOTH test stubs (tests/test_control_socket.py:33 and
#   tests/test_voicectl.py:192) must gain the method or any session dispatch test (and any
#   future {"cmd":"session"} against a stub) AttributeErrors inside the worker thread.
#   Existing non-session tests are unaffected (branch is equality-guarded).

# CRITICAL #10 (G10) — NO LIVE-DESKTOP VALIDATION: automated tests mock subprocess entirely;
#   never run wl-copy/wl-paste against the operator's real session in validation (R.7 + the
#   repo's discipline). The unit tests' mocked argv/stdin assertions ARE the clipboard
#   contract. A real-desktop smoke is the operator's manual choice, not a gate.
```

## Implementation Blueprint

### Data models and structure

No new dataclasses. The wire/reply shapes (dicts) and the client-side contract:

```python
# Wire (client → daemon), one JSON line — send_command(socket_path, cmd, extra=None):
{"cmd": "session"}                    # plain print
{"cmd": "session", "copy": true}      # --copy (informational: daemon logs/reports it)

# Reply (daemon → client), one JSON line — VoiceTypingDaemon.session_reply(copy=False):
{"ok": false, "error": "no completed session yet"}          # store empty / cleared at exit
{"ok": true, "session": {                                   # S2's snapshot dict, verbatim
    "text": "...", "truncated": false, "finals": 3,
    "finals_dropped": 0, "tail_chars": 0, "ended_monotonic": 12345.678}}

# Client module constants (voice_typing/ctl.py):
_WL_COPY = "/usr/bin/wl-copy"          # verified present on this machine
_WL_PASTE = "/usr/bin/wl-paste"
_WL_STAGE_TIMEOUT_S = 5.0              # wl-copy subprocess timeout (fork-mode parent)
_WL_VERIFY_DEADLINE_S = 2.0            # total wl-paste verify poll budget
_WL_PASTE_TIMEOUT_S = 1.0              # each wl-paste attempt
_WL_VERIFY_POLL_S = 0.025              # poll interval
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — re-verify anchors post-S2 + record the baseline.
  - RUN: grep -n "def session_snapshot\|def status_snapshot\|def session_reply" voice_typing/daemon.py
         grep -n "def _dispatch\|class ControlServer" voice_typing/daemon.py
         grep -n "_COMMANDS\|def send_command\|def format_result\|def _build_parser\|def main" voice_typing/ctl.py
         grep -n "class _StubDaemon\|def running_server" tests/test_voicectl.py tests/test_control_socket.py
  - EXPECT: session_snapshot EXISTS (S2 landed). If not, STOP — this item's input is missing.
  - RUN (baseline, BEFORE any edit):
      for f in test_control_socket test_voicectl test_session_recovery test_bulk_dispatch \
               test_streaming_commit test_zero_diff_rewind test_key_listener test_config; do
        timeout 300 .venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1; done
  - EXPECTED post-change: identical (test_streaming_commit reds are pre-existing —
    tests/G1_BASELINE.md; do not fix, do not skip).

Task 1: MODIFY voice_typing/daemon.py — session_reply + dispatch branch + doc line.
  - ADD on VoiceTypingDaemon, BESIDE session_snapshot():
      def session_reply(self, copy: bool = False) -> dict:
          """Control-socket reply for {"cmd": "session"} — P1.M6.T2.S3 (PRD §4.2sexies R.6).

          Most recent COMPLETED session only (session_snapshot() never exposes an open
          draft). None → ok:false, so the client's existing error path yields exit 1 with
          the clipboard untouched. Log line is counts-only (R.6: no transcript-bearing logs).
          """
          snap = self.session_snapshot()
          if snap is None:
              return {"ok": False, "error": "no completed session yet"}
          logger.info(
              "session recovery: session served copy=%d chars=%d truncated=%d",
              int(bool(copy)), len(snap.get("text", "")), int(bool(snap.get("truncated"))),
          )
          return {"ok": True, "session": snap}
  - ADD in ControlServer._dispatch, after the `quit` branch, BEFORE the unknown-command
    fallthrough (grep `unknown command`):
      if cmd == "session":  # P1.M6.T2.S3 (§4.2sexies R.6): most recent COMPLETED session
          return self._daemon.session_reply(copy=bool(msg.get("copy", False)))
  - ADD one line to the ControlServer class docstring protocol block (beside the existing
    command list): `{"cmd":"session"}` → session reply (R.6 recovery surface).
  - RUN: .venv/bin/python -m py_compile voice_typing/daemon.py

Task 2: MODIFY voice_typing/ctl.py — command, flag, helper, formatting, docs.
  - IMPORTS: add `import shutil`, `import subprocess`, `import time` (stdlib; keep
    import-purity — test_voicectl's test_ctl_module_present_and_imports_pure pattern).
  - _COMMANDS: append "session" → (toggle, start, stop, status, quit, cancel, session).
    _ALIASES untouched.
  - CONSTANTS: _WL_* block per Data models; resolver:
      def _resolve_tool(preferred: str, name: str) -> str | None:
          return preferred if os.path.exists(preferred) else shutil.which(name)
  - send_command: signature → `def send_command(socket_path: str, cmd: str,
    extra: dict | None = None) -> dict`; payload line →
    `sock.sendall((json.dumps({"cmd": cmd, **(extra or {})}) + "\n").encode("utf-8"))`;
    extend the docstring: "extra payload keys are merged after 'cmd'; the daemon ignores
    unknown keys, so old daemons fail safe (unknown command → exit 1)".
  - format_result: extend the docstring's branch list ("session → the recovered session
    text, exactly") and add AFTER the status branch, before the final toggle/start/stop/
    cancel return:
      if cmd == "session":
          # P1.M6.T2.S3 (§4.2sexies R.6): stdout is EXACTLY the recovered text (print adds
          # the single terminal newline); truncation is reported on stderr by main(); the
          # ok:false none-case never reaches here (first branch → exit 1).
          session = response.get("session") or {}
          return session.get("text", "") or "", 0
  - NEW helper (place after send_command/_send_command_with_loading_hint):
      def _copy_session_to_clipboard(text: str) -> tuple[bool, str]:
          """Stage `text` on the Wayland CLIPBOARD — exact UTF-8 bytes, NO added newline —
          and verify the round-trip. Returns (ok, error detail).

          Stage: wl-copy FORK MODE (no --foreground — it blocks until the selection is
          replaced; a CLI hang risk). Source-verified: wl-copy's parent exits 0 only AFTER
          set_selection + roundtrip, so exit 0 means the selection is registered; the
          forked child serves it until the next selection (normal paste UX). Verify:
          `wl-paste --no-newline` stdout must BYTE-EQUAL the staged bytes (wl-paste always
          appends \\n without --no-newline); bounded poll — a fresh connection can see the
          new selection one event-loop turn later. PRIMARY untouched (no --primary); no
          --paste-once (a history-manager read would consume the offer); no --trim-newline
          (we add no newline). NEVER types/erases/submits: the only subprocesses are
          wl-copy and wl-paste (PRD §4.2sexies R.6; research/wlclipboard_external.md).
          """
          wl_copy = _resolve_tool(_WL_COPY, "wl-copy")
          if wl_copy is None:
              return False, "wl-copy not found (install wl-clipboard)"
          wl_paste = _resolve_tool(_WL_PASTE, "wl-paste")
          if wl_paste is None:
              return False, "wl-paste not found (install wl-clipboard)"
          payload = text.encode("utf-8")
          try:
              staged = subprocess.run(
                  [wl_copy, "--type", "text/plain;charset=utf-8"],
                  input=payload,
                  capture_output=True,
                  timeout=_WL_STAGE_TIMEOUT_S,
              )
          except subprocess.TimeoutExpired:
              return False, "wl-copy timed out staging the clipboard"
          if staged.returncode != 0:
              lines = staged.stderr.decode("utf-8", errors="replace").strip().splitlines()
              first = lines[0] if lines else f"exit {staged.returncode}"
              return False, f"wl-copy failed: {first}"
          deadline = time.monotonic() + _WL_VERIFY_DEADLINE_S
          while True:
              try:
                  readback = subprocess.run(
                      [wl_paste, "--no-newline"],
                      capture_output=True,
                      timeout=_WL_PASTE_TIMEOUT_S,
                  )
              except subprocess.TimeoutExpired:
                  return False, "wl-paste timed out verifying the clipboard"
              if readback.returncode == 0 and readback.stdout == payload:
                  return True, ""
              if time.monotonic() >= deadline:
                  return False, (
                      "clipboard verification failed (content did not match within "
                      f"{_WL_VERIFY_DEADLINE_S:.0f}s)"
                  )
              time.sleep(_WL_VERIFY_POLL_S)
  - _build_parser: add the flag + docs:
      parser.add_argument(
          "--copy",
          action="store_true",
          help="with 'session': copy the recovered text to the Wayland clipboard (exact "
          "bytes, no added newline, PRIMARY untouched) instead of printing it",
      )
    epilog → "subcommands: toggle, start, stop, status, quit, cancel, session [--copy]  (see
    the project README for the full usage table)"; positional help →
    "toggle | start | stop | status | quit | cancel | session".
  - main(): after the _COMMANDS validation block, add:
      if args.copy and cmd != "session":
          print("voicectl: --copy applies only to the 'session' command", file=sys.stderr)
          return _EX_USAGE
    In the send step, pass the flag on the wire (session is NOT an arm command — plain
    send_command):
      extra = {"copy": True} if (cmd == "session" and args.copy) else None
      ... response = send_command(socket_path, cmd, extra=extra)   # non-arm branch
    After `text, code = format_result(cmd, response)`, add the session orchestration BEFORE
    the final print:
      if cmd == "session" and code == 0:
          session = response.get("session") or {}
          if session.get("truncated"):
              dropped = session.get("finals_dropped", 0)
              print(
                  f"voicectl: session was truncated ({dropped} finals dropped by the "
                  "1 MiB cap; the newest text that fits is shown)",
                  file=sys.stderr,
              )
          if args.copy:
              copied, detail = _copy_session_to_clipboard(text)
              if not copied:
                  print(f"voicectl: {detail}", file=sys.stderr)
                  return 1
              print(f"copied {len(text)} chars")
              return 0
  - MODE A DOCS: module docstring — Subcommands list gains:
      session  print the most recent COMPLETED dictation session (arm→disarm recovery,
               R.6; never a moving draft). --copy stages it on the Wayland CLIPBOARD
               instead — exact bytes, no added newline, PRIMARY untouched, never
               types/erases/submits. Exit 1 when no completed session exists.
    Usage line gains session (keep the exit-code table unchanged). main() docstring: add one
    line noting the session/--copy flow + the 64 rule for --copy-with-non-session.
  - RUN: .venv/bin/python -m py_compile voice_typing/ctl.py

Task 3: MODIFY tests/test_control_socket.py — stub + dispatch/socket tests.
  - _StubDaemon: ctor gains `session=None` param; add:
      self._session = session
      self.session_calls: list[bool] = []
      def session_reply(self, copy: bool = False):
          # P1.M6.T2.S3: mirror VoiceTypingDaemon.session_reply() — records the copy flag,
          # returns the canned shape (None -> the no-completed-session error).
          self.session_calls.append(bool(copy))
          if self._session is None:
              return {"ok": False, "error": "no completed session yet"}
          return {"ok": True, "session": dict(self._session)}
  - TESTS (Layer A _disp / Layer B _send):
    1. test_dispatch_session_returns_reply_verbatim — stub(session={...full S2 shape...});
       _disp({"cmd": "session"}) == {"ok": True, "session": {...}} (verbatim passthrough,
       NOT via _arm_response — no status keys beyond "session").
    2. test_dispatch_session_reads_copy_flag — _disp({"cmd": "session", "copy": True});
       stub.session_calls == [True]; with copy absent -> [False] (extra-payload read pin).
    3. test_dispatch_session_none_is_error — default stub →
       {"ok": False, "error": "no completed session yet"}.
    4. test_socket_session_round_trip — server fixture: _send(path, {"cmd": "session"}) ==
       canned reply (real AF_UNIX path), plus a none-variant.
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py -q

Task 4: MODIFY tests/test_voicectl.py — stub + CLI tests.
  - _StubDaemon (:192): same session_reply addition (canned `session` ctor param,
    session_calls list).
  - running_server fixture: NO signature change needed — tests set
    `srv._daemon._session = <canned>` (ControlServer stores the daemon as self._daemon;
    the stub is test-owned). (A fixture param is acceptable if preferred.)
  - TESTS (monkeypatch discipline per the loading-hint tests):
    5. test_format_session_prints_text_exactly — format_result("session", {"ok": True,
       "session": {...}}) == (text, 0); no metadata in the string.
    6. test_format_session_none_is_error_exit1 — ok:false reply → ("error: no completed
       session yet", 1) (pins the none-case riding the first branch).
    7. test_main_session_round_trip_prints_text — running_server + canned session →
       main(["session"]) == 0; capsys out == text + "\n" (byte-exact stdout purity).
    8. test_main_session_none_exits_1 — default stub → main(["session"]) == 1; stdout has
       the error; and NO subprocess: monkeypatch ctl.subprocess.run to raise
       AssertionError if called (clipboard-untouched pin).
    9. test_main_session_truncation_warns_on_stderr — truncated session → exit 0; stdout
       == text; stderr contains "truncated" and the finals_dropped count; stdout has NO
       warning text.
    10. test_main_session_copy_calls_helper_with_exact_text — monkeypatch
        ctl._copy_session_to_clipboard → (True, ""); main(["session", "--copy"]) == 0;
        helper called ONCE with EXACTLY text; stdout == f"copied {len(text)} chars".
    11. test_main_session_copy_failure_exits_1 — helper → (False, "wl-copy failed: X") →
        exit 1; stderr contains the detail; stdout has no "copied".
    12. test_main_session_copy_sends_copy_flag_through_socket — running_server +
        monkeypatched helper; main(["session", "--copy"]) → stub.session_calls == [True]
        (full-stack wire pin: extra payload survived send_command → _dispatch).
    13. test_main_copy_flag_requires_session — main(["status", "--copy"]) == 64;
        stderr names --copy.
    14. test_copy_helper_stages_exact_bytes_no_newline — monkeypatch subprocess.run:
        wl-copy call argv contains ("--type", "text/plain;charset=utf-8"), NOT
        --primary/--paste-once/--trim-newline/--foreground; input == text.encode() EXACTLY
        (no trailing b"\n"); wl-paste call argv contains "--no-newline" and its stdout ==
        payload → (True, ""); the recorded call list contains ONLY wl-copy/wl-paste argv
        (never wtype/ydotool — the never-types pin).
    15. test_copy_helper_verify_retries_then_succeeds — first wl-paste returns wrong bytes
        (or exit 1), second matches → (True, "") (poll pin; shrink _WL_VERIFY_POLL_S via
        monkeypatch for speed).
    16. test_copy_helper_verify_timeout_fails — wl-paste never matches → (False, msg
        containing "verification failed"); bounded (monkeypatch the deadline small).
    17. test_copy_helper_missing_binary — monkeypatch ctl._WL_COPY to a nonexistent path
        AND shutil.which → None → (False, "wl-copy not found").
    18. test_copy_helper_wl_copy_error_surfaces_stderr — wl-copy returncode 1, stderr
        b"Failed to connect to a Wayland server\n..." → (False, detail containing that
        line).
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py -q

Task 5: CREATE tests/test_voicectl_session.py — real-daemon session_reply semantics.
  - PATTERN: mirror S2's landed tests/test_session_recovery.py daemon-driving fixtures
    (real VoiceTypingDaemon + fake host; drive _arm/on_final/_on_partial/_disarm
    synchronously; no CUDA, no subprocess, no live desktop). If its fixtures diverge from
    S2's PRP, adapt — the driving pattern is the contract.
  - TESTS:
    19. test_session_reply_none_maps_to_error — fresh daemon (store empty) →
        session_reply() == {"ok": False, "error": "no completed session yet"}.
    20. test_session_reply_completed_carries_snapshot — arm → accepted on_final("hello
        world") → disarm → session_reply() == {"ok": True, "session": {"text": "hello
        world", "truncated": False, ...}} (exact text; presence of finals/finals_dropped/
        tail_chars/ended_monotonic keys).
    21. test_session_reply_never_exposes_open_draft — complete session #1 → arm →
        _on_partial("moving draft tail") → session_reply() still session #1's text; the
        draft string appears NOWHERE in the reply.
    22. test_session_reply_log_is_counts_only — caplog: the served line matches
        "session recovery: session served copy=%d chars=%d truncated=%d" and does NOT
        contain the session text (R.6 log law).
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_voicectl_session.py -q

Task 6: VALIDATE — the full Validation Loop below; reconcile the G1 watch set + S1/S2
  suites against Task 0's baseline (identical numbers required). No git commit unless
  directed (message if so: "P1.M6.T2.S3: voicectl session [--copy] — R.6 recovery surface,
  wl-copy stage+verify, session_reply dispatch").
```

### Implementation Patterns & Key Details

```python
# PATTERN — main() session flow (complete; the ONLY main() changes beyond validation/send):
    text, code = format_result(cmd, response)
    if cmd == "session" and code == 0:
        session = response.get("session") or {}
        if session.get("truncated"):
            print(f"voicectl: session was truncated ({session.get('finals_dropped', 0)} "
                  "finals dropped by the 1 MiB cap; the newest text that fits is shown)",
                  file=sys.stderr)
        if args.copy:
            copied, detail = _copy_session_to_clipboard(text)
            if not copied:
                print(f"voicectl: {detail}", file=sys.stderr)
                return 1
            print(f"copied {len(text)} chars")
            return 0
    print(text)
    return code

# GOTCHA — why the none-case needs NO new client logic (G1):
#   {"ok": false, ...} → format_result's first branch → ("error: no completed session yet", 1)
#   → `if cmd == "session" and code == 0` is False → plain print + return 1. --copy never runs.

# GOTCHA — argparse dest: --copy → args.copy (bool, store_true). It never collides with the
#   positional args.cmd; `voicectl --copy` alone → cmd None → existing 64 path.

# PATTERN — subprocess mock shape for tests 14-16 (record, then replay):
calls = []
def fake_run(argv, **kwargs):
    calls.append((argv, kwargs))
    if argv[0].endswith("wl-copy"):
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
    return subprocess.CompletedProcess(argv, 0, stdout=kwargs_want_bytes, stderr=b"")
monkeypatch.setattr(ctl.subprocess, "run", fake_run)   # module-level subprocess — patch its run

# CRITICAL — do NOT use `with subprocess.Popen(...)` or .wait() on any wl-copy (G3): fork
#   mode's parent exit is the completion signal; the serving grandchild is wl-copy's own.
```

### Integration Points

```yaml
DAEMON (voice_typing/daemon.py):
  - "VoiceTypingDaemon.session_reply(copy=False) — beside session_snapshot(); reads S2's
     snapshot; None → ok:false; counts-only logger.info; ~14 lines."
  - "ControlServer._dispatch — `if cmd == \"session\": return
     self._daemon.session_reply(copy=bool(msg.get(\"copy\", False)))` after quit, before the
     unknown fallthrough."
  - "ControlServer class docstring protocol block — one session line."

CLIENT (voice_typing/ctl.py):
  - "_COMMANDS += 'session'  (order: append last)"
  - "send_command(socket_path, cmd, extra=None) → {\"cmd\": cmd, **(extra or {})}"
  - "format_result: `if cmd == \"session\": return (session text, 0)` after the status branch"
  - "_copy_session_to_clipboard(text) -> (bool, str) + _resolve_tool + _WL_* constants"
  - "_build_parser: --copy store_true; epilog/positional help list session"
  - "main(): --copy-with-non-session → 64; extra={\"copy\": True} on the wire; session
     orchestration block (truncation stderr → optional copy → print)"

TESTS:
  - "tests/test_control_socket.py: _StubDaemon.session_reply + tests 1-4"
  - "tests/test_voicectl.py: _StubDaemon.session_reply + tests 5-18"
  - "tests/test_voicectl_session.py: NEW, tests 19-22 (S2's daemon-driving pattern)"

NO config keys. NO state.json/feedback.py changes. NO hypr-binds.conf / install.sh / README
changes (the recovery bind is USER-assigned; README sync is P1.M7.T2.S1). NO edits to
session_recovery.py / streaming.py / bulk_controller.py.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
# bash-tool timeout: 60
.venv/bin/python -m py_compile voice_typing/ctl.py voice_typing/daemon.py \
  tests/test_voicectl.py tests/test_control_socket.py tests/test_voicectl_session.py && echo OK

.venv/bin/python - <<'EOF'
import inspect
import voice_typing.ctl as ctl, voice_typing.daemon as d
assert "session" in ctl._COMMANDS and len(ctl._COMMANDS) == 7
assert "extra" in inspect.signature(ctl.send_command).parameters
assert hasattr(d.VoiceTypingDaemon, "session_reply")
assert '"session"' in inspect.getsource(d.ControlServer._dispatch)
assert hasattr(ctl, "_copy_session_to_clipboard") and ctl._WL_COPY == "/usr/bin/wl-copy"
print("session wiring OK")
EOF
# Expected: OK + "session wiring OK". NO daemon is started; NO real clipboard is touched.
```

### Level 2: Unit Tests (Component Validation)

```bash
# This item's suites (bash-tool timeout 330 for each):
timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_control_socket.py \
  tests/test_voicectl_session.py -q
# Expected: all green (incl. every PRE-EXISTING test in the two modified files).

# Upstream contracts that must stay green untouched:
timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py -q        # S2's suite
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q           # S1's suite
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cancel or final or partial or arm or disarm"

# G1 watch set (numbers must IDENTICALLY match Task 0's baseline):
for f in test_streaming_commit test_zero_diff_rewind test_key_listener test_control_socket test_config; do
  timeout 300 .venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1; done
# Expected: green except test_streaming_commit's PRE-EXISTING reds (same counts as baseline;
# tests/G1_BASELINE.md is the recorded history — no new failures, no blanket skips).
```

### Level 3: Integration Testing (System Validation)

```bash
# The socket layer IS the integration layer (real AF_UNIX round-trip on tmp_path inside the
# test files — Layer B). NO live daemon is started for this item (AGENTS.md: never run the
# daemon in the foreground; voicectl always under timeout if invoked at all).

# CLI surface check (safe — --help exits 0 without contacting the daemon):
timeout 15 .venv/bin/voicectl --help | grep -i "session"
# Expected: the epilog line lists "session [--copy]".

# DO NOT run bare `voicectl session` in validation: the operator's real daemon may be live
# under systemd and that would exercise the REAL clipboard path. The mocked tests are the
# gate; a real-desktop smoke (arm → dictate → stop → session/--copy → wl-paste check) is the
# OPERATOR's manual acceptance, not an automated one.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Contract-coverage sweep — every clause of the item contract has a green named test:
timeout 120 .venv/bin/python -m pytest tests/test_voicectl.py -q -k "session or copy or clipboard" -v
timeout 120 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_voicectl_session.py \
  -q -k "session" -v
# Expected names cover: none/error-exit-1, no-subprocess (clipboard untouched), exact bytes
# (no newline), verify retry/timeout, missing binary, wl-copy error, never-types (only
# wl-copy/wl-paste argv), truncation stderr+reply, open-draft invisibility, copy flag on the
# wire, --copy-with-non-session 64, counts-only log.

# Scope-wall sweep (must all be silent):
grep -n "session" hypr-binds.conf install.sh README.md           # → no hits
grep -rn "wtype\|ydotool\|typing_backends" voice_typing/ctl.py   # → no hits
git status --short                                               # → only the 5 declared files
```

## Final Validation Checklist

### Technical Validation

- [ ] L1 py_compile + wiring asserts OK; `--help` lists `session [--copy]`.
- [ ] `tests/test_voicectl.py`, `tests/test_control_socket.py`, `tests/test_voicectl_session.py`
      fully green (new + pre-existing).
- [ ] S1 (`test_bulk_dispatch`) + S2 (`test_session_recovery`) suites green untouched.
- [ ] G1 watch set numbers IDENTICAL to the Task 0 baseline (incl. pre-existing
      `test_streaming_commit` reds — reconciled, not newly broken, not skipped).

### Feature Validation

- [ ] `voicectl session` prints exactly the most recent COMPLETED session text (stdout purity
      pinned byte-exact); never an open draft (daemon-level test).
- [ ] `--copy`: exact UTF-8 bytes staged on CLIPBOARD, byte-verified via `wl-paste
      --no-newline`; no `--primary`/`--paste-once`/`--trim-newline`/`--foreground`; stdout
      `copied N chars`; exit 0.
- [ ] None-case: exit 1, error on stdout, ZERO subprocesses (clipboard untouched).
- [ ] Copy failures (missing binary / wl-copy error incl. not-on-Wayland / verify timeout):
      stderr detail, exit 1.
- [ ] Truncation: `truncated` + `finals_dropped` in the daemon reply AND a stderr warning;
      copy still delivers the truncated text.
- [ ] Never types/erases/submits: only wl-copy/wl-paste argv ever recorded (test-pinned);
      no typing_backends import in ctl.py.
- [ ] `--copy` with non-session → 64; unknown/missing command → 64; daemon down → 2; all
      existing exit codes and commands behave identically (suites green).
- [ ] Old-daemon fail-safe holds: `{"cmd":"session"}` against a daemon without the branch →
      `unknown command: 'session'` → client exit 1, clipboard untouched.

### Code Quality Validation

- [ ] Adds confined to the 5 declared files; scope walls respected (no hypr-binds.conf, no
      install.sh, no README, no config keys, no state.json, no feedback.py, no
      session_recovery/streaming/bulk_controller edits).
- [ ] `format_result` remains PURE (no I/O); `send_command` timeout semantics unchanged;
      `_dispatch` never-raises contract preserved; every wl subprocess timeout-bounded.
- [ ] Mode A docs: ctl.py module docstring (Subcommands + Usage) and `--help` epilog +
      positional help list session; ControlServer protocol docstring line added.

### Documentation & Deployment

- [ ] New log line is counts/times only (no session text) — caplog-pinned.
- [ ] No new env vars or config keys; `_WL_*` are code constants with a `shutil.which`
      fallback (documented in the helper docstring).
- [ ] README intentionally NOT updated here — P1.M7.T2.S1 owns the doc sync (recorded as a
      scope wall, not an omission).

---

## Anti-Patterns to Avoid

- ❌ Don't invent a `{"ok": true, "session": null}` shape for the none-case — it must ride
  the existing ok:false → exit-1 path (one shape, one handler, clipboard untouched by
  construction).
- ❌ Don't put metadata on stdout for `voicectl session` (breaks piping); truncation warnings
  and copy confirmations excepted per the exit-code table.
- ❌ Don't use `--foreground` wl-copy, `--paste-once`, `--primary`, or `--trim-newline` —
  each is a documented trap (hang risk / offer consumption by history managers / PRIMARY
  mutation / eating a legitimate trailing newline).
- ❌ Don't add a trailing newline to the staged bytes, and don't verify without
  `--no-newline` (wl-paste ALWAYS appends `\n`).
- ❌ Don't fall back to typing (wtype/ydotool) when the clipboard fails — a blocked copy is
  a REPORTED failure (R.3: no typing fallback in this mode).
- ❌ Don't read the recovery store any way except `session_snapshot()`/`session_reply()` —
  draft invisibility and the exclusion rules live there (S2's gates).
- ❌ Don't add a keybind, don't touch hypr-binds.conf or install.sh — the bind is
  USER-assigned (R.6).
- ❌ Don't touch README (P1.M7.T2.S1), config, state.json, or feedback.py.
- ❌ Don't run the daemon in the foreground, the E2E/CUDA suites, or anything against the
  real desktop clipboard in automated validation (AGENTS.md; R.7).
- ❌ Don't break `test_dispatch_status_has_all_keys` — the session reply is its own shape;
  never spread session keys into the status reply.

---

## Confidence Score

**9/10.** The feature is small and every ingredient is pre-verified: the daemon dispatch site
and both test stubs were reconnoitered live (with the S2-drift re-grep mandated as Task 0);
the wire reply, exit-code table, and none-case routing follow patterns already proven in this
codebase (ok:false→exit-1, cancel's dedicated reply shape, text-field precedent in status);
the clipboard mechanics are source-verified upstream (fork-after-set_selection semantics,
`--no-newline` byte-verify) AND lab-proven in-repo (ghostty_probe); the d2 §4 recipe is
quoted verbatim in research with one justified deviation (`--foreground` → fork mode,
rationale in design_decisions.md D4). Residual risks: (1) S2's landed `session_snapshot`
shape drifts from its PRP — mitigated by defensive `.get` everywhere plus Task 20's
exact-shape test failing loudly; (2) the wl-paste verify poll could flake on a slow
compositor in a hypothetical real run — irrelevant to the mocked tests, and the poll is
bounded; (3) both stub files must gain `session_reply` (G9) — a missed one surfaces as an
immediate AttributeError in the new dispatch tests, not a silent gap.

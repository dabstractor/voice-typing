name: "P1.M1.T1.S4 — Align installer and CLI generic usage"
description: >

---

## Goal

**Feature Goal**: Make the two user-facing usage surfaces — `voicectl`'s help (`voice_typing/ctl.py`: module docstring + argparse epilog + the wedged-socket runtime hint) and `install.sh`'s printed usage/troubleshooting block — describe ONLY the supported generic product: the working stream/block arm commands, the generic fragment cancel (`voicectl cancel`), and the explicit session copy (`voicectl session [--copy]`). Remove every stale claim of the retired Rev-4 bulk-delivery experiment and of shipped shortcuts; name `systemctl --user stop voice-typing` as the out-of-band stop for the user unit `install.sh` installs whenever the control socket is nonresponsive; and reuse S1's actionable migration wording for `output.delivery="bulk-text"`. Pin all of it with static/help assertions and stub service/tools. **No binding changes, no installer-behavior change, and `install.sh` is never run against the user's service.**

**Deliverable** (Mode A — the docs update IS this work; exactly four files):
1. `voice_typing/ctl.py` — reword the `status` docstring line; add a Troubleshooting block to the module docstring; append three lines to the `_build_parser` epilog; change the remedy inside the `daemon wedged` `ValueError` (`:243-247`); relabel the delivery-fields comment (`:170-172`). No change to `_COMMANDS`, `_ALIASES`, `format_result` output, `send_command` logic, exit codes, or argument shape.
2. `install.sh` — comment-only fix of the header's stale plan id; ONE added stderr line in the NOT-active branch; ONE added usage line (keybinds user-owned); a clarifier on the existing wedged-service line; S1's wording appended to the `config :` line. Every changed line is a `#` comment or an `echo`.
3. `tests/test_voicectl.py` — new help/docstring assertions + a wedged-hint behavioral assertion (fake socket), following the file's existing `test_help_surfaces_list_all_commands` pattern.
4. `tests/test_systemd_unit.py` — a static install.sh text assertion following the file's existing `test_install_sh_offline_grep_and_summary` pattern.

**Success Definition**:
- (a) `timeout 20 .venv/bin/voicectl --help` contains `systemctl --user stop voice-typing`, `output.delivery="bulk-text" is retired`, `set delivery = "stream-edit"`, and `user-owned`; and still lists every entry of `ctl._COMMANDS` (existing sweep stays green).
- (b) The only `bulk` token in `voice_typing/ctl.py` and in `install.sh` is inside S1's retirement phrase `output.delivery="bulk-text" is retired` (source-level pin).
- (c) `voicectl status` output is byte-identical before/after (the `delivery: stream-edit (inactive)` rendering is KEPT — S2 Critical #3).
- (d) `git diff -U0 install.sh | grep -E '^[+-][^+-]'` yields only lines beginning with `#` or `echo` (whitespace-insensitive) — zero installer behavior change; `git diff --stat -- systemd/voice-typing.service` is empty.
- (e) `timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_voicectl_session.py tests/test_systemd_unit.py -q` → all passed; the 59-test ctl baseline grows only by S4's new tests; `bash -n install.sh` clean.
- (f) `install.sh` was never executed in full (no `uv sync`, no unit restart, no launcher symlink, no model prefetch) — validated statically + via a stubbed render of ONLY its print tail.

## User Persona

**Target User**: (1) The operator who just ran `install.sh` or hit a wedged daemon and reads the printed usage / `voicectl --help` to learn what to type next; (2) the downstream subtasks **P1.M1.T2.S5** (bounded focus-based context starts — it will ADD a command and must publish it in the four places this PRP defines) and **P1.M2.T4.S1** (final README sync, which mirrors this wording).

**Use Case**: The daemon stops answering the control socket. The user runs `voicectl status`; after `VOICECTL_TIMEOUT` seconds it prints `daemon wedged: no reply within Ns — … Stop the installed user unit out of band with 'systemctl --user stop voice-typing' …`. The user runs exactly that; the unit (which would otherwise sit wedged) is stopped. Or: after `install.sh`, the unit is "NOT active" and the stderr hint names the retired `output.delivery="bulk-text"` key and both fixes.

**User Journey**: install.sh prints usage → user binds `voicectl toggle-stream` in their OWN compositor config (the installer sets no shortcut) → first arm → later a wedge or a config-load failure → the help/installer text names the journal command, the out-of-band stop, and the config fix, with nothing pointing at the retired bulk mode.

**Pain Points Addressed**: a `--help` that is silent about the one situation where voicectl cannot help (a nonresponsive socket) and whose runtime hint suggests only `restart`; a `status` help line advertising a delivery state machine that no longer varies; an installer whose failure branch gives no config-fix hint; and nothing preventing a future "we ship a keybind" or bulk claim from creeping back into these surfaces.

## Why

- **The usage text is the product's front door.** `install.sh:21` declares its stdout "IS the user-facing install/usage quick-start (Mode A docs)"; `ctl.py`'s docstring/epilog are what `voicectl --help` renders. After S1 (config rejection), S2 (daemon detach) and S3 (recorder detach), these are the last places that still describe the retired experiment's shape.
- **The out-of-band stop is a safety fact.** `system_context.md` (§Preserve and retire, para 3): "The existing systemd unit does not need a shortcut or an editor dependency; `systemctl --user stop voice-typing` remains the out-of-band stop for users of that unit." The unit has `Restart=on-failure` (`systemd/voice-typing.service:51`) — an explicit `stop` is never overridden, whereas a hint that says only "restart" leaves a user with a wedged daemon and no dependable way down. AGENTS.md documents that the control socket has no server-side read timeout, so a client-side `VOICECTL_TIMEOUT` cannot be the whole remedy.
- **S1 and S2 explicitly hand the wording to this item.** S1 PRP :147-149 ("S2's daemon-side and S4's installer/CLI messaging reuse this") and :267; S2 PRP :280-281 ("P1.M1.T1.S4 … consumes S1's migration wording; … S4's usage text mirrors it"), :147-148/:393 (keep the delivery rendering).
- **Keys are user-owned by spec** (PRD §4.10; layout comment "User-owned shortcuts"). No shipped-shortcut claim exists today; the pin keeps it that way.

## What

User-visible text only (plus the one runtime error string). No command is added, removed, renamed or re-routed; no exit code changes; no config key; no unit change.

### Success Criteria

- [ ] `voicectl --help` and `ctl.__doc__` each contain: `systemctl --user stop voice-typing`, `journalctl --user -u voice-typing`, `output.delivery="bulk-text" is retired`, `set delivery = "stream-edit"`, `user-owned`.
- [ ] The wedged-socket `ValueError` still begins with `daemon wedged: no reply within` (so existing `match=` tests hold) and contains `systemctl --user stop voice-typing`.
- [ ] The `status` docstring line no longer says "delivery (mode/state, reason/op when present)".
- [ ] `install.sh` keeps verbatim: the `toggle|start|stop|status|cancel|session|quit` usage line, both block/stream example fragments, `voicectl cancel drops the pending fragment`, the `voicectl session [--copy]` line with `copied N chars`, and `stop a wedged service: systemctl --user stop voice-typing`.
- [ ] `install.sh` adds: the user-owned keybind line, the S1 wording in the NOT-active branch (stderr) and on the `config :` line.
- [ ] In both files the substring `bulk` occurs ONLY inside `output.delivery="bulk-text" is retired`.
- [ ] No user-facing text asserts or implies that a shortcut/keybind/hotkey is installed, shipped or bound by this tool.
- [ ] `voicectl status` rendering unchanged (`delivery: stream-edit (inactive)` still printed from the same fields).
- [ ] Four-file diff: `voice_typing/ctl.py install.sh tests/test_voicectl.py tests/test_systemd_unit.py`; `systemd/voice-typing.service` untouched; every changed `install.sh` line is a comment or an `echo`.
- [ ] `install.sh` never executed end-to-end during the work.

## All Needed Context

### Context Completeness Check

_Pass._ Every edit site is enumerated with verified line numbers against the live files at HEAD `ae7db9f` (ctl.py 480 lines; install.sh 213 lines, `bash -n` clean); the exact replacement text is copy-ready; the existing test seams that will sweep the new text are named with their assertions; the sibling contracts (S1 landed, S2/S3 in flight) are confirmed disjoint from this edit set and their keep-constraints are quoted; the baseline (59 passed) is recorded; the two validation styles the item requires (static/help assertions; stub service/tools) each have a concrete, bounded recipe that never touches the user's daemon.

### Verified Current State (this session)

- `voicectl --help` today renders: description ("Control the voice-typing daemon. … Exits 0 …, 2 if the daemon is not running, 64 on a usage error"), epilog `subcommands: toggle, start, stop, status, quit, cancel, session [--copy]  (see the project README for the full usage table)` + the per-session output-mode paragraph. `grep -i "systemctl\|bulk\|delivery\|stop voice-typing"` on it → **no hits**.
- `ctl.py:243-247` wedged raise: `f"daemon wedged: no reply within {timeout:.0f}s " "(systemctl --user restart voice-typing to recover)"`.
- `ctl.py:22-23` status docstring: `status   pretty-print listening + mode + phase + partial + last final + uptime + device + mic` / `+ context-prompt + delivery (mode/state, reason/op when present)`.
- `ctl.py:170-176`: comment "P1.M3.T3.S2: bulk-delivery status surface (PRD §4.2sexies R.5) …" then `delivery_mode/delivery_state/delivery_reason/delivery_op = response.get(...)`. This is the ONLY `bulk` occurrence in ctl.py.
- `install.sh:206-210` (usage block) and `:213` (config line) — text as quoted in the research note §1; no `bulk`, no shortcut text in the file.
- S1 message (`voice_typing/config.py:204-207`, two adjacent literals): `output.delivery="bulk-text" is retired: remove the key (default "stream-edit") or set delivery = "stream-edit"`.
- `tests/test_voicectl.py` ≈:460-498 `test_help_surfaces_list_all_commands` (all `_COMMANDS` in `format_help()` AND `ctl.__doc__`; no `toggle-lite`/`start-lite` in either); ≈:500-510 `test_cancel_in_commands_docstring_and_epilog` (`_COMMANDS` exact tuple; `cancel` in docstring + epilog). `tests/test_systemd_unit.py` ≈:60-64 install.sh path helper; :201-215 `test_install_sh_offline_grep_and_summary` (static text).
- Baseline: `timeout 120 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_voicectl_session.py -q --tb=no` → **59 passed in 4.74s**.

### Documentation & References

```yaml
# THE SITE MAP (authoritative for this item)
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: §Preserve and retire, para 3: "ctl.py:_build_parser/main and install.sh already mention
        stream/block and explicit session copy. … The existing systemd unit does not need a shortcut
        or an editor dependency; systemctl --user stop voice-typing remains the out-of-band stop for
        users of that unit." Also: the control socket's server read path has no deadline — the
        client-side VOICECTL_TIMEOUT is why voicectl returns at all on a wedge.
  critical: "Keep stream/block examples, generic fragment cancel, explicit session copy. 'Shortcut'
            is named only to say it is NOT shipped."

# THE MIGRATION WORDING TO REUSE (LANDED ae7db9f)
- file: voice_typing/config.py
  why: :204-207 — the exact S1 message whose two actionable verbs ('remove the key (default
        "stream-edit")' / 'set delivery = "stream-edit"') both surfaces must reproduce verbatim.
  pattern: 'output.delivery="bulk-text" is retired: remove the key (default "stream-edit") or set delivery = "stream-edit"'
  gotcha: "Do NOT edit config.py. Copy the wording; do not paraphrase it — S4's tests pin the phrase
          'output.delivery=\"bulk-text\" is retired' and 'set delivery = \"stream-edit\"'."

# SIBLING CONTRACTS (disjoint edit sets)
- file: plan/009_ef3b49b0fc0d/P1M1T1S1/PRP.md
  why: :147-149 "ACTIONABLE MESSAGE … BOTH actionable verbs … S4's installer/CLI messaging reuse this";
        :267 "P1.M1.T1.S4 (installer + CLI generic usage): reuses the migration wording for any usage text."
- file: plan/009_ef3b49b0fc0d/P1M1T1S2/PRP.md
  why: :147-148 + :393 "KEEP THE FEEDBACK DELIVERY SURFACE … ctl.py:170-199 render
        'delivery: stream-edit (inactive)'. Keep … ctl.py's rendering"; :115/:132/:288 list ctl.py as
        READ-ONLY for S2 (it edits only daemon.py + its test quarantine); :280-281 hands usage text to S4.
  critical: "S4 may reword the COMMENT at ctl.py:170-172 but MUST NOT remove/alter the delivery fields
            or the rendered status line. S2's validation runs tests/test_voicectl.py — S4's additions
            there must be green and must not edit S2-owned tests (test_daemon.py,
            test_session_recovery.py, the bulk suites, pyproject.toml)."
- file: plan/009_ef3b49b0fc0d/P1M1T1S3/PRP.md
  why: S3 edits ONLY voice_typing/recorder_host.py + tests/test_prompt_engine.py. Its source pin
        (inspect.getsource(recorder_host) has no 'bulk'/'beam') does NOT read ctl.py — S4 cannot break it.
  critical: "No overlap. Do not touch either of S3's files."

# THE SUPPLIED UNIT (READ-ONLY; the reason 'stop' is the named remedy)
- file: systemd/voice-typing.service
  why: :51 Restart=on-failure (an explicit `systemctl --user stop` is never overridden by it);
        :74 KillMode=mixed; :85 TimeoutStopSec=15; :59 ExecStopPost ducking heal; :93 WantedBy=graphical-session.target.
  gotcha: "NOT in S4's edit set. 'Do not ship binding changes' ⇒ the unit, the launcher symlink logic
          (install.sh:186-189) and any compositor config stay exactly as they are."

# THE EXISTING TEST SEAMS TO EXTEND
- file: tests/test_voicectl.py
  why: ≈:460-498 test_help_surfaces_list_all_commands (format_help() + ctl.__doc__ positive/negative
        sweep); ≈:500-510 test_cancel_in_commands_docstring_and_epilog; the file's fake control-socket
        fixture + its existing wedged test (grep 'wedged' in the file first).
  pattern: "help_text = ctl._build_parser().format_help(); assert needle in help_text / in ctl.__doc__"
  gotcha: "NEVER write 'toggle-lite' or 'start-lite' into the docstring or epilog — the existing sweep
          forbids it. The alias stays an undocumented compatibility shim (ctl.py:80)."
- file: tests/test_systemd_unit.py
  why: ≈:60-64 the install.sh path helper; :201-215 test_install_sh_offline_grep_and_summary — the
        precedent for STATIC assertions on install.sh text (the installer is never executed in tests).
  pattern: "text = <helper>().read_text(); for needle in (...): assert needle in text, f'install.sh is missing {needle!r}'"

# THE SPEC
- docfile: plan/009_ef3b49b0fc0d/prd_snapshot.md
  why: §4.8 voicectl (exit 0/1/2/64; one command per invocation); §4.9 systemd user service;
        §4.10 "User-owned shortcuts" (nothing is installed); §5 Installation (install.sh prints usage);
        §4.1 layout ("install.sh # idempotent: uv sync, model prefetch, service install");
        §4.2sexies is "Legacy bulk text delivery experiment (Rev 4 reference, superseded)".
  critical: "PRD §4.10 is why the help says keybinds are user-owned. Do not add bind examples that
            name a specific compositor config file as if the tool wrote it."

# THIS ITEM'S RESEARCH NOTE
- docfile: plan/009_ef3b49b0fc0d/P1M1T1S4/research/usage_surfaces_findings.md
  why: §1 line map of both surfaces + the unit; §2 the four precise gaps; §3 test seams + baseline;
        §4 the usage-baseline contract for P1.M1.T2.S5; §5 README lines handed to P1.M2.T4.S1; §6 validation decisions.
  section: "§1 (line map) and §4 (usage-baseline contract) are load-bearing."

# REPO SAFETY RULES (READ BEFORE ANY COMMAND)
- file: AGENTS.md
  why: Two timeouts on every non-trivial command; `voicectl` always under `timeout 15/30`; never run
        the daemon in the foreground; /tmp is RAM — bound scratch, `mktemp -d` + EXIT trap; PATH shims
        must never `exec` a bare name.
  critical: "`install.sh` restarts the user's unit, runs `uv sync`, prefetches models and writes a
            launcher symlink. NEVER run it in full. `timeout 15 .venv/bin/voicectl status` is the ONLY
            live-daemon command this PRP needs, and only as an optional before/after comparison."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── ctl.py                      # 480 lines. docstring :10-34; _COMMANDS :56-68; _ALIASES :80; wedged raise :243-247;
│                               #   delivery fields comment :170-176; _build_parser :340-376 (epilog :355-362)   ← EDIT
├── config.py                   # S1 wording :204-207                                                                      ← READ-ONLY
├── daemon.py                   # S2 (in flight) — reports delivery_mode/state as constants :2750-2753                       ← NOT S4's
└── recorder_host.py            # S3 (in flight)                                                                            ← NOT S4's
install.sh                      # 213 lines. header :21-22; print block :191-213 (usage :206-209, wedged :210, config :213)   ← EDIT
systemd/voice-typing.service    # 93 lines. Restart=on-failure :51; TimeoutStopSec=15 :85                                      ← READ-ONLY
tests/
├── test_voicectl.py            # fake-socket ctl suite; help sweep ≈:460-498; cancel pin ≈:500-510                           ← EDIT (add tests)
├── test_voicectl_session.py    # session/--copy suite (no edit)                                                             ← GATE
└── test_systemd_unit.py        # unit/launcher/installer static tests; install.sh helper ≈:60-64; :201-215                  ← EDIT (add test)
README.md                       # stale bulk section :230-262 — P1.M2.T4.S1's                                               ← NOT S4's
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/ctl.py             # MODIFY: status docstring line; +Troubleshooting block in module docstring; +3 epilog lines;
                                #          wedged remedy → 'systemctl --user stop voice-typing' (prefix kept); comment relabel :170-172
install.sh                      # MODIFY: header comment :21-22; +1 stderr line (NOT-active branch); +1 usage line (keybinds);
                                #          clarifier on :210; S1 wording on :213.  ONLY '#'-comment and `echo` lines change.
tests/test_voicectl.py          # MODIFY: +test_help_troubleshooting_names_out_of_band_stop_and_migration
                                #          +test_voicectl_source_has_no_bulk_surface_beyond_migration_hint
                                #          + wedged-hint assertion (extend/add next to the existing wedged test)
tests/test_systemd_unit.py      # MODIFY: +test_install_sh_usage_is_generic_and_names_out_of_band_stop (static)
# NOTHING ELSE. systemd/voice-typing.service, README.md, daemon.py, recorder_host.py, config.py untouched.
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — THE EXISTING HELP SWEEP IS A TWO-WAY GATE. test_help_surfaces_list_all_commands asserts EVERY
# ctl._COMMANDS entry appears in _build_parser().format_help() AND in ctl.__doc__, and that 'toggle-lite' /
# 'start-lite' appear in NEITHER. S4 adds text only — but never write the lite names into the docstring/epilog,
# and never delete a command name while rewording the status line.

# CRITICAL #2 — KEEP THE "daemon wedged: no reply within" PREFIX BYTE-IDENTICAL. Existing tests match on it
# (and users/scripts may). Change ONLY the parenthesized remedy. Precheck: grep -rn "to recover" tests/ voice_typing/
# and update any EXACT-string assertion (keep the 'wedged' match working).

# CRITICAL #3 — DO NOT TOUCH format_result's DELIVERY RENDERING (ctl.py:177-199) OR THE FOUR delivery_* READS
# (:173-176). S2 Critical #3 keeps `delivery: stream-edit (inactive)`. S4 only relabels the comment above them
# (without the token 'bulk') and the help prose that advertised "mode/state, reason/op".

# CRITICAL #4 — THE WORD "bulk" IS ALLOWED IN EXACTLY ONE PHRASE PER FILE:
#     output.delivery="bulk-text" is retired
# Everything else (comments included) must avoid the token so the source-level pin (count equality) holds.
# Word the :170 comment as "the alternate delivery experiment was retired (P1.M1.T1.S1 config rejection,
# P1.M1.T1.S2 daemon detach)".

# CRITICAL #5 — "NO SHIPPED-SHORTCUT CLAIM" MEANS POSITIVE + NEGATIVE. Positive: the exact token 'user-owned'
# appears in ctl.__doc__, the epilog, and install.sh. Negative: no phrase like "shortcut is installed",
# "we bind", "binds are installed", "sets up a keybind", or any file path a compositor config would own.
# Descriptive prose about the USER's own binds ("two keybinds can pick either mode") is fine — keep it.

# CRITICAL #6 — NEVER RUN install.sh IN FULL (restarts the unit, uv sync, model prefetch, launcher symlink).
# Static text assertions are the test. The OPTIONAL render (L3) executes ONLY the step-(7) print tail
# (`sed -n '/^# --- (7) print usage/,$p'`) under a 2-line `systemctl` stub that does `exit "${SYSTEMCTL_STUB_RC:-0}"`
# with NO `exec` (no recursion vector), PATH prepended for that single `bash` call, `mktemp -d` + `trap … EXIT`.

# GOTCHA #7 — THE PRINT TAIL'S ONLY EXTERNAL CALL IS `systemctl --user is-active --quiet voice-typing.service`
# (install.sh:194) and its variables are $REPO, ${VERDICT:-unknown}, $CFG_DIR — all env-supplied, so the tail runs
# standalone. It prints the NOT-active hint to STDERR (>&2): capture with 2>&1.

# GOTCHA #8 — BASH QUOTING. Inside the double-quoted echo strings, write \" for literal quotes
# (echo "… output.delivery=\"bulk-text\" is retired …"). `$CFG_DIR` and `$REPO` must stay unescaped so they expand.

# GOTCHA #9 — ARGPARSE RENDERS THE EPILOG VERBATIM (RawDescriptionHelpFormatter, :349) and textwrap is NOT re-wrapping
# it — so keep each epilog line < ~90 cols yourself and never break the needle
# 'systemctl --user stop voice-typing' across two string literals with a \n between.

# GOTCHA #10 — CONCURRENT SIBLINGS. `git status` already shows S2/S3 files modified (pyproject.toml, test_daemon.py,
# test_prompt_engine.py, test_session_recovery.py, tools/lab-tests/…). The scope gate checks S4's FOUR files are
# present in the diff; other entries are expected and must be reported, never reverted or "fixed".

# GOTCHA #11 — TWO TIMEOUTS ON EVERY PYTEST/CLI COMMAND (AGENTS.md Rule 1): inner GNU `timeout`, bash-tool timeout above.
# The ctl/systemd suites are CPU-only (no CUDA) — `timeout 300` is ample. `voicectl` invocations: `timeout 20`.
```

## Implementation Blueprint

### Data models and structure

None. No new commands, config keys, wire keys or types. `_COMMANDS`, `_ALIASES`, the argparse signature (`cmd`, `--copy`) and all exit codes are unchanged.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PRECHECK — baselines and the three facts the edits depend on.
  - RUN: git log --oneline -1                      # EXPECT ae7db9f (S1) or later
  - RUN: grep -n 'is retired' voice_typing/config.py        # EXPECT :206 — the phrase to reuse
  - RUN: grep -rn "to recover" tests/ voice_typing/ | grep -v '^Binary'   # any exact-string test on the old remedy?
  - RUN: grep -n "wedged" tests/test_voicectl.py | head      # locate the existing wedged test + its fake-socket fixture
  - RUN: sed -n '58,66p;199,216p' tests/test_systemd_unit.py  # learn the install.sh helper's NAME + its read pattern
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_voicectl_session.py tests/test_systemd_unit.py -q --tb=no | tail -1
    EXPECT: all passed (59 + N); RECORD N (test_systemd_unit.py's count) for the after-count.
  - RUN (optional, read-only): timeout 15 .venv/bin/voicectl status > /tmp/s4_status_before.txt 2>&1 || true
    (only if a daemon is up; used for the byte-identical status comparison in L4 — a missing daemon is fine)

Task 1: EDIT voice_typing/ctl.py — help + docstring (text only).
  - 1a. Module docstring, the `status` entry (:22-23): replace the second line
        `             + context-prompt + delivery (mode/state, reason/op when present)`
        with
        `             + context-prompt + output delivery`
  - 1b. Module docstring: insert this block AFTER the `session` entry (:26-29) and BEFORE `Usage:` (:31), verbatim:

        Troubleshooting — the daemon runs as the systemd USER unit that install.sh installs
        (systemd/voice-typing.service); voicectl itself only talks to the control socket:

            exit 2 (daemon not running)       systemctl --user status voice-typing
                                                 journalctl --user -u voice-typing -e
            "daemon wedged: no reply within"  the control socket is nonresponsive — voicectl gives up
                                                 on its own after VOICECTL_TIMEOUT seconds. Stop the unit out
                                                 of band, start it again when you want it back:
                                                   systemctl --user stop voice-typing
                                                   systemctl --user start voice-typing
            startup error naming               output.delivery="bulk-text" is retired: remove the key
            output.delivery                    (default "stream-edit") or set delivery = "stream-edit"
                                                 in $XDG_CONFIG_HOME/voice-typing/config.toml

        Keybinds are user-owned (PRD §4.10): this tool installs no shortcut — bind the commands
        above (for example `voicectl toggle-stream`) in your own compositor config.

  - 1c. `_build_parser` epilog (:355-362): KEEP the existing two blocks; append (as further string
        literals in the same parenthesized concatenation) EXACTLY:

            "\n"
            "if the control socket is nonresponsive ('daemon wedged'):\n"
            "systemctl --user stop voice-typing stops the installed user unit out of band\n"
            "(start it again to resume).\n"
            "config: output.delivery=\"bulk-text\" is retired — remove the key (default \"stream-edit\")\n"
            "or set delivery = \"stream-edit\".\n"
            "keybinds are user-owned: this tool installs no shortcut — bind commands in your\n"
            "own compositor config."

        (Needle 'systemctl --user stop voice-typing' stays on ONE literal — Gotcha #9.)
  - 1d. Wedged raise in `send_command` (:243-247) → keep the prefix, change the remedy:

        except socket.timeout:
            # P1.M1.T1.S4: name the OUT-OF-BAND stop for the unit install.sh installs. The control
            # socket has no server-side deadline, so VOICECTL_TIMEOUT only gets the client back; the
            # dependable way down is systemd's (Restart=on-failure never overrides an explicit stop).
            raise ValueError(
                f"daemon wedged: no reply within {timeout:.0f}s — the control socket is "
                "nonresponsive. Stop the installed user unit out of band with "
                "'systemctl --user stop voice-typing' (or kill the voice-typing-daemon process if "
                "you started it by hand); 'systemctl --user restart voice-typing' brings it back"
            ) from None

  - 1e. Relabel the comment :170-172 (the three lines above the delivery_* reads):

        # Output-delivery status fields. Since the alternate delivery experiment was retired
        # (P1.M1.T1.S1 config rejection; P1.M1.T1.S2 daemon detach) the daemon only ever reports
        # delivery_mode="stream-edit" / delivery_state="inactive" — kept for status-shape
        # compatibility. Missing/empty keys (old daemon) read as 'unknown' like context_prompt;
        # reason/op render ONLY when non-empty.

        Do NOT change the four `response.get(...)` reads or the f-string that renders `delivery:`.
  - 1f. VERIFY: timeout 20 .venv/bin/voicectl --help | grep -c 'systemctl --user stop voice-typing'  → 1
        grep -ci 'bulk' voice_typing/ctl.py → a number EQUAL to grep -c 'output.delivery="bulk-text" is retired' voice_typing/ctl.py
        grep -n 'toggle-lite\|start-lite' voice_typing/ctl.py → ONLY :76 (comment) and :80 (_ALIASES) — never in the docstring/epilog.

Task 2: EDIT install.sh — comments and echo lines ONLY (no behavior change).
  - 2a. Header :21-22 →
        # This script's stdout IS the user-facing install/usage quick-start (Mode A docs). README (synced
        # across the changeset by P1.M2.T4.S1) documents the same CLI entry points.
  - 2b. NOT-active branch (:196-197) → add ONE stderr line after the existing one:
        else
          echo "    voice-typing.service: NOT active — check 'journalctl --user -u voice-typing -e'" >&2
          echo "    (a startup error saying output.delivery=\"bulk-text\" is retired means: remove the key (default \"stream-edit\") or set delivery = \"stream-edit\" in $CFG_DIR/config.toml)" >&2
        fi
  - 2c. Usage block: KEEP :206-209 byte-for-byte. After :209 add:
        echo "          (keybinds are user-owned: this installer sets no shortcut — bind the voicectl commands in your compositor config)"
  - 2d. Wedged line :210 →
        echo "stop a wedged service: systemctl --user stop voice-typing   (out-of-band stop when voicectl reports 'daemon wedged')"
  - 2e. Config line :213 →
        echo "config : $CFG_DIR/config.toml   (output.delivery=\"bulk-text\" is retired: remove the key (default \"stream-edit\") or set delivery = \"stream-edit\")"
  - 2f. VERIFY: bash -n install.sh → clean.
        git diff -U0 install.sh | grep -E '^[+-][^+-]' | grep -vE '^[+-][[:space:]]*(#|echo)'   → EXPECT NO OUTPUT (every changed line is a comment or an echo).

Task 3: EDIT tests/test_voicectl.py — pin the help surface (follow test_help_surfaces_list_all_commands).
  - 3a. ADD after test_cancel_in_commands_docstring_and_epilog (≈:510):

        def test_help_troubleshooting_names_out_of_band_stop_and_migration():
            """P1.M1.T1.S4 (usage baseline): --help and the module docstring must tell a user whose
            control socket is nonresponsive how to stop the installed user unit OUT OF BAND
            (`systemctl --user stop voice-typing` — the supplied unit's dependable remedy; Restart=
            on-failure never overrides an explicit stop), reuse S1's actionable migration wording, and
            state that keybinds are user-owned (PRD §4.10 — nothing is shipped)."""
            help_text = ctl._build_parser().format_help()
            doc = ctl.__doc__ or ""
            for needle in (
                "systemctl --user stop voice-typing",                 # the out-of-band stop
                "journalctl --user -u voice-typing",                  # where the startup error lands
                'output.delivery="bulk-text" is retired',            # S1's wording (config.py:204-207)
                'set delivery = "stream-edit"',                      # …with BOTH actionable verbs
                "user-owned",                                        # no shipped shortcut (PRD §4.10)
            ):
                assert needle in help_text, f"{needle!r} missing from --help:\n{help_text}"
                assert needle in doc, f"{needle!r} missing from the ctl module docstring"
            # The retired delivery state machine is no longer advertised as a live status feature
            assert "mode/state, reason/op" not in doc

        def test_voicectl_source_has_no_bulk_surface_beyond_migration_hint():
            """P1.M1.T1.S4: the only 'bulk' token left in ctl.py is S1's retirement phrase (the
            migration hint users must see). Mirrors S2/S3's no-bulk-surface pins on their modules."""
            import inspect
            src = inspect.getsource(ctl)
            assert src.lower().count("bulk") == src.count('output.delivery="bulk-text" is retired'), (
                "a stale bulk claim crept into ctl.py — only the migration phrase may name it")

  - 3b. WEDGED-HINT assertion: open the existing wedged test found in Task 0 (grep "wedged").
        If it already raises/captures the ValueError, ADD to it:
                assert "systemctl --user stop voice-typing" in str(excinfo.value)   # or the captured message variable
                assert str(excinfo.value).startswith("daemon wedged: no reply within")   # prefix contract (Gotcha #2)
        If no such test exists, ADD one that reuses the file's fake-socket fixture to serve a connection
        that NEVER replies (accept + sleep), monkeypatches the socket timeout to 1 s (VOICECTL_TIMEOUT=1
        via monkeypatch.setenv), calls ctl.main(["status"]), and asserts the two lines above on the
        captured ValueError / stderr. Do NOT contact the real control socket.

  - 3c. If Task 0 found an exact-string assertion on "to recover", update it to the new remedy text.

Task 4: EDIT tests/test_systemd_unit.py — static install.sh pin (follow test_install_sh_offline_grep_and_summary).
  - ADD after test_install_sh_offline_grep_and_summary (:201-215), reusing the file's install.sh path
        helper (the function at ≈:60-64 — use its real name) and its read pattern:

        def test_install_sh_usage_is_generic_and_names_out_of_band_stop():
            """P1.M1.T1.S4: install.sh's printed usage/troubleshooting (its stdout IS the user-facing
            quick-start — header) keeps the WORKING stream/block examples, the generic fragment cancel
            and the explicit session copy; names `systemctl --user stop voice-typing` as the out-of-band
            stop for the unit it installs; reuses S1's migration wording; and makes no shipped-shortcut
            or bulk-delivery claim. STATIC — install.sh is never executed (it restarts the user's service)."""
            text = _install_sh_text()        # <- the file's existing helper / read pattern
            for needle in (
                "toggle|start|stop|status|cancel|session|quit",                 # the generic command set
                "start-block / toggle-block", "start-stream / toggle-stream",   # working examples stay
                "voicectl cancel drops the pending fragment",                   # generic fragment cancel stays
                "voicectl session [--copy]", "copied N chars",                  # explicit session copy stays
                "systemctl --user stop voice-typing",                           # out-of-band stop for the shipped unit
                "journalctl --user -u voice-typing -e",                         # where to look on a failed start
                'output.delivery="bulk-text" is retired', 'set delivery = "stream-edit"',  # S1 wording
                "user-owned",                                                 # no shipped shortcut
            ):
                assert needle in text, f"install.sh is missing {needle!r}"
            assert text.lower().count("bulk") == text.count('output.delivery="bulk-text" is retired'), (
                "install.sh must name bulk only inside the retirement hint")
            # "Do not ship binding changes": the installer must not claim to touch any compositor/shortcut config
            for forbidden in ("hyprland.conf", "sets a shortcut", "installs a shortcut", "binds the key"):
                assert forbidden not in text, f"install.sh makes a shipped-shortcut claim: {forbidden!r}"

Task 5: VALIDATE (gates below). No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S4: align installer and CLI generic usage (ctl.py help, install.sh printouts, static/help pins)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — every help assertion in this item is a two-surface check (argparse epilog AND module docstring),
# exactly like the existing sweep at tests/test_voicectl.py ≈:484-493:
help_text = ctl._build_parser().format_help()
assert needle in help_text and needle in (ctl.__doc__ or "")

# PATTERN — the source-level "no stale bulk" pin (mirrors S2's test_daemon_has_no_bulk_surface / S3's
# recorder_host pin, but ALLOWS the one migration phrase users need):
src.lower().count("bulk") == src.count('output.delivery="bulk-text" is retired')

# PATTERN — "no installer behavior change" as a gate, not a promise: every changed install.sh line is a
# comment or an echo:
#   git diff -U0 install.sh | grep -E '^[+-][^+-]' | grep -vE '^[+-][[:space:]]*(#|echo)'   → empty

# GOTCHA RECAP — the status RENDERING (delivery: stream-edit (inactive)) is intentionally untouched (S2 keeps
# the fields); only the help PROSE that advertised "mode/state, reason/op" is reworded.
```

### Integration Points

```yaml
DOWNSTREAM (consume S4's baseline — NOT S4's edits):
  - P1.M1.T2.S5 (Expose bounded focus-based context starts): any new voicectl command must be published in
    FOUR places — ctl._COMMANDS (:56-68), the module docstring Subcommands block (:13-29), the argparse epilog
    "subcommands:" line (:356), install.sh's "usage  :" line (:206). test_help_surfaces_list_all_commands
    sweeps (1)→(2)+(3); S4's test_install_sh_usage_is_generic_and_names_out_of_band_stop pins (4) as a
    literal that T2.S5 must extend.
  - P1.M2.T4.S1 (Refresh README.md across the changeset): mirrors this wording. README.md still has the
    retired section (:230-262) + "## Dictation commands and optional shortcuts" (:80) + "## Troubleshooting"
    (:436) to reconcile. ctl.py's "see the project README for the full usage table" pointer stays.
PARALLEL (S2/S3 — contracts, disjoint edit sets):
  - S2 owns daemon.py + test_daemon.py/test_session_recovery.py/bulk suites/pyproject.toml; it KEEPS the
    delivery status fields (its Critical #3) and runs tests/test_voicectl.py in its validation — S4's
    additions there must be green and additive only.
  - S3 owns recorder_host.py + test_prompt_engine.py. No overlap.
PRESERVED SURFACES (byte-identical): _COMMANDS, _ALIASES (toggle-lite→toggle), argparse signature (cmd,
  --copy), exit codes (0/1/2/64), format_result output incl. the delivery line and the session branch,
  send_command logic (only the remedy string inside the timeout raise), the client timeout resolver,
  _copy_session_to_clipboard; install.sh steps (1)-(6), the launcher symlink logic, the is-active check.
NOT TOUCHED: systemd/voice-typing.service, README.md, voice_typing/{daemon,recorder_host,config,feedback,
  session_recovery}.py, tests/{test_daemon,test_session_recovery,test_prompt_engine,test_bulk_*}.py, pyproject.toml.
```

## Validation Loop

> AGENTS.md two-timeout rule on EVERY command (inner GNU `timeout`; bash-tool timeout above it). The suites below are CPU-only (no CUDA/model load). NEVER run `install.sh` in full, the daemon, `tests/test_streaming.py`, `test_feed_audio.py`, `test_cuda_check.py`, or the E2E shell scripts.

### Level 1: Syntax & static text (immediate)

```bash
cd /home/dustin/projects/voice-typing
echo "--- install.sh parses; ctl imports ---"
bash -n install.sh && echo "install.sh syntax ok"
timeout 30 .venv/bin/python -c "import voice_typing.ctl as c; assert c._build_parser().format_help(); print('ctl imports + help builds')"
echo "--- the help names the out-of-band stop, the migration fix, and user-owned keybinds ---"
timeout 20 .venv/bin/voicectl --help > /tmp/s4_help.txt 2>&1; cat /tmp/s4_help.txt | tail -8
grep -c 'systemctl --user stop voice-typing' /tmp/s4_help.txt                      # EXPECT 1
grep -c 'output.delivery="bulk-text" is retired' /tmp/s4_help.txt                  # EXPECT 1
grep -c 'set delivery = "stream-edit"' /tmp/s4_help.txt                            # EXPECT 1
grep -c 'user-owned' /tmp/s4_help.txt                                              # EXPECT 1
echo "--- the only 'bulk' in each file is the retirement phrase ---"
test "$(grep -ci 'bulk' voice_typing/ctl.py)" -eq "$(grep -c 'output.delivery="bulk-text" is retired' voice_typing/ctl.py)" && echo "ctl.py: bulk only in migration hint"
test "$(grep -ci 'bulk' install.sh)" -eq "$(grep -c 'output.delivery="bulk-text" is retired' install.sh)" && echo "install.sh: bulk only in migration hint"
echo "--- no lite names leaked into help/docstring; alias still a shim ---"
grep -n 'toggle-lite\|start-lite' voice_typing/ctl.py                              # EXPECT only :76 (comment) + :80 (_ALIASES)
echo "--- wedged remedy: prefix kept, stop named ---"
grep -n 'daemon wedged: no reply within' voice_typing/ctl.py                        # EXPECT the f-string line, unchanged prefix
grep -n "systemctl --user stop voice-typing" voice_typing/ctl.py                    # EXPECT ≥ 2 hits (docstring + raise)
echo "--- install.sh behavior gate: every changed line is a comment or an echo ---"
git diff -U0 install.sh | grep -E '^[+-][^+-]' | grep -vE '^[+-][[:space:]]*(#|echo)' && echo "L1 FAIL: non-comment/echo change" || echo "L1 PASS: installer behavior untouched"
echo "--- unit untouched ---"
git diff --stat -- systemd/voice-typing.service | grep . && echo "L1 FAIL: unit changed" || echo "L1 PASS: unit untouched"
echo "--- scope: S4's four files are in the diff; anything else belongs to S2/S3 (report only) ---"
git diff --name-only -- voice_typing/ctl.py install.sh tests/test_voicectl.py tests/test_systemd_unit.py
rm -f /tmp/s4_help.txt    # scratch teardown (small, bounded; removed on purpose)
```

### Level 2: Unit tests — the pins (CPU-only)

```bash
cd /home/dustin/projects/voice-typing
echo "--- S4's new tests by name ---"
timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_systemd_unit.py -q -v \
  -k "out_of_band_stop or no_bulk_surface or wedged" 2>&1 | grep -E "PASSED|FAILED|ERROR|passed|failed"
# EXPECT: test_help_troubleshooting_names_out_of_band_stop_and_migration PASSED
#        test_voicectl_source_has_no_bulk_surface_beyond_migration_hint PASSED
#        test_install_sh_usage_is_generic_and_names_out_of_band_stop PASSED
#        the wedged test (existing, extended) PASSED
echo "--- the existing two-way help sweep still green (no command lost, no lite leak) ---"
timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py -q -k "help_surfaces or cancel_in_commands" 2>&1 | tail -1
echo "--- full affected suites; compare the count with Task 0's baseline ---"
timeout 300 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_voicectl_session.py tests/test_systemd_unit.py -q 2>&1 | tail -1
# EXPECT: all passed; total == baseline + 3 (or +4 if a new wedged test was added) and ZERO failures
echo "--- sibling suites S2 runs against ctl.py (must stay green) ---"
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_feedback.py -q --tb=short 2>&1 | tail -1
# (read-only check: S2's own gate. If anything here is red for reasons inside daemon.py, report "pending S2" — never edit daemon.py.)
```

### Level 3: Stubbed render of the installer's print tail (never the installer)

```bash
cd /home/dustin/projects/voice-typing
# Executes ONLY step (7) of install.sh (the print block from '# --- (7) print usage' to EOF) with a 2-line
# systemctl stub. No exec in the stub → no PATH recursion; PATH is prepended for this one bash call only;
# mktemp -d is removed by an EXIT trap (AGENTS.md Rule 3). The real service is never contacted.
SHIM="$(mktemp -d)"; trap 'rm -rf "$SHIM"' EXIT
printf '#!/bin/sh\nexit "${SYSTEMCTL_STUB_RC:-0}"\n' > "$SHIM/systemctl"; chmod +x "$SHIM/systemctl"
render() { PATH="$SHIM:$PATH" REPO="$PWD" CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/voice-typing" VERDICT=cuda-ok \
             SYSTEMCTL_STUB_RC="$1" bash <(sed -n '/^# --- (7) print usage/,$p' install.sh) 2>&1; }
echo "--- active branch ---"
render 0 | grep -E 'voice-typing\.service: active|usage  :|start-block / toggle-block|start-stream / toggle-stream|voicectl cancel drops|session \[--copy\]|user-owned|systemctl --user stop voice-typing|config :' 
echo "--- NOT-active branch carries the migration hint (stderr merged) ---"
render 3 | grep -E 'NOT active|output\.delivery="bulk-text" is retired|set delivery = "stream-edit"'
echo "--- bounded scratch: the shim is the only file written; trap removes it on exit ---"
```

### Level 4: Behavioral — wedged hint and unchanged status (fake socket; no real daemon required)

```bash
cd /home/dustin/projects/voice-typing
echo "--- wedged hint: a server that accepts and never replies (in-process, temp socket path) ---"
timeout 60 .venv/bin/python - <<'PY'
import os, socket, tempfile, threading, pathlib
os.environ["VOICECTL_TIMEOUT"] = "1"
from voice_typing import ctl
d = tempfile.mkdtemp(prefix="s4sock-")            # bounded: one socket file, removed below
path = str(pathlib.Path(d) / "control.sock")
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); srv.bind(path); srv.listen(1)
held = []
def hold():
    c, _ = srv.accept(); held.append(c)            # accept, NEVER reply
t = threading.Thread(target=hold, daemon=True); t.start()
# Patch the socket-path resolution the SAME way tests/test_voicectl.py does (see its fake-socket fixture);
# the attribute name is whatever send_command calls at ctl.py:~230 — read it, then patch it here:
ctl._default_control_socket_path = lambda: path    # adjust the name if send_command uses a different symbol
import io, contextlib
err = io.StringIO()
try:
    with contextlib.redirect_stderr(err):
        rc = ctl.main(["status"])
finally:
    srv.close()
    for c in held: c.close()
    os.unlink(path); os.rmdir(d)                   # teardown
out = err.getvalue()
assert "daemon wedged: no reply within" in out, out
assert "systemctl --user stop voice-typing" in out, out
print("L4 PASS: wedged hint names the out-of-band stop; rc =", rc)
PY
echo "--- status rendering unchanged (only if a daemon was up in Task 0; otherwise note 'skipped: daemon down') ---"
if [ -s /tmp/s4_status_before.txt ] && timeout 15 .venv/bin/voicectl status > /tmp/s4_status_after.txt 2>&1; then
  diff <(sed -E 's/[0-9]+(\.[0-9]+)?//g' /tmp/s4_status_before.txt) <(sed -E 's/[0-9]+(\.[0-9]+)?//g' /tmp/s4_status_after.txt) \
    && echo "L4 PASS: status shape identical (numbers masked)"; grep -n '^delivery:' /tmp/s4_status_after.txt
fi
rm -f /tmp/s4_status_before.txt /tmp/s4_status_after.txt
echo "--- S2's daemon half, read-only: the status keys are constants now (report only; never edit daemon.py) ---"
grep -nE '"delivery_mode": snap.get\("delivery_mode", "stream-edit"\)' voice_typing/daemon.py | head -1   # EXPECT :2750-ish
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `bash -n install.sh` clean; `voicectl --help` contains the stop command, the migration phrase, both actionable verbs, `user-owned`; `bulk` appears in ctl.py and install.sh only inside the retirement phrase; the `daemon wedged: no reply within` prefix is intact; every changed install.sh line is a comment or an echo; the unit is untouched.
- [ ] L2: the three new pins + the extended/new wedged test pass; the existing help sweep and cancel pin stay green; `test_voicectl.py + test_voicectl_session.py + test_systemd_unit.py` all passed, count == baseline + S4's additions; `test_control_socket.py`/`test_feedback.py` green (or "pending S2" reported with evidence).
- [ ] L3: the stubbed print tail renders both branches with the required lines; the shim dir is gone afterwards (`ls "$SHIM"` fails after exit).
- [ ] L4: the wedged hint names `systemctl --user stop voice-typing` through the real `main()` path against a never-replying fake socket; `voicectl status` output shape unchanged (or the comparison was explicitly skipped because no daemon was up).

### Feature Validation
- [ ] Working stream/block examples, `voicectl cancel`, and `voicectl session [--copy]` (`copied N chars`, exit 1 without a session) are still documented in BOTH surfaces.
- [ ] `systemctl --user stop voice-typing` is named for a nonresponsive socket in `--help`, the module docstring, the runtime hint, and install.sh.
- [ ] S1's migration wording appears verbatim in `--help`, the docstring, install.sh's NOT-active branch, and its `config :` line.
- [ ] No stale bulk claim: the `status` help no longer advertises "delivery (mode/state, reason/op)"; the only `bulk` token per file is the retirement phrase.
- [ ] No shipped-shortcut claim; `user-owned` stated in all surfaces.

### Code Quality Validation
- [ ] Four-file diff exactly: `voice_typing/ctl.py install.sh tests/test_voicectl.py tests/test_systemd_unit.py`; new tests carry docstrings naming P1.M1.T1.S4; existing test patterns reused (no new fixtures/files).
- [ ] `format_result` output, `_COMMANDS`, `_ALIASES`, argparse signature, exit codes unchanged.
- [ ] Scratch bounded and removed (`/tmp/s4_*`, the `mktemp -d` shim); no file left on `PATH`.

### Scope Boundary Validation
- [ ] No edits to `systemd/voice-typing.service`, README.md, daemon.py, recorder_host.py, config.py, feedback.py, pyproject.toml, or S2/S3-owned tests.
- [ ] `install.sh` never executed end-to-end; the live daemon contacted only via the optional read-only `timeout 15 voicectl status`.
- [ ] S2/S3's in-flight modifications in `git status` are reported, not touched.

### Documentation & Deployment
- [ ] Mode A satisfied: help and installer printouts updated as this work; the README pointer in ctl.py remains for P1.M2.T4.S1, which also reconciles README.md :80, :230-262, :436.
- [ ] The usage-baseline contract (four publish points) is recorded in the research note §4 for P1.M1.T2.S5.

---

## Anti-Patterns to Avoid

- ❌ **Don't run `install.sh`** — not "to check the output", not with `--dry-run` (there is none). Static assertions + the stubbed print tail are the whole validation (Critical #6).
- ❌ Don't remove or reword the `delivery: …` status rendering or the four `delivery_*` reads — S2 keeps them (Critical #3); only the help prose and the comment change.
- ❌ Don't change the `daemon wedged: no reply within` prefix or any exit code (Critical #2).
- ❌ Don't write `toggle-lite`/`start-lite` into the docstring or epilog — the existing sweep forbids it (Critical #1); the alias stays an undocumented shim.
- ❌ Don't paraphrase S1's message — the phrases `output.delivery="bulk-text" is retired` and `set delivery = "stream-edit"` are pinned.
- ❌ Don't introduce the token `bulk` anywhere else (comments included) — the count-equality pin will fail (Critical #4).
- ❌ Don't "helpfully" add a bind example that names a compositor config file, or any phrase like "installs a shortcut" (Critical #5).
- ❌ Don't change installer behavior — no new step, no changed command, no reordering; the diff gate enforces comment/echo-only.
- ❌ Don't edit `systemd/voice-typing.service`, README.md, daemon.py, or S2/S3 files to make a gate pass; report "pending S2/S3" instead.
- ❌ Don't leave the PATH shim or `/tmp/s4_*` files behind; don't `exec` a bare command name in any shim (AGENTS.md Rule 3).
- ❌ Don't skip the two-timeout rule on any command, and don't run the CUDA suites or the daemon.

---

## Confidence Score

**9/10** for one-pass success. Both surfaces are small and fully line-mapped; the exact replacement text, the three new tests, the wedged-hint behavioral check, the comment/echo-only installer gate, and the stubbed print-tail render are copy-ready; the keep-constraints from S2 (delivery rendering) and the reuse-constraint from S1 (migration wording) are quoted with line references; the sibling edit sets are disjoint and the shared-suite interaction (S2 also runs `tests/test_voicectl.py`) is called out. The −1: three names are deliberately left for the implementer's Task 0 precheck rather than guessed — the existing wedged test/fixture in `tests/test_voicectl.py`, the install.sh helper name in `tests/test_systemd_unit.py`, and the socket-path symbol `send_command` calls (the L4 snippet patches `ctl._default_control_socket_path` and says to adjust it) — plus the possibility that an existing test pins the old "(systemctl --user restart voice-typing to recover)" string, which Task 0's `grep -rn "to recover"` surfaces before any edit.

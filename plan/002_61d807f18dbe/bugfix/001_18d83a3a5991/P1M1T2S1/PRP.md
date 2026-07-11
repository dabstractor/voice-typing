# PRP — P1.M1.T2.S1: Add post-restart journal grep + offline summary line to install.sh

## Goal

**Feature Goal**: Close bugfix **Issue 4** (install.sh "does not reflect the no-network requirement") by adding two things to `install.sh`: (a) a **post-restart, warn-level journal grep** that detects if the freshly-restarted daemon made any `HTTP Request: GET https://huggingface.co` network calls (the Issue 1 regression signal), and (b) a **summary line** in the `[7/7]` block confirming the daemon runs fully local. Together they surface a regression at install time and make the documented offline promise (PRD §1, §7.8) visible to the user. This subtask depends on P1.M1.T1.S1 (Complete): `launch_daemon.sh` already exports `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` (lines 71-72), so the grep is expected to be clean — it fires a WARNING only if those exports are later removed.

**Deliverable** (two files edited, no new files):
1. `install.sh` — (i) capture a pre-restart timestamp; (ii) after the restart, wait for the control socket to answer (recorder constructed → any HF call already logged), flush journald, then `if … | grep -q 'HTTP Request: GET https://huggingface.co'` → echo a stderr WARNING (non-fatal); (iii) add an `offline:` line to the `[7/7]` summary.
2. `tests/test_systemd_unit.py` — add a static drift-guard test (mirroring the existing `test_launch_daemon_exports_offline_vars`) asserting install.sh carries the grep + the summary line, so the change is locked in for the fast pytest suite.

**Success Definition**:
- (a) `bash -n install.sh` exits 0; `shellcheck install.sh` (if installed) clean.
- (b) install.sh greps the post-restart journal for `HTTP Request: GET https://huggingface.co` inside an `if`-condition (set-e-safe) and echoes a stderr WARNING on a match.
- (c) The grep **never aborts install.sh** under `set -euo pipefail` — verified hermetically for the no-match case AND the journalctl-fails case.
- (d) install.sh's `[7/7]` summary contains an `offline:` line confirming fully-local operation.
- (e) The new `tests/test_systemd_unit.py` drift-guard passes; the full pytest suite stays green.
- (f) No conflict with the parallel P1.M1.T1.S3 (which edits only `tests/test_idle_and_gpu.sh`) and no change to `launch_daemon.sh` (T1.S1 owns it), `daemon.py`, or config.

## User Persona

**Target User**: The end user running `./install.sh` to set up voice-typing, and the maintainer who re-runs it after a `git pull`.

**Use Case**: User installs/updates; the script restarts the daemon, checks the journal for any huggingface.co network calls, prints either "offline check: no huggingface.co network calls after restart" (stdout, clean) or a WARNING (stderr, regression), and the final summary tells them "offline: daemon runs fully local … — no network at runtime".

**Pain Points Addressed**: Issue 1 shipped invisibly because nothing observed the *production* daemon's network behavior at install time. This gives the user (and the maintainer) an at-install proof point + a documented promise, so a future regression that removes the offline exports is surfaced immediately rather than silently re-violating "100% local" (PRD §1 / §7.8).

## Why

- **Issue 4 (Minor) is the mandate.** The PRD's "Optional" suggested fix is exactly this: *"Optionally add a post-install journal grep in install.sh that asserts no `HTTP Request: GET https://huggingface.co` lines appear after the first restart"* + *"a line in install.sh's summary confirming daemon runs fully offline would close the loop on the documented promise."* This subtask implements both.
- **Defense in depth alongside T1.S1/S2/S3.** T1.S1 put the offline exports in `launch_daemon.sh` (root cause). T1.S2 (Complete) statically drift-guards those exports in pytest (hard config gate). T1.S3 (parallel) makes `test_idle_and_gpu.sh` a non-circular runtime proof. This subtask adds the **install-time runtime surface**: the moment a user/maintainer installs, the journal is checked. Four layers make Issue 1 hard to reintroduce silently.
- **Warn, don't block.** The grep is a WARNING (stderr, non-fatal) — a failed/empty grep must NOT abort `install.sh` (which runs under `set -euo pipefail`). The hard gate is T1.S2's static test; this is the human-visible regression signal. (PRD §5 install steps must remain unobstructed.)
- **Mode A docs.** Per install.sh's own header (L21: *"This script's stdout IS the user-facing install/usage quick-start (Mode A docs)"*), the new `offline:` summary line **is** the doc update — it confirms the offline guarantee to the user at install time. No separate doc file.

## What

Three coordinated edits to `install.sh` + one static test in `tests/test_systemd_unit.py`:

1. **Capture a pre-restart timestamp** (one line, immediately before `systemctl --user restart` at L116) so the journal grep window is this-run-only (no contamination from a prior install's restart within a loose `--since` window).
2. **Post-restart offline grep block** (after the realtimesst.log cleanup, ~after L126, before step `[5/7]` config): poll `voicectl status` until it answers (control socket binds AFTER recorder construction in `main()` → any HF HTTP call is already logged), `sleep 2` for journald flush, then `if journalctl … --since "$RESTART_TS" | grep -q 'HTTP Request: GET https://huggingface.co'; then echo WARNING >&2; else echo "offline check: clean"; fi`.
3. **Summary line** (after the `CUDA :` line at L151): `echo "offline: daemon runs fully local (HF_HUB_OFFLINE=1 via launch_daemon.sh) — no network at runtime"`.
4. **Static drift-guard test** in `tests/test_systemd_unit.py`: assert install.sh contains the grep target string + the offline summary phrase (locks the change into the fast pytest suite).

### Success Criteria

- [ ] `bash -n install.sh` → exit 0; `shellcheck install.sh` (if present) clean.
- [ ] `install.sh` contains exactly one `grep -q 'HTTP Request: GET https://huggingface.co'` inside an `if`-condition (set-e-safe; not a bare grep that could trip errexit).
- [ ] The grep uses `journalctl --user -u voice-typing --since "$RESTART_TS" --no-pager 2>/dev/null`; `RESTART_TS` is captured before the restart.
- [ ] On a match: a WARNING is echoed to **stderr** (not stdout) and contains "huggingface.co" + "offline exports" guidance; install.sh does **not** exit non-zero.
- [ ] The grep is preceded by a readiness wait that polls `voicectl status` (up to ~30s) + a journald flush sleep.
- [ ] The `[7/7]` summary contains an `offline:` line with the "no network at runtime" promise.
- [ ] New `tests/test_systemd_unit.py::test_install_sh_offline_grep_and_summary` passes; `uv run pytest tests/test_systemd_unit.py -v` fully green.
- [ ] Hermetic set-e safety test: under `set -euo pipefail`, the grep block survives both the no-match and journalctl-fails cases without aborting.
- [ ] `git diff --name-only` == `install.sh` + `tests/test_systemd_unit.py` (no touch to `launch_daemon.sh`, `daemon.py`, `tests/test_idle_and_gpu.sh`, config, README).

## All Needed Context

### Context Completeness Check

_Pass._ The exact edit sites (with current line numbers), the set-e-safe bash idiom (verified against install.sh's own `cuda-smoke` `if !` pattern at L86 and `test_idle_and_gpu.sh`'s readiness poll), the daemon's startup ordering (control socket binds after recorder construction → any HF call precedes `voicectl status` answering), the parallel-item boundary (T1.S3 owns `test_idle_and_gpu.sh`), and the existing drift-guard test pattern (`test_launch_daemon_exports_offline_vars`) are all verified below. A developer new to this codebase can apply the patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the mandate (Issue 4 + the Issue 1 regression-guard recommendation)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/prd_snapshot.md
  why: §2.3 Issue 4 prescribes BOTH the summary line ("a line in install.sh's summary confirming
       daemon runs fully offline would close the loop") AND the optional grep ("post-install journal
       grep … asserts no HTTP Request: GET https://huggingface.co lines appear after the first
       restart"). §2.1 Issue 1 gives the verbatim journal line the grep targets.
  critical: "The grep target 'HTTP Request: GET https://huggingface.co' is a LITERAL prefix of the
            verbatim journal lines (TEST_RESULTS.md). Reuse the exact same string T1.S3 uses so the
            two guards match."

# MUST READ — the install.sh structure + exact edit sites
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/scout_launch_status_install.md
  why: §4 maps install.sh: restart at L116, is-active at L142-146, summary at L149+, and says the
       "post-restart journal grep would slot after line 116, before line 142" + summary line "in
       step [7/7] (~line 149)".
  critical: "set -euo pipefail is at L25 — the grep MUST be warn-level + if-condition-wrapped or it
            aborts the whole install on a no-match/journalctl-failure."

# THE EDIT SITE — install.sh (the primary deliverable)
- file: install.sh
  why: 164 lines. L25 `set -euo pipefail`; L86 the set-e-safe `if ! SMOKE="$(...)"` cuda-smoke pattern
        (the idiom to mirror); L116 `systemctl --user restart voice-typing.service`; L118-126 stale
        realtimesst.log cleanup; L128 step [5/7] config; L142-146 is-active check; L149-151 the summary
        (`daemon :` / `CUDA :`); L153 `$REPO/.venv/bin/voicectl` path.
  pattern: "Mirror L86's `if ! cmd; then :; fi` (errexit-exempt condition) for the grep. Mirror
           test_idle_and_gpu.sh's readiness poll (`if voicectl status …; then break; fi`) for the
           pre-grep wait. Summary keys align at column 8: 'daemon '(7)+'/', 'CUDA   '(7)+'/',
           'offline'(7)+'/'."
  gotcha: "The readiness signal is `voicectl status` ANSWERING (control socket up), NOT `systemctl
           is-active` (which is true as soon as the process starts, BEFORE model load). The control
           socket binds AFTER recorder construction in main() — so once voicectl answers, any HF HTTP
           call has already been logged. is-active alone would race the model load."

# THE ROOT-CAUSE FIX THIS DEPENDS ON (Complete) — proves the grep is expected clean
- file: voice_typing/launch_daemon.sh
  why: Lines 71-72 export HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 before `exec "$PY"`. This is
        P1.M1.T1.S1 (Complete). Because the wrapper carries the vars, the restarted daemon loads
        models from cache with ZERO network → the grep is expected to find nothing → it prints the
        clean stdout line. A regression that removes L71-72 makes the grep fire the WARNING.
  critical: "Do NOT edit launch_daemon.sh here (T1.S1 owns it). Do NOT bake the vars into the systemd
            unit's Environment= either — the wrapper is the single source (consistent with LD_LIBRARY_PATH)."

# THE HARD GATE (Complete) + the test pattern to mirror
- file: tests/test_systemd_unit.py
  why: test_launch_daemon_exports_offline_vars (L89) + _launch_daemon_path (L56) are the EXACT
        pattern for the new install.sh drift-guard. That test is the "hard gate" the contract cites
        ("the static test (P1.M1.T1.S2) is the hard gate"); this subtask's install.sh grep is the
        runtime surface, and a parallel static assertion here locks install.sh's text too.
  pattern: "_launch_daemon_path() returns <repo>/voice_typing/launch_daemon.sh; add _install_sh_path()
            returning <repo>/install.sh. The test asserts literal substrings are present in the text."
  critical: "The new test asserts install.sh contains 'HTTP Request: GET https://huggingface.co' (the
            grep target) AND 'no network at runtime' (the summary phrase). Keep it substring-based
            (not line-anchored) so comment changes don't break it."

# THE PARALLEL ITEM (no-conflict boundary)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M1T1S3/PRP.md
  why: P1.M1.T1.S3 (Implementing in parallel) edits ONLY tests/test_idle_and_gpu.sh (removes the
        circular HF_HUB_OFFLINE pre-set, adds a runtime grep over $WORK/daemon.log). It explicitly
        does NOT touch install.sh. Its grep target string is the SAME 'HTTP Request: GET
        https://huggingface.co' — reuse it verbatim so the install-time and test-time guards match.
  critical: "No overlap. T2.S1 = install.sh + test_systemd_unit.py; T1.S3 = test_idle_and_gpu.sh.
            Different files, same grep target. Both can land independently."
```

### Current Codebase tree (relevant slice — T1.S1/S2 Complete; T1.S3 in parallel)

```bash
/home/dustin/projects/voice-typing/
├── install.sh                  # ← EDIT (timestamp + grep block + summary line). 164 lines, set -euo pipefail.
├── voice_typing/
│   └── launch_daemon.sh        # L71-72 export HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 (T1.S1, Complete). UNCHANGED.
└── tests/
    ├── test_systemd_unit.py    # ← EDIT (+_install_sh_path helper + 1 drift-guard test). T1.S2's
    │                           #   test_launch_daemon_exports_offline_vars is the pattern + the hard gate.
    └── test_idle_and_gpu.sh    # T1.S3 (parallel) edits this; T2.S1 does NOT touch it.
```

### Desired Codebase tree with files to be added/changed

```bash
install.sh                     # MODIFY: +RESTART_TS line (pre-L116); +post-restart offline grep block
#                              #         (after realtimesst.log cleanup); +offline summary line (after CUDA).
tests/test_systemd_unit.py     # MODIFY: +_install_sh_path() helper; +test_install_sh_offline_grep_and_summary.
# No new files. No daemon.py / config / launch_daemon.sh / README / systemd unit changes.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — set -euo pipefail WILL ABORT on a bare grep. install.sh L25 sets -euo pipefail. A bare
# `journalctl ... | grep -q '...'` exits 1 when there is NO match (the EXPECTED clean case) -> errexit
# fires -> install.sh aborts at [4/7]. FIX: put the pipeline in an `if` CONDITION: `if PIPELINE; then
# warn; else echo clean; fi`. Errexit does NOT apply to commands tested in an `if` (bash manual, Set
# Builtin). This is the SAME idiom as install.sh L86 (`if ! SMOKE="$(...)"`) and L50-52 (portaudio).

# CRITICAL #2 — pipefail does NOT change #1's safety. `set -o pipefail` makes a pipeline's status the
# rightmost-non-zero, but the pipeline is STILL in the `if` condition (errexit-exempt). journalctl
# failing + grep no-match -> pipeline status non-zero -> `if` false -> clean branch -> no abort. Verified.

# CRITICAL #3 — READINESS = voicectl status ANSWERING, not systemctl is-active. is-active is true the
# instant systemd starts the process (Type=simple), BEFORE the recorder is constructed (model load).
# The HF HTTP calls happen DURING recorder construction (WhisperModel load). So is-active alone would
# let the grep race ahead of the model load (false negative — miss the regression). The control socket
# is bound by main() AFTER VoiceTypingDaemon construction (which builds the recorder), so `voicectl
# status` answering ⟹ recorder constructed ⟹ any HF call already logged. Mirror test_idle_and_gpu.sh's
# `if "$VOICECTL" status …; then ready=1; break; fi` readiness poll.

# CRITICAL #4 — WARN, DO NOT FATAL. The contract is explicit: "Make this a WARNING (not fatal) so a
# failed grep doesn't abort install.sh under set -e — the static test (P1.M1.T1.S2) is the hard gate."
# On a match: echo WARNING to STDERR (not stdout — keep stdout = the Mode A quick-start clean) and
# CONTINUE (no `exit 1`). The install must still complete and reach the summary.

# GOTCHA #5 — capture RESTART_TS BEFORE the restart, not after. `journalctl --since "$RESTART_TS"`
# with a pre-restart timestamp captures ONLY this run's journal lines, avoiding false positives from
# a prior install's restart within a loose `--since '1 min ago'` window. Format `date '+%Y-%m-%d %H:%M:%S'`
# is accepted by journalctl --since.

# GOTCHA #6 — reuse the EXACT grep target T1.S3 uses: 'HTTP Request: GET https://huggingface.co'. It is
# a literal prefix of the verbatim journal lines (httpx logs 'HTTP Request: GET
# https://huggingface.co/api/models/Systran/.../revision/main "HTTP/1.1 200 OK"'). Do NOT shorten to
# just 'huggingface.co' (too broad — could match an unrelated log line) or over-lengthen to include
# the model name (brittle across model swaps). T1.S3 + T1.S2 use the same string — match it.

# GOTCHA #7 — stderr for the WARNING, stdout for the clean note + summary. install.sh's stdout is the
# user-facing Mode A quick-start (L21); a regression WARNING is operator-noise → stderr (journald/
# terminal shows it, but it doesn't pollute the captured quick-start). The clean "offline check: …"
# line and the summary "offline: …" line are user-affirming → stdout.

# GOTCHA #8 — summary key alignment. Existing: 'daemon :' (7 chars + ':' at col 8), 'CUDA   :' (4 +
# 3 spaces = 7, ':' at col 8). 'offline' is 7 chars, so 'offline:' (no space before colon) puts ':' at
# col 8 — ALIGNED. Write `echo "offline: …"` (no space before colon). Visually the colons line up.

# GOTCHA #9 — FULL PATHS. install.sh uses $REPO/.venv/bin/voicectl (L153) and $REPO/.venv/bin/python.
# The readiness poll must use "$REPO/.venv/bin/voicectl" (not bare `voicectl` — zsh aliases shadow it
# interactively, and install.sh is run in bash but the user's PATH may differ). journalctl/systemctl/
# date/seq/sleep are standard and unaliased.

# GOTCHA #10 — DO NOT run a full ./install.sh as the unit gate. It is heavy (uv sync + cuda smoke +
# prefetch + systemd restart; needs GPU + cached models + a login session). The deterministic gates
# are: bash -n + shellcheck + the hermetic grep-logic test + the pytest drift-guard. The full run is
# OPTIONAL manual corroboration (and will print the clean "offline check" line since T1.S1 is in place).

# GOTCHA #11 — DO NOT touch tests/test_idle_and_gpu.sh (T1.S3, in parallel) or launch_daemon.sh (T1.S1).
# This subtask owns install.sh + tests/test_systemd_unit.py ONLY. The grep target string is SHARED
# (intentionally) but the files are distinct.
```

## Implementation Blueprint

### Data models and structure

None. No data models, types, or config schema. The only "structure" is: one bash timestamp variable (`RESTART_TS`), one `if`-guarded grep pipeline, one readiness `for` loop, and one `echo` summary line — plus one Python static test function + one `Path` helper.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY install.sh — capture RESTART_TS before the restart (set-e-safe, precedes the grep window)
  - FIND the restart line (L116):
        systemctl --user restart voice-typing.service
  - EDIT: insert ONE line immediately BEFORE it:
        # timestamp captured BEFORE restart so the offline journal grep below sees only this run
        RESTART_TS="$(date '+%Y-%m-%d %H:%M:%S')"
        systemctl --user restart voice-typing.service
  - WHY: `journalctl --since "$RESTART_TS"` then captures exactly this run's startup, not a prior run's.
  - DO NOT move/rename the restart line; only prepend the timestamp.

Task 2: MODIFY install.sh — add the post-restart offline grep block (the core deliverable)
  - FIND the end of the realtimesst.log cleanup block (~L123-126):
        if [ -f "$REPO/realtimesst.log" ]; then
          rm -f "$REPO/realtimesst.log"
          echo "    removed stale realtimesst.log"
        fi
  - EDIT: insert the following block immediately AFTER that `fi` and BEFORE the step [5/7] config
    comment (`# --- (6) copy config.toml …`):
        # Offline regression guard (bugfix Issue 1 / Issue 4): launch_daemon.sh now exports
        # HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 (P1.M1.T1.S1), so the restarted daemon must load
        # models from cache with ZERO network calls to huggingface.co. Wait for the control socket to
        # answer (it binds AFTER recorder construction in main() -> any HF HTTP call is already logged),
        # flush journald, then grep the post-restart journal and WARN (stderr, NOT fatal) on any match.
        # The hard config gate is tests/test_systemd_unit.py::test_launch_daemon_exports_offline_vars;
        # this is the install-time runtime surface. set-e-safe: the grep pipeline is in an `if`
        # condition (errexit-exempt); a journalctl failure yields no match -> clean branch, no abort
        # (same idiom as the cuda-smoke `if !` at line 86).
        for _ in $(seq 1 60); do                  # up to ~30s for cold CUDA init + 2 model loads
          if "$REPO/.venv/bin/voicectl" status >/dev/null 2>&1; then break; fi
          sleep 0.5
        done
        sleep 2                                   # let journald flush the startup HTTP lines
        if journalctl --user -u voice-typing --since "$RESTART_TS" --no-pager 2>/dev/null \
            | grep -q 'HTTP Request: GET https://huggingface.co'; then
          echo "install.sh: WARNING — daemon made network calls to huggingface.co after restart;" \
               "offline exports (HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE) may be missing from launch_daemon.sh." >&2
        else
          echo "    offline check: no huggingface.co network calls after restart (HF_HUB_OFFLINE=1 active)"
        fi
  - WHY each piece:
      * `voicectl status` readiness poll: the robust "model load done" signal (Gotcha #3); matches
        test_idle_and_gpu.sh's proven pattern; 60×0.5s=30s matches cold-init budget.
      * `sleep 2`: journald flushes async; give it a beat so the grep sees the startup HTTP lines.
      * `if PIPELINE | grep -q …; then … else … fi`: the set-e-safe form (CRITICAL #1/#2).
      * `--since "$RESTART_TS"`: this-run-only window (Gotcha #5).
      * `2>/dev/null` on journalctl: suppress journalctl's own stderr (e.g. no journal) — pipeline
        still completes; grep gets EOF -> no match -> clean branch.
      * WARNING to `>&2` + no `exit`: WARN-level, non-fatal (CRITICAL #4); stdout stays the clean
        Mode A quick-start.
      * the grep target `'HTTP Request: GET https://huggingface.co'`: verbatim match with T1.S3 (Gotcha #6).
  - DO NOT: make it fatal (`exit 1`), drop the `2>/dev/null`, use bare `voicectl`, use `--since '1 min ago'`,
    or shorten/lengthen the grep target.

Task 3: MODIFY install.sh — add the offline summary line to step [7/7]
  - FIND the CUDA summary line (~L151):
        echo "CUDA   : ${VERDICT:-unknown}"
  - EDIT: insert ONE line immediately AFTER it:
        echo "CUDA   : ${VERDICT:-unknown}"
        echo "offline: daemon runs fully local (HF_HUB_OFFLINE=1 via launch_daemon.sh) — no network at runtime"
  - WHY: 'offline'(7 chars) + ':' aligns the colon at column 8 with 'daemon :' and 'CUDA   :' (Gotcha #8).
    This is the Mode A doc update (install.sh stdout IS the quick-start, per L21).
  - DO NOT change the daemon/CUDA/usage/tmux/hypr/logs/config lines.

Task 4: MODIFY tests/test_systemd_unit.py — add the _install_sh_path helper + drift-guard test
  - FIND the existing helper (L56-58):
        def _launch_daemon_path() -> Path:
            # voice_typing/launch_daemon.sh — repo root is the parent of tests/.
            return Path(__file__).resolve().parent.parent / "voice_typing" / "launch_daemon.sh"
  - EDIT: add a sibling helper immediately AFTER it:
        def _install_sh_path() -> Path:
            # install.sh — repo root is the parent of tests/.
            return Path(__file__).resolve().parent.parent / "install.sh"
  - FIND test_launch_daemon_exports_offline_vars (L89) — add the new test alongside it (after it, or
    at the end of the file's drift-guard group). ADD EXACTLY:
        def test_install_sh_offline_grep_and_summary():
            """install.sh must (a) grep the post-restart journal for huggingface.co HTTP calls
            (warn-level runtime regression surface) and (b) print an offline summary line (the Mode A
            user-facing offline promise). bugfix Issue 1 / Issue 4 (P1.M1.T2.S1).

            The hard config gate is test_launch_daemon_exports_offline_vars; this asserts install.sh
            carries the runtime surface + the documented promise, so neither can be silently removed.
            """
            text = _install_sh_path().read_text()
            assert "HTTP Request: GET https://huggingface.co" in text, (
                "install.sh is missing the post-restart journal grep for huggingface.co HTTP calls "
                "(bugfix Issue 1/Issue 4 runtime regression surface)."
            )
            assert "no network at runtime" in text, (
                "install.sh is missing the offline summary line (Mode A user-facing offline promise)."
            )
  - WHY substring-based (not line-anchored regex): tolerant of comment/whitespace changes; the grep
    target + the summary phrase are each distinctive. Mirrors the style of test_launch_daemon_exports_offline_vars.
  - DO NOT over-constrain (e.g. exact full-line regex) — it would break on harmless reformatting.

Task 5: VALIDATE — run the Validation Loop L1–L5 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S1: install.sh post-restart offline journal grep + offline summary line (Issue 4)".
```

### Implementation Patterns & Key Details

```bash
# PATTERN 1 — set-e-safe warn-level grep (the core idiom). The pipeline sits in the `if` CONDITION,
# so errexit never fires on a no-match (grep exits 1) or a journalctl failure. Same shape as install.sh
# L86 (`if ! SMOKE="$(...")`) and L50-52 (portaudio). pipefail is irrelevant inside an if-condition.
if journalctl --user -u voice-typing --since "$RESTART_TS" --no-pager 2>/dev/null \
    | grep -q 'HTTP Request: GET https://huggingface.co'; then
  echo "install.sh: WARNING — … huggingface.co … offline exports may be missing." >&2   # stderr, no exit
else
  echo "    offline check: no huggingface.co network calls after restart (HF_HUB_OFFLINE=1 active)"
fi

# PATTERN 2 — readiness via the control socket (NOT is-active). main() constructs VoiceTypingDaemon
# (builds recorder = loads models = makes any HF call) BEFORE binding ControlServer. So `voicectl
# status` answering ⟹ recorder constructed ⟹ any HF HTTP call already in the journal. This is the
# robust pre-grep wait; it is exactly test_idle_and_gpu.sh's ready-loop idiom.
for _ in $(seq 1 60); do
  if "$REPO/.venv/bin/voicectl" status >/dev/null 2>&1; then break; fi
  sleep 0.5
done

# PATTERN 3 — drift-guard test (pytest, fast). Substring assertions on install.sh's text lock the
# grep target + summary phrase into CI, mirroring test_launch_daemon_exports_offline_vars. Substring
# (not line-regex) tolerates comment edits.
```

### Integration Points

```yaml
PRODUCTION RUNTIME (install.sh → systemctl restart → launch_daemon.sh → daemon):
  - With T1.S1's exports in launch_daemon.sh (L71-72), the restarted daemon loads models from cache
    with ZERO HF network calls → the grep finds nothing → install.sh prints the clean stdout line and
    the WARNING never fires. The offline summary line then reaffirms the promise. Net user-visible
    effect: install output gains one "offline check: clean" line + one "offline: …" summary line.
  - If a future change removes launch_daemon.sh's exports (the Issue 1 regression), the grep fires the
    stderr WARNING at install time — surfacing the regression immediately (alongside T1.S2's static
    gate failing in pytest and T1.S3's runtime gate failing in the heavy test).

DOWNSTREAM — tests/test_systemd_unit.py (the hard gate + this subtask's drift-guard):
  - The new test_install_sh_offline_grep_and_summary joins test_launch_daemon_exports_offline_vars as
    the configuration-layer guards. Together they ensure BOTH the wrapper exports AND the install.sh
    surface stay present. Runs in the fast pytest suite (~seconds).

SIBLING BOUNDARY — P1.M1.T1.S3 (test_idle_and_gpu.sh, in parallel):
  - T1.S3 owns the heavy runtime guard in tests/test_idle_and_gpu.sh (grep over $WORK/daemon.log).
  - T2.S1 owns install.sh + tests/test_systemd_unit.py. NO file overlap. The grep target string is
    intentionally identical ('HTTP Request: GET https://huggingface.co') so the two layers match.

NO INTERFACE / BEHAVIOR CHANGES beyond install.sh's stdout/stderr:
  - launch_daemon.sh, daemon.py, config.toml, the systemd unit, README: UNCHANGED.
  - install.sh remains idempotent and non-fatal on the new check (WARN-level).
  - The new check adds ~30s worst-case (the readiness poll) to install.sh's [4/7] step only when the
    daemon is slow to bind the control socket; typically the socket is up in a few seconds (models are
    warm in page cache from the just-run prefetch/cuda-smoke steps).
```

## Validation Loop

> Full paths where invoked. The deterministic gates (L1–L4) are hermetic — NO full install run, NO GPU,
> NO models, NO systemd restart required. L5 is OPTIONAL manual corroboration (heavy).

### Level 1: Syntax + lint (install.sh is still valid bash)

```bash
cd /home/dustin/projects/voice-typing
bash -n install.sh && echo "L1 PASS: bash -n clean" || echo "L1 FAIL: syntax error"
command -v shellcheck >/dev/null 2>&1 && { shellcheck install.sh && echo "L1 PASS: shellcheck clean" || echo "L1 FAIL: shellcheck findings"; } || echo "L1 (shellcheck not installed — non-blocking)"
# Expected: bash -n exits 0; shellcheck (if present) clean. Any syntax error -> fix before proceeding.
```

### Level 2: Static — both edits are present + correctly shaped

```bash
cd /home/dustin/projects/voice-typing
echo "--- grep target present (exactly the T1.S3 string), inside an if-condition ---"
grep -n "grep -q 'HTTP Request: GET https://huggingface.co'" install.sh
echo "--- RESTART_TS captured before restart + used in --since ---"
grep -n 'RESTART_TS="$(date' install.sh && grep -n -- '--since "$RESTART_TS"' install.sh
echo "--- readiness poll uses voicectl status (NOT is-active) ---"
grep -n 'voicectl" status' install.sh
echo "--- WARNING to stderr, no 'exit 1' near it ---"
grep -n 'huggingface.co after restart' install.sh
echo "--- offline summary line present, colon-aligned ---"
grep -n '^echo "offline:' install.sh
echo "--- no bare (unguarded) journalctl|grep that could trip set -e ---"
awk '/journalctl.*\| *grep/ && !/if / {print "L2 WARN: unguarded pipeline at " NR} END{print "L2 scan done"}' install.sh
# Expected: the grep target line exists; RESTART_TS is set + used; readiness uses voicectl status; the
# WARNING line is present; the summary 'offline:' line exists; no unguarded journalctl|grep pipeline.
```

### Level 3: Hermetic set-e safety — the grep block never aborts (no-match AND journalctl-fails)

```bash
cd /home/dustin/projects/voice-typing
echo "--- simulate the EXACT if-form under set -euo pipefail: CLEAN case (no match) ---"
bash -c '
set -euo pipefail
RESTART_TS="$(date "+%Y-%m-%d %H:%M:%S")"
# stub journalctl to emit a clean line (no HF call):
journalctl() { printf "voice-typing daemon ready\n"; }
if journalctl --user -u voice-typing --since "$RESTART_TS" --no-pager 2>/dev/null \
    | grep -q "HTTP Request: GET https://huggingface.co"; then
  echo "WARN(fire)" >&2
else
  echo "clean(no match)"
fi
echo "survived set -e (clean case)"
'
echo "--- REGRESSION case (match present) -> WARNING fires, still no abort ---"
bash -c '
set -euo pipefail
RESTART_TS="$(date "+%Y-%m-%d %H:%M:%S")"
journalctl() { printf "Jul 11 14:47:37 host python[42]: HTTP Request: GET https://huggingface.co/api/models/Systran/faster-distil-whisper-large-v3/revision/main \"HTTP/1.1 200 OK\"\n"; }
if journalctl --user -u voice-typing --since "$RESTART_TS" --no-pager 2>/dev/null \
    | grep -q "HTTP Request: GET https://huggingface.co"; then
  echo "install.sh: WARNING — huggingface.co call detected" >&2
else
  echo "clean"
fi
echo "survived set -e (regression case)"
'
echo "--- journalctl FAILS (missing/broken) -> no match, no abort ---"
bash -c '
set -euo pipefail
if command -v journalctl >/dev/null 2>&1; then journalctl() { return 1; }; else :; fi
if journalctl --user -u voice-typing --since "2020-01-01 00:00:00" --no-pager 2>/dev/null \
    | grep -q "HTTP Request: GET https://huggingface.co"; then
  echo "WARN(fire)" >&2
else
  echo "clean(journalctl failed gracefully)"
fi
echo "survived set -e (journalctl-fails case)"
'
# Expected: all three print "survived set -e …"; the regression case ALSO prints the WARNING. If any
# aborts under set -e, the if-form is wrong (re-check CRITICAL #1/#2).
```

### Level 4: pytest drift-guard + no regressions

```bash
cd /home/dustin/projects/voice-typing
/home/dustin/.local/bin/uv run pytest tests/test_systemd_unit.py -v
# Expected: ALL PASS, including the new test_install_sh_offline_grep_and_summary AND the existing
# test_launch_daemon_exports_offline_vars (T1.S2's hard gate — must stay green; this subtask doesn't
# touch launch_daemon.sh). Then confirm no broad regression:
/home/dustin/.local/bin/uv run pytest tests/ -q 2>&1 | tail -5
# Expected: full fast suite green (the count was 269 before; stays green — only an ADDITIVE test was added).
```

### Level 5: OPTIONAL manual corroboration (heavy — full install; skip in CI/headless)

```bash
cd /home/dustin/projects/voice-typing
# ONLY if: login session + GPU + cached models + willing to restart the user service. Re-runs the whole
# installer. With T1.S1 in place, the new check prints the CLEAN line; the summary shows the offline line.
systemctl --user stop voice-typing 2>/dev/null || true
./install.sh 2>&1 | tee /tmp/install.out
echo "--- expect a clean offline-check line + the summary offline line: ---"
grep -E 'offline check|offline:' /tmp/install.out
grep -E 'WARNING.*huggingface' /tmp/install.out && echo "REGRESSION (unexpected with T1.S1)" || echo "no WARNING (expected)"
# Expected: "offline check: no huggingface.co network calls after restart …" + "offline: daemon runs
# fully local …" appear; no WARNING. (If a WARNING appears, T1.S1's exports were removed — real regression.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `bash -n install.sh` clean; `shellcheck` (if present) clean.
- [ ] L2: grep target + RESTART_TS + voicectl readiness poll + stderr WARNING + `offline:` summary all present; no unguarded `journalctl|grep`.
- [ ] L3: hermetic set-e safety — clean / regression / journalctl-fails cases all survive without abort; regression case emits the WARNING.
- [ ] L4: `pytest tests/test_systemd_unit.py` green (new drift-guard + existing hard gate); full fast suite green.
- [ ] L5 (optional): full `./install.sh` prints the clean offline-check line + the offline summary line, no WARNING.

### Feature Validation
- [ ] The grep targets the exact `HTTP Request: GET https://huggingface.co` string (matches T1.S3).
- [ ] The grep is WARN-level (stderr, no `exit`) — install.sh always reaches the summary.
- [ ] The readiness wait uses `voicectl status` (control socket), not `systemctl is-active` (races model load).
- [ ] The `[7/7]` summary carries the `offline:` promise line.
- [ ] With T1.S1's exports in place, the grep is clean (no WARNING); removing them would fire it.

### Code Quality Validation
- [ ] New install.sh lines match existing style (the `if !` cuda-smoke idiom; the `for _ in $(seq…)` readiness loop; the `key : value` summary alignment).
- [ ] WARNING → stderr; clean note + summary → stdout (Mode A quick-start stays clean).
- [ ] New test mirrors `test_launch_daemon_exports_offline_vars` (helper + substring assertions).
- [ ] Comment on the grep block cites bugfix Issue 1/Issue 4 + the hard-gate test name.
- [ ] No bare `python`/`pip`/`voicectl` (full paths: `$REPO/.venv/bin/voicectl`).

### Scope Boundary Validation
- [ ] `git diff --name-only` == `install.sh` + `tests/test_systemd_unit.py` ONLY.
- [ ] No touch to `launch_daemon.sh` (T1.S1), `tests/test_idle_and_gpu.sh` (T1.S3), `daemon.py`, `config.toml`, the systemd unit, or README.
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore NOT modified (read-only).
- [ ] No conflict with the parallel T1.S3 (distinct file; same grep target, intentionally).

### Documentation & Deployment
- [ ] install.sh stdout carries the offline summary line (Mode A doc update — install.sh stdout IS the quick-start, per L21).
- [ ] No separate doc file needed (Mode A; the summary line + the grep block's comment are self-documenting).

---

## Anti-Patterns to Avoid

- ❌ Don't use a BARE `journalctl … | grep -q …` (unguarded) — under `set -euo pipefail` a no-match (grep exit 1) aborts install.sh at `[4/7]`. Wrap it in an `if CONDITION; then …; else …; fi` (errexit-exempt) — CRITICAL #1.
- ❌ Don't make the grep FATAL (`exit 1` on match) — the contract mandates WARN-level (the hard gate is T1.S2's static test). A fatal check would block install on a journal quirk.
- ❌ Don't use `systemctl is-active` as the readiness signal — it's true before model load, racing the HF HTTP calls. Use `voicectl status` answering (control socket binds after recorder construction) — CRITICAL #3.
- ❌ Don't use a blind `sleep 5` — cold CUDA init can exceed it; the voicectl-status poll is strictly more robust and mirrors test_idle_and_gpu.sh.
- ❌ Don't shorten the grep target to `huggingface.co` (too broad) or lengthen it to include a model name (brittle). Reuse the exact `HTTP Request: GET https://huggingface.co` (matches T1.S3 + T1.S2) — Gotcha #6.
- ❌ Don't emit the WARNING to stdout — stdout is the Mode A quick-start (L21); operator-noise goes to stderr (Gotcha #7).
- ❌ Don't edit `launch_daemon.sh` (T1.S1 owns it), `tests/test_idle_and_gpu.sh` (T1.S3 owns it), `daemon.py`, config, the systemd unit, or README.
- ❌ Don't bake `HF_HUB_OFFLINE=1` into the systemd unit's `Environment=` — the launch wrapper is the single source (consistent with LD_LIBRARY_PATH; matches T1.S1's design).
- ❌ Don't over-constrain the drift-guard test (exact full-line regex) — substring assertions tolerate comment edits; mirror `test_launch_daemon_exports_offline_vars`.
- ❌ Don't run a full `./install.sh` as the unit gate — it's heavy (uv sync + cuda + prefetch + systemd). The deterministic gates are bash -n + shellcheck + the hermetic set-e test + pytest. The full run is optional corroboration (Gotcha #10).
- ❌ Don't use bare `voicectl` — use `$REPO/.venv/bin/voicectl` (zsh aliases; PATH may differ) — Gotcha #9.

---

## Confidence Score

**9/10** for one-pass implementation success. The change is small and surgical (one timestamp line, one set-e-safe grep block, one summary echo in install.sh; one helper + one substring-assertion test in test_systemd_unit.py), and every load-bearing fact is **verified against the actual repo**: the edit sites + line numbers (install.sh L25/L86/L116/L142/L149), the set-e-safe `if`-condition idiom (mirrors install.sh's own cuda-smoke `if !` at L86 and the portaudio guards), the readiness signal (control socket binds after recorder construction in `main()` — the same assumption test_idle_and_gpu.sh relies on), the launch_daemon.sh exports being in place (T1.S1 Complete, L71-72), the existing drift-guard pattern (`test_launch_daemon_exports_offline_vars`), and the no-conflict boundary with T1.S3 (distinct file, same grep target). The −1 residual risk is environmental: the full `./install.sh` run (L5) depends on the daemon actually binding the control socket promptly, which is true on this machine but is also why L5 is optional and the verdict doesn't depend on it — the deterministic gates (L1–L4) hermetically prove syntax, presence, set-e safety, and CI drift-guard coverage without any GPU/models/systemd.

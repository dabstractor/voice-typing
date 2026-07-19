# PRP — P1.M3.T2.S1: Audit control socket — path, protocol, all 7 commands, error handling (vs PRD §4.2 #3 / §4.8)

## Goal

**Feature Goal**: Produce the authoritative **control-socket protocol audit** for
`voice_typing/daemon.py` (`ControlServer` + `_dispatch` + `status_snapshot` + `_arm_response`) against
PRD §4.2 #3 / §4.8 — verifying the 7 item checks (a)-(g): (a) socket path resolves to
`$XDG_RUNTIME_DIR/voice-typing/control.sock`; (b) parent dir mkdir 0700; (c) stale socket unlinked
before bind; (d) all 7 commands (`toggle`/`start`/`stop`/`status`/`toggle-lite`/`start-lite`/`quit`)
produce correct JSON responses; (e) status includes `phase`/`models_loaded`/`mode`/`partial`/`uptime_s`;
(f) unknown cmd → `{ok:false,error}`; (g) start/toggle block during load (single-flight) + the response
includes `listening` after arm. This is a **READ-ONLY AUDIT**: the deliverable is a report file; NO
source code is modified (the code is compliant — this PRP's research verified it; the audit re-confirms
live). Satisfies **Acceptance #6** ("`voicectl toggle/start/stop/status/quit` all work").

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_socket.md` — a NEW self-contained `# Gap Report —
  P1.M3.T2.S1: …` file (there is NO existing `gap_socket.md`; this subtask creates it — unlike the
  feedback audits which split S1/S2 into one file). Format mirrors `gap_feedback.md`. Verbatim content
  in Implementation Blueprint → Task 3.

**Success Definition**:
- (a) The report verifies all 7 checks against the LIVE `voice_typing/daemon.py` (re-grep + re-read —
  not trusting this PRP's verdict blindly) and records a ✅ verdict + file:line evidence + a pinning
  test for each.
- (b) The contract's mandated run command — `.venv/bin/python -m pytest tests/test_control_socket.py
  tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'` — is re-run live and the
  pass count (35) is recorded in the report's §3.
- (c) The 2 non-defect test-coverage nuances (the socket test's reduced `_StubDaemon` key set; the
  single-flight/load-failure coverage living in test_daemon.py) are recorded in a §4 so they are not
  mistaken for code gaps.
- (d) **No source files are modified** — `daemon.py`/`test_control_socket.py`/`test_daemon.py` are
  compliant + read-only; the only artifact change is creating `gap_socket.md`. `git status --short`
  shows ONLY `plan/006_862ee9d6ef41/architecture/gap_socket.md`.
- (e) The report's scope is the DAEMON-side control socket only — NOT the `ctl.py` client (P1.M3.T2.S2),
  NOT `status.sh` (P1.M3.T2.S3), NOT the recorder-host subprocess lifecycle (P1.M2.*, Complete).

> **VERIFIED VERDICT (this PRP's research): the control socket is COMPLIANT on all 7 checks — no code
> fix needed.** The audit's job is to re-confirm this live and document it with evidence + the 2
> non-defect nuances. If a check surprisingly fails on re-read, document it as a real gap for a
> SEPARATE remediation task (this audit does not fix code).

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance cross-check)
who needs an authoritative, file:line-evidenced record that the daemon's control socket matches PRD
§4.2 #3 / §4.8 — so `voicectl` (and any other JSON-line client) can reliably arm/disarm/query/quit the
daemon over `$XDG_RUNTIME_DIR/voice-typing/control.sock`.

**Use Case**: A reviewer asks "do all 7 commands produce the right JSON, does status carry the
lifecycle fields, and does an unknown command error cleanly?" The report answers yes/no per check with
the exact source lines + the pinning test.

**Pain Points Addressed**: Without this audit, a regression (a missing `toggle-lite` branch; a status
payload that drops `phase`/`mode` so voicectl can't show the lifecycle; a stale socket that wedges
boot; an unknown command that crashes the worker thread instead of returning `{ok:false}`) would be
invisible until a user sees a wrong status / a boot hang / a crashed daemon. The audit pins the
protocol to PRD §4.2 #3 with evidence.

## Why

- **PRD §4.2 #3 is the daemon's entire external control surface.** Every user action flows through
  this socket (`voicectl` → JSON line → `_dispatch` → daemon method → JSON response). Acceptance #6
  ("all commands work") is satisfied by THIS audit. A protocol drift would break every command.
- **Closes the control-plane audit area (P1.M3.T2, S1).** Every other audit area in round 006 produced
  a `gap_*.md`; the control socket is this round's S1. (S2 = voicectl CLI; S3 = status.sh — separate.)
- **Read-only + parallel-safe.** The audit reads `daemon.py` + the two test files and CREATES
  `gap_socket.md`. The parallel P1.M3.T1.S2 (feedback) touches `gap_feedback.md` — a DIFFERENT file;
  no conflict. No source edits → no conflict with any in-flight implementation task.
- **The research already did the work.** This PRP's research note pre-maps every check to its
  file:line + verdict + pinning test, so the implementing agent re-verifies + writes the report in one
  pass (the value of a PRP: curated context, not open-ended exploration).

## What

A read-only verification of `voice_typing/daemon.py`'s control socket — `_default_control_socket_path`
(path), `ControlServer.start`/`stop`/`_handle` (lifecycle + mkdir 0700 + stale-unlink + accept loop),
`_dispatch` (the 7 commands + unknown/malformed/non-dict errors), `status_snapshot` (the status
payload), and `_arm_response` (single-flight-aware post-arm response) — re-confirmed live, then
documented as a new `gap_socket.md` (mirroring `gap_feedback.md`'s format). The 7 checks (a)-(g) + the
live test run + the 2 non-defect nuances.

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_socket.md` exists, titled `# Gap Report — P1.M3.T2.S1: Control socket protocol vs PRD §4.2(3) / §4.8`.
- [ ] The report records a ✅ verdict + `daemon.py` file:line + a pinning test (test_control_socket.py or test_daemon.py) for each of the 7 checks (a)-(g).
- [ ] `.venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'` is re-run live; its pass count (35) is recorded.
- [ ] The 2 non-defect nuances (the socket `_StubDaemon` reduced key set; single-flight/load-failure coverage in test_daemon.py) are documented in §4.
- [ ] The report's scope is the daemon-side socket only — not `ctl.py` (S2), not `status.sh` (S3), not the recorder-host lifecycle (P1.M2.*).
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_socket.md` — NO source files modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task
nature (read-only audit → new report file), the `gap_feedback.md` FORMAT template, the verified verdict
(compliant) + the file:line evidence + the pinning test for all 7 checks, the 2 non-defect nuances, the
exact test command + its live count (35), and the scope boundaries are all pinned. The audit
re-verifies live (re-grep + re-read + re-run) rather than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + file:line evidence + the 2 nuances + scope boundaries
- docfile: plan/006_862ee9d6ef41/P1M3T2S1/research/control_socket_audit.md
  why: "§1 THE VERIFIED VERDICT: a 7-row table mapping each check (a-g) to its daemon.py file:line +
        ✅ COMPLIANT. §2 the test-coverage map (each check -> its pinning test in test_control_socket.py
        OR test_daemon.py). §3 the contract's -k run command + its LIVE count (35 passed). §4 the 2
        NON-DEFECT nuances (socket _StubDaemon reduced key set; single-flight/load-failure coverage in
        test_daemon.py). §5 scope boundaries. §6 tooling."
  section: "ALL load-bearing. §1 (verdict table), §2 (test map), §4 (nuances), §5 (scope)."

# MUST READ — the file being audited (path / ControlServer.start / _dispatch / status_snapshot / _arm_response)
- file: voice_typing/daemon.py
  why: "AUDIT TARGET (read-only). _CONTROL_SOCKET_SUBPATH :352 + _default_control_socket_path() :355
        (path + RuntimeError). ControlServer.start() :1762 (mkdir 0o700 :1773, stale-unlink :1774-1776,
        bind :1779, chmod 0o600 :1787, listen(8) :1788). _dispatch(line) :1892 (toggle :1898 /
        start :1908 / start-lite :1911 / toggle-lite :1915 / stop :1922 / status :1924 / quit :1926 /
        unknown :1965 / malformed :1896 / non-dict :1899). status_snapshot() :1548 (keys incl mode :1564,
        phase :1565, models_loaded :1566, partial :1569, uptime_s :1571). _arm_response() :1875
        (ok:false on load_failure+not_listening :1889; else {ok:true,**status})."
  critical: "RE-VERIFY by grep + read — do NOT trust the line numbers blindly (re-locate them live).
             The audit READS this file; it does NOT edit it (compliant code = no modification)."

# MUST READ — the socket test file (coverage to cite per check)
- file: tests/test_control_socket.py
  why: "274-line suite (3 layers: dispatch logic / real-socket round-trip / lifecycle-hardening). _StubDaemon
        :27 (duck-type daemon — REDUCED 9-key status_snapshot :45, NO phase/models_loaded/mode — nuance §4.1).
        Per-check tests: (a) :266/:271; (b) :224; (c) :235; (d) :115/:120/:126/:131/:143/:161 + round-trips
        :189-219; (f) :169/:173 + malformed :177 + non-dict :182. Run it via the -k filter + record the count."
  critical: "Characterize coverage accurately. The socket _StubDaemon's status_snapshot is a REDUCED key
             set (9 keys) — the REAL 14-key set is pinned in test_daemon.py:1595 (nuance §4.1). Do NOT
             claim test_dispatch_status_has_all_keys (:120) pins the real key set; it pins the stub's."

# MUST READ — the daemon test file (where the REAL status key set + single-flight coverage live)
- file: tests/test_daemon.py
  why: "REAL status key set: test_status_snapshot_keys_and_cuda_values :1595 (asserts the exact 14 keys
        incl phase/models_loaded/mode/load_error/mic_ok/mic_error @1610-1612). Single-flight:
        test_load_recorder_single_flight_one_build_under_concurrency :3010 +
        test_load_and_unload_serialize_on_the_same_single_flight_lock :3198. Load-failure arm suppression:
        test_start_suppressed_when_load_fails :2994. These cover checks (e) + (g) where the socket
        tests' _StubDaemon can't (it has no recorder/_load_error)."
  critical: "The -k 'status' filter picks up these test_daemon.py tests too — that is why the contract's
             run command spans BOTH files (35 passed). Cite them for checks (e)+(g)."

# MUST READ — the gap-report FORMAT template (mirror its structure for the new file)
- file: plan/006_862ee9d6ef41/architecture/gap_feedback.md
  why: "The format template. Structure: title (`# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X`) + Date +
        Scope + Audited artifacts (read-only) + Bottom line (✅) + §1 Method (w/ commands run) + §2 per-
        check compliance TABLE (PRD req | actual | file:line | pinning test | ✅) + §3 Test results
        (the live count) + §4 non-defect nuances + §5 Conclusion (PASS; no fix). Mirror it EXACTLY."
  critical: "Mirror the structure. gap_socket.md is a NEW file (CREATE, not append) — it does NOT share
             a file with any sibling the way the feedback S1/S2 audits share gap_feedback.md. Cite
             daemon.py file:line + a test_control_socket.py OR test_daemon.py test per check."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.2(3) Control socket: SOCK_STREAM at $XDG_RUNTIME_DIR/voice-typing/control.sock (mkdir 0700);
        the 7 commands' JSON responses (toggle→{ok:true,listening:true}; start/stop/status→{ok:true,
        listening,partial,uptime_s,mode}; toggle-lite/start-lite→lite mode; quit→clean shutdown); unknown
        →{ok:false,error}; 'Remove stale socket file on startup'. §4.8 voicectl: status pretty-prints
        partial/phase/models_loaded/mode. This is the authoritative spec each check is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.2(3)/§4.8 as the contract."

# CONTEXT — the parallel task contract (P1.M3.T1.S2 = feedback; DIFFERENT file; no conflict)
- file: plan/006_862ee9d6ef41/P1M3T1S2/PRP.md
  why: "The parallel item (feedback atomic/throttle/notify audit) APPENDS to gap_feedback.md — a
        DIFFERENT file from gap_socket.md (which this task CREATEs). Confirms the two audits are
        disjoint (socket vs feedback) and neither touches the other's report."
  critical: "gap_socket.md is INDEPENDENT of gap_feedback.md. No append coordination needed (unlike the
             feedback S1/S2 split). CREATE the file fresh."
```

### Current Codebase tree (state at P1.M3.T2.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/daemon.py              # AUDIT TARGET (read-only — ControlServer/_dispatch/status_snapshot/_arm_response)
├── tests/
│   ├── test_control_socket.py          # AUDIT (cite the pinning test per check; read-only) — 274 lines
│   └── test_daemon.py                  # AUDIT (real status key set :1595 + single-flight :3010/:3198; read-only)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_feedback.md                 # FORMAT TEMPLATE (mirror its structure) — being appended-to by P1.M3.T1.S2 (DIFFERENT area)
    ├── gap_typing.md                   # FORMAT REFERENCE (same structure)
    └── gap_socket.md                   # <-- CREATE (NEW file; no prior socket gap report exists)
# NO source files modified. The only artifact change is creating gap_socket.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_socket.md   # CREATE (NEW): the P1.M3.T2.S1 control-socket protocol audit
                                                   #   (7-check compliance table + live -k count + 2 nuances + conclusion).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT. The code is COMPLIANT (research §1). Do NOT modify daemon.py
#   or any source file. The ONLY artifact change is CREATING gap_socket.md. If a check fails on re-read,
#   DOCUMENT it as a gap for a separate remediation task — do not fix it here.

# CRITICAL #2 — RE-VERIFY LIVE; DON'T TRUST THE LINE NUMBERS BLINDLY. The research pre-maps each check
#   to daemon.py file:line, but the audit must re-grep + re-read the live tree (mirrors gap_feedback.md
#   "audit re-verified against the live tree"). Line numbers drift; the verdict must reflect the CURRENT
#   file. Re-run: grep -nE '_default_control_socket_path|def start|def _dispatch|def status_snapshot|
#   def _arm_response|os\.makedirs.*0o700|os\.unlink|unknown command' voice_typing/daemon.py

# CRITICAL #3 — gap_socket.md is a NEW FILE (CREATE), NOT an APPEND. There is no prior gap_socket.md.
#   (This differs from the feedback audits where S1 creates + S2 appends to ONE gap_feedback.md.) Do NOT
#   look for a sibling to append to; do NOT touch gap_feedback.md (the parallel P1.M3.T1.S2 owns it).
#   (Research §0, §5.)

# CRITICAL #4 — THE SOCKET _StubDaemon USES A REDUCED KEY SET — that is a NON-DEFECT, NOT A GAP. The
#   test_control_socket.py _StubDaemon.status_snapshot (:45) returns 9 keys (no phase/models_loaded/mode).
#   So test_dispatch_status_has_all_keys (:120) pins the STUB's 9-key set, NOT the real daemon's 14 keys.
#   The REAL key set is pinned by test_daemon.py:1595 (asserts the exact 14 keys). Record this in §4.1
#   as a NON-DEFECT — do NOT flag it as a gap and do NOT "fix" the stub. (Research §4 nuance 1.)

# CRITICAL #5 — THE SINGLE-FLIGHT + LOAD-FAILURE COVERAGE LIVES IN test_daemon.py, NOT test_control_socket.py
#   — that is a NON-DEFECT. The socket tests use _StubDaemon (no _load_host/_load_error) — they prove
#   DISPATCH WIRING + post-arm listening, NOT the single-flight or the _arm_response ok:false path. The
#   single-flight (test_daemon.py:3010/:3198) + load-failure suppression (:2994) are daemon concerns.
#   Record in §4.2 as a NON-DEFECT. (Research §4 nuance 2.)

# CRITICAL #6 — CHECK (g) "block during load" IS THE DAEMON'S _load_host/_load_recorder SINGLE-FLIGHT,
#   NOT a socket-layer property. start() -> daemon.start() -> _load_host (single-flight under _lock) ->
#   _arm -> _arm_response. The socket worker thread BLOCKS in daemon.start() for the duration of the load
#   (that IS the "block during load" — a concurrent voicectl status on ANOTHER connection stays responsive
#   because status takes no lock). Cite test_daemon.py:3010 (single-flight) for the mechanism + the
#   _dispatch:1908 wiring for the entry point. (Research §1 check (g).)

# CRITICAL #7 — STATUS PAYLOAD IS UNIFORM: every successful cmd returns {ok:true, **status_snapshot()}
#   (or _arm_response which is the same on success). toggle/start/start-lite/toggle-lite return
#   _arm_response() when arming (else {ok:true,**status}); stop/status return {ok:true,**status}; quit
#   returns {ok:true,shutting_down:true}. Do NOT claim different shapes per command — they share the
#   status_snapshot spread. (daemon.py _dispatch :1898-1963.)

# GOTCHA #8 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare python/pytest).
#   mypy NOT installed — do NOT run it. ruff optional (not a gate). The -k suite is GPU-free
#   (_StubDaemon + monkeypatched cuda_check) — ~3s.

# GOTCHA #9 — SCOPE = DAEMON-SIDE SOCKET ONLY. NOT ctl.py (the client — P1.M3.T2.S2), NOT status.sh
#   (P1.M3.T2.S3), NOT the recorder-host lifecycle (P1.M2.* Complete). The socket just dispatches;
#   whether ctl.py RENDERS the response correctly is S2's audit. (Research §5.)

# GOTCHA #10 — THE -k FILTER SPANS BOTH TEST FILES BY DESIGN. The contract's run command is
#   `pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch
#   or status'` — the 'status' keyword picks up test_daemon.py's status_snapshot tests (the REAL key-set
#   coverage for check (e)), and 'dispatch'/'cmd' pick up the socket tests. That is why it is 35 passed,
#   not just test_control_socket.py's count. Cite the FULL command + 35 verbatim. (Research §3.)
```

## Implementation Blueprint

### Data models and structure

Not applicable — no code, no data models. The "data" is the audit's findings table (7 checks → verdict +
file:line + pinning test), recorded as a new `gap_socket.md`.

### Audit Tasks (ordered — verify → run → write)

```yaml
Task 1: RE-VERIFY the 7 checks against the LIVE daemon.py (read-only; re-grep + re-read)
  - RUN (from /home/dustin/projects/voice-typing):
      grep -nE '_CONTROL_SOCKET_SUBPATH|def _default_control_socket_path' voice_typing/daemon.py
      grep -nE 'def start\(self\)|os\.makedirs\(directory.*0o700|os\.unlink\(self\._socket_path\)|sock\.bind|os\.chmod\(self\._socket_path' voice_typing/daemon.py
      grep -nE 'def _dispatch|def status_snapshot|def _arm_response|unknown command|malformed JSON|request must be a JSON object' voice_typing/daemon.py
      grep -nE '"cmd" == "(toggle|start|start-lite|toggle-lite|stop|status|quit)"' voice_typing/daemon.py
  - For each check (a)-(g), confirm the verdict + capture the CURRENT file:line (re-locate; Critical #2).
    Expected findings (research §1): all 7 ✅ COMPLIANT.
  - DO NOT edit daemon.py. This is read-only.

Task 2: RUN the contract's test command (re-run live; record the pass count)
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'
  - EXPECTED: 35 passed (GPU-free). Record the count + time in the report's §3. Cite the pinning test
    per check (research §2 map; note the test_daemon.py cross-refs for (e)+(g)).

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_socket.md
  - FILE: plan/006_862ee9d6ef41/architecture/gap_socket.md (NEW file — use the `write` tool).
  - CONTENT: the verbatim block in "Task 3 SOURCE" below (mirror gap_feedback.md's structure — Critical #3).
  - ACCURACY: cite the LIVE file:line (from Task 1) + the LIVE pytest count (from Task 2). Replace the
    <today> placeholder with the real date. Re-verify the test line numbers (Critical #2).
  - DO NOT: modify daemon.py/tests/PRD.md/any source; append to or touch gap_feedback.md (parallel S2
    owns it); audit ctl.py (S2) or status.sh (S3) or the recorder-host lifecycle (P1.M2.*); flag the
    _StubDaemon-reduced-key-set / single-flight-in-test_daemon.py nuances as gaps.

Task 4: VALIDATE (no further file change — see Validation Loop)
  - gap_socket.md exists w/ the title + the 7-check table + the live -k count + the 2 nuances.
  - git status --short shows ONLY gap_socket.md (no source modified). No git commit unless directed.
```

#### Task 3 SOURCE — write verbatim to `gap_socket.md` (NEW file)

> Replace `<today>` with the audit date and confirm every file:line against the LIVE tree (Task 1) +
> the LIVE pytest count (Task 2). This is a NEW file (CREATE, not append).

```markdown
# Gap Report — P1.M3.T2.S1: Control socket protocol vs PRD §4.2(3) / §4.8

**Date:** <today> (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/daemon.py`'s **control socket** — the `voicectl`↔daemon AF_UNIX
`SOCK_STREAM` wire surface (PRD §4.2(3), §4.8) — on the **7 item checks (a)-(g)**: (a) socket path
resolves to `$XDG_RUNTIME_DIR/voice-typing/control.sock`; (b) parent dir `mkdir 0700`; (c) stale
socket unlinked before bind; (d) all 7 commands (`toggle`/`start`/`stop`/`status`/`toggle-lite`/
`start-lite`/`quit`) produce correct JSON responses; (e) status includes `phase`/`models_loaded`/
`mode`/`partial`/`uptime_s`; (f) unknown cmd → `{ok:false,error}`; (g) start/toggle block during load
(single-flight) + the response includes `listening` after arm. The audited code regions are:
`_default_control_socket_path` (path), `ControlServer.start` (mkdir 0700 + stale-unlink + bind +
chmod 0600 + listen), `ControlServer._dispatch` (the 7 commands + unknown/malformed/non-dict errors),
`VoiceTypingDaemon.status_snapshot` (the status payload), and `ControlServer._arm_response`
(single-flight-aware post-arm response). Subtask **P1.M3.T2.S1** of verification round `006_862ee9d6ef41`.

**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `_CONTROL_SOCKET_SUBPATH = ("voice-typing","control.sock")` (:352) +
  `_default_control_socket_path()` (:355 → `os.path.join(xdg,*subpath)` :370; raises RuntimeError if
  XDG unset :361); `ControlServer.start()` (:1762 → `os.makedirs(directory, exist_ok=True, mode=0o700)`
  :1773; stale-unlink `try: os.unlink(self._socket_path) except FileNotFoundError: pass` :1774-1776
  BEFORE `sock.bind()` :1779; `os.chmod(self._socket_path, 0o600)` :1787; `sock.listen(8)` :1788);
  `ControlServer._dispatch(line)` (:1892 → toggle :1898 / start :1908 / start-lite :1911 / toggle-lite
  :1915 / stop :1922 / status :1924 / quit :1926→`{"ok":true,"shutting_down":true}`; unknown :1965;
  malformed JSON :1896; non-dict :1899); `status_snapshot()` (:1548 → keys incl `mode` :1564, `phase`
  :1565, `models_loaded` :1566, `partial` :1569, `uptime_s` :1571); `_arm_response()` (:1875 →
  `{"ok":False,"error":f"model load failed: {load_error}"}` on load_failure+not_listening :1889;
  else `{"ok":True,**status_snapshot()}`).
- `tests/test_control_socket.py` + `tests/test_daemon.py` — the contract's run targets (the `-k` filter;
  re-ran live). Coverage characterized in §2 + §4.

**Bottom line:** ✅ `daemon.py`'s control socket is **COMPLIANT** with PRD §4.2(3)/§4.8 on all 7 checks
— each mapped to a `daemon.py` file:line + a pinning test (in `test_control_socket.py` OR
`test_daemon.py`), and the contract's `-k` suite is **35 passed** (GPU-free). **No source files were
modified.** Two non-blocking test-coverage observations (the socket `_StubDaemon`'s reduced key set; the
single-flight/load-failure coverage living in `test_daemon.py`) are recorded in §4 so they are not
mistaken for defects.

---

## 1. Method

Each of the 7 checks was mapped 1:1 to its `voice_typing/daemon.py` implementation by `grep -n` (the
file:line evidence), the 7 command branches were read in `_dispatch` (:1892-1965), the status payload
was read in `status_snapshot` (:1548-1574), the `_arm_response` load-failure path was read (:1875-1891),
and the contract's `-k` suite (`tests/test_control_socket.py tests/test_daemon.py -k 'socket or control
or cmd or dispatch or status'`) was **re-run live** to record the actual pass count. Nothing was assumed
from the PRP's embedded numbers — every figure + line below was re-verified this round (pure stdlib:
`json`/`os`/`select`/`socket`/`threading`; no GPU/recorder required).

### Commands run (re-verification)

```bash
# (a) path; (b) mkdir 0700 + chmod 0600; (c) stale-unlink-before-bind
grep -nE '_CONTROL_SOCKET_SUBPATH|def _default_control_socket_path' voice_typing/daemon.py
grep -nE 'os\.makedirs\(directory.*0o700|os\.unlink\(self\._socket_path\)|sock\.bind|os\.chmod\(self\._socket_path' voice_typing/daemon.py
# (d) the 7 command branches + (f) unknown/malformed/non-dict errors
grep -nE 'cmd == "(toggle|start|start-lite|toggle-lite|stop|status|quit)"|unknown command|malformed JSON|request must be a JSON object' voice_typing/daemon.py
# (e) the status payload keys + (g) the _arm_response load-failure path
grep -nE 'def status_snapshot|"mode"|"phase"|"models_loaded"|"partial"|"uptime_s"|def _arm_response|model load failed' voice_typing/daemon.py
# the contract's run command, LIVE
timeout 120 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'
```

## 2. Per-check compliance table (PRD §4.2(3)/§4.8 vs `daemon.py`)

| # | PRD requirement | `daemon.py` actual | file:line | Pinning test | Verdict |
|---|---|---|---|---|---|
| **(a)** | socket at `$XDG_RUNTIME_DIR/voice-typing/control.sock` | `_default_control_socket_path()` joins `XDG_RUNTIME_DIR` + `("voice-typing","control.sock")`; raises `RuntimeError` if XDG unset (no safe default — fail clearly) | `_CONTROL_SOCKET_SUBPATH` `:352`; `_default_control_socket_path` `:355`; join `:370`; RuntimeError `:361` | `test_default_socket_path_honors_xdg` `:266`; `test_default_socket_path_raises_when_xdg_unset` `:271` (test_control_socket.py) | ✅ |
| **(b)** | parent dir `mkdir 0700` | `ControlServer.start()` does `os.makedirs(directory, exist_ok=True, mode=0o700)` then, after bind, `os.chmod(self._socket_path, 0o600)` (belt-and-suspenders owner-only on the 0700 dir) | `start` `:1762`; `makedirs 0o700` `:1773`; `chmod 0o600` `:1787` | `test_start_creates_dir_0700_and_socket_0600` `:224` (asserts dir `0o700` + socket `0o600`) | ✅ |
| **(c)** | stale socket removed before bind | `start()` `try: os.unlink(self._socket_path) except FileNotFoundError: pass` BEFORE `sock.bind()` (SO_REUSEADDR is meaningless for AF_UNIX path sockets) | unlink `:1774-1776`; bind `:1779` | `test_start_recovers_stale_socket_file` `:235` (pre-creates a stale file → start recovers) | ✅ |
| **(d)** | all 7 commands → correct JSON | `_dispatch` branches: `toggle`→arm_response-or-status; `start`→`_arm_response()`; `start-lite`→`_arm_response()`; `toggle-lite`→arm-or-status; `stop`→`{ok:true,**status}`; `status`→`{ok:true,**status}`; `quit`→`{ok:true,"shutting_down":true}` (+request_shutdown). Successful cmds share the uniform `{ok:true,**status_snapshot()}` spread | `_dispatch` `:1892`; toggle `:1898`; start `:1908`; start-lite `:1911`; toggle-lite `:1915`; stop `:1922`; status `:1924`; quit `:1926` | `test_dispatch_toggle` `:115`; `test_dispatch_status_has_all_keys` `:120`; `test_dispatch_start_stop_set_listening` `:126`; `test_dispatch_lite_commands_call_daemon` `:131`; `test_dispatch_status_response_carries_mode` `:143`; `test_dispatch_quit_calls_request_shutdown` `:161`; round-trips `:189-219` | ✅ |
| **(e)** | status has `phase`/`models_loaded`/`mode`/`partial`/`uptime_s` | `status_snapshot()` returns a 14-key dict incl `mode` (`self._mode`), `phase` (from `feedback.snapshot()`), `models_loaded`, `partial`, `last_final`, `uptime_s` (round(uptime_s,3)), + `load_error`/`device`/`compute_type`/`final_model`/`realtime_model`/`mic_ok`/`mic_error`. ALL 5 required fields present | `status_snapshot` `:1548`; `mode` `:1564`; `phase` `:1565`; `models_loaded` `:1566`; `partial` `:1569`; `uptime_s` `:1571` | REAL 14-key set: `test_status_snapshot_keys_and_cuda_values` `test_daemon.py:1595` (asserts the exact 14 keys `:1610-1612`); mode-on-wire: `test_dispatch_status_response_carries_mode` `:143` (test_control_socket.py) | ✅ |
| **(f)** | unknown cmd → `{ok:false,error}` | `_dispatch` falls through to `return {"ok":False,"error":f"unknown command: {cmd!r}"}` (also hit by a MISSING cmd — `msg.get("cmd")` is None). Malformed JSON + non-dict JSON also → `{ok:false,error}` | unknown `:1965`; malformed `:1896`; non-dict `:1899` | `test_dispatch_unknown_command` `:169`; `test_dispatch_missing_cmd` `:173`; `test_dispatch_malformed_json` `:177`; `test_dispatch_non_dict_json` `:182` (test_control_socket.py) | ✅ |
| **(g)** | start/toggle BLOCK during load (single-flight) + response has `listening` after arm | `start`→`self._daemon.start()` (calls `_load_host`, single-flight under `_lock` — a concurrent caller WAITS on the in-flight load)→`_arm_response()`. `_arm_response` returns `{ok:false,error}` if the load failed (load_error set AND not listening), else `{ok:true,**status}` (carrying `listening`). toggle takes the same arm path when arming | `_dispatch` start `:1908`; `_arm_response` `:1875` (ok:false `:1889`); `_load_host` single-flight `:698` | single-flight: `test_load_recorder_single_flight_one_build_under_concurrency` `test_daemon.py:3010` + `test_load_and_unload_serialize_on_the_same_single_flight_lock` `:3198`; post-arm listening: `test_dispatch_start_stop_set_listening` `:126`; load-failure suppression: `test_start_suppressed_when_load_fails` `test_daemon.py:2994` | ✅ |

> All 7 checks **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this
> round. The `_dispatch` branches are exhaustive (the 7 known commands + the unknown fallthrough), and
> the status payload's 5 required fields are all present in `status_snapshot`.

## 3. Test results

```
.venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'
...................................                                      [100%]
35 passed, 179 deselected in 3.01s
```

**35 passed, 0 failed, 0 errors.** The `-k` filter spans BOTH files by design: `socket`/`control`/
`dispatch`/`cmd` select the `test_control_socket.py` suite (path, mkdir, stale-unlink, the 7 command
branches, the error paths, the real-socket round-trips), and `status` selects `test_daemon.py`'s
`test_status_snapshot_*` tests (the REAL 14-key status payload — see nuance §4.1) + the single-flight
tests (nuance §4.2). Every one of the 7 checks has at least one dedicated pinning test.

## 4. Non-defect test-coverage nuances (recorded so they are NOT mistaken for code gaps)

### 4.1 (e) the socket `_StubDaemon` uses a REDUCED key set — the REAL key set is pinned in test_daemon.py

`tests/test_control_socket.py:_StubDaemon.status_snapshot()` (`:45`) returns a **9-key** dict
(`{listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model}`) — it
OMITS `phase`/`models_loaded`/`mode`/`load_error`/`mic_ok`/`mic_error`. Consequently
`test_dispatch_status_has_all_keys` (`:120`) pins that **reduced 9-key set on the WIRE**, NOT the real
daemon's 14-key set. The REAL `status_snapshot()` key set is pinned by
`test_status_snapshot_keys_and_cuda_values` in **`test_daemon.py:1595`** (asserts the exact 14 keys,
line 1610-1612, incl `phase`/`models_loaded`/`mode`/`load_error`/`mic_ok`/`mic_error`). And
`test_dispatch_status_response_carries_mode` (`:143`) subclass-proves the wire spread surfaces `mode`
when the daemon emits it. **NON-DEFECT**: the socket layer is tested with a duck-typed stub (no
recorder, no lifecycle fields); the real key set is covered in `test_daemon.py`. The CODE is compliant
(`status_snapshot` has all 5 clause-(e) fields). This mirrors the "compliant-by-design" recording
convention used in `gap_feedback.md` §4 + `gap_typing.md` §4.1.

### 4.2 (g) single-flight + load-failure-arm-response coverage lives in test_daemon.py, not test_control_socket.py

The socket tests use `_StubDaemon` (no `_load_host`, no `_load_error`) — they prove **dispatch wiring** +
**post-arm `listening`** + the `{ok:true,**status}` spread, NOT the single-flight load or the
`_arm_response` ok:false path. The single-flight (`start`/`toggle` block during a load — a concurrent
caller waits on the in-flight load) is a **daemon** concern, tested in `test_daemon.py`
(`test_load_recorder_single_flight_one_build_under_concurrency` `:3010`;
`test_load_and_unload_serialize_on_the_same_single_flight_lock` `:3198`); the load-failure arm
suppression is `test_start_suppressed_when_load_fails` (`:2994`). The `_arm_response` ok:false path is
exercised through those (the daemon sets `_load_error`; `_arm_response` reads it via `getattr`). **NON-
DEFECT**: the coverage is split across the two test files by responsibility (socket wiring vs. daemon
load lifecycle). The CODE is compliant (`start`→single-flight `_load_host`→`_arm`→`_arm_response` with
`listening`).

## 5. Conclusion

**PASS — no fix required.** `voice_typing/daemon.py`'s control socket is PRD §4.2(3)/§4.8-compliant on
all 7 checks: the path resolves to `$XDG_RUNTIME_DIR/voice-typing/control.sock` (`:355`) with a clear
RuntimeError when XDG is unset (a); the parent dir is `mkdir 0o700` + the socket `chmod 0o600` (`:1773`/
`:1787`) (b); a stale socket is `os.unlink`'d before `bind` (`:1774-1776`) (c); all 7 commands
(`toggle`/`start`/`stop`/`status`/`toggle-lite`/`start-lite`/`quit`) dispatch to the right daemon method
+ return the correct JSON (`_dispatch` `:1892-1963`) (d); `status_snapshot` carries all 5 required
fields (`phase`/`models_loaded`/`mode`/`partial`/`uptime_s`, `:1548-1574`) (e); an unknown/missing
command returns `{ok:false,error}` (`:1965`) (f); and `start`/`toggle` block on the single-flight load
then respond with `listening` after arm (`_arm_response` `:1875`) (g). The contract's `-k` suite is
**35 passed**.

The two recorded non-defect nuances are test-coverage observations, not code gaps: the socket
`_StubDaemon`'s reduced 9-key status (the real 14-key set is pinned in `test_daemon.py:1595` — §4.1),
and the single-flight/load-failure coverage living in `test_daemon.py` (the socket tests use a stub —
§4.2). The code is compliant regardless.

**No source changes were required and none were made.** This report is the only artifact produced by
this subtask. Adjacent concerns are correctly deferred: the **`ctl.py` client** (rendering, exit codes,
the client-side "loading models…" hint) is **P1.M3.T2.S2**; **`status.sh`** is **P1.M3.T2.S3**; the
**recorder-host subprocess lifecycle** (the load the single-flight serializes) is **P1.M2.***
(Complete). Downstream **P1.M5.T5** (acceptance cross-check) can consume this report as the evidence
that **Acceptance #6** ("`voicectl toggle/start/stop/status/quit` all work") is met at the daemon side.
```

### Implementation Patterns & Key Details

```python
# PATTERN: each check -> PRD clause -> daemon.py file:line -> pinning test (in test_control_socket.py
# OR test_daemon.py) -> ✅ verdict (mirror gap_feedback.md's §2 table). Example for check (d):
#   "(d) all 7 commands -> _dispatch branches toggle:1898/start:1908/start-lite:1911/toggle-lite:1915/
#    stop:1922/status:1924/quit:1926; success = uniform {ok:true,**status_snapshot()} spread. ✅."

# PATTERN: non-defect nuances are recorded explicitly (gap_feedback.md §4 style) so a future auditor
# does not re-flag them: "4.1 socket _StubDaemon reduced key set — real 14-key set pinned in
# test_daemon.py:1595. NON-DEFECT." / "4.2 single-flight/load-failure coverage in test_daemon.py —
# socket tests use a stub. NON-DEFECT."

# GOTCHA: re-verify live; line numbers drift. The report cites the CURRENT file:line + the LIVE pytest
# count (replace <today>; confirm 35). (Critical #2.)

# GOTCHA: gap_socket.md is a NEW file (CREATE). Do NOT append to / touch gap_feedback.md (parallel S2).
# (Critical #3.)
```

### Integration Points

```yaml
AUDIT (read-only):
  - voice_typing/daemon.py: "READ — _default_control_socket_path / ControlServer.start / _dispatch / status_snapshot / _arm_response"
  - tests/test_control_socket.py: "READ + RUN — cite the pinning test per check (socket layer)"
  - tests/test_daemon.py: "READ + RUN — the REAL status key set (:1595) + single-flight (:3010/:3198) coverage for (e)+(g)"
REPORT (the deliverable):
  - create: "plan/006_862ee9d6ef41/architecture/gap_socket.md (NEW file)"
NO code/test/config changes:
  - daemon.py / test_control_socket.py / test_daemon.py: UNCHANGED (compliant — read-only audit)
  - PRD.md: READ-ONLY (forbidden)
  - gap_feedback.md: UNCHANGED (parallel P1.M3.T1.S2 owns it — DIFFERENT area)
DOWNSTREAM:
  - P1.M5.T5 (acceptance cross-check): "consumes this report as the Acceptance #6 (all commands work) evidence"
  - P1.M3.T2 (the parent): "S1 (socket) + S2 (voicectl) + S3 (status.sh) close the control-plane + feedback-UI audit"
```

## Validation Loop

> The audit's validation = re-run the `-k` suite + verify the report exists w/ the right structure +
> git status shows only gap_socket.md. No code is compiled/edited (read-only). FULL PATHS.

### Level 1: The audited files are unchanged (read-only guard)

```bash
cd /home/dustin/projects/voice-typing
echo "--- daemon.py / test_control_socket.py / test_daemon.py NOT modified by this audit ---"
git status --porcelain voice_typing/daemon.py tests/test_control_socket.py tests/test_daemon.py   # expect: empty
```

### Level 2: The contract's test command (re-run live; record the count)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'
# Expected: 35 passed (GPU-free). Record the pass count + time in the report's §3.
```

### Level 3: The report exists with the required structure

```bash
cd /home/dustin/projects/voice-typing
test -f plan/006_862ee9d6ef41/architecture/gap_socket.md && echo "L3 gap_socket.md exists" || echo "L3 FAIL"
grep -n 'Gap Report — P1.M3.T2.S1: Control socket protocol' plan/006_862ee9d6ef41/architecture/gap_socket.md   # the title
grep -cE '✅' plan/006_862ee9d6ef41/architecture/gap_socket.md   # >=7 (one per check a-g)
grep -nE 'reduced key set|single-flight.*test_daemon|NON-DEFECT|nuance' plan/006_862ee9d6ef41/architecture/gap_socket.md   # the 2 nuances
grep -nE '35 passed' plan/006_862ee9d6ef41/architecture/gap_socket.md   # the live pytest count
# Expected: the title present; >=7 ✅; both nuances; the 35-passed line.
# Confirm gap_feedback.md was NOT touched (parallel S2 owns it):
git status --porcelain plan/006_862ee9d6ef41/architecture/gap_feedback.md   # expect: empty (NOT this task's file)
```

### Level 4: Scope guard

```bash
cd /home/dustin/projects/voice-typing
echo "--- ONLY gap_socket.md created; no source modified ---"
git status --porcelain
# Expected: "?? plan/006_862ee9d6ef41/architecture/gap_socket.md" (one new file). Any M to
#   voice_typing/daemon.py / tests/* / PRD.md, OR any change to gap_feedback.md = SCOPE VIOLATION.
echo "--- the report is daemon-side socket only (does not audit ctl.py / status.sh / recorder-host) ---"
# (The §2 table lists checks (a)-(g) — socket path/protocol/commands/errors — NOT ctl.py rendering (S2),
#  NOT status.sh (S3), NOT the recorder-host lifecycle (P1.M2.*). Confirm by reading the §2 header.)
```

## Final Validation Checklist

### Technical Validation
- [ ] `git status --porcelain voice_typing/daemon.py tests/test_control_socket.py tests/test_daemon.py` → empty (read-only).
- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_daemon.py -q -k 'socket or control or cmd or dispatch or status'` → 35 passed; count recorded in §3.
- [ ] `gap_socket.md` exists with the `# Gap Report — P1.M3.T2.S1: Control socket protocol …` title.
- [ ] The report has a ✅ verdict + `daemon.py` file:line + a pinning test for each of the 7 checks (a)-(g).
- [ ] `gap_feedback.md` is UNCHANGED (parallel P1.M3.T1.S2 owns it; this task does not touch it).

### Feature Validation
- [ ] Checks (a) path; (b) mkdir 0700 + chmod 0600; (c) stale-unlink-before-bind; (d) all 7 commands; (e) status 5 fields; (f) unknown→{ok:false,error}; (g) single-flight block + post-arm listening — each verified live with evidence + a pinning test.
- [ ] The 2 non-defect nuances (socket _StubDaemon reduced key set; single-flight/load-failure coverage in test_daemon.py) are documented in §4.
- [ ] The report cites the LIVE file:line (re-verified, not this PRP's numbers).

### Code Quality Validation
- [ ] The report mirrors `gap_feedback.md`'s structure (title + date + scope + audited artifacts + bottom line + method + findings table + test results + nuances + conclusion).
- [ ] Scope is the daemon-side socket (7 checks) only — no ctl.py (S2), no status.sh (S3), no recorder-host lifecycle (P1.M2.*).
- [ ] Read-only — no source modified; CREATE only (gap_feedback.md untouched).

### Documentation & Deployment
- [ ] `gap_socket.md` is the only artifact change; it lands in the `architecture/gap_*.md` series.
- [ ] No README/ACCEPTANCE edits (item DOCS: none — internal protocol).

---

## Anti-Patterns to Avoid

- ❌ Don't modify `daemon.py` or ANY source file — this is a READ-ONLY audit; the code is compliant (Critical #1).
- ❌ Don't trust this PRP's file:line numbers blindly — re-grep + re-read the live tree; cite the CURRENT lines (Critical #2).
- ❌ Don't APPEND to `gap_feedback.md` (or any existing file) — gap_socket.md is a NEW file (CREATE). The parallel P1.M3.T1.S2 owns gap_feedback.md (a DIFFERENT area); do not touch it (Critical #3).
- ❌ Don't flag the socket `_StubDaemon`'s reduced 9-key status as a gap — it's a NON-DEFECT (the real 14-key set is pinned in test_daemon.py:1595); record it in §4.1, do NOT "fix" the stub (Critical #4).
- ❌ Don't flag the single-flight/load-failure coverage living in test_daemon.py as a gap — it's a NON-DEFECT (the socket tests use a stub); record it in §4.2 (Critical #5).
- ❌ Don't conflate the daemon-side socket with the `ctl.py` client — ctl.py rendering/exit-codes/loading-hint is P1.M3.T2.S2 (Gotcha #9).
- ❌ Don't claim `test_dispatch_status_has_all_keys` (`:120`) pins the REAL status key set — it pins the stub's reduced 9-key set; the real 14-key set is test_daemon.py:1595 (Critical #4).
- ❌ Don't invent a report structure — mirror `gap_feedback.md` (the format template).
- ❌ Don't write the report anywhere except `plan/006_862ee9d6ef41/architecture/gap_socket.md`.
- ❌ Don't run `mypy` (not installed) or bare `python`/`pytest` — use `.venv/bin/python -m pytest` (Gotcha #8).
- ❌ Don't add tests in this audit — it only REPORTS coverage; adding tests is a separate task (read-only).
- ❌ Don't drop the `-k` filter or run only one test file — the contract's command spans BOTH files (the `status` keyword pulls test_daemon.py's real-key-set + single-flight tests); cite the FULL command + 35 (Gotcha #10).

---

**Confidence Score: 9.5/10** for one-pass success. The audit is read-only and the verdict is pre-established
(compliant on all 7 checks, with file:line + pinning-test evidence in the research note, cross-file
coverage split correctly attributed to test_daemon.py for (e)+(g)); the deliverable's path + format are
pinned to the established `gap_*.md` convention (confirmed by `gap_feedback.md` + the sibling
P1.M1/P1.M2 audit PRPs); the 2 non-defect nuances are identified; the exact test command + its live
count (35) are verified; and the verbatim report content is provided in Task 3 SOURCE (the implementer
re-verifies the line numbers live + fills the `<today>` placeholder). The −0.5 reserves: the audit must
re-verify live (line numbers drift) + the cross-file coverage attribution for (e)+(g) must be stated
carefully (the socket stub's reduced key set vs. test_daemon.py's real key set) — but the grep gates
(title present; ≥7 ✅; both nuances; 35-passed line; only gap_socket.md in git status; gap_feedback.md
untouched; no source modified) catch structural/verdict/scope regressions deterministically.
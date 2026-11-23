# PRP — P1.M1.T2.S3: Journal-noise regression guard (no per-burst fallback storms)

## Goal

**Feature Goal**: Pin D3.1's closure with a deterministic regression test: after the datagram merge
(S1) + contact gap (S2), the ydotool socket path must NEVER degrade to per-burst CLI spawns +
WARNINGs while healthy, and a single socket death must cost exactly ONE fallback spawn + ONE warning
before self-healing. This replaces journal-scraping with a test assertion (delta acceptance #3).

**Deliverable** (1 test file edited, no source change):
1. `tests/test_typing_backends.py` — TWO additive tests (in-file DGRAM server + one client double):
   - `test_socket_healthy_datagram_zero_cli_spawns_zero_warnings` — a REAL `YdotoolClient` bound to an
     in-file AF_UNIX SOCK_DGRAM server; N consecutive `press_backspace` bursts → ZERO CLI argvs, ZERO
     "falling back" warnings (pre-merge this was N spawns + N warnings — the 56/week Errno-91 storm).
   - `test_socket_death_one_fallback_spawn_one_warning_then_heals` — a client double that raises ONCE
     then succeeds (self-heal; real reconnect coverage is S1's test_ydotoold_client restart tests) →
     N total calls → exactly ONE CLI argv + exactly ONE warning + all N calls routed to the client.

**Success Definition**:
- (a) Healthy-socket test: `recorder.argvs == []` and zero filtered WARNING records across N=8
      consecutive `press_backspace(2)` bursts through the injected real `YdotoolClient`.
- (b) Death-then-heal test: N=6 bursts → `len(recorder.argvs) == 1` (the one `ydotool key -d 6 …`
      fallback), exactly one "falling back" WARNING record, `client.calls == N`.
- (c) No source file changes (`git diff --name-only` == `tests/test_typing_backends.py`); the routing
      under test (typing_backends.py ~134-151) is verified-correct, only pinned.
- (d) Full suites green: `timeout 300 .venv/bin/pytest tests/test_typing_backends.py
      tests/test_ydotoold_client.py -q` (S3's 2 tests additive).
- (e) D3.1 closed as a test-pinned property (no journal scraping anywhere in the repo's gates).

## User Persona

**Target User**: the maintainer reading `journalctl` (or CI) — the guard ensures the 56-warnings/week
Errno-91 storm class can never silently return via a routing or merge regression.
**Pain Points Addressed**: PRD §8 Known defects — "EVERY connection since f0d8d0a failed with Errno 91
and degraded to per-burst CLI spawns (56 journal warnings/week)". The merge fixed it; this test keeps
it fixed.

## Why

- **PRD §8 mandates the merge + gap; delta acceptance #3 mandates the proof be a test**: "assert via
  tests, not journal scraping." S1 (merge) + S2 (gap) are the fix; S3 is the regression lock.
- **The routing is the property.** `YdotoolBackend.press_backspace` routes client-present → socket,
  falling back (ONE spawn + ONE warning at typing_backends.py:143-144) per FAILING call. The storm was
  "every call fails"; health is "no call fails". Only a test can pin both directions cheaply.
- **Restart coverage already exists** (S1's `tests/test_ydotoold_client.py` reconnect/restart tests) —
  S3 deliberately does NOT duplicate client-internals coverage; it pins the BACKEND's no-storm routing.

## What

Add two tests to `tests/test_typing_backends.py` under a P1.M1.T2.S3 banner:
- an in-file ~12-line AF_UNIX SOCK_DGRAM server helper (tmp_path socket; daemon thread recvfrom-ing
  into a list) — self-contained, never importing from `tests/test_ydotoold_client.py` (which may still
  be landing), never touching `/run/ydotoold.socket`;
- Test A constructs the REAL `YdotoolClient(socket_path=…)` and injects it via `YdotoolBackend(client=…)`;
- Test B uses a `_DyingOnceClient` double (calls counter; raises once with an Errno-91-flavored
  RuntimeError, then succeeds);
- both reuse the existing `recorder` fixture (monkeypatched `subprocess.run`) + the file's caplog idiom,
  counting warnings by message text ("falling back") because the logger name is shared with the wtype
  fallback warning.

### Success Criteria

- [ ] Both tests exist under a banner citing P1.M1.T2.S3 / D3.1 and pass.
- [ ] Test A asserts ZERO argvs + ZERO warnings (the no-storm property) over N=8 consecutive bursts.
- [ ] Test B asserts EXACTLY ONE argv + EXACTLY ONE warning over N=6 bursts with a once-dying client.
- [ ] No real socket path `/run/ydotoold.socket`, no real CLI spawn (recorder guards), no `time.sleep` mocking.
- [ ] `git diff --name-only` == `tests/test_typing_backends.py`; both suites green.

## All Needed Context

### Context Completeness Check

_Pass._ The routing under test (typing_backends.py ~123-151) and the warning site (~143-144) are quoted
verbatim in the research note; the landed client constructor (`YdotoolClient(socket_path=None)` @31,
SOCK_DGRAM `_connect` @39) was verified on disk; the test seam (`_Recorder` @44-75, `recorder` fixture
@77, caplog idiom @257-263, n≤0 precedent @327) was read from the live file. An agent new to the repo
can write both tests from this PRP + the note alone.

### Documentation & References

```yaml
# MUST READ — this task's verified design + the routing/warning-site truth + the landing gate
- docfile: plan/008_a47116bb2b79/P1M1T2S3/research/no_storm_regression_test_design.md
  why: "§3 the verbatim routing (n<=0 guard; client-present try/except; ONE warning + CLI per failing
        call); §4 the existing seam (_Recorder/.argvs/caplog idiom; NO existing client-injection test —
        S3 adds the first); §5 the two-test design incl. WHY the DGRAM server is in-file (don't import
        from a still-landing test module); §2 the Task-0 gate commands."
  critical: "§6: if Test A shows spawns/warnings on a healthy socket, that is a REAL S1-merge bug —
            report it, do not weaken the test."

# MUST READ — the parallel sibling (gate + no-duplication boundary)
- docfile: plan/008_a47116bb2b79/P1M1T2S2/PRP.md
  why: "S2 adds _CONTACT_GAP_S (timing only; S3 asserts COUNTS, not timing — orthogonal). Its Task-0/
        Downstream sections name S3 as the owner of the typing_backends fallback guard."
  critical: "Gate on BOTH: tests/test_ydotoold_client.py exists (S1) AND grep _CONTACT_GAP_S
            voice_typing/ydotoold_client.py (S2)."

# THE ROUTING UNDER TEST (read ~123-151)
- file: voice_typing/typing_backends.py
  why: "YdotoolBackend.__init__(client=None) @123; press_backspace @134-151: n<=0 return; client path
        try/except Exception -> logger.warning('ydotoold client failed; falling back to ydotool CLI',
        exc_info=True) (~143-144) -> _paced_run CLI; client absent -> CLI only."
  pattern: "Inject via YdotoolBackend(client=obj) — the designed seam. DO NOT edit this file."
  gotcha: "The warning logger is 'voice_typing.typing_backends' — SHARED with the wtype fallback
           warning; count records by 'falling back' message text."

# THE LANDED CLIENT (verify constructor at implementation time)
- file: voice_typing/ydotoold_client.py
  why: "YdotoolClient(socket_path: str | None = None) @31 (verified); press_backspace(n) @66; SOCK_DGRAM
        _connect @39. Construct ONLY with an explicit tmp socket_path."
  gotcha: "Real client paces ~18 ms/char post-S2 — Test A's 8×press_backspace(2) ≈ 0.3 s real sleeps;
           acceptable; do NOT mock time.sleep (measurement-bound style)."

# THE TEST FILE — the seam to reuse
- file: tests/test_typing_backends.py
  why: "_Recorder @44-75 (monkeypatched subprocess.run; .argvs) + recorder fixture @77; caplog idiom
        @257-263; test_ydotool_press_backspace_exact_argv @318 (CLI argv when client=None — mirror its
        argv assert for Test B's one spawn); banner-section style throughout."
  critical: "ADDITIVE only — do not touch existing tests. Import the client lazily inside the test
            module top is fine (voice_typing.ydotoold_client exists post-gate)."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/typing_backends.py     # READ-ONLY for S3 (routing + warning site ~143-151).
voice_typing/ydotoold_client.py     # LANDED (S1): YdotoolClient(socket_path=None), SOCK_DGRAM. READ-ONLY.
tests/test_ydotoold_client.py       # S1's 11 tests (gate on its existence; S3 does NOT import/edit it).
tests/test_typing_backends.py       # ← EDIT: +2 tests (+in-file DGRAM server helper + _DyingOnceClient).
```

### Desired Codebase tree with files to be changed

```bash
tests/test_typing_backends.py       # ADD: the P1.M1.T2.S3 section (2 tests + helpers). No new files.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — GATE ON S1 AND S2 (Task 0): test -f tests/test_ydotoold_client.py AND
# grep -q _CONTACT_GAP_S voice_typing/ydotoold_client.py. The client module itself is verified LANDED —
# but S3's suites run the sibling file too. If either gate fails: STOP and flag (blocked on S1/S2).

# CRITICAL #2 — DO NOT IMPORT FROM tests/test_ydotoold_client.py. It is S1's, may still be landing, and
# cross-test-module imports are fragile (tests/ is not a package). Build the ~12-line in-file DGRAM
# server instead: socket.socket(AF_UNIX, SOCK_DGRAM) bound to str(tmp_path/"ydotoold-test.sock"), a
# daemon thread looping sock.recvfrom(4096) appending to a list, closed via a stop flag + sock.close()
# (SOCK_DGRAM recvfrom unblocks on close with OSError — catch + break).

# CRITICAL #3 — COUNT WARNINGS BY MESSAGE TEXT. The logger 'voice_typing.typing_backends' also carries
# the wtype auto-fallback warning; filter [r for r in caplog.records if "falling back" in
# r.getMessage()] — and prefer the exact substring "ydotoold client failed" for Test B's single warning.

# CRITICAL #4 — THE CLIENT IS STATEFUL/RECONNECTING; THE DOUBLE MODELS THE HEALED CLIENT. The real
# client self-heals its connection internally (S1's restart tests cover it). Test B's double raises ONCE
# then succeeds — pinning the BACKEND property (one fallback per failing call, none thereafter). Do not
# try to kill a real client's socket mid-test for B (racy); the double is deterministic.

# GOTCHA #5 — REAL PACING ON TEST A (~0.3 s total) is fine; do NOT mock time.sleep (the suite's
# measurement-bound style is deliberate). Keep N small (8 bursts × 2 chars).

# GOTCHA #6 — NEVER THE REAL DAEMON SOCKET: always YdotoolClient(socket_path=str(tmp_path/…)); the real
# /run/ydotoold.socket must never receive test datagrams (it would type into the live session).

# GOTCHA #7 — n<=0 IS NOT THIS TASK'S CASE: the guard is already tested (@327). Use n=2 per burst.

# GOTCHA #8 — FULL PATHS + INNER TIMEOUTS (AGENTS.md): timeout 300 .venv/bin/pytest …; .venv/bin/python.
# No ruff/mypy. Never run the heavy GPU tests.
```

## Implementation Blueprint

### Data models and structure

None — two test functions, one in-file DGRAM server helper, one `_DyingOnceClient` double (calls list +
fails flag).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE — S1 + S2 landed
  - RUN:
      cd /home/dustin/projects/voice-typing
      test -f tests/test_ydotoold_client.py && echo "S1 landed" || echo "STOP: blocked on S1"
      grep -q _CONTACT_GAP_S voice_typing/ydotoold_client.py && echo "S2 landed" || echo "STOP: blocked on S2"
      timeout 300 .venv/bin/pytest tests/test_typing_backends.py -q 2>&1 | tail -1   # baseline green

Task 1: ADD tests/test_typing_backends.py — the P1.M1.T2.S3 section (both tests)
  - PLACE: a new banner section at the END of the file:
      # ===========================================================================
      # P1.M1.T2.S3 — journal-noise regression guard (D3.1, PRD §8 known defects):
      # a healthy ydotoold DATAGRAM socket must NEVER degrade to per-burst CLI spawns
      # + WARNINGs (the pre-merge Errno-91 storm: 56 journal warnings/week); a single
      # socket death costs exactly ONE fallback spawn + ONE warning, then heals.
      # Counts-only assertions (no timing) — delta acceptance #3: tests, not scraping.
      # ===========================================================================
  - ADD the in-file DGRAM server helper (module-level, next to the section):
        def _dgram_server(tmp_path):
            """In-process AF_UNIX SOCK_DGRAM stand-in for ydotoold (self-contained — S3 deliberately
            does not import S1's test_ydotoold_client module). Returns (sock, received)."""
            import socket as _s, threading as _t
            sock = _s.socket(_s.AF_UNIX, _s.SOCK_DGRAM)
            path = str(tmp_path / "ydotoold-test.sock")
            sock.bind(path)
            received: list[bytes] = []
            stop = _t.Event()
            def _drain():
                while not stop.is_set():
                    try:
                        data, _ = sock.recvfrom(4096)
                    except OSError:
                        break
                    received.append(data)
            th = _t.Thread(target=_drain, daemon=True); th.start()
            return sock, received, path, stop
  - ADD Test A:
        def test_socket_healthy_datagram_zero_cli_spawns_zero_warnings(recorder, caplog, tmp_path):
            """D3.1 regression: a healthy datagram socket routes EVERY burst over the socket —
            zero CLI spawns, zero 'falling back' warnings (pre-merge: N spawns + N warnings)."""
            from voice_typing.ydotoold_client import YdotoolClient
            sock, received, path, stop = _dgram_server(tmp_path)
            try:
                backend = YdotoolBackend(client=YdotoolClient(socket_path=path))
                with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
                    for _ in range(8):                       # N consecutive bursts
                        backend.press_backspace(2)
                assert recorder.argvs == [], f"healthy socket spawned CLI: {recorder.argvs}"
                storms = [r for r in caplog.records if "falling back" in r.getMessage()]
                assert storms == [], f"healthy socket warned: {[r.getMessage() for r in storms]}"
                assert len(received) > 0                     # datagrams actually flowed
            finally:
                stop.set(); sock.close()
  - ADD the double + Test B:
        class _DyingOnceClient:
            """Socket-death double: fails the FIRST call (Errno-91 flavor) then succeeds — models the
            real client's self-heal reconnect (restart coverage: S1's test_ydotoold_client)."""
            def __init__(self):
                self.calls = 0
                self._died = False
            def press_backspace(self, n: int) -> None:
                self.calls += 1
                if not self._died:
                    self._died = True
                    raise RuntimeError("Protocol wrong type for socket (Errno 91)")

        def test_socket_death_one_fallback_spawn_one_warning_then_heals(recorder, caplog):
            """One socket death = exactly ONE CLI fallback spawn + ONE WARNING, then the healed client
            serves the rest with zero further spawns/warnings (the no-storm property)."""
            backend = YdotoolBackend(client=_DyingOnceClient())
            with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
                for _ in range(6):                           # N total bursts, first one dies
                    backend.press_backspace(2)
            assert len(recorder.argvs) == 1, f"expected exactly ONE fallback spawn: {recorder.argvs}"
            assert recorder.argvs[0][:4] == ("ydotool", "key", "-d", "6")   # the CLI fallback argv
            warns = [r for r in caplog.records if "ydotoold client failed" in r.getMessage()]
            assert len(warns) == 1, f"expected exactly ONE warning: {[r.getMessage() for r in warns]}"
  - RUN: timeout 300 .venv/bin/pytest tests/test_typing_backends.py -q -k "healthy_datagram or death_one_fallback" -v
  - EXPECTED: both PASS. If Test A fails with spawns/warnings on a healthy socket → a REAL merge bug:
    report it (do NOT weaken the test — research §6).

Task 2: VALIDATE — the Validation Loop below. No git commit unless directed. If asked:
  "P1.M1.T2.S3: journal-noise regression guard — healthy datagram socket = zero CLI spawns/warnings;
   one death = one fallback + one warning then heals (D3.1 closed, test-pinned)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — counts-only assertions (the acceptance #3 discipline): recorder.argvs length +
# filtered caplog records; NO timing asserts (S2 owns pacing) and NO journal scraping.
# PATTERN 2 — message-filtered warning count (the logger is shared with the wtype fallback):
warns = [r for r in caplog.records if "ydotoold client failed" in r.getMessage()]
# PATTERN 3 — real client + in-file DGRAM server for the healthy path (true D3.1 fidelity);
# deterministic double for the death path (real mid-test socket killing is racy).
```

### Integration Points

```yaml
UPSTREAM — S1 (merge; landed) + S2 (contact gap): gate on both; S3 asserts counts only, so S2's
           timing change is orthogonal. S2's only typing_backends touch is a comment.
DOWNSTREAM — none (D3.1 closes here). The real client's reconnect/restart coverage stays in S1's
             test_ydotoold_client.py — S3 does NOT duplicate it.
NO SOURCE CHANGES: typing_backends.py / ydotoold_client.py read-only; config/systemd/README untouched.
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic — the recorder fixture makes real CLI spawns impossible; the DGRAM server is in-process tmp. Run from `/home/dustin/projects/voice-typing`.

### Level 1: The tests are in place (static)

```bash
cd /home/dustin/projects/voice-typing
grep -n 'test_socket_healthy_datagram_zero_cli_spawns_zero_warnings\|test_socket_death_one_fallback_spawn_one_warning_then_heals' tests/test_typing_backends.py \
  && echo "L1 PASS: both tests present" || echo "L1 FAIL"
grep -n 'ydotoold.socket' tests/test_typing_backends.py | grep -v 'tmp_path' && echo "L1 FAIL: real socket path referenced" || echo "L1 PASS: tmp-path only"
timeout 60 .venv/bin/python -c "import ast; ast.parse(open('tests/test_typing_backends.py').read()); print('L1 PASS: parses')"
```

### Level 2: The two new tests (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/pytest tests/test_typing_backends.py -q -k "healthy_datagram or death_one_fallback" -v 2>&1 | tail -4
# Expected: 2 PASSED. Test A failing with spawns/warnings = a REAL healthy-socket bug (report, don't
# weaken). Test B failing with 2+ warnings = the client raised twice (check the double) or the n<=0
# guard was bypassed.
```

### Level 3: No regressions (both suites)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/pytest tests/test_typing_backends.py tests/test_ydotoold_client.py -q 2>&1 | tail -2
# Expected: all green (existing backends tests + S1's 11 + S2's spacing test + S3's 2).
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'tests/test_typing_backends.py' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS: test-only"
git diff --quiet voice_typing/typing_backends.py voice_typing/ydotoold_client.py && echo "L4 PASS: source untouched" || echo "L4 FAIL: source changed"
git diff --exit-code -- PRD.md plan/008_a47116bb2b79/tasks.json plan/008_a47116bb2b79/prd_snapshot.md .gitignore && echo "L4 PASS: read-only unchanged" || echo "L4 NOTE: orchestrator bookkeeping"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: both tests present; no real socket path; file parses.
- [ ] L2: both new tests pass (zero spawns/warnings healthy; exactly one each on death-then-heal).
- [ ] L3: both suites green.
- [ ] L4: diff == tests/test_typing_backends.py; source/read-only untouched.

### Feature Validation
- [ ] D3.1 closed as a test-pinned property (no journal scraping).
- [ ] Healthy datagram socket ⇒ N bursts ⇒ 0 CLI argvs + 0 warnings; datagrams actually flowed.
- [ ] One socket death ⇒ exactly 1 fallback argv (`ydotool key -d 6 …`) + 1 warning; healed client serves the rest.

### Code Quality Validation
- [ ] Counts-only asserts; message-filtered warning counts; no time.sleep mocking.
- [ ] Reuses `recorder`/caplog idioms; banner cites P1.M1.T2.S3/D3.1; additive only.

### Scope Boundary Validation
- [ ] No source edits; no import from S1's test module; real restart coverage left to S1's file.

### Documentation & Deployment
- [ ] DOCS: none (contract). The banner + docstrings are the durable explanation.

---

## Anti-Patterns to Avoid

- ❌ Don't start before S1's test file + S2's `_CONTACT_GAP_S` land (Task 0 gate).
- ❌ Don't weaken Test A if it fails — a healthy-socket storm is a REAL merge bug; report it.
- ❌ Don't import from `tests/test_ydotoold_client.py` (still landing; cross-module test imports are fragile) — in-file DGRAM server.
- ❌ Don't count warnings without the message filter — the logger name is shared with the wtype fallback.
- ❌ Don't kill a real client's socket mid-test for the death path — the deterministic double is the design.
- ❌ Don't assert timing (S2's territory) or scrape journals (acceptance #3 forbids it) — counts only.
- ❌ Don't reference the real `/run/ydotoold.socket`; don't mock `time.sleep`; don't edit source; don't touch PRD/tasks/snapshots.

---

## Confidence Score

**9/10** for one-pass implementation success. TEST-ONLY, two small additive tests over a fully verified
seam: the routing + warning site (typing_backends.py ~134-151) read verbatim, the landed client
constructor (`YdotoolClient(socket_path=None)`) confirmed on disk, and the existing test idioms
(`_Recorder.argvs`, caplog-with-message-filter, banner style) read from the live file. The one trap
(shared logger name → message-filtered warning counts) and one fragility (importing S1's still-landing
test module → in-file server instead) are both pre-solved. The −1 is the dependency residual: S1's
`tests/test_ydotoold_client.py` must exist (gated; the client module itself is already landed), and
Test A's healthy-path fidelity depends on the real client's connect behavior being final post-merge —
if Test A finds a storm, that is a genuine bug to report, not a planning failure.

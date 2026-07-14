# PRP — P1.M1.T2.S2: Reduce `_bounded_shutdown` default timeout from 10s to 5s (Fix 1C)

## Goal

**Feature Goal**: Tighten the daemon's teardown-timeout budget so a single `_bounded_shutdown()` call is bounded at ~7s (was ~12s), giving the SIGTERM teardown path comfortable headroom under systemd's `TimeoutStopSec=15`. This is **Fix 1C** of bugfix Issue 1 (the third of three measures: 1A = `RecorderHost._stop_lock` [Complete], 1B = daemon single-flight coordination [P1.M1.T2.S1, parallel], **1C = this task**). The change is one parameter default (`10.0` → `5.0`) plus budget-math docstring/comment alignment.

**Deliverable** (3 core files edited, no new files):
1. `voice_typing/daemon.py` — `_bounded_shutdown()` signature default `10.0` → `5.0` + a budget-math paragraph in its docstring; the "(default 10s)" phrase in `shutdown()`'s docstring → "(default 5s)".
2. `systemd/voice-typing.service` — the timeout-budget comment (~L44-48) updated to the 5s math (the contract's Mode A doc).
3. (stale-value alignment) `tests/test_daemon.py`, `tests/test_systemd_unit.py`, `tests/test_idle_and_gpu.sh` — align the now-stale `10s` references for accuracy (none break; see Context).

**Success Definition**:
- (a) `_bounded_shutdown`'s signature default is `5.0` (the one behavioral change). `request_shutdown()` and `shutdown()` (both use the default) now tear down at ~7s max per call; `_unload_host()`'s explicit `timeout=5.0` is now redundant-but-harmless (explicit == default) and is LEFT as-is.
- (b) `_bounded_shutdown`'s docstring documents the budget: `host.stop(timeout=5) → join(5)+killpg+join(2) ≈ 7s/call; + server.stop() join(2) ≈ 2s; with single-flight (P1.M1.T2.S1) total ≤ ~9s < TimeoutStopSec=15`.
- (c) The systemd unit's budget comment reflects the 5s default; `TimeoutStopSec=15` itself is UNCHANGED.
- (d) No test breaks (verified: no test asserts on the real default; the one `10.0` in a test is a lambda's own default). The full fast suite stays green.
- (e) No out-of-scope work: no change to `request_shutdown()`/`shutdown()` call sites (they keep using the default), no `recorder_host.py` (T1.S1), no single-flight coordination (S1), no config/ctl/control-socket/README.

## User Persona

**Target User**: the user running `systemctl --user stop voice-typing` (or logging out → SIGTERM) who expects a clean, prompt stop — not a 15.2s hang + SIGKILL. (The user-visible fix is the COMPOSITION 1A+1B+1C; this subtask contributes the budget-tightening 1C.)

## Why

- **bugfix Issue 1 (Critical)** is the source. The SIGTERM teardown blew the 15s `TimeoutStopSec` → SIGKILL + `Failed with result 'timeout'` (reproduced 2/2 at 15.2s). `bug_analysis.md` Fix Strategy prescribes three measures; **1C is "Reduce the teardown timeout budget for headroom."** With the old `timeout=10`: `host.stop` = `join(10)+killpg+join(2)` ≈ 12s/call; even a SINGLE teardown + `server.stop()` join(2) = ~14s — no margin under 15s. Reducing to 5s: `join(5)+killpg+join(2)` ≈ 7s/call + 2s = ~9s — comfortable.
- **1C is REQUIRED for the clean SIGTERM path.** Fix 1B (S1) makes `shutdown()` WAIT (bounded `_TEARDOWN_WAIT_TIMEOUT=8.0`) for the in-flight teardown instead of starting a second one. S1 sized that 8.0s wait **assuming 1C's ~7s teardown** lands: with 1C, the teardown signals `_teardown_done` well inside 8.0s → `shutdown()` returns clean (~9s total). WITHOUT 1C, a single ~12s teardown exceeds the 8.0s wait → `shutdown()` falls back to its own teardown on every SIGTERM (still safe via 1A's `_stop_lock`, but ~12s+2s wall-time, not the clean path). So 1B fixes the double-teardown BUG; 1C makes the budget actually fit.
- **Scope discipline.** This subtask owns ONLY the timeout default + its budget-math docs. It does NOT add single-flight coordination (S1), does NOT touch `recorder_host.py` (T1.S1), does NOT add the SIGTERM-subprocess test (T2.S3), does NOT change config/systemd's `TimeoutStopSec`/README/ctl.

## What

- `daemon.py _bounded_shutdown()`: `timeout: float = 10.0` → `timeout: float = 5.0`; add a budget-math paragraph to its docstring.
- `daemon.py shutdown()` docstring: "(default 10s)" → "(default 5s)" (a disjoint phrase from S1's IDEMPOTENT-paragraph edit — apply both).
- `systemd/voice-typing.service`: update the budget comment (~L44-48) to the 5s math; `TimeoutStopSec=15` unchanged.
- (accuracy alignment, optional-but-recommended) `tests/test_daemon.py:1472` lambda `10.0`→`5.0` + assertion `[10.0]`→`[5.0]`; `tests/test_systemd_unit.py` docstring 10s→5s; `tests/test_idle_and_gpu.sh:40` `≤10s`→`≤7s`.

### Success Criteria

- [ ] `grep -n 'def _bounded_shutdown(self, timeout' voice_typing/daemon.py` shows `timeout: float = 5.0`.
- [ ] `_bounded_shutdown` docstring contains the budget sentence ("host.stop(timeout=5) → join(5)+killpg+join(2) ≈ 7s").
- [ ] `shutdown()` docstring no longer says "(default 10s)" — it says "(default 5s)".
- [ ] `_unload_host()` STILL calls `_bounded_shutdown(timeout=5.0)` (left as-is; explicit == new default).
- [ ] `request_shutdown()`/`shutdown()` STILL call `self._bounded_shutdown()` with no arg (they pick up 5.0 via the default — NO explicit arg added).
- [ ] `systemd/voice-typing.service` budget comment reflects 5s; `TimeoutStopSec=15` unchanged.
- [ ] Full fast pytest suite green (no test asserts on the real default; the lambda at test_daemon.py:1472 is aligned to 5.0).
- [ ] No edits to `request_shutdown()`/`shutdown()` bodies or call sites, `recorder_host.py`, config, ctl, README.

## All Needed Context

### Context Completeness Check

_Pass._ The change is one parameter default plus docstring/comment text. Every edit site is quoted verbatim below; the call sites are enumerated (which use the default vs explicit); the contract-vs-bug_analysis reconciliation is explicit (change the default, NOT add an explicit arg); the S1 composition (why 5s) and no-conflict boundary are documented; and the stale-`10s` reference inventory is complete. A developer new to this repo can apply the patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the fix strategy (1A/1B/1C); this subtask is 1C
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "§Issue 1 'Fix Strategy' → Fix 1C: 'Reduce _bounded_shutdown default timeout from 10.0s to 5.0s.
        A single teardown: host.stop(timeout=5) → proc.join(5) + killpg + join(2) ≈ up to 7s. Plus
        server.stop() join(2) = up to 2s. Total ≤ 9s, comfortable headroom under 15s.'"
  critical: "bug_analysis also says 'Update request_shutdown() to call _bounded_shutdown(timeout=5.0).'
            The ITEM CONTRACT supersedes that: change the DEFAULT instead (covers BOTH request_shutdown
            AND shutdown in one edit, less churn). Do NOT add an explicit timeout=5.0 to the callers."

# MUST READ — this task's verified edit sites, call-site table, contract-vs-bug_analysis reconciliation,
#              the S1 composition (why 5s), and the stale-10s inventory
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T2S2/research/fix1c_timeout_reduction_edit_sites.md
  why: "The full codebase analysis: exact current _bounded_shutdown signature + docstring; the 3 call
        sites (request_shutdown/shutdown use the default; _unload_host uses explicit 5.0); WHY the line
        numbers are stale (S1 is editing daemon.py concurrently → navigate by signature); the S1
        composition (_TEARDOWN_WAIT_TIMEOUT=8.0 presupposes 1C's ~7s teardown); and every stale '10s'
        reference with its alignment action."
  section: "§2 (contract vs bug_analysis) and §4 (S1 composition) are load-bearing."

# MUST READ — the parallel sibling (no-conflict boundary + the composition)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T2S1/PRP.md
  why: "S1 (1B) adds daemon single-flight: request_shutdown claims _shutdown_done + signals _teardown_done;
        shutdown() WAITS on _teardown_done (_TEARDOWN_WAIT_TIMEOUT=8.0) instead of a 2nd teardown. S1's
        Gotcha #9 EXPLICITLY leaves _bounded_shutdown's timeout to THIS task ('DON'T CHANGE ... HERE.
        That is T2.S2'). S1's _TEARDOWN_WAIT_TIMEOUT=8.0 was sized for 1C's ~7s teardown."
  critical: "S1 and S2 share ONE surface: shutdown()'s docstring. S1 edits the IDEMPOTENT paragraph; S2
            edits the '(default 10s)' phrase — DISJOINT sentences, text edits compose. No line conflict."

# THE EDIT SITE — _bounded_shutdown (navigate by signature; line ~1294 but SHIFTING — S1 is editing daemon.py)
- file: voice_typing/daemon.py
  why: "_bounded_shutdown(self, timeout: float = 10.0) is the one behavioral edit (10.0 -> 5.0). Its
        docstring gets the budget-math paragraph. The two default-using callers (request_shutdown @~1194,
        shutdown @~1368) pick up 5.0 automatically — DO NOT add an explicit arg. _unload_host @~1003 uses
        explicit timeout=5.0 (now redundant; LEAVE it)."
  pattern: "The method routes through self._host.stop(timeout=timeout). For a real RecorderHost: join(timeout)
            + killpg + join(2). For the legacy test adapter: bounded in-process force-cleanup. Both bounded."
  gotcha: "Line numbers are STALE on arrival (S1 editing concurrently). Find the method by
           'def _bounded_shutdown(self, timeout' — NOT by line number. The call sites by
           'self._bounded_shutdown()' (default) vs 'self._bounded_shutdown(timeout=5.0)' (explicit)."

# THE MODE-A DOC — the systemd unit's timeout-budget comment (the contract-required doc edit)
- file: systemd/voice-typing.service
  why: "Lines ~44-48 currently say '_bounded_shutdown(timeout=10) ... ~10s ... 15s budget = 10s bound +
        5s grace'. Update to the 5s math (contract gives the exact wording). TimeoutStopSec=15 is UNCHANGED."
  critical: "Mode A = update this one comment. Do NOT change TimeoutStopSec=15 (the contract is explicit:
            'The TimeoutStopSec=15 value itself does NOT change'). The headroom comes from the smaller
            teardown, not a bigger stop budget."
```

### Current Codebase tree (relevant slice — S1 editing daemon.py concurrently)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py             # ← EDIT: _bounded_shutdown signature 10.0->5.0 + docstring budget math;
│   │                         #   shutdown() docstring "(default 10s)"->"(default 5s)".
│   │                         #   _bounded_shutdown @~1294 (SHIFTING); request_shutdown call @~1194;
│   │                         #   shutdown call @~1368; _unload_host explicit call @~1003. NAVIGATE BY NAME.
│   └── recorder_host.py      # T1.S1 (_stop_lock). READ-ONLY for T2.S2.
├── systemd/
│   └── voice-typing.service  # ← EDIT: budget comment ~L44-48 (5s math). TimeoutStopSec=15 UNCHANGED.
└── tests/
    ├── test_daemon.py        # ← (align) lambda @~1472 10.0->5.0 + assertion [10.0]->[5.0]. S1 adds tests ~L1095 (disjoint).
    ├── test_systemd_unit.py  # ← (align) docstring @~97 10s->5s math (comment; asserts TimeoutStopSec=15 unchanged).
    └── test_idle_and_gpu.sh  # ← (align, optional) comment @~40 "<=10s"->"<=7s".
# NOTE: line numbers in daemon.py/test_daemon.py are STALE on arrival — S1 (parallel) is editing both.
# Navigate by method/signature text, not line number.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py            # MODIFY: _bounded_shutdown default 10.0->5.0 + docstring; shutdown() docstring phrase.
systemd/voice-typing.service      # MODIFY: budget comment (5s math); TimeoutStopSec=15 unchanged.
tests/test_daemon.py              # MODIFY (align): lambda default 10.0->5.0 + assertion [10.0]->[5.0].
tests/test_systemd_unit.py        # MODIFY (align): docstring 10s->5s math.
tests/test_idle_and_gpu.sh        # MODIFY (align, optional): "<=10s"->"<=7s" comment.
# No recorder_host.py (T1.S1), no request_shutdown/shutdown coordination (S1), no config/ctl/README.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — LINE NUMBERS ARE STALE ON ARRIVAL. The parallel S1 task is concurrently editing daemon.py
# (it adds _teardown_done to __init__, restructures request_shutdown/shutdown). _bounded_shutdown was at
# L1265 in an earlier read and L1294 now — it WILL move again. FIND IT BY SIGNATURE TEXT:
#   grep -n 'def _bounded_shutdown(self, timeout' voice_typing/daemon.py
# Match the edit on the exact string 'timeout: float = 10.0' inside that def — NOT on a line number.

# CRITICAL #2 — CHANGE THE DEFAULT, DO NOT ADD AN EXPLICIT ARG. bug_analysis.md Fix 1C suggests
# "Update request_shutdown() to call _bounded_shutdown(timeout=5.0)". The ITEM CONTRACT supersedes that:
# change the DEFAULT to 5.0 so BOTH request_shutdown() and shutdown() (which call self._bounded_shutdown()
# with no arg) pick it up in one edit. Do NOT touch the call sites. (Less churn, covers both paths.)

# CRITICAL #3 — _unload_host's EXPLICIT timeout=5.0 IS NOW REDUNDANT — LEAVE IT. After the default becomes
# 5.0, _unload_host's `self._bounded_shutdown(timeout=5.0)` is explicit==default. Removing it is pure churn
# (and risks a merge tangle with nothing gained). The contract says "redundant but harmless" — LEAVE it.

# CRITICAL #4 — TimeoutStopSec=15 DOES NOT CHANGE. The headroom comes from the smaller teardown (~7s vs
# ~12s), NOT from enlarging systemd's stop budget. Editing TimeoutStopSec is out of scope and would change
# the unit's externally-observable stop bound (and break test_systemd_unit.py's TimeoutStopSec=15 assertion).

# CRITICAL #5 — THE VALUE 5.0 (NOT 5) — keep the float literal style. The signature is `timeout: float`;
# match the existing `= 10.0` float-literal form (`= 5.0`), not an int (`= 5`), so the type hint + call
# math (join(5)) read consistently. (The lambda in test_daemon.py:1472 likewise uses `10.0` -> `5.0`.)

# GOTCHA #6 — NO TEST ASSERTS ON THE REAL DEFAULT. The only `10.0` in a test is the lambda at
# test_daemon.py:1472 (`d._bounded_shutdown = lambda timeout=10.0: ...`), which is the lambda's OWN default
# (independent of the real method). The suite is green pre- AND post-change. Aligning that lambda to 5.0 is
# faithfulness, not a breakage fix. test_bounded_shutdown_force_cleans_on_timeout uses explicit timeout=0.3
# (unaffected). test_systemd_unit.py asserts TimeoutStopSec=15 (unchanged), not the 10s.

# GOTCHA #7 — SHARED DOCSTRING WITH S1, BUT DISJOINT SENTENCES. shutdown()'s docstring is edited by BOTH
# S1 (the IDEMPOTENT/single-flight paragraph) and S2 (the "(default 10s)" phrase). They are DIFFERENT
# sentences — text-based oldText/newText edits compose. If applying both PRPs, do S1's docstring edit and
# S2's phrase edit independently (they don't overlap). Do not let one clobber the other.

# GOTCHA #8 — THE BUDGET MATH: a single _bounded_shutdown(5.0) → host.stop(timeout=5) → proc.join(5) +
# _terminate_group() (killpg) + join(2) ≈ 7s MAX (only if the child wedges for the full join; normally far
# less). Plus ControlServer.stop() join(2) ≈ 2s. With S1 single-flight (ONE teardown on the SIGTERM path),
# total ≤ ~9s. Document exactly this in the _bounded_shutdown docstring (the canonical place).

# GOTCHA #9 — FULL PATHS. `.venv/bin/python -m pytest` (this machine aliases python3→uv run). No ruff/mypy
# configured in this project — don't invoke them.
```

## Implementation Blueprint

### Data models and structure

None. No types/config/pydantic. The only "structure" change is one float-literal default (`10.0` → `5.0`) and docstring/comment text.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/daemon.py — _bounded_shutdown signature default 10.0 -> 5.0
  - FIND by signature (line numbers are STALE — S1 is editing daemon.py concurrently):
      grep -n 'def _bounded_shutdown(self, timeout' voice_typing/daemon.py
  - EDIT (exact text replacement):
      FROM:  def _bounded_shutdown(self, timeout: float = 10.0) -> None:
      TO:    def _bounded_shutdown(self, timeout: float = 5.0) -> None:
  - WHY: the one behavioral change. request_shutdown() + shutdown() call self._bounded_shutdown() with no
    arg → they pick up 5.0 automatically (CRITICAL #2 — do NOT add an explicit arg to the callers).

Task 2: MODIFY voice_typing/daemon.py — add the budget-math paragraph to _bounded_shutdown's docstring
  - FIND the docstring (immediately under the def from Task 1). It currently ends with:
        "... Both paths are bounded + best-effort + never re-raise.

        Does NOT null self._host (the caller — _unload_host / shutdown — does that after this
        returns). Idempotent-vs-missing-host: a None host is a no-op (a session that never armed).
        """
  - EDIT: insert a NEW paragraph BEFORE the "Does NOT null self._host" paragraph:
        Budget (bugfix Issue 1 / Fix 1C, P1.M1.T2.S2): host.stop(timeout=5) -> proc.join(5) +
        _terminate_group() (killpg) + join(2) = ~7s max per call (only if the child wedges the full
        join; normally far less); plus ControlServer.stop() join(2) = ~2s. With daemon single-flight
        (P1.M1.T2.S1: exactly ONE _bounded_shutdown runs on the SIGTERM path) the total is <= ~9s —
        comfortable headroom under systemd TimeoutStopSec=15. The default was 10.0 (-> ~12s/call,
        ~14s total, no margin); 5.0 makes the clean single-teardown path fit.
  - This is the canonical home for the budget math (the method that owns the timeout).

Task 3: MODIFY voice_typing/daemon.py — shutdown() docstring "(default 10s)" -> "(default 5s)"
  - FIND shutdown()'s docstring (grep -n 'def shutdown(self)' voice_typing/daemon.py). It contains:
        "Delegates to _bounded_shutdown(): runs recorder.shutdown() in a daemon thread under a hard
         timeout (default 10s); on timeout it force-terminates ..."
  - EDIT (the single stale phrase — DISJOINT from S1's IDEMPOTENT-paragraph edit, Gotcha #7):
      FROM:  under a hard timeout (default 10s);
      TO:    under a hard timeout (default 5s);
  - WHY: this phrase references the value Task 1 changed; align it so the docstring is accurate. S1
    edits a DIFFERENT paragraph of this same docstring — apply both; they don't overlap.

Task 4: MODIFY systemd/voice-typing.service — the timeout-budget comment (Mode A doc)
  - FIND the comment block above TimeoutStopSec (grep -n 'TimeoutStopSec\|_bounded_shutdown(timeout'
    systemd/voice-typing.service). It currently reads:
        # The daemon's own _bounded_shutdown(timeout=10) (P1.M1.T1.S2) makes VoiceTypingDaemon.shutdown()
        # return within ~10s even when RealtimeSTT's shutdown_recorder() wedges at an unbounded
        # threading.Thread.join() (root-caused in P1.M1.T1.S1). The 15s budget = 10s bound + 5s grace
        # for the SIGTERM -> signal-handler -> request_shutdown -> run() exits -> main() finally latency.
  - EDIT to (use the contract's exact budget wording):
        # The daemon's own _bounded_shutdown(timeout=5) (P1.M1.T1.S2 + P1.M1.T2.S2) makes
        # VoiceTypingDaemon.shutdown() return within ~7s even when RealtimeSTT's shutdown_recorder()
        # wedges at an unbounded threading.Thread.join() (root-caused in P1.M1.T1.S1). With daemon
        # single-flight (P1.M1.T2.S1: exactly ONE teardown on the SIGTERM path) the 15s budget =
        # 5s bounded teardown + 5s signal/shutdown coordination + 5s headroom.
  - DO NOT change the TimeoutStopSec=15 line (CRITICAL #4). DO NOT change Restart=/RestartSec=.
  - WHY: Mode A = update this comment (the contract's specified doc). The headroom is real only with
    the smaller teardown; the comment must say so.

Task 5: ALIGN stale "10s" references for accuracy (recommended; none break the suite)
  - 5a. tests/test_daemon.py — the lambda in test_shutdown_delegates_to_bounded_shutdown (grep
        'lambda timeout=10.0' tests/test_daemon.py):
          FROM:  d._bounded_shutdown = lambda timeout=10.0: calls.append(timeout)
                 ...
                 assert calls == [10.0], f"shutdown() did not delegate to _bounded_shutdown(): {calls}"
          TO:    d._bounded_shutdown = lambda timeout=5.0: calls.append(timeout)
                 ...
                 assert calls == [5.0], f"shutdown() did not delegate to _bounded_shutdown(): {calls}"
        WHY: the lambda's own default mirrored the (old) real default; align it so the delegation test
        documents the real value. The suite is green EITHER way (the lambda is independent of the real
        method) — this is faithfulness. (S1 adds its coordination tests ~L1095; this lambda is ~L1472 —
        disjoint, no line conflict.)
  - 5b. tests/test_systemd_unit.py — the test_timeout_stop_sec_bounds_shutdown docstring (grep
        '_bounded_shutdown(timeout=10)' tests/test_systemd_unit.py):
          FROM:  The daemon's own _bounded_shutdown(timeout=10) (P1.M1.T1.S2) returns within ~10s; the 15s
                 unit budget = 10s bound + 5s grace ...
          TO:    The daemon's own _bounded_shutdown(timeout=5) (P1.M1.T1.S2 + P1.M1.T2.S2) returns within
                 ~7s; the 15s unit budget = 5s bounded teardown + 5s coordination + 5s headroom ...
        WHY: comment accuracy (the test asserts TimeoutStopSec=15, which is unchanged — no assertion breaks).
  - 5c. (optional) tests/test_idle_and_gpu.sh:40 — the auto-unload ceiling comment:
          FROM:  ... + <=10s _bounded_shutdown teardown + ...
          TO:    ... + <=7s _bounded_shutdown teardown + ...
        WHY: minor accuracy (5s join + 2s = ~7s). This is a shell-test comment; skip if you want the
        changeset minimal — it does not affect any assertion.
  - These are accuracy alignments, NOT breakage fixes (Gotcha #6). They prevent a future reader from
    seeing a stale "10s" that contradicts the new 5s default.

Task 6: VERIFY call-site INVARIANTS (no behavioral change beyond the default)
  - RUN:
      cd /home/dustin/projects/voice-typing
      echo "--- request_shutdown + shutdown use the DEFAULT (no explicit arg) ---"
      grep -n 'self._bounded_shutdown()' voice_typing/daemon.py    # expect the 2 default-using call sites
      echo "--- _unload_host STILL uses explicit timeout=5.0 (redundant, LEFT as-is) ---"
      grep -n 'self._bounded_shutdown(timeout=5.0)' voice_typing/daemon.py
      echo "--- no stray explicit timeout=10.0 / timeout=5.0 added to request_shutdown/shutdown ---"
      grep -nE 'self\._bounded_shutdown\(timeout=' voice_typing/daemon.py   # expect ONLY _unload_host's
  - EXPECTED: exactly 2 `self._bounded_shutdown()` (default) call sites + exactly 1
    `self._bounded_shutdown(timeout=5.0)` (_unload_host, unchanged). NO new explicit-arg calls added.

Task 7: VALIDATE — run the Validation Loop L1–L4 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S2: reduce _bounded_shutdown default timeout 10s -> 5s (Fix 1C) + budget-math docs".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the ONE behavioral edit (change the default; callers inherit it).
#   request_shutdown() and shutdown() call self._bounded_shutdown() with NO arg -> they inherit the
#   default. Changing 10.0 -> 5.0 tightens BOTH paths in one edit. Do NOT add explicit timeout=5.0 to
#   the callers (bug_analysis suggested that; the contract chose the cleaner default-change).
def _bounded_shutdown(self, timeout: float = 5.0) -> None:   # was 10.0
    ...

# PATTERN 2 — the budget math (a single teardown, composed with S1's single-flight):
#   host.stop(timeout=5) -> proc.join(5) + _terminate_group(killpg) + join(2) ≈ 7s MAX
#   + ControlServer.stop() join(2) ≈ 2s
#   = ~9s total  (with S1: exactly ONE teardown on the SIGTERM path)  < TimeoutStopSec=15  ✓
# The old 10.0 -> ~12s/call -> ~14s total (no margin). Document this in _bounded_shutdown's docstring.
```

### Integration Points

```yaml
PRODUCTION RUNTIME (SIGTERM path, composed fix 1A+1B+1C):
  - 1A (Complete): RecorderHost._stop_lock — concurrent host.stop() calls share ONE teardown.
  - 1B (S1, parallel): request_shutdown claims + does the ONE teardown + signals _teardown_done; shutdown()
    WAITS (_TEARDOWN_WAIT_TIMEOUT=8.0) instead of a 2nd teardown.
  - 1C (THIS task): default 10->5 -> the single teardown is ~7s (not ~12s). With 1B's 8.0s wait, the
    teardown signals well inside the wait -> shutdown() returns clean -> total ~9s < 15s. ✓
  - WITHOUT 1C: a single ~12s teardown > 1B's 8.0s wait -> shutdown() falls back to its own teardown every
    SIGTERM (safe via 1A, but ~12s+2s wall-time, not the clean ~9s path). So 1C is needed for the contract
    OUTPUT's ~9s target.

QUIT PATH (sequential, unchanged):
  - request_shutdown() (teardown @ ~7s now) -> _teardown_done set -> on_quit=shutdown() sees it set ->
    returns immediately. No second teardown. (Was correct; still correct.)

NO INTERFACE / BEHAVIOR CHANGES BEYOND THE TIMEOUT:
  - _bounded_shutdown's signature default is the only behavioral change. request_shutdown()/shutdown()
    signatures + call structure UNCHANGED (S1 owns the coordination restructure).
  - TimeoutStopSec=15 UNCHANGED. config.toml, ctl.py, control-socket protocol, README: UNCHANGED.
  - recorder_host.py: UNCHANGED (T1.S1's _stop_lock is the belt-and-suspenders; 1C is orthogonal).
```

## Validation Loop

> Full paths (machine aliases python3→uv run). All gates are FAST unit tests / greps — NO GPU / models /
> real child / systemd. No ruff/mypy configured. Line numbers in daemon.py are STALE (S1 editing) — gates
> match on TEXT, not line numbers.

### Level 1: The edits are in place (text-matched, not line-matched)

```bash
cd /home/dustin/projects/voice-typing
echo "--- signature default is 5.0 ---"
grep -n 'def _bounded_shutdown(self, timeout: float = 5.0)' voice_typing/daemon.py && echo "L1 PASS: default=5.0" || echo "L1 FAIL"
echo "--- (no stale 10.0 default remains) ---"
grep -n 'def _bounded_shutdown(self, timeout: float = 10.0)' voice_typing/daemon.py && echo "L1 FAIL: stale 10.0 default still present" || echo "L1 PASS: no 10.0 default"
echo "--- budget-math paragraph present in _bounded_shutdown docstring ---"
awk '/def _bounded_shutdown/,/def [a-z_]+\(self.*->.*:/' voice_typing/daemon.py | grep -q 'host.stop(timeout=5) -> proc.join(5)' && echo "L1 PASS: budget math in docstring" || echo "L1 FAIL: budget math missing"
echo "--- shutdown() docstring says (default 5s), not (default 10s) ---"
grep -q 'hard timeout (default 5s)' voice_typing/daemon.py && echo "L1 PASS: shutdown docstring aligned" || echo "L1 FAIL: shutdown docstring still 10s"
echo "--- systemd unit budget comment reflects 5s; TimeoutStopSec=15 UNCHANGED ---"
grep -q '_bounded_shutdown(timeout=5)' systemd/voice-typing.service && grep -q '^TimeoutStopSec=15' systemd/voice-typing.service && echo "L1 PASS: unit comment 5s + TimeoutStopSec=15 intact" || echo "L1 FAIL: unit comment/TimeoutStopSec"
echo "--- daemon.py parses ---"
.venv/bin/python -c "import ast; ast.parse(open('voice_typing/daemon.py').read()); print('L1 PASS: daemon.py parses')"
# Expected: default=5.0; no 10.0 default; budget math present; shutdown docstring 5s; unit comment 5s +
# TimeoutStopSec=15 intact; daemon.py parses.
```

### Level 2: Call-site invariants (the default-change covers both paths; no explicit args added)

```bash
cd /home/dustin/projects/voice-typing
echo "--- exactly 2 default-using call sites (request_shutdown + shutdown) ---"
n_def=$(grep -c 'self._bounded_shutdown()' voice_typing/daemon.py); echo "default calls=$n_def (expect 2)"
echo "--- exactly 1 explicit-timeout call (_unload_host, unchanged) ---"
n_exp=$(grep -cE 'self\._bounded_shutdown\(timeout=' voice_typing/daemon.py); echo "explicit calls=$n_exp (expect 1: _unload_host)"
echo "--- _unload_host's explicit timeout is 5.0 (redundant now, LEFT as-is) ---"
grep -n 'self._bounded_shutdown(timeout=5.0)' voice_typing/daemon.py && echo "L2 PASS: _unload_host explicit 5.0 intact" || echo "L2 FAIL: _unload_host call changed (should be left alone)"
[ "$n_def" -eq 2 ] && [ "$n_exp" -eq 1 ] && echo "L2 PASS: call-site invariants hold" || echo "L2 FAIL: a call site was edited (only the default should change)"
# Expected: 2 default calls + 1 explicit (_unload_host, unchanged). No new explicit-arg calls.
```

### Level 3: No test regression — the fast suite stays green (no test asserts on the real default)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the bounded-shutdown / shutdown delegation tests (the ones touching the timeout) ---"
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "bounded_shutdown or shutdown_delegates or request_shutdown or shutdown" 2>&1 | tail -20
echo "--- the systemd-unit test (asserts TimeoutStopSec=15, unchanged) ---"
.venv/bin/python -m pytest tests/test_systemd_unit.py -v 2>&1 | tail -8
echo "--- full fast suite (confirm no regression anywhere) ---"
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh -q 2>&1 | tail -3
# Expected: ALL green. test_bounded_shutdown_force_cleans_on_timeout (uses explicit timeout=0.3) unaffected;
# test_shutdown_delegates_to_bounded_shutdown green (lambda aligned to 5.0 in Task 5a; if NOT aligned, still
# green — the lambda is independent of the real default); test_systemd_unit green (TimeoutStopSec=15
# unchanged). The fast suite total count is unchanged from baseline (this task edits no test SIGNATURES,
# only a lambda literal + comments) — a count drift means a parallel task (S1) landed tests (expected).
```

### Level 4: Scope guards — only the intended files; no S1/recorder_host/config/TimeoutStopSec work

```bash
cd /home/dustin/projects/voice-typing
echo "--- changed files are within scope ---"
git diff --name-only
echo "--- TimeoutStopSec value UNCHANGED ---"
git diff -- systemd/voice-typing.service | grep -E '^[+-]TimeoutStopSec=' && echo "L4 FAIL: TimeoutStopSec changed" || echo "L4 PASS: TimeoutStopSec unchanged"
echo "--- recorder_host.py / config.py / ctl.py UNTOUCHED (T1.S1 / out of scope) ---"
git diff --quiet voice_typing/recorder_host.py voice_typing/config.py voice_typing/ctl.py && echo "L4 PASS: those files unchanged" || echo "L4 FAIL: an out-of-scope file was modified"
echo "--- no single-flight coordination logic added (S1's job) ---"
git diff -- voice_typing/daemon.py | grep -E '^\+.*(_teardown_done|_shutdown_done|_TEARDOWN_WAIT_TIMEOUT)' && echo "L4 NOTE: single-flight symbols in diff — confirm that's S1's parallel edit, not T2.S2's" || echo "L4 PASS: no single-flight logic in T2.S2's diff (S1 owns it)"
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/tasks.json plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md .gitignore && echo "L4 PASS: read-only files unchanged" || echo "L4 NOTE: tasks.json may show orchestrator bookkeeping (M) — not this subtask"
# Expected: changed files ⊆ {daemon.py, systemd/voice-typing.service, tests/test_daemon.py,
# tests/test_systemd_unit.py, tests/test_idle_and_gpu.sh}; TimeoutStopSec=15 unchanged; recorder_host/
# config/ctl untouched; no single-flight logic in T2.S2's diff (S1 owns it); read-only files unchanged.
# NOTE: daemon.py will ALSO show S1's parallel edits (_teardown_done etc.) in git diff — that is S1's work
# landing concurrently, not T2.S2's. T2.S2's OWN diff is the signature default + the 2 docstring phrases.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `_bounded_shutdown` default = `5.0` (no stale `10.0`); budget-math paragraph in its docstring; `shutdown()` docstring "(default 5s)"; systemd comment 5s + `TimeoutStopSec=15` intact; daemon.py parses.
- [ ] L2: exactly 2 default-using call sites + 1 explicit (`_unload_host`, unchanged); no new explicit-arg calls.
- [ ] L3: bounded-shutdown / shutdown / request_shutdown / systemd-unit tests green; full fast suite green (count may rise from S1's parallel additions — expected).
- [ ] L4: changed files ⊆ {daemon.py, systemd unit, test_daemon.py, test_systemd_unit.py, test_idle_and_gpu.sh}; `TimeoutStopSec=15` unchanged; recorder_host/config/ctl untouched; no single-flight logic in T2.S2's diff.

### Feature Validation
- [ ] Each `_bounded_shutdown()` call is bounded at ~7s (5s join + 2s), down from ~12s.
- [ ] Composed with S1's single-flight, the SIGTERM path totals ≤ ~9s (< `TimeoutStopSec=15`).
- [ ] `_unload_host`'s explicit `timeout=5.0` is redundant-but-harmless and LEFT as-is.
- [ ] `TimeoutStopSec=15` is unchanged (headroom comes from the smaller teardown, not a bigger stop budget).

### Code Quality Validation
- [ ] Float-literal style preserved (`= 5.0`, not `= 5`).
- [ ] Budget math documented in the canonical place (`_bounded_shutdown`'s docstring) + the systemd comment.
- [ ] Stale `10s` references aligned (test lambda, test docstrings/comments) — no contradictory literals.
- [ ] No bare `python`/`pytest` (`.venv/bin/python -m pytest`); no ruff/mypy invoked (not configured).

### Scope Boundary Validation
- [ ] No change to `request_shutdown()`/`shutdown()` call sites or bodies (S1 owns the coordination restructure).
- [ ] No `recorder_host.py` edit (T1.S1's `_stop_lock`); no config/ctl/control-socket/README change.
- [ ] No single-flight coordination logic (`_teardown_done`/`_shutdown_done`/`_TEARDOWN_WAIT_TIMEOUT`) — S1's job.
- [ ] No `TimeoutStopSec` change; no SIGTERM-subprocess test (T2.S3's job).
- [ ] PRD.md, tasks.json, prd_snapshot.md, bug_analysis.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] Mode A doc (systemd budget comment) updated to the 5s math.
- [ ] `_bounded_shutdown` + `shutdown()` docstrings accurate (no stale "10s").
- [ ] No user-facing behavior change beyond the faster teardown bound (the user-visible fix is the 1A+1B+1C composition).

---

## Anti-Patterns to Avoid

- ❌ Don't add an explicit `timeout=5.0` to `request_shutdown()`/`shutdown()` — the contract says change the DEFAULT (covers both in one edit). bug_analysis suggested the explicit-arg form; the contract supersedes it (CRITICAL #2).
- ❌ Don't remove `_unload_host`'s explicit `timeout=5.0` — it's now redundant (explicit == default) but harmless; removing it is pure churn + merge risk (CRITICAL #3).
- ❌ Don't change `TimeoutStopSec=15` — the headroom comes from the smaller teardown, not a bigger stop budget. Changing it breaks `test_systemd_unit.py`'s assertion and is out of scope (CRITICAL #4).
- ❌ Don't match edits by line number — S1 is editing daemon.py concurrently, so line numbers are STALE on arrival. Match on signature/docstring TEXT (`def _bounded_shutdown(self, timeout`, `hard timeout (default 10s)`) (CRITICAL #1).
- ❌ Don't use `= 5` (int) — keep the float-literal `= 5.0` to match the existing `= 10.0` and the `timeout: float` annotation (CRITICAL #5).
- ❌ Don't add single-flight coordination (`_teardown_done`/`_shutdown_done`/`_TEARDOWN_WAIT_TIMEOUT`) — that's S1 (1B). This task is ONLY the timeout default + budget docs.
- ❌ Don't touch `recorder_host.py` (T1.S1's `_stop_lock`), `request_shutdown()`/`shutdown()` bodies (S1's restructure), config, ctl, README, or the SIGTERM-subprocess test (T2.S3).
- ❌ Don't assume a test will break — no test asserts on the real default (the lone `10.0` is a lambda's own default). The suite is green pre- and post-change; the test-lambda alignment (Task 5a) is faithfulness, not a fix.
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `bug_analysis.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9.5/10** for one-pass implementation success. This is a one-parameter surgical change (`10.0` → `5.0`) plus docstring/comment text alignment. Every edit site is quoted verbatim; the call-site table is verified (which callers use the default vs explicit); the contract-vs-bug_analysis reconciliation is explicit (change the default, not add an explicit arg); the S1 composition is documented (S1's `_TEARDOWN_WAIT_TIMEOUT=8.0` presupposes 1C's ~7s teardown for the clean ~9s path); and the no-conflict boundary with S1 is precise (disjoint sentences in `shutdown()`'s docstring; test_daemon.py edits far from S1's additions). No test asserts on the real default, so the suite is green pre- and post-change (verified). The −0.5 residual is the concurrent-edit churn: S1 is editing daemon.py in parallel, so line numbers are stale (the PRP mitigates by matching on signature/docstring TEXT, not line numbers) and the shared `shutdown()` docstring surface requires both PRPs' text edits to compose (they target disjoint sentences). No GPU/models/systemd/network required for any gate.

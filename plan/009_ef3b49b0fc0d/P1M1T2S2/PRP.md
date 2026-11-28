# PRP — P1.M1.T2.S2: Acknowledge priming across recorder IPC

## Goal

**Feature Goal**: Give `RecorderHost` a **confirmed** prompt-priming path across the daemon↔child IPC: an async request/ACK (`("prime", …)` on cmd_q → `("prime_ack", …)` on evt_q) that installs the §4.8.1 initial-prompt seed via the child's `PromptedExecutor.install_initial_prompt` (S1's tri-state primitive) and returns a **sanitized, fenced** result — `applied | clear | unconfirmed` + opaque token count + lane count — with a **deadline and cancellation**, so P1.M1.T2.S3 can gate capture on a *known* priming state instead of the fire-and-forget `set_prompt()` that "cannot count as confirmation." Ordinary rolling `set_prompt()` stays byte-identical.

**Deliverable** (1 source file + 1 test file edited):
1. `voice_typing/recorder_host.py` — (a) `("prime", {"token", "generation", "text"})` child command handler extending the `_prompt_targets` seam → emits `("prime_ack", {"token", "generation", "state", "tokens", "lanes"})` (NO text); (b) daemon-side `prime_prompt(text, *, timeout) -> PrimeResult` — mints a token, puts the command, waits OUTSIDE the reader thread and outside any lock, fences stale/late ACKs by (token, generation), returns a sanitized frozen `PrimeResult`; (c) `cancel_prime()` supersession + a per-host `generation` counter bumped on spawn; (d) reader `_dispatch("prime_ack")` stores the payload + sets `_prime_evt` (the `_cancel_mark`/`_final_evt` pattern); (e) Mode A docstrings on the parent/child queue protocol + confirmed priming.
2. `tests/test_recorder_host.py` — fake-queue/fake-executor tests: confirmed applied (1 lane), clear, unconfirmed (executor failure), known-empty (0 lanes ⇒ known from ready/capability), aliased-lane dedup, **partial failure**, **delayed ACK → timeout → sanitized unconfirmed**, **stale/late ACK fenced** (token mismatch, generation mismatch after respawn), cancellation supersedes, waiter wakes outside the reader thread, **no text in ACK/logs/results**.

**Success Definition**:
- (a) `prime_prompt("seed text", timeout=…)` on a 1-lane warm child returns `PrimeResult(state="applied", tokens=<n>, lanes=1, …)`; the child emitted exactly one `prime_ack` whose payload has NO `"text"` key and no seed substring anywhere.
- (b) 0 lanes (context-prompt not armed, proven by the child's ready/capability) → `state="clear"`, `lanes=0`, `reason="no-lane"` — a KNOWN-empty result, not unconfirmed.
- (c) Executor returns UNCONFIRMED (cold/broken) → `state="unconfirmed"`; an executor that RAISES → `unconfirmed`, no raise across IPC.
- (d) Deadline: no ACK within `timeout` → `state="unconfirmed", reason="timeout"`; a dead child → `reason="dead"`; a stale ACK (wrong token, or old generation after respawn) is DROPPED and never satisfies a live waiter.
- (e) `cancel_prime()` makes the outstanding request unsatisfiable; a subsequent request gets a fresh token and works.
- (f) The waiter runs in the CALLER's thread; the reader thread only stores + sets an Event; nothing blocks the reader or the daemon `_lock`.
- (g) `set_prompt()` behavior byte-identical; all existing recorder-host tests green; `timeout 300 .venv/bin/pytest tests/test_recorder_host.py -q` green (baseline + new).
- (h) `git diff --name-only` == the two files; `daemon.py`/`prompt_engine.py` untouched (S3 wires the caller; S1 owns the executor).

## User Persona

**Target User**: P1.M1.T2.S3's implementer (gate warm/cold capture on priming) and, ultimately, the §4.8.1 opt-in integration user whose editor text seeds the first decode — they need the daemon to KNOW the child saw the seed before capture starts, and never to see their text in journald.

## Why

- **The arch note is the mandate** (system_context.md "Confirmed seed before capture"): "`RecorderHost.set_prompt()` is fire-and-forget … `PromptedExecutor.set_prompt()` catches its own failures, so calling it cannot count as confirmation. Add an explicit confirmed path with observable known-applied/known-clear result for both active lanes (one object is normal), an ACK carrying only opaque token/generation and outcome, after installation and before arming. Reuse the child ready/capability evidence and command ordering; idempotent token checks, no exceptions containing seed text. **Child ACK waiting on its reader, or the control lock, would wedge both the ACK and unrelated clients.**"
- **S1's primitive needs a transport.** S1 (parallel) delivers `install_initial_prompt(text) -> PromptInstallResult(state, tokens)` with the tri-state contract; its Integration Points say verbatim: "S2 wraps install_initial_prompt's result in the child's ACK (opaque state + token count; no text). S1's tri-state maps 1:1; **S2 treats timeout/partial as unconfirmed too**."
- **`_prompt_targets` already names this seam**: its docstring says "the confirmed-prompt ACK (P1.M1.T2.S2) extends THIS seam" — the 0-or-1-element unique-executor list is the dedup point.
- **The waiter-outside-reader rule is load-bearing**: `_read_loop`'s dispatch errors are swallowed precisely because "a dispatch error must never kill the reader thread (it would strand text())"; blocking the reader on a daemon-side wait would strand `text()` and every other event. The `_cancel_mark`/`_final_evt` pattern (reader stores + sets an Event; another thread consumes) is the proven shape.
- **Scope discipline**: S2 = the IPC ACK only. S3 = gating capture (the `_arm` caller). S4 = seed handoff at the first accepted final. daemon.py and prompt_engine.py are not touched.

## What

Add a confirmed priming channel beside the existing fire-and-forget prompt channel:

1. **Child**: a `("prime", {"token": int, "generation": int, "text": str | None})` command arm that calls `install_initial_prompt` on `_prompt_targets(prompt_executor)` (dedup by identity), and emits `("prime_ack", {"token", "generation", "state": <applied|clear|unconfirmed>, "tokens": int|None, "lanes": int})`.
2. **Parent**: `prime_prompt(text, *, timeout=_PRIME_TIMEOUT_S) -> PrimeResult` — mint token, put the command, wait on `_prime_evt` in the caller's thread (bounded, outside `_lock`), accept only the matching (token, generation), return a sanitized frozen `PrimeResult`; `cancel_prime()` fences the outstanding request.
3. **Reader**: `_dispatch("prime_ack")` stores the payload + sets `_prime_evt` — nothing else.
4. **Generation**: `self._generation: int` bumped on every `spawn()` (host lifetime) and stamped on requests + ACKs so an ACK from a previous child can never satisfy a new one.
5. **Docs (Mode A)**: the module docstring's cmd_q/evt_q protocol lists gain the two new messages; the new methods document confirmed-vs-best-effort, the fence, the deadline, and privacy.

### Success Criteria

- [ ] `("prime", …)` / `("prime_ack", …)` appear in the module docstring's protocol lists (Mode A) and in the child loop / reader dispatch.
- [ ] `prime_prompt` never raises across IPC; returns a frozen `PrimeResult` with fields `{state, tokens, lanes, generation, reason}` and NO text field; `__repr__` carries no seed.
- [ ] Applied path: executor APPLIED → `state="applied"`, `tokens` = the opaque count, `lanes=1`.
- [ ] Known-empty path: 0 targets → `state="clear"`, `lanes=0`, `reason="no-lane"`.
- [ ] Unconfirmed paths: executor UNCONFIRMED or raises; timeout; dead child; cancelled → `state="unconfirmed"` with a sanitized `reason`.
- [ ] Stale ACKs (token mismatch / generation mismatch) are dropped (DEBUG, counts only) and never resolve a live waiter.
- [ ] The ACK payload and every log line contain no seed text (test asserts over captured logs + the payload).
- [ ] `set_prompt` untouched; existing tests green; new tests green.
- [ ] Only the two files change.

## All Needed Context

### Context Completeness Check

_Pass._ The IPC seam is read verbatim (set_prompt @349-362; the child prompt arm @1012-1024; `_prompt_targets` @1102-1111 incl. its "S2 extends THIS seam" note; `_read_loop` @502-525; the `_cancel_mark`/`_final_evt`/`_ready_evt` Event precedent @221-229 + `consume_cancel_mark` @409-418), the design decisions are settled in the research note, the S1 result contract is pinned, and the test patterns (`_make_host` @59, direct `_dispatch` tests @82-160, the threaded `_final_evt` test @164) are verified. An agent new to the repo can implement from this PRP + the note.

### Documentation & References

```yaml
# MUST READ — the mandate
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Confirmed seed before capture': set_prompt can't confirm; confirmed path for both active lanes
        (one object normal); ACK = opaque token/generation + outcome only; reuse ready/capability
        evidence + command ordering; idempotent token checks; no exceptions with seed text; child ACK
        waiting on its reader OR the control lock would wedge both the ACK and unrelated clients;
        timeout/partial = unknown, not unavailable; never put seed in logs/feedback/replies."
  critical: "The waiter-outside-reader/outside-lock rule and the no-text rule are non-negotiable; they
            are the two ways this feature could take the daemon down or leak dictation."

# MUST READ — the verified seam + the settled design
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S2/research/prime_ack_ipc_seam_and_design.md
  why: "§1 the verbatim IPC seam (incl. the _cancel_mark precedent and the reader-swallow rule); §2 the
        six design decisions (new 'prime' command vs reuse; token+generation fencing; waiter outside
        the reader; aliased-lane dedup + 0-lane known-empty; the sanitized PrimeResult shape; set_prompt
        untouched); §3 why between-utterances timing works for arming; §4 the test seam; §5 boundaries."
  section: "§2 decisions 2-4 are load-bearing (fence, waiter placement, 0-lane = KNOWN clear)."

# MUST READ — the executor contract consumed (parallel)
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S1/PRP.md
  why: "install_initial_prompt(text: str|None) -> PromptInstallResult(state: PromptState, tokens: int|None)
        — APPLIED/CLEAR only on a warm model, UNCONFIRMED fail-closed, never raises, counts only.
        Its Integration Points: 'S2 wraps the result in the child's ACK (opaque state + token count; no
        text). S2 treats timeout/partial as unconfirmed too.'"
  critical: "S1 may not have landed at implementation time (it is 'Implementing'). Consume by
            attribute (`result.state.value`, `result.tokens`) and let the tests use a duck-typed fake;
            do NOT import PromptState at module top (keeps the child-only import discipline)."

# THE EDIT SITES
- file: voice_typing/recorder_host.py
  why: "module docstring protocol lists @19-30; ctor events @206-229 (add _prime_evt/_prime_ack/
        _prime_token/_generation beside them); set_prompt @349-362 (UNCHANGED — mirror its put
        discipline); spawn @~290-345 (bump _generation); _read_loop @502-525 + _dispatch @541+
        (add the 'prime_ack' arm: store + set Event only); child loop @958-1036 (add the 'prime' arm
        next to 'prompt' @1012); _prompt_targets @1102-1111 (the seam to extend — keep the function,
        add the install loop beside it)."
  pattern: "Reader stores + sets an Event; another thread waits — the _cancel_mark/_final_evt shape.
            Fire-and-forget puts mirror set_prompt (catch BrokenPipeError/OSError/EOFError → _dead)."
  gotcha: "The child loop blocks inside text() during an utterance — a prime sent mid-utterance is
           read only after it; _arm primes while DISARMED so it drains immediately. Bound the wait
           anyway (cold model → fast UNCONFIRMED; dead child → EOF → _dead)."

# THE TEST FILE
- file: tests/test_recorder_host.py
  why: "_make_host @59 (stubbed worker/queues); _dispatch tested directly @82-160 (no thread) — the
        pattern for prime_ack dispatch; test_text_blocks_until_final_event_then_returns @164 drives an
        Event from another thread — the pattern for the waiter/timeout/stale tests. Use queue.Queue
        stand-ins for cmd_q/evt_q (the file's convention) and a duck-typed fake executor
        (install_initial_prompt returning an object with .state.value/.tokens)."
  pattern: "Gate the fake executor's install on a threading.Event to simulate a DELAYED ACK: assert
            prime_prompt(timeout=0.1) → unconfirmed/timeout while the child is 'still working';
            release → a NEW request (fresh token) confirms; the LATE ack for the old token is dropped."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/recorder_host.py   # ← EDIT: protocol docstring; ctor (_prime_evt/_prime_ack/_prime_token/_generation);
                                #   spawn (generation bump); _dispatch ('prime_ack'); child loop ('prime');
                                #   +prime_prompt/+cancel_prime/+PrimeResult; Mode A docstrings.
tests/test_recorder_host.py     # ← EDIT: +the priming test section (fake queues/executor/gates).
voice_typing/prompt_engine.py   # S1's (parallel) — UNTOUCHED here (consumed by attribute).
voice_typing/daemon.py          # UNTOUCHED (S3 wires the _arm caller; set_prompt rolling path unchanged).
```

### Desired Codebase tree with files to be changed

```bash
# (same 2 files; no new files)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE WAITER LIVES IN THE CALLER'S THREAD, NEVER THE READER, NEVER UNDER _lock.
# _read_loop's dispatch must only STORE the ack payload + set self._prime_evt. If the reader waited,
# it would stop draining evt_q → text() strands → the run loop wedges. If the caller held the daemon
# _lock while waiting, every control-socket client wedges (arch: "would wedge both the ACK and
# unrelated clients"). prime_prompt() takes NO lock across the wait (a short lock only to mint the
# token + snapshot the generation, released before waiting).

# CRITICAL #2 — FENCE BY (token, generation). Mint a strictly increasing token per request; stamp the
# host generation (bumped on every spawn). _dispatch stores the ack ONLY IF it matches the outstanding
# (token, generation); mismatches are dropped with a DEBUG counts-only line. This is what makes a
# LATE ack (child finally answered after the caller timed out) or an OLD child's ack (after a respawn)
# unable to satisfy a NEW waiter. "Idempotent token checks" = the same ack delivered twice resolves once.

# CRITICAL #3 — 0 LANES IS A *KNOWN* EMPTY STATE, NOT UNCONFIRMED. _prompt_targets returns [] when the
# child's prompt executor is not armed — and the child's 'ready' payload already proves the
# capability (context_prompt key). The contract: "explicit ready/capability proves empty/disabled/
# unavailable only when clear is known." So: lanes == 0 → state "clear", reason "no-lane". But a
# BROKEN lane (install raised / UNCONFIRMED) → "unconfirmed" (unknown ≠ unavailable).

# CRITICAL #4 — DEDUP ALIASES, CONFIRM BOTH LANES. The same executor object sits in BOTH kwargs
# (T1.S3's one-executor contract). Iterate `list({id(t): t for t in targets}.values())` (or rely on
# _prompt_targets' 0/1 list) so an aliased pair installs ONCE, and report lanes = the confirmed-lane
# count (1 object = both lanes confirmed). If two DISTINCT executors ever appear (future), confirm
# each and report partial failure as unconfirmed (reason "partial").

# CRITICAL #5 — NO TEXT ANYWHERE. The ack payload: {token, generation, state, tokens, lanes} — never
# "text". Logs: counts + reason codes only. PrimeResult: frozen dataclass with no text field (repr
# safe). Exceptions from install are caught in the child and converted to state=unconfirmed; the
# child logs the exception TYPE name only (an exception could embed the input). The test asserts the
# seed substring is absent from the payload, caplog, and str(result).

# CRITICAL #6 — S1 MAY NOT HAVE LANDED. Consume the result by attribute (getattr(result, "state")).value
# with a defensive fallback (a plain-string state), and let tests use a duck-typed fake. Do NOT import
# PromptState/PromptInstallResult at module top — recorder_host.py keeps heavy/child-only imports
# lazy (the daemon process must never import prompt_engine's deps at module load).

# CRITICAL #7 — PRIME IS NOT SET_PROMPT. Keep ("prompt", …) + set_prompt() byte-identical (rolling
# updates, fire-and-forget). A new ("prime", …) command with a token/generation and an ack is the
# confirmed channel. Do not "upgrade" set_prompt to wait.

# GOTCHA #8 — DEAD CHILD: _read_loop's finally sets _dead/_final_evt/_ready_evt on EOF — ALSO set
# _prime_evt there so a blocked prime_prompt wakes immediately and reports reason "dead" (otherwise
# it waits the full timeout). Mirror the existing belt-and-suspenders (text() also polls _proc).

# GOTCHA #9 — THE CHILD LOOP BLOCKS IN text() DURING AN UTTERANCE. A prime sent mid-utterance is read
# only after it returns. _arm primes while DISARMED (cmd_q drains immediately), but the API must still
# bound the wait (timeout → unconfirmed). Do NOT add a watcher thread to the child to pre-empt text()
# (the abort/cancel events are the only sanctioned pre-emptions).

# GOTCHA #10 — FULL PATHS + timeout (AGENTS.md): `timeout 300 .venv/bin/pytest tests/test_recorder_host.py -q`.
# Hermetic (no process, no CUDA); the file's existing tests stub _worker_main. No ruff/mypy.
```

## Implementation Blueprint

### Data models and structure

```python
# Parent-side (recorder_host.py, above RecorderHost or beside it) — the sanitized result S3 consumes:
@dataclass(frozen=True)
class PrimeResult:
    state: str            # "applied" | "clear" | "unconfirmed"
    tokens: int | None    # opaque count (None unless applied)
    lanes: int            # confirmed lanes (0 = known-empty via ready/capability)
    generation: int       # host lifetime the result belongs to
    reason: str           # sanitized code: "ok" | "no-lane" | "partial" | "timeout" | "dead" | "cancelled" | "executor-error"
    # NO text field — repr is safe by construction

# Wire (child → daemon): ("prime_ack", {"token": int, "generation": int, "state": str, "tokens": int|None, "lanes": int})
# Wire (daemon → child): ("prime", {"token": int, "generation": int, "text": str|None})
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT recorder_host.py — ctor state + generation + Event (beside the _cancel_mark block @221-229)
  - ADD in __init__:
        # Confirmed prompt priming (P1.M1.T2.S2 / §4.8.1): the daemon mints a token per request and
        # waits OUTSIDE the reader thread; the reader only stores the matching ack + sets the Event
        # (the _cancel_mark/_final_evt shape — a reader-side wait would strand text()).
        self._prime_evt = threading.Event()
        self._prime_ack: dict | None = None        # last matching ("prime_ack", ...) payload
        self._prime_token: int | None = None        # outstanding request token (None = none)
        self._prime_counter = itertools.count(1)     # strictly increasing tokens
        self._generation = 0                        # bumped on every spawn (host lifetime fence)
  - ADD `import itertools` (stdlib) if not already imported.

Task 2: EDIT recorder_host.py — spawn() bumps the generation
  - FIND spawn() (~@290): where the Process is created/started. ADD before start:
        self._generation += 1
        self._prime_ack = None; self._prime_evt.clear()   # a new child: old acks can never match
  - WHY: an ack from the PREVIOUS child (still in the evt_q pipe) must not satisfy a request to the
    new one — the generation stamp is the fence half the token alone cannot provide.

Task 3: EDIT recorder_host.py — reader _dispatch("prime_ack") (store + set ONLY)
  - ADD an arm in _dispatch (beside "error"/"final"):
        elif kind == "prime_ack":
            # P1.M1.T2.S2: reader-side ONLY stores + wakes. Fence: accept only the outstanding
            # (token, generation); stale/late acks are dropped (counts-only DEBUG). Never waits,
            # never holds a lock beyond the store — see CRITICAL #1.
            tok = payload.get("token"); gen = payload.get("generation")
            if tok is not None and tok == self._prime_token and gen == self._generation:
                self._prime_ack = {k: payload.get(k) for k in ("token", "generation", "state", "tokens", "lanes")}
                self._prime_evt.set()
            else:
                logger.debug("recorder host: stale prime ack dropped (token=%s gen=%s)", tok, gen)
  - ADD in _read_loop's finally (beside _final_evt/_ready_evt): `self._prime_evt.set()` so a dead child
    wakes a blocked prime_prompt immediately (Gotcha #8).
  - DO NOT put any text key in the stored dict (the comprehension above whitelists the 5 safe keys).

Task 4: EDIT recorder_host.py — the child "prime" command arm (beside "prompt" @1012-1024)
  - ADD:
                elif kind == "prime":
                    # P1.M1.T2.S2: CONFIRMED priming (vs the fire-and-forget "prompt" above). Install
                    # on the deduped prompt targets via the executor's confirmed primitive (S1) and
                    # ACK with opaque state/token-count/lane-count only — NEVER the seed text.
                    tok = payload.get("token"); gen = payload.get("generation")
                    text = payload.get("text")
                    targets = list({id(t): t for t in _prompt_targets(prompt_executor)}.values())
                    if not targets:
                        # ready/capability already proved context-prompt is not armed → KNOWN empty
                        _safe_put(evt_q, ("prime_ack", {"token": tok, "generation": gen, "state": "clear", "tokens": None, "lanes": 0}))
                        continue
                    states, ntok, failed = [], None, False
                    for _exec in targets:
                        try:
                            res = _exec.install_initial_prompt(text if isinstance(text, str) or text is None else None)
                            st = getattr(getattr(res, "state", None), "value", None) or str(getattr(res, "state", "unconfirmed"))
                            states.append(str(st)); ntok = getattr(res, "tokens", None)
                        except Exception as exc:   # CRITICAL #5: TYPE name only — never str(exc)
                            logger.warning("child: priming install raised (%s) — unconfirmed", type(exc).__name__)
                            states.append("unconfirmed"); failed = True
                    if failed or any(s == "unconfirmed" for s in states):
                        state = "unconfirmed"
                    elif all(s == "applied" for s in states):
                        state = "applied"
                    elif all(s == "clear" for s in states):
                        state = "clear"
                    else:
                        state = "unconfirmed"        # mixed lanes → partial → unknown (never over-claim)
                    _safe_put(evt_q, ("prime_ack", {"token": tok, "generation": gen, "state": state,
                                                    "tokens": ntok if state == "applied" else None, "lanes": len(targets)}))
  - NOTE: `continue` must fit the loop's structure — if the loop body is a try/except, place the
    no-lane put as a normal statement (no continue) and guard the rest with `if targets:`. Match the
    surrounding style; the outer `except Exception: logger.exception("child: command %r raised")`
    already swallows any slip (but the ack must still be sent — keep the put outside the raise path).

Task 5: EDIT recorder_host.py — the parent API: prime_prompt() + cancel_prime() + PrimeResult
  - ADD PrimeResult (frozen dataclass) at module level (blueprint above), with a Mode A docstring:
    sanitized (no text), states, reason codes, "S3 gates capture on this".
  - ADD methods (beside set_prompt):
        def prime_prompt(self, text: str | None, *, timeout: float = _PRIME_TIMEOUT_S) -> PrimeResult:
            """Confirmed priming across IPC (P1.M1.T2.S2; §4.8.1 initial seed). Puts ("prime", …) with a
            fresh token + the current generation, then WAITS in the CALLER's thread (bounded; never the
            reader thread, never under the daemon lock). Fences by (token, generation): only the
            matching ack resolves; a late/stale ack is dropped by _dispatch. Never raises across IPC.
            Returns a sanitized PrimeResult — unconfirmed on timeout/dead/cancelled (unknown, never
            'unavailable'). set_prompt() stays the ordinary rolling channel."""
            gen = self._generation
            tok = next(self._prime_counter)
            self._prime_ack = None
            self._prime_token = tok
            self._prime_evt.clear()
            try:
                self._cmd_q.put(("prime", {"token": tok, "generation": gen, "text": text}))
            except (BrokenPipeError, OSError, EOFError):
                self._dead = True
                self._prime_token = None
                return PrimeResult("unconfirmed", None, 0, gen, "dead")
            if not self._prime_evt.wait(timeout=timeout):
                if tok == self._prime_token:            # not superseded/cancelled meanwhile
                    self._prime_token = None
                    reason = "dead" if self._dead else "timeout"
                    return PrimeResult("unconfirmed", None, 0, gen, reason)
                return PrimeResult("unconfirmed", None, 0, gen, "cancelled")
            ack = self._prime_ack or {}
            self._prime_token = None                    # resolved; idempotent vs a duplicate ack
            if tok != ack.get("token") or gen != ack.get("generation"):
                return PrimeResult("unconfirmed", None, 0, gen, "stale")
            state = str(ack.get("state", "unconfirmed"))
            lanes = int(ack.get("lanes", 0) or 0)
            tokens = ack.get("tokens") if state == "applied" else None
            reason = "ok" if state in ("applied", "clear") else ("no-lane" if lanes == 0 and state == "clear" else "executor-error")
            return PrimeResult(state, tokens, lanes, gen, reason)

        def cancel_prime(self) -> None:
            """Fence the outstanding priming request (P1.M1.T2.S2): its (possibly late) ack can no
            longer resolve anything. Idempotent; never raises."""
            self._prime_token = None
            self._prime_evt.set()      # wake a blocked waiter → it sees the token cleared → "cancelled"
  - ADD `_PRIME_TIMEOUT_S: float = 5.0` beside `_STOP_JOIN_TIMEOUT_S` (named constant; tests shrink it
    via the kwarg, not by editing the constant).
  - Note the "no-lane" reason precedence: state "clear" + lanes 0 → "no-lane" (known-empty); a plain
    clear with lanes 1 → "ok". (Fix the reason expression accordingly if you prefer explicit branches.)

Task 6: EDIT recorder_host.py — Mode A docstrings
  - Module docstring cmd_q list (@19-23): add `("prime", {"token", "generation", "text"})  # P1.M1.T2.S2 confirmed priming (ack'd)`.
  - Module docstring evt_q list (@29+): add `("prime_ack", {"token", "generation", "state", "tokens", "lanes"})  # opaque — never text`.
  - A short paragraph: confirmed (prime) vs best-effort (prompt); the fence; the waiter-outside-reader
    rule; privacy (counts only); "S3 gates capture on PrimeResult".

Task 7: EDIT tests/test_recorder_host.py — the priming section (TDD: write first where feasible)
  - BUILD a duck-typed fake: `class _FakeExec: def __init__(self, result=None, raise_=None, gate=None)` with
    `install_initial_prompt(self, text)` that optionally waits on `gate` (delayed ack), raises, or
    returns an object with `.state.value` + `.tokens` (use `types.SimpleNamespace(state=SimpleNamespace(value="applied"), tokens=7)`).
  - Tests (names in this spirit):
    * test_prime_prompt_applied_one_lane — fake exec APPLIED(7); drive `host._dispatch("prime_ack", {...matching...})`
      from a thread AFTER calling prime_prompt; assert state "applied", tokens 7, lanes 1, reason "ok".
    * test_prime_prompt_clear_known_empty_zero_lanes — ack lanes 0/state clear → "clear"/"no-lane".
    * test_prime_prompt_unconfirmed_on_executor_failure — ack state "unconfirmed" → "unconfirmed"/"executor-error".
    * test_prime_prompt_timeout_is_sanitized_unconfirmed — no ack; `prime_prompt("x", timeout=0.1)` →
      unconfirmed/timeout; takes < ~1 s.
    * test_prime_prompt_dead_child_wakesImmediately — set host._dead + _prime_evt (the reader-finally path)
      → reason "dead" without waiting the timeout.
    * test_late_ack_for_timed_out_token_is_dropped — request A times out; request B is outstanding; an ack
      with A's token arrives → B stays waiting (not resolved); then B's ack resolves B.
    * test_ack_from_previous_generation_is_fenced — bump _generation (simulate respawn) → an ack with the
      old generation is dropped (DEBUG) and never resolves.
    * test_cancel_prime_fences_and_wakes — a blocked waiter returns "cancelled" promptly; its later ack
      is dropped; a new request works.
    * test_child_prime_command_acks_without_text — run the child command handler with a fake evt_q
      (queue.Queue) + a fake prompt_executor: assert the ("prime_ack", …) payload keys == the 5 safe keys
      and that the seed substring is absent from the payload AND caplog.
    * test_child_prime_dedupes_aliased_executors — pass the SAME fake exec as both lane objects (via a
      patched `_prompt_targets` returning [e, e]) → install called once; lanes counted once.
    * test_set_prompt_unchanged — the existing set_prompt test still green (byte-identical path).
  - CONSTRAINTS: fake queues (`queue.Queue`); fake executor; no process; the child-handler test calls
    the loop body's arm directly or via a minimal harness mirroring the file's existing child-loop
    tests (if the file has none, extract the arm into a small helper `_handle_prime(payload, prompt_executor,
    evt_q)` the child loop calls — keeps it unit-testable without a process).

## Implementation Patterns & Key Details

```python
# PATTERN 1 — reader stores + wakes; the caller waits (the _cancel_mark/_final_evt shape).
#   _dispatch("prime_ack"): if (token, generation) match the outstanding request: store the 5 safe
#   keys + self._prime_evt.set(). Else DEBUG-drop. NO waiting, NO lock held, NO text stored.

# PATTERN 2 — fence = strictly increasing token (per request) + generation (per child lifetime).
#   A late ack (after timeout) or an old child's ack (after respawn) fails the match → dropped.

# PATTERN 3 — sanitized result, fail to UNKNOWN. state ∈ {applied, clear, unconfirmed}; 0 lanes =
#   KNOWN clear (ready/capability proved the executor isn't armed); anything broken/late/timed out
#   = unconfirmed with a reason code. NEVER "unavailable", NEVER text.
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S1 (executor primitive, parallel): install_initial_prompt → PromptInstallResult.
           Consumed BY ATTRIBUTE in the child (CRITICAL #6). Its tri-state maps 1:1; timeout/partial →
           unconfirmed here.
DOWNSTREAM — P1.M1.T2.S3 (gate warm/cold capture on priming): CALLS host.prime_prompt(seed, timeout=…)
           from the arm path — OUTSIDE the daemon _lock, inside the 30 s native start deadline — and
           gates on PrimeResult.state ("applied"/"clear" ⇒ proceed; "unconfirmed" ⇒ degrade to
           context-free + private hint). S2 exposes the API + the result; S3 wires it.
DOWNSTREAM — P1.M1.T2.S4 (seed handoff at first accepted final) and S5 (focus-based starts): further
           consumers of the same API.
UNCHANGED: set_prompt() (ordinary rolling), daemon.py's prompt callers, prompt_engine.py (S1's),
           _prompt_targets (kept; the install loop is added beside it).
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic (no process/CUDA). Run from `/home/dustin/projects/voice-typing`.

### Level 1: The channel is in place (static)

```bash
cd /home/dustin/projects/voice-typing
grep -n 'def prime_prompt\|def cancel_prime\|class PrimeResult\|_prime_evt\|_generation' voice_typing/recorder_host.py | head -12
grep -n '"prime"' voice_typing/recorder_host.py | head -3            # child arm + docstring
grep -n '"prime_ack"' voice_typing/recorder_host.py | head -4        # dispatch + child put + docstring
grep -q 'never text\|NEVER the seed\|opaque' voice_typing/recorder_host.py && echo "L1 PASS: docstring privacy note" || echo "L1 FAIL"
timeout 60 .venv/bin/python -c "import ast; ast.parse(open('voice_typing/recorder_host.py').read()); print('L1 PASS: parses')"
# Expected: prime_prompt/cancel_prime/PrimeResult/_prime_evt/_generation present; both wire messages in
# the docstring + code; privacy note; parses.
```

### Level 2: The priming tests (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/pytest tests/test_recorder_host.py -q -k "prime" -v 2>&1 | tail -16
# Expected: all new tests PASSED. Load-bearing: timeout → sanitized unconfirmed (fast); late-ack
# dropped (token fence); old-generation ack dropped; aliased dedup (install once); payload has no
# text key + no seed in payload/caplog. If the timeout test takes ~5 s: the kwarg wasn't honored.
# If the late-ack test resolves B with A's ack: _dispatch isn't checking the token (CRITICAL #2).
```

### Level 3: No regressions (the full host suite + import purity)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/pytest tests/test_recorder_host.py -q 2>&1 | tail -2
timeout 60 .venv/bin/python -c "import sys, voice_typing.recorder_host; bad=[m for m in ('faster_whisper','torch','ctranslate2','voice_typing.prompt_engine') if m in sys.modules]; print('L3 import-purity', 'PASS' if not bad else f'FAIL {bad}')"
# Expected: full file green (baseline + new); importing recorder_host still pulls no heavy/child-only
# modules (CRITICAL #6 — the PromptState consumption must stay attribute-based).
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'voice_typing/recorder_host.py|tests/test_recorder_host.py' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS"
git diff --quiet voice_typing/daemon.py voice_typing/prompt_engine.py && echo "L4 PASS: daemon/prompt_engine untouched" || echo "L4 NOTE: their diffs are S1's parallel work, not this task's"
git diff voice_typing/recorder_host.py | grep -E '^[+-]' | grep -E 'def set_prompt|_cmd_q.put\(\("prompt"' && echo "L4 FAIL: set_prompt changed" || echo "L4 PASS: set_prompt byte-identical"
# Expected: only the 2 files; daemon/prompt_engine not this task's; set_prompt untouched.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `prime_prompt`/`cancel_prime`/`PrimeResult`/`_prime_evt`/`_generation` present; both wire messages documented + implemented; privacy note; parses.
- [ ] L2: all priming tests pass (applied/clear-known-empty/unconfirmed/timeout/dead/late-ack-fenced/old-generation-fenced/cancel/no-text/dedup).
- [ ] L3: full recorder-host suite green; import purity (no heavy/child-only modules at import).
- [ ] L4: diff ⊆ the 2 files; `set_prompt` byte-identical; daemon/prompt_engine untouched by this task.

### Feature Validation
- [ ] Applied path returns the opaque token count + lanes=1; 0 lanes is KNOWN clear (reason "no-lane").
- [ ] Timeout/dead/cancelled/executor-failure → `unconfirmed` with a sanitized reason; never raises; never "unavailable".
- [ ] Stale/late ACKs (token or generation mismatch) are dropped and never resolve a live waiter; a duplicate ack is idempotent.
- [ ] The waiter runs in the caller's thread; the reader only stores + sets the Event; nothing waits under the daemon lock.
- [ ] No seed text in any ack payload, log line, or result (asserted).

### Code Quality Validation
- [ ] `PrimeResult` is a frozen dataclass with no text field (repr-safe).
- [ ] Mode A docstrings: protocol lists updated; confirmed-vs-best-effort; fence; deadline; privacy.
- [ ] S1's result consumed by attribute (no top-level PromptState import); `_prompt_targets` kept.
- [ ] Tests use fake queues/executors/gates; no process; full paths + `timeout`.

### Scope Boundary Validation
- [ ] `set_prompt()` and the `("prompt", …)` channel byte-identical.
- [ ] No daemon.py edits (S3 wires the caller); no prompt_engine.py edits (S1).
- [ ] No config/systemd/README changes; PRD.md/tasks.json/prd_snapshot.md/.gitignore untouched.

### Documentation & Deployment
- [ ] Mode A: module docstring protocol + confirmed-priming docstrings ride with the work.

---

## Anti-Patterns to Avoid

- ❌ Don't wait in the reader thread (`_read_loop`/`_dispatch`) or under the daemon `_lock` — either wedges `text()` and every control client (CRITICAL #1). Reader stores + sets an Event; the caller waits.
- ❌ Don't fence by token alone — bump and stamp a per-spawn `generation` too, or an old child's ack satisfies a new request after a respawn (CRITICAL #2).
- ❌ Don't report 0 lanes as "unconfirmed" — the child's ready/capability proves the executor isn't armed ⇒ KNOWN "clear" (CRITICAL #3). Conversely never report a broken lane as "clear".
- ❌ Don't let an aliased executor pair install twice or count as two lanes — dedup by identity (CRITICAL #4).
- ❌ Don't put the seed text in the ack, a log line, a result field, or an exception string — counts and exception TYPE names only (CRITICAL #5).
- ❌ Don't import `PromptState` at module top — consume by attribute; recorder_host must stay import-light for the daemon process (CRITICAL #6).
- ❌ Don't "upgrade" `set_prompt` to wait or reuse `("prompt", …)` for priming — a separate `("prime", …)` channel; `set_prompt` byte-identical (CRITICAL #7).
- ❌ Don't forget to set `_prime_evt` in `_read_loop`'s finally — a dead child must wake the waiter immediately (Gotcha #8).
- ❌ Don't add a child watcher thread to pre-empt `text()` for priming — arm primes while disarmed; bound the wait instead (Gotcha #9).
- ❌ Don't edit daemon.py / prompt_engine.py / config / README, or PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**8.5/10** for one-pass implementation success. The IPC seam is fully mapped verbatim (the `("prompt", …)` channel, the child loop's blocking-in-`text()` behavior, `_prompt_targets`' explicit "S2 extends THIS seam" note, `_read_loop`'s swallow-and-never-die rule, and the `_cancel_mark`/`_final_evt` store-and-wake precedent that the waiter design mirrors), the six design decisions are settled with the arch note's two non-negotiables (waiter outside reader/lock; no text) called out as CRITICAL #1 and #5, the result contract is pinned to S1's tri-state with timeout/partial mapped to unconfirmed, and the test seam (direct `_dispatch` tests + the threaded `_final_evt` pattern + fake queues) is verified in the same test file. The −1.5 is the parallel dependency: S1's executor primitive is "Implementing" and not yet in the tree, so the child handler must consume its result by attribute with a defensive fallback (CRITICAL #6) and the tests must duck-type it — if S1's attribute shape differs from its PRP (`.state.value`, `.tokens`), the child arm needs a one-line adjustment, which the Task 4 defensive code already anticipates. The remaining risk is small: the fence/waiter logic has more branches than the average subtask, but each branch has a named test in Task 7.

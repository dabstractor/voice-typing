# PRP — P1.M1.T2.S3: Gate warm and cold capture on current priming

## Goal

**Feature Goal**: Make the daemon's start/arm path **priming-aware and fenced**: a shared
reserve → load → prime → commit seam where the arm decision is reserved under `_lock`, the heavy wait
(load + S2's confirmed `prime_prompt`) happens **outside** `_lock`, and an **atomic revalidation**
under `_lock` gates the actual capture (`set_microphone(True)`) — so the mic never opens until the
prompt state is KNOWN (applied / known-clear) or the host is isolated on uncertainty. Replace `_arm`'s
unconditional fire-and-forget `_clear_context_prompt()` (which would erase a confirmed seed) with a
gated policy: a seed arm installs the confirmed seed and skips the clear; a plain arm after a seeded
session performs a **confirmed** clear (or isolates the host if unconfirmable); a plain arm with no
prior seed stays byte-identical to today. Late/superseded/aborted arms can never commit ("harmless
stale ACK"). Expose a sanitized `ArmOutcome` (`context_seeded` + reason, never text) for S4/S5/T3.S4.

**Deliverable** (1 source file + 1 test file edited, no new files):
1. `voice_typing/daemon.py` — (a) `ArmOutcome` frozen dataclass + `_START_DEADLINE_S = 30.0` /
   `_PRIME_BUDGET_S = 5.0` constants; (b) `__init__` state: `_arm_seq = 0`, `_arming: int | None = None`,
   `_seed_active = False`; (c) new `_start_fenced(seed: str | None, *, streaming, timeout) -> ArmOutcome`
   implementing reserve/load/prime/revalidate/commit with the fail-closed + isolate/confirm-cleanup
   rules; (d) `start()`/`toggle()` route through `_start_fenced(None, …)`; `_arm()` loses its
   unconditional clear (moved into the gated seam; legacy best-effort clear retained ONLY when the host
   has no confirmed channel — fakes/old hosts); (e) Mode A docstrings on start/toggle/_arm/_load_host.
2. `tests/test_daemon.py` — a `_PrimeableFakeHost(_FakeHost)` (recorded `prime_prompt`, scriptable
   result, optional gate/raise) + barrier tests: warm/cold ordering, plain-arm-never-inherits-seed
   (confirmed clear), timeout → no capture + cleanup/isolation, harmless stale ACK, stop-during-prime,
   superseded arm, failed load, unconfirmed seed arm fails closed, `ArmOutcome` text-free.

**Success Definition**:
- (a) Seed arm, warm or cold: observed order is load-complete → `prime_prompt(seed)` → (state applied)
  → `set_microphone(True)`; NO `set_prompt("")` between prime and capture; `ArmOutcome.context_seeded
  is True`, `tokens` = the opaque count.
- (b) Seed arm with `unconfirmed` (timeout/dead/executor) → **no capture** (`set_microphone` never
  True), outcome `ok=False, context_seeded=None`, sanitized reason; the host is left idle-resident or
  isolated — never armed.
- (c) Plain arm (seed None) after a seeded session: a **confirmed** clear (`prime_prompt(None)` →
  clear) precedes capture; if unconfirmable → host isolated (`_bounded_shutdown` + drop, phase
  unloaded), outcome `ok=False, reason="prompt-unconfirmed"`, no capture — plain arm never inherits a seed.
- (d) Plain arm with no prior seed AND a host lacking `prime_prompt` (all existing fakes): behavior
  byte-identical to today (legacy best-effort clear still fires under its existing gates); every
  existing daemon test stays green.
- (e) Revalidation is atomic under `_lock`: a stop/shutdown/drain/newer-reservation/dead-host between
  prime and commit aborts the commit (no capture); a superseded arm's late prime result changes nothing.
- (f) No seed text appears in `ArmOutcome.__repr__`, any log line, or any exception string.
- (g) `timeout 600 .venv/bin/pytest tests/test_daemon.py -q` green (baseline + new);
  `git diff --name-only` == the two files.

## User Persona

**Target User**: the §4.8.1 opt-in integration user whose editor text seeds the first decode — they
need the daemon to KNOW the child saw (or provably cleared) the seed before the mic opens, and never
to have their text leak or a stale seed bleed into an unrelated plain dictation session.

## Why

- **The arch note is the mandate** (system_context.md "Confirmed seed before capture"): "`_arm`
  currently clears via `_clear_context_prompt()` just before `set_microphone(True)`. An unconditional
  clear there would erase a confirmed seed. Make the reservation/arm decision under `_lock` but wait for
  load and prompt confirmation outside it. Treat the 30-second native cap as a total start deadline; a
  late worker may leave a safely idle resident host, never re-arm it. Worker cleanup/disarm/prompt-clear
  belongs to its fenced lifetime, not the next one."
- **Today's ordering cannot host the feature.** `_arm` sets `_listening` and opens the mic in the same
  critical section as the clear — there is no point at which a confirmation can be awaited without
  holding `_lock` (which would wedge every control client: S2 CRITICAL #1 / arch "would wedge both the
  ACK and unrelated clients").
- **"Plain arm must not inherit any seed"** is a correctness property, not a nicety: after a seeded
  session disarms, the child stays resident WITH the seed; the next plain arm must provably clear it
  (S1: `install(None)` on a warm executor → CLEAR proven; cold → UNCONFIRMED) — fire-and-forget
  `set_prompt("")` cannot prove anything (arch: "calling it cannot count as confirmation").
- **Scope discipline.** S2 owns the IPC channel; S1 the executor primitive; S4 the seed→rolling
  handoff at the first accepted final; S5 the focus-based start requests; T3.S4 the native-owner
  reservation. S3 is the daemon-side gated arm seam they all call.

## What

Add the fenced start seam to `VoiceTypingDaemon`:

- **`ArmOutcome`** (frozen dataclass, module level): `ok: bool`, `listening: bool`, `reason: str`,
  `context_seeded: bool | None` (True=applied, False=plain/known-clear, None=unconfirmed/failed),
  `tokens: int | None`, `arm_seq: int`. No text field; sanitized reason codes only.
- **`__init__`**: `_arm_seq = 0` (monotonic arm reservation generation), `_arming: int | None = None`
  (the outstanding reservation token), `_seed_active = False` (a confirmed seed is resident in the child).
- **`_start_fenced(seed, *, streaming=None, timeout=_START_DEADLINE_S) -> ArmOutcome`**:
  1. **Reserve** under `_lock`: `_arm_seq += 1; tok = _arm_seq; _arming = tok` (a newer reservation
     supersedes an older one).
  2. **Load** outside `_lock`: `if not self._load_host(): return failed("load-failed")` (clears `_arming`
     if still ours).
  3. **Prime** outside `_lock` (bounded by `min(_PRIME_BUDGET_S, deadline_remaining)`), only when the
     host has a confirmed channel (`getattr(host, "prime_prompt", None)`): seed arm → `prime_prompt(seed)`;
     plain arm with `_seed_active` → `prime_prompt(None)` (confirmed clear); plain arm with no prior
     seed → no prime call.
  4. **Revalidate** under `_lock` before any capture: abort unless `_arming == tok`, not `_shutdown`,
     not `_listening`, not draining, host is `self._host` and alive. Then apply the prompt policy
     (applied → `_seed_active=True`, skip clear; clear → `_seed_active=False`, skip clear; unconfirmed
     seed arm → fail closed, no capture; unconfirmed plain clear → isolate host: `_bounded_shutdown()` +
     drop host, phase unloaded; no channel → legacy best-effort `_clear_context_prompt()` under its
     existing gates) and run the arm body.
  5. **Abort path**: on revalidation failure, if a seed was confirmed-installed by THIS arm, confirm
     cleanup (`prime_prompt(None)` → clear) or isolate the host before returning; never leave a seed for
     the next arm. Return `ArmOutcome(ok=False, …)`.
- **`start()` / `toggle()`**: route through `_start_fenced(None, streaming=streaming)` (return value
  ignored — existing control-socket behavior preserved: `_load_host` failure already yields `ok:false`
  via `_arm_response`'s `_load_error`; add: when `_start_fenced` returns `ok=False` for a prompt reason,
  set `self._load_error = <sanitized reason>` so `_arm_response` reports `ok:false`).
- **`_arm()`**: remove the unconditional `_clear_context_prompt()` call (now owned by the seam);
  docstring updated (Mode A).
- **Mode A docs**: start/toggle/_arm/_load_host docstrings describe reservation, wait-outside-lock,
  atomic revalidation, and the seed-clear guarantees.

### Success Criteria

- [ ] `ArmOutcome` exists (frozen, no text field) with the fields above; `_START_DEADLINE_S = 30.0`,
      `_PRIME_BUDGET_S = 5.0` module constants.
- [ ] `_start_fenced` implements reserve → load (outside lock) → prime (outside lock, bounded) → atomic
      revalidate → arm; `_arming` cleared on every exit path.
- [ ] Seed arm: prime-then-capture ordering; no clear between; `context_seeded=True` on applied.
- [ ] Unconfirmed seed arm: no capture; `ok=False`, `context_seeded=None`; host idle or isolated.
- [ ] Plain arm after a seeded session: confirmed clear or host isolation; plain arm with no prior seed
      and no channel: byte-identical legacy behavior.
- [ ] Revalidation aborts on stop/shutdown/drain/superseded/dead-host; stale results are harmless.
- [ ] All new tests pass; full `tests/test_daemon.py` green; diff == the two files.

## All Needed Context

### Context Completeness Check

_Pass._ The current start/toggle/_load_host/_arm/_clear_context_prompt bodies were read verbatim
(ordered call sites identified), the S2 input contract (`PrimeResult`, `prime_prompt`, waiter-outside-
lock, fence) and the S1 primitive semantics (warm `install(None)` → CLEAR proven; cold → UNCONFIRMED)
are pinned from their PRPs, the test seam (`_FakeHost`, `_fake_host_factory`, `_make_lazy_daemon`,
`_PromptRecordingHost`, `_GatedFakeHost` barrier pattern, `_wait_for`) is verified, and every branch of
the policy has a named test. An agent new to the repo can implement from this PRP + the research note.

### Documentation & References

```yaml
# MUST READ — the mandate + the exact hazard
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Confirmed seed before capture': _arm clears before set_microphone(True) → would erase a
        confirmed seed; reserve under _lock, wait outside, 30 s total start deadline, a late worker
        leaves an idle resident host and never re-arms; cleanup belongs to its fenced lifetime."
  critical: "Two non-negotiables: never wait under the daemon _lock or on the reader thread; never put
            seed text in logs/feedback/replies/exceptions."

# MUST READ — this task's design (the seam, the policy table, the test matrix)
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S3/research/start_arm_priming_gate_design.md
  why: "§1 the hazard with exact call sites; §2 the verbatim lifecycle (start ~2495, toggle ~2512,
        _load_host ~1044, _arm ~1692 with the clear @~1741 and mic @~1749, _clear_context_prompt ~1666);
        §4 the fenced seam design + the full prompt policy table + ArmOutcome shape + test matrix; §5
        boundaries (S2/S1/S4/S5/T3.S4) + why _seed_active persists across disarm."
  critical: "§4.1 step 4's policy table IS the implementation spec; §4.2's abort-cleanup rule (confirm
            cleanup or isolate — never leave a seed for the next arm)."

# MUST READ — the INPUT contract (parallel; assume landed exactly as specified)
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S2/PRP.md
  why: "prime_prompt(text, *, timeout=5.0) -> PrimeResult(state, tokens, lanes, generation, reason) —
        frozen, sanitized, never raises across IPC; waiter in the CALLER's thread (CRITICAL #1: never
        the reader, never under the daemon lock); stale ACKs fenced by (token, generation);
        cancel_prime(); 0 lanes = KNOWN clear ('no-lane'). Its Integration Points: 'S3 CALLS
        host.prime_prompt(seed, timeout=…) from the arm path — OUTSIDE the daemon _lock, inside the 30 s
        native start deadline — and gates on state (applied/clear ⇒ proceed; unconfirmed ⇒ degrade).'"
  critical: "Consume by attribute (getattr(host, 'prime_prompt', None)); tolerate hosts without it
            (all current test fakes) via the legacy clear path. Do NOT edit recorder_host.py."

# MUST READ — the executor semantics behind 'confirmed clear'
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S1/PRP.md
  why: "install_initial_prompt(None|'') returns CLEAR only on a WARM executor (proven); cold/broken →
        UNCONFIRMED, prompt forced None defensively, no raise, no seed in exceptions. 'S3 uses
        UNCONFIRMED to gate capture / degrade to context-free.'"
  critical: "This is why an unconfirmable plain-arm clear must ISOLATE the host (a cold child may hold
            an unknown prompt) rather than assume clear."

# THE EDIT SITES (navigate by symbol; S1/S2 may shift lines)
- file: voice_typing/daemon.py
  why: "__init__ ~801-930 (locks/events region: add _arm_seq/_arming/_seed_active beside _load_cond @927);
        _load_host ~1044 (docstring only + no logic change); _clear_context_prompt ~1666 (KEEP — the
        legacy no-channel path); _arm ~1692 (remove the unconditional clear @~1741; docstring);
        start ~2495 / toggle ~2512 (route through _start_fenced); module constants near the other
        daemon constants; ArmOutcome above the class."
  pattern: "Mirror the existing lock discipline verbatim: read/reserve under _lock; _load_host and
            prime_prompt OUTSIDE; commit under _lock (start/toggle's current structure). Reuse
            _bounded_shutdown() + the _load_host failure block's drop sequence for isolation."
  gotcha: "_arm sets _listening FIRST — the revalidation must complete BEFORE _arm is entered (once
           listening is set the run loop may call text()). _arm_response reads _load_error for ok:false."

# THE TEST FILE
- file: tests/test_daemon.py
  why: "_FakeHost ~782 (full surface; device dict lacks 'context_prompt' → _context_prompt_active False);
        _fake_host_factory ~886; _make_lazy_daemon ~3610; _PromptRecordingHost ~5028 (set_prompt
        recording — extend this idea for prime_prompt); _GatedFakeHost ~1787 (Event-gated stop — the
        barrier idiom to reuse for a gated prime_prompt); _wait_for ~765; _cuda_resolve ~69."
  pattern: "Subclass _FakeHost as _PrimeableFakeHost: prime_prompt(self, text, *, timeout) records the
            call (text, timeout), optionally waits on self.prime_gate, optionally raises, returns a
            scripted SimpleNamespace(state=..., tokens=..., lanes=1, generation=1, reason=...). Drive
            start()/toggle() on a _make_lazy_daemon(host_factory=…) daemon; assert ordering via the
            recorded call list + rec.mic (the wrapped _StubRecorder records set_microphone)."
  critical: "The fake must mirror S2's never-raise contract for the main tests; ONE test scripts a
            raise to prove the seam still fails closed (defensive — S2 says it never raises)."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py          # ← EDIT: +ArmOutcome, +_START_DEADLINE_S/_PRIME_BUDGET_S, +_arm_seq/_arming/
                                #   _seed_active, +_start_fenced; start/toggle route through it; _arm loses the
                                #   unconditional clear; Mode A docstrings (start/toggle/_arm/_load_host).
tests/test_daemon.py            # ← EDIT: +_PrimeableFakeHost + the fenced-start barrier test section.
voice_typing/recorder_host.py   # S2's (parallel) — UNTOUCHED. Consume prime_prompt/PrimeResult by attribute.
voice_typing/prompt_engine.py   # S1's — UNTOUCHED.
```

### Desired Codebase tree with files to be changed

```bash
# (same 2 files; no new files)
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — NEVER WAIT UNDER self._lock OR ON THE READER THREAD. The prime wait (S2's prime_prompt)
# runs in the arm CALLER's thread with NO daemon lock held (arch + S2 CRITICAL #1: "would wedge both
# the ACK and unrelated clients"). The seam's shape is reserve(under lock) → load+prime(no lock) →
# revalidate+arm(under lock). Holding _lock across prime_prompt would deadlock _load_host (it
# acquire-release-reacquires the same lock) and wedge status/stop.

# CRITICAL #2 — _arm SETS _listening FIRST. The revalidation must be the LAST step before _arm; once
# _arm runs, the run loop may enter text() and a late abort becomes a disarm (visible to the user).
# Everything abortable happens BEFORE _arm.

# CRITICAL #3 — THE UNCONDITIONAL CLEAR IS THE BUG; DON'T JUST MOVE IT. Removing it from _arm and
# calling it earlier in the seam would STILL erase a confirmed seed if the seed was installed first.
# The clear is now POLICY: seed arm → never clear (the seed is the prompt); plain arm + _seed_active →
# CONFIRMED clear via prime_prompt(None); plain arm + no seed + no channel → legacy best-effort clear
# (unchanged); plain arm + no seed + channel present → nothing to clear (prompt provably None from the
# ready/cold-load state or the last confirmed clear) — skip.

# CRITICAL #4 — UNCONFIRMED IS *UNKNOWN*, NEVER *UNAVAILABLE*. Seed arm unconfirmed → do NOT capture
# (the user asked for a seeded session; an unknown prompt is not that). Plain-arm clear unconfirmed →
# the child's prompt is unknown (it may still hold a seed) → ISOLATE the host (bounded shutdown + drop;
# phase unloaded; _load_error set) so the next arm cold-loads a prompt-None child. Never "arm anyway
# and hope" — that is the seed-bleed the arch note forbids.

# CRITICAL #5 — DEADLINE IS THE 30 s NATIVE CAP (TOTAL START), NOT PER-STEP. Reserve t0; load gets the
# remainder; the prime wait gets min(_PRIME_BUDGET_S, remaining). S2's prime_prompt takes timeout= —
# pass the bounded value. A timed-out prime is fenced by S2's token: its late ACK is DROPPED at the
# host, so the daemon only needs its own _arming token check (the "harmless stale ACK" test drives a
# late return from the FAKE to prove the daemon-side fence independently).

# CRITICAL #6 — _seed_active PERSISTS ACROSS DISARM (do not clear it in _disarm). The child stays
# resident with the seed; the next arm decides: a seed arm re-primes; a plain arm confirmed-clears.
# Clearing it at disarm would make the next plain arm SKIP the confirmed clear → seed bleed. Set it
# True only on an APPLIED prime; False only on a CONFIRMED clear or host isolation/drop.

# CRITICAL #7 — EVERY EXIT PATH CLEARS _arming (if still ours). A stale non-None _arming would block
# or confuse the next reservation's revalidation. Use try/finally around the seam body; the finally
# does `with self._lock: if self._arming == tok: self._arming = None`.

# CRITICAL #8 — EXISTING TESTS MUST STAY GREEN WITHOUT EDITS. All current fakes lack prime_prompt and
# start with no seed → the seam takes the legacy branch (no prime call; legacy best-effort clear under
# its existing gates) → byte-identical behavior. If an existing test breaks, the legacy branch diverged.

# CRITICAL #9 — NO TEXT ANYWHERE. ArmOutcome has no text field (repr safe); log lines carry counts,
# states, reason codes, arm_seq — never the seed. Exceptions from a (misbehaving) host are caught in
# the seam and converted to an unconfirmed outcome (log the TYPE name only).

# GOTCHA #10 — _arm_response / CONTROL-SOCKET ok:false. When _start_fenced returns ok=False for a prompt
# reason, set self._load_error = "<sanitized reason>" (and ensure phase is not 'idle' lying about
# readiness — for isolation it's 'unloaded'; for a seed-unconfirmed idle-resident host, leave phase
# 'idle' but _load_error set) so voicectl's `start` reply carries ok:false + the reason via the
# existing _arm_response path. Do not change the protocol shape.

# GOTCHA #11 — TOGGLE'S READ/ACT SPLIT STAYS. toggle reads _listening under _lock, then either
# _request_stop() or the fenced arm — unchanged structure; only the arm side becomes _start_fenced.

# GOTCHA #12 — FULL PATHS + INNER TIMEOUTS (AGENTS.md): timeout 600 .venv/bin/python -m pytest tests/
# test_daemon.py -q. No ruff/mypy. Hermetic fakes only (no CUDA/process/mic).
```

## Implementation Blueprint

### Data models and structure

```python
@dataclass(frozen=True)
class ArmOutcome:
    """Sanitized result of the fenced start seam (P1.M1.T2.S3). NO text field — repr/log safe."""
    ok: bool
    listening: bool
    reason: str                    # "ok" | "seed-applied" | "seed-clear" | "seed-unconfirmed" |
                                   # "prompt-unconfirmed" | "load-failed" | "aborted" | "superseded" | ...
    context_seeded: bool | None    # True=applied, False=plain/known-clear, None=unconfirmed/failed
    tokens: int | None             # opaque count (seed-applied only)
    arm_seq: int                   # the reservation this outcome belongs to

_START_DEADLINE_S: float = 30.0    # the native start cap — TOTAL (load + prime + commit)
_PRIME_BUDGET_S: float = 5.0       # per-prime wait bound (mirrors S2's default); ≤ remaining deadline
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE — S2's channel is callable (or will be); survey baseline
  - RUN:
      cd /home/dustin/projects/voice-typing
      grep -n 'def prime_prompt\|class PrimeResult' voice_typing/recorder_host.py || echo "NOTE: S2 not landed — proceed (consume by attribute; fakes drive the tests)"
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -1   # baseline green
  - The seam consumes prime_prompt by attribute, so S2's absence only means the legacy branch runs on
    the real host until S2 lands — the NEW tests use _PrimeableFakeHost and are independent of S2.

Task 1: EDIT voice_typing/daemon.py — ArmOutcome + constants + __init__ state
  - ADD ArmOutcome (blueprint above) at module level, above class VoiceTypingDaemon; add the two
    constants near the other daemon constants (e.g. beside _DRAIN_TIMEOUT_S).
  - ADD in __init__ beside `self._load_cond = threading.Condition(self._lock)` (~927):
        # P1.M1.T2.S3 — fenced start seam (§4.8.1 confirmed seed before capture).
        self._arm_seq = 0                 # monotonic arm reservation generation (supersedes older arms)
        self._arming: int | None = None   # the outstanding reservation token, or None
        self._seed_active = False         # a CONFIRMED seed is resident in the child (persists across disarm)

Task 2: EDIT voice_typing/daemon.py — the fenced seam `_start_fenced`
  - ADD as a private method (place it directly ABOVE start()):
        def _start_fenced(self, seed: str | None, *, streaming: bool | None = None,
                          timeout: float = _START_DEADLINE_S) -> ArmOutcome:
            """Reserve → load → prime → atomic revalidate → arm (P1.M1.T2.S3; §4.8.1).

            Reservation + the final arm decision run UNDER self._lock; the heavy waits (_load_host's
            spawn, the host's confirmed prime_prompt) run OUTSIDE it so status/stop/quit stay
            responsive and the reader is never blocked. The mic is never opened until the prompt state
            is KNOWN: a seed arm captures only on 'applied'; a plain arm after a seeded session captures
            only after a CONFIRMED clear (unconfirmable → the host is isolated, never reused blind); a
            plain arm with no prior seed keeps the legacy best-effort clear (hosts without a confirmed
            channel) or skips it (nothing to clear). A stop/shutdown/drain/newer reservation/dead host
            between prime and commit aborts the commit — a late or stale prime result can never re-arm
            (the _arming token is the daemon-side fence; the host token is S2's). Never raises; never
            logs or returns seed text.
            """
            t0 = time.monotonic()
            with self._lock:
                self._arm_seq += 1
                tok = self._arm_seq
                self._arming = tok                      # a newer reservation supersedes an older one
            try:
                # --- load OUTSIDE the lock (single-flight inside _load_host) ---
                if not self._load_host():
                    return self._abort_start(tok, None, "load-failed")
                host = self._host
                primer = getattr(host, "prime_prompt", None) if host is not None else None
                remaining = max(0.0, timeout - (time.monotonic() - t0))
                want_seed = seed is not None
                need_clear = (not want_seed) and self._seed_active
                result = None
                if callable(primer) and (want_seed or need_clear):
                    # --- confirmed prime OUTSIDE the lock, bounded by the start deadline ---
                    budget = min(_PRIME_BUDGET_S, remaining)
                    try:
                        result = primer(seed if want_seed else None, timeout=budget)
                    except Exception as exc:            # defensive: a misbehaving host — TYPE name only
                        logger.warning("start: prime_prompt raised (%s) — treating as unconfirmed", type(exc).__name__)
                        result = None
                    state = getattr(result, "state", "unconfirmed")
                    if want_seed and state != "applied":
                        return self._abort_start(tok, host, "seed-unconfirmed", result=result)
                    if need_clear and state != "clear":
                        # Unknown prompt in a resident child while the user asked for a PLAIN arm:
                        # isolate the host so the next arm cold-loads a prompt-None child (fail closed).
                        self._isolate_host("prompt-unconfirmed")
                        return ArmOutcome(False, False, "prompt-unconfirmed", None, None, tok)
                # --- ATOMIC revalidate + commit UNDER the lock ---
                with self._lock:
                    if self._arming != tok or self._shutdown.is_set() or self._listening.is_set() \
                       or self._drain or self._loading or self._host is not host \
                       or not getattr(host, "is_alive", True):
                        stale = self._arming != tok
                        return ArmOutcome(False, False, "superseded" if stale else "aborted", None, None, tok)
                    if want_seed:
                        self._seed_active = True           # the seed IS the prompt — no clear
                    elif need_clear:
                        self._seed_active = False          # CONFIRMED clear
                    elif not callable(primer):
                        self._clear_context_prompt()       # legacy best-effort (no confirmed channel)
                    # else: plain arm, channel present, no prior seed → prompt provably None: skip
                    self._arming = None
                    self._arm(streaming=streaming)
                    seeded = True if want_seed else False
                    return ArmOutcome(True, True, "seed-applied" if want_seed else "seed-clear" if need_clear else "ok",
                                      seeded, getattr(result, "tokens", None) if want_seed else None, tok)
            finally:
                with self._lock:
                    if self._arming == tok:
                        self._arming = None

        def _abort_start(self, tok: int, host, reason: str, *, result=None) -> ArmOutcome:
            """Abort a fenced start AFTER a prime may have installed a seed: confirm cleanup or isolate."""
            if reason == "seed-unconfirmed" and getattr(result, "state", None) == "applied":
                pass  # unreachable by construction (applied proceeds); kept for clarity
            # If THIS arm installed a seed but we are aborting, the child holds it → clear or isolate.
            if host is not None and self._seed_active and reason in ("aborted", "superseded"):
                primer = getattr(host, "prime_prompt", None)
                cleared = False
                if callable(primer):
                    try:
                        cleared = getattr(primer(None, timeout=_PRIME_BUDGET_S), "state", None) == "clear"
                    except Exception as exc:
                        logger.warning("start: abort cleanup raised (%s)", type(exc).__name__)
                if not cleared:
                    self._isolate_host("seed-cleanup-unconfirmed")
                else:
                    with self._lock:
                        self._seed_active = False
            self._load_error = {"load-failed": self._load_error, "seed-unconfirmed": "context seed unconfirmed",
                                "aborted": None, "superseded": None}.get(reason, None) or self._load_error if reason != "aborted" else self._load_error
            return ArmOutcome(False, False, reason, None, None, tok)

        def _isolate_host(self, reason: str) -> None:
            """Retire a host whose prompt state is UNKNOWN (fail closed): bounded teardown + drop, so the
            next arm cold-loads a fresh prompt-None child. Best-effort; never raises."""
            with self._lock:
                host, self._host, self._models_loaded = self._host, None, False
                self._context_prompt_active = None
                self._seed_active = False
                self._feedback.set_phase("unloaded")
                self._feedback.set_models_loaded(False)
            if host is not None:
                try:
                    self._bounded_shutdown_host(host)
                except Exception:
                    logger.exception("start: isolating an unconfirmable host failed (ignored)")
            self._load_error = reason
  - NOTE on `_bounded_shutdown_host(host)`: `_bounded_shutdown()` today tears down `self._host`; since
    the field is already None, call `host.stop(timeout=5.0)` directly inside the try (mirror
    `_bounded_shutdown`'s body: `try: host.stop(timeout=timeout) except Exception: logger.exception(...)`).
    Do NOT change `_bounded_shutdown`'s contract.
  - SIMPLIFY the `_load_error` expression in `_abort_start` to explicit branches (the inline dict above is
    illustrative): load-failed → leave as set by _load_host; seed-unconfirmed → "context seed unconfirmed";
    aborted/superseded → leave untouched.

Task 3: EDIT voice_typing/daemon.py — route start()/toggle() through the seam; slim _arm()
  - EDIT start():
        def start(self, streaming: bool | None = None) -> None:
            # P1.M1.T2.S3: the fenced seam (reserve under _lock → load/prime outside → revalidate+arm
            # under _lock). A plain arm carries no seed; a seeded arm is `start_with_seed` (S5).
            self._start_fenced(None, streaming=streaming)
  - ADD the public seeded entry S5/T3.S4 call (thin wrapper):
        def start_with_seed(self, seed: str | None, *, streaming: bool | None = None,
                            timeout: float = _START_DEADLINE_S) -> ArmOutcome:
            """Fenced start with a §4.8.1 initial-prompt seed (P1.M1.T2.S3). Returns a sanitized
            ArmOutcome; the mic opens only on a CONFIRMED applied seed (or a known clear when seed is
            None). Callers (S5 focus-based starts, T3.S4 native owner) surface `context_seeded`/reason."""
            return self._start_fenced(seed, streaming=streaming, timeout=timeout)
  - EDIT toggle()'s arm side: replace `if not self._load_host(): return` + `with self._lock: self._arm(...)`
    with `self._start_fenced(None, streaming=streaming)` (the disarm side is unchanged).
  - EDIT _arm(): DELETE the `self._clear_context_prompt()` call (~1741) and its preceding comment block;
    replace with a one-line comment: `# P1.M1.T2.S3: the context-prompt clear/seed policy moved to
    # _start_fenced (confirmed clear/seed BEFORE this arm; never an unconditional fire-and-forget).`
  - UPDATE docstrings (Mode A): start, toggle, _arm (locking + seed-clear guarantees), _load_host (note
    it is called outside _lock by the seam; its own contract unchanged).

Task 4: EDIT tests/test_daemon.py — `_PrimeableFakeHost` + the fenced-start section (TDD where feasible)
  - ADD the fake (next to _PromptRecordingHost ~5028):
        class _PrimeableFakeHost(_FakeHost):
            """_FakeHost + a scripted confirmed-prime seam (P1.M1.T2.S3). Records (text, timeout) per
            call; optional Event gate (delayed ACK), optional raise; returns a PrimeResult-like object."""
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.prime_calls: list[tuple[str | None, float]] = []
                self.prime_gate: threading.Event | None = None
                self.prime_raise: Exception | None = None
                self.prime_results: dict[str | None, object] = {}   # keyed by text (None / "seed")
                self.device = {**self.device, "context_prompt": True}   # ready evidence: capability on
            def prime_prompt(self, text, *, timeout=5.0):
                self.prime_calls.append((text, timeout))
                if self.prime_gate is not None:
                    self.prime_gate.wait(timeout=5.0)
                if self.prime_raise is not None:
                    raise self.prime_raise
                res = self.prime_results.get(text if text else None)
                if res is None:
                    res = _PrimeResult(state="applied" if text else "clear", tokens=7 if text else None,
                                       lanes=1 if text else 0, generation=1, reason="ok")
                return res
        class _PrimeResult:   # duck-typed S2 PrimeResult (by-attribute consumption)
            def __init__(self, state, tokens, lanes, generation, reason):
                self.state, self.tokens, self.lanes, self.generation, self.reason = state, tokens, lanes, generation, reason
        def _primeable_factory(script=None):
            def _factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
                h = _PrimeableFakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)
                if script:
                    script(h)
                return h
            return _factory
  - ADD the tests (a new banner section "P1.M1.T2.S3 — fenced start: capture gated on current priming"):
        def test_seed_arm_cold_order_load_prime_then_mic(recorder_free=None):
            host_box = {}
            def _script(h): host_box["h"] = h
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            out = d.start_with_seed("the quick brown fox")
            h = host_box["h"]
            assert out.ok and out.context_seeded is True and out.tokens == 7 and out.reason == "seed-applied"
            assert h.prime_calls == [("the quick brown fox", pytest.approx(5.0, abs=1.0))]   # load → prime
            assert h.recorder.mic == [True]        # capture opened AFTER prime (single arm)
            assert d.is_listening() and d._seed_active is True
            assert "the quick brown fox" not in repr(out)                # no text in the outcome

        def test_seed_arm_warm_reprime_no_clear_between_prime_and_mic():
            # arm plain first (no seed → no prime call), disarm, then a seed arm on the resident child
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory())
            d.start(); assert d._host.prime_calls == []           # plain, no prior seed: nothing to confirm
            d.stop(); _wait_for(lambda: not d.is_listening(), 2.0)
            out = d.start_with_seed("seed text")
            h = d._host
            assert out.ok and out.context_seeded is True
            assert h.prime_calls[-1][0] == "seed text"            # re-prime on the resident child
            assert h.recorder.mic[-1] is True                      # capture after the prime
            assert h.stop_calls == 0                               # warm: no reload

        def test_plain_arm_after_seed_confirms_clear_before_mic():
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory())
            d.start_with_seed("seed text"); assert d._seed_active is True
            d.stop(); _wait_for(lambda: not d.is_listening(), 2.0)
            d.start()                                             # PLAIN arm — must not inherit
            h = d._host
            assert h.prime_calls[-1][0] is None                   # CONFIRMED clear (prime_prompt(None))
            assert h.recorder.mic[-1] is True                     # then capture
            assert d._seed_active is False and d.is_listening()

        def test_plain_arm_unconfirmable_clear_isolates_host():
            def _script(h): h.prime_results[None] = _PrimeResult("unconfirmed", None, 1, 1, "executor-error")
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            d.start_with_seed("seed text"); d.stop(); _wait_for(lambda: not d.is_listening(), 2.0)
            d.start()                                             # plain arm; clear unconfirmable
            assert d.is_listening() is False                      # NO capture
            assert d._host is None and d._models_loaded is False  # host ISOLATED
            assert d._seed_active is False and d.status_snapshot()["phase"] == "unloaded"
            assert "prompt-unconfirmed" in (d._load_error or "")

        def test_seed_arm_unconfirmed_fails_closed_no_capture():
            def _script(h): h.prime_results["seed text"] = _PrimeResult("unconfirmed", None, 1, 1, "timeout")
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            out = d.start_with_seed("seed text")
            assert out.ok is False and out.context_seeded is None and out.reason == "seed-unconfirmed"
            assert d._host.recorder.mic == []                      # mic NEVER opened
            assert d.is_listening() is False and d._seed_active is False

        def test_seed_arm_timeout_budget_bounded_no_capture():
            def _script(h):
                h.prime_gate = threading.Event()                 # never released within the budget
                h.prime_results["s"] = _PrimeResult("applied", 3, 1, 1, "ok")
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            t0 = _time.monotonic()
            out = d.start_with_seed("s", timeout=0.4)            # a SHORT total deadline (test seam)
            dt = _time.monotonic() - t0
            assert out.ok is False and out.reason == "seed-unconfirmed"
            assert dt < 3.0 and d._host.recorder.mic == []        # bounded; no capture
            d._host.prime_gate.set()                               # release the fake (cleanup)
  - NOTE on the timeout test: the fake's gate ignores the timeout kwarg (it waits on the Event); the
    REAL host honors timeout. To keep this test honest, make the FAKE honor the budget:
    `if self.prime_gate is not None and not self.prime_gate.wait(timeout=timeout): return
    _PrimeResult("unconfirmed", None, 0, 1, "timeout")`. Then the test asserts the unconfirmed outcome
    arrived within ~budget+slack and the mic never opened. (This mirrors S2's contract.)
        def test_stop_during_prime_aborts_commit_no_capture():
            def _script(h): h.prime_gate = threading.Event()
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            t = threading.Thread(target=lambda: d.start_with_seed("s"), daemon=True); t.start()
            _wait_for(lambda: len(d._host.prime_calls) == 1, 2.0)   # prime in flight (gated)
            d._host.prime_gate.set()                               # prime will return applied...
            d.stop()                                               # ...but a stop lands → revalidate aborts
            t.join(3.0)
            assert d.is_listening() is False
            # the abort cleaned up: seed confirmed-cleared (prime(None) → clear) or host isolated
            assert d._seed_active is False and d._host is not None and d._host.recorder.mic == []

        def test_superseded_arm_stale_result_is_harmless():
            # Two seeded arms overlap; the OLDER arm's late prime result must not arm anything.
            def _script(h): h.prime_gate = threading.Event()
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            t1 = threading.Thread(target=lambda: d.start_with_seed("first"), daemon=True); t1.start()
            _wait_for(lambda: len(d._host.prime_calls) == 1, 2.0)
            # the newer reservation (second arm) supersedes the first; release the gate so the FIRST
            # arm's prime returns applied AFTER it is already stale
            d._arm_seq += 1                                        # simulate the newer reservation (or start a 2nd arm)
            d._host.prime_gate.set(); t1.join(3.0)
            assert d.is_listening() is False                       # the stale arm did NOT capture
            assert d._seed_active is False                         # and left no seed behind (cleanup/isolate)

        def test_failed_load_makes_no_prime_call():
            def _script(h): h.spawn_result = False
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            out = d.start_with_seed("s")
            assert out.ok is False and out.reason == "load-failed" and d._host is None

        def test_host_prime_raising_fails_closed():
            def _script(h): h.prime_raise = RuntimeError("boom (fake contract violation)")
            d, _fb = _make_lazy_daemon(host_factory=_primeable_factory(_script))
            out = d.start_with_seed("s")
            assert out.ok is False and out.reason == "seed-unconfirmed" and d._host.recorder.mic == []
            assert "boom" not in repr(out)
  - CONSTRAINTS: reuse `_make_lazy_daemon`, `_wait_for`, `_time`, `threading`, `pytest`; the fake's
    `device` gains `"context_prompt": True` so `_load_host`'s ready-evidence gate sees the capability.
    The stop/superseded tests may need `_cuda_resolve(monkeypatch, …)` only if a code path probes CUDA
    (the lazy daemon seeds the device cache from the host; it does not) — add it if a test touches
    `_resolved_device`.

Task 5: VALIDATE — the Validation Loop below. No git commit unless directed. If asked:
  "P1.M1.T2.S3: fenced start seam — capture gated on confirmed priming (reserve/load/prime/revalidate);
  plain arms never inherit a seed; sanitized ArmOutcome for S4/S5/T3.S4".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — reserve under lock, wait outside, commit under lock (the whole seam):
with self._lock: self._arm_seq += 1; tok = self._arm_seq; self._arming = tok
try:
    if not self._load_host(): return self._abort_start(tok, None, "load-failed")   # outside lock
    result = primer(seed_or_None, timeout=min(_PRIME_BUDGET_S, remaining))         # outside lock
    with self._lock:                                                               # ATOMIC revalidate
        if self._arming != tok or self._shutdown.is_set() or self._listening.is_set() \
           or self._drain or self._loading or self._host is not host or not host.is_alive:
            return self._abort_start(tok, host, "superseded" if self._arming != tok else "aborted")
        # prompt policy (applied → seed_active; clear → not seed_active; legacy clear iff no channel)
        self._arming = None; self._arm(streaming=streaming)
        return ArmOutcome(True, True, ..., ...)
finally:
    with self._lock:
        if self._arming == tok: self._arming = None

# PATTERN 2 — fail closed on UNKNOWN; isolate on an unconfirmable plain-arm clear:
state == "unconfirmed" + want_seed → no capture (seed-unconfirmed)
state == "unconfirmed" + need_clear → _isolate_host(): drop + bounded host.stop(5.0); phase unloaded

# PATTERN 3 — sanitized outcome only: ArmOutcome(ok, listening, reason, context_seeded, tokens, arm_seq)
# — no text field; logs carry state/reason/arm_seq; a raising host is logged by exception TYPE only.
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S2 (parallel; the INPUT): host.prime_prompt(text, *, timeout) -> PrimeResult
           (state/tokens/lanes/generation/reason; never raises; waiter in caller's thread). Consumed
           BY ATTRIBUTE; absent on legacy hosts/fakes → legacy best-effort clear branch.
UPSTREAM — P1.M1.T2.S1 (executor): install(None) on warm → CLEAR proven; cold → UNCONFIRMED — the
           reason an unconfirmable clear must isolate the host rather than assume clear.
DOWNSTREAM — P1.M1.T2.S4 (handoff at first accepted final): reads ArmOutcome.context_seeded to know a
           seed awaits handoff; S4 does NOT re-prime — the seam already installed it.
DOWNSTREAM — P1.M1.T2.S5 (focus-based context starts): calls start_with_seed(seed) and surfaces
           context_seeded/reason (private hint) in its start reply.
DOWNSTREAM — P1.M1.T3.S4 (reserve one native owner; fence startup): the _arm_seq/_arming reservation
           is the generic fence; T3.S4 adds the owner/lease layer ABOVE it (no socket/lease code here).
UNCHANGED: recorder_host.py (S2), prompt_engine.py (S1), the control-socket protocol shape (ok:false
           flows via the existing _load_error/_arm_response path), _disarm/_request_stop/drain logic.
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic fakes only (no CUDA/process/mic/socket). Run from `/home/dustin/projects/voice-typing`. Navigate by symbol — line numbers shift.

### Level 1: The seam is in place (static)

```bash
cd /home/dustin/projects/voice-typing
grep -n 'class ArmOutcome\|_START_DEADLINE_S = 30.0\|_PRIME_BUDGET_S = 5.0\|def _start_fenced\|def start_with_seed\|def _abort_start\|def _isolate_host\|self._arm_seq = 0\|self._seed_active = False' voice_typing/daemon.py | head -12
echo "--- _arm no longer calls the unconditional clear ---"
awk '/    def _arm\(self/,/    def _disarm\(self/' voice_typing/daemon.py | grep -n '_clear_context_prompt()' && echo "L1 FAIL: unconditional clear still in _arm" || echo "L1 PASS: clear moved out of _arm"
echo "--- start/toggle route through the seam ---"
grep -n 'self._start_fenced(None, streaming=streaming)' voice_typing/daemon.py   # expect 2 (start + toggle)
echo "--- ArmOutcome has NO text field ---"
awk '/class ArmOutcome/,/^class [A-Z]/' voice_typing/daemon.py | grep -i 'text' && echo "L1 WARN: check the text mention is a comment only" || echo "L1 PASS: no text field"
timeout 60 .venv/bin/python -c "import ast; ast.parse(open('voice_typing/daemon.py').read()); print('L1 PASS: parses')"
# Expected: all symbols present; _arm has no _clear_context_prompt() call; start+toggle route through the
# seam; ArmOutcome text-free; parses.
```

### Level 2: The fenced-start tests (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k "seed_arm or plain_arm or stop_during_prime or superseded_arm or failed_load_makes_no_prime or prime_raising" -v 2>&1 | tail -14
# Expected: all PASSED. Load-bearing: cold order (prime → mic), plain-after-seed confirmed clear,
# unconfirmable clear isolates (no capture, host None), seed-unconfirmed fails closed, bounded timeout,
# stop/superseded aborts with no capture and no lingering seed, failed load → no prime, raising host →
# fail closed with no text. If 'unconfirmable clear isolates' shows mic opened: the need_clear branch
# isn't gating capture. If plain-after-seed shows prime_calls[-1][0] == "seed text": _seed_active was
# cleared at disarm (CRITICAL #6) or the plain arm re-primed the seed.
```

### Level 3: No regressions (the full daemon suite — legacy branch byte-identical)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -2
timeout 600 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_voicectl.py -q 2>&1 | tail -2
# Expected: all green. Every existing test uses hosts WITHOUT prime_prompt and no prior seed → the
# legacy branch (no prime call; best-effort clear under its gates) → identical behavior. A red here
# means the legacy branch diverged (CRITICAL #8) — diff the seam's no-channel path against the old
# start()/toggle()/ _arm() sequence.
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'voice_typing/daemon.py|tests/test_daemon.py' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS"
git diff --quiet voice_typing/recorder_host.py voice_typing/prompt_engine.py voice_typing/ctl.py voice_typing/config.py config.toml systemd/ && echo "L4 PASS: siblings untouched" || echo "L4 NOTE: recorder_host/prompt_engine diffs are S1/S2's parallel work, not this task's"
git diff --exit-code -- PRD.md plan/009_ef3b49b0fc0d/tasks.json plan/009_ef3b49b0fc0d/prd_snapshot.md .gitignore && echo "L4 PASS: read-only unchanged" || echo "L4 NOTE: orchestrator bookkeeping"
# Expected: diff == the two files; siblings untouched by this task; read-only unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: ArmOutcome + constants + `_arm_seq/_arming/_seed_active` + `_start_fenced/_abort_start/_isolate_host` + `start_with_seed` present; `_arm` has no unconditional clear; start+toggle route through the seam; parses.
- [ ] L2: all fenced-start tests pass (cold/warm ordering, plain-after-seed confirmed clear, isolation on unconfirmable clear, fail-closed seed-unconfirmed, bounded timeout, stop/superseded aborts, failed load, raising host).
- [ ] L3: full daemon suite + control-socket/voicectl suites green (legacy branch byte-identical).
- [ ] L4: diff == the two files; siblings/read-only untouched.

### Feature Validation
- [ ] Mic never opens before the prompt state is KNOWN (applied / confirmed clear) or the host is isolated.
- [ ] Seed arm never clears between prime and capture; plain arm after a seed confirmed-clears (or isolates); plain arm with no seed is unchanged.
- [ ] Atomic revalidation under `_lock`; stop/shutdown/drain/superseded/dead-host abort without capture; stale results harmless.
- [ ] `_arming` cleared on every exit; `_seed_active` persists across disarm; no seed text in outcomes/logs/exceptions.

### Code Quality Validation
- [ ] Lock discipline mirrors the codebase (reserve/commit under `_lock`; load/prime outside).
- [ ] Mode A docstrings on start/toggle/_arm/_load_host (locking + seed-clear guarantees).
- [ ] S2 consumed by attribute; fakes duck-type `PrimeResult`; no new imports beyond stdlib.
- [ ] Full paths + `timeout`; no ruff/mypy; hermetic.

### Scope Boundary Validation
- [ ] No recorder_host.py/prompt_engine.py/ctl/config/systemd edits; no S4 handoff, S5 focus starts, or T3.S4 owner/lease code.
- [ ] `_disarm`/`_request_stop`/drain untouched; control-socket protocol shape unchanged.
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore not modified.

### Documentation & Deployment
- [ ] Mode A: lifecycle docstrings updated; ArmOutcome docstring states the consumer contract.

---

## Anti-Patterns to Avoid

- ❌ Don't hold `self._lock` across `_load_host()` or `prime_prompt()` — `_load_host` re-acquires that lock (deadlock) and every control client wedges (CRITICAL #1).
- ❌ Don't just relocate the unconditional clear — it's a policy now: seed arms never clear; plain-after-seed arms CONFIRMED-clear; no-seed plain arms skip or legacy-clear (CRITICAL #3).
- ❌ Don't treat UNCONFIRMED as "unavailable"/"clear" — seed arm fails closed; plain-arm clear isolates the host (CRITICAL #4).
- ❌ Don't clear `_seed_active` in `_disarm` — the resident child still holds the seed; the NEXT arm must confirmed-clear it (CRITICAL #6).
- ❌ Don't let `_arm()` run before revalidation — it sets `_listening` first (CRITICAL #2).
- ❌ Don't leave `_arming` set on any exit path (CRITICAL #7); don't break the legacy no-channel branch (CRITICAL #8).
- ❌ Don't put seed text in `ArmOutcome`, logs, or exception strings (CRITICAL #9).
- ❌ Don't implement S4's handoff, S5's focus starts, or T3.S4's owner/lease — S3 is the generic fenced arm seam they call.
- ❌ Don't edit recorder_host.py (S2) or prompt_engine.py (S1); don't modify PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**8.5/10** for one-pass implementation success. The hazard and every edit site are read verbatim
(`start` ~2495, `toggle` ~2512, `_load_host` ~1044, `_arm` ~1692 with the unconditional clear at ~1741
and `set_microphone(True)` at ~1749, `_clear_context_prompt` ~1666); the input contract (S2's
`prime_prompt`/`PrimeResult`, waiter-outside-lock, fence) and the executor semantics behind "confirmed
clear" (S1: warm `install(None)` → CLEAR proven, cold → UNCONFIRMED) are pinned from their PRPs; the
design's policy table maps each (seed|plain) × (applied|clear|unconfirmed|no-channel) cell to an action
with a named barrier test; and the legacy no-channel branch is explicitly specified as byte-identical so
the ~500 existing daemon tests stay green without edits. The −1.5 is inherent to a concurrency seam
with more branches than the average subtask: the stop/superseded tests depend on the fake's gate
honoring the timeout kwarg (specified) and on `_wait_for` timing, and S2's exact `PrimeResult`
attribute names are consumed by attribute defensively. The task-4 test code is illustrative
reference — the implementer should treat the POLICY TABLE and the named tests as the contract and
adapt mechanics (e.g. `_make_lazy_daemon` + the fake's `device["context_prompt"]`) to the live file.

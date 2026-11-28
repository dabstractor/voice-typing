# Research — P1.M1.T2.S3: Gate warm and cold capture on current priming

Verified at the live tree (daemon.py ~3530L; tests/test_daemon.py ~5300L). Navigate by symbol.

## 1. The hazard (arch: "Confirmed seed before capture")
`_arm()` (daemon.py ~1692-1760) runs UNDER `self._lock` and, at ~1741, calls `_clear_context_prompt()`
UNCONDITIONALLY (gated only by `cfg.asr.context_prompt and self._context_prompt_active is True`) just
BEFORE `self._host.set_microphone(True)` (~1749). The clear is a fire-and-forget `host.set_prompt("")`
(FIFO: the child drains its cmd queue between utterances). A seed primed by S2's confirmed channel
(`host.prime_prompt(seed) -> PrimeResult`) would be ERASED by that clear if the order is prime →
clear → mic. And capture (`set_microphone(True)`) must never open before the priming state is KNOWN.

## 2. The current start/arm lifecycle (verbatim essentials)
- `start(streaming=None)` ~2495: `if not self._load_host(): return` (OUTSIDE _lock) → `with self._lock:
  self._arm(streaming=streaming)`.
- `toggle(streaming=None)` ~2512: read `_listening` under _lock → if armed `_request_stop()`; else the
  same load-then-arm sequence as start.
- `_load_host()` ~1044-1160: fast path under _lock (`_models_loaded and _host is not None and
  _host.is_alive` → True); single-flight via `_load_cond` (a second caller WAITS and returns
  `_models_loaded`); loader publishes `_host`, `_resolved_device_cache = host.device`,
  `_context_prompt_active = bool(host.device.get("context_prompt", False))` (the READY evidence), phase
  idle. Failure → `host.stop()`, `_host=None`, `_load_error`, phase unloaded, returns False.
- `_arm()` ~1692-1760 (under _lock): `_listening.set()` FIRST, session reset, `_rev1_committed=""`,
  `_clear_context_prompt()`, `_armed_monotonic`, `set_microphone(True)`, feedback, duck, mic probe.
  Note the ordering bug for this feature: listening is set and the mic opened inside the same critical
  section as the clear — no room to wait for a confirmation.
- `_clear_context_prompt()` ~1666-1690: gated put of `set_prompt("")`, never raises, no lock.
- `_refresh_context_prompt()` ~2078: commit-time rolling push (gated on `_context_prompt_active is True`).
- Test seam: `_FakeHost` tests/test_daemon.py ~782 (ctor mirrors real RecorderHost; `device` dict w/o
  `context_prompt` key → `_context_prompt_active=False` for fakes); `_fake_host_factory` ~886;
  `_make_lazy_daemon(cfg, host_factory)` ~3610; `_PromptRecordingHost` ~5028 (`set_prompt` recording);
  `_GatedFakeHost` pattern ~1787 (stop gates via Events); `_wait_for` ~765; `_cuda_resolve` ~69.

## 3. INPUT contract (S2, parallel — assume landed exactly)
`RecorderHost.prime_prompt(text: str|None, *, timeout=_PRIME_TIMEOUT_S=5.0) -> PrimeResult` — frozen,
sanitized: `state ∈ {"applied","clear","unconfirmed"}`, `tokens: int|None`, `lanes: int`, `generation`,
`reason ∈ {"ok","no-lane","partial","timeout","dead","cancelled","executor-error","stale"}`. NO text.
Waiter runs in the CALLER's thread (never reader, never under daemon _lock — S2 CRITICAL #1). Stale ACKs
(token/generation) are dropped. `cancel_prime()` fences. 0 lanes = KNOWN clear (`reason="no-lane"`).
S2 explicitly says: "S3 CALLS host.prime_prompt(seed, timeout=…) from the arm path — OUTSIDE the daemon
_lock, inside the 30 s native start deadline — and gates on state (applied/clear ⇒ proceed;
unconfirmed ⇒ degrade to context-free + private hint)." S1: `install_initial_prompt` UNCONFIRMED
fail-closed; "S3 uses UNCONFIRMED to gate capture / degrade to context-free."

## 4. Design (what S3 builds) — the fenced start seam
### 4.1 Reservation under _lock; wait outside; atomic revalidate before capture
New private `_StartRequest` (seed: str|None, streaming, token) + `_arm_seq` counter (monotonic arm
generation). New `start_with_seed(seed, *, streaming, timeout) -> ArmOutcome` (the helper S5/T3.S4
call; plain `start()`/`toggle()` route through it with `seed=None`):
1. **Reserve** (under _lock): `self._arm_seq += 1; tok = self._arm_seq; self._arming = tok`. (A newer
   reservation supersedes an older one — the older's late commit fails revalidation.)
2. **Load** (outside _lock): `if not self._load_host(): outcome failed("load-failed")` (clears _arming).
3. **Prime** (outside _lock, only if `seed is not None` and `host.prime_prompt` exists): `res =
   host.prime_prompt(seed, timeout=min(_PRIME_BUDGET_S, deadline_remaining))`. Plain arm (seed None):
   NO prime call, and the old clear becomes **conditional**: only when the prompt is KNOWN stale, i.e.
   a seed was active from a previous arm (`self._seed_active`), never unconditionally.
4. **Revalidate atomically** (under _lock) BEFORE any capture: `if self._arm_seq != tok or
   self._shutdown.is_set() or self._listening.is_set() or self._drain or self._loading or host is not
   self._host or not host.is_alive: → abort commit` (fail closed). Then commit the prompt state:
   - seed arm + `res.state == "applied"` → `self._seed_active = True`; SKIP the clear (the seed IS the
     prompt); arm.
   - seed arm + `res.state == "clear"` (incl. no-lane) → prompt KNOWN clear; `self._seed_active=False`;
     SKIP the clear (already clear — a redundant set_prompt("") is harmless but unnecessary); arm.
   - seed arm + `unconfirmed` → fail closed for SEED mode: do NOT open the mic on an unknown prompt with
     a seed requested. Outcome `unconfirmed` (sanitized reason) — S5 surfaces the private hint. The host
     is left idle-resident (safe: prompt is None-or-stale-but-no-seed-was-proven-installed... see 4.3).
   - plain arm (seed None) → if `self._seed_active` (a previous seed session may have left the seed in
     the child): the clear must be CONFIRMED, not fire-and-forget: `res = host.prime_prompt(None,
     timeout=…)` (S1: install(None) on warm → CLEAR proven; cold → unconfirmed) → `clear` ⇒
     `self._seed_active=False`; arm context-free. `unconfirmed` ⇒ the child's prompt state is UNKNOWN
     while the user asked for a PLAIN arm → **isolate the host**: `_bounded_shutdown()` + drop
     (`_host=None, _models_loaded=False`, phase unloaded) so the next arm cold-loads a fresh child
     (prompt None by construction) — "on uncertainty … confirm cleanup or isolate host before reuse."
     If `self._seed_active` is False (normal plain arm, incl. every existing test fake): behavior is
     BYTE-IDENTICAL to today minus nothing — keep the legacy best-effort `_clear_context_prompt()` for
     the rolling-context path? NO: the rolling clear exists so a warm re-arm doesn't condition on the
     previous session's text. That is the `_rev1_committed`-driven rolling prompt — still desired.
     Resolution: keep `_clear_context_prompt()` ONLY when `not self._context_prompt_active` is False and
     NO confirmed channel exists (test fakes without `prime_prompt`) — i.e. confirmed channel present ⇒
     confirmed clear; absent ⇒ legacy best-effort clear (fakes/old hosts). This keeps every existing
     test green while making real hosts confirmed.
5. **Arm** (under _lock): the existing `_arm()` body MINUS the unconditional clear (moved into the
   gated logic above). `_arming = None`.
Deadline: `_START_DEADLINE_S = 30.0` total (the native cap); prime budget `_PRIME_BUDGET_S = 5.0`
(= S2's default) bounded by the remaining deadline; a timed-out prime → unconfirmed → the S2 fence
(token) makes its late ACK harmless ("harmless stale ACK" — the contract's test).

### 4.2 Guards on the revalidate (abort commit, fail closed)
stop/shutdown/listening/drain/arming-superseded/load-failed/dead-host → abort. On abort with a seed
possibly installed: if `res.state=="applied"` but we're aborting → the seed is in the child → confirm
cleanup (`prime_prompt(None)` → clear) or isolate the host (drop) — never leave a seed armed for the
next plain arm. On abort before any prime (load failed) → nothing to clean.

### 4.3 Outcome (sanitized) for S4/S5/T3.S4
`ArmOutcome(ok: bool, listening: bool, reason: str, context_seeded: bool|None, tokens: int|None,
arm_seq: int)` — frozen dataclass, NO text. `context_seeded`: True (applied), False (plain/known
clear), None (unconfirmed/failed). S4 reads `context_seeded` to know a seed awaits handoff at the
first accepted final; S5/T3.S4 return it in their start reply.

### 4.4 Tests (fake host barriers — the contract's explicit ask)
`_FakeHost` gains a `prime_prompt` seam ONLY in a new `_PrimeableFakeHost(_FakeHost)`: records calls,
returns a scripted `PrimeResult`-like object, optionally GATED on an Event (delayed ACK) and/or
scripted to raise (a fake violating S2's never-raise → must still not crash the arm). Asserts:
warm/cold ordering (load → prime → mic True; plain warm arm with seed_active → confirmed clear → mic;
plain arm with no prior seed → no prime call, mic True), timeout cleanup (gated prime → deadline →
outcome unconfirmed, NO set_microphone(True), host isolated/idle per branch), harmless stale ACK (an
aborted/superseded arm's late `prime` result can't flip `_seed_active`/`listening`), stop-during-prime
(abort; no capture), superseded arm (newer token wins), failed load (no prime call), plain arm never
inherits a seed (`_seed_active` False → context-free), `ArmOutcome` has no text in repr.

## 5. Boundaries
- S2 owns recorder_host.py (prime_prompt/cancel_prime/PrimeResult) — do NOT edit; consume by attribute
  (`getattr(res, "state", …)`), tolerate fakes without the method (legacy clear path).
- S1 owns prompt_engine.py. S4 (handoff at first accepted final) and S5 (focus starts) consume
  `ArmOutcome` — do NOT implement handoff or focus-based starts here. T3.S4 reserves the native owner —
  S3's `_arm_seq`/`_arming` reservation is the generic seam it will call; do NOT add socket/lease code.
- `_disarm`/`_request_stop`/drain: UNCHANGED except: `_disarm` should clear `_seed_active` ONLY after a
  confirmed clear or host isolation? NO — keep disarm untouched; `_seed_active` persists across disarm
  (the child stays resident with the seed) and the NEXT arm's logic handles it (confirmed clear on
  plain, re-prime on seed). That is the "Plain arm must not inherit any seed" guarantee's home.
- DOCS Mode A: start/toggle/_arm/_load_host docstrings describe reservation/wait-outside-lock/
  revalidate/seed-clear guarantees.

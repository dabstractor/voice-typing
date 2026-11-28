# Research Note — P1.M1.T2.S2: Acknowledge priming across recorder IPC

All sites verified against HEAD `f677f2e` (recorder_host.py line numbers current). S1's executor API
(`PromptedExecutor.install_initial_prompt` / `PromptState` / `PromptInstallResult`) is NOT yet in the
tree (parallel, "Implementing") — treated as the contract per S1's PRP.

## 1. The IPC seam today (verified verbatim)

- **cmd_q (daemon→child)** @19-23 docstring; `("prompt", {"text": ...})` @20. `set_prompt(text)`
  @349-362: fire-and-forget `self._cmd_q.put(("prompt", {"text": text}))`, never blocks/raises.
- **evt_q (child→daemon)** @29+; `("ready", {...})`, `("error", {msg})`, `("final", …)`, `("partial",…)`,
  `("speech",{})`, `("gone",{})`.
- **Child command loop** @958-1036: `kind, payload = cmd_q.get()` → arms; the `"prompt"` branch
  @1012-1024: `targets = _prompt_targets(prompt_executor)`; `for _exec in targets: _exec.set_prompt(...)`
  (or DEBUG "ignored (context-prompt not armed)" when no targets). **Blocks inside `recorder.text()`**
  during an utterance — commands are read BETWEEN utterances (by design; the comment says so).
- **`_prompt_targets(prompt_executor)` @1102-1111**: "at most the shared context-prompt executor … always
  a 0- or 1-element list; **the confirmed-prompt ACK (P1.M1.T2.S2) extends THIS seam**." Returns
  `[prompt_executor] if prompt_executor is not None else []` (dedupes the retired 2-lane split by
  construction — but the daemon's two lane objects may alias; see §4).
- **Reader** `_read_loop` @502-525: drains evt_q → `_dispatch(kind, payload)`; dispatch errors are
  logged + swallowed (must never kill the reader — it would strand `text()`); on "gone"/EOF sets
  `_dead`, `_final_evt`, `_ready_evt` (the Event-wakeup precedent). **"Child ACK waiting on its
  reader, or the control lock, would wedge both the ACK and unrelated clients"** (arch note) → the
  waiter must live OUTSIDE the reader thread.
- **The cancel-mark precedent** (the pattern to mirror): ctor `self._cancel_mark = False` @226 + comment
  @221-225 ("on_final runs ON the reader thread, so the mark is always observed in the write-then-relay
  order"); `cancel()` @388-408 sets `_cancel_event` THEN `_abort_event`; `consume_cancel_mark()` @409-418
  reads-and-clears. Reader sets the mark from the payload before relaying.

## 2. Design decisions (load-bearing — recorded for the implementer)

1. **New command `("prime", {"token": int, "text": str|None, "generation": int})`** on cmd_q — NOT a
   reuse of `("prompt", …)`: prompt is fire-and-forget rolling; prime is confirmed. Child handler:
   `for _exec in _prompt_targets(prompt_executor): result = _exec.install_initial_prompt(text_or_None)`
   → `evt_q.put(("prime_ack", {"token": …, "generation": …, "state": result.state.value,
   "tokens": result.tokens, "lanes": len(targets)}))`. **NO TEXT in the ACK** (arch: "an ACK carrying
   only opaque token/generation and outcome"; S1: tokens is a count).
2. **Token + generation fencing.** The daemon mints a monotonic `token` per request (itertools.count
   or an int counter under `_lock`) and stamps the host `generation` (a per-host-lifetime int — bump on
   spawn/respawn; "host lifetime plus request/reservation token" from the INPUT). The waiter accepts
   ONLY the ACK whose (token, generation) match its outstanding request; any other `prime_ack` is stale
   (a late ACK from a cancelled/previous request, or from an old child after a respawn) → dropped with a
   DEBUG line (counts only). "Fence stale/late ACKs."
3. **Waiter OUTSIDE the reader thread.** Reader's `_dispatch("prime_ack")` only stores the payload and
   sets `self._prime_evt` (a threading.Event) — mirroring `_cancel_mark`/`_final_evt`. The REQUESTER
   (daemon arm path, S3's caller) waits on `_prime_evt.wait(timeout)` in ITS OWN thread, never under
   the daemon `_lock` (arch: "wait for load and prompt confirmation outside [the lock]"). Deadline +
   cancellation: `wait(timeout)` returns a sanitized `UNCONFIRMED`-class result on timeout; a
   `cancel_prime(token)` (or the next request) supersedes the outstanding token so a late ACK is fenced.
4. **Dedup aliased lane objects, confirm BOTH lanes.** `_prompt_targets` already returns unique objects
   (0/1). The ACK reports `lanes = len(targets)`: **0 lanes ⇒ the child's ready/capability evidence
   proves "context-prompt not armed" ⇒ EMPTY/DISABLED/UNAVAILABLE is KNOWN** (report `CLEAR`-class with
   `lanes=0`, i.e. "known-empty", per the contract: "explicit ready/capability proves
   empty/disabled/unavailable only when clear is known"). 1 lane ⇒ its `PromptState` is the result.
   Dedup by `id()` when iterating so an aliased pair (same object in both kwargs) is installed ONCE but
   counted as confirmed for both (S1's CRITICAL #1: APPLIED is honest only against the decode object).
5. **Sanitized result type** (for S3): frozen dataclass `PrimeResult(state: str  # applied|clear|
   unconfirmed, tokens: int|None, lanes: int, generation: int, reason: str  # sanitized enum-like
   code, e.g. "timeout"|"stale"|"dead"|"no-lane"|"ok")`. NO text anywhere; `__repr__` safe by default.
   The daemon-side API: `host.prime_prompt(text: str|None, *, timeout: float) -> PrimeResult` (puts the
   command, waits OUTSIDE the lock, fences, returns sanitized) — deadline + cancellation via timeout
   + `cancel_prime()`.
6. **`set_prompt()` STAYS** byte-identical for ordinary rolling updates (contract OUTPUT).

## 3. Why "between utterances" timing works for priming

`_arm` runs while DISARMED (the child is idle, NOT inside `text()`), so cmd_q is drained immediately —
the prime is read + ACKed within ms of the request. The daemon must STILL bound the wait (arch: 30 s
native start cap is S3's total deadline; S2's per-request timeout default e.g. 5 s) because a cold
model (install → UNCONFIRMED fast) or a dead child (reader EOF → `_dead`) must not hang the arm.

## 4. Test seam (verified from tests/test_recorder_host.py)

`_make_host(...)` @59 (stubbed worker/queues — `_FakeFeedback` @31, `_FakeLatency` @45); `_dispatch`
tests call `host._dispatch(kind, payload)` DIRECTLY (no thread) @82-160 — the exact pattern for the
`prime_ack` dispatch; `test_text_blocks_until_final_event_then_returns` @164 drives `_final_evt`
from another thread — the pattern for the waiter test (gate the fake executor's install on an Event
to simulate a delayed ACK; assert the waiter returns UNCONFIRMED on timeout; then release → a fresh
request confirms). Fake queue = `queue.Queue` (the file already uses stand-ins); fake executor = an
object with `install_initial_prompt` returning a stub `PromptInstallResult`-shaped namedtuple (S1's
real type may not be importable yet — duck-type by attribute: `.state.value`, `.tokens`).

## 5. Sibling boundaries

- S1 (executor primitive): untouched here; consumed by attribute. S3 (gate warm/cold capture on the
  priming result) is the CALLER of `prime_prompt` — S2 exposes the API + sanitized result only.
- S4 (seed handoff at first accepted final) and S5 (focus-based starts) are downstream of S3.
- daemon.py: NOT edited (S3 wires `_arm` to call `prime_prompt`); the daemon's rolling `set_prompt`
  caller @1614/2116 is unchanged.

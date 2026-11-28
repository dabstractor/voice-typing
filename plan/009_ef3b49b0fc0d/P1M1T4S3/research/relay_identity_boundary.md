# Research — P1.M1.T4.S3: recorder identity safe at capture boundaries

Checked at HEAD `a865228` (+ staged T4.S1/T4.S2 work). All line numbers are `voice_typing/recorder_host.py`
unless noted. Research was direct (sed/grep + sliced reads); no subagents.

## 1. Ground truth (verified, not inferred)

| Fact | Where |
|---|---|
| Identity contract: every final/partial payload carries ADDITIVE `utterance_id` + `session_gen`; id-less payloads "dispatch byte-identically (the legacy path)" | module docstring :73-88 |
| `_RelayIdentity(session_gen, utterance_id)` NamedTuple; "Either field is None when the payload was id-less" | :1229-1240 |
| `_RelayIds` (child-side, lock-protected): `rotate_utterance()` ONLY at on_speech; `new_session()` at every 'arm'; `stamp()` | :1242-1272 |
| `_with_identity(payload, ids)` — `ids=None` stamps nothing (legacy/test sites) | :1275-1281 |
| Reader-thread-only tracker state, initialized ONLY in `__init__`: `_ids_latest_session=-1`, `_ids_settled` (deque maxlen 16) + mirror set, `_ids_open`, `_relay_identity` | :308-315 |
| `relay_identity` property — "valid INSIDE the on_final/on_partial callbacks (reader thread)" | :344-352 |
| `_dispatch` final branch: stale-gen drop → `_final_evt.set()` + return; duplicate drop → set + return; session advance clears settled; `_ids_settle(uid)` BEFORE relay; `_ids_open=None`; **`_relay_identity` assigned only when `uid is not None`**; `_cancel_mark` then `on_final` then `_final_evt.set()` | :710-745 |
| `_dispatch` partial branch: same three rules; `_ids_open=uid`; `_relay_identity` assigned only when identified; `_on_partial(text)` | :748-771 |
| `speech` branch: bare `self._on_speech()` — payload is `{}` by contract ("only the six final/partial sites carry identity keys") | :773, child :928-935 |
| `spawn()` bumps `self._generation += 1` ("a NEW child lifetime") BEFORE starting the reader; same instance is reused | :383-395 |
| `set_microphone(on)` = best-effort `cmd_q.put(("arm"|"disarm", {}))` | :420-425 |
| `_read_loop` re-reads `self._evt_q` every iteration; `finally` sets `_dead`/`_final_evt`/`_ready_evt`/`_prime_evt` | :652-675 |
| Daemon has ZERO consumers of `relay_identity` / `_RelayIdentity` / `_generation` today | `grep` over daemon.py → empty |
| Daemon arm choke point: `self._host.set_microphone(True)` only in `_arm` (:1872); `_start_fenced` calls `self._arm(...)` (:2817) | daemon.py |
| Daemon run loop: `_utterance_finalized=False; _text_in_flight.set(); host.text(on_final)` | daemon.py :1355-1361 |
| `_touch_speech` sets `_final_pending=True` on the `speech` event (BEFORE any partial) | daemon.py :1943-1981 |
| Existing fake harness: `_make_host(...)`, `_feed_event(host, kind, payload)`; identity tests :878-1033 call `host._dispatch` directly (2 args) | tests/test_recorder_host.py :61-82 |
| Existing test asserts `host.relay_identity == (2, 7)` (2-tuple equality) and `("he", (2, 7))` inside callbacks | tests/test_recorder_host.py :878-905 |

## 2. Defects this task must close

**D1 — stale identity on id-less events.** `_relay_identity` is assigned conditionally, so after an
identified event, a legacy id-less event leaves the PREVIOUS event's `(gen, uid)` latched. A native
consumer reading `relay_identity` inside `on_final` for the legacy event would attribute it to the
previous utterance. Fix: assign `_RelayIdentity(None, None)` on every id-less path.

**D2 — cold host inherits the previous child's tracker.** `spawn()` reuses the instance; the new child
starts at `session=0` (`_RelayIds()` at :924) so its first arm yields `session_gen=1`. If the previous
child reached gen 5, `_ids_latest_session=5` → **every event of the new child is dropped as "late
cross-session"** (`gen < latest`), and colliding uids are dropped as duplicates. The daemon builds a
fresh host per `_load_host` today, but `spawn()` is public and documents re-spawn. Fix: reset the
tracker on the reader thread at `"ready"` (the first event of every child lifetime; G6-safe — never
from the spawner thread).

**D3 — previous host's events can contaminate the new host.** The OLD reader thread can still drain
stragglers after the next `spawn()` (it re-reads `self._evt_q`, and its `finally` runs late). A
straggler with a higher `session_gen` than the new child's would ADVANCE `_ids_latest_session` and
then starve the new child (same symptom as D2). Fix: each reader captures `generation` at entry and
passes it to `_dispatch`; an event whose generation ≠ the host's current generation is dropped
(counts-only DEBUG) without touching the tracker or `_final_evt`.

**D4 — the boundary opens late.** The utterance id rotates at `on_speech` (decode source) but the
`speech` payload is unstamped, so the reader only learns the open utterance at the FIRST partial — up
to one `realtime_processing_pause` (~150 ms) later. A Stop landing in that window (daemon
`_final_pending` already True) sees `_ids_open is None` → T4.S5 would treat the in-flight utterance as
"nothing eligible" and lose its final. Fix: stamp the speech payload with the rotated id
(`_with_identity` precedent; `ids=None` → `{}` unchanged) and open the boundary at `speech`.

**D5 — arm generation is implicit.** `session_gen` is only learned from events; a final from the
PREVIOUS arm (same host) that arrives after a re-arm but before any new-session event is relayed as a
normal final with the old gen, indistinguishable from the current arm. Fix: explicit `arm_seq` bumped
in `set_microphone(True)` BEFORE the cmd put (happens-before the child's arm → its first stamped
event), latched per session by the reader when the session advances.

## 3. Design (host-side only; daemon.py untouched)

- Keep `_RelayIdentity` 2-field (existing tuple-equality tests hold). ADD:
  `FinalClass` enum (ACCEPTED|SENTINEL|CANCELLED|UNIDENTIFIED|DUPLICATE|STALE),
  `_RelayEvent(kind, final_class, host_generation, arm_seq, session_gen, utterance_id)`,
  `_CaptureBoundary(host_generation, arm_seq, session_gen, utterance_id|None)`.
- Properties: `generation`, `arm_seq`, `relay_event` (`_RelayEvent|None`, valid INSIDE callbacks),
  `capture_boundary` (`_CaptureBoundary|None`; whole/never torn; ≤1 event superseded when read
  off the reader thread — same discipline as `relay_identity`).
- Final class precedence: `cancelled` → CANCELLED; `text==""` → SENTINEL; `uid is None` →
  UNIDENTIFIED; else ACCEPTED. Dropped: STALE / DUPLICATE (never reach `on_final`; recorded on
  `relay_event` so the unblock is attributable).
- Boundary: opens at identified `speech`/`partial`; closes (`utterance_id=None`) at EVERY final
  path incl. sentinel/cancel/filtered; legacy id-less events never move it; reset at `ready`.
- `text()` unblocking preserved: `_final_evt.set()` on every final path, still AFTER `on_final`.
- Reader adds NO lock, NO wait: the only lock remains the child-side `_RelayIds` lock.

## 4. Consumer contract handed to T4.S4 / T4.S5

- T4.S4 (inside `on_final`, reader thread): `ev = host.relay_event`; eligible iff
  `ev.kind=="final" and ev.final_class is FinalClass.ACCEPTED and ev.arm_seq > 0 and
  (ev.host_generation, ev.arm_seq) == fence` where `fence` is the native session's arm fence.
- T4.S5 (at Stop, control thread): `b = host.capture_boundary`; nothing eligible iff
  `b is None or b.utterance_id is None or b.arm_seq == 0`. During drain accept iff ACCEPTED and
  `(ev.host_generation, ev.arm_seq, ev.session_gen, ev.utterance_id) == b`.

## 5. Adjacent hazards NOT in scope (record, do not fix)

- Old reader's `finally` sets `_dead=True` on the shared instance after a respawn (:668-675).
- `_ids_settled` bounded to 16 — long sessions with >16 finals per arm rely on session advance to
  clear; unchanged.
- `tests/test_recorder_host.py` loads real CUDA models in places (AGENTS.md) → `timeout 600`.

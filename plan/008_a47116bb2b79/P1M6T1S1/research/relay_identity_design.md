# Relay identity design — P1.M6.T1.S1

Backing research for the PRP. Sources: `architecture/d2_bulk_delivery_map.md §1` (the exact recipe,
all file:line cites verified against live code), live `voice_typing/recorder_host.py` (1141 lines),
`tests/test_recorder_host.py` (775 lines), PRD §4.2sexies R.5, and P1.M5.T3.S1's PRP (parallel
contract; adds-only house rule).

## §1 — The six sites + the choke point (verified live)

| Site | Code (live) | Today's payload |
|---|---|---|
| REAL final | `_child_on_final` :643 → put :644 | `{"text": text}` |
| stale-cancel sentinel | cmd loop :742 | `{"text": "", "cancelled": True}` |
| stale-abort sentinel | cmd loop :745 | `{"text": ""}` |
| abort/cancel sentinels | `_run_text_and_emit_final` :1052/:1054 | `{"text": ""[, "cancelled": True]}` |
| partial | `_RelayFeedback.update_partial` :1100 | `{"text": text}` |
| daemon consume | `_dispatch` :426-479 (final :437-451, partial :452-454) | reads `text`, `cancelled` additively |

Precedents for additive keys: `cancelled` (P1.M2.T7.S1, consumed at :439-441 via
`self._cancel_mark`), `ready`'s `context_prompt` (:864-873). Child per-utterance lifecycle:
`aborted`/`cancelled`/`text_running` events defined :631-643, cleared at top of each text cmd
(:735-737). `arm` branch: `elif kind == "arm": _handle_arm(...)` :756 (`_handle_arm` def :873).
`_child_on_speech` def :571 (puts `("speech", {})` :572 — fires on VAD speech detection, per
utterance). `RecorderHost.text()` :310-338 and the daemon run loop: NO change (payload dict flows
through whole).

## §2 — Design decisions

**D1 — ONE helper.** `_with_identity(payload, ids) -> dict` stamps `utterance_id` + `session_gen`
(additive, never renames/removes existing keys). All six sites call it. Child state = `_RelayIds`
(`threading.Lock`, `utterance:int`, `session:int`) with `stamp(payload)`, `rotate_utterance()`,
`new_session()`.

**D2 — utterance rotation fires at `_child_on_speech`** (the decode source's new-utterance
boundary), NOT at the text-cmd top. Rationale (the "never relabeled" requirement): with text-cmd
rotation, a late realtime partial landing after final-N but before text-cmd-N+1 processes gets the
NEW id → the daemon can't tell it's late → stale text reaches the tail (the exact bug R.5 kills).
With speech-start rotation the holder still holds N until utterance N+1's speech begins, so the late
partial keeps id N → discarded as post-final. on_speech precedes each utterance's partials (VAD
speech-detect → realtime decode); it is already wired today (:571-572). Belt-and-braces: sentinels
settle the CURRENT id (no rotation) so a cancel/stop cycle never advances the id either.

**D3 — session_gen bumps in the `arm` cmd branch** (`ids.new_session()` just before `_handle_arm`)
— R.5 "new session generation at every arm". `_handle_arm`'s signature stays untouched.

**D4 — capture-at-entry.** `stamp()` reads under the ids lock at callback entry (realtime thread
races the cmd-loop thread). Sentinels stamp with the current (in-flight) id at emission time.

**D5 — daemon-side discard at `_dispatch`** (the single choke point). Tracker on RecorderHost
(reader-thread-only mutation): `_latest_session`, `_settled_ids` (bounded, last ~16, cleared on
session advance), `_open_id`, + `relay_identity` (last relayed event's (session_gen, utterance_id) —
the P1.M6.T2.S1 consumption seam; the daemon's callbacks run ON the reader thread so reading it
inside on_final/on_partial is race-free). Rules:
- final-kind: session_gen < latest → drop. id in settled → DUPLICATE → do NOT call `_on_final`,
  but STILL `_final_evt.set()` (host.text() unblock invariant, VT-007). Else: settle id, relay
  (existing `_cancel_mark` flow FIRST — unchanged), set `_final_evt`.
- partial: session check same. id in settled → LATE post-final → drop. Else set `_open_id`, relay.
- No-id payloads (`utterance_id` absent): EXACT today's behavior, no tracking — keeps every
  existing double/test green and covers the 4-arg `_run_text_and_emit_final` call sites.
- "A dropped or filtered final still closes its boundary": settling happens at RELAY time in
  `_dispatch`, before/without caring what the daemon's on_final does downstream (clean() rejection,
  cancel suppression) — holds by construction.

**D6 — stream-edit unchanged on the happy path.** With ids present the only delta is suppressing
pathological events (late/duplicate/cross-session) that today leak stale text into the tail. All
normal flows (partials, finals, sentinels, cancel mark consumption, VAD stale-drop) are bit-identical.
Gate = existing suite green (the doubles drive _dispatch with id-less payloads → legacy path).

## §3 — Test surface (existing doubles)

`tests/test_recorder_host.py` already drives `host._dispatch("final", {...})` directly with
`_FakeFeedback`/`_FakeLatency`-style stubs (tests at :82-150) and `_AbortFakeRecorder` /
`_NormalFakeRecorder` (:393/:409) for the sentinel paths via `_run_text_and_emit_final`. New tests
follow the same two layers + a `_RelayIds` unit layer + one real-child round-trip (the spawn/stop
tests at :306+ show the stubbed `_worker_main` pattern).

## §4 — Scope boundaries

IN: recorder_host.py (helper + ids + six sites + _dispatch discard/tracker + docstring),
tests/test_recorder_host.py additions. OUT: daemon.py (T2.S1 owns dispatch wiring + cancel
intercept; the callbacks' signatures unchanged here), bulk_delivery.py (landed), streaming.py /
typing_backends.py (untouchable per map §3), config (no new keys). P1.M5.T3.S1 (parallel) lands
clipboard_target.py — no overlap; both feed T2.S1.

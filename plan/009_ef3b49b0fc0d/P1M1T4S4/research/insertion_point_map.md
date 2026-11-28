# Insertion-point map — P1.M1.T4.S4 (verified by direct reads at HEAD `cc203ce`)

Line numbers are `voice_typing/daemon.py` at `cc203ce` (T4.S3 landed; `daemon.py` untouched by it).
Companion note: `native_contracts.md` (contract extraction). Everything below was read from source.

## 1. `on_final` (:1463-1735) — branch order

| Lines | What | Thread / lock | Native verdict |
|---|---|---|---|
| :1476-1479 | listening gate (`_listening.is_set()`), OUTSIDE the lock | reader / none | KEEP (drops post-disarm stragglers) |
| :1483 | `with self._on_final_lock:` — serialize clean→type→record→log | reader / `_on_final_lock` | KEEP |
| :1486-1584 | cancel-suppression window (`_cancel_suppress_final`, `consume_cancel_mark`, self-heal) | reader / `_on_final_lock` | BYPASS (generic Rev-2 Backspace-cancel machinery; `cancel()` is refused for native at :2342) |
| :1587 | `cleaned = textproc.clean(text, self._cfg.filter)` | reader | REUSE (native must clean/filter too) |
| :1588-1637 | reject branch: `note_rejected` :1591, stream freeze :1597-1608, `_final_pending=False` :1621, `_utterance_finalized=True` :1624, warning + `feedback.notify` :1630-1635, `return` :1637 | reader | MIRROR only the two lifecycle stores |
| :1638-1641 | `_final_pending = False`; `_utterance_finalized = True` | reader | KEEP (run()/drain lifecycle) |
| :1642 | `self._handoff_context_prompt(cleaned)` — T2.S4 ACCEPTANCE POINT | reader / `_on_final_lock` | REUSE (seed consumed exactly once) |
| :1643-1729 | GENERIC OUTPUT: stream commit :1653 / `_backend.type_text` :1662; `_rev1_committed` :1677; `_feedback.record_final` :1682; `_session_recovery.note_final` :1685; `_latency.finalize_utterance` :1689; `logger.info` latency line :1695; debug :1709; `_stream.reset_boundary` :1721; `_refresh_context_prompt()` :~1723-1730 | reader | BYPASS except the rolling-context refresh |
| :1736-1775 | `_duck_engage` / `_duck_release` (separate methods, not in on_final) | control | KEEP (media lifecycle) |

**Insertion point: first statement inside `with self._on_final_lock:` (:1484).**

## 2. Reader-thread siblings

- `_touch_speech` (:1943-1981): `self._stream.resume()` :1978 (GENERIC engine — skip for native);
  `_last_speech_monotonic = time.monotonic()` :1979 (idle auto-stop clock — KEEP);
  `_final_pending = True` unless `_utterance_finalized` :1980-1981 (KEEP).
- `_on_partial` (:1983-2005): gate :1989-1993 (KEEP); `self._stream.on_partial(text)` :1994 (BYPASS —
  types + mirrors transcript into state.json); `_session_recovery.note_tail` :1999 (BYPASS);
  `_latency.note_partial` :2000 (BYPASS). Native = gate then return.
- `note_user_keypress` (:2083-2141, the evdev guard seam): gate :2096; HALT branch :2098+; Backspace-cancel
  after. Native = return right after the gate (the editor adapter owns invalidation via `lost`/`cancel`).
- Listener thread is started ONCE in `run()` at :1308 (`_start_key_listener`, def :2142).

## 3. Arm / disarm

- `_start_fenced` (:2691): native commit under `self._lock` at :2799-2806 (`self._native.commit(native_tok)`,
  Start-cap timer retired), then `self._arm(streaming=streaming)` at **:2816 — still inside the `with self._lock:`
  block opened at :2775**.
- `_arm` (:1802-1880): `_listening.set()` :1823 (KEEP); stream `set_streaming` :1830-1832 (skip for native);
  `_session_recovery.open_session()` :1834 (skip for native — no generic recovery session);
  stream `reset_session` :1845 (skip for native); `_rev1_committed = ""` :1855, `_session_accepted = []`
  :1860 (KEEP — the accepted-only accumulator native reuses); `_last_speech_monotonic` :1865 (KEEP);
  `self._host.set_microphone(True)` :1872 (KEEP — opens capture; bumps the HOST `arm_seq` before the cmd put);
  `feedback.set_mode` :1873, `set_listening(True)` :1876 (KEEP — lifecycle); `_duck_engage()` :1877 (KEEP).
- `_disarm` (:1882-1941): `_listening.clear()` :1900; `close_session()` :1913 (generic recovery — a no-op when
  no session was opened); `set_microphone(False)` :1930; `set_listening(False)` :1931; `_duck_release()` :1932;
  native end at :1939-1940 (`_end_native_locked(self._native.end_reason, None)`).
- `run()` (:1256-1364): only `_utterance_finalized = False` :1355 and `self._host.text(self.on_final)` :1358 —
  no generic output in the loop itself.

## 4. Native seams that already exist (T3.S4)

`_native_owner_live_locked` :2883 · `_native_blockers_locked` :2888 · `_native_start_expired` :2927 ·
`_native_can_commit_locked` :2958 · `_end_native_locked(reason, cause, …)` :2972 ·
`terminate_native(reason, *, cause=None, …)` :3011 · `_native_drain_or_stop` :3031 ·
`_native_start_worker` :3046. Native checks today: :1422 (dead host), :1939 (disarm), :2342 (cancel refused),
:2724 (generic start → busy), :2910 (blockers), :3040 (drain-or-stop). **Not fenced:** on_final, `_on_partial`,
`_touch_speech`, `_arm` generic setup, `note_user_keypress`.

State block :1006-1019: `_native`, `_native_seq` (owner tokens), `_native_ids`, `_native_timer`,
`_native_worker`, `_native_clock`, `_native_timers`, `_native_end_cb` (T4.S6/T4.S7).
The daemon owns NO `NativeRecovery` / `OfferQueue` yet (grep-verified).

## 5. Rolling context (T2.S4 seam)

- `_handoff_context_prompt(accepted)` :2208-2258 — runs under `_on_final_lock` (NOT `_lock`, :2233);
  `self._session_accepted.append(accepted)` :2237 happens for EVERY accepted final; the seed handoff
  (`_seed_handoff_pending → _seed_handoff_done`, one `host.set_prompt(...)`) only on the first.
- `_refresh_context_prompt()` :2260-2314 — source selection at :2297-2302: `_seed_handoff_done` → the
  accepted accumulator; elif streaming → `self._stream.committed`; else `self._rev1_committed`.
  GAP for native: an UNSEEDED native session never sets `_seed_handoff_done`, so its source would be the
  generic engine's `committed` — which a native session never feeds. Fix = a native-source branch first.

## 6. Test harness (`tests/test_daemon.py`, CPU-only, hermetic post-T1)

`_FakeBackend` :739 · `_FakeHost` :783 (no T4.S3 identity surface — needs a subclass) ·
`_make_daemon(*, recorder, recorder_host, host_factory, backend, cfg) -> (d, fb, rec, be)` :904-921 (uses
`hermetic_cfg`, `_DaemonFakeFeedback`, `_StubRecorder`, `_ok_probe`) · `_make_daemon_with_feedback` :2174.
No existing tripwire helper (grep-verified) — this task defines its own.

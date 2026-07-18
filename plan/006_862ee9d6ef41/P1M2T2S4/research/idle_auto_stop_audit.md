# Research Note — P1.M2.T2.S4: Idle Auto-Stop Watchdog Audit (PRD §4.5 `auto_stop_idle_seconds`)

> **Scope reminder (DISJOINT from §1/§2/§3).** This audit owns the **idle AUTO-STOP watchdog**
> (`_idle_watchdog` → `_maybe_auto_stop` → `_disarm`): disarms the MIC after `auto_stop_idle_seconds`
> (default 30s) of no recognized speech WHILE LISTENING. It does NOT tear down models.
> - §1 (S1) = lazy-load STATE machine (unloaded/loading/loaded + single-flight).
> - §2 (S2) = recorder-host IPC MECHANISM (queues/commands/events/relay/abort/setsid/killpg).
> - **§3 (S3) = idle-UNLOAD watchdog + bounded teardown** (`_idle_unload_watchdog` → `_maybe_idle_unload` →
>   `_unload_recorder` → `_unload_host` → `_bounded_shutdown` → `host.stop`): tears DOWN models to free
>   VRAM after `auto_unload_idle_seconds` (default 1800s) DISARMED. THIS is what §4 HANDS OFF TO.
> - **§4 (S4, this) = idle-AUTO-STOP watchdog**: disarms the mic after 30s of silence while listening,
>   then STARTS the idle-unload clock (via `_disarm` stamping `_disarmed_monotonic`).

## §0 — The two watchdogs (do not confuse)

| | idle AUTO-STOP (§4, this audit) | idle UNLOAD (§3, S3) |
|---|---|---|
| PRD clause | §4.5 `auto_stop_idle_seconds` (30.0) | §4.2bis Idle-unload `auto_unload_idle_seconds` (1800.0) |
| Fires when | LISTENING, no partial for 30s | DISARMED, no re-arm for 30min |
| Action | `_disarm()` (mic off; models stay) | `_unload_host()` (models torn down; VRAM freed) |
| Thread | `_idle_watchdog` | `_idle_unload_watchdog` |
| Method | `_maybe_auto_stop` | `_maybe_idle_unload` |
| Composition | auto-stop's `_disarm` stamps `_disarmed_monotonic` → starts unload clock for FREE | unload reads `_disarmed_monotonic` |

## §1 — Audited code regions (file:line, verified live)

`voice_typing/daemon.py`:
- **L621** `self._last_speech_monotonic: float | None = None` — the idle auto-stop clock (boot = None = not listening).
  Comment L616-620 documents: set on `_arm`, cleared on `_disarm`, refreshed by the partial callback (`on_speech`).
  Comment L622 notes the atomic-CPython-float-store rationale (written by reader/control threads, read by watchdog).
- **L631-632** `self._disarmed_monotonic: float | None = None` — the idle-UNLOAD clock (§3). Set by `_disarm`,
  cleared by `_arm`. THE HAND-OFF POINT: auto-stop's `_disarm` stamps this, starting the 30min unload clock.
- **L994** `_arm`: `self._last_speech_monotonic = time.monotonic()` (start the auto-stop clock fresh) +
  `self._disarmed_monotonic = None` (armed → unload clock inactive).
- **L1020-1021** `_disarm`: `self._last_speech_monotonic = None` (not listening → auto-stop clock inactive) +
  `self._disarmed_monotonic = time.monotonic()` (start the unload clock → §3 reads this).
- **L1029-1039** `_touch_speech`: `self._last_speech_monotonic = time.monotonic()` + `self._final_pending = True`.
  Comment L1032-1036: "Wired into the host's 'speech' event (the child's realtime partial callback fires
  on_speech → ('speech', {}) → the host reader thread calls this)." Partials reset the clock.
- **L1119-1147** `_maybe_auto_stop` — THE CORE METHOD. See §2 for the property-by-property verdict.
- **L1148-1156** `_idle_watchdog` — the background thread. `while not self._shutdown.wait(1.0):` ticks ~1s
  AND exits promptly on shutdown; `try/except Exception` L1154-1155 swallows so a transient error never kills it.
- **L1160-1168** `_idle_unload_watchdog` — the §3 sibling (NOT this audit; mirrors the structure).
- **L751 / L757** `_load_host` wires `self._touch_speech` as the 5th positional arg (`on_speech`) to the
  RecorderHost factory (real + fake), so partials → `_touch_speech`.
- **L219 / L237-238** `_build_callbacks`: the partial callback `_partial(text)` calls `on_speech()` after
  `feedback.update_partial` + `latency.note_partial` → idle auto-stop: recognized words reset the clock.
- **L1335-1362** `_safe_abort`: abort() gated on `_text_in_flight`. After 30s of silence the loop is idle
  (time.sleep(0.05)), so `_text_in_flight` is clear → abort() SKIPPED (correct — nothing to wake).

`voice_typing/config.py`:
- **L65** `auto_stop_idle_seconds: float = 30.0` (the default; PRD §4.5 match).
- **L76** the strict-loader would reject a string like `"thirty"` (validation guard — not a defect here).
- **L89** `auto_stop_idle_seconds` is in the validated-keys list.

## §2 — ★ THE 6-PROPERTY VERDICT (all COMPLIANT, file:line)

| # | item property (LOGIC a-f) | PRD §4.5 expected | code actual (daemon.py) | verdict |
|---|---|---|---|---|
| (a) | `_idle_watchdog` ticks ~1s | "~1s tick" | `_idle_watchdog` **L1148-1156**: `while not self._shutdown.wait(1.0):` (**L1152**) → sleeps ~1s PER tick AND returns the instant `_shutdown` is set (no `time.sleep`). | ✅ COMPLIANT |
| (b) | checks deadline under listen lock so late partial cancels stop | "re-checks the deadline under the listen lock so a late partial cancels the stop" | `_maybe_auto_stop` **L1129** `with self._lock:` → re-reads `self._last_speech_monotonic` under the lock at **L1131** (`is None` guard) + **L1133** (`time.monotonic() - self._last_speech_monotonic < threshold` → return, no disarm). A partial arriving between the 1s tick and lock-acq updates `_last_speech_monotonic` (atomic float store via `_touch_speech`@1039); the lock-gated re-read sees the fresh value → stop cancelled. | ✅ COMPLIANT |
| (c) | `_maybe_auto_stop` disarms (NOT drain — immediate) | "auto-disarms immediately (no drain — by definition no utterance is in flight after this long silent)" | **L1139** `self._disarm()` (immediate). Comment **L1142-1145**: "Auto-stop fires only after auto_stop_idle_seconds of NO speech, so the last utterance finalized long ago — nothing to drain, an immediate disarm+abort is correct." (`_drain`/`_final_pending` never set — contrast with `_request_stop`'s graceful-drain path.) | ✅ COMPLIANT |
| (d) | writes journal INFO line | "writes a journal INFO line (`voice-typing auto-stop: 30.0s of no recognized speech; disarming`)" | **L1134-1137** `logger.info("voice-typing auto-stop: %.1fs of no recognized speech; disarming (set [asr] auto_stop_idle_seconds=0 to disable)", threshold)` — emitted UNDER `_lock` (before `_disarm`), so the line precedes the disarm's state changes. `%.1f` formats the configured threshold (30.0). | ✅ COMPLIANT |
| (e) | starts idle-unload clock (hands off to `_idle_unload_watchdog`) | "Auto-stop disarms the mic but does NOT unload models by itself — it starts the slower idle-unload clock" | `_disarm()` **L1021** `self._disarmed_monotonic = time.monotonic()` — stamps the clock that `_idle_unload_watchdog`/`_maybe_idle_unload` reads (§3). So 30s auto-stop → 30min idle-unload composes for FREE. Comment L622-625 documents the hand-off. | ✅ COMPLIANT |
| (f) | 0 disables (watchdog skips) | "`0` disables" | `_maybe_auto_stop` **L1127-1128** `threshold = self._cfg.asr.auto_stop_idle_seconds; if threshold <= 0: return` — short-circuits BEFORE acquiring `_lock`, so the watchdog's 1s tick is a cheap no-op when disabled. (test_auto_stop_disabled_when_threshold_zero covers it.) | ✅ COMPLIANT |

**Plus the partial-reset hook (PRD: "Partials reset the clock"):** `_touch_speech`@1039 (writes `_last_speech_monotonic`)
← `on_speech` param ← `_build_callbacks._partial`@237-238 (`on_speech()` after update_partial) ← `_load_host`@751/757
(`self._touch_speech` as 5th positional arg) ← child's `('speech', {})` event ← RealtimeSTT realtime partial callback.
✅ COMPLIANT — partials reset the clock (test_touch_speech_resets_the_idle_clock).

## §3 — TEST EVIDENCE (the contract's run target, re-ran live)

```bash
$ timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or auto_stop or watchdog'
...........................                                              [100%]
27 passed, 166 deselected in 1.07s
```

Key evidence tests (tests/test_daemon.py L761-826):
- `test_auto_stop_disarms_when_idle_beyond_threshold` (L767): 31s silent (> 30.0) → `is_listening()` False. **(c)**
- `test_auto_stop_keeps_alive_with_recent_speech` (L776): 5s silent → stays armed. **(b)/(partial)**
- `test_touch_speech_resets_the_idle_clock` (L784): 60s idle, `_touch_speech()` → stays armed. **(partial reset)**
- `test_auto_stop_disabled_when_threshold_zero` (L793): threshold 0, 9999s idle → stays armed. **(f)**
- `test_auto_stop_noop_when_not_listening` (L803): boot (not listening, clock None) → clean no-op. **(b) guard**
- `test_disarm_clears_the_idle_clock` (L810): `_disarm` clears `_last_speech_monotonic` → stale tick is no-op. **(b)/(e)**
- `test_idle_watchdog_actually_disarms_in_background` (L818): REAL thread, 1.0s threshold, disarms within 4s. **(a)+(c)**

## §4 — Non-defect nuances (recorded so they aren't mistaken for gaps)

1. **Two watchdogs, two clocks.** `_idle_watchdog` (auto-stop, fires while LISTENING) and `_idle_unload_watchdog`
   (idle-unload, fires while DISARMED) are SEPARATE threads with SEPARATE clocks (`_last_speech_monotonic` vs
   `_disarmed_monotonic`). §3 owns the unload watchdog; §4 owns the auto-stop watchdog. They COMPOSE (auto-stop's
   `_disarm` stamps `_disarmed_monotonic` → unload reads it), they do not overlap.
2. **`_last_speech_monotonic` is an atomic float store, NOT lock-guarded.** `_touch_speech`@1029 writes it from the
   host reader thread WITHOUT `_lock`; `_arm`@994 and `_disarm`@1020 write it under `_lock`. The watchdog re-reads
   it UNDER `_lock` (L1131/1133). CPython float stores are atomic → the watchdog always sees a complete value; the
   lock serializes the DISARM decision against concurrent start/stop/toggle, guaranteeing a partial that landed
   just before lock-acquisition cancels the stop. This is the PRD §4.5 "re-check under the listen lock" mechanism.
3. **`_idle_watchdog` uses `_shutdown.wait(1.0)`, not `time.sleep(1.0)`.** So it both ticks ~1s AND exits promptly on
   shutdown (no orphan thread lingering past `quit`). Mirrors `_idle_unload_watchdog`'s tick (§3).
4. **The watchdog swallows its own exceptions** (L1154-1155 `except Exception: logger.exception(...)`). A transient
   error in `_maybe_auto_stop` never kills the watchdog — it logs and ticks again next second.
5. **abort() after auto-stop is effectively always skipped.** `_maybe_auto_stop` calls `_safe_abort()`@1147 ONLY
   `if disarmed and self._host is not None`, and `_safe_abort`@1355 returns immediately `if not self._text_in_flight`.
   After 30s of silence the run() loop is in `time.sleep(0.05)` (idle), so `_text_in_flight` is clear → abort()
   is skipped (correct: nothing to wake). The path exists for symmetry with stop/toggle; for auto-stop it's a no-op.
   This is NOT a defect — abort() is "best-effort nudge" per `_safe_abort`'s docstring.
6. **The INFO line + the "Recording Stopped" toast.** `logger.info(...)`@1134-1137 is the journal INFO line (property d).
   The "Recording Stopped" toast fires via `_disarm()`@1027 → `_feedback.set_listening(False)` → feedback.py fires
   "Recording Stopped" on the True→False transition (feedback.py L23: "listening-stop -> 'Recording Stopped'
   (set_listening True->False transition; ANY disarm)"). This is the SAME disarm path as stop/toggle — the toast
   wiring itself is a P1.M3.T1 (feedback) concern, not §4's. §4 certifies only that auto-stop REACHES `_disarm`.
7. **The 0-disable check is BEFORE the lock** (L1127-1128 `if threshold <= 0: return`, before `with self._lock`).
   So a disabled auto-stop never acquires `_lock` on its 1s tick — a cheap no-op, no contention with arm/stop.

## §5 — Verdict + acceptance linkage

**✅ COMPLIANT — all 6 properties (a)-(f) + the partial-reset hook pass** (daemon.py file:line in §2). Test slice
= **27 passed, 166 deselected in 1.07s**. No defect found → **NO source or test changes.**

**Acceptance #5 linkage:** PRD §7 #5 = "Daemon survives ≥2 min of silence with no hallucinated output and trivial
CPU use." The idle auto-stop watchdog is the **forgotten-hot-mic guard**: after 30s of no recognized speech it
DISARMS (mic off, models stay). This caps the hot-mic exposure window so a mic left armed cannot hallucinate for
minutes (the blocklist filter §4.5/§4.7 catches the classic hallucinations; auto-stop removes the exposure).
Trivial CPU: when disarmed the run() loop is in `time.sleep(0.05)`; the watchdog itself is a 1s-tick thread.
Note: the 2min silence test (T4) exceeds the 30s auto-stop threshold, so it also EXERCISES the auto-stop disarm
transition as a side effect — the daemon must remain stable across the armed→auto-stopped→(unload clock running)
transitions for the full 2min. §4 certifies that transition is correct.

## §6 — Append convention

APPEND `# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)` to `architecture/gap_lifecycle.md` BELOW the last section
present. At research time the file has §1 (L1) + §2 (L201) = 404 lines; §3 (S3) is being appended in parallel.
§4's `# §4` heading makes it compose with §3 regardless of append order. Mirror §2's shape (the file's own
§2 @L201): Scope/Audited-artifacts/Bottom-line/§4.1 Method/§4.2 compliance-table/§4.3 test-evidence/
§4.4 nuances/§4.5 Conclusion. The deliverable is the REPORT section — NO source/test edits (no defect exists).
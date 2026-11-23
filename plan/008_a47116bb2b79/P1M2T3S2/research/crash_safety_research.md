# Research Note — P1.M2.T3.S2: Crash Safety (ducked flag self-heal + ExecStopPost)

> Pre-verified research for the ducking crash-safety layer. Consumes P1.M2.T3.S1's contract
> (set_ducked write side + seam wiring). Deliverables: NEW `voice_typing/ducking_heal.py`,
> daemon startup self-heal + `flush()` at quit, `ExecStopPost` in the unit + lockstep test.

## §0 — VERIFIED FACTS (live tree, 2026-11-23)

| # | Fact | Evidence |
|---|---|---|
| F1 | install.sh's `__REPO__` sed is **GLOBAL over the whole unit file** — `sed -i "s#__REPO__#$REPO#g" "$USER_UNIT_DIR/voice-typing.service"` (install.sh:119). An `ExecStopPost=__REPO__/...` line WILL be substituted. **No install.sh edit needed** (the "ExecStart only" worry in the contract/seams doc is stale — the comment says ExecStart but the sed is file-wide). | install.sh:116-119 |
| F2 | The unit has NO ExecStopPost today (grep → no match). Existing directives: ExecStartPre (import-environment), ExecStart (wrapper, `__REPO__`), Restart=on-failure, RestartSec=2, KillMode=mixed, TimeoutStopSec=15. | systemd/voice-typing.service |
| F3 | Lockstep test pattern: `tests/test_systemd_unit.py` `_unit_lines()` @45 strips comments; `test_restart_on_failure` @93-96 asserts an EXACT directive line (`assert any(ln == "Restart=on-failure" for ln in _unit_lines())`). Mirror this style for ExecStopPost. | test_systemd_unit.py:45-52, 93-96 |
| F4 | `Feedback.__init__` (@89) does NOT write state.json — it only seeds `self._state`. `_write()` fires in SETTERS only (:122,:133,:145,:153,:169,:191). So the crashed session's `"ducked": true` SURVIVES Feedback construction — but the daemon's boot `set_models_loaded(...)` call (in `VoiceTypingDaemon.__init__`) writes immediately and clobbers it to the seeded False. → The self-heal read MUST happen BEFORE any Feedback setter fires (safest: before the Feedback ctor line in daemon `__init__`). | feedback.py:89-122 |
| F5 | Path resolution: `cfg.feedback.resolved_state_file()` is "the SINGLE source of truth for the path — called lazily inside _write() (NOT __init__) because XDG_RUNTIME_DIR is unset outside real sessions" (docstring :47-48; raises RuntimeError if empty AND XDG unset). ducking_heal MUST use the same resolver. | feedback.py:46-48, 220-245 |
| F6 | `AsyncDucker.flush(self, timeout: float = 2.0) -> bool` EXISTS (ducking_async.py:84) — bounded join of the worker. S4 landed. | ducking_async.py:84 |
| F7 | Post-crash, `AudioDucker.release()` is a NO-OP: `_release_mpris` returns when the ledger is empty; `_release_volume` returns when `_volume_snapshot is None`. The ledger/snapshot are in-memory only. → The heal CANNOT just call release(); it needs heuristic logic. | audio_ducking.py:106-117, 131-136, 160-166 |
| F8 | `MprisBusctlBackend` @75 (ducking_mpris.py) implements `list_players()` / `resume_player(name)` / `get_sink_volume_pct()`; its `_run` subprocess helper is bounded. ducking_mpris/volume/async/audio_ducking are S1-S4-owned: READ/import OK, NEVER edit. | ducking_mpris.py:75-123 |
| F9 | `AudioConfig` landed: `duck_mode: str = "off"` (:226), `duck_volume_pct: int = 15` (:227), with validation (:231-236). Volume eps for compare: `audio_ducking._VOL_EPS` (module const). | config.py:218-236 |
| F10 | `voice_typing/__init__.py` is a docstring only (80 bytes) — `python -m voice_typing.ducking_heal` import cost is trivial; no CUDA libs load (heal = stdlib + config + ducking_mpris subprocess). `.venv/bin/python` is the repo-standard interpreter. | voice_typing/__init__.py |
| F11 | test_ducking.py currently holds ONLY the core AudioDucker tests (:97-240). S1's lifecycle section (`_FakeDucker`, `_make_ducking_daemon`, 9 cases) is CONTRACT — it lands with S1 (implementing in parallel). Re-grep at impl time; reuse S1's fixtures if present, else define locally. | tests/test_ducking.py |
| F12 | Daemon anchors (current): `__init__` @604 (Feedback constructed inside it — grep `self._feedback = Feedback` for the exact line); `run()` @953; `request_shutdown()` @2207 (S1 inserts `_duck_release()` after `self._shutdown.set()`); `shutdown()` follows (~2210+, single-flight via `_teardown_done` @660, teardown runs OUTSIDE `_lock`). | daemon.py |
| F13 | PRD §4.2quinquies crash-safety text: "a `ducked` field in the feedback state file lets a post-crash restart self-heal (best-effort release at startup when set), and the systemd unit gets an `ExecStopPost` best-effort restore." Test case (f): "crash-recovery: `ducked` flag in state → release at next daemon start." | PRD.md §4.2quinquies |
| F14 | systemd runs `ExecStopPost=` on EVERY stop — clean exit, failure, AND SIGKILL/timeout — which is exactly the crash net needed. It shares the TimeoutStopSec budget; the heal is bounded (≤1 s per call, ~3 calls) so 15 s is ample. | systemd.unit docs (standard semantics) |

## §1 — THE HEAL DESIGN (documented judgment call)

Post-crash there is NO bookkeeping (F7), so "best-effort release" must be heuristic and
mode-agnostic (the crashed session's tier is unknown). One shared module —
`voice_typing/ducking_heal.py` — serves BOTH consumers (daemon startup thread AND
`ExecStopPost`'s `python -m voice_typing.ducking_heal`):

1. **Gate**: read state.json via `cfg.feedback.resolved_state_file()`; if `ducked` is not
   exactly `True` → exit 0, ZERO backend calls (this is also the clean-stop case: quit already
   released + flushed, flag is false, ExecStopPost no-ops).
2. **MPRIS heal**: enumerate players; resume EVERY currently-`Paused` one. False positives
   (a player the user paused themselves) are re-pausable; false negatives leave music stuck —
   resuming is the least-bad direction. One INFO line per resume.
3. **Volume heal — WARN-ONLY (decision)**: if the default sink volume ≈ `cfg.audio.duck_volume_pct`
   (within `audio_ducking._VOL_EPS`), log ONE warning that the crash left the sink at duck level;
   do NOT set a restore value. Rationale: the pre-duck volume is unknowable post-crash; a guessed
   restore (e.g. 100%) can blast audio — PRD philosophy: "a restore that clobbers … is worse than
   not ducking" / "put it back EXACTLY as it found it". A journal warning + manual bump is safer.
   Carry this rationale into the code comment.
4. **Discipline**: every backend call bounded (≤1 s, mirror `ducking_mpris._run`); every failure →
   ONE warning, continue; ALWAYS exit 0 (never a gate; an ExecStopPost failure would only noise
   the journal). Stdlib-only imports.

## §2 — DAEMON WIRING (2 sites)

- **Startup self-heal**: early in `VoiceTypingDaemon.__init__` — BEFORE the `self._feedback = Feedback(...)`
  line (F4: the first setter write clobbers the flag): `ducked = ducking_heal.read_ducked_flag(cfg)`;
  remember it; after the ctor wiring, if ducked: spawn a one-shot daemon thread
  (`threading.Thread(target=ducking_heal.heal, args=(cfg,), daemon=True, name="vt-duck-heal")`) +
  one INFO line. Never blocks boot; never under `_lock`; heal is idempotent + bounded.
- **flush() at quit**: at the END of `shutdown()` (after host teardown, before return):
  `if self._ducker is not None: try: self._ducker.flush(2.0) except Exception: logger.warning(...)`.
  Rationale: S1's `request_shutdown` seam only DISPATCHES the async release; without a bounded
  flush the process can exit before the worker finishes resuming → media stuck despite the seam.
  Budget: 2 s inside TimeoutStopSec=15 (5 s teardown + 2 s flush + 8 s headroom). Note in comment.

## §3 — ExecStopPost + LOCKSTEP TEST

Unit (after `RestartSec=2` or near TimeoutStopSec — keep directive grouping sane):
```
# Crash safety (PRD §4.2quinquies): if the daemon dies while media is ducked (crash, SIGKILL at
# TimeoutStopSec, OOM), its in-memory restore bookkeeping is gone. The persisted `ducked` flag in
# $XDG_RUNTIME_DIR/voice-typing/state.json is the orphan signal: this best-effort restore resumes
# paused MPRIS players and warns when the sink was left at duck volume (it never guesses a volume
# restore). No-ops (exit 0) when the flag is unset — i.e. on every clean stop, where the daemon
# already released + flushed ducking itself. Runs on every stop per systemd semantics.
ExecStopPost=__REPO__/.venv/bin/python -m voice_typing.ducking_heal
```
(Substitution covered by F1 — the sed is file-wide `g`. Comment above = Mode A docs requirement.)

Lockstep test (mirror test_restart_on_failure @93-96):
```python
def test_execstoppost_ducking_crash_heal():
    """ExecStopPost runs the ducking crash-heal (best-effort media restore; PRD §4.2quinquies)."""
    lines = [ln for ln in _unit_lines() if ln.startswith("ExecStopPost=")]
    assert len(lines) == 1, lines
    assert lines[0] == "ExecStopPost=__REPO__/.venv/bin/python -m voice_typing.ducking_heal", lines[0]
```
(The exact-line assert doubles as the `__REPO__`-placeholder guard — install.sh:119 substitutes it.)

## §4 — TEST MATRIX (appends)

test_ducking.py (heal section — fake backend, tmp state file, no real audio):
1. `test_heal_noop_when_ducked_false` — state ducked:false → zero backend calls.
2. `test_heal_noop_when_state_file_missing` — absent file → zero calls, no raise.
3. `test_heal_resumes_paused_players_when_ducked` — ducked:true + one Paused player → resume_player called; Playing players untouched.
4. `test_heal_volume_warn_only` — ducked:true + sink at duck pct → NO set_sink_volume_pct; warning logged (caplog).
5. `test_heal_always_exits_zero_on_backend_failure` — backend raises → swallowed, no propagate.
6. `test_daemon_startup_heals_ducked_flag` — daemon ctor with state ducked:true (tmp state_file) → heal dispatched (join the thread; assert fake-backend resume called) AND a later Feedback write reports ducked:false (self-clearing).
7. `test_shutdown_flushes_ducker` — fake ducker records flush(); daemon.shutdown() → flush called once (reuse S1's `_make_ducking_daemon` fixture if landed — F11 — else a local copy).
test_systemd_unit.py: the §3 lockstep test.

## §5 — SCOPE BOUNDARIES

- S1 (parallel, implementing): set_ducked write side, seam calls, `_duck_engage/_duck_release`, request_shutdown release dispatch, feedback lockstep (:129/:441), lifecycle tests. THIS task only CONSUMES those.
- S2-S4 modules: frozen — import OK (MprisBusctlBackend, AsyncDucker.flush), never edit.
- T4 (later): flips duck_mode default to "mpris" + live acceptance evidence. Not here.
- README/ACCEPTANCE.md: P1.M7 owns. Unit comment (Mode A) is the only doc surface here.
- No install.sh / config.py / config.toml changes (F1, F9 — both already sufficient).

## §6 — VALIDATION (verified commands)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_ducking.py tests/test_systemd_unit.py tests/test_feedback.py -q
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # vs tests/G1_BASELINE.md
timeout 60 .venv/bin/python -m voice_typing.ducking_heal   # exit 0, no output noise (flag unset in real state)
grep -n "ExecStopPost" systemd/voice-typing.service tests/test_systemd_unit.py
```

# Research — AudioDucker core + Backend protocol + bookkeeping (P1.M2.T2.S1 / D1)

The PRP (../PRP.md) is the runbook. This note pins the verified facts, the design, and
the task boundary inside D1.

## 1. Verified facts

- **Subprocess discipline (d1_ducking_seams.md §1e, confirmed by grep):** only
  `feedback.py:66` and `typing_backends.py:47` import subprocess in `voice_typing/`;
  ZERO `subprocess.run(..., timeout=)` calls exist today. The ≤1 s timeout pattern is
  NEW and belongs to the tier backends (S2 busctl / S3 wpctl) — they copy
  `feedback.py:247-261 _notify`'s swallow discipline (`check=False`,
  `stdout/stderr=DEVNULL`, `try/except (OSError, subprocess.SubprocessError)` → one
  log line, never re-raise) and ADD `timeout=1.0` (`TimeoutExpired` IS a
  `SubprocessError` → same except arm). A new `voice_typing/audio_ducking.py` keeps the
  third import local (module top stays stdlib-only; S2/S3 add the subprocess calls).
- **Config contract (P1.M2.T1.S1 PRP, parallel "Ready" — treat as landed):**
  `AudioConfig` dataclass with `duck_mode: str = "off"` (enum off/mpris/volume,
  TypeError guard) + `duck_volume_pct: int = 15` (non-bool-int guard), exposed as
  `cfg.audio.*` on `VoiceTypingConfig`; ships `"off"`; default flips to `"mpris"` only
  in P1.M2.T4 (evidence-gated).
- **PRD §4.2quinquies sovereignty rules (the core's contract):**
  MPRIS resume-only (a) players WE paused, (b) that were `Playing` before we paused
  them, (c) that are STILL `Paused` now (user resumed/paused → never fight them;
  restore is additive, never destructive). Volume: snapshot at arm → set
  `duck_volume_pct`; restore ONLY if current volume still equals what we last set
  (compare-before-restore; a restore that clobbers a user change is worse than not
  ducking). Engage/release idempotent; repeated arms must not stack pauses or overwrite
  the ORIGINAL snapshot; release-without-engage = no-op; `off` = byte-identical.
- **Task boundary inside D1** (plan 008): S1 (THIS) = AudioDucker core + Backend
  protocol + bookkeeping + pure unit tests. **S2** = the busctl MPRIS backend (implements
  the protocol's player half, with the ≤1 s subprocess timeout). **S3** = the wpctl
  volume backend (volume half). **S4** = failure discipline hardening (non-blocking,
  bounded engage so a hung backend can't delay arm — the arm-latency bound). **T3** =
  daemon lifecycle wiring (engage at `_arm()` toast site :1415, release at `_disarm()`
  :1454 + `request_shutdown()` :2177, all spawned threads never under `_lock`) + crash
  safety (`ducked` feedback flag — the seams doc §2 recipe — + ExecStopPost). **T4** =
  default flip. This task touches ONLY `voice_typing/audio_ducking.py` (new) +
  `tests/test_ducking.py` (new). No daemon, no config, no feedback, no systemd edits.
- **Test seam recommendation (seams doc §5):** `tests/test_ducking.py` with pure fakes,
  CUDA-free, no daemon construction — the AudioDucker is a plain injectable object, so
  no `_make_daemon` needed at this layer.

## 2. The design

**One injectable Backend protocol (S2/S3 implement it; the ducker orchestrates +
bookkeeps).** Primitives are tier-agnostic: the MPRIS half (`list_players`,
`pause_player`, `resume_player`) and the volume half (`get_sink_volume_pct`,
`set_sink_volume_pct`). A single runtime-checkable `Protocol` keeps S1→S2/S3 the
"injectable Backend" the item names; each tier task fills in its half (a production
backend may implement both; tests always inject a fake).

```python
@dataclass(frozen=True)
class PlayerState:
    name: str
    playing: bool

@runtime_checkable
class DuckBackend(Protocol):
    def list_players(self) -> list[PlayerState]: ...
    def pause_player(self, name: str) -> bool: ...
    def resume_player(self, name: str) -> bool: ...
    def get_sink_volume_pct(self) -> float | None: ...
    def set_sink_volume_pct(self, pct: float) -> bool: ...
```
Backend contract (docstring): every method bounded (≤1 s), best-effort, never raises;
failure = `[]`/`False`/`None` + one journal line. The ducker ALSO wraps every call in
its own `_call()` swallow (belt-and-braces: a misbehaving backend can never break
engage/release — mirrors feedback's `_notify` discipline at the orchestration layer).

**AudioDucker (bookkeeping + sovereignty):**
- State under one `threading.Lock`: `_engaged: bool`, `_paused_players: list[str]`
  (ledger — only names WE paused, which at engage-time were `Playing` ⇒ rule (b) is
  enforced at ledger-fill time), `_volume_snapshot: float | None`.
- `engage()`: under lock — no-op if `_engaged` or mode `"off"`; set `_engaged=True`
  FIRST (a partially-failed engage still unwinds via release); then dispatch:
  - mpris: `list_players()` → pause each `playing` one, appending successes to the
    ledger; one INFO line with the paused names. Non-playing players untouched.
  - volume: snapshot `get_sink_volume_pct()`; `None` → one WARNING, no snapshot, done
    (release then no-ops — never restore what we never changed). Else
    `set_sink_volume_pct(duck_volume_pct)`; on success store the snapshot (set failed ⇒
    no snapshot ⇒ release no-ops).
- `release()`: under lock — no-op if not `_engaged`; clear `_engaged`; dispatch:
  - mpris: fresh `list_players()` → name→state map. For each ledger name: player gone
    → skip; **currently `playing` → skip (rule (c): the user resumed it — never
    fight them)**; else `resume_player(name)`. Ledger cleared. A player the user
    paused themselves is never in the ledger → never touched (additive restore).
  - volume: take+clear the snapshot; `None` → done. Fresh `get_sink_volume_pct()`;
    `None` → one WARNING, done. If `abs(current − duck_volume_pct) > _VOL_EPS`
    (0.5 pct): the user changed volume mid-dictation → log one INFO ("keeping user
    value"), DO NOTHING. Else `set_sink_volume_pct(snapshot)` + one INFO restore line.
- Idempotence: the `_engaged` gate makes double-engage a no-op (second engage can
  neither re-pause nor overwrite the original snapshot) and release-without-engage a
  no-op (zero backend calls).
- `engaged` read-only property (T3/S4/status consume it; the `ducked` feedback latch
  is T3.S2's).
- `from_config(cfg, backend)` classmethod: reads `cfg.audio.duck_mode` +
  `cfg.audio.duck_volume_pct` (the parallel config contract) — convenience for T3.
- Constructor takes plain `backend, *, mode, volume_pct` so unit tests (and T3) never
  depend on the config module's landing order.

**Mode A module docstring**: states the two tiers (MPRIS pause primary; sink-volume
duck fallback), the sovereignty rules verbatim (resume-only-what-we-paused ∧
was-playing ∧ still-paused; compare-before-restore), the failure discipline (bounded,
one-line, never a gate, idempotent), and that S2/S3 own the subprocess backends.

## 3. Unit tests (tests/test_ducking.py — pure, no subprocess, no daemon)

`_FakeBackend` records calls (`paused`, `resumed`, `set_calls`, `call_log`), holds
mutable `players: list[PlayerState]` + `volume: float | None`, optional `fail={"pause_player",...}`
(raising) — the file's only fixture machinery. Tests (PRD §4.2quinquies (a)(b)(e) +
bookkeeping edges):
1. `test_engage_mpris_pauses_only_playing_players` — A playing, B paused → pause A
   only; ledger == [A].
2. `test_release_resumes_only_we_paused_and_still_paused` — engage pauses A,C; user
   resumes A, user pauses B themselves → release resumes C ONLY (A skipped rule (c);
   B untouched — not ours).
3. `test_release_player_gone_is_skipped` — ledger name absent from fresh list → no
   resume call, no error.
4. `test_volume_engage_snapshots_and_ducks` — 50 → set 15, snapshot 50.
5. `test_volume_release_restores_when_untouched` — still 15 → set 50 back.
6. `test_volume_release_skips_restore_when_user_changed` — user set 80 mid-dictation →
   NO set call (call_log proves it), one INFO logged.
7. `test_engage_idempotent_double_engage` — two engages → one pause set; volume:
   snapshot stays the ORIGINAL 50 (not overwritten by 15).
8. `test_release_without_engage_is_noop` — zero backend calls.
9. `test_off_mode_never_calls_backend` — engage+release → empty call_log.
10. `test_backend_exception_swallowed_logged_once` — fail={"pause_player"} → no
    propagate; engage completes; exactly ONE warning in caplog.
11. `test_volume_engage_read_failure_leaves_no_snapshot` — get→None → no set call;
    release no-ops.
12. `test_from_config_reads_audio_section` — `VoiceTypingConfig` with
    `audio=AudioConfig(duck_mode="volume", duck_volume_pct=25)` → ducker mode/volume
    wired (consumes the parallel config contract).

## 4. Tooling

pytest 9.1.1 in `.venv`; fast suite today = the current HEAD count (run to confirm);
`.venv/bin/python -m pytest` under `timeout` per AGENTS.md (the new tests are pure —
sub-second). Optional ruff at `/home/dustin/.local/bin/ruff`. Full paths (zsh aliases).

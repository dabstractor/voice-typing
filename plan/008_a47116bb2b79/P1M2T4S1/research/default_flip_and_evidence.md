# Research — P1.M2.T4.S1: Default flip (duck_mode → "mpris") + acceptance evidence

## §0 Verified facts (live tree, F-numbers)

- **F1 — the flip is a 2-file lockstep + 1 test-line value change:**
  - `voice_typing/config.py:226` — `duck_mode: str = "off"` (in `AudioConfig` @218; validation @231
    accepts off/mpris/volume — unchanged).
  - `voice_typing/config.py:221-222` — the AudioConfig docstring says "Ships duck_mode='off' … the
    default flips to 'mpris' the round the ducker lands (P1.M2.T4)" — THIS round; the docstring must
    be updated to state the landed default.
  - `config.toml:60` — `duck_mode = "off"` with the comment tail "Ships 'off' until the feature
    lands; the default becomes 'mpris' then." — value AND comment must flip (DOCS Mode A).
  - `tests/test_config.py:277` — `assert a.duck_mode == "off" and a.duck_volume_pct == 15` pins the
    DEFAULT VALUE; must become `"mpris"`. This is the ONLY test asserting the default value.
- **F2 — the lockstep + key-set tests need NO structural change:** 
  `tests/test_config_repo_default.py::test_repo_config_toml_equals_defaults` @17 compares repo
  config.toml vs dataclass defaults (auto-adapts when BOTH flip; goes red if only one flips — that's
  the lockstep guard). `test_repo_config_toml_has_no_extra_keys` @27 pins the 26-key set — a VALUE
  flip doesn't touch keys (contract RESEARCH NOTE). Optional comment touch-up: line 49's
  `# §4.2quinquies media ducking (D1; ships "off")` → drop the "ships off" clause.
- **F3 — the D1 machinery is on disk (T1/T2/T3.S1 landed; T3.S2 in flight = contract):**
  - `voice_typing/audio_ducking.py` — `AudioDucker` @60: `engage()` @95, `release()` @106;
    journal lines: `"ducking: paused MPRIS player(s): %s"` @129, `"ducking: resumed MPRIS player(s):
    %s"` @146, `"ducking: sink volume %.0f%% -> %.0f%%"` @158, `"ducking: volume was changed
    mid-dictation (%.0f%%); keeping user value"` @170, `"ducking: restored sink volume %.0f%%"` @173,
    `"ducking: %s failed; continuing"` @182 (`_call` swallow discipline).
  - `voice_typing/ducking_async.py` — `AsyncDucker` @56 (`engage` @76 / `release` @80 / `flush(2.0)`
    @84) — non-blocking dispatch; arm never waits on media (PRD failure discipline).
  - `voice_typing/ducking_mpris.py` — `MprisBusctlBackend` @75 (busctl-based list/pause/resume).
  - `voice_typing/ducking_volume.py` — wpctl snapshot + compare-before-restore tier.
  - `voice_typing/daemon.py` — seams landed: `_duck_engage` @1468 (called from `_arm` @1565 after
    `set_listening(True)`), `_duck_release` @1489 (called from `_disarm` @1605 + dead-host @1164 +
    `request_shutdown`), `self._ducker is None` when `duck_mode="off"` @868 (byte-identical path).
  - `voice_typing/feedback.py` — `set_ducked` @161 (state.json `ducked` flag, S1).
  - T3.S2 contract (parallel): `voice_typing/ducking_heal.py` + `ExecStopPost` + `flush` at shutdown —
    treat as landed; VERIFY before evidence (Task 1 grep) but do NOT depend on it for the flip itself.
- **F4 — engage happens at `_arm()`, which runs AFTER the lazy model load.** The sandbox evidence
  daemon pays a full CUDA model load (~1–3 s, ~1.5–3 GB VRAM) per instance. The ducker is built ONCE
  at daemon init from cfg → **one sandbox daemon per duck_mode value**. Scenarios merge: the
  "default" scenario (sandbox config with NO `duck_mode` key → flipped default active) IS the mpris
  scenario → **3 daemon instances total** (default/mpris, volume, off).
- **F5 — the sandbox daemon MUST set `output.backend = "null"`** (config table overlay: a partial
  `[output]` table overlays defaults — config.py:384) or a recognized final would TYPE INTO THE
  OPERATOR'S FOCUSED WINDOW (wtype default). This is the e2e_virtual_mic.sh precedent ("an automated
  run can never type into the developer's focused window").
- **F6 — the MPRIS tier pauses EVERY playing player** (ledger-tracked, restored at release). During
  evidence: if the operator's real music is playing it will be paused and resumed (correct behavior,
  but document the caveat; prefer running when user media is idle). Disposable target: `mpv --idle
  --no-video <silent.wav>` publishes MPRIS `PlaybackStatus=Playing`. A silent WAV is generated
  dependency-free with stdlib `wave` (N seconds of zero frames, 16 kHz mono s16le).
- **F7 — the volume tier mutates the DEFAULT SINK (global state).** Harmless-target pattern (the
  e2e_virtual_mic.sh discipline): `pactl load-module module-null-sink` → `pactl set-default-sink
  <n>` → run the scenario on the disposable sink → restore the original default + `pactl
  unload-module <index>` in the EXIT trap (unload by recorded index; the AGENTS.md cleanup note
  warns `unload-module module-null-sink` nukes ALL null-sinks — never do that here).
- **F8 — two CUDA daemons at once = double VRAM.** `tests/test_idle_and_gpu.sh` precedent: stop the
  user unit first (`systemctl --user stop voice-typing`), restore it in the trap (`systemctl --user
  start voice-typing`). The evidence script does this.
- **F9 — sandboxing the daemon:** env `XDG_RUNTIME_DIR=$SB/run XDG_CONFIG_HOME=$SB/cfg` gives the
  instance its own control socket (`$SB/run/voice-typing/control.sock`) and state file, so
  `voicectl` in the same env talks ONLY to it — the user's systemd daemon is never touched. Run
  detached: `setsid .venv/bin/voice-typing-daemon >> "$SB/daemon.log" 2>&1 &disown` (AGENTS.md Rule
  2; NEVER foreground). Readiness poll: `timeout 15 .venv/bin/voicectl status` (exit 2 = not up yet).
  Teardown by RECORDED PID (quit via socket → `kill -TERM $PID` → `kill -KILL $PID`); NEVER
  `pkill -f voice-typing` (would kill the user's systemd daemon mid-script).
- **F10 — every `voicectl` call wrapped `timeout 30`** (control socket has no read timeout —
  AGENTS.md). Script itself under `timeout 900`; daemon.log is short-lived but the script truncates
  to a bounded excerpt in the evidence doc (`grep ducking: | head -40`), and the scratch dir is
  `rm -rf`'d by the trap (tmpfs discipline).
- **F11 — pause-latency measurement (PRD "within ~1 s"):** after `timeout 30 .venv/bin/voicectl
  start`, poll `playerctl -p mpv status` at 0.1 s cadence until `Paused`, timestamp with
  `date +%s%N`; record Δt (assert < 1.5 s hard bound; PRD's ~1 s is the soft target — engage is
  concurrent with arming so it typically lands in ~100–300 ms).
- **F12 — evidence homes:** `tests/G1_BASELINE.md` (pre-change reds) and `tests/ACCEPTANCE.md`
  exist; ACCEPTANCE.md ROWS are owned by P1.M7.T2.S2 (Mode B) — NOT this task. This task records
  evidence in a NEW `tests/D1_DUCK_EVIDENCE.md` + checks in the re-runnable script
  `tests/d1_duck_evidence.sh` (mirrors tests/e2e_virtual_mic.sh's shape: preflight, trap, bounded
  steps). P1.M7.T2.S2 later transcribes rows from it.
- **F13 — user sovereignty, scripted:** with TWO disposable mpv players playing: manually `playerctl
  -p <p2> pause` mid-arm (simulating user action) → at release p2 must STAY paused (rule: resume
  only what WE paused). Volume twin: set sink to 60% mid-arm (≠ our 15%) → release keeps 60% +
  logs the mid-dictation line (@170).
- **F14 — `duck_mode="off"` byte-identical:** unit level already pinned (`self._ducker is None` @868
  → every seam no-ops, no subprocess); live level: sandbox off-daemon → `grep -c "ducking:" log`
  must be 0 across an arm/disarm cycle.

## §1 The flip (exact edits)

1. `config.py:226`: `duck_mode: str = "mpris"` + trailing comment update.
2. `config.py` AudioConfig docstring (@219-224): replace the "Ships duck_mode='off' … flips … (P1.M2.T4)"
   sentences with the landed state ("Defaults to 'mpris' (P1.M2.T4): pause players at arm, resume
   only what WE paused at disarm; 'off' restores pre-D1 behavior exactly").
3. `config.toml:60`: `duck_mode = "mpris"` + comment rewrite: drop "Ships 'off' until the feature
   lands; the default becomes 'mpris' then." → state the behavior + that "off" restores pre-D1
   behavior byte-for-byte (DOCS Mode A).
4. `tests/test_config.py:277`: `assert a.duck_mode == "mpris" and a.duck_volume_pct == 15`.
5. Optional comment: `tests/test_config_repo_default.py:49` drop `; ships "off"`.
6. NOTHING else: key-set pin (26) untouched; validation set untouched; all other ducking tests
   construct explicit modes/fakes (verified: only test_config.py:277 pins the default).

## §2 Evidence script design (tests/d1_duck_evidence.sh)

Phase 0 preflight: binaries (voicectl/voice-typing-daemon/mpv/playerctl/pactl/wpctl) or exit 2 with
"operator checklist" pointer; systemd unit stop (record whether it was active); scratch mktemp -d;
silent WAV via stdlib python wave; EXIT trap: restore default sink + unload null-sink by index,
kill mpv PIDs, kill daemon PID (TERM→KILL), `systemctl --user start voice-typing` if it was active,
`rm -rf $SB`.

Phase 1 (default → mpris, merged): sandbox daemon, config.toml = `[output] backend = "null"` +
`[asr] auto_stop_idle_seconds = 0` (stop auto-disarm from racing the scenario; 0 disables) and NO
duck_mode key → proves the flipped default engages. mpv p1 + p2 playing. arm → poll p1 Paused
(Δt<1.5s) + log @129; manually pause p2 (user sovereignty); stop → p1 Playing again + log @146; p2
STILL Paused. Record lines.

Phase 2 (volume): null-sink default; sandbox daemon config adds `duck_mode = "volume"`; wpctl
40% → arm → 15% + log @158; user-change: 60% mid-arm → stop → stays 60% + log @170; second
cycle 40% → arm → stop → restores exactly 40% + log @173.

Phase 3 (off): sandbox daemon `duck_mode = "off"`; arm/disarm; `grep -c "ducking:"` == 0.

Each phase prints `PASS <name> ...` lines; script exits non-zero on any failure. Output excerpt
(Δt values + ducking journal lines, ≤40 lines) is pasted into tests/D1_DUCK_EVIDENCE.md.

## §3 Operator checklist fallback (if mpv absent, or the operator prefers manual)

Documented checks with EXACT expected journal lines (from F3) + `journalctl --user -u voice-typing`
for the systemd daemon after a natural restart: arm with music playing → pause ≤~1 s → stop →
resume; volume tier via the real sink (operator-mediated); sovereignty by manually pausing/adjusting
mid-dictation. The evidence doc records which path (scripted / operator) produced each row.

## §4 Validation commands

```bash
timeout 600 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_ducking.py -q
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # vs tests/G1_BASELINE.md
timeout 900 bash tests/d1_duck_evidence.sh
grep -n 'duck_mode' config.toml voice_typing/config.py tests/test_config.py
```

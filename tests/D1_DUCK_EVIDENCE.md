# D1 acceptance evidence — `duck_mode` default flip (PRD §4.2quinquies; P1.M2.T4.S1)

**Recorded**: 2026-11-23 08:09 EST · **HEAD at recording**: `b9da1eb` (+ this task's working tree)
**Method**: scripted — `timeout 900 bash tests/d1_duck_evidence.sh` (checked in; re-runnable).
**Result**: **exit 0 — ALL 12 SCENARIOS PASS** (the five §4.2quinquies acceptance rows map to the
12 scripted checks below; Δt and journal excerpts are from THIS run, verbatim).

The script runs three SANDBOX daemons (one per duck_mode — the ducker is built once at init from
cfg) with `output.backend = "null"` (an automated run can never type into a focused window), own
`XDG_RUNTIME_DIR`/`XDG_CONFIG_HOME`, `auto_stop_idle_seconds = 0` (no auto-disarm race), and the
user systemd unit stopped around the run (double-VRAM avoidance) and restarted by the EXIT trap.
Disposable MPRIS targets: a minimal GLib stub (this host's mpv ships no MPRIS plugin and VLC's
instance registration is not playerctl-controllable — both verified; see the script header).

## The five §4.2quinquies acceptance rows

| # | Acceptance scenario | Scripted checks (this run) | Result |
|---|---------------------|----------------------------|--------|
| 1 | Music playing → arm → pauses ≤~1 s → resume at stop (journal lines) | `mpris-pause<=1.5s` (**107 ms** after the arm command returned; arm round-trip 2755 ms = lazy CUDA load) · `mpris-engage-journal-line` · `mpris-resume-at-stop` (**107 ms**) · `mpris-release-journal-line` | **PASS** |
| 2 | `duck_mode="volume"` ducks to 15% and restores EXACTLY (40% cycle, disposable null-sink) | `volume-duck-15` (40% → 15% at arm) · `volume-exact-restore` (15% → exactly 40%) | **PASS** |
| 3 | User sovereignty — user's media/volume actions are NEVER overridden | `sovereignty-user-resume-mid-arm` (user resumes p2 mid-dictation → daemon never fights them) · `sovereignty-user-resume-honored` (p2 absent from the resumed ledger) · `sovereignty-user-paused-stays-paused` (a user-paused player — never Playing at arm, so never in the ledger — stays Paused) · `volume-user-60-kept` (mid-arm 60% survives release) | **PASS** |
| 4 | `duck_mode="off"` is byte-identical to pre-D1 (no ducking activity) | `off-zero-ducking-lines` (an arm/disarm cycle logged **zero** `ducking:` lines) | **PASS** |
| 5 | The flipped DEFAULT engages with NO `duck_mode` key in the config | Phase 1's sandbox config OMITS `[audio]` entirely — the default ("mpris" after this flip) ducked and restored | **PASS** |

Scripted-path count: 12/12 PASS. No operator-checklist fallback rows were needed (every host tool
the script needs was present); the fallback recipe is preserved in the script header + below.

## Journal-line excerpts (verbatim, from this run)

```
INFO voice_typing.audio_ducking: ducking: paused MPRIS player(s): org.mpris.MediaPlayer2.brave.instance2729297, org.mpris.MediaPlayer2.vtdummy1, org.mpris.MediaPlayer2.vtdummy2
INFO voice_typing.audio_ducking: ducking: resumed MPRIS player(s): org.mpris.MediaPlayer2.brave.instance2729297, org.mpris.MediaPlayer2.vtdummy1
INFO voice_typing.audio_ducking: ducking: sink volume 40% -> 15%
INFO voice_typing.audio_ducking: ducking: volume was changed mid-dictation (60%); keeping user value
INFO voice_typing.audio_ducking: ducking: restored sink volume 40%
```

Notes on the excerpts (they demonstrate the rules, not defects):
- **brave** (the operator's real browser media, playing during the run) appears in the paused
  ledger and is resumed at stop — the §4.2quinquies "pause EVERY playing player" behavior, with
  user sovereignty intact. The script header documents this transient pause/resume caveat.
- **vtdummy2 was user-resumed mid-dictation** → absent from the resumed ledger (rule c: the USER
  resumed it; the daemon never fights them).
- The mid-dictation line fires for the 60% user change; the clean second cycle logs
  `restored sink volume 40%` (compare-before-restore, exact).

## Sovereignty-row refinement (F13 note)

The research note's F13 sketched "manually pause p2 mid-arm → p2 stays paused". The LANDED ledger
semantics are: engage pauses every **Playing** player (ledger = ours); release resumes ledger
players **only if still paused** — a user-resumed player is skipped (rule c), and a player that
was never Playing at arm never enters the ledger. The scripted rows therefore assert BOTH real
sides of sovereignty: (S1) user-resume mid-dictation is never fought, and (S2) a user-paused
player (never in the ledger) is never resumed. Both PASS. The PRD's own acceptance sentence —
"If the user manually resumed/changed volume mid-dictation, THEIR state wins" — is exactly S1.

## Machine restore (post-run, verified)

- `pactl get-default-sink` == pre-run value (each run records + restores its own; verified in the
  script's final line and re-checked manually after the recorded run).
- `module-null-sink` unloaded **by recorded index** (never by name).
- systemd unit: restarted by the trap (it was active pre-run) — `systemctl --user is-active
  voice-typing` → **active** post-run.
- No stray sandbox daemon / stub-player processes (teardown by RECORDED PID only).
- Scratch dir removed (`mktemp -d` under /tmp + trap `rm -rf`; log excerpts bounded to ≤40 lines).

## Operator checklist fallback (if a host tool is absent, or for a human-verified pass)

Prerequisites: the repo config flipped (see git history; the operator's own
`~/.config/voice-typing/config.toml`, if present, still WINS over the repo default — the
user-visible default lands at the systemd unit's next natural restart, which the script performs
during its cleanup; a manual `systemctl --user restart voice-typing` does the same).

1. **mpris pause/resume**: play music in any MPRIS player → `voicectl start` → expect within ~1 s:
   `journalctl --user -u voice-typing | tail` shows
   `ducking: paused MPRIS player(s): <players>` and the music pauses → `voicectl stop` → music
   resumes and the journal shows `ducking: resumed MPRIS player(s): <players>`.
2. **volume tier** (`duck_mode = "volume"`): set the sink to 40% → arm → 15% +
   `ducking: sink volume 40% -> 15%` → stop → exactly 40% + `ducking: restored sink volume 40%`.
3. **sovereignty**: resume your music mid-dictation → at stop it stays playing (never re-paused);
   change sink volume mid-dictation → at stop your value is kept +
   `ducking: volume was changed mid-dictation (60%); keeping user value`.
4. **off** (`duck_mode = "off"`): arm/disarm → `journalctl --user -u voice-typing | grep -c
   ducking:` == 0 for the session.

## Inputs consumed downstream

`P1.M7.T2.S2` transcribes the five rows above into `tests/ACCEPTANCE.md` / README (Mode B — NOT
this task; those files are untouched here).

# Research — P1.M7.T2.S1 README sync: verified facts, insertion map, no-over-claim ledger

Sources read directly: README.md (454 lines, Oct 4 — pre-delta), config.toml, voice_typing/config.py,
ctl.py, feedback.py, audio_ducking.py surface, ime/manager.py, tests/ACCEPTANCE.md,
tests/D1_DUCK_EVIDENCE.md, plan/008_a47116bb2b79/architecture/{g3_field_matrix.md,
pi_row_verdicts.jsonl, editor_browser_row_verdicts.jsonl, g4_clipboard_verdicts.jsonl}, and the
parallel P1.M7.T1.S1 (G6) PRP.

## 1. What the README must add (item contract → concrete content)

### Media ducking (§4.2quinquies; P1.M2 complete)
- Config (AudioConfig, config.py:238): `duck_mode` default **"mpris"** (flipped with evidence,
  P1.M2.T4.S1, commit `22009a0`), values `"mpris" | "volume" | "off"`; `duck_volume_pct` default **15**.
- Sovereignty rules (D1_DUCK_EVIDENCE.md, 12/12 scripted PASS at HEAD b9da1eb):
  resume ONLY players (a) WE paused, (b) that were Playing before, (c) still Paused now;
  volume tier restores ONLY if current volume still equals what we set (compare-before-restore).
- Default `off` = byte-identical to pre-D1 (zero `ducking:` journal lines — scripted row 4).
- Surfaces: state.json gains `"ducked"` flag (feedback.py:135; crash self-heal reads it at boot);
  systemd unit has `ExecStopPost=… python -m voice_typing.ducking_heal` (voice-typing.service:59).
  Journal lines (verbatim from D1 evidence):
  `ducking: paused MPRIS player(s): …`, `ducking: resumed MPRIS player(s): …`,
  `ducking: sink volume 40% -> 15%`, `ducking: volume was changed mid-dictation (60%); keeping user value`,
  `ducking: restored sink volume 40%`.
- Measured: pause lands ~107 ms after arm returns (D1 evidence). Engage is async — arm latency unchanged.
- Backspace-cancel does NOT release ducking (mic stays hot); release fires on every disarm path
  (manual stop/toggle-off, idle auto-stop, HALT keypress disarm, quit) + crash self-heal.

### Bulk text delivery (§4.2sexies; P1.M3–M6 complete, G6 pending)
- Opt-in: `output.delivery = "bulk-text"`; default remains **"stream-edit"** until G6 graduation.
  Precondition triple enforced at config load, ONE ValueError listing ALL violations (config.py:399-428):
  requires `output.streaming=true`, `asr.graceful_stop=false`, `cancel.keypress_action="disarm"`.
- Status surface (ctl.py:153-181; feedback.py:93-146): `voicectl status` prints
  `delivery: {mode} ({state})` (+ `delivery reason:` / `delivery op:` when non-empty);
  states: `inactive | active | unsupported | fault`; `delivery_mode` mirrors [output] delivery;
  state.json gains delivery_mode/delivery_state/delivery_reason/last_confirmed_op.
- `voicectl session [--copy]` (ctl.py:185-190, 267, 362-430): prints the most recent COMPLETED
  dictation session text exactly; `--copy` stages it to the Wayland clipboard (no added newline),
  prints `copied N chars`; exit 1 + clipboard untouched when no completed session exists;
  `--copy` with a non-session command = usage error 64; truncation reported on stderr.
- CLI is now SEVEN commands (README's "Upgrading from Rev 1" section still says six — must update).
- Delivery routes landed: IM-v2 adapter (voice_typing/ime/), pi cooperating-editor adapter
  (voice_typing/pi_editor.py — pi extension + AF_UNIX control socket), clipboard insert fallback
  (voice_typing/clipboard_target.py, conditional ghostty-class only).

## 2. No-over-claim ledger — what is VERIFIED vs NOT (R.2 rule)

| Claim | Status | Evidence |
|---|---|---|
| Ducking mpris/volume/off + sovereignty | **verified** (scripted, 12/12) | tests/D1_DUCK_EVIDENCE.md |
| G2 controller fake-target matrix | **verified** | plan/.../architecture/g2_gate_record.md |
| G3 pi-prompt row (insert+correct+zero-diff+finalize) | **verified** at pi 1.0.2 / ghostty 1.4.0-arch2 / sway 1.12 | plan/.../architecture/pi_row_verdicts.jsonl (all `passed:true`) |
| G3 GTK editor rows (insert + 20-sentence correction) | **verified** | editor_browser_row_verdicts.jsonl (rows pass, oracle: 1 transition, no transient hashes) |
| G3 browser field: INSERT verified (1 op/change); CORRECTION **refused** at chromium | **verified, with honest limit** | editor_browser_row_verdicts.jsonl `browser-firstword-20sent`: `correction_first: REFUSED (recheck: caret moved)` — surrounding_text lags; caret guard can't confirm ownership |
| Field-class matrix (2026-11-23, installed versions) | **verified mechanism rows** | g3_field_matrix.md: foot 1.28.0-2 insert-only; kitty 0.51.0-1 insert-only; ghostty 1.4.0-2 **blocked** (activate not_activated); Hyprland relay 0.57.2 blocked-in-lab (nested boot fails; never tested live) |
| G4 clipboard gate | L1 **unprovable** (watcher active → adapter refuses, honest); L2–L6 verified | g4_clipboard_verdicts.jsonl |
| G5 timing (speech-end→word-visible etc.) | **pending** — P1.M6.T4.S1 implementing; tests/G5_TIMING_EVIDENCE.md may or may not exist at doc time | reference only what the file records |
| G6 graduation / default flip | **pending** — parallel P1.M7.T1.S1; expected STAY OPT-IN (operator sessions evidence can't be automated; template ships EMPTY) | tests/G6_GRADUATION.md (produced by that task) |
| Speech-to-visible latency, live-desktop coverage, "works on Wayland" | **NEVER claim** | R.2: "No operator acceptance on record" |

## 3. Seat IM exclusivity (troubleshooting item)
- One input-method client per wl_seat. ime/manager.py:23 "user's fcitx5 is explicitly forbidden";
  :151 "during starting (fcitx5 holds the seat) -> False with state UNSUPPORTED".
- User guidance: if fcitx5/ibus is running, the IM-v2 route reports `delivery: bulk-text (unsupported)`
  with the reason; stop the IME (or use stream-edit) to arm bulk-text on GTK-class fields.
- Compositor must advertise `zwp_input_method_manager_v2` (ime_host.py:72 raises otherwise).

## 4. README insertion map (current section order, with anchors)
1. First run — add ONE sentence: playing media pauses at arm / resumes at stop (default mpris) + link.
2. Upgrading from Rev 1 — "six commands" → seven (+ `session`).
3. NEW `## Media ducking while listening` — after `### Backspace-cancel…`, before `## Feedback surfaces`.
4. NEW `## Bulk text delivery (opt-in, experimental)` — after ducking section.
5. Feedback surfaces — add `ducked` + delivery_* fields to the state.json field list.
6. Configuration table — add rows `audio.duck_mode`, `audio.duck_volume_pct` (new [audio] group),
   `output.delivery` (after `output.streaming` row). NOTE: README's "Voice-activity constants are NOT
   config keys" subsection claims compute_type is not a config key while config.toml:23 ships
   `compute_type` — pre-existing drift, owned by P1.M7.T2.S3's sweep; FLAG in the commit message,
   do NOT fix here (scope discipline).
7. NEW troubleshooting subsections (after `### wtype vs ydotool`):
   `### Bulk delivery: input-method seat is taken (fcitx5/ibus)`;
   `### Bulk delivery: what my terminal/editor supports (field-class matrix)`;
   `### Bulk delivery: the clipboard fallback contract`.
8. Logs, status — status sample gains the `delivery:` line(s).

## 5. G6-verdict conditional (the parallel-task contract)
P1.M7.T1.S1 produces tests/g6_assessment.py, tests/test_g6_assessment.py,
tests/G6_WRITING_SESSIONS.md (EMPTY), tests/G6_GRADUATION.md, and (flip path only) the lockstep
default change. It explicitly does NOT touch README (this task owns docs). Our README:
- MUST read `tests/G6_GRADUATION.md` at implementation time and frame the bulk section per its
  `G6 DECISION:` line verbatim.
- STAY OPT-IN (expected): bulk = opt-in + "unverified until G6" framing, default stays stream-edit,
  point at the assessment doc + the empty sessions template as the outstanding input.
- FLIP (only if the doc says FLIP): default becomes bulk-text; document the graduated claims WITH
  the assessment as evidence pointer; still never claim "works on Wayland" categorically.
- If `tests/G6_GRADUATION.md` is ABSENT at implementation time: that is a blocking dependency —
  report it; do not guess the verdict.

## 6. Voice/style constraints (match the existing README)
Terse, exact commands with absolute `.venv/bin/voicectl` paths, tables for config, "you"-addressed,
every claim tied to a knob/file/log line; section anchors used in cross-links; no marketing prose.
Config table row format: `| \`section.key\` | \`default\` | description |`.

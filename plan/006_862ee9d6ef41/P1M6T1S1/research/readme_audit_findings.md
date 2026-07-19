# README audit findings — P1.M6.T1.S1

Pre-verification of README.md against PRD §7 #7 + the item's 8-point checklist (a–h). This is the
research backing the PRP. All README claims below were cross-checked against the LIVE source
(`voice_typing/config.py` schema, `hypr-binds.conf`, `status.sh`) + the 17 `architecture/gap_*.md`
audits (which already cross-read README). Conclusion: **README is COMPLETE and ACCURATE — verdict
PASS; the deliverable is primarily `gap_readme.md` (the audit evidence dossier), with README either
unchanged or receiving only optional minor polish.**

## §1 — The spec being audited (two layers)

**Layer A — PRD §7 #7 (the literal acceptance criterion):**
> "Everything committed to git; README documents: install, hotkey snippet, tmux status snippet,
> config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to
> switch to CPU-only mode."

**Layer B — the item's 8-point checklist (RESEARCH NOTE + LOGIC), which expands #7 with the evolved
PRD's new surfaces (lite mode, idle lifecycle):**
- (a) install instructions (portaudio, uv sync, install.sh)
- (b) hotkey snippet (source hypr-binds.conf)
- (c) tmux status snippet (status.sh or inline jq)
- (d) config tuning table with key knobs (post_speech_silence_duration, silero_sensitivity, lite thresholds)
- (e) troubleshooting: cuDNN libs (LD_LIBRARY_PATH wrapper), PyAudio device (input_device_index), wtype vs ydotool
- (f) CPU-only mode (device=cpu in config)
- (g) first-run guide matching T5
- (h) lite mode documentation (toggle-lite, Alt+Super+D)

**Scope boundary (what this task does NOT own):** the literal "everything committed to git" half of
#7 → **P1.M6.T1.S3**; stale BUGS.md / VT-* references (VT-001 doc-drift) → **P1.M6.T1.S2**. This task
owns ONLY the README-completeness half + `gap_readme.md`.

## §2 — 8-point audit matrix (README section → line → verdict → evidence)

README headings (live `grep -nE '^#{1,3} ' README.md`):

| # | Checklist item | README section (line) | Verdict | Evidence / cross-check |
|---|---|---|---|---|
| a | install: portaudio + uv sync + install.sh | `## Install` (L23) | ✅ PASS | L26 `./install.sh`; L30–46 the 7 numbered install.sh steps incl. (1) portaudio `pacman -Q` check + abort msg, (2) `uv sync`, (3) CUDA smoke, (4) prefetch, (5) systemd install, (6) XDG config copy, (7) print snippets. Matches `architecture/gap_install.md` (PASS, 15 tests). |
| b | hotkey snippet: source hypr-binds.conf | `## Hotkey (Hyprland)` (L79) | ✅ PASS | L87 `source = /home/<you>/projects/voice-typing/hypr-binds.conf`; L101–102 BOTH binds verbatim (`CTRL SUPER ALT, D ... toggle` + `SUPER ALT, D ... toggle-lite`); L83 "the repo never edits your hyprland.conf". Cross-checked `gap_hypr_binds.md` (README:79/87/101/102 MATCH hypr-binds.conf + install.sh). |
| c | tmux status snippet: status.sh | `## tmux status line` (L135) | ✅ PASS | L141–142 the 2-line snippet (`set -g status-interval 1` + `status-right "#(.../status.sh)"`) referencing status.sh (NOT inline jq). Cross-checked `gap_status_sh.md` (README:141-142 MATCH status.sh header; Mode B ✅). |
| d | config tuning table: key knobs incl. lite thresholds | `## Configuration` (L152) | ✅ PASS | L159–177 the real TABLE. Covers `post_speech_silence_duration` (0.6), `lite_post_speech_silence_duration` (0.5), `realtime_processing_pause`, `auto_stop_idle_seconds`, `auto_unload_idle_seconds`, `device`, `final_model`/`realtime_model`/`lite_model`, `language`, `output.*`, `feedback.notify_on_final`/`notify_ms`, `filter.*`, `log.level`. ALL defaults match `config.py` (§3 below). L184–200 explicitly documents `silero_sensitivity`/`webrtc_sensitivity`/`silero_backend`/`compute_type` are NOT config keys (correct — they are `_FIXED_KWARGS` constants in daemon.py). |
| e | troubleshooting: cuDNN + PyAudio device + wtype/ydotool | `## Troubleshooting` (L229) | ✅ PASS | `### cuDNN load error` (L231): LD_LIBRARY_PATH wrapper (`launch_daemon.sh`), triage cmds (LD_DEBUG/ldd), "do not bake Environment=" + CPU auto-fallback. `### Wrong microphone` (L258): default-source model + `pactl` cmds + the `mic:` health line (PyAudio probe). `### wtype vs ydotool` (L276): auto-fallback + ydotoold + force-backend config. |
| f | CPU-only mode: device=cpu | `## CPU-only mode` (L202) | ✅ PASS | L209–228 all THREE paths: (1) force `device="cpu"` in config → int8; (2) auto-fallback (0 CUDA devices → small.en/tiny.en); (3) construction-failure fallback (cuDNN init fail → CPU retry). + the `voicectl status` device line. |
| g | first-run guide matching T5 | `## First run` (L50) | ✅ PASS (see §4 nuance) | L57–67 the exact T5 sequence: `systemctl --user start voice-typing`, `voicectl toggle` (arms), speak, watch tmux status, `voicectl toggle` (disarms). + expected behavior + "a pause does not end the session". + the loading hint (~1–3 s first arm). |
| h | lite mode: toggle-lite, Alt+Super+D | `## Lite mode` (L118) + `## Hotkey` (L79) | ✅ PASS | L120–133: lite loads ONLY `small.en` (~half VRAM, faster finals, lower acc), own shorter silence threshold, `toggle-lite`/`start-lite` cmds, Alt+Super+D bind, mode-switch reload (~1–3 s), shared drain/auto-stop/idle-unload, `mode:` in status/state.json/tmux (⚡ prefix). |

**Verdict: 8/8 PASS.** Plus bonus sections that exceed the spec: `### Model lifecycle & VRAM` (L332,
the §4.2bis lazy-load + idle-unload story), `## Logs, status, stopping` (L286), and the type-
validation note (config rejects wrong-type values).

## §3 — Config-table ↔ config.py lockstep cross-check (no drift)

Every README table row's default was checked against `voice_typing/config.py` dataclass defaults:

| README table key | README default | config.py default | Match |
|---|---|---|---|
| asr.post_speech_silence_duration | 0.6 | 0.6 | ✅ |
| asr.lite_post_speech_silence_duration | 0.5 | 0.5 | ✅ |
| asr.realtime_processing_pause | 0.15 | 0.15 | ✅ |
| asr.auto_stop_idle_seconds | 30.0 | 30.0 | ✅ |
| asr.auto_unload_idle_seconds | 1800.0 | 1800.0 | ✅ |
| asr.device | "cuda" | "cuda" | ✅ |
| asr.final_model / realtime_model / lite_model | distil-large-v3 / small.en / small.en | same | ✅ |
| output.backend / tmux_target / append_space | wtype / "" / true | same | ✅ |
| feedback.notify_on_final / notify_ms | true / 2500 | True / 2500 | ✅ |
| filter.min_chars / blocklist | 2 / list | 2 / list | ✅ |
| log.level | "INFO" | "INFO" | ✅ |

**Zero drift.** (Verified the dataclasses: AsrConfig L48, OutputConfig L118, FeedbackConfig L127,
FilterConfig L177, LogConfig L203, VoiceTypingConfig L215.)

## §4 — Correct divergences from the item checklist (NOT gaps — document them)

These are places the README intentionally differs from the literal PRD/checklist wording because the
codebase EVOLVED. They are CORRECT; the audit must NOT "fix" them:

1. **(d) `silero_sensitivity` is listed in the checklist but is NOT a config key.** The README is
   RIGHT to document it under "### Voice-activity constants are NOT config keys" (L184) as a
   `_FIXED_KWARGS` constant in daemon.py, not a tunable. The checklist's mention predates the
   silero_use_onnx → silero_backend="auto" + constants-not-config decision (delta_prd §1 item 2).
   Adding it to the tuning table would mislead users (config.py rejects unknown keys → crash-loop).
2. **(g) First-run "two knobs" diverges from PRD T5.** PRD T5 says the two knobs are
   `post_speech_silence_duration, silero_sensitivity`. README (L75–77) says they are "the microphone
   default source (Troubleshooting) and post_speech_silence_duration (Configuration)". This is MORE
   accurate + actionable: silero_sensitivity isn't tunable via config (see #1), and the mic default
   source is the #1 real first-run failure. Correct divergence — do NOT revert.
3. **(e) `input_device_index` is listed in the checklist but is NOT a user config.** It is the
   RealtimeSTT recorder kwarg used by the T3 E2E TEST (to point at a virtual-sink monitor), left
   UNSET in production → PipeWire default source. The README correctly documents the user-facing path
   (default source + `pactl set-default-source` + the `mic:` health line). Mentioning input_device_index
   as a user knob would be wrong. PyAudio IS mentioned (the `mic:` health probe "the daemon's PyAudio
   probe found no input device", L264).

## §5 — Optional, NON-BLOCKING polish (judgment call for the implementer; not required for PASS)

1. **`feedback.hypr_notify` and `feedback.state_file` have no dedicated table rows.** Both ARE config
   fields. `hypr_notify` is referenced in the `notify_ms` row ("hypr_notify is the master on/off
   switch") and `state_file` is referenced in the tmux section (the resolved `$XDG_RUNTIME_DIR/.../state.json`
   path). The table is explicitly "Real tunable keys" (curated), and these are arguably not tuning
   knobs (state_file's default is "use XDG"; hypr_notify is a master on/off). **Not a gap** — but if
   the implementer wants the table to be an EXHAUSTIVE field enumeration, adding a one-line
   `feedback.hypr_notify | true | master on/off for ALL hyprctl popups (set false to suppress the
   start/stop toasts too)` row would close the implicit gap. Low priority; skip if unsure.
2. **Line-number drift guard.** The acceptance gate (P1.M5.T5.S1) cites README sections at specific
   lines (L23/L79/L118/...). Lines are stable as of this read but the audit MUST re-grep live
   (`grep -nE '^#{1,3} ' README.md`) and cite the CURRENT numbers, not the PRP's, in `gap_readme.md`.

## §6 — Validation approach (documentation task; no pytest/heavy scripts)

This is a doc-audit task. The gates are: (1) grep-based completeness (every required section +
keyword present); (2) config-table ↔ config.py lockstep (§3, re-run the diff); (3) markdown sanity
(no broken anchors, placeholder `<you>` consistent); (4) a clean `git diff` if README is edited
(surgical, no accidental reflow). NO pytest, NO heavy shell scripts (AGENTS.md). The deliverable is
`gap_readme.md` (the evidence dossier) + README unchanged-or-surgically-polished.
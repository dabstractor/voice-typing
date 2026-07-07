# Research Notes — P2.M1.T2.S1 README.md

**Method:** first-hand reads of every artifact the README must document (install.sh, config.toml,
config.py, status.sh, ctl.py, daemon.py, launch_daemon.sh, cuda_check.py, typing_backends.py,
feedback.py, systemd unit, hypr-binds.conf PRP, research_faster_whisper_cuda.md, system_context.md).
For a documentation task the codebase IS the source of truth, so this is more accurate than
delegating to re-search subagents. The one external check (write-tech-docs prose rules) is below.

---

## 1. CRITICAL DISCREPANCY — `silero_sensitivity` is NOT a config key

The item contract + PRD §6 T5 both name "the two tunables that matter: `post_speech_silence_duration`,
`silero_sensitivity`." But only the FIRST is user-tunable in this codebase:

- `post_speech_silence_duration` → real `[asr]` key in `config.toml` + `config.py:AsrConfig`.
- `silero_sensitivity` → **hardcoded** in `voice_typing/daemon.py:_FIXED_KWARGS` (`= 0.4`). It is
  NOT in `config.toml`, NOT in `config.py:AsrConfig`.

**Why this matters (the README landmine):** `config.py:VoiceTypingConfig.from_toml()` overlays each
TOML table onto its dataclass with `section_cls(**section)`, so an UNKNOWN key raises `TypeError`.
The config.toml header even says: "Unknown keys are REJECTED at load time (a typo raises an error
instead of being silently ignored)." If the README says "tune `silero_sensitivity` in config.toml",
a user who does it crashes the daemon at load (TypeError: unexpected keyword argument). The
daemon's `main()` catches the load failure, logs "failed to load config; exiting", returns 1, and
systemd `Restart=on-failure` loops it forever.

**README contract (truthful split):**
- "Config tuning" table lists ONLY real `config.toml` keys.
- A separate short note: `silero_sensitivity` (VAD voice detection threshold), `webrtc_sensitivity`,
  `min_length_of_recording`, `min_gap_between_recordings`, `silero_backend` are CODE-ONLY constants
  in `voice_typing/daemon.py` (`_FIXED_KWARGS`). To change them, edit that file and restart the
  daemon. Do NOT add them to config.toml (load will fail).

The full `_FIXED_KWARGS` dict (verbatim, the code-only tunables):
```python
_FIXED_KWARGS = {
    "enable_realtime_transcription": True,
    "use_main_model_for_realtime": False,
    "min_length_of_recording": 0.3,
    "min_gap_between_recordings": 0.0,
    "silero_sensitivity": 0.4,
    "webrtc_sensitivity": 3,
    "silero_backend": "auto",
    "spinner": False,
    "use_microphone": True,
    "ensure_sentence_starting_uppercase": False,
    "ensure_sentence_ends_with_period": False,
}
```

---

## 2. Verified verbatim strings the README copies (do NOT rephrase)

### install.sh prints (the "Mode A" doc surface; README mirrors these)
- usage: `$REPO/.venv/bin/voicectl toggle|start|stop|status|quit`
- tmux (two lines):
  ```
  set -g status-interval 1
  set -g status-right "#(/home/dustin/projects/voice-typing/voice_typing/status.sh)"
  ```
- hypr (install.sh:137, byte-identical to hypr-binds.conf's source line):
  `source = /home/dustin/projects/voice-typing/hypr-binds.conf`
- logs: `journalctl --user -u voice-typing -f`
- config path: `$XDG_CONFIG_HOME/voice-typing/config.toml` (default `~/.config/voice-typing/config.toml`)

NOTE: install.sh:136 currently says "after P2.M1 creates hypr-binds.conf". P2.M1.T1.S1 (parallel)
edits THAT line to present-tense; line 137 (`source = $REPO/hypr-binds.conf`) stays byte-identical.
The README copies the FINAL state, so the hypr lead-in reads as if the file already exists.

### hypr-binds.conf (from P2.M1.T1.S1 PRP contract — the README's canonical source)
- bind line: `bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle`
- source line: `source = /home/dustin/projects/voice-typing/hypr-binds.conf`
- precedence: Hyprland uses the LAST matching bind → source it at the bottom of hyprland.conf;
  if SUPER+ALT+D collides, rebind (e.g. SUPER ALT, V).

### voicectl status output (exact format, ctl.py:format_result)
```
listening: on
partial: <live partial text>
last: <last finalized text>
uptime: 42.3s
device: cuda (float16)
models: distil-large-v3 + small.en
```
CPU fallback shows: `device: cpu (int8)` and `models: small.en + tiny.en`.

### voicectl exit codes: 0 success, 1 logical failure, 2 daemon not running.

---

## 3. Config tuning table — the real (config.toml) knobs

From config.toml + config.py (defaults in parens):
- `[asr] final_model` ("distil-large-v3") — model whose output gets typed.
- `[asr] realtime_model` ("small.en") — fast model for live partial previews.
- `[asr] language` ("en").
- `[asr] device` ("cuda"|"cpu") — auto-falls-back to cpu if ctranslate2 sees no CUDA device.
- `[asr] post_speech_silence_duration` (0.6) — silence seconds before a final is emitted.
- `[asr] realtime_processing_pause` (0.15) — partial cadence.
- `[output] backend` ("wtype"|"ydotool"|"tmux") — wtype auto-falls-back to ydotool.
- `[output] tmux_target` ("") — used only when backend="tmux", e.g. "voicetest:0.0".
- `[output] append_space` (true) — trailing space after each final.
- `[feedback] hypr_notify` (true), `notify_ms` (2500), `state_file` ("").
- `[filter] min_chars` (2), `blocklist` ([classic whisper hallucinations]).
- `[log] level` ("INFO"|"DEBUG").

---

## 4. CPU-only mode (PRD §4.4; daemon.py:_resolve_device_config + cuda_check.py)
- Set `[asr] device = "cpu"` in config.toml. daemon.py derives `compute_type="int8"` from device=="cpu".
- Auto path: if ctranslate2 sees 0 CUDA devices at startup, cuda_check.CPU_FALLBACK overrides to
  device=cpu, compute_type=int8, final_model=small.en, realtime_model=tiny.en (regardless of config).
- `voicectl status` reports the resolved device/models (so a forced-cpu-with-cuda-present keeps the
  large model; an auto-fallback shows the small models).
- Known limitation (cuda_check docstring): get_cuda_device_count() probes the DRIVER only, not
  cuDNN. A missing libcudnn_ops.so.9 still yields "cuda-ok" and fails later at WhisperModel load.

---

## 5. Troubleshooting facts (each must appear in the README, PRD §7.7)

### cuDNN / "cannot load libcudnn_ops.so.9" (also libcudnn.so.9, libcublas.so.12)
faster-whisper/ctranslate2 load cuDNN 9 from the nvidia-*-cu12 wheels; cuDNN 9's split sub-libs
(libcudnn_ops/cnn/eng) have no $ORIGIN RUNPATH so they MUST be on LD_LIBRARY_PATH, which the
dynamic linker reads ONLY at exec. systemd ExecStart → `voice_typing/launch_daemon.sh` exports it
before exec'ing python. DO NOT add `Environment=LD_LIBRARY_PATH=` to the unit (the unit comment says
so; it would go stale on `uv sync`). Triage (from launch_daemon.sh header, fastest first):
1. `journalctl --user -u voice-typing -e`
2. `systemctl --user show voice-typing -p Environment` (returns empty by design; the wrapper sets it)
3. `LD_DEBUG=libs voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn`
4. `ldd .venv/lib/python3.12/site-packages/nvidia/cudnn/lib/libcudnn.so.9` (look for "not found")
5. `strace -f -e openat voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn`
Then `systemctl --user restart voice-typing`.

### PyAudio / wrong microphone
daemon.py does NOT pass `input_device_index` (not in _FIXED_KWARGS, not in cfg_to_kwargs) →
RealtimeSTT/PyAudio uses the system default input = the PipeWire/PulseAudio default source.
To change the mic, change the default source (NOT a config key):
- `pactl list short sources` (find the source)
- `pactl set-default-source <name>`
- `pactl set-default-source alsa_input.usb-Sonix_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-02.mono-fallback`
  (the webcam mic; system_context.md calls it the accuracy ceiling)
Then restart the daemon. (PRD §2: webcam mic is the only real mic; use the default source.)

### wtype vs ydotool (typing backends)
default `[output] backend = "wtype"` (Wayland virtual-keyboard-v1). On wtype failure (nonzero exit
or missing binary → CalledProcessError/OSError) `_WtypeWithFallback` retries ONCE via ydotool and
logs a WARNING; if ydotool also fails the exception propagates (daemon logs it, on_final survives).
To force a backend: set `[output] backend = "ydotool"` (uinput; works for XWayland apps; needs
`ydotoold` running: `systemctl --user status ydotool`) or `"tmux"` (set `[output] tmux_target`).
Backends type EXACTLY the text (no trailing newline; `-l` for tmux = literal).

---

## 6. First-run smoke (PRD §6 T5 — exact steps the README must give)
```
systemctl --user start voice-typing          # install.sh already enabled+started it
/home/dustin/projects/voice-typing/.venv/bin/voicectl toggle   # arms the mic (daemon boots NOT listening)
# speak; watch the tmux status line (🎤 partials) or hyprctl popups (● listening / ✔ final)
/home/dustin/projects/voice-typing/.venv/bin/voicectl toggle   # disarms
```
Expected behavior (cite, do not over-claim): live partials in the tmux status line while speaking;
finalized text typed into the focused window shortly after you stop; a pause up to a few seconds
does not end the session (only `post_speech_silence_duration` = 0.6s triggers a final, then it
keeps listening). The two knobs to reach for if it misbehaves: `post_speech_silence_duration`
(config.toml) and `silero_sensitivity` (daemon.py:_FIXED_KWARGS — code edit, see §1).

---

## 7. Logs / status / GPU residency (supporting commands)
- status: `voicectl status` (see §2 format).
- logs: `journalctl --user -u voice-typing -f`. INFO emits a per-utterance latency line prefixed
  `voice-typing latency:` and a startup `voice-typing device resolved:` line; DEBUG adds raw
  monotonic timestamps.
- GPU residency: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` lists the daemon
  (~1-5 GB, per PRD §6 T6).
- stop/disable: `systemctl --user stop voice-typing`; `systemctl --user disable voice-typing`.

---

## 8. write-tech-docs prose rules (the README must pass these)
From /home/dustin/.pi/agent/skills/write-tech-docs/SKILL.md (hard rules, enforced by a linter):
1. NO em dashes. Use colon / parentheses / comma / period. (grep for the em-dash chars.)
2. NO marketing tell-words: powerful, robust, elegant, seamless, comprehensive, cutting-edge,
   revolutionary, leverage, utilize, unlock, empower, supercharge, transform, streamline, elevate,
   delve, lightweight (unmeasured), blazing-fast, etc.
3. NO hedging / formulaic transitions: moreover, furthermore, "in conclusion", "it's worth noting",
   excess perhaps/maybe/likely/tends to.
4. Do NOT narrate the codebase. Document what the code cannot show: what it is, why, how to use,
   gotchas. No file-by-file walkthrough.
5. Concision: no prose paragraph over ~100 words; prefer lists/tables/code; front-load the answer.
6. Lint: `bash /home/dustin/.pi/agent/skills/write-tech-docs/scripts/lint.sh <file>` until exit 0.
PRD also says "keep README short and credible (no marketing tone)". Target ≤ ~200 lines.

---

## 9. Scope / boundary facts
- README.md does NOT exist yet (confirmed: `ls README.md` → no such file). .gitignore does NOT
  ignore README.md (good).
- PRD §7 criterion 7 enumerates the REQUIRED sections (install, hotkey, tmux status, config tuning
  table, troubleshooting [cuDNN/PyAudio/wtype-vs-ydotool], CPU-only mode). The item contract adds a
  "First run" section (PRD §6 T5). These seven are the must-haves; anything else is optional/short.
- The README must NOT fabricate acceptance-test evidence (criteria 1-6,8 are satisfied by the test
  suite P1.M7, not by the README). The README documents the user-facing commands.
- This is Mode B (changeset-level doc sync). No other docs subtask exists. README + this note are it.

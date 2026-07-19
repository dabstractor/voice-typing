# README completeness audit — P1.M6.T1.S1 (PRD §7 #7 documentation clause)

**Date:** 2026-07-18
**Verdict:** **PASS.** README satisfies PRD §7 #7's documentation clause on all 8 checklist items.
Config table has **zero drift** vs `voice_typing/config.py`. Three divergences from the literal
checklist wording are **correct-by-design** (registered in §4 — do NOT "fix"). README was **updated
with the optional `feedback.hypr_notify` row** (one surgical row added at L180; the `notify_ms` row's
trailing "`hypr_notify` is the master on/off switch" clause was moved into the new dedicated row — no
other prose churn). This closes the implicit discoverability gap where the global kill switch lived
only in a parenthetical.
Scope: this audit owns ONLY #7's docs half; the "everything committed to git" half → P1.M6.T1.S3;
stale BUGS.md / VT-001 references → P1.M6.T1.S2.

## 1. Audit spec

- **PRD §7 #7 (literal):** "Everything committed to git; README documents: install, hotkey snippet,
  tmux status snippet, config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs
  ydotool), and how to switch to CPU-only mode."
- **Item 8-point checklist (a–h):** install (portaudio/uv sync/install.sh); hotkey (source
  hypr-binds.conf); tmux (status.sh snippet); config tuning table (post_speech_silence_duration,
  silero_sensitivity handling, lite thresholds); troubleshooting (cuDNN LD_LIBRARY_PATH, PyAudio device,
  wtype vs ydotool); CPU-only (device=cpu); first-run (T5); lite mode (toggle-lite, Alt+Super+D).

## 2. 8-point audit matrix

Line numbers below are LIVE — re-grepped this round via `grep -nE '^#{1,3} ' README.md` AFTER the
surgical `feedback.hypr_notify` row edit (which shifted all sections at/after the config table by +1;
sections before L152 are unchanged from the PRP's cited numbers). Each row's evidence is a grep match,
a `voice_typing/config.py` line, or a sibling `gap_*.md` verdict.

| # | Item | README section (live line) | Verdict | Evidence |
|---|---|---|---|---|
| a | install (portaudio + uv sync + install.sh) | `## Install` (L23) | ✅ | L26 `./install.sh`; L30–46 the 7 numbered install.sh steps incl. (1) portaudio `pacman -Q` check + abort msg (L30–32), (2) `uv sync` (L33), (3) CUDA smoke (L34), (4) prefetch (L35), (5) systemd install (L36), (6) XDG config copy (L37–38), (7) print snippets (L39–41). `grep -cE '## Install\|portaudio\|uv sync' README.md` = 9 hits. Matches `architecture/gap_install.md` (PASS, 15 tests). |
| b | hotkey (source hypr-binds.conf) | `## Hotkey (Hyprland)` (L79) | ✅ | L83 "the repo never edits your hyprland.conf" (never-edit promise); L87 `source = /home/<you>/projects/voice-typing/hypr-binds.conf`; L101–102 BOTH binds verbatim (`bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` + `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite`). Level-4 `diff <(grep -E '^bind = ' hypr-binds.conf) <(grep -oE … README.md)` = MATCH. `grep -cE 'source = .*hypr-binds\.conf\|CTRL SUPER ALT, D, exec' README.md` = 2 hits. Cross-checked `architecture/gap_hypr_binds.md` (README:79/83/87/101/102 MATCH hypr-binds.conf:50/52 + install.sh; ✅). |
| c | tmux status (status.sh snippet) | `## tmux status line` (L135) | ✅ | L141–142 the 2-line snippet: `set -g status-interval 1` + `set -g status-right "#(/home/<you>/projects/voice-typing/voice_typing/status.sh)"` — references `status.sh` (NOT inline jq). Level-4 check `grep -q 'status\.sh' README.md && ! grep -q 'status-right.*jq ' README.md` = "tmux uses status.sh (correct)". `grep -cE 'set -g status-right.*status\.sh' README.md` = 1 hit. Cross-checked `architecture/gap_status_sh.md` (README:141-142 MATCH status.sh header; Mode B ✅). |
| d | config tuning table (key knobs) | `## Configuration` (L152) | ✅ | The real TABLE (L165–183, 19 rows post-edit). Covers `post_speech_silence_duration` (0.6), `lite_post_speech_silence_duration` (0.5), `realtime_processing_pause`, `auto_stop_idle_seconds`, `auto_unload_idle_seconds`, `device`, `final_model`/`realtime_model`/`lite_model`, `language`, `output.*`, `feedback.notify_on_final`/`notify_ms`/`hypr_notify`, `filter.*`, `log.level`. ALL defaults match `config.py` (§3 below, 19/19 zero-drift). L185–201 explicitly documents `silero_sensitivity`/`webrtc_sensitivity`/`silero_backend`/`compute_type` are NOT config keys (correct — they are `_FIXED_KWARGS` constants in daemon.py / derived from device). |
| e | troubleshooting (cuDNN + PyAudio + wtype/ydotool) | `## Troubleshooting` (L230) | ✅ | `### cuDNN load error (libcudnn_ops.so.9)` (L232): LD_LIBRARY_PATH wrapper (`launch_daemon.sh`), triage cmds (LD_DEBUG/ldd), "do not bake Environment=" + CPU auto-fallback. `### Wrong microphone` (L259): default-source model + `pactl` cmds + the `mic:` health line (PyAudio probe, L264). `### wtype vs ydotool` (L277): auto-fallback + ydotoold + force-backend config. `grep -cE 'cuDNN\|Wrong microphone\|wtype vs ydotool' README.md` = 8 hits (≥3 required). |
| f | CPU-only mode (device=cpu) | `## CPU-only mode` (L203) | ✅ | L209–228 all THREE paths: (1) force `device="cpu"` in config → int8 (L209–213); (2) auto-fallback (0 CUDA devices → small.en/tiny.en) (L214–217); (3) construction-failure fallback (cuDNN init fail → CPU retry) (L218–228). + the `voicectl status` device line. `grep -cE 'CPU-only mode\|device = "cpu"' README.md` = 2 hits. |
| g | first-run (T5) | `## First run` (L50) | ✅ (see §4 divergence ii) | L57–62 the exact T5 sequence: `systemctl --user start voice-typing`, `voicectl toggle` (arms), speak, watch tmux status, `voicectl toggle` (disarms). + expected behavior + "A pause does **not** end the session" + the ~1-3s first-arm loading hint. The "two knobs" line (L75–77) intentionally diverges from PRD T5 — see §4 divergence ii. `grep -cE 'systemctl --user start voice-typing\|voicectl toggle' README.md` = 9 hits. |
| h | lite mode (toggle-lite, Alt+Super+D) | `## Lite mode` (L118) + `## Hotkey` (L79) | ✅ | L120–133: lite loads ONLY `small.en` (~half VRAM, faster finals, lower acc), own shorter silence threshold (`lite_post_speech_silence_duration` 0.5 vs 0.6), `toggle-lite`/`start-lite` cmds, Alt+Super+D bind, mode-switch reload (~1–3 s), shared drain/auto-stop/idle-unload, `mode:` in `voicectl status`/`state.json`/tmux (⚡ prefix). `grep -cE 'toggle-lite\|Alt\+Super\+D' README.md` = 7 hits. |

**Verdict: 8/8 PASS.** Bonus sections that exceed the spec: `### Model lifecycle & VRAM` (L333, the
§4.2bis lazy-load + idle-unload story), `## Logs, status, stopping` (L287), and the type-validation
note (config rejects wrong-type values, L193–200).

## 3. Config-table ↔ config.py lockstep (zero drift)

Every README table row's default was checked against `voice_typing/config.py` dataclass defaults.
Re-run live this round via `grep -nE '^\| \(asr|output|feedback|filter|log\)\.' README.md` (19 rows
post-edit) cross-checked against `grep -nE '^\s+(\w+): .* = ' voice_typing/config.py`. The oracle
dataclasses: `AsrConfig` (L48), `OutputConfig` (L121), `FeedbackConfig` (L130), `FilterConfig` (L179),
`LogConfig` (L210).

| README table key | README default | config.py default (line) | Match |
|---|---|---|---|
| `asr.post_speech_silence_duration` | `0.6` | `0.6` (L58) | ✅ |
| `asr.lite_post_speech_silence_duration` | `0.5` | `0.5` (L59) | ✅ |
| `asr.realtime_processing_pause` | `0.15` | `0.15` (L64) | ✅ |
| `asr.auto_stop_idle_seconds` | `30.0` | `30.0` (L65) | ✅ |
| `asr.auto_unload_idle_seconds` | `1800.0` | `1800.0` (L67) | ✅ |
| `asr.device` | `"cuda"` | `"cuda"` (L57) | ✅ |
| `asr.final_model` | `"distil-large-v3"` | `"distil-large-v3"` (L52) | ✅ |
| `asr.realtime_model` | `"small.en"` | `"small.en"` (L53) | ✅ |
| `asr.lite_model` | `"small.en"` | `"small.en"` (L54) | ✅ |
| `asr.language` | `"en"` | `"en"` (L56) | ✅ |
| `output.backend` | `"wtype"` | `"wtype"` (L122) | ✅ |
| `output.tmux_target` | `""` | `""` (L123) | ✅ |
| `output.append_space` | `true` | `True` (L124) | ✅ |
| `feedback.notify_on_final` | `true` | `True` (L134) | ✅ |
| `feedback.notify_ms` | `2500` | `2500` (L133) | ✅ |
| `feedback.hypr_notify` | `true` | `True` (L132) | ✅ (NEW row added this task; default matches) |
| `filter.min_chars` | `2` | `2` (L180) | ✅ |
| `filter.blocklist` | list | `list[str]` default_factory (L184) | ✅ |
| `log.level` | `"INFO"` | `"INFO"` (L211) | ✅ |

**Zero drift (19/19).** The README `true`/`false` literals are TOML casing for the Python `True`/`False`
bool defaults — semantically identical (tomllib parses bare `true`/`false` as bool). No row drifted;
no mandatory drift fix was required. (Pre-edit the table had 18 rows; the `feedback.hypr_notify` row
was added as the optional §5 polish — its default was verified to match config.py L132 before commit.)

## 4. Correct divergences (NOT gaps — do not "fix")

These are places the README intentionally differs from the literal PRD §7 / checklist wording because
the codebase EVOLVED. Registering them here IS part of the deliverable — a future maintainer reading
the PRD and "fixing" the README to match it literally would BREAK the README's accuracy.

1. **(d) `silero_sensitivity`** is listed in the checklist's config-tuning item but is **NOT a config
   key.** It is a `_FIXED_KWARGS` constant in `voice_typing/daemon.py`. README correctly documents it
   under `### Voice-activity constants are NOT config keys` (L185) alongside
   `webrtc_sensitivity`/`min_length_of_recording`/`min_gap_between_recordings`/`silero_backend`.
   `compute_type` is likewise NOT a config key (derived from `device` — `float16` on cuda, `int8` on
   cpu). The checklist's `silero_sensitivity` mention predates the `silero_use_onnx → silero_backend='auto'`
   + constants-not-config decision (`delta_prd.md` §1 item 2). Adding it to the tuning table would
   mislead users: `config.py`'s `from_toml` rejects unknown keys with `TypeError` → systemd's
   `Restart=on-failure` loops the daemon forever. Do NOT add it.
2. **(g) First-run "two knobs"** = the microphone default source (Troubleshooting) +
   `post_speech_silence_duration` (Configuration) — README L75–77. PRD T5 says the two knobs are
   `post_speech_silence_duration, silero_sensitivity`. README is **MORE accurate + actionable**:
   `silero_sensitivity` isn't tunable via config (see #1), and the mic default source is the #1 real
   first-run failure (a changed PipeWire default source silently captures the wrong device). Correct
   divergence — do NOT revert to the PRD T5 wording.
3. **(e) `input_device_index`** is listed in the checklist's troubleshooting item (PyAudio device) but
   is **NOT a user config.** It is the RealtimeSTT recorder kwarg used by the T3 E2E TEST (to point at
   a virtual-sink monitor), left UNSET in production → PipeWire default source. README correctly
   documents the user-facing path (default source + `pactl set-default-source` + the `mic:` health
   line, L259–272). Mentioning `input_device_index` as a user knob would be wrong. PyAudio IS
   mentioned — the `mic:` health probe "the daemon's PyAudio probe found no input device" (L264).

## 5. Optional polish (non-blocking; routed)

- **`feedback.hypr_notify`** had no dedicated table row pre-edit (the table is a curated "Real
  tunable keys" set; `hypr_notify` was referenced only in the `notify_ms` row's parenthetical
  "hypr_notify is the master on/off switch"). **APPLIED this task:** added ONE dedicated row at L180
  — `\| feedback.hypr_notify \| true \| master on/off for ALL hyprctl popups …\|` — because it is the
  global kill switch and its only prior documentation was a parenthetical inside another row's
  description (a genuine discoverability gap for a user wanting to suppress ALL popups). The
  `notify_ms` row's trailing clause was removed (moved into the new row) to avoid duplication.
  Default verified to match `config.py` L132 (`hypr_notify: bool = True`). `git diff README.md` is
  surgical: 2 insertions, 1 deletion, one row added, no prose reflow.
- **`feedback.state_file`** still has no dedicated table row (default `""` → resolved lazily to
  `$XDG_RUNTIME_DIR/voice-typing/state.json`). It is referenced in the `## tmux status line` section
  (the resolved state.json path). **Not applied:** `state_file`'s default is "use XDG" (not a tuning
  knob); adding a row would be exhaustive-enumeration churn without a discoverability payoff (the XDG
  resolution is documented where it's consumed). Low priority; does not affect the PASS.

## 6. Scope

- **IN scope (this task):** README-completeness audit + `gap_readme.md` + the optional surgical
  `feedback.hypr_notify` README row.
- **OUT of scope (cited, not duplicated):**
  - The literal "everything committed to git" half of PRD §7 #7 → **P1.M6.T1.S3** (commit readiness).
    This audit does NOT judge git cleanliness or create the final integration commit.
  - Stale BUGS.md / VT-001 doc-drift references → **P1.M6.T1.S2** (stale-reference hygiene). This
    audit confirms the README CONTENT is complete; S2 owns the stale-ref sweep without re-auditing
    content.
- **No source/test/script edit.** No `voice_typing/*.py`, `tests/*`, `*.sh`, `config.toml`,
  `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or other `plan/` file was touched. No
  pytest, no heavy shell script (`test_idle_and_gpu.sh` / `e2e_virtual_mic.sh` forbidden per AGENTS.md
  and irrelevant to a README audit). The only commands run were `grep`, `diff`, and `git diff` (fast,
  safe, no timeout needed).
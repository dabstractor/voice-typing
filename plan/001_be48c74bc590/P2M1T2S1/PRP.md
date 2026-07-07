# PRP — P2.M1.T2.S1: Write README.md (install, hotkey, tmux status, config tuning, troubleshooting, CPU mode, first-run)

> **Scope reminder.** This is a **single new file** deliverable: **CREATE** `README.md` at the repo
> root (`/home/dustin/projects/voice-typing/README.md`). It is the user-facing entry document and the
> FINAL task of the changeset (SOW §5 Mode B). It consumes the outputs of every implementing subtask
> (install.sh, config.toml, status.sh, hypr-binds.conf, the daemon, voicectl, the systemd unit) but
> modifies NONE of them. No Python, no tests, no config edits, no .gitignore. PRD §7 criterion 7 is
> the contract: the README must document exactly seven things (enumerated in Success Criteria). PRD
> also says "keep README short and credible (no marketing tone)".

## Goal

**Feature Goal**: Ship a **short, credible** `README.md` at the repo root that takes a fresh-clone
reader (and dustin, six months from now) from "what is this" to "I ran it and it types my voice"
without reading any source. It documents exactly what PRD §7 criterion 7 enumerates, using the
verbatim commands and snippets the rest of the changeset already produces (install.sh's printed
snippets, hypr-binds.conf's source line, status.sh's tmux lines), and it honestly distinguishes
config-tunable knobs from code-only constants (the `silero_sensitivity` landmine, see Context).

**Deliverable** (1 file — ADD only; **zero** other changes):
- `README.md` at repo root. Markdown, UTF-8, LF. Roughly 120-200 lines. Plain, imperative,
  evidence-first prose. No em dashes, no marketing tell-words, no codebase narration (the
  `write-tech-docs` hard rules; see Validation). It contains the seven required sections in the
  order below. Every command and snippet is real and runnable on this machine.

**Success Definition** (the README "definition of done"; maps 1:1 to PRD §7 criterion 7 + §6 T5):
- (a) **Install** section: `./install.sh` from the repo root, with the portaudio prereq and a one-line
  list of what install.sh does (uv sync → CUDA smoke → prefetch models → install+enable+start the
  systemd user unit → copy config.toml to XDG → print usage). (PRD §7.7 "install".)
- (b) **First run** section: the exact PRD §6 T5 smoke steps (`systemctl --user start voice-typing`;
  `voicectl toggle`; speak; watch tmux status; `voicectl toggle`) with the FULL voicectl path, the
  expected behavior, and the two knobs to reach for.
- (c) **Hotkey** section: the `source = /home/dustin/projects/voice-typing/hypr-binds.conf` line
  (verbatim, byte-identical to install.sh:137 / hypr-binds.conf), the SUPER+ALT+D bind, and the
  "source it LAST" precedence note. (PRD §7.7 "hotkey snippet".)
- (d) **tmux status** section: the two `~/.tmux.conf` lines (verbatim from status.sh / install.sh)
  and what they show ("🎤 <partial>" while listening, blank when idle). (PRD §7.7 "tmux status snippet".)
- (e) **Config tuning** section: a TABLE of the real `config.toml` knobs + a short callout that
  `silero_sensitivity` (and the other VAD constants) are CODE-ONLY in `voice_typing/daemon.py`
  (`_FIXED_KWARGS`), NOT config keys, and that config.py REJECTS unknown keys (adding them crashes
  the daemon). (PRD §7.7 "config tuning table".)
- (f) **CPU-only mode** section: set `[asr] device = "cpu"`; plus the auto-fallback story and how
  `voicectl status` reports it. (PRD §7.7 "how to switch to CPU-only mode".)
- (g) **Troubleshooting** section: three named sub-sections — cuDNN (`libcudnn_ops.so.9` → the
  `launch_daemon.sh` LD_LIBRARY_PATH wrapper + the 4-step triage), PyAudio device (default source,
  `pactl set-default-source`), and wtype vs ydotool (auto-fallback; forcing a backend).
  (PRD §7.7 "troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool)".)
- (h) A short **Logs / status / stop** pointer (journalctl, `voicectl status` format, GPU residency,
  disable). Optional but expected of a user-facing README.
- (i) **No out-of-scope edits**: no change to `voice_typing/*`, `config.toml`, `systemd/*`,
  `install.sh`, `hypr-binds.conf`, `tests/*`, `pyproject.toml`, `.gitignore`, `PRD.md`, any
  `tasks.json`, any `prd_snapshot.md`.
- (j) Passes the `write-tech-docs` prose rules (no em dashes, no tell-words, no hedging) — verified
  by the grep gates in Validation (and the linter if present).

## User Persona

**Target User**: **dustin** (Arch + Hyprland + tmux; the one this was built for) re-onboarding after
time away, and a **fresh-clone** reader who wants local voice dictation into any focused Wayland
window or tmux pane. Both are technical Linux users; they want exact commands, not hand-holding.

**Use Case**:
```
git clone <repo> && cd voice-typing
./install.sh                      # syncs deps, prefetches models, starts the daemon (NOT listening)
# (add the one hypr source line + the two tmux lines, if not already)
voicectl toggle                   # arms the mic
# speak -> partials in the tmux status line; finalized text types into the focused window
voicectl toggle                   # disarms
```

**Pain Points Addressed**: the previous WhisperX attempt (1) stopped listening on a short pause and
(2) gave no live feedback. The README's "First run" + "Config tuning" sections make the "silence only
segments, never ends the session" + "live partials in tmux" behavior discoverable, and the
troubleshooting section prevents the three support tickets this kind of project always generates
(cuDNN load error, wrong mic, wtype failing in some window).

## Why

- **PRD §7 criterion 7 is the contract.** It says: "Everything committed to git; README documents:
  install, hotkey snippet, tmux status snippet, config tuning table, troubleshooting (cuDNN libs,
  PyAudio device, wtype vs ydotool), and how to switch to CPU-only mode." This item is the literal
  fulfillment of that criterion.
- **Mode B (SOW §5): this IS the changeset-level documentation sync.** There is no other docs
  subtask. The README + the inline Mode-A comments in install.sh / status.sh / hypr-binds.conf are
  the whole user-facing documentation surface. Every implementing subtask already ships a Mode-A
  header comment that prints its own snippet; the README consolidates them into one entry point.
- **The README is PRD §6 T5.** T5 ("Real-hardware smoke — cannot be automated — leave to user") is
  satisfied by the README's "First run" section telling the user exactly what to type and what to
  expect. No test covers it; the doc IS the deliverable.
- **Honesty over marketing.** The single most important accuracy duty: `silero_sensitivity` is NOT a
  config key. The PRD and the item contract both call it a "tunable", but in THIS codebase it is a
  constant in `daemon.py:_FIXED_KWARGS`, and `config.py` rejects unknown keys with `TypeError` (load
  failure → systemd restart-loop). A README that says "tune silero_sensitivity in config.toml" would
  brick the user's daemon. The README must split "config-tunable" from "code-only" truthfully.
- **Scope discipline.** One new Markdown file. It consumes (read-only) the snippets the rest of the
  changeset already produces, so it stays in lockstep without coupling. It touches no code.

## What

A plain-Markdown README at the repo root, structured for scanning (front-loaded one-liner, then
heading-per-task), with every command in a fenced code block. The seven required sections plus a
short logs/status pointer. No fabricated test results, no badges, no "Contributing" wall, no
emoji fanfare.

### Required section order (with the load-bearing content pinned)

1. **Title + one-liner.** What it is: fully-local voice typing for Linux (Wayland/Hyprland, any
   focused window, tmux panes), via RealtimeSTT (faster-whisper/CTranslate2 on CUDA). One sentence:
   what it is and who it's for. No mission statement.
2. **Requirements** (3-5 bullets): Arch-ish Linux; NVIDIA GPU (optional — runs on CPU, slower);
   Wayland/Hyprland for the default wtype backend + `hyprctl notify`; tmux (optional, for the status
   line); PipeWire. Mention `portaudio` (PyAudio dep; `pacman -Q portaudio`).
3. **Install** — see Success (a).
4. **First run** — see Success (b).
5. **Hotkey (Hyprland)** — see Success (c).
6. **tmux status line** — see Success (d).
7. **Configuration** — see Success (e): the table + the code-only callout.
8. **CPU-only mode** — see Success (f).
9. **Troubleshooting** — see Success (g).
10. **Logs, status, stopping** — see Success (h). End the doc here.

### Success Criteria

- [ ] README.md exists at repo root; ~120-200 lines; UTF-8/LF; no trailing whitespace on lines.
- [ ] All seven PRD §7.7 topics present and findable by heading.
- [ ] Every fenced command is real and runnable on this machine (full paths where the shell needs
      them: `/home/dustin/projects/voice-typing/.venv/bin/voicectl`, `/usr/bin/tmux`).
- [ ] The config tuning section honestly splits config.toml knobs from `_FIXED_KWARGS` code-only
      constants, and explicitly warns that config.py rejects unknown keys.
- [ ] The verbatim snippets (hypr source line, tmux status lines, voicectl usage) match install.sh /
      status.sh / hypr-binds.conf exactly (asserted by the grep gates in Validation).
- [ ] Passes the prose gates: zero em dashes, zero tell-words, no >100-word paragraph.

## All Needed Context

### Context Completeness Check

_Pass._ A reader with zero codebase knowledge can write this README from the PRP alone because every
load-bearing string is pinned verbatim below (the exact voicectl usage line, the exact hypr source
line, the exact two tmux lines, the exact config keys, the exact troubleshooting commands, the exact
`voicectl status` output format). The one non-obvious fact — that `silero_sensitivity` is a code
constant, not a config key, and that config.py rejects unknown keys — is stated explicitly with the
failure mode. The required section order and the prose rules (no em dashes, no tell-words) are fixed.
Every validation command is a deterministic grep executable as written.

### Documentation & References

```yaml
# MUST READ #1 — the contract: §7 criterion 7 enumerates EXACTLY what the README must contain;
#                §6 T5 defines the "First run" smoke steps; §4.5/§4.4 define the config + the
#                silero/post_speech_silence knobs; §4.6 the tmux status snippet; §4.10 the hotkey.
- file: PRD.md
  sections: "§7 (esp. 7.7), §6 T5, §4.4, §4.5, §4.6, §4.10, §8 (cuDNN/PyAudio/wtype risk rows)"
  why: "§7.7 is the definition-of-done checklist for THIS file. §6 T5 is the First-run section,
        verbatim steps. §4.4/§4.5 are the tuning-table source. §4.6 is the tmux snippet. §4.10 is
        the hotkey + 'do not auto-edit hyprland.conf'. §8 risk rows are the troubleshooting facts."
  critical: "PRD §6 T5 + the item contract call silero_sensitivity a 'tunable', but it is NOT a
             config key in this codebase — see MUST READ #6. Do not blindly copy the PRD's tuning
             framing; reflect the implemented reality (config.toml vs daemon.py:_FIXED_KWARGS)."

# MUST READ #2 — the install script. Its stdout IS the user-facing install/usage quick-start
#                (Mode A). The README mirrors install.sh's printed snippets VERBATIM (the README
#                is the consolidated copy; install.sh is the source of truth for the exact strings).
- file: install.sh
  why: "Lines 150-172 print: the voicectl usage line, the two tmux status lines, the hypr source
        line, the journalctl logs line, and the config path. Copy these strings exactly. The README
        must agree with install.sh so a user who reads the README then runs install.sh sees the
        same snippets install.sh prints."
  pattern: "Mirror the 7-step install narrative (the ==> [n/7] echo blocks, lines 60-148) as a
            short bullet list in the README's Install section."
  critical: "install.sh:136 ('Hyprland (after P2.M1 creates hypr-binds.conf)...') is being edited
             to present-tense by P2.M1.T1.S1 (parallel). install.sh:137
             ('source = $REPO/hypr-binds.conf') is byte-identical and STABLE — the README copies the
             FINAL (post-edit) lead-in phrasing and the unchanged source line. Do NOT quote the
             '(after P2.M1...)' qualifier — it is gone by the time the README ships."

# MUST READ #3 — the Hyprland hotkey file (created by P2.M1.T1.S1, parallel). The README's Hotkey
#                section copies its bind line + source line VERBATIM.
- file: plan/001_be48c74bc590/P2M1T1S1/PRP.md
  why: "Defines hypr-binds.conf's exact contents (the contract the README consumes): the bind line
        'bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle'
        and the source line 'source = /home/dustin/projects/voice-typing/hypr-binds.conf', plus the
        'source it LAST / last bind wins' precedence note and the 'we never edit your hyprland.conf'
        promise. The README lifts these verbatim."
  critical: "Treat the hypr-binds.conf produced by P2.M1.T1.S1 as already-existing and final. Do not
             duplicate its creation; only reference + copy its two load-bearing lines into the README."

# MUST READ #4 — the tmux status helper. The README's tmux section copies its two lines + explains
#                what they render.
- file: voice_typing/status.sh
  why: "The Mode-A header comment states the exact two ~/.tmux.conf lines and what they show
        ('🎤 <partial>' while listening, max 60 chars; blank when idle). The README copies the two
        lines verbatim and paraphrases the behavior."
  pattern: "status.sh resolves state.json from \$XDG_RUNTIME_DIR/voice-typing/state.json. Mention
            that the partials come from the daemon's atomic state-file writes (feedback.py) so a
            reader understands the data flow without reading the code."

# MUST READ #5 — config.toml + config.py: the schema for the tuning table. They are the single
#                source of truth for which keys ARE tunable and their defaults.
- file: config.toml
  why: "The self-documenting default config. Every key in it IS a real tunable (the README's tuning
        table mirrors these). The header comment also states the search order and that 'Unknown keys
        are REJECTED at load time' — the fact that powers the silero_sensitivity warning."
- file: voice_typing/config.py
  why: "The dataclasses + loader. AsrConfig/OutputConfig/FeedbackConfig/FilterConfig/LogConfig are
        the exhaustive list of accepted config keys. from_toml() overlays each table with
        section_cls(**section), so an unknown key raises TypeError — the exact failure mode the
        README must warn about for silero_sensitivity."
  critical: "config.py has NO silero_sensitivity / webrtc_sensitivity / min_length_of_recording /
             compute_type fields. compute_type is DERIVED from device in daemon.py (float16 if cuda,
             int8 if cpu), NOT a config key. Do not list any of these as config-tunable."

# MUST READ #6 — THE LANDMINE. daemon.py:_FIXED_KWARGS holds the VAD/silero constants that the PRD
#                calls 'tunables' but which are NOT config keys.
- file: voice_typing/daemon.py
  section: "_FIXED_KWARGS dict + cfg_to_kwargs()"
  why: "_FIXED_KWARGS hardcodes silero_sensitivity=0.4, webrtc_sensitivity=3,
        min_length_of_recording=0.3, min_gap_between_recordings=0.0, silero_backend='auto', etc.
        cfg_to_kwargs() merges these with the config-derived kwargs BEFORE construction. There is NO
        path for a user to set silero_sensitivity via config.toml."
  critical: "The README's tuning table must list ONLY config.toml keys. A separate short note must
        say: silero_sensitivity (VAD voice-detection threshold) and the other VAD constants live in
        voice_typing/daemon.py (_FIXED_KWARGS); to change them, edit that file and restart the
        daemon; do NOT add them to config.toml (config.py rejects unknown keys → daemon fails to
        load → systemd restart-loops). This is the single most important accuracy duty in the README."

# MUST READ #7 — the voicectl CLI surface + the EXACT status output format (the README's status
#                example must match what the user actually sees).
- file: voice_typing/ctl.py
  section: "format_result() + _COMMANDS"
  why: "Defines the 5 subcommands (toggle|start|stop|status|quit), the exit codes (0 ok / 1 logical
        failure / 2 not running), and the EXACT status output:
          listening: on
          partial: <text>
          last: <text>
          uptime: <n>s
          device: cuda (float16)
          models: distil-large-v3 + small.en
        CPU fallback shows 'device: cpu (int8)' and 'models: small.en + tiny.en'. The README's
        status example must reproduce this format exactly."

# MUST READ #8 — the cuDNN troubleshooting facts (the launch wrapper + the triage steps).
- file: voice_typing/launch_daemon.sh
  why: "The header comment is the authoritative troubleshooting text for 'cannot load
        libcudnn_ops.so.9': WHY (cuDNN 9 split sub-libs, no RUNPATH, LD_LIBRARY_PATH read only at
        exec), the wrapper's role (systemd ExecStart → this script exports LD_LIBRARY_PATH before
        exec'ing python), and the 5-step triage (journalctl; systemctl show -p Environment;
        LD_DEBUG=libs ... | grep cudnn; ldd libcudnn.so.9; strace). The README's cuDNN subsection
        summarizes the WHY in two sentences and lists the triage commands."
  critical: "State that the unit must NOT get an 'Environment=LD_LIBRARY_PATH=' line (the unit
             comment forbids it; it goes stale on uv sync). The wrapper recomputes the path each
             launch. Restart with 'systemctl --user restart voice-typing' after any cuDNN fix."

# MUST READ #9 — PyAudio device + wtype/ydotool facts (the other two troubleshooting subsections).
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1 verified facts: the daemon records the PipeWire default source (webcam mic, the accuracy
        ceiling); wtype is the default backend, ydotool the auto-fallback; ydotoold runs as a user
        service. Powers the 'wrong microphone' and 'wtype vs ydotool' subsections."
- file: voice_typing/typing_backends.py
  why: "_WtypeWithFallback: on wtype failure (CalledProcessError/OSError, incl. FileNotFoundError)
        it retries ONCE via ydotool, logs a WARNING, and propagates if ydotool also fails. To force
        a backend: set [output] backend. Powers the wtype/ydotool subsection."
  critical: "daemon.py does NOT pass input_device_index (not in _FIXED_KWARGS or cfg_to_kwargs), so
             the mic is the PipeWire/PulseAudio default source — changed via 'pactl set-default-source',
             NOT via config. State this plainly."

# MUST READ #10 — CPU-only mode facts.
- file: voice_typing/cuda_check.py
  why: "CUDA_DEFAULTS vs CPU_FALLBACK. resolve_device_and_models() returns CPU_FALLBACK
        (cpu/int8/small.en/tiny.en) when ctranslate2 sees 0 CUDA devices, REGARDLESS of config. The
        README's CPU-only section: set [asr] device='cpu' to FORCE it; the auto path does it when no
        GPU; voicectl status reports the resolved device."
- file: voice_typing/daemon.py
  section: "_resolve_device_config()"
  why: "compute_type is DERIVED: 'float16' if device=='cuda' else 'int8'. So device='cpu' → int8. If
        cuda IS present and you force device='cpu', the daemon keeps your final_model/realtime_model
        (only cuda_check overrides them when no device is visible). State the simple version:
        device='cpu' → int8 quantization; if no GPU at all, models also auto-downgrade."

# MUST READ #11 — the prose rules the README must pass (no em dashes, no tell-words, linter).
- docfile: /home/dustin/.pi/agent/skills/write-tech-docs/SKILL.md
  why: "The hard rules for credible short docs: no em dashes (use colon/parens/comma/period); no
        marketing tell-words (powerful, robust, seamless, comprehensive, leverage, utilize, unlock,
        streamline, elevate, blazing-fast, lightweight-unmeasured, ...); no hedging/formulaic
        transitions (moreover, furthermore, 'in conclusion', 'it's worth noting'); do NOT narrate the
        codebase (document what the code cannot show: what/why/how/gotchas); no prose paragraph over
        ~100 words; front-load the answer; prefer lists/tables/code over prose."
  critical: "PRD says 'keep README short and credible (no marketing tone)'. The linter is at
             /home/dustin/.pi/agent/skills/write-tech-docs/scripts/lint.sh — run it on README.md and
             fix every hit until exit 0. The grep gates in Validation enforce the key rules even if
             the linter is unavailable."
```

### Current Codebase tree (state at P2.M1.T2.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── .gitignore                 # READ-ONLY (already ignores .venv/*.log/.pi-subagents; NOT README.md)
├── PRD.md                     # READ-ONLY (§7.7 = the contract; §6 T5 = First run)
├── pyproject.toml uv.lock     # READ-ONLY ([project.scripts] voicectl + voice-typing-daemon present)
├── config.toml                # READ-ONLY (the tuning-table source)
├── install.sh                 # READ-ONLY (the snippets the README mirrors verbatim)
├── systemd/voice-typing.service  # READ-ONLY
├── hypr-binds.conf            # READ-ONLY (created by P2.M1.T1.S1 — the README copies its lines)
├── voice_typing/              # READ-ONLY
│   ├── ctl.py                 #   voicectl CLI + exact status format
│   ├── daemon.py              #   _FIXED_KWARGS (the silero landmine) + _resolve_device_config
│   ├── config.py              #   the schema (rejects unknown keys)
│   ├── cuda_check.py          #   CPU_FALLBACK story
│   ├── typing_backends.py     #   wtype→ydotool auto-fallback
│   ├── feedback.py            #   state.json writer (what tmux status consumes)
│   ├── launch_daemon.sh       #   the cuDNN LD_LIBRARY_PATH wrapper + triage comment
│   └── status.sh              #   the two tmux lines (Mode-A doc)
├── tests/                     # READ-ONLY (P1.M7; the README does not document test internals)
└── .venv/bin/voicectl         # EXISTS + executable (the command the README tells users to run)
# README.md                    # ← CREATE at repo root (this task; does not exist yet)
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
└── README.md                  # NEW — repo root; the user-facing entry doc (~120-200 lines)
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 (G-SILERO-NOT-CONFIG) — silero_sensitivity is a CODE constant, NOT a config key.
#   It lives in voice_typing/daemon.py:_FIXED_KWARGS (=0.4). config.py:AsrConfig has no such field,
#   and VoiceTypingConfig.from_toml() raises TypeError on unknown keys (config.toml header says so).
#   If the README tells a user to set silero_sensitivity in config.toml, the daemon fails to load
#   (main() catches it, logs "failed to load config; exiting", returns 1) and systemd Restart=on-
#   failure loops it forever. The README MUST split "config-tunable" from "code-only (_FIXED_KWARGS)"
#   and explicitly warn against adding VAD keys to config.toml. webrtc_sensitivity,
#   min_length_of_recording, min_gap_between_recordings, silero_backend are the same (code-only).

# CRITICAL #2 (G-VERBATIM-SNIPPETS) — copy the integration snippets EXACTLY from their sources.
#   hypr source line:   source = /home/dustin/projects/voice-typing/hypr-binds.conf
#     (== install.sh:137's `source = $REPO/hypr-binds.conf` with REPO resolved; == hypr-binds.conf)
#   tmux lines:
#     set -g status-interval 1
#     set -g status-right "#(/home/dustin/projects/voice-typing/voice_typing/status.sh)"
#     (== install.sh's printed tmux block; == status.sh's Mode-A header)
#   voicectl usage: /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle|start|stop|status|quit
#   These are STABLE surfaces (the README, install.sh, status.sh, hypr-binds.conf all share them).
#   Do not paraphrase the paths or the quoting — a reader copy-pastes them verbatim.

# CRITICAL #3 (G-NO-SCOPE-CREEP) — this task writes ONE file. Do NOT edit install.sh, config.toml,
#   hypr-binds.conf, status.sh, the systemd unit, or any voice_typing/*.py. Do NOT add a test for the
#   README. Do NOT touch .gitignore, PRD.md, tasks.json, prd_snapshot.md. P2.M1.T1.S1 (parallel) owns
#   hypr-binds.conf + install.sh:136; the README consumes their FINAL state read-only.

# CRITICAL #4 (G-FULL-PATHS) — use full paths for commands the user copy-pastes, because the user's
#   zsh aliases python3/pip/tmux (PRD §2). voicectl: /home/dustin/projects/voice-typing/.venv/bin/voicectl.
#   tmux (if the README shows any tmux command): /usr/bin/tmux. uv: /home/dustin/.local/bin/uv. The
#   hypr/tmux SNIPPETS themselves use the absolute repo path (G-VERBATIM-SNIPPETS).

# CRITICAL #5 (G-CUDA-ONLY-CPU-FALLBACK) — be precise about CPU mode. Two distinct things:
#   (a) FORCE cpu: set [asr] device="cpu". daemon derives compute_type="int8". If a GPU IS present,
#       the daemon still uses your configured final_model/realtime_model on CPU (int8).
#   (b) AUTO cpu: ctranslate2 sees 0 CUDA devices → cuda_check.CPU_FALLBACK overrides to cpu/int8/
#       small.en/tiny.en regardless of config. voicectl status shows 'device: cpu (int8)'.
#   Do not conflate them. State (a) as "how to switch to CPU-only mode" (PRD §7.7) and (b) as the
#   fallback that happens when there is no GPU.

# CRITICAL #6 (G-CUDNN-WRAPPER-NOT-UNIT) — for the cuDNN troubleshooting, point at launch_daemon.sh
#   (the wrapper systemd ExecStart's), NOT at a unit Environment= line. The unit comment explicitly
#   forbids baking LD_LIBRARY_PATH into the unit (it goes stale on uv sync). The wrapper recomputes
#   the lib dirs from the live nvidia wheels each launch. Restart = systemctl --user restart voice-typing.

# CRITICAL #7 (G-NO-ACCEPTANCE-FABRICATION) — the README must NOT claim test results it cannot back.
#   PRD §7 criteria 1-6,8 are satisfied by the P1.M7 test suite, not by the README. The README
#   documents the user-facing commands and the expected runtime behavior; it does not reproduce test
#   output. (Criterion 7 — the README itself — is what THIS task satisfies.)

# CRITICAL #8 (G-PROSE-RULES) — no em dashes (U+2014, or "--" rendered as one), no tell-words, no
#   hedging, no codebase narration, no >100-word paragraph. PRD says "short and credible, no
#   marketing tone." Run the write-tech-docs linter (Validation L4) and the grep gates (L1).
```

## Implementation Blueprint

### Data models and structure

No data models. The artifact is a Markdown document. Its "schema" is the ten-section order in
**What → Required section order**, each section short (mostly one table + one code block), front-
loaded, scannable.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE README.md  (repo root — /home/dustin/projects/voice-typing/README.md)
  - WRITE a Markdown doc, ~120-200 lines, UTF-8, LF, no trailing whitespace, in this section order:
      1. Title + one-liner (what it is; who it's for). No emoji fanfare, no "Welcome to".
      2. Requirements (3-5 bullets: Arch-ish Linux; NVIDIA GPU optional; Wayland/Hyprland for wtype
         + hyprctl notify; tmux optional; PipeWire; portaudio via `pacman -Q portaudio`).
      3. Install: `./install.sh` from the repo root. One short bullet list of what it does (uv sync;
         CUDA smoke; prefetch models; install+enable+start the systemd user unit; copy config.toml
         to ~/.config/voice-typing/ if absent; print usage). Note it starts the daemon NOT listening.
      4. First run (PRD §6 T5, exact steps):
             systemctl --user start voice-typing
             /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle   # arms the mic
             # speak; watch the tmux status line (🎤 partials) / hyprctl popups (● listening, ✔ final)
             /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle   # disarms
         + the expected behavior (partials while speaking; finalized text into the focused window
         shortly after you stop; a pause does not end the session) + the two knobs (see §7).
      5. Hotkey (Hyprland): the source line (G-VERBATIM-SNIPPETS) + `hyprctl reload`; SUPER+ALT+D;
         "source it LAST (Hyprland uses the last matching bind); we never edit your hyprland.conf".
      6. tmux status line: the two ~/.tmux.conf lines (G-VERBATIM-SNIPPETS) + what they render.
      7. Configuration: a TABLE of the config.toml knobs (see Content Pack A) + the G-SILERO-NOT-
         CONFIG callout (VAD constants are code-only in daemon.py:_FIXED_KWARGS; config.py rejects
         unknown keys; do not add them to config.toml).
      8. CPU-only mode (G-CUDA-ONLY-CPU-FALLBACK): set [asr] device="cpu" (int8); auto-fallback when
         no GPU (small.en/tiny.en); voicectl status reports device.
      9. Troubleshooting: three named subsections — cuDNN (G-CUDNN-WRAPPER-NOT-UNIT + the triage
         commands), PyAudio device (default source; `pactl list short sources`; `pactl set-default-
         source <name>`; restart), wtype vs ydotool (auto-fallback; force via [output] backend;
         ydotool needs ydotoold).
     10. Logs, status, stopping: `voicectl status` (show the exact format from Content Pack C);
         `journalctl --user -u voice-typing -f` (INFO latency line; DEBUG timestamps); GPU residency
         (`nvidia-smi --query-compute-apps=pid,used_memory --format=csv`); stop/disable
         (`systemctl --user stop|disable voice-typing`). End the doc.
  - FOLLOW prose rules: G-PROSE-RULES (no em dashes, no tell-words, no hedging, no narration,
    no >100-word paragraph; prefer lists/tables/code; imperative for steps; second person).
  - NAMING: `README.md` (uppercase, repo root — matches PRD §4.1 layout + GitHub convention).
  - PLACEMENT: repo ROOT (beside install.sh, PRD.md, config.toml). NOT under docs/ or voice_typing/.
  - ENCODING: UTF-8, LF newlines, single trailing newline at EOF.

Task 2: VALIDATE (no file written — run the Validation Loop, then optionally the linter)
  - RUN Level 1 grep gates (the seven required headings present; the three verbatim snippets match
    their sources; zero em dashes; zero tell-words; voicectl usage line present).
  - RUN Level 2 (markdown sanity: fenced blocks balanced; no trailing whitespace; LF endings).
  - RUN Level 3 (the cross-source consistency check: README's snippets == install.sh/status.sh/
    hypr-binds.conf; config keys == config.py dataclasses; status format == ctl.py).
  - RUN Level 4 (the write-tech-docs linter if present; the prose gates either way).
```

### Implementation Patterns & Key Details

```markdown
# PATTERN 1 — the tuning TABLE (config.toml knobs ONLY). One row per real key, default in code:
# | Section.key                | Default            | What it does                                          |
# | -------------------------- | ------------------ | ----------------------------------------------------- |
# | asr.post_speech_silence_duration | 0.6          | seconds of silence before a final is emitted.         |
# | asr.realtime_processing_pause    | 0.15         | cadence of live partial previews.                     |
# | asr.device                 | "cuda"             | "cuda" or "cpu" (auto-falls-back if no GPU).          |
# | asr.final_model            | "distil-large-v3"  | model whose output gets typed.                        |
# | asr.realtime_model         | "small.en"         | fast model for live partials.                         |
# | asr.language               | "en"               | ISO-639-1 code.                                       |
# | output.backend             | "wtype"            | "wtype" (default) / "ydotool" / "tmux".               |
# | output.tmux_target         | ""                 | pane target, used only when backend="tmux".           |
# | output.append_space        | true               | trailing space after each final.                      |
# | filter.min_chars           | 2                  | finals shorter than this are dropped.                 |
# | filter.blocklist           | [whisper hallucs]  | exact case-insensitive phrases dropped.               |
# | log.level                  | "INFO"             | "INFO" or "DEBUG" (raw latency timestamps).           |
# Edit at ~/.config/voice-typing/config.toml (install.sh copies the repo default there if absent);
# restart the daemon after editing.

# PATTERN 2 — the G-SILERO-NOT-CONFIG callout (one short paragraph or a blockquote after the table):
# > silero_sensitivity, webrtc_sensitivity, min_length_of_recording, min_gap_between_recordings,
# > and silero_backend are NOT config keys. They are constants in voice_typing/daemon.py (the
# > _FIXED_KWARGS dict). To change VAD sensitivity, edit that file and restart the daemon. Do not
# > add them to config.toml: config.py rejects unknown keys and the daemon will fail to load.

# PATTERN 3 — the cuDNN triage block (fenced, copy-pasteable):
#     journalctl --user -u voice-typing -e
#     LD_DEBUG=libs /home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn
#     ldd /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib/libcudnn.so.9
#     systemctl --user restart voice-typing
# (Two-sentence WHY: faster-whisper loads cuDNN 9 from the nvidia-*-cu12 wheels; its split sub-libs
#  have no RUNPATH so the dynamic linker needs them on LD_LIBRARY_PATH at process start, which
#  launch_daemon.sh sets. Do not bake LD_LIBRARY_PATH into the unit; it goes stale on uv sync.)

# PATTERN 4 — the PyAudio device block:
#     pactl list short sources
#     pactl set-default-source <source_name>
#     systemctl --user restart voice-typing
# (One sentence: the daemon records the PipeWire/PulseAudio default source; there is no config key
#  for the device, so switch the system default and restart.)
```

### Integration Points

```yaml
CONSUMES (READ-ONLY reuse; do NOT modify — the README mirrors these, it does not own them):
  - install.sh (stdout snippets)            -> the usage/tmux/hypr/logs strings the README copies
  - voice_typing/status.sh (Mode-A header)  -> the two tmux lines
  - hypr-binds.conf (P2.M1.T1.S1)           -> the source line + bind + precedence note
  - config.toml + voice_typing/config.py    -> the tuning-table schema (which keys are real)
  - voice_typing/daemon.py (_FIXED_KWARGS)  -> the silero-not-config landmine + compute_type derivation
  - voice_typing/ctl.py (format_result)     -> the exact voicectl status output format
  - voice_typing/cuda_check.py              -> the CPU_FALLBACK story
  - voice_typing/launch_daemon.sh (header)  -> the cuDNN triage
  - voice_typing/typing_backends.py         -> wtype/ydotool auto-fallback
  - architecture/system_context.md          -> verified mic/backend facts

PRODUCES (this task):
  - README.md (repo root)                   -> the user-facing entry doc; satisfies PRD §7 criterion 7
                                               and §6 T5 (the First-run real-hardware smoke doc)

NO integration with: DATABASE (none), CONFIG (config.toml untouched), ROUTES (none), systemd (the
  unit already runs the daemon; the README just documents the systemctl/voicectl/journalctl commands).
```

### Content Pack A — config.toml tuning-table rows (defaults verified against config.py)

| Section.key | Default | Effect |
| --- | --- | --- |
| `asr.post_speech_silence_duration` | `0.6` | seconds of silence before a final is emitted. Lower = snappier but cuts deliberate pauses; higher = fewer false finals but slower. |
| `asr.realtime_processing_pause` | `0.15` | cadence of live partial previews. Lower = more responsive status line; higher = less CPU. |
| `asr.device` | `"cuda"` | `"cuda"` or `"cpu"`. Auto-falls-back to `cpu` if ctranslate2 finds no CUDA device. |
| `asr.final_model` | `"distil-large-v3"` | the model whose output gets typed. |
| `asr.realtime_model` | `"small.en"` | the fast model that produces live partials. |
| `asr.language` | `"en"` | ISO-639-1 code. |
| `output.backend` | `"wtype"` | `"wtype"` (Wayland virtual keyboard), `"ydotool"` (uinput), or `"tmux"`. `wtype` auto-falls-back to `ydotool`. |
| `output.tmux_target` | `""` | pane target, used only when `backend="tmux"` (e.g. `"voicetest:0.0"`). |
| `output.append_space` | `true` | append one trailing space after each final. |
| `filter.min_chars` | `2` | finals shorter than this are dropped. |
| `filter.blocklist` | `[...]` | exact, case-insensitive phrases dropped (classic Whisper silence hallucinations). |
| `log.level` | `"INFO"` | `"INFO"` (per-utterance latency line) or `"DEBUG"` (raw timestamps). |

### Content Pack B — the code-only `_FIXED_KWARGS` constants (NOT config keys)

`silero_sensitivity` (`0.4`), `webrtc_sensitivity` (`3`), `min_length_of_recording` (`0.3`),
`min_gap_between_recordings` (`0.0`), `silero_backend` (`"auto"`). These live in
`voice_typing/daemon.py` (`_FIXED_KWARGS`). `compute_type` is derived (`float16` on cuda, `int8` on
cpu), also not a config key. The README must say: to change VAD sensitivity, edit `daemon.py` and
restart; do not add these to `config.toml`.

### Content Pack C — the exact `voicectl status` output (reproduce in the Logs section)

```
listening: on
partial: this is what i am say
last: Previous sentence.
uptime: 42.3s
device: cuda (float16)
models: distil-large-v3 + small.en
```
CPU fallback: `device: cpu (int8)` and `models: small.en + tiny.en`.

## Validation Loop

### Level 1: Content + prose grep gates (deterministic — run after writing README.md)

```bash
cd /home/dustin/projects/voice-typing

# (a) the seven required headings are present (PRD §7.7 + §6 T5). Adjust heading text to your draft,
#     but all seven topics must appear. (Case-insensitive substring is enough for the gate.)
for topic in "Install" "First run" "Hotkey" "tmux" "Configur" "CPU" "Troubleshoot"; do
  grep -iq "$topic" README.md || echo "MISSING topic: $topic"
done

# (b) the three verbatim integration snippets match their sources (G-VERBATIM-SNIPPETS).
grep -F 'source = /home/dustin/projects/voice-typing/hypr-binds.conf' README.md
grep -F '#(/home/dustin/projects/voice-typing/voice_typing/status.sh)' README.md
grep -F 'set -g status-interval 1' README.md
#   and they agree with the canonical sources:
grep -F 'source = $REPO/hypr-binds.conf' install.sh          # install.sh prints this (REPO resolves to the same path)
grep -F '#(/home/dustin/projects/voice-typing/voice_typing/status.sh)' install.sh voice_typing/status.sh

# (c) the voicectl usage line (full path) is present.
grep -F '/home/dustin/projects/voice-typing/.venv/bin/voicectl' README.md

# (d) the silero landmine is documented (G-SILERO-NOT-CONFIG): the README must name
#     silero_sensitivity AND daemon.py AND warn config rejects unknown keys.
grep -F 'silero_sensitivity' README.md
grep -F 'daemon.py' README.md
grep -iE 'unknown key|reject' README.md

# (e) the cuDNN triage points at launch_daemon.sh (G-CUDNN-WRAPPER-NOT-UNIT), not a unit Environment line.
grep -F 'launch_daemon.sh' README.md
grep -F 'libcudnn' README.md

# (f) PROSE GATE — zero em dashes (U+2014) and zero en dashes (U+2013). Use a colon/paren/comma/period.
! grep -P '\x{2014}|\x{2013}' README.md

# (g) PROSE GATE — zero tell-words (case-insensitive whole-word). Add more from the skill list if you like.
! grep -iE '\b(powerful|robust|elegant|seamless|comprehensive|cutting-edge|revolutionary|leverage|utilize|unlock|empower|supercharge|transform|streamline|elevate|delve|blazing-fast|lightweight)\b' README.md

# Expected: (a) prints no MISSING lines; (b)(c)(d)(e) greps exit 0; (f)(g) `!`-greps exit 0 (no matches).
```

### Level 2: Markdown sanity (immediate)

```bash
cd /home/dustin/projects/voice-typing
# fenced code blocks balanced (equal count of opening ``` and closing ```).
opens=$(grep -c '^```' README.md); [ $((opens % 2)) -eq 0 ] && echo "fences: balanced ($opens)" || echo "fences: UNBALANCED ($opens)"
# no trailing whitespace; LF endings (no CRLF); ends with a single newline.
! grep -nP ' +$' README.md && echo "no trailing whitespace"
! grep -lU $'\r' README.md >/dev/null 2>&1 || echo "WARN: README.md has CRLF"
tail -c1 README.md | od -An -tx1 | grep -q '0a' && echo "README.md: ends with LF"
wc -l README.md   # sanity: aim for ~120-200 lines (PRD: "keep short"). Not a hard fail, but flag if >250.
# Expected: fences balanced; no trailing whitespace; no CRLF; ends with LF; line count reasonable.
```

### Level 3: Cross-source consistency (the "does the README match reality" check)

```bash
cd /home/dustin/projects/voice-typing
# Every config key the README lists as tunable MUST be a real AsrConfig/OutputConfig/etc field
# (else G-SILERO-NOT-CONFIG is violated and a user will crash the daemon). Spot-check the load-bearing
# ones exist in config.py:
for key in post_speech_silence_duration realtime_processing_pause device final_model realtime_model \
           backend tmux_target append_space min_chars blocklist; do
  grep -q "    $key:" voice_typing/config.py || echo "NOT a config field (good if README calls it code-only): $key"
done
# Conversely, the keys README must NOT call config-tunable:
for key in silero_sensitivity webrtc_sensitivity min_length_of_recording silero_backend; do
  ! grep -q "    $key:" voice_typing/config.py && echo "confirmed code-only (not in config.py): $key"
done
# voicectl status format in the README matches ctl.py:format_result's labels.
for label in "listening:" "partial:" "last:" "uptime:" "device:" "models:"; do
  grep -F "$label" README.md >/dev/null || echo "status example missing label: $label"
done
# Expected: the first loop prints nothing (all ARE config fields); the second prints 4 "confirmed
# code-only" lines; the third prints nothing (all labels present).
```

### Level 4: Prose linter (the write-tech-docs gate)

```bash
cd /home/dustin/projects/voice-typing
# The skill ships a linter. Run it on README.md; fix every hit; re-run until exit 0.
if [ -f /home/dustin/.pi/agent/skills/write-tech-docs/scripts/lint.sh ]; then
  bash /home/dustin/.pi/agent/skills/write-tech-docs/scripts/lint.sh README.md && echo "lint: pass"
else
  echo "lint.sh: not present — the Level 1 (f)(g) grep gates enforce the hard rules instead."
fi
# Expected: 'lint: pass' (exit 0), OR the explicit not-present message (L1 greps already cover the rules).
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1: all seven topics present; the three verbatim snippets match install.sh/status.sh/
      hypr-binds.conf; voicectl full path present; silero landmine + daemon.py + unknown-key warning
      present; cuDNN points at launch_daemon.sh; zero em/en dashes; zero tell-words.
- [ ] Level 2: fences balanced; no trailing whitespace; LF endings; ends with LF; ~120-250 lines.
- [ ] Level 3: every README-tunable key is a real config.py field; the four VAD constants confirmed
      code-only; the status example has all six labels.
- [ ] Level 4: write-tech-docs linter exits 0 (or, if absent, the L1 grep gates pass).

### Feature Validation

- [ ] README.md exists at repo root and satisfies PRD §7 criterion 7 (all seven enumerated topics).
- [ ] "First run" reproduces PRD §6 T5's exact steps with the full voicectl path and expected behavior.
- [ ] Config tuning table lists ONLY real config.toml keys; the code-only callout names daemon.py and
      warns that config rejects unknown keys (G-SILERO-NOT-CONFIG).
- [ ] CPU-only mode section distinguishes forced `device="cpu"` from the no-GPU auto-fallback
      (G-CUDA-ONLY-CPU-FALLBACK) and notes `voicectl status` reports it.
- [ ] Troubleshooting has the three required subsections (cuDNN, PyAudio device, wtype vs ydotool)
      with copy-pasteable commands and full paths.
- [ ] No fabricated acceptance-test evidence (G-NO-ACCEPTANCE-FABRICATION); the README documents
      commands and runtime behavior only.

### Code Quality Validation

- [ ] File placement matches the desired tree (repo root, beside install.sh / PRD.md).
- [ ] Naming `README.md` matches PRD §4.1 layout + GitHub convention.
- [ ] Prose passes the write-tech-docs rules: no em dashes, no tell-words, no hedging, no codebase
      narration, no >100-word paragraph, front-loaded, scannable.
- [ ] Every fenced command is real and runnable on this machine (full paths where the shell needs them).

### Documentation & Deployment

- [ ] The README is the single user-facing entry doc (Mode B); it mirrors install.sh's printed
      snippets so a user who reads it then runs install.sh sees consistent output.
- [ ] No new env vars / config keys / dependencies introduced (the README changes nothing but itself).
- [ ] Committed to git (criterion 7: "Everything committed to git") — `git add README.md`.

---

## Anti-Patterns to Avoid

- ❌ Don't tell users to set `silero_sensitivity` (or any `_FIXED_KWARGS` constant) in config.toml —
  config.py rejects unknown keys and the daemon fails to load (G-SILERO-NOT-CONFIG). Call it out as
  code-only and point at `voice_typing/daemon.py`.
- ❌ Don't use em dashes, marketing tell-words, or hedging transitions — PRD says "short and credible,
  no marketing tone"; the write-tech-docs rules + linter enforce it (G-PROSE-RULES).
- ❌ Don't narrate the codebase (file-by-file walkthrough of voice_typing/). Document what the code
  cannot show: what it is, why, how to use it, the gotchas. Then stop.
- ❌ Don't paraphrase the integration snippets (hypr source line, tmux lines, voicectl usage) — copy
  them verbatim from install.sh / status.sh / hypr-binds.conf (G-VERBATIM-SNIPPETS).
- ❌ Don't conflate forced CPU mode (`device="cpu"`, keeps your models) with the no-GPU auto-fallback
  (overrides to small.en/tiny.en). State both precisely (G-CUDA-ONLY-CPU-FALLBACK).
- ❌ Don't point cuDNN troubleshooting at a unit `Environment=LD_LIBRARY_PATH=` line — the wrapper
  (`launch_daemon.sh`) is the fix; the unit comment forbids baking it in (G-CUDNN-WRAPPER-NOT-UNIT).
- ❌ Don't fabricate test/acceptance evidence. Criteria 1-6,8 are the test suite's job; the README
  documents commands (G-NO-ACCEPTANCE-FABRICATION).
- ❌ Don't edit any file other than README.md (G-NO-SCOPE-CREEP). install.sh:136 and hypr-binds.conf
  are owned by P2.M1.T1.S1 (parallel); consume their final state read-only.
- ❌ Don't use bare `voicectl` / `tmux` / `python3` in copy-paste commands — the user's zsh aliases
  them (PRD §2). Use full paths (G-FULL-PATHS).
- ❌ Don't pad the README with template sections nobody reads (badges, "Contributing" wall, license
  boilerplate unless you mean it). Keep it short and task-oriented.

---

## Confidence Score

**9/10.** The deliverable is one Markdown file whose every load-bearing string is pinned verbatim in
this PRP (the exact voicectl usage line, the exact hypr source line, the exact two tmux lines, the
exact config keys, the exact `voicectl status` format, the exact cuDNN triage). The required section
order, the prose rules, and the validation gates are all fixed and deterministic. The one accuracy
landmine (`silero_sensitivity` is a code constant, not a config key, and config.py rejects unknown
keys) is called out in five places with the failure mode. The cross-source consistency check (Level 3)
mechanically proves the README's snippets and config keys match the actual code. Deducted 1 point for
the inherent subjectivity of "short and credible" prose quality (mitigated by the write-tech-docs
linter + the grep gates) and for the soft length target (not a hard gate).

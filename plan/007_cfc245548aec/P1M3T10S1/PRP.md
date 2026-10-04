# PRP — P1.M3.T10.S1: README end-to-end Rev 2 sync + residual-reference sweep

---

## Goal

**Feature Goal**: Rewrite `README.md` so it documents the as-built Rev 2 product — single-model streaming dictation (`small.en` types live partials revised in place), the collapsed command surface (`toggle|start|stop|status|cancel|quit`), the single hotkey + cancel bind, and the new config keys — with ZERO residual references to the deleted normal/lite dual-mode surface (two models, `toggle-lite`, `distil-large-v3`, `final_model`, `realtime_model`, mode switching, `⚡` marker).

**Deliverable**: A fully updated `/home/dustin/projects/voice-typing/README.md` (the ONLY file modified).

**Success Definition**: `grep -inE "toggle-lite|start-lite|distil-large|final_model|realtime_model|⚡|lite mode|normal mode|two-model" README.md` returns nothing; every config-table row names a real, consumed key; every command/keybind/status-line quoted in the README matches the shipped code (verified by cross-reading the files below).

## User Persona

**Target User**: dustin six months from now, or a cloner of the repo — a Linux power user who wants exact commands, not hand-holding (the README's own stated audience).

**Use Case**: Install, bind one hotkey, dictate with live typed partials, cancel a bad fragment with Backspace, tune config, troubleshoot.

**User Journey**: `./install.sh` → source `hypr-binds.conf` → press **Ctrl+Alt+Super+D** → speak (words appear live, revised in place; silence commits) → Backspace cancels a bad fragment → press the key again to stop. `voicectl status` / config table / troubleshooting consulted when something misbehaves.

**Pain Points Addressed**: The current README describes a product that no longer exists — dual modes, two binds, two models, append-only finals. Following it (e.g. pressing Alt+Super+D or running `toggle-lite` → exit 64) actively fails.

## Why

- PRD §7 criterion 7: "README documents: install, hotkey snippet, feedback surfaces, config tuning table, troubleshooting, and how to switch to CPU-only mode" — currently satisfied for the Rev 1 product only.
- Rev 2 (PRD §1, §4.2quater) removed normal mode entirely; all code/config/bind tasks (P1.M1, P1.M2, P1.M3.T8/T9) are Complete — README is the last stale artifact.
- `tests/ACCEPTANCE.md` cites "criterion 7 by `git status` + the README task" — this task IS that reference.

## What

Rewrite README.md section by section to the Rev 2 truth, then sweep for residual stale vocabulary. No code changes; no new files.

### Success Criteria

- [ ] Hotkey section shows the TWO real binds from `hypr-binds.conf`: `CTRL SUPER ALT, D → toggle` and `SUPER ALT, Backspace → cancel`; no `SUPER ALT, D` bind.
- [ ] "Lite mode" section DELETED, replaced by a "Streaming dictation" section describing: typed partials revised in place (delete-and-retype of the changed tail), silence triggers commit/correction pass (not visible output), stranded tails freeze (never auto-delete), any non-Backspace user key freezes the tail, `output.streaming=false` rollback hatch.
- [ ] Backspace-cancel documented: physical Backspace while a fragment is in flight cancels it (compensated by subtraction, idempotent), plus the `Alt+Super+Backspace` / `voicectl cancel` fallback and the one-time journal warning when evdev can't open a keyboard.
- [ ] Config table rows: `asr.lite_model` (the single model), `asr.lite_post_speech_silence_duration` (0.8, THE silence gate), `asr.context_prompt`, `output.streaming`, `[cancel].on_backspace`, `[cancel].devices` — and NO rows for `final_model`/`realtime_model`.
- [ ] `voicectl status` example shows the real output shape incl. `mode: lite`, `context-prompt:` line, `mic:` line; `models: small.en (loaded)` (CPU: `tiny.en`).
- [ ] CPU-only section: single model (`small.en` → `tiny.en` on fallback), no `final_model`/`realtime_model` mentions.
- [ ] Model lifecycle section: single resident model (~0.5–3 GB), no "whichever mode is resident" phrasing.
- [ ] Residual grep (above) clean; README keeps its existing tone, heading structure, and still-correct sections (Install, cuDNN, wrong-mic, teardown) intact.

## All Needed Context

### Context Completeness Check

Verified: an agent with only this PRP + repo access knows every stale line (enumerated below), the as-built truth (quoted from code), and the grep gate. No guessing required.

### Documentation & References

```yaml
- file: README.md
  why: THE artifact to rewrite. Current stale lines (verified by grep, 1-indexed):
       79, 100, 103-109 (dual-mode hotkey prose + both binds), 116-127 (whole "## Lite mode"
       section), 139+143 (state-file mode + ⚡ marker), 161 (lite silence row, wrong default
       0.5 & rationale), 166-168 (final_model/realtime_model/lite_model rows), 206 (CPU-mode
       final_model+realtime_model), 318+322 (status example "models: distil-large-v3 +
       small.en" + mode: normal), 334+337 (lifecycle loads two models / lite VRAM half).
  pattern: keep the tone (terse, exact commands, <repo-path> placeholders, section order).
  gotcha: also lines ~60-76 "First run" say "finalized text is typed … as you pause" — Rev 2
       types partials LIVE; update the expected-behavior prose too.

- file: config.toml
  why: the already-synced Rev 2 config reference (Mode A doc). The README table must mirror
       these keys/defaults verbatim: lite_model="small.en",
       lite_post_speech_silence_duration=0.8, context_prompt=true, output.streaming=true,
       [cancel].on_backspace=true, [cancel].devices=[].
  gotcha: config.toml still LISTS asr.post_speech_silence_duration=0.6, but daemon.py:205
       consumes ONLY the lite_ value — do NOT present the base key as a tunable knob; the
       README table should carry only lite_post_speech_silence_duration (silence gate).

- file: voice_typing/ctl.py
  why: command surface truth: _COMMANDS = toggle|start|stop|status|quit|cancel (usage errors
       exit 64; daemon-not-running exit 2). format_result() status block = the exact lines to
       show in the README example: listening / mode / phase / partial / last / uptime /
       "device: cuda (float16)" / mic: ok / "context-prompt: on" (+ optional load error line).
       mode is the daemon constant "lite" — document it as a fixed Rev 2 value, NOT a switch.
  gotcha: NO ⚡ prefix exists anymore (README line 143 claims one — remove).

- file: hypr-binds.conf
  why: the two real binds to quote: `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl
       toggle` and `bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel`.
       Keep the $HOME launcher + source-LAST precedence explanation (still accurate).

- file: voice_typing/daemon.py (read the module docstring + lines 150-210 only)
  why: _resolve_device_config()/cfg_to_kwargs(): single model fills BOTH model= and
       realtime_model_type= slots from cfg.asr.lite_model (use_main_model_for_realtime=True);
       post_speech_silence_duration kwarg = cfg.asr.lite_post_speech_silence_duration;
       cuda_check maps small.en→tiny.en on CPU fallback.

- file: tests/ACCEPTANCE.md (head only)
  why: criterion 7 points at this README task; VRAM evidence row cites single-model range
       [512,3072] MiB — reuse "~0.5–3 GB" for the resident footprint.

- file: validate.sh (head)
  why: validation entrypoint: `./validate.sh` (phases 1,2,3,5; ~2-3 min; safe, never arms
       mic). Mention in README only if it already does — it doesn't; do not add.

- url: https://github.com/KoljaB/RealtimeSTT
  why: engine citation already in README intro; keep as-is.

- docfile: plan/007_cfc245548aec/prd_snapshot.md §4.2quater, §4.8, §4.10
  why: authoritative Rev 2 behavior spec for the new Streaming dictation section
       (output state machine rules 1-5, cancel semantics, context prompt, guards).
```

### Current Codebase tree (relevant slice)

```bash
voice-typing/
├── README.md            # STALE — the artifact (modified by THIS task)
├── config.toml          # Rev 2-synced reference  (read-only for this task)
├── hypr-binds.conf       # Rev 2-synced (2 binds)  (read-only)
├── install.sh            # Rev 2-synced usage line (read-only)
├── validate.sh           # validation runner       (read-only)
├── voice_typing/{config,ctl,daemon,streaming,key_listener,prompt_engine,...}.py
└── tests/ACCEPTANCE.md   # evidence rows           (read-only)
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
# NO files added. README.md rewritten in place — same sections, Rev 2 content:
#   Install (unchanged) / First run (streaming prose) / Hotkey (2 binds) /
#   Streaming dictation (NEW, replaces "Lite mode") / Feedback surfaces (mode fixed "lite",
#   no ⚡) / Configuration (Rev 2 table) / CPU-only (single model) / Troubleshooting
#   (unchanged except model names) / Logs, status, stopping (real status example) /
#   Model lifecycle & VRAM (single model).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: `toggle-lite`/`start-lite` now exit 64 (usage error) — test_control_socket.py:138
# asserts the daemon rejects them. README must not suggest them anywhere, including prose.
# CRITICAL: config schema REJECTS unknown keys (TypeError at load → systemd crash-loop) — the
# README table must list ONLY real keys from config.py; do not invent or keep dead ones.
# GOTCHA: `asr.post_speech_silence_duration` exists in config.toml/config.py but the daemon
# consumes only `lite_post_speech_silence_duration` (daemon.py:205). Do NOT tell users to tune
# the base key; document the lite_ key as THE silence gate (0.8 default; 0.5 razor-snappy,
# 1.0 near-zero mid-thought cuts — rationale now: endpointer only delays COMMIT, words are
# already typed live).
# GOTCHA: README "First run" cites tunable `post_speech_silence_duration` (line ~76) — repoint
# to lite_post_speech_silence_duration.
# GOTCHA: mode in state.json/status is a CONSTANT "lite" (daemon-side), not a user choice —
# document as vestigial-but-present, or simply show it in the example without switch prose.
# NOTE: bash tool discipline (AGENTS.md): every non-trivial command under inner GNU `timeout`
# + harness timeout; never run the daemon in the foreground for README verification — grep and
# file reads only; `timeout 15 .venv/bin/voicectl status` if a live check is ever needed.
```

## Implementation Blueprint

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: REWRITE README.md "First run" expected-behavior prose
  - REPLACE "finalized text is typed … as you pause" with Rev 2: stabilized partials are TYPED
    live and revised in place; a pause triggers the commit/correction pass (+ trailing space);
    a pause never ends the session; Backspace cancels the in-flight fragment.
  - REPOINT the tuning knob mention to asr.lite_post_speech_silence_duration.

Task 2: REWRITE "## Hotkey (Hyprland)"
  - ONE toggle bind: Ctrl+Alt+Super+D (quotes hypr-binds.conf lines verbatim).
  - ADD the cancel fallback bind: Alt+Super+Backspace → voicectl cancel (evdev-unavailable
    fallback + automated-test seam).
  - DELETE: the SUPER ALT, D bind line, dual-mode paragraphs (lines 103-109), mode-switch
    reload prose, ⚡ sentence.
  - KEEP: source-LAST precedence + custom/keybinds.conf conflict note (still valid).

Task 3: REPLACE "## Lite mode" with "## Streaming dictation"
  - Content (PRD §4.2quater): live typed partials; extend-types delta, revise =
    delete-and-retype changed tail (rewinds rate-limited ≥300 ms); silence trips the
    commit/correction pass (small.en re-decodes the whole utterance; differs → rewind+retype);
    stranded tail FREEZES (never auto-deleted — only explicit cancel deletes); any
    non-Backspace keypress while a fragment is pending freezes it (never type over the user);
    rolling context prompt (asr.context_prompt — continuations don't start capitalized or gain
    spurious periods); output.streaming=false = append-only rollback hatch.
  - SUBSECTION "Backspace-cancel": physical Backspace while a fragment is in flight cancels it
    (rewinds len(tail)−1 — the keystroke itself deleted one), drops buffered audio, mic stays
    hot; idempotent; [cancel].devices override; unreadable keyboard → one journal warning at
    arm + Alt+Super+Backspace/`voicectl cancel` fallback.

Task 4: SYNC "## Feedback surfaces"
  - state.json fields: mode is constant "lite"; partial mirrors the live tail; drop ⚡ from the
    voicectl status bullet.

Task 5: REBUILD "## Configuration" table
  - DROP rows: asr.final_model, asr.realtime_model, asr.post_speech_silence_duration,
    asr.lite_post_speech_silence_duration's OLD 0.5/lite-mode rationale.
  - ADD/UPDATE rows (defaults from config.toml): asr.lite_model "small.en" (the single model —
    partials AND finals), asr.lite_post_speech_silence_duration 0.8 (THE silence gate — commit
    delay under streaming), asr.context_prompt true, output.streaming true (rollback hatch),
    cancel.on_backspace true, cancel.devices [] (auto-detect).
  - KEEP unchanged rows: realtime_processing_pause, auto_stop_idle_seconds,
    auto_unload_idle_seconds, device, language, output.backend, output.append_space,
    feedback.*, filter.*, log.level.
  - KEEP the "Voice-activity constants are NOT config keys" subsection (verify the _FIXED_KWARGS
    claim still matches daemon.py before keeping verbatim).

Task 6: SYNC "## CPU-only mode"
  - Path 1 (forced cpu): uses configured lite_model, int8.
  - Path 2 (auto-fallback): device=cpu + tiny.en (single model).
  - Path 3 (construction-failure): same as 2; status shows device: cpu (int8),
    models: tiny.en.
  - REMOVE final_model/realtime_model mentions (line 206).

Task 7: SYNC "## Logs, status, stopping" + "### Model lifecycle & VRAM"
  - Status example: mode: lite / context-prompt: on / mic: ok / models: small.en (loaded)
    (CPU: tiny.en); explain the context-prompt line labels (on / off (disabled by config) /
    off (degraded) / unknown).
  - Lifecycle: ONE resident model (~0.5–3 GB); first arm ~1-3 s; drop "whichever mode is
    resident / reloads in whatever mode" (lines 334-337).

Task 8: RESIDUAL-REFERENCE SWEEP (the gate)
  - RUN: grep -inE "toggle-lite|start-lite|distil-large|final_model|realtime_model|⚡|lite
    mode|normal mode|two-model|mode switch|Alt\+Super\+D(?!.*Backspace)" README.md
    → must be EMPTY (prune the alternation if a legit hit is argued away, but zero is expected).
  - ALSO sanity-sweep cross-file drift the README quotes: hypr-binds.conf binds, install.sh
    usage line (`voicectl toggle|start|stop|status|cancel|quit`), config.toml keys — README
    quotes must match verbatim.

Task 9: VALIDATION (below), then `git add README.md && git commit`.
```

### Implementation Patterns & Key Details

```markdown
<!-- Pattern for the status example — quote the REAL shape from ctl.py format_result():
listening: on
mode: lite
phase: speaking
partial: this is what i am say
last: Previous sentence.
uptime: 42.3s
device: cuda (float16)
mic: ok
context-prompt: on
-->

<!-- Pattern for bind quoting — copy verbatim from hypr-binds.conf:
bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle
bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel
-->
```

### Integration Points

```yaml
DOCUMENTATION-ONLY:
  - README.md is referenced BY: tests/ACCEPTANCE.md (criterion 7), install.sh's printed
    pointers, AGENTS.md workflows. No code reads README at runtime.
  - Do NOT touch: config.toml, hypr-binds.conf, install.sh, tests/, PRD.md, tasks.json.
```

## Validation Loop

### Level 1: Residual sweep (the core gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 20 grep -inE "toggle-lite|start-lite|distil-large|final_model|realtime_model|⚡|lite mode|normal mode|two-model" README.md
# Expected: NO OUTPUT (exit 1). Any hit = stale reference, fix before proceeding.
timeout 20 grep -cE "^\|" README.md   # table intact (sanity)
```

### Level 2: Cross-quote consistency (README vs code)

```bash
# Commands quoted in README must be a subset of ctl.py's surface:
timeout 20 grep -oE "voicectl [a-z-]+" README.md | sort -u   # every hit ∈ {toggle,start,stop,status,cancel,quit}
# Binds quoted must match hypr-binds.conf; config keys quoted must exist in config.toml:
timeout 20 grep -oE "(asr|output|cancel|feedback|filter|log)\.[a-z_]+" README.md | sort -u
# Expected: every key exists in config.toml; NO asr.post_speech_silence_duration / final_model /
# realtime_model rows presented as tunables.
```

### Level 3: Repo health (nothing else broke — doc-only change)

```bash
timeout 300 uv run pytest tests/test_voicectl.py tests/test_config_repo_default.py tests/test_systemd_unit.py -q
# Expected: all pass (these already guard ctl/config/install sync; README edit can't break
# them, but they prove the environment + sibling artifacts are still coherent).
# If broader assurance is wanted: ./validate.sh  (phases 1,2,3,5; ~2-3 min; never arms the mic).
```

### Level 4: Human read-through

Read the final README top-to-bottom as the "six months from now" user: install → first arm →
speak (live partials) → Backspace-cancel → stop → tune → troubleshoot. Every command must be
copy-pasteable and correct against the files in "Documentation & References".

## Final Validation Checklist

### Technical Validation
- [x] Level 1 grep clean (zero residual hits)
- [x] Level 2 cross-quote checks pass (commands ⊆ ctl surface; keys exist; binds verbatim)
- [x] Level 3 pytest trio green (or `./validate.sh` exit 0)
- [x] Level 4 read-through: journey is coherent end-to-end for a fresh reader

### Feature Validation
- [x] All success criteria in "What" met (hotkey, streaming section, cancel doc, config table, status example, CPU section, lifecycle)
- [x] Still-correct sections (Install, cuDNN, wrong-mic, wtype/ydotool, teardown) preserved unbroken
- [x] No new claims that the code contradicts (single model, fixed mode, cancel idempotence)

### Code Quality / Scope Validation
- [x] ONLY README.md modified (`git status` shows exactly one changed file)
- [x] Tone, heading hierarchy, and `<repo-path>` placeholder style preserved
- [x] No PRD.md / tasks.json / config.toml / test edits (FORBIDDEN for this task)

### Documentation & Deployment
- [x] Committed to git with a message referencing Rev 2 README sync (criterion 7 evidence)

---

## Anti-Patterns to Avoid

- ❌ Don't invent behavior — every sentence must trace to code, config.toml, hypr-binds.conf, or PRD §4.2quater.
- ❌ Don't document `asr.post_speech_silence_duration` as a knob (dead in the daemon — only the lite_ key is consumed).
- ❌ Don't describe mode switching / "whichever mode is resident" — there is exactly one mode.
- ❌ Don't delete or rewrite the still-accurate troubleshooting sections out of zeal — surgical sync only.
- ❌ Don't add new files or tests — this is a doc task; the grep IS the gate.

---

**Confidence Score**: 9/10 — the artifact is a single file, every stale line is enumerated with line numbers, and every replacement fact is quoted from shipped code/config. The residual risk is only editorial (omitting a Rev 2 behavior worth documenting), bounded by the Level 4 read-through.

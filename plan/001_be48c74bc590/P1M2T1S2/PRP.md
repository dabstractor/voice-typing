# PRP — P1.M2.T1.S2: Write self-documenting default `config.toml`

## Goal

**Feature Goal**: Produce `config.toml` at the **repo root** (`/home/dustin/projects/voice-typing/config.toml`) that is **both** the daemon's runtime default **and** the primary user-facing configuration reference (PRD "Mode A"). Its four tables (`[asr]`, `[output]`, `[feedback]`, `[filter]`) carry the **exact** default values defined by `voice_typing/config.py` (P1.M2.T1.S1, PRD §4.5), and **every value line is commented** to explain its effect and its valid values (`device` `cuda|cpu`, `backend` `wtype|ydotool|tmux`, etc.). It parses under stdlib `tomllib` with **zero overrides** over the dataclass defaults.

**Deliverable** (two artifacts):
1. `config.toml` (repo root) — the self-documenting default. Verbatim content in Implementation Blueprint → Task 1. Consumed by `install.sh` (P1.M6.T1.S1), which copies it to `$XDG_CONFIG_HOME/voice-typing/config.toml` if absent.
2. `tests/test_config_repo_default.py` — a small **drift-guard** unit test codifying the contract "`from_toml_file(<repo>/config.toml) == VoiceTypingConfig()`". This is the *verification step* (item LOGIC step 3: "Verify `load()` parses it with no overrides") made permanent, so a future default change in `config.py` cannot silently desync from `config.toml`. Verbatim source in Implementation Blueprint → Task 2.

**Success Definition**:
- (a) `config.toml` exists at repo root; parses under stdlib `tomllib` with no `TOMLDecodeError`.
- (b) `VoiceTypingConfig.from_toml_file("<repo>/config.toml") == VoiceTypingConfig()` — **byte-for-value equality**, i.e. the file introduces **no overrides** (the item's acceptance gate).
- (c) Each of the 14 config keys has a trailing comment explaining effect + valid values; the file opens with a header block documenting Mode A, the search order, and the `install.sh` copy.
- (d) `.venv/bin/python -m pytest tests/test_config_repo_default.py -v` → **pass**.
- (e) `.venv/bin/python -m pytest -q` (whole suite) → still **all green** (S1's `tests/test_config.py` unaffected by this file's existence).
- (f) No out-of-scope files: no edits to `voice_typing/config.py` (S1 owns it), no `daemon.py`/`textproc.py`/`feedback.py`/`typing_backends.py`/`ctl.py`/`install.sh`/systemd, no edits to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.

## User Persona

**Target User**: A Linux desktop user (Wayland/Hyprland, terminal-heavy) who wants to tune voice-typing behavior without reading source code.

**Use Case**: The user opens `config.toml` (either the repo copy or their XDG copy that `install.sh` placed) to change e.g. the typing backend, raise the silence duration, or add a phrase to the blocklist.

**User Journey**: User reads the header → understands the search order and that editing this file tunes the daemon → finds the relevant table → each line's comment tells them the effect and valid values → they change one value → restart the daemon.

**Pain Points Addressed**: No separate config doc to keep in sync (this file IS the doc, Mode A); no guessing valid values (every enum is inline); typos fail loudly (unknown keys raise at load).

## Why

- **One file, two roles.** PRD §4.5 designates `config.toml` as both the runtime default (search-order step 2) and the Mode A user documentation surface. Writing it as a *self-documenting* artifact means the config reference can never drift from the config the daemon actually loads — the comments live next to the values they describe.
- **`install.sh` (P1.M6.T1.S1) copies THIS file to XDG.** Because the copied file becomes the user's editable config, it must be readable as documentation *before* it is readable as data. Comments here are not decoration; they are the user-facing tuning guide.
- **The code↔config drift risk is real and named.** S1's PRP explicitly warns: "if a default is ever changed in `config.py`, the matching line + comment in `config.toml` MUST change in lockstep." This task ships the file AND a permanent test that enforces that lockstep, so the warning is not just prose.
- **Small, well-bounded, GPU-free.** No CUDA, no audio, no network. Fully validatable with stdlib `tomllib` + the dataclass equality from S1. Sits squarely inside P1.M2 (Configuration & Text Processing) and unblocks `install.sh` (P1.M6.T1.S1), which needs a repo default to copy.

## What

Create `config.toml` at the repo root (verbatim in Implementation Blueprint → Task 1): a header comment block (Mode A, search order, schema source), then the four PRD §4.5 tables. Every value equals the corresponding `voice_typing/config.py` dataclass default. The `[filter].blocklist` is a multi-line array with one entry per line, each commented, in the **exact order** of the dataclass default (list equality is order-sensitive). Then `tests/test_config_repo_default.py` (verbatim in Implementation Blueprint → Task 2) asserting `from_toml_file(_repo_config_path()) == VoiceTypingConfig()`.

### Success Criteria

- [ ] `config.toml` exists at `/home/dustin/projects/voice-typing/config.toml` (repo root, **not** inside `voice_typing/`).
- [ ] `tomllib.load(open("config.toml","rb"))` succeeds (no `TOMLDecodeError`).
- [ ] `VoiceTypingConfig.from_toml_file("<repo>/config.toml") == VoiceTypingConfig()` is `True`.
- [ ] The parsed top-level dict's keys are exactly `{asr, output, feedback, filter}`; `[asr]` has exactly `{final_model, realtime_model, language, device, post_speech_silence_duration, realtime_processing_pause}`; `[output]` `{backend, tmux_target, append_space}`; `[feedback]` `{state_file, hypr_notify, notify_ms}`; `[filter]` `{min_chars, blocklist}`. No `compute_type` or any other extra key.
- [ ] Every value line has a trailing `#` comment; the file has a header comment block.
- [ ] `blocklist` order matches the dataclass default: `["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"]`.
- [ ] `.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -v` → all pass.
- [ ] Only `config.toml` (new) and `tests/test_config_repo_default.py` (new) are created. Nothing else changes.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge of this repo: the verbatim `config.toml` content and the verbatim test are in the Implementation Blueprint; the exact default values are pinned to PRD §4.5 and cross-referenced against S1's `config.py` (read at preflight to confirm); the one TOML gotcha (multi-line array + inline comments) was verified live with stdlib `tomllib` and the result is recorded in `research/config_toml_defaults_and_toml_syntax.md`; the placement (repo root) and search-order/install contract are documented with the exact path expression S1's `_repo_config_path()` uses.

### Documentation & References

```yaml
# MUST READ — the authoritative TOML schema + every default value (the contract)
- file: PRD.md
  why: "§4.5 is the canonical config.toml (schema + defaults + search order + the
        install.sh copy note). §4.4 documents the cuda_check device fallback that the
        [asr].device comment must reference (device='cuda' is the DESIRED value; the
        daemon may override to 'cpu'). §4.1 file map shows config.toml at repo root."
  critical: "Reproduce §4.5 values EXACTLY. Do NOT add compute_type (it is a §4.4
             cuda_check field, not a §4.5 config key — adding it raises TypeError at load).
             The search order and the install.sh-copy sentence at the end of §4.5 belong
             in the header comment."

# MUST READ — the contract this task consumes (config.py defaults are the source of truth)
- file: plan/001_be48c74bc590/P1M2T1S1/PRP.md
  why: "S1 writes voice_typing/config.py with the 5 dataclasses + from_toml_file +
        _repo_config_path(). The DEFAULTS in its 'Task 3 SOURCE' block are the values
        config.toml must mirror. Its '_repo_config_path()' = Path(__file__).resolve().
        parent.parent / 'config.toml' is WHY this file lives at repo root. Its tests
        monkeypatch _repo_config_path, so creating config.toml does NOT break them."
  critical: "config.toml's values must equal S1's dataclass defaults so
             from_toml_file == VoiceTypingConfig(). If S1 actually shipped a default that
             differs from this PRP's verbatim block, TRUST THE LIVE config.py (read it at
             preflight) and reconcile — do not blindly paste. The drift-guard test is the
             final arbiter."

# MUST READ — verified machine facts + the corrected decisions (READ-ONLY context)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1: Python 3.12.10, shell aliases -> ALWAYS full paths (.venv/bin/python,
        /home/dustin/.local/bin/uv); tomllib is stdlib (3.11+). §2 file map: config.toml
        sits at repo root (same level as pyproject.toml), NOT inside voice_typing/. §4
        decision #6: config holds device='cuda' as the desired value; cuda_check overrides
        at daemon runtime — the [asr].device comment must reflect this."
  critical: "Use .venv/bin/python explicitly (never bare python/uv/tmux — zsh aliases).
             config.toml at repo root is what _repo_config_path() expects."

# MUST READ — TOML syntax verification + the exact defaults table (this task's research)
- docfile: plan/001_be48c74bc590/P1M2T1S2/research/config_toml_defaults_and_toml_syntax.md
  why: "§1: the 14 valid keys + exact default values (incl. blocklist ORDER). §2: verified
        that stdlib tomllib parses multi-line arrays WITH inline per-element comments, that
        trailing inline comments work, that 0.6/0.15 parse as float and 2/2500 as int (so
        equality holds), and that unknown keys (e.g. compute_type) are valid TOML but
        rejected by the dataclass layer. §3: placement + search order + install contract.
        §4: self-documenting conventions (Mode A). §5: the verification run output."
  section: "ALL sections load-bearing. §1 (keys+values), §2 (TOML facts), §3 (placement),
            §4 (comment style)."

# Background — the sibling module whose MODEL/DEVICE defaults config mirrors (consistency)
- file: voice_typing/cuda_check.py
  why: "CUDA_DEFAULTS = {device:'cuda', final_model:'distil-large-v3', realtime_model:
        'small.en'}. config.toml's [asr] mirrors these three. cuda_check.compute_type is
        NOT mirrored (it is not a config key). Mirror its docstring/comment style: plain
        present-tense, concrete units, cross-references not duplication."
  critical: "Do NOT add compute_type to config.toml. The [asr].device comment must say the
             daemon auto-falls-back to cpu via cuda_check (do not re-explain CUDA mechanics)."

# Downstream — the consumer that copies THIS file (why it must be self-documenting)
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M6.T1.S1 (install.sh) copies repo config.toml to $XDG_CONFIG_HOME/voice-typing/
        config.toml if absent. So this file becomes the user's editable config reference —
        its comments ARE the user docs (Mode A). install.sh expects the file at repo root."
  critical: "config.toml must be at repo root (install.sh references it by relative path from
             the repo). Keep comments user-facing: effect + valid values, not dev notes."
```

### Current Codebase tree (state at P1.M2.T1.S2 start — S1 done, others pending)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*'` from repo root. Expected after S1 lands:

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores dist/, *.pyc, __pycache__/, .venv/, .pi-subagents/ (DO NOT touch)
├── .venv/                      # Python 3.12.10; realtimesttt + nvidia-* + huggingface_hub + pytest installed
│   └── bin/python              # the python everything runs under
├── PRD.md                      # READ-ONLY
├── pyproject.toml              # S1 added [dependency-groups] dev = ["pytest"] (DO NOT touch here)
├── uv.lock                     # DO NOT touch
├── voice_typing/
│   ├── __init__.py             # S1's package docstring
│   ├── cuda_check.py           # T2.S2 (CUDA_DEFAULTS — [asr] mirrors device/model)
│   ├── launch_daemon.sh        # T2.S1 (LD_LIBRARY_PATH wrapper — unrelated)
│   ├── prefetch.py             # T3.S1 (model prefetch — unrelated)
│   └── config.py               # ← S1's output (dataclasses + loader + _repo_config_path). READ but DO NOT EDIT.
└── tests/
    └── test_config.py          # ← S1's output (config loader unit tests). DO NOT EDIT.
# NO config.toml yet — Task 1 creates it at repo root (the ONLY new non-test file).
# NO tests/test_config_repo_default.py yet — Task 2 creates it (the drift-guard test).
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
├── config.toml                 # ← CREATE at REPO ROOT (Task 1; runtime default + Mode A doc)
└── tests/
    └── test_config_repo_default.py  # ← CREATE (Task 2; drift guard: repo config.toml == defaults)
# NOTHING ELSE. No __init__.py in tests/ (pytest discovers test_*.py without it; the package is
# editable-installed so `from voice_typing.config import ...` resolves). No edits to config.py
# (S1 owns it). No install.sh/systemd (P1.M6). No daemon/textproc/feedback/typing_backends (later).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — VALUES MUST EQUAL THE DATACLASS DEFAULTS EXACTLY.
#   The acceptance gate is `VoiceTypingConfig.from_toml_file("config.toml") == VoiceTypingConfig()`.
#   Dataclass __eq__ compares field-by-field; lists compare in ORDER. So:
#     - every scalar must match (device="cuda", backend="wtype", append_space=true, ...);
#     - floats must be floats: write 0.6 and 0.15 (NOT "0.60" is fine, but do not write 1 where 0.6
#       is meant — obviously);
#     - blocklist must list the 5 entries in the EXACT order of FilterConfig's default_factory list:
#       ["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"].
#   The drift-guard test (Task 2) is the final arbiter — if it fails, READ the diff (pytest prints
#   the unequal dataclasses) and reconcile config.toml to the LIVE config.py defaults. (Research §1.)

# CRITICAL #2 — NO UNKNOWN KEYS. tomllib will PARSE [asr]\ncompute_type = "float16" fine, but S1's
#   from_toml passes the section dict as **kwargs to the dataclass __init__, which raises TypeError
#   on any key that is not a field. So config.toml must contain ONLY the 14 valid keys across the
#   four tables. In particular NO compute_type (a §4.4 cuda_check field), NO sample_rate / silero_* /
#   spinner_* / any RealtimeSTT recorder kwarg — those are NOT config keys (they are built by
#   cfg_to_kwargs in the daemon, P1.M4.T1.S1). (Research §2.4; verified live.)

# CRITICAL #3 — MULTI-LINE ARRAYS WITH INLINE COMMENTS DO PARSE (verified), but keep each comment
#   AFTER the comma+string, on the same line, and start every array element on its own line for the
#   blocklist so the per-entry comments are readable. Trailing inline comments after scalar values
#   also parse. A `#` inside a "..." string would be literal (none of our values contain #).
#   (Research §2.1–§2.2; verified live with stdlib tomllib on Python 3.12.10.)

# CRITICAL #4 — PLACEMENT: REPO ROOT, not voice_typing/. S1's _repo_config_path() =
#   Path(__file__).resolve().parent.parent / "config.toml" resolves config.py -> voice_typing/ ->
#   repo root. Put config.toml at /home/dustin/projects/voice-typing/config.toml. It is intentionally
#   NOT inside the wheel (packages=["voice_typing"]); installed runs rely on the XDG candidate that
#   install.sh creates from this file. (system_context.md §2; Research §3.)

# CRITICAL #5 — DO NOT EDIT voice_typing/config.py. S1 owns it. If the live config.py defaults
#   differ from this PRP's verbatim config.toml block (they should not — S1's PRP gives verbatim
#   source), fix config.toml to match config.py, NOT the other way around. The dataclass defaults
#   are the source of truth; config.toml mirrors them. (Item INPUT: "VoiceTypingConfig defaults
#   from P1.M2.T1.S1.")

# CRITICAL #6 — STATE_FILE EMPTY STRING IS INTENTIONAL. state_file = "" is the DEFAULT (not a
#   placeholder to fill in). The comment must explain it resolves lazily to
#   $XDG_RUNTIME_DIR/voice-typing/state.json and that leaving it empty is the normal choice.
#   Do NOT put a guessed path here. (S1 FeedbackConfig.resolved_state_file() semantics; Research §1.)

# CRITICAL #7 — DEVICE="cuda" IS THE DESIRED VALUE, not a guarantee. The comment must state the
#   daemon auto-falls-back to "cpu" (+ smaller models) at startup if ctranslate2 sees no CUDA device
#   (cuda_check.py / PRD §4.4). Do NOT hardcode "cpu" and do NOT re-explain CUDA mechanics in the
#   comment — cross-reference cuda_check. (system_context.md §4 #6.)

# GOTCHA #8 — COMMENTS USE `#`. Every comment is `# ...` (TOML). No C-style //. A `#` starts a
#   comment to end-of-line; on its own line or trailing a value both work. Keep one blank line
#   between tables for readability. (Research §2.5.)

# GOTCHA #9 — ENCODING + TRAILING NEWLINE. Write config.toml UTF-8 with a single trailing newline
#   (diff-friendly; tomllib tolerates absence but convention matters). The write tool handles this
#   if the content block ends with a newline. (Research §2.6.)

# GOTCHA #10 — FULL PATHS in every bash command. This machine aliases python3->uv run, pip->alias,
#   tmux->zsh plugin. Invoke .venv/bin/python and /home/dustin/.local/bin/uv explicitly. Do NOT use
#   bare `cat`/`sed` to create the file — use the `write` tool (exact content, no shell quoting
#   hazards with the `#` characters). (system_context.md §1.)

# GOTCHA #11 — THE DRIFT-GUARD TEST READS THE REAL repo config.toml (via _repo_config_path()), so
#   it must run AFTER Task 1 creates the file. It is hermetic otherwise: it imports only stdlib +
#   voice_typing.config, asserts ==, no env manipulation. Do NOT monkeypatch _repo_config_path in
#   it (the whole point is to read the REAL repo file). (Research §3.)

# GOTCHA #12 — CREATE config.toml DOES NOT BREAK S1's test_config.py. S1's search-order tests
#   (test_search_order_*) monkeypatch BOTH _xdg_config_path and _repo_config_path to tmp_path, so
#   they never read the real repo config.toml. A real (un-patched) load(None) will now resolve to
#   the repo candidate (this file) and return the defaults — that is the INTENDED runtime behavior.
#   Re-run S1's full suite to confirm green. (Research §3; S1 PRP GOTCHA #13.)
```

## Implementation Blueprint

### Data models and structure

None created. This task produces a **data file** (`config.toml`) and a **test** (`tests/test_config_repo_default.py`). The data model it conforms to is `voice_typing/config.py`'s five dataclasses (owned by S1) — this file is an *instance* of that schema in TOML form. The schema's 14 keys and their exact default values are reproduced in `research/config_toml_defaults_and_toml_syntax.md` §1.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm S1's config.py exists and read its LIVE defaults (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/config.py && echo "ok: config.py exists (S1 done)" || echo "PREFLIGHT FAIL: config.py missing (S1 not done — cannot validate)"
      test ! -e config.toml && echo "ok: config.toml not yet created" || echo "PREFLIGHT FAIL: config.toml already exists"
      test ! -e tests/test_config_repo_default.py && echo "ok: drift-guard test not yet created" || echo "PREFLIGHT FAIL"
      .venv/bin/python -c "import voice_typing.config as m; c=m.VoiceTypingConfig(); print('LIVE DEFAULTS:'); print('  asr:', c.asr); print('  output:', c.output); print('  feedback:', c.feedback); print('  filter:', c.filter)" \
        || echo "PREFLIGHT FAIL: cannot import config"
      .venv/bin/python -c "import pytest; print('pytest', pytest.__version__)" || echo "PREFLIGHT FAIL: pytest missing (S1 should have added it)"
  - EXPECTED: config.py present; config.toml + drift-guard test absent; import prints the LIVE
    defaults; pytest present.
  - RECONCILE: the printed LIVE defaults MUST match the verbatim values in "Task 1 SOURCE" below.
    If any value differs, TRUST THE LIVE config.py and edit the Task 1 block to match before writing
    (CRITICAL #5). The drift-guard test will catch any residual mismatch anyway.

Task 1: CREATE config.toml AT REPO ROOT — use the `write` tool with EXACTLY the content in
        "Task 1 SOURCE" below (reconciled to the LIVE defaults if Task 0 found a discrepancy).
  - FILE: config.toml   (at /home/dustin/projects/voice-typing/config.toml — REPO ROOT, NOT voice_typing/)
  - CONTENT: see "Task 1 SOURCE" (verbatim — header block + [asr]/[output]/[feedback]/[filter] tables,
    every value commented, blocklist as a multi-line array with per-entry comments in default order).
  - DO NOT: place it inside voice_typing/ (CRITICAL #4); add compute_type or any non-schema key
    (CRITICAL #2); reorder the blocklist (CRITICAL #1); edit voice_typing/config.py (CRITICAL #5);
    use shell heredoc to create it (use the write tool — GOTCHA #10).

Task 2: CREATE tests/test_config_repo_default.py — use the `write` tool with EXACTLY the content in
        "Task 2 SOURCE" below. This codifies the item's "verify load() parses with no overrides" as a
        permanent regression (drift guard).
  - FILE: tests/test_config_repo_default.py
  - CONTENT: see "Task 2 SOURCE" (verbatim — imports _repo_config_path + VoiceTypingConfig, asserts
    from_toml_file(repo_default) == VoiceTypingConfig()).
  - DO NOT: monkeypatch _repo_config_path (the test must read the REAL repo file — GOTCHA #11);
    assert on individual fields (assert the WHOLE object == for max coverage); import cuda_check/
    ctranslate2 (keep the test pure).

Task 3: VALIDATE — run the Validation Loop L1–L4 below. Iterate until all gates pass. The drift-guard
        test (L2) is the contract; if it fails, READ the printed diff and reconcile config.toml to the
        live config.py defaults, then re-run.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M2.T1.S2: self-documenting repo config.toml (PRD §4.5 defaults, no overrides) + drift-guard test".
```

#### Task 1 SOURCE — `config.toml` (write verbatim at repo root)

> Reconcile to the LIVE `config.py` defaults from Task 0 first (they should already match; this block mirrors PRD §4.5 and S1's verbatim dataclass source). Comments are the Mode A user doc — keep them plain, concrete, and in lockstep with the value they describe.

```toml
# =============================================================================
# voice-typing configuration
# =============================================================================
#
# WHAT THIS FILE IS
#   Both the daemon's runtime default AND the user-facing config reference (PRD
#   "Mode A"). The values below ARE the built-in defaults: change one to tune
#   the daemon and nothing else needs editing. Every line is commented so this
#   file reads as documentation.
#
# SEARCH ORDER  (first existing file wins; lowest priority is the defaults baked
# into voice_typing/config.py)
#   1. $XDG_CONFIG_HOME/voice-typing/config.toml   (unset/empty -> ~/.config/...)
#   2. <repo>/config.toml                          (this file)
#   3. dataclass defaults in voice_typing/config.py
#   install.sh copies this file to location (1) if it is missing, so your edits
#   survive reinstalls.
#
# SCHEMA SOURCE
#   voice_typing/config.py is the single source of truth for the schema and the
#   default values; this file mirrors it. Keep the two in lockstep: if you change
#   a default in code, change it here too. Unknown keys are REJECTED at load time
#   (a typo raises an error instead of being silently ignored).
#
# =============================================================================


[asr]   # speech recognition: models, device, voice-activity-detection timing

final_model                  = "distil-large-v3"  # final, high-accuracy transcription model (faster-whisper). Sets the quality and latency of the text that actually gets typed.
realtime_model               = "small.en"          # faster model used for live partial previews (shown in the tmux status line while you speak).
language                     = "en"                # ISO-639-1 code, e.g. "en", "es", "fr", "de".
device                       = "cuda"              # "cuda" | "cpu". The daemon AUTO-FALLS-BACK to "cpu" (and smaller models) at startup if ctranslate2 finds no usable CUDA device; see voice_typing/cuda_check.py (PRD 4.4). Usually leave this as "cuda".
post_speech_silence_duration = 0.6                 # seconds of silence after speech before a final is emitted. Lower = snappier but can cut off pauses; higher = fewer false finals but slower.
realtime_processing_pause    = 0.15                # seconds between live partial updates. Lower = more responsive status; higher = less CPU.


[output]   # how typed text leaves the daemon

backend     = "wtype"   # "wtype" (Wayland virtual keyboard, default) | "ydotool" (kernel uinput, TTY/X fallback) | "tmux" (send-keys to a pane; used for tests and SSH). The daemon auto-falls-back from wtype to ydotool on failure.
tmux_target = ""        # used ONLY when backend = "tmux", e.g. "voicetest:0.0" (session:window.pane). Ignored for wtype/ydotool.
append_space = true     # append one trailing space after each final so consecutive utterances flow as words. false = type text verbatim.


[feedback]   # runtime state file + Hyprland notifications

state_file  = ""        # "" (empty) -> resolved at runtime to $XDG_RUNTIME_DIR/voice-typing/state.json (set by systemd user sessions). Set an absolute path to override. If empty AND XDG_RUNTIME_DIR is unset, the daemon raises at write time (no silent fallback). Leave empty for normal use.
hypr_notify = true      # show a hyprctl notify one-liner for start/partial/final/stop. Requires Hyprland; harmless elsewhere (the notify call is skipped when false).
notify_ms   = 2500      # how long the hyprctl notification stays on screen, in milliseconds.


[filter]   # post-recognition text cleanup (consumed by textproc.clean)

min_chars = 2           # finals shorter than this many characters are dropped (filters out "oh", "huh", etc.). Set 1 to type everything.
blocklist = [           # EXACT, case-insensitive matches that are dropped instead of typed. These are the classic Whisper silence hallucinations. Add your own; remove any you actually say.
  "thank you.",                   # most common hallucination
  "thanks for watching.",         # YouTube-style filler
  "you",                          # single-word false positive
  "bye.",                         # sign-off hallucination
  "thank you for watching",       # long-form filler
]
```

#### Task 2 SOURCE — `tests/test_config_repo_default.py` (write verbatim)

```python
"""Drift guard: the repo config.toml must equal the dataclass defaults (PRD §4.5).

Catches the code<->config drift that would otherwise go unnoticed until a user
reloads: if a default changes in voice_typing/config.py, repo config.toml must
change in lockstep (and vice-versa). This is the permanent form of the
P1.M2.T1.S2 acceptance check ("load() parses it with no overrides").

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_config_repo_default.py -v
"""
from __future__ import annotations

from voice_typing.config import VoiceTypingConfig, _repo_config_path


def test_repo_config_toml_equals_defaults():
    """Parsing <repo>/config.toml must yield NO overrides over the defaults."""
    repo_default = VoiceTypingConfig.from_toml_file(_repo_config_path())
    assert repo_default == VoiceTypingConfig(), (
        "repo config.toml drifts from voice_typing/config.py defaults; "
        "edit config.toml (or config.py) so the two match exactly. "
        f"Diff:\n  repo:    {repo_default!r}\n  defaults:{VoiceTypingConfig()!r}"
    )


def test_repo_config_toml_has_no_extra_keys():
    """The repo default must carry only the 14 schema keys (no compute_type etc.)."""
    import tomllib

    with open(_repo_config_path(), "rb") as fh:
        data = tomllib.load(fh)
    expected = {
        "asr": {
            "final_model",
            "realtime_model",
            "language",
            "device",
            "post_speech_silence_duration",
            "realtime_processing_pause",
        },
        "output": {"backend", "tmux_target", "append_space"},
        "feedback": {"state_file", "hypr_notify", "notify_ms"},
        "filter": {"min_chars", "blocklist"},
    }
    assert set(data.keys()) == set(expected.keys()), data.keys()
    for section, keys in expected.items():
        assert set(data[section].keys()) == keys, (section, data[section].keys())
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — values are the defaults, verbatim. The whole point of this file is that loading it
# changes NOTHING relative to VoiceTypingConfig(). So every line is `key = <default>`, never a
# tuned/example value. The drift-guard test enforces this; a single stray override fails L2.
final_model = "distil-large-v3"   # == AsrConfig.final_model default
append_space = true               # lowercase bool, TOML-native (NOT True/False, NOT yes/no)
post_speech_silence_duration = 0.6  # float, matches annotation (NOT "0.6s", NOT 600ms)

# PATTERN 2 — multi-line array with per-element comments (verified parseable by stdlib tomllib).
# Keep element ORDER identical to the dataclass default (list == is order-sensitive). One entry
# per line, comment trailing, trailing comma allowed.
blocklist = [
  "thank you.",          # comment
  "thanks for watching.",
]

# PATTERN 3 — every value line carries an inline `# effect + valid values` comment. This file IS
# the user doc (Mode A), so comments are mandatory, not optional. Enumerate valid values where the
# field is one (device cuda|cpu, backend wtype|ydotool|tmux); give units where it is numeric
# (seconds, ms, characters).
device = "cuda"     # "cuda" | "cpu"
notify_ms = 2500    # milliseconds

# PATTERN 4 — header block documents the whole config model (Mode A, search order, schema source,
# install copy). A user opening this file cold should understand it in ~10 seconds.
# (See Task 1 SOURCE top-of-file comment block.)

# PATTERN 5 — cross-reference, do not duplicate. The [asr].device comment points to cuda_check.py
# and PRD 4.4 rather than re-explaining the CUDA fallback. The header points to voice_typing/config.py
# as the schema source. Single source of truth per fact.
```

### Integration Points

```yaml
CONSUMES — voice_typing/config.py (S1, READ-ONLY):
  - _repo_config_path() resolves to <repo>/config.toml (THIS file's location). from_toml_file() parses
    it. The dataclasses are the equality target for the drift guard. DO NOT EDIT config.py here.

CONSUMES — PRD §4.5 (READ-ONLY):
  - The canonical TOML the header/tables mirror. The search-order + install-copy note at the end of
    §4.5 is reproduced (in prose) in the header comment block.

DOWNSTREAM — P1.M6.T1.S1 (install.sh):
  - install.sh copies THIS repo config.toml to $XDG_CONFIG_HOME/voice-typing/config.toml if absent.
    Therefore this file must be (a) at repo root (install.sh references it by repo-relative path),
    (b) self-documenting (it becomes the user's editable config). install.sh is the ONLY writer of
    the XDG candidate; this task writes only the repo candidate.

DOWNSTREAM — every config consumer reads values that this file SETS to defaults:
  - textproc.clean(cfg.filter) (P1.M2.T2.S1): min_chars=2, blocklist=[5 entries].
  - typing_backends (P1.M3.T1.S1): backend="wtype", tmux_target="", append_space=true.
  - feedback (P1.M3.T2.S1): state_file="" (-> XDG_RUNTIME_DIR), hypr_notify=true, notify_ms=2500.
  - daemon (P1.M4.T1.S1): final_model/realtime_model/language/device; applies the cuda_check override
    on top of device="cuda". None of these are CHANGED by this file (it sets defaults), but its
    existence makes `load(None)` resolve to real values instead of baked-in defaults — same result.

NO DATABASE / NO CONFIG-CODE / NO ROUTES integration. This is a static data file + a test.
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases — system_context.md §1). Run from
> `/home/dustin/projects/voice-typing`. L1 is instant (TOML well-formedness).
> L2 is THE contract (drift guard). L3 is a real search-order smoke. L4 is the scope guard.

### Level 1: TOML well-formedness + placement (no deps beyond stdlib)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) file exists at REPO ROOT (not inside voice_typing/):
test -f config.toml && echo "L1a PASS: config.toml at repo root" || echo "L1a FAIL: config.toml missing"
test ! -f voice_typing/config.toml && echo "L1a PASS: not misplaced inside voice_typing/" || echo "L1a FAIL: wrongly placed in voice_typing/"
# (b) parses under stdlib tomllib (binary mode) with no error:
"$PY" - <<'PYEOF'
import tomllib
with open("config.toml", "rb") as fh:
    data = tomllib.load(fh)
assert set(data) == {"asr", "output", "feedback", "filter"}, data.keys()
print("L1b PASS: valid TOML; top-level tables:", sorted(data))
PYEOF
# (c) every value line has a trailing comment (rough doc-coverage check — Mode A):
"$PY" - <<'PYEOF'
import re
lines = [l.rstrip() for l in open("config.toml", encoding="utf-8")]
# value lines contain '=' (key = value), excluding pure-comment/header lines:
value_lines = [l for l in lines if "=" in l and not l.lstrip().startswith("#") and not l.lstrip().startswith("[")]
missing = [l for l in value_lines if "#" not in l]
print("L1c value lines:", len(value_lines), "| without '#':", len(missing))
assert not missing, f"value lines missing comments: {missing}"
print("L1c PASS: every value line is commented")
PYEOF
# Expected: L1a file at repo root + not in voice_typing/; L1b 4 tables parse; L1c every value line has a '#'.
```

### Level 2: The contract — repo config.toml == dataclass defaults (drift guard)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) direct equality check (the item's acceptance gate, run inline):
"$PY" - <<'PYEOF'
from voice_typing.config import VoiceTypingConfig, _repo_config_path
cfg = VoiceTypingConfig.from_toml_file(_repo_config_path())
assert cfg == VoiceTypingConfig(), f"DRIFT:\n repo={cfg!r}\n def ={VoiceTypingConfig()!r}"
print("L2a PASS: repo config.toml == VoiceTypingConfig() (no overrides)")
print("   resolved via:", _repo_config_path())
PYEOF
# (b) the permanent drift-guard test (Task 2) + S1's loader tests, all green:
"$PY" -m pytest tests/test_config_repo_default.py tests/test_config.py -v
# (c) whole-suite sanity (config.toml existing must not break any S1 test):
"$PY" -m pytest -q
# Expected: L2a equal; L2b all collected tests pass; L2c full suite green (config.toml's existence
# does not affect S1's monkeypatched search-order tests — GOTCHA #12).
```

### Level 3: Real search-order smoke (proves load(None) now resolves to this file)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) With NO XDG config and the repo config.toml present, load(None) finds the repo candidate and
#     returns the defaults (this is the intended runtime behavior, NOT test pollution):
XDG_CONFIG_HOME=/nonexistent-xdg-for-this-smoke "$PY" - <<'PYEOF'
import os
os.environ.pop("XDG_CONFIG_HOME", None)  # belt-and-suspenders: ensure ~/.config has no voice-typing file
from voice_typing.config import VoiceTypingConfig, _repo_config_path
import os.path
print("   repo candidate present?", os.path.isfile(_repo_config_path()), "->", _repo_config_path())
cfg = VoiceTypingConfig.load(None)
assert cfg.asr.final_model == "distil-large-v3"
assert cfg.output.backend == "wtype"
assert cfg == VoiceTypingConfig()
print("L3a PASS: load(None) resolves to repo config.toml -> defaults")
PYEOF
# (b) Editing a value in a COPY overrides only that value (proves the file is a real config, not dead text):
TMPF=$(mktemp /tmp/vt-cfg-XXXX.toml)
sed 's/append_space = true/append_space = false/' config.toml > "$TMPF"
"$PY" - "$TMPF" <<'PYEOF'
import sys
from voice_typing.config import VoiceTypingConfig
cfg = VoiceTypingConfig.load(sys.argv[1])
assert cfg.output.append_space is False, cfg.output.append_space   # overridden
assert cfg.asr.final_model == "distil-large-v3"                     # default kept
print("L3b PASS: copied+edited config overrides append_space only ->", cfg.output.append_space)
PYEOF
rm -f "$TMPF"
# Expected: L3a repo candidate found -> defaults; L3b a one-line edit overrides exactly one field.
```

### Level 4: Scope guards — only config.toml + drift-guard test created; read-only files untouched

```bash
cd /home/dustin/projects/voice-typing
# Only NEW files are config.toml (repo root) + tests/test_config_repo_default.py:
ls config.toml && echo "L4 present: config.toml"
ls tests/test_config_repo_default.py && echo "L4 present: tests/test_config_repo_default.py"
# config.py (S1) must be UNCHANGED by this task:
test -f voice_typing/config.py && echo "L4 ok: config.py still present (verify unchanged via git)"
# Read-only / out-of-scope files UNCHANGED:
for f in PRD.md pyproject.toml uv.lock .gitignore; do
  test -f "$f" && echo "present (verify unchanged): $f"
done
for f in plan/001_be48c74bc590/tasks.json plan/001_be48c74bc590/prd_snapshot.md; do
  test -f "$f" && echo "present (verify unchanged): $f"
done
# No downstream source files created out of scope:
for f in voice_typing/daemon.py voice_typing/textproc.py voice_typing/feedback.py voice_typing/typing_backends.py voice_typing/ctl.py install.sh systemd hypr-binds.conf; do
  test ! -e "$f" && echo "absent (ok): $f" || echo "L4 WARN: $f exists (verify not created by this task)"
done
# Misplacement guard: no config.toml inside the package (would be wrong + not packaged):
test ! -e voice_typing/config.toml && echo "L4 PASS: no config.toml inside voice_typing/" || echo "L4 FAIL: config.toml misplaced in package"
git status --short
# Expected: git status shows config.toml (new, repo root) + tests/test_config_repo_default.py (new).
# Nothing else. pyproject.toml/uv.lock/config.py UNCHANGED.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 `config.toml` at repo root, parses under `tomllib`, every value line commented.
- [ ] L2 `VoiceTypingConfig.from_toml_file("<repo>/config.toml") == VoiceTypingConfig()` (inline + drift-guard test green).
- [ ] L2 `.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -v` → all pass; full suite green.
- [ ] L3 `load(None)` resolves to repo `config.toml` → defaults; a one-line edit overrides exactly one field.
- [ ] L4 only `config.toml` + `tests/test_config_repo_default.py` created; `config.py`/`pyproject.toml`/`uv.lock`/read-only files unchanged; no misplaced/in-scope-violating files.

### Feature Validation
- [ ] All four tables present (`[asr]`/`[output]`/`[feedback]`/`[filter]`) with exactly the 14 schema keys.
- [ ] Every value equals the live `voice_typing/config.py` default (drift-guard test is the proof).
- [ ] `blocklist` has the 5 entries in default order.
- [ ] Header block documents Mode A, search order, schema source, and the `install.sh` copy.
- [ ] Every value line carries an effect + valid-values comment (Mode A doc surface).
- [ ] No `compute_type` or any non-schema key.

### Code Quality Validation
- [ ] `config.toml` is UTF-8 with a trailing newline; TOML 1.0-compliant (stdlib `tomllib` parses it).
- [ ] Comments are plain, present-tense, concrete-units; no marketing filler; cross-references (cuda_check, config.py, PRD) instead of duplicated explanation.
- [ ] `blocklist` is a multi-line array (one entry per line, each commented), not a long inline array.
- [ ] Drift-guard test is hermetic (no env mutation, no monkeypatching of `_repo_config_path`), imports only stdlib + `voice_typing.config`.

### Documentation & Deployment
- [ ] `config.toml` reads as user documentation (Mode A): a cold reader understands the config model from the header in ~10 seconds.
- [ ] `install.sh` (P1.M6.T1.S1) can copy this file verbatim to the XDG candidate; nothing here is machine-specific (no hardcoded `/home/dustin/...`).
- [ ] No new environment variables, no new dependencies.

### Scope Boundary Validation
- [ ] `voice_typing/config.py` NOT edited (S1 owns it).
- [ ] No `daemon.py`/`textproc.py`/`feedback.py`/`typing_backends.py`/`ctl.py`/`install.sh`/systemd/`hypr-binds.conf`.
- [ ] No edits to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.
- [ ] `config.toml` at repo root (NOT inside `voice_typing/`).

---

## Anti-Patterns to Avoid

- ❌ Don't put example/tuned values in `config.toml` — every value is a DEFAULT; loading the file must change nothing (`== VoiceTypingConfig()`). The drift-guard test enforces this.
- ❌ Don't add `compute_type` (or any RealtimeSTT recorder kwarg) — those are not config keys; they'd raise `TypeError` at load. `compute_type` is a `cuda_check` field (§4.4).
- ❌ Don't reorder the `blocklist` — list equality is order-sensitive; match the dataclass default order.
- ❌ Don't write floats as ints or vice versa — `post_speech_silence_duration = 0.6` (float), `notify_ms = 2500` (int); match the annotations so equality is exact.
- ❌ Don't use `True`/`False`/`yes`/`no` — TOML booleans are lowercase `true`/`false`.
- ❌ Don't place `config.toml` inside `voice_typing/` — it belongs at repo root (S1's `_repo_config_path()` expects it there; `install.sh` references it by repo path; it is not packaged in the wheel).
- ❌ Don't edit `voice_typing/config.py` to match `config.toml` — the dataclasses are the source of truth; reconcile `config.toml` to the LIVE config.py if they differ.
- ❌ Don't leave any value line without a comment — this file IS the user doc (Mode A).
- ❌ Don't duplicate CUDA/config-schema explanations inline — cross-reference `cuda_check.py`/`config.py`/PRD (single source of truth).
- ❌ Don't use shell heredoc (`cat > config.toml <<EOF`) to create the file — the `#` characters and quoting are error-prone; use the `write` tool with the verbatim content.
- ❌ Don't monkeypatch `_repo_config_path` in the drift-guard test — it must read the REAL repo file (that's the entire point of a drift guard).
- ❌ Don't create `install.sh`/`daemon.py`/etc. — those are downstream tasks.
- ❌ Don't edit `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.
- ❌ Don't use bare `python`/`uv`/`tmux` (zsh aliases) — use `.venv/bin/python` and `/home/dustin/.local/bin/uv`.
- ❌ Don't make ruff/mypy gates — neither is installed/configured; use `tomllib` parse + `pytest` for validation.

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is a static data file whose exact content is given verbatim (Task 1 SOURCE), and the contract (`from_toml_file == VoiceTypingConfig()`) is codified as both an inline check (L2a) and a permanent test (Task 2). The one real gotcha — multi-line TOML arrays with inline per-element comments — was verified live with stdlib `tomllib` on Python 3.12.10 (research §5), and unknown-key rejection was confirmed to happen at the dataclass layer (so the file must carry only the 14 schema keys). The values are pinned to PRD §4.5 and S1's verbatim dataclass source, with a preflight (Task 0) that reads the LIVE `config.py` defaults and reconciles any discrepancy. The residual uncertainty (−1) is the parallel-execution ordering: S1 must have landed `voice_typing/config.py` (with `from_toml_file` + `_repo_config_path` + pytest) before S2 can validate; if S1 is not yet complete, L1 still passes (pure TOML parse) but L2/L3 block on `config.py` existing — the preflight makes that explicit so the implementer waits rather than guessing.

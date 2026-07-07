# Research — P1.M2.T1.S2: self-documenting default `config.toml`

> Purpose: capture (a) the EXACT default values this file must reproduce (the
> S1/P1.M2.T1.S1 contract), (b) the TOML-syntax facts the file relies on, and
> (c) the install/search-order contract. This is a small, well-bounded task; the
> research is correspondingly tight. No external web research was needed — the
> schema is fully pinned by PRD §4.5 and the sibling S1 PRP, and the one real
> gotcha (multi-line array + inline-comment parsing) was verified empirically.

## 1. The contract: S1's dataclass defaults (verbatim, the single source of truth)

P1.M2.T1.S1 is being implemented in parallel and writes `voice_typing/config.py`
with these defaults — verbatim from its PRP (which itself mirrors PRD §4.5).
**`config.toml`'s values MUST equal these exactly**, so that
`VoiceTypingConfig.from_toml_file("<repo>/config.toml") == VoiceTypingConfig()`
holds (the deliverable's acceptance gate). Equality is dataclass field-wise +
list order-sensitive, so the `blocklist` order below must be preserved.

```python
AsrConfig:        final_model="distil-large-v3", realtime_model="small.en",
                  language="en",
                  device="cuda",                            # "cuda" | "cpu"
                  post_speech_silence_duration=0.6 (float), # 0.6 NOT int 0
                  realtime_processing_pause=0.15 (float)
OutputConfig:     backend="wtype",                          # "wtype"|"ydotool"|"tmux"
                  tmux_target="",
                  append_space=True (bool)
FeedbackConfig:   state_file="", hypr_notify=True (bool), notify_ms=2500 (int)
FilterConfig:     min_chars=2 (int),
                  blocklist=["thank you.","thanks for watching.","you","bye.",
                             "thank you for watching"]      # 5 entries, THIS order
```

Cross-check vs the live `cuda_check.CUDA_DEFAULTS` (the S1 drift-guard target):
`device="cuda"`, `final_model="distil-large-v3"`, `realtime_model="small.en"`.
`compute_type` is **cuda_check's** field (PRD §4.4) — it is NOT a config key and
MUST NOT appear in `config.toml` (it would raise `TypeError` at load — see §2).

**No key beyond these 13 is valid.** The 13 keys, grouped:
`[asr]`: final_model, realtime_model, language, device,
post_speech_silence_duration, realtime_processing_pause (6)
`[output]`: backend, tmux_target, append_space (3)
`[feedback]`: state_file, hypr_notify, notify_ms (3)
`[filter]`: min_chars, blocklist (2) → 6+3+3+2 = 14? No: re-count asr = 6, others
3/3/2 → 14. **Correct count is 14 keys** (final_model, realtime_model, language,
device, post_speech_silence_duration, realtime_processing_pause, backend,
tmux_target, append_space, state_file, hypr_notify, notify_ms, min_chars,
blocklist). A load-time drift guard test asserting the parsed dict's keys equal
exactly these 14 is the strongest typo/config guard.

## 2. TOML 1.0 syntax facts — verified live with stdlib `tomllib` (Python 3.12.10)

The probe below was executed and PASSED (see `## Verification run` at the end):

1. **Multi-line arrays WITH inline per-element comments parse correctly.**
   ```toml
   blocklist = [
     "thank you.",          # Whisper silence hallucination
     "thanks for watching.",
   ]
   ```
   tomllib yields the list in source order, comments stripped. This is what lets
   `config.toml` self-document the blocklist entry-by-entry.

2. **Trailing inline comments after scalar values parse correctly.**
   `device = "cuda"   # "cuda" | "cpu"` → `{"device": "cuda"}`. Enables one
   comment per field line (the file's primary doc surface).

3. **Type fidelity matters for `==`.** tomllib yields `0.6`/`0.15` as `float`,
   `2`/`2500` as `int`, `true`/`false` as `bool`, `""` as `str`. These match the
   dataclass field annotations EXACTLY (S1 pins them), so equality holds. A value
   like `post_speech_silence_duration = 1` (int) would parse as `int` and still
   `== 0.6`? No — `1 == 0.6` is False; but `1 == 1.0` is True. The point: write
   the float defaults as floats (`0.6`, `0.15`) to match annotations verbatim and
   avoid any int-vs-float surprise.

4. **Unknown keys are VALID TOML but rejected by the dataclass layer.** tomllib
   happily parses `[asr]\ncompute_type = "float16"`; S1's
   `AsrConfig(**section)` then raises `TypeError: unexpected keyword argument
   'compute_type'`. This is the (desired) typo-detection feature — do NOT add
   `compute_type`, `sample_rate`, `silero_*`, or any RealtimeSTT recorder kwarg
   to `config.toml`. Those live in `cfg_to_kwargs` (daemon, P1.M4.T1.S1), not
   config.

5. **Comments use `#`** and may appear on their own line or trailing a value. A
   `#` inside a string literal is literal (not a comment). Blocklists/etc. with
   `"` containing `#` are fine; our values contain none.

6. **Encoding**: write the file UTF-8 with a trailing newline. tomllib reads
   binary (`"rb"`); a missing final newline is tolerated but a trailing newline
   is conventional and diff-friendly.

## 3. Placement + search-order + install contract (PRD §4.5; system_context.md §2)

- **Location: repo ROOT**, i.e. `/home/dustin/projects/voice-typing/config.toml`
  (NOT inside `voice_typing/`). The file map in system_context.md §2 lists
  `config.toml` at the same level as `pyproject.toml`, outside the package.
  Rationale: it must be findable by S1's `_repo_config_path()` =
  `Path(__file__).resolve().parent.parent / "config.toml"` (config.py →
  voice_typing/ → repo root). It is intentionally NOT inside the wheel
  (`packages=["voice_typing"]`); installed runs rely on the XDG candidate.
- **Search order (lowest priority = baked-in defaults):**
  1. `$XDG_CONFIG_HOME/voice-typing/config.toml` (unset/empty → `~/.config/...`)
  2. `<repo>/config.toml` (THIS file)
  3. dataclass defaults in `voice_typing/config.py`
  First existing file wins; an explicit `path=` bypasses the search.
- **`install.sh` (P1.M6.T1.S1) copies THIS file to the XDG candidate** if absent,
  so user edits persist across reinstalls. That is why THIS file must be
  self-documenting (Mode A): once copied, it becomes the user's editable config
  reference. Comments must read as user documentation, not developer notes.
- **After S2 lands, a real `VoiceTypingConfig.load(None)` (no monkeypatching)
  resolves to the repo candidate** (this file), returning the defaults. This is
  the intended runtime behavior, NOT a test-pollution problem — S1's
  search-order tests monkeypatch `_repo_config_path`, so they are unaffected by
  this file's existence (verified: `test_search_order_*` patch both path
  helpers to `tmp_path`, never reading the real repo file).

## 4. Self-documenting config conventions (Mode A — this file IS the doc)

- **Header block comment**: state plainly that this file is BOTH the runtime
  default AND the user-facing config reference; document the search order and
  the install.sh copy. A user opening this file first should understand the whole
  config model in 10 seconds.
- **Every value line carries a trailing comment** giving (a) its effect and
  (b) its valid values/enumeration where applicable (`device` `cuda|cpu`,
  `backend` `wtype|ydotool|tmux`, `append_space` `true|false`).
- **Blocklist as a multi-line array**, one entry per line, each with a short
  comment (why it's there). Keep entry order IDENTICAL to the dataclass default
  (list `==` is order-sensitive).
- **Cross-reference, don't duplicate**: point to `voice_typing/config.py` as the
  schema source and to `cuda_check.py`/PRD §4.4 for the device fallback story;
  do not re-explain CUDA mechanics here (single source of truth).
- **Tone**: plain, present-tense, no marketing words. This file is read by humans
  tuning the daemon, so favor concrete units ("seconds of silence", "ms") and
  consequences ("lower = snappier but risks cutting pauses").

## 5. Verification run (executed during PRP research)

Probe `/tmp/_toml_probe.toml` used a multi-line `blocklist` with inline comments,
float/int/bool/empty-str scalars, and trailing comments. Parsed with
`/home/dustin/projects/voice-typing/.venv/bin/python` + stdlib `tomllib`:

```
PARSE OK
ALL ASSERTIONS PASS: multi-line array + inline comments parse correctly under stdlib tomllib
```

A second probe (`[asr]\ncompute_type = "float16"`) confirmed tomllib parses it but
a dataclass `__init__(**section)` rejects it as `TypeError: unexpected keyword
argument 'compute_type'`. Both outcomes are exactly what the deliverable relies
on. Stdlib tomllib is TOML 1.0.0-compliant on Python 3.12.10 (no `tomli` backport
needed).

# Delta PRD: Lite-mode silence threshold + keybind doc reconciliation

**Base PRD:** `PRD.md` (current revision). **Scope of this delta:** a single conceptual change — lite
mode must use its own shorter `post_speech_silence_duration` — plus reconciliation of two stale
keybind references. Everything else in the base PRD is unchanged.

**Size:** Small. ~20 lines of actual spec change. This PRD is deliberately short to match.

---

## 1. What changed in the PRD (diff summary)

Two edits to the base PRD, both localized to the already-shipped lite-mode feature (PRD §4.2ter):

### 1.1 Lite mode gets its own, shorter silence threshold (the substantive change)

New finding, now written into §4.2ter + §4.4 + §4.5 + §6(T7) + §7(#10):

> **The silence gate, not the model, is the perceived-latency bottleneck.** The per-utterance latency
> clock starts at `on_vad_stop`, which fires only AFTER `post_speech_silence_duration` of trailing
> silence. The small model's ~50 ms transcription edge over the large model is swamped by that
> silence wait, which is identical across modes unless lite overrides it. Therefore lite MUST use its
> own shorter `post_speech_silence_duration` — that is what makes lite actually FEEL instant.

Concretely the PRD now mandates:

- **New config key** `[asr] lite_post_speech_silence_duration` (default `0.5`; the PRD gives tunable
  guidance `0.3 = razor-snappy, 0.6 = safe`).
- **Lite recorder construction** overrides `post_speech_silence_duration =
  lite_post_speech_silence_duration` (§4.2ter / §4.4). All other lite kwargs are unchanged.
- **T7** now asserts the lite kwargs carry the SHORTER threshold and that end-to-end stop→text latency
  is materially lower than normal (not merely "not slower").
- **Acceptance #10** now reads: "lite uses its own shorter `post_speech_silence_duration` … so it is
  observably snappier end-to-end, not just faster at transcription."

### 1.2 Keybind reconciliation (doc only — the binds are already correct)

The PRD's keybinds changed from `SUPER ALT,D` (toggle) + `SUPER ALT,F` (toggle-lite) to
`CTRL SUPER ALT,D` (toggle / "big") + `SUPER ALT,D` (toggle-lite / "little"). The actual bind file
(`hypr-binds.conf`) and `README.md` already reflect the new binds (finalized in the prior session,
commit `179ee94`). This delta only has to reconcile **two stale `F` references** that survived:
`config.toml`'s `lite_model` comment and `daemon.py`'s `toggle_lite` docstring.

---

## 2. Current implementation state (verified in the working tree)

Lite mode (PRD §4.2ter) is fully implemented, tested, and committed (prior session; HEAD `6c656b3`).
The recorder lives in a child subprocess; lite is selected by `lite=True` in the construction layer
(`cfg_to_kwargs` / `build_recorder` / `recorder_host._worker_main`). The `lite: bool` ↔ `mode: str`
split is intentional and must not be churned (see `plan/004_607e9cca32b7/architecture/system_context.md`
§4 invariant #6).

Confirmed exact edit sites for THIS delta:

| Concern | File:line | Current state | Required change |
|---|---|---|---|
| Config field | `voice_typing/config.py:58` | only `post_speech_silence_duration` exists | ADD `lite_post_speech_silence_duration: float = 0.5` |
| Config validation | `voice_typing/config.py:81` | numeric-fields validation tuple | ADD `"lite_post_speech_silence_duration"` to it (mirrors the existing `post_speech_silence_duration` entry) |
| TOML | `config.toml:37` | only `post_speech_silence_duration = 0.6` | ADD `lite_post_speech_silence_duration = 0.5` with self-documenting comment |
| Recorder kwargs | `voice_typing/daemon.py:203` | always `cfg.asr.post_speech_silence_duration` for both modes | In the `if lite:` block (already at `:206`), set `kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration` |
| Repo-config test | `tests/test_config_repo_default.py:33-49` | expected `[asr]` key set lacks the new key | ADD `"lite_post_speech_silence_duration"` |
| Stale keybind doc | `config.toml:34` comment | says "`toggle-lite` / SUPER+ALT+F" | change to `Alt+Super+D` |
| Stale keybind doc | `voice_typing/daemon.py:1371-1373` `toggle_lite` docstring | says "pressing F while…" | reword to the `Alt+Super+D` lite key |

**Already correct (do NOT touch):** `hypr-binds.conf` (new binds), `README.md` Hotkey section + config
table + lite section (already on `Ctrl+Alt+Super+D` / `Alt+Super+D`), `status.sh` ⚡ prefix, the
mode-switch / drain / status machinery, the T7 test fixtures (`lite_recorder` → `cfg_to_kwargs(cfg,
lite=True)`).

---

## 3. Requirements

### 3.1 Add `lite_post_speech_silence_duration` and use it in lite construction

- **Config:** add `AsrConfig.lite_post_speech_silence_duration: float = 0.5` with validation (numeric,
  reject bool — mirror the existing `post_speech_silence_duration` validation). Add the line to
  `config.toml` `[asr]` with a comment citing §4.2ter's "silence gate is the perceived bottleneck"
  finding and the `0.3 = razor-snappy / 0.6 = safe` guidance.
- **Construction:** in `cfg_to_kwargs`, the lite branch MUST override
  `kwargs["post_speech_silence_duration"]` to `cfg.asr.lite_post_speech_silence_duration` (it is the
  ONLY timing kwarg lite overrides; device/compute_type/language/`use_main_model_for_realtime` are
  unchanged). Update the `lite` paragraph of the `cfg_to_kwargs` docstring to note this override and
  WHY (the silence-gate finding).
  - **Mode A docs (ride with the work):** `voice_typing/config.py` field doc comment;
    `voice_typing/daemon.py` `cfg_to_kwargs` docstring; `config.toml` comment.

### 3.2 Reconcile the two stale keybind references

- `config.toml:34` `lite_model` comment: `SUPER+ALT+F` → `Alt+Super+D`.
- `voice_typing/daemon.py` `toggle_lite` docstring: replace the "pressing F while…" wording with the
  `Alt+Super+D` lite key, keeping the existing mode-specific toggle semantics wording intact.
  - **Mode A docs (ride with the work):** the two doc strings above.
  - Note: `hypr-binds.conf` and `README.md` are already correct — leave them.

### 3.3 Tests

- **Unit (fast, CUDA-free):** assert `cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"]
  == cfg.asr.lite_post_speech_silence_duration` AND `< cfg.asr.post_speech_silence_duration` (pins
  the override + the shorter-threshold invariant deterministically, not via a flaky GPU timing
  check). `cfg_to_kwargs(cfg, lite=False)` continues to use `post_speech_silence_duration`. Add the
  new key to `tests/test_config_repo_default.py`'s expected `[asr]` set. Add a config-type test that
  `lite_post_speech_silence_duration` is validated (rejects non-numeric / bool), mirroring the
  existing `post_speech_silence_duration` test.
- **T7 integration (`tests/test_feed_audio.py`):** the existing `lite_recorder` fixture (which calls
  `cfg_to_kwargs(cfg, lite=True)`) now carries the shorter threshold automatically. Tighten
  `test_lite_feed_audio_utt_simple` (or the latency test `test_lite_latency_lower_than_normal`) to
  assert the constructed lite recorder kwargs use `lite_post_speech_silence_duration`, and (CUDA-gated)
  that lite end-to-end latency is materially LOWER than normal on `utt_simple.wav` — not merely "not
  more than 25% slower" as the current defensive bound reads. The unit assertion in 3.3 is the
  load-bearing one; the GPU timing check is secondary corroboration.

### 3.4 Sync changeset-level documentation (Mode B — runs last)

- `README.md`: add `asr.lite_post_speech_silence_duration` to the config-tuning table (default `0.5`,
  with the "silence gate is the perceived-latency lever in lite — lower is snappier but may split a
  brief pause into two finals" note), and add one sentence to the Lite-mode subsection stating that
  lite uses its own shorter silence threshold so it feels observably snappier end-to-end (not just at
  transcription). This is the cross-cutting sweep that only makes sense once §3.1–§3.3 land.

---

## 4. Acceptance (definition of done for this delta)

1. `lite_post_speech_silence_duration` exists in `config.py` (default 0.5, validated) and
   `config.toml`.
2. `cfg_to_kwargs(lite=True)` emits `post_speech_silence_duration == lite_post_speech_silence_duration`
   (< normal); `lite=False` is unchanged. Proven by a passing unit test.
3. T7 asserts the shorter lite threshold reaches the real recorder and lite latency is materially
   lower than normal on `utt_simple.wav` (CUDA-gated).
4. No stale `SUPER+ALT+F` / "pressing F" reference remains in `config.toml` or `daemon.py` (the binds
   + README are already correct).
5. README config table + lite section document the new key and the silence-gate rationale.
6. Full suite green: `.venv/bin/python -m pytest tests/ -q` (use full paths; `python3`/`pip`/`tmux`
   are aliased — base PRD §2). Commit on `main` with a message like `Add lite-mode silence threshold
   (lite_post_speech_silence_duration); reconcile stale keybind docs`. Do NOT modify `PRD.md`,
   `.gitignore`, or `plan/004_*`.

## 5. Out of scope

- Changing the actual keybind binds (already correct) or the README hotkey text (already correct).
- The mode-switch reload path, graceful drain, status/`mode` propagation, `status.sh` ⚡ — all
  shipped and unchanged.
- Any change to normal-mode latency or `post_speech_silence_duration`.

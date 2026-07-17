# P1.M3.T1.S2 — Test Design Notes (ACCEPTANCE.md criterion #10 + lite_post_speech_silence_duration)

**Goal:** Update the criterion #10 row in `tests/ACCEPTANCE.md` (the human-readable record of PRD §7
acceptance evidence) so it reflects the landed `asr.lite_post_speech_silence_duration` feature
(P1.M1.T1.S1 config + P1.M2.T1.S1 daemon wiring). This is a **Mode B** changeset-level doc sync — a
single markdown-table row edit. No code, no test run (the item explicitly says do NOT regenerate the
fenced evidence block — that needs the ~5–8 min GPU `test_idle_and_gpu.sh`).

---

## 1. The current criterion #10 row (tests/ACCEPTANCE.md line 39)

```
| 10 | **Lite mode (§4.2ter):** `toggle-lite` arms in lite using ONLY `lite_model` (large model never loads — ~half the VRAM on `nvidia-smi`); `toggle` arms normal; switching costs one bounded reload; `status` + `state.json` report `mode`; both modes honor the graceful drain | **PASS** | `./tests/test_idle_and_gpu.sh` T7 section (mode-switch roundtrip PASS): ... [long evidence] ... Both modes honor the shared graceful drain (`_request_stop`/`_begin_drain`/`_complete_drain` — already implemented, applies identically in lite). (Evidence block below.) |
```

**Gap:** the Criterion column does NOT mention `lite_post_speech_silence_duration` / the silence-gate
clause. The PRD §7 criterion #10 was updated in commit **a66b9d4 "Refine Lite mode latency via
silence gate"** to add: *"lite uses its own shorter `post_speech_silence_duration` (the silence gate
is the perceived bottleneck — §4.2ter) so it is observably snappier end-to-end, not just faster at
transcription."* The ACCEPTANCE.md row must mirror that.

---

## 2. The landed implementation (the evidence to cite — all verified live 2026-07-16)

| Artifact | Location | Content |
|---|---|---|
| Config field | `voice_typing/config.py:59` | `lite_post_speech_silence_duration: float = 0.5  # PRD §4.2ter: lite-mode silence threshold` |
| config.toml | `config.toml:38` | `lite_post_speech_silence_duration = 0.5  # ... the silence gate, not the model, is the perceived-latency bottleneck ...` |
| Daemon wiring | `voice_typing/daemon.py:213` | `kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration` (the cfg_to_kwargs lite override) |
| Unit test (evidence) | `tests/test_daemon.py:216` | `def test_cfg_to_kwargs_lite_uses_shorter_silence_duration` — PASSES (`2 passed` with `-k`, verified) |

The referenced test RUNS and PASSES today: `.venv/bin/python -m pytest tests/test_daemon.py -k
"test_cfg_to_kwargs_lite_uses_shorter_silence_duration or test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal" -q`
→ `2 passed`. So the evidence citation is accurate.

---

## 3. The two exact edits (verified-unique, byte-exact anchors)

The whole criterion #10 row is ONE markdown line (line 39). Two non-overlapping substring edits:

### Edit A — Criterion column: insert the silence-gate clause (before "both modes honor the graceful drain")
- `oldText` (unique — 1 match): `` both modes honor the graceful drain | **PASS** | ``
- `newText`: `` lite uses its own shorter `post_speech_silence_duration` (`asr.lite_post_speech_silence_duration`, default `0.5` — the silence gate, not the model, is the perceived-latency bottleneck, §4.2ter) so it is observably snappier end-to-end, not just faster at transcription; both modes honor the graceful drain | **PASS** | ``
- Effect: the Criterion column now mirrors the updated PRD §7 #10 (the silence-gate requirement).

### Edit B — Evidence column: append the lite silence-gate note (before "(Evidence block below.)")
- `oldText` (unique — 1 match): `` applies identically in lite). (Evidence block below.) | ``
- `newText`: the same prefix + a new **Lite silence gate** note citing config.py:59 + config.toml:38
  + daemon.py:213 + the `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` test + the §4.2ter
  latency insight + the trailing "(Evidence block below.) |".
- Effect: the Evidence column documents that the feature is implemented + cites the unit test.

### Status column: NO change
It is already `**PASS**` and the feature is implemented — keep `**PASS**` (item clause (a)).

---

## 4. Scope (Mode B — what NOT to touch)

- **EDIT ONLY** the criterion #10 row (line 39). Two substring edits, both inside that one row.
- **DO NOT** edit the fenced `=== ACCEPTANCE EVIDENCE ===` block (lines ~62-110) — regenerating it
  needs the ~5-8 min GPU `test_idle_and_gpu.sh` run (item clause (c)).
- **DO NOT** edit README.md (P1.M3.T1.S1 owns it — parallel, README-only).
- **DO NOT** edit config.py / config.toml / daemon.py / test_daemon.py (P1.M1.T1.S1 + P1.M2.T1.S1 —
  landed/parallel; this task only DOCUMENTS them).
- **DO NOT** edit PRD.md / tasks.json / prd_snapshot.md / .gitignore (forbidden/owned by orchestrator).
- **DO NOT** touch criteria 1-9 — out of scope.

---

## 5. Tooling reality (confirmed live 2026-07-16)

- **No test framework applies** to a markdown file. Validation = grep (the field appears in the
  criterion #10 row) + git status (only ACCEPTANCE.md) + a manual accuracy read.
- **Reproduce Unicode EXACTLY** in oldText: the row uses `—` (em-dash), `≥` (in the existing evidence),
  backticks. The two chosen anchors are ASCII-clean (no em-dash/≥ in the oldText itself) so they
  match byte-for-byte; the newText introduces `—` + backticks (markdown renders fine).
- Run greps via the repo shell (zsh aliases python→uv run is irrelevant for grep/git; no venv needed).

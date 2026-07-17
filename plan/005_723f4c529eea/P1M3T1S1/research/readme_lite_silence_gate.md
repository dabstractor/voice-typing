# Research — P1.M3.T1.S1 README.md: Lite mode + config table for `lite_post_speech_silence_duration`

Mode B changeset-level documentation sync (the final README task for the lite-mode silence-gate
feature, PRD §4.2ter / §4.5). Ground truth verified by reading README.md / config.py / config.toml +
the parallel PRP on 2026-07-15. This is a TWO-EDIT markdown task: one new config-table row + one
explanatory sentence in the Lite mode section. No code, no tests.

---

## 1. What landed (the INPUT — the implemented feature)

- `voice_typing/config.py:59` — `lite_post_speech_silence_duration: float = 0.5` (AsrConfig field,
  P1.M1.T1.S1, Complete).
- `config.toml:38` — `lite_post_speech_silence_duration = 0.5  # PRD §4.2ter: lite-mode silence
  threshold (the silence gate, not the model, is the perceived-latency bottleneck). 0.3 =
  razor-snappy (may split a brief pause); 0.6 = safe.` (P1.M1.T1.S1, Complete).
- The daemon wiring (cfg_to_kwargs lite override) is P1.M2.T1.S1 — IN PARALLEL, edits daemon.py +
  test_daemon.py ONLY. It does NOT touch README.md (confirmed by reading its PRP). Disjoint.
- → the README must now (a) list the new knob in the tuning table and (b) explain WHY lite feels
  faster (the silence gate, not the model — the PRD §4.2ter latency-note insight).

## 2. The two README edits (exact anchors verified)

### 2.1 Edit (a) — Configuration tuning table: new row AFTER `asr.post_speech_silence_duration`
The table (README ~line 159-176) currently has `asr.post_speech_silence_duration` (line 160) and
`asr.lite_model` (line 167) but NOT the new field. The item: "Add a new row AFTER the existing
`asr.post_speech_silence_duration` row." Placing it right after post_speech_silence_duration groups
the two silence-threshold rows together (logical). The row must match the table's cell format:
``| `asr.<key>` | `<default>` | <effect> |`` (backticks around key + default; em-dash — is used
throughout the table). Verbatim oldText→newText in the PRP Task 2.

### 2.2 Edit (b) — Lite mode section: silence-gate sentence after "at lower accuracy."
The Lite mode section (README lines 116-128) says "...produces markedly faster finals, at lower
accuracy. Arm it with `voicectl toggle-lite`...". The item: "Add a sentence after the existing
'produces markedly faster finals, at lower accuracy' clause explaining the silence-gate
optimization." Insert between "at lower accuracy." and "Arm it with". Verbatim oldText→newText in
the PRP Task 3. The sentence conveys the PRD §4.2ter insight: the silence gate (not the model) is
the perceived-latency bottleneck; lite's shorter threshold (0.5 vs 0.6) is what makes it FEEL instant.

## 3. Accuracy cross-checks (the README text must match the deployed reality)

- The new row's "0.3 = razor-snappy (may split a brief pause); 0.6 = safe" matches config.toml:38's
  comment verbatim + PRD §4.2ter's tuning guidance. ✓
- "The silence gate, not the model size, is the perceived-latency bottleneck" matches PRD §4.2ter's
  latency note + config.toml:38 + the parallel P1.M2.T1.S1 PRP's rationale. ✓
- Default `0.5` matches config.py:59 + config.toml:38. ✓ (Normal mode stays 0.6 — config.py field.)
- The Lite-mode sentence's "0.5 s vs the normal 0.6" is accurate (normal post_speech_silence_duration
  default 0.6, lite 0.5). ✓

## 4. Scope boundaries

- **README.md ONLY.** `tests/ACCEPTANCE.md` criterion #10 is P1.M3.T1.S2 (a separate task) — do NOT
  touch it here. No config.py/config.toml (P1.M1.T1.S1 owns them — landed). No daemon.py (P1.M2.T1.S1
  — parallel). No PRD.md/tasks.json/prd_snapshot.md/.gitignore.
- **Do NOT touch** the "### Model lifecycle & VRAM" section (line 326+, mentions lite VRAM) — out of
  scope (it's about VRAM, not the silence gate; the item names only the Lite mode section + table).
- **Do NOT touch** the First-run one-liner (line 105 "~half the VRAM and markedly faster finals") —
  it's an accurate brief summary; the detailed "why" lives in the Lite mode section (this edit). Scope
  discipline: edit only the two places the item names.
- **README voice** (line 7-8): terse, command-first, no hand-holding. Em-dash (—) is used throughout;
  backticks wrap config keys + values. Match in the new text. No marketing ("exciting"), no
  changelog voice ("Issue X fixed") — describe behavior.

## 5. Validation (no test framework for markdown)
- `grep -n lite_post_speech_silence_duration README.md` → ≥2 matches (table row + Lite-mode sentence).
- `grep -c '^| \`asr\.' README.md` → the asr-row count rises by 1 (was N; now N+1).
- `git status --porcelain` → only `M README.md`.
- No pytest/ruff/mypy applies to a markdown file (ruff/mypy are for .py). py_compile N/A.

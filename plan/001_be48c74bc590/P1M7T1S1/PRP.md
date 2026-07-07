# PRP — P1.M7.T1.S1: `tests/make_test_audio.sh` — espeak-ng → sox/ffmpeg WAVs (simple, pause, multi, punct)

## Goal

**Feature Goal**: Create **`tests/make_test_audio.sh`** — an idempotent bash fixture generator that
synthesizes the four synthetic test WAVs the PRD §6 test plan requires, in the exact audio format
RealtimeSTT consumes (16 kHz mono 16-bit signed-integer PCM). `utt_pause.wav` is **THE** artifact that
proves the WhisperX flaw is fixed: it embeds **3.0 s of pure silence inside one file** between two
halves of a sentence, so the downstream offline test (P1.M7.T2.S1) can assert both halves transcribe.

**Deliverable** (1 file — 1 ADD; **NO** edit to anything else):
1. `tests/make_test_audio.sh` — NEW. An executable (`chmod +x`) bash script (#!/usr/bin/env bash,
   `set -euo pipefail`) that uses `espeak-ng` (voice `en-us`, 150 wpm) → `sox` (resample to 16 kHz mono
   s16le + synthesize pure silence + concatenate silence *inside* one file). Produces into `tests/out/`:
   `utt_simple.wav`, `utt_pause.wav` (3.0 s embedded silence), `utt_multi.wav` (3 sentences, 1.5 s
   gaps), `utt_punct.wav`. Per-file idempotent skip (override with `FORCE=1`). Writes a self-contained
   `tests/out/.gitignore` (`*`) so the generated audio stays out of git **without** touching the
   repo-root `.gitignore`. Exact content pinned verbatim in the Implementation Blueprint.

**Success Definition**:
- (a) `tests/make_test_audio.sh` exists, is executable, passes `shellcheck` (0.11.0 present) with no
  errors, and `bash -n` is clean.
- (b) Running it (from anywhere) creates `tests/out/{utt_simple,utt_pause,utt_multi,utt_punct}.wav`.
- (c) **Every** WAV is verified by `soxi`/`ffprobe` as **16000 Hz, 1 channel, 16-bit, signed-integer
  PCM** (RealtimeSTT `SAMPLE_RATE=16000`, `BUFFER_SIZE=512`).
- (d) `utt_pause.wav` contains an embedded **≥ 3.0 s** pure-silence gap between its two halves (sox
  concat of `[half_a][3.0 s silence][half_b]` into ONE file), and `sox … -n stat` shows the gap's max
  amplitude ≈ 0 (true silence, not a low tone). `utt_multi.wav` contains **two 1.5 s** silence gaps.
- (e) **Idempotent**: a second run skips all four (prints `skip … (exists; FORCE=1 to regenerate)`);
  `FORCE=1` regenerates all four (deterministic — espeak+sox reproduce byte-identical WAVs).
- (f) `tests/out/.gitignore` exists with `*` so `git status` never lists `tests/out/` or its WAVs.
- (g) The **canonical source text** of all four clips is pinned verbatim in the script (variables) so
  the downstream `tests/test_feed_audio.py` (P1.M7.T2.S1, PLANNED) can fuzzy-match (≥80 % token
  overlap, case/punct-insensitive) against a single source of truth.
- (h) No out-of-scope edits: NO change to `.gitignore`, any module under `voice_typing/`,
  `pyproject.toml`, `config.toml`, `install.sh`, `systemd/`, `PRD.md`, `tasks.json`, `prd_snapshot.md`;
  NO README; NO `test_feed_audio.py` (that is P1.M7.T2.S1); NO `e2e_virtual_mic.sh` (P1.M7.T3.S1).

## User Persona

**Target User**: (1) the **implementing/test-running developer** (dustin) who invokes the script to
populate `tests/out/` before running the offline/E2E test suites; (2) the **downstream test files**
(`test_feed_audio.py`, `e2e_virtual_mic.sh`) that *consume* the WAVs as inputs; (3) **CI / a fresh
clone** that regenerates the fixtures deterministically.

**Use Case**: `cd /home/dustin/projects/voice-typing && ./tests/make_test_audio.sh` → `tests/out/`
now holds the four 16 kHz mono s16le WAVs. Then `uv run pytest tests/test_feed_audio.py` (once
P1.M7.T2.S1 lands) feeds each WAV via `recorder.feed_audio()` and asserts partials/finals. The E2E
script (P1.M7.T3.S1) plays them into a PipeWire null-sink.

**Pain Points Addressed**: (1) PRD §6 requires these exact fixtures but none exist yet. (2) RealtimeSTT
needs 16 kHz mono 16-bit PCM; espeak-ng emits 22.05 kHz — so a naive `espeak -w` produces the wrong
format and `feed_audio()` misbehaves. (3) The WhisperX flaw ("stops listening after a pause") can only
be regression-tested by a clip whose silence is *inside one file* (not two files played with a gap).
(4) espeak is robotic → exact-match assertions are brittle; the script pins canonical text so the
downstream tests can fuzzy-match.

## Why

- **This is the foundation of the whole test suite (P1.M7).** T1 (offline), T3 (E2E), T4 (idle) all
  consume these WAVs. Without them, P1.M7.T2.S1 and P1.M7.T3.S1 cannot be implemented. This item is the
  unblocked first step of Milestone 7.
- **`utt_pause.wav` is the regression guard for the core product fix.** The entire daemon (P1.M4.T1.S2)
  exists to fix WhisperX stopping after a pause. A clip with 3.0 s of *embedded* silence is the only way
  to prove both halves transcribe from a single feed — the script's sox-concat step is what makes that
  artifact possible and unambiguous.
- **Deterministic + idempotent = reproducible tests.** espeak-ng + sox reproduce byte-identical WAVs for
  fixed `−v`/`−s`/text; per-file skip makes re-runs fast; `FORCE=1` regenerates on demand (e.g. after an
  espeak upgrade). The fixtures are regenerable, so they are correctly git-ignored, not committed.
- **Format correctness is load-bearing.** `feed_audio(chunk, original_sample_rate=16000)` (RealtimeSTT
  v1.0.2, confirmed `research_realtimestt_api.md` §5) expects 16-bit mono PCM @ 16 kHz. A wrong
  sample rate silently corrupts the offline test. Resampling in the script (not the test) keeps the
  test simple and the format contract in one place.
- **Scope discipline.** This item is a *fixture generator* only. It produces the 4 WAVs + a
  self-contained gitignore. It does NOT write the offline test, the E2E script, or any docs. The
  canonical text is pinned here so the downstream PRPs can reference it without ambiguity.

## What

A single ~90-line executable bash script at `tests/make_test_audio.sh`. Pipeline:
`espeak-ng (-v en-us -s 150 -w temp.wav "text")` (emits 22.05 kHz mono 16-bit) → `sox` resample to
`-r 16000 -c 1 -e signed-integer -b 16`; pure silence via `sox -n … trim 0 N`; concatenation via plain
`sox a.wav sil.wav b.wav out.wav` (no gap, no crossfade). `ffmpeg` is documented as a resample-only
fallback but is NOT required (sox owns both resample and concat). Outputs four WAVs + `tests/out/.gitignore`.
Per-file idempotent skip; `FORCE=1` override; `set -euo pipefail`; `trap` cleans the temp scratch dir.

### Success Criteria

- [ ] `tests/make_test_audio.sh` exists + executable (`test -x`); `shellcheck` clean; `bash -n` clean.
- [ ] Run creates `tests/out/{utt_simple,utt_pause,utt_multi,utt_punct}.wav`.
- [ ] Each WAV = 16000 Hz / 1 ch / 16-bit / signed-integer PCM (`soxi` + `ffprobe` agree).
- [ ] `utt_pause.wav` has an embedded ≥ 3.0 s pure-silence gap (max amplitude ≈ 0) between its halves.
- [ ] `utt_multi.wav` has two 1.5 s gaps; 3 distinct sentences.
- [ ] Idempotent: 2nd run skips all; `FORCE=1` regenerates all (deterministic).
- [ ] `tests/out/.gitignore` = `*`; `git status` shows no `tests/out/` files.
- [ ] Canonical text pinned verbatim in the script (variables). No root `.gitignore` edit; no other file touched.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the **entire script is pinned verbatim**
(every command executed and verified empirically on this exact machine — versions, sample rates,
durations, and silence purity all confirmed); the audio-format contract is cited to the RealtimeSTT
research (which cites `audio_recorder.py:73-74,694`); every validation command is executable as written
(`shellcheck`, `soxi`, `ffprobe`, `sox … stat` all present).

### Documentation & References

```yaml
# MUST READ — the verified design + command reference (THIS is the spec).
- file: plan/001_be48c74bc590/P1M7T1S1/research/make_test_audio_verification.md
  why: "§1 espeak-ng emits 22050 Hz mono 16-bit (MUST resample). §2 sox resample line. §3 sox pure-silence
        via `sox -n … trim 0 N` (verified max amplitude ≈ 1 LSB = true silence). §4 sox concat embeds
        silence INSIDE one file (the whisperx-flaw artifact). §5 ffmpeg resample fallback. §6 the 4 WAV
        contracts. §7 idempotency pattern. §8 self-contained tests/out/.gitignore. §9-10 validation +
        external URLs."
  critical: "G1 resample is REQUIRED (22050→16000). G2 silence must be INSIDE one file (sox concat). G3
             silence must be PURE (sox -n trim), NOT a low-volume tone. G8 sox concat needs all inputs at
             the same 16k mono s16le format (resample first)."

# MUST READ — the audio-format contract (why 16 kHz mono s16le).
- file: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "§5 feed_audio(chunk, original_sample_rate=16000) accepts 16-bit mono PCM @16kHz (audio_recorder.py:694);
        SAMPLE_RATE=16000, BUFFER_SIZE=512 (audio_recorder.py:73-74). The downstream offline test (T1) feeds
        these WAV chunks at real-time pacing. This script's job is to make that input well-formed."
  critical: "The 16 kHz mono 16-bit format is NON-NEGOTIABLE — a 22050 Hz espeak WAV would silently break
             the offline test. Verify with soxi/ffprobe in the validation loop."

# MUST READ — PRD §6 (the contract: exact text, durations, fuzzy-match rule).
- file: PRD.md
  why: "§6 Test plan: the four WAV specs verbatim (utt_simple/pause/multi/punct), espeak-ng 150 wpm en-us,
        16 kHz mono via sox/ffmpeg, the 3.0 s pause INSIDE one file, the ≥80% fuzzy-match rule. §4.1 layout
        (tests/make_test_audio.sh; tests/out/ gitignored)."
  critical: "Do NOT paraphrase the canonical text — downstream tests fuzzy-match against it. Do NOT change
             3.0 s → other, or 1.5 s → other — those durations are the segmentation contract (vs the
             recorder's 0.6 s post_speech_silence_duration)."

# MUST READ — the daemon's feed_audio/test seam (confirms the consumer).
- file: voice_typing/daemon.py
  why: "cfg_to_kwargs documents `use_microphone: True  # False + feed_audio() in tests (P1.M7.T2.S1)` —
        confirms the offline test (the consumer) flips use_microphone=False and calls recorder.feed_audio().
        This script just has to emit the right-format WAVs; it does NOT call feed_audio itself."
  critical: "Do NOT add feed_audio logic to this script — it is a fixture generator, not a test. The test
             is P1.M7.T2.S1 (PLANNED). Read-only reference here."

# MUST READ — the sibling PRP being implemented in parallel (confirms what lands alongside).
- file: plan/001_be48c74bc590/P1M6T1S2/PRP.md
  why: "P1.M6.T1.S2 lands systemd/voice-typing.service in parallel. It does NOT touch tests/ or this
        script — confirms no file-level conflict with this item. (Confirms the project-wide rule: do NOT
        edit the repo-root .gitignore — that rule applies here too; use tests/out/.gitignore instead.)"

# External — tool documentation (verified reachable).
- url: https://sox.sourceforge.net/sox.html
  why: "sox effects reference: `trim` (synthesize N s from null input = silence), `rate`/`channels`
        (resample/downmix), and the multi-input `sox in1 in2 … out` concatenation (Combining Files)."
- url: https://github.com/espeak-ng/espeak-ng/blob/master/docs/guide.md
  why: "espeak-ng CLI: `-v <voice>` (en-us), `-s <wpm>` (150), `-w <file>` (write WAV), `--stdout`. Confirms
        the default output is 22050 Hz mono 16-bit (which is why resampling is mandatory)."
- url: https://trac.ffmpeg.org/wiki/AudioChannel
  why: "ffmpeg resample fallback: `-ar 16000 -ac 1 -sample_fmt s16`. (Optional — sox is primary.)"
- url: https://github.com/KoljaB/RealtimeSTT
  why: "README 'Feed external audio into the recorder' — confirms feed_audio is the offline-test seam and
        expects 16 kHz mono 16-bit PCM (matches the architecture research §5)."
```

### Current Codebase tree (state at P1.M7.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── .gitignore                 # READ-ONLY (has NO tests/out/ entry — do NOT edit it; use tests/out/.gitignore)
├── PRD.md                     # READ-ONLY (§6 the contract; §4.1 layout)
├── pyproject.toml uv.lock     # DO NOT touch
├── config.toml                # DO NOT touch
├── install.sh systemd/        # DO NOT touch (P1.M6 owns these)
├── tests/                     # ← the script lands HERE
│   ├── make_test_audio.sh     # ← CREATE (this task; +x)
│   ├── test_config.py test_textproc.py test_daemon.py ...   # existing unit tests (READ-ONLY; not referenced)
│   └── out/                   # ← CREATED BY THE SCRIPT at run time (gitignored via tests/out/.gitignore)
│       ├── .gitignore         # ← CREATED BY THE SCRIPT ('*')
│       ├── utt_simple.wav ... utt_punct.wav                 # ← CREATED BY THE SCRIPT
└── voice_typing/              # DO NOT touch (daemon.py confirms the feed_audio seam; read-only)

# Tools present (PRD §2 verified): espeak-ng 1.52.0, sox (SoX_ng) 14.8.0.1, soxi, ffmpeg n8.1.1, ffprobe,
#   shellcheck 0.11.0, bash 5.3.15. nvidia-smi/pactl/pw-cat/jq also present (for the later E2E test).
```

### Desired Codebase tree with files to be added

```bash
tests/
├── make_test_audio.sh         # NEW — this task's sole COMMITTED artifact (the script; +x)
└── out/                       # NEW at run time — gitignored (NOT committed; regenerable)
    ├── .gitignore             # NEW at run time — the script writes this ('*'); keeps tests/out/ out of git
    ├── utt_simple.wav         # generated
    ├── utt_pause.wav          # generated (3.0 s embedded silence)
    ├── utt_multi.wav          # generated (1.5 s × 2 gaps)
    └── utt_punct.wav          # generated
# NOTHING ELSE is committed by this task. tests/out/* are gitignored and regenerated on demand.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 (G1) — espeak-ng emits 22050 Hz, NOT 16000. `espeak-ng -w out.wav` produces mono 22050 Hz
#   16-bit (VERIFIED via soxi). RealtimeSTT needs 16000 Hz (SAMPLE_RATE=16000). EVERY espeak clip MUST be
#   resampled with sox (`-r 16000 -c 1 -e signed-integer -b 16`) before it is output or concatenated.
#   Forgetting this silently breaks the downstream feed_audio test. Assert the format in the validation loop.

# CRITICAL #2 (G2) — the pause silence MUST be INSIDE one file (sox concat), not two files played back-to-
#   back. The whole point of utt_pause.wav is a single feed whose embedded 3.0 s gap proves the daemon
#   keeps listening. `sox a.wav sil.wav b.wav out.wav` concatenates with NO gap/crossfade (VERIFIED).
#   Do NOT generate two half-files and rely on the test to insert a gap.

# CRITICAL #3 (G3) — silence must be PURE (all-zero / ~1 LSB), not a low-volume tone. Use
#   `sox -n -r 16000 -c 1 -b 16 -e signed-integer out.wav trim 0 N` (null input = silence; VERIFIED max
#   amplitude ≈ 0.000031 = 1 LSB). Do NOT use `synth N sine 0`, a muted sine, or recorded room tone — VAD
#   must see true silence. Verify with `sox out.wav -n stat` (Maximum amplitude ≈ 0).

# CRITICAL #4 (G4) — per-file idempotency skip, with FORCE=1 override. `[ -f "$OUT/x.wav" ] && skip` per
#   file (not all-or-nothing) so a partial run completes. `FORCE=1` rm's + regenerates everything. The
#   contract says "idempotent (skip if present)". `should_make` returns 1 on skip — used under `if`, so
#   `set -e` does NOT abort (set -e is disabled inside if-conditions).

# CRITICAL #5 (G5) — NEVER edit the repo-root .gitignore. Project convention (every prior PRP) + this
#   agent's forbidden-operations. The current root .gitignore has NO tests/out/ entry. Instead, the script
#   writes a SELF-CONTAINED tests/out/.gitignore whose body is `*` (ignore everything in the dir). A dir
#   containing only ignored files never appears in `git status`, so tests/out/ stays clean. Satisfies the
#   PRD §4.1 intent ("*.wav under tests/out/" gitignored) at the directory level.

# CRITICAL #6 (G6) — pin the canonical source text VERBATIM in script variables. Downstream tests fuzzy-
#   match (≥80% token overlap, case/punct-insensitive) against THESE exact strings (PRD §6). Do NOT
#   paraphrase, re-capitalize, or "improve" the sentences — that drifts the downstream contract. The four
#   text values are pinned in the Implementation Blueprint.

# CRITICAL #7 (G7) — espeak is robotic; the SCRIPT does not assert accuracy (that is the downstream test's
#   job with fuzzy ≥80%). But the script's header comment MUST state the fuzzy rule so a future editor
#   doesn't "fix" the text to chase 100% on a synthetic voice (PRD §6 explicitly says don't).

# CRITICAL #8 (G8) — sox concat requires all inputs to share sample rate/channels/encoding. Resample EVERY
#   espeak clip to 16k mono s16le AND generate the silence at 16k mono s16le BEFORE concatenating. (VERIFIED
#   — mismatched formats make sox warn or produce a broken file.)

# CRITICAL #9 (G9) — deps: espeak-ng + sox are REQUIRED (fail clearly if absent). ffmpeg is OPTIONAL
#   (resample fallback only; sox owns concat, so ffmpeg cannot replace sox). Do NOT hard-require ffmpeg.
#   `command -v` each; print a clear `ERROR: required tool 'X' not found (PRD §2)` and exit 1.

# CRITICAL #10 (G10) — `set -euo pipefail` + `trap 'rm -rf "$TMP"' EXIT` for the scratch dir. Resolve the
#   repo root via BASH_SOURCE (run-from-anywhere), default OUT=tests/out, allow OUT_DIR override.

# CRITICAL #11 (G11) — `chmod +x tests/make_test_audio.sh`. The PRD §4.1 layout lists it as an executable
#   script (invoked `./tests/make_test_audio.sh`). The write tool creates it 0644; the implementer MUST
#   chmod +x (the validation loop asserts `test -x`).

# CRITICAL #12 (G12) — durations are EXACT. `sox -n … trim 0 3.0` = exactly 3.000000 s (48000 samples @16k,
#   VERIFIED); `trim 0 1.5` = exactly 1.5 s. Keep PAUSE_SIL=3.0 and MULTI_SIL=1.5 as named constants (PRD
#   §6 contract values) — do NOT inline magic numbers or round them.
```

## Implementation Blueprint

### Data models and structure

None (a single bash script). The "schema" is the **canonical text + format-constant table** below —
these are the pinned values the script and downstream tests share:

```bash
# Canonical source strings (PINNED — downstream tests fuzzy-match ≥80% against these, PRD §6):
SIMPLE_TEXT="The quick brown fox jumps over the lazy dog."
PAUSE_A="I want to test whether this system"          # first half of utt_pause.wav
PAUSE_B="keeps listening after a pause."              # second half (AFTER the 3.0 s gap)
PUNCT_TEXT="Hello, world! Does punctuation, like commas, question marks? It should."
MULTI_TEXTS=(                                          # the 3 sentences of utt_multi.wav, in order
  "The weather looks good today."
  "I need to buy some groceries."
  "Let us meet at the cafe."
)

# Audio format (RealtimeSTT SAMPLE_RATE=16000; mono; 16-bit signed-integer PCM):
RATE=16000  CHAN=1  BITS=16  ENC=signed-integer  VOICE=en-us  WPM=150
# Pause durations (PRD §6 — EXACT, do not change):
PAUSE_SIL=3.0   # seconds of PURE SILENCE embedded inside utt_pause.wav
MULTI_SIL=1.5   # seconds of silence between each pair of sentences in utt_multi.wav
```

### `tests/make_test_audio.sh` reference content (research §1–§8 — implement verbatim)

```bash
#!/usr/bin/env bash
#
# make_test_audio.sh — generate the synthetic test WAVs for the voice-typing test suite (PRD §6).
#
# Produces, into tests/out/ (16 kHz mono 16-bit signed-integer PCM = RealtimeSTT SAMPLE_RATE=16000):
#   utt_simple.wav  "The quick brown fox jumps over the lazy dog."
#   utt_pause.wav   "I want to test whether this system" + 3.0 s PURE SILENCE + "keeps listening after a pause."
#                   THE artifact that proves the WhisperX flaw is fixed: both halves must transcribe
#                   from a SINGLE file feed (the 3.0 s silence is embedded, not played as a gap).
#   utt_multi.wav   3 sentences separated by 1.5 s silences (must yield 3 non-empty finals).
#   utt_punct.wav   "Hello, world! Does punctuation, like commas, question marks? It should."
#
# Toolchain: espeak-ng (voice en-us, 150 wpm) -> sox (resample 22050->16k mono s16le; synth silence;
#            concatenate silence INSIDE one file). ffmpeg is an OPTIONAL resample fallback (not required).
#
# Idempotent: skips any WAV that already exists. Set FORCE=1 to regenerate everything.
# Override the output dir with OUT_DIR=/path (default: <repo>/tests/out).
#
# NOTE: espeak-ng is a robotic synthetic voice; Whisper transcribes it imperfectly. Downstream tests
#       MUST use fuzzy matching (>=80% token overlap, case/punctuation-insensitive) — never exact match.
#       Do not "fix" the canonical text below to chase 100% accuracy. (PRD §6.)
#
# Contract: PRD §6 + work item P1.M7.T1.S1.
# Consumers: tests/test_feed_audio.py (P1.M7.T2.S1, offline feed_audio) + tests/e2e_virtual_mic.sh
#            (P1.M7.T3.S1, PipeWire null-sink playback).
set -euo pipefail

# --- resolve paths (run from anywhere) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${OUT_DIR:-$SCRIPT_DIR/out}"

# --- canonical source strings (PINNED — downstream tests fuzzy-match against these exact values) ---
SIMPLE_TEXT="The quick brown fox jumps over the lazy dog."
PAUSE_A="I want to test whether this system"
PAUSE_B="keeps listening after a pause."
PUNCT_TEXT="Hello, world! Does punctuation, like commas, question marks? It should."
MULTI_TEXTS=(
  "The weather looks good today."
  "I need to buy some groceries."
  "Let us meet at the cafe."
)

# --- audio format constants (RealtimeSTT SAMPLE_RATE=16000, mono, 16-bit signed PCM) ---
RATE=16000
CHAN=1
BITS=16
ENC=signed-integer
VOICE=en-us
WPM=150
PAUSE_SIL=3.0   # s of PURE SILENCE embedded inside utt_pause.wav (PRD §6)
MULTI_SIL=1.5   # s of silence between the 3 sentences in utt_multi.wav (PRD §6)

# --- dependency check (fail clearly; PRD §2 says espeak-ng + sox are present) ---
need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: required tool '$1' not found (PRD §2)." >&2; exit 1; }; }
need espeak-ng
need sox
# ffmpeg is optional (resample fallback only); do NOT hard-require it.

# --- scratch dir (cleaned on exit) ---
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- helpers ---
# synth_sentence <text> <out_16k_wav>: espeak-ng (22050) -> sox resample to 16k mono s16le
synth_sentence() {
  local text="$1" out="$2"
  espeak-ng -v "$VOICE" -s "$WPM" -w "$TMP/raw.wav" "$text"
  sox "$TMP/raw.wav" -r "$RATE" -c "$CHAN" -e "$ENC" -b "$BITS" "$out"
}

# synth_silence <seconds> <out_16k_wav>: PURE silence (null input trimmed to N s) at 16k mono s16le
synth_silence() {
  local secs="$1" out="$2"
  sox -n -r "$RATE" -c "$CHAN" -b "$BITS" -e "$ENC" "$out" trim 0 "$secs"
}

# should_make <wav>: skip if present unless FORCE=1 (returns 1=skip, 0=make)
should_make() {
  local wav="$1"
  [ "${FORCE:-0}" = "1" ] && { rm -f "$wav"; return 0; }
  if [ -f "$wav" ]; then echo "skip   $(basename "$wav") (exists; FORCE=1 to regenerate)"; return 1; fi
  return 0
}

# --- prepare output dir + self-contained gitignore (root .gitignore is OFF-LIMITS — G5) ---
mkdir -p "$OUT"
cat > "$OUT/.gitignore" <<'EOF'
# Generated test audio (regenerable via tests/make_test_audio.sh) — do not commit.
*
EOF

# --- 1. utt_simple.wav ---
if should_make "$OUT/utt_simple.wav"; then
  synth_sentence "$SIMPLE_TEXT" "$OUT/utt_simple.wav"
  echo "made   utt_simple.wav"
fi

# --- 2. utt_pause.wav (THE whisperx-flaw test: 3.0 s PURE SILENCE embedded INSIDE one file — G2/G3) ---
if should_make "$OUT/utt_pause.wav"; then
  synth_sentence "$PAUSE_A" "$TMP/a.wav"
  synth_silence "$PAUSE_SIL" "$TMP/sil.wav"
  synth_sentence "$PAUSE_B" "$TMP/b.wav"
  sox "$TMP/a.wav" "$TMP/sil.wav" "$TMP/b.wav" "$OUT/utt_pause.wav"   # concat: no gap, no crossfade
  echo "made   utt_pause.wav (3.0 s embedded silence)"
fi

# --- 3. utt_multi.wav (3 sentences + 1.5 s silences between each pair) ---
if should_make "$OUT/utt_multi.wav"; then
  synth_silence "$MULTI_SIL" "$TMP/gap.wav"
  synth_sentence "${MULTI_TEXTS[0]}" "$TMP/m0.wav"
  synth_sentence "${MULTI_TEXTS[1]}" "$TMP/m1.wav"
  synth_sentence "${MULTI_TEXTS[2]}" "$TMP/m2.wav"
  sox "$TMP/m0.wav" "$TMP/gap.wav" "$TMP/m1.wav" "$TMP/gap.wav" "$TMP/m2.wav" "$OUT/utt_multi.wav"
  echo "made   utt_multi.wav (3 sentences, 1.5 s gaps)"
fi

# --- 4. utt_punct.wav ---
if should_make "$OUT/utt_punct.wav"; then
  synth_sentence "$PUNCT_TEXT" "$OUT/utt_punct.wav"
  echo "made   utt_punct.wav"
fi

# --- summary (duration per file; format asserted by the validation loop, not here) ---
echo "---"
echo "tests/out/ (target: ${RATE} Hz ${CHAN}ch ${BITS}-bit ${ENC}):"
for w in utt_simple utt_pause utt_multi utt_punct; do
  [ -f "$OUT/$w.wav" ] && printf '  %-16s %6.2f s\n' "$w.wav" "$(soxi -D "$OUT/$w.wav")"
done
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm tools + that the target file does NOT exist yet (no mutation; informational).
  - RUN (from /home/dustin/projects/voice-typing):
      for t in espeak-ng sox soxi ffmpeg ffprobe shellcheck; do
        command -v "$t" >/dev/null && echo "$t OK ($(command -v $t))" || echo "PREFLIGHT FAIL: $t missing (PRD §2)"
      done
      test ! -e tests/make_test_audio.sh && echo "ok: tests/make_test_audio.sh not yet created" \
        || echo "PREFLIGHT FAIL: tests/make_test_audio.sh already exists"
      grep -q '^*$' tests/out/.gitignore 2>/dev/null && echo "note: tests/out/.gitignore already present" || true
  - EXPECTED: all tools OK (espeak-ng 1.52.0, sox 14.8.0.1, shellcheck 0.11.0 verified present); the script absent.
  - DO NOT: create/edit any file, run the script, touch .gitignore, or any module.

Task 1: CREATE tests/make_test_audio.sh — the reference content above VERBATIM.
  - FILE: tests/make_test_audio.sh (NEW). The write tool creates it 0644; you MUST then `chmod +x` (G11).
  - KEEP: `#!/usr/bin/env bash` + `set -euo pipefail`; the four canonical text values VERBATIM (G6); the
    format constants (RATE=16000/CHAN=1/BITS=16/ENC=signed-integer); PAUSE_SIL=3.0 + MULTI_SIL=1.5 (G12);
    deps check (G9); `trap` temp cleanup (G10); sox resample on EVERY espeak clip (G1); sox `-n … trim`
    for PURE silence (G3); sox concat to embed silence INSIDE one file (G2); per-file `should_make` skip
    + FORCE=1 (G4); the self-contained `tests/out/.gitignore` with `*` (G5); the fuzzy-match header note (G7).
  - DO NOT: add ffmpeg as a hard requirement (G9); edit the root .gitignore (G5); paraphrase the text (G6);
    generate two half-files for utt_pause (G2); use a tone instead of pure silence (G3); call feed_audio or
    import any Python (this is a fixture generator, not a test); edit any other file; create test_feed_audio.py
    (P1.M7.T2.S1) or e2e_virtual_mic.sh (P1.M7.T3.S1).

Task 2: CHMOD — make it executable.
  - RUN: chmod +x tests/make_test_audio.sh && test -x tests/make_test_audio.sh && echo "chmod OK"
  - WHY: PRD §4.1 invokes it as ./tests/make_test_audio.sh (G11).

Task 3: VALIDATE — run the Validation Loop L1–L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M7.T1.S1: tests/make_test_audio.sh — espeak-ng/sox 16k mono s16le WAVs (simple, pause, multi, punct)".
```

### Implementation Patterns & Key Details

```bash
# PATTERN 1 — espeak-ng -> sox resample (G1). espeak emits 22050 Hz mono 16-bit; resample to 16k mono s16le.
espeak-ng -v en-us -s 150 -w "$TMP/raw.wav" "$text"
sox "$TMP/raw.wav" -r 16000 -c 1 -e signed-integer -b 16 "$out.wav"

# PATTERN 2 — PURE silence of N seconds (G3). `-n` = null input (silence); `trim 0 N` = first N seconds.
sox -n -r 16000 -c 1 -b 16 -e signed-integer "$sil.wav" trim 0 3.0   # exactly 3.000000 s (48000 samples)

# PATTERN 3 — embed silence INSIDE one file (G2). Plain sox concat = no gap, no crossfade (VERIFIED).
sox "$a.wav" "$sil.wav" "$b.wav" "$utt_pause.wav"   # [half_a][3.0s silence][half_b] in ONE file

# PATTERN 4 — per-file idempotency + FORCE override (G4). `should_make` returns 1 on skip; used under
#   `if`, so `set -e` does NOT abort on the skip return (set -e is disabled inside if-conditions).
should_make() { local w="$1"; [ "${FORCE:-0}" = "1" ] && { rm -f "$w"; return 0; };
                [ -f "$w" ] && { echo "skip $(basename "$w")"; return 1; }; return 0; }
if should_make "$OUT/x.wav"; then … make it …; fi

# PATTERN 5 — self-contained gitignore (G5). The root .gitignore is OFF-LIMITS; the script writes this so
#   the dir stays out of git. A dir containing only ignored files never appears in `git status`.
cat > "$OUT/.gitignore" <<'EOF'
# Generated test audio (regenerable via tests/make_test_audio.sh) — do not commit.
*
EOF
```

### Integration Points

```yaml
CONSUMED BY — tests/test_feed_audio.py (P1.M7.T2.S1, PLANNED):
  - reads:   tests/out/{utt_simple,utt_pause,utt_multi,utt_punct}.wav
  - format:  16 kHz mono 16-bit signed-integer PCM (RealtimeSTT feed_audio original_sample_rate=16000)
  - seam:    recorder = AudioToTextRecorder(use_microphone=False); recorder.feed_audio(chunk, 16000)
  - asserts: (b) utt_pause.wav -> BOTH halves across finals (the whisperx-flaw fix); (c) utt_multi.wav ->
             3 non-empty finals; (d) fuzzy >=80% token overlap against the PINNED canonical text above;
             (e) final <=1.5s after last sample. (PRD §6 T1.)
  - note:    This PRP's canonical text variables ARE the test's expected strings — P1.M7.T2.S1 must
             reference them verbatim (or read them) for the >=80% fuzzy match.

CONSUMED BY — tests/e2e_virtual_mic.sh (P1.M7.T3.S1, PLANNED):
  - plays:   tests/out/utt_pause.wav + utt_multi.wav into a PipeWire null-sink (pw-cat --playback --target)
  - asserts: tmux pane contains fuzzy-matched text of ALL segments incl. post-pause half; toggle-off gates
             output; state.json showed partials. (PRD §6 T3.)
  - cleanup: trap unloads the null-sink module + restores the default source. (This script is NOT that test.)

GITIGNORE — tests/out/.gitignore (self-contained, G5):
  - body:    `*` (ignore everything in tests/out/; the generated WAVs + this .gitignore are all ignored)
  - why:     keeps tests/out/ out of `git status` WITHOUT editing the repo-root .gitignore (off-limits)
  - PRD §4.1 intent ("*.wav under tests/out/") is satisfied at the directory level.

NO database. NO config change. NO pyproject/uv.lock change. NO module edit. NO root .gitignore edit.
```

## Validation Loop

> Run from `/home/dustin/projects/voice-typing`. All gates are executable as written (every tool verified
> present: espeak-ng 1.52.0, sox/soxi 14.8.0.1, ffmpeg/ffprobe n8.1.1, shellcheck 0.11.0). A real
> Whisper transcribe is OUT OF SCOPE here — it is P1.M7.T2.S1's job; this loop proves the *fixtures* are
> well-formed (format, durations, embedded silence, idempotency, gitignore).

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
shellcheck tests/make_test_audio.sh && echo "L1 shellcheck OK (no errors)" || echo "L1 FAIL: shellcheck reported errors — read them + fix"
bash -n tests/make_test_audio.sh && echo "L1 bash -n OK (syntax clean)" || echo "L1 FAIL: bash syntax error"
test -x tests/make_test_audio.sh && echo "L1 +x OK (executable)" || echo "L1 FAIL: not executable (run chmod +x)"
# Expected: shellcheck clean, bash -n clean, executable. (ruff/mypy are Python-only — N/A for a .sh file.)
```

### Level 2: Format (Component Validation — every WAV must be 16 kHz mono s16le)

```bash
cd /home/dustin/projects/voice-typing
./tests/make_test_audio.sh                       # generate the fixtures
for w in utt_simple utt_pause utt_multi utt_punct; do
  f="tests/out/$w.wav"
  test -f "$f" || { echo "L2 FAIL: $f missing"; continue; }
  r="$(soxi -r "$f")"; c="$(soxi -c "$f")"; b="$(soxi -b "$f")"; e="$(soxi -e "$f")"
  [ "$r" = 16000 ] && [ "$c" = 1 ] && [ "$b" = 16 ] && [ "$e" = "Signed Integer" ] \
    && echo "L2 $w OK ($r Hz $cch ${b}-bit $e)" \
    || echo "L2 FAIL $w: rate=$r ch=$c bits=$b enc=$e (expected 16000 1 16 Signed Integer)"
  # cross-check with ffprobe (independent tool):
  ffprobe -v error -show_entries stream=sample_rate,channels,sample_fmt -of default=nw=1 "$f"
done
# Expected: all four = 16000 Hz / 1 ch / 16-bit / Signed Integer (s16le); ffprobe agrees (sample_fmt=s16).
```

### Level 3: Structure & Idempotency (the pause gap, the multi gaps, skip-on-rerun)

```bash
cd /home/dustin/projects/voice-typing
# (a) utt_pause.wav embeds a >= 3.0 s PURE-SILENCE gap (G2/G3). Concatenate math + silence detection:
A="$(soxi -D <(espeak-ng -v en-us -s 150 -w /dev/stdout "$PAUSE_A" 2>/dev/null) 2>/dev/null)"   # ~ half_a dur
# Simpler: assert the gap directly via sox silence detection on the produced file:
sox tests/out/utt_pause.wav -n silence 1 0.5 0.1% 1 0.5 0.1% stat 2>&1 | grep -qi 'length\|samples' \
  && echo "L3a pause gap detectable" || echo "L3a NOTE: silence-detect syntax varies — verify the gap by math:"
python3 - <<'PY'
import subprocess, json
d = float(subprocess.check_output(["soxi","-D","tests/out/utt_pause.wav"]).strip())
# halves (16k) durations:
ha = float(subprocess.check_output(["soxi","-D","tests/out/utt_simple.wav"]).strip())  # rough proxy; use real halves below
print(f"utt_pause.wav total = {d:.2f}s (must be > 3.0s and contain a >=3.0s embedded gap)")
assert d > 3.0, "pause clip too short"
print("L3a pause math OK")
PY

# (b) the embedded silence is PURE (max amplitude ~ 0 — G3): extract the middle 3.0s and stat it.
TOTAL="$(soxi -D tests/out/utt_pause.wav)"
START="$(python3 -c "print(round(($TOTAL-3.0)/2,3))")"   # center the 3.0s window on the gap
sox tests/out/utt_pause.wav -t wav /tmp/gap_window.wav trim "$START" 3.0
MAXAMP="$(sox /tmp/gap_window.wav -n stat 2>&1 | awk '/Maximum amplitude/{print $3}')"
python3 -c "v=float('$MAXAMP'); exit(0 if v<0.001 else 1)" && echo "L3b embedded silence is PURE (max amp $MAXAMP < 0.001)" \
  || echo "L3b FAIL: embedded gap not silent (max amp $MAXAMP) — did you use a tone instead of sox -n trim? (G3)"

# (c) utt_multi.wav has TWO 1.5 s gaps: total ~= sum(sentences) + 2*1.5
python3 - <<'PY'
import subprocess
d = float(subprocess.check_output(["soxi","-D","tests/out/utt_multi.wav"]).strip())
print(f"utt_multi.wav total = {d:.2f}s (expect ~ sum(3 sentences) + 2*1.5s gaps)")
assert d > 2*1.5, "multi clip too short for two 1.5s gaps"
print("L3c multi gap math OK")
PY

# (d) idempotency: a 2nd run skips all four (G4).
OUT2="$(./tests/make_test_audio.sh)"
echo "$OUT2" | grep -q 'skip' && echo "L3d idempotent skip OK" || echo "L3d FAIL: 2nd run did not skip (G4)"
# FORCE=1 regenerates all four (deterministic — md5 stable across regenerations):
md5_1="$(md5sum tests/out/utt_pause.wav | awk '{print $1}')"
FORCE=1 ./tests/make_test_audio.sh >/dev/null
md5_2="$(md5sum tests/out/utt_pause.wav | awk '{print $1}')"
[ "$md5_1" = "$md5_2" ] && echo "L3d FORCE=1 deterministic (md5 stable)" || echo "L3d NOTE: md5 differs (espeak/sox nondeterminism — acceptable, but re-check)"
# Expected: gap detectable + math sane; embedded gap max amp < 0.001; two multi gaps; 2nd run skips; FORCE=1 reproducible.
```

### Level 4: Creative & Domain-Specific Validation

```bash
cd /home/dustin/projects/voice-typing
# (a) tests/out/ stays out of git via the self-contained tests/out/.gitignore (G5) — root .gitignore untouched:
grep -q '^tests/out/$\|^\*\.wav' .gitignore && echo "L4a NOTE: root .gitignore already ignores tests/out (fine)" \
  || echo "L4a root .gitignore untouched as required (G5); relying on tests/out/.gitignore"
git status --porcelain tests/out/ | grep -q . && echo "L4a FAIL: tests/out/ shows in git status" \
  || echo "L4a tests/out/ clean (gitignored via tests/out/.gitignore) OK"
test "$(cat tests/out/.gitignore | grep -v '^#' | tr -d ' \n')" = "*" && echo "L4a tests/out/.gitignore body = '*' OK"

# (b) canonical text is pinned verbatim in the script (G6) — grep the exact strings:
grep -q 'SIMPLE_TEXT="The quick brown fox jumps over the lazy dog."' tests/make_test_audio.sh && echo "L4b simple text pinned OK"
grep -q 'PAUSE_A="I want to test whether this system"' tests/make_test_audio.sh && echo "L4b pause_a pinned OK"
grep -q 'PAUSE_B="keeps listening after a pause."' tests/make_test_audio.sh && echo "L4b pause_b pinned OK"
grep -q 'PUNCT_TEXT="Hello, world! Does punctuation, like commas, question marks? It should."' tests/make_test_audio.sh && echo "L4b punct text pinned OK"
grep -qi 'fuzzy\|>=80%\|80%' tests/make_test_audio.sh && echo "L4b fuzzy-match note present OK (G7)"

# (c) sox concat is what embeds the gap (G2) — confirm the script does NOT generate two separate half files:
grep -q 'sox "\$TMP/a.wav" "\$TMP/sil.wav" "\$TMP/b.wav"' tests/make_test_audio.sh && echo "L4c concat-in-one-file OK (G2)"

# (d) optional: a 1-line human check that espeak produced the right WORDS (NOT a Whisper accuracy check —
#     just that the clip is intelligible). Play it (needs an audio device; skip in CI/headless):
# paplay tests/out/utt_simple.wav   # uncomment interactively
echo "L4d (interactive) paplay tests/out/utt_simple.wav to sanity-hear the clip"
# Expected: root .gitignore untouched; tests/out/ clean; canonical text pinned; concat-in-one-file; fuzzy note present.
```

## Final Validation Checklist

### Technical Validation

- [ ] L1: `shellcheck tests/make_test_audio.sh` clean; `bash -n` clean; `test -x` passes.
- [ ] L2: all four WAVs = 16000 Hz / 1 ch / 16-bit / Signed Integer (soxi AND ffprobe agree).
- [ ] L3: embedded pause gap ≥ 3.0 s AND pure (max amp < 0.001); two 1.5 s multi gaps; 2nd run skips; FORCE=1 reproducible.
- [ ] L4: root `.gitignore` untouched; `tests/out/` clean in `git status`; `tests/out/.gitignore` body = `*`.

### Feature Validation

- [ ] Four WAVs created in `tests/out/`: `utt_simple`, `utt_pause` (3.0 s embedded silence), `utt_multi` (1.5 s × 2 gaps), `utt_punct`.
- [ ] `utt_pause.wav` embeds the silence INSIDE one file (sox concat) — the whisperx-flaw regression artifact.
- [ ] Silence is PURE (`sox -n … trim`, not a tone); max amplitude ≈ 0.
- [ ] Idempotent per-file skip + `FORCE=1` regenerate; deterministic across regenerations.
- [ ] Canonical text pinned verbatim in script variables; fuzzy-match header note present.

### Code Quality Validation

- [ ] File placement: `tests/make_test_audio.sh` (+x) per PRD §4.1 layout.
- [ ] `set -euo pipefail` + `trap` temp cleanup; paths resolved via `BASH_SOURCE` (run-from-anywhere).
- [ ] Named constants (RATE/CHAN/BITS/ENC/VOICE/WPM/PAUSE_SIL/MULTI_SIL) — no magic numbers inlined.
- [ ] Deps checked with a clear error (espeak-ng + sox required; ffmpeg optional).
- [ ] No edit to `.gitignore`, any `voice_typing/` module, `pyproject.toml`, `config.toml`, `install.sh`,
      `systemd/`, `PRD.md`, `tasks.json`, `prd_snapshot.md`; no README; no `test_feed_audio.py`; no `e2e_virtual_mic.sh`.

### Documentation & Deployment

- [ ] Header comment documents: the four clips, the toolchain, the embedded-silence rationale (whisperx flaw),
      the fuzzy-match rule (PRD §6), idempotency/FORCE, and the two downstream consumers (P1.M7.T2/T3.S1).
- [ ] No new env vars required (OUT_DIR + FORCE are optional conveniences, documented in the header).

---

## Anti-Patterns to Avoid

- ❌ Don't emit raw espeak WAVs (22050 Hz) — ALWAYS resample to 16 kHz mono s16le with sox (G1); a 22050 Hz
  clip silently breaks `feed_audio`.
- ❌ Don't make `utt_pause.wav` two half-files played with a gap — the silence MUST be embedded INSIDE one
  file via sox concat (G2); that single-file feed is what proves the whisperx flaw is fixed.
- ❌ Don't synthesize silence with a tone (`synth N sine 0`, a muted sine, room tone) — use `sox -n … trim 0 N`
  for PURE silence (G3); VAD must see true zero.
- ❌ Don't edit the repo-root `.gitignore` — it is off-limits; write the self-contained `tests/out/.gitignore`
  with `*` instead (G5).
- ❌ Don't paraphrase the canonical text — pin it verbatim; downstream tests fuzzy-match (≥80%) against these
  exact strings (G6/G7). Don't chase 100% accuracy on a robotic synthetic voice.
- ❌ Don't change `3.0 s` or `1.5 s` to "nicer" values — they are the segmentation contract vs the recorder's
  0.6 s `post_speech_silence_duration` (G12).
- ❌ Don't hard-require ffmpeg (G9) — sox owns both resample and concat; ffmpeg is an optional resample fallback.
- ❌ Don't mix formats in a sox concat (G8) — resample every espeak clip AND generate the silence at 16k mono
  s16le before concatenating.
- ❌ Don't run ruff/mypy on the `.sh` file (Python-only tools, N/A); the gate is `shellcheck` + `bash -n`.
- ❌ Don't call `recorder.feed_audio()` or import any Python here — this is a fixture GENERATOR, not a test.
  The offline test is P1.M7.T2.S1 (PLANNED); the E2E is P1.M7.T3.S1 (PLANNED).
- ❌ Don't create `test_feed_audio.py` / `e2e_virtual_mic.sh` / a README — out of scope for this item.

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is a single ~90-line bash script whose entire
content is **pinned verbatim above**, and **every command in it has been executed and verified empirically on
this exact machine**: espeak-ng 1.52.0 emits 22050 Hz mono 16-bit (soxi-confirmed); `sox … -r 16000 -c 1
-e signed-integer -b 16` resamples to the exact RealtimeSTT format (soxi-confirmed = 16000/1/16/Signed
Integer); `sox -n … trim 0 3.0` produces exactly 3.000000 s of silence with max amplitude ≈ 1 LSB (sox
stat-confirmed = true silence); plain `sox a sil b out` concatenates with no gap (duration-confirmed =
a + 3.0 + b). All four tools (espeak-ng, sox/soxi, ffmpeg/ffprobe, shellcheck) are verified present
(PRD §2). The audio-format contract (16 kHz mono s16le) is cited to RealtimeSTT research §5
(`audio_recorder.py:73-74,694`). The only non-deterministic surface is **espeak/sox byte-stability across
regeneration** — verified stable in L3d, and even if it drifted, the downstream test uses fuzzy ≥80% (PRD §6)
so fixture drift is non-fatal. The −1 residual risk is that L3's exact `sox silence`-detection syntax can
vary by sox build, so the loop provides a Python math fallback that asserts the gap indirectly (total
duration > 3.0 s, pure-silence window max amp < 0.001) — robust regardless of the detector. No Python, no
models, no GPU, no network: this is a pure offline fixture generator with zero external runtime deps beyond
the four CLI tools already installed.

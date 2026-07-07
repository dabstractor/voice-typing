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

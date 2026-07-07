# Research — P1.M7.T1.S1: `tests/make_test_audio.sh` (espeak-ng → sox/ffmpeg WAVs)

All commands below were **executed and verified empirically** on this machine (2026-07-07).
Versions present: `espeak-ng` 1.52.0, `sox` (SoX_ng) v14.8.0.1, `ffmpeg` n8.1.1,
`soxi`/`ffprobe`, `shellcheck` 0.11.0, `bash` 5.3.15. PRD §2 confirmed (all tools present).

## 1. espeak-ng output format (verified)

```bash
espeak-ng -v en-us -s 150 -w out.wav "The quick brown fox jumps over the lazy dog."
soxi out.wav   # ->  Channels: 1 | Sample Rate: 22050 | Precision: 16-bit | Encoding: Signed Integer PCM
```

- espeak-ng writes **mono, 22050 Hz, 16-bit signed-integer PCM** by default.
- RealtimeSTT requires **16000 Hz mono 16-bit PCM** (`SAMPLE_RATE=16000`, `BUFFER_SIZE=512`;
  `feed_audio(chunk, original_sample_rate=16000)`). See
  `plan/001_be48c74bc590/architecture/research_realtimestt_api.md` §5 (audio_recorder.py:73-74,694).
- → **every espeak WAV MUST be resampled to 16 kHz mono s16le** before output. sox is the primary
  resampler (it also does concatenation, which ffmpeg cannot do cleanly without a concat list).

Flags: `-v en-us` (voice = English America, confirmed present in `espeak-ng --voices=en`),
`-s 150` (speed = 150 words/min, the PRD §6 contract value), `-w file` (write WAV; do NOT use
`--stdout` here — `-w` to a file is simplest), text passed as the final quoted argument.

## 2. sox resample (verified) — 22050 → 16000 mono s16le

```bash
sox in_22050.wav -r 16000 -c 1 -e signed-integer -b 16 out_16k.wav
soxi out_16k.wav   # -> Sample Rate: 16000 | Channels: 1 | Precision: 16-bit | Signed Integer PCM
```

## 3. sox generate PURE SILENCE (verified) — N seconds at 16 kHz mono s16le

```bash
sox -n -r 16000 -c 1 -b 16 -e signed-integer silence.wav trim 0 3.0
soxi silence.wav            # -> Duration: 00:00:03.00 = 48000 samples  (= 3.0 s @ 16 kHz, exact)
sox silence.wav -n stat     # -> Maximum amplitude: 0.000031  (≈ 1 LSB = effectively pure silence)
```

- `-n` = null input (silence); `trim 0 N` = take the first N seconds. This is the idiomatic sox way
  to synthesize silence of an exact length. Max amplitude ≈ 1/32768 = one quantization bit = true
  digital silence for VAD/Whisper (webrtc+silero thresholds are far above this).
- Optional byte-exact-zero silence: append `--no-dither` (`-r ... -D`). NOT required — 1 LSB is
  inaudible and below every VAD threshold. Keep `trim 0 N` (simple, verified).

## 4. sox CONCATENATE with EMBEDDED silence (verified) — THE WhisperX-flaw test

```bash
# two halves (already resampled to 16k mono s16le) + a 3.0 s silence between, in ONE file:
sox sentence_a_16k.wav silence_3.0s.wav sentence_b_16k.wav utt_pause.wav
soxi utt_pause.wav   # -> Duration: 00:00:07.92  (= a(≈2.5s) + 3.0 + b(≈2.4s))
```

- Plain `sox in1 in2 ... inN out.wav` concatenates with **NO gap and NO crossfade** by default.
- The 3.0 s silence is therefore **inside one file** (PRD §6 / contract requirement) — exactly the
  artifact that proves the WhisperX flaw is fixed: the listen-forever loop must yield BOTH halves
  as finalized utterances (the second half comes AFTER a 3 s pause).
- sox requires all inputs share the same sample rate / channels / encoding for clean concat, so
  resample every espeak clip AND generate the silence at 16 kHz mono s16le first.

## 5. ffmpeg resample FALLBACK (verified) — PRD says "sox/ffmpeg"

```bash
ffmpeg -y -i in_22050.wav -ar 16000 -ac 1 -sample_fmt s16 out_16k.wav
soxi out_16k.wav   # -> 16000 Hz | 1 ch | 16-bit Signed Integer PCM  (identical to sox output)
```

- Use sox as the PRIMARY (it owns the concat step too). ffmpeg is the resample-only fallback if sox
  were ever missing — but it CANNOT replace sox for the silence-insertion step (no clean concat).
  Do NOT make ffmpeg the primary; the script depends on sox's concat + silence synthesis.

## 6. The four WAV contracts (PRD §6 — pinned verbatim)

| file            | content                                                                                       | silence                                |
|-----------------|-----------------------------------------------------------------------------------------------|----------------------------------------|
| `utt_simple.wav`| "The quick brown fox jumps over the lazy dog."                                                 | none                                   |
| `utt_pause.wav` | "I want to test whether this system" + **3.0 s silence** + "keeps listening after a pause."    | 3.0 s, INSIDE one file (sox concat)    |
| `utt_multi.wav` | 3 sentences (see PRP §"Implementation Blueprint") separated by **1.5 s silences**              | 1.5 s × 2, between each pair           |
| `utt_punct.wav` | "Hello, world! Does punctuation, like commas, question marks? It should."                      | none                                   |

- `utt_pause.wav` is THE test that the WhisperX flaw is fixed (both halves transcribed).
- `utt_multi.wav` must yield 3 non-empty finals (1.5 s gap ≫ 0.6 s `post_speech_silence_duration`).
- `utt_punct.wav` exercises punctuation preservation (textproc must keep commas/`?`/`!`).
- **Canonical source strings are pinned in the PRP** so the downstream consumer (P1.M7.T2.S1
  `test_feed_audio.py`, PLANNED) can fuzzy-match (≥80 % token overlap, case/punct-insensitive)
  against a single source of truth. PRD §6: espeak is robotic → NEVER assert exact match.

## 7. Idempotency + determinism (contract)

```bash
mkdir -p "$OUT"
[ -f "$OUT/utt_simple.wav" ] && { echo "skip utt_simple.wav (exists)"; continue; }   # per-file skip
```

- Per-file skip-if-present (the contract says "idempotent (skip if present)"). A `FORCE=1` env var
  re-generates (rm + rebuild) for reproducibility / when espeak is upgraded.
- espeak-ng + sox are **deterministic** for a fixed `-s`/`-v`/text — re-generating yields
  byte-identical WAVs (good for test reproducibility).

## 8. gitignore — self-contained approach (root `.gitignore` is OFF-LIMITS)

- Project convention (every prior PRP) + this agent's FORBIDDEN-OPERATIONS list: **NEVER edit the
  repo-root `.gitignore`**. Current root `.gitignore` has NO `tests/out/` entry (verified).
- The script therefore writes a **self-contained** `tests/out/.gitignore` whose content is just `*`
  (ignore everything in the dir, including the generated WAVs). A dir containing only ignored files
  never appears in `git status`, so `tests/out/` stays clean without touching the root file.
- This satisfies the PRD §4.1 intent ("`*.wav` under tests/out/" gitignored) at the directory level.

## 9. Validation gates (verified executable)

- **L1 lint:** `shellcheck tests/make_test_audio.sh` (present, v0.11.0); fallback `bash -n`.
- **L2 format:** `soxi -r/-c/-b/-e` and `ffprobe` per WAV → assert 16000 / 1 / 16 / signed-integer.
- **L3 structure/duration:** `soxi -D` → assert `utt_pause.wav` has a ≥3.0 s internal silence and
  `utt_multi.wav` total ≈ Σsentences + 2×1.5 s; idempotency (run twice → second run skips).
- **L4 silence purity:** `sox utt_pause.wav -n stat` max-amplitude check confirms the embedded gap
  is real silence (a real Whisper/ASR transcribe is OUT OF SCOPE — that is P1.M7.T2.S1's job).

## 10. External documentation (URLs)

- sox manual (effects — `trim`, synth, `rate`, `channels`, concatenation):
  https://sox.sourceforge.net/sox.html  (sections "Effect usage" → `trim`; "Combining / Concatenating").
- espeak-ng command reference (`-v`, `-s`, `-w`, `--stdout`):
  https://github.com/espeak-ng/espeak-ng/blob/master/docs/guide.md
- ffmpeg audio resampling (`-ar`, `-ac`, `-sample_fmt`):
  https://trac.ffmpeg.org/wiki/AudioChannel
- RealtimeSTT `feed_audio` / external audio input (the downstream consumer):
  https://github.com/KoljaB/RealtimeSTT (README "Feed external audio into the recorder").

# ASR Lab — offline engine bake-off for the voice-typing daemon

Experimentation harness (not shipped, not imported by the daemon). Measures the
things the daemon's live experience is made of, on recorded audio, feeding at
REAL-TIME pace:

| metric | maps to |
|---|---|
| `ttfd_med_s` | arm-to-first-word-on-screen feel |
| `fb_med_ms` / `fb_p95_ms` | per-word feedback lag while talking (the "phone feel") |
| `wobble_tot` | words retracted after being shown → revision/backspace churn |
| `final_lag_s` | engine lag after last audio, before the commit gate |
| `wer_mean` / `sim_min` | accuracy vs reference text |
| `load_s`, `vram` | first-arm cost, residency |

## Layout

- `common.py` — fixtures, metrics, voice-clip discovery
- `paced_poll.py` — re-decode poll simulation (the daemon's realtime paradigm)
- `adapters/whisper_poll.py` — faster-whisper, any CT2 model/dtype (runs under the DAEMON venv — has CUDA)
- `adapters/vosk_stream.py` — Vosk incremental streaming (CPU)
- `adapters/sherpa_stream.py` — sherpa-onnx streaming Zipformer transducer (CPU)
- `adapters/moonshine_poll.py` — moonshine ONNX poller (CPU)
- `models/` — downloaded models (gitignored)
- `results/` — one JSON per arm (gitignored)
- `voice/` — YOUR clips: `name.wav` + `name.txt` (reference text) — auto-included when present

## Run

```sh
# CUDA/whisper arms use the daemon venv (needs its LD_LIBRARY_PATH):
CUDA_LIBS="$(../../.venv/bin/python -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None)
    return os.path.dirname(f) if f else next(iter(m.__path__))
print(_d(a)+":"+_d(b))')" && export LD_LIBRARY_PATH="$CUDA_LIBS"
timeout 240 ../../.venv/bin/python adapters/whisper_poll.py large-v3-turbo float16 > results/t.json
# CPU arms use the lab venv:
timeout 240 .venv/bin/python adapters/vosk_stream.py models/vosk-model-small-en-us-0.15 > results/v.json
.venv/bin/python aggregate.py results/*.json
```

## Findings so far (2026-01 fixtures = espeak TTS, 4 clips)

| engine | ttfd | fb_med | wobble | wer | note |
|---|---|---|---|---|---|
| whisper small.en f32 (current daemon) | 0.45s | 521ms | 50 | 0.071 | |
| **whisper large-v3-turbo f16** | **0.43s** | **382ms** | 58 | **0.021** | dominates on this GPU |
| whisper large-v3-turbo f32 | 0.78s | 2667ms | 57 | 0.021 | re-decode too slow → the "big model lag" |
| vosk small (streaming) | 0.85s | 368ms | 13 | 0.227 | near-zero wobble, weak accuracy |
| vosk 0.22-lgraph (streaming) | 3.16s | 1528ms | 12 | 0.311 | slower AND worse on fixtures |
| sherpa zipformer (streaming) | 1.37s | 634ms | 7 | 0.596 | librispeech model chokes on espeak |
| moonshine base (CPU poll) | 1.68s | 5606ms | 1349 | 0.13 | CPU re-decode too slow; >5s clips return empty |

Key takeaways:

1. **compute_type matters more than model size for the poll paradigm.** turbo
   re-decoding at float32 costs 2.7s median word lag (pace-clock snowball as
   the buffer grows); float16 is the *fastest arm measured* (382ms) with 3.4x
   better WER than small.en. The daemon hardcodes float32 (a laptop-940MX
   constraint) — a `compute_type` config key is the unlock for turbo here.
2. **Streaming transducers basically never retract words** (wobble 7–13 vs
   50–58) — that property would eliminate most revision/backspace churn — but
   the tested models' accuracy is far behind. Verdict pending on real voice
   (espeak is adversarial for them).
3. Hybrid candidate: streaming transducer for live words + turbo f16 for
   authoritative finals = phone-feel partials + best accuracy.

## Caveats

- Fixtures are espeak synthesis: biased against acoustic models (esp. vosk/
  sherpa) and too easy for whisper-family. Real-voice clips in `voice/` are
  the real benchmark.
- Feedback latency approximates word audio-offset by linear spread over the
  clip (see `summarize_emissions`); ttfd for poll arms counts hallucinated
  early words (a real daemon phenomenon — cf. the blocklist).

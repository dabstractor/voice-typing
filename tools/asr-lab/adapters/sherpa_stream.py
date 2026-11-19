"""sherpa-onnx streaming Zipformer adapter — modern incremental transducer.

Feeds float32 chunks at REAL-TIME pace into an OnlineRecognizer (streaming
zipformer, token-level emission, no re-decode of old audio).
Usage: sherpa_stream.py <model_dir with tokens.txt + encoder/decoder/joiner onnx>
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import discover_wavs, emit_json, summarize_emissions, vram_mib, wav_duration
FIXTURES = discover_wavs()  # noqa: E402
import common  # noqa: E402
import sherpa_onnx  # noqa: E402

MODEL_DIR = sys.argv[1]

def _pick(pattern: str) -> str:
    """Deterministic fp32 (non-int8) model file pick."""
    files = [f for f in glob.glob(os.path.join(MODEL_DIR, pattern)) if "int8" not in f]
    return files[0]


v0 = vram_mib()
t0 = time.time()
recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    tokens=os.path.join(MODEL_DIR, "tokens.txt"),
    encoder=_pick("*encoder*onnx"),
    decoder=_pick("*decoder*onnx"),
    joiner=_pick("*joiner*onnx"),
    num_threads=4,
    enable_endpoint_detection=True,
    rule1_min_trailing_silence=0.8,  # commit segment after 800ms silence
    rule3_min_utterance_length=20.0,
)
load_s = round(time.time() - t0, 2)
vram = vram_mib() - v0


def run_wav(name: str, path: str, ref: str) -> dict:
    dur = wav_duration(path)
    stream = recognizer.create_stream()
    events = []
    committed = ""

    feed_start = time.monotonic()
    for off, samples in common.pcm_float_chunks(path):
        target = feed_start + off + common.CHUNK_S
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)
        stream.accept_waveform(16000, samples)
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        text = recognizer.get_result(stream)
        if text and text != committed:
            events.append((time.monotonic(), (committed + " " + text).strip()))
        if recognizer.is_endpoint(stream):
            if text:
                committed = (committed + " " + text).strip()
            recognizer.reset(stream)
    last_audio_at = time.monotonic()
    text = recognizer.get_result(stream)
    if text:
        committed = (committed + " " + text).strip()
    events.append((time.monotonic(), committed))
    ftext = committed

    s = summarize_emissions(events, ftext, ref, dur, feed_start, last_audio_at)
    return {"wav": name, "dur_s": round(dur, 1), **s}


cases = [run_wav(*f) for f in FIXTURES]
emit_json({"engine": f"sherpa-zipformer:{os.path.basename(MODEL_DIR.rstrip('/'))}",
           "load_s": load_s, "vram_delta_mib": vram, "cases": cases})

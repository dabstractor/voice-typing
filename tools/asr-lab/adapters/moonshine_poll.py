"""Moonshine re-decode poll (fast batch model, whisper-style polling).

moonshine (Useful Sensors, 2024): seq2seq built for edge realtime; base=61M
params, ONNX CPU. Same growing-buffer poll as the daemon's realtime engine.
Usage: moonshine_poll.py <tiny|base>
"""
from __future__ import annotations

import array
import os
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from common import discover_wavs, emit_json, summarize_emissions, vram_mib
FIXTURES = discover_wavs()  # noqa: E402
from moonshine_onnx import MoonshineOnnxModel, load_tokenizer  # noqa: E402
from paced_poll import paced_poll  # noqa: E402

SIZE = sys.argv[1] if len(sys.argv) > 1 else "base"

v0 = vram_mib()
t0 = time.time()
model = MoonshineOnnxModel(model_name=f"moonshine/{SIZE}")
tok = load_tokenizer()
load_s = round(time.time() - t0, 2)
vram = vram_mib() - v0


def load_audio_16k(path: str) -> np.ndarray:
    with wave.open(path) as w:
        rate = w.getframerate()
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    x = np.array(a, dtype=np.float32) / 32768.0
    if rate != 16000:
        n = int(len(x) * 16000 / rate)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


def run_wav(name: str, path: str, ref: str) -> dict:
    x = load_audio_16k(path)
    dur = len(x) / 16000.0

    def _gen(seg):
        tokens = model.generate(seg[None, :].astype("float32"))
        return tok.decode_batch(tokens)[0].strip()

    events = []

    def tick(t):
        text = _gen(x[: int(16000 * t)])
        if text:
            events.append(text)
        return text

    # NOTE: this ONNX build returns empty output when a single generate()
    # call sees more than ~5s of audio ([BOS, EOS]). The live-poll role only
    # ever decodes the growing buffer, so the lab "final" = last non-empty
    # partial — the screen truth a daemon would keep.
    def final():
        for t in reversed(events):
            if t and t.strip():
                return t.strip()
        return ""

    events, last_audio_at, feed_start, ftext = paced_poll(path, tick, final)
    s = summarize_emissions(events, ftext, ref, dur, feed_start, last_audio_at)
    return {"wav": name, "dur_s": round(dur, 1), **s}


cases = [run_wav(*f) for f in FIXTURES]
emit_json({"engine": f"moonshine-poll:{SIZE}", "load_s": load_s,
           "vram_delta_mib": vram, "cases": cases})

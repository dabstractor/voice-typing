"""Whisper-family re-decode poll (CONTROL arm: exactly the daemon's paradigm).

Runs under ANY interpreter that has faster_whisper (the daemon venv qualifies).
Usage: whisper_poll.py <model> <compute_type>
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from common import discover_wavs, emit_json, summarize_emissions, vram_mib
FIXTURES = discover_wavs()  # noqa: E402
from paced_poll import paced_poll  # noqa: E402

MODEL, CT = sys.argv[1], sys.argv[2]


def load_audio_16k(path: str):
    import array
    import wave
    import numpy as np
    with wave.open(path) as w:
        rate = w.getframerate()
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    x = np.array(a, dtype=np.float32) / 32768.0
    if rate != 16000:
        n = int(len(x) * 16000 / rate)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


v0 = vram_mib()
t0 = time.time()
from faster_whisper import WhisperModel  # noqa: E402
m = WhisperModel(MODEL, device="cuda", compute_type=CT)
load_s = round(time.time() - t0, 2)
vram = vram_mib() - v0

audio_cache: dict[str, object] = {}


def run_wav(name: str, path: str, ref: str) -> dict:
    x = audio_cache.get(path) or load_audio_16k(path)
    audio_cache[path] = x
    dur = len(x) / 16000.0

    def tick(t):
        segs, _ = m.transcribe(x[: int(16000 * t)], language="en",
                               beam_size=1, vad_filter=False, condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()

    def final():
        segs, _ = m.transcribe(x, language="en", beam_size=1, vad_filter=False,
                               condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()

    events, last_audio_at, feed_start, ftext = paced_poll(path, tick, final)
    s = summarize_emissions(events, ftext, ref, dur, feed_start, last_audio_at)
    return {"wav": name, "dur_s": round(dur, 1), **s}


cases = [run_wav(*f) for f in FIXTURES]
emit_json({"engine": f"whisper-poll:{MODEL}:{CT}", "load_s": load_s,
           "vram_delta_mib": vram, "cases": cases})

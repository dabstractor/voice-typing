"""Vosk streaming adapter — true incremental emitter (Kaldi/zipformer under the hood).

Feeds 16-bit PCM chunks at REAL-TIME pace; Vosk emits partial results as words
solidify and NEVER re-decodes old audio. Usage: vosk_stream.py <model_dir>
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from common import discover_wavs, emit_json, summarize_emissions, vram_mib, wav_duration
FIXTURES = discover_wavs()  # noqa: E402
from vosk import KaldiRecognizer, Model  # noqa: E402

MODEL_DIR = sys.argv[1]

v0 = vram_mib()
t0 = time.time()
model = Model(MODEL_DIR)
load_s = round(time.time() - t0, 2)
vram = vram_mib() - v0


def run_wav(name: str, path: str, ref: str) -> dict:
    import wave
    dur = wav_duration(path)
    with wave.open(path) as w:
        rate = w.getframerate()

    rec = KaldiRecognizer(model, rate)
    rec.SetWords(True)
    events = []
    final = ""
    feed_start = time.monotonic()
    import common

    for off, chunk in common.wav_chunks(path):
        target = feed_start + off + common.CHUNK_S
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)
        if rec.AcceptWaveform(chunk):
            obj = json.loads(rec.Result())
            if obj.get("text"):
                final += " " + obj["text"]
            # segment boundary: partial resets; emit the segment text as event
            if obj.get("text"):
                events.append((time.monotonic(), (final + " ...").strip()))
        else:
            obj = json.loads(rec.PartialResult())
            p = obj.get("partial", "")
            if p:
                events.append((time.monotonic(), (final + " " + p).strip()))
    last_audio_at = time.monotonic()
    obj = json.loads(rec.FinalResult())
    if obj.get("text"):
        final += " " + obj["text"]
    events.append((time.monotonic(), final.strip()))
    ftext = final.strip()

    s = summarize_emissions(events, ftext, ref, dur, feed_start, last_audio_at)
    return {"wav": name, "dur_s": round(dur, 1), **s}


cases = [run_wav(*f) for f in FIXTURES]
emit_json({"engine": f"vosk:{MODEL_DIR.rsplit('/', 1)[-1]}", "load_s": load_s,
           "vram_delta_mib": vram, "cases": cases})

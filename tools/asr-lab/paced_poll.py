"""Paced poll runner shared by re-decode engines (whisper-sim, moonshine).

Simulates the daemon's realtime engine: audio accumulates at REAL-TIME pace and
the engine re-decodes the whole buffer every `tick` seconds (the daemon uses
realtime_processing_pause=0.15). Each tick's decode runs DURING the pace clock,
so decode time directly delays subsequent words exactly as it does live.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import wav_duration  # noqa: E402


def paced_poll(wav_path: str, tick_fn, final_fn=None, tick: float = 0.15):
    """tick_fn(t_seconds) -> partial_text | None. final_fn() -> final_text.

    Returns (events, last_audio_at, feed_start, final_text) where events is
    [(wall_time, partial_text)] for every non-empty partial. When final_fn is
    None (poller role), the last tick's partial stands as the final and no
    extra decode pass runs.
    """
    dur = wav_duration(wav_path)
    feed_start = time.monotonic()
    events = []
    t = 0.0
    while t < dur:
        t += tick
        target = feed_start + min(t, dur)
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)
        text = tick_fn(min(t, dur))
        if text:
            events.append((time.monotonic(), text))
    last_audio_at = time.monotonic()
    if final_fn is not None:
        final = final_fn()
        events.append((time.monotonic(), final))
    else:
        final = events[-1][1] if events else ""
    return events, last_audio_at, feed_start, final

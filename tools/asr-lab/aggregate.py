"""Aggregate asr-lab JSON results into one comparison table. Usage: aggregate.py <json...>"""
from __future__ import annotations

import json
import statistics
import sys

rows = []
for f in sys.argv[1:]:
    try:
        d = json.load(open(f))
    except Exception:
        continue  # skip empty/failed runs
    cases = d["cases"]
    def med(key):
        vals = [c[key] for c in cases if c.get(key) is not None]
        return statistics.median(vals) if vals else float("nan")
    def tot(key):
        return sum(c.get(key) or 0 for c in cases)
    rows.append({
        "engine": d["engine"],
        "load_s": d["load_s"],
        "vram": d.get("vram_delta_mib", 0),
        "ttfd_med_s": round(med("ttfd_s"), 2),
        "fb_med_ms": round(med("feedback_ms_med")),
        "fb_p95_ms": round(med("feedback_ms_p95")),
        "wobble_tot": tot("wobble_n"),
        "final_lag_med_s": round(med("final_lag_s"), 2),
        "wer_mean": round(statistics.mean(c["wer"] for c in cases), 3),
        "sim_min": min(c["sim"] for c in cases),
    })

hdr = ["engine", "load_s", "vram", "ttfd_med_s", "fb_med_ms", "fb_p95_ms",
       "wobble_tot", "final_lag_med_s", "wer_mean", "sim_min"]
w = [max(max((len(str(x[h])) for x in rows), default=0), len(h)) for h in hdr]
print("  ".join(h.ljust(x) for h, x in zip(hdr, w)))
print("  ".join("-" * x for x in w))
for r in rows:
    print("  ".join(str(r[h]).ljust(x) for h, x in zip(hdr, w)))

#!/usr/bin/env python3
"""g5_make_alignments — offline word-alignment fixture generator (P1.M6.T4.S1).

Runs faster-whisper with word_timestamps=True over the tracked real-voice clips
(tools/asr-lab/voice/*.wav) under the DAEMON venv, and writes one committed
fixture per clip: tools/asr-lab/voice/<name>.words.json —
[{"word": ..., "start": <seconds>, "end": <seconds>}, ...] (2-space JSON,
stable layout). These fixtures are the G5 SPEECH CLOCK (Gotcha #1): word i's
speech-end during a replay is feed_start + words[i].end. They replace asr-lab
summarize_emissions' LINEAR-SPREAD approximation — G5 must never approximate.

ENV-GATED (G5_ALIGN=1), NOT collected by pytest. CUDA recipe (the asr-lab
README run block — the daemon venv has faster-whisper; cuBLAS/cuDNN live in
its nvidia wheels):

    CUDA_LIBS="$(.venv/bin/python -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
    def _d(m):
        f=getattr(m,"__file__",None)
        return os.path.dirname(f) if f else next(iter(m.__path__))
    print(_d(a)+":"+_d(b))')" && export LD_LIBRARY_PATH="$CUDA_LIBS"
    timeout -k 2 900 env G5_ALIGN=1 .venv/bin/python tests/g5_make_alignments.py

Model/decode mirror the configured FINAL path (voice_typing/config.py
AsrConfig defaults: lite_model small.en, float16, cuda, language en) — the
alignment must come from the same engine family the daemon ships. After each
clip the word count is reconciled against the .txt reference (asr-lab
common.norm_words); MISMATCHES ARE PRINTED, NEVER FUDGED (CRITICAL #9).
Bounded output: prints + the small JSONs only.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VOICE_DIR = REPO / "tools" / "asr-lab" / "voice"
GATE_ENV = "G5_ALIGN"


def norm_words(s: str) -> list[str]:
    """The shared matching space (tools/asr-lab/common.py norm_words)."""
    import re
    import unicodedata

    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^a-z0-9' ]", " ", s).split()


def main() -> int:
    if os.environ.get(GATE_ENV) != "1":
        print(
            json.dumps(
                {"gate": GATE_ENV, "pass": None, "note": f"skipped (set {GATE_ENV}=1)"}
            )
        )
        return 0
    from faster_whisper import (
        WhisperModel,
    )  # daemon venv only (CUDA/LD recipe in the header)

    from voice_typing.config import AsrConfig

    asr = AsrConfig()
    model = WhisperModel(
        asr.lite_model, device=asr.device, compute_type=asr.compute_type
    )
    print(
        json.dumps(
            {
                "model": asr.lite_model,
                "device": asr.device,
                "compute_type": asr.compute_type,
                "language": asr.language,
            }
        )
    )
    rc = 0
    for wav in sorted(VOICE_DIR.glob("*.wav")):
        stem = wav.stem
        ref_path = wav.with_suffix(".txt")
        t0 = time.monotonic()
        segments, _info = model.transcribe(
            str(wav), word_timestamps=True, language=asr.language
        )
        words: list[dict] = []
        for seg in segments:
            for w in seg.words:
                words.append(
                    {
                        "word": str(w.word).strip(),
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                    }
                )
        out = wav.with_suffix(".words.json")
        out.write_text(
            json.dumps(words, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        # reconciliation against the .txt reference — recorded, never fudged
        ref = (
            norm_words(ref_path.read_text(encoding="utf-8"))
            if ref_path.exists()
            else []
        )
        hyp = norm_words(" ".join(w["word"] for w in words))
        match = sum(1 for a, b in zip(ref, hyp) if a == b)
        row = {
            "clip": stem,
            "words": len(words),
            "ref_words": len(ref),
            "prefix_match": match,
            "duration_s": round(words[-1]["end"], 2) if words else 0.0,
            "gen_s": round(time.monotonic() - t0, 1),
            "fixture": str(out.relative_to(REPO)),
            "reconciled": len(ref) == len(hyp) and match == len(ref),
        }
        print(json.dumps(row, ensure_ascii=False))
        if not row["reconciled"]:
            rc = 1  # honest: a mismatch leaves rc=1 but the fixture is still written
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

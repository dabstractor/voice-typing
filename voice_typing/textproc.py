"""voice_typing.textproc — post-recognition text normalizer (PRD §4.7).

clean() is the quality + hallucination filter applied to every finalized
utterance before it is typed. PURE PYTHON (stdlib only), GPU-free, and fast,
so it is trivially unit-testable (PRD test T2).

PIPELINE (PRD §4.7), in order:
  1. strip() + drop trailing newlines + collapse internal whitespace runs to
     single spaces.
  2. reject (-> None) if len(cleaned) < cfg.min_chars.
  3. reject (-> None) if the lowercase, trailing-punctuation-stripped form of
     the cleaned text is in the blocklist (the blocklist is normalized the
     same way, so "Bye", "bye.", and "BYE!" all match the "bye." entry).
  4. return cleaned text. The CALLER (daemon on_final) appends a trailing
     space when output.append_space — clean() never adds one.

THE BLOCKLIST is the primary defense against Whisper's silence hallucination
("thank you." on silent audio — a top-3 project risk, PRD §8). VAD gating +
this filter + PRD test T4 assert it together. Trailing-punctuation stripping
makes the match robust to whether Whisper appended a period: "Bye", "Bye.",
and "BYE!" all normalize to "bye" and all match the "bye." blocklist entry.

CONSUMES: voice_typing.config.FilterConfig (P1.M2.T1.S1).
CONSUMED BY: daemon.on_final (P1.M4.T1.S2) as:
    txt = textproc.clean(text, cfg.filter)
    if txt is not None: <type txt + " " when cfg.output.append_space>

NO SIDE EFFECTS, NO I/O. Deterministic and pure.
"""
from __future__ import annotations

from voice_typing.config import FilterConfig

# Trailing punctuation stripped when building the blocklist comparison key
# (PRD §4.7 step 3). Pinned verbatim; do not add/remove characters.
_TRAILING_PUNCT = ".!?," + ";"  # written split to avoid an editor auto-trim of trailing punctuation


def clean(text: str, cfg: FilterConfig) -> str | None:
    """Normalize + filter a finalized utterance (PRD §4.7).

    Args:
        text: raw finalized text from the ASR engine (may carry stray
            leading/trailing whitespace, embedded newlines, double spaces).
        cfg: the [filter] config (min_chars, blocklist) from VoiceTypingConfig.

    Returns:
        The cleaned text, or None if it should be dropped (too short, or a
        known hallucination). Never appends a space (the caller's job).
    """
    # Step 1: strip + drop trailing newlines + collapse internal whitespace
    # runs to single spaces. str.split() (no args) splits on ANY whitespace run
    # and discards leading/trailing empties, so join() yields a fully-stripped,
    # single-space-joined string in one expression.
    cleaned = " ".join(text.split())

    # Step 2: min-length gate (on the CLEANED length).
    if len(cleaned) < cfg.min_chars:
        return None

    # Step 3: hallucination blocklist. Normalize BOTH the input and every
    # blocklist entry the same way: lowercase + strip trailing punctuation.
    # Exact match on the normalized form (NOT substring): "you" blocks, but
    # "yourself" does not.
    key = cleaned.lower().rstrip(_TRAILING_PUNCT)
    if key in {b.lower().rstrip(_TRAILING_PUNCT) for b in cfg.blocklist}:
        return None

    # Step 4: return cleaned text (caller appends a space when append_space).
    return cleaned

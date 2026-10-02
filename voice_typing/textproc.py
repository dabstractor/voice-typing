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
  and (P1.M2.T6.S1) voice_typing.streaming.StreamingOutput.on_partial, which applies
  apply_streaming_guards() to every delta/revised-tail before typing it.

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


# Terminal punctuation that ends a sentence for the CASING guard (PRD §4.2quater
# rule 1). Pinned verbatim: a '.' '!' or '?' as the last non-whitespace char of
# the preceding text means the next fragment starts a NEW sentence and keeps its
# capitalization. ',' ';' ':' and everything else mean mid-sentence -> lowercase.
_SENTENCE_TERMINALS = ".!?"


def apply_streaming_guards(committed: str, fragment: str) -> str:
    """Deterministic casing + period guards for a streaming fragment (PRD §4.2quater R1).

    Applied by StreamingOutput (P1.M2.T6.S1) to EVERY piece of text it is about to
    type (an extend delta, or a full revised tail). Two rules, in order:

      (a) CASING — if `committed` (rstripped) is non-empty and does NOT end with a
          terminal '.' '!' or '?', the fragment joins MID-SENTENCE: lowercase the
          first cased (alphabetic, case-distinct) character of the fragment, so a
          Whisper partial like "The" lands as "the" after "then he said". An EMPTY
          `committed` (session/utterance start) preserves the fragment's case —
          the first dictated words should stay capitalized.
      (b) PERIOD — only when rule (a) FIRED (mid-sentence) and the fragment
          (rstripped) ends with '.', strip exactly ONE trailing '.'. Whisper
          partials waffle between "word." and "word and" mid-utterance; eating
          that single spurious period converts a whole class of flickering
          rewind-and-retype cycles into clean extensions ("word." -> "word" is
          typed once, then "word and" extends). After a sentence terminal the
          period is legitimate and is kept.

    Rule (b) fires whenever rule (a)'s mid-sentence branch is taken, even if the
    fragment has no cased character to lowercase (e.g. a lone "." delta becomes
    "" and nothing is typed). Rule (a) without a cased character is a no-op.

    Args:
        committed: the finalized text preceding this fragment (the casing
            context). Trailing whitespace is ignored; empty/whitespace-only
            means "session start" -> case preserved.
        fragment: the text about to be typed. Assumed pre-normalized
            (whitespace-collapsed) by the caller; never made to end with a space.

    Returns:
        The guarded fragment (possibly unchanged, possibly shorter by one '.').
        PURE: no I/O, no state, deterministic.
    """
    context = committed.rstrip()
    # Rule (a): empty context == session start -> keep the fragment verbatim
    # (and rule (b) never fires without it).
    if not context or context[-1] in _SENTENCE_TERMINALS:
        return fragment
    # Mid-sentence: lowercase the FIRST cased character (skips quotes/parens/
    # digits — '"Quoted' -> '"quoted'). Already-lowercase chars are rewritten to
    # themselves, so an already-lowercase fragment is unchanged.
    for i, ch in enumerate(fragment):
        if ch.isalpha() and ch.lower() != ch.upper():
            fragment = fragment[:i] + ch.lower() + fragment[i + 1 :]
            break
    # Rule (b): strip exactly ONE mid-sentence trailing '.' ("Stop..." -> "stop..").
    stripped = fragment.rstrip()
    if stripped.endswith("."):
        cut = len(stripped) - 1  # index of that final '.'; keep anything after it
        fragment = fragment[:cut] + fragment[cut + 1 :]
    return fragment

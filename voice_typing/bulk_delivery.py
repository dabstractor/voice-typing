"""voice_typing.bulk_delivery — the R.3 contract surface for bulk text delivery (PRD §4.2sexies).

A PURE, stdlib-only contracts module: the names, the result taxonomy, and the two
pure rules (rendered-equality zero-diff guard, char-span → target-units mapping)
that the bulk-delivery controller and every TargetAdapter program against. ZERO
implementation and ZERO engine coupling: this module imports nothing from the
streaming engine, the typing backends, or the daemon, exposes no typing fallback
surface, and is importable in every context — the adapters import THIS module,
never the reverse.

THE DELIVERY MODEL (R.3), one line per Protocol call:
  acquire()  bind the SPECIFIC editable field — not merely a window, terminal
             process, or screen position. Return an opaque target handle +
             revision. Fail BEFORE delivery for non-editable, password/secret,
             selected, or unidentified fields; never replace a pre-existing user
             selection by default. A pane, tab, or inner editor can change
             without the window changing.
  show(...)  ONE insert-or-replace executed ON the target's event loop, only if
             focus, caret, selection, and ownership still match; the complete
             rendered span replaces the adapter's OWN verified range.
  finalize() a final matching the visible text ⇒ NO further edit (ownership
             ends; composition-protocol commit side effects must not visibly
             change or duplicate the text). A differing final ⇒ ONE replacement
             of verified owned text. A final with no preceding partial inserts
             once and counts as a missed live update in latency evidence.
  leave()    stop preserves the last visible words where they are — NO
             post-stop writes anywhere, including a newly focused field.
  cancel()   deliberate cancel removes the owned fragment in ONE operation,
             drops its buffered audio, and keeps listening.

THE RESULT TAXONOMY (ShowResult): applied | unchanged | refused | unknown.
Bytes sent is not "applied"; "unknown" is not "delivered". Only applied and
unchanged keep delivery active; refused and unknown DISARM delivery — and an
operation whose outcome is unknown is NEVER retried (R.5: never retry an
operation that may already have landed).

THE EVENT-COUNT LAW (R.1): judge every delivery primitive by
operations-per-change — insertion = 1, correction = 1, zero-diff = 0.
Synthesized per-character typing and Backspace chains are FORBIDDEN in this
mode; there is no fallback to the legacy typing backends. The zero-diff guard
is rendered_equal(): compare RENDERED text after the spacing guard ONLY — two
strings that render identically ⇒ zero events; real case/punctuation/word
differences are never declared equal.

EVIDENCE DISCIPLINE (R.2): a passing transport probe (byte reader, scrollback,
state-file write) is mechanism evidence only — it never substitutes for the
real-field acceptance gates. "A passing transport probe NEVER flips any of
these to 'passed'."

UNITS AND OWNERSHIP (R.3): the adapter maps text positions to the target's own
units (UTF-8 bytes, characters, UTF-16 units, or editor markers); map_span()
implements the three mechanical units exactly, counting on the ORIGINAL string
only — never slice via a lowercased/normalized copy. EDITOR_MARKERS is
adapter-owned and deliberately unimplemented here. Adjacent user text,
whitespace, and formatting are never touched.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

__all__ = [
    "ShowResult",
    "AcquireResult",
    "DeliveryTarget",
    "TargetUnits",
    "map_span",
    "rendered_equal",
]


# ---------------------------------------------------------------------------
# The result taxonomy (R.3; serialized verbatim into status/log lines, R.5)
# ---------------------------------------------------------------------------

class ShowResult(str, Enum):
    """Outcome of one show/finalize/cancel operation — EXACTLY these four.

    str-valued so the words serialize straight into status/log lines (R.5's
    delivery_state/delivery_reason surface). Branch on these: only APPLIED and
    UNCHANGED keep delivery active; REFUSED/UNKNOWN disarm, never retry (R.5).
    """

    APPLIED = "applied"      # the target executed AND confirmed the edit
    UNCHANGED = "unchanged"  # render-equal to what is already shown — ZERO events emitted
    REFUSED = "refused"      # the target actively declined (focus/ownership mismatch, …)
    UNKNOWN = "unknown"      # outcome unverifiable (timeout, lost ack) — NOT delivered; never retry


@dataclass(frozen=True)
class AcquireResult:
    """One matchable shape for both the bound target and every fail-before-delivery case.

    ok            — the field was bound (a usable handle/revision came back).
    handle        — opaque target handle (adapter-defined; meaningless here).
    revision      — the target's current content revision (for expected_revision
                    re-checks on show/finalize); 0 unless ok.
    reason        — the fail-before-delivery cause when ok is False
                    (non-editable / password-secret / selected / unidentified, …).
    """

    ok: bool
    handle: object = None
    revision: int = 0
    reason: str = ""


# ---------------------------------------------------------------------------
# The TargetAdapter seam (R.3) — implement this; never a typing fallback
# ---------------------------------------------------------------------------

@runtime_checkable
class DeliveryTarget(Protocol):
    """The adapter contract a concrete target implements (R.3 delivery model).

    One writer per target; one operation in flight. Every mutating call carries
    the arm-generation `session`, the utterance identity `utterance`, the
    monotonic per-utterance `seq`, and the `expected_revision` the caller
    believes the target is at; the adapter re-checks them AT MUTATION TIME so a
    late/queued operation can never mutate after takeover (R.5).
    """

    def acquire(self) -> AcquireResult:
        """Bind the SPECIFIC editable field — not merely a window, terminal
        process, or screen position. Return an opaque target handle + revision.
        Fail BEFORE delivery for non-editable, password/secret, selected, or
        unidentified fields; never replace a pre-existing user selection by
        default."""
        ...

    def show(
        self, session: int, utterance: str, seq: int, expected_revision: int, span: str
    ) -> ShowResult:
        """ONE insert-or-replace executed ON the target's event loop, only if
        focus, caret, selection, and ownership still match. `span` is the
        COMPLETE rendered span. Returns applied | unchanged | refused | unknown.
        Bytes sent is not "applied"; "unknown" is not "delivered"."""
        ...

    def finalize(
        self, session: int, utterance: str, seq: int, expected_revision: int, span: str
    ) -> ShowResult:
        """A final matching the visible text ⇒ NO further edit (ownership ends;
        composition-protocol commit side effects must not visibly change or
        duplicate the text). A differing final ⇒ ONE replacement of verified
        owned text. Same result taxonomy as show()."""
        ...

    def leave(self) -> None:
        """Stop preserving the last visible words where they are — no post-stop
        writes anywhere, including a newly focused field."""
        ...

    def cancel(self) -> ShowResult:
        """Deliberate cancel: remove the owned fragment in ONE operation, drop
        its buffered audio, and keep listening. Returns the operation's result
        (applied / refused / unknown; nothing pending ⇒ unchanged)."""
        ...


# ---------------------------------------------------------------------------
# Units mapping (R.3): mechanical for the three countable units, original string only
# ---------------------------------------------------------------------------

class TargetUnits(str, Enum):
    """The coordinate systems a target's edit API may speak (R.3 units rule)."""

    UTF8_BYTES = "utf8_bytes"          # byte offsets into the UTF-8 encoding
    CHARACTERS = "characters"          # Python str code-point indices
    UTF16_UNITS = "utf16_units"        # UTF-16 code units (surrogate-pair aware)
    EDITOR_MARKERS = "editor_markers"  # the target's own markers — adapter-owned


def _utf16_len(ch: str) -> int:
    """UTF-16 code units for one character: an astral-plane char is a pair.

    Python 3 strings are code-point sequences, so len(ch) is always 1 — the
    test for "needs a surrogate pair in UTF-16" is the code point itself:
    anything above the BMP (> 0xFFFF) encodes as 2 UTF-16 code units.
    """
    return 2 if ord(ch) > 0xFFFF else 1


def map_span(text: str, start_char: int, end_char: int, units: TargetUnits) -> tuple[int, int]:
    """Convert a Python-str character span into the target's own units.

    Counts on the ORIGINAL string only — never a lowercased/normalized copy
    (R.3: "never slice via a lowercased/normalized copy"; a normalized count is
    exactly the index-desync class the units rule forbids). UTF-8 offsets are
    cumulative byte lengths; UTF-16 counts are surrogate-pair aware (an astral
    char counts as 2 units). CHARACTERS is the identity (after range
    validation). EDITOR_MARKERS raises NotImplementedError — the adapter owns
    its own marker algebra and this module does not guess it.

    Raises ValueError for a malformed span (start > end, negative, or past the
    end of `text`).
    """
    if not (0 <= start_char <= end_char <= len(text)):
        raise ValueError(
            f"invalid char span ({start_char}, {end_char}) for text of {len(text)} chars"
        )
    if units is TargetUnits.CHARACTERS:
        return (start_char, end_char)
    if units is TargetUnits.UTF8_BYTES:
        start = len(text[:start_char].encode("utf-8"))
        end = len(text[:end_char].encode("utf-8"))
        return (start, end)
    if units is TargetUnits.UTF16_UNITS:
        start = sum(_utf16_len(ch) for ch in text[:start_char])
        end = sum(_utf16_len(ch) for ch in text[:end_char])
        return (start, end)
    raise NotImplementedError("EDITOR_MARKERS mapping is adapter-owned (R.3)")


# ---------------------------------------------------------------------------
# The generalized zero-diff guard (R.1) — spacing normalization ONLY
# ---------------------------------------------------------------------------

def rendered_equal(old: str, new: str) -> bool:
    """True iff two renderings are the same text after the spacing guard.

    The R.1 generalization of the streaming engine's exact-equal no-op: compare
    RENDERED text — collapse every whitespace run (spaces, tabs, line breaks,
    and any Unicode whitespace such as NBSP) to a single space and strip the
    ends via str.split(), then EXACT ==. Prose line breaks normalize to a space
    (R.3); two strings that render identically ⇒ zero events.

    NEVER folds case, NEVER strips punctuation: "Hello"/"hello" and "Hi."/"Hi"
    are REAL differences (R.1) — declaring them equal is the exact index-desync
    class this guard exists to prevent. An empty string and a whitespace-only
    string render identically (both normalize to "").
    """
    return " ".join(old.split()) == " ".join(new.split())

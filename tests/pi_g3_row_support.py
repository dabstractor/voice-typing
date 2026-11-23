"""pi_g3_row_support — pure helpers for the G3 row "pi chat prompt in isolated
Ghostty" (P1.M5.T2.S1), driven through S2's PiEditorTarget adapter.

NO desktop / socket / subprocess imports: this module is imported BOTH by the
collected unit tests (tests/test_pi_g3_row_support.py) and by the env-gated
lab (tests/pi_g3_row_lab.py). The only voice_typing import is bulk_delivery's
contract vocabulary (pure) — UTF-16 math is routed through map_span, never
hand-rolled (CRITICAL #6).

Contents:
  - KINDS / EXPECT vocabularies   the closed step/branch sets for the row
  - G3Step                        one scripted step of the G3 trace list
  - EditorMirror                  pure expected-state tracker for the pi
                                  editor (text + caret + owned + dirty),
                                  mirroring the LANDED extension's rules in
                                  .pi/extensions/voice-editor.ts
  - row_traces()                  the §4 G3 trace list, scoped to one window
  - row_status()                  THE honest status rule (PRD §4.2sexies R.7
                                  vocabulary + this item's "not verified
                                  (visibility instrumentation absent)" case)
  - VerdictRow                    one report/JSONL verdict row
  - assert_no_paste_markers()     the folded-paste + control-byte detector
  - render_row_report()           the bounded (<= MAX_REPORT_LINES) renderer

Payload vocabulary is REUSED from tests/pi_seam_support.py (S1's frozen
probes) — no forked dialect. A G2/lab pass never marks the row verified:
row_status() can only return "verified" when the caller attests visible-prompt
instrumentation, which the landed extension does not have (its read reply
carries text/cursor/owned/dirty/units/changes — no rendered-prompt dump).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from voice_typing.bulk_delivery import TargetUnits, map_span

try:
    from pi_seam_support import ASCII_PROBE, UNICODE_PROBE  # sibling import
except ImportError:  # package-style import (tests.*): namespace-relative
    from .pi_seam_support import ASCII_PROBE, UNICODE_PROBE  # type: ignore[no-redef]

__all__ = [
    "KINDS",
    "EXPECTS",
    "STATUSES",
    "MAX_REPORT_LINES",
    "G3Step",
    "EditorMirror",
    "VerdictRow",
    "LONG_PAYLOAD",
    "LONG_CORRECTED",
    "ROW_COMMAND",
    "row_traces",
    "row_status",
    "assert_no_paste_markers",
    "render_row_report",
    "utf16_len",
    "u16_span",
]


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: step kinds (the §4 trace list). "focus" carries a live owned fragment into
#: a second window BEFORE the takeover leg: the landed extension has no
#: focus-loss signal, so the measured branch is "ownership persists" — after
#: takeover every op is refused and the focus question would be unanswerable.
KINDS = (
    "insert",
    "correction",
    "zero_diff",
    "finalize",
    "unicode",
    "unicode_zero_diff",
    "long",
    "long_correction",
    "refusal_range",
    "refusal_oob",
    "cancel_empty",
    "cancel_pending",
    "focus",
    "takeover",
    "refusal_dirty",
    "refusal_acquire_dirty",
    "cancel_dirty",
)

#: expected branch per step: ShowResult values (applied|unchanged|refused) or
#: "halt" (the takeover watch must fire exactly once).
EXPECTS = ("applied", "unchanged", "refused", "halt")

#: the row-status vocabulary (R.7 + this item's explicit middle case).
STATUSES = (
    "untested",
    "insert-only",
    "blocked",
    "not verified",
    "verified",
)

MAX_REPORT_LINES = 120

ROW_COMMAND = (
    "timeout -k 2 240 env PI_G3_ROW_LAB=1 .venv/bin/python tests/pi_g3_row_lab.py"
)

#: ~1 KB ASCII payload (exactly 1024 chars, single line, printable only).
_BASE = "alpha bravo charlie delta echo foxtrot golf hotel "
LONG_PAYLOAD: str = (_BASE * ((1024 // len(_BASE)) + 1))[:1024]
#: its first-word correction (same length — one atomic in-place rewrite).
LONG_CORRECTED: str = "ALPHA" + LONG_PAYLOAD[5:]


# ---------------------------------------------------------------------------
# Units plumbing — ONLY via bulk_delivery.map_span (CRITICAL #6)
# ---------------------------------------------------------------------------


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units on the ORIGINAL string (🫡 = 2)."""
    if text == "":
        return 0
    return map_span(text, 0, len(text), TargetUnits.UTF16_UNITS)[1]


def u16_span(text: str, start_char: int, end_char: int) -> tuple[int, int]:
    """char span -> UTF-16 unit span on the ORIGINAL string."""
    return map_span(text, start_char, end_char, TargetUnits.UTF16_UNITS)


# ---------------------------------------------------------------------------
# Step model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class G3Step:
    """One scripted G3 step: what the lab drives and what must come back.

    payload is the RENDERED span passed to target.show() for show-shaped
    kinds ("" for cancel/takeover/refusal-acquire steps whose payload is
    structural). expect is the ShowResult value — or "halt" for the takeover
    step. expect_changes is the per-op onChange delta the reply must carry
    (1 for every applied mutation, 0 for zero-diff/zero-request steps — the
    R.1 edit-count law: applied=1, unchanged=0, never a delete/retype pair).
    """

    name: str
    kind: str
    payload: str
    expect: str
    expect_changes: int


def row_traces() -> list[G3Step]:
    """The §4 G3 trace list for the pi prompt in isolated Ghostty.

    Order (documented in the row report): inserts -> first-word correction
    -> zero-diff repeat -> finalize boundary -> empty-cancel -> pending
    cancel -> owned-null refusal -> Unicode -> zero-diff -> out-of-bounds
    refusal -> finalize -> 1 KB payload -> its in-place word correction ->
    focus switch (ownership persists — measured BEFORE takeover: only a
    delegated keystroke revokes v1) -> takeover -> dirty refusals
    (show/acquire/cancel). Utterance spans follow S2's adapter contract:
    after a finalize, the NEXT utterance's first show inserts its FULL span
    at the caret (contiguous owned extension) — spans below are per
    utterance, never cumulative. The visible-prompt leg is decided by
    row_status(), never here.
    """
    u1 = ASCII_PROBE  # "hello from pi seam" — utterance 1's partial/final
    u1_grown = u1 + " for G3"
    u1_fixed = "Hello" + u1_grown[5:]  # first-word correction, same length
    u2 = "again"  # utterance 2 — inserted at the caret after u1's finalize
    u4 = LONG_PAYLOAD  # utterance 4: the ~1 KB tail (u3's text stays owned)
    # the correction span is the FULL owned fragment (u3's Unicode prefix is
    # still owned, so the in-place rewrite must carry it — S2 replaces
    # [owned_start, owned_start+owned_len) with the rendered span verbatim):
    u4_fixed = UNICODE_PROBE + LONG_CORRECTED
    u5_tail = u4_fixed + " tail"  # utterance 5 (open at takeover time)
    return [
        G3Step("short-insert-1", "insert", u1, "applied", 1),
        G3Step("short-insert-2", "insert", u1_grown, "applied", 1),
        G3Step("first-word-correction", "correction", u1_fixed, "applied", 1),
        G3Step("zero-diff-repeat", "zero_diff", u1_fixed, "unchanged", 0),
        # finalize(u1): matching final -> unchanged, ZERO requests.
        G3Step("finalize-u1", "finalize", u1_fixed, "unchanged", 0),
        # cancel with NOTHING pending (post-finalize) -> unchanged, ZERO reqs.
        G3Step("cancel-nothing-pending", "cancel_empty", "", "unchanged", 0),
        G3Step("u2-pending-insert", "insert", u2, "applied", 1),
        # cancel-pending removes the OWNED range in ONE op (the whole u1+u2
        # fragment — ownership bound at buffer offset 0), leaving text empty.
        G3Step("cancel-pending", "cancel_pending", "", "applied", 1),
        # owned is now null AND the buffer is empty: a raw replace over the
        # in-bounds empty range [0,0) hits the ownership check FIRST ->
        # refused "range not owned" (any wider range would be out_of_bounds).
        G3Step("refuse-range-not-owned", "refusal_range", "", "refused", 0),
        G3Step("unicode-insert", "unicode", UNICODE_PROBE, "applied", 1),
        G3Step("unicode-zero-diff", "unicode_zero_diff", UNICODE_PROBE, "unchanged", 0),
        # owned is (0,18): a raw replace past the buffer -> "out_of_bounds".
        G3Step("refuse-out-of-bounds", "refusal_oob", "", "refused", 0),
        G3Step("finalize-u3", "finalize", UNICODE_PROBE, "unchanged", 0),
        G3Step("long-insert-1kb", "long", u4, "applied", 1),
        G3Step("long-word-correction", "long_correction", u4_fixed, "applied", 1),
        G3Step("focus-switch", "focus", u5_tail, "applied", 1),
        # a real xdotool space into the focused private window; the watch
        # must fire halt_for_takeover EXACTLY once.
        G3Step("takeover-real-key", "takeover", "", "halt", 0),
        # divergent span -> replace path -> bind read sees dirty -> refused.
        G3Step(
            "refuse-show-while-dirty", "refusal_dirty", "X" + u5_tail[1:], "refused", 0
        ),
        G3Step("refuse-acquire-while-dirty", "refusal_acquire_dirty", "", "refused", 0),
        G3Step("refuse-cancel-while-dirty", "cancel_dirty", "", "refused", 0),
    ]


# ---------------------------------------------------------------------------
# Expected-state mirror (the pure oracle for the editor's own read replies)
# ---------------------------------------------------------------------------


@dataclass
class EditorMirror:
    """Expected editor state per the LANDED extension's op semantics.

    Mirrors .pi/extensions/voice-editor.ts (read-only ground truth):
    insert extends contiguous ownership at the caret (which sits at
    end-of-buffer throughout this trace), replace rewrites the owned range
    in ONE op (caret lands end-of-buffer), cancel removes the owned range in
    ONE op, and the FIRST delegated real keystroke while owned flips dirty
    and emits exactly one takeover event (never triggered by socket writes).
    All offsets are UTF-16 code units computed via map_span.
    """

    text: str = ""
    owned: tuple[int, int] | None = None  # [start, end) UTF-16, None = null
    dirty: bool = False

    # -- the ops (guarded: they refuse exactly like the extension) ----------
    def op_insert(self, text: str) -> None:
        """insertTextAtCursor at the caret (end-of-buffer in this trace)."""
        caret_before = utf16_len(self.text)
        caret_after = caret_before + utf16_len(text)
        self.text += text
        if self.owned and not self.dirty and caret_before == self.owned[1]:
            self.owned = (self.owned[0], caret_after)  # contiguous extend
        elif self.owned and not self.dirty and caret_before == self.owned[0]:
            self.owned = (caret_before, self.owned[1] - self.owned[0] + caret_after)
        else:
            self.owned = (caret_before, caret_after)  # fresh/disowned fragment

    def op_replace(self, start: int, end: int, text: str) -> None:
        """ONE atomic whole-buffer set with the owned range rewritten."""
        self.text = self.text[:start] + text + self.text[end:]
        self.owned = (start, start + utf16_len(text))

    def op_cancel(self) -> None:
        """Remove the owned range in ONE op; ownership ends."""
        assert self.owned is not None, "cancel with no owned range"
        s, e = self.owned
        self.text = self.text[:s] + self.text[e:]
        self.owned = None

    def take_real_key(self, keysym_text: str = " ") -> None:
        """A delegated REAL keystroke while owned: dirty flips, ownership
        (and the buffer at the caret) changes exactly as the user's key did."""
        if self.owned is not None and not self.dirty:
            self.dirty = True
        self.text += keysym_text

    # -- expectations the lab asserts against read replies -------------------
    @property
    def caret_u16(self) -> int:
        """Absolute UTF-16 caret offset (end-of-buffer in this trace)."""
        return utf16_len(self.text)

    def cursor(self) -> dict[str, int]:
        """The extension's {line, col} for a single-line buffer."""
        return {"line": 0, "col": self.caret_u16}


# ---------------------------------------------------------------------------
# The honest status rule (decided in THIS order, per the PRP)
# ---------------------------------------------------------------------------


def row_status(
    *,
    boot_ok: bool,
    traces_passed: bool,
    corrections_passed: bool,
    visibility_instrumented: bool,
    block_reason: str = "",
) -> str:
    """Map the measured outcome to exactly one R.7 status string.

    Order (the PRP's status rule, verbatim intent):
      1. boot/socket failure                      -> "blocked (<reason>)"
      2. all traces pass AND visible prompt is
         instrumented (a rendered-prompt dump)    -> "verified (versions + evidence)"
      3. traces pass but NO rendered-prompt
         instrumentation exists                   -> "not verified (visibility
                                                     instrumentation absent)"
      4. inserts pass but corrections fail        -> "insert-only"
      5. nothing was measured                     -> "untested"

    A G2/lab pass can never reach branch 2 from buffer state alone: the
    caller must attest the visible-prompt instrumentation explicitly.
    """
    if not boot_ok:
        return f"blocked ({block_reason or 'boot failed'})"
    if traces_passed and visibility_instrumented:
        return "verified (versions + evidence)"
    if traces_passed and not visibility_instrumented:
        return "not verified (visibility instrumentation absent)"
    if corrections_passed:
        return "insert-only"
    return "untested"


# ---------------------------------------------------------------------------
# Verdict rows (report table + JSONL evidence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerdictRow:
    """One row of the report / one JSONL line (the matrix convention)."""

    row: str
    passed: bool | None  # None = infra-untested, never a pass
    status: str
    detail: str = ""
    versions: dict[str, str] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()

    def to_jsonl(self) -> str:
        """One machine-readable line (t_ms fields are mechanism-level ONLY)."""
        return json.dumps(
            {
                "row": self.row,
                "passed": self.passed,
                "status": self.status,
                "detail": self.detail,
                "versions": dict(self.versions),
                "evidence": list(self.evidence),
            },
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# The four-contract detector: no folded-paste placeholders / control bytes
# ---------------------------------------------------------------------------


def assert_no_paste_markers(text: str) -> tuple[str, ...]:
    """Return every forbidden byte-class found in an editor read-back.

    Checks: the bracketed-paste markers ESC[200~ / ESC[201~ (a folded paste
    placeholder would surface as exactly these), any other C0 control byte,
    tab, CR, and LF (the trace payloads are single-line prose; R.1 forbids
    Enter/newline ever reaching the buffer). Empty tuple == clean.
    """
    found: list[str] = []
    for marker in ("\x1b[200~", "\x1b[201~"):
        if marker in text:
            found.append(f"paste-marker {marker!r}")
    for ch in text:
        if ch in ("\t", "\n", "\r"):
            found.append(f"whitespace-control {ch!r}")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            found.append(f"control-byte U+{ord(ch):04X}")
    return tuple(found)


# ---------------------------------------------------------------------------
# Bounded report renderer (<= MAX_REPORT_LINES, matrix style)
# ---------------------------------------------------------------------------


def render_row_report(
    title: str,
    header_lines: list[str],
    rows: list[VerdictRow],
    section_lines: list[str],
) -> str:
    """Render the bounded row report; never exceed MAX_REPORT_LINES total."""
    lines: list[str] = [f"# {title}", ""]
    lines.extend(header_lines)
    lines.append("")
    lines.append("| row | pass | status | detail |")
    lines.append("|---|---|---|---|")
    for r in rows:
        detail = r.detail if len(r.detail) <= 60 else r.detail[:57] + "..."
        lines.append(f"| {r.row} | {r.passed} | {r.status} | {detail} |")
    lines.append("")
    lines.extend(section_lines)
    if len(lines) > MAX_REPORT_LINES:
        kept = lines[: MAX_REPORT_LINES - 1]
        kept.append(f"… [truncated at {MAX_REPORT_LINES} lines]")
        lines = kept
    return "\n".join(lines) + "\n"

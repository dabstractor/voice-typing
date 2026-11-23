"""clipboard_g4_support — pure stdlib helpers for the G4 clipboard gate.

Leg models, the verdict vocabulary, the R.6 clause→leg map, JSONL I/O, and
the bounded (≤150-line) evidence renderer for P1.M5.T3.S1
(tests/clipboard_g4_lab.py is the live harness; this module has NO process,
socket, or desktop code — importable by unit tests everywhere).

VERDICT VOCABULARY (honest outcomes only):
  verified    — the leg ran and its assertions held, with live versions +
                capped evidence attached.
  unprovable  — the leg ran, the mechanism behaved as designed, and the R.6
                property itself still cannot be claimed with the local
                manager (the PRD-pre-declared UNAVAILABLE-under-watcher case).
  blocked     — the leg could not run for a stated environmental reason
                (never silently skipped; the reason is recorded).

G4 NEVER judges exit codes: every leg asserts contents, history, formats,
target, and the untouched PRIMARY (PRD R.7).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

MAX_REPORT_LINES = 150
_EVIDENCE_CAP = 4
VERIFIED = "verified"
UNPROVABLE = "unprovable"
BLOCKED = "blocked"
STATUSES = (VERIFIED, UNPROVABLE, BLOCKED)

ROUTE_TABLE_KEY = "clipboard_fallback_m5t3"
ROUTE_TABLE_CITATION = (
    'plan/008_a47116bb2b79/architecture/g3_field_matrix.md route table: '
    'clipboard_fallback_m5t3: "needed (ghostty-class insert blocked at 1.4.0-2)"'
)
GHOSTTY_WATCH_NOTE = (
    "ghostty 1.5.0 watch — PR #15246 milestone; the matrix re-run (P1.M4.T5.S2's "
    "artifact) is the future ELSE trigger for this route, not this item."
)

# The six PRD R.7 G4 legs. `assertion` is what the leg VERIFIES (never an
# exit code): contents / history / formats / target / PRIMARY.
@dataclass(frozen=True)
class G4Leg:
    leg: str          # L1..L6
    title: str
    clause: str       # which R.6 clause this leg is the proof for
    assertion: str

SIX_LEGS: tuple[G4Leg, ...] = (
    G4Leg("L1", "private manager (text+image watchers) — history pollution?",
          "R.6 clause 4 (partials out of the history watcher)",
          "watcher detected at acquire ⇒ refusal BEFORE delivery; private store "
          "contains ZERO voice fragments; clause-4 with-watcher cleanliness is "
          "recorded unprovable, never faked"),
    G4Leg("L2", "simultaneous foreign copies incl. byte-identical",
          "R.6 clause 2 (ownership ≠ content) + clause 3 (protect the paste)",
          "nonce sentinel + cancelled event distinguish a byte-identical foreign "
          "copy; adapter aborts pre-trigger (REFUSED), snapshot restored exact, "
          "target witness empty (no paste fired)"),
    G4Leg("L3", "user paste during transfer",
          "R.6 clause 3 (protect a simultaneous user paste)",
          "second chord + foreign selection mid-window ⇒ target receives EXACTLY "
          "one paste (no doubling); adapter outcome ∈ {refused, unknown} — never "
          "falsely applied; clipboard restored"),
    G4Leg("L4", "original-offer classes: empty / rich-text / image",
          "R.6 clause 1 (preserve ALL prior formats AND bytes)",
          "snapshot + restore via a data-control source: every original type "
          "re-offered with EXACT per-type bytes; empty restores to null selection"),
    G4Leg("L5", "failure before/after the data request",
          "R.3 unknown discipline (bytes sent ≠ applied)",
          "target death pre-read ⇒ UNKNOWN, never applied, clipboard intact; "
          "runner killed post-restore ⇒ witness proves delivery, record stays "
          "unknown-class"),
    G4Leg("L6", "process death mid-cycle",
          "R.6 clause 1 + R.3 lifecycle",
          "SIGKILL mid-cycle ⇒ clipboard ends restored-or-visibly-faulted "
          "(observed shape recorded honestly); PRIMARY + formats + history "
          "verified"),
)

# The four R.6 clauses + the PRIMARY rider, each with its named mechanism.
R6_CLAUSES: tuple[dict[str, str], ...] = (
    {"clause": "1", "requirement": "preserve all prior formats AND bytes",
     "mechanism": "data-control snapshot of every offered type (exact bytes) + "
                  "restore via a zwlr_data_control_source serving per-type bytes",
     "legs": "L4"},
    {"clause": "2", "requirement": "ownership distinguished from a later identical copy",
     "mechanism": "sentinel nonce MIME (x-voice-typing/nonce, fresh per staging "
                  "generation) on OUR sources only; source-cancelled event — never content comparison",
     "legs": "L2"},
    {"clause": "3", "requirement": "simultaneous user paste protected",
     "mechanism": "mutation-time recheck through a sync barrier (cancelled ⇒ abort "
                  "+ restore); positive witness required for applied",
     "legs": "L2, L3, L5"},
    {"clause": "4", "requirement": "partials kept out of the configured history watcher",
     "mechanism": "detect watcher at acquire (scoped /proc scan) ⇒ fail BEFORE "
                  "delivery — never disable the manager",
     "legs": "L1"},
    {"clause": "+", "requirement": "PRIMARY selection untouched",
     "mechanism": "only clipboard set_selection is ever sent; set_primary_selection "
                  "is never called; asserted unchanged after every leg",
     "legs": "L1–L6 (invariant)"},
)


@dataclass
class G4Verdict:
    """One leg's honest outcome (rendered to verdicts.jsonl + the report)."""

    leg: str
    title: str = ""
    status: str = BLOCKED
    reason: str = ""
    checks: list[str] = field(default_factory=list)     # PASS/FAIL assertion lines
    evidence: list[str] = field(default_factory=list)   # capped factual lines
    primary_unchanged: bool | None = None
    versions: dict[str, str] = field(default_factory=dict)
    t_ms: float | None = None                            # mechanism info, NEVER G5

    def to_dict(self) -> dict:
        return asdict(self)


def status_ok(status: str) -> bool:
    return status in STATUSES


def verdict_from_dict(v: dict) -> G4Verdict:
    """Parse one lab verdict line; unknown statuses are a hard error (the
    vocabulary is closed — a smoothe-over 'passed' word must not sneak in)."""
    status = v.get("status", BLOCKED)
    if not status_ok(status):
        raise ValueError(f"verdict status {status!r} outside the honest vocabulary")
    return G4Verdict(
        leg=v.get("leg", "?"),
        title=v.get("title", ""),
        status=status,
        reason=v.get("reason", ""),
        checks=list(v.get("checks", [])),
        evidence=list(v.get("evidence", []))[:_EVIDENCE_CAP],
        primary_unchanged=v.get("primary_unchanged"),
        versions=dict(v.get("versions", {})),
        t_ms=v.get("t_ms"),
    )


def read_verdicts(path) -> list[G4Verdict]:
    verdicts: list[G4Verdict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                verdicts.append(verdict_from_dict(json.loads(line)))
    return verdicts


def write_verdicts(path, verdicts: list[G4Verdict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for v in verdicts:
            fh.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")


def leg_recorded(verdicts: list[G4Verdict], leg: str) -> bool:
    return any(v.leg == leg for v in verdicts)


def all_legs_recorded(verdicts: list[G4Verdict]) -> bool:
    return all(leg_recorded(verdicts, leg.leg) for leg in SIX_LEGS)


def availability_statement(verdicts: list[G4Verdict]) -> str:
    """Derive the honest availability statement from the leg verdicts.

    The PRD-pre-declared legitimate outcome: a watcher was active, the adapter
    refused to engage, clause 4 is recorded unprovable ⇒ UNAVAILABLE under a
    clipboard-history watcher (the manager is never disabled). AVAILABLE
    requires a recorded no-watcher engagement with clause 1–3 verified and
    zero fragments in any history surface. Anything else is UNAVAILABLE with
    the recorded reason.
    """
    l1 = next((v for v in verdicts if v.leg == "L1"), None)
    if l1 is not None and l1.status == UNPROVABLE and "watcher" in l1.reason:
        return ("UNAVAILABLE under a clipboard-history watcher — R.6 partials-"
                "out-of-history unprovable with the local manager; the adapter "
                "refuses to engage and the manager is never disabled")
    engaged = [v for v in verdicts if v.status == VERIFIED]
    if l1 is not None and l1.status == VERIFIED and len(engaged) >= len(SIX_LEGS):
        return "AVAILABLE — engaged with no history pollution and clauses 1–4 verified"
    reason = next((v.reason for v in verdicts if v.status == BLOCKED and v.reason),
                  "insufficient leg evidence")
    return f"UNAVAILABLE (other reason: {reason})"


def render_g4_report(versions: dict[str, str], verdicts: list[G4Verdict],
                     meta: dict[str, str]) -> str:
    """Render the bounded evidence report (the item's OUTPUT). Hard cap
    MAX_REPORT_LINES; the open-items tail survives truncation with an honest
    '[… truncated …]' marker. Timing values are mechanism info — the renderer
    never emits a G5 claim."""
    lines: list[str] = []
    lines.append("# G4 clipboard contract — evidence report (P1.M5.T3.S1)")
    lines.append("")
    lines.append(f"- Date: {meta.get('date', 'unknown')}  |  HEAD: {meta.get('head', 'unknown')}")
    lines.append(f"- Command: `{meta.get('command', 'n/a')}`")
    lines.append(f"- Decision: {ROUTE_TABLE_CITATION}")
    for key in ("kernel", "sway", "ghostty", "wl_clipboard", "xdotool"):
        if versions.get(key):
            lines.append(f"- {key}: {versions[key]}")
    lines.append("")
    lines.append("> Honesty rules: verdicts use ONLY verified | unprovable | blocked;")
    lines.append("> legs assert contents/history/formats/target/PRIMARY, never exit")
    lines.append("> codes; t_ms values are mechanism info, NEVER G5 timing (no")
    lines.append("> speech in this run).")
    lines.append("")
    lines.append("## Decision input (recorded FIRST; never re-derived)")
    lines.append(f"`{ROUTE_TABLE_KEY}`: needed at HEAD (ghostty 1.4.0-2 insert blocked;")
    lines.append("route = clipboard insert-fallback under R.6).")
    lines.append("")
    lines.append("## R.6 clause → mechanism → leg")
    lines.append("| clause | requirement | mechanism | leg |")
    lines.append("|---|---|---|---|")
    for c in R6_CLAUSES:
        lines.append(f"| {c['clause']} | {c['requirement']} | {c['mechanism']} | {c['legs']} |")
    lines.append("")
    lines.append("## Leg verdicts")
    lines.append("| leg | status | PRIMARY unchanged | key evidence |")
    lines.append("|---|---|---|---|")
    for v in verdicts:
        prim = "n/a" if v.primary_unchanged is None else ("yes" if v.primary_unchanged else "NO")
        key_ev = (v.evidence[0] if v.evidence else v.reason)[:110]
        lines.append(f"| {v.leg} {v.title[:46]} | {v.status} | {prim} | {key_ev} |")
    for v in verdicts:
        lines.append(f"### {v.leg}")
        if v.reason:
            lines.append(f"  reason: {v.reason}")
        for chk in v.checks[:_EVIDENCE_CAP]:
            lines.append(f"  check: {chk}")
        for ev in v.evidence[:_EVIDENCE_CAP]:
            lines.append(f"  {ev}")
        if v.t_ms is not None:
            lines.append(f"  t_ms (mechanism only, NOT G5): {v.t_ms}")
    lines.append("")
    lines.append("## Availability statement")
    lines.append(availability_statement(verdicts))
    lines.append("")
    lines.append(f"Verdicts file: {meta.get('verdicts_path', 'g4_clipboard_verdicts.jsonl')}")
    lines.append("")
    open_items = meta.get("open_items") or [GHOSTTY_WATCH_NOTE]
    lines.append("## Open items")
    for item in open_items:
        lines.append(f"- {item}")
    lines.append("")
    if meta.get("summary"):
        lines.append(f"Summary: {meta['summary']}")
        lines.append("")
    if len(lines) > MAX_REPORT_LINES:
        head = lines[: MAX_REPORT_LINES - 4]
        tail = [ln for ln in lines[len(head):]
                if ln.startswith(("- ", "#", "UNAVAILABLE", "AVAILABLE"))]
        lines = head + ["[… truncated …]"] + tail[-3:]
    return "\n".join(lines[:MAX_REPORT_LINES])

"""g6_assessment — the mechanical G6 graduation verdict engine (P1.M7.T1.S1).

Pure stdlib. NO CUDA, NO desktop, NO compositor, NO service contact, NO
network: every input is a committed evidence artifact (G7). It reads:

  - plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl        (G3 rows, condition A/B)
  - plan/008_a47116bb2b79/architecture/editor_browser_row_verdicts.jsonl (A/B)
  - plan/008_a47116bb2b79/architecture/g2_gate_record.md            (B)
  - tests/G5_TIMING_EVIDENCE.md                                     (C; P1.M6.T4.S1)
  - tests/G6_WRITING_SESSIONS.md                                    (D; operator-authored ONLY)

and derives the PRD §4.2sexies R.7 G6 decision — FLIP iff ALL of:

  A. verified G3 rows for the pi prompt in Ghostty, a graphical editor, and
     a browser text field (insert AND correct on each);
  B. zero observed integrity failures (zero failed rows / non-empty checks
     across both G3 registers + G2 record with no failing trace);
  C. G5 per-route timing evidence passing on every claimed route;
  D. >= 3 operator-attributed writing sessions whose usable proofread wpm
     (counting corrections, recovery, and rereading) beats 110.

Honesty rules (R.2 / PRP Gotchas):
  - absent or unparsable evidence is UNMET / not-run, never passed (G2);
  - a passing transport probe NEVER substitutes for G3/G5/G6 rows (R.2);
  - session entries are operator-authored; the parser enforces attribution
    and this tool never writes entries (G1);
  - the decision is data, not an error: exit code is 0 for BOTH outcomes (G8).

CLI:  timeout 60 .venv/bin/python tests/g6_assessment.py
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_ARCH = REPO_ROOT / "plan" / "008_a47116bb2b79" / "architecture"
PI_ROWS_PATH = PLAN_ARCH / "pi_row_verdicts.jsonl"
EB_ROWS_PATH = PLAN_ARCH / "editor_browser_row_verdicts.jsonl"
G2_RECORD_PATH = PLAN_ARCH / "g2_gate_record.md"
G5_REPORT_PATH = REPO_ROOT / "tests" / "G5_TIMING_EVIDENCE.md"
SESSIONS_PATH = REPO_ROOT / "tests" / "G6_WRITING_SESSIONS.md"

WPM_TARGET = 110.0  # G6: usable proofread wpm must BEAT 110 (strictly >)
MIN_SESSIONS = 3  # G6: at least three representative completed sessions
WPM_TOLERANCE = 1.0  # entry's stated usable_wpm must match the computed one

# Required G3 row classes, derived by ENUMERATING the committed registers
# (Task 0 preflight, PRP research §2 caveat: derive, don't guess). Each entry
# is (surface, kind, row-name substring predicates). A class counts as
# present iff at least one row matches; whether it PASSED is decided by the
# all-rows check, not by the pattern.
REQUIRED_ROW_CLASSES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("pi-ghostty", "insert", ("-insert",)),
    ("pi-ghostty", "correct", ("correction",)),
    ("editor", "insert", ("editor-short-updates", "editor-long-unicode")),
    ("editor", "correct", ("editor-firstword",)),
    ("browser", "insert", ("browser-short-updates", "browser-long-unicode")),
    ("browser", "correct", ("browser-firstword",)),
)

# status/verdict markers that DENY verification even when a pass flag is true
# or absent (e.g. pi-prompt-ghostty passed:true status "not verified (...)";
# class-browser-text-field pass:null verdict "insert-only (correction REFUSED...)").
_DENY_PASS_TRUE_MARKER = "not verified"  # e.g. pi-prompt-ghostty passed:true, status
# "not verified (visibility instrumentation absent)" — the flag alone must NOT
# count as verified (R.2: never upgrade a NOT VERIFIED claim).
# Markers that deny verification on FLAGLESS summary rows only (the verdict
# text is the only signal there). NB: "refused" is a legitimate EXPECTED status
# on passing refuse-* rows, so it must never deny a pass:true row.
_SUMMARY_DENY_MARKERS = ("not verified", "refused", "insert-only")

_FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_SESSION_HEADER_RE = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.+?)\s*$")
_ROUTE_VERDICT_RE = re.compile(r"\*{0,2}(pass|fail|blocked)\*{0,2}", re.IGNORECASE)


# --------------------------------------------------------------------------
# data model (Blueprint; no ORM/pydantic — pure stdlib dataclasses)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ConditionResult:
    """One G6 condition's verdict: verified | unmet | not-run (+ evidence)."""

    condition: str  # "A-g3-matrix" | "B-integrity" | "C-g5-timing" | "D-sessions"
    verdict: str  # "verified" | "unmet" | "not-run"
    reason: str = ""  # "" when verified; else the specific missing/failed evidence
    evidence: tuple[str, ...] = ()  # paths/counts quoted (never full contents)


@dataclass(frozen=True)
class Assessment:
    results: tuple[ConditionResult, ...]

    @property
    def flip(self) -> bool:
        return all(r.verdict == "verified" for r in self.results)

    @property
    def unmet(self) -> tuple[str, ...]:
        return tuple(r.condition for r in self.results if r.verdict != "verified")

    @property
    def decision_line(self) -> str:
        if self.flip:
            return "G6 DECISION: FLIP"
        return f"G6 DECISION: STAY OPT-IN (unmet: {', '.join(self.unmet)})"


@dataclass(frozen=True)
class WritingSession:
    """One operator-authored writing-session entry (G6 condition D)."""

    date: str  # YYYY-MM-DD
    minutes: float  # wall-clock session duration
    raw_words: int
    correction_min: float  # time spent correcting
    recovery_min: float  # time spent recovering (re-arm, cancel-respeak, freeze)
    rereading_min: float  # time spent proofreading/rereading
    attributed: str  # operator attribution (REQUIRED; entries without are invalid)

    @property
    def effective_min(self) -> float:
        return (
            self.minutes - self.correction_min - self.recovery_min - self.rereading_min
        )

    @property
    def usable_wpm(self) -> float:
        """Usable proofread wpm: raw words over the net (non-accounted) minutes.

        The accounting subtracts corrections, recovery, and rereading per
        PRD §4.2sexies R.7 G6 — exactly the rules the template documents.
        """
        return self.raw_words / self.effective_min


# --------------------------------------------------------------------------
# G3 register loading + row classification (conditions A and B)
# --------------------------------------------------------------------------


def load_jsonl(path: Path) -> tuple[list[dict], str] | None:
    """Load a jsonl register; None if unreadable/unparsable (fail-closed)."""
    try:
        rows = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
    except OSError:
        return None
    except json.JSONDecodeError:
        return None
    return rows, path.name


def classify_row(row: dict) -> str:
    """Classify one verdict row: "passed" | "failed" | "not-verified".

    Tolerant of both registers' pass-field names ("passed" / "pass") and of
    the class-summary rows that carry only a verdict string. A row with
    non-empty `checks` is a failed row (the checks ARE the failures).
    """
    if row.get("checks"):
        return "failed"
    pass_val = row.get("passed", row.get("pass"))
    text = str(row.get("status") or row.get("verdict") or "").lower()
    if pass_val is False:
        return "failed"
    if pass_val is True:
        return "not-verified" if _DENY_PASS_TRUE_MARKER in text else "passed"
    # No boolean pass flag (summary rows): the verdict text decides.
    if "verified" in text and not any(m in text for m in _SUMMARY_DENY_MARKERS):
        return "passed"
    return "not-verified"


def _register_report(
    name: str, rows: list[dict]
) -> tuple[list[str], list[str], list[str]]:
    """Split register rows into (failed, not-verified, all-row-names)."""
    failed: list[str] = []
    unverified: list[str] = []
    names: list[str] = []
    for row in rows:
        names.append(str(row.get("row", "<unnamed>")))
        verdict = classify_row(row)
        if verdict == "failed":
            failed.append(names[-1])
        elif verdict == "not-verified":
            unverified.append(names[-1])
    return failed, unverified, names


def _missing_row_classes(names: list[str]) -> list[str]:
    missing = []
    for surface, kind, predicates in REQUIRED_ROW_CLASSES:
        if not any(any(p in n for p in predicates) for n in names):
            missing.append(f"{surface}:{kind}")
    return missing


def assess_g3_matrix(
    pi_path: Path = PI_ROWS_PATH, eb_path: Path = EB_ROWS_PATH
) -> ConditionResult:
    """Condition A — every G3 row passed and all required row classes present."""
    loaded = {p: load_jsonl(p) for p in (pi_path, eb_path)}
    if any(v is None for v in loaded.values()):
        missing = [p.name for p, v in loaded.items() if v is None]
        return ConditionResult(
            "A-g3-matrix", "unmet", f"cannot read register(s): {', '.join(missing)}"
        )
    loaded_pi, loaded_eb = loaded[pi_path], loaded[eb_path]
    failed, unverified, names = [], [], []
    for rows, _ in (loaded_pi, loaded_eb):
        f, u, n = _register_report("register", rows)
        failed.extend(f)
        unverified.extend(u)
        names.extend(n)
    evidence = (
        f"{pi_path.name}:{len(loaded_pi[0])} rows",
        f"{eb_path.name}:{len(loaded_eb[0])} rows",
    )
    problems = []
    if failed:
        problems.append(f"failed rows: {failed}")
    if unverified:
        problems.append(f"unverified rows: {unverified}")
    if problems:
        return ConditionResult("A-g3-matrix", "unmet", "; ".join(problems), evidence)
    missing = _missing_row_classes(names)
    if missing:
        return ConditionResult(
            "A-g3-matrix", "unmet", f"missing rows: {missing}", evidence
        )
    return ConditionResult("A-g3-matrix", "verified", "", evidence)


def assess_integrity(
    pi_path: Path = PI_ROWS_PATH,
    eb_path: Path = EB_ROWS_PATH,
    g2_path: Path = G2_RECORD_PATH,
) -> ConditionResult:
    """Condition B — zero observed integrity failures.

    Mechanical rule: zero failed rows / non-empty `checks` across both G3
    registers, plus a readable G2 gate record with no failing (❌) trace.
    """
    loaded_pi = load_jsonl(pi_path)
    loaded_eb = load_jsonl(eb_path)
    failed: list[str] = []
    if loaded_pi is not None:
        failed.extend(_register_report(pi_path.name, loaded_pi[0])[0])
    if loaded_eb is not None:
        failed.extend(_register_report(eb_path.name, loaded_eb[0])[0])
    if failed:
        return ConditionResult(
            "B-integrity", "unmet", f"failed register rows: {sorted(set(failed))}"
        )
    try:
        g2_text = g2_path.read_text()
    except OSError:
        return ConditionResult(
            "B-integrity", "unmet", f"cannot read G2 gate record ({g2_path})"
        )
    if "❌" in g2_text:
        return ConditionResult(
            "B-integrity", "unmet", f"failing trace recorded in {g2_path.name}"
        )
    return ConditionResult(
        "B-integrity",
        "verified",
        "",
        (f"{g2_path.name}: no failing trace", "G3 registers: zero failed rows"),
    )


# --------------------------------------------------------------------------
# condition C — the G5 per-route timing report
# --------------------------------------------------------------------------


def parse_route_verdicts(report_text: str) -> dict[str, str] | None:
    """Extract {route: pass|fail|blocked} from the G5 report's verdict table.

    Matches the format the P1.M6.T4.S1 PRP commits: a `| route | verdict |`
    table whose route rows carry `**pass** | **fail**(reason) | **blocked**`
    verdicts. Returns None when no route rows can be found (unparsable).
    """
    routes: dict[str, str] = {}
    in_table = False
    for line in report_text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            in_table = False
            continue
        if cells[0] == "route":
            in_table = True
            continue
        if not in_table or set(cells[0]) <= {"-", " ", ":"}:
            continue
        m = _ROUTE_VERDICT_RE.search(cells[1])
        if m is None:
            continue
        routes[cells[0]] = m.group(1).lower()
    return routes or None


def assess_g5_timing(report_path: Path = G5_REPORT_PATH) -> ConditionResult:
    """Condition C — every claimed G5 route verdict is pass (never pass-by-default)."""
    if not report_path.is_file():
        return ConditionResult(
            "C-g5-timing", "not-run", f"G5 report absent ({report_path}; P1.M6.T4.S1)"
        )
    try:
        report_text = report_path.read_text()
    except OSError:
        return ConditionResult(
            "C-g5-timing", "not-run", f"cannot read report ({report_path})"
        )
    verdicts = parse_route_verdicts(report_text)
    if verdicts is None:
        return ConditionResult("C-g5-timing", "not-run", "cannot parse report format")
    failed = [r for r, v in verdicts.items() if v != "pass"]
    if failed:
        return ConditionResult(
            "C-g5-timing",
            "unmet",
            f"failing/blocked routes: {failed}",
            tuple(f"{report_path.name}:{r}" for r in sorted(verdicts)),
        )
    return ConditionResult(
        "C-g5-timing",
        "verified",
        "",
        tuple(f"{report_path.name}:{r}=pass" for r in sorted(verdicts)),
    )


# --------------------------------------------------------------------------
# condition D — the operator-authored writing sessions
# --------------------------------------------------------------------------


def parse_writing_sessions(text: str) -> tuple[list[WritingSession], list[str]]:
    """Parse sessions entries; returns (valid_sessions, invalid_reasons).

    STRICT format (pinned by tests/G6_WRITING_SESSIONS.md): `### YYYY-MM-DD`
    blocks of `key: value` lines carrying duration_min, raw_words,
    correction_min, recovery_min, rereading_min, usable_wpm, and a REQUIRED
    `attributed:` line (entries without attribution are invalid — G1).
    Fenced code blocks (the commented example) are ignored.
    """
    text = _FENCED_BLOCK_RE.sub("", text)
    valid: list[WritingSession] = []
    invalid: list[str] = []
    headers = list(_SESSION_HEADER_RE.finditer(text))
    for i, m in enumerate(headers):
        date = m.group(1)
        body = text[
            m.end() : headers[i + 1].start() if i + 1 < len(headers) else len(text)
        ]
        fields: dict[str, str] = {}
        for line in body.splitlines():
            fm = _FIELD_RE.match(line.strip())
            if fm and fm.group(1) not in fields:
                fields[fm.group(1)] = fm.group(2)
        problems: list[str] = []
        nums: dict[str, float] = {}
        for key in (
            "duration_min",
            "raw_words",
            "correction_min",
            "recovery_min",
            "rereading_min",
            "usable_wpm",
        ):
            try:
                nums[key] = float(fields[key])
            except (KeyError, ValueError):
                problems.append(f"{key} missing/unparsable")
        attribution = fields.get("attributed", "").strip()
        if not attribution:
            problems.append(
                "no operator attribution (entries are operator-authored ONLY)"
            )
        if not problems:
            session = WritingSession(
                date=date,
                minutes=nums["duration_min"],
                raw_words=int(nums["raw_words"]),
                correction_min=nums["correction_min"],
                recovery_min=nums["recovery_min"],
                rereading_min=nums["rereading_min"],
                attributed=attribution,
            )
            if session.effective_min <= 0:
                problems.append(
                    f"accounting leaves {session.effective_min:.1f} net minutes (<= 0)"
                )
            elif abs(session.usable_wpm - nums["usable_wpm"]) > WPM_TOLERANCE:
                problems.append(
                    f"stated usable_wpm {nums['usable_wpm']:.1f} != computed "
                    f"{session.usable_wpm:.1f} (raw_words / net minutes)"
                )
        if problems:
            invalid.append(f"{date}: {'; '.join(problems)}")
        else:
            valid.append(session)
    return valid, invalid


def assess_writing_sessions(path: Path = SESSIONS_PATH) -> ConditionResult:
    """Condition D — >= MIN_SESSIONS operator sessions, each usable wpm > WPM_TARGET."""
    if not path.is_file():
        return ConditionResult(
            "D-sessions",
            "unmet",
            "no operator writing-session evidence on record "
            f"({path.name} absent; entries are operator-authored ONLY)",
        )
    valid, invalid = parse_writing_sessions(path.read_text())
    if invalid:
        return ConditionResult(
            "D-sessions",
            "unmet",
            f"invalid session entries: {invalid}",
            (f"{path.name}: {len(valid)} valid",),
        )
    slow = [s.date for s in valid if s.usable_wpm <= WPM_TARGET]
    if slow:
        detail = ", ".join(
            f"{s.date}={s.usable_wpm:.1f}wpm" for s in valid if s.date in slow
        )
        return ConditionResult(
            "D-sessions",
            "unmet",
            f"sessions at/below {WPM_TARGET:.0f} usable wpm (must BEAT it): {detail}",
        )
    if len(valid) < MIN_SESSIONS:
        return ConditionResult(
            "D-sessions",
            "unmet",
            f"{len(valid)} valid session(s) on record, need >= {MIN_SESSIONS}",
            (f"{path.name}: {len(valid)} valid",),
        )
    return ConditionResult(
        "D-sessions",
        "verified",
        "",
        tuple(
            f"{path.name}:{s.date}={s.usable_wpm:.1f}wpm({s.attributed})" for s in valid
        ),
    )


# --------------------------------------------------------------------------
# the assessment + CLI
# --------------------------------------------------------------------------


def run_assessment(repo_root: Path = REPO_ROOT) -> Assessment:
    """Derive the G6 verdict from the committed artifacts under repo_root."""
    arch = repo_root / "plan" / "008_a47116bb2b79" / "architecture"
    return Assessment(
        results=(
            assess_g3_matrix(
                arch / "pi_row_verdicts.jsonl",
                arch / "editor_browser_row_verdicts.jsonl",
            ),
            assess_integrity(
                arch / "pi_row_verdicts.jsonl",
                arch / "editor_browser_row_verdicts.jsonl",
                arch / "g2_gate_record.md",
            ),
            assess_g5_timing(repo_root / "tests" / "G5_TIMING_EVIDENCE.md"),
            assess_writing_sessions(repo_root / "tests" / "G6_WRITING_SESSIONS.md"),
        )
    )


def format_assessment(assessment: Assessment) -> str:
    lines = ["G6 GRADUATION ASSESSMENT (PRD §4.2sexies R.7)"]
    for r in assessment.results:
        lines.append(
            f"  {r.condition}: {r.verdict}" + (f" — {r.reason}" if r.reason else "")
        )
        for ev in r.evidence:
            lines.append(f"    evidence: {ev}")
    lines.append(assessment.decision_line)
    return "\n".join(lines)


def main() -> int:
    """Print the per-condition block + decision; exit 0 for BOTH outcomes (G8)."""
    print(format_assessment(run_assessment()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

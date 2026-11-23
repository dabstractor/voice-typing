"""ime_g3_support — pure, venv-importable logic for the G3 real-field harness
(P1.M4.T5.S1).

NO gi / wayland / pytest / voice_typing imports: this module is imported BOTH by
the collected unit tests (tests/test_ime_g3_support.py, venv python) and by the
live lab (tests/ime_g3_lab.py) and the GTK field app's schema (tests/
ime_g3_field_gtk.py documents the same dump shape).

Contents:
  - ROW_STATUSES          the closed G3 row-status vocabulary (PRD §4.2sexies R.7):
                          "untested | insert-only | blocked (reason) |
                          verified (versions + evidence links)"
  - RowVerdict            one row's verdict (pass True/False/None — None is
                          infra-untested and is NEVER a pass)
  - row_status()          verdicts -> closed-vocabulary status string
  - text_hash8()          sha1(text utf-8)[:8] — the frame-oracle's hash space
  - single_edit_analysis()the frame-level oracle over two field dumps
  - build_payloads()      deterministic row payloads (sizes in UTF-8 BYTES)
  - render_report()       the bounded row-report renderer (<= MAX_REPORT_LINES)

Report conventions follow plan/008_a47116bb2b79/architecture/g2_gate_record.md
and tests/D1_DUCK_EVIDENCE.md: date + HEAD header, verbatim mandate banner
("a G2 pass never marks a row verified"), capped evidence excerpts, open items.
Lineage: tools/im-lab (29 rows / 24 pass, 2026-11-22) productized per
plan/008_a47116bb2b79/P1M4T5S1/research/imlab-pattern.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# --- the closed status vocabulary (R.7, verbatim set) ------------------------
ROW_STATUSES = ("untested", "insert-only", "blocked", "verified")

VERIFIED_SUFFIX = "verified (versions + evidence)"

ROW_IDS = (
    "gtk-short-updates",
    "gtk-firstword-20sent",
    "gtk-identical-finals",
    "gtk-long-unicode",
    "gtk-refusing-readonly",
)

OVERCAP_BLOCKED_REASON = (
    "4000-byte commit cap — refused by design; chunking vs R.1 one-edit rule undecided"
)


@dataclass(frozen=True)
class RowVerdict:
    """One JSON verdict line, typed. passed=None means infra-untested."""

    row: str  # one of ROW_IDS
    sub: str = ""  # "unicode-951b" / "mixed-3500b" / "overcap-4500b" / ""
    passed: bool | None = None
    checks: tuple[str, ...] = field(default_factory=tuple)  # failed assertion names
    t_ms: int | None = None  # mechanism-level info ONLY — never claimed as G5


def row_status(
    verdicts: list[RowVerdict],
    *,
    exercised_correction: bool,
    capability_blocked_reason: str | None = None,
) -> str:
    """Map a row's verdicts onto the closed vocabulary. NEVER invents words.

    - any False            -> "blocked (FAILED: <first check>)"  (honest failure)
    - capability gap       -> "blocked (<reason>)"  (e.g. over-cap refused-by-design)
    - any None, no False   -> "untested (infra: <reason>)"
    - all True + correction exercised -> "verified (versions + evidence)"
    - all True, insert-only paths     -> "insert-only" (never "verified")
    """
    if capability_blocked_reason:
        return f"blocked ({capability_blocked_reason})"
    failed = [v for v in verdicts if v.passed is False]
    if failed:
        first = failed[0]
        check = first.checks[0] if first.checks else first.row
        return f"blocked (FAILED: {check})"
    untested = [v for v in verdicts if v.passed is None]
    if untested:
        v = untested[0]
        why = v.sub or v.row or "unspecified"
        return f"untested (infra: {why})"
    if not verdicts:
        return "untested (infra: no verdicts)"
    if exercised_correction:
        return VERIFIED_SUFFIX
    return "insert-only"


# --- frame oracle -------------------------------------------------------------


def text_hash8(text: str) -> str:
    """The frame-oracle hash space: sha1(utf-8 bytes)[:8]."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _window_segments(ring_rle, frames_before: int, frames_after: int):
    """Consume exactly (frames_after - frames_before) frames from the NEWEST end
    of the RLE ring ([h, n] pairs, newest-LAST). Returns (segs_oldest_first,
    underflow). Segments partially inside the window count as their hash."""
    want = max(0, frames_after - frames_before)
    segs: list[str] = []
    remaining = want
    for pair in reversed(ring_rle):
        if remaining <= 0:
            break
        h, n = pair[0], int(pair[1])
        take = min(n, remaining)
        segs.append(h)
        remaining -= take
    underflow = remaining > 0  # ring/RLE cap lost window frames — cannot verify
    segs.reverse()
    return segs, underflow, want


def single_edit_analysis(before: dict, after: dict, *, expect: str) -> dict:
    """Frame-level single-edit oracle over two field dumps (dump schema v2).

    Dump fields consumed: frames (total painted ticks at dump time) and
    ring_rle (RLE of per-frame text hashes, newest-last, cap 64 pairs).
    Window = frames in (before.frames, after.frames]. Boundary hashes:
    h(before.text), h(after.text).

    Returns {frames, transitions, transient_hashes, painted_final, underflow,
    ok}:
      frames      window size (painted frames the field witnessed between dumps)
      transitions painted text-hash transitions attributable to the commit:
                  in-window segment boundaries PLUS the boundary the commit
                  causes at the window START (the before-dump usually IS the
                  last old-text paint — an on-demand clock paints nothing
                  between ops — so a first segment differing from hA counts
                  as the A→B transition; a clean commit counts exactly 1)
      transient   in-window hashes that are neither hA nor hB (delete/retype
                  frame painted an intermediate state — R.1 violation)
      painted_final  at least one in-window frame carries hB (visibility
                  witnessed — the field actually PAINTED the final text)
      underflow   True when the ring could not reconstruct the whole window
      ok          transient == [] and transitions == (0 for noop / 1 for change)
                  and (noop or painted_final) and not underflow

    Rate-agnostic (counts distinct hashes, not frames) and no-op tolerant: an
    empty window under expect="noop" is a PASS (an idle clock paints nothing
    between two dumps that saw no signal).
    """
    if expect not in ("noop", "change"):
        raise ValueError(f"expect must be 'noop' or 'change', got {expect!r}")
    ha = text_hash8(before.get("text", ""))
    hb = text_hash8(after.get("text", ""))
    fb = int(before.get("frames", 0))
    fa = int(after.get("frames", 0))
    segs, underflow, want = _window_segments(after.get("ring_rle") or [], fb, fa)
    internal = sum(1 for i in range(1, len(segs)) if segs[i] != segs[i - 1])
    boundary = 1 if (segs and segs[0] != ha) else 0  # the commit's A→B step
    transitions = internal + boundary
    transient = sorted({h for h in segs if h not in (ha, hb)})
    painted_final = hb in segs
    ok = (
        not underflow
        and not transient
        and transitions == (0 if expect == "noop" else 1)
        and (expect == "noop" or painted_final)
    )
    return {
        "frames": want,
        "transitions": transitions,
        "transient_hashes": transient,
        "painted_final": painted_final,
        "underflow": underflow,
        "ok": ok,
    }


# --- deterministic payloads (sizes are UTF-8 BYTE sizes) ----------------------

_SENTENCES = [
    "The team reviewed the draft and left notes on every paragraph before lunch.",
    "Our next milestone needs a working demo, a short script, and one backup plan.",
    "She counted the boxes twice, signed the sheet, and mailed it from the lobby.",
    "When the storm hit, the crew moved the scaffolding inside and waited it out.",
    "The recipe calls for slow heat, patient stirring, and a firm hand with salt.",
    "Every visitor gets a badge, a map, and a quiet room to leave their bags in.",
    "He read the meter, wrote the number down, and closed the panel without noise.",
    "The archive keeps older contracts on the lower shelves, boxed by fiscal year.",
    "A good summary names the actors, the stakes, and the next concrete step first.",
    "Rain fell all week, so the painters pushed the mural deadline to Thursday.",
    "The council voted to fund the bridge repair after two hours of testimony.",
    "Bring the blue folder to the meeting; the numbers inside back our request.",
    "Their factory runs three shifts, yet orders still outpace the current output.",
    "The kitten climbed the bookshelf, knocked down a ruler, and looked innocent.",
    "Please silence phones during the concert; ushers will seat latecomers at break.",
    "Wind carved long ridges into the dune field over the course of a single night.",
    "The pilot announced a short delay, then taxied to the gate for refueling.",
    "Students measured the pond weekly and logged algae growth in a shared sheet.",
    "The bakery donates day-old bread to the shelter on Denker Avenue each Friday.",
    "Snow packed the mountain pass, so the mail truck borrowed the valley route.",
]

_UNICODE_SEED = (
    "CJK: 中文测试文本，标点也算字节。"
    "Accents: héllo wörld — naïve café, à côté de chez toi. "
    "Combining: áéó (marks over plain ASCII). "
    "Emoji: 🌍 🚀 📝 🎛️ (astral planes, 4 bytes each). "
    "Greek/Hebrew/Cyrillic: αβγ Ω, שלום, Привет мир. "
    "Mixed digits: 1½ ¾ Ⅻ … ㊙ ㊗"
)


def _pad_to_bytes(s: str, target: int) -> str:
    """Pad with '.' to an exact UTF-8 byte size (ASCII pad = boundary safe)."""
    have = len(s.encode("utf-8"))
    if have > target:
        raise ValueError(f"seed already {have} B > target {target} B")
    return s + "." * (target - have)


def build_payloads() -> dict[str, object]:
    """Deterministic payloads for rows R1–R4. Sizes in UTF-8 bytes.

    short          6 cumulative growing spans (every op extends the owned span)
    twenty_*       20-sentence corpus (~1.2–2 KB, < the 4000 B commit cap);
                   corrected differs from committed in the FIRST word only
    unicode_951b   multilingual sample, byte-exact 951 B (paste-lab lineage)
    mixed_3500b    ASCII+Unicode mix, byte-exact 3500 B
    overcap_4500b  byte-exact 4500 B — deliberately crosses the 4000 B cap
    """
    committed = "Thier " + " ".join(_SENTENCES)  # first word deliberately wrong
    corrected = "Their " + " ".join(_SENTENCES)
    shorts = []
    acc = ""
    for piece in (
        "H",
        "ello wor",
        "ld, this is",
        " the voice",
        "-typing",
        " bulk lane.",
    ):
        acc += piece
        shorts.append(acc)
    unicode_951b = _pad_to_bytes(_UNICODE_SEED, 951)
    mixed_seed = (
        "Report №7 — Zusammenfassung: "
        "コストは 1,200 円（税込み）で、納期は来週の金曜日です。 "
        "Contact: naïve@example.com — café open 8–17. "
        "Symbols: ✓ ✗ § ¶ µ Ω ≈ ≠ → ✓ "
        "Emoji: 📦 🧪 ✅ "
        "Tail: "
    )
    mixed_3500b = _pad_to_bytes(mixed_seed, 3500)
    overcap_4500b = _pad_to_bytes("overcap-payload " + "a" * 64 + "\n", 4500)
    return {
        "short": shorts,
        "twenty_committed": committed,
        "twenty_corrected": corrected,
        "unicode_951b": unicode_951b,
        "mixed_3500b": mixed_3500b,
        "overcap_4500b": overcap_4500b,
    }


# --- bounded report renderer ---------------------------------------------------

MAX_REPORT_LINES = 150
_EVIDENCE_CAP_PER_ROW = 8


def render_report(versions: dict[str, str], rows: list[dict], meta: dict) -> str:
    """Render the bounded G3 row report (g2_gate_record.md style).

    versions: live environment numbers (kernel, sway, gtk, pygobject, pacman_*).
    rows:     [{id, title, status, passed, t_ms, evidence: [str, …]}] — evidence
              excerpts are capped per row and the WHOLE report is hard-capped at
              MAX_REPORT_LINES (a final '[… truncated …]' marker preserves the
              open-items section when the cap would cut it).
    meta:     {date, head, command, summary, open_items}.
    """
    lines: list[str] = []
    lines.append("# G3 GTK row report — real-field IM-v2 matrix (P1.M4.T5.S1)")
    lines.append("")
    lines.append(
        f"- Date: {meta.get('date', 'unknown')}  |  HEAD: {meta.get('head', 'unknown')}"
    )
    lines.append(f"- Command: `{meta.get('command', 'n/a')}`")
    for key in ("kernel", "sway", "gtk", "pygobject", "pacman_gtk4", "pacman_sway"):
        if versions.get(key):
            lines.append(f"- {key}: {versions[key]}")
    lines.append("")
    lines.append("> **A G2 pass never marks a row verified.** Only this harness's")
    lines.append("> field-side witnesses (frame oracle + dump + verify) verify a row,")
    lines.append("> and only with live versions attached. t_ms values are")
    lines.append("> mechanism-level info, NEVER G5 timing (no speech in this run).")
    lines.append("")
    lines.append("| row | pass | status |")
    lines.append("|---|---|---|")
    for r in rows:
        passed = r.get("passed")
        p = {True: "true", False: "FALSE", None: "null"}[passed]
        lines.append(f"| {r.get('id', '?')} | {p} | {r.get('status', 'untested')} |")
    lines.append("")
    for r in rows:
        lines.append(f"## {r.get('id', '?')} — {r.get('title', '')}")
        for ev in (r.get("evidence") or [])[:_EVIDENCE_CAP_PER_ROW]:
            lines.append(f"  {ev}")
        lines.append("")
    summary = meta.get("summary")
    if summary:
        lines.append(f"Summary: {summary}")
        lines.append("")
    open_items = meta.get("open_items") or []
    if open_items:
        lines.append("## Open items")
        for item in open_items:
            lines.append(f"- {item}")
        lines.append("")
    # Hard cap: keep the open-items tail; mark the cut honestly.
    if len(lines) > MAX_REPORT_LINES:
        head = lines[: MAX_REPORT_LINES - 4]
        tail = [ln for ln in lines[len(head) :] if ln.startswith(("- ", "# ", "## "))]
        keep = tail[-3:]
        lines = head + ["[… truncated …]"] + keep
    return "\n".join(lines[:MAX_REPORT_LINES])

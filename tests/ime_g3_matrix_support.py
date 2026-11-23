"""ime_g3_matrix_support — pure, venv-importable logic for the G3 FIELD-CLASS
matrix re-run at installed versions (P1.M4.T5.S2).

NO gi / wayland / pytest / voice_typing imports: this module is imported BOTH
by the collected unit tests (tests/test_ime_g3_matrix_support.py) and by the
live lab (tests/ime_g3_matrix_lab.py).

Contents:
  - TERM_PAYLOADS          the small proven probe set (ASCII-first + one
                           Unicode probe; byte-math sanity, no combining traps)
  - LEGAL_TERM_OUTCOMES    the closed branch sets per probe — the probe
                           invariants are THESE sets (an outcome outside them
                           is a harness bug, not a capability finding)
  - TermProbeOutcome       one terminal row's measured branches (validated)
  - term_row_status()      branches -> closed-vocabulary status string
                           (ROW_STATUSES words only, from S1's pure module)
  - HyprlandAttempt        one ladder attempt (variant env + boot + err head)
  - hypr_row_status()      attempt ladder -> closed-vocabulary status string
  - derive_route_table()   matrix -> per-field-class route -> THE P1.M5.T3
                           decision ("clipboard_fallback_m5t3": needed/skip)
  - render_matrix_report() the bounded matrix report (<= MAX_MATRIX_REPORT_LINES)

Lineage / evidence posture:
  - refreshes the 2026-11-22 im-lab measurement (tools/im-lab/README.md:41-84)
    at the installed set (foot 1.28.0 / kitty 0.51.0 / ghostty 1.4.0 /
    Hyprland 0.57.2 — plan/008_a47116bb2b79/P1M4T5S2/research/
    matrix-rerun-mechanics.md §1)
  - statuses use S1's closed vocabulary verbatim
    (tests/ime_g3_support.py ROW_STATUSES: untested | insert-only |
    blocked (reason) | verified (versions + evidence)); GTK-class rows are
    S1's (plan/008_a47116bb2b79/architecture/g3_gtk_rows.md) — referenced,
    never re-run
  - upstream expectations live in research/upstream-changelog-drift.md
    (ghostty 1.4.0 NOT-FIXED: PR #15246 is milestone 1.5.0; kitty 0.51
    delete_surrounding_text still a no-op; Hyprland 0.56.2→0.57.2 relay diffs
    = logging refactors only) — they set EXPECTATIONS for the report's
    discussion, never hard-coded outcomes: the harness MEASURES.
  - a G2/lab pass NEVER marks a row verified; insert-only rows never run as
    full dictation; terminal verification is APP-SIDE ONLY (term.json).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# S1's pure module is the stable seam: import, never edit (parallel landing).
from ime_g3_support import (  # noqa: F401  (re-exported seam)
    ROW_STATUSES,
    RowVerdict,
    build_payloads,
    single_edit_analysis,
)

__all__ = [
    "ROW_STATUSES",
    "RowVerdict",
    "build_payloads",
    "single_edit_analysis",
    "TERM_PAYLOADS",
    "LEGAL_TERM_OUTCOMES",
    "MAX_MATRIX_REPORT_LINES",
    "TermProbeOutcome",
    "term_row_status",
    "HyprlandAttempt",
    "hypr_row_status",
    "derive_route_table",
    "render_matrix_report",
    "pacman_versions",
    "first_version_line",
    "outcome_from_verdict",
    "attempts_from_verdict",
]

# --- probe payloads (im-lab proven; byte math pinned) -------------------------
TERM_PAYLOADS = {
    "insert_ascii": "hello from im",  # the im-lab string — keeps rows comparable
    "insert_unicode": "Zoë — naïve 日本語 🫡",  # byte-math sanity, no combining traps
    "correct_delete": " im",  # len(" im".encode()) == 3 — BEFORE is BYTES
    "correct_replacement": "v2",
}
ASCII_INSERT_LINE = TERM_PAYLOADS["insert_ascii"]
UNICODE_INSERT_LINE = ASCII_INSERT_LINE + TERM_PAYLOADS["insert_unicode"]
CORRECT_APPLIED_LINE = "hello fromv2"  # delete_surrounding_text honored
CORRECT_IGNORED_LINE = "hello from imv2"  # delete_surrounding_text silently ignored

assert len(TERM_PAYLOADS["correct_delete"].encode("utf-8")) == 3  # byte math (GOTCHA)


# --- closed legal-branch sets (the probe invariants) --------------------------
LEGAL_TERM_OUTCOMES = {
    "insert": {"delivered", "not_delivered"},
    "correct": {"delete_applied", "delete_ignored"},
    "activate": {"activated", "not_activated"},
    "surround": {"sent", "never_sent"},
}

TERMINALS = ("foot", "kitty", "ghostty")
PREEDIT_NOTE = (
    "not exercised — the product host transport serves acquire/show/cancel/"
    "grab/verify/leave/ping only; it has no preedit command (the im-lab "
    "im_probe ctl preedit/endpreedit diagnostic has no IM-v2 host equivalent)"
)


@dataclass(frozen=True)
class TermProbeOutcome:
    """One terminal row's measured branches (all from the closed legal sets).

    None-rules pin the skip-deps: a correct probe is NEVER sent to a terminal
    whose insert probe measured not_delivered, and the Unicode roundtrip is
    only meaningful when the ASCII insert delivered. `correct` is REQUIRED
    (non-None, legal) whenever the insert delivered — a missing branch there
    is a harness bug, not a capability gap.
    """

    terminal: str  # "foot" | "kitty" | "ghostty"
    version: str  # live-captured, e.g. "kitty 0.51.0"
    activate: str  # LEGAL_TERM_OUTCOMES["activate"]
    insert: str  # LEGAL_TERM_OUTCOMES["insert"]
    correct: str | None = None
    insert_unicode_roundtrip: bool | None = None
    surround: str = "never_sent"  # from host acquire reason / event log
    t_ms: dict | None = None  # mechanism-level ONLY — never claimed as G5
    reasons: dict = field(default_factory=dict)  # host reply reason strings
    evidence: tuple[str, ...] = ()  # capped excerpt strings for the report

    def __post_init__(self):
        if self.terminal not in TERMINALS:
            raise ValueError(
                f"terminal must be one of {TERMINALS}, got {self.terminal!r}"
            )
        for key, value in (
            ("activate", self.activate),
            ("insert", self.insert),
            ("surround", self.surround),
        ):
            if value not in LEGAL_TERM_OUTCOMES[key]:
                raise ValueError(f"{key}={self.__dict__.get(key)!r} outside legal set")
        if self.activate == "not_activated":
            if self.insert != "not_delivered":
                raise ValueError("a not-activated terminal cannot deliver an insert")
            if self.correct is not None or self.insert_unicode_roundtrip is not None:
                raise ValueError(
                    "skip-deps: no correct/unicode probes past no-activation"
                )
        if self.insert == "not_delivered":
            if self.correct is not None or self.insert_unicode_roundtrip is not None:
                raise ValueError(
                    "skip-deps: correct/unicode probes must not run after a not-delivered insert"
                )
        else:  # insert delivered (implies activated)
            if self.correct not in LEGAL_TERM_OUTCOMES["correct"]:
                raise ValueError(
                    "insert delivered => the correct branch is REQUIRED evidence"
                )
            if not isinstance(self.insert_unicode_roundtrip, bool):
                raise ValueError(
                    "insert delivered => unicode roundtrip is REQUIRED evidence"
                )


def term_row_status(o: TermProbeOutcome) -> str:
    """Closed-vocabulary status for one terminal row. NEVER invents words.

    - not_activated | insert not_delivered -> "blocked (<branch> at <version>
      — IM route unavailable for this class; evidence: <terminal> row)"
    - delivered + delete_applied + surround sent -> "verified (<version> +
      evidence)" (the day a terminal ships full support)
    - delivered + (delete_ignored or surround never_sent) -> "insert-only
      (<version> + evidence)"  — THE expected foot/kitty shape
    """
    ev = f"{o.terminal} row, verdicts.jsonl"
    if o.activate == "not_activated":
        return (
            f"blocked (activate not_activated at {o.version} — IM route "
            f"unavailable for this class; evidence: {ev})"
        )
    if o.insert == "not_delivered":
        return (
            f"blocked (insert not_delivered at {o.version} — IM route "
            f"unavailable for this class; evidence: {ev})"
        )
    if o.correct == "delete_applied" and o.surround == "sent":
        return f"verified ({o.version} + evidence: {ev})"
    return f"insert-only ({o.version} + evidence: {ev})"


# --- Hyprland attempt ladder ---------------------------------------------------
# Variants (research/matrix-rerun-mechanics.md §4 + upstream-changelog-drift.md
# "Hyprland 0.57.x"): aquamarine backends are DRM | HEADLESS | WAYLAND only —
# there is NO x11 backend, and WLR_BACKENDS/WLR_RENDERER are wlroots variables
# aquamarine never reads. The ladder is DATA so the report can show the exact
# env deltas; "@" keys are placeholders the lab substitutes (sway socket).
HYPR_LADDER = (
    {
        "variant": "nested-wayland",
        # Drop the inherited x11/wlroots values AND DISPLAY (research §4: the
        # recorded failure shape is aquamarine CBackend::create() + Hyprland's
        # "NOT an X11 one" guard — DISPLAY leaking from xvfb-run is part of
        # that posture). WAYLAND_DISPLAY=sway makes the WAYLAND backend the
        # fallback aquamarine actually boots.
        "unset": ("WLR_BACKENDS", "WLR_LIBINPUT_NO_DEVICES", "DISPLAY", "WLR_RENDERER"),
        "set": {
            "WAYLAND_DISPLAY": "@SWAY_SOCK@",
            "XDG_CURRENT_DESKTOP": "Hyprland",
            "WLR_RENDERER": "pixman",  # dead in aquamarine; pinned for posture parity
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_SHADER_CACHE_DISABLE": "true",
        },
    },
    {
        "variant": "aq-headless",
        # Upstream virtual-gpu recipe: AQ_NO_KMS_REQUIREMENT=1 -> HEADLESS-0;
        # AQ_DRM_DEVICES pinned empty = no DRM attempt at all. No
        # WAYLAND_DISPLAY (the wayland fallback must not be available).
        "unset": (
            "WLR_BACKENDS",
            "WLR_LIBINPUT_NO_DEVICES",
            "DISPLAY",
            "WLR_RENDERER",
            "WAYLAND_DISPLAY",
        ),
        "set": {
            "XDG_CURRENT_DESKTOP": "Hyprland",
            "AQ_NO_KMS_REQUIREMENT": "1",
            "AQ_DRM_DEVICES": "",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_SHADER_CACHE_DISABLE": "true",
        },
    },
    {
        "variant": "legacy-x11",
        # The 2026-11-22 hypr_nest.py posture VERBATIM (full inherited env incl.
        # WLR_BACKENDS=x11 + nested WAYLAND_DISPLAY) — re-confirm the recorded
        # failure shape with the error head, for the report's provenance.
        "unset": (),
        "set": {
            "WAYLAND_DISPLAY": "@SWAY_SOCK@",
            "XDG_CURRENT_DESKTOP": "Hyprland",
        },
    },
)


@dataclass(frozen=True)
class HyprlandAttempt:
    """One ladder attempt: the exact env (serializable), boot outcome, and —
    when booted — the measured field-row branches (or None when the boot
    could not host field rows, e.g. headless with no visible output)."""

    variant: str  # "nested-wayland" | "aq-headless" | "legacy-x11"
    env: dict = field(default_factory=dict)  # sorted rendering for the report
    booted: bool = False
    err_head: str = ""  # <=400 B of hypr.err when not booted
    rows_measured: dict | None = None  # activate/insert/correct/surround/preedit


def hypr_row_status(attempts: list[HyprlandAttempt]) -> str:
    """Closed-vocabulary status for the whole ladder. NEVER invents words."""
    if not attempts:
        return "untested (infra: no Hyprland attempts recorded)"
    booted = [a for a in attempts if a.booted]
    if not booted:
        first = attempts[0]
        head = " ".join(first.err_head.split())[:160] or "no error captured"
        tried = ",".join(a.variant for a in attempts)
        return f"blocked (nested Hyprland: {head} @ {tried})"
    a = booted[0]
    rows = a.rows_measured
    if rows is None:
        return (
            f"blocked (booted {a.variant} but field rows not measurable: "
            "no visible output for field rows — boot + registry proven)"
        )
    insert = rows.get("insert", "not_delivered")
    if insert == "delivered":
        if rows.get("correct") == "delete_applied" and rows.get("surround") == "sent":
            return (
                f"verified (isolated Hyprland {a.variant} relay + evidence: hypr row)"
            )
        return f"insert-only (isolated Hyprland {a.variant} relay + evidence: hypr row)"
    return f"blocked (insert not_delivered through the {a.variant} relay; evidence: hypr row)"


# --- THE route table (P1.M5.T3's go/no-go input) -------------------------------


def derive_route_table(
    term_rows: list[TermProbeOutcome], hypr: str, gtk_rows_ref: str
) -> dict:
    """Matrix -> per-field-class route -> the M5.T3 clipboard-fallback decision.

    Pure and unit-tested — the report carries this VERBATIM; P1.M5.T3's PRP
    greps the "clipboard_fallback_m5t3" key. R.4 discipline: this refreshes
    route COVERAGE at real versions; it never re-picks the route (IM-v2 stays
    primary — "clipboard insert-fallback (R.6)" entries are the per-class
    delivery seam BEHIND the primary route, exactly what M5.T3 implements).
    """
    field_classes: dict[str, dict] = {
        "gtk": {"route": "im-v2 full", "evidence": gtk_rows_ref},
    }
    ghostty: TermProbeOutcome | None = None
    for o in term_rows:
        if o.insert == "delivered":
            if o.correct == "delete_applied" and o.surround == "sent":
                route = "im-v2 full"
            else:
                route = "im-v2 insert-only"
        else:
            route = "clipboard insert-fallback (R.6)"
        entry: dict = {"route": route, "evidence": f"{o.terminal} row at {o.version}"}
        if route == "im-v2 insert-only":
            entry["corrections"] = "cooperating-editor seam (M5.T1)"
        field_classes[o.terminal] = entry
        if o.terminal == "ghostty":
            ghostty = o
    if ghostty is not None and ghostty.insert == "delivered":
        decision = (
            f"skip (ghostty insert works over IM at {ghostty.version}; "
            "evidence: ghostty row in this matrix)"
        )
    elif ghostty is not None:
        decision = f"needed (ghostty-class insert blocked at {ghostty.version})"
    else:
        decision = "needed (no ghostty row measured — fall back conservatively)"
    return {
        "field_classes": field_classes,
        "clipboard_fallback_m5t3": decision,
        "hyprland_relay": hypr,
    }


# --- verdict (de)serialization (the lab writes these; the report reads them) ---


def outcome_from_verdict(v: dict) -> TermProbeOutcome:
    """Rebuild a TermProbeOutcome from the lab's per-row verdict dict
    (keys: terminal, version, branches{activate,insert,correct,surround,
    unicode}, reasons, evidence). Doubles as the lab's own invariant check:
    constructing the object VALIDATES every branch against the legal sets."""
    b = v.get("branches", {})
    return TermProbeOutcome(
        terminal=v["terminal"],
        version=v.get("version", "unknown"),
        activate=b["activate"],
        insert=b["insert"],
        correct=b.get("correct"),
        insert_unicode_roundtrip=b.get("unicode"),
        surround=b.get("surround", "never_sent"),
        t_ms=v.get("t_ms"),
        reasons=v.get("reasons", {}),
        evidence=tuple(v.get("evidence", ())),
    )


def attempts_from_verdict(v: dict) -> list[HyprlandAttempt]:
    """Rebuild the ladder from the hypr verdict dict (key: attempts — env
    dicts are dropped for the report rebuild; the live lab's verdicts.jsonl
    keeps full envs)."""
    out = []
    for a in v.get("attempts", []):
        out.append(
            HyprlandAttempt(
                variant=a["variant"],
                env=a.get("env", {}),
                booted=bool(a.get("booted")),
                err_head=a.get("err_head", ""),
                rows_measured=a.get("rows_measured"),
            )
        )
    return out


# --- bounded matrix report renderer ---------------------------------------------
MAX_MATRIX_REPORT_LINES = 150
_EVIDENCE_CAP_PER_ROW = 4


def _fmt_route_table(rt: dict) -> list[str]:
    lines = ["```json"]
    lines.append(json.dumps(rt, ensure_ascii=False, indent=1, sort_keys=True))
    lines.append("```")
    return lines


def render_matrix_report(
    versions: dict[str, str],
    term_rows: list[TermProbeOutcome],
    hypr_attempts: list[HyprlandAttempt],
    route_table: dict,
    meta: dict,
) -> str:
    """Render the bounded matrix report (g2_gate_record.md / D1_DUCK_EVIDENCE
    style). Hard cap MAX_MATRIX_REPORT_LINES; the open-items tail survives a
    truncation with an honest '[… truncated …]' marker."""
    lines: list[str] = []
    lines.append("# G3 field-class matrix — re-run at installed versions (P1.M4.T5.S2)")
    lines.append("")
    lines.append(
        f"- Date: {meta.get('date', 'unknown')}  |  HEAD: {meta.get('head', 'unknown')}"
    )
    lines.append(f"- Command: `{meta.get('command', 'n/a')}`")
    for key in ("kernel", "sway", "foot", "kitty", "ghostty", "hyprland", "gtk4"):
        if versions.get(key):
            lines.append(f"- {key}: {versions[key]}")
    for key in ("pacman",):
        if versions.get(key):
            lines.append(f"- pacman -Q (verbatim): {versions[key]}")
    lines.append("")
    lines.append("> **A G2/lab pass never marks a row verified.** Only this harness's")
    lines.append("> app-side witnesses (term.json / field dump + host reason strings)")
    lines.append("> record a row, and only with live versions attached. t_ms values")
    lines.append("> are mechanism-level info, NEVER G5 timing (no speech in this run).")
    lines.append("")
    lines.append("| field class | measured version | status |")
    lines.append("|---|---|---|")
    lines.append(
        f"| gtk (S1) | (S1's run, see {meta.get('gtk_rows_ref', 'g3_gtk_rows.md')}) | im-v2 full — cited, NOT re-run |"
    )
    for o in term_rows:
        lines.append(f"| {o.terminal} | {o.version} | {term_row_status(o)} |")
    lines.append(
        f"| Hyprland relay | {versions.get('hyprland', 'unknown')} | {route_table.get('hyprland_relay', 'untested')} |"
    )
    lines.append("")
    lines.append("## Hyprland isolated-boot ladder")
    for a in hypr_attempts:
        env_keys = (
            ", ".join(f"{k}={a.env[k]}" for k in sorted(a.env) if a.env[k] != "")
            or "(inherited verbatim)"
        )
        line = f"- {a.variant}: {'BOOTED' if a.booted else 'failed'}; env {env_keys}"
        lines.append(
            line
            if a.booted
            else f"{line}; err head: {' '.join(a.err_head.split())[:160]}"
        )
    lines.append("")
    lines.append("## Route table (derives the P1.M5.T3 decision — unit-tested)")
    lines.append(
        f"clipboard_fallback_m5t3: {route_table.get('clipboard_fallback_m5t3', 'unspecified')}"
    )
    lines.extend(_fmt_route_table(route_table))
    lines.append("")
    lines.append("## Evidence excerpts (capped)")
    for o in term_rows:
        lines.append(f"### {o.terminal}")
        if o.t_ms:
            lines.append(f"  t_ms (mechanism): {json.dumps(o.t_ms, sort_keys=True)}")
        if o.reasons:
            lines.append(
                f"  host reasons: {json.dumps(o.reasons, sort_keys=True, ensure_ascii=False)}"
            )
        for ev in o.evidence[:_EVIDENCE_CAP_PER_ROW]:
            lines.append(f"  {ev}")
    booted = [a for a in hypr_attempts if a.booted]
    for a in booted:
        if a.rows_measured:
            lines.append(f"### Hyprland {a.variant}")
            lines.append(
                f"  rows: {json.dumps(a.rows_measured, sort_keys=True, ensure_ascii=False)}"
            )
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
    if len(lines) > MAX_MATRIX_REPORT_LINES:
        head = lines[: MAX_MATRIX_REPORT_LINES - 4]
        tail = [
            ln
            for ln in lines[len(head) :]
            if ln.startswith(("- ", "#", "clipboard_fallback_m5t3"))
        ]
        keep = tail[-3:]
        lines = head + ["[… truncated …]"] + keep
    return "\n".join(lines[:MAX_MATRIX_REPORT_LINES])


# --- version-string helpers (pure; the lab feeds them raw process output) ------


def pacman_versions(out: str) -> dict[str, str]:
    """Parse `pacman -Q <pkgs…>` stdout: 'name version …' lines -> {name: ver}."""
    versions: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            versions[parts[0]] = parts[1]
    return versions


def first_version_line(raw: str) -> str:
    """First non-empty line of a `--version` banner, whitespace-collapsed."""
    for line in raw.splitlines():
        if line.strip():
            return " ".join(line.split())
    return ""

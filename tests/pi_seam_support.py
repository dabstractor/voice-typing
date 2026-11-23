"""Pure support helpers for the pi-editor-seam proof (P1.M5.T1.S1).

stdlib only — no pi / tmux / socket imports, collectable on any machine.

Roles:
  * OpRequest / OpReply — frozen data model for the pi-editor.sock JSONL protocol v1.
  * classify_reply()    — validate a raw reply dict against the closed reply vocabulary
                          (mirrors voice_typing.bulk_delivery.ShowResult: applied |
                          unchanged | refused; `unknown` stays reserved for the S2
                          deadline layer — socket ops are synchronous, never unknown here).
  * classify_event()    — validate an unrequested event line (takeover).
  * expected_matrix()   — the proof oracle: request kind -> legal reply result set.
  * build_probe_payloads() — the exact probe strings the lab sends (ASCII, unicode,
                          replace / zero-diff / refuse cases).
  * render_proof_table() — bounded (< =120 lines) rendering of lab results for the
                          evidence record.

UNITS: all offsets/lengths in this protocol are UTF-16 code units ("units":"utf-16").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Result vocabulary — mirrors bulk_delivery.ShowResult minus `unknown`
#: (socket ops are synchronous on pi's loop; unknown is S2's deadline-layer verdict).
RESULT_VOCAB: frozenset[str] = frozenset({"applied", "unchanged", "refused"})

#: Refusal reasons for {"ok":true,"result":"refused",...}.
REFUSE_REASONS: frozenset[str] = frozenset(
    {"range not owned", "dirty", "out_of_bounds"}
)

#: Error-reply categories ({"ok":false,"error":...}); the classifier maps an error
#: string prefix to exactly one of these.
ERROR_VOCAB: frozenset[str] = frozenset(
    {"malformed_json", "not_object", "unknown_op", "bad_args", "not_ready", "other"}
)

#: Event vocabulary (unrequested server->client lines).
EVENT_VOCAB: frozenset[str] = frozenset({"takeover"})
EVENT_SOURCES: frozenset[str] = frozenset({"key"})

#: Units marker every read reply must carry.
UNITS = "utf-16"

#: Request kinds the oracle knows (matrix rows).
REQUEST_KINDS: frozenset[str] = frozenset(
    {"insert", "replace", "cancel", "read", "malformed", "not_object", "unknown_op"}
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpRequest:
    """One JSONL op line client->server. Unused fields stay None."""

    op: str
    text: str | None = None
    start: int | None = None
    end: int | None = None

    def encode(self) -> str:
        """Exact JSON line (compact, insertion-ordered) sent over the socket."""
        obj: dict[str, Any] = {"op": self.op}
        if self.text is not None:
            obj["text"] = self.text
        if self.start is not None:
            obj["start"] = self.start
        if self.end is not None:
            obj["end"] = self.end
        return json_dumps(obj)

    @property
    def kind(self) -> str:
        """Matrix-row kind: known op name, or the error-probe kind."""
        return (
            self.op if self.op in {"insert", "replace", "cancel", "read"} else self.op
        )


@dataclass(frozen=True)
class OpReply:
    """A classified reply line. `error_kind` is set iff ok is False."""

    ok: bool
    result: str | None = None  # RESULT_VOCAB member when ok, else "error"
    error_kind: str | None = None  # ERROR_VOCAB member when not ok
    error: str | None = None
    reason: str | None = None  # REFUSE_REASONS member when result == "refused"
    text: str | None = None  # read replies
    cursor: dict[str, int] | None = None  # {"line": int, "col": int}
    owned: tuple[int, int] | None = None  # inclusive-exclusive, UTF-16 units
    dirty: bool | None = None
    units: str | None = None
    changes: int | None = None


@dataclass(frozen=True)
class OpEvent:
    """A classified unrequested event line."""

    event: str
    source: str


# ---------------------------------------------------------------------------
# Classification (validating)
# ---------------------------------------------------------------------------


def _check_cursor(cursor: Any) -> dict[str, int]:
    if not isinstance(cursor, dict):
        raise ValueError(f"cursor must be an object, got {cursor!r}")
    line, col = cursor.get("line"), cursor.get("col")
    if not isinstance(line, int) or isinstance(line, bool) or line < 0:
        raise ValueError(f"cursor.line must be a non-negative int, got {line!r}")
    if not isinstance(col, int) or isinstance(col, bool) or col < 0:
        raise ValueError(f"cursor.col must be a non-negative int, got {col!r}")
    return {"line": line, "col": col}


def _classify_error(error: Any) -> str:
    if not isinstance(error, str) or not error:
        raise ValueError(f"error reply must carry a non-empty string, got {error!r}")
    if error.startswith("malformed JSON:"):
        return "malformed_json"
    if error == "request must be a JSON object":
        return "not_object"
    if error.startswith("unknown op:"):
        return "unknown_op"
    if error == "editor not ready":
        return "not_ready"
    if ": " in error and error.split(": ", 1)[0] in {
        "insert",
        "replace",
        "cancel",
        "read",
    }:
        return "bad_args"
    return "other"


def classify_reply(raw: dict[str, Any]) -> OpReply:
    """Validate one reply dict against the protocol vocabulary; raise ValueError on violation."""
    if not isinstance(raw, dict):
        raise ValueError(f"reply must be a JSON object, got {type(raw).__name__}")
    ok = raw.get("ok")
    if not isinstance(ok, bool):
        raise ValueError(f"'ok' must be a bool, got {ok!r}")
    if not ok:
        error = raw.get("error")
        return OpReply(
            ok=False, result="error", error_kind=_classify_error(error), error=error
        )
    result = raw.get("result")
    if result not in RESULT_VOCAB:
        raise ValueError(
            f"result {result!r} not in closed vocabulary {sorted(RESULT_VOCAB)}"
        )
    kwargs: dict[str, Any] = {"ok": True, "result": result}
    if result == "refused":
        reason = raw.get("reason")
        if reason not in REFUSE_REASONS:
            raise ValueError(
                f"refused reason {reason!r} not in {sorted(REFUSE_REASONS)}"
            )
        kwargs["reason"] = reason
        if (
            "cursor" in raw
        ):  # refused replies still carry cursor/changes instrumentation
            kwargs["cursor"] = _check_cursor(raw["cursor"])
        if "changes" in raw:
            changes = raw["changes"]
            if not isinstance(changes, int) or isinstance(changes, bool) or changes < 0:
                raise ValueError(f"changes must be a non-negative int, got {changes!r}")
            kwargs["changes"] = changes
        return OpReply(**kwargs)
    if "cursor" in raw:
        kwargs["cursor"] = _check_cursor(raw["cursor"])
    if "changes" in raw:
        changes = raw["changes"]
        if not isinstance(changes, int) or isinstance(changes, bool) or changes < 0:
            raise ValueError(f"changes must be a non-negative int, got {changes!r}")
        kwargs["changes"] = changes
    if "text" in raw:  # read replies carry the full state
        kwargs["text"] = raw["text"]
        kwargs["units"] = raw.get("units")
        if kwargs["units"] != UNITS:
            raise ValueError(
                f"read reply units must be {UNITS!r}, got {kwargs['units']!r}"
            )
        kwargs["dirty"] = raw.get("dirty")
        if not isinstance(kwargs["dirty"], bool):
            raise ValueError(f"dirty must be a bool, got {kwargs['dirty']!r}")
        owned = raw.get("owned")
        if owned is not None:
            if (
                not isinstance(owned, dict)
                or not isinstance(owned.get("start"), int)
                or not isinstance(owned.get("end"), int)
                or owned["start"] < 0
                or owned["end"] < owned["start"]
            ):
                raise ValueError(
                    f"owned must be null or {{start,end}} ints, got {owned!r}"
                )
            kwargs["owned"] = (owned["start"], owned["end"])
    return OpReply(**kwargs)


def classify_event(raw: dict[str, Any]) -> OpEvent:
    """Validate one unrequested event dict; raise ValueError on violation."""
    if not isinstance(raw, dict):
        raise ValueError(f"event must be a JSON object, got {type(raw).__name__}")
    event = raw.get("event")
    if event not in EVENT_VOCAB:
        raise ValueError(f"event {event!r} not in {sorted(EVENT_VOCAB)}")
    source = raw.get("source")
    if source not in EVENT_SOURCES:
        raise ValueError(f"event source {source!r} not in {sorted(EVENT_SOURCES)}")
    return OpEvent(event=event, source=source)


def is_event(raw: dict[str, Any]) -> bool:
    """Cheap discriminator BEFORE classification: events have no 'ok'/'op' keys."""
    return isinstance(raw, dict) and "event" in raw


# ---------------------------------------------------------------------------
# Proof oracle
# ---------------------------------------------------------------------------

#: op -> frozenset of legal reply `result` values (error replies count as "error";
#: the lab asserts actual result ∈ legal set for every matrix row).
EXPECTED_MATRIX: dict[str, frozenset[str]] = {
    "insert": frozenset({"applied"}),
    "replace": frozenset({"applied", "unchanged", "refused"}),
    "cancel": frozenset({"applied", "unchanged"}),
    "read": frozenset({"applied"}),
    "malformed": frozenset({"error"}),
    "not_object": frozenset({"error"}),
    "unknown_op": frozenset({"error"}),
}


def expected_matrix() -> dict[str, frozenset[str]]:
    """Fresh copy of the oracle (callers may shrink per-phase, never grow it)."""
    return {k: frozenset(v) for k, v in EXPECTED_MATRIX.items()}


# ---------------------------------------------------------------------------
# Probe payloads (the exact strings the lab sends)
# ---------------------------------------------------------------------------

ASCII_PROBE = "hello from pi seam"
UNICODE_PROBE = "Zoë — naïve 日本語 🫡"
#: replace old->new applied to the ASCII probe tail (owned range after inserts).
REPLACE_OLD = "pi seam"
REPLACE_NEW = "edge seam"


@dataclass(frozen=True)
class ProbePlan:
    """The full op matrix, in lab order (one row = one socket request)."""

    rows: list[tuple[str, OpRequest]] = field(default_factory=list)


def build_probe_payloads(buffer_prefix: str = "") -> dict[str, Any]:
    """Probe strings, parameterised by the buffer already present before the inserts.

    Keys: ascii, unicode, replace_old, replace_new, replace_start/end (UTF-16 offsets
    into the post-insert buffer tail), zero_diff (same range, identical text),
    oob_start/oob_end (a range outside the owned fragment).
    """
    tail_start = len(buffer_prefix)
    return {
        "ascii": ASCII_PROBE,
        "unicode": UNICODE_PROBE,
        "replace_old": REPLACE_OLD,
        "replace_new": REPLACE_NEW,
        "replace_start": tail_start + len(ASCII_PROBE) - len(REPLACE_OLD),
        "replace_end": tail_start + len(ASCII_PROBE),
        # zero-diff targets the span AS THE REPLACE LEFT IT ([replace_start,
        # replace_start+len(new))) with identical text -> the reply must be
        # "unchanged" with changes == 0.
        "zero_diff_start": tail_start + len(ASCII_PROBE) - len(REPLACE_OLD),
        "zero_diff_end": tail_start
        + len(ASCII_PROBE)
        - len(REPLACE_OLD)
        + len(REPLACE_NEW),
        "zero_diff_text": REPLACE_NEW,
        "oob_start": 0,
        "oob_end": tail_start
        + len(ASCII_PROBE)
        + len(REPLACE_NEW)
        - len(REPLACE_OLD)
        + 10,
        "owned_after_cancel_probe": "again",  # re-establishes ownership before takeover
    }


def build_probe_plan(buffer_prefix: str = "") -> ProbePlan:
    """The full 8-step matrix as concrete requests (lab order; see pi_seam_lab.py)."""
    p = build_probe_payloads(buffer_prefix)
    rows = [
        ("1 insert ascii", OpRequest("insert", text=p["ascii"])),
        ("2 insert unicode", OpRequest("insert", text=p["unicode"])),
        (
            "3 replace owned",
            OpRequest(
                "replace",
                text=p["replace_new"],
                start=p["replace_start"],
                end=p["replace_end"],
            ),
        ),
        (
            "4 replace zero-diff",
            OpRequest(
                "replace",
                text=p["zero_diff_text"],
                start=p["zero_diff_start"],
                end=p["zero_diff_end"],
            ),
        ),
        (
            "5 replace outside owned",
            OpRequest(
                "replace", text=p["replace_new"], start=p["oob_start"], end=p["oob_end"]
            ),
        ),
        ("6 cancel owned", OpRequest("cancel")),
        ("7a insert (re-own)", OpRequest("insert", text=p["owned_after_cancel_probe"])),
        ("8 read final", OpRequest("read")),
    ]
    return ProbePlan(rows=rows)


# ---------------------------------------------------------------------------
# Bounded rendering for the evidence record
# ---------------------------------------------------------------------------


def render_proof_table(results: list[dict[str, Any]], max_lines: int = 120) -> str:
    """Render lab results as a markdown table, hard-capped at max_lines lines."""
    header = "| step | request | reply | detail |"
    sep = "|---|---|---|---|"
    body = []
    for r in results:
        body.append(
            "| {} | {} | {} | {} |".format(
                r.get("step", "?"),
                str(r.get("request", "?")).replace("|", "\\|"),
                str(r.get("result", "?")).replace("|", "\\|"),
                str(r.get("detail", "")).replace("|", "\\|").replace("\n", " "),
            )
        )
    lines = [header, sep, *body]
    if len(lines) > max_lines:
        kept = max_lines - 4
        lines = [
            header,
            sep,
            *body[:kept],
            f"| … | … | … | ({len(body) - kept} rows elided) |",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# tiny local json helper (keeps the module import-free of anything but stdlib)
# ---------------------------------------------------------------------------


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

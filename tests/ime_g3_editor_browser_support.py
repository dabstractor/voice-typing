"""ime_g3_editor_browser_support — pure helpers for the G3 graphical-editor +
browser-text-field rows (P1.M5.T2.S2).

NO gi / wayland / pytest / voice_typing imports (mirrors tests/ime_g3_support.py):
this module is imported BOTH by the collected unit tests
(tests/test_ime_g3_editor_browser_support.py, venv python) and by the live lab
(tests/ime_g3_editor_browser_lab.py).

Contents:
  - fnv1a32(text)          the browser-witness hash space (sha1 is the GTK
                           oracle's space). MUST stay in lockstep with the
                           fixture's JS twin (tests/fixtures/
                           ime_g3_browser_field.html): TextEncoder (UTF-8
                           bytes) + 32-bit FNV-1a, hex 8.
  - utf16_len(text)        DOM length semantics (bulk_delivery.TargetUnits.
                           UTF16_UNITS / _utf16_len lineage): astral chars
                           count 2.
  - BrowserState           one pushed/reported page state (the page's OWN
                           truth; never a pixel scrape).
  - parse_push(raw)        validated parse of one /push body.
  - parse_title(raw)       parse of the document.title FALLBACK channel
                           ("vtg3-browser[-ro]|{counts+hashes only}").
  - input_event_law(...)   the R.1 event-count law in DOM terms:
                           insert=1 input event, correction=1 input event
                           whose newest ring entry covers the FULL before→after
                           delta, zero-diff=0 events; no intermediate rAF
                           value-hash between the two states.
  - chromium_argv(...)     the isolated-Chromium argv builder (IM-v2 flags +
                           temp-root profile + no keyring D-Bus).
  - firefox_argv(...)      the bounded ONE-shot contingency argv (MOZ_ENABLE_
                           WAYLAND=1 is set by the lab's env, not argv).
  - class_verdict(rows)    the closed-vocabulary CLASS verdict mapper
                           (R.7: untested | insert-only | blocked (reason) |
                           verified (versions + evidence)).
  - render_class_report    bounded report renderer wrapping
                           ime_g3_support.render_report (≤ MAX_REPORT_LINES)
                           with the extra live-version keys (chromium, flags).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from ime_g3_support import MAX_REPORT_LINES, VERIFIED_SUFFIX, render_report  # noqa: E402

# --- the browser-witness hash space (fixture JS twin) -------------------------


def fnv1a32(text: str) -> str:
    """32-bit FNV-1a over the UTF-8 bytes, hex 8 — the page's own hash.

    The fixture computes exactly this in JS (TextEncoder().encode() gives the
    identical UTF-8 byte string; Math.imul keeps the multiply in 32 bits), so
    ring/frames hashes recorded BY THE PAGE compare equal to hashes computed
    HERE from the expected strings. NOT cryptographic: it only fingerprints
    which value-states the page witnessed (the ring is the delta evidence).
    """
    h = 2166136261
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"


def utf16_len(text: str) -> int:
    """DOM string length (UTF-16 code units): astral chars count 2.

    Lineage: voice_typing/bulk_delivery.py TargetUnits.UTF16_UNITS /
    _utf16_len (kept local to keep this module voice_typing-free — the same
    units rule, not a fork of the offset algebra; the LAB computes expected
    cursor offsets via bulk_delivery.map_span, never here)."""
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)


# --- the pushed page state ------------------------------------------------------


@dataclass(frozen=True)
class BrowserState:
    """One /push body: the DOM field's own state, witnessed by its OWN JS.

    n        cumulative `input` event count (monotonic; the event-count law's
             counter)
    k        cumulative keydown count (must stay 0 — grabbed keys never reach
             the page; delivery commits generate zero key events)
    sel_start/sel_end   DOM selection anchors (UTF-16 units)
    length   field.value.length (UTF-16 units)
    text     field.value (the field's own truth, byte-exact)
    ring     last ≤32 input events, each (fnv(before), fnv(after),
             len16(before), len16(after)) — the one-edit delta evidence
    frames   last ≤64 rAF value-hashes (the transient-frame oracle's raw feed)
    f        cumulative painted-frame count (rAF ticks)
    readonly True when the page booted ?mode=ro (<input readonly>)
    """

    n: int
    k: int
    sel_start: int
    sel_end: int
    length: int
    text: str
    ring: tuple[tuple[str, str, int, int], ...]
    frames: tuple[str, ...]
    f: int
    readonly: bool = False


def _validate_state(obj: dict) -> None:
    """Raise ValueError unless the payload is a well-formed page state."""
    for key in ("n", "k", "sel", "len", "text", "ring", "frames", "f"):
        if key not in obj:
            raise ValueError(f"push missing key {key!r}")
    for key in ("n", "k", "f", "len"):
        if not isinstance(obj[key], int) or isinstance(obj[key], bool):
            raise ValueError(f"push field {key!r} must be an int")
    sel = obj["sel"]
    if (
        not isinstance(sel, list)
        or len(sel) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) for v in sel)
    ):
        raise ValueError("push 'sel' must be [start, end] ints")
    if not isinstance(obj["text"], str):
        raise ValueError("push 'text' must be a string")
    for entry in obj["ring"]:
        if (
            not isinstance(entry, (list, tuple))
            or len(entry) != 4
            or not all(
                isinstance(v, int) and not isinstance(v, bool) for v in entry[2:]
            )
            or not all(isinstance(v, str) and len(v) == 8 for v in entry[:2])
        ):
            raise ValueError(f"push ring entry malformed: {entry!r}")
    for h in obj["frames"]:
        if not isinstance(h, str) or len(h) != 8:
            raise ValueError(f"push frame hash malformed: {h!r}")


def parse_push(raw: bytes | str) -> BrowserState:
    """One /push body → BrowserState (validated; ValueError on malformed)."""
    obj = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    if not isinstance(obj, dict):
        raise ValueError("push body must be a JSON object")
    _validate_state(obj)
    return BrowserState(
        n=int(obj["n"]),
        k=int(obj["k"]),
        sel_start=int(obj["sel"][0]),
        sel_end=int(obj["sel"][1]),
        length=int(obj["len"]),
        text=obj["text"],
        ring=tuple(
            tuple(int(v) if i >= 2 else str(v) for i, v in enumerate(e))
            for e in obj["ring"]
        ),
        frames=tuple(str(h) for h in obj["frames"]),
        f=int(obj["f"]),
        readonly=bool(obj.get("ro", False)),
    )


def parse_title(raw: str | None) -> dict | None:
    """The document.title FALLBACK channel:
    'vtg3-browser[-ro]|{"n":..,"k":..,"f":..,"v":"<8hex>","s":<sel>,"ro":bool}'.
    Counts + hashes only (~≤200 chars — the full value never rides the title).
    Returns None for anything that is not the channel (wrong prefix, bad JSON).
    """
    if not raw or "|" not in raw:
        return None
    base, _, payload = raw.partition("|")
    if base not in ("vtg3-browser", "vtg3-browser-ro"):
        return None
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    obj["base"] = base
    return obj


# --- the event-count law in DOM terms (R.1) -------------------------------------


def input_event_law(
    before: BrowserState, after: BrowserState, *, expect: str, exp_text: str
) -> dict:
    """The DOM event-count law over two pushed states.

    expect="change": EXACTLY ONE input event (Δn == 1) whose newest ring entry
    covers the FULL before→after delta (fnv hashes AND UTF-16 lengths), no
    intermediate rAF value-hash between the two states (transient == []), the
    final value painted (painted_final), the whole frame window reconstructable
    (no underflow), and the DOM value byte-exact equal to exp_text.

    expect="noop": ZERO input events (Δn == 0), value unchanged, zero
    transitions, zero transient hashes.

    Mirrors ime_g3_support.single_edit_analysis' frame-window math on the
    page's raw frames feed (same underflow/transient/transition semantics,
    different hash space + witness). Returns a dict with `ok` plus the fields
    the row evidence cites.
    """
    if expect not in ("change", "noop"):
        raise ValueError(f"expect must be 'change' or 'noop', got {expect!r}")
    ha = fnv1a32(before.text)
    hb = fnv1a32(after.text)
    dn = after.n - before.n
    want = max(0, after.f - before.f)
    added = list(after.frames[-want:]) if want else []
    underflow = want > len(after.frames)
    internal = sum(1 for i in range(1, len(added)) if added[i] != added[i - 1])
    boundary = 1 if (added and added[0] != ha) else 0
    transitions = internal + boundary
    transient = sorted({h for h in added if h not in (ha, hb)})
    painted_final = hb in added
    ring_last = after.ring[-1] if after.ring else None
    ring_full = bool(
        dn == 1
        and ring_last is not None
        and tuple(ring_last) == (ha, hb, utf16_len(before.text), utf16_len(after.text))
        and len(after.ring) - len(before.ring) == dn  # no eviction in-window
    )
    text_ok = after.text == exp_text
    len_ok = after.length == utf16_len(exp_text)
    if expect == "change":
        ok = bool(
            dn == 1
            and ring_full
            and not transient
            and transitions == 1
            and painted_final
            and not underflow
            and text_ok
            and len_ok
        )
    else:
        ok = bool(
            dn == 0
            and hb == ha
            and not transient
            and transitions == 0
            and not underflow
            and text_ok
            and len_ok
        )
    return {
        "ok": ok,
        "dn": dn,
        "ring_full": ring_full,
        "ring_last": list(ring_last) if ring_last is not None else None,
        "transitions": transitions,
        "transient": transient,
        "painted_final": painted_final,
        "underflow": underflow,
        "frames": want,
        "text_ok": text_ok,
        "len_ok": len_ok,
        "ha": ha,
        "hb": hb,
    }


# --- argv builders (the isolation flags ARE the contract) -----------------------

CHROMIUM_BIN = "/usr/bin/chromium"

_CHROMIUM_BASE_FLAGS = (
    "--ozone-platform=wayland",  # the IM-v2 seat's native session
    "--enable-wayland-ime",  # without this the IME pipe never initializes
    "--wayland-text-input-version=3",  # 135+ requires the v3 flag for ozone IME
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",  # pixman-sway disposable seat
    "--password-store=basic",  # no keyring D-Bus hang under the private bus
)


def chromium_argv(
    profile_dir: Path | str, url: str, *, extra: tuple[str, ...] = ()
) -> list[str]:
    """One clean app-mode window: isolated temp-root profile (--user-data-dir
    is NEVER the real profile), text-input-v3 IME flags, the fixture URL.
    `extra` carries recorded fallbacks only (e.g. '--no-sandbox' inside the
    disposable desktop)."""
    return [
        CHROMIUM_BIN,
        *_CHROMIUM_BASE_FLAGS,
        f"--user-data-dir={profile_dir}",
        f"--app={url}",
        *extra,
    ]


def firefox_argv(
    profile_dir: Path | str, url: str, *, extra: tuple[str, ...] = ()
) -> list[str]:
    """The ONE bounded contingency sub-row (Chromium never activated): isolated
    profile via --profile; the lab sets MOZ_ENABLE_WAYLAND=1 in the env."""
    return [
        "/usr/bin/firefox",
        "--profile",
        str(profile_dir),
        "--new-window",
        url,
        *extra,
    ]


# --- the closed-vocabulary CLASS verdict mapper (R.7) ---------------------------


def class_verdict(rows: list[dict]) -> str:
    """Map a field class's row outcomes onto the closed vocabulary — ONE
    verdict per class, never invented words (VERIFIED_SUFFIX verbatim).

    rows: dicts with keys
      row            id (for the failure/reason text)
      ok             True | False | None (None = infra-skipped, never a pass)
      insert_ok      True when an insert leg passed on this class's witnesses
      correction_ok  True when a correction leg passed on this class's own
                     witnesses (None when not exercised)
      reason         the exact honest reason for insert-only / skipped rows
      attempted      False for explicitly-not-attempted rows (Firefox default)

    Order: FAILED row → blocked; a row carrying blocked_reason (a MEASURED
    capability gap, e.g. 'text-input never activated') with nothing passing →
    blocked; passing rows decide (insert+correction → verified; inserts only →
    insert-only with the exact reason); skipped rows (ok None, infra-only)
    decide only when NOTHING passed (they never erase real insert evidence —
    an unmeasurable zero-diff repeat does not uninsert what the class
    verifiably delivered); nothing exercised → untested.
    The reason strings stay OPEN (they carry the live measured facts, e.g.
    'surrounding_text lags the committed value at chromium 158…').
    """
    if not rows:
        return "untested (infra: no rows)"
    attempted = [r for r in rows if r.get("attempted", True)]
    if not attempted:
        return "untested (not attempted)"
    for r in attempted:
        if r.get("ok") is False:
            checks = r.get("checks") or ()
            check = checks[0] if checks else r.get("row") or "unspecified"
            return f"blocked (FAILED: {check})"
    inserts = [r for r in attempted if r.get("insert_ok") is True]
    corrections = [r for r in attempted if r.get("correction_ok") is True]
    if not inserts:
        for r in attempted:
            if r.get("blocked_reason"):
                return f"blocked ({r['blocked_reason']})"
    if inserts:
        if corrections:
            return VERIFIED_SUFFIX
        for r in attempted:
            if r.get("correction_ok") is not True and r.get("reason"):
                return f"insert-only ({r['reason']})"
        return "insert-only"
    for r in attempted:
        if r.get("ok") is None:
            why = r.get("reason") or r.get("row") or "unspecified"
            return f"untested (infra: {why})"
    return "untested (infra: no insert exercised)"


# --- bounded report renderer (wraps ime_g3_support.render_report) ---------------

_EXTRA_VERSION_KEYS = (
    "chromium",
    "chromium_flags",
    "firefox",
    "firefox_flags",
    "kernel",
    "sway",
    "gtk",
    "pygobject",
)


def render_class_report(
    versions: dict[str, str],
    rows: list[dict],
    meta: dict,
    *,
    title: str,
    links: tuple[str, ...] = (),
    drift: tuple[str, ...] = (),
) -> str:
    """The bounded row report for this item: render_report's machinery (row
    table, capped evidence, 150-line hard cap) with (a) this item's title,
    (b) the extra live-version keys render_report's fixed tuple does not know
    (chromium/flags/firefox) inserted right after the Command line, (c) an
    evidence-links + PRP-vs-code-drift block after the Summary line, then
    re-capped honestly."""
    text = render_report(versions, rows, meta)
    lines = text.split("\n")
    lines[0] = title
    extra = [f"- {k}: {versions[k]}" for k in _EXTRA_VERSION_KEYS if versions.get(k)]
    if extra:
        idx = next(
            (i for i, ln in enumerate(lines) if ln.startswith("- Command:")), None
        )
        if idx is not None:
            known = {"kernel", "sway", "gtk", "pygobject", "pacman_gtk4", "pacman_sway"}
            dedup = [ln for ln in extra if ln.split(":")[0][2:] not in known]
            lines[idx + 1 : idx + 1] = dedup
    block: list[str] = []
    if links:
        block.append("Evidence links:")
        block.extend(f"  {ln}" for ln in links)
    if drift:
        block.append("Drift notes (PRP-vs-code, recorded honestly):")
        block.extend(f"  - {ln}" for ln in drift)
    if block:
        idx = next((i for i, ln in enumerate(lines) if ln.startswith("Summary:")), None)
        if idx is not None:
            lines[idx + 1 : idx + 1] = [""] + block
    if len(lines) > MAX_REPORT_LINES:  # the insertion can cross the cap
        head = lines[: MAX_REPORT_LINES - 4]
        tail = [ln for ln in lines[len(head) :] if ln.startswith(("- ", "# ", "## "))]
        lines = head + ["[… truncated …]"] + tail[-3:]
    return "\n".join(lines[:MAX_REPORT_LINES])

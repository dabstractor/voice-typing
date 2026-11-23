"""voice_typing.ime.target — the IM-route TargetAdapter: verified acquire + re-checks (R.3).

Binds the SPECIFIC editable field — not a window, terminal process, or screen
position — by VERIFYING it through the target's own `surrounding_text`
snapshot: cursor/anchor are target-CONFIRMED evidence (R.5's third distinct
value), byte-exact per the vendored input-method-unstable-v2 XML. Everything
else fails BEFORE delivery (the refusal taxonomy, each branch test-pinned in
tests/test_ime_target.py):

  - "ime no reply"          — the IM child is dead or timed out (never retry; R.5)
  - "<host reason>"         — not activated / no surrounding text, propagated
  - "snapshot missing fields" — ok reply without text/cursor/anchor
  - "snapshot truncated"    — host sent a head-capped snapshot (cursor could
                              exceed the sent text) — refuse, never slice through
  - "inconsistent snapshot" — cursor/anchor negative or beyond the text's byte
                              length (cannot be a byte-exact field offset)
  - "user selection present" — cursor != anchor: a pre-existing user selection
                              is NEVER replaced by default (R.3)

UNITS: the wire speaks UTF-8 BYTE offsets (XML: uint byte positions), so this
adapter's units are TargetUnits.UTF8_BYTES, fixed; every char→byte conversion
goes through bulk_delivery.map_span / .encode("utf-8") on the ORIGINAL string —
never a normalized/lowercased copy (R.3's index-desync rule).

DOCUMENTED LIMITATION: IM-v2 exposes NO password/secret hint, so this adapter
cannot detect password fields — an honest gap recorded here rather than a
guessed heuristic; R.3's password rule is enforced where a signal exists
(other adapters own it).

CONSUMES: a proc duck with request(cmd, timeout=..., **fields) -> dict | None
(the S2 ImeProcess surface, P1.M4.T1.S2 — duck-typed; NEVER imported here).
CONSUMED BY: P1.M4.T3.S1 show() (recheck + to_bytes_span + binding_caret_after
before every mutation); P1.M4.T4 takeover (the mutation-time half of R.5);
P1.M6.T2.S1 constructs ImeTarget(ImeProcess(...)) in the daemon.
FENCES: show() INSERT path only (P1.M4.T3.S1): corrections (before>0) are
T3.S2 — REFUSED here, never approximated with N inserts; finalize/leave/cancel
are T3.S3; no takeover policy (T4); no manager/daemon/feedback import.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from voice_typing.bulk_delivery import (
    AcquireResult,
    ShowResult,
    TargetUnits,
    map_span,
    rendered_equal,
)

logger = logging.getLogger(__name__)

_ACQUIRE_TIMEOUT_S = 2.5  # > host _SURROUND_WAIT_S (1.0) + margin; S2's default is 1.0 — PASS EXPLICITLY
_SHOW_TIMEOUT_S = 0.25    # fits the controller's 250 ms failure deadline (M3.T2.S2)
_COMMIT_CAP_BYTES = 4000  # ≤4000 B/commit — engineering rule (item contract); larger ⇒ REFUSED, never chunked


@dataclass(frozen=True)
class FieldBinding:
    """The opaque AcquireResult.handle — everything recheck needs, nothing more.

    pre_caret is sliced from the ORIGINAL snapshot text on BYTE boundaries
    (cursor_bytes is a field-produced boundary), never a normalized copy.
    """

    im_handle: str
    cursor_bytes: int
    anchor_bytes: int
    pre_caret: str
    revision: int


class ImeTarget:
    """Daemon-side adapter: verified acquire + mutation-time re-checks (R.3).

    acquire() binds the field or refuses (fail BEFORE delivery); recheck()
    re-derives everything from ONE fresh verify pull and NEVER mutates — the
    helpers show() (T3) consults at mutation time so a queued operation that
    lost the field refuses instead of typing into the wrong place.
    """

    units = TargetUnits.UTF8_BYTES  # the wire speaks UTF-8 byte offsets (vendored XML)

    def __init__(self, proc):  # duck: ImeProcess (S2) or a test fake
        self._proc = proc
        self._binding: "FieldBinding | None" = None
        self._last_applied_span = ""  # the last APPLIED complete rendered span ("" until applied)
        self._inserted_bytes = 0      # cumulative UTF-8 bytes WE committed this acquisition
        self.last_reason = ""         # machine-readable refusal/unknown taxonomy (R.5 logs)

    # --- acquire (R.3): bind the FIELD, verify via target-CONFIRMED snapshot ---
    def acquire(self) -> AcquireResult:
        r = self._proc.request("acquire", timeout=_ACQUIRE_TIMEOUT_S)
        if r is None:
            return AcquireResult(ok=False, reason="ime no reply")
        if not r.get("ok", False):
            return AcquireResult(ok=False, reason=r.get("reason", "acquire refused"))
        text = r.get("text")
        cursor, anchor = r.get("cursor"), r.get("anchor")
        if text is None or cursor is None or anchor is None:
            return AcquireResult(ok=False, reason="snapshot missing fields")
        raw = text.encode("utf-8")  # ORIGINAL bytes — offsets are UTF-8 byte positions
        if r.get("snapshot_truncated"):
            return AcquireResult(ok=False, reason="snapshot truncated")
        if not (0 <= cursor <= len(raw) and 0 <= anchor <= len(raw)):
            return AcquireResult(ok=False, reason="inconsistent snapshot")
        if cursor != anchor:
            return AcquireResult(ok=False, reason="user selection present")  # R.3: never replace
        binding = FieldBinding(im_handle=str(r.get("handle", "")), cursor_bytes=cursor,
                               anchor_bytes=anchor,
                               pre_caret=raw[:cursor].decode("utf-8", errors="ignore"),
                               revision=int(r.get("revision", 0)))
        self._binding = binding
        self._last_applied_span = ""  # fresh acquisition: nothing applied yet
        self._inserted_bytes = 0
        return AcquireResult(ok=True, handle=binding, revision=binding.revision)

    # --- mutation-time re-check (R.5): ONE fresh verify pull; NEVER mutates ---
    def recheck(self, binding: FieldBinding, inserted_bytes: int = 0) -> tuple[bool, str, int]:
        r = self._proc.request("verify", timeout=_ACQUIRE_TIMEOUT_S)
        if r is None:
            return False, "ime no reply", 0
        if not r.get("activated", False):
            return False, "ime deactivated", 0
        if not r.get("ok", False) or r.get("text") is None:
            return False, "no surrounding text", 0
        text, cursor, anchor = r["text"], r["cursor"], r["anchor"]
        rev = int(r.get("dones", 0))
        if cursor != anchor:
            return False, "user selection present", rev
        expected = binding.cursor_bytes + inserted_bytes  # OUR accounting since acquire
        if cursor != expected:
            return False, "caret moved", rev
        # The pre-caret REGION must still start with the acquired pre_caret bytes.
        # (PRP pseudocode said `endswith`, but its own L3 gate — pre_caret "héllo ",
        # fresh "héllo w", inserted 1 → must be ok — only passes with prefix
        # semantics: our own committed text extends the region PAST pre_caret,
        # so the region cannot end with it; it must START with it.)
        if not text.encode("utf-8")[:expected].startswith(binding.pre_caret.encode("utf-8")):
            return False, "adjacent text changed", rev  # user text BEFORE our point was touched
        return True, "", rev  # post-caret changes do NOT revoke (typing itself is T4's signal)

    # --- show (R.3/R.5, P1.M4.T3.S1): the INSERT path ------------------------
    def show(self, session: int, utterance: str, seq: int,
             expected_revision: int, span: str) -> ShowResult:
        """Insert path (R.3/R.5; P1.M4.T3.S1): extend our confirmed span at the caret.

        ONE atomic commit per change: commit_string(delta) + commit. Zero-diff ⇒ zero events.
        Corrections (non-extension spans) are REFUSED here — the correction path is P1.M4.T3.S2.
        State advances ONLY on applied; unknown is never retried by the caller (controller).
        """
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        # (1) zero-diff guard FIRST — render-equal ⇒ ZERO events (R.1 event-count law)
        if rendered_equal(self._last_applied_span, span):
            return ShowResult.UNCHANGED
        # (2) insert condition: pure extension of the last APPLIED span, on ORIGINAL strings
        if not span.startswith(self._last_applied_span):
            self.last_reason = "correction not implemented (P1.M4.T3.S2)"
            return ShowResult.REFUSED
        delta = span[len(self._last_applied_span):]
        # (3) mutation-time re-check (R.5): fresh verify — activation/caret/selection/adjacency
        ok, reason, _rev = self.recheck(binding, inserted_bytes=self._inserted_bytes)
        if not ok:
            self.last_reason = f"recheck: {reason}"
            return ShowResult.REFUSED                 # NO request sent
        # (4) the per-commit byte cap (engineering rule; never chunk inside show())
        delta_bytes = len(delta.encode("utf-8"))
        if delta_bytes > _COMMIT_CAP_BYTES:
            self.last_reason = f"commit cap {_COMMIT_CAP_BYTES}B exceeded ({delta_bytes}B)"
            return ShowResult.REFUSED                 # NO request sent
        # (5) ONE atomic insert: commit_string(delta) + commit   (before=0 → no delete)
        r = self._proc.request("show", timeout=_SHOW_TIMEOUT_S, session=session,
                               utterance=utterance, seq=seq, expected_revision=expected_revision,
                               text=delta, before=0)
        # (6) honest mapping — bytes-sent ≠ applied; None/odd ⇒ unknown; never retry (R.5)
        if r is None:
            self.last_reason = "ime no reply"
            logger.warning("ime show: no reply (session=%s seq=%s span_chars=%d)",
                           session, seq, len(span))
            return ShowResult.UNKNOWN
        result = r.get("result")
        if result == "applied":
            self._last_applied_span = span            # advance ONLY on applied (Critical #1)
            self._inserted_bytes += delta_bytes
            self.last_reason = ""
            logger.info("ime show applied: session=%s seq=%s delta_bytes=%d t_ms=%s total=%d",
                        session, seq, delta_bytes, r.get("t_ms"), self._inserted_bytes)
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = "host refused"
            return ShowResult.REFUSED
        self.last_reason = f"host result {result!r}"
        logger.warning("ime show unknown: session=%s seq=%s result=%r", session, seq, result)
        return ShowResult.UNKNOWN

    # --- units plumbing for T3 (never hand-roll offsets) ---------------------
    @staticmethod
    def binding_caret_after(binding: FieldBinding, inserted_bytes: int) -> int:
        return binding.cursor_bytes + inserted_bytes

    @staticmethod
    def to_bytes_span(text: str, start_char: int, end_char: int) -> tuple[int, int]:
        """char span → UTF-8 byte span on the ORIGINAL string (thin map_span wrapper)."""
        return map_span(text, start_char, end_char, TargetUnits.UTF8_BYTES)

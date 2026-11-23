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
CONSUMED BY: P1.M4.T3.S1/S2 show() (recheck + to_bytes_span + binding_caret_after
before every mutation); P1.M4.T4 takeover (the mutation-time half of R.5);
P1.M6.T2.S1 constructs ImeTarget(ImeProcess(...)) in the daemon.
FENCES: show() = insert (T3.S1) + correction (T3.S2); finalize/leave/cancel =
T3.S3 (R.3 lifecycle — ownership ends, stop preserves, one-op cancel, no
legacy len(tail)−1 compensation); no takeover policy (T4); no manager/daemon/
feedback import.
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
        # (P1.M4.T3.S3) ownership bookkeeping — the span is PER-UTTERANCE, bytes are not.
        self._owned_utterance: "str | None" = None   # utterance owning _last_applied_span (None ⇒ none open)
        self._closed_utterances: set[str] = set()    # settled by finalize/cancel (defensive late-stray refusal)

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
        self._owned_utterance = None          # no utterance owns anything yet
        self._closed_utterances.clear()       # ...and nothing is closed in the new field
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

    # --- show (R.3/R.5): insert (P1.M4.T3.S1) + correction (P1.M4.T3.S2) ------
    def show(self, session: int, utterance: str, seq: int,
             expected_revision: int, span: str) -> ShowResult:
        """Insert OR correction (R.3/R.5; P1.M4.T3.S1 insert + P1.M4.T3.S2 correction).

        Extension of the owned span  → ONE atomic insert   (commit_string(delta)+commit,
        before=0). Any non-extension span → ONE atomic range replacement
        (delete_surrounding_text(before,0) + commit_string(span) + commit) — verified-owned:
        the delete counts BACKWARD from the caret, so recheck proves the caret sits at the
        END of our range and _owned_region_intact proves the range's content is still ours.
        Reach is bounded by OWNERSHIP, never size (user decision 2026-11-19); an unchunkable
        (> 4000 B) correction is REFUSED, never split (N chunks = N visible edits, R.1).
        Zero-diff ⇒ zero events. State advances ONLY on applied (the controller +1s
        expected_revision only on applied); unknown is never retried by the caller.
        """
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        # (0) utterance bookkeeping (P1.M4.T3.S3) — ownership is per-utterance, bytes are not.
        if utterance in self._closed_utterances:
            self.last_reason = "utterance closed"      # settled final/cancel — never a 2nd op
            return ShowResult.REFUSED
        if self._owned_utterance is not None and utterance != self._owned_utterance:
            # The previous utterance's final never came (dropped/rejected — the controller's
            # on_final_dropped makes NO finalize call): its visible words STAY on screen; we
            # merely stop owning them. NEVER a delete here (rejected finals never auto-erase).
            self._last_applied_span = ""               # ownership ends; _inserted_bytes KEEPS
        self._owned_utterance = utterance
        # (1) zero-diff guard FIRST — render-equal ⇒ ZERO events (R.1 event-count law),
        #     including for spans that would take the correction branch.
        if rendered_equal(self._last_applied_span, span):
            return ShowResult.UNCHANGED
        # (2) revision-regression guard: the caller seeds expected_revision from the
        #     acquire revision and ONLY +1s on applied — anything lower (or non-int) is a
        #     stale/desynced caller; refuse BEFORE any request (R.5).
        if not isinstance(expected_revision, int) or expected_revision < binding.revision:
            self.last_reason = "revision regression"
            return ShowResult.REFUSED
        owned = self._last_applied_span
        owned_bytes = len(owned.encode("utf-8"))      # wire units: UTF-8 bytes (astral = 4)
        span_bytes = len(span.encode("utf-8"))
        correction = False
        if span.startswith(owned):
            # ---- INSERT path (P1.M4.T3.S1, unchanged behavior) ---------------------
            delta = span[len(owned):]
            delta_bytes = span_bytes - owned_bytes
            # mutation-time re-check (R.5): fresh verify — activation/caret/selection/adjacency
            ok, reason, _rev = self.recheck(binding, inserted_bytes=self._inserted_bytes)
            if not ok:
                self.last_reason = f"recheck: {reason}"
                return ShowResult.REFUSED             # NO request sent
            # per-commit byte cap (engineering rule; never chunk inside show())
            if delta_bytes > _COMMIT_CAP_BYTES:
                self.last_reason = f"commit cap {_COMMIT_CAP_BYTES}B exceeded ({delta_bytes}B)"
                return ShowResult.REFUSED             # NO request sent
            before, text_bytes = 0, delta_bytes
            r = self._proc.request("show", timeout=_SHOW_TIMEOUT_S, session=session,
                                   utterance=utterance, seq=seq,
                                   expected_revision=expected_revision, text=delta, before=0)
        else:
            # ---- CORRECTION path (P1.M4.T3.S2): ONE atomic range replacement --------
            # (a) caret at the END of the owned range — the delete counts backward from it.
            #     (P1.M4.T3.S3) the caret is binding.cursor + CUMULATIVE _inserted_bytes and
            #     the owned range is its SUFFIX; in the single-utterance world
            #     (_inserted_bytes == owned_bytes) this is the same number as before S3.
            ok, reason, _rev = self.recheck(binding, inserted_bytes=self._inserted_bytes)
            if not ok:
                self.last_reason = f"recheck: {reason}"
                return ShowResult.REFUSED             # NO request sent
            # (b) the range's CURRENT content is still exactly ours (verified-owned range)
            if not self._owned_region_intact(binding, owned):
                self.last_reason = "owned region diverged"
                return ShowResult.REFUSED             # NO request sent
            # (c) unchunkable ⇒ refuse — never split (N commits = N visible edits, R.1)
            if span_bytes > _COMMIT_CAP_BYTES:
                self.last_reason = (f"unchunkable correction {span_bytes}B "
                                    f"> {_COMMIT_CAP_BYTES}B cap")
                return ShowResult.REFUSED             # NO request sent
            correction = True
            before, text_bytes = owned_bytes, span_bytes
            r = self._proc.request("show", timeout=_SHOW_TIMEOUT_S, session=session,
                                   utterance=utterance, seq=seq,
                                   expected_revision=expected_revision, text=span,
                                   before=owned_bytes)
        # ---- honest mapping (both paths; bytes-sent ≠ applied) ---------------------
        if r is None:
            self.last_reason = "ime no reply"
            logger.warning("ime show: no reply (session=%s seq=%s span_chars=%d)",
                           session, seq, len(span))
            return ShowResult.UNKNOWN
        result = r.get("result")
        if result == "applied":
            self._last_applied_span = span            # advance ONLY on applied
            if correction:
                # (P1.M4.T3.S3) suffix-aware: the owned span was replaced in place, so the
                # cumulative bytes move by (span − owned). Single-utterance world: identical
                # to the pre-S3 SET-to-span_bytes (there _inserted_bytes == owned_bytes).
                self._inserted_bytes = self._inserted_bytes - owned_bytes + span_bytes
            else:
                self._inserted_bytes += delta_bytes
            self.last_reason = ""
            # counts + times only — NEVER the span text (R.5)
            logger.info("ime show applied: session=%s seq=%s before=%d text_bytes=%d "
                        "total_bytes=%d t_ms=%s", session, seq, before, text_bytes,
                        self._inserted_bytes, r.get("t_ms"))
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = "host refused"
            return ShowResult.REFUSED
        self.last_reason = f"host result {result!r}"
        logger.warning("ime show unknown: session=%s seq=%s result=%r", session, seq, result)
        return ShowResult.UNKNOWN

    def _owned_region_intact(self, binding: "FieldBinding", owned: str) -> bool:
        """(P1.M4.T3.S2) ONE fresh verify pull: the byte range we are about to delete must
        still contain EXACTLY our owned span — a verified-owned range (R.3: never touch
        adjacent user text). Corrections only; inserts do not pay this roundtrip."""
        r = self._proc.request("verify", timeout=_ACQUIRE_TIMEOUT_S)
        if r is None or not r.get("ok", False) or r.get("text") is None:
            return False
        raw = r["text"].encode("utf-8")                   # ORIGINAL bytes, never normalized
        # (P1.M4.T3.S3) the owned span is the SUFFIX of our committed range: the owned_bytes
        # immediately before the expected caret. In the single-utterance world
        # (_inserted_bytes == owned_bytes) this is exactly the pre-S3 binding-caret anchor.
        end = binding.cursor_bytes + self._inserted_bytes
        start = end - len(owned.encode("utf-8"))
        if r.get("snapshot_truncated") and end > len(raw):
            return False                                  # cannot verify through the cap
        return raw[start:end] == owned.encode("utf-8")

    # --- R.3 lifecycle (P1.M4.T3.S3): finalize / leave / cancel ----------------
    def finalize(self, session: int, utterance: str, seq: int,
                 expected_revision: int, span: str) -> ShowResult:
        """R.3 finalize (P1.M4.T3.S3): settle the utterance.

        Matching final ⇒ NO further edit (zero requests — commit side effects cannot change
        or duplicate text that is already visible); ownership ends. Differing final ⇒ ONE
        replacement (the landed insert/correction paths, delegated — never reimplemented).
        No preceding partial ⇒ inserts once (logged live=false — the missed-live-update
        evidence hook; counting it in latency evidence is M6.T4/G5, fenced).
        _inserted_bytes NEVER resets here: committed text stays, caret math survives.
        A rejected/dropped final NEVER reaches this method (the controller's
        on_final_dropped is a no-target-call boundary) — the utterance-switch guard in
        show() self-heals so the next utterance INSERTS, never erases the abandoned words.
        """
        if self._binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if utterance in self._closed_utterances:
            self.last_reason = "utterance closed"       # duplicate final — never a 2nd op
            return ShowResult.REFUSED
        live = bool(self._last_applied_span) and self._owned_utterance == utterance
        result = self.show(session, utterance, seq, expected_revision, span)
        if result in (ShowResult.APPLIED, ShowResult.UNCHANGED):
            self._last_applied_span = ""                # ownership ENDS (R.3); bytes remain
            self._owned_utterance = None
            self._closed_utterances.add(utterance)
            logger.info("ime finalize settled: session=%s seq=%s result=%s live=%s",
                        session, seq, result.value, live)
        return result

    def leave(self) -> None:
        """R.3 leave (P1.M4.T3.S3): stop preserving the last visible words — NO post-stop
        writes anywhere, including a newly focused field. Never raises; idempotent; the
        host request is best-effort (releases any grab; the host keeps serving). Runs
        OUTSIDE the controller's op runner, so it bounds itself (timeout 0.25) and clears
        the binding FIRST: even a wedged call cannot leave us writing after stop.
        Post-leave, every show/finalize/cancel refuses \"not acquired\" until a fresh
        acquire() re-binds the (possibly different) field."""
        binding = self._binding
        self._binding = None                            # FIRST: nothing may write after this
        self._last_applied_span = ""
        self._owned_utterance = None
        if binding is None:
            return                                      # already left — pure no-op
        try:
            self._proc.request("leave", timeout=_SHOW_TIMEOUT_S)
        except Exception:                               # dead/raising proc must not propagate
            logger.warning("ime leave: host request raised")   # one line, no text (R.5)

    def cancel(self) -> ShowResult:
        """R.3 cancel (P1.M4.T3.S3): remove the owned fragment in ONE operation; keep
        listening. NO len(tail)−1 physical-key compensation (that is the legacy evdev
        path's rule, daemon.py — bulk cancel has NO physical key): before == owned_bytes
        EXACTLY. Uncertain range ⇒ REFUSED (the controller disarms; stop, never repair).
        Nothing pending (queued-but-undispatched partial) ⇒ UNCHANGED, no request — the
        controller stays active (G2 trace_07 pin)."""
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if rendered_equal(self._last_applied_span, ""):
            self.last_reason = "nothing pending"        # queued-but-undispatched partial ⇒ fine
            return ShowResult.UNCHANGED                 # NO request (G2 trace_07 pin)
        owned = self._last_applied_span
        owned_bytes = len(owned.encode("utf-8"))        # wire units; ORIGINAL string
        ok, reason, _rev = self.recheck(binding, inserted_bytes=self._inserted_bytes)
        if not ok:                                      # caret must END the owned range —
            self.last_reason = f"recheck: {reason}"     # the delete counts backward from it
            return ShowResult.REFUSED
        if not self._owned_region_intact(binding, owned):
            self.last_reason = "owned region diverged"  # uncertain range ⇒ stop (R.5)
            return ShowResult.REFUSED
        r = self._proc.request("cancel", timeout=_SHOW_TIMEOUT_S, before=owned_bytes)
        if r is None:
            self.last_reason = "ime no reply"
            logger.warning("ime cancel: no reply (before=%d)", owned_bytes)
            return ShowResult.UNKNOWN
        result = r.get("result")
        if result == "applied":
            u, self._owned_utterance = self._owned_utterance, None
            if u is not None:
                self._closed_utterances.add(u)
            self._last_applied_span = ""
            self._inserted_bytes -= owned_bytes         # caret moved BACK by owned_bytes
            self.last_reason = ""
            logger.info("ime cancel applied: before=%d remaining_bytes=%d t_ms=%s",
                        owned_bytes, self._inserted_bytes, r.get("t_ms"))
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = "host refused"
            return ShowResult.REFUSED
        self.last_reason = f"host result {result!r}"
        logger.warning("ime cancel unknown: result=%r", result)
        return ShowResult.UNKNOWN

    # --- units plumbing for T3 (never hand-roll offsets) ---------------------
    @staticmethod
    def binding_caret_after(binding: FieldBinding, inserted_bytes: int) -> int:
        return binding.cursor_bytes + inserted_bytes

    @staticmethod
    def to_bytes_span(text: str, start_char: int, end_char: int) -> tuple[int, int]:
        """char span → UTF-8 byte span on the ORIGINAL string (thin map_span wrapper)."""
        return map_span(text, start_char, end_char, TargetUnits.UTF8_BYTES)

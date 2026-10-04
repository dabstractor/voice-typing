# Validation Report — voice-typing (Rev 2 streaming + bugfix delta)

## Overview

End-to-end PRD validation of the current tree (HEAD `fd32e4e`), which contains the complete
fix delta for the 8 bugs filed in the previous validation round (BUG-001…BUG-008, commits
`03f9602`…`eac2d03`). Method: ran the repo's own gates (ruff check, the 401-test fast CUDA-free
pytest set), then drove the **real daemon + real StreamingOutput engine** through complete user
journeys with the **production event ordering** — every child partial is dispatched by the host
reader as `('partial', text)` **followed by** the paired `('speech', {})` event
(`daemon._build_callbacks._partial` fires `on_speech()` on every stabilized partial;
`recorder_host._child_on_speech` relays it) — plus a live ControlServer over a real AF_UNIX
socket, the config fail-fast contract, and `voicectl` client exit codes (0/2/64). No CUDA model
was loaded; the CUDA-gated suites (`test_feed_audio.py`, `test_daemon.py` heavy paths,
`test_recorder_host.py`, `tests/*.sh`) were not run per AGENTS.md guidance.

**Result: all 8 PRD bugs are verified FIXED** (regression-probed at the daemon/engine level,
each reproduced the old failure mode and now passes). **2 new issues found — both introduced by
the BUG-001/BUG-002 fix delta itself**: the new `resume()` seam is called from `_touch_speech`,
which fires on *every* partial (via the paired speech event), so it lifts freezes and
suppression far earlier than its "next genuinely-new speech" contract — defeating the
user-keypress freeze (PRD §4.2quater rule 5) and the rejected-final session freeze (the very
guard BUG-001 added).

## PRD Bug Fix Verification (all 8 fixed)

| PRD bug | Fix commit | Verified by probe | Outcome |
|---|---|---|---|
| BUG-001 rejected final silences session | `03f9602`+`60356cc` (`resume()` seam) | rejected final → next utterance types; user cue emitted | **FIXED** (see ISSUE-002 for a residual hole) |
| BUG-002 post-cancel suppression kills live typing | `8dc1534`+`e6cf128` | cancel → re-said sentence streams live before commit; tail rewound (`bs 14` for a 15-char tail) | **FIXED** |
| BUG-003 frozen commit glues words | `aae7060` | keypress-frozen commit types the separator; screen `Hello world the quick new sentence` | **FIXED** |
| BUG-004 no listening gate on partials | `fe30155` | stale partial AND final after stop type nothing | **FIXED** |
| BUG-005 empty socket line hangs client | `c22df05` | bare newline gets `{"ok": false, "error": "malformed JSON: ..."}` | **FIXED** |
| BUG-006 unknown config table silently ignored | `bcf7205` | `from_toml({'outpt': {...}})` raises TypeError | **FIXED** |
| BUG-007 stop-after-cancel drains ~5s | `c9f2c8b` | cancelled sentinel clears `_final_pending` (stop takes the immediate path) | **FIXED** |
| BUG-008 guard-induced rewind churn | `eac2d03` | capitalized mid-sentence partials extend with zero backspaces | **FIXED** |

## Critical Issues (Must Fix)

None.

## Major Issues (Should Fix)

### Issue 1: The user-keypress freeze is lifted by the very next partial — the engine types over the user's cursor, violating PRD §4.2quater rule 5
**Severity**: Major
**ID**: ISSUE-001
**Location**: `voice_typing/streaming.py:283-296` (`resume()` lifts ANY non-backend freeze, including per-utterance ones); `voice_typing/daemon.py:1405` (`_touch_speech` calls `self._stream.resume()`); root wiring: `voice_typing/daemon.py:229-235` (`_build_callbacks._partial` fires `on_speech()` on **every** stabilized partial) + `voice_typing/recorder_host.py:568` (`_child_on_speech` relays it as the `('speech', {})` event dispatched right after each `('partial', ...)`).

**Description**:
PRD §4.2quater rule 5 and README.md:166 promise: "Any non-Backspace keypress while a fragment
is pending freezes the fragment … never typed over" — the per-utterance freeze must hold until
that utterance's commit absorbs the tail. The BUG-001/BUG-002 fix added `resume()` and wired it
into `_touch_speech`, described as "the next utterance's genuinely-new speech". But `_touch_speech`
is not an utterance-start signal: the child fires `on_speech()` inside the partial callback
itself (that is how the idle auto-stop clock resets on every partial — `daemon.py:1383-1385`
documents this), so the host reader dispatches a `('speech', {})` event after **every** partial.
Consequently, after a user keypress freezes the pending tail:

- partial N+1 arrives → `_on_partial` → frozen → mirror-only (the freeze "works" for one cycle);
- its paired speech event → `_touch_speech` → `resume()` → **the freeze lifts** (it is a
  non-backend-origin freeze; `resume()` never checks the freeze class);
- partial N+2 extends the tail and **types at the user's cursor** — exactly the corruption
  rule 5 exists to prevent (e.g. the user typed `x` mid-fragment → `hello worxld again`-style
  out-of-order text).

The keypress freeze therefore survives exactly one partial cycle (~0.3–1 s) instead of the rest
of the utterance. Any non-Backspace keypress counts — `key_listener.parse_key_event` routes
modifier keys (Shift/Ctrl/CapsLock, which insert nothing) to the same `OTHER_PRESS` path — so
this triggers on ordinary modifier use during dictation. The repo's own suite misses it because
the daemon-level fix tests (`tests/test_daemon.py:4579`
`test_cancel_then_next_utterance_streams_live_daemon_level`) fire `_touch_speech` as a
standalone "next speech" event *before* the re-said partials — an event order production never
produces (production pairs speech with every partial). The engine-level freeze tests never call
`resume()` mid-utterance.

**Steps to Reproduce** (probe in `./validate.sh`, Journey 7 — mirrors production dispatch order):
arm (streaming on) → feed partial pair `hello wor` (typed) → `note_user_keypress()` (frozen,
verified `frozen_after_keypress=True`) → feed partial pair `hello world` (mirror-only; paired
speech lifts the freeze — `frozen_after_next_partial=False`) → feed `hello world again` →
backend receives the delta typed over the user's edit (`typed='hello world again'`, i.e.
`'ld again'` landed after the keypress). Live repro: arm, speak a fragment, press any key
(e.g. Shift), keep speaking — typing resumes over the edit within ~a second.

### Issue 2: A stray partial after a rejected final lifts the session freeze — hallucination text gets typed despite the blocklist
**Severity**: Major
**ID**: ISSUE-002
**Location**: same seam as ISSUE-001 (`voice_typing/daemon.py:1405` + `streaming.py:283-296`); contradicted invariant documented at `voice_typing/daemon.py:1399-1401`.

**Description**:
When a final is rejected (blocklist hallucination such as `thank you.`, or below `min_chars`),
the daemon freezes the engine SESSION-class so "stray late partials of the dead utterance
cannot revise the frozen tail", and `_touch_speech`'s comment asserts: *"A stray late partial
of the rejected utterance never reaches this hook — it arrives via `_on_partial`."* That
invariant is false: every partial is paired with a `('speech', {})` event (see ISSUE-001), so
the first stray partial after a rejected final calls `resume()` via its paired speech event and
**lifts the session freeze**. A second stray partial then types as a fresh start — including
the hallucination text the blocklist exists to suppress. This partially re-opens, on the
partial path, the exact hole BUG-001 was filed against ("triggered by the hallucinations the
filter exists to catch", PRD §8 top-3 risk): finals are still filtered, but Whisper's
silence-hallucination cycles emit realtime partials too, and after the first one disarms the
freeze the rest land on screen (lowercased by the mid-sentence casing guard, case-preserved at
session start). The fragment stays typed if the user stops dictating; it is only revised away
if more speech follows. The same mechanism weakens the post-cancel stale window in principle
(a stray partial pair of the cancelled utterance lifts `_suppressed` early), though
`host.cancel()`'s audio discard makes strays unlikely there.

**Steps to Reproduce** (probe in `./validate.sh`, Journey 8): arm → partial pair `real words` →
final `Real words` (committed) → final `Thank you.` (rejected → session freeze,
`frozen_after_reject=True`) → stray partial pair `thank you` (mirror-only, then freeze lifted —
`frozen_after_stray_pair=False`) → one more stray partial `thank you` → backend types it:
`typed='real words thank you'`. Live repro: arm, dictate a sentence, let silence produce a
hallucinated final (the toast `filtered hallucination — not typed; keep dictating` appears),
then stay quiet through the next hallucination cycle — the hallucination text is typed anyway.

## Minor Issues (Nice to Fix)

None beyond the two above. Process-level observations (not defects): no type checker is
configured (no mypy/pyright config — Phase 2 N/A), and no formatter gate is adopted (`ruff
check` is the only lint gate; `ruff format --check` would reformat 23 files, but the project
never opted in, so this is not counted as an issue).

## Testing Summary

- Gates: `ruff check voice_typing tests` clean; fast CUDA-free pytest set **401 passed**
  (127 s; excludes the CUDA-gated suites per AGENTS.md).
- E2E probes (`./validate.sh` Phase 5): **25 checks — 23 pass, 2 fail** (ISSUE-001, ISSUE-002).
  Coverage: all 8 PRD-bug regressions, core arm→stream→commit→second-utterance→stop journey,
  cancel compensation rewind, session reset on stop, config contract (valid load, unknown
  table, unknown key, repo `config.toml`), live control-socket protocol (empty line, malformed
  JSON, non-object JSON, unknown command, status), and `voicectl` exit codes (0 live status,
  64 unknown/missing command, 2 daemon down).
- Total bugs found: **2** (0 critical, 2 major, 0 minor). All 8 PRD bugs verified fixed.

## Recommendations

- Make `resume()` class-aware or move the lift point: only a rejected-final (session-class,
  non-backend-origin) freeze — and the post-cancel `_suppressed` flag — should be liftable at
  the speech seam; per-utterance (user-keypress) freezes must survive until the utterance's
  `reset_boundary()`. Alternatively, gate the lift on genuinely-new speech (e.g. fire it from
  the child's utterance-start VAD transition, not from the per-partial `on_speech` relay).
- Enforce the "freeze survives stray partials" property with daemon-level regression tests
  driven in the PRODUCTION event order (each partial followed by its paired speech event) —
  the current fix tests fire `_touch_speech` standalone, which is why both regressions landed
  green. `./validate.sh` Journeys 7/8 are ready-made failing cases.
- Correct the false invariant comment at `daemon.py:1399-1401` ("a stray late partial … never
  reaches this hook") when fixing — it is what allowed the regression through review.
- Consider having `host.cancel()`/sentinel handling also re-arm suppression against stray
  partial pairs of the cancelled utterance (same root cause as ISSUE-002).

# Research — bugfix plan P1.M3.T9.S1 (README streaming/cancel/configuration sweep)

Repo @ eac2d03 (all 8 bugfixes landed; M1/M2 Complete).

## Landed behaviors → README impact (verified against code)

| Bug | Landed behavior (code pin) | README section | Action |
|---|---|---|---|
| BUG-001 | Rejected final (blocklist/min_chars) freezes only THAT utterance's tail; typing resumes at next genuinely-new speech (`_touch_speech → stream.resume()`, daemon.py:1396-1404; commit 60356cc). User-visible cue: journal WARNING "streaming: final rejected by filter (blocklist/min_chars); tail frozen as-is, typing resumes at next speech" (daemon.py:1181-1183) + hyprctl toast `feedback.notify("filtered hallucination — not typed; keep dictating")` (daemon.py:1185-1186, self-gated on `hypr_notify`). | §Streaming dictation safety rails | ADD bullet (currently silent) |
| BUG-002 | Re-said sentence after Backspace-cancel streams LIVE (suppression lifted at genuinely-new speech, same `resume()` hook; commit 8dc1534/e6cf128). | §Backspace-cancel | ADD clause to "just say the sentence again" |
| BUG-003 | Frozen commit types the trailing space (commit aae7060). Internal correctness — README already promises space-separated words. | — | NO CHANGE (explicit verdict) |
| BUG-004 | `_on_partial` gated on listening — stale partials never type while toggled off (commit fe30155). | §Streaming ("A pause never ends the session" bullet / safety rails) | ADD one line (acceptance-#4 guarantee) |
| BUG-005 | Empty control-socket line gets malformed-JSON error reply (commit c22df05). README §Logs/status does NOT document request framing (grep: no JSON-lines protocol prose). | §Logs, status, stopping | NO CHANGE (explicit verdict) |
| BUG-006 | Unknown top-level config TABLE raises TypeError like unknown keys (commit bcf7205). | §Configuration, L243-244 ("rejects unknown keys with TypeError") | EXTEND sentence to "and unknown tables" |
| BUG-007 | Cancel-then-stop disarms immediately — cancelled utterance finalizes at its sentinel, no ~5s drain (commit c9f2c8b). | §Backspace-cancel | ADD clause |
| BUG-008 | Extend matching is case-insensitive (comparison-normalized) so a casing-guarded tail still extends by clean deltas (commit eac2d03). | §Streaming "Partials are typed live" bullet | ADD clause |

## README map (@ HEAD, 436 lines)

§Streaming dictation :129 (bullets: partials-live ~:138, silence-commit ~:142, continuations
~:147, pause-never-ends ~:151; safety rails: stranded-tails ~:154, keystrokes-win ~:157,
rollback-hatch ~:159) · §Backspace-cancel :164-181 (idempotent ~:172, listener ~:176, one-warning
~:178, fallback bind ~:180) · §Feedback surfaces :182 · §Configuration :197 (table :205-233,
VAD-constants note :234, unknown-keys sentence :243-244) · §Logs/status :339-388 ·
§Model lifecycle :389. Plan doc: architecture/config_tests_docs.md :22 (heading line numbers) —
matches.

## Constraints from the contract

- Mode B changeset-level sweep: edit ONLY where prose is wrong or silent about a landed behavior;
  minimal, user-facing, NO engine internals (resume(), freeze classes, _suppressed stay out).
- Explicit no-change verdict per section where no edit is needed (contract demands it).
- tests/ACCEPTANCE.md is the SIBLING task S2 — do not touch.
- Docs-only change: validation is grep/verify-based, no heavy suites.

## Verification greps for the implementer (claim → pin)

- toast text: `grep -n "filtered hallucination" voice_typing/daemon.py` → :1186
- resume hook: `grep -n "_stream.resume()" voice_typing/daemon.py`
- unknown tables: `grep -n "unknown.*table\|table.*unknown" voice_typing/config.py`
- partial gate: `grep -n "_on_partial" voice_typing/daemon.py` (is_listening check)
- hypr_notify gating of notify(): feedback.notify self-gates per daemon comment :1179-1180.

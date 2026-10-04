# Research — P1.M3.T9.S1 README sweep: streaming/cancel/configuration prose (Rev 2 bugfix changeset)

Mode B changeset-level docs sweep. Ground truth verified 2026-07-23: README sections read verbatim
(:129/:164/:197 confirmed), landing state grepped, the cited architecture note read, the parallel
task checked. ONE file edited: README.md. The verdict per section is mostly KNOWN at PRP time
(below) — the implementer verifies live then applies the three small required edits.

---

## 1. Section map (verified) + the parallel task is disjoint

README headings: Streaming dictation :129, **Backspace-cancel :164** (a ### under Streaming),
Configuration :197. The parallel P1.M2.T5.S1 (empty-line socket reply) touches daemon.py +
test_control_socket.py; its conditional README touch ("§Logs/status only if it documents request
framing") does NOT fire — `grep -niE 'empty line|request framing|one JSON (object|line) per' README.md`
→ no matches. Zero overlap. config.toml's header extension is T6.S1's Mode A ride-along (different
file). ACCEPTANCE.md rows 4/11/12 are P1.M3.T9.S2 — NOT this task. No docs/ dir exists.

## 2. Landing state (grepped)

- BUG-001/002 (M1.T1/T2 ✅): `resume()` + suppression-lift landed in streaming.py (:116/:166/:210-217);
  daemon wires resume at next `_touch_speech` (:1166) + a user-visible rejected-final journal line
  (:1169 "streaming: final rejected by filter (blocklist/min_chars); tail frozen …").
- BUG-003 (M1.T3 ✅): frozen-absorb path carries the companion fix (streaming.py :486 comment).
- BUG-004 (M1.T4 ✅): `_on_partial` gate landed (daemon.py :1397, P1.M3.T2.S2 re-plan docstring).
- BUG-006 (T6.S1, PLANNED — lands before this task per M2→M3 ordering): unknown-table rejection in
  config.py from_toml. **Preflight gate**: `grep -nE 'unknown.*(table|section)|_KNOWN_TABLES' voice_typing/config.py`
  must hit; if absent at implementation time → report blocked (do not write a false claim).

## 3. Verdict per section (pre-derived; verify live, then edit)

### §Streaming dictation (:129-163) — ONE required bullet + one optional clause
Current "Safety rails" bullets: Stranded tails freeze / Your keystrokes win / Rollback hatch.
- **REQUIRED (named in the contract)**: SILENT about rejected finals. Add one bullet (before the
  Rollback-hatch bullet): a filter-rejected final (blocklist hallucination / sub-`min_chars`)
  freezes THAT fragment and logs a journal line; the NEXT utterance types live again — the session
  never stays silent until re-toggle (the BUG-001 guarantee).
- **OPTIONAL (recommended, small)**: the now-true BUG-004 guarantee — nothing types while toggled
  off (a trailing partial arriving just after toggle-off is dropped). One short bullet or clause.
- **NO-CHANGE verdicts (explicit, per the contract)**: BUG-003 (frozen-commit trailing space) —
  internal correctness; the config table's `output.append_space` row already promises the
  user-visible outcome (space-separated commits). architecture/config_tests_docs.md's per-bug map
  agrees: "BUG-003 | none (README already promises space-separated words)". BUG-008 (case-insensitive
  extends) — internal engine detail; the existing "an extension types only the delta" bullet remains
  accurate (MORE accurate post-fix). Do NOT document either.

### §Backspace-cancel (:164-181) — ONE required clause
Current: "…the mic stays hot — just say the sentence again."
- **REQUIRED (named in the contract)**: SILENT that the re-said sentence types LIVE. Extend the
  sentence: the re-said words stream live (partials and all) — cancel never degrades the next
  utterance to append-only (the BUG-002 guarantee).
- **NO-CHANGE verdict**: BUG-007 (stop-after-cancel immediacy) — internal timing; README is silent
  and should stay so (a stall that no longer happens is not user-facing prose).

### §Configuration (:197-233) — ONE required sentence (gated on T6 landing)
Current intro: "Real tunable keys (every key below is a real field in `voice_typing/config.py`):"
- **REQUIRED (named in the contract — "config table rejection")**: SILENT on the fail-fast
  contract. Add one sentence near the intro: unknown KEYS and unknown `[section]` names are both
  rejected at load time with a clear error — a typo'd section name can never silently disable a
  feature (the BUG-006 guarantee).
- **NO-CHANGE verdict**: the table itself is accurate (spot-checked: lite_model 0.8 gate,
  context_prompt, cancel.*, output.streaming rows all match the landed schema). Do not touch rows.

## 4. Voice + scope

README voice: bold bullet leads, em-dash (—), backticks for config keys, terse command-first. The
three edits are each ONE bullet/sentence — minimal, user-facing, no engine internals (no
resume()/_suppressed/reset_boundary in prose). Do NOT touch: Feedback surfaces (accurate), Upgrading
from Rev 1, First run, §Logs/status, the config TABLE rows, ACCEPTANCE.md (S2), config.toml (T6.S1).
If live verification shows a section already covers a behavior, record the no-change verdict in the
subtask result instead of forcing the edit (the contract explicitly allows this).

## 5. Validation
Greps: the three new phrases present; the no-change sections byte-identical (`git diff --stat` shows
only README.md; `git diff README.md` touches only the three regions). Header count unchanged (grep
-cE '^#{1,3} ' before/after). Fence count stays even. No test framework applies (markdown).

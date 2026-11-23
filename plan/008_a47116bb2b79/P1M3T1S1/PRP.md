# PRP — P1.M3.T1.S1: Contracts module — DeliveryTarget Protocol + result taxonomy + zero-diff guard

## Goal

**Feature Goal**: Create `voice_typing/bulk_delivery.py` — the pure, stdlib-only **R.3 contract surface** for Rev 4 bulk text delivery (PRD §4.2sexies): the `DeliveryTarget` Protocol (`acquire`/`show`/`finalize`/`leave`/`cancel`), the `applied | unchanged | refused | unknown` result taxonomy, the units-mapping contract (with a pure helper for the three mechanical units), and the generalized **zero-diff guard** (`rendered_equal` — spacing-normalized render equality; real case/punctuation/word differences NEVER equal). Contracts only, zero implementation: the controller (P1.M3.T2.S1) and both adapters (M4/M5) consume this module.

**Deliverable** (TWO new files; nothing else changes):
1. `voice_typing/bulk_delivery.py` — `ShowResult`, `AcquireResult`, `@runtime_checkable DeliveryTarget(Protocol)`, `TargetUnits`, `map_span()`, `rendered_equal()`; Mode A module docstring carrying the R.2/R.3 contract summary.
2. `tests/test_bulk_delivery.py` — pure unit tests incl. Unicode, the do-not-touch guard, and the source-scan purity check.

**Success Definition**:
- (a) The Protocol's five methods and the taxonomy match the R.3 wording exactly (names, args, return shapes — §5 of the research note, pinned).
- (b) `rendered_equal` implements the R.1 generalization: whitespace-run/line-break normalization → exact compare; case/punctuation/word differences are never equal (the existing streaming exact-equal guard stays untouched — generalized, not replaced).
- (c) `map_span` is Unicode-exact for UTF8_BYTES/CHARACTERS/UTF16_UNITS (é, CJK, astral-plane emoji) and raises for EDITOR_MARKERS (adapter-owned); it operates only on the ORIGINAL string (never a normalized copy).
- (d) The module imports NOTHING from `voice_typing.streaming` / `typing_backends` / `daemon`, exposes NO `type_text`/`press_backspace`/`make_backend`/`StreamingOutput` (the d2 §3 do-not-touch law), and stays importable in every context (pure stdlib: `enum`, `dataclasses`, `typing`).
- (e) `timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_zero_diff_rewind.py -q` → all pass (the second file proves streaming is untouched).

## User Persona

**Target User**: The implementing agents of P1.M3.T2.S1 (controller), M4.T2/T3 (IM-v2 adapter), and M5 (pi editor adapter) — they program against this contract; and the G2/G3 verification passes, which assert controller/adapter behavior in terms of this taxonomy.

**Use Case**: The controller asks `target.show(session, utt, seq, rev, span)` and branches on `APPLIED/UNCHANGED/REFUSED/UNKNOWN` (only the first two keep delivery active; `UNKNOWN` disarms, never retries — R.5). Adapters implement the Protocol; tests use `runtime_checkable` isinstance to pin conformance.

**Pain Points Addressed**: The Rev 2/3 incidents (whole-tail rewinds, dropped-insertion desync) came from under-specified delivery contracts. Pinning the taxonomy + zero-diff + units rules in ONE pure module prevents each consumer from re-inventing (and re-breaking) them.

## Why

- PRD §4.2sexies R.3 mandates the separation: "A new bulk-delivery controller plus a TargetAdapter, SEPARATE from `StreamingOutput`/`typing_backends.py`… the bulk adapter MUST NOT expose `type_character`/`press_backspace` or any typing fallback." The contracts module is the seam that enforces it structurally (grep-able, test-guarded).
- R.1's event-count law (insert=1, correct=1, zero-diff=0) and the "bytes sent is not applied; unknown is not delivered" rule need a NAMED taxonomy before the controller can exist — this is the first D2 code subtask and blocks T2.
- The zero-diff guard already exists as streaming's exact-equal no-op (pinned by `test_zero_diff_rewind.py` T1) but is engine-internal; R.1 generalizes it (rendered comparison) and every adapter needs the same rule. A pure function ends the re-implementation.
- The units rule ("never slice via a lowercased/normalized copy") is the exact class of bug that desyncs indices (cf. the Rev 2 casing-guard churn incident); a tested mechanical helper closes it for 3 of 4 unit kinds.

## What

One new pure module + its tests, per the design in research §4–§5. Signatures:

```python
ShowResult(str, Enum)          # APPLIED/UNCHANGED/REFUSED/UNKNOWN — str values = the PRD words
AcquireResult (frozen dc)      # ok, handle (opaque object), revision, reason
@runtime_checkable
class DeliveryTarget(Protocol):
    def acquire(self) -> AcquireResult: ...
    def show(self, session: int, utterance: str, seq: int, expected_revision: int, span: str) -> ShowResult: ...
    def finalize(self, session: int, utterance: str, seq: int, expected_revision: int, span: str) -> ShowResult: ...
    def leave(self) -> None: ...
    def cancel(self) -> ShowResult: ...

TargetUnits(str, Enum)         # UTF8_BYTES / CHARACTERS / UTF16_UNITS / EDITOR_MARKERS
def map_span(text: str, start_char: int, end_char: int, units: TargetUnits) -> tuple[int, int]: ...
def rendered_equal(old: str, new: str) -> bool: ...   # " ".join(s.split()) on both, then exact ==
```

### Success Criteria

- [ ] `ShowResult` has exactly the four members with str values `"applied"/"unchanged"/"refused"/"unknown"`.
- [ ] `DeliveryTarget` is a runtime-checkable Protocol with the five methods above; a minimal fake satisfies `isinstance(fake, DeliveryTarget)`.
- [ ] `rendered_equal`: whitespace/strip/newline/NBSP-only diffs → `True`; case, trailing-period, and word diffs → `False`; Unicode (diacritics, astral emoji) handled by plain str ops.
- [ ] `map_span`: identity for CHARACTERS; byte-exact UTF-8 offsets; surrogate-pair-aware UTF-16 counts (😀 = 4 bytes / 2 units); EDITOR_MARKERS raises `NotImplementedError`; out-of-range raises `ValueError`.
- [ ] The do-not-touch guard + source-scan tests pass (no forbidden attrs; no forbidden imports).
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_zero_diff_rewind.py -q` → 0 failed.
- [ ] Only the two new files exist; `git status --short` shows exactly them.

## All Needed Context

### Context Completeness Check

_Pass._ The R.3 contract wording is quoted verbatim in the research note with signatures pinned; the repo's protocol-module precedent (`audio_ducking.py`) is identified; the existing zero-diff guard + its characterization tests are located (generalize, don't touch); the do-not-touch surface (d2 §3) and the shared-state traps are listed; the Unicode semantics of the normalization idiom are specified. The module is pure stdlib with no unlanded dependencies.

### Documentation & References

```yaml
# MUST READ — the design: signatures, taxonomy, normalization semantics, traps, test matrix, scope
- docfile: plan/008_a47116bb2b79/P1M3T1S1/research/bulk_delivery_contracts.md
  why: "§1 IS/IS-NOT + the d2 §3 traps (no _stream sharing, no typing fallback, own feedback keys).
        §2 the audio_ducking.py protocol-module precedent. §3 the existing pieces generalized (the
        streaming exact-equal guard + test_zero_diff_rewind T1; the units rule). §4 the R.3 verbatim
        wording each signature/docstring encodes + the R.1/R.2 docstring lines. §5 the pinned types.
        §6 the consumers. §7 the test matrix. §8 tooling/scope."
  section: "ALL load-bearing — §4/§5 are the contract text."

# MUST READ — the do-not-touch surface + shared-state traps (the separation law)
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§3 maps StreamingOutput (:180, every method line), typing_backends (ABC :75, make_backend),
        and the three traps (the _on_final_lock commit path daemon.py:1275-1286; daemon.py:1738-1741
        reading _stream.committed for the prompt push; feedback mirrors riding streaming paths).
        §4 the ctl/feedback recipes (bulk state gets its OWN keys — not this task, but the docstring
        must not promise hijacking partial)."
  critical: "Bulk code must NOT call type_text/press_backspace/make_backend/StreamingOutput.* — encode
             as the guard test, not just prose."

# MUST READ — the module-style precedent (Protocol + runtime_checkable, pure stdlib)
- file: voice_typing/audio_ducking.py
  why: "The landed contracts-module precedent (M2.T2): `from typing import Protocol, runtime_checkable`,
        @runtime_checkable class DuckBackend(Protocol), module docstring carrying the contract.
        bulk_delivery.py mirrors this style."
  pattern: "Protocol module: docstring contract → enums/dataclasses → @runtime_checkable Protocol →
            pure helpers; zero heavy imports."
  gotcha: "READ for style only — do not import or couple to it."

# MUST READ — the R.3 source wording (what every docstring/signature must encode)
- docfile: PRD.md
  why: "§4.2sexies R.1 (event-count law; zero-diff generalization wording), R.2 (the evidence table +
        'a passing transport probe NEVER flips to passed' — the docstring's caution line), R.3 (the
        acquire/show/finalize/leave/cancel model, the taxonomy, the units rule, the no-fallback law),
        R.5 (unknown/refused → disarm, never retry — context for the taxonomy docstrings)."
  critical: "READ-ONLY. Quote R.3's semantics in docstrings; do not paraphrase away 'Bytes sent is not
             applied; unknown is not delivered.'"

# CONTEXT — the existing guards this module generalizes (do NOT modify)
- file: voice_typing/textproc.py
  why: "apply_streaming_guards (:82) is the existing casing/period guard; clean() step 1
        (\" \".join(text.split())) is the spacing idiom rendered_equal reuses verbatim. The bulk path
        compares AFTER guards — the pure function owns only the spacing normalization."
  critical: "Do NOT edit textproc.py. The zero-diff function is NEW and standalone."
- file: tests/test_zero_diff_rewind.py
  why: "T1 pins streaming's exact-equal guard (identical final ⇒ zero keystrokes) — the thing
        rendered_equal GENERALIZES (adds spacing normalization; keeps case/punct strict). Re-run this
        file in validation to prove streaming is untouched."
  critical: "READ-ONLY."
- file: voice_typing/streaming.py
  why: "The separated-from engine (:180). Only context — the module must not import or reference it."
  critical: "READ-ONLY; the source-scan test enforces the non-import."

# CONTEXT — the parallel task (disjoint)
- file: plan/008_a47116bb2b79/P1M2T4S1/PRP.md
  why: "Edits config.py/config.toml/test_config.py (duck_mode default flip). Zero overlap with two
        brand-new files."
  critical: "No conflict."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/
  streaming.py        # SEPARATED-FROM engine — read-only context, never imported
  typing_backends.py  # the forbidden surface (type_text/press_backspace/make_backend)
  audio_ducking.py    # the protocol-module STYLE precedent
  bulk_delivery.py    # ← CREATE (this task)
tests/
  test_zero_diff_rewind.py   # the guard this generalizes — re-run to prove untouched
  test_bulk_delivery.py      # ← CREATE (this task)
```

### Desired Codebase tree

```bash
voice_typing/bulk_delivery.py    # NEW — R.3 contracts: ShowResult, AcquireResult, DeliveryTarget
                                 #   Protocol, TargetUnits, map_span, rendered_equal. Pure stdlib.
tests/test_bulk_delivery.py      # NEW — taxonomy/Unicode/guards/purity tests (plain functions).
# NOTHING ELSE. No streaming/textproc/typing_backends/config/daemon edits.
```

### Known Gotchas

```python
# CRITICAL #1 — CONTRACTS ONLY, NO IMPLEMENTATION. No adapter logic, no queue, no I/O, no imports of
#   streaming/typing_backends/daemon (d2 §3). The controller (T2) and adapters (M4/M5) implement;
#   this module only pins names, shapes, and the two pure rules (zero-diff, units).
# CRITICAL #2 — THE NO-TYPING-FALLBACK LAW IS TESTED, NOT JUST DOCUMENTED. The guard test asserts the
#   module exposes no type_text/press_backspace/make_backend/StreamingOutput, and the source-scan
#   test asserts the file imports none of voice_typing.streaming/typing_backends/daemon.
# CRITICAL #3 — rendered_equal NEVER FOLDS CASE OR STRIPS PUNCTUATION. Only the spacing guard runs
#   (" ".join(s.split()) — collapse runs incl. line breaks and Unicode whitespace such as NBSP, strip
#   ends); then EXACT ==. "Hello"/"hello" and "Hi."/"Hi" are REAL differences (R.1). Lowercasing
#   here would resurrect the exact index-desync class the units rule forbids.
# CRITICAL #4 — map_span COUNTS ON THE ORIGINAL STRING ONLY (never a lowercased/normalized copy —
#   R.3). UTF-16 counts must be surrogate-pair aware (an astral char = len(ch)==2 → 2 units);
#   UTF-8 offsets are cumulative byte lengths. EDITOR_MARKERS is deliberately unimplemented
#   (adapter-owned) — raise NotImplementedError, do not guess.
# CRITICAL #5 — STR-VALUED ENUMS. ShowResult/TargetUnits subclass str so values serialize straight
#   into status/log lines (R.5's delivery_state surface) — matching the repo's mode/phase string
#   conventions.
# GOTCHA #6 — runtime_checkable isinstance only checks METHOD PRESENCE — the conformance test uses a
#   minimal fake; real behavioral conformance is G2's job (T2), not this module's.
# GOTCHA #7 — FULL TOOL PATHS (.venv/bin/python; zsh aliases); timeout 60 wrapper; mypy NOT
#   installed; ruff optional (/home/dustin/.local/bin/ruff).
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/bulk_delivery.py — pure stdlib: enum, dataclasses, typing only.
class ShowResult(str, Enum):
    APPLIED = "applied"        # the target executed AND confirmed the edit
    UNCHANGED = "unchanged"    # render-equal to what's already shown — ZERO events emitted
    REFUSED = "refused"        # the target actively declined (focus/ownership mismatch, …)
    UNKNOWN = "unknown"        # outcome unverifiable (timeout, lost ack) — NOT delivered; never retry

@dataclass(frozen=True)
class AcquireResult:
    ok: bool
    handle: object = None      # opaque target handle (adapter-defined)
    revision: int = 0
    reason: str = ""           # the fail-before-delivery cause (non-editable/secret/selected/…)

@runtime_checkable
class DeliveryTarget(Protocol): ...   # the five methods, R.3 docstrings verbatim-anchored

class TargetUnits(str, Enum): UTF8_BYTES / CHARACTERS / UTF16_UNITS / EDITOR_MARKERS
def map_span(text, start_char, end_char, units) -> tuple[int, int]
def rendered_equal(old: str, new: str) -> bool
```

### Implementation Tasks (ordered)

```yaml
Task 1: CREATE voice_typing/bulk_delivery.py — docstring + taxonomy + Protocol
  - Module docstring (Mode A): the R.3 model summary (acquire/show/finalize/leave/cancel one-liners),
    the R.1 event-count law (insert=1, correct=1, zero-diff=0; typing/backspace chains FORBIDDEN here),
    "Bytes sent is not applied; unknown is not delivered", and the R.2 caution (transport probes are
    mechanism evidence only). Mirror audio_ducking.py's style.
  - ShowResult (4 str members), AcquireResult (frozen dataclass), DeliveryTarget Protocol with R.3
    docstrings per method (show's: ONE insert-or-replace ON the target's event loop, only if
    focus/caret/selection/ownership still match; finalize's: matching final ⇒ no edit, differing ⇒
    ONE replacement; leave/cancel per R.3).
  - NO implementation bodies beyond `...`.

Task 2: ADD the pure helpers to the same module
  - TargetUnits + map_span (identity for CHARACTERS after range validation; cumulative UTF-8 byte
    offsets; surrogate-aware UTF-16 units via len(ch); EDITOR_MARKERS → NotImplementedError;
    out-of-range → ValueError).
  - rendered_equal (" ".join(s.split()) on both; exact ==; docstring states the never-fold-case /
    never-strip-punctuation rule per R.1).

Task 3: CREATE tests/test_bulk_delivery.py (plain-function style, test_textproc.py pattern)
  - Taxonomy: exactly 4 members; str values == the PRD words; str-enum serialization.
  - rendered_equal matrix: identical; multi-space/strip/newline/NBSP-only diffs → True; case /
    trailing-period / word diffs → False; "" vs " " → True; "naïve  café", "a 😀 b" whitespace runs → True.
  - map_span: CHARACTERS identity; "héllo" span(1,2) → utf8 (1,3); "😀" → utf8 4 / utf16 2 / chars 1;
    "a😀b" span(0,3) → utf16 (0,4); EDITOR_MARKERS raises NotImplementedError; start>end/out-of-range
    raises ValueError.
  - Protocol: a minimal FakeTarget (five methods, canned results) satisfies isinstance(…, DeliveryTarget).
  - Do-not-touch guard: `for bad in ("type_text","press_backspace","make_backend","StreamingOutput"):
    assert not hasattr(bulk_delivery, bad)`; source-scan: the file text contains no
    "voice_typing.streaming" / "voice_typing.typing_backends" / "voice_typing.daemon" import.
  - Purity: importing the module adds no RealtimeSTT/torch/ctranslate2 to sys.modules (fresh
    subprocess check OR module-__dict__ scan).

Task 4: VALIDATE
  - timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_zero_diff_rewind.py -q
  - (optional) /home/dustin/.local/bin/ruff check voice_typing/bulk_delivery.py tests/test_bulk_delivery.py
  - git status --short == the two new files only.
```

### Implementation Patterns & Key Details

```python
# rendered_equal — the R.1 generalization (spacing guard only, then exact):
def rendered_equal(old: str, new: str) -> bool:
    return " ".join(old.split()) == " ".join(new.split())   # str.split() = Unicode whitespace incl. NBSP
#   "Hello world" vs "hello world" -> False (case is REAL). "Hi." vs "Hi" -> False (punct is REAL).

# map_span — count on the ORIGINAL string; surrogate-aware:
def _utf16_len(ch: str) -> int: return 2 if len(ch) == 2 else 1    # astral plane pairs
def map_span(text, start_char, end_char, units):
    if not (0 <= start_char <= end_char <= len(text)): raise ValueError(...)
    if units is TargetUnits.CHARACTERS: return (start_char, end_char)
    if units is TargetUnits.UTF8_BYTES: ...   # cumulative len(ch.encode("utf-8"))
    if units is TargetUnits.UTF16_UNITS: ...  # cumulative _utf16_len(ch)
    raise NotImplementedError("EDITOR_MARKERS mapping is adapter-owned (R.3)")

# Protocol method docstrings quote R.3's operative lines verbatim-anchored:
#   show: "one insert-or-replace executed ON the target's event loop … Returns
#          applied|unchanged|refused|unknown. Bytes sent is not 'applied'; 'unknown' is not 'delivered'."
```

### Integration Points

```yaml
CONSUMED BY (contracts, not code — zero wiring in this task):
  - P1.M3.T2.S1 controller: "imports DeliveryTarget/ShowResult/AcquireResult/rendered_equal; branches
                            on the taxonomy (UNKNOWN/REFUSED → disarm, never retry — R.5)"
  - M4.T2/T3 + M5 adapters: "implement DeliveryTarget; use map_span for units; call rendered_equal
                              before emitting any show() (zero-diff ⇒ UNCHANGED, zero events)"
  - M3.T3.S2 status surface: "reuses ShowResult's str values for delivery_state/delivery_reason"
NO config keys, NO daemon/streaming/textproc/typing_backends changes, NO feedback keys (d2 §4 is
T2/T3's surface). New module only.
```

## Validation Loop

### Level 1: Syntax + purity (immediate)
```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/bulk_delivery.py tests/test_bulk_delivery.py && echo OK
.venv/bin/python -c "import voice_typing.bulk_delivery as m; print(sorted(m.ShowResult.__members__))"
# expect: ['APPLIED', 'REFUSED', 'UNCHANGED', 'UNKNOWN']
grep -nE 'import (voice_typing\.)?(streaming|typing_backends|daemon)' voice_typing/bulk_delivery.py  # expect: no match
```

### Level 2: The unit suite (THE gate)
```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py -v
# Expected: all pass (fast, no CUDA/daemon/subprocess).
timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_zero_diff_rewind.py -q
# Expected: 0 failed — the second file proves streaming's guard is untouched.
```

### Level 3: Contract-shape probe (the consumers' view)
```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing import bulk_delivery as bd
class FakeTarget:                      # the minimal conforming adapter
    def acquire(self): return bd.AcquireResult(ok=True, handle=object(), revision=7)
    def show(self, session, utterance, seq, expected_revision, span): return bd.ShowResult.APPLIED
    def finalize(self, session, utterance, seq, expected_revision, span): return bd.ShowResult.UNCHANGED
    def leave(self): ...
    def cancel(self): return bd.ShowResult.REFUSED
assert isinstance(FakeTarget(), bd.DeliveryTarget)            # runtime_checkable conformance
assert bd.rendered_equal("Hello  world", "Hello\nworld") is True
assert bd.rendered_equal("Hello world", "hello world") is False
assert bd.map_span("a😀b", 0, 3, bd.TargetUnits.UTF16_UNITS) == (0, 4)
assert not any(hasattr(bd, a) for a in ("type_text", "press_backspace", "make_backend"))
print("L3 OK: contract shape + zero-diff + units + no-typing-surface")
PY
```

### Level 4: Scope guard
```bash
git status --short   # expect exactly: ?? voice_typing/bulk_delivery.py  ?? tests/test_bulk_delivery.py
# Any M to streaming.py/textproc.py/typing_backends.py/config.py/daemon.py = scope violation.
```

## Final Validation Checklist

- [ ] L1–L3 green (taxonomy values, Protocol conformance, zero-diff matrix, map_span Unicode, purity).
- [ ] `tests/test_zero_diff_rewind.py` still passes (streaming untouched).
- [ ] The module docstring carries the R.1/R.2/R.3 summary (Mode A); method docstrings anchor R.3's operative lines.
- [ ] Only the two new files in git status.
- [ ] No forbidden attrs/imports (guard + source-scan tests).

## Anti-Patterns to Avoid

- ❌ Don't implement adapter/controller logic here — contracts + the two pure rules only (Critical #1).
- ❌ Don't import or call streaming/typing_backends/daemon — and don't just promise it; ship the guard + source-scan tests (Critical #2).
- ❌ Don't casefold/strip punctuation in rendered_equal — spacing normalization ONLY (Critical #3).
- ❌ Don't map units via a normalized copy — count on the original string (Critical #4).
- ❌ Don't implement EDITOR_MARKERS — raise; it's adapter-owned (Critical #4).
- ❌ Don't touch streaming's existing exact-equal guard — generalize alongside, don't modify (test_zero_diff_rewind must stay green).
- ❌ Don't add config keys / feedback fields / daemon wiring — those belong to T2/T3 (d2 §4).
- ❌ Don't run mypy (not installed); full paths + timeout 60 wrappers throughout (Gotcha #7).

---

**Confidence Score: 9/10** — the module is pure and self-contained with zero unlanded dependencies; every signature, enum value, and helper semantic is pinned to R.3/R.1 wording; the repo's protocol-module precedent (audio_ducking.py) fixes the style; the do-not-touch law is enforced by tests; and validation (incl. re-running the existing zero-diff characterization) is deterministic and fast. The −1 reserves signature-drift pressure from consumers (mitigated by quoting R.3 verbatim in the docstrings so later tasks can reconcile against the same source).

# Research — P1.M3.T1.S1 contracts module: DeliveryTarget Protocol + result taxonomy + zero-diff guard

Ground truth verified 2026-11-25: d2_bulk_delivery_map.md §3 (the do-not-touch surface), PRD §4.2sexies
R.1–R.3, streaming.py/textproc.py surfaces, the protocol-module precedent (audio_ducking.py), the
existing zero-diff characterization tests, and the parallel task. This is the FIRST D2 code subtask:
a pure, stdlib-only contracts module consumed by P1.M3.T2.S1 (controller) and the M4/M5 adapters.

---

## 1. What this module IS and IS NOT

IS: the R.3 contract surface, pure + importable everywhere — `DeliveryTarget` Protocol, the
`applied|unchanged|refused|unknown` result taxonomy, the units-mapping contract (with a pure helper
for the three mechanical units), and the generalized zero-diff guard `rendered_equal`. Mode A
docstring carries the R.2/R.3 summary.

IS NOT: any implementation. NO adapter code, NO controller/queue logic (that's T2), NO import of
`voice_typing.streaming` / `typing_backends` / `daemon` — d2 §3: bulk code must NOT call
`type_text`/`press_backspace`/`make_backend`/`StreamingOutput.*` and must not expose any typing
fallback. Shared-state traps to avoid by construction (d2 §3): never share `_stream` state (the
engine commits under `_on_final_lock`; daemon.py:1738-1741 reads `_stream.committed` for the prompt
push; feedback mirrors ride the streaming paths — bulk state gets its OWN keys per d2 §4).

## 2. The precedent to mirror: voice_typing/audio_ducking.py (M2.T2, landed)

`from typing import Protocol, runtime_checkable` + `@runtime_checkable class DuckBackend(Protocol)`
— the module-style for a contracts module in this repo (pure stdlib, protocol + docstring contract,
unit tests, zero heavy imports). `bulk_delivery.py` follows it exactly.

## 3. The existing pieces the module generalizes (do not duplicate, do not touch)

- **The exact-equal commit guard**: streaming.py already no-ops an identical final (pinned by
  `tests/test_zero_diff_rewind.py` T1 — "an identical final emits ZERO keystrokes"). The new
  `rendered_equal` GENERALIZES it per R.1: compare RENDERED text after the spacing guard — whitespace
  runs collapse (the repo idiom: `" ".join(s.split())`, textproc clean() step 1) and prose line breaks
  normalize to a space (R.3) — then EXACT compare. NO case folding, NO punctuation stripping: "real
  case/punctuation/word differences are never declared equal" (R.1). Streaming's guard stays as-is;
  the pure function is the reusable contract for the bulk path.
- **The units rule (R.3)**: "the adapter maps text positions to the target's own units (UTF-8 bytes,
  characters, UTF-16 units, or editor markers); never slice via a lowercased/normalized copy."
  Mechanical for 3 of the 4 units → a pure helper `map_span(text, start_char, end_char, units)`
  operating ONLY on the original string; EDITOR_MARKERS is adapter-owned (raises).

## 4. The R.3 contract wording the signatures must encode (verbatim source)

- `acquire`: "bind the SPECIFIC editable field… Return an opaque target handle + revision. Fail
  BEFORE delivery for non-editable, password/secret, selected, or unidentified fields."
- `show(session, utterance, seq, expected_revision, complete rendered span)`: "one insert-or-replace
  executed ON the target's event loop, only if focus, caret, selection, and ownership still match.
  Returns `applied | unchanged | refused | unknown`. Bytes sent is not 'applied'; 'unknown' is not
  'delivered'."
- `finalize`: matching final ⇒ NO further edit; differing final ⇒ ONE replacement of verified owned
  text; no-partial final ⇒ single insert + counts as a missed live update.
- `leave`/`cancel`: leave = stop preserving the last visible words, NO post-stop writes; cancel =
  ONE operation removing the owned fragment, drop buffered audio, keep listening.
- R.1 event-count law for the docstring: insertion = 1, correction = 1, zero-diff = 0; synthesized
  per-character typing and Backspace chains FORBIDDEN in this mode; no fallback to §4.3 backends.
- R.2 caution line for the docstring: transport probes are mechanism evidence only — "A passing
  transport probe NEVER flips any of these to 'passed'".

## 5. Types (pinned; keep simple + stdlib)

- `ShowResult(str, Enum)`: APPLIED/"applied", UNCHANGED/"unchanged", REFUSED/"refused",
  UNKNOWN/"unknown" — str-valued so it serializes straight into status/log lines (R.5's
  delivery_state/delivery_reason surface).
- `AcquireResult` frozen dataclass: `ok: bool`, `handle: object = None` (opaque), `revision: int = 0`,
  `reason: str = ""` — one matchable shape for both the bound and every fail-before-delivery case.
- `DeliveryTarget` method args: `session: int` (arm generation), `utterance: str` (decode-source
  identity, R.5), `seq: int` (monotonic per utterance), `expected_revision: int`, `span: str`
  (complete rendered span). `finalize` mirrors show's args. `leave() -> None`, `cancel() -> ShowResult`.
- `TargetUnits(str, Enum)`: UTF8_BYTES/CHARACTERS/UTF16_UNITS/EDITOR_MARKERS.
- `map_span(text, start_char, end_char, units) -> tuple[int, int]`: chars = identity (validated in
  range); UTF8_BYTES = cumulative `len(ch.encode("utf-8"))` offsets; UTF16_UNITS = surrogate-pair-
  aware (`len(ch) == 2` astral → 2 units); EDITOR_MARKERS → NotImplementedError. Pure; operates on
  the ORIGINAL text only (the never-normalize rule).
- `rendered_equal(old, new) -> bool`: `_render_norm = " ".join(s.split())` on both, then `==`.
  Python `str.split()` splits on Unicode whitespace (incl. NBSP) — collapse+strip in one idiom.

## 6. Consumers (the contract's customers — do not break their expectations)

- P1.M3.T2.S1 (controller): imports `DeliveryTarget`, `ShowResult`, `AcquireResult`, `rendered_equal`.
- M4.T2/T3 (IM-v2 adapter) + M5 (pi editor adapter): implement `DeliveryTarget`; use `map_span`.
- M3.T3.S2 (status surface): reuses the str values for `delivery_state`/`delivery_reason`.

## 7. Tests (pure, tests/test_textproc.py plain-function style; no CUDA/daemon/subprocess)

`tests/test_bulk_delivery.py`: taxonomy (exactly 4 values; str values = the PRD words);
rendered_equal (identical→True; whitespace-run/strip diffs→True; newline-vs-space→True; NBSP→True;
case diff→False; trailing-period diff→False; word diff→False; empty vs whitespace-only→True;
Unicode: "naïve  café", emoji astral spans); map_span (identity; é 2-byte utf8; 😀 4-byte/2-utf16;
mixed spans; EDITOR_MARKERS raises; out-of-range raises); protocol shape (a minimal FakeTarget is
instanceof DeliveryTarget via runtime_checkable); the do-not-touch guard (module has NO
type_text/press_backspace/make_backend/StreamingOutput attrs) + a source-scan that the file never
imports voice_typing.streaming/typing_backends/daemon.

## 8. Tooling/scope

Files: `voice_typing/bulk_delivery.py` (NEW) + `tests/test_bulk_delivery.py` (NEW). Nothing else.
Parallel P1.M2.T4.S1 (duck default flip) edits config.py/config.toml/test_config.py — disjoint.
Validation: `timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py
tests/test_zero_diff_rewind.py -q` (the latter proves streaming untouched). ruff optional
(/home/dustin/.local/bin/ruff); mypy NOT installed.

# PRP — P1.M1.T3.S2: Define versioned message validation and shared vectors

## Goal

**Feature Goal**: Turn PRD §4.8.1 B's v1 wire table into an **executable validation contract** — strict,
side-effect-free validators for every v1 request and event, the native error codes and end reasons as
exported constants, the §A UTF-8 code-point-safe 4 KiB seed truncation, and the §C splice-padding rule as a
pure function — **added to S1's `voice_typing/editor_protocol.py`** (codec) without touching S1's framing
symbols; plus **ONE language-neutral vector file** `tests/fixtures/editor_v1.json` that is the shared
cross-language oracle for Python now and the TypeScript (Pi) and Lua (Neovim) adapters later. No second
wire schema, no implicit whitespace normalization, no socket or editor dependency — pure functions over
dicts/strings.

**Deliverable** (1 source file edited — S1's new module, appended to; 1 fixture file + 1 test file created):
1. `voice_typing/editor_protocol.py` — **APPEND** (S1 creates the file in parallel; never rewrite its
   `MAX_FRAME_BYTES`/`FrameError`/`FrameReader`/`encode_line`): `ProtocolVersion`, `PROTOCOL_VERSION`,
   `NATIVE_ERROR_CODES`, `END_REASONS`, `CONTEXT_REASONS`, `MAX_CONTEXT_BYTES`, `MAX_FINAL_TEXT_BYTES`,
   `OPEN_DELIMITERS`, `CLOSE_PUNCTUATION`, `UUID_V4_RE`; `ProtocolError(code, detail)`;
   `is_uuid_v4(s)`; `utf8_len(s)`; `has_lone_surrogates(s)`; `truncate_utf8_suffix(text, max_bytes)`
   (newest-N-bytes, code-point-aligned); `validate_request(obj) -> dict` and `validate_event(obj) -> dict`
   (return the validated object, raise `ProtocolError`); `request_kind(obj)`; `splice_padding(before,
   text, after) -> tuple[str, str]`; `native_error_reply(code) -> dict`.
2. `tests/fixtures/editor_v1.json` — the shared vectors (frame/request/event/pad/truncate cases).
3. `tests/test_editor_protocol_vectors.py` — loads the fixture and asserts every case against the
   validators (the Python consumer of the oracle; TS/Lua consumers are P1.M2.T1.S2 / P1.M2.T2.S1).

**Success Definition**:
- (a) Every v1 frame in §4.8.1 B validates: the 5 request shapes and 6 event shapes accept their canonical
  forms and reject — with the spec's code — wrong types, missing/unknown fields, non-v4/non-canonical ids,
  non-positive/bool seqs, `version != 1`, oversized `context`/`text`, lone surrogates.
- (b) Error-code precedence is deterministic and pinned: shape → `unsupported_version` → `too_large`
  for `editor-start` (a wrong-*type* version is a shape error; a right-type wrong value is
  `unsupported_version`). `busy`/`duplicate_id` are NOT produced here (state decisions — T3.S3/T3.S4).
- (c) `truncate_utf8_suffix` never splits a code point (2-byte and 4-byte straddles, exact fit, CJK) and
  keeps the NEWEST bytes; `splice_padding` reproduces the PRD's two worked examples exactly and treats
  whitespace by explicit code-point classification (no `\s`, no `locale`, no normalization).
- (d) The fixture round-trips through `json.loads` with real Unicode preserved, names every case stably,
  stores invalid-UTF-8 frames as `wire_hex`, and every case passes against the Python oracle.
- (e) S1's symbols are byte-identical (this task only appends); S1's `tests/test_editor_protocol.py`
  is untouched; `timeout 120 .venv/bin/python -m pytest tests/test_editor_protocol_vectors.py -q` → 0
  failures; `git diff --name-only` ⊆ {editor_protocol.py, the fixture, the new test file}.

## User Persona

**Target User**: the implementers of the owner connection pump (P1.M1.T3.S3), sequenced offers
(P1.M1.T4.S2), and the Pi/Neovim adapters (P1.M2.T1.S2, T1.S4, T2.S1, T2.S3). **Use Case**: each
re-implements message checks in another language and needs (1) an unambiguous, ordered rule set and
(2) the same pass/fail vectors so a divergence is a named case, not a debugging session. **Pain Points
Addressed**: today the v1 rules live only in PRD prose; cross-language whitespace (`\s` vs `%s`),
permissive UUID parsing, JSON-escaping byte inflation, and UTF-8 boundary cuts are exactly where three
independent implementations silently disagree.

## Why

- **PRD §4.8.1 B is normative**: "reject invalid UTF-8, malformed frames, invalid types, oversized
  fields, or unsupported protocol before arming" with fixed codes `invalid_request | too_large |
  unsupported_version | busy | duplicate_id`. S1 (parallel, the framing contract) delivers the UTF-8/
  frame/JSON layer and explicitly leaves "types/fields/versioning" to this task.
- **The contract's OUTPUT is six downstream tasks.** Without a single oracle, TS and Lua would each
  re-derive the rules from prose. The architecture doc is explicit: "Lua `%s` and JS `\s` cannot be
  assumed equivalent" — the §C padding rule MUST be an explicit scalar classification shared verbatim.
- **Probes found three latent cross-language bugs the vectors must pin** (research §3): Python's
  `uuid.UUID()` accepts `{…}`, `urn:uuid:…`, uppercase and hyphen-less ids (a loose validator would admit
  non-canonical ids two languages disagree on); 4,096 `"` chars become **8,279** wire bytes after JSON
  escaping (so the 4 KiB limits are on UTF-8 *text* bytes, not frame bytes); and the "strip trailing
  continuation bytes" truncation rule is WRONG (`"a"*4094+"é"` cut at 4096 ends on the LEAD byte `0xC3`).
- **Scope discipline.** Validators are pure and stateless. Reservation/busy, timers, socket writes,
  recovery and adapter code belong to T3.S3/T3.S4/T4.*/T5.*/P1.M2.*. Nothing here touches `daemon.py`.

## What

Append the validation contract to `voice_typing/editor_protocol.py`; add the shared vector fixture and
its Python consumer test. No behavior change for existing commands (nothing imports the new symbols yet
except tests; T3.S3/T4.S2 wire them).

### Success Criteria

- [ ] `editor_protocol.py` exports the constants, `ProtocolError`, the two validators, `is_uuid_v4`,
      `utf8_len`, `has_lone_surrogates`, `truncate_utf8_suffix`, `splice_padding`, `native_error_reply`,
      `request_kind` — each with a Mode A docstring naming the §4.8.1 clause it encodes.
- [ ] `validate_request` accepts `editor-start{version:1,id,context}`, `ping{id}`, `applied{id,seq≥1}`,
      `stop|cancel|lost{id}`; rejects everything else with `ProtocolError.code ∈ NATIVE_ERROR_CODES`
      minus the state codes.
- [ ] `validate_event` accepts `starting/listening/pong/final/finishing/ended` with their exact fields;
      `ended.reason ∈ END_REASONS`; `context_reason ∈ CONTEXT_REASONS` only when `context_seeded` is False.
- [ ] Strictness pinned: `seq: true` rejected (bool ≠ int); `id` uppercase/braced/urn/hyphen-less/non-v4
      rejected; unknown top-level key rejected; `version: "1"` rejected as shape; `version: 2` →
      `unsupported_version`; `context` 4097 bytes → `too_large`.
- [ ] `truncate_utf8_suffix("a"*3+"é"+"z"*4096, 4096) == "z"*4096` (a 2-byte char straddling the window start is
      dropped); `("a"*3+"é"+"z"*4094) == "é"+"z"*4094` (fits); every result decodes cleanly and is ≤ 4096 B.
- [ ] `splice_padding("hello", "there", ", world") == ("", " ")`; `("hello","there","world") == (" "," ")`.
- [ ] `tests/fixtures/editor_v1.json` exists, `json.loads`-clean, with ≥ 40 named cases across the five
      kinds; `tests/test_editor_protocol_vectors.py` parametrizes over it and passes.
- [ ] S1's four symbols unchanged; S1's test file untouched; vector suite green; diff ⊆ the three files.

## All Needed Context

### Context Completeness Check

_Pass._ Every rule is given as a verbatim, probe-validated implementation; the spec clauses are cited by
section and line; the vector file's schema and a representative subset are given verbatim with the exact
expected values; the downstream consumers and the parallel sibling's file boundary are named. Pure
stdlib; no sockets, no editor, no daemon import.

### Documentation & References

```yaml
# MUST READ — the locked design (D1–D9), the three probe findings, scope, tooling
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S2/research/v1_validation_and_vectors_design.md
  why: "§2 the v1 contract extracted from §4.8.1 B. §3 the decisions: validation layers + precedence (D1),
        strict types incl. the uuid.UUID looseness and bool-is-int (D2), text-bytes vs wire-bytes (D3),
        the code-point truncation bug + correct rule (D4), the padding algorithm (D5), event symmetry (D6),
        no-echo errors (D7), the single-vector-file convention (D8), no second schema (D9). §4 scope."
  critical: "D4 is load-bearing: the naive continuation-byte strip leaves a lead byte and raises
            UnicodeDecodeError — the PRP's helper walks back to the lead and drops the partial sequence."

# THE SPEC — PRD §4.8.1 (A: seed; B: wire v1; C: padding)
- file: PRD.md
  why: "§4.8.1 B (prd_snapshot.md:448-482): the frame table (9 shapes), the 5 native error codes, the 9
        end reasons, '32 KiB wire limit per request and live event', '4 KiB UTF-8 per final', 'seq start
        at 1, monotonic', 'context_reason if unseeded'. §4.8.1 A (:440-446): 'at most the newest 4 KiB
        of text before it ... truncated on a UTF-8 code-point boundary'. §4.8.1 C (:476): the padding
        rule with the two worked examples."
  critical: "'No target name/path, editor buffer contents beyond the seed, or output-mode option' is WHY
             the schema is closed (unknown keys → invalid_request). 'An old daemon's unknown-command reply
             means unsupported' → this module never emits `unsupported_version` for a MISSING version on
             non-start commands (only editor-start carries version)."

# THE UPSTREAM CONTRACT — S1 (parallel; creates the module this task appends to)
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S1/PRP.md
  why: "Defines MAX_FRAME_BYTES, FrameError(reason,detail), FrameReader, encode_line verbatim. Its
        Integration Points: 'P1.M1.T3.S2 validates the DICT the handler parsed; consumes FrameError
        reason codes + encode_line.' Its frame-level cases (invalid UTF-8, oversize, split/coalesced,
        partial EOF) are the `frame` kind in the vector file — recorded here so TS/Lua get them too."
  gotcha: "S1 was NOT on disk at research time. Task 0 gates on its presence; if absent, STOP and report
           (do not author S1's module). If present, APPEND ONLY — the L1 gate diffs S1's symbols."

# THE ARCHITECTURE NOTES the item names
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Proposed voice_typing/editor_protocol.py owns codec, lease and serialized socket writer' — this
        task adds ONLY the codec/validation half. 'do not echo arbitrary request fragments in reasons'
        → ProtocolError.detail names the field + violation class, never the value. Timers/deadlines and
        editor_session.py are explicitly other tasks'."
- docfile: plan/009_ef3b49b0fc0d/architecture/editor_apis.md
  why: "'Explicit Unicode whitespace/delimiter table or scalar classification must match the PRD across
        languages; Lua %s and JS \\s cannot be assumed equivalent' — the reason D5 is a pure code-point
        function with explicit tables that TS (`codePointAt`) and Lua (`utf8.codepoint`) can mirror."
  critical: "Pi columns are JS string offsets (UTF-16) and Neovim's are UTF-8 bytes — the PADDING output
             is plain text ('' or ' '); unit mapping is the adapters' job (T1.S4/T2.S3), NOT this task's."

# THE TEST CONVENTIONS TO FOLLOW
- file: tests/conftest.py
  why: "Line 1-19: tests import voice_typing.config eagerly but keep daemon imports lazy. This task's
        module is stdlib-only, so a plain top-level `from voice_typing import editor_protocol as ep` is
        fine (import purity preserved). tests/fixtures/ already exists (ime_g3_browser_field.html,
        input-method-unstable-v2.xml) — the JSON vector file joins it."
  pattern: "Fixture path: Path(__file__).resolve().parent / 'fixtures' / 'editor_v1.json'. Parametrize
            with pytest.mark.parametrize over the case list, ids=[case['name']] so failures name vectors."
- file: voice_typing/bulk_delivery.py
  why: ":77 `class ShowResult(str, Enum)` — the repo's code-set convention (`str, Enum`). Use the same
        shape for NATIVE_ERROR_CODES / END_REASONS / CONTEXT_REASONS; `bulk_controller.py:132` shows the
        `@dataclass(frozen=True, slots=True)` convention for small value types (ProtocolError is an
        Exception, so a plain Exception subclass with attributes, mirroring S1's FrameError)."
  gotcha: "pyproject has NO schema library (jsonschema/pydantic) and NO typing_extensions — stdlib only.
          Do NOT add a dependency."

# THE TEST PLAN ROWS THIS ORACLE SERVES
- docfile: plan/009_ef3b49b0fc0d/prd_snapshot.md
  why: "§6 T10a (:575): '4 KiB/32 KiB boundaries, invalid UTF-8 and JSON, split/coalesced frames and
        partial EOF' — the `frame` + `truncate` vector kinds. T10b (:576): 'wrong id/seq, duplicate/
        stale/identity-less finals' — the `event` reject vectors. T10c (:577): 'Use shared protocol
        vectors ... multiple finals with spacing' — the `pad` vectors consumed by BOTH adapters."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/editor_protocol.py     # S1 (parallel) creates: MAX_FRAME_BYTES, FrameError, FrameReader,
#                                   # encode_line. NOT on disk at research time.        ← APPEND (this task)
tests/fixtures/                      # exists: ime_g3_browser_field.html, input-method-unstable-v2.xml
tests/test_editor_protocol.py        # S1 (parallel) creates — DO NOT TOUCH.
tests/conftest.py                    # eager config imports OK; daemon lazy — this task needs neither.
# No editor_session.py yet (T3.S3). No integrations/ yet (P1.M2). pyproject: stdlib + pytest only.
```

### Desired Codebase tree with files to be added

```bash
voice_typing/editor_protocol.py            # APPEND §"v1 message validation" (constants, ProtocolError,
#                                          # validators, helpers). S1's framing section byte-identical.
tests/fixtures/editor_v1.json              # CREATE: the shared cross-language vectors (one file, 5 kinds).
tests/test_editor_protocol_vectors.py      # CREATE: Python consumer — loads the fixture, asserts all cases.
# No daemon.py / ctl.py / config / integrations changes. No new dependency. No JSON-Schema/codegen.
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — APPEND, NEVER REWRITE. S1 lands editor_protocol.py in parallel. Put this task's code
# below a banner "# --- v1 message validation (P1.M1.T3.S2; PRD §4.8.1 B/C) ---". The L1 gate asserts
# S1's four symbols are unchanged (inspect.signature + source grep). If the file is absent, STOP (Task 0).

# CRITICAL #2 — uuid.UUID() IS TOO LOOSE (probe). It ACCEPTS '{…}', 'urn:uuid:…', UPPERCASE, and
# hyphen-less 32-hex forms. The wire id MUST be the canonical lowercase 8-4-4-4-12 form with version
# nibble '4' and variant nibble in [89ab]. Use the regex — never uuid.UUID() for validation.

# CRITICAL #3 — bool IS int IN PYTHON. isinstance(True, int) == True, so a JSON `true` would pass a
# naive seq/version check. Require `type(x) is int` (excludes bool) for seq and version.

# CRITICAL #4 — TEXT-BYTE LIMITS, NOT WIRE-BYTE LIMITS (probe). 4,096 '"' chars → 8,279 wire bytes
# after JSON escaping. MAX_CONTEXT_BYTES / MAX_FINAL_TEXT_BYTES (4096) are enforced on
# len(s.encode('utf-8')) — S1's 32 KiB frame bound applies independently on top.

# CRITICAL #5 — LONE SURROGATES CRASH THE ENCODER (probe). json.dumps(ensure_ascii=False).encode()
# raises UnicodeEncodeError on '\ud800'. A str field that passed json.loads can still hold one (from
# "\ud800" escapes). has_lone_surrogates(s) must run BEFORE any size check/encode → invalid_request.

# CRITICAL #6 — THE CODE-POINT TRUNCATION RULE (probe-caught bug). "Strip trailing 0x80-prefixed bytes"
# is WRONG: 'a'*4094+'é' cut at 4096 ends on the LEAD byte 0xC3 (its continuation is byte 4097) →
# UnicodeDecodeError on decode. Correct: walk back over continuation bytes to the lead, derive the
# expected length from the lead (0xC0-0xDF→2, 0xE0-0xEF→3, 0xF0-0xF7→4), drop the sequence if incomplete.
# For the newest-SUFFIX seed, drop LEADING continuation bytes (a partial seq at the START of the cut).

# CRITICAL #7 — PRECEDENCE IS PART OF THE CONTRACT. editor-start: (1) shape/types → invalid_request;
# (2) version value → unsupported_version; (3) context bytes → too_large. A wrong-TYPE version is (1).
# TS and Lua MUST use the same order — the vector file pins it (one case per layer, same input family).

# CRITICAL #8 — busy / duplicate_id ARE NOT PRODUCED HERE. They depend on reservation state (T3.S3/T3.S4).
# This module exports the codes (so all languages share the spelling) but no validator returns them.

# CRITICAL #9 — NO ECHO IN ERRORS. ProtocolError.detail names the FIELD and the violation class only
# ('field seq: expected int >= 1'), never the value. Context can be private editor text; a 4 KiB final
# is transcript. native_error_reply(code) emits {"ok": False, "error": "<code>"} and nothing else.

# CRITICAL #10 — PADDING IS OVER CODE POINTS, EXPLICITLY. Whitespace = ch.isspace() per code point (this
# is Python's Unicode whitespace; TS/Lua consumers get vectors for tab, '\n', NBSP U+00A0, ideographic
# space U+3000 so they implement the SAME set, not \s / %s). Never normalize, strip, or collapse the
# final. Empty final text → ('', ''). Empty before/after → that side gets no pad.

# GOTCHA #11 — THE FIXTURE CANNOT HOLD INVALID UTF-8. JSON strings are Unicode; store raw-byte frames
# as hex ("wire_hex") and have the consumer bytes.fromhex them before feeding FrameReader. Everything
# else is stored as real Unicode (ensure_ascii=False when WRITING the file; json.loads keeps it).

# GOTCHA #12 — FULL PATHS + two timeouts: timeout 120 .venv/bin/python -m pytest <file> -q (bash ≥ 180).
# pytest only (no ruff/mypy). Never bare python/pytest/uv. Do NOT run test_daemon.py (nothing changed).

# GOTCHA #13 — DOWNSTREAM FILES ARE NOT YOURS. Do not create editor_session.py, touch daemon.py/_dispatch,
# or add integrations/. T3.S3/T4.S2/P1.M2.* import these symbols — keep names EXACTLY as specified.
```

## Implementation Blueprint

### Data models and structure

Stdlib only. Code sets are `str, Enum` (repo convention); `ProtocolError` is an `Exception` subclass
mirroring S1's `FrameError` (attributes `code`, `detail`). Validators return the validated `dict`
(unchanged, no coercion — D2) or raise. No pydantic/jsonschema (none installed; the spec forbids a
second schema).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREREQUISITE GATE — S1 has landed
  - RUN: test -f voice_typing/editor_protocol.py && grep -c 'class FrameReader\|def encode_line\|MAX_FRAME_BYTES\|class FrameError' voice_typing/editor_protocol.py
  - EXPECT: file exists and grep ≥ 4. Else STOP and report "P1.M1.T3.S1 not landed" (do not author it).

Task 1: APPEND to voice_typing/editor_protocol.py (verbatim — PROBE-VALIDATED helpers; the module docstring's
        first paragraph should gain one sentence: "Also holds the v1 message validation contract (PRD
        §4.8.1 B/C) and the §C splice-padding + §A code-point-safe seed helpers (P1.M1.T3.S2)." — append
        that sentence ONLY if S1's docstring is present; do not reflow its text.)
  - BANNER + CONTENT:
    # --- v1 message validation (P1.M1.T3.S2; PRD §4.8.1 B wire, §4.8.1 A seed, §4.8.1 C padding) ---
    # Pure, stateless validators over the DICT the handler parsed (framing/UTF-8/JSON are handled above).
    # They never raise anything but ProtocolError, never coerce, never echo field values in errors.
    # Reservation state (busy / duplicate_id) is NOT decided here — see P1.M1.T3.S3 / T3.S4.
    import enum
    import re

    PROTOCOL_VERSION: int = 1   # §4.8.1 B: the only version; "version":2 → unsupported_version

    MAX_CONTEXT_BYTES: int = 4 * 1024      # §4.8.1 A: newest 4 KiB of pre-caret text (UTF-8, code-point aligned)
    MAX_FINAL_TEXT_BYTES: int = 4 * 1024   # §4.8.1 B: "4 KiB UTF-8 per final"

    class NativeErrorCode(str, enum.Enum):
        """§4.8.1 B native error codes. busy/duplicate_id are STATE decisions (T3.S3/T3.S4), emitted elsewhere."""
        INVALID_REQUEST = "invalid_request"
        TOO_LARGE = "too_large"
        UNSUPPORTED_VERSION = "unsupported_version"
        BUSY = "busy"               # not produced by this module's validators
        DUPLICATE_ID = "duplicate_id"   # not produced by this module's validators

    class EndReason(str, enum.Enum):
        """§4.8.1 B `ended` reasons."""
        STOPPED = "stopped"; IDLE = "idle"; CANCELLED = "cancelled"; TARGET_LOST = "target_lost"
        DISCONNECTED = "disconnected"; TIMEOUT = "timeout"; DELIVERY_FAILED = "delivery_failed"
        LOAD_FAILED = "load_failed"; SHUTDOWN = "shutdown"

    class ContextReason(str, enum.Enum):
        """§4.8.1 A: only when context_seeded is false."""
        EMPTY = "empty"; DISABLED = "disabled"; UNAVAILABLE = "unavailable"

    NATIVE_ERROR_CODES = frozenset(c.value for c in NativeErrorCode)
    END_REASONS = frozenset(c.value for c in EndReason)
    CONTEXT_REASONS = frozenset(c.value for c in ContextReason)

    # §C splice-edge tables — EXPLICIT, so TS/Lua mirror the same scalars (never \s or %s).
    OPEN_DELIMITERS = "([{"
    CLOSE_PUNCTUATION = ")]},.!?;:"

    # Canonical lowercase RFC 4122 v4: 8-4-4-4-12, version nibble 4, variant nibble 8/9/a/b.
    # (uuid.UUID() is deliberately NOT used: it accepts braces, urn:, uppercase and hyphen-less forms.)
    UUID_V4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

    class ProtocolError(Exception):
        """A v1 validation failure. `code` ∈ NATIVE_ERROR_CODES; `detail` names field + class, NEVER the value."""

        def __init__(self, code: str, detail: str = "") -> None:
            super().__init__(code)
            self.code = code
            self.detail = detail

    def native_error_reply(code: str) -> dict:
        """The wire failure reply for a rejected FIRST request: {"ok": False, "error": "<code>"} (+ EOF by caller)."""
        return {"ok": False, "error": code}

    def is_uuid_v4(value: object) -> bool:
        """True iff `value` is the canonical lowercase text form of a UUIDv4 (strict; no coercion)."""
        return isinstance(value, str) and UUID_V4_RE.match(value) is not None

    def utf8_len(text: str) -> int:
        """UTF-8 byte length — the unit of every §4.8.1 size limit (text bytes, NOT JSON-escaped wire bytes)."""
        return len(text.encode("utf-8"))

    def has_lone_surrogates(text: str) -> bool:
        """True if any code point is a lone (unpaired) UTF-16 surrogate — such a str cannot be UTF-8 encoded."""
        return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)

    def _lead_len(byte: int) -> int:
        """Expected UTF-8 sequence length from a lead byte (1 for ASCII)."""
        if byte < 0x80: return 1
        if byte < 0xC0: return 1          # continuation byte passed as lead: treat as 1 (caller walks back first)
        if byte < 0xE0: return 2
        if byte < 0xF0: return 3
        return 4

    def _drop_partial_tail(raw: bytes) -> bytes:
        """Drop a trailing INCOMPLETE UTF-8 sequence (the cut landed inside a multi-byte character)."""
        i = len(raw) - 1
        while i >= 0 and (raw[i] & 0xC0) == 0x80:   # walk back over continuation bytes to the lead
            i -= 1
        if i >= 0 and len(raw) - i < _lead_len(raw[i]):
            return raw[:i]
        return raw

    def truncate_utf8_suffix(text: str, max_bytes: int = MAX_CONTEXT_BYTES) -> str:
        """The NEWEST ≤max_bytes of `text`, cut on a UTF-8 code-point boundary (§4.8.1 A seed rule).

        Keeps the suffix (text nearest the caret); if the cut lands inside a multi-byte character the
        WHOLE partial leading sequence is dropped, so the result always decodes cleanly. ≤ max → unchanged.
        """
        raw = text.encode("utf-8")
        if len(raw) <= max_bytes:
            return text
        cut = raw[-max_bytes:]
        k = 0
        while k < len(cut) and (cut[k] & 0xC0) == 0x80:   # drop leading continuation bytes (partial seq)
            k += 1
        return cut[k:].decode("utf-8")

    def _require_str(obj: dict, key: str, *, allow_empty: bool = True) -> str:
        if key not in obj:
            raise ProtocolError("invalid_request", f"missing field {key!r}")
        value = obj[key]
        if not isinstance(value, str):
            raise ProtocolError("invalid_request", f"field {key!r}: expected string")
        if has_lone_surrogates(value):
            raise ProtocolError("invalid_request", f"field {key!r}: lone surrogate")
        if not allow_empty and value == "":
            raise ProtocolError("invalid_request", f"field {key!r}: expected non-empty string")
        return value

    def _require_id(obj: dict) -> str:
        value = _require_str(obj, "id", allow_empty=False)
        if not is_uuid_v4(value):
            raise ProtocolError("invalid_request", "field 'id': expected canonical UUIDv4")
        return value

    def _require_int(obj: dict, key: str, *, minimum: int) -> int:
        if key not in obj:
            raise ProtocolError("invalid_request", f"missing field {key!r}")
        value = obj[key]
        if type(value) is not int:          # bool is an int subclass in Python — JSON true must NOT pass
            raise ProtocolError("invalid_request", f"field {key!r}: expected int")
        if value < minimum:
            raise ProtocolError("invalid_request", f"field {key!r}: expected int >= {minimum}")
        return value

    def _reject_unknown(obj: dict, allowed: set) -> None:
        extra = sorted(set(obj) - allowed)
        if extra:
            raise ProtocolError("invalid_request", f"unknown field {extra[0]!r}")

    # cmd → (allowed fields, field spec). A CLOSED schema: §4.8.1 B forbids target names, buffer text
    # beyond the seed, and output-mode options in editor-start; unknown keys are invalid_request.
    _REQUEST_SPECS: dict = {
        "editor-start": {"version", "id", "context"},
        "ping": {"id"},
        "applied": {"id", "seq"},
        "stop": {"id"},
        "cancel": {"id"},
        "lost": {"id"},
    }
    _POST_START_CMDS = frozenset({"ping", "applied", "stop", "cancel", "lost"})

    def request_kind(obj: object) -> str | None:
        """The cmd name if `obj` is a dict with a known native cmd string, else None (no validation)."""
        if isinstance(obj, dict) and isinstance(obj.get("cmd"), str) and obj["cmd"] in _REQUEST_SPECS:
            return obj["cmd"]
        return None

    def validate_request(obj: object) -> dict:
        """Validate one editor→daemon v1 request; return it unchanged or raise ProtocolError.

        Precedence (pinned by the vectors; TS/Lua MUST match): (1) object/shape/types → invalid_request,
        (2) version value → unsupported_version (editor-start only), (3) context bytes → too_large.
        `busy` and `duplicate_id` depend on reservation state and are never raised here.
        """
        if not isinstance(obj, dict):
            raise ProtocolError("invalid_request", "expected a JSON object")
        cmd = obj.get("cmd")
        if not isinstance(cmd, str) or cmd not in _REQUEST_SPECS:
            raise ProtocolError("invalid_request", "field 'cmd': unknown native command")
        # Layer 1 — shape (closed field set + strict types), checked BEFORE version/size:
        if cmd == "editor-start":
            _reject_unknown(obj, _REQUEST_SPECS["editor-start"])
            if "version" not in obj:
                raise ProtocolError("invalid_request", "missing field 'version'")
            if type(obj["version"]) is not int:
                raise ProtocolError("invalid_request", "field 'version': expected int")
            _require_id(obj)
            context = _require_str(obj, "context")
            # Layer 2 — protocol version (right type, wrong value):
            if obj["version"] != PROTOCOL_VERSION:
                raise ProtocolError("unsupported_version", "field 'version': unsupported protocol version")
            # Layer 3 — field size (UTF-8 TEXT bytes, not escaped wire bytes):
            if utf8_len(context) > MAX_CONTEXT_BYTES:
                raise ProtocolError("too_large", "field 'context': exceeds 4 KiB UTF-8")
            return obj
        _reject_unknown(obj, _REQUEST_SPECS[cmd])
        _require_id(obj)
        if cmd == "applied":
            _require_int(obj, "seq", minimum=1)
        return obj

    _EVENT_SPECS: dict = {
        "starting": {"event", "id"},
        "listening": {"event", "id", "context_seeded", "context_reason"},
        "pong": {"event", "id"},
        "final": {"event", "id", "seq", "text"},
        "finishing": {"event", "id"},
        "ended": {"event", "id", "reason", "recoverable"},
    }

    def validate_event(obj: object) -> dict:
        """Validate one daemon→editor v1 event (used by clients on receive; by the daemon before encode_line).

        Same layer order as validate_request; `ended.reason` ∈ END_REASONS; `context_reason` present only
        when `context_seeded` is false; final `text` ≤ 4 KiB UTF-8.
        """
        if not isinstance(obj, dict):
            raise ProtocolError("invalid_request", "expected a JSON object")
        event = obj.get("event")
        if not isinstance(event, str) or event not in _EVENT_SPECS:
            raise ProtocolError("invalid_request", "field 'event': unknown native event")
        spec = _EVENT_SPECS[event]
        _reject_unknown(obj, spec)
        required = spec - {"context_reason"}          # context_reason is optional
        missing = sorted(required - set(obj))
        if missing:
            raise ProtocolError("invalid_request", f"missing field {missing[0]!r}")
        _require_id(obj)
        if event == "listening":
            if type(obj["context_seeded"]) is not bool:
                raise ProtocolError("invalid_request", "field 'context_seeded': expected bool")
            if "context_reason" in obj:
                if obj["context_seeded"] is not False:
                    raise ProtocolError("invalid_request", "field 'context_reason': only when context_seeded is false")
                if not (isinstance(obj["context_reason"], str) and obj["context_reason"] in CONTEXT_REASONS):
                    raise ProtocolError("invalid_request", "field 'context_reason': expected empty|disabled|unavailable")
        if event == "final":
            _require_int(obj, "seq", minimum=1)
            text = _require_str(obj, "text")
            if utf8_len(text) > MAX_FINAL_TEXT_BYTES:
                raise ProtocolError("too_large", "field 'text': exceeds 4 KiB UTF-8")
        if event == "ended":
            if not (isinstance(obj["reason"], str) and obj["reason"] in END_REASONS):
                raise ProtocolError("invalid_request", "field 'reason': unknown end reason")
            if type(obj["recoverable"]) is not bool:
                raise ProtocolError("invalid_request", "field 'recoverable': expected bool")
        return obj

    def _is_ws(ch: str) -> bool:
        """Unicode whitespace per CODE POINT (Python str.isspace). Consumers mirror via the pad vectors."""
        return ch.isspace()

    def splice_padding(before: str, text: str, after: str) -> tuple:
        """§4.8.1 C: (left_pad, right_pad), each '' or one ASCII space.

        No pad for empty/whitespace adjacency, after an opening delimiter '([{' (left), or before closing
        punctuation ')]},.!?;:' (right); otherwise one space where adjacent text would touch. Pure over
        code points — no normalization. An empty `text` gets no pads. The adapter inserts
        before + left_pad + text + right_pad + after and places the caret after right_pad.
        """
        if text == "":
            return ("", "")
        left = ""
        if before != "" and not _is_ws(before[-1]) and before[-1] not in OPEN_DELIMITERS:
            left = " "
        right = ""
        if after != "" and not _is_ws(after[0]) and after[0] not in CLOSE_PUNCTUATION:
            right = " "
        return (left, right)
  - DO NOT: alter S1's symbols; use uuid.UUID for validation; add a dependency; add timers/state;
    echo field values into ProtocolError.detail; normalize/strip text in splice_padding.

Task 2: CREATE tests/fixtures/editor_v1.json (the shared oracle — ONE file, 5 kinds)
  - TOP-LEVEL SHAPE:
    {
      "$note": "voice-typing native v1 shared protocol vectors (PRD §4.8.1). Language-neutral: Python,
                TypeScript (integrations/pi) and Lua (integrations/neovim) MUST assert identical results.
                Strings are real Unicode; raw/invalid-UTF-8 frames are hex ('wire_hex'). Case names are
                stable ids — a failure names the vector.",
      "version": 1,
      "limits": {"frame_bytes": 32768, "context_bytes": 4096, "final_text_bytes": 4096},
      "codes": {"error": ["invalid_request","too_large","unsupported_version","busy","duplicate_id"],
                "end_reason": ["stopped","idle","cancelled","target_lost","disconnected","timeout",
                               "delivery_failed","load_failed","shutdown"],
                "context_reason": ["empty","disabled","unavailable"]},
      "pad_tables": {"open_delimiters": "([{", "close_punctuation": ")]},.!?;:"},
      "id": "123e4567-e89b-42d3-a456-426614174000",
      "cases": [ ... ]
    }
  - CASE SCHEMA (one object per case; `kind` selects the consumer assertion):
      {"name": "<stable.id>", "kind": "request"|"event", "frame": {...}, "expect": {"ok": true}}
      {"name": "...", "kind": "request"|"event", "frame": {...}, "expect": {"ok": false, "code": "<error code>"}}
      {"name": "...", "kind": "pad", "before": "...", "text": "...", "after": "...", "expect": ["<left>", "<right>"]}
      {"name": "...", "kind": "truncate", "text": "...", "max_bytes": 4096, "expect": "<resulting suffix>"}
      {"name": "...", "kind": "frame", "wire_hex": "<hex of raw bytes incl. newline>", "expect": {"frames": ["<frame1 str>", ...], "errors": ["<reason>", ...]}}
       (frame cases replay S1's byte-level scenarios so TS/Lua share them: split, coalesced+handoff,
        oversize+newline resync, invalid UTF-8, partial EOF. Python feeds bytes.fromhex(wire_hex) to
        FrameReader via a fake recv that returns it in ONE chunk, then collects frames/FrameError.reasons
        until eof.)
  - THE CASES (verbatim names + inputs; build the long strings programmatically in the test when needed,
    but the FILE must contain literal JSON — generate it once with a small script, see Task 2b):
    REQUEST (accept):
      req.start.ok.001            {"cmd":"editor-start","version":1,"id":ID,"context":"hello world"}
      req.start.ok.002            context "" (empty seed is valid + unseeded)
      req.start.ok.003            context = 4096 ASCII bytes exactly ("a"*4096) — the boundary PASSES
      req.ping.ok.001             {"cmd":"ping","id":ID}
      req.applied.ok.001          {"cmd":"applied","id":ID,"seq":1}
      req.applied.ok.002          seq 2 (monotonic; any >=1 accepted by the validator)
      req.stop.ok.001 / req.cancel.ok.001 / req.lost.ok.001   {"cmd":"stop|cancel|lost","id":ID}
    REQUEST (reject — pin the code AND the precedence):
      req.start.bad.version-type   version "1"            → invalid_request   (shape before version)
      req.start.bad.version-value  version 2              → unsupported_version
      req.start.bad.version-missing (no version key)      → invalid_request
      req.start.bad.version-bool   version true           → invalid_request (bool is not int)
      req.start.bad.id-missing     (no id)                → invalid_request
      req.start.bad.id-type        id 42                  → invalid_request
      req.start.bad.id-upper       ID uppercased          → invalid_request (uuid.UUID would ACCEPT)
      req.start.bad.id-braced      "{ID}"                 → invalid_request (uuid.UUID would ACCEPT)
      req.start.bad.id-urn         "urn:uuid:ID"          → invalid_request
      req.start.bad.id-nohyphen    ID without hyphens     → invalid_request
      req.start.bad.id-v1          "123e4567-e89b-12d3-a456-426614174000" → invalid_request (not v4)
      req.start.bad.id-badvariant  "123e4567-e89b-42d3-c456-426614174000" → invalid_request (variant nibble c)
      req.start.bad.ctx-type       context 42             → invalid_request
      req.start.bad.ctx-surrogate  context "\ud800"       → invalid_request (lone surrogate)
      req.start.bad.ctx-large      context "a"*4097       → too_large
      req.start.bad.ctx-large-cjk  context "漢"*1366 (4098 B) → too_large (byte limit, not char limit)
      req.start.bad.unknown-field  + "target":"pi"       → invalid_request (closed schema)
      req.applied.bad.seq-zero     seq 0                 → invalid_request
      req.applied.bad.seq-bool     seq true              → invalid_request
      req.applied.bad.seq-type     seq "1"               → invalid_request
      req.applied.bad.seq-missing  (no seq)              → invalid_request
      req.ping.bad.unknown-field   + "seq":1             → invalid_request
      req.cmd.bad.unknown          {"cmd":"toggle","id":ID} → invalid_request (legacy cmds are NOT native)
      req.cmd.bad.type             cmd 42                → invalid_request
      req.obj.bad.not-dict         (frame: [1,2])        → invalid_request
    EVENT (accept):
      ev.starting.ok.001          {"event":"starting","id":ID}
      ev.listening.ok.001         {"event":"listening","id":ID,"context_seeded":true}
      ev.listening.ok.002         context_seeded false + context_reason "empty"
      ev.pong.ok.001 / ev.finishing.ok.001
      ev.final.ok.001             {"event":"final","id":ID,"seq":1,"text":"hello there"}
      ev.final.ok.002             text = 4096 ASCII bytes (boundary passes)
      ev.final.ok.003             text with real Unicode "héllo 😀 ." (raw, ensure_ascii=False)
      ev.ended.ok.001             reason "stopped", recoverable false
      ev.ended.ok.002             reason "target_lost", recoverable true
      ev.ended.ok.003             reason "delivery_failed", recoverable true
    EVENT (reject):
      ev.listening.bad.reason-when-seeded  context_seeded true + context_reason "empty" → invalid_request
      ev.listening.bad.reason-unknown      context_reason "later"               → invalid_request
      ev.listening.bad.seeded-type         context_seeded "yes"                 → invalid_request
      ev.final.bad.seq-zero / ev.final.bad.text-large ("a"*4097 → too_large) / ev.final.bad.text-surrogate
      ev.final.bad.text-large-esc  text = 4096 '"' chars → too_large? NO: that is 4096 TEXT bytes → OK
                                       (use it as ev.final.ok.004 to pin text-bytes-not-wire-bytes)
      ev.ended.bad.reason / ev.ended.bad.recoverable-type ("true" → invalid_request)
      ev.unknown.bad.001          {"event":"partial","id":ID} → invalid_request (partials are NOT native v1)
      ev.obj.bad.not-dict
    PAD (before, text, after) → [left, right]:
      pad.prnd.hello-comma      ("hello","there",", world") → ["", " "]      (PRD example 1)
      pad.prnd.hello-world      ("hello","there","world")   → [" ", " "]     (PRD example 2)
      pad.empty.final           ("hello","","world")        → ["", ""]
      pad.empty.before          ("","there","world")        → ["", " "]
      pad.empty.after           ("hello","there","")        → [" ", ""]
      pad.ws.before.tab         ("hello\t","there","x")     → ["", " "]
      pad.ws.before.nl          ("line\n","there","x")      → ["", " "]
      pad.ws.before.nbsp        ("hello\u00a0","there","x") → ["", " "]      (NBSP is whitespace)
      pad.ws.before.ideosp      ("hello\u3000","there","x") → ["", " "]      (ideographic space)
      pad.ws.after.space        ("hello","there"," world")  → [" ", ""]
      pad.open.paren            ("(","there",")")           → ["", ""]       (no pad after '(' ; ')' closing)
      pad.open.bracket          ("[","there","]")           → ["", ""]
      pad.open.brace            ("{","there","}")           → ["", ""]
      pad.close.period          ("hello","there",". next")  → [" ", ""]
      pad.close.comma           ("hello","there",", world") → ["", " "]      (= example 1, listed for symmetry)
      pad.close.all             ("x","y",")]},.!?;:")       → [" ", ""]      (first char ')' → no right pad)
      pad.unicode.text          ("héllo","wörld 😀","wörld") → [" ", " "]
      pad.unicode.ws-mix        ("héllo\u2028","wörld","x") → ["", " "]      (LINE SEPARATOR is whitespace)
    TRUNCATE (text, max_bytes 4096) → expect suffix (PROBE-VERIFIED with the Task-1 code):
      trunc.short.001           ("abc", 4096) → "abc"
      trunc.exact.ascii         ("a"*4096) → unchanged
      trunc.over.1byte          ("a"*4095 + "é" + "z") → "éz"                 (4098 B in → newest 4096 B; é survives)
      trunc.straddle.2byte      ("a"*3 + "é" + "z"*4096) → "z"*4096         (window starts INSIDE é → é dropped; result starts "z")
      trunc.straddle.4byte      ("a"*3 + "😀" + "z"*4096) → "z"*4096        (window starts at byte 2 of the emoji → dropped)
      trunc.fit.2byte           ("a"*3 + "é" + "z"*4094) → "é" + "z"*4094    (window starts exactly at é → kept; 4096 B)
      trunc.fit.4byte           ("a"*3 + "😀" + "z"*4092) → "😀" + "z"*4092  (kept; 4096 B)
      trunc.cjk.001             ("漢"*2000, 6000 B) → "漢"*1365             (4095 B; 1366 would be 4098)
      trunc.suffix.keeps-newest ("z" + "é" + "a"*4094) → "é" + "a"*4094    (drops the LEADING "z"; keeps newest; 4096 B)
      NOTE: a straddle requires the multibyte char AT THE WINDOW START — input > 4096 B and the last 4096
      bytes begin mid-character. With a short trailing tail (e.g. "a"*4094+"é"+"z") the window begins
      before the char and it simply FITS — that is trunc.over.1byte, not a straddle.
    FRAME (wire_hex, replayed through FrameReader — S1's byte cases, shared with TS/Lua):
      frame.split.001           '{"cmd":"ping","id":"…"}\n' sent as ONE chunk but the case records it
                                expect {"frames":["{...ping...}"], "errors":[]}  (see note below)
      frame.coalesced.handoff   two frames in one chunk → frames == [f1, f2], errors == []
      frame.oversize.resync     b"x"*(32769)+b"\n"+valid+"\n" → errors ["frame-too-large"], then valid frame
      frame.invalid-utf8        b"\xff\xfe{\n" + valid → (UTF-8 is the HANDLER's layer; FrameReader returns
                                the raw frame b"\xff\xfe{" — record frames: [<that str via latin-1>], errors: [])
      frame.partial-eof         b'{"partial"' (no newline) → frames [], errors ["eof"]  (detail "partial")
  - WRITING THE FILE (Task 2b — do this, don't hand-type 4 KiB strings):
      generate with a throwaway script that json.dump(..., ensure_ascii=False, indent=1) the dict built in
      Python (so "a"*4096, the CJK repeats and the hex frames are exact), then DELETE the script. The
      committed artifact is the JSON only. Verify: json.loads round-trips; `"é"` and `"😀"` appear raw.

Task 3: CREATE tests/test_editor_protocol_vectors.py (the Python consumer of the oracle)
  - HEADER: "Shared v1 protocol vectors (PRD §4.8.1; P1.M1.T3.S2). Loads tests/fixtures/editor_v1.json and
    asserts EVERY case against voice_typing.editor_protocol — the same file the Pi (TS) and Neovim (Lua)
    adapters consume. NO socket, NO editor, NO daemon import. Run: timeout 120 .venv/bin/python -m pytest
    tests/test_editor_protocol_vectors.py -q"
  - HARNESS + TESTS (verbatim):
    from __future__ import annotations
    import json
    from pathlib import Path
    import pytest
    from voice_typing import editor_protocol as ep

    VECTORS = json.loads((Path(__file__).resolve().parent / "fixtures" / "editor_v1.json").read_text("utf-8"))
    CASES = VECTORS["cases"]

    def _cases(kind):
        return [c for c in CASES if c["kind"] == kind]

    class _OneShotSock:
        """Returns the given bytes in ONE recv, then b'' (EOF) — the scripted fake recv S1's tests use."""
        def __init__(self, data: bytes) -> None:
            self._data = data
        def recv(self, n: int) -> bytes:
            out, self._data = self._data[:n], self._data[n:]
            return out

    # --- fixture self-consistency (the oracle must match the module's exported constants) ---
    def test_fixture_constants_match_module():
        assert VECTORS["version"] == ep.PROTOCOL_VERSION == 1
        assert VECTORS["limits"]["frame_bytes"] == ep.MAX_FRAME_BYTES
        assert VECTORS["limits"]["context_bytes"] == ep.MAX_CONTEXT_BYTES
        assert VECTORS["limits"]["final_text_bytes"] == ep.MAX_FINAL_TEXT_BYTES
        assert set(VECTORS["codes"]["error"]) == set(ep.NATIVE_ERROR_CODES)
        assert set(VECTORS["codes"]["end_reason"]) == set(ep.END_REASONS)
        assert set(VECTORS["codes"]["context_reason"]) == set(ep.CONTEXT_REASONS)
        assert VECTORS["pad_tables"]["open_delimiters"] == ep.OPEN_DELIMITERS
        assert VECTORS["pad_tables"]["close_punctuation"] == ep.CLOSE_PUNCTUATION

    def test_fixture_case_names_are_unique_and_kinds_known():
        names = [c["name"] for c in CASES]
        assert len(names) == len(set(names)), "vector names must be stable unique ids"
        assert {c["kind"] for c in CASES} == {"request", "event", "pad", "truncate", "frame"}
        assert len(CASES) >= 40

    # --- requests ---
    @pytest.mark.parametrize("case", _cases("request"), ids=lambda c: c["name"])
    def test_request_vectors(case):
        if case["expect"]["ok"]:
            assert ep.validate_request(case["frame"]) is case["frame"]
        else:
            with pytest.raises(ep.ProtocolError) as ei:
                ep.validate_request(case["frame"])
            assert ei.value.code == case["expect"]["code"]

    # --- events (daemon emits / clients validate on receive) ---
    @pytest.mark.parametrize("case", _cases("event"), ids=lambda c: c["name"])
    def test_event_vectors(case):
        if case["expect"]["ok"]:
            assert ep.validate_event(case["frame"]) is case["frame"]
        else:
            with pytest.raises(ep.ProtocolError) as ei:
                ep.validate_event(case["frame"])
            assert ei.value.code == case["expect"]["code"]

    # --- accepted events must also be wire-encodable within S1's frame bound ---
    @pytest.mark.parametrize("case", [c for c in _cases("event") if c["expect"]["ok"]], ids=lambda c: c["name"])
    def test_accepted_events_encode_within_frame_bound(case):
        line = ep.encode_line(case["frame"])          # raises FrameError if > 32 KiB
        assert line.endswith(b"\n") and len(line) <= ep.MAX_FRAME_BYTES

    # --- §C splice padding ---
    @pytest.mark.parametrize("case", _cases("pad"), ids=lambda c: c["name"])
    def test_splice_padding_vectors(case):
        assert list(ep.splice_padding(case["before"], case["text"], case["after"])) == case["expect"]

    # --- §A code-point-safe newest-suffix truncation ---
    @pytest.mark.parametrize("case", _cases("truncate"), ids=lambda c: c["name"])
    def test_truncate_utf8_suffix_vectors(case):
        out = ep.truncate_utf8_suffix(case["text"], case.get("max_bytes", ep.MAX_CONTEXT_BYTES))
        assert out == case["expect"]
        assert len(out.encode("utf-8")) <= case.get("max_bytes", ep.MAX_CONTEXT_BYTES)   # never over

    # --- S1 framing cases replayed for cross-language parity (bytes come from hex) ---
    @pytest.mark.parametrize("case", _cases("frame"), ids=lambda c: c["name"])
    def test_frame_vectors(case):
        reader = ep.FrameReader(_OneShotSock(bytes.fromhex(case["wire_hex"])).recv)
        frames, errors = [], []
        while True:
            try:
                frames.append(reader.read_frame_bytes().decode("utf-8"))
            except ep.FrameError as fe:
                errors.append(fe.reason)
                if fe.reason == "eof":
                    break
        assert frames == case["expect"]["frames"] and errors == case["expect"]["errors"]

    # --- the probe-pinned properties that motivated the vectors (kept explicit, not only via the file) ---
    def test_uuid_validator_rejects_forms_uuid_module_accepts():
        import uuid
        loose = ["{" + VECTORS["id"] + "}", "urn:uuid:" + VECTORS["id"], VECTORS["id"].upper(), VECTORS["id"].replace("-", "")]
        for s in loose:
            assert uuid.UUID(s) and not ep.is_uuid_v4(s)    # the stdlib accepts; the wire does not

    def test_bool_is_not_an_int_seq():
        with pytest.raises(ep.ProtocolError):
            ep.validate_request({"cmd": "applied", "id": VECTORS["id"], "seq": True})

    def test_text_limit_is_utf8_bytes_not_wire_bytes():
        text = '"' * 4096                               # 4096 text bytes, 8279 wire bytes
        assert ep.utf8_len(text) == 4096
        assert len(ep.encode_line({"event": "final", "id": VECTORS["id"], "seq": 1, "text": text})) > 4096
        ep.validate_event({"event": "final", "id": VECTORS["id"], "seq": 1, "text": text})   # passes
        with pytest.raises(ep.ProtocolError) as ei:
            ep.validate_event({"event": "final", "id": VECTORS["id"], "seq": 1, "text": text + "x"})
        assert ei.value.code == "too_large"

    def test_errors_never_echo_field_values():
        secret = "private editor text " * 50
        with pytest.raises(ep.ProtocolError) as ei:
            ep.validate_request({"cmd": "editor-start", "version": 1, "id": VECTORS["id"], "context": secret + "x"})
        assert "private" not in ei.value.detail and secret not in str(ei.value)
        assert ep.native_error_reply("too_large") == {"ok": False, "error": "too_large"}

    def test_request_kind_recognizes_only_native_cmds():
        assert ep.request_kind({"cmd": "ping", "id": VECTORS["id"]}) == "ping"
        assert ep.request_kind({"cmd": "toggle"}) is None and ep.request_kind([]) is None
  - NOTE on `frame.invalid-utf8`: FrameReader is bytes-only (S1 design) — it RETURNS the raw frame; the
    handler does the strict decode. Record that frame in `expect.frames` as the latin-1 decoding of the
    bytes (so JSON can carry it) and assert `.decode("latin-1")` in the test for that one case — or
    simply compare `reader.read_frame_bytes()` bytes against `bytes.fromhex` of a `frames_hex` list. Use
    `frames_hex` for ALL frame cases (cleaner + language-neutral): expect {"frames_hex": [...], "errors": [...]}.
  - DO NOT: import voice_typing.daemon; open sockets; edit S1's test file; weaken a vector to pass.

Task 4: VALIDATE (L1–L4). If committing: "P1.M1.T3.S2: v1 message validation contract + shared
  cross-language vectors (editor_protocol validators/codes, §C splice padding, §A cp-safe seed cut;
  tests/fixtures/editor_v1.json oracle for Python/TS/Lua)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — layered validation with a stable code per layer and a FIXED precedence (CRITICAL #7):
def validate_request(obj):
    if not isinstance(obj, dict): raise ProtocolError("invalid_request", "expected a JSON object")
    ...                                           # (1) closed schema + strict types → invalid_request
    if obj["version"] != PROTOCOL_VERSION:        # (2) right type, wrong value
        raise ProtocolError("unsupported_version", ...)
    if utf8_len(context) > MAX_CONTEXT_BYTES:     # (3) TEXT bytes (CRITICAL #4)
        raise ProtocolError("too_large", ...)

# PATTERN 2 — strict scalars: type(x) is int (not bool); regex UUIDv4 (not uuid.UUID); no lone surrogates.
# PATTERN 3 — cp-safe newest-suffix cut (CRITICAL #6): slice the suffix, then drop LEADING continuation bytes.
cut = raw[-max_bytes:]; k = 0
while k < len(cut) and (cut[k] & 0xC0) == 0x80: k += 1
return cut[k:].decode("utf-8")
# PATTERN 4 — §C padding as a pure function over code points with EXPLICIT tables (D5):
left  = " " if before and not before[-1].isspace() and before[-1] not in OPEN_DELIMITERS else ""
right = " " if after  and not after[0].isspace()  and after[0]  not in CLOSE_PUNCTUATION else ""
# (with the empty-final short-circuit returning ("", "") first)
```

### Integration Points

```yaml
UPSTREAM CONSUMED — P1.M1.T3.S1 (parallel): MAX_FRAME_BYTES, FrameError, FrameReader, encode_line.
  This task APPENDS to its module and replays its byte cases as `frame` vectors; never modifies them.

DOWNSTREAM CONSUMERS (the contract's OUTPUT — keep names EXACT):
  - P1.M1.T3.S3 (owner pump): validate_request on every decoded dict; native_error_reply + EOF on a
    rejected first frame; request_kind to route native vs legacy; PROTOCOL_VERSION.
  - P1.M1.T4.S2 (sequenced offer): validate_event before encode_line; seq >= 1; MAX_FINAL_TEXT_BYTES.
  - P1.M2.T1.S2 (Pi client, TS) / P1.M2.T2.S1 (Neovim libuv transport, Lua): re-implement the validators
    against tests/fixtures/editor_v1.json; same precedence; frame cases via the same wire_hex bytes.
  - P1.M2.T1.S4 (Pi splice) / P1.M2.T2.S3 (Neovim byte-exact edit): splice_padding + truncate_utf8_suffix
    semantics (pad vectors); unit mapping (UTF-16 / UTF-8 bytes) is theirs.
  - P1.M1.T5.S1 (recovery reply): NATIVE_ERROR_CODES spelling for not_found/busy (its own codes are its own).

PARALLEL — P1.M1.T2.S5 (start-context route in _dispatch, ctl.py): DISJOINT (no editor_protocol edits).

UNCHANGED: daemon.py, ctl.py, config.py, recorder_host.py, every existing test; no new dependency.
```

## Validation Loop

> Full paths; two timeouts (inner `timeout`, bash-tool ≥ +60). pytest only. No socket, no daemon import.

### Level 1: S1 intact + this task's symbols exported

```bash
cd /home/dustin/projects/voice-typing
test -f voice_typing/editor_protocol.py || { echo "L1 FAIL: S1 not landed"; exit 1; }
git diff -- voice_typing/editor_protocol.py | grep -c '^-[^-]'   # 0 deleted lines → S1's text untouched (append-only)
timeout 60 .venv/bin/python - <<'PY'
import inspect
from voice_typing import editor_protocol as ep
# S1's four symbols, unchanged:
assert ep.MAX_FRAME_BYTES == 32768 and inspect.signature(ep.FrameReader).parameters["recv"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
assert {"read_frame_bytes"} <= {n for n,_ in inspect.getmembers(ep.FrameReader, inspect.isfunction)}
assert callable(ep.encode_line) and issubclass(ep.FrameError, Exception)
# this task's exports:
for n in ["PROTOCOL_VERSION","NATIVE_ERROR_CODES","END_REASONS","CONTEXT_REASONS","MAX_CONTEXT_BYTES",
          "MAX_FINAL_TEXT_BYTES","OPEN_DELIMITERS","CLOSE_PUNCTUATION","UUID_V4_RE","ProtocolError",
          "is_uuid_v4","utf8_len","has_lone_surrogates","truncate_utf8_suffix","validate_request",
          "validate_event","request_kind","splice_padding","native_error_reply"]:
    assert hasattr(ep, n), n
assert ep.PROTOCOL_VERSION == 1 and ep.MAX_CONTEXT_BYTES == 4096 == ep.MAX_FINAL_TEXT_BYTES
assert "busy" in ep.NATIVE_ERROR_CODES and "target_lost" in ep.END_REASONS and "unavailable" in ep.CONTEXT_REASONS
print("L1 PASS: S1 intact; v1 validation surface exported")
PY
timeout 60 .venv/bin/python -m py_compile voice_typing/editor_protocol.py tests/test_editor_protocol_vectors.py && echo "L1 PASS: compiles"
```

### Level 2: The vector suite + S1's suite (unchanged) + the fixture round-trip

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -c "import json;d=json.load(open('tests/fixtures/editor_v1.json',encoding='utf-8'));print('cases',len(d['cases']));assert open('tests/fixtures/editor_v1.json',encoding='utf-8').read().find('é')>=0, 'Unicode must be raw, not \\\\u-escaped'"
timeout 120 .venv/bin/python -m pytest tests/test_editor_protocol_vectors.py -q 2>&1 | tail -3
test -f tests/test_editor_protocol.py && timeout 120 .venv/bin/python -m pytest tests/test_editor_protocol.py -q 2>&1 | tail -3
# Expected: vector suite green (≥ 40 parametrized cases + the explicit pins); S1's suite green UNMODIFIED.
```

### Level 3: The behavioral proof (inline — the probe findings, now enforced)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python - <<'PY'
from voice_typing import editor_protocol as ep
ID = "123e4567-e89b-42d3-a456-426614174000"
# precedence: shape beats version beats size
for frame, code in [({"cmd":"editor-start","version":"1","id":ID,"context":"a"*4097}, "invalid_request"),
                    ({"cmd":"editor-start","version":2,"id":ID,"context":"a"*4097},   "unsupported_version"),
                    ({"cmd":"editor-start","version":1,"id":ID,"context":"a"*4097},   "too_large")]:
    try: ep.validate_request(frame); raise SystemExit("FAIL: accepted")
    except ep.ProtocolError as e: assert e.code == code, (e.code, code)
assert ep.truncate_utf8_suffix("a"*3+"😀"+"z"*4096) == "z"*4096            # 4-byte straddle at the window start → dropped
assert ep.truncate_utf8_suffix("a"*3+"é"+"z"*4094) == "é"+"z"*4094          # starts exactly at é → kept
assert ep.truncate_utf8_suffix("a"*4095+"é"+"z").endswith("éz")          # over by 2 → newest 4096 B include é
assert ep.splice_padding("hello","there",", world") == ("", " ") and ep.splice_padding("hello","there","world") == (" ", " ")
assert not ep.is_uuid_v4(ID.upper()) and ep.is_uuid_v4(ID)
print("L3 PASS: precedence, cp-safe cut, padding, strict id")
PY
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only; git status --short | grep '^??'
# Expected ⊆ {voice_typing/editor_protocol.py, tests/fixtures/editor_v1.json, tests/test_editor_protocol_vectors.py}
# (editor_protocol.py / test_editor_protocol.py may show as S1's untracked/modified — fine; S1's TEST file must be unmodified by you.)
git diff --exit-code -- voice_typing/daemon.py voice_typing/ctl.py voice_typing/config.py pyproject.toml && echo "L4 PASS: out-of-scope files untouched by this task" || echo "L4 NOTE: daemon.py/ctl.py diffs are T2.S5's parallel work — verify none are yours"
grep -c "import uuid" voice_typing/editor_protocol.py     # 0 — uuid module is NOT used for validation (CRITICAL #2)
grep -c "time\.\|settimeout\|threading" voice_typing/editor_protocol.py   # 0 — no timers/state (T3.S3)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: S1's symbols byte-identical (append-only diff); all 19 new symbols exported; py_compile clean.
- [ ] L2: vector suite green (≥ 40 cases); S1's suite green unmodified; fixture is raw-Unicode JSON.
- [ ] L3: inline proof of precedence, the cp-safe cut (window-start straddle drops / exact-start fits), both PRD padding examples, strict id.
- [ ] L4: diff ⊆ the three files; no `uuid`/timers/state in the module; no dependency added.

### Feature Validation
- [ ] All 6 request shapes and 6 event shapes validated (accept + reject with the spec's code).
- [ ] Precedence pinned: shape → `unsupported_version` → `too_large`; `busy`/`duplicate_id` never raised here.
- [ ] Strictness pinned: bool≠int, canonical lowercase UUIDv4 only, closed schema, lone surrogates, text-byte limits.
- [ ] `truncate_utf8_suffix` keeps the newest bytes and never splits a code point; `splice_padding` reproduces the PRD examples and explicit Unicode-whitespace behavior.
- [ ] Errors never echo field values; `native_error_reply` is exactly `{"ok": false, "error": code}`.

### Code Quality / Scope Validation
- [ ] Pure, stateless, stdlib-only; `str, Enum` code sets and an Exception subclass follow repo convention.
- [ ] No second wire schema (no JSON Schema/codegen); no normalization of divergent whitespace; vectors are the single oracle.
- [ ] Mode A docstrings on every exported symbol naming the §4.8.1 clause; fixture `$note` documents the conventions.

### Documentation & Deployment
- [ ] DOCS Mode A satisfied in-module and in fixture metadata (no README change required by this item).

---

## Anti-Patterns to Avoid

- ❌ Don't rewrite or re-indent S1's framing code — append below a banner; the L1 diff must show zero deletions.
- ❌ Don't validate ids with `uuid.UUID()` — it accepts braces/urn/uppercase/hyphen-less forms (use the regex).
- ❌ Don't accept `True` as a seq/version (`isinstance(True, int)` is True) — use `type(x) is int`.
- ❌ Don't enforce the 4 KiB limits on JSON-escaped wire bytes — they are UTF-8 TEXT byte limits (S1's 32 KiB bound is separate).
- ❌ Don't truncate with "strip trailing `0x80` bytes" — a cut can land on a LEAD byte; walk back to the lead and drop the partial sequence.
- ❌ Don't use `\s`, `str.isspace()` on a normalized copy, `locale`, or implicit whitespace folding in padding — explicit code-point classification with pinned vectors.
- ❌ Don't let `ProtocolError.detail` or any reply carry field text (context is private editor text; finals are transcript).
- ❌ Don't invent a JSON Schema / protobuf / codegen — the validators are the oracle; the vectors are the contract.
- ❌ Don't produce `busy`/`duplicate_id` from validators (state — T3.S3/T3.S4) or add timers (T3.S3) or touch daemon.py.
- ❌ Don't hand-type 4 KiB strings into the JSON — generate the file once, commit the artifact, delete the generator.
- ❌ Don't run pytest without both timeouts; don't invent ruff/mypy gates; don't modify S1's or any existing test.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The three hazards most likely to produce a silently
divergent cross-language contract were **found by running probes** (loose `uuid.UUID`, bool-is-int,
text-vs-wire bytes, and the lead-byte truncation bug — the naive helper actually raised
`UnicodeDecodeError` in the probe) and are baked into both the verbatim implementation and explicit
test pins; every rule maps to a cited §4.8.1 clause; the vector file's schema, names, inputs and expected
values are enumerated so the oracle is reproducible, and its consumer test is given verbatim. The −0.5 is
the dependency on S1 landing first (Task 0 gates it; the append-only rule and the zero-deletions diff make
the merge safe by construction) and the mechanical care needed to generate the long-string vectors exactly
(Task 2b prescribes generating rather than typing them).

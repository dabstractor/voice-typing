# T3.S2 research — v1 message validation + shared cross-language vectors

## 1. Inputs consumed (contracts, verified)

- **S1 (P1.M1.T3.S1, parallel — NOT yet on disk at research time)**: creates `voice_typing/editor_protocol.py`
  with `MAX_FRAME_BYTES = 32*1024`, `FrameError(reason, detail)` (reader reasons `frame-too-large` |
  `eof` | `io`), `FrameReader(recv, *, max_bytes, chunk_size)` (bytes-only; `read_frame_bytes()`,
  `unread`, `_drain_runaway`), `encode_line(obj) -> bytes` (`json.dumps(ensure_ascii=False)` + `\n`;
  raises `FrameError("frame-too-large")` past MAX). Its Integration Points: "P1.M1.T3.S2 validates the
  DICT the handler parsed; consumes FrameError reason codes + encode_line for its vectors."
  → T3.S2 ADDS to this module (never rewrites S1's symbols); it receives an already-decoded `dict`.
- **PRD §4.8.1 B** (prd_snapshot.md:448-482) — the authoritative v1 frames, error codes, reasons, limits.
- **PRD §4.8.1 A/C** — 4 KiB seed (newest suffix, UTF-8 code-point boundary); §C padding rules.
- architecture/system_context.md (codec/policy split; "do not echo arbitrary request fragments in reasons";
  timers are T3.S3's); editor_apis.md ("Explicit Unicode whitespace/delimiter table or scalar
  classification must match the PRD across languages; Lua `%s` and JS `\s` cannot be assumed equivalent").

## 2. The v1 wire contract, extracted from §4.8.1 B (normative)

Requests (editor→daemon): `editor-start{version,id,context}`, `ping{id}`, `applied{id,seq}`,
`stop|cancel|lost{id}`. First frame MUST be `editor-start`. Events (daemon→editor): `starting{id}`,
`listening{id,context_seeded,context_reason?}`, `pong{id}`, `final{id,seq,text}`, `finishing{id}`,
`ended{id,reason,recoverable}`; failure of the first request: `{ok:false,error:<code>}` + EOF.
Native error codes: `invalid_request | too_large | unsupported_version | busy | duplicate_id`.
End reasons: `stopped | idle | cancelled | target_lost | disconnected | timeout | delivery_failed |
load_failed | shutdown`. Limits: frame 32 KiB incl. newline (S1); context ≤ 4 KiB UTF-8; final text
≤ 4 KiB UTF-8; seq starts at 1, monotonic; `context_reason ∈ empty|disabled|unavailable` only when
`context_seeded` is false.

## 3. Design decisions (locked)

**D1 — Validation layers, in order, with a stable code each.** (a) framing/UTF-8/JSON → S1 (`frame-too-large`,
handler's `invalid UTF-8 frame`, dispatcher's `malformed JSON:`); (b) **shape/type → `invalid_request`**
(this task: wrong field types, missing/extra fields, bad UUID, seq not a positive int, bool-as-int);
(c) **field size → `too_large`** (context > 4 KiB UTF-8; final text > 4 KiB); (d) **version →
`unsupported_version`** (version present, int, ≠ 1). `busy`/`duplicate_id` are STATE decisions (T3.S3/T3.S4)
— out of scope. Precedence for `editor-start`: shape → version → size (a wrong-type version is a shape
error; a right-type wrong value is `unsupported_version`). Order matters cross-language → pinned in vectors.

**D2 — Strict types, no coercion.** `id` must match canonical lowercase RFC 4122 **v4** (probe: Python's
`uuid.UUID()` ACCEPTS `{…}`, `urn:uuid:…`, UPPERCASE, and hyphen-less forms → a regex is required, with
the version nibble `4` and variant `[89ab]` checked). `seq`/`version` must be `int` **and not `bool`**
(`isinstance(True, int)` is True in Python; JSON `true` must not pass as a seq). `context`/`text` must be
`str` with **no lone surrogates** (probe: `json.dumps(ensure_ascii=False).encode()` raises
`UnicodeEncodeError` on `"\ud800"` — a crash path if unvalidated). Unknown top-level keys → `invalid_request`
(the spec forbids target names, buffer contents, output-mode options in `editor-start`; a closed schema
enforces that structurally).

**D3 — Byte limits are on UTF-8 TEXT bytes, not wire bytes.** Probe: 4,096 `"` chars → **8,279** wire
bytes after JSON escaping. The spec says "4 KiB UTF-8 per final" and "newest 4 KiB of text" → the limit is
`len(s.encode("utf-8"))`, checked independently of S1's 32 KiB frame bound. Both apply.

**D4 — Code-point-boundary truncation (the probe-caught bug).** The naive rule "strip trailing
continuation bytes (`0x80`-prefixed)" is WRONG: `"a"*4094 + "é"` cut at 4096 ends on the LEAD byte
`0xC3` (continuation `0xA9` is byte 4097) → `UnicodeDecodeError`. Correct rule: walk back over
continuation bytes to the lead, compute the expected sequence length from the lead, and drop the whole
sequence if incomplete. For the newest-suffix seed, drop LEADING continuation bytes the same way. The
helper `truncate_utf8_suffix(text, max_bytes)` (newest ≤N bytes, cp-aligned) lives in editor_protocol and
the vectors pin: 2-byte straddle, 4-byte emoji straddle, exact-fit, all-CJK, and the suffix case.

**D5 — Padding is a PURE function over code points, never locale/regex whitespace.** §C: "Add at most
one ASCII space at each splice edge: no pad for empty/whitespace adjacency, between an opening delimiter
`([{` and text, or before closing punctuation `)]},.!?;:`; otherwise add one space where adjacent text
would touch." Implementation: an explicit table `OPEN_DELIMITERS = "([{"`, `CLOSE_PUNCTUATION = ")]},.!?;:"`,
and whitespace = `ch.isspace()` on **code points** (NOT `str.ispace()` on a normalized copy, NOT `\s`).
Output = `(left_pad: str, right_pad: str)` each `""` or `" "`; the adapter splices `left + text + right`
at the caret. Rules: left pad iff `before` non-empty AND `before[-1]` is not whitespace AND not in
OPEN_DELIMITERS; right pad iff `after` non-empty AND `after[0]` is not whitespace AND not in
CLOSE_PUNCTUATION. Vectors pin the PRD's own examples (`hello|, world`+`there` → `hello there|, world`
= right pad only; `hello|world` → `hello there |world` = both) plus tab/newline/NBSP/ideographic-space
adjacency, delimiter cases, empty-before/after, and empty final (no pads).

**D6 — Events are validated by the SAME validators** (daemon-side encode asserts, client-side decode).
`validate_event(obj)` mirrors `validate_request`: unknown event → `invalid_request`-class
`ProtocolError(kind="event")`; `context_reason` present ⇒ `context_seeded` must be false; `ended` reason
∈ the 9 codes; `seq ≥ 1`. Symmetry is what makes one vector file serve Python, TS and Lua.

**D7 — `ProtocolError` carries the wire code; it never carries raw field text.** `ProtocolError(code:
str, detail: str)` where `detail` names only the FIELD and the violation class ("field 'seq': expected
int >= 1") — never the offending value (spec: "no echo in errors"; system_context: "do not echo arbitrary
request fragments in reasons"). `too_large` replies use the fixed string the spec implies.

**D8 — Vectors: ONE JSON file, three directions, language-neutral.** `tests/fixtures/editor_v1.json`
with `{"$schema_note", "version": 1, "cases": [...]}`; every case has `name`, `kind` ∈
`frame | request | event | pad | truncate`, an `expect` object, and ONLY JSON-representable values
(strings are stored as real Unicode; invalid-UTF-8 frames are stored as hex `wire_hex` because JSON
cannot carry invalid UTF-8). Each consumer language reads the same file and asserts the same `expect`.
Case IDs are stable (`req.start.ok.001`) so a failure names the vector, not a line.

**D9 — No second wire schema.** No JSON Schema file, no codegen, no protobuf — the spec forbids inventing
one. The Python validators ARE the reference oracle; TS/Lua re-implement against the vectors.

## 4. Scope boundaries

- IN: `editor_protocol.py` additions (validators, codes, pad, truncation helpers, `native_error_reply`
  helper), `tests/fixtures/editor_v1.json`, `tests/test_editor_protocol_vectors.py`, S1's
  `tests/test_editor_protocol.py` untouched (S1 owns it; this task's tests live in their own file).
- OUT: `editor_session.py`, timers, reservation state (`busy`/`duplicate_id`), `_dispatch` changes,
  socket writes, recovery (T3.S3/T3.S4/T4.*/T5.*), any adapter code (P1.M2.*), daemon.py.

## 5. Tooling

pytest only (no ruff/mypy/schema lib; stdlib only: `json`, `re`, `uuid` NOT used for validation).
`timeout 120 .venv/bin/python -m pytest tests/test_editor_protocol_vectors.py -q`. Fixture path via
`Path(__file__).parent / "fixtures" / "editor_v1.json"` (tests/ already hosts `fixtures/`).

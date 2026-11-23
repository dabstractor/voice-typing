# PRP — P1.M4.T1.S1: Wire transport package + JSONL protocol (`voice_typing/ime/`)

## Goal

**Feature Goal**: Productize the proven im-lab transport into a daemon-importable package:
**copy + evolve** `tools/im-lab/wlwire.py` (stdlib Wayland wire client, core +
`zwp_input_method_v2` + keyboard grab) and `tools/im-lab/im_probe.py` (seat-IM JSON command loop +
64 KiB-capped event log) into a new **`voice_typing/ime/`** package, adding a **pure JSONL
request/reply protocol** (`acquire` / `show` / `verify` / `leave` + `ping`, replies echoing caller
`id`, async `{"ev":...}` result/state events using `ShowResult`/`AcquireResult` verbatim from
`voice_typing/bulk_delivery.py`), served by the IM host over **stdin/stdout** (the P1.M4.T1.S2
subprocess speaks pipes). Tests pin the **opcode tables against the vendored
`input-method-unstable-v2.xml`** and the **JSONL framing**. This is the TRANSPORT LAYER ONLY —
subprocess lifecycle (S2), acquire/verify/show SEMANTICS (T2/T3), takeover (T4) are fenced out.
Development MUST NOT change the operator's service/config/bindings.

**Deliverable** (5 new source/test files + 1 fixture; tools/im-lab untouched):
1. `voice_typing/ime/__init__.py` — package docstring carrying the **Mode A R.2 evidence trail**
   (26–40 ms insert; one atomic commit corrects a whole 1024-byte span; `surrounding_text` byte-exact;
   `commit_string` generates zero key events) + provenance line.
2. `voice_typing/ime/wlwire.py` — evolved copy of the lab wire client (see What).
3. `voice_typing/ime/protocol.py` — NEW pure module: JSONL vocabulary, encode/decode framing,
   request validation, reply/event constructors, the capped event-log writer class.
4. `voice_typing/ime/ime_host.py` — evolved im_probe: binds the seat IM (stdlib, via wlwire), serves
   JSONL on stdin/stdout, maps requests to wire requests, emits async events, writes the capped log,
   exits cleanly on `unavailable`.
5. `tests/test_ime_wlwire.py`, `tests/test_ime_protocol.py`, `tests/test_ime_host.py` + vendored
   `tests/fixtures/input-method-unstable-v2.xml`.

**Success Definition**:
- (a) All three new suites green under `timeout 120 .venv/bin/python -m pytest tests/test_ime_*.py -q`;
  no existing suite regressed (`git status --porcelain` shows ONLY the new files).
- (b) The opcode-table test parses the vendored XML and proves wlwire's `REQUESTS`/`EVENTS` entries
  for `zwp_input_method_manager_v2`, `zwp_input_method_v2`, `zwp_input_method_keyboard_grab_v2`
  match the XML's `<request>`/`<event>` order and arg kinds exactly.
- (c) `import voice_typing.ime`, `import voice_typing.ime.protocol` succeed with **no WAYLAND_DISPLAY
  set** (protocol.py pure; wlwire only opens a socket in `Client.__init__`).
- (d) The JSONL contract is pinned: requests `acquire|show|verify|leave|ping` (＋ vocabulary-reserved
  `cancel`), every request with `id` gets exactly one reply echoing it; `show` replies carry a
  `result` field ∈ the `ShowResult` words; unknown request → error reply, host keeps serving;
  async events are id-less `{"ev": name, "t_ms": ...}` lines; the event log stops appending at
  64 KiB.
- (e) `tools/im-lab/` is byte-identical (`git diff --stat tools/im-lab | wc -l` → 0) — the lab is
  R.2 evidence, cited by path.
- (f) NO change to `systemd/`, `config.toml`, `voice_typing/config.py`, `hypr-binds.conf`,
  `pyproject.toml`, `voice_typing/daemon.py`, `voice_typing/feedback.py`, `voice_typing/ctl.py`,
  `voice_typing/bulk_delivery.py`, `voice_typing/bulk_controller.py`.

## User Persona

**Target User**: (a) The P1.M4.T1.S2 / T2 / T3 / T4 implementers — this package is the transport
skeleton they build the subprocess lifecycle, acquire/verify semantics, atomic insert/correction, and
takeover detection on; (b) the operator, indirectly: nothing user-visible changes (no config, no
service, no bindings — the bulk path is not yet wired into the daemon).

**Use Case**: The S2 subprocess host does `python -m voice_typing.ime.ime_host <event-log-path>`;
the daemon writes `{"id":1,"cmd":"acquire"}` → the host replies `{"id":1,"reply":"acquire","ok":false,"reason":"not activated"}`;
later `{"id":2,"cmd":"show","session":...,"utterance":...,"seq":...,"expected_revision":...,"text":"..."}`
→ `{"id":2,"reply":"show","result":"applied","t_ms":41}`; asynchronously the host emits
`{"ev":"surrounding_text","t_ms":...,"cursor":...}` / `{"ev":"grab_key","key":...,"state":...}` lines
that T4's takeover logic consumes.

**Pain Points Addressed**: The proven transport currently lives only as spike instrumentation in
`tools/im-lab/` with a lab-specific ctl.sock; there is no daemon-importable, protocol-documented,
test-pinned package. This task creates the stable seam so four later tasks (S2, T2, T3, T4) implement
against a contract instead of re-deriving wire details.

## Why

- **The route is DECIDED (R.4): do not re-run route discovery.** The d2 map §5 verdict: wlwire is
  "the adapter transport skeleton", im_probe "evolve[s] into the TargetAdapter-side
  probe/controller". This task executes that REUSE verdict.
- **pywayland is NOT importable in the daemon venv** (verified) — the hand-rolled stdlib client is
  the decided lineage; the package must stay stdlib-only (no pyproject change).
- **Opcode tables are the highest-silent-blast-radius artifact in the transport**: a re-ordered entry
  sends a different request than intended (e.g. `delete_surrounding_text` vs `commit`). The XML-vs-
  table test makes drift loud forever (PRD R.2: "opcode tables must match the protocol XML
  (provenance: Hyprland-vendored …)" — im-lab README:29-33).
- **The JSONL protocol is the seam for four future tasks** (S2 lifecycle, T2 acquire, T3 show/
  finalize, T4 takeover via async events). Fixing the vocabulary NOW — with `ShowResult` words
  verbatim from the already-landed contracts module — prevents each future task from inventing its
  own wire dialect.
- **Mode A evidence discipline**: the package docstring carries the R.2 mechanism-evidence trail so
  nobody re-derives (or over-claims) it later.

## What

**1. `voice_typing/ime/wlwire.py`** — copy of `tools/im-lab/wlwire.py` (READ the lab file; copy
byte-for-byte then evolve) with exactly these changes:
- `Client.__init__(self, display=None, sock=None)` — optional pre-connected socket (socketpair or
  fake) for unit tests; when `sock` is given, skip display resolution/connect. Everything else
  (REQUESTS/EVENTS tables, `u32/i32/wstr`, `request`, `next_event`, `roundtrip`, `handle`, `bind`,
  fd handling) moves as-is.
- Module docstring: provenance line (Hyprland-vendored `input-method-unstable-v2.xml`,
  wlr-protocols lineage) + "tested against the vendored XML by tests/test_ime_wlwire.py".
- Keep closing received keymap fds (fd-leak discipline) and the 0xFF000000 id guard.

**2. `voice_typing/ime/protocol.py`** — NEW, pure stdlib (json only + typing). Contents:

```python
REQUEST_CMDS = ("acquire", "show", "verify", "leave", "ping")   # 'cancel' RESERVED (P1.M4.T3.S3)
SHOW_RESULTS = ("applied", "unchanged", "refused", "unknown")   # == ShowResult values, verbatim
LOG_CAP_BYTES = 64 * 1024                                       # im_probe lineage
SHOW_FIELDS = ("session", "utterance", "seq", "expected_revision", "text")

def encode(obj: dict) -> bytes          # json.dumps(..., ensure_ascii=False) + "\n"
def decode(line: str | bytes) -> dict   # json.loads; raises ProtocolError on bad JSON
def make_reply(id, cmd, **fields) -> dict    # {"id":id,"reply":cmd,**fields}
def make_error(id, message) -> dict          # {"id":id,"error":message}
def make_event(name, **fields) -> dict       # {"ev":name,"t_ms":round(...,3),**fields} — NO id
def validate_request(obj: dict) -> tuple[str|None, str|None]
    # (cmd, error): missing id or unknown cmd → error string; show → required SHOW_FIELDS present;
    #   acquire/verify/leave/ping take no required fields
class EventLogWriter:  # __init__(path: Path); append(obj) — no-op once byte cap reached; counts bytes
```

- `ProtocolError(ValueError)` for framing faults.
- Docstring = the wire contract (Mode A): one JSON object per line each way; requests carry caller
  `id`; replies echo `id` + `reply` (the cmd) + fields; `show` reply carries `result` ∈ SHOW_RESULTS;
  `acquire` reply carries `{ok, handle, revision, reason}` (AcquireResult shape verbatim); events are
  id-less and may interleave arbitrarily between replies.

**3. `voice_typing/ime/ime_host.py`** — evolved `tools/im-lab/im_probe.py`:
- `ImeHost(client, out, log_path)` — injected wlwire `Client` (or fake), output stream (daemon-side
  stdout), event-log path. Keeps the lab's state (`activated`, `dones`, `surround`, `grab`) and its
  become-IM sequence (`get_registry` → roundtrip → bind manager+seat → `get_input_method` → two
  roundtrips), reusing `protocol.make_event`/`EventLogWriter` instead of the probe's hand-rolled log.
- Serve loop: read stdin line-by-line (`for line in sys.stdin:` is acceptable — pipe close ends it);
  per line: `decode` → `validate_request` → dispatch → write ONE reply line to `out` (flush);
  errors → `make_error` reply, keep serving (the probe's survive-bad-rows posture). Between lines
  drain wlwire events non-blocking and forward as event lines + log entries.
- Request mapping (transport-level, semantics-free — T2/T3 own ownership logic):
  - `ping` → `make_reply(id,"ping", activated=..., dones=...)`.
  - `acquire` → if not activated: `make_reply(id,"acquire", ok=False, revision=0, reason="not activated")`;
    if activated: `ok=True, handle=<str: the im object id>, revision=<dones>` (a placeholder handle —
    T2 replaces with verified binding).
  - `show` → the probe's proven wire mechanics: optional
    `delete_surrounding_text(before,0)` + `commit_string(text)` + `commit(dones)` in ONE commit
    (insert = commit_string+commit; replace = delete+commit_string+commit, arg order per wlwire
    tables). Reply `result="applied", t_ms=...` when the wire send succeeded and a subsequent
    compositor `done` increments `dones` within a short bounded wait (reuse probe timing);
    `result="unknown"` on timeout, `result="refused"` when not activated. No retry, ever.
  - `verify` → reply with the last `surround` snapshot (`text_head`, `cursor`, `anchor`, `bytes`).
  - `leave` → release grab if held, reply `ok=True`, keep serving (S2 owns process exit; a `quit`
    escape command MAY exit — keep probe's `quit` for lab parity).
  - `cancel` → error reply `"cancel reserved (P1.M4.T3.S3)"`.
- `unavailable` event → log + event line + clean exit(0) (one-IM-per-seat; S2 marks the route
  unavailable).
- `main(argv)`: log path from argv[1] (default: `$XDG_RUNTIME_DIR/voice-typing/ime-events.jsonl`
  best-effort, else `/dev/null`); `ImeHost(Client(), sys.stdout, path).serve()`. Never run in the
  foreground of a test — unit tests use injected fakes only.

**4. `voice_typing/ime/__init__.py`** — Mode A docstring: purpose (IM-v2 primary-route transport,
R.4-decided), lineage (im-lab spike → this package; tools/im-lab kept as evidence), the R.2 evidence
trail (insert 26–40 ms cmd→field; ONE atomic commit `delete_surrounding_text(before,0)` +
`commit_string` + `commit(serial)` corrects a whole 1024-byte span byte-exactly with 1–2 internal
changed-signals; `surrounding_text` byte-exact cursor/anchor up to 1024 B; `commit_string` generates
ZERO key events so delivery cannot self-trigger takeover), the field-class matrix summary
(GTK-class full / foot+kitty insert-only / ghostty dead), and "a passing transport probe is mechanism
evidence only — never acceptance" (R.2). Re-export `protocol` symbols for convenience.

**5. Fixture**: `tests/fixtures/input-method-unstable-v2.xml` — fetched ONCE by the implementer:
`curl -sf -o tests/fixtures/input-method-unstable-v2.xml https://raw.githubusercontent.com/hyprwm/Hyprland/main/protocols/input-method-unstable-v2.xml`
(verified reachable). Committed (fixtures are the only evidence that enters version control). A
header comment may NOT be added (XML must stay parseable; provenance is documented in the test +
wlwire docstring).

**6. Tests** (all pure/CUDA-free):

`tests/test_ime_wlwire.py`:
- `test_opcode_tables_match_vendored_xml` — parse the XML with `xml.etree.ElementTree`; for each
  `<interface name="zwp_...">` build `{entry_name: arg_kinds}` from child `<request>`/`<event>`
  elements in DOCUMENT ORDER (arg kind map: `uint→u int→i string→s object→o new_id→n fd→h`;
  note the XML uses `<arg name="..." type="..."/>` — order of `<arg>` children is the wire order);
  assert equal to wlwire's `REQUESTS[iface]` / `EVENTS[iface]` for the three zwp_* interfaces
  (both requests and events; arg-name lists too, cheaply, via the name attributes).
- `test_wstr_layout` — `wstr("hi")` == 4-byte len prefix (3) + b"hi\0" + one pad byte; total
  multiple of 4; utf-8 encoding; NUL counted in length.
- `test_u32_i32_bytes` — little-endian packing; i32 negative wrap.
- `test_request_message_bytes` — build `Client.__new__(Client)` (bypass connect), set `s` to a fake
  recording `sendall`; call `request(obj, "zwp_input_method_v2", "commit_string", "ab")`; assert
  bytes == `struct.pack("<IHH", obj, 0, 8+len)` + payload (opcode 0 = first entry) — and that
  `delete_surrounding_text` gets opcode 2, `commit` opcode 3 (order-of-tables pin).
- `test_unknown_request_raises` / `test_id_space_guard`.

`tests/test_ime_protocol.py`:
- encode/decode round trip incl. Unicode + embedded newline (dumps escapes it — one line out);
  `decode` of garbage raises `ProtocolError`.
- `validate_request`: each legal cmd passes; missing `id` → error; unknown cmd → error; `show`
  missing any SHOW_FIELDS → error naming the field; extra fields tolerated.
- reply/event constructors: id echo; event lines have NO `id` and DO have `ev` + `t_ms`;
  SHOW_RESULTS == the four ShowResult values (import from `voice_typing.bulk_delivery` and compare
  `{r.value for r in ShowResult}` — the cross-module pin).
- `EventLogWriter` (tmp_path): appends lines until byte cap, then no-ops; cap honored at
  64 KiB (write ~200 × 400-byte events; assert file ≤ cap + one line).

`tests/test_ime_host.py` (no compositor — fake client):
- A `_FakeWire` with the probe-relevant surface (`s` = None; scripted `next_event` returns; a
  `request()` recorder). Host over `io.StringIO` in/out: ping→reply; unknown→error reply + loop
  survives; acquire while deactivated→`ok False, reason "not activated"`; show while activated with
  a scripted `done` event→`result "applied"`; show with no done within timeout→`"unknown"`;
  leave→ok; event forwarding: a scripted `surrounding_text` event lands on out + the capped log;
  `unavailable` → clean return/exit.

### Success Criteria

- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_ime_wlwire.py tests/test_ime_protocol.py tests/test_ime_host.py -q` → all pass.
- [ ] `env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime, voice_typing.ime.protocol, voice_typing.ime.wlwire; print('ok')"` → ok.
- [ ] `git status --porcelain` shows ONLY the new files (`voice_typing/ime/*`, `tests/test_ime_*.py`,
      `tests/fixtures/input-method-unstable-v2.xml`); `git diff --stat tools/im-lab | wc -l` → 0.
- [ ] `grep -rn 'pywayland' voice_typing/` → no hits (stdlib-only lineage).
- [ ] The existing fast suites still green (spot: `timeout 120 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_config.py -q`).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: both source files to copy are small (212 + 192
lines) and cited; the exact evolutions are enumerated; the protocol vocabulary + field names are
pinned; the XML fetch URL is verified reachable; the test matrix (opcode-vs-XML parsing recipe with
the arg-type map, framing tests, fake-client host tests) is fully specified; the fences (what S2/T2/
T3/T4 own) and the operator-surface prohibition are explicit.

### Documentation & References

```yaml
# MUST READ — this task's research: move map, pinned design, fences, tooling
- docfile: plan/008_a47116bb2b79/P1M4T1S1/research/ime_transport_package.md
  section: "ALL (§1 move map, §2 contracts served, §3 pinned design decisions, §4 test matrix, §5 fences)."

# MUST READ — the source being copied (READ tools/, COPY into voice_typing/ime/; leave tools/ untouched)
- file: tools/im-lab/wlwire.py
  why: "The transport skeleton: REQUESTS/EVENTS opcode tables (the artifact the XML test pins), u32/i32/wstr,
        Client (connect/new/bind/request/next_event/roundtrip/handle), fd discipline, id guard. Copy as-is;
        the ONLY evolution is the injectable sock= ctor arg."
- file: tools/im-lab/im_probe.py
  why: "The host lineage: become-IM sequence (registry→bind manager+seat→get_input_method→2 roundtrips),
        the select/serve loop, the proven wire mechanics (insert = commit_string+commit;
        replace = delete_surrounding_text+commit_string+commit; preedit), state (activated/dones/surround/
        grab), the 64 KiB log cap, survive-bad-rows posture, unavailable→WlError. Evolve into ImeHost."
  gotcha: "im_probe serves a ctl.SOCK — the package serves stdin/stdout (S2 pipes). Do NOT carry the socket code."

# MUST READ — the contracts module whose vocabulary the protocol carries verbatim (READ-ONLY)
- file: voice_typing/bulk_delivery.py
  why: "ShowResult words (applied|unchanged|refused|unknown — 'serialized verbatim into status/log
        lines'), AcquireResult shape (ok/handle/revision/reason), DeliveryTarget method names
        (acquire/show/finalize/leave/cancel) the wire vocabulary mirrors. The protocol test
        cross-pins SHOW_RESULTS == {r.value for r in ShowResult}."

# MUST READ — the reuse verdict + lab results (evidence trail source)
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  section: "§5 Lab-reuse table (wlwire REUSE, im_probe REUSE, hypr_nest THROWAWAY) + the open items
            carried forward (unavailable collision, 4000-byte commit cap → T3's concern)."
- file: tools/im-lab/README.md
  why: "The R.2 evidence numbers the package docstring must carry (26–40 ms insert; 1024 B one-commit
        correction; surrounding_text byte-exact; zero key events from commit_string) + opcode-table
        provenance (:29-33) + the field-class matrix. The durable record — cite, don't fork."

# MUST READ — the PRD spec this implements a slice of (READ-ONLY)
- docfile: PRD.md
  section: "§4.2sexies R.2 (evidence, do not re-derive), R.3 (the delivery model the vocabulary names),
            R.4 ('wlwire lineage is the decided transport'; do NOT re-run route discovery), R.5 (events/
            ordering vocabulary the async lines foreshadow)."
  gotcha: "R.4: 'Development MUST NOT change the operator's service, config, or bindings as a side
           effect' — no systemd/config.toml/hypr-binds/pyproject edits."

# READ — the parallel task's surface (do NOT touch its files)
- docfile: plan/008_a47116bb2b79/P1M3T3S2/PRP.md
  why: "In-flight (feedback.py/daemon.py/ctl.py status surface). Confirms the file fence in Success (f);
        nothing in voice_typing/ime/ may edit those files, and the package writes NO feedback fields."

# READ — operational discipline
- docfile: AGENTS.md
  section: "Rules 1-3 (timeout discipline; never foreground the daemon; bounded scratch — the event
            log is capped at 64 KiB BY DESIGN, keep it)."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/
├── bulk_delivery.py        # READ-ONLY: ShowResult/AcquireResult/DeliveryTarget (the vocabulary)
├── bulk_controller.py      # READ-ONLY
├── daemon.py / feedback.py / ctl.py  # FENCED (parallel task + M6 wiring)
└── (no ime/ yet)
tools/im-lab/               # READ-ONLY evidence: wlwire.py, im_probe.py, README.md, …
tests/
├── fixtures/               # (create; add the vendored XML here)
└── test_bulk_delivery.py   # the contracts suite (regression spot-check)
```

### Desired Codebase tree with files to be added

```bash
voice_typing/ime/
├── __init__.py       # Mode A docstring: R.2 evidence trail + lineage + matrix; re-export protocol
├── wlwire.py         # evolved copy of tools/im-lab/wlwire.py (+ injectable sock=)
├── protocol.py       # NEW pure: REQUEST_CMDS/SHOW_RESULTS/LOG_CAP, encode/decode, constructors,
│                     #   validate_request, EventLogWriter, ProtocolError — the wire contract docs
└── ime_host.py       # evolved im_probe: ImeHost(client, out, log_path) + stdin/stdout main()
tests/
├── fixtures/input-method-unstable-v2.xml   # vendored once via curl (verified URL)
├── test_ime_wlwire.py     # opcode tables vs XML + wire byte-layout units
├── test_ime_protocol.py   # JSONL framing + vocabulary + log cap
└── test_ime_host.py       # fake-client serve-loop dispatch tests
# NOTHING ELSE. tools/im-lab byte-identical. No pyproject/config/systemd/hypr-binds changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — COPY, DO NOT MOVE. tools/im-lab/* is the R.2 evidence record cited by path (d2 §5,
#   README). The package is the evolved lineage. `git diff --stat tools/im-lab | wc -l` must be 0.

# CRITICAL #2 — OPCODE ORDER IS THE CONTRACT. wlwire's tables are (name, kinds) lists whose INDEX is
#   the opcode. The XML test must compare ORDER + names + arg kinds for the three zwp_* interfaces.
#   XML <arg> children give the wire order; type map uint→u int→i string→s object→o new_id→n fd→h.
#   The core wl_* tables are NOT in this XML (they come from wayland.xml) — pin those by literal
#   expectations (opcode of commit_string=0, delete_surrounding_text=2, commit=3 — the test_request_
#   message_bytes assertions do it).

# CRITICAL #3 — WAYLAND ABSENCE MUST NOT BREAK IMPORTS. protocol.py is pure; wlwire must not resolve
#   WAYLAND_DISPLAY at import time (it doesn't — only in Client.__init__). The host's Client() call
#   happens in main()/serve(), never at module import. Gate (c) asserts this.

# CRITICAL #4 — NEVER RETRY show, NEVER BLOCK THE LOOP. An op whose outcome can't be confirmed is
#   "unknown" (R.5) — one bounded wait, reply, move on. The serve loop must keep draining events and
#   answering subsequent requests even after an error/timeout reply.

# CRITICAL #5 — EVENT LINES ARE THE T4 TAKEOVER FEED. grab key/keymap/modifiers, activate/deactivate,
#   surrounding_text, done, unavailable must ALL flow to stdout as id-less {"ev":...} lines (not just
#   to the log) — takeover detection (P1.M4.T4) subscribes at this seam. Keep the probe's head-
#   truncated surrounding_text (text[:80]) in BOTH channels: counts/times discipline, no document dumps.

# CRITICAL #6 — STDLIB ONLY, NO NEW DEPS. pyproject.toml is fenced. json/select/socket/struct/os/sys/
#   pathlib/xml.etree (test-side only) suffice — the whole point of the wlwire lineage.

# CRITICAL #7 — THE EVENT LOG IS BOUNDED SCRATCH (AGENTS.md Rule 3). Keep the 64 KiB cap semantics:
#   append lines while total ≤ cap, then silently no-op. It writes under $XDG_RUNTIME_DIR (tmpfs) —
#   the cap is what makes that safe.

# GOTCHA #8 — TIMEOUTS + FULL PATHS (AGENTS.md Rule 1; zsh aliases python). All pytest runs:
#   `timeout 120 .venv/bin/python -m pytest ...`. The new suites are pure/fast; never spawn a real
#   compositor or the daemon from tests. curl (fixture fetch) gets `timeout 30`.

# GOTCHA #9 — DON'T IMPLEMENT THE FENCED SEMANTICS. acquire's handle/revision here is a PLACEHOLDER
#   (pass-through), show does no ownership/units verification (T2), no chunking strategy (the
#   4000-byte commit question is T3's), no takeover policy (T4), no subprocess supervision (S2).
#   Shipping more than the transport is scope creep that collides with four planned tasks.
```

## Implementation Blueprint

### Data models and structure

```python
# protocol.py — the wire vocabulary (pure; see What §2 for the full API list)
REQUEST_CMDS = ("acquire", "show", "verify", "leave", "ping")  # + reserved "cancel"
SHOW_RESULTS = ("applied", "unchanged", "refused", "unknown")  # cross-pinned to bulk_delivery.ShowResult
class ProtocolError(ValueError): ...
# No dataclasses needed: requests/replies/events are plain dicts on the wire (JSONL).
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT (no mutation)
  - RUN: ls tools/im-lab/wlwire.py tools/im-lab/im_probe.py; grep -c '' tools/im-lab/wlwire.py   # 212
         grep -n 'REQUESTS\|EVENTS' voice_typing/ -r | head -3   # confirm no existing collision
         timeout 30 curl -sfI https://raw.githubusercontent.com/hyprwm/Hyprland/main/protocols/input-method-unstable-v2.xml | head -1
         test ! -e voice_typing/ime && echo "ok: no ime/ yet"
  - EXPECTED: sources present; URL HTTP 200; no package; no name collisions.

Task 2: VENDOR THE FIXTURE + WRITE test_ime_wlwire.py (TDD RED)
  - RUN: mkdir -p tests/fixtures && timeout 30 curl -sf -o tests/fixtures/input-method-unstable-v2.xml \
      https://raw.githubusercontent.com/hyprland/Hyprland/main/protocols/input-method-unstable-v2.xml
  - WRITE tests/test_ime_wlwire.py per What §6 (opcode-vs-XML parser, wstr/u32/i32 layouts,
    request-bytes via Client.__new__ + fake socket, opcode pins, guards). Confirm RED (no package yet).

Task 3: CREATE voice_typing/ime/wlwire.py (copy + evolve)
  - COPY tools/im-lab/wlwire.py; add the sock= ctor arg; docstring provenance update.
  - RUN the wlwire tests → GREEN.

Task 4: WRITE tests/test_ime_protocol.py (RED) then CREATE voice_typing/ime/protocol.py (GREEN)
  - Per What §2/§6. Include the ShowResult cross-pin import from voice_typing.bulk_delivery.

Task 5: WRITE tests/test_ime_host.py (RED) then CREATE voice_typing/ime/ime_host.py (GREEN)
  - Evolve im_probe per What §3 (injected client/out/log; stdin/stdout serve; dispatch table;
    event forwarding; unavailable exit; bounded wait; no retry).
  - CREATE voice_typing/ime/__init__.py (Mode A evidence docstring + re-exports).

Task 6: VALIDATE — full Validation Loop; git scope guard; tools/im-lab untouched; no-deps guard.
  - If the orchestrator directs a commit: "P1.M4.T1.S1: voice_typing/ime transport package
    (wlwire lineage) + JSONL protocol + opcode/XML + framing tests".
```

### Implementation Patterns & Key Details

```python
# The XML opcode-table parser (the heart of test_ime_wlwire.py):
import xml.etree.ElementTree as ET
KIND = {"uint": "u", "int": "i", "string": "s", "object": "o", "new_id": "n", "fd": "h"}
def xml_entries(root, iface, tag):  # tag in ("request", "event")
    el = next(e for e in root.findall("interface") if e.get("name") == iface)
    return [(e.get("name"), "".join(KIND[a.get("type")] for a in e.findall("arg")))
            for e in el.findall(tag)]
# assert xml_entries(root, "zwp_input_method_v2", "request") == [(n, k) for n, k in
#        ime.wlwire.REQUESTS["zwp_input_method_v2"]]   # (name, kinds) tuples, document order

# The serve-loop dispatch (survive-bad-rows; one reply per id; events interleaved):
for line in sys.stdin:
    try:
        obj = protocol.decode(line)
        cmd, err = protocol.validate_request(obj)
        reply = self._dispatch(cmd, obj) if not err else protocol.make_error(obj.get("id"), err)
    except protocol.ProtocolError as e:
        reply = protocol.make_error(-1, f"bad json: {e}")
    self.out.write(protocol.encode(reply).decode()); self.out.flush()
    self._drain_events()   # forwards + logs; never raises

# show's ONE-commit mechanics (proven in the lab; keep arg order from the tables):
if before: self.client.request(self.im, IFACE, "delete_surrounding_text", before, 0)
self.client.request(self.im, IFACE, "commit_string", text)
self.client.request(self.im, IFACE, "commit", self.dones)
```

### Integration Points

```yaml
PACKAGE SEAM (consumed downstream, nothing wired here):
  - P1.M4.T1.S2: "spawns `python -m voice_typing.ime.ime_host <log>`; monitors via ping; owns teardown"
  - P1.M4.T2/T3: "acquire/verify/show semantics over this protocol (replace the placeholder handle)"
  - P1.M4.T4: "takeover detection consumes the id-less {\"ev\":...} stdout lines"
  - P1.M6.T2.S1: "daemon-side wiring (the only writer of feedback delivery fields)"
IMPORTS: "voice_typing.ime.protocol imports NOTHING from the daemon/streaming/backends (mirror of
          bulk_delivery's purity rule); ime_host imports wlwire + protocol only."
NO INTEGRATION TOUCHED: "no config/service/bindings/pyproject/feedback/daemon/ctl changes (fence)."
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile voice_typing/ime/*.py tests/test_ime_*.py && echo "L1 OK"
env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime, voice_typing.ime.protocol, voice_typing.ime.wlwire, voice_typing.ime.ime_host; print('L1 imports ok (no WAYLAND_DISPLAY)')"
```

### Level 2: Unit tests (the gate)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_ime_wlwire.py tests/test_ime_protocol.py tests/test_ime_host.py -q
# Expected: 0 failed. If the opcode test fails: read WHICH interface/entry diverged — the XML is
# authoritative; fix the table (and note it: a table/XML mismatch here is exactly the silent-blast-
# radius drift this test exists to catch).
```

### Level 3: Protocol smoke (fake duplex, no compositor)

```bash
timeout 60 .venv/bin/python - <<'EOF'
import io
from voice_typing.ime import protocol
from voice_typing.ime.ime_host import ImeHost
class FakeWire:  # minimal client double: not activated, no events
    s = None; ifaces = {1: "wl_display"}; globals = {}
    def request(self, *a, **k): pass
    def next_event(self, t=0): return None
    def roundtrip(self, t=5): pass
out = io.StringIO()
host = ImeHost(FakeWire(), out, None)   # log_path None → logging disabled
host.handle_line(protocol.encode({"id": 1, "cmd": "ping"}).decode())
host.handle_line(protocol.encode({"id": 2, "cmd": "acquire"}).decode())
host.handle_line(protocol.encode({"id": 3, "cmd": "bogus"}).decode())
host.handle_line(protocol.encode({"id": 4, "cmd": "show", "session": 9, "utterance": "u1",
                                  "seq": 1, "expected_revision": 0, "text": "hi"}).decode())
lines = [protocol.decode(l) for l in out.getvalue().splitlines()]
assert lines[0]["id"] == 1 and "activated" in lines[0]
assert lines[1]["id"] == 2 and lines[1]["ok"] is False and lines[1]["reason"] == "not activated"
assert lines[2]["id"] == 3 and "error" in lines[2]
assert lines[3]["id"] == 4 and lines[3]["result"] in protocol.SHOW_RESULTS
print("L3 OK:", *lines, sep="\n  ")
EOF
# (If ImeHost exposes the loop only via serve(), expose handle_line()/a testable dispatch — the
#  point is: request→exactly-one-reply with id echo, errors survive, wrong-state show degrades to
#  refused/unknown — never a crash, never a retry.)
```

### Level 4: Scope & lineage guards

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain
# Expected ONLY new files: voice_typing/ime/{__init__,wlwire,protocol,ime_host}.py,
#   tests/test_ime_{wlwire,protocol,host}.py, tests/fixtures/input-method-unstable-v2.xml
git diff --stat tools/im-lab | wc -l        # → 0 (Critical #1)
grep -rn 'pywayland' voice_typing/ || echo "ok: stdlib lineage"
git diff --stat voice_typing/daemon.py voice_typing/feedback.py voice_typing/ctl.py voice_typing/bulk_delivery.py voice_typing/bulk_controller.py config.toml pyproject.toml systemd/ hypr-binds.conf | wc -l   # → 0
timeout 120 .venv/bin/python -m pytest tests/test_bulk_delivery.py -q | tail -1   # vocabulary module untouched
timeout 120 .venv/bin/python -c "import xml.etree.ElementTree as ET; ET.parse('tests/fixtures/input-method-unstable-v2.xml'); print('fixture parses')"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 green; three new suites pass; fixture parses; imports work without WAYLAND_DISPLAY.
- [ ] Opcode tables == vendored XML for all three zwp_* interfaces (requests + events, names + kinds + order).
- [ ] SHOW_RESULTS cross-pinned to `bulk_delivery.ShowResult` values.
- [ ] `git status --porcelain` = exactly the 7 new files; tools/im-lab untouched; fenced files untouched.

### Feature Validation
- [ ] JSONL contract pinned by tests: id echo, one reply per request, event lines id-less, unknown→error+survive, log cap 64 KiB.
- [ ] Wire mechanics preserved verbatim (insert/replace/commit ordering; one commit per op; no retry).
- [ ] `unavailable` → clean exit path; events forwarded on stdout (the T4 feed).
- [ ] Mode A docstring carries the four R.2 evidence facts + matrix + "mechanism evidence only".

### Code Quality Validation
- [ ] Package mirrors repo style (module docstrings, `from __future__ import annotations`, stdlib only).
- [ ] protocol.py imports nothing from daemon/streaming/backends (purity mirror).
- [ ] Fences respected (no S2/T2/T3/T4 semantics shipped).

### Documentation & Deployment
- [ ] wlwire provenance line; __init__ evidence trail; protocol docstring = the wire contract.
- [ ] No new env vars, config keys, commands, or deps.

## Anti-Patterns to Avoid

- ❌ Don't move/delete/modify `tools/im-lab/*` — it is cited evidence (Critical #1).
- ❌ Don't hand-adjust opcode tables to "fix" a failing XML test without reading the XML — the XML is
      authoritative; a mismatch is exactly the drift the test exists to catch (Critical #2).
- ❌ Don't import wlwire/ime_host at package import time in a way that requires a Wayland display, and
      don't resolve WAYLAND_DISPLAY outside `Client.__init__` (Critical #3).
- ❌ Don't retry a timed-out show or block the serve loop on one request (Critical #4) — `unknown`,
      reply, keep serving.
- ❌ Don't swallow events into the log only — stdout event lines are the T4 takeover feed (Critical #5).
- ❌ Don't add dependencies, config, service, or binding changes (Critical #6, R.4 operator-surface rule).
- ❌ Don't implement acquire/verify/show semantics, chunking, takeover policy, or subprocess
      supervision — S2/T2/T3/T4 own them (Critical #9).
- ❌ Don't run pytest/curl without GNU `timeout` + `.venv/bin/python` (Gotcha #8).

---

**Confidence Score: 9/10.** The core artifacts already exist and are proven (the lab client ran the
full 29-row matrix); this task is a copy-with-two-evolutions plus one new pure module and mechanical
tests. The riskiest piece — the XML-vs-opcode-table parser — has a fully specified recipe (document
order, arg-type map) and a verified-reachable XML. −1 reserves: (a) the ime_host serve loop's exact
dispatch shape is left to the implementer within the pinned contract (the L3 smoke + host tests
constrain it); (b) XML interface scope (zwp_* only vs also core wl_*) could surprise — Critical #2
fences it explicitly (the vendored file contains only the IM protocol).

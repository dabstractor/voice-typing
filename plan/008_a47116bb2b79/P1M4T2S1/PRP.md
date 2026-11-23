# PRP — P1.M4.T2.S1: `acquire()` — field binding, verification, units mapping (`voice_typing/ime/target.py` + evolved `_acquire`)

## Goal

**Feature Goal**: Ship the **verified acquire** for the IM-v2 primary route (PRD §4.2sexies R.3): bind
the specific **editable field** — not a window/process/position — by VERIFYING it through
`surrounding_text` (byte-exact cursor/anchor = R.5's third distinct value: **target-CONFIRMED
text**), refuse BEFORE delivery for fields that cannot be ownership-verified (no snapshot ⇒
insert-only/dead class) or carry a **pre-existing user selection** (never replace by default), map
all positions in the target's own units (**UTF-8 bytes** — the wire's unit) via
`bulk_delivery.map_span`/`TargetUnits`, and provide the **mutation-time re-check helpers**
(focus/caret/selection/ownership) that `show()` (P1.M4.T3.S1) consumes. Two layers: the S1 host's
`_acquire`/`_verify` evolve from placeholder passthrough to snapshot-carrying transport; a NEW
daemon-side `ImeTarget` adapter owns the binding/verification/units semantics over the S2
`ImeProcess.request()` duck surface.

**Deliverable** (2 evolved/new source files + 3 test files; everything else fenced):
1. `voice_typing/ime/ime_host.py` — **EVOLVE** (the ONLY existing file modified): `_acquire` gains the
   bounded snapshot wait/drain + returns the full bounded snapshot fields; `_verify` returns the full
   bounded snapshot (the `:80` head-truncation moves to event-LOG lines only, where it already
   exists); + 2 module constants. S1's own docstring names this: "acquire's handle/revision is a
   placeholder passthrough; … T2 replaces with verified binding".
2. `voice_typing/ime/target.py` — **CREATE**: `ImeTarget` (`acquire() -> AcquireResult`,
   `recheck(...)`, `binding_caret_after`, `to_bytes_span`) + the frozen `FieldBinding` handle.
   Duck-types `proc` (`.request(cmd, timeout=..., **fields)`); NEVER imports manager/daemon/feedback.
3. `tests/test_ime_target.py` — **CREATE**: the fake-proc unit suite (the required gate).
4. `tests/test_ime_host.py` — **APPEND**: host acquire/verify verification tests (existing tests
   unchanged).
5. `tests/ime_acquire_lab.py` — **CREATE** (NON-collected driver, name has no `test_` prefix): the
   env-gated GTK-harness evidence rows (disposable desktop, per the im-lab pattern).

**Success Definition**:
- (a) `timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py
  tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_bulk_delivery.py -q` → all green;
  `git status --porcelain` shows ONLY the files above.
- (b) `env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime.target"` succeeds; target.py
  imports only stdlib + `voice_typing.bulk_delivery` + (nothing from manager/daemon/feedback).
- (c) Host `_acquire`: not-activated → `ok=False, reason="not activated"` (unchanged); activated +
  cached snapshot → `ok=True, handle=str(im), revision=dones` PLUS `text` (bounded head),
  `cursor`, `anchor` (byte offsets), `snapshot_truncated: bool`; activated + NO snapshot after the
  bounded wait → `ok=False, reason="no surrounding text"`. `_verify` replies the same snapshot
  shape (+ `activated`, `dones`).
- (d) Daemon `ImeTarget.acquire()`: returns `AcquireResult`; **refusal taxonomy** (each test-pinned):
  no reply → `"ime no reply"`; not activated → propagated `"not activated"`; no snapshot → propagated
  `"no surrounding text"`; **`cursor != anchor` → `"user selection present"`** (the R.3
  never-replace-a-selection guard); inconsistent snapshot (`cursor`/`anchor` > byte length, negative)
  → `"inconsistent snapshot"`; truncated snapshot (cursor beyond the sent head) →
  `"snapshot truncated"`. Success: `handle` = frozen `FieldBinding`, `revision` = dones, and the
  adapter's `units is TargetUnits.UTF8_BYTES`.
- (e) `FieldBinding` carries `im_handle`, `cursor_bytes`, `anchor_bytes`, `pre_caret` (str, bounded),
  `revision` — everything `recheck` needs; `pre_caret` is sliced from the ORIGINAL snapshot text
  (byte-derived, never a normalized/lowercased copy).
- (f) `recheck(binding, inserted_bytes=0) -> (ok, reason, current_revision)`: ONE fresh `verify`
  pull; branches per research §4 (no-reply / deactivated / no-snapshot / selection / caret-moved /
  adjacent-text-changed / ok); **never mutates**; expected caret = `binding.cursor_bytes +
  inserted_bytes`; post-caret changes do NOT revoke. `binding_caret_after` +
  `to_bytes_span(text, sc, ec)` (thin `map_span(..., UTF8_BYTES)` wrapper) exported for T3.
- (g) `acquire()` passes `timeout=2.5` on BOTH its requests (host snapshot wait is 1.0 s; S2's
  default 1.0 s request timeout would otherwise race — asserted in tests).
- (h) The GTK-harness driver runs ONLY under `IME_ACQUIRE_LAB=1` (+ `timeout 300`), reproduces the
  three rows (seeded-char ok / Ctrl+A selection refused / optional terminal no-snapshot refused),
  prints one verdict line each, and touches NOTHING outside its private seat. Default `pytest` runs
  it NEVER (no `test_` prefix; no autouse fixture).
- (i) NO out-of-scope code: no show/finalize/cancel/leave semantics (T3), no takeover policy (T4),
  no pi seam/clipboard (M5), no daemon/feedback/ctl/bulk_* edits (M6), no config/pyproject/systemd/
  hypr-binds changes, `protocol.py`/`wlwire.py`/`tools/im-lab/` byte-identical, NO `manager` import.

## User Persona

**Target User**: Internal — **P1.M4.T3.S1** (insert path) constructs `ImeTarget(proc)` and calls
`acquire()` at arm, then `recheck(binding, inserted_bytes=...)` + `to_bytes_span(...)` before every
`show()`; **P1.M4.T4** (takeover) complements these helpers with the `on_event` feed;
**P1.M6.T2.S1** wires it into the daemon. No end-user surface changes (bulk path still not armed).

**Use Case**: Bulk arm (M6): the daemon spawns the IM child (S2) → the seat activates it → the focused
GTK field pushes `surrounding_text("user text ", cursor=9, anchor=9)` → the daemon calls
`ImeTarget.acquire()` → the host's cached snapshot (byte-exact) flows back → no selection, offsets
consistent → `AcquireResult(ok=True, handle=FieldBinding(pre_caret="user text ", cursor_bytes=9,
...), revision=dones)` → T3 types at byte offset 9, and before EACH edit `recheck` re-pulls verify
and proves caret/selection/pre-caret still match — a queued op that lost the field refuses, never
mutates. If the user had selected text (Ctrl+A), acquire REFUSES up front — the selection is never
replaced. In foot/kitty (no `surrounding_text` ever) acquire refuses `"no surrounding text"` — the
field is exactly R.3's "unidentified" and delivery must not start on the IM route.

**Pain Points Addressed**: (1) S1's acquire is a placeholder (`handle=str(im)`, no verification) — any
field, any state, "bound". (2) R.3 requires binding the FIELD with fail-before-delivery semantics —
only `surrounding_text` provides target-CONFIRMED evidence on this route. (3) The units trap: the
wire speaks UTF-8 BYTES while recognition text is Python chars — without `map_span`, a single astral
character desyncs every delete range (the exact index-desync class R.3 forbids).

## Why

- **This is the first R.3 sentence made real**: "bind the SPECIFIC editable field — not merely a
  window, terminal process, or screen position" — verified by the ONLY target-confirmed channel this
  route has (`surrounding_text`, lab-proven byte-exact to 1024 B; R.2).
- **T3 is blocked on a trustworthy handle**: show() must re-check "focus, caret, selection, and
  ownership … at mutation time" (R.3) — that requires exactly the binding + helpers this task ships.
- **The refusal taxonomy IS the safety model**: no-snapshot (insert-only class) must FAIL here —
  R.3: "Fail BEFORE delivery for … selected, or unidentified fields" — rather than deliver unverifiably;
  a user selection must never be replaced "by default". The alternative (bind to the window, or
  deliver without verification) is the R.2-labeled silent-corruption class.
- **Units are load-bearing**: `surrounding_text` cursor/anchor and `delete_surrounding_text` counts
  are UTF-8 BYTE offsets (per the vendored XML) — `bulk_delivery.map_span(..., TargetUnits.UTF8_BYTES)`
  on the ORIGINAL string is the mandated conversion (a normalized copy is the forbidden index-desync).
- **Small, fenced, unblocks T3/T4.** One evolved method pair + one new adapter module; consumes the
  landed S1 protocol and the S2 duck surface; every fence aligned with the S1/S2 PRPs' downstream maps.

## What

### 1. `voice_typing/ime/ime_host.py` — EVOLVE (the only modified file)

Add module constants:
```python
_SNAPSHOT_HEAD_BYTES = 64 * 1024   # generous vs the ~4 KiB practical cap; refuse rather than mis-slice
_SURROUND_WAIT_S = 1.0             # bounded poll for a first surrounding_text after activation
```

`_acquire(rid)` — replacement semantics (transport-level; daemon owns interpretation):
```python
def _acquire(self, rid) -> dict:
    if not self.activated:
        return protocol.make_reply(rid, "acquire", ok=False, handle="",
                                   revision=0, reason="not activated")
    # Bounded wait for a cached surrounding_text snapshot (the text-input side PUSHES it;
    # the IM cannot request it). Pump _drain_events so it can arrive.
    deadline = time.monotonic() + _SURROUND_WAIT_S
    while self.surround is None and time.monotonic() < deadline:
        self._drain_events()
        if self.surround is not None:
            break
        time.sleep(0.02)
    if self.surround is None:
        return protocol.make_reply(rid, "acquire", ok=False, handle="", revision=0,
                                   reason="no surrounding text")
    text, cursor, anchor = self.surround["text"], self.surround["cursor"], self.surround["anchor"]
    return protocol.make_reply(rid, "acquire", ok=True, handle=str(self.im),
                               revision=self.dones,
                               text=text[:_SNAPSHOT_HEAD_BYTES],   # str slice keeps chars whole
                               cursor=cursor, anchor=anchor,
                               snapshot_truncated=len(text) > _SNAPSHOT_HEAD_BYTES)
```
`_verify(rid)` — same snapshot shape (drop the `:80` truncation from the REPLY; the `:80` head
truncation in the EVENT line at ime_host.py:95 stays exactly as-is — counts discipline):
```python
def _verify(self, rid) -> dict:
    s = self.surround
    if s is None:
        return protocol.make_reply(rid, "verify", activated=self.activated, dones=self.dones,
                                   ok=False, reason="no surrounding text")
    text, cursor, anchor = s["text"], s["cursor"], s["anchor"]
    return protocol.make_reply(rid, "verify", activated=self.activated, dones=self.dones, ok=True,
                               text=text[:_SNAPSHOT_HEAD_BYTES], cursor=cursor, anchor=anchor,
                               snapshot_truncated=len(text) > _SNAPSHOT_HEAD_BYTES)
```
(Existing imports suffice — `time` is already imported if used elsewhere in the module; ADD
`import time` only if absent. The `handle=str(self.im)` placeholder value stays — opacity is the
contract; the SNAPSHOT fields are what makes it verified.)

### 2. `voice_typing/ime/target.py` — CREATE (the R.3 TargetAdapter's acquire half)

```python
"""voice_typing.ime.target — the IM-route TargetAdapter: verified acquire + re-checks (R.3).

...docstring: field-not-window binding; surrounding_text = target-CONFIRMED text (R.5's third
value); the refusal taxonomy; UTF-8-BYTES units via bulk_delivery.map_span on the ORIGINAL string;
the password/secret limitation (IM-v2 exposes no such signal — documented, not guessed)...
CONSUMES: a proc duck with request(cmd, timeout=..., **fields) -> dict | None  (ImeProcess, P1.M4.T1.S2)
CONSUMED BY: P1.M4.T3.S1 show() (recheck + to_bytes_span + binding_caret_after); P1.M4.T4 takeover.
FENCES: no show/finalize/cancel/leave semantics (T3); no manager/daemon/feedback import.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from voice_typing.bulk_delivery import AcquireResult, TargetUnits, map_span

_ACQUIRE_TIMEOUT_S = 2.5          # > host _SURROUND_WAIT_S (1.0) + margin; S2 default is 1.0 — PASS EXPLICITLY

@dataclass(frozen=True)
class FieldBinding:
    """The opaque AcquireResult.handle — everything recheck needs, nothing more."""
    im_handle: str
    cursor_bytes: int
    anchor_bytes: int
    pre_caret: str          # snapshot text before the caret, ORIGINAL slice (byte-derived), bounded
    revision: int

class ImeTarget:
    """Daemon-side adapter: acquire + mutation-time re-checks over the IM subprocess (R.3)."""
    units = TargetUnits.UTF8_BYTES     # the wire speaks UTF-8 byte offsets (XML: uint byte positions)

    def __init__(self, proc):          # duck: ImeProcess (S2) or a test fake
        self._proc = proc

    # --- acquire (R.3): bind the FIELD, verify via target-CONFIRMED snapshot, refuse otherwise ---
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
        nbytes = len(text.encode("utf-8"))
        if r.get("snapshot_truncated") or not (0 <= cursor <= nbytes and 0 <= anchor <= nbytes):
            return AcquireResult(ok=False, reason="snapshot truncated" if r.get("snapshot_truncated")
                                 else "inconsistent snapshot")
        if cursor != anchor:
            return AcquireResult(ok=False, reason="user selection present")   # R.3: never replace
        pre = text.encode("utf-8")[:cursor].decode("utf-8", errors="ignore")  # ORIGINAL bytes
        binding = FieldBinding(im_handle=str(r.get("handle", "")), cursor_bytes=cursor,
                               anchor_bytes=anchor, pre_caret=pre, revision=int(r.get("revision", 0)))
        return AcquireResult(ok=True, handle=binding, revision=binding.revision)

    # --- mutation-time re-check helpers (R.5): consumed by show() (T3). ONE fresh verify pull. ---
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
        expected = binding.cursor_bytes + inserted_bytes
        if cursor != expected:
            return False, "caret moved", rev
        if not text.encode("utf-8")[:expected].endswith(binding.pre_caret.encode("utf-8")):
            return False, "adjacent text changed", rev          # adjacent user text was touched
        return True, "", rev                                     # post-caret changes do NOT revoke

    # --- units plumbing for T3 (never hand-roll offsets) ---
    @staticmethod
    def binding_caret_after(binding: FieldBinding, inserted_bytes: int) -> int:
        return binding.cursor_bytes + inserted_bytes

    @staticmethod
    def to_bytes_span(text: str, start_char: int, end_char: int) -> tuple[int, int]:
        return map_span(text, start_char, end_char, TargetUnits.UTF8_BYTES)   # ORIGINAL string only
```

### Success Criteria

- [ ] All 5 files as specified; the combined suites green under `timeout 120`; scope guard clean.
- [ ] Host: not-activated / no-snapshot / snapshot-carrying acquire replies + full-snapshot verify
      pinned (existing host tests UNCHANGED).
- [ ] Daemon: the 6-refusal taxonomy + happy path + Unicode/astral byte correctness pinned.
- [ ] `recheck` branches pinned; never mutates; `acquire` passes `timeout=2.5` (asserted).
- [ ] GTK driver: 3 rows under `IME_ACQUIRE_LAB=1` only; default pytest never runs it.
- [ ] Fences: protocol.py/wlwire.py/tools-im-lab byte-identical; no manager/daemon/feedback import.

## All Needed Context

### Context Completeness Check

_Pass._ The consumed S1 surface (state vars, `_acquire`/`_verify` at ime_host.py:146-152/:179-183,
`_drain_events`, cached `surround`) is quoted verbatim; the S2 duck surface is named; the
`bulk_delivery` vocabulary (`AcquireResult` fields, `TargetUnits.UTF8_BYTES`, `map_span` contract)
is quoted; the wire facts (byte offsets, push-only surrounding_text, dones-as-revision) come from
the vendored XML + R.2 lab evidence (do-not-re-derive); the full source for BOTH evolved/created
modules is pinned above; tests are specified case-by-case; validation commands are executable.

### Documentation & References

```yaml
# MUST READ — this task's design record (split rationale, wire facts, fences).
- docfile: plan/008_a47116bb2b79/P1M4T2S1/research/ime_acquire_design.md
  section: "ALL. §1 consumed contracts verbatim (incl. the S1 placeholder lines this task replaces),
            §2 the wire facts (BYTE offsets; push-only snapshot; selection=cursor!=anchor; dones),
            §3 host/daemon split, §4 the recheck contract, §5 test strategy, §6 fences."

# MUST READ — the file being EVOLVED (the only modified file).
- file: voice_typing/ime/ime_host.py
  why: "`_acquire` :146-152 (placeholder — replace per What §1), `_verify` :179-183 (:80 truncation
        moves to the EVENT line only — the event-line truncation at :95 stays), `self.surround`
        cache :92-95, `self.dones` bump :84-85, `_drain_events` :196+, `handle_line`/`_dispatch`
        :117-144 (one id-echoing reply; extra reply fields tolerated), `become_im` :57."
  gotcha: "Add `import time` ONLY if absent. Do NOT touch serve()/dispatch structure, event-line
           truncation, grab logic, or the `not activated` refusal (test-pinned)."

# MUST READ — the vocabulary + units machinery (READ-ONLY; target.py imports from it).
- file: voice_typing/bulk_delivery.py
  why: "`AcquireResult(ok, handle, revision, reason)` :92-105 (frozen; revision=0 unless ok),
        `TargetUnits.UTF8_BYTES` :166-173, `map_span` :185-215 (ORIGINAL string only; ValueError on
        malformed spans), the DeliveryTarget.acquire docstring :124-130 (the R.3 fail-before-delivery
        taxonomy this task implements for the IM route)."
  gotcha: "map_span counts UTF-8 offsets cumulatively — call it with the ORIGINAL str, NEVER a
           casefolded/normalized copy (R.3's index-desync rule)."

# MUST READ — the S1/S2 contracts (parallel-context lineage).
- docfile: plan/008_a47116bb2b79/P1M4T1S1/PRP.md
  why: "The JSONL contract (id echo; replies tolerate extra fields — that is what carries the new
        snapshot fields with ZERO protocol.py changes) + the R.2 evidence trail the design leans on
        (byte-exact surrounding_text to 1024 B; commit_string → zero key events)."
- docfile: plan/008_a47116bb2b79/P1M4T1S2/PRP.md
  why: "The `proc` duck surface this adapter consumes: request(cmd, timeout=..., **fields) -> dict|None
        (None on timeout/death; NO resend), on_event feed, states. Its Integration seam names
        'P1.M4.T2/T3 build the IM DeliveryTarget adapter ON this manager's request() surface'."
  critical: "manager.py may NOT be landed when you start (in flight) — target.py DUCK-TYPES proc and
             must not import it. Tests inject fakes regardless. Do NOT edit manager.py/S2's files."

# MUST READ — the lab harness pattern for the evidence rows (READ-ONLY; cited, never edited).
- file: tools/im-lab/imlab_run.py
  why: "The disposable-desktop pattern the GTK driver reproduces: xvfb-run + dbus-run-session + sway
        (private seat), field launch, scripted rows, verdict lines. Read it; copy the PATTERN into
        tests/ime_acquire_lab.py — do NOT edit the lab."
- file: tools/im-lab/field_gtk.py
  why: "The real GTK4 Gtk.Entry target (dumps text+cursor+edit-count atomically) — the R2/G3
        graphical-field fake target the driver launches."
  gotcha: "tools/im-lab is FENCED (git diff --stat tools/im-lab | wc -l → 0) — it is cited evidence."

# READ — grounding map + PRD slice + discipline.
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  section: "§5 lab-reuse table (field_gtk = the G3 graphical-field fake target), §9 risks 1/2/5/6
            (version drift; Hyprland row missing; terminals send no surrounding text; GTK decomposes
            correcting commits — 1-2 changed signals per commit cycle)."
- docfile: PRD.md
  section: "§4.2sexies R.3 (acquire/ownership/units — the normative source), R.5 (the three distinct
            values; mutation-time re-checks), R.2 (evidence; do not re-derive; a passing probe is
            never acceptance), R.4 (route DECIDED; no operator-surface changes)."
- docfile: AGENTS.md
  section: "Rules 1-3 (GNU timeout on everything; .venv/bin/python; never the live desktop; bounded
            scratch)."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/ime/                     # S1 LANDED: __init__.py, wlwire.py, protocol.py, ime_host.py
voice_typing/ime/manager.py           # S2 IN FLIGHT (may be absent — duck-type, never import)
voice_typing/bulk_delivery.py         # READ-ONLY (AcquireResult/TargetUnits/map_span)
voice_typing/bulk_controller.py       # FENCED
voice_typing/{daemon,feedback,ctl}.py # FENCED (M6 wiring owns them)
tools/im-lab/                         # READ-ONLY evidence (imlab_run.py, field_gtk.py, README.md)
tests/test_ime_{wlwire,protocol,host}.py   # S1 suites (host suite gets APPENDED tests)
tests/test_bulk_delivery.py           # regression spot-check
# NOT YET: voice_typing/ime/target.py, tests/test_ime_target.py, tests/ime_acquire_lab.py
```

### Desired Codebase tree with files to be added

```bash
voice_typing/ime/target.py        # CREATE: ImeTarget + FieldBinding (acquire + recheck + units plumbing)
tests/test_ime_target.py          # CREATE: fake-proc unit suite (~18 cases) — the required gate
tests/ime_acquire_lab.py          # CREATE: NON-collected env-gated GTK-harness evidence driver
tests/test_ime_host.py            # MODIFY: APPEND ~5 host acquire/verify tests (existing unchanged)
voice_typing/ime/ime_host.py      # MODIFY: _acquire/_verify evolve + 2 constants (per What §1)
# NOTHING ELSE. protocol.py/wlwire.py/tools-im-lab/daemon/feedback/ctl/bulk_*/config untouched.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — BYTE OFFSETS, NOT CHARS. surrounding_text cursor/anchor and delete_surrounding_text
#   counts are UTF-8 BYTE offsets (XML: uint byte positions into the UTF-8 string). Recognition text
#   is Python chars. EVERY char↔byte conversion goes through map_span(..., UTF8_BYTES) or explicit
#   .encode("utf-8") — on the ORIGINAL string, never a normalized copy (R.3's index-desync rule; an
#   astral char is 4 UTF-8 bytes / 2 UTF-16 units / 1 char — one hand-rolled offset = corrupted range).

# CRITICAL #2 — THE SNAPSHOT IS PUSH-ONLY. The IM CANNOT request surrounding_text; the text-input
#   side pushes it (at enable + after edits). Hence the host's bounded _drain_events poll (≤1.0 s) —
#   and hence foot/kitty (never send it) are CORRECTLY refused: "no surrounding text" is the
#   fail-before-delivery verdict for the unidentified/insert-only class on THIS route (R.3), not a bug.

# CRITICAL #3 — NEVER REPLACE A USER SELECTION. cursor != anchor in the target-CONFIRMED snapshot ⇒
#   refuse acquire AND recheck ("user selection present"). This is R.3 verbatim and the single most
#   safety-critical refusal — pin it in BOTH suites (unit + GTK row).

# CRITICAL #4 — recheck NEVER mutates and pulls FRESH state. It must re-derive everything from a new
#   `verify` request (R.5: "queued operations re-check at mutation time") — never trust the binding's
#   cached snapshot for the check itself. Expected caret = acquire caret + OUR inserted_bytes
#   (the caller's accounting); post-caret text changes do NOT revoke (the typing ACT is T4's signal).

# CRITICAL #5 — TIMEOUT BUDGET. Host snapshot wait 1.0 s; acquire/verify requests MUST pass
#   timeout=2.5 (S2's ImeProcess default is 1.0 s — a default-timeout acquire would race the wait and
#   return None spuriously). Assert the timeout value in a test.

# CRITICAL #6 — DO NOT SLICE BYTES MID-CHAR. The host head-caps with a STR slice (text[:65536] keeps
#   chars whole); the daemon computes pre_caret from text.encode()[:cursor].decode(..., "ignore") —
#   cursor is a valid byte boundary (the field produced it), so the slice is char-safe by construction;
#   a truncated snapshot is REFUSED, never sliced-through ("snapshot truncated").

# CRITICAL #7 — EXTRA REPLY FIELDS ARE THE EXTENSION MECHANISM. S1's JSONL tolerates extra fields in
#   replies — the snapshot fields ride acquire/verify replies with ZERO protocol.py changes. Do NOT
#   add request cmds, do NOT touch REQUEST_CMDS/SHOW_FIELDS, do NOT touch validate_request.

# CRITICAL #8 — PASSWORD/SECRET IS A DOCUMENTED LIMITATION. IM-v2 exposes no password hint; the
#   adapter CANNOT detect it. Record it in the module docstring (research §6). Do NOT invent a
#   heuristic (a wrong guess is worse than an honest limitation); other adapters own it where a
#   signal exists.

# GOTCHA #9 — GTK DECOMPOSITION IS EXPECTED. A correcting commit lands as 1-2 internal `changed`
#   signals within one commit cycle (d2 §9.6) — acquire/verify care about the SNAPSHOT, not the
#   signal count. Don't "fix" that; frame-level single-edit proof is G3 (T5).

# GOTCHA #10 — THE LAB DRIVER MUST STAY OUT OF THE DEFAULT GATE. Name it WITHOUT a test_ prefix
#   (tests/ime_acquire_lab.py), gate on IME_ACQUIRE_LAB=1, run under `timeout 300`, private seat
#   only (xvfb-run + dbus-run-session + sway per imlab_run) — never the live desktop, never
#   auto-collected. A lab row is mechanism evidence, never acceptance (R.2).

# GOTCHA #11 — TIMEOUTS + FULL PATHS (AGENTS.md Rule 1; zsh aliases python). Every command under GNU
#   timeout; pytest via .venv/bin/python. No real compositor in the unit suites; never foreground the
#   daemon; the driver's scratch (verdicts, logs) stays in a mktemp dir, bounded and torn down.
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/ime/target.py (see What §2 for the full pinned source)
@dataclass(frozen=True)
class FieldBinding:      # the opaque handle
    im_handle: str; cursor_bytes: int; anchor_bytes: int; pre_caret: str; revision: int
class ImeTarget:         # units=TargetUnits.UTF8_BYTES; acquire()/recheck()/binding_caret_after()/to_bytes_span()
# Host side: no new dataclasses — snapshot rides reply fields (text/cursor/anchor/snapshot_truncated).
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT (no mutation)
  - RUN:
      test -f voice_typing/ime/ime_host.py && test -f voice_typing/ime/protocol.py && echo "ok: S1 landed" \
        || echo "PREFLIGHT FAIL: S1 absent — STOP"
      test ! -e voice_typing/ime/target.py && test ! -e tests/test_ime_target.py && echo "ok: targets free"
      ls voice_typing/ime/manager.py 2>/dev/null || echo "note: S2 manager in flight — duck-type proc"
      env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime.ime_host; print('import ok')"
      timeout 120 .venv/bin/python -m pytest tests/test_ime_host.py tests/test_ime_protocol.py -q | tail -1
  - EXPECTED: S1 present + green; targets free; manager presence recorded (either way is fine).

Task 2: WRITE tests/test_ime_target.py FIRST (TDD RED) — the fake-proc matrix:
  _FakeProc(records .request calls; scripted replies/dead-None):
    happy path (snapshot, cursor==anchor) → AcquireResult.ok + FieldBinding fields + revision;
    pre_caret byte-derived from ORIGINAL text (Unicode + an astral char: cursor at a byte boundary
      INSIDE multibyte territory — pre_caret computed from bytes, not chars);
    no reply (None) → "ime no reply"; not activated → reason propagated;
    no surrounding text → propagated; cursor!=anchor → "user selection present";
    inconsistent (cursor>byte len / negative anchor) → "inconsistent snapshot";
    snapshot_truncated=True → "snapshot truncated";
    acquire passes timeout=2.5 on BOTH requests (fake asserts the kwarg);
    recheck: all 7 branches (no-reply/deactivated/no-snapshot/selection/caret-moved(with
      inserted_bytes>0 proving the arithmetic)/adjacent-changed/ok) + never sends a mutating cmd
      (fake asserts only "verify" was requested);
    to_bytes_span: char→byte round-trip incl. astral (4-byte) char; binding_caret_after arithmetic.
  DO NOT: import manager; spawn anything; need WAYLAND_DISPLAY.

Task 3: CREATE voice_typing/ime/target.py (per What §2) → GREEN.
Task 4: APPEND tests/test_ime_host.py (~5 cases) then EVOLVE voice_typing/ime/ime_host.py per What §1:
    activated+cached surround → ok=True WITH text/cursor/anchor/snapshot_truncated;
    activated+NO surround (fake never delivers one) → ok=False "no surrounding text";
    surround arrives LATE (fake queues it; host's poll+_drain_events catches it within the wait) → ok=True;
    verify: ok=True full text (NOT :80) + activated/dones; no snapshot → ok=False reason;
    existing tests UNTOUCHED (the "not activated" acquire refusal is already pinned — keep it).
  DO NOT: touch serve()/dispatch/protocol.py/wlwire.py/event-line truncation/grab logic.

Task 5: CREATE tests/ime_acquire_lab.py — the env-gated GTK evidence driver (pattern from
    tools/im-lab/imlab_run.py; READ that file first):
    private seat (xvfb-run dbus-run-session sway), launch OUR `python -m voice_typing.ime.ime_host`
    over pipes (S2-style Popen) + tools/im-lab/field_gtk.py as the target;
    R1: seed one char via the lab's synthetic-key mechanism → acquire → expect ok + byte-exact pre_caret;
    R2: Ctrl+A (selection) → acquire → expect REFUSED "user selection present";
    R3 (optional, skip gracefully if the binary/class is absent): a no-surrounding_text terminal row
        → expect REFUSED "no surrounding text";
    print ONE verdict line per row (row, ok/refused, reason); exit 0 iff expectations met;
    requires IME_ACQUIRE_LAB=1 (else prints "skipped (set IME_ACQUIRE_LAB=1)" and exits 0);
    scratch in mktemp -d with an EXIT trap (AGENTS.md Rule 3).
  DO NOT: run against the live desktop; edit tools/im-lab; make pytest collect it.

Task 6: VALIDATE — L1-L4; iterate until green. If the orchestrator directs a commit:
  "P1.M4.T2.S1: verified IM acquire — snapshot-carrying host + ImeTarget binding/units/rechecks".
```

### Implementation Patterns & Key Details

```python
# PATTERN — the fake proc (records + scripts; the ONLY injection seam):
class _FakeProc:
    def __init__(self, replies): self.calls = []; self._replies = list(replies)
    def request(self, cmd, timeout=None, **fields):
        self.calls.append((cmd, timeout, fields)); return self._replies.pop(0)
# assert proc.calls[0][0] == "acquire" and proc.calls[0][1] == 2.5

# PATTERN — byte-true pre_caret (CRITICAL #1/#6): slice BYTES, decode strictly-boundary-safe:
pre = text.encode("utf-8")[:cursor].decode("utf-8", errors="ignore")   # cursor is a field-produced boundary

# PATTERN — recheck's adjacent-text rule: fresh text_bytes[:expected_caret] must ENDSWITH the
# binding's pre_caret bytes (a user edit BEFORE our point shifts the prefix → refuse); equality is
# too strict (our own committed text extends the prefix past pre_caret).
```

### Integration Points

```yaml
PACKAGE SEAM (consumed downstream; nothing wired here):
  - P1.M4.T3.S1: "ImeTarget(proc).acquire() at arm; recheck(binding, inserted_bytes) +
                  to_bytes_span(...) before EVERY show(); expected_revision = acquire().revision"
  - P1.M4.T4: "takeover complements recheck via the on_event feed (revocation AT the target)"
  - P1.M6.T2.S1: "constructs ImeTarget(ImeProcess(...)) — the duck seam is the contract"
NO INTEGRATION TOUCHED: "no daemon.py/feedback.py/ctl.py/bulk_*/config/pyproject/systemd/
                          hypr-binds/manager.py/protocol.py/wlwire.py/tools-im-lab changes."
```

## Validation Loop

### Level 1: Syntax & purity

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile voice_typing/ime/target.py voice_typing/ime/ime_host.py \
  tests/test_ime_target.py tests/ime_acquire_lab.py && echo "L1 OK"
env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime.target as t; \
  print('pure import ok', t._ACQUIRE_TIMEOUT_S)"
grep -nE "from voice_typing.ime.manager|from voice_typing.daemon|from voice_typing.feedback" \
  voice_typing/ime/target.py || echo "ok: no manager/daemon/feedback import"
```

### Level 2: Unit tests (the gate)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py -q
timeout 120 .venv/bin/python -m pytest tests/test_ime_protocol.py tests/test_ime_wlwire.py \
  tests/test_bulk_delivery.py -q | tail -1        # S1 + vocabulary unregressed
# Expected: 0 failed everywhere. A host-suite failure → read WHICH acquire shape diverged (Task 4 list).
```

### Level 3: Fake duplex smoke (no compositor)

```bash
timeout 60 .venv/bin/python - <<'EOF'
from voice_typing.ime.target import ImeTarget
class FakeProc:
    def __init__(self, r): self.r = list(r); self.calls = []
    def request(self, cmd, timeout=None, **f):
        self.calls.append((cmd, timeout)); return self.r.pop(0)
snap = {"id": 1, "reply": "acquire", "ok": True, "handle": "im7", "revision": 3,
        "text": "héllo ", "cursor": 7, "anchor": 7, "snapshot_truncated": False}   # 7 bytes: h,é(2),l,l,o,space
p = FakeProc([snap, {"id": 2, "reply": "verify", "ok": True, "activated": True, "dones": 4,
                     "text": "héllo w", "cursor": 8, "anchor": 8, "snapshot_truncated": False}])
t = ImeTarget(p); a = t.acquire()
assert a.ok and a.handle.pre_caret == "héllo " and a.revision == 3, a
ok, why, rev = t.recheck(a.handle, inserted_bytes=1)
assert ok and rev == 4 and why == "", (ok, why, rev)
print("L3 OK", p.calls)
EOF
# Expected: L3 OK [('acquire', 2.5), ('verify', 2.5)] — byte-true pre_caret (é = 2 bytes), recheck ok.
```

### Level 4: Scope guards + the OPTIONAL GTK evidence row

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain   # ONLY: target.py, ime_host.py(M), test_ime_target.py, test_ime_host.py(M), ime_acquire_lab.py
git diff --stat tools/im-lab | wc -l                                    # 0
git diff --stat voice_typing/ime/protocol.py voice_typing/ime/wlwire.py \
  voice_typing/daemon.py voice_typing/feedback.py voice_typing/ctl.py \
  voice_typing/bulk_delivery.py voice_typing/bulk_controller.py config.toml pyproject.toml | wc -l   # 0
# Default pytest does NOT collect the driver:
timeout 120 .venv/bin/python -m pytest tests/ -q --collect-only 2>/dev/null | grep -c ime_acquire_lab || echo "ok: not collected"
# OPTIONAL evidence row (mechanism evidence only — never acceptance, R.2):
timeout 300 env IME_ACQUIRE_LAB=1 .venv/bin/python tests/ime_acquire_lab.py || echo "lab row failed/skipped — record honestly"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1-L4 green; all listed suites pass; import purity (no WAYLAND_DISPLAY, no manager import).
- [ ] `git status --porcelain` = exactly the 5 files; protocol/wlwire/tools-im-lab/fenced files clean.

### Feature Validation
- [ ] Host acquire: not-activated (unchanged) / no-snapshot / snapshot-carrying shapes pinned; verify full-snapshot.
- [ ] Daemon acquire: the 6-refusal taxonomy + happy path + Unicode/astral byte correctness pinned.
- [ ] recheck: 7 branches; never mutates; timeout=2.5 asserted; inserted_bytes arithmetic proven.
- [ ] Units: all conversions via map_span/encode on ORIGINAL text; to_bytes_span exported for T3.
- [ ] GTK rows (optional run): seeded-char ok / selection refused — recorded honestly either way.

### Code Quality Validation
- [ ] Mirrors repo style (CONSUMES/CONSUMED BY docstrings, `from __future__ import annotations`, stdlib-only).
- [ ] Existing test bodies untouched (append-only); anti-patterns avoided (no retries, no typing fallback,
      no manager import, no protocol edits).

### Documentation & Deployment
- [ ] target.py docstring: field-not-window rationale, the refusal taxonomy, the password limitation,
      the units rule. No new env vars beyond the driver's opt-in gate; no config/deps.

## Anti-Patterns to Avoid

- ❌ Don't hand-roll char↔byte offsets or slice a normalized/lowercased copy — map_span/encode on the
      ORIGINAL string only (Critical #1).
- ❌ Don't add request commands or touch protocol.py — extra REPLY fields are the extension mechanism (Critical #7).
- ❌ Don't "helpfully" deliver to a no-snapshot (insert-only) field — refusal IS the R.3 contract (Critical #2).
- ❌ Don't acquire over a user selection, and don't let recheck trust cached state — fresh verify pull
      every time (Critical #3/#4).
- ❌ Don't use the default request timeout for acquire/verify — 2.5 s explicitly (Critical #5).
- ❌ Don't implement show/finalize/cancel/leave/takeover/daemon wiring — T3/T4/M6 own them.
- ❌ Don't edit tools/im-lab, protocol.py, wlwire.py, manager.py, or any fenced file.
- ❌ Don't let pytest collect the lab driver or run it without the env gate; never the live desktop (Gotcha #10).
- ❌ Don't run anything without GNU timeout + `.venv/bin/python` (Gotcha #11).

---

**Confidence Score: 9/10.** Both consumed surfaces are landed-and-quoted (S1) or pinned-as-contract
(S2 duck type); the evolved/created source is fully pinned above including the byte-offset arithmetic;
the refusal taxonomy, recheck contract, and test matrix are case-enumerated; validation gates are
executable as written. −1: the GTK evidence row depends on the disposable-desktop environment being
reproducible from the imlab_run pattern (bounded risk — it is optional evidence with an honest
skip path; the unit suites are the required gate).

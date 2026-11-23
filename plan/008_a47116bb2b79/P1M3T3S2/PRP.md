# PRP — P1.M3.T3.S2: Delivery status surface: feedback fields + voicectl status rendering

## Goal

**Feature Goal**: Give bulk text delivery (PRD §4.2sexies R.5) its **status surface**: four
always-present, additive keys — `delivery_mode`, `delivery_state`
(`inactive|active|unsupported|fault`), `delivery_reason`, `last_confirmed_op` — in the
Feedback state file, surfaced through `status_snapshot()` into every control-socket status
reply, and rendered by `voicectl status` as delivery lines **after** the existing
`context-prompt:` line. This task builds the SURFACE ONLY (fields + setters + snapshot keys +
rendering + docs + tests); the bulk controller wiring that drives it is P1.M4/P1.M6.

**Deliverable** (6 modified files, nothing else):
1. `voice_typing/feedback.py` — 4 new `_state` keys + 3 set_phase-style setters (always
   write, never notify) + a whitespace-collapse/length-cap sanitizer for reason/op + Mode A
   state-field docs.
2. `voice_typing/daemon.py` — `status_snapshot()` gains the 4 additive keys read from the
   LIVE feedback snapshot (`.get` defaults, the `mic_*`/`context_prompt` precedent);
   docstring 14 → 18 keys.
3. `voice_typing/ctl.py` — `format_result` status branch renders `delivery: {mode}
   ({state})` always, plus `delivery reason:` / `delivery op:` lines only when non-empty;
   Mode A status-help doc updates.
4. `tests/test_feedback.py`, `tests/test_daemon.py`, `tests/test_voicectl.py` — extend the
   two exact-key-set assertions; add the TDD coverage for setters/snapshot/rendering.

**Success Definition**: All three suites green (`test_feedback.py`, `test_voicectl.py` fast;
`test_daemon.py -k status_snapshot` targeted); a `Feedback` + `format_result` smoke shows
`delivery: bulk-text (fault)` with a reason line and an op line; today's default status
renders exactly one new line `delivery: stream-edit (inactive)`; `git status --porcelain`
shows exactly the 6 files; NO consumer of `cfg.output.delivery` added in daemon/feedback
(that is P1.M6.T2.S1), and `bulk_controller.py`/`bulk_delivery.py` untouched.

## User Persona

**Target User**: (a) The operator running `voicectl status` mid-dictation — needs to see at
a glance WHICH delivery path is live and WHY a bulk session stopped (the PRD R.5 fault
surface: "reports one concise reason via status"). (b) The P1.M4/P1.M6 implementers — this
surface is the contract they write against (`INPUT: P1.M3.T3.S1 + P1.M3.T1.S1`; `OUTPUT:
status surface consumed by M4/M6 wiring`). (c) The G3/G5 evidence harnesses, which grep
status output for delivery liveness.

**Use Case**: Bulk delivery hits a 250 ms op deadline → controller stops with reason
`op-deadline` → (M6 wiring, later) `fb.set_delivery_state("fault", "op-deadline")` → the
user's next `voicectl status` shows `delivery: bulk-text (fault)` + `delivery reason:
op-deadline` — one concise reason, no recognition text, no surrounding document.

**User Journey**: arm in bulk-text mode → status shows `delivery: bulk-text (active)` →
words confirm → `delivery op: insert utt=… seq=… rev=… 41ms` (M6 format) → a fault stops
delivery → status shows the fault + reason → re-arm → `active` again, reason cleared.

**Pain Points Addressed**: Today there is NO way to observe delivery state from outside the
daemon — R.5's "disarms … and reports one concise reason via status and the configured fault
surface" has nowhere to land; M4/M6 cannot wire what does not exist.

## Why

- PRD §4.2sexies R.5 (verbatim): "`state.json`/status gain `delivery_mode`, `delivery_state`
  (`inactive|active|unsupported|fault`), `delivery_reason`, and last confirmed op — never the
  surrounding user document. New bulk-path logs carry counts and times, not recognition
  text."
- The additive-key recipe is pre-verified in `plan/008_a47116bb2b79/architecture/
  d2_bulk_delivery_map.md` §4 ("Recipe — delivery fields"): seed in `_state` init, one
  set_phase-style setter per field, render after context-prompt.
- `voice_typing/bulk_controller.py`'s docstring names THIS task as its status consumer:
  "P1.M3.T3 (config gate + the delivery_state surface, **fed by stats()**)" — the M6 wiring
  will derive setter calls from `stats()` (`active`, `stopped_reason`, counters) and
  `on_stopped(reason)`. The taxonomy and stop reasons already exist
  (`queue-overflow|op-deadline|refused|unknown|target-error` fault-class; `stopped` /
  acquire-failure non-fault) — this task is the landing zone.
- Ordering: P1.M3.T3.S1 (parallel, disjoint files) adds the `output.delivery` config key
  whose VALUE SPACE (`"stream-edit"|"bulk-text"`) this surface mirrors; this task needs no
  code from it, only its vocabulary.

## What

- **feedback.py**: `_state` init gains (after `ducked`, before `partial`):
  `"delivery_mode": "stream-edit"`, `"delivery_state": "inactive"`, `"delivery_reason": ""`,
  `"last_confirmed_op": ""`. New public setters, all set_phase-style (assign → `_write()`,
  NEVER notify — the module's anti-spam rule):
  - `set_delivery_mode(mode: str)` — ValueError unless `mode ∈ ("stream-edit", "bulk-text")`.
  - `set_delivery_state(state: str, reason: str = "")` — ValueError unless `state ∈
    ("inactive", "active", "unsupported", "fault")`; `reason` is ALWAYS overwritten (the
    default `""` clears a stale reason); sanitized via the shared helper.
  - `record_confirmed_op(op: str)` — sanitized via the shared helper. The sanitizer
    (`" ".join(s.split())[:160]`) is the MECHANICAL guarantee that state never carries the
    surrounding user document / recognition text: multi-line payloads collapse to one line,
    anything longer than 160 chars truncates.
  - Setter docstrings document the M4/M6 consumption contract (Mode A): who calls what
    (bulk wiring only), the stop-reason → state mapping (`queue-overflow|op-deadline|
    refused|unknown|target-error` → `fault` + the reason; clean stop → `inactive`;
    acquire-failure → `unsupported` + reason; acquire ok → `active`), and the
    counts-and-times format guidance for `last_confirmed_op` (verb + ids + revision +
    elapsed ms — never text).
- **daemon.py `status_snapshot()`**: 4 additive keys `snap.get("delivery_mode",
  "stream-edit")`-style with defaults EQUAL to the Feedback seeds; docstring updated
  ("— 18 keys" + a line explaining delivery provenance: live feedback state, written only by
  the bulk wiring, defaults = surface-unwired truth). NO other daemon change — the daemon
  never CALLS the setters in this task and never reads `cfg.output.delivery` (P1.M6.T2.S1).
- **ctl.py `format_result` status branch**: after the `context-prompt:` line (before the
  optional `load error:` line):
  - always: `f"delivery: {mode} ({state})"` — missing/empty keys default `"unknown"`
    (the `context_prompt` old-daemon tolerance precedent);
  - only when non-empty: `f"delivery reason: {reason}"`;
  - only when non-empty: `f"delivery op: {op}"`.
  Update the `format_result` docstring's status-line list (also stale re context-prompt —
  add both) and any module-level status help (Mode A). Exit code stays 0; `format_result`
  stays PURE; `_COMMANDS` unchanged.
- **Behavior today (default config, nothing wired)**: `voicectl status` gains exactly one
  line, `delivery: stream-edit (inactive)` — truthful: the bulk path is not wired until M6.
  `state.json` gains 4 keys with those seed values on every write.

### Success Criteria

- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_feedback.py tests/test_voicectl.py -q` → 0 failed.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -k status_snapshot -q` → 0 failed.
- [ ] `test_state_shape_has_the_documented_fields` asserts the 12-key set (8 old + 4 new).
- [ ] `test_status_snapshot_keys_and_cuda_values` asserts the 18-key set (14 + 4).
- [ ] Setter validation: `set_delivery_mode("Bulk-Text")` and
      `set_delivery_state("actve")` raise ValueError; both legal values round-trip through
      state.json.
- [ ] Sanitizer pinned: a 500-char multi-line payload → single line, ≤160 chars, in BOTH
      `delivery_reason` and `last_confirmed_op`.
- [ ] Never-notify pinned: all three setters invoke zero hyprctl calls (existing
      `test_set_phase_never_invokes_hyprctl` pattern).
- [ ] `format_result("status", …)`: delivery line renders AFTER the `context-prompt:` line;
      missing delivery keys → `delivery: unknown (unknown)`; empty reason/op → lines hidden;
      populated → both lines present; exit 0.
- [ ] `update_partial`/`record_final` leave all four delivery fields untouched (never
      hijacks `partial` in either direction).
- [ ] `git status --porcelain` → exactly the 6 files; `grep -rn 'output.delivery'
      voice_typing/daemon.py voice_typing/feedback.py voice_typing/ctl.py` → no hits.

## All Needed Context

### Context Completeness Check

_Pass._ The research note pins: the exact current `_state` shape and setter conventions
(feedback.py), the exact-key assertions that MUST be extended (test_feedback.py:125,
test_daemon.py:1954), the status_snapshot additive-key pattern + the `.get`-default
requirement imposed by minimal `_FakeFeedback` doubles, the ctl status branch structure and
its `_STATUS_ON` test fixture, the taxonomy/stop-reason vocabulary from
bulk_delivery.py/bulk_controller.py (what M6 will feed in), the d2 §4 recipe, and verified
validation commands.

### Documentation & References

```yaml
# MUST READ — this task's research: current state, locked design, seams, commands
- docfile: plan/008_a47116bb2b79/P1M3T3S2/research/delivery_status_surface.md
  section: "ALL of it (§0 current state, §1 design, §3 test seams, §5 out-of-scope)."

# MUST READ — the pre-verified recipe this task implements
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  section: "§4 ctl.py + feedback.py recipes — 'Recipe — delivery fields' paragraph"
  why: "The additive-key recipe (seed _state + set_phase-style setters + render after
        context-prompt) and the exact key names/taxonomy, straight from the planning round."
  gotcha: "Its line anchors have drifted (~+188 in daemon.py); use the PRP's current anchors."

# MUST READ — the file being extended (its own docstrings ARE the Mode A docs)
- file: voice_typing/feedback.py
  why: "_state init (~92-110): seed the 4 keys after 'ducked'. set_phase (~124) /
        set_ducked (~163): the setter pattern to copy (assign + self._write(), never
        notify, rich docstring). snapshot() (~230): nothing to change — copy carries new
        keys automatically. Module docstring schema line (~20): update (Mode A)."
  gotcha: "Feedback sees ONLY FeedbackConfig — it must NOT import/read OutputConfig.
           The 'stream-edit' seed is a LITERAL, not a config read (M6 owns seeding)."

# MUST READ — status plumbing + exact-key test
- file: voice_typing/daemon.py
  why: "status_snapshot() at :2463 (NOT 2275 — drifted): add 4 snap.get() keys mirroring
        phase/models_loaded; update the docstring '14 keys' → 18. _context_prompt_label()
        :2447 = the additive-key/never-raises precedent. Callers spread {'ok':True,
        **status_snapshot()} (:1964/:1981/:2885/:2909) — additive keys flow for free."
  gotcha: "VT-001: status_snapshot must stay free of cuda_check calls. The daemon must
           NOT call the new setters or read cfg.output.delivery here (P1.M6.T2.S1)."

# MUST READ — rendering + its test fixture
- file: voice_typing/ctl.py
  why: "format_result :~90 (PURE); status branch :~105-171 — the text block ends with
        f\"context-prompt: {context_prompt}\" then the optional load-error append; insert
        the delivery lines between them. Defensive .get + 'unknown' default precedent =
        context_prompt (:~122). Docstring :~85-90 lists status lines (stale — add
        context-prompt AND delivery, Mode A)."
- file: tests/test_voicectl.py
  why: "_STATUS_ON module dict + containment assertions ('x: y' in text, code == 0) — the
        exact style for the new format tests (:62-72, :94-103)."

# MUST READ — the two exact-key assertions to extend
- file: tests/test_feedback.py
  why: "Fixture :~91 (fb, recorder-mock, frozen clock) + _read_state(tmp_path) :~100.
        test_state_shape_has_the_documented_fields :125 — EXACT set(...) assertion, extend
        +4. Never-notify pattern :316. Throttle tests show why setters are always-write."
- file: tests/test_daemon.py
  why: "test_status_snapshot_keys_and_cuda_values :1954 — set(s) == EXACT 14-key assertion
        (extend to 18, then assert the seeded defaults). _make_daemon_with_feedback
        supplies a REAL Feedback (setters reach status_snapshot live). _FakeFeedback :~40
        minimal snapshot() — the reason daemon-side .get defaults are load-bearing."

# READ — the vocabulary this surface carries (do NOT modify these files)
- file: voice_typing/bulk_delivery.py
  why: "ShowResult taxonomy :77-90 ('serialized verbatim into status/log lines, R.5's
        delivery_state/delivery_reason surface'). AcquireResult.reason vocabulary."
- file: voice_typing/bulk_controller.py
  why: "Docstring: 'P1.M3.T3 … delivery_state surface, fed by stats()' + the stop-reason
        list the M6 wiring will map onto delivery_state/fault. READ-ONLY for this task
        (P1.M3.T2.S3 G2-gate work is in flight there)."

# READ — coordination contracts
- file: plan/008_a47116bb2b79/P1M3T3S1/PRP.md
  why: "The PARALLEL config-gate item (config.py/config.toml/test_config*). Disjoint files.
        Its value space ('stream-edit'|'bulk-text') is the delivery_mode vocabulary — no
        code dependency; do not duplicate its work."

# READ — the spec source (READ-ONLY)
- docfile: PRD.md
  why: "§4.2sexies R.5 (the verbatim key list + 'never the surrounding user document' +
        'counts and times, not recognition text'); §4.6 (state-file schema + notification
        discipline the setters must not disturb)."

# READ — operational discipline (timeouts; never foreground the daemon)
- docfile: AGENTS.md
  section: "Rules 1-2 + the hang-vector table (voicectl under timeout 30; pytest under
            timeout with .venv/bin/python)."
```

### Current Codebase tree (excerpt — `tree` the repo root for the full view)

```bash
voice_typing/
├── feedback.py        # ← EDIT: 4 _state keys + 3 setters + sanitizer + Mode A docs
├── daemon.py          # ← EDIT: status_snapshot 4 additive keys (docstring 14→18)
├── ctl.py             # ← EDIT: status-branch delivery lines + Mode A help
├── bulk_delivery.py   # (READ-ONLY: ShowResult/AcquireResult vocabulary)
├── bulk_controller.py # (READ-ONLY: stats()/on_stopped — the future writer)
├── config.py          # (S1's file — parallel, disjoint)
└── ...
tests/
├── test_feedback.py   # ← EDIT: shape pin +4; setter/sanitizer/never-notify tests
├── test_daemon.py     # ← EDIT: status key pin 14→18 + live-surface test
└── test_voicectl.py   # ← EDIT: format_result delivery-line tests
```

### Desired Codebase tree with files to be added

No new files — 6 modifications only.

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TWO EXACT-KEY-SET ASSERTIONS WILL FAIL ON TOUCH. tests/test_feedback.py:125
#   (state.json shape) and tests/test_daemon.py:1954 (status_snapshot keys) both use set(...)
#   == EXACT equality. The 4 new keys break both unless extended IN THE SAME CHANGESET —
#   extend them first (TDD: red → implement → green).

# CRITICAL #2 — THE DAEMON-SIDE .get DEFAULTS ARE LOAD-BEARING. tests/test_daemon.py's
#   _FakeFeedback.snapshot() returns ONLY {"phase": ...} and tests/test_context_prompt_
#   refresh.py has its own minimal double. status_snapshot MUST read the delivery keys via
#   snap.get(key, <default>) with defaults EQUAL to the Feedback seeds ("stream-edit",
#   "inactive", "", "") or every daemon test using those doubles breaks.

# CRITICAL #3 — NEVER NOTIFY, NEVER THROTTLE (contract wording): the setters are set_phase
#   style — assign + self._write(), NO hyprctl call, NO throttle gate. Do not "improve" them
#   with the _PARTIAL_WRITE_MIN_INTERVAL throttle; the contract pins always-write. Write
#   frequency is the M6 wiring's concern (state transitions + confirmed ops, both rare).

# CRITICAL #4 — 'partial' IS NEVER HIJACKED, EITHER DIRECTION. record_final overwrites
#   partial/last_final only; the delivery setters touch ONLY their own keys. Add the
#   independence test (update_partial + record_final leave delivery fields untouched; a
#   delivery setter leaves partial/last_final untouched).

# CRITICAL #5 — THE SANITIZER IS THE PRIVACY GUARD. delivery_reason/last_confirmed_op pass
#   through " ".join(s.split())[:160] — collapse ALL whitespace (a newline in the value would
#   break ctl's one-line rendering) and cap length (a pasted document can never ride in).
#   Do NOT sanitize partial/last_final — those carry recognition text BY DESIGN.

# CRITICAL #6 — NO CONSUMER, NO SEEDING FROM CONFIG. grep 'output.delivery' across
#   daemon.py/feedback.py/ctl.py must stay empty after this task. The "stream-edit" seed is
#   a literal; M6.T2.S1 will call set_delivery_mode(cfg.output.delivery) at boot. Likewise
#   do NOT wire bulk_controller → feedback (M6.T2.S1) and do NOT add `voicectl session`
#   (M6.T2.S3). This task ships an empty-but-writable surface.

# GOTCHA #7 — LINE ANCHORS DRIFTED. The item contract cites daemon.py:2275-2318 for
#   status_snapshot (now :2463) and ctl.py:126-171 (now ~:105-171). Trust symbol names
#   (grep -n 'def status_snapshot' / 'def format_result'), not those numbers.

# GOTCHA #8 — TIMEOUT DISCIPLINE (AGENTS.md). Every pytest/python call: inner `timeout N`
#   + `.venv/bin/python` (zsh aliases python3). tests/test_daemon.py FULLY RUN loads CUDA
#   models (minutes) — use `-k status_snapshot` for iteration; voicectl CLI probes get
#   `timeout 30`.
```

## Implementation Blueprint

### Data models and structure

```python
# feedback.py — module constants near _PARTIAL_WRITE_MIN_INTERVAL:
_DELIVERY_MODES = ("stream-edit", "bulk-text")          # mirrors [output] delivery (P1.M3.T3.S1)
_DELIVERY_STATES = ("inactive", "active", "unsupported", "fault")  # PRD §4.2sexies R.5 taxonomy
_STATUS_TEXT_MAX = 160                                   # reason/op cap (never a document)

def _sanitize_status_text(value: str) -> str:
    """Collapse whitespace runs to single spaces + truncate — the R.5 guard that keeps
    delivery_reason/last_confirmed_op to counts/times, never recognition text or the
    surrounding user document."""
    return " ".join(value.split())[:_STATUS_TEXT_MAX]

# feedback.py __init__._state — insert after "ducked", before "partial":
    "delivery_mode": "stream-edit",   # literal seed (config default); M6.T2.S1 re-seeds from cfg.output.delivery at boot
    "delivery_state": "inactive",   # taxonomy above; bulk path unwired until M6
    "delivery_reason": "",          # one concise reason (stop/acquire failure), sanitized
    "last_confirmed_op": "",        # last APPLIED op descriptor (counts+times), sanitized
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT (no mutation)
  - RUN: grep -n 'def status_snapshot' voice_typing/daemon.py; grep -n 'def format_result' voice_typing/ctl.py
         grep -n 'test_state_shape_has_the_documented_fields' -A3 tests/test_feedback.py
         timeout 120 .venv/bin/python -m pytest tests/test_feedback.py tests/test_voicectl.py -q | tail -1
         timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -k status_snapshot -q | tail -1
  - EXPECTED: anchors confirmed (gotcha #7); all three green at baseline.

Task 2: TDD RED — extend the two exact-key pins FIRST (Critical #1)
  - MODIFY tests/test_feedback.py test_state_shape_has_the_documented_fields: the set gains
    "delivery_mode", "delivery_state", "delivery_reason", "last_confirmed_op".
  - MODIFY tests/test_daemon.py test_status_snapshot_keys_and_cuda_values: the 14-key set
    gains the same 4; ALSO assert the seeded defaults
    (s["delivery_mode"] == "stream-edit" and s["delivery_state"] == "inactive"
     and s["delivery_reason"] == "" and s["last_confirmed_op"] == "").
  - RUN the two suites → the two pinned tests RED, everything else green.

Task 3: IMPLEMENT feedback.py (the surface)
  - ADD constants + _sanitize_status_text (blueprint above).
  - ADD the 4 _state seeds after "ducked" (Critical #6: literals, no config read).
  - ADD three setters following set_phase/set_ducked style (assign → self._write(); rich
    docstring = Mode A docs; see Implementation Patterns):
      set_delivery_mode(mode), set_delivery_state(state, reason=""), record_confirmed_op(op)
  - UPDATE the module docstring's state.json schema line to include the 4 keys (+ one
    sentence: written ONLY by the bulk wiring (M4/M6), taxonomy per R.5, reason/op carry
    counts/times never recognition text).
  - FILE: voice_typing/feedback.py

Task 4: IMPLEMENT daemon.py status_snapshot
  - ADD after the "context_prompt" entry (same snap.get pattern, Critical #2):
      "delivery_mode": snap.get("delivery_mode", "stream-edit"),
      "delivery_state": snap.get("delivery_state", "inactive"),
      "delivery_reason": snap.get("delivery_reason", ""),
      "last_confirmed_op": snap.get("last_confirmed_op", ""),
  - UPDATE the docstring: "— 18 keys" + a delivery-provenance sentence (live feedback
    state; written only by the bulk wiring (P1.M6.T2.S1); defaults = surface unwired).
  - FILE: voice_typing/daemon.py

Task 5: IMPLEMENT ctl.py rendering
  - IN format_result status branch: read
      delivery_mode = response.get("delivery_mode", "") or "unknown"
      delivery_state = response.get("delivery_state", "") or "unknown"
      delivery_reason = response.get("delivery_reason", "") or ""
      delivery_op = response.get("last_confirmed_op", "") or ""
    then AFTER the f"context-prompt: ..." line append (before the load-error append):
      f"delivery: {delivery_mode} ({delivery_state})"
      + (f"delivery reason: {delivery_reason}" if delivery_reason else "")
      + (f"delivery op: {delivery_op}" if delivery_op else "")
  - UPDATE format_result docstring status-line list (add context-prompt — currently
    missing — and the delivery lines) — Mode A ctl status help.
  - FILE: voice_typing/ctl.py

Task 6: TDD GREEN + NEW TESTS
  - tests/test_feedback.py (use the `feedback` fixture + _read_state; follow existing style):
      set_delivery_mode round-trips both legal values; ValueError on "Bulk-Text"/non-member;
      set_delivery_state round-trips state+reason pair; default reason="" CLEARS a previous
      reason; ValueError on "actve"; record_confirmed_op round-trip;
      sanitizer: 500-char multi-line payload → one line ≤160 (assert no "\n", len ≤ 160)
      for BOTH reason and op; always-write (like test_set_phase_always_writes…);
      never-invoke-hyprctl for all three setters (recorder-mock pattern :316);
      independence: update_partial("hi") + record_final("x") leave all 4 delivery fields
      untouched (Critical #4); snapshot() copy includes the 4 keys.
  - tests/test_daemon.py:
      live-surface test: d, fb = _make_daemon_with_feedback(...); fb.set_delivery_state(
      "fault", "op-deadline"); fb.record_confirmed_op("insert seq=7 rev=12 41ms"); assert
      status_snapshot() reflects both (live in-memory read, no disk involved).
  - tests/test_voicectl.py (use _STATUS_ON spreads + containment, exit 0):
      delivery line renders AFTER context-prompt (assert text.index("context-prompt:") <
      text.index("delivery:")); populated reason/op render their lines; empty/absent →
      hidden (assert "delivery reason:" not in text); missing delivery keys entirely →
      "delivery: unknown (unknown)"; default stream-edit response → exactly
      "delivery: stream-edit (inactive)" present, no reason/op lines.

Task 7: VALIDATE — run the full Validation Loop below; then git status --porcelain == the
  6 files exactly; grep guard (no cfg.output.delivery consumer; bulk_* untouched).
```

### Implementation Patterns & Key Details

```python
# feedback.py — the setter pattern (copy set_phase/set_ducked EXACTLY; Critical #3):
def set_delivery_state(self, state: str, reason: str = "") -> None:
    """Record the bulk-delivery state + one concise reason (PRD §4.2sexies R.5; P1.M3.T3.S2).

    Taxonomy: inactive | active | unsupported | fault. Written ONLY by the bulk-delivery
    wiring (P1.M6.T2.S1 maps the controller's on_stopped/stats onto these): controller stop
    reasons queue-overflow | op-deadline | refused | unknown | target-error -> "fault" with
    that reason; a clean stop -> "inactive"; acquire failure -> "unsupported" + the
    AcquireResult.reason; a successful acquire -> "active". `reason` is ALWAYS overwritten
    (the default "" clears a stale fault reason on the next healthy transition). Sanitized
    via _sanitize_status_text: whitespace-collapsed, <=160 chars — counts and times, never
    recognition text or the surrounding user document (R.5). Always writes; never notifies
    (same anti-spam rule as set_phase).
    """
    if state not in _DELIVERY_STATES:
        raise ValueError(
            f"delivery_state must be one of {_DELIVERY_STATES}, got {state!r}"
        )
    self._state["delivery_state"] = state
    self._state["delivery_reason"] = _sanitize_status_text(reason)
    self._write()  # ALWAYS — set_phase style; no throttle, no notify

# set_delivery_mode: same shape, `_DELIVERY_MODES` check, docstring noting the seed is the
#   config-default literal and M6.T2.S1 re-seeds from cfg.output.delivery at boot.
# record_confirmed_op(op): _sanitize_status_text(op) -> _state["last_confirmed_op"]; write.
#   Docstring: called on each in-time ShowResult.APPLIED (controller law: only APPLIED
#   confirms); format = verb + utterance/seq ids + revision + elapsed ms — M6 builds it.

# daemon.py — the additive-key pattern (Critical #2; mirrors phase/models_loaded):
"delivery_mode": snap.get("delivery_mode", "stream-edit"),  # P1.M3.T3.S2: delivery surface

# ctl.py — the rendering (context_prompt 'unknown' precedent for old daemons):
delivery_mode = response.get("delivery_mode", "") or "unknown"
# ...then in the text block, after context-prompt:
f"delivery: {delivery_mode} ({delivery_state})"
# + conditional "delivery reason: ..." / "delivery op: ..." lines (only when non-empty)
```

### Integration Points

```yaml
STATE SCHEMA (state.json):
  - add keys: "delivery_mode ('stream-edit'|'bulk-text'), delivery_state (inactive|active|unsupported|fault), delivery_reason (<=160 chars), last_confirmed_op (<=160 chars)"
STATUS PROTOCOL (control socket, additive — every status/toggle/start/stop reply):
  - add keys: "the same 4, .get-defaulted in status_snapshot"
CTL STATUS OUTPUT:
  - add lines: "delivery: {mode} ({state}) [always] + delivery reason: / delivery op: [only when non-empty], placed after context-prompt:, before load error:"
FUTURE CONSUMERS (NOT here): "P1.M4 adapters + P1.M6.T2.S1 wiring (setters' only writers), P1.M6.T2.S3 voicectl session, P1.M7 evidence greps"
DEPENDENCIES: "none new (pure stdlib; feedback.py already imports nothing beyond stdlib + FeedbackConfig)"
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile voice_typing/feedback.py voice_typing/daemon.py voice_typing/ctl.py tests/test_feedback.py tests/test_daemon.py tests/test_voicectl.py && echo "L1 OK"
```

### Level 2: Unit suites (fast, pure)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_feedback.py tests/test_voicectl.py -q | tail -2
# Expected: 0 failed — the two extended exact-key pins now green + all new tests green.
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -k status_snapshot -q | tail -2
# Expected: 0 failed (targeted filter; the FULL test_daemon.py loads CUDA — do not run it
# without a 600 s timeout, and never without -k when iterating).
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_context_prompt_refresh.py -q | tail -2
# Expected: 0 failed — no-regression on the dispatch spread + the minimal _FakeFeedback
# double consumers (proves the .get defaults, Critical #2).
```

### Level 3: Behavioral smoke (the surface end-to-end, no daemon)

```bash
timeout 60 .venv/bin/python - <<'EOF'
import tempfile, os
from voice_typing.config import FeedbackConfig
from voice_typing.feedback import Feedback
from voice_typing import ctl

with tempfile.TemporaryDirectory() as td:
    fb = Feedback(FeedbackConfig(state_file=os.path.join(td, "state.json"), hypr_notify=False))
    fb.set_listening(True)
    fb.set_delivery_mode("bulk-text"); fb.set_delivery_state("active")
    fb.record_confirmed_op("insert utt=3 seq=7 rev=12 +34ch 41ms")
    fb.set_delivery_state("fault", "op-deadline")
    snap = {"listening": False, "mode": "lite", "phase": "speaking", "partial": "x",
            "last_final": "y", "uptime_s": 1.0, "device": "cuda", "compute_type": "float16",
            "context_prompt": "on", **fb.snapshot()}
    text, code = ctl.format_result("status", snap)
    print(text); assert code == 0
    assert text.index("context-prompt: on") < text.index("delivery: bulk-text (fault)")
    assert "delivery reason: op-deadline" in text
    assert "delivery op: insert utt=3 seq=7 rev=12 +34ch 41ms" in text
    t2, _ = ctl.format_result("status", {"ok": True})  # old-daemon tolerance
    assert "delivery: unknown (unknown)" in t2 and "delivery reason:" not in t2
    print("L3 OK")
EOF
# Also verify TODAY's default surface (one new line, nothing else changes):
#   a fresh Feedback's snapshot renders "delivery: stream-edit (inactive)" and NO reason/op lines.
```

### Level 4: Scope guard + no-regression

```bash
git status --porcelain
# Expected EXACTLY:
#   M voice_typing/feedback.py  M voice_typing/daemon.py  M voice_typing/ctl.py
#   M tests/test_feedback.py    M tests/test_daemon.py    M tests/test_voicectl.py
grep -rn 'output.delivery' voice_typing/daemon.py voice_typing/feedback.py voice_typing/ctl.py || echo "ok: no config consumer (M6.T2.S1 owns it)"
git diff --stat voice_typing/bulk_controller.py voice_typing/bulk_delivery.py voice_typing/config.py config.toml | wc -l  # → 0 (untouched; S1/T2.S3 own them)
timeout 120 .venv/bin/python -m pytest tests/test_feedback.py tests/test_voicectl.py -q | tail -1  # final clean run
```

## Final Validation Checklist

### Technical Validation

- [ ] L1–L4 green; `git status --porcelain` shows exactly the 6 files.
- [ ] Both exact-key pins extended and green (feedback shape 12 keys; status_snapshot 18 keys).
- [ ] `tests/test_control_socket.py` + `tests/test_context_prompt_refresh.py` still green
      (`.get` defaults protect the minimal doubles).
- [ ] No lint/type regressions in the touched files (follow existing style; ruff/mypy if run
      repo-wide today, keep the touched files clean).

### Feature Validation

- [ ] All success criteria in "What" met (validation matrix, never-notify, sanitizer caps,
      independence both ways, rendering order after context-prompt, unknown-default).
- [ ] L3 smoke prints the full status block with the delivery lines in the right place.
- [ ] Default-config surface: exactly one new status line `delivery: stream-edit (inactive)`;
      state.json carries the 4 seeded keys on every write.
- [ ] Error cases: ValueError messages name the offending value (setter misuse = wiring bug,
      fail-fast per repo posture).

### Code Quality Validation

- [ ] Setters copy the set_phase/set_ducked pattern verbatim (assign → _write(); no notify,
      no throttle); docstrings document the M4/M6 consumption contract (Mode A).
- [ ] File placement matches the tree; no new files; no renames.
- [ ] Anti-patterns below avoided; no config import added to feedback.py; daemon.py change
      confined to status_snapshot + its docstring.

### Documentation & Deployment

- [ ] feedback.py module docstring schema line updated (Mode A: field docs).
- [ ] ctl.py format_result docstring + status help list the delivery lines (Mode A).
- [ ] No new env vars, config keys, or commands (`_COMMANDS` untouched).

## Anti-Patterns to Avoid

- ❌ Don't extend `_state` without extending the two exact-key tests in the same changeset
      (Critical #1 — they are pins, not suggestions).
- ❌ Don't read the delivery keys from the snapshot without `.get` defaults (Critical #2 —
      the minimal test doubles depend on them).
- ❌ Don't throttle or notify in the new setters (Critical #3 — the contract pins
      set_phase-style always-write/never-notify).
- ❌ Don't couple delivery fields to `partial`/`last_final` in either direction (Critical #4).
- ❌ Don't skip the sanitizer or apply it to `partial`/`last_final` (Critical #5 — it is the
      mechanical R.5 guard, and recognition text in partial/last_final is by design).
- ❌ Don't add a consumer: no `cfg.output.delivery` read, no controller wiring, no
      `voicectl session`, no new command (Critical #6 — M4/M6 own all of that).
- ❌ Don't run the full `tests/test_daemon.py` bare or without a 600 s timeout — CUDA load;
      iterate with `-k status_snapshot` (Gotcha #8, AGENTS.md).
- ❌ Don't trust the item contract's line anchors — grep the symbol names (Gotcha #7).

---

**Confidence Score: 9/10.** The change is fully additive over three pre-verified seams
(the d2 §4 recipe, the `mic_*`/`context_prompt` additive-key precedents, the exact-key pin
tests), with the taxonomy/vocabulary already fixed by P1.M3.T1.S1's `ShowResult` and the
controller's stop reasons. −1: the sanitizer (collapse+160 cap) and the
`set_delivery_state(state, reason)` pairing are small refinements beyond the literal "one
setter per field" recipe wording — both are contract-compatible and test-pinned, but the
implementer should follow THIS PRP's shape, not re-derive from the research note alone.

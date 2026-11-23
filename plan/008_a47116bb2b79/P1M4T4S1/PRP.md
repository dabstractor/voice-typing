# PRP — P1.M4.T4.S1: Takeover detection + revocation + mutation-time re-checks (`voice_typing/ime/` completes)

## Goal

**Feature Goal**: Ship the **takeover half** of the IM-v2 adapter (PRD §4.2sexies R.5, work-item contract):
event listeners that DETECT user takeover (ordinary physical keys via the keyboard grab, surrounding-text
caret/selection divergence, deactivate, target death), a revocation path that **releases the grab AT THE
TARGET** (daemon-side flags alone do not suffice — the grab CONSUMES the user's keys, so an un-released
grab leaves the keyboard swallowed), and mutation-time re-check hooks so a queued operation that lost the
field refuses instead of mutating. On completion the adapter is **takeover-complete, ready for G3**
(P1.M4.T5 consumes it; P1.M6.T2.S1 wires it into the daemon).

**Contract points** (item LOGIC, each implemented AND unit-tested):
1. **Takeover listeners**: key events (via `grab_key`), `surrounding_text` caret/selection deltas,
   `deactivate` (focus/pane switch), target death (manager `fault`/child EOF — already emitted; treat as
   revocation, no double-emission).
2. **Handle revocation**: revoke AT THE TARGET — release the compositor keyboard grab + clear the binding
   (composes with S3's `leave()`, which already does exactly this) + halt the controller with ONE recorded
   reason.
3. **Mutation-time re-checks**: queued ops re-check at dispatch — event-driven revoke (fast path) PLUS the
   existing `recheck()` fresh-verify backstop; no post-takeover mutation is possible (binding cleared →
   later ops REFUSE "not acquired").
4. **Evidence-carried rules** (R.5 + im-lab rows O/O2, pinned by tests): the arming chord is IGNORED by
   key-composition match (NOT a blanket grace window — no 1.5 s timer like legacy §4.2quater Rev 3);
   synthetic delivery events cannot self-trigger HALT (commits generate ZERO key events — row O2) or leave
   modifiers held (never synthesize keys; modifier-only presses never revoke); pointer motion alone is not
   an edit (it generates NO IM event → nothing revokes).

**Deliverable** (1 NEW module + 1 NEW test file + 3 EVOLVED source files + 3 EVOLVED test files + 1 optional lab):
1. `voice_typing/ime/takeover.py` — **CREATE**: stdlib-pure takeover policy (`TakeoverDetector.feed(ev) ->
   reason|None`), keycode constants, the chord set, and a `TakeoverWatch` wiring helper
   (proc.on_event → detector → revoke callback) — unit-testable with fakes.
2. `voice_typing/ime/protocol.py` — **EVOLVE**: add `"grab"` to `REQUEST_CMDS` (additive; S3's `cancel`
   lift is a different line); `validate_request` passes `grab` (no extra fields).
3. `voice_typing/ime/ime_host.py` — **EVOLVE**: add the `_grab` handler (`grab_keyboard` request + set
   `self.grab`; reply `ok/grab`); release stays in `_leave` (already releases when held). Add ONE dispatch
   arm. `grab_key`/`keymap`/`modifiers` forwarding ALREADY EXISTS in `on_event`.
4. `voice_typing/bulk_controller.py` — **EVOLVE**: add public `halt_for_takeover(reason)` — records the
   reason through the existing `_stop_locked` path, stops the writer, drains, `target.leave()` exactly
   once (the existing `stop(leave=True)` machinery, re-used — do not duplicate it).
5. `voice_typing/ime/target.py` — **DO NOT TOUCH** (revocation composes with S3's landed `leave()`; the
   post-leave "not acquired" refusal IS the mutation-time guard). This is also the parallel-safety split.
6. `tests/test_ime_takeover.py` — **CREATE**: the detector policy matrix + watch wiring + controller halt.
7. `tests/test_ime_protocol.py`, `tests/test_ime_host.py`, `tests/test_bulk_controller.py` — **APPEND**
   (grab vocab/host cases; takeover halt case). No existing test body changes (S3 owns
   `test_cancel_reserved`).
8. `tests/ime_takeover_lab.py` — **CREATE (OPTIONAL, NON-collected)**: env-gated GTK row
   (`IME_TAKEOVER_LAB=1`, disposable desktop only) re-proving rows O/O2 + chord-ignore + release.

**Success Definition**:
- (a) `timeout 180 .venv/bin/python -m pytest tests/test_ime_takeover.py tests/test_ime_host.py
  tests/test_ime_protocol.py tests/test_ime_target.py tests/test_ime_wlwire.py tests/test_ime_manager.py
  tests/test_bulk_delivery.py tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q` → all green
  (S1–S3 + controller/G2 consumers — zero regression); `ruff check voice_typing/ime/ voice_typing/bulk_controller.py tests/test_ime_takeover.py` clean;
  `git status --porcelain` shows ONLY the files above.
- (b) Detector matrix pinned: ordinary non-modifier key ⇒ revoke `user key <code>`; modifier-only
  DOWN/UP ⇒ never revoke (down-set maintained); KEY_D(32) with down-mods ⊇ {ALT,SUPER} ⇒ chord, ignored
  (covers BOTH §4.10 binds: Ctrl+Alt+Super+D and Alt+Super+D — Super+Alt ⊆ Ctrl+Super+Alt); no grace timer
  exists anywhere; `surrounding_text` diverging from the accounting expectation
  (cursor ≠ binding.cursor_bytes + inserted_bytes, or anchor ≠ cursor) with a non-input_method cause ⇒
  revoke; surrounding_text matching our accounting ⇒ benign; `deactivate` ⇒ revoke; a cause cycle of
  `input_method` ⇒ never revokes; NO event ⇒ nothing happens (pointer motion alone).
- (c) Revocation pinned: exactly ONE `target.leave()`; the host `leave` RELEASES the grab (assert the
  `zwp_input_method_keyboard_grab_v2.release` request is sent when the grab is held); every later mutating
  call REFUSES "not acquired" with NO request; controller halts with the one concise reason recorded
  (idempotent — second revoke is a no-op); no post-takeover mutation (queued op refuses or drains into the
  late-result discard path).
- (d) Watch wiring pinned: `TakeoverWatch(proc, target, controller)` subscribes `proc.on_event`; events
  arrive on the reader thread; a detector exception cannot kill it (manager already guards callbacks — the
  watch itself never raises out of the callback); `unavailable`/fault paths are NOT double-emitted.
- (e) Logs carry counts/times/keycodes/reasons ONLY — never recognition text (R.5).

## User Persona

**Target User**: Internal — the daemon wiring (P1.M6.T2.S1) constructs the stack; **P1.M4.T5** (G3
real-field proof) exercises it against live fields. No end-user surface changes in this task.

**Use Case**: Bulk mode armed on a GTK field (acquire succeeded, grab engaged). The user starts typing a
URL by hand — the first `grab_key` (non-modifier, not the chord) revokes: grab released at the compositor
(keyboard returns to the user), binding cleared, controller halted with `takeover: user key 32`, mic
delivery stops, the typed-so-far words stay. The user re-arms later with Ctrl+Alt+Super+D — that chord,
pressed while the grab is live, is ignored by composition match, not by a timer.

**Pain Points**: (1) Without the grab, NO key events flow — takeover is undetectable and dictation
clobbers hand-typing. (2) A revoke that only sets a daemon flag leaves the grab held — the user's ENTIRE
keyboard is dead. (3) A blanket grace window (legacy 1.5 s) would ignore real user keys right after
arming. (4) A queued show() that lost the field must refuse at mutation time, not type into the new focus.

## Why

- **R.5 pins it verbatim**: "any ordinary physical key, caret move, selection change, mouse click, focus
  change, tab/pane switch, or target death revokes the handle AT THE TARGET; queued operations re-check
  at mutation time. … The arming chord is ignored (not a blanket grace window). Synthetic delivery events
  cannot self-trigger HALT or leave modifiers held. Pointer motion alone is not an edit."
- **The wire machinery is landed**: the host already forwards every event the detector needs
  (`ime_host.on_event`); the manager already fans them to `on_event` (docstring: "P1.M4.T4 subscribes
  takeover detection via on_event"); the protocol docstring pre-declares this subscription. Only the
  GRAB ENGAGEMENT and the POLICY are missing.
- **The evidence is settled** (im-lab rows O/O2, d2 map :189): grabbed keys reach the adapter while the
  field stays untouched; commits generate ZERO key events. Do NOT re-run route discovery (R.4).
- **G3 (T5) is blocked on this**: "OUTPUT: takeover-complete adapter ready for G3."

## What

A pure daemon-side detector + a host `grab` request + a controller halt seam, all additive to the landed
S1–S3 surfaces, zero changes to `target.py` (revocation composes with S3's `leave()`).

### Success Criteria

- [ ] `grab` request engages the keyboard grab; `leave` releases it (asserted at the wire level).
- [ ] Detector implements the full matrix of Success Definition (b) — pure, no Wayland/evdev imports.
- [ ] Revocation path meets (c); watch wiring meets (d); logs meet (e).
- [ ] Full IM+bulk suite green (command in (a)); ruff clean; only the listed files touched.

## All Needed Context

### Context Completeness Check

_Pass._ Someone who knows nothing about this codebase gets: the exact landed seams (file:line), the wire
event vocabulary, the keycode constants, the chord rule, the accounting formula, the evidence rows, the
parallel-merge discipline vs S3, and the exact test commands. No inference required.

### Documentation & References

```yaml
# MUST READ — the landed seams this task builds on
- file: voice_typing/ime/ime_host.py
  why: on_event ALREADY forwards grab_key/keymap/modifiers/surrounding_text/text_change_cause/
        deactivate/unavailable as JSONL; _leave ALREADY releases a held grab; _grab is the ONE missing
        handler. Mirror _show/_leave's handler style + the SHOW_CONFIRM_WAIT bounded-wait posture.
  pattern: _dispatch arms at :~160; _leave releases the grab at :~230.
  gotcha: the host NEVER grabs today (self.grab=0 forever) — without adding grab_keyboard, zero key
          events flow. keymap fds are CLOSED by wlwire (no keymap name available — match raw keycodes).

- file: voice_typing/ime/manager.py
  why: ImeProcess.on_event is the T4 feed (ALL events, reader-thread, exception-guarded); fault/
        unsupported already emitted exactly once — the watch must NOT double-emit for child death.
  pattern: constructor injection (on_event/on_delivery_state); _fire guards callbacks.
  gotcha: callbacks run ON the reader thread — the watch's revoke action must be quick + non-blocking
          (target.leave() is a bounded 0.25 s request; controller halt must not join the reader).

- file: voice_typing/ime/target.py
  why: recheck() is the existing MUTATION-TIME backstop (fresh verify; refuses deactivated/selection/
        caret-moved/adjacent-changed); leave() (S3) clears the binding → later ops REFUSE "not acquired".
  pattern: accounting formula cursor == binding.cursor_bytes + inserted_bytes (recheck's `expected`).
  gotcha: DO NOT EDIT this file — S3 (in flight) owns it; revocation composes with its leave().

- file: voice_typing/ime/protocol.py
  why: REQUEST_CMDS + validate_request — add "grab" (S3 lifts the cancel reservation on a DIFFERENT
        line; appends must not collide).
  gotcha: keep purity (json/time/pathlib only — the module's own rule).

- file: voice_typing/bulk_controller.py
  why: stop(leave=True) machinery (writer join 5 s, runner shutdown(wait=False), late-result discard,
        leave exactly once, never masks the stop reason) + _stop_locked(reason) + _fire_on_stopped —
        halt_for_takeover re-uses these; do NOT duplicate the teardown.
  pattern: stop() at :331; the "one-concise-reason law (R.5)" comment.
  gotcha: halt may be invoked from the manager reader thread — no unbounded joins there.

- file: voice_typing/key_listener.py
  why: _MODIFIER_KEYCODES (:50-56) — the lineage for the modifier-only rule ("bare modifier presses are
        NOT user typing … the ARM HOTKEY's own chord"). Mirror the keycodes as LITERAL INTS (the ime
        package must stay stdlib-pure; key_listener imports evdev).

- file: tests/test_ime_host.py
  why: the fake-Client injection pattern (ImeHost(client, out, log_path)) your grab tests mirror;
        S3 is concurrently REPLACING test_cancel_reserved + appending — APPEND ONLY, no shared hunks.

# MUST READ — the contract + evidence
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: §4.2sexies R.5 (takeover, verbatim) + R.2 evidence table (rows: grab_keyboard key events reach
        the adapter while the field stays untouched; IM commits generate ZERO key events) + R.4 (do not
        re-run route discovery).
  section: "R.5 Ordering, takeover, and failure" + "R.2 Evidence and provenance".

- file: plan/008_a47116bb2b79/P1M4T3S3/PRP.md
  why: the INPUT CONTRACT — defines leave()/finalize()/cancel() semantics this task composes with; its
        :590 notes "takeover revocation composes with leave() (binding cleared) and the closed-set".
  gotcha: treat as landed-by-the-time-you-run; coordinate shared files per the merge discipline below.

- file: plan/008_a47116bb2b79/P1M4T4S1/research/takeover_detection_research.md
  why: THIS task's research note — the full design rationale, keycode table, evidence citations,
        parallel-conflict map. Read it FIRST.

- file: tools/im-lab/imlab_run.py
  why: rows O/O2 (grab_rows, :353-372) — the reference implementation of the lab assertions your
        optional ime_takeover_lab.py re-proves (xdotool key → grab_key + field untouched; insert → zero
        grab_key). Evidence record — never edit.

# External — protocol ground truth
- url: https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/input-method/input-method-unstable-v2.xml
  why: the vendored XML this wire implements — grab_keyboard/release requests; key(time,key,state,serial);
        text_change_cause enum {input_method=0, other=1}; event ordering (surrounding_text + cause batch
        before done).
  critical: keys delivered to the grab are NOT forwarded to the app (row O: field untouched) — that is
            WHY revocation must release the grab at the target.
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/ime/
├── __init__.py        # re-exports protocol vocabulary (update if takeover adds public names)
├── wlwire.py          # wire client — grab_keyboard/release already in REQUESTS; keymap fd closed
├── protocol.py        # JSONL vocab — EVOLVE: + "grab"
├── ime_host.py        # host — EVOLVE: + _grab handler (events already forwarded)
├── manager.py         # ImeProcess — on_event feed exists; NO changes needed
├── target.py          # S3's file — DO NOT TOUCH (leave() composes)
└── takeover.py        # CREATE — detector + chord/modifier policy + TakeoverWatch
voice_typing/bulk_controller.py  # EVOLVE: + halt_for_takeover(reason)
tests/
├── test_ime_takeover.py    # CREATE — the policy matrix + wiring + halt
├── test_ime_host.py        # APPEND grab cases (S3 concurrent — append-only)
├── test_ime_protocol.py    # APPEND vocab cases
├── test_bulk_controller.py # APPEND takeover-halt case
└── ime_takeover_lab.py     # CREATE optional, env-gated IME_TAKEOVER_LAB=1
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: the grab CONSUMES keys (im-lab row O: field untouched while grabbed). Engage ONLY for an
#   acquisition's lifetime; release is mandatory on EVERY exit path (leave/revocation/stop). A daemon
#   flag without the release = the user's whole keyboard is dead ("revoke AT THE TARGET").
# CRITICAL: the arming chord is ignored BY COMPOSITION (key==KEY_D and down-mods ⊇ {ALT,SUPER}), never
#   by a time window. Legacy §4.2quater's 1.5 s grace is NOT ported here (explicit contract point).
# CRITICAL: modifier-only presses never revoke AND never reset the down-set incorrectly — track DOWN/UP
#   transitions from grab_key events (state arg), not the `modifiers` event (group state, advisory).
# GOTCHA: our own commits change surrounding_text — distinguish via (a) cause cycle (text_change_cause
#   == input_method) and (b) the accounting rule (cursor == binding.cursor_bytes + inserted_bytes, the
#   same formula recheck() uses). A surrounding_text matching our accounting is benign.
# GOTCHA: wlwire closes keymap fds immediately — no keymap names; match RAW keycodes (KEY_D=32; mods:
#   29/97 ctrl, 56/100 alt, 42/54 shift, 58 caps, 69 num, 70 scroll, 125/126 super/meta).
# GOTCHA: T3.S3 runs IN PARALLEL — shared files are protocol.py/ime_host.py/test_ime_host.py; your edits
#   are appends on different lines (grab vs cancel). Do NOT touch target.py at all.
# CRITICAL (AGENTS.md): wrap every pytest run in `timeout` (inner) + set the bash tool `timeout` above
#   it. These suites are pure-python (no compositor/GPU/daemon) — fast and safe.
# GOTCHA: logs carry counts/times/keycodes/reasons ONLY — never recognition text (R.5's bulk-path rule).
```

## Implementation Blueprint

### Data models and structure

```python
# takeover.py — pure stdlib, no Wayland/evdev imports (mirror bulk purity rules)

# Keycode constants (Linux input.h; literal ints — the ime package must not depend on evdev)
KEY_D = 32
MODIFIER_KEYCODES = frozenset({29, 97, 56, 100, 42, 54, 58, 69, 70, 125, 126})  # mirrors key_listener
CHORD_KEY = KEY_D
CHORD_MODS = frozenset({"ALT", "SUPER"})   # ⊇-match covers Ctrl+Alt+Super+D AND Alt+Super+D (§4.10)

class TakeoverDetector:
    """feed(ev: dict) -> reason | None. Pure policy over the JSONL event dicts."""
    # state: _mods_down: set[str] (from grab_key DOWN/UP of modifier keycodes),
    #        _expected_caret: int | None, _cause: int | None (last text_change_cause)
    # feed() dispatch:
    #   ev == "grab_key":  modifier keycode → update _mods_down, return None.
    #                      CHORD_KEY and CHORD_MODS ⊆ _mods_down → chord → None.
    #                      else → f"user key {key}".
    #   ev == "surrounding_text": cursor/anchor diverge from expectation
    #                      (cursor != expected or anchor != cursor) AND cause != input_method(0)
    #                      → "caret moved" | "selection present". Else None (benign/ours).
    #   ev == "deactivate": → "deactivated".
    #   ev == "text_change_cause": record _cause; None.
    #   everything else (activate/done/keymap/modifiers/...): None.

class TakeoverWatch:
    """Binds ImeProcess.on_event → detector → revocation. Constructor-injected fakes for tests."""
    # on_event(ev): reason = detector.feed(ev); if reason and not already revoked:
    #     revoked = True; target.leave() (bounded, never raises); controller.halt_for_takeover(reason)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/ime/takeover.py
  - IMPLEMENT: keycode constants, MODIFIER_KEYCODES, CHORD_KEY/CHORD_MODS, TakeoverDetector.feed,
    TakeoverWatch (subscribes via a set-once on_event hook; quick, non-blocking, never raises out).
  - FOLLOW pattern: bulk_controller's constructor-injection + manager's callback guarding; purity =
    stdlib only, no imports from daemon/streaming/backends.
  - NAMING: snake_case; reasons are short machine-readable strings (R.5's one-concise-reason law).
  - PLACEMENT: voice_typing/ime/takeover.py; export public names from ime/__init__.py if needed.

Task 2: EVOLVE voice_typing/ime/protocol.py
  - ADD: "grab" to REQUEST_CMDS; validate_request accepts it (no required fields beyond id).
  - PRESERVE: everything else (S3's cancel lift lands on its own line — no collision).

Task 3: EVOLVE voice_typing/ime/ime_host.py
  - ADD: _grab(rid) — if not activated → reply ok=False; else create the grab object
    (c.new(GRAB_IFACE) + c.request(self.im, IFACE, "grab_keyboard", grab)), set self.grab, reply ok=True.
    Mirror im_probe.py:112-114 exactly (the lab-proven sequence).
  - ADD: one dispatch arm. RELEASE stays in _leave (already: `if self.grab: release`).
  - PRESERVE: on_event forwarding (already emits grab_key/keymap/modifiers — nothing to add there).

Task 4: EVOLVE voice_typing/bulk_controller.py
  - ADD: public halt_for_takeover(reason: str) — record reason via _stop_locked(f"takeover: {reason}"),
    then the existing stop(leave=True) machinery (writer stop, runner discard, leave exactly once).
    Idempotent (second call no-ops). Must be safe to call from the manager reader thread (no unbounded
    joins of the calling thread; the writer join already guards current_thread).
  - FOLLOW pattern: stop() at :331 — re-use, do not duplicate.

Task 5: CREATE tests/test_ime_takeover.py
  - IMPLEMENT the full Success-Definition-(b)/(c)/(d) matrix with fakes (fake proc feeding dicts; fake
    target recording leave(); fake/real controller). Include: chord ignored both binds; modifier-only
    ignored incl. release-mid-hold; ordinary key revokes; cause=input_method benign; divergent
    surrounding_text revokes; deactivate revokes; no-event no-op; exactly-one leave; post-revoke ops
    refuse "not acquired" with zero requests; controller halt idempotent + reason recorded; detector
    exception safety.
  - FOLLOW pattern: tests/test_ime_manager.py's fake-proc injection + test_ime_host.py's fake Client.

Task 6: APPEND grab cases (tests/test_ime_host.py) + vocab cases (tests/test_ime_protocol.py) +
        takeover-halt case (tests/test_bulk_controller.py)
  - APPEND ONLY (S3 concurrent). Host cases: grab → grab_keyboard sent + keymap/grab_key forwarded;
    leave releases a held grab (assert the release request); grab while unactivated refuses.

Task 7 (OPTIONAL): CREATE tests/ime_takeover_lab.py — env-gated IME_TAKEOVER_LAB=1, disposable
  desktop (mirror ime_finalize_lab.py / imlab_run.grab_rows :353): grab → xdotool key → revoked +
  released (subsequent keys reach the field) + chord ignored + commit no-self-trigger. NON-collected.

Task 8: NONE — target.py untouched; manager.py untouched (its on_event feed already suffices); no
  config/pyproject/docs changes (DOCS: none); daemon wiring is M6.T2, NOT this task.
```

### Implementation Patterns & Key Details

```python
# The chord rule — composition, NOT a timer (the contract's explicit contrast):
def _chord(self, key: int) -> bool:
    return key == CHORD_KEY and CHORD_MODS.issubset(self._mods_down)
    # ⊇ {ALT, SUPER} matches Alt+Super+D (lite bind) AND Ctrl+Alt+Super+D (normal bind) — §4.10's two.

# The accounting rule — the SAME formula recheck() uses (target.py `expected`):
#   expected = binding.cursor_bytes + inserted_bytes
#   benign:  cursor == expected and anchor == cursor (our own commit, cause input_method)
#   revoke:  cursor != expected → "caret moved"; anchor != cursor → "selection present"

# The revocation action — AT THE TARGET, composing with S3's leave():
#   target.leave()          # host releases the grab (wire: zwp_input_method_keyboard_grab_v2.release)
#                           #      + binding cleared → later ops REFUSE "not acquired" (S3 contract)
#   controller.halt_for_takeover(reason)   # one recorded reason; queue drained into late-discard

# TakeoverWatch.on_event MUST be quick + never raise (it runs on the manager's reader thread,
# which is already exception-guarded — stay within its budget anyway; leave() is a 0.25 s request).
```

### Integration Points

```yaml
WIRE (existing seams, no new wiring in this task):
  - ImeProcess(on_event=watch.on_event)     # manager already forwards ALL events (T4 feed)
  - ImeTarget(proc).leave()                  # S3's landed lifecycle — the revocation vehicle
  - controller.halt_for_takeover(reason)     # NEW seam this task adds (consumed by M6.T2 wiring)

PRODUCES:
  - takeover-complete adapter → P1.M4.T5 (G3 real-field matrix: "focus change mid-operation",
    "a refusing target", pane/tab/window-switch rows all exercise THIS detection live)
  - P1.M6.T2.S1 wires TakeoverWatch into the daemon's bulk arm path (NOT this task)

PARALLEL-SAFE (T3.S3 Implementing now):
  - shared: protocol.py / ime_host.py / test_ime_host.py — APPEND-only edits on different lines
    (grab vs cancel); target.py untouched by this task. See research note §5.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
ruff check voice_typing/ime/ voice_typing/bulk_controller.py tests/test_ime_takeover.py --fix
ruff format voice_typing/ime/ voice_typing/bulk_controller.py tests/test_ime_takeover.py
# Expected: zero errors. (No mypy config in this repo — ruff is the gate.)
```

### Level 2: Unit Tests (the deliverable's gate)

```bash
# The full IM + bulk suite (T3.S3's success command + the new file) — two timeouts per AGENTS.md:
timeout 180 .venv/bin/python -m pytest tests/test_ime_takeover.py tests/test_ime_host.py \
  tests/test_ime_protocol.py tests/test_ime_target.py tests/test_ime_wlwire.py \
  tests/test_ime_manager.py tests/test_bulk_delivery.py tests/test_bulk_controller.py \
  tests/test_g2_bulk_gate.py -q
# (set the bash tool `timeout` to ~240.) Expected: all green — zero regression in S1–S3/controller/G2.
```

### Level 3: Integration (static — no live compositor needed)

```bash
# Confirm no forbidden imports (purity) + the grab request exists at the wire:
grep -L "import evdev\|wayland" voice_typing/ime/takeover.py   # takeover.py must not match
grep -n '"grab"' voice_typing/ime/protocol.py                  # REQUEST_CMDS grew
grep -n "grab_keyboard" voice_typing/ime/ime_host.py           # the handler sends it
# Optional live evidence (ONLY inside the disposable lab desktop; NEVER the operator desktop):
IME_TAKEOVER_LAB=1 timeout 120 .venv/bin/python tests/ime_takeover_lab.py  # if implemented
```

### Level 4: Contract audit (grep-provable invariants)

```bash
# No grace timer anywhere in the ime package (the chord is composition-matched, never timed):
grep -rn "grace\|1\.5" voice_typing/ime/ | grep -v "^.*#" || echo "ok: no grace window"
# The chord rule references the §4.10 binds' composition:
grep -n "CHORD_MODS\|KEY_D" voice_typing/ime/takeover.py
# target.py untouched by this task:
git diff --stat voice_typing/ime/target.py   # (empty after S3's own land — coordinate, don't revert)
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 2 suite green (exact command, all 9 files); ruff clean; only listed files in `git status`.
- [ ] Detector matrix fully pinned (Success Definition (b) — every bullet has a test).
- [ ] Revocation pinned ((c)): grab released at the wire, one leave, post-revoke refusal, halt idempotent.
- [ ] Watch wiring pinned ((d)); logs text-free ((e)).

### Feature Validation

- [ ] All contract points (listeners / revocation / mutation-time re-checks / evidence rules) covered.
- [ ] Chord-ignored is composition-based; no grace timer exists (Level 4 grep).
- [ ] target.py untouched; manager.py untouched; no config/docs changes.

### Code Quality Validation

- [ ] takeover.py is stdlib-pure, constructor-injected, unit-tested with fakes (no compositor needed).
- [ ] Appends to shared files don't collide with S3's regions (grab vs cancel).
- [ ] Anti-patterns avoided (below).

### Documentation & Deployment

- [ ] Module docstrings carry the lineage + evidence citations (rows O/O2) like the sibling modules do.
- [ ] DOCS: none required by the contract — docstrings only.

---

## Anti-Patterns to Avoid

- ❌ Don't re-run route discovery or re-prove the wire (R.4: decided; rows O/O2 are the evidence).
- ❌ Don't port the legacy 1.5 s grace window — the chord is matched by key composition ONLY.
- ❌ Don't set a daemon-side flag and skip the target-side release — the grab must actually be dropped.
- ❌ Don't touch `target.py` (S3 owns it; `leave()` already is the revocation vehicle).
- ❌ Don't duplicate the controller's stop teardown — `halt_for_takeover` re-uses it.
- ❌ Don't block or raise from the reader-thread callback; don't log recognition text.
- ❌ Don't run anything against the live desktop — labs are env-gated + disposable-desktop-only.

---

## Confidence Score

**9/10** — the design composes entirely with landed, tested seams (host event forwarding, manager
`on_event` feed, S3's `leave()`, controller stop machinery); the policy module is pure and its matrix is
fully enumerated; the evidence (rows O/O2) settles the wire behavior. Residual risk: the
parallel-edit collision with T3.S3 in three shared files — mitigated by append-only discipline on
disjoint regions + the untouched-target.py split.

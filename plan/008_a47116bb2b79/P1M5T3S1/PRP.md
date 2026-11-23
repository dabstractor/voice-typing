# PRP — P1.M5.T3.S1: Conditional clipboard insert-fallback + G4 gate (or recorded skip)

## Goal

**Feature Goal**: The decision INPUT is already recorded and says **NEEDED**: the refreshed G3 matrix
(`plan/008_a47116bb2b79/architecture/g3_field_matrix.md`, P1.M4.T5.S2, ghostty 1.4.0-2 =
"blocked — activate not_activated", route table `clipboard_fallback_m5t3: "needed (ghostty-class
insert blocked at 1.4.0-2)"`). Therefore: implement the **insert-only clipboard TargetAdapter** for
ghostty-class terminals under the **R.6 contract** (PRD §4.2sexies) as a `DeliveryTarget`
(`voice_typing/bulk_delivery.py`), and run the **G4 clipboard gate** (PRD R.7) in a disposable
private desktop — producing honest per-leg evidence, where **"adapter UNAVAILABLE under a live
history watcher" is a legitimate, contract-compliant SUCCESS outcome** (R.6: "If this cannot be
proven with the local manager, that adapter is unavailable — never disable the manager").

**Deliverable** (5 NEW code files + 1 unit-test file + evidence; **ZERO modifications** to any landed
file — adds-only, the M5.T2.S1/S2 house rule):
1. `voice_typing/clipboard_target.py` — the adapter (Mode A: module docstring carries the R.6
   contract verbatim-clause-by-clause). Insert-only: paste deltas via one trigger chord; corrections
   honestly REFUSED; no `type_character`/`press_backspace` surface, no legacy-backend fallback.
2. `tests/test_clipboard_target.py` — pure unit tests (fakes; no desktop, always collected).
3. `tests/clipboard_g4_support.py` — pure stdlib helpers: G4 leg models, verdict vocabulary
   (`verified (versions + evidence) | unprovable (reason) | blocked (reason)`), nonce/snapshot
   models, bounded (≤150-line) report renderer.
4. `tests/clipboard_g4_lab.py` — env-gated live lab (`CLIPBOARD_G4_LAB=1`; the paste-lab +
   `ime_g3_matrix_lab.py` two-phase-boot pattern): disposable Xvfb + private D-Bus + sway, isolated
   Ghostty byte-reader target, a PRIVATE clipboard-history manager, the six G4 legs, verdicts →
   `<root>/verdicts.jsonl`, exit 1 on any leg that fails to record.
5. `tests/test_clipboard_g4_support.py` — unit tests for the helpers (normal sweeps; no desktop).
6. `plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md` + beside it
   `g4_clipboard_verdicts.jsonl` — the bounded evidence report (the item's OUTPUT): one verdict per
   R.6 clause + per G4 leg, live versions, the final availability statement (AVAILABLE / UNAVAILABLE
   under watcher / UNAVAILABLE other-reason), and the route-table citation.

**Success Definition**:
- (a) The decision step is recorded FIRST: read the live route table in `g3_field_matrix.md`
      (`clipboard_fallback_m5t3`); at HEAD it says "needed" → implement. (If a future matrix re-run
      flips it, the ELSE branch = record "not needed at current versions" citing the matrix — but do
      NOT re-run the matrix yourself; it is P1.M4.T5.S2's artifact.)
- (b) The adapter implements `DeliveryTarget` faithfully: `acquire()` fails BEFORE delivery when a
      clipboard-history watcher is detected (reason string recorded) or the snapshot cannot be taken;
      `show()` pastes ONLY the delta of a pure extension (1 op), REFUSES a diverging span (insert-only
      row), `finalize()` matching ⇒ UNCHANGED with no edit; `leave()` never writes; `cancel()` refuses
      honestly (an insert-only route cannot remove owned text — record, don't fake).
- (c) All four R.6 clauses have a named mechanism in the module docstring AND a G4 leg that tests it:
      (1) preserve ALL prior formats AND bytes (data-control source serving per-type bytes — wl-copy
      single-stream restore is INSUFFICIENT); (2) ownership distinguished from a later identical copy
      (sentinel nonce MIME, NOT content comparison); (3) simultaneous user paste protected
      (mutation-time nonce recheck + abort; real key ⇒ existing HALT path); (4) partials kept out of
      the history watcher (watcher detection ⇒ UNAVAILABLE; never disable the manager). PRIMARY is
      never touched.
- (d) G4 runs all six legs with contents/history/formats/target assertions (NEVER exit codes):
      private manager (text+image watchers); simultaneous copies incl identical bytes; user paste
      during transfer; empty/rich-text/image originals; failure before/after the data request;
      process death.
- (e) Timeouts: lab `timeout 420 env CLIPBOARD_G4_LAB=1 .venv/bin/python tests/clipboard_g4_lab.py`
      (bash-tool 480); unit `timeout 120 .venv/bin/python -m pytest tests/test_clipboard_target.py
      tests/test_clipboard_g4_support.py -q` (bash-tool 130). Plain `pytest tests/` never boots a
      desktop (env gate verified). Nothing left behind (EXIT-trap temp-root teardown; `git status`
      shows only the new files); the live desktop, real clipboard, PRIMARY, mic, and service are
      never touched.

## User Persona

**Target User**: Internal — three consumers:
1. **P1.M6.T2.S1 (dispatch wiring)** — will route ghostty-class fields to this adapter; it needs the
   `DeliveryTarget` surface + the honest availability semantics (UNAVAILABLE reasons) already encoded.
2. **P1.M7.T1.S1 (G6 graduation)** — reads `g4_clipboard_evidence.md`; over-claiming here corrupts
   the gate. An honest "UNAVAILABLE under watcher" is a correct deliverable; a fabricated "works"
   is fatal.
3. **The operator** — whose desktop, clipboard, PRIMARY selection, service, and config MUST be
   untouched (R.4/R.7); the disposable-desktop discipline is the guarantee.

**Use Case**: Bulk-text delivery (Rev 4) needs an insert path for ghostty-class terminals (IM route
blocked at 1.4.0-2). The adapter pastes recognition deltas as ONE bracketed paste each; when a
clipboard-history manager runs, the adapter refuses to engage (R.6 unprovable) instead of polluting
history or disabling the manager.

**Pain Points Addressed**: (1) ghostty-class insert has no IM route — the matrix names clipboard as
the only insert fallback; (2) the clipboard is USER-OWNED state — naive stage/restore destroys
multi-format offers, leaks partials into history, and confuses identical copies; (3) honesty pressure
— R.6 pre-declares that the contract may be unprovable, and the deliverable must record which.

## Why

- **The matrix already decided the route** (R.4 #2: do NOT re-run route discovery): ghostty-class =
  clipboard insert-fallback under R.6. This item is the decided implementation + its safety gate.
- **G4 is the only proof that a clipboard route is safe to ship**: the PRD names four insufficient
  mechanisms (compare-before-restore, sleep-before-restore, `--paste-once`, "first reader = the
  editor") precisely because the failure modes (clobbered multi-format clipboard, polluted history,
  misattributed ownership) damage USER state, not just ours.
- **The evidence base is landed**: paste-lab mechanism proof (ONE bracketed paste, 153/175 ms,
  0x08→spaces ⇒ insert-only), wlwire stdlib wire lineage, the G3 harness pattern, and the
  `DeliveryTarget` contracts — this is a measured extension, not discovery.
- **Parallel items stay unblocked**: M5.T2.S1/S2 (in flight) share zero files; M6 wiring consumes
  this adapter's surface afterward.

## What

Three phases: **(1) decision re-check** (read the route table; needed ⇒ proceed), **(2) implement the
insert-only adapter** (Mode A docstring + DeliveryTarget + snapshot/nonce/restore/watcher-detection
mechanisms), **(3) run G4 + write the bounded evidence report**.

### Success Criteria

- [ ] Decision recorded: route table cited verbatim; "needed" at HEAD confirmed before any code.
- [ ] `voice_typing/clipboard_target.py` exists with the R.6 contract in its docstring (Mode A) and
      implements `DeliveryTarget` (acquire/show/finalize/leave/cancel) with insert-only semantics.
- [ ] Multi-format snapshot+restore implemented via a data-control source (per-type bytes); wl-copy
      used only where it is provably sufficient (staging), never as the restore of a multi-format
      snapshot.
- [ ] Sentinel-nonce ownership distinction; mutation-time recheck + abort; watcher detection ⇒
      acquire-time UNAVAILABLE with reason; PRIMARY never bound.
- [ ] G4 lab runs all six legs under both AGENTS.md timeouts; every leg asserts
      contents/history/formats/target (never exit codes); verdicts.jsonl + bounded report written.
- [ ] Unit tests green; regression neighbors green (`tests/test_bulk_delivery.py`,
      `tests/test_ime_g3_matrix_support.py`); fast sweep unaffected (env gate).
- [ ] Adds-only: `git status --porcelain` shows only the new files; no landed file modified.
- [ ] The report's availability statement is honest (AVAILABLE / UNAVAILABLE under watcher / other),
      with the ghostty 1.5.0 matrix watch noted as the future ELSE trigger.

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the recorded decision input + its file/key, the landed
`DeliveryTarget` contract surface, two adapter exemplars with line-level structure, the paste-lab
mechanism recipe (disposable desktop, staging, trigger, witness), the R.6 clause→mechanism map
(research §3), the six G4 legs with their assertion discipline, the exact run commands + timeouts,
the adds-only scope, and the honest-outcome rule (UNAVAILABLE = success). No inference required.

### Documentation & References

```yaml
# MUST READ — the DECISION INPUT (read FIRST; do not re-run the matrix).
- file: plan/008_a47116bb2b79/architecture/g3_field_matrix.md
  why: "Route table at the bottom: `clipboard_fallback_m5t3: \"needed (ghostty-class insert blocked
        at 1.4.0-2)\"` + per-class routes (ghostty → clipboard insert-fallback R.6; foot/kitty → im-v2
        insert-only + cooperating-editor corrections; gtk → im-v2 full). Ghostty row: 'activate
        not_activated at 1.4.0-2'. Open item: 1.5.0 watch (the future ELSE/skip trigger)."
  critical: "The route table is derived + unit-tested by tests/ime_g3_matrix_support.py::
             derive_route_table — cite it, never re-derive. If (counterfactually at HEAD) the key
             said not-needed, the ELSE branch = record the skip citing this file and STOP."

# MUST READ — the contracts the adapter implements (PURE; import THIS, never the reverse).
- file: voice_typing/bulk_delivery.py
  why: "DeliveryTarget Protocol (acquire/show/finalize/leave/cancel signatures VERBATIM), ShowResult
        taxonomy (applied|unchanged|refused|unknown; refused/unknown disarm; unknown never retried),
        AcquireResult(ok,handle,revision,reason), rendered_equal zero-diff guard, map_span units rule."
  critical: "The adapter must not add a typing fallback surface (no type_character/press_backspace).
             The controller owns deadlines — never self-time-out inside the adapter."

# MUST READ — adapter exemplars (FOLLOW the structure; do not modify them).
- file: voice_typing/pi_editor.py
  why: "PiEditorTarget (:352) — the newest DeliveryTarget: Binding dataclass as the opaque handle,
        mutation-time re-checks, REFUSED/UNKNOWN discipline (:455-533). Structural template."
- file: voice_typing/ime/target.py
  why: "ImeTarget (:75) — FieldBinding + recheck() (:126) + _owned_region_intact (:264): how an
        insert-only class refuses corrections honestly. Mirror this for diverging spans."

# MUST READ — the paste mechanism evidence (run-form + recipe; NEVER edit this file).
- file: tools/paste-lab/ghostty_probe.py
  why: "The proven mechanism: disposable desktop (xvfb-run + dbus-run-session private bus + sway,
        WLR_BACKENDS=x11, WLR_RENDERER=pixman, private HOME/XDG, refusal guard :69-74), staging
        `wl-copy --foreground --type text/plain;charset=utf-8` (:101-104), verify `wl-paste
        --no-newline`, trigger `xdotool key --delay 10 ctrl+shift+v`, byte-reader target with
        bracketed-paste marks + atomic tmp→rename publish, SIGKILL process-group teardown."
  critical: "NO --paste-once (probe comment :104 — 'a read by a history manager isn't a target
             acknowledgement'). Results: 951-B Unicode = ONE exact bracketed paste, 153/175 ms;
             pasted 0x08 → SPACES ⇒ insert-only BY DESIGN; corrections are the cooperating-editor
             seam's job (M5.T1), never this route."

# MUST READ — external clipboard facts (wl-clipboard + managers + data-control).
- file: plan/008_a47116bb2b79/architecture/external_tech_notes.md
  why: "§5 wl-clipboard: wl-copy forks/parent-exits (5.2); multi-format = ONE stream ⇒ wl-copy CANNOT
        restore multi-format offers (5.4 — hence the data-control source); managers snapshot EVERY
        offer via data-control wl-paste --watch (5.5); cliphist/wl-clip-persist/clippie likely not
        installed locally (5.6 — the G4 lab therefore runs its OWN private watcher). PRIMARY is a
        separate selection (--primary) — never touched (5.1)."
- url: https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-data-control-unstable-v1.xml
  why: "zwlr_data_control_manager_v1 (v2 advertised on this box — im-lab README:79-84): data_source
        offer(mime_type) + send(mime_type, fd) events ⇒ a source can serve DIFFERENT bytes per type —
        the ONLY in-repo-feasible multi-format restore. set_selection on the data-control device
        replaces the clipboard selection exactly like wl_data_device.set_selection."
  critical: "Hand-roll this client on the wlwire skeleton (voice_typing/ime/wlwire.py: Client/Event/
             u32/i32/wstr) — pywayland is NOT importable in the daemon venv (verified, d2 map §6)."

# MUST READ — harness pattern + gate discipline.
- file: tests/ime_g3_matrix_lab.py
  why: "The env-gated two-phase lab pattern to mirror: GATE_ENV (:64,:102), `timeout 420 env
        IME_G3_MATRIX_LAB=1 ...` run form (:9), verdicts.jsonl emission, EXIT-trap teardown,
        session-group process kills (never pattern-sweeps)."
- file: plan/008_a47116bb2b79/P1M5T2S1/PRP.md        # parallel, in flight — ZERO overlap, cite only
- file: plan/008_a47116bb2b79/P1M5T2S2/PRP.md        # parallel, in flight — its browser row MAY later
  why: "M5.T2.S2's browser-row verdict may EXTEND the need to browser-class inserts (its PRP:73-74,
        :513) — it never blocks this item; the matrix doc stays the single decision input. Do NOT
        touch their files (tests/ime_g3_field_edit.py, fixtures, editor/browser labs, reports)."

# MUST READ — AGENTS.md (timeout discipline for every command you run).
- file: AGENTS.md
  why: "Rule 1 two-timeouts on EVERY non-trivial command (inner GNU timeout + bash-tool timeout);
        never foreground the daemon; bound every scratch file. The G4 lab mutates a PRIVATE
        clipboard inside a disposable desktop only — never the real one."

# MUST READ — the PRD spec (the oracle).
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.6 (the four clauses + 'INSUFFICIENT' list + PRIMARY + never-disable-the-manager),
        R.7 G4 (the six legs + 'verify contents, history, all original formats, and the target, never
        exit codes'), R.3 (DeliveryTarget semantics; 'No control bytes, tabs, newlines, escape
        sequences, paste delimiters, or Enter as input'), R.1 (event-count law: insertion=1, zero-diff=0),
        R.4 (clipboard = insert fallback for ghostty-class ONLY; do not re-run route discovery)."

# Cross-refs (cite, don't re-derive).
- file: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md   # §5-6: wlwire lineage, env probes, open risks
- file: plan/008_a47116bb2b79/P1M5T3S1/research/clipboard_g4_research.md  # THIS item's research (clause→mechanism map, G4 legs)
```

### Current Codebase tree (relevant slice — state at P1.M5.T3.S1)

```bash
voice_typing/
├── bulk_delivery.py            # PURE contracts: DeliveryTarget/ShowResult/AcquireResult/rendered_equal (CONSUME)
├── bulk_controller.py          # controller (deadlines owned HERE; adapter never self-times-out) (CONSUME)
├── ime/wlwire.py               # stdlib Wayland wire client — the reuse skeleton for data-control (CONSUME)
├── ime/target.py               # ImeTarget — insert-only refusal exemplar (FOLLOW)
├── pi_editor.py                # PiEditorTarget — binding/recheck exemplar (FOLLOW)
└── clipboard_target.py         # ← NEW (Task 1): the insert-only clipboard adapter (Mode A)
tests/
├── ime_g3_matrix_lab.py        # env-gated lab pattern (FOLLOW); GATE_ENV precedent
├── ime_g3_matrix_support.py    # derive_route_table — the decision derivation (CITE)
├── test_bulk_delivery.py       # contracts tests (regression neighbor)
├── clipboard_g4_support.py     # ← NEW (Task 3): pure helpers + report renderer
├── clipboard_g4_lab.py         # ← NEW (Task 4): env-gated G4 lab (CLIPBOARD_G4_LAB=1)
├── test_clipboard_target.py    # ← NEW (Task 2): adapter unit tests (fakes)
└── test_clipboard_g4_support.py# ← NEW (Task 5): helper unit tests
tools/paste-lab/ghostty_probe.py # mechanism evidence (READ ONLY — never edit)
plan/008_a47116bb2b79/architecture/
├── g3_field_matrix.md          # the DECISION INPUT (route table: clipboard_fallback_m5t3 = needed)
├── g4_clipboard_evidence.md    # ← NEW (Task 6): the bounded evidence report
└── g4_clipboard_verdicts.jsonl # ← NEW (Task 6): machine-readable verdicts
```

### Desired Codebase tree with files to be added/modified

```bash
# ALL NEW — zero modifications to landed files:
voice_typing/clipboard_target.py          # insert-only clipboard DeliveryTarget (Mode A docstring = R.6)
tests/test_clipboard_target.py            # unit tests (fakes; no desktop)
tests/clipboard_g4_support.py             # pure helpers: legs, verdicts, renderer
tests/clipboard_g4_lab.py                 # env-gated G4 lab (disposable desktop)
tests/test_clipboard_g4_support.py        # helper unit tests
plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md + g4_clipboard_verdicts.jsonl
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — wl-copy CANNOT restore a multi-format offer (one input stream under N -t types;
#   external_tech_notes §5.4). Restore MUST be a zwlr_data_control_v1 SOURCE serving per-type bytes
#   (offer(mime)+send(mime,fd)). Single-type-only restore = R.6 clause 1 FAILED, not "mostly done".
# CRITICAL #2 — NO --paste-once (paste-lab :104): a history manager's read would consume the
#   one-shot offer and the REAL paste would get nothing — silently. Stage with a persistent source.
# CRITICAL #3 — Content comparison CANNOT distinguish our restored offer from a later identical user
#   copy (PRD names compare-before-restore INSUFFICIENT). Use a sentinel nonce MIME
#   (x-voice-typing/nonce, random token per staging generation) on OUR sources only.
# CRITICAL #4 — Managers see EVERY selection via data-control (wl-paste --watch); there is NO
#   protocol-level hiding. Clause 4's honest mechanism = DETECT the watcher (pgrep known managers /
#   wl-paste --watch scans; data-control exposes no peer list) → acquire() FAILS with reason →
#   adapter UNAVAILABLE. NEVER stop/disable the manager. UNAVAILABLE-under-watcher is a SUCCESS
#   outcome of this item, not a failure.
# CRITICAL #5 — Insert-only BY DESIGN: pasted 0x08 bytes arrive as SPACES (paste-lab) — corrections
#   over this route are impossible; a diverging span is REFUSED (record the row insert-only).
#   Corrections for ghostty-class belong to the cooperating-editor seam (M5.T1), not here.
# CRITICAL #6 — One trigger chord = the sanctioned paste mechanism (R.2 shortcut-trigger evidence:
#   153/175 ms). Synthesized per-character typing + Backspace chains are FORBIDDEN (R.1); a single
#   Ctrl+Shift+V chord is not a typing fallback. Synthetic delivery must not self-trigger HALT or
#   leave modifiers held (R.5) — xdotool key presses+releases atomically in the lab.
# CRITICAL #7 — The controller owns deadlines ("the adapter is never trusted to self-timeout",
#   bulk_controller.py:54-58) — but the paste-lab evidence (~175 ms) must fit the 250 ms engineering
#   budget; G4 does NOT gate latency (G5 does) — record ms as mechanism info only, never claim G5.
# CRITICAL #8 — PRIMARY stays untouched: wl-copy/wl-paste default to the clipboard selection;
#   data-control set_selection = clipboard. NEVER bind zwp_primary_selection. G4 asserts PRIMARY
#   unchanged after every leg.
# CRITICAL #9 — Adds-only: no edits to bulk_delivery/bulk_controller/ime/**/pi_editor/daemon/
#   config.toml/pyproject/matrix-or-pi-or-editor-browser labs, and NO daemon dispatch wiring (that is
#   P1.M6.T2.S1's). The adapter ships as a library surface + lab evidence.
# CRITICAL #10 — Lab safety: the disposable-desktop refusal guard (paste-lab :69-74 pattern) must
#   gate the G4 lab; EXIT trap kills ONLY our session groups (never pattern-sweeps); two AGENTS.md
#   timeouts on every run; bounded logs (≤ a few MB per run, mktemp root auto-removed).
# CRITICAL #11 — pytest purity: plain `pytest tests/` must never boot a desktop — the lab is
#   env-gated (GATE_ENV="CLIPBOARD_G4_LAB"); unit tests use fakes only (no WAYLAND_DISPLAY needed).
# CRITICAL #12 — Never run the live daemon/voicectl/systemctl/pactl in this item; nothing here needs
#   the real desktop, real clipboard, or mic (R.7 isolation).
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/clipboard_target.py (NEW) — pure data shapes (stdlib only):
# @dataclass(frozen=True) ClipboardFormat: mime: str, data: bytes          # one snapshot entry
# @dataclass ClipboardSnapshot: formats: tuple[ClipboardFormat, ...], nonce: str, generation: int
# class ClipboardWatchdog…  # selection-event watcher: nonce match => ours; else => foreign
# class ClipboardTarget:    # implements bulk_delivery.DeliveryTarget
#   acquire() -> AcquireResult   # watcher detected? -> ok=False reason="clipboard-history watcher
#                                #   active — R.6 partials-out-of-history unprovable"
#                                # snapshot (all types+bytes) failed? -> ok=False reason=...
#   show(session, utterance, seq, expected_revision, span) -> ShowResult
#                                # rendered_equal(owned, span) -> UNCHANGED (0 events)
#                                # span extends owned prefix -> stage(nonce)+trigger+confirm -> APPLIED
#                                # span diverges -> REFUSED (insert-only row; record, never retry)
#   finalize(...) -> UNCHANGED on match (no edit); REFUSED on differ (cannot replace)
#   leave() -> restore snapshot; NO writes to any newly focused field
#   cancel() -> REFUSED with reason (insert-only route cannot remove owned text; nothing
#               pending -> UNCHANGED)
# ZwlrDataControlSource (wire, wlwire skeleton): offer(mime) per snapshot type + nonce sentinel;
#   on send(mime, fd) write THAT type's exact bytes; set_selection on the data-control device.
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: DECISION RE-CHECK (read-only, 1 command).
  - READ plan/008_a47116bb2b79/architecture/g3_field_matrix.md (route table at the bottom).
  - CONFIRM `clipboard_fallback_m5t3` == "needed (ghostty-class insert blocked at 1.4.0-2)".
  - RECORD the citation in the eventual report header. (ELSE branch, only if flipped: write the
    skip note into g4_clipboard_evidence.md citing the matrix + close — no code.)

Task 1: CREATE voice_typing/clipboard_target.py (Mode A docstring = the R.6 contract, clause by
  clause, each mapped to its mechanism + its G4 leg; follow pi_editor.py/ime/target.py structure).
  - IMPLEMENT ClipboardSnapshot (all MIME types + exact bytes via `wl-paste --list-types` +
    per-type reads; empty selection = empty snapshot), the nonce sentinel, and the data-control
    SOURCE on the wlwire skeleton for multi-format restore (CRITICAL #1).
  - IMPLEMENT ClipboardTarget(DeliveryTarget) with the insert-only semantics of the data-model
    block above; mutation-time nonce recheck before the trigger chord; abort->REFUSED on a foreign
    selection change mid-window; watcher detection at acquire (CRITICAL #4).
  - STAGING may reuse the paste-lab-proven `wl-copy --foreground --type text/plain;charset=utf-8`
    subprocess for the text offer — but the RESTORE is ALWAYS the data-control source.
  - NAMING: module clipboard_target.py; classes ClipboardTarget/ClipboardSnapshot; no daemon imports.

Task 2: CREATE tests/test_clipboard_target.py (pure unit tests, fakes for wl subprocesses + wire).
  - COVER: delta-vs-diverging span logic; rendered_equal no-op; finalize match/differ; cancel
    refusal; acquire failure reasons (watcher active; snapshot failed); nonce distinction (ours vs
    identical-bytes foreign); leave restores + writes nothing; ShowResult taxonomy obedience
    (refused/unknown never retried by the adapter itself).
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_clipboard_target.py -q  (bash-tool 130).

Task 3: CREATE tests/clipboard_g4_support.py (pure stdlib helpers).
  - MODELS: the six G4 legs; verdict vocabulary `verified (versions + evidence) | unprovable
    (reason) | blocked (reason)`; report renderer (≤150 lines) mirroring ime_g3_matrix_support.

Task 4: CREATE tests/clipboard_g4_lab.py (env-gated: GATE_ENV="CLIPBOARD_G4_LAB"; paste-lab +
  ime_g3_matrix_lab two-phase boot; refusal guard; EXIT-trap teardown; verdicts.jsonl).
  - DESKTOP: xvfb-run + dbus-run-session(private bus) + sway (WLR_BACKENDS=x11, pixman), private
    HOME/XDG_RUNTIME_DIR; isolated Ghostty running the byte-reader (paste-lab `receive` pattern).
  - PRIVATE MANAGER: `wl-paste --watch <store-script>` inside the disposable desktop, accepting
    text/* and image/png into a private store (this IS leg 1's watcher; also proves clause 4).
  - SIX LEGS (each asserts contents/history/all-formats/target — NEVER exit codes; PRIMARY checked
    unchanged after every leg):
    L1 manager history pollution: N live partial inserts -> does the store contain fragments?
        (expected honest outcome: adapter refuses to engage when watcher detected -> record
         UNAVAILABLE-under-watcher; if engagement happened, the store contents are the evidence)
    L2 simultaneous copies incl identical bytes: foreign set_selection mid-window (incl. a copy
        byte-identical to the original) -> nonce distinguishes; adapter aborts (REFUSED); user
        content intact
    L3 user paste during transfer: synthetic real key (xdotool) mid-window -> HALT/refuse; no
        second paste over the user's; target contents exact
    L4 original-offer classes: empty / text/plain+text/html / image/png originals -> snapshot +
        restore exact per-type bytes (the data-control source proof)
    L5 failure before/after the data request: target dies pre-read; adapter killed post-send ->
        outcome unknown-class, never falsely applied; contents intact
    L6 process death mid-cycle: SIGKILL the adapter -> clipboard ends restored-or-visibly-faulted;
        history + formats + PRIMARY verified
  - RUN: timeout 420 env CLIPBOARD_G4_LAB=1 .venv/bin/python tests/clipboard_g4_lab.py (bash-tool 480).

Task 5: CREATE tests/test_clipboard_g4_support.py (helper unit tests; normal sweeps, no desktop).
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_clipboard_g4_support.py
         tests/test_clipboard_target.py -q   (bash-tool 130)
  - REGRESSION neighbors: tests/test_bulk_delivery.py + tests/test_ime_g3_matrix_support.py green.

Task 6: WRITE the evidence (the item's OUTPUT).
  - plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md (≤150 lines, renderer-emitted):
    decision citation (route table), live versions (kernel/sway/ghostty/wl-clipboard), per-clause +
    per-leg verdicts, the AVAILABILITY statement (AVAILABLE / UNAVAILABLE under watcher / other),
    the ghostty 1.5.0 watch as the future ELSE trigger, bounded evidence links (verdicts.jsonl).
  - COPY verdicts.jsonl beside it as g4_clipboard_verdicts.jsonl.
  - HONESTY: a mechanism ms number is recorded as mechanism info, NEVER G5; an unprovable clause is
    recorded as unprovable — never smoothed over.
```

### Implementation Patterns & Key Details

```python
# The transfer cycle (one show() that inserts a delta):
#   1. snapshot   wl-paste --list-types -> per-type reads (ClipboardSnapshot, nonce minted)
#   2. stage      our source (text/plain;charset=utf-8 + x-voice-typing/nonce) set_selection
#   3. recheck    selection still carries OUR nonce?  foreign (incl. identical bytes) -> REFUSED, abort
#   4. trigger    ONE chord (lab: xdotool key ctrl+shift+v) — never per-char, never --paste-once
#   5. confirm    byte-reader witness received exactly our delta (bytes sent is NOT "applied")
#   6. restore    data-control source re-offering the snapshot's EXACT types, per-type bytes
#                 (+ leave() path identical; a killed adapter mid-cycle = L6's unknown/fault case)
# Deadline note: the RECEIVER (bulk_controller) owns the 250 ms deadline — the adapter never
# self-times-out; paste-lab evidence ~175 ms fits, but G4 does not gate latency.

# Insert-only span algebra (mirror ime/target.py's honest refusal):
#   k = common prefix(owned, span); k == len(owned) -> paste span[k:] (1 op, APPLIED)
#   rendered_equal(owned, span)                    -> UNCHANGED (0 events)
#   k < len(owned) (divergence = correction)       -> REFUSED (row insert-only; never retried)

# Watcher detection (clause 4): pgrep -af 'wl-paste.*--watch|cliphist|clipman|wl-clip-persist|clippie'
#   inside the TARGET session only; a hit => acquire() ok=False with the R.6 reason string. NEVER
#   stop/disable the manager (R.6). In the G4 lab the PRIVATE watcher is expected -> L1's verdict.
```

### Integration Points

```yaml
CONSUMES (read-only):
  - plan/008_a47116bb2b79/architecture/g3_field_matrix.md      # the decision input (route table)
  - voice_typing/bulk_delivery.py                              # DeliveryTarget/ShowResult/AcquireResult/rendered_equal
  - voice_typing/{pi_editor.py, ime/target.py, ime/wlwire.py}  # adapter exemplars + wire skeleton
  - tools/paste-lab/ghostty_probe.py                           # mechanism recipe (NEVER edit)
  - tests/ime_g3_matrix_lab.py + ime_g3_matrix_support.py      # lab pattern + route derivation (cite)
  - plan/008_a47116bb2b79/architecture/external_tech_notes.md  # §5 wl-clipboard facts
  - plan/008_a47116bb2b79/prd_snapshot.md                      # R.1/R.3/R.4/R.6/R.7

PRODUCES (all NEW):
  - voice_typing/clipboard_target.py + 4 test/lab files         # the adapter + its gates
  - plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md + g4_clipboard_verdicts.jsonl

FEEDS (downstream consumers):
  - P1.M6.T2.S1 (dispatch wiring)                               # routes ghostty-class to ClipboardTarget;
                                                                # consumes the availability semantics + reasons
  - P1.M7.T1.S1 (G6 graduation)                                 # reads g4_clipboard_evidence.md — the honest
                                                                # availability statement gates any claim

PARALLEL-SAFE:
  - P1.M5.T2.S1 (pi row, in flight) + P1.M5.T2.S2 (editor/browser rows, in flight): ZERO file overlap
    (their files: .pi/extensions, voice_typing/pi_editor.py, tests/pi_g3_row_*, tests/ime_g3_field_edit.py,
    fixtures, editor/browser labs + reports). Shared surface = READ-ONLY (bulk_delivery, matrix doc).
    M5.T2.S2's browser verdict may later EXTEND the fallback need; it never blocks or rewrites this item.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 60 .venv/bin/python -c "import voice_typing.clipboard_target, tests.clipboard_g4_support" 2>/dev/null \
  || timeout 60 .venv/bin/python -c "import voice_typing.clipboard_target"
# (mypy is NOT installed in this repo — do not run it; pytest is the gate.)
```

### Level 2: Unit Tests (the always-collected gate)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_clipboard_target.py tests/test_clipboard_g4_support.py -q
# (bash-tool timeout 130.) Expected: all green; no desktop, no WAYLAND_DISPLAY required.
timeout 120 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_ime_g3_matrix_support.py -q
# (bash-tool 130.) Expected: regression neighbors unchanged (adds-only).
timeout 300 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_daemon.py --ignore=tests/test_recorder_host.py --ignore=tests/test_feed_audio.py 2>&1 | tail -3
# (bash-tool 320; skip the CUDA-heavy files.) Expected: fast sweep green; the G4 lab is SKIPPED
# without CLIPBOARD_G4_LAB=1 (env-gate purity — assert it appears as skipped, never booted).
```

### Level 3: The G4 Lab (the item's live gate — disposable desktop only)

```bash
timeout 420 env CLIPBOARD_G4_LAB=1 .venv/bin/python tests/clipboard_g4_lab.py
# (bash-tool timeout 480.) Expected: six legs recorded to <root>/verdicts.jsonl; exit 0 when every
# leg recorded a verdict (verified OR honestly unprovable/blocked — an UNAVAILABLE-under-watcher
# outcome is a PASS of the gate discipline); exit 1 only when a leg failed to record/witness.
# AFTER: verify teardown — the mktemp root is gone; `git status --porcelain` shows only new files;
# the REAL clipboard/PRIMARY untouched (the lab never touched them by construction — sanity-check
# `wl-paste --no-newline | head -c 80` ONLY if you must, never mutate).
```

### Level 4: Evidence & Honesty Validation

```bash
# The report must carry: the route-table citation, live versions, per-clause + per-leg verdicts,
# the availability statement, and NO G5/timing claims.
grep -c "clipboard_fallback_m5t3\|needed" plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md
grep -ci "unavailable\|unprovable\|blocked" plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md
wc -l plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md   # ≤150
# Expected: citation present; the honest-outcome vocabulary present; bounded length.
```

## Final Validation Checklist

### Technical Validation
- [ ] Task 0 decision citation recorded (route table says "needed" at HEAD).
- [ ] Unit + regression + fast-sweep runs green under two timeouts; lab env-gated (skipped by default).
- [ ] G4 lab ran once end-to-end; verdicts.jsonl captured; teardown verified (temp root gone; adds-only git status).

### Feature Validation
- [ ] All success criteria from "What" met; the four R.6 clauses each have mechanism + G4 leg + verdict.
- [ ] Insert-only semantics verified (diverging span REFUSED; finalize-match UNCHANGED; no typing surface).
- [ ] PRIMARY asserted untouched; multi-format restore proven (or recorded unprovable) via L4.
- [ ] The availability statement is honest and cites evidence; UNAVAILABLE-under-watcher recorded as a
      legitimate outcome if that is what L1 showed.

### Code Quality Validation
- [ ] Follows pi_editor/ime_target structure; Mode A docstring carries the R.6 contract; stdlib-only
      module (wire via wlwire skeleton); no daemon imports in the adapter.
- [ ] Adds-only: zero modifications to landed files; scratch/logs bounded and torn down.

### Documentation & Deployment
- [ ] g4_clipboard_evidence.md + g4_clipboard_verdicts.jsonl in architecture/; feeds M6 wiring + G6.

---

## Anti-Patterns to Avoid

- ❌ Don't re-run route discovery or the matrix (R.4 #2) — the route table already decided; cite it.
- ❌ Don't use wl-copy to RESTORE a multi-format snapshot (single stream — collapses formats; R.6 clause 1).
- ❌ Don't use `--paste-once` (a manager read consumes it; the real paste silently gets nothing).
- ❌ Don't distinguish ownership by content comparison (PRD: INSUFFICIENT) — use the nonce sentinel.
- ❌ Don't disable/stop/kill the user's clipboard manager — detect + go UNAVAILABLE instead.
- ❌ Don't deliver corrections over this route (0x08 → spaces; insert-only) — REFUSE honestly.
- ❌ Don't add a typing fallback or per-character synthesis (R.1 event-count law; no §4.3 backends).
- ❌ Don't touch PRIMARY, the real clipboard, the live desktop, the daemon, or the service (R.7).
- ❌ Don't claim G5 timing from the lab's ms numbers (mechanism info only).
- ❌ Don't smooth over an unprovable clause — record it; the honest UNAVAILABLE is the deliverable.
- ❌ Don't modify landed files or the parallel M5.T2 items' files — adds-only.
- ❌ Don't run any command without both AGENTS.md timeouts; don't leave scratch behind.

---

## Confidence Score

**8/10** — one-pass success likelihood. The decision input is recorded (route table: needed), the
contract surface (`DeliveryTarget`) is landed with two adapter exemplars, the paste mechanism is
lab-proven with a runnable recipe (staging/trigger/witness/teardown), the wlwire skeleton exists for
the data-control source, and the external wl-clipboard facts (multi-format limits, watcher behavior,
PRIMARY separation) are documented with URLs. The two genuine risks: (1) the hand-rolled
zwlr_data_control_v1 source is new wire code (opcode tables must match the wlr XML — the wlwire
lineage did exactly this for input-method-v2, so the pattern is proven, but budget iteration); (2)
clause 4 is expected to land UNAVAILABLE-under-watcher — which the PRD pre-authorizes as the honest
outcome; the main residual is execution discipline (env-gating, teardown, bounded evidence), all of
which have in-repo precedents spelled out above.

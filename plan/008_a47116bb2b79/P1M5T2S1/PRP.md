# PRP — P1.M5.T2.S1: G3 row — pi chat prompt in isolated Ghostty (cooperating-editor route)

## Goal

**Feature Goal**: Execute the **first G3 real-field row** (PRD §4.2sexies R.7 G3; R.3/R.4 milestone
"the terminal chat prompt is the first milestone: prove pi's real input editor inside isolated
Ghostty"): launch a **disposable private headless Sway + isolated Ghostty** (the paste-lab pattern)
running **real pi with S1's `voice-editor.ts` extension**, then drive **scripted partials/finals
through the REAL pi editor via S2's `PiEditorTarget` adapter** (the cooperating-editor seam — the
route DECIDED by the refreshed matrix, since ghostty 1.4.0-2's IM route is blocked), asserting the
editor's **own text + caret** (the extension's `read` = `getText()`/`getCursor()`, never a pty byte
reader, scrollback, or fake editor), the **visible prompt** (only if visibility instrumentation
exists — else the row is honestly "not verified", never "passed"), **no folded-paste placeholders**,
**no shortcut execution/submission**, and **no neighbor changes**.

**Deliverable** (3 NEW lab files + 1 evidence doc; **ZERO modifications** to S1's `.pi/extensions/**`,
S2's `voice_typing/pi_editor.py`, `bulk_controller.py`, `bulk_delivery.py`, `daemon.py`, any
`tests/ime_*`/`tests/test_pi_editor.py`/matrix-lab file):
1. `tests/pi_g3_row_lab.py` — the env-gated lab (`PI_G3_ROW_LAB=1`; mirrors
   `tests/ime_g3_matrix_lab.py`): builds the disposable desktop, boots pi, drives the full G3 trace
   list through `PiEditorTarget`, witnesses via `read` + per-op `changes` counts, emits the verdict.
2. `tests/pi_g3_row_support.py` — pure helpers: the G3 trace/payload set (ASCII, "Zoë — naïve 日本語
   🫡", ~1 KB long payload, first-word-correction cases, zero-diff repeats, refusal cases), the
   verdict-row model (`untested | insert-only | blocked (reason) | not verified (reason) | verified
   (versions + evidence)`), a bounded (≤120-line) row-table renderer.
3. `tests/test_pi_g3_row_support.py` — pure unit tests for the helpers (run in normal sweeps; no
   desktop, no pi).
4. `plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md` — **the bounded row report** (the
   item's OUTPUT: "pi-prompt row verified | blocked (reason) with evidence links"), plus a
   machine-readable `pi_row_verdicts.jsonl` beside it.

**Success Definition**:
- (a) The lab runs end-to-end under two AGENTS.md timeouts and leaves NOTHING behind (EXIT-trap
      temp-desktop removal; repo `git status` unchanged apart from the new files + evidence).
- (b) The G3 trace list is exercised through `PiEditorTarget` (acquire → inserts → correction →
      zero-diff repeats → Unicode/long payloads → takeover → focus-switch → refusals → cancel), and
      each step asserts the editor's own text + caret exactly (via `read`) and the per-op `changes`
      count (applied=1, unchanged=0 — the edit-count law; no delete/retype frame pairs).
- (c) The four contract assertions are each positively checked: no `\x1b[200~`/`\x1b[201~`/control
      bytes in the read-back text; no submission (buffer intact, no Enter, no message-shaped
      departure); no neighbor changes (sway tree window census before/after).
- (d) Takeover: a scripted REAL keypress (`xdotool`) mid-owned-fragment → S2's
      `PiEditorTakeoverWatch` fires the duck-controller's `halt_for_takeover` EXACTLY once; after
      takeover ops are REFUSED (dirty), no post-takeover mutation is attempted.
- (e) The row report records the verdict — **verified (with live versions + evidence links)**, or
      **blocked (reason)**, or **not verified (visibility instrumentation absent)** if the
      visible-prompt leg cannot be witnessed — with live versions (pi, ghostty, sway, kernel) and
      bounded evidence. A G2/lab pass never marks the row verified.
- (f) `timeout 120 .venv/bin/python -m pytest tests/test_pi_g3_row_support.py -q` green;
      `tests/test_pi_editor.py` + `tests/test_ime_g3_matrix_support.py` stay green (adds-only);
      `pytest tests/` fast sweep unaffected (the lab is env-gated, skipped by default).

## User Persona

**Target User**: Internal — three consumers:
1. **P1.M5.T3.S1 (conditional clipboard fallback)** — consumes this row's verdict: the matrix route
   table already says clipboard insert-fallback is "needed (ghostty-class insert blocked at
   1.4.0-2)" for INSERT; this row's verified/blocked verdict on the cooperating-editor seam decides
   what CORRECTIONS coverage the pi prompt has without the fallback.
2. **P1.M7.T1.S1 (G6 graduation assessment)** — counts "verified G3 rows for the pi prompt in
   Ghostty" from this row's evidence; over-claiming here corrupts the graduation gate.
3. **The operator** — the person whose desktop, service, config, and bindings MUST be untouched
   (R.4: "Development MUST NOT change the operator's service, config, or bindings as a side
   effect"); the private-desktop discipline is the guarantee.

**Use Case**: Bulk-text delivery (Rev 4) needs proof that recognition updates become visible in the
real chat prompt with ONE edit per change and correct in place. This row is that proof for the
first milestone field: pi's editor inside an isolated Ghostty, driven through the same adapter the
daemon will use (S2), witnessed by the editor's own state.

**Pain Points Addressed**: (1) The IM route is DEAD on ghostty 1.4.0-2 — without this row the pi
prompt has NO verified delivery route. (2) The seam was proven mechanism-level (S1's tmux proof) —
a lab pass never marks a row verified; only this app-side-witnessed row does. (3) Synthetic typing
is forbidden in bulk mode (R.1) — this row proves a one-edit insert/correct route exists.

## Why

- **PRD §4.2sexies R.3/R.4 makes this the FIRST milestone**: "The terminal chat prompt is the first
  milestone: prove pi's real input editor inside isolated Ghostty… Field FIRST… Prove insert AND
  correct before any mic integration." S1 built the editor side, S2 the daemon side; THIS row is
  the real-field join.
- **The refreshed matrix (P1.M4.T5.S2) DECIDED the route**: ghostty 1.4.0-2 = IM blocked
  ("activate not_activated"); foot/kitty = insert-only; corrections for terminals ride the
  cooperating-editor seam, NEVER IM delete. This row executes that decision — do NOT re-run route
  discovery (R.4 #2).
- **It is the evidence artifact G6 consumes**: "verified G3 rows for the pi prompt in Ghostty" is a
  graduation precondition; an honest blocked/not-verified verdict now is cheaper than a fabricated
  pass discovered later.

## What

An env-gated G3 lab + pure support helpers + unit tests + a bounded row report. The lab: disposable
private headless Sway (WLR_BACKENDS=x11, pixman, software GL, private XDG_RUNTIME_DIR/TMPDIR) →
isolated Ghostty (`--gtk-single-instance=false --shell-integration=none`) → real `pi` (cwd = temp
project with `.pi/extensions/voice-editor.ts`; no API key, no message ever sent) → wait for
`$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock` → drive `PiEditorTarget` through the G3 traces →
witness + assert → write the verdict + report. Plain `pytest tests/` never boots the desktop.

### Success Criteria

- [ ] (a)–(f) of the Success Definition, per the Validation Loop.
- [ ] All assertions come from app-side witnesses: `read` (text/cursor/owned/dirty/units) + per-op
      `changes` counts + sway window census. No pty scraping, no scrollback capture, no fake editor.
- [ ] UTF-16 offsets only via `bulk_delivery.map_span`; astral payload (🫡) exercised.
- [ ] The row report is bounded (≤120 lines), carries live versions, and states exactly one
      verdict: `verified` / `blocked (reason)` / `not verified (visibility instrumentation absent)`.
- [ ] `git status --porcelain` shows only the new files (+ this plan/ dir).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer gets: the S1 socket protocol v1 verbatim (ops/replies/events/ownership +
the `changes` instrumentation), the S2 adapter surface (constructor ducks, result taxonomy,
takeover watch), the matrix route verdict, the paste-lab disposable-desktop env recipe verbatim
(with the one HOME delta called out), the G3 trace list scoped to one window, the witness taxonomy
(what counts as "the editor's own text + caret" vs "the visible prompt"), and every isolation/
timeout gotcha. No pi/TS authoring is needed — S1's extension is landed and treated read-only.

### Documentation & References

```yaml
# MUST READ — this item's own research (verified this session; compact, authoritative).
- docfile: plan/008_a47116bb2b79/P1M5T2S1/research/pi_prompt_g3_row_research.md
  why: "§1 the two INPUT contracts verbatim (S1 protocol v1 incl. the `changes` onChange-count
        instrumentation + ownership/dirty semantics; S2's PiEditorTarget/PiEditorClient/
        PiEditorTakeoverWatch surface + refusal taxonomy). §2 the matrix verdict (ghostty 1.4.0-2
        IM blocked → cooperating-editor seam; Hyprland nested-boot dead → private Sway). §3 the
        paste-lab disposable-desktop recipe VERBATIM (env dict, xvfb-run+dbus-run-session, sway
        spawn, ghostty flags, xdotool window find, EXIT-trap cleanup) + the HOME-preservation delta
        (pi needs its real home; isolate everything else). §4 the G3 trace list + the four contract
        assertions + the verdict vocabulary. §5 the harness trio shape. §6 twelve gotchas."

# MUST READ — S1's PRP (the socket contract's source of truth; extension LANDED at .pi/extensions/voice-editor.ts).
- file: plan/008_a47116bb2b79/P1M5T1S1/PRP.md
  why: "'The socket protocol (v1 — S2's contract; keep stable)' block (:285-310): ops insert/replace/
        cancel/read, replies applied|unchanged|refused + read's text/cursor/owned/dirty/units:'utf-16',
        events {\"event\":\"takeover\",\"source\":\"key\"}, ownership = [start,end) UTF-16 since the last
        boundary, no-id-echo JSONL, stale-socket unlink. CRITICAL #8: pi needs NO model/API key;
        find via shutil.which('pi') + PI_BIN override; export XDG_RUNTIME_DIR into the pane env."
  critical: "S1's proof ran pi in tmux on the real desktop — THIS row must upgrade to the isolated
             Ghostty disposable desktop (the milestone's explicit requirement). Never send a message
             in pi; never type into the operator's real terminal."

# MUST READ — S2's PRP (the adapter this row drives; IN FLIGHT — treat as contract).
- file: plan/008_a47116bb2b79/P1M5T1S2/PRP.md
  why: "The PiEditorClient/PiEditorTarget/PiEditorTakeoverWatch consumption surface (constructor
        ducks, one-request-in-flight, event-vs-reply dispatch), the refusal taxonomy strings
        ('pi socket absent'/'pi socket no reply'/'editor dirty'/'editor owns fragment'/…), the
        zero-diff ⇒ UNCHANGED with ZERO requests rule, UNKNOWN never retried, takeover latch
        (exactly one halt). The lab instantiates these classes; it does NOT re-implement them."
  critical: "Do NOT modify S2's files; if a field name drifted between the PRP and the landed code,
             READ the landed voice_typing/pi_editor.py and follow the CODE, recording the drift."

# MUST READ — the matrix verdict (the route decision INPUT).
- file: plan/008_a47116bb2b79/architecture/g3_field_matrix.md
  why: "ghostty 1.4.0-2 row = blocked for IM ('activate not_activated'); route table: ghostty →
        cooperating-editor seam (M5.T1); Hyprland relay blocked (do not attempt nested Hyprland);
        the 'G2/lab pass never marks a row verified' rule; the env-gated lab command precedent."

# MUST READ — the disposable-desktop recipe to reuse.
- file: tools/paste-lab/ghostty_probe.py
  why: "The verified private-headless-Sway + ghostty launch pattern (the contract mandates reuse):
        the guarded private root, the env dict (:153-157), xvfb-run -a dbus-run-session chain
        (:158), sway spawn + SWAYSOCK/WAYLAND_DISPLAY wait (:84-92), ghostty flags (:93),
        xdotool window find (:97), bounded waits + trap cleanup (:125-140, GNU timeout -k 2 25)."
  gotcha: "It sets HOME=folder — pi will NOT boot that way (node install + ~/.pi are home-resident).
           DELTA (documented in the row report): keep HOME real/read-only, isolate XDG_RUNTIME_DIR/
           XDG_CONFIG_HOME/TMPDIR + all Wayland surfaces; run pi with cwd = the temp project dir."

# MUST READ — the landed editor-side artifacts (read-only).
- file: .pi/extensions/voice-editor.ts
  why: "The actual extension the row loads (copy into the temp project's .pi/extensions/). Read it
        to confirm the LIVE protocol field names (if S1 drifted from the PRP, the code wins) and to
        enumerate what visibility instrumentation EXISTS (read's text/cursor; per-op changes;
        any render dump) — the 'visible prompt' leg's availability check."
- file: tests/pi_seam_support.py
  why: "S1's frozen op/reply dataclasses + payload builders ('Zoë — naïve 日本語 🫡' et al.) — reuse
        the payload vocabulary so the row and the seam proof agree; do not fork a second dialect."

# MUST READ — the harness patterns to mirror.
- file: tests/ime_g3_matrix_lab.py
  why: "The env-gated lab shape (IME_G3_MATRIX_LAB=1 gate, bounded run, verdicts.jsonl emission,
        versions capture). THIS row's lab = the same shape for pi+ghostty via the S2 adapter."
- file: tests/ime_g3_matrix_support.py + tests/test_ime_g3_matrix_support.py
  why: "The support-helpers + pure-unit-test split that keeps `pytest tests/` green without a
        desktop. Mirror for pi_g3_row_support."
- file: plan/008_a47116bb2b79/architecture/g3_gtk_rows.md
  why: "The row-report format precedent (versions, traces, verdicts, evidence links) the new
        g3_pi_prompt_row.md must match."

# MUST READ — the contracts the adapter imports (read-only vocabulary).
- file: voice_typing/bulk_delivery.py
  why: "ShowResult/AcquireResult/TargetUnits/map_span/rendered_equal — the lab asserts results in
        THIS vocabulary and computes UTF-16 offsets ONLY via map_span."

# PRD ground truth.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.1 (event-count law: insert=1, correction=1, zero-diff=0; no folded-paste
        placeholders; no control bytes/tabs/newlines/Enter), R.3 (delivery model; 'the terminal chat
        prompt is the first milestone… inside isolated Ghostty'; units rule), R.4 (field FIRST;
        route assignment DECIDED — no re-discovery; never fall back to typing; a blocked row is a
        legitimate result; MUST NOT change the operator's service/config/bindings), R.5 (takeover at
        the target; never retry may-have-landed ops), R.7 G3 (the trace list; rows report
        untested|insert-only|blocked|verified with versions+evidence; isolation: private compositor
        + synthetic input + isolated app instances; t_ms is mechanism-level, NEVER G5 timing)."

# External — xdotool/sway scripting mechanics used by the lab.
- url: https://man.archlinux.org/man/xdotool.1
  why: "`xdotool search --onlyvisible --maxdepth 1 --name …` (window find — the paste-lab line),
        `xdotool key --delay 10 <keysym>` (the scripted REAL keypress for the takeover leg),
        `xdotool windowactivate` (the focus-switch leg). All into the PRIVATE X display only."
- url: https://man.archlinux.org/man/swaymsg.1
  why: "`swaymsg -r get_tree` over the private SWAYSOCK — the neighbor-census witness (exact window
        set before/after each phase)."
```

### Current Codebase tree (relevant slice — state at P1.M5.T2.S1)

```bash
.pi/extensions/voice-editor.ts     # S1 LANDED (read-only for this item)
voice_typing/pi_editor.py          # S2 (in flight → will exist): PiEditorClient/Target/TakeoverWatch
voice_typing/bulk_delivery.py      # contracts (read-only): ShowResult/map_span/…
tests/
├── pi_seam_support.py             # S1's op/reply dataclasses + payload builders (reuse payloads)
├── test_pi_editor.py              # S2's adapter tests (read-only)
├── ime_g3_matrix_lab.py           # env-gated lab pattern (mirror)
├── ime_g3_matrix_support.py       # support-helper pattern (mirror)
└── test_ime_g3_matrix_support.py  # pure unit-test pattern (mirror)
tools/paste-lab/ghostty_probe.py   # the disposable-desktop recipe (reuse + HOME delta)
plan/008_a47116bb2b79/architecture/{g3_field_matrix.md,g3_gtk_rows.md}   # verdict + format precedent
# THIS ITEM ADDS:
tests/pi_g3_row_lab.py             # NEW — env-gated G3 row lab (PI_G3_ROW_LAB=1)
tests/pi_g3_row_support.py         # NEW — pure helpers (traces/payloads/verdict model/renderer)
tests/test_pi_g3_row_support.py    # NEW — pure unit tests for the helpers
plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md + pi_row_verdicts.jsonl   # NEW — evidence
```

### Desired Codebase tree with files to be added

```bash
tests/pi_g3_row_lab.py             # the lab (disposable desktop + real pi + S2 adapter + witnesses)
tests/pi_g3_row_support.py         # pure: G3Trace/VerdictRow models, payload set, bounded renderer
tests/test_pi_g3_row_support.py    # pure unit tests (always run; no desktop)
plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md   # the bounded row report (the OUTPUT)
plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl # machine-readable verdicts (matrix convention)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — pi will NOT boot under paste-lab's HOME=folder (node install + ~/.pi are
#   home-resident). DELTA: keep HOME real (read-only), isolate XDG_RUNTIME_DIR/XDG_CONFIG_HOME/
#   TMPDIR + Wayland surfaces; cwd = temp project dir with .pi/extensions/voice-editor.ts copied in.
#   Verify repo `git status` clean afterwards (R.4: no service/config/binding side effects).

# CRITICAL #2 — the socket lives at $XDG_RUNTIME_DIR/voice-typing/pi-editor.sock: export the PRIVATE
#   XDG_RUNTIME_DIR into ghostty's shell env explicitly (a server may predate the shell env — S1's
#   tmux lesson). Wait for the socket file (bounded poll) before connecting. FileNotFoundError → S2's
#   "pi socket absent"; never spin forever.

# CRITICAL #3 — isolation discipline (R.7): the lab touches ONLY the private compositor, the
#   isolated ghostty instance, the temp project cwd, and the private XDG dirs. NEVER: the live
#   desktop, real clipboard (no wl-copy/wl-paste at all on this route), default microphone, the
#   active voice-typing service, voicectl, or the operator's bindings. All xdotool/swaymsg calls
#   point at the private DISPLAY/SWAYSOCK only.

# CRITICAL #4 — every command under BOTH AGENTS.md timeouts (inner GNU timeout -k 2 N + outer
#   bash-tool timeout > N); every socket read bounded (never an unbounded makefile("r") — the
#   ctl.py canonical hang); every wait a bounded poll; the lab installs an EXIT trap that kills the
#   sway/ghostty/pi tree and removes the temp root (under /tmp = RAM — AGENTS.md Rule 3).

# CRITICAL #5 — the witness taxonomy is the row's whole point: (i) editor's own text + caret = the
#   extension's read (getText/getCursor) — NEVER pty scraping/scrollback/a fake editor; (ii) the
#   edit-count law = per-op `changes` (applied=1, unchanged=0) — no delete/retype frame pairs;
#   (iii) the VISIBLE PROMPT leg: enumerate what the landed extension actually instruments (read
#   its source). If no rendered-prompt dump exists, that leg is "not verified" — record it as such,
#   NEVER as passed. Optional supplementary screenshot (grim) is evidence, never the gate.

# CRITICAL #6 — UTF-16 units everywhere: offsets via bulk_delivery.map_span on the ORIGINAL string;
#   🫡 = 2 units; never len(); never a normalized/lowercased copy (R.3 index-desync rule).

# CRITICAL #7 — no id echo in the protocol: one request in flight; dispatch on "event" first
#   (a takeover line arriving between request and reply must never parse as the reply). S2's client
#   already enforces this — the lab just uses PiEditorClient as-is.

# CRITICAL #8 — never retry after UNKNOWN; never mutate after takeover (the takeover leg asserts
#   S2's latch fires halt_for_takeover EXACTLY once and subsequent ops are refused 'editor dirty').

# CRITICAL #9 — route assignment is DECIDED (matrix): cooperating-editor seam; terminal corrections
#   NEVER ride IM delete; do NOT re-run route discovery; do NOT attempt nested Hyprland (dead —
#   aquamarine abort). Private Sway is the compositor. The clipboard fallback is P1.M5.T3's row,
#   NOT this one — no wl-copy/wl-paste here.

# CRITICAL #10 — pi is never sent a message (no API key needed for editor+extension work; S1
#   CRITICAL #8); "no shortcut execution/submission" is asserted by: read-back shows the buffer
#   intact and uncleared, no Enter/newline ever inserted, per-op changes match exactly, and nothing
#   message-shaped leaves the editor.

# CRITICAL #11 — env-gate the lab (PI_G3_ROW_LAB=1) so `pytest tests/` fast sweeps never boot a
#   desktop; the pure support tests run always. t_ms values in evidence are mechanism-level info,
#   NEVER G5 timing claims.

# CRITICAL #12 — scope fences: do NOT modify .pi/extensions/**, voice_typing/pi_editor.py,
#   bulk_controller.py, bulk_delivery.py, daemon.py, tests/ime_*, tests/test_pi_editor.py,
#   tests/pi_seam_support.py, pyproject, .gitignore. If the landed S1/S2 code drifted from the
#   PRPs, follow the CODE and record the drift in the row report.

# CRITICAL #13 — ghostty flags are isolation flags only (--gtk-single-instance=false,
#   --shell-integration=none). Do NOT reconfigure paste safeguards (R.3: "no disabling of paste
#   safeguards") — moot on this route (no paste happens) but do not touch them anyway.
```

## Implementation Blueprint

### Data models and structure

```python
# tests/pi_g3_row_support.py — pure, no desktop imports.
@dataclass(frozen=True)
class G3Step:            # one scripted step: name, expected ShowResult, expected changes count, payload kind
    name: str; kind: str  # kind ∈ insert|correction|zero_diff|unicode|long|takeover|focus|refusal|cancel
    payload: str; expect: str  # expect ∈ applied|unchanged|refused|halt
    expect_changes: int

@dataclass(frozen=True)
class VerdictRow:        # the report row
    field_class: str; app: str; versions: dict[str, str]
    status: str          # untested|insert-only|blocked (reason)|not verified (reason)|verified
    evidence: tuple[str, ...]

def row_traces() -> list[G3Step]            # the §4 trace list (payloads reuse pi_seam_support's set)
def render_row_report(rows) -> str          # bounded ≤120 lines (matrix renderer style)
def assert_no_paste_markers(text: str)      # the folded-paste-placeholder + control-byte check
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE tests/pi_g3_row_support.py (pure helpers) + tests/test_pi_g3_row_support.py.
  - IMPLEMENT: G3Step/VerdictRow models; row_traces() (short inserts; first-word correction;
    repeated zero-diff finals; unicode 'Zoë — naïve 日本語 🫡'; ~1 KB long payload; takeover; focus;
    refusals range-not-owned/dirty; cancel-nothing-pending); render_row_report (bounded);
    assert_no_paste_markers (\x1b[200~/\x1b[201~ + control bytes/tabs/newlines).
  - REUSE payloads from tests/pi_seam_support.py's builders (do not fork a dialect).
  - TEST: pure unit tests for every helper (verdict vocabulary closed; renderer bounded; marker
    detector catches each forbidden byte).
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_pi_g3_row_support.py -q   (bash 180)

Task 2: CREATE tests/pi_g3_row_lab.py — desktop scaffold FIRST (run it once WITHOUT pi to prove
         the disposable-desktop step, pi socket absent verdict path).
  - IMPLEMENT the paste-lab recipe + the HOME delta: private root under /tmp; env dict (paste-lab
    :153-157 MINUS HOME=folder — keep real HOME; document in the report); xvfb-run -a
    dbus-run-session chain; sway spawn + SWAYSOCK/WAYLAND_DISPLAY bounded wait; EXIT trap kills
    the tree and removes the root; `timeout -k 2 240` self-wrap.
  - ADD: temp project dir with .pi/extensions/voice-editor.ts copied from the repo; spawn ghostty
    --gtk-single-instance=false --shell-integration=none running `pi` (shutil.which/PI_BIN) with
    cwd=project, XDG_RUNTIME_DIR exported; bounded wait for voice-typing/pi-editor.sock.
  - ENV-GATE: main() refuses to run unless PI_G3_ROW_LAB=1 (matrix precedent).
  - RUN (smoke): timeout -k 2 240 env PI_G3_ROW_LAB=1 .venv/bin/python tests/pi_g3_row_lab.py
    (bash 300) — expect the desktop to boot, pi to start, socket to appear, then the scaffold's
    census: exactly 1 sway window. If pi fails to boot under the real-HOME delta, STOP and record
    'blocked (pi boot: <reason>)' — that IS a legitimate verdict.

Task 3: EXTEND the lab — the G3 drive through S2's adapter.
  - IMPLEMENT: PiEditorClient + PiEditorTarget + PiEditorTakeoverWatch wiring with a duck
    controller (records halt_for_takeover calls); run row_traces(): per step, call the adapter
    method (acquire/show/finalize/cancel), assert the returned ShowResult + per-op changes count
    (read replies carry them), then read() and assert the editor's OWN text + cursor exactly
    (UTF-16 offsets via map_span for expected positions; 🫡 = 2 units).
  - TAKEOVER leg: xdotool key --delay 10 into the ghostty window mid-owned-fragment → assert the
    watch fired halt_for_takeover EXACTLY once with the fixed reason; read shows dirty=true;
    the next op is REFUSED; no further mutation attempted.
  - FOCUS leg: activate a second sway window (spawn a second ghostty or a terminal) mid-operation
    → takeover/refusal per the landed extension's semantics; window census 1→2 recorded.
  - REFUSAL legs: replace outside owned (range not owned); op while dirty (dirty); cancel with
    nothing pending (unchanged, ZERO socket requests — assert via a request-counting client wrapper).
  - CENSUS + paste-marker + submission assertions after every phase (swaymsg get_tree window set;
    assert_no_paste_markers(read text); buffer intact/no newline inserted).
  - EMIT: pi_row_verdicts.jsonl rows + the verdict (see Task 4's status rule).

Task 4: WRITE the row report plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md.
  - STATUS RULE (decide honestly, in this order):
      * pi/ghostty/desktop boot failed, or the socket never appeared → `blocked (<reason>)`.
      * All traces pass AND the visible-prompt leg is instrumented (the landed extension exposes a
        rendered-prompt dump — read its source; S1's changes counts + read are editor-internal) →
        `verified` with live versions (pi --version, ghostty --version, sway --version, kernel) +
        evidence links (verdicts.jsonl lines, report sections).
      * Traces pass but NO rendered-prompt instrumentation exists → `not verified (visibility
        instrumentation absent)` — record what IS proven (editor text/caret/edit-counts) and what
        is NOT. NEVER upgrade to verified from buffer-state alone.
      * Inserts pass but corrections fail → `insert-only (…)` (still useful; feeds P1.M5.T3).
  - BOUNDED: ≤120 lines; versions table; per-trace verdict table; the four contract assertions;
    the HOME-delta note; evidence links; "t_ms values are mechanism-level, NEVER G5 timing".

Task 5: VALIDATE — the full Validation Loop L1-L4; `git status --porcelain` = the new files only.
```

### Implementation Patterns & Key Details

```python
# The drive loop core (per G3Step) — asserts land in the SHOWRESULT vocabulary + editor truth:
def run_step(target, client, step, state):
    res = target.show(SESSION, UTTER, state.seq, state.rev, step.payload)  # or finalize/cancel per kind
    assert res.value == step.expect, (step.name, res, target.last_reason)
    if step.kind == "zero_diff":
        assert client.request_count_delta == 0        # ZERO socket requests (S2 zero-diff-first)
    reply_changes = client.last_changes               # per-op onChange count from the reply
    if step.expect == "applied":
        assert reply_changes == step.expect_changes   # 1 for insert/correction (edit-count law)
    st = read_state(client)                            # {"text","cursor","owned","dirty","units"}
    assert st["text"] == state.expected_text           # the editor's OWN text — the witness
    assert st["units"] == "utf-16"
    assert_no_paste_markers(st["text"])                # no folded-paste placeholders, no control bytes

# The disposable-desktop skeleton (paste-lab verbatim + the HOME delta):
env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "XDG_RUNTIME_DIR": str(root),   # HOME stays REAL
       "XDG_CONFIG_HOME": str(root), "TMPDIR": str(root), "GDK_BACKEND": "wayland",
       "WLR_BACKENDS": "x11", "WLR_LIBINPUT_NO_DEVICES": "1", "WLR_RENDERER": "pixman",
       "LIBGL_ALWAYS_SOFTWARE": "1", "XDG_SESSION_TYPE": "wayland", "LANG": "C.UTF-8",
       "GTK_A11Y": "none", "GIO_USE_VFS": "local"}
# xvfb-run -a dbus-run-session -- <self> run <root>  →  sway -c root/sway.conf  →  SWAYSOCK/
# WAYLAND_DISPLAY bounded waits  →  ghostty --gtk-single-instance=false --shell-integration=none \
#   -e sh -c 'export XDG_RUNTIME_DIR=<root>; cd <proj>; exec <PI_BIN>'   →  wait pi-editor.sock

# The takeover leg (REAL key into the PRIVATE display only):
sp.run(["xdotool", "key", "--delay", "10", "space"], env=lab_env, check=True, timeout=5)
wait_for(lambda: duck_controller.halts == 1, timeout=5)      # EXACTLY one halt_for_takeover
assert read_state(client)["dirty"] is True
```

### Integration Points

```yaml
CONSUMES (read-only):
  - .pi/extensions/voice-editor.ts (S1, LANDED — copied into the temp project cwd)
  - voice_typing/pi_editor.py (S2, in flight→contract): PiEditorClient/PiEditorTarget/PiEditorTakeoverWatch
  - voice_typing/bulk_delivery.py: ShowResult/AcquireResult/map_span
  - tests/pi_seam_support.py: payload builders
  - tools/paste-lab/ghostty_probe.py: the disposable-desktop recipe (+ documented HOME delta)
  - plan/008_a47116bb2b79/architecture/g3_field_matrix.md: the route decision
PRODUCES:
  - tests/{pi_g3_row_lab,pi_g3_row_support,test_pi_g3_row_support}.py
  - plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md + pi_row_verdicts.jsonl (the OUTPUT verdict)
FEEDS:
  - P1.M5.T3.S1 (clipboard fallback decision), P1.M7.T1.S1 (G6 graduation counts), P1.M6.T2 (daemon wiring confidence)
DOES NOT TOUCH:
  - S1/S2 source, controller/contracts/daemon, ime_* labs, matrix lab, pyproject, .gitignore,
    the operator's live desktop/service/config/bindings (R.4)
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 60 .venv/bin/python -c "import tests.pi_g3_row_support, tests.pi_g3_row_lab" && echo "imports clean"
ruff check tests/pi_g3_row_support.py tests/test_pi_g3_row_support.py tests/pi_g3_row_lab.py --fix && \
  ruff format tests/pi_g3_row_support.py tests/test_pi_g3_row_support.py tests/pi_g3_row_lab.py
grep -c 'PI_G3_ROW_LAB' tests/pi_g3_row_lab.py            # ≥1 (the env gate exists)
```

### Level 2: Unit Tests (pure helpers — always run)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_pi_g3_row_support.py -q        # (bash 180)
# Regression (adds-only proof):
timeout 240 .venv/bin/python -m pytest tests/test_pi_seam_support.py tests/test_pi_editor.py \
  tests/test_ime_g3_matrix_support.py -q                                          # (bash 300)
timeout 120 .venv/bin/python -m pytest tests/pi_g3_row_lab.py -q                  # (bash 180)
#   ↑ WITHOUT the env var: collects + skips the desktop work (the gate works; no boot attempt)
```

### Level 3: The lab itself (THE gate — real pi, isolated Ghostty)

```bash
timeout -k 2 240 env PI_G3_ROW_LAB=1 .venv/bin/python tests/pi_g3_row_lab.py    # (bash 300)
# Expected: the verdict line + the report path. Outcomes, ALL legitimate:
#   verified (versions + evidence)  |  insert-only (…)  |  not verified (visibility
#   instrumentation absent)  |  blocked (<reason>)  — recorded verbatim in the row report.
# After: test -f plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md; ls /tmp for leftover roots
# (must be none — the EXIT trap removed them); git status --porcelain (new files only).
```

### Level 4: Isolation & honesty audit

```bash
grep -nE 'wl-copy|wl-paste|voicectl|systemctl|RealtimeSTT|HYPR|hypr' tests/pi_g3_row_lab.py || echo "ok: no clipboard/service/hyprland"
grep -n 'map_span' tests/pi_g3_row_lab.py | head -3            # UTF-16 math routed through map_span
grep -nE 'HOME.*=.*root|HOME=folder' tests/pi_g3_row_lab.py || echo "ok: HOME preserved (the delta is documented in the report)"
awk 'END{print NR}' plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md   # ≤120 lines
grep -c 'not verified\|blocked\|verified\|insert-only' plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md  # verdict present
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 green; the lab runs under both AGENTS.md timeouts; no temp-desktop leftovers; repo clean.
- [ ] Pure helper tests green; neighboring suites (pi_seam, pi_editor, ime matrix support) green.
- [ ] The env gate works (`pytest tests/pi_g3_row_lab.py` without the var = no desktop boot).

### Feature Validation
- [ ] (a)–(f) of the Success Definition demonstrated by the lab run + the report.
- [ ] Witnesses: editor's own text+caret (read) + per-op changes counts; NO pty/scrollback/fake editor.
- [ ] The four contract assertions each positively checked (paste markers, submission, neighbors,
      visible prompt — or honestly recorded as not-verified).
- [ ] Takeover: exactly one halt; dirty asserted; refused afterwards; no post-takeover mutation.
- [ ] UTF-16 offsets via map_span; astral payload exercised.

### Code Quality Validation
- [ ] Mirrors the ime_g3 trio pattern; payloads reuse pi_seam_support (no forked dialect).
- [ ] Bounded report (≤120 lines) with versions + evidence links; t_ms framed as mechanism-level.
- [ ] Anti-patterns below avoided.

### Documentation & Deployment
- [ ] Row report at architecture/g3_pi_prompt_row.md + pi_row_verdicts.jsonl; verdict stated once.
- [ ] The HOME delta + any S1/S2 PRP-vs-code drift documented in the report.

---

## Anti-Patterns to Avoid

- ❌ Don't mark the row verified from a lab/buffer-state pass without the visible-prompt leg —
  "missing visibility instrumentation means 'not verified', not 'passed'".
- ❌ Don't witness via pty bytes, scrollback capture, tmux capture-pane, or a fake/replay editor.
- ❌ Don't touch IM delete, wl-copy/wl-paste, the clipboard, or re-run route discovery — the matrix
  DECIDED the cooperating-editor seam; the clipboard fallback is P1.M5.T3's separate row.
- ❌ Don't set HOME to the temp folder (pi won't boot) — the documented HOME-preservation delta.
- ❌ Don't run pi with an API key or send any message; don't run the real daemon/voicectl/systemctl.
- ❌ Don't use unbounded reads/waits (the ctl.py makefile hang); don't skip the EXIT-trap cleanup.
- ❌ Don't retry after UNKNOWN, mutate after takeover, or compute offsets with len()/normalized copies.
- ❌ Don't modify S1/S2/controller/contracts/daemon/ime files or the matrix lab; don't add config keys.
- ❌ Don't claim G5 timing from t_ms values; don't let plain `pytest tests/` boot a desktop.
- ❌ Don't leave evidence unbounded or write outside tests/ + plan/008…/architecture/.

---

## Confidence Score

**8/10.** Both input contracts are pinned (S1's extension is landed on disk — verified; S2's adapter
PRP specifies the exact consumption surface, and its landed code is readable at implementation
time), the disposable-desktop recipe is proven code reused verbatim with one called-out delta, and
the matrix pre-decided the route (no discovery work). The verdict taxonomy makes every outcome
deliverable — verified, insert-only, not-verified, and blocked are ALL successes of this item when
honestly recorded. Residual -2: (1) real-pi-in-isolated-Ghostty boot is first-time here (the HOME
delta + extension auto-load could surface an environment quirk — the scaffold-first Task 2 smoke
run isolates it, and a boot failure is a legitimate blocked verdict with evidence); (2) S2 is in
flight — if its landed surface drifted from the PRP, the lab follows the code and records the drift
(one small adaptation, not a redesign).

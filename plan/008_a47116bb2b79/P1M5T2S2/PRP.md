# PRP — P1.M5.T2.S2: G3 rows — graphical editor + browser text field (IM-v2 route)

## Goal

**Feature Goal**: Execute the **remaining two G3 real-field rows that G6 graduation needs**
(PRD §4.2sexies R.7 G3; G6: "verified G3 rows for … a graphical editor, and a browser text
field; … never claim 'works on Wayland' from one row") on the **landed G3 harness pattern**
(P1.M4.T5.S1) through the **REAL takeover-complete IM-v2 adapter** (`ImeProcess` +
`ImeTarget`, finalize/leave/cancel from P1.M4.T3.S3):
1. **graphical editor row** — a real **Gtk.TextView document-editor app** (the widget class
   of gedit-class editors; hand-written because no editor app is installed on this box —
   M4.T5.S1 precedent "hand-written field apps only") run on system python3 in the
   disposable desktop;
2. **browser text field row** — a **real browser text input** (Chromium 158,
   `/usr/bin/chromium`, `--ozone-platform=wayland --enable-wayland-ime
   --wayland-text-input-version=3`, isolated `--user-data-dir`) rendering a repo HTML
   fixture with a real DOM `<input>` in the SAME isolated compositor — **not a mock DOM**.

Both rows run the **same assertion set** as the harness: contents + cursor + **visible
field** (frame oracle for the editor; DOM input-event law + rAF value-hash ring for the
browser), **one-edit corrections**, **zero-diff ⇒ zero events**, **takeover revocation**
(live `grab_key` leg). Each field class is reported **honestly** from the closed vocabulary
`untested | insert-only | blocked (reason) | verified (versions + evidence links)`.

**Deliverable** (4 NEW code files + 1 fixture + report; **zero modifications** to any landed
file — `tests/ime_g3_*`, `tests/pi_g3_row_*` (S1, in flight), `voice_typing/**`,
pyproject, config.toml, .gitignore):
1. `tests/ime_g3_field_edit.py` — the Gtk.TextView graphical-editor app (system python3;
   fork lineage `tests/ime_g3_field_gtk.py`).
2. `tests/fixtures/ime_g3_browser_field.html` — the browser field page: real DOM input,
   autofocus, self-witnessing JS (HTTP-push state channel + document.title fallback).
3. `tests/ime_g3_editor_browser_support.py` — pure stdlib helpers: browser-state model +
   parser + assertions (event-count law, ring analysis), Chromium argv/env builder, editor
   row mapping, per-class verdict mapper (insert-only detection), report glue.
4. `tests/ime_g3_editor_browser_lab.py` — env-gated live lab (`IME_G3_EDITOR_BROWSER_LAB=1`)
   mirroring `tests/ime_g3_lab.py`'s two-phase boot; drives editor rows E1–E6 + browser rows
   B1–B6; emits `<root>/verdicts.jsonl`; exit 1 on any failed row.
5. `tests/test_ime_g3_editor_browser_support.py` — pure unit tests (always collected; no
   desktop).
6. `plan/008_a47116bb2b79/architecture/g3_editor_browser_rows.md` + beside it
   `editor_browser_row_verdicts.jsonl` — the **bounded row report** (the item's OUTPUT +
   DOCS contract), rendered via `ime_g3_support.render_report` (≤150 lines).

**Success Definition**:
- (a) The lab runs end-to-end under both AGENTS.md timeouts, leaves NOTHING behind (EXIT-trap
      teardown of the temp root; `git status --porcelain` shows only the new files), and
      never touches the live desktop, real clipboard/profile, default microphone, or the
      service (no `voicectl`/`systemctl`/`pactl`/`wl-copy`/`hyprctl` anywhere in new files).
- (b) Editor rows: contents byte-exact + cursor exact + cseq Δ∈(1,2) per mutating op +
      frame-oracle single-edit; identical finals ⇒ UNCHANGED ×3 with zero wire commits and
      zero field events; overcap refused; readonly refuses honestly; takeover: xdotool real
      key mid-owned-fragment → `halt_for_takeover` EXACTLY once, field counters frozen, next
      op refused.
- (c) Browser rows: same law in DOM terms — insert/correction = exactly ONE `input` event
      with the full (before→after) delta, no intermediate value-hash in the rAF ring;
      zero-diff ⇒ zero `input` events; cursor `selectionStart` exact (UTF-16 via
      `map_span`); no submission (no Enter/form submit); readonly `<input readonly>` refuses.
- (d) The report states ONE verdict per field class from the closed vocabulary with live
      versions (kernel, sway, gtk, pygobject; chromium `--version` + the exact IME flags)
      and evidence links; insert-only/blocked outcomes are recorded with the exact reason —
      **they are legitimate successes of this item when honest**. A passing assertion run
      never upgrades a class whose correction leg failed.
- (e) `timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_editor_browser_support.py -q`
      green; regression neighbors green (`tests/test_ime_g3_support.py`,
      `tests/test_ime_g3_matrix_support.py`, `tests/test_ime_takeover.py`); plain
      `pytest tests/` never boots a desktop (env gate verified).

## User Persona

**Target User**: Internal — three consumers:
1. **P1.M7.T1.S1 (G6 graduation)** — counts "a graphical editor" and "a browser text field"
   among its required verified rows; over-claiming here corrupts the graduation gate.
2. **P1.M5.T3.S1 (conditional clipboard fallback)** — the browser row's verdict decides
   whether a browser-class insert fallback is needed.
3. **The operator** — whose desktop, Chromium profile, service, config, and bindings MUST be
   untouched (R.4); the private-desktop + `--user-data-dir`-in-temp discipline is the
   guarantee.

**Use Case**: Bulk-text delivery (Rev 4) needs proof that the IM-v2 route delivers
one-edit insert/correct beyond GTK Entry fields. The GTK-class rows are done; G6 still owes
a document-editor class and a browser class. An implementer runs the lab, gets one JSON
verdict per row, and transcribes them into the bounded report.

**Pain Points Addressed**: (1) R.2's matrix measured terminals + Gtk.Entry — a browser
text-input client was NEVER measured: whether Chromium 158 activates text-input-v3 under
sway's IM-v2 relay, sends `surrounding_text`, or honors `delete_surrounding_text` is
unknown — this row is the measurement. (2) "Graphical editor" ≠ "text field": TextView is a
buffer-based IM consumer with its own preedit/surrounding path; G6 requires the class
explicitly. (3) Honesty pressure: the PRD forbids claiming "works on Wayland" from one row.

## Why

- **G6 lists exactly these classes**: "verified G3 rows for the pi prompt in Ghostty, a
  graphical editor, and a browser text field". S1 (parallel) covers the pi prompt; THIS item
  covers the other two. Without them G6 cannot graduate bulk-text to default.
- **The harness + adapter are landed and proven** (M4.T5.S1's five GTK rows ran green with
  the frame oracle; the adapter is takeover-complete). Extending the row set is a measured,
  bounded step — NOT route discovery (R.4 #2: the IM-v2 route is DECIDED for field classes
  that support it; do not re-litigate).
- **Honest rows are cheap, fabricated ones are fatal**: the verdict vocabulary makes
  insert-only and blocked deliverable outcomes that feed P1.M5.T3's decision correctly.

## What

One disposable private desktop (Xvfb seat + private D-Bus + sway x11 backend — the
`ime_g3_lab` recipe, forked not modified), one real `ImeProcess`/`ImeTarget`, two field
apps, eleven rows:

| Row | Field | Drives | Core assertions (all families from M4.T5.S1) |
|---|---|---|---|
| E1 `editor-short-updates` | TextView | 6 short inserts (`payloads["short"]`) | applied, cumulative text byte-exact, cursor at end (chars), cseq Δ∈(1,2), frame oracle = exactly 1 text transition, 0 transient frames |
| E2 `editor-firstword-20sent` | TextView | ~1.5–2 KB span then FIRST-word correction (`twenty_committed`→`twenty_corrected`) | byte-exact, ONE wire commit (delete_surrounding+commit), single visible edit, reach ≫ utterance, pre-op `recheck()` ok, verify suffix-agreement |
| E3 `editor-identical-finals` | TextView | same final span ×3 | UNCHANGED ×3, cseq Δ0, host dones unchanged — zero-diff ⇒ zero events |
| E4 `editor-long-unicode` | TextView | `unicode_951b`, `mixed_3500b`, `overcap_4500b` | (a),(b) applied byte-exact; (c) REFUSED at the 4000 B cap, field untouched |
| E5 `editor-refusing-readonly` | TextView `--readonly` | ops against a non-editable view | no visible edit under any branch; actual branch recorded; fresh writable view then takes one insert |
| E6 `editor-takeover` | TextView | real key via xdotool mid-owned-fragment | `grab_key` event → takeover detector `halt_for_takeover` exactly once; next op refused; field `keys`/`cseq` frozen (grab consumed the key) |
| B1 `browser-short-updates` | Chromium input | 6 short inserts | applied, `value` byte-exact, `selectionStart` exact (UTF-16), exactly 1 `input` event per op, no intermediate rAF value-hashes |
| B2 `browser-firstword-20sent` | Chromium input | 20-sentence span + first-word correction | ONE `input` event with the full before→after delta (one-edit law), cursor exact, no transient states |
| B3 `browser-identical-finals` | Chromium input | same final span ×3 | UNCHANGED ×3, ZERO `input` events, value hash unchanged |
| B4 `browser-long-unicode` | Chromium input | unicode_951b / mixed_3500b / overcap_4500b | applied byte-exact / applied / REFUSED at cap with field untouched |
| B5+B6 | Chromium | `<input readonly>` refusing row + takeover leg | same as E5/E6 in DOM terms (`input` events 0; keydown counter frozen while grabbed) |

**Contingency (strictly bounded)**: if Chromium never activates text-input (row blocked at
acquire/activation), ONE Firefox sub-row may be attempted (`MOZ_ENABLE_WAYLAND=1`, same
fixture, title-channel witness) before declaring the browser class blocked; otherwise
Firefox records `untested (not attempted — one browser class is the row's scope)`.

### Success Criteria

- [ ] (a)–(e) of the Success Definition, per the Validation Loop.
- [ ] Every browser assertion comes from the page's OWN JS state pushes (the DOM's truth) —
      never a pixel scrape alone; every editor assertion from the app's own atomic dump —
      never pty/scrollback. Supplementary `lab.shot()` screenshots are evidence, never the
      gate.
- [ ] Expected cursor offsets computed ONLY via `bulk_delivery.map_span` (chars for GTK,
      UTF-16 for the DOM); astral payload exercised (🫡-class, 2 UTF-16 units).
- [ ] The report is bounded (≤150 lines via `render_report`), carries live versions + flags,
      and states exactly one class verdict each for `graphical-editor` and
      `browser-text-field` in the closed vocabulary.
- [ ] `git status --porcelain` shows only the new files (+ this plan/ dir).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer gets: the harness boot recipe + Lab/field/adapter APIs (file:line),
the exact new-file responsibilities, the Chromium flag set with upstream URLs, the
browser-witness channel design (HTTP push + title fallback, CORS rationale), the row matrix
with expected adapter results, the verdict rules, and every isolation/timeout gotcha. No
unverified assumption is load-bearing: the one genuine unknown (Chromium's IM-v2 behavior)
is the thing the row MEASURES, with insert-only/blocked as honest outcomes.

### Documentation & References

```yaml
# MUST READ — this item's own research (verified this session at HEAD de20669).
- docfile: plan/008_a47116bb2b79/P1M5T2S2/research/editor_browser_rows_research.md
  why: "§2 harness digest (boot pseudocode, Lab class, dump schema, adapter API with
        timeouts/caps, R1–R5 structure, verify-suffix rule). §3 app inventory (chromium
        158.0.8127.36, firefox 160.0.1, NO editor apps → hand-written TextView precedent).
        §4 design decisions (TextView fork; Chromium flags; HTTP-push witness; UTF-16 rule;
        insert-only contingency). §5 URLs. §6 gotchas (seat singleton, sway≠DOM focus,
        tmpfs caps, adds-only fences)."

# MUST READ — the harness being extended (READ-ONLY; fork, never edit).
- file: tests/ime_g3_lab.py
  why: "The two-phase boot, Lab class (spawn/cmd/focus/verdict/shot/teardown/until),
        spawn_field (system python3 + ready-flag poll), start_adapter (ImeProcess spawn +
        'globals' readiness), _verify_agrees (surrounding_text ~4 KiB window → suffix
        agreement), the R1–R5 row skeletons to mirror, verdicts.jsonl emission."
  gotcha: "Env gate GATE_ENV='IME_G3_LAB' + docstring run line + exit-code contract
           (0/1/2) — replicate for the new gate."
- file: tests/ime_g3_field_gtk.py
  why: "The field-app to fork into the TextView editor: atomic dump (field*.tmp + replace),
        ready flag, RING_MAX/RLE_CAP ring, add_tick_callback frame oracle, keys/activated
        counters, --readonly/--tag, GTK version in dump."
  pattern: "Replace Gtk.Entry with Gtk.TextView in ScrolledWindow; buffer 'changed' = cseq;
            cursor = get_iter_at_mark(get_insert()).get_offset(); 'activated' becomes the
            Enter-press counter (EventControllerKey), still must stay 0."
- file: tests/ime_g3_support.py
  why: "REUSE, do not fork: build_payloads() (short/twenty_committed/twenty_corrected/
        unicode_951b/mixed_3500b/overcap_4500b), single_edit_analysis(), text_hash8(),
        ROW_STATUSES/row_status(), render_report() (≤150 lines)."
  gotcha: "overcap_4500b contains \\n and is REFUSED pre-wire — never applied to any field."
- file: tests/test_ime_g3_support.py
  why: "The pure-unit-test pattern to mirror for the new support module."

# MUST READ — the adapter being driven (READ-ONLY).
- file: voice_typing/ime/target.py
  why: "ImeTarget(proc): acquire()→AcquireResult; recheck(binding, inserted_bytes=0)→
        (bool,str,int); show(session,utterance,seq,expected_revision,span)→ShowResult
        (render-equal→UNCHANGED zero events; >4000 B→REFUSED never chunked; correction
        verifies _owned_region_intact BEFORE the wire); finalize(); leave(); cancel().
        _ACQUIRE_TIMEOUT_S=2.5, _SHOW_TIMEOUT_S=0.25."
- file: voice_typing/ime/manager.py
  why: "ImeProcess(log_path, on_event).spawn(timeout=15); request(cmd, timeout, **fields);
        healthy(); stop(). ONE per seat (input-method singleton)."
- file: voice_typing/ime/ime_host.py
  why: "Host 'grab' command → zwp_input_method_keyboard_grab_v2; grabbed keys arrive as
        grab_key events and are NOT forwarded to the app — the takeover leg's evidence.
        EventLogWriter caps the log at 64 KiB; 'ping'→{activated,dones}."
- file: voice_typing/ime/takeover.py
  why: "The daemon-side takeover detector (T4) the lab ducks: feed it the collected grab_key
        events; assert halt_for_takeover fires EXACTLY once and post-takeover ops are
        refused. Mirror the consumption pattern in tests/test_ime_takeover.py."
- file: voice_typing/bulk_delivery.py
  why: "ShowResult values; TargetUnits enum; map_span(text, start_char, end_char, units) —
        the ONLY offset math (chars for GTK, UTF-16 for DOM); rendered_equal."

# MUST READ — the report/verdict conventions + the matrix (READ-ONLY).
- file: plan/008_a47116bb2b79/architecture/g3_gtk_rows.md
  why: "The row-report format the new g3_editor_browser_rows.md must match: header with
        command + live versions, the R.7 quote, the 'A G2 pass never marks a row verified'
        banner, the row table, per-row evidence sections."
- file: plan/008_a47116bb2b79/architecture/g3_field_matrix.md
  why: "The class matrix (gtk full; foot/kitty insert-only; ghostty blocked; Hyprland relay
        blocked — never attempt nested Hyprland). The new report ADDS editor/browser rows;
        it does not edit this file."

# MUST READ — the parallel sibling's PRP (in flight; avoid overlap).
- file: plan/008_a47116bb2b79/P1M5T2S1/PRP.md
  why: "S1 produces tests/pi_g3_row_{lab,support}.py + test_pi_g3_row_support.py +
        architecture/g3_pi_prompt_row.md (pi-prompt row via the cooperating-editor seam).
        ZERO file overlap with this item; do not read/write its outputs beyond this fence."

# PRD ground truth.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.7 G3 (the trace list; 'Rows report untested|insert-only|blocked|
        verified'; 'A G2 pass never marks a row verified'; isolation: private compositor +
        synthetic input + isolated app instances; evidence bounded) and G6 (the three
        required rows; 'never claim works on Wayland from one row'). R.2 (field-class
        matrix — browser absent = unmeasured; sway 1.12 advertises text-input-v3 +
        input-method-v2). R.3/R.4 (route DECIDED; never fall back to typing; blocked row is
        legitimate)."

# External — the browser row's flag set (verify at runtime; record versions).
- url: https://issues.chromium.org/40113488
  why: "Chromium ozone-wayland text_input_v3 support tracker — the protocol implementation
        this row exercises through sway's IM-v2 relay."
- url: https://github.com/brave/brave-browser/issues/45183
  why: "Field evidence that IME on ozone/wayland (135+) requires the text-input-v3 flag —
        hence --wayland-text-input-version=3 alongside --enable-wayland-ime."
- url: https://discourse.nixos.org/t/ibus-not-working-with-electron-apps/64128
  why: "The exact working flag combo in the wild: --ozone-platform=wayland
        --enable-wayland-ime --wayland-text-input-version=3."
```

### Current Codebase tree (relevant slice — state at P1.M5.T2.S2)

```bash
tests/
├── ime_g3_lab.py               # the G3 harness (M4.T5.S1) — READ-ONLY, fork its pattern
├── ime_g3_field_gtk.py         # Gtk.Entry field app — fork lineage for the editor
├── ime_g3_support.py           # payloads/oracle/status/render — REUSE via import
├── test_ime_g3_support.py      # pure tests — pattern to mirror
├── test_ime_takeover.py        # takeover-detector consumption pattern
├── fixtures/                   # input-method-unstable-v2.xml lives here
├── pi_g3_row_lab.py            # S1 (in flight) — DO NOT TOUCH
voice_typing/ime/{target,manager,ime_host,protocol,takeover}.py   # adapter — READ-ONLY
voice_typing/bulk_delivery.py                                   # ShowResult/map_span — READ-ONLY
plan/008_a47116bb2b79/architecture/{g3_gtk_rows,g3_field_matrix}.md   # report conventions
# S1 also adds (in flight): tests/pi_g3_row_support.py, tests/test_pi_g3_row_support.py,
#   architecture/g3_pi_prompt_row.md — no overlap with this item's files.
```

### Desired Codebase tree with files to be added

```bash
tests/
├── ime_g3_field_edit.py                  # Gtk.TextView graphical-editor app (system python3)
├── fixtures/ime_g3_browser_field.html    # real-DOM browser field page (self-witnessing)
├── ime_g3_editor_browser_support.py      # pure helpers (state model, argv builder, verdicts)
├── ime_g3_editor_browser_lab.py          # env-gated lab: E1–E6 + B1–B6 → verdicts.jsonl
└── test_ime_g3_editor_browser_support.py # pure unit tests (no desktop)
plan/008_a47116bb2b79/architecture/
├── g3_editor_browser_rows.md             # the bounded row report (the OUTPUT)
└── editor_browser_row_verdicts.jsonl     # machine-readable verdicts (matrix convention)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TWO timeouts on every non-trivial command (AGENTS.md): inner GNU timeout
#   (`timeout -k 2 420 env IME_G3_EDITOR_BROWSER_LAB=1 .venv/bin/python tests/
#   ime_g3_editor_browser_lab.py`) + bash-tool timeout 480+. Every wait is a bounded
#   `until()` poll; every subprocess call carries timeout=. No voicectl/systemctl/pactl
#   ANYWHERE (isolation, not just safety).

# CRITICAL #2 — the GTK editor app runs on SYSTEM python3 (the venv has no `gi`); the
#   adapter (ImeProcess) runs venv python with cwd=repo root (PYTHONPATH inherited from
#   start_desktop). They share ONLY the private seat.

# CRITICAL #3 — ONE ImeProcess per seat (input-method singleton: "another input method
#   holds the seat"). Rows share it; leave() between rows; re-acquire per field/row.

# CRITICAL #4 — sway focus ≠ DOM focus for Chromium: the fixture AUTOFOCUSES the input
#   (page JS focus() + autofocus attr) — DOM editable focus is what drives text-input
#   enable. The lab still `swaymsg -r <criteria> focus`es the window before acquire.

# CRITICAL #5 — Chromium isolation: --user-data-dir=<root>/chromium-profile (NEVER the
#   real profile), --no-first-run --no-default-browser-check --disable-gpu (pixman sway),
#   --password-store=basic (no keyring D-Bus hang). Record chromium --version + flags in
#   the report. If the sandbox fails under the seat, --no-sandbox is an allowed fallback
#   ONLY inside the disposable desktop, recorded in the report.

# CRITICAL #6 — the browser witness channel: page JS POSTs state as text/plain (simple
#   request, NO CORS preflight) to http://127.0.0.1:<ephemeral>/push; handler replies 204
#   with Access-Control-Allow-Origin: * (file:// origin = null — this works). Caps: push
#   payload ≤8 KiB (full text fits: max applied payload is 3500 B), server keeps ≤256
#   pushes. Fallback if fetch is blocked: document.title (counts+hashes, ~200 chars) read
#   via `swaymsg -r -t get_tree` (page sets it on every state change). The push channel is
#   the PRIMARY witness; title is the fallback — record which was used.

# CRITICAL #7 — units: DOM cursor/length are UTF-16 code units (🫡 = 2); GTK TextView pos
#   is chars; adapter verify is bytes. ALL expected offsets via bulk_delivery.map_span;
#   never len() on a normalized/lowercased copy (R.3 index-desync rule).

# CRITICAL #8 — grabbed keys never reach the app (ime_host grab semantics): during the
#   takeover leg the field's keys/keydown counters must NOT move — the grab consumed the
#   key; the host's grab_key EVENT is the takeover evidence. Delivery cannot self-trigger
#   takeover (assert zero grab_key events across all non-takeover rows — M4.T5.S1
#   invariant).

# CRITICAL #9 — GTK caps surrounding_text near the cursor (~3999 B measured): verify
#   agreement on long fields is asserted as byte-exact SUFFIX (copy _verify_agrees' rule
#   into the new lab with lineage comment; do NOT import from ime_g3_lab).

# CRITICAL #10 — bounded scratch (AGENTS.md Rule 3: /tmp is RAM): ONE TemporaryDirectory
#   root; field dump cap 2000; host log 64 KiB; push ring caps; EXIT trap killpg's the
#   spawned session groups and removes the root. Verify teardown ran (no /tmp leftovers).

# CRITICAL #11 — env-gate the lab (IME_G3_EDITOR_BROWSER_LAB=1); plain `pytest tests/`
#   collects only the pure support tests. t_ms values are mechanism-level info, NEVER G5
#   timing claims.

# CRITICAL #12 — adds-only fences: do NOT modify tests/ime_g3_{lab,field_gtk,support}.py,
#   tests/ime_g3_matrix_*, tests/pi_g3_row_* (S1 in flight), voice_typing/**, pyproject,
#   .gitignore, config.toml, the matrix/gtk-rows reports. If landed code drifted from any
#   PRP, follow the CODE and record the drift in the row report.

# CRITICAL #13 — never claim the class verified without BOTH insert and correction passing
#   on that class's own witnesses; never let a screenshot substitute for the app-side
#   witness; a browser row that never activates text-input is `blocked (<reason>)`, one
#   that inserts but cannot correct/verify is `insert-only (<reason>)`.
```

## Implementation Blueprint

### Data models and structure

```python
# tests/ime_g3_editor_browser_support.py — pure stdlib, no desktop imports.
@dataclass(frozen=True)
class BrowserState:          # one pushed/reported page state
    n: int; k: int           # input-event count, keydown count (monotonic)
    sel_start: int; sel_end: int; length: int; text: str
    ring: tuple[tuple[str, str, int, int], ...]   # last (beforeHash, afterHash, lenBefore, lenAfter)
    frames: tuple[str, ...]                       # last rAF value-hashes
    f: int                    # frame counter

def parse_push(raw: bytes) -> BrowserState                     # + validation
def input_event_law(before: BrowserState, after: BrowserState, *,
                    expect: str, exp_text: str) -> dict        # applied=Δn 1 & full delta in ONE ring
                                                               # entry & no intermediate frame hash;
                                                               # unchanged=Δn 0 & hash equal
def chromium_argv(profile_dir: Path, url: str, *, extra: tuple = ()) -> list[str]
def class_verdict(rows: list[dict]) -> str                     # closed-vocabulary mapper:
                                                               # correction+insert+zero-diff pass → verified;
                                                               # inserts pass, correction fail → insert-only;
                                                               # activation/boot fail → blocked; else untested
def render_class_report(versions, rows, meta) -> str           # wraps ime_g3_support.render_report
```

```javascript
// tests/fixtures/ime_g3_browser_field.html — the page's own truth (verbatim design):
// <input id="field" autofocus> (B5 variant: readonly attribute, selected by ?mode=ro)
// const S = {n:0,k:0,ring:[],frames:[],f:0};
// input    → S.n++, ring.push([hash(v0), hash(v1), v0.length, v1.length]) (cap 32)
// keydown  → S.k++ (counter only)
// rAF loop → frames.push(hash(value)) (cap 64), S.f++
// push()   → fetch('/push',{method:'POST',headers:{'Content-Type':'text/plain'},
//             body: JSON.stringify({n,k,sel:[s,e],len,text:value,ring,frames,f})}).catch(…)
//            on input/selectionchange + 200 ms heartbeat; document.title = compact fallback
//            ("vtg3-browser|" + JSON of counts+hashes only)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE tests/ime_g3_editor_browser_support.py + tests/test_ime_g3_editor_browser_support.py
  - IMPLEMENT: BrowserState/parse_push/input_event_law/chromium_argv/class_verdict/
    render_class_report per the models above; import payloads+ROW_STATUSES+render_report
    from ime_g3_support (sys.path trick copied from ime_g3_lab: parents[1] insert).
  - input_event_law encodes the event-count law in DOM terms: insert=1, correction=1
    (single ring entry covering the full delta), zero-diff=0 AND no text change.
  - class_verdict: pure mapping, unit-tested for every branch (verified / insert-only /
    blocked / untested) BEFORE any desktop exists.
  - TEST: parse_push round-trips the fixture's JSON incl. astral chars (🫡 → len 2 in
    UTF-16, hash stable); law catches a 2-event correction, a 1-event-with-intermediate-
    frame correction, a zero-diff that emitted an event (all must FAIL the law).
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_editor_browser_support.py -q
    (bash 180)

Task 2: CREATE tests/ime_g3_field_edit.py (the graphical editor app) — runs on SYSTEM python3.
  - FORK pattern: tests/ime_g3_field_gtk.py verbatim structure (atomic dump field*.tmp+
    os.replace, ready flag via GLib.idle_add, 2000-dump cap, RING_MAX=256/RLE_CAP=64,
    add_tick_callback frame oracle, --readonly/--tag, versions in dump).
  - REPLACE: Gtk.Entry → Gtk.TextView inside Gtk.ScrolledWindow; cseq = buffer "changed";
    pos = buffer.get_iter_at_mark(buffer.get_insert()).get_offset() (chars); 'activated' =
    Enter-press counter via EventControllerKey (must stay 0 — no submission); 'keys' =
    non-Enter key counter (must stay 0 — IM commits generate zero key events); --readonly →
    set_editable(False) + set_cursor_visible(False); window title "vtg3-editor" (+
    "-ro"/"-<tag>" suffixes); app id "org.vtg3.editor".
  - VERIFY locally (no compositor): `timeout 20 python3 -c "import ast,sys;
    ast.parse(open('tests/ime_g3_field_edit.py').read())"`.
  - RUN: smoke inside the Task-3 desktop scaffold (below).

Task 3: CREATE tests/ime_g3_editor_browser_lab.py — scaffold FIRST (desktop + editor app +
         NO browser yet; editor rows green before browser work begins).
  - MIRROR tests/ime_g3_lab.py's two-phase boot exactly: gate IME_G3_EDITOR_BROWSER_LAB=1
    (exit 2 on misuse); outer re-exec under xvfb-run -a + dbus-run-session --config-file=
    <private>; ONE TemporaryDirectory root (prefix "ime-g3-eb-lab-") = HOME/XDG_RUNTIME_DIR/
    TMPDIR; start_desktop() sway.conf + sway-ipc poll; Lab class (spawn/cmd/focus/verdict/
    shot/teardown/until) — copy, do not import from ime_g3_lab.
  - EDITOR ROWS E1–E5: spawn_field_edit() (system python3, ready-flag poll), start_adapter()
    (ImeProcess + "globals" readiness), then the row skeletons mirrored from ime_g3_lab's
    R1–R5 with payloads from build_payloads(); assertions: byte-exact text, cursor (chars),
    cseq Δ∈(1,2) mutating / Δ0 no-op, single_edit_analysis oracle, zero-diff zero-events,
    overcap refused, readonly honest branch + recovery insert; a LOCAL _verify_agrees copy
    (suffix rule, lineage comment); verdicts.jsonl per row.
  - E6 TAKEOVER: acquire + one owned insert → proc.request("grab") if the adapter does not
    already hold it (read target.py; mirror its grab lifecycle) → `xdotool key --delay 10
    space` into the editor window (private DISPLAY only) → feed the collected grab_key
    events into voice_typing/ime/takeover.py's detector (duck controller records
    halt_for_takeover calls) → assert EXACTLY one halt, next show refused/dirty, field
    counters frozen; global invariant: zero grab_key events in every other row.
  - RUN (smoke): timeout -k 2 420 env IME_G3_EDITOR_BROWSER_LAB=1 .venv/bin/python
    tests/ime_g3_editor_browser_lab.py   (bash 480) — editor class verdict printed.

Task 4: EXTEND the lab — the browser rows B1–B6.
  - START the push server: threading http.server on 127.0.0.1:0 (ephemeral) in the lab
    process; POST /push → 204 + ACAO:*; bounded store (≤256 pushes ×8 KiB).
  - SPAWN chromium: chromium_argv(profile_dir=root/"chromium-profile",
    url=f"file://{REPO}/tests/fixtures/ime_g3_browser_field.html?push=http://127.0.0.1:
    {port}/push") + the Task-CRITICAL#5 isolation flags; env = lab seat env; readiness =
    first push received (≤30 s poll — cold Chromium is slow) + sway window present (title
    "vtg3-browser…"); record chromium --version + app_id from get_tree.
  - B1–B4: drive ImeTarget against the DOM field exactly as the editor rows; witness via
    BrowserState (parse_push): text byte-exact, selectionStart via map_span UTF-16,
    input_event_law per op (insert=1/correction=1/zero-diff=0), overcap refused (field
    untouched: Δn=0), verify-agrees on whatever surrounding_text Chromium actually returns
    (record the byte count honestly — possibly absent → that fact goes in the verdict).
  - B5 readonly: reload a second window/tab with ?mode=ro (<input readonly>) → same honest
    refusing-branch recording + recovery insert on the writable window.
  - B6 takeover: same leg as E6 against the browser window; additionally assert the page's
    keydown counter did NOT move (grab consumed the key).
  - CONTINGENCY: if acquire never activates (wait_activated fails) → ONE bounded Firefox
    sub-row (MOZ_ENABLE_WAYLAND=1, same fixture, title-channel witness) → else record
    Firefox "untested (not attempted)".
  - RUN: full lab; both class verdicts + report emitted.

Task 5: WRITE the report plan/008_a47116bb2b79/architecture/g3_editor_browser_rows.md +
         editor_browser_row_verdicts.jsonl.
  - RENDER via render_class_report (ime_g3_support.render_report): header (date, HEAD,
    command, gate), live versions (kernel, sway, gtk, pygobject, chromium + flags, firefox
    if attempted), the R.7 G3 quote + "A G2 pass never marks a row verified" banner, the
    row table (row | pass | status), per-row evidence sections (capped), the two CLASS
    verdicts: `graphical-editor` and `browser-text-field`, each one closed-vocabulary
    string with versions + evidence links; insert-only/blocked rows carry the exact reason
    (e.g. "correction refused: owned region not intact — surrounding_text absent at
    chromium 158.0.8127.36"); the contingency note; t_ms framed as mechanism-level, never
    G5. BOUNDED ≤150 lines (renderer-enforced).
```

### Implementation Patterns & Key Details

```python
# The per-op browser assertion core (the event-count law on a real DOM):
def assert_browser_op(states_before, states_after, expect, exp_text):
    law = input_event_law(states_before, states_after, expect=expect, exp_text=exp_text)
    assert law["ok"], law                    # Δn, ring delta, frame-hash intermediates
    got = states_after.text
    assert got == exp_text                   # byte-exact DOM value — the field's own truth
    exp_caret = map_span(exp_text, len_char, len_char, TargetUnits.UTF16)[-1]  # at end

# The Chromium spawn (isolation flags are the contract):
argv = [CHROMIUM, "--ozone-platform=wayland", "--enable-wayland-ime",
        "--wayland-text-input-version=3", f"--user-data-dir={root}/chromium-profile",
        "--no-first-run", "--no-default-browser-check", "--disable-gpu",
        "--password-store=basic", f"--app={url}"]      # app mode: one clean window

# The takeover leg (REAL key into the PRIVATE display only):
lab.cmd(["xdotool", "key", "--delay", "10", "space"], timeout=5)
until(lambda: duck.halts == 1, 5)            # EXACTLY one halt_for_takeover
assert collector.count("grab_key") >= 1 and field_keys_frozen()
```

### Integration Points

```yaml
CONSUMES (read-only):
  - tests/ime_g3_lab.py + ime_g3_field_gtk.py + ime_g3_support.py  (patterns + payloads)
  - voice_typing/ime/{manager,target,ime_host,takeover}.py          (the adapter + detector)
  - voice_typing/bulk_delivery.py                                   (ShowResult/map_span)
  - plan/008_a47116bb2b79/architecture/{g3_gtk_rows,g3_field_matrix}.md (conventions)
  - /usr/bin/chromium (158.0.8127.36)                               (the browser field class)
PRODUCES:
  - tests/{ime_g3_field_edit,ime_g3_editor_browser_support,ime_g3_editor_browser_lab,
    test_ime_g3_editor_browser_support}.py + tests/fixtures/ime_g3_browser_field.html
  - plan/008_a47116bb2b79/architecture/g3_editor_browser_rows.md + editor_browser_row_verdicts.jsonl
FEEDS:
  - P1.M7.T1.S1 (G6 graduation counts the graphical-editor + browser-text-field rows)
  - P1.M5.T3.S1 (clipboard fallback decision — a browser insert-only/blocked verdict raises
    its priority; a verified row may let it record a skip)
DOES NOT TOUCH:
  - any landed test/adapter/daemon file, S1's in-flight files, pyproject, config.toml,
    .gitignore, the operator's live desktop/Chromium profile/service/bindings (R.4)
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 60 .venv/bin/python -c "import ast; [ast.parse(open(f).read()) for f in \
  ['tests/ime_g3_field_edit.py','tests/ime_g3_editor_browser_support.py',\
   'tests/ime_g3_editor_browser_lab.py','tests/test_ime_g3_editor_browser_support.py']]" && echo ok
timeout 60 .venv/bin/python -c "import sys; sys.path.insert(0,'tests'); \
  import ime_g3_editor_browser_support" && echo "support imports clean (venv)"
timeout 20 python3 -c "import ast; ast.parse(open('tests/ime_g3_field_edit.py').read())" && echo ok
ruff check tests/ime_g3_editor_browser_support.py tests/ime_g3_editor_browser_lab.py \
  tests/test_ime_g3_editor_browser_support.py tests/ime_g3_field_edit.py --fix && \
  ruff format tests/ime_g3_editor_browser_support.py tests/ime_g3_editor_browser_lab.py \
  tests/test_ime_g3_editor_browser_support.py tests/ime_g3_field_edit.py
grep -c 'IME_G3_EDITOR_BROWSER_LAB' tests/ime_g3_editor_browser_lab.py   # ≥1 (gate exists)
```

### Level 2: Unit Tests (pure helpers — always run)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_editor_browser_support.py -q   # (bash 180)
# Adds-only regression proof:
timeout 240 .venv/bin/python -m pytest tests/test_ime_g3_support.py \
  tests/test_ime_g3_matrix_support.py tests/test_ime_takeover.py -q                    # (bash 300)
timeout 120 .venv/bin/python -m pytest tests/ime_g3_editor_browser_lab.py -q           # (bash 180)
#   ↑ WITHOUT the env var: collects + skips (the gate works; no desktop boot)
```

### Level 3: The lab itself (THE gate — real fields, isolated compositor)

```bash
# Editor class first (scaffold milestone), then both classes:
timeout -k 2 420 env IME_G3_EDITOR_BROWSER_LAB=1 .venv/bin/python \
  tests/ime_g3_editor_browser_lab.py                                                  # (bash 480)
# Expected: per-row JSON verdicts + two class verdicts. ALL outcomes legitimate when honest:
#   verified (versions + evidence) | insert-only (<reason>) | blocked (<reason>) |
#   untested (firefox not attempted) — recorded verbatim in the row report.
# After: test -f plan/008_a47116bb2b79/architecture/g3_editor_browser_rows.md
#        ls /tmp | grep ime-g3-eb-lab   → nothing (EXIT trap removed the root)
#        git status --porcelain         → the new files only
```

### Level 4: Isolation & honesty audit

```bash
grep -nE 'wl-copy|wl-paste|voicectl|systemctl|pactl|hyprctl|HYPR' \
  tests/ime_g3_editor_browser_lab.py tests/ime_g3_field_edit.py \
  tests/ime_g3_editor_browser_support.py tests/fixtures/ime_g3_browser_field.html \
  || echo "ok: no clipboard/service/hyprland"
grep -n 'user-data-dir' tests/ime_g3_editor_browser_support.py tests/ime_g3_editor_browser_lab.py \
  | head -3    # profile is inside the temp root
grep -n 'map_span' tests/ime_g3_editor_browser_lab.py tests/ime_g3_editor_browser_support.py | head -3
awk 'END{print NR}' plan/008_a47116bb2b79/architecture/g3_editor_browser_rows.md   # ≤150
grep -c 'verified\|insert-only\|blocked\|untested' \
  plan/008_a47116bb2b79/architecture/g3_editor_browser_rows.md                    # verdicts present
grep -n 'HOME' tests/ime_g3_editor_browser_lab.py | head -3   # disposable HOME (unlike S1's
                                                              # real-HOME delta — no pi here)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 green; the lab runs under both AGENTS.md timeouts; no /tmp leftovers; repo adds-only.
- [ ] Pure helper tests green; neighbor suites (ime_g3_support, ime matrix, takeover) green.
- [ ] The env gate works (no-var pytest run = no desktop boot).

### Feature Validation
- [ ] (a)–(e) of the Success Definition demonstrated by the lab run + the report.
- [ ] Editor witnesses: the TextView app's own atomic dump + frame oracle + cseq/keys/enter
      counters. Browser witnesses: the page's own JS state pushes (or documented title
      fallback). No pixel-only or pty-based assertion anywhere.
- [ ] Event-count law held per op (editor: cseq/oracle; browser: input-event law) or the
      deviation is a recorded honest failure.
- [ ] Takeover legs: exactly one halt each; counters frozen; post-takeover ops refused.
- [ ] Offsets via map_span (chars / UTF-16); astral payload exercised.

### Code Quality Validation
- [ ] Mirrors the ime_g3 trio pattern; payloads/statuses reused from ime_g3_support (no
      forked dialect); chromium argv centralized in the support module (unit-tested).
- [ ] Report bounded with versions + evidence links; t_ms framed as mechanism-level only.
- [ ] Anti-patterns below avoided.

### Documentation & Deployment
- [ ] Row report + jsonl at the exact paths; one class verdict each, closed vocabulary.
- [ ] Any PRP-vs-code drift and any contingency branch (Firefox, --no-sandbox) recorded.

## Anti-Patterns to Avoid

- ❌ Don't mark a class verified from inserts alone, from a mechanism-level probe, or from a
  screenshot — "a G2 pass never marks a row verified"; corrections + zero-diff + takeover
  must pass on the class's own witnesses, else insert-only/blocked with the reason.
- ❌ Don't fake the browser row with a mock DOM, a headless shell without the compositor, or
  CDP text injection — the contract is a REAL browser input in the isolated compositor,
  delivered through the IM-v2 adapter.
- ❌ Don't touch the real Chromium profile (user-data-dir MUST be in the temp root), the
  live desktop, the clipboard, or the service; don't re-run route discovery; don't attempt
  nested Hyprland (dead per the matrix).
- ❌ Don't modify landed harness/adapter/S1 files; don't import cross-lab internals from
  ime_g3_lab (copy the small helpers with lineage comments).
- ❌ Don't use unbounded waits/reads; don't skip the EXIT-trap teardown; don't leave
  unbounded scratch under /tmp (tmpfs = RAM).
- ❌ Don't compute offsets with len()/normalized copies; don't conflate chars/UTF-16/bytes.
- ❌ Don't claim G5 timing from t_ms; don't let plain `pytest tests/` boot a desktop.
- ❌ Don't spawn a second ImeProcess on the same seat; don't mutate after takeover; don't
  retry ops that may have landed (UNKNOWN is terminal).
- ❌ Don't over-report: an absent surrounding_text, a refused correction, or a failed
  activation is DATA — write it down, don't paper over it.

## Confidence Score

**8/10.** The harness pattern, adapter API, payloads, oracle, and report conventions are all
landed code read this session (fork-and-extend, no new infrastructure); the editor row is a
low-risk fork of a proven app; the flag set for Chromium IME is externally corroborated and
the isolation flags are standard. Residual -2: (1) Chromium 158's text-input-v3 behavior
under sway's IM-v2 relay is genuinely unmeasured — activation, surrounding_text, and
delete_surrounding handling may each fail; the PRP turns every such failure into a recorded,
useful verdict (insert-only/blocked) rather than a crash, and the Firefox contingency is
strictly bounded. (2) First-run environment risk (cold-boot slowness, sandbox-under-seat,
fetch-from-file CORS) is mitigated by bounded polls, the title fallback channel, and the
documented --no-sandbox-in-disposable-desktop escape hatch.

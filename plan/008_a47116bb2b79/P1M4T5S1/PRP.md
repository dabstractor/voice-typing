# PRP — P1.M4.T5.S1: G3 harness + GTK field rows (insert AND correct, visible)

## Goal

**Feature Goal**: Productize the im-lab disposable-desktop pattern into the repo's **G3 real-field
harness** and run the **GTK-class row set** through the **REAL takeover-complete IM-v2 adapter**
(`voice_typing/ime/`, landed by P1.M4.T1–T4), with **frame-level single-edit instrumentation** so
"one visible edit" is asserted against what the field PAINTS — not just signal counts. This is the
first G3 evidence (PRD §4.2sexies R.7, third bullet): "real-field matrix … Assert editor contents +
cursor + the visible prompt; no transient delete/retype frames". **A G2 pass never marks a row
verified** — only this harness's field-side witnesses can.

**Deliverable** (5 NEW files; zero modifications to `voice_typing/` or existing tests):
1. `tests/ime_g3_support.py` — pure, venv-importable logic: row-status vocabulary + mapping,
   payload builders (20-sentence corpus, 951 B Unicode sample, ~3.5 KB mixed, >4 KB over-cap),
   the frame-oracle, the bounded report renderer.
2. `tests/ime_g3_field_gtk.py` — the G3 GTK4 field app (lineage: `tools/im-lab/field_gtk.py`),
   run on **system python3** (PyGObject lives there — d2 map §6), adding: frame-clock ring with
   run-length-encoded dumps, Enter (`activate`) counter, received-key counter, `--readonly`
   refusing mode, GTK version in the ready payload.
3. `tests/ime_g3_lab.py` — env-gated live runner (`IME_G3_LAB=1`), one private-desktop boot,
   rows R1–R5, per-row JSON verdicts, summary line, exit 1 on any `pass: false`.
4. `tests/test_ime_g3_support.py` — collected, compositor-free unit tests for (1).
5. `plan/008_a47116bb2b79/architecture/g3_gtk_rows.md` — the **bounded row-report file** (DOCS
   contract): live versions, per-row status from the closed vocabulary, capped evidence excerpts.

**Success Definition**:
- (a) Live gate green: `timeout 300 env IME_G3_LAB=1 .venv/bin/python tests/ime_g3_lab.py` →
  exit 0, all five rows `pass: true`, with every assertion family below holding.
- (b) Row report written with live-captured versions (sway, GTK4, kernel, PyGObject seat) and the
  closed status vocabulary `untested | insert-only | blocked (reason) | verified (versions +
  evidence links)`; GTK rows that pass BOTH insert and correction report **`verified`**.
- (c) Isolation provable: the harness never touches the live desktop, real clipboard, default
  microphone, or the active service (no `voicectl`/`systemctl`/`pactl`/`wl-copy`/`hyprctl`
  anywhere in the new files; inner phase refuses to run outside a disposable root).
- (d) `timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_support.py -q` green; the full
  IM+bulk regression suite (9 files, command below) green; ruff clean; `git status --porcelain`
  shows ONLY the five files above.

## User Persona

**Target User**: Internal — P1.M4.T5.S2 (field-class matrix re-run at drifted versions) and
P1.M5.T2 (pi-prompt / graphical-editor / browser rows) EXTEND this harness; P1.M7.T1 (G6
graduation) reads the row report as its evidence base.

**Use Case**: An implementer runs the live gate, gets one JSON verdict per row plus the summary,
then transcribes the verdicts into the bounded report. A failing row prints the exact assertion
and the field dump tail — no archaeology.

**Pain Points Addressed**: (1) G2's fake target can't see pixels — "applied" there is a stub's
word; only a real field witnesses visibility. (2) The im-lab evidence (29 rows / 24 pass) drove a
throwaway probe (`im_probe.py`), not the product adapter — G3 must drive `voice_typing/ime/`.
(3) "1–2 `changed` signals per commit cycle" proves signal-level atomicity but NOT that no
transient frame was painted — hence the frame-level oracle.

## Why

- **R.7 G3 is the gate that can mark rows verified**; R.4 fixes the route (IM-v2 primary) — this
  task PROVES the decided route on the productized stack. Do NOT re-run route discovery.
- **The adapter is takeover-complete** by the time this runs (P1.M4.T4.S1 contract: grab, release,
  `halt_for_takeover`, mutation-time re-checks) — G3's "refusing target" and later switch rows
  lean on those seams.
- **Drift is real** (d2 map §6: pacman now gtk4 4.24.1, sway 1:1.12-4 vs the im-lab measurement
  set) — the harness records LIVE versions into every report; nobody trusts stale numbers.
- **gtk4-demo / gtk3-demo are MISSING** on this box (d2 map §6) — hand-written field apps only.

## What

One private disposable desktop (Xvfb seat + private D-Bus + sway x11 backend — the im-lab recipe),
one real `ImeProcess` (manager) + `ImeTarget` stack, one instrumented GTK4 `Gtk.Entry`, five rows:

| Row | Drives | Core assertions |
|---|---|---|
| R1 `gtk-short-updates` | 6 short insert `show()`s (growing span, INSERT path, delta-only wire) | per-op: `applied`, cumulative text byte-exact, cursor at end, `cseq` Δ∈(1,2), frame oracle = exactly 1 text transition, 0 transient frames |
| R2 `gtk-firstword-20sent` | build a 20-sentence span (~1.2–2 KB, < 4000 B cap) then correct its FIRST word (CORRECTION path: `delete_surrounding_text(before=owned_bytes,0)` + `commit_string` + ONE `commit`) | byte-exact corrected text, cursor at end, `cseq` Δ∈(1,2), **single visible edit** (1 frame transition, no frame ever shows a deleted/partial/retype state), reach NOT bounded by utterance (span ≫ one utterance), pre-op `recheck()` ok |
| R3 `gtk-identical-finals` | the same final span `show()`n 3× more | each → `unchanged`, `cseq` Δ==0, 0 frame transitions, host `dones` unchanged, ZERO new wire commits (zero-diff law: identical ⇒ zero events) |
| R4 `gtk-long-unicode` | (a) 951 B multilingual Unicode insert (paste-lab lineage); (b) ~3.5 KB mixed insert; (c) >4 KB payload | (a),(b): `applied`, byte-exact round-trip (UTF-8 boundary safety), single visible edit; (c): `refused` (4000 B commit cap — refused, NEVER chunked), field untouched (`cseq` Δ==0, 0 transitions) → capability row records `blocked (4000-byte commit cap — refused by design; chunking vs R.1 one-edit rule undecided)` while the behavior assertion PASSES |
| R5 `gtk-refusing-readonly` | the field app booted with `--readonly` (`Gtk.Entry` not editable) | NO visible edit under any branch (`cseq` Δ==0, 0 transitions); either acquire refuses (R.3 "fail BEFORE delivery") or `show()` ∈ {`refused`,`unknown`} — record the ACTUAL branch honestly; adapter not wedged afterwards (a follow-up writable acquire+insert succeeds) |

**Global harness invariants** (asserted across the whole run): host event log contains ZERO
`grab_key` events (IM commits generate zero key events — delivery cannot self-trigger takeover);
the field's received-key counter stays 0 and `activate` (Enter) count stays 0 (no submission /
no shortcut execution); teardown leaves nothing behind (host exited, sway killpg'd, temp dir gone).

**Per-row assertion families** (every row weaves all that apply — G2's discipline, on a real field):
1. editor contents byte-exact (field's own atomic dump — the visible field);
2. cursor position exact;
3. single-visible-edit: frame oracle + `cseq` Δ ∈ (1,2) for mutating ops, (0,) for no-ops;
4. no submission / no keys reaching the field;
5. adapter result taxonomy exact (`applied|unchanged|refused|unknown`);
6. target-CONFIRMED text (`verify` → `surrounding_text`) agrees with the field dump;
7. `t_ms` latency recorded as MECHANISM-level info only — never claimed as G5 (no speech here).

### Success Criteria

- [ ] All five rows pass live with every applicable assertion family.
- [ ] Report uses the closed status vocabulary; passing rows show `verified (versions + evidence)`;
      the >4 KB capability sub-row shows `blocked (reason)`; nothing is marked verified by G2.
- [ ] Isolation greps clean (Level 4); scratch bounded (caps enforced, temp dir removed).
- [ ] Pure unit tests + full IM regression suite green; only the five new files in git status.

## All Needed Context

### Context Completeness Check

_Pass._ An implementer who knows nothing about this repo gets: the boot recipe (verbatim env
guard), the exact adapter API and its decision order, the field-app oracle design with code, the
row matrix with expected adapter results, the evidence/report conventions to mirror, and the exact
validation commands with the repo's two-timeout discipline.

### Documentation & References

```yaml
# MUST READ — this task's own research (written 2026-11-23; the structural facts below live there)
- docfile: plan/008_a47116bb2b79/P1M4T5S1/research/imlab-pattern.md
  why: the im-lab boot recipe verbatim (two-phase re-exec, mktemp root, private dbus config,
        xvfb-run -a dbus-run-session, WLR_BACKENDS=x11 guard, sway readiness polls, killpg
        teardown), field_gtk.py's dump schema {seq,cseq,kind,text,pos,t}, the cseq oracle,
        evidence caps (64 KiB im.jsonl, 2000-dump cap, screenshot sha pairs), and the 29-rows/
        24-pass reference run (~90 s).
- docfile: plan/008_a47116bb2b79/P1M4T5S1/research/adapter-api.md
  why: the EXACT adapter surface G3 drives — ImeProcess.spawn/request/healthy/stop,
        ImeTarget.acquire/recheck/show/leave, FieldBinding fields, the show() decision order
        (render-equal → UNCHANGED zero events; revision regression → REFUSED; INSERT vs
        CORRECTION path; 4000 B cap → REFUSED never chunked), host commands + SHOW_CONFIRM_WAIT,
        and the labs' HostPipes ping-pump pattern.
  section: "1. Package map" + "show() decision order"

# The contract stack this consumes (READ-ONLY — do not modify these files)
- file: plan/008_a47116bb2b79/P1M4T4S1/PRP.md
  why: the INPUT adapter contract — takeover-complete (grab engage/release, TakeoverWatch,
        halt_for_takeover, mutation-time re-checks). G3 consumes; never edits.
- file: voice_typing/ime/target.py
  why: ImeTarget — acquire()/recheck()/show()/leave()/finalize()/cancel() (leave at :312,
        finalize :282, cancel :331 — T3.S3 landed). show(session, utterance, seq,
        expected_revision, span) -> ShowResult. Duck-types any proc with .request(cmd,
        timeout=..., **fields) — ImeProcess satisfies it.
  gotcha: recheck() never mutates; correction path verifies _owned_region_intact BEFORE the wire.
- file: voice_typing/ime/manager.py
  why: ImeProcess — spawns `sys.executable -m voice_typing.ime.ime_host [log]`; request/healthy/
        stop; on_event feeds every event dict on the reader thread; killpg teardown.
  gotcha: the child needs the repo root importable (cwd) and inherits the seat env — the harness
          inner phase must run with cwd=repo root and the seat vars already exported.
- file: voice_typing/ime/ime_host.py
  why: host JSONL commands (acquire/show/verify/leave/ping), SHOW_CONFIRM_WAIT=0.22 s,
        64 KiB-capped event log via EventLogWriter, unavailable → clean exit(0).
- file: voice_typing/bulk_delivery.py
  why: ShowResult enum (applied|unchanged|refused|unknown) + rendered_equal() zero-diff guard.
- file: tests/ime_correction_lab.py
  why: THE closest existing pattern — env gate (GATE_ENV="IME_CORRECTION_LAB"), docstring run
        line `timeout 300 env IME_CORRECTION_LAB=1 .venv/bin/python tests/ime_correction_lab.py`
        (:8), two-phase boot (outer re-exec at :400), lab.spawn helper (:141), sway spawn (:186),
        system-python3 field app spawn (:220), host spawn (:342), TemporaryDirectory scratch.
        Fork its skeleton; do not modify it.
- file: tools/im-lab/field_gtk.py
  why: the field-app lineage to fork — Gtk.Application("org.imlab.field"), window title
        "imlab-field-gtk", signals `changed` + `notify::cursor-position`, atomic dump via
        field.tmp + os.replace, ready flag via GLib.idle_add.
  gotcha: EVIDENCE-ADJACENT research tool — do NOT edit it; fork into tests/ime_g3_field_gtk.py.
- file: tools/im-lab/imlab_run.py
  why: row-machinery reference — per-row try/except (one failure never kills the run),
        lab.verdict() JSON lines, summary + SystemExit(1), --keep DIR escape hatch.
  gotcha: never edit (evidence record).
- file: tests/test_g2_bulk_gate.py + plan/008_a47116bb2b79/architecture/g2_gate_record.md
  why: the gate-record format to mirror (date+HEAD, verbatim mandate, verdict table, assertion
        families, "necessary, never sufficient" banner) and the discipline that G2 NEVER
        verifies a field row.
- file: tests/D1_DUCK_EVIDENCE.md
  why: the checked-in evidence-doc style — header with method/result, row table with scripted
        check names + measured values, verbatim excerpts, bounded length.

# PRD ground truth
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: §4.2sexies R.7 G3 row spec + status vocabulary verbatim; R.1 event-count law (insertion=1,
        correction=1, zero-diff=0; no per-character retype, no caret walk, no blank frame); R.2
        evidence table (GTK fires 1–2 changed per commit cycle; frame-level single-edit
        unverified — THIS task closes that hole); R.4 (route decided; no re-discovery).
  section: "R.7 Verification and graduation gates" + "R.1" + "R.4".
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: §5 lab-reuse verdicts (field_gtk REUSE as G3 oracle; imlab_run REUSE as harness pattern);
        §6 environment (system PyGObject Gtk 4.24 OK; gtk4-demo MISSING; pacman drift list).
  section: "5. Lab-reuse table" + "6. IM-route environment".

# External — protocol + GTK instrumentation ground truth
- url: https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/input-method/input-method-unstable-v2.xml
  why: the wire contract (commit_string / delete_surrounding_text / atomic commit(serial));
        also vendored at tests/fixtures/input-method-unstable-v2.xml.
- url: https://docs.gtk.org/gtk4/method.Widget.add_tick_callback.html
  why: the frame-sampling mechanism — a tick callback runs each frame the clock paints, keeping
        the frame clock alive; sample (text hash, pos, cseq) per tick.
- url: https://docs.gtk.org/gtk4/signal.Entry.changed.html
  why: `changed` fires 1–2× per decomposed commit (delete+insert) — cseq Δ∈(1,2), never ==1
        exactly. Also signal.Entry.activate (Enter) for the submission counter.
- url: https://docs.gtk.org/gtk4/ctor.Entry.html + method.Entry.set_editable.html
  why: the refusing-target row (editable=False rejects IM insertion).
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/ime/            # the ADAPTER under test (READ-ONLY for this task)
├── protocol.py  wlwire.py  ime_host.py  manager.py  target.py  takeover.py(T4)
tests/
├── ime_acquire_lab.py  ime_show_lab.py  ime_correction_lab.py   # env-gated lab precedent
├── test_ime_{protocol,wlwire,host,manager,target,takeover}.py   # fake-injection unit tests
├── test_g2_bulk_gate.py    tests/D1_DUCK_EVIDENCE.md  tests/G1_BASELINE.md
├── fixtures/input-method-unstable-v2.xml
tools/im-lab/               # research lab (READ-ONLY evidence): imlab_run.py, field_gtk.py, …
plan/008_a47116bb2b79/architecture/{d2_bulk_delivery_map.md, g2_gate_record.md}
```

### Desired Codebase tree with files to be added

```bash
tests/
├── ime_g3_support.py       # NEW — pure: status vocab, payloads, frame-oracle, report renderer
├── ime_g3_field_gtk.py     # NEW — instrumented GTK4 field app (system python3; --readonly)
├── ime_g3_lab.py           # NEW — env-gated live runner: boot + rows R1–R5 + verdicts
└── test_ime_g3_support.py  # NEW — collected pure unit tests for ime_g3_support
plan/008_a47116bb2b79/architecture/
└── g3_gtk_rows.md          # NEW — the bounded row-report (DOCS deliverable)
plan/008_a47116bb2b79/P1M4T5S1/research/{imlab-pattern.md, adapter-api.md}  # already written
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL (AGENTS.md): TWO timeouts on every non-trivial command — inner GNU `timeout`, outer
#   bash-tool `timeout` above it. The live gate: inner 300, outer 360. pytest: inner 120/180.
# CRITICAL: automation NEVER exercises the live desktop / real clipboard / default mic / active
#   service (R.7). Private compositor + synthetic input only; no voicectl/systemctl/pactl/wl-copy/
#   hyprctl anywhere in the harness (grep-proven, Level 4). The harness spawns its OWN ImeProcess
#   — it must NOT stop/start the user's voice-typing unit (unlike tests/d1_duck_evidence.sh).
# CRITICAL: /tmp is a 32 GB tmpfs (= RAM). All scratch in ONE TemporaryDirectory; every log
#   capped (host event log 64 KiB via EventLogWriter; field dumps ≤2000 writes then a
#   `dump_capped` flag; frame ring bounded; verdicts one line/row). Teardown via killpg + the
#   TemporaryDirectory context manager — never a bare pkill (AGENTS.md cleanup recipe is for
#   WEDGED runs, not the happy path).
# CRITICAL: GTK fires 1–2 `changed` signals per commit cycle (delete+insert decomposition) —
#   assert cseq Δ ∈ (1,2) for mutating ops; Δ==1-only asserts are WRONG and will flake.
# GOTCHA: signal-level atomicity ≠ frame-level. A decomposed commit still paints once, but ONLY
#   a per-frame sampler proves it. Conversely a no-op op may paint ZERO frames (idle clock) —
#   the oracle treats 0 transitions + 0 transient frames as the no-op PASS.
# GOTCHA: keep the frame clock ALIVE: an `add_tick_callback` on the entry makes the clock run
#   every frame while mapped; sample cheap (hash ≤4 KB at ~60 Hz is trivial). Under Xvfb the
#   rate may free-run — the oracle is rate-agnostic (counts distinct text hashes, not frames).
# GOTCHA: run the field app with SYSTEM python3 (`shutil.which("python3")` — PyGObject/gi is
#   system-wide; the daemon .venv has no gi — d2 map §6). The ADAPTER runs under the venv
#   python (`sys.executable -m voice_typing.ime.ime_host`) with cwd=repo root.
# GOTCHA: one IM per seat: the harness's ime_host is the ONLY input method in the private seat.
#   An `unavailable` event → host exits 0 → row verdict `pass: null` (status `untested (infra)`),
#   NEVER a false pass. Never respawn into the same seat mid-row.
# GOTCHA: ImeTarget duck-types `.request(cmd, timeout=..., **fields)` — ImeProcess provides it.
#   Passive event reads can deadlock a pipes-driven host; the labs pump with `ping` during waits
#   (research/adapter-api.md §3). With the real manager the reader thread drains events — still
#   pump pings around long waits rather than blocking reads.
# GOTCHA: 4000 B commit cap is REFUSED-never-chunked (target.py). Keep R2's span and R4(a)/(b)
#   UNDER the cap; R4(c) deliberately crosses it and expects refusal + untouched field.
# GOTCHA: UTF-8 byte math everywhere (TargetUnits.UTF8_BYTES): payloads sized via
#   len(s.encode("utf-8")); the 951 B sample must be byte-exact 951, not 951 codepoints.
# GOTCHA: DON'T re-run route discovery (R.4) and DON'T re-prove takeover rows O/O2 beyond the
#   global zero-grab_key invariant (T4's optional ime_takeover_lab.py owns the deep takeover
#   rows). DON'T claim G5 timing — t_ms numbers are mechanism-level only.
# GOTCHA: this task must not modify voice_typing/** or any existing test (T4/S3 regions are
#   freshly landed; the harness only IMPORTS the adapter). New files only.
```

## Implementation Blueprint

### Data models and structure

```python
# tests/ime_g3_support.py — pure stdlib, importable by the venv (collected tests) and the lab

ROW_STATUSES = ("untested", "insert-only", "blocked", "verified")  # closed vocabulary (R.7)

@dataclass(frozen=True)
class RowVerdict:
    row: str            # "gtk-short-updates" | "gtk-firstword-20sent" | "gtk-identical-finals"
                        # | "gtk-long-unicode" | "gtk-refusing-readonly"
    sub: str = ""       # "unicode-951b" / "mixed-3500b" / "overcap-4500b" / "" …
    passed: bool | None # True | False | None (None = infra-untested — never a pass)
    checks: tuple[str, ...] = ()   # failed assertion names when passed is False
    t_ms: int | None = None        # mechanism-level info ONLY (never G5)

def row_status(verdicts: list[RowVerdict], *, exercised_correction: bool,
               capability_blocked_reason: str | None = None) -> str:
    # all True + insert AND correction exercised -> "verified (versions + evidence)"
    # any False -> "blocked (FAILED: <first check>)"   # honest failure, still closed-vocab
    # capability gap (e.g. over-cap refused-by-design) -> "blocked (<reason>)"
    # any None and no False -> "untested (infra: <reason>)"
    # insert-only paths never report "verified" (S2's terminal rows use "insert-only")

def single_edit_analysis(before: dict, after: dict, *, expect: "noop|change") -> dict:
    """Frame oracle over two field dumps.
    Dump v2 carries: frames (total painted), ring_rle — run-length-encoded frame text hashes
    [(hash8, n_frames), …] newest-last, cap 64 pairs — plus text/pos/cseq/t.
    Window = frames (before.frames, after.frames]. Boundary hashes: h(before.text),
    h(after.text). Returns {frames, transitions, transient_hashes, painted_final, ok}:
      transitions   = RLE segments whose hash differs from the previous segment's (in-window)
      transient     = any in-window hash not in {hA, hB}            -> delete/retype frame
      painted_final = at least one in-window frame carries hB        -> visibility witnessed
      ok = transient == [] and transitions == (0 if expect=="noop" else 1)
           and (expect=="noop" or painted_final)
    """

def build_payloads() -> dict[str, str]:
    # "short" list: 6 short spans; "twenty_committed"/"twenty_corrected": 20-sentence corpus,
    #   first word of sentence 1 differs, total ~1.2–2 KB UTF-8 (UNDER the 4000 B cap);
    # "unicode_951b": multilingual (CJK + accents + emoji + combining), len(encode)==951;
    # "mixed_3500b": ASCII+Unicode ~3500 B; "overcap_4500b": ~4500 B.

MAX_REPORT_LINES = 150
def render_report(versions: dict[str, str], rows: list[dict], meta: dict) -> str:
    # D1/g2_gate_record style: header (date, HEAD, live versions), the row table (closed vocab),
    # capped verbatim evidence excerpts, the banner "a G2 pass never marks a row verified",
    # open-items section. HARD cap 150 lines (truncate evidence blocks, count enforced by test).
```

```python
# tests/ime_g3_field_gtk.py — GTK4 app on SYSTEM python3 (fork of tools/im-lab/field_gtk.py)
# Keeps: Gtk.Application("org.imlab.g3field"), window title "imlab-g3-field-gtk", one Gtk.Entry,
# signals `changed` + `notify::cursor-position`, atomic dump field.tmp + os.replace -> field.json,
# ready flag file via GLib.idle_add, dump cap 2000 writes.
# Adds:
#   add_tick_callback on the entry -> per-frame sample (sha1(text)[:8], pos, cseq, t) into
#     collections.deque(maxlen=256); dump carries counters + ring_rle (RLE of the ring, cap 64
#     pairs). Gtk version (get_major/minor/micro) + editable flag in every dump.
#   `activate` signal counter (Enter/submission must stay 0).
#   Gtk.EventControllerKey on the entry -> received-key counter (field must see 0 keys — the
#     IM route commits text without key events).
#   --readonly flag -> entry.set_editable(False)  (the refusing target, row R5).
# Dump schema v2: {seq, cseq, kind, text, pos, t, frames, activated, keys, editable, gtk,
#                  ring_rle, dump_capped}   (superset of the im-lab schema — waiters port as-is)
```

```python
# tests/ime_g3_lab.py — env-gated runner, GATE_ENV = "IME_G3_LAB"; without it: print usage, exit 2.
# Two-phase re-exec mirroring tests/ime_correction_lab.py:
#   OUTER: TemporaryDirectory -> re-exec `[sys.executable, __file__, "run", root]` under
#     `xvfb-run -a dbus-run-session --config-file=<private dbus config>` with env
#     HOME=XDG_RUNTIME_DIR=TMPDIR=root, WLR_BACKENDS=x11, WLR_LIBINPUT_NO_DEVICES=1 (inner guard
#     refuses unless root==HOME==XDG_RUNTIME_DIR and WLR_BACKENDS=="x11").
#   INNER: write sway.conf ("xwayland disable\nfocus_follows_mouse no"); spawn sway; poll 20 ms
#     `until()` (7 s) for sway-ipc.*.sock -> SWAYSOCK and wayland-* -> WAYLAND_DISPLAY; focus via
#     xdotool if needed. Spawn the field app (system python3, tests/ime_g3_field_gtk.py [--readonly])
#     and wait for field.ready. Spawn the adapter: ImeProcess(event_log=<root>/ime_host.jsonl)
#     + .spawn(); build ImeTarget(proc). Rows run sequentially, each in try/except ->
#     RowVerdict; leave() at row end; verdicts.jsonl (one line/row) + stdout; summary line;
#     SystemExit(1) iff any passed is False; finally: teardown (target leave best-effort,
#     proc.stop() killpg, sway killpg, field terminate).
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE tests/ime_g3_support.py
  - IMPLEMENT: ROW_STATUSES, RowVerdict, row_status(), single_edit_analysis(), build_payloads(),
    render_report() (MAX_REPORT_LINES hard cap), plus dump-hash helper (sha1[:8]).
  - FOLLOW pattern: bulk_delivery.py's frozen dataclasses; g2_gate_record.md's report shape.
  - NAMING: snake_case; row ids exactly "gtk-short-updates", "gtk-firstword-20sent",
    "gtk-identical-finals", "gtk-long-unicode", "gtk-refusing-readonly" (S2/M5T2 reuse them).
  - PURITY: stdlib only; no gi/wayland/pytest imports (imported by both venv test and lab).
  - PLACEMENT: tests/ime_g3_support.py.

Task 2: CREATE tests/test_ime_g3_support.py
  - IMPLEMENT: oracle matrix — noop (0 transitions, no transient), change (exactly 1 transition,
    painted_final true), transient-frame rejection (a middle hash -> ok False), missing painted
    final -> ok False, RLE cap behavior; row_status closure over ROW_STATUSES (every output
    starts with a vocab word; False -> "blocked (FAILED: …)"; None -> "untested"); payload sizes
    (951 B byte-exact, twenty_* < 4000 B and >= 1200 B, overcap > 4000 B, UTF-8 multilingual
    content sanity); render_report <= MAX_REPORT_LINES with a 200-row stress input; determinism
    (same payloads twice).
  - FOLLOW pattern: tests/test_g2_bulk_gate.py (sys.path insert, plain asserts, no I/O outside
    tmp_path).
  - PLACEMENT: tests/test_ime_g3_support.py. MUST be collected by plain pytest (no env gate).

Task 3: CREATE tests/ime_g3_field_gtk.py
  - IMPLEMENT: the app per the data-model block. VERIFY the dump stays atomic (tmp + os.replace)
    and the 2000-write cap flips `dump_capped` instead of growing without bound.
  - FOLLOW pattern: tools/im-lab/field_gtk.py verbatim structure (window/entry/signals/dump);
    cite the lineage in the module docstring ("fork of tools/im-lab/field_gtk.py, im-lab
    evidence 2026-11-22").
  - GOTCHA: sample INSIDE the tick callback only when the widget is mapped; wrap GTK calls in
    GLib.idle_add-safe contexts; never let a sample raise into the GTK main loop.
  - PLACEMENT: tests/ime_g3_field_gtk.py (spawned by the lab with system python3).

Task 4: CREATE tests/ime_g3_lab.py
  - IMPLEMENT: boot per the data-model block (mirror ime_correction_lab.py's outer/inner split,
    lab.spawn with start_new_session=True, err_head helper for spawn failures).
  - IMPLEMENT rows R1–R5 exactly as the What-table specifies; each row: fresh acquire() ->
    ops -> dump before/after each op -> single_edit_analysis() -> assertions -> target.leave().
    Use target.show(session, utterance, seq, expected_revision, span) with monotonically
    increasing session/seq and expected_revision from the binding/last-applied revision.
  - ASSERT global invariants at summary: zero grab_key lines in ime_host.jsonl; field keys==0;
    activated==0.
  - EVIDENCE: <root>/verdicts.jsonl (one line/row, mirrored to stdout); ime_host.jsonl is the
    manager's capped EventLogWriter log; OPTIONAL grim screenshot sha256[:16] per row (images
    deleted; hashes only) when grim is present — skip silently otherwise.
  - EXIT: 0 all True; 1 any False; 2 usage/gate violation. Per-row try/except -> passed=None.
  - PLACEMENT: tests/ime_g3_lab.py. MUST NOT be pytest-collected (no test_ prefix; GATE_ENV).
  - PURITY: imports voice_typing.ime (manager/target) + ime_g3_support ONLY from repo code.

Task 5: RUN the live gate + WRITE plan/008_a47116bb2b79/architecture/g3_gtk_rows.md
  - RUN: `timeout 300 env IME_G3_LAB=1 .venv/bin/python tests/ime_g3_lab.py` (bash timeout 360).
  - WRITE (render via ime_g3_support.render_report, then hand-finish): header with date, HEAD,
    live versions (sway --version; GTK from the field dump's gtk field; kernel uname -r;
    `pacman -Q gtk4 sway` output), the five-row table with statuses, capped verbatim verdict
    excerpts (t_ms included, marked mechanism-level/not-G5), the banner "a G2 pass never marks
    a row verified", open items (preedit transition not rowed here; >4 KB chunking decision
    pending; Hyprland live-compositor row outstanding — S2/M5 scope).
  - BOUND: <= 150 lines (the renderer enforces; do not hand-expand past the cap).
```

### Implementation Patterns & Key Details

```python
# The row skeleton (R2 shown — the others differ only in payloads/expectations):
binding = target.acquire()                      # AcquireResult; assert ok, reason==""
before = dump()                                 # wait_field(seq bump) -> field.json dict
res = target.show(session=s, utterance="u1", seq=q, expected_revision=rev,
                  span=payloads["twenty_corrected"])
assert res is ShowResult.APPLIED                # CORRECTION path: before=owned_bytes, ONE commit
after = dump()
a = single_edit_analysis(before, after, expect="change")
assert a["ok"] and a["transient_hashes"] == [] and a["transitions"] == 1
assert after["text"].encode() == payloads["twenty_corrected"].encode()   # byte-exact
assert after["pos"] == len(after["text"])                                # cursor at end
assert after["cseq"] - before["cseq"] in (1, 2)                          # GTK commit cycle
v = proc.request("verify", timeout=2.5)                                  # target-CONFIRMED
assert v["text"].encode() == payloads["twenty_corrected"].encode()
target.leave()                                                             # row hygiene

# The frame sampler (inside tests/ime_g3_field_gtk.py):
def _on_tick(self, widget, frame_clock):
    text = self.entry.get_text()
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    self.ring.append((h, self.entry.get_position(), self.cseq, time.monotonic()))
    return GLib.SOURCE_CONTINUE               # keeps the frame clock running every frame

# Dump-side RLE (bounded): collapse the deque into [(hash, n), …] pairs, newest-last, cap 64 —
# the oracle consumes segments; per-frame payload never leaves the app.

# Zero-diff row (R3): identical span -> show() hits rendered_equal(_last_applied_span, span)
# FIRST in its decision order -> UNCHANGED, zero wire events; assert cseq delta == 0,
# transitions == 0, and host `ping` dones UNCHANGED across the three repeats.

# Over-cap row (R4c): span.encode() > 4000 -> show() -> ShowResult.REFUSED (cap check precedes
# the wire); assert field cseq/frames/text unchanged; row verdict True (behavior as specified)
# while the REPORT records the capability as "blocked (4000-byte commit cap …)".

# Read-only row (R5): boot a SECOND field instance with --readonly in the SAME seat (fresh
# window; re-acquire binds the focused field — focus it via sway/xdotool or spawn it before the
# writable one is destroyed). Whatever branch the platform takes (acquire refuses, or show
# returns refused/unknown because the read-only entry never applies the commit), assert: field
# cseq delta == 0, no transient frames, no crash; THEN re-acquire on a WRITABLE field and land
# one insert (adapter-not-wedged witness). Record the actual branch verbatim in the verdict.
```

### Integration Points

```yaml
CONSUMES (READ-ONLY):
  - voice_typing/ime/manager.py ImeProcess   # real subprocess lifecycle (spawn/stop killpg)
  - voice_typing/ime/target.py ImeTarget     # acquire/recheck/show/leave — the G3 driving surface
  - voice_typing/bulk_delivery.py ShowResult # result taxonomy
  - P1.M4.T4.S1 takeover seams               # consumed implicitly (grab never engaged here; the
                                             # zero-grab_key global invariant re-pins row O2)
PRODUCES:
  - The G3 harness pattern (row registry + oracle + report) that S2 (field-class matrix) and
    P1.M5.T2 (pi prompt / editor / browser rows) extend — keep rows data-driven (row id ->
    callable) so S2 adds fields without touching the boot.
  - plan/008_a47116bb2b79/architecture/g3_gtk_rows.md — the first G3 evidence base for G6 (M7.T1).
DOES NOT TOUCH:
  - voice_typing/**, tools/im-lab/**, every existing test, config.toml, pyproject.toml,
    tests/ACCEPTANCE.md (M7.T2.S2 owns that sync), tasks.json, PRD/plan read-only docs.
```

## Validation Loop

### Level 1: Syntax & Style (immediate)

```bash
ruff check tests/ime_g3_support.py tests/ime_g3_field_gtk.py tests/ime_g3_lab.py \
  tests/test_ime_g3_support.py --fix
ruff format tests/ime_g3_support.py tests/ime_g3_field_gtk.py tests/ime_g3_lab.py \
  tests/test_ime_g3_support.py
# Expected: zero errors (ruff is the repo's gate; no mypy config).
```

### Level 2: Unit Tests (compositor-free)

```bash
# New pure tests (fast, deterministic):
timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_support.py -q
# (set the bash tool timeout to 180.)

# Zero regression across the adapter + controller + G2 surfaces (the T4 gate command):
timeout 180 .venv/bin/python -m pytest tests/test_ime_takeover.py tests/test_ime_host.py \
  tests/test_ime_protocol.py tests/test_ime_target.py tests/test_ime_wlwire.py \
  tests/test_ime_manager.py tests/test_bulk_delivery.py tests/test_bulk_controller.py \
  tests/test_g2_bulk_gate.py -q
# (bash tool timeout 240.) Expected: all green — this task added files only.
```

### Level 3: The live G3 gate (the deliverable's proof)

```bash
# ONE run, private disposable desktop; ~2–4 min expected (boot ~15 s + rows):
timeout 300 env IME_G3_LAB=1 .venv/bin/python tests/ime_g3_lab.py
# (bash tool timeout 360.)
# Expected: exit 0; stdout shows one JSON verdict per row (all "passed": true) + summary line;
# the R4(c) and R5 verdicts carry their branch notes. Exit 1 -> read the failed checks + field
# dump tail printed by the failing row; fix and re-run. Exit 2 -> gate/env misuse.
# THEN write/refresh plan/008_a47116bb2b79/architecture/g3_gtk_rows.md from this run (Task 5).
# If a run wedges (it should not — every wait is a bounded until()): inner timeout returns 124;
# the TemporaryDirectory context removes scratch on the way out; re-run once after confirming
# `pgrep -f 'ime_g3|sway'` is empty. NEVER run against the operator's session.
```

### Level 4: Contract audit (grep-provable invariants)

```bash
# Isolation — the harness never touches the live desktop/clipboard/mic/service:
grep -nE "voicectl|systemctl|pactl|wl-copy|hyprctl|XDG_RUNTIME_DIR/voice-typing" \
  tests/ime_g3_lab.py tests/ime_g3_field_gtk.py tests/ime_g3_support.py || echo "ok: isolated"
# Closed vocabulary + banner + bound in the report:
grep -c "" plan/008_a47116bb2b79/architecture/g3_gtk_rows.md        # <= 150
grep -n "G2 pass never" plan/008_a47116bb2b79/architecture/g3_gtk_rows.md
grep -oE "untested|insert-only|blocked|verified" \
  plan/008_a47116bb2b79/architecture/g3_gtk_rows.md | sort | uniq -c
# Read-only discipline — the adapter and evidence records untouched:
git status --porcelain   # ONLY the five new files (plus the report once written)
# Evidence-only files under plan/ are the durable record; scratch dirs are gone:
ls /tmp | grep -c "ime_g3\|tmp[a-zA-Z0-9]" || true   # no leftover harness dirs
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1 ruff clean; Level 2 both suites green; Level 3 exit 0; Level 4 greps clean.
- [ ] `git status --porcelain` shows only the five new files.

### Feature Validation

- [ ] All five rows pass with every applicable assertion family (contents, cursor, single
      visible edit via the frame oracle, no submission/keys, exact result taxonomy,
      target-confirmed verify, t_ms recorded).
- [ ] R2 proves insert AND correct on one field with reach beyond a single utterance.
- [ ] R3 shows identical finals ⇒ zero events/edits/transitions; R4(c) refused-not-chunked with
      an untouched field; R5 records the ACTUAL refusal branch with the adapter recovering.
- [ ] Report: closed vocabulary, live versions, capped evidence, G2-never banner, ≤ 150 lines.

### Code Quality Validation

- [ ] ime_g3_support is pure stdlib; the field app forks field_gtk.py with cited lineage; the
      lab mirrors ime_correction_lab.py's boot; no new patterns invented where these exist.
- [ ] Scratch bounded everywhere (caps + TemporaryDirectory + killpg teardown verified by a
      clean re-run).
- [ ] Anti-patterns below avoided.

### Documentation & Deployment

- [ ] Module docstrings carry lineage + evidence citations (im-lab run 2026-11-22; d2 map §5/§6).
- [ ] The row report records versions and links; open items routed to S2/M5; no config/env
      changes anywhere.

## Anti-Patterns to Avoid

- ❌ Don't mark ANY row verified from G2, probe results, or the im-lab record — only this
  harness's field-side witnesses (frame oracle + dump + verify) verify, and only with versions.
- ❌ Don't assert `cseq` Δ==1 exactly — GTK fires 1–2 `changed` per commit cycle.
- ❌ Don't substitute a byte reader, scrollback, or fake editor for the visible field (R.4);
  don't skip the frame oracle because "signals look atomic".
- ❌ Don't touch `voice_typing/**`, `tools/im-lab/**`, or existing tests; don't re-run route
  discovery; don't re-prove takeover rows beyond the zero-grab_key invariant.
- ❌ Don't run anything against the live desktop; don't stop/start the user's service; don't
  write unbounded scratch under /tmp (tmpfs = RAM — AGENTS.md Rule 3).
- ❌ Don't claim G5 timing; t_ms is mechanism-level info. Don't paper over R5's actual branch or
  the R4(c) cap — blocked-with-reason is a legitimate, expected result.
- ❌ Don't let one row's failure kill the run (per-row try/except → `passed: null`), and don't
  treat `null` as a pass.

---

## Confidence Score

**9/10** — every structural input is proven and documented: the boot recipe and field-oracle
lineage ran 29 rows successfully in im-lab; three sibling labs (`tests/ime_*_lab.py`) already boot
this exact stack; the adapter surface (`ImeProcess`/`ImeTarget`, `show()` decision order, 4000 B
cap, `leave()`) is landed and unit-pinned; the evidence/report conventions have two in-repo
precedents (g2_gate_record.md, D1_DUCK_EVIDENCE.md). Residual risks: (1) frame-clock behavior
under Xvfb (mitigated: tick callback keeps the clock alive; the oracle is rate-agnostic and
no-op-tolerant); (2) the read-only refusal branch is genuinely unmeasured — the row is designed
to record whichever branch occurs honestly; (3) T3.S3/T4.S1 land timing — treated as contract
per the parallel-execution context; if `leave()` is momentarily absent, fall back to
`proc.request("leave", timeout=2.5)` (the host command is landed).

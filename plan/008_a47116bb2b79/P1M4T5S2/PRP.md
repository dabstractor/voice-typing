# PRP — P1.M4.T5.S2: Field-class matrix re-run at installed versions (drift!)

## Goal

**Feature Goal**: Re-run the R.2 field-class matrix rows at the **installed** versions —
foot 1.28.0 / kitty 0.51.0 / ghostty 1.4.0 (vs the measured 0.49.1 / 1.3.1) — through the
**product IM transport** (`voice_typing/ime/ime_host` via `ImeProcess`), and make the first
**isolated real-Hyprland row attempt** at 0.57.2 (nested failed before: aquamarine
`CBackend::create()` — root cause now identified, see Context). Every row reports the closed
vocabulary `untested | insert-only | blocked (reason) | verified (versions + evidence)`;
insert-only rows NEVER run as full dictation; terminal verification is APP-SIDE ONLY
(terminals never send `surrounding_text`).

**Deliverable** (5 NEW files; zero modifications to `voice_typing/`, `tools/im-lab/**`,
existing tests, or S1's in-flight files):
1. `tests/ime_g3_matrix_support.py` — pure stdlib: terminal-probe outcome model +
   closed-vocab classifier, Hyprland attempt-variant ladder (data), the **route-table
   derivation** (matrix → per-field-class route → P1.M5.T3 clipboard-fallback decision),
   bounded matrix-report renderer (≤150 lines).
2. `tests/ime_g3_field_term.py` — app-side terminal witness (fork of
   `tools/im-lab/field_term.py`; same dump schema `{line, seq, t}`, 2000-write cap).
3. `tests/ime_g3_matrix_lab.py` — env-gated live runner (`IME_G3_MATRIX_LAB=1`), fork of
   S1's two-phase boot; rows: foot / kitty / ghostty terminal probes + the isolated
   Hyprland-row attempt ladder; verdicts.jsonl; exit 0/1/2.
4. `tests/test_ime_g3_matrix_support.py` — collected, compositor-free unit tests for (1).
5. `plan/008_a47116bb2b79/architecture/g3_field_matrix.md` — the **refreshed bounded matrix
   report + route table** (DOCS contract; the artifact P1.M5.T3 reads to decide whether the
   clipboard fallback is needed at all).

**Success Definition**:
- (a) Live gate runs clean: `timeout 420 env IME_G3_MATRIX_LAB=1 .venv/bin/python
  tests/ime_g3_matrix_lab.py` → exit 0 with every probe MEASURED (each row's recorded
  outcome is one of the pre-declared legal branches; harness invariants held). Capability
  findings (e.g. ghostty insert not delivered, kitty delete ignored, Hyprland boot failure)
  are **measurements, not gate failures** — exit 1 fires only on infra/assertion violations.
- (b) `g3_field_matrix.md` written with LIVE-captured versions (foot/kitty/ghostty/hyprland/
  sway/GTK + date + HEAD), per-row closed-vocab statuses, capped evidence excerpts, the
  route table with the explicit M5.T3 decision (`needed` | `skip (evidence)`), and the
  banner "a G2/lab pass never marks a row verified".
- (c) Isolation provable: nothing touches the live desktop, real clipboard, default
  microphone, or the active service. The ONLY permitted live-session posture is the im-lab
  precedent: a **passive registry listing** of the live Hyprland socket (connect, list
  globals, exit — no binds, no input) to refresh 0.56.2→0.57.2 advertisement, and it can
  never flip the relay row off `untested`. Every `hyprctl` invocation must carry `--sig
  <private-instance-signature>`.
- (d) `timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_matrix_support.py -q` green;
  the IM+G3 regression suites green; ruff clean; `git status --porcelain` shows ONLY the
  five files above.

## User Persona

**Target User**: Internal — P1.M5.T3 (conditional clipboard insert-fallback) reads the route
table as its go/no-go input; P1.M5.T2 (pi-prompt / editor / browser rows) and P1.M7.T1 (G6
graduation) consume the refreshed matrix as the coverage evidence base.

**Use Case**: An implementer runs the live gate once per terminal-class version bump, gets
one JSON verdict per row (probe outcome + measured branch + versions), transcribes into the
bounded report, and reads off the route table whether M5.T3 is needed. A failing probe prints
the exact assertion and the term.json/err tail — no archaeology.

**Pain Points Addressed**: (1) The 2026-11-22 matrix was measured at kitty 0.49.1 /
ghostty 1.3.1 / Hyprland 0.56.2 — the ghostty version watch TRIGGERED and the installed set
drifted; route decisions built on stale numbers are unsound. (2) The Hyprland relay row has
never existed (nested boot failure was recorded but not root-caused). (3) Upstream research
(now in `research/upstream-changelog-drift.md`) says ghostty's gtk-IME fix (#15246) landed
AFTER 1.4.0's cut and kitty 0.51.1 still no-ops `delete_surrounding_text` — but the item
contract requires MEASUREMENT, not source-reading: retest before trusting any verdict.

## Why

- **PRD §4.2sexies R.2** pins the field-class matrix as route evidence; R.4 fixed the route
  (IM-v2 primary) and forbids re-running route **discovery** — this task refreshes route
  **coverage** at real versions, which is different and required ("retest before trusting
  ghostty = unavailable"). d2 map §6 flags the drift; §9 risks 1–2 and 5 are exactly this
  task.
- **P1.M5.T3's conditionality needs a decision artifact**: if ghostty-class insert now works
  over IM, the clipboard insert-fallback is unnecessary; if still dead, M5.T3 proceeds under
  R.6. Either way the decision must cite measured evidence with versions.
- **The Hyprland row** is the last unmeasured relay: upstream diffed 0.56.2→0.57.2 relay
  code = logging refactors only, but the operator's compositor class has zero behavioral
  evidence. An isolated attempt with `blocked(reason)` is a legitimate, expected result
  (d2 map §9.2); a booted row would be the first real relay evidence.

## What

One private disposable desktop (Xvfb seat + private D-Bus + sway x11 backend — the S1/im-lab
recipe, forked into the new lab), one real `ImeProcess` per seat, **terminal rows driven at
the HOST transport level** (`proc.request("acquire"/"show"/"verify")` — NOT `ImeTarget`,
whose policy requires a surrounding-text snapshot terminals never provide):

| Row | Drives | Legal measured branches (ALL recorded, none "failed") |
|---|---|---|
| T1 `foot-insert-correct` | host `show(before=0,text=…)` insert; `show(before=3,text="v2")` correct probe; `acquire` reason probe | insert delivered \| not; delete applied (`"hello fromv2"`) \| ignored (`"hello from imv2"`); acquire: `no surrounding text` \| ok |
| T2 `kitty-insert-correct` | same probes at kitty 0.51.0 | same branch set |
| T3 `ghostty-insert` | same probes at ghostty 1.4.0 | insert delivered \| not (line unchanged); activation: yes \| no |
| T4 `hyprland-isolated` | variant ladder (below); if booted: S1's `tests/ime_g3_field_gtk.py` field + host against the Hyprland socket; insert/correct/preedit/surrounding probes | booted+rows measured \| `blocked (nested Hyprland: <err-head> @ <variant>)` |
| T5 `registry-refresh` (optional) | passive live Hyprland registry listing (im-lab posture) | globals listed \| skipped (posture note) |

**Hyprland variant ladder** (each attempt: fresh env dict, ≤25 s socket wait for
`hypr/<sig>/.wl_socket`, `hypr.err` head ≤400 B captured on failure; ≤3 attempts total):
1. **Nested Wayland backend**: `WAYLAND_DISPLAY=<sway socket>`, **drop the inherited
   `WLR_BACKENDS=x11`** (aquamarine has NO x11 backend — drm/headless/wayland only; the
   inherited x11 value is the probable killer of the 2026-11-22 attempt,
   `research/matrix-rerun-mechanics.md` §4), `WLR_RENDERER=pixman`,
   `LIBGL_ALWAYS_SOFTWARE=1`, `MESA_SHADER_CACHE_DISABLE=true`.
2. **Aquamarine headless**: `AQ_NO_KMS_REQUIREMENT=1` (+ `AQ_DRM_DEVICES=` pinned empty if
   needed) per upstream docs; output via the auto `HEADLESS-0`; if no field can be shown
   without a real output, this variant only proves boot + registry — still a valid
   `blocked (headless: no visible output for field rows)`.
3. **Legacy posture verbatim** (`WLR_BACKENDS=x11` inherited) — re-confirm the recorded
   failure shape with the error head, for the report's provenance.

**Probe invariants** (these ARE assertions — violations fail the row as harness bugs): the
app-side buffer after each probe is byte-exactly one of the pre-declared legal outcome
strings; `t_ms` recorded mechanism-level only (never G5); no probe ever sends a correction
to a terminal whose insert probe measured not-delivered (skip-deps: T-row correct probes run
only if that terminal's insert delivered); host event log contains ZERO `grab_key` events;
term.json never exceeds its write cap; teardown kills every process group.

**Terminal row discipline** (item contract): insert-only rows NEVER run as full dictation —
no streaming session, no partials cadence, no multi-utterance sequences; each terminal gets
at most: activation probe, one ASCII insert, one short Unicode insert, one correct probe,
one preedit app-side diagnostic (zero bytes to app). Verification is app-side only via
`term.json`; IM-side `verify`/`acquire` replies are recorded as the surrounding-text-channel
evidence (their `reason` strings), never as a text channel.

### Success Criteria

- [ ] All terminal rows measured at live-captured installed versions with legal-branch
      outcomes recorded in verdicts.jsonl + the report.
- [ ] Hyprland row either measured on a booted isolated instance or recorded
      `blocked (reason)` with the error head and variant — never silently skipped.
- [ ] Route table in the report decides M5.T3 (`needed` / `skip (evidence)`) from the
      measured branches via the unit-tested derivation, not prose.
- [ ] Report uses the closed vocabulary, carries live versions, is ≤150 lines, and includes
      the G2-never banner.
- [ ] Isolation greps clean; scratch bounded; only the five new files in git status.

## All Needed Context

### Context Completeness Check

_Pass._ An implementer who knows nothing about this repo gets: the exact host-command
surface to drive (with the critical ImeTarget-vs-host distinction), the terminal spawn and
app-side-witness recipes verbatim from the measured im-lab, the Hyprland ladder with its
root-cause analysis and upstream-verified env vars, the upstream changelog verdicts with
URLs, the S1 contract surfaces to import (never edit), and the exact validation commands
under the repo's two-timeout discipline.

### Documentation & References

```yaml
# MUST READ — this task's own research (written 2026-11-23)
- docfile: plan/008_a47116bb2b79/P1M4T5S2/research/matrix-rerun-mechanics.md
  why: §2 the exact im-lab terminal-row recipe (spawn args, app_ids, focus criteria, probe
        sequence, killpg); §3 the host-transport surface + WHY ImeTarget cannot drive
        terminal rows (acquire refuses "no surrounding text"; show refuses "not acquired");
        §4 the nested-Hyprland root cause (inherited WLR_BACKENDS=x11 vs aquamarine's
        drm/headless/wayland-only backends) + variant ladder + live-registry posture;
        §5 the S1 seams to import; §6 the item's pinned constraints.
- docfile: plan/008_a47116bb2b79/P1M4T5S2/research/upstream-changelog-drift.md
  why: upstream verdicts with URLs — ghostty 1.4.0 NOT-FIXED (PR #15246 "gtk: preserve IME
        commits triggered by key release" merged 2026-11-17, milestone 1.5.0, AFTER the
        1.4.0 cut; 1.4.0 landed only candidate-window/preedit fixes); kitty 0.50/0.51
        NOT-FIXED (wl_text_input.c at v0.51.1: delete_surrounding_text still a debug-log
        no-op; set_surrounding_text never called); Hyprland 0.56.2→0.57.2 relay diffs =
        LOG refactors only; aquamarine headless recipe AQ_NO_KMS_REQUIREMENT=1.
        NOTE: these set EXPECTATIONS for the report's discussion section — the harness
        still MEASURES and records what actually happens; do not hard-code them as outcomes.

# The S1 harness contract (parallel-landed; IMPORT its pure seams, NEVER edit its files)
- file: plan/008_a47116bb2b79/P1M4T5S1/PRP.md
  why: THE input contract — defines tests/ime_g3_support.py (ROW_STATUSES, RowVerdict,
        build_payloads, render_report, single_edit_analysis), tests/ime_g3_field_gtk.py
        (the GTK field app S2's Hyprland row SPAWNS read-only with system python3),
        tests/ime_g3_lab.py (the two-phase boot S2 forks), and
        plan/008_a47116bb2b79/architecture/g3_gtk_rows.md (the GTK-class rows of the
        refreshed matrix — S2 REFERENCES it, never re-runs GTK rows, never edits it).
  gotcha: S1 files are treated as landed exactly per that PRP; if `leave()` etc. differ,
          S2 only ever imports the PURE support module and spawns the field app — no
          structural coupling beyond those two surfaces.
- file: plan/008_a47116bb2b79/P1M4T5S1/research/imlab-pattern.md
  why: the boot recipe verbatim (two-phase re-exec, mktemp root, private dbus config,
        xvfb-run -a dbus-run-session, WLR_BACKENDS=x11 guard for the SWAY parent,
        readiness polls, killpg teardown) + evidence caps.
- file: plan/008_a47116bb2b79/P1M4T5S1/research/adapter-api.md
  why: ImeProcess/ime_host command surface and the HostPipes ping-pump pattern (pump pings
        around long waits; never block a passive event read).

# The adapter stack under test (READ-ONLY)
- file: voice_typing/ime/ime_host.py
  why: host commands acquire/show/cancel/grab/verify/leave/ping (_dispatch :137);
        _show (:180) takes {before, text} and does NOT require acquire — only activation;
        _acquire (:156) bounded-waits _SURROUND_WAIT_S for a PUSHED snapshot and replies
        reason="no surrounding text" — that reason string IS terminal-row evidence.
- file: voice_typing/ime/manager.py
  why: ImeProcess.spawn/request/healthy/stop — spawn `sys.executable -m
        voice_typing.ime.ime_host [log]` with cwd=repo root + seat env; killpg teardown;
        on_event reader thread drains host events.
- file: voice_typing/ime/target.py
  why: the POLICY layer S2 must NOT drive for terminal rows (acquire requires snapshot;
        show refuses "not acquired" without a binding) — cited so the implementer doesn't
        burn hours trying to force ImeTarget onto a terminal.
- file: voice_typing/bulk_delivery.py
  why: ShowResult taxonomy (applied|unchanged|refused|unknown) reused for host reply mapping.

# The measured precedent (READ-ONLY evidence record — fork its recipes, never edit)
- file: tools/im-lab/imlab_run.py
  why: term_rows (:289) — the probe sequence, terminal spawn args (:387-390: `foot -T
        imlab-foot`/`foot`; `kitty --class imlab-kitty`/`imlab-kitty`; `ghostty
        --gtk-single-instance=false --shell-integration=none -e`/`com.mitchellh.ghostty`),
        wait_field against term.json, per-row killpg.
- file: tools/im-lab/field_term.py
  why: the 56-line readline witness to fork — poll thread 5 ms, atomic term.tmp→term.json,
        {line, seq, t} schema, 2000-write cap, term.ready flag, term.final at EOF.
- file: tools/im-lab/hypr_nest.py
  why: the failed nested attempt — shows the bug to avoid (:146-155 inherits
        WLR_BACKENDS=x11 into the Hyprland env), the hypr/<sig>/.wl_socket readiness glob,
        hyprctl --sig focuswindow pattern, and the graceful "untested verdict instead of
        hanging" posture.
- file: tools/im-lab/README.md
  why: the matrix being refreshed (:41-84), the passive live-registry posture (:79-84),
        open items (:97-113) this task closes or re-baselines.
- file: tools/im-lab/globals.py
  why: the passive registry lister (51 lines) to reuse read-only for T5.

# PRD ground truth
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: §4.2sexies R.2 (evidence table + provenance limits — "a passing transport probe
        NEVER flips these to passed"), R.4 (route DECIDED; do NOT re-run route discovery),
        R.7 (G3 row spec + status vocabulary; automation must not exercise the live
        desktop/clipboard/mic/service).
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: §6 the drift list + environment probes; §9 risks 1-2 (version drift), 5 (terminals
        send no surrounding text) — the risks this task retires or re-baselines.
- file: tests/D1_DUCK_EVIDENCE.md
  why: the checked-in evidence-doc style (header method/result, row table, verbatim
        excerpts, bounded length) the matrix report mirrors.

# External — upstream ground truth (also summarized in upstream-changelog-drift.md)
- url: https://github.com/ghostty-org/ghostty/pull/15246
  why: the gtk-IME fix ("preserve IME commits triggered by key release") — merged
        2026-11-17, milestone 1.5.0: NOT in installed 1.4.0. Sets the ghostty expectation.
- url: https://sw.kovidgoyal.net/kitty/changelog/
  why: 0.50/0.51 IME entries are preedit-cursor/candidate-window positioning only — no
        delete_surrounding/surrounding-text change. Sets the kitty expectation.
- url: https://wiki.hyprland.org/Configuring/Variables/
  why: AQ_NO_KMS_REQUIREMENT / AQ_DRM_DEVICES aquamarine env vars for headless boot
        (variant 2 of the ladder).
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/ime/            # the transport under test (READ-ONLY): protocol.py wlwire.py
                             # ime_host.py manager.py target.py takeover.py
tests/                       # S1's G3 harness (landing in parallel; READ-ONLY for S2):
                             # ime_g3_support.py ime_g3_field_gtk.py ime_g3_lab.py
                             # test_ime_g3_support.py  + the ime_*_lab.py precedent labs
tools/im-lab/                # the measured evidence (READ-ONLY): imlab_run.py field_term.py
                             # field_gtk.py hypr_nest.py globals.py README.md
plan/008_a47116bb2b79/architecture/{d2_bulk_delivery_map.md, g2_gate_record.md,
                             g3_gtk_rows.md (S1's)}
```

### Desired Codebase tree with files to be added

```bash
tests/
├── ime_g3_matrix_support.py   # NEW — pure: probe-outcome model, classifier, ladder data,
│                              #         route-table derivation, matrix report renderer
├── ime_g3_field_term.py       # NEW — readline witness (fork of tools/im-lab/field_term.py)
├── ime_g3_matrix_lab.py       # NEW — env-gated live runner: boot + T1-T5 + verdicts
└── test_ime_g3_matrix_support.py  # NEW — collected pure unit tests
plan/008_a47116bb2b79/architecture/
└── g3_field_matrix.md         # NEW — the refreshed matrix + route table (DOCS deliverable)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL (AGENTS.md): TWO timeouts on every non-trivial command — inner GNU `timeout`,
#   outer bash-tool `timeout` above it. Live gate: inner 420, outer 480. pytest: 120/180.
#   voicectl never needed here — this task never talks to the daemon at all.
# CRITICAL: drive TERMINAL rows via ImeProcess.request("show", before=…, text=…) at the
#   HOST level. ImeTarget.acquire() refuses "no surrounding text" and ImeTarget.show()
#   refuses "not acquired" — that is BY DESIGN (R.3 fail-before-delivery policy), not a bug
#   to work around. The host's _show needs only activation.
# CRITICAL: capability findings are MEASUREMENTS, not failures. ghostty insert not
#   delivered, kitty delete ignored, Hyprland boot failure → recorded branches / blocked
#   rows. Exit 1 ONLY on: infra failure (terminal never ready, host wedge/unavailable
#   mid-row), an outcome OUTSIDE the pre-declared legal set (garbled/doubled/partial
#   buffer = harness bug), or a global-invariant violation. Do NOT write assertions that
#   "correct must work" — that flunks the expected kitty row and tempts result-fudging.
# CRITICAL: /tmp is a 32 GB tmpfs (= RAM). All scratch in ONE TemporaryDirectory; term.json
#   2000-write cap; host event log 64 KiB (EventLogWriter); hypr.err heads ≤400 B; verdicts
#   one line/row. Teardown via killpg + the TemporaryDirectory context manager.
# GOTCHA: the SWAY parent needs WLR_BACKENDS=x11 + WLR_LIBINPUT_NO_DEVICES=1 (the proven
#   recipe) — but that value MUST NOT leak into the nested Hyprland env (aquamarine has no
#   x11 backend; drm/headless/wayland only). Build hypr_env as a fresh dict that explicitly
#   del/overrides WLR_BACKENDS per ladder variant. WLR_RENDERER/WLR_BACKENDS are unreferenced
#   in aquamarine (upstream-verified) — harmless but not the lever people think it is.
# GOTCHA: hyprctl inside the lab MUST carry --sig <private HYPRLAND_INSTANCE_SIGNATURE> —
#   a bare `hyprctl` talks to the operator's LIVE instance (isolation breach). The S1 grep
#   gate forbade hyprctl entirely; S2's gate allows ONLY the --sig-scoped form.
# GOTCHA: one IM per seat — the matrix lab's ime_host is the seat's only input method.
#   Terminals come and go within one seat without colliding, but NEVER spawn a second host
#   into the same WAYLAND_DISPLAY. An `unavailable` event → host exits 0 → row
#   passed:null ("untested (infra)"), never a false pass. The Hyprland-row host binds to
#   the HYPRLAND socket, not sway's (hypr_nest.py:31-37 precedent).
# GOTCHA: kitty 0.51 dropped X11 — spawn it exactly as im-lab did (plain wayland); if a
#   terminal fails to activate text-input, that IS the measurement (record branch, don't
#   "fix" spawn args beyond the proven recipe without recording why).
# GOTCHA: UTF-8 byte math for the correct probe: len(" im".encode("utf-8")) == 3 — before=
#   takes BYTES not chars (ime_host passes it straight to delete_surrounding_text).
# GOTCHA: legal-outcome sets keep the harness honest: e.g. after the kitty correct probe the
#   buffer must equal "hello fromv2" (delete applied) OR "hello from imv2" (ignored) —
#   anything else (e.g. "hello fromv2" with a doubled fragment, mojibake) fails the row.
# GOTCHA: don't re-run GTK rows (S1 owns them — cite g3_gtk_rows.md), don't re-run route
#   discovery (R.4), don't exercise clipboard anywhere (M5.T3's territory), don't claim G5
#   timing (t_ms is mechanism-level info only).
# GOTCHA: S1's files are LANDING IN PARALLEL — never edit them; import only the pure
#   `tests/ime_g3_support.py` (ROW_STATUSES, RowVerdict, build_payloads, single_edit_analysis)
#   and SPAWN `tests/ime_g3_field_gtk.py` (Hyprland row). Fork the boot skeleton; if S1's
#   module names shifted, mirror whatever its PRP's PRODUCES section names.
```

## Implementation Blueprint

### Data models and structure

```python
# tests/ime_g3_matrix_support.py — pure stdlib, importable by venv tests and the lab

# re-export/reuse from S1's pure module (import, never edit):
#   ROW_STATUSES, RowVerdict, build_payloads, single_edit_analysis

TERM_PAYLOADS = {                      # small, proven, ASCII-first + one Unicode probe
    "insert_ascii": "hello from im",   # the im-lab string — keeps rows comparable
    "insert_unicode": "Zoë — naïve 日本語 🫡",   # byte-math sanity, no combining-mark traps
    "correct_delete": " im", "correct_replacement": "v2",
}
LEGAL_TERM_OUTCOMES = {                # the closed branch sets (probe invariants)
    "insert":  {"delivered", "not_delivered"},
    "correct": {"delete_applied", "delete_ignored"},
    "activate": {"activated", "not_activated"},
    "surround": {"sent", "never_sent"},
}

@dataclass(frozen=True)
class TermProbeOutcome:
    terminal: str          # "foot" | "kitty" | "ghostty"
    version: str           # live-captured, e.g. "kitty 0.51.0"
    activate: str          # LEGAL_TERM_OUTCOMES["activate"]
    insert: str
    correct: str | None    # None when the insert probe measured not_delivered (skip-deps)
    insert_unicode_roundtrip: bool | None
    surround: str          # from host acquire reason / event log
    t_ms: dict | None      # mechanism-level only

def term_row_status(o: TermProbeOutcome) -> str:
    # not_activated or insert not_delivered -> "blocked (<branch> at <version> — IM route
    #   unavailable for this class; evidence link)"
    # insert delivered + correct delete_applied + surround sent -> "verified (<version> +
    #   evidence)"  (the day a terminal ships full support)
    # insert delivered + (correct delete_ignored or surround never_sent) ->
    #   "insert-only (<version> + evidence)"   # THE expected foot/kitty shape
    # closed vocabulary only — every output starts with a ROW_STATUSES word

@dataclass(frozen=True)
class HyprlandAttempt:
    variant: str           # "nested-wayland" | "aq-headless" | "legacy-x11"
    env: dict              # the exact env dict (serializable, sorted for the report)
    booted: bool
    err_head: str          # ≤400 B of hypr.err when not booted
    rows_measured: dict | None   # insert/correct/preedit/surround outcomes when booted

def hypr_row_status(a_list: list[HyprlandAttempt]) -> str:
    # any booted -> verdict from rows_measured ("verified …" | "insert-only …" | honest fail)
    # all failed -> "blocked (nested Hyprland: <first err head> @ <variants tried>)"

def derive_route_table(term_rows: list[TermProbeOutcome], hypr: str,
                       gtk_rows_ref: str) -> dict:
    # THE OUTPUT the item demands — pure, unit-tested:
    # {"field_classes": {
    #    "gtk":  {"route": "im-v2 full", "evidence": gtk_rows_ref},   # S1's report
    #    "foot": {"route": "im-v2 insert-only" | "im-v2 full" | "blocked",
    #             "corrections": "cooperating-editor seam (M5.T1)"},
    #    "kitty": {...}, "ghostty": {"route": "im-v2 insert-only" if insert delivered
    #             else "clipboard insert-fallback (R.6)", ...}},
    #  "clipboard_fallback_m5t3": "needed (ghostty-class insert blocked at <ver>)"
    #                              | "skip (ghostty insert works over IM at <ver>; evidence)",
    #  "hyprland_relay": hypr}
MAX_MATRIX_REPORT_LINES = 150
def render_matrix_report(versions: dict, term_rows: list, hypr_attempts: list,
                         route_table: dict, meta: dict) -> str:
    # header (date, HEAD, LIVE versions incl. pacman -Q line), the matrix table
    # (field | measured version | status | key evidence), Hyprland ladder outcomes,
    # route table verbatim, capped verbatim excerpts, the banner
    # "a G2/lab pass never marks a row verified", open items. Hard cap 150 lines.
```

```python
# tests/ime_g3_field_term.py — fork of tools/im-lab/field_term.py (56 lines), lineage
# docstring citing it + the 2026-11-22 evidence run. Same behavior: GNU readline, 5 ms
# poll thread, {line, seq, t} atomic dump (term.tmp + os.replace), MAX_DUMPS=2000 cap,
# term.ready flag, term.final at EOF. NO new fields needed — the schema is the contract.
```

```python
# tests/ime_g3_matrix_lab.py — GATE_ENV = "IME_G3_MATRIX_LAB"; without it: usage, exit 2.
# Two-phase re-exec mirroring S1's tests/ime_g3_lab.py (itself mirroring ime_correction_lab):
#   OUTER: TemporaryDirectory -> re-exec [sys.executable, __file__, "run", root] under
#     `xvfb-run -a dbus-run-session --config-file=<private dbus conf>` with
#     HOME=XDG_RUNTIME_DIR=TMPDIR=root, WLR_BACKENDS=x11, WLR_LIBINPUT_NO_DEVICES=1,
#     WLR_RENDERER=pixman, LIBGL_ALWAYS_SOFTWARE=1 (inner guard: root==HOME==XDG_RUNTIME_DIR
#     and WLR_BACKENDS=="x11").
#   INNER: sway.conf ("xwayland disable\nfocus_follows_mouse no"); spawn sway; poll for
#     sway-ipc sock + wayland-* socket; spawn ONE ImeProcess (event_log=<root>/ime_host.jsonl)
#     with cwd=repo root; then rows:
#     T1-T3 per terminal (foot/kitty/ghostty, spawn args per research §2):
#       spawn [term…, sys.executable, tests/ime_g3_field_term.py, root] (start_new_session);
#       wait term.ready (8 s) else verdict untested(infra) + err head; focus via sway
#       criteria; activation probe (host events "activate" within 4 s — pump pings);
#       acquire probe (record reason); insert probe show(before=0, text=insert_ascii) ->
#       wait term.json line == payload (4 s) => branch; unicode insert probe likewise;
#       correct probe ONLY if insert delivered: show(before=len(" im".encode()),
#       text="v2") -> line must equal "hello fromv2" | "hello from imv2" => branch;
#       preedit diagnostic (preedit+endpreedit; assert app seq unchanged); killpg term.
#     T4 Hyprland ladder (research §4): fresh env per variant (NO WLR_BACKENDS=x11 leak);
#       poll hypr/<sig>/.wl_socket (25 s); on boot: hyprctl --sig focuswindow, spawn S1's
#       tests/ime_g3_field_gtk.py (system python3) against the HYPR socket, spawn a SECOND
#       ImeProcess bound to WAYLAND_DISPLAY=hypr/<sig>/.wl_socket, run insert/correct/
#       preedit/surrounding probes (single_edit_analysis from ime_g3_support for edit
#       counting); record HyprlandAttempt. On failure: err head, next variant.
#     T5 optional passive registry: run tools/im-lab/globals.py against the LIVE socket
#       ONLY if env IME_G3_MATRIX_LIVE_REGISTRY=1 is set (default OFF; document posture).
#   Global invariants at summary: zero grab_key in all host event logs; every verdict's
#   outcome fields ∈ their legal sets; verdicts.jsonl + stdout mirror; SystemExit(1) iff
#   any passed is False (infra/assertion); finally: teardown (hosts .stop(), sway killpg,
#   terms killpg, TemporaryDirectory exit).
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE tests/ime_g3_matrix_support.py
  - IMPLEMENT: TERM_PAYLOADS, LEGAL_TERM_OUTCOMES, TermProbeOutcome, term_row_status(),
    HyprlandAttempt, hypr_row_status(), derive_route_table(), render_matrix_report()
    (MAX_MATRIX_REPORT_LINES hard cap), version-string helper.
  - FOLLOW pattern: S1's tests/ime_g3_support.py (frozen dataclasses, closed vocab,
    report renderer shape); import ROW_STATUSES/RowVerdict/build_payloads from it.
  - NAMING: terminal names exactly "foot"|"kitty"|"ghostty"; statuses from ROW_STATUSES
    only; the route-table key "clipboard_fallback_m5t3" verbatim (M5.T3's PRP greps it).
  - PURITY: stdlib only (json/dataclasses/pathlib); no gi/wayland/pytest imports.
  - PLACEMENT: tests/ime_g3_matrix_support.py.

Task 2: CREATE tests/test_ime_g3_matrix_support.py
  - IMPLEMENT: classifier matrix — every (activate, insert, correct, surround) combo maps
    to a closed-vocab status; insert-only shape for the foot/kitty expectation; blocked
    shapes for the ghostty expectation; route-table derivation: ghostty not_delivered ->
    "needed", ghostty delivered -> "skip (…)", kitty surprise-full -> route upgrade;
    hypr_row_status over booted/all-failed ladders; renderer ≤150 lines under a stress
    input; determinism; legal-set closure (every LEGAL_TERM_OUTCOMES value covered).
  - FOLLOW pattern: tests/test_g2_bulk_gate.py (sys.path insert, plain asserts, tmp_path).
  - PLACEMENT: tests/test_ime_g3_matrix_support.py. MUST be collected by plain pytest.

Task 3: CREATE tests/ime_g3_field_term.py
  - IMPLEMENT: verbatim fork per the data-model block; module docstring cites lineage
    ("fork of tools/im-lab/field_term.py; im-lab evidence 2026-11-22").
  - VERIFY: atomic dump (tmp+replace) and the 2000-write cap behave (unit-testable by
    import with a stubbed readline if cheap — else assert by inspection + lab smoke).
  - PLACEMENT: tests/ime_g3_field_term.py (spawned by the lab under each terminal).

Task 4: CREATE tests/ime_g3_matrix_lab.py
  - IMPLEMENT: boot per the data-model block (fork S1's skeleton; lab.spawn
    start_new_session=True; err_head helper; until() bounded polls).
  - IMPLEMENT rows T1-T4 (+T5 behind IME_G3_MATRIX_LIVE_REGISTRY=1, default off): probe
    sequence, branch recording, skip-deps (no correct probe when insert not delivered),
    per-row killpg, host ping-pumps around every wait.
  - ASSERT global invariants at summary; write verdicts.jsonl; exit 0/1/2 semantics.
  - EVIDENCE: <root>/verdicts.jsonl; ime_host.jsonl (manager's capped log); hypr.err
    heads embedded in verdicts; OPTIONAL grim screenshot sha256[:16] per row when present.
  - PLACEMENT: tests/ime_g3_matrix_lab.py. MUST NOT be pytest-collected (no test_ prefix).

Task 5: RUN the live gate + WRITE plan/008_a47116bb2b79/architecture/g3_field_matrix.md
  - RUN: `timeout 420 env IME_G3_MATRIX_LAB=1 .venv/bin/python tests/ime_g3_matrix_lab.py`
    (bash timeout 480).
  - WRITE (render via render_matrix_report, then hand-finish): live versions (pacman -Q
    foot kitty ghostty hyprland sway gtk4 verbatim + binary --version outputs), the matrix
    table citing S1's g3_gtk_rows.md for GTK rows, Hyprland ladder outcomes with error
    heads, the route table with the M5.T3 decision, capped evidence excerpts, the banner,
    open items (e.g. ghostty 1.5.0 watch: PR #15246 is milestone 1.5.0 — retest then).
  - BOUND: ≤150 lines enforced by the renderer; do not hand-expand past the cap.
```

### Implementation Patterns & Key Details

```python
# The terminal-row probe skeleton (T2 kitty shown; T1/T3 differ only in spawn args/app_id):
spawn_args, app_id = ["kitty", "--class", "imlab-kitty"], "imlab-kitty"   # im-lab recipe
for f in ("term.json", "term.final", "term.ready"):
    (root / f).unlink(missing_ok=True)
proc = lab.spawn(spawn_args + [sys.executable, str(REPO / "tests/ime_g3_field_term.py"),
                               str(root)], stderr_name="term-kitty.err")
if not until(lambda: (root / "term.ready").exists(), 8):
    lab.verdict("kitty", passed=None, checks=("term never ready",),
                stderr=lab.err_head("term-kitty.err")); killpg; next row
lab.focus(f'[app_id="{app_id}"]')
base = host_event_count()
activated = wait_host_event("activate", 4)            # pump pings while waiting (adapter-api §3)
acq = proc_ime.request("acquire", timeout=3)          # reason ∈ {"no surrounding text", "not activated", …}
r = proc_ime.request("show", before=0, text=TERM_PAYLOADS["insert_ascii"], timeout=3)
got = wait_term_line(lambda s: s and s.get("line") in
                     (TERM_PAYLOADS["insert_ascii"], ""), 4)   # BOTH branches legal
insert = "delivered" if got and got["line"] == TERM_PAYLOADS["insert_ascii"] else "not_delivered"
# unicode insert probe likewise; then (only if insert delivered):
r = proc_ime.request("show", before=len(" im".encode()), text="v2", timeout=3)
got = wait_term_line(lambda s: s and s.get("line") in ("hello fromv2", "hello from imv2"), 4)
correct = "delete_applied" if got and got["line"] == "hello fromv2" else "delete_ignored"
# Any OTHER line value (garbled/doubled/mojibake) => wait times out => row FAILED (assert)
# Hyprland variant env (T4) — the fix vs hypr_nest.py:146-155:
hypr_env = {**seat_env_minus_wl_backends,            # explicit del WLR_BACKENDS/WLR_RENDERER
            "WAYLAND_DISPLAY": sway_socket, "XDG_CURRENT_DESKTOP": "Hyprland",
            "WLR_RENDERER": "pixman", "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_SHADER_CACHE_DISABLE": "true"}     # variant 2 adds AQ_NO_KMS_REQUIREMENT=1
# On boot: sig = hypr/<sig>/.wl_socket; hyprctl --sig <sig> dispatch focuswindow class:…
# (NEVER a bare hyprctl — the audit gate enforces --sig on every occurrence).
```

### Integration Points

```yaml
CONSUMES (READ-ONLY):
  - voice_typing/ime/manager.py ImeProcess   # the product transport driven at host level
  - voice_typing/ime/ime_host.py commands    # acquire/show/verify (reason strings = evidence)
  - tests/ime_g3_support.py (S1)             # ROW_STATUSES, RowVerdict, payloads, oracle
  - tests/ime_g3_field_gtk.py (S1)           # spawned by the Hyprland row (system python3)
  - tools/im-lab/globals.py                  # spawned by T5 only (passive registry)
  - plan/008_a47116bb2b79/architecture/g3_gtk_rows.md (S1)  # cited as the GTK-class rows
PRODUCES:
  - plan/008_a47116bb2b79/architecture/g3_field_matrix.md — the refreshed matrix + route
    table; P1.M5.T3's PRP cites "clipboard_fallback_m5t3" from it; P1.M7.T1 reads it for G6.
DOES NOT TOUCH:
  - voice_typing/**, tools/im-lab/**, S1's four files, every existing test, config.toml,
    pyproject.toml, tests/ACCEPTANCE.md, tasks.json, PRD/plan read-only docs, the operator's
    live session (except the optional passive registry listing behind its own env flag).
```

## Validation Loop

### Level 1: Syntax & Style (immediate)

```bash
ruff check tests/ime_g3_matrix_support.py tests/ime_g3_field_term.py \
  tests/ime_g3_matrix_lab.py tests/test_ime_g3_matrix_support.py --fix
ruff format tests/ime_g3_matrix_support.py tests/ime_g3_field_term.py \
  tests/ime_g3_matrix_lab.py tests/test_ime_g3_matrix_support.py
# Expected: zero errors (ruff is the repo's gate; no mypy config).
```

### Level 2: Unit Tests (compositor-free)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_matrix_support.py -q
# (bash tool timeout 180.)

# Zero regression across the adapter + G3 surfaces (include S1's suite once landed):
timeout 180 .venv/bin/python -m pytest tests/test_ime_matrix_support.py \
  tests/test_ime_g3_support.py tests/test_ime_takeover.py tests/test_ime_host.py \
  tests/test_ime_protocol.py tests/test_ime_target.py tests/test_ime_wlwire.py \
  tests/test_ime_manager.py tests/test_bulk_delivery.py tests/test_bulk_controller.py \
  tests/test_g2_bulk_gate.py -q
# (bash tool timeout 240.) Expected: all green — this task added files only.
```

### Level 3: The live matrix gate (the deliverable's proof)

```bash
# ONE run, private disposable desktop; ~2–6 min (boot ~15 s + 3 terminal rows ~30 s +
# Hyprland ladder ≤3×25 s + Hyprland rows if booted):
timeout 420 env IME_G3_MATRIX_LAB=1 .venv/bin/python tests/ime_g3_matrix_lab.py
# (bash tool timeout 480.)
# Expected: exit 0 with every row MEASURED — including blocked/unavailable branches
# (ghostty not-delivered and a failed Hyprland ladder are SUCCESSFUL measurements).
# Exit 1 -> read the failed row's checks + term.json/err tail: that is an infra or
# out-of-legal-set failure — a harness bug, fix and re-run. Exit 2 -> gate/env misuse.
# THEN write plan/008_a47116bb2b79/architecture/g3_field_matrix.md from this run (Task 5).
# If a run wedges: inner timeout returns 124; the TemporaryDirectory removes scratch on the
# way out; confirm `pgrep -f 'ime_g3_matrix|sway|Hyprland'` is empty before re-running.
# NEVER run against the operator's session; T5's live-registry flag stays unset by default.
```

### Level 4: Contract audit (grep-provable invariants)

```bash
# Isolation — no live-desktop/service/clipboard surface (hyprctl allowed ONLY --sig-scoped):
grep -nE "voicectl|systemctl|pactl|wl-copy|wl-paste" tests/ime_g3_matrix_lab.py \
  tests/ime_g3_field_term.py tests/ime_g3_matrix_support.py || echo "ok: isolated"
grep -Pn 'hyprctl(?![^\n]*--sig)' tests/ime_g3_matrix_lab.py || echo "ok: hyprctl sig-scoped"
# Report bounds + banner + closed vocabulary:
grep -c "" plan/008_a47116bb2b79/architecture/g3_field_matrix.md   # <= 150
grep -n "G2/lab pass never" plan/008_a47116bb2b79/architecture/g3_field_matrix.md
grep -oE "untested|insert-only|blocked|verified" \
  plan/008_a47116bb2b79/architecture/g3_field_matrix.md | sort | uniq -c
# Route-table decision present and machine-greppable:
grep -n "clipboard_fallback_m5t3" plan/008_a47116bb2b79/architecture/g3_field_matrix.md
# Read-only discipline — the adapter, evidence records, and S1's files untouched:
git status --porcelain   # ONLY the five new files (plus the report once written)
# Scratch gone:
ls /tmp | grep -c "ime_g3_matrix" || true   # no leftover harness dirs
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1 ruff clean; Level 2 both suites green; Level 3 exit 0; Level 4 greps clean.
- [ ] `git status --porcelain` shows only the five new files.

### Feature Validation

- [ ] foot / kitty / ghostty rows measured at live-captured installed versions with every
      branch from the closed legal sets; skip-deps honored (no correct probe after a
      not-delivered insert).
- [ ] Hyprland row measured on a booted isolated instance OR recorded `blocked (reason)`
      with error heads per variant — never silently skipped; the ladder tried ≥2 variants.
- [ ] Route table derives the M5.T3 decision from measured branches via the unit-tested
      pure function; the report cites S1's GTK rows rather than re-running them.
- [ ] Report: closed vocabulary, live versions, ≤150 lines, G2-never banner, open items
      (incl. the ghostty 1.5.0 watch from upstream-changelog-drift.md).
- [ ] Zero grab_key events; no full-dictation sequence anywhere on insert-only rows;
      terminal verification app-side only.

### Code Quality Validation

- [ ] Support module pure stdlib; field-term fork cites lineage; the lab forks S1's boot
      skeleton rather than inventing a new pattern; S1's files imported/spawned, never edited.
- [ ] Scratch bounded everywhere; teardown verified by a clean re-run.
- [ ] Anti-patterns below avoided.

### Documentation & Deployment

- [ ] Module docstrings carry lineage + evidence citations (im-lab 2026-11-22; d2 map §5/§6;
      upstream-changelog-drift.md).
- [ ] The matrix report records versions and evidence; no config/env changes anywhere.

## Anti-Patterns to Avoid

- ❌ Don't assert capability outcomes ("correct must work") — assert the probe measured a
      LEGAL branch; a blocked row is a result, not a failure (the item says so explicitly).
- ❌ Don't drive terminal rows through `ImeTarget` — it refuses by design; use host-level
      `proc.request("show", …)`. Don't "fix" the adapter to make terminals verifiable.
- ❌ Don't run insert-only rows as full dictation, and don't let IM-side `verify` masquerade
      as terminal text verification — app-side `term.json` is the only terminal witness.
- ❌ Don't touch `voice_typing/**`, `tools/im-lab/**`, S1's files, or existing tests; don't
      re-run route discovery or GTK rows; don't exercise the clipboard (M5.T3's scope).
- ❌ Don't run anything against the live desktop; a bare `hyprctl` is an isolation breach
      (`--sig` only); the passive registry listing is opt-in behind its own env flag and
      never flips a row's status.
- ❌ Don't leak `WLR_BACKENDS=x11` into the nested Hyprland env (aquamarine has no x11
      backend — that's the recorded failure's probable root cause).
- [ ] Don't claim G5 timing; t_ms is mechanism-level info. Don't paper over which branch
      occurred — the report's value IS the honest branch.
- [ ] Don't let one row's failure kill the run (per-row try/except → `passed: null`), and
      don't treat `null` as a pass; don't write unbounded scratch under /tmp (tmpfs = RAM).

---

## Confidence Score

**9/10** — every structural input is proven: the terminal-row recipe ran green in im-lab
(29 rows / 24 pass at this exact boot); the host-transport surface is landed and unit-pinned
(ime_host `_show` needs only activation; `_acquire`'s reason strings are documented); S1's
pure seams (support module + GTK field app) are contract-fixed and consumed read-only; the
Hyprland failure now has an identified root cause (inherited `WLR_BACKENDS=x11` vs
aquamarine's drm/headless/wayland-only backends — upstream-verified) plus a documented
headless fallback (`AQ_NO_KMS_REQUIREMENT=1`); and upstream changelog research sets honest
expectations (ghostty NOT-FIXED at 1.4.0, kitty no-op confirmed at source level) that the
harness measures rather than assumes. Residual risks: (1) S1 lands with different file
names/signatures than its PRP — mitigated by consuming only the two lowest-coupling seams
and forking the boot; (2) the nested Hyprland boot may still fail on this GPU box even with
the right backend env — recording `blocked (reason)` is an explicitly legitimate deliverable;
(3) terminal spawn quirks at new versions (kitty 0.51 dropped X11 — irrelevant on the
Wayland seat, and the im-lab recipe is re-used verbatim).

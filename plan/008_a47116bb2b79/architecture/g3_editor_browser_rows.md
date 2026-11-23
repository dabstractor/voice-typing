G3 editor + browser row report — TextView + Chromium text field, IM-v2 (P1.M5.T2.S2)

- Date: 2026-11-23  |  HEAD: 4fc3f9b
- Command: `timeout -k 2 420 env IME_G3_EDITOR_BROWSER_LAB=1 .venv/bin/python tests/ime_g3_editor_browser_lab.py`
- chromium: Chromium 158.0.8127.36 Arch Linux
- chromium_flags: --ozone-platform=wayland --enable-wayland-ime --wayland-text-input-version=3 --user-data-dir=<temp root> --no-first-run --no-default-browser-check --disable-gpu --password-store=basic
- firefox: Mozilla Firefox 160.0.1
- firefox_flags: MOZ_ENABLE_WAYLAND=1 --profile <temp root> (contingency only)
- kernel: 7.2.7-arch1-1
- sway: sway version 1.12
- gtk: 4.24.1
- pygobject: 3.58.1
- pacman_gtk4: 1:4.24.1-1
- pacman_sway: 1:1.12-4

> **A G2 pass never marks a row verified.** Only this harness's
> field-side witnesses (frame oracle + dump + verify) verify a row,
> and only with live versions attached. t_ms values are
> mechanism-level info, NEVER G5 timing (no speech in this run).

| row | pass | status |
|---|---|---|
| editor-overcap-4500b (capability sub-row) | null | 4000-byte commit cap — refused by design; chunking vs R.1 one-edit rule undecided |
| browser-overcap-4500b (capability sub-row) | null | 4000-byte commit cap — refused by design; chunking vs R.1 one-edit rule undecided |
| editor-short-updates | true | insert-only |
| editor-firstword-20sent | true | verified (versions + evidence) |
| editor-identical-finals | true | verified (versions + evidence) |
| editor-long-unicode | true | insert-only |
| editor-refusing-readonly | true | blocked (refuses at activation by toolkit/browser design — the expected refusing branch: activation-refused (non-editable view never enabled text-input); recovery insert verified) |
| editor-takeover | true | verified (versions + evidence) |
| browser-short-updates | true | insert-only |
| browser-firstword-20sent | true | insert-only |
| browser-identical-finals | true | insert-only |
| browser-long-unicode | true | insert-only |
| browser-refusing-readonly | true | blocked (refuses at activation by toolkit/browser design — the expected refusing branch: acquire-refused (not activated); recovery insert verified) |
| browser-takeover | true | verified (versions + evidence) |
| CLASS graphical-editor | null | verified (versions + evidence) |
| CLASS browser-text-field | null | insert-only (correction REFUSED (recheck: caret moved) — the surrounding_text snapshot lags the committed value at this chromium, so the adapter's owned-region precheck cannot confirm) |

## editor-overcap-4500b (capability sub-row) — >4000 B delivery capability
  refused pre-wire, never chunked; field untouched

## browser-overcap-4500b (capability sub-row) — >4000 B delivery capability
  refused pre-wire, never chunked; field untouched (Δn=0)

## editor-short-updates — 6 short inserts into the TextView
  pass=True
  t_ms=200 (mechanism-level, never G5)

## editor-firstword-20sent — 20-sentence span + FIRST-word correction
  pass=True
  t_ms=44 (mechanism-level, never G5)
  recheck=ok

## editor-identical-finals — same final ×3 — zero-diff ⇒ zero events
  pass=True
  t_ms=1 (mechanism-level, never G5)
  results=['UNCHANGED', 'UNCHANGED', 'UNCHANGED']

## editor-long-unicode — 951 B unicode + 3.5 KB mixed; >4 KB refused
  pass=True
  t_ms=156 (mechanism-level, never G5)
  subrows=[('unicode-951b', 'ok'), ('mixed-3500b', 'ok'), ('overcap-4500b', 'refused-by-design')]

## editor-refusing-readonly — non-editable view refuses; recovery insert
  pass=True
  t_ms=9169 (mechanism-level, never G5)
  branch=activation-refused (non-editable view never enabled text-input)
  recovery=APPLIED

## editor-takeover — real key mid-owned-fragment → exactly ONE halt
  pass=True
  t_ms=1983 (mechanism-level, never G5)
  injector=xdotool
  grab_key_events=2
  halt_reasons=['user key 57']
  watch_reason=user key 57
  post_takeover=REFUSED

## browser-short-updates — 6 short inserts into the DOM input
  pass=True
  t_ms=744 (mechanism-level, never G5)
  channel=push
  op1_law={'dn': 1, 'transitions': 1, 'transient': [], 'painted_final': True, 'underflow': False}
  op2_law={'dn': 1, 'transitions': 1, 'transient': [], 'painted_final': True, 'underflow': False}
  op3_law={'dn': 1, 'transitions': 1, 'transient': [], 'painted_final': True, 'underflow': False}
  op4_law={'dn': 1, 'transitions': 1, 'transient': [], 'painted_final': True, 'underflow': False}
  op5_law={'dn': 1, 'transitions': 1, 'transient': [], 'painted_final': True, 'underflow': False}

## browser-firstword-20sent — 20-sentence span + FIRST-word correction (recorded branch)
  pass=True
  t_ms=494 (mechanism-level, never G5)
  insert_law={'dn': 1, 'transitions': 1, 'transient': [], 'painted_final': True, 'underflow': False}
  recheck=refused (caret moved)
  recheck_note=surrounding_text snapshot lags the committed value at this chromium — the caret guard cannot confirm ownership
  correction_branch=REFUSED (recheck: caret moved)
  correction_note=correction refused — the adapter's owned-region check (_owned_region_intact) needs surrounding_text; the DOM field kept the committed (misspelled) span
  b2_verify_note=one-commit lag MEASURED: snapshot == field value before the last commit

## browser-identical-finals — same applied span ×3 — zero input events
  pass=True
  t_ms=357 (mechanism-level, never G5)
  noop_law={'dn': 0, 'transitions': 0, 'transient': [], 'painted_final': False, 'underflow': False}
  results=['UNCHANGED', 'UNCHANGED', 'UNCHANGED']

## browser-long-unicode — 951 B unicode + 3.5 KB mixed; >4 KB refused
  pass=True
  t_ms=415 (mechanism-level, never G5)
  unicode_law={'dn': 1, 'transitions': 1, 'transient': [], 'painted_final': True, 'underflow': False}
  overcap_law={'dn': 0, 'transitions': 0, 'transient': [], 'painted_final': False, 'underflow': False}
  b4_verify_note=one-commit lag MEASURED: snapshot == field value before the last commit
  subrows=[('unicode-951b', 'ok'), ('mixed-3500b', 'refused-recorded'), ('overcap-4500b', 'refused-by-design')]

## browser-refusing-readonly — <input readonly> refuses; recovery insert
  pass=True
  t_ms=3329 (mechanism-level, never G5)
  branch=acquire-refused (not activated)
  recovery=APPLIED

## browser-takeover — real key mid-owned-fragment; page keydowns frozen
  pass=True
  t_ms=2041 (mechanism-level, never G5)
  injector=xdotool
  grab_key_events=2
  halt_reasons=['user key 57']
  watch_reason=user key 57
  post_takeover=REFUSED

## CLASS graphical-editor — one closed-vocabulary verdict per field class (R.7)
  rows = editor-* (see per-row sections)

## CLASS browser-text-field — one closed-vocabulary verdict per field class (R.7)
  rows = browser-* (see per-row sections)

Summary: editor: verified (versions + evidence); browser: insert-only (correction REFUSED (recheck: caret moved) — the surrounding_text snapshot lags the committed value at this chromium, so the adapter's owned-region precheck cannot confirm); rows=13 pass=13 fail=0 skip=0

Evidence links:
  harness tests/ime_g3_editor_browser_lab.py (rows E1–E6 + B1–B6, takeover legs, injector ladder)
  editor field app tests/ime_g3_field_edit.py (fork of tests/ime_g3_field_gtk.py — the TextView-class document editor)
  browser fixture tests/fixtures/ime_g3_browser_field.html (real DOM input, self-witnessing JS, push + title channels)
  helpers tests/ime_g3_editor_browser_support.py (event-count law, argv builders, class verdicts); unit pins tests/test_ime_g3_editor_browser_support.py
  conventions plan/008_a47116bb2b79/architecture/g3_gtk_rows.md + g3_field_matrix.md; verdicts.jsonl beside this report
Drift notes (PRP-vs-code, recorded honestly):
  - the leg drives ONE real key via xdotool XTEST into sway's X window on the Xvfb display (tools/im-lab/imlab_run.py grab_rows recipe: search --onlyvisible --maxdepth 1 + windowfocus + key) — the injected X events become seat keyboard input through wlroots' x11 backend and arrive as grab_key while the IM holds the grab; wtype is the recorded fallback
  - E4(a)'s post-op dump waits for the commit's PAINTED frame (painted=True) — tightens the harness R4 fork's oracle window (the signal-time dump can precede the paint; determinism fix)
  - B1 drives each short update as ONE acquire + ONE delta-append (per-utterance cadence); the one-acquisition multi-op cadence is B4(b)'s explicit measurement
[… truncated …]
## Open items
- browser correction branch: correction REFUSED (recheck: caret moved) — the surrounding_text snapshot lags the committed value at this chromium, so the adapter's owned-region precheck cannot confirm — feeds P1.M5.T3.S1 clipboard-fallback decision

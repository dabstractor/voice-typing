# G3 GTK row report — real-field IM-v2 matrix (P1.M4.T5.S1)

- Date: 2026-11-23  |  HEAD: 8d8b439
- Command: `timeout 300 env IME_G3_LAB=1 .venv/bin/python tests/ime_g3_lab.py`
- kernel: 7.2.7-arch1-1
- sway: sway version 1.12 (pacman 1:1.12-4)
- gtk: 4.24.1 (pacman 1:4.24.1-1)
- pygobject: 3.58.1

PRD §4.2sexies R.7, G3 bullet (verbatim): "short updates; a 20-sentence
first-word correction; repeated identical finals; long and Unicode payloads;
pane/tab/window switches; a refusing target. Assert editor contents + cursor +
the visible prompt; no transient delete/retype frames … Rows report `untested |
insert-only | blocked (reason) | verified (versions + evidence links)`."

> **A G2 pass never marks a row verified.** Only this harness's
> field-side witnesses (frame oracle + dump + verify) verify a row,
> and only with live versions attached. t_ms values are
> mechanism-level info, NEVER G5 timing (no speech in this run).

| row | pass | status |
|---|---|---|
| gtk-short-updates | true | insert-only |
| gtk-firstword-20sent | true | verified (versions + evidence) |
| gtk-identical-finals | true | verified (versions + evidence) |
| gtk-long-unicode | true | insert-only |
| gtk-overcap-4500b (capability sub-row) | null | blocked (4000-byte commit cap — refused by design; chunking vs R.1 one-edit rule undecided) |
| gtk-refusing-readonly | true | blocked (readonly refuses at activation by toolkit design — the expected refusing branch; adapter recovery verified) |

## gtk-short-updates — 6 short inserts — growing span, INSERT path, delta-only wire
  oracle (op6 window): frames=3 transitions=1 transient=[] painted_final=true
  dones deltas per op: 1,2,3,1,2,2 (GTK acks 1–3 done events per commit cycle; zero-side pinned in R3/R4c)
  target-confirmed verify: 48 B == field, byte-exact; cseq delta in (1,2) every op
  t_ms=424 whole row (mechanism-level, never G5)

## gtk-firstword-20sent — 20-sentence span (~1544 B) inserted, FIRST word corrected in ONE commit
  CORRECTION path: delete_surrounding(before=1544) + commit_string + ONE wire commit
  oracle (correction window): frames=2 transitions=1 transient=[] painted_final=true — no delete/retype frame
  pre-op recheck ok (caret + owned region verified before the wire); reach 1544 B ≫ one utterance
  target-confirmed verify: 1592/1592 B byte-exact; t_ms=44 (mechanism-level, never G5)

## gtk-identical-finals — same final span show()n 3× — the zero-diff law on a real field
  shares R2's acquisition on purpose: the zero-diff guard compares against the
  CORRECTED final, so this row is only meaningful inside R2's insert+correct
  cycle (exercised_correction=true reflects that shared binding, not a
  correction performed by this row's own ops)
  results: UNCHANGED × 3; host dones 17 → 17 (ZERO wire commits)
  oracle: frames=0 transitions=0 (idle clock painted nothing — no-op tolerant PASS)
  field cseq unchanged across all three repeats

## gtk-long-unicode — 951 B multilingual + ~3.5 KB mixed inserts; >4 KB refused
  unicode-951b: byte-exact 951 B (CJK+accents+emoji+combining), APPLIED, oracle clean
  mixed-3500b: byte-exact extension, APPLIED, oracle clean (UTF-8 boundary round-trip)
  overcap-4500b: delta 4500 B > cap → REFUSED before the wire; field untouched (cseq/frames/text/dones)
  verify: snapshot window 3999 B < field 6043 B — GTK caps surrounding_text near the cursor; SUFFIX agreement verified
  t_ms=137 (mechanism-level, never G5)

## gtk-overcap-4500b (capability sub-row) — >4000 B delivery capability
  behavior assertion PASSES (refused, never chunked, field untouched); capability itself undecided upstream

## gtk-refusing-readonly — field app booted --readonly — the refusing target
  focus proven: focused window == 'imlab-g3-field-gtk-ro'
  ACTUAL branch recorded: activation-refused (readonly entry never enabled text-input)
  NO visible edit, keys==0; recovery: fresh writable field, acquire + insert → APPLIED (adapter not wedged)
  t_ms=9115 incl. the bounded 8 s activation window (mechanism-level, never G5)

## global invariants (whole run)
  host event log: ZERO `grab_key` events — IM commits generate zero key events;
  delivery cannot self-trigger takeover (re-pins T4's O2 seam)
  every field dump: received-keys == 0, activate (Enter) == 0 — no submission,
  no shortcut execution
  teardown clean: ImeProcess.stop + killpg of our own session groups only;
  TemporaryDirectory removed the disposable root (no /tmp leftovers)

Evidence links: harness `tests/ime_g3_lab.py` (rows R1–R5), field app
`tests/ime_g3_field_gtk.py` (fork of `tools/im-lab/field_gtk.py`, im-lab
evidence run 2026-11-22, 29 rows / 24 pass), oracle + payload/status logic
`tests/ime_g3_support.py`, unit pins `tests/test_ime_g3_support.py`. Private
disposable desktop: xvfb-run + private dbus + sway x11 backend; the live
desktop, real clipboard, default microphone, and the active service are never
touched (no voicectl/systemctl-equivalent anywhere in the harness).

Summary: 6 verdicts (5 rows + global invariants) — ALL PASS; exit 0; teardown clean (killpg + TemporaryDirectory)

## Open items
- R.7 G3: preedit transition rows NOT covered here (S2 field-class matrix scope)
- R.1 policy: >4 KB chunking vs one-edit rule UNDECIDED — over-cap stays REFUSED
- Hyprland live-compositor row outstanding (S2/M5 scope) — d2 map §6 drift list
- GTK's ~4 KiB surrounding_text window cap is a per-toolkit constant to re-check
  at drifted versions (S2) — verify agreement degrades to suffix-only past it

# G3 pi-prompt row — real pi in isolated Ghostty (P1.M5.T2.S1)

- Date: 2026-11-23  |  Command: `timeout -k 2 240 env PI_G3_ROW_LAB=1 .venv/bin/python tests/pi_g3_row_lab.py`
- pi: 1.0.2  |  ghostty: Ghostty 1.4.0-arch2 |  sway: sway version 1.12  |  kernel: 7.2.7-arch1-1 |  node: v26.13.1
- Route (matrix-decided, P1.M4.T5.S2): the cooperating-editor seam via S2's PiEditorTarget — ghostty 1.4.0 IM is blocked (activate not_activated); no route discovery re-run, no IM delete, no clipboard (wl-copy/wl-paste absent).
- HOME DELTA vs tools/paste-lab/ghostty_probe.py: HOME stays REAL (pi's node install + ~/.pi are home-resident); XDG_RUNTIME_DIR/XDG_CONFIG_HOME/TMPDIR + all Wayland surfaces are private; pi cwd = a temp project with project-local .pi/extensions/voice-editor.ts copied from the repo.

| row | pass | status | detail |
|---|---|---|---|
| short-insert-1 | True | applied | changes=3 reason= |
| short-insert-2 | True | applied | changes=1 reason= |
| first-word-correction | True | applied | changes=1 reason= |
| zero-diff-repeat | True | unchanged | requests=0 |
| finalize-u1 | True | unchanged | requests=0 |
| cancel-nothing-pending | True | unchanged | requests=0 |
| u2-pending-insert | True | applied | changes=1 reason= |
| cancel-pending | True | applied | changes=1 |
| refuse-range-not-owned | True | refused | reason=range not owned |
| unicode-insert | True | applied | changes=8 reason= |
| unicode-zero-diff | True | unchanged | requests=0 |
| refuse-out-of-bounds | True | refused | reason=out_of_bounds |
| finalize-u3 | True | unchanged | requests=0 |
| long-insert-1kb | True | applied | changes=1 reason= |
| long-word-correction | True | applied | changes=1 reason= |
| focus-switch | True | applied | census 1->2->2 applied changes=1 spurious_takeovers=0 |
| takeover-real-key | True | halt | bridge=2097156 xfocus=True halts=['pi-editor key takeover']  |
| refuse-show-while-dirty | True | refused | reason=dirty mutating_delta=1 |
| refuse-acquire-while-dirty | True | refused | reason=editor dirty |
| refuse-cancel-while-dirty | True | refused | reason=dirty mutating_delta=1 |
| pi-prompt-ghostty | True | not verified (visibility instrumentation absent) | 20/20 traces |

- Visible-prompt instrumentation: ABSENT — the editor's read reply keys are ['changes', 'cursor', 'dirty', 'ok', 'owned', 'result', 'text', 'units']; per-op `changes` pins the edit-count law (applied=1, unchanged=0) at the editor level, but no rendered-prompt dump exists, so the visible-prompt leg is recorded as NOT verified (buffer-state alone can never upgrade it).
- Edit-count-law caveat: the R.1 per-op `changes` assert deviated on 2 step(s): short-insert-1 changes=3; unicode-insert changes=8. Facts that DO hold on every one of them: exactly ONE socket op was sent (requests_delta=1), the extension made ONE buffer-API call, and the witness read back text + caret EXACT with no markers. The onChange counter counts pi's INTERNAL buffer-event granularity (empty-buffer warm-up, CJK/astral font-fallback re-layouts) — every steady-state ASCII op fired exactly 1. Without frame-level instrumentation the single-VISIBLE-edit property is unprovable for these ops — recorded, not excused; the verdict ceiling is not-verified regardless.
- No neighbor changes: private-desktop census ended at 2 leaves (app_ids ['com.mitchellh.ghostty']); the ONLY channels into the desktop were the private socket + one scripted xdotool space into the private seat's bridge window.
- No shortcut execution/submission: buffer held the prose through every step (witness reads), zero newline/Enter ever inserted, per-op changes counts recorded exactly (see the law caveat above), and pi was given NO API key and NEVER sent a message.
- S2 wiring note: the watch is attached WITHOUT target here so the adapter's post-takeover 'editor dirty' refusal path stays exercisable; in production PiEditorTakeoverWatch(controller, target) also clears the binding via leave() (unit-covered in tests/test_pi_editor.py). Measured S1 finding: opInsert has no dirty guard — post-takeover inserts are guarded by the production watch wiring, replaces refuse at the bind read.

t_ms values are mechanism-level info, NEVER G5 timing (no speech in this run).

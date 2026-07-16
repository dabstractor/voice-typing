# Research — README lite-mode sections + ACCEPTANCE.md #10 (P1.M2.T2.S1)

This note pins what is ALREADY documented (a concurrent Mode-A process did most of
it), what is MISSING, the verified implemented behavior (drift prevention), and the
exact edit content. The PRP (../PRP.md) references it as the single source of truth.

## 1. ★ The README is ALREADY largely updated (concurrent Mode-A process) ★

The item warned: "RE-VERIFY what README already says about lite (a concurrent
process may have started it)." Confirmed — the per-file Mode-A doc edits (P1.M1.*)
already landed most of the lite documentation. Status against the item's LOGIC:

| item sub-item | status | where |
|---|---|---|
| (a) `lite_model` in the config table under `[asr]` | ✅ DONE | README `| asr.lite_model | "small.en" | …` row |
| (c) Hotkey section lists BOTH binds + mode behavior | ✅ DONE | README "## Hotkey (Hyprland)" — SUPER+ALT+D normal / SUPER+ALT+F lite, ⚡ prefix, switch cost |
| (b) dedicated short "Lite mode" subsection | ❌ MISSING | (only lite prose is inside Hotkey; no discoverable section) |
| (d) lite note in Model-lifecycle (~half VRAM, idle-unload either mode) | ❌ MISSING | "### Model lifecycle & VRAM" discusses normal mode only |

Plus the status example (`mode: normal` line) + the `mode:` explanation in "Logs,
status, stopping" are already present. So this task is the **cross-cutting
completeness sweep**: add the MISSING (b) + (d), and cross-check ACCEPTANCE.md #10.

## 2. ★ Verified implemented behavior (drift prevention — read from the code) ★

Every fact the docs must state was confirmed against the live source (no drift):

| fact | source (verified) |
|---|---|
| config key `asr.lite_model`, default `"small.en"` | config.py:54 (`lite_model: str = "small.en"`) |
| commands `toggle-lite`, `start-lite` | ctl.py:35 (`_COMMANDS` tuple); main() routes them @197 |
| keybind SUPER+ALT+F → `voicectl toggle-lite` | hypr-binds.conf (bind line) + README Hotkey |
| `mode` IS in state.json (`"normal"` \| `"lite"`) | feedback.py:99 (`_state["mode"]`) + `set_mode` @145; daemon calls `set_mode` @980 |
| `voicectl status` renders `mode:` | ctl.py:88; daemon status_snapshot includes `mode` @1501 |
| tmux ⚡ prefix in lite | status.sh:40 (`(if (.mode == "lite") then "⚡" …)`) |
| mode switch = one ~1–3 s reload | daemon _load_host checks `host.mode` @704/712 (tears+respawns on mismatch) |
| both modes honor graceful drain / auto-stop / idle-unload | PRD §4.2ter (verified by P1.M1.T2); idle-unload: _unload_host re-checks `not _models_loaded` |

**Minor FYI (OUT OF SCOPE here):** feedback.py's docstring *example* (line 11) +
`snapshot()` docstring (line 194) list the state shape WITHOUT `mode` — stale vs
the actual `_state` (which has it @99). That is a per-file Mode-A doc concern owned
by the feedback.py implementing subtask, NOT this README/ACCEPTANCE task. Do NOT
edit feedback.py here.

## 3. What to ADD (the missing pieces)

### 3.1 README — "## Lite mode" subsection (item (b))
Place AFTER "## Hotkey (Hyprland)" (before "## tmux status line"). Concise (~8 lines):
what it is (single `lite_model` for partials+finals; large model never loads), why
(low-latency snippets; ~half VRAM + faster finals, lower accuracy), how to arm
(`toggle-lite`/`start-lite`/SUPER+ALT+F; `stop` disarms either), switch cost (one
~1–3 s reload), what's shared (graceful drain, 30 s auto-stop, idle-unload), where
it shows (`status` `mode:`, `state.json` `mode`, tmux ⚡). Cross-link Hotkey +
Model lifecycle. (The Hotkey section keeps its bind-contextual lite prose; the new
section is the canonical discoverable explanation — minor overlap is intentional.)

### 3.2 README — Model lifecycle lite note (item (d))
In "### Model lifecycle & VRAM", after "...so later arms are instant." add one
sentence: in lite the resident set is just `small.en` (~half normal VRAM);
idle-unload tears down whichever mode is resident; the next arm reloads in
whichever mode that arm requests.

### 3.3 ACCEPTANCE.md — criteria table: add #9 + #10 (item: "add/confirm #10")
The criteria table currently has rows 1–8 ONLY. The evidence block already
references "criteria 5, 6, 8, 9" (so #9's evidence exists, but its TABLE ROW is
missing), and PRD §7 now has #9 (idle-unload) + #10 (lite). Add BOTH rows for a
contiguous 1–10 table (adding #10 alone would leave an 8→10 gap):
- **#9 (idle-unload):** status **PASS** — evidence is the existing T6(d-gone) block.
- **#10 (lite):** status **pending T7** — evidence is the parallel task P1.M2.T1.S1
  (`tests/test_feed_audio.py` lite tests + `test_idle_and_gpu.sh` T7 section);
  P1.M2.T3.S1 flips it to PASS. Do NOT pre-claim PASS (T7 not yet landed).

Also fix the self-contradictions the #10 addition creates:
- intro "criteria 1–8" → "criteria 1–10".
- "Regenerate the **5 / 6 / 8** block" → "5 / 6 / 8 / 9 / 10".
- evidence header "criteria 5, 6, 8, 9" → "5, 6, 8, 9, 10".
- (secondary) #7 row's stale "README is task **P2.M1.T2.S1** (pending)" → the README
  is complete (this task adds lite); only the commit (P1.M2.T3.S1) is pending.

## 4. ★ CONCURRENT-EDITING CAVEAT ★

README.md (and to a lesser degree ACCEPTANCE.md) is being edited by the parallel
Mode-A per-file subtasks RIGHT NOW — verified: the Hotkey-section wording shifted
between two reads ("If SUPER+ALT+D/F is inert…" → "If a bind is inert…"). So the
exact `oldText` anchors captured here are a SNAPSHOT; the implementer MUST re-read
the live file and locate the anchor semantically before applying each edit. The
CONTENT to insert is stable (it states verified behavior); only the surrounding
anchor text may drift. The PRP gives the anchor-as-of-now + a semantic description
so the edit lands even if whitespace/wording shifted.

## 5. Parallel-task boundary (no conflict)

- **P1.M2.T1.S1 (parallel):** edits `tests/test_feed_audio.py` (lite tests) +
  `tests/test_idle_and_gpu.sh` (T7 section). NOT README.md / ACCEPTANCE.md. No overlap.
- **P1.M1.* (Complete):** the per-file Mode-A doc edits (config.toml/config.py/
  daemon.py/recorder_host.py/feedback.py/status.sh/ctl.py/hypr-binds.conf). They
  produced the README content that is ALREADY there. This task is the cross-cutting
  README/ACCEPTANCE sweep that only makes sense now the feature is whole.
- This task edits ONLY `README.md` + `tests/ACCEPTANCE.md`. No source, no tests.

## 6. Tooling

Docs task — no pytest gate (no code changes). Validation = (a) edits apply to the
live file (re-verified anchors), (b) markdown is well-formed, (c) no drift from the
verified behavior (§2). Optional: `markdown` lint if available. The fast suite
(`.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`) is
unaffected (no test files touched) — run only to confirm no accidental edit.

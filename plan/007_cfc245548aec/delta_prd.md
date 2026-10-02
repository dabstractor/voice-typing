# Delta PRD: Rev 2 — Streaming Dictation (typed partials, in-place revision, Backspace-cancel) + Single-Mode Collapse

**Base:** `PRD.md` @ `6b61db1` ("Revise PRD for Rev 2 streaming dictation"). **Prior session:** plan/006_862ee9d6ef41 (Rev 1 fully implemented + audited; see its `architecture/system_context.md`, `gap_*.md`).

**Size:** Medium-large. One major new feature (§4.2quater streaming output engine), one removal (normal/two-model mode), plus config/CLI/test plumbing. This PRD is scoped to exactly that delta — everything else in `PRD.md` is implemented and verified.

---

## 1. What actually changed (diff summary)

The Rev 2 commit (`6b61db1`, PRD-only, +65/−8) plus the §1 decision list introduce:

1. **NEW §4.2quater — Streaming dictation** (the core delta): phone-style typed partials revised in place (`committed`/`tail` state machine), commit/correction pass, rate-limited rewinds, stranded-tail FREEZE, user-typing freeze, `press_backspace(n)` backend primitive, Backspace-cancel via a passive evdev listener + `voicectl cancel` fallback, rolling context prompts (dynamic `initial_prompt`/`initial_prompt_realtime`), deterministic casing/period guards in textproc, `output.streaming=false` rollback hatch.
2. **REMOVAL — one mode only:** normal mode (`distil-large-v3`, two-model construction, mode switching) is deleted; the former lite construction (single `small.en`, `use_main_model_for_realtime=True`) becomes THE path. Delete `final_model` config, the `toggle` vs `toggle-lite` distinction, T7's mode-switching assertions, and acceptance #10's mode-switch claims.
3. **Config delta:** `lite_post_speech_silence_duration` default **0.5 → 0.8** (streaming: the endpointer only delays COMMIT now, words are already visible); new `asr.context_prompt = true`; new `output.streaming = true`; new `[cancel]` section (`on_backspace = true`, `devices = []`).
4. **Control plane:** new `{"cmd":"cancel"}` socket command + `voicectl cancel`; new Hyprland bind `SUPER ALT, Backspace → voicectl cancel` (fallback when evdev can't open a keyboard).
5. **Dependency:** `evdev` (python-evdev) added to `uv add` / pyproject.
6. **Test plan:** NEW T8 (`test_streaming.py` + evdev parser unit tests); T5 manual smoke gains a real-Backspace check; T3/T4 re-worded for the null backend + `state.json` assertions; acceptance items #11 (streaming) and #12 (cancel fallback) added, #4 amended (typed = live partials + commits).
7. **New risk rows:** cursor-race during revision, constructor-static prompts in RealtimeSTT 1.0.2, per-app Backspace semantics, revision flicker, evdev failure modes.

### Already implemented — do NOT re-do

Commit `ccf95eb` ("Drop tmux status helper and prune verbose comments") already landed the tmux-surface half of the PRD delta, ahead of this session:

- `voice_typing/status.sh` and `tests/test_status_sh.py` are **gone**; `feedback.py`/README no longer reference the tmux status line.
- `typing_backends.py` already has `NullBackend` and **no** `TmuxBackend`; `make_backend()` accepts `"wtype" | "ydotool" | "null"`; `config.py` validates exactly those.
- `tests/e2e_virtual_mic.sh` already runs the daemon with `backend = "null"` and asserts finals via `state.json` (T3's new shape).

All Rev 1 machinery (lazy load, recorder-host subprocess + killpg teardown, graceful drain, idle auto-stop, idle unload, lite recorder construction, control socket, voicectl, feedback, cuda_check) is implemented and green — verified by plan/006's audit (`architecture/gap_*.md`, `tests/ACCEPTANCE.md`). Reference it; do not rebuild it.

### Verified current state of the code (grep-confirmed)

- `daemon.py` still carries the two-mode machinery: `cfg_to_kwargs(..., lite=False)`, `resolved["final_model"]/["realtime_model"]`, `"use_main_model_for_realtime": False` for normal mode, mode-switch reload logic, `self._mode`.
- `ctl.py` `_COMMANDS = (toggle, start, stop, status, quit, toggle-lite, start-lite)` — no `cancel`.
- `config.py`/`config.toml` still have `final_model = "distil-large-v3"`, `realtime_model`, `lite_post_speech_silence_duration = 0.5`; no `streaming`/`context_prompt`/`[cancel]`.
- `prefetch.py` still prefetches `Systran/faster-distil-whisper-large-v3` (+ turbo).
- `hypr-binds.conf` still has both toggle binds, no cancel bind.
- `pyproject.toml` has no `evdev`.
- No `press_backspace` / evdev / `initial_prompt` / streaming code anywhere in `voice_typing/`.

---

## 2. Requirements

### R1 — Single-mode collapse (§1 "One mode" decision; supersedes §4.2ter's mode machinery)

The daemon arms in exactly ONE mode: the former lite construction. `model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True`, `post_speech_silence_duration = lite_post_speech_silence_duration` (now default 0.8). The large model never loads anywhere.

Changes to completed work (all in `voice_typing/` unless noted):

- **`config.py` + `config.toml`:** remove `final_model` and `realtime_model` fields (single-model construction never constructs a second model; `use_main_model_for_realtime=True` means `realtime_model` is unused). Keep `lite_model` as THE model field (keep the name — `cuda_check` and §4.4/§4.5 reference it; a rename is churn with no benefit). Remove `use_main_model_for_realtime: False` from normal-path kwargs. Update `test_config.py` / `test_config_repo_default.py` for the removed fields and the 0.8 default.
- **`daemon.py`:** delete `self._mode`, mode-switch reload branches, and the normal-mode kwargs path; `cfg_to_kwargs()`/`_load_host()` always build the single-model recorder (the current `lite=True` branch becomes the only branch). `toggle`/`start` arm it. `status` may keep reporting `mode: "lite"` (constant) so the `state.json` schema in §4.6 stays stable — or drop the field; pick one and keep `feedback.py` consistent.
- **`cuda_check.py`:** simplify `resolve_device_and_models` — no `final_model`/`realtime_model` distinction; CPU fallback = single model `tiny.en` (existing lite fallback logic). Update its tests.
- **`ctl.py`:** remove `toggle-lite`/`start-lite` from `_COMMANDS`, docstring, help/epilog (exit-64 validation list). `toggle`/`start` arm the single path; `stop` disarms. Keep `status` output shape otherwise.
- **`prefetch.py`:** drop `Systran/faster-distil-whisper-large-v3` and the turbo entry — prefetch only `faster-whisper-small.en` (+ `faster-whisper-tiny.en` if the CPU-fallback prefetch already exists; do not add new prefetch surface otherwise). First-arm VRAM drops to roughly half (~0.75–1.5 GB).
- **`hypr-binds.conf`:** collapse to ONE toggle bind (`CTRL SUPER ALT, D → voicectl toggle`), drop the `toggle-lite` bind (see R4 for the new cancel bind).
- **Tests:** delete/rewrite mode-switch tests in `test_daemon.py` (the `-k 'mode or toggle_lite or start_lite or switch'` family), `test_control_socket.py` lite-vs-normal responses, `test_voicectl.py` command-list tests, and `test_recorder_host.py` lite-flag tests. T7 shrinks to: single model resident (no large-model worker, ~half the old VRAM), finals still ≥70% fuzzy accuracy over the clean→type path — fold these two assertions into T8 where convenient rather than keeping a separate T7 mode-switch suite.

**Mode A docs (ride with R1):** `config.toml` comments (removed fields, 0.8 rationale), `ctl.py` docstring/`--help`, `hypr-binds.conf` comments, `prefetch.py` module docstring, `tests/ACCEPTANCE.md` rows for #10.

### R2 — `press_backspace(n)` typing primitive (§4.2quater "Typing backend additions")

Add `press_backspace(n: int) -> None` to the `TypingBackend` ABC (`typing_backends.py`): deletes exactly n characters in an ordinary text field.

- **wtype:** repeat `-k Backspace` (batch the subprocess call — e.g. one `wtype` invocation with n key args, or a single call per press with tight looping; the PRD's budget is **~80 chars rewound in <150 ms**, so per-keystroke `subprocess.run` spawning is too slow — batch it).
- **ydotool:** repeat the backspace keycode, same batching budget.
- **null:** no-op (records nothing; T8 uses a `RecordingTypingBackend` test double, not this).
- The `_WtypeWithFallback` wrapper: on wtype failure fall back to ydotool for backspaces too (same auto-fallback contract as `type_text`).

Update `test_typing_backends.py` (interface, batching, fallback, n=0 no-op).

**Mode A docs:** none beyond docstrings — internal primitive (README covers it via R3's streaming section).

### R3 — Streaming output state machine (§4.2quater core; `daemon.py`)

While armed with `output.streaming = true` (default), the daemon types text as it is spoken and revises it in place. New per-session state: `committed` (finalized text through the last checkpoint) and `tail` (typed since; tentative, no trailing space while tentative).

1. **Partial typing.** On each stabilized-partial event (the existing IPC path that currently feeds `feedback.update_partial`), diff against the typed `tail`: extends → `type_text(delta)`; revises → `press_backspace(len(revised_chars))` then type the corrected tail. **Full rewinds are rate-limited ≥300 ms apart** (code constant, not config) so a wobbling decode cannot flicker.
2. **Commit (silence trips).** The child's re-decode of the complete utterance (the old "final", now a correction pass): if it differs from the typed tail, rewind + retype; apply `append_space`; advance the checkpoint; refresh the rolling context prompt (R5). Existing gates unchanged — `textproc.clean` (blocklist/min_chars) and the `listening` gate (§4.2 #2); a rejected final FREEZES the tail as-is.
3. **Drain unchanged** — an explicit stop mid-speech still lets the correction pass land before disarming (existing `_request_stop`/`_begin_drain` machinery; do not regress it).
4. **Stranded tail → FREEZE, never delete.** If no commit can ever land (drain-watchdog abort, child death — existing `_handle_dead_host`), the tail stays on screen exactly as last shown. The ONLY deliberate deletion is explicit cancel (R4).
5. **User-typing protection.** Any non-Backspace keypress observed while a `tail` is pending → immediately freeze the tail and stop revising that utterance entirely (suppress further partial typing until the next utterance boundary). Never type over the user's cursor. Key events come from the evdev listener (R4) — no new input plumbing.
6. **Rollback hatch.** `output.streaming = false` selects the Rev 1 append-only path: partials go to the state file only, one `type_text(final + " ")` per committed final. KEEP the existing `on_final` append path intact and branch on the flag — this is the regression escape hatch, not dead code.
7. **Feedback:** `state.json` `partial` field mirrors the live tail; `record_final` records the committed text (existing behavior of writing finals back to `partial` carries over). No toast changes.

Implementation notes: the state machine lives in the daemon process (partials already arrive there over the evt_q reader thread); all typing goes through the existing backend instance. Apply R6's textproc guards on every typed fragment (partial deltas and commits).

**Mode A docs:** `config.toml` `streaming` comment; daemon docstring section.

### R4 — Backspace-cancel + evdev listener (§4.2quater "Backspace-cancel"; §4.2 #3; §4.8; §4.10)

- **Control socket:** new `{"cmd":"cancel"}` → rewind + drop the in-flight fragment, keep listening (`{"ok":true,"listening":true}`); no-op when nothing is in flight. `ctl.py` gains `cancel` in `_COMMANDS`/help (R1's removal keeps the list at: toggle, start, stop, status, quit, cancel).
- **Cancel semantics:** rewind `max(len(tail) − 1, 0)` characters — the physical keystroke itself already deleted one, so compensate by subtraction, never by re-typing. Drop the child's in-flight utterance (existing `RecorderHost.abort()` discards its buffered audio — verify, don't reinvent). Keep listening. **Idempotent:** further Backspaces with no pending tail are plain user edits, never compensated.
- **evdev listener:** a passive, read-only (never `EVIOCGRAB`) listener thread in the daemon process over every keyboard `/dev/input/event*` node — auto-enumerate EV_KEY devices exposing `KEY_BACKSPACE`; `[cancel].devices` overrides the enumeration. Trigger: KEY_BACKSPACE **press** while armed AND a tail is pending → cancel. Non-Backspace key presses feed R3 rule 5 (freeze). Dep: `uv add evdev` (pyproject + uv.lock). User is already in the `input` group (§2) — no permission changes.
- **Fallback:** `voicectl cancel` (socket cmd above) is the keybind-able path when no keyboard node is readable — log the listener failure ONCE at arm (not per retry). New bind in `hypr-binds.conf`: `bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel`.
- Gated by `[cancel].on_backspace = true` (false disables the listener entirely; `voicectl cancel` still works).

Unit-test the evdev key-event parser with synthetic events (no real keyboard); real-Backspace behavior stays in the T5 manual smoke.

**Mode A docs:** `config.toml` `[cancel]` comments; `hypr-binds.conf` comment for the new bind; `ctl.py` help.

### R5 — Rolling context prompt (§4.2quater; `recorder_host.py` + `daemon.py`)

Condition every decode on the committed text **back to the last sentence boundary** (last `.`/`!`/`?`), capped at ~200 tokens (Whisper's ~224-token budget; code constant). Partial decodes via `initial_prompt_realtime`, commit decodes via `initial_prompt`. Both kwargs exist in installed RealtimeSTT 1.0.2 but are constructor-static — the child MUST make them dynamic (update between utterances via a small local patch / attribute poke on the recorder). **If dynamic updating fails, degrade to context-free decoding and log — never crash.** Toggled by `asr.context_prompt = true`. This is the primary fix for mid-paragraph fragments starting capitalized or acquiring spurious trailing periods.

The daemon computes the prompt string (it owns `committed`) and ships it to the child over the existing cmd_q IPC with each arm/text-cycle; the child applies it before the next decode.

**Mode A docs:** `config.toml` `context_prompt` comment.

### R6 — Deterministic textproc guards (§4.2quater; `textproc.py`)

New pure functions alongside `clean()` (which is unchanged), applied at typing time on the streaming path, unit-tested:

- **Casing guard:** if `committed` does not end a sentence (no terminal `. ! ?`), lowercase the fragment's first word.
- **Period guard:** if the casing guard fired (we joined mid-sentence), strip one trailing `.` from the committed fragment — a decoder closing a sentence it was told it was continuing is spurious by definition.

**Mode A docs:** none (internal; covered by README tuning notes in the Mode B sweep).

### R7 — Config schema delta (§4.5; `config.py` + `config.toml`)

Net changes (combine with R1/R3/R4/R5 field work into one coherent schema edit):

| Field | Change |
|---|---|
| `asr.final_model` | **REMOVED** |
| `asr.realtime_model` | **REMOVED** |
| `asr.lite_post_speech_silence_duration` | default `0.5` → `0.8` (comment: endpointer only delays COMMIT under streaming; 0.5 razor-snappy, 1.0 near-zero cuts) |
| `asr.context_prompt` | **NEW**, default `true` |
| `output.backend` | values now `"wtype" | "ydotool" | "null"` (validation already matches — no change needed) |
| `output.streaming` | **NEW**, default `true` |
| `[cancel] on_backspace` | **NEW**, default `true` |
| `[cancel] devices` | **NEW**, default `[]` (auto-enumerate) |

Extend the existing `__post_init__` type validation to the new fields (bool-for-numeric rejection, unknown-key rejection — follow the established patterns in `config.py`). Keep `config.toml` ↔ `config.py` lockstep (`test_config_repo_default.py`).

**Mode A docs:** `config.toml` is the user-facing reference — every new/removed field gets a self-documenting comment.

### R8 — Dependency + install delta (§5)

`pyproject.toml`: add `evdev` to `dependencies` (via `uv add evdev`; commit `uv.lock`). `install.sh` printed usage gains `voicectl cancel` and the Backspace bind mention; prefetch output drops the large model (R1). Nothing else in install/systemd changes.

---

## 3. Removed requirements (awareness only — no tasks)

- **Normal/two-model mode** (`distil-large-v3` final pass, `toggle-lite` as a *distinct* mode, mode-switch reload, T7 mode-switching, acceptance #10 mode-switch claims, ⚡ lite prefix semantics). Superseded by R1. The large-model code paths, config fields, tests, and docs go away; no re-addition planned.
- **tmux surfaces** (tmux typing backend, `status.sh`, tmux status snippet) — already removed in `ccf95eb`; only residual doc references may remain (Mode B sweep).

## 4. Test plan delta (§6)

- **T8 (NEW) — `tests/test_streaming.py`, no mic, no real keystrokes.** Lite-style recorder child + a `RecordingTypingBackend` test double (records `type_text`/`press_backspace` calls). Feed WAVs via `feed_audio()`. Assert: (a) typing deltas arrive ≥1/500 ms while speech streams, and only the delta when a partial extends the tail; (b) a differing commit rewinds exactly the tail length then types the final text (+ trailing space); (c) a sentence split by a 3 s pause joins into ONE coherent commit — no mid-sentence capital, no spurious trailing period (context prompt + guards); (d) the child's decodes carry `initial_prompt` = committed context back to the last sentence boundary, capped (assert via child log/kwargs); (e) `cancel` with a pending tail → `press_backspace(len(tail)−1)`, buffered audio dropped (no late commit), listening stays on; second cancel is a no-op; (f) a non-Backspace key with a pending tail → tail frozen, no further revision keystrokes that utterance; (g) forced drain-timeout → tail frozen on screen, not rewound. Heavy (CUDA) — run under `timeout 600` per AGENTS.md.
- **Evdev parser unit tests (NEW):** synthetic events only (parse KEY_BACKSPACE press vs release, non-Backspace keys, device enumeration filter). No real keyboard.
- **T1–T4, T6:** unchanged in substance. T3/T4's null-backend/state.json shape already landed. T6 VRAM expectations shift down (~half) with the single model — widen the armed-memory assertion accordingly (e.g. ~0.5–3 GB).
- **T7:** collapses into single-model assertions (one model resident, ≥70% accuracy) — fold into T8/T6; delete the mode-switch socket suite.
- **T5 (manual):** README "First run" gains: press Backspace mid-fragment → fragment disappears, dictation stays armed.
- **Existing suites to update (not delete):** `test_daemon.py` (mode machinery → single path; new streaming state-machine unit tests with a fake backend + fake partial stream — pure-python, fast), `test_control_socket.py` (+`cancel`, −lite commands), `test_voicectl.py` (command list), `test_config.py`/`test_config_repo_default.py` (schema delta), `test_typing_backends.py` (+`press_backspace`), `test_recorder_host.py` (lite-flag removal, dynamic prompt application), `test_textproc.py` (+guards).

## 5. Acceptance delta (§7)

Amend/add only (all others stand as verified in plan/006):

- **#4 (amended):** typed output = live partial text plus commits (§4.2quater); still nothing typed while toggled off (listening gates unchanged on both paths).
- **#10 (rewrite):** single-model arming only — `small.en` is the sole model (no large-model worker, ~half the old VRAM via `nvidia-smi`); the drain applies unchanged.
- **#11 (NEW):** streaming — words typed continuously (≥1 update/500 ms, T8a); commits revise in place (T8b); mid-paragraph fragments never start capitalized nor end with a spurious period (T8c); Backspace mid-fragment cancels — text rewound, mic still armed (T8e); stranded fragments freeze, never auto-delete (T8g); `output.streaming=false` restores Rev 1 append-only behavior.
- **#12 (NEW):** with evdev unavailable, `voicectl cancel` performs the same rewind over the socket (T8e) and the daemon logs the listener failure once at arm.

## 6. Risks (new rows, §8 — mitigations already embedded in R2–R6)

| Risk | Mitigation (where) |
|---|---|
| Revision corrupts text if the user moves the cursor mid-utterance | non-Backspace keypress freezes the tail (R3 rule 5); rewind assumes 1 char/keystroke at end of typed text — documented assumption |
| `initial_prompt*` constructor-static in RealtimeSTT 1.0.2 | child updates them between utterances; on failure degrade to context-free + log (R5) |
| Backspace semantics differ per app | cancel only while armed AND tail pending; idempotent; subtraction compensation; `voicectl cancel` fallback (R4) |
| Revision flicker (rewind/retype storms) | delta-typing default; full rewinds rate-limited ≥300 ms; no trailing space while tentative (R3 rule 1) |
| evdev misses keyboards / permission loss | log once at arm; keybind fallback; `[cancel].devices` override (R4) |

## 7. Documentation impact

- **Mode A (per-requirement, listed inline above):** `config.toml` comments (R1, R3, R4, R5, R7), `ctl.py` docstring/help (R1, R4), `hypr-binds.conf` (R1, R4), `prefetch.py` docstring (R1), `tests/ACCEPTANCE.md` (R1, §5 delta).
- **Mode B (changeset-level — final task, depends on all):** sync `README.md` end-to-end for the Rev 2 product: one mode + streaming output as THE behavior (not a mode), Backspace-cancel + its fallback bind, feedback surfaces (toasts/`state.json`/`voicectl status` — tmux snippet gone), updated config tuning table (`lite_post_speech_silence_duration` 0.8 semantics, `streaming`, `context_prompt`, `[cancel]`), troubleshooting additions (backspace-in-terminals caveat, evdev permission), first-run section with the Backspace check, removal of all normal/lite two-mode prose. Also sweep `install.sh` printed usage and any residual tmux/status.sh references.

## 8. Suggested breakdown shape (for the breakdown agent — 1 phase, 3 milestones)

- **M1 Substrate:** single-mode collapse across config/cuda_check/daemon/ctl/prefetch/hypr-binds + tests (R1, R7 schema half, R8 dep), `press_backspace` backends + tests (R2).
- **M2 Streaming engine:** daemon committed/tail state machine + freeze rules + rollback hatch (R3), cancel path: socket cmd + ctl + evdev listener (R4), rolling context prompt in recorder_host (R5), textproc guards (R6), remaining config fields (R7).
- **M3 Verification & docs:** T8 + evdev unit tests + updated suites + T6/T7 adjustments + acceptance evidence (§4, §5), Mode B doc sweep (§7).

Story-point feel: M1 ~5, M2 ~10, M3 ~6. Keep tasks file-scoped with the heavy daemon work (R3) as its own task with the R4/R5/R6 seams called out.

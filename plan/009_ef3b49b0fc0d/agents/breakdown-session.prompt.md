# PROJECT INITIATION

**INPUT DOCUMENTATION (PRD):**
# Delta PRD — Contextual dictation for Pi and Neovim

**Scope:** One phase, two milestones. The [current snapshot](prd_snapshot.md) adds a native editor feature, not a new ASR engine or a rewrite of desktop dictation. Compared with the [previous snapshot](../008_a47116bb2b79/prd_snapshot.md), the line diff is **+77 / −34 lines** (**+4,790 / −1,360 whitespace-delimited words on changed lines**, net +43 lines / +3,430 words). New §4.8.1 and T10 account for 55 lines and 3,508 words; the remaining changes chiefly retire Rev 4 from the product and clarify keyboard delivery and installation. §4.8.1 remains the detailed protocol contract; this delta is not evidence of implementation or release acceptance.

**Reuse the completed work.** Keep the resident recorder, rolling prompt executor, recorder event identities, lazy load/unload and media ducking, legacy safety fixes, and ordinary session recovery. [Prior architecture notes](../008_a47116bb2b79/architecture/) map the recorder relay and recovery seams (`d2_bulk_delivery_map.md`, `d1_ducking_seams.md`) and document the Pi splice/caret proof (`pi_seam_proof.md`, `g3_pi_prompt_row.md`). Use the proof as a starting point, not as acceptance of the new client protocol or of stock Pi-Bolt. The previous `docs/` directory is empty. Existing stream/block CLI dispatch and the in-tree tmux compatibility remap are starting points, not features to rebuild.

## Phase 1 — Ship opt-in contextual editor dictation

### Milestone 1 — Daemon contract and safe migration

#### 1. Preserve generic dictation and retire public bulk delivery (§4.3, §4.5, §4.10, §7.13)

Stream remains the default and types partials and finals; an explicit block arm types only accepted finals through the same low-level injector. Preserve generic stop/cancel behavior and `voicectl session [--copy]`; `--copy` remains an explicit action, not a delivery mechanism. `output.backend` selects `wtype`, `ydotool`, or `null`; preserve `tmux` → `ydotool` without tmux operations. Reject explicit `output.delivery="bulk-text"` with an actionable migration error **before arming or injecting**; absent/`stream-edit` config continues to work. Disconnect the shipped bulk dispatch and adapter activation from `VoiceTypingDaemon` and remove any bulk-only recorder wiring from supported paths. Keep experimental code/evidence as lab reference where useful. Reuse `OutputConfig`, `make_backend()`, and existing arm/dispatch tests. No desktop bindings are shipped; users own mappings. Document the supplied service's `systemctl --user stop voice-typing` as the socket-independent stop, not a panic chord.

- **Mode A:** `config.toml`, `voice_typing/config.py` comments, `voice_typing/ctl.py` help, and `install.sh` printed usage/troubleshooting; retain already-correct behavior and remove stale instructions in touched surfaces.

#### 2. Add confirmed, private prompt seeding (§4.2quater, §4.8.1 A; T10a)

Reuse `PromptedExecutor` and the shared recorder. Extend `RecorderHost.set_prompt()`'s existing fire-and-forget pattern with **confirmed priming for Start**: newest pre-caret suffix, capped at 4 KiB UTF-8 by the adapter and trimmed to the model budget without sentence-boundary cutting. The child must acknowledge the active partial and final lanes before capture. Known-clear/no-executor starts may report `context_seeded:false` with `empty`, `disabled`, or `unavailable`; unknown prompt state fails closed. Fence late ACKs by reservation/generation, never wait under the daemon control lock, and clear seeds on failed arm/end. Keep the seed until the first accepted utterance, then use normal rolling context (native: only this session's accepted finals). Never feed the seed into spacing/committed text or expose it in feedback, logs, replies, recovery, or persistent client files.

Expose `start-context` and `voicectl start|start-block|start-stream --context-stdin` for callers who explicitly want **focus-based** dictation with a seed. Reject during arming/listening/draining; do not retry or fall back on old daemon or timeout. Plain starts never inherit a seed. Pin warm/cold ACK-before-capture, Unicode/bounds, rejected-first-utterance handoff, and privacy in T10a.

- **Mode A:** `voice_typing/recorder_host.py` and `voice_typing/prompt_engine.py` protocol/docstrings; `voice_typing/ctl.py` help distinguishing context-only from pinned delivery.

#### 3. Own, drain, and recover native sessions (§4.8.1 B–C; T10b)

Extend `ControlServer._handle`/`_dispatch` on the existing owner-only XDG socket with v1 `editor-start` and `editor-recover`; keep old one-shot clients compatible. Reserve one owner connection and UUIDv4 across startup/listening/drain, rejecting competing starts/toggles/cancels as busy without queueing. Keep status/stop/quit usable. Enforce UTF-8 JSONL framing and a 32 KiB request/live-event ceiling while reading. Preserve `starting → listening → [finishing] → ended`, FIFO accepted finals with one sequenced offer outstanding, and ACK only for the verified edit. An exact duplicate of the last ACK is harmless; malformed, stale, or uncertain delivery must never trigger a resend. Use existing recorder generation/utterance identities to reject stale, duplicate, or unidentified finals; callbacks clean/filter, retain and enqueue, with no socket waits or abort/drain under the control lock or on the recorder reader thread. Cap live delivery at eight finals including the outstanding one, 4 KiB UTF-8 each; overflow revokes delivery and drains to recovery without inserting truncated text.

Keep ownership responsive during cold load: 30 s Start cap, 2 s pings / 6 s lease, 2 s write cap and 5 s offer ACK deadline; allow at most 5 s total for outstanding ACKs after the bounded ASR drain. Native Stop (including idle or `voicectl stop`) lets at most the in-flight utterance finish and settles queued inserts only while the target remains valid. Cancel revokes locally and aborts capture; loss/EOF revokes locally and drains at most that utterance to recovery only. Ending during startup prevents a late arm. Shutdown/host failure need not drain. Reuse mic/media/idle lifecycle; native mode bypasses all generic injection, bulk acquisition, evdev guards and transcript-bearing desktop/status feedback.

Reuse `SessionRecovery` machinery where practical, but keep native recovery separate from `voicectl session`: unacknowledged accepted finals only, up to two nonempty ended IDs, 1 MiB UTF-8 per session including active unacknowledged text, and a 7 MiB escaped reply ceiling. `voicectl recover [ID]` prints text only; warn on stderr about truncation or possible prior insertion when an offer was attempted without a verified ACK. No automatic replay or persistence. Retain transcript-free abnormal reason/recovery hint in status and logs; use an optional desktop-neutral warning when the editor UI is unavailable. T10b must prove exclusivity, bounds, timeout/loss races, and zero global output even on failure.

- **Mode A:** docstrings in `voice_typing/daemon.py`, the native protocol module and `voice_typing/session_recovery.py`; `voice_typing/ctl.py` recovery help.

### Milestone 2 — Native editors and verification

#### 4. Ship independent Pi and Neovim adapters (§4.8.1 C–D; T10c)

Both expose editor-local **Start / Stop / Cancel** with visible Starting/Listening/Finishing and actionable loss warnings. Start snapshots the live insertion point; use only eligible pre-caret text, or send an empty seed with `send_context=false`. Pin target identity, caret, mode, and revision. Invalidate before user actions or lifecycle changes that can move, edit, submit, or replace the target, including edit-and-return and external-editor transitions. Recheck the live checkpoint in the same UI operation as the splice. Insert a cleaned final as one native undoable edit, with §4.8.1 C's shared Unicode-whitespace and delimiter padding; verify exact text/caret before ACK. Never replace neighboring text, resubmit an uncertain edit, save a draft, or hand off to another target. Desktop/terminal/tmux focus is not a routing authority. A fresh explicit Start is required after loss.

- **Pi (`integrations/pi/`):** use public APIs in upstream Pi and stock Pi-Bolt; wrap the mounted editor without breaking normal input or extensions. Use actual `getLines()`/`getCursor()` offsets and `insertTextAtCursor()`, not whole-buffer setters or simulated paste. Refuse ambiguous markers or unsupported modes; act from a nonempty draft without replacing it. Revoke before the external-editor action (including remaps), submit, replacement or session shutdown. The prior `.pi/extensions/voice-editor.ts` and `voice_typing/pi_editor.py` are lab precedents, not the shipped connection model.
- **Neovim (`integrations/neovim/`):** use a libuv pipe, scheduled callbacks, Insert-mode actions, pinned buffer/window and changedtick, and native `nvim_buf_set_text` with byte offsets. Verify one Undo per final. Support the live unsaved Pi external-editor buffer, never its temp file directly; refuse special, selected, read-only, excluded or otherwise ineligible targets. No auto-bind.
- **Mode A:** `integrations/pi/README.md` and `integrations/neovim/README.md` cover install/uninstall, verified versions, non-shortcut invocation and optional mappings, privacy, warnings/recovery, and separate daemon vs adapter prerequisites. Both adapters work with no compositor, tmux, desktop tools, systemd dependency, or fixed local paths.

#### 5. Qualify the delta and report limits (T10a–d, §7.13–14)

Use shared protocol vectors, deterministic race barriers, private sockets, fake ASR and isolated real editors. T10c verifies text/caret, one Undo, stop vs cancel, sticky invalidation, remapped Pi external-editor action, and operation on both adapters under non-default XDG with no display or desktop tools. Record verified upstream Pi, Pi-Bolt and Neovim versions. Run T10a–c under `AGENTS.md` timeouts, diff daemon failures by name against `tests/G1_BASELINE.md`, and require no new regressions. T10d is opt-in: mid-draft Stop/Undo, external-editor loss and recovery, unsaved Neovim edits and return to Pi, pane isolation, and warm-recorder reuse. Record evidence or mark hardware-dependent checks pending user run; never restart the user's service automatically. Automated tests do not touch the live service, desktop, mic, clipboard, or audio devices.

- **Mode A:** `tests/ACCEPTANCE.md` records test evidence, tested versions, and pending hardware results.

#### 6. Sync changeset-level documentation (Mode B; after requirements 1–5)

Update `README.md` to distinguish generic stream/block, context-only starts, pinned native sessions, and explicit recovery/copy. Replace shipped bulk guidance with the migration instructions and link to the lab history; align install guidance with distro-neutral prerequisites, optional CUDA/CPU fallback and independently installed adapters. Remove stale shortcut claims and distinguish verified behavior from pending T10d checks. No operator config or binding changes.

**Removed from product scope (no work items):** Rev 4 system-wide atomic paste/IM-v2 routing, clipboard fallback, application/register discovery, G3–G6 graduation and the 110 wpm release bar, and the shipped desktop/panic binds. Do not rerun Rev 4 labs for acceptance. Also out of scope: native partial writes, live reseeding, automatic handoff, and unrelated recognition tuning or rework of completed ducking and legacy fixes.


**PRD STRUCTURE INDEX:**
Use these selectors in `prd_selectors` to reference specific sections for each subtask.
Downstream PRP agents will only receive the selected sections, not the full PRD.

```
h1.0 PRD: Fully-Local Voice Typing for Linux/Wayland — "voice-typing"
 h2.0 1. Problem statement (user's own framing)
 h2.1 2. Verified machine facts (already checked on this exact machine — do not re-derive, but trust these over stale docs)
 h2.2 3. Research summary and engine decision (completed July 6, 2026 — a light verification pass is fine, a full re-research is not needed)
 h2.3 4. Architecture
  h3.0 4.1 Repository layout
  h3.1 4.2 The daemon (daemon.py)
  h3.2 4.2bis Model lifecycle — lazy load on first arm
  h3.3 4.2ter Lite mode — small-model-only quick dictation
  h3.4 4.2quater Streaming dictation — typed partials, in-place revision, Backspace-cancel (Rev 2; small-model/lite path only)
  h3.5 4.2quinquies Media ducking while listening — pause/duck speakers at arm (spec'd 2026-11-18; implement next round)
  h3.6 4.2sexies Legacy bulk text delivery experiment (Rev 4 reference, superseded)
  h3.7 4.3 System-wide keyboard injection (typing_backends.py)
  h3.8 4.4 RealtimeSTT recorder configuration (exact starting values — tune only if tests fail)
  h3.9 4.5 Config (config.toml, parsed with stdlib tomllib into dataclasses)
  h3.10 4.6 Feedback (feedback.py)
  h3.11 4.7 Text processing (textproc.py)
  h3.12 4.8 voicectl (ctl.py)
   h4.0 4.8.1 Editor integrations — contextual dictation with pinned delivery (proposed)
    h5.0 A. Shared context and optional context-only CLI
    h5.1 B. Native wire protocol v1 (same owner-only Unix socket)
    h5.2 C. Target validity, edit semantics, and warnings
    h5.3 D. Required adapters and implementation boundaries
  h3.13 4.9 systemd user service (systemd/voice-typing.service)
  h3.14 4.10 User-owned shortcuts
 h2.4 5. Installation
 h2.5 6. Test plan — ALL must pass before declaring success
 h2.6 7. Acceptance criteria (definition of done)
 h2.7 8. Known risks & prescribed mitigations
 h2.8 9. Future work (explicitly out of scope now)
---
code:5 para:82 list:35 table:4
```

**INSTRUCTIONS:**
1.  **Analyze** the PRD above.
2.  **Spawn** subagents immediately to research the current codebase state and external documentation. validate that the PRD is feasible and identify architectural patterns to follow.
3.  **Store** your high-level research findings in the `plan/009_ef3b49b0fc0d/architecture/` directory. This is critical: the downstream PRP agents will rely on this documentation to generate implementation plans.
4.  **Decompose** the project into the JSON Backlog format defined in the System Prompt. Ensure your breakdown is grounded in the reality of the research you just performed.
5.  **Populate `prd_selectors`** for each subtask using selectors from the PRD STRUCTURE INDEX. Reference ALL relevant sections.
6.  **CRITICAL: Write the JSON to `./plan/009_ef3b49b0fc0d/tasks.json` (current working directory) using your file writing tools.** Do NOT output the JSON to the conversation. Do NOT search for or modify any existing tasks.json files in other directories. Create a NEW file at `./plan/009_ef3b49b0fc0d/tasks.json`. The file MUST exist when you are done.

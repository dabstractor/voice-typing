# P1M1T4S6-R3: Native Editor Session End — PRD Requirements Extraction
# Source: plan/009_ef3b49b0fc0d/prd_snapshot.md (READ-ONLY)

## 1. Wire Protocol v1 `ended` event/frame (§4.8.1 B)
Last frame: `{"event":"ended","id":"...","reason":"<code>","recoverable":true}` after finishing drain. Exactly one `ended`; terminal transition idempotent even if Stop/loss/exit/EOF race.

**Reason vocabulary**: stopped | idle | cancelled | timeout | target_lost | disconnected | shutdown | delivery_failed

**`finishing` event**: `{"event":"finishing","id":"..."}` — winds down after graceful stop; ordered before any final accepted during drain.

**Ordering**: `ended` after last `finishing`; exactly one `ended` frame.

**`applied` command** (editor→daemon): `{"cmd":"applied","id":"...","seq":1}` — sent only after verifying native edit and new caret/checkpoint; advance ACK watermark once; ignore exact duplicate last ACK; other unexpected ids/seqs/commands → `delivery_failed`; clients never insert duplicate/skipped/stale/out-of-generation offers.

**Native error codes**: invalid_request, too_large, unsupported_version, busy, duplicate_id.

**ACK/delivery rules**: Accept `applied` only for outstanding seq, advance watermark once; ignore exact duplicate last ACK; unexpected ids/seqs/commands → `delivery_failed`; final outside Listening/Finishing, wrong seq, unknown event, failed edit, uncertain outcome, or timeout → invalidate locally, warn, abandon delivery, never retry; Cancel/Lost immediately disable local delivery before transport processes; transport close or abnormal terminal event invalidates any not-yet-executed UI callback.

---

## 2. Hints / Warnings / Toast Rules on Failure or Loss (§4.8.1 C, §4.6)
**'Neutral optional warning if editor UI is gone'**: Target loss must show visible warning e.g. "Dictation stopped: draft or caret changed. Start again here. Unconfirmed text: `voicectl recover <id>`." Alert editor when UI still available, including disconnects. For suspended/closed editor, daemon attempts transcript-free warning with recovery hint via freedesktop notifications (e.g. `notify-send` if available). Configured desktop notifier optional fallback, never dependency. Always retain transcript-free last abnormal end reason and recovery hint in `voicectl status` and log same diagnostic, even if notifier succeeds. Closed editor on bare TTY cannot show live popup; document limitation. `hyprctl` not required for native warnings.

**What must NEVER appear**: Never the surrounding user document. Never seed text in errors/replies, logs (DEBUG), status, state file, recovery, clipboard, or persistent client files. Only recognizer output can become transcript, even if it repeats seed words. Expose fixed reason codes, counts, and ids rather than dumping raw requests or exception data carrying text.

**Toast rules** (§4.6): `hyprctl notify -1 <notify_ms> "rgb(88c0d0)" "<msg>"` fire-and-forget, swallow errors. Only notify on: listening-start ("Recording"; first arm preceded by one-shot "Loading…" toast while models load — §4.2bis), each final ("✔ <text>" — gated by `notify_on_final`), listening-stop ("Recording Stopped" — for ANY disarm). Partials go to state file only. `record_final` also writes finalized text back into `partial` field.

**state.json keys**: `{"listening": true, "phase": "speaking", "models_loaded": true, "mode": "normal", "partial": "...", "last_final": "...", "ts": ...}`; `mode` is "normal" or "lite"; written on every partial update (throttle ≥10 Hz), phase change, final, and model-lifecycle transition; while models not loaded: `phase` is `unloaded`/`loading`, `models_loaded` is false.

---

## 3. Recovery: How Owner is Told Recovery Text Exists (§4.8.1 C, §4.8)
**`voicectl recover [ID]` contract** (one-shot, stdout text only, warnings on stderr):
- `{"cmd":"editor-recover","id":"..."}` → `{"ok":true,"id":"...","text":"...","truncated":false,"possibly_applied":true}` for retained id (omitting id selects latest); text = unacknowledged accepted finals joined with single space; `possibly_applied` true if included final's offer write attempted without verified ACK; return `not_found` if absent, `busy` for active id; bound 7 MiB including newline.
- `voicectl recover [ID]` prints only text to stdout, warns of truncation/possible duplication on stderr; **never auto-inserts**.
- Fully acknowledged or empty endings do not evict previous recovery. No durable recovery promised after daemon restart.

**How owner is told recovery text exists**: Visible warning in editor: "Dictation stopped: draft or caret changed. Start again here. Unconfirmed text: `voicectl recover <id>`."
- `voicectl status` retains transcript-free last abnormal end reason and recovery hint.
- Log same diagnostic.
- Desktop-neutral notification backend (freedesktop, e.g. `notify-send` if available).
- Configured desktop notifier optional fallback, never dependency.

**Caps**: Bound escaped JSON recovery reply separately (7 MiB including newline). No durable recovery promised after daemon restart.

---

## 4. Lifecycle: Shutdown, Recorder-Host Failure, Stop/Drain/Idle Unload (§4.8.1 B-C, §6, §7, §8)
**Shutdown / recorder-host failure**: "Clean up without promising a recoverable drain."

**Stop during startup**: Aborts reservation without opening capture.

**Loss while starting**: Aborts without capture.

**Lease expiry**: Active lease expires at 6 s without valid ping/pong; ACK deadline 5 s from offer write; clients close on expired deadline; EOF/client failure/expired lease is loss, never permission to send text anywhere else.

**Idle auto-stop & idle UNLOAD with native owner**: Daemon starts not-listening/not-loaded; never hot-mic on boot; loads no models until first arm (§4.2bis, ~0 VRAM at idle). **May idle watchdog unload while owner reserved/starting/listening/draining?** — Known risk: toggle-off race types one last utterance; idle-unload requires bounded teardown (§4.2bis: hard timeout + force-cleanup of recorder's worker threads/`transcript_process` so VRAM released and racing arm isn't blocked for 90 s). Daemon must service EOF/stop/lost/heartbeat during cold load; cancelled reservation cannot resume/arm when worker returns. Keep status/stop/quit responsive.

**Status fields for native sessions**: `delivery_mode`, `delivery_state`, `delivery_reason`.

**'Recheck reservation on commit/end/mic commands and retain ownership through cleanup/drain'**: Immediately before accepting a final, recheck same live target, revision, mode, and caret in one synchronous UI-thread operation; insert via native editing API only, verify expected splice and new caret, update checkpoint before ACK; only adapter's own successful edit advances checkpoint; do not suppress unrelated changes by callbacks/plugins. If verification fails after possible write, stop with uncertain delivery, never reapply or attempt destructive rollback. Moving caret, making manual edit (incl. undo/redo), switching drafts, losing editor surface/window, entering modal/selection/read-only state invalidates session even if user immediately returns. External editor open/close always a boundary. Local invalidation sticky for id, occurs before sending `lost`, `cancel`, or closing connection; queued callbacks recheck before editing. Desktop/compositor/tmux focus is neither routing authority nor proof of target loss: if logical draft still valid, output may reach only that draft, never newly focused target.

---

## 5. Test Plan Items (verbatim with IDs) and Acceptance Criteria (§6, §7)
**T10a** — priming/compatibility: Warm/cold starts same daemon recorder; assert child ACK then capture on both decode lanes; complete-sentence and multiline Unicode seeds; rejected first utterance then rolling handoff; empty/disabled/unavailable prompting, lost/late/failed priming with no late arm, no prompt inheritance on plain re-arm; context-only CLI on new/old daemon; 4 KiB/32 KiB boundaries, invalid UTF-8 and JSON, split/coalesced frames, partial EOF; distinctive seed absent from replies, logs, state, recovery, and delivery; plain start/stop/stream/block retain keyboard behavior outside owner sessions; plain block arm emits no partials, accepted final goes to same injector as stream mode.

**T10b** — native lifecycle and recovery: Competing editor and legacy starts in arming/listening/draining; warm/cold stop and disconnect; blocked receiver, lease/ACK timeout, wrong id/seq, duplicate/stale/identity-less finals, duplicate ACK, late callback after re-arm, exactly one bounded terminal transition, queue/byte caps, cleanup of media/mic/ownership; verify ordering starting/listening/finishing/ended; one accepted final per offer; no transcript in general feedback; zero calls to every global delivery path even on error; legacy `delivery="bulk-text"` config produces migration error not keystrokes; graceful Stop, Cancel, loss mid-utterance, loss during drain, shutdown; known acknowledged vs never-offered vs possibly applied recovery; id lookup and latest selection; truncation and bounded retention; simulate native edit completing just before socket breaks: recovery may include with duplicate warning; replay never occurs.

**T10c** — each real editor with fake socket server: Use shared protocol vectors; live pre-capture (unsaved/multibyte/multiline, 4 KiB boundary); privacy opt-out; status; unsupported targets; multiple finals with spacing, one undo per final; no modifications outside exact splice; inject final after caret movement, manual edit, undo, edit-and-return, target switch/close, mode change, reload, lost/duplicate/out-of-order frame; assert zero further writes and visible warning; prove Stop applies eligible in-flight final while Cancel does not; upstream Pi and stock Pi-Bolt in isolated PTYs; on both adapters run Start→final→Stop plus target loss with non-default XDG runtime dir and without `DISPLAY`/`WAYLAND_DISPLAY`/`TMUX`/compositor helpers/injection/clipboard tools or project paths on PATH; verify in-editor warning and transcript-free status hint when desktop notifications unavailable; record verified editor versions; fake warning sink sufficient for daemon desktop notification tests.

**T10d** — end-to-end smoke: In Pi with real service, dictate at mid-draft caret, Stop mid-phrase, Undo; start again and open Neovim via external-editor action during delayed final: expect loss warning, no write in either editor from that session, recover text if accepted; start in Neovim after unsaved manual edits, dictate and Stop; verify insertion stays in that buffer and not auto-saved; close Neovim mid-dictation and late final cannot land in Pi; verify warning/recovery; restart dictation in Pi explicitly; switch tmux panes while dictating and other pane receives nothing; verify Pi and Neovim reused same resident recorder on warm sequence; installed service opt-in smoke only; no auto-restart of user's service.

**Acceptance criteria §7**: (1) T1–T4, T6 pass by actual output; (2) ≥3 s pause mid-dictation loses zero words, does not end session (T1b, T3); (3) Live partials observable in `state.json` while audio plays; (4) Only daemon's typed output reaches target; (5) Daemon survives ≥2 min silence no hallucinated output trivial CPU; (6) `voicectl toggle/start/stop/status/quit` all work; daemon as systemd user service, starts un-armed/un-loaded (~0 VRAM until first arm), auto-restarts on failure; (7) Everything committed to git; README documents install, CLI, shortcuts, feedback surfaces, config tuning table, troubleshooting (cuDNN, PyAudio device, wtype vs ydotool), CPU-only mode switch; (8) No network access needed at runtime; (9) After `auto_unload_idle_seconds` disarmed idle, recorder unloads (~0 VRAM via `nvidia-smi`), later arm reloads it; teardown bounded (seconds, no 90 s hang); (10) Lite mode: `toggle-lite` arms using ONLY `lite_model` (large model never loads, ~half VRAM of normal); `toggle` arms normal mode; switch costs one bounded reload; `status`/`state.json` report `mode`; lite uses shorter `post_speech_silence_duration` (silence gate is perceived bottleneck — §4.2ter) so observably snappier end-to-end; both modes honor graceful drain; (11) Streaming: while speaking words typed continuously ≥1 update/500 ms (T8a); partials/commits revise in place with MINIMAL backspacing — only diverging suffix after longest common prefix ever rewound, never whole tail (T8a/T8b); mid-paragraph fragment never starts with capital nor ends spurious period (T8c); Backspace mid-fragment cancels — text rewound, mic still armed (T8e); stranded fragments freeze, never auto-delete (T8g); `output.streaming=false` restores Rev 1 append-only; (12) Cancel fallback: with evdev unavailable, `voicectl cancel` performs same rewind over socket (T8e) and daemon logs listener failure once at arm; (13) System-wide delivery: stream/block use same generic key injector; block sends no partials to target; neither detects application, routes to tmux, or writes clipboard; native one-edit insertion only by explicit app integrations; Rev 4 lab results not graduation or release gate; (14) Editor integrations: both independently installable adapters use same resident daemon, one native undoable edit per final, no writes to any other target; moving or losing target stops insertion, shows warning, makes unconfirmed finals recoverable; new explicit Start captures fresh context; T10a–c must pass and T10d results must be reported before claiming completion.

---

## 6. Risk Table Rows (§8)
| Risk | Mitigation |
|---|---|
| `recorder.shutdown()` hangs ~90 s (seen on every `quit`: SIGKILL after systemd `TimeoutStopSec`) | Prerequisite for idle-unload: teardown MUST be bounded/non-blocking (§4.2bis Idle unload): hard timeout + force-cleanup of recorder's worker threads/`transcript_process` so VRAM released and racing arm isn't blocked for 90 s. Root-cause the wedge (likely `transcript_process` join or mic stream close) and fix it; until then idle-unload would hang every 30 min |
| `ydotoold_client` SOCK_STREAM vs ydotoold SOCK_DGRAM → Errno 91 every connection since f0d8d0a (2026-10-31) | Merge branch `fix/ydotoold-datagram` (commit 33321c6, 11 tests; packing proven byte-identical to real CLI). Add 6 ms press→release contact gap |
| Cancel compensation assumes one physical Backspace = one character (auto-repeat violates it) → under-compensation manufactures belief-desync | Under investigation |
| Cancel-suppression window latched and dropped finals 4× week of 2026-11-12..18 ("missing/repeated sections") | Window latch timing needs investigation |
| Backspace semantics differ per app (terminals, editors) | Cancel fires only while armed AND a tail is pending; idempotent; compensation by subtraction; falls back to `voicectl cancel` keybind |
| Seat IM slot exclusive (`zwp_input_method_v2`): voice-typing and user IME (fcitx5) cannot both hold seat | Report `delivery_state=unsupported` with one reason — never displace or disable user's IME |
| Protocol caps single commit at 4000 bytes (`commit_string`) | Corrections larger than one commit must chunk without violating one-edit rule, else refuse with `delivery_reason`; covered at G2 |

---

## 7. Section 4.6 Feedback about Native Sessions: state.json Keys, 'never the surrounding user document', toasts (§411-431)
**state.json keys for native sessions**: `{"listening": true, "phase": "speaking", "models_loaded": true, "mode": "normal", "partial": "...", "last_final": "...", "ts": ...}`; `delivery_mode`/`delivery_state`/`delivery_reason` referenced in acceptance criteria §9 and risk table.

**'Never the surrounding user document'**: State file and all feedback mechanisms never write the surrounding user document text. Only the recognition final (cleaned) is typed into the focused window via native editing API; surrounding document context never part of transcript or state.

**Toasts for native start/stop/failure** (§4.6): listening-start ("Recording"; first arm preceded by one-shot "Loading…" toast while models load — §4.2bis), each final ("✔ <text>" — gated by `notify_on_final`), listening-stop ("Recording Stopped" — for ANY disarm). Partials go to state file only, not toasts.

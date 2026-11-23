# D2 — bulk text delivery grounding map (READ-ONLY research)

Repo `/home/dustin/projects/voice-typing` @ HEAD `2335a9e` (main). All cites file:line at HEAD.
Scope: PRD §4.2sexies Rev 4 — bulk-delivery controller + `TargetAdapter` SEPARATE from
`StreamingOutput`/`typing_backends.py`. Decided route (not re-litigated): `zwp_input_method_v2`
primary; GTK-class = full, foot/kitty = insert-only, ghostty = clipboard insert-fallback only (R.6);
pi chat-prompt milestone rides pi's extension seam.

---

## 1. Event-relay extension recipe (recorder_host.py → daemon)

IPC protocol: two spawn-context `mp.Queue`s + two `mp.Event`s, documented at
`voice_typing/recorder_host.py:27-78`. Exact child→daemon event payloads and construction sites:

| Event | Payload | Child construction site | Daemon dispatch |
|---|---|---|---|
| `ready` | `{device, compute_type, model, context_prompt}` | `_ready_payload()` `:864`, put `:634` | `_dispatch` `:429-431` → `_ready_evt` |
| `error` | `{msg}` | `:605, :625, :638` | `:432-434` |
| `final` | `{text}` or `{text:"", cancelled:True}` | `:644` (real, via `_child_on_final` `:643`), `:742/:745` (stale-signal sentinels in cmd loop), `:1052/:1054` (`_run_text_and_emit_final` `:984` abort/cancel sentinels) | `:437-451` → `_cancel_mark` + `self._on_final(text)` + `_final_evt` |
| `partial` | `{text}` | `_RelayFeedback.update_partial` `:1100` | `:452-454` → `_on_partial` |
| `speech` | `{}` | `:572` | `:455-456` → `_on_speech` |
| `speech_end` | `{}` | `_RelayLatency.note_speech_end` `:1135` | `:457-459` → `latency.note_speech_end` |
| `vad` | `{phase: "listening"|"speaking"}` | `_RelayFeedback.set_phase` `:1104` | `:460-468` (drops when `is_listening()` false) |
| `gone` | `{}` | `:790` | read-loop exit `:403-418` |

Reader thread: `_read_loop` `recorder_host.py:403` (started by `spawn()` `:198-202`); dispatch
`_dispatch` `:426-479`; `on_final` runs ON the reader thread (`:444-449`), matching the in-process
worker-thread model.

**Where per-utterance identities + session-generation id attach with least disruption (R.5):**
all five `("final", ...)` puts are the only construction sites — `:644, :742, :745, :1052, :1054`.
Least-disruption recipe: wrap them in one helper (e.g. `_final_payload(text, cancelled, utterance_id,
session_gen)`) and add the keys there; the daemon consumes new keys additively at the single choke
point `_dispatch:437-451` (it already reads the additive `cancelled` key, P1.M2.T7.S1 precedent;
`ready`'s `context_prompt` is the same additive-key pattern, `:864-873`). The child already owns a
per-utterance lifecycle (`aborted`/`cancelled`/`text_running` events, `:631-643`) the id can piggyback
on. `RecorderHost.text()` (`:310-338`) and the daemon run loop (`daemon.py:941+`) need no change —
the payload dict flows through whole.

**prompt_engine.py summary** (`voice_typing/prompt_engine.py`, 299 lines): child-side dynamic
context-prompt transcription executor. `trim_prompt()` `:102` (cap `_PROMPT_TOKEN_CAP` = 200 tokens
`:47`); `rolling_context_prompt(committed)` `:119` — the daemon-side formal prompt (sentences after
last `.!?` boundary, `_CONTEXT_BOUNDARY_CHARS` `:52`); `PromptedExecutor` `:143` (ONE faster-whisper
model + thread-safe mutable prompt; `set_prompt` `:181`, `prompt` `:198`, `transcribe` `:219`);
`probe_prompt_executor` `:289` (build + 1 s zeros warmup). What it feeds: injected as BOTH
`transcription_executor` and `realtime_transcription_executor` via
`augment_kwargs_with_executor` (`recorder_host.py:838-887`) → `initial_prompt` per decode (partials
AND finals; RealtimeSTT skips its TranscriptionWorker). Daemon-side push:
`daemon.py:1735-1747` (`rolling_context_prompt(self._stream.committed)` → `host.set_prompt`), clear
on arm `daemon.py:1391`. **Bulk relevance:** `_stream.committed` (screen-truth checkpoint) is the
existing committed-text source a bulk controller could mirror for its own last-confirmed state —
read-only; do not couple.

## 2. Cancel-intercept site (daemon.py)

Control socket: `ControlServer` `daemon.py:2481`; accept loop `:2586-2608` (select-poll + one daemon
thread per connection); per-connection handler `_handle` `:2606-2639` (`makefile` r/w, one JSON line
per request, flush per reply). Dispatch table `_dispatch` `:2660-2710`:
`toggle|toggle-lite` `:2668`, `start` `:2683`, `stop` `:2688`, **`cancel` `:2691-2694` →
`self._daemon.cancel()`**, `status` `:2695`, `quit` `:2697`, unknown → `{"ok":false,"error":"unknown
command: ..."}` `:2709`.

**The bulk cancel must intercept in `VoiceTypingDaemon.cancel()` (`daemon.py:1754-1798`) BEFORE the
legacy backspace compensation**, which is:

- `daemon.py:1774` `with self._lock:` (the daemon control lock, `threading.Lock` `daemon.py:637`;
  `_on_final_lock` `:644` is separate — see below)
- `:1778` `tail_len = self._pending_tail_len()`
- `:1779` `n = max(tail_len - 1, 0)` — the keystroke already deleted 1 char
- **`:1781` `self._backend.press_backspace(n)` — the exact compensation site to precede**
- `:1783-1793` host.cancel() + `_cancel_suppress_final` latch (bounded by
  `_CANCEL_SUPPRESS_TIMEOUT_S`, self-heal in `on_final` `:1186-1212`)
- `:1795` `self._reset_stream_after_cancel()` (`:1569`)

Recipe: branch at the top of `cancel()` (after the not-armed idempotent return `:1775-1778`) on
bulk/delivery mode — route the rewind through the bulk TargetAdapter
(`delete_surrounding_text(before,0)` + `commit_string` + one atomic `commit`) instead of
`press_backspace`, keeping the host.cancel + suppression-window logic shared. Entry points reaching
`cancel()`: socket `cancel` `:2691` and the evdev Backspace callback `_on_cancel_backspace`
`:1621-1630` (KeyListener reader thread, no locks held — safe to call the bulk path too).

Locks: daemon `_lock` `:637` (cancel/arms/drains); `_on_final_lock` `:644` (serializes
clean→type→record; deliberately never taken by `_lock` holders — no deadlock); `ControlServer`'s own
`_lock` `:2526` guards socket lifecycle only, NOT dispatch (dispatch threads race `on_final` —
cancel↔commit ordering is exactly what `_on_final_lock` + engine lock serialize).

`StreamingOutput` construction: `daemon.py:780-785` (unconditional; args backend, feedback,
`cfg.output.streaming`, `append_space`). Routing into it:
`on_final` `daemon.py:1142` (gate `:1145`, `_on_final_lock` `:1151`) → commit `self._stream.commit(cleaned)`
`:1281`; legacy Rev 1 path `self._backend.type_text(payload)` `:1290`. Freeze/reset sites:
`:1185/:1189, :1213/:1217, :1234/:1237, :1247 (arm_stray_echo_guard), :1345 (reset_boundary),
:1376/:1448 (reset_session on disarm), :1495 (resume on arm)`. `_on_partial` `daemon.py:1500-1517`
(gate → `self._stream.on_partial(text)` `:1516` + `latency.note_partial`). These are wired as
RecorderHost ctor callbacks at `daemon.py:868/878`.

## 3. What bulk code must NOT touch/reuse (streaming.py + typing_backends.py)

`StreamingOutput` (`voice_typing/streaming.py:180`): ctor `:205` (backend, feedback, streaming,
append_space, `revision_debounce_s=2.0` `:96`); internal `threading.Lock` `:235`; state
`_pending_leading_space` `:276`, **`_lead_sep` `:282`** (leading-separator gate: cleared on every
reset `:330/:379/:414`, set when a committed/absorbed tail ends without separator); public surface:
`committed` `:287`, `tail` `:292`, `frozen` `:297`, `frozen_session` `:302`, `pending_tail_len`
`:312`, `reset_after_cancel` `:317`, `reset_boundary` `:341`, `reset_session` `:387`, `resume`
`:428`, `arm_stray_echo_guard` `:480`, `freeze` `:500`, `note_user_keypress` `:538`, `on_partial`
`:560`, `commit` `:711`. `commit()` paths (`:711-740` docstring): frozen→absorb (no keystrokes);
extends→guarded delta; differs→minimal-diff rewind `press_backspace(len(tail)−k)` + suffix; then
append_space, checkpoint advances to text ACTUALLY TYPED.

`typing_backends.py`: `TypingBackend` ABC `:75` (`type_text` `:79`, `press_backspace` `:90`);
`WtypeBackend` `:99` (`wtype -d 12`, batched `-k Backspace` `:107/:115`); `YdotoolBackend` `:118`
(persistent ydotoold client); `make_backend()` auto-fallback wrapper `:14-17` (wtype→ydotool once).

**Bulk code must NOT call** `type_text`/`press_backspace`/`make_backend`/`StreamingOutput.*` (no
typing fallback — R: bulk adapter exposes none of that; legacy stays only for `stream-edit` mode).
**Shared-mutable-state traps:** (a) the engine commits under the daemon's `_on_final_lock`
(`daemon.py:1275-1286`) — a bulk controller sharing `_stream` state would inherit that lock-ordering
constraint ("the engine never takes a daemon lock back"); (b) `daemon.py:1738-1741` reads
`self._stream.committed` directly (prompt push) — a bulk mode changing what "committed" means must
not silently alter prompt context; (c) `Feedback` mirrors are updated inside streaming paths
(`reset_after_cancel` clears partial via `daemon.py:1590`) — bulk delivery state must go through its
own feedback keys (§4), not hijack `partial`.

## 4. ctl.py + feedback.py recipes

`ctl.py` (`voice_typing/ctl.py`, 301 lines): `_COMMANDS` tuple `:42-49` = (toggle, start, stop,
status, quit, cancel); `_ALIASES` `:55` (toggle-lite→toggle); exit codes 0/1/2/64 (`:6-16`;
`_EX_USAGE=64` `:60`); `_LOADING_HINT_DELAY=0.3` `:66`; `_SOCKET_TIMEOUT_S=10.0` `:73`, overridable
`VOICECTL_TIMEOUT` (`_socket_timeout_s` `:76`; AGENTS.md mandates `timeout 30` wrapper anyway);
`format_result(cmd, response)` `:90` — PURE; status branch `:126-171` renders the multi-line block;
`send_command` `:167-210` (sock.settimeout bounds connect+recv; wedged daemon → `ValueError` →
exit 1; one line one-shot); `_build_parser` `:236` — single optional positional `cmd`, argparse
choices deliberately OFF so usage errors exit 64 not 2; `main()` `:262-301` (alias remap → validate
→ resolve socket → send (arm cmds via loading-hint wrapper `:213`) → format → print).

**Recipe — `session [--copy]`:**
1. `ctl.py`: add `"session"` to `_COMMANDS`; add `--copy` as an argparse `store_true` flag (or a
   second positional) — but note `send_command` sends only `{"cmd": cmd}`; the flag must become part
   of the payload, so extend `send_command(socket_path, cmd, extra=None)` → `{"cmd":..., **extra}`
   (daemon `_dispatch` reads `msg.get("cmd")` only — additive keys are ignored today, harmless).
2. `daemon.py` `_dispatch` `:2660`: add `if cmd == "session": return self._daemon.session_reply(...)`
   (new method; NOT routed through `_arm_response`).
3. `format_result`: add a `session` branch (mirror the `status` branch style) rendering
   delivery_mode/delivery_state/last-confirmed-op.
4. `--copy` client side: stage via `/usr/bin/wl-copy --foreground --type text/plain;charset=utf-8`
   (verified present; the exact spawn+stdin pattern is `tools/paste-lab/ghostty_probe.py:102`, with
   `wl-paste --no-newline` verify at `:109`).

`feedback.py` (`voice_typing/feedback.py`, 264 lines): state.json schema `{"listening", "phase"
(unloaded/loading/idle/listening/speaking), "models_loaded", "mode", "partial", "last_final", "ts"}`
(docstring `:10-11`, init `:92-105`); partial disk-write throttle `_PARTIAL_WRITE_MIN_INTERVAL` `:74`
(≥10 Hz; in-memory always updated `:111-122`); `set_phase` `:124` (always writes, never notifies);
`set_models_loaded` `:135`; `set_mode` `:147`; `record_final` `:155`; `set_listening` `:173`;
`snapshot` `:195`; `notify` `:206` (Hyprland notify; NEVER on partial/phase by rule `:28`).

**Recipe — delivery fields:** add `delivery_mode`, `delivery_state`
(`inactive|active|unsupported|fault`), `delivery_reason`, `last_confirmed_op` keys to `_state` init
(additive — the `"mode"` and `"cancelled"` precedents) + one setter per field in the `set_phase`
style (always write, never notify); the bulk controller is the only writer. Render path: daemon
`status_snapshot()` `daemon.py:2275-2318` (keys: listening, mode="lite", phase, models_loaded,
load_error, partial, last_final, uptime_s, device, compute_type, model, mic_ok, mic_error,
context_prompt — additive-key pattern proven by `mic_*` and the `context_prompt` label
`_context_prompt_label()` `:2318`) → `ctl.py format_result` status branch `:126-171` (add delivery
lines after `context-prompt`).

## 5. Lab-reuse table

| Asset | What it is | G2/G3 reuse verdict |
|---|---|---|
| `tools/im-lab/wlwire.py` | Hand-rolled Wayland wire client, **stdlib only** (pywayland NOT importable in the daemon `.venv` — verified). Core + `zwp_input_method_v2` + keyboard grab; opcode tables must match protocol XML (provenance: Hyprland-vendored `input-method-unstable-v2.xml`, wlr-protocols lineage — README:29-33) | **REUSE** — this is the adapter transport skeleton |
| `tools/im-lab/im_probe.py` | Becomes the seat input method; JSON command socket (`insert`/`replace`/`preedit`/`endpreedit`/`grab`); 64 KiB-capped `im.jsonl` event log | **REUSE** — evolve into the TargetAdapter-side probe/controller |
| `tools/im-lab/field_gtk.py` | Real GTK4 `Gtk.Entry` dumping text+cursor+edit-count (`cseq`) atomically | **REUSE** — the G3 graphical-field fake target (system PyGObject Gtk4 verified working) |
| `tools/im-lab/field_term.py` | Real GNU-readline line editor in the terminal under test, dumping live buffer | **REUSE** — terminal-class G3 target |
| `tools/im-lab/imlab_run.py` | Orchestrator: private Xvfb seat + private D-Bus + Sway x11 backend (`:5, :167-172, :439` `xvfb-run dbus-run-session sway`), scripted rows, verdicts → `verdicts.jsonl` | **REUSE** — the disposable-desktop harness pattern for G2/G3 |
| `tools/im-lab/hypr_nest.py` | Nested-Hyprland attempt | **THROWAWAY** (failed: aquamarine `CBackend::create()` under software rendering; only advertisement verified) |
| `tools/paste-lab/ghostty_probe.py` | Clipboard route probe: private headless Sway, `wl-copy --foreground` staging `:102`, byte-reader instead of shell, `wl-paste --no-newline` verify `:109` | **REUSE** for the R.6 ghostty clipboard insert-fallback evidence |
| `tools/asr-lab/` | Offline engine bake-off (see below) | Context only — recognition side, not delivery |

**im-lab results** (README `tools/im-lab/README.md:41-77`, run 2026-11-22: sway 1.12 / foot 1.28 /
kitty 0.49.1 / ghostty 1.3.1 / GTK 4; 29 rows, 24 pass; evidence `verdicts.jsonl` + `im.jsonl` +
screenshot-hash pairs in mktemp dirs — auto-removed unless `--keep`, README is the durable record):
- GTK4 Entry: insert 26–40 ms cmd→field; correction = whole-span 1024 B in ONE commit, 1–2 internal
  `changed` signals per commit cycle; preedit = zero document edits; `surrounding_text` byte-exact
  cursor/anchor up to 1024 B (14+ events).
- foot 1.28 / kitty 0.49: insert exact (20 ms foot); `delete_surrounding_text` silently IGNORED;
  terminals never send surrounding text → insert-only class.
- ghostty 1.3.1: text-input activates but commit never reaches the pty (matches its IME tracker) →
  IM route dead there; clipboard insert-fallback under R.6.
- Takeover: `grab_keyboard` — keymap delivered, synthetic `b` captured (keycode 48), field untouched
  while grabbed, **`commit_string` generates zero key events** (delivery cannot self-trigger HALT).
- Unicode payload + the 951-byte paste-lab sample round-trip byte-exact; zero-diff row = zero events.
- Compositor advertisement identical live Hyprland / private Sway: `zwp_input_method_manager_v2 v1`,
  `zwp_text_input_manager_v3`, `zwp_virtual_keyboard_manager_v1`, `zwlr_data_control_manager_v1 v2`,
  `zwp_primary_selection_device_manager_v1` (README:79-84).
- Open items carried forward (README:97-113): Hyprland behavior matrix still needs a real isolated
  Hyprland row; one-IM-per-seat collision (`unavailable` event) must degrade gracefully; 4000-byte
  commit cap → chunking vs R.1 one-edit rule; terminals' ownership verification must be app-side.

**paste-lab** (`tools/paste-lab/ghostty_probe.py`; results recorded at
`plan/008_a47116bb2b79/prd_snapshot.md:266-267, :578`): 951-byte Unicode payload delivered intact as
ONE bracketed paste; 153 ms / 175 ms (two runs) shortcut-trigger→bytes-received, clipboard
pre-staged — mechanism-level only, not speech/G5 evidence. Two pasted Backspace bytes (`0x08 0x08`)
arrived as two SPACES → bulk-Backspace-over-paste is DEAD; range replacement must come from a real
editing mechanism (the IM route / cooperating-editor seam).

**asr-lab** (one paragraph, `tools/asr-lab/README.md:36-77`, per-arm JSONs in gitignored
`tools/asr-lab/results/`): on 2026-01 espeak fixtures, whisper large-v3-turbo **float16** dominates
(ttfd 0.43 s, fb_med 382 ms, WER 0.021) while turbo **float32** re-decode snowballs (fb_med
2667 ms — compute_type matters more than model size for the poll paradigm); current daemon engine
small.en f32 measures fb 521 ms / WER 0.071; streaming transducers (vosk, sherpa zipformer) show
near-zero wobble (7–13 words retracted vs 50–58) but weak accuracy on these fixtures (vosk-small
0.227, sherpa 0.596); hybrid candidate noted (transducer partials + turbo-f16 finals). Caveat:
espeak fixtures are adversarial for acoustic models; real-voice clips in `tools/asr-lab/voice/` are
the real benchmark.

## 6. IM-route environment (probed at research time, read-only)

- `pywayland` NOT importable in the daemon `.venv` (ImportError) → hand-rolled `wlwire.py` stands.
- `/usr/share/wayland-protocols/unstable/input-method/input-method-unstable-v1.xml` is the ONLY
  system input-method XML (upstream v1); the v2 XML comes from Hyprland's vendored wlr-protocol
  (im-lab README provenance) — wlwire's opcode tables are the source of truth on this box.
- `pacman -Q`: **hyprland 0.57.2-1, sway 1:1.12-4, foot 1.28.0-2, kitty 0.51.0-1, ghostty 1.4.0-2,
  gtk4 4.24.1, gtk3 3.24.52** — DRIFT vs the im-lab measurement set (hyprland 0.56.2, kitty 0.49.1,
  **ghostty 1.3.1**): the ghostty version watch has TRIGGERED (its gtk-ime fix may have landed in
  1.4.0 — retest the IM rows before trusting "ghostty = unavailable"); kitty 0.49→0.51 may change
  the delete_surrounding/surrounding-text verdicts; hyprland 0.56.2→0.57.2.
- Binaries: `/usr/bin/Xvfb`, `/usr/bin/sway`, `/usr/bin/foot`, `/usr/bin/kitty`, `/usr/bin/ghostty`,
  `/usr/bin/wl-copy` all present; **gtk4-demo / gtk3-demo MISSING** (G3 GTK field apps must be
  hand-written like `field_gtk.py`, not gtk4-demo).
- System PyGObject works: `/usr/bin/python3 -c 'gi.require_version("Gtk","4.0")'` OK (Gtk 4.24) — a
  G3 GTK field app can run on system python.

## 7. pi extension seam summary

Doc: `/home/dustin/.pi/agent/npm/node_modules/@mariozechner/.pi-coding-agent-e74iH7Md/docs/extensions.md`
(2596 lines; a second differing copy exists at `@earendil-works/pi-coding-agent/docs/extensions.md` —
the @mariozechner install is the live agent's). Extension locations (`:108-133`):
`~/.pi/agent/extensions/*.ts` (global), `.pi/extensions/*.ts` (project-local), plus
`settings.json` `packages`/`extensions` paths; imports include `@mariozechner/pi-coding-agent`
(ExtensionAPI), `@mariozechner/pi-tui` (TUI components), node builtins; npm deps resolve from a
neighbor `package.json`. Lifecycle: `pi.on("session_start", (event, ctx) => …)` is the standard hook;
`ctx.hasUI` (`:860`) must gate UI installs (extensions can run headless).

- **`ctx.ui.setEditorComponent(factory)`** (`:2258-2268`, Custom Editor section `:2387-2440`):
  factory `(tui, theme, keybindings) => new CustomEditor(...)`. Contract: extend `CustomEditor`
  (NOT base `Editor`) to keep app keybindings (escape/ctrl+d/model switching); call
  `super.handleInput(data)` for unhandled keys; `ctx.ui.getEditorComponent()` first to capture/wrap
  the previous editor (single-slot — compose by wrapping); `setEditorComponent(undefined)` restores
  default. `CustomEditor` subclasses own the editor buffer and receive raw input — full programmatic
  control of prompt text on pi's event loop.
- **`ctx.fork(entryId, {position})`** (`:1024-1052`): `position: "before"` (default) forks before
  the selected user message AND restores that prompt into the editor; `"at"` duplicates the active
  path without restoring editor text; `withSession(ctx)` runs post-switch against the fresh
  replacement-session context (never captured old ctx — documented footgun). NOTE: fork takes an
  ENTRY ID of an existing session entry — it is a session-tree restore primitive, not a
  text-injection API; the chat-prompt adapter gets arbitrary text in via its own editor, not fork.
- **Cooperating-editor TargetAdapter recipe (pi milestone):** a project-local extension
  (`.pi/extensions/…`) on `session_start` (gated on `ctx.hasUI`) installs a `CustomEditor` subclass
  that (a) owns/renders the prompt buffer, (b) opens or connects a local AF_UNIX control socket
  speaking the voicectl-style one-JSON-line protocol (insert/replace/cancel/read), (c) applies ops
  as buffer edits on pi's event loop = true range replacement with zero keystrokes. The
  daemon-side bulk TargetAdapter for the "pi chat prompt" target speaks that socket. Constraints:
  one editor slot (wrap-don't-replace), TS runtime, extension runs with full user permissions,
  `ctx.ui` calls only valid with UI.

## 8. plan/007 realtimestt_internals.md — drift check

Doc: `plan/007_cfc245548aec/architecture/realtimestt_internals.md` (67 lines; RealtimeSTT 1.0.2 —
unchanged). Key symbols re-located at HEAD:

| 007 cite | HEAD now | Note |
|---|---|---|
| `daemon.py:160-216 cfg_to_kwargs` | `daemon.py:185` | shifted |
| `_FIXED_KWARGS daemon.py:99-112` | `daemon.py:111` | `use_main_model_for_realtime=True` single-model path retained (`:202/:211`) |
| `_PARTIAL_CALLBACK_ATTR daemon.py:120-124` | `daemon.py:128` | `on_realtime_transcription_stabilized` |
| `recorder_host.py:440-620 _child_main` | `recorder_host.py:497 _worker_main` | renamed + grown (cancel/prompt/stale-signal logic) |
| `recorder_host.py:332-382` reader dispatch | `recorder_host.py:426 _dispatch` | shifted |
| `recorder_host.py:587-622 _clear_recorder_audio` | `recorder_host.py:892` | shifted |

Semantic drift: the doc's §7 "Poke slot" (prompt not deliverable while text() blocks; finals
unpokable without rebuild) is **superseded** — P1.M2.T5.S1's `PromptedExecutor` injection
(`prompt_engine.py:143`, `recorder_host.py:838`) makes BOTH partials and finals dynamically prompted
(README of prompt_engine explains the executor route); the `("prompt", …)` cmd is read between
utterances by design. The doc's lite-mode traps predate the Rev 2 single-mode collapse. Its
abort/`clear_audio_queue`/double-type analysis remains accurate (the `_clear_recorder_audio`
workaround is now at `recorder_host.py:892-935`).

## 9. Open risks

1. **ghostty 1.4.0 installed vs 1.3.1 measured** — the IM-unavailable verdict may be stale; retest
   im-lab ghostty rows before locking the R.6 clipboard fallback as permanent. kitty 0.51 /
   hyprland 0.57.2 similarly untested vs the 2026-11-22 matrix.
2. **Hyprland real-session row still missing** — nested Hyprland failed (aquamarine); G3 needs an
   isolated real Hyprland session before any "works on the operator's desktop" claim (im-lab README
   open item).
3. **One-IM-per-seat collision** — a user IME (fcitx5) would conflict; `unavailable` event handling
   must degrade gracefully (delivery_state `unsupported`/`fault` per §4 recipe).
4. **4000-byte commit cap** vs R.1 one-edit rule — pathological finals need a chunking policy.
5. **Terminals send no surrounding text** — verification/ownership in foot/kitty must be app-side
   (readline state / pi seam), not IM-side.
6. **GTK decomposes a correcting commit** into internal delete+insert (1–2 `changed` signals in one
   commit cycle) — "one rendered frame" needs frame-level instrumentation in G3.
7. **`_stream.committed` coupling** — the context-prompt push (`daemon.py:1735-1747`) reads it; bulk
   mode must not redefine it implicitly; prompt source for bulk mode needs an explicit decision.
8. **Two differing extensions.md copies** on disk — pin the seam doc version when the pi milestone
   starts.
9. **`session`/`--copy` payload shape** — `send_command` currently sends `{"cmd": cmd}` only; the
   `--copy` flag needs an additive-payload extension (daemon `_dispatch` ignores unknown keys today,
   so old daemons fail safe with unknown-command/ignore rather than wedge).

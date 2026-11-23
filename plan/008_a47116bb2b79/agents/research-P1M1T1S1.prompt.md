Create a PRP for Subtask P1.M1.T1.S1 of the PRD. Store it at plan/008_a47116bb2b79/P1M1T1S1/PRP.md.

SCOPE: Write ONLY this item's PRP (P1.M1.T1.S1). You were asked for ONE PRP. Writing PRPs for other items in this session is allowed ONLY after you clear the MULTI-PRP BATCHING POLICY in the prompt (full task tree + full PRD + thorough per-item research for EVERY PRP you write). When in doubt, write one.
<item_title>Run and record the baseline suite numbers</item_title>
<item_description>CONTRACT DEFINITION:
1. RESEARCH NOTE: numbers already measured at 2335a9e — see plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md Part A: 379 passed / 20 failed across 15 pure suites (commit 10F/22P; core 2F/32P; freeze 4F/22P; test_streaming.py 3P/4F real-model 106 s; zero_diff_rewind 3/3; all others green).
2. INPUT: repo at 2335a9e, tree clean except plan/.
3. LOGIC: re-run the 15 suites listed in the research doc, one file per call, `timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q` with bash-tool timeout above it (AGENTS.md discipline; NEVER run test_feed_audio/test_daemon/test_recorder_host/test_cuda_check, tests/*.sh, the daemon, or voicectl untimed). Write the durable baseline (counts + failure names + one-line reasons) to tests/G1_BASELINE.md — bounded, no transcripts.
4. OUTPUT: committed baseline doc; numbers must match the research record (investigate any drift before any code change).
5. DOCS: Mode A — tests/G1_BASELINE.md is the doc; nothing else changes.</item_description>
<prd_selectors>["h2.3","h3.6","h2.5"]</prd_selectors>
<selected_prd_content>
heading:h2.3:
## 4. Architecture

```
                       ┌────────────────────────────────────────────┐
                       │  voice-typing daemon (Python, uv project)  │
 PipeWire default mic ─►  RealtimeSTT AudioToTextRecorder           │
                       │   ├─ VAD (webrtc+silero): segments only    │
                       │   ├─ realtime model small.en ──► partials ─┼──► state file (JSON) ──► voicectl status / anything
                       │   │                                        ├──► hyprctl notify (replaceable one-liner)
                       │   └─ final model distil-large-v3 ─► final ─┼──► typing backend:
                       │                                            │      wtype (default) | ydotool | null
                       │  control: unix socket (JSON lines)         │
                       └────────────────▲───────────────────────────┘
                                        │
                          voicectl CLI (toggle/start/stop/status/quit)
```

### 4.1 Repository layout

```
/home/dustin/projects/voice-typing/
├── PRD.md                      # this file
├── README.md                   # usage doc (write last, keep short)
├── pyproject.toml              # uv-managed, python >=3.12,<3.13
├── uv.lock
├── voice_typing/
│   ├── __init__.py
│   ├── daemon.py               # main loop, control socket, lifecycle orchestration
│   ├── recorder_host.py        # owns AudioToTextRecorder in a spawn child subprocess (VRAM reclamation, §4.2bis)
│   ├── cuda_check.py           # ctranslate2 CUDA probe + CPU-fallback resolution (§4.4)
│   ├── config.py               # dataclass + TOML loader (see §4.5)
│   ├── typing_backends.py      # wtype / ydotool / null implementations
│   ├── feedback.py             # state file writer + hyprctl notify
│   ├── textproc.py             # normalization + hallucination filter
│   ├── ctl.py                  # voicectl client CLI
│   ├── prefetch.py             # install-time model prefetch into the HF cache
│   ├── launch_daemon.sh        # ExecStart wrapper: LD_LIBRARY_PATH + HF_HUB_OFFLINE + WAYLAND_DISPLAY import
├── config.toml                 # default config, self-documenting comments
├── hypr-binds.conf             # Hyprland keybinds, sourced from hyprland.conf (§4.10)
├── systemd/voice-typing.service# user service (installed by install.sh)
├── install.sh                  # idempotent: uv sync, model prefetch, service install
├── tests/
│   ├── make_test_audio.sh      # espeak-ng → WAVs incl. pause-laden ones
│   ├── test_feed_audio.py      # offline pipeline test via feed_audio (no mic)
│   ├── e2e_virtual_mic.sh      # PipeWire null-sink + pw-cat E2E, asserts finals via state.json
│   └── test_textproc.py        # pure-python unit tests
└── .gitignore                  # .venv, __pycache__, models/, *.wav under tests/out/
```

### 4.2 The daemon (`daemon.py`)

Single process, three concerns:

1. **Recorder loop (main thread).** The `AudioToTextRecorder` is constructed **lazily on first arm** (§4.2bis), not at daemon boot; until then `recorder is None` and the loop has nothing to transcribe.
   ```python
   recorder = None                      # built on first arm — see §4.2bis (lazy load)
   while not shutdown_requested:
       if recorder is None:
           time.sleep(0.05); continue   # no models loaded yet → idle, ~0 VRAM
       if listening.is_set():
           recorder.text(on_final)      # blocks until one utterance finalizes → on_final types it → returns; if a stop was requested mid-utterance the loop drains here (lets this final land, then disarms) instead of re-listening (#2)
       else:
           time.sleep(0.05)
   if recorder is not None:
       recorder.shutdown()
   ```
   `on_final(text)` → `textproc.clean()` → if non-empty: typing backend types `text + " "`; feedback shows the final; log with timestamps.
   CRITICAL: the loop never exits on silence. `recorder.text()` returning is *normal segmentation*, not session end. Verify RealtimeSTT v1.x API against its README before coding — method names above are from v1.0.x.

2. **Listening gate.** A `threading.Event` (`listening`). Toggle/start/stop flips it. **Stop is IMMEDIATE by default (Rev 3):** an explicit stop/toggle-off disarms NOW — mic off, listen gate cleared, racing final dropped by the `on_final` gate, tail stays typed as-is; it never waits on the child's decoder ("all the way, no exceptions"). The Rev 2 graceful drain (let the in-flight `text()` return its natural final, bounded by a few-seconds watchdog, then disarm) is OPT-IN via `asr.graceful_stop = true`. Either way a stop can never hang, and any final arriving after disarm is dropped. Prefer constructing the recorder once (on first arm, per §4.2bis) and keeping it resident afterward = instant re-toggle.

3. **Control socket (background thread).** `SOCK_STREAM` unix socket at `$XDG_RUNTIME_DIR/voice-typing/control.sock` (mkdir 0700). Protocol: one JSON object per line in, one per line out.
   * `{"cmd":"toggle"}` → `{"ok":true,"listening":true}`
   * `{"cmd":"start"}` / `{"cmd":"stop"}` / `{"cmd":"status"}` → `{"ok":true,"listening":...,"partial":"...","uptime_s":...,"mode":"normal"|"lite"}`
   * `{"cmd":"toggle-lite"}` / `{"cmd":"start-lite"}` → arm in lite mode (§4.2ter); same payload with `mode` reflecting the requested mode.

* `{"cmd":"cancel"}` → §4.2quater: rewind + drop the in-flight fragment, keep listening (`{"ok":true,"listening":true}`); no-op when nothing is in flight.
* `{"cmd":"quit"}` → clean shutdown.
  Unknown cmd → `{"ok":false,"error":"..."}`. Remove stale socket file on startup.

Partial callbacks: wire `on_realtime_transcription_stabilized` (preferred; falls back to `on_realtime_transcription_update` if stabilized proves too laggy) → `feedback.update_partial(text)`. Also wire `on_recording_start`/`on_vad_detect_start` etc. to feedback state transitions (`idle`/`listening`/`speaking`) if available.

Logging: python `logging` to stderr (journald picks it up under systemd) at INFO; DEBUG via config. Log per-utterance: t\_speech\_end (when VAD closed), t\_final\_ready, t\_typed, and the text. These timestamps are what the latency test reads.

### 4.2bis Model lifecycle — lazy load on first arm

Models MUST NOT load at daemon boot. The daemon starts with no recorder, no CUDA context, and \~0 VRAM. Construction of the `AudioToTextRecorder` — which loads `small.en` + `distil-large-v3` onto the GPU (§4.4 kwargs; \~1–3 s, \~1.5–3 GB VRAM in float16) — is deferred to the **first** `start`/`toggle` that arms the mic. After that first arm the recorder stays resident so the *second* and later arms are instant. It is torn down on `quit` / daemon shutdown, AND after `auto_unload_idle_seconds` (default 30 min) of sitting disarmed (see **Idle unload** below) — so the load cost is paid once per \~30 min of *actual use*, not once per boot. The goal: stop taxing the GPU both on boots where the feature is never used AND after a one-off use.

**Implementation note (recorder-host subprocess):** the `AudioToTextRecorder` is NOT constructed in the daemon process. On the first arm the daemon spawns a managed **child subprocess** (`voice_typing/recorder_host.py`, `RecorderHost`); that child owns the recorder and ALL CUDA contexts. Arm/disarm/text/abort/shutdown are proxied over multiprocessing queues, and partials/finals/VAD events stream back to a daemon reader thread. Rationale: RealtimeSTT's realtime model runs on an in-process thread whose CUDA primary context is unreleasable until the owning process exits, so idle-unload (below) and `quit` can only reach \~0 VRAM by **terminating the child's process group** (`os.setsid` in the child + `os.killpg` in the daemon). The daemon process is therefore *intended* to never import `RealtimeSTT`/`torch`/`ctranslate2` and never create a CUDA context — **caveat: `voicectl status` currently violates this; see BUGS.md VT-001.** RealtimeSTT's \~90 s `recorder.shutdown()` wedge is sidestepped entirely: teardown = `proc.join(5s)` then `SIGKILL` the group.

Lifecycle states (surfaced via `voicectl status` and the state file, §4.6/§4.8):

* `unloaded` — daemon up, no recorder, \~0 VRAM. This is the boot state.
* `loading` — first arm in progress; constructing recorder + loading models. The arm command blocks here; `voicectl` prints a `loading models…` hint.
* `loaded` / not listening — recorder resident, mic disarmed. Instant arm from here (in the SAME mode it was loaded — switching to the other mode reloads, §4.2ter). After `auto_unload_idle_seconds` in this state with no arm, the watchdog tears the recorder down → back to `unloaded` (see **Idle unload**).
* `loaded` / listening — armed, transcribing.

Concurrency & failure rules:

* A second arm while `loading` MUST NOT start a second load — it waits on the in-flight one (the load is single-flight under a lock).
* If the load fails (CUDA init error, missing model, cuDNN load failure), the daemon returns to `unloaded`, the arm command returns `{"ok":false,"error":"..."}`, and `status` reports the error + the CPU-fallback hint (§4.4). It MUST NOT leave a half-constructed recorder behind.
* The control-socket handlers for `start`/`toggle` (§4.2 #3) acquire/await the single-flight load, then proceed to the existing arm path. `status` reports `models_loaded: bool` so callers/UI can tell `loading` from `armed`.
* The idle auto-stop (§4.5) disarms the mic but does NOT itself unload — it hands off to the slower idle-unload timer (below), which is what eventually frees VRAM.
* Teardown (idle-unload and `quit`) runs under the SAME single-flight lock as load, so an arm that races an in-flight teardown waits for it, then loads fresh — an arm can never see a half-torn-down recorder.

**Idle unload.** A background watchdog reclaims VRAM after a one-off use: when the recorder has sat in `loaded / not listening` for `asr.auto_unload_idle_seconds` (default `1800.0` = 30 min; `0` disables), it tears the recorder down, logs `voice-typing idle-unload: 1800.0s disarmed; unloading models`, transitions to `unloaded`, and frees the \~1.5–3 GB VRAM. The clock starts when the mic disarms (manual stop, toggle-off, or the §4.5 idle auto-stop) and resets on any arm; time spent listening does not count. The next arm then pays the \~1–3 s reload, same as a session's first arm. **Hard requirement — bounded teardown:** the `recorder.shutdown()` call invoked here MUST be non-blocking and complete in well under the arm-latency budget. It MUST NOT reproduce the \~90 s teardown hang currently seen on every `quit` (journal: `run() loop exiting` → 90 s → systemd `SIGKILL` / `Failed with result 'timeout'`), because idle-unload would trigger that hang every 30 min AND block any re-arm that races it under the single-flight lock. If `recorder.shutdown()` cannot be made to complete promptly, guard it with a hard timeout plus force-cleanup of the recorder's worker threads / `transcript_process` so VRAM is actually released. Making teardown bounded is therefore a **prerequisite** for this feature (risk row, §8). **(Resolved by the recorder-host subprocess model above: the daemon `killpg`s the child group after a 5 s join, so VRAM is force-released regardless of `recorder.shutdown()`'s behavior.)**

### 4.2ter Lite mode — small-model-only quick dictation

A second arming mode for short, speed-critical snippets (URLs, shell commands, short replies) where latency matters more than accuracy. Lite mode loads **only** the small realtime model and uses it as both the partials source AND the final-pass model — the large `distil-large-v3` never loads, never runs. Result: \~half the VRAM and markedly faster finals, at lower accuracy. It is entered via a **separate keybind / command**, never by the normal toggle.

**Configuration** (`[asr]`):

* `lite_model` (default `"small.en"`): the single model loaded in lite mode, used for BOTH realtime partials and final transcription. On CPU fallback it auto-downgrades via cuda\_check like the normal models; the approved CPU lite substitute is `tiny.en`.

**Recorder construction (lite):** the recorder-host child builds the recorder with `model = lite_model`, `realtime_model_type = lite_model`, and `use_main_model_for_realtime = True`. Verified against RealtimeSTT v1.0.2: with `use_main_model_for_realtime=True` the separate realtime engine is NOT initialized (`_initialize_realtime_transcription_model` early-returns), so exactly ONE model (`lite_model`) is resident — the large final model is never constructed. All other kwargs (device, compute\_type, language, silero) are identical to normal mode EXCEPT `post_speech_silence_duration`, which lite overrides with its own snugger threshold (`lite_post_speech_silence_duration`, §4.5) — see the latency note below for why this is load-bearing. `on_final` therefore yields `lite_model` finals — fast, lower-accuracy — over the SAME clean→type→record path as normal mode (§4.2).

**The silence gate, not the model, is the perceived-latency bottleneck (latency-log finding).** The per-utterance latency line clocks `speech_end_to_final_ms` from `on_vad_stop`, which fires only AFTER `post_speech_silence_duration` of trailing silence. On this GPU the small model's final pass is \~80 ms vs the large model's \~130 ms — a \~50 ms win that is SWAMPED by the silence wait, which is identical across modes unless lite overrides it. (Observed live: a 1.5 s `post_speech_silence_duration` made lite feel "no faster than the big model" even though the small model was in fact \~1.6× faster at transcription.) Therefore lite MUST use its own shorter `post_speech_silence_duration` (default `0.5` — the small model is fast and quips are short, so the big model's thinking-pause cushion isn't needed); that is what makes lite actually FEEL instant, cutting stop→text latency from \~1.6 s to \~0.6 s. Tunable: \~0.3 = razor-snappy (may split a brief pause into two finals), \~0.6 = safe. **Rev 2 (§4.2quater):** under streaming the endpointer no longer gates *visible* output — words are typed as they are spoken — it only delays the commit/correction pass, so the default rises to `0.8` (halving mid-thought cuts for +0.3 s commit latency). The "must be snug" rationale above applied to the Rev 1 output model, where finals were the only visible output; `0.5` remains the razor-snappy setting.

**Mode is a spawn-time property of the recorder-host child; the daemon tracks `self._mode` (`"normal"` | `"lite"`).** The resident child is always in exactly one mode. Arming rules:

* Arm in mode X while resident child is mode X → instant arm (models already resident in the right mode).
* Arm in mode X while resident child is the OTHER mode → tear the child down and respawn it in mode X (\~1–3 s reload, same bounded teardown as idle-unload, "Loading…" toast). I.e. **switching modes costs one reload.**
* Arm in mode X while unloaded → spawn in mode X (same as a session's first arm).
  Idle-unload (§4.2bis) tears down whichever mode is resident; the next arm reloads in whatever mode that arm requests. The graceful drain (§4.2 #2) and idle auto-stop (§4.5) apply identically in lite mode.

**Commands / keybind:** `voicectl toggle-lite` / `voicectl start-lite` arm in lite mode (a clean toggle independent of the normal toggle, so each keybind is unambiguous); `voicectl toggle` / `start` arm in normal mode; `voicectl stop` disarms either. Two Hyprland binds (§4.10): `Ctrl+Alt+Super+D` → `toggle` (big/normal model) and `Alt+Super+D` → `toggle-lite` (little/lite model).

**State / status:** `state.json` gains `"mode": "normal" | "lite"` (written on every arm/disarm alongside the existing fields); `voicectl status` reports `mode:` and prefixes lite with `⚡` so the user can see at a glance which mode is armed. Start/stop toasts stay `"Recording"` / `"Recording Stopped"` in either mode (the keybind itself disambiguates); finals still toast `✔ <text>` per `notify_on_final`.

**Why a reload on switch is accepted:** it is the same \~1–3 s cost already paid on first-arm and after idle-unload, and a user picks a mode for a stretch of use rather than toggling per utterance. A no-reload alternative — committing the realtime partial from the resident two-model recorder — was REJECTED: it keeps the large model loaded, still spins its final pass per utterance, and so delivers neither the VRAM nor the latency benefit that motivates lite mode.

### 4.2quater Streaming dictation — typed partials, in-place revision, Backspace-cancel (Rev 2; small-model/lite path only)

The Rev 1 output model — partials visible only in the status display, one append per silence-triggered final, and a snug endpointer existing largely to force frequent visible output — is REPLACED on this path by phone-style dictation: **words are typed into the focused window as they are spoken, revised in place, and the mic never pauses for decoding.** Scope: the small-model recorder — the ONLY mode (normal mode removed, §1).

**Output state machine (daemon process).** The daemon tracks two strings per armed session:

* `committed` — finalized text, ending at the last commit checkpoint;
* `tail` — everything typed since that checkpoint (the current utterance: tentative, revisable, no trailing space while tentative).

1. **Partial typing (minimal-diff revision).** On each stabilized-partial event (existing IPC): compare the new partial against the currently typed `tail` and touch ONLY what changed. Compute `k` = length of the longest common prefix of the typed `tail` and the new partial (per-character, case-insensitive — the casing guard lowercases mid-sentence fragments while decoder partials stay capitalized — but counted and sliced on the ORIGINAL characters, so a casefold-length change can never desync the indices). Then `press_backspace(len(tail) − k)` — exactly the diverging suffix, NEVER the whole string — and type the corrected suffix (the new partial from offset `k`, through the deterministic guards with the on-screen prefix as casing context). Degenerate cases: pure extension (`k = len(tail)`) → type only the delta with ZERO backspaces; identical text → full no-op; a whole-tail rewind is correct ONLY when the partial genuinely shares no prefix with the tail (fresh start / total rewrite). Backspacing the entire string on every revision is a defect, not the design (user-reported against the first Rev 2 build; pinned by T8a/T8b). Mid-utterance revision is DEBOUNCED for smoothness (code constant, not config): partial typing is extend-only while divergence is fresh — momentary decoder wobble that grows back past the tail re-converges as a pure extension with zero backspaces — and a rewind fires only after the divergence has persisted ≥2 s, using the latest partial (one minimal-diff correction per sustained divergence; the window re-arms after each). The commit's correction is authoritative and never debounced; the common case is zero mid-utterance rewinds and exactly one correction, at the end of the utterance.
2. **Commit (silence trips).** The child's small.en re-decodes the complete utterance (the old "final", now a *correction pass*): if it differs from the typed `tail`, revise with the SAME minimal-diff rule as partial typing (backspace exactly `len(tail) − k` for common-prefix `k`, type only the corrected suffix — a commit that confirms most of the typed tail rewinds only the diverging suffix, and a commit that extends it rewinds nothing); append the trailing space (`output.append_space`); advance the checkpoint; refresh the rolling context prompt (below). Existing gates unchanged: `textproc.clean` (blocklist/min\_chars) and the `listening` gate; a rejected final freezes the `tail` as-is.
3. **Drain unchanged** (§4.2 #2) — an explicit stop mid-speech still lets the correction pass land before disarming.
4. **Stranded tail → FREEZE, never delete** (user decision). If no commit can ever land (drain-watchdog abort, child death), the tail stays on screen exactly as last shown. The ONLY thing that deletes typed text is an explicit cancel (below).
5. **User-typing protection (Rev 3 — HALT).** Any non-Backspace keypress observed while armed → DISARM dictation entirely: mic off, engine session reset, no drain, no late keystrokes; the tail stays typed as-is (re-arm with the hotkey). Modifier-only presses (Ctrl/Super/Alt/Shift/Caps etc. — they insert no text and are the arm chord's own keys) do not count, and a 1.5 s grace after arming absorbs the hotkey's own keystrokes. Legacy per-utterance freeze (lift at the next boundary) remains available as `cancel.keypress_action = "freeze"`.

**Typing backend additions.** `press_backspace(n)` MUST delete exactly n characters in an ordinary text field (wtype: repeat `-k Backspace`; ydotool: repeat the backspace keycode; batched so \~80 chars rewind in <150 ms). Revision correctness assumes the cursor sits at the end of our typed text and one keystroke deletes one character — the window where that can be false is closed by the Rev 3 HALT rule. **Accounting invariant (Rev 3):** a rewind MUST be clamped to the engine's own pending tail (never more chars than the engine typed since the checkpoint), every rewind is journaled (count + tail length), and every DROPPED final (cancel-suppression window, sentinel loss) MUST reset the utterance boundary — the tail never accumulates across dropped finals.

**Backspace-cancel.**

* **Listener:** a passive, read-only (never `EVIOCGRAB`) evdev listener thread in the daemon process over every keyboard `/dev/input/event*` node (auto-enumerate: EV\_KEY devices that expose KEY\_BACKSPACE; `[cancel].devices` overrides). The user is in the `input` group (§2) — no permission changes. `python-evdev` is the implementation dep.
* **Trigger:** KEY\_BACKSPACE press while armed AND a `tail` is pending → cancel: rewind `max(len(tail)−1, 0)` characters (the physical keystroke itself already deleted one — compensate by subtraction, never by re-typing), drop the child's in-flight utterance (host abort discards its buffered audio), keep listening — just say the sentence again. **Idempotent:** further Backspaces with no pending tail are plain user edits and are never compensated.
* **Fallback:** `voicectl cancel` (control-socket cmd, §4.2 #3) runs the identical path — keybind-able when no keyboard node is readable (log once at arm; §4.10) and the automated-test seam (T8e).

**Rolling context prompt.** Every decode is conditioned on the committed text **back to the last sentence boundary** (last `.`/`!`/`?`), capped at \~200 tokens (Whisper's \~224-token prompt budget — code constant): partial decodes via `initial_prompt_realtime`, commit decodes via `initial_prompt`. Both kwargs exist in the installed RealtimeSTT 1.0.2 but are constructor-static — the child MUST make them dynamic (update between utterances); if that fails, degrade to context-free decoding and log (never crash). This is the primary fix for mid-paragraph fragments starting capitalized or acquiring spurious trailing periods: the decoder is told it is *continuing*, not starting.

**Deterministic guards (textproc, Rev 2).** Applied at typing time (pure, unit-tested):

* **Casing:** if `committed` does not end a sentence (no terminal `. ! ?`), lowercase the fragment's first word.
* **Period:** if the casing guard fired (we joined mid-sentence), strip one trailing `.` from the committed fragment — a decoder closing a sentence it was just told it was continuing is spurious by definition.
  Rev 1 `clean()` rules (blocklist, min\_chars, whitespace) are unchanged.

**Unchanged:** VAD segmentation (it now only triggers commits); feedback/state file/toasts (the `partial` field mirrors the live tail; `record_final` records the committed text); lazy load, idle unload, idle auto-stop, and the lite recorder construction (§4.2ter) including single-model `use_main_model_for_realtime=True`; `output.streaming=false` restores Rev 1 append-only behavior as a rollback hatch (§4.5).

### 4.2quinquies Media ducking while listening — pause/duck speakers at arm (spec'd 2026-11-18; implement next round)

**Problem.** The mic has no acoustic echo cancellation: anything the speakers play during dictation is transcribed as speech (music, video, notification dings). Every second of media bleed is pure WER — it is a leading source of "wrong words that change meaning" when dictating on a machine that is also playing audio. The tool should get media out of the way for exactly as long as the mic is hot, and put it back EXACTLY as it found it.

**Mechanism — two tiers, strictly best-effort (verified on this machine 2026-11-18: PipeWire 1.6.9 with PulseAudio compatibility, `playerctl`/`wpctl`/`pactl` installed, 4 live MPRIS endpoints):**

1. **MPRIS pause (primary, default).** At arm: enumerate MPRIS players; for each whose `PlaybackStatus` is `Playing`, record its bus name and pause it (`playerctl --all-players pause` or direct D-Bus; subprocess under a hard timeout). At disarm: resume ONLY players (a) that WE paused, (b) that were `Playing` before we paused them, and (c) that are still `Paused` now. Rule (c) is the user-sovereignty guard: if the user resumed a player themselves mid-dictation, or paused a different one, we never fight them — restore is additive, never destructive.
2. **Sink-volume duck (fallback / non-MPRIS audio).** At arm: read and store the default sink's current volume (`wpctl get-volume @DEFAULT_AUDIO_SINK@`), then set `duck_volume_pct`. At disarm: restore the stored value ONLY if the current volume still equals what we last set — if the user touched the volume mid-dictation, THEIR value wins and we do nothing. This comparison-before-restore is the whole point: a restore that clobbers a user's manual change is worse than not ducking.

NOT chosen: PipeWire `module-role-ducking` (module availability varies across PipeWire versions and it requires a live duck-role stream we do not otherwise need — the classic Linux crapshoot; revisit if WirePlumber grows first-class ducking).

**Lifecycle wiring.** Engage where the arm toast fires; release on EVERY disarm path: manual stop/toggle-off, idle auto-stop, Rev 3 HALT keypress disarm, daemon quit — but NOT on Backspace-cancel (the mic stays hot). Crash-safety: a `ducked` field in the feedback state file lets a post-crash restart self-heal (best-effort release at startup when set), and the systemd unit gets an `ExecStopPost` best-effort restore.

**Failure discipline (non-negotiable, mirrors the PRD §8 philosophy).** Ducking is an enhancement, NEVER a gate: every audio call is subprocess/bounded (`timeout` ≤1 s), failures journal ONE line and are otherwise invisible, and arm latency must not measurably change (engage runs concurrently with recorder arming; the arm does not wait for it). Engage/release are idempotent — repeated arms must not stack pauses or volume writes, and release without a prior engage is a no-op.

**Config (`[audio]` section — add to config.py + config.toml in lockstep with the key-set test, 24 → 26 keys).**

* `duck_mode = "off"` — `"mpris"` | `"volume"` | `"off"`. Ships `"off"` until implemented; default flips to `"mpris"` the round this lands.
* `duck_volume_pct = 15` — target volume for the `"volume"` tier.

**Tests (unit, no real audio — an `AudioDucker` protocol with engage()/release() and a mocked backend):** (a) resume-only-what-we-paused (a player the user paused mid-dictation stays paused); (b) volume restore skipped when the user changed volume mid-dictation; (c) release fires on every disarm path incl. HALT and auto-stop; (d) a hung backend call (mocked 5 s sleep) does not delay arm beyond bound; (e) engage/release idempotence; (f) crash-recovery: `ducked` flag in state → release at next daemon start.

**Acceptance.** Music playing → arm → music pauses within \~1 s and resumes at stop; video in a non-MPRIS app with `duck_mode="volume"` → volume ducks to 15% and restores exactly; the user changing volume or player state mid-dictation is never overridden; `journalctl` shows the engage/release lines; with `duck_mode="off"` behavior is byte-identical to today.

### 4.2sexies Bulk text delivery — paste as policy (Rev 4; active when `output.delivery="bulk-text"`)

**Status: normative specification; NOT implemented and NOT verified in any real field.** Everything in this subsection uses MUST in the PRD sense. Labels R.1–R.8 are referenced from §6/§7/§8.

**R.1 The experience (binding user requirements).**

* Words MUST become visible in the **focused editable field** as recognition updates arrive — the operator reads the newest words at the insertion point while still speaking. No wait-for-silence, no "survived N partials / one word behind the frontier" batching (the 2026-11-18 draft's stability gate is REVOKED — it violates this), no minimum batch size or flush timer before the first words, never a sentence-end dump. A caption bar, notification, state-file field, or session transcript is NOT a substitute; no caption window is required by this spec.
* A correction MUST land as ONE visible edit that replaces only the tool's OWN verified range — no erase animation, no blank frame, no per-character retype, no caret walk. An unchanged result MUST emit ZERO visible edits (zero-diff guard, generalized: compare RENDERED text after the existing language/spacing guards; two strings that render identically ⇒ zero events; real case/punctuation/word differences are never declared equal).
* **Event-count law:** judge every delivery primitive by operations-per-change — insertion = 1, correction = 1, zero-diff = 0. Pacing is not a lever. Synthesized per-character typing and Backspace chains are FORBIDDEN in this mode; there is no fallback to the §4.3 typing backends.
* Correction reach is NOT bounded by utterance (user decision 2026-11-19: proposed scope limits were rejected). Replacement may reach any OWNED dictation text provided it is imperceptible; the safety boundary is OWNERSHIP, never size.
* The bar: beat the operator's \~110 wpm type-then-proofread effective throughput, counting corrections, recovery, and rereading time.

**R.2 Evidence and provenance (2026-11-20; do not re-derive, do not over-claim).**

| Observation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Witness and limits                                                                                                                                                                                                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 951-byte Unicode payload delivered intact as ONE bracketed paste; 153 ms and 175 ms in two runs from shortcut-trigger to bytes-received (clipboard pre-staged; includes test overhead; NOT speech, render, or end-to-end timing)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | A Python byte reader inside disposable Ghostty 1.3.1 under a private headless Sway (`tools/paste-lab/ghostty_probe.py`). NOT the operator, NOT pi's editor, NOT the real desktop. An earlier synthetic-keyboard variant FAILED to deliver — process success is not acceptance. |
| Two pasted Backspace bytes (0x08 0x08) arrived as two SPACES followed by "end"                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Same probe, raw payload. Bulk-Backspace-over-paste is DEAD on this route; range replacement must come from a real editing mechanism.                                                                                                                                           |
| Engine facts: large-v3-turbo\@float16 polled = 382 ms median word lag, WER 0.021; streaming transducers = 42–52% wrong words on the operator's real voice (transducer migration DEAD)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | `tools/asr-lab/` bake-off + real-voice clips.                                                                                                                                                                                                                                  |
| Input-method-v2 route is LIVE and capable on GTK-class fields (2026-11-22): insert 26–40 ms command→visible-field with exact cursor; ONE atomic commit (`delete_surrounding_text(before,0)` + `commit_string` + `commit(serial)`) corrects a whole 1024-byte span byte-exactly — GTK fires 1–2 internal `changed` signals within one commit cycle, frame-level single-edit still unverified; preedit carries live updates with ZERO document edits and a matching final lands as one atomic preedit→commit transition; `surrounding_text` returns byte-exact cursor/anchor (target-CONFIRMED text, R.5's third value); `grab_keyboard` key events reach the adapter while the field stays untouched and IM commits generate ZERO key events (delivery cannot self-trigger takeover) | `tools/im-lab/` (wlwire/im\_probe/fields/imlab\_run) in a disposable Xvfb+Sway desktop; GTK4 `Gtk.Entry` asserting its own text/caret/edit-count; 29-row run, 24 pass. NOT the operator's desktop, NOT Hyprland, NOT speech — mechanism evidence only.                         |
| Field-class matrix (same lab): foot 1.28 and kitty 0.49 = INSERT-ONLY over IM (both silently ignore `delete_surrounding_text`; neither ever sends `surrounding_text`; foot renders preedit, kitty app-side only); ghostty 1.3.1 = IM route DEAD (text-input activates, no byte ever reaches the pty; matches ghostty's own IME tracker — retest on version bump); live Hyprland 0.56.2 ADVERTISES `zwp_input_method_manager_v2 v1` + `zwp_text_input_v3 v1` (passive read-only registry listing via `tools/im-lab/globals.py`); sway 1.12 advertises the same set                                                                                                                                                                                                                   | Terminals that never send `surrounding_text` cannot be ownership-verified over IM — terminal verification MUST come from the app side (R.3 units rule).                                                                                                                        |
| pi's TUI editor has a DOCUMENTED extension seam (no fork): `ctx.ui.setEditorComponent()` installs a custom editor component; `ctx.fork({position:"before"})` restores a prompt into the editor — the cooperating-editor TargetAdapter for the chat-prompt milestone can be an extension + local control socket                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | pi `docs/extensions.md` read 2026-11-22; the API's exact write/caret control is not yet exercised by code — prove at G3.                                                                                                                                                       |
| Old incident mechanisms pinned: equality guard already exists; a k=0 final orders a full-tail rewind BY DESIGN; one silently dropped insertion desyncs belief and the next rewind eats committed text                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | `tests/test_zero_diff_rewind.py` T1–T3 (3/3 pass at handoff).                                                                                                                                                                                                                  |
| NOT VERIFIED anywhere: insert+correct in the real chat prompt; speech-to-visible latency; desktop coverage; throughput; Hyprland relay behavior (nested Hyprland cannot boot under the lab's software rendering — aquamarine `CBackend::create()` fails)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | No operator acceptance on record. A passing transport probe NEVER flips any of these to "passed".                                                                                                                                                                              |

Protocol facts (upstream-verified): `wl_data_offer.receive` serves bytes to ANY requester — a clipboard-history manager can be that requester, and the protocol carries NO acceptance acknowledgement; `wl-copy` cannot restore an offer that had multiple formats; `input-method-v2` provides `commit_string`/`set_preedit_string`/`delete_surrounding_text` plus an atomic `commit(serial)` whose evaluation order is preedit-replace → delete-surrounding → insert-commit (wire format per the XML Hyprland itself vendors); compositor advertisement verified on live Hyprland 0.56.2 and sway 1.12, per-field support MEASURED (R.2 matrix) — Hyprland relay behavior remains untested.

**R.3 Delivery model.** A new bulk-delivery controller plus a TargetAdapter, SEPARATE from `StreamingOutput`/`typing_backends.py` (legacy code stays for `stream-edit`; the bulk adapter MUST NOT expose `type_character`/`press_backspace` or any typing fallback):

* `acquire`: bind the SPECIFIC editable field — not merely a window, terminal process, or screen position. Return an opaque target handle + revision. Fail BEFORE delivery for non-editable, password/secret, selected, or unidentified fields; never replace a pre-existing user selection by default. A pane, tab, or inner editor can change without the window changing.
* `show(session, utterance, seq, expected_revision, complete rendered span)`: one insert-or-replace executed ON the target's event loop, only if focus, caret, selection, and ownership still match. Returns `applied | unchanged | refused | unknown`. Bytes sent is not "applied"; "unknown" is not "delivered".
* `finalize`: a final matching the visible text ⇒ NO further edit (ownership ends; composition-protocol commit side effects must not visibly change or duplicate the text). A differing final ⇒ ONE replacement of verified owned text. A final with no preceding partial inserts once and counts as a missed live update in latency evidence.
* `leave`/`cancel`: stop preserves the last visible words where they are — no post-stop writes anywhere, including a newly focused field. Deliberate cancel may remove the owned fragment in ONE operation, drop its buffered audio, and keep listening.
* Ownership and units: the adapter maps text positions to the target's own units (UTF-8 bytes, characters, UTF-16 units, or editor markers); never slice via a lowercased/normalized copy. Adjacent user text, whitespace, and formatting are never touched. No control bytes, tabs, newlines, escape sequences, paste delimiters, or Enter as input — recognized prose line breaks normalize to a space. The lazy continuation space applies only on the SAME verified target.
* The terminal chat prompt is the first milestone: prove pi's real input editor inside isolated Ghostty. An adapter for that editor is in scope (a documented extension/input seam preferred over a fork; the seam exists — R.2: `ctx.ui.setEditorComponent()` / fork prompt-restore). No tmux requirement, no terminal reconfiguration, no disabling of paste safeguards.

**R.4 Implementation order and stopping rules.** (1) Field FIRST: an isolated instance of the real prompt, scripted partials/finals, asserting exact editor text + caret + the VISIBLE prompt — a byte reader, scrollback, or fake editor never substitutes; missing visibility instrumentation means "not verified", not "passed". (2) Route assignment is DECIDED (2026-11-22, R.2): the `zwp_input_method_v2` adapter is the PRIMARY route — insert = `commit_string`+`commit`; correction = `delete_surrounding_text(before,0)`+`commit_string`+`commit` in ONE atomic commit; zero-diff = no request; verification via `surrounding_text`; takeover via keyboard-grab key events. Coverage per the R.2 matrix: full on GTK-class fields, insert-only on foot/kitty, UNAVAILABLE on ghostty 1.3.1. The terminal chat-prompt milestone uses the cooperating-editor extension seam (R.2); clipboard paste remains an insert fallback for ghostty-class terminals only, under the R.6 contract. Do NOT re-run route discovery. (3) Prove insert AND correct before any mic integration. (4) Integrate recognition and keep the first working route runnable. If no safe route exists in a field, record the missing capability — NEVER fall back to typing, and a blocked matrix row is a legitimate result. Development MUST NOT change the operator's service, config, or bindings as a side effect.

**R.5 Ordering, takeover, and failure.**

* New session generation at every arm; utterance identities assigned at the decode source and carried through `recorder_host`'s event relay (extend the `partial`/`final` payloads — a late event keeps its own identity, never relabeled as newer); keep the existing arm/disarm audio purges. Discard late post-final partials, duplicate finals, and canceled-utterance events; a dropped or filtered final still closes its utterance boundary; a rejected final never auto-erases visible words.
* `RecorderHost._dispatch` invokes `_on_partial`/`on_final` on the reader thread: bulk mode MUST enqueue and return — no subprocess, editor wait, or display polling there or under the daemon control lock. One writer per target; one operation in flight; newest partial wins for the current utterance; finals and boundaries are ordered barriers, never overwritten (bounded queue, default 32; overflow stops delivery rather than dropping a barrier).
* Takeover: any ordinary physical key, caret move, selection change, mouse click, focus change, tab/pane switch, or target death revokes the handle AT THE TARGET (daemon-side flags alone do not suffice); queued operations re-check at mutation time. Stop/toggle-off/idle-stop disarm immediately with no late flush. The arming chord is ignored (not a blanket grace window). Synthetic delivery events cannot self-trigger HALT or leave modifiers held. Pointer motion alone is not an edit.
* Bare Backspace keeps cancel semantics ONLY where the target can consume the gesture on an owned live fragment before performing an ordinary deletion (test tap, hold, auto-repeat, release). Otherwise the real key is an ordinary user edit ⇒ HALT ⇒ inject nothing. `voicectl cancel` in bulk mode performs NO `len(tail)-1` physical-character compensation (route bulk cancel BEFORE `daemon.cancel`'s legacy backspace call): it discards the fragment's recognition, removes only a verified owned range, and leaves the mic armed on success; nothing pending ⇒ no edit; uncertain range ⇒ stop, never attempt repair.
* Any `unknown`/`refused`/stalled operation (250 ms engineering deadline) disarms bulk delivery AND recording, retains recoverable recognition, and reports one concise reason via status and the configured fault surface. NEVER retry an operation that may already have landed. Validate deadlines and takeover in the RECEIVER so a late operation cannot mutate after the daemon has given up.
* Keep three values distinct: latest recognized text; filter-accepted final; last target-CONFIRMED visible text. `feedback.record_final` keeps its recognition meaning for existing clients; `state.json`/status gain `delivery_mode`, `delivery_state` (`inactive|active|unsupported|fault`), `delivery_reason`, and last confirmed op — never the surrounding user document. New bulk-path logs carry counts and times, not recognition text.

**R.6 Clipboard and recovery.**

* Routine delivery prefers a CLIPBOARD-FREE route. If an adapter must use the ordinary clipboard it MUST preserve all prior formats and bytes, distinguish original ownership from a later copy with identical text, protect a simultaneous user paste, and keep partials out of the configured clipboard-history watcher. Compare-before-restore, sleep-before-restore, `--paste-once`, and "first reader = the editor" are INSUFFICIENT. If this cannot be proven with the local manager, that adapter is unavailable — never disable the manager. The PRIMARY selection stays untouched.
* Recovery (both delivery modes): daemon memory holds the last nonempty arm→disarm session — accepted final per utterance plus the last visible/recognized unfinished tail, exactly once each; a rejected final retains only the shown tail; deliberate cancels and late finals are excluded; the previous completed session survives empty or failed arms; at most two sessions × 1 MiB UTF-8 (on overflow keep the newest complete text that fits and report truncation); cleared at daemon exit; no crash persistence, audio archive, or new transcript-bearing logs. `voicectl session` prints the most recent COMPLETED session (never a moving draft); `voicectl session --copy` copies exactly that text — no added newline, never types/erases/submits, exit 1 with the clipboard untouched when none exists; truncation is reported on stderr and in the reply. Any bind for it is user-assigned, never installed over an existing one.

**R.7 Verification and graduation gates.** All under the repo's timeout discipline; automation MUST NOT exercise the live desktop, real clipboard, default microphone, or active service — private compositor + synthetic input + isolated app instances; evidence stays bounded, only fixtures enter version control.

* **G1 regression baseline:** record pre-change results of `test_streaming_commit`, `test_zero_diff_rewind`, key-listener, control-socket, and config suites; reconcile the legacy separator failures at HEAD (measured at the 2026-11 handoff: `test_streaming_commit.py` 10 failed / 22 passed; `test_zero_diff_rewind.py` 3/3 passes) against the lazy-separator contract and separate them from NEW failures (no blanket skips, no legacy behavior changes to fake parity).
* **G2 controller, fake target:** deterministic traces — append; first-word change; identical update and final; retraction; Unicode; rejected/lost final; repeated cancel; timeout-after-apply; held key; out-of-order results; stop + immediate re-arm; child death; focus change mid-operation. Assert exact text/caret, bounded queue, zero legacy-backend calls, no duplicates, no extra writes, no post-takeover mutations. Necessary, never sufficient.
* **G3 real-field matrix** (per claimed field, starting with text on both sides of the caret): short updates; a 20-sentence first-word correction; repeated identical finals; long and Unicode payloads; pane/tab/window switches; a refusing target. Assert editor contents + cursor + the visible prompt; no transient delete/retype frames, no folded-paste placeholders, no neighbor changes, no shortcut execution or submission. Rows report `untested | insert-only | blocked (reason) | verified (versions + evidence links)`. A G2 pass never marks a row verified.
* **G4 clipboard (only if used):** private manager with text+image watchers; simultaneous copies incl. identical bytes; user paste during transfer; empty, rich-text, and image offers; failure before and after the data request; process death — verify contents, history, all original formats, and the target, never exit codes.
* **G5 timing** (warm GPU, monotonic clocks, word-aligned replay of real voice — callback cadence and the silence detector are NOT the speech clock): speech-end→word-visible median ≤ 500 ms, p95 < 1 s; update-ready→first-changed-frame p95 ≤ 100 ms (insertion) / ≤ 50 ms (correction); unchanged ⇒ no edit; ≥ 100 insertions and ≥ 100 corrections per claimed route; publish counts, median, p95, worst gap, max words outstanding. Missing words are misses, not zero-latency samples. A sustained five-word backlog or a sentence-end dump fails regardless of medians.
* **G6 graduation to default:** verified G3 rows for the pi prompt in Ghostty, a graphical editor, and a browser text field; zero observed integrity failures; and ≥ 3 representative completed writing sessions where usable proofread words per minute — counting corrections, recovery, and rereading — beats 110 wpm. Otherwise report that and stay opt-in. Never claim "works on Wayland" from one row; never fabricate user acceptance.

**R.8 Recognition quality is separate work.** Keep the configured large-v3-turbo\@float16 path and its lifecycle guarantees (lazy load, idle unload, segmentation without session end). Compare the earliest usable update callback against the currently wired stabilized callback on the same recordings and choose by VISIBLE word lag and correctness; never interleave two streams as one hypothesis chain. A second LOCAL model for a preview/final split is a permitted experiment (one utterance identity, one displayed hypothesis, one authoritative final; keep only if measurably better); external/offload processing is NOT enabled here. Unrelated-phrase reports: replay known speech, silence, a pause, media bleed, and stop/re-arm against recognition-vs-delivered text — already-in-recognition ⇒ audio/model/stale-audio investigation; only-in-field ⇒ delivery/stale-state investigation; no origin claims without evidence, no phrase suppression to pass tests. Media ducking (§4.2quinquies) and the legacy §8 bugfixes (datagram merge `33321c6`, cancel auto-repeat) are NOT prerequisites for a clipboard-free bulk adapter.

### 4.3 Typing backends (`typing_backends.py`)

Interface: `type_text(text: str) -> None` (append committed text) plus `press_backspace(n: int) -> None` (Rev 2, §4.2quater — delete exactly n characters for in-place revision). Selected by config `output.backend`, default **`wtype`**.

* **wtype** (default): `subprocess.run(["wtype", "--", text])`. Uses Wayland `virtual-keyboard-v1` — supported by Hyprland, full Unicode, no layout issues. Types into the focused window.
* **ydotool**: `subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text])`. uinput-level, works even for XWayland apps; known weakness: non-ASCII/layout quirks. Keep as fallback; daemon MUST auto-fall-back to ydotool if a wtype call fails (nonzero exit), logging a warning.
* **null**: types NOTHING. For the headless E2E test (which asserts finals via the state file instead of real keystrokes, so an automated run can never type into the developer's focused window) and for output-disabled setups. No subprocess is spawned.

Never send Enter/newline unless the utterance-final text itself demands it — it never should; strip trailing newlines in textproc.

### 4.4 RealtimeSTT recorder configuration (exact starting values — tune only if tests fail)

```python
AudioToTextRecorder(
    model="distil-large-v3",            # final pass; substitute "large-v3-turbo" if needed
    realtime_model_type="small.en",     # partials
    language="en",
    device="cuda", compute_type="float16", # if compute_type is a supported kwarg; verify against v1.x, else set gpu_device_index and rely on default
    enable_realtime_transcription=True,
    realtime_processing_pause=0.15,     # partials cadence ~150ms
    use_main_model_for_realtime=False,  # two models — avoid contention
    post_speech_silence_duration=0.6,   # finalize sentence after 0.6s pause (segmentation ONLY)
    min_length_of_recording=0.3,
    min_gap_between_recordings=0.0,     # resume listening immediately
    silero_sensitivity=0.4,
    webrtc_sensitivity=3,
    silero_backend="auto",              # item correction: modern control (prefers bundled CPU ONNX → avoids the torch-hub download). Supersedes the legacy silero_use_onnx=True.
    spinner=False,
    use_microphone=True,                # False + feed_audio() in tests
    ensure_sentence_starting_uppercase=False,  # item correction: textproc owns casing/punctuation cleanup
    ensure_sentence_ends_with_period=False,    # item correction (same reason)
    no_log_file=True,                   # suppress RealtimeSTT's unbounded realtimesst.log (sole log path = stderr → journald)
    # input_device_index: leave unset → PipeWire default source
    on_realtime_transcription_stabilized=...,  # → feedback
)
```

Notes:

* Verify each kwarg name against the installed RealtimeSTT version's `audio_recorder.py` signature; drop unknown kwargs rather than crash.
* First construction downloads models to `~/.cache/huggingface`. `install.sh` MUST prefetch (construct recorder once, or `huggingface_hub.snapshot_download` of `Systran/faster-distil-whisper-large-v3` and `Systran/faster-whisper-small.en`) so the first arm never does a network download. ("Instant" applies to arms after the first in a session; the first arm still pays the \~1–3 s load-from-cache-into-VRAM cost per §4.2bis.)
* **cuDNN/cuBLAS:** ship `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` as deps and, in `daemon.py` before importing anything CUDA, prepend their lib dirs to the process's dynamic loader path — standard trick:
  ```python
  import os, pathlib, nvidia.cublas.lib, nvidia.cudnn.lib
  libs = os.pathsep.join(str(pathlib.Path(m.__file__).parent) for m in (nvidia.cublas.lib, nvidia.cudnn.lib))
  os.environ["LD_LIBRARY_PATH"] = libs + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
  ```
  must happen via os.execv re-exec or in a launcher wrapper, because LD\_LIBRARY\_PATH is read at process start. **Realized approach:** `voice_typing/launch_daemon.sh` (the ExecStart, §4.9) recomputes the cuBLAS/cuDNN lib dirs from the *live installed* `nvidia-*-cu12` wheels on every launch and exports `LD_LIBRARY_PATH` before exec'ing python — so no baked `Environment=LD_LIBRARY_PATH=` is used in the unit (it would go stale on `uv sync`). If `libcudnn_ops*.so` errors still appear, check the wrapper (`LD_DEBUG=libs launch_daemon.sh`).
* If CUDA init fails entirely, daemon MUST log clearly and fall back to `device="cpu", compute_type="int8"` with `realtime_model_type="tiny.en"`, model `small.en` — degraded but functional — and say so in `status`.
* **Lite mode (§4.2ter):** the lite recorder is constructed with `model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True` (verified: only ONE model initializes; the large final model is never constructed), AND a snugger `post_speech_silence_duration = lite_post_speech_silence_duration` — the silence gate, not the model, is the perceived-latency bottleneck, so lite MUST shorten it to actually feel faster (see §4.2ter).
* **Streaming path (Rev 2, §4.2quater):** the lite recorder additionally runs with a dynamic `initial_prompt` / `initial_prompt_realtime` (rolling committed context; both kwargs exist in installed v1.0.2 but are constructor-static — the child updates them between utterances) and `lite_post_speech_silence_duration = 0.8` default.

### 4.5 Config (`config.toml`, parsed with stdlib `tomllib` into dataclasses)

```toml
[asr]
final_model = "distil-large-v3"
realtime_model = "small.en"
lite_model = "small.en"             # the SINGLE model loaded in lite mode (used for both partials + finals); §4.2ter
language = "en"
device = "cuda"                       # "cuda" | "cpu"
compute_type = "float16"              # ctranslate2 compute type on the CUDA path (2026-11-18: now a config key, config.py + config.toml in lockstep). "float16" = Ampere+ native — measured ~2x faster decode (the ASR-lab bake-off: turbo polled at float16 = 382 ms median word lag vs 2667 ms at float32); "float32" = legacy cards without usable fp16. Ignored on the CPU paths (always int8).
post_speech_silence_duration = 0.6
lite_post_speech_silence_duration = 0.8  # Rev 2 §4.2quater: the endpointer only delays COMMIT under streaming (words are already typed live) — 0.8 halves mid-thought cuts for +0.3 s commit latency. 0.5 = razor-snappy; 1.0 = near-zero cuts.
context_prompt = true                  # Rev 2 §4.2quater: condition every decode on the rolling committed context (back to the last sentence boundary, ~200-token cap)
realtime_processing_pause = 0.15
auto_stop_idle_seconds = 30.0          # auto-disarm after this many seconds of no speech; 0 disables
auto_unload_idle_seconds = 1800.0     # after this many seconds disarmed (loaded, not listening), tear down models to free VRAM; 0 disables (§4.2bis Idle unload)

[output]
backend = "wtype"                     # "wtype" | "ydotool" | "null"
append_space = true
graceful_stop = false                # Rev 3: stop = IMMEDIATE disarm (racing final dropped, tail stays typed). true = Rev 2 drain (wait ~5 s for the in-flight final) first.
streaming = true                     # Rev 2 §4.2quater: type stabilized partials live + revise in place; false = Rev 1 append-only finals (rollback hatch)
delivery = "stream-edit"             # Rev 4 §4.2sexies: "bulk-text" = paste-as-policy output path (show each update in the field; one-edit corrections; NO typing/backspace fallback). "stream-edit" = today's behavior (default until G6 graduation). bulk-text requires streaming=true, graceful_stop=false, keypress_action="disarm".

[cancel]                              # Rev 2 §4.2quater: Backspace-cancel
keypress_action = "disarm"           # Rev 3: any real keypress while armed halts dictation entirely; "freeze" = legacy per-utterance freeze
on_backspace = true                  # evdev listener: Backspace while a fragment is in flight cancels it (rewind + drop audio, keep listening)
devices = []                         # empty → auto-enumerate keyboard /dev/input/event* nodes; else explicit path list override

[feedback]
state_file = ""                       # empty → $XDG_RUNTIME_DIR/voice-typing/state.json
hypr_notify = true                    # master switch for hyprctl popups (start/final/stop)
notify_on_final = true                # also pop “✔ <text>” per final? (redundant: text is typed into the focused window)
notify_ms = 2500

[filter]
min_chars = 2
blocklist = ["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"]  # case-insensitive exact matches — classic whisper silence hallucinations


[log]   # daemon logging verbosity (stderr → journald under systemd)

level = "INFO"            # "INFO" = one structured per-utterance latency line + the startup device/models line; "DEBUG" = also the raw monotonic timestamps. Read live with `journalctl --user -u voice-typing -f`.
```

Config file search order: `$XDG_CONFIG_HOME/voice-typing/config.toml`, then repo `config.toml`, then built-in defaults. `install.sh` copies the repo default to XDG if absent.

**Idle auto-stop** (`asr.auto_stop_idle_seconds`, default `30.0`): while listening, if no recognized speech (a realtime partial) arrives for this many seconds, the daemon auto-disarms immediately (no drain — by definition no utterance is in flight after this long silent) — it fires the `Recording Stopped` toast and writes a journal `INFO` line (`voice-typing auto-stop: 30.0s of no recognized speech; disarming`). Partials reset the clock while you talk, so it only triggers when you genuinely go silent (a forgotten hot-mic guard, NOT a mid-thought cut — that is governed by `post_speech_silence_duration`). A background `_idle_watchdog` thread ticks \~1s and re-checks the deadline under the listen lock so a late partial cancels the stop. `0` disables. Auto-stop disarms the mic but does NOT unload models by itself — it starts the slower idle-unload clock (below).

**Idle unload** (`asr.auto_unload_idle_seconds`, default `1800.0` = 30 min): a separate, slower watchdog that tears down the resident recorder to reclaim VRAM once the mic has been disarmed this long with no re-arm. It composes with idle auto-stop — the 30 s auto-stop disarms first, then the 30 min idle-unload frees the models. Full rule + the bounded-teardown requirement in §4.2bis (Idle unload). `0` disables (models then stay resident until `quit`).

### 4.6 Feedback (`feedback.py`)

* **State file** (atomic write via tempfile+rename) at `$XDG_RUNTIME_DIR/voice-typing/state.json`:
  ```json
  {"listening": true, "phase": "speaking", "models_loaded": true, "mode": "normal", "partial": "this is what i am say", "last_final": "Previous sentence.", "ts": 1783718400.123}
  ```
  `mode` is `"normal"` or `"lite"` (§4.2ter); it is written on every arm/disarm. Written on every partial update (throttle to ≥10 Hz max), phase change, final, and model-lifecycle transition. While models are not yet loaded (boot) or mid-load, `phase` is `unloaded` or `loading` and `models_loaded` is false (§4.2bis); once loaded, `phase` cycles `idle`/`listening`/`speaking`.
* **hyprctl notify**: `hyprctl notify -1 <notify_m
</selected_prd_content>
<prd_index>
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
  h3.6 4.2sexies Bulk text delivery — paste as policy (Rev 4; active when output.delivery="bulk-text")
  h3.7 4.3 Typing backends (typing_backends.py)
  h3.8 4.4 RealtimeSTT recorder configuration (exact starting values — tune only if tests fail)
  h3.9 4.5 Config (config.toml, parsed with stdlib tomllib into dataclasses)
  h3.10 4.6 Feedback (feedback.py)
  h3.11 4.7 Text processing (textproc.py)
  h3.12 4.8 voicectl (ctl.py)
  h3.13 4.9 systemd user service (systemd/voice-typing.service)
  h3.14 4.10 Phase 2 (implement after all tests pass — small, do it in the same run)
 h2.4 5. Installation steps (for the implementing agent)
 h2.5 6. Test plan — ALL must pass before declaring success
 h2.6 7. Acceptance criteria (definition of done)
 h2.7 8. Known risks & prescribed mitigations
 h2.8 9. Future work (explicitly out of scope now)
---
code:6 para:79 list:31 table:3
</prd_index>
<issue_feedback>

</issue_feedback>
<plan_status>Task Status Summary
==================================================

P1: Delta Rev 3/4 remainder — media ducking (D1), bulk text delivery (D2), legacy defect pipeline (D3) - Planned
  P1.M1: G1 regression baseline + legacy defect closure (D3) - Planned
    P1.M1.T1: Record the G1 regression baseline at pre-change HEAD - Planned
      P1.M1.T1.S1: Run and record the baseline suite numbers - Researching (1 points)
      P1.M1.T1.S2: Classify reds vs the lazy-separator contract - Planned (1 points)
    P1.M1.T2: Merge fix/ydotoold-datagram and add the 6 ms socket contact gap - Planned
      P1.M1.T2.S1: Merge fix/ydotoold-datagram onto main - Planned (1 points)
      P1.M1.T2.S2: Add the 6 ms press→release contact gap on the socket path - Planned (1 points)
      P1.M1.T2.S3: Journal-noise regression guard (no per-burst fallback storms) - Planned (1 points)
    P1.M1.T3: Close the cancel auto-repeat compensation audit (D3.2) - Planned
      P1.M1.T3.S1: Replay a sustained-Backspace hold as a regression test + audit trace - Planned (2 points)
      P1.M1.T3.S2: Mitigate or record the residual desync window - Planned (1 points)
    P1.M1.T4: Fix the cancel-suppression window latch chaining (D3.3) - Planned
      P1.M1.T4.S1: Bound the suppression-window re-latch chain - Planned (2 points)
      P1.M1.T4.S2: Replay the 4× incident sequence as a regression test - Planned (2 points)
  P1.M2: Media ducking while listening (D1, §4.2quinquies) - Planned
    P1.M2.T1: Add the [audio] config surface in lockstep - Planned
      P1.M2.T1.S1: AudioConfig dataclass + config.toml table + key-set pin 24→26 - Planned (1 points)
    P1.M2.T2: Implement the AudioDucker module (protocol + two tiers + failure discipline) - Planned
      P1.M2.T2.S1: AudioDucker core + backend protocol + bookkeeping - Planned (1 points)
      P1.M2.T2.S2: MPRIS tier: tracked pause set via busctl - Planned (2 points)
      P1.M2.T2.S3: Volume tier: wpctl snapshot + conditional restore - Planned (1 points)
      P1.M2.T2.S4: Failure discipline: non-blocking, bounded, idempotent - Planned (1 points)
    P1.M2.T3: Wire ducking lifecycle into the daemon + crash safety - Planned
      P1.M2.T3.S1: Engage/release at the arm/disarm seams (spawned, never under _lock) - Planned (2 points)
      P1.M2.T3.S2: Crash safety: ducked flag, startup self-heal, ExecStopPost - Planned (1 points)
    P1.M2.T4: Flip duck_mode default to mpris with evidence - Planned
      P1.M2.T4.S1: Default flip + acceptance evidence - Planned (1 points)
  P1.M3: Bulk delivery controller core + config gate (D2, G2) - Planned
    P1.M3.T1: Define bulk delivery contracts (protocol, results, zero-diff guard) - Planned
      P1.M3.T1.S1: Contracts module: protocol + result taxonomy + zero-diff guard - Planned (2 points)
    P1.M3.T2: Implement the bulk controller (ordering, failure, G2 gate) - Planned
      P1.M3.T2.S1: Ordering core: bounded queue, barriers, one writer - Planned (2 points)
      P1.M3.T2.S2: Failure handling: 250 ms deadline, disarm-on-unknown, no retries - Planned (2 points)
      P1.M3.T2.S3: G2 gate: full fake-target trace matrix green + evidence record - Planned (2 points)
    P1.M3.T3: output.delivery config gate + delivery status surface - Planned
      P1.M3.T3.S1: output.delivery key + precondition triple enforcement - Planned (1 points)
      P1.M3.T3.S2: Delivery status surface: feedback fields + voicectl status rendering - Planned (1 points)
  P1.M4: IM-v2 primary adapter: transport, acquire, show, takeover, real-field proof - Planned
    P1.M4.T1: Productize the IM-v2 wire transport into a daemon-owned subprocess - Planned
      P1.M4.T1.S1: Wire transport package + JSONL protocol - Planned (2 points)
      P1.M4.T1.S2: Subprocess lifecycle: spawn/monitor/teardown + unavailable handling - Planned (2 points)
    P1.M4.T2: acquire + ownership verification - Planned
      P1.M4.T2.S1: acquire(): field binding, verification, units mapping - Planned (2 points)
    P1.M4.T3: show()/finalize: atomic insert, atomic correction, finalize semantics - Planned
      P1.M4.T3.S1: Insert path (commit_string + commit) - Planned (2 points)
      P1.M4.T3.S2: Correction path (one atomic range replacement) - Planned (2 points)
      P1.M4.T3.S3: finalize/leave/cancel semantics - Planned (2 points)
    P1.M4.T4: Takeover revocation at the target - Planned
      P1.M4.T4.S1: Takeover detection + revocation + mutation-time re-checks - Planned (2 points)
    P1.M4.T5: Real-field proof + field-class matrix re-run (G3 core) - Planned
      P1.M4.T5.S1: G3 harness + GTK field rows (insert AND correct, visible) - Planned (2 points)
      P1.M4.T5.S2: Field-class matrix re-run at installed versions (drift!) - Planned (2 points)
  P1.M5: Cooperating-editor pi-prompt adapter + remaining G3 rows + conditional clipboard fallback - Planned
    P1.M5.T1: pi chat-prompt cooperating-editor adapter (extension seam) - Planned
      P1.M5.T1.S1: pi extension: CustomEditor + AF_UNIX control socket - Planned (2 points)
      P1.M5.T1.S2: Daemon-side cooperating-editor TargetAdapter - Planned (2 points)
    P1.M5.T2: G3 rows: pi prompt in isolated Ghostty (first), graphical editor, browser field - Planned
      P1.M5.T2.S1: pi-prompt-in-isolated-Ghostty row - Planned (2 points)
      P1.M5.T2.S2: Graphical editor + browser text field rows - Planned (2 points)
    P1.M5.T3: Clipboard insert-fallback adapter (conditional on the refreshed matrix) - Planned
      P1.M5.T3.S1: Conditional clipboard insert-fallback + G4 gate (or recorded skip) - Planned (2 points)
  P1.M6: Recognition integration + delivery lifecycle (R.5/R.6 daemon-side) + G5 timing - Planned
    P1.M6.T1: Utterance identities + session generation through the recorder relay - Planned
      P1.M6.T1.S1: Payload helper at the five final sites + partial site - Planned (2 points)
    P1.M6.T2: Wire bulk delivery into the daemon + session recovery + voicectl session - Planned
      P1.M6.T2.S1: Dispatch wiring + bulk cancel intercept - Planned (2 points)
      P1.M6.T2.S2: Session recovery memory (R.6) - Planned (2 points)
      P1.M6.T2.S3: voicectl session [--copy] - Planned (2 points)
    P1.M6.T3: Decouple bulk committed context from StreamingOutput - Planned
      P1.M6.T3.S1: Bulk-mode prompt source decision + implementation - Planned (1 points)
    P1.M6.T4: G5 timing evidence (word-aligned real-voice replay) - Planned
      P1.M6.T4.S1: G5 harness + per-route timing evidence - Planned (2 points)
  P1.M7: Graduation assessment + changeset-level documentation sync - Planned
    P1.M7.T1: G6 graduation assessment (evidence-gated, no over-claiming) - Planned
      P1.M7.T1.S1: Assemble G6 assessment; conditionally flip the default - Planned (1 points)
    P1.M7.T2: Sync changeset-level documentation - Planned
      P1.M7.T2.S1: README.md: ducking + bulk delivery sections, config table, troubleshooting - Planned (2 points)
      P1.M7.T2.S2: tests/ACCEPTANCE.md rows + install.sh usage - Planned (1 points)
      P1.M7.T2.S3: Final consistency sweep + commit discipline - Planned (1 points)</plan_status>

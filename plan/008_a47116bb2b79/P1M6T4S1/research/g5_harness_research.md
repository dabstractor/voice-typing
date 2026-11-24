# G5 harness research — P1.M6.T4.S1 (verified live this session @ dd0bd5b)

## 1. The input contract (what exists when this item starts)

- **Bulk path wired** (P1.M6.T2.S1, commit df934ed): `on_final`/`_on_partial` bulk branches,
  `_bulk_cancel` intercept, arm/disarm/fault lifecycle, `bulk_target_factory` ctor seam +
  `_build_default_bulk_target`, `feedback.set_delivery_mode`. The daemon ctor ALSO has
  `host_factory` (daemon.py:788/:829, resolved in `_load_host` :1115-1120 — "only the real
  RecorderHost takes it" extra-kwarg pass-through pattern to copy for `feed_input`).
- **Identity relay** (P1.M6.T1.S1, 1a979dc): `host.relay_identity` → `(gen, utterance, seq)`.
- **Session recovery** (P1.M6.T2.S2, dd0bd5b) — orthogonal, ignore.
- **Parallel item P1.M6.T3.S1** (bulk prompt source): touches `_refresh_context_prompt` /
  `_bulk_handle_final` / `_on_bulk_applied` / `_bulk_cancel` / `_arm`. Disjoint from this
  item's sites (recorder_host feed seam + daemon ctor pass-through + new labs). Re-grep
  anchors before editing; do NOT touch its functions.
- **Verified routes (G3)**: gtk-field (tests/ime_g3_lab.py, P1.M4.T5.S1), matrix re-run
  (P1.M4.T5.S2), pi-prompt-in-Ghostty (tests/pi_g3_row_lab.py, P1.M5.T2.S1), editor+browser
  (tests/ime_g3_editor_browser_lab.py, P1.M5.T2.S2), clipboard insert-fallback
  (tests/clipboard_g4_lab.py, P1.M5.T3.S1).

## 2. KEY FINDING — recorder_host has NO audio feed seam

`grep feed_audio|input_device|device_index voice_typing/recorder_host.py` → **nothing**. The
child always constructs `AudioToTextRecorder(use_microphone=True)` → PipeWire **default
source**. Commands the child loop knows (recorder_host.py:843-903): `text|arm|disarm|abort|
prompt|shutdown` (+ reader-side `ready|error|final|partial|speech|speech_end|vad|gone`).

Options for getting real audio in WITHOUT the default mic:
- **REJECTED**: e2e_virtual_mic.sh route (`pactl set-default-source` on the SYSTEM server) —
  rebinds the live desktop's global default source; its own header calls that the reason an
  aborted run is worse here. G5/R.7 forbids it.
- **REJECTED (too heavy/unproven)**: private PipeWire server in a private XDG_RUNTIME_DIR
  (sounddevice/PortAudio→ALSA→pipewire routing inside a synthetic runtime dir is untested
  territory; e2e's G-RUNTIME note already shows XDG_RUNTIME_DIR games break pw tooling).
- **CHOSEN**: PRD §4.4 sanctions `use_microphone=False  # False + feed_audio() in tests`
  (tests/test_feed_audio.py is the proven pattern: G-ORDER arm-before-feed, feed_audio
  non-blocking + re-slices to 32 ms, **silence must be fed as zero slices at natural pace**,
  lines 194-226, 276). Add an INERT additive feed seam to recorder_host (ctor kwarg
  `feed_input=False`; child-loop `('feed', {'pcm', 'sr'})` cmd → `recorder.feed_audio(...)`;
  host proxy `feed()` = cmd-queue put). Daemon passes it through `_load_host` exactly like
  the existing extra kwarg (test fakes keep the old surface). Default False ⇒ production
  byte-identical.

## 3. Seams the harness drives (no daemon surgery beyond the feed pass-through)

- In-process `VoiceTypingDaemon(cfg, host_factory=<real RecorderHost + feed wrapper>,
  bulk_target_factory=<route bundle>)`. tests/test_bulk_dispatch.py:324-342 proves the ctor
  kwarg surface.
- Control via the daemon's REAL control socket — isolated by running the harness with a
  PRIVATE `XDG_RUNTIME_DIR` (e2e header: "the real control socket is pinned to
  $XDG_RUNTIME_DIR" ⇒ moving it isolates it). No voicectl against the live socket, ever.
- Update-ready timestamps: wrap `d.on_final` / `d._on_partial` entry with `time.monotonic()`
  captures (in-process lab-only monkeypatch; a list-append cannot perturb 50-100 ms budgets).

## 4. The speech clock — word-aligned replay of real voice

- Clips: `tools/asr-lab/voice/{natural,jargon,pauses,noisy}.wav` + `.txt` references —
  TRACKED in git (also `.raw48k/`). These are the G5-mandated real-voice fixtures.
- Alignment fixture: offline faster-whisper pass with `word_timestamps=True` (daemon venv +
  CUDA libs LD_LIBRARY_PATH recipe, asr-lab README run block) → per-word {word, start, end}
  JSON per clip, committed as `tools/asr-lab/voice/<name>.words.json`.
- Pacer: feed PCM slices so audio-time t hits the wall at `feed_start + t`
  (tools/asr-lab/paced_poll.py:18-39 is the exact pattern — monotonic clock, sleep to
  target). Word i's speech-end = `feed_start + words[i].end` — **the alignment fixture is
  the clock; callback cadence and the silence detector are NEVER the clock** (work item +
  R.7 G5). Pauses are fed as zero slices at natural pace (test_feed_audio G-silence).
- 382 ms median word lag (turbo@float16, asr-lab) = EXTERNAL reference only — it is engine
  word lag, not the delivery clock; never a pass bar and never confused with G5 deltas.

## 5. Clock sync across processes

`time.monotonic()` = CLOCK_MONOTONIC = same epoch across all processes on this host
(harness, daemon, field apps, extension). Spec a heartbeat sanity check anyway: every
participant emits (monotonic, wall) pairs; harness asserts pairwise monotonic deltas match
wall deltas within tolerance (catches accidental CLOCK_MONOTONIC_RAW/boottime drift).

## 6. Visibility observation (field side, R.7 "visible prompt")

G3 precedent: field apps assert their OWN text/caret/edit-count; frame oracle in
tests/ime_g3_support.py (EventLogWriter capped 64 KiB, field dumps capped 2000 writes).
G5 adds: env-gated timing log of `(time.monotonic(), full_text)` per text-change, bounded,
dumped on teardown. Routes:
- im-gtk: tests/ime_g3_field_gtk.py on SYSTEM python3 (venv has no gi), xvfb-run +
  dbus-run-session + sway x11 backend + disposable HOME/XDG_RUNTIME_DIR/TMPDIR (the
  ime_g3_lab.py boot recipe from tools/im-lab/imlab_run.py).
- pi-ghostty: tests/pi_g3_row_lab.py recipe — private headless Sway + isolated Ghostty +
  pi CustomEditor extension (THE DOCUMENTED HOME DELTA); adapter = voice_typing/pi_editor.py.
- optional later rows via the same registry: editor/browser (ime_g3_editor_browser_lab
  recipe), clipboard insert-only (clipboard_g4_lab private-manager recipe).

## 7. Bulk controller timing surfaces already present

bulk_controller.py stamps `t0 = time.monotonic()` pre-op and reports `elapsed_ms` in
`on_applied` (P1.M6.T2.S1) — useful cross-checks, but G5's authoritative numbers come from
the FIELD event log vs the replay clock (bytes sent is not "applied").

## 8. Config for the measured daemon (all private/inert)

delivery="bulk-text" + streaming=true + graceful_stop=false + keypress_action="disarm"
(precondition triple); backend="null"; feedback: hypr_notify=false, state_file=<private>;
cancel.devices=["/nonexistent/vt-g5-no-keyboard"] (listener fails → sanctioned "log once
at arm" fallback — REAL keyboards are live-desktop surfaces AND a stray human keypress
would HALT mid-run); auto_stop_idle_seconds=0 (no mid-run disarm on pause clips);
auto_unload_idle_seconds=0 (models stay resident = warm GPU across replays). Models: as
configured (defaults small.en + distil-large-v3) — G5 measures the shipped path.

## 9. Metric definitions (unit-test in support module)

- word-visible(w): first field event whose text contains w at its transcript position.
- speech-end→word-visible = visible_ts − (feed_start + w.end). Median ≤ 500 ms, p95 < 1 s.
- update-ready→first-changed-frame = first field event ≥ wrapped dispatch ts of that
  partial/final; classify insertion (new extends old at cursor) vs correction (anything
  else). p95 ≤ 100 ms insertion / ≤ 50 ms correction.
- unchanged ⇒ zero field events (zero-diff law row per route).
- counts: ≥100 insertions AND ≥100 corrections per claimed route; loop replays under a
  REPLAY_BUDGET; shortfall = reported failure, never faked.
- misses: reference words never visible — counted as misses, NEVER as zero-latency samples.
- worst gap: max single speech-end→word-visible sample.
- max words outstanding: peak of (words spoken per alignment clock − words visible), plus
  sustain flag: outstanding ≥ 5 held ≥ SUSTAIN_WINDOW_S (2.0 s) ⇒ route FAIL.
- sentence-end dump: utterance (alignment pause gap ≥ 0.6 s / clip boundary) with ≥5 words
  and <2 of them visible before its finalize event ⇒ route FAIL regardless of medians.

## 10. Safety/boundedness (AGENTS.md + R.7)

Everything under inner GNU `timeout -k 2` + bash-tool backstop > inner; lab is env-gated,
not pytest-collected; ONE TemporaryDirectory scratch (tmpfs = RAM) with EXIT/INT trap
teardown + killpg of owned session groups, no pattern-sweeps; event logs bounded (64 KiB /
2000-write caps); only the alignment JSONs + the committed markdown report enter git;
preflight asserts the live systemd unit is not required/touched (we never call systemctl);
never `pactl`/`pw-cat`/`hyprctl` against live sessions.

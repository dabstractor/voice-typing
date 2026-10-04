# Validation Report — voice-typing (Rev 2 streaming dictation)

**Date:** 2026-10-03 · **Validator:** automated + manual deep-dive · **HEAD at start:** `b2c0424` (moved to `a5e8616` mid-run — plan files committed externally; no repo-code drift during validation)

## Scope & method

Deep codebase review (all 13 `voice_typing/` modules read; control-plane, recorder-host child,
streaming engine, key listener, prompt engine traced end-to-end), the repo's own tooling
discovered and run through `./validate.sh` (written by this validation), plus live
workflow simulations against the real systemd daemon and the real Hyprland/PipeWire machine.
AGENTS.md discipline honored throughout (double timeouts, no foreground daemon, bounded scratch).

## Validation executed (all demonstrated by actual output)

| Phase | What | Result |
|---|---|---|
| Lint | `ruff check voice_typing/ tests/` | **FAIL — 1 error** (Issue 3) |
| Shell syntax | `bash -n` on all 5 repo shell scripts | PASS |
| Unit tests | 17-file pure-python pytest batch | **PASS — 623 passed** (22.10s) |
| Streaming E2E (CUDA) | `tests/test_streaming.py` — PRD §6 T8 (a)–(g): delta cadence, exact commit rewinds, pause-join casing/period guards, rolling context prompts, Backspace-cancel, user-key freeze, stranded-tail freeze | **PASS — 7/7** (121.63s, real small.en) |
| Offline ASR (CUDA) | `tests/test_feed_audio.py` — T1/T7: pause-keeps-listening, finals, latency, single-model construction | **PASS — 9/9** (69.74s) |
| Live control plane | `voicectl status`, removed-command rejection (exit 64), cancel idempotence, raw-socket malformed-JSON + unknown-command robustness | PASS (6/7 checks; quit failed → Issue 1) |
| systemd lifecycle | `voicectl quit` → socket removal → `systemctl --user start` → boots NOT-listening, phase `unloaded`, daemon PID absent from `nvidia-smi` (T6a lazy-load ~0 VRAM) | PASS (except the quit reply — Issue 1) |
| E2E virtual mic | `tests/e2e_virtual_mic.sh` — real daemon on PipeWire null-sink monitor, null typing backend: criterion 2 (3s pause loses zero words: fuzzy 0.86/0.80), criterion 3 (146 partial snapshots in state.json), criterion 4 (nothing typed after stop); all 5 segments ≥0.80 fuzzy; source restored, module unloaded | **PASS** |
| Install journey | `./install.sh` end-to-end (idempotent re-run): CUDA verdict `cuda-ok`, models cached, offline check (zero huggingface.co calls), unit active+enabled, usage/hypr instructions printed | PASS |
| Idle + GPU lifecycle | `tests/test_idle_and_gpu.sh` — T4: 120 s armed silence, zero finals (no hallucination), CPU avg 2.17 % (<25 %); T6: boot ~0 VRAM → armed 890 MiB → disarmed resident → idle-unload → ~0 → re-arm reload; T7 single-model: `small.en` sole model (no distil-large-v3 in the log), `mode: lite`, VRAM in [512,3072], cancel smoke; criterion 8 offline (zero HF requests via the production launch path) | **PASS** — `IDLE+GPU PASS` (zero FAIL lines) |
| Journal audit | 7-day `journalctl --user -u voice-typing` error scan | PASS — only harmless PyAudio/ALSA enumeration noise |

## Issues found

### 1. MAJOR — `voicectl quit` fails whenever the daemon is unloaded (acceptance #6 violation)

**Observed (live, twice):** with the daemon in its normal idle state (models not resident —
before the first arm of a session or after idle-unload), `voicectl quit` prints
`voicectl: daemon closed the connection without replying` and **exits 1** instead of
`shutting down` / exit 0. The daemon itself exits correctly (socket removed, clean
teardown) — the bug is the lost reply + wrong exit code. PRD acceptance criterion 6
("`voicectl toggle/start/stop/status/quit` all work") is violated on the quit arm.

**Root cause (traced in code + reproduced deterministically):**
- `ControlServer._dispatch("quit")` runs `request_shutdown()` then `on_quit()` = `daemon.shutdown()`
  **before** returning the reply dict — the reply is written only after `shutdown()` returns.
- With `self._host is None` (unloaded), `request_shutdown()` returns early *without* claiming
  `_shutdown_done` and *without* ever setting `_teardown_done`
  (`daemon.py` `request_shutdown`: `if self._host is None: return` precedes the claim block).
- The worker's `on_quit` → `daemon.shutdown()` first calls `key_listener.stop()` — with the real
  evdev listener that closes N keyboard fds and joins N reader threads (hundreds of ms).
- Meanwhile the MAIN thread: `run()` exits on `_shutdown`, `main()`'s finally calls
  `daemon.shutdown()` — its listener stop is the cheap second call, it **claims
  `_shutdown_done`**, then hits `if self._host is None: return` — the early return that
  **bypasses the `finally: self._teardown_done.set()`**.
- The worker resumes, sees `already_claimed=True`, and blocks in
  `self._teardown_done.wait(timeout=8.0)` on an event that is never set.
- Main thread proceeds to `server.stop()` → `main()` returns → interpreter exit kills the
  daemon-thread connection worker **before it writes the reply** → client EOF, exit 1.

**Heredity:** only the unloaded state is affected. With models loaded,
`request_shutdown()` takes the claim and its `try/finally` sets `_teardown_done`, so the
worker's `shutdown()` wait returns immediately and the reply lands (verified: live quit with
models loaded works; the fork-based repro below also shows the loaded path OK).

**Reproduction (deterministic, hermetic — forked daemon child, client parent, real-shaped
listener whose first `stop()` costs ~0.4 s and second is instant):**
`reply='' in 0.31s -> REPLY LOST — BUG REPRODUCED` (exit 3). Live: validate phase 6e-1 and a
manual `voicectl quit` both failed identically.

**Suggested fix (any one suffices, first is smallest):**
(a) in `shutdown()`, set `_teardown_done` on the `host is None` early-return path (mirror it in
`request_shutdown()`'s early return by claiming + signaling); or
(b) in `ControlServer._dispatch("quit")`, write/flush the reply **before** invoking `on_quit`
(reorder reply-first, teardown-after); or
(c) make the quit worker the only teardown owner (main's finally already handles the signal path).

### 2. MAJOR (migration) — the user's live Hyprland keybind calls the removed `toggle-lite`

`~/.config/hypr/custom/keybinds.lua` (line ~270, modified 2026-10-02 23:00, *before* the Rev 2
CLI trim landed) binds **Super+Alt+D** to a robust wrapper ending in
`voicectl toggle-lite` — the command P1.M1.T2.S3 removed from the six-command surface.
Pressing that hotkey now yields `voicectl: invalid command 'toggle-lite'` (exit 64) and
**dictation never arms** on that key. The README documents the *new* binds and even points at
`~/.config/hypr/custom/keybinds.conf` for inert binds, but nowhere warns that pre-existing
`toggle-lite`/`start-lite` callers break — and this machine's config demonstrably still has one
(the repo's own dogfood setup). Fix options: update the Lua bind to `toggle`, or reinstate
`toggle-lite` as an alias for `toggle` during a migration window, and add a README
"Upgrading from two-mode Rev 1" note.

### 3. MINOR — lint failure: `ruff` F821 undefined name `Iterator` (tests/test_streaming.py:1016)

`def stream_recorder() -> "Iterator[tuple[AudioToTextRecorder, StreamingHarness]]":` — `Iterator`
is never imported. Present since the harness landed (`f348eb6`); makes
`ruff check voice_typing/ tests/` exit 1 (validate phase 1 FAIL). No runtime impact (string
annotation is never evaluated). Fix: `from typing import Iterator` (or `collections.abc`).

### 4. MINOR — `state.json` reports `"mode": "normal"` at boot, contradicting the "always lite" contract

`Feedback.__init__` seeds `"mode": "normal"`; `set_mode("lite")` is only called in `_arm()`.
Between daemon boot and the first arm, the state file (the documented `jq`-able surface) carries
a mode name that no longer exists in the product, while `voicectl status` simultaneously shows
`mode: lite` (hardcoded in `status_snapshot`). README ("`mode` is always `"lite"` — a fixed
constant") and acceptance #10 ("`status` + `state.json` report `mode` (constant `"lite"`)") are
contradicted in that window. Live evidence: current
`$XDG_RUNTIME_DIR/voice-typing/state.json` → `"mode": "normal"` on an unloaded daemon.
Fix: default the field to `"lite"` in `Feedback.__init__` (or call `set_mode("lite")` in the
daemon constructor).

### 5. MINOR (doc drift) — `launch_daemon.sh` comment describes the pre-VT-004 unit ordering

The display-vars comment block says "The systemd unit is WantedBy=default.target … does NOT
wait for graphical-session.target" — but the shipped unit (VT-004, and its own header comment)
is `After=/PartOf=/WantedBy=graphical-session.target`. Comment-only; the wrapper code is
correct and the belt-and-suspenders re-fetch is still right. Fix: refresh the comment.

### 6. MINOR (process) — PRD's embedded task snapshot is stale vs. the repo

The PRD §9 Tasks block lists P1.M3.T9.S1 and P1.M3.T10.S1 as "Planned", while
`plan/007_cfc245548aec/tasks.json` and git history show them Complete (README sync committed as
`b2c0424`, suite adjustments as `f62c9b0`). The implementation matches the *completed* state
(README is Rev 2-consistent — verified by grep: zero residual `toggle-lite`/`final_model`/
`distil-large` references in README/install.sh/hypr-binds.conf). No action needed in code;
noting so the orchestrator doesn't "re-implement" finished work from the stale PRD copy.

## What was verified working (no action needed)

- **Streaming core (PRD §4.2quater):** extend-only deltas, rate-limited (≥300 ms) full
  rewinds, guarded commits with exact-length rewinds, committed/tail checkpointing, both freeze
  classes + suppression, rollback hatch — all pinned by 623 unit tests + 7 CUDA E2E tests.
- **Pause-keeping (the WhisperX flaw #1):** 3.0 s mid-sentence pause loses zero words through
  the REAL mic path (E2E fuzzy 0.86 pre / 0.80 post) and never ends the session.
- **Feedback loop (flaw #2):** 146 partial snapshots observed in `state.json` during playback;
  typed live partials verified by the streaming suite (≥1 delta/500 ms).
- **Lazy load / idle-unload:** boot daemon PID absent from `nvidia-smi` (T6a); armed 890 MiB
  (within the 512–3072 single-model band); idle-unload reclaims to ~0 and a later arm reloads
  (verified twice in the live suite); bounded teardown (quit completes in ~1–4 s; no 90 s hang);
  `context-prompt: on` confirmed live in the real daemon after an arm/disarm cycle.
- **Single-mode collapse:** exactly one model everywhere (cuda_check, cfg_to_kwargs,
  prefetch, binds, voicectl surface, README); `toggle-lite`/`start-lite` correctly rejected
  client-side (exit 64) — which is precisely why Issue 2 bites.
- **Robustness:** malformed JSON / unknown commands answered over the raw socket without
  crash or hang; cancel idempotent while disarmed; config loader rejects unknown keys and
  wrong-typed/wrong-valued fields at load time; daemon survives 7 days of journal without a
  single real error; install.sh idempotent with offline verification.
- **Docs:** README ↔ code spot-checks all passed (config table keys exist, tunables match,
  troubleshooting accurate, CPU-only paths as described) apart from Issues 2/4/5 above.

## Verdict

The Rev 2 streaming implementation is functionally excellent — every automated suite passes,
including the real-CUDA streaming E2E and the real-audio virtual-mic E2E. The findings are:
one real protocol bug on the `voicectl quit` path (unloaded daemon), one broken real-world
keybind caused by the CLI surface trim, and four minor hygiene items. Issues 1–3 are directly
fixable in one small changeset; Issue 2 needs a user-config decision (alias vs. edit).

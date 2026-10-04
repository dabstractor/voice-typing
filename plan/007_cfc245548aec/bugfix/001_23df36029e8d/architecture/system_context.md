# System Context — voice-typing Rev 2 streaming delta bugfix

Repo: `/home/dustin/projects/voice-typing` (cwd for all work). All line numbers verified by direct read during this research pass (2025, Rev 2 delta landed as P1.M2.T6/T7 + P1.M3.T2 per in-code tags).

## What this system is

A foreground CUDA dictation daemon: `voice-typing-daemon` runs a subprocess recorder host (RealtimeSTT, small.en single-model "lite" mode), types recognized text into the focused window via wtype/ydotool backends, and is controlled by `voicectl` over a Unix control socket. Rev 2 added streaming output (`StreamingOutput` engine): live partial typing with delta extends / rewind+retype revises, per-utterance commits, Backspace-cancel, freeze classes, and casing guards.

## Module map (line counts)

| File | Role | Key symbols (verified lines) |
|---|---|---|
| `voice_typing/daemon.py` (2829) | The daemon + ControlServer | `on_final` :1115 (listening gate :1121-1123; cancel-suppress branch :1130-1137; rejected-final freeze :1154 `freeze(..., session=True)`; `reset_boundary()` right after; `_final_pending=False` :1165), `_arm` :1258, `_disarm` :1314, `_touch_speech` :1354, `_on_partial` :1376 (NO listening gate), `_request_stop` :1391 (drains iff host+`_text_in_flight`+`_final_pending`), `note_user_keypress` :1448, `cancel` :1603, `_begin_drain` :1637 (`_DRAIN_TIMEOUT_S`=5.0 :149), `is_listening` :2061, `ControlServer._handle` :2444 (empty line `continue` :2453-2454), `_dispatch` malformed reply `{"ok": False, "error": f"malformed JSON: {exc}"}` :2496-2497, unknown cmd :2537 |
| `voice_typing/streaming.py` (499) | `StreamingOutput` engine :100 | ctor `(backend, feedback, streaming, *, append_space=True, rate_limit_s, clock)` :123; props `committed`/`tail`/`frozen`/`frozen_session`/`pending_tail_len` :192; `reset_after_cancel` :197 (sets `_suppressed=True`), `reset_boundary` :208 (lifts `_suppressed` + per-utterance freeze only), `reset_session` :226, `freeze(reason, *, session=False)` :248 (PROMOTE-ONLY), `note_user_keypress` :279 (per-utterance freeze), `on_partial` :301 (suppressed :314, frozen :318, EXTEND case-sensitive `text.startswith(self._tail)` :328, REVISE + 300ms rate limit :345+), `commit` :377 (frozen-absorb :415-425 — no append_space; extend/revise; space typed only in non-frozen paths), `_safe_type`/`_safe_backspace` :472/:485 (backend failure → SESSION freeze) |
| `voice_typing/textproc.py` (134) | `clean()` + `apply_streaming_guards(context, fragment)` | guard rule (a): mid-sentence (committed not ending `./!?`) lowercases first cased char :107-134; rule (b): strips one trailing `.` mid-sentence |
| `voice_typing/recorder_host.py` (1009) | Subprocess child wrapping RealtimeSTT; IPC event stream | `_dispatch` :423 — `partial`→`_on_partial` UNGATED :444-446, `speech`→`_on_speech` :447-448, `vad` GATED by a listening predicate :135-138,:453+; events documented :37-52 (`partial`/`speech`/`vad`/`speech_end`/`final`) |
| `voice_typing/key_listener.py` (347) | evdev listener | `KEY_BACKSPACE`→`backspace_cb` (daemon.cancel), every other key (incl. Shift/Ctrl/CapsLock modifiers) → `OTHER_PRESS`→`other_key_cb` (daemon.note_user_keypress) :51-66 |
| `voice_typing/config.py` (409) | Dataclass config + TOML load | `from_toml` :329-354 via `_overlay(section_cls, table_name)` for exactly 6 tables: `asr output cancel feedback filter log`; unknown KEYS raise TypeError via dataclass `__init__`; unknown TABLES silently ignored (BUG-006) |
| `voice_typing/ctl.py` (268) | voicectl client | `send_command` uses `sock.makefile("r")` — NO read timeout (AGENTS.md hang hazard; always `timeout 30 .venv/bin/voicectl …`) |
| `voice_typing/typing_backends.py` (196) | wtype/ydotool: `type_text` / `press_backspace` | |
| `voice_typing/feedback.py` (264) | Toasts/state.json mirror; `update_partial(text)` | check for a user-visible notify method before adding warnings |

## Threading / sequencing model (why the bugs are daemon-level)

- Partials arrive on the host reader thread → `daemon._on_partial` → `engine.on_partial`. Finals fire in a NEW thread per final → `daemon.on_final` under `_on_final_lock`. `cancel()` runs on the control-socket worker under daemon `self._lock`. The engine serializes via its own `self._lock` (never takes daemon locks back).
- Utterance boundary events: `engine.reset_boundary()` is called by the daemon ONLY inside `on_final` after a commit or a rejected final (:1157 and the post-commit path ~:1243). There is NO boundary event between a cancel and the next real final (the cancelled sentinel final is dropped at the suppression branch :1130-1137 before it can reach commit) — root cause of BUG-002 and BUG-007.
- New-speech signal: the child's `on_speech` hook relays `("speech", {})` → `daemon._touch_speech()` (:1354) — this is the seam the PRD recommends for explicitly lifting rejected-final freezes / post-cancel suppression at the next utterance start.

## Freeze/suppression state machine (engine)

Two freeze classes: per-utterance (`_frozen_session=False`, lifted by `reset_boundary()`; set by `note_user_keypress`) and session (`True`, survives every boundary; ONLY `reset_session()` clears; set by backend failures and — BUG-001 — by rejected finals at daemon.py:1154). While frozen: `on_partial` mirrors tail only; `commit()` absorbs tail into `committed` with NO keystrokes and NO trailing space (BUG-003). `_suppressed` (set by `reset_after_cancel`) mirrors-only until `reset_boundary()`/`commit()` (BUG-002). The in-code comment at daemon.py:1150-1153 explicitly warns: "The landed S2 test pins frozen=True across this call — do not retag to per-utterance" — because the immediately following `reset_boundary()` would lift a per-utterance freeze at once, and stray late partials of the rejected utterance must stay inert. Any fix must introduce a NEW lift semantic (explicit resume at next-utterance start), not a class flip.

## Documentation surfaces (no docs/ dir exists)

`README.md` (§Streaming dictation :129, §Backspace-cancel :164, §Feedback surfaces :182, §Configuration :197, §Logs/status/stopping :339), `config.toml` header (:22 promises "Unknown keys are REJECTED at load time"), `tests/ACCEPTANCE.md` (row 4 :35 claims the listening flag "gates BOTH the partial and commit paths" — false against code until BUG-004 is fixed; rows 11-12 :42-43 cover streaming/cancel criteria), `hypr-binds.conf`, `PRD.md` (§4.2quater).

## Operational constraints (AGENTS.md — binding for every implementing agent)

- Two timeouts on every non-trivial command (inner `timeout N` + harness timeout). `voicectl` ALWAYS under `timeout 30`. Never run the daemon in the foreground. Prefer single fast pytest files / `-k` filters; `tests/test_feed_audio.py`, parts of `test_daemon.py`, `test_recorder_host.py` and the two shell E2E suites are CUDA-heavy (minutes). Tests written for this changeset use the existing doubles → fast.

## Research provenance note

Subagent delegation was attempted 3× (inline workflow ×2, file-based workflow async + foreground) and is HARD-BLOCKED in this environment: child runs fail with "Background children require the host npm package (@earendil-works/pi-coding-agent) … does not provide @earendil-works/pi-agent-core/node" (attempt script kept at `architecture/research_workflow.js`). All findings below were therefore gathered by direct parent inspection; every line number in these files was read from source, not inferred.

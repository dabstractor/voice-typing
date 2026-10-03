name: "P1.M2.T5.S2 — Daemon-side prompt computation + commit-time refresh"
description: Formalize the rolling context-prompt computation daemon-side (committed text back to the last sentence boundary, ~200-token cap), refresh it at commit time in BOTH output modes, clear it at arm time, and surface context_prompt in voicectl status.

---

## Goal

**Feature Goal**: Every small.en decode in the recorder-host child is conditioned on the correct rolling committed context — computed by ONE formal, pure, unit-tested daemon-side function — refreshed after every commit, cleared at every arm, gated by config and by the child's capability, and visible in `voicectl status`. This replaces the "thin S2 seam" left by P1.M2.T6.S2.

**Deliverable**:
1. `voice_typing/prompt_engine.py` — NEW pure function `rolling_context_prompt(committed: str) -> str` (the formal daemon-side computation; module is already daemon-importable, stdlib-only at module scope).
2. `voice_typing/daemon.py` — formalized `_refresh_context_prompt()` (config + degrade gates, unified committed source for both modes), arm-time prompt clear (correct FIFO ordering), Rev 1-mode committed accumulator, ready-flag capture into status.
3. `voice_typing/ctl.py` — one new `status` line reporting context-prompt state (on / off (disabled) / off (degraded)).
4. `tests/test_context_prompt_refresh.py` (NEW, pure) + `rolling_context_prompt` unit tests added to `tests/test_prompt_engine.py`.
5. `voice_typing/streaming.py` — comment-only edit pointing `context_after_last_boundary` consumers at the formal function.

**Success Definition**: After any commit, the child's next decode carries `initial_prompt` = committed text back to the last sentence boundary (whole committed text when no boundary exists — the T8c pause-join case), capped at ~200 tokens; a warm re-arm never conditions on the previous session's text; `context_prompt=false` and probe-degraded children receive zero prompt pushes; `voicectl status` shows the state; all fast suites + ruff stay green.

**Scope boundary (do NOT implement here)**: T8-style E2E assertions via `feed_audio` (P1.M3.T8), any child-side/`recorder_host.py` change (the `("prompt", {...})` cmd, `set_prompt` proxy, and `ready.context_prompt` flag from S1 are complete and correct — verify only), any state-file/`feedback.py` field addition (PRD §4.6 field set is closed), any new config key (read existing `[asr] context_prompt`, config.py:63).

## User Persona (if applicable)

**Target User**: End user dictating multi-sentence paragraphs into a Hyprland window.

**Use Case**: "I dictate a long thought with natural pauses; the second half of a sentence split by a pause must come out lower-case and continue the first half, without a spurious period."

**Pain Points Addressed**: Whisper decodes each utterance as a fresh sentence → mid-paragraph fragments start capitalized / gain trailing periods. The rolling prompt tells the decoder it is *continuing*, not starting (PRD §4.2quater "Rolling context prompt").

## Why

- PRD §4.2quater: rolling context prompt is "the primary fix for mid-paragraph fragments starting capitalized or acquiring spurious trailing periods". S1 built the child mechanism (executor + `("prompt", ...)` cmd + probe/degrade); this task supplies the daemon-side brain that feeds it.
- The current thin seam (daemon.py:1353-1375) has a real semantic bug: `context_after_last_boundary` returns `""` when `committed` contains NO sentence terminator, so a long unpunctuated run (exactly the `utt_pause.wav` / T8c scenario) decodes context-free. PRD semantics: "back to the last sentence boundary" = the whole committed text when no boundary exists.
- Warm re-arm currently leaks the previous session's prompt into the new session's first utterance (the child stays resident across disarm/arm — §4.2bis).
- S1's PRP explicitly handed off: "daemon/`status` consumption is T5.S2 — do not change ctl here."

## What

Formal semantics of `rolling_context_prompt(committed)` (PRD §4.2quater + T8d):
- last `.`/`!`/`?` mid-string → the text after it (current in-progress sentence), whitespace-normalized;
- `committed` ENDS with a terminator → `""` (fresh sentence; decoder may capitalize);
- NO terminator anywhere → the WHOLE committed text (this is the seam's bug — fix it);
- cap: keep the NEWEST ~200 tokens (`prompt_engine.trim_prompt`; `_PROMPT_TOKEN_CAP` stays THE code constant; child caps again — defense in depth);
- pure, deterministic, stdlib-only.

Daemon behavior:
- **Commit-time refresh** (streaming mode, existing call site daemon.py:1105): after `self._stream.commit(...)` + `reset_boundary()`, push `rolling_context_prompt(self._stream.committed)` via `host.set_prompt(text)`.
- **Rev 1 rollback mode** (`output.streaming=false`): the daemon keeps its own committed accumulator (cleaned finals + trailing space, per `append_space`) and refreshes the prompt from it — `asr.context_prompt=true` + `output.streaming=false` is a legal combination and must not silently disable conditioning. The engine (`StreamingOutput`) is NOT touched in this mode (T6.S2 pinned the hatch "provably keystroke-identical").
- **Arm-time clear**: on every `_arm()`, queue `host.set_prompt("")` BEFORE the arm command so the FIFO cmd queue guarantees the child clears before blocking in `text()`; reset the daemon-side trackers. Idle-unload respawn starts a fresh child (prompt already None) — the clear is a harmless no-op there.
- **Gates**: push only when `cfg.asr.context_prompt` is true AND the loaded child's `ready` payload reported `context_prompt: true`. Disabled-vs-degraded is distinguishable in status.
- **Deliberate no-ops** (document in code): rejected finals (blocklist/min_chars — committed unchanged), `cancel()` (fragment never committed), and unload teardown do NOT refresh.
- **Status**: `status_snapshot()` gains an additive `context_prompt` field; `voicectl status` prints one line, e.g. `context-prompt: on` / `off (disabled by config)` / `off (degraded — context-free decoding)` / `off (models not loaded)`.

### Success Criteria

- [ ] `rolling_context_prompt` unit-pinned: mid-string boundary; terminator-at-end → `""`; **no terminator → whole committed**; >200-token run-on → newest-200 kept; whitespace normalized; empty input → `""`.
- [ ] Fake-host test: a streaming commit triggers `set_prompt(<new rolling context>)`; consecutive commits advance it.
- [ ] Fake-host test: `_arm()` calls `set_prompt("")` BEFORE `set_microphone(True)` (ordering pinned) — a warm re-arm never conditions on stale session text.
- [ ] `context_prompt=false` config → ZERO `set_prompt` calls across arm + commits; status shows disabled.
- [ ] Child degraded (`ready.context_prompt=false`) → zero pushes; status shows degraded.
- [ ] Rev 1 mode (`streaming=false`) → commits still refresh the prompt from the daemon accumulator.
- [ ] Host fake without `set_prompt`, or a raising `set_prompt` → silent DEBUG no-op, `on_final` thread survives.
- [ ] `tests/test_context_prompt_refresh.py` + `tests/test_prompt_engine.py` + adjacent fast suites green under `timeout`; ruff check/format clean on touched files.

## All Needed Context

### Context Completeness Check

A fresh agent needs: the exact existing seam and IPC (no child work required), the falsy-`""` composition trap, the FIFO ordering rule at arm, the lock discipline, and the repo's timeout rules (AGENTS.md). All below.

### Documentation & References

```yaml
- docfile: PRD.md
  why: §4.2quater "Rolling context prompt" — the normative semantics (committed text back to the last
       sentence boundary, ~200-token cap, code constant; partials AND commits conditioned; degrade
       never crashes) and §8 risk row "initial_prompt constructor-static → child updates between
       utterances; on failure degrade to context-free decoding + log"
  section: 4.2quater (also 4.5 config context_prompt, 6 T8c/T8d)

- file: voice_typing/prompt_engine.py
  why: S1 output. `_PROMPT_TOKEN_CAP = 200` (~line 51) is THE cap constant; `trim_prompt(text, cap)`
       (~line 95) is the pure cap to reuse; module docstring guarantees daemon-safe import
       (stdlib-only module scope, CUDA imports are lazy inside methods)
  pattern: add `rolling_context_prompt` here — one home for prompt semantics, next to trim_prompt
  gotcha: do NOT touch PromptedExecutor (child-only CUDA object); keep the new function pure

- file: voice_typing/daemon.py
  why: ALL wiring lands here. Anchors: `on_final` streaming branch + `self._refresh_context_prompt()`
       call at ~1006-1105 (inside `with self._on_final_lock:`); `_arm()` at ~1107-1129
       (`stream_reset()` getattr seam ~1117-1120, then the arm/mic call); `_refresh_context_prompt()`
       thin seam at ~1353-1375; `_load_host` at ~770-820 (`self._host_factory` injection seam ~775,
       `self._resolved_device_cache = host.device` ready-dict capture ~797-800 — the ready dict
       ALREADY carries `context_prompt`); `status_snapshot()` builds the status payload
  pattern: keep the defensive getattr seam style (host without set_prompt = DEBUG no-op);
       never raise out of the refresh path; refresh stays INSIDE _on_final_lock; NEVER take
       self._lock from the on_final path (existing lock-ordering rule)
  gotcha: `_arm` runs under `self._lock`; `host.set_prompt` is a fast best-effort queue put — safe

- file: voice_typing/recorder_host.py
  why: the S1 IPC this task drives — `RecorderHost.set_prompt(text)` (~259-271) queues
       `("prompt", {"text": text})`; child dispatch (~716-725) applies it BETWEEN utterances
       (cmd loop blocks in text() otherwise — commit-time sends land by design, NO watcher
       thread); `_ready_payload` (~810-819) + `RecorderHost.device` (~183-186) expose
       `context_prompt: bool`
  pattern: FIFO single-reader queue ⇒ ORDER of puts is delivery order — the arm-time clear must
       be queued BEFORE the arm cmd
  gotcha: READ-ONLY for this task — no changes needed or wanted here

- file: voice_typing/streaming.py
  why: `context_after_last_boundary()` (~44-62, the seam's slicer — returns "" when NO boundary:
       the bug this task supersedes) and `StreamingOutput.committed` property (~168, the
       streaming-mode prompt source). Existing slicer tests live in tests/test_streaming_commit.py
  pattern: leave the slicer's contract and tests intact; daemon switches to
       prompt_engine.rolling_context_prompt; comment-only edit here pointing at the formal function
  gotcha: do NOT "compose" `slicer(c) or trim(c)` — "" is ambiguous between ends-with-terminator
       (prompt must stay empty) and no-terminator (prompt must be everything); the rfind must live
       inside rolling_context_prompt

- file: voice_typing/textproc.py
  why: `_SENTENCE_TERMINALS = ".!?"` (~79) — the canonical boundary set; streaming.py pins its copy
       "verbatim" to it. The new function's boundary set must match (pinned copy + comment is the
       established repo convention)
- file: voice_typing/config.py
  why: `AsrConfig.context_prompt: bool = True` at line 63 (bool-validated ~109-114) — READ only,
       no schema change
- file: voice_typing/ctl.py
  why: status pretty-printer (~64-90) reads the response via `.get` — additive keys are safe;
       add one context-prompt line following the existing f-string block
- file: tests/test_streaming_commit.py
  why: the fast test pattern — RecordingBackend / FakeFeedback / FakeClock doubles (copied from
       test_streaming_core.py) + docstring-documented coverage list; follow it for the new file
- file: tests/test_control_socket.py
  why: constructs the daemon with an injected fake host factory (the `self._host_factory` seam) —
       NO CUDA; the pattern for daemon-wiring tests
- file: tests/test_prompt_engine.py
  why: S1's pure unit tests — extend with rolling_context_prompt cases (same style)
- file: tests/test_voicectl.py
  why: pattern for asserting the new status line
- file: plan/007_cfc245548aec/P1M2T5S2/research/daemon_prompt_computation.md
  why: this task's codebase-research notes (anchors + gap analysis + the T8c no-boundary proof)
- file: plan/007_cfc245548aec/P1M2T5S1/PRP.md
  why: sibling PRP — the IPC contract this task completes, and the explicit handoff
       "daemon/status consumption is T5.S2 — do not change ctl here" (i.e. change it HERE)
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── prompt_engine.py     # S1: PromptedExecutor (child-only CUDA) + trim_prompt + probe — pure parts daemon-importable
├── recorder_host.py     # S1: ("prompt", {...}) child cmd + set_prompt proxy + ready.context_prompt  [READ-ONLY here]
├── streaming.py         # T6: StreamingOutput (committed property) + context_after_last_boundary (thin slicer)
├── daemon.py            # on_final/_arm/_load_host/_refresh_context_prompt/status_snapshot wiring points
├── ctl.py               # voicectl status printer
└── textproc.py          # _SENTENCE_TERMINALS + apply_streaming_guards (T4, done)
tests/
├── test_prompt_engine.py        # S1 pure tests (extend)
├── test_streaming_commit.py     # doubles + slicer tests (pattern)
├── test_control_socket.py       # fake-factory daemon construction (pattern)
└── test_voicectl.py             # status-output assertions (pattern)
```

### Desired Codebase tree with files to be added

```bash
voice_typing/
├── prompt_engine.py     # MODIFIED: + rolling_context_prompt(committed) + pinned boundary constant
├── daemon.py            # MODIFIED: formal _refresh_context_prompt, _arm clear, Rev 1 accumulator,
│                        #   ready-flag capture, status_snapshot context_prompt field
├── ctl.py               # MODIFIED: one status line
└── streaming.py         # MODIFIED: comment-only pointer (slicer docstring → formal function)
tests/
├── test_prompt_engine.py          # MODIFIED: + rolling_context_prompt unit tests
└── test_context_prompt_refresh.py # NEW: daemon wiring tests (fake host factory, no CUDA)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL (AGENTS.md): every test/CLI under GNU `timeout` + a bash-tool timeout ABOVE it.
#   `timeout 120 ... pytest` (bash timeout 180); `timeout 30 .venv/bin/voicectl ...`;
#   NEVER run the daemon in the foreground. tests/test_daemon.py, test_recorder_host.py,
#   test_feed_audio.py are HEAVY CUDA — put new tests in a NEW pure file.
# CRITICAL: the daemon process must stay CUDA-free — prompt_engine is safe to import (stdlib-only
#   module scope; CUDA imports are lazy INSIDE PromptedExecutor methods) but never import
#   faster_whisper/RealtimeSTT/recorder-host worker paths daemon-side.
# CRITICAL (composition trap): `context_after_last_boundary(c) or trim_prompt(c)` is WRONG — ""
#   means BOTH "ends with terminator" (prompt stays empty) and "no terminator" (prompt = everything).
#   Do the rfind inside rolling_context_prompt.
# GOTCHA (FIFO): the child reads cmd_queue with ONE reader, in order, only between text() blocks.
#   Queue the arm-time clear BEFORE the arm cmd or the new session's FIRST utterance decodes on the
#   stale prompt (child blocks in text() right after arming).
# GOTCHA: refresh must NEVER raise (on_final reader thread survives) and must NOT log prompt TEXT
#   above DEBUG (it is user dictation).
# GOTCHA: host.set_prompt("") clears the child (executor maps ""→None→cleared); the push is
#   best-effort (dead/full queue = no-op by S1 contract) — do not add retries.
# GOTCHA: ctl reads status via .get — additive keys only; do not rename existing fields.
# GOTCHA: mp queues pickle payloads — only plain strings cross (already true).
```

## Implementation Blueprint

### Data models and structure

No new config/schema/ORM models. The only new "model" is one pure function + small daemon-side scalars:

```python
# voice_typing/prompt_engine.py (daemon-importable; stdlib-only at module scope)
_CONTEXT_BOUNDARY_CHARS = ".!?"  # pinned verbatim to textproc._SENTENCE_TERMINALS (repo convention)

def rolling_context_prompt(committed: str) -> str:
    """The formal daemon-side computation (PRD §4.2quater; P1.M2.T5.S2).

    committed back to the last sentence boundary, whitespace-normalized, capped to the
    NEWEST _PROMPT_TOKEN_CAP tokens:
      - terminator mid-string  -> text after it (in-progress sentence)
      - committed ends with it -> "" (fresh sentence)
      - no terminator anywhere -> the WHOLE committed text (the T8c pause-join case)
    """
    last = max((committed or "").rfind(ch) for ch in _CONTEXT_BOUNDARY_CHARS)
    source = committed[last + 1 :] if last >= 0 else committed
    return trim_prompt(source)

# voice_typing/daemon.py (fields on VoiceTypingDaemon.__init__)
self._context_prompt_active: bool | None = None   # None = no child loaded yet; else ready-payload flag
self._rev1_committed: str = ""                     # Rev 1 mode accumulator (streaming=false)
# (optional) self._last_sent_prompt: str | None    # DEBUG-noise dedup ONLY — must reset at arm/spawn
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/prompt_engine.py — the formal computation
  - IMPLEMENT: rolling_context_prompt(committed) exactly per the blueprint above (own rfind — no
    delegation to streaming's slicer; see composition-trap gotcha)
  - REUSE: trim_prompt + _PROMPT_TOKEN_CAP (do not invent a second heuristic/constant)
  - NAMING/PLACEMENT: module-level public function beside trim_prompt; boundary constant pinned
    to textproc._SENTENCE_TERMINALS via comment
  - PURITY: no imports beyond stdlib; never raises on weird input (None/empty degrade to "")

Task 2: MODIFY tests/test_prompt_engine.py — pin the semantics
  - IMPLEMENT: test_rolling_prompt_* cases — mid-string boundary slice; ends-with-terminator -> "";
    NO terminator -> whole committed; >200-token run-on keeps newest 200; whitespace collapsed;
    empty/None -> "". FOLLOW the existing style in this file (fast, pure)
  - COVERAGE: each Success-Criterion bullet from "What" maps to one named test

Task 3: MODIFY voice_typing/daemon.py — formalize _refresh_context_prompt (~1353)
  - IMPLEMENT: gates first (`cfg.asr.context_prompt` false → return; `self._context_prompt_active`
    is not True → return, models-unloaded None → return); source = `self._stream.committed` when
    `cfg.output.streaming` else `self._rev1_committed`; text = prompt_engine.rolling_context_prompt(source);
    push via the existing defensive getattr seam; never raise; DEBUG logs without user text
  - REPLACE: the streaming.context_after_last_boundary call at ~1367
  - PRESERVE: call site at ~1105 (inside _on_final_lock, after commit + reset_boundary) — do not move it

Task 4: MODIFY voice_typing/daemon.py — _arm-time clear (~1107-1129)
  - IMPLEMENT: right AFTER `stream_reset()` and BEFORE the host arm/mic call, reset
    `self._rev1_committed = ""` (and the dedup tracker if added), then queue the clear via the
    same defensive seam (`set_prompt("")`) so FIFO puts it ahead of the arm cmd
  - GATE: same config gate as Task 3 (disabled → skip the put entirely)
  - GOTCHA: host is guaranteed loaded at _arm time (single-flight load precedes it) — keep the
    defensive getattr anyway (test fakes / legacy adapter)

Task 5: MODIFY voice_typing/daemon.py — Rev 1 accumulator + refresh in the Rev 1 branch
  - IMPLEMENT: in on_final's `else` (rollback-hatch) branch after the backend type: append
    `self._rev1_committed = (self._rev1_committed.rstrip() + " " + cleaned).lstrip()` + trailing
    space iff append_space (mirror StreamingOutput.commit's join discipline), then call
    `self._refresh_context_prompt()` (outside/after the latency log is fine; keep it inside
    _on_final_lock like the streaming branch)
  - DO NOT touch StreamingOutput in this branch (T6.S2 pinned the hatch keystroke-identical)

Task 6: MODIFY voice_typing/daemon.py — ready-flag capture + status field
  - IMPLEMENT: in _load_host's success block (~797-800, where `self._resolved_device_cache =
    host.device`), also `self._context_prompt_active = bool(host.device.get("context_prompt",
    False))`; reset to None on unload/teardown paths (find them via the existing phase->unloaded
    transitions)
  - IMPLEMENT: status_snapshot() gains `"context_prompt"` — derive a human label: on (active) /
    off (disabled by config) / off (degraded) / off (models not loaded). ADDITIVE key only
  - FOLLOW pattern: how models_loaded/phase are already surfaced in status_snapshot

Task 7: MODIFY voice_typing/ctl.py — one status line
  - IMPLEMENT: after the existing f-string block (~64-90), print e.g.
    f"context-prompt: {label}\n" from response.get("context_prompt") — follow the phase line's
    .get-with-default style; keep every existing line byte-identical

Task 8: MODIFY voice_typing/streaming.py — comment-only pointer
  - EDIT: context_after_last_boundary's docstring (~44-62): note the formal daemon-side
    computation now lives in prompt_engine.rolling_context_prompt (P1.M2.T5.S2) and this slicer
    keeps its ""-on-no-boundary contract (pinned by tests). NO behavior change.

Task 9: CREATE tests/test_context_prompt_refresh.py — daemon wiring (pure, no CUDA)
  - IMPLEMENT with the daemon's host-factory seam (see tests/test_control_socket.py) +
    RecordingBackend/FakeFeedback doubles (copied per test_streaming_commit.py convention):
    - commit (streaming) pushes set_prompt with the new rolling context; two commits advance it
    - _arm orders set_prompt("") BEFORE set_microphone(True) (record call order on the fake host)
    - context_prompt=false → zero set_prompt across arm+commits; status label "disabled"
    - ready flag false (degraded fake) → zero pushes; status label "degraded"
    - Rev 1 mode commits refresh from the accumulator
    - fake host WITHOUT set_prompt → DEBUG no-op, no crash; raising set_prompt → swallowed
    - rejected final (blocklist) does NOT push
  - NAMING: test_{behavior} functions; file docstring lists coverage (house style)
  - PLACEMENT: tests/test_context_prompt_refresh.py — NOT in the heavy test_daemon.py
```

### Implementation Patterns & Key Details

```python
# The refreshed daemon seam (illustrative — keep the existing defensive style):
def _refresh_context_prompt(self) -> None:
    """Push the rolling context prompt to the child (P1.M2.T5.S2 — formal computation).

    Gates: [asr].context_prompt config AND the child's ready-payload context_prompt flag.
    Source: StreamingOutput.committed (streaming) / self._rev1_committed (Rev 1 hatch).
    Never raises; prompt text is never logged above DEBUG.
    """
    try:
        if not self._cfg.asr.context_prompt or self._context_prompt_active is not True:
            return
        source = self._stream.committed if self._cfg.output.streaming else self._rev1_committed
        text = prompt_engine.rolling_context_prompt(source)
        setter = getattr(self._host, "set_prompt", None)
        if callable(setter):
            setter(text)
        else:
            logger.debug("context-prompt push skipped: host has no set_prompt seam")
    except Exception:
        logger.debug("context-prompt push failed (ignored)", exc_info=True)

# _arm ordering (the load-bearing two lines):
#   stream_reset()                       # engine strings reset (existing, ~1117-1120)
#   self._rev1_committed = ""            # + tracker reset
#   ... defensive set_prompt("") put ...  # MUST precede the host arm/mic put (FIFO delivery)
```

### Integration Points

```yaml
IPC:
  - uses EXISTING ("prompt", {"text": str}) child cmd + RecorderHost.set_prompt — NO child change
  - delivery contract (S1): read between utterances only — commit-time sends land before the next
    decode; arm-time clear must be queued BEFORE the arm cmd (FIFO)
CONFIG:
  - no schema change; read [asr].context_prompt (config.py:63) and output.streaming/append_space
STATUS:
  - status_snapshot(): additive "context_prompt" key; ctl.py prints one line
DEPENDENTS (do not break):
  - P1.M3.T8 (T8d) asserts decodes carry initial_prompt = this computation — the function's
    semantics are the contract
LOGS:
  - DEBUG for pushes/clears (never the text); no new INFO lines required
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/ruff check voice_typing/prompt_engine.py voice_typing/daemon.py voice_typing/ctl.py voice_typing/streaming.py tests/test_context_prompt_refresh.py tests/test_prompt_engine.py --fix
.venv/bin/ruff format voice_typing/prompt_engine.py voice_typing/daemon.py voice_typing/ctl.py voice_typing/streaming.py tests/test_context_prompt_refresh.py tests/test_prompt_engine.py
# Expected: zero errors. (mypy only if already configured in this repo — skip silently if absent.)
```

### Level 2: Unit Tests (Component Validation)

```bash
# New + S1 prompt suites (pure, fast). bash-tool timeout 180 on each:
timeout 120 .venv/bin/python -m pytest tests/test_prompt_engine.py tests/test_context_prompt_refresh.py -q
# Adjacent fast suites — prove no regression in the touched seams:
timeout 240 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_commit.py tests/test_streaming_freeze.py tests/test_textproc.py tests/test_config.py tests/test_control_socket.py tests/test_voicectl.py -q
# Expected: all pass. On failure, fix the implementation — the slicer's own tests must ALSO still
# pass unchanged (comment-only edit to streaming.py).
```

### Level 3: Integration Testing (bounded; daemon only via systemd — NEVER foreground)

```bash
# Optional heavy regression (CUDA, minutes). bash-tool timeout 700:
timeout 600 .venv/bin/python -m pytest tests/test_recorder_host.py -q

# Live smoke (systemd unit; every voicectl under timeout 30 — AGENTS.md):
systemctl --user restart voice-typing 2>/dev/null || true
timeout 30 .venv/bin/voicectl start
timeout 30 .venv/bin/voicectl status     # expect a "context-prompt: ..." line (on, GPU healthy)
timeout 30 .venv/bin/voicectl stop
journalctl --user -u voice-typing --since '-3 min' | grep -i 'context-prompt'   # armed/degrade INFO from S1 still present
# Cleanup if anything wedges (AGENTS.md): timeout 30 .venv/bin/voicectl quit; systemctl --user stop voice-typing; pkill per AGENTS.md.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# The full T8d assertion (decodes carry the prompt via child log/kwargs) belongs to P1.M3.T8 — do
# not build it here. A bounded manual proxy, only if desired: temporarily copy config.toml to
# $XDG_CONFIG_HOME/voice-typing/config.toml with [log] level="DEBUG", restart the unit, dictate one
# sentence across a pause, and grep the journal for context-prompt DEBUG push lines; then restore
# the config. Do NOT leave DEBUG enabled.
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1 clean (ruff check + format on all touched files)
- [ ] `tests/test_prompt_engine.py` + `tests/test_context_prompt_refresh.py` green under `timeout`
- [ ] Adjacent fast suites (streaming×3, textproc, config, control_socket, voicectl) green
- [ ] `tests/test_streaming_commit.py` slicer tests pass UNCHANGED (streaming.py was comment-only)
- [ ] No new import of faster_whisper/RealtimeSTT anywhere in daemon.py (CUDA purity preserved)

### Feature Validation
- [ ] rolling_context_prompt semantics pinned: no-boundary → whole committed; ends-with-terminator → ""; newest-200 cap
- [ ] Commit → `set_prompt(rolling_context_prompt(committed))`; Rev 1 mode refreshes from the accumulator
- [ ] Arm → clear queued BEFORE arm; warm re-arm never conditions on the previous session
- [ ] `context_prompt=false` and degraded child → zero pushes; distinguishable status labels
- [ ] Rejected finals / cancel / teardown do not refresh (documented in code)
- [ ] `voicectl status` shows the context-prompt line; existing lines byte-identical

### Code Quality Validation
- [ ] Defensive getattr seam style preserved; refresh never raises; prompt text never logged ≥ INFO
- [ ] No recorder_host.py / feedback.py / config.py changes; no new config keys
- [ ] Call site stays inside `_on_final_lock`; no `self._lock` acquisition from the on_final path
- [ ] New tests are pure (no CUDA, no mic, no keystrokes) per the test_streaming_commit.py pattern

### Documentation & Deployment
- [ ] streaming.py slicer docstring points at prompt_engine.rolling_context_prompt
- [ ] No env vars / config additions to document (README sync is P1.M3.T10)

## Anti-Patterns to Avoid

- ❌ Don't compose `context_after_last_boundary(c) or trim_prompt(c)` — the `""` ambiguity corrupts both the fresh-sentence and no-boundary cases.
- ❌ Don't "fix" streaming.context_after_last_boundary's no-boundary `""` contract — it is pinned by tests and superseded, not wrong, for the slicer's role; the formal function does its own rfind.
- ❌ Don't queue the arm-time clear after the arm cmd, or add a watcher thread to force prompt delivery — FIFO + between-utterance reads are the designed contract.
- ❌ Don't push prompts when disabled or degraded "for safety" — the gates are the spec; a degraded child ignores them anyway, but status must tell the truth.
- ❌ Don't let StreamingOutput gain Rev 1 knowledge — the rollback hatch stays keystroke-identical; the daemon accumulates.
- ❌ Don't run pytest/voicectl without GNU `timeout`; never foreground the daemon (AGENTS.md).
- ❌ Don't log prompt text at INFO — it is user dictation.

---

**Confidence Score: 9/10** — the IPC, config field, ready flag, and commit-time call site all exist and are test-pinned; the only judgment calls (no-boundary semantics, Rev 1 accumulator, status labeling) are derived directly from the PRD text and S1's explicit handoff, and every wiring point has a line anchor plus an existing fake-based test pattern.

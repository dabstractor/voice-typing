# P1.M3.T3.S2 research — delivery status surface (feedback fields + voicectl status rendering)

Verified live at research time (line anchors CURRENT; the item contract's anchors had drifted).

## §0 Current state (verified)

### feedback.py (`voice_typing/feedback.py`, 289 lines)
- `_state` init ≈ **lines 92-110** (contract said 92-105): keys today =
  `listening, phase, models_loaded, mode ("lite" constant), ducked, partial, last_final, ts`.
  Every key is ALWAYS present (additive-key recipe: seed in `__init__`, never add later).
- Setter precedents (all: ALWAYS write via `self._write()`, NEVER notify):
  `set_phase` :~124 (docstring: "accepts any string (no validation)"), `set_models_loaded`
  :~135, `set_mode` :~147, `set_ducked` :~163 (pair-with-docstring style), `record_final`
  :~183, `set_listening` :~205. `snapshot()` :~230 returns `dict(self._state)` (copy).
- `update_partial` :~111 is the ONLY throttled method (`_PARTIAL_WRITE_MIN_INTERVAL = 0.1`,
  module const :~74). In-memory always updated; disk write throttled.
- Module docstring (lines 1-70) documents the state.json schema inline — Mode A doc home.
- Pure stdlib; `FeedbackConfig` only (it does NOT see OutputConfig).

### daemon.py (`voice_typing/daemon.py`, ~3160 lines)
- `status_snapshot()` at **line 2463** (item contract said 2275-2318 — drifted +188):
  returns 14 keys; reads LIVE `self._feedback.snapshot()` for phase/models_loaded/partial/
  last_final via `snap.get(key, default)` (the additive-key pattern proven by `mic_*` +
  `context_prompt` keys). `_context_prompt_label()` :2447 = the label precedent
  (precedence-ordered human label; never raises).
- Docstring says "…— 14 keys" (must become 18).
- Callers: control-socket dispatch spreads `{"ok": True, **status_snapshot()}`
  (daemon.py:1964, 1981, 2885, 2909). Additive keys flow to every status/toggle/start/stop
  reply automatically.

### ctl.py (`voice_typing/ctl.py`, 301 lines)
- `format_result(cmd, response)` :~90 — PURE (dict in → (text, exit_code) out).
  Status branch :~105-171: builds the multi-line block ending
  `f"context-prompt: {context_prompt}"`, then optional `load error:` line.
  Defensive `.get(key, default)` everywhere; `context_prompt` missing → `"unknown"`
  (old-daemon tolerance precedent). `_STATUS_ON` module dict in tests is the fixture.
- Mode A doc surface: `format_result` docstring :~85-90 (stale — doesn't mention
  context_prompt yet; fix while adding delivery) + module docstring/epilog.
- `_COMMANDS` unchanged by this task (no new command; `session` is M6.T2.S3).

### The taxonomy source (P1.M3.T1.S1 + controller)
- `voice_typing/bulk_delivery.py` `ShowResult` (:77-90): applied|unchanged|refused|unknown
  — "serialized verbatim into status/log lines (R.5's delivery_state/delivery_reason surface)".
- `voice_typing/bulk_controller.py` docstring: **"P1.M3.T3 (config gate + the
  delivery_state surface, fed by stats())"** — i.e. M6 wiring derives the feedback calls from
  `stats()` (`active`, `stopped_reason`, counters) + `on_stopped(reason)`. Stop reasons:
  `queue-overflow | op-deadline | refused | unknown | target-error` (fault-class) +
  `stopped` / acquire-failure (non-fault). ONLY APPLIED confirms an op.

## §1 Design (locked)

Feedback `_state` gains 4 always-present keys:
```python
"delivery_mode": "stream-edit",   # config-default literal; M6.T2.S1 seeds from cfg.output.delivery
"delivery_state": "inactive",     # inactive|active|unsupported|fault (PRD R.5 taxonomy)
"delivery_reason": "",            # one concise reason; whitespace-collapsed, <=160 chars
"last_confirmed_op": "",          # counts+times descriptor (M6 format); sanitized same way
```
Three setters (set_phase style — always write, never notify; only ever called by the
M4/M6 bulk wiring; `partial` is never hijacked):
- `set_delivery_mode(mode)` — ValueError unless mode ∈ ("stream-edit", "bulk-text").
- `set_delivery_state(state, reason="")` — ValueError unless state ∈ taxonomy; reason is
  ALWAYS overwritten (default "" clears a stale reason); sanitized.
- `record_confirmed_op(op)` — sanitized; the mechanical "state NEVER carries the
  surrounding user document" guard (collapse whitespace + truncate 160).
Sanitizer: `" ".join(s.split())[:160]` shared module helper, applied to reason + op only
(NOT partial/last_final, which carry recognition text by design).

daemon `status_snapshot`: 4 additive keys `snap.get(...)`-read with the same seeds as
Feedback defaults (stale `_FakeFeedback` doubles in tests keep working); docstring 14→18.

ctl status branch, AFTER the context-prompt line:
- always `delivery: {mode} ({state})` (missing/empty key → "unknown", context_prompt precedent)
- `delivery reason: {reason}` line ONLY when reason non-empty
- `delivery op: {op}` line ONLY when op non-empty
Today (stream-edit, nothing wired) this renders exactly one new line:
`delivery: stream-edit (inactive)` — truthful (bulk path not wired until M6).

## §2 Files (exactly 6)
feedback.py, daemon.py, ctl.py, tests/test_feedback.py, tests/test_daemon.py,
tests/test_voicectl.py. NOT touched: config.py/config.toml (S1, parallel),
bulk_controller.py/bulk_delivery.py/test_bulk_* (T1.S1 done + T2.S3 in flight).

## §3 Test seams (verified)
- tests/test_feedback.py: `feedback` fixture :~91 (fb, recorder-mock, frozen clock),
  `_read_state(tmp_path)` :~100; `test_state_shape_has_the_documented_fields` :125 has the
  EXACT-key-set assertion to extend (+4 keys); never-notify tests monkeypatch via the
  recorder mock (`test_set_phase_never_invokes_hyprctl` :316 pattern).
- tests/test_daemon.py: `test_status_snapshot_keys_and_cuda_values` :1954 — `set(s) ==`
  EXACT 14-key assertion (extend to 18); `_make_daemon_with_feedback` gives a REAL Feedback.
  `_FakeFeedback` double :~40 has a minimal `snapshot()` (why .get defaults are load-bearing).
- tests/test_voicectl.py: format tests call `ctl.format_result("status", resp)` with
  `_STATUS_ON` dict spreads; containment (`in text`) assertions, exit code 0.

## §4 Commands (AGENTS.md discipline: inner timeout + .venv/bin/python)
- `timeout 120 .venv/bin/python -m pytest tests/test_feedback.py tests/test_voicectl.py -q`
- `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -k status_snapshot -q`
  (targeted — the full file loads CUDA models, minutes)
- `timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py -q` (stub-based, fast)

## §5 Out of scope (owned elsewhere)
- Daemon consumption of cfg.output.delivery / seeding delivery_mode at boot → P1.M6.T2.S1.
- Controller→feedback wiring (on_stopped/stats → setters), stop-reason→state mapping code →
  M6.T2.S1 (this task only DOCUMENTS the mapping in setter docstrings).
- `voicectl session [--copy]` → M6.T2.S3 (d2 §4 recipe exists; NOT this task).
- Any new ctl command; any change to `_COMMANDS`.

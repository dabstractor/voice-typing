# Research Brief: README.md teardown / phase / config-validation doc sync (P1.M4.T1.S1)

**Status:** All three post-fix behaviors VERIFIED against the LANDED code in this repo on
2026-07-14 (the bugfix milestones P1.M1.T2, P1.M2.T1, P1.M3.T1 are all Complete/landed per
`plan_status`). The README currently still documents the PRE-fix behavior in three spots;
this task updates exactly those three prose blocks. NO code, NO tests, NO ACCEPTANCE.md
(that is S2's job).

---

## 1. The three README regions to update (exact current text + line numbers)

README.md is 333 lines. All line numbers below are the CURRENT state (pre-edit); they will
shift slightly as edits land, so the `edit` tool anchors on exact TEXT, not line numbers.

### Region A — config validation (item clause (c), Issue 4) — README lines 162–165

Inside `### Voice-activity constants are NOT config keys` (header at line 153). Current text:

```
To change VAD sensitivity, edit `daemon.py` and restart the daemon. Do **not** add
these names to `config.toml`. The config loader (`config.py`) rejects unknown keys
with `TypeError`, so a stray key makes the daemon fail to load and systemd's
`Restart=on-failure` loops it forever.
```

GAP: documents UNKNOWN-KEY rejection only. Does NOT mention that a WRONG-TYPED value is also
rejected at load. Fix: append a sentence mirroring the unknown-key behavior for wrong types.

### Region B — phase lifecycle (item clause (b), Issue 2) — README lines 308–312

Inside `### Model lifecycle & VRAM` (header at line 294). Current text:

```
`voicectl status` surfaces the lifecycle: `phase:` is `unloaded` (boot /
idle-unloaded), `loading` (first arm), `idle` (loaded, disarmed), or `listening`
(armed); the `models:` line ends in `(loaded)` or `(not loaded)`. The journal logs
`voice-typing models loaded (lazy load complete); recorder resident` on load and
`voice-typing idle-unload: 1800.0s disarmed; unloading models` on idle teardown.
```

GAP: enumerates the phase states but never states the disarm→idle TRANSITION. Fix: insert a
sentence stating that disarming (stop / toggle-off / 30 s auto-stop) transitions `phase`
back to `idle`. (There is a SECOND phase mention at lines 287–290 in the `### Logs, status,
stopping` section — "then `idle`/`listening`" — but the item targets the lifecycle paragraph
at ~308–312; do NOT edit 287–290 to avoid redundancy.)

### Region C — teardown budget (item clause (a), Issue 1) — README lines 330–333

Last paragraph of `### Model lifecycle & VRAM` / the stopping section. Current text:

```
`voicectl quit` and `systemctl --user stop` complete in seconds. Teardown is
bounded at ≤10s — if `recorder.shutdown()` wedges, the recorder's worker processes
are force-terminated so VRAM is actually released. The old ~90s systemd stop
timeout (`Failed with result 'timeout'` / SIGKILL) is gone.
```

GAP/INACCURACY: "bounded at ≤10s" is stale (now 5 s), and "the old ~90s SIGKILL is gone" was
PROVEN INACCURATE by Issue 1 — the SIGTERM path still SIGKILLed at 15 s until this fix. Fix:
state single-flight + ≤5 s join, exits in seconds under `TimeoutStopSec=15`, SIGTERM path no
longer races a double teardown.

---

## 2. VERIFIED post-fix code facts (the README MUST match these)

### Region A — config type validation (Issue 4) — `voice_typing/config.py`
- `AsrConfig.__post_init__` at **config.py:65** — validates 4 float fields (accept int|float,
  reject bool via the `isinstance(True,int)` guard) + 4 str fields (must be str). Raises
  `TypeError(f"[asr] {field} expects a number (int or float), got {type}: {value!r}")` /
  `f"[asr] {field} expects str, got {type}: {value!r}"`. **Field name always in the message.**
- `FeedbackConfig.__post_init__` at **config.py:121** — `notify_ms` must be int (reject
  bool/float/str). `TypeError(f"[feedback] notify_ms expects int, got {type}: {value!r}")`.
- Path: `VoiceTypingConfig.from_toml` → `_overlay` → `section_cls(**section)` → `__post_init__`
  runs AT LOAD → TypeError propagates (not caught). So a wrong type fails fast at load, same
  severity as an unknown key (which is rejected by the dataclass `__init__`).
- Exact examples to cite (verified by S2's tests, P1.M3.T1.S2): `auto_stop_idle_seconds =
  "thirty"` → TypeError naming the field; `device = 123` → TypeError; bare int accepted for a
  float field (NOT coerced); `true`/`false` bool rejected for numeric fields.

### Region B — phase→idle on disarm (Issue 2) — `voice_typing/daemon.py`
- `_disarm()` at **daemon.py:918** calls `self._feedback.set_phase("idle")` with the comment
  `# Issue 2 / P1.M2.T1.S1: 'loaded / not listening' ⇒ phase idle (PRD §4.2bis, §4.6)`.
- So after ANY disarm path — manual `stop`, `toggle` off, or the 30 s `auto_stop_idle_seconds`
  auto-stop — `phase` returns to `idle` (loaded, not listening). This is what makes
  `voicectl status` self-consistent (`listening: off` / `phase: idle`).

### Region C — single-flight bounded teardown (Issue 1) — `recorder_host.py` + `daemon.py`
- `recorder_host.py:87` → `_STOP_JOIN_TIMEOUT_S: float = 5.0` (the join budget; was 10 pre-fix).
- `recorder_host.py:255` → `def stop(self, timeout: float = _STOP_JOIN_TIMEOUT_S)` (default 5 s).
  `:287-291` → joins the child up to `timeout`, then SIGKILLs the child's PROCESS GROUP
  (force-releases ALL VRAM — all CUDA lives in the child).
- `recorder_host.py:140` → `self._stop_lock = threading.Lock()`. `:264-274` → "SINGLE-FLIGHT
  (thread-safe, bugfix Issue 1 / P1.M1.T1.S1): the ENTIRE body — including the `self._proc is
  None` early guard — runs under `self._stop_lock`." A concurrent second caller (the SIGTERM
  signal thread + the main-thread `finally` block) shares the ONE in-progress join+SIGKILL.
- `daemon.py:554` → `self._teardown_done = threading.Event()`; `:550` comment: "signaled when
  the in-flight `_bounded_shutdown()` finishes" so `main()`'s `daemon.shutdown()` waits rather
  than starting a parallel teardown. `daemon.py:342` → `_TEARDOWN_WAIT_TIMEOUT = 8.0`
  ("8.0s covers a ~7s teardown (5s join + ...)").
- systemd: `systemd/voice-typing.service:52` → `TimeoutStopSec=15`. (The "old ~90s" in the
  current README refers to systemd's DEFAULT; this unit sets 15 s. Pre-fix, the SIGTERM path
  hit 15 s and was SIGKILLed with `Failed with result 'timeout'`; post-fix it exits in seconds.)
- Net user-facing fact: `systemctl --user stop` (and session-logout SIGTERM) now exit in a few
  seconds, well under 15 s, with no systemd SIGKILL and no `Failed with result 'timeout'`.

---

## 3. Scope boundaries (what this task is NOT)

- **README.md ONLY.** Three prose edits within two existing sections. No new files, no new
  headings (so all internal `#anchor` links stay valid), no code, no tests.
- **NOT `tests/ACCEPTANCE.md`.** That is the SIBLING task **P1.M4.T1.S2** ("Update
  tests/ACCEPTANCE.md teardown criteria + add SIGTERM-path test coverage note"). Do NOT touch
  ACCEPTANCE.md — it would collide with S2. (Confirmed: S2 owns it.)
- **NOT any `.py` file.** The fixes are LANDED; this task only documents them. Do NOT "fix"
  code if a README edit reveals a mismatch — raise it instead.
- **NOT the other phase mention** at README lines 287–290 (the `Logs, status, stopping`
  section). The item targets the lifecycle paragraph at ~308–312. Editing both is redundant;
  edit the lifecycle paragraph only.
- **NOT `PRD.md` / `tasks.json` / `prd_snapshot.md` / `.gitignore` / `config.toml` /
  `pyproject.toml` / `uv.lock`.** All forbidden or out of scope.

---

## 4. Markdown style conventions to preserve (for a clean diff)

- The README uses **manual soft-wrapping at ~76–80 columns** (hard newlines within
  paragraphs). New/edited prose MUST be wrapped the same way (wrap at ~76 chars). Do NOT
  reflow the whole file — only the edited blocks.
- Inline code uses single backticks (`` `config.py` ``, `` `TypeError` ``, `` `voicectl
  status` ``). Em dashes `—` and `≤`/`≥` glyphs are used as-is (preserve them in anchors).
- Bold for emphasis uses `**...**`. Section headers are `###` under `##`.
- Do NOT add a Table of Contents or change any heading text/level (keeps anchors stable).
- Keep the tone consistent with the surrounding user-facing prose (factual, second-person,
  no marketing).

---

## 5. Validation approach (no pytest for docs — use accuracy + scope gates)

Documentation has no unit tests. The gates are:
1. **Markdown validity** — the file still parses; code-fence count is even; no heading was
   removed (anchors intact).
2. **Factual accuracy** — grep the LANDED code to confirm the README's NEW numbers/claims
   match reality (5.0 s `_STOP_JOIN_TIMEOUT_S`; `_stop_lock` single-flight; `_disarm`→
   `set_phase("idle")`; `__post_init__`→`TypeError`).
3. **New-phrase presence** — grep the edited README for the key new claims ("single-flight",
   "5 s", "idle" on disarm, "wrong type"/"TypeError" for config).
4. **Scope guard** — `git status` shows ONLY `README.md` modified.

Run all gates via `.venv/bin/python` / bash from the repo root (zsh aliases bare `python`).

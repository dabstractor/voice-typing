# Research Brief: README/docs verification for the three-fix changeset (P1.M4.T1.S1)

**Status:** VERIFIED against the live tree on 2026-07-18. All three fixes are LANDED (Issue 1
`_dispatch()` cross-mode routing, Issue 2 `_final_pending` reset in `_arm()`/`_disarm()`, Issue 3
`OutputConfig.__post_init__` at config.py:126/136). The README is **ACCURATE** on all three; the one
contract-invited touch-up (a wrong-*value* rejection sentence) is test-safe + low-risk. This is a
**DOCUMENTATION VERIFICATION** task: the deliverable is the verification + (recommended) one small
README touch-up; NO source/test files change.

---

## 0. THE VERDICT — README is accurate; one clarity touch-up recommended

The README faithfully reflects the post-fix behavior for all three issues. The contract's expected
outcome ("if the README is already accurate, make no changes") is ~95% met — the ONLY gap is that the
config-validation paragraph documents unknown-key + wrong-*type* rejection but not wrong-*value*
rejection, which is exactly the user-facing surface Issue 3 (and the pre-existing VT-005 `device`
check) add. The contract explicitly invites "noting that config values are validated at load time" as
an acceptable touch-up, so the recommended action is ONE verbatim sentence. The drift-guard test
(`test_config_repo_default.py`) is unaffected (it reads `config.toml`, not README) and passes (3/3).

---

## 1. The three verification points (vs the contract's LOGIC A/B/C)

### Point A — `output.backend` row consistency with the Issue 3 load-time validation
- **README line 175**: `` | `output.backend` | `"wtype"` | `"wtype"` (Wayland virtual keyboard), `"ydotool"` (uinput), or `"tmux"`. `wtype` auto-falls-back to `ydotool`. | ``
- **The 3 valid values match** `OutputConfig.__post_init__`'s `("wtype", "ydotool", "tmux")` set (config.py:126-136). ✅
- **"auto-falls-back to ydotool" is ACCURATE** — that fallback is the runtime `_WtypeWithFallback`
  wrapper in `typing_backends.py`, NOT a config behavior. The contract confirms: "the fallback is in
  _WtypeWithFallback, not config." ✅ (No misleading claim.)
- **Does the row mislead on a typo?** No — it lists the valid values; a typo like `wtyp` is clearly
  not among them. The row does NOT say "any string is accepted." So by the contract's threshold
  ("only if the current text would mislead"), no row edit is strictly required. The IMPROVEMENT is in
  the config-validation paragraph (Point C / §2 below), not the row itself.

### Point B — voicectl exit-code documentation consistency with toggle failures → exit 1
- **The README has NO explicit voicectl exit-code table.** Grep (`exit code|exits? (0|1|2|64)|exit
  [0-9]|0/1/2|sysexits|EX_USAGE`) returns nothing in README. (The contract's parenthetical "the README
  already documents exit codes 0/1/2/64 per PRD §4.8" is NOT borne out — there is no such section. The
  contract's "(if any)" covers this: nothing to verify for consistency → vacuously consistent.)
- **The Issue 1 fix makes toggle failures surface as `ok:false`** → `ctl.py:63`
  `return f"error: {response.get('error', 'unknown error')}", 1` → **exit 1**. Exit 1 for a command
  error is the documented-by-PRD-§4.8 behavior; since the README doesn't document exit codes, there is
  nothing to contradict. ✅ **No README change needed for exit codes.** (Record this finding so the
  implementer doesn't hunt for a non-existent exit-code section.)

### Point C — Issues 1 & 2 are internal; no `_final_pending`/drain/dispatch docs needed
- **The README correctly does NOT mention `_final_pending`, the dispatch-layer response shaping, or
  the drain internals.** Grep for `_final_pending|drain|dispatch|cross.mode` returns ONE hit — line
  130: *"Both modes share the graceful drain on stop"* — which is the **user-facing** §4.2 #2
  graceful-drain FEATURE description (a documented behavior), NOT the internal `_final_pending`
  mechanism Issue 2 fixed. ✅ No change needed (and none should be added — these are implementation
  details; the contract explicitly says "No mention of _final_pending, drain internals, or
  dispatch-layer response shaping needs to be added").

---

## 2. The recommended touch-up (ONE sentence; contract-invited; test-safe)

### Why
The config-validation paragraph (README ~lines 194-202, in `### Voice-activity constants are NOT
config keys`) currently documents TWO of the three fail-fast modes:
- **unknown key** → `TypeError` (the dataclass `__init__` rejects it)
- **wrong TYPE** → `TypeError` (e.g. `auto_stop_idle_seconds = "thirty"`, `device = 123`; the
  `AsrConfig.__post_init__` type checks)

It does NOT document the THIRD mode — **wrong VALUE** → `ValueError` — which is exactly what BOTH
`asr.device` (VT-005, `AsrConfig.__post_init__`) and now `output.backend` (Issue 3,
`OutputConfig.__post_init__`) enforce. Adding one sentence completes the fail-fast picture and
documents the Issue 3 fix's user-facing surface (a `backend = "wtyp"` typo now fails at load with a
clear `ValueError` instead of crash-looping under systemd). The contract explicitly invites this:
*"If a minor touch-up improves clarity (e.g., noting that config values are validated at load time),
apply it."*

### The verbatim edit (byte-exact oldText → newText)

`oldText` (the paragraph's tail — unique):
```
feature at runtime. Bare integers are accepted for numeric fields; a `true`/`false`
bool is not.
```
`newText` (append ONE sentence, wrapped to ~80 cols matching the README):
```
feature at runtime. Bare integers are accepted for numeric fields; a `true`/`false`
bool is not. A value outside a field's allowed set is rejected the same way — for
example `output.backend = "wtyp"` or `asr.device = "gpu"` raises `ValueError` at
load (the type is valid, the value is not), so a typo fails fast at startup instead
of crash-looping later.
```

### Why this wording
- **`ValueError` (not `TypeError`)** — the type IS valid (str); the value is not. Mirrors the code
  (`AsrConfig`/`OutputConfig.__post_init__` raise `ValueError` for bad enum values).
- **Names BOTH `output.backend` (Issue 3) AND `asr.device` (VT-005)** — completes the picture for
  both enum fields, not just the changeset's one.
- **"crash-looping later"** — references the systemd `Restart=on-failure` crash-loop that Issue 3's
  fix prevents (the exact failure mode the bug report described), reinforcing the *why*.
- **Mirrors the preceding "wrong type" sentence's structure** ("raises `X` at load ... rather than
  ... at runtime") for prose consistency.
- **~80-col soft-wrap** matches the README's manual wrap width.

### Test safety
- **No test reads README.** `grep -rnlE "README" tests/` returns only `tests/ACCEPTANCE.md` (a
  markdown doc, not a test asserting README content). So a README prose edit cannot break any test.
- **The drift-guard `test_config_repo_default.py`** reads `config.toml` ↔ dataclass defaults — NOT
  README — and the `OutputConfig` defaults are unchanged (backend still defaults to `"wtype"`).
  Verified: **3 passed in 0.01s** this round. A README edit leaves it green.

---

## 3. Scope boundaries (what this task is NOT)

- **README.md ONLY.** The touch-up is one prose sentence within an existing paragraph. No new files,
  no new headings (all `#anchor` links stay valid), no structural change.
- **NOT `voice_typing/config.py` / `daemon.py` / `ctl.py` / `typing_backends.py`** — the three fixes
  are LANDED; this task only verifies + documents. Do NOT "fix" code if a verification reveals a
  mismatch — raise it instead.
- **NOT `tests/`** — no test edits (the contract: "Mocking: None — this is a documentation
  verification task"). The drift-guard test is RUN, not edited.
- **NOT `tests/ACCEPTANCE.md`** — that is the acceptance-criteria doc, owned by a different concern
  (the round-006 P1.M5.T5 / P1.M6 acceptance work); not an "overview doc" for this changeset.
- **NOT `PRD.md` / `tasks.json` / `prd_snapshot.md` / `.gitignore` / `pyproject.toml` / `uv.lock`** —
  all forbidden or out of scope.
- **There is no separate `docs/` directory** (no `CONFIGURATION.md` etc.) — the README IS the config
  documentation (system_context.md §Documentation Surface confirms this).

---

## 4. The no-change fallback (if the reviewer prefers zero diff)

The README is accurate WITHOUT the touch-up (it lists the valid backend values; it doesn't mislead).
If the reviewer/orchestrator prefers a zero-diff documentation task, SKIP the edit and instead record
the verification finding in the commit message / PR description:
> "P1.M4.T1.S1: README verified consistent with the three-fix changeset (Issue 1 toggle→ok:false→exit1;
> Issue 2 _final_pending reset; Issue 3 OutputConfig backend validation). The output.backend row lists
> the 3 valid values; 'auto-falls-back' is accurate (runtime _WtypeWithFallback); Issues 1&2 are
> internal with no user-facing doc surface. The config-validation paragraph documents unknown-key +
> wrong-type rejection (TypeError); wrong-value rejection (ValueError, device+backend) is the only
> undocumented fail-fast mode — a one-sentence touch-up was [applied | deferred]."

Both paths are contract-valid. The PRP RECOMMENDS applying the touch-up (deterministic, low-regret,
documents the changeset) but the gate tolerates a zero-diff outcome.

---

## 5. Tooling + AGENTS.md compliance

- **Two timeouts per AGENTS.md Rule 1.** `test_config_repo_default.py` is pure-stdlib + sub-second,
  but STILL wrap: `timeout 60 .venv/bin/python -m pytest tests/test_config_repo_default.py -q` (inner
  GNU timeout) + set the bash-tool `timeout` param above it (outer harness backstop).
- **FULL PATHS** (zsh aliases `python`/`pytest` → `uv run`). Always `.venv/bin/python -m pytest`.
  mypy NOT installed (skip). ruff at `/home/dustin/.local/bin/ruff` is OPTIONAL (not in `.venv`; not
  a gate; the README is Markdown — ruff/mypy do not apply).
- The README uses **~76-82 col manual soft-wrap**; the touch-up sentence is wrapped to match.
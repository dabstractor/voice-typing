# Research Note — P1.M3.T2.S3: Audit `status.sh` tmux helper (PRD §4.6)

A focused, **read-only** audit of `voice_typing/status.sh` — the tmux status-right helper that jq-reads
the daemon's `state.json` and prints a one-line `🎤 <partial>` (or `⚡🎤 <partial>` in lite mode). This
note pre-maps every item check (a)-(e) to its `status.sh` file:line + verdict + pinning test, mirroring
how the S2 (`voicectl`) research note supported `gap_voicectl.md`. The auditor re-confirms live.

---

## §0 THE VERIFIED VERDICT

**`status.sh` is COMPLIANT** with PRD §4.6 on all 5 item checks (a)-(e) + Mode A (self-doc header) +
Mode B (README + install.sh snippet) — no code fix needed. The audit re-confirms this live and
documents it with evidence + the 2 non-defect nuances. If a check fails on re-read, document it as a
real gap for a SEPARATE remediation task (this audit does not fix code — consistent with S1 + S2 + every
round-006 audit).

**Live test run (this research):** `timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q`
→ **`5 passed in 0.03s`** (exit 0). Pure-stdlib subprocess test (runs the REAL script with a controlled
`XDG_RUNTIME_DIR`; no GPU/CUDA/daemon).

---

## §1 PER-CHECK EVIDENCE MAP (status.sh file:line → ✅ → pinning test)

All line numbers are `grep -n`-verified against the live tree this research (2026-07-18). The auditor
RE-VERIFIES them (they may have shifted) — record the ACTUAL numbers in the report, do not copy blind.

### (a) Reads `$XDG_RUNTIME_DIR/voice-typing/state.json`
- **status.sh:30:** `STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"`
- **Expected:** the script resolves `$XDG_RUNTIME_DIR/voice-typing/state.json`.
- **Actual:** ✅ — it uses the `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}` expansion, which resolves to
  `$XDG_RUNTIME_DIR` when set (the PRD path) AND falls back to `/run/user/$(id -u)` (the conventional
  XDG default) when unset. This is a **strictly more robust** resolution than the bare `$XDG_RUNTIME_DIR`
  — a non-defect superset (nuance §4.3, mirroring gap_typing.md's OSError-superset framing).
- **Pinning test:** `_run_status` (`tests/test_status_sh.py:26`) overrides `XDG_RUNTIME_DIR` →
  `tmp_path` and the script reads `<tmp_path>/voice-typing/state.json` (proven by every test that calls
  `_write_state` → the file is read). No dedicated path-resolution test, but the resolution is exercised
  by all 5 tests transitively.

### (b) jq filter: if `.listening` then `🎤 ` + partial else empty
- **status.sh:38-44:** the `jq -r` program:
  ```jq
  (if (.listening // false)
     then ((if (.mode == "lite") then "⚡" else "" end) + "🎤 " + (.partial // ""))
     else "" end) as $line
  ```
- **Expected:** listening → `🎤 <partial>`; not listening → `` (empty).
- **Actual:** ✅ — `.listening // false` (null-safe), `.partial // ""` (null-safe), the `else ""` branch
  yields empty when not listening. The `🎤 ` literal is the microphone emoji + space.
- **Pinning tests:** `test_status_sh_listening_renders_partial_and_exits_zero` (`:71`, asserts
  `out.startswith("🎤")` + `"hello world" in out`); `test_status_sh_not_listening_renders_empty_and_exits_zero`
  (`:102`, asserts `stdout.strip() == ""` for `{"listening": false, ...}`).

### (c) `cut -c1-60` truncation → 60 codepoints
- **status.sh:37 + 41-44:**
  ```sh
  MAX="${VOICE_TYPING_STATUS_MAX:-60}"        # :37
  ...
  | if ($line | length) > ($max | tonumber)    # :42
    then $line[:(($max | tonumber) - 1)] + "…"  # :43 — codepoint slice + ellipsis
    else $line end                              # :44
  ```
- **Expected (literal PRD inline snippet):** `| cut -c1-60`.
- **Actual:** ⚠️→✅ **The script does NOT use `cut -c1-60`.** It implements the truncation INSIDE jq via
  **codepoint-based slicing** to `MAX` (default **60**) + appends `"…"` on overflow. This is a
  **deliberate refinement** of the PRD's inline snippet, explicitly authorized by PRD §4.6's directive:
  *"Provide a small `voice_typing/status.sh` helper script instead of inline jq … — cleaner quoting."*
  The functional intent (cap a long line at ~60 chars) is preserved AND improved: codepoint-accurate
  (4-byte emoji count as 1), a visible `…` truncation marker, and an override hook
  (`VOICE_TYPING_STATUS_MAX`). This is the audit's **headline nuance — §4.1** (compliant-by-design; the
  helper refines the inline snippet per the PRD's own instruction). Verdict ✅.
- **Pinning test:** ⚠️ **NONE.** No test asserts the 60-codepoint bound (no test feeds a >60-char
  partial and asserts truncation + `…`). This is a coverage gap — nuance **§4.2** (non-defect; the
  truncation logic exists and the happy-path tests prove rendering works, but the bound itself is
  unpinned).

### (d) Lite mode `⚡` prefix when `mode == "lite"`
- **status.sh:40:** `(if (.mode == "lite") then "⚡" else "" end)` — prepended to the `🎤 ` line.
- **Expected (PRD §4.2ter):** "the tmux status line prefixes lite with `⚡`."
- **Actual:** ✅ — exactly that, prepended before the `🎤` so the rendered line is `⚡🎤 <partial>` in
  lite and `🎤 <partial>` in normal/missing-mode.
- **Pinning test:** `test_status_sh_lite_mode_prefixes_bolt` (`:87`): asserts `out.startswith("⚡🎤")`
  for `{"listening": true, "mode": "lite", ...}` AND `not out2.startswith("⚡")` for `mode:"normal"`
  (the negative guard).

### (e) Handles missing file gracefully (`2>/dev/null`)
- **status.sh:45 + 50:** `"$STATE" 2>/dev/null` (suppresses jq's stderr: file-missing=exit 2,
  corrupt-JSON=exit 5) + the trailing `exit 0` (zeroes the exit code so a non-tmux caller checking `$?`
  sees 0, not jq's failure code). The header comment documents this as the "exit 0 (never abort)"
  contract (Issue 2 fix).
- **Expected:** missing/corrupt state.json → empty stdout + exit 0 (never abort).
- **Actual:** ✅ — `2>/dev/null` + the jq `// ""` defaults (`.listening // false`, `.partial // ""`)
  guarantee empty-on-failure stdout; the explicit `exit 0` zeroes the exit code.
- **Pinning tests:** `test_status_sh_missing_state_file_exits_zero_with_empty_stdout` (`:51`, no file →
  exit 0 + empty stdout — the Issue 2 regression for jq's exit 2); `test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout`
  (`:61`, `not json{{}` → exit 0 + empty stdout — the Issue 2 regression for jq's exit 5).

### Mode A — self-documenting header comment (item DOCS: "status.sh is self-documenting")
- **status.sh:1-28:** the header comment block. Lines 8-23 are the "USER INTEGRATION" block — the exact
  two-line `tmux.conf` snippet (`set -g status-interval 1` + `set -g status-right "#(.../status.sh)"`),
  the expected result, and the `VOICE_TYPING_STATUS_MAX` override. This IS the doc the item contract
  refers to ("status.sh is self-documenting").
- **Verdict:** ✅.

### Mode B — README tmux section + install.sh snippet (PRD §4.6: "document in README, and install.sh prints the snippet")
- **README.md:135-150:** the "## tmux status line" section — the same two-line snippet
  (`README.md:141-142`: `set -g status-interval 1` + `set -g status-right "#(/home/<you>/.../status.sh)"`)
  + the result description + the `state.json` reference (`:150`). Also `README.md:63,69,111,132`
  reference the tmux status line / `⚡` lite prefix in context.
- **install.sh:213-214:** prints the snippet verbatim to stdout:
  ```sh
  echo '  set -g status-interval 1'
  echo "  set -g status-right \"#($REPO/voice_typing/status.sh)\""
  ```
  (the `tmux status (add these TWO lines ...)` header at `install.sh:212`).
- **Verdict:** ✅ — both the README and install.sh reference `status.sh` (not inline jq), exactly as
  PRD §4.6 mandates.

---

## §2 THE TRUNCATION NUANCE (§4.1 of the report) — the audit's headline finding

PRD §4.6's *inline* snippet truncates with `| cut -c1-60`. `status.sh` does NOT — it truncates INSIDE
jq to `MAX` (default 60) codepoints + appends `"…"` on overflow, overridable via
`VOICE_TYPING_STATUS_MAX`. **Why this is compliant, not a gap:**

1. **PRD §4.6 explicitly redirects to the helper:** *"Provide a small `voice_typing/status.sh` helper
   script instead of inline jq, and reference that — cleaner quoting."* The inline `cut -c1-60` snippet
   is the ALTERNATIVE the PRD is steering the implementer AWAY from.
2. **The functional intent is preserved AND improved:** a long line is capped at ~60 chars. The jq
   approach is strictly better on three axes:
   - **Codepoint-accurate:** jq string slicing is codepoint-based, so a 4-byte emoji (🎤/⚡/…) counts as
     1; `cut -c1-60` is locale/byte-dependent and can split a multibyte glyph mid-sequence.
   - **Visible truncation:** the `$line[:(($max - 1))] + "…"` drops the last char and appends `…`, so a
     cut line is visibly cut, not silently chopped.
   - **Override hook:** `MAX="${VOICE_TYPING_STATUS_MAX:-60}"` lets the user widen it (`tmux
     set-environment VOICE_TYPING_STATUS_MAX 80`) without editing the script.
3. **No literal "60" is lost:** the DEFAULT is still 60 (`:-60`), matching the PRD's `c1-60`.

**Verdict: ✅ compliant-by-design.** Record as nuance §4.1 — frame it precisely as "the helper refines
the inline `cut` per the PRD's own directive," NOT as "the script dropped the truncation." Do NOT
"restore" `cut -c1-60` — that would regress the codepoint-accuracy + ellipsis + override improvements.

---

## §3 THE NO-TRUNCATION-TEST NUANCE (§4.2 of the report) — a coverage gap, not a code gap

The 5-test suite pins (a) path resolution (transitively), (b) listening-render + idle-empty, (d) lite
bolt + normal-negative, (e) missing-file + corrupt-JSON exit-0. **No test pins the 60-codepoint
truncation bound or the `…` overflow marker** (check c). I.e. no test feeds `{"listening": true,
"partial": "<61+ chars>"}` and asserts the output is ≤60 chars + ends in `…`.

This is a **non-blocking coverage observation**, not a §4.6 violation: the truncation logic exists and
is correct-by-inspection (`status.sh:42-44`); the happy-path tests prove the render pipeline works.
Record it as nuance §4.2 so a future test-hardening pass COULD add a truncation test (out of scope for
this read-only audit — do NOT add a test here; consistent with every round-006 audit's "read-only, no
new tests" discipline).

---

## §4 SCOPE BOUNDARIES (do not cross)

This audit is the **`status.sh` tmux helper only**. It is NOT:
- **The state.json SCHEMA / atomic writes / throttling** — that is the `feedback.py` audit
  (P1.M3.T1.S1 → `gap_feedback.md`, already COMPLETE). `status.sh` is a CONSUMER of `state.json`; it
  does not WRITE it. The fields it reads (`listening`, `partial`, `mode`) are defined by §4.6 +
  audited in `gap_feedback.md`.
- **`voicectl` (ctl.py)** — that is S2 (P1.M3.T2.S2 → `gap_voicectl.md`). `status.sh` is the tmux-side
  reader; `voicectl` is the CLI control client. Disjoint.
- **The daemon-side control socket** — that is S1 (P1.M3.T2.S1 → `gap_socket.md`, COMPLETE).
- **The README/install.sh full audit** — those are P1.M6.T1.S1 (README completeness) / P1.M4.T3.S1
  (install.sh idempotency). This audit only CONFIRMS status.sh is referenced there (Mode B), per PRD
  §4.6's "document in README, and install.sh prints the snippet" — it does not audit the rest of those
  files.

The deliverable file is **`plan/006_862ee9d6ef41/architecture/gap_status_sh.md`** (NEW — CREATE, do not
append; NO prior status.sh gap report exists). Mirror `gap_typing.md`'s structure (the format template).
This file is **DISJOINT** from `gap_feedback.md` (S1 of P1.M3.T1), `gap_socket.md` (S1 of P1.M3.T2),
and `gap_voicectl.md` (S2 of P1.M3.T2) — four different filenames, no conflict.

---

## §5 TEST SUITE COVERAGE MAP (`tests/test_status_sh.py`, 109 lines, 5 tests)

| Test | Line | Check | What it asserts |
|---|---|---|---|
| `_run_status(tmp_path)` | `:26` | (a) [helper] | runs the REAL script with `XDG_RUNTIME_DIR` → `tmp_path` (full env carried so jq/id/sh stay on PATH); `timeout=10` |
| `_write_state(tmp_path, contents)` | `:43` | (a) [helper] | writes `<tmp_path>/voice-typing/state.json` |
| `test_status_sh_missing_state_file_exits_zero_with_empty_stdout` | `:51` | **(e)** | no file → exit 0 + empty stdout (Issue 2 regression: jq exit 2) |
| `test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout` | `:61` | **(e)** | `not json{{}` → exit 0 + empty stdout (Issue 2 regression: jq exit 5) |
| `test_status_sh_listening_renders_partial_and_exits_zero` | `:71` | **(b)** | `{"listening": true, "partial": "hello world"}` → starts `🎤` + contains `hello world` + exit 0 |
| `test_status_sh_lite_mode_prefixes_bolt` | `:87` | **(d)** | `mode:"lite"` → starts `⚡🎤`; `mode:"normal"` → NOT `⚡` (negative) |
| `test_status_sh_not_listening_renders_empty_and_exits_zero` | `:102` | **(b)** | `{"listening": false, ...}` → empty stdout + exit 0 (the idle case) |

**No test for check (c)** (the 60-codepoint truncation bound / `…` marker) — nuance §4.2.

The suite is **pure-stdlib** (`subprocess`/`os`/`pathlib`); it runs the REAL `voice_typing/status.sh`
with a controlled `XDG_RUNTIME_DIR` (no GPU/CUDA/daemon/mic). Runs in **0.03s**. The contract's run
command is `.venv/bin/python -m pytest tests/test_status_sh.py -q` (this research: **5 passed**).

---

## §6 EXIT-CODE / FAILURE-SEMANTICS DETAIL (for check e precision)

`status.sh` is deliberately written with **no `set -e`** (status.sh header, the "NO `set -e`" note).
The failure-handling chain for a missing/corrupt `state.json`:

| Failure | jq exit code | jq stdout | jq stderr | status.sh action | status.sh exit |
|---|---|---|---|---|---|
| file missing | 2 | `` (empty) | error msg | `2>/dev/null` swallows stderr; stdout already empty | **0** (`exit 0`) |
| corrupt JSON | 5 | `` (empty) | parse error | `2>/dev/null` swallows stderr | **0** (`exit 0`) |
| valid, listening | 0 | `🎤 <partial>` | — | passes through | **0** |
| valid, not listening | 0 | `` (empty) | — | passes through | **0** |

The trailing `exit 0` (status.sh:50) is the **Issue 2 fix**: without it, the script's exit code would be
jq's (2 or 5) on failure, violating the "exit 0 (never abort)" contract for any non-tmux caller that
checks `$?`. (tmux's `#(...)` substitution itself ignores the exit code — it only captures stdout — but
the contract honors all callers.) Both regressions are pinned (`:51` + `:61`).

---

## §7 TOOLING & GOTCHAS

- **Run via `.venv/bin/python -m pytest`** (zsh aliases bare `python` → `uv run`). The contract's run
  command is exactly `.venv/bin/python -m pytest tests/test_status_sh.py -q`.
- **mypy NOT installed** — skip it (status.sh is a shell script anyway; there is nothing to type-check).
- **ruff** at `/home/dustin/.local/bin/ruff` is OPTIONAL (not in `.venv`; not a gate; status.sh is a
  shell script, not Python — ruff does not apply).
- **Per AGENTS.md:** the test is pure-stdlib and sub-second, but still wrap in `timeout 120` (inner) +
  the bash-tool `timeout` (outer) — Rule 1 (two timeouts on every non-trivial command). This research
  did exactly that: `timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q`.
- **DO NOT run the daemon** or any `voicectl` command for this audit — `status.sh` is read directly off
  `state.json`; no daemon needed. The test suite synthesizes `state.json` in a `tmp_path`.
- **shellcheck** is not in the project's gate; status.sh is POSIX `sh` + `jq` only. Do not introduce a
  shellcheck gate (out of scope; would be a separate tooling decision).
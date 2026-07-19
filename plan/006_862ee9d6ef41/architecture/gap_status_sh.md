# Gap Report — P1.M3.T2.S3: status.sh tmux helper (§4.6)

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/status.sh` — the tmux status-right helper (PRD §4.6) — against the 5 item
checks (a)-(e) + Mode A (the self-documenting header comment) + Mode B (README + install.sh reference
`status.sh`): (a) reads `$XDG_RUNTIME_DIR/voice-typing/state.json`; (b) jq filter: `if .listening then
🎤 + partial else empty`; (c) truncation to 60 chars (PRD §4.6 inline snippet says `cut -c1-60`); (d)
lite mode `⚡` prefix when `mode=="lite"` (§4.2ter); (e) handles missing/corrupt file gracefully
(`2>/dev/null` + exit 0) — and re-run the pure-Python unit suite (`tests/test_status_sh.py`). Subtask
**P1.M3.T2.S3** of verification round `006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/status.sh` — `STATE` path resolution (`:30`), `MAX` override (`:37`), the `jq -r`
  render program (`:38`-`:44`: `.listening // false` gate `:39`; `.mode == "lite"` → `⚡` prefix
  `:40`; `🎤 ` literal + `.partial // ""` `:40`; truncation if/else `:42`-`:44`), `2>/dev/null`
  (`:45`), trailing `exit 0` (`:50`, the Issue 2 fix), self-documenting header block (`:1`-`:28`).
- `tests/test_status_sh.py` — the 5-test suite (the contract's run command); pure-stdlib subprocess
  (runs the REAL script with a controlled `XDG_RUNTIME_DIR`; no GPU/CUDA/daemon/mic).
- `README.md` — §"tmux status line" (`:135`-`:150`): the two-line snippet (`:141`-`:142`) + the
  result description + the state.json reference.
- `install.sh` — prints the snippet verbatim (`:212`-`:214`).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.6 (state file + the tmux status integration
  block incl. the "Provide a small `status.sh` helper … cleaner quoting" directive) + §4.2ter (the `⚡`
  lite prefix).

**Bottom line:** ✅ `status.sh` is **COMPLIANT** with PRD §4.6 / §4.2ter — all 5 checks (a)-(e) + Mode A
self-doc + Mode B README/install.sh references hold, each mapped to a `status.sh`/`README.md`/
`install.sh` file:line and a pinning test, and the suite is green (**5 passed in 0.03s**, re-run live).
**No source files were modified** — the helper faithfully implements the spec, INCLUDING the deliberate
jq-internal truncation that refines the PRD's inline `cut -c1-60` snippet per §4.6's own "cleaner
quoting" directive. The three non-blocking observations (the jq-truncation refinement; the absent
truncation-bound test; the XDG-fallback resolution superset) are recorded in §4 so they are not
mistaken for defects.

---

## 1. Method

Each of the 5 item checks (a)-(e) + Mode A/B was mapped 1:1 to its `status.sh`/`README.md`/`install.sh`
implementation by `grep -n` (the file:line evidence), and the truncation approach + the failure-handling
chain were read directly. The full `tests/test_status_sh.py` suite was then **re-run live** to record
the actual pass count and timing. Nothing was assumed from the PRP's embedded numbers — every line
number + the pass count below was re-verified this round (the suite is pure-stdlib `subprocess`/`os`/
`pathlib`; it runs the REAL `voice_typing/status.sh` under a controlled `XDG_RUNTIME_DIR` — no GPU/
CUDA/daemon/mic required).

### Commands run (re-verification)

```bash
# (a-e + Mode A) Line-number map (grep -n)
grep -nE 'STATE=|VOICE_TYPING_STATUS_MAX|MAX=' voice_typing/status.sh
grep -nE 'if \(\.listening|mode == "lite"|\.partial|⚡|🎤' voice_typing/status.sh
grep -nE '2>/dev/null|exit 0' voice_typing/status.sh
# (c) the headline nuance check — there is NO cut -c1-60 in status.sh (truncation is jq-internal):
grep -nE 'cut -c1-60' voice_typing/status.sh || echo "CLEAN: no cut -c1-60 (truncation is jq-internal — §4.1)"
# Mode B references:
grep -nE 'status\.sh|status-right|status-interval|tmux status line' README.md install.sh
# the pinning tests:
grep -nE '^def test_' tests/test_status_sh.py
# the unit suite (the contract's run command), LIVE (two timeouts per AGENTS.md Rule 1)
timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q
```

### Observed output (abridged — re-verified live this round)

```
(a) 30:STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"   (XDG-fallback superset, §4.3)
(b) 39:  (if (.listening // false)   40:     then ((if (.mode == "lite") then "⚡" else "" end) + "🎤 " + (.partial // ""))
(c) 37:MAX="${VOICE_TYPING_STATUS_MAX:-60}"  42:  | if ($line | length) > ($max | tonumber)
                                                  43:    then $line[:(($max | tonumber) - 1)] + "…"
                                                  44:    else $line end
    (c-clean) grep 'cut -c1-60' status.sh → CLEAN (truncation is jq-internal, §4.1)
(d) 40:     then ((if (.mode == "lite") then "⚡" else "" end) + ...)
(e) 45:' "$STATE" 2>/dev/null   50:exit 0
(Mode A) 1-28: header self-doc block (USER INTEGRATION 8-23: the 2-line tmux.conf snippet + MAX override note)
(Mode B) README.md:135-150 §"tmux status line" (141-142 snippet; 150 state.json ref)  install.sh:212-214 snippet
.....                                                                                          [100%]
5 passed in 0.03s
```

---

## 2. Per-check Compliance Table (PRD §4.6 / §4.2ter vs `status.sh`)

| # | PRD requirement | Expected (spec) | `status.sh` / `README.md` / `install.sh` actual | file:line | Pinning tests (`tests/test_status_sh.py`) | Verdict |
|---|---|---|---|---|---|---|
| **(a)** | reads `$XDG_RUNTIME_DIR/voice-typing/state.json` | `STATE` resolves the XDG runtime path | `STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"` — resolves to `$XDG_RUNTIME_DIR` when set (the PRD path) AND falls back to `/run/user/$(id -u)` when unset (the conventional default — a strictly-more-robust superset, §4.3) | `status.sh:30` | `_run_status` (`:26`) sets `XDG_RUNTIME_DIR`→`tmp_path`; every test's `_write_state` proves the script reads `<tmp>/voice-typing/state.json` (resolution exercised transitively by all 5 tests) | ✅ |
| **(b)** | jq filter: `if .listening then 🎤 + partial else empty` | listening → `🎤 <partial>`; not listening → `` (empty) | `jq -r` program: `(if (.listening // false) then (… + "🎤 " + (.partial // "")) else "" end) as $line` — null-safe `.listening // false` + `.partial // ""`, `🎤 ` literal, `else ""` empty branch | render program `status.sh:38`-`:44`; gate `:39`; emoji+partial `:40` | `test_status_sh_listening_renders_partial_and_exits_zero` (`:71`, `🎤` prefix + `hello world`); `test_status_sh_not_listening_renders_empty_and_exits_zero` (`:102`, idle → empty stdout) | ✅ |
| **(c)** | truncate to 60 chars (PRD §4.6 inline snippet: `cut -c1-60`) | a long line capped at ~60 chars | **NO `cut -c1-60`** — truncation is jq-INTERNAL: `MAX="${VOICE_TYPING_STATUS_MAX:-60}"`; `if ($line\|length) > ($max\|tonumber) then $line[:($max-1)] + "…" else $line end` → codepoint slice to 60 + `…` overflow marker, overridable. Compliant-by-design: PRD §4.6 redirects to the helper ("cleaner quoting"); the 60-char intent is preserved AND improved (codepoint-accurate emoji, visible `…`, override hook). See §4.1 | `MAX` `status.sh:37`; truncation if/else `:42`-`:44` | (none — coverage gap, §4.2; not a code gap) | ✅ |
| **(d)** | lite mode `⚡` prefix when `mode=="lite"` (§4.2ter) | the status line prefixes lite with `⚡` | `(if (.mode == "lite") then "⚡" else "" end)` prepended before `🎤 ` → `⚡🎤 <partial>` in lite, `🎤 <partial>` in normal/missing | `status.sh:40` | `test_status_sh_lite_mode_prefixes_bolt` (`:87`, `⚡🎤` prefix in lite + NOT `⚡` in normal — negative guard) | ✅ |
| **(e)** | handles missing/corrupt file gracefully (`2>/dev/null`) | missing/corrupt state.json → empty stdout + exit 0 (never abort) | `2>/dev/null` swallows jq's stderr (exit 2=missing, 5=corrupt); jq `// ""` defaults keep stdout empty; the trailing `exit 0` zeroes the exit code (Issue 2 fix) honoring the "exit 0 (never abort)" contract for non-tmux callers that check `$?` | `status.sh:45` (`2>/dev/null`) + `:50` (`exit 0`) | `test_status_sh_missing_state_file_exits_zero_with_empty_stdout` (`:51`, no file → exit 0+empty — jq exit 2 regression); `test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout` (`:61`, `not json{{}` → exit 0+empty — jq exit 5 regression) | ✅ |
| **Mode A** | `status.sh` is self-documenting (item DOCS) | the header comment IS the tmux doc | the `# USER INTEGRATION #` block documents the 2-line `tmux.conf` snippet (`status-interval 1` + `status-right "#(.../status.sh)"`), the expected result, and the `VOICE_TYPING_STATUS_MAX` override | `status.sh:1`-`:28` (snippet block `:8`-`:23`) | (n/a — documentation; corroborated by reading the header) | ✅ |
| **Mode B** | README documents it + install.sh prints the snippet (PRD §4.6) | both reference `status.sh` (NOT inline jq) | README §"tmux status line" has the 2-line snippet; install.sh `echo`s the snippet verbatim with `$REPO/voice_typing/status.sh` | README.md `:135`-`:150` (snippet `:141`-`:142`); install.sh `:212`-`:214` (snippet `:213`-`:214`) | (n/a — documentation; corroborated by grep) | ✅ |

> All checks **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this
> round. The `(c)`-clean grep (no `cut -c1-60`) confirms the headline nuance: truncation is jq-internal,
> not a dropped feature (§4.1).

---

## 3. Test results (the contract's run command, LIVE)

```
$ timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q
.....                                                                    [100%]
5 passed in 0.03s
exit: 0
```

The suite (109 lines, 5 tests) is pure-stdlib `subprocess`/`os`/`pathlib`: it runs the REAL
`voice_typing/status.sh` under a controlled `XDG_RUNTIME_DIR` (full env carried so `jq`/`id`/`sh` stay
on PATH) with a synthesized `state.json` — no GPU/CUDA/daemon/mic. Coverage by check: (e) missing-file
(`:51`) + corrupt-JSON (`:61`) exit-0 regressions; (b) listening-render (`:71`) + idle-empty
(`:102`); (d) lite-bolt + normal-negative (`:87`); (a) path resolution exercised transitively by
all 5. **No test for check (c)** (the 60-codepoint truncation bound / `…` marker) — §4.2.

---

## 4. Non-defect nuances (so they are not mistaken for gaps)

### 4.1 (c) Truncation is jq-INTERNAL (codepoint slice + `…`), NOT `cut -c1-60` — compliant-by-design
PRD §4.6's *inline* snippet truncates with `| cut -c1-60`. `status.sh` does NOT — it truncates INSIDE jq:
`MAX="${VOICE_TYPING_STATUS_MAX:-60}"` (`:37`); `if ($line | length) > ($max | tonumber) then
$line[:($max - 1)] + "…" else $line end` (`:42`-`:44`). **Why this is compliant, not a gap:**

1. **PRD §4.6 explicitly redirects to the helper:** the SAME sentence says *"Provide a small
   `voice_typing/status.sh` helper script instead of inline jq, and reference that — cleaner quoting."*
   The inline `cut -c1-60` snippet is the ALTERNATIVE the PRD steers the implementer AWAY from.
2. **The functional intent is preserved AND improved on three axes:**
   - **Codepoint-accurate:** jq string slicing is codepoint-based, so a 4-byte emoji (🎤/⚡/…) counts as
     1; `cut -c1-60` is locale/byte-dependent and can split a multibyte glyph mid-sequence.
   - **Visible truncation:** `$line[:($max - 1)] + "…"` drops the last char and appends `…`, so a cut
     line is visibly cut, not silently chopped.
   - **Override hook:** `VOICE_TYPING_STATUS_MAX` lets the user widen it (`tmux set-environment
     VOICE_TYPING_STATUS_MAX 80`) without editing the script.
3. **No literal "60" is lost:** the DEFAULT is still 60 (`:-60`), matching the PRD's `c1-60`.

> **Do NOT "restore" `cut -c1-60`.** That would regress the codepoint-accuracy + ellipsis + override
> improvements. ✅

### 4.2 (c) No test pins the 60-codepoint truncation bound — a coverage gap, not a code gap
The 5-test suite pins (a) transitively, (b), (d), (e) — but NO test feeds a >60-char partial and asserts
the output is ≤60 codepoints + ends in `…` (check c). This is a **non-blocking coverage observation**,
not a §4.6 violation: the truncation logic exists (`:42`-`:44`) and is correct-by-inspection; the
happy-path tests prove the render pipeline works. A future test-hardening pass COULD add a truncation
test (out of scope for this read-only audit — do NOT add one here; consistent with every round-006
audit's "read-only, no new tests" discipline). ✅

### 4.3 (a) The `XDG_RUNTIME_DIR:-/run/user/$(id -u)` resolution is a TESTED SUPERSET — compliant
PRD §4.6 names the path `$XDG_RUNTIME_DIR/voice-typing/state.json`. `status.sh` uses
`${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json` (`:30`): it resolves to
`$XDG_RUNTIME_DIR` when set (the PRD path) AND falls back to `/run/user/$(id -u)` (the conventional XDG
default) when unset. This is **strictly more robust** than the bare `$XDG_RUNTIME_DIR` — a host where
XDG_RUNTIME_DIR is somehow unset (rare but possible) still resolves correctly. Intentionally more robust
than the contract's literal wording; exercised transitively by all 5 tests (`_run_status` sets
`XDG_RUNTIME_DIR`→`tmp_path`). Mirrors the "compliant-by-design superset" framing in `gap_typing.md`
§4.1 (the `(CalledProcessError, OSError)` fallback superset). ✅

---

## 5. Conclusion

**PASS.** `voice_typing/status.sh` is compliant with PRD §4.6 / §4.2ter on all 5 item checks (a)-(e) +
Mode A self-doc + Mode B README/install.sh references. The helper resolves the state.json path with a
robust XDG fallback (`:30`), renders `🎤 <partial>` while listening and `` when idle (`:38`-`:44`),
prefixes `⚡` in lite mode (`:40`), truncates long lines to 60 codepoints with a visible `…` marker
INSIDE jq (an improvement on the PRD's inline `cut -c1-60`, explicitly authorized by §4.6's "cleaner
quoting" directive — `:37`/`:42`-`:44`), and survives a missing/corrupt state.json with empty
stdout + exit 0 (`2>/dev/null` `:45` + `exit 0` `:50`, the Issue 2 fix). README (`:135`-`:150`)
+ install.sh (`:212`-`:214`) both reference `status.sh` (not inline jq). The 5-test suite pins every
check except the truncation bound (a coverage gap, §4.2). **No source files were modified** (read-only
audit); the sole artifact is this report.

Scope is the `status.sh` tmux helper only — the state.json schema/atomic writes are P1.M3.T1.S1
(`gap_feedback.md`, COMPLETE), `voicectl` is P1.M3.T2.S2 (`gap_voicectl.md`), the daemon control socket
is P1.M3.T2.S1 (`gap_socket.md`, COMPLETE), and a full README/install.sh audit is P1.M6.T1.S1 /
P1.M4.T3.S1.
# Research — P1.M4.T1.S2: Update tests/ACCEPTANCE.md teardown criteria + SIGTERM-path test coverage note

**Task type:** documentation-only — two edits to ONE existing file (`tests/ACCEPTANCE.md`, 146 lines).
No code, no tests, no new files. This is the ACCEPTANCE.md half of the bugfix documentation sync
(sibling P1.M4.T1.S1 owns `README.md`; this task owns `tests/ACCEPTANCE.md`). All facts below are
verified against the LANDED code + the LANDED tests (file:line).

---

## 1. The target file + exact edit anchors

`tests/ACCEPTANCE.md` structure (146 lines):
- L1–9: header + "How to reproduce the 5/6/8 evidence"
- L26–37: **Criteria** table (criterion 1–8 rows)
- L39–106: **Evidence block** (verbatim `test_idle_and_gpu.sh` output)
- L108–146: **Notes on the method** (4 bullets: T4 CPU sampling; T6 GPU residency; Criterion 8;
  Cleanup) ← **the edits live here**

### Edit 1 anchor — the teardown-budget fragment (L130, in the **T6 GPU residency** bullet)
The T6 bullet explains the T6(d-gone) poll ceiling. It currently budgets the teardown at **≤10 s**
(the pre-`P1.M1.T2.S2` default). Exact current text (L129-130):
```
  transition is **polled** (every 0.5 s up to a ~25 s ceiling), not a fixed `sleep 7` — the contract's
  literal "7 s" under-budgets the 1 s watchdog tick + 5 s threshold + ≤10 s bounded teardown + driver
```
The fragment `≤10 s bounded teardown` is the **only** stale teardown budget in the file. It must become
the post-fix `≤5 s` + **single-flight** wording (item clause (a)).

### Edit 2 anchor — append a new bullet at the END of "Notes on the method"
The section's last bullet is **Cleanup** (L142-146), ending with:
```
  Ctrl-C (`SIGINT`). The default audio source is never touched (this test listens to ambient room
  silence on the real mic).
```
`silence on the real mic).` is the file's final line (L146; no trailing content). The new
**Regression-test coverage** bullet is appended AFTER it (item clauses (b)+(c)).

**No other teardown/`≤10 s`/SIGTERM references exist in the file** (verified: `grep -nE "≤10|SIGTERM|voicectl quit|single-flight" tests/ACCEPTANCE.md` returns only L130 for the budget; the SIGTERM-path coverage is currently UNDOCUMENTED — exactly the gap to fill).

---

## 2. Verified post-fix code facts (what the new prose must match)

Every number/claim in the edits cites a LANDED, file:line-verified fact (do NOT invent):

| Fact | Location | Value |
|---|---|---|
| Per-call host.stop() join budget | `voice_typing/recorder_host.py:87` | `_STOP_JOIN_TIMEOUT_S: float = 5.0` (was effectively 10) |
| `RecorderHost.stop()` default timeout | `voice_typing/recorder_host.py:255` | `def stop(self, timeout: float = _STOP_JOIN_TIMEOUT_S)` |
| Single-flight lock (concurrent stop shares ONE teardown) | `voice_typing/recorder_host.py:140` (`self._stop_lock = threading.Lock()`) + `:265` (body under lock) | `_stop_lock` |
| Daemon per-call bounded teardown default | `voice_typing/daemon.py:1338` | `def _bounded_shutdown(self, timeout: float = 5.0)` (was 10.0 — P1.M1.T2.S2) |
| Daemon single-flight wait budget | `voice_typing/daemon.py:342` | `_TEARDOWN_WAIT_TIMEOUT = 8.0` |
| Disarm → phase idle (Issue 2) | `voice_typing/daemon.py:918` | `self._feedback.set_phase("idle")` (in `_disarm()`) |
| systemd stop timeout | `systemd/voice-typing.service:52` | `TimeoutStopSec=15` |

**Budget math (consistent with sibling S1's README claim):** host.stop(timeout=5) → proc.join(5) +
killpg + join(2) ≈ ≤7 s per call; with daemon single-flight EXACTLY ONE teardown runs on the SIGTERM
path → + ControlServer.stop() join(2) ≈ ≤9 s total, comfortably under `TimeoutStopSec=15`.

---

## 3. Verified LANDED regression-test coverage (what the new bullet documents)

This is the load-bearing section — the bullet MUST only name tests that ACTUALLY EXIST (verified via
`grep -nE "def test_..."` on the live test files). All present:

### Issue 1 — SIGTERM/systemctl-stop teardown (the previously-UNTESTED path)
- **`test_concurrent_request_shutdown_and_shutdown_only_one_stop`** — `tests/test_daemon.py:1029`.
  The end-to-end SIGTERM-path test (P1.M1.T2.S3): drives `request_shutdown()` (signal-handler thread)
  AND `shutdown()` (main-thread `finally`) **concurrently** against a live armed (lazy-spawned fake
  host) daemon; asserts exactly ONE `host.stop()` runs (`stop_calls == 1`) + bounded wall time (< 8 s)
  + clean run()-thread exit. **This is the test that did not exist before — only `voicectl quit` was
  covered, which is precisely why Issue 1 slipped through.**
- Supporting unit tests (P1.M1.T2.S1, same file): `test_request_shutdown_claims_and_signals_teardown_done`
  (1647), `test_shutdown_does_own_teardown_when_called_first` (1658),
  `test_shutdown_waits_for_inflight_teardown_no_second_stop` (1669),
  `test_shutdown_returns_immediately_when_teardown_already_done` (1702),
  `test_shutdown_falls_back_to_own_teardown_on_wait_timeout` (1724),
  `test_install_registers_handler_for_sigterm_and_sigint` (1758).
- RecorderHost-level single-flight (P1.M1.T1.S2): **`test_concurrent_stop_calls_share_one_teardown`**
  — `tests/test_recorder_host.py:232`.

### Issue 2 — phase stuck `listening`/`speaking` after disarm
- **`test_disarm_resets_phase_to_idle`** — `tests/test_daemon.py:3021`
- **`test_toggle_off_resets_phase_to_idle`** — `:3032`
- **`test_auto_stop_resets_phase_to_idle`** — `:3043`

### Issue 3 — silent child-crash leaving `listening: on`
- **`test_run_loop_detects_dead_host_and_transitions_to_unloaded`** — `tests/test_daemon.py:3076`
- **`test_load_host_respawns_after_dead_child`** — `:3116`
- **`test_status_reports_unloaded_after_child_death`** — `:3155`

---

## 4. Scope boundary — do NOT collide with sibling P1.M4.T1.S1 (README.md)

- **This task edits `tests/ACCEPTANCE.md` ONLY.**
- **Sibling P1.M4.T1.S1 edits `README.md` ONLY** (its PRP's Critical #1 + scope guard L3 enforce
  `tests/ACCEPTANCE.md` untouched). The two doc tasks are on disjoint files → no merge conflict.
- FORBIDDEN (per the orchestrator's hard rules): `PRD.md`, `**/tasks.json`, `**/prd_snapshot.md`,
  `.gitignore`, any `voice_typing/*.py` (fixes are LANDED — this task only documents them),
  `config.toml`, `pyproject.toml`, `uv.lock`, `README.md` (S1's file).

---

## 5. Markdown style conventions (preserve exactly)

- The "Notes on the method" bullets each start with a **bold lead term** (`- **T4 CPU sampling** …`,
  `- **Criterion 8** …`). The new bullet follows the same form: `- **Regression-test coverage (bugfix
  Issues 1–3).** …`.
- Continuation lines are indented **2 spaces** (the bullet's hanging indent), hand-wrapped at ~76 cols
  (NOT a single reflowed line). New prose wraps the same way.
- Inline code uses single backticks (`` `test_concurrent_request_shutdown_and_shutdown_only_one_stop` ``);
  em dashes (`—`) and `≤`/`≥` glyphs are used as in the rest of the file.
- **Do NOT add/change any heading** (`#`/`##`/`###`); edits are prose WITHIN the existing Notes section.
- **Do NOT touch the Criteria table or the Evidence block** — only the Notes section's T6 bullet (Edit 1)
  + a new appended bullet (Edit 2).

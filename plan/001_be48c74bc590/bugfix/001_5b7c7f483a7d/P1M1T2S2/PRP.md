# PRP — P1.M1.T2.S2: Surface mic health in status_snapshot() and voicectl status output

## Goal

**Feature Goal**: Surface the mic-health signal that P1.M1.T2.S1 detects (`self._mic_ok`, `self._mic_error`) in the two user/programmer-visible status surfaces, so a dead/missing mic is no longer silent. Concretely: (a) add `"mic_ok"` and `"mic_error"` keys to `VoiceTypingDaemon.status_snapshot()` — which automatically propagate into every control-socket JSON response via the existing `**status_snapshot()` spread in `_dispatch()`; (b) render a `mic:` line in `voicectl status`'s human-readable output (`format_result()`). This is the **surfacing** half of bugfix Issue 2; S1 is the detection half, S3 is the rate-limit half.

**Deliverable** (4 files edited, no new files):
1. `voice_typing/daemon.py` — `status_snapshot()`: +2 keys (`mic_ok`, `mic_error`) + docstring update.
2. `voice_typing/ctl.py` — `format_result()` status branch: +`mic:` line + docstring update.
3. `tests/test_daemon.py` — update the exact-set status test (8→10 keys) + 1 new surfacing test.
4. `tests/test_voicectl.py` — update the `_STATUS_ON` fixture + 2 new format_result mic tests.
5. `README.md` — troubleshooting "Wrong microphone" subsection + the "Logs, status, stopping" example.

**Success Definition**:
- (a) `status_snapshot()` returns a dict whose key set is exactly `{listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model, mic_ok, mic_error}`; `mic_ok` is `self._mic_ok` (bool) and `mic_error` is `self._mic_error or ""` (always a string).
- (b) `_dispatch()` is **unchanged** — the new keys appear in toggle/start/stop/status JSON automatically via `**status_snapshot()` (verify, don't edit).
- (c) `voicectl status` prints a final `mic: ok` line when `mic_ok` is True, and `mic: unavailable (<error>)` when False. toggle/start/stop output is **unchanged** (still the terse `listening: on/off` one-liner).
- (d) `format_result()` uses `.get("mic_ok", True)` / `.get("mic_error", "")` so a response missing the keys never raises and never shows a spurious error (matches the file's existing defensive `.get` convention).
- (e) The README "Wrong microphone" subsection tells the user to check `voicectl status`'s `mic:` line first; the status example block shows `mic: ok`.
- (f) All existing tests stay green; the only updated assertion is the exact-set test (8→10 keys). No real mic, no CUDA, no systemd in the gates.
- (g) No out-of-scope work: no `_dispatch()`/`feedback.py`/`status.sh`/`config.py`/systemd changes; no rate-limiting (S3); no probe/detection logic (S1).

## User Persona

**Target User**: the end user running `voicectl status` (and scripts parsing the control-socket JSON) on a 24/7 systemd deployment.
**Use Case**: the user arms the mic, speaks, gets nothing typed. Today they must dig into `journalctl` to discover the mic disconnected. After S2, `voicectl status` immediately shows `mic: unavailable (<reason>)`.
**Pain Points Addressed**: bugfix Issue 2 — "voicectl status reports a healthy `device: cuda`, and voicectl start returns `listening: on` (exit 0) with no hint that capture is broken. The user would arm, speak, get nothing, and have to dig into journalctl." S2 makes the failure user-visible in the primary status surface.

## Why

- **Bugfix Issue 2 (Major)** is the source. Its prescribed fix (a): "Detect mic/PyAudio open failure ... and reflect it in `status_snapshot()` (e.g. add a `mic_ok`/`error` field so `voicectl status` ... show the problem)." S1 added the detection (`self._mic_ok`/`self._mic_error`, refreshed in `__init__`/`_arm`). S2 is the reflect-in-status half — without it, the detected signal is invisible to the user and to scripts.
- **The JSON spread is free.** `_dispatch()` already does `{"ok": True, **self._daemon.status_snapshot()}` for toggle/start/stop/status. Adding the keys to `status_snapshot()` means scripts parsing JSON get `mic_ok`/`mic_error` on every command automatically — the contract's "The JSON control-socket response includes mic_ok and mic_error fields" is satisfied by editing ONE method.
- **`voicectl status` is the right human surface.** The bug explicitly calls it out, and the contract OUTPUT line names it ("voicectl status now shows mic health"). toggle/start/stop stay terse one-liners (with exact-equality unit tests) so the mic line is status-only; the JSON still carries the fields on all commands for programmatic checks.
- **PRD alignment.** PRD §4.4 spirit ("daemon MUST log clearly … and say so in status"), §8 risk row "PyAudio picks wrong device", §6 T5 ("First run" expects clear behavior). S2 makes "say so in status" literally true.

## What

- `daemon.py status_snapshot()`: append `"mic_ok": self._mic_ok,` and `"mic_error": self._mic_error or "",` to the returned dict; update the docstring field list.
- `ctl.py format_result()`: in the `if cmd == "status":` branch, compute a `mic_line` from `.get("mic_ok", True)` / `.get("mic_error", "")` and append it as the last line; update the docstring.
- `tests/test_daemon.py`: update `test_status_snapshot_keys_and_cuda_values` expected set to 10 keys + assert the mic values; add `test_status_snapshot_reflects_mic_health` (sets `d._mic_ok`/`d._mic_error` directly, asserts snapshot carries them — decoupled from S1's probe).
- `tests/test_voicectl.py`: add `mic_ok`/`mic_error` to the `_STATUS_ON` fixture; add a status+mic-failure test and a status+mic-ok test.
- `README.md`: "Wrong microphone" subsection — note `voicectl status` shows a `mic:` line; "Logs, status, stopping" example — add `mic: ok` to the CUDA output block.

### Success Criteria

- [ ] `status_snapshot()` key set is exactly the 10 keys above; `mic_ok` is `self._mic_ok`; `mic_error` is `self._mic_error or ""`.
- [ ] `_dispatch()` byte-unchanged (the spread carries the new keys; verify with git diff).
- [ ] `format_result("status", resp)` returns text ending in `mic: ok` when `resp["mic_ok"]` is True; ending in `mic: unavailable (<mic_error>)` when False (and `mic: unavailable` if False with empty error).
- [ ] `format_result("toggle"/"start"/"stop", resp)` is byte-identical to before (terse `listening: …`).
- [ ] `format_result` uses `.get("mic_ok", True)` / `.get("mic_error", "")` (a response missing the keys → healthy, no raise).
- [ ] All existing ctl/daemon tests green; the status exact-set test updated to 10 keys; 3 new tests added (1 daemon surfacing + 2 ctl format).
- [ ] README "Wrong microphone" mentions the `voicectl status` `mic:` line; status example shows `mic: ok`.
- [ ] No edits to `_dispatch()`, `feedback.py`, `status.sh`, `config.py`, `launch_daemon.sh`, `systemd/`, `cuda_check.py`, `pyproject.toml`, `PRD.md`, `tasks.json`.

## All Needed Context

### Context Completeness Check

_Pass._ Every edit site has been read in the live repo with exact line numbers (status_snapshot ~538, format_result 42-73, the exact-set test at 762, the _STATUS_ON fixture at 24, the README subsections at 187 and 226). The S1 dependency (`self._mic_ok`/`self._mic_error`) is treated as a landed contract. A developer new to this codebase can apply the patch from this PRP + the research note alone.

### Documentation & References

```yaml
# MUST READ — the defect definition + prescribed fix (authoritative)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2 Issue 2 (Major) is the source. Prescribed fix (a): 'reflect it in status_snapshot() (e.g.
        add a mic_ok/error field so voicectl status ... show the problem)'. S2 IS that reflect-in-status
        half. Verified live behavior: 2822+ retry errors, voicectl status showed healthy device:cuda,
        voicectl start returned listening:on with no hint."
  critical: "The fix's mechanism is status_snapshot + voicectl status display. S2 does NOT fix the
            retry-loop spam (that's S3) and does NOT add detection (that's S1, already landing)."

# MUST READ — the S1 INPUT contract (what self._mic_ok / self._mic_error are)
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T2S1/PRP.md
  why: "S1 creates self._mic_ok (bool, default True) + self._mic_error (str|None, default None),
        refreshed in __init__ and _arm via _refresh_mic_status(). S1 LEAVES status_snapshot at 8 keys
        on purpose ('S2 owns adding mic_ok/mic_error'). S2 reads those attributes directly."
  critical: "S2 ASSUMES S1 has landed (the attributes exist on every instance). If status_snapshot
            raises AttributeError on self._mic_ok, S1 hasn't landed — see Known Gotcha #1. mic_error is
            None when healthy → S2 must coerce to '' for JSON (self._mic_error or '')."

# MUST READ — verified edit sites, line numbers, test impacts, design decisions
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T2S2/research/codebase_edit_sites_and_test_impact.md
  why: "The full codebase analysis: status_snapshot() current source (~538), the automatic _dispatch
        spread (~790, no edit needed), format_result() source (42-73), the exact-set test (762), the
        _STATUS_ON fixture (24), which tests stay green vs need updating, the parallel-conflict analysis,
        and the 4 load-bearing design decisions (mic line is STATUS-only; always-show; .get defaults;
        mic_error -> '' in JSON)."
  section: "§4 (format_result decision) and §5 (test update/add list) are load-bearing."

# THE EDIT SITE A — status_snapshot() (navigate by method name; ~line 538)
- file: voice_typing/daemon.py
  why: "status_snapshot() returns the 8-key dict spread into every JSON response. S2 adds 2 keys.
        The mic values come from self (S1), NOT _feedback.snapshot() / _resolved_device() — keep them
        separate keys at the end of the literal."
  pattern: "Existing keys use direct values (self.is_listening()) or .get() on snap/dev dicts. Add
            mic_ok/mic_ok as direct self-attribute reads (self._mic_ok) + a coercion (self._mic_error or '')."
  gotcha: "The method caches device via _resolved_device(); do NOT route mic through it. mic_error must
           be coerced to '' (S1 stores None when healthy) so JSON consumers always get a string."

# THE EDIT SITE B — format_result() status branch (lines 42-73)
- file: voice_typing/ctl.py
  why: "format_result(cmd, response) is the PURE renderer. The status branch builds the multi-line text;
        toggle/start/stop return a terse one-liner with EXACT-equality tests. The mic line goes in the
        status branch ONLY (see design decision §6 of the research note)."
  pattern: "The file's convention is defensive .get() everywhere ('so a missing key never raises').
            Match it: .get('mic_ok', True) / .get('mic_error', ''). Append the mic line as the LAST line."
  gotcha: "Do NOT add the mic line to toggle/start/stop — that breaks test_format_toggle_on/off /
           start_on / stop_off (they assert == ('listening: ...', 0)). Those tests use _STATUS_ON which,
           after S2 adds mic_ok=True, still yields the terse one-liner."

# THE TEST FILE A — exact-set status test that MUST be updated (line 762)
- file: tests/test_daemon.py
  why: "test_status_snapshot_keys_and_cuda_values asserts set(s) == {8 keys}. S2 adds mic_ok/mic_error
        → the set becomes 10. This is the ONE assertion S2 must change. The daemon is built via
        _make_daemon_with_feedback (which, after S1, injects _ok_probe → mic_ok True, mic_error '')."
  critical: "After the update also assert s['mic_ok'] is True and s['mic_error'] == '' (the hermetic
             _ok_probe value). Add a SEPARATE test that sets d._mic_ok=False directly (decoupled from S1)."

# THE TEST FILE B — ctl format tests + the _STATUS_ON fixture (line 24)
- file: tests/test_voicectl.py
  why: "_STATUS_ON (line 24) is the canned 8-key status dict; add mic_ok/mic_error for protocol realism.
        test_format_status_multiline_has_partial_and_models (line 58) uses `in text` checks → survives
        the added 'mic: ok' line. The toggle/start/stop tests use == → survive because mic is status-only."
  pattern: "Layer A tests are pure format_result calls with canned JSON. Add two: status+mic_ok=False
            (assert 'mic: unavailable (...)' in text) and status+_STATUS_ON (assert 'mic: ok' in text)."

# THE README — two spots to update (Mode A docs)
- file: README.md
  why: "### Wrong microphone (line 187) is the 'mic device' subsection the contract names — add the
        'check voicectl status mic: line first' note. ## Logs, status, stopping (line 226) has the
        'Typical CUDA output' block — add 'mic: ok' as the last line so the example matches real output."
  critical: "Mode A = update the existing prose; do NOT restructure the sections. Keep the existing
             pactl/set-default-source/restart guidance intact — just add the voicectl-status-first tip."
```

### Current Codebase tree (relevant slice — S1 landing in parallel)

```bash
/home/dustin/projects/voice-typing/
├── README.md                # ### Wrong microphone @187; ## Logs, status, stopping @208 (example @226)  ← EDIT
├── voice_typing/
│   ├── daemon.py            # status_snapshot() @~538 (8 keys); _dispatch() @~790 (spreads **status_snapshot — NO edit)
│   │                          # AFTER S1 lands: __init__/_arm set self._mic_ok/self._mic_error (the INPUTS S2 reads).
│   └── ctl.py               # format_result() @42-73 (status branch is the multi-line block)            ← EDIT
└── tests/
    ├── test_daemon.py       # test_status_snapshot_keys_and_cuda_values @762 (exact 8-key set)          ← EDIT + ADD
    └── test_voicectl.py     # _STATUS_ON @24; test_format_status_multiline... @58                       ← EDIT + ADD
# NOTE: S1 (parallel) edits daemon.py (__init__/_arm/new methods) + test_daemon.py (_ok_probe + 4 sites +
# probe section) at DISJOINT lines from S2. No line-level merge conflict expected (see research note §8).
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py       # MODIFY status_snapshot() (+2 keys + docstring)
voice_typing/ctl.py          # MODIFY format_result() status branch (+mic line + docstring)
tests/test_daemon.py         # MODIFY exact-set test (8→10 keys); ADD test_status_snapshot_reflects_mic_health
tests/test_voicectl.py       # MODIFY _STATUS_ON (+mic fields); ADD 2 mic format tests
README.md                    # MODIFY "Wrong microphone" note + status example block
# No new files. No _dispatch/feedback/status.sh/config/systemd/cuda_check changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — S2 DEPENDS ON S1 (self._mic_ok / self._mic_error). S1 (P1.M1.T2.S1) is landing in
# parallel and creates those attributes in __init__. S2 reads them directly: self._mic_ok, self._mic_error.
# If status_snapshot() raises AttributeError on self._mic_ok at test time, S1 has NOT landed yet —
# that is the coordination signal, NOT a bug in S2. Verify S1 landed first: `grep -n '_mic_ok' voice_typing/daemon.py`
# must show the __init__ init + _refresh_mic_status. (parallel_execution_context: treat S1's PRP as a CONTRACT.)

# CRITICAL #2 — DO NOT EDIT _dispatch(). It already does {"ok": True, **self._daemon.status_snapshot()}
# for toggle/start/stop/status. Adding the keys to status_snapshot() propagates them to ALL JSON responses
# automatically. Editing _dispatch() is out of scope and unnecessary. Verify (git diff) it's unchanged.

# CRITICAL #3 — THE MIC LINE IS STATUS-ONLY. format_result's toggle/start/stop branches return a terse
# one-liner and have EXACT-equality tests (test_format_toggle_on == ("listening: on", 0), etc.). Adding a
# mic line there breaks those tests AND changes the terse UX. The contract OUTPUT scopes surfacing to
# "voicectl status"; JSON still carries mic_ok/mic_error on all commands (via the spread) for scripts.

# CRITICAL #4 — mic_error MUST be coerced to "" in JSON. S1 stores self._mic_error = None when the mic is
# healthy. JSON consumers expect a string. Use self._mic_error or "" (not the raw None). In format_result,
# .get("mic_error", "") or "" handles both a JSON "" and a defensive None.

# CRITICAL #5 — USE .get() WITH A 'True' DEFAULT for mic_ok in format_result. A response missing mic_ok
# (old daemon, a partial test fixture, the quit reply) must read as HEALTHY, not raise and not show a
# spurious "unavailable". .get("mic_ok", True) matches the file's existing defensive-.get convention.
# (The quit reply {"ok":true,"shutting_down":true} has no mic_ok — but quit branches before status, so this
# is belt-and-suspenders; still, never let a missing key raise.)

# GOTCHA #6 — THE EXACT-SET TEST IS THE ONE ASSERTION TO UPDATE. test_status_snapshot_keys_and_cuda_values
# (test_daemon.py:762) asserts set(s) == {8 keys}. After S2 it MUST be 10 keys. Every OTHER status test reads
# specific keys (s["device"], s["listening"]) and survives the additive change untouched. Do not 'fix' them.

# GOTCHA #7 — DECOUPLE S2's SURFACING TEST FROM S1's PROBE. The new daemon test sets d._mic_ok=False and
# d._mic_error="..." DIRECTLY on a daemon built via _make_daemon_with_feedback, then asserts status_snapshot
# carries them. This tests S2's job (surfacing) without depending on S1's probe mechanics (which have their
# own tests in S1). Do NOT mock pyaudio in S2's tests — that's S1's concern.

# GOTCHA #8 — _STATUS_ON fixture realism. After S2, the real protocol includes mic_ok/mic_error. Add them
# to _STATUS_ON (mic_ok=True, mic_error="") so the canned fixture matches reality. This is optional (the .get
# defaults cover absence) but keeps the fixture honest and makes the new "mic: ok" status test clean.

# GOTCHA #9 — DOCSTRINGS (the contract's "Update JSDoc/docstring"). status_snapshot()'s docstring lists the
# 8 fields in prose — add mic_ok/mic_error. format_result()'s docstring lists the status fields — add 'mic'.
# These are Mode-A doc surfaces; keep them accurate so future readers see the full field set.

# GOTCHA #10 — FULL PATHS in every bash command. This machine aliases python3→uv run, pip→alias, tmux→zsh
# plugin. Invoke .venv/bin/python and .venv/bin/pytest explicitly.

# GOTCHA #11 — DO NOT run/restart the live systemd daemon to verify (out of scope, slow, needs the real mic).
# The deterministic gates are the unit tests (canned JSON + direct attribute setting). The runtime effect
# (mic: line in voicectl status) follows directly from the verified format_result logic.

# GOTCHA #12 — DO NOT surface mic health in status.sh / state.json / tmux status line. The bug mentions tmux
# as a nice-to-have, but the S2 contract is specifically status_snapshot() (JSON) + format_result() (voicectl
# status text). status.sh reads feedback.py's state.json — a DIFFERENT path, out of scope. Note it as future
# work in the README if helpful, but do not implement it here.
```

## Implementation Blueprint

### Data models and structure

No config/schema/pydantic changes. The only "structure" change is two additive keys in a returned dict literal and one appended line in a formatted string. The keys' types are fixed by S1: `mic_ok: bool`, `mic_error: str` (coerced from `str | None`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: VERIFY S1 has landed (the INPUT contract) — no mutation
  - RUN:
      grep -n 'self._mic_ok' voice_typing/daemon.py | head
      grep -n 'def _refresh_mic_status\|def _probe_mic' voice_typing/daemon.py
  - EXPECTED: self._mic_ok appears in __init__ (init) and _refresh_mic_status (assignment); both methods exist.
    If ABSENT, S1 (P1.M1.T2.S1) has not landed — S2 CANNOT proceed (status_snapshot would raise AttributeError).
    Halt and flag: "blocked on P1.M1.T2.S1 (self._mic_ok/_mic_error not yet present)". (Gotcha #1.)
  - DO NOT: implement S1's probe yourself (out of scope). Wait for / coordinate with S1.

Task 2: MODIFY voice_typing/daemon.py — add mic_ok + mic_error to status_snapshot()
  - FIND status_snapshot() (navigate by `def status_snapshot(self)`; ~line 538). Its return literal ends:
        return {
            "listening": self.is_listening(),
            "partial": snap.get("partial", ""),
            "last_final": snap.get("last_final", ""),
            "uptime_s": round(self.uptime_s, 3),
            "device": dev.get("device", "unknown"),
            "compute_type": dev.get("compute_type", "unknown"),
            "final_model": dev.get("final_model", "unknown"),
            "realtime_model": dev.get("realtime_model", "unknown"),
        }
  - EDIT: add the two mic keys at the END of the literal (after realtime_model), and update the docstring:
        return {
            "listening": self.is_listening(),
            "partial": snap.get("partial", ""),
            "last_final": snap.get("last_final", ""),
            "uptime_s": round(self.uptime_s, 3),
            "device": dev.get("device", "unknown"),
            "compute_type": dev.get("compute_type", "unknown"),
            "final_model": dev.get("final_model", "unknown"),
            "realtime_model": dev.get("realtime_model", "unknown"),
            "mic_ok": self._mic_ok,            # bugfix Issue 2 / P1.M1.T2.S2: surface mic health (S1 detects)
            "mic_error": self._mic_error or "",  # None -> "" so JSON always carries a string
        }
  - EDIT the docstring's field list: change
        "Returns {listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model}."
      to
        "Returns {listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model,
        mic_ok, mic_error}. mic_ok/mic_error come from S1's PyAudio probe (self._mic_ok/self._mic_error),
        refreshed in __init__/_arm — lets voicectl status + JSON consumers see a dead mic without journalctl."
  - DO NOT: touch _resolved_device(), _dispatch(), __init__, _arm, or any other method. The mic values come
    from self (S1's attributes), NOT snap or dev.

Task 3: MODIFY voice_typing/ctl.py — add the mic line to format_result()'s status branch
  - FIND format_result()'s `if cmd == "status":` branch (lines ~58-66). Current:
        if cmd == "status":
            listening = "on" if response.get("listening") else "off"
            partial = response.get("partial", "") or ""
            last_final = response.get("last_final", "") or ""
            uptime = response.get("uptime_s", 0.0)
            device = response.get("device", "unknown")
            compute_type = response.get("compute_type", "unknown")
            final_model = response.get("final_model", "unknown")
            realtime_model = response.get("realtime_model", "unknown")
            text = (
                f"listening: {listening}\n"
                f"partial: {partial}\n"
                f"last: {last_final}\n"
                f"uptime: {uptime}s\n"
                f"device: {device} ({compute_type})\n"
                f"models: {final_model} + {realtime_model}"
            )
            return text, 0
  - EDIT: compute mic_ok/mic_error (defensive .get with True default), build mic_line, append it:
        if cmd == "status":
            listening = "on" if response.get("listening") else "off"
            partial = response.get("partial", "") or ""
            last_final = response.get("last_final", "") or ""
            uptime = response.get("uptime_s", 0.0)
            device = response.get("device", "unknown")
            compute_type = response.get("compute_type", "unknown")
            final_model = response.get("final_model", "unknown")
            realtime_model = response.get("realtime_model", "unknown")
            mic_ok = response.get("mic_ok", True)             # bugfix Issue 2 / P1.M1.T2.S2: default True
            mic_error = response.get("mic_error", "") or ""   #   so a missing key never looks broken
            if mic_ok:
                mic_line = "mic: ok"
            elif mic_error:
                mic_line = f"mic: unavailable ({mic_error})"
            else:
                mic_line = "mic: unavailable"
            text = (
                f"listening: {listening}\n"
                f"partial: {partial}\n"
                f"last: {last_final}\n"
                f"uptime: {uptime}s\n"
                f"device: {device} ({compute_type})\n"
                f"models: {final_model} + {realtime_model}\n"
                f"{mic_line}"
            )
            return text, 0
  - EDIT the format_result docstring's status-field list: add "mic" to the multi-line description, e.g.:
        "status -> multi-line: listening, partial, last_final, uptime, device, compute_type, final_model,
         realtime_model, mic  (PRD §4.8 'incl. partial and models loaded'; mic health per bugfix Issue 2)"
  - DO NOT: add a mic line to the toggle/start/stop branch (Gotcha #3 — breaks exact-equality tests).
  - DO NOT: change the ok:false / shutting_down branches.

Task 4: MODIFY tests/test_daemon.py — update the exact-set test + add a surfacing test
  - FIND test_status_snapshot_keys_and_cuda_values (~line 762). Current:
        s = d.status_snapshot()
        assert set(s) == {"listening", "partial", "last_final", "uptime_s",
                          "device", "compute_type", "final_model", "realtime_model"}
        assert s["listening"] is False and s["partial"] == "hello" and s["last_final"] == "world"
        assert s["device"] == "cuda" and s["compute_type"] == "float16"
        assert s["final_model"] == "distil-large-v3" and s["realtime_model"] == "small.en"
  - EDIT: add mic_ok/mic_error to the expected set + assert their hermetic values (_ok_probe → True/None):
        s = d.status_snapshot()
        assert set(s) == {"listening", "partial", "last_final", "uptime_s",
                          "device", "compute_type", "final_model", "realtime_model",
                          "mic_ok", "mic_error"}                      # bugfix Issue 2 / P1.M1.T2.S2
        assert s["listening"] is False and s["partial"] == "hello" and s["last_final"] == "world"
        assert s["device"] == "cuda" and s["compute_type"] == "float16"
        assert s["final_model"] == "distil-large-v3" and s["realtime_model"] == "small.en"
        assert s["mic_ok"] is True and s["mic_error"] == ""          # S1's _ok_probe via _make_daemon_with_feedback
  - ADD a new test (place it right after test_status_snapshot_cpu_fallback_models, ~line 786):
        def test_status_snapshot_reflects_mic_health(tmp_path, monkeypatch):
            """bugfix Issue 2 / P1.M1.T2.S2: status_snapshot surfaces self._mic_ok/_mic_error (S1's probe).

            Sets the attrs directly (decoupled from S1's probe mechanics) and asserts they appear in the
            snapshot with the right types (mic_ok bool, mic_error coerced from None -> '').
            """
            d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
            # healthy (default from _ok_probe):
            assert d.status_snapshot()["mic_ok"] is True
            assert d.status_snapshot()["mic_error"] == ""
            # unhealthy — set directly to test the SURFACING (S2's job), not the probe (S1's job):
            d._mic_ok = False
            d._mic_error = "no PyAudio input devices available"
            s = d.status_snapshot()
            assert s["mic_ok"] is False
            assert s["mic_error"] == "no PyAudio input devices available"
            # mic_error None coerces to "" even if a probe ever stores None on a False result:
            d._mic_error = None
            assert d.status_snapshot()["mic_error"] == ""
  - DO NOT: mock pyaudio here (that's S1's test concern). DO NOT touch the resolved_device tests at 796/810
    (S1 injects _ok_probe there; S2 leaves them alone).

Task 5: MODIFY tests/test_voicectl.py — update _STATUS_ON + add 2 mic format tests
  - FIND _STATUS_ON (~line 24). Current:
        _STATUS_ON = {
            "ok": True, "listening": True, "partial": "hello wor", "last_final": "previous sentence.",
            "uptime_s": 12.345, "device": "cuda", "compute_type": "float16",
            "final_model": "distil-large-v3", "realtime_model": "small.en",
        }
  - EDIT: add the mic fields so the canned fixture matches the real protocol:
        _STATUS_ON = {
            "ok": True, "listening": True, "partial": "hello wor", "last_final": "previous sentence.",
            "uptime_s": 12.345, "device": "cuda", "compute_type": "float16",
            "final_model": "distil-large-v3", "realtime_model": "small.en",
            "mic_ok": True, "mic_error": "",                       # bugfix Issue 2 / P1.M1.T2.S2
        }
  - ADD two tests (place in Layer A, after test_format_status_multiline_has_partial_and_models, ~line 65):
        def test_format_status_shows_mic_ok_when_healthy():
            text, code = ctl.format_result("status", _STATUS_ON)
            assert code == 0
            assert "mic: ok" in text

        def test_format_status_shows_mic_unavailable_with_error_when_broken():
            resp = {**_STATUS_ON, "mic_ok": False, "mic_error": "no PyAudio input devices available"}
            text, code = ctl.format_result("status", resp)
            assert code == 0
            assert "mic: unavailable (no PyAudio input devices available)" in text

        def test_format_status_mic_defaults_healthy_when_key_absent():
            # A response missing mic_ok (old daemon) must read as healthy, never 'unavailable'.
            resp = {k: v for k, v in _STATUS_ON.items() if k not in ("mic_ok", "mic_error")}
            text, code = ctl.format_result("status", resp)
            assert code == 0 and "mic: ok" in text
  - DO NOT: change the toggle/start/stop/quit format tests (mic is status-only — their output is unchanged).

Task 6: MODIFY README.md — troubleshooting note + status example (Mode A)
  - FIND "### Wrong microphone" (~line 187). After the existing pactl block, ADD a paragraph:
        If speech yields nothing, check the mic health line FIRST — `voicectl status` prints a `mic:`
        line (`mic: ok` when the default source is reachable, `mic: unavailable (<reason>)` when the
        daemon's PyAudio probe found no input device). This surfaces a dead or changed default source
        immediately, without digging into `journalctl`. After fixing the source, arm again with
        `voicectl toggle` (the probe re-runs on each arm).
  - FIND the "Typical CUDA output:" block in "## Logs, status, stopping" (~line 226). Current:
        listening: on
        partial: this is what i am say
        last: Previous sentence.
        uptime: 42.3s
        device: cuda (float16)
        models: distil-large-v3 + small.en
    ADD the mic line as the last line:
        listening: on
        partial: this is what i am say
        last: Previous sentence.
        uptime: 42.3s
        device: cuda (float16)
        models: distil-large-v3 + small.en
        mic: ok
    And append a sentence after the CPU-fallback note: "If the mic is unavailable, the last line reads
    `mic: unavailable (<reason>)` instead."
  - DO NOT: restructure the sections or remove existing guidance. Mode A = additive prose.

Task 7: VALIDATE — run the Validation Loop L1–L5 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S2: surface mic health (mic_ok/mic_error) in status_snapshot() and voicectl status".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — additive keys in status_snapshot() propagate to ALL JSON responses for free.
# _dispatch() does {"ok": True, **self._daemon.status_snapshot()} for toggle/start/stop/status, so the
# two new keys appear in every response without touching _dispatch. (Gotcha #2.)
"mic_ok": self._mic_ok,            # direct read of S1's attribute
"mic_error": self._mic_error or "",  # None -> "" for clean JSON

# PATTERN 2 — defensive .get() in format_result (the file's existing convention). mic_ok defaults True
# so a missing key (old daemon / quit reply / partial fixture) reads healthy, never raises.
mic_ok = response.get("mic_ok", True)
mic_error = response.get("mic_error", "") or ""
mic_line = "mic: ok" if mic_ok else (f"mic: unavailable ({mic_error})" if mic_error else "mic: unavailable")

# PATTERN 3 — mic line is STATUS-ONLY. toggle/start/stop keep the terse "listening: on/off" one-liner
# (exact-equality tests). JSON carries mic_ok/mic_error on all commands; the human mic line is the
# "show everything" status command's job. (Gotcha #3, design decision §6.)
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S1 (the INPUT; landing in parallel):
  - S1 creates self._mic_ok (bool, default True) + self._mic_error (str|None, default None) in __init__,
    refreshed in _arm via _refresh_mic_status(). S2 reads them. Task 1 verifies S1 landed before proceeding.

DOWNSTREAM — P1.M1.T2.S3 (rate-limit the RealtimeSTT mic-retry traceback spam in journalctl):
  - S3 reduces the journalctl noise (the "Microphone connection failed … Retrying..." tracebacks). S2 is
    INDEPENDENT of S3: S2 surfaces the daemon's own probe verdict; S3 limits the library's retry logging.
    Both are needed for full Issue 2 remediation; they touch different code (S2: status_snapshot/format_result;
    S3: a logging filter/handler on the realtimestt logger).

DOWNSTREAM — P1.M3.T1.S1 (changeset-level README sync):
  - S2 edits two README spots (the mic troubleshooting note + the status example). P1.M3.T1.S1 does the
    FULL changeset README pass and may reword/consolidate; S2's edits are the authoritative mic-status
    content for that pass. No conflict (additive).

FUTURE (explicitly OUT OF SCOPE for S2):
  - Surfacing mic health in the tmux status line (status.sh reads feedback.py state.json) — a different
    path; the bug mentions it as nice-to-have. S2 does NOT touch status.sh/feedback.py. (Gotcha #12.)
  - Auto re-resolve default device on sustained mic failure (Issue 2 fix (c)) — detection/recovery, not surfacing.

NO INTERFACE CHANGES:
  - config.toml / VoiceTypingConfig: no new field (mic health is a runtime probe, surfaced read-only).
  - control-socket protocol: additive keys only (mic_ok/mic_error); no new commands; backward compatible
    (format_result's .get defaults mean an old ctl talking to a new daemon, or vice-versa, stays healthy).
  - launch_daemon.sh / systemd unit / cuda_check: unchanged.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip). Run from the repo root
> `/home/dustin/projects/voice-typing`. All gates are pure/unit: NO real mic, NO CUDA, NO systemd.

### Level 1: The edits are in place (static + structural)

```bash
cd /home/dustin/projects/voice-typing
echo "--- S1 landed (the INPUT contract) ---"
grep -q 'self._mic_ok' voice_typing/daemon.py && echo "L1 PASS: self._mic_ok present (S1 landed)" || echo "L1 FAIL/BLOCKED: S1 not landed — see Task 1"
echo "--- status_snapshot has the 2 new keys ---"
.venv/bin/python - <<'PY'
import re
src = open("voice_typing/daemon.py").read()
m = re.search(r"def status_snapshot\(self\).*?return \{(.*?)\}", src, re.S)
assert m, "status_snapshot not found"
keys = re.findall(r'^\s*"([a-z_]+)":', m.group(1), re.M)
assert keys == ["listening","partial","last_final","uptime_s","device","compute_type","final_model","realtime_model","mic_ok","mic_error"], keys
print("L1 PASS: status_snapshot returns 10 keys:", keys)
PY
echo "--- _dispatch() UNCHANGED (still spreads **status_snapshot, no mic hardcoding) ---"
git diff -- voice_typing/daemon.py | grep -E '^[+-].*mic_ok|^[+-].*mic_error' | grep -i dispatch && echo "L1 FAIL: _dispatch edited" || echo "L1 PASS: _dispatch untouched (mic keys come from the spread)"
echo "--- format_result status branch has a mic line; toggle/start/stop do not ---"
grep -q 'mic_line\|mic: ok\|mic: unavailable' voice_typing/ctl.py && echo "L1 PASS: mic line in ctl.py" || echo "L1 FAIL: no mic line"
echo "--- README mentions the mic: line ---"
grep -qi 'mic: ok\|voicectl status.*mic\|mic: unavailable' README.md && echo "L1 PASS: README documents mic status" || echo "L1 FAIL: README not updated"
# Expected: S1 landed; status_snapshot returns the 10 keys; _dispatch byte-unchanged; ctl has the mic line; README updated.
```

### Level 2: status_snapshot surfacing (the daemon unit test — hermetic, no real mic)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "status_snapshot_keys_and_cuda_values or status_snapshot_reflects_mic_health or status_snapshot_reflects_listening_toggle or status_snapshot_cpu_fallback_models or resolved_device"
# Expected: ALL selected PASS. The exact-set test now asserts 10 keys; test_status_snapshot_reflects_mic_health
# asserts mic_ok/mic_error appear (healthy default + direct-set False + None->'' coercion). The resolved_device
# tests pass because S1 injected _ok_probe there (verify they're green — if they error on _mic_ok, S1 is stale).
```

### Level 3: format_result surfacing (the ctl unit tests — pure, canned JSON)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_voicectl.py -v
# Expected: ALL PASS. Specifically:
#   - test_format_status_shows_mic_ok_when_healthy        ("mic: ok" in status text)
#   - test_format_status_shows_mic_unavailable_with_error_when_broken  ("mic: unavailable (...)" in text)
#   - test_format_status_mic_defaults_healthy_when_key_absent          (missing key -> "mic: ok", no raise)
# AND the existing tests stay green (toggle/start/stop exact-equality; status `in` checks; quit; ok:false).
# If test_format_toggle_on/off/start_on/stop_off FAIL, you accidentally added the mic line to the wrong branch.
```

### Level 4: No regressions across daemon + ctl + control-socket suites

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py tests/test_voicectl.py tests/test_control_socket.py -v
# Expected: ALL PASS. The additive status_snapshot keys do not break the control-socket tests (they read
# specific keys / spread dicts). If test_control_socket fails on a key-set assertion, update it the same way
# as the daemon exact-set test (it is an additive change) — but check first whether S1 or S2 owns that file.
echo "--- purity invariant still green (S1's lazy pyaudio; S2 doesn't touch it) ---"
.venv/bin/python -m pytest tests/test_voicectl.py -k "ctl_module_present_and_imports_pure" -v
```

### Level 5: Scope guards — _dispatch/feedback/status.sh/config untouched; no S1/S3 work; no new files

```bash
cd /home/dustin/projects/voice-typing
echo "--- _dispatch() not edited by S2 (mic keys come from the status_snapshot spread) ---"
git diff -- voice_typing/daemon.py | grep -E '^\+.*def _dispatch|^-.*def _dispatch' && echo "L5 WARN: _dispatch signature changed" || echo "L5 PASS: _dispatch unchanged"
echo "--- no mic surfacing leaked into status.sh / feedback.py (out of scope) ---"
git diff --exit-code -- voice_typing/status.sh voice_typing/feedback.py voice_typing/config.py voice_typing/cuda_check.py voice_typing/launch_daemon.sh systemd/ config.toml pyproject.toml && echo "L5 PASS: those files untouched" || echo "L5 NOTE: a file in that set changed — verify it's not S2's doing (S2 edits only daemon.py/ctl.py/README + 2 test files)"
echo "--- no probe/rate-limit logic added (S1/S3's jobs) ---"
git diff -- voice_typing/daemon.py | grep -E '^\+.*(import pyaudio|_probe_mic|logging\.Filter|Microphone connection failed)' && echo "L5 WARN: S1/S3 logic leaked into S2" || echo "L5 PASS: no probe/rate-limit code in S2's diff"
echo "--- only the 5 intended files changed (no new files) ---"
git status --short
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/tasks.json plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md && echo "L5 PASS: read-only files unchanged" || echo "L5 FAIL: a read-only file was modified"
# Expected: git status shows ONLY voice_typing/daemon.py, voice_typing/ctl.py, README.md, tests/test_daemon.py,
# tests/test_voicectl.py modified (no new files); _dispatch/status.sh/feedback/config/systemd/cuda_check untouched;
# no probe or rate-limit code; PRD/tasks.json/prd_snapshot unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: S1 landed (`self._mic_ok` present); status_snapshot returns 10 keys; `_dispatch()` byte-unchanged; ctl has a mic line; README updated.
- [ ] L2: daemon status tests green (exact-set 10 keys; new `test_status_snapshot_reflects_mic_health`).
- [ ] L3: ctl tests green (2 new mic tests; existing toggle/start/stop/status/quit/ok:false all green).
- [ ] L4: full daemon + ctl + control_socket suites green; ctl purity test green.
- [ ] L5: only the 5 intended files changed; `_dispatch`/status.sh/feedback/config/systemd/cuda_check untouched; no probe/rate-limit code; read-only files unchanged.

### Feature Validation
- [ ] `status_snapshot()["mic_ok"]` is `self._mic_ok`; `["mic_error"]` is `self._mic_error or ""`.
- [ ] `mic_ok`/`mic_error` appear in toggle/start/stop/status JSON (via the spread — verify with a control-socket test or `_dispatch` read).
- [ ] `voicectl status` ends with `mic: ok` (healthy) / `mic: unavailable (<error>)` (broken).
- [ ] toggle/start/stop text unchanged (terse `listening: …`).
- [ ] A response missing `mic_ok` → format_result reads healthy (`mic: ok`), never raises.

### Code Quality Validation
- [ ] `status_snapshot()` + `format_result()` docstrings updated to list the mic fields (Mode A).
- [ ] Defensive `.get()` style matches ctl.py's existing convention.
- [ ] The new daemon test sets `_mic_ok`/`_mic_error` directly (decoupled from S1's probe).
- [ ] No bare `python`/`pip`/`pytest` in commands (all `.venv/bin/...`).
- [ ] Test additions are ADDITIVE; the only edited existing assertion is the exact-set test (8→10 keys).

### Scope Boundary Validation
- [ ] `_dispatch()` UNCHANGED (the spread carries the keys); `feedback.py`/`status.sh`/`config.py` UNCHANGED.
- [ ] No S1 probe logic, no S3 rate-limit logic (those are separate subtasks).
- [ ] No tmux/status.sh mic surfacing (out of scope; noted as future work).
- [ ] No conflict with parallel S1 (disjoint lines: S1=__init__/_arm/new methods + test sites; S2=status_snapshot + exact-set test).
- [ ] No new dependencies; no new files; README edits are additive (Mode A).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `_dispatch()` — it already spreads `**status_snapshot()` into every JSON response; the two new keys propagate automatically. Editing it is out of scope and unnecessary (Gotcha #2).
- ❌ Don't add the mic line to toggle/start/stop — those branches have exact-equality tests (`== ("listening: …", 0)`) and are meant to be terse. The mic line is status-only (Gotcha #3).
- ❌ Don't read `mic_error` as raw `self._mic_error` in the JSON — S1 stores `None` when healthy; coerce with `or ""` so JSON consumers always get a string (Gotcha #4).
- ❌ Don't use `response["mic_ok"]` (bracket access) in format_result — a missing key raises KeyError. Use `.get("mic_ok", True)` so old/partial responses read healthy (Gotcha #5; the file's convention).
- ❌ Don't forget to update the exact-set test (`test_status_snapshot_keys_and_cuda_values`) from 8→10 keys — it WILL fail otherwise. It is the ONE assertion S2 owns (Gotcha #6).
- ❌ Don't mock pyaudio in S2's tests — that's S1's concern. S2 tests the SURFACING by setting `d._mic_ok`/`d._mic_error` directly (Gotcha #7).
- ❌ Don't route mic health through `_resolved_device()` or `_feedback.snapshot()` — it comes straight from `self` (S1's attributes). Keep the keys separate.
- ❌ Don't implement S1's probe or S3's rate-limiting — S2 is surfacing ONLY. If `self._mic_ok` is absent, S1 hasn't landed; halt and flag (Gotcha #1), don't improvise detection.
- ❌ Don't surface mic health in `status.sh`/`state.json`/tmux — that's a different path, out of scope (Gotcha #12).
- ❌ Don't run/restart the live systemd daemon as "verification" — the deterministic gates are the unit tests (Gotcha #11).
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, `pyproject.toml`, or `config.toml` (READ-ONLY / owned by others).

---

## Confidence Score

**9/10** for one-pass implementation success. The change is small and surgical: two additive keys in one returned dict literal, one appended line in one formatted string, one exact-set test update, three additive tests, and two README prose edits. Every edit site has been read in the live repo with exact line numbers (`status_snapshot` ~538, `format_result` 42-73, the exact-set test at 762, `_STATUS_ON` at 24, the README subsections at 187/226), and the full test-impact analysis (which tests stay green vs need updating) is in `research/codebase_edit_sites_and_test_impact.md`. The design decisions are settled and contract-compliant: mic line is status-only (preserves the toggle/start/stop exact-equality tests), `.get("mic_ok", True)` keeps backward compatibility, and `mic_error or ""` guarantees clean JSON. The `_dispatch()` spread means the JSON contract is satisfied by editing ONE method (no protocol/handler changes).

The −1 residual risk is the **parallel-S1 dependency**: S2 reads `self._mic_ok`/`self._mic_error`, which S1 creates. If S1 has not landed when S2's tests run, `status_snapshot()` raises `AttributeError`. The PRP handles this explicitly (Task 1 verifies S1 landed before proceeding; the coordination signal is documented in Gotcha #1) per the parallel_execution_context instruction to treat S1's PRP as a contract. The two subtasks edit disjoint lines (S1 = `__init__`/`_arm`/new methods + test construction sites; S2 = `status_snapshot` + the exact-set test), so no line-level merge conflict is expected. No real mic/CUDA/systemd is needed for any gate.

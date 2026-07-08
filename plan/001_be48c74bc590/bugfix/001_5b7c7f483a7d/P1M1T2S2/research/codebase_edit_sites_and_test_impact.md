# Research Note — P1.M1.T2.S2: Surface mic health in status_snapshot() + voicectl status

**Scope:** internal code surgery on two existing functions. No external library/API research needed
(our own `status_snapshot()` + `format_result()`). All facts below VERIFIED by reading the live repo
on 2026-07-08. The bug is bugfix Issue 2 (Major) — mic-unavailable silent failure.

## 1. The S1 dependency (parallel) — the INPUT contract

`P1.M1.T2.S1` (parallel, treated as a CONTRACT) adds to `VoiceTypingDaemon`:
- `self._mic_ok: bool` (default `True`) and `self._mic_error: str | None` (default `None`).
- `_refresh_mic_status()` called at the end of `__init__` and `_arm()`; `_probe_mic()` (lazy `import pyaudio`).
- A `mic_prober=` injection kwarg; tests inject `_ok_probe` (returns `(True, None)`).
- **S1 leaves `status_snapshot()` at exactly 8 keys** — S2 owns adding `mic_ok`/`mic_error`.

⇒ When S2 runs, every `VoiceTypingDaemon` instance HAS `_mic_ok`/`_mic_error`. S2 reads them directly
(`self._mic_ok`, `self._mic_error`). If `status_snapshot()` raises `AttributeError` on `self._mic_ok`,
S1 has NOT landed yet — that is the coordination signal (see PRP Known Gotchas).

## 2. EDIT SITE A — `daemon.py` `status_snapshot()` (verified: method starts ~line 538)

Current return (8 keys):
```python
def status_snapshot(self) -> dict:
    """...Returns {listening, partial, last_final, uptime_s, device, compute_type, final_model,
    realtime_model}. ..."""
    snap = self._feedback.snapshot()
    dev = self._resolved_device()
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
```
S2 adds two keys to the returned dict:
```python
        "realtime_model": dev.get("realtime_model", "unknown"),
        "mic_ok": self._mic_ok,                       # bugfix Issue 2 / P1.M1.T2.S2
        "mic_error": self._mic_error or "",           # None -> "" for clean JSON
    }
```
And updates the docstring's field list (add `mic_ok`, `mic_error`). The mic values come from
`self` (S1's probe), NOT `_feedback.snapshot()` and NOT `_resolved_device()` — keep them separate.
`mic_error` uses `or ""` so JSON always carries a string (S1 stores `None` when healthy).

## 3. The automatic JSON spread (why no `_dispatch()` edit is needed)

`daemon.py` `_dispatch()` (verified ~line 790-810) does `{"ok": True, **self._daemon.status_snapshot()}`
for toggle/start/stop/status. Spreading the dict means the two new keys appear in EVERY JSON response
automatically — **S2 does NOT touch `_dispatch()`**. Scripts parsing JSON get `mic_ok`/`mic_error` on
all four commands for free. (The contract §4: "The JSON control-socket response includes mic_ok and
mic_error fields.")

## 4. EDIT SITE B — `ctl.py` `format_result()` (verified: lines 42-73)

The `status` branch builds the multi-line text. toggle/start/stop return a terse one-liner
(`"listening: on/off"`). DECISION (see §6): the mic line goes in the **status branch ONLY**, always
shown. Current status branch:
```python
    if cmd == "status":
        listening = "on" if response.get("listening") else "off"
        partial = response.get("partial", "") or ""
        ...
        text = (
            f"listening: {listening}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"models: {final_model} + {realtime_model}"
        )
        return text, 0
```
S2 appends a mic line (uses `.get("mic_ok", True)` so old/missing responses stay healthy; `.get("mic_error","")`):
```python
        mic_ok = response.get("mic_ok", True)
        mic_error = response.get("mic_error", "") or ""
        mic_line = "mic: ok" if mic_ok else f"mic: unavailable ({mic_error})" if mic_error else "mic: unavailable"
        text = (
            f"listening: {listening}\n"
            ...
            f"models: {final_model} + {realtime_model}\n"
            f"{mic_line}"
        )
        return text, 0
```
Update the `format_result` docstring's status list (add `mic`). `.get(...)` defensive style is already
the file's convention (the docstring says so) — match it.

## 5. Tests that S2 must UPDATE / ADD

**UPDATE — `tests/test_daemon.py::test_status_snapshot_keys_and_cuda_values` (line 762-770):**
```python
    assert set(s) == {"listening", "partial", "last_final", "uptime_s",
                      "device", "compute_type", "final_model", "realtime_model"}
```
→ add `"mic_ok", "mic_error"` (10-key set). Also assert `s["mic_ok"] is True` and `s["mic_error"] == ""`
(the daemon is built via `_make_daemon_with_feedback`, which after S1 injects `_ok_probe` → mic_ok True).

**UPDATE — `tests/test_voicectl.py::_STATUS_ON` (line 24-28):** add `"mic_ok": True, "mic_error": ""`
so the canned fixture matches the real protocol (optional but realistic; `.get` defaults already cover it).

**ADD — `test_voicectl.py`:** a status+mic-failure test and a status+mic-ok test:
- `format_result("status", {**_STATUS_ON, "mic_ok": False, "mic_error": "no PyAudio input devices"})`
  → text contains `"mic: unavailable (no PyAudio input devices)"`.
- `format_result("status", _STATUS_ON)` → text contains `"mic: ok"`.

**ADD — `test_daemon.py`:** `test_status_snapshot_reflects_mic_health` — construct daemon via
`_make_daemon_with_feedback`, set `d._mic_ok=False; d._mic_error="boom"`, assert snapshot carries them.
(Decouples S2's surfacing test from S1's probe mechanics — sets the attrs directly.)

Existing tests that stay GREEN (verified by analysis):
- `test_format_toggle_on/off`, `test_format_start_on`, `test_format_stop_off`: use `== ("listening: …", 0)`.
  mic line is STATUS-only → toggle/start/stop output unchanged → exact equality holds. ✓
- `test_format_status_multiline_has_partial_and_models`: uses `in text` assertions → the added
  `"mic: ok"` line doesn't break any `in` check. ✓
- `test_format_quit_no_listening_key`: quit branch unchanged. ✓
- All `_make_daemon_with_feedback` status tests: snapshot now has 10 keys but they read specific keys
  (`s["device"]`, `s["listening"]`) → still pass; only the exact-SET test needs the set update. ✓

## 6. Design decisions (load-bearing)

1. **Mic line is STATUS-only** (not toggle/start/stop). Rationale: the contract OUTPUT says "voicectl
   status now shows mic health"; toggle/start/stop are terse one-liners with exact-equality tests;
   the bug's prescribed fix (Issue 2 suggested fix (a)) explicitly names `voicectl status`. JSON still
   carries `mic_ok`/`mic_error` on ALL commands (via the `**status_snapshot()` spread), so scripts
   checking `start` can read `mic_ok` from JSON even though the human text stays terse.
2. **Status always shows the mic line** ("mic: ok" when healthy, "mic: unavailable (<error>)" when not).
   The contract permits either omit-or-show when ok; always-show is unambiguous and documents the
   field exists. README example gets a "mic: ok" line.
3. **`.get("mic_ok", True)`** in format_result so a response missing the key (old daemon / partial
   fixture) reads as healthy, never a spurious error. Matches the file's existing defensive `.get` style.
4. **`mic_error` → `""` in JSON** (`self._mic_error or ""`) so JSON consumers always get a string.

## 7. README updates (Mode A) — two spots

- **`### Wrong microphone` (line 187):** add a note that `voicectl status` now prints a `mic:` line
  (`mic: ok` / `mic: unavailable (<reason>)`), so check it FIRST (before journalctl) when speech yields
  nothing — a dead/changed default source shows up there immediately.
- **`## Logs, status, stopping` typical output (line 226):** add `mic: ok` to the CUDA example block
  (and note the CPU/unavailable variants). Keeps the documented example matching real output.

## 8. Parallel-execution conflict analysis (S1 ↔ S2)

Both edit `daemon.py` + `tests/test_daemon.py`, but at DISJOINT locations:
- daemon.py: S1 = `__init__`/`_arm`/new methods; S2 = `status_snapshot()` only. No overlap.
- test_daemon.py: S1 = `_ok_probe` stub (~400), 4 construction-site injections (407/759/796/810) +
  end-of-file probe section; S2 = exact-set test update (762-770) + one new surfacing test. Different
  lines; the only shared fixture is `_make_daemon_with_feedback` (S1 edits its RETURN at ~759 to add
  `mic_prober=_ok_probe`; S2's test at 762 CALLS it — S2 depends on S1's edit landing so the daemon
  has `_mic_ok=True`). ctl.py / test_voicectl.py / README = S2-only (S1 doesn't touch them).

No `git merge` line-level conflict is expected; the only true dependency is S2 reads `self._mic_ok`
which S1 creates.

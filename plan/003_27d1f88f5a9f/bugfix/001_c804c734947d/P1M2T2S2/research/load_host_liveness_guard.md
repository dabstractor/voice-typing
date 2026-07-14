# Research — `_load_host()` liveness guard (P1.M2.T2.S2 / bugfix Issue 3, Fix 3B)

This note pins the exact defect (the race window), the exact current code, the exact
corrected guard, the sibling-task boundary, the no-breakage proof, and the validated
fix behavior. The PRP (../PRP.md) references it as the single source of truth. All line
numbers verified live against the working tree on 2026-07-14 (S1 is IN-TREE).

## 1. The defect (bugfix Issue 3, Fix 3B — see architecture/bug_analysis.md §Issue 3)

`VoiceTypingDaemon._load_host()` (~line 631) has an early-return guard as its FIRST
statement inside `with self._lock:`:

```python
        with self._lock:
            if self._models_loaded:
                return True                       # resident → instant (second+ arm)
```

This guard short-circuits purely on `self._models_loaded` — it does NOT check whether
the host is alive. When the recorder-host child dies, `_models_loaded` is NOT cleared
until `run()`'s liveness check calls `_handle_dead_host()` (added by sibling S1). So in
the **race window where `_load_host()` is called (from `start()`/`toggle()`) BEFORE
`run()` has detected the death**, the guard sees stale `_models_loaded=True`, returns
`True`, and the **dead host is reused** — exactly the silent-breakage bug of Issue 3.

**Fix 3B (THIS task):** tighten the guard to also require a LIVE host:

```python
            if self._models_loaded and self._host is not None and self._host.is_alive:
                return True                       # resident + alive → instant (second+ arm)
```

Now: (a) a LIVE resident host still short-circuits (instant re-arm, UNCHANGED behavior);
(b) a DEAD host with stale `_models_loaded` does NOT short-circuit → falls through to the
spawn path → a fresh child is created. This is belt-and-suspenders for S1's `run()`
detection (in normal operation S1's `_handle_dead_host` already clears `_models_loaded`
before the next arm, so this guard's added `is_alive` term is False only in the race).

## 2. Exact current code + line numbers (verified live)

### 2.1 `voice_typing/daemon.py` `_load_host()` — the guard site (lines 648-654)
```
648:        with self._lock:
649:            if self._models_loaded:
650:                return True                       # resident → instant (second+ arm)
651:            if self._loading:
652:                while self._loading:               # wait for the in-flight spawn (spurious-wake safe)
653:                    self._load_cond.wait()
654:                return self._models_loaded         # its result (True=loaded, False=failed)
```
The edit swaps ONLY line 649's condition (and updates the line-650 comment). Lines 651+
(`_loading` wait path) and the rest of the method are UNCHANGED. The guard is INSIDE
`with self._lock:`, so reading `self._host` / `self._host.is_alive` here is lock-protected
and consistent with `_handle_dead_host`/`_unload_host` (which also mutate `_host` under
`_lock`) — no new race is introduced.

### 2.2 The `is_alive` property EXISTS on both host types (do NOT add it)
- **Production** `RecorderHost.is_alive` (recorder_host.py:156-158):
  `return self._proc is not None and self._proc.is_alive() and not self._dead` → False on
  a dead child.
- **Test adapter** `_LegacyRecorderHostAdapter.is_alive` (daemon.py:439-441): `return True`
  ALWAYS. So for every `recorder=`-injected test, the new `is_alive` term is always True →
  the guard behaves IDENTICALLY to the old one → DORMANT (see §4).
- **`_FakeHost.is_alive`** (tests/test_daemon.py:466-468): `return self._alive`, where
  `_alive` starts `False` and `spawn()` sets `_alive = bool(spawn_result)` (default True).
  So a freshly-spawned `_FakeHost` has `is_alive=True` → re-arm short-circuits identically.

## 3. Sibling-task boundary (CRITICAL — avoid conflicts; S1 is already IN-TREE)

- **S1 (P1.M2.T2.S1)** — IN-TREE (verified: `run()` check at daemon.py:745,
  `_handle_dead_host` at 773). It edits `run()` + adds `_handle_dead_host()`. It does NOT
  touch `_load_host()`. S1 ALONE makes the next arm re-spawn, because `_handle_dead_host`
  sets `_models_loaded=False` → the EXISTING `if self._models_loaded:` guard already does
  not short-circuit. **S2 (THIS task) is complementary defense-in-depth** for the race
  window before `run()` detects the death.
- **S2 (THIS task)** — edits ONLY the `_load_host()` early-return guard (one condition).
  Touches NO other method, NO test file.
- **S3 (P1.M2.T2.S3)** — owns the COMMITTED pytest for dead-child detection (run() loop,
  recovery on next arm, status correctness). S2 does NOT add a committed test (test_daemon.py
  is owned by S3 + P1.M2.T1.S2); S2 validates via a throwaway probe (Level 3) + non-regression.
- **P1.M2.T1.S2** — owns the phase-after-disarm tests appended to test_daemon.py. DISJOINT.
- All four tasks touch DISJOINT regions of daemon.py / test_daemon.py → git merges cleanly.

## 4. No-breakage proof (baseline 345 passed — verified live, S1 in-tree)

The new `is_alive` term changes behavior ONLY when `_models_loaded=True` AND
`_host.is_alive=False` (a dead host with stale loaded flag). No existing test creates that
state. Categorized:

1. **`recorder=`-injected tests** (the majority — run-loop, on_final, phase, shutdown, etc.):
   the daemon wraps the stub in `_LegacyRecorderHostAdapter` whose `is_alive=True` ALWAYS →
   the guard is `True and True and True` = True → short-circuits IDENTICALLY to before.
   **Dormant. No behavior change.**
2. **`host_factory=_fake_host_factory()` + `_FakeHost` tests** (lazy-load / idle-unload /
   single-flight, e.g. test_daemon.py:2506-2740): `_models_loaded` starts False → first
   `_load_host()` spawns → `_FakeHost.spawn()` sets `_alive=True` → `_models_loaded=True`.
   Re-arm: guard is `True and True and True(=is_alive)` → short-circuits → spawn NOT called
   again (the `spawn_calls == 1` assertions still hold). **Identical behavior.**
   - idle-unload sets `_models_loaded=False` + `_host=None` → re-arm guard is `False and …`
     → spawn path either way → identical.
3. **`recorder_host=`-injected tests** (test_daemon.py:1647-1745, the SIGTERM-teardown
   suite): they inject `_CountingHost`/`_GatedHost` (which have ONLY `stop()` — NO
   `is_alive`, NO `spawn`) and call ONLY `request_shutdown()`/`shutdown()` — they NEVER call
   `start()`/`toggle()`/`_load_host()`/`run()`. So the guard is NEVER evaluated for them →
   no `AttributeError` (no `is_alive` attr), no behavior change. (S1's `run()` check is
   likewise never reached by these — confirmed by the 345-green baseline with S1 in-tree.)

Net: the edit is **dormant for all 345 existing tests**. The only tests it would affect are
S3's future dead-host tests (intended).

## 5. Validated fix behavior (non-invasive monkeypatch probe — no source modified)

Faithfully reproduced the EDITED `_load_host` by swapping the guard in the live method's
`inspect.getsource` + `exec` (NO source file touched), then ran the race scenario with a
killable pre-built host injected via `recorder_host=` + a `_fake_host_factory()` for the
re-spawn path. Results:

```
(1) OK: live host short-circuits (no re-spawn); _host is still the live killable host
(3) OK: dead host (stale _models_loaded) is NOT reused; a fresh host is spawned
(4) OK: re-arm on the fresh live host short-circuits (no extra spawn)
ALL OK
```

This proves: (a) the fix closes the race (dead host → re-spawn), (b) live hosts are
unchanged (instant re-arm preserved), (c) idempotency holds (no double-spawn). The same
scenario against the CURRENT (un-fixed) guard returns True and reuses the dead host (the bug).

## 6. Gotchas

1. **Guard is INSIDE `with self._lock:`** — reading `self._host` / `self._host.is_alive`
   here is lock-protected (consistent with `_handle_dead_host`/`_unload_host`). No new race.
2. **Reproduce the `→` (U+2192) in oldText** — line 650's comment uses `→`. The edit tool
   matches exact bytes; copy verbatim. The newText comment uses `→` too (style consistency).
3. **The spawn-path fallback** — when the guard does NOT short-circuit, `_load_host` builds a
   fresh host via `self._host_factory or RecorderHost` (line 660). In production that is a real
   `RecorderHost` (correct — re-spawn). In tests that inject `recorder_host=` WITHOUT a
   `host_factory`, this would hit the real `RecorderHost` — but NO such test calls
   `_load_host` (see §4.3). The S2 probe injects BOTH `recorder_host=` and `host_factory=` so
   the re-spawn uses a `_FakeHost` (CUDA-free).
4. **No committed test in S2** — test_daemon.py is owned by S3 (+ P1.M2.T1.S2, parallel).
   S2 validates via the Level-3 throwaway probe + the 345 non-regression suite. S3 formalizes
   the committed dead-host-recovery test.
5. **Do NOT add `is_alive` anywhere** — it already exists on both host types (§2.2).
6. **Scope = ONE condition in `_load_host()`** — do NOT touch `run()`, `_handle_dead_host`,
   `_unload_host`, `_disarm`, `_arm`, `start`, `toggle`, or any test file.

## 7. Validation commands (verified)

```bash
cd /home/dustin/projects/voice-typing
# Non-regression (THE gate — edit is dormant for all existing tests): baseline 345 -> 345.
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Targeted (lazy-load / single-flight — the guard's re-entry callers):
.venv/bin/python -m pytest tests/test_daemon.py -v -k "load or spawn or lazy or idle_unload or single_flight or rearm or re_arm"
# Structural sanity after the edit:
grep -n "if self._models_loaded and self._host is not None and self._host.is_alive" voice_typing/daemon.py
# Optional lint (ruff is a uv tool at /home/dustin/.local/bin/ruff, NOT in .venv; mypy NOT installed):
/home/dustin/.local/bin/ruff check voice_typing/daemon.py || true
```
ALWAYS use `.venv/bin/python -m pytest ...` (zsh aliases bare python/pytest). Never run mypy
(not installed). The Level-3 throwaway probe (in the PRP) proves the fix behavior post-edit.

# Research — P1.M1.T2.S3: Rate-limit RealtimeSTT mic-retry traceback spam

Two sources: (A) authoritative Python `logging` internals (CPython `logging/__init__.py`,
read directly), (B) codebase recon (exact line numbers + verbatim snippets). Everything below
was verified against the live repo + installed RealtimeSTT wheel.

---

## A. Python `logging.Filter` semantics (the load-bearing facts)

Source of truth: CPython `Lib/logging/__init__.py` (read directly). Stable across 3.x.

### A1. A Filter on a LOGGER gates BEFORE callHandlers → single chokepoint
`Logger.handle` (~`logging/__init__.py:1629`):
```python
def handle(self, record):
    if (not self.disabled) and self.filter(record):   # <- OUR FILTER RUNS HERE
        self.callHandlers(record)                      # <- only if filter passed
```
`Filterer.filter` (~`:807`) loops the logger's own `.filters`; if ANY returns falsy →
returns False → `callHandlers` is **never invoked**. So one Filter on the `realtimestt`
logger returning False drops the record before:
  (a) the `realtimestt` logger's OWN handlers (its console `StreamHandler` + the
      `FileHandler` when `no_log_file` is False — but P1.M1.T1.S1 already set
      `no_log_file=True`, so only the console handler remains), AND
  (b) propagation to the root logger's stderr handler (`callHandlers` walks
      `c = c.parent` while `propagate` is True).
=> A single `logging.getLogger("realtimestt").addFilter(...)` is the chokepoint for BOTH
   surfaces that reach journald. No handler-level / root-level attachment needed.

### A2. Propagate stays True (RealtimeSTT never disables it)
`RealtimeSTT/core/initialization.py:_configure_logger` (lines 305-336) does `setLevel(DEBUG)`,
adds a `StreamHandler` + optional `FileHandler`, and NEVER sets `logger.propagate = False`.
=> propagation to root is active; A1's chokepoint reasoning holds. Verified: `grep propagate`
   in initialization.py → no hits.

### A3. Mutating a LogRecord inside filter() is DOCUMENTED
`Filter.filter` docstring (~`:766`): "the record may be modified in-place." Because the filter
runs in `Logger.handle` BEFORE `callHandlers` → `Handler.handle` → `emit` → `Formatter.format`,
EVERY downstream handler formats the MUTATED record. `getMessage()` (~`:362`) is NOT cached
(`str(self.msg) % self.args` recomputed each call) → rewriting `record.msg` + `record.args=()`
reliably changes the formatted text.
GOTCHA — clear BOTH `exc_info` AND `exc_text`: `Formatter.format` (~`:669`) appends
`record.exc_text` (a CACHE of the traceback) if truthy. Setting `exc_info=None` alone leaves a
stale `exc_text` → traceback still appended. Our summary path sets both to `None`.
GOTCHA — level-gate timing: the handler-level threshold (`record.levelno >= hdlr.level` in
`callHandlers`) runs AFTER our filter on the MUTATED levelno. So downgrading ERROR→WARNING is
fine for display at the production default (`cfg.log.level="INFO"` → WARNING>=INFO passes both
the realtimestt console handler and root stderr handler). If a user sets `log.level >= ERROR`,
WARNING summaries would be dropped by the gate — acceptable (they opted into minimal logging)
and inherent to in-filter re-leveling. Note in gotchas.

### A4. getMessage() for the f-string call returns the interpolated string
`logger.error(f"Microphone connection failed: {e}. Retrying...", exc_info=True)` → the f-string
is evaluated at call time and passed positionally as `msg`; `args` is `()`. `getMessage()`
returns it verbatim (no `%` interpolation). => `"Microphone connection failed" in
record.getMessage()` works. Match on `getMessage()` ALWAYS (robust for both f-string and
%-style calls).

### A5. addFilter/removeFilter are NOT lock-protected; filters is a plain list; double-register possible
`addFilter`/`removeFilter` (~`:800`) use a membership (`in`, i.e. `__eq__`) check, NOT a
class-de-dup. Two DISTINCT instances of the same Filter subclass (default identity `__eq__`)
BOTH get registered. `addFilter`/`removeFilter` do NOT acquire the logging lock (unlike
addHandler/removeHandler). => (1) install ONCE from the main thread during `_setup_logging`
(never concurrently); (2) make install IDEMPOTENT by removing any existing instance of the
class before adding a fresh one, so repeated `_setup_logging` calls (main() calls it on the
config-load-fail fallback path AND the normal path) never accumulate filters. This is also what
keeps the per-attempt counter from double-incrementing (Filterer.filter short-circuits on the
first falsy, so a 2nd instance's side effects would be skipped when the 1st suppresses —
divergent counts).

### A6. dedup-filter recipe (canonical)
The stdlib `Filter.filter` in-place-modify hook IS the canonical dedup/rate-limit mechanism
(Logging Cookbook). Recipe: keep last-emitted timestamp + count; in filter() suppress within
the cooldown, periodically emit a summarized (mutated) record. Runs once per record at the
chokepoint (A1) → dedups all downstream handlers for free.

---

## B. Codebase recon (exact line numbers, verified)

### B1. daemon.py imports — `logging` + `time` ALREADY at module top
`daemon.py:64-82` (pure stdlib + already-landed pure modules). `import logging` @69,
`import time` @76. Module logger @84 `logger = logging.getLogger(__name__)`. Adding a Filter
class (uses only logging+time) needs NO new imports and preserves import purity (torch /
ctranslate2 / RealtimeSTT are ALL lazy, imported inside `build_recorder`; confirmed by the
module docstring lines 39-43). So `from voice_typing import daemon` stays cheap → pure Filter
unit tests are fast and side-effect-free.

### B2. `_setup_logging` EXACT source — `daemon.py:923-941`
```python
def _setup_logging(level_name: object) -> None:          # 923
    """Configure stderr logging at the resolved level (PRD §4.2; P1.M4.T3.S1).
    ...basicConfig is IDEMPOTENT: a no-op if the root logger already has a handler
    (e.g. under pytest caplog ...) ...
    """
    logging.basicConfig(                                  # 936
        stream=sys.stderr,
        level=_resolve_log_level(level_name),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
```
HOOK POINT: append the filter install as the LAST statement (after basicConfig). The
attachment must be a DIRECT `logging.getLogger("realtimestt").addFilter(...)`, NOT contingent
on basicConfig actually running (basicConfig is a no-op under pytest caplog — the integration
test monkeypatches it to a no-op and must still observe the filter).

### B3. main() call sites — `daemon.py:966-972`
- `daemon.py:968` `_setup_logging("INFO")` — config-load-fail fallback (then `return 1`).
- `daemon.py:972` `_setup_logging(cfg.log.level)` — PRIMARY.
Both run in main() BEFORE `VoiceTypingDaemon(...)`/`build_recorder` (~`:983`) constructs the
recorder, i.e. BEFORE RealtimeSTT's `_configure_logger` ever runs and before any retry loop can
fire. So attaching inside `_setup_logging` guarantees the filter exists first. RealtimeSTT's
`addHandler` does NOT clear `.filters`, so the filter survives `_configure_logger`.

### B4. NO existing logging.Filter anywhere in the repo
`grep -rn 'logging.Filter|addFilter|class .*(logging.Filter)' *.py` → no matches. Invent the
class; mirror the defensive docstring style of `LatencyLog` (`daemon.py:244`) and
`_resolve_log_level` (`daemon.py:907`).

### B5. Layer B tests EXACT source — `tests/test_daemon.py:998-1022`
```python
def test_setup_logging_configures_stderr_at_level(monkeypatch):       # 1001
    captured = {}
    def _capture(**kw):
        captured.update(kw)
    monkeypatch.setattr(logging, "basicConfig", _capture)             # 1007
    daemon._setup_logging("DEBUG")
    assert captured["stream"] is sys.stderr
    assert captured["level"] == logging.DEBUG
    assert "asctime" in captured["format"] and "message" in captured["format"]

def test_setup_logging_passes_resolved_level(monkeypatch):            # 1014
    captured = {}
    def _capture(**kw):
        captured.update(kw)
    monkeypatch.setattr(logging, "basicConfig", _capture)             # 1020
    daemon._setup_logging("not-a-level")  # invalid -> INFO
    assert captured["level"] == logging.INFO
```
Idiom: monkeypatch `logging.basicConfig` to a kwarg-capturing fake so the test never touches
the real root logger. These two tests assert ONLY on `captured` (basicConfig kwargs) — they are
NOT affected by S3 (which adds a filter-attach after basicConfig); they keep passing unchanged.
caplog idiom to mirror: `with caplog.at_level(LEVEL, logger="NAME"):` then
`" ".join(rec.getMessage() for rec in caplog.records)` (test_daemon.py:263).

### B6. tests/test_daemon.py import quirks
- `import logging` @18; `from voice_typing import daemon` @23; `import sys` mid-file @979
  (globally available).
- `time` is imported ONLY as `import time as _time` @334 (mid-file). A timestamp-based pure
  unit test must reuse `_time` OR add its own import, OR (preferred) monkeypatch
  `daemon.time.monotonic` for deterministic clock control.
- NO `LogRecord` construction exists anywhere in the file — S3's pure unit test creates the
  first. Pattern: `logging.LogRecord(name="realtimestt", level=logging.ERROR,
  pathname=__file__, lineno=1, msg="Microphone connection failed: boom. Retrying...",
  args=(), exc_info=None)`.

### B7. RealtimeSTT retry source — `core/audio_input_worker.py:155-167`
```python
            except Exception as e:
                logger.error(f"Microphone connection failed: {e}. Retrying...", exc_info=True)  # 162
                input_device_index = None
                time.sleep(3)  # Wait before retrying       # 164
                continue
```
`logger = logging.getLogger("realtimestt")` @worker:11 (same instance as initialization.py:33).
Message is STABLE: prefix `Microphone connection failed: ` + `{e}` + suffix `. Retrying...`.
`exc_info=True` → the ERROR record carries a full traceback (the spam). Loops every ~3s,
indefinitely, no max-retries, no backoff (verified live: 2822+ errors). NOTE: the filter
throttles the LOG EMISSION only — it does NOT and cannot stop the actual mic retry (that loop
lives in the spawned worker thread, out of our process control). The README note must say so.

### B8. README "## Logs, status, stopping" — line 214 (section 214-260); does NOT mention mic retry
The section covers: `journalctl -f`, INFO/DEBUG latency lines, `voicectl status`, the `mic:` /
`mic: unavailable` status line (added by P1.M1.T2.S2), GPU VRAM check, systemctl stop/disable.
It does NOT mention `Microphone connection failed` or retry/rate-limit. The `mic:` line is the
daemon's OWN PyAudio probe (S1/S2) — unrelated to RealtimeSTT's per-3s retry LOG spam.
MODE-A additive insertion point: after the latency-line paragraph (between README lines 223 and
225), a 1-3 sentence note that the per-3s `Microphone connection failed ... Retrying` ERROR is
rate-limited to ~one summary per 60s (the retry still happens; only the repeated traceback log
line is throttled), pointing to `### Wrong microphone` / `voicectl status` `mic:` for the fix.
(Also relevant: `### Wrong microphone` @187, which S2 already augmented with the `mic:` tip.)

---

## C. Parallel-execution context (P1.M1.T2.S1 + S2 landing alongside S3)

- **S1 (detection):** adds `_probe_mic` + `self._mic_ok`/`self._mic_error` to `__init__`/`_arm`.
  S3 does NOT read those attributes — S3 is purely a logging filter on the `realtimestt`
  logger. No interface coupling.
- **S2 (surfacing):** adds `mic_ok`/`mic_error` to `status_snapshot()` + a `mic:` line in
  `voicectl status`, and edits two README spots (the `### Wrong microphone` note + the status
  example `mic: ok`). S3 edits a DIFFERENT README spot (the "## Logs, status, stopping"
  latency paragraph @223) — disjoint from S2's README edits. S3 does NOT touch
  `status_snapshot()`/`ctl.py`. No line-level conflict.
- **T1.S1 (no_log_file):** added `"no_log_file": True` to `_FIXED_KWARGS` (now landed). That
  removed the `FileHandler` from the `realtimestt` logger, so the only handler on it is the
  console `StreamHandler` (+ propagation to root). S3's single logger-level filter still covers
  both (A1), independent of whether the FileHandler is present.
- S3 edits: `voice_typing/daemon.py` (new Filter class + install helper + `_setup_logging`
  hook) + `tests/test_daemon.py` (new test section) + `README.md` (one additive note). All
  disjoint from S1's/S2's edit sites.

# PRP — P1.M1.T2.S3: Rate-limit RealtimeSTT mic-retry traceback spam in journalctl

## Goal

**Feature Goal**: Stop RealtimeSTT from flooding `journalctl` with a full ERROR+traceback every
~3 seconds when the mic is unavailable. Attach an idempotent `logging.Filter` to the
`realtimestt` logger (inside `_setup_logging`) that (a) lets the **first** "Microphone connection
failed … Retrying…" ERROR+traceback through unchanged, (b) **suppresses** (drops) the per-attempt
repeats within a dedup window, and (c) emits a single **summarized WARNING** (no traceback) on a
periodic tick ("Microphone still unavailable after N retry attempts (last error: …)"). This is the
**rate-limit / noise** half of bugfix Issue 2; S1 is detection, S2 is surfacing.

**Deliverable** (3 files edited, no new files):
1. `voice_typing/daemon.py` — +`MicRetryRateLimitFilter` class, +`_extract_mic_retry_error` /
   `_summarize_mic_retry` module helpers, +`_install_mic_retry_rate_limiter` (idempotent) helper,
   +one call at the end of `_setup_logging`. (`import logging`@69 + `import time`@76 already
   present — no new imports.)
2. `tests/test_daemon.py` — +a dedicated test section: pure filter-logic unit tests (deterministic
   clock via `monkeypatch.setattr(daemon.time, "monotonic", …)`), a traceback-preservation test,
   an integration test asserting `_setup_logging` attaches exactly ONE filter (idempotent), and a
   chokepoint test proving one logger-level filter gates the handler.
3. `README.md` — +one additive (Mode A) note in "## Logs, status, stopping" describing the
   rate-limited mic-retry summaries.

**Success Definition**:
- (a) A single `logging.Filter` on `logging.getLogger("realtimestt")` is the **chokepoint**: it
  gates records in `Logger.handle` BEFORE `callHandlers`, so it suppresses both the library's own
  console `StreamHandler` AND propagation to the root stderr/journald handler (RealtimeSTT leaves
  `propagate=True`; verified). No handler-level or root-level attachment is needed.
- (b) First matching record (`count==1`) → returns `True`, record UNCHANGED (still ERROR, `exc_info`
  intact — the full traceback is logged exactly once).
- (c) Subsequent matches within `dedup_seconds` (default 60) AND not on a summary tick → returns
  `False` (the per-attempt traceback is dropped — no journal spam).
- (d) On every `summary_every`-th occurrence (default 20 ≈ 60 s @ 3 s/retry) OR once `dedup_seconds`
  has elapsed since the last emitted record → the record is REWRITTEN IN PLACE to a WARNING summary
  with NO traceback (`levelno`/`levelname` set, `exc_info` AND `exc_text` cleared, `msg`/`args`
  replaced) and passed through. Count is cumulative across the filter's lifetime.
- (e) Non-matching records (everything else RealtimeSTT/the app logs) pass through UNCHANGED and do
  NOT increment the counter (the filter is transparent for all other logging).
- (f) Install is IDEMPOTENT: repeated `_setup_logging` calls (main() may call it on the
  config-load-fail fallback path AND the normal path) leave exactly ONE filter; re-installing resets
  the counter (no stale state). No double-registration / double-counting.
- (g) All existing tests stay green; the only existing method edited is `_setup_logging` (one appended
  call + a docstring line). No real mic, no CUDA, no systemd, no real RealtimeSTT in any gate.
- (h) No out-of-scope work: no S1 (probe) or S2 (status surfacing) changes, no `ctl.py` /
  `config.py` / `cuda_check.py` / systemd / `launch_daemon.sh` changes, no `status_snapshot()` change.

## User Persona

**Target User**: the operator of the 24/7 systemd daemon (the end user + anyone reading
`journalctl --user -u voice-typing`).
**Use Case**: the webcam mic disconnects; the daemon's RealtimeSTT worker enters its infinite ~3 s
retry loop. Today this logs a full traceback every 3 s (2822+ errors observed on the live daemon),
burying useful log lines and ballooning the journal. After S3, the journal shows ONE full traceback
on the first failure, then a one-line WARNING summary roughly once per minute.
**Pain Points Addressed**: bugfix Issue 2's noise half — "a full traceback (`exc_info=True`) on
every attempt … 2822+ errors and counting". (Visibility of the failure itself — `voicectl status`
`mic:` line — is S2's job; S3 only tames the per-attempt log spam.)

## Why

- **Bugfix Issue 2 (Major)** is the source. Its prescribed fix (b): "Rate-limit or suppress the
  per-attempt traceback (wrap/redirect the RealtimeSTT logger for this message, or detect the
  recurring error and log a single summarized warning)." S3 IS that fix. (S1 detects; S2 surfaces;
  S3 limits the reactive noise. All three are needed for full Issue 2 remediation and are
  independent — S3 touches only the `realtimestt` logger.)
- **The chokepoint is the logger, not a handler.** RealtimeSTT's `realtimestt` logger has its own
  console `StreamHandler` (stderr) AND propagates to the root handler (also stderr/journald). A
  `logging.Filter` attached to the *logger* runs in `Logger.handle` BEFORE `callHandlers`, so ONE
  attachment gates BOTH surfaces (verified against CPython `logging/__init__.py`). Attaching to a
  handler instead would miss one of the two paths; attaching to root would over-reach. The logger is
  the single correct chokepoint.
- **In-place record mutation is documented + correct.** `logging.Filter.filter`'s docstring
  explicitly permits "the record may be modified in-place"; the filter runs before formatting, so
  rewriting `levelno`/`levelname`/`exc_info`/`exc_text`/`msg`/`args` reliably changes what every
  downstream handler prints (and clears the traceback, which lives in `exc_info`/`exc_text`).
- **Idempotency is non-negotiable.** CPython `addFilter`/`removeFilter` are NOT lock-protected and
  use `__eq__` (two distinct instances BOTH register → double-counting), and `main()` can call
  `_setup_logging` twice (fallback path + normal path). The install helper removes any existing
  instance before adding a fresh one, so there is always exactly one filter and never stale state.

## What

Add a rate-limiting filter to the `realtimestt` logger:

- **`MicRetryRateLimitFilter(logging.Filter)`** — `__init__(self, dedup_seconds=60.0,
  summary_every=20)`; instance state `_count` (cumulative) and `_last_seen` (`time.monotonic()` of
  the last EMITTED record — first or summary; `0.0` = never). `filter(record)`:
  - read `record.getMessage()`; if it does NOT contain `"Microphone connection failed"` → return
    `True` (transparent; counter untouched);
  - else `self._count += 1`, `now = time.monotonic()`; if `count == 1` → set `_last_seen = now`,
    return `True` (full traceback once);
  - else if `now - self._last_seen >= dedup_seconds` OR `count % summary_every == 0` → rewrite the
    record to a WARNING summary (via the helper), set `_last_seen = now`, return `True`;
  - else return `False` (suppress the per-attempt spam).
- **`_extract_mic_retry_error(message)`** — pure module helper: pull `<e>` out of
  `"Microphone connection failed: <e>. Retrying..."` (strip the known prefix + suffix; fall back to
  the whole message) so the summary names the most recent failure, not just a count.
- **`_summarize_mic_retry(record, count, message)`** — rewrite a `LogRecord` IN PLACE to a WARNING
  summary with no traceback: `record.levelno=logging.WARNING`, `record.levelname="WARNING"`,
  `record.exc_info=None`, `record.exc_text=None`, `record.msg=…`, `record.args=()`. (Clears BOTH
  `exc_info` and `exc_text` — the latter is a cached traceback `Formatter.format` appends.)
- **`_install_mic_retry_rate_limiter(logger_name="realtimestt")`** — idempotent: remove any existing
  `MicRetryRateLimitFilter` from `logging.getLogger(logger_name).filters`, then add a fresh one.
- **`_setup_logging`** — append `_install_mic_retry_rate_limiter("realtimestt")` as its LAST
  statement (after `basicConfig`); add one docstring line noting the rate-limit filter.

`status_snapshot()`, `ctl.py`, `config.py`, `cuda_check.py`, `__init__`/`_arm`/`_probe_mic` are
**untouched** (S1/S2's territory).

### Success Criteria

- [ ] `MicRetryRateLimitFilter` subclasses `logging.Filter`; `__init__(dedup_seconds=60.0,
      summary_every=20)` initializes `_count=0` and `_last_seen=0.0`; `filter()` implements the
      first-pass / suppress / summary logic above.
- [ ] First matching record → `True`, record UNCHANGED (level ERROR, `exc_info` intact); count==1.
- [ ] Subsequent within-window non-tick matches → `False`; count keeps incrementing.
- [ ] On `count % summary_every == 0` OR `now - _last_seen >= dedup_seconds` → `True` and record
      rewritten to WARNING, `exc_info is None`, `exc_text is None`,
      `"Microphone still unavailable after N retry attempts (last error: <e>)"` in `getMessage()`.
- [ ] Non-matching records → `True`, counter unchanged.
- [ ] `_extract_mic_retry_error` parses `<e>`; `_summarize_mic_retry` clears traceback + rewrites.
- [ ] After `_setup_logging` (even with `basicConfig` mocked to a no-op), `realtimestt.filters`
      contains exactly ONE `MicRetryRateLimitFilter`; a second `_setup_logging` leaves exactly ONE.
- [ ] A logger-level filter gates a capturing handler: logging the message 25× with
      `summary_every=20` yields exactly 2 emitted records (the first + the 20th-summary).
- [ ] Only `_setup_logging` is edited in daemon.py (one appended call + docstring line); the new
      class + 3 helpers are pure additions. No `import` lines added. No new files.
- [ ] README "## Logs, status, stopping" gains one additive note about the rate-limited summaries.

## All Needed Context

### Context Completeness Check

_Pass._ Every claim is verified against the live repo + the installed RealtimeSTT wheel + CPython's
`logging/__init__.py` (read directly). Exact current line numbers: `_setup_logging` @daemon.py:923-941
(`basicConfig` call @936); `main()` call sites @968 (fallback) + @972 (primary); the retry source
@`RealtimeSTT/core/audio_input_worker.py:162`; `_configure_logger` @`RealtimeSTT/core/initialization.py:305-336`
(never sets `propagate=False`); Layer B tests @`tests/test_daemon.py:998-1022`; README "## Logs,
status, stopping" @214 (does NOT mention mic retry). A developer new to this codebase can apply the
patch from this PRP + the research note alone.

### Documentation & References

```yaml
# MUST READ — the CPython logging internals that make the design correct (authoritative)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T2S3/research/logging_filter_semantics_and_codebase.md
  why: "§A proves the load-bearing facts: (A1) a Filter on a LOGGER runs in Logger.handle BEFORE
        callHandlers -> one attachment gates BOTH the logger's own handlers AND propagation to root
        (single chokepoint); (A2) RealtimeSTT leaves propagate=True (verified); (A3) mutating a
        LogRecord in filter() is documented and must clear BOTH exc_info AND exc_text; (A4)
        getMessage() returns the interpolated f-string so substring matching works; (A5)
        addFilter/removeFilter are unlocked + use __eq__ -> double-register possible -> idempotent
        install required. §B gives exact daemon.py/test/README/RealtimeSTT line numbers."
  critical: "These four facts (chokepoint-is-the-logger; mutate+clear exc_text; match getMessage();
            idempotent install) ARE the design contract. Violating any -> wrong behavior or flaky tests."

# MUST READ — the defect definition + prescribed fix (authoritative)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2 Issue 2 (Major) fix (b): 'Rate-limit or suppress the per-attempt traceback (wrap/redirect
        the RealtimeSTT logger for this message, or detect the recurring error and log a single
        summarized warning).' S3 IS that fix. Verified live: 2822+ 'Microphone connection failed'
        errors, full traceback per ~3 s attempt."
  critical: "S3 rate-limits the LOG line ONLY. It does NOT and cannot stop the actual ~3 s mic retry
            (that loop lives in the spawned worker thread, out of process control). The README note
            must say so. Detection=S1, surfacing=S2, noise-limit=S3 — S3 touches only the realtimestt
            logger."

# THE EDIT SITE A — _setup_logging (navigate by `def _setup_logging`; ~line 923, basicConfig @936)
- file: voice_typing/daemon.py
  why: "_setup_logging is the INPUT the contract names ('The _setup_logging function ... called from
        main() at line 916'). It runs in main() BEFORE the recorder is constructed (~:983), so the
        filter is in place before RealtimeSTT's _configure_logger runs and before any retry fires.
        Append ONE call as the last statement; attach DIRECTLY to the logger (NOT contingent on
        basicConfig, which is a no-op under pytest caplog — the integration test mocks basicConfig)."
  pattern: "Module helpers near _setup_logging (group logging-config concerns). _resolve_log_level
            (@907) is the defensive-style model for the docstrings. `import logging`@69 + `import
            time`@76 are ALREADY present — NO new imports."
  gotcha: "Do NOT attach inside build_recorder / VoiceTypingDaemon — the contract scopes it to
           _setup_logging. Do NOT make the attach conditional on basicConfig (it's idempotent)."

# THE LIBRARY SOURCE — the exact retry line + the logger wiring (verified against the installed wheel)
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/audio_input_worker.py
  why: "Line 162: logger.error(f'Microphone connection failed: {e}. Retrying...', exc_info=True) +
        line 164 time.sleep(3) + continue (infinite, no backoff). logger=getLogger('realtimestt') @11.
        Message is STABLE: prefix 'Microphone connection failed: ' + {e} + suffix '. Retrying...'.
        _extract_mic_retry_error strips exactly that prefix+suffix."
  critical: "Match on 'Microphone connection failed' (a substring of getMessage()). exc_info=True ->
            the ERROR record carries a full traceback (the spam). The first-occurrence path MUST
            leave exc_info intact (full traceback once); the summary path MUST clear exc_info+exc_text."

# THE LIBRARY LOGGER CONFIG — propagate stays True (the chokepoint reasoning depends on this)
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py
  why: "_configure_logger @305-336: setLevel(DEBUG) + addHandler(StreamHandler) + optional
        FileHandler (no_log_file suppresses the FileHandler — P1.M1.T1.S1 set no_log_file=True).
        NEVER sets propagate=False -> records reach root. So ONE logger-level filter covers both."
  critical: "If a future RealtimeSTT version set propagate=False, the logger-level filter would STILL
            gate the logger's own console handler (chokepoint holds for own handlers regardless). The
            design is robust to that change."

# THE TEST FILE — Layer B idiom + the time/LogRecord quirks
- file: tests/test_daemon.py
  why: "Layer B _setup_logging tests @998-1022 monkeypatch logging.basicConfig to a kwarg-capturing
        fake (the hermetic pattern to MIRROR for the integration test). caplog idiom @263
        (`with caplog.at_level(...)` + `rec.getMessage()`). `import time as _time` @334 (NOT bare
        `time`) — the deterministic pure tests monkeypatch `daemon.time.monotonic` instead. NO
        LogRecord construction exists yet; S3 adds the first (`logging.LogRecord(name='realtimestt',
        level=ERROR, pathname=__file__, lineno=1, msg=..., args=(), exc_info=...)`)."
  pattern: "ADD a new section at the END of the file under a banner comment (additive — do NOT touch
            existing tests). Mirror the `monkeypatch.setattr(logging, 'basicConfig', _capture)` hermetic
            pattern; mirror the defensive `_resolve_log_level` docstring style for the new class."
  critical: "The integration test MUST snapshot+restore logging.getLogger('realtimestt').filters
             (process-global singleton) in a finally to avoid cross-test bleed. Pure logic tests
             construct the filter directly + feed LogRecords (NO global logger) -> fully hermetic."

# THE README — the one additive (Mode A) note
- file: README.md
  why: "## Logs, status, stopping @214 (section 214-260) does NOT mention mic retry today. Insert ONE
        additive paragraph after the latency-line paragraph (between current lines ~223 and ~225):
        what the rate-limited mic-retry log looks like (one full traceback, then a ~once-per-minute
        WARNING summary; the retry still happens, only the repeated traceback is throttled) and where
        to look for the fix (### Wrong microphone @187 / voicectl status mic: line)."
  critical: "Mode A = additive prose. Do NOT restructure the section or touch the S2-added mic: status
             example (@239). Keep it to ~2-3 sentences."

# PYTHON DOCS — the in-place-modify hook (cite, don't rely on memory)
- url: https://docs.python.org/3/library/logging.html#logging.Filter.filter
  why: "Filter.filter docstring: 'the record may be modified in-place.' Authorizes the summary-rewrite
        path. (Local CPython logging/__init__.py confirms filter runs before Formatter.format.)"
- url: https://docs.python.org/3/library/logging.html#logging.Logger.handle
  why: "Logger.handle applies logger-level filtering BEFORE callHandlers — the chokepoint guarantee."
```

### Current Codebase tree (relevant slice — S1/S2 may be landing in parallel)

```bash
/home/dustin/projects/voice-typing/
├── README.md                 # ## Logs, status, stopping @214 (no mic-retry mention)         ← EDIT (additive note)
├── voice_typing/
│   └── daemon.py             # _setup_logging @923-941 (basicConfig @936); main() calls @968/@972;
│   │                           import logging @69, import time @76 (NO new imports needed).
│   │                           NOTE: S1 (parallel) edits __init__/_arm/_probe_mic; S2 edits
│   │                           status_snapshot/ctl — DISJOINT from S3's _setup_logging region.
└── tests/
    └── test_daemon.py        # Layer B _setup_logging tests @998-1022; time as _time @334.     ← EDIT (new section)
# NOTE: importing voice_typing.daemon is CHEAP (torch/ctranslate2/RealtimeSTT all lazy) — pure
# filter tests are fast. No existing logging.Filter anywhere in the repo (S3 invents the class).
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py        # ADD: MicRetryRateLimitFilter + _extract_mic_retry_error +
#                              _summarize_mic_retry + _install_mic_retry_rate_limiter; MODIFY
#                              _setup_logging (append one call + one docstring line). No new imports.
tests/test_daemon.py          # ADD: dedicated test section (pure logic + traceback-preserve +
#                              integration/idempotent + chokepoint). No existing test changed.
README.md                     # MODIFY: one additive paragraph in ## Logs, status, stopping.
# No new files. No ctl.py/config.py/cuda_check/systemd/launch_daemon/status_snapshot changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE CHOKEPOINT IS THE LOGGER, NOT A HANDLER. CPython Logger.handle runs
# self.filter(record) BEFORE callHandlers; if it returns False, NEITHER the logger's own handlers
# (RealtimeSTT's console StreamHandler + the FileHandler when no_log_file is False — but T1.S1 set
# no_log_file=True, so only the console handler) NOR propagation to the root stderr handler sees the
# record. So ONE `logging.getLogger("realtimestt").addFilter(...)` covers both surfaces that reach
# journald. Do NOT attach to a handler (misses one path) or to root (over-reaches). (research §A1.)

# CRITICAL #2 — CLEAR BOTH exc_info AND exc_text ON THE SUMMARY PATH. CPython Formatter.format
# appends record.exc_text (a CACHE of the traceback) if truthy — even after you set exc_info=None.
# If you only clear exc_info, a stale exc_text still prints the traceback. The summary helper MUST
# set BOTH record.exc_info=None and record.exc_text=None. (research §A3.)

# CRITICAL #3 — MUTATING THE RECORD IS DOCUMENTED BUT MUST BE DONE BEFORE FORMATTING. Filter.filter
# runs in Logger.handle before callHandlers->emit->Formatter.format, so rewriting levelno/levelname/
# exc_info/exc_text/msg/args IS seen by every downstream handler. getMessage() is NOT cached (it
# recomputes str(msg) % args), so record.msg=... + record.args=() reliably changes the text. This is
# the canonical dedup/rate-limit recipe. (research §A3/A6.)

# CRITICAL #4 — IDEMPOTENT INSTALL OR DOUBLE-REGISTER. CPython addFilter uses __eq__ (default object
# identity), so two DISTINCT instances of the same Filter class BOTH register. main() can call
# _setup_logging twice (config-load-fail fallback @968 + normal @972). Without the remove-then-add
# reset, each call adds another filter -> double-counting / divergent state. ALSO: addFilter/
# removeFilter are NOT lock-protected (unlike addHandler/removeHandler), so install is done ONCE per
# _setup_logging from the MAIN thread (never concurrently). The reset also gives a fresh counter so a
# re-call can't leave stale state. (research §A5.)

# CRITICAL #5 — ATTACH DIRECTLY, NOT CONTINGENT ON basicConfig. logging.basicConfig is IDEMPOTENT: a
# no-op if root already has a handler (e.g. under pytest caplog). The integration test monkeypatches
# basicConfig to a no-op. So the filter attach must be a DIRECT getLogger("realtimestt").addFilter,
# unconditional, as the LAST statement of _setup_logging — so it happens regardless of whether
# basicConfig actually installed a handler. (B2; daemon.py _setup_logging docstring @929.)

# GOTCHA #6 — MATCH ON getMessage(), NOT record.msg. record.getMessage() returns the interpolated
# message for BOTH the f-string call site (RealtimeSTT) and any future %-style call. For the current
# f-string call, record.msg already holds the interpolated string, but getMessage() is robust to
# both. Match on `"Microphone connection failed" in record.getMessage()`. (research §A4.)

# GOTCHA #7 — THE FILTER THROTTLES THE LOG LINE, NOT THE RETRY. RealtimeSTT's time.sleep(3) retry
# loop lives in the spawned worker thread; a logging.Filter cannot and must not try to stop the
# actual mic retry — only the repeated traceback LOG emission. The README note must state this so an
# operator isn't misled into thinking the retry stopped. (B7; OUTPUT contract.)

# GOTCHA #8 — LEVEL-GATE TIMING ON THE SUMMARY PATH. The handler-level threshold
# (record.levelno >= hdlr.level in callHandlers) runs AFTER our filter, on the MUTATED levelno. At the
# production default cfg.log.level="INFO", a WARNING(30) summary passes both the realtimestt console
# handler (level=recorder.level, default INFO) and the root stderr handler (level=INFO). If a user
# sets log.level >= ERROR, WARNING summaries would be dropped by the gate (they opted into minimal
# logging). This is inherent to in-filter re-leveling and acceptable — note it, do not code around it.

# GOTCHA #9 — UNRELATED RECORDS MUST BE TRANSPARENT AND NOT INCREMENT THE COUNTER. RealtimeSTT and
# the app log many other things to the realtimesttt logger (e.g. "Microphone connected and validated",
# model load lines). The filter MUST return True for any record whose getMessage() lacks the match
# substring WITHOUT touching _count/_last_seen. This keeps the filter a no-op for all non-mic-retry
# logging (so it can never accidentally rate-limit something else). Assert this in a unit test.

# GOTCHA #10 — THE FIRST-OCCURRENCE RECORD MUST KEEP exc_info INTACT. count==1 returns True with the
# record UNCHANGED (level stays ERROR, exc_info preserved) so the full traceback is logged exactly
# once. Do NOT clear exc_info on the first path. (A unit test constructs a real exc_info tuple and
# asserts the filter leaves record.exc_info is exc_info on the first pass.)

# GOTCHA #11 — DETERMINISTIC TIME IN PURE TESTS. The filter uses time.monotonic(). Do NOT use real
# sleeps (flaky). tests/test_daemon.py imports time only as `import time as _time` @334. The cleanest
# deterministic seam: monkeypatch `daemon.time.monotonic` (daemon.py does `import time` @76) to a
# controllable clock. Pure logic tests construct the filter directly + feed LogRecords (NO global
# logger) -> fully hermetic. (B6.)

# GOTCHA #12 — THE realtimestt LOGGER IS A PROCESS-GLOBAL SINGLETON. The integration test MUST
# snapshot logging.getLogger("realtimestt").filters, clear them, call _setup_logging, assert exactly
# one MicRetryRateLimitFilter, and RESTORE in a finally. (Other tests that call _setup_logging, e.g.
# Layer B, will leave a filter — that's harmless because it's transparent for non-matching messages
# (Gotcha #9), and the idempotent install means re-calls reset the counter. My own tests never depend
# on the global filter state.) (B6 residual risk.)

# GOTCHA #13 — FULL PATHS in every bash command. This machine aliases python3->uv run, pip->alias,
# tmux->zsh plugin. Invoke .venv/bin/python and .venv/bin/pytest explicitly.

# GOTCHA #14 — DO NOT run/restart the live systemd daemon to verify (out of scope, slow, needs the
# real mic + a disconnect to reproduce). The deterministic gates are the unit tests (filter logic +
# idempotent install + chokepoint). The runtime effect (one traceback then periodic summaries in
# journald) follows directly from the verified filter logic + the CPython chokepoint guarantee.

# GOTCHA #15 — DO NOT touch status_snapshot()/ctl.py (S2), __init__/_arm/_probe_mic (S1), or
# _FIXED_KWARGS (T1.S1). S3 edits ONLY _setup_logging + adds the filter class/helpers + the README
# note + the test section. Editing those is out of scope and risks a merge conflict with the parallel
# subtasks (they touch DISJOINT regions — keep yours disjoint).
```

## Implementation Blueprint

### Data models and structure

No config/schema/pydantic changes. The only new "structure" is one `logging.Filter` subclass with
two scalar instance attributes (`_count: int`, `_last_seen: float`) and two tunable floats/ints
(`dedup_seconds`, `summary_every`). The `LogRecord` mutation is in-place field assignment (no new
type). Everything is pure-Python using the already-imported `logging` + `time`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD voice_typing/daemon.py — MicRetryRateLimitFilter + 3 module helpers (pure additions)
  - PLACE: immediately BEFORE `def _setup_logging` (~line 923), right after `_resolve_log_level`
    ends (~921) — group the logging-config helpers together. Do NOT touch _resolve_log_level.
  - ADD the pure extraction helper first (it has its own unit test):
        def _extract_mic_retry_error(message: str) -> str:
            """Pull <e> out of 'Microphone connection failed: <e>. Retrying...'.

            Returns <e> (or the whole message as a fallback). Keeps the periodic mic-retry summary
            actionable (bugfix Issue 2 / P1.M1.T2.S3): it names the most recent failure instead of
            just counting attempts. Strips the known prefix + suffix; falls back to the full message
            if the shape differs.
            """
            prefix = "Microphone connection failed: "
            suffix = ". Retrying..."
            text = message
            if text.startswith(prefix):
                text = text[len(prefix):]
            if text.endswith(suffix):
                text = text[: -len(suffix)]
            return text
  - ADD the in-place record-rewrite helper:
        def _summarize_mic_retry(record: logging.LogRecord, count: int, message: str) -> None:
            """Rewrite a mic-retry LogRecord IN PLACE into a single WARNING summary (no traceback).

            Bugfix Issue 2 / P1.M1.T2.S3. CPython Formatter.format appends record.exc_text (a CACHE of
            the traceback) if truthy, so BOTH exc_info and exc_text must be cleared to fully strip the
            traceback. getMessage() is not cached, so rewriting record.msg + record.args changes the
            formatted text. Runs inside a logging.Filter (documented: 'the record may be modified
            in-place'), before callHandlers -> handler.emit -> Formatter.format.
            """
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
            record.exc_info = None
            record.exc_text = None
            record.msg = (
                f"Microphone still unavailable after {count} retry attempts "
                f"(last error: {_extract_mic_retry_error(message)})"
            )
            record.args = ()
  - ADD the Filter class:
        class MicRetryRateLimitFilter(logging.Filter):
            """Rate-limit RealtimeSTT's per-retry 'Microphone connection failed' ERROR+traceback spam.

            Bugfix Issue 2 / P1.M1.T2.S3. RealtimeSTT's AudioInputWorker retries the mic in an
            infinite ~3-second loop (core/audio_input_worker.py:162), logging a full traceback
            (exc_info=True) on EVERY attempt -> thousands of identical errors in journald (2822+
            observed on the live daemon). Attached to the 'realtimestt' logger via
            _install_mic_retry_rate_limiter (called from _setup_logging) so a SINGLE filter gates
            records in Logger.handle BEFORE callHandlers -> it suppresses BOTH the library's own
            console handler AND propagation to the root stderr/journald handler (CPython:
            Filterer.filter runs before callHandlers; RealtimeSTT leaves propagate=True).

            Behavior:
              - first occurrence (count==1): pass through unchanged (the full ERROR+traceback logs ONCE);
              - subsequent within `dedup_seconds` of the last emitted record, not on a summary tick:
                SUPPRESSED (return False);
              - on every `summary_every`-th occurrence OR once `dedup_seconds` elapsed since the last
                emitted record: rewrite the record in place to a WARNING summary WITHOUT a traceback
                ('Microphone still unavailable after N retry attempts (last error: <e>)'), pass through.

            This throttles the LOG line only — it does NOT stop the actual ~3s mic retry (that loop
            lives in the spawned worker thread). Match key: record.getMessage() contains
            'Microphone connection failed' (robust for f-string and %-style call sites). Non-matching
            records pass through untouched and do NOT increment the counter.
            """

            def __init__(self, dedup_seconds: float = 60.0, summary_every: int = 20) -> None:
                super().__init__()
                self.dedup_seconds = float(dedup_seconds)
                self.summary_every = max(1, int(summary_every))
                self._count = 0
                self._last_seen = 0.0  # time.monotonic() of the last EMITTED record; 0.0 == never

            def filter(self, record: logging.LogRecord) -> bool:
                message = record.getMessage()
                if "Microphone connection failed" not in message:
                    return True  # unrelated record — never touch it (counter stays clean)
                self._count += 1
                now = time.monotonic()
                if self._count == 1:
                    self._last_seen = now  # first ever: let the full ERROR + traceback through once
                    return True
                if (
                    now - self._last_seen >= self.dedup_seconds
                    or self._count % self.summary_every == 0
                ):
                    _summarize_mic_retry(record, self._count, message)
                    self._last_seen = now
                    return True
                return False  # within the window and not a summary tick — drop the per-attempt spam
  - ADD the idempotent install helper:
        def _install_mic_retry_rate_limiter(logger_name: str = "realtimestt") -> None:
            """Attach the mic-retry rate-limit filter to the named logger, IDEMPOTENTLY.

            Bugfix Issue 2 / P1.M1.T2.S3. Removes any already-attached MicRetryRateLimitFilter first,
            so repeated _setup_logging calls (main() may invoke it on the config-load-fail fallback
            path AND the normal path) never double-register. CPython addFilter/removeFilter are NOT
            lock-protected and use __eq__ (distinct instances both register), so this reset-then-add
            is the safe pattern; it is called once per _setup_logging from the MAIN thread (never
            concurrently). A fresh instance also resets the dedup counter, so re-calling _setup_logging
            cannot leave stale state from a prior run.
            """
            target = logging.getLogger(logger_name)
            for existing in [f for f in target.filters if isinstance(f, MicRetryRateLimitFilter)]:
                target.removeFilter(existing)
            target.addFilter(MicRetryRateLimitFilter())
  - DO NOT add any `import` lines (logging + time already at module top @69/@76).
  - DO NOT touch _resolve_log_level, main(), VoiceTypingDaemon, status_snapshot, build_recorder.

Task 2: MODIFY voice_typing/daemon.py — _setup_logging appends the install call + a docstring line
  - FIND _setup_logging (~line 923). Current body ends:
        logging.basicConfig(
            stream=sys.stderr,
            level=_resolve_log_level(level_name),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
  - EDIT: append the install call as the LAST statement (CRITICAL #5 — direct attach, not contingent
    on basicConfig):
        logging.basicConfig(
            stream=sys.stderr,
            level=_resolve_log_level(level_name),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        # bugfix Issue 2 / P1.M1.T2.S3: rate-limit RealtimeSTT's per-retry mic traceback spam.
        _install_mic_retry_rate_limiter("realtimestt")
  - EDIT the docstring: append one sentence to the existing docstring (after the basicConfig-
    idempotency explanation), e.g.:
        "Also attaches (idempotently) a MicRetryRateLimitFilter to the 'realtimestt' logger so the
        library's per-~3s 'Microphone connection failed' ERROR+traceback spam logs once then degrades
        to periodic WARNING summaries (bugfix Issue 2 / P1.M1.T2.S3)."
  - DO NOT change the basicConfig call itself; DO NOT move/branch the attach (unconditional).

Task 3: ADD tests/test_daemon.py — dedicated rate-limit test section (ADDITIVE; no existing test changed)
  - PLACE: a new section at the END of the file, under a clear banner comment:
        # ===========================================================================
        # bugfix P1.M1.T2.S3 — rate-limit RealtimeSTT mic-retry traceback spam
        # (MicRetryRateLimitFilter + _install_mic_retry_rate_limiter + _setup_logging wiring.
        #  ADDITIVE: pure filter-logic unit tests (deterministic daemon.time.monotonic) + an
        #  idempotent-install integration test + a chokepoint test. ZERO real RealtimeSTT/mic/CUDA.)
        # ===========================================================================
  - ADD a LogRecord factory + a deterministic clock helper near the top of the section:
        def _mic_retry_record(msg="Microphone connection failed: boom. Retrying...",
                              level=logging.ERROR, exc_info=None):
            return logging.LogRecord(
                name="realtimestt", level=level, pathname=__file__, lineno=1,
                msg=msg, args=(), exc_info=exc_info,
            )

        def _fixed_clock(monkeypatch, t):
            """Freeze daemon.time.monotonic at t (deterministic dedup-window tests)."""
            monkeypatch.setattr(daemon.time, "monotonic", lambda: t)
  - ADD the pure-logic unit tests:
        def test_mic_retry_filter_passes_unrelated_records_untouched():
            f = daemon.MicRetryRateLimitFilter()
            rec = _mic_retry_record(msg="Microphone connected and validated (device index: 2)")
            assert f.filter(rec) is True          # transparent
            assert f._count == 0                  # unrelated records do NOT increment the counter
            assert rec.levelno == logging.ERROR    # record untouched

        def test_mic_retry_filter_first_occurrence_passes_through_unchanged(monkeypatch):
            _fixed_clock(monkeypatch, 0.0)
            f = daemon.MicRetryRateLimitFilter()
            rec = _mic_retry_record()
            assert f.filter(rec) is True
            assert rec.levelno == logging.ERROR            # level preserved (full error once)
            assert "Microphone connection failed" in rec.getMessage()  # message preserved
            assert f._count == 1

        def test_mic_retry_filter_first_occurrence_preserves_traceback(monkeypatch):
            _fixed_clock(monkeypatch, 0.0)
            f = daemon.MicRetryRateLimitFilter()
            try:
                raise RuntimeError("portaudio exploded")
            except RuntimeError:
                exc_info = sys.exc_info()
            rec = _mic_retry_record(
                msg="Microphone connection failed: portaudio exploded. Retrying...",
                exc_info=exc_info,
            )
            assert f.filter(rec) is True
            assert rec.exc_info is exc_info      # traceback preserved on the first pass
            assert rec.exc_text is None           # not yet formatted/cached
            assert rec.levelno == logging.ERROR

        def test_mic_retry_filter_suppresses_repeats_within_window(monkeypatch):
            f = daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=20)
            _fixed_clock(monkeypatch, 0.0)
            assert f.filter(_mic_retry_record()) is True      # count=1: first (pass)
            for i in range(2, 20):                             # every ~3s, well within the 60s window
                _fixed_clock(monkeypatch, (i - 1) * 3.0)
                assert f.filter(_mic_retry_record()) is False  # count=2..19: suppressed
            assert f._count == 19

        def test_mic_retry_filter_summary_on_nth_occurrence(monkeypatch):
            f = daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=20)
            _fixed_clock(monkeypatch, 0.0)
            assert f.filter(_mic_retry_record()) is True       # count=1: first (full error)
            for i in range(2, 20):
                _fixed_clock(monkeypatch, (i - 1) * 3.0)
                assert f.filter(_mic_retry_record()) is False  # 2..19 suppressed
            _fixed_clock(monkeypatch, 19 * 3.0)                # 57s: within window, but count%20==0
            summary = _mic_retry_record()
            assert f.filter(summary) is True                   # count=20: summary tick
            assert summary.levelno == logging.WARNING
            assert summary.levelname == "WARNING"
            assert summary.exc_info is None and summary.exc_text is None   # CRITICAL #2
            text = summary.getMessage()
            assert "Microphone still unavailable after 20 retry attempts" in text
            assert "last error: boom" in text
            assert f._count == 20

        def test_mic_retry_filter_summary_after_dedup_window(monkeypatch):
            # summary_every huge so ONLY the elapsed-window triggers a summary
            f = daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=10_000)
            _fixed_clock(monkeypatch, 0.0)
            assert f.filter(_mic_retry_record()) is True       # count=1 @ t=0
            _fixed_clock(monkeypatch, 3.0)
            assert f.filter(_mic_retry_record()) is False      # count=2 suppressed
            _fixed_clock(monkeypatch, 70.0)                    # > 60s since last emitted record
            summary = _mic_retry_record()
            assert f.filter(summary) is True                   # window elapsed -> summary
            assert summary.levelno == logging.WARNING
            assert "after 3 retry attempts" in summary.getMessage()

        def test_mic_retry_filter_count_is_cumulative(monkeypatch):
            # dedup_seconds=0 -> window always elapsed -> every attempt past the first is a summary
            f = daemon.MicRetryRateLimitFilter(dedup_seconds=0.0, summary_every=10_000)
            _fixed_clock(monkeypatch, 0.0)
            assert f.filter(_mic_retry_record()) is True                    # 1: first
            _fixed_clock(monkeypatch, 1.0); s = _mic_retry_record()
            assert f.filter(s) is True and "after 2 retry attempts" in s.getMessage()
            _fixed_clock(monkeypatch, 2.0); s = _mic_retry_record()
            assert f.filter(s) is True and "after 3 retry attempts" in s.getMessage()

        def test_extract_mic_retry_error_parses_message():
            assert daemon._extract_mic_retry_error(
                "Microphone connection failed: Selected device validation failed. Retrying..."
            ) == "Selected device validation failed"
            assert daemon._extract_mic_retry_error(
                "Microphone connection failed: boom. Retrying..."
            ) == "boom"
            assert daemon._extract_mic_retry_error("something else") == "something else"  # fallback
  - ADD the integration / idempotency test (CRITICAL #4/#5; GOTCHA #12 — snapshot+restore):
        def test_setup_logging_attaches_exactly_one_rate_limit_filter(monkeypatch):
            rt = logging.getLogger("realtimestt")
            saved = list(rt.filters)
            try:
                monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)  # don't touch root
                rt.filters[:] = []                                            # start clean
                daemon._setup_logging("INFO")
                matches = [f for f in rt.filters if isinstance(f, daemon.MicRetryRateLimitFilter)]
                assert len(matches) == 1
                # idempotent: a second call must NOT double-register (CRITICAL #4)
                daemon._setup_logging("DEBUG")
                matches = [f for f in rt.filters if isinstance(f, daemon.MicRetryRateLimitFilter)]
                assert len(matches) == 1
            finally:
                rt.filters[:] = saved                                         # restore global state
  - ADD the chokepoint test (empirically confirms CRITICAL #1 — one logger-level filter gates the
    handler; uses a throwaway logger name to avoid touching the global realtimestt logger):
        def test_rate_limit_filter_is_logger_level_chokepoint():
            captured = []

            class _Cap(logging.Handler):
                def emit(self, record):
                    captured.append(record)

            name = "voice_typing.test.micretry.chokepoint"
            log = logging.getLogger(name)
            log.handlers = [_Cap()]
            log.propagate = False
            log.setLevel(logging.DEBUG)
            log.addFilter(daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=20))
            for _ in range(25):
                log.error("Microphone connection failed: boom. Retrying...")
            # first occurrence (count=1) + summary at count=20 = exactly 2 records reach the handler
            assert len(captured) == 2
            assert captured[0].levelno == logging.ERROR                       # the first (full)
            assert "Microphone connection failed" in captured[0].getMessage()
            assert captured[1].levelno == logging.WARNING                     # the summary
            assert "after 20 retry attempts" in captured[1].getMessage()
  - DO NOT modify any existing test (the Layer B _setup_logging tests @998-1022 stay as-is; they
    still pass because they assert only on the basicConfig kwargs, and the filter attach is harmless).

Task 4: MODIFY README.md — one additive (Mode A) note in ## Logs, status, stopping
  - FIND the latency-line paragraph (~lines 222-223): 'At `log.level = "INFO"`, each typed utterance
    prints one structured latency line. At `"DEBUG"`, the raw monotonic timestamps are also logged.'
  - EDIT: insert ONE additive paragraph immediately AFTER it (before the blank line + 'Check live
    state and the resolved device:'):
        If the configured mic is unreachable, RealtimeSTT retries it roughly every 3 seconds. The
        daemon rate-limits that `Microphone connection failed ... Retrying` ERROR so the journal
        shows the full traceback once, then a single `WARNING` summary roughly once per minute
        (`Microphone still unavailable after N retry attempts (last error: ...)`). The retry itself
        still happens; only the repeated traceback log line is throttled. See
        [Wrong microphone](#wrong-microphone) and `voicectl status`'s `mic:` line to fix the source.
  - DO NOT restructure the section; DO NOT touch the S2-added `mic: ok` status example (@~239). Mode A.
  - (Optional: if a markdown linter complains about the anchor, use a plain `### Wrong microphone`
    reference instead of a link. The existing README uses H3 headings, so `#wrong-microphone` is the
    GitHub-style anchor for `### Wrong microphone`.)

Task 5: VALIDATE — run the Validation Loop L1–L5 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S3: rate-limit RealtimeSTT mic-retry traceback spam (logging.Filter on the realtimestt logger)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the single chokepoint: a Filter on the LOGGER (not a handler). CPython Logger.handle
# runs self.filter(record) BEFORE callHandlers; a False return drops the record before BOTH the
# logger's own handlers AND propagation to root. RealtimeSTT leaves propagate=True, so one
# addFilter covers every surface that reaches journald. (CRITICAL #1.)
target = logging.getLogger("realtimestt")
target.addFilter(MicRetryRateLimitFilter())   # gates console handler + root propagation

# PATTERN 2 — in-place record rewrite for the summary (documented + correct). Runs in filter() before
# formatting; clears BOTH exc_info and exc_text (exc_text is a cached traceback) and rewrites msg/args.
def _summarize_mic_retry(record, count, message):
    record.levelno = logging.WARNING
    record.levelname = "WARNING"
    record.exc_info = None
    record.exc_text = None                      # CRITICAL #2: clear the cache too
    record.msg = f"Microphone still unavailable after {count} retry attempts (last error: {_extract_mic_retry_error(message)})"
    record.args = ()

# PATTERN 3 — idempotent install (CRITICAL #4). addFilter uses __eq__ (identity) -> distinct instances
# both register; main() can call _setup_logging twice. Remove existing instances, then add ONE fresh.
def _install_mic_retry_rate_limiter(logger_name="realtimestt"):
    target = logging.getLogger(logger_name)
    for existing in [f for f in target.filters if isinstance(f, MicRetryRateLimitFilter)]:
        target.removeFilter(existing)
    target.addFilter(MicRetryRateLimitFilter())   # fresh counter, no stale state

# PATTERN 4 — match on getMessage() (robust), be transparent for non-matching records (counter clean).
def filter(self, record):
    message = record.getMessage()
    if "Microphone connection failed" not in message:
        return True            # unrelated: pass through, counter untouched (GOTCHA #9)
    ...
```

### Integration Points

```yaml
UPSTREAM — _setup_logging (the INPUT the contract names) + main():
  - _setup_logging @daemon.py:923-941 is the hook point; main() calls it @968 (config-load-fail
    fallback) and @972 (primary), BOTH before VoiceTypingDaemon(...)/build_recorder (@~983) constructs
    the recorder. So the filter is attached before RealtimeSTT's _configure_logger runs and before any
    retry loop can fire. RealtimeSTT's addHandler does NOT clear .filters, so the filter survives
    _configure_logger.

SIBLING — P1.M1.T2.S1 (detection; landing in parallel):
  - S1 adds _probe_mic + self._mic_ok/_mic_error to __init__/_arm. S3 does NOT read those attributes;
    S3 is purely a logging filter on the realtimestt logger. No interface coupling.

SIBLING — P1.M1.T2.S2 (surfacing; landing in parallel):
  - S2 adds mic_ok/mic_error to status_snapshot() + a mic: line in voicectl status, and edits two
    README spots (### Wrong microphone note @187 + the status example mic: ok @239). S3 edits a
    DIFFERENT README spot (the ## Logs, status, stopping latency paragraph @223) — disjoint from S2's
    README edits. S3 does NOT touch status_snapshot()/ctl.py. No line-level conflict.

SIBLING — P1.M1.T1.S1 (no_log_file; landed):
  - T1.S1 added no_log_file=True to _FIXED_KWARGS, removing the realtimestt FileHandler. The only
    handler on realtimestt is now the console StreamHandler (+ propagation to root). S3's single
    logger-level filter still covers both (CRITICAL #1), independent of the FileHandler's presence.

DOWNSTREAM — P1.M3.T1.S1 (changeset-level README sync):
  - S3 adds one additive note to ## Logs, status, stopping. P1.M3.T1.S1 does the FULL changeset README
    pass and may reword/consolidate; S3's note is the authoritative rate-limit content. No conflict.

PRODUCTION RUNTIME (daemon under systemd):
  - On mic failure, the worker emits "Microphone connection failed: <e>. Retrying..." (ERROR,
    exc_info=True) every ~3s. The filter: lets #1 through (one full traceback), suppresses #2..#19,
    emits a WARNING summary at #20 (~60s) and again ~every 60s thereafter. journald stays readable and
    actionable. The retry loop itself is unaffected (GOTCHA #7).

NO INTERFACE CHANGES:
  - VoiceTypingConfig / config.toml: no new field (dedup_seconds/summary_every are hardcoded
    defaults — tunable via code, not user config, matching the PRD §4.4 "fixed values" style).
  - control-socket protocol / ctl.py / status_snapshot: unchanged.
  - launch_daemon.sh / systemd unit / cuda_check: unchanged.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo
> root `/home/dustin/projects/voice-typing`. All gates are pure/unit: NO real mic, NO CUDA, NO
> systemd, NO real RealtimeSTT (the filter is exercised with constructed LogRecords + a throwaway
> logger).

### Level 1: The edits are in place (static + structural)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the class + 3 helpers exist; no new imports ---"
grep -q 'class MicRetryRateLimitFilter(logging.Filter)' voice_typing/daemon.py && echo "L1 PASS: filter class" || echo "L1 FAIL"
grep -q 'def _extract_mic_retry_error' voice_typing/daemon.py && grep -q 'def _summarize_mic_retry' voice_typing/daemon.py && grep -q 'def _install_mic_retry_rate_limiter' voice_typing/daemon.py && echo "L1 PASS: 3 helpers" || echo "L1 FAIL"
echo "--- _setup_logging appends the install call as its LAST statement ---"
.venv/bin/python - <<'PY'
import ast, inspect
from voice_typing import daemon
src = inspect.getsource(daemon._setup_logging)
assert '_install_mic_retry_rate_limiter("realtimestt")' in src, "install call missing from _setup_logging"
# it must come AFTER the basicConfig call (be the last statement)
assert src.index('_install_mic_retry_rate_limiter') > src.index('basicConfig'), "install must follow basicConfig"
print("L1 PASS: _setup_logging wires the filter after basicConfig")
PY
echo "--- no NEW module-top imports (logging @69 + time @76 already present) ---"
git diff -- voice_typing/daemon.py | grep -E '^\+\s*(import|from) ' && echo "L1 NOTE: a new import line appeared — verify it's needed (none should be)" || echo "L1 PASS: no new imports"
echo "--- README has the additive note ---"
grep -qi 'rate-limit\|rate limits\|still unavailable after\|summary' README.md && echo "L1 PASS: README notes the rate-limit" || echo "L1 FAIL: README not updated"
# Expected: class + 3 helpers present; _setup_logging appends the install AFTER basicConfig; no new
# imports; README mentions the rate-limited summary behavior.
```

### Level 2: Pure filter-logic unit tests (deterministic clock; no global logger)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "mic_retry_filter or extract_mic_retry_error"
# Expected: ALL selected PASS, specifically:
#   test_mic_retry_filter_passes_unrelated_records_untouched          (transparency + counter clean)
#   test_mic_retry_filter_first_occurrence_passes_through_unchanged   (first = full ERROR, unchanged)
#   test_mic_retry_filter_first_occurrence_preserves_traceback        (first keeps exc_info)
#   test_mic_retry_filter_suppresses_repeats_within_window            (2..19 -> False)
#   test_mic_retry_filter_summary_on_nth_occurrence                   (20 -> WARNING summary, no traceback)
#   test_mic_retry_filter_summary_after_dedup_window                  (elapsed window -> summary)
#   test_mic_retry_filter_count_is_cumulative                         (count persists; summary text has N)
#   test_extract_mic_retry_error_parses_message                       (prefix/suffix strip + fallback)
# These prove the contract: first-pass-through, within-window suppression, Nth/window summary,
# traceback clearing (exc_info AND exc_text), transparency for unrelated records, and the extractor.
```

### Level 3: Integration + chokepoint tests (_setup_logging wiring + the CPython guarantee)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "setup_logging_attaches_exactly_one_rate_limit_filter or rate_limit_filter_is_logger_level_chokepoint"
# Expected: BOTH PASS:
#   - the integration test: after _setup_logging (basicConfig mocked), realtimestt.filters has exactly
#     ONE MicRetryRateLimitFilter; a 2nd _setup_logging leaves exactly ONE (idempotent — CRITICAL #4).
#     The finally restores the global logger's filters (GOTCHA #12).
#   - the chokepoint test: 25 attempts with summary_every=20 -> exactly 2 records reach the capturing
#     handler (the first ERROR + the 20th WARNING summary). Empirically confirms CRITICAL #1 (one
#     logger-level filter gates the handler).
```

### Level 4: No regressions across the daemon suite (incl. the unchanged Layer B tests)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v
# Expected: ALL PASS. The existing Layer B _setup_logging tests (@998-1022) stay GREEN because they
# assert only on the basicConfig kwargs (the appended filter attach is harmless to them). The new
# S3 section is additive. Pay attention to:
#   - test_setup_logging_configures_stderr_at_level / test_setup_logging_passes_resolved_level (unchanged)
#   - all status_snapshot / _probe_mic (S1/S2) tests (untouched by S3)
echo "--- import purity still holds (daemon stays cheap; no heavy module leaked at import) ---"
.venv/bin/python - <<'PY'
import sys
import voice_typing.daemon
heavy = [m for m in ("torch", "ctranslate2", "RealtimeSTT", "pyaudio") if m in sys.modules]
assert not heavy, f"heavy modules imported at module load: {heavy}"
print("L4 PASS: importing daemon stays cheap (no torch/ctranslate2/RealtimeSTT/pyaudio at import)")
PY
```

### Level 5: Scope guards — only the intended files changed; no S1/S2/T1 territory; no new files

```bash
cd /home/dustin/projects/voice-typing
echo "--- S3 does NOT touch status_snapshot/ctl/__init__/_arm/_probe_mic/_FIXED_KWARGS (S1/S2/T1) ---"
git diff -- voice_typing/daemon.py | grep -E '^\+.*(def status_snapshot|def _probe_mic|"no_log_file"|mic_ok|mic_error)' && echo "L5 WARN: S1/S2/T1 territory edited" || echo "L5 PASS: no S1/S2/T1 territory in S3's diff"
echo "--- _setup_logging's basicConfig call itself UNCHANGED (only an appended call + docstring line) ---"
git diff -- voice_typing/daemon.py | grep -E '^[+-].*basicConfig|^[+-].*stream=sys.stderr|^[+-].*format=' | head
echo "--- only the 3 intended files changed (no new files) ---"
git status --short
echo "--- ctl.py / config.py / cuda_check.py / systemd / launch_daemon.sh untouched ---"
git diff --exit-code -- voice_typing/ctl.py voice_typing/config.py voice_typing/cuda_check.py systemd/ voice_typing/launch_daemon.sh && echo "L5 PASS: those files untouched" || echo "L5 NOTE: a file in that set changed — verify it's not S3's doing"
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/tasks.json plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md pyproject.toml config.toml && echo "L5 PASS: read-only files unchanged" || echo "L5 FAIL: a read-only file was modified"
# Expected: git status shows ONLY voice_typing/daemon.py, tests/test_daemon.py, README.md modified
# (no new files); no S1/S2/T1 territory in the daemon diff; ctl/config/cuda_check/systemd/launch_daemon
# untouched; read-only files unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: class + 3 helpers present; `_setup_logging` appends `_install_mic_retry_rate_limiter("realtimestt")` AFTER `basicConfig`; no new imports; README updated.
- [ ] L2: all 8 pure-logic tests PASS (transparency, first-passthrough, traceback-preserve, within-window suppression, Nth summary, window-elapsed summary, cumulative count, extractor).
- [ ] L3: integration test (exactly ONE filter, idempotent) + chokepoint test (25 attempts → 2 records) PASS.
- [ ] L4: full `tests/test_daemon.py` green; the unchanged Layer B tests still green; import purity holds.
- [ ] L5: only `daemon.py`/`test_daemon.py`/`README.md` changed; no S1/S2/T1 territory; read-only files unchanged.

### Feature Validation
- [ ] First "Microphone connection failed" record → `True`, UNCHANGED (full ERROR + traceback once).
- [ ] Subsequent within `dedup_seconds`, not a summary tick → `False` (dropped; no journal spam).
- [ ] On `count % summary_every == 0` OR elapsed window → `True`, record rewritten to WARNING summary, `exc_info is None`, `exc_text is None`, summary message present.
- [ ] Non-matching records → `True`, counter unchanged (transparent).
- [ ] One logger-level filter gates BOTH the logger's own handler AND propagation (chokepoint test).
- [ ] `_setup_logging` attaches exactly one filter; idempotent across repeated calls.

### Code Quality Validation
- [ ] `MicRetryRateLimitFilter` + helpers have docstrings citing bugfix Issue 2 / P1.M1.T2.S3 + the CPython rationale (chokepoint, exc_text cache, idempotency).
- [ ] `dedup_seconds`/`summary_every` defaults documented (60 s / 20 ≈ one summary per ~60 s at 3 s/retry).
- [ ] Defensive style matches `_resolve_log_level` / `LatencyLog` (the nearest stylistic models).
- [ ] No bare `python`/`pip`/`pytest` in commands (all `.venv/bin/...`).
- [ ] Test additions are ADDITIVE (new section); no existing test changed.

### Scope Boundary Validation
- [ ] `_setup_logging` is the only existing method edited (one appended call + one docstring line); the class/helpers are pure additions.
- [ ] No `status_snapshot()`/`ctl.py` (S2), no `__init__`/`_arm`/`_probe_mic` (S1), no `_FIXED_KWARGS` (T1.S1) edits.
- [ ] No real mic/CUDA/systemd/RealtimeSTT in any gate; the filter is exercised with constructed `LogRecord`s + a throwaway logger.
- [ ] No conflict with parallel S1/S2 (disjoint regions: S3 = `_setup_logging` + a new class/helpers block + a new test section + one README note).
- [ ] No new dependencies; no new files.

---

## Anti-Patterns to Avoid

- ❌ Don't attach the filter to a **handler** or to **root** — attach it to `logging.getLogger("realtimestt")` (the LOGGER). A handler-level filter misses one of the two emission paths (library console handler vs. root propagation); root over-reaches. The logger is the single chokepoint (CRITICAL #1; GOTCHA #15).
- ❌ Don't clear only `exc_info` on the summary path — clear **both** `exc_info` and `exc_text`. `exc_text` is a cached traceback that `Formatter.format` appends if truthy; leaving it stale still prints the traceback (CRITICAL #2).
- ❌ Don't make the attach contingent on `basicConfig` actually running — `basicConfig` is idempotent (a no-op under pytest caplog). Attach unconditionally as the LAST statement of `_setup_logging` (CRITICAL #5).
- ❌ Don't call `addFilter` without first removing existing instances — CPython `addFilter` uses `__eq__` (identity), so distinct instances double-register, and `main()` can call `_setup_logging` twice. Use the reset-then-add idempotent install (CRITICAL #4).
- ❌ Don't match on `record.msg` — match on `record.getMessage()` (robust for f-string and %-style calls). And don't increment the counter for non-matching records (GOTCHA #6/#9).
- ❌ Don't clear `exc_info` on the FIRST-occurrence path — count==1 must pass through UNCHANGED so the full traceback logs exactly once (GOTCHA #10).
- ❌ Don't use real `time.sleep` in tests — monkeypatch `daemon.time.monotonic` for a deterministic clock. And don't construct the global `realtimestt` logger in the logic tests — construct the filter directly + feed `LogRecord`s (hermetic) (GOTCHA #11/#12).
- ❌ Don't forget to snapshot+restore `logging.getLogger("realtimestt").filters` in the integration test — it's a process-global singleton (GOTCHA #12).
- ❌ Don't try to stop the actual ~3 s mic retry — a logging filter can only throttle the LOG line, not the worker-thread loop. The README note must say so (GOTCHA #7).
- ❌ Don't edit `status_snapshot()`/`ctl.py` (S2), `__init__`/`_arm`/`_probe_mic` (S1), or `_FIXED_KWARGS` (T1.S1) — S3 is the `_setup_logging` logger filter ONLY (GOTCHA #15).
- ❌ Don't run/restart the live systemd daemon as "verification" — the deterministic gates are the unit tests + the chokepoint test (GOTCHA #14).
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, `pyproject.toml`, or `config.toml` (READ-ONLY / owned by others).

---

## Confidence Score

**9/10** for one-pass implementation success. The change is small and surgical: one new
`logging.Filter` subclass (≈15 lines of logic) + 3 small pure helpers + one appended call in
`_setup_logging` + one README sentence + an additive test section. Every claim is verified against
the live repo + the installed RealtimeSTT wheel + CPython's `logging/__init__.py` (read directly):
the chokepoint-is-the-logger guarantee (CRITICAL #1), the in-place-mutate-permitted + clear-exc_text
requirement (CRITICAL #2/#3), the `__eq__`-double-register → idempotent-install need (CRITICAL #4),
and the exact edit sites / line numbers / test idioms / README anchor (§B of the research note). The
contract is highly prescriptive (`__init__(self, dedup_seconds=60)`, `_count`, `_last_seen`,
`filter(record)`, match `getMessage()`), and this PRP follows it literally while adding the two
robustness essentials the contract implies but doesn't spell out: clearing `exc_text` (not just
`exc_info`) and idempotent install.

The −1 residual risk is the **process-global `realtimestt` logger** in the integration test: if
snapshot/restore is mishandled, a filter (transparent for non-matching messages, but present) could
linger and interact with a later test that logs "Microphone connection failed". The PRP mitigates
this explicitly (the integration test restores `filters` in a finally — GOTCHA #12; the pure tests
never touch the global logger; the idempotent install resets the counter on re-call). No real
mic/CUDA/systemd/RealtimeSTT is needed for any gate. No merge conflict with the parallel S1/S2
subtasks is expected (disjoint regions: S3 = `_setup_logging` + a new helper/class block + a new test
section + one README note).

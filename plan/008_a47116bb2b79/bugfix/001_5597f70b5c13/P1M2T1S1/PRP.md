# PRP — P1.M2.T1.S1: Select exactly one callback across the recorder spawn boundary

## Goal

**Feature Goal**: Introduce a **private, feed-only `partial_source` selector** (`"plain"` | `"stabilized"`, default `"stabilized"`) threaded as **picklable data** through the entire recorder-build chain — `VoiceTypingDaemon` → `RecorderHost` → spawn args → `_worker_main` → `build_recorder`/`_construct`/`_build_callbacks` (both the normal AND the force_cpu CPU-fallback builds) — mapping to **exactly one** upstream callback key (`on_realtime_transcription_update` | `on_realtime_transcription_stabilized`), with the **actual installed key reported in the lab-ready provenance** (the `("ready", ...)` payload) and **invalid or ineffective selections rejected** (never a silent no-partial build). This is the R.8 foundation (BUG-002 remediation): the G5 paired comparison (S6) and final selection (P1.M2.T2.S3) need it, because RealtimeSTT 1.0.2 fires **both** callbacks in the same eligible decode and a parent monkeypatch cannot survive multiprocessing spawn.

**Deliverable** (2 source + 2 test files, TDD):
1. `voice_typing/daemon.py` — `_PARTIAL_SOURCES` map + `partial_source` param on `_build_callbacks`/`_construct`/`build_recorder` (+ the ineffective-selection rejection) + `VoiceTypingDaemon.__init__` keyword-only `partial_source` → `self._partial_source` → passed to the REAL RecorderHost in `_load_host` (fakes keep the old surface). `_PARTIAL_CALLBACK_ATTR` retained as the default key.
2. `voice_typing/recorder_host.py` — keyword-only `partial_source` on `__init__`, carried in the spawn `args` tuple, threaded to every `build_recorder` call in `_worker_main` (incl. the CPU-fallback retry), and `"partial_callback": <installed key>` added to the ready payload + exposed on the host. Docstrings updated (Mode A).
3. `tests/test_daemon.py` + `tests/test_recorder_host.py` — additive hermetic sections (mocked recorder_cls / Process / host / device resolution; no real models, no CUDA).

**Success Definition**:
- (a) Default `"stabilized"` everywhere → the callbacks dict and every build are **byte-identical to today** (the 8+ tests hardcoding `on_realtime_transcription_stabilized` stay green; stream-edit unchanged).
- (b) `partial_source="plain"` → the callbacks dict carries `on_realtime_transcription_update` and **NOT** the stabilized key (exactly one partial key, never both); the child's `("partial", {...})` relay shape/identity (R.5) is unchanged.
- (c) An invalid value raises `ValueError`; a selection whose key the signature filter DROPS raises `ValueError` from `_construct` (refuses a no-partial build).
- (d) The spawn `args` carry the selector (picklable str); `_worker_main` passes it to both build paths; the ready payload reports the installed key.
- (e) `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q` and `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q` → 0 failures beyond the documented baselines; no config/env/CLI knob added.

## User Persona

Not applicable (internal lab seam; DOCS: Mode A — `build_recorder`/`RecorderHost`/feed-input + ready-metadata docstrings document the contract; **no public config changes**).

## Why

- **R.8 is mandated and currently unmet.** PRD §4.2sexies R.8: "compare the earliest usable update callback against the stabilized one and choosing by VISIBLE word lag" — the validation hunt (BUG-002) confirmed only the laggy stabilized callback is wired (daemon.py:221) and the G5 gate FAILS on both routes (57-word backlog, sentence-end dumps, 12.6 s median). This task creates the *mechanism* to run that comparison; S4/S6 run it; P1.M2.T2.S3 ships the winner.
- **Spawn isolation forbids the naive fix.** external_deps.md (verified): RealtimeSTT 1.0.2 tries both callbacks in the same eligible decode, and multiprocessing spawn gives the child a fresh interpreter — a parent monkeypatch of `_PARTIAL_CALLBACK_ATTR` is not an experiment. The selector must travel as picklable constructor data (the doc's exact prescription).
- **Exactly-one + provenance are hard rules.** The doc mandates "Select exactly one callback for delivery before construction/load; no runtime swapping, double-delivery…" and "Actual selected source and device/cadence must be in the G5 provenance" — hence the exclusivity invariant and the ready-payload field.

## What

A private selector threaded end-to-end, defaulting to `"stabilized"` (both normal and CPU-fallback modes) so nothing changes until a lab override is passed. No production knob.

### Success Criteria

- [ ] `_PARTIAL_SOURCES = {"plain": "on_realtime_transcription_update", "stabilized": "on_realtime_transcription_stabilized"}`; `_PARTIAL_CALLBACK_ATTR` retained (== the stabilized value).
- [ ] `_build_callbacks(..., partial_source="stabilized")` default returns today's dict byte-identically; `"plain"` swaps the key; invalid → `ValueError`.
- [ ] `_construct` rejects a dropped (ineffective) selection; `build_recorder`/`RecorderHost.__init__`/`VoiceTypingDaemon.__init__` gain the keyword-only param; `_load_host` passes it to the real host only.
- [ ] The spawn args carry it; `_worker_main` threads it to BOTH build paths; the ready payload gains `partial_callback`; the host exposes it.
- [ ] New hermetic tests pin: exclusivity, default-identity, invalid+ineffective rejection, spawn carry, ready provenance, daemon pass-through, fakes-unchanged. Both suites stay at/under their documented baselines; only the 4 files change.

## All Needed Context

### Context Completeness Check

_Pass._ The verified wiring chain (every site with HEAD line numbers), the both-callbacks/spawn rationale, the two rejection semantics, the byte-identity constraint (8+ hardcoded-key tests), the R.5 relay invariant, the hermetic-mocking requirement, and the consumer handoff (S4/S6/T2.S3) are all below + in the research note.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S1/research/partial_source_selector.md
  why: "§1 why (both-callbacks + spawn). §2 the full wiring-chain table (every edit site). §3 the two rejections.
        §4 the invariants the tests must pin. §5 consumers. §6 scope."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/external_deps.md
  why: "The verified RealtimeSTT 1.0.2 callback facts (both fired in one eligible decode; stabilizer runs even
        plain-only; stabilized not gated on stable_delta) + the prescription: 'Select exactly one callback before
        construction/load; no runtime swapping, double-delivery… Keep the stream-edit callback unchanged. Actual
        selected source… must be in the G5 provenance' + 'Carry a private, picklable selector over the existing
        feed-only recorder build path and through both initial/CPU-fallback construction paths… no public config
        switch needed.'"
  critical: "start_callback_in_new_thread stays default False (inline dispatch) — do not touch it."
- file: voice_typing/daemon.py
  why: "_PARTIAL_CALLBACK_ATTR :221 (comment :219 already blesses the switch); _build_callbacks :327 (the _partial
        closure body must NOT change); _construct :397 (filter → reject); build_recorder :436; _load_host :~1096
        (the real-host call gets feed_input=/is_listening= — add partial_source= the same way; the host_factory
        fake call at the else-branch stays UNTOUCHED); VoiceTypingDaemon.__init__ (the feed_input seam precedent)."
  gotcha: "_PARTIAL_CALLBACK_ATTR must stay defined — tests/test_daemon.py hardcodes the stabilized KEY STRING at
           :337,346,414,424,446,1831-1845,3259; the default path must be byte-identical."
- file: voice_typing/recorder_host.py
  why: "__init__ :140 (keyword-only tail force_cpu/is_listening/feed_input — add partial_source the same way);
        spawn() :252 (the ctx.Process args tuple — picklable str); _worker_main (grep 'build_recorder' for EVERY
        call site incl. the force_cpu retry); the ready payload ('ready', {device,compute_type,model}) gains
        partial_callback; the .device property precedent for exposing it. The ('partial', {...}) R.5 relay is
        UNTOUCHED — only the upstream source key changes."
- file: tests/test_daemon.py
  why: "The _build_callbacks/_construct test region (~:230-460: _FakeFeedback, the _FakeRecorder(**kwargs)
        capture, the VAD-phase parametrized tests). New additive section mirrors them with partial_source cases."
- file: tests/test_recorder_host.py
  why: "The existing spawn/worker test patterns (Process/spawn-context mocking, _worker_main-level monkeypatching
        of build_recorder) — the new carry/provenance tests mirror them hermetically."
- file: PRD.md  # §4.2sexies R.8 (the comparison mandate) + R.1 (why: the visibility failure this enables fixing)
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T3S1/PRP.md  # parallel: docs-only (G1_BASELINE.md, AGENTS.md) — zero overlap
```

### Known Gotchas

```python
# CRITICAL #1 — DEFAULT MUST BE BYTE-IDENTICAL. partial_source="stabilized" must make _build_callbacks return
#   EXACTLY today's dict (8+ tests hardcode the stabilized key). Never emit both keys ("no two callbacks
#   delivering to one consumer") — the map yields exactly ONE per build.
# CRITICAL #2 — THE SELECTOR IS CONSTRUCTOR DATA, NOT A MONKEYPATCH. It must ride the spawn args (a picklable str)
#   into _worker_main, and _worker_main must pass it to EVERY build_recorder call — the normal build AND the
#   force_cpu CPU-fallback retry ("both initial/CPU-fallback construction paths").
# CRITICAL #3 — REJECT, DON'T FALL BACK. Invalid value -> ValueError in _build_callbacks; a selection whose key
#   _filter_kwargs_to_signature DROPPED -> ValueError in _construct ("refusing to build a recorder with no partial
#   callback"). The log-and-drop filter stays as-is for OTHER kwargs; the partial key is the one kwarg whose loss
#   is fatal. Build success ⟹ the key survived ⟹ the ready payload's partial_callback == the requested key.
# CRITICAL #4 — NO PRODUCTION KNOB: no config.py/config.toml/env/CLI. The daemon param is private keyword-only,
#   mirroring the feed_input lab seam; the fake host_factory path in _load_host stays UNTOUCHED (fakes keep the
#   old surface). Stream-edit stays stabilized after release.
# CRITICAL #5 — PRESERVE SEMANTICS: the _partial closure body (update_partial + note_partial + on_speech), the 3
#   VAD callbacks, and the child's ("partial", {text, utterance_id, session_gen}) relay identity are UNCHANGED —
#   only the upstream key name varies. start_callback_in_new_thread stays default False.
# GOTCHA #6 — HERMETIC TESTS ONLY: mock recorder_cls / the spawn Process / the host / CUDA-device resolution.
#   No real models, no CUDA, no live desktop (R.7). pytest>=9.1.1; full paths + functional `timeout` (AGENTS.md).
```

## Implementation Blueprint

### Implementation Tasks

```yaml
Task 1: ADD the failing tests FIRST (RED) — two additive hermetic sections.
  - tests/test_daemon.py (after the _build_callbacks/_construct region, ~:460):
    (a) default identity: `_build_callbacks(fb)` has the stabilized key AND lacks the plain key (and
        equals today's key-set — pins byte-identity).
    (b) plain swap: `_build_callbacks(fb, partial_source="plain")` has on_realtime_transcription_update,
        LACKS the stabilized key, and the closure still fires fb partials + on_speech (call it).
    (c) exactly-one: for each valid source, exactly one of the two keys is present.
    (d) invalid: `pytest.raises(ValueError)` for partial_source="loud" (and "STABILIZED" — no case folding).
    (e) ineffective: `_construct(cfg, fb, FakeClsLackingThePlainKey, partial_source="plain")` raises
        ValueError naming the dropped key; with a FakeCls accepting it, the filtered kwargs carry it.
        (Fakes: one with an explicit __init__ lacking the key — NOT a **kwargs fake, which passes everything.)
    (f) build_recorder signature smoke: `partial_source` param, default "stabilized" (mirror the existing
        callable/docstring smoke test).
    (g) daemon pass-through: VoiceTypingDaemon(..., partial_source="plain") stores it; _load_host passes it
        to the real RecorderHost only (host_factory=None path) — capture via a monkeypatched RecorderHost
        factory in the daemon module; the injected-fake path is unchanged.
  - tests/test_recorder_host.py:
    (h) __init__ stores partial_source (default "stabilized").
    (i) spawn carry: monkeypatch the spawn-context Process (or capture the args) -> the args tuple contains
        the selector string.
    (j) _worker_main threading: monkeypatch recorder_host's build_recorder lookup to capture kwargs ->
        partial_source reaches EVERY call, including the force_cpu retry (simulate the first build raising
        to exercise the fallback).
    (k) ready provenance: the ("ready", ...) payload includes partial_callback == the requested key.
  - RUN (RED): `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k partial_source` and the
    new test_recorder_host cases → they FAIL (no such param today).

Task 2: EDIT voice_typing/daemon.py (GREEN).
  - 2a: beside _PARTIAL_CALLBACK_ATTR (:221) add the map + keep the constant:
        _PARTIAL_SOURCES = {"plain": "on_realtime_transcription_update",
                            "stabilized": "on_realtime_transcription_stabilized"}
        (_PARTIAL_CALLBACK_ATTR stays "on_realtime_transcription_stabilized" == the default resolved key.)
  - 2b: _build_callbacks gains `partial_source: str = "stabilized"`; validate
        `if partial_source not in _PARTIAL_SOURCES: raise ValueError(f"partial_source expects 'plain' or 'stabilized', got {partial_source!r}")`;
        the returned dict's partial entry uses `_PARTIAL_SOURCES[partial_source]` as its key (the `_partial`
        closure body UNCHANGED). Update the docstring (Mode A): exactly-one mapping, default stabilized.
  - 2c: _construct + build_recorder gain `partial_source: str = "stabilized"`, threaded into _build_callbacks;
        in _construct AFTER `filtered = _filter_kwargs_to_signature(...)` add the ineffective-selection guard:
        `key = _PARTIAL_SOURCES[partial_source]; if key not in filtered: raise ValueError(f"partial_source={partial_source!r}: {key!r} was dropped by {recorder_cls.__name__}'s signature — refusing to build a recorder with no partial callback")`.
        Docstrings updated (Mode A).
  - 2d: VoiceTypingDaemon.__init__ gains keyword-only `partial_source: str = "stabilized"` ->
        `self._partial_source = partial_source` (mirror the feed_input seam comment); in _load_host add
        `partial_source=self._partial_source,` to the REAL RecorderHost call ONLY (the host_factory else-branch
        stays byte-identical).
  - DO NOT: touch start_callback_in_new_thread; emit both keys; mutate the closure bodies; add config/env/CLI.

Task 3: EDIT voice_typing/recorder_host.py (GREEN).
  - 3a: __init__ keyword-only tail gains `partial_source: str = "stabilized"` -> `self._partial_source`
        (comment: picklable str carried to the spawn child; lab seam like feed_input; default = production
        byte-identical).
  - 3b: spawn()'s ctx.Process args tuple gains `self._partial_source`.
  - 3c: _worker_main accepts it and passes `partial_source=...` to EVERY build_recorder call — the normal
        build AND the force_cpu retry (grep `build_recorder` in the file; keep both paths identical in
        selection).
  - 3d: the ready payload gains `"partial_callback": _daemon._PARTIAL_SOURCES[partial_source]` (the installed
        key; build success ⟹ it survived the filter per 2c); expose it on the host alongside .device (e.g. a
        `partial_callback` attribute set at ready). Update the module docstring's event-schema line + the
        RecorderHost/feed-input docstrings (Mode A).
  - DO NOT: change the ("partial", {...}) relay payload/identity; the VAD events; stop()/teardown.

Task 4: VALIDATE.
  - `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q` (0 failures beyond the documented
    20-case legacy baseline; the new cases pass).
  - `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q` (its documented baseline).
  - `timeout 150 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q` (no
    knob was added — config untouched, quick sanity).
  - `git status --short` -> ONLY daemon.py, recorder_host.py, test_daemon.py, test_recorder_host.py.
    Message if committed: "P1.M2.T1.S1: private partial_source selector across the spawn boundary (exactly-one
    callback, ready-payload provenance, reject ineffective selection; default stabilized)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — exactly-one mapping. The selector resolves to ONE upstream key; the callbacks dict carries it
# instead of the hardcoded constant; default "stabilized" reproduces today's dict byte-for-byte.
_PARTIAL_SOURCES = {"plain": "on_realtime_transcription_update",
                    "stabilized": "on_realtime_transcription_stabilized"}
if partial_source not in _PARTIAL_SOURCES:
    raise ValueError(f"partial_source expects 'plain' or 'stabilized', got {partial_source!r}")
return {_PARTIAL_SOURCES[partial_source]: _partial, "on_vad_detect_start": ..., ...}  # _partial body UNCHANGED

# PATTERN — reject the ineffective selection AFTER the signature filter (a no-partial build is broken, not drift):
key = _PARTIAL_SOURCES[partial_source]
if key not in filtered:
    raise ValueError(f"partial_source={partial_source!r}: {key!r} dropped by {recorder_cls.__name__} — "
                     "refusing to build a recorder with no partial callback")

# PATTERN — picklable carry across spawn (a parent monkeypatch dies in the fresh interpreter):
ctx.Process(target=_worker_main, args=(cfg, queues..., force_cpu, ..., self._partial_source))  # str is picklable
# _worker_main: build_recorder(..., partial_source=partial_source) on BOTH the normal and force_cpu paths;
# ready payload: {"device": ..., "compute_type": ..., "model": ..., "partial_callback": <installed key>}
```

### Integration Points

```yaml
DOWNSTREAM — the R.8 chain: P1.M2.T1.S4 (the route runner passes partial_source per arm to compare real builds),
  P1.M2.T1.S6 (the paired plain-vs-stabilized replay), P1.M2.T2.S3 (final selection; if it flips the default it
  flips _PARTIAL_CALLBACK_ATTR/_PARTIAL_SOURCES' default IN THE SAME CHANGE as the stream-edit decision — this
  task ships stabilized).
UNCHANGED: the _partial closure semantics, the VAD callbacks, the ("partial", {...}) R.5 relay identity,
  start_callback_in_new_thread (default False), config.py/config.toml (NO knob), ctl, bulk_controller,
  stream-edit behavior.
PARALLEL — P1.M1.T3.S1: docs-only (tests/G1_BASELINE.md, AGENTS.md) — zero file overlap.
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# RED first (Task 1 before Tasks 2-3): the new partial_source cases FAIL.
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k partial_source        # GREEN after
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q                          # documented baseline only
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py -q                   # documented baseline only
timeout 150 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q   # untouched
git status --short   # ONLY the 4 files
```

## Final Validation Checklist

- [ ] Default `"stabilized"` byte-identical (the 8+ hardcoded-key tests green; stream-edit unchanged).
- [ ] `"plain"` swaps to exactly one key; never both; closure + R.5 relay semantics preserved.
- [ ] Invalid → ValueError; dropped-key selection → ValueError (no silent no-partial build).
- [ ] Spawn args carry the selector; both child build paths receive it; ready payload reports `partial_callback`.
- [ ] No config/env/CLI knob; fakes/host_factory path untouched; hermetic tests only; only the 4 files changed.

## Anti-Patterns to Avoid

- ❌ Don't monkeypatch `_PARTIAL_CALLBACK_ATTR` in the parent and call it an experiment — spawn discards it; carry the str.
- ❌ Don't emit both callbacks ("no two callbacks delivering to one consumer") or register plain alongside stabilized.
- ❌ Don't silently fall back when the signature filter drops the chosen key — reject (ValueError).
- ❌ Don't change the default (stream-edit stays stabilized), add a config/env/CLI knob, or touch the fake-factory path.
- ❌ Don't alter the `_partial` closure body, the VAD callbacks, the R.5 relay payload, or `start_callback_in_new_thread`.
- ❌ Don't run real models/CUDA or touch the live desktop in tests (R.7); no pytest without `timeout`; no bare
  python/pytest (zsh aliases); no ruff/mypy.

---

## Confidence Score

**9/10** — the wiring chain is verified site-by-site (with the spawn/picklability rationale and the both-callbacks fact from external_deps.md), the default byte-identity constraint is pinned against the 8+ hardcoded-key tests, the two rejection semantics and the exactly-one/provenance invariants are explicit, and the parallel task is docs-only. The −1: `_worker_main`'s internal build sites (normal + force_cpu retry) were located by signature/grep rather than read line-by-line — the PRP directs the implementer to thread `partial_source` into EVERY `build_recorder` call found there (a mechanical, greppable step), and the _worker_main-level capture test verifies it.

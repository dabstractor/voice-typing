# PRP — P1.M1.T2.S1: Reconcile toggle/toggle_lite to mode-specific arming (delta §3.4) + tests

## Goal

**Feature Goal**: Fix lite-mode toggle semantics (architecture `system_context.md` §3.2 **BUG-B**, mandated by delta PRD §3.4 "toggle-lite semantics"). Today `toggle()` and `toggle_lite()` both gate purely on `self._listening.is_set()`: an armed press of **either** key disarms. Delta §3.4 mandates **mode-specific arming**: `toggle` disarms ONLY if armed-in-normal (otherwise arms/switches-to normal); `toggle_lite` disarms ONLY if armed-in-lite (otherwise arms/switches-to lite). So pressing F while armed-in-**normal** SWITCHES to lite (one bounded reload), and vice-versa — instead of disarming. The mode-switch reload machinery in `_load_host(mode)` is already correct (do not touch it); this subtask only changes the **toggle condition** + docstrings + the hypr-binds.conf comment, and adds the unit tests.

**Deliverable** (two files edited, no new files):
1. `voice_typing/daemon.py` — rewrite the `if disarmed:` condition in `toggle()` (L1343-1356) and `toggle_lite()` (L1359-1374) to a **mode-aware** check; refresh both docstrings.
2. `hypr-binds.conf` — update the header comment's behavior description (the "Both keys STOP when pressed while already listening … press the active key to stop, then the other" text describes the OLD deviating behavior; replace with the mode-specific "pressing the OTHER mode's key while armed switches modes" description).
3. `tests/test_daemon.py` — 6 unit tests (via the `_FakeHost`/`_fake_host_factory`/`_make_lazy_daemon` seam) pinning all six toggle×mode outcomes.

**Success Definition**:
- (a) `toggle()`: disarms iff `(listening and mode=="normal")`; else `_load_host("normal") + _arm()` (arms from idle, or switches from lite).
- (b) `toggle_lite()`: disarms iff `(listening and mode=="lite")`; else `_load_host("lite") + _arm()` (arms from idle, or switches from normal).
- (c) The read-act split is preserved: `self._listening` + `self._mode` read together under `_lock`, then `_load_host` called OUTSIDE `_lock` (it acquires `_lock` — nesting would deadlock).
- (d) `_load_host`'s mode-switch machinery is **untouched** (it already detects a wrong-mode resident, tears it down, respawns in the requested mode, sets `self._mode`).
- (e) The 6 new tests pass; existing toggle/idle/lazy-load tests stay green; `git diff` == `daemon.py` + `hypr-binds.conf` + `test_daemon.py`.

## User Persona

**Target User**: The user with both keybinds bound (SUPER+ALT+D = normal, SUPER+ALT+F = lite). They pick a mode for a stretch of use; today switching modes requires pressing the *active* key to stop, then the other to start. After this fix they press the *other* key directly to switch (one ~1–3 s reload) — fewer keystrokes, no ambiguity.

**Use Case**: User is dictating in normal mode (D), wants a quick URL → presses F → switches to lite (one reload, ~half VRAM, faster finals). Presses F again → disarms. Later presses D → normal. Each key only ever toggles its own mode on/off; the cross-mode press switches.

**Pain Points Addressed**: BUG-B — the current "both keys stop when armed" behavior contradicts delta §3.4 + the hypr-binds.conf comment (which the fix also corrects). Mode-switching is needlessly a two-press dance.

## Why

- **Delta §3.4 is the mandate.** "toggle-lite semantics (pin these down)" prescribes: `toggle_lite` disarms ONLY if armed-in-lite, otherwise arms in lite (pressing F while armed-in-normal SWITCHES — one reload); `toggle` mirrors for normal. The current code deviates (both gate on `_listening` alone) and the `hypr-binds.conf` header comment + the `toggle_lite` docstring describe the *deviation* as if intended. This subtask reconciles code + docs to the spec.
- **BUG-B (system_context.md §3.2) flagged it.** The lite-mode feature code is ~90% landed but this toggle-condition bug remained. It is one of the "confirmed spec bugs" blocking the lite-mode release.
- **The reload machinery is already correct — this is a small, surgical condition change.** `_load_host(mode)` already: detects a wrong-mode resident (`switch_mode`), tears it down (`_bounded_shutdown`), respawns in the requested mode, sets `self._mode`. So the fix is purely *which branch calls `_load_host` vs `_request_stop`* — no new teardown path, no new state. (PRD §4.2ter explicitly accepts the one-reload switch cost.)
- **Scope discipline.** This subtask owns ONLY the toggle condition + its docstrings + the hypr-binds comment + the unit tests. It does NOT touch `_load_host`/`_arm`/`_disarm`/`_request_stop`/`_mode` (already correct), does NOT touch `ctl.py`/socket dispatch/`status_snapshot` (P1.M1.T2.S2 owns the end-to-end mode verification), does NOT build the T7 feed-audio integration test (P1.M2.T1), and does NOT sync README/ACCEPTANCE (P1.M2.T2).

## What

Rewrite the toggle condition in both methods + refresh docstrings + the keybind comment + add 6 tests:

1. **`toggle()`**: read `(listening, mode)` under `_lock`; if `listening and mode == "normal"` → `_request_stop()`; else `_load_host("normal") + _arm()`.
2. **`toggle_lite()`**: read `(listening, mode)` under `_lock`; if `listening and mode == "lite"` → `_request_stop()`; else `_load_host("lite") + _arm()`.
3. **Docstrings** on both methods describe the mode-specific behavior (a key only toggles its own mode; the cross-mode press switches).
4. **hypr-binds.conf header** comment's behavior paragraph describes "pressing the OTHER mode's key while armed switches modes (one reload)" instead of the old "both keys stop; press active key to stop then the other".
5. **6 tests** (next section) via `_make_lazy_daemon(host_factory=…)`.

### Success Criteria

- [ ] `toggle()` condition is `listening and mode == "normal"` for disarm (not bare `_listening.is_set()`).
- [ ] `toggle_lite()` condition is `listening and mode == "lite"` for disarm.
- [ ] Both read `_listening` + `_mode` together under `_lock`, then call `_load_host` OUTSIDE `_lock`.
- [ ] `_load_host`/`_arm`/`_disarm`/`_request_stop`/`self._mode` machinery is UNCHANGED.
- [ ] `toggle_lite` + `toggle` docstrings describe mode-specific arming (cite delta §3.4).
- [ ] hypr-binds.conf comment no longer says "Both keys STOP when pressed while already listening"; describes the mode-switch behavior.
- [ ] 6 new tests pass; existing toggle/lazy-load/idle tests green; `git diff` == `daemon.py` + `hypr-binds.conf` + `test_daemon.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The verbatim current bodies of `toggle()` (L1343-1356) and `toggle_lite()` (L1359-1374), the `_load_host(mode)` mode-switch machinery (L686-780, confirmed correct + must-not-touch), the read-act-split + outside-`_lock` discipline, the `_FakeHost`/`_fake_host_factory`/`_make_lazy_daemon` test seam (incl. the `mode=None`-respects-kwarg detail), the `_request_stop` immediate-disarm-when-no-utterance-in-flight behavior (so disarm tests need no run loop), and the hypr-binds.conf comment text are all verified below with line citations. A developer new to this repo can implement this from the PRP alone.

### Documentation & References

```yaml
# MUST READ — the mandate (mode-specific arming semantics)
- docfile: plan/004_607e9cca32b7/delta_prd.md
  why: §3.4 "toggle-lite semantics (pin these down)" prescribes the mode-aware condition: toggle_lite
       disarms ONLY if armed-in-lite (else arms/switches-to lite); toggle mirrors for normal. Pressing
       the other mode's key while armed SWITCHES (one reload).
  critical: "The condition changes from `disarmed = self._listening.is_set()` to a mode-aware check.
            The cross-mode press must SWITCH (route to _load_host), NOT disarm."

# MUST READ — the bug + the "machinery is correct, don't touch it" note
- docfile: plan/004_607e9cca32b7/architecture/system_context.md
  why: §3.2 BUG-B documents the deviation (both keys gate on _listening alone). §3.1 DONE table row
       confirms _load_host's mode-switch (switch_mode detection, teardown-then-respawn, self._mode=mode)
       is LANDED + correct. The contract: "The mode-switch reload machinery in _load_host is already
       correct (do not touch it)."
  critical: "Do NOT edit _load_host. It already handles resident-wrong-mode → teardown + respawn in the
            requested mode + sets self._mode. The toggle change only decides WHETHER to call it."

# THE EDIT SITE — the two methods (verbatim current bodies)
- file: voice_typing/daemon.py
  why: toggle() L1343-1356 and toggle_lite() L1359-1374. Both currently: `with self._lock: disarmed =
        self._listening.is_set()` then `if disarmed: self._request_stop() else: _load_host(mode)+_arm()`.
        self._mode is the resident mode ("normal"|"lite", set by _load_host on success L754). threading
        + _lock already in scope.
  pattern: "Read TWO values (listening + mode) under ONE _lock critical section (the contract's
            'read-act split'), then act. _load_host OUTSIDE _lock (it acquire-release-reacquires _lock
            — nesting deadlocks); _arm INSIDE _lock (re-acquire). Mirror the existing structure."
  gotcha: "self._mode reflects the RESIDENT child's mode (set by _load_host). When idle (no child),
           _mode is its last value (or 'normal' at boot) — but idle always takes the arm/switch branch
           anyway (listening is False), so the idle _mode value is irrelevant to the decision. Good."

# THE MACHINERY TO REUSE (READ-ONLY) — why the switch 'just works'
- file: voice_typing/daemon.py
  why: _load_host(mode) L686-780. Fast path: resident + alive + SAME mode → instant True. Switch path:
        resident + alive + OTHER mode → switch_mode=True → `with _lock: _bounded_shutdown(timeout=5.0);
        self._host=None; self._models_loaded=False` → spawn new child with mode=mode → `self._mode=mode`.
        So toggle_lite-while-armed-in-normal → _load_host("lite") tears down normal + spawns lite +
        sets _mode="lite"; the following _arm() re-arms. EXACTLY the delta §3.4 switch semantics.
  critical: "REUSE this. Do not write a second teardown/switch path. The only edit is the toggle
            CONDITION routing the cross-mode press to _load_host instead of _request_stop."

# THE COMMENT TO FIX — describes the OLD deviating behavior
- file: hypr-binds.conf
  why: The header comment's behavior paragraph currently says: 'Both keys STOP when pressed while
        already listening, so to switch modes: press the active key to stop, then the other key to
        start in its mode.' That describes BUG-B's deviation. After the fix, pressing the OTHER mode's
        key while armed SWITCHES (one reload) — the comment must say so (Mode A: this comment IS the
        hotkey doc).
  critical: "Replace the 'Both keys STOP … press active key to stop then the other' sentence with the
            mode-specific description. Keep the rest of the comment (integration/precedence/mods) intact."

# THE TEST SEAM — fakes + factory + lazy daemon builder
- file: tests/test_daemon.py
  why: _FakeHost L510 (has .mode, .spawn_calls, .stop_calls, wraps _StubRecorder; ctor takes mode=);
        _fake_host_factory(spawn_result, device, mode) L579 — NOTE: with mode=None (the DEFAULT) the
        factory respects the `mode` kwarg passed by _load_host (the closure-override at L589 only fires
        when mode is explicitly passed). _make_lazy_daemon(cfg, host_factory) L2663 builds a production-
        like lazy daemon (recorder=None, host_factory=, mic_prober=_ok_probe). Existing toggle tests
        L932-953 + lazy-load tests L2686+ show the patterns. _request_stop (L1035) disarms IMMEDIATELY
        when _text_in_flight is clear (no run loop needed for the disarm tests).
  pattern: "Build a spawn-tracking factory (append each _FakeHost to a list) so 'one reload' =
            len(spawns)==2. Arm via d.start()/d.start_lite() (no run loop → _text_in_flight stays clear
            → _request_stop disarms immediately). Assert d._mode, d.is_listening(), d._host.mode."
  critical: "Use _fake_host_factory() with NO mode arg (mode=None default) so the resident host's .mode
            reflects what _load_host requested — REQUIRED for the switch tests (a forced mode would
            break the mode-mismatch detection). For the idle/_mode boot value, _make_lazy_daemon boots
            _mode='normal'."

# THE PARALLEL ITEM (no-conflict boundary)
- docfile: plan/004_607e9cca32b7/P1M1T1S2/PRP.md
  why: T1.S2 (parallel) adds kwargs×mode×force_cpu + config tests to test_daemon.py + test_config.py.
        It does NOT touch toggle/toggle_lite/hypr-binds.conf. T2.S1 (this) edits toggle logic + the
        keybind comment + adds toggle-semantics tests. Distinct edit sites; both ADD tests to
        test_daemon.py (additive, no overlap).
  critical: "No conflict. T1.S2 = construction-layer (cfg_to_kwargs/AsrConfig) tests; T2.S1 = toggle-
            semantics tests. Different daemon.py methods, different test functions."
```

### Current Codebase tree (relevant slice — lite feature ~90% landed; T1.S1 CPU-fix Complete; T1.S2 parallel)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py          # toggle @1343-1356; toggle_lite @1359-1374; _load_host @686-780 (REUSE);
│   │                        # _arm @969; _disarm @984; _request_stop @1035; self._mode @632/+754. EDIT toggle+docstrings.
├── hypr-binds.conf        # header comment describes OLD 'both keys stop' behavior. EDIT the behavior paragraph.
└── tests/
    └── test_daemon.py     # _FakeHost @510; _fake_host_factory @579; _make_lazy_daemon @2663. ADD 6 tests.
```

### Desired Codebase tree with files to be added/changed

```bash
voice_typing/daemon.py     # MODIFY: toggle() + toggle_lite() conditions (mode-aware) + docstrings. NO other method.
hypr-binds.conf            # MODIFY: header comment behavior paragraph (mode-switch description).
tests/test_daemon.py       # MODIFY: +6 toggle×mode tests (+ a spawn-tracking factory helper if needed). NO new files.
# No _load_host/_arm/_disarm/_request_stop/ctl.py/socket/config/recorder_host changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — READ _listening AND _mode TOGETHER UNDER ONE _lock. The contract's "read-act split":
# snapshot both values in one critical section, release, then act. Reading them in two separate
# `with self._lock:` blocks would be a TOCTOU (mode could change between reads). One read, then act.

# CRITICAL #2 — _load_host MUST RUN OUTSIDE _lock. It acquire-release-reacquires self._lock (the
# single-flight _load_cond wait + the publish block). Calling it while holding _lock deadlocks.
# _arm() is then re-acquired under _lock. This is the EXISTING structure in toggle/toggle_lite —
# preserve it (the only change is the condition, not the lock discipline).

# CRITICAL #3 — THE CONDITION IS mode-AWARE, NOT listening-ALONE. The BUG-B fix: `toggle` disarms
# iff (listening AND mode=="normal"); `toggle_lite` disarms iff (listening AND mode=="lite"). The
# cross-mode armed press (e.g. toggle_lite while armed-in-normal) takes the ELSE branch → _load_host
# → mode-switch reload → _arm. Do NOT keep the bare `_listening.is_set()` check.

# CRITICAL #4 — DO NOT TOUCH _load_host / _arm / _disarm / _request_stop / self._mode. They are
# correct (system_context.md §3.1 DONE). _load_host already does mode-mismatch detection + teardown
# + respawn + self._mode=mode. _arm already calls set_mode(self._mode). The toggle change ONLY
# re-routes the cross-mode press from _request_stop to _load_host. Editing the machinery = scope creep
# + risks T2.S2's verification.

# CRITICAL #5 — CONCURRENCY NOTE (flag for T2.S2, do NOT fix here): the BUG-B fix is the FIRST time
# _load_host is called while _listening is SET (the mode-switch-while-armed case). _load_host's
# comment says it is "only called while NOT listening" (true for start*/idle-unload today). When the
# switch tears down the resident child, the run() loop's dead-host check (daemon.py L831, which runs
# BEFORE the _listening check) MAY fire spuriously on the killed resident ("recorder-host child died
# unexpectedly"). The end state is still correct (_load_host's success path clears _load_error, sets
# _mode, and _arm re-sets _listening), but it can emit a confusing log line mid-switch. The UNIT tests
# here do NOT run the run() loop, so they don't exercise this; T2.S2 ("Verify + test mode-switch
# reload") owns the live/concurrent verification. Do NOT add a workaround in this subtask — flag it.

# GOTCHA #6 — _request_stop DISARMS IMMEDIATELY when no utterance is in flight (_text_in_flight clear).
# The unit tests don't run the run() loop, so _text_in_flight stays clear → toggle-off → _request_stop
# → immediate _disarm → d.is_listening() is False right after. So the disarm-branch tests are clean
# (no drain wait). (Mirror test_toggle_on_to_off_disarms which sets _text_in_flight only to make
# abort() valid — not needed here since we assert _listening, not abort.)

# GOTCHA #7 — USE _fake_host_factory() WITH NO mode ARG. The factory's closure overrides host.mode
# ONLY when mode is explicitly passed (L589 `if mode is not None`). With the default mode=None, the
# `mode` kwarg from _load_host flows through to _FakeHost(...) and sets host.mode correctly. A forced
# mode would break the switch test (_load_host's mismatch detection would never see wrong-mode). For
# counting reloads, wrap the factory to append each host to a list (len(spawns) == total spawns).

# GOTCHA #8 — _make_lazy_daemon BOOTS _mode="normal" + _host=None. So an idle daemon is _mode="normal",
# not listening, no host. d.start() loads normal + arms (mode="normal"). d.start_lite() loads lite +
# arms (mode="lite"). These are the setup primitives for the 6 tests.

# GOTCHA #9 — DON'T CONFUSE d._mode WITH d._host.mode. d._mode is the daemon's record of the resident
# child's mode (set by _load_host on success). d._host.mode is the host object's own mode attribute.
# After a successful load they agree. Assert BOTH in the switch tests (d._mode == "lite" AND
# d._host.mode == "lite") to pin the resident mode end-to-end.

# GOTCHA #10 — FULL PATHS. `.venv/bin/python -m pytest` (machine aliases python3->uv run). No
# ruff/mypy configured in this project — don't invoke them.
```

## Implementation Blueprint

### Data models and structure

None. No new state. `self._mode` already exists ("normal"|"lite", set by `_load_host`). The only change is the toggle *condition* (a boolean expression) + docstring/comment text + tests.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/daemon.py — toggle() mode-aware condition + docstring
  - FIND toggle() (L1343-1356). Current body:
        def toggle(self) -> None:
            # NORMAL-mode toggle (PRD §4.2ter). ...
            with self._lock:
                disarmed = self._listening.is_set()
            if disarmed:
                self._request_stop()
            else:
                if not self._load_host("normal"):
                    return  # load failed → stay unarmed
                with self._lock:
                    self._arm()
  - EDIT: make the condition mode-aware (read BOTH under one _lock) + refresh the docstring:
        def toggle(self) -> None:
            """NORMAL-mode toggle (PRD §4.2ter / delta §3.4): mode-specific arming.

            Disarms ONLY if currently armed in NORMAL; otherwise arms in normal. So: pressing D while
            idle arms in normal; pressing D while armed-in-normal disarms; pressing D while armed-in
            LITE switches to normal (one bounded reload — the same mode-switch _load_host uses). Each
            key only ever toggles its own mode on/off; the cross-mode press switches (one reload).
            """
            with self._lock:
                listening = self._listening.is_set()
                mode = self._mode
            if listening and mode == "normal":
                self._request_stop()           # armed-in-normal → disarm
            else:
                # idle, OR armed-in-lite → arm in normal (switch from lite = one reload via _load_host)
                if not self._load_host("normal"):
                    return  # load failed → stay unarmed
                with self._lock:
                    self._arm()
  - WHY: `listening and mode == "normal"` is the mode-aware disarm condition (CRITICAL #3). Reading
    both under one _lock is the read-act split (CRITICAL #1). _load_host stays outside _lock (CRITICAL #2).
  - DO NOT: keep the bare `_listening.is_set()` check; touch _load_host/_arm/_request_stop; change the
    lock structure.

Task 2: MODIFY voice_typing/daemon.py — toggle_lite() mode-aware condition + docstring
  - FIND toggle_lite() (L1359-1374). Current body + docstring (the docstring describes the OLD
    "pressing F while listening (in EITHER mode) stops" deviation).
  - EDIT: mirror Task 1 for lite:
        def toggle_lite(self) -> None:
            """LITE-mode toggle (PRD §4.2ter / delta §3.4): mode-specific arming.

            Disarms ONLY if currently armed in LITE; otherwise arms in lite. So: pressing F while idle
            arms in lite; pressing F while armed-in-lite disarms; pressing F while armed-in NORMAL
            switches to lite (one bounded reload — the same mode-switch _load_host uses). Each key only
            ever toggles its own mode on/off; the cross-mode press switches (one reload).
            """
            with self._lock:
                listening = self._listening.is_set()
                mode = self._mode
            if listening and mode == "lite":
                self._request_stop()           # armed-in-lite → disarm
            else:
                # idle, OR armed-in-normal → arm in lite (switch from normal = one reload via _load_host)
                if not self._load_host("lite"):
                    return  # load failed → stay unarmed
                with self._lock:
                    self._arm()
  - DO NOT: touch _load_host/_arm/_request_stop; change the lock structure.

Task 3: MODIFY hypr-binds.conf — header comment behavior paragraph (Mode A doc)
  - FIND the behavior paragraph in the header comment (the lines reading):
        #  listening on/off. Switching modes (D after F, or F after D) reloads the model set (~1–3 s).
        #  Both keys STOP when pressed while already listening, so to switch modes: press the active
        #  key to stop, then the other key to start in its mode.
  - EDIT: replace the "Both keys STOP … press the active key to stop, then the other" description with
    the mode-specific behavior:
        #  Each key toggles listening on/off IN ITS OWN MODE: pressing D while armed-in-normal (or idle)
        #  toggles normal; pressing F while armed-in-lite (or idle) toggles lite. Pressing the OTHER
        #  mode's key while armed SWITCHES modes (one bounded ~1–3 s reload) — e.g. press F while
        #  armed-in-normal to switch to lite. You never need to stop first to change modes.
  - WHY: the old text documents BUG-B's deviation; Mode A says this comment IS the hotkey doc.
  - DO NOT: touch the binds themselves, the integration/precedence/mods sections, or the SUPER+ALT+D/F
    bind lines.

Task 4: ADD tests/test_daemon.py — 6 toggle×mode tests (via _make_lazy_daemon + a spawn-tracking factory)
  - PLACE: a new section among the toggle tests (near L932-953) OR after the lazy-load tests (~L2700+),
    under a banner:
        # ===========================================================================
        # P1.M1.T2.S1 — toggle/toggle_lite mode-specific arming (delta §3.4 / BUG-B)
        # (Each key toggles its own mode; cross-mode press switches = one reload.)
        # ===========================================================================
  - ADD a spawn-tracking factory helper + the 6 tests. Reference implementation (copy-ready; reuses
    _FakeHost / _make_lazy_daemon / _fake_host_factory from the file; threading/time not needed here):

        def _spawning_factory(spawns):
            """A host_factory that appends each built _FakeHost to `spawns` (so reloads are countable)
            and respects the `mode` kwarg _load_host passes (no closure override)."""
            def factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
                host = _FakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)
                spawns.append(host)
                return host
            return factory

        def test_toggle_lite_while_idle_arms_in_lite():
            """F while idle → arms in lite (mode becomes lite, one spawn)."""
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            assert not d.is_listening() and d._mode == "normal"
            d.toggle_lite()
            assert d.is_listening() is True
            assert d._mode == "lite"
            assert d._host.mode == "lite"
            assert len(spawns) == 1                      # armed once (no reload from idle)

        def test_toggle_lite_while_armed_in_lite_disarms():
            """F while armed-in-lite → disarms (no reload)."""
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.start_lite()                               # arm in lite
            assert d._mode == "lite" and d.is_listening()
            d.toggle_lite()                              # armed-in-lite → disarm
            assert d.is_listening() is False
            assert len(spawns) == 1                      # no reload on a same-mode disarm

        def test_toggle_lite_while_armed_in_normal_switches_to_lite():
            """BUG-B fix: F while armed-in-NORMAL → switches to lite (exactly ONE reload)."""
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.start()                                    # arm in normal
            assert d._mode == "normal" and d.is_listening()
            d.toggle_lite()                              # cross-mode press → switch (not disarm!)
            assert d.is_listening() is True              # re-armed in lite (not disarmed)
            assert d._mode == "lite"
            assert d._host.mode == "lite"
            assert len(spawns) == 2                      # normal spawn + ONE lite reload

        def test_toggle_while_idle_arms_in_normal():
            """D while idle → arms in normal (mode becomes normal, one spawn)."""
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.toggle()
            assert d.is_listening() is True
            assert d._mode == "normal"
            assert d._host.mode == "normal"
            assert len(spawns) == 1

        def test_toggle_while_armed_in_normal_disarms():
            """D while armed-in-normal → disarms (no reload)."""
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.start()                                    # arm in normal
            d.toggle()                                   # armed-in-normal → disarm
            assert d.is_listening() is False
            assert len(spawns) == 1

        def test_toggle_while_armed_in_lite_switches_to_normal():
            """BUG-B fix: D while armed-in-LITE → switches to normal (exactly ONE reload)."""
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.start_lite()                               # arm in lite
            assert d._mode == "lite" and d.is_listening()
            d.toggle()                                   # cross-mode press → switch (not disarm!)
            assert d.is_listening() is True              # re-armed in normal (not disarmed)
            assert d._mode == "normal"
            assert d._host.mode == "normal"
            assert len(spawns) == 2                      # lite spawn + ONE normal reload
  - CONSTRAINTS:
      * The `_spawning_factory` respects the `mode` kwarg (no closure override) — REQUIRED for the
        switch tests (Gotcha #7).
      * Arm via d.start()/d.start_lite() (no run loop → _text_in_flight clear → _request_stop disarms
        immediately → the disarm-branch tests are clean; Gotcha #6).
      * Assert d._mode AND d._host.mode in the switch tests (Gotcha #9). Assert len(spawns) for the
        reload count (2 = one switch reload; 1 = no reload).
      * Reuse _FakeHost / _make_lazy_daemon (no new imports).
      * Do NOT run a real run() loop (the dead-host-detection concurrency is T2.S2's scope — Gotcha #5).

Task 5: VALIDATE — run the Validation Loop L1–L4; fix until green. No git commit unless the orchestrator
  directs it. If asked, message:
  "P1.M1.T2.S1: reconcile toggle/toggle_lite to mode-specific arming (delta §3.4 / BUG-B) + tests".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the mode-aware condition (the whole fix). Read both under one _lock; the cross-mode
# armed press routes to _load_host (switch), NOT _request_stop (disarm):
#   with self._lock:
#       listening = self._listening.is_set()
#       mode = self._mode
#   if listening and mode == <this key's mode>:   # armed-in-OWN-mode → disarm
#       self._request_stop()
#   else:                                          # idle OR armed-in-OTHER-mode → arm/switch
#       if not self._load_host(<this key's mode>): return
#       with self._lock: self._arm()

# PATTERN 2 — _load_host ALREADY does the switch. When the resident child is the OTHER mode,
# _load_host(mode) detects switch_mode, tears the resident down (_bounded_shutdown), respawns in the
# requested mode, and sets self._mode. So toggle_lite-while-armed-in-normal → _load_host("lite") does
# the entire normal→lite switch; the following _arm() just flips listening + set_microphone(True) on
# the new lite child. No new teardown path. (PRD §4.2ter accepts the one-reload switch cost.)

# PATTERN 3 — the spawn-tracking test factory. _fake_host_factory() with mode=None respects the kwarg,
# but to COUNT reloads you need to observe every spawned host. A factory that appends to a list makes
# "one reload" = len(spawns)==2 (deterministic, no timing). The switch is the load-bearing assertion;
# d._mode + d._host.mode pin the resident mode end-to-end.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T2.S2 (Verify + test mode-switch reload, set_mode, status_snapshot, socket, ctl, status.sh):
  - T2.S2 owns the END-TO-END mode verification: the live/concurrent mode-switch reload (the dead-host-
    detection interaction flagged in Gotcha #5), status_snapshot's "mode" field, socket dispatch of
    toggle-lite/start-lite, ctl.py rendering, status.sh. T2.S1 (this) provides the toggle-LOGIC fix +
    unit tests; T2.S2 verifies the full path. The CONCURRENCY NOTE (Gotcha #5) is T2.S2's to confirm.

CONTROL SOCKET + ctl.py (UNCHANGED by T2.S1):
  - ControlServer._dispatch already routes "toggle"/"toggle-lite" to d.toggle()/d.toggle_lite()
    (system_context §3.1 DONE). ctl.py already has toggle-lite/start-lite in _COMMANDS + reads "mode".
    T2.S1 changes the methods' BEHAVIOR; the dispatch/wiring is already correct. No ctl.py/socket edit.

_mode / status (UNCHANGED by T2.S1):
  - self._mode is set by _load_host (L754); status_snapshot already includes "mode": self._mode
    (L1488); _arm already calls set_mode(self._mode) (L980). All correct; T2.S1 doesn't touch them.

NO INTERFACE CHANGES beyond the toggle behavior:
  - config.toml, systemd unit, recorder_host.py, feedback.py, ctl.py: UNCHANGED.
  - The toggle/toggle_lite SIGNATURES are unchanged (no new params).
  - hypr-binds.conf binds (SUPER+ALT+D/F) UNCHANGED — only the descriptive comment.
```

## Validation Loop

> Full paths (machine aliases python3→uv run). All gates are FAST unit tests with fakes — NO GPU /
> models / real child / run loop / network. No ruff/mypy configured. Reuse the file's existing seam.

### Level 1: The edits are in place + daemon.py parses

```bash
cd /home/dustin/projects/voice-typing
echo "--- toggle() condition is mode-aware (not bare _listening) ---"
grep -nA2 'def toggle(self)' voice_typing/daemon.py | grep -q 'mode == "normal"' && echo "L1 PASS: toggle mode-aware" || echo "L1 FAIL"
grep -nA2 'def toggle_lite(self)' voice_typing/daemon.py | grep -q 'mode == "lite"' && echo "L1 PASS: toggle_lite mode-aware" || echo "L1 FAIL"
echo "--- both read _listening + _mode under one _lock ---"
awk '/def toggle\(self\)|def toggle_lite\(self\)/{f=1} f&&/with self._lock:/{l=1} f&&l&&/_listening.is_set()/{a=1} f&&l&&a&&/self._mode/{print "L1 PASS: joint read"; exit}' voice_typing/daemon.py
echo "--- _load_host/_arm/_disarm/_request_stop UNCHANGED (grep line counts stable) ---"
grep -c 'def _load_host\|def _arm\|def _disarm\|def _request_stop' voice_typing/daemon.py
echo "--- hypr-binds.conf no longer says 'Both keys STOP' ---"
grep -q 'Both keys STOP' hypr-binds.conf && echo "L1 FAIL: stale BUG-B comment remains" || echo "L1 PASS: stale comment gone"
grep -q 'SWITCHES modes' hypr-binds.conf && echo "L1 PASS: mode-switch description present" || echo "L1 FAIL"
echo "--- daemon.py parses ---"
.venv/bin/python -c "import ast; ast.parse(open('voice_typing/daemon.py').read()); print('L1 PASS: parses')"
# Expected: both conditions mode-aware; joint _lock read; 4 method defs still present; stale hypr
# comment gone + new description present; daemon.py parses.
```

### Level 2: The 6 new toggle×mode tests pass (the deterministic proof)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "toggle_lite_while_idle or toggle_lite_while_armed_in_lite or toggle_lite_while_armed_in_normal or toggle_while_idle or toggle_while_armed_in_normal or toggle_while_armed_in_lite"
# Expected: 6 PASSED. The load-bearing BUG-B-fix tests:
#   test_toggle_lite_while_armed_in_normal_switches_to_lite  -> len(spawns)==2 + mode lite + listening
#   test_toggle_while_armed_in_lite_switches_to_normal       -> len(spawns)==2 + mode normal + listening
# If a switch test shows len(spawns)==1: the cross-mode press took the DISARM branch (the condition is
# still bare _listening) — re-check Task 1/2. If it shows d._host.mode unchanged: the factory forced a
# mode (re-check _spawning_factory respects the kwarg — Gotcha #7).
```

### Level 3: No regression — existing toggle/lazy-load/idle tests green

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v 2>&1 | tail -8
echo "--- specifically the existing toggle tests still green ---"
.venv/bin/python -m pytest tests/test_daemon.py -k "toggle or lazy or idle or load_host" -v 2>&1 | tail -20
# Expected: full suite green. The existing test_toggle_off_to_on_arms / test_toggle_on_to_off_disarms /
# test_toggle_is_an_invololution still pass (they use the legacy _make_daemon() stub path where _mode
# is "normal" by default, so toggle-on→arm-normal + toggle-off→disarm is unchanged). The lazy-load /
# idle-unload tests pass (_load_host untouched). If an existing toggle test fails, it likely asserted
# the OLD bare-_listening behavior — update it to the mode-aware semantics.
```

### Level 4: Scope — only daemon.py + hypr-binds.conf + test_daemon.py changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY the 3 files ---"
git diff --name-only | grep -vxE 'voice_typing/daemon.py|hypr-binds.conf|tests/test_daemon.py' && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only daemon.py + hypr-binds.conf + test_daemon.py"
echo "--- _load_host/_arm/_disarm/_request_stop bodies UNCHANGED (diff does not touch them) ---"
git diff voice_typing/daemon.py | grep -nE '^[+-].*(def _load_host|def _arm|def _disarm|def _request_stop|self._mode = mode|switch_mode)' && echo "L4 FAIL: machinery touched (out of scope)" || echo "L4 PASS: toggle machinery untouched"
echo "--- sibling/scope files UNTOUCHED ---"
git diff --quiet voice_typing/recorder_host.py voice_typing/ctl.py voice_typing/config.py config.toml systemd/voice-typing.service install.sh \
  && echo "L4 PASS: sibling files unchanged" || echo "L4 FAIL: a scope file was modified"
# Expected: diff = the 3 files only; the diff does NOT add/remove any _load_host/_arm/_disarm/
# _request_stop/_mode/switch_mode line; recorder_host/ctl/config/unit/install.sh unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: both toggle conditions mode-aware; joint `_listening`+`_mode` read under one `_lock`; `_load_host`/`_arm`/`_disarm`/`_request_stop` defs present; hypr-binds stale comment gone + new description present; daemon.py parses.
- [ ] L2: 6 toggle×mode tests pass (incl. the two BUG-B-fix switch tests asserting `len(spawns)==2` + mode switch + listening).
- [ ] L3: full `tests/test_daemon.py` green; existing toggle/lazy-load/idle tests unchanged.
- [ ] L4: diff = `daemon.py` + `hypr-binds.conf` + `test_daemon.py`; toggle machinery (`_load_host`/`_arm`/`_disarm`/`_request_stop`/`_mode`/`switch_mode`) untouched; sibling files unchanged.

### Feature Validation
- [ ] `toggle` disarms iff `(listening and mode=="normal")`; else arms/switches-to normal.
- [ ] `toggle_lite` disarms iff `(listening and mode=="lite")`; else arms/switches-to lite.
- [ ] Cross-mode armed press (F while normal, D while lite) SWITCHES (one reload), does NOT disarm.
- [ ] Each key while idle arms in its own mode.
- [ ] `_load_host` mode-switch machinery reused unchanged (no second teardown path).

### Code Quality Validation
- [ ] Read-act split preserved (joint read under `_lock`; `_load_host` outside `_lock`; `_arm` under `_lock`).
- [ ] Both docstrings describe mode-specific arming + cite delta §3.4.
- [ ] hypr-binds.conf comment describes the mode-switch behavior (Mode A doc).
- [ ] Tests use `_spawning_factory` (respects mode kwarg + counts reloads) + `_make_lazy_daemon`; assert `d._mode` + `d._host.mode`.

### Scope Boundary Validation
- [ ] `_load_host`/`_arm`/`_disarm`/`_request_stop`/`self._mode` UNCHANGED (correct already).
- [ ] No `ctl.py`/socket-dispatch/`status_snapshot`/`recorder_host.py`/`config`/systemd/install.sh changes (T2.S2 owns end-to-end mode verification).
- [ ] No real run() loop in the unit tests (the dead-host-detection concurrency is T2.S2's — Gotcha #5).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] Mode A: toggle/toggle_lite docstrings + the hypr-binds.conf comment ARE the doc (rides with the work).
- [ ] README lite-mode sections are P1.M2.T2's job (Mode B sweep), not this subtask.

---

## Anti-Patterns to Avoid

- ❌ Don't keep the bare `disarmed = self._listening.is_set()` condition — that IS BUG-B. The condition must be `(listening and mode == <this mode>)` (CRITICAL #3).
- ❌ Don't read `_listening` and `_mode` in two separate `with self._lock:` blocks — TOCTOU. Read both in one critical section (CRITICAL #1).
- ❌ Don't call `_load_host` while holding `_lock` — it acquire-release-reacquires `_lock` → deadlock. It stays OUTSIDE `_lock`; only `_arm` is under `_lock` (CRITICAL #2).
- ❌ Don't touch `_load_host`/`_arm`/`_disarm`/`_request_stop`/`self._mode` — they are correct (system_context §3.1). The fix is purely the toggle condition routing the cross-mode press to `_load_host` (CRITICAL #4).
- ❌ Don't add a workaround for the dead-host-detection concurrency note in THIS subtask — the unit tests don't run the loop, and T2.S2 owns the live mode-switch verification. Flag it (Gotcha #5), don't fix it here.
- ❌ Don't use `_fake_host_factory(mode=...)` with an explicit mode for the switch tests — the closure override forces that mode on every host, breaking `_load_host`'s mismatch detection. Use `_spawning_factory` (or `_fake_host_factory()` with no mode arg) so the kwarg flows through (Gotcha #7).
- ❌ Don't run a real run() loop in the unit tests — `_request_stop` disarms immediately when `_text_in_flight` is clear (no loop), so the disarm tests are clean; the loop's concurrency is T2.S2's scope (Gotcha #6).
- ❌ Don't edit the hypr-binds.conf BINDS or the integration/precedence/mods comment sections — only the behavior paragraph (the "Both keys STOP" text) is stale.
- ❌ Don't edit ctl.py / socket dispatch / status_snapshot — they already route toggle-lite + report mode (system_context §3.1). T2.S1 changes only the methods' behavior.
- ❌ Don't use bare `python`/`pytest` or invoke ruff/mypy (not configured). Use `.venv/bin/python -m pytest` (Gotcha #10).

---

## Confidence Score

**9/10** for one-pass implementation success. The change is small and surgical — a boolean condition rewrite in two methods (verbatim current bodies confirmed at L1343-1356 / L1359-1374), a docstring refresh, a one-paragraph comment edit, and 6 deterministic unit tests — and every load-bearing fact is **verified against the live repo**: the `_load_host(mode)` mode-switch machinery is confirmed correct + must-not-touch (L686-780: `switch_mode` detection → teardown → respawn → `self._mode=mode`); the read-act-split + outside-`_lock` discipline is the existing structure; the `_FakeHost`/`_fake_host_factory`/`_make_lazy_daemon` seam is read in full (incl. the `mode=None`-respects-kwarg detail that makes the switch tests work); `_request_stop` disarms immediately when no utterance is in flight (so the disarm tests need no run loop); and the no-conflict boundary with T1.S2 (construction-layer tests) is explicit. The 6 tests deterministically pin all six toggle×mode outcomes, with `len(spawns)` as the precise reload-count signal. The −1 residual is the **concurrency note** (Gotcha #5): the BUG-B fix is the first time `_load_host` is called while `_listening` is set, and the run() loop's dead-host check (L831) may fire spuriously on the killed resident mid-switch — benign (end state correct; `_load_host`'s success path cleans up `_load_error`/`_mode`) but potentially noisy. That is explicitly deferred to T2.S2's live/concurrent verification and is NOT exercised by the unit tests here (which don't run the loop), so it does not block one-pass implementation of this subtask's contract.

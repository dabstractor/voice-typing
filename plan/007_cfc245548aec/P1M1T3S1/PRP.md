# PRP — P1.M1.T3.S1: ABC + batched wtype/ydotool/null press_backspace implementations + fallback

## Goal

**Feature Goal**: Add the Rev 2 `press_backspace(n: int) -> None` primitive (PRD §4.3 + §4.2quater R2 — "delete exactly n characters") to `voice_typing/typing_backends.py`: an abstract method on the `TypingBackend` ABC plus all four implementations — **WtypeBackend** (`["wtype"] + ["-k","Backspace"]*n`, ONE batched invocation), **YdotoolBackend** (`["ydotool","key","-d","1"] + ["14:1","14:0"]*n`, ONE batched invocation), **NullBackend** (no-op), and **_WtypeWithFallback** (the same catch-`(CalledProcessError, OSError)` → WARNING → retry-ONCE-via-ydotool contract as `type_text`). `n <= 0` returns immediately without spawning. Backed by an ADDITIVE test section pinning exact argv, the n=0/no-negative no-op, the single-invocation batching for n=80 (the <150 ms budget contract), fallback ordering, and abstract-ness.

**Deliverable** (2 files edited, no new files):
1. `voice_typing/typing_backends.py` — `press_backspace` on the ABC (@abstractmethod) + WtypeBackend + YdotoolBackend + NullBackend + _WtypeWithFallback; docstring notes updated (the module header's NEVER-EMIT-ENTER note gains the backspace primitive's contract; DOCS: none beyond docstrings).
2. `tests/test_typing_backends.py` — one ADDITIVE banner section (~11 tests) using the existing `_Recorder` harness; no existing test changed.

**Success Definition**:
- (a) `TypingBackend.press_backspace` is abstract; a subclass implementing only `type_text` cannot instantiate (TypeError).
- (b) `WtypeBackend().press_backspace(3)` → exactly ONE subprocess.run with argv `("wtype","-k","Backspace","-k","Backspace","-k","Backspace")`, `check=True`.
- (c) `YdotoolBackend().press_backspace(2)` → exactly ONE subprocess.run with argv `("ydotool","key","-d","1","14:1","14:0","14:1","14:0")`, `check=True`.
- (d) `n <= 0` (0, negative) spawns NO subprocess on WtypeBackend, YdotoolBackend, or the wrapper — and logs no WARNING.
- (e) `press_backspace(80)` → exactly ONE subprocess.run call (argv length 2+2n / 4+2n) on each real backend — never per-keystroke spawning (the ~80-chars-in-<150 ms budget).
- (f) `_WtypeWithFallback.press_backspace` catches `(CalledProcessError, OSError)` from the primary, logs a WARNING mentioning ydotool, retries ONCE on the fallback; a fallback failure propagates; success makes exactly 2 calls total.
- (g) `NullBackend().press_backspace(n)` spawns nothing (headless-E2E safety).
- (h) All existing tests pass unmodified; `make_backend`, `type_text`, and every existing argv pin are byte-identical.
- (i) Zero real keystrokes: every new test goes through the `_Recorder` monkeypatch (the file-wide no-real-subprocess guard at :274 covers this).

> **VERIFIED FACTS (this PRP's research):** the binary semantics are LOCAL-probed on this machine — wtype `-k` occurrences repeat within ONE invocation (`env -i /usr/bin/wtype -k Backspace -k Backspace` → no parse error; fails only at Wayland connect); ydotool `key` takes `-d <ms>` + repeated `<keycode>:<pressed>` codes with Backspace = 14; the budget math (one fork/exec ~5–15 ms + 80 pairs ≈ 45–175 ms worst) requires batching. No `TypingBackend` subclass exists outside typing_backends.py, so the new abstract method breaks nothing.

## User Persona

Not applicable as an end-user surface — this is an internal primitive (DOCS: "none beyond docstrings"). The consumers are downstream tasks: **P1.M2.T6** (the streaming state machine's revise/commit rewinds call `press_backspace(len(revised_chars))`), **P1.M2.T7.S1** (Backspace-cancel rewinds `max(len(tail)-1, 0)` — which is 0 when the tail is ≤1 char, exercising the n<=0 no-op), and **T8's RecordingTypingBackend** (mirrors the method to RECORD calls instead of typing). The end-user benefit arrives with streaming dictation: in-place revision instead of append-only output.

## Why

- **PRD §4.2quater R2 is the mandate**: "`press_backspace(n)` MUST delete exactly n characters in an ordinary text field (wtype: repeat `-k Backspace`; ydotool: repeat the backspace keycode; batched so ~80 chars rewind in <150 ms)." It is the foundation the entire streaming state machine (P1.M2.T6) rewinds with — without it, neither in-place revision (rule 1/2) nor Backspace-cancel (the trigger path) can exist.
- **Batching is the performance contract, not a style choice.** ~80 per-keystroke spawns × ~10 ms fork/exec ≈ 800 ms — five times over the 150 ms budget; one batched invocation lands at ~45–175 ms worst-case (external_deps.md §4, LOCAL-probed). Both real backends MUST build ONE argv list and make ONE subprocess.run call.
- **The single-invocation forms are verified against the actual binaries** (external_deps.md §2–§3): wtype's synopsis `wtype [OPTION_OR_TEXT]... -- [TEXT]...` accepts repeated `-k` occurrences (probe: no usage error); ydotool's `key` takes `-d N` (ms between keystrokes) and repeated `14:1 14:0` press/release pairs (Backspace keycode 14). Guessing these would risk argv that parses wrong at runtime — the probes eliminate that.
- **Why the wrapper repeats the pattern instead of refactoring**: `_WtypeWithFallback` must give `press_backspace` the same retry-once contract as `type_text` (PRD §4.3's auto-fallback applies to the backend, not to one method). Duplicating the small try/except is the established pattern; a generic delegator would be a larger refactor and change the WARNING message contract the tests pin.
- **n<=0 must not spawn.** The cancel path computes `max(len(tail)-1, 0)` — a 1-char tail yields n=0, and spawning `wtype` with zero `-k` pairs (a bare `wtype` with no args) would be a wasted/odd invocation that could even error. The guard belongs in each concrete backend (and the wrapper short-circuits before the try, avoiding a pointless WARNING).

## What

Add `press_backspace(n: int) -> None` to the ABC and all four classes per the verified argv forms; add ~11 additive tests using the existing `_Recorder` harness. No changes to `type_text`, `make_backend`, or any existing method.

### Success Criteria

- [ ] `grep -c 'def press_backspace' voice_typing/typing_backends.py` → **5** (ABC + 4 impls).
- [ ] ABC's `press_backspace` is decorated `@abstractmethod`; `TypingBackend()` still raises TypeError; a type_text-only subclass also raises TypeError.
- [ ] WtypeBackend n=3 argv pinned: `("wtype","-k","Backspace","-k","Backspace","-k","Backspace")` + `check=True`; no `--` (all args are options).
- [ ] YdotoolBackend n=2 argv pinned: `("ydotool","key","-d","1","14:1","14:0","14:1","14:0")` + `check=True`.
- [ ] n ∈ {0, -1, -5} on WtypeBackend/YdotoolBackend/_WtypeWithFallback → `recorder.calls == []` and no WARNING logged.
- [ ] n=80 → exactly ONE subprocess.run per real backend; "Backspace" appears 80× (wtype argv len 162); "14:1"/"14:0" 80× each (ydotool argv len 164).
- [ ] Fallback: primary raises CalledProcessError → exactly 2 recorded calls (wtype argv then ydotool argv) + a WARNING mentioning ydotool; primary raises FileNotFoundError → same retry; both fail → the OSError propagates; primary succeeds → exactly 1 call, no WARNING.
- [ ] `NullBackend().press_backspace(5)` → `recorder.calls == []`.
- [ ] `.venv/bin/python -m pytest tests/test_typing_backends.py -q` → 0 failures (all pre-existing + new).
- [ ] `git diff --name-only` == `voice_typing/typing_backends.py` + `tests/test_typing_backends.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact current shape of every class to extend (verbatim), the LOCAL-probed binary semantics (wtype repeated `-k`; ydotool `-d 1` + `14:1 14:0` pairs; keycode 14), the budget math that forces batching, the verbatim implementation code for all five methods, the complete test list with exact assertions, and the parallel-sibling no-conflict analysis are all below. An agent new to this repo can implement from this PRP alone. Pure stdlib; the tests mock subprocess.run — no display, no ydotoold, no real keystrokes.

### Documentation & References

```yaml
# MUST READ — the verified impl code + test plan + binary facts (this task's own research)
- docfile: plan/007_cfc245548aec/P1M1T3S1/research/press_backspace_impl_and_tests.md
  why: "§1 the current typing_backends.py shape (no press_backspace exists; no other TypingBackend
        subclass anywhere). §2 the LOCAL-probed binary facts (wtype -k repeats in ONE invocation —
        env -i probe; ydotool key -d N + repeated 14:1/14:0; Backspace=14; budget math 45–175ms batched
        vs ~800ms per-keystroke). §3 the verbatim implementation code for all 5 methods. §4 the complete
        test list. §5 parallel/scope."
  critical: "§3 is the implementation, verbatim. §2 explains WHY these exact argv forms (probed, not
            guessed) and why n<=0 must not spawn (the cancel path's max(len-1,0) yields 0)."

# MUST READ — the probed external-binary facts + the budget check
- docfile: plan/007_cfc245548aec/architecture/external_deps.md
  why: "§2 wtype: man synopsis 'wtype [OPTION_OR_TEXT]... -- [TEXT]...' — option occurrences REPEAT within
        one invocation; the env -i parse probe (-k Backspace -k Backspace → no usage error, fails only at
        Wayland connect, nonzero exit → CalledProcessError → the fallback catches it). §3 ydotool:
        'key [OPTION]... [KEYCODES]...', -d N = ms between keystrokes, codes <keycode>:<pressed>,
        Backspace = 14 (input-event-codes.h); VERDICT one call ['ydotool','key','-d','1'] + ['14:1','14:0']*n.
        §4 budget check: one fork/exec ~5–15ms + 80 pairs ≈ 45–175ms worst — batching MANDATORY."
  critical: "These are LOCAL probes on this machine (marked LOCAL), not doc citations. Do NOT deviate from
            the pinned argv forms (e.g. no '--' on the wtype backspace call — all args are options; do not
            rely on ydotool's default delay — pass the explicit '-d','1')."

# THE FILE TO EDIT — the current classes (verbatim old→new in the Blueprint)
- file: voice_typing/typing_backends.py
  why: "TypingBackend ABC (one abstract type_text), WtypeBackend (['wtype','--',text] check=True),
        YdotoolBackend (['ydotool','type','--key-delay','2','--',text]), NullBackend (no-op),
        _WtypeWithFallback (ctor-injected primary/fallback; catches (CalledProcessError, OSError),
        WARNING 'wtype typing failed (%s); retrying once via ydotool', retries ONCE), make_backend
        (wtype→wrapper / ydotool / null / else ValueError)."
  pattern: "Every subprocess call uses check=True. The wrapper's except is deliberately the SUPERSET
            OSError (covers FileNotFoundError + PermissionError) — mirror it exactly. The n<=0 guard goes
            INSIDE each concrete backend AND at the top of the wrapper's method (before the try, so a
            failing primary on n=0 cannot emit a spurious WARNING)."
  gotcha: "Do NOT add '--' to the wtype press_backspace argv (there is no positional text to separate
           options from — '-k Backspace' pairs are all options). Do NOT spawn per keystroke."

# THE TEST HARNESS — the _Recorder fake + the pins to mirror
- file: tests/test_typing_backends.py
  why: "The `recorder` fixture (monkeypatches subprocess.run for the whole test; records (argv, kwargs);
        raise_on(argv[0], exc) simulates failures) is THE harness — every new test uses it. Mirror the
        existing exact-argv pins (test_wtype_invokes_exact_argv :89, test_ydotool_invokes_exact_argv :122)
        and the NullBackend no-subprocess pin (:144). The file-wide no-real-subprocess guard (:274) already
        covers the new tests. `caplog.at_level(logging.WARNING, logger='voice_typing.typing_backends')` is
        the established WARNING-assert idiom."
  pattern: "ADD a new banner section at the END of the file (the file's convention). Tests: exact argv pins
            both backends; n=0/-1/-5 no-spawn across 3 classes; n=80 single-invocation (len(argvs)==1 +
            per-token counts); fallback ordering (wtype-then-ydotool argvs); WARNING mentions ydotool;
            both-fail propagates; success = exactly 2 calls; null no-spawn; abstract-ness extended (a
            type_text-only subclass fails to instantiate)."
  critical: "NEVER let a test execute real wtype/ydotool — everything goes through `recorder`. Assert
            check=True via recorder.calls[0][1].get('check') is True (the existing idiom)."

# THE SPEC — PRD §4.3 + §4.2quater
- file: PRD.md
  why: "§4.3: the interface gains 'press_backspace(n: int) -> None (Rev 2, §4.2quater — delete exactly n
        characters for in-place revision)'; null backend 'types NOTHING... No subprocess is spawned.'
        §4.2quater 'Typing backend additions': press_backspace(n) MUST delete exactly n chars; wtype
        repeats -k Backspace; ydotool repeats the backspace keycode; batched so ~80 chars rewind in
        <150 ms; correctness assumes the cursor sits at the end of our typed text."
  critical: "The consumer contract: P1.M2.T6 rewinds len(revised_chars); P1.M2.T7.S1 rewinds
            max(len(tail)-1, 0) — hence n can legitimately be 0 and MUST be a no-op."

# THE SIBLING (parallel) — no overlap
- docfile: plan/007_cfc245548aec/P1M1T2S4/PRP.md
  why: "T2.S4 (parallel) edits voice_typing/prefetch.py, hypr-binds.conf, install.sh, tests/ACCEPTANCE.md,
        tests/test_systemd_unit.py — DISJOINT from this task's two files. No merge conflict."
  critical: "Do NOT touch prefetch/binds/install/ACCEPTANCE here; do NOT rewire the daemon (P1.M2.T6's job)
            or add cancel (P1.M2.T7's job) or the RecordingTypingBackend double (T8's job)."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── typing_backends.py      # ABC + Wtype/Ydotool/Null/_WtypeWithFallback + make_backend.      ← EDIT (add press_backspace ×5)
│   │                            NO press_backspace exists yet (grep → 0). No other TypingBackend subclass
│   │                            anywhere (daemon.py only type-hints it) — the new abstract method breaks nothing.
└── tests/
    └── test_typing_backends.py # 301 lines; _Recorder harness; argv pins :89/:122; null :144; guard :274.  ← EDIT (additive section)
# T2.S4 (parallel) edits prefetch.py / hypr-binds.conf / install.sh / ACCEPTANCE.md / test_systemd_unit.py — DISJOINT.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/typing_backends.py # EDIT: +press_backspace on ABC (@abstractmethod) + WtypeBackend + YdotoolBackend
#                               + NullBackend + _WtypeWithFallback (n<=0 guards; ONE batched run each; retry-once).
#                               Module docstring: one short note that Rev 2 adds press_backspace (PRD §4.2quater).
tests/test_typing_backends.py   # ADD: one banner section (~11 tests) — exact argv pins, n<=0 no-op, n=80 single
#                               invocation, fallback ordering/warning/propagation, null no-spawn, abstract-ness.
# No new files. No daemon/recorder_host/ctl/config changes (downstream tasks consume the primitive).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ONE SUBPROCESS CALL, NEVER PER KEYSTROKE. 80 spawns × ~10 ms ≈ 800 ms — five times the
# <150 ms budget. Build the whole argv list and make ONE subprocess.run(["wtype"] + ["-k","Backspace"]*n)
# (or ["ydotool","key","-d","1"] + ["14:1","14:0"]*n). The n=80 test asserts len(argvs) == 1 — this is the
# budget contract, not a style preference. (external_deps.md §4.)

# CRITICAL #2 — THE EXACT ARGV FORMS ARE PROBED, NOT GUESSED. wtype: repeated "-k Backspace" pairs within
# ONE invocation (env -i probe: no usage error; fails only at Wayland connect → nonzero → the fallback
# catches CalledProcessError). ydotool: "key", "-d", "1", then "14:1","14:0" press/release pairs
# (Backspace keycode = 14). Do NOT add "--" to the wtype call (no positional text — all options). Do NOT
# omit the explicit "-d","1" (never rely on ydotool's default delay for an 80-press batch).

# CRITICAL #3 — n <= 0 MUST NOT SPAWN (and must not WARN). The cancel path computes max(len(tail)-1, 0):
# a 1-char tail yields n=0. A bare "wtype" with zero -k pairs is a wasted/odd invocation. Guard inside
# EACH concrete backend (Wtype/Ydotool) AND at the top of the wrapper's method — the wrapper's guard must
# precede the try so a failing primary can't emit a spurious WARNING for n=0. NullBackend ignores n.

# CRITICAL #4 — MIRROR THE FALLBACK CONTRACT EXACTLY. Same except tuple ((CalledProcessError, OSError) —
# the deliberate OSError superset covering FileNotFoundError AND PermissionError), same one-retry-only
# semantics, same "propagates if the fallback also fails", TypeError NOT caught. Only the WARNING message
# differs: "wtype backspace failed (%s); retrying once via ydotool". Do NOT refactor type_text+press_backspace
# into a shared delegator — the duplication preserves the pinned WARNING strings.

# CRITICAL #5 — THE ABC ADDITION BREAKS NOTHING... VERIFIED. No class anywhere subclasses TypingBackend
# outside typing_backends.py (daemon.py :95/:541 only uses it as a type hint; test fakes are duck-typed).
# The T8 RecordingTypingBackend (later task) will implement it. But DO add the abstract-ness test: a
# minimal subclass implementing only type_text must now fail to instantiate.

# GOTCHA #6 — USE FULL PATHS. zsh aliases python3/uv/pip/tmux. Invoke .venv/bin/python -m pytest. Never
# bare python/pytest.

# GOTCHA #7 — THIS PROJECT USES pytest (no ruff/mypy configured — dev group is pytest only). Validation =
# py_compile + pytest. The PRP template's ruff/mypy gates are N/A here.

# GOTCHA #8 — NO REAL KEYSTROKES, EVER. Every new test uses the `recorder` fixture (subprocess.run
# monkeypatched). A stray real call would type Backspaces into the developer's FOCUSED window — the
# file-wide guard at :274 asserts the mechanism; follow the harness.

# GOTCHA #9 — DOCS: none beyond docstrings. The README streaming section lands with P1.M3.T10.S1. Do NOT
# touch config.toml/README/ACCEPTANCE here. Also do NOT wire the daemon (P1.M2.T6), cancel (P1.M2.T7),
# or the RecordingTypingBackend (T8) — this task ships ONLY the primitive + its tests.
```

## Implementation Blueprint

### Data models and structure

No new data models. The only new "structure" is one abstract method signature plus four small concrete implementations. The n parameter is `int`; return is `None`; no state is added to any class.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/typing_backends.py — add press_backspace to the ABC + all four classes
  - (1a) ABC — add the abstract method directly after type_text:
        @abstractmethod
        def press_backspace(self, n: int) -> None:
            """Delete exactly n characters via n Backspace keypresses (PRD §4.2quater R2).

            Implementations MUST batch into ONE subprocess invocation (~80 chars in <150 ms —
            per-keystroke spawning blows the budget). n <= 0 is a no-op (no subprocess).
            """
            raise NotImplementedError
  - (1b) WtypeBackend — add:
        def press_backspace(self, n: int) -> None:
            # ONE batched invocation: repeated "-k Backspace" pairs are verified to repeat within a
            # single wtype call (external_deps.md §2, env -i probe). No "--" — all args are options.
            if n <= 0:
                return
            subprocess.run(["wtype"] + ["-k", "Backspace"] * n, check=True)
  - (1c) YdotoolBackend — add:
        def press_backspace(self, n: int) -> None:
            # ONE batched invocation: "14:1 14:0" = Backspace press+release (keycode 14); explicit
            # "-d 1" (1 ms between events) — never rely on the default delay for an 80-press batch.
            if n <= 0:
                return
            subprocess.run(["ydotool", "key", "-d", "1"] + ["14:1", "14:0"] * n, check=True)
  - (1d) NullBackend — add:
        def press_backspace(self, n: int) -> None:
            logger.debug("null backend: suppressed %d backspaces", n)
  - (1e) _WtypeWithFallback — add after type_text:
        def press_backspace(self, n: int) -> None:
            if n <= 0:
                return  # guard BEFORE the try: n=0 must not try wtype nor log a WARNING
            try:
                self._primary.press_backspace(n)
            except (subprocess.CalledProcessError, OSError) as exc:
                logger.warning(
                    "wtype backspace failed (%s); retrying once via ydotool", exc
                )
                self._fallback.press_backspace(n)  # may raise -> propagates (one retry only)
  - (1f) Module docstring: extend the header with one short note, e.g. after the NEVER EMIT ENTER/NEWLINE
    paragraph: "Rev 2 adds press_backspace(n) (PRD §4.2quater): delete exactly n characters — ONE batched
    subprocess per call (wtype repeats -k Backspace; ydotool repeats 14:1/14:0 pairs); n<=0 is a no-op."
  - DO NOT: modify type_text/make_backend/any existing line beyond the docstring note; add "--" to the
    wtype backspace argv; spawn per keystroke; catch TypeError.

Task 2: ADD tests/test_typing_backends.py — one additive banner section (~11 tests, verbatim below)
  - PLACE: a new section at the END of the file:
        # ===========================================================================
        # Rev 2 P1.M1.T3.S1 — press_backspace(n): batched backspace primitive (PRD §4.2quater R2)
        # (ONE subprocess per call — the <150ms/80-char budget; n<=0 is a no-op. Exact argv pins for
        #  wtype (-k Backspace ×n) and ydotool (key -d 1 + 14:1/14:0 ×n); the wrapper mirrors the
        #  type_text catch/WARNING/retry-once contract. All via the `recorder` fixture — no real keys.)
        # ===========================================================================
  - TESTS:
        def test_wtype_press_backspace_exact_argv(recorder):
            WtypeBackend().press_backspace(3)
            assert recorder.argvs == [("wtype", "-k", "Backspace", "-k", "Backspace", "-k", "Backspace")]
            assert recorder.calls[0][1].get("check") is True

        def test_ydotool_press_backspace_exact_argv(recorder):
            YdotoolBackend().press_backspace(2)
            assert recorder.argvs == [("ydotool", "key", "-d", "1", "14:1", "14:0", "14:1", "14:0")]
            assert recorder.calls[0][1].get("check") is True

        @pytest.mark.parametrize("n", [0, -1, -5])
        def test_press_backspace_nonpositive_spawns_nothing(recorder, caplog, n):
            with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
                WtypeBackend().press_backspace(n)
                YdotoolBackend().press_backspace(n)
                make_backend(OutputConfig(backend="wtype")).press_backspace(n)
            assert recorder.calls == []          # no subprocess at all
            assert not any("ydotool" in r.getMessage() for r in caplog.records)  # no spurious WARNING

        def test_press_backspace_n80_is_one_invocation(recorder):
            # The budget contract (PRD §4.2quater): ~80 chars must rewind via ONE subprocess call.
            WtypeBackend().press_backspace(80)
            assert len(recorder.argvs) == 1
            assert len(recorder.argvs[0]) == 2 + 2 * 80           # "wtype" + 80 × ("-k","Backspace")
            assert recorder.argvs[0].count("Backspace") == 80
            YdotoolBackend().press_backspace(80)
            assert len(recorder.argvs) == 2                        # one MORE call (total), still 1 each
            assert len(recorder.argvs[1]) == 4 + 2 * 80            # + "-d","1" pair
            assert recorder.argvs[1].count("14:1") == 80 and recorder.argvs[1].count("14:0") == 80

        def test_press_backspace_fallback_ordering(recorder):
            recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
            make_backend(OutputConfig(backend="wtype")).press_backspace(2)
            assert recorder.argvs == [
                ("wtype", "-k", "Backspace", "-k", "Backspace"),
                ("ydotool", "key", "-d", "1", "14:1", "14:0", "14:1", "14:0"),
            ]                                                          # retry exactly ONCE, correct argv each

        def test_press_backspace_fallback_missing_binary_also_retries(recorder):
            recorder.raise_on("wtype", FileNotFoundError("wtype"))
            make_backend(OutputConfig(backend="wtype")).press_backspace(1)
            assert recorder.argvs[0][0] == "wtype" and recorder.argvs[1][0] == "ydotool"

        def test_press_backspace_fallback_logs_warning(recorder, caplog):
            recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
            with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
                make_backend(OutputConfig(backend="wtype")).press_backspace(1)
            assert any(r.levelno == logging.WARNING and "ydotool" in r.getMessage() for r in caplog.records)

        def test_press_backspace_fallback_failure_propagates(recorder):
            recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
            recorder.raise_on("ydotool", FileNotFoundError("ydotool"))
            with pytest.raises(OSError):
                make_backend(OutputConfig(backend="wtype")).press_backspace(1)

        def test_press_backspace_primary_success_no_fallback(recorder):
            make_backend(OutputConfig(backend="wtype")).press_backspace(2)
            assert len(recorder.argvs) == 1 and recorder.argvs[0][0] == "wtype"

        def test_null_press_backspace_spawns_no_subprocess(recorder):
            NullBackend().press_backspace(5)
            assert recorder.calls == []

        def test_press_backspace_is_abstract_on_abc():
            with pytest.raises(TypeError):
                TypingBackend()  # still abstract overall
            class _OnlyTypeText(TypingBackend):
                def type_text(self, text): ...
            with pytest.raises(TypeError):
                _OnlyTypeText()  # press_backspace missing -> uninstantiable (genuinely abstract)

  - Note: `make_backend`, `OutputConfig`, `logging`, `subprocess`, `pytest`, and all backend classes are
    already imported at the file top — no new imports.
  - DO NOT: modify any existing test; execute real subprocesses; drop the check=True assertions.

Task 3: VALIDATE — run the Validation Loop L1–L4. No git commit unless the orchestrator directs it.
  If asked: "P1.M1.T3.S1: press_backspace(n) on the ABC + batched wtype/ydotool/null impls + fallback
  retry-once; 11 additive tests (exact argv, n<=0 no-op, n=80 single-invocation, fallback, abstractness)."
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the batched argv construction (THE budget contract). Never loop subprocess.run.
subprocess.run(["wtype"] + ["-k", "Backspace"] * n, check=True)          # 2 + 2n tokens
subprocess.run(["ydotool", "key", "-d", "1"] + ["14:1", "14:0"] * n, check=True)  # 4 + 2n tokens

# PATTERN 2 — the n<=0 guard placement. Concrete backends guard before spawning; the wrapper guards
# BEFORE the try so n=0 can neither spawn wtype nor emit a spurious WARNING (the cancel path sends n=0
# via max(len(tail)-1, 0)).
if n <= 0:
    return

# PATTERN 3 — the wrapper mirrors type_text's contract exactly (superset OSError; one retry; propagates).
except (subprocess.CalledProcessError, OSError) as exc:      # NOT just FileNotFoundError
    logger.warning("wtype backspace failed (%s); retrying once via ydotool", exc)
    self._fallback.press_backspace(n)                        # may raise -> propagates
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS (the contract's OUTPUT):
  - P1.M2.T6 (streaming state machine): the revise path calls press_backspace(len(revised_chars)); the
    commit correction pass rewinds the tail the same way. Depends on: exact-n deletion, batching (the
    <150 ms budget keeps revision visually instant), exceptions propagating (freeze rules).
  - P1.M2.T7.S1 (Backspace-cancel): calls press_backspace(max(len(tail)-1, 0)) — n=0 is a REAL runtime
    value here; the no-op guard is load-bearing. Also `voicectl cancel` runs the same path.
  - T8 RecordingTypingBackend (P1.M3.T8.S1): a test double MIRRORING this method (records calls) — the
    ABC contract is what it mirrors.

PARALLEL — P1.M1.T2.S4 (in flight): edits prefetch.py / hypr-binds.conf / install.sh / ACCEPTANCE.md /
  test_systemd_unit.py — DISJOINT files. No merge conflict.

UNCHANGED SURFACES:
  - type_text (all classes), make_backend dispatch, module import purity (no new imports), the
    THREAD SAFETY docstring claims, the NEVER-EMIT-ENTER/NEWLINE invariant (backspace DELETES; it never
    adds newlines). config.toml [output] untouched (backend selection unchanged — press_backspace is
    method-level, not config-level).
```

## Validation Loop

> Full paths (zsh aliases). From the repo root. pytest only (no ruff/mypy — Gotcha #7). All hermetic.

### Level 1: The edits are in place

```bash
cd /home/dustin/projects/voice-typing
test "$(grep -c 'def press_backspace' voice_typing/typing_backends.py)" -eq 5 && echo "L1 PASS: 5 impls" || echo "L1 FAIL"
grep -q '@abstractmethod' voice_typing/typing_backends.py && grep -A1 'abstractmethod' voice_typing/typing_backends.py | grep -q 'press_backspace' && echo "L1 PASS: abstract" || echo "L1 FAIL"
grep -q '\["wtype"\] + \["-k", "Backspace"\] \* n' voice_typing/typing_backends.py && echo "L1 PASS: wtype batched" || echo "L1 FAIL"
grep -q '\["ydotool", "key", "-d", "1"\] + \["14:1", "14:0"\] \* n' voice_typing/typing_backends.py && echo "L1 PASS: ydotool batched" || echo "L1 FAIL"
grep -cE 'if n <= 0' voice_typing/typing_backends.py   # expect 3 (wtype, ydotool, wrapper)
.venv/bin/python -m py_compile voice_typing/typing_backends.py && echo "L1 PASS: compiles" || echo "L1 FAIL"
```

### Level 2: The new tests + the full file (no regression)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_typing_backends.py -q -k press_backspace -v 2>&1 | tail -18
.venv/bin/python -m pytest tests/test_typing_backends.py -q 2>&1 | tail -3
# Expected: all new press_backspace tests pass; the FULL file is green (pre-existing pins unchanged).
```

### Level 3: The behavioral spot-check (hermetic, via a throwaway script — still NO real keystrokes)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import subprocess
from voice_typing.typing_backends import WtypeBackend, YdotoolBackend, NullBackend, TypingBackend
calls = []
def fake_run(argv, **kw):
    calls.append((tuple(argv), kw)); return subprocess.CompletedProcess(list(argv), 0)
subprocess.run = fake_run
WtypeBackend().press_backspace(3); YdotoolBackend().press_backspace(2); NullBackend().press_backspace(5)
WtypeBackend().press_backspace(0); YdotoolBackend().press_backspace(-1)
assert calls[0][0] == ("wtype","-k","Backspace","-k","Backspace","-k","Backspace") and calls[0][1]["check"] is True
assert calls[1][0] == ("ydotool","key","-d","1","14:1","14:0","14:1","14:0") and calls[1][1]["check"] is True
assert len(calls) == 2                       # null + n<=0 spawned nothing
WtypeBackend().press_backspace(80)
assert len(calls) == 3 and len(calls[2][0]) == 162 and calls[2][0].count("Backspace") == 80
try: TypingBackend()
except TypeError: print("L3 PASS: ABC abstract; all argv/batching/no-op behavior correct")
PY
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only
git diff --exit-code -- voice_typing/daemon.py voice_typing/prefetch.py voice_typing/config.py hypr-binds.conf install.sh README.md config.toml && echo "L4 PASS: out-of-scope files untouched" || echo "L4 FAIL"
git diff --exit-code -- PRD.md plan/007_cfc245548aec/tasks.json .gitignore && echo "L4 PASS: read-only untouched" || echo "L4 NOTE: tasks.json = orchestrator bookkeeping"
# Expected: diff == voice_typing/typing_backends.py + tests/test_typing_backends.py ONLY.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: 5 `press_backspace` defs; @abstractmethod on the ABC; both batched argv forms present; 3 `n<=0` guards; compiles.
- [ ] L2: new tests green; full test_typing_backends.py green (existing pins unmodified).
- [ ] L3: hermetic spot-check passes (exact argv, batching, no-op, abstract ABC).
- [ ] L4: only the 2 in-scope files changed.

### Feature Validation
- [ ] Wtype n=3 / Ydotool n=2 exact argv + check=True pinned; n=80 → ONE call per backend with correct token counts.
- [ ] n ∈ {0,-1,-5} → no subprocess + no WARNING across Wtype/Ydotool/wrapper.
- [ ] Fallback: CalledProcessError AND FileNotFoundError both retry once via ydotool; WARNING mentions ydotool; both-fail propagates; success = 1 call.
- [ ] NullBackend spawns nothing; a type_text-only subclass cannot instantiate.

### Code Quality / Scope Validation
- [ ] type_text / make_backend / existing tests byte-identical; no new imports; no daemon/cancel/T8 wiring.
- [ ] The wrapper mirrors the established catch/WARNING/retry-once pattern (superset OSError; TypeError uncaught).
- [ ] Zero real keystrokes (everything through the recorder/monkeypatch).

### Documentation & Deployment
- [ ] Docstring note added (Rev 2 primitive, batching rationale); no README/config/ACCEPTANCE changes (later tasks).

---

## Anti-Patterns to Avoid

- ❌ Don't spawn one subprocess per keystroke (`for _ in range(n): subprocess.run(...)`) — 80 × ~10 ms ≈ 800 ms, five times the budget. ONE batched argv per call. (Gotcha #1.)
- ❌ Don't deviate from the probed argv forms: no `--` on the wtype backspace call (all options); don't omit ydotool's explicit `-d 1`; `14:1`/`14:0` are separate argv tokens. (Gotcha #2.)
- ❌ Don't skip or misplace the `n<=0` guard — it must precede the wrapper's try (no spurious WARNING) and each backend's run (no spawn); n=0 is a real runtime value from the cancel path's `max(len(tail)-1, 0)`. (Gotcha #3.)
- ❌ Don't narrow the wrapper's except to `(CalledProcessError, FileNotFoundError)` — mirror the established OSError superset; and don't catch TypeError. (Gotcha #4.)
- ❌ Don't refactor type_text + press_backspace into a shared delegator — the duplication preserves the pinned WARNING strings; keep the change additive. (Gotcha #4.)
- ❌ Don't wire the daemon / cancel / RecordingTypingBackend — downstream tasks (P1.M2.T6, P1.M2.T7, T8) consume this primitive. (Gotcha #9.)
- ❌ Don't run a real subprocess in any test — always the `recorder` fixture / monkeypatch. (Gotcha #8.)
- ❌ Don't use bare python/pytest/uv (zsh aliases) or invent ruff/mypy gates. (Gotchas #6–#7.)
- ❌ Don't modify PRD.md / tasks.json / prd_snapshot.md / .gitignore / any out-of-scope file.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The implementation code is given verbatim for all five methods; the argv forms are LOCAL-probed against the actual installed binaries (not doc guesses — wtype's repeated `-k` verified by an `env -i` parse probe, ydotool's `-d`/`14:1 14:0` pairs by `ydotool key --help`); the test harness (`_Recorder`) is established and every new test is written out with exact assertions; no other `TypingBackend` subclass exists, so the new abstract method breaks nothing; and the parallel sibling edits disjoint files. The −0.5 residual is the small chance of an argv-token typo (e.g. miscounting the n=80 lengths) — caught immediately by the exact pins in L2/L3. No GPU, display, ydotoold, daemon, or network required.

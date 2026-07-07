# PRP — P1.M3.T1.S1: typing_backends.py (interface + wtype/ydotool/tmux + auto-fallback)

## Goal

**Feature Goal**: Ship `voice_typing/typing_backends.py` — the typing-output backend layer specified verbatim by PRD §4.3. It exposes an abstract `TypingBackend.type_text(text: str) -> None`, three concrete backends (`WtypeBackend`, `YdotoolBackend`, `TmuxBackend`) that each `subprocess.run` their respective command lists, a `_WtypeWithFallback` wrapper that implements PRD §4.3/§8 auto-fallback (wtype→ydotool on nonzero exit / missing binary), and a `make_backend(cfg: OutputConfig) -> TypingBackend` factory. This is the implementation half of milestone P1.M3.T1; the committed unit tests live in the NEXT task (P1.M3.T1.S2).

**Deliverable** (ONE artifact — impl only, tests are S2):
1. `voice_typing/typing_backends.py` — the module in Implementation Blueprint → Task 2 (verbatim). Exports `TypingBackend` (ABC), `WtypeBackend`, `YdotoolBackend`, `TmuxBackend`, and `make_backend(cfg: OutputConfig) -> TypingBackend`. The `_WtypeWithFallback` wrapper is module-private (leading underscore) but is what `make_backend` returns for `backend == "wtype"`.

**Success Definition**:
- (a) `voice_typing/typing_backends.py` exists, `py_compile`-clean, and `import voice_typing.typing_backends` succeeds importing ONLY stdlib + `OutputConfig` (no `cuda_check`/`torch`/`realtimestt`/`ctranslate2`).
- (b) `make_backend(OutputConfig(backend="wtype"))` returns a `TypingBackend` that wraps wtype with auto-fallback to ydotool; `backend="ydotool"` → `YdotoolBackend`; `backend="tmux"` → `TmuxBackend`; any other value → `ValueError`.
- (c) Each concrete backend runs the EXACT PRD §4.3 command list (`["wtype","--",text]`; `["ydotool","type","--key-delay","2","--",text]`; `["/usr/bin/tmux","send-keys","-t",tmux_target,"-l","--",text]`), with `check=True` added so nonzero exit is detectable for the fallback.
- (d) Auto-fallback: when the primary wtype raises `subprocess.CalledProcessError` (nonzero exit) or `OSError` (⊇ `FileNotFoundError` = binary missing), the wrapper logs a `WARNING` and retries ONCE via ydotool; if ydotool also raises, the exception propagates (no silent swallow).
- (e) Never appends Enter/newline — backends type exactly the text passed (textproc stripped trailing newlines; the daemon appends the trailing space).
- (f) `type_text` is safe to call from the daemon's `on_final` callback thread (no shared mutable state; `subprocess.run` is reentrant).
- (g) No out-of-scope files: NO `tests/test_typing_backends.py` (that is P1.M3.T1.S2), no edits to `config.py` (P1.M2.T1.S1 owns it; this module only imports `OutputConfig`), no `daemon.py`/`feedback.py`/`ctl.py`/`config.toml`/`install.sh`/systemd, no edits to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. stdlib only — no new dependencies.

## User Persona

**Target User**: None directly — `make_backend()` is an internal factory (no user-facing/config/API surface change, per item DOCS). Its "users" are the daemon (`on_final`, P1.M4.T1.S2) and the E2E test (P1.M7.T3.S1, via `backend="tmux"`).

**Use Case**: Every finalized, textproc-cleaned utterance is handed to a `TypingBackend.type_text(text)` which dispatches it to the OS typing surface (wtype / ydotool / tmux). `make_backend(cfg.output)` is called ONCE at daemon startup; the returned backend is reused for every utterance.

**User Journey**: ASR final → `textproc.clean()` → daemon appends `" "` when `append_space` → `backend.type_text(text)` → wtype types into the focused window (or, on wtype failure, ydotool; or, for tests/SSH, tmux `send-keys` into a target pane).

**Pain Points Addressed**: (1) wtype occasionally fails on some windows (XWayland edge cases) — auto-fallback to ydotool keeps typing working (PRD §8 risk). (2) Tests need a deterministic, side-effect-free typing target — the tmux backend types into a throwaway pane that `capture-pane` can read back (used by the E2E test). (3) SSH/detached use has no focused Wayland window — tmux `send-keys` is the right backend there.

## Why

- **It is the typed-output half of the data-flow.** PRD §4 architecture: `final model → on_final(text) → textproc.clean() → typing backend`. `textproc` (P1.M2.T2.S1) is done; this module is the next link. Without it, the daemon (P1.M4.T1.S2) has nowhere to send text.
- **Auto-fallback is a PRD §8 prescribed mitigation.** PRD §8 lists "wtype fails on some window (rare)" → mitigation "auto-fallback to ydotool (§4.3)". This item IS that fallback, made executable. The daemon never needs to know wtype failed — the wrapper handles it transparently and logs a warning.
- **Small, well-bounded, GPU-free, unblocks the daemon AND the E2E test.** Pure stdlib (`subprocess`/`logging`/`abc`) + one `OutputConfig` import. No CUDA/audio/network. The E2E test (P1.M7.T3.S1) is blocked on the tmux backend existing; the daemon (P1.M4.T1.S2) is blocked on `make_backend` existing. Finishing it here keeps both clean.
- **Testable in isolation.** The unit tests (S2) mock `subprocess.run` and assert the exact command lists + the fallback ordering — no real typing needed for unit validation. The tmux backend is additionally smoke-testable for real via a throwaway tmux pane (verified live in research §1.1).

## What

One pure-stdlib module `voice_typing/typing_backends.py` with: an abstract `TypingBackend` (ABC + `@abstractmethod type_text`), three concrete subclasses each running their PRD §4.3 subprocess with `check=True`, a private `_WtypeWithFallback` composition wrapper (primary wtype + fallback ydotool, retry-once, log on fallback, propagate if fallback fails), and `make_backend(cfg: OutputConfig) -> TypingBackend` dispatching on `cfg.backend`. The module imports only `subprocess`/`logging`/`abc` + `from voice_typing.config import OutputConfig`. Verbatim source is in Implementation Blueprint → Task 2.

### Success Criteria

- [ ] `voice_typing/typing_backends.py` exists; `.venv/bin/python -m py_compile voice_typing/typing_backends.py` exits 0.
- [ ] `import voice_typing.typing_backends` imports only `subprocess`/`logging`/`abc` + `OutputConfig` (grep-clean of `cuda_check`/`torch`/`realtimestt`/`ctranslate2`).
- [ ] `TypingBackend` is an ABC; instantiating it directly raises `TypeError`; each concrete backend subclasses it and implements `type_text`.
- [ ] `WtypeBackend.type_text` calls `subprocess.run(["wtype","--",text], check=True)`.
- [ ] `YdotoolBackend.type_text` calls `subprocess.run(["ydotool","type","--key-delay","2","--",text], check=True)`.
- [ ] `TmuxBackend(cfg).type_text` calls `subprocess.run(["/usr/bin/tmux","send-keys","-t",cfg.tmux_target,"-l","--",text], check=True)` (reads `tmux_target` from the `OutputConfig` passed at construction).
- [ ] `make_backend(OutputConfig(backend="wtype"))` returns a `_WtypeWithFallback` (is a `TypingBackend`).
- [ ] `make_backend(OutputConfig(backend="ydotool"))` returns a `YdotoolBackend`.
- [ ] `make_backend(OutputConfig(backend="tmux"))` returns a `TmuxBackend`.
- [ ] `make_backend(OutputConfig(backend="bogus"))` raises `ValueError`.
- [ ] `_WtypeWithFallback`: primary success → no fallback call; primary raises `CalledProcessError` → logs WARNING + calls fallback; primary raises `OSError` (e.g. `FileNotFoundError`) → logs WARNING + calls fallback; fallback also raises → exception propagates.
- [ ] Backends never append a newline; they type exactly `text`.
- [ ] ONLY `voice_typing/typing_backends.py` is created. Nothing else changes (no test file — S2 owns it).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: the consumed contract (`OutputConfig` in `voice_typing/config.py`) is read at preflight; the three subprocess command lists are pinned verbatim to PRD §4.3 (and verified live in research §1 + §9); the auto-fallback exception set and "retry once / propagate" semantics are pinned (research §3–4); the thread-safety argument is documented (research §5); the verbatim module source is in Implementation Blueprint → Task 2; and the validation commands (py_compile, import-purity grep, factory wiring smoke, real tmux round-trip) are executable as written. Tooling reality (pytest in venv; ruff a uv tool; mypy absent) is pinned from the prior tasks' research.

### Documentation & References

```yaml
# MUST READ — the authoritative behavior spec (the contract)
- file: PRD.md
  why: "§4.3 is the verbatim spec for the three command lists + the auto-fallback rule
        ('daemon MUST auto-fall-back to ydotool if a wtype call fails (nonzero exit),
        logging a warning'). §4 architecture diagram shows on_final -> typing backend.
        §8 names the 'wtype fails on some window (rare)' risk with mitigation
        'auto-fallback to ydotool (§4.3)'. §4.2 on_final wires textproc.clean -> backend."
  critical: "Reproduce the THREE command lists EXACTLY (incl. the literal '/usr/bin/tmux'
             full path — zsh aliases tmux). The fallback triggers on NONZERO EXIT
             (CalledProcessError) OR missing binary (OSError/FileNotFoundError). NEVER
             append a newline (PRD §4.3 last paragraph)."

# MUST READ — the consumed contract (OutputConfig). READ, do NOT edit.
- file: voice_typing/config.py
  why: "Defines OutputConfig(backend='wtype', tmux_target='', append_space=True) — the
        INPUT to make_backend(). TmuxBackend reads cfg.tmux_target. make_backend reads
        cfg.backend. append_space is the DAEMON's concern, NOT used here."
  critical: "make_backend takes OutputConfig (NOT VoiceTypingConfig) — the daemon calls
             make_backend(cfg.output). Do NOT import cuda_check/torch/realtimestt into
             typing_backends (same purity rule as config.py). Do NOT mutate the config."

# MUST READ — verified CLI facts + design (this task's research)
- docfile: plan/001_be48c74bc590/P1M3T1S1/research/typing_backends_facts_and_design.md
  why: "§1 verified tool paths + the tmux send-keys -l LIVE round-trip + the ydotool
        --key-delay space-form proof. §3 subprocess semantics (check=True is REQUIRED to
        detect nonzero exit; FileNotFoundError is an OSError). §4 the auto-fallback design
        (composition; catch (CalledProcessError, OSError); retry once; propagate on 2nd
        failure). §5 thread-safety argument (no shared state; subprocess reentrant). §6
        purity (stdlib-only). §7 S1-vs-S2 scope (S1 = impl only; S2 = tests). §8
        make_backend(OutputConfig). §9 the verbatim command lists."
  section: "ALL sections load-bearing. §1 (CLI facts), §3 (subprocess), §4 (fallback
            design), §9 (command lists), §7 (scope — do NOT write tests)."

# MUST READ — the established module style to mirror (docstring + purity + future-import)
- file: voice_typing/textproc.py
  why: "The sibling module landed by P1.M2.T2.S1. Mirror its: module docstring (plain
        present-tense, CONSUMES/CONSUMED BY/PIPELINE sections, PRD cross-refs not
        duplication), `from __future__ import annotations`, stdlib-only purity, single
        focused responsibility, and the 'caller owns the trailing space' rule
        (textproc.clean returns text verbatim; the daemon appends the space — same rule
        applies to backends: type exactly the text given)."
  critical: "Mirror textproc.py's docstring STRUCTURE (CONSUMES/CONSUMED BY) and its
             purity rule (no heavy deps). The trailing-space ownership is split across
             textproc (no space) -> daemon appends space -> backend types verbatim."

# Background — machine facts (READ-ONLY context; the tmux/wtype/ydotool/zsh-alias facts)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1: wtype/ydotool present; ydotoold user service; /dev/uinput crw-rw-rw-, user in
        input group; /usr/bin/tmux (zsh aliases tmux -> ALWAYS full path); shell aliases
        -> ALWAYS full paths (.venv/bin/python). §2 file map: typing_backends.py lives at
        voice_typing/typing_backends.py. §3 data-flow: on_final -> textproc.clean -> type
        text+' '. §4 decision #5: textproc owns cleanup (RealtimeSTT post-proc disabled)."
  critical: "Use /usr/bin/tmux literally in the TmuxBackend command list (zsh aliases tmux).
             Use .venv/bin/python explicitly for validation (never bare python/pytest)."

# Downstream — the consumer contracts this item feeds (future work, do not build)
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M4.T1.S2 (daemon on_final) will call: backend = typing_backends.make_backend(
        cfg.output); then on each final: backend.type_text(text + (' ' if cfg.output.
        append_space else '')). P1.M7.T3.S1 (E2E) sets backend='tmux' and reads the pane via
        capture-pane. Confirms make_backend takes the OutputConfig SUB-config and that
        append_space is the daemon's job (backends type the text given)."
  critical: "Do NOT add append_space logic into the backends — the daemon owns it. The
             backends type exactly the string handed to type_text() (no newline, no space)."
```

### Current Codebase tree (state at P1.M3.T1.S1 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*'` from repo root. Expected after P1.M2.* lands (config.py + textproc.py done; tests for them present):

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores dist/, *.pyc, __pycache__/, .venv/, .pytest_cache/ (DO NOT touch)
├── .venv/                      # Python 3.12.10; pytest 9.1.1 installed (dev group)
├── PRD.md                      # READ-ONLY
├── config.toml                 # ← P1.M2.T1.S2 output (default config). DO NOT touch.
├── pyproject.toml              # dev = ["pytest>=9.1.1"] (DO NOT touch; no new deps needed)
├── uv.lock                     # DO NOT touch
├── voice_typing/
│   ├── __init__.py             # package docstring
│   ├── cuda_check.py           # P1.M1.T2.S2 (unrelated)
│   ├── launch_daemon.sh        # P1.M1.T2.S1 (unrelated)
│   ├── prefetch.py             # P1.M1.T3.S1 (unrelated)
│   ├── config.py               # ← P1.M2.T1.S1 output (OutputConfig lives HERE). READ but DO NOT EDIT.
│   └── textproc.py             # ← P1.M2.T2.S1 output (STYLE TEMPLATE to mirror). DO NOT EDIT.
└── tests/
    ├── test_config.py                # ← P1.M2.T1.S1 output. DO NOT EDIT.
    ├── test_config_repo_default.py   # ← P1.M2.T1.S2 output. DO NOT EDIT.
    └── test_textproc.py              # ← P1.M2.T2.S1 output. DO NOT EDIT.
# NO voice_typing/typing_backends.py yet — Task 2 creates it (the ONLY new file).
# NO tests/test_typing_backends.py — that is P1.M3.T1.S2 (NEXT task). DO NOT create it here.
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
└── voice_typing/
    └── typing_backends.py      # ← CREATE (Task 2): TypingBackend ABC + Wtype/Ydotool/Tmux + _WtypeWithFallback + make_backend
# NOTHING ELSE. No test file (S2 owns tests/test_typing_backends.py). No tests/__init__.py
# (pytest discovers test_*.py without it). No edits to config.py (S1 owns OutputConfig;
# this module only imports it). No daemon/feedback/ctl/config.toml/install.sh/systemd.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — `check=True` IS REQUIRED FOR THE AUTO-FALLBACK. PRD §4.3 lists the command
#   lists as `subprocess.run([...])`; the auto-fallback contract ("on subprocess non-zero
#   exit / FileNotFoundError") needs to DETECT nonzero exit. Without check=True,
#   subprocess.run returns a CompletedProcess with returncode!=0 but DOES NOT raise, so the
#   fallback would never trigger. check=True makes nonzero exit raise CalledProcessError,
#   which the wrapper catches. The COMMAND LIST is unchanged from PRD §4.3 — only check=True
#   is added, and it is load-bearing. (Research §3, §9.)

# CRITICAL #2 — `/usr/bin/tmux` LITERAL, NEVER bare `tmux`. zsh aliases `tmux` to a plugin
#   wrapper. subprocess.run(["tmux", ...]) from a zsh-launched process would resolve to the
#   alias's underlying path inconsistently; the FULL PATH is deterministic and matches PRD
#   §4.3 verbatim. (system_context.md §1; Research §1.) Define it once as a module constant
#   `_TMUX = "/usr/bin/tmux"` and use it in TmuxBackend.

# CRITICAL #3 — FileNotFoundError IS AN OSError. The item says "non-zero exit /
#   FileNotFoundError". Missing binary raises FileNotFoundError; an unexecutable binary
#   raises PermissionError; both are OSError subclasses. Catch (subprocess.CalledProcessError,
#   OSError) — OSError covers the whole "binary unusable" family. Do NOT narrow to only
#   FileNotFoundError (a PermissionError on wtype would then crash instead of falling back).
#   (Research §3, §4.)

# CRITICAL #4 — RETRY ONCE, THEN PROPAGATE. The wrapper calls the fallback EXACTLY once. If
#   ydotool ALSO raises (e.g. ydotool missing too), the exception PROPAGATES to the caller —
#   do NOT wrap it in a bare `except Exception` that swallows it. The daemon (P1.M4.T1.S2)
#   logs/handles propagated failures. Silent swallow of a total failure is a bug. (Research §4.)

# CRITICAL #5 — NEVER APPEND A NEWLINE. PRD §4.3 last paragraph: "Never send Enter/newline
#   unless the utterance-final text itself demands it — it never should; strip trailing
#   newlines in textproc." textproc.clean() already collapsed whitespace and stripped
#   trailing newlines. type_text() must type EXACTLY its argument — no trailing \n, no
#   trailing space. The DAEMON appends a single " " when cfg.output.append_space (not the
#   backend). For tmux specifically: `send-keys -l` types literal text WITHOUT a trailing
#   Enter (that is the `-l` flag's purpose — do NOT drop `-l` or tmux would interpret key
#   names and you might accidentally send Enter). (Research §1.1; PRD §4.3.)

# CRITICAL #6 — PURE STDLIB + OutputConfig. typing_backends.py imports only subprocess,
#   logging, abc, and `from voice_typing.config import OutputConfig`. It must NOT import
#   cuda_check / torch / ctranslate2 / realtimestt — it must load in CPU-only and test
#   contexts (S2 mocks subprocess.run; the module must import without a GPU). Same purity
#   rule as config.py + textproc.py. (Research §6; textproc.py module docstring.)

# CRITICAL #7 — THREAD-SAFE BY CONSTRUCTION (no locks needed). type_text is called from the
#   on_final callback thread (P1.M4.T1.S2). Backends hold NO shared mutable state: Wtype/
#   Ydotool are stateless; TmuxBackend stores one immutable _tmux_target str at __init__.
#   subprocess.run spawns an independent child process per call (reentrant). The daemon
#   serializes on_final calls anyway. Do NOT add a threading.Lock — it would be dead weight
#   and could deadlock if a future caller recurses. Document the argument in the docstring.
#   (Research §5.)

# CRITICAL #8 — make_backend TAKES OutputConfig, NOT VoiceTypingConfig. The item INPUT is
#   explicitly OutputConfig(backend, tmux_target, append_space). The daemon calls
#   make_backend(cfg.output). append_space is NOT read here (daemon's job). If you accept
#   the whole VoiceTypingConfig you break the documented contract + the daemon wiring.
#   (Research §8; item INPUT.)

# CRITICAL #9 — `--` SEPARATOR IS LOAD-BEARING for wtype and ydotool. `wtype -- "text"` and
#   `ydotool type ... -- text` ensure that text beginning with a `-` is treated as a
#   positional (literal text), not parsed as an option. Without `--`, typing "-5 degrees"
#   could make wtype/ydotool error on the "-5". For tmux, `--` before the keys is the
#   standard send-keys guard. Keep `--` in all three command lists verbatim. (PRD §4.3; Research §9.)

# CRITICAL #10 — ydotool `--key-delay 2` (SPACE FORM) IS CORRECT. The man page documents
#   `type [-d,--key-delay <ms>] "text"` (space form); GNU argp accepts both `--key-delay 2`
#   and `--key-delay=2`. The PRD §4.3 verbatim form is the space form. Do NOT "fix" it to
#   `--key-delay=2` — match PRD §4.3 exactly. (S2 mocks subprocess.run so it asserts the
#   LIST; E2E (P1.M7.T3.S1) validates real execution.) (Research §1.2.)

# CRITICAL #11 — S1 IS IMPL ONLY; DO NOT WRITE TESTS. The plan deliberately split P1.M3.T1
#   into S1 (this: typing_backends.py) and S2 (tests/test_typing_backends.py). Creating a
#   test file here would collide with S2. S1 validates via py_compile + import-purity +
#   the factory/tmux smokes in the Validation Loop (L1 + L3) — NOT a committed pytest file.
#   (Research §7.)

# GOTCHA #12 — TypingBackend MUST BE UNINSTANTIABLE. It is an ABC with @abstractmethod
#   type_text. `TypingBackend()` must raise TypeError (proves it is abstract). Concrete
#   backends subclass + implement type_text. Use `from abc import ABC, abstractmethod`.
#   (Standard Python ABC; Research §4.)

# GOTCHA #13 — FULL PATHS for tooling (zsh aliases python/pip/tmux). Always
#   .venv/bin/python -m pytest / .venv/bin/python -m py_compile (never bare python/pytest).
#   ruff, if used as an OPTIONAL lint, is at /home/dustin/.local/bin/ruff (NOT in .venv).
#   mypy is NOT installed anywhere — do NOT list it as a gate. (Prior tasks' research §5.)

# GOTCHA #14 — `_WtypeWithFallback` SHOULD ACCEPT OPTIONAL primary/fallback. Default to
#   WtypeBackend()/YdotoolBackend() so make_backend needs no args, but allow injection so
#   S2 can pass fakes to assert fallback ORDERING deterministically (without depending on
#   subprocess.run's call sequence). Constructor: __init__(self, primary=None, fallback=None).
#   (Research §4.)
```

## Implementation Blueprint

### Data models and structure

No new data model. The module consumes the existing `OutputConfig` dataclass from `voice_typing/config.py` (P1.M2.T1.S1) and defines an abstract base + three concrete backends. The contract is the class hierarchy + the `make_backend` factory:

```python
class TypingBackend(ABC):                      # abstract — uninstantiable
    @abstractmethod
    def type_text(self, text: str) -> None: ...   # type exactly `text`; raise on failure

class WtypeBackend(TypingBackend): ...         # subprocess.run(["wtype","--",text], check=True)
class YdotoolBackend(TypingBackend): ...       # subprocess.run(["ydotool","type","--key-delay","2","--",text], check=True)
class TmuxBackend(TypingBackend):              # __init__(cfg: OutputConfig) stores cfg.tmux_target
    ...                                        # subprocess.run(["/usr/bin/tmux","send-keys","-t",target,"-l","--",text], check=True)
class _WtypeWithFallback(TypingBackend):       # private; primary wtype + fallback ydotool
    ...                                        # retry once on (CalledProcessError, OSError); propagate on 2nd failure

def make_backend(cfg: OutputConfig) -> TypingBackend: ...   # dispatch on cfg.backend
```

`OutputConfig` fields used: `cfg.backend: str` (default `"wtype"`, selects impl), `cfg.tmux_target: str` (default `""`, used only by TmuxBackend). `cfg.append_space` is NOT used here (daemon's job).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm inputs exist and target does not (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/config.py && echo "ok: config.py exists (OutputConfig source)" || echo "PREFLIGHT FAIL"
      test -f voice_typing/textproc.py && echo "ok: textproc.py exists (style template)" || echo "PREFLIGHT FAIL"
      test ! -e voice_typing/typing_backends.py && echo "ok: typing_backends.py not yet created" || echo "PREFLIGHT FAIL: target exists"
      test ! -e tests/test_typing_backends.py && echo "ok: tests/test_typing_backends.py not yet created (S2 owns it)" || echo "PREFLIGHT FAIL: S2 test file exists"
      .venv/bin/python -c "from voice_typing.config import OutputConfig; c=OutputConfig(); print('OutputConfig OK', c.backend, repr(c.tmux_target), c.append_space)" || echo "PREFLIGHT FAIL"
      .venv/bin/python -c "import subprocess; from subprocess import CalledProcessError; print('subprocess OK')"
      command -v wtype >/dev/null && echo "ok: wtype present" || echo "note: wtype not on PATH (fallback path still imports fine)"
      command -v ydotool >/dev/null && echo "ok: ydotool present" || echo "note: ydotool not on PATH (fallback path still imports fine)"
      ls -l /usr/bin/tmux >/dev/null 2>&1 && echo "ok: /usr/bin/tmux present" || echo "note: /usr/bin/tmux absent (TmuxBackend smoke will skip)"
  - EXPECTED: config.py + textproc.py present; typing_backends.py + tests/test_typing_backends.py absent;
    OutputConfig OK prints `wtype '' True`; subprocess OK; wtype/ydotool/tmux present on this machine.
  - DO NOT: create typing_backends.py yet, create any test file, run uv sync/add, or touch any other file.

Task 2: CREATE voice_typing/typing_backends.py — use the `write` tool with EXACTLY the
        content in "Task 2 SOURCE" below (verbatim).
  - FILE: voice_typing/typing_backends.py
  - CONTENT: module docstring + `from __future__ import annotations` + imports (subprocess,
    logging, abc, OutputConfig) + `_TMUX` constant + TypingBackend ABC + WtypeBackend +
    YdotoolBackend + TmuxBackend + _WtypeWithFallback + make_backend.
  - DO NOT: import cuda_check/torch/realtimestt (Gotcha #6); drop `--` from any command
    list (Gotcha #9); change ydotool to `--key-delay=2` (Gotcha #10); use bare `tmux`
    (Gotcha #2); add append_space logic (Critical #5); swallow the fallback's exception
    (Critical #4); add a threading.Lock (Critical #7); create any test file (Critical #11).

Task 3: VALIDATE — run the Validation Loop L1 (py_compile + import purity) and L3
        (factory wiring smoke + real tmux round-trip). Iterate until all gates pass.
        L2 (committed unit tests) is OWNED BY S2 (P1.M3.T1.S2) — do NOT create a test file.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M3.T1.S1: typing_backends.py (TypingBackend ABC + wtype/ydotool/tmux + auto-fallback + make_backend)".
```

#### Task 2 SOURCE — `voice_typing/typing_backends.py` (write verbatim)

```python
"""voice_typing.typing_backends — typing output backends (PRD §4.3).

type_text(text) sends finalized, textproc-cleaned text to the focused window (or a
tmux pane) via one of three backends, selected by config output.backend:

  - wtype    (default): Wayland virtual-keyboard-v1. Full Unicode, no layout issues.
             Types into the focused window incl. terminals/tmux.
  - ydotool: uinput-level. Works for XWayland apps; known weakness: non-ASCII / layout
             quirks. Kept as the auto-fallback when wtype fails.
  - tmux:    tmux send-keys -l into an explicit target pane. Used by the E2E test and
             for SSH/detached use.

AUTO-FALLBACK (PRD §4.3 + §8 risk "wtype fails on some window"): make_backend() returns
a wrapper for backend=="wtype" that runs wtype, and on a nonzero exit or a missing/
unusable binary (subprocess.CalledProcessError / OSError, which includes FileNotFoundError)
logs a WARNING and retries ONCE via ydotool. If the fallback also raises, the exception
propagates to the caller (the daemon logs/handles it) — it is never silently swallowed.

THREAD SAFETY: type_text is safe to call from the daemon's on_final callback thread.
The backends hold NO shared mutable state (Wtype/Ydotool are stateless; TmuxBackend
stores one immutable tmux_target at construction), and subprocess.run spawns an
independent child process per call (reentrant). The daemon serializes on_final calls,
so no locking is needed.

NEVER EMIT ENTER/NEWLINE: the backends type EXACTLY the text passed (no trailing
newline). textproc.clean() already stripped trailing newlines/whitespace; the daemon
appends a single trailing space when output.append_space (not the backend). For tmux,
the `-l` flag makes send-keys treat the keys as literal text (no key-name interpretation,
no trailing Enter) — do not drop it.

CONSUMES: voice_typing.config.OutputConfig (P1.M2.T1.S1): backend, tmux_target.
  append_space is the DAEMON's concern (not used here).
CONSUMED BY: daemon on_final (P1.M4.T1.S2) as:
    backend = typing_backends.make_backend(cfg.output)
    backend.type_text(text + (" " if cfg.output.append_space else ""))
  and the E2E test (P1.M7.T3.S1) via backend="tmux".

PURE STDLIB (subprocess, logging, abc, OutputConfig). No cuda_check / torch /
realtimestt / ctranslate2 — loads in CPU-only and test contexts; subprocess.run is
mocked in unit tests (P1.M3.T1.S2).
"""
from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod

from voice_typing.config import OutputConfig

logger = logging.getLogger(__name__)

# Full path: zsh aliases `tmux` to a plugin wrapper. ALWAYS invoke the real binary in
# subprocess (PRD §4.3; system_context.md §1).
_TMUX = "/usr/bin/tmux"


class TypingBackend(ABC):
    """Abstract typing backend (PRD §4.3). type_text sends text to the target."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type `text` exactly (no trailing newline). Raise on failure.

        Implementations run a subprocess (wtype/ydotool/tmux). Failures surface as
        subprocess.CalledProcessError (nonzero exit) or OSError (missing/unusable
        binary). The auto-fallback wrapper (for wtype) catches these and retries
        via ydotool; other backends let exceptions propagate to the caller.
        """
        raise NotImplementedError


class WtypeBackend(TypingBackend):
    """wtype: Wayland virtual-keyboard-v1. Full Unicode. The default backend."""

    def type_text(self, text: str) -> None:
        # `--` separates options from text so text starting with '-' is literal.
        # check=True -> nonzero exit raises CalledProcessError, caught by the
        # auto-fallback wrapper. A missing wtype binary raises FileNotFoundError
        # (an OSError), also caught by the fallback.
        subprocess.run(["wtype", "--", text], check=True)


class YdotoolBackend(TypingBackend):
    """ydotool type: uinput-level. Fallback; non-ASCII/layout quirks (PRD §4.3)."""

    def type_text(self, text: str) -> None:
        # --key-delay 2: 2ms between key events (PRD §4.3 verbatim; man ydotool
        # documents the space form `--key-delay <ms>`; GNU argp accepts it).
        subprocess.run(
            ["ydotool", "type", "--key-delay", "2", "--", text], check=True
        )


class TmuxBackend(TypingBackend):
    """tmux send-keys -l into an explicit target pane. E2E test / SSH backend."""

    def __init__(self, cfg: OutputConfig) -> None:
        # tmux_target may be "" (active pane of most recent client) or explicit,
        # e.g. "voicetest:0.0". -l treats the keys as literal text (no key-name
        # interpretation), so punctuation is typed verbatim and no Enter is sent.
        self._tmux_target = cfg.tmux_target

    def type_text(self, text: str) -> None:
        subprocess.run(
            [_TMUX, "send-keys", "-t", self._tmux_target, "-l", "--", text],
            check=True,
        )


class _WtypeWithFallback(TypingBackend):
    """wtype primary, ydotool fallback (PRD §4.3 auto-fallback; §8 risk).

    Runs wtype; on a nonzero exit (CalledProcessError) or a missing/unusable binary
    (OSError, which includes FileNotFoundError), logs a WARNING and retries ONCE via
    ydotool. If the fallback also raises, the exception propagates to the caller
    (daemon logs/handles it) — never silently swallowed.
    """

    def __init__(
        self,
        primary: TypingBackend | None = None,
        fallback: TypingBackend | None = None,
    ) -> None:
        # Optional injection lets unit tests (P1.M3.T1.S2) swap in fakes to assert
        # fallback ORDERING deterministically; defaults are the real backends.
        self._primary = primary if primary is not None else WtypeBackend()
        self._fallback = fallback if fallback is not None else YdotoolBackend()

    def type_text(self, text: str) -> None:
        try:
            self._primary.type_text(text)
        except (subprocess.CalledProcessError, OSError) as exc:
            # OSError covers FileNotFoundError (binary missing) and PermissionError
            # (binary not executable); CalledProcessError covers nonzero exit. A
            # bug raising, e.g., TypeError is NOT caught here — let it surface.
            logger.warning(
                "wtype typing failed (%s); retrying once via ydotool", exc
            )
            self._fallback.type_text(text)  # may raise -> propagates (one retry only)


def make_backend(cfg: OutputConfig) -> TypingBackend:
    """Select a typing backend from output.backend (PRD §4.3).

    Args:
        cfg: the [output] config (backend, tmux_target). append_space is the
            daemon's concern and is NOT used here.

    Returns:
        - backend == "wtype"   -> wtype with auto-fallback to ydotool (default)
        - backend == "ydotool" -> ydotool (no further fallback)
        - backend == "tmux"    -> tmux send-keys into cfg.tmux_target

    Raises:
        ValueError: unknown backend name.
    """
    backend = cfg.backend
    if backend == "wtype":
        return _WtypeWithFallback()
    if backend == "ydotool":
        return YdotoolBackend()
    if backend == "tmux":
        return TmuxBackend(cfg)
    raise ValueError(f"unknown output.backend: {backend!r}")
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — ABC for the interface; concrete subclasses implement type_text. TypingBackend
# is uninstantiable (proves it is abstract); make_backend returns one of the concretes.
class TypingBackend(ABC):
    @abstractmethod
    def type_text(self, text: str) -> None: ...
class WtypeBackend(TypingBackend):
    def type_text(self, text): ...   # implements the abstract method

# PATTERN 2 — check=True turns nonzero exit into a catchable exception. The auto-fallback
# NEEDS to detect nonzero exit; without check=True, subprocess.run silently returns
# returncode!=0 and the fallback never fires. The command LIST is unchanged from PRD §4.3.
subprocess.run(["wtype", "--", text], check=True)   # raises CalledProcessError on nonzero

# PATTERN 3 — composition for the fallback (NOT inheritance hack). The wrapper holds a
# primary + fallback backend; catching (CalledProcessError, OSError) on the primary triggers
# exactly one fallback call. Optional constructor args let tests inject fakes.
self._primary = primary or WtypeBackend()
self._fallback = fallback or YdotoolBackend()
try: self._primary.type_text(text)
except (subprocess.CalledProcessError, OSError) as exc:
    logger.warning("wtype failed (%s); retrying via ydotool", exc)
    self._fallback.type_text(text)   # if THIS raises, it propagates (one retry only)

# PATTERN 4 — OSError as the "binary unusable" catch-all. FileNotFoundError is the common
# case (binary not installed); PermissionError (not executable) is rarer. Both are OSError.
# Catching OSError covers the family; catching only FileNotFoundError would miss the rare
# case and crash instead of falling back.
except (subprocess.CalledProcessError, OSError):   # NOT `except Exception` (too broad)

# PATTERN 5 — full path for tmux (zsh aliases it). Pin once as a module constant.
_TMUX = "/usr/bin/tmux"
subprocess.run([_TMUX, "send-keys", "-t", target, "-l", "--", text], check=True)

# PATTERN 6 — thread-safe by construction (no locks). Backends hold no shared mutable
# state; subprocess.run is reentrant (independent child per call). Document the argument;
# do NOT add a threading.Lock.
```

### Integration Points

```yaml
IMPORTS:
  - add to: voice_typing/typing_backends.py (NEW)
  - pattern: |
      import logging, subprocess
      from abc import ABC, abstractmethod
      from voice_typing.config import OutputConfig   # the sole project import

CONSUMER (future — P1.M4.T1.S2, daemon.on_final; DO NOT build here):
  - construct: "backend = typing_backends.make_backend(cfg.output)"   # called ONCE at startup
  - per final: "backend.type_text(text + (' ' if cfg.output.append_space else ''))"

CONSUMER (future — P1.M7.T3.S1, E2E test):
  - config: 'output.backend = "tmux"; output.tmux_target = "<test session>:0.0"'
  - assert: capture-pane reads back the typed text (fuzzy token overlap per PRD §8).

CONFIG: none — make_backend reads cfg.backend and cfg.tmux_target at call time; it adds no
  config keys and changes no defaults. append_space is consumed by the daemon, not here.

DEPENDENCIES: none new (stdlib only; OutputConfig already exists). No pyproject.toml /
  uv.lock changes (the dev pytest dep was added in P1.M2.T1.S1).
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases — system_context.md §1). Run from
> `/home/dustin/projects/voice-typing`. L1 is instant. L2 (committed unit tests) is OWNED
> BY S2 (P1.M3.T1.S2) — do NOT create a test file here. L3 is a manual smoke that proves
> the wiring + a real tmux round-trip. L4 is the scope guard.

### Level 1: Syntax + import-cleanness (no deps needed beyond stdlib)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f voice_typing/typing_backends.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile voice_typing/typing_backends.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
# THE KEY IMPORT TEST: importing must pull ONLY stdlib + OutputConfig (no cuda_check/torch/realtimestt):
"$PY" -c "import voice_typing.typing_backends as m; print('L1 import OK'); print(' classes:', [c for c in dir(m) if c[0].isupper()]); print(' make_backend:', m.make_backend)" \
  && echo "L1 PASS: importable, pure-stdlib" \
  || echo "L1 FAIL: import raised (heavy dep leaked?)"
# Verify NO forbidden imports (must be pure stdlib + OutputConfig):
grep -nE 'import (cuda_check|torch|realtimestt|ctranslate2)' voice_typing/typing_backends.py && echo "L1 FAIL: forbidden import found" || echo "L1 PASS: no forbidden imports"
# Expected: file present; py_compile OK; import OK (lists TypingBackend/WtypeBackend/YdotoolBackend/TmuxBackend
#   + make_backend — _WtypeWithFallback is private, dir() still shows it but that's fine); no forbidden imports.
```

### Level 2: Unit Tests (component validation) — OWNED BY P1.M3.T1.S2

```bash
# S2 (the NEXT task) writes tests/test_typing_backends.py with subprocess.run MOCKED.
# S1 does NOT create that file. After S2 lands, the gate will be:
#   .venv/bin/python -m pytest tests/test_typing_backends.py -v
# For S1, the equivalent wiring proof is the L3 smoke below (no committed test file).
```

### Level 3: Integration smoke (factory dispatch + real tmux round-trip)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python

# 3a — factory wiring: each backend value returns the right class; unknown raises ValueError.
"$PY" - <<'PY'
from voice_typing.config import OutputConfig
from voice_typing import typing_backends as tb
# wtype -> the auto-fallback wrapper (a TypingBackend holding a WtypeBackend + YdotoolBackend)
w = tb.make_backend(OutputConfig(backend="wtype"))
assert isinstance(w, tb.TypingBackend), "wtype result must be a TypingBackend"
assert hasattr(w, "_primary") and hasattr(w, "_fallback"), "wtype result must be the fallback wrapper"
assert isinstance(w._primary, tb.WtypeBackend) and isinstance(w._fallback, tb.YdotoolBackend)
# ydotool -> YdotoolBackend
y = tb.make_backend(OutputConfig(backend="ydotool"))
assert isinstance(y, tb.YdotoolBackend), f"ydotool -> {type(y).__name__}"
# tmux -> TmuxBackend (carries tmux_target)
t = tb.make_backend(OutputConfig(backend="tmux", tmux_target="voicetest_z:0.0"))
assert isinstance(t, tb.TmuxBackend) and t._tmux_target == "voicetest_z:0.0"
# unknown -> ValueError
try:
    tb.make_backend(OutputConfig(backend="bogus")); raise SystemExit("FAIL: no ValueError")
except ValueError as e:
    assert "bogus" in str(e), e
# TypingBackend is abstract (uninstantiable)
try:
    tb.TypingBackend(); raise SystemExit("FAIL: ABC instantiated")
except TypeError:
    pass
print("L3a PASS: factory dispatch + ABC abstractness correct")
PY

# 3b — auto-fallback logic WITHOUT real typing: inject fakes, assert ordering.
"$PY" - <<'PY'
import subprocess
from voice_typing import typing_backends as tb
calls = []
class FakeOK(tb.TypingBackend):
    def type_text(self, text): calls.append(("ok", text))
class FakeFail(tb.TypingBackend):
    def type_text(self, text):
        calls.append(("fail", text))
        raise subprocess.CalledProcessError(1, ["wtype"])
class FakeMissing(tb.TypingBackend):
    def type_text(self, text):
        calls.append(("missing", text))
        raise FileNotFoundError(2, "no wtype")
# primary succeeds -> fallback NOT called
calls.clear(); tb._WtypeWithFallback(primary=FakeOK(), fallback=FakeFail()).type_text("hi")
assert calls == [("ok", "hi")], calls
# primary nonzero exit -> fallback called once
calls.clear(); tb._WtypeWithFallback(primary=FakeFail(), fallback=FakeOK()).type_text("hi")
assert calls == [("fail", "hi"), ("ok", "hi")], calls
# primary missing binary (OSError) -> fallback called once
calls.clear(); tb._WtypeWithFallback(primary=FakeMissing(), fallback=FakeOK()).type_text("hi")
assert calls == [("missing", "hi"), ("ok", "hi")], calls
# BOTH fail -> second exception propagates (one retry only, no swallow)
calls.clear()
try:
    tb._WtypeWithFallback(primary=FakeFail(), fallback=FakeFail()).type_text("hi")
    raise SystemExit("FAIL: propagated exception was swallowed")
except subprocess.CalledProcessError:
    assert calls == [("fail","hi"), ("fail","hi")], calls
print("L3b PASS: auto-fallback ordering + propagate-on-second-failure correct")
PY

# 3c — REAL tmux round-trip (the one backend safe to execute: types into a throwaway pane).
"$PY" - <<'PY'
import subprocess, time
from voice_typing.config import OutputConfig
from voice_typing.typing_backends import make_backend, TmuxBackend
sess = "voicetest_l3c"
subprocess.run(["/usr/bin/tmux", "new-session", "-d", "-s", sess], check=True)
try:
    b = make_backend(OutputConfig(backend="tmux", tmux_target=sess))
    assert isinstance(b, TmuxBackend)
    b.type_text("Hello tmux literal 123")          # send-keys -l
    time.sleep(0.2)
    pane = subprocess.check_output(["/usr/bin/tmux","capture-pane","-t",sess,"-p"], text=True)
    assert "Hello tmux literal 123" in pane, pane
    print("L3c PASS: TmuxBackend round-trip typed literal text into the pane")
finally:
    subprocess.run(["/usr/bin/tmux", "kill-session", "-t", sess], check=False)
PY

# Expected: L3a, L3b, L3c each print "PASS". L3c proves the tmux command list + -l flag
#   work end-to-end against the real /usr/bin/tmux (no Enter emitted; literal text only).
```

### Level 4: Creative & Domain-Specific Validation

```bash
cd /home/dustin/projects/voice-typing
# SCOPE GUARD — confirm ONLY typing_backends.py was created (no test file, no other edits).
test -f voice_typing/typing_backends.py && echo "L4 ok: impl present" || echo "L4 FAIL"
test ! -e tests/test_typing_backends.py && echo "L4 ok: no test file (S2 owns it)" || echo "L4 FAIL: test file created (out of scope)"
git status --porcelain | grep -E 'typing_backends\.py$' && echo "L4 ok: only typing_backends.py changed" || echo "L4 note: check git status for unexpected changes"
# git status should show ONLY: ?? voice_typing/typing_backends.py   (one new untracked file)
# Any modification to config.py/textproc.py/config.toml/pyproject.toml/uv.lock/PRD.md is a SCOPE VIOLATION.

# DOMAIN NOTE — real wtype/ydotool typing is intentionally NOT exercised here:
#   - wtype types into the FOCUSED window (would disrupt the user's session) — skip.
#   - ydotool types via uinput into the focused window — skip.
#   Both are validated by the E2E test (P1.M7.T3.S1, which uses backend="tmux" anyway) and
#   by manual usage once the daemon exists (P1.M4). The unit tests (S2) mock subprocess.run.
#   ydotoold is currently `inactive` (systemctl --user is-active ydotoold) — starting it is
#   install.sh's (P1.M6) + the systemd unit's (P1.M6.T1.S2) job, NOT this task's.
```

## Final Validation Checklist

### Technical Validation

- [ ] `.venv/bin/python -m py_compile voice_typing/typing_backends.py` → exit 0.
- [ ] `import voice_typing.typing_backends` succeeds; grep finds NO `cuda_check`/`torch`/`realtimestt`/`ctranslate2` imports.
- [ ] L3a smoke prints `PASS` (factory dispatch: wtype→wrapper, ydotool→YdotoolBackend, tmux→TmuxBackend, bogus→ValueError; `TypingBackend()` raises TypeError).
- [ ] L3b smoke prints `PASS` (auto-fallback ordering: success→no fallback; CalledProcessError→fallback once; OSError→fallback once; both-fail→propagate).
- [ ] L3c smoke prints `PASS` (real tmux `send-keys -l` round-trip into a throwaway pane; literal text only, no Enter).
- [ ] L4 scope guard: ONLY `voice_typing/typing_backends.py` created; NO `tests/test_typing_backends.py`; no edits to config.py/textproc.py/config.toml/pyproject.toml/uv.lock.

### Feature Validation

- [ ] Three command lists match PRD §4.3 verbatim: `["wtype","--",text]`, `["ydotool","type","--key-delay","2","--",text]`, `["/usr/bin/tmux","send-keys","-t",tmux_target,"-l","--",text]` (with `check=True` added).
- [ ] Auto-fallback triggers on `CalledProcessError` (nonzero exit) AND `OSError` (⊇ FileNotFoundError); logs a WARNING; retries ONCE.
- [ ] If the fallback (ydotool) also raises, the exception propagates (not swallowed).
- [ ] Backends never append a newline or trailing space (type exactly `text`).
- [ ] `make_backend` takes `OutputConfig` (not `VoiceTypingConfig`); reads `backend` + `tmux_target`; does not read `append_space`.
- [ ] `type_text` is thread-safe by construction (no shared mutable state; no locks).

### Code Quality Validation

- [ ] Module docstring mirrors `textproc.py`'s structure (CONSUMES / CONSUMED BY / purity / thread-safety sections; PRD cross-refs not duplication).
- [ ] `from __future__ import annotations`; stdlib-only + the single `OutputConfig` import.
- [ ] `_TMUX = "/usr/bin/tmux"` module constant (never bare `tmux`).
- [ ] `_WtypeWithFallback` accepts optional `primary`/`fallback` for testability (S2).
- [ ] File placement matches the desired tree (`voice_typing/typing_backends.py` only).
- [ ] No new dependencies; no edits to `pyproject.toml`/`uv.lock`.

### Documentation & Deployment

- [ ] Module docstring documents the three backends, the auto-fallback rule, thread safety, the "never emit Enter/newline" rule, and the daemon/E2E consumer contracts.
- [ ] No new env vars, no config keys, no user-facing surface (item DOCS: "none" — backend selection is the `config.toml` surface owned by P1.M2.T1.S2; README troubleshooting for wtype-vs-ydotool is P2.M1.T2.S1).

---

## Anti-Patterns to Avoid

- ❌ Don't drop `check=True` — without it, nonzero exit is undetectable and the auto-fallback never fires.
- ❌ Don't use bare `tmux` — zsh aliases it; always `/usr/bin/tmux` (PRD §4.3 verbatim).
- ❌ Don't narrow the fallback catch to only `FileNotFoundError` — `PermissionError` and other `OSError`s should also fall back; catch `(CalledProcessError, OSError)`.
- ❌ Don't `except Exception` to swallow the fallback's failure — retry ONCE, then let it propagate (the daemon logs it).
- ❌ Don't append a newline/space in `type_text` — type exactly `text`; the daemon owns `append_space`; textproc owns trailing-newline stripping.
- ❌ Don't drop the `-l` flag from `tmux send-keys` — without it tmux interprets key names and may send Enter; `-l` = literal text.
- ❌ Don't drop the `--` separator from any command list — text starting with `-` must be treated as positional, not an option.
- ❌ Don't "fix" `--key-delay 2` to `--key-delay=2` — match PRD §4.3 verbatim (man page documents the space form; GNU argp accepts it).
- ❌ Don't import cuda_check/torch/realtimestt into typing_backends — it must stay pure-stdlib (test/CPU-loadable).
- ❌ Don't make `make_backend` take `VoiceTypingConfig` — the contract is `OutputConfig` (the daemon calls `make_backend(cfg.output)`).
- ❌ Don't add a `threading.Lock` — backends are stateless/reentrant by construction; a lock is dead weight and a deadlock risk.
- ❌ Don't create `tests/test_typing_backends.py` — that is P1.M3.T1.S2 (the next task); S1 is impl-only.
- ❌ Don't run `mypy` — it is not installed (would fail); py_compile + the L3 smokes are the authoritative gates.

---

## Confidence Score

**9/10** for one-pass implementation success.

Rationale: the module is ~70 lines of straightforward stdlib (`subprocess.run` + ABC + a try/except wrapper + a factory dispatch). The three command lists are pinned verbatim to PRD §4.3 and verified live (tmux `send-keys -l` round-tripped real text; ydotool space-form proven via man page + parsing probe; wtype path confirmed). The auto-fallback semantics (catch set, retry-once, propagate) are fully specified, and the L3 smokes prove the wiring + fallback ordering + a real tmux execution deterministically. The −1 reserves: (a) real wtype/ydotool execution is deferred to the E2E test (intentional — they type into the focused window), and (b) the committed unit tests are S2's deliverable, so S1's safety net is the L3 smokes rather than a full pytest suite. Both are by-design scope boundaries, not gaps.

# PRP — P1.M2.T2.S1: `clean(text)` implementation + `tests/test_textproc.py` (PRD test T2)

## Goal

**Feature Goal**: Ship `voice_typing/textproc.py` exposing `clean(text: str, cfg: FilterConfig) -> str | None`, the **post-recognition text normalizer + Whisper-hallucination filter** specified verbatim by PRD §4.7. It is the project's primary defense against Whisper's silence-hallucination ("thank you." on silent audio — a **top-3 project risk**, PRD §8). Pair it with `tests/test_textproc.py`, which **IS PRD test T2** (§6) and must pass before this item is done. Pure stdlib, GPU-free, fast — trivially unit-testable.

**Deliverable** (two artifacts, TDD order):
1. `tests/test_textproc.py` — written FIRST. Covers PRD test T2's four named areas (blocklist filtering incl. case-insensitivity, whitespace collapse, min-length rejection, punctuation preserved) plus the return-value contract. Verbatim source in Implementation Blueprint → Task 1.
2. `voice_typing/textproc.py` — exposes `clean(text, cfg)`. Verbatim source in Implementation Blueprint → Task 2. Consumed by `daemon.on_final` (P1.M4.T1.S2): `txt = textproc.clean(text, cfg.filter)`; daemon types `txt + " "` only when `txt is not None`.

**Success Definition**:
- (a) `clean()` implements PRD §4.7 steps 1–4 in order: (1) `strip()` + drop trailing newlines + collapse internal whitespace runs to single spaces; (2) `-> None` if `len(cleaned) < cfg.min_chars`; (3) `-> None` if `cleaned.lower().rstrip(".!?,;")` is in `{b.lower().rstrip(".!?,;") for b in cfg.blocklist}`; (4) return cleaned text. **Never appends a space** (the caller's job).
- (b) `.venv/bin/python -m pytest tests/test_textproc.py -v` → **all pass**.
- (c) `.venv/bin/python -m pytest -v` (whole suite) → still **all green** (`test_config.py` / `test_config_repo_default.py` unaffected).
- (d) The four item-required cases hold: `"Thank you." → None` (case-insensitive), whitespace collapse works, min-length rejects, `"Hello, world!"` is kept (punctuation preserved).
- (e) No out-of-scope files: no edits to `voice_typing/config.py` (S1 owns it; `clean()` only imports `FilterConfig`), no edits to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`, no new `daemon.py`/`feedback.py`/`typing_backends.py`/`ctl.py`/`config.toml`/`install.sh`/systemd. stdlib only — no new dependencies.

## User Persona

**Target User**: None directly — `clean()` is an internal function (no user-facing/config/API surface change, per item DOCS). Its "users" are two downstream agents: the daemon (`on_final`) and the test suite.

**Use Case**: Every finalized utterance from the ASR engine passes through `clean()` before typing. Dropped hallucinations ("thank you.", "bye.") never reach the keyboard; short noise (`len < 2`) is discarded; real text is whitespace-normalized and typed as-is.

**Pain Points Addressed**: Whisper hallucinates fluent text on silent audio (a documented model failure mode). Without this filter, the daemon would type "Thank you." into the user's terminal whenever the mic heard silence — embarrassing and disruptive. VAD gating (RealtimeSTT config) + **this filter** + PRD test T4 (idle-stability) defend against it together.

## Why

- **It is PRD test T2.** PRD §6 lists "textproc unit tests" as a gating test; the item explicitly states "this is PRD test T2." Shipping it now (early, in the GPU-free P1.M2 milestone) means the hallucination filter is proven before the daemon even exists.
- **Top-3 project risk.** PRD §8 names "Whisper hallucinates on silence ('Thank you.')" with mitigation "VAD gating + blocklist filter (§4.7) + T4 asserts it." This item IS that blocklist filter, made executable and tested.
- **Small, well-bounded, unblocks the daemon.** Pure Python, stdlib-only, no CUDA/audio/network. It is the one dependency `daemon.on_final` (P1.M4.T1.S2) needs from P1.M2; finishing it here keeps the daemon item clean.
- **TDD-able end to end.** The spec is fully deterministic (input string + `FilterConfig` → `str | None`), so tests can be written FIRST and drive the implementation — exactly the ordering the item prescribes.

## What

A single pure function `clean(text: str, cfg: FilterConfig) -> str | None` in `voice_typing/textproc.py` that normalizes and filters a finalized utterance per PRD §4.7, plus `tests/test_textproc.py` (PRD test T2) pinning every behavior. The function imports only `FilterConfig` from `voice_typing.config` and uses only the stdlib; it performs no I/O and has no side effects.

### Success Criteria

- [ ] `voice_typing/textproc.py` exists and exports `clean(text: str, cfg: FilterConfig) -> str | None`.
- [ ] `clean()` follows PRD §4.7 steps 1→2→3→4 in that order; step 1 uses `" ".join(text.split())` (strip + trailing-newline drop + internal-run collapse in one expression).
- [ ] Step 3 normalizes BOTH sides identically: `cleaned.lower().rstrip(".!?,;")` vs `{b.lower().rstrip(".!?,;") for b in cfg.blocklist}`.
- [ ] `clean()` never appends a trailing space (daemon's job).
- [ ] `tests/test_textproc.py` exists (written before the implementation file) and covers: blocklist filtering (`"Thank you." → None`, case-insensitive, with/without trailing punct, non-substring match), whitespace collapse (spaces/tabs/newlines, leading/trailing), min-length rejection (incl. cleaned-length semantics + custom `min_chars`), punctuation preserved (`"Hello, world!"`, `"?"`, `"."` when not blocklisted), and the return-value contract (`None` for rejections; no appended space).
- [ ] `.venv/bin/python -m pytest tests/test_textproc.py -v` → all pass.
- [ ] `.venv/bin/python -m pytest -v` → whole suite green.
- [ ] Only `voice_typing/textproc.py` (new) and `tests/test_textproc.py` (new) are created. Nothing else changes.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge of this repo: the authoritative spec (PRD §4.7) and the consumed contract (`FilterConfig` in `voice_typing/config.py`) are both read at preflight; the exact normalization semantics were verified live against the real `FilterConfig` defaults and the resulting truth table is recorded in the research note; the verbatim implementation and verbatim tests are in the Implementation Blueprint; the test-run command and the tooling reality (pytest in venv; ruff a uv tool; mypy absent) are pinned. Placement and naming follow `tests/test_config.py` (the established pattern).

### Documentation & References

```yaml
# MUST READ — the authoritative behavior spec (the contract)
- file: PRD.md
  why: "§4.7 is the verbatim spec for clean() steps 1-4. §6 'T2 — textproc unit
        tests' enumerates the four areas tests must cover. §8 names the
        silence-hallucination risk this filter mitigates (top-3)."
  critical: "Reproduce §4.7 step ORDER exactly (clean -> min_chars -> blocklist
             -> return). Step 3 strips TRAILING punctuation from BOTH the input
             and each blocklist entry (same normalization). The RETURNED text
             keeps its punctuation — stripping is compare-only."

# MUST READ — the consumed contract (FilterConfig). READ, do NOT edit.
- file: voice_typing/config.py
  why: "Defines FilterConfig (min_chars=2, blocklist=['thank you.', 'thanks for
        watching.', 'you', 'bye.', 'thank you for watching']) — the INPUT to
        clean(). clean() imports ONLY FilterConfig from here."
  critical: "blocklist entries are stored VERBATIM (trailing periods included);
             normalization (lowercase + rstrip trailing punct) happens at COMPARE
             time, so storage form does not change matching. Do NOT mutate the
             list in clean() (build a throwaway set). Do NOT import cuda_check/
             torch/realtimestt into textproc — same purity rule as config.py."

# MUST READ — the verified semantics + truth table (this task's research)
- docfile: plan/001_be48c74bc590/P1M2T2S1/research/textproc_spec_and_verification.md
  why: "§3 is a verified truth table for every input -> cleaned -> norm-key ->
        result, run live against the real FilterConfig defaults. §1 pins the
        exact signature + step-3 set comprehension. §5 pins the tooling reality
        (pytest in venv; ruff = uv tool at /home/dustin/.local/bin/ruff; mypy
        ABSENT). §6 pins the test conventions to reuse from test_config.py."
  section: "ALL sections load-bearing. §3 (truth table), §5 (tooling), §7 (scope)."

# MUST READ — the test pattern to follow (the project's established pytest style)
- file: tests/test_config.py
  why: "First unit tests in the repo; establishes the docstring + section-banner
        + one-assertion-per-test style test_textproc.py must mirror. Uses
        FilterConfig() for defaults and FilterConfig(...) construction for
        parametric cases."
  critical: "No tests/__init__.py (pytest discovers test_*.py; the package is
             editable-installed so 'from voice_typing.textproc import clean'
             resolves). Use FULL path .venv/bin/python (zsh aliases python/pip)."

# Background — machine facts (READ-ONLY context; shell-alias gotcha)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1: Python 3.12.10; shell aliases -> ALWAYS full paths (.venv/bin/python,
        /home/dustin/.local/bin/uv, /usr/bin/tmux). §2 file map: textproc.py
        lives at voice_typing/textproc.py. §3 data-flow: on_final -> clean() ->
        type text+' '. §4 decision #5: textproc owns text cleanup (RealtimeSTT's
        built-in post-proc is disabled) — so clean() is the SOLE normalizer."
  critical: "Use .venv/bin/python explicitly (never bare python/uv — zsh aliases)."

# Downstream — the consumer contract this item feeds (future work, do not build)
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M4.T1.S2 (daemon on_final) will call txt = textproc.clean(text,
        cfg.filter) and type txt+' ' only when txt is not None. Confirms clean()
        takes the FilterConfig SUB-config (not the top-level VoiceTypingConfig)
        and returns None to mean 'drop utterance'."
  critical: "Do NOT add append_space logic into clean() — the daemon owns it
             (cfg.output.append_space). clean() returns None | str only."
```

### Current Codebase tree (state at P1.M2.T2.S1 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*'` from repo root. Expected after P1.M2.T1.S1 (done) lands; P1.M2.T1.S2 (config.toml) may or may not be present yet (parallel) — it does not affect this item:

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores dist/, *.pyc, __pycache__/, .venv/, .pytest_cache/ (DO NOT touch)
├── .venv/                      # Python 3.12.10; pytest 9.1.1 installed (dev group)
├── PRD.md                      # READ-ONLY
├── pyproject.toml              # dev = ["pytest>=9.1.1"] (DO NOT touch; no new deps needed)
├── uv.lock                     # DO NOT touch
├── voice_typing/
│   ├── __init__.py             # package docstring
│   ├── cuda_check.py           # P1.M1.T2.S2 (unrelated)
│   ├── launch_daemon.sh        # P1.M1.T2.S1 (unrelated)
│   ├── prefetch.py             # P1.M1.T3.S1 (unrelated)
│   └── config.py               # ← P1.M2.T1.S1 output (FilterConfig lives HERE). READ but DO NOT EDIT.
└── tests/
    ├── test_config.py                # ← P1.M2.T1.S1 output (pattern to follow). DO NOT EDIT.
    └── test_config_repo_default.py   # ← P1.M2.T1.S2 output if landed (parallel). DO NOT EDIT.
# NO voice_typing/textproc.py yet — Task 2 creates it (the ONLY new non-test file).
# NO tests/test_textproc.py yet — Task 1 creates it (PRD test T2).
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── textproc.py             # ← CREATE (Task 2): clean(text, cfg: FilterConfig) -> str | None
└── tests/
    └── test_textproc.py        # ← CREATE (Task 1, TDD — written FIRST): PRD test T2
# NOTHING ELSE. No __init__.py in tests/ (pytest discovers test_*.py without it;
# the package is editable-installed so 'from voice_typing.textproc import clean'
# resolves). No edits to config.py (S1 owns it). No daemon/feedback/typing_backends/
# ctl/config.toml/install.sh/systemd (other items own those).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — STEP ORDER IS FIXED (PRD §4.7). clean -> min_chars -> blocklist ->
#   return, in that order. Do not reorder. The length check uses the CLEANED length
#   (post step 1), so "  A  " (raw len 5) -> cleaned "A" (len 1) -> None. The
#   blocklist check is EXACT on the normalized form, NOT substring/prefix: "you" is
#   blocked but "yourself" is NOT (it's not in the normalized set). (Research §3.)

# CRITICAL #2 — STEP 3 NORMALIZES BOTH SIDES IDENTICALLY. Input key =
#   cleaned.lower().rstrip(".!?,;"); blocklist = {b.lower().rstrip(".!?,;") for b
#   in cfg.blocklist}. This is why "Bye", "bye.", and "BYE!" all drop (normalize to
#   "bye") and why "thank you." in text matches "thank you." in the default list
#   (both normalize to "thank you"). The strip class is exactly .!?,; — do not add
#   or remove characters (it is pinned verbatim by the item + PRD §8 risk note).
#   (Research §1, §3.)

# CRITICAL #3 — PUNCTUATION STRIPPING IS COMPARE-ONLY. The RETURNED cleaned text
#   keeps its trailing punctuation: "Hello, world!" is returned as "Hello, world!"
#   (the item's explicit success case). Only the blocklist-comparison KEY strips
#   trailing punct. Do not strip punctuation from the return value. (Research §3.)

# CRITICAL #4 — clean() NEVER APPENDS A SPACE. The daemon (P1.M4.T1.S2) appends
#   " " when cfg.output.append_space. clean() returns None | str only; a returned
#   str must be the cleaned text verbatim with no added trailing whitespace.
#   (PRD §4.7 step 4; item: "Caller appends a space ... daemon's job, not here".)

# CRITICAL #5 — STEP 1 IDIOM: " ".join(text.split()). str.split() with no args
#   splits on ANY unicode-whitespace run and drops leading/trailing empties, so
#   join() yields a fully-stripped, single-space-joined string in ONE expression —
#   covering strip() + trailing-newline drop + internal-run collapse (PRD §4.7 step
#   1's three clauses). No `re` import needed. Verified: tabs, \n, double-spaces all
#   collapse. Empty/whitespace-only input -> "" (then caught by min_chars -> None).
#   (Research §3.)

# CRITICAL #6 — PURE STDLIB. textproc.py imports ONLY FilterConfig from
#   voice_typing.config and uses no other imports (the verbatim source uses just
#   `from __future__ import annotations`). It must NOT import cuda_check / torch /
#   realtimestt / ctranslate2 — textproc must load in CPU-only and test contexts
#   (same purity rule as config.py's module docstring). (config.py module docstring.)

# CRITICAL #7 — DO NOT MUTATE cfg.blocklist. It is a per-instance list (config.py
#   uses default_factory precisely to avoid shared mutable state). clean() builds a
#   throwaway set for the membership test; it never appends/removes from the list.

# CRITICAL #8 — FULL PATHS for tooling (zsh aliases python/pip/tmux). Always
#   .venv/bin/python -m pytest ... (never bare `python` or `pytest`). ruff, if used
#   as an OPTIONAL lint, is at /home/dustin/.local/bin/ruff (NOT in .venv). mypy is
#   NOT installed anywhere — do NOT list it as a gate. (Research §5; system_context §1.)
```

## Implementation Blueprint

### Data models and structure

`clean()` consumes the existing `FilterConfig` dataclass from `voice_typing/config.py` (P1.M2.T1.S1) — **no new data model is created by this item.** The function signature is the contract:

```python
def clean(text: str, cfg: FilterConfig) -> str | None: ...
```

`FilterConfig` fields used: `cfg.min_chars: int` (default 2), `cfg.blocklist: list[str]` (default `["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"]`). Return type `str | None`: `None` ⇒ drop utterance (hallucination or too short); `str` ⇒ type this (daemon appends a space when `cfg.output.append_space`).

### Implementation Tasks (ordered by dependencies — TDD: tests first)

```yaml
Task 1: CREATE tests/test_textproc.py   (WRITE FIRST — this IS PRD test T2)
  - IMPLEMENT: the pytest suite in the verbatim block below (PRD §6 T2's four
    areas + return-value contract). ~20 focused tests.
  - FOLLOW pattern: tests/test_config.py (module docstring with run command,
    `from __future__ import annotations`, section `# ----` banners, one focused
    assertion per test, FilterConfig() for defaults + FilterConfig(...) for cases).
  - NAMING: test_<behavior> (e.g. test_rejects_default_blocklist_thank_you,
    test_collapses_internal_whitespace_runs, test_internal_punctuation_preserved).
  - COVERAGE: blocklist filtering ("Thank you."->None, case-insensitive,
    with/without trailing punct, non-substring "yourself" kept, empty blocklist),
    whitespace collapse (spaces/tabs/newlines, leading/trailing, whitespace-only),
    min-length (below/ boundary/ empty/ cleaned-length semantics/ custom min_chars),
    punctuation preserved ("Hello, world!", "?", "." when not blocklisted),
    return-value contract (None for rejections; never appends a space).
  - PLACEMENT: tests/test_textproc.py. No tests/__init__.py.
  - NOTE: This task will FAIL until Task 2 lands (ImportError on
    voice_typing.textproc) — that is the intended RED step of TDD.

Task 2: CREATE voice_typing/textproc.py
  - IMPLEMENT: the module in the verbatim block below (clean() + docstring +
    the _TRAILING_PUNCT constant + `from __future__ import annotations` +
    the single FilterConfig import).
  - FOLLOW pattern: voice_typing/config.py for docstring style (plain
    present-tense, concrete units, cross-references to PRD sections not
    duplication of them) and the stdlib-only purity rule.
  - NAMING: clean() (function), _TRAILING_PUNCT (module-level constant, the
    compare-time punctuation strip class pinned verbatim from the item spec).
  - DEPENDENCIES: `from voice_typing.config import FilterConfig` (Task 0 / S1).
  - PLACEMENT: voice_typing/textproc.py.
  - VERIFICATION: re-run Task 1's suite — it must now go GREEN.
```

#### Task 1 — `tests/test_textproc.py` (verbatim)

```python
"""Unit tests for voice_typing.textproc.clean (PRD §4.7 — PRD test T2).

Pure-Python: no network, no GPU, no audio. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_textproc.py -v

This is PRD test T2 (§6). It pins the text normalizer + hallucination filter
that every finalized utterance passes through before typing. Whisper's
silence-hallucination ("thank you." on silent audio) is a top-3 project risk
(PRD §8); VAD gating + this filter + PRD test T4 (idle stability) defend
against it together. Written FIRST (TDD) — it is RED until textproc.py lands.
"""
from __future__ import annotations

from voice_typing.config import FilterConfig
from voice_typing.textproc import clean


# ---------------------------------------------------------------------------
# Whitespace normalization (PRD §4.7 step 1)
# ---------------------------------------------------------------------------

def test_collapses_internal_whitespace_runs():
    assert clean("Hello  world", FilterConfig()) == "Hello world"


def test_strips_leading_and_trailing_whitespace():
    assert clean("   Hello world   ", FilterConfig()) == "Hello world"


def test_drops_trailing_newlines_and_collapses():
    assert clean("Hello\n\nworld\n", FilterConfig()) == "Hello world"


def test_tabs_are_whitespace_too():
    assert clean("Hello\tworld", FilterConfig()) == "Hello world"


# ---------------------------------------------------------------------------
# min-length rejection (PRD §4.7 step 2)
# ---------------------------------------------------------------------------

def test_rejects_below_min_chars():
    # default min_chars == 2
    assert clean("A", FilterConfig()) is None


def test_accepts_at_min_chars_boundary():
    assert clean("Hi", FilterConfig()) == "Hi"


def test_rejects_empty_string():
    assert clean("", FilterConfig()) is None


def test_rejects_whitespace_only():
    # collapses to "" -> len 0 < min_chars
    assert clean("    \n  ", FilterConfig()) is None


def test_min_length_uses_cleaned_text_not_raw():
    # raw length 5 but cleaned length 1 -> rejected
    assert clean("  A  ", FilterConfig()) is None


def test_custom_min_chars():
    cfg = FilterConfig(min_chars=5, blocklist=[])
    assert clean("Hi", cfg) is None        # len 2 < 5
    assert clean("Hello", cfg) == "Hello"  # len 5 == 5


# ---------------------------------------------------------------------------
# Blocklist / hallucination filter (PRD §4.7 step 3) — case-insensitive
# ---------------------------------------------------------------------------

def test_rejects_default_blocklist_thank_you():
    assert clean("Thank you.", FilterConfig()) is None


def test_blocklist_is_case_insensitive():
    assert clean("THANK YOU.", FilterConfig()) is None
    assert clean("thank YOU", FilterConfig()) is None


def test_blocklist_matches_with_or_without_trailing_punct():
    # "bye." is in the default blocklist; "Bye"/"bye."/"BYE!" all normalize to "bye"
    assert clean("Bye", FilterConfig()) is None
    assert clean("bye.", FilterConfig()) is None
    assert clean("BYE!", FilterConfig()) is None  # "!" is in the strip class


def test_blocklist_entry_without_punctuation_matches():
    # "you" is in the default blocklist with no trailing punctuation
    assert clean("you", FilterConfig()) is None
    assert clean("You.", FilterConfig()) is None


def test_blocklist_is_exact_not_substring():
    # "you" is blocked, but "yourself" must NOT be dropped (exact normalized match)
    assert clean("yourself", FilterConfig()) == "yourself"


def test_empty_blocklist_never_rejects():
    cfg = FilterConfig(min_chars=2, blocklist=[])
    assert clean("thank you", cfg) == "thank you"


# ---------------------------------------------------------------------------
# Punctuation preserved (PRD §4.7 — return the cleaned text as-is)
# ---------------------------------------------------------------------------

def test_internal_punctuation_preserved():
    # the item's explicit success case: "Hello, world!" kept verbatim
    assert clean("Hello, world!", FilterConfig()) == "Hello, world!"


def test_question_mark_preserved():
    assert clean("Is this real?", FilterConfig()) == "Is this real?"


def test_period_preserved_when_not_blocklisted():
    assert clean("It works.", FilterConfig()) == "It works."


# ---------------------------------------------------------------------------
# Return-value contract
# ---------------------------------------------------------------------------

def test_never_appends_trailing_space():
    # clean() never adds a space; the daemon does (cfg.output.append_space)
    result = clean("Hello", FilterConfig())
    assert result == "Hello"
    assert not result.endswith(" ")


def test_returns_none_for_every_rejection_reason():
    assert clean("A", FilterConfig()) is None              # too short
    assert clean("Thank you.", FilterConfig()) is None     # blocklist
    assert clean("", FilterConfig()) is None               # empty
```

#### Task 2 — `voice_typing/textproc.py` (verbatim)

```python
"""voice_typing.textproc — post-recognition text normalizer (PRD §4.7).

clean() is the quality + hallucination filter applied to every finalized
utterance before it is typed. PURE PYTHON (stdlib only), GPU-free, and fast,
so it is trivially unit-testable (PRD test T2).

PIPELINE (PRD §4.7), in order:
  1. strip() + drop trailing newlines + collapse internal whitespace runs to
     single spaces.
  2. reject (-> None) if len(cleaned) < cfg.min_chars.
  3. reject (-> None) if the lowercase, trailing-punctuation-stripped form of
     the cleaned text is in the blocklist (the blocklist is normalized the
     same way, so "Bye", "bye.", and "BYE!" all match the "bye." entry).
  4. return cleaned text. The CALLER (daemon on_final) appends a trailing
     space when output.append_space — clean() never adds one.

THE BLOCKLIST is the primary defense against Whisper's silence hallucination
("thank you." on silent audio — a top-3 project risk, PRD §8). VAD gating +
this filter + PRD test T4 assert it together. Trailing-punctuation stripping
makes the match robust to whether Whisper appended a period: "Bye", "Bye.",
and "BYE!" all normalize to "bye" and all match the "bye." blocklist entry.

CONSUMES: voice_typing.config.FilterConfig (P1.M2.T1.S1).
CONSUMED BY: daemon.on_final (P1.M4.T1.S2) as:
    txt = textproc.clean(text, cfg.filter)
    if txt is not None: <type txt + " " when cfg.output.append_space>

NO SIDE EFFECTS, NO I/O. Deterministic and pure.
"""
from __future__ import annotations

from voice_typing.config import FilterConfig

# Trailing punctuation stripped when building the blocklist comparison key
# (PRD §4.7 step 3). Pinned verbatim; do not add/remove characters.
_TRAILING_PUNCT = ".!?," + ";"  # written split to avoid an editor auto-trim of trailing punctuation


def clean(text: str, cfg: FilterConfig) -> str | None:
    """Normalize + filter a finalized utterance (PRD §4.7).

    Args:
        text: raw finalized text from the ASR engine (may carry stray
            leading/trailing whitespace, embedded newlines, double spaces).
        cfg: the [filter] config (min_chars, blocklist) from VoiceTypingConfig.

    Returns:
        The cleaned text, or None if it should be dropped (too short, or a
        known hallucination). Never appends a space (the caller's job).
    """
    # Step 1: strip + drop trailing newlines + collapse internal whitespace
    # runs to single spaces. str.split() (no args) splits on ANY whitespace run
    # and discards leading/trailing empties, so join() yields a fully-stripped,
    # single-space-joined string in one expression.
    cleaned = " ".join(text.split())

    # Step 2: min-length gate (on the CLEANED length).
    if len(cleaned) < cfg.min_chars:
        return None

    # Step 3: hallucination blocklist. Normalize BOTH the input and every
    # blocklist entry the same way: lowercase + strip trailing punctuation.
    # Exact match on the normalized form (NOT substring): "you" blocks, but
    # "yourself" does not.
    key = cleaned.lower().rstrip(_TRAILING_PUNCT)
    if key in {b.lower().rstrip(_TRAILING_PUNCT) for b in cfg.blocklist}:
        return None

    # Step 4: return cleaned text (caller appends a space when append_space).
    return cleaned
```

> **Note on `_TRAILING_PUNCT`:** the literal strip class is the 5 characters `.!?,;` exactly. The split expression (`".!?," + ";"`) in the verbatim source is a defensive way to write the constant so a future editor's "remove trailing whitespace/punctuation on save" rule cannot accidentally delete the trailing `;`. An implementer may write it as the single literal `".!?,"` if they prefer — the test suite does not depend on the spelling, only the resulting character set (verified in Research §3).

### Implementation Patterns & Key Details

```python
# The whole module is ~20 lines of logic. The non-obvious details, concentrated:

# (1) Whitespace collapse in one expression (covers all of step 1):
cleaned = " ".join(text.split())
#   "  Hello   world\n" -> "Hello world"     (spaces + newline collapse, stripped)
#   "\t\t"               -> ""               (whitespace-only -> empty)
#   ""                   -> ""               (empty stays empty)

# (2) min_chars uses the CLEANED length, not raw length:
if len(cleaned) < cfg.min_chars: return None
#   "  A  " -> cleaned "A" (len 1) -> None, even though raw is len 5.

# (3) Identical normalization on both sides (case-insensitive, trailing-punct-robust):
key = cleaned.lower().rstrip(".!?,;")
if key in {b.lower().rstrip(".!?,;") for b in cfg.blocklist}: return None
#   "Thank you." -> key "thank you"  -> matches "thank you." entry -> None
#   "BYE!"       -> key "bye"        -> matches "bye." entry       -> None
#   "yourself"   -> key "yourself"   -> NO match (exact, not substring) -> kept

# (4) Punctuation stripping is COMPARE-ONLY; the return value is untouched:
return cleaned
#   "Hello, world!" -> cleaned "Hello, world!" -> returned AS-IS (punctuation kept).
```

### Integration Points

```yaml
# No database, no routes, no config-schema change, no new env vars. The only
# integration is the import + the future consumer:

IMPORTS:
  - add to: voice_typing/textproc.py (NEW)
  - pattern: "from voice_typing.config import FilterConfig"  # the sole import

CONSUMER (future — P1.M4.T1.S2, daemon.on_final; DO NOT build here):
  - call: "txt = textproc.clean(text, cfg.filter)"
  - gate: "if txt is not None: <type txt + ' ' when cfg.output.append_space>"

CONFIG: none — clean() reads cfg.min_chars and cfg.blocklist at call time; it
  adds no config keys and changes no defaults.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# PRIMARY — pytest is in .venv (declared in pyproject dev). FULL paths (zsh aliases).
cd /home/dustin/projects/voice-typing

# OPTIONAL lint — ruff is a uv tool at /home/dustin/.local/bin/ruff (NOT in .venv).
#   Skip if unavailable; it is not required for success (precedent: test_config.py
#   used pytest only). mypy is NOT installed anywhere — do NOT run mypy.
/home/dustin/.local/bin/ruff check voice_typing/textproc.py tests/test_textproc.py || true

# Expected (ruff): no F-class (unused import / undefined name) or E-class errors.
#   The verbatim sources above are already ruff-clean (no unused imports, no `re`).
```

### Level 2: Unit Tests (Component Validation — THE gate)

```bash
cd /home/dustin/projects/voice-typing

# After Task 1 (tests) only: this is the TDD RED step — expect ImportError on
# voice_typing.textproc. That is correct; it proves the tests are wired.
.venv/bin/python -m pytest tests/test_textproc.py -v

# After Task 2 (impl) lands: MUST be all green.
.venv/bin/python -m pytest tests/test_textproc.py -v

# Full suite (confirm no regression in config tests):
.venv/bin/python -m pytest -v

# Expected: every test_textproc.py test PASSES; test_config.py and
# test_config_repo_default.py (if present) still PASS. Zero failures.
```

### Level 3: Integration Testing (System Validation)

```bash
cd /home/dustin/projects/voice-typing

# textproc is a pure function with no I/O — there is no service to start.
# Validate the import resolves from the real package and the truth table holds:

.venv/bin/python - <<'PY'
from voice_typing.config import FilterConfig
from voice_typing.textproc import clean
cfg = FilterConfig()
# The four item-required behaviors, in one shot:
assert clean("Thank you.", cfg) is None        # blocklist, case-insensitive
assert clean("Hello  world", cfg) == "Hello world"   # whitespace collapse
assert clean("A", cfg) is None                 # min-length rejection
assert clean("Hello, world!", cfg) == "Hello, world!"  # punctuation preserved
print("OK: clean() truth table holds against the real FilterConfig defaults")
PY

# Expected: prints "OK: clean() truth table holds ..." with exit code 0.
# (Cross-check against Research §3's verified truth table.)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No GPU/audio/network involved — the domain-specific validation IS Level 2 + 3.
# The hallucination-defense efficacy is ultimately asserted end-to-end by PRD
# test T4 (idle-stability, P1.M7.T4.S1): 120 s of silence must type nothing.
# That test is out of scope here; this item proves the FILTER half in isolation.
```

## Final Validation Checklist

### Technical Validation

- [ ] `.venv/bin/python -m pytest tests/test_textproc.py -v` → all pass.
- [ ] `.venv/bin/python -m pytest -v` → whole suite green (no regression).
- [ ] `clean()` import resolves from the real package (Level 3 one-liner prints `OK`).
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/textproc.py tests/test_textproc.py` → clean (skip if unavailable).

### Feature Validation

- [ ] PRD §4.7 step order reproduced exactly: clean → min_chars → blocklist → return.
- [ ] `"Thank you." → None` (case-insensitive: `THANK YOU.` and `thank YOU` too).
- [ ] Whitespace collapse works (spaces, tabs, newlines; leading/trailing; whitespace-only).
- [ ] Min-length rejects (`"A" → None`; boundary `"Hi"` kept; cleaned-length semantics; custom `min_chars`).
- [ ] Punctuation preserved: `"Hello, world!"` returned verbatim.
- [ ] Blocklist is exact, not substring: `"yourself"` kept though `"you"` is blocked.
- [ ] `clean()` never appends a trailing space.

### Code Quality Validation

- [ ] Follows `tests/test_config.py` pattern (docstring, section banners, one assertion per test).
- [ ] `textproc.py` docstring mirrors `config.py` style (plain present-tense, PRD cross-refs).
- [ ] stdlib-only; imports only `FilterConfig` from `voice_typing.config`.
- [ ] File placement matches the desired tree (`voice_typing/textproc.py`, `tests/test_textproc.py`).
- [ ] No new dependencies; no edits to `pyproject.toml`/`uv.lock`.

### Documentation & Deployment

- [ ] `textproc.py` module docstring documents the pipeline, the blocklist's purpose, and the consumer contract (`daemon.on_final`).
- [ ] No new env vars, no config keys, no user-facing surface (item DOCS: "none").

---

## Anti-Patterns to Avoid

- ❌ Don't reorder PRD §4.7 steps — the order is fixed (clean → min_chars → blocklist → return).
- ❌ Don't strip punctuation from the RETURN value — stripping is compare-only; `"Hello, world!"` is returned verbatim.
- ❌ Don't make the blocklist match a substring/prefix — it is exact on the normalized form (`"yourself"` ≠ `"you"`).
- ❌ Don't append a space in `clean()` — that is the daemon's job (`cfg.output.append_space`).
- ❌ Don't import cuda_check/torch/realtimestt into textproc — it must stay pure-stdlib (test/CPU-loadable).
- ❌ Don't mutate `cfg.blocklist` — build a throwaway set for the membership test.
- ❌ Don't add `re` when `" ".join(text.split())` does step 1 in one expression.
- ❌ Don't run `mypy` — it is not installed (would fail); pytest is the authoritative gate.
- ❌ Don't write the implementation before the tests — this item prescribes TDD (Task 1 = tests first, the RED step).

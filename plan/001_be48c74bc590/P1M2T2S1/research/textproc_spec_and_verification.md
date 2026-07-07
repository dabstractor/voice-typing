# Research — textproc.clean() (P1.M2.T2.S1, PRD §4.7 / test T2)

This note captures the authoritative spec, the consumed contract, the verified
runtime semantics, and the validation-tooling reality. The PRP (../PRP.md)
references it as the single source of truth for behavior + tests.

## 1. The spec (PRD §4.7, verbatim) + the item contract

PRD §4.7 defines `clean(text) -> str | None`:

1. `text.strip()`; strip trailing newlines; collapse internal whitespace runs
   to single spaces.
2. Reject if `len < filter.min_chars`.
3. Reject if the lowercase, trailing-punctuation-stripped form is in blocklist.
4. Return cleaned text. Caller appends a single space when `append_space`.

The WORK ITEM pins the EXACT signature and step details:

- Signature: `clean(text: str, cfg: FilterConfig) -> str | None` (takes the
  `[filter]` sub-config, NOT the whole `VoiceTypingConfig`).
- Step 3 normalization (verbatim from item): `return None if the lowercase form
  with trailing punctuation stripped is in {b.lower().rstrip(".!?,;") for b in
  cfg.blocklist}`. So BOTH the input AND every blocklist entry are normalized
  the SAME way: `.lower().rstrip(".!?,;")`.
- Step 4: "Caller appends a space when append_space (daemon's job, not here)."
  ⇒ `clean()` NEVER appends a space.
- TDD ordering: write `tests/test_textproc.py` FIRST (this IS PRD test T2),
  then `voice_typing/textproc.py`.
- Required test cases (item): blocklist filtering ("Thank you." → None,
  case-insensitive), whitespace collapse, min-length rejection, punctuation
  preserved ("Hello, world!" kept).

## 2. Consumed contract — `FilterConfig` (P1.M2.T1.S1, already shipped)

`voice_typing/config.py` (READ, do not edit) defines:

```python
@dataclass
class FilterConfig:
    min_chars: int = 2
    blocklist: list[str] = field(default_factory=lambda: [
        "thank you.", "thanks for watching.", "you", "bye.", "thank you for watching",
    ])
```

Notes that govern `clean()`:
- `default_factory` gives each instance its OWN list (no shared mutable state) —
  `clean()` must not mutate it (it builds a throwaway `set`).
- Entries are stored VERBATIM (trailing periods included); normalization
  (lowercase + strip trailing punct) happens at COMPARE time, so the storage
  form does not change matching — only the normalized form matters.
- `clean()` imports ONLY `FilterConfig` from config. It must NOT import
  cuda_check/torch/realtimestt — textproc is pure-stdlib and must load in
  CPU-only/test contexts (same purity rule as config.py).

## 3. Verified runtime semantics (live run, 2026-07-06)

Normalized blocklist set:
`{'bye', 'thank you', 'thank you for watching', 'thanks for watching', 'you'}`

| raw input          | cleaned           | norm-key        | min_ok | blocked | result            |
|--------------------|-------------------|-----------------|--------|---------|-------------------|
| `"Thank you."`     | `"Thank you."`    | `"thank you"`   | True   | True    | `None`            |
| `"THANK YOU."`     | `"THANK YOU."`    | `"thank you"`   | True   | True    | `None` (case-ins) |
| `"Bye"`            | `"Bye"`           | `"bye"`         | True   | True    | `None`            |
| `"bye."`           | `"bye."`          | `"bye"`         | True   | True    | `None`            |
| `"you"`            | `"you"`           | `"you"`         | True   | True    | `None`            |
| `"Hello, world!"`  | `"Hello, world!"` | `"hello, world"`| True   | False   | `"Hello, world!"` |
| `"Hello  world"`   | `"Hello world"`   | `"hello world"` | True   | False   | `"Hello world"`   |
| `"A"`              | `"A"`             | `"a"`           | False  | False   | `None` (min_chars)|
| `"Hi"`             | `"Hi"`            | `"hi"`          | True   | False   | `"Hi"`            |
| `""`               | `""`              | `""`            | False  | False   | `None`            |
| `"   "`            | `""`              | `""`            | False  | False   | `None`            |

Implementation choice for step 1: `cleaned = " ".join(text.split())`. `str.split()`
with no args splits on ANY unicode-whitespace run and discards leading/trailing
empties, so the `join` yields a fully-stripped, single-space-joined string in
one expression — covering strip() + trailing-newline drop + internal-run
collapse. No `re` import needed (verified: tabs/newlines/double-spaces all
collapse correctly). Alternative `re.sub(r"\s+", " ", text).strip()` is
equivalent but adds an import for no benefit.

Critical non-obvious points pinned here and in the PRP:
- The length check (step 2) uses the CLEANED length, so `"  A  "` (raw len 5)
  → cleaned `"A"` (len 1) → rejected. (This is a test case.)
- The blocklist match is EXACT on the normalized form, NOT substring/prefix:
  `"you"` is blocked but `"yourself"` is NOT (`"yourself"` ∉ set). (Test case.)
- Punctuation stripping is TRAILING-only (`.rstrip`) and is applied ONLY to
  build the blocklist comparison key; the RETURNED cleaned text keeps its
  punctuation (`"Hello, world!"` returned as-is). (Test case — the item's
  explicit "Hello, world! kept".)
- `"BYE!"` also drops (the `!` is in the strip class `.!?,;`), matching the
  `bye.` blocklist entry after both normalize to `"bye"`.

## 4. Consumer contract — daemon `on_final` (P1.M4.T1.S2, future work)

PRD §4.2 / §3 architecture: `on_final(text) → textproc.clean() → if non-None:
typing backend types text + " "`. Concretely the daemon will call
`txt = textproc.clean(text, cfg.filter)` (passes the `[filter]` sub-config).
If `txt` is None ⇒ drop (no typing, no feedback last_final). If a str ⇒ type
`txt + (" " if cfg.output.append_space else "")`. This confirms:
- `clean()` takes `FilterConfig` (the sub-config), not the top-level config.
- `clean()` returns `None` to signal "drop this utterance" (hallucination or
  too short) and a `str` to signal "type this". Boolean-y falsy strings like
  `""` never occur as a return (empty is caught by min_chars → None).
- `append_space` is the daemon's concern; `clean()` never touches it.

## 5. Validation tooling reality (verified on this machine)

- pytest 9.1.1 is installed in `.venv` (declared in pyproject `[dependency-groups]
  dev`). Run command (FULL paths — zsh aliases `python`/`pip`/`tmux`):
  `.venv/bin/python -m pytest tests/test_textproc.py -v`
- ruff v0.14.13 is available as a uv tool at `/home/dustin/.local/bin/ruff` but
  is NOT in `.venv` and NOT declared in pyproject. Optional lint only:
  `/home/dustin/.local/bin/ruff check voice_typing/textproc.py tests/test_textproc.py`
- mypy is NOT installed anywhere (not in venv, not on PATH, not a uv tool). Do
  NOT list `mypy` as a validation gate — it would fail. (The PRP template lists
  it; this project has not adopted it.)
- Precedent: the project's first tests, `tests/test_config.py` and
  `tests/test_config_repo_default.py`, used ONLY `.venv/bin/python -m pytest`.
  `test_textproc.py` follows the same pattern.

## 6. Test-pattern conventions to reuse (from tests/test_config.py)

- Module docstring names the PRD section + the run command
  (`.venv/bin/python -m pytest tests/test_textproc.py -v`).
- `from __future__ import annotations` at top.
- Imports: `pytest`, `FilterConfig` from `voice_typing.config`, `clean` from
  `voice_typing.textproc`.
- Section dividers with `# ----` banners grouping related cases.
- One focused assertion per test; descriptive `test_<behavior>` names.
- Use `FilterConfig()` (defaults) for default-blocklist tests; construct
  `FilterConfig(min_chars=..., blocklist=[...])` for parametric cases.
- No `tests/__init__.py` needed (pytest discovers `test_*.py`; the package is
  editable-installed so `from voice_typing.textproc import clean` resolves).

## 7. Scope boundaries (do / don't)

DO: create `voice_typing/textproc.py` (`clean`) + `tests/test_textproc.py`.
DON'T: edit `voice_typing/config.py` (S1 owns it — `clean()` only imports from
it), edit `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/
`uv.lock`, create `daemon.py`/`feedback.py`/`typing_backends.py`/`ctl.py`/
`config.toml`/`install.sh`/systemd (other items own those), add `append_space`
logic into `clean()` (daemon's job). No new dependencies (stdlib only).

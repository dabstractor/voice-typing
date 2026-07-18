# Gap Report — P1.M1.T2.S1: textproc.clean() vs PRD §4.7

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/textproc.py`'s `clean()` against the PRD §4.7 4-step spec + the
§4.3 trailing-newline strip + the blocklist-normalization intent (case- + trailing-punctuation-
insensitive; exact, not substring). Subtask **P1.M1.T2.S1** of verification round
`006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/textproc.py` — `clean()` `:39-70`; `_TRAILING_PUNCT` `:36`.
- `tests/test_textproc.py` — the 21-test behavior-pinning suite (PRD test T2).
- `voice_typing/config.py` — `FilterConfig` defaults (`:184-200`) for blocklist context only.
- `plan/006_862ee9d6ef41/prd_snapshot.md` — §4.7 (4-step spec), §4.3 (trailing newlines),
  §4.5 (canonical blocklist, incl. the bare `"you"` the code intentionally omits — VT-006),
  §8 (silence-hallucination as a top-3 risk).

**Bottom line:** ✅ `clean()` is **COMPLIANT** with PRD §4.7 — all 4 steps map 1:1 to the
spec, the §4.3 trailing-newline strip holds, and the blocklist normalization correctly rejects
`"Thank you."` / `"BYE!"` / `"bye"` via their respective entries. **No source files were modified**
(`clean()` is compliant per audit). The VT-006 `"you"` blocklist removal is a §4.5 config concern,
**not** a `textproc.py` defect (see §6).

---

## 1. Method

`clean()` was read line-by-line and each of its four expressions was mapped 1:1 to the PRD §4.7
steps (with `grep -n`-verified file:line). The two contract behaviors were then **re-run live**
(pure stdlib, milliseconds) and the full `tests/test_textproc.py` suite was re-run to record the
actual pass count. Nothing was assumed from the PRP's embedded numbers — every figure below was
re-verified this round.

### Commands run (re-verification)

```bash
# (a) Line-number map of clean() + _TRAILING_PUNCT (grep -n)
grep -n '' voice_typing/textproc.py | sed -n '34,72p'

# (b) The two contract behavior checks (trailing newlines + blocklist normalization), LIVE
.venv/bin/python - <<'PY'
from voice_typing.textproc import clean, _TRAILING_PUNCT
from voice_typing.config import FilterConfig
cfg = FilterConfig()   # default blocklist (VT-006: no bare "you")
assert clean("Hello\n\nworld\n", cfg) == "Hello world"     # §4.3 trailing newlines
assert clean("Thank you.", cfg) is None                    # "thank you." entry
assert clean("BYE!", cfg) is None                          # "bye." entry, "!" stripped
assert clean("bye", cfg) is None                           # "bye." entry
cfg2 = FilterConfig(min_chars=2, blocklist=["you"])
assert clean("yourself", cfg2) == "yourself"               # exact, not substring
assert clean("you", cfg2) is None
print("behavior checks PASS; _TRAILING_PUNCT =", repr(_TRAILING_PUNCT))
PY

# (c) The unit suite (PRD test T2), LIVE
.venv/bin/python -m pytest tests/test_textproc.py -q
```

### Observed output (abridged)

```
behavior checks PASS; _TRAILING_PUNCT = '.!,;?'
.....................                                                    [100%]
21 passed in 0.01s
```

`_TRAILING_PUNCT = ".!?," + ";"` (`textproc.py:36`) = `'.!,;?'` — the trailing-punctuation strip
class used in step 3.

---

## 2. Per-step Compliance Table (PRD §4.7 vs `textproc.py`)

| PRD §4.7 step | Expected (spec) | `textproc.py` actual | file:line | Pinning tests (`tests/test_textproc.py`) | Verdict |
|---|---|---|---|---|---|
| **1** strip + drop trailing newlines + collapse internal whitespace | `text.strip(); strip trailing newlines; collapse internal whitespace runs to single spaces` | `cleaned = " ".join(text.split())` — `str.split()` (no args) splits on ANY whitespace run and discards leading/trailing empties, so `join()` yields a fully-stripped, newline-dropped, single-space-joined string in one expression | `:55` | `test_collapses_internal_whitespace_runs` `:23`; `test_strips_leading_and_trailing_whitespace` `:27`; `test_drops_trailing_newlines_and_collapses` `:31` (THE §4.3 check); `test_tabs_are_whitespace_too` `:35` | ✅ |
| **2** min_chars gate | reject (`None`) if `len(cleaned) < filter.min_chars` | `if len(cleaned) < cfg.min_chars: return None` (on the **cleaned** length) | `:58` | `test_rejects_below_min_chars` `:43`; `test_accepts_at_min_chars_boundary` `:48`; `test_rejects_empty_string` `:52`; `test_rejects_whitespace_only` `:56`; `test_min_length_uses_cleaned_text_not_raw` `:61`; `test_custom_min_chars` `:66` | ✅ |
| **3** blocklist (normalized both sides, exact) | reject (`None`) if lowercase + trailing-punctuation-stripped form is in blocklist; both input and entries normalized identically; match is **exact, not substring** | `key = cleaned.lower().rstrip(_TRAILING_PUNCT)` (normalize input); `if key in {b.lower().rstrip(_TRAILING_PUNCT) for b in cfg.blocklist}: return None` (normalize entries + exact set membership) | `:65-67` | `test_rejects_default_blocklist_thank_you` `:76`; `test_blocklist_is_case_insensitive` `:80`; `test_blocklist_matches_with_or_without_trailing_punct` `:85` (THE normalization check); `test_blocklist_entry_without_punctuation_matches` `:92`; `test_blocklist_is_exact_not_substring` `:101`; `test_empty_blocklist_never_rejects` `:109` | ✅ |
| **4** return cleaned text (no space) | return cleaned text; **caller** appends a single space when `append_space` | `return cleaned` (never appends a space) | `:70` | `test_internal_punctuation_preserved` `:118`; `test_question_mark_preserved` `:123`; `test_period_preserved_when_not_blocklisted` `:127`; `test_never_appends_trailing_space` `:135` | ✅ |

> **Step 1 is a benign SUPERSET, not drift.** PRD §4.7 step 1 says "strip(); strip trailing
> newlines; collapse internal whitespace." `clean()` does `" ".join(text.split())`, which strips
> **all** leading/trailing whitespace (not only newlines) plus collapses all internal whitespace
> runs. Stripping trailing spaces too is **strictly more correct** than the PRD's literal wording —
> it is recorded as **COMPLIANT**, not drift. `test_drops_trailing_newlines_and_collapses` (`:31`)
> pins the §4.3 trailing-newline case specifically.

---

## 3. Contract Behavior Checks (re-run live)

### 3.1 Trailing-newline strip (PRD §4.3) — ✅ PASS

```python
clean("Hello\n\nworld\n", FilterConfig()) == "Hello world"
```

The embedded `\n\n` is collapsed to a single space and the trailing `\n` is dropped entirely —
exactly the §4.3 "strip trailing newlines in textproc" requirement. Pinned by
`test_drops_trailing_newlines_and_collapses` (`tests/test_textproc.py:31`).

### 3.2 Blocklist normalization — ✅ PASS

All three contract inputs reject, each via its **own** normalized blocklist entry:

| Input | normalized key (`cleaned.lower().rstrip('.!,;?')`) | matches blocklist entry | entry normalized | result |
|---|---|---|---|---|
| `"Thank you."` | `"thank you"` | `"thank you."` | `"thank you"` | `None` ✅ |
| `"BYE!"` | `"bye"` | `"bye."` | `"bye"` | `None` ✅ |
| `"bye"` | `"bye"` | `"bye."` | `"bye"` | `None` ✅ |

**The mechanism.** `_TRAILING_PUNCT = '.!,;?'` (`textproc.py:36`, `".!?," + ";"`). Both the input
(`:65`) and each blocklist entry (`:66`) are normalized with `str.lower().rstrip(_TRAILING_PUNCT)`,
then compared via **exact set membership** (`key in {...}`). Because `rstrip` strips a **CHARACTER
SET from the right end** (not a suffix): `"bye!!"` → `"bye"`, and `"thank you."` → `"thank you"`
(the internal space is untouched — `rstrip` only strips from the right). This is why multi-word
hallucinations normalize correctly and why `"Bye"` / `"bye."` / `"BYE!"` all converge on `"bye"`
and match the `"bye."` entry.

**Exact, not substring.** With an explicit `["you"]` blocklist, `"yourself"` → key `"yourself"` is
**not** a member of `{"you"}` → returned unchanged; `"you"` → key `"you"` **is** a member → `None`.
Pinned by `test_blocklist_is_exact_not_substring` (`tests/test_textproc.py:101`).

---

## 4. Test Results

```
.venv/bin/python -m pytest tests/test_textproc.py -q
.....................                                                    [100%]
21 passed in 0.01s
```

**21 passed, 0 failed, 0 errors.** (The live count is 21; the PRP's "~20" was an estimate.) The
suite pins every PRD §4.7 step:

- **Step 1 (whitespace):** 4 tests (`:23`, `:27`, `:31`, `:35`) — internal-collapse, leading/trailing
  strip, **trailing-newline drop** (§4.3), tabs-as-whitespace.
- **Step 2 (min_chars):** 6 tests (`:43`, `:48`, `:52`, `:56`, `:61`, `:66`) — below-min reject,
  boundary accept, empty reject, whitespace-only reject, **cleaned-length-not-raw**, custom min_chars.
- **Step 3 (blocklist):** 6 tests (`:76`, `:80`, `:85`, `:92`, `:101`, `:109`) — default `"Thank you."`
  reject, case-insensitivity, **with/without trailing punct** (`Bye`/`bye.`/`BYE!`), entry-without-
  punct match, **exact-not-substring** (`yourself` survives), empty-blocklist never rejects.
- **Step 4 (return):** 4 tests (`:118`, `:123`, `:127`, `:135`) — internal-punctuation preserved,
  question-mark preserved, period preserved when not blocklisted, **never-appends-trailing-space**.
- **Aggregate:** `test_returns_none_for_every_rejection_reason` (`:142`) — every rejection reason
  yields `None`.

---

## 5. Mismatches / Drift

**None.** `clean()` implements all 4 PRD §4.7 steps faithfully:

- Step 1 is a benign superset of the PRD wording (strips all trailing whitespace, not only newlines)
  — strictly more correct, not drift (see §2 note).
- Steps 2-4 match the spec verbatim, one expression each.
- Both contract behaviors (§4.3 trailing newlines; blocklist normalization of `"Thank you."` /
  `"BYE!"` / `"bye"`) hold live.
- `_TRAILING_PUNCT` is the documented `'.!,;?'` character set; `rstrip` is correctly used as a
  char-set strip (not a suffix strip) — this is the intended mechanism, not a bug.

**No source files were modified.** `voice_typing/textproc.py`, `tests/test_textproc.py`, and
`voice_typing/config.py` are all **unchanged**.

---

## 6. Boundary Note — the VT-006 `"you"` removal is a §4.5 concern, NOT a `textproc.py` defect

PRD §4.5's literal blocklist lists a bare `"you"`; the code **omits** it (VT-006 — a blanket `"you"`
silently dropped dictating the single word "you"). This divergence is a **§4.5 config concern**,
already recorded in `gap_config.md` (P1.M1.T1.S1 §3 + S2 §2.3 + S3), where it is classified as
**compliant-by-design** and pinned by `tests/test_config.py:64`.

**`clean()`'s LOGIC is unaffected.** The blocklist is an **input** to `clean()` — `cfg.blocklist`.
`clean()` normalizes both the input and each entry identically (`:65-66`) and matches exactly
(`:66`, `key in {...}`). It correctly handles **whatever** blocklist it receives, whether the bare
`"you"` is present or absent. The VT-006 deviation is therefore a property of the **default
contents** (owned by P1.M1.T1.S1/S2), **not** of `textproc.py`'s normalization/matching logic. Do
**not** mistake the missing `"you"` for a `textproc` gap or "fix" it here — that would conflate two
distinct audit scopes and duplicate a config decision already recorded in `gap_config.md`.

---

## 7. Conclusion

**PASS — no fix required.** `voice_typing/textproc.py`'s `clean()` matches PRD §4.7 exactly: step 1
(strip + drop trailing newlines + collapse, `:55`), step 2 (min_chars gate on cleaned length,
`:58`), step 3 (normalize both sides + exact blocklist match, `:65-67`), step 4 (return cleaned
text, no space, `:70`). The §4.3 trailing-newline strip holds, and `"Thank you."` / `"BYE!"` /
`"bye"` each reject via their normalized entries. The 21-test suite (`tests/test_textproc.py`,
PRD test T2) pins every step including the exact-not-substring and never-append-space invariants.
The VT-006 `"you"` blocklist removal is correctly scoped as a §4.5 config concern (not a `textproc`
defect). **No code changes were required and none were made.**

This closes **P1.M1.T2.S1**. Downstream **P1.M2.T1** (main-loop audit) can rely on this report's
per-step compliance table as the reference for `clean()`'s contract (`txt = textproc.clean(text,
cfg.filter); if txt is not None: <type>` — `None` gates typing; `clean()` never appends a space, the
daemon's `on_final` does).
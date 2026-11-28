# PRP — P1.M1.T2.S1: Fit and confirm an initial prompt in the executor

## Goal

**Feature Goal**: Add a **child-side confirmed prompt-state primitive** to `PromptedExecutor` (voice_typing/prompt_engine.py) for the §4.8.1 initial-prompt seed: an API that **fits** the newest context to the *real* model prompt budget (tokenizer-proven, not a whitespace-word proxy), **installs** it observably, and returns a tri-state result — **known-applied / known-clear / unconfirmed** — instead of the ordinary best-effort `set_prompt()` that silently swallows failures. Normal rolling behavior (daemon-side `rolling_context_prompt()` → child `("prompt", …)` → `set_prompt()`) stays byte-identical. Consumed by P1.M1.T2.S2 (priming ACK across recorder IPC).

**Deliverable** (two files):
1. `voice_typing/prompt_engine.py` — (a) `fit_initial_prompt(text, *, tokenizer, max_length) -> str` pure fitter (newest-context suffix; tokenizer-proven token bound; never splits a Unicode codepoint; bypasses the `.?!` sentence cut); (b) `PromptedExecutor.install_initial_prompt(text: str | None) -> PromptState` — confirmed install/clear returning a frozen `PromptState` (`APPLIED` / `CLEAR` / `UNCONFIRMED` + opaque token count, NEVER text); (c) a 4 KiB UTF-8 pre-caret byte-suffix helper for the adapter's input bound (`utf8_suffix_within(text, max_bytes=4096)` — codepoint-safe); (d) Mode A docstrings documenting confirmed-vs-best-effort semantics, the token bound (derived from the warmed model, not a copied constant), and privacy (seed never in logs/exceptions/diagnostics).
2. `tests/test_prompt_engine.py` — fakes for a warmed model/tokenizer (deterministic char→token map incl. multibyte/CJK/emoji), plus the failure path; asserts applied/clear/unconfirmed, token bound, no-codepoint-split, 4 KiB suffix, and **no seed text in any log record or exception message**.

**Success Definition**:
- (a) `install_initial_prompt(text)` on a warmed executor returns `PromptState.APPLIED` with `self._prompt == fitted` and `len(tokenizer.encode(fitted)) <= budget`; on a **warmed** model the budget is `model.max_length // 2 - 1` read from the model (448 → **223** on the installed faster-whisper) — never a copied literal.
- (b) `install_initial_prompt(None | "")` returns `PromptState.CLEAR` with `self._prompt is None` — but **only if the executor is warm** (a cold model cannot prove the decode sees no prompt → `UNCONFIRMED`, prompt forced None defensively).
- (c) Any failure in the fit/install path (tokenizer/model missing or raising, un-warmed model, non-str input) → `PromptState.UNCONFIRMED`, prompt left `None` (fail-closed to context-free), **no raise**, and the exception text/log lines contain **no seed content** (counts only).
- (d) The fitter keeps the NEWEST context (tail), cuts on token boundaries only, never emits a partial codepoint (e.g. slicing inside a CJK char or emoji ZWJ sequence is impossible by construction: it slices on decoded-token boundaries), and does NOT apply the `.?!` boundary cut (`rolling_context_prompt` is untouched and still used by the ordinary path).
- (e) `utf8_suffix_within(text, 4096)` returns the longest codepoint-aligned suffix whose UTF-8 encoding is ≤ 4096 bytes; never raises.
- (f) Ordinary `set_prompt()` / `trim_prompt()` / `rolling_context_prompt()` are byte-identical in behavior; all existing prompt-engine tests stay green; `timeout 300 .venv/bin/pytest tests/test_prompt_engine.py -q` → all pass (30 baseline + new).
- (g) `git diff --name-only` == the two files; `recorder_host.py`/`daemon.py` untouched (S2 owns the IPC ACK; T1.S3 owns the shared-executor seam).

## User Persona

**Target User**: The P1.M1.T2.S2 implementer (IPC priming ACK) and S3 (warm/cold capture gating) — they need a primitive whose result they can trust as *known*, not "probably applied"; and ultimately the §4.8.1 opt-in integration user whose editor text seeds the first decode.

**Use Case**: Daemon arms with an eligible seed → child calls `install_initial_prompt(seed)` → `APPLIED` (token count N) → S2 ACKs priming → capture starts; or `UNCONFIRMED` → S3 gates capture off / degrades to context-free with a private hint.

**Pain Points**: (1) `trim_prompt`'s 200-whitespace-word cap is NOT a token proof (CJK text has no spaces → one "word" of hundreds of tokens; long joined words likewise) — the decoder could overflow Whisper's prompt window. (2) `set_prompt()` swallows its own failures, so a caller can never *confirm* the decode will actually see the prompt — the ACK S2 must send would be a lie. (3) Seed text leaking into logs/exceptions would put user dictation into journald.

## Why

- **The arch note is explicit** (system_context.md L14-15): `set_prompt()` "catches its own failures, so calling it cannot count as confirmation. Add an explicit confirmed path with observable known-applied/known-clear result … no exceptions containing seed text"; "the initial trim must genuinely fit the model context budget (word count alone is not a proof on CJK or long joined words; … use the warmed model/tokenizer and verify the actual cap rather than copying the 448 constant)"; "validate the adapter's 4 KiB UTF-8 suffix separately, without splitting codepoints"; "treat a timeout/partial update/ambiguous old child as unknown, not `unavailable`" (→ the tri-state, never a boolean).
- **Verified in the installed faster-whisper**: `transcribe.py:1532 get_prompt()` keeps `previous_tokens[-(self.max_length // 2 - 1):]` (so over-long prompts are silently *clipped from the left*, dropping the OLDEST tokens — the opposite of what a tail-fitter wants, and a silent behavior we must pre-empt by fitting ourselves); `self.max_length = 448` (`transcribe.py:722`); the tokenizer's `encode(text) -> List[int]` / `decode(tokens) -> str` exist (`tokenizer.py:92/95`). We read `model.max_length` from the warmed object — not the literal.
- **Fail-closed is the PRD §8 discipline**: "on failure degrade to context-free decoding + log, never crash." Unconfirmed → prompt None.
- **Scope discipline**: S1 = the child-side primitive only. S2 = the recorder-IPC ACK (daemon↔child ordering, tokens/generation). S3 = gating capture. S4 = handing the seed off at the first accepted final. None of those files are touched here.

## What

Add three things to `prompt_engine.py` + tests. No IPC, no daemon, no recorder_host, no config changes.

### The contract (exact)

```python
class PromptState(enum.Enum):          # frozen semantics; str-backed for easy JSON/log use
    APPLIED = "applied"                # fitted prompt installed on a WARMED executor; proven bound
    CLEAR = "clear"                    # prompt is None on a WARMED executor (proven)
    UNCONFIRMED = "unconfirmed"        # cold/broken tokenizer or model, or any failure → unknown

@dataclass(frozen=True)
class PromptInstallResult:
    state: PromptState
    tokens: int | None = None          # opaque count ONLY — never text; None when not APPLIED

def prompt_token_budget(model) -> int | None:
    """model.max_length // 2 - 1 (faster-whisper get_prompt's previous-tokens clip), read from the
    warmed model; None if unavailable/invalid."""

def fit_initial_prompt(text: str, *, encode, budget: int) -> str:
    """Pure: whitespace-normalize, then keep the NEWEST token-aligned suffix whose encode() length
    <= budget. Slices on decoded token boundaries → never splits a codepoint. No sentence cut."""

def utf8_suffix_within(text: str, max_bytes: int = 4096) -> str: ...

PromptedExecutor.install_initial_prompt(self, text: str | None) -> PromptInstallResult: ...
```

### Success Criteria

- [ ] `PromptState` enum + frozen `PromptInstallResult(state, tokens)` exist in prompt_engine.py; `tokens` is a count, never text.
- [ ] `fit_initial_prompt` keeps the newest tokens, result `encode(result)` ≤ budget, no codepoint split, ignores `.?!` boundaries.
- [ ] `prompt_token_budget(model)` returns `model.max_length // 2 - 1` (223 for 448) from the object; None on AttributeError/TypeError/non-int/`<1`.
- [ ] `install_initial_prompt(text)` → APPLIED + installed on warm; `None/""` → CLEAR + None on warm; cold/any failure → UNCONFIRMED + prompt forced None; never raises.
- [ ] `utf8_suffix_within` is codepoint-safe, ≤ 4096 bytes, never raises.
- [ ] No seed text in any emitted log record or exception message (test asserts over `caplog.records` + `str(exc)`).
- [ ] `set_prompt`/`trim_prompt`/`rolling_context_prompt` unchanged (existing tests green); full file green.
- [ ] Only the two files change.

## All Needed Context

### Context Completeness Check

_Pass._ The executor's current prompt plumbing (read verbatim :143-200), the installed faster-whisper `get_prompt` clip + `max_length` (verified :1532/:722), the tokenizer `encode/decode` API (:92/:95), the existing test fake pattern (`_install_fake_faster_whisper` + `_executor()`), and the sibling boundaries are all verified. Pure unit tests with fakes; no CUDA/model load.

### Documentation & References

```yaml
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: L14 — set_prompt can't confirm; need known-applied/known-clear/unconfirmed, no seed in
       exceptions. L15 — initial seed bypasses the sentence cut; trim must fit the REAL budget via
       the warmed model/tokenizer (don't copy 448); 4 KiB UTF-8 suffix validated separately without
       splitting codepoints; unknown ≠ unavailable; never put seed in logs/feedback/replies.
  critical: "This note IS the contract. Re-read both lines before implementing."

- file: voice_typing/prompt_engine.py
  why: PromptedExecutor @143; __init__ @162 (self._model=None lazily built; self._prompt;
        self._lock); set_prompt @181 (best-effort: try/except → logger.exception, keeps previous);
        `prompt` property @197; `_build_model` ~@250 (`WhisperModel(model_size_or_path=…, device=…,
        compute_type=…)`); `_transcribe_locked` ~@264 reads `self._prompt` under lock and passes
        `initial_prompt=`. trim_prompt @102 (word proxy), rolling_context_prompt @119 (sentence cut).
  pattern: "install_initial_prompt must take self._lock for the write (same discipline as the
            decode read) and read the tokenizer/model from the SAME warmed `self._model` the decode
            will use — that equality is what makes APPLIED a *known* state."
  gotcha: "The warmed faster-whisper WhisperModel exposes `.max_length` (int) and its tokenizer via
          the `tokenizer` attribute used by transcribe (hf tokenizer at `.hf_tokenizer`; the
          transcribe-time Tokenizer wraps it with `.encode`). Access defensively: if the attribute
          shape differs → UNCONFIRMED, never a guess."

- file: .venv/lib/python3.12/site-packages/faster_whisper/transcribe.py
  why: get_prompt @1532: `previous_tokens[-(self.max_length // 2 - 1):]` — over-long prompts are
        LEFT-CLIPPED silently; `self.max_length = 448` @722 → budget 223. transcribe @176-207
        encodes `options.initial_prompt` via `tokenizer.encode`. The reason we must fit ourselves
        and why the budget formula is exactly this one.
  critical: "Mirror the clip formula so our fitted prompt never triggers faster-whisper's own clip
            (which would drop the OLDEST tokens and make our 'newest context' claim false)."

- file: .venv/lib/python3.12/site-packages/faster_whisper/tokenizer.py
  why: `encode(text) -> List[int]` @92, `decode(tokens) -> str` @95 — the two calls the fitter/
        budget proof use. `split_tokens_on_unicode` @161 is the library's own proof that token
        boundaries can be mapped back to text safely.

- file: tests/test_prompt_engine.py
  why: Fakes to reuse/extend: `_install_fake_faster_whisper(monkeypatch, …)` @60-103 (installs a
        fake `faster_whisper.WhisperModel` with `.transcribe`), `_executor()` @106, `_FakeSegment`
        @54. Existing set_prompt/trim/rolling tests pin the ordinary path — they MUST stay green.
  pattern: "Extend the fake `_Model` (or add a local `_WarmModel`) with `max_length = 448` and a
            `tokenizer` exposing `encode`/`decode` backed by a deterministic map (e.g. one token per
            Unicode codepoint for ASCII, multi-token for a CJK char / an emoji ZWJ sequence) so the
            bound + no-split assertions are exact. Install it on `ex._model` directly (the executor
            reads `self._model` for the budget/tokenizer) — no real model load."

- docfile: plan/009_ef3b49b0fc0d/P1M1T1S3/PRP.md
  why: The SHARED-executor contract (Complete): exactly ONE PromptedExecutor injected as both
        transcription_executor and realtime_transcription_executor. `install_initial_prompt` is a
        method on that one object — no lane fan-out, no recorder_host change.
  critical: "S2 (ACK across IPC) and T1.S3 (seam) are disjoint from this file set; T1.S4 (parallel,
            installer/CLI) touches neither."
```

### Current / Desired tree

```bash
voice_typing/prompt_engine.py     # ← EDIT: +PromptState, +PromptInstallResult, +prompt_token_budget,
                                  #   +fit_initial_prompt, +utf8_suffix_within, +PromptedExecutor.install_initial_prompt,
                                  #   +Mode A docstrings. set_prompt/trim/rolling UNCHANGED.
tests/test_prompt_engine.py       # ← EDIT: +warm model/tokenizer fakes, +confirmed/clear/unconfirmed/
                                  #   bound/no-split/4KiB/privacy tests. Existing tests unchanged.
# recorder_host.py, daemon.py — S2/S3's. Untouched.
```

### Known Gotchas

```python
# CRITICAL #1 — "CONFIRMED" MEANS PROVEN AGAINST THE SAME OBJECT THE DECODE USES. APPLIED is only
# honest if the tokenizer/model consulted for the bound is the warmed `self._model` that
# `_transcribe_locked` will call. A cold model (self._model is None) → UNCONFIRMED (even for a
# CLEAR request: you cannot prove the decode sees no prompt if the decode object doesn't exist yet
# — force `self._prompt = None` defensively, but report UNCONFIRMED). Never build the model inside
# install_initial_prompt (that would import CUDA on the daemon's cmd thread — warmup owns that).

# CRITICAL #2 — FIT ON TOKEN BOUNDARIES, KEEP THE NEWEST. Algorithm: norm = " ".join(text.split());
# toks = encode(norm). If len(toks) <= budget → done. Else binary-search (or linear from the end)
# the smallest start index s such that len(encode(decode(toks[s:]))) <= budget; return that decoded
# string. Because you slice the TOKEN list and re-decode, a multi-token codepoint/emoji never gets
# cut in half — assert with a CJK + emoji ZWJ fixture ("👩‍💻" = several codepoints) where a naive
# byte/char slice at the budget WOULD split it.

# CRITICAL #3 — DO NOT USE rolling_context_prompt FOR THE SEED. The seed is pre-caret editor text;
# the sentence-boundary cut is the ROLLING path's rule (after the first accepted final). The fitter
# ignores `.?!` entirely. Keep rolling_context_prompt byte-identical.

# CRITICAL #4 — PRIVACY: NO SEED TEXT ANYWHERE. Log lines: counts only ("context-prompt: initial
# install unconfirmed (tokenizer error: <exc type name>)" — exc TYPE, not str(exc), since a
# tokenizer exception could embed the input). Exceptions: never raise with the text. The test
# asserts: for every caplog record + every raised/caught exception string, seed substring NOT present.

# CRITICAL #5 — utf8_suffix_within MUST BE CODEPOINT-ALIGNED. Walk codepoints from the END,
# accumulating len(ch.encode("utf-8")), stop before exceeding max_bytes. A 4-byte emoji at the edge
# must be included whole or excluded whole — never half. Non-str input → "". max_bytes<=0 → "".

# CRITICAL #6 — THE RESULT TYPE CARRIES ONLY A COUNT. PromptInstallResult.tokens = len(encode(
# fitted)) (an int) — S2 will copy it into an ACK; it must be safe to log/serialize. No `text`
# field, no `__repr__` leaking content (frozen dataclass with just state+tokens is safe by default).

# GOTCHA #7 — FULL PATHS + timeout (AGENTS.md): `timeout 300 .venv/bin/pytest tests/test_prompt_engine.py -q`.
# Fake-model only; no CUDA. No ruff/mypy configured.
```

## Implementation Blueprint

### Data models and structure

```python
class PromptState(str, enum.Enum):
    APPLIED = "applied"; CLEAR = "clear"; UNCONFIRMED = "unconfirmed"

@dataclass(frozen=True)
class PromptInstallResult:
    state: PromptState
    tokens: int | None = None   # count only (None unless APPLIED)

def prompt_token_budget(model: Any) -> int | None:
    try:
        ml = int(model.max_length)
    except Exception:
        return None
    b = ml // 2 - 1
    return b if b >= 1 else None

def fit_initial_prompt(text: str, *, encode: Callable[[str], list[int]],
                       decode: Callable[[list[int] | Any], str], budget: int) -> str:
    # pure; token-boundary tail fit; no sentence cut; never raises (returns "" on bad input)

def utf8_suffix_within(text: str, max_bytes: int = 4096) -> str: ...

PromptedExecutor.install_initial_prompt(self, text: str | None) -> PromptInstallResult:
    with self._lock:
        model = self._model
        if model is None: self._prompt = None; return UNCONFIRMED   # cold (CRITICAL #1)
        budget = prompt_token_budget(model)
        tok = getattr(model, "tokenizer", None); enc = getattr(tok, "encode", None); dec = getattr(tok, "decode", None)
        if not (budget and callable(enc) and callable(dec)):
            self._prompt = None; log(count-only); return UNCONFIRMED
        try:
            if not (text or "").strip():
                self._prompt = None; return PromptInstallResult(PromptState.CLEAR, None)
            fitted = fit_initial_prompt(text, encode=enc, decode=dec, budget=budget)
            n = len(enc(fitted))
            if n > budget or n == 0: self._prompt = None; return UNCONFIRMED   # bound must be proven
            self._prompt = fitted
            logger.info("context-prompt: initial install applied (%d tokens, budget %d)", n, budget)
            return PromptInstallResult(PromptState.APPLIED, n)
        except Exception as exc:   # CRITICAL #4: type name only
            self._prompt = None
            logger.warning("context-prompt: initial install unconfirmed (%s)", type(exc).__name__)
            return PromptInstallResult(PromptState.UNCONFIRMED, None)
```

### Tasks

```yaml
Task 1: EDIT prompt_engine.py — add the types + pure helpers (PromptState, PromptInstallResult,
  prompt_token_budget, fit_initial_prompt, utf8_suffix_within) ABOVE PromptedExecutor, with Mode A
  docstrings: confirmed-vs-best-effort, the budget formula + "read from the warmed model, never a
  copied 448", privacy (counts only).
Task 2: EDIT prompt_engine.py — add PromptedExecutor.install_initial_prompt (blueprint above) right
  after set_prompt; docstring states: takes the lock; APPLIED only on a warm model; CLEAR only warm;
  UNCONFIRMED forces prompt None (fail-closed); never raises; seed never logged. Update the class
  docstring's "Failure contract" paragraph to name both paths (set_prompt = best-effort rolling;
  install_initial_prompt = confirmed seed).
Task 3: EDIT tests/test_prompt_engine.py — fakes + tests:
  - _WarmModel(max_length=448) with .tokenizer = _Tok (encode: 1 token/codepoint for BMP, 2 tokens
    for astral codepoints — deterministic; decode inverse) — or simpler: 1 token per codepoint, and
    a separate CJK/emoji case. Install via `ex._model = _WarmModel(...)`.
  - Tests: applied_on_warm (tokens<=223, ex.prompt==fitted, encode(fitted)<=223); clear_on_warm;
    unconfirmed_when_cold (prompt forced None); unconfirmed_when_tokenizer_raises; unconfirmed_when_
    budget_missing (model without max_length); fit_keeps_newest_tokens (400-char ASCII → tail of
    223 tokens); fit_never_splits_codepoint (emoji ZWJ "👩‍💻" ×N at the boundary → result endswith a
    whole emoji and is decodable); fit_ignores_sentence_boundaries (text with '.' inside is NOT cut
    at '.'); utf8_suffix_codepoint_safe (4-byte char at the edge; result.encode()<=4096; whole);
    no_seed_text_in_logs_or_exceptions (caplog at DEBUG + capture str(exc) across the failure path);
    ordinary_set_prompt_unchanged (existing tests cover; add one asserting set_prompt still
    best-effort and does NOT change install semantics).
Task 4: VALIDATE (Loop). Commit msg if asked: "P1.M1.T2.S1: confirmed initial-prompt install
  (applied/clear/unconfirmed) + tokenizer-proven fit + codepoint-safe 4 KiB suffix (prompt_engine)".
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T2.S2 (ACK across recorder IPC): wraps install_initial_prompt's result in the
  child's ACK (opaque state + token count; no text). S1's tri-state maps 1:1; S2 treats timeout/
  partial as unconfirmed too.
DOWNSTREAM — P1.M1.T2.S3 (gate warm/cold capture): uses UNCONFIRMED to gate capture / degrade
  to context-free; S4 hands the seed off after the first accepted final (then rolling path resumes).
UNCHANGED: set_prompt/trim_prompt/rolling_context_prompt (ordinary rolling path), recorder_host
  (shared executor seam, T1.S3), daemon, config.
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# L1 static:
.venv/bin/python -c "import voice_typing.prompt_engine as p; assert p.PromptState.APPLIED and p.PromptInstallResult and callable(p.fit_initial_prompt) and callable(p.utf8_suffix_within) and hasattr(p.PromptedExecutor,'install_initial_prompt'); print('L1 PASS')"
grep -c "def set_prompt\|def trim_prompt\|def rolling_context_prompt" voice_typing/prompt_engine.py   # 3 — unchanged
# L2 full file:
timeout 300 .venv/bin/pytest tests/test_prompt_engine.py -q 2>&1 | tail -2            # all pass
timeout 300 .venv/bin/pytest tests/test_prompt_engine.py -k "install or fit or suffix or seed" -q 2>&1 | tail -2
# L3 scope + purity:
git diff --name-only | grep -vE 'prompt_engine.py|test_prompt_engine.py' && echo "L3 FAIL" || echo "L3 PASS"
git diff --quiet voice_typing/recorder_host.py voice_typing/daemon.py && echo "L3 PASS (S2/T1.S3 files untouched)"
.venv/bin/python -c "import sys, voice_typing.prompt_engine; sys.exit(0 if 'faster_whisper' not in sys.modules else 1)" && echo "L3 import-purity PASS"
```

## Final Validation Checklist

- [ ] L1: types + helpers + method exist; the three ordinary functions unchanged.
- [ ] L2: full test_prompt_engine.py green (30 baseline + new); the new install/fit/suffix/seed tests green.
- [ ] L3: only the two files changed; recorder_host/daemon untouched; import purity (no faster_whisper at import).
- [ ] APPLIED only on warm + proven bound (≤ `model.max_length//2-1`, read from the model); CLEAR only warm; UNCONFIRMED forces prompt None, never raises.
- [ ] Fit keeps newest tokens, token-boundary aligned (no codepoint split), ignores `.?!`.
- [ ] utf8_suffix_within codepoint-safe ≤ 4096 bytes.
- [ ] No seed text in any log record or exception string (asserted).
- [ ] Result carries counts only (no text field).

## Anti-Patterns

- ❌ Don't reuse `trim_prompt`'s word proxy or copy the 448/223 literal — read `model.max_length` from the warmed object (CRITICAL #1; arch L15).
- ❌ Don't report APPLIED/CLEAR on a cold model, and don't build the model inside install (CUDA on the cmd thread) — UNCONFIRMED + prompt None.
- ❌ Don't slice by bytes/chars when fitting — slice the token list and re-decode (CRITICAL #2); don't apply the sentence cut to the seed (CRITICAL #3).
- ❌ Don't log or raise seed text — counts and exception TYPE names only (CRITICAL #4); no text field on the result (CRITICAL #6).
- ❌ Don't let `utf8_suffix_within` emit half a codepoint (CRITICAL #5).
- ❌ Don't touch set_prompt/trim/rolling behavior, recorder_host, daemon, or config (S2/S3/T1.S3 own those).
- ❌ No bare pytest; `timeout 300` + `.venv/bin/pytest` (GOTCHA #7).

## Confidence Score

**9/10** — the contract is fully specified by the arch note, the executor plumbing and the installed faster-whisper clip/budget/tokenizer API are verified verbatim, and the test-fake pattern is established in the same file. The −1 is the exact warmed-WhisperModel attribute shape for the tokenizer at runtime (the unit tests pin it via a fake; if the real object exposes the tokenizer differently, the defensive `getattr` path yields UNCONFIRMED — fail-closed — and S2's live ACK run will surface it; the budget `.max_length` attribute is verified at transcribe.py:722).

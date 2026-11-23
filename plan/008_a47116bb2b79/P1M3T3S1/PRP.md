# PRP — P1.M3.T3.S1: output.delivery key + precondition triple enforcement

## Goal

**Feature Goal**: Add the `output.delivery` config key (`"stream-edit"` | `"bulk-text"`, PRD §4.2sexies
Rev 4) to `OutputConfig` + `config.toml`, with **load-time enforcement of the bulk-text precondition
triple**: `delivery="bulk-text"` requires `output.streaming=true` AND `asr.graceful_stop=false` AND
`cancel.keypress_action="disarm"`, else a clear **ValueError naming all violated keys** (collected,
not first-fail). Default stays `"stream-edit"` (opt-in until G6 graduation) — **zero behavior change at
default**. Bump the key-set pin 26 → 27.

**Deliverable** (4 modified files, nothing else):
1. `voice_typing/config.py` — `OutputConfig.delivery` field + value/type validation; NEW top-level
   `VoiceTypingConfig.__post_init__` enforcing the cross-section triple.
2. `config.toml` — `delivery = "stream-edit"` line in `[output]` with the Mode A comment (opt-in
   status + the triple).
3. `tests/test_config_repo_default.py` — key-set pin output 3→4 keys, total 26→27.
4. `tests/test_config.py` — value/type validation tests + the full precondition matrix.

**Success Definition**: `timeout 60 .venv/bin/python -m pytest tests/test_config.py
tests/test_config_repo_default.py -q` → 0 failed; the repo-default lockstep test
(`test_repo_config_toml_equals_defaults`) still green (config.py ↔ config.toml in lockstep); a
bulk-text + streaming=false load raises ValueError whose message contains `output.streaming`;
`git status --porcelain` shows exactly the 4 files.

## User Persona

**Target User**: the operator opting into bulk-text delivery (a config author), and the future G6
graduation round that flips the default. Secondarily every future task (P1.M6.T2.S1 daemon wiring,
P1.M3.T3.S2 status surface) that reads `cfg.output.delivery`.

**Use Case**: Set `[output] delivery = "bulk-text"` in config.toml → the daemon either arms the new
path or fails AT LOAD with an actionable message naming exactly which of the three preconditions is
violated and its current value.

**Pain Points Addressed**: bulk-text (§4.2sexies R.3/R.5) forbids typing fallbacks, drains, and the
freeze keypress action — a config combining bulk-text with any of those would produce incoherent
runtime behavior far from the config mistake (the exact failure mode VT-005/Issue 3 already
established as worth rejecting at load).

## Why

- PRD §4.5 pins the key + triple verbatim: `bulk-text requires streaming=true, graceful_stop=false,
  keypress_action="disarm"`; PRD §4.2sexies R.3 mandates "the bulk adapter MUST NOT expose
  type_character/press_backspace or any typing fallback" and R.5's HALT semantics — hence the triple.
- This is the config half of P1.M3.T3; S2 (feedback/voicectl surface) and P1.M6.T2.S1 (daemon wiring)
  build on the key existing with a guaranteed-coherent value combination.
- The repo already has the fail-fast posture (VT-005 device, Issue 3 backend, BUG-006 tables) — this
  extends it with the FIRST cross-section validation, which is why it needs a new top-level
  `__post_init__`.

## What

- `OutputConfig.delivery: str = "stream-edit"`; `__post_init__` validates: non-str → TypeError
  (string-field precedent); `not in ("stream-edit", "bulk-text")` → ValueError (device/backend
  precedent — "the TYPE is correct, the VALUE is not").
- NEW `VoiceTypingConfig.__post_init__`: when `self.output.delivery == "bulk-text"`, collect ALL
  violated preconditions — `not self.output.streaming` → `output.streaming`; `self.asr.graceful_stop`
  → `asr.graceful_stop`; `self.cancel.keypress_action != "disarm"` → `cancel.keypress_action` — and
  if any, raise ONE ValueError naming every violated (section-qualified) key with its got-value.
- `config.toml` `[output]`: `delivery = "stream-edit"` + Mode A comment documenting opt-in status
  ("default until G6 graduation") and the triple.
- Key-set pin: `"output": {"backend", "append_space", "streaming", "delivery"}`, docstring 26 → 27.
- Tests: invalid value / non-str type; happy path bulk-text with all-default companions (which
  satisfy the triple: streaming=True, graceful_stop=False, keypress_action="disarm"); each single
  violation; a two-violation case naming both; stream-edit ignores all violations.

### Success Criteria

- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q` → 0 failed.
- [ ] Key-set pin asserts 27 keys; `output` = 4 keys.
- [ ] `VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text", "streaming": False}})` → ValueError message contains `output.streaming` (and does NOT mention unviolated keys).
- [ ] Two-violation config → error names BOTH keys.
- [ ] `delivery="bulk-text"` + all-default asr/cancel → loads (no error).
- [ ] Default `VoiceTypingConfig().output.delivery == "stream-edit"`; defaults test updated.
- [ ] `git status --porcelain` → exactly the 4 files.

## All Needed Context

### Context Completeness Check

_Pass._ The research note pins: the exact current state (OutputConfig at config.py:140-168, its
validation-style precedent, the CRITICAL fact that `graceful_stop` lives in **[asr]** and
`keypress_action` in **[cancel]** — not [output] as PRD §4.5's listing suggests — which forces the
top-level `__post_init__`), the verbatim PRD contract, the design (field + both validation layers +
error-message format), the test conventions in tests/test_config.py (constructor-based value tests,
from_toml dict round-trips, pytest.raises + match), and verified validation commands.

### Documentation & References

```yaml
# MUST READ — this task's research: current state, design, error format, validation commands
- docfile: plan/008_a47116bb2b79/P1M3T3S1/research/delivery_key_preconditions.md
  section: "ALL load-bearing (§0 current state incl. the graceful_stop-in-[asr] gotcha, §2 design, §4 commands)."

# MUST READ — the file being modified (the whole validation architecture is its own precedent)
- file: voice_typing/config.py
  why: "OutputConfig (140-168): field placement + the __post_init__ value/type-validation pattern
        (backend ValueError precedent, streaming TypeError precedent — mirror BOTH for delivery).
        AsrConfig.graceful_stop field (~96-99) + CancelConfig.keypress_action (~176-177): the two
        remote members of the triple. VoiceTypingConfig (bottom): NO __post_init__ today — you ADD
        one; it must not disturb from_toml's overlay (post-init runs after all construction)."
  gotcha: "graceful_stop is in [asr], NOT [output] (PRD §4.5's listing is misleading vs the code) —
           the triple is CROSS-SECTION, hence the top-level post-init."
  critical: "Keep config.py pure data + loader (stdlib only, no daemon imports)."

# MUST READ — the lockstep pair + the pin
- file: config.toml
  why: "[output] block at lines 45-50 — add delivery after streaming. The repo-default lockstep test
        parses this file, so the value AND presence must exactly mirror the dataclass default."
- file: tests/test_config_repo_default.py
  why: "Lines 37-63: the key-set pin. Add 'delivery' to the output set; docstring 'the 26 schema
        keys' → 27. test_repo_config_toml_equals_defaults (lines 16-28) enforces value lockstep."

# MUST READ — test conventions to follow
- file: tests/test_config.py
  why: "Style: plain functions; value-validation via direct constructor (test_invalid_backend_value_raises
        :384, test_duck_mode_rejects_unknown_value :258); happy paths via VoiceTypingConfig.from_toml(dict);
        pytest.raises(..., match=...). test_defaults_match_prd_4_5 (:41) asserts per-field defaults —
        add delivery=='stream-edit'. New precondition tests follow the from_toml dict-literal pattern."

# MUST READ — the spec source
- docfile: PRD.md
  why: "§4.5 [output] delivery line (verbatim contract + comment wording); §4.2sexies R.3 (no typing
        fallback in bulk mode) + R.5 (HALT/keypress) — WHY the triple."
  critical: "READ-ONLY. Do not edit PRD.md."

# READ — coordination (disjoint files; do not touch)
- file: plan/008_a47116bb2b79/P1M3T2S3/PRP.md
  why: "The parallel G2-gate item (bulk_controller.py + its tests + architecture/g2_gate_record.md).
        Disjoint from config. Do NOT touch bulk_controller.py/bulk_delivery.py."
  critical: "P1.M3.T3.S2 (next) owns feedback.py/ctl.py delivery-status surface — also out of scope
             here. P1.M6.T2.S1 owns the daemon's CONSUMPTION of cfg.output.delivery — this task adds
             NO consumer (grep confirms none exists; that is expected)."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/config.py              # ← EDIT: OutputConfig.delivery + VoiceTypingConfig.__post_init__
config.toml                         # ← EDIT: [output] delivery line + Mode A comment
tests/test_config.py                # ← EDIT: validation + precondition-matrix tests
tests/test_config_repo_default.py   # ← EDIT: key-set pin 26→27
# NOT touched: bulk_controller.py, bulk_delivery.py, daemon.py, feedback.py, ctl.py, streaming.py
```

### Desired Codebase tree with files to be added

No new files — 4 modifications only.

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — graceful_stop IS AN [asr] FIELD. The triple spans THREE sections ([output].streaming,
#   [asr].graceful_stop, [cancel].keypress_action). OutputConfig.__post_init__ CANNOT see the others —
#   the cross-section gate MUST be a NEW VoiceTypingConfig.__post_init__. Verify with:
#   grep -n 'graceful_stop' voice_typing/config.py  (it's in AsrConfig).

# CRITICAL #2 — COLLECT ALL VIOLATIONS, RAISE ONCE. The contract: "a clear ValueError naming ALL
#   three violated keys" — build a list of (key, got) clauses, then raise ONE ValueError:
#   'output.delivery="bulk-text" requires [output] streaming=true (got false), [asr]
#   graceful_stop=false (got true), [cancel] keypress_action="disarm" (got "freeze")' — only the
#   violated ones appear. First-fail-only is a contract miss (test the two-violation case).

# CRITICAL #3 — VALUEERROR vs TYPEERROR DISCIPLINE. Wrong VALUE (delivery="Bulk-Text") → ValueError;
#   wrong TYPE (delivery=true) → TypeError. Exactly the existing device/backend precedent — keep the
#   citation comment style. The cross-section precondition is a VALUE problem → ValueError.

# CRITICAL #4 — DEFAULT MUST BE A NO-OP. Default delivery="stream-edit" short-circuits the gate;
#   VoiceTypingConfig() (all defaults) and every existing config must load identically. Run the full
#   tests/test_config.py before/after — only additions, zero changed assertions.

# CRITICAL #5 — LOCKSTEP OR THE PIN FAILS. config.py default and config.toml value must BOTH land in
#   the same changeset or test_repo_config_toml_equals_defaults fails. Key count: currently 26
#   (asr 11, output 3, cancel 3, audio 2, feedback 4, filter 2, log 1) → 27.

# GOTCHA #6 — NO CONSUMER YET, BY DESIGN. grep cfg.output.delivery across voice_typing/ returns
#   nothing today; the daemon wiring is P1.M6.T2.S1. Do NOT add a consumer, and do NOT touch
#   feedback.py/ctl.py (P1.M3.T3.S2 owns the status surface).

# GOTCHA #7 — TIMEOUT DISCIPLINE (AGENTS.md). Wrap every pytest/python invocation in `timeout 60`
#   (config tests are pure-stdlib, seconds-fast). Use .venv/bin/python (zsh aliases python3).
```

## Implementation Blueprint

### Data models and structure

```python
# OutputConfig (config.py:140-168) — add after `streaming`:
delivery: str = "stream-edit"  # Rev 4 §4.2sexies: "bulk-text" = paste-as-policy path
                               # (opt-in until G6); "stream-edit" = today's behavior.
                               # bulk-text additionally requires (checked at the TOP level):
                               # output.streaming=true, asr.graceful_stop=false,
                               # cancel.keypress_action="disarm" — see VoiceTypingConfig.

# In OutputConfig.__post_init__ (mirror the backend/streaming guards):
if not isinstance(self.delivery, str):
    raise TypeError(f"[output] delivery expects str, got {type(self.delivery).__name__}: {self.delivery!r}")
if self.delivery not in ("stream-edit", "bulk-text"):
    raise ValueError(f'[output] delivery must be "stream-edit" or "bulk-text", got {self.delivery!r}')

# NEW — VoiceTypingConfig gains (first time this dataclass has a post-init):
def __post_init__(self) -> None:
    """Cross-section gate (P1.M3.T3.S1): bulk-text's precondition triple.

    Runs for BOTH construction paths (defaults + from_toml overlay) since __post_init__
    fires after all field construction. Default delivery="stream-edit" short-circuits.
    """
    if self.output.delivery != "bulk-text":
        return
    required = [
        ("[output] streaming", self.output.streaming is True, "true"),
        ("[asr] graceful_stop", self.asr.graceful_stop is False, "false"),
        ('[cancel] keypress_action', self.cancel.keypress_action == "disarm", '"disarm"'),
    ]
    violated = [f"{key}={want} (got {got!r})" for key, ok, want in
                ((k, o, w) for (k, o, w) in required if not o)
                for got in [_lookup(self, k)]]   # or simpler: build (key, ok, want, got) tuples
    if violated:
        raise ValueError(
            'output.delivery="bulk-text" requires ' + ", ".join(violated)
        )
# (Implement the tuple-building plainly — 4-tuples (key, ok, want, got); the sketch above is shape,
#  not verbatim code. got-values: self.output.streaming, self.asr.graceful_stop,
#  self.cancel.keypress_action.)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT (no mutation)
  - RUN: grep -n 'graceful_stop\|keypress_action\|class OutputConfig\|class VoiceTypingConfig' voice_typing/config.py
         timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q | tail -1
  - EXPECTED: graceful_stop in AsrConfig, keypress_action in CancelConfig (Critical #1); current suites green (baseline).
  - DO NOT edit anything yet.

Task 2: MODIFY voice_typing/config.py
  - ADD OutputConfig.delivery field + its two __post_init__ guards (type → TypeError; value → ValueError).
  - ADD VoiceTypingConfig.__post_init__ cross-section gate (collect all violations → ONE ValueError,
    message format per Critical #2). Cite the precedent (VT-005/Issue 3) in a short comment.
  - FILE: voice_typing/config.py

Task 3: MODIFY config.toml (lockstep — same changeset as Task 2 or the pin test fails)
  - ADD in [output], after the streaming line: delivery = "stream-edit" with the Mode A comment:
    opt-in status (default until G6 graduation, PRD §4.2sexies), "bulk-text" = paste-as-policy path
    (one-edit corrections, NO typing/backspace fallback), and the triple precondition (naming all
    three section-qualified keys). FILE: config.toml

Task 4: MODIFY tests/test_config_repo_default.py — pin 26→27
  - ADD "delivery" to the output key set; update the docstring "the 26 schema keys" → 27.
  - FILE: tests/test_config_repo_default.py

Task 5: MODIFY tests/test_config.py — validation + precondition matrix
  - ADD (follow the file's conventions — constructor-based value tests, from_toml dict happy paths):
    test_invalid_delivery_value_raises / test_delivery_rejects_non_str / both values load round-trip;
    defaults: delivery == "stream-edit" (extend test_defaults_match_prd_4_5);
    bulk-text + all-default companions → loads;
    bulk-text + streaming=false → ValueError matching 'output.streaming' (and NOT naming others);
    bulk-text + graceful_stop=true → matches 'asr.graceful_stop';
    bulk-text + keypress_action="freeze" → matches 'cancel.keypress_action';
    bulk-text + two violations → matches BOTH keys in one message;
    stream-edit + all three violated → loads fine.
  - FILE: tests/test_config.py

Task 6: VALIDATE — run the loops below; then git status --porcelain == the 4 files exactly.
```

### Integration Points

```yaml
CONFIG SCHEMA:
  - add key: "[output] delivery = 'stream-edit' (27th schema key; lockstep config.py + config.toml)"
TEST SURFACE:
  - key-set pin: "tests/test_config_repo_default.py output set → {backend, append_space, streaming, delivery}"
  - lockstep test: "test_repo_config_toml_equals_defaults stays green (no drift)"
FUTURE CONSUMERS (NOT here): "P1.M3.T3.S2 (status surface), P1.M6.T2.S1 (daemon dispatch), P1.M7.T1 (G6 default flip)"
DEPENDENCIES: "none new (stdlib only)."
```

## Validation Loop

### Level 1: Syntax

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile voice_typing/config.py tests/test_config.py tests/test_config_repo_default.py && echo "L1 OK"
```

### Level 2: Config suites

```bash
timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q | tail -2
# Expected: 0 failed (all pre-existing tests unchanged + the new matrix green).
```

### Level 3: Behavioral smoke of the gate

```bash
timeout 60 .venv/bin/python -c "
from voice_typing.config import VoiceTypingConfig
VoiceTypingConfig.from_toml({'output': {'delivery': 'bulk-text'}}); print('ok: all-default triple loads')
try:
    VoiceTypingConfig.from_toml({'output': {'delivery': 'bulk-text', 'streaming': False}, 'asr': {'graceful_stop': True}})
    print('FAIL: no error')
except ValueError as e:
    assert 'output.streaming' in str(e) and 'asr.graceful_stop' in str(e) and 'keypress_action' not in str(e), e
    print('ok: both named, unviolated omitted')
print(VoiceTypingConfig().output.delivery)"   # ok lines + stream-edit
```

### Level 4: Scope guard + no-regression

```bash
git status --porcelain   # exactly: voice_typing/config.py, config.toml, tests/test_config.py, tests/test_config_repo_default.py
grep -rn 'output.delivery\|\.delivery' voice_typing/daemon.py voice_typing/feedback.py voice_typing/ctl.py || echo "ok: no consumer added (by design)"
timeout 120 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q | tail -1   # re-run clean
```

## Final Validation Checklist

- [ ] L1-L4 green; git status shows exactly the 4 files; no consumer added.
- [ ] Key-set pin at 27; repo-default lockstep test green.
- [ ] delivery defaults "stream-edit"; default construction is a no-op (no legacy behavior change).
- [ ] Invalid value → ValueError; non-str → TypeError; both-value round-trips load.
- [ ] Precondition matrix: all-default loads; each single violation named; two violations both named
      in one message; unviolated keys omitted; stream-edit ignores everything.
- [ ] config.toml comment documents opt-in-until-G6 + the triple (Mode A).

## Anti-Patterns to Avoid

- ❌ Don't enforce the triple inside OutputConfig.__post_init__ — it can't see asr/cancel (Critical #1).
- ❌ Don't fail on the first violation — collect and name all (Critical #2; the two-violation test pins it).
- ❌ Don't use TypeError for the value/combination errors — wrong VALUE is ValueError per precedent (Critical #3).
- ❌ Don't change any default or existing assertion — this task is purely additive (Critical #4).
- ❌ Don't land config.py without config.toml in the same changeset (lockstep test, Critical #5).
- ❌ Don't add a daemon/feedback/ctl consumer, touch bulk_controller.py, or the parallel G2-gate files (Gotcha #6).
- ❌ Don't run pytest bare — `timeout 60` + `.venv/bin/python` (Gotcha #7).

---

**Confidence Score: 9/10.** Small, fully-pinned additive change over a well-established validation
architecture: the field + two guard patterns are copied verbatim from existing precedents in the same
class; the only novel piece (the first cross-section gate in a top-level `__post_init__`) is designed
around the verified fact that graceful_stop lives in [asr]; the test conventions, exact key counts
(26→27), and validation commands were verified live. −1: minor judgment in the error-message wording
and post-init tuple plumbing (shape given; implementer renders it plainly).

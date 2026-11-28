# PRP — P1.M1.T1.S1: Reject retired `bulk-text` in supported config (actionable migration error)

## Goal

**Feature Goal**: Retire the `output.delivery = "bulk-text"` experiment at the **config boundary**: an explicit `bulk-text` must fail fast — **before any daemon arming or backend injection** — with an actionable migration error (`remove the key or set "stream-edit"`), while everything supported is preserved byte-for-byte: absent key → default `stream-edit`; `stream-edit`; default `streaming`; `wtype`/`ydotool`/`null`; and the legacy `tmux → ydotool` alias. The ordinary keyboard backend implementation (`make_backend`) stays untouched.

**Deliverable**: Three files:
1. `voice_typing/config.py` — `OutputConfig.__post_init__` rejects `delivery == "bulk-text"` with the migration message; the `VoiceTypingConfig` bulk-precondition cross-section gate becomes dead code → **remove** it (or reduce to a no-op guard that never fires); update `delivery` field comments.
2. `config.toml` — `delivery` comment rewritten: accepted values = `"stream-edit"` only (or absent); `"bulk-text"` retired → remove/set migration guidance; no labs presented as supported.
3. `tests/test_config.py` + `tests/test_typing_backends.py` — flip the bulk pins to the retirement contract; add loader/launcher-boundary tests with fake constructors/subprocesses asserting no `tmux` (and no backend) invocation on rejection; keep the tmux-alias test green.

**Success Definition**: (a) `from_toml({"output": {"delivery": "bulk-text"}})` and `OutputConfig(delivery="bulk-text")` raise `ValueError` naming `"stream-edit"` and the migration action; (b) `VoiceTypingConfig()` and the repo `config.toml` load unchanged (drift guard green, key set unchanged — `delivery` key stays); (c) `stream-edit`/absent/default/`streaming` default/backends/`tmux` alias behave identically to today; (d) `make_backend()` unchanged and never reached for a rejected config (proven by a fake-constructor boundary test); (e) only the four files change; `daemon.py`/`typing_backends.py` untouched.

## User Persona

**Target User**: (1) An operator whose `~/.config/voice-typing/config.toml` still carries `delivery = "bulk-text"` from the retired lab — they need a one-line, actionable error at load instead of a silent arm request or a crash-loop; (2) S2 (daemon bulk routing disconnect) and S4 (installer/CLI generic usage), which consume this validated boundary.

**Use Case**: `systemctl --user start voice-typing` with a stale `bulk-text` setting → the daemon logs `output.delivery="bulk-text" is retired: remove the key or set delivery = "stream-edit"` and exits non-zero (systemd shows the failure) — before any recorder spawn, arming, or backend construction.

**Pain Points Addressed**: Silent reinterpretation of a retired value as an arm request; the config drift-guard only checking values, not semantics; and the stale precondition-triple machinery that would otherwise linger as dead code.

## Why

- **PRD §4.2sexies is now "Legacy bulk text delivery experiment (Rev 4 reference, superseded)"** — the archived contract "does not apply to generic dictation or the supported editor integrations"; §4.5's `delivery` comment reads "existing keyboard-delivery default; native editor sessions do not use this selector". Today `config.py:204` still admits `"bulk-text"` and the top-level `__post_init__` (:420-451) enforces its precondition triple — admitting a retired experiment into the supported surface.
- **Fail at the supported boundary, early and actionable** (architecture/system_context.md §7: "Make rejection an early, actionable migration failure at the supported boundary; do not silently reinterpret it as an arm request"). `__post_init__` fires for BOTH construction paths (defaults + `from_toml` overlay) and runs before `main()` reaches `make_backend(cfg.output)` (daemon.py:1162) or any `_arm()` — so the config layer is the earliest, cheapest gate.
- **Preserve the ordinary path exactly**: the contract explicitly requires `absent`/`stream-edit`, default `streaming`, `wtype`/`ydotool`/`null`, and the `tmux → ydotool` alias to keep working; `make_backend()` "never needs a new backend".
- **Remove the now-dead triple gate**: once `bulk-text` can't be constructed, `VoiceTypingConfig.__post_init__`'s bulk branch is unreachable; leaving it would be misleading dead code and its 7 pins would test a lie.

## What

Config-only retirement: `OutputConfig.__post_init__` → reject `"bulk-text"` with a migration `ValueError`; drop the unreachable top-level bulk-precondition gate; rewrite the `delivery` comments in `config.py` + `config.toml`; reconcile the pins (bulk-triple tests → retirement tests; keep `stream-edit`-with-violations loading; keep the tmux alias); add a boundary test proving a rejected config never reaches `make_backend`/subprocess. No daemon/typing_backends changes.

### Success Criteria

- [ ] `OutputConfig(delivery="bulk-text")` raises `ValueError` whose message contains `"bulk-text"`, `"retired"`, and both migration actions (`remove` / `"stream-edit"`).
- [ ] `VoiceTypingConfig.__post_init__` no longer carries the bulk-precondition branch (dead code removed) — or it is provably unreachable; no test still asserts the triple.
- [ ] `stream-edit`, absent key, and the repo `config.toml` load unchanged; `tests/test_config_repo_default.py` key set untouched (`delivery` still present) and green.
- [ ] `streaming` default `True`, `backend` values `wtype|ydotool|null`, and `tmux → ydotool` alias preserved (existing tests green).
- [ ] Non-str `delivery` still raises `TypeError`; unknown strings still raise `ValueError` (existing).
- [ ] New boundary test: a rejected config raises at load and `make_backend`/any subprocess is NEVER invoked (fake constructors).
- [ ] `make_backend()` and `daemon.py` untouched; only `config.py`, `config.toml`, `test_config.py`, `test_typing_backends.py` change.

## All Needed Context

### Context Completeness Check

_Pass._ Every edit site is quoted with re-verified line numbers, every affected pin is enumerated with its current assertion, the preserved behaviors are listed with their existing tests, and the boundary to prove is identified (daemon.py:1162 → make_backend). No prior knowledge of this codebase is required.

### Verified Current State (re-verified this session)

**`voice_typing/config.py`:**
- `OutputConfig` (:140): `backend: str = "wtype"`, `append_space`, `streaming: bool = True`, `stream_chunks: str = "char"`, **`delivery: str = "stream-edit"`** (:152) with a multi-line comment still describing `"bulk-text"` as an opt-in paste-as-policy path and referencing "see VoiceTypingConfig" for the triple (:152-160).
- `OutputConfig.__post_init__` (:162-207): `tmux → ydotool` alias (:170-171: `if self.backend == "tmux": self.backend = "ydotool"`) — **PRESERVE**; backend ValueError (:173-176); streaming bool guard; `stream_chunks` guards; then the delivery block (:195-206):
  ```python
  if not isinstance(self.delivery, str):
      raise TypeError(f"[output] delivery expects str, got ...")
  if self.delivery not in ("stream-edit", "bulk-text"):
      raise ValueError(
          f'[output] delivery must be "stream-edit" or "bulk-text", got {self.delivery!r}'
      )
  ```
  ← **the edit site**: keep the TypeError; make `"bulk-text"` its own actionable rejection BEFORE the generic unknown-value check; narrow the allowed set to `("stream-edit",)`.
- `VoiceTypingConfig.__post_init__` (:420-451): the bulk-precondition triple (`if self.output.delivery != "bulk-text": return` → collect violations → ValueError). ← becomes unreachable → REMOVE.

**`voice_typing/typing_backends.py` — `make_backend(cfg)` (:208-232):** `wtype → _WtypeWithFallback()`, `ydotool → YdotoolBackend(client=YdotoolClient())`, `null → NullBackend()`, else `ValueError(f"unknown output.backend: {backend!r}")`. **READ-ONLY** — the ordinary backend implementation stays.

**The boundary to prove:** `daemon.py:1162` `backend if backend is not None else typing_backends.make_backend(cfg.output)` — reached only AFTER `VoiceTypingConfig.load()` (:4122) in `main()`. A `ValueError` from `__post_init__` therefore fires before any backend construction/arming. The test proves this with fakes at the loader/launcher boundary.

**`config.toml:51`:** `delivery    = "stream-edit"  # Normal system-wide keystroke output, including final-only block mode. "bulk-text" is a legacy lab experiment slated for retirement; not an editor integration.` ← rewrite (Mode A).

**Affected pins (current assertions):**
- `tests/test_config.py`: :58 default `stream-edit` (KEEP); :410 `test_invalid_delivery_value_raises` loops `("Bulk-Text", "stream", "bulk", "paste", "", "STREAM-EDIT")` (KEEP); :417 non-str TypeError (KEEP); **:424 `test_valid_delivery_values_load` asserts BOTH `stream-edit` AND `bulk-text` round-trip → FLIP** (bulk-text must now raise); :431 default (KEEP); **:436-478 the bulk-triple family** (`test_bulk_text_with_all_default_companions_loads`, `_requires_streaming_true`, `_requires_graceful_stop_false`, `_requires_keypress_action_disarm`, `_two_violations_named_together`) → REPLACE with retirement tests; **:483 `test_stream_edit_ignores_all_violations`** (stream-edit loads with every precondition violated) → KEEP (now trivially true, still a good "no over-rejection" pin).
- `tests/test_typing_backends.py:200-204` `test_legacy_tmux_config_uses_only_system_wide_keystrokes`: `OutputConfig(backend="tmux")` → `"ydotool"`; `make_backend(cfg).type_text(...)` → argv `("ydotool","type","--key-delay","1","--","synthetic final")` — **KEEP unchanged** (the `recorder` fixture records argvs; proves the alias + no tmux).
- `tests/test_config_repo_default.py:47`: expected output key set includes `"delivery"` — UNCHANGED (the key stays; only its comment/semantics change).
- **Downstream (NOT S1's):** `tests/test_daemon.py:5758` `_make_s2_bulk_daemon` constructs `from_toml({"output": {"delivery": "bulk-text"}})` — this will FAIL after S1. That is **expected and owned by S2** ("Disconnect daemon bulk routing and activation"), which removes the bulk arm-worker tests. S1 must NOT touch test_daemon.py; S1's gates exclude it, and the handoff note flags it.

### Documentation & References

```yaml
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: §7 maps exactly this: "OutputConfig.__post_init__ maps tmux→ydotool and currently admits
       stream-edit and bulk-text. VoiceTypingConfig.__post_init__ then applies bulk prerequisites.
       Make rejection an early, actionable migration failure at the supported boundary; do not
       silently reinterpret it as an arm request. make_backend() is the existing dispatch and never
       needs a new backend. Per-arm mode already flows from _cmd_streaming … (S2's concern)."
  critical: "Rejection must be EARLY (config) and ACTIONABLE (remove/set stream-edit). No silent
            reinterpretation. No new backend."
- docfile: plan/009_ef3b49b0fc0d/prd_snapshot.md
  why: §4.2sexies is titled "Legacy bulk text delivery experiment (Rev 4 reference, superseded)" and
       scoped out of generic dictation; §4.5's delivery line is "existing keyboard-delivery default;
       native editor sessions do not use this selector"; §4.3 lists exactly wtype|ydotool|null.
- file: voice_typing/config.py
  pattern: "VT-005 precedent — TypeError for wrong TYPE, ValueError for wrong VALUE, message names
            the section/key and the accepted values. Follow it for the retirement message; keep the
            actionable verbs ('remove the key' / 'set delivery = \"stream-edit\"')."
  gotcha: "The tmux alias runs FIRST in __post_init__ (:170) — keep it above the delivery checks so
           existing files with backend='tmux' keep loading exactly as today."
- file: voice_typing/typing_backends.py
  why: make_backend (:208) — the dispatch the boundary test must prove is never reached on rejection.
        READ-ONLY. The `recorder` fixture in test_typing_backends.py records argvs (the no-tmux proof).
- file: tests/test_config.py
  why: the delivery test block (:400-490) — flip the bulk pins; keep the TypeError/unknown/default/
        stream-edit-ignores-violations pins; add the retirement + boundary tests.
- file: tests/test_typing_backends.py
  why: :200 the tmux-alias pin (KEEP); the `recorder` fixture is the fake-subprocess pattern to reuse
        for the "no backend invocation on rejection" boundary test (or place it in test_config.py with
        a monkeypatched make_backend).
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/config.py               # OutputConfig :140 (delivery :152; __post_init__ :162-207); top-level triple gate :420-451  ← EDIT
config.toml                          # [output] :45-51; delivery :51  ← EDIT (comment)
voice_typing/typing_backends.py      # make_backend :208  ← READ-ONLY
voice_typing/daemon.py               # :1162 make_backend call (after load :4122)  ← READ-ONLY
tests/test_config.py                 # delivery block :400-490  ← EDIT
tests/test_typing_backends.py        # :200 tmux alias pin  ← EDIT (add boundary test; keep pin)
tests/test_config_repo_default.py    # :47 key set (unchanged)  ← READ-ONLY gate
tests/test_daemon.py                 # :5758 bulk helper  ← S2's (expected red after S1 — do not touch)
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/config.py          # MODIFY: reject bulk-text in OutputConfig.__post_init__; remove dead triple gate; comments
config.toml                     # MODIFY: delivery comment (accepted values + migration; no labs as supported)
tests/test_config.py            # MODIFY: flip bulk pins → retirement; add loader-boundary test (no make_backend call)
tests/test_typing_backends.py   # MODIFY: + launcher-boundary test (fake subprocess; no tmux); tmux alias pin kept
# NOTHING ELSE. typing_backends.py / daemon.py untouched; test_daemon.py is S2's.
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — REJECT IN OutputConfig.__post_init__, NOT ONLY AT THE TOP LEVEL. OutputConfig can be
# constructed directly (tests do: OutputConfig(backend="tmux")), and from_toml overlays per-section.
# The rejection must fire for the SECTION object so no path admits bulk-text. The top-level triple
# gate then becomes dead code — remove it rather than leave a branch that can never execute.

# CRITICAL #2 — ORDER INSIDE __post_init__: tmux alias FIRST (unchanged, :170), then backend/streaming/
# stream_chunks guards (unchanged), then: delivery TypeError (unchanged) → NEW retirement check for
# "bulk-text" → the generic allowed-set check narrowed to ("stream-edit",). A retirement message must
# be emitted for the exact retired token, while "Bulk-Text"/"bulk"/"paste" etc. keep hitting the
# generic 'must be "stream-edit"' ValueError (test_invalid_delivery_value_raises stays green).

# CRITICAL #3 — ACTIONABLE MESSAGE. Include: the offending value, that it is retired, and BOTH
# remedies — e.g. 'output.delivery="bulk-text" is retired: remove the key (default "stream-edit")
# or set delivery = "stream-edit"'. S2's daemon-side and S4's installer/CLI messaging reuse this.

# CRITICAL #4 — PRESERVE, DON'T REWRITE. Absent key → default; stream-edit; streaming default True;
# wtype|ydotool|null; tmux→ydotool alias (test_legacy_tmux_config_uses_only_system_wide_keystrokes
# must stay byte-identical green). make_backend() untouched. config.toml VALUE stays "stream-edit"
# (only the comment changes → drift guard + key-set test unchanged).

# CRITICAL #5 — test_daemon.py:5758 WILL GO RED (bulk helper constructs bulk-text). That is S2's
# scope ("Disconnect daemon bulk routing and activation"). S1 does NOT touch test_daemon.py and S1's
# gates EXCLUDE it. Record the handoff explicitly.

# CRITICAL #6 — BOUNDARY TEST WITH FAKES, NEVER A REAL SUBPROCESS. Prove "no backend reached" by
# monkeypatching voice_typing.typing_backends.make_backend (or the daemon's lookup) to a recorder
# that fails the test if called, and assert VoiceTypingConfig.from_toml(...) raises BEFORE it. In
# test_typing_backends.py the existing `recorder` fixture (argv recorder) is the no-tmux proof.

# GOTCHA #7 — TWO-TIMEOUT RULE (AGENTS.md) on every pytest run; .venv/bin/python -m pytest idiom.
# Do NOT run test_daemon.py as a gate (CUDA-classified in AGENTS.md; S2 owns its reconciliation).

# GOTCHA #8 — DEAD-CODE REMOVAL MUST ALSO DROP ITS DOCSTRING CLAIMS: the top-level __post_init__
# docstring describes the triple; if the method body becomes `return`/empty, delete the method
# entirely (dataclass without __post_init__ is fine) or leave a one-line no-op docstring stating the
# gate was retired with bulk-text (P1.M1.T1.S1). Either way: no unreachable bulk branch remains.
```

## Implementation Blueprint

### Data models and structure

No schema change: `OutputConfig.delivery: str = "stream-edit"` stays (key retained for existing files); only its **allowed value set** narrows to `{"stream-edit"}` and the top-level cross-section bulk gate is removed.

### Implementation Tasks (ordered)

```yaml
Task 1: EDIT voice_typing/config.py — OutputConfig.__post_init__ rejection + comments.
  - FIND the delivery block (:195-206). REPLACE the allowed-set check with:
        if self.delivery == "bulk-text":   # retired lab experiment (PRD §4.2sexies, superseded)
            raise ValueError(
                'output.delivery="bulk-text" is retired: remove the key (default "stream-edit") '
                'or set delivery = "stream-edit"'
            )
        if self.delivery != "stream-edit":
            raise ValueError(
                f'[output] delivery must be "stream-edit", got {self.delivery!r}'
            )
    (keep the isinstance TypeError above it unchanged).
  - REWRITE the `delivery` field comment (:152-160): accepted values = "stream-edit" (or absent);
    "bulk-text" is a retired lab experiment rejected at load with migration guidance; native editor
    sessions do not use this selector (PRD §4.5). Delete the "see VoiceTypingConfig" triple reference.

Task 2: EDIT voice_typing/config.py — remove the dead top-level bulk gate.
  - DELETE VoiceTypingConfig.__post_init__ (:420-451) entirely (the dataclass needs no __post_init__
    once the only cross-section rule is gone), OR replace with a no-op whose docstring says the
    bulk-text triple was retired with the value (P1.M1.T1.S1). No unreachable bulk branch may remain.
  - RUN a quick import check: .venv/bin/python -c "from voice_typing.config import VoiceTypingConfig;
    VoiceTypingConfig()" must still succeed.

Task 3: EDIT config.toml:51 — the delivery comment (Mode A):
        delivery    = "stream-edit"  # The ONLY accepted value (or omit the key): system-wide keyboard delivery of finals/partials. "bulk-text" (a retired lab experiment) is rejected at load with migration guidance — remove the key or set "stream-edit". Editor integrations do not use this selector.
  - VALUE unchanged ("stream-edit") → drift guard + key-set test untouched.

Task 4: EDIT tests/test_config.py — flip the pins to the retirement contract.
  - REPLACE test_valid_delivery_values_load (:424): stream-edit round-trips; bulk-text RAISES.
  - REPLACE the bulk-triple family (:436-478) with:
      * test_bulk_text_is_rejected_with_migration_guidance — from_toml({"output":{"delivery":"bulk-text"}})
        raises ValueError matching "bulk-text", "retired", "stream-edit" (and "remove").
      * test_bulk_text_rejected_as_direct_output_config — OutputConfig(delivery="bulk-text") raises
        (the section-level path, Critical #1).
      * test_bulk_text_rejected_even_with_former_valid_companions — the old "all defaults" input now
        raises (the triple is moot).
      * test_loader_boundary_never_builds_a_backend_for_retired_delivery — monkeypatch
        voice_typing.typing_backends.make_backend to a recorder that raises if called; assert
        from_toml(... bulk-text ...) raises ValueError first; recorder not called. (Fake
        constructors only; no subprocess.)
  - KEEP: :58, :410, :417, :431, and :483 test_stream_edit_ignores_all_violations (now the
    "no over-rejection" pin — it must still load).

Task 5: EDIT tests/test_typing_backends.py — launcher-boundary proof + keep the alias pin.
  - KEEP :200-204 unchanged.
  - ADD test_retired_delivery_never_reaches_backend_subprocess: build cfg via
    VoiceTypingConfig.from_toml({"output":{"delivery":"bulk-text"}}) inside pytest.raises(ValueError);
    with the `recorder` fixture active assert recorder.argvs == [] afterwards (no ydotool/tmux call).
    (If the fixture is function-scoped per test, structure as: request recorder → assert raise →
    assert recorder.argvs == [].)

Task 6: VERIFY (gates below). No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S1: retire output.delivery=bulk-text at the config boundary (actionable migration error)".
  HANDOFF NOTE for S2: tests/test_daemon.py:5758 _make_s2_bulk_daemon now fails at from_toml —
  S2 removes the bulk arm-worker tests with the daemon routing.
```

### Implementation Patterns & Key Details

```python
# The whole change is one allowed-set narrowing + one dead branch removal + comment/test reconciliation.
# Invariants:
#  (1) EARLIEST gate: OutputConfig.__post_init__ fires on direct construction AND inside from_toml's
#      section_cls(**section) — before VoiceTypingConfig exists, before main() reaches
#      make_backend (daemon.py:1162), before any _arm(). Nothing downstream can observe bulk-text.
#  (2) TWO distinct ValueErrors for two distinct user mistakes:
#        exact "bulk-text"  -> retirement + migration guidance (remove / set "stream-edit")
#        anything else      -> 'must be "stream-edit"' (typo class; existing pin :410 stays green)
#  (3) Everything else byte-identical: tmux alias first; backend/streaming/stream_chunks guards
#      untouched; default + repo config.toml load identically (drift guard green).
# Boundary proof is by FAKES: a make_backend recorder that would fail the test if invoked is never
# invoked because the ValueError precedes it; the argv recorder shows [] (no subprocess).
```

### Integration Points

```yaml
LOADER / LAUNCHER BOUNDARY:
  - VoiceTypingConfig.load() (daemon.py:4122, main()) → OutputConfig.__post_init__ raises → the
    daemon exits before make_backend (daemon.py:1162) / arming. systemd surfaces the failure with
    the actionable message in the journal (no Restart loop ambiguity beyond the existing policy).
DOWNSTREAM CONSUMERS (NOT S1):
  - P1.M1.T1.S2 (daemon bulk routing disconnect): removes bulk_target_factory routing + the
    test_daemon.py bulk helpers/tests that S1's rejection now makes unconstructible.
  - P1.M1.T1.S4 (installer + CLI generic usage): reuses the migration wording for any usage text.
PRESERVED SURFACES: make_backend() (typing_backends.py:208) unchanged; config.toml VALUE unchanged;
  tests/test_config_repo_default.py key set unchanged (delivery key retained).
```

## Validation Loop

> AGENTS.md two-timeout rule: inner `timeout 300` + bash-tool timeout above it. `.venv/bin/python -m pytest`. Do NOT run test_daemon.py / CUDA suites / the daemon.

### Level 1: The rejection + preservation landed (static + one-off)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing.config import OutputConfig, VoiceTypingConfig
import pytest_shim if False else None
def expect(exc, fn):
    try: fn()
    except exc as e: return str(e)
    raise SystemExit(f"expected {exc.__name__}")
msg = expect(ValueError, lambda: OutputConfig(delivery="bulk-text"))
assert "bulk-text" in msg and "retired" in msg and "stream-edit" in msg and "remove" in msg, msg
expect(ValueError, lambda: VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text"}}))
expect(TypeError, lambda: OutputConfig(delivery=True))
expect(ValueError, lambda: OutputConfig(delivery="Bulk-Text"))
# preserved:
assert VoiceTypingConfig().output.delivery == "stream-edit"
assert OutputConfig(backend="tmux").backend == "ydotool"
assert VoiceTypingConfig.from_toml({"output": {"delivery": "stream-edit"}}).output.delivery == "stream-edit"
print("L1 PASS: rejection actionable; preserved paths intact")
PY
grep -c "bulk-text" voice_typing/config.py | xargs -I{} sh -c 'test {} -ge 1 && echo "L1b: bulk-text still referenced (expected: the retirement message/comment)"'
# and confirm the dead triple gate is gone:
! grep -q 'requires .*output.streaming' voice_typing/config.py && echo "L1c PASS: triple gate removed"
```

### Level 2: The owned suites are green (the S1 gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_config.py tests/test_typing_backends.py tests/test_config_repo_default.py -q 2>&1 | tail -4
# Expected: all passed (drift guard + key set green → config.toml value untouched; alias pin green).
```

### Level 3: Boundary proof — no backend/subprocess on rejection (run the new pins explicitly)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_config.py tests/test_typing_backends.py -q -k "retired or boundary or tmux" 2>&1 | tail -4
# Expected: all passed — incl. test_legacy_tmux_config_uses_only_system_wide_keystrokes (unchanged)
# and the two new boundary pins (make_backend recorder never called; argv recorder empty).
```

### Level 4: Scope

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only
git diff --name-only | grep -vE 'voice_typing/config\.py|config\.toml|tests/test_config\.py|tests/test_typing_backends\.py' | grep -E '\.py$|\.toml$|\.md$|\.sh$' && echo "L4 FAIL: out of scope" || echo "L4 PASS: only the 4 files"
git diff voice_typing/typing_backends.py voice_typing/daemon.py | grep -q . && echo "L4 FAIL: backend/daemon touched" || echo "L4 PASS: typing_backends.py + daemon.py untouched"
grep -c '^delivery' config.toml | grep -q '^1$' && grep '^delivery' config.toml | grep -q '"stream-edit"' && echo "L4 PASS: config.toml delivery value unchanged"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `bulk-text` rejected with an actionable message (value, "retired", both remedies); TypeError/typo paths intact; defaults/tmux/stream-edit preserved; triple gate gone.
- [ ] L2: `test_config.py` + `test_typing_backends.py` + `test_config_repo_default.py` green.
- [ ] L3: the two new boundary pins + the unchanged tmux alias pin green.
- [ ] L4: only the four files changed; `typing_backends.py`/`daemon.py` untouched; `config.toml` value unchanged.

### Feature Validation
- [ ] Rejection fires at config load — before daemon arming/injection (loader-boundary pin).
- [ ] Absent / `stream-edit` / default `streaming` / `wtype|ydotool|null` / `tmux → ydotool` unchanged.
- [ ] Ordinary backend implementation untouched; no tmux invocation possible (argv recorder empty).
- [ ] `config.toml` + `config.py` comments describe accepted values + migration without presenting labs as supported.

### Code Quality Validation
- [ ] Two distinct ValueErrors (retired token vs typo) following the VT-005 precedent.
- [ ] Dead top-level gate removed (no unreachable bulk branch; docstring claims gone with it).
- [ ] Boundary tests use fakes only (no real subprocess/daemon).

### Scope Boundary Validation
- [ ] `tests/test_daemon.py` untouched (its :5758 bulk helper is S2's expected red).
- [ ] No `typing_backends.py`/`daemon.py`/installer/CLI changes (S2/S4).
- [ ] `tests/test_config_repo_default.py` key set untouched.

---

## Anti-Patterns to Avoid

- ❌ Don't only narrow the top-level gate — reject in `OutputConfig.__post_init__` so direct section construction can't admit `bulk-text` either.
- ❌ Don't silently map `bulk-text` → `stream-edit` (reinterpretation) — the contract demands an explicit, actionable failure; and don't "arm" anything on its behalf.
- ❌ Don't let the generic typo check swallow the retired token — `bulk-text` needs its own migration message; `"Bulk-Text"`/`"bulk"` keep the generic `'must be "stream-edit"'` error.
- ❌ Don't leave the unreachable triple branch or its docstring in `VoiceTypingConfig` — dead code that still "documents" a retired contract is a trap.
- ❌ Don't change the `config.toml` VALUE or remove the `delivery` key — the drift guard and key-set pin must stay green; only the comment changes.
- ❌ Don't break `test_legacy_tmux_config_uses_only_system_wide_keystrokes` or the `stream-edit`-with-violations pin — they are the preservation proof.
- ❌ Don't touch `typing_backends.py`/`make_backend()` or `daemon.py` — "never needs a new backend"; routing removal is S2.
- ❌ Don't fix `tests/test_daemon.py:5758` here — it is S2's expected fallout; touching it crosses scope and S1's gates exclude it.
- ❌ Don't prove "no subprocess" with a real backend — fake constructors/argv recorders only.
- ❌ Don't run unwrapped pytest, `test_daemon.py`, or the live daemon (AGENTS.md).

---

## Confidence Score

**9.5/10** for one-pass success. The edit sites (the delivery block :195-206, the dead triple gate :420-451, the config.toml comment :51), every affected pin with its current assertion (:424, :436-478 to flip; :58/:410/:417/:431/:483 and the tmux alias :200 to keep), the preserved behaviors with their tests, and the exact downstream boundary (daemon.py:1162 after load :4122) are all verified against the live tree, and the architecture note prescribes precisely this early/actionable rejection. The −0.5 is the deliberate, documented fallout (`test_daemon.py:5758` goes red → S2) plus standard tree-drift risk on the cited line numbers.

# PRP — P1.M2.T1.S1: AudioConfig dataclass + config.toml `[audio]` table + key-set pin 24→26

## Goal

**Feature Goal**: Land the `[audio]` config surface for media ducking (PRD §4.2quinquies, D1's first subtask): an `AudioConfig` dataclass (`duck_mode: str = "off"`, `duck_volume_pct: int = 15`) with fail-fast `__post_init__` guards, wired into `VoiceTypingConfig` / `_KNOWN_TABLES` / `from_toml`, mirrored as a commented `[audio]` table in `config.toml`, with the repo-default key-set pin extended **24 → 26** and new type/value guard tests. **Ships `duck_mode="off"`** — the feature itself (AudioDucker, daemon wiring) is later D1 subtasks; the default flips to `"mpris"` in P1.M2.T4.

**Deliverable** (4 files, TDD):
1. `tests/test_config_repo_default.py` — pin test extended FIRST (RED): `"audio": {"duck_mode", "duck_volume_pct"}` + docstring "24"→"26".
2. `tests/test_config.py` — a 5-test `[audio]` guard section (RED): unknown enum value, all-3-enum acceptance, bool/int/str/float/None/list rejection, defaults `("off", 15)`.
3. `voice_typing/config.py` — `AudioConfig` dataclass after `CancelConfig` + field + `_KNOWN_TABLES` + `from_toml` overlay (GREEN).
4. `config.toml` — `[audio]` table after `[cancel]`, both keys inline-commented (Mode A — this IS the user-facing reference).

**Success Definition**:
- (a) `VoiceTypingConfig().audio.duck_mode == "off"` and `.duck_volume_pct == 15`.
- (b) `from_toml({"audio": {"duck_mode": "mpris"}})` works; `{"audio": {"duck_mode": "loud"}}` raises `TypeError` naming `duck_mode`; `{"audio": {"duck_volume_pct": True}}` (and `"15"`/`15.0`/`None`/`[15]`) raise `TypeError` naming `duck_volume_pct`.
- (c) Repo `config.toml` parses to NO overrides over the defaults (`test_repo_config_toml_equals_defaults` green) and carries exactly the 26 schema keys.
- (d) `timeout 300 .venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q` → 0 failures.
- (e) Only the 4 files changed; the rest of the fast suite stays green.

## User Persona

Not applicable as an end-user surface yet (`duck_mode="off"` = byte-identical behavior today). DOCS: Mode A — the `config.toml [audio]` comments are the user-facing reference and ride with this task.

## Why

- **D1's foundation.** §4.2quinquies pins the two-key `[audio]` surface ("add to config.py + config.toml in lockstep with the key-set test, 24 → 26 keys") and mandates `duck_mode = "off"` shipping until the ducker lands. Every later D1 subtask (AudioDucker, daemon wiring, ExecStopPost, default flip) consumes `cfg.audio.*` — this task creates that surface with the repo's fail-fast discipline from day one.
- **Lockstep discipline is the repo's proven pattern.** The key-set pin + defaults-equality drift guard are how every prior section (`[cancel]`, `graceful_stop`, `context_prompt`) landed without code↔config drift; a typo'd value must fail at LOAD (the guard tests), not at arm time under systemd.

## What

A new `[audio]` config section (2 keys), fully guarded and pinned. No behavior change (`"off"`).

### Success Criteria

- [ ] `AudioConfig` dataclass after `CancelConfig` with the two fields + `__post_init__` guards (enum + non-bool-int).
- [ ] `audio` field on `VoiceTypingConfig`; `"audio"` in `_KNOWN_TABLES`; `audio=_overlay(AudioConfig, "audio")` in `from_toml` (+ its docstring table list).
- [ ] `config.toml` gains the commented `[audio]` table after `[cancel]`; both files agree exactly (defaults test green).
- [ ] Pin test: 26 keys, docstring updated; the 5 new guard tests pass; both suites 0 failures; only 4 files changed.

## All Needed Context

### Context Completeness Check

_Pass._ The exact 5 code points + 2 test sites (with HEAD line numbers), the verbatim guard patterns from the real code, the verified 24-key pin, the TDD RED rationale, and the seams-doc checklist boundary (items #4-#8 are LATER subtasks) are all below + in the research note.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/P1M2T1S1/research/audio_config_surface.md
  why: "§1 the 5-point recipe table. §2 the verbatim guard patterns (NOTE: the seams doc's ValueError sketch is
        superseded — the real keypress_action guard raises TypeError; mirror the REAL code). §3 the pin (verified 24).
        §4 the guard tests. §5 TDD order + why RED pre-implementation. §6 scope."
- docfile: plan/008_a47116bb2b79/architecture/d1_ducking_seams.md
  why: "§3 the authoritative recipe this task implements (checklist items 1-3); §5-§6 confirm the AudioDucker/daemon/
        systemd work is LATER subtasks (do not start them)."
- file: voice_typing/config.py
  why: "CancelConfig __post_init__ ends ~:213 (the on_backspace bool guard ~:195-199 + keypress_action enum guard
        :201-206 are the verbatim templates); insert AudioConfig before @dataclass FeedbackConfig (~:216).
        _KNOWN_TABLES frozenset :337; VoiceTypingConfig fields :341-346; from_toml cls(...) overlay :385-391
        (+ docstring table list)."
  critical: "The enum guard mirrors keypress_action: TypeError, f\"[audio] duck_mode expects 'off', 'mpris', or
             'volume', got {self.duck_mode!r}\". The int guard mirrors on_backspace's message shape (reject bool +
             require int). Without \"audio\" in _KNOWN_TABLES, [audio] raises 'unknown config table(s)'."
- file: tests/test_config_repo_default.py
  why: "test_repo_config_toml_has_no_extra_keys :37-63 (docstring 'only the 24 schema keys' at :38; expected dict:
        asr 11 / output 3 / cancel 3 / feedback 4 / filter 2 / log 1 = 24 verified). Add the audio entry after
        'cancel' + 24→26. test_repo_config_toml_equals_defaults :16-26 pins ('off', 15) automatically."
- file: tests/test_config.py
  why: "The wrong-typed guard region :143-201 (test_string_for_float_field_raises :148, _REV2_BOOL_FIELDS loops :184+)
        — place the new [audio] section beside it, mirroring the pytest.raises(match=...) style."
- file: config.toml
  why: "[cancel] table ends ~:60, then blank line + [feedback] — insert [audio] between. Inline-comment style: every
        key commented (see the [output] block). Header (:15-19) already promises unknown-key AND unknown-table
        rejection + lockstep."
- file: PRD.md  # §4.2quinquies Config block: duck_mode ("mpris"|"volume"|"off", ships "off") + duck_volume_pct=15
- docfile: plan/008_a47116bb2b79/P1M1T4S2/PRP.md  # parallel: tests/test_daemon.py ONLY (latch regression) — NO overlap
```

### Known Gotchas

```python
# CRITICAL #1 — TypeError, NOT ValueError, for the duck_mode enum guard (mirror the real keypress_action code at
#   config.py:201-206; the seams doc's sketch says ValueError — the actual repo convention is TypeError, and the
#   guard tests assert match="duck_mode" inside pytest.raises(TypeError)).
# CRITICAL #2 — duck_volume_pct must REJECT bool first (isinstance(True, int) is True — the notify_ms/on_backspace
#   asymmetry), then require isinstance int; "15"/15.0/None/[15] all raise.
# CRITICAL #3 — "audio" MUST join _KNOWN_TABLES or every config.toml carrying [audio] (including the repo default
#   this task writes) fails to load with "unknown config table(s)".
# CRITICAL #4 — TDD: the pin + guard tests are RED before implementation (config.toml lacks [audio]; from_toml
#   rejects the table). Run them RED first; then implement; then GREEN.
# GOTCHA #5 — Ships duck_mode="off"; do NOT flip to "mpris" (that's P1.M2.T4, evidence-gated) and do NOT start the
#   AudioDucker/daemon/feedback/ExecStopPost work (seams checklist #4-#8 = later subtasks).
# GOTCHA #6 — Full paths + functional `timeout` on every command (AGENTS.md); pytest>=9.1.1, NO ruff/mypy.
```

## Implementation Blueprint

### Implementation Tasks

```yaml
Task 1: EDIT tests/test_config_repo_default.py — the pin, FIRST (RED)
  - EDIT 1a: docstring :38 `only the 24 schema keys` → `only the 26 schema keys`.
  - EDIT 1b: in the `expected` dict, after the `"cancel": {...},` line, add:
        "audio": {"duck_mode", "duck_volume_pct"},   # §4.2quinquies media ducking (D1; ships "off")
  - RUN (RED): `timeout 300 .venv/bin/python -m pytest tests/test_config_repo_default.py -q -k extra_keys`
    → FAILS (config.toml has no [audio] table).

Task 2: ADD the [audio] guard tests to tests/test_config.py (RED) — place after the wrong-typed region (~:201):
        # ---------------------------------------------------------------------------
        # [audio] media-ducking keys (PRD §4.2quinquies / D1): duck_mode + duck_volume_pct.
        # duck_mode is a closed enum (the CancelConfig.keypress_action guard style);
        # duck_volume_pct is a genuine int (bool rejected — the notify_ms guard style).
        # ---------------------------------------------------------------------------

        def test_duck_mode_rejects_unknown_value():
            with pytest.raises(TypeError, match="duck_mode"):
                VoiceTypingConfig.from_toml({"audio": {"duck_mode": "loud"}})

        def test_duck_mode_accepts_all_three_values():
            for v in ("off", "mpris", "volume"):
                assert VoiceTypingConfig.from_toml({"audio": {"duck_mode": v}}).audio.duck_mode == v

        def test_duck_volume_pct_rejects_bool():
            with pytest.raises(TypeError, match="duck_volume_pct"):
                VoiceTypingConfig.from_toml({"audio": {"duck_volume_pct": True}})

        def test_duck_volume_pct_rejects_non_int():
            for bad in ("15", 15.0, None, [15]):
                with pytest.raises(TypeError, match="duck_volume_pct"):
                    VoiceTypingConfig.from_toml({"audio": {"duck_volume_pct": bad}})

        def test_audio_defaults_ship_off():
            a = VoiceTypingConfig().audio
            assert a.duck_mode == "off" and a.duck_volume_pct == 15
  - RUN (RED): `timeout 300 .venv/bin/python -m pytest tests/test_config.py -q -k duck` → the 5 FAIL
    ("unknown config table(s): [audio]" / AttributeError .audio).

Task 3: EDIT voice_typing/config.py — AudioConfig + wiring (GREEN).
  - 3a: INSERT after CancelConfig's __post_init__ (before `@dataclass class FeedbackConfig`):
        @dataclass
        class AudioConfig:
            """[audio] — media ducking while listening (PRD §4.2quinquies).

            Ships duck_mode="off": the [audio] SURFACE lands before the AudioDucker (later D1
            subtasks); the default flips to "mpris" the round the ducker lands (P1.M2.T4).
            "off" is byte-identical to pre-D1 behavior (no audio subprocess is ever spawned).
            """

            duck_mode: str = "off"        # "mpris" (pause players at arm) | "volume" (duck sink) | "off"
            duck_volume_pct: int = 15     # target sink volume % for the "volume" tier (wpctl)

            def __post_init__(self) -> None:
                """Validate at construction = load time (mirrors CancelConfig's guards)."""
                if self.duck_mode not in ("off", "mpris", "volume"):
                    raise TypeError(
                        f"[audio] duck_mode expects 'off', 'mpris', or 'volume', got "
                        f"{self.duck_mode!r}"
                    )
                if isinstance(self.duck_volume_pct, bool) or not isinstance(self.duck_volume_pct, int):
                    raise TypeError(
                        f"[audio] duck_volume_pct expects int, got "
                        f"{type(self.duck_volume_pct).__name__}: {self.duck_volume_pct!r}"
                    )
  - 3b: `VoiceTypingConfig` field (after `cancel:`): `audio: AudioConfig = field(default_factory=AudioConfig)`.
  - 3c: `_KNOWN_TABLES` → `frozenset({"asr", "output", "cancel", "audio", "feedback", "filter", "log"})`.
  - 3d: `from_toml` cls(...) — after `cancel=_overlay(CancelConfig, "cancel"),` add
        `audio=_overlay(AudioConfig, "audio"),`; and the from_toml docstring's table list gains `[audio]`.
  - DO NOT: start the AudioDucker/feedback `ducked`/daemon/ExecStopPost work (later subtasks); add a range
    check to duck_volume_pct (type-only per contract); use ValueError.

Task 4: EDIT config.toml — the [audio] table (Mode A) between [cancel] and [feedback]:
        [audio]   # media ducking while listening (PRD §4.2quinquies): get media out of the way for exactly as long as the mic is hot
        duck_mode        = "off"   # "mpris" = pause MPRIS players at arm, resume at stop (only what WE paused, only if still paused — user sovereignty); "volume" = duck the default sink's volume at arm, restore at stop (only if the user didn't touch volume mid-dictation); "off" = do nothing. Ships "off" until the feature lands; the default becomes "mpris" then.
        duck_volume_pct  = 15      # target sink volume % for the "volume" tier (wpctl). Restore is compare-before-restore — a manual mid-dictation volume change always wins.

Task 5: VALIDATE.
  - `timeout 300 .venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q` → 0 failures.
  - `timeout 150 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failures (nothing else reads [audio] yet; "off" = no behavior change).
  - `git status --short` → ONLY the 4 files. Message if committed:
    "P1.M2.T1.S1: [audio] config surface (duck_mode/duck_volume_pct, ships off) + key-set pin 24→26".
```

### Integration Points

```yaml
DOWNSTREAM — the D1 chain consumes cfg.audio.*: P1.M2.T2 (AudioDucker reads duck_mode/duck_volume_pct),
  P1.M2.T3 (daemon wiring; ducker=None ctor seam default "built from cfg.audio when != off"), P1.M2.T4
  (flips the default to "mpris" + updates BOTH config.py and config.toml in lockstep — the pin enforces it).
UNCHANGED: all other sections; from_toml's unknown-key/unknown-table rejection; daemon/streaming (no [audio]
  consumer yet — "off" is inert). Parallel P1.M1.T4.S2 edits ONLY tests/test_daemon.py.
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# RED first (Tasks 1-2, before Task 3): both new/extended tests FAIL.
timeout 300 .venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q   # GREEN after
timeout 150 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q                 # 0 failures
git status --short   # ONLY config.py, config.toml, test_config_repo_default.py, test_config.py
```

## Final Validation Checklist

- [ ] Pin = 26 keys (docstring updated); defaults test green (toml ↔ dataclass exact: "off"/15).
- [ ] Guards: unknown enum raises TypeError(match="duck_mode"); bool/str/float/None/list raise for duck_volume_pct.
- [ ] "audio" in _KNOWN_TABLES; `from_toml({"audio": {...}})` overlays correctly; ships "off".
- [ ] Both config suites + full fast sweep green; only the 4 files changed; no D1-subsequent work started.

## Anti-Patterns to Avoid

- ❌ Don't use ValueError (the seams doc's sketch) — the real keypress_action guard raises TypeError; mirror the code.
- ❌ Don't forget the bool-first check on duck_volume_pct (`isinstance(True, int)` is True).
- ❌ Don't skip `_KNOWN_TABLES` — the repo default config.toml itself would then fail to load.
- ❌ Don't flip the default to "mpris" or start the AudioDucker/daemon/feedback/ExecStopPost work (later subtasks).
- ❌ Don't add a range guard or config keys beyond the two (contract is 2 keys, type-guards only).
- ❌ No pytest without `timeout`; no bare python/pytest (zsh aliases); no ruff/mypy.

---

## Confidence Score

**10/10** — the authoritative seams recipe (§3, HEAD-verified), the verbatim guard templates from the real code, the verified 24-key pin, the exact 4-file TDD sequence with RED rationale, and the explicit boundary against later D1 subtasks are all pinned; the change is additive and inert (`"off"`).

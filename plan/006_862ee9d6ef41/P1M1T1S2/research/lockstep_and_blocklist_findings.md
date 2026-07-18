# Research Note: config.toml ↔ config.py lockstep + blocklist correctness (P1.M1.T1.S2)

**Status:** EMPIRICALLY RE-VERIFIED against the live repo (`config.toml`, `voice_typing/config.py`, `tests/test_config_repo_default.py`, `tests/test_config.py`, `hypr-binds.conf`) on July 18 2026.
**Purpose:** Establish ground truth for the lockstep (drift) verification, the blocklist correctness, and the Mode A comment accuracy — the three concerns distinct from S1's PRD-§4.5 field-compliance audit.

---

## §1. S2's scope is DISTINCT from S1 (do not duplicate)

| Subtask | Question it answers | Proof |
|---|---|---|
| **S1 (P1.M1.T1.S1)** | Does `config.py` match **PRD §4.5**? (field/default PRD-compliance) | the `gap_config.md` compliance table (PRD / config.py / config.toml columns) |
| **S2 (this)** | Does `config.toml` mirror `config.py` **exactly** (drift/lockstep)? + is the blocklist correct in BOTH? + are config.toml's comments accurate (Mode A doc)? | the **drift-guard test** (`test_config_repo_default.py`) + direct tomllib comparison + Mode A comment scan |

S1's report already has a config.toml COLUMN, but S2 runs the **dedicated drift-guard test** + the **focused blocklist check** + the **Mode A comment-accuracy scan** — three things S1 only touches incidentally. S2 **appends** its findings to S1's `gap_config.md`; it does NOT re-derive S1's field table.

## §2. LIVE lockstep verification — ALL GREEN (re-verified today)

**Drift-guard test:** `.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q` → **37 passed**.

`test_config_repo_default.py` (73 lines) contains THREE lockstep tests:
1. `test_repo_config_toml_equals_defaults` — `VoiceTypingConfig.from_toml_file(_repo_config_path()) == VoiceTypingConfig()` (the actual config.toml↔config.py equality assertion; this is THE lockstep proof).
2. `test_repo_config_toml_has_no_extra_keys` — tomllib parse → exact 20-key set (asr:10, output:3, feedback:4, filter:2, log:1). Catches a stray/renamed key.
3. `test_repo_config_lite_model_comment_names_correct_keybind` — asserts the RAW config.toml text's `lite_model` line contains `SUPER+ALT+D` and NOT `SUPER+ALT+F` (tomllib drops comments, so this scans raw text). Source of truth: `hypr-binds.conf:52` `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite`.

**Direct comparison (independent of the test):**
- `VoiceTypingConfig.from_toml_file(repo) == VoiceTypingConfig()` → **True** (no drift).
- config.py has **20 scalar fields** total (`dataclasses.fields` across AsrConfig..LogConfig`) == config.toml's **20 keys**. Match.

→ **No drift exists. No fix is warranted.** (The "fix any drift" branch of the contract is NOT taken — same expected-outcome shape as S1.)

## §3. Blocklist correctness — VERIFIED in BOTH files

| Source | blocklist value |
|---|---|
| config.py `FilterConfig.blocklist` default_factory (config.py:192-200) | `['thank you.', 'thanks for watching.', 'bye.', 'thank you for watching']` |
| config.toml `[filter].blocklist` (config.toml:60-66) | `['thank you.', 'thanks for watching.', 'bye.', 'thank you for watching']` |
| `tests/test_config.py:_PRD_BLOCKLIST` (the authoritative pin, :24) | same 4-entry list |

- **Lockstep:** config.py == config.toml == the test pin. ✓
- **Contract-required 4 entries present:** `thank you.`, `thanks for watching.`, `bye.`, `thank you for watching` — all 4 ✓.
- **VT-006 respected:** bare `'you'` is NOT in either file ✓. (PRD §4.5's literal 5-entry list includes `'you'`; the implementation deliberately omits it.)
- **VT-006 documented in 3 places:** config.py:201-208 (`NOTE (VT-006)`), config.toml:67 (`# NOTE (VT-006): the bare "you" entry was removed …`), tests/test_config.py:24 (the `_PRD_BLOCKLIST` comment). Pinned by `tests/test_config.py:64` (`assert cfg.filter.blocklist == _PRD_BLOCKLIST`).
- **DO NOT re-add `'you'`** — it breaks test_config.py:64, contradicts VT-006, and re-introduces the silent-drop-of-"you" UX bug.

## §4. Mode A comment accuracy — config.toml "reads as documentation"

config.toml (76 lines) is the user-facing config reference (Mode A). Verified:
- **Every key is commented** (20 keys, 20 trailing `#` comments — the file is self-documenting per §4.5).
- **No stale keybind references:** `grep -nE 'SUPER\+ALT\+F|super alt, f' config.toml` → none. The `lite_model` comment correctly cites `SUPER+ALT+D` (matches hypr-binds.conf:52).
- **No removed-field references:** `grep -nE 'compute_type' config.toml` → none (compute_type is a cuda_check concern, correctly absent from the config schema).
- The only `config.toml` self-references are in the search-order header (lines 13-14), which are correct (XDG → repo → defaults).
- Comments accurately describe each field per §4.5 (device auto-fallback to cpu, append_space semantics, state_file XDG_RUNTIME_DIR resolution, idle-stop vs idle-unload distinction, etc.) — spot-checked against the §4.5 prose; no inaccuracies found.

## §5. The deliverable shape — APPEND to S1's gap_config.md

S1 creates `plan/006_862ee9d6ef41/architecture/gap_config.md` (the field/default compliance report). S2's contract says "Updated gap_config.md with lockstep verification result." So S2:
- **APPENDS** a clearly-delineated section (e.g. `## Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)`) to the existing gap_config.md — does NOT overwrite or duplicate S1's field-compliance table.
- The section records: the drift-guard test result (3 tests / 37 total), the direct comparison result (no drift), the blocklist correctness (4 entries, VT-006, both files agree), the Mode A comment-accuracy scan (20 keys commented, SUPER+ALT+D correct, no stale refs), and the conclusion (no drift → no fix).
- If gap_config.md does NOT yet exist (S1 still in flight): create a minimal file with the S2 section + a `<!-- P1.M1.T1.S1 field-compliance section: pending -->` placeholder. Do NOT fabricate S1's findings.

## SUMMARY (what S2 can rely on)

1. ✅ **No drift.** config.toml == config.py defaults (direct comparison + 37 tests pass). The "fix any drift" branch is NOT taken.
2. ✅ **Blocklist correct** in BOTH files: 4 entries, includes all contract-required entries, no `'you'` (VT-006), documented in 3 places, test-pinned.
3. ✅ **Mode A comments accurate:** 20 keys all commented; SUPER+ALT+D (matches hypr-binds.conf:52); no SUPER+ALT+F / compute_type stale refs.
4. ✅ **20-key set matches:** config.py 20 scalar fields == config.toml 20 keys (test_repo_config_toml_has_no_extra_keys pins the exact set).
5. ✅ **Deliverable = APPEND** a lockstep section to S1's gap_config.md (don't duplicate S1's table; don't fabricate if S1 hasn't landed).
6. ⚠️ **VT-006 trap** (shared with S1): do NOT re-add `'you'` to the blocklist — it's an intentional, documented, test-pinned deviation.
7. ✅ S2 ≠ S1: S1 = PRD §4.5 compliance; S2 = drift/lockstep + blocklist correctness + Mode A doc accuracy.
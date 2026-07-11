# Delta PRD: idle auto-stop + optional final popup + status-line sync

**Base PRD:** `PRD.md` (Fully-Local Voice Typing for Linux Terminal). This delta captures the changes between the previous and current PRD only.

**Delta size:** small — ~12 substantive lines changed, confined to PRD §4.5 (config) and §4.6 (feedback). No architecture, engine, test-plan, or acceptance-criteria changes.

---

## 1. What changed (diff summary)

Three functional requirements were added/tightened in the PRD. **All three are already implemented, committed, and tested in the prior session** (git: `367b774 add idle auto-stop for forgotten hot-mics`, `3913106 make final popup optional, fix status line drift`). This delta is therefore primarily a **spec-sync verification** with one residual doc fix.

| # | Change (PRD §) | What it requires | Status in code |
|---|---|---|---|
| D1 | **Idle auto-stop** (§4.5 new key `asr.auto_stop_idle_seconds=30.0`, new "Idle auto-stop" paragraph, §4.6 "■ stopped" label). While listening, if no realtime partial arrives for N seconds, the daemon auto-disarms via the same path as a manual `stop` — fires the `■ stopped` popup + a journal `INFO` line. A background `_idle_watchdog` thread ticks ~1 s and re-checks the deadline under the listen lock so a late partial cancels the stop. `0` disables. Partials reset the clock. | config field + daemon watchdog + feedback (reuse stop path) | ✅ `config.py:AsrConfig.auto_stop_idle_seconds`, `daemon.py:_idle_watchdog/_maybe_auto_stop`, `config.toml`, `README.md`. Tested by `tests/test_daemon.py` (6 tests). |
| D2 | **`feedback.notify_on_final`** (§4.5 new key, default `true`; §4.6 "✔ <text> — gated by `notify_on_final`"). New config knob gating the per-final popup. `hypr_notify` re-commented as the master on/off switch. | config field + feedback gate | ✅ `config.py:FeedbackConfig.notify_on_final`, `feedback.py:record_final`, `config.toml`, `README.md`. Tested by `tests/test_feedback.py`. |
| D3 | **`record_final` writes finalized text into `partial`** (§4.6). So the tmux status line matches what was typed instead of lingering on a stale trailing realtime partial. | feedback behavior | ✅ `feedback.py:record_final`, tested by `tests/test_feedback.py::test_record_final_updates_partial_so_status_matches_screen`. |

**Incidental PRD-only cleanup (no code action):** §4.2 dropped `{"cmd":"status"}` from the start/stop response-line bullet. The control socket still supports `status`; this is a cosmetic PRD wording fix and the implementation is already correct.

### 1.1 Relationship to the core "never auto-stops on silence" requirement (PRD §1)

D1 is a **deliberate, narrow relaxation** of "the session ends only on explicit stop/toggle." It is NOT a VAD/silence-based cut — it keys off *no recognized speech (realtime partial)*, defaults to 30 s (not a pause), is explicitly framed as a forgotten-hot-mic guard, and is fully disableable (`0`). `post_speech_silence_duration` still owns mid-thought segmentation. The updated PRD §4.5 paragraph documents this distinction explicitly; no re-litigation needed.

---

## 2. Residual work — the only actionable gap

A single stale comment survived the implementation. **`config.toml:49`** still describes `hypr_notify` as:

```
hypr_notify = true      # show a hyprctl notify one-liner for start/partial/final/stop. ...
```

The word **"partial"** is wrong per the updated PRD §4.5 ("master switch for hyprctl popups (start/final/stop)") and §4.6 (partials go to the state file ONLY — they NEVER fire hyprctl, the core anti-spam discipline). `README.md` already states this correctly ("`hypr_notify` is the master on/off switch"); only `config.toml` lags. This is a one-word deletion (`partial/`) in a comment — no runtime behavior change.

No other stale wording exists (verified: `grep -rn "start/partial/final\|partial/final/stop\|notify one-liner for partials"` returns only the above line).

---

## 3. Scope of this delta session

### 3.1 Verification (reference, do not re-implement)

Confirm the already-shipped code matches the updated PRD. All of the following exist and are green; the implementing agent should run them as a regression check, not re-author them:

- `tests/test_config.py` — asserts `asr.auto_stop_idle_seconds == 30.0` and `feedback.notify_on_final is True` (defaults).
- `tests/test_config_repo_default.py` — asserts `config.toml` exposes both new keys.
- `tests/test_feedback.py` — `record_final` writes final into `partial`; `notify_on_final=False` suppresses only the final popup while start/stop still fire.
- `tests/test_daemon.py` — `_idle_watchdog`/`_maybe_auto_stop`: disarm-on-idle, keep-alive-with-speech, touch-resets-clock, disabled-at-0, noop-when-not-listening, and a real background-thread disarm test.
- `tests/test_idle_and_gpu.sh` (PRD T4) — unchanged 120 s armed-idle hallucination/CPU guard still passes (auto-stop default 30 s does not interfere because T4 arms listening then holds silence; note: auto-stop will disarm the daemon ~30 s into T4's 120 s window — **see §4 below, the one real interaction to verify**).

### 3.2 The fix

Update the one stale comment in `config.toml` (§2 above). No code, no test, no behavior change — comment-only.

---

## 4. One interaction to verify (test-suite consistency, not new behavior)

PRD T4 (`tests/test_idle_and_gpu.sh`) holds **120 s of armed silence** and asserts "no finals typed" + "daemon survives." With D1 now active (default `auto_stop_idle_seconds=30.0`), the daemon will **auto-disarm ~30 s into that window**. This is *correct new behavior*, but it raises two questions the implementing agent must confirm by re-reading the current `test_idle_and_gpu.sh`:

1. Does T4 still pass after the daemon auto-disarms mid-window? (It should: auto-disarm writes the `■ stopped` popup + journal line and flips `listening=false`, but types nothing — so "no finals typed" still holds, and the daemon process survives.) Confirm the test does not assert `listening==true` at the end of the idle window. If it does, that assertion must be relaxed (the test was written pre-D1).
2. If the test explicitly wants to exercise the *pure* 120 s hallucination guard without auto-stop interference, it may set `auto_stop_idle_seconds=0` in its daemon config override — but that is a test-only choice, not a product requirement.

If T4 already accounts for this, **no change is needed** — just note it in the acceptance evidence. This is the single most likely place the prior D1 commit left a latent test inconsistency, so it must be checked, not assumed.

---

## 5. Documentation impact

**Mode A — doc-with-work:**
- `config.toml` — the `hypr_notify` comment fix rides with §3.2. (`README.md` is already correct; `config.py` docstrings already correct.)

**Mode B — changeset-level docs:** **Does not apply.** README.md already documents both new knobs in its config table (`asr.auto_stop_idle_seconds`, `feedback.notify_on_final`), the `■ stopped`/`● listening`/`✔ <text>` notification discipline, and the auto-stop journal line. No cross-cutting README/overview sweep is warranted for a comment-only delta — re-stating it would be churn. The implementing agent should only touch README if §4 surfaces a real T4 inconsistency that changes documented expected behavior.

---

## 6. Acceptance criteria (definition of done for this delta)

1. `config.toml:49` comment no longer mentions "partial" for `hypr_notify`; matches the "start/final/stop" master-switch wording (D2/§4.5).
2. The existing test suite (`uv run pytest tests/` + `./tests/test_idle_and_gpu.sh`) still passes — confirming D1/D2/D3 are correctly in place and §4's T4 interaction is sound.
3. No functional code changes introduced (this is a spec-sync + comment fix). If §4 requires a T4 assertion relaxation, that change is the only permitted non-comment edit and is called out explicitly in the commit.
4. `grep -rn "partial" config.toml` returns no hits inside the `hypr_notify` comment.

---

## 7. Out of scope

- Re-implementing idle auto-stop, `notify_on_final`, or `record_final`→`partial` (all shipped in prior session).
- Any change to the RealtimeSTT recorder config, typing backends, control-socket protocol, systemd unit, or install.sh.
- The richer overlay UI / per-app profiles / voice commands listed in PRD §9 Future Work.

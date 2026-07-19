# Research Notes — P1.M5.T3.S1: Audit of `tests/e2e_virtual_mic.sh`

**Subject:** static audit of `tests/e2e_virtual_mic.sh` (364 lines) against PRD §6 T3 + the
work-item's 9 sub-checks (a)–(i). **NOT run** (rebinds global default audio source — AGENTS.md).
All findings below are verified by direct read of the script + the LIVE source it drives.

## 0. Method

Read the full script (364 lines). Cross-checked every claim against the actual source it exercises:
`voice_typing/config.py`, `voice_typing/launch_daemon.sh`, `voice_typing/ctl.py`,
`voice_typing/daemon.py`, `voice_typing/typing_backends.py`, and the sibling `tests/test_idle_and_gpu.sh`.
No audio mutation performed. `pactl` was NOT touched (would rebind the user's real mic).

## 1. The 9-check matrix (work-item contract a–i) — verified against LIVE source

| # | check | script line(s) | verdict | evidence |
|---|---|---|---|---|
| a | records ORIG default source BEFORE switching | `ORIG_SRC="$(pactl get-default-source)"` (before load-module) | ✅ PASS | G-SOURCE comment; restore-by-value in trap |
| b | loads module-null-sink | `MODIDX="$(pactl load-module module-null-sink sink_name="$SINK" media.class=Audio/Sink)"` (`SINK=vt_test`) | ✅ PASS | captures the module INDEX (not name) → safe unload |
| c | starts daemon with tmux backend | config.toml override `[output] backend="tmux"`, `tmux_target="voicetest"`; `XDG_CONFIG_HOME="$WORK/config" "$LAUNCH"` | ✅ PASS | config.py:266 XDG search order #1 = `$XDG_CONFIG_HOME/voice-typing/config.toml` |
| d | tmux session running cat>file | `"$TMUX_BIN" new-session -d -s "$TMUX_SESS" "cat > '$CAPFILE'"` (`TMUX_BIN=/usr/bin/tmux`) | ✅ PASS | matches daemon TmuxBackend `/usr/bin/tmux send-keys -t` (typing_backends.py:54,94-105) |
| e | plays WAVs via pw-cat | `pw-cat -p --target "$SINK" "$PAUSE_WAV"` + `"$MULTI_WAV"` + `"$SIMPLE_WAV"` | ✅ PASS | `--target vt_test` = SINK NAME (G-TARGET) |
| f | polls state.json partials DURING playback | bg loop `jq -r .partial "$WORK/state.json"` → `partials.log` (150×0.2s=30s) | ✅ PASS | criterion 3 = `partials.log` non-empty |
| g | **asserts drain (in-flight final typed after stop)** | — | ⚠️ **GAP (MEDIUM)** | see §2 |
| h | asserts nothing typed post-disarm | CRIT4_OK: `before=="$typed"` → stop → play SIMPLE → `after=capture_pane` → assert `before==after` | ✅ PASS | the on_final gate + disarmed mic |
| i | EXIT trap restores source + unloads module + kills tmux; **ALL voicectl in timeout** | trap cleanup EXIT (complete) | ⚠️ **GAP (HIGH)** | trap is complete; **voicectl timeout wrapping is INCOMPLETE** — see §3 |

**Net:** 7 of 9 checks PASS; 2 gaps (g + the timeout half of i). Everything else is correct + robust.

## 2. GAP (g) — drain path NOT exercised by this E2E [MEDIUM]

**PRD §6 T3 step 4 clause 3:** "assert the in-flight utterance's final IS typed after `voicectl stop`
(the graceful drain lets the final model finish — §4.2 #2)".

**The script does not do this.** Flow (criterion 4 block):
1. `voicectl start`
2. play `utt_pause.wav` (2 finals) THEN `utt_multi.wav` (3 finals) — both to completion
3. poll `capture-pane` up to 90s until ALL 5 refs fuzzy-match → `break`
4. `before="$typed"` (== all 5 matched → nothing in flight)
5. `voicectl stop`
6. play `utt_simple.wav`; assert `after==before` (nothing new typed)

At step 5 (stop), playback finished long ago and all 5 finals are already typed, so **nothing is in
flight** → the daemon's drain guard does not fire. daemon.py:1065: `_request_stop` only begins a drain
when `self._host is not None AND self._text_in_flight.is_set() AND self._final_pending` — all three
must hold; here `_text_in_flight`/`_final_pending` are clear. So the **graceful-drain path (§4.2 #2)
is not exercised by a real-audio stop-during-speech**.

**Conflict note:** criterion 4's PASS condition (`before==after`) is the OPPOSITE of a drain
assertion. If a final WERE drained+typed after stop, `after != before` → CRIT4 would FAIL. So the
script's design actively measures the GATE, not the drain. To test drain, stop would have to land
WHILE an utterance is in flight (e.g. stop during the 3 s mid-`utt_pause` silence, before PAUSE_B's
final), and the assertion would be "PAUSE_B IS typed despite the stop" (drain) — a different test.

**Coverage elsewhere:** the drain LOGIC is already audited (P1.M2.T1.S2 /
`research/drain_audit_findings.md`) + unit-tested (test_daemon.py mocked). So this is a
**coverage gap in the REAL-AUDIO E2E**, not a missing feature. Report it as "E2E proves the gate
(#4) but NOT the drain (§6 T3 clause 3); drain is unit-test-covered only."

## 3. GAP (i, timeout half) — voicectl control calls NOT wrapped in `timeout` [HIGH]

**AGENTS.md Rule 1 + the work-item (i):** "All voicectl calls wrapped in timeout." / "voicectl always
under timeout 30. The control socket will never time out on its own."

**ctl.py:112 (confirmed LIVE):** "Uses makefile("r") (NOT settimeout — makefile raises if the socket
has a timeout, P1.M4.T2.S1 §3)." + ctl.py:116 `sock.connect(...)`. **There is NO read timeout.** A
daemon that accepts the connection but never replies (wedged on its control lock, mid-shutdown VRAM
release, recorder-host spawn deadlock) → `voicectl` blocks FOREVER.

**e2e_virtual_mic.sh voicectl call audit:**

| call | site | wrapped in `timeout`? |
|---|---|---|
| `"$VOICECTL" status` | preflight (daemon-running check) | ❌ NO |
| `"$VOICECTL" status` | ready-wait loop (360×0.5s) | ❌ NO |
| `"$VOICECTL" status \|\| true` | post-ready echo | ❌ NO |
| `"$VOICECTL" start >/dev/null` | arm (criterion run) | ❌ NO — **blocks on cold model load (minutes); hangs FOREVER if recorder-host spawn deadlocks** |
| `"$VOICECTL" stop >/dev/null` | disarm (criterion 4) | ❌ NO |
| `timeout 5 "$VOICECTL" quit` | cleanup() trap | ✅ YES (the ONLY one) |

**5 of 6 voicectl control calls are unwrapped.** This is the hang vector AGENTS.md Rule 1 exists for.
`voicectl start` is the worst offender: `start()` (daemon.py) → `_load_host("normal")` SYNCHRONOUSLY
spawns the recorder-host child and WAITS for it (single-flight, daemon.py:722 `while self._loading`).
Cold cuDNN/cuBLAS init + 2 model loads = minutes; a recorder-host spawn deadlock (the exact
"deadlock on the recorder/GIL" AGENTS.md warns about) → voicectl start hangs forever, blocking the
whole script until a manual Ctrl-C.

**Smoking gun — the sibling script contradicts this.** `tests/test_idle_and_gpu.sh` codifies the fix:
- line 151-156: "voicectl's socket readline() has NO timeout (makefile is incompatible with
  settimeout, ctl.py … the SIGTERM-path teardown stall) would hang voicectl FOREVER. Wrap the control
  commands in timeout … `VOICECTL_TIMEOUT=30`"
- line 353-357: `voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }` — a wrapper FUNCTION
  that applies `timeout 30` to EVERY control command (start/stop/toggle/quit).

So the discipline exists in-repo; e2e_virtual_mic.sh simply does not apply it (except `quit`).

**Recommended fix (for a remediation task — NOT this audit item):** copy the
`VOICECTL_TIMEOUT=30` + `voicectl()` wrapper-function pattern from test_idle_and_gpu.sh, OR wrap each
call inline (`timeout 30 "$VOICECTL" start`, etc.). The ready-wait + post-ready status calls can use a
shorter timeout (e.g. `timeout 5`) since they should be sub-second.

## 4. Minor observations (not gaps — record for completeness)

1. **Ready-wait comment mis-attributes model-load timing.** The comment "waiting for ready (models
   load, up to 180s)" implies the ready-wait covers model load. Per §4.2bis + `start()`→`_load_host()`
   (synchronous), models load at `voicectl start`, NOT during the ready-wait. The ready-wait only
   polls the control SOCKET (seconds). Harmless (the 180s budget is never consumed because start
   blocks on the load instead), but the comment is inaccurate.
2. **Cleanup order** = daemon-stop → restore source → unload-module(by index) → kill tmux → rm temp.
   PRD §6 T3 step 5 lists "unload module, restore default source, kill tmux" (unload-then-restore);
   the script does restore-then-unload. Either order is safe (both happen, trap is idempotent +
   best-effort). Restoring the source first reconnects the user's mic ASAP — arguably better. Not a gap.
3. **`set-default-source vt_test.monitor`** is the PRD §6 T3 step 1 *alternative* approach (vs the
   `input_device_index` PyAudio-resolution path). PRD explicitly sanctions it ("Alternatively `pactl
   set-default-source vt_test.monitor` for the test and restore the original default after (record it
   first!)"). The script honors both parentheticals: records ORIG_SRC first, restores in trap. ✅
4. **TMUX_TARGET="voicetest" bare session name** (not `voicetest:0.0`): documented rationale is this
   machine's tmux base-index=1 → first pane is `voicetest:1.0`, not `:0.0`. The daemon's TmuxBackend
   (typing_backends.py:105 `[_TMUX, "send-keys", "-t", self._tmux_target, "-l", "--", text]`) passes
   `tmux_target` straight to `-t`, so a bare session name targets the session's active pane. Correct.
5. **`unset TMUX TMUX_PANE TMUX_TMPDIR`** at top — so the daemon (launched via `$LAUNCH`, inheriting
   this env) + the script both talk to the default tmux socket. Matches the daemon's send-keys (no
   `-L`). ✅
6. **5 canonical refs** (PAUSE_A/B, MULTI_1/2/3) PINNED verbatim from make_test_audio.sh. Fuzzy matcher
   = python `Counter` multiset overlap ≥0.80, case/punct-insensitive — matches PRD §6 "≥80% token
   overlap". ✅

## 5. Is it safe to RUN? — verdict

**Conditionally YES, with one caveat.**
- ✅ The cleanup trap (`trap cleanup EXIT`) is robust + idempotent: it fires on ANY exit (pass, fail,
  Ctrl-C), restores the user's default source FIRST, unloads the null-sink BY INDEX, kills tmux,
  kills the daemon (bounded: 5s quit → SIGTERM → 8s grace → SIGKILL), and verifies no `vt_test` trace.
  The PRD §6 T3 step 5 hard rule ("MUST NOT leave the user's default source switched") is honored.
- ✅ Preflight refuses if a daemon is already running (voicectl status OR systemctl is-active) — so it
  won't collide with the user's real daemon.
- ⚠️ **Caveat:** it does NOT honor AGENTS.md Rule 1 / `VOICECTL_TIMEOUT=30`. If the daemon wedges
  during `voicectl start` (recorder-host spawn deadlock) or `voicectl stop`, that call blocks forever
  and the script hangs until a manual Ctrl-C (which DOES trigger the EXIT trap → cleanup runs). So it
  is **safe-but-not-unattended-safe**: an operator must be able to Ctrl-C it. The fix (§3) makes it
  unattended-safe.

**Do NOT run during this audit item** (AGENTS.md: rebinds the global default audio source; the
work-item says "do NOT run it unless explicitly required"). The audit is STATIC. If a later task is
explicitly authorized to run it, apply the §3 timeout fix first.

## 6. What gap_e2e.md MUST contain (the deliverable)

1. Header: scope = static audit of `tests/e2e_virtual_mic.sh` vs PRD §6 T3; NOT run.
2. The 9-check matrix (§1 above) — a–i, each PASS/GAP with the script line + LIVE-source evidence.
3. GAP (g) drain [MEDIUM] — §2: play-to-completion design → stop lands with nothing in flight →
   drain path not exercised; gate (CRIT4) is the opposite assertion; drain is unit-test-covered
   (P1.M2.T1.S2). PRD §6 T3 clause 3 uncovered by E2E.
4. GAP (i) voicectl timeout [HIGH] — §3: 5/6 control calls unwrapped; ctl.py has no socket timeout →
   forever-hang risk on a wedged daemon (esp. `voicectl start` blocking on `_load_host`); sibling
   test_idle_and_gpu.sh wraps them (VOICECTL_TIMEOUT=30 + voicectl() fn). Recommended fix.
5. Minor observations (§4): ready-wait comment inaccuracy, cleanup order, set-default-source alt,
   TMUX_TARGET rationale, fuzzy matcher — all NOT gaps.
6. Safe-to-run verdict (§5): conditionally yes (trap is robust); caveat = missing voicectl timeouts.
7. Cross-refs: architecture/gap_socket.md, gap_voicectl.md, gap_typing.md, gap_lifecycle.md (source
   side already audited — this is the TEST-SCRIPT side); P1.M2.T1.S2 (drain unit coverage);
   P1.M5.T2.S1 (T1 offline, the drain's offline backstop); test_idle_and_gpu.sh (the timeout precedent).

## 7. External reference (PipeWire null-sink monitor testing — validates the "correct" verdict on a–f)

- PipeWire `module-null-sink` creates a sink + an auto-created `.<sink_name>.monitor` source. Pointing
  the default input at that monitor + playing into the sink is the standard virtual-mic E2E pattern
  (matches the script's `set-default-source vt_test.monitor` + `pw-cat -p --target vt_test`).
- The "record the original default source BEFORE set-default-source, restore it in an EXIT trap" is
  the canonical safe-cleanup idiom (the script's G-SOURCE + G-CLEANUP-IDEMPOTENT encode exactly this).
# Audit — P1.M5.T3.S1: `tests/e2e_virtual_mic.sh` (PRD §6 T3 — Full E2E with virtual mic + tmux)

**Date:** 2025-01-XX
**Method:** STATIC audit (read-only). NOT run — the script runs `pactl set-default-source` (rebinds the
user's GLOBAL default audio source) + loads CUDA models for minutes (AGENTS.md + work-item: "do NOT run
it unless explicitly required"). Findings cross-checked against the LIVE source the script drives.
**Verdict:** 7/9 checks PASS; **2 gaps** — (g) drain assertion [MEDIUM], (i) voicectl-timeout wrapping
[HIGH]. **Safe to run: CONDITIONALLY** (trap is robust; caveat = missing voicectl timeouts).

---

## 0. LIVE-source re-confirmation (every claim below was re-checked this round, not inferred)

| fact | LIVE source | confirmed line |
|---|---|---|
| voicectl has NO socket read timeout | `voice_typing/ctl.py` | 111-112 ("Uses makefile('r') (NOT settimeout — makefile raises if the socket has a timeout)…") ; read loop at 118 |
| `start()` → `_load_host()` is SYNCHRONOUS (single-flight) | `voice_typing/daemon.py` | 722 `while self._loading` (wait for in-flight spawn); 725 `self._loading = True`; 760+ the load; 762 `self._loading = False` |
| drain guard fires ONLY when an utterance is in flight at stop | `voice_typing/daemon.py` | 1053 `_request_stop`; 1065 `if self._host is not None and self._text_in_flight.is_set() and self._final_pending:` → `_begin_drain()` (1073); drain watchdog `_DRAIN_TIMEOUT_S=5.0` (138) |
| TmuxBackend uses `/usr/bin/tmux` + `send-keys -t <tmux_target> -l` | `voice_typing/typing_backends.py` | 54 `_TMUX = "/usr/bin/tmux"`; 102 `[_TMUX, "send-keys", "-t", self._tmux_target, "-l", "--", text]` |
| config search order #1 = `$XDG_CONFIG_HOME/voice-typing/config.toml` | `voice_typing/config.py` | 266, 284 |
| launch wrapper `exec`s python → `$!` IS the python PID | `voice_typing/launch_daemon.sh` | last line `exec "$PY" -m voice_typing.daemon "$@"` |
| the sibling script DOES wrap voicectl (`VOICECTL_TIMEOUT=30` + `voicectl()` fn) | `tests/test_idle_and_gpu.sh` | 156 `VOICECTL_TIMEOUT=30`; 151-155 the "would hang voicectl FOREVER" rationale; 357 `voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }` |

The 6 voicectl control calls in `tests/e2e_virtual_mic.sh` (the GAP (i) evidence):

| call | site (script line) | wrapped in `timeout`? |
|---|---|---|
| `"$VOICECTL" status` | 168 (preflight daemon-running check) | ❌ NO |
| `"$VOICECTL" status` | 219 (ready-wait loop, 360×0.5s) | ❌ NO |
| `"$VOICECTL" status \|\| true` | 225 (post-ready echo) | ❌ NO |
| `"$VOICECTL" start >/dev/null` | 228 (arm / criterion run) | ❌ NO — **blocks on cold model load (minutes); FOREVER if recorder-host spawn deadlocks** |
| `"$VOICECTL" stop >/dev/null` | 330 (disarm / criterion 4) | ❌ NO |
| `timeout 5 "$VOICECTL" quit` | 112 (cleanup() trap) | ✅ YES (the ONLY one) |

---

## 1. The 9-check matrix (work-item contract a–i)

| # | check | script line(s) | LIVE-source evidence | verdict |
|---|---|---|---|---|
| (a) | records ORIG default source BEFORE switching | 183 `ORIG_SRC="$(pactl get-default-source)"` (before any `load-module`) | G-SOURCE comment (header); restore-by-value in trap (138-140) | ✅ PASS |
| (b) | loads module-null-sink (captures INDEX, not name) | 191 `MODIDX="$(pactl load-module module-null-sink sink_name="$SINK" media.class=Audio/Sink)"` (`SINK=vt_test`); unload-by-INDEX in trap (144-146) | unloading by module NAME would unload ALL null-sinks (destructive) — script correctly unloads `$MODIDX` | ✅ PASS |
| (c) | daemon with tmux backend | 200-209 config.toml override `[output] backend="tmux"`, `tmux_target="voicetest"`; 215 `XDG_CONFIG_HOME="$WORK/config" "$LAUNCH"` | `config.py:266/284` search order #1 = `$XDG_CONFIG_HOME/voice-typing/config.toml` (first EXISTING wins) → override is honored | ✅ PASS |
| (d) | tmux session running `cat > file` | 213 `"$TMUX_BIN" new-session -d -s "$TMUX_SESS" "cat > '$CAPFILE'"` (`TMUX_BIN=/usr/bin/tmux`, line 59) | `typing_backends.py:54` `_TMUX='/usr/bin/tmux'`; `:102` `send-keys -t <tmux_target> -l` — same binary, same `-t` contract | ✅ PASS |
| (e) | plays WAVs via pw-cat | 252 `pw-cat -p --target "$SINK" "$PAUSE_WAV"`; 255 `... "$MULTI_WAV"`; 332 `... "$SIMPLE_WAV"` | `--target vt_test` = SINK name (G-TARGET); the null-sink auto-creates `vt_test.monitor`, which `set-default-source` (196) points the daemon at | ✅ PASS |
| (f) | polls state.json partials DURING playback | 240-250 bg loop `jq -r .partial "$WORK/state.json"` → `partials.log` (150×0.2s) | criterion 3 = `partials.log` non-empty (`CRIT3_OK`, 310-316); partials come from the daemon's `state_file="$WORK/state.json"` (207) | ✅ PASS |
| (g) | **asserts drain (in-flight final typed after stop)** | — (criterion 4 asserts the GATE, not drain) | `daemon.py:1065` drain guard needs `_text_in_flight.is_set() AND _final_pending`; the script's stop (330) lands AFTER all 5 finals matched → both clear → guard never fires | ⚠️ **GAP (MEDIUM)** — §2 |
| (h) | asserts nothing typed post-disarm | 326-340 CRIT4_OK: `before="$typed"` → stop (330) → play `$SIMPLE_WAV` (332) → `sleep 4` → `after=capture_pane` → assert `before==after` | the on_final gate + disarmed mic; the GATE assertion (criterion 4 / PRD §6 T3 step 4 clause 4) | ✅ PASS |
| (i) | EXIT trap restores source + unloads module + kills tmux; **ALL voicectl in timeout** | 107-160 `trap cleanup EXIT` (complete + idempotent) | trap is complete + idempotent (see §6); **voicectl timeout INCOMPLETE** — 5 of 6 control calls unwrapped (see §0 table) | ⚠️ **PARTIAL — trap PASS, voicectl-timeout GAP (HIGH)** — §3 |

---

## 2. GAP (g) — drain path NOT exercised by this E2E [MEDIUM]

**PRD clause:** §6 T3 step 4 clause 3 ("assert the in-flight utterance's final IS typed after
`voicectl stop`") + §4.2 #2 (graceful drain).

**Why missed:** the script plays `utt_pause.wav` (2 finals: PAUSE_A + PAUSE_B) THEN `utt_multi.wav`
(3 finals) to completion (252-255), polls `capture-pane` up to 90s (258-279) until ALL 5 refs
fuzzy-match (`break`), THEN calls `voicectl stop` (330). At stop time, playback finished long ago +
all 5 finals are typed → **nothing is in flight**. `daemon.py:1065` `_request_stop` begins a drain
ONLY when `_text_in_flight.is_set() AND _final_pending` — both clear here → the drain guard never
fires → the graceful-drain path (§4.2 #2) is NOT exercised with real audio.

**Conflict note:** criterion 4's PASS condition (`before==after`, "nothing typed after stop",
CRIT4 at 336) is the *opposite* of a drain assertion. If a final WERE drained+typed after stop,
`after != before` → CRIT4 would FAIL. So the script's design measures the GATE (PRD §6 T3 step 4
clause 4 / Acceptance #4), not the drain (clause 3). They cannot both be the same assertion.

**Coverage elsewhere:** the drain LOGIC is sound + unit-tested (`test_daemon.py` mocked; audited in
`P1.M2.T1S2/research/drain_audit_findings.md` — graceful stop, `_DRAIN_TIMEOUT_S=5.0` watchdog,
abort-on-idle). So this is an **E2E-coverage gap**, NOT a missing feature or a drain bug.

**Test shape that WOULD cover it:** stop DURING an in-flight utterance (e.g. send `voicectl stop`
inside the 3 s mid-`utt_pause.wav` silence, before PAUSE_B's final lands) and assert PAUSE_B IS
typed despite the stop (the drain lets the final model finish + `on_final` types it before disarm).
**(Fix for a downstream remediation task — NOT applied here; this is a REPORT item.)**

**Acceptance impact:** P1.M5.T5.S1 should credit the E2E for Acceptance **#4** (gate) + the
**pause-clause** of #2 (PAUSE_B transcribed through the real mic path), but NOT the **drain-clause**
of #2 (stop-during-speech), which stays unit-test-only.

---

## 3. GAP (i, voicectl-timeout half) — voicectl control calls NOT wrapped in `timeout` [HIGH]

**Requirement:** AGENTS.md Rule 1 ("voicectl always under timeout 30. The control socket will never
time out on its own") + work-item (i) ("All voicectl calls wrapped in timeout").

**Root cause:** `voice_typing/ctl.py:111-112` — "Uses makefile('r') (NOT settimeout — makefile
raises if the socket has a timeout)". There is **NO read timeout** (the read loop is at `:118`
`sock.makefile("r", ...)`). A daemon that accepts the connection but never replies (wedged on its
control lock, mid-shutdown VRAM release, recorder-host spawn deadlock) → `voicectl` blocks
**FOREVER**. (The `:131-132` request/one-line-response comment + the in-cli `Timer` hint exist
precisely because `makefile('r')` is incompatible with `settimeout`.)

**The 6 voicectl control calls in `e2e_virtual_mic.sh`** — see the §0 table. **5 of 6 are
unwrapped**; only the cleanup `timeout 5 "$VOICECTL" quit` (line 112) is wrapped.

**Worst offender — `voicectl start` (line 228):** `daemon.py` `start()` → `_load_host("normal")`
is SYNCHRONOUS (single-flight, line 722 `while self._loading` waits for the in-flight spawn; line
725 claims the load; the cold cuDNN/cuBLAS init + 2 model loads happen inline; line 762 clears
`_loading`) → `voicectl start` BLOCKS for the cold init (minutes); a recorder-host spawn deadlock
(the "deadlock on the recorder/GIL" AGENTS.md warns about) → hangs forever, blocking the whole
script until a manual Ctrl-C.

**In-repo precedent (the sibling script DOES wrap):** `tests/test_idle_and_gpu.sh`:
- lines 151-155: "voicectl's socket readline() has NO timeout (makefile is incompatible with
  settimeout, ctl.py `_send_command`), so any daemon-side hang (e.g. a regression of the
  abort()-under-`_lock` wedge, or the SIGTERM-path teardown stall) **would hang voicectl FOREVER**.
  Wrap the control commands in `timeout` so a hang fails LOUD (exit 124) instead of stalling the
  whole heavy test."
- line 156: `VOICECTL_TIMEOUT=30`
- line 357: `voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }` — a wrapper FUNCTION
  applying `timeout 30` to EVERY control call.

So the discipline exists in-repo; `e2e_virtual_mic.sh` simply does not apply it (except `quit`).

**Recommended fix (for a downstream remediation task — NOT applied here):** copy the
`VOICECTL_TIMEOUT=30` + `voicectl()` wrapper-function pattern from `test_idle_and_gpu.sh`, OR wrap
each call inline (`timeout 30 "$VOICECTL" start`, `timeout 30 "$VOICECTL" stop`, etc.). The
ready-wait (219) + post-ready (225) `status` calls can use a shorter timeout (e.g. `timeout 5`)
since a healthy `status` is sub-second (it is lock-free).

---

## 4. Minor observations (NOT gaps — recorded for completeness)

1. **Ready-wait comment mis-attributes model-load timing** (line 217): "waiting for ready (models
   load, up to 180s)" implies the ready-wait covers model load. Per §4.2bis (lazy load) +
   `start()`→`_load_host()` (synchronous, daemon.py:722), models load at `voicectl start` (228),
   NOT during the ready-wait (219, which only polls the control socket, fast). Harmless (the 180s
   budget at 219 is never consumed; `start` blocks on the load instead) but the comment is
   inaccurate.
2. **Cleanup order** = daemon-stop (110-130) → restore source (136-140) → unload-module-by-index
   (143-146) → kill tmux (148-149) → rm temp (151) → verify no `vt_test` trace (153-156). PRD §6
   T3 step 5 lists "unload module, restore default source, kill tmux"; the script does
   restore-then-unload. Either order is safe (both happen; every step is `|| true` / `2>/dev/null`
   → trap is idempotent + best-effort). Restoring the source FIRST reconnects the user's mic ASAP —
   arguably better.
3. **`set-default-source vt_test.monitor`** (line 196) is the PRD §6 T3 step 1 *alternative* (vs
   the `input_device_index` PyAudio-resolution path). PRD sanctions it ("Alternatively `pactl
   set-default-source vt_test.monitor` … record it first!"). Script honors both parentheticals:
   records `ORIG_SRC` first (183), restores in trap (138). ✅
4. **`TMUX_TARGET="voicetest"` bare session name** (line 73, NOT `voicetest:0.0`): documented
   rationale (lines 74-79) = this machine's tmux `base-index=1` → first pane is `voicetest:1.0`.
   The daemon `TmuxBackend` (typing_backends.py:102) passes `tmux_target` straight to `-t` → a
   bare session name targets the session's active pane regardless of base-index. Correct.
5. **`unset TMUX TMUX_PANE TMUX_TMPDIR`** (line 92) → daemon (launched via `$LAUNCH`, inherits
   env) + script both talk to the default tmux socket (daemon `send-keys` has no `-L`). ✅
6. **Fuzzy matcher** (261-270, 283-292) = python `Counter` multiset overlap ≥0.80,
   case/punct-insensitive — matches PRD §6 "≥80% token overlap". The 5 refs (73-77) are PINNED
   VERBATIM from `tests/make_test_audio.sh` (`PAUSE_A`, `PAUSE_B`, `MULTI_1/2/3`); cross-checked
   against `make_test_audio.sh`'s canonical strings — identical. ✅

---

## 5. PRD §6 T3 step-4 sub-assertion map (4 clauses → coverage)

| PRD §6 T3 step 4 clause | script criterion | verdict |
|---|---|---|
| 4.1 all-segments fuzzy (incl post-pause half) | ALLREFS_OK (277-296) + CRIT2_OK (299-317) (5 refs, PAUSE_B is the post-3s-pause half) | ✅ COVERED |
| 4.2 partials observable in state.json DURING playback | CRIT3_OK (308-316) (`partials.log` non-empty) | ✅ COVERED == check (f) |
| 4.3 in-flight final typed after `voicectl stop` (drain) | — (stop at 330 lands AFTER all 5 finals matched → nothing in flight) | ❌ NOT COVERED == check (g) = **GAP** |
| 4.4 nothing further typed while playing one more WAV after stop (gate) | CRIT4_OK (326-340) (`before==after`) | ✅ COVERED == check (h) |

---

## 6. Safe-to-run verdict

**CONDITIONALLY YES**, with one caveat.

- ✅ **Cleanup trap is robust + idempotent:** `trap cleanup EXIT` (line 107 declares; `trap cleanup
  EXIT` at 160 installs) fires on ANY exit (pass, fail, Ctrl-C). It (1) stops the daemon bounded
  — `timeout 5 voicectl quit` (112) → `kill -TERM $DAEMON_PID` (116) → 8s grace (16×0.5s, 117-120)
  → `kill -KILL` (122-123); (2) restores the user's default source FIRST (`pactl set-default-source
  $ORIG_SRC`, 138-140); (3) unloads the null-sink BY INDEX (`pactl unload-module $MODIDX`, 144-146
  — never by name); (4) kills the tmux session (148-149); (5) removes temp files (151); (6)
  verifies no `vt_test` trace (153-156). The PRD §6 T3 step 5 hard rule ("MUST NOT leave the user's
  default source switched") is HONORED. Because `launch_daemon.sh` ends in `exec "$PY" ...`,
  `$DAEMON_PID` (216) IS the python PID → `kill $DAEMON_PID` kills the right process.
- ✅ **Preflight** (166-173) refuses if a daemon is already running (`voicectl status` answers OR
  `systemctl --user is-active voice-typing`) — won't collide with the user's real daemon.
- ⚠️ **Caveat:** missing voicectl timeouts (§3). A wedged daemon during `voicectl start` (228) /
  `stop` (330) hangs the script until a manual Ctrl-C (which DOES trigger cleanup → source
  restored). So **safe-but-not-unattended-safe**: an operator must be able to Ctrl-C it. Apply the
  §3 timeout fix before any unattended/CI run.

**Do NOT run during this audit item** (AGENTS.md: rebinds global default audio source). If a later
task is explicitly authorized to run it, apply the §3 timeout fix first.

---

## 7. Cross-references

- Source-side audits (cite, don't re-derive): `architecture/gap_socket.md` (no socket timeout),
  `gap_voicectl.md` (voicectl CLI / socket readline), `gap_typing.md` (TmuxBackend `/usr/bin/tmux`),
  `gap_lifecycle.md` (lazy load + drain).
- Drain logic unit coverage: `P1.M2T1S2/research/drain_audit_findings.md` (`test_daemon.py` mocked).
- T1 offline (drain's offline backstop): `P1.M5.T2.S1` (`test_feed_audio.py`).
- Timeout precedent: `tests/test_idle_and_gpu.sh:151-156,357` (sibling P1.M5.T3.S2 audits it fully).
- Acceptance evidence consumer: `P1.M5.T5.S1` (#2 drain-clause caveat = unit-only; #4 gate = E2E-covered).
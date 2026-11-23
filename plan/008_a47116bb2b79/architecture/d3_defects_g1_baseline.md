# D3 defects + G1 baseline — read-only research record

HEAD `2335a9e` (main, 2026-11-22), tree clean except `plan/`. Every pytest run below used
`timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q` (one file per call; `--tb=line`
added only to capture one-line failure reasons), bash-tool timeout 360. No daemon, no voicectl,
no E2E/idle scripts, no CUDA suites. No repo file touched except this one.

---

## PART A — G1 regression baseline at HEAD

| # | File | Passed | Failed | Runtime |
|---|------|-------:|-------:|---------|
| 1 | tests/test_streaming_commit.py | 22 | **10** | 0.11 s |
| 2 | tests/test_streaming_core.py | 32 | **2** | 0.02 s |
| 3 | tests/test_streaming_freeze.py | 22 | **4** | 0.02 s |
| 4 | tests/test_streaming.py | 3 | **4** | 106.45 s (real small.en on wav fixtures) |
| 5 | tests/test_zero_diff_rewind.py | 3 | 0 | 0.01 s |
| 6 | tests/test_key_listener.py | 32 | 0 | 0.03 s |
| 7 | tests/test_control_socket.py | 27 | 0 | 3.37 s |
| 8 | tests/test_config.py | 54 | 0 | 0.03 s |
| 9 | tests/test_config_repo_default.py | 3 | 0 | 0.01 s |
| 10 | tests/test_textproc.py | 31 | 0 | 0.01 s |
| 11 | tests/test_typing_backends.py | 36 | 0 | 0.81 s |
| 12 | tests/test_voicectl.py | 36 | 0 | 2.85 s |
| 13 | tests/test_feedback.py | 38 | 0 | 0.05 s |
| 14 | tests/test_prompt_engine.py | 28 | 0 | 0.05 s |
| 15 | tests/test_context_prompt_refresh.py | 12 | 0 | 0.02 s |
| | **Total** | **379** | **20** | |

### A.1 Failure inventory (name — line — one-line reason — classification)

Legend: **(i)** = known legacy lazy-separator contract red (tests encode the *eager* separator
contract — commit types its trailing space immediately, separator as its own typed item — while
HEAD (since `26d570b` "Carry a lazy separator across interrupted sessions", 2026-10-28) defers
it). **(ii)** = new/unexpected or unclassified.

**tests/test_streaming_commit.py — 10 failed / 22 passed — exactly matches the 2026-11 handoff
measurement (10 failed / 22 passed) → all (i).**

1. `test_commit_extend_applies_casing_guard_to_the_delta` (:116) — actual typed delta
   `['then he said', ' stop ']` carries the trailing space; expected `' stop'` (separator
   deferred to its own later event). (i)
2. `test_commit_empty_delta_types_only_the_space` (:125) — actual `[('type','hello world')]`
   missing the trailing space; expected `[('type','hello world ')]`. (i)
3. `test_commit_shorter_final_backspaces_only_the_extra` (:209) — expected sequence ends with
   `('type', ' ')`; actual never types the separator op. (i)
4. `test_commit_advances_checkpoint_next_partial_diffs_against_empty_tail` (:226) — typed
   chunks differ in trailing-space placement (index-level diff `' world '` vs `' world'`). (i)
5. `test_commit_checkpoint_guard_context_is_screen_truth` (:241) — expected separator as a
   separate `' '` item between chunks; actual glues it onto a typed chunk. (i)
6. `test_commit_extend_stips…strips_spurious_mid_sentence_period` (:252) — expected
   `['Done', ' ', 'next']`; actual `['Done', ' next']` (separator folded into delta). (i)
7. `test_commit_frozen_absorbs_tail_and_types_separator` (:288) — frozen commit must type the
   separator; actual `[('type','hello wor')]` lacks the trailing space. (i)
8. `test_commit_space_type_failure_keeps_checkpoint_at_boundary` (:342) — `assert False is
   True` (`frozen` set but `frozen_session` not promoted on separator-type failure — the
   fail-safe promote path reacts to a separator keystroke that never happened). (i)
9. `test_reset_session_clears_everything_including_frozen` (:374) — `['Hello',' world ','Next']`
   vs expected `['Hello',' w…',' ','Next']` — separator placement again. (i)
10. `test_frozen_commit_space_type_failure_absorbs_nothing` (:491) — `frozen_session` not True
    after separator-type failure under freeze (same fail-safe family as #8). (i)

**tests/test_streaming_core.py — 2 failed / 32 passed (no prior handoff count).**

11. `test_mid_sentence_capitalized_partials_extend_case_insensitively` (:170) — actual first
    chunk `'and then he said '` (space glued); expected `"and then he said"` + separate
    `" "` item. (i) — separator-contract.
12. `test_no_separator_after_clean_commit` (:538) — after commit + 2× `reset_session`, actual
    `('type',' next sentence')` (leading space + lowercase) vs expected `('type','Next
    sentence')` — the lazy separator's "clean commit already spaced" state is not recognized
    across the session reset → double separator + guard lowercases. (i) — separator-contract.

**tests/test_streaming_freeze.py — 4 failed / 22 passed (no prior handoff count).**

13. `test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types` (:210) —
    "a frozen commit must absorb (no revision keystrokes) but still type the separator" —
    separator not typed. (i)
14. `test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen` (:243) —
    `('type','hello wor')` vs expected `('type','hello wor ')`. (i)
15. `test_rejected_final_freeze_lives_until_resume_then_next_utterance_types` (:314) — "the
    next commit must produce real backend calls": post-resume commit is an empty-delta commit,
    and with the separator deferred it produces zero keystrokes. (i)
16. `test_cancel_then_resume_restores_live_delta_typing` (:389) — expected commit's inter-final
    space typed eagerly `[('type','Hello world '), …]`; actual has no trailing space. (i)

**tests/test_streaming.py — 3 passed / 4 failed, 106.45 s (real-model harness; no prior
handoff count; ACCEPTANCE row 11 claims a past 7/7).**

17. `test_f_user_key_freeze` (:1627) — BUG-003 pin: "between the keypress and the commit the
    engine must send ONLY the append_space separator, got `[]`" — the separator is deferred,
    not sent. (i)
18. `test_g_stranded_tail` (:1795) — absorbed committed `'…Keep sleeping  '` (two trailing
    spaces) vs expected one — lazy separator + stranded-tail absorb disagree. (i)
19. `test_a_delta_cadence` (:1202) — "no delta-only extend cycle observed (every cycle
    rewound?)". **(ii) — NOT separator-shaped** (extend-vs-rewind cadence property).
20. `test_b_commit_rewind_exact` (:1236) — "no revising commit (a commit that rewound a
    non-empty tail) across 4 commits". **(ii) — NOT separator-shaped** (rewind property).

   For #19/#20: single run, read-only (no checkout to bisect). They are red against
   ACCEPTANCE's past-live 7/7 claim, so they are either a late regression from the post-T8
   commits (`cf2dfb1` debounce 10-19, `0e7dd05` clamped rewinds 10-25, `26d570b` lazy
   separator 10-28, `e5409a1` pacing 10-28) or a real-model flake on a loaded machine.
   **G1 must treat 3P/4F as the pre-change number and re-run this file before/after any D3
   change to disambiguate.**

**tests/test_zero_diff_rewind.py — 3/3 PASS — matches the handoff exactly (T1 exact-equal
guard, T2 k=0 full-tail rewind by design, T3 dropped-insertion desync).**

### A.2 tests/ACCEPTANCE.md current claims (stale vs the G1 baseline)

- **Row 11 (Streaming §4.2quater): PASS** — claims `tests/test_streaming.py` "7/7 green via
  `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v`" and
  `test_streaming_core.py test_streaming_freeze.py test_streaming_commit.py -q → 77 passed`.
  At HEAD: 3/7 and 76 passed / 18 failed (22+22+32 pass). Row 11's numbers are **stale by
  ~4 months of commits** (the lazy-separator + debounce + clamped-rewind era).
- **Row 12 (Cancel fallback): PASS** — `test_e_cancel` (real-model), socket dispatch
  `test_dispatch_cancel_routes_to_daemon_cancel_and_returns_shape` (test_control_socket.py:326),
  `voicectl cancel` smoke (regenerated shell evidence), listener-warning
  `test_zero_keyboard_warning_fires_once_at_first_arm`, BUG-002/BUG-007 daemon tests.
- **Totals (the dossier cross-check line):** "Overall verdict: **GO — 9/10 PASS on substance;
  #7 PASS-on-substance** (commit sign-off → P1.M6.T1.S3); 17/17 source gap audits COMPLIANT;
  424 LIVE-green test executions this round." (Rows 11/12 were appended after that 10-row
  dossier; the 9/10 line predates them.)

---

## PART B — D3.1 `fix/ydotoold-datagram` merge-risk assessment

**Topology.** `git branch -a`: `backup-19-new-commits-to-squash`, `fix/ydotoold-datagram`,
`main`, `origin/main`. `git log --oneline main..fix/ydotoold-datagram` → exactly one commit:
`33321c6 fix(ydotoold_client): open SOCK_DGRAM — ydotoold's socket is a datagram socket`.
`git merge-base main fix/ydotoold-datagram` = `f0d8d0a` (2026-10-31, "Send backspaces over a
persistent ydotoold socket").

**What 33321c6 changes** (`git diff main...fix/ydotoold-datagram --stat`: 2 files,
+293/−8):

- `voice_typing/ydotoold_client.py` (+30/−8): module docstring rewritten (SOCK_DGRAM
  rationale; Errno-91 history — "the original SOCK_STREAM implementation could never connect…
  every backspace burst silently degraded to per-batch CLI spawns"; wire-format caveat
  "PENDING independent verification against ydotoold source"); the ONE functional hunk in
  `_connect()`: `socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` → `SOCK_DGRAM` (+4-line
  comment). **No packing change** — `_MSG = struct.Struct("<6I")`, the press/SYN/release/SYN
  `sendall` sequence, and `press_backspace` are byte-identical to main.
- `tests/test_ydotoold_client.py` (new, 271 lines): the 11 tests live HERE — 9 test functions,
  11 items (`test_nonpositive_sends_no_datagrams` is parametrized n∈{0,−1,−3}):
  `press_backspace_3_sends_12_datagrams_24_bytes_each`,
  `press_backspace_3_key_datagrams_decode_press_then_release`,
  `press_backspace_interleaving_event_then_sync`,
  `one_connection_reused_across_two_calls`, `socket_is_datagram` (the regression pin),
  `server_killed_next_call_raises_and_backend_falls_back_to_cli`,
  `client_self_heals_after_server_restart`,
  `test_nonpositive_sends_no_datagrams[0/-1/-3]`,
  `press_backspace_3_latency_under_100ms`. 100% in-process FakeYdotoold (AF_UNIX SOCK_DGRAM
  server on tmp_path; client constructed after bind so the `/run/ydotoold.socket` fallback
  can never fire). **Not executed in this brief** (would need a checkout); PRD triage records
  them as 11 tests with "packing proven byte-identical to the real CLI by two independent
  captures."

**Conflict risk — enumerate.** Branch touches `voice_typing/ydotoold_client.py` +
`tests/test_ydotoold_client.py` (new file). `git log f0d8d0a..main -- <those files>` is EMPTY
and `git diff --stat f0d8d0a main -- voice_typing/ydotoold_client.py` is empty (main's copy is
byte-identical to the branch point; `tests/test_ydotoold_client.py` absent on main). Main's
changes since f0d8d0a (39 files): `.gitignore`, `PRD.md`, `config.toml`,
`tests/test_config_repo_default.py`, `tests/test_cuda_check.py`,
`tests/test_zero_diff_rewind.py` (+133), `voice_typing/config.py`,
`voice_typing/cuda_check.py`, `voice_typing/daemon.py` (compute_type plumbing only:
`_resolve_device_config` daemon.py:167-181 and the status snapshot daemon.py:2350-2358),
`voice_typing/recorder_host.py`, `tools/asr-lab/**`, `tools/im-lab/**`,
`tools/paste-lab/ghostty_probe.py`. **Zero overlap → git-level merge conflict risk: none.**
Semantic: no main change touches the ydotoold/typing path. Merge is low-risk; the only open
item is the branch docstring's own "PENDING independent verification" of the wire format.

**The 6 ms press→release contact gap does NOT exist in either socket path.**
`grep -nE 'gap|sleep|0\.006|contact|press.*release'` on both main's and the branch's
`ydotoold_client.py`: no 6 ms constant; `press_backspace` (identical, main
voice_typing/ydotoold_client.py:66-72) is
`for i in range(n): (if i: sleep(_CHAR_GAP_S)); _key(14,1); _key(14,0)` — press and release
back-to-back with **zero contact time**; the only sleep is the 12 ms inter-CHAR gap (skipped
before char 0). The gap exists only in the CLI fallback: `voice_typing/typing_backends.py:148`
`["ydotool","key","-d","6"] + ["14:1","14:0"] * n` — `-d 6` = 6 ms between events (comment
typing_backends.py:147: "-d 6 = 6ms/event, 2 events/char = 12ms/char"). PRD triage confirms
(PRD.md:584): "add the 6 ms press→release contact gap (protocol finding: CLI gaps every
event; socket path currently does not)." → merging 33321c6 does NOT close that gap; it is
follow-up work on the merged socket path.

**Main's `voice_typing/ydotoold_client.py` sites (file:line):**

- SOCK_STREAM-vs-DGRAM bug site: **ydotoold_client.py:41** —
  `s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)` against ydotoold's DGRAM socket →
  `connect()` raises Errno 91 ("Protocol wrong type for socket").
- Errno-91 fallback path: `_key` catches `OSError` → `_close()` + `raise` (**ydotoold_client.py:51-56**)
  → `YdotoolBackend.press_backspace` catches, logs the journal WARNING, falls back to one
  paced CLI spawn (**typing_backends.py:138-149**).
- Journal-warning site: **typing_backends.py:143-144** —
  `logger.warning("ydotoold client failed; falling back to ydotool CLI", exc_info=True)`
  (PRD triage: 56 journal warnings/week while broken).
- Pacing constants: `_CHAR_GAP_S = 0.012` (12 ms/char) **ydotoold_client.py:25**;
  `_MIN_SPAWN_GAP_S = 0.025` (25 ms inter-spawn floor) **typing_backends.py:58** (enforced by
  `_paced_run`, typing_backends.py:61-68); text-path pacing `ydotool type --key-delay 12`
  typing_backends.py:131.
- Client injection into the backend: `make_backend` imports `YdotoolClient`
  (typing_backends.py:227).

---

## PART C — D3.2 cancel auto-repeat audit

**Auto-repeat filter (exact lines).** `voice_typing/key_listener.py:74-88
parse_key_event()`; the filter is **:81** `if ev_type != ecodes.EV_KEY or value != 1: return
None` — value 0 (release) and **value 2 (autorepeat)** both drop, non-EV_KEY too. Docstring
:77-79: "A held Backspace therefore fires exactly ONE cancel (the press), never autorepeat
storms." (Module header :18-19 repeats the contract.)

**How key events reach the daemon.** `_pump_events` (key_listener.py:199-225) maps
`BACKSPACE_PRESS → cancel_cb()`, `OTHER_PRESS → other_key_cb()`, gated by `is_active()`
(:216). The daemon constructs the listener (daemon.py:799-805):
`KeyListener(cancel_cb=self._on_cancel_backspace, other_key_cb=self._on_user_keypress,
is_active=lambda: self._listening.is_set())`.

- `_on_cancel_backspace` (daemon.py:1633-1643): `if self._listening.is_set(): self.cancel()`.
- `_on_user_keypress` (daemon.py:1645-1652) → `note_user_keypress` (daemon.py:1581-1631).
  Default `cancel.keypress_action = "disarm"` (config.py:181; config.toml:53) → **HALT
  semantics**: any real non-Backspace keypress while armed disarms entirely (1.5 s post-arm
  grace ignores the hotkey's own chord; modifiers pre-filtered at key_listener.py:83-85).

**Daemon-side cancel compensation (exact site).** `VoiceTypingDaemon.cancel()`
daemon.py:1756-1795; the compensation is **daemon.py:1779**
`n = max(tail_len - 1, 0)  # the keystroke already deleted 1 char` (tail via
`_pending_tail_len`, daemon.py:1554-1568). Then, if text is in flight: latch the
cancel-suppression window + `host.cancel()` (drop buffered audio, daemon.py:1785-1792), and
`_reset_stream_after_cancel()` (daemon.py:1569-1580) → `stream.reset_after_cancel()`
(streaming.py:317-331: clear tail, set `_suppressed`).

**Sustained Backspace HOLD today (press → R repeats → release), armed, tail in flight:**

1. **press (value 1)** → one cancel: `press_backspace(tail_len−1)` deletes the rest of the
   fragment on screen (12 ms/char paced), the suppression window latches + stamps
   (daemon.py:1788-1791), the child drops buffered audio, the tail resets. Screen now shows
   the fragment's first char deleted by the keystroke + `tail_len−1` by the daemon.
2. **repeats (value 2)** → `parse_key_event` :81 returns `None` → **invisible to the daemon
   by design** — but the OS auto-repeat keeps deleting REAL on-screen characters. Each repeat
   eats one char of text *before* the cancelled fragment (committed dictation / user text);
   the daemon's accounting is already zeroed (`tail_len = 0`, `committed` unchanged), so
   these deletions are uncompensated and unobservable. Repeats that land while the daemon's
   paced `press_backspace(n)` burst is still running interleave with it: total deleted =
   `n + 1 + R` vs `n + 1` believed — **belief-desync** (PRD.md:585: "Cancel compensation
   assumes one physical Backspace = one character (auto-repeat violates it) →
   under-compensation manufactures belief-desync"). Repeats do NOT re-fire cancel (correct —
   no autorepeat-cancel storm), but note a *separate press* while text is in flight DOES
   re-latch/re-stamp the suppression window (daemon.py:1789-1791, "refreshed per press").
3. **release (value 0)** → :81 returns `None` → nothing.

**Existing coverage (grep autorepeat / value.*2 / hold / repeat in tests/):**
`tests/test_key_listener.py:61-65 test_autorepeat_ignored` (parse level: value 2 → None for
Backspace and KEY_A) and `tests/test_key_listener.py:218-228
test_repeated_backspace_presses_route_one_cancel_each` (pump level:
`[_BS_PRESS,_BS_REPEAT,_BS_REPEAT,_BS_PRESS]` → exactly 2 cancels). The compensation itself
is pinned by `test_streaming.py::test_e_cancel` ("press_backspace(len(tail)−1)") and the
daemon cancel suite — but **no test anywhere simulates the R extra OS-level deletions of a
hold** (the desync mechanism); the only other "repeat" hits are unrelated
(`test_mic_retry_filter_suppresses_repeats_within_window` is mic-retry, not keys).

---

## PART D — D3.3 cancel-suppression window latch: closure assessment

**Commit 4640041** (2026-10-09, "Minimal-diff revises; self-healing cancel window"; stat: 9
files +637/−139 — streaming/daemon/recorder_host + 5 test files + README):
(a) minimal-diff (LCP) revises; (b) ROOT fix in the recorder child — the abort handler now
tells an in-flight decode from an idle gap via a lock held across the whole `text()` call, so
a cancel landing between `text()` calls is no longer wiped by the per-utterance marker clears
(the lost-sentinel source), and the recorder interrupt is time-bounded; (c) daemon backstop —
the window records when it latched; a final arriving past the bound closes the window and
commits; both healthy exits (sentinel consumption, fresh arm) clear the stamp.

**The latch at HEAD lives in `daemon.py`, NOT streaming.py** (streaming.py carries the
separate ENGINE-level `_suppressed`):

- Latch: `cancel()` daemon.py:1788-1792 — `_cancel_suppress_final = True`;
  `_cancel_suppress_since = time.monotonic()` (**refreshed per press**, comment :1790-1791);
  `host.cancel()`.
- Bound: `_CANCEL_SUPPRESS_TIMEOUT_S = 5.0` daemon.py:164 (rationale :151-163: sentinel
  ~0.5 s, racing real final ~2 s, matches `_DRAIN_TIMEOUT_S`).
- Drop path in `on_final` (daemon.py:1158-1217): while latched, EVERY final is dropped.
  - Timeout self-heal :1166-1189 — past 5 s: close window (`False`/`None`), WARNING
    "suppression window open >5.0s with no marked sentinel", absorb any accumulated tail
    (`stream.freeze(…, session=True)` + `reset_boundary()`, :1184-1189 "TAIL-ACCUMULATION
    FIX"), then fall through and process the final.
  - Within bound :1193-1207 — `host.consume_cancel_mark()` (recorder_host.py:310-319): the
    marked sentinel closes the window, clears the stamp, `_final_pending=False`,
    `_utterance_finalized=True` (BUG-007 bookend).
  - **Both paths** :1213-1216 — every DROPPED final is still an utterance boundary:
    `stream.freeze("final dropped (cancel suppression window latched)", session=True)` +
    `reset_boundary()` — the tail can never accumulate across dropped finals; then `return`
    :1217 (no clean, no type, no record_final).
- Resets: sentinel consumption (:1194-1197), timeout self-heal (:1177-1178), fresh `_arm()`
  (:1371-1374 — clears flag AND stamp). Partials do NOT close the daemon latch:
  `_touch_speech` (daemon.py:1460-1499) only calls `stream.resume()` (:1498-1499, "the ONE
  post-cancel lift point") — that lifts the ENGINE `_suppressed` (streaming.py:428-458,
  `_suppressed=False` at :458; set by `reset_after_cancel` :317-331; mirror-only partials
  while set :573).
- Child-side source fix (4640041 part b) at HEAD: recorder_host.py `_drain_stale_abort_signals`
  (:936+), the text-loop stale-signal check (:732-744), arm-time purge (:874-888), sentinel
  mark relayed from the child payload (:437-439).

**Tests pinning it:** tests/test_daemon.py:4529
`test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`; :4564
`test_arm_clears_stale_cancel_suppression`; :5142 `test_lost_sentinel_self_heals_after_timeout`
(stamp aged past the bound → force-close + "fresh sentence" processed + window cleared);
:5168 `test_sentinel_consume_clears_suppress_since`; :5184
`test_fresh_arm_clears_suppress_since`; plus recorder-host stale-signal/lock/bounded-interrupt
tests from 4640041 (tests/test_recorder_host.py). `tests/test_zero_diff_rewind.py` T1–T3 pin
the *rewind mechanisms* the latch incident feeds (T1 exact-equal guard → incidents are not
equality misses; T2 k=0 divergence orders a full-tail rewind by design; T3 dropped-insertion
desync makes the next rewind eat committed text) — they do NOT pin the latch itself.

**Closure assessment: NOT closed at HEAD — treat as open.** Evidence:

1. PRD.md:586 (2026-11-18 triage, "Known defects"): "Cancel-suppression window latched and
   dropped finals 4× in the week of 2026-11-12..18 ('missing/repeated sections') — **window
   latch timing needs investigation**."
2. The incident week ran builds that ALREADY contained both backstops: 4640041 (10-09) and
   0e7dd05 (10-25, clamped rewinds + dropped-finals-boundary-reset). The deployed tip during
   2026-11-12..18 was f0d8d0a-era (2026-10-31) or earlier — all post-4640041. So the 4×
   recurrence happened WITH the 5 s self-heal and boundary reset in place.
3. No fix landed after the triage: `git log --since=2026-10-09 -- daemon.py recorder_host.py`
   → cf2dfb1, 0e7dd05, 965f903, bcfd171 (compute_type only); nothing after 2026-11-19.
4. The pinning gap matches the incident shape: `test_lost_sentinel_self_heals_after_timeout`
   covers one cancel + a final arriving >5 s later. It does NOT cover (a) finals arriving
   *within* the bound while the user actively re-speaks after a sentinel loss (dropped by
   design — "missing sections"), nor (b) the **stamp-refresh-per-press**: every new Backspace
   press while text is in flight re-latches and re-stamps the window (daemon.py:1789-1791), so
   a cancel → re-speak → cancel → re-speak loop (a user correcting themselves repeatedly)
   chains the window open indefinitely, dropping each re-said sentence's final — a mechanism
   that reproduces "dropped finals 4×" inside one session with no bound ever firing.

**Exact event-sequence a regression test must replay (daemon-level, mock host, streaming on):**

1. Arm; feed partials so text() is in flight and a tail is pending.
2. Backspace press #1 → `cancel()` (latch + stamp S1, host.cancel(), tail reset).
3. Sentinel LOST — do NOT call `host.mark_cancel_sentinel()` (the cancel-raced-text()-boundary
   path 4640041(b) was meant to close; the incident proves it still leaks).
4. User re-speaks: partial → `_touch_speech()` (engine `resume()`; partials stream live
   again — tail grows) — **daemon latch still closed**.
5. Final of the re-said sentence arrives at S1+δ, δ < 5 s → **DROPPED** (freeze(session)+
   reset_boundary; nothing typed/recorded — the "missing section").
6. Backspace press #2 while the new text is in flight → re-latch, stamp refreshed to S2 = now.
7. Re-speak → final at S2+δ, δ < 5 s → DROPPED again. Repeat ×4.

Assertions to decide (product call): how many finals may be dropped per cancel; whether a
partial/`_touch_speech` (genuinely-new speech, no sentinel) should close or refuse to
re-stamp the window; and that the chain terminates even when presses keep refreshing the
stamp. Today's code has no bound on the chained case — that is the open defect.

---

## Command log (every claim above traces to one of these)

- `git rev-parse HEAD` → 2335a9ee93ae9f21851134d9c78adcef968c44f5 (main; only `plan/` untracked)
- `timeout 300 /home/dustin/.local/bin/uv run pytest tests/<each of the 15 files> -q [--tb=line]`
- `cat tests/ACCEPTANCE.md` (rows 11/12, dossier GO line)
- `git branch -a`; `git log --oneline main..fix/ydotoold-datagram` (→ 33321c6);
  `git merge-base main fix/ydotoold-datagram` (→ f0d8d0a);
  `git diff main...fix/ydotoold-datagram --stat` (+ full diff);
  `git show fix/ydotoold-datagram:voice_typing/ydotoold_client.py`;
  `git show fix/ydotoold-datagram:tests/test_ydotoold_client.py` (test defs);
  `git log/diff f0d8d0a..main` (overlap enumeration)
- `git show 4640041 --stat` (+ message); `git log --date=short -12` (incident-window dating)
- Source reads: voice_typing/{key_listener,ydotoold_client,typing_backends,streaming,
  daemon,recorder_host,config}.py; config.toml; PRD.md:570-590; tests/{test_key_listener,
  test_zero_diff_rewind,test_daemon,test_streaming_commit,test_streaming_core,
  test_streaming_freeze,test_streaming}.py

# D3.2 closure decision — P1.M1.T3.S2 (mitigate or record the residual desync window)

**Decision: BOUNDED — record the evidence and STOP. No mitigation, no gold-plating.**

## 1. The question (item contract)

PRD fix rules already hold (cancel only while armed + tail pending; idempotent; compensation by
subtraction — daemon.py:1756-1795, verified). The only open question is whether the hold window
is bounded. Input = the S1 (P1.M1.T3.S1) audit note in the hold-trace test docstring +
architecture Part C.

## 2. The desync mechanism (recap, Part C)

A held Backspace: the daemon sees ONLY the press (key_listener.py:81 drops value≠1), compensates
`press_backspace(n)`, `n = tail_len − 1`. The OS autorepeat keeps deleting REAL chars invisibly.
Repeats landing while the paced burst runs interleave with it: total deleted = `n + 1 + R` vs
`n + 1` believed → desync of R chars. Post-burst repeats hit zeroed accounting (tail_len = 0) →
plain user edits, uncompensable BY DESIGN (not desync — the engine owns nothing).

## 3. The bound inputs — all three verified finite (the load-bearing finding)

R ≤ repeat_rate × burst_duration, burst_duration = n × per_char_pace + spawn_gap. Each factor:

1. **per_char_pace — 12–18 ms/char, constant, argv-pinned.** typing_backends.py:
   - wtype: `_paced_run(["wtype","-d","12"] + ["-k","Backspace"]*n)` (:109-116) → 12 ms/char.
   - ydotool CLI: `["ydotool","key","-d","6"] + ["14:1","14:0"]*n` (:134-152) → 6 ms/event ×
     2 events/char = 12 ms/char.
   - ydotoold socket: `self._client.press_backspace(n)` — "18 ms/char (contact 6 + inter 12;
     P1.M1.T2.S2)" (:140).
   - `_MIN_SPAWN_GAP_S = 0.025` (:65) adds ≤25 ms ONCE (single batched spawn), not per char.
   - **Pinned in tests**: test_typing_backends.py:310 (`test_wtype_press_backspace_exact_argv`),
     :318/:321 (`test_ydotool_press_backspace_exact_argv`, asserts the `-d 6` + `14:1/14:0`×n
     argv), :413 (CLI fallback argv), :427 (80-char burst shape). The recorded bound's inputs
     cannot silently rot.
2. **n — bounded by VAD segmentation + the accounting clamp.** n = pending tail ≤ one utterance:
   VAD commits at `post_speech_silence_duration` (0.6 s normal / 0.8 s lite, config.toml:37-38)
   so tails are per-pause fragments (typically ~10–40 chars); the streaming invariant clamps
   every rewind to the engine's own tail ("NEVER delete more characters than THIS engine typed
   since the checkpoint — clamped to len(tail)", streaming.py:870-871) and accounting always
   uses the REAL tail (streaming.py:31, :280, :312 `pending_tail_len`).
3. **repeat_rate — finite, OS-typical.** Linux evdev typematic default ≈ 30 cps (500 ms delay).
   A documented assumption (same figure Part C and S1's note use), not a code constant.

## 4. Corrected arithmetic (supersedes the stale figure in S1's docstring / Part C)

Part C and S1's audit note say "~12 ms/char" AND "≤150 ms for ~80 chars → R ≤ ~4–5 chars" —
internally inconsistent (12 ms/char × 80 = 960 ms). True parametric bound:

    R ≤ 30 cps × (n × 0.012–0.018 s + 0.025 s)

- Typical tail 10–40 chars → burst 0.15–0.75 s → R ≈ **4–22 chars**.
- Pathological 80-char tail → burst ≈ 1.0–1.4 s → R ≈ **30–45 chars**.
- Finite and parametric in n; n itself bounded by VAD cadence (§3.2). No unbounded input exists.

## 5. The decision, against the item's LOGIC

- "if bounded and correct-by-design → record the evidence and STOP — do not gold-plate": **this
  branch**. All three bound inputs are finite (§3); post-burst repeats are by-design plain user
  edits (idempotence rule; §2). The item's example mitigation ("bound the burst so a hold past
  the burst is provably a user edit") is ALREADY structurally present: the burst is finite
  (n clamped to the engine's own tail × fixed per-char pace), and after it completes the
  accounting is zeroed so any further deletion is provably a user edit.
- Mitigation would observe value==2 events or pace-compensate — S1's pin
  (`test_sustained_backspace_hold_fires_one_cancel_and_never_restamps`) exists precisely to make
  that a deliberate red. Nothing justifies it: worst-case loss is a few dozen chars of text the
  user was actively Backspacing through anyway.

## 6. Conditional fallback (ONLY if a re-audit finds an unbounded input — not the case today)

Decision procedure for a future re-run: grep-verify (a) key_listener.py:81 filter intact,
(b) the three pace argv shapes (test_typing_backends.py:310/:318/:413) intact,
(c) streaming.py clamp + VAD commit cadence intact. If ANY input is unbounded, the smallest
PRD-sanctioned mitigation is a bounded compensation burst: clamp `n` to a fixed duration budget
(`n_capped = min(n, BUDGET_S / per_char_pace)`), journal the stranded remainder, document that a
hold past the burst is provably a user edit — accepting that stranded tail chars stay on screen
(a worse failure than the desync) and that S1's pin + S2's note must be updated deliberately.

## 7. Consequences for D3.2 closure

- D3.2 closed with: (a) the S1 hold-trace regression test (the "test" half, landed in parallel),
  (b) S2's corrected bound + decision recorded in that test's AUDIT NOTE docstring (this task's
  edit — the docstring is the designated Mode A record; DOCS: none means no README change), and
  (c) this note (the orchestrator-facing evidence record).
- No source change. No README. No new tests (the bound's inputs are already pinned, §3.1).

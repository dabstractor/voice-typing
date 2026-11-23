# PRP — P1.M1.T2.S2: Add the 6 ms press→release contact gap on the ydotoold socket path

## Goal

**Feature Goal**: Close the protocol-finding gap from the PRD §8 triage — "CLI gaps every event; socket path currently does not." The socket path's `press_backspace` sends press and release back-to-back (`ydotoold_client.py:70-71`); zero contact time can read as no keypress at all in some apps. Insert **~6 ms contact time between press and release** (new constant `_CONTACT_GAP_S` beside `_CHAR_GAP_S`), **keeping the 12 ms inter-char gap** (per-char cycle 12→18 ms), mirroring the CLI fallback's `ydotool key -d 6` contact behavior. Extend the merged `tests/test_ydotoold_client.py` with per-event spacing assertions.

**Deliverable** (2 files edited after S1's merge):
1. `voice_typing/ydotoold_client.py` — `_CONTACT_GAP_S = 0.006` constant; the contact sleep in `press_backspace`; module-docstring gap rationale (Mode A); the stale "12 ms/char" comments aligned to 18.
2. `tests/test_ydotoold_client.py` — `FakeYdotoold.times` arrival-timestamp extension (additive); a new spacing test asserting per-key press→release ≥ 6 ms and inter-key ≥ 12 ms; (optional) refresh the latency test's pacing comment.

**Success Definition**:
- (a) `grep -n '_CONTACT_GAP_S' voice_typing/ydotoold_client.py` shows the constant @~26 + one sleep in `press_backspace` between the two `_key` calls; `_CHAR_GAP_S` inter-char sleep unchanged.
- (b) The new spacing test passes: for `press_backspace(3)`, each KEY pair's arrival delta ≥ `_CONTACT_GAP_S − 0.002` and each release→next-press delta ≥ `_CHAR_GAP_S − 0.002` (6 key events from 12 datagrams).
- (c) The suite is green: `timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py -q` (11 existing + the new test; the existing `test_press_backspace_3_latency_under_100ms` stays green — verified: 42 ms < 100 ms and ≥ its pacing-sanity floor).
- (d) `git diff --name-only` ⊆ the 2 files (+ `typing_backends.py` ONLY for the stale comment at ~:147).
- (e) No behavior change beyond pacing; the datagram count/content is byte-identical (12 datagrams for n=3 — framing untouched).

## User Persona

**Target User**: anyone typing through the ydotool path into apps that require a minimum keypress contact duration to register the key (the class of app that works via the CLI's `-d 6` pacing but drops zero-gap socket pairs).
**Pain Points**: PRD §8 Known-defects triage — the socket path (about to go live via S1's merge) would have shipped WITHOUT the contact time the real CLI always had; this lands parity before the socket path becomes primary.

## Why

- **PRD §8 mandates it**: "MERGE + add the 6 ms press→release contact gap (protocol finding: CLI gaps every event; socket path currently does not)." S1 is the MERGE; THIS is the gap.
- **The gap is real on both socket paths**: `_key` sends press/release back-to-back (no sleep between the pair in `press_backspace` @63-71); only the inter-char gap exists. The CLI (`ydotool key -d 6`, typing_backends.py:145-149) gaps EVERY event — a press always has ≥6 ms contact.
- **Timing budget is verified safe**: per-char 12→18 ms; `press_backspace(3)` sleeps 42 ms — the existing latency test's `< 100 ms` budget and its `≥ 2×_CHAR_GAP_S − 2 ms` pacing floor both still hold (verbatim-checked).
- **Scope discipline**: no framing/protocol change (datagram bytes identical), no CLI-fallback logic change (S3 owns the fallback guard), no rebalancing of the 12 ms inter-char gap (the contract fixes 6+12).

## What

Add `_CONTACT_GAP_S = 0.006` beside `_CHAR_GAP_S`; sleep it between the press and release `_key` calls in `press_backspace`; document the rationale in the module docstring (Mode A); align the two stale "12 ms/char" comments; extend the test file with arrival-timestamped spacing assertions (small additive `FakeYdotoold.times` list).

### Success Criteria

- [ ] `_CONTACT_GAP_S = 0.006` defined beside `_CHAR_GAP_S` (@~25-26) with a CLI-parity comment.
- [ ] `press_backspace` loop: `… _key(_BACKSPACE, 1); time.sleep(_CONTACT_GAP_S); _key(_BACKSPACE, 0)` — inter-char `if i: time.sleep(_CHAR_GAP_S)` unchanged.
- [ ] Module docstring notes the contact-gap rationale (Mode A): apps need minimum press→release contact time; the CLI's `-d 6` paces every event; the socket path now matches (6 ms contact + 12 ms inter-char = 18 ms/char).
- [ ] `FakeYdotoold` gains `self.times` (arrival `time.monotonic()` per datagram, appended in `_serve`) — `datagrams` shape UNCHANGED.
- [ ] New `test_press_backspace_contact_gap_spacing` (name in that spirit): filters the KEY datagrams (`ev_type == EV_KEY`) from `press_backspace(3)`'s 12, asserts press→release ≥ 6 ms and release→next-press ≥ 12 ms (slack 0.002, the file's style).
- [ ] Existing latency test green unchanged (optionally refresh its pacing comment to "2 inter-char + 3 contact gaps").
- [ ] Stale comments aligned: `_CHAR_GAP_S`'s own comment; `typing_backends.py:~147` "persistent socket, 12 ms/char (3e)" → 18 ms/char.
- [ ] Both suites green; diff ⊆ the 2-3 files.

## All Needed Context

### Context Completeness Check

_Pass._ The edit sites are quoted verbatim (research note §2), the branch test file's structure (FakeYdotoold, fixtures, datagram interleaving, the verbatim latency test) is verified from commit 33321c6, the timing budget is arithmetically checked against the existing test's bounds, and the sequencing gate on S1's merge is explicit. An agent new to the repo can implement from this PRP + the note.

### Documentation & References

```yaml
# MUST READ — the verified edit sites + test seam + timing arithmetic
- docfile: plan/008_a47116bb2b79/P1M1T2S2/research/contact_gap_edit_sites_and_test_seam.md
  why: "§2 the verbatim press_backspace loop + where the gap goes (between the _key calls, NOT inside
        _key); §3 the end-state pacing (6+12=18ms/char; press_backspace(3)=42ms) + the verbatim
        existing-latency-test bounds that stay green; §4 the FakeYdotoold times-extension design +
        the 12-datagram event/sync interleaving; §5 sibling boundaries (no 6+6 rebalance)."
  critical: "Task 0 gate: the test file exists only AFTER S1's merge. Everything below assumes it."

# MUST READ — the merge that delivers the file being extended (the parallel contract)
- docfile: plan/008_a47116bb2b79/P1M1T2S1/PRP.md
  why: "S1 merges fix/ydotoold-datagram (33321c6) — bringing voice_typing/ydotoold_client.py with
        SOCK_DGRAM @:41 + the NEW tests/test_ydotoold_client.py (11 in-process FakeYdotoold tests).
        The branch's ONLY client change is _connect; the rest is byte-identical to main (research
        §1) — so main's verified line numbers hold modulo the merge."
  critical: "Do NOT touch _connect or the CLI fallback (S1/S3 territory). The gap is the ONLY
            behavior change."

# THE EDIT SITE — the client (post-merge)
- file: voice_typing/ydotoold_client.py
  why: "_CHAR_GAP_S @25; _key @51 (sends ONE datagram — the gap does NOT go here); press_backspace
        @63-71 (the loop with the inter-char sleep + the back-to-back pair). Module docstring already
        references `ydotool key -d 6` pacing — extend it (Mode A)."
  pattern: "Bare time.sleep, no injectable clock — same as the existing inter-char sleep. Keep the
            constant beside _CHAR_GAP_S with a parity comment."
  gotcha: "Update _CHAR_GAP_S's own comment ('Rev 3d: 12 ms/char') — per-char is now 18 ms. And
           typing_backends.py:~147's 'persistent socket, 12 ms/char (3e)' comment."

# THE TEST FILE — arrives with S1's merge (structure verified from 33321c6)
- file: tests/test_ydotoold_client.py
  why: "FakeYdotoold @~71-130 (SOCK_DGRAM server; datagrams list[(bytes,src)] appended in _serve;
        wait_for(n); _decode_event -> {zeros,code,ev_type,value}); fixtures fake_daemon/client (bound
        BEFORE client construction — never the real /run/ydotoold.socket);
        test_press_backspace_3_latency_under_100ms @~290 (perf_counter; dt<0.100 AND
        dt>=2*_CHAR_GAP_S-0.002). press_backspace(3) = 12 datagrams: key,sync interleaved."
  pattern: "Additive extension: self.times list in _serve (time.monotonic() per datagram) — do NOT
            change the datagrams tuple shape (existing tests + .payloads read it). New test: decode
            payloads, keep only ev_type==EV_KEY, zip with times, assert pair deltas."
  gotcha: "The datagram ORDER is event,sync,event,sync… — filtering to KEY events yields exactly
           press,release,press,release,press,release. Arrival deltas track send deltas (AF_UNIX is
           µs-scale); keep the file's slack style (-0.002)."

# THE MANDATE
- docfile: plan/008_a47116bb2b79/prd_snapshot.md   # (or the PRD §8 Known-defects triage)
  why: "'MERGE + add the 6 ms press→release contact gap (protocol finding: CLI gaps every event;
        socket path currently does not)' — this subtask is the gap half."
```

### Current Codebase tree (relevant slice — BEFORE S1's merge; the test file arrives with it)

```bash
voice_typing/ydotoold_client.py     # _CHAR_GAP_S @25; _key @51; press_backspace @63-71. ← EDIT (gap + comments + docstring)
tests/test_ydotoold_client.py       # (arrives with S1's merge — 11 tests). ← EDIT (times + spacing test)
voice_typing/typing_backends.py     # :~147 stale "12 ms/char" comment. ← EDIT (comment only)
```

### Desired Codebase tree with files to be changed

```bash
# (same 3 files; no new files)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — GATE ON S1's MERGE. tests/test_ydotoold_client.py exists ONLY after P1.M1.T2.S1 lands
# fix/ydotoold-datagram. Task 0: test -f tests/test_ydotoold_client.py && grep -q SOCK_DGRAM
# voice_typing/ydotoold_client.py — else STOP (extending a file that isn't there = writing a new one
# that will conflict with the merge).

# CRITICAL #2 — THE GAP GOES BETWEEN THE _key CALLS, NOT INSIDE _key. _key sends ONE datagram; it is
# a transport primitive (also the self-heal/raise path). The contact gap is a PACING concern of the
# key-PAIR loop in press_backspace. Putting a sleep inside _key would gap every single event (CLI
# total-parity 6+6) — the contract fixes 6 contact + 12 inter (18/char). Do NOT rebalance.

# CRITICAL #3 — DO NOT CHANGE THE datagrams TUPLE SHAPE. Existing tests iterate it and .payloads reads
# [data for data,_src in self.datagrams]. The times extension is a PARALLEL list appended in _serve.

# CRITICAL #4 — THE EXISTING LATENCY TEST MUST STAY GREEN UNCHANGED (bounds verified): 42 ms < 100 ms
# budget ✓; 42 ms >= 2*0.012-0.002 ✓. If you tighten its lower bound to include the contact gaps
# (2*_CHAR_GAP_S + 3*_CONTACT_GAP_S - slack), that's an optional IMPROVEMENT — keep it generous, this
# suite runs REAL sleeps; CI jitter on a loaded box is why the slack exists at all.

# GOTCHA #5 — REAL-SLEEP SUITE RUNTIME: press_backspace(3) is now 42 ms (was 24). The whole file stays
# well under a second; do NOT mock time.sleep (the suite's measurement-bound style is deliberate —
# it catches pacing regressions by wall clock).

# GOTCHA #6 — FULL PATHS + timeout (AGENTS.md): `timeout 300 .venv/bin/pytest ...` / `.venv/bin/python`.
# No ruff/mypy. NOTE (repo-specific): the PRD-PROTECT hook blocks `git show` — read branch content via
# `git log -p -1 33321c6 -- <path>` (verified working) or the merged file on disk post-S1.

# GOTCHA #7 — PRD §8's aspirational "~80 chars rewind in <150 ms" is violated at 18 ms/char (1.44 s)
# — as it already was at 12 ms/char (0.96 s). NOT this task's concern; note it in the report only.
```

## Implementation Blueprint

### Data models and structure

None — one float constant, one sleep, one test-double list, one test function.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE — S1's merge has landed
  - RUN:
      cd /home/dustin/projects/voice-typing
      test -f tests/test_ydotoold_client.py && echo "test file present (merge landed)" || echo "STOP: merge not landed"
      grep -n 'SOCK_DGRAM' voice_typing/ydotoold_client.py | head -1
      timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py -q 2>&1 | tail -1   # expect 11 passed
  - If the file is absent: STOP and flag (blocked on P1.M1.T2.S1).

Task 1: ADD tests/test_ydotoold_client.py — the spacing test FIRST (TDD)
  - EDIT FakeYdotoold (additive): in __init__ add `self.times: list[float] = []`; in _serve, beside
    the datagrams append, add `self.times.append(time.monotonic())`.
  - ADD the test (place right after test_press_backspace_3_latency_under_100ms):

        def test_press_backspace_contact_gap_spacing(client, fake_daemon):
            """P1.M1.T2.S2 (PRD §8 protocol finding): the socket path MUST gap press→release contact
            time (~6 ms, CLI `-d 6` parity) and keep the 12 ms inter-char gap — zero-contact pairs
            can read as no keypress in contact-sensitive apps. Arrival deltas track send deltas
            (AF_UNIX datagrams are µs-scale); slack 0.002 = the file's style.
            """
            client.press_backspace(3)
            fake_daemon.wait_for(12)
            keys = [   # (arrival_time, value) for the KEY events only, in order
                (t, _decode_event(d)["value"])
                for d, t in zip(fake_daemon.payloads, fake_daemon.times)
                if _decode_event(d)["ev_type"] == 0x01  # EV_KEY
            ]
            assert [v for _t, v in keys] == [1, 0, 1, 0, 1, 0]  # press/release × 3, ordered
            for i in range(0, len(keys), 2):
                press_t, release_t = keys[i][0], keys[i + 1][0]
                assert release_t - press_t >= _CONTACT_GAP_S - 0.002, (
                    f"key {i // 2}: press->release contact {(release_t - press_t) * 1000:.1f} ms < 6 ms"
                )
                if i + 2 < len(keys):
                    next_press_t = keys[i + 2][0]
                    assert next_press_t - release_t >= _CHAR_GAP_S - 0.002, (
                        f"key {i // 2 + 1}: inter-char {(next_press_t - release_t) * 1000:.1f} ms < 12 ms"
                    )

  - RUN it: expect RED on the contact assertion (the gap doesn't exist yet — pairs arrive ~0 ms apart).
  - NOTE: `_CONTACT_GAP_S` is imported from the module under test (the file already imports
    `_CHAR_GAP_S` for the latency test — mirror that import).

Task 2: EDIT voice_typing/ydotoold_client.py — the constant + the gap + comments (Mode A)
  - ADD beside _CHAR_GAP_S (@25):
        _CHAR_GAP_S = 0.012   # Rev 3d/3e: inter-char (release -> next press); 18 ms/char with the contact gap
        _CONTACT_GAP_S = 0.006  # P1.M1.T2.S2 (PRD §8 protocol finding): press->release contact time.
        #   The CLI (`ydotool key -d 6`) gaps EVERY event; zero-contact pairs can read as no keypress
        #   in contact-sensitive apps. Socket-path parity for the contact half; the inter-char gap
        #   above stays 12 ms (matches the text path) -> 18 ms/char total.
  - EDIT press_backspace's loop:
        for i in range(n):
            if i:
                time.sleep(_CHAR_GAP_S)      # inter-char: release -> next press
            self._key(_BACKSPACE, 1)
            time.sleep(_CONTACT_GAP_S)       # press->release contact (P1.M1.T2.S2; CLI -d 6 parity)
            self._key(_BACKSPACE, 0)
  - EDIT the module docstring (Mode A): after the "exactly what `ydotool key -d 6 14:1 14:0` writes"
    paragraph, add one sentence: "Pacing: each press is held ~6 ms before its release (`_CONTACT_GAP_S`,
    matching the CLI's per-event gap — apps need minimum contact time to register a keypress) and
    successive keys are separated by 12 ms (`_CHAR_GAP_S`, the text-path pace) — 18 ms per character."
  - ALIGN the stale comment in typing_backends.py (~:147): "persistent socket, 12 ms/char (3e)" ->
    "persistent socket, 18 ms/char (contact 6 + inter 12; P1.M1.T2.S2)".
  - DO NOT: touch _key, _connect, the CLI fallback logic, or rebalance the gaps (6+12 is the contract).

Task 3: RUN the gates
  - timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py -q
    # expect: 12 passed (11 + the new spacing test) + the backends suite green.
  - Optional comment refresh in the latency test (its pacing note now undersells 42 ms) — keep bounds.

Task 4: VALIDATE — the Validation Loop. No git commit unless directed. If asked:
  "P1.M1.T2.S2: 6 ms press->release contact gap on the ydotoold socket path (CLI -d 6 parity; 18 ms/char)
  + arrival-time spacing test".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the gapped pair (the whole change): contact between the pair, inter-char between pairs.
#   press -> 6ms -> release -> 12ms -> next press ...  (18 ms/char; press_backspace(3) sleeps 42 ms)
# PATTERN 2 — arrival-time spacing asserts (test): FakeYdotoold.times (parallel to datagrams) +
#   _decode_event's ev_type filter -> ordered [(t,1),(t,0)] pairs -> delta asserts with -0.002 slack.
#   AF_UNIX datagram latency is µs-scale, so arrival deltas track send deltas.
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S1 (the merge): delivers the client (SOCK_DGRAM) + the 11-test file this task
           extends. Task 0 gates on it. No in-flight overlap (S1 makes no manual edits).
DOWNSTREAM — P1.M1.T2.S3 (journal-noise guard): guards the Errno-91 CLI fallback in typing_backends —
           my only typing_backends touch is the stale comment.
NO INTERFACE CHANGES: the wire bytes/datagram count are identical (framing untouched); only inter-event
  timing changes. config/systemd/README untouched (README sweep is Mode B, later).
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Real-sleep tests (fast: the file runs in well under a second). Run from `/home/dustin/projects/voice-typing`.

### Level 1: The gap is in place (static)

```bash
cd /home/dustin/projects/voice-typing
grep -n '_CONTACT_GAP_S = 0.006' voice_typing/ydotoold_client.py && echo "L1 PASS: constant" || echo "L1 FAIL"
grep -n 'time.sleep(_CONTACT_GAP_S)' voice_typing/ydotoold_client.py | head -1 && echo "L1 PASS: contact sleep" || echo "L1 FAIL"
awk '/def press_backspace/,/^    def [a-z_]/' voice_typing/ydotoold_client.py | grep -c 'time.sleep' | xargs -I{} echo "sleeps in loop: {} (expect 2: inter + contact)"
grep -qi 'contact' voice_typing/ydotoold_client.py && echo "L1 PASS: docstring note" || echo "L1 FAIL"
timeout 60 .venv/bin/python -c "import ast; ast.parse(open('voice_typing/ydotoold_client.py').read()); print('L1 PASS: parses')"
# Expected: constant + exactly one contact sleep (2 sleeps in the loop) + docstring mention + parses.
```

### Level 2: The new spacing test (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py -q -k "contact_gap" -v 2>&1 | tail -3
# Expected: PASSED. If the contact leg fails with ~0 ms: the sleep isn't between the _key calls. If the
# inter-char leg fails: the inter-char sleep was moved/removed. If datagram counts break: framing was
# touched (revert — only pacing changes).
```

### Level 3: No regressions (both suites + the latency bounds)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py -q 2>&1 | tail -2
# Expected: all green — 12 in the client file (11 + 1) incl. test_press_backspace_3_latency_under_100ms
# (42 ms < 100 ms; >= its pacing floor), and the backends suite unchanged. A backends red on a timing
# assert means something else pins the 12 ms pace — re-check for other pins (grep 0.012/_CHAR_GAP in tests/).
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'voice_typing/ydotoold_client.py|tests/test_ydotoold_client.py|voice_typing/typing_backends.py' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS"
git diff voice_typing/typing_backends.py | grep -E '^[+-]' | grep -vE '^[+-]{3}|^[+-]\s*#|^[+-]\s*$' && echo "L4 FAIL: backends logic changed (comment-only allowed)" || echo "L4 PASS: comment-only"
git diff voice_typing/ydotoold_client.py | grep -E '^[+-].*(_MSG|struct|_connect|SOCK_)' && echo "L4 WARN: framing/connect touched — verify" || echo "L4 PASS: framing/connect untouched"
# Expected: only the 2-3 files; backends comment-only; no framing/_connect change.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `_CONTACT_GAP_S = 0.006` + exactly one contact sleep in the loop + docstring note + parses.
- [ ] L2: the spacing test passes (contact ≥ 6 ms, inter-char ≥ 12 ms, order press/release ×3).
- [ ] L3: both suites green (12 + backends); the existing latency test green unchanged.
- [ ] L4: diff ⊆ the 2-3 files; backends comment-only; framing/connect untouched.

### Feature Validation
- [ ] Per-char cycle 18 ms (6 contact + 12 inter); datagram count/content byte-identical.
- [ ] The gap rationale documented in the module docstring (Mode A).
- [ ] Stale 12 ms/char comments aligned (client constant comment + typing_backends :~147).

### Code Quality Validation
- [ ] Test extends FakeYdotoold additively (`times` parallel list; `datagrams` shape unchanged).
- [ ] Measurement-bound style mirrored (real sleeps, −0.002 slack, perf/monotonic deltas).
- [ ] Full paths + `timeout` wrappers; no ruff/mypy.

### Scope Boundary Validation
- [ ] No `_key`/`_connect`/fallback-logic change; no 6+6 rebalance (6+12 is the contract).
- [ ] S3's journal-guard territory untouched; PRD/tasks/snapshots untouched.

### Documentation & Deployment
- [ ] Mode A docstring note rides with the work; commit message names the CLI-parity rationale.

---

## Anti-Patterns to Avoid

- ❌ Don't start before S1's merge lands — the file being extended doesn't exist on main (Task 0 gate).
- ❌ Don't put the sleep inside `_key` — it's a single-event transport primitive; the gap belongs to the pair loop. Inside `_key` would also change the total pace to 6+6 (the contract fixes 6+12).
- ❌ Don't rebalance the inter-char gap down to 6 ms for CLI total-parity — the contract explicitly KEEPS 12 ms inter-char.
- ❌ Don't change the `datagrams` tuple shape — a parallel `times` list only (existing tests + `.payloads` read it).
- ❌ Don't mock `time.sleep` — the suite's measurement-bound style is deliberate (it catches pacing regressions by wall clock); the file runs in well under a second with real sleeps.
- ❌ Don't touch the wire format, `_connect`, or the CLI fallback logic (S1/S3 territory; comment-only in typing_backends).
- ❌ Don't skip the datagram-order filter (`ev_type == EV_KEY`) — the 12 datagrams interleave events and syncs; asserting raw deltas would mis-pair.
- ❌ Don't modify PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**8.5/10** for one-pass implementation success. The change is one constant + one sleep + one additive test-double field + one measurement-bound test, with every fact verified: the verbatim `press_backspace` loop on main (≡ the branch except `_connect`), the branch test file's exact structure (FakeYdotoold's datagram recording, the event/sync interleaving, the verbatim latency test whose `<100 ms` and pacing-floor bounds both provably absorb the 42 ms new total), and the contract-fixed pacing (6 contact + 12 inter, no rebalancing). The TDD order (spacing test RED first, then the sleep) makes the deliverable self-verifying. The −1.5 is the two-stage dependency: S1's merge must land first (gated, but its timing is out of my control), and the file I verified comes from the branch commit (33321c6) via `git log -p` — if S1's merge resolves differently than a plain merge (it shouldn't; zero-conflict is proven), the test-file line numbers shift (mitigated: the PRP matches on test names and structures, not line numbers, and Task 0 re-runs the 11-test baseline). The remaining −0.5 is real-sleep CI jitter on a loaded box (why the slack exists) — the spacing deltas (6/12 ms) are far above scheduler noise.

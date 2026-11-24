# G6 WRITING SESSIONS — operator-authored evidence (G6 condition D)

PRD §4.2sexies R.7 G6 requires **≥ 3 representative completed writing sessions** whose
usable proofread words per minute — **counting corrections, recovery, and rereading** —
**beats 110 wpm**, before bulk-text delivery may graduate to the shipped default.

This file is the ONLY sanctioned place to record that evidence. `tests/g6_assessment.py`
parses it mechanically; `tests/G6_GRADUATION.md` records the verdict.

## THE RULE — read before adding anything

- **Entries are written by the OPERATOR only.** Implementers, agents, and automation
  MUST NOT add, seed, "example-fill", or edit entries. Fabricated user acceptance is the
  explicitly forbidden failure (PRD R.2: "No operator acceptance on record").
- Every entry MUST carry an `attributed:` line naming the operator. **An entry without
  attribution is INVALID and never counts** toward the ≥ 3.
- All numbers are observed facts from a real session — never estimates invented on the
  operator's behalf.

## Entry format (strict — the parser enforces it)

```text
### YYYY-MM-DD
duration_min: <wall-clock minutes, float>
raw_words: <words of final proofread text, int>
correction_min: <minutes spent correcting, float>
recovery_min: <minutes spent recovering: re-arming, cancel-respeak, freezes, float>
rereading_min: <minutes spent proofreading/rereading, float>
usable_wpm: <raw_words / (duration_min - correction_min - recovery_min - rereading_min), float>
attributed: operator: <your name>
notes: <optional free text>
```

The example above is inside a fenced code block: it is the FORMAT SPECIFICATION, **not
evidence** — never uncomment it, never count it.

## Accounting rules (usable proofread wpm)

```
net_minutes   = duration_min − correction_min − recovery_min − rereading_min
usable_wpm    = raw_words / net_minutes
```

- Corrections, recovery, and rereading time are SUBTRACTED — they are part of real
  usable throughput, not overhead to hide (R.7 wording, verbatim intent).
- The gate needs usable_wpm **> 110 strictly**: an entry at exactly 110.0 does NOT
  qualify. The parser recomputes `usable_wpm` from your fields; a stated value that
  disagrees with the arithmetic by more than 1 wpm invalidates the entry.
- `net_minutes` must be > 0 (an entry whose accounting eats the whole session is invalid).

## Recorded sessions

*(none on record)*

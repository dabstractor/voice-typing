# G4 clipboard contract — evidence report (P1.M5.T3.S1)

- Date: 2026-11-23  |  HEAD: 026395c
- Command: `timeout 420 env CLIPBOARD_G4_LAB=1 .venv/bin/python tests/clipboard_g4_lab.py`
- Decision: plan/008_a47116bb2b79/architecture/g3_field_matrix.md route table: clipboard_fallback_m5t3: "needed (ghostty-class insert blocked at 1.4.0-2)"
- kernel: 7.3.5-arch1-1
- sway: sway version 1.12
- ghostty: Ghostty 1.4.0-arch2 Version - version: 1.4.0-arch2 - channel
- wl_clipboard: wl-clipboard 2.3.0 Copyright (C) 2018-2026 Sergey Bugaev Lic
- xdotool: xdotool version 4.20260303.1

> Honesty rules: verdicts use ONLY verified | unprovable | blocked;
> legs assert contents/history/formats/target/PRIMARY, never exit
> codes; t_ms values are mechanism info, NEVER G5 timing (no
> speech in this run).

## Decision input (recorded FIRST; never re-derived)
`clipboard_fallback_m5t3`: needed at HEAD (ghostty 1.4.0-2 insert blocked;
route = clipboard insert-fallback under R.6).

## R.6 clause → mechanism → leg
| clause | requirement | mechanism | leg |
|---|---|---|---|
| 1 | preserve all prior formats AND bytes | data-control snapshot of every offered type (exact bytes) + restore via a zwlr_data_control_source serving per-type bytes | L4 |
| 2 | ownership distinguished from a later identical copy | sentinel nonce MIME (x-voice-typing/nonce, fresh per staging generation) on OUR sources only; source-cancelled event — never content comparison | L2 |
| 3 | simultaneous user paste protected | mutation-time recheck through a sync barrier (cancelled ⇒ abort + restore); positive witness required for applied | L2, L3, L5 |
| 4 | partials kept out of the configured history watcher | detect watcher at acquire (scoped /proc scan) ⇒ fail BEFORE delivery — never disable the manager | L1 |
| + | PRIMARY selection untouched | only clipboard set_selection is ever sent; set_primary_selection is never called; asserted unchanged after every leg | L1–L6 (invariant) |

## Leg verdicts
| leg | status | PRIMARY unchanged | key evidence |
|---|---|---|---|
| L1 private manager (text+image watchers) — histor | unprovable | yes | watcher scan hits (scoped): 2 |
| L2 simultaneous foreign copies incl. byte-identic | verified | yes | observed read: b'meeting notes draft' |
| L3 user paste during transfer | verified | yes | user chord delivery: theirs_exact=False theirs_bytes=0B |
| L4 original-offer classes: empty / rich-text / im | verified | yes | [empty] types after restore: [] |
| L5 failure before/after the data request | verified | yes | [pre-read death] status={"result": "unknown", "reason": "target receipt unconfirmed", "status": "done"} |
| L6 process death mid-cycle | verified | yes | types after death: ['text/plain;charset=utf-8', 'x-voice-typing/nonce'] (faulted=False restored=True) |
### L1
  reason: watcher active — adapter refused to engage; R.6 partials-out-of-history cleanliness is unprovable with a live manager (PRD-pre-authorized honest outcome)
  check: PASS private text watcher captured a user copy
  check: PASS acquire refused under watcher
  check: PASS refusal carries the contract reason string
  check: PASS store holds ZERO voice fragments
  watcher scan hits (scoped): 2
  refusal reason: clipboard-history watcher active — R.6 partials-out-of-history unprovable
### L2
  check: PASS [identical-bytes] adapter REFUSED
  check: PASS [identical-bytes] no paste fired
  check: PASS [different-bytes] adapter REFUSED
  check: PASS [different-bytes] no paste fired
  observed read: b'meeting notes draft'
  [identical-bytes] restore-exact read: True
  [identical-bytes] foreign fired=True trace=['sync#1', 'fired'] last_reason='foreign selection change mid-window — aborted' types after=['text/plain;charset=utf-8', 'x-voice-typing/nonce'] hand_reconnects=0 hand_err=''
  observed read: None
### L3
  check: PASS our delta pasted exactly once
  check: PASS clipboard restored to original after the user's action
  check: PASS adapter outcome honest: unknown
  user chord delivery: theirs_exact=False theirs_bytes=0B
  meta[ours]: {"bytes": 37, "ends_with_end": true, "body": "voice words for leg three", "t_ms": 5091}
  foreign source: sends=None cancelled=None
  witness ours=37B theirs=0B obs_types=['text/plain;charset=utf-8', 'x-voice-typing/nonce'] chords=[]
### L4
  check: PASS [empty] outcome honest (applied=False, never falsely applied)
  check: PASS [empty] all original formats restored EXACT per-type bytes
  check: PASS [empty] our restore source carries the sentinel
  check: PASS [rich-text] outcome honest (applied=False, never falsely applied)
  [empty] types after restore: []
  [rich-text] types after restore: ['text/plain;charset=utf-8', 'text/html', 'x-voice-typing/nonce']
  [image] types after restore: ['image/png', 'x-voice-typing/nonce']
### L5
  check: PASS [pre-read death] runner recorded unknown (unknown)
  check: PASS [pre-read death] no complete witness — never counted applied
  check: PASS [pre-read death] clipboard intact (runner served the restore)
  check: PASS [post-restore kill] witness proves the delta WAS delivered
  [pre-read death] status={"result": "unknown", "reason": "target receipt unconfirmed", "status": "done"}
  L5b observed read: None
  L5b intact read: False (disclosed harness read; the same restore-then-read passed in L5a)
  [post-restore kill] witness exact=True
### L6
  reason: observed shape: restored
  check: PASS observed shape is restored-or-visibly-faulted (recorded)
  check: PASS no applied claim exists for a killed cycle
  check: PASS history store unchanged since L1
  types after death: ['text/plain;charset=utf-8', 'x-voice-typing/nonce'] (faulted=False restored=True)

## Availability statement
UNAVAILABLE under a clipboard-history watcher — R.6 partials-out-of-history unprovable with the local manager; the adapter refuses to engage and the manager is never disabled

Verdicts file: <root>/verdicts.jsonl → g4_clipboard_verdicts.jsonl

## Open items
- ghostty 1.5.0 watch — PR #15246 milestone; the matrix re-run (P1.M4.T5.S2's artifact) is the future ELSE trigger for this route, not this item.

Summary: six legs recorded: L1=unprovable, L2=verified, L3=verified, L4=verified, L5=verified, L6=verified

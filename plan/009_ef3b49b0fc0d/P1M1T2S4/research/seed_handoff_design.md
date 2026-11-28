# Research Note — P1.M1.T2.S4: Hand off the seed only on the first accepted final

Source at HEAD `de29942` (S1 landed). S2 (prime IPC) and S3 (fenced start seam) are in flight; their
PRPs are treated as contracts. Navigate by symbol — line numbers shift under the parallel work.

## 1. What exists today (daemon.py, read verbatim)

| site | line | behaviour |
|---|---|---|
| `_context_prompt_active` init | 912 | ready-payload capability flag (None/True/False); gates every push |
| `_rev1_committed` | 921, 1567 | Rev 1 hatch accumulator; reset in `_arm` @1740 |
| `on_final` entry | 1364 | listening gate (outside `_on_final_lock`), then under `_on_final_lock`: cancel-suppression window (dropped finals `return` @~1476 before clean) |
| `cleaned = textproc.clean(...)` / rejection | ~1480-1535 | `if not cleaned:` → `note_rejected`, streaming freeze + `reset_boundary`, WARNING, notify, `return`. NO prompt push on this path |
| acceptance point | ~1536 | `self._final_pending = False` — first statement after acceptance, BEFORE the streaming/Rev 1 typing branches |
| streaming branch | ~1546 | `self._stream.commit(cleaned)` (fail-safe freeze inside) |
| Rev 1 branch | ~1548-1572 | `backend.type_text`, then `_rev1_committed` append |
| record/latency/log | 1574-1605 | `record_final`, `note_final`, latency line with `text=%r` (dictated text only) |
| `_refresh_context_prompt()` calls | 1619, 1624 | after commit, both modes |
| `_clear_context_prompt` | 1666 | best-effort `set_prompt("")`, gated config AND `_context_prompt_active is True` |
| `_arm` | 1692-1760 | `reset_session`, `_rev1_committed = ""` @1740, `_clear_context_prompt()` @1741 (S3 makes this policy), `set_microphone(True)` @1749 |
| `_refresh_context_prompt` | 2078-2127 | gates: `cfg.asr.context_prompt` and `_context_prompt_active is True`; source = `_stream.committed` (streaming) / `_rev1_committed` (Rev 1); `rolling_context_prompt(source)` → `host.set_prompt(text)`; debug log = word COUNT only |

No `_seed*` state exists in the tree yet (`grep -n 'seed' daemon.py` → only device-cache "seed"
comments). S3 will add `_seed_active`, `_arming`, `_arm_seq`, `_start_fenced`, `start_with_seed`.

## 2. The three gaps this task closes

1. **Config-off leak.** `_refresh_context_prompt` returns early when `cfg.asr.context_prompt` is
   false. A seed arm (S3) installs the seed regardless of that key, so with the rolling prompt
   disabled the seed would condition EVERY decode of the whole session and never be replaced.
2. **Source is the display engine, not acceptance.** The only replacement path sources from
   `StreamingOutput.committed`, which (a) does not exist on the native path T4.S4 is about to add
   (native finals bypass generic output), and (b) can absorb an UNACCEPTED frozen tail
   (`streaming.py:362-384`: "While FROZEN, the tail is first ABSORBED into committed").
3. **No explicit state.** Nothing records "a seed is resident and awaits its handoff", so nothing
   can guarantee the handoff happens exactly once, on acceptance only, independent of typing.

## 3. Design (settled)

State (in `__init__`, beside `_rev1_committed`):

```python
self._seed_handoff_pending = False   # a confirmed seed is resident AND not yet replaced (P1.M1.T2.S4)
self._seed_handoff_done = False      # this armed session replaced its seed via the accumulator
self._session_accepted: list[str] = []   # THIS session's accepted finals only — never seed text
```

- `_seed_handoff_pending = True` is set in exactly ONE place outside this task's methods: S3's
  `_start_fenced` revalidation, beside its `self._seed_active = True` (applied seed). One line.
- `_arm` (beside `self._rev1_committed = ""`): `self._session_accepted = []`;
  `self._seed_handoff_done = False`. Do NOT touch `_seed_handoff_pending` there (the seed arm sets
  it in the seam BEFORE calling the arm body).
- `_seed_active` (S3's) is deliberately left True after the handoff: the child then holds this
  session's rolling text, and the next arm must still treat the resident prompt as "something to
  confirmed-clear or re-prime". Never write `_seed_active` from this task.

New method `_handoff_context_prompt(accepted: str) -> None` (never raises; called under
`_on_final_lock`, which is NOT `_lock` — `set_prompt` is a non-blocking queue put, S2 contract):

```python
self._session_accepted.append(accepted)
if not self._seed_handoff_pending:
    return
self._seed_handoff_pending = False
self._seed_handoff_done = True
if self._cfg.asr.context_prompt and self._context_prompt_active is True:
    text = prompt_engine.rolling_context_prompt(" ".join(self._session_accepted))
else:
    text = ""            # rolling disabled/degraded → the replacement is a known EMPTY prompt
setter = getattr(self._host, "set_prompt", None)
if callable(setter):
    setter(text)
    logger.debug("context-prompt: seed handed off to rolling context (%d words)", len(text.split()))
else:
    logger.debug("context-prompt handoff skipped: host has no set_prompt seam")
```

`rolling_context_prompt("First one. second")` → `"second"`; `("Hello world.")` → `""` (ends on a
boundary = new sentence, context-free). Both are the normal rolling semantics.

Call site: `on_final`, immediately AFTER `self._utterance_finalized = True` (the acceptance point)
and BEFORE `if self._streaming_now():`. So it runs before any typing, before commit, before
record/latency — typing failure, a frozen commit, a missing backend, or a native early-return
above it cannot skip it.

`_refresh_context_prompt` gains ONE branch at the top of the source selection:

```python
if self._seed_handoff_done:
    source = " ".join(self._session_accepted)   # P1.M1.T2.S4: accepted-only accumulator
elif self._streaming_now():
    source = self._stream.committed
else:
    source = self._rev1_committed
```

Its gates and the push stay byte-identical. Non-seeded sessions never set `_seed_handoff_done` →
identical behaviour (`host.prompts == ["", "second"]` in the existing test still holds).

## 4. Paths the seed must NOT reach — verified untouched

Displayed text / spacing: handoff touches no backend, no `StreamingOutput`. Log/latency: the
latency line logs `cleaned` only; handoff logs a word count. Status: `status_snapshot` /
`_context_prompt_label` unchanged. Feedback: unchanged. Recovery: `note_final` unchanged — the
accumulator is a separate list and is NOT passed to `SessionRecovery`. Next session: `_arm`
resets the accumulator; the child's resident prompt is handled by S3's next-arm policy
(`_seed_active` stays True → confirmed clear or re-prime). Cancel: suppressed finals `return`
before `clean` → never accepted → no handoff, seed retained (say it again). Post-disarm final:
dropped by the listening gate. Unload/dead child: `_host` is None/replaced → setter no-op;
a respawned child starts prompt-free and the next arm re-primes.

## 5. Tests to mirror (tests/test_daemon.py)

- `_PromptRecordingHost(_FakeHost)` @5028 — records `set_prompt` in `self.prompts`.
- `test_on_final_streaming_pushes_context_prompt_to_host` @5231 — the construction idiom:
  `VoiceTypingConfig()`, host with `device["context_prompt"] = True`, `host.spawn()`,
  `_make_daemon(cfg=cfg, recorder_host=host)`, `d.start()`, `_on_partial`, `on_final`;
  asserts `host.prompts`.
- `_make_daemon` @903 (pre-built host, legacy arm path), `_make_lazy_daemon` @3610.
- `textproc.clean` rejects: `< min_chars` (default 2) and blocklist exact matches
  (`"thank you."`, `"you"`, `"bye."`, … case-insensitive, trailing punct stripped).

## 6. Upstream observation (for the implementer to VERIFY, not fix here)

S3's PRP policy says a plain arm with no prior seed and a confirmed channel skips the clear
("prompt provably None"). That holds after a cold load or a confirmed clear, but NOT after an
ordinary rolling session (the child still holds the last pushed rolling text). S3's fenced
seam should clear on every warm plain re-arm. S4 must not edit that policy; it only guarantees
its own case (`_seed_active` stays True after handoff). If the implementer confirms the gap with
a quick test on the landed S3, report it in the task result for the orchestrator (S3/S5 follow-up).

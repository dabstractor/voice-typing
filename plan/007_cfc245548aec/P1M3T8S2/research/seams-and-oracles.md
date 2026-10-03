# Research Notes — P1.M3.T8.S2 (T8 asserts c/e/f/g)

Date: session of PRP creation. Source: direct code reads (no re-verification needed since).

## 1. What exists (S1, landed)

`tests/test_streaming.py` (939 lines): session-scoped production-built recorder (small.en,
`use_microphone=False`, fed via `feed_audio` at real-time pacing), `RecordingTypingBackend`
(screen model + timestamped events), `RecordingPromptedExecutor`, `TimestampedFeedback`,
`StreamingHarness` (daemon.on_final streaming-branch extraction), asserts a/b/d. The module
docstring reserves c/e/f/g for S2 and mandates extending the same file without loosening
fixtures.

## 2. Production seams to mirror (daemon.py line anchors, current tree)

| Seam | Lines | Behavior the harness must replicate |
|---|---|---|
| `on_final` gate | 1116-1130 | listening gate first, outside any lock |
| cancel suppression window | 1131-1140 | `_cancel_suppress_final` drops racing finals until the marked sentinel is consumed |
| rejected-final branch | 1146-1165 | streaming: `freeze(..., session=True)` + `reset_boundary()` + early return |
| commit + boundary + prompt refresh | 1166-1256 | (already mirrored in S1's harness) |
| `_pending_tail_len` | 1421-1435 | 0 when not listening |
| `_reset_stream_after_cancel` | 1436-1447 | `reset_after_cancel()` + `feedback.update_partial("")` |
| `note_user_keypress` | 1448-1469 | gate on listening → `stream.note_user_keypress()` |
| `_on_cancel_backspace` | 1470-1480 | listener entry: `cancel()` when listening |
| `_freeze_stranded_tail` | 1532-1554 | streaming gate + pending-tail gate + `freeze(reason, session=True)` |
| `cancel` | 1603-1636 | n = max(tail−1, 0) via **backend directly**; host.cancel() only if text in flight; reset stream after |
| `_drain_timeout` | 1671-1693 | freeze BEFORE `_safe_abort()`; `_DRAIN_TIMEOUT_S = 5.0` (L149) — harness forces directly |

## 3. Key semantic findings

- **Physical Backspace is invisible to the engine.** The evdev listener observes it; the
  daemon compensates by subtraction because `StreamingOutput.tail` still holds the full
  fragment when `cancel()` computes n. Simulated screen needs the test to play the user:
  `backend.press_backspace(1)` before the cancel seam → screen returns to exactly
  `committed` (1 physical + (len−1) compensation).
- **Post-cancel suppression timeline**: `reset_after_cancel()` sets `_suppressed`; it
  clears only in `commit()`/`reset_boundary()` — i.e., at the NEXT utterance's final. So
  the utterance spoken right after a cancel types once at commit (partials mirror-only),
  and live partial typing resumes for the utterance after that. Assert, don't fight.
- **Frozen-absorb commits type nothing** — no rewind, no retype, **no trailing space**
  (streaming.py commit() frozen path). `_assert_commit_invariants` check #2 is therefore
  false on frozen sessions.
- **abort() drops the in-flight utterance**: text() returns without cb firing → no
  raw_final, no commit. Recorder stays usable (abort only interrupts the current
  transcription) — proven in-test by the follow-up utterance.
- **Freeze classes**: per-utterance (user keypress) lifted by `reset_boundary()`; session
  (rejected final, stranded tail, backend failure) survives boundaries, cleared only by
  `reset_session()` (= fresh arm; `harness.reset()` rebuilds the engine).

## 4. Oracle determinism analysis (assert c)

espeak/model punctuation is nondeterministic (S1 observed small.en adding a period to
PAUSE_A in one run, dropping multi's periods in another). `apply_streaming_guards`
(textproc.py L82-134) is deterministic **given its context input**:
- context empty or ends `.!?` → fragment verbatim (case preserved, period kept);
- else (mid-sentence) → first cased char lowercased + one trailing `.` stripped.

Therefore the E2E oracle must be conditional on the ENGINE's committed truth at each
commit (S1's `committed_state_at` helper), and the "mid-sentence branch exercised ≥1"
requirement needs the bounded re-feed retry (same discipline as test_b's revising-commit
retry). utt_multi/punct cannot substitute: their reference sentences all end with
terminators, so their commits take the sentence-start branch.

## 5. Cancel racing-final mirror (in-process)

Production uses a marked sentinel final consumed via `host.consume_cancel_mark()`. In-process
there is no host: mirror with a text()-generation counter (bumped per `rec.text()` call in
the consume wrapper; `cancel()` records the generation; `on_final` drops finals while the
generation is unchanged; the next `rec.text()` entry clears the window). This is the
recommended design; a simpler bounded drop-window is acceptable if the counter proves noisy.

## 6. Unit coverage already present (do not duplicate)

- `tests/test_streaming_freeze.py`: freeze classes/promotion/idempotence, backend-failure
  session freezes, note_user_keypress semantics + frozen-commit absorb + boundary lift,
  session-frozen late commit/partials/disarm.
- `tests/test_streaming_commit.py`: commit extend/revise/fresh/no-rate-limit, frozen
  no-touch absorb, append_space=False, failure freezes.
- `tests/test_key_listener.py`: evdev parser + KeyListener with synthetic events
  (PRD T8 tail note — real-Backspace stays in the T5 manual smoke).
- `tests/test_daemon.py`: daemon wiring incl. cancel/drain/freeze seams.

## 7. Tooling facts

- Run heavy suite: `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v`
  (two-timeout rule from AGENTS.md; never foreground the daemon — not needed here).
- WAVs: `./tests/make_test_audio.sh` → `tests/out/utt_{simple,pause,multi,punct}.wav`.
- pyproject pins pytest>=9.1.1; no ruff/mypy config observed → validation ladder is
  pytest-based (collect-only purity + fast sweep + heavy run + determinism re-run).

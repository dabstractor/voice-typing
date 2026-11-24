# PRP — P1.M6.T2.S2: Session recovery memory (R.6) — daemon-side recovery store, both delivery modes

## Goal

**Feature Goal**: A pure in-memory daemon-side recovery store that holds the **last nonempty
arm→disarm session** — the filter-**accepted final per utterance (exactly once each)** plus the
**last visible/recognized unfinished tail** — with every R.6 exclusion rule enforced *by hook
placement* (late finals, deliberate cancels, rejected finals excluded; a rejected final retains
only the shown tail), the ≤**2 sessions × 1 MiB UTF-8** cap with newest-complete-text-that-fits
truncation reporting, and clearing at daemon exit. It works in **BOTH delivery modes**
(`stream-edit` and `bulk-text`), keeps **no crash persistence and adds no transcript-bearing
logs** (bulk/session log lines carry counts and times only), and never touches state.json.

**Deliverable** (1 CREATE + 1 MODIFY + 1 CREATE):
1. `voice_typing/session_recovery.py` — NEW: `SessionRecovery` store + `CompletedSession`
   frozen dataclass (pure python, own `threading.Lock`, never calls back into the daemon).
2. `voice_typing/daemon.py` — MODIFY: 8 narrow hook insertions (ctor field, `_arm`, `_disarm`,
   `on_final` accepted + rejected sites, `_on_partial`, legacy `cancel`, S1's
   `_bulk_handle_final`/`_bulk_handle_partial`/`_bulk_cancel`, `request_shutdown`), a
   `session_snapshot()` accessor (the S3 contract point), and a module-docstring note.
3. `tests/test_session_recovery.py` — NEW: store-level unit tests for **every exclusion rule**
   + cap/eviction, plus daemon-level wiring tests (fake host, both modes; no CUDA, no
   subprocess, no live desktop).

**Success Definition**:
- (a) Arm → speak (partials) → accepted finals → disarm: the completed session's `text()` is the
  accepted finals joined with single spaces plus the unfinished tail appended with one space —
  no trailing space, no added newline — with each final present **exactly once**.
- (b) A rejected final (blocklist/min_chars) adds NO final and the pending tail is retained.
- (c) A deliberate cancel (Backspace/`voicectl cancel` — both entry points) contributes
  neither the cancelled tail nor its racing final; a late post-disarm final is not recorded.
- (d) An empty or failed arm→disarm produces no completed session — the previous completed
  session survives untouched.
- (e) Store holds ≤2 completed sessions, ≤1 MiB UTF-8 each; on overflow the newest complete
  text that fits is kept, whole oldest items dropped first, a lone oversized item hard-truncated
  at a codepoint boundary, `truncated=True` reported.
- (f) `request_shutdown()` clears the store (daemon exit = SIGTERM + quit funnel).
- (g) Default mode (`stream-edit`) behavior byte-identical: the G1 watch set reports identical
  numbers before/after; S1's `tests/test_bulk_dispatch.py` stays green.
- (h) No new config keys, no state.json/session-text writes, no ctl.py changes, no socket
  commands (S3 owns `voicectl session`); new log lines carry counts/times only.

## User Persona

**Target User**: internal — three consumers: (1) the **operator** who disarmed mid-thought and
wants the words back (surfaced by P1.M6.T2.S3 `voicectl session [--copy]`); (2) **P1.M6.T2.S3**
— it reads this item's `daemon.session_snapshot()` for the control-socket reply; (3) future
audit/G5 work — the store's counters (finals/tail_chars/bytes/truncated) are the evidence shape.

**Use Case**: arm → dictate three sentences (three accepted finals) → keep talking (partials
typed) → press stop mid-utterance → the disarm closes the session: three finals + the visible
tail. The next arm is a pocket of silence (auto-stop, nothing said) → empty session discarded,
the previous one still answers `voicectl session`. Daemon restarts → store empty (no crash
persistence, by design).

**Pain Points Addressed**: (1) today a mid-thought disarm loses the tail words permanently —
no recovery surface exists anywhere in the codebase (verified: no session_recovery/`voicectl
session` code); (2) R.5/R.6 forbid transcript-bearing logs and state-file text, so the recovery
buffer must be a dedicated memory structure with its own exclusion discipline, not a log scrape.

## Why

- **PRD §4.2sexies R.6** (the clause this item implements, verbatim contract): "Recovery (both
  delivery modes): daemon memory holds the last nonempty arm→disarm session — accepted final
  per utterance plus the last visible/recognized unfinished tail, exactly once each; a rejected
  final retains only the shown tail; deliberate cancels and late finals are excluded; the
  previous completed session survives empty or failed arms; at most two sessions × 1 MiB UTF-8
  (on overflow keep the newest complete text that fits and report truncation); cleared at daemon
  exit; no crash persistence, audio archive, or new transcript-bearing logs."
- **Everything upstream is landed/contract-stable**: the dispatch wiring this item hooks into is
  P1.M6.T2.S1's (INPUT; its PRP is the contract — the `_bulk_handle_final`/`_bulk_handle_partial`/
  `_bulk_cancel` bodies and lifecycle are assumed exactly as specified there), the controller's
  three-value accessors (`latest_recognized`/`accepted_final`/`confirmed_visible`) exist in
  `voice_typing/bulk_controller.py`, and the stream-edit funnel sites (`on_final` →
  `record_final`, `_on_partial` → `_stream.on_partial`, `cancel` →
  `_reset_stream_after_cancel`) are stable, heavily-tested code.
- **The exclusion rules are already enforced by existing gates** — the listening gate, the
  cancel-suppression window, and the `if not cleaned` block all run BEFORE the sites this item
  hooks. The store inherits correctness by placement instead of duplicating gate logic.

## What

A new pure-python store fed by narrow daemon hooks, plus the daemon wiring in both modes:

1. **Store** (`voice_typing/session_recovery.py`): `SessionRecovery` with
   `open_session()`, `note_final(text, key=None)` (closed-set dedupe on `key`),
   `note_rejected()` (content no-op — pending tail retained), `note_tail(text)` (overwrite),
   `note_cancel()` (clear pending tail), `close_session()` (discard empty; cap; append to
   ≤2-deque), `latest_completed() -> CompletedSession | None`, `clear()`.
   `CompletedSession` (frozen): `finals: tuple[str, ...]`, `tail: str`, `truncated: bool`,
   `ended_monotonic: float`, `finals_dropped: int`; `text()` = `" ".join(finals + [tail])`
   (no trailing space, no newline); `byte_len()` = UTF-8 size of `text()`.
2. **Daemon wiring** (all insertions AFTER existing gates; 1–3 lines each):
   ctor field; `_arm` → `open_session()`; `_disarm` → `close_session()` before the
   `stream_reset` block; `on_final` → `note_final(cleaned)` after `record_final(cleaned)` and
   `note_rejected()` at the top of the `if not cleaned:` block; `_on_partial` →
   `note_tail(self._stream.tail)` after `self._stream.on_partial(text)`; legacy `cancel` →
   `note_cancel()` after `_reset_stream_after_cancel()`; S1's bulk paths → `note_tail(text)` /
   `note_final(cleaned, key=(gen, uid))` / `note_rejected()` / `note_cancel()` inside the
   corresponding `_bulk_*` bodies; `request_shutdown` → `clear()`.
   New accessor `session_snapshot() -> dict | None` for S3 (text + truncated + counts + ts).
3. **Cap discipline**: `_MAX_SESSIONS = 2`, `_MAX_SESSION_BYTES = 1 << 20` (code constants, NOT
   config). At close, while `byte_len() > cap`: drop the oldest final; if a single remaining
   item alone exceeds the cap, slice it at a codepoint boundary to fit; set `truncated=True`
   and count `finals_dropped`.
4. **Log discipline**: one INFO line at close — `session recovery: session completed finals=%d
   tail_chars=%d bytes=%d truncated=%d store=%d` — counts/times only, NEVER text.

### Success Criteria

- [ ] (a)–(h) above hold, each pinned by at least one named test in `tests/test_session_recovery.py`.
- [ ] Store-level tests cover EVERY exclusion rule of the contract: exactly-once, rejected-final
      tail retention, cancel exclusion, late-final exclusion, empty/failed-arm survival, 2×1 MiB
      cap + truncation reporting, clear-at-exit.
- [ ] Daemon-level tests pin the hook placement in both modes (incl. the suppression-window and
      listening-gate precedents).
- [ ] G1 watch set + S1's suite green/identical; no new config/state-file/ctl surface.

## All Needed Context

### Context Completeness Check

_Pass._ The exact hook sites (current-HEAD anchors + the S1 drift warning), the S1 contract
bodies this item hooks inside, the store design with the exclusion-rule→gate mapping, the
test-double patterns, and executable validation commands are all below. S1 lands first and adds
~250 lines to `daemon.py` — every cite below is re-verified live in Task 0 before editing.

### Documentation & References

```yaml
# MUST READ — the parallel-predecessor CONTRACT (assume it landed exactly as specified).
- file: plan/008_a47116bb2b79/P1M6T2S1/PRP.md
  why: "The bulk-path bodies S2 hooks INSIDE: _bulk_handle_final (identity gate → rejected
        branch → ctrl.on_final → record_final), _bulk_handle_partial (identity gate →
        ctrl.on_partial → update_partial), _bulk_cancel (ctrl.cancel out of lock → shared
        under-lock recognition cancel + _reset_stream_after_cancel), the lifecycle (_arm gen
        bumps, _disarm funnel, acquire-failure keeps recording armed), and the test template
        tests/test_bulk_dispatch.py (bulk cfg triple, FakeBundle, fake host w/ relay_identity)."
  critical: "S1's anti-pattern list explicitly forbids IT from adding session/recovery logic —
             the seam is this item's. Do not duplicate or rewrite S1's branches; insert 1-3
             lines inside them."

# MUST READ — this item's verified research (site map, gate mapping, decisions D1-D8).
- file: plan/008_a47116bb2b79/P1M6T2S2/research/session_recovery_design.md
  why: "§2 the daemon site map (current-HEAD anchors for all 8 hooks). §3 the exclusion-rule →
        existing-gate mapping (the design's core claim: hooks sit AFTER the listening gate, the
        suppression window, and the `if not cleaned` block, so exclusions are inherited).
        §4 decisions D1-D8 (event-fed pending_tail vs polling; tail source per mode; text()
        rendering; code-constant caps; no-state.json law; counts-only log)."

# MUST READ — the PRD clause (verbatim spec) + the R.5 three-value law it sits on.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.6 (recovery paragraph — quoted in Why), R.5 ('keep three values distinct:
        latest recognized; filter-accepted final; last target-CONFIRMED visible'; 'never the
        surrounding user document' in state.json), R.1 event-count context, §4.2quater
        Backspace-cancel semantics (what a deliberate cancel is)."

# MUST READ — the files being modified/created.
- file: voice_typing/daemon.py
  why: "(1) on_final :1246 (listening gate :1248, _on_final_lock :1257, suppression window
        :1262-1359 early-returns, cleaned :1360, rejected block :1362-1403, record_final :1451
        — the accepted-final funnel for BOTH streaming-commit and Rev1 paths). (2) _on_partial
        :1684 (gate :1691, _stream.on_partial :1697). (3) _disarm :1603 (stream_reset block ~
        :1620 — close_session goes BEFORE it). (4) _arm :1541. (5) cancel :1938
        (_reset_stream_after_cancel :1980). (6) request_shutdown :2341. (7) ctor :661 +
        the :843-920 field block. (8) status_snapshot :2463 (session_snapshot goes beside it).
        ALL pre-S1 anchors — S1 shifts them; re-grep (Task 0)."
  critical: "Insert AFTER existing statements only — never reorder gates, never touch the
             legacy bodies' logic. close_session under _lock is safe (pure memory, bounded
             encode) but the store must NEVER call back into the daemon."

- file: voice_typing/streaming.py
  why: "READ ONLY. .tail :292 (everything typed since the last checkpoint — the visible
        unfinished-utterance text; '' after commit), .committed :287, reset_session :387
        (clears both — why close_session precedes it and why pending_tail is event-fed, not
        engine-read at close)."
  gotcha: "In Rev1 mode (streaming=false) the engine tail stays '' — session is finals-only. Correct."

- file: voice_typing/bulk_controller.py
  why: "READ ONLY. The three-value accessors (:604/:611/:618) S1's persona names as the S2/S3
        surface — documented to justify WHY this design feeds from events instead (research §1:
        polling confirmed_visible at close cannot distinguish committed-last-utterance from
        unfinished tail without lossy string comparison)."

- file: tests/test_daemon.py
  why: "READ ONLY. _FakeHost :561, _fake_host_factory :665, _make :683 — the daemon-construction
        pattern for the wiring tests; the existing cancel/suppression-window tests as templates
        for driving the cancel exclusion."

- file: tests/test_bulk_dispatch.py
  why: "S1's suite — the freshest bulk-mode test template (bulk cfg triple fixture, FakeBundle,
        fake host with settable relay_identity, spy backend). Reuse its fixtures for the
        bulk-mode wiring tests; the whole file must stay green after S2's insertions."

# Hard rules.
- file: AGENTS.md
  why: "Two timeouts on every non-trivial command; pytest under timeout 600 (bash-tool timeout
        above); never foreground the daemon; unit doubles only — no CUDA, no live desktop."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # ← MODIFY: 8 hook insertions + session_snapshot() + docstring note
├── session_recovery.py  # ← CREATE: SessionRecovery + CompletedSession (pure python)
├── bulk_controller.py   # READ ONLY (three-value accessors; context)
├── streaming.py         # READ ONLY (.tail source; reset ordering)
├── feedback.py          # READ ONLY (no session text ever written there)
└── ctl.py               # READ ONLY (S3 owns the session command)
tests/
├── test_session_recovery.py  # ← CREATE (store-level + daemon-level)
└── (test_daemon / test_bulk_dispatch / G1 watch set)  # must stay green untouched
```

### Desired Codebase tree with files to be added

```bash
voice_typing/session_recovery.py      # + ~160 lines: frozen CompletedSession (text/byte_len),
                                      #   SessionRecovery (open/note_final/note_rejected/
                                      #   note_tail/note_cancel/close/latest_completed/clear),
                                      #   _MAX_SESSIONS=2, _MAX_SESSION_BYTES=1<<20
voice_typing/daemon.py                # + ~45 lines: ctor field, 8 narrow hooks (1-3 lines each),
                                      #   session_snapshot(), module-docstring §RECOVERY note
tests/test_session_recovery.py        # + ~20 tests (store rules + both-mode wiring)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G1) — HOOK PLACEMENT IS THE CORRECTNESS STORY: every store hook must sit AFTER
#   the existing gates (listening gate on_final :1248 / _on_partial :1691; cancel-suppression
#   window :1262-1359; `if not cleaned:` :1362). Late finals, cancelled racing finals, and
#   rejected finals are excluded because those gates return BEFORE the hook — never duplicate
#   or reorder the gate logic.

# CRITICAL #2 (G2) — the store is a LEAF: own threading.Lock, no calls into daemon/feedback/
#   controller, no callbacks, no I/O. note_* are O(1) (string ref assignment); close_session
#   is bounded pure memory (≤ ~2 MiB encode worst case). Safe under _lock and on the reader
#   thread; deadlock-free by construction.

# CRITICAL #3 (G3) — S1 CO-MODIFICATION DRIFT: S1 lands first (+~250 lines in daemon.py).
#   All cites above are pre-S1 anchors. Re-grep live (Task 0). The bulk hooks are insertions
#   INSIDE S1's _bulk_handle_final/_bulk_handle_partial/_bulk_cancel bodies — not new intercepts.

# CRITICAL #4 (G4) — _disarm ORDERING: close_session() must run BEFORE the stream_reset
#   (reset_session) block — although pending_tail is event-fed (never read from the engine at
#   close), keeping this order documents the invariant and survives any future design that
#   does read engine state. _disarm is the funnel for EVERY disarm path (stop/toggle-off/
#   drain-complete/auto-stop/HALT/bulk-fault) — verified in its docstring.

# CRITICAL #5 (G5) — the cap is on UTF-8 BYTES of the RENDERED text (len(s.encode('utf-8')));
#   Python str slicing is codepoint-safe (never splits a surrogate). Drop WHOLE oldest items
#   first ("newest complete text that fits"); only a lone oversized item gets sliced.
#   Measure once at close, not per-event.

# CRITICAL #6 (G6) — NO transcript-bearing surfaces: no session text in state.json, feedback,
#   logs, or exceptions. The close-time INFO line carries counts/times only. The one place
#   text leaves the store is session_snapshot() — an on-demand pull for S3's control reply.

# CRITICAL #7 (G7) — exactly-once dedupe key: bulk = (ident.session_gen, ident.utterance_id)
#   (raw hashables; the str(uid) form is for the controller, not the store); stream-edit =
#   None (no ids — the single post-record_final funnel fires once per accepted text()
#   invocation; the gates upstream make duplicates unreachable).

# CRITICAL #8 (G8) — SCOPE WALLS: no config keys (R.6 fixes 2×1 MiB as code constants), no
#   ctl.py, no ControlServer cmd, no state.json schema change, no streaming.py/
#   bulk_controller.py/feedback.py edits. S3 owns `voicectl session [--copy]`; S1's suites
#   must stay green untouched.

# CRITICAL #9 (G9) — acquire-failure (bulk "unsupported") leaves recording ARMED: the session
#   stays open and continues — it is NOT a "failed arm" for recovery. A failed arm = a session
#   that closes empty (load error, nothing dictated) → discarded, previous completed survives.

# CRITICAL #10 (G10) — clear() rides request_shutdown() (the SIGTERM + quit funnel). A quit
#   while armed may skip _disarm — clear() still empties the store ("cleared at daemon exit").
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/session_recovery.py — full shape (pure stdlib)
from __future__ import annotations
import threading, time
from dataclasses import dataclass, field

_MAX_SESSIONS = 2            # R.6: at most two sessions (code constant, NOT config)
_MAX_SESSION_BYTES = 1 << 20 # R.6: 1 MiB UTF-8 per session

@dataclass(frozen=True)
class CompletedSession:
    finals: tuple[str, ...]      # accepted finals, in order, exactly once per utterance
    tail: str                    # last visible/recognized unfinished tail ("" if none)
    truncated: bool              # size-cap truncation happened
    finals_dropped: int          # count dropped by the cap (for the truncation report)
    ended_monotonic: float
    def text(self) -> str:       # EXACTLY what S3 prints/copies: single-space join,
        parts = list(self.finals) + ([self.tail] if self.tail else [])
        return " ".join(parts)   # no trailing space, NO added newline
    def byte_len(self) -> int:
        return len(self.text().encode("utf-8"))

class SessionRecovery:
    """R.6 recovery store — daemon MEMORY ONLY (no persistence, no transcript-bearing logs)."""
    def __init__(self, max_sessions: int = _MAX_SESSIONS,
                 max_session_bytes: int = _MAX_SESSION_BYTES) -> None:
        self._lock = threading.Lock()          # leaf lock: never held across callbacks
        self._completed: list[CompletedSession] = []   # oldest first, ≤ max_sessions
        self._draft_finals: list[str] = []
        self._draft_keys: set[tuple] = set()   # bulk (gen, uid) closed set — exactly-once
        self._pending_tail: str = ""
        self._open = False
    # API: open_session / note_final(text, key=None) / note_rejected() / note_tail(text) /
    #      note_cancel() / close_session() / latest_completed() / clear()
    #      — see Implementation Tasks for exact semantics.
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — re-verify anchors post-S1 + record the baseline.
  - RUN: grep -n "def on_final\|def _on_partial\|def _disarm\|def _arm\|def cancel\|def request_shutdown\|record_final(\|_reset_stream_after_cancel\|_bulk_handle_final\|_bulk_handle_partial\|_bulk_cancel" voice_typing/daemon.py
  - RUN (baseline, BEFORE any edit): for f in test_daemon test_bulk_dispatch test_streaming_commit \
      test_zero_diff_rewind test_key_listener test_control_socket test_config; do
      timeout 300 .venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1; done
  - EXPECTED: identical numbers post-change (test_streaming_commit has pre-existing reds —
    tests/G1_BASELINE.md records the history; do not fix).

Task 1: CREATE voice_typing/session_recovery.py.
  - IMPLEMENT CompletedSession + SessionRecovery exactly per Data models above, with:
    - open_session(): under lock — draft reset (finals=[], keys=set(), tail="", _open=True).
    - note_final(text, key=None): under lock, only when _open; if key is not None and key in
      _draft_keys: return (exactly-once); append text to _draft_finals; add key; CLEAR
      _pending_tail (the utterance closed — its content is now the final, not a tail).
    - note_rejected(): content NO-OP by design (a rejected final retains only the shown tail —
      pending_tail stays exactly as-is). Exists as an explicit, testable hook.
    - note_tail(text): under lock, only when _open; _pending_tail = text (plain overwrite —
      newest partial wins, matching the visible field).
    - note_cancel(): under lock; _pending_tail = "" (the cancelled fragment is excluded).
    - close_session(): under lock; _open=False; if NOT (draft_finals or pending_tail): discard
      the draft entirely (empty session — previous completed survives) and return; else build
      the session then enforce the cap (G5): while byte_len() > max_session_bytes AND
      len(finals) > 1: pop the OLDEST final, finals_dropped += 1; if still over (a single
      item alone exceeds): hard-truncate that item by codepoints until it fits
      (bisect the slice so the encoded size ≤ cap; keep the NEWEST end? NO — keep the item's
      START, drop its overflow suffix: the beginning of an utterance is the recoverable part;
      document the choice); truncated = (finals_dropped > 0 or any slice happened);
      append CompletedSession(finals, tail, truncated, finals_dropped, time.monotonic());
      trim _completed to the newest max_sessions (pop oldest).
    - latest_completed(): under lock; return _completed[-1] if any else None (NEVER a draft).
    - clear(): under lock; _completed.clear(); draft reset; _open=False.
  - NAMING: module session_recovery.py, classes SessionRecovery/CompletedSession, methods
    snake_case per above. Module docstring: Mode A — the R.6 contract in brief, the
    no-persistence/no-text-logs law, the leaf-lock law (G2), and the consumer contract for
    S3 (latest_completed().text() is EXACTLY what voicectl session prints).
  - RUN: timeout 60 .venv/bin/python -c "import voice_typing.session_recovery" && \
        .venv/bin/python -m py_compile voice_typing/session_recovery.py

Task 2: MODIFY daemon.py — ctor + lifecycle hooks.
  - IMPORT: from . import session_recovery (module top; it is import-pure stdlib).
  - CTOR: in the :843-920 field block: self._session_recovery = session_recovery.SessionRecovery().
  - _arm(): inside the existing under-lock body (near the gen bumps S1 added): 
      self._session_recovery.open_session().
  - _disarm(): INSERT self._session_recovery.close_session() immediately BEFORE the
    stream_reset (reset_session) block (G4). One line; pure memory; under _lock is fine.
  - request_shutdown(): after the _duck_release() line: self._session_recovery.clear() (G10).

Task 3: MODIFY daemon.py — stream-edit event hooks (default mode).
  - on_final ACCEPTED: immediately AFTER self._feedback.record_final(cleaned) (the single
    funnel both streaming-commit and Rev1 reach — re-grep post-S1):
      self._session_recovery.note_final(cleaned)
  - on_final REJECTED: at the TOP of the `if not cleaned:` block (before the streaming
    freeze — order within the block is irrelevant, top is the readable choice):
      self._session_recovery.note_rejected()
  - _on_partial: after self._stream.on_partial(text) (the engine tail is now current):
      self._session_recovery.note_tail(self._stream.tail)
  - cancel() legacy path: after self._reset_stream_after_cancel():
      self._session_recovery.note_cancel()

Task 4: MODIFY daemon.py — bulk-mode hooks (INSIDE S1's bodies; 1-3 lines each; G3).
  - _bulk_handle_partial: after the ctrl.on_partial(...) call:
      self._session_recovery.note_tail(text)
  - _bulk_handle_final ACCEPTED branch: after self._feedback.record_final(cleaned):
      self._session_recovery.note_final(cleaned, key=(gen, uid))     # G7 raw hashables
  - _bulk_handle_final REJECTED branch (the `if not cleaned:` → on_final_dropped + notify):
      self._session_recovery.note_rejected()
  - _bulk_cancel: after the under-lock recognition-cancel block (beside/after
    _reset_stream_after_cancel): self._session_recovery.note_cancel()
  - The identity-missing drop path and the fault lifecycle need NO store calls (nothing was
    recognized/delivered; the disarm funnel closes the session).

Task 5: MODIFY daemon.py — the S3 contract point + docstring.
  - ADD session_snapshot() beside status_snapshot (lock-safe, control-thread callable):
      def session_snapshot(self) -> dict | None:
          s = self._session_recovery.latest_completed()
          if s is None: return None
          return {"text": s.text(), "truncated": s.truncated,
                  "finals": len(s.finals), "finals_dropped": s.finals_dropped,
                  "tail_chars": len(s.tail), "ended_monotonic": s.ended_monotonic}
  - MODULE DOCSTRING: extend with a §RECOVERY paragraph — R.6 in one breath: memory-only,
    last nonempty arm→disarm session, accepted finals exactly once + unfinished tail,
    exclusions enforced by hook placement (after the listening gate / suppression window /
    rejected-final block), 2×1 MiB cap with truncation reporting, cleared at exit, no
    transcript-bearing logs, session_snapshot() feeds T2.S3's voicectl session.

Task 6: CREATE tests/test_session_recovery.py (two layers; fakes only — no CUDA/subprocess).
  - LAYER A — STORE (pure unit; every contract exclusion rule):
    1. accepted finals in order; text() single-space join, no trailing space/newline.
    2. tail appended with one space; tail-only session → text == tail.
    3. exactly-once: note_final twice with the SAME key → one entry; different keys → two.
    4. rejected: note_tail("abc") → note_rejected() → close → tail retained, no final.
    5. cancel: note_tail("abc") → note_cancel() → close (with an earlier final) → tail gone,
       final kept; a post-cancel racing final never reaches the store (daemon-level test 14
       pins the gate; store-level: note_cancel cleared the tail).
    6. close with nothing → discarded; latest_completed() unchanged (empty-arm survival).
    7. re-arm resets the draft: open → note_tail → close(empty after note_cancel) → open →
       no leakage of the previous draft's tail into the next session.
    8. ≤2 sessions: three completions → oldest evicted; latest == newest.
    9. 1 MiB cap: a session of many finals overflowing → oldest finals dropped until it
       fits, newest kept, truncated=True, finals_dropped counted; byte_len() ≤ cap.
    10. lone oversized item: one final > cap → sliced to fit, truncated=True, ≤ cap bytes,
        valid UTF-8 (decode the encode round-trip).
    11. clear() → latest_completed() is None; open/final/close works again after clear.
    12. thread-safety smoke: concurrent note_tail/note_final from 2 threads + close — no
        exception, consistent final state (bounded loop, e.g. 200 ops).
  - LAYER B — DAEMON WIRING (test_daemon's _make/_FakeHost pattern; bulk tests reuse
    test_bulk_dispatch.py's fixtures — copy the minimal fake set if import is awkward):
    13. stream-edit accepted final → latest_completed().text() == the final; record via
        daemon.on_final with a fake host, _listening set.
    14. stream-edit cancel: arm → _on_partial("hello wor") → cancel() → the suppressed
        racing on_final (drive the suppression window like the existing test_daemon cancel
        tests) → disarm → session text has NEITHER the tail NOR the final.
    15. late final: arm → on_final(accepted) → _disarm() → on_final("late text") → store
        unchanged (previous session intact; "late text" absent).
    16. rejected final: on_final(blocklisted text e.g. "thank you for watching") → disarm →
        no final recorded; a prior note_tail survives as the tail (retention rule).
    17. empty arm survival: complete a session → arm → (no events) → _disarm() →
        latest_completed() still the FIRST session.
    18. bulk accepted final: bulk-mode daemon + fake host relay_identity (gen, uid=7) →
        on_final → session has the final exactly once; replay the same final (dup) → still
        once (the (gen,uid) key).
    19. bulk cancel: _on_partial → cancel() → disarm → tail + racing final absent.
    20. quit clears: complete a session → request_shutdown() → session_snapshot() is None.
    21. log discipline: caplog — the close-time INFO line matches
        "session recovery: session completed finals=\d+ tail_chars=\d+ bytes=\d+ truncated=\d+"
        and does NOT contain any final's text.
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py -q
    (bash-tool timeout 330).

Task 7: VALIDATE — the full Validation Loop; reconcile the G1 watch set + test_bulk_dispatch
  against Task 0's baseline (identical numbers required). No git commit unless directed
  (message if so: "P1.M6.T2.S2: R.6 session recovery store — daemon-memory, both modes,
  exclusion rules by hook placement, 2x1MiB cap").
```

### Implementation Patterns & Key Details

```python
# PATTERN — the accepted-final hook (stream-edit; the ONLY lines added to on_final's tail):
            self._feedback.record_final(cleaned)   # existing
            self._session_recovery.note_final(cleaned)   # ← NEW (1 line, after the funnel)
    # and inside the `if not cleaned:` block, at its top:
            self._session_recovery.note_rejected()       # ← NEW (content no-op by design)

# PATTERN — _disarm insertion (before the engine reset; G4):
        self._disarmed_monotonic = time.monotonic()      # existing
        self._session_recovery.close_session()           # ← NEW (pure memory; under _lock OK)
        stream_reset = getattr(self._stream, "reset_session", None)   # existing

# PATTERN — close_session cap enforcement (G5 — whole items first, then a lone item's slice):
    def close_session(self) -> None:
        with self._lock:
            self._open = False
            if not (self._draft_finals or self._pending_tail):
                self._draft_finals.clear(); self._draft_keys.clear(); self._pending_tail = ""
                return                                   # empty session: discarded (R.6)
            finals, dropped = list(self._draft_finals), 0
            truncated = False
            def _mk() -> CompletedSession:
                return CompletedSession(tuple(finals), self._pending_tail, truncated,
                                        dropped, time.monotonic())
            s = _mk()
            while s.byte_len() > self._max_session_bytes and len(finals) > 1:
                finals.pop(0); dropped += 1; truncated = True; s = _mk()
            if s.byte_len() > self._max_session_bytes:
                # lone oversized item (final or tail): keep its START, drop the overflow suffix
                item = finals[0] if finals else self._pending_tail
                lo, hi = 0, len(item)
                while lo < hi:                            # codepoint-binary-search the budget
                    mid = (lo + hi + 1) // 2
                    probe = item[:mid] + (" " + self._pending_tail if not finals and self._pending_tail else "")
                    if len((probe if finals else probe).encode("utf-8")) <= self._max_session_bytes:
                        lo = mid
                    else:
                        hi = mid - 1
                ...apply the slice to finals[0] or the pending tail...; truncated = True
                s = _mk()
            self._completed.append(s)
            del self._completed[:-self._max_sessions]
            self._draft_finals.clear(); self._draft_keys.clear(); self._pending_tail = ""
        # (logging happens at the DAEMON hook — counts only, G6/D6 — so the store stays a leaf)

# GOTCHA — note_final clears the pending tail (the utterance closed):
    def note_final(self, text: str, key: tuple | None = None) -> None:
        with self._lock:
            if not self._open: return
            if key is not None:
                if key in self._draft_keys: return       # exactly-once (R.6)
                self._draft_keys.add(key)
            self._draft_finals.append(text)
            self._pending_tail = ""                      # closed utterance ⇒ not a tail

# CRITICAL — never let the store grow unbounded in the DRAFT either: note_tail is an
# overwrite (O(1)), so the draft holds at most one tail string + the finals list; the finals
# list is bounded at close by the cap. A pathological session (hours of dictation, no disarm)
# accumulates finals in memory until close — acceptable per R.6 (the cap is per stored
# session), but note it in the module docstring.
```

### Integration Points

```yaml
DAEMON → STORE (this item's wiring — the complete list):
  - "_arm():            open_session()"
  - "_disarm():         close_session()  [before the reset_session block]"
  - "on_final:          note_final(cleaned)  [after record_final] · note_rejected() [rejected block top]"
  - "_on_partial:       note_tail(self._stream.tail)  [after _stream.on_partial]"
  - "cancel() legacy:   note_cancel()  [after _reset_stream_after_cancel]"
  - "_bulk_handle_final:    note_final(cleaned, key=(gen, uid)) · note_rejected()   [inside S1's body]"
  - "_bulk_handle_partial:  note_tail(text)                                       [inside S1's body]"
  - "_bulk_cancel:          note_cancel()                                         [inside S1's body]"
  - "request_shutdown(): clear()  [after _duck_release]"

S3 CONSUMPTION (next item — do NOT implement):
  - "daemon.session_snapshot() -> None | {text, truncated, finals, finals_dropped, tail_chars, ended_monotonic}"
  - "S3's control reply prints/copies snapshot['text'] EXACTLY (no added newline); reports
     truncated on stderr + in the reply; exit 1 with clipboard untouched when None."

NO config keys. NO state.json changes. NO ctl.py/ControlServer changes. NO edits to
streaming.py / bulk_controller.py / feedback.py / recorder_host.py.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/session_recovery.py voice_typing/daemon.py tests/test_session_recovery.py && echo OK
.venv/bin/python - <<'EOF'
import sys, inspect
import voice_typing.session_recovery as sr
assert not [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]  # import purity
assert sr._MAX_SESSIONS == 2 and sr._MAX_SESSION_BYTES == 1 << 20
import voice_typing.daemon as d
assert hasattr(d.VoiceTypingDaemon, 'session_snapshot')
src = open('voice_typing/daemon.py').read()
assert src.count('session_recovery.note_') >= 6 and 'close_session()' in src
print('symbols + wiring OK')
EOF
```

### Level 2: Unit Tests (Component Validation)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py -q   # bash-tool 330
# The neighbors this item touches (must be green / identical to Task 0 baseline):
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cancel or final or partial or arm or disarm"
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q      # S1's suite
# The G1 watch set (identical numbers required):
for f in test_streaming_commit test_zero_diff_rewind test_key_listener test_control_socket test_config; do
  timeout 300 .venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1; done
# Expected: all green except test_streaming_commit's PRE-EXISTING reds (same count as Task 0's
# baseline; tests/G1_BASELINE.md is the recorded history — no new failures, no blanket skips).
```

### Level 3: Integration Testing (System Validation)

```bash
# Structural — the hooks sit AFTER the gates (AST order check on on_final):
.venv/bin/python - <<'EOF'
import ast
tree = ast.parse(open('voice_typing/daemon.py').read())
of = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'on_final')
body = ast.dump(of)
i_gate = body.index('_listening')            # the listening gate
i_supp = body.index('suppress')              # the suppression window
i_rej  = body.index('note_rejected')
i_acc  = body.index('note_final')
assert i_gate < i_supp < i_rej, 'rejected hook must follow the gates'
assert i_gate < i_supp < i_acc < body.index('record_final') or i_acc > i_supp, 'accepted hook after gates'
d = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_disarm')
db = ast.dump(d); assert db.index('close_session') < db.index('reset_session')
print('hook placement structurally OK')
EOF
# NO live daemon is started for this item (AGENTS.md) — daemon-level behavior is covered by
# the Layer-B tests with fakes. voicectl session end-to-end belongs to T2.S3.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# The no-transcript-logs pin — every session-recovery log line must be counts-only:
timeout 120 .venv/bin/python -m pytest tests/test_session_recovery.py -q -k "log" -v
# The exclusion-rule completeness pin — one green test per contract rule:
timeout 120 .venv/bin/python -m pytest tests/test_session_recovery.py -v 2>&1 | \
  grep -E "exactly_once|rejected|cancel|late|empty|cap|truncat|clear|survive" | head -15
# Expected: each named exclusion rule has ≥1 passing test (store level) and the four
# daemon-level gate tests (late/cancel/rejected/empty) pass. No CUDA, no subprocess, no
# live desktop anywhere in this item's validation.
```

## Final Validation Checklist

### Technical Validation

- [ ] L1 py_compile + import purity + symbol/wiring asserts OK.
- [ ] `tests/test_session_recovery.py` green (store layer: all 12; wiring layer: all 9).
- [ ] `tests/test_daemon.py -k "cancel or final or partial or arm or disarm"` green.
- [ ] `tests/test_bulk_dispatch.py` green untouched (S1 compose check).
- [ ] G1 watch set numbers IDENTICAL to the Task 0 baseline (incl. pre-existing
      `test_streaming_commit` reds — reconciled, not newly broken, not skipped).
- [ ] Structural AST checks: hooks after the gates in `on_final`; `close_session` before
      `reset_session` in `_disarm`.

### Feature Validation

- [ ] Accepted finals recorded in order, exactly once per utterance (bulk keyed dedupe pinned).
- [ ] Rejected final: no final added, shown tail retained.
- [ ] Deliberate cancels excluded (tail + racing final absent — both entry points funnel).
- [ ] Late finals excluded; previous completed session survives empty/failed arms.
- [ ] ≤2 sessions × 1 MiB: eviction + truncation reported (`truncated`, `finals_dropped`).
- [ ] `request_shutdown()` clears the store; `session_snapshot()` returns None afterwards.
- [ ] `session_snapshot()` shape matches the Integration Points contract (S3-ready).
- [ ] No session text in state.json / feedback / logs (caplog pin).

### Code Quality Validation

- [ ] Adds confined to the 3 declared files; scope walls respected (streaming/bulk_controller/
      feedback/ctl/recorder_host/config untouched).
- [ ] Store is a leaf (own Lock, no callbacks, no I/O); all methods non-blocking/bounded.
- [ ] New log lines carry counts/times only; module docstrings document the R.6 contract
      (Mode A house style).
- [ ] No new config keys, env vars, state-file fields, or voicectl surface.

### Documentation & Deployment

- [ ] daemon.py module docstring §RECOVERY note (contract summary + consumer pointer to S3).
- [ ] session_recovery.py module docstring (R.6 brief, no-persistence law, leaf-lock law,
      S3 consumption contract, draft-accumulation note).

---

## Anti-Patterns to Avoid

- ❌ Don't place any store hook BEFORE the existing gates (listening gate, suppression window,
  `if not cleaned`) — the exclusions are inherited from them; duplicating gate logic forks truth.
- ❌ Don't poll the controller/engine at session close for the tail — feed from events
  (`note_tail`); `confirmed_visible()` cannot distinguish a committed last utterance from an
  unfinished tail without lossy comparison.
- ❌ Don't call INTO the daemon from the store (callbacks, feedback, logging) — it must stay a
  deadlock-free leaf; the close-time log line belongs to the daemon hook.
- ❌ Don't write session text to state.json, feedback, logs, or exceptions — R.5/R.6: daemon
  memory only; `session_snapshot()` is the single exit point (S3's pull).
- ❌ Don't add config keys for the caps — R.6 fixes 2 × 1 MiB as code constants.
- ❌ Don't implement `voicectl session`, the control-socket cmd, or `--copy` — T2.S3 owns them.
- ❌ Don't touch/reorder S1's `_bulk_*` bodies beyond the 1–3-line insertions — S1's suite is a
  hard green gate.
- ❌ Don't truncate by dropping the NEWEST text — R.6: keep the newest COMPLETE text that fits
  (drop oldest items first); only a lone oversized item gets sliced.
- ❌ Don't run the daemon, E2E scripts, or CUDA suites for this item — unit doubles only
  (AGENTS.md).

---

## Confidence Score

**9/10.** The store is a self-contained pure-python leaf with the contract's rules mapped 1:1 to
named tests; every hook site was verified live this session (with the S1-drift re-grep mandated
as Task 0); the exclusion rules ride existing, heavily-tested gates rather than new logic; and
the only genuinely subtle piece (cap enforcement: whole-items-first, codepoint-boundary slice)
has an explicit pattern with a binary-search sketch. Residual risks: (1) S1's landed shape
differs slightly from its PRP (mitigated: hooks are 1–3-line insertions at grep-able statements
— `record_final(cleaned)`, `ctrl.on_partial(`, `_reset_stream_after_cancel()` — trivially
adaptable; Task 0's re-grep is the safety net); (2) the lone-oversized-item slice math
(mitigated: dedicated tests 9/10 pin byte_len ≤ cap and UTF-8 round-trip); (3) thread-timing in
the wiring tests (mitigated: no timing dependence — events are driven synchronously through the
daemon methods on the test thread, the established test_daemon pattern).

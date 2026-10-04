# Research — P1.M1.T4.S1: Gate _on_partial on is_listening + stale-partial regression test (BUG-004)

> BUG-004 (Major, PRD h2.2/h3.3): `_on_partial` has NO listening gate while `on_final`'s first
> statement is the race guard. A partial already in the IPC queue when the user toggles off types
> into the focused window AFTER the disarm. Fix: the same first-line guard, BEFORE the engine
> routing AND the latency note. TDD: daemon-level failing test FIRST with the repo's own doubles.

## §1 — The defect, verified in source (file:line)

`voice_typing/daemon.py` `_on_partial` (~:1390, body ends :1411-1412):

```python
def _on_partial(self, text: str) -> None:
    """Handle a realtime partial from the host's reader thread (P1.M3.T2.S2 re-plan).

    Routes the partial through the streaming engine (P1.M2.T6.S2): extend/revise
    typing with guards — the engine mirrors into the Feedback partial on EVERY path ...
    Called from the host reader thread (daemon thread). The engine never raises ...
    """
    self._stream.on_partial(text)
    self._latency.note_partial(text)
```

NO gate. Compare `on_final` (~:1119-1124) — the reference pattern to mirror:

```python
def on_final(self, text: str) -> None:
    """Gate → clean → type → record + log latency. Fired by RealtimeSTT in a NEW thread."""
    t_final_ready = time.monotonic()  # entry stamp (PRD §4.2 latency logging)
    if (
        not self._listening.is_set()
    ):  # GATE: race guard (PRD §4.2/§8 — utterance may
        return  #   complete right after stop)
```

Upstream: `recorder_host._dispatch` (:444-446 per architecture/daemon_flow.md) relays `'partial'`
events ungated (it gates only `'vad'` events) — so the daemon-level gate is the correct fix point
(per PRD h2.5 recommendation: "Add a listening gate to _on_partial (mirror the on_final gate)").
Do NOT touch recorder_host.py — the daemon gate covers all callers.

**Demonstrated (PRD h3.3 repro, daemon level, repo doubles):** `d.start(); d._on_partial('hello
there')` types; `d.stop(); d._on_partial('stray words')` STILL types — `backend.typed` gains
'stray words'.

## §2 — The verbatim fix

Insert the gate as the FIRST statement of `_on_partial`, before BOTH the engine routing and the
latency note (a stray post-disarm partial must neither type NOR count into latency). Mirror
on_final's comment style:

```python
        self._stream.on_partial(text)
```
becomes (insert before that line):
```python
        if (
            not self._listening.is_set()
        ):  # GATE: race guard (BUG-004 / P1.M1.T4.S1) — a stray
            return  #   post-disarm partial must neither type nor count into latency
        self._stream.on_partial(text)
        self._latency.note_partial(text)
```
(Exact indentation/wrap style optional; the CONTRACT is: the guard is the first statement and both
the stream call and the latency note sit after it. Do not touch anything else.)

**Documented side effect (intended, note in the test docstring):** the gate also stops the Feedback
partial mirror (`state.json`'s `partial` field) while toggled off — the engine mirror lives inside
`_stream.on_partial`. Consistent with on_final's behavior (no mirror while off) + more honest
status. Also note: `_touch_speech` (the `'speech'` event hook, ~:1366) is a SEPARATE path and is
NOT gated here — a stray 'speech' event only resets the idle clock / resumes the engine
(engine-internal, no keystrokes), which is harmless and already correct (BUG-001/BUG-002 wiring).
Do not add a gate there.

## §3 — The TDD test (daemon level, doubles only — mirrors the existing Rev 2 section)

`tests/test_daemon.py` already has a Rev 2 streaming section driving `d._on_partial` with the REAL
`StreamingOutput` on fakes (banner ~:4589; tests at :4601, :4617, :4659, :4671, :4702 — all via
`_make_daemon()` from :684). APPEND a new banner + 1 test at the file's END (the file is ~4964
lines; the current last test is the stranded-tail freeze test). `daemon` and `_make_daemon` are
already in scope.

```python
# ===========================================================================
# P1.M1.T4.S1 — _on_partial listening gate (BUG-004): stale post-disarm partials
# (on_final gates its first line (the race guard); _on_partial did NOT — a partial
#  already in the IPC queue when the user toggles off typed AFTER the disarm. The
#  gate also stops the state.json partial mirror + the latency count while off.)
# ===========================================================================
def test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing():
    """A stray post-disarm partial neither types nor counts into latency (BUG-004).

    Daemon-level repro (PRD h2.2/h3.3): arm, a partial types through the engine; stop()
    clears the listening flag; a partial already computed/in the IPC queue arrives AFTER
    the disarm — it must NOT reach the backend (case-preserved fresh-session text was
    typed into the focused window before the gate) and must NOT reach the latency log.
    Mirrors on_final's first-line race guard (daemon.py on_final GATE).
    """
    d, _fb, _rec, be = _make_daemon()
    d.start()
    assert d.is_listening() is True
    d._on_partial("hello there")            # armed: routed through the engine
    assert "hello there" in "".join(be.typed)
    d.stop()
    assert d.is_listening() is False
    before = list(be.typed)
    d._on_partial("stray words")            # stale partial AFTER the disarm
    assert be.typed == before, f"stale partial typed while toggled off: {be.typed!r}"
```

Notes on the assertion `"hello there" in "".join(be.typed)`: streaming mode may type deltas
('hello', ' there') rather than the whole string — joining all typed entries covers both. The
stale check is exact (`be.typed == before`) — the load-bearing RED discriminator: before the fix,
`be.typed` gains 'stray words' (or its delta) → test FAILS.

RED→GREEN proof: run the new test against the UNEDITED daemon.py → the final assert fails with
`['hello there', ..., 'stray words']`. Apply §2 → green.

Latency-note gating is covered by construction (the guard precedes the note) — the typed-backend
assertion is the observable seam; no separate latency assert needed (keep the test lean, matching
the file's style).

## §4 — ACCEPTANCE.md row 4 (Mode A docs update)

`tests/ACCEPTANCE.md` row 4 (~:35) currently claims: "the `listening` flag gates BOTH the partial
and commit paths — COMPLIANT + mocked LIVE (193 daemon tests)". False until this lands. Update the
Evidence cell's first sentence to cite the new regression test, e.g. replace

> Disarm gate unchanged by Rev 2: the `listening` flag gates BOTH the partial and commit paths —
> COMPLIANT + mocked **LIVE** (193 daemon tests).

with

> Disarm gate: the `listening` flag gates BOTH the partial and commit paths — the commit gate is
> on_final's first line; the partial gate is `_on_partial`'s first line (BUG-004 /
> P1.M1.T4.S1), pinned by `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing`
> (mocked **LIVE** in tests/test_daemon.py).

The criterion/Status cells are UNCHANGED (the claim itself was always the spec; it is now actually
true). No README change (P1.M3.T9's Mode B sweep re-verifies).

## §5 — Verify commands + scope

```bash
cd /home/dustin/projects/voice-typing
# TDD red (before the daemon.py edit):
timeout 600 /home/dustin/.local/bin/uv run pytest tests/test_daemon.py -k "stale_partial_after_stop" -q
# green after + no regression:
timeout 600 /home/dustin/.local/bin/uv run pytest tests/test_daemon.py -k "partial or listening" -q
```

Scope: ONLY `voice_typing/daemon.py` (1 guard, `_on_partial`), `tests/test_daemon.py` (1 banner +
1 additive test), `tests/ACCEPTANCE.md` (row 4 evidence text). NO streaming.py (parallel T3.S1 owns
it — DISJOINT), no recorder_host.py, no README (P1.M3.T9). Never run the daemon foreground
(AGENTS.md). No CUDA — `_StubRecorder`/`_FakeBackend`/`_ok_probe` doubles via `_make_daemon()` (:684).

Machine gotchas: `.venv/bin/python -m pytest` or full `uv` path (zsh aliases); pytest only, no
ruff/mypy; wrap pytest in `timeout 600` per AGENTS.md Rule 1.

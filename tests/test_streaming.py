"""tests/test_streaming.py — PRD §6 T8 streaming-dictation E2E harness (P1.M3.T8.S1).

Heavy, real-model integration test: drives the REAL decode stream (small.en) through the REAL
StreamingOutput engine (voice_typing.streaming) and the REAL context-prompt executor
(voice_typing.prompt_engine.PromptedExecutor), capturing every backend keystroke via an
in-file RecordingTypingBackend — NO real keystrokes, NO mic, NO daemon/child process
(no make_backend, no RecorderHost spawn; fixtures are passed `use_microphone=False` and fed
tests/out/*.wav via feed_audio at real-time pacing).

PRD §6 T8 spec mapping — THIS file implements asserts (a), (b), (d) only; (c)/(e)/(f)/(g)
belong to P1.M3.T8.S2 and will extend THIS file (fixtures + helpers are deliberately
reusable; do not loosen them when S2 lands):
  (a) test_a_delta_cadence     — while speech streams, typed deltas arrive >=1 per 500 ms
                                 (suppress-aware: a gap is legitimate iff a feedback-mirror
                                 partial arrived in it — a rate-limited/suppressed revise
                                 cycle types nothing but the decoder is alive), and at least
                                 one extend cycle types ONLY the delta (no backspace since
                                 the previous keystroke).
  (b) test_b_commit_rewind_exact — every commit leaves the simulated screen exactly equal to
                                 the committed-so-far reconstruction (guarded final + trailing
                                 space, reconstructed from the harness's own commit log — an
                                 EXACT check, not fuzzy); every rewind deletes EXACTLY the
                                 pending tail; >=1 revising commit occurs (bounded retry with
                                 utt_punct.wav before failing).
  (d) test_d_decode_prompts    — every post-warmup decode of the RecordingPromptedExecutor
                                 carries initial_prompt == prompt_engine.rolling_context_prompt(
                                 ENGINE-committed-at-decode-time): empty after a commit whose
                                 committed truth ends a sentence, non-empty mid-paragraph
                                 (the committed tail has no terminator yet), always <=200
                                 whitespace tokens. THE ORACLE IS THE ENGINE'S COMMITTED TRUTH
                                 (typed text), not the cleaned final: the streaming guards
                                 legitimately strip a mid-paragraph spurious '.' / lower-case a
                                 mid-sentence start (T8c), and daemon._refresh_context_prompt
                                 sources stream.committed — the TYPED text. Model punctuation
                                 of espeak audio is nondeterministic (small.en added a period
                                 to PAUSE_A in one run and dropped multi's periods), so the
                                 empty/non-empty case per window FOLLOWS the engine truth;
                                 only >=1 non-empty window across pause+multi is required.

"lite recorder child" interpretation (in-process): the production child build path is
replicated IN THIS PROCESS — daemon.cfg_to_kwargs + recorder_host.augment_kwargs_with_executor
(the factory seam) + daemon._filter_kwargs_to_signature — exactly the order
recorder_host._worker_main builds in. Child IPC itself is covered by tests/test_recorder_host.py;
the executor-factory seam is what makes assert (d) deterministic (the harness holds the very
executor object the recorder decodes through, so its transcribe() calls are observable).

Load-bearing invariants (copied conventions from tests/test_feed_audio.py — each tag documents
a REAL hang/flake that already bit this repo):
  G-PACE               feed a 0.1 s slice, sleep its audio duration (VAD thresholds are
                       WALL-CLOCK); feed_audio is non-blocking and re-slices internally.
  G-TRAILING-SILENCE   20 x 0.1 s PACED zero slices after the last speech slice (>= 2x the
                       0.8 s lite_post_speech_silence_duration) — one big zeros dump drains in
                       <1 ms wall-clock so the stop threshold never fires and text() blocks
                       forever.
  G-ORDER              start the consume thread (text() arms listening) BEFORE the first feed.
  G-ABORT              recorder.abort() blocks on was_interrupted.wait() (set only INSIDE
                       text()) — call it ONLY from a helper thread, never the test thread.
  G-SHUTDOWN           session teardown calls shutdown() on a helper daemon thread, join(30).
  G-REALTIME-CB        enable_realtime_transcription stays True; the stabilized-partial
                       callback is wired to the harness (the engine's on_partial entry).
  G-NOLOGFILE          no_log_file=True (RealtimeSTT otherwise writes an unbounded
                       realtimesst.log into the repo).
  G-FUZZY              _token_overlap multiset helper; NEVER exact-match espeak-fixture model
                       output (the EXACT oracles here are the harness's OWN screen/commit-log
                       reconstruction, which is deterministic by construction).
  G-SKIP-GUARDS        module pytestmark + lazy _load_deps(): a box without WAVs/deps/CUDA
                       skips cleanly (never errors), and collecting this module imports no
                       heavy dependency (RealtimeSTT/torch/numpy/daemon stay lazy) so the fast
                       `pytest tests/` sweep and test_voicectl.py's import-purity check are
                       unaffected. The voice_typing modules imported at module scope
                       (streaming/typing_backends/prompt_engine/textproc) are stdlib-only by
                       contract (their own docstrings pin import purity; the sibling
                       test_streaming_core/test_prompt_engine/test_textproc modules import
                       them at module scope too).

Run explicitly (CUDA box; first model load is tens of seconds):
    cd /home/dustin/projects/voice-typing
    ./tests/make_test_audio.sh          # ensure tests/out/*.wav exist
    timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -v
"""

from __future__ import annotations

import dataclasses
import logging
import re
import string
import threading
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from voice_typing import prompt_engine, textproc
from voice_typing.streaming import StreamingOutput
from voice_typing.typing_backends import TypingBackend

if TYPE_CHECKING:
    # Type hints ONLY — never imported at runtime (G-SKIP-GUARDS; see module docstring).
    import numpy as np
    from RealtimeSTT import AudioToTextRecorder
    from voice_typing.config import VoiceTypingConfig

logger = logging.getLogger(__name__)

# --- skip guards (G-SKIP-GUARDS): never error the suite on a missing heavy prereq --------------
_OUT = Path(__file__).parent / "out"
_WAVS = {k: _OUT / f"utt_{k}.wav" for k in ("simple", "pause", "multi", "punct")}


def _have_wavs() -> bool:
    return all(p.is_file() for p in _WAVS.values())


def _load_deps() -> "dict[str, object]":
    """Import the heavy deps lazily; return a namespace dict (skip cleanly via the fixture).

    Mirrors tests/test_feed_audio.py::_load_deps: a non-polluting find_spec pre-probe for the
    optional faster-whisper extra, THEN the heavy imports. Collecting this module never runs
    this — sys.modules stays clean for tests/test_voicectl.py's import-purity check.
    """
    import importlib.util

    if importlib.util.find_spec("faster_whisper") is None:
        raise ImportError(
            "RealtimeSTT's default engine needs the optional 'faster-whisper' extra "
            '(install: pip install "RealtimeSTT[faster-whisper]")'
        )

    import numpy as _np
    import soundfile as _sf

    from RealtimeSTT import AudioToTextRecorder as _Rec
    from voice_typing import daemon as _daemon
    from voice_typing import recorder_host as _recorder_host
    from voice_typing.config import VoiceTypingConfig as _Cfg

    return {
        "np": _np,
        "sf": _sf,
        "AudioToTextRecorder": _Rec,
        "daemon": _daemon,
        "recorder_host": _recorder_host,
        "VoiceTypingConfig": _Cfg,
    }


# Populated by the `stream_recorder` fixture (session-scoped) before any test runs. None until
# then, so collection never imports RealtimeSTT/torch (preserves import purity).
_DEPS: "dict[str, object] | None" = None

pytestmark = pytest.mark.skipif(
    not _have_wavs(),
    reason="needs tests/out/*.wav (run ./tests/make_test_audio.sh first)",
)


# --- canonical fuzzy targets (PINNED VERBATIM from tests/make_test_audio.sh; PRD §6) ------------
SIMPLE_TEXT = "The quick brown fox jumps over the lazy dog."
PAUSE_A = "I want to test whether this system"
PAUSE_B = "keeps listening after a pause."
PUNCT_TEXT = "Hello, world! Does punctuation, like commas, question marks? It should."
MULTI_TEXTS = (
    "The weather looks good today.",
    "I need to buy some groceries.",
    "Let us meet at the cafe.",
)


def _token_overlap(hyp: str, ref: str) -> float:
    """Multiset token intersection / ref-length (case + punctuation insensitive). G-FUZZY.

    1.0 = perfect; PRD §6 mandates >=0.80 for espeak synthetic audio (do not chase 100%).
    """

    def toks(s: str) -> list[str]:
        return re.sub(rf"[{re.escape(string.punctuation)}]", " ", s.lower()).split()

    h, r = Counter(toks(hyp)), Counter(toks(ref))
    return (sum((h & r).values()) / len(r)) if r else 0.0


# ================================================================================================
# In-file test doubles (PRP Task 2). Pattern: tests/test_streaming_core.py's RecordingBackend /
# FakeFeedback (call recording, press_backspace(n<=0) NOT recorded) + monotonic timestamps +
# a simulated screen buffer. Called from two threads (the recorder's partial reader thread via
# on_partial, and the final-callback thread via commit) — everything is lock-guarded.
# ================================================================================================


@dataclasses.dataclass
class BackendEvent:
    """One timestamped backend keystroke + the simulated screen state AFTER it."""

    t: float  # time.monotonic() at the call
    kind: str  # "type" | "bs"
    text: str = ""  # payload for kind == "type"
    n: int = 0  # payload for kind == "bs"
    screen_after: str = ""  # simulated on-screen text after this event


class RecordingTypingBackend(TypingBackend):
    """Records (t, kind, payload) per call + maintains a simulated screen buffer.

    Screen model: type_text appends; press_backspace(n) deletes exactly n chars (floored at
    0). Thread-safe: the engine calls it from the partial reader thread AND the commit path
    (one internal lock — mirrors the engine's own serialization discipline).

    press_backspace(n <= 0) is a contract no-op and is NOT recorded (real backends spawn no
    subprocess for it — same rule as tests/test_streaming_core.py's RecordingBackend).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: list[BackendEvent] = []
        self._screen: str = ""

    def type_text(self, text: str) -> None:
        with self._lock:
            self._screen += text
            self.events.append(
                BackendEvent(time.monotonic(), "type", text=text, screen_after=self._screen)
            )

    def press_backspace(self, n: int) -> None:
        if n <= 0:
            return  # contract no-op — nothing recorded (see class docstring)
        with self._lock:
            self._screen = self._screen[: max(0, len(self._screen) - n)]
            self.events.append(BackendEvent(time.monotonic(), "bs", n=n, screen_after=self._screen))

    @property
    def screen(self) -> str:
        """Simulated on-screen text (what a real screen would show right now)."""
        with self._lock:
            return self._screen

    def reset(self) -> None:
        """Per-test: clear events + screen."""
        with self._lock:
            self.events.clear()
            self._screen = ""


class RecordingPromptedExecutor(prompt_engine.PromptedExecutor):
    """PromptedExecutor that records (t, prompt, use_prompt) around every transcribe() and
    every set_prompt() — the assert-(d) evidence (PRP Task 2).

    The warmup capability probe (probe_prompt_executor -> warmup) decodes via
    _transcribe_locked directly, so it does NOT appear in `decodes`; the t >= first-feed
    filter in test_d guards the case anyway (belt and suspenders, per the PRP gotcha).
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._rec_lock = threading.Lock()
        self.decodes: list[tuple[float, "str | None", bool]] = []
        self.prompts_set: list[tuple[float, "str | None"]] = []

    def transcribe(self, audio: object, language: "str | None" = None,
                   use_prompt: bool = True, **kwargs: object) -> object:
        with self._rec_lock:
            self.decodes.append((time.monotonic(), self.prompt, use_prompt))
        return super().transcribe(audio, language=language, use_prompt=use_prompt, **kwargs)

    def set_prompt(self, text: "str | None") -> None:
        with self._rec_lock:
            self.prompts_set.append((time.monotonic(), text))
        super().set_prompt(text)


class TimestampedFeedback:
    """FakeFeedback + monotonic stamps — the assert-(a) liveness oracle.

    StreamingOutput mirrors a string into update_partial() on EVERY on_partial path
    (extend, revise, suppressed, frozen), so a typing gap with a mirror update in it means
    "decoder alive, cycle suppressed" — legitimate — while a gap with NO mirror update means
    the decoder itself stalled — a failure (PRP gotcha / PRD T8a).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.partials: list[tuple[float, str]] = []

    def update_partial(self, text: str) -> None:
        with self._lock:
            self.partials.append((time.monotonic(), text))

    def reset(self) -> None:
        with self._lock:
            self.partials.clear()


# ================================================================================================
# The harness glue (PRP Task 4): daemon.on_final's streaming branch, extracted.
# ================================================================================================


class StreamingHarness:
    """Faithful extraction of daemon.on_final's streaming branch (daemon.py ~L1112-1256).

    The daemon-level wiring itself (locks, feedback.record_final, latency log, cancel
    window, drain flags) is unit-tested in tests/test_daemon.py; T8 adds the REAL decode
    stream through the REAL engine. Kept in the daemon's shape so S2 can extend with
    freeze/cancel semantics (asserts e/f/g) without rewiring:
      gate (listening) -> textproc.clean -> [rejected-final early return — S2 extends with
      the daemon's session-freeze] -> stream.commit -> stream.reset_boundary ->
      executor.set_prompt(rolling_context_prompt(stream.committed)) -> commit_log stamp.
    """

    def __init__(self, cfg: "VoiceTypingConfig") -> None:
        self.cfg = cfg
        self.executor: RecordingPromptedExecutor | None = None
        self.listening = threading.Event()  # the daemon's _listening gate (armed == set)
        # (t_commit_stamped, cleaned piece, ENGINE committed right after commit()) — the
        # engine truth is what the context prompt is sourced from (see committed_state_at).
        self.commit_log: list[tuple[float, str, str]] = []
        self.raw_finals: list[str] = []  # RAW finals (pre-clean) for consume-loop counting
        self.t_first_feed: float | None = None  # warmup-decode filter bound for (d)
        self.t_vad_start: float | None = None
        self.t_vad_stop: float | None = None
        self._build_stream()

    def _build_stream(self) -> None:
        self.backend = RecordingTypingBackend()
        self.feedback = TimestampedFeedback()
        self.stream = StreamingOutput(
            self.backend,
            self.feedback,
            self.cfg.output.streaming,
            append_space=self.cfg.output.append_space,
        )

    def attach_executor(self, executor: RecordingPromptedExecutor) -> None:
        self.executor = executor

    # --- recorder callbacks (G-REALTIME-CB) -----------------------------------------------------

    def on_partial(self, text: str) -> None:
        """Stabilized partials route straight into the production engine."""
        self.stream.on_partial(text)

    def on_vad_start(self) -> None:
        self.t_vad_start = time.monotonic()

    def on_vad_stop(self) -> None:
        self.t_vad_stop = time.monotonic()

    def note_feed(self) -> None:
        """Stamp the FIRST feed of the session (assert-(d) warmup filter bound)."""
        if self.t_first_feed is None:
            self.t_first_feed = time.monotonic()

    # --- the daemon-equivalent final path ---------------------------------------------------

    def on_final(self, text: str) -> None:
        """daemon.on_final's streaming branch (see class docstring for the mapping)."""
        if not self.listening.is_set():  # GATE: race guard parity with the daemon
            return
        cleaned = textproc.clean(text, self.cfg.filter)
        if not cleaned:
            # Rejected final (blocklist/min_chars). The daemon freezes (session) + resets the
            # boundary here; kept as a plain early return for S1 — S2 owns freeze/cancel
            # semantics (asserts e/f/g) and will mirror the daemon shape exactly.
            return
        self.stream.commit(cleaned)
        # Stamp BEFORE reset_boundary/set_prompt: any decode starting after this stamp must
        # observe this commit's prompt, so the (d) oracle timeline is race-free.
        commit_t = time.monotonic()
        engine_committed = self.stream.committed  # TYPED truth (guards may alter the final)
        self.commit_log.append((commit_t, cleaned, engine_committed))
        self.stream.reset_boundary()
        if self.executor is not None:
            self.executor.set_prompt(prompt_engine.rolling_context_prompt(engine_committed))

    # --- assert-(d) oracle helpers -----------------------------------------------------------

    def committed_state_at(self, t: float) -> str:
        """The ENGINE's committed (typed truth) after the last commit stamped < t.

        NOT the join of the cleaned pieces: the streaming guards legitimately alter a final
        before it is typed (a mid-paragraph spurious '.' is stripped, a mid-sentence start
        lower-cased — T8c), and the daemon's context-prompt source is stream.committed —
        the TYPED text (daemon._refresh_context_prompt). The (d) oracle must reconstruct
        exactly the string the glue fed set_prompt: the engine committed captured at each
        commit. Entries are chronological; the last one stamped < t is the state.
        """
        state = ""
        for ct, _piece, engine_committed in self.commit_log:
            if ct < t:
                state = engine_committed
        return state

    # --- per-test reset (PRP Task 4) -----------------------------------------------------------

    def reset(self) -> None:
        """Fresh stream/backend/feedback/commit state; executor prompt cleared + logs truncated."""
        self._build_stream()
        self.commit_log = []
        self.raw_finals = []
        self.t_first_feed = None
        self.t_vad_start = None
        self.t_vad_stop = None
        if self.executor is not None:
            self.executor.set_prompt(None)  # fresh session starts prompt-free (daemon parity)
            with self.executor._rec_lock:
                self.executor.decodes.clear()
                self.executor.prompts_set.clear()


# ================================================================================================
# Feed/consume/teardown plumbing (PRP Task 5) — tests/test_feed_audio.py shapes, verbatim where
# the invariants live (G-PACE / G-ORDER / G-ABORT / G-SHUTDOWN / G-TRAILING-SILENCE).
# ================================================================================================


def _safe_abort(rec: "AudioToTextRecorder") -> None:
    """rec.abort() on a HELPER thread (G-ABORT): swallow everything, never block the test."""
    try:
        rec.abort()
    except Exception:  # pragma: no cover — best-effort teardown
        pass


def _safe_shutdown(rec: "AudioToTextRecorder") -> None:
    """rec.shutdown() for the session-fixture teardown (G-SHUTDOWN): swallow, helper thread."""
    try:
        rec.shutdown()
    except Exception:  # pragma: no cover — best-effort teardown
        pass


def _wait_for(predicate: Callable[[], object], timeout: float = 30.0, interval: float = 0.05) -> bool:
    """Poll until predicate() is truthy or timeout (house style: tests/test_daemon.py)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


def _feed_paced(
    rec: "AudioToTextRecorder",
    samples_int16: "np.ndarray",
    harness: StreamingHarness,
    *,
    stop: threading.Event,
    chunk_s: float = 0.1,
    trailing_slices: int = 20,
) -> None:
    """Feed 16-bit mono @16k at ~real time so VAD wall-clock timing behaves (G-PACE).

    feed_audio is NON-blocking + re-slices to 32 ms internally; the wall-clock silence
    between slices is what lets the post_speech_silence threshold fire. The trailing silence
    is fed as paced 0.1 s slices — 20 of them (2.0 s >= 2x the 0.8 s
    lite_post_speech_silence_duration) — because one big zeros dump would drain in <1 ms of
    wall-clock and the stop threshold would never fire (G-TRAILING-SILENCE; see
    tests/test_feed_audio.py::_feed_paced for the full post-mortem).
    """
    assert _DEPS is not None
    np_ = _DEPS["np"]
    step = int(16000 * chunk_s)
    i = 0
    while i < len(samples_int16) and not stop.is_set():
        slc = samples_int16[i : i + step]
        if i == 0:
            harness.note_feed()  # assert-(d) warmup filter bound (first feed of the session)
        rec.feed_audio(slc, original_sample_rate=16000)
        i += step
        time.sleep(len(slc) / 16000.0)
    if not stop.is_set():
        zero_slice = np_.zeros(step, dtype=np_.int16)
        for _ in range(trailing_slices):
            if stop.is_set():
                break
            rec.feed_audio(zero_slice, original_sample_rate=16000)
            time.sleep(chunk_s)


def _run_streamed(
    rec: "AudioToTextRecorder",
    harness: StreamingHarness,
    wav: Path,
    want_finals: int,
    *,
    feed_timeout: float = 90.0,
) -> None:
    """Consume + feed one WAV through the harness; wait for want_finals RAW finals.

    No reset() here — tests own harness.reset() (test (b)'s bounded utt_punct retry
    deliberately CONTINUES the same session without resetting). G-ORDER: the consume thread
    starts before the first feed; teardown aborts via a helper thread (G-ABORT) and joins
    with timeouts (G-SHUTDOWN shape).
    """
    assert _DEPS is not None
    sf = _DEPS["sf"]
    harness.listening.set()
    samples, _sr = sf.read(str(wav), dtype="int16")  # 16k mono int16 (soxi-confirmed)
    n0 = len(harness.raw_finals)
    stop = threading.Event()

    def cb(text: str) -> None:
        # RAW final first (count for the consume loop), then the daemon-equivalent path.
        harness.raw_finals.append(text)
        harness.on_final(text)

    def _count() -> int:
        return len(harness.raw_finals)

    cons = threading.Thread(
        target=_consume, args=(rec, cb, stop, _count, n0 + want_finals), daemon=True
    )
    cons.start()  # G-ORDER: consume arms listening BEFORE feed
    feed = threading.Thread(
        target=_feed_paced, args=(rec, samples, harness), kwargs={"stop": stop}, daemon=True
    )
    feed.start()
    try:
        assert _wait_for(
            lambda: len(harness.raw_finals) >= n0 + want_finals, timeout=feed_timeout
        ), f"expected {want_finals} finals, got {harness.raw_finals!r}"
        time.sleep(0.5)  # let any in-flight partial settle before the asserts read state
    finally:
        stop.set()
        # G-ABORT: abort() from a HELPER thread (blocks on was_interrupted.wait(), which is
        # only set INSIDE text()); the test thread joins it with a timeout.
        abort_thread = threading.Thread(target=_safe_abort, args=(rec,), daemon=True)
        abort_thread.start()
        abort_thread.join(timeout=10.0)
        cons.join(timeout=5.0)
        feed.join(timeout=5.0)


def _consume(
    rec: "AudioToTextRecorder",
    cb: Callable[[str], None],
    stop: threading.Event,
    count: Callable[[], int],
    want: int,
) -> None:
    while count() < want and not stop.is_set():
        # text(cb) BLOCKS until ONE utterance finalizes; cb fires async with the RAW text.
        rec.text(cb)


# ================================================================================================
# Diagnostics: every failing assert dumps the event/partial/decode log (PRP Task 6-8).
# ================================================================================================


def _dump_events(harness: StreamingHarness, limit: int = 300) -> str:
    lines = ["--- backend events (tail) ---"]
    for e in harness.backend.events[-limit:]:
        lines.append(f"  t={e.t:.3f} {e.kind} text={e.text!r} n={e.n} screen={e.screen_after!r}")
    lines.append("--- feedback mirror partials (tail) ---")
    for t, s in harness.feedback.partials[-limit:]:
        lines.append(f"  t={t:.3f} {s!r}")
    lines.append("--- commit log ---")
    for t, s in harness.commit_log:
        lines.append(f"  t={t:.3f} {s!r}")
    if harness.executor is not None:
        lines.append("--- executor decodes (tail) ---")
        for t, p, u in harness.executor.decodes[-limit:]:
            lines.append(f"  t={t:.3f} use_prompt={u} prompt={p!r}")
    lines.append("--- engine state ---")
    lines.append(
        f"  committed={harness.stream.committed!r} tail={harness.stream.tail!r} "
        f"frozen={harness.stream.frozen} screen={harness.backend.screen!r}"
    )
    return "\n".join(lines)


# ================================================================================================
# Assert-(b) invariant helpers (exact oracles over the harness's OWN event stream).
# ================================================================================================


def _assert_commit_invariants(harness: StreamingHarness, refs: list[str]) -> None:
    """Exact screen/rewind invariants over the WHOLE run (PRD T8b), + per-piece fuzzy (G-FUZZY).

    The EXACT oracle is the ENGINE's committed truth (what commit() actually typed + the
    trailing space), captured by the harness at each commit — the cleaned final may differ
    from it because the guards alter mid-paragraph punctuation by design (T8c).

    1. The capture is live: the engine's CURRENT committed == the last captured truth.
    2. Every commit window contains its trailing type_text(" ").
    3. EVERY backspace deletes exactly the pending tail:
       n == len(screen_before) - len(engine_committed_at_event_time).
    4. Replaying the recorded keystrokes up to each commit stamp lands EXACTLY on that
       commit's engine committed — the on-screen truth the engine believes (stale partials
       that slip in after a commit are typed on top and would break this; by engine design
       the NEXT commit's rewind deletes exactly them, so between-commit junk is legal but
       AT-commit junk is not).
    5. End state: screen == committed + engine tail (engine's own public invariant).
    6. Per-piece fuzzy: each CLEANED piece overlaps its pinned reference >=0.80 (G-FUZZY;
       model output — never exact-matched).
    """
    events = harness.backend.events
    commits = harness.commit_log
    assert commits, "no commits recorded\n" + _dump_events(harness)
    pieces = [piece for _, piece, _ in commits]
    engine_truths = [ec for _, _, ec in commits]

    # 1. the harness capture mirrors the live engine state (exact)
    assert harness.stream.committed == engine_truths[-1], (
        f"engine committed {harness.stream.committed!r} != last captured "
        f"{engine_truths[-1]!r}\n" + _dump_events(harness)
    )

    # 2. every commit typed its trailing space
    for k, (ct, _piece, _ec) in enumerate(commits):
        prev_t = commits[k - 1][0] if k else float("-inf")
        win = [e for e in events if prev_t < e.t <= ct]
        assert any(e.kind == "type" and e.text == " " for e in win), (
            f"commit {k} ({pieces[k]!r}) has no trailing type_text(' ') in its window\n"
            + _dump_events(harness)
        )

    # 3. EVERY backspace rewinds exactly the pending tail (commit-time AND mid-utterance
    #    revises — the engine only ever deletes typed-since-checkpoint text).
    screen = ""
    ci = 0
    for e in events:
        while ci < len(commits) and commits[ci][0] < e.t:
            ci += 1
        committed_prefix = engine_truths[ci - 1] if ci else ""
        if e.kind == "bs":
            n_expected = max(0, len(screen) - len(committed_prefix))
            assert e.n == n_expected, (
                f"backspace n={e.n} != pending tail {n_expected} "
                f"(screen {screen!r} vs committed {committed_prefix!r})\n" + _dump_events(harness)
            )
        screen = e.screen_after

    # 4. at each commit stamp the replayed keystrokes land exactly on the engine's committed
    for k, (ct, _piece, ec) in enumerate(commits):
        replay = ""
        for e in events:
            if e.t > ct:
                break
            replay = e.screen_after
        assert replay == ec, (
            f"after commit {k}: screen {replay!r} != engine committed {ec!r}\n"
            + _dump_events(harness)
        )

    # 5. end state: screen == committed + pending tail (nothing else may be on screen)
    assert harness.backend.screen == harness.stream.committed + harness.stream.tail, (
        f"screen {harness.backend.screen!r} != committed+tail "
        f"{harness.stream.committed + harness.stream.tail!r}\n" + _dump_events(harness)
    )

    # 6. per-piece fuzzy vs the pinned references (G-FUZZY — model output, never exact)
    assert len(pieces) == len(refs), (
        f"{len(pieces)} commits vs {len(refs)} pinned references: {pieces!r}\n"
        + _dump_events(harness)
    )
    for i, (piece, ref) in enumerate(zip(pieces, refs)):
        assert _token_overlap(piece, ref) >= 0.80, (
            f"commit {i} fuzzy {piece!r} vs {ref!r}\n" + _dump_events(harness)
        )


def _has_revising_commit(harness: StreamingHarness) -> bool:
    """True iff some commit REVISED (rewound a non-empty tail, then retyped the full final).

    Event signature within one commit window: [bs(n>0)] [type(guarded final)] [type(" ")] —
    i.e. a bs immediately followed by exactly those two type events. An extending/fresh
    commit has NO bs right before the retype.
    """
    events = harness.backend.events
    for k, (ct, _piece, _ec) in enumerate(harness.commit_log):
        prev_t = harness.commit_log[k - 1][0] if k else float("-inf")
        win = [e for e in events if prev_t < e.t <= ct]
        for i, e in enumerate(win):
            if e.kind != "bs":
                continue
            rest = win[i + 1 :]
            if (
                len(rest) == 2
                and rest[0].kind == "type"
                and rest[0].text.strip()
                and rest[1].kind == "type"
                and rest[1].text == " "
            ):
                return True
    return False


# ================================================================================================
# The session fixture (PRP Task 3): production wiring + executor injection.
# ================================================================================================


@pytest.fixture(scope="session")
def stream_recorder() -> "Iterator[tuple[AudioToTextRecorder, StreamingHarness]]":
    """ONE session-scoped recorder via the PRODUCTION build path (T8's 'lite recorder child',
    in-process): cfg_to_kwargs -> callbacks -> augment_kwargs_with_executor(factory seam) ->
    _filter_kwargs_to_signature -> construct. Mirrors recorder_host._worker_main's build order.

    Skips cleanly (never errors, G-SKIP-GUARDS) when deps are absent, the executor probe
    fails (CPU-only/clone box — assert (d) would be unverifiable), or construction fails.
    Teardown: shutdown() on a helper daemon thread, join(30) (G-SHUTDOWN).
    """
    global _DEPS
    try:
        deps = _load_deps()
    except Exception as exc:  # pragma: no cover — CPU-only/clone box without deps
        pytest.skip(f"heavy deps unavailable: {exc!r}")
    _DEPS = deps
    daemon = deps["daemon"]  # type: ignore[assignment]
    recorder_host = deps["recorder_host"]  # type: ignore[assignment]
    AudioToTextRecorder = deps["AudioToTextRecorder"]  # type: ignore[assignment]
    cfg = deps["VoiceTypingConfig"]()  # defaults: streaming=True, context_prompt=True,
    # lite_model="small.en" -> cfg_to_kwargs gives ONE small.en (use_main_model_for_realtime).
    harness = StreamingHarness(cfg)
    resolved = daemon._resolve_device_config(cfg)
    kwargs = daemon.cfg_to_kwargs(cfg, resolved=resolved)
    kwargs["use_microphone"] = False  # THE feed_audio override (PRD T8: no mic)
    kwargs.update(
        {
            "on_realtime_transcription_stabilized": harness.on_partial,  # G-REALTIME-CB
            "on_vad_start": harness.on_vad_start,
            "on_vad_stop": harness.on_vad_stop,
            "no_log_file": True,  # G-NOLOGFILE
        }
    )

    holder: list[RecordingPromptedExecutor] = []

    def recording_factory(model: str, device: str, compute_type: str) -> RecordingPromptedExecutor:
        ex = RecordingPromptedExecutor(model_name=model, device=device, compute_type=compute_type)
        holder.append(ex)
        return ex

    # BEFORE the signature filter (recorder_host._worker_main order); probes 1 s of zeros.
    executor = recorder_host.augment_kwargs_with_executor(
        kwargs, cfg, resolved, logger, executor_factory=recording_factory
    )
    if executor is None:
        # cfg.asr.context_prompt is true by default, so None == probe failure (degrade path).
        # Assert (d) is unverifiable without the armed executor — skip, don't fail.
        pytest.skip("context-prompt executor not armed (probe failed); assert (d) unverifiable")
    assert holder and holder[0] is executor
    harness.attach_executor(executor)
    assert kwargs.get("transcription_executor") is executor, "executor not armed into kwargs"
    assert kwargs.get("realtime_transcription_executor") is executor

    filtered = daemon._filter_kwargs_to_signature(kwargs, AudioToTextRecorder)
    try:
        rec = AudioToTextRecorder(**filtered)
    except Exception as exc:  # pragma: no cover — models/engine absent
        pytest.skip(f"AudioToTextRecorder construction failed (models/engine unavailable): {exc!r}")
    yield rec, harness
    # G-SHUTDOWN teardown (never rec.abort() inline — see test_feed_audio.py's fixture).
    shutdown_thread = threading.Thread(target=_safe_shutdown, args=(rec,), daemon=True)
    shutdown_thread.start()
    shutdown_thread.join(timeout=30.0)


# ================================================================================================
# T8 (a): delta cadence + delta-only extends.
# ================================================================================================


def test_a_delta_cadence(
    stream_recorder: "tuple[AudioToTextRecorder, StreamingHarness]",
) -> None:
    """T8(a): typed deltas arrive >=1 per 500 ms while speech streams; >=1 extend cycle types
    ONLY the delta (no backspace in that cycle); overall content fuzzy-matches the fixture."""
    rec, harness = stream_recorder
    harness.reset()
    _run_streamed(rec, harness, _WAVS["simple"], want_finals=1)

    events = harness.backend.events
    assert events, "no backend events at all (streaming wired? G-REALTIME-CB)\n" + _dump_events(
        harness
    )
    types = [e for e in events if e.kind == "type"]
    assert harness.commit_log, "no commit for utt_simple\n" + _dump_events(harness)
    commit_t = harness.commit_log[0][0]
    win = [e for e in types if e.t <= commit_t]
    assert len(win) >= 3, (
        f"expected >=3 typed deltas before the commit, got {len(win)}\n" + _dump_events(harness)
    )

    # Cadence: consecutive typing gaps <= 0.5 s, OR a feedback-mirror partial arrived in the
    # gap (suppressed/rate-limited/frozen cycle — decoder alive, mirror updated, keystrokes
    # legitimately withheld). A gap with NO mirror update == decoder stall == failure.
    mirror_stamps = [t for t, _ in harness.feedback.partials]
    for e1, e2 in zip(win, win[1:]):
        gap = e2.t - e1.t
        if gap > 0.5:
            assert any(e1.t < ts <= e2.t for ts in mirror_stamps), (
                f"typing gap {gap:.2f}s with no feedback-mirror update in "
                f"({e1.t:.3f}, {e2.t:.3f}] — decoder stalled (T8a)\n" + _dump_events(harness)
            )

    # Delta-only extends: a type event whose IMMEDIATELY preceding backend event is another
    # type event extending the screen (pure append — no backspace since the previous
    # keystroke). By the screen model, the payload is exactly the on-screen suffix delta.
    extends = []
    for prev, e in zip(events, events[1:]):
        if e.kind == "type" and prev.kind == "type":
            if (
                prev.screen_after
                and e.screen_after.startswith(prev.screen_after)
                and len(e.screen_after) > len(prev.screen_after)
            ):
                extends.append(e)
    assert extends, (
        "no delta-only extend cycle observed (every cycle was a full rewind?)\n"
        + _dump_events(harness)
    )

    # Overall typed content fuzzy >=0.80 vs the pinned fixture text (G-FUZZY).
    screen_now = harness.backend.screen.strip()
    assert _token_overlap(screen_now, SIMPLE_TEXT) >= 0.80, (
        f"typed content {screen_now!r} vs {SIMPLE_TEXT!r}\n" + _dump_events(harness)
    )


# ================================================================================================
# T8 (b): commit correction exactness.
# ================================================================================================


def test_b_commit_rewind_exact(
    stream_recorder: "tuple[AudioToTextRecorder, StreamingHarness]",
) -> None:
    """T8(b): every commit leaves the simulated screen EXACTLY at the committed-so-far
    reconstruction (guarded final + trailing space); every rewind deletes EXACTLY the pending
    tail; >=1 revising commit occurs (bounded utt_punct retry before failing)."""
    rec, harness = stream_recorder
    harness.reset()
    refs: list[str] = list(MULTI_TEXTS)
    _run_streamed(rec, harness, _WAVS["multi"], want_finals=3)
    if not _has_revising_commit(harness):
        # Real-model nondeterminism: a differing commit cannot be forced with espeak audio.
        # Bounded retry: ONE more utterance (utt_punct) in the SAME session — committed text
        # accumulates, the invariants below cover the whole event stream either way.
        refs.append(PUNCT_TEXT)
        _run_streamed(rec, harness, _WAVS["punct"], want_finals=1)
    assert _has_revising_commit(harness), (
        "no revising commit (a commit that rewound a non-empty tail) across "
        f"{len(harness.commit_log)} commits\n" + _dump_events(harness)
    )
    _assert_commit_invariants(harness, refs)


# ================================================================================================
# T8 (d): the rolling context prompt on decodes.
# ================================================================================================


def test_d_decode_prompts(
    stream_recorder: "tuple[AudioToTextRecorder, StreamingHarness]",
) -> None:
    """T8(d): every post-warmup use_prompt decode carries initial_prompt ==
    rolling_context_prompt(ENGINE-committed-at-decode-time) — non-empty mid-paragraph
    (when the committed tail has no terminator yet), empty after a commit whose committed
    truth ends a sentence, always <=200 tokens. See module docstring: the oracle is the
    engine's TYPED truth, and the empty/non-empty case per window follows it."""
    rec, harness = stream_recorder
    assert harness.executor is not None
    harness.reset()
    _run_streamed(rec, harness, _WAVS["pause"], want_finals=2)  # PAUSE_A has NO terminator
    _run_streamed(rec, harness, _WAVS["multi"], want_finals=3)  # every sentence ends '.'

    ex = harness.executor
    assert ex.prompts_set, "set_prompt never ran (the commit glue did not refresh)\n" + _dump_events(
        harness
    )
    assert harness.t_first_feed is not None
    decodes = [
        (t, p, u)
        for (t, p, u) in ex.decodes
        if u and harness.t_first_feed is not None and t >= harness.t_first_feed
    ]
    assert decodes, (
        f"no post-warmup use_prompt decodes recorded ({len(ex.decodes)} total)\n"
        + _dump_events(harness)
    )

    # The oracle: the harness's OWN engine-committed timeline (deterministic — no model
    # output enters it; see StreamingHarness.committed_state_at for why it is the TYPED
    # truth, not the cleaned pieces).
    for t, prompt, _u in decodes:
        expected = prompt_engine.rolling_context_prompt(harness.committed_state_at(t))
        assert (prompt or "") == expected, (
            f"decode at t={t:.3f}: prompt={prompt!r} != expected {expected!r}\n"
            + _dump_events(harness)
        )
        assert len((prompt or "").split()) <= prompt_engine._PROMPT_TOKEN_CAP, (
            f"prompt over cap at t={t:.3f}: {prompt!r}\n" + _dump_events(harness)
        )

    # Per-window case checks (PRD §4.2quater rule 2, against the engine's committed truth):
    # window k = decodes after commit k's prompt refresh, before commit k+1's. Whether the
    # prompt there is empty or not follows the ENGINE truth (model punctuation of espeak
    # audio is nondeterministic), so each window is asserted per its own expected value; the
    # mid-paragraph non-empty case must occur >=1 time across the pause+multi session.
    assert len(harness.commit_log) >= 5, (
        f"expected 2 pause + 3 multi commits, got {harness.commit_log!r}\n" + _dump_events(harness)
    )
    stamps = [ct for ct, _, _ in harness.commit_log]
    nonempty_windows = 0
    for k in range(len(harness.commit_log)):
        w_start = stamps[k]
        w_end = stamps[k + 1] if k + 1 < len(stamps) else None
        expected_k = prompt_engine.rolling_context_prompt(harness.commit_log[k][2])
        win = [
            (t, p) for t, p, _u in decodes if t >= w_start and (w_end is None or t < w_end)
        ]
        if not win:
            continue
        if expected_k:
            nonempty_windows += 1
            assert all(p for _, p in win), (
                f"window {k}: expected non-empty prompts {expected_k!r}, got {win!r}\n"
                + _dump_events(harness)
            )
            if k == 0:  # utt_pause's first half -> the committed-first-half fuzzy case
                assert _token_overlap(" ".join(p for _, p in win), PAUSE_A) >= 0.80, (
                    f"window 0 prompts {win!r} vs {PAUSE_A!r}\n" + _dump_events(harness)
                )
        else:
            assert all(not p for _, p in win), (
                f"window {k}: committed truth ends a sentence, expected empty prompts, "
                f"got {win!r}\n" + _dump_events(harness)
            )
    assert nonempty_windows >= 1, (
        "every inter-commit window ran with an empty prompt — the non-empty "
        "mid-paragraph case (PRD §4.2quater rule 2) was never exercised\n"
        + _dump_events(harness)
    )

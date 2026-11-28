"""voice_typing.prompt_engine — child-side dynamic context-prompt transcription executor.

P1.M2.T5.S1 (PRD §4.2quater "Rolling context prompt"): Whisper decodes each utterance as a
fresh sentence, so mid-paragraph fragments come out capitalized with spurious trailing
punctuation. The fix is conditioning EVERY decode (realtime partials AND commit/final passes)
on the rolling committed context — a runtime-mutable `initial_prompt`.

WHY AN EXECUTOR (verified line-by-line against the installed RealtimeSTT 1.0.2):
  - `initial_prompt` / `initial_prompt_realtime` are constructor-STATIC in RealtimeSTT (its
    transcription worker copies them at spawn), and on our single-model path
    (use_main_model_for_realtime=True) even the realtime-engine attribute poke is unavailable —
    post-construction attribute assignment is inert. BUT RealtimeSTT accepts EXTERNAL
    transcription executors: AudioToTextRecorder(transcription_executor=...,
    realtime_transcription_executor=...) — and BOTH decode paths route through it:
      * finals: core/transcription.py call_transcription_executor() calls
        executor.transcribe(audio, language=..., use_prompt=...) on an in-process thread;
      * realtime partials: core/realtime.py _transcribe_with_main_model() checks
        _uses_external_transcription_executor FIRST, even under use_main_model_for_realtime=True.
    With an executor set, RealtimeSTT never spawns its TranscriptionWorker process
    (core/initialization.py sets transcript_process = None) — so ONE PromptedExecutor owns the
    ONE faster-whisper model for partials AND finals (PRD §4.2quater single-mode; the built-in
    warmup lives in that skipped worker, so executor warmup is OUR job — hence the probe).
  - Executor call contract: transcribe(audio, language=None, use_prompt=True) returning an
    object with .text and .info; the consumer reads .info.language /
    .info.language_probability (core/transcription_api.py:113-115).

SEED vs ROLLING CONTEXT (§4.8.1, P1.M1.T2.S4): the initial-prompt SEED is pre-caret editor
text installed ONCE by a confirmed prime (the fenced start seam) and used only until the
session's FIRST accepted final — it is recognition-only conditioning and is never mixed
into the rolling source. The ROLLING source is this session's accepted finals only (the
daemon-side accumulator; see daemon._handoff_context_prompt / _refresh_context_prompt),
delivered via rolling_context_prompt() below — the handoff's replacement target. Neither
the seed nor dictated text is ever logged with content (word counts only).

IMPORT PURITY: this module is importable ANYWHERE — module scope is stdlib-only (dataclasses,
enum, logging, threading); faster_whisper + numpy are imported LAZILY inside methods, so importing
the module never touches CUDA. The executor OBJECTS, however, own CUDA contexts and are not
picklable: they are CONSTRUCTED only inside the recorder-host child process (P1.M2.T5.S1
wiring in recorder_host.augment_kwargs_with_executor) and never cross the spawn IPC.
"""

from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Defensive prompt cap (PRD §4.2quater): Whisper accepts an initial_prompt of up to ~224
# tokens; 200 whitespace words is a cheap conservative proxy (a CODE CONSTANT per the PRP —
# tuning it is a deliberate change, not a config knob). Keeps prompt + audio inside the
# decoder window on even long utterances.
_PROMPT_TOKEN_CAP = 200

# Sentence terminators that end the rolling context window (P1.M2.T5.S2). Pinned
# verbatim to textproc._SENTENCE_TERMINALS (repo convention — streaming.py pins
# the same copy for its slicer); the three sets must never drift apart.
_CONTEXT_BOUNDARY_CHARS = ".!?"

# Capability-probe warmup: 1 s of 16 kHz float32 zeros — enough to force the model build +
# CUDA context init + one full encode/decode pass, so probe failures surface at READY time
# instead of on the first arm.
_WARMUP_SAMPLE_RATE = 16000
_WARMUP_SECONDS = 1.0


@dataclass
class TranscriptionInfo:
    """Duck-typed stand-in for RealtimeSTT's transcription_engines.base.TranscriptionInfo.

    Upstream reads result.info.language / result.info.language_probability only. A local copy
    (NOT an import: `import RealtimeSTT` pulls torch/CUDA into the importing process, which
    would break the daemon's import purity) so the empty-result degrade path always has an
    info object. When faster_whisper runs for real, its own richer info object passes
    straight through this field (structural typing — consumers only read attributes).
    """

    language: str | None = None
    language_probability: float = 0.0


@dataclass
class TranscriptionResult:
    """Duck-typed stand-in for RealtimeSTT's transcription_engines.base.TranscriptionResult.

    call_transcription_executor accepts ANY object from executor.transcribe(); the finals
    consumer reads .text (and .info per above). Structurally identical to the upstream
    dataclass (text: str, info with a default).
    """

    text: str
    info: Any = field(default_factory=TranscriptionInfo)


@dataclass(frozen=True)
class PromptProbeResult:
    """Startup capability-probe outcome — drives arm-vs-degrade in recorder_host.

    ok=True  -> the executor is warm; arm it into the recorder kwargs.
    ok=False -> `error` carries repr(exc); recorder_host logs ONE INFO degrade line and
                builds the recorder with stock (context-free) kwargs — never a crash.
    """

    ok: bool
    error: str | None = None


def trim_prompt(text: str, cap: int = _PROMPT_TOKEN_CAP) -> str:
    """Whitespace-normalize `text` and keep only the NEWEST `cap` whitespace tokens.

    Pure function (unit-tested). Split on whitespace; when more than `cap` tokens, keep the
    TAIL — the newest words are the live sentence context ("continuing, not starting"), the
    oldest words are the first to go. Rejoined with single spaces (canonical form). Non-str
    input or cap <= 0 degrades safely: "" (tokens[-0:] would wrongly keep everything, so the
    guard is explicit).
    """
    if cap <= 0:
        return ""
    tokens = (text or "").split()
    if len(tokens) <= cap:
        return " ".join(tokens)
    return " ".join(tokens[-cap:])


def rolling_context_prompt(committed: str) -> str:
    """The formal daemon-side rolling context prompt (PRD §4.2quater; P1.M2.T5.S2).

    The committed text back to the last sentence boundary, whitespace-normalized,
    capped to the NEWEST _PROMPT_TOKEN_CAP tokens (via trim_prompt — the child
    caps again in set_prompt: defense in depth, same constant):
      - terminator mid-string       -> the text after it (the in-progress sentence);
      - committed ENDS with one     -> "" (fresh sentence — decoder may capitalize);
      - NO terminator anywhere      -> the WHOLE committed text (capped). This is
        the T8c pause-join case: a long unpunctuated run still conditions the
        next decode (the old thin-seam slicer returned "" here — superseded).

    PURE: no I/O, no state, deterministic, stdlib-only. Never raises — None or
    empty input degrades to "". The rfind lives HERE, not in the caller: the
    composition `context_after_last_boundary(c) or trim_prompt(c)` is WRONG
    because "" is ambiguous between the ends-with-terminator case (prompt stays
    empty) and the no-boundary case (prompt must be everything).

    P1.M1.T2.S4: this is also the SEED-handoff target — the first accepted final
    of a seeded session replaces the resident seed with
    rolling_context_prompt(session_accepted) (or "" when the rolling prompt is
    disabled), after which every commit refreshes from the same accepted-finals
    source.
    """
    committed = committed or ""
    last = max(committed.rfind(ch) for ch in _CONTEXT_BOUNDARY_CHARS)
    source = committed[last + 1 :] if last >= 0 else committed
    return trim_prompt(source)


# --- §4.8.1 initial-prompt seed: confirmed install primitives (P1.M1.T2.S1) -----------------


class PromptState(str, enum.Enum):
    """Tri-state outcome of a CONFIRMED prompt install — never a bare boolean.

    APPLIED     -> the fitted prompt is installed on a WARMED executor; the token bound is
                   proven against the same model object the decode will use.
    CLEAR       -> the prompt is None on a WARMED executor (proven — the decode sees no prompt).
    UNCONFIRMED -> the executor is cold, the tokenizer/model is missing or broken, or the fit
                   failed: UNKNOWN, not "unavailable" (the arch-note distinction — a timeout/
                   partial update/ambiguous old child must land here too). The install still
                   forces the stored prompt to None so the decode degrades to context-free
                   (PRD §8 fail-closed) — but the caller cannot treat the state as known.
    """

    APPLIED = "applied"
    CLEAR = "clear"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True)
class PromptInstallResult:
    """What install_initial_prompt() reports — SAFE TO LOG/ACK: counts only, never text.

    `tokens` is the fitted prompt's token count (an int) when state == APPLIED, else None.
    There is deliberately no text field: the seed is user dictation and must never leak into
    logs, ACKs, exceptions or repr()s.
    """

    state: PromptState
    tokens: int | None = None


def prompt_token_budget(model: Any) -> int | None:
    """The initial-prompt token budget, READ FROM THE WARMED MODEL — never a copied literal.

    faster-whisper's get_prompt() keeps `previous_tokens[-(max_length // 2 - 1):]` — an
    over-long initial_prompt is silently LEFT-CLIPPED (the OLDEST tokens dropped, the exact
    opposite of what a newest-context seed wants), so we fit to that same formula up front.
    Returns None when the model exposes no usable integer max_length (cold / wrong attribute
    shape → the caller must fail closed to UNCONFIRMED, never guess). 448 → 223 on the
    installed faster-whisper; the value is DERIVED from the warmed model at runtime.
    """
    ml = getattr(model, "max_length", None)
    if isinstance(ml, bool) or not isinstance(ml, int):
        return None
    budget = ml // 2 - 1
    return budget if budget >= 1 else None


def fit_initial_prompt(
    text: str,
    *,
    encode: Callable[[str], list[int]],
    decode: Callable[[Any], str],
    budget: int,
) -> str:
    """Fit the §4.8.1 seed to the model's prompt budget: keep the NEWEST token-aligned tail.

    PURE (unit-tested) and sentence-cut-FREE: unlike rolling_context_prompt — which slices at
    .?! (the ROLLING path's rule once finals exist) — the seed is pre-caret editor text and
    is fitted purely by tokens; the .?! characters carry no special meaning here.

    Algorithm: whitespace-normalize; encode; if the token count is within budget, return the
    normalized text. Otherwise binary-search the smallest cut whose suffix (a) round-trips
    the codepoints — decode(prefix) + decode(suffix) == decode(all), so a multi-token
    codepoint or emoji ZWJ sequence can never be cut in half — and (b) re-encodes to <=
    budget tokens, then refines downward token by token to grab back everything the budget
    still allows. Returns "" (NEVER raises) on non-str input, budget < 1, non-callable
    encode/decode, empty input, or when no codepoint-safe suffix fits.
    """
    try:
        if budget is None or budget < 1 or not callable(encode) or not callable(decode):
            return ""
        if not isinstance(text, str):
            return ""
        norm = " ".join(text.split())
        if not norm:
            return ""
        toks = encode(norm)
        total = len(toks)
        if total <= budget:
            return norm
        full = decode(toks)

        def fits(cut: int) -> bool:
            suffix = toks[cut:]
            if not suffix:
                return False
            decoded_suffix = decode(suffix)
            if cut > 0 and decode(toks[:cut]) + decoded_suffix != full:
                return False  # the cut would split a codepoint / emoji sequence
            return len(encode(decoded_suffix)) <= budget

        # The search's upper bound must be a FEASIBLE cut: scanning down from the last token
        # skips the tail's partial codepoint group (a cut inside the final multi-token emoji
        # would decode with replacement glue and can never round-trip). The scan is bounded
        # by the group size (a few tokens for real BPE).
        hi = total - 1
        while hi > 0 and not fits(hi):
            hi -= 1
        if not fits(hi):
            return ""
        lo = 0
        while lo < hi:
            mid = (lo + hi) // 2
            if fits(mid):
                hi = mid
            else:
                lo = mid + 1
        cut = hi
        while cut > 0 and fits(cut - 1):
            cut -= 1
        return decode(toks[cut:])
    except Exception:  # noqa: BLE001 — pure helper: the caller degrades (UNCONFIRMED), never crashes
        return ""


def utf8_suffix_within(text: str, max_bytes: int = 4096) -> str:
    """The longest codepoint-aligned suffix of `text` whose UTF-8 encoding is <= max_bytes.

    Pure, never raises (non-str or max_bytes <= 0 → ""; a codepoint that cannot encode, e.g.
    a lone surrogate, is dropped along with everything before it). Walks codepoints from the
    END accumulating byte lengths, so a 4-byte emoji at the edge is included whole or
    excluded whole — never half. This is the §4.8.1 ADAPTER-side input bound (the seed may
    cross the recorder IPC as at most 4 KiB of UTF-8), validated separately from the model
    token budget (prompt_token_budget/fit_initial_prompt above).
    """
    if not isinstance(text, str) or max_bytes <= 0:
        return ""
    total = 0
    i = len(text)
    while i > 0:
        try:
            b = len(text[i - 1].encode("utf-8"))
        except UnicodeEncodeError:  # unencodable codepoint: exclude it and everything before
            break
        if total + b > max_bytes:
            break
        total += b
        i -= 1
    return text[i:]


class PromptedExecutor:
    """Object-style RealtimeSTT executor: ONE faster-whisper model + a thread-safe mutable prompt.

    The child passes the SAME instance as BOTH transcription_executor and
    realtime_transcription_executor (one object == one model instance serving partials and
    finals; RealtimeSTT skips its TranscriptionWorker process entirely).

    Threading: RealtimeSTT calls transcribe() from the realtime-partial thread AND from the
    external-final threads concurrently — every model access holds self._lock. Prompt updates
    (set_prompt) happen between utterances from the child's command loop; the decode reads the
    current value under the lock, so no decode ever sees a half-updated prompt.

    Failure contract (PRD §8 "degrade to context-free decoding + log, never crash"):
    transcribe() NEVER raises — any failure is logged (WARNING + traceback) and an empty
    result is returned. warmup() is the deliberate exception: it RAISES so the startup
    capability probe can distinguish healthy from broken and degrade BEFORE the recorder is
    built.

    Prompt installation has two deliberate paths (P1.M1.T2.S1): set_prompt() is the ordinary
    BEST-EFFORT rolling update — it swallows failures and keeps the previous prompt, so its
    success can never be treated as confirmation. install_initial_prompt() is the CONFIRMED
    §4.8.1 seed path: it fits the seed to the warmed model's REAL token budget (read from
    the model, never a copied constant), installs it under the lock, and returns a tri-state
    PromptInstallResult (applied / clear / unconfirmed + token count — never text).
    UNCONFIRMED forces the stored prompt to None (fail-closed to context-free), never
    raises, and never logs seed content — counts and exception TYPE names only.
    """

    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        beam_size: int = 5,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._model: Any = (
            None  # faster_whisper.WhisperModel — built lazily (CUDA import)
        )
        self._prompt: str | None = None
        self._lock = threading.Lock()

    # --- prompt management (child cmd ("prompt", {"text": ...}) -> set_prompt) -----------

    def set_prompt(self, text: str | None) -> None:
        """Replace the rolling context prompt (whitespace-trimmed to the cap). None/"" clears.

        Never raises (a bad update is logged and the previous prompt kept) and never logs the
        prompt TEXT above DEBUG — it is user dictation content.
        """
        try:
            trimmed = trim_prompt(text) if text else None
            self._prompt = trimmed
            logger.debug(
                "context-prompt: set (%d words)",
                0 if trimmed is None else len(trimmed.split()),
            )
        except Exception:  # noqa: BLE001 — prompt updates must never break the cmd loop
            logger.exception("context-prompt: set_prompt failed (previous prompt kept)")

    def install_initial_prompt(self, text: str | None) -> PromptInstallResult:
        """CONFIRMED §4.8.1 seed install — the observable counterpart of best-effort set_prompt.

        Semantics (all under self._lock — the SAME lock the decode's prompt read takes, so a
        decode never sees a half-updated prompt):
          - text with content AND a WARMED self._model: fit the seed to the model's real
            prompt budget (fit_initial_prompt — newest tokens, token-boundary/codepoint-safe,
            no sentence cut), install it, report APPLIED with the token count. APPLIED is
            honest because the budget + tokenizer consulted are the SAME warmed model object
            _transcribe_locked will use for the next decode.
          - None/"" on a WARMED executor: CLEAR — prompt None, proven.
          - Cold model (warmup not done), missing/broken tokenizer or budget, non-str text,
            or ANY failure: UNCONFIRMED — unknown, not "unavailable" — with the stored prompt
            forced to None (fail-closed: the decode degrades to context-free, PRD §8).

        Never raises; never builds the model here (that would import CUDA on the caller's
        thread — warmup() owns model construction); NEVER logs or returns the seed text
        (counts and exception TYPE names only — the seed is user dictation).
        """
        with self._lock:
            model = self._model
            if model is None:
                self._prompt = None  # cold: nothing is provable — fail closed to no prompt
                logger.debug("context-prompt: initial install unconfirmed (executor cold)")
                return PromptInstallResult(PromptState.UNCONFIRMED)
            budget = prompt_token_budget(model)
            tok = getattr(model, "tokenizer", None)
            enc = getattr(tok, "encode", None)
            dec = getattr(tok, "decode", None)
            if budget is None or not callable(enc) or not callable(dec):
                self._prompt = None
                logger.warning(
                    "context-prompt: initial install unconfirmed (no usable tokenizer/budget)"
                )
                return PromptInstallResult(PromptState.UNCONFIRMED)
            try:
                if not (text or "").strip():  # None/""/whitespace: a CLEAR request (warm only)
                    self._prompt = None
                    logger.debug("context-prompt: initial install clear")
                    return PromptInstallResult(PromptState.CLEAR)
                fitted = fit_initial_prompt(text, encode=enc, decode=dec, budget=budget)
                if not fitted:
                    self._prompt = None
                    logger.warning("context-prompt: initial install unconfirmed (empty fit)")
                    return PromptInstallResult(PromptState.UNCONFIRMED)
                n = len(enc(fitted))
                if n == 0 or n > budget:  # the bound must be PROVEN on the fitted text
                    self._prompt = None
                    logger.warning(
                        "context-prompt: initial install unconfirmed (bound not proven)"
                    )
                    return PromptInstallResult(PromptState.UNCONFIRMED)
                self._prompt = fitted
                logger.info(
                    "context-prompt: initial install applied (%d tokens, budget %d)", n, budget
                )
                return PromptInstallResult(PromptState.APPLIED, n)
            except Exception as exc:  # noqa: BLE001 — fail-closed; never raise with seed content
                self._prompt = None
                logger.warning(
                    "context-prompt: initial install unconfirmed (%s)", type(exc).__name__
                )
                return PromptInstallResult(PromptState.UNCONFIRMED)

    @property
    def prompt(self) -> str | None:
        """The current (trimmed) prompt, or None when cleared."""
        return self._prompt

    # --- capability probe ----------------------------------------------------------------

    def warmup(self) -> None:
        """CAPABILITY PROBE: build the model + transcribe 1 s of 16 kHz float32 zeros.

        RAISES on any failure (model build, CUDA init, decode) — recorder_host's
        augment_kwargs_with_executor folds that into a degrade. Exercising a REAL transcribe
        (not just the constructor) is the point: it surfaces CUDA/encoder failures at READY
        time instead of on the first arm.
        """
        import numpy as np  # lazy: keeps the module import CUDA-free

        audio = np.zeros(int(_WARMUP_SECONDS * _WARMUP_SAMPLE_RATE), dtype="float32")
        self._transcribe_locked(audio, language=None, use_prompt=True)

    # --- RealtimeSTT executor entry point -------------------------------------------------

    def transcribe(
        self,
        audio: Any,
        language: str | None = None,
        use_prompt: bool = True,
        **_kwargs: Any,
    ) -> TranscriptionResult:
        """Transcribe `audio` conditioned on the current prompt. NEVER raises.

        Signature mirrors RealtimeSTT's call_transcription_executor call shape
        (audio positional; language/use_prompt keyword; **_kwargs accepted defensively so a
        future RealtimeSTT that adds args cannot crash us). use_prompt=False (or a cleared
        prompt) sends initial_prompt=None — the context-free decode.

        On ANY failure: log WARNING + return an EMPTY result (degrade-not-fail); RealtimeSTT's
        partial/final paths just see no text for that pass.
        """
        try:
            return self._transcribe_locked(audio, language, use_prompt)
        except Exception:  # noqa: BLE001 — deliberate: executor errors must never crash the child
            logger.warning(
                "context-prompt: transcribe failed; returning empty result",
                exc_info=True,
            )
            return TranscriptionResult(text="")

    # --- internals -------------------------------------------------------------------------

    def _build_model(self) -> Any:
        """Lazily construct the faster_whisper.WhisperModel (lazy import: child-only CUDA)."""
        import faster_whisper  # lazy: module import must stay CUDA-free (IMPORT PURITY)

        logger.debug(
            "context-prompt: building WhisperModel (model=%s device=%s compute_type=%s)",
            self._model_name,
            self._device,
            self._compute_type,
        )
        return faster_whisper.WhisperModel(
            model_size_or_path=self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

    def _transcribe_locked(
        self, audio: Any, language: str | None, use_prompt: bool
    ) -> TranscriptionResult:
        """One model call under self._lock. RAISES on failure — transcribe() swallows, warmup() propagates.

        The call shape mirrors RealtimeSTT's faster_whisper_engine (language, initial_prompt,
        beam_size, vad_filter) with ONE deliberate difference: condition_on_previous_text=False
        — WE own the cross-utterance context via initial_prompt; whisper's own previous-window
        conditioning would double-condition and drift.
        """
        with self._lock:
            if self._model is None:
                self._model = self._build_model()
            segments, info = self._model.transcribe(
                audio,
                language=language or None,
                initial_prompt=self._prompt if use_prompt else None,
                beam_size=self._beam_size,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            # Text assembly mirrors faster_whisper_engine.py: join segment texts, strip.
            text = " ".join(segment.text for segment in segments).strip()
            return TranscriptionResult(text=text, info=info)


def probe_prompt_executor(executor: PromptedExecutor) -> PromptProbeResult:
    """Run the executor's warmup and fold ANY exception into a PromptProbeResult.

    This is the startup capability probe recorder_host consumes: ok=True -> arm the executor
    into the recorder kwargs; ok=False -> stock kwargs + ONE INFO degrade line. Never raises.
    """
    try:
        executor.warmup()
    except Exception as exc:  # noqa: BLE001 — the probe's whole point is catching anything
        return PromptProbeResult(ok=False, error=repr(exc))
    return PromptProbeResult(ok=True)

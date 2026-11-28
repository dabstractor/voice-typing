"""voice-typing configuration: dataclasses + stdlib tomllib loader (PRD §4.5).

Loads user config from TOML into nested dataclasses. The schema and every default
below mirror config.toml (P1.M2.T1.S2) and PRD §4.5 EXACTLY — they are the single
source of truth for runtime tuning.

SEARCH ORDER (PRD §4.5), implemented by VoiceTypingConfig.load(path=None):
  1. $XDG_CONFIG_HOME/voice-typing/config.toml   (XDG_CONFIG_HOME unset/empty → ~/.config/...)
  2. <repo>/config.toml                          (module-relative; parent dir of voice_typing/)
  3. built-in dataclass defaults                 (no candidate found → VoiceTypingConfig())
The FIRST existing file wins. An explicit `path=` disables the search and loads
that one file (used by tests and a future --config flag).

THIS MODULE IS PURE DATA + A LOADER (stdlib only: os, pathlib, dataclasses,
tomllib). It must NOT import cuda_check / ctranslate2 / torch / realtimestt —
config must load in CPU-only and test contexts. The `device="cuda"` default is the
user's DESIRED setting; whether CUDA is actually available is decided at daemon
startup by voice_typing.cuda_check.resolve_device_and_models() (P1.M1.T2.S2),
which the daemon (P1.M4.T1.S1) APPLIES as an override on the loaded config
(e.g. `cfg.asr.device = "cpu"`). `compute_type` is NOT a config field (it is a
cuda_check concern per §4.4); do not add it here.

state_file LAZY RESOLUTION: FeedbackConfig.state_file defaults to "" (empty).
Its effective path ($XDG_RUNTIME_DIR/voice-typing/state.json when empty) is
resolved lazily by FeedbackConfig.resolved_state_file() — NOT at load time —
because XDG_RUNTIME_DIR is unset outside real login sessions (cron, tests,
non-interactive shells). feedback.py (P1.M3.T2.S1) calls resolved_state_file()
at write time; if state_file is empty AND XDG_RUNTIME_DIR is unset it raises
RuntimeError (no safe default — fail clearly rather than write to a wrong path).

CONSUMERS: textproc.clean(cfg.filter) (P1.M2.T2.S1), typing_backends (cfg.output)
(P1.M3.T1.S1), feedback (cfg.feedback) (P1.M3.T2.S1), daemon (whole cfg + the
cuda_check override) (P1.M4.T1.S1).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Sub-config dataclasses (PRD §4.5 — defaults mirror config.toml EXACTLY)
# ---------------------------------------------------------------------------

@dataclass
class AsrConfig:
    """[asr] — ASR model + device settings. `device` may be overridden by cuda_check."""

    lite_model: str = "small.en"            # Rev 2 single-mode: THE model — loads once and is
                                          # used for both partials + finals (the old two-model
                                          # pair is gone; PRD §4.2quater collapse)
    language: str = "en"
    device: str = "cuda"  # "cuda" | "cpu" (daemon may override via cuda_check at startup)
    compute_type: str = "float16"  # ctranslate2 compute type on the CUDA path. "float16" =
                                   # Ampere+ native (~2x faster decode than float32 — the
                                   # measured difference between usable and laggy live partials
                                   # on large models). "float32" = legacy cards without usable
                                   # fp16 (e.g. Maxwell 940MX). IGNORED when device="cpu" or on
                                   # the no-CUDA fallback (always int8 there).
    post_speech_silence_duration: float = 0.6  # VAD: finalize after this much silence (seconds)
    lite_post_speech_silence_duration: float = 0.8  # PRD §4.2quater: the endpointer only delays
                                               # COMMIT under streaming (words are already typed
                                               # live) — 0.8 halves mid-thought cuts for +0.3 s
                                               # commit latency. 0.5 = razor-snappy;
                                               # 1.0 = near-zero cuts.
    context_prompt: bool = True                # PRD §4.2quater: condition every decode on the
                                             # rolling committed context (back to the last
                                             # sentence boundary, ~200-token cap)
    realtime_processing_pause: float = 0.15    # partials cadence (seconds)
    auto_stop_idle_seconds: float = 30.0       # auto-disarm after this many seconds of no recognized
                                               # speech (partials reset the clock); 0 disables
    auto_unload_idle_seconds: float = 1800.0   # PRD §4.2bis: after this many seconds DISARMED with
                                               # models loaded, tear down the recorder to free VRAM
                                               # (~0); the clock starts on disarm and resets on arm.
                                               # 0 disables (models stay resident until quit)
    graceful_stop: bool = False       # stop = IMMEDIATE disarm (mic off now; the racing final
                                       # is dropped, the tail stays typed as-is). The old drain
                                       # (wait up to ~5 s for the in-flight final) is opt-in
                                       # (2026-10: "all the way, no exceptions")

    def __post_init__(self) -> None:
        """Validate field types at construction (bugfix Issue 4 / PRD §4.5 robustness).

        dataclasses do NOT enforce annotations at runtime, so a wrong-typed TOML value (e.g.
        auto_stop_idle_seconds = "thirty") loaded via from_toml(**section) would pass silently and
        break the feature at runtime — _maybe_auto_stop's `time.monotonic() - ts < threshold` raises
        TypeError, which the _idle_watchdog swallows, so auto-stop silently dies. This raises
        TypeError at LOAD time (construction = when from_toml calls AsrConfig(**section); before
        models load, before systemd loops), mirroring the existing unknown-key rejection (also
        TypeError). bool is rejected even for numeric fields: bool is an int subclass in Python but
        is not a valid config value here.
        """
        # Numeric fields: accept int or float, reject bool (int subclass) + everything else.
        for _name in (
            "post_speech_silence_duration",
            "lite_post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
            "auto_unload_idle_seconds",
        ):
            _v = getattr(self, _name)
            if isinstance(_v, bool) or not isinstance(_v, (int, float)):
                raise TypeError(
                    f"[asr] {_name} expects a number (int or float), "
                    f"got {type(_v).__name__}: {_v!r}"
                )
        # String fields: must be str.
        for _name in ("lite_model", "language", "device", "compute_type"):
            _v = getattr(self, _name)
            if not isinstance(_v, str):
                raise TypeError(
                    f"[asr] {_name} expects str, got {type(_v).__name__}: {_v!r}"
                )
        # Bool fields: must be genuine bools. Same int/bool asymmetry as the numeric guard
        # above, mirrored: the numerics REJECT bool (bool is an int subclass); the bools REJECT
        # int (a bare `context_prompt = 1` in config.toml is a typo, not a flag). Raises
        # TypeError at LOAD time instead of silently flipping the feature off.
        if not isinstance(self.context_prompt, bool):
            raise TypeError(
                f"[asr] context_prompt expects bool, got "
                f"{type(self.context_prompt).__name__}: {self.context_prompt!r}"
            )
        # device VALUE validation (VT-005): only "cuda" | "cpu" are valid. A typo such as
        # device="cud" or device="gpu" is a valid str so it passed the type guard above, but it
        # would then flow into _resolve_device_config -> AudioToTextRecorder(device=…) and fail
        # noisily at construction (force-CPU retry) FAR from the config mistake. Reject it here at
        # load time with a clear ValueError, mirroring the fast-fail posture for bad types.
        # (cuda_check already auto-falls-back from "cuda" when no GPU is visible, so no "auto"
        # sentinel is needed.) ValueError (not TypeError): the TYPE is correct, the VALUE is not.
        if self.device not in ("cuda", "cpu"):
            raise ValueError(
                f'[asr] device must be "cuda" or "cpu", got {self.device!r}'
            )


@dataclass
class OutputConfig:
    """[output] — typing-output backend selection."""

    backend: str = "wtype"     # "wtype" | "ydotool" | "null" (types nothing)
    append_space: bool = True  # daemon appends one trailing space to each final
    streaming: bool = True     # PRD §4.2quater: type stabilized partials live + revise in place;
                               # false = append-only finals (rollback hatch)
    stream_chunks: str = "char"  # live-stream flush granularity (ONLY when streaming=true):
                               # "word" = hold each partial's delta until the next non-word
                               # char, then type the whole word-chunk at once (\W-to-\W — text
                               # lands word-by-word, never letter-by-letter); "char" = legacy
                               # behavior (every delta types as soon as it arrives).
    delivery: str = "stream-edit"  # Rev 4 §4.2sexies: "bulk-text" = paste-as-policy output path
                               # (one-edit corrections, NO typing/backspace fallback; opt-in
                               # until G6 graduation — verdict in tests/G6_GRADUATION.md:
                               # STAY OPT-IN, 2026-11-23 @ 69952ae); "stream-edit" = today's
                               # behavior.
                               # bulk-text additionally requires (enforced at the TOP level,
                               # because the other two members live in other sections):
                               # output.streaming=true, asr.graceful_stop=false,
                               # cancel.keypress_action="disarm" — see VoiceTypingConfig.

    def __post_init__(self) -> None:
        # backend VALUE validation (bugfix Issue 3 / VT-005 precedent): only "wtype" | "ydotool" |
        # "null" are valid. A typo such as backend="wtyp" is a valid str, but it would otherwise flow
        # into typing_backends.make_backend() -> VoiceTypingDaemon.__init__() and raise there — under
        # systemd that is a Restart=on-failure crash-loop discoverable only via journalctl. Reject it
        # here at load time with a clear ValueError (the TYPE is correct, the VALUE is not — mirrors
        # AsrConfig's device validation). make_backend() retains its own ValueError as a defensive
        # second gate.
        if self.backend not in ("wtype", "ydotool", "tmux", "null"):
            raise ValueError(
                f'[output] backend must be "wtype", "ydotool", "tmux", or "null", got {self.backend!r}'
            )
        # streaming must be a genuine bool (rejects int — `streaming = 1` is a typo, not a
        # flag; mirrors the AsrConfig.context_prompt guard).
        if not isinstance(self.streaming, bool):
            raise TypeError(
                f"[output] streaming expects bool, got "
                f"{type(self.streaming).__name__}: {self.streaming!r}"
            )
        # stream_chunks VALUE validation (same typo class as backend/delivery):
        # only "char" | "word" are valid.
        if not isinstance(self.stream_chunks, str):
            raise TypeError(
                f"[output] stream_chunks expects str, got "
                f"{type(self.stream_chunks).__name__}: {self.stream_chunks!r}"
            )
        if self.stream_chunks not in ("char", "word"):
            raise ValueError(
                f'[output] stream_chunks must be "char" or "word", got {self.stream_chunks!r}'
            )
        # delivery VALUE validation (backend / VT-005 precedent): only "stream-edit" | "bulk-text"
        # are valid. A typo such as delivery="Bulk-Text" is a valid str, but it would otherwise be
        # silently treated as the default by the future daemon wiring (P1.M6.T2.S1) — reject it at
        # load time with a clear ValueError (the TYPE is correct, the VALUE is not).
        if not isinstance(self.delivery, str):
            raise TypeError(
                f"[output] delivery expects str, got "
                f"{type(self.delivery).__name__}: {self.delivery!r}"
            )
        if self.delivery not in ("stream-edit", "bulk-text"):
            raise ValueError(
                f'[output] delivery must be "stream-edit" or "bulk-text", got {self.delivery!r}'
            )


@dataclass
class CancelConfig:
    """[cancel] — Rev 2 Backspace-cancel of the last committed utterance (PRD §4.2quater).

    While dictation is armed, Alt+Super+Backspace erases the last committed utterance
    (types Backspaces to undo it) instead of typing a literal Backspace. `on_backspace`
    enables the gesture; `devices` optionally pins the keyboard device node(s) to watch
    (e.g. ["/dev/input/event3"]) — an empty list means auto-detect (P1.M2.T7.S2 owns the
    enumeration).
    """

    on_backspace: bool = True  # Alt+Super+Backspace erases the last committed utterance
    keypress_action: str = "disarm"  # user keypress while armed (2026-10 user decision):
                                     # "disarm" = halt dictation ENTIRELY (mic off, no late
                                     # keystrokes, re-arm with the hotkey) | "freeze" = legacy
                                     # per-utterance freeze (typing resumes at the boundary)
    # default_factory: each CancelConfig gets its OWN list (mutable-default guard,
    # mirroring FilterConfig.blocklist). Empty list = auto-detect the keyboard device(s).
    devices: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate field types at construction (PRD §4.5 robustness; mirrors the other sections).

        on_backspace must be a genuine bool (int rejected — the same asymmetry as everywhere
        else: numeric fields reject bool, bool fields reject int). devices must be a list of
        str (FilterConfig.blocklist guard style): a wrong-typed value would otherwise only
        crash at RUNTIME when the cancel listener opens/grabs the device — under systemd,
        far from the config mistake. TypeError at LOAD time keeps the fail-fast posture.
        """
        if not isinstance(self.on_backspace, bool):
            raise TypeError(
                f"[cancel] on_backspace expects bool, got "
                f"{type(self.on_backspace).__name__}: {self.on_backspace!r}"
            )
        if self.keypress_action not in ("disarm", "freeze"):
            raise TypeError(
                f"[cancel] keypress_action expects 'disarm' or 'freeze', got "
                f"{self.keypress_action!r}"
            )
        if not isinstance(self.devices, list) or not all(
            isinstance(_d, str) for _d in self.devices
        ):
            raise TypeError(
                f"[cancel] devices expects a list of str, got "
                f"{type(self.devices).__name__}: {self.devices!r}"
            )


@dataclass
class AudioConfig:
    """[audio] — media ducking while listening (PRD §4.2quinquies).

    Defaults to duck_mode="mpris" (P1.M2.T4 — the ducker landed; this IS that round): MPRIS
    players pause at arm, and at disarm we resume ONLY what WE paused (still paused) — user
    sovereignty. "off" is byte-identical to pre-D1 behavior (no audio subprocess is ever
    spawned).
    """

    duck_mode: str = "mpris"      # "mpris" (pause players at arm) | "volume" (duck sink) | "off"
    duck_volume_pct: int = 15     # target sink volume % for the "volume" tier (wpctl)

    def __post_init__(self) -> None:
        """Validate at construction = load time (mirrors CancelConfig's guards)."""
        if self.duck_mode not in ("off", "mpris", "volume"):
            raise TypeError(
                f"[audio] duck_mode expects 'off', 'mpris', or 'volume', got "
                f"{self.duck_mode!r}"
            )
        if isinstance(self.duck_volume_pct, bool) or not isinstance(self.duck_volume_pct, int):
            raise TypeError(
                f"[audio] duck_volume_pct expects int, got "
                f"{type(self.duck_volume_pct).__name__}: {self.duck_volume_pct!r}"
            )


@dataclass
class FeedbackConfig:
    """[feedback] — state file + Hyprland notification settings."""

    state_file: str = ""       # "" → resolved lazily to $XDG_RUNTIME_DIR/voice-typing/state.json
    hypr_notify: bool = True   # hyprctl notify one-liner for start/final/stop
    notify_ms: int = 2500      # hyprctl notify duration (ms)
    notify_on_final: bool = True  # also pop a hyprctl popup per final ("✔ <text>")? The text is
                                  # already typed into the focused window, so this popup is
                                  # status line, so this is redundant for most setups — set False to
                                  # keep only the brief Recording / Recording Stopped toasts.
                                  # hypr_notify=False still wins (suppresses ALL popups).

    def __post_init__(self) -> None:
        """Validate notify_ms is an int (bugfix Issue 4 / PRD §4.5 robustness).

        notify_ms is the only runtime-numeric FeedbackConfig field. tomllib parses a bare `2500` as
        int (correct); `2500.0` parses as float and `true`/`"2500"` as bool/str. Reject all but a
        genuine int (and reject bool, an int subclass) at load time, mirroring AsrConfig.__post_init__
        and the unknown-key TypeError. Only notify_ms is validated here — the other fields are out of
        scope (a wrong-typed state_file fails at file-open with a clear error; a wrong-typed bool is
        merely truthy).
        """
        _v = self.notify_ms
        if isinstance(_v, bool) or not isinstance(_v, int):
            raise TypeError(
                f"[feedback] notify_ms expects int, got {type(_v).__name__}: {_v!r}"
            )

    def resolved_state_file(self) -> str:
        """Return the effective state-file path (lazy XDG_RUNTIME_DIR resolution).

        Non-empty state_file → returned verbatim. Empty →
        $XDG_RUNTIME_DIR/voice-typing/state.json. Raises RuntimeError if empty
        AND XDG_RUNTIME_DIR is unset/empty (no safe default — fail clearly).
        """
        if self.state_file:
            return self.state_file
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        if not xdg_runtime:
            raise RuntimeError(
                "feedback.state_file is empty and XDG_RUNTIME_DIR is not set; "
                "cannot determine the state-file path. Set state_file in config "
                "or run under a session that exports XDG_RUNTIME_DIR (systemd "
                "user sessions set it)."
            )
        return os.path.join(xdg_runtime, "voice-typing", "state.json")


@dataclass
class FilterConfig:
    """[filter] — post-recognition text filter. Consumed by textproc.clean()."""

    min_chars: int = 2
    # default_factory: each FilterConfig gets its OWN list (mutable-default guard).
    # Stored VERBATIM; textproc lowercases + strips trailing punctuation at compare
    # time (PRD §4.7). Defaults are already lowercase per §4.5.
    blocklist: list[str] = field(
        default_factory=lambda: [
            "thank you.",
            "thanks for watching.",
            "bye.",
            "thank you for watching",
        ]
        # NOTE (VT-006): the bare "you" entry was REMOVED from the defaults. "you" is a common
        # English word a user frequently wants to type as a standalone utterance, and the
        # blocklist matches on the punctuation/case-normalized form (textproc.clean), so it
        # silently dropped dictating the single word "you" with no feedback. The blocklist's
        # purpose is suppressing Whisper silence hallucinations (the other entries are genuine
        # hallucinations); a single-word "you" is not. If a lone "you" hallucination is observed,
        # filter it with a hallucination-pattern heuristic (e.g. drop a lone word only when VAD
        # saw no real speech) rather than blanket-suppressing the word for all dictation.
    )

    def __post_init__(self) -> None:
        """Validate field types at construction (validation Issue 4 / PRD §4.5 robustness).

        FilterConfig was the lone sub-config with no load-time validation. A wrong-typed value
        loaded via from_toml(**section) would pass silently and crash at RUNTIME inside
        textproc.clean (called from on_final on every utterance): e.g. min_chars = "two" raises
        TypeError on `len(cleaned) < cfg.min_chars`; blocklist = [123] raises AttributeError on
        `b.lower()`. Both would silently drop EVERY final (on_final swallows textproc exceptions
        are not the issue — clean() itself raises before typing). This raises TypeError at LOAD
        time, mirroring AsrConfig/OutputConfig/FeedbackConfig + the unknown-key rejection.
        bool is rejected for min_chars even though bool is an int subclass (a `min_chars = true`
        config typo is not a meaningful threshold).
        """
        # min_chars: a non-bool int (a float threshold like 2.0 would technically compare but is
        # not a meaningful char count and config.toml documents it as an int — accept int only).
        _v = self.min_chars
        if isinstance(_v, bool) or not isinstance(_v, int):
            raise TypeError(
                f"[filter] min_chars expects int, got {type(_v).__name__}: {_v!r}"
            )
        # blocklist: each element must be a str (textproc calls .lower() on every entry).
        for _i, _entry in enumerate(self.blocklist):
            if not isinstance(_entry, str):
                raise TypeError(
                    f"[filter] blocklist[{_i}] expects str, "
                    f"got {type(_entry).__name__}: {_entry!r}"
                )


@dataclass
class LogConfig:
    """[log] — daemon logging verbosity (PRD §4.2 'logging … at INFO; DEBUG via config').

    `level` sets the `voice_typing` namespace logger level (applied in VoiceTypingDaemon.run). The
    entry point (P1.M4.T3.S1) also reads this for basicConfig's handler/root level. "INFO" ships the
    per-utterance latency line; "DEBUG" adds the raw monotonic-timestamp line.
    """

    level: str = "INFO"  # "INFO" | "DEBUG" (case-insensitive at apply time)


# BUG-006: the ONLY top-level TOML tables from_toml understands. Anything else in the
# mapping is a typo'd SECTION header (e.g. [outpt]) — worse than a typo'd key, it would
# silently disable the whole feature. Rejected loudly in from_toml (TypeError), matching
# the unknown-KEY rejection the dataclass __init__ already performs. ALL-CAPS literal
# (cf. textproc._TRAILING_PUNCT): one definition, never re-typed at the check site.
_KNOWN_TABLES = frozenset({"asr", "output", "cancel", "audio", "feedback", "filter", "log"})


@dataclass
class VoiceTypingConfig:
    """Top-level config aggregating all PRD §4.5 sub-sections."""

    asr: AsrConfig = field(default_factory=AsrConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    cancel: CancelConfig = field(default_factory=CancelConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    log: LogConfig = field(default_factory=LogConfig)

    def __post_init__(self) -> None:
        """Cross-section gate (P1.M3.T3.S1): bulk-text's precondition triple.

        bulk-text (§4.2sexies R.3/R.5) forbids typing fallbacks, drains, and the freeze
        keypress action — a config combining bulk-text with any of those would produce
        incoherent runtime behavior far from the config mistake (the exact failure mode
        VT-005/Issue 3 established as worth rejecting at load). The triple spans THREE
        sections (output.streaming, asr.graceful_stop, cancel.keypress_action), so it
        cannot live in OutputConfig.__post_init__ — this is the config's FIRST cross-section
        validation, hence a top-level __post_init__. It runs for BOTH construction paths
        (defaults + from_toml overlay) since __post_init__ fires after all field
        construction; the default delivery="stream-edit" short-circuits, so every existing
        config loads identically (zero behavior change at default).

        ALL violated preconditions are collected into ONE ValueError (not first-fail) so
        the operator sees the full extent of the incoherence in a single edit round.
        """
        if self.output.delivery != "bulk-text":
            return
        violated = []  # (dot-qualified key, required value, got value) clauses
        if self.output.streaming is not True:
            violated.append(("output.streaming", "true", self.output.streaming))
        if self.asr.graceful_stop is not False:
            violated.append(("asr.graceful_stop", "false", self.asr.graceful_stop))
        if self.cancel.keypress_action != "disarm":
            violated.append(
                ("cancel.keypress_action", '"disarm"', self.cancel.keypress_action)
            )
        if violated:
            clauses = ", ".join(f"{key}={want} (got {got!r})" for key, want, got in violated)
            raise ValueError(
                'output.delivery="bulk-text" requires ' + clauses
            )

    # --- construction from parsed TOML / files ---

    @classmethod
    def from_toml(cls, data: Mapping[str, Any]) -> VoiceTypingConfig:
        """Build a config from an already-parsed TOML mapping.

        Each table ([asr]/[output]/[cancel]/[audio]/[feedback]/[filter]/[log]) overlays its
        dataclass defaults — only present keys override; missing tables/keys keep
        defaults. Unknown keys raise TypeError (dataclass __init__ rejects them) so a
        typo'd config key surfaces loudly instead of being silently ignored. Unknown
        top-level TABLES raise TypeError the same way (BUG-006): a typo'd section
        header like [outpt] would otherwise silently disable an entire feature.
        Malformed TOML is caught upstream by tomllib (TOMLDecodeError); a scalar where
        a table is expected raises TypeError via the Mapping check here.
        """
        # BUG-006 fail-fast gate BEFORE any overlay runs: reject typo'd section names.
        # Difference (not a whitelist match) so {} and known subsets stay valid; table
        # CONTENT validation stays with each section's own __init__/__post_init__.
        unknown = set(data) - _KNOWN_TABLES
        if unknown:
            raise TypeError(
                f"unknown config table(s): {', '.join(f'[{t}]' for t in sorted(unknown))}; "
                f"known tables: {', '.join(sorted(_KNOWN_TABLES))}"
            )

        def _overlay(section_cls, table_name):
            section = data.get(table_name, {})
            if not isinstance(section, Mapping):
                raise TypeError(
                    f"[{table_name}] must be a TOML table, got {type(section).__name__}"
                )
            return section_cls(**section)

        return cls(
            asr=_overlay(AsrConfig, "asr"),
            output=_overlay(OutputConfig, "output"),
            cancel=_overlay(CancelConfig, "cancel"),
            audio=_overlay(AudioConfig, "audio"),
            feedback=_overlay(FeedbackConfig, "feedback"),
            filter=_overlay(FilterConfig, "filter"),
            log=_overlay(LogConfig, "log"),
        )

    @classmethod
    def from_toml_file(cls, path: str | os.PathLike[str]) -> VoiceTypingConfig:
        """Read + parse a TOML file → config. tomllib requires BINARY mode."""
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls.from_toml(data)

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> VoiceTypingConfig:
        """Load from `path`, or via the PRD §4.5 search order when path is None.

        Search order (first EXISTING file wins):
          1. $XDG_CONFIG_HOME/voice-typing/config.toml (unset/empty → ~/.config/...)
          2. <repo>/config.toml (module-relative: parent dir of voice_typing/)
          3. built-in dataclass defaults (no candidate exists)
        An explicit path= bypasses the search and loads that one file.
        """
        if path is not None:
            return cls.from_toml_file(path)
        for candidate in _candidate_paths():
            if os.path.isfile(candidate):
                return cls.from_toml_file(candidate)
        return cls()  # built-in defaults


# ---------------------------------------------------------------------------
# Search-order helpers (module-level so tests can monkeypatch them for hermeticity)
# ---------------------------------------------------------------------------

def _xdg_config_path() -> str:
    """$XDG_CONFIG_HOME/voice-typing/config.toml (XDG unset/empty → ~/.config/...)."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not xdg_config:
        xdg_config = os.path.expanduser("~/.config")
    return os.path.join(xdg_config, "voice-typing", "config.toml")


def _repo_config_path() -> str:
    """<repo>/config.toml — module-relative so it resolves regardless of CWD.

    voice_typing/config.py → parent = voice_typing/ → parent = repo root.
    config.toml is NOT packaged in the wheel (packages=["voice_typing"]); for
    installed runs this candidate won't exist — install.sh copies it to XDG.
    """
    return str(Path(__file__).resolve().parent.parent / "config.toml")


def _candidate_paths() -> list[str]:
    """Ordered search candidates: XDG first, then repo. Defaults are the fallback."""
    return [_xdg_config_path(), _repo_config_path()]


def load(path: str | os.PathLike[str] | None = None) -> VoiceTypingConfig:
    """Module-level convenience wrapper around VoiceTypingConfig.load()."""
    return VoiceTypingConfig.load(path)

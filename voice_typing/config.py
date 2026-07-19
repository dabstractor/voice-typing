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

    final_model: str = "distil-large-v3"
    realtime_model: str = "small.en"
    lite_model: str = "small.en"            # PRD §4.2ter: the SINGLE model loaded in lite mode
                                          # (used for both partials + finals; large model never loads)
    language: str = "en"
    device: str = "cuda"  # "cuda" | "cpu" (daemon may override via cuda_check at startup)
    post_speech_silence_duration: float = 0.6  # VAD: finalize after this much silence (seconds)
    lite_post_speech_silence_duration: float = 0.5  # PRD §4.2ter: lite-mode silence threshold —
                                               # the silence gate, not the model, is the
                                               # perceived-latency bottleneck (see §4.2ter).
                                               # 0.3 = razor-snappy (may split a brief pause);
                                               # 0.6 = safe.
    realtime_processing_pause: float = 0.15    # partials cadence (seconds)
    auto_stop_idle_seconds: float = 30.0       # auto-disarm after this many seconds of no recognized
                                               # speech (partials reset the clock); 0 disables
    auto_unload_idle_seconds: float = 1800.0   # PRD §4.2bis: after this many seconds DISARMED with
                                               # models loaded, tear down the recorder to free VRAM
                                               # (~0); the clock starts on disarm and resets on arm.
                                               # 0 disables (models stay resident until quit)

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
        for _name in ("final_model", "realtime_model", "lite_model", "language", "device"):
            _v = getattr(self, _name)
            if not isinstance(_v, str):
                raise TypeError(
                    f"[asr] {_name} expects str, got {type(_v).__name__}: {_v!r}"
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

    backend: str = "wtype"     # "wtype" | "ydotool" | "tmux"
    tmux_target: str = ""      # used only when backend == "tmux", e.g. "voicetest:0.0"
    append_space: bool = True  # daemon appends one trailing space to each final

    def __post_init__(self) -> None:
        # backend VALUE validation (bugfix Issue 3 / VT-005 precedent): only "wtype" | "ydotool" |
        # "tmux" are valid. A typo such as backend="wtyp" is a valid str, but it would otherwise flow
        # into typing_backends.make_backend() -> VoiceTypingDaemon.__init__() and raise there — under
        # systemd that is a Restart=on-failure crash-loop discoverable only via journalctl. Reject it
        # here at load time with a clear ValueError (the TYPE is correct, the VALUE is not — mirrors
        # AsrConfig's device validation). make_backend() retains its own ValueError as a defensive
        # second gate.
        if self.backend not in ("wtype", "ydotool", "tmux"):
            raise ValueError(
                f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}'
            )


@dataclass
class FeedbackConfig:
    """[feedback] — state file + Hyprland notification settings."""

    state_file: str = ""       # "" → resolved lazily to $XDG_RUNTIME_DIR/voice-typing/state.json
    hypr_notify: bool = True   # hyprctl notify one-liner for start/final/stop
    notify_ms: int = 2500      # hyprctl notify duration (ms)
    notify_on_final: bool = True  # also pop a hyprctl popup per final ("✔ <text>")? The text is
                                  # already typed into the focused window + shown live in the tmux
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


@dataclass
class VoiceTypingConfig:
    """Top-level config aggregating all PRD §4.5 sub-sections."""

    asr: AsrConfig = field(default_factory=AsrConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    log: LogConfig = field(default_factory=LogConfig)

    # --- construction from parsed TOML / files ---

    @classmethod
    def from_toml(cls, data: Mapping[str, Any]) -> VoiceTypingConfig:
        """Build a config from an already-parsed TOML mapping.

        Each table ([asr]/[output]/[feedback]/[filter]) overlays its dataclass
        defaults — only present keys override; missing tables/keys keep defaults.
        Unknown keys raise TypeError (dataclass __init__ rejects them) so a typo'd
        config key surfaces loudly instead of being silently ignored. Malformed
        TOML is caught upstream by tomllib (TOMLDecodeError); a scalar where a
        table is expected raises TypeError via the Mapping check here.
        """

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

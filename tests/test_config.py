"""Unit tests for voice_typing.config (PRD §4.5 — config schema + search order).

Pure-Python: no network, no GPU, no audio. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_config.py -v

These are the project's FIRST unit tests; they establish the pytest pattern every
downstream test task (test_textproc, typing-backend tests, P1.M7 suite) reuses.
"""
from __future__ import annotations

import os

import pytest

import voice_typing.config as cfgmod
from voice_typing.config import (
    AsrConfig,
    CancelConfig,
    FeedbackConfig,
    FilterConfig,
    VoiceTypingConfig,
)

# PRD §4.5 authoritative blocklist (pinned verbatim, incl. trailing periods).
# VT-006: the bare "you" entry was removed from the defaults — it is a common word users want to
# type as a standalone utterance, not a Whisper silence hallucination.
_PRD_BLOCKLIST = [
    "thank you.",
    "thanks for watching.",
    "bye.",
    "thank you for watching",
]


# ---------------------------------------------------------------------------
# Defaults (PRD §4.5) — the single source of truth these tests pin
# ---------------------------------------------------------------------------

def test_defaults_match_prd_4_5():
    """A bare VoiceTypingConfig() must equal PRD §4.5 defaults exactly."""
    cfg = VoiceTypingConfig()
    # [asr]
    assert cfg.asr.lite_model == "small.en"   # the SINGLE model (Rev 2 single-mode collapse)
    assert cfg.asr.language == "en"
    assert cfg.asr.device == "cuda"
    assert cfg.asr.post_speech_silence_duration == 0.6
    assert cfg.asr.lite_post_speech_silence_duration == 0.8  # PRD §4.2quater: endpointer only delays COMMIT under streaming
    assert cfg.asr.context_prompt is True  # PRD §4.2quater: rolling committed-context conditioning
    assert cfg.asr.realtime_processing_pause == 0.15
    assert cfg.asr.auto_stop_idle_seconds == 30.0
    assert cfg.asr.auto_unload_idle_seconds == 1800.0  # P1.M3.T1.S1: idle-unload knob (PRD §4.2bis)
    # [output]
    assert cfg.output.backend == "wtype"
    assert cfg.output.append_space is True
    assert cfg.output.streaming is True  # PRD §4.2quater: live partial typing + revise in place
    # [cancel]
    assert cfg.cancel.on_backspace is True  # PRD §4.2quater: Alt+Super+Backspace cancel gesture
    assert cfg.cancel.devices == []
    # [feedback]
    assert cfg.feedback.state_file == ""
    assert cfg.feedback.hypr_notify is True
    assert cfg.feedback.notify_ms == 2500
    assert cfg.feedback.notify_on_final is True
    # [filter]
    assert cfg.filter.min_chars == 2
    assert cfg.filter.blocklist == _PRD_BLOCKLIST


def test_defaults_match_cuda_check():
    """Drift guard: the asr single-model/device defaults must equal cuda_check.CUDA_DEFAULTS.

    config holds the DESIRED value; cuda_check holds the same value for its CUDA
    path. If these drift, the daemon's cuda_check override (P1.M4.T1.S1) would
    contradict the config default. Single-model contract (Rev 2 / P1.M1.T2.S1):
    cuda_check resolves exactly {device, compute_type, model}; config's
    lite_model is THE model and must equal CUDA_DEFAULTS["model"]; the CPU
    substitute is tiny.en.
    """
    from voice_typing.cuda_check import CPU_FALLBACK, CUDA_DEFAULTS

    assert set(CUDA_DEFAULTS) == {"device", "compute_type", "model"}
    assert AsrConfig().lite_model == CUDA_DEFAULTS["model"]
    assert AsrConfig().device == CUDA_DEFAULTS["device"]
    assert CPU_FALLBACK["model"] == "tiny.en"  # the approved CPU substitute


def test_field_types_are_tomllib_natural_types():
    """Defaults carry the Python types tomllib yields (float for 0.6, int, bool)."""
    cfg = VoiceTypingConfig()
    assert isinstance(cfg.asr.post_speech_silence_duration, float)  # 0.6, not int 0
    assert isinstance(cfg.asr.lite_post_speech_silence_duration, float)  # 0.8, not int 0 (PRD §4.2quater)
    assert isinstance(cfg.asr.realtime_processing_pause, float)
    assert isinstance(cfg.filter.min_chars, int)
    assert isinstance(cfg.feedback.notify_ms, int)
    assert isinstance(cfg.output.append_space, bool)
    assert isinstance(cfg.asr.context_prompt, bool)
    assert isinstance(cfg.output.streaming, bool)
    assert isinstance(cfg.cancel.on_backspace, bool)
    assert isinstance(cfg.filter.blocklist, list)
    assert isinstance(cfg.cancel.devices, list)


def test_blocklist_not_shared_between_instances():
    """default_factory must give each FilterConfig its OWN list (no shared state)."""
    a = FilterConfig()
    b = FilterConfig()
    a.blocklist.append("mutated")
    assert "mutated" not in b.blocklist
    assert b.blocklist == _PRD_BLOCKLIST


# ---------------------------------------------------------------------------
# from_toml / from_toml_file
# ---------------------------------------------------------------------------

def test_from_toml_partial_table_keeps_other_defaults():
    """A TOML with only one overridden key keeps every other default."""
    cfg = VoiceTypingConfig.from_toml(
        {"asr": {"language": "es"}, "cancel": {"on_backspace": False}}
    )
    assert cfg.asr.language == "es"                  # overridden
    assert cfg.asr.lite_model == "small.en"          # same-section default kept
    assert cfg.output.backend == "wtype"             # other section untouched
    assert cfg.filter.min_chars == 2                 # other section untouched
    assert cfg.cancel.on_backspace is False          # overridden
    assert cfg.cancel.devices == []                  # same-section default kept


def test_from_toml_empty_dict_is_all_defaults():
    """An empty TOML mapping yields pure defaults (no tables present)."""
    assert VoiceTypingConfig.from_toml({}) == VoiceTypingConfig()


def test_from_toml_unknown_key_raises():
    """A typo'd key must surface as a loud TypeError, not be silently ignored."""
    with pytest.raises(TypeError):
        VoiceTypingConfig.from_toml({"output": {"bakcend": "wtype"}})


def test_from_toml_section_not_a_table_raises():
    """A scalar where a TOML table is expected must raise (not silently default)."""
    with pytest.raises(TypeError):
        VoiceTypingConfig.from_toml({"asr": "not-a-table"})


# ---------------------------------------------------------------------------
# from_toml — wrong-TYPED values raise TypeError at load (bugfix Issue 4 / PRD §4.5)
#
# Unknown keys already raise TypeError (test_from_toml_unknown_key_raises). A wrong TYPE
# (e.g. auto_stop_idle_seconds = "thirty") used to load silently and break the feature at
# runtime (a TypeError the _idle_watchdog swallowed -> auto-stop silently died).
# AsrConfig/FeedbackConfig __post_init__ (P1.M3.T1.S1) now validates types at construction
# (= load time). These pin that fail-fast contract.
# ---------------------------------------------------------------------------


def test_string_for_float_field_raises():
    """A string where a float is expected raises TypeError naming the field + bad value."""
    with pytest.raises(TypeError) as excinfo:
        VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})
    assert "auto_stop_idle_seconds" in str(excinfo.value)
    assert "thirty" in str(excinfo.value)


def test_bool_for_float_field_raises():
    """A bool where a float is expected raises TypeError (the isinstance(True, int) gotcha)."""
    with pytest.raises(TypeError, match="post_speech_silence_duration"):
        VoiceTypingConfig.from_toml({"asr": {"post_speech_silence_duration": True}})


def test_int_for_string_field_raises():
    """An int where a str is expected raises TypeError naming the field."""
    with pytest.raises(TypeError, match="device"):
        VoiceTypingConfig.from_toml({"asr": {"device": 123}})


# ---------------------------------------------------------------------------
# Rev 2 streaming-dictation knobs (PRD §4.2quater): asr.context_prompt, output.streaming,
# [cancel] (on_backspace + devices). The bool fields must be GENUINE bools — int is
# rejected (the mirror of the numeric guards rejecting bool); devices must be a list of
# str (FilterConfig.blocklist guard style); unknown [cancel] keys raise TypeError via
# from_toml's dataclass __init__.
# ---------------------------------------------------------------------------

_REV2_BOOL_FIELDS = (
    ("asr", "context_prompt"),
    ("output", "streaming"),
    ("cancel", "on_backspace"),
)


def test_bool_fields_reject_int():
    """int is NOT a valid bool for the Rev 2 flag fields (context_prompt=1 is a typo)."""
    for section, key in _REV2_BOOL_FIELDS:
        with pytest.raises(TypeError, match=key):
            VoiceTypingConfig.from_toml({section: {key: 1}})
        with pytest.raises(TypeError, match=key):
            VoiceTypingConfig.from_toml({section: {key: 0}})


def test_bool_fields_reject_non_bool_types():
    """str/float/None/list are likewise rejected for the Rev 2 bool fields."""
    for section, key in _REV2_BOOL_FIELDS:
        for bad in ("yes", 1.0, None, [True]):
            with pytest.raises(TypeError, match=key):
                VoiceTypingConfig.from_toml({section: {key: bad}})


def test_bool_fields_round_trip_through_toml():
    """Genuine bools — including false — round-trip through TOML for the Rev 2 flags."""
    cfg = VoiceTypingConfig.from_toml(
        {
            "asr": {"context_prompt": False},
            "output": {"streaming": False},
            "cancel": {"on_backspace": False},
        }
    )
    assert cfg.asr.context_prompt is False
    assert cfg.output.streaming is False
    assert cfg.cancel.on_backspace is False


def test_cancel_devices_wrong_type_raises():
    """[cancel] devices must be a list of str; a bare str/int/set or non-str element raises."""
    for bad in ("event3", 3, {"event3"}, ["ok", 3], [None]):
        with pytest.raises(TypeError, match="devices"):
            VoiceTypingConfig.from_toml({"cancel": {"devices": bad}})


def test_cancel_devices_round_trips_through_toml():
    """[cancel] devices accepts a list of str and keeps it verbatim."""
    cfg = VoiceTypingConfig.from_toml({"cancel": {"devices": ["/dev/input/event3"]}})
    assert cfg.cancel.devices == ["/dev/input/event3"]


def test_cancel_devices_not_shared_between_instances():
    """default_factory gives each CancelConfig its OWN devices list (mirrors blocklist)."""
    a = CancelConfig()
    b = CancelConfig()
    a.devices.append("/dev/input/event9")
    assert b.devices == []


def test_cancel_unknown_key_raises():
    """A typo'd [cancel] key (on_backspce) surfaces as a loud TypeError, not silent ignore."""
    with pytest.raises(TypeError):
        VoiceTypingConfig.from_toml({"cancel": {"on_backspce": True}})


def test_lite_post_speech_silence_duration_default_and_round_trip_08():
    """PRD §4.2quater: the commit silence default rises to 0.8 and 0.8 round-trips."""
    assert VoiceTypingConfig().asr.lite_post_speech_silence_duration == 0.8
    cfg = VoiceTypingConfig.from_toml({"asr": {"lite_post_speech_silence_duration": 0.8}})
    assert cfg.asr.lite_post_speech_silence_duration == 0.8


# ---------------------------------------------------------------------------
# asr.device enum validation (VT-005): only "cuda" | "cpu" are valid. A value typo such as
# "gpu" or "cud" is a valid str (passes the type guard above) but would otherwise flow into
# _resolve_device_config -> AudioToTextRecorder(device=…) and fail noisily at construction
# (force-CPU retry) FAR from the config mistake. Reject it at load time with a clear ValueError.
# ValueError (not TypeError): the TYPE is correct, the VALUE is not.
# ---------------------------------------------------------------------------


def test_invalid_device_value_raises():
    """VT-005: a device value outside {cuda, cpu} is rejected at load with a ValueError naming it."""
    for bad in ("gpu", "cud", "CUDA", "cuda ", "auto", ""):
        with pytest.raises(ValueError, match="device"):
            VoiceTypingConfig.from_toml({"asr": {"device": bad}})


def test_valid_device_values_load():
    """VT-005: 'cuda' and 'cpu' are the accepted device values and round-trip through TOML."""
    for good in ("cuda", "cpu"):
        cfg = VoiceTypingConfig.from_toml({"asr": {"device": good}})
        assert cfg.asr.device == good


# ---------------------------------------------------------------------------
# output.backend enum validation (bugfix Issue 3 / VT-005 precedent): only "wtype" |
# "ydotool" | "null" are valid. A typo such as "wtyp" is a valid str but would otherwise
# flow into typing_backends.make_backend() and raise there — under systemd a
# Restart=on-failure crash-loop. Reject at load with a clear ValueError (TYPE correct,
# VALUE not — mirrors asr.device). make_backend() keeps its own ValueError as a 2nd gate.
# ---------------------------------------------------------------------------


def test_invalid_backend_value_raises():
    """bugfix Issue 3: a backend value outside {wtype, ydotool, null} is rejected at load with a ValueError naming it."""
    for bad in ("wtyp", "xterm", "WTYPE", "", "auto", "gpu"):
        with pytest.raises(ValueError, match="backend"):
            VoiceTypingConfig.from_toml({"output": {"backend": bad}})


def test_valid_backend_values_load():
    """bugfix Issue 3: 'wtype', 'ydotool', 'null' are the accepted backend values and round-trip through TOML."""
    for good in ("wtype", "ydotool", "null"):
        cfg = VoiceTypingConfig.from_toml({"output": {"backend": good}})
        assert cfg.output.backend == good


# ---------------------------------------------------------------------------
# [filter] load-time validation (validation Issue 4 / PRD §4.5 robustness).
# FilterConfig was the lone sub-config with no __post_init__; wrong-typed values crashed at runtime
# inside textproc.clean (called from on_final) instead of at load. Mirrors device/backend guards.
# ---------------------------------------------------------------------------


def test_filter_min_chars_wrong_type_raises():
    """validation Issue 4: a non-int [filter] min_chars is rejected at load with a TypeError naming it.

    Before the fix, min_chars = "two" loaded silently and textproc.clean raised
    TypeError: '<' not supported between 'int' and 'str' on EVERY final inside on_final.
    """
    for bad in ("two", 2.0, True, None, [2]):
        with pytest.raises(TypeError, match="min_chars"):
            VoiceTypingConfig.from_toml({"filter": {"min_chars": bad}})


def test_filter_blocklist_wrong_element_type_raises():
    """validation Issue 4: a non-str blocklist element is rejected at load with a TypeError naming the index.

    Before the fix, blocklist = [123] loaded silently and textproc.clean raised
    AttributeError: 'int' object has no attribute 'lower' on the blocklist check.
    """
    for bad in ([123], ["ok", 45], [True], [None]):
        with pytest.raises(TypeError, match=r"blocklist\["):
            VoiceTypingConfig.from_toml({"filter": {"blocklist": bad}})


def test_filter_valid_values_load():
    """validation Issue 4: valid [filter] values round-trip through TOML (regression guard for the new guard)."""
    cfg = VoiceTypingConfig.from_toml(
        {"filter": {"min_chars": 3, "blocklist": ["bye.", "thanks"]}}
    )
    assert cfg.filter.min_chars == 3
    assert cfg.filter.blocklist == ["bye.", "thanks"]



# ---------------------------------------------------------------------------
# [asr] lite_model (Rev 2 single-mode) — THE model: loaded once for partials + finals.
# Pinned here for parity with the other [asr] fields above: it is a PRD §4.5 default AND a
# __post_init__-validated str field.
# ---------------------------------------------------------------------------


def test_lite_model_round_trips_through_toml():
    """[asr] lite_model parses from TOML and overrides the default (Rev 2 single-mode)."""
    cfg = VoiceTypingConfig.from_toml({"asr": {"lite_model": "tiny.en"}})
    assert cfg.asr.lite_model == "tiny.en"               # overridden
    assert cfg.asr.language == "en"                      # other defaults kept


def test_lite_model_wrong_type_raises():
    """A non-string lite_model is rejected at load (mirrors the device type guard)."""
    for bad in (123, 12.0, True, None, ["small.en"]):
        with pytest.raises(TypeError, match="lite_model"):
            VoiceTypingConfig.from_toml({"asr": {"lite_model": bad}})


def test_lite_post_speech_silence_duration_round_trips_through_toml():
    """[asr] lite_post_speech_silence_duration parses from TOML and overrides the default (PRD §4.2ter)."""
    cfg = VoiceTypingConfig.from_toml({"asr": {"lite_post_speech_silence_duration": 0.3}})
    assert cfg.asr.lite_post_speech_silence_duration == 0.3   # overridden (0.8 default -> 0.3)


def test_lite_post_speech_silence_duration_wrong_type_raises():
    """A non-numeric lite_post_speech_silence_duration is rejected at load (mirrors the
    post_speech_silence_duration numeric guard; bool/str/None/list all raise TypeError)."""
    for bad in [True, "0.5", None, [0.5]]:
        with pytest.raises(TypeError, match="lite_post_speech_silence_duration"):
            VoiceTypingConfig.from_toml({"asr": {"lite_post_speech_silence_duration": bad}})


def test_none_for_float_field_raises():
    """None is not a valid numeric value -> TypeError (a common real-world wrong value)."""
    with pytest.raises(TypeError, match="auto_unload_idle_seconds"):
        VoiceTypingConfig.from_toml({"asr": {"auto_unload_idle_seconds": None}})


def test_valid_types_still_load():
    """Correctly-typed values load fine and override the defaults (no false positives)."""
    cfg = VoiceTypingConfig.from_toml(
        {"asr": {"auto_stop_idle_seconds": 30.0, "post_speech_silence_duration": 0.6}}
    )
    assert cfg.asr.auto_stop_idle_seconds == 30.0
    assert cfg.asr.post_speech_silence_duration == 0.6


def test_int_accepted_for_float():
    """A bare int is acceptable for a float field (TOML allows bare integers); not coerced."""
    cfg = VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": 30}})
    assert cfg.asr.auto_stop_idle_seconds == 30
    assert isinstance(cfg.asr.auto_stop_idle_seconds, int)  # accepted as-is, not coerced to float


def test_notify_ms_wrong_type_raises():
    """FeedbackConfig.notify_ms: a float/bool/str is rejected at load (same Issue 4 fix); int OK."""
    for bad in (2500.0, True, "2500"):
        with pytest.raises(TypeError, match="notify_ms"):
            VoiceTypingConfig.from_toml({"feedback": {"notify_ms": bad}})
    cfg = VoiceTypingConfig.from_toml({"feedback": {"notify_ms": 9999}})
    assert cfg.feedback.notify_ms == 9999


def test_from_toml_file_reads_toml(tmp_path):
    """from_toml_file parses a real TOML file (binary mode — tomllib requirement)."""
    f = tmp_path / "c.toml"
    f.write_text(
        '[asr]\nlanguage = "fr"\n[output]\nbackend = "null"\n',
        encoding="utf-8",
    )
    cfg = VoiceTypingConfig.from_toml_file(f)
    assert cfg.asr.language == "fr"
    assert cfg.output.backend == "null"


def test_invalid_toml_propagates(tmp_path):
    """Malformed TOML raises tomllib.TOMLDecodeError (fail loud, not silent default)."""
    import tomllib

    f = tmp_path / "bad.toml"
    f.write_text('bad = "unterminated string\n', encoding="utf-8")
    with pytest.raises(tomllib.TOMLDecodeError):
        VoiceTypingConfig.from_toml_file(f)


# ---------------------------------------------------------------------------
# load(path=None) — the PRD §4.5 search order
# ---------------------------------------------------------------------------

def test_load_with_explicit_path_bypasses_search(tmp_path):
    """load(path=...) loads that one file and skips the search order."""
    f = tmp_path / "explicit.toml"
    f.write_text('[asr]\ndevice = "cpu"\n', encoding="utf-8")
    cfg = VoiceTypingConfig.load(f)
    assert cfg.asr.device == "cpu"
    assert cfg.asr.lite_model == "small.en"  # non-overridden default kept


def test_search_order_xdg_wins_over_repo(tmp_path, monkeypatch):
    """PRD §4.5: XDG config wins over repo config when BOTH exist."""
    xdg_file = tmp_path / "xdg.toml"
    repo_file = tmp_path / "repo.toml"
    xdg_file.write_text('[asr]\nlanguage = "de"\n', encoding="utf-8")   # XDG marker
    repo_file.write_text('[asr]\nlanguage = "ja"\n', encoding="utf-8")  # repo marker
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(xdg_file))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(repo_file))
    cfg = VoiceTypingConfig.load(None)
    assert cfg.asr.language == "de"  # XDG won


def test_search_order_repo_used_when_xdg_absent(tmp_path, monkeypatch):
    """When the XDG candidate does not exist, the repo candidate is used."""
    repo_file = tmp_path / "repo.toml"
    repo_file.write_text('[asr]\nlanguage = "ja"\n', encoding="utf-8")
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(tmp_path / "missing-xdg.toml"))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(repo_file))
    cfg = VoiceTypingConfig.load(None)
    assert cfg.asr.language == "ja"


def test_search_order_missing_file_falls_back_to_defaults(tmp_path, monkeypatch):
    """No candidate exists → built-in dataclass defaults (NOT an error)."""
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(tmp_path / "no-xdg.toml"))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(tmp_path / "no-repo.toml"))
    cfg = VoiceTypingConfig.load(None)
    assert cfg == VoiceTypingConfig()  # pure defaults


def test_xdg_config_path_falls_back_to_home_when_unset(monkeypatch):
    """XDG_CONFIG_HOME unset/empty → ~/.config/voice-typing/config.toml (XDG spec)."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    expected = os.path.join(os.path.expanduser("~/.config"), "voice-typing", "config.toml")
    assert cfgmod._xdg_config_path() == expected


def test_xdg_config_path_respects_env(monkeypatch):
    """XDG_CONFIG_HOME set → used verbatim (with the voice-typing/config.toml suffix)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/xdg")
    assert cfgmod._xdg_config_path() == "/custom/xdg/voice-typing/config.toml"


# ---------------------------------------------------------------------------
# FeedbackConfig.resolved_state_file() — lazy XDG_RUNTIME_DIR resolution
# ---------------------------------------------------------------------------

def test_resolved_state_file_uses_xdg_runtime_dir(monkeypatch):
    """Empty state_file + XDG_RUNTIME_DIR set → <RUNTIME>/voice-typing/state.json."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert FeedbackConfig().resolved_state_file() == "/run/user/1000/voice-typing/state.json"


def test_resolved_state_file_explicit_path_returned_as_is():
    """Non-empty state_file is returned verbatim (no XDG resolution)."""
    fb = FeedbackConfig(state_file="/tmp/custom-state.json")
    assert fb.resolved_state_file() == "/tmp/custom-state.json"


def test_resolved_state_file_raises_when_xdg_runtime_unset(monkeypatch):
    """Empty state_file + XDG_RUNTIME_DIR unset → RuntimeError (no safe default)."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    with pytest.raises(RuntimeError):
        FeedbackConfig().resolved_state_file()


# ---------------------------------------------------------------------------
# Module-level load() wrapper
# ---------------------------------------------------------------------------

def test_module_level_load_matches_classmethod(tmp_path, monkeypatch):
    """voice_typing.config.load() is a thin wrapper over VoiceTypingConfig.load()."""
    monkeypatch.setattr(cfgmod, "_xdg_config_path", lambda: str(tmp_path / "x.toml"))
    monkeypatch.setattr(cfgmod, "_repo_config_path", lambda: str(tmp_path / "r.toml"))
    assert cfgmod.load() == VoiceTypingConfig()


# ---------------------------------------------------------------------------
# [log] config (P1.M4.T1.S3 — daemon logging verbosity)
# ---------------------------------------------------------------------------

def test_log_config_default_and_override():
    """LogConfig.level defaults to INFO and round-trips through TOML (PRD §4.2)."""
    from voice_typing.config import LogConfig, VoiceTypingConfig
    assert VoiceTypingConfig().log.level == "INFO"
    assert LogConfig(level="DEBUG").level == "DEBUG"
    # round-trips through TOML
    cfg = VoiceTypingConfig.from_toml({"log": {"level": "DEBUG"}})
    assert cfg.log.level == "DEBUG"

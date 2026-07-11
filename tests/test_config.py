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
    FeedbackConfig,
    FilterConfig,
    OutputConfig,
    VoiceTypingConfig,
)

# PRD §4.5 authoritative blocklist (pinned verbatim, incl. trailing periods).
_PRD_BLOCKLIST = [
    "thank you.",
    "thanks for watching.",
    "you",
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
    assert cfg.asr.final_model == "distil-large-v3"
    assert cfg.asr.realtime_model == "small.en"
    assert cfg.asr.language == "en"
    assert cfg.asr.device == "cuda"
    assert cfg.asr.post_speech_silence_duration == 0.6
    assert cfg.asr.realtime_processing_pause == 0.15
    assert cfg.asr.auto_stop_idle_seconds == 30.0
    # [output]
    assert cfg.output.backend == "wtype"
    assert cfg.output.tmux_target == ""
    assert cfg.output.append_space is True
    # [feedback]
    assert cfg.feedback.state_file == ""
    assert cfg.feedback.hypr_notify is True
    assert cfg.feedback.notify_ms == 2500
    assert cfg.feedback.notify_on_final is True
    # [filter]
    assert cfg.filter.min_chars == 2
    assert cfg.filter.blocklist == _PRD_BLOCKLIST


def test_defaults_match_cuda_check():
    """Drift guard: asr model/device defaults must equal cuda_check.CUDA_DEFAULTS.

    config holds the DESIRED values; cuda_check holds the same values as its CUDA
    path. If these drift, the daemon's cuda_check override (P1.M4.T1.S1) would
    contradict the config defaults.
    """
    from voice_typing.cuda_check import CUDA_DEFAULTS

    assert AsrConfig().final_model == CUDA_DEFAULTS["final_model"]
    assert AsrConfig().realtime_model == CUDA_DEFAULTS["realtime_model"]
    assert AsrConfig().device == CUDA_DEFAULTS["device"]


def test_field_types_are_tomllib_natural_types():
    """Defaults carry the Python types tomllib yields (float for 0.6, int, bool)."""
    cfg = VoiceTypingConfig()
    assert isinstance(cfg.asr.post_speech_silence_duration, float)  # 0.6, not int 0
    assert isinstance(cfg.asr.realtime_processing_pause, float)
    assert isinstance(cfg.filter.min_chars, int)
    assert isinstance(cfg.feedback.notify_ms, int)
    assert isinstance(cfg.output.append_space, bool)
    assert isinstance(cfg.filter.blocklist, list)


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
    cfg = VoiceTypingConfig.from_toml({"asr": {"language": "es"}})
    assert cfg.asr.language == "es"                  # overridden
    assert cfg.asr.final_model == "distil-large-v3"  # same-section default kept
    assert cfg.output.backend == "wtype"             # other section untouched
    assert cfg.filter.min_chars == 2                 # other section untouched


def test_from_toml_empty_dict_is_all_defaults():
    """An empty TOML mapping yields pure defaults (no tables present)."""
    assert VoiceTypingConfig.from_toml({}) == VoiceTypingConfig()


def test_from_toml_unknown_key_raises():
    """A typo'd key must surface as a loud TypeError, not be silently ignored."""
    with pytest.raises(TypeError):
        VoiceTypingConfig.from_toml({"output": {"bakcend": "tmux"}})


def test_from_toml_section_not_a_table_raises():
    """A scalar where a TOML table is expected must raise (not silently default)."""
    with pytest.raises(TypeError):
        VoiceTypingConfig.from_toml({"asr": "not-a-table"})


def test_from_toml_file_reads_toml(tmp_path):
    """from_toml_file parses a real TOML file (binary mode — tomllib requirement)."""
    f = tmp_path / "c.toml"
    f.write_text(
        '[asr]\nlanguage = "fr"\n[output]\nbackend = "tmux"\ntmux_target = "voicetest:0.0"\n',
        encoding="utf-8",
    )
    cfg = VoiceTypingConfig.from_toml_file(f)
    assert cfg.asr.language == "fr"
    assert cfg.output.backend == "tmux"
    assert cfg.output.tmux_target == "voicetest:0.0"


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
    assert cfg.asr.final_model == "distil-large-v3"  # non-overridden default kept


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

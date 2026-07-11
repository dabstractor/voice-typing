"""Drift guard: the repo config.toml must equal the dataclass defaults (PRD §4.5).

Catches the code<->config drift that would otherwise go unnoticed until a user
reloads: if a default changes in voice_typing/config.py, repo config.toml must
change in lockstep (and vice-versa). This is the permanent form of the
P1.M2.T1.S2 acceptance check ("load() parses it with no overrides").

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_config_repo_default.py -v
"""
from __future__ import annotations

from voice_typing.config import VoiceTypingConfig, _repo_config_path


def test_repo_config_toml_equals_defaults():
    """Parsing <repo>/config.toml must yield NO overrides over the defaults."""
    repo_default = VoiceTypingConfig.from_toml_file(_repo_config_path())
    assert repo_default == VoiceTypingConfig(), (
        "repo config.toml drifts from voice_typing/config.py defaults; "
        "edit config.toml (or config.py) so the two match exactly. "
        f"Diff:\n  repo:    {repo_default!r}\n  defaults:{VoiceTypingConfig()!r}"
    )


def test_repo_config_toml_has_no_extra_keys():
    """The repo default must carry only the 16 schema keys (no compute_type etc.)."""
    import tomllib

    with open(_repo_config_path(), "rb") as fh:
        data = tomllib.load(fh)
    expected = {
        "asr": {
            "final_model",
            "realtime_model",
            "language",
            "device",
            "post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
        },
        "output": {"backend", "tmux_target", "append_space"},
        "feedback": {"state_file", "hypr_notify", "notify_ms", "notify_on_final"},
        "filter": {"min_chars", "blocklist"},
        "log": {"level"},
    }
    assert set(data.keys()) == set(expected.keys()), data.keys()
    for section, keys in expected.items():
        assert set(data[section].keys()) == keys, (section, data[section].keys())

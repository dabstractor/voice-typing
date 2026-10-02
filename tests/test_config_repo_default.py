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
    """The repo default must carry only the 21 schema keys (no compute_type etc.)."""
    import tomllib

    with open(_repo_config_path(), "rb") as fh:
        data = tomllib.load(fh)
    expected = {
        "asr": {
            "lite_model",                 # Rev 2 single-mode: THE model (partials + finals)
            "language",
            "device",
            "post_speech_silence_duration",
            "lite_post_speech_silence_duration",   # PRD §4.2quater: commit silence under streaming
            "context_prompt",             # PRD §4.2quater: rolling committed-context conditioning
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
            "auto_unload_idle_seconds",   # P1.M3.T1.S1: idle-unload knob (PRD §4.2bis)
        },
        "output": {"backend", "append_space", "streaming"},  # streaming: PRD §4.2quater
        "cancel": {"on_backspace", "devices"},  # PRD §4.2quater: Backspace-cancel section
        "feedback": {"state_file", "hypr_notify", "notify_ms", "notify_on_final"},
        "filter": {"min_chars", "blocklist"},
        "log": {"level"},
    }
    assert set(data.keys()) == set(expected.keys()), data.keys()
    for section, keys in expected.items():
        assert set(data[section].keys()) == keys, (section, data[section].keys())


def test_repo_config_lite_model_comment_names_end_state_binds():
    """The lite_model comment must name Ctrl+Alt+Super+D (the end-state toggle bind), not the old lite binds.

    Rev 2 collapse (PRD §4.2quater): exactly ONE toggle bind (Ctrl+Alt+Super+D) and ONE cancel
    bind (Alt+Super+Backspace); toggle-lite is gone, so the old `voicectl toggle-lite` /
    SUPER+ALT+D-as-lite-bind phrasing must not survive in the comments. config.toml is
    user-facing config DOC (Mode A); tomllib DROPS comments, so the value drift-guards above
    don't catch this — assert on the RAW text. The cancel bind must be documented somewhere in
    the file (the [cancel] section).
    """
    with open(_repo_config_path()) as fh:
        text = fh.read()
    lite_lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("lite_model")]
    assert lite_lines, "no lite_model line in config.toml"
    line = lite_lines[0]
    assert "Ctrl+Alt+Super+D" in line, (
        "config.toml lite_model comment must reference Ctrl+Alt+Super+D (the end-state toggle "
        "bind, PRD §4.2quater), not a stale lite bind."
    )
    assert "toggle-lite" not in line, "config.toml lite_model comment still cites toggle-lite"
    assert "SUPER+ALT+D" not in line, (
        "config.toml lite_model comment still uses the old SUPER+ALT+D-as-lite-bind vocabulary"
    )
    assert "SUPER+ALT+F" not in line, "config.toml lite_model comment still has the stale SUPER+ALT+F"
    assert "Alt+Super+Backspace" in text, (
        "config.toml must document the end-state cancel bind Alt+Super+Backspace ([cancel] section)."
    )

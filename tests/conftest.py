"""Shared pytest fixtures for voice-typing tests.

Hosts the opt-in `hermetic_daemon_media` fixture (BUG-001 seam fix, P1.M1.T1.S1) and the
shared `hermetic_cfg` builder (P1.M1.T1.S2). The fixture is deliberately NOT auto-requested
and the daemon/ducking_heal modules are imported ONLY at fixture invocation (never at
collection): importing voice_typing.daemon eagerly would drag the daemon import into every
test session (import-purity suites such as test_ime_manager.py rely on it staying absent),
while an auto-applied fixture would change semantics for not-yet-migrated daemon tests
while masking the fail-closed factory raise as a collection error. Ordinary constructor
helpers share ONE discipline through the plain `hermetic_cfg()` function (config-only
imports — safe for any test module to import).
"""
from __future__ import annotations

import dataclasses

import pytest

from voice_typing.config import VoiceTypingConfig


def hermetic_cfg(cfg: VoiceTypingConfig | None = None, *, state_file: str | None = None) -> VoiceTypingConfig:
    """Test-owned hermetic config for ORDINARY daemon construction (BUG-001 / P1.M1.T1.S2).

    duck_mode is ALWAYS 'off' (the daemon builds a ducker only when duck_mode != 'off', and
    _duck_engage no-ops when the ducker is None — so this one wrap covers _arm(),
    start()/toggle(), the run-loop lazy first-arm and socket-driven arms).

    feedback.state_file precedence: the `state_file` param wins; else a NON-EMPTY supplied
    cfg.feedback.state_file is PRESERVED (real-Feedback tmp_path sites keep their writable
    private state); else a nonexistent private default under the system temp dir (missing
    file ⇒ the construction-time boot-heal read swallows to False; fake-feedback sites never
    write state anyway).

    Returns a NEW config (dataclasses.replace at top + audio + feedback; mirrors the
    FilterConfig.blocklist not-shared discipline); it never mutates its argument or any
    production default. Plain function (config-only imports) so constructor HELPERS without
    fixture access share the fixture's discipline; the fixture's hermetic() delegates here.
    """
    import os
    import tempfile

    base = cfg if cfg is not None else VoiceTypingConfig()
    if state_file is None:
        supplied = base.feedback.state_file
        state_file = (
            supplied
            if supplied
            else os.path.join(tempfile.gettempdir(), f"vt-hermetic-{os.getpid()}-state.json")
        )
    return dataclasses.replace(
        base,
        audio=dataclasses.replace(base.audio, duck_mode="off"),
        feedback=dataclasses.replace(base.feedback, state_file=state_file),
    )


@pytest.fixture
def hermetic_daemon_media(monkeypatch, tmp_path):
    """Opt-in hermeticity for daemon-constructing tests (BUG-001 / P1.M1.T1.S1).

    USE: request this fixture in any test that constructs a VoiceTypingDaemon and
    arms it; build the daemon's config with the returned `hermetic(cfg=None) ->
    cfg` helper and pass it to the constructor (or a `_wire_daemon`-style helper).
    Guarantees, for the duration of ONE test (function-scoped monkeypatch +
    tmp_path — isolation happens at invocation, never at collection/import):

      1. NO REAL DUCKER CAN BE BUILT: `voice_typing.daemon._build_default_ducker`
         is patched to raise AssertionError, so an unguarded construction
         (default duck_mode='mpris', no `ducker=`) fails SYNCHRONOUSLY at the
         daemon ctor — before any thread or subprocess can spawn (the factory is
         construction-pure; the `vt-ducking` worker only spawns on first
         dispatch). The sanctioned escapes: inject a fake via the ctor's
         `ducker=` seam (cf. `_FakeDucker` in tests/test_ducking.py — the
         INTENTIONAL exception for the dedicated duck-wiring tests, P1.M1.T1.S3),
         or use this helper's `duck_mode="off"` config (the ordinary case).
      2. THE PERSISTED DUCK-FLAG READ IS ISOLATED: `ducking_heal.read_ducked_flag`
         is patched to a recording fake returning False (module-attribute patch —
         the daemon looks the attribute up at call time), so no `vt-duck-heal`
         thread can start even if the operator's real state would say "ducked".
         The calls list is exposed as `hermetic.read_calls` for assertions.
      3. CONFIG-LEVEL BELT-AND-SUSPENDERS: the helper's config points
         `feedback.state_file` at a private nonexistent tmp path, so even an
         un-patched resolved-state resolution can never see operator state.

    NO global `subprocess.run` patch (and no PATH/busctl shim): a real media
    command must never be able to "prove" failure — the synchronous factory
    raise is the only sanctioned failure proof, and a global patch would hide
    future real leaks. The helper returns a NEW config built with
    `dataclasses.replace` (top level + audio + feedback sub-configs, mirroring
    the FilterConfig.blocklist not-shared discipline); it never mutates its
    argument or any production default.
    """
    state_path = tmp_path / "state.json"
    import voice_typing.daemon as daemon_mod  # lazy: fixture invocation, never collection
    import voice_typing.ducking_heal as ducking_heal_mod

    def hermetic(cfg: VoiceTypingConfig | None = None) -> VoiceTypingConfig:
        # Delegates to the shared builder; the fixture's private tmp state wins (S2).
        return hermetic_cfg(cfg, state_file=str(state_path))

    calls: list = []

    def _fake_read_ducked_flag(cfg):
        calls.append(cfg)
        return False  # isolated: never consults cfg.feedback.resolved_state_file()

    monkeypatch.setattr(
        ducking_heal_mod, "read_ducked_flag", _fake_read_ducked_flag, raising=True
    )

    def _fail_closed_factory(cfg):
        raise AssertionError(
            "hermetic_daemon_media: unguarded _build_default_ducker use — a real ducker "
            "would dispatch busctl --user at the live session (BUG-001). Inject a fake "
            "via ducker= (the dedicated duck-wiring tests) or build cfg with this "
            "fixture's hermetic() helper (duck_mode='off')."
        )

    monkeypatch.setattr(
        daemon_mod, "_build_default_ducker", _fail_closed_factory, raising=True
    )

    hermetic.read_calls = calls  # tests may assert the read was consulted/isolated
    return hermetic

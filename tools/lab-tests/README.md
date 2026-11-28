# Rev-4 bulk-text lab reference (PRD §4.2sexies — superseded)

These suites exercised the retired `output.delivery="bulk-text"` experiment. The delivery
selector is retired at the config boundary (P1.M1.T1.S1) and the daemon-side bulk routing,
activation, and seams are detached (P1.M1.T1.S2); `voice_typing/bulk_controller.py` and
`voice_typing/ime/*` remain as the lab implementation, NOT product routing.

**These files are NOT collected by any pytest run** (`[tool.pytest.ini_options]
norecursedirs` excludes `tools/` in pyproject.toml). They are kept for the evidence trail
(controller/IM-adapter/G5 timing measurements — see tests/G5_TIMING_EVIDENCE.md and the
plan/009 architecture notes) and as the reference implementation for any future native
editor integration, which per PRD §4.5 will be a separate opt-in surface, never a
`output.delivery` backend.

They are NOT runnable in place: they import `conftest` helpers from `tests/` and product
symbols the daemon no longer exports. Treat them as read-only history.

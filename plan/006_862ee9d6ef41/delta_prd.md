# Delta PRD: Reconcile stale VT-001 caveat in the recorder-host subprocess note

**Base PRD:** `PRD.md` (current revision). **Scope of this delta:** one documentation
correction. The large diff between the prior PRD snapshot and the current `PRD.md` is **already
implemented and committed**; the only genuine remaining work is fixing a stale bug reference.

**Size:** Tiny. ~1 sentence of actual change. This PRD is deliberately short to match.

---

## 1. What changed in the PRD (diff summary) — and why almost all of it is already done

The diff against the prior snapshot touches ~12 hunks spanning §3, §4.1, §4.2bis, §4.4, §4.5, §4.9,
§4.10, §5. Grouped:

1. **Recorder-host subprocess architecture (§4.1, §4.2bis).** `PRD.md` gained the "Implementation
   note (recorder-host subprocess)" paragraph and the Idle-unload "Resolved by … `killpg`" sentence;
   the §4.1 layout gained `recorder_host.py`, `cuda_check.py`, `prefetch.py`, `launch_daemon.sh`,
   `status.sh`, `hypr-binds.conf`.
2. **Recorder kwargs (§4.4).** `silero_use_onnx=True` → `silero_backend="auto"`; added
   `ensure_sentence_starting_uppercase=False`, `ensure_sentence_ends_with_period=False`,
   `no_log_file=True`; cuDNN note rewritten as the "Realized approach" (`launch_daemon.sh`).
3. **Config (§4.5).** New `[log]` section (`level = "INFO"`).
4. **systemd unit (§4.9).** Overhaul to `graphical-session.target` (VT-004), `ExecStartPre`
   `import-environment`, `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (VT-003),
   `KillMode=mixed`, `TimeoutStopSec=15`.
5. **Keybinds / deps / typo (§4.10, §5, §3).** `$HOME/.local/bin/voicectl` paths; the
   `realtimestt[faster-whisper,silero-vad]` / `nvidia-cudnn-cu12==9.*` / `huggingface_hub>=0.23` pin;
   the `github.com/KoljaB/RealtimeSTT` URL fix.

**Implementation status — all of the above is DONE and committed**, primarily in:
- `c01b0e9` "Formalize subprocess architecture and service wiring" (PRD-only, +38 −8)
- `05b4f93` "Harden portability, init lifecycle, and config" (PRD + code + tests, +576 −76)

Verified in the working tree: `voice_typing/{recorder_host,cuda_check,prefetch}.py`,
`voice_typing/{launch_daemon.sh,status.sh}`, `hypr-binds.conf` all exist; `daemon.py` carries
`silero_backend="auto"`, `ensure_sentence_*`, `no_log_file` (lines ~106–111) and the
`killpg`-after-5 s-join teardown; `config.py` has `class LogConfig` and `config.toml` has `[log]`;
`systemd/voice-typing.service` matches the unit in §4.9; `pyproject.toml` carries the pinned deps.
README and the test suite (`test_systemd_unit.py`, `test_recorder_host.py`, `test_status_sh.py`,
plus the VT-001 regression guards in `test_daemon.py`) are already synced.

**This delta therefore creates NO implementation tasks.** The work is referenced, not re-implemented
(SOW: "reference existing implementations rather than re-implementing").

---

## 2. The one genuine gap — a stale caveat in PRD §4.2bis

PRD §4.2bis (the recorder-host subprocess note) ends with:

> The daemon process is therefore *intended* to never import `RealtimeSTT`/`torch`/`ctranslate2` and
> never create a CUDA context — **caveat: `voicectl status` currently violates this; see BUGS.md
> VT-001.**

Both clauses are now false:

- **VT-001 is resolved, not current.** `VoiceTypingDaemon._resolved_device()` / `_unprobed_device_config()`
  (`voice_typing/daemon.py`, docstrings at lines ~1585, ~1599, ~1609) enforce the invariant: status
  NEVER calls `cuda_check.resolve_device_and_models`; the resolved device is seeded from config and
  replaced by the child's report on arm. The invariant is pinned by ~8 regression assertions in
  `tests/test_daemon.py` (e.g. `status_snapshot must NOT call cuda_check … (VT-001)`) and a guard that
  fails if any future status field reintroduces a probe (`VT-001/VT-008: the daemon must stay
  CUDA-free`).
- **`BUGS.md` does not exist** — and never has (no commit in `git log -- BUGS.md`). The reference is
  a dangling pointer to a file that was never created, for a bug that is no longer present.

A reader following the caveat today would (a) be told the daemon leaks a CUDA context in status,
which is untrue, and (b) look for a `BUGS.md` that isn't there. This is pure documentation drift
introduced when the subprocess note was written against the pre-fix state and never reconciled after
VT-001 was closed.

### 2.1 Documentation impact

- **Mode A (doc-with-work):** none beyond the edit below — the per-module docs (`daemon.py`
  VT-001 docstrings, the test guards, README's `RecorderHost.stop()` / `launch_daemon.sh` coverage)
  are already current.
- **Mode B (changeset-level docs):** none — README.md and `tests/ACCEPTANCE.md` were synced in the
  same commits (`05b4f93` touched README; acceptance criteria are behaviour-level and unchanged by
  the subprocess implementation detail). No separate cross-cutting doc task is warranted.

---

## 3. The work (single task)

**Fix the stale VT-001/BUGS.md caveat in `PRD.md` §4.2bis** so it reflects that the invariant is
enforced and regression-guarded rather than "currently violated".

- File: `PRD.md`, the "Implementation note (recorder-host subprocess)" paragraph (currently the only
  line containing `currently violates this`).
- Replace the bolded caveat. Suggested wording (preserves the `VT-001` cross-reference as the stable
  identifier used throughout the code/tests, and drops the nonexistent `BUGS.md` pointer):

  > The daemon process is therefore *intended* to never import `RealtimeSTT`/`torch`/`ctranslate2`
  > and never create a CUDA context. **This invariant is enforced by `status_snapshot()` returning
  > only the cached / config-seeded device (never probing CUDA) and pinned by regression tests
  > (VT-001); the child reports the authoritative resolved device on arm.**

- Do **not** create a `BUGS.md` for a fixed bug — the reference should be removed, not satisfied.
- No code or test change is required; VT-001 is already guarded. (Optional belt-and-suspenders: if a
  grep-based drift guard for "`currently violates`" / "`BUGS.md`" is wanted, add it — but this is
  not required and would be the only new test surface.)

**Acceptance:** `grep -rn 'currently violates this' PRD.md` returns nothing; `grep -rn 'BUGS.md'
PRD.md` returns nothing (or, if `VT-001` is retained as a cross-reference, it no longer points at a
`BUGS.md`); the §4.2bis paragraph reads as a resolved invariant, not an open caveat. The repo builds
and the existing `pytest` suite remains green (no behaviour change).

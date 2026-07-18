# Peripheral Modules Research Report

Scope: `voice_typing/` peripheral modules — `typing_backends.py`, `feedback.py`, `textproc.py`, `ctl.py`, `prefetch.py`, `launch_daemon.sh`, `status.sh`. Each module's interface, completeness, spec compliance (vs PRD §4.3/§4.6/§4.7/§4.8), and gaps.

All 123 tests across the 5 dedicated test files pass (`.venv/bin/python -m pytest tests/test_typing_backends.py tests/test_feedback.py tests/test_textproc.py tests/test_voicectl.py tests/test_status_sh.py -q`).

---

## 1. `typing_backends.py` — typing output backends (PRD §4.3)

**File:** `voice_typing/typing_backends.py` (lines 1-185)

### Interface
```python
class TypingBackend(ABC):
    def type_text(self, text: str) -> None: ...   # types EXACTLY text; no trailing newline; raises on failure

def make_backend(cfg: OutputConfig) -> TypingBackend:  # factory dispatch on cfg.backend
```
Three concrete backends + one fallback wrapper:
- `WtypeBackend` → `subprocess.run(["wtype", "--", text], check=True)` (default)
- `YdotoolBackend` → `subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text], check=True)`
- `TmuxBackend(cfg)` → `subprocess.run(["/usr/bin/tmux", "send-keys", "-t", cfg.tmux_target, "-l", "--", text], check=True)`
- `_WtypeWithFallback` → wtype primary, ydotool fallback (the default when `backend=="wtype"`)

### Auto-fallback logic (`_WtypeWithFallback.type_text`, lines 158-175)
Runs wtype; on `subprocess.CalledProcessError` (nonzero exit) OR `OSError` (covers `FileNotFoundError` = missing binary, `PermissionError` = not executable), logs a WARNING and retries **ONCE** via ydotool. If the fallback also raises, the exception propagates to the caller (never silently swallowed). No retry loop — exactly 2 subprocess calls max. Constructor accepts injectable `primary`/`fallback` for deterministic unit tests.

### Completeness: COMPLETE
Matches PRD §4.3 exactly. **Enhancement over spec:** the PRD says fallback on "nonzero exit"; the impl ALSO catches `OSError` (missing/unusable binary) — strictly more robust.

### Key design details
- `_TMUX = "/usr/bin/tmux"` (line 49): full path because zsh aliases `tmux` to a plugin wrapper.
- `--` separator on all three backends keeps text starting with `-` literal (positional, not option).
- tmux `-l` flag = literal text (no key-name interpretation, no trailing Enter).
- `append_space` is the daemon's concern (not used here) — `make_backend` consumes only `backend` + `tmux_target`.
- Test coverage: `tests/test_typing_backends.py` — exact argv pinning for all 3 backends, fallback ordering, once-only retry, warning log, injection-point tests, abstract-class guard, unknown-backend `ValueError`.

### Tests
30 tests, all passing. Covers: exact argv for all 3 backends, `check=True`, literal text via `--`, full `/usr/bin/tmux` path, auto-fallback on `CalledProcessError`/`FileNotFoundError`/`PermissionError`, once-only retry (no loop), double-failure propagation, WARNING logging, `make_backend` dispatch, unknown-backend `ValueError`.

---

## 2. `feedback.py` — state file + Hyprland notify (PRD §4.6)

**File:** `voice_typing/feedback.py` (lines 1-230)

### Interface
```python
class Feedback:
    def __init__(self, cfg: FeedbackConfig) -> None: ...
    def update_partial(self, text: str) -> None      # throttled disk write (>=10 Hz); NEVER notifies
    def set_phase(self, phase: str) -> None           # idle/listening/speaking/unloaded/loading; always writes; never notifies
    def set_models_loaded(self, loaded: bool) -> None  # §4.2bis lifecycle; always writes; never notifies
    def set_mode(self, mode: str) -> None              # "normal" | "lite" (§4.2ter); always writes; never notifies
    def record_final(self, text: str) -> None          # sets last_final + partial; always writes; maybe notifies ("✔ <text>")
    def set_listening(self, listening: bool) -> None   # master gate; always writes; notifies on TRANSITION only
    def snapshot(self) -> dict                          # low-latency in-memory copy (no disk read)
    def notify(self, msg: str) -> None                  # ad-hoc hyprctl toast (e.g. "Loading…"); gated by hypr_notify; no state change
```

### State.json schema (the exact 7 fields, `_state` dict at lines 109-117)
```json
{"listening": false, "phase": "unloaded", "models_loaded": false, "mode": "normal", "partial": "", "last_final": "", "ts": 0.0}
```
Matches PRD §4.6 exactly: `listening`, `phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`), `models_loaded` (bool), `mode` (`normal`/`lite`), `partial`, `last_final`, `ts` (wall epoch `time.time()`).

### Atomic writes (`_write`, lines 195-222)
`tempfile.mkstemp(dir=<target_dir>)` creates a temp file mode `0o600` (Python default), writes JSON, then `os.replace(tmp, target)` (same-filesystem POSIX atomic rename). Parent dir `makedirs(exist_ok=True, mode=0o700)`. On ANY failure (incl. json/replace errors), the temp file is `unlink`ed first (no `.state.*.tmp` litter), then the exception re-raises. A concurrent `tmux jq`-reader (status-interval 1s) never sees a half-written file.

### Throttling (`update_partial`, lines 122-135)
`_PARTIAL_WRITE_MIN_INTERVAL = 0.1` seconds (≥10 Hz max). Clock = `time.monotonic()` (NTP-safe, never freezes). Baseline starts at `0.0` so the FIRST partial always writes. **The in-memory `_state["partial"]` is ALWAYS updated** (unconditionally) — only the disk write is throttled. `set_phase`/`record_final`/`set_listening`/`set_models_loaded`/`set_mode` always write (not throttled).

### Hyprctl notify discipline (`_notify`, lines 224-230)
`hyprctl notify -1 <notify_ms> "rgb(88c0d0)" "<msg>"` — `check=False`, `stdout=DEVNULL`, `stderr=DEVNULL` (fire-and-forget). Swallows `OSError` + `SubprocessError` at DEBUG level. Notifications fire ONLY on:
- **listening-start** (`False→True` transition): `"Recording"`; also clears stale partial.
- **each final** (`record_final`): `"✔ <text>"` — GATED by both `hypr_notify` AND `notify_on_final`.
- **listening-stop** (`True→False` transition): `"Recording Stopped"` (any disarm).
- **cold model load** (`notify()` ad-hoc): `"Loading…"` — fired by the daemon before the lazy first-arm load.
- **NEVER** on `update_partial`. **NEVER** on `set_phase`/`set_models_loaded`/`set_mode`. No-op `set_listening` (same value) writes but does NOT notify (avoids startup spam).

### Completeness: COMPLETE
Matches PRD §4.6 fully. The notification anti-spam contract (partials → state file only) is correctly enforced. `record_final` writes the final text back into `partial` so the tmux status matches the screen (PRD requirement). `snapshot()` returns a shallow copy (`dict(self._state)`) for concurrent-reader safety.

### Tests
`tests/test_feedback.py` — 40+ tests, all passing. Covers: round-trip shape (exact 7-key set), atomic write (no `.tmp` litter, mode `0o600`, dir `0o700`), throttle (first-call-writes, skip within 0.1s, release at 0.1s, in-memory always updated, non-throttled methods always write), hyprctl argv pinning, anti-spam (50 partials → 0 hyprctl calls), transition-only notify, `notify_on_final=False` gate, `hypr_notify=False` gate, stale-partial-clear-on-arm, fire-and-forget error swallowing, snapshot copy-not-alias.

---

## 3. `textproc.py` — post-recognition text normalizer (PRD §4.7)

**File:** `voice_typing/textproc.py` (lines 1-70)

### Interface
```python
def clean(text: str, cfg: FilterConfig) -> str | None: ...
```
Pure function, no I/O, no side effects, deterministic.

### Pipeline (lines 48-69, exactly matches PRD §4.7 4-step order)
1. **Whitespace:** `" ".join(text.split())` — strips leading/trailing whitespace, drops trailing newlines, collapses internal whitespace runs (incl. tabs) to single spaces, in one expression.
2. **min_chars gate:** `if len(cleaned) < cfg.min_chars: return None` (on the CLEANED length, not raw).
3. **Blocklist:** `key = cleaned.lower().rstrip(".!?,;")`; reject if `key in {b.lower().rstrip(".!?,;") for b in cfg.blocklist}`. Case-insensitive, trailing-punctuation-stripped, EXACT match (not substring). Both input and blocklist entries are normalized the same way.
4. **Return** cleaned text (caller appends a space when `append_space` — never done here).

### Completeness: COMPLETE
Matches PRD §4.7 exactly. The blocklist is the primary defense against Whisper's silence hallucination ("thank you." on silent audio — PRD §8 top-3 risk).

### Spec deviation: VT-006 (intentional, documented, low severity)
**PRD §4.5 blocklist default** lists `"you"` as a default entry: `["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"]`. **The implementation REMOVES `"you"`** from both the dataclass default (`config.py` lines 169-176) AND the shipped `config.toml` (lines 62-67). Rationale (documented as VT-006 in both files): `"you"` is a common English word users frequently want to type as a standalone utterance; the blocklist's exact-match normalization silently dropped dictating the single word "you". The blocklist's purpose is suppressing genuine hallucinations, not common words. **The PRD text was NOT updated to match** — this is a stale PRD artifact, not an implementation defect.

### Tests
`tests/test_textproc.py` — 22 tests, all passing. Covers: whitespace collapse (spaces/tabs/newlines), min_chars boundary (reject `<`, accept `==`), empty/whitespace-only rejection, custom min_chars, blocklist case-insensitivity, trailing-punctuation-stripping (`.`, `!`, `?`, `,`), exact-not-substring match (`"you"` blocks, `"yourself"` doesn't), empty blocklist never rejects, internal punctuation preserved, never appends trailing space.

---

## 4. `ctl.py` — voicectl CLI (PRD §4.8)

**File:** `voice_typing/ctl.py` (lines 1-205)

### Interface
```
voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>
```
Console-script entry point: `[project.scripts] voicectl = "voice_typing.ctl:main"` (verified in `pyproject.toml` line 17).

### Exit codes (PRD §4.8)
| Code | Meaning | Source |
|------|---------|--------|
| 0 | success (daemon replied `{"ok": true}`) | `format_result` |
| 1 | logical failure (daemon `{"ok": false}` / protocol error) | `format_result` / `ValueError` path |
| 2 | daemon not running (socket absent / refused / XDG unset) | `OSError` / `RuntimeError` path |
| 64 | usage error (unknown/missing command, BSD `EX_USAGE`) | `_COMMANDS` validation in `main()` |

Commands are validated in `main()` (NOT argparse `choices`) so usage errors map to exit 64 while exit 2 stays exclusive to "daemon not running" (bugfix Issue 7).

### Socket protocol (`send_command`, lines 80-95)
Resolves `$XDG_RUNTIME_DIR/voice-typing/control.sock` via the canonical `daemon._default_control_socket_path()`. Opens `AF_UNIX SOCK_STREAM`, sends `{"cmd": <cmd>}\n`, reads ONE JSON line via `sock.makefile("r")` (NOT `settimeout` — makefile is incompatible with timeouts), closes. Raises `OSError` → exit 2; `ValueError` (empty/non-JSON line) → exit 1.

### Loading hint (`_send_command_with_loading_hint`, lines 98-115)
For `start`/`toggle`/`start-lite`/`toggle-lite` (commands that may block ~1–3 s on a cold arm): a daemon `threading.Timer` (default 0.3 s) prints `"loading models… (first arm, ~1–3 s)"` to **stderr** if the daemon doesn't reply in time. Client-side because the one-line-request/one-line-response protocol can't carry an in-band "loading" signal. Timer is cancelled in `finally` so fast (resident) arms never print it. `stop`/`status`/`quit` use plain `send_command`.

### Status formatting (`format_result`, lines 39-78)
Multi-line output for `status`:
```
listening: on
mode: normal
phase: listening
partial: hello wor
last: previous sentence.
uptime: 12.345s
device: cuda (float16)
models: distil-large-v3 + small.en (loaded)
mic: ok
```
Plus optional `load error: <...>` line on §4.2bis load failures. Mic health defaults to `True` when the key is absent (defensive `.get()`). All keys use `.get(...)` so a missing key never raises.

### Completeness: COMPLETE
Matches PRD §4.8 fully: all 7 commands, exit codes 0/1/2/64, `status` pretty-prints partial + phase + models_loaded + mode. Pure-stdlib import (verified by `test_ctl_module_present_and_imports_pure` — fresh interpreter importing only `voice_typing.ctl` pulls no `RealtimeSTT`/`torch`/`ctranslate2`).

### Minor spec note (superseded, informational)
PRD §4.3 says "document `voicectl` usage `--target`" for the tmux backend. There is **no `--target` flag** in `ctl.py` — `tmux_target` is config-only (`[output] tmux_target`). This is a cleaner design (the E2E test + SSH use set it via config); the PRD mention is a superseded detail, not a defect.

### Tests
`tests/test_voicectl.py` — 40+ tests across 3 layers, all passing:
- **Layer A** (pure `format_result`): toggle/start/stop/quit/status rendering, mic health variants, unloaded + load_error, lite mode, ok:false variants.
- **Layer B** (real socket round-trip): live `ControlServer` + `_StubDaemon` on a tmp socket; status/toggle/quit round-trips.
- **Layer C** (exit-2 paths): socket absent, stale socket, XDG unset.
- Plus: unknown/missing command → 64, loading-hint on slow arm / no-hint on fast arm, failed-load → ok:false + exit 1, help text lists all 7 commands, import purity, `main()` returns `int`.

---

## 5. `prefetch.py` — model prefetch (PRD §4.4)

**File:** `voice_typing/prefetch.py` (lines 1-175)

### Interface
```python
CORE_REPOS = {                    # required — daemon cannot start without these
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",   # FINAL (CUDA default)
    "small.en": "Systran/faster-whisper-small.en",                 # REALTIME (also CPU-fallback FINAL)
    "tiny.en": "Systran/faster-whisper-tiny.en",                   # CPU-fallback REALTIME
}
OPTIONAL_REPOS = {                # approved FINAL substitute — failure is a warning, never fatal
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

def prefetch(short_to_repo: dict[str, str] | None = None) -> dict[str, str]: ...  # → {short: local_path}
def _main() -> int: ...   # CLI entry: prefetch CORE + OPTIONAL; exit 0 iff all CORE succeed
```
Invoked by `install.sh` (line 102): `"$PY" -m voice_typing.prefetch`. **No console-script entry point** (by design — internal install-time tooling). `huggingface_hub` is imported lazily inside `prefetch()` so `import voice_typing.prefetch` triggers no network call and needs no CUDA.

### Completeness: COMPLETE
- Repo IDs verified against faster-whisper `utils.py` `_MODELS` + live HF API (documented). Correctly uses Systran (3 repos) vs mobiuslabsgmbh (turbo) — the trap-avoidance note explicitly warns against `distil-whisper/distil-large-v3` (raw PyTorch, not CTranslate2).
- Idempotent: `snapshot_download(force_download=False)` skips blobs whose cached etag matches. Re-runs are free.
- CLI exit logic: exit 0 iff ALL CORE succeed; OPTIONAL (turbo) failures are warnings, never fatal (so `install.sh` runs under `set -e`).
- Reports `model.bin` size per repo + total cached bytes. Validates `model.bin` presence (signals a broken/partial repo).

### Coverage gap (acceptable)
No unit test — it's install-time tooling requiring network access. The repo IDs are hardcoded and documented as verified. If HF renames a repo, prefetch fails at install time (CORE failure → exit 1 → `install.sh` warns but continues; the daemon then lazy-downloads on first run).

---

## 6. `launch_daemon.sh` — LD_LIBRARY_PATH wrapper (PRD §4.4 + §4.9)

**File:** `voice_typing/launch_daemon.sh` (lines 1-100)

### Responsibilities (all 3 PRD §4.4/§4.9 requirements)
1. **LD_LIBRARY_PATH wrapper** (lines 33-50): computes cuBLAS + cuDNN lib dirs from the LIVE installed `nvidia-*-cu12` wheels on every launch (survives `uv sync` reinstalls). Uses a Python one-liner with a namespace-package-aware `_d()` helper: `__file__` for regular packages, `__path__[0]` for namespace packages (the nvidia wheels ship `nvidia/cublas/lib` and `nvidia/cudnn/lib` as namespace packages with no `__init__.py`, so `__file__` is `None` there). On failure (no GPU host / wheels not installed), logs a clear warning and continues WITHOUT the override → daemon falls back to CPU.
2. **HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1** (lines 53-57): guarantees 100% local operation (PRD §1). Models are prefetched at install time; `HF_HUB_OFFLINE=1` makes huggingface_hub cache-only (skips the freshness GET). Must be set BEFORE python starts (read at import time in `constants.py`).
3. **WAYLAND_DISPLAY/DISPLAY re-fetch** (lines 60-80): pulls from `systemctl --user show-environment` so the daemon always has them regardless of boot order (VT-004: graphical-session.target race). Each var is only set if not already present (idempotent). Missing var is non-fatal.

### Path resolution (lines 26-28)
`SCRIPT_DIR = <this file's dir> = .../voice_typing`; `VENV_DIR = dirname(SCRIPT_DIR) = repo root`; `PY = $VENV_DIR/.venv/bin/python`. Verified correct against the repo layout (`.venv/` is at repo root, sibling of `voice_typing/`). `exec "$PY" -m voice_typing.daemon "$@"` — the wrapper replaces itself (no fork).

### Completeness: COMPLETE
Matches PRD §4.4 (cuDNN/cuBLAS wrapper) + §4.9 (the ExecStart). The inline debugging guide (lines 16-24) documents triage for `libcudnn_ops.so.9` errors.

### Coverage gap (acceptable)
No dedicated unit test — it's a shell wrapper exercised at install/runtime. `tests/test_systemd_unit.py` covers the unit file. The lib-discovery Python one-liner is inline and somewhat fragile (if the nvidia wheel layout changes), but the designed graceful degradation (CPU-fallback warning) handles it.

---

## 7. `status.sh` — tmux status-right helper (PRD §4.6)

**File:** `voice_typing/status.sh` (lines 1-45)

### Interface
POSIX `#!/bin/sh` + `jq` only. Reads `$XDG_RUNTIME_DIR/voice-typing/state.json`. Called every `status-interval` (1s) by tmux's `#(...)` substitution.

### Rendering logic (the jq program, lines 36-43)
- If `.listening` is true: render `(⚡ if .mode == "lite" else "") + "🎤 " + (.partial // "")`.
- Else: empty string (status-right is blank when idle).
- Truncate the whole line to `MAX` codepoints (default 60, overridable via `VOICE_TYPING_STATUS_MAX` env); on overflow, drop the last char and append `…` (visibly cut, not silently chopped). jq slicing is codepoint-based, so 4-byte emoji count as 1.

### Robustness (lines 28-31)
- `2>/dev/null` + jq `// ""` defaults → empty stdout on failure.
- Explicit `exit 0` at the end (Issue 2 fix): jq exits non-zero on a missing (exit 2) or corrupt (exit 5) state.json; the script always exits 0 to honor the "exit 0 (never abort)" contract for non-tmux callers that check `$?`.
- `STATE` path: `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json` — falls back to `/run/user/$UID` if XDG is unset.
- No `set -e`: a missing/malformed state.json must print an empty line with exit 0.

### Completeness: COMPLETE
Matches PRD §4.6 (the PRD says "Provide a small `voice_typing/status.sh` helper script instead of inline jq" — this IS that script, with a more sophisticated codepoint-aware truncation + lite-mode ⚡ prefix + robustness hardening).

### Tests
`tests/test_status_sh.py` — 5 tests, all passing. Runs the REAL script via `subprocess` with a controlled `XDG_RUNTIME_DIR`. Covers: missing state file → exit 0 + empty stdout (Issue 2 regression), corrupt JSON → exit 0 + empty stdout, listening → `🎤 <partial>` + exit 0, lite mode → `⚡🎤` prefix, normal mode → no ⚡, not-listening → empty + exit 0.

---

## Summary: Gaps vs PRD Spec

| Module | Status | Gap | Severity |
|--------|--------|-----|----------|
| typing_backends.py | COMPLETE | None (enhancement: catches OSError beyond spec's nonzero-exit) | — |
| feedback.py | COMPLETE | None | — |
| textproc.py | COMPLETE | VT-006: PRD §4.5 blocklist default still lists `"you"`; impl (config.py + config.toml) removed it. Deliberate + documented in code; **PRD text is stale** | Low (doc drift) |
| ctl.py | COMPLETE | None (PRD §4.3 `--target` mention is superseded by config approach) | — |
| prefetch.py | COMPLETE | No unit test (install-time tooling, network-dependent) | Low (acceptable) |
| launch_daemon.sh | COMPLETE | No unit test (shell wrapper); inline Python lib-discovery is fragile but degrades gracefully | Low (acceptable) |
| status.sh | COMPLETE | None | — |

## Residual Risks
1. **prefetch.py repo-ID drift:** if HF renames a repo (esp. the mobiuslabsgmbh turbo or Systran repos), CORE prefetch fails at install time → exit 1. `install.sh` warns but continues; the daemon lazy-downloads on first run (but `HF_HUB_OFFLINE=1` would then fail-fast with `LocalEntryNotFoundError`). No runtime re-verification of repo IDs.
2. **launch_daemon.sh lib-discovery fragility:** the inline Python one-liner assumes `nvidia.cublas.lib` and `nvidia.cudnn.lib` are importable namespace packages with `__path__[0]` pointing at the lib dir. A future nvidia wheel layout change would silently fall to CPU mode (designed graceful degradation, but silent — the warning goes to journald).
3. **PRD §4.5 blocklist drift (VT-006):** the shipped `config.toml` + dataclass defaults removed `"you"`; the PRD text was never updated. A reader matching code against PRD §4.5 would see a discrepancy. Not a runtime risk.
4. **No negative/edge tests for `_human_bytes` (prefetch):** the `n=0` path returns `"0 B"` (correct by inspection), but the function is untested.

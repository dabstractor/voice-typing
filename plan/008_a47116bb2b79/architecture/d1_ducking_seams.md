# D1 — media-ducking seams at HEAD 2335a9e (read-only research)

Repo `/home/dustin/projects/voice-typing`, branch main, HEAD 2335a9e. Companion: `plan/007_cfc245548aec/architecture/{substrate_map,daemon_control_map}.md` (Rev-2-era, HEAD 6b61db1 — drift noted in §7). All citations `file:line` at HEAD unless marked "cmd".

## 1. `voice_typing/daemon.py` (2997 lines)

### (a) Arm paths — ALL funnel into `_arm()` (daemon.py:1360), called under `self._lock`

| Entry | Path | Toast that fires |
|---|---|---|
| `voicectl start` / socket `"start"` | `ControlServer._dispatch` daemon.py:2683-2686 → `start()` daemon.py:2116: `_load_host()` OUTSIDE `_lock` (2119-2122), then `with self._lock: self._arm()` (2123-2125) | cold load: `'Loading…'` via `feedback.notify` in `_load_host` (daemon.py:871-873, constant `_COLD_LOAD_NOTIFY_LOADING` daemon.py:129); arm: `'Recording'` via `self._feedback.set_listening(True)` **daemon.py:1415** (feedback.py:173→189-191) |
| `voicectl toggle` (idle) / socket `"toggle"`/`"toggle-lite"` | `_dispatch` daemon.py:2672-2682 → `toggle()` daemon.py:2132: read listening under `_lock` (2145-2146); armed→`_request_stop()` (2147); idle→`_load_host()` (2149) + `_arm()` under `_lock` (2150-2152) | same as start |
| Lite variants | **GONE at HEAD** (Rev-2 single-mode). `"toggle-lite"` is only a deprecated alias→`toggle()` (daemon.py:2673-2677); `"start-lite"` = unknown command (daemon.py:2706) | — |

Arm choke point: **one** — `_arm()` at daemon.py:1360; the arm toast site is `self._feedback.set_listening(True)` at **daemon.py:1415**.

### (a′) Disarm paths — all fire `'Recording Stopped'` via `set_listening(False)`

All except quit funnel into `_disarm()` (daemon.py:1420), whose toast line is `self._feedback.set_listening(False)` at **daemon.py:1454** (feedback.py:173→191).

| PRD disarm path | Code path | Thread |
|---|---|---|
| manual stop / toggle-off (immediate, default `graceful_stop=false`) | `stop()` daemon.py:2127 / `toggle()` 2147 → `_request_stop()` 1519 → `with self._lock: self._disarm()` 1548-1549 + `_safe_abort()` OUTSIDE `_lock` 1550-1551 | control-socket worker thread |
| manual stop / toggle-off (graceful) | `_request_stop` → `_begin_drain()` 1545 (Timer `_DRAIN_TIMEOUT_S`=5.0, daemon.py:146) → run loop completes: **daemon.py:1019-1024** `if self._drain: self._complete_drain()` → `_disarm()` 1817-1818 under `_lock` | main thread (run loop) |
| idle auto-stop | `_idle_watchdog` daemon.py:1882 (thread `"voice-typing-idle"` started in `run()` 989-991) → `_maybe_auto_stop()` 1852 → `_disarm()` 1871-1872 under `_lock` + `_safe_abort()` 1880-1881 | watchdog thread |
| Rev-3 HALT keypress disarm (`keypress_action="disarm"` default, config.py:181-206) | `_on_user_keypress` 1637 → `note_user_keypress()` **1581**: 1.5 s post-arm grace 1592-1593, `with self._lock: if listening: self._disarm()` 1598-1601 + `_safe_abort()` 1602-1603; WARNING log 1596-1597 | KeyListener evdev reader thread (no daemon locks held on entry) |
| daemon quit (`voicectl quit`) | `_dispatch "quit"` daemon.py:2697-2705 → `request_shutdown()` **2154** + `on_quit=daemon.shutdown()` (wired in `main()`, daemon.py:2966; doc 2165-2166) | control-socket worker thread |
| SIGTERM (systemctl stop) | handler daemon.py:2738-2742 spawns `"voice-typing-signal-shutdown"` thread → `request_shutdown()`; `main()` finally also calls `daemon.shutdown()` **2388** (daemon.py:2968-2972) | signal-spawned daemon thread; main-thread finally |
| drain completion | `_complete_drain()` **1809** → `_disarm()` 1817-1818 (called from run loop at 1023) | main thread |
| dead-host handler | run-loop liveness check 1007-1012 → `_handle_dead_host()` **1050**: clears `_listening` (1090), `set_phase("unloaded")` (1091), `set_listening(False)` (1093). Does NOT call `_disarm()` — no `_disarmed_monotonic` stamp, no host mic-off. NOT in the PRD release list; noted as edge (see §1-b note) | main thread |

`request_shutdown()` (2154) sets `_shutdown` at 2177, runs `_safe_abort()` + `_bounded_shutdown()` OUTSIDE `_lock` (2203-2213). It does NOT call `_disarm()` — quit-path release needs its own hook.

### (b) Backspace-cancel path — must NOT release

`_on_cancel_backspace()` **daemon.py:1621-1631** (KeyListener thread) → `cancel()` **daemon.py:1754**: `with self._lock:` (1775); when not armed → idempotent no-op (1776-1778); when armed: `press_backspace(n)` (1782), latches `_cancel_suppress_final` 1786-1788, `host_cancel()` 1789, `_reset_stream_after_cancel()` 1791; **never clears `_listening`, never calls `_disarm()`**; returns `{"ok": True, "listening": True, ...}` (1794). Distinguishing signal: `_listening` stays set. So "release on `_disarm`" naturally excludes cancel; anything hooked into `cancel()` itself must be avoided.

### (c) Best choke points for engage/release

- **Engage — single choke point: `_arm()` at the toast site, daemon.py:1415** (covers start, toggle, every arm). `_arm()` runs UNDER `self._lock` (callers: start 2124-2125, toggle 2150-2152), so engage must be a fire-and-forget spawn (`threading.Thread(target=..., daemon=True).start()`) — same shape as the signal handler's spawn (2738-2742) — to satisfy "concurrent, never blocks arm".
- **Release — two choke points** (idempotent release makes the overlap safe):
  1. `_disarm()` right after `self._feedback.set_listening(False)` at daemon.py:1454 — covers manual stop/toggle-off (both immediate + drain), idle auto-stop, HALT keypress. All callers hold `_lock` here → spawn, never call inline.
  2. `request_shutdown()` after `self._shutdown.set()` (daemon.py:2177) — covers `voicectl quit` AND SIGTERM (both funnel here; `main()` finally's `shutdown()` is downstream of the same teardown, guarded idempotent). Outside `_lock` (2178-2213) but still spawn for the ≤1 s bound uniformity.
  - Gated on "we engaged": idempotent engage/release + a `ducked` latch (see §2) naturally no-op when `duck_mode="off"` or never engaged (mirrors `cancel()`'s armed-gate at 1776-1778).
  - Edge NOT in the PRD list: `_handle_dead_host` (1050) fires the stop toast (1093) without `_disarm()` — if release lives only in `_disarm()`, a child crash while ducked leaves media ducked until daemon quit. Flag to implementer/PRD owner.

### (d) Thread + lock of each site

`self._lock` = `threading.Lock` (daemon.py:627, `__init__`); `_load_cond = threading.Condition(self._lock)` (daemon.py:747). Lock discipline precedent: `abort()` was moved OUT of `_lock` because a blocking call under it wedges every control command (validation NEW-2; `_disarm` docstring daemon.py:1422-1436, `_safe_abort` docstring 2086-2114 "Never re-raises"). **Engage/release must therefore never run under `_lock`** — spawn a short-lived daemon thread at the call sites (the ≤1 s subprocess bound then cannot touch the control path). Threads at each site: arm = control-socket worker (per-connection thread spawned daemon.py:2604); drain-complete = main thread; idle auto-stop = `"voice-typing-idle"` watchdog (989-991); HALT = KeyListener reader thread; quit = socket worker; SIGTERM = `"voice-typing-signal-shutdown"` thread (2741). `Feedback` methods are lock-free and safe from any thread (feedback.py:44-52).

### (e) Subprocess-with-timeout helper patterns to copy

- **No existing `subprocess.run(..., timeout=...)` anywhere in `voice_typing/`** (grep `timeout=` → 0 hits on run calls). The ≤1 s hard timeout is a NEW pattern.
- Copy the swallow-discipline from `feedback.py:247-261 _notify`: `subprocess.run([...], check=False, stdout=DEVNULL, stderr=DEVNULL)` inside `try/except (OSError, subprocess.SubprocessError)` → `logger.debug`, never re-raise. Add `timeout=1.0` and let `subprocess.TimeoutExpired` (a `SubprocessError`) land in the same except → journal ONE line (WARNING per PRD).
- Serialization precedent: `typing_backends.py:62-69 _InjectorRateLimiter` ("subprocess.run serialized + floored"). Bounded-thread+Event precedent: `_LegacyRecorderHostAdapter.stop` daemon.py:540-569.
- New module home: nothing in `voice_typing/` imports `subprocess` except feedback.py:66 and typing_backends.py:47 — a new `voice_typing/audio_ducking.py` keeps the third import local.

## 2. `voice_typing/feedback.py` (264 lines) — `ducked` recipe

- Live schema = `self._state` dict, feedback.py:95-109: `listening, phase, models_loaded, mode, partial, last_final, ts` (documented module docstring 9-12). In-memory dict mirrors on-disk JSON EXACTLY (contract, 91-93).
- Setters are plain always-write methods; the exact template for a bool is **`set_models_loaded` feedback.py:135-145** (`self._state[...] = bool(...); self._write()`; never notifies — anti-spam rule 26-37). Also `set_mode` 147-153, `set_phase` 124-133.
- **Recipe**: (1) add `"ducked": False,` to `_state` (feedback.py:95-109, keep key order near `mode`); (2) add `def set_ducked(self, ducked: bool) -> None` cloning `set_models_loaded` (135-145) with a "never notifies" doc; (3) no throttle needed — `_PARTIAL_WRITE_MIN_INTERVAL` (75-76) only gates `update_partial` (111-122); setters always write; (4) atomic write already handled by `_write()` feedback.py:220-245 (mkstemp 0600 in target dir + `os.replace`, temp cleaned on failure); (5) `snapshot()` feedback.py:195-203 returns `dict(self._state)` → status/`voicectl` see `ducked` free; (6) update the schema docstring lines 9-12. Post-crash self-heal: `ducked: true` persisted in state.json at crash time is the signal `ExecStopPost` / next boot checks.
- Optional surface: `daemon.status_snapshot()` (daemon.py:2275-2316) reads `snap.get(...)` per key — add `"ducked": snap.get("ducked", False)` there if `voicectl status` should show it.

## 3. `voice_typing/config.py` (447) + `config.toml` (84) — `[audio]` lockstep recipe

- Pattern: per-section `@dataclass` + `__post_init__` fail-fast guards. AsrConfig 49-139 (`graceful_stop` at 79), OutputConfig 140-168, CancelConfig **170-215**, FeedbackConfig 218-265, FilterConfig 267-319, LogConfig 321-339.
- `duck_mode` guard template = `keypress_action` (config.py:201-206): `if self.duck_mode not in ("off","mpris","volume"): raise ValueError(f"[audio] duck_mode expects ...")`. `duck_volume_pct` guard template = notify_ms non-bool-int guard in FeedbackConfig `__post_init__` (config.py:~236-244) / min_chars (FilterConfig).
- Exact wire-in (5 code points):
  1. new `@dataclass class AudioConfig:` after CancelConfig (~config.py:216);
  2. field on `VoiceTypingConfig` (config.py:341-346): `audio: AudioConfig = field(default_factory=AudioConfig)`;
  3. `_KNOWN_TABLES = frozenset({"asr","output","cancel","feedback","filter","log"})` **config.py:337** → add `"audio"` (else `[audio]` in config.toml raises "unknown config table(s)", config.py:367-375);
  4. `from_toml` (config.py:354-392): add `audio=_overlay(AudioConfig, "audio"),` to the `cls(...)` call (config.py:385-391);
  5. `config.toml`: new `[audio]` table, two keys, comment style = inline `# ...` on every key (config.toml:31-47 pattern); header comment states "Unknown keys AND unknown tables are REJECTED" (config.toml:15-16) and "Keep the two in lockstep" (config.toml:18-19).
- **Key-set pinning — VERIFIED at HEAD**: lives ONLY in `tests/test_config_repo_default.py` (grep `expected = {` in tests/test_config.py → 0 hits). `test_repo_config_toml_has_no_extra_keys` builds `expected` at **tests/test_config_repo_default.py:37-63**; docstring says "only the 24 schema keys" (line 38). Current set: asr 11 + output 3 + cancel 3 + feedback 4 + filter 2 + log 1 = **24 — PRD's count confirmed**. After `[audio]`: add `"audio": {"duck_mode", "duck_volume_pct"}` → **26**; update the docstring count. `test_repo_config_toml_equals_defaults` (test_config_repo_default.py:16-26) then pins the new defaults automatically. Type/value-guard tests for the new keys belong in tests/test_config.py next to the device/backend guards (tests/test_config.py:143-201 region, per HEAD grep; no key-set pin there).

## 4. `systemd/voice-typing.service` (86 lines) + `tests/test_systemd_unit.py` (377)

- Unit directives: `ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY` (line 26); `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (50, `__REPO__` placeholder substituted by install.sh — comment 46-49); `Restart=on-failure` (51); `RestartSec=2` (52); `KillMode=mixed` (78); `TimeoutStopSec=15` (79). **`ExecStopPost` NOT present** (grep over the file → no match).
- test_systemd_unit.py asserts (helper `_unit_lines()` at :45): ExecStart→wrapper (71-75), ExecStartPre imports both vars (78-88), `Restart=on-failure` exact line (94-96), `TimeoutStopSec=15` exact line (99-109), launch_daemon.sh offline env (115-161), `__REPO__` placeholder (273-280+). Adding `ExecStopPost` needs a lockstep test mirroring 94-96, e.g. `assert any(ln.startswith("ExecStopPost=") for ln in _unit_lines())`. If ExecStopPost invokes a repo script (e.g. a `voicectl`/python one-liner restoring volume via wpctl), use the same `__REPO__` placeholder + verify install.sh's sed covers it (install.sh currently seds `__REPO__` in ExecStart only — check before relying on it).

## 5. Test seams for a mocked AudioDucker (CUDA-free)

Daemon ctor injection seams (daemon.py:571-586): `recorder=`, `recorder_host=`, `host_factory=`, `backend=`, `latency=`, `mic_prober=`, `key_listener=` (constructed at 802-812 only when `cfg.cancel.on_backspace`). An `AudioDucker` follows the `key_listener=` precedent: `ducker=None` kwarg, default built from `cfg.audio` when `duck_mode != "off"`.
Existing fakes at HEAD (tests/test_daemon.py): `_FakeFeedback` 33, `_DaemonFakeFeedback` 470 (records finals/listening), `_StubRecorder` 490, **`_FakeBackend` 517** (records `typed`, `raise_on=`), **`_ok_probe` 535** (`(True, None)` — the PyAudio guard), `_FakeHost` 561 (mirrors RecorderHost ctor), `_fake_host_factory` 665, **`_make_daemon` 682-700** (injects `backend=` + `mic_prober=_ok_probe` at 696), `_make_daemon_with_feedback` 1932 (real Feedback + tmp state file), `_make_lazy_daemon` 3306.
**Recommendation**: new `tests/test_ducking.py` — pure fakes, never imports RealtimeSTT/feedback.py internals beyond what `_make_daemon_with_feedback` shows; a `_FakeDucker` (records `engage`/`release` calls, optional `raise_on`/delay) injected via the new `ducker=` kwarg through a copy of `_make_daemon` (682-700). Six PRD tests: engage-on-arm (via `start()`), release-on-stop/toggle-off, release-on-idle-auto-stop (`_maybe_auto_stop` direct call — precedent: "also safe to call directly (unit tests do)", daemon.py:1857-1858), release-on-HALT (`note_user_keypress`), release-on-quit (`request_shutdown`), NO-release-on-Backspace-cancel (`cancel()`); + idempotence + `_lock`-freedom (fake ducker asserting it runs off the calling thread / never blocks).

## 6. Environment facts (each under `timeout 10`; run 2026-dustin host "ghost")

| Check | Result |
|---|---|
| `playerctl --version` | **v2.4.1**, rc 0 — present |
| `wpctl --version` | **unsupported flag** — prints usage, rc 1. wpctl IS installed/live: `wpctl status` works; `wireplumber --version` → libwireplumber **0.5.19**; session shows **PipeWire 1.6.9** + WirePlumber client. Volume ops confirmed in usage: `get-volume ID`, `set-volume ID VOL[%][-/+]`, `set-mute ID 1/0`, `set-default ID` |
| `pactl --version` | **17.0-134-g77d25** (libpulse 17.0.0), rc 0 |
| `.venv/bin/python -c 'import dbus'` | **ModuleNotFoundError**, rc 1 — NO python-dbus in venv |
| `.venv/bin/python -c 'import gi'` | **ModuleNotFoundError**, rc 1 — NO PyGObject in venv |
| `command -v busctl gdbus` | `/usr/bin/busctl`, `/usr/bin/gdbus`, rc 0 |

Implication: tier-1 MPRIS must be `playerctl` CLI via `subprocess` (no D-Bus bindings in the venv; adding python-dbus/gi would be a new dependency — flag if PRD assumed them). Tier-2 sink-volume = `wpctl` CLI (`@DEFAULT_AUDIO_SINK@` is wpctl's default-sink token per its usage).

## 7. plan/007 maps — drift at HEAD

`daemon_control_map.md` (HEAD 6b61db1, daemon.py 2300L) describes the two-mode substrate — **all mode machinery is GONE at HEAD 2335a9e** (daemon.py 2997L):
- `self._mode`, `start_lite`/`toggle_lite` methods, `_load_host(mode)` + reload branch, `cfg_to_kwargs(lite=)` — none exist. Now: `cfg_to_kwargs(cfg, *, resolved=None)` (176-215), `_load_host()` single-path (827), `toggle()` single-path (2132).
- Control cmds now: `toggle`(+deprecated `toggle-lite` alias 2673-2677), `start`, `stop`, **`cancel`** (2691-2695 — NEW since 007), `status`, `quit` (2697-2705).
- `status_snapshot()` now returns `listening, mode("lite" const), phase, models_loaded, load_error, partial, last_final, uptime_s, device, compute_type, model, mic_ok, mic_error, context_prompt` (daemon.py:2275-2316) — `final_model`/`realtime_model` keys gone.
- feedback state.json now includes `"mode": "lite"` (feedback.py:98-101; set in `_arm` daemon.py:1413).
- 007's §5 seam lines for feedback.py are stale by ~30 lines (setters now at 111-245, see §2 above).
`substrate_map.md` config section (348L file) is superseded: config.py now 447L with `[cancel]`, `graceful_stop`, `context_prompt`, `output.streaming`, `keypress_action`; key count 20→**24** (§3). Still accurate: cuda_check shape, typing_backends argv pins, prefetch, packaging (`requires-python >=3.12,<3.13`).

## Implementer checklist (dependency order)

1. `voice_typing/config.py` — `AudioConfig` dataclass (after CancelConfig ~216): `duck_mode: str = "off"` + guard copying config.py:201-206 (`("off","mpris","volume")`), `duck_volume_pct: int = 15` + non-bool-int guard; field on `VoiceTypingConfig` (341-346); `"audio"` in `_KNOWN_TABLES` (337); `audio=_overlay(AudioConfig, "audio")` in `from_toml` (385-391).
2. `config.toml` — `[audio]` table (after `[cancel]`, ~line 55): `duck_mode = "off"  # ...` + `duck_volume_pct = 15  # ...`, every key commented.
3. `tests/test_config_repo_default.py` — `expected["audio"] = {"duck_mode","duck_volume_pct"}` (37-63) + docstring 24→26 (line 38). Run: `timeout 600 .venv/bin/pytest tests/test_config_repo_default.py tests/test_config.py -q`.
4. `voice_typing/feedback.py` — `"ducked": False` in `_state` (95-109) + `set_ducked()` cloning `set_models_loaded` (135-145) + docstring schema (9-12).
5. NEW `voice_typing/audio_ducking.py` — `AudioDucker(engage/release)` over an injectable backend; `PlayerctlMprisBackend` / `WpctlVolumeBackend`; every `subprocess.run(..., check=False, timeout=≤1.0, DEVNULL)` in `try/except (OSError, subprocess.SubprocessError)` → ONE journal line (copy feedback.py:247-261 + add timeout); idempotent engage/release with the paused-players/volume restore bookkeeping the PRD pins.
6. `voice_typing/daemon.py` — `ducker=` ctor seam (mirror `key_listener=` 574-576/802-812, default from `cfg.audio`); engage spawn at `_arm()` toast site **1415**; release spawn in `_disarm()` after **1454** and in `request_shutdown()` after **2177**; wire `feedback.set_ducked` from the ducker thread; decide the `_handle_dead_host` (1050) edge.
7. `systemd/voice-typing.service` + `tests/test_systemd_unit.py` — add `ExecStopPost=` (crash-safe volume restore; `__REPO__` handling per §4) + lockstep assertion mirroring 94-96.
8. NEW `tests/test_ducking.py` — six mocked-backend tests per §5 (`_FakeDucker` + `_make_daemon` copy at tests/test_daemon.py:682-700).

# Substrate Map — Rev 2 delta grounding (config schema, typing backends, textproc, binds, install, packaging, tests)

All paths relative to /home/dustin/projects/voice-typing. Read-only scout; no repo files modified.

## 1. voice_typing/config.py (348 lines) — full schema

Top-level `VoiceTypingConfig` (config.py:230) aggregates five sub-configs, each `field(default_factory=…)`:
- `asr: AsrConfig`, `output: OutputConfig`, `feedback: FeedbackConfig`, `filter: FilterConfig`, `log: LogConfig` (config.py:233-237).

### AsrConfig (config.py:48-116)
| field | default | line |
|---|---|---|
| final_model | "distil-large-v3" | 52 |
| realtime_model | "small.en" | 53 |
| lite_model | "small.en" | 54 |
| language | "en" | 57 |
| device | "cuda" | 58 |
| post_speech_silence_duration | 0.6 | 59 |
| lite_post_speech_silence_duration | 0.5 | 61 |
| realtime_processing_pause | 0.15 | 66 |
| auto_stop_idle_seconds | 30.0 | 67 |
| auto_unload_idle_seconds | 1800.0 | 70 |

`__post_init__` (config.py:76-114):
- **Bool-for-numeric rejection (EXACT, config.py:86-95):**
```python
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
```
- String fields guard (config.py:96-102): `for _name in ("final_model", "realtime_model", "lite_model", "language", "device")` — `raise TypeError(f"[asr] {_name} expects str, ...")`.
- device VALUE validation (config.py:103-114): `if self.device not in ("cuda", "cpu"): raise ValueError('[asr] device must be "cuda" or "cpu", got ...')` — TypeError for wrong type, ValueError for wrong value (the pattern to copy for new fields).

### OutputConfig (config.py:118-140)
- `backend: str = "wtype"` (124), `append_space: bool = True` (125).
- `__post_init__` (129-140): `if self.backend not in ("wtype", "ydotool", "null"): raise ValueError(...)`.

### FeedbackConfig (config.py:142-197)
- `state_file: str = ""` (147), `hypr_notify: bool = True` (148), `notify_ms: int = 2500` (149), `notify_on_final: bool = True` (150).
- `__post_init__` (159-171): notify_ms must be non-bool int → TypeError.
- `resolved_state_file()` (173-197): empty → `$XDG_RUNTIME_DIR/voice-typing/state.json`; RuntimeError if XDG_RUNTIME_DIR unset.

### FilterConfig (config.py:199-248)
- `min_chars: int = 2` (203), `blocklist: list[str] = field(default_factory=lambda: ["thank you.", "thanks for watching.", "bye.", "thank you for watching"])` (206-211).
- `__post_init__` (219-248): min_chars non-bool int; each blocklist[i] must be str → TypeError.

### LogConfig (config.py:250-260)
- `level: str = "INFO"` (259). No `__post_init__` validation.

### Unknown-key rejection (EXACT — this is the merge mechanism, config.py:249-271)
```python
    @classmethod
    def from_toml(cls, data: Mapping[str, Any]) -> VoiceTypingConfig:
        """...Each table ([asr]/[output]/[feedback]/[filter]) overlays its dataclass
        defaults — only present keys override; missing tables/keys keep defaults.
        Unknown keys raise TypeError (dataclass __init__ rejects them)..."""

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
```
Unknown keys fail via `section_cls(**section)` → dataclass `__init__` TypeError. **Implication for Rev 2: adding `asr.context_prompt`, `output.streaming`, `[cancel]` table requires (a) new dataclass/fields, (b) a `_overlay(CancelConfig, "cancel")` line in from_toml, (c) config.toml keys, (d) test_config_repo_default.py expected-key set (tests/test_config_repo_default.py:27-46) — removing final_model/realtime_model also touches that set (lines 35-36) plus test_config.py parity tests (lines 43-44, 75-76).

### Loaders
- `from_toml_file` (config.py:273-278): `open(path,"rb")` + `tomllib.load` → `from_toml`.
- `load(path=None)` (config.py:280-297): explicit path → that file; else search order XDG → repo → defaults.
- `_xdg_config_path()` (301-307), `_repo_config_path()` (309-319, `Path(__file__).parent.parent/"config.toml"`), `_candidate_paths()` (322-324), module-level `load()` (327-331).

## 2. config.toml — full current contents (line-numbered)

Lines 1-27: header comments (what this file is; search order; schema source; "Unknown keys are REJECTED at load time"; wrong-typed values rejected).
- L29 `[asr]` comment; L31 `final_model = "distil-large-v3"`; L32 `realtime_model = "small.en"`; L33 `lite_model = "small.en"`; L34 `language = "en"`; L35 `device = "cuda"`; L36 `post_speech_silence_duration = 0.6`; L37 `lite_post_speech_silence_duration = 0.5`; L38 `realtime_processing_pause = 0.15`; L39 `auto_stop_idle_seconds = 30.0`; L40 `auto_unload_idle_seconds = 1800.0`.
- L43 `[output]`; L45 `backend = "wtype"`; L46 `append_space = true`.
- L49 `[feedback]`; L51 `state_file = ""`; L52 `hypr_notify = true`; L53 `notify_ms = 2500`; L54 `notify_on_final = true`.
- L57 `[filter]`; L59 `min_chars = 2`; L60-65 `blocklist = [ "thank you.", "thanks for watching.", "bye.", "thank you for watching", ]` + VT-006 note comment.
- L68 `[log]`; L72 `level = "INFO"` (L69-71 comments re INFO/DEBUG + journalctl).

Every key carries a user-facing comment — new keys must too. Comments are tested: tests/test_config_repo_default.py:53-72 asserts the `lite_model` line contains `SUPER+ALT+D`.

## 3. voice_typing/cuda_check.py (168 lines)

- `CUDA_DEFAULTS: dict[str,str]` (46-52): device=cuda, compute_type=float16, final_model=distil-large-v3, realtime_model=small.en.
- `CPU_FALLBACK: dict[str,str]` (54-59): device=cpu, compute_type=int8, final_model=small.en, realtime_model=tiny.en (the tiny.en CPU fallback logic; applied REGARDLESS of `defaults` when no CUDA).
- `resolve_device_and_models(defaults: Mapping[str,str] | None = None) -> dict[str,str]` (114-130): CUDA available → `dict(defaults or CUDA_DEFAULTS)`; else `dict(CPU_FALLBACK)`. Fresh dict each call.
- `is_cuda_available()` (100-104) ← `_cuda_device_count()` (62-82) (ctranslate2 import + `get_cuda_device_count()` both wrapped, any failure → 0). `_torch_cuda_available()` (91-96) is diagnostics-only.
- `_main()` (135-165): CLI VERDICT printer; exit 0=cuda-ok, 1=cpu-fallback-required.
- **Test file: none dedicated.** No `tests/test_cuda_check.py` exists; coverage lives in tests/test_daemon.py (e.g. lines 2747, 2813-2849 assert CPU_FALLBACK mapping) and tests/test_config.py:66-77 (`test_defaults_match_cuda_check` pins AsrConfig defaults == CUDA_DEFAULTS final/realtime — must change when those fields are removed).

## 4. voice_typing/prefetch.py (168 lines)

- Docstring (1-29): pre-downloads faster-whisper CT2 models into ~/.cache/huggingface/hub; internal install-time tooling; only documented caller is CLI `python -m voice_typing.prefetch`, re-invoked idempotently by install.sh; imports only huggingface_hub lazily.
- `CORE_REPOS` (36-40):
  - "distil-large-v3" → "Systran/faster-distil-whisper-large-v3"
  - "small.en" → "Systran/faster-whisper-small.en"
  - "tiny.en" → "Systran/faster-whisper-tiny.en"
- `OPTIONAL_REPOS` (43-47): "large-v3-turbo" → "mobiuslabsgmbh/faster-whisper-large-v3-turbo".
- `prefetch(short_to_repo) -> dict[str,str]` (50-77) uses `snapshot_download(repo_id=..., repo_type="model")`; `_main()` (101-148) core-fail → exit 1, optional fail → warning.
- **Invokers:** install.sh:100-104 (`"$PY" -m voice_typing.prefetch`, warn-only on failure). No daemon or test invocation found.

## 5. voice_typing/typing_backends.py (148 lines)

- `TypingBackend(ABC)` (45-60): single abstract `type_text(self, text: str) -> None` — raises on failure (CalledProcessError / OSError).
- `WtypeBackend.type_text` (63-72): `subprocess.run(["wtype", "--", text], check=True)` (argv: `wtype -- <text>`).
- `YdotoolBackend.type_text` (75-83): `subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text], check=True)` (argv: `ydotool type --key-delay 2 -- <text>`).
- `NullBackend` (86-89): logs debug, types nothing.
- `_WtypeWithFallback` (92-127): ctor injects primary/fallback (for tests); `type_text` catches `(subprocess.CalledProcessError, OSError)`, logs WARNING, retries ONCE via fallback; second failure propagates. TypeError NOT caught.
- `make_backend(cfg: OutputConfig) -> TypingBackend` (130-148): "wtype"→`_WtypeWithFallback()`, "ydotool"→`YdotoolBackend()`, "null"→`NullBackend()`, else ValueError.
- Call style: `subprocess.run(..., check=True)` everywhere — no Popen. Stateless per-call children; serialized by daemon `_on_final_lock`. A new `press_backspace(n)` primitive goes on the ABC + each backend + the fallback wrapper + make_backend contract; tests pin exact argv (tests/test_typing_backends.py:89, 122) and no-real-subprocess guard (line 274).

## 6. voice_typing/textproc.py (70 lines)

- `clean(text: str, cfg: FilterConfig) -> str | None` (26-69): (1) `" ".join(text.split())`; (2) `len(cleaned) < cfg.min_chars` → None; (3) key = `cleaned.lower().rstrip(_TRAILING_PUNCT)` (`_TRAILING_PUNCT = ".!?," + ";"`, line 19) vs same-normalized blocklist set, exact match → None; (4) return cleaned (never appends space). Pure, no I/O. Casing/period guards for Rev 2 slot in around steps 3-4.

### tests/test_textproc.py case list (21 tests)
Whitespace: collapses_internal_whitespace_runs, strips_leading_and_trailing, drops_trailing_newlines_and_collapses, tabs_are_whitespace_too. min_chars: rejects_below, accepts_at_boundary, rejects_empty, rejects_whitespace_only, min_length_uses_cleaned_not_raw, custom_min_chars. Blocklist: rejects_default_thank_you, case_insensitive, matches_with_or_without_trailing_punct, entry_without_punctuation_matches, exact_not_substring, empty_blocklist_never_rejects. Punctuation: internal_punctuation_preserved, question_mark_preserved, period_preserved_when_not_blocklisted. Contract: never_appends_trailing_space, returns_none_for_every_rejection_reason.

## 7. Packaging / environment

pyproject.toml:
- build-system hatchling (2-4). `[project]` (6-13): name voice-typing, version 0.1.0, requires-python ">=3.12,<3.13", dependencies = `["realtimestt[faster-whisper,silero-vad]", "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*", "huggingface_hub>=0.23"]` (9-13). **evdev must be added here + uv.lock regenerated.**
- scripts (15-17): voicectl=voice_typing.ctl:main, voice-typing-daemon=voice_typing.daemon:main.
- wheel packages=["voice_typing"] (20) — config.toml NOT packaged.
- dev group: pytest>=9.1.1 (24-26).
- **uv.lock exists** (yes). `.venv/bin/python --version` → **Python 3.12.10**.

## 8. hypr-binds.conf — every bind line verbatim

- Line 57: `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle`
- Line 59: `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite`
(Driven by $HOME/.local/bin/voicectl symlink VT-003, install.sh:174-191. Header docs lines 1-55.)

## 9. install.sh — printed usage/help lines mentioning voicectl

- 205: `echo "daemon : running and NOT listening (~0 VRAM; first 'voicectl toggle' loads models, ~1-3s). Run 'voicectl toggle' to arm the mic."`
- 209: `echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit|toggle-lite|start-lite"`
- 210: `echo "          (bind Ctrl+Alt+Super+D -> voicectl toggle;  Alt+Super+D -> voicectl toggle-lite; see the Hyprland note below)"`
- Also 19 (comment), 151 (readiness poll), 174-191 (launcher symlink install).

## 10. tests/ACCEPTANCE.md — row ids (criteria 1-10), one line each

1. T1-T4,T6 pass by actual output — PASS (424 LIVE-green; T4/T6 static via test_idle_and_gpu.sh).
2. ≥3s mid-dictation pause loses zero words, session continues — PASS (pause test live).
3. Live partials observable in state.json while audio plays — PASS.
4. Only finals reach target; nothing typed while off — PASS.
5. Daemon survives ≥2min silence, no hallucination, trivial CPU — PASS.
6. voicectl toggle/start/stop/status/quit work; systemd user service; un-armed boot; auto-restart — PASS.
7. Everything committed; README documents install/hotkey/config/troubleshooting/CPU-only — PASS-on-substance.
8. No network at runtime (models cached by install) — PASS.
9. Idle-unload → ~0 VRAM + bounded teardown + reload — PASS (subprocess recorder host).
10. Lite mode: toggle-lite single-model, shorter lite_post_speech_silence_duration (default 0.5), mode in status — PASS. (This row's `0.5` default text must be updated to 0.8.)

## 11. Safe probes (verbatim; failures recorded as data)

- `timeout 10 wtype --help` → `Missing argument to --help` (wtype installed, no help flag).
- `timeout 10 ydotool --help` → Usage: `ydotool <cmd> <args>`; commands: click, mousemove, type, key, debug, bakers; `YDOTOOL_SOCKET` env for daemon socket.
- `timeout 10 ydotool key --help` → `Usage: key [OPTION]... [KEYCODES]...`; `-d/--key-delay=N`; raw keycodes `<keycode>:<pressed>` e.g. `28:1 28:0` = Enter; see `/usr/include/linux/input-event-codes.h`. (Backspace = keycode 14.)
- `/dev/input/`: event0..event23+ root:input `crw-rw----` (user NOT in a per-device group but IS in group `input` — rw works).
- `id` → `uid=1000(dustin) gid=1000(dustin) groups=1000(dustin),...,994(input),998(wheel)` — **dustin is in `input` group** → evdev read access OK.
- `.venv/bin/python -c "import evdev"` → `ModuleNotFoundError: No module named 'evdev'` (evdev NOT installed — Rev 2 must add it).
- Grep final_model/realtime_model/toggle-lite/start-lite: hits in voice_typing/{config,ctl,cuda_check,daemon,prefetch,recorder_host}.py; tests/{test_config,test_config_repo_default,test_daemon,test_control_socket}.py. Key removal blast radius for final_model/realtime_model:
  - voice_typing/config.py:52-53,99 (fields + str-guard tuple)
  - voice_typing/cuda_check.py:46-57 (CUDA_DEFAULTS/CPU_FALLBACK keys), 4-6,20,25-26,117,125,147,162 (docstrings/prints)
  - voice_typing/daemon.py:144-197,306,970-975,1617-1682 (device dict plumbing, lite override at 191-192, status keys 1641-1642, log line)
  - voice_typing/recorder_host.py:23,164,681-714 (ready payload, re-derive)
  - voice_typing/ctl.py:55,75-76,96 (status display)
  - tests/test_config.py:43-44,75-76,109,258,262; tests/test_config_repo_default.py:35-36; tests/test_daemon.py:118-313,558,1652-1754,2747-2964+; tests/test_control_socket.py:35
  - hypr-binds.conf:59 (toggle-lite bind — keep unless Rev 2 changes lite surface); README.md many (see §12).

## 12. README.md sweep (380 lines) — two-modes / lite / toggle-lite / tmux / status.sh inventory

- **tmux: ZERO hits. status.sh: ZERO hits** (grep -i over README.md).
- Lite/two-mode/toggle-lite hits: L79 (binds for both modes), L100 (lite bind line), L104 (Lite mode description), L109 (`⚡` prefix in status), L116 (`## Lite mode` section head), L119, L123-125 (lite_post_speech_silence_duration 0.5 vs 0.6 — must update to 0.8), L125 (toggle-lite/start-lite mention), L139 (mode normal/lite in state.json), L143 (⚡ lite marker), L161 (config table row, default 0.5), L168 (lite_model table row), L322 (mode: normal two-model set vs lite), L337 (lite VRAM).
- Section headings for orientation: Requirements L14, Install L22, First run L48, Hotkey L77, Lite mode L116, Feedback surfaces L133, Configuration L147, VAD-not-config L179, CPU-only L200, Troubleshooting L227 (cuDNN L229, Wrong microphone L256, wtype vs ydotool L274), Logs/status/stopping L284, Model lifecycle & VRAM L330.

## 13. Test inventory (shapes)

- tests/test_config.py (436 ln, 37 tests): defaults-vs-PRD/cuda_check parity (39,66), tomllib natural types, mutable-default, partial-table overlay, unknown-key raises (119), section-not-table raises, type guards (string-for-float 142, bool-for-float 150, int-for-string 156, none-for-float 282, notify_ms 304), device value guard (171-178), backend value guard (194-201), filter guards (215-237), lite_model round-trip (254-261), lite silence round-trip (268-274), from_toml_file, load search-order (339-391), resolved_state_file (395-407), module-level load (418), log override (429).
- tests/test_config_repo_default.py (73 ln, 3 tests): repo config == dataclass defaults (17); exact 20-key schema set incl. final_model/realtime_model (26-46); lite_model comment names SUPER+ALT+D (53-72).
- tests/test_typing_backends.py (301 ln, 22 tests): `_Recorder` fake around subprocess.run (44); exact-argv pins (89, 122); fallback ordering/injection (202-260); abstract-ness (156); no-real-subprocess guard (274).
- tests/test_textproc.py: 21 tests (§6 above).
- tests/test_recorder_host.py (578 ln, 27 tests): dispatch of child events (partial/speech/speech_end/vad/final/ready/error), text() blocking, set_microphone arm/disarm, abort, stop single-flight, spawn/read-loop, _AbortFakeRecorder sentinel-final.
- tests/test_feed_audio.py (real models, offline feed): partials cadence (394), pause halves (418), three finals (434), fuzzy accuracy (447), final latency (459), daemon-path latency line (597), lite simple (653), lite faster than normal (679). Skips cleanly when fixtures/deps absent.
- tests/e2e_virtual_mic.sh: real PipeWire null-sink E2E; rebinds global default source; trap restores; null backend; asserts criteria 2/3/4 via state.json.
- Others present: test_control_socket.py, test_daemon.py, test_feedback.py, test_systemd_unit.py, test_voicectl.py, test_idle_and_gpu.sh, make_test_audio.sh, out/ fixtures.
- systemd/: voice-typing.service (ExecStart=launch_daemon.sh, Restart=on-failure).

## 14. Risks / open questions for Rev 2

- Removing final_model/realtime_model breaks the cuda_check dict contract (CUDA_DEFAULTS/CPU_FALLBACK, daemon `_resolve_device_config` at daemon.py:144-197, recorder_host ready payload, ctl.py status line, and ~30 test assertions). The lite path already overrides both to lite_model (daemon.py:191-192, recorder_host.py:713-714), which is the natural collapse point.
- test_config_repo_default.py pins the exact key set — any schema change fails it until updated; its comment-text test (SUPER+ALT+D) also constrains config.toml comment edits.
- evdev absent from .venv (probe); user in `input` group so /dev/input/event* readable; ydotool key uses raw keycodes (backspace=14) — a press_backspace(n) can be `ydotool key 14:1 14:0` ×n or `--key-delay`; wtype has no key-press command (only type) — press_backspace likely needs evdev or ydotool per backend.
- ACCEPTANCE.md criterion 10 text hardcodes the 0.5 default.

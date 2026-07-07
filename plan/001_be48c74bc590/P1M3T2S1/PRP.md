# PRP — P1.M3.T2.S1: feedback.py (state file + hyprctl notify) + status.sh helper

## Goal

**Feature Goal**: Ship the feedback layer for PRD §4.6 — a `Feedback` class that atomically writes the daemon's live state to `$XDG_RUNTIME_DIR/voice-typing/state.json` and fires fire-and-forget `hyprctl notify` popups on listening-start / each final / listening-stop ONLY (never per partial). Plus a POSIX `status.sh` helper that jq-reads the state file into a one-line tmux status-right snippet. This is the **complete** P1.M3.T2 task (impl **and** tests — there is no S2 split; `plan_status` shows T2 has only S1).

**Deliverable** (THREE artifacts + one chmod):
1. `voice_typing/feedback.py` — `class Feedback` taking `FeedbackConfig`; methods `update_partial(text)`, `set_phase(phase)`, `record_final(text)`, `set_listening(listening)`, and a private `_write()` / `_notify(msg)`. Pure stdlib (`json`, `os`, `subprocess`, `tempfile`, `time`, `logging`) + the `FeedbackConfig` import. Verbatim source is in Implementation Blueprint → Task 3.
2. `voice_typing/status.sh` — POSIX `#!/bin/sh` helper (jq + cut) printing `🎤 <partial>` (truncated to 60 chars) when listening, else empty. Header comment IS the tmux integration doc (item DOCS: Mode A). Verbatim source in Task 4.
3. `tests/test_feedback.py` — TDD unit tests: state-file round-trip, throttle behavior, hyprctl argv pinning + "never notify per partial", error swallowing. Follows `tests/test_typing_backends.py`'s `_Recorder` + `monkeypatch` harness style. Test spec in Task 5.
4. `chmod +x voice_typing/status.sh`.

**Success Definition**:
- (a) `voice_typing/feedback.py` exists, `py_compile`-clean, and `import voice_typing.feedback` imports ONLY stdlib + `FeedbackConfig` (no `cuda_check`/`torch`/`realtimestt`/`ctranslate2`).
- (b) State-file JSON shape is EXACTLY `{"listening": bool, "phase": str, "partial": str, "last_final": str, "ts": float}` (PRD §4.6 + item); written atomically (tempfile in the SAME directory as the target + `os.replace`); parent dir `mkdir 0o700`; final file inherits `0o600` from `tempfile.mkstemp`.
- (c) `update_partial` is THROTTLED to a minimum 0.1 s between disk writes (≥10 Hz max, PRD §4.6); the in-memory `partial` is always updated so the next flush captures the latest. `set_phase` / `record_final` / `set_listening` always write (un-throttled).
- (d) `hyprctl notify` argv is EXACTLY `["hyprctl", "notify", "-1", str(notify_ms), "rgb(88c0d0)", msg]` with `check=False` + `stdout/stderr=DEVNULL`; invoked ONLY on listening-start (`"● listening"`), each final (`"✔ <text>"`), listening-stop (`"■ stopped"`) — **NEVER** on `update_partial` (partials go to state.json only). All `OSError`/`subprocess.SubprocessError` swallowed (fire-and-forget).
- (e) Notifications fire only when `cfg.hypr_notify` is True; only on an actual `listening` VALUE TRANSITION (no double-notify on a no-op `set_listening(False)` when already False).
- (f) `status.sh` prints `🎤 <partial>` (or `🎤 …` when partial empty) when `.listening`, else empty; missing/malformed state file → empty line + exit 0 (never aborts; no `set -e`).
- (g) `tests/test_feedback.py` passes (≥10 Hz throttle via a monkeypatched `time.monotonic` fake clock; hyprctl via a `subprocess.run` recorder — no real notifications sent during tests).
- (h) No out-of-scope files: NO edits to `config.py` (P1.M2.T1.S1 owns `FeedbackConfig`; this module only imports it), no `daemon.py`/`ctl.py`/`typing_backends.py`/`textproc.py`/`config.toml`/`install.sh`/systemd, no edits to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. stdlib only — no new dependencies.

## User Persona

**Target User**: The daemon (`voice_typing/feedback.Feedback`) is an internal service object — no direct user surface. The *visible* output is two things end-users see: (1) the live partial transcript in their tmux status bar (via `status.sh`), and (2) Hyprland popups (`hyprctl notify`) that confirm "listening armed", show each finalized sentence, and confirm "stopped".

**Use Case**: While dictating, the user glances at the tmux status-right to watch their words stream in phone-style (the partial), and gets a Hyprland popup per finalized sentence (`✔ <text>`) plus start/stop confirmations. Without leaving the terminal, they know the system heard them.

**User Journey**: `voicectl toggle` → daemon `set_listening(True)` → Hyprland popup `● listening`, tmux status shows `🎤 …` → user speaks → partials stream to state.json (tmux shows `🎤 <words>` live) → utterance finalizes → `record_final(text)` → popup `✔ <text>` + daemon types it → `voicectl toggle` → `set_listening(False)` → popup `■ stopped`, tmux status goes blank.

**Pain Points Addressed**: (1) Hyprland notifications are NOT replaceable by ID — per-partial notifications would stack-spam the screen. The design routes partials to the state file (tmux consumes them) and reserves popups for the 3 non-spammy events. (2) Inline jq in `tmux.conf` is a quoting nightmare → `status.sh` isolates it. (3) A torn (half-written) state file would corrupt tmux's status line every second → atomic write guarantees readers always see a complete JSON.

## Why

- **It is the feedback/UI half of the data-flow.** PRD §4 architecture: `realtime model → partials → state file (JSON) → tmux status`, and `final → on_final → ... → feedback notify`. `textproc` (P1.M2.T2.S1) and `typing_backends` (P1.M3.T1.S1) are done; this module is the state/notify link. Without it, the daemon (P1.M4.T1.S1/S2) has nowhere to publish partials and nothing to call for finals.
- **Atomic write is non-negotiable.** tmux polls `status.json` every 1s (`status-interval 1`). A non-atomic write (open/truncate/write) can be read mid-write → `jq` errors → status flicker or error text. Tempfile + `os.replace` is a same-filesystem atomic rename (POSIX guarantee) — readers see either the old or the new file, never a partial one.
- **Throttle protects the disk + the 1s tmux cadence.** RealtimeSTT emits partials at ~150ms cadence (`realtime_processing_pause=0.15`, PRD §4.4) ≈ 6.7 Hz — already under 10 Hz, but a burst could exceed it. Capping disk writes at ≥10 Hz (min 0.1 s apart) is cheap insurance and matches PRD §4.6 verbatim. tmux polls at 1s anyway, so writing faster than ~10 Hz is pure waste.
- **Notification discipline = UX sanity.** The `hyprctl notify -1 <ms> "rgb(88c0d0)" "<partial>"` example in PRD §4.6 is the OLD per-partial design. The item description SUPSEDES it: Hyprland notifications are not replaceable by ID, so per-partial popups would stack into an unreadable pile. The fix (and this task's contract): popups ONLY on start/final/stop; partials live in the state file for tmux. **This is the single most important behavioral constraint** — an implementer reading only PRD §4.6 would get it wrong.
- **Small, well-bounded, GPU-free, unblocks the daemon + install.sh.** Pure stdlib. The daemon (P1.M4.T1.S1) wires callbacks to `Feedback`; install.sh (P1.M6.T1.S1) prints the tmux snippet that calls `status.sh`. Finishing it here keeps both clean.

## What

One pure-stdlib module `voice_typing/feedback.py` exposing `class Feedback`:
- `__init__(self, cfg: FeedbackConfig)` — stores config; initializes in-memory state `{"listening": False, "phase": "idle", "partial": "", "last_final": "", "ts": 0.0}`; throttle clock baseline `0.0`. Does NOT write on construction (lazy — the daemon's startup `set_listening(False)` creates the file; avoids writing before the daemon is ready).
- `update_partial(text)` — sets `partial` in memory, then writes ONLY if `time.monotonic() - last_partial_write >= 0.1` (updating `last_partial_write`). Never notifies.
- `set_phase(phase)` — sets `phase`; always writes. Never notifies (phases are VAD transitions, not the start/final/stop notify events — see Gotcha #2).
- `record_final(text)` — sets `last_final`; always writes; if `hypr_notify`, fires `_notify("✔ " + text)`.
- `set_listening(listening)` — sets `listening`; always writes; if `hypr_notify` AND the value CHANGED, fires `_notify("● listening")` on False→True or `_notify("■ stopped")` on True→False.
- `_write()` — sets `ts = time.time()`, resolves path via `cfg.resolved_state_file()`, `os.makedirs(dirname, exist_ok=True, mode=0o700)`, `tempfile.mkstemp(dir=dirname, prefix=".state.", suffix=".tmp")` → `json.dump(state)` → `os.replace(tmp, target)`; cleans up the temp file on any error then re-raises.
- `_notify(msg)` — `subprocess.run(["hyprctl","notify","-1",str(cfg.notify_ms),"rgb(88c0d0)",msg], check=False, stdout=DEVNULL, stderr=DEVNULL)` wrapped in `try/except (OSError, subprocess.SubprocessError): pass`.

Plus `voice_typing/status.sh` (POSIX sh, jq+cut) and `tests/test_feedback.py` (TDD). Verbatim sources in Implementation Blueprint.

### Success Criteria

- [ ] `voice_typing/feedback.py` exists; `.venv/bin/python -m py_compile voice_typing/feedback.py` exits 0.
- [ ] `import voice_typing.feedback` imports only stdlib + `FeedbackConfig` (grep-clean of `cuda_check`/`torch`/`realtimestt`/`ctranslate2`).
- [ ] State-file shape after any write is exactly `{"listening","phase","partial","last_final","ts"}` with a float `ts`.
- [ ] Atomic write: no `.state.*.tmp` files linger in the state dir after a successful write; a reader `json.load`-ing concurrently never fails.
- [ ] Parent dir of state file is created `0o700` (mode bits, regardless of umask); final state file is `0o600` (inherited from `tempfile.mkstemp`).
- [ ] `update_partial` writes at most once per 0.1 s (monotonic); in-memory partial always updated; first call after 0.1 s+ always writes.
- [ ] `set_phase` / `record_final` / `set_listening` always write (un-throttled) regardless of the partial clock.
- [ ] `hyprctl notify` argv is exactly `["hyprctl","notify","-1",str(notify_ms),"rgb(88c0d0)",msg]`; `check=False`; stdout+stderr → `DEVNULL`.
- [ ] `_notify` messages: start=`"● listening"`, final=`"✔ "+text`, stop=`"■ stopped"`.
- [ ] `update_partial` NEVER invokes `hyprctl` (the anti-spam contract).
- [ ] Notifications suppressed when `cfg.hypr_notify == False`.
- [ ] Notifications fire only on an actual `listening` value transition (no-op `set_listening` does not double-notify).
- [ ] `_notify` swallows `OSError` + `subprocess.SubprocessError` (missing `hyprctl` binary, non-Hyprland session) — no exception propagates.
- [ ] `voice_typing/status.sh` is executable (`chmod +x`); `#!/bin/sh`; prints `🎤 <partial>` when `.listening`, empty when not; missing/malformed state → empty + exit 0; output truncated to 60 chars.
- [ ] `tests/test_feedback.py` passes via `.venv/bin/python -m pytest tests/test_feedback.py -v`; no real `hyprctl` invocation, no real `time.monotonic` flakiness (both monkeypatched).
- [ ] ONLY `voice_typing/feedback.py`, `voice_typing/status.sh`, `tests/test_feedback.py` are created/changed. Nothing else.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge of this codebase: the consumed contract (`FeedbackConfig` in `voice_typing/config.py`, incl. `resolved_state_file()`) is read at preflight; the hyprctl argv + icon semantics + jq query are verified LIVE in research §1–2; the atomic-write mechanics (mkstemp same-dir + os.replace, 0o600/0o700, monotonic throttle clock) are pinned in research §3; the test seams (monkeypatch `subprocess.run` + `time.monotonic`, `tmp_path` round-trip) are pinned in research §4 and mirrored from `tests/test_typing_backends.py`; verbatim module + script source is in Tasks 3–4; and the validation commands (py_compile, import-purity grep, pytest, status.sh smoke) are executable as written.

### Documentation & References

```yaml
# MUST READ — the authoritative behavior spec. NOTE THE SUPERSESSION (Gotcha #1).
- file: PRD.md
  why: "§4.6 defines the state-file shape + the tmux snippet shape + the hyprctl color/icon/notify_ms.
        §4 architecture diagram: partials → state file → tmux status; final → on_final → feedback.
        §4.2 wires on_realtime_transcription_stabilized → feedback.update_partial and on_final →
        record_final; on_recording_start/on_vad_detect_start → set_phase. §4.5 [feedback] table:
        state_file/hypr_notify/notify_ms defaults. §8 (risks) — not directly cited but the
        'notification spam' risk is the root of the never-per-partial rule."
  critical: "PRD §4.6 shows `hyprctl notify ... \"<partial>\"` as the per-partial example. THAT LINE
             IS SUPERSEDED by the item description: notifications are start/final/stop ONLY, NEVER
             per partial. Do NOT implement per-partial hyprctl notify — partials go to state.json.
             The tmux snippet SHAPE (§4.6) is still correct; we just move the jq into status.sh."

# MUST READ — the consumed contract (FeedbackConfig). READ, do NOT edit.
- file: voice_typing/config.py
  why: "Defines FeedbackConfig(state_file='', hypr_notify=True, notify_ms=2500) and its
        resolved_state_file() method — the SINGLE source of truth for the state-file path. Empty
        state_file → $XDG_RUNTIME_DIR/voice-typing/state.json; raises RuntimeError if empty AND
        XDG_RUNTIME_DIR unset. feedback.py MUST call resolved_state_file() (do not re-derive the
        XDG path). The docstring mandates feedback.py resolves lazily at WRITE time."
  critical: "Call cfg.resolved_state_file() inside _write(), NOT in __init__ (lazy resolution —
             tests pass an explicit state_file via tmp_path; production relies on XDG_RUNTIME_DIR
             which is set by systemd user sessions). Do NOT mutate the config. Do NOT import
             cuda_check/torch/realtimestt into feedback.py (same purity rule as config.py)."

# MUST READ — verified CLI facts + the full design (this task's research, verified live 2026-07-06)
- docfile: plan/001_be48c74bc590/P1M3T2S1/research/feedback_hyprctl_jq_verification.md
  why: "§1: hyprctl `notify --help` → icon -1 = 'No icon' (so the glyph ●/✔/■ IS the visual);
        canonical argv; NOT replaceable by ID → start/final/stop only; check=False + DEVNULL +
        except(OSError,SubprocessError). §2: jq query verified against sample state.json incl.
        the cut -c1-60 char-truncation table (🎤 counts as 1 char in UTF-8 locale); status.sh
        path fallback `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}`; NO set -e. §3: atomic write via
        tempfile.mkstemp(dir=same)+os.replace (same-fs rename); mkstemp→0o600 inherited;
        makedirs(exist_ok=True,0o700); ts=time.time() (wall); throttle clock=time.monotonic()
        (NTP-immune); only update_partial throttled. §4: test seams. §5: FeedbackConfig recap.
        §6: SCOPE — exactly 3 files created here + chmod; daemon/install.sh are future consumers."
  section: "ALL sections load-bearing. §1 (hyprctl), §2 (jq/status.sh), §3 (atomic+throttle),
            §4 (test seams), §6 (scope)."

# MUST READ — the sibling module + its test (the style + harness to mirror EXACTLY)
- file: voice_typing/typing_backends.py
  why: "The sibling IO-backend module landed by P1.M3.T1.S1. Mirror its: module docstring structure
        (plain present-tense, CONSUMES/CONSUMED BY sections, thread/purity notes, PRD cross-refs not
        duplication), `from __future__ import annotations`, `logger = logging.getLogger(__name__)`,
        stdlib-only purity, and the `_TMUX`-style module constant for pinned paths/args. feedback.py
        follows the SAME shape: docstring + future-import + imports + Feedback class + private
        helpers."
  critical: "Mirror the docstring CONSUMES/CONSUMED BY pattern verbatim (feedback CONSUMES
             FeedbackConfig; CONSUMED BY daemon P1.M4.T1.* and the tmux status via status.sh)."
- file: tests/test_typing_backends.py
  why: "The test harness style: the `_Recorder` class monkeypatching `subprocess.run` via a pytest
        `recorder` fixture, capturing argv + kwargs, never touching the OS. feedback.py's hyprctl
        tests use the IDENTICAL mechanic. The module docstring ('Written FIRST (TDD)', full-path
        pytest invocation) is the house style for test files."
  critical: "REUSE the _Recorder shape for hyprctl (monkeypatch subprocess.run, assert argv). ADD a
             second monkeypatch for time.monotonic to control throttle deterministically. Test files
             invoke `.venv/bin/python -m pytest` (zsh aliases bare python)."

# Background — machine facts (READ-ONLY context)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1: /usr/bin/hyprctl + /usr/bin/jq present; XDG_RUNTIME_DIR set under systemd/logind; zsh
        aliases → ALWAYS use .venv/bin/python for tooling. §3 data-flow: partials→state, final→type.
        Confirms the runtime environment feedback.py targets."
  critical: "Use .venv/bin/python explicitly for validation (never bare python/pytest). hyprctl/jq
             are present so L3 status.sh smoke runs for real."

# Downstream — the consumers this item feeds (future work, do NOT build)
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M4.T1.S1 (daemon partial/state callbacks): wires on_realtime_transcription_stabilized →
        feedback.update_partial; on_recording_start/on_vad_detect_start → feedback.set_phase. P1.M4.
        T1.S2 (on_final): feedback.record_final + the listening gate → feedback.set_listening on
        toggle/start/stop. P1.M6.T1.S1 (install.sh) prints the tmux snippet referencing status.sh.
        Confirms the Feedback method NAMES + signatures this item must expose."
  critical: "Do NOT add daemon/install.sh logic here — only define the Feedback API the daemon will
             call. The method names (update_partial/set_phase/record_final/set_listening) are the
             contract; do not rename them."
```

### Current Codebase tree (state at P1.M3.T2.S1 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*'` from repo root. Expected (config.py + textproc.py + typing_backends.py + their tests landed; 69 tests collect):

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores dist/, *.pyc, __pycache__/, .venv/, .pytest_cache/, .pi-subagents/ (DO NOT touch)
├── .venv/                      # Python 3.12.10; pytest 9.1.1 (dev group)
├── PRD.md                      # READ-ONLY (§4.6 + §4 + §4.5 [feedback])
├── config.toml                 # ← P1.M2.T1.S2 output (has the [feedback] table). DO NOT touch.
├── pyproject.toml              # dev = ["pytest>=9.1.1"] (DO NOT touch; no new deps)
├── uv.lock                     # DO NOT touch
├── voice_typing/
│   ├── __init__.py             # package docstring
│   ├── cuda_check.py           # P1.M1.T2.S2 (unrelated)
│   ├── launch_daemon.sh        # P1.M1.T2.S1 (unrelated)
│   ├── prefetch.py             # P1.M1.T3.S1 (unrelated)
│   ├── config.py               # ← P1.M2.T1.S1 (FeedbackConfig + resolved_state_file() live HERE). READ, DO NOT EDIT.
│   ├── textproc.py             # ← P1.M2.T2.S1 (STYLE TEMPLATE). DO NOT EDIT.
│   └── typing_backends.py      # ← P1.M3.T1.S1 (STYLE TEMPLATE — closest sibling). DO NOT EDIT.
└── tests/
    ├── test_config.py                # ← P1.M2.T1.S1. DO NOT EDIT.
    ├── test_config_repo_default.py   # ← P1.M2.T1.S2. DO NOT EDIT.
    ├── test_textproc.py              # ← P1.M2.T2.S1. DO NOT EDIT.
    └── test_typing_backends.py       # ← P1.M3.T1.S2 (HARNESS TEMPLATE — _Recorder/monkeypatch style). DO NOT EDIT.
# NO voice_typing/feedback.py yet — Task 3 creates it.
# NO voice_typing/status.sh yet — Task 4 creates it.
# NO tests/test_feedback.py yet — Task 5 creates it.
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── feedback.py             # ← CREATE (Task 3): class Feedback (state file + hyprctl notify)
│   └── status.sh               # ← CREATE (Task 4) + chmod +x: POSIX jq helper for tmux status-right
└── tests/
    └── test_feedback.py        # ← CREATE (Task 5): round-trip + throttle + hyprctl (subprocess.run mocked)
# NOTHING ELSE. No edits to config.py/textproc.py/typing_backends.py/config.toml/pyproject.toml/uv.lock.
# No tests/__init__.py (pytest discovers test_*.py without it). No daemon/ctl/install.sh/systemd.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — NEVER NOTIFY PER PARTIAL (the #1 behavior contract). PRD §4.6 shows a per-partial
#   `hyprctl notify ... "<partial>"` example — that is the OLD design, SUPERSEDED by the item:
#   Hyprland notifications are NOT replaceable by ID, so per-partial popups stack into spam.
#   update_partial() writes the partial to state.json ONLY and NEVER calls _notify(). Notifications
#   fire EXCLUSIVELY in set_listening (start/stop) and record_final (final). (Research §1; item
#   contract point 1.) An implementer who reads only PRD §4.6 will get this wrong — this PRP is
#   authoritative over the PRD's inline example.

# CRITICAL #2 — set_phase() DOES NOT NOTIFY. The item says set_phase "may notify on listening
#   transitions" but the HARD constraint (notify only on start/final/stop) forbids it: phase
#   transitions (idle/listening/speaking VAD states) are NOT start/final/stop events. If set_phase
#   notified, the "speaking"→"listening" VAD flip would fire a popup that is none of the 3 sanctioned
#   events → violates the anti-spam rule. set_phase() writes the phase field ONLY. The listening
#   GATE (bool) is a separate field owned by set_listening(), which owns the start/stop popups.
#   (Item contract + PRD §4.2 "if available" wiring note.)

# CRITICAL #3 — TEMPFILE MUST BE IN THE SAME DIRECTORY AS THE TARGET. Atomicity of os.replace
#   depends on a SAME-FILESYSTEM rename. tempfile.mkstemp(dir=<target dir>, ...) puts the temp file
#   in the target's directory; os.replace(tmp, target) is then atomic. Using tempfile.mkstemp() with
#   NO dir (or the system temp dir) would be cross-filesystem → os.replace raises OSError (EXDEV-ish)
#   or is non-atomic. ALWAYS pass dir=os.path.dirname(target). (Research §3.)

# CRITICAL #4 — tempfile.mkstemp CREATES MODE 0o600 ALREADY (Python 3 security default). Do NOT
#   os.chmod the final file — the renamed-in-place state.json inherits mkstemp's 0o600. Parent dir:
#   os.makedirs(directory, exist_ok=True, mode=0o700) — 0o700 has no group/other bits for umask to
#   mask, so the dir is 0o700 regardless of umask. (Research §3; item "mkdir 0700".)

# CRITICAL #5 — THROTTLE CLOCK = time.monotonic(), NEVER time.time(). Wall clock (time.time()) can
#   jump BACKWARD on NTP sync → a backward jump would make (now - last) negative → always < 0.1 →
#   throttle forever (partial never flushes). time.monotonic() is monotonic → immune. ts FIELD uses
#   time.time() (wall epoch, matches PRD sample 1783718400.123). (Research §3.)

# CRITICAL #6 — THROTTLE THE DISK WRITE, NOT THE IN-MEMORY UPDATE. update_partial() must set
#   self._state["partial"] = text BEFORE the throttle check, so the latest partial is always in
#   memory and the next flush (from any method) captures it. Skipping the write is fine; skipping
#   the memory update would drop the latest words. "≥10 Hz max" = min 0.1 s between WRITES. Only
#   update_partial is throttled; set_phase/record_final/set_listening always write. (Research §3.)

# CRITICAL #7 — NOTIFY ONLY ON A LISTENING VALUE TRANSITION. If set_listening(False) is called when
#   listening is already False (daemon startup no-op), do NOT fire the "■ stopped" popup. Track the
#   previous value; fire start on False→True, stop on True→False, nothing on no-op. This also
#   prevents a spurious popup when the daemon initializes (it starts not-listening per §4.9).
#   (Design; avoids startup spam.)

# CRITICAL #8 — hyprctl MUST BE FIRE-AND-FORGET: check=False + try/except (OSError,
#   subprocess.SubprocessError): pass. Missing hyprctl binary (not under Hyprland / SSH) raises
#   FileNotFoundError (an OSError); a hung/errored hyprctl raises SubprocessError. BOTH must be
#   swallowed — a notification failure must NEVER crash the daemon or stall on_final. Suppress
#   stdout+stderr (subprocess.DEVNULL) so hyprctl's `ok` ack doesn't clutter journald. (Research §1.)

# CRITICAL #9 — hyprctl ICON -1 = "NO ICON" (verified). So the leading glyph in the message string
#   (● / ✔ / ■) IS the visual. Pass "-1" as the icon arg verbatim; embed the glyph in the message.
#   Color arg "rgb(88c0d0)" verbatim (Nord frost — PRD §4.6). Do not invent an icon number.
#   (Research §1.)

# CRITICAL #10 — status.sh: NEVER `set -e` AND NEVER let it exit nonzero. tmux #(...) shows the
#   script's stdout in status-right; a nonzero exit or an abort would print an error string. jq
#   failure + `2>/dev/null` + the pipe to cut already yields empty-on-failure with exit 0. The `//
#   false` / `// "…"` defaults in the jq query make it safe if a key is absent (older/forward state
#   files). Path fallback `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}` (POSIX `:-` treats empty as
#   unset). Shebang `#!/bin/sh` (POSIX; tmux #(...) runs /bin/sh). (Research §2.)

# CRITICAL #11 — status.sh USES `cut -c1-60` (CHARACTERS, not bytes). In a UTF-8 locale cut counts
#   the 🎤 emoji as 1 char, so truncation lands on 60 visible chars (verified, research §2 table).
#   Do NOT switch to `cut -b1-60` (bytes) — that could split a multibyte char mid-sequence. Match the
#   PRD §4.6 `cut -c1-60` verbatim.

# CRITICAL #12 — PURE STDLIB + FeedbackConfig. feedback.py imports only json/os/subprocess/tempfile/
#   time/logging + `from voice_typing.config import FeedbackConfig`. It must NOT import cuda_check/
#   torch/ctranslate2/realtimestt — it must load in CPU-only and test contexts (tests monkeypatch
#   subprocess.run + time.monotonic; the module must import without a GPU). Same purity rule as
#   config.py/textproc.py/typing_backends.py. (Research §4/§5.)

# CRITICAL #13 — FEEDBACK NEEDS NO THREADING.Lock. The daemon calls Feedback methods from the
#   RealtimeSTT callback threads (partial/final) and the socket thread (set_listening). Updates to
#   self._state (a dict) are individually atomic in CPython, and _write() does tempfile+os.replace
#   which is atomic at the OS level. A torn write is impossible. Do NOT add a Lock (dead weight +
#   deadlock risk if a future caller recurses). Document the argument. (Same reasoning as
#   typing_backends §7; research §3.)

# CRITICAL #14 — THIS TASK INCLUDES THE TESTS (combined impl+test). Unlike P1.M3.T1 (split into
#   S1=impl, S2=tests), P1.M3.T2 has ONE subtask (S1) that delivers feedback.py + status.sh +
#   tests/test_feedback.py. Do NOT skip the test file — it is a required deliverable. (plan_status;
#   item "TDD where feasible".)

# GOTCHA #15 — FULL PATHS for tooling (zsh aliases python/pytest). Always
#   .venv/bin/python -m pytest / .venv/bin/python -m py_compile (never bare python/pytest). mypy is
#   NOT installed — do NOT list it as a gate. ruff is NOT in .venv (optional, at
#   /home/dustin/.local/bin/ruff) — py_compile + pytest are the authoritative gates. (system_context
#   §1; prior tasks' research.)

# GOTCHA #16 — status.sh IS A DATA FILE TOO. Add `chmod +x voice_typing/status.sh` so tmux's #(...)
#   can exec it directly. Hatch only packages voice_typing/*.py via packages=["voice_typing"]; a
#   .sh in the package dir is fine for the dev/source-tree run (the daemon runs from the repo). If a
#   future wheel packaging concern arises it is P1.M6's job, not here.
```

## Implementation Blueprint

### Data models and structure

No new data model. The module consumes the existing `FeedbackConfig` dataclass from `voice_typing/config.py` (P1.M2.T1.S1) and holds an in-memory state dict matching the PRD §4.6 JSON shape:

```python
# In-memory state (matches the on-disk JSON shape EXACTLY — PRD §4.6 / item):
_STATE_DEFAULTS = {
    "listening":  False,   # the master listening gate (bool)
    "phase":      "idle",  # VAD/recording phase: "idle" | "listening" | "speaking"
    "partial":    "",      # latest realtime partial (throttled to disk at >=10 Hz)
    "last_final": "",      # most recent finalized utterance
    "ts":         0.0,     # wall-clock epoch of the last write (time.time())
}

class Feedback:
    def __init__(self, cfg: FeedbackConfig) -> None: ...
    def update_partial(self, text: str) -> None: ...      # throttled write; never notify
    def set_phase(self, phase: str) -> None: ...          # write; never notify
    def record_final(self, text: str) -> None: ...        # write; notify "✔ <text>" if hypr_notify
    def set_listening(self, listening: bool) -> None: ... # write; notify start/stop on transition
    def _write(self) -> None: ...                         # atomic tempfile+os.replace
    def _notify(self, msg: str) -> None: ...              # hyprctl, fire-and-forget
```

`FeedbackConfig` fields used: `cfg.state_file` ("" → `resolved_state_file()`), `cfg.hypr_notify` (bool gate), `cfg.notify_ms` (int → `str()` in argv). `resolved_state_file()` is called inside `_write()` (lazy).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm inputs exist and targets do not (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/config.py && echo "ok: config.py exists (FeedbackConfig source)" || echo "PREFLIGHT FAIL"
      test -f voice_typing/typing_backends.py && echo "ok: typing_backends.py exists (style template)" || echo "PREFLIGHT FAIL"
      test -f tests/test_typing_backends.py && echo "ok: test_typing_backends.py exists (harness template)" || echo "PREFLIGHT FAIL"
      test ! -e voice_typing/feedback.py && echo "ok: feedback.py not yet created" || echo "PREFLIGHT FAIL: target exists"
      test ! -e voice_typing/status.sh && echo "ok: status.sh not yet created" || echo "PREFLIGHT FAIL: target exists"
      test ! -e tests/test_feedback.py && echo "ok: tests/test_feedback.py not yet created" || echo "PREFLIGHT FAIL: target exists"
      .venv/bin/python -c "from voice_typing.config import FeedbackConfig; c=FeedbackConfig(); print('FeedbackConfig OK', repr(c.state_file), c.hypr_notify, c.notify_ms); print('resolved (with XDG):', c.resolved_state_file())" || echo "PREFLIGHT FAIL: resolved_state_file needs XDG_RUNTIME_DIR? set it: XDG_RUNTIME_DIR=/run/user/\$(id -u)"
      XDG_RUNTIME_DIR=/run/user/$(id -u) .venv/bin/python -c "from voice_typing.config import FeedbackConfig; print('resolved:', FeedbackConfig().resolved_state_file())"
      command -v hyprctl >/dev/null && command -v jq >/dev/null && echo "ok: hyprctl + jq present (L3 smokes run for real)" || echo "note: hyprctl/jq missing (smokes will be no-ops)"
  - EXPECTED: config.py + typing_backends.py + test_typing_backends.py present; feedback.py + status.sh + test_feedback.py
    absent; FeedbackConfig OK prints `'' True 2500`; resolved prints `$XDG/voice-typing/state.json`;
    hyprctl (/usr/bin/hyprctl) + jq (/usr/bin/jq) present on this machine.
  - DO NOT: create any target file yet, run uv sync/add, or touch any other file.

Task 2: WRITE tests/test_feedback.py FIRST (TDD — RED until feedback.py lands in Task 3).
        Use the `write` tool with EXACTLY the content in "Task 5 SOURCE" below.
  - FILE: tests/test_feedback.py
  - CONTENT: module docstring + the `_Recorder`/`_Clock` harness + `feedback` pytest fixture + all
    test functions from the Task 5 spec.
  - DO NOT: import cuda_check/torch/realtimestt (Gotcha #12); call real hyprctl (subprocess.run is
    mocked); depend on real time.monotonic (it is mocked).

Task 3: CREATE voice_typing/feedback.py — use the `write` tool with EXACTLY the content in
        "Task 3 SOURCE" below (verbatim). This turns the Task 2 tests GREEN.
  - FILE: voice_typing/feedback.py
  - CONTENT: module docstring + `from __future__ import annotations` + imports (json/os/subprocess/
    tempfile/time/logging + FeedbackConfig) + Feedback class (methods above + _write + _notify).
  - DO NOT: notify per partial (Critical #1); make set_phase notify (Critical #2); forget dir= on
    mkstemp (Critical #3); chmod the file (Critical #4); use time.time() for throttle (Critical #5);
    forget to update in-memory partial before throttle (Critical #6); notify on no-op transition
    (Critical #7); let hyprctl raise (Critical #8); use a non-(-1) icon (Critical #9); import heavy
    deps (Critical #12); add a Lock (Critical #13).

Task 4: CREATE voice_typing/status.sh — use the `write` tool with EXACTLY the content in
        "Task 4 SOURCE" below (verbatim), then `chmod +x voice_typing/status.sh`.
  - FILE: voice_typing/status.sh
  - CONTENT: #!/bin/sh header comment (the tmux integration doc — item DOCS Mode A) + STATE path
    resolution + jq query + cut -c1-60.
  - DO NOT: add `set -e` (Critical #10); use cut -b (Critical #11); drop the `// false`/`// "…"`
    defaults; reference the user's tmux.conf (just DOCUMENT the snippet, never edit it).

Task 5: VALIDATE — run the Validation Loop L1 (py_compile + import purity), L2 (pytest), L3
        (status.sh smoke + atomic-write check + factory smoke), L4 (scope guard). Iterate until all
        gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M3.T2.S1: feedback.py (Feedback: atomic state.json + hyprctl notify) + status.sh + tests".
```

#### Task 3 SOURCE — `voice_typing/feedback.py` (write verbatim)

```python
"""voice_typing.feedback — state-file writer + Hyprland notify (PRD §4.6).

Feedback is the daemon's live-state publisher. It writes a small JSON snapshot of the
current voice-typing session (listening flag, VAD phase, latest partial, last final,
timestamp) to an atomic state file, and fires fire-and-forget `hyprctl notify` popups
on the three events that are NOT spammy: listening-start, each final, listening-stop.

STATE FILE (PRD §4.6), written atomically (tempfile + os.replace) to
$XDG_RUNTIME_DIR/voice-typing/state.json (overridable via feedback.state_file):
    {"listening": true, "phase": "speaking", "partial": "...", "last_final": "...", "ts": 1783718400.123}
Consumed by voice_typing/status.sh (the tmux status-right helper) and by voicectl status.

NOTIFICATION DISCIPLINE (the #1 contract — PRD §4.6 inline example is SUPERSEDED):
Hyprland notifications are NOT replaceable by ID, so per-partial popups would stack into
unreadable spam. Partials go to the state file ONLY (tmux shows them live). hyprctl popups
fire EXCLUSIVELY on:
  - listening-start  -> "● listening"   (set_listening False->True transition)
  - each final       -> "✔ <text>"      (record_final)
  - listening-stop   -> "■ stopped"      (set_listening True->False transition)
NEVER on update_partial. NEVER on set_phase (VAD phase flips are not start/final/stop events).

THROTTLE: update_partial is capped at >=10 Hz max (min 0.1 s between disk writes). The
in-memory partial is ALWAYS updated (so the next flush captures the latest words); only
the disk write is throttled. set_phase / record_final / set_listening always write.

ATOMIC WRITE: tempfile.mkstemp(dir=<target dir>) + os.replace(tmp, target) is a
same-filesystem atomic rename (POSIX) — a concurrent tmux jq-reader (status-interval 1s)
never sees a half-written file. mkstemp creates the file mode 0o600 (Python 3 default) →
the renamed state.json inherits 0o600. Parent dir makedirs(exist_ok=True, mode=0o700).

THREAD SAFETY: Feedback methods are called from RealtimeSTT callback threads (partial/
final) and the control-socket thread (set_listening). self._state dict updates are
individually atomic in CPython, and _write()'s tempfile+os.replace is atomic at the OS
level — a torn write is impossible. No Lock is needed (and would risk deadlock if a future
caller recurses). The daemon serializes on_final anyway.

CONSUMES: voice_typing.config.FeedbackConfig (P1.M2.T1.S1): state_file, hypr_notify, notify_ms.
  resolved_state_file() is the SINGLE source of truth for the path — called lazily inside
  _write() (NOT __init__) because XDG_RUNTIME_DIR is unset outside real sessions.
CONSUMED BY: daemon partial/state callbacks (P1.M4.T1.S1) and on_final (P1.M4.T1.S2) as:
    fb = feedback.Feedback(cfg.feedback)
    fb.set_listening(False)                 # startup (not-listening, per PRD §4.9)
    # on_realtime_transcription_stabilized: fb.update_partial(text)
    # on_recording_start/on_vad_detect_start: fb.set_phase("listening"|"speaking"|"idle")
    # on_final: fb.record_final(text)
    # toggle/start/stop socket cmd: fb.set_listening(True|False)

PURE STDLIB (json, os, subprocess, tempfile, time, logging + FeedbackConfig). No cuda_check
/ torch / realtimestt / ctranslate2 — loads in CPU-only and test contexts; subprocess.run +
time.monotonic are mocked in unit tests (P1.M3.T2.S1).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time

from voice_typing.config import FeedbackConfig

logger = logging.getLogger(__name__)

# Minimum seconds between update_partial DISK writes (>=10 Hz max — PRD §4.6). The throttle
# clock is time.monotonic() (never time.time() — wall clock can jump backward on NTP and
# would freeze the partial forever). The ts FIELD still uses time.time() (wall epoch).
_PARTIAL_WRITE_MIN_INTERVAL = 0.1

# hyprctl notify icon "-1" means "No icon" (verified: `hyprctl notify --help`) — so the
# leading glyph in the message string (●/✔/■) IS the visual. Color is Nord frost (PRD §4.6).
_HYPR_ICON = "-1"
_HYPR_COLOR = "rgb(88c0d0)"


class Feedback:
    """Daemon state publisher: atomic state file + fire-and-forget hyprctl notify (PRD §4.6)."""

    def __init__(self, cfg: FeedbackConfig) -> None:
        self._cfg = cfg
        # In-memory state mirrors the on-disk JSON shape EXACTLY (PRD §4.6 / item contract).
        self._state: dict[str, object] = {
            "listening": False,
            "phase": "idle",
            "partial": "",
            "last_final": "",
            "ts": 0.0,
        }
        # Throttle baseline: 0.0 so the FIRST update_partial always writes (monotonic() >> 0.1).
        self._last_partial_write = 0.0

    # --- public API (the daemon calls these) ---

    def update_partial(self, text: str) -> None:
        """Record a realtime partial; THROTTLED disk write (>=10 Hz max); NEVER notify.

        The in-memory partial is updated unconditionally so the next flush (from any
        method) captures the latest words — only the disk write is throttled.
        """
        self._state["partial"] = text
        now = time.monotonic()
        if now - self._last_partial_write < _PARTIAL_WRITE_MIN_INTERVAL:
            return  # throttled: skip this disk write; memory already holds the latest partial
        self._last_partial_write = now
        self._write()

    def set_phase(self, phase: str) -> None:
        """Record a VAD/recording phase (idle/listening/speaking); always write; never notify.

        Phase flips are NOT start/final/stop events, so they never fire hyprctl (the
        anti-spam rule — see module docstring).
        """
        self._state["phase"] = phase
        self._write()

    def record_final(self, text: str) -> None:
        """Record a finalized utterance; set last_final; always write; notify '✔ <text>'.

        Notifications fire only when cfg.hypr_notify is True.
        """
        self._state["last_final"] = text
        self._write()
        if self._cfg.hypr_notify:
            self._notify("✔ " + text)

    def set_listening(self, listening: bool) -> None:
        """Set the master listening gate; always write; notify start/stop ON TRANSITION ONLY.

        start (False->True): '● listening'. stop (True->False): '■ stopped'. A no-op call
        (same value) writes but does NOT notify (avoids startup spam — daemon starts
        not-listening per PRD §4.9). Notifications fire only when cfg.hypr_notify is True.
        """
        prev = self._state["listening"]
        self._state["listening"] = listening
        self._write()
        if self._cfg.hypr_notify and listening != prev:
            self._notify("● listening" if listening else "■ stopped")

    # --- internals ---

    def _write(self) -> None:
        """Atomically write self._state to cfg.resolved_state_file() (tempfile + os.replace).

        Sets ts=time.time() (wall epoch). Creates the parent dir 0o700. The temp file is
        created IN THE TARGET DIRECTORY (same filesystem → os.replace is atomic) and starts
        mode 0o600 (Python 3 mkstemp default), which the renamed state.json inherits.
        Raises propagate (a state-write failure is a real error the daemon should log) —
        but the temp file is cleaned up first so no .tmp litters the dir.
        """
        self._state["ts"] = time.time()
        path = self._cfg.resolved_state_file()  # raises RuntimeError if empty AND XDG unset
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh)
            os.replace(tmp, path)
        except BaseException:
            # Clean up the orphaned temp file on ANY failure (incl. json/replace errors)
            # so a crash mid-write doesn't leave .state.*.tmp littering the runtime dir.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _notify(self, msg: str) -> None:
        """Fire-and-forget `hyprctl notify`. Swallow ALL errors (missing binary / non-Hyprland).

        check=False + DEVNULL so hyprctl's `ok` ack never clutters journald and a nonzero
        exit never raises. OSError (binary missing) + SubprocessError are both caught — a
        notification failure must NEVER crash the daemon or stall on_final.
        """
        try:
            subprocess.run(
                ["hyprctl", "notify", _HYPR_ICON, str(self._cfg.notify_ms), _HYPR_COLOR, msg],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # Fire-and-forget: log at DEBUG (not WARNING) — non-Hyprland/SSH runs hit this
            # routinely and it is not actionable. Never re-raise.
            logger.debug("hyprctl notify failed (%s); ignored", exc)
```

#### Task 4 SOURCE — `voice_typing/status.sh` (write verbatim, then `chmod +x`)

```sh
#!/bin/sh
# voice_typing/status.sh — tmux status-right helper (PRD §4.6).
#
# Prints a one-line "live partial" snippet for tmux's status-right by jq-reading the
# voice-typing daemon's state.json. Empty output when not listening (so status-right is
# blank when idle). Called every status-interval (1s) by tmux's #(...) substitution.
#
# =====================================================================
#  USER INTEGRATION  (item DOCS: Mode A — this comment IS the tmux doc)
# =====================================================================
#  Add these TWO lines to your ~/.tmux.conf (install.sh prints them; we never edit your
#  tmux.conf for you). Point the path at where this script lives:
#
#      set -g status-interval 1
#      set -g status-right "#(/home/dustin/projects/voice-typing/voice_typing/status.sh)"
#
#  Result: while listening, status-right shows "🎤 <live partial words>" (max 60 chars);
#  when idle it is blank. The partial comes from feedback.py's atomic state.json writes.
#
# POSIX sh + jq + cut only. NO `set -e`: a missing or malformed state.json must print an
# empty line with exit 0 (never abort) — otherwise tmux would show an error string in
# status-right. The `2>/dev/null` + the jq `//` defaults already guarantee empty-on-failure.

STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"

# `// false` / `// "…"` make this safe if a key is absent (older/forward state files).
# `cut -c1-60` truncates to 60 CHARACTERS (not bytes) so the 4-byte 🎤 emoji counts as 1.
jq -r 'if (.listening // false) then "🎤 " + (.partial // "…") else "" end' "$STATE" 2>/dev/null \
  | cut -c1-60
```

#### Task 5 SOURCE — `tests/test_feedback.py` (write verbatim — TDD, RED until Task 3 lands)

```python
"""Unit tests for voice_typing.feedback (PRD §4.6 — state file + hyprctl notify).

Pure-Python, NO real hyprctl, NO real disk throttle timing:
  - subprocess.run is monkeypatched (same _Recorder mechanic as tests/test_typing_backends.py)
    so hyprctl argv is captured and NEVER sent to the OS.
  - time.monotonic is monkeypatched (a controllable fake clock) so the >=10 Hz throttle is
    asserted DETERMINISTICALLY (no timing flakiness, no sleeps).
  - the state file is written to pytest's tmp_path (real round-trip: write -> json.load back).

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_feedback.py -v

Covers: state-file round-trip + shape, atomic write (no .tmp litter, valid JSON), throttle
(>=10 Hz cap, first-call-writes, in-memory partial always updated), hyprctl argv pinning,
the "never notify per partial" contract, notify-only-on-transition, hypr_notify=False gate,
and fire-and-forget error swallowing. TDD — RED until voice_typing/feedback.py (P1.M3.T2.S1)
lands.
"""
from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

from voice_typing.config import FeedbackConfig
from voice_typing.feedback import Feedback


# ---------------------------------------------------------------------------
# Harness: subprocess.run recorder (hyprctl) — identical mechanic to
# tests/test_typing_backends.py::_Recorder. Captures argv + kwargs, never touches the OS.
# ---------------------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = {}
        self.calls = []
        self._raises: dict[str, BaseException] = {}

    def raise_on(self, cmd0: str, exc: BaseException) -> None:
        self._raises[cmd0] = exc

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(argv, **kwargs):
            self.calls.append((tuple(argv), dict(kwargs)))
            exc = self._raises.get(argv[0])
            if exc is not None:
                raise exc
            return subprocess.CompletedProcess(args=list(argv), returncode=0)

        monkeypatch.setattr(subprocess, "run", fake_run)

    @property
    def argvs(self) -> list[tuple[str, ...]]:
        return [argv for argv, _kw in self.calls]


# ---------------------------------------------------------------------------
# Harness: controllable monotonic clock (throttle). time.time() is left REAL so ts is a
# plausible epoch; only time.monotonic is frozen/advanced (it drives the throttle).
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def advance(self, dt: float) -> None:
        self._now += dt


# ---------------------------------------------------------------------------
# Fixtures: a Feedback pointed at a tmp_path state file, with hyprctl + clock mocked.
# ---------------------------------------------------------------------------


def _cfg(tmp_path) -> FeedbackConfig:
    return FeedbackConfig(state_file=str(tmp_path / "state.json"), hypr_notify=True, notify_ms=2500)


@pytest.fixture
def feedback(monkeypatch, tmp_path):
    """A Feedback with hyprctl mocked + a frozen monotonic clock; state file in tmp_path."""
    rec = _Recorder()
    rec.install(monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    fb = Feedback(_cfg(tmp_path))
    return fb, rec, clock


def _read_state(tmp_path) -> dict:
    with open(tmp_path / "state.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# State-file round-trip + shape (PRD §4.6)
# ---------------------------------------------------------------------------


def test_initial_state_not_written_until_first_call(tmp_path):
    # __init__ is lazy — no file until a state-changing call (daemon's set_listening(False)
    # at startup creates it).
    Feedback(_cfg(tmp_path))
    assert not os.path.exists(tmp_path / "state.json")


def test_update_partial_round_trip(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("hello world")
    state = _read_state(tmp_path)
    assert state["partial"] == "hello world"
    assert isinstance(state["ts"], float) and state["ts"] > 0.0


def test_state_shape_has_exactly_the_five_fields(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("x")
    state = _read_state(tmp_path)
    assert set(state.keys()) == {"listening", "phase", "partial", "last_final", "ts"}


def test_set_phase_round_trip(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.set_phase("speaking")
    assert _read_state(tmp_path)["phase"] == "speaking"


def test_record_final_sets_last_final(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.record_final("A finished sentence.")
    state = _read_state(tmp_path)
    assert state["last_final"] == "A finished sentence."


def test_set_listening_round_trip(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.set_listening(True)
    assert _read_state(tmp_path)["listening"] is True


# ---------------------------------------------------------------------------
# Atomic write — no .tmp litter; file is always valid JSON (readable mid-write)
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_no_tmp_files(feedback, tmp_path):
    fb, _rec, _clock = feedback
    for i in range(20):
        fb.update_partial(f"partial {i}")
    leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".state.") and p.endswith(".tmp")]
    assert leftovers == [], f"orphaned temp files: {leftovers}"


def test_state_file_mode_0600(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("x")
    mode = os.stat(tmp_path / "state.json").st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_state_dir_mode_0700(tmp_path, monkeypatch):
    # Nested target dir must be created 0o700.
    rec = _Recorder(); rec.install(monkeypatch)
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    nested = tmp_path / "voice-typing" / "state.json"
    Feedback(FeedbackConfig(state_file=str(nested))).update_partial("x")
    dmode = os.stat(tmp_path / "voice-typing").st_mode & 0o777
    assert dmode == 0o700, oct(dmode)


# ---------------------------------------------------------------------------
# Throttle — >=10 Hz max (min 0.1 s between writes); in-memory partial always updated
# ---------------------------------------------------------------------------


def test_first_partial_always_writes(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("first")
    assert _read_state(tmp_path)["partial"] == "first"


def test_throttle_skips_write_within_0_1s(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("first")          # writes (clock=1000.0)
    clock.advance(0.05)                 # 50 ms later — under the 0.1 s cap
    fb.update_partial("second")         # throttled: NOT written to disk
    assert _read_state(tmp_path)["partial"] == "first"  # disk still shows first


def test_throttle_releases_after_0_1s(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("first")          # writes
    clock.advance(0.1)                  # exactly the cap
    fb.update_partial("second")         # writes again
    assert _read_state(tmp_path)["partial"] == "second"


def test_in_memory_partial_updated_even_when_throttled(feedback):
    fb, _rec, clock = feedback
    fb.update_partial("first")
    clock.advance(0.01)                 # under cap -> throttled write
    fb.update_partial("second")
    # memory has the latest; the NEXT non-throttled write flushes it
    assert fb._state["partial"] == "second"


def test_set_phase_always_writes_regardless_of_throttle(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("p")              # writes (resets throttle baseline)
    clock.advance(0.001)                # way under cap
    fb.set_phase("speaking")            # set_phase is NOT throttled -> writes immediately
    assert _read_state(tmp_path)["phase"] == "speaking"


def test_record_final_always_writes_regardless_of_throttle(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("p")
    clock.advance(0.001)
    fb.record_final("done.")            # record_final is NOT throttled -> writes
    assert _read_state(tmp_path)["last_final"] == "done."


# ---------------------------------------------------------------------------
# hyprctl notify — argv pinning, the "never per partial" contract, transitions, gate
# ---------------------------------------------------------------------------


def test_hyprctl_argv_exact_on_listening_start(feedback):
    _fb, rec, _clock = feedback
    feedback[0].set_listening(True)
    assert rec.argvs[0] == (
        "hyprctl", "notify", "-1", "2500", "rgb(88c0d0)", "● listening"
    )


def test_hyprctl_passes_check_false_and_devnull(feedback):
    fb, rec, _clock = feedback
    fb.set_listening(True)
    _argv, kw = rec.calls[0]
    assert kw.get("check") is False
    assert kw.get("stdout") == subprocess.DEVNULL
    assert kw.get("stderr") == subprocess.DEVNULL


def test_record_final_notifies_with_check_glyph(feedback):
    fb, rec, _clock = feedback
    fb.record_final("Hello there.")
    assert rec.argvs[-1][-1] == "✔ Hello there."


def test_set_listening_stop_notifies_stopped(feedback):
    fb, rec, _clock = feedback
    fb.set_listening(True)   # start
    fb.set_listening(False)  # stop
    assert rec.argvs[-1][-1] == "■ stopped"


def test_update_partial_never_invokes_hyprctl(feedback):
    """THE anti-spam contract: partials go to state.json ONLY, NEVER to hyprctl."""
    fb, rec, _clock = feedback
    for i in range(50):
        fb.update_partial(f"partial {i}")
    assert rec.argvs == [], f"hyprctl was called {len(rec.argvs)} times for partials"


def test_set_phase_never_invokes_hyprctl(feedback):
    fb, rec, _clock = feedback
    fb.set_phase("speaking"); fb.set_phase("listening"); fb.set_phase("idle")
    assert rec.argvs == []


def test_no_notify_on_noop_listening_transition(feedback):
    # set_listening(False) when already False -> write but NO popup (no startup spam).
    fb, rec, _clock = feedback
    fb.set_listening(False)
    assert rec.argvs == []


def test_no_double_notify_when_set_true_twice(feedback):
    fb, rec, _clock = feedback
    fb.set_listening(True)
    fb.set_listening(True)   # already True -> no transition -> no popup
    notify_calls = [a for a in rec.argvs if a[0] == "hyprctl"]
    assert len(notify_calls) == 1


def test_no_notify_when_hypr_notify_false(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"), hypr_notify=False, notify_ms=2500)
    fb = Feedback(cfg)
    fb.set_listening(True)
    fb.record_final("text")
    fb.set_listening(False)
    assert rec.argvs == []  # hypr_notify=False suppresses ALL popups


def test_notify_ms_from_config_in_argv(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"), hypr_notify=True, notify_ms=9999)
    Feedback(cfg).set_listening(True)
    assert rec.argvs[0][3] == "9999"  # str(notify_ms) in the argv


# ---------------------------------------------------------------------------
# Fire-and-forget — hyprctl failures never propagate (missing binary / non-Hyprland)
# ---------------------------------------------------------------------------


def test_notify_swallows_missing_binary(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)
    rec.raise_on("hyprctl", FileNotFoundError(2, "No such file", "hyprctl"))
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"))
    fb = Feedback(cfg)
    fb.set_listening(True)  # must NOT raise despite hyprctl missing
    assert os.path.exists(tmp_path / "state.json")  # state write still happened


def test_notify_swallows_subprocess_error(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)
    rec.raise_on("hyprctl", subprocess.SubprocessError("hyprctl exploded"))
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"))
    Feedback(cfg).record_final("x")  # must NOT raise


# ---------------------------------------------------------------------------
# No real hyprctl — the recorder guarantees subprocess.run never runs for real.
# ---------------------------------------------------------------------------


def test_no_real_subprocess_run_during_tests(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    fb = Feedback(FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb.set_listening(True); fb.update_partial("p"); fb.record_final("f")
    # every hyprctl call was captured, none reached the OS
    assert all(a[0] == "hyprctl" for a in rec.argvs) or rec.argvs == []
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — atomic write via same-directory tempfile + os.replace. mkstemp(dir=target_dir)
# guarantees same-filesystem (os.replace is atomic). mkstemp's 0o600 is inherited by the rename.
d = os.path.dirname(path)
os.makedirs(d, exist_ok=True, mode=0o700)
fd, tmp = tempfile.mkstemp(dir=d, prefix=".state.", suffix=".tmp")
try:
    with os.fdopen(fd, "w") as fh: json.dump(self._state, fh)
    os.replace(tmp, path)
except BaseException:
    try: os.unlink(tmp)
    except OSError: pass
    raise

# PATTERN 2 — throttle the WRITE, not the memory update. Update partial in memory FIRST, then
# decide whether to flush. This way the latest words are never lost; only the disk I/O is rate-limited.
self._state["partial"] = text
if time.monotonic() - self._last_partial_write < 0.1: return   # throttled
self._last_partial_write = time.monotonic()
self._write()

# PATTERN 3 — notify only on the 3 sanctioned events, guarded by hypr_notify + a real transition.
# set_listening compares prev vs new so a no-op call (daemon startup) doesn't spam a popup.
prev = self._state["listening"]; self._state["listening"] = listening; self._write()
if self._cfg.hypr_notify and listening != prev:
    self._notify("● listening" if listening else "■ stopped")

# PATTERN 4 — fire-and-forget hyprctl: check=False + DEVNULL + swallow (OSError, SubprocessError).
# A notification failure must NEVER crash the daemon or stall on_final.
try:
    subprocess.run(["hyprctl","notify","-1",str(ms),"rgb(88c0d0)",msg],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except (OSError, subprocess.SubprocessError) as exc:
    logger.debug("hyprctl notify failed (%s); ignored", exc)

# PATTERN 5 — test seams match tests/test_typing_backends.py. Monkeypatch subprocess.run (the
# _Recorder) for hyprctl; monkeypatch time.monotonic (a _Clock) for the throttle. NO constructor
# seam needed -> Feedback(cfg) stays clean. Round-trip reads tmp_path/state.json with json.load.
```

### Integration Points

```yaml
IMPORTS (feedback.py):
  - add to: voice_typing/feedback.py (NEW)
  - pattern: |
      import json, logging, os, subprocess, tempfile, time
      from voice_typing.config import FeedbackConfig   # the sole project import

DATA FILE (status.sh):
  - add to: voice_typing/status.sh (NEW) + chmod +x
  - shebang: "#!/bin/sh" (POSIX; tmux #(...) runs /bin/sh)
  - deps: jq, cut (both present at /usr/bin; status.sh resolves state path via XDG_RUNTIME_DIR)

CONSUMER (future — P1.M4.T1.S1, daemon partial/state callbacks; DO NOT build here):
  - construct: "fb = feedback.Feedback(cfg.feedback)"   # called ONCE at startup
  - startup:   "fb.set_listening(False)"                # PRD §4.9: starts not-listening (creates the file)
  - partial:   "fb.update_partial(text)"                # on_realtime_transcription_stabilized
  - phase:     'fb.set_phase("speaking")'               # on_recording_start/on_vad_detect_start

CONSUMER (future — P1.M4.T1.S2, on_final; DO NOT build here):
  - per final: "fb.record_final(text)"                  # after textproc.clean + type_text

CONSUMER (future — P1.M6.T1.S1, install.sh; DO NOT build here):
  - prints the tmux snippet referencing voice_typing/status.sh (see status.sh header comment).

CONFIG: none — feedback reads cfg.state_file/cfg.hypr_notify/cfg.notify_ms at call time; adds no
  config keys and changes no defaults. resolved_state_file() (P1.M2.T1.S1) is the path source.

DEPENDENCIES: none new (stdlib only; FeedbackConfig already exists). No pyproject.toml / uv.lock
  changes.
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases — system_context.md §1). Run from
> `/home/dustin/projects/voice-typing`. L1 is instant. L2 is the committed pytest suite (this
> task's required deliverable). L3 is a real status.sh + atomic-write smoke. L4 is the scope guard.

### Level 1: Syntax + import-cleanness (no deps needed beyond stdlib)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f voice_typing/feedback.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile voice_typing/feedback.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
# THE KEY IMPORT TEST: importing must pull ONLY stdlib + FeedbackConfig (no cuda_check/torch/realtimestt):
"$PY" -c "import voice_typing.feedback as m; print('L1 import OK'); print(' Feedback:', m.Feedback); print(' methods:', [x for x in dir(m.Feedback) if not x.startswith('__')])" \
  && echo "L1 PASS: importable, pure-stdlib" \
  || echo "L1 FAIL: import raised (heavy dep leaked?)"
# Verify NO forbidden imports:
grep -nE 'import (cuda_check|torch|realtimestt|ctranslate2)' voice_typing/feedback.py && echo "L1 FAIL: forbidden import found" || echo "L1 PASS: no forbidden imports"
# Expected: file present; py_compile OK; import OK (lists Feedback + update_partial/set_phase/
#   record_final/set_listening/_write/_notify); no forbidden imports.
```

### Level 2: Unit Tests (the committed suite — this task's required deliverable)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# Just this module's tests (subprocess.run + time.monotonic mocked; no real hyprctl, no sleeps):
"$PY" -m pytest tests/test_feedback.py -v
# Then the FULL suite to prove nothing else regressed (expect 69 prior + new feedback tests):
"$PY" -m pytest -q
# Expected: all pass. If a throttle/transition test fails, re-read Gotcha #5/#6/#7 and the
#   _Clock/transition logic. If an argv test fails, re-read the hyprctl argv in Task 3 verbatim.
```

### Level 3: Integration smoke (real status.sh + atomic write + Feedback wiring)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
RUNTIME=$(mktemp -d); export XDG_RUNTIME_DIR="$RUNTIME"

# 3a — status.sh against a listening state (prints the partial, truncated to 60).
"$PY" - <<'PY'
import os, json
d = os.path.join(os.environ["XDG_RUNTIME_DIR"], "voice-typing")
os.makedirs(d, exist_ok=True)
json.dump({"listening": True, "phase": "speaking", "partial": "this is what i am say",
           "last_final": "", "ts": 1.0}, open(os.path.join(d, "state.json"), "w"))
PY
out=$(./voice_typing/status.sh); echo "3a listening -> [$out]"
test "$out" = "🎤 this is what i am say" && echo "3a PASS" || echo "3a FAIL"

# 3b — status.sh when not listening (empty line, exit 0).
"$PY" - <<'PY'
import os, json
d = os.path.join(os.environ["XDG_RUNTIME_DIR"], "voice-typing")
json.dump({"listening": False, "phase": "idle", "partial": "x", "last_final": "", "ts": 1.0},
          open(os.path.join(d, "state.json"), "w"))
PY
out=$(./voice_typing/status.sh); rc=$?
test -z "$out" && test "$rc" -eq 0 && echo "3b PASS (empty, exit 0)" || echo "3b FAIL: [$out] rc=$rc"

# 3c — status.sh when the state file is MISSING (must NOT abort; empty + exit 0).
rm -f "$RUNTIME/voice-typing/state.json"
out=$(./voice_typing/status.sh); rc=$?
test -z "$out" && test "$rc" -eq 0 && echo "3c PASS (missing file -> empty, exit 0)" || echo "3c FAIL: [$out] rc=$rc"

# 3d — status.sh truncates a long partial to 60 chars (UTF-8: 🎤 counts as 1 char).
"$PY" - <<'PY'
import os, json
d = os.path.join(os.environ["XDG_RUNTIME_DIR"], "voice-typing")
json.dump({"listening": True, "phase": "speaking", "partial": "w"*200, "last_final": "", "ts": 1.0},
          open(os.path.join(d, "state.json"), "w"))
PY
out=$(./voice_typing/status.sh)
# "🎤 " (3 chars incl trailing space) + 57 w's = 60 chars
test "${#out}" -le 60 && echo "3d PASS (len=${#out}, <=60)" || echo "3d FAIL: len=${#out}"

# 3e — REAL Feedback round-trip via the actual XDG path (proves resolved_state_file + atomic write).
"$PY" - <<'PY'
from voice_typing.config import FeedbackConfig
from voice_typing.feedback import Feedback
fb = Feedback(FeedbackConfig())          # state_file="" -> resolved_state_file() -> $XDG/state.json
fb.set_listening(True); fb.update_partial("real partial"); fb.record_final("Real final.")
import json, os
st = json.load(open(os.path.join(os.environ["XDG_RUNTIME_DIR"], "voice-typing", "state.json")))
assert st["listening"] is True and st["partial"] == "real partial" and st["last_final"] == "Real final.", st
import glob
assert glob.glob(os.path.join(os.environ["XDG_RUNTIME_DIR"], "voice-typing", ".state.*.tmp")) == [], "tmp litter"
print("3e PASS: real Feedback round-trip + atomic (no tmp litter)")
PY

rm -rf "$RUNTIME"
# Expected: 3a–3e each print PASS. status.sh works against the real jq+cut; the Feedback writes
#   through the real resolved_state_file() with no temp-file litter.
```

### Level 4: Creative & Domain-Specific Validation

```bash
cd /home/dustin/projects/voice-typing
# SCOPE GUARD — confirm ONLY the 3 expected files were created (+ status.sh executable).
test -f voice_typing/feedback.py && echo "L4 ok: feedback.py present" || echo "L4 FAIL"
test -x voice_typing/status.sh && echo "L4 ok: status.sh present + executable" || echo "L4 FAIL: status.sh missing/not executable"
test -f tests/test_feedback.py && echo "L4 ok: test_feedback.py present" || echo "L4 FAIL"
git status --porcelain
# Expected untracked: ?? voice_typing/feedback.py  ?? voice_typing/status.sh  ?? tests/test_feedback.py
# Any modification to config.py/textproc.py/typing_backends.py/config.toml/pyproject.toml/uv.lock/PRD.md
#   is a SCOPE VIOLATION.

# DOMAIN NOTE — real hyprctl popups are intentionally NOT asserted in unit tests (they would spam
#   the user's screen during the test run). The 3a–3e smokes prove the state-file + status.sh path
#   for real; the argv is pinned by the mocked tests. A manual sanity check (optional, under Hyprland):
#     hyprctl notify -1 2500 "rgb(88c0d0)" "● listening"   # should show a popup
#   This is the SAME argv feedback._notify emits.
```

## Final Validation Checklist

### Technical Validation

- [ ] `.venv/bin/python -m py_compile voice_typing/feedback.py` → exit 0.
- [ ] `import voice_typing.feedback` succeeds; grep finds NO `cuda_check`/`torch`/`realtimestt`/`ctranslate2` imports.
- [ ] `.venv/bin/python -m pytest tests/test_feedback.py -v` → all pass.
- [ ] `.venv/bin/python -m pytest -q` → full suite green (prior 69 + new feedback tests).
- [ ] L3 status.sh smokes 3a–3e each print PASS (listening/not-listening/missing-file/60-char-trunc/real-round-trip).
- [ ] L4 scope guard: ONLY `voice_typing/feedback.py`, `voice_typing/status.sh` (executable), `tests/test_feedback.py` created; no other edits.

### Feature Validation

- [ ] State-file JSON shape is exactly `{listening, phase, partial, last_final, ts}` with a float `ts` (PRD §4.6).
- [ ] Atomic write: no `.state.*.tmp` files linger; concurrent `json.load` never fails; file mode `0o600`, dir `0o700`.
- [ ] `update_partial` throttled to ≥10 Hz (min 0.1 s via `time.monotonic`); in-memory partial always updated; first call writes.
- [ ] `set_phase`/`record_final`/`set_listening` always write (un-throttled).
- [ ] hyprctl argv is exactly `["hyprctl","notify","-1",str(notify_ms),"rgb(88c0d0)",msg]`; `check=False`; stdout+stderr → `DEVNULL`.
- [ ] Notify messages: start `● listening`, final `✔ <text>`, stop `■ stopped`.
- [ ] `update_partial` and `set_phase` NEVER invoke hyprctl (anti-spam contract).
- [ ] Notifications fire only when `hypr_notify=True` and only on an actual `listening` transition.
- [ ] `_notify` swallows `OSError` + `subprocess.SubprocessError` (missing binary / non-Hyprland).
- [ ] `status.sh` prints `🎤 <partial>` when listening else empty; missing/malformed file → empty + exit 0; truncates to 60 chars.

### Code Quality Validation

- [ ] `feedback.py` module docstring mirrors `typing_backends.py`'s structure (CONSUMES / CONSUMED BY / thread-safety / purity / notification-discipline sections; PRD cross-refs not duplication).
- [ ] `from __future__ import annotations`; stdlib-only + the single `FeedbackConfig` import.
- [ ] `_PARTIAL_WRITE_MIN_INTERVAL = 0.1`, `_HYPR_ICON = "-1"`, `_HYPR_COLOR = "rgb(88c0d0)"` module constants.
- [ ] `status.sh` has `#!/bin/sh`, no `set -e`, jq `//` defaults, `cut -c1-60`, and the tmux integration snippet in its header comment.
- [ ] File placement matches the desired tree (`voice_typing/feedback.py`, `voice_typing/status.sh`, `tests/test_feedback.py` only).
- [ ] No new dependencies; no edits to `pyproject.toml`/`uv.lock`.

### Documentation & Deployment

- [ ] `feedback.py` docstring documents the state shape, the notification discipline (start/final/stop ONLY — PRD §4.6 inline example superseded), the throttle, atomic write, thread safety, and the daemon consumer contract.
- [ ] `status.sh` header comment documents the tmux `status-interval` + `status-right` snippet (item DOCS: Mode A) — install.sh (P1.M6.T1.S1) prints the same snippet.
- [ ] No new env vars, no new config keys (the `[feedback]` table is owned by P1.M2.T1.S2).

---

## Anti-Patterns to Avoid

- ❌ Don't notify per partial — PRD §4.6's inline `hyprctl notify ... "<partial>"` example is SUPERSEDED; partials go to state.json only, popups are start/final/stop only.
- ❌ Don't make `set_phase` notify — VAD phase flips are not start/final/stop events; notifying them would violate the anti-spam rule.
- ❌ Don't put the tempfile outside the target directory — `os.replace` is only atomic same-filesystem; always `tempfile.mkstemp(dir=target_dir, ...)`.
- ❌ Don't `os.chmod` the state file — `mkstemp`'s `0o600` is inherited by the rename; just don't clobber it.
- ❌ Don't use `time.time()` for the throttle clock — it can jump backward on NTP and freeze the partial; use `time.monotonic()` (`time.time()` is only for the `ts` field).
- ❌ Don't throttle the in-memory partial update — update memory first, then decide whether to flush; otherwise the latest words are dropped.
- ❌ Don't fire start/stop popups on a no-op `set_listening` — only notify on an actual value transition (else daemon startup spams "stopped").
- ❌ Don't let `hyprctl` raise — `check=False` + DEVNULL + `except (OSError, SubprocessError)`; a notification failure must never crash the daemon.
- ❌ Don't use a hyprctl icon other than `-1` — `-1` = "No icon"; the glyph in the message IS the visual.
- ❌ Don't `set -e` in `status.sh` — a failure must print empty + exit 0, never abort (tmux would show an error string).
- ❌ Don't use `cut -b1-60` (bytes) — it can split a multibyte char; `cut -c1-60` (chars) treats 🎤 as 1 char.
- ❌ Don't import cuda_check/torch/realtimestt into feedback.py — keep it pure-stdlib (test/CPU-loadable).
- ❌ Don't add a `threading.Lock` — `_state` dict updates + tempfile/os.replace are already atomic; a lock is dead weight and a deadlock risk.
- ❌ Don't skip the test file — this task (P1.M3.T2.S1) is combined impl+test; `tests/test_feedback.py` is a required deliverable.
- ❌ Don't run `mypy` — it is not installed (would fail); py_compile + pytest are the authoritative gates.
- ❌ Don't reference `/usr/bin/tmux` here — feedback.py has no tmux dependency (that's typing_backends' concern).

---

## Confidence Score

**9/10** for one-pass implementation success.

Rationale: the module is ~110 lines of straightforward stdlib (atomic write via tempfile+os.replace, a monotonic-clock throttle, a guarded fire-and-forget subprocess, and a small state dict). Every fact is pinned and verified LIVE in `research/feedback_hyprctl_jq_verification.md`: hyprctl `notify --help` → icon `-1` = "No icon"; the jq query + `cut -c1-60` char-truncation table; mkstemp same-dir atomicity + `0o600`/`0o700` modes; the `time.monotonic` throttle clock; and the exact test seams (monkeypatch `subprocess.run` + `time.monotonic`, `tmp_path` round-trip) mirrored from the landed `tests/test_typing_backends.py`. The `FeedbackConfig` consumed contract (incl. `resolved_state_file()`) already exists and is tested. The committed test suite (Task 5) pins the behavior deterministically with no real I/O or timing flakiness, and the L3 smokes prove `status.sh` + the real atomic write end-to-end. The −1 reserves: (a) the exact stop-message wording (`"■ stopped"`) is a minor judgment call not pinned by the PRD/item (the research lists `■` as the stop glyph but not the trailing word); (b) real hyprctl popup rendering under Hyprland is validated only manually (the argv is pinned by mocked tests — intentional, to avoid screen-spam during the test run); and (c) the `set_phase`-never-notifies interpretation resolves the item's ambiguous "may notify on listening transitions" wording per the hard start/final/stop-only constraint — it is well-justified but not verbatim from the item.

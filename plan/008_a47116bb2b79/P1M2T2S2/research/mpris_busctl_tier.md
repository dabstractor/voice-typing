# Research — MPRIS tier via busctl (P1.M2.T2.S2 / PRD §4.2quinquies, D1)

Pins the exact argv forms, parsing rules, safety gates, and the test design for the busctl-backed
MPRIS ducking backend. Sources: `architecture/external_tech_notes.md` §3 (verified forms + the
playerctl prohibition), `architecture/d1_ducking_seams.md` §1e/§5/§6, the S1 contract
(`P1M2T2S1/PRP.md` — landed, verified live), and the live tree.

## 1. Contract inputs (all verified)

### 1.1 S1's landed protocol (`voice_typing/audio_ducking.py` — exists at HEAD, API verified by grep)
- `PlayerState` frozen dataclass: `name: str`, `playing: bool` (L36).
- `DuckBackend` runtime_checkable Protocol (L44-57): `list_players() -> list[PlayerState]`,
  `pause_player(name) -> bool`, `resume_player(name) -> bool`, `get_sink_volume_pct() -> float | None`,
  `set_sink_volume_pct(pct) -> bool`. Contract: bounded ≤1 s, best-effort, NEVER raises.
- `AudioDucker` (L60) owns ALL sovereignty bookkeeping: engage pauses only `playing` players into a
  ledger of successful pauses; release resumes ledger ∧ still-present (`fresh list_players()` map,
  L135) ∧ not-currently-playing (L141-142). **S2's backend provides ONLY the three MPRIS primitives —
  no ledger, no sovereignty logic in the backend** (that would duplicate S1).
- S1's module is **stdlib-only** (imports: logging/threading/dataclasses/typing — verified). The
  subprocess import therefore CANNOT go there → S2 lands its own module (also keeps S1/S2 disjoint
  while S1's tests are still landing).

### 1.2 Exact busctl argv forms (external_tech_notes.md §3.3 — the contract's prescribed forms)
```
List:    busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ListNames
Status:  busctl --user get-property <name> /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player PlaybackStatus
CanPause:busctl --user get-property <name> /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player CanPause
Pause:   busctl --user call <name> /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player Pause
Play:    busctl --user call <name> /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player Play
```
`<name>` = a well-known bus name under `org.mpris.MediaPlayer2.*`.

### 1.3 Environment facts (seams §6, verified on this host)
- `/usr/bin/busctl` present; `playerctl` v2.4.1 also present but **NOT used** (see §2.1).
- NO python D-Bus bindings in `.venv` (`dbus`, `gi` both absent) → subprocess argv is the only route
  without new deps. Confirms the contract's RESEARCH NOTE.

### 1.4 Subprocess discipline precedent (seams §1e)
- ZERO existing `subprocess.run(..., timeout=)` in `voice_typing/` — `timeout=1.0` is a NEW pattern,
  explicitly blessed by seams §1e: copy `feedback.py:247-261 _notify`'s swallow shape
  (check=False, DEVNULL, try/except (OSError, SubprocessError) — TimeoutExpired is a SubprocessError)
  and add `timeout=1.0`.
- Absolute binary path convention: `typing_backends.py` `_TMUX = "/usr/bin/tmux"` (zsh aliases) →
  use `_BUSCTL = "/usr/bin/busctl"`.

## 2. Design decisions

### 2.1 busctl only — playerctl is forbidden for this tier
Tech-notes §3.4 + the contract FORBID `playerctl --all-players pause` + bare `play`: `--all-players`
acts on the set present at invocation (a late player is missed) and a bare `play` targets the
most-recently-active player only — unsafe for exact restore. Decision: **busctl exclusively**, even
for individual ops. The tracked-pause-set bookkeeping is S1's ducker; the backend is stateless.

### 2.2 New module `voice_typing/ducking_mpris.py` (disjoint from S1's file)
S1 owns `audio_ducking.py` (stdlib-only; its scope guard pins `git status` to its 2 files) — S2
editing it would conflict with the parallel S1. A separate `ducking_mpris.py` holds
`MprisBusctlBackend` (+ the local `import subprocess`). S3 later lands `ducking_wpctl.py` the same
way. T3 wires `AudioDucker.from_config(cfg, MprisBusctlBackend())`.

### 2.3 Safety gates (the load-bearing details)
- **pause_player: respect CanPause.** Read `CanPause` first (`b true`/`b false`). `false` or the read
  fails (player gone) → return False, NO Pause call → the ducker never ledgers it (rule (a)/(b)).
- **resume_player: Play() ONLY on exactly "Paused" — never restarts a Stopped player.**
  Tech-notes §3.1: "Play() on a stopped player restarts — resume with Play() only what you paused".
  The ducker's rule (c) checks not-currently-playing, which conflates Paused and Stopped; if the
  user STOPPED a player we had paused, a bare Play() would restart it = fighting the user. The
  backend re-reads PlaybackStatus and issues Play() ONLY when it is exactly `Paused`. This is
  belt-and-suspenders on top of S1's rule (c) and closes the restart hazard. (Also covers the race
  where the user resumes between the ducker's fresh list and the resume call → no double-play.)
- **PlayerState.playing** = (PlaybackStatus == "Playing") exactly.

### 2.4 Failure discipline (PRD: one line, never a gate)
`_run(argv)` helper (all busctl calls go through it):
- `subprocess.run([_BUSCTL, *argv], timeout=1.0, check=False, stdout=PIPE, stderr=DEVNULL, text=True)`.
- `TimeoutExpired` / `OSError` / `SubprocessError` → **ONE WARNING** line, return `None`. (The ducker's
  `_call` additionally swallows anything the backend lets escape — defense in depth.)
- `rc != 0` → **one DEBUG** line, return `None`. Per-player nonzero is NORMAL churn (a name vanishing
  between ListNames and the property read; mpd/browser tabs appear+vanish constantly — tech-notes
  §3.4); WARNING per player per engage would spam the journal.
- Callers map `None` → the safe default: list_players omits that player / returns `[]`;
  pause/resume return False.

### 2.5 Volume methods = documented protocol stubs
The protocol has 5 methods; S2's backend implements the 3 MPRIS ones and stubs the 2 volume ones
(`get_sink_volume_pct -> None`, `set_sink_volume_pct -> False`, one DEBUG) so the class is fully
`DuckBackend`-conformant (runtime_checkable isinstance holds); `mode="mpris"` never calls them, and
S3's wpctl backend owns the real ones. 4 lines, honestly documented — not dead weight.

### 2.6 Latency shape (context, not S2's problem to fix)
`list_players` = 1 ListNames + N per-name status reads (sequential, each ≤1 s). Engage latency is
bounded by T3 (engage runs on a spawned thread; the arm never waits) and S4 (the hardening task).
The docstring notes this explicitly so nobody "fixes" it by caching state in the backend.

## 3. busctl output parsing (exact forms + robust regexes)

| Call | stdout shape | Parse |
|---|---|---|
| ListNames | `as 42 "org.mpris.MediaPlayer2.mpd" "org.freedesktop.DBus" ...` | regex `org\.mpris\.MediaPlayer2\.[A-Za-z0-9_.]+` (inside quotes; robust to count token/line wrapping) |
| PlaybackStatus | `s "Playing"` (or Paused/Stopped) | regex `"(Playing\|Paused\|Stopped)"` |
| CanPause | `b true` / `b false` | regex `\b(true\|false)\b` |
| Pause / Play | (empty), rc 0 | rc 0 == success |

Regex-over-whole-stdout (not token splitting) is version-robust: busctl may print the array count
and wrap long lines; the quoted-name pattern is stable.

## 4. Test design (`tests/test_ducking_mpris.py` — fakes only, no busctl, no audio)

Fake the runner the way `tests/test_typing_backends.py`'s `_Recorder` does: monkeypatch
`ducking_mpris.subprocess.run` with a callable that pattern-matches argv and returns a canned
`subprocess.CompletedProcess(argv, rc, stdout=...)` (or raises `TimeoutExpired`/`OSError`). The
backend is exercised end-to-end through its own `_run` → parsing is under test.

14 tests:
1. `test_list_players_parses_names_and_status` — canned ListNames + per-name statuses → exactly the
   MPRIS PlayerStates with the right `playing` flags.
2. `test_list_players_ignores_non_mpris_names` — org.freedesktop.* / org.bar names never appear.
3. `test_list_players_omits_player_whose_status_read_fails` — rc!=0 on one name → omitted, no raise.
4. `test_list_names_failure_returns_empty_with_one_warning` — ListNames rc!=0 → `[]`, ONE WARNING.
5. `test_pause_player_exact_argv_and_success` — CanPause `b true` → the Pause call fires with the
   EXACT argv from §1.2; returns True.
6. `test_pause_player_respects_can_pause_false` — `b false` → NO Pause call, returns False.
7. `test_pause_player_canpause_unreadable_skips` — CanPause read fails → False, no Pause call.
8. `test_resume_player_plays_when_paused` — status `Paused` → Play call (exact argv), True.
9. `test_resume_player_never_restarts_stopped` — status `Stopped` → NO Play call, False
   (**pins tech-notes §3.1** — the restart hazard).
10. `test_resume_player_skips_already_playing` — status `Playing` → no call, False (race guard).
11. `test_timeout_swallowed_into_one_warning` — run raises `TimeoutExpired` → safe default, exactly
    ONE WARNING in caplog, nothing propagates.
12. `test_missing_binary_swallowed` — run raises `OSError` → same discipline.
13. `test_volume_methods_are_stubs` — return None/False, zero busctl calls (call_log empty).
14. `test_case_a_tier_pin_through_real_ducker` — **the PRD case-(a) pin at the TIER level**:
    `AudioDucker(MprisBusctlBackend(...), mode="mpris")` over the fake runner. Players A(Playing),
    B(Paused), C(Playing). engage → Pause called for A and C only. Mid-dictation the fake mutates:
    A → Playing (user resumed), B → Paused-stays, D appears Playing (user started a NEW player —
    never touched at release because not in the ledger). release → Play called ONLY for C.
    (Import from `voice_typing.audio_ducking` — S1's landed contract file.)

## 5. Scope + validation

- Files: NEW `voice_typing/ducking_mpris.py` + NEW `tests/test_ducking_mpris.py`. Nothing else.
  No edits to `audio_ducking.py` (S1's), daemon.py (T3), config.py (landed), feedback.py.
- Gate: `timeout 300 .venv/bin/python -m pytest tests/test_ducking_mpris.py -q` (14 passed);
  `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → no NEW
  failures beyond the recorded G1 classification (tests/G1_BASELINE.md).
- Live read-only smoke (never Pause/Play the user's real music): construct the backend, call
  `list_players()` once against the real session bus, journal what it found; rc!=0 (headless session)
  is also an acceptable smoke result — it exercises the swallow path.
- AGENTS.md: every command under `timeout` (inner) + bash-tool timeout (outer); full tool paths.

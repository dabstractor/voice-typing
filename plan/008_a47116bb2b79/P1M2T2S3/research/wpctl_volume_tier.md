# Research — Volume tier: wpctl snapshot + conditional restore (P1.M2.T2.S3 / PRD §4.2quinquies, D1)

The PRP (../PRP.md) references this note as the single source of truth. Pins: S1's landed protocol
(verified by read), the exact wpctl argv/grammar (LIVE-verified this run, upgrading the tech notes'
medium-high confidence to observed), the node-id state machine, the mute decision, the subprocess
discipline, and the test matrix.

## 0. Contract inputs (all verified)

- **S1 LANDED**: `voice_typing/audio_ducking.py` (183 lines) + `tests/test_ducking.py` (250 lines)
  exist in the working tree. Protocol (verified by grep @53-57):
  `get_sink_volume_pct() -> float | None` (PCT — ducker-side compare uses `_VOL_EPS = 0.5` pct
  @32, `audio_ducking.py:168`), `set_sink_volume_pct(pct) -> bool`, plus the 3 MPRIS primitives.
  The DUCKER owns all bookkeeping (snapshot ledger, compare-before-restore @160-176); the tier is
  primitives only (the S2 precedent). Ducker volume sequences (verified @148-176):
  - engage: `get()` → if None: warn+skip; else `set(duck_pct)`; snapshot stored only on set-True.
  - release: `get()` → if None: warn, keep; elif `abs(current - duck_pct) > 0.5`: INFO "keeping
    user value", NO write; else `set(snapshot)`.
  So the backend observes EXACTLY this call grammar per session: `get, set(D) [, get, set(V0)]`.
- **S2 (parallel, same shape)**: `voice_typing/ducking_mpris.py` + `tests/test_ducking_mpris.py`
  (fake-runner tests, monkeypatched `subprocess.run`). Its volume methods are documented stubs
  (`None`/`False`, zero subprocess) with an explicit handoff comment to S3. Mirror that file's
  structure; mirror the symmetry (S3's MPRIS methods = stubs).
- **Tech notes §4** (external_tech_notes.md): grammar `Volume: <float>[ MUTED]` (§4.1); bare `15%`
  = ABSOLUTE set, `+`/`-` = relative (§4.2); float round-trips exactly; mute is independent state
  (§4.3); `@DEFAULT_AUDIO_SINK@` re-resolves per invocation → snapshot the CONCRETE node id and
  restore by id, skip gracefully if gone (§4.4 — the item's RESEARCH NOTE).
- **Item contract**: engage = read+store node id + float volume + mute state, then set
  duck_volume_pct absolute. Release = restore stored float + mute ONLY if current volume still
  equals what we last set; skip gracefully if node gone. ≤1 s timeouts; one-line failure logs.

## 1. ★ LIVE-VERIFIED wpctl facts (this run, /usr/bin/wpctl, PipeWire 1.6.x) ★

```
$ wpctl get-volume @DEFAULT_AUDIO_SINK@   → "Volume: 1.05"          # rc=0
$ wpctl get-volume 72                     → "Volume: 1.05"          # rc=0  ← numeric node id WORKS
$ wpctl get-volume 99999                  → "Node '99999' not found" # rc=0 (!!) ← GONE NODE, rc STILL 0
$ wpctl status (Sinks block):
  ├─ Sinks:
  │      39. WholeHouse              [vol: 1.00]
  │  *   72. Local Analog Stereo     [vol: 1.05]    ← default = leading '*'
  ├─ Sources:
  │  *   74. Webcam ...                             ← Sources ALSO has a '*' — scope the parse to Sinks!
```

- **CRITICAL #1 (rc lies)**: a nonexistent node returns rc=0 with `Node 'N' not found` on stdout.
  Failure detection MUST be output-grammar parse (regex `^Volume:\s*(\d+(?:\.\d+)?)`), NEVER rc.
  This directly implements the item's "skip gracefully if the node is gone".
- **Scale**: volume floats can EXCEED 1.0 (observed 1.05 = 105%). pct = float × 100; never clamp.
- **Absolute set**: `wpctl set-volume <target> 15%` — percent with NO sign prefix is absolute
  (tech notes §4.2; wpctl source semantics). Emit exactly `f"{pct:.0f}%"` — never `+`/`-`.
- **set-by-id**: same target slot accepts the numeric node id (verified for get; set shares the
  target grammar — wpctl.c parses the object spec once). Belt-and-suspenders: the fake-runner tests
  pin the argv; a live `set` is FORBIDDEN in validation (it would mutate the user's real volume).

## 2. The node-id state machine (the §4.4 fix, protocol-compliant)

The frozen DuckBackend protocol has no node-id/mute/engage parameters — so the tier itself is
STATEFUL about the node, driven purely by the ducker's observable call sequence
(`get, set(D) [, get, set(V0)]` per session). Sequence-driven, NOT value-driven (works even in the
degenerate `D == V0` case, e.g. sink already at 15%):

```python
class WpctlVolumeBackend:            # implements DuckBackend
    _node: int | None = None         # the pinned (engaged) sink node id
    _ducked: bool = False            # True between the engage-set and the release-set
    _muted_at_engage: bool | None = None   # diagnostics only — see §3

    def get_sink_volume_pct(self) -> float | None:
        if self._ducked and self._node is not None:
            target = self._node                     # release-time compare: read the DUCKED node
        else:
            self._node = self._resolve_default_node()   # engage-time: pin the CONCRETE id
            target = self._node if self._node is not None else "@DEFAULT_AUDIO_SINK@"
        out = self._run(["wpctl", "get-volume", str(target)])
        m = re.match(r"^Volume:\s*(\d+(?:\.\d+)?)", out or "")
        if m is None:
            # Node-gone self-heal: a pinned-but-dead node (output "Node 'N' not found", rc==0)
            # → clear the pin so the NEXT get re-resolves the (possibly new) default.
            if self._ducked and self._node is not None:
                logger.info("ducking(volume): sink node %s gone; unpinning", self._node)
                self._node, self._ducked = None, False
            return None
        self._muted_at_engage = "[MUTED]" in (out or "") if not self._ducked else self._muted_at_engage
        return float(m.group(1)) * 100.0

    def set_sink_volume_pct(self, pct: float) -> bool:
        target = str(self._node) if self._node is not None else "@DEFAULT_AUDIO_SINK@"
        ok = self._run_ok(["wpctl", "set-volume", target, f"{pct:.0f}%"])
        if ok:
            self._ducked = not self._ducked if (self._ducked or pct is not None) else self._ducked
            # sequence semantics: engage-set → ducked=True; release-set → ducked=False, clear pin
            if not self._ducked:
                self._node = None
            else:
                self._ducked = True
        return ok
```

(Rationale, spelled out for the implementer: `set` is called exactly twice per full session —
engage `set(D)` and release `set(V0)`. The FIRST successful set of a session marks `_ducked=True`
(the get before it pinned the node); the SECOND successful set marks `_ducked=False` and clears the
pin so the next engage re-resolves the default. `get` while `_ducked` reads the PINNED node so the
ducker's compare-before-restore compares the ducked device's volume (not a newly-selected sink) and
the restore targets the ducked device by id — the §4.4 hazard fixed. If the user changed volume
mid-dictation the ducker makes NO release set: `_ducked` stays True and the pin stays — benign: the
next engage's `get` reads the pinned (still-ducked, still-at-D) node, the engage-set re-marks it,
and the next COMPLETED release restores it; a stale pin also self-heals via the node-gone path.)

State table (the tests pin each row):

| sequence (ducker view) | backend state after | effect |
|---|---|---|
| get (fresh) | node=defN, ducked=False | pins default, returns vol(N) pct |
| get, set(D) | node=defN, ducked=True | D applied to defN by id |
| get, set(D), get | (unchanged) | reads defN (pinned) even if default changed |
| get, set(D), get, set(V0) | node=None, ducked=False | V0 restored to defN by id; re-pin next engage |
| get, set(D), get(user-changed → no set) | node=defN, ducked=True | no write (ducker rule); pin persists, self-heals later |
| get, set(D), get(node gone → None) | node=None, ducked=False | ducker warns + keeps; pin cleared → next get re-resolves |

## 3. Mute decision (documented, load-bearing)

The tier **never issues a `set-mute` call**. `wpctl set-volume` does not touch mute (tech notes
§4.3: mute is independent node state), so during a duck the mute state CANNOT change by our hand —
restoring it is structurally a no-op. Snapshotting `_muted_at_engage` (from the `[MUTED]` suffix)
is kept for the one-line engage log and as a guard: if the sink was muted at engage it stays muted
at restore — and if the USER muted/unmuted mid-dictation, writing mute back would fight them (the
exact sovereignty violation §4.2quinquies forbids). The item's "restore stored ... mute" is
satisfied vacuously-and-safely: we restore exactly what we changed (volume only). Record this as a
non-defect nuance so nobody "completes" it with a set-mute pair.

## 4. Subprocess discipline (mirror S2 / seams §1e)

```python
def _run(self, argv: list[str]) -> str | None:
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=1.0, check=False, stderr=subprocess.DEVNULL)
        return r.stdout.strip() if r.returncode == 0 else None   # NOTE: rc==0 can still be a parse miss — caller regexes
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
        logger.warning("ducking(volume): %s failed; continuing", argv[0])   # ONE line, no traceback
        return None
```
- `timeout=1.0` (item: "≤1 s"), `check=False`, `stderr=DEVNULL`, never raises.
- `wpctl status` (default-node resolve) uses the same helper (status is the slowest call — still ≤1 s).
- Third `import subprocess` site lives in `ducking_mpris.py` (S2); S3 adds the fourth in its own
  module — S1's `audio_ducking.py` stays stdlib-only (verified: no subprocess there).

## 5. Default-node resolution (`wpctl status` parse)

Scope to the **Sinks block** (the Sources block has its own `*` — live-observed):
```python
def _resolve_default_node(self) -> int | None:
    out = self._run(["wpctl", "status"])
    if out is None: return None
    in_sinks = False
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Sinks:"): in_sinks = True; continue
        if s.startswith("Sources:"): break            # block ended
        if in_sinks and s.startswith("*"):
            m = re.match(r"\*\s+(\d+)\.", s)          # "*   72. Local Analog Stereo ..."
            if m: return int(m.group(1))
    return None                                      # no default marker → caller falls back to the selector
```
Fallback when resolve fails: use `@DEFAULT_AUDIO_SINK@` for the get (still correct for a one-shot
read) — but note a set then targets the selector (the §4.4 hazard, degraded not broken; log DEBUG).

## 6. Exact argv forms (tests pin them byte-for-byte)

```
read:  ["wpctl", "get-volume", "<node-id>|@DEFAULT_AUDIO_SINK@"]
set:   ["wpctl", "set-volume", "<node-id>|@DEFAULT_AUDIO_SINK@", "15%"]   # absolute, NO +/- prefix
list:  ["wpctl", "status"]                                                 # default-node resolve only
```

## 7. Test matrix (tests/test_ducking_volume.py — fake runner, monkeypatched subprocess.run; ZERO real wpctl in unit tests)

`_FakeRunner(records argv, returns canned stdout/rc/raise)`; `_Backend = WpctlVolumeBackend`.
1. `test_parse_volume_basic` — "Volume: 0.65" → 65.0; argv == get-volume + selector (no prior state).
2. `test_parse_volume_muted_suffix` — "Volume: 0.65 [MUTED]" → 65.0; `_muted_at_engage` True; set-mute NEVER in argv log.
3. `test_parse_volume_above_unity` — "Volume: 1.05" → 105.0 (live-observed; no clamp).
4. `test_gone_node_returns_none_rc0` — stdout "Node '99999' not found", rc=0 → None (Critical #1);
   pinned-gone path also clears the pin (next get re-resolves).
5. `test_resolve_default_node_scoped_to_sinks` — canned status (with a `*` in Sources @74) → returns
   72 (the Sinks `*`), never 74.
6. `test_resolve_no_default_marker` — status without `*` in Sinks → get falls back to the selector argv.
7. `test_engage_pins_node_and_sets_absolute` — get(default→72) then set(15): set argv target "72",
   value "15%" (no sign); state node=72, ducked=True.
8. `test_release_restores_by_pinned_id` — full session get,set(15),get,set(50): final argv target
   "72", value "50%"; pin cleared, ducked=False.
9. `test_release_read_uses_pinned_node_not_new_default` — mid-session swap the canned status (default
   now 82): the release `get` argv target is still "72".
10. `test_timeout_swallowed_one_warning` — runner raises TimeoutExpired → None/False; exactly ONE
    warning in caplog; nothing propagates.
11. `test_mpris_stubs_zero_subprocess` — list_players()==[], pause/resume → False; zero argv entries.
12. `test_case_b_end_to_end_user_changed_volume_no_write` — ★ the PRD case-(b) pin through S1's REAL
    AudioDucker + this backend + fake runner: engage (vol 50 → set 15); fake mutates volume to 80
    (release get returns 80); release → NO restore write in the argv log (last set is still the 15%
    engage set) + ducker INFO "keeping user value".
13. `test_case_b_variant_node_gone_at_release` — release get returns "Node ... not found" → no set,
    one ducker warning, backend pin cleared.
14. `test_degenerate_duck_equals_original` — original volume == 15% == duck: full session round-trips
    (set(15), set(15)); state machine still ends ducked=False, pin cleared (sequence-driven).

## 8. Tooling / validation facts

- pytest 9.x in `.venv`; run: `timeout 300 .venv/bin/python -m pytest tests/test_ducking_volume.py -q`
  (expect 14 passed); full gate `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/
  test_feed_audio.py -q` — no NEW failures beyond the G1 classification (tests/G1_BASELINE.md).
- ruff at `/home/dustin/.local/bin/ruff` (optional). mypy NOT installed. FULL tool paths (zsh aliases).
- **LIVE-SET FORBIDDEN**: any `wpctl set-volume` against the real machine in validation would
  mutate the operator's audio. Live probes are READ-ONLY (get-volume/status — both used in §1).
  The live end-to-end (music-volume duck + restore) is T4's acceptance evidence, not this task's.
- AGENTS.md Rule 1: every command under `timeout` (inner) + bash-tool timeout (outer).

## 9. Scope (do / don't)

DO: CREATE `voice_typing/ducking_volume.py` (`WpctlVolumeBackend` + `_run` + `_resolve_default_node`
+ MPRIS stubs) and `tests/test_ducking_volume.py` (14 fake-runner tests). Mirror S2's
`ducking_mpris.py` module/test structure exactly.

DON'T: edit `audio_ducking.py`/S1 tests (protocol frozen), `ducking_mpris.py` (S2 owns; its volume
stubs stay), daemon.py/config/feedback/systemd (T3/T4), PRD/tasks.json/prd_snapshot/.gitignore.
No new deps (subprocess+re+logging only). No live `wpctl set-volume` runs. DOCS: none (Mode A
module docstring carries the design, mirroring S1/S2).

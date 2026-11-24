# S5 research — Qualify a private Pi prompt frame observation

Verified in-tree at HEAD (post-S4 landing). All anchors grep-stable via named symbols.

## 1. The gap S5 closes

- `tests/g5_timing_lab.py:PiGhosttyRoute._poll_loop` (:526-557) samples the EDITOR's socket
  state every 10 ms and writes `(t_mono, t_wall, text)` to `field_timing.jsonl`. The route
  docstring (:403-406) and `preflight_note()` (:631) already admit: "the extension exposes no
  render callback — the poll IS the editor's read op". Architecture doc (§ G5): "pi-ghostty:
  extension/editor read is currently polled ~10 ms; field state **is not actual Ghostty
  rendering**. Record instrument precision/scope; get qualified independent changed-frame
  evidence in the private route if feasible, otherwise explicitly mark any frame-specific gate
  unverified and BUG-002 open. No invented frame or cross-route pass."
- `.pi/extensions/voice-editor.ts` (428 lines, harness-owned; copied by boot into
  `proj/.pi/extensions/`): insert/replace mutate editor model and schedule render via
  `setTimeout(0)`; there is NO render-completed callback — nothing in the protocol certifies
  when Ghostty painted. Ops are closed-set `insert|replace|cancel|read`
  (voice_typing/pi_editor.py:259). Insert/replace REFUSE when `!owned` ("range not owned") —
  the harness cannot manufacture a text change through the socket; probes must go through the
  terminal's own input path (wtype keystrokes into the focused private window).
- HOME isolation gap: `boot()` (:416-458) spawns ghostty with `env` = os.environ minus
  LD_LIBRARY_PATH — real HOME survives → pi loads operator agent config/extensions/sessions
  from `~/.pi*`. Architecture mandate: "Before measuring Pi, isolate its agent/config/state and
  restrict extensions to the harness-owned fixture; a real HOME used only to locate binaries
  must not load live operator sessions/extensions. If that can't be safely arranged, block that
  route and record it." `pi_bin` is resolved in the PARENT (`PI_BIN` env or `shutil.which`) —
  never needs the child's HOME.

## 2. In-tree contracts S5 consumes (READ-ONLY)

- S3 landed (`tests/g5_timing_support.py`): `FieldEvent` (:75, `t` = field's own change ts),
  `ReadyEvent` (:84, `ack_ts` = "target APPLIED cross-check ONLY — never a frame (R.5 #3)"),
  `ReplayRecord` provenance fields (`partial_source`, `anchor_text`, `capped`, `heartbeats`),
  `changed_spans(old, new)` (S3 changed-span core — reusable for insert-vs-correction
  classification), `attribute_updates` labels (matched/missing/superseded/no_op/ambiguous;
  orphan frames `unpaired`), `MAX_REPORT_LINES = 120` (:1019).
- S4 landed (`tests/g5_timing_lab.py`): `--partial-source` both parsers; `start_daemon(smoke,
  factory, partial_source=None)` materializes `or "stabilized"` at the daemon seam (:719-744);
  `_resolve_partial_source` fail-closed provenance (:746+); `wrap_ready` ReadyEvent stamping;
  `FieldLog.anchor_text()`; `preflight(route_name) -> str|None` blocked semantics; GTK default
  route; `tests/test_g5_timing_lab.py` (S4's suite — must stay green; it never invokes Pi
  boot, only asserts `PiGhosttyRoute(...).bulk_target_factory()` returns a callable).
- Pi route surface S5 OWNS (frozen only for S4): `boot`, `_focus_ghostty` (:460),
  `_log_editor_state` (:477), `_editor_ready` (:506), `_poll_loop` (:526), `field_log`
  (:559), `bulk_target_factory`/`_G5PiBundle`/`_CancelOnLeaveTarget` (:562-629),
  `preflight_note` (:631). PI_EXT_SRC = REPO/.pi/extensions/voice-editor.ts (:85).
- `boot_sway` (:279-292): private sway socket exported to `os.environ["SWAYSOCK"]` /
  `WAYLAND_DISPLAY` — the inner process env IS the private compositor; every observer
  subprocess must be given these EXPLICITLY (never inherit blindly).
- Smoke quirk (S4 Gotcha #9): pi `field_log()` touches `self._log_path`, set only in boot()
  → pi smoke crashes. GtkRoute sets its field-log path eagerly in `__init__` (:319 pattern);
  S5 mirrors that so pi smoke stops crashing (enables observer lifecycle testing at smoke).
- `_Lab.spawn/kill/kill_all` (:232-277): own-process-group bookkeeping — ghostty's pid is
  trackable for the window-identity guard.

## 3. Frame observation mechanism (verified available)

`/usr/bin/grim`, `/usr/bin/wtype`, `/usr/bin/swaymsg`, `/usr/bin/ghostty` all present.

- Geometry: `swaymsg -t get_tree` → JSON tree; find node `app_id == "ghostty"`; require
  EXACTLY ONE such node whose `pid` is in the lab's tracked set → `node.rect` {x,y,width,
  height} → grim geometry string `"X,Y WxH"`. Any miss (0 nodes, >1 node, pid untracked) ⇒
  observer blocked, never guess.
- Capture: `grim -g "X,Y WxH" -` writes PNG to stdout (grim(1); `-` = stdout). Digest the
  bytes (hashlib.sha256 → hex); NEVER persist pixels. sway implements wlr-screencopy on every
  backend (the lab's sway runs under the private runtime; ghostty GL-under-Xvfb already proven
  by the GTK field route), so the headless output has real composited pixels.
- Cadence: process-spawn capture costs ~10-30 ms; a ~50 ms loop is realistic. Observer
  resolution ≥ cadence + capture latency → CANNOT certify the ≤100 ms/50 ms frame bars by
  itself; that is WHY the output is "qualified/blocked", never a synthetic pass.
- Cursor blink produces periodic frame digests with NO text change — the classifier must
  label them (period-stable intervals, no field change in the ± window). Do NOT change
  ghostty render config (no `--cursor-blink=false`): the item requires DISTINGUISHING cursor
  redraw, not eliminating it.
- Calibration probes (boot-time, BEFORE warmup — outside every measured window): with wtype,
  (a) type 2-3 plain chars then Backspace them (text change + revert; must produce paired
  text/frame detections), (b) ArrowLeft/ArrowRight (cursor move: frame change, NO text
  change → the cursor-redraw discriminandum). No Enter (never submit), no ownership risk
  (boot precedes any acquire; `owned` is null). Resolution stats = per-probe
  frame_detect_t − poll_detect_t distribution, reported as observer resolution, NEVER
  subtracted from measured latencies (conservative).

## 4. Isolation design (Pi agent/config/state)

`_pi_window_env()` helper builds the ghostty+pi child env: `HOME = lab.root/"home"` (fresh
mkdir), `XDG_CONFIG_HOME/XDG_CACHE_HOME/XDG_DATA_HOME/XDG_STATE_HOME` under it, PATH
preserved, `LD_LIBRARY_PATH` stripped (existing GL/CUDA-LD recipe), `SWAYSOCK`/
`WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` passed EXPLICITLY from the inner env. pi binary discovery
already happened in the parent. The harness extension loads from `proj/.pi/extensions`
(cwd=proj) — project-local, unaffected by HOME. NO FALLBACK to real HOME, ever: if pi fails
to boot under the disposable HOME (socket never appears → boot's existing `until` raises),
the route honestly fails/blocked per the architecture mandate — never re-expose operator
state to make it boot.

## 5. Classification contract (unit-provable with mocked feeds)

Correlate (poll text transitions, frame digest changes, ReadyEvent ack_ts, anchor_text) into:
- `visible_insert` — field span-grew change (g5.changed_spans) + frame change within
  attribution window (window = max(2×cadence, 150 ms) — OBS constant, recorded per run)
- `visible_correction` — field span-rewritten change + frame change within window
- `ack_only` — ACK ts with no field change AND no frame change (proves ACK ≠ paint only when
  the observer demonstrably sees other frames)
- `unchanged` — no ack/field/frame activity in window
- `cursor_redraw` — frame change(s), no field change, interval-period-stable
- `reset` — field text returns to anchor_text equality (+ frame change); excluded from
  dictation counts (S3/S4 anchor rules) but verified painted
- `missed_below_resolution` — field change with NO frame change in window (counted, never
  imputed, never a fast sample)
- `unpaired_frame` — frame change, no field change, NOT period-stable (mirrors S3 orphan rule)

Miss rule (S3 law): a miss is a miss — excluded from latency stats, counted in the block.

## 6. Output interface for S6 / T2.S3

Artifact JSON + final stdout line gain ONE additive `frame_observer` block:
`{status: verified|unverified|blocked, reason, proxy, observer, cadence_ms_{p50,p95},
capture_ms_{p50,p95}, resolution_ms_{p50,p95}, calibration{...}, samples{...},
classes{...counts...}}`; per-record additive bounded `frame_qualified` list (≤20:
field_t/ack_ts/frame_t/class/latency_ms). Status semantics: `verified` = observer ran AND
detected ≥1 real text-correlated frame (calibration or in-run); `unverified` = ran, zero
detections; `blocked` = never ran (grim missing / geometry miss / env-identity guard tripped).
Missing grim does NOT block the ROUTE (S4 preflight untouched) — the editor poll stays a
LABELLED PROXY and frame metrics are marked unverified.

## 7. Evidence doc discipline

`tests/G5_TIMING_EVIDENCE.md`: append a new `## Pi frame observer qualification
(P1.M2.T1.S5)` section (Mode A: tools preflight, disposable-HOME isolation, resolution
numbers from the qualification run, proxy limits). Exactly ONE verdict-shaped table may exist
(g6_assessment.parse_route_verdicts overwrites duplicate route keys) — the new section must
NOT be route+verdict shaped. Historical rows/commands untouched.

## 8. External references

- grim(1): https://gitlab.freedesktop.org/wayland/grim — `-g "<x>,<y> <W>x<H>"` geometry,
  `-` writes PNG to stdout; requires wlr-screencopy (sway implements it on all backends).
- swaymsg IPC: `swaymsg -t get_tree` JSON (`man swaymsg` / sway IPC docs
  https://github.com/swaywm/sway/blob/master/meson.build# ipc docs:
  https://man.archlinux.org/man/sway-ipc.7.en) — nodes carry `app_id`, `pid`, `rect`.
- wtype(1): https://github.com/atx/wtype — Wayland virtual-keyboard typing; honors
  WAYLAND_DISPLAY of the target compositor.
- Ghostty config keys: https://ghostty.org/docs/config — cursor blink is `cursor-blink`
  (NOT changed by S5; classifier handles it).

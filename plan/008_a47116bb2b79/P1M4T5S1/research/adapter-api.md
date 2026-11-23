# Research — the REAL IM-v2 bulk-delivery adapter (P1.M4.T1–T3) and its evidence patterns

Scope of this note: everything a G3 harness (P1.M4.T5) must know about the existing
IM-v2 adapter stack, the lab-driver pattern, and the G2 evidence discipline. All paths
repo-relative under `/home/dustin/projects/voice-typing`.

---

## 1. `voice_typing/ime` package map

Five modules (`ls voice_typing/ime/`): `__init__.py`, `protocol.py`, `wlwire.py`,
`ime_host.py`, `manager.py`, `target.py`.

| Module | Role |
|---|---|
| `protocol.py` | Pure-stdlib JSONL wire contract (encode/decode/validate, `EventLogWriter`). |
| `wlwire.py` | Hand-rolled stdlib Wayland wire client (REQUESTS/EVENTS opcode tables pinned against vendored `tests/fixtures/input-method-unstable-v2.xml`). |
| `ime_host.py` | The in-compositor-seat JSONL host (`python -m voice_typing.ime.ime_host [event-log]`): becomes the seat's IM, serves acquire/show/verify/leave/ping/cancel. |
| `manager.py` | `ImeProcess`: subprocess supervisor (spawn/stop/health) for the host child, over stdin/stdout pipes. |
| `target.py` | `ImeTarget`: the daemon-side `DeliveryTarget` adapter — verified acquire, mutation-time recheck, show insert/correction. |

### Driving surface for the G3 harness

**Spawn/own the transport subprocess — `voice_typing/ime/manager.py`:**

```python
class ImeProcess:
    def __init__(self, on_delivery_state=None, on_event=None,
                 python_exe: str | None = None, log_path: str | None = None,
                 spawn_timeout: float = 10.0, stop_timeout: float = 5.0,
                 _popen=None): ...
    @property
    def state(self) -> str          # idle | starting | running | unsupported | fault
    @property
    def is_alive(self) -> bool
    def spawn(self, timeout: float | None = None) -> bool
    def request(self, cmd: str, timeout: float = 1.0, **fields) -> dict | None
    def healthy(self) -> bool
    def stop(self, timeout: float | None = None) -> None
```

- `spawn()` runs `[python_exe, "-m", "voice_typing.ime.ime_host", log_path?]` with
  `stdin/stdout=PIPE`, `start_new_session=True`; readiness = ONE id-echoing `ping`
  reply within `timeout` (default 10 s). `unavailable` event (fcitx5 holds the seat)
  → state `unsupported`, never respawned (one-IM-per-seat, R.5).
- `request(cmd, timeout, **fields)` → reply dict or `None` (timeout/dead child).
  **Never retries** (R.5: never resend an op that may already have landed).
- Callbacks run ON the reader thread, exception-guarded: `on_event(ev_dict)` is the
  T4 takeover feed (every `{"ev": ...}` line); `on_delivery_state(state, reason)`
  fires ONLY for `unsupported` / `fault`.
- `stop()` = single-flight bounded teardown: SIGTERM → wait(5 s) → `killpg` SIGKILL.
  Emits nothing. A stale reader can never touch new state (epoch counter).

**Acquire / show / verify — `voice_typing/ime/target.py`:**

```python
_ACQUIRE_TIMEOUT_S = 2.5   # > host _SURROUND_WAIT_S (1.0) + margin — PASS EXPLICITLY
_SHOW_TIMEOUT_S    = 0.25  # fits the controller's 250 ms failure deadline
_COMMIT_CAP_BYTES  = 4000  # >4000 B commit ⇒ REFUSED, never chunked

@dataclass(frozen=True)
class FieldBinding:          # the opaque AcquireResult.handle
    im_handle: str           # str(host im object id) — informational
    cursor_bytes: int        # caret as UTF-8 byte offset at acquire
    anchor_bytes: int
    pre_caret: str           # ORIGINAL bytes before caret, sliced on byte boundary
    revision: int            # == host `dones` count

class ImeTarget:
    units = TargetUnits.UTF8_BYTES
    def __init__(self, proc): ...        # duck: anything with .request(cmd, timeout=..., **fields)
    last_reason: str                     # machine-readable refusal taxonomy (R.5 logs)
    def acquire(self) -> AcquireResult
    def recheck(self, binding, inserted_bytes=0) -> tuple[bool, str, int]  # (ok, reason, revision)
    def show(self, session: int, utterance: str, seq: int,
             expected_revision: int, span: str) -> ShowResult
    @staticmethod
    def binding_caret_after(binding, inserted_bytes) -> int
    @staticmethod
    def to_bytes_span(text, start_char, end_char) -> tuple[int, int]
```

- **Acquire refusal taxonomy** (each branch test-pinned in `tests/test_ime_target.py`):
  `"ime no reply"` · `"<host reason>"` (not activated / no surrounding text) ·
  `"snapshot missing fields"` · `"snapshot truncated"` · `"inconsistent snapshot"` ·
  `"user selection present"` (cursor != anchor; never replace — R.3).
- **`show()` decision order**: (0) no binding → REFUSED `"not acquired"`;
  (1) `rendered_equal(_last_applied_span, span)` → UNCHANGED, ZERO events;
  (2) `expected_revision < binding.revision` (or non-int) → REFUSED `"revision regression"`;
  INSERT path (`span.startswith(owned)`): recheck → cap check → wire `show` with
  `text=delta, before=0`; CORRECTION path: recheck(caret at END of owned range) →
  `_owned_region_intact` (ONE fresh verify; the byte range to delete must still be
  byte-exactly ours) → cap check → wire `show` with `text=span, before=owned_bytes`
  (ONE atomic `delete_surrounding_text(before, 0) + commit_string + commit`).
  `_last_applied_span`/`_inserted_bytes` advance ONLY on `applied`.
- **recheck()** (never mutates): fresh `verify` → checks activated, snapshot present,
  cursor==anchor, `cursor == binding.cursor_bytes + inserted_bytes` (else
  `"caret moved"`), and pre-caret region still STARTS WITH `binding.pre_caret`
  (else `"adjacent text changed"`; prefix semantics, not endswith — see the code comment).
- NOTE: `finalize`/`leave`/`cancel` are NOT yet on `ImeTarget` (T3.S3 pending);
  `leave` exists only at the wire/host level. The `DeliveryTarget` protocol
  (bulk_delivery.py) requires all five.

**Host-level commands** (`voice_typing/ime/ime_host.py`, JSONL on pipes):
`{"id":N,"cmd":"acquire"}` → `{ok, handle, revision, text, cursor, anchor,
snapshot_truncated[, reason]}` (waits ≤1.0 s for first surrounding_text);
`"show"` (fields `session, utterance, seq, expected_revision, text[, before]`) →
`{result, t_ms}`; `"verify"` → `{activated, dones, ok, text, cursor, anchor,
snapshot_truncated, text_head, bytes}` (read-back verification); `"leave"` → `{ok:true}`
(releases keyboard grab, keeps serving); `"ping"` → `{activated, dones}`;
`"cancel"` with `before: K` → deletes K UTF-8 bytes backward in ONE commit cycle.
Host `show` waits ≤ `SHOW_CONFIRM_WAIT = 0.22 s` for the compositor `done` → else
`unknown`; NEVER retries. Snapshot head cap `_SNAPSHOT_HEAD_BYTES = 64 KiB`.
Host readiness for `become_im` proven by the capped event log's first `"globals"` line.
`unavailable` → event + log + clean `exit(0)`.

**Wire client** (`wlwire.py`): `Client(display=None, sock=None)` (sock = pre-connected
socket for tests; resolves `WAYLAND_DISPLAY` only in `__init__` under
`$XDG_RUNTIME_DIR`); `request(obj, iface, name, *args)`, `next_event(timeout=0.5)`,
`roundtrip(timeout=5.0)`, `bind(global_name, iface, version=1)`; received keymap fds
are closed (fd discipline).

---

## 2. Result taxonomy

`voice_typing/bulk_delivery.py`:

```python
class ShowResult(str, Enum):
    APPLIED   = "applied"    # target executed AND confirmed the edit
    UNCHANGED = "unchanged"  # render-equal — ZERO events
    REFUSED   = "refused"    # target actively declined
    UNKNOWN   = "unknown"    # outcome unverifiable — NOT delivered; never retry
```

Cross-pinned: `voice_typing/ime/protocol.py` `SHOW_RESULTS = ("applied", "unchanged",
"refused", "unknown")` and `tests/test_ime_protocol.py::test_show_results_cross_pinned_to_bulk_delivery`.
Only APPLIED/UNCHANGED keep delivery active; REFUSED/UNKNOWN disarm. Also here:
`AcquireResult(ok, handle, revision, reason)`, `TargetUnits` (UTF8_BYTES /
CHARACTERS / UTF16_UNITS / EDITOR_MARKERS), `map_span()`, `rendered_equal()`
(whitespace-collapse-only zero-diff guard; never folds case/punctuation), and the
`@runtime_checkable class DeliveryTarget(Protocol)` with `acquire/show/finalize/
leave/cancel` — every mutating call carries `session, utterance, seq,
expected_revision` re-checked AT MUTATION TIME.

`bulk_controller.py` (skim): `BulkController` deque QSIZE 32 (bounded; overflow STOPS
not drops), `op_deadline` (default per test 0.02 s; production 0.25 s budget),
single-worker op runner, `arm(gen)`, `on_partial/on_final(span, *, utterance, seq, gen)`,
`cancel(*, gen=None) -> bool`, `stop(*, leave=True)`, `drain()`, `stats()`,
`confirmed_visible()`. A raising target is unknown-class → stop `"target-error"`.
Late results after give-up are discarded (discarded ≠ not-happened).

---

## 3. Lab drivers (`tests/ime_acquire_lab.py`, `ime_show_lab.py`, `ime_correction_lab.py`)

These are the closest existing pattern to the G3 harness — all three share one shape:

- **Env-gated, never collected by pytest** (no `test_` prefix). Without the gate env
  they print a JSON `{"row":"gate","pass":null,"note":"skipped (set <ENV>=1)"}` and
  exit 0. Gate envs: `IME_ACQUIRE_LAB`, `IME_SHOW_LAB`, `IME_CORRECTION_LAB`.
  Invocation pattern: `timeout 300 env <GATE_ENV>=1 .venv/bin/python tests/ime_X_lab.py`.
- **They DO boot a compositor**: outer process = `xvfb-run -a dbus-run-session
  --config-file=<private-bus.conf> -- python <this script> run <tmpdir>` with
  `start_new_session=True` and a 240 s `proc.wait(timeout=240)` + killpg fallback.
  Disposable env: `HOME/XDG_RUNTIME_DIR/XDG_CONFIG_HOME/TMPDIR` all = the mktemp dir;
  `GDK_BACKEND=wayland`, `WLR_BACKENDS=x11`, `WLR_LIBINPUT_NO_DEVICES=1`,
  `WLR_RENDERER=pixman`, `LIBGL_ALWAYS_SOFTWARE=1`, `XDG_SESSION_TYPE=wayland`,
  `LANG=C.UTF-8`. Inner `run(root)` refuses unless root is the disposable dir
  (`root == XDG_RUNTIME_DIR == home`, name-prefixed). Then `sway -c sway.conf`
  (`xwayland disable`, `focus_follows_mouse no`) on the private seat; readiness by
  polling `sway-ipc.*.sock` and a `wayland-*` socket (≤7 s `until()` polls).
- **The field**: `tools/im-lab/field_gtk.py` via SYSTEM `python3` (the venv has no gi);
  readiness file `field.ready`; state dumped to `field.json` (text/pos) in the root
  (capped 2000). Focus via `swaymsg -r '[title="imlab-field-gtk"] focus'`; synthetic
  keys via `xdotool key` (XTEST → wlroots X11 backend → seat).
- **The transport**: the lab spawns `python -m voice_typing.ime.ime_host <log>` itself
  over pipes and talks to it with a local `HostPipes` class implementing the proc duck
  (`request(cmd, timeout, **fields)`, skipping id-less event lines) plus
  `wait_event(name, seconds, pred)` — which PUMPS the host with a ping per poll cycle
  (a passive read would deadlock: the host drains wire events only around request
  handling). Then it builds the REAL `ImeTarget(pipes)`.
- **Rows → one JSON verdict line each**, printed with `print(json.dumps(v), flush=True)`:
  `{"row": "R1 gtk seed", "pass": true|false|null, ...evidence fields}` (`null` =
  skipped/honest-limitation). Final summary line: `{"rows":N,"passed":P,"skipped":S,
  "failed":F,"failed_rows":[...]}`; exit 1 iff any `pass is False`.
- **Bounded scratch discipline** (AGENTS.md Rule 3): one `TemporaryDirectory`
  (prefix `ime-<x>-lab-`), host event log via `EventLogWriter` (64 KiB cap),
  teardown = killpg every spawned proc in reverse, `_cleanup_stale_dirs()` removes
  stale prefix dirs from earlier aborted runs — explicitly NO pkill (a path-pattern
  sweep once killed the runner itself).

Existing rows: acquire lab (R3 foot no-snapshot refuse; R1 gtk seed byte-exact
pre_caret; R2 gtk Ctrl+A — honest finding: GTK4/text-input-v3 pushes NO selection
snapshot, acquire cannot see selections on this toolkit, pass=null with probe
evidence); show lab (R4 gtk bind; R5 gtk x3 inserts, edit-count ≤3, ZERO grab_key);
correction lab (R1 small correction; R2 >1024 B atomic replacement byte-exact).

---

## 4. G2 gate evidence pattern

`tests/test_g2_bulk_gate.py` is a pure-deterministic pytest module (fake
`G2FakeTarget`, 13 frozen traces + a `test_g2_gate_summary` machine-check of the
13-name list, autouse zero-legacy-backend sentinel fixture). It writes NO evidence
files itself; the evidence record is the hand-written markdown
**`plan/008_a47116bb2b79/architecture/g2_gate_record.md`** containing:

- Date + HEAD commit; the R.7 mandate verbatim; "necessary, NEVER sufficient" banner
  (a G2 pass never marks a field row verified; G3 is the real-field gate).
- A verdict TABLE (`| # | trace | test | ✅ | families |`).
- Per-family enforcement prose (six assertion families: exact text/caret, bounded
  queue, zero legacy-backend calls, no duplicates, no extra writes / event-count law,
  no post-takeover mutations).
- "Live pass counts" table: file / passed / failed / note, quoting pytest summary
  lines only; determinism shown as 3 identical consecutive run timings.
- Scope guard: `git status --porcelain` listing exactly what changed.
- Quotes only pytest summary lines; fixtures under version control in `tests/`;
  no `/tmp` dumps.

G3 should follow the same discipline: a `plan/008_a47116bb2b79/...` record + JSON
verdict lines from an env-gated lab driver, never editing past evidence.

---

## 5. Version/reporting conventions

- Versions captured prose-style in evidence headers, e.g. `tests/ACCEPTANCE.md`
  evidence block: "Captured on Arch Linux, kernel 7.2.7-arch1-1, NVIDIA GeForce RTX
  3080 Ti (driver 615.71.09)". `plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md`
  line ~292 mentions "hyprland 0.57.2 similarly untested vs the 2026-11-22 matrix".
- `tests/ACCEPTANCE.md` structure: a numbered criteria table `| # | criterion |
  verdict (**PASS** etc.) | evidence prose |` with inline test names and exact
  commands (`timeout N .venv/bin/python -m pytest ...`), plus fenced verbatim
  evidence blocks emitted by the shell drivers ("=== ACCEPTANCE EVIDENCE (paste into
  tests/ACCEPTANCE.md, criteria ...) ===").
- Row-status vocabulary that exists today: field-class matrix words in
  `voice_typing/ime/__init__.py` / `d2_bulk_delivery_map.md` — "GTK-class full
  (insert + replace)", "foot + kitty insert-only", "ghostty dead",
  "untested" (hyprland). The exact G3 row-status string set
  ("untested | insert-only | blocked (reason) | verified (versions + evidence
  links)") does NOT exist yet anywhere — it is new vocabulary G3 introduces; the
  nearest precedents are these per-field class words and the lab JSON verdict
  `pass: true|false|null` + `reason`.

---

## 6. Takeover hooks (T4 feed)

- `ImeProcess(on_event=cb)`: cb receives EVERY decoded `{"ev": name, "t_ms", ...}`
  line from the host stdout — `activate`, `deactivate`, `done`, `surrounding_text`
  (bytes/cursor/anchor/head-80), `grab_key` (key, state), `keymap`, `modifiers`,
  `repeat_info`, `content_type`, `text_change_cause`, `unavailable`.
- `ImeHost.on_event`/`_emit` in `ime_host.py` is where these are produced;
  `commit_string` generates ZERO key events (R.2) so delivery cannot self-trigger
  takeover. Typed keys surface as `grab_key` events — the mutation-time revocation
  signal for the GTK selection-invisibility case (acquire-lab R2 note).
- Mutation-time half: `ImeTarget.recheck()` refusals (`"ime deactivated"`,
  `"caret moved"`, `"user selection present"`, `"adjacent text changed"`,
  `"ime no reply"`, `"no surrounding text"`) + `_owned_region_intact`.
- There is no takeover policy module yet (T4 not landed); no queues beyond the
  reader-thread callback.

---

## 7. Gotchas a G3 harness must respect

- **Deadlines**: show budget 250 ms end-to-end; host `SHOW_CONFIRM_WAIT = 0.22 s`;
  `ImeTarget` `_SHOW_TIMEOUT_S = 0.25`, `_ACQUIRE_TIMEOUT_S = 2.5` (must stay > the
  host's 1.0 s `surrounding_text` wait). `ImeProcess` request default timeout 1.0 s
  — the acquire path passes 2.5 explicitly.
- **Never retry** unknown/no-reply operations (R.5); never resend on the wire.
- **The host only drains wire events around request handling** — a passive stdout
  read deadlocks. Pump with pings (see lab `HostPipes.wait_event`) or use
  `ImeProcess`'s reader thread.
- **One IM per seat**: an `unavailable` event means another IM (fcitx5) holds the
  seat → state `unsupported`, emitted once, no respawn; the lab/test desktops must
  not run another IM.
- **Threads**: `ImeProcess` reader thread is the sole stdout consumer and owns
  closing stdout; callbacks run on it (keep them non-blocking / exception-safe);
  stop() is single-flight; epoch guards stale readers.
- **Bounded scratch**: event log capped 64 KiB (`EventLogWriter` / `LOG_CAP_BYTES`);
  scratch in one TemporaryDirectory; NO pkill pattern sweeps (killpg your own
  session groups only).
- **Field-state reads** come from the field app's own dump (`field.json`) — assert
  byte-exact text/caret/edit counts from the TARGET's view, not the sender's.
- **Sequence on the target's pushed snapshots**: wait for the post-commit
  `surrounding_text` event (pred on bytes) before the next recheck-dependent op,
  or recheck may see a stale cache.
- AGENTS.md: every command under inner `timeout` + harness backstop; daemon only
  via systemd/detached; voicectl always under `timeout 30`.

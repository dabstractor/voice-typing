# Research Brief: voice_typing/ime transport package + JSONL protocol (P1.M4.T1.S1)

**Status:** verified against the live tree 2026-11-22+. Sources read in full: `tools/im-lab/wlwire.py`
(212 lines), `tools/im-lab/im_probe.py` (192), `tools/im-lab/README.md`, `voice_typing/bulk_delivery.py`
(the P1.M3.T1.S1 contracts), `plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md` §5. The
upstream XML (`https://raw.githubusercontent.com/hyprwm/Hyprland/main/protocols/input-method-unstable-v2.xml`)
is reachable (HTTP 200 verified) — vendor it as a test fixture.

---

## 1. What exists and what moves where

| Source (stays in tools/ — READ-ONLY, it is R.2 evidence) | Destination (evolved copy) |
|---|---|
| `tools/im-lab/wlwire.py` — stdlib wire client (core + zwp_input_method_v2 + grab); REQUESTS/EVENTS opcode tables; `Client` (connect/roundtrip/next_event/handle) | `voice_typing/ime/wlwire.py` |
| `tools/im-lab/im_probe.py` — becomes seat IM; select() loop; JSON commands insert/replace/preedit/endpreedit/grab; 64 KiB-capped `im.jsonl` | `voice_typing/ime/ime_host.py` |
| (new) | `voice_typing/ime/protocol.py` — pure JSONL vocabulary/framing |
| (new) | `voice_typing/ime/__init__.py` — Mode A docstring (R.2 evidence trail) |

**Copy, do not delete or re-point the lab.** d2 §5 and the im-lab README cite tools/im-lab by path as
the durable evidence record; the package is the evolved production lineage ("wlwire lineage is the
decided transport").

## 2. The contracts this package serves (bulk_delivery.py, READ-ONLY)

- `ShowResult(str, Enum)`: `applied | unchanged | refused | unknown` — "serialized verbatim into
  status/log lines". JSONL replies carry these words verbatim (str-Enum values).
- `AcquireResult(ok, handle, revision, reason)` → acquire reply shape `{ok, handle, revision, reason}`.
- `DeliveryTarget` protocol methods: `acquire()`, `show(session, utterance, seq, expected_revision, text)`,
  `finalize(...)`, `leave()`, `cancel()` — S1 defines the WIRE VOCABULARY for these (acquire/show/
  verify/leave per the item contract; cancel reserved for P1.M4.T3.S3), the semantics land in T2/T3.

## 3. Design decisions (pinned)

1. **Transport-agnostic JSONL**: requests = one JSON object per line in; replies + async events = one
   per line out. `ime_host.main()` serves stdin/stdout (the daemon-owned subprocess of S2 speaks
   pipes); the framing functions accept any file-like. (im_probe's ctl.sock was lab instrumentation.)
2. **Requests**: `acquire`, `show` (fields: session/utterance/seq/expected_revision/text), `verify`,
   `leave`, plus `ping` (health/latency, doubles as the S2 monitor's heartbeat). `cancel` is defined
   in the vocabulary but marked reserved (T3.S3 implements semantics). Unknown request →
   `{"id":..., "error":"unknown request ..."}` reply, host keeps serving.
3. **Every request carries a caller-supplied `id`** (monotonic from the daemon); the reply echoes it.
   Async events (activate/deactivate/surrounding_text/text_change_cause/done/unavailable/grab key/
   keymap/modifiers/repeat_info) are emitted as `{"ev": name, "t_ms": ..., ...}` lines WITHOUT id —
   the daemon-side takeover detection (P1.M4.T4) consumes exactly these. `unavailable` also causes a
   clean exit (one-IM-per-seat; the lab's open item "degrade gracefully" → host exits, S2 marks route
   unavailable).
4. **Event log**: keep im_probe's 64 KiB cap mechanism (`LOG_CAP = 64*1024`, stop appending past cap),
   path from argv (default `<stderr>`? no — a file path arg, lab passes tmp path; S2 passes a
   daemon-rundir path). Log lines are the same event dicts (counts/times only — no recognition text
   beyond what surrounding_text head-truncation already does; keep the existing `head: text[:80]`
   truncation).
5. **wlwire evolution is MINIMAL**: move as-is, plus (a) injectable transport for tests — `Client`
   gains an optional pre-connected `sock` argument (`__init__(display=None, sock=None)`; tests pass a
   socketpair or a fake with `sendall`/`recvmsg`); (b) fd leak discipline already closes keymap fds;
   (c) no new interfaces (grab already tabled).
6. **Opcode-table tests vs the vendored XML**: vendor `input-method-unstable-v2.xml` into
   `tests/fixtures/` (fetch once, commit — fixtures are the only evidence that enters version control).
   The test parses it with `xml.etree.ElementTree`: for each `<interface name=...>`, the child
   `<request>`/`<event>` elements in document order give (name, arg-kinds) — kinds from
   `<arg type=...>` mapped `uint→u, int→i, string→s, object→o, new_id→n, fd→h` — and MUST equal
   wlwire's REQUESTS/EVENTS entries for the zwp_input_method* interfaces (core wl_* tables stay
   hand-pinned; the XML is only the IM protocol). XML only defines the IM interfaces we table; wl_seat
   etc. come from wayland.xml, not this file — test only the zwp_* tables against the XML.
7. **JSONL framing tests**: encode/decode round trip; newline-inside-payload impossible (json.dumps
   escapes); id echo; unknown-request error reply; event lines lack id; the log cap stops appending at
   64 KiB; `show` field validation (missing field → error reply, not crash — probe's survive-bad-rows
   posture kept).
8. **No operator surface**: no systemd/config.toml/hypr-binds/pyproject changes. Stdlib only.
   `voice_typing/ime/` must import cleanly with no WAYLAND_DISPLAY set (protocol.py pure; wlwire only
   touches the socket in `Client.__init__`).

## 4. Test matrix (all CUDA-free, sub-second)

- `tests/test_ime_wlwire.py`: opcode tables == XML (requests+events, per-interface, arg kinds);
  `u32/i32/wstr` byte layouts (wstr pads to 4, includes NUL, length prefix counts NUL);
  `request()` message bytes via a fake socket (monkeypatch `Client.s`); header packing
  `<IHH` = (obj, opcode, size); id-space exhaustion guard.
- `tests/test_ime_protocol.py`: framing round trips; request vocabulary accepted/rejected; reply id
  echo; ShowResult words verbatim; event-line shape; log-cap behavior.
- `tests/test_ime_host.py` (optional but cheap): `ImeHost` with a FAKE client (no compositor): serve
  loop answers ping/acquire-not-activated/unknown from an in-memory duplex (io.StringIO pair or
  socketpair thread).

## 5. Out of scope (fenced)

- Subprocess spawn/monitor/teardown + unavailable handling → **P1.M4.T1.S2**.
- acquire()/show()/verify() SEMANTICS (surrounding_text verification, units mapping, serial tracking
  beyond passthrough) → **P1.M4.T2/T3**. S1's host maps requests to wire requests best-effort
  (insert/replace/preedit mechanics already proven in the lab) but ownership logic is not required.
- Takeover detection/revocation → P1.M4.T4 (the package just forwards grab events).
- Daemon wiring, feedback delivery fields (in flight in P1.M3.T3.S2 — do NOT touch feedback.py/
  daemon.py/ctl.py), controller, voicectl.

## 6. Tooling

`.venv/bin/python -m pytest` (zsh aliases bare python); every run under inner GNU `timeout` + the
bash-tool backstop (AGENTS.md Rule 1). No GPU/daemon/compositor needed. Do not run the daemon
foreground. New tests are pure/fast — full-file runs fine under `timeout 120`.

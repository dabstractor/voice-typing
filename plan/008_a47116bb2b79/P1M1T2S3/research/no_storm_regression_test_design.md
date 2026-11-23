# Research — P1.M1.T2.S3: Journal-noise regression guard (no per-burst fallback storms)

TEST-ONLY task: pins D3.1's no-storm property in `tests/test_typing_backends.py` after S1's merge +
S2's contact gap. Verified facts below; line numbers from live tree unless noted.

## 1. The defect being pinned (D3.1, PRD §8 Known defects)
Pre-merge, `YdotoolClient` opened SOCK_STREAM against ydotoold's SOCK_DGRAM socket → EVERY connect
failed (Errno 91) → every backspace burst degraded to ONE CLI spawn + ONE WARNING (56 journal
warnings/week). Post-merge a healthy datagram socket routes every burst over the socket: ZERO spawns,
ZERO warnings. Fix branch: `fix/ydotoold-datagram` (33321c6) — merged by S1.

## 2. Landing state (verified NOW) + gate
- LANDED: `voice_typing/ydotoold_client.py` — `class YdotoolClient` @28,
  `__init__(self, socket_path: str | None = None)` @31, `_connect` @39 (SOCK_DGRAM),
  `press_backspace(n)` @66. Injected by path: `YdotoolClient(socket_path="<tmp>/s.sock")` — never the
  real `/run/ydotoold.socket`.
- NOT yet on disk: `tests/test_ydotoold_client.py` (S1's 11-test file; S1 status Implementing) and S2's
  `_CONTACT_GAP_S`. GATE (Task 0): `test -f tests/test_ydotoold_client.py` AND
  `grep -q _CONTACT_GAP_S voice_typing/ydotoold_client.py` — else STOP (blocked on S1/S2).

## 3. The property owner: `YdotoolBackend.press_backspace` (typing_backends.py ~134-151)
Routing (verbatim shape):
- `if n <= 0: return` — BEFORE client/CLI (n=0: no spawn, no warning; already tested @327).
- `if self._client is not None:` → `try: self._client.press_backspace(n); return`
  → `except Exception: logger.warning("ydotoold client failed; falling back to ydotool CLI",
  exc_info=True)` (**the warning site, ~143-144**) → CLI `_paced_run(["ydotool","key","-d","6"] +
  ["14:1","14:0"]*n)`.
- Client absent → CLI only. `__init__(self, client=None)` @123 injects.
So: healthy client ⇒ 0 spawns + 0 warnings; a client that raises ⇒ exactly ONE spawn + ONE warning PER
FAILING CALL (the storm pre-merge was one fail per burst). One transient death followed by self-heal ⇒
exactly one spawn+warning TOTAL.

## 4. The existing test seam (tests/test_typing_backends.py, 401L)
- `_Recorder` @44-75: monkeypatches `subprocess.run` (fixture `recorder` @77); `.calls` list,
  `.argvs` property (tuple argvs), `.raise_on(cmd0, exc)`. Zero real spawns possible — guarded by
  `test_no_real_subprocess_run_during_tests` @272.
- caplog idiom: `with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):` then
  filter records (pattern @257-263 `test_fallback_logs_warning` — counts the wtype fallback warning).
- Precedent tests: `test_ydotool_press_backspace_exact_argv` @318 (CLI argv when client=None);
  `test_press_backspace_nonpositive_spawns_nothing` @327 (n≤0 guard).
- NO existing test injects a client into YdotoolBackend (grep: none) — S3 adds the first two.

## 5. Design (two tests, additive, in test_typing_backends.py)
A. **No-storm (the D3.1 regression):** a REAL `YdotoolClient` bound to an in-file AF_UNIX SOCK_DGRAM
   server (tmp_path socket + a daemon thread recvfrom-ing into a list — ~12 lines, self-contained; do
   NOT import from tests/test_ydotoold_client.py — it may still be landing). N=8 consecutive
   `press_backspace(2)` → assert `recorder.argvs == []` and zero "falling back" warnings. Pre-merge
   this fails with 8 spawns + 8 warnings — the true regression shape. Timing: real client pacing
   ≈18 ms/char (post-S2) → 8×2×18 ms ≈ 0.3 s (fine; do NOT mock time.sleep).
B. **Death-once-then-heal:** a `_DyingOnceClient` double (raises RuntimeError("Protocol not available
   (Errno 91)") on call #1, succeeds after — models the client's self-heal reconnect, whose REAL
   coverage restart tests live in S1's test_ydotoold_client.py). N=6 total `press_backspace(2)` →
   exactly ONE CLI argv + exactly ONE warning + `client.calls == N`.
Assert warning count via message filter ("falling back" in r.getMessage()) — the logger name is shared
with the wtype fallback warning, so filter by text.

## 6. Boundaries
- No source change: routing/warning already correct post-merge; S3 only pins it. If Test A shows
  spawns/warnings on a healthy socket, that's a REAL bug (S1 merge incomplete) — report, don't paper over.
- S2's only typing_backends touch is the ~:147 pacing comment. S3's tests don't depend on it beyond the
  gate (timing is not asserted here — only counts).
- DOCS: none (contract). PRD/tasks/snapshots untouched.

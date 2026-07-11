# S3 Research Findings — Close the circular-proof gap in test_idle_and_gpu.sh

## 0. Task restatement (one line)

Remove `tests/test_idle_and_gpu.sh:206`'s pre-set `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`,
rely on `launch_daemon.sh`'s exports (S1, already applied), and add a real production-path
regression guard that greps `$WORK/daemon.log` for `HTTP Request: GET https://huggingface.co` and
FAILS if any are found. Update the file's own header/G-OFFLINE/criterion-8 comments to document the
new NON-CIRCULAR proof approach.

## 1. The masking (CONFIRMED against the live file)

`tests/test_idle_and_gpu.sh` line 206 (verified by `grep -n`):

```sh
206  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1     # ← THE MASKING (test pre-sets the var)
207  XDG_CONFIG_HOME="$WORK/config" "$LAUNCH" > "$WORK/daemon.log" 2>&1 &
208  DAEMON_PID=$!
209  echo "daemon launched OFFLINE (HF_HUB_OFFLINE=1) pid=$DAEMON_PID; ..."
```

This proves the daemon CAN run offline, but NOT that the PRODUCTION path (systemd → launch_daemon.sh
with no pre-set env) runs offline. The criterion-8 "proof" at line 388 is therefore circular: it
passes because the TEST supplies the variable that production omitted. This is exactly the gap that
let bugfix Issue 1 ship (PRD §2.1 / scout_launch_status_install.md §6).

## 2. S1 is ALREADY APPLIED (the precondition for S3)

`voice_typing/launch_daemon.sh` L71-72 (read in full, confirmed):

```sh
71  export HF_HUB_OFFLINE=1
72  export TRANSFORMERS_OFFLINE=1
74  exec "$PY" -m voice_typing.daemon "$@"
```

So removing the test's line-206 pre-set does NOT break the test: the daemon still inherits both vars
via the wrapper (execve(2) reads them at process start). The test now exercises the REAL production
path. S1's PRP (line 259-260) explicitly states: "S3 removes the line-206 pre-set and adds a
production-path journal grep for 'HTTP Request: GET https://huggingface.co' -> fail if found. S1
makes that grep pass." This is the contract.

## 3. WHY the daemon.log grep WORKS (the load-bearing technical detail)

The grep target `HTTP Request: GET https://huggingface.co` is reliable because of three verified
facts:

**(a) huggingface_hub, in ONLINE mode, performs an HTTP GET per model on startup.**
The bug report (TEST_RESULTS.md L25-26) shows the verbatim journal lines:
```
Jul 11 14:47:37 ... HTTP Request: GET https://huggingface.co/api/models/Systran/faster-distil-whisper-large-v3/revision/main "HTTP/1.1 200 OK"
Jul 11 14:47:37 ... HTTP Request: GET https://huggingface.co/api/models/Systran/faster-whisper-small.en/revision/main "HTTP/1.1 200 OK"
```
These are httpx (the HTTP client used by huggingface_hub) INFO-level logs emitted when it does the
online model-revision/freshness check. Two per startup, one per model. With `HF_HUB_OFFLINE=1` set,
huggingface_hub is cache-only and emits ZERO such lines (research_hf_offline.md "Validation of
Proposed Diff": recorder constructs cleanly with zero `HTTP Request` lines).

**(b) The daemon's logging emits these to stderr.**
`voice_typing/daemon.py:_setup_logging` (L1149-1173, read in full):
```python
logging.basicConfig(
    stream=sys.stderr,
    level=_resolve_log_level(level_name),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
```
`logging.basicConfig` installs a single `StreamHandler` on `sys.stderr` at the resolved level on the
ROOT logger. httpx logs via `logging.getLogger("httpx")` — a child of root — so its records
PROPAGATE to the root handler → stderr. (Confirmed: the production systemd journal captured these
lines, and journald captures the unit's stderr. Same code path, same stderr stream.)

**(c) The test redirects stderr into daemon.log.**
Line 207: `"$LAUNCH" > "$WORK/daemon.log" 2>&1 &`. The `2>&1` folds stderr into the stdout redirect,
so EVERYTHING the daemon (and its child libraries) writes to stderr lands in `$WORK/daemon.log`.
Therefore: `grep -q 'HTTP Request: GET https://huggingface.co' "$WORK/daemon.log"` will match IFF the
daemon made online HF requests — i.e. IFF the offline exports are missing from launch_daemon.sh.

**Conclusion:** the grep is a true regression guard. If a future change removes S1's exports, the
daemon runs online, httpx logs the GETs to stderr, they land in daemon.log, and the test FAILs.

**Network-failure nuance (non-blocking):** the grep is most reliable on a test host WITH network
(the typical dev machine — and exactly the case where the regression would "succeed" silently).
If the host has NO network AND the exports are missing, huggingface_hub's freshness check may
time-out before httpx logs the request line; in that degraded case the daemon's startup latency
spikes (tens of seconds) and may hit the 180s ready-wait timeout or raise
LocalEntryNotFoundError → caught by the existing `die "daemon not ready in 180s"` /
`die "daemon exited during startup"` guards. Either way the test does not silently pass. This is
acceptable and matches the item contract: "Do NOT make it require network — if the exports are
missing, the daemon should fail to start, which the ready-wait timeout catches."

## 4. Exact edit sites (line numbers verified by grep -n)

| Line(s)    | Current content (verbatim)                                                | Edit                                                                 |
|------------|---------------------------------------------------------------------------|----------------------------------------------------------------------|
| 3-5        | header: "Stands up the REAL daemon (launch_daemon.sh, launched OFFLINE with HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 so the run itself PROVES ...)" | Reword: production-path launch; no pre-set; offline via wrapper; grep is the proof |
| 51-52      | `G-OFFLINE:` invariant (launch with HF_HUB_OFFLINE=1 ...)                 | Reword: do NOT pre-set; rely on wrapper; grep daemon.log for ZERO HF HTTP lines |
| 200-205    | launch-section comment block ("HF_HUB_OFFLINE=1 ... -> criterion 8 proof") | Reword for production-path + wrapper-provided vars                   |
| **206**    | `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`                          | **REMOVE** (or replace with a one-line comment: wrapper provides them) |
| 209        | `echo "daemon launched OFFLINE (HF_HUB_OFFLINE=1) pid=..."`               | Reword echo (no longer pre-set)                                      |
| 218 (after ready loop)  | (nothing — insertion point)                                    | **ADD** the post-ready grep assertion (the regression guard)         |
| 386-387    | comment "# --- criterion 8 ... restate — the WHOLE run was under HF_HUB_OFFLINE=1 ---" | Reword: NON-CIRCULAR proof via the grep (no pre-set) |
| 388        | `echo "[PASS] criterion 8 (no network): daemon ran under HF_HUB_OFFLINE=1 ..."` | Reword PASS msg: daemon.log has ZERO HF HTTP-request lines          |
| 404        | `echo "offline_env: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1"`             | Reword: via launch_daemon.sh exports; daemon.log grep CLEAN          |

The ready-wait loop ends at line 218: `[ "$ready" = 1 ] || die "daemon not ready in 180s; see $WORK/daemon.log"`,
followed by a blank line and `# --- criterion 6: un-armed boot ...` (L220). The grep assertion goes BETWEEN
them (after the daemon is confirmed ready, before criterion-6 boot capture) — exactly where the
contract says ("Place it after the daemon is confirmed ready, after the ready-wait loop, ~line 215+").

## 5. The grep assertion (contract-specified code, lightly enhanced)

```sh
# --- criterion 8 (no-network): NON-CIRCULAR regression guard (bugfix Issue 1) ---
# The test did NOT pre-set HF_HUB_OFFLINE (that masked Issue 1). launch_daemon.sh exports it
# (S1); this grep proves the PRODUCTION path is offline by asserting the daemon log contains
# ZERO online huggingface.co requests. httpx logs 'HTTP Request: GET https://huggingface.co'
# to stderr (root StreamHandler from _setup_logging) -> folded into daemon.log by the 2>&1
# redirect at launch. Missing exports => online freshness check => match => FAIL.
if grep -q 'HTTP Request: GET https://huggingface.co' "$WORK/daemon.log"; then
  die "FAIL: daemon made network calls to huggingface.co (offline exports missing from launch_daemon.sh?); see $WORK/daemon.log"
fi
echo "[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)"
```

## 6. Validation strategy (the test CANNOT run in CI)

This is a ~400-line manual bash integration test requiring CUDA + prefetched models + ~3-4 min and a
quiet room. It is NOT collected by pytest (it is a `.sh` script). Therefore S3's validation is:

1. **`bash -n tests/test_idle_and_gpu.sh`** — syntax check (the primary automated gate).
2. **`shellcheck`** (if available) — catches unquoted vars / SC errors in the new grep block.
3. **Static verification the grep target matches the production journal format** — confirmed against
   TEST_RESULTS.md L25-26 (the verbatim bug-report lines). The grep substring
   `HTTP Request: GET https://huggingface.co` is a prefix of both observed journal lines.
4. **`git diff --name-only` == `tests/test_idle_and_gpu.sh` only** — scope discipline.
5. **Manual run (optional, requires GPU host):** stop the service, run the script, confirm the new
   criterion-8 guard echoes PASS and (if you temporarily revert S1) FAILs.

The CI safety net for this guarantee is the SIBLING task S2 (static drift-guard test in
test_systemd_unit.py), which DOES run in pytest and fails if the exports leave launch_daemon.sh.
S3 is the RUNTIME guard; S2 is the CONFIGURATION guard. Together they close the gap end-to-end.
**S2 is being implemented in parallel** (per the parallel_execution_context) — S3 must NOT edit
test_systemd_unit.py or launch_daemon.sh; S3 owns ONLY test_idle_and_gpu.sh.

## 7. Anti-patterns to explicitly avoid

- ❌ Do NOT keep the line-206 pre-set "to be safe" — that re-introduces the circular proof. The
  whole point of S3 is to remove it.
- ❌ Do NOT make the test require network at the test level (no `curl`/`wget` of huggingface.co). The
  guard greps a LOCAL log file; network is only relevant to whether the daemon (under a regressed
  wrapper) would emit the lines.
- ❌ Do NOT change the grep target string. `HTTP Request: GET https://huggingface.co` is the exact
  httpx log prefix confirmed in the bug report. Tightening it (e.g. to `/api/models/`) risks missing
  future variants; loosening it (e.g. to `huggingface`) risks false positives from unrelated logs.
- ❌ Do NOT touch launch_daemon.sh, test_systemd_unit.py, install.sh, daemon.py, README, or the
  systemd unit — sibling scope.
- ❌ Do NOT add a pytest wrapper for this `.sh` script — it is explicitly a manual test (header L33).

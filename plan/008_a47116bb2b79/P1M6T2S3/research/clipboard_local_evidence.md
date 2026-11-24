# Clipboard / CLI local evidence — P1M6T2S3 (READ-ONLY extraction)

Repo `/home/dustin/projects/voice-typing`. Sources quoted verbatim with exact line numbers. No
source file was modified; this file is the only write.

---

## Source 1: `plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md`

### Section 4 — "ctl.py + feedback.py recipes" (lines 124–165, verbatim)

```
## 4. ctl.py + feedback.py recipes

`ctl.py` (`voice_typing/ctl.py`, 301 lines): `_COMMANDS` tuple `:42-49` = (toggle, start, stop,
status, quit, cancel); `_ALIASES` `:55` (toggle-lite→toggle); exit codes 0/1/2/64 (`:6-16`;
`_EX_USAGE=64` `:60`); `_LOADING_HINT_DELAY=0.3` `:66`; `_SOCKET_TIMEOUT_S=10.0` `:73`, overridable
`VOICECTL_TIMEOUT` (`_socket_timeout_s` `:76`; AGENTS.md mandates `timeout 30` wrapper anyway);
`format_result(cmd, response)` `:90` — PURE; status branch `:126-171` renders the multi-line block;
`send_command` `:167-210` (sock.settimeout bounds connect+recv; wedged daemon → `ValueError` →
exit 1; one line one-shot); `_build_parser` `:236` — single optional positional `cmd`, argparse
choices deliberately OFF so usage errors exit 64 not 2; `main()` `:262-301` (alias remap → validate
→ resolve socket → send (arm cmds via loading-hint wrapper `:213`) → format → print).

**Recipe — `session [--copy]`:**
1. `ctl.py`: add `"session"` to `_COMMANDS`; add `--copy` as an argparse `store_true` flag (or a
   second positional) — but note `send_command` sends only `{"cmd": cmd}`; the flag must become part
   of the payload, so extend `send_command(socket_path, cmd, extra=None)` → `{"cmd":..., **extra}`
   (daemon `_dispatch` reads `msg.get("cmd")` only — additive keys are ignored today, harmless).
2. `daemon.py` `_dispatch` `:2660`: add `if cmd == "session": return self._daemon.session_reply(...)`
   (new method; NOT routed through `_arm_response`).
3. `format_result`: add a `session` branch (mirror the `status` branch style) rendering
   delivery_mode/delivery_state/last-confirmed-op.
4. `--copy` client side: stage via `/usr/bin/wl-copy --foreground --type text/plain;charset=utf-8`
   (verified present; the exact spawn+stdin pattern is `tools/paste-lab/ghostty_probe.py:102`, with
   `wl-paste --no-newline` verify at `:109`).

`feedback.py` (`voice_typing/feedback.py`, 264 lines): state.json schema `{"listening", "phase"
(unloaded/loading/idle/listening/speaking), "models_loaded", "mode", "partial", "last_final", "ts"}`
(docstring `:10-11`, init `:92-105`); partial disk-write throttle `_PARTIAL_WRITE_MIN_INTERVAL` `:74`
(≥10 Hz; in-memory always updated `:111-122`); `set_phase` `:124` (always writes, never notifies);
`set_models_loaded` `:135`; `set_mode` `:147`; `record_final` `:155`; `set_listening` `:173`;
`snapshot` `:195`; `notify` `:206` (Hyprland notify; NEVER on partial/phase by rule `:28`).

**Recipe — delivery fields:** add `delivery_mode`, `delivery_state`
(`inactive|active|unsupported|fault`), `delivery_reason`, `last_confirmed_op` keys to `_state` init
(additive — the `"mode"` and `"cancelled"` precedents) + one setter per field in the `set_phase`
style (always write, never notify); the bulk controller is the only writer. Render path: daemon
`status_snapshot()` `daemon.py:2275-2318` (keys: listening, mode="lite", phase, models_loaded,
load_error, partial, last_final, uptime_s, device, compute_type, model, mic_ok, mic_error,
context_prompt — additive-key pattern proven by `mic_*` and the `context_prompt` label
`_context_prompt_label()` `:2318`) → `ctl.py format_result` status branch `:126-171` (add delivery
lines after `context-prompt`).
```

### Related items (same file)

- `session_reply` in `_dispatch`: quoted above at d2 line 141 — `daemon.py _dispatch :2660`: add
  `if cmd == "session": return self._daemon.session_reply(...)` (new method; NOT routed through
  `_arm_response`).
- **wl-copy**: d2 line 145 (§4 step 4, quoted above) and line 176 (§5 lab-reuse table row for
  `ghostty_probe.py`: "`wl-copy --foreground` staging `:102`, byte-reader instead of shell,
  `wl-paste --no-newline` verify at `:109`"), plus line 228 ("`/usr/bin/wl-copy` all present").
- **Exit codes**: d2 lines 128–135 — exit codes 0/1/2/64 (`:6-16`; `_EX_USAGE=64` `:60`); wedged
  daemon → `ValueError` → exit 1; argparse choices deliberately OFF so usage errors exit 64 not 2.
- **Truncation reporting**: **no mention of truncation reporting exists in d2** (grep for
  "truncat" over the file returns nothing). The closest analogous precedent is the status branch
  rendering (`format_result :126-171`) and the additive `format_result` session branch recipe
  (§4 step 3) — any truncation reporting for `session --copy` output would follow the same
  "session branch mirrors status branch" pattern, but no spec text exists yet.
- Also relevant — §9 risk 9 (d2 lines 307–309, verbatim):
  ```
  9. **`session`/`--copy` payload shape** — `send_command` currently sends `{"cmd": cmd}` only; the
     `--copy` flag needs an additive-payload extension (daemon `_dispatch` ignores unknown keys today,
     so old daemons fail safe with unknown-command/ignore rather than wedge).
  ```

---

## Source 2: `plan/008_a47116bb2b79/architecture/external_tech_notes.md`

### Section 5. wl-clipboard (lines 92–117, verbatim — 5.7 quoted, neighbors included for context)

```
### 5. wl-clipboard
Sources: [wl-clipboard](https://github.com/bugaevc/wl-clipboard), [wl-copy(1)](https://man.archlinux.org/man/wl-copy.1), [wl-clip-persist](https://github.com/Linus7890/wl-clip-persist), [cliphist](https://github.com/christianhe99/cliphist).

5.1 Selections: wl-copy/wl-paste default to the **clipboard** selection; `--primary` targets PRIMARY. Plain `wl-copy` never touches PRIMARY. **Confidence:** high.

5.2 Lifetime: wl-copy **forks**; the parent exits immediately, a background child serves the data offer and the selection lives only while that server runs. When the server exits (or is killed), the offer content is gone unless a clipboard manager snapshotted it — exactly the gap `wl-clip-persist` exists to fill. **Confidence:** high.

5.3 `--paste-once` serves exactly the first paste request then exits (one-shot semantics). `-c`/`--clear` clears the selection. Exit codes: parent exits non-zero on failure to connect/serve; exact codes unverified this run. **Confidence:** medium-high.

5.4 Multi-format: multiple `-t mime` flags offer one **input stream** under several MIME types; wl-copy cannot ingest different content per type, therefore **it cannot faithfully restore a multi-format selection** (save/restore via `wl-paste | wl-copy` collapses to one type). **Confidence:** medium-high (man-page behavior).

5.5 Managers (cliphist etc.) observe via the data-control protocol (`wl-paste --watch`) and snapshot **every** offer — so if one runs, `--copy` text will land in clipboard history regardless of clearing. **Confidence:** medium-high. Sources: [wlr-data-control-v1](https://gitlab.freedesktop.org/wayland/wlroots/-/protocols/-/blob/master/unstable/wlr-data-control-unstable-v1.xml), [ext-data-control-v1](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/staging/ext-data-control-v1.xml).

5.6 **Local probes:** no `/usr/share/licenses/{cliphist,wl-clip-persist,clippie}` directories exist → none of the three appear installed as Arch/AUR packages with standard layout (medium confidence; AUR layouts vary). `systemctl --user list-ununits` **not run** (no shell) — clipboard-manager *service* presence remains unverified; belt-and-braces: treat history capture as possible.

5.7 Safest `voicectl session --copy` pattern: `printf %s "$text" | wl-copy -t text/plain` — clipboard selection only (PRIMARY untouched), explicit MIME (don't rely on wl-copy's tty autodetect), persistent serve until the next selection (normal paste UX). Use `--paste-once` only if one-shot semantics are wanted. If prior-clipboard restoration is required, save/restore single-type via `wl-paste --no-newline` and document the multi-format loss (5.4). **Support:** inference over 5.1–5.5. **Confidence:** high.

**Design implication for voice-typing:** `--copy` = wl-copy clipboard-only with explicit `-t text/plain`; never restore-then-clear via playerctl-style broad ops; accept that a running manager will record it.
```

Note: the "wl-clip-persist" source URL in the quoted header line is as it appears in the original
file. Neighboring guidance relevant to the CLI copy idiom:
- **Staging verify with `wl-paste --no-newline`** (5.7): after staging with wl-copy, verify the
  selection content with `wl-paste --no-newline` — the `--no-newline` flag matters because wl-paste
  by default appends a trailing newline; `--no-newline` gives back exactly the staged bytes.
- **Trim-newline behavior** (5.7): save/restore of a prior clipboard must use
  `wl-paste --no-newline` on the read side so the restored content is not grown by a newline;
  multi-format loss must be documented (5.4).
- **Clipboard-history watchers (cliphist)** (5.5–5.6): managers observe via data-control
  (`wl-paste --watch`) and snapshot every offer — staged `--copy` text will land in history if such
  a manager runs, regardless of clearing; treat history capture as possible.

---

## Source 3: `tools/paste-lab/ghostty_probe.py` — lines 80–130 verbatim

```python
        try:
            conf = root / "sway.conf"
            conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
            sway = spawn(["sway", "-c", str(conf)])

            def private_socket():
                if sway.poll() is not None:
                    raise RuntimeError("Private headless Sway failed to start")
                return next(root.glob("sway-ipc.*.sock"), None)

            env["SWAYSOCK"] = str(until(private_socket))
            env["WAYLAND_DISPLAY"] = until(lambda: next((p.name for p in root.glob("wayland-*") if p.is_socket()), None))
            term = spawn(["ghostty", "--gtk-single-instance=false", "--shell-integration=none",
                          "-e", sys.executable, str(Path(__file__).resolve()), "receive", str(root)])
            until(lambda: (root / "ready").exists(), 7)
            # Focus the private compositor's X window, not a desktop application.
            window = cmd(["xdotool", "search", "--onlyvisible", "--maxdepth", "1", "--name", ".*"]).splitlines()[-1].decode()
            cmd(["xdotool", "windowfocus", window])
            for i, data in enumerate(SAMPLES):
                # Inspect only the private compositor's clipboard. No
                # --paste-once: a read by a history manager isn't a target acknowledgement.
                owner = spawn(["wl-copy", "--foreground", "--type", "text/plain;charset=utf-8"], writable=True)
                assert owner.stdin is not None
                owner.stdin.write(data)
                owner.stdin.close()

                def offered():
                    try:
                        return cmd(["wl-paste", "--no-newline"]) == data
                    except sp.CalledProcessError:
                        return False

                until(offered)
                start = time.monotonic()
                cmd(["xdotool", "key", "--delay", "10", "ctrl+shift+v"])
                result = root / f"result{i}"
                until(result.exists)
                payload = result.read_bytes()
                if i == 0 and payload != START + data + END:
                    raise RuntimeError(f"Expected one ordinary bracketed paste, got {len(payload)} bytes starting with {payload[:24]!r}")
                print(json.dumps({"sample": "text" if i == 0 else "backspace bytes", "source_bytes": len(data),
                                  "one_exact_bracketed_paste": payload == START + data + END,
                                  "received_hex": payload.hex() if i else None,
                                  "trigger_to_observed_ms": round(1000 * (time.monotonic() - start))}), flush=True)
            term.wait(timeout=2)
        finally:
            for p in reversed(procs):
                if p.poll() is None:
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                p.wait(timeout=2)
```

(Continuation of the same file, lines 130–141, showing outer timeout discipline:)
```python
        elif len(sys.argv) == 3 and sys.argv[1] == "run":
            # Unwind the child cleanup block even if the enclosing GNU timeout fires.
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
            run(Path(sys.argv[2]))
        elif len(sys.argv) == 1:
            # No inherited compositor, D-Bus session, user config or notifications.
            # TemporaryDirectory owns cleanup; no debug logs, fixed sample count.
            with tempfile.TemporaryDirectory(prefix="paste-lab-") as folder:
                root = Path(folder)
                ...
                sp.run(["xvfb-run", "-a", "dbus-run-session", f"--config-file={bus}", "--", sys.executable, str(Path(__file__).resolve()), "run", folder],
                       env=env, check=True, timeout=21)
```

### The stage→verify idiom in `ghostty_probe.py`

- **Stage (line ~102):** `spawn(["wl-copy", "--foreground", "--type", "text/plain;charset=utf-8"], writable=True)`
  — wl-copy is spawned as a subprocess with piped stdin; the payload bytes are written directly to
  `owner.stdin` (a byte pipe, not a shell), then stdin is closed. `--foreground` keeps wl-copy in
  the foreground so the probe owns its lifetime (a lab-harness choice; in production wl-copy's
  default fork-and-serve is fine — external_tech_notes 5.2). Explicit `--type text/plain;charset=utf-8`
  matches 5.7's "explicit MIME, don't rely on tty autodetect".
- **Verify (line ~109):** `wl-paste --no-newline` is read back and compared `== data` for exact byte
  equality — `--no-newline` ensures wl-paste doesn't append a trailing newline, so equality means
  the staged bytes (no added newline) are what the selection holds.
- **Gate before use:** `until(offered)` polls the verification to a bounded success before the probe
  triggers the paste (ctrl+shift+v) — the target is never asked to paste content that hasn't been
  confirmed in the selection. The comment at lines 100–101 explains deliberately NOT using
  `--paste-once`: a read by a history manager would consume the one-shot offer without the target
  ever acknowledging.
- **Subprocess timeout discipline:** the probe bounds itself at multiple layers — an outer GNU
  `timeout` (SIGTERM handler at the `run` branch converts it into the `finally` kill-tree cleanup),
  `sp.run(..., timeout=21)` on the outermost launcher, `term.wait(timeout=2)` / `p.wait(timeout=2)`
  per process, and an `until(...)` readiness helper with deadline (e.g. `until(..., 7)`); the
  `finally` block SIGKILLs the whole process group of every spawned proc, in reverse order. This
  matches the repo's AGENTS.md two-layer timeout rule.

---

## Synthesis — the safe CLI copy idiom (stage → verify → report; no added newline)

1. **Stage with explicit MIME, clipboard selection only, no newline added:**
   `printf %s "$text" | wl-copy -t text/plain` (external_tech_notes 5.7) — `printf %s` (not `echo`)
   adds no trailing newline; wl-copy defaults to the CLIPBOARD selection and never touches PRIMARY
   (5.1); explicit `-t` avoids tty autodetect. In Python, spawn wl-copy with piped stdin and write
   the exact bytes, then close stdin (`ghostty_probe.py:102-105`); use `/usr/bin/wl-copy` by
   absolute path with `--foreground --type text/plain;charset=utf-8` (d2 §4 step 4).
2. **Verify before reporting success:** read the selection back with
   `wl-paste --no-newline` and require exact byte equality with the staged text
   (`ghostty_probe.py:107-113`). `--no-newline` is mandatory on the read side: wl-paste otherwise
   appends a newline, and any save/restore of a prior clipboard must also use it so restored
   content isn't grown (5.7). Do not use `--paste-once` for staging: a clipboard-history manager's
   read would consume the offer without the real target acknowledging (probe comment, lines
   100–101).
3. **Report:** surface success/failure through the existing CLI plumbing — a `format_result`
   `session` branch mirroring the status branch (d2 §4 step 3), with exit codes per ctl.py's
   existing 0/1/2/64 contract (`send_command` uses sock.settimeout; wedged daemon → ValueError →
   exit 1). Note: no truncation-reporting spec exists in the local docs yet — grep confirms "truncat"
   appears nowhere in d2; if `session --copy` output is ever truncated, the precedent is the status
   branch's rendering style, but this must be specified, not assumed.
4. **Accept environmental realities:** wl-copy forks and serves until replaced (normal paste UX,
   5.2/5.7); a running clipboard manager (cliphist et al.) WILL snapshot the staged text via
   data-control `--watch` regardless of any clearing (5.5–5.6) — treat history capture as possible
   and document it. Prior-clipboard restore is single-type-lossy (5.4).
5. **Timeout discipline everywhere:** every wl-copy/wl-paste subprocess call in the probe is
   deadline-bounded (`until(...)` with a deadline, `sp.run(..., timeout=21)`, per-proc
   `wait(timeout=2)`, SIGTERM→finally kill-tree), consistent with AGENTS.md's two-layer timeout
   rule; a production `voicectl session --copy` should bound the stage/verify subprocesses the same
   way and never block the turn on an unbounded clipboard read.

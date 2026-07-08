# Research — P1.M3.T1.S1 README.md changeset sweep (bugfix release)

This is a DOCUMENTATION task (Mode B — changeset-level overview sweep). The README is
~90% already updated: the per-feature (Mode A) doc updates landed inside the implementing
subtasks (P1.M1.T2.S2/S3, P1.M1.T3.S2, P1.M2.T3.S1). This task's job is a SURGICAL
gap-fill + ACCURACY/COHERENCE verification across the bugfix changeset. All "ground truth"
below was verified by reading the actual source files on 2026-07-08.

---

## 1. Clause-by-clause status against the item contract

| Clause | Contract requirement | README status | Action |
|---|---|---|---|
| (a) mic | `voicectl status` shows mic health; mic-retry logs rate-limited to periodic summaries | **DONE + accurate** — "Wrong microphone" section has the `mic:` line; "Logs" section has the rate-limit paragraph | VERIFY accuracy only (see §3) |
| (b) CPU fallback | daemon auto-falls-back to CPU if CUDA construction fails (degradation, not crash-loop) | **DONE + accurate** — "CPU-only mode" #3 + the cuDNN section's degradation paragraph | VERIFY accuracy only (see §3) |
| (c) install portaudio | install.sh checks for portaudio automatically | **GAP** — install.sh HAS the preflight; README "Install" numbered list OMITS it | **FILL** (the one required addition; see §4) |
| (d) exit codes | IF exit codes are documented, note usage errors now exit 64 | **conditional does NOT fire** — `grep -niE 'exit\|rc=\|\$[?]\|return code' README.md` → "(none)" | DO NOTHING (no table exists; see §5) |
| (e) coherence | verify all Mode A updates are consistent + no stale claims | **SWEEP** — check for crash-loop/silent-mic/confusing-exit staleness | VERIFY (see §6) |

**Net:** the PRIMARY deliverable is clause (c). Everything else is verification. This is a
small, surgical edit — NOT a rewrite.

---

## 2. Verified ground truth (the README must match these — read the source, don't guess)

### 2.1 `voicectl status` output format (voice_typing/ctl.py:format_result, lines ~60-95)

The status block `format_result` emits EXACTLY these lines (in order):
```
listening: on            # or off
partial: <text>
last: <text>
uptime: <Ns>s
device: <device> (<compute_type>)     # e.g. "device: cuda (float16)" / "device: cpu (int8)"
models: <final_model> + <realtime_model>   # e.g. "distil-large-v3 + small.en"
mic: ok                  # when mic_ok is True
mic: unavailable (<error>)   # when mic_ok False AND mic_error non-empty
mic: unavailable         # when mic_ok False AND mic_error empty
```
The JSON protocol fields are `mic_ok` (bool) and `mic_error` (str). The HUMAN output is the
`mic:` line. The README correctly documents the human form (`mic: ok` / `mic: unavailable
(<reason>)`) — NOT the JSON field names. The item's phrase "mic_ok/mic_error fields" refers
to the internal/protocol fields; the README's `mic:` line is the correct user-facing surface.
**README is accurate here — do not change `mic:` to `mic_ok:`.**

### 2.2 README's "Typical CUDA output" block (README ~line 245-252) — VERIFIED ACCURATE
```
listening: on
partial: this is what i am say
last: Previous sentence.
uptime: 42.3s
device: cuda (float16)
models: distil-large-v3 + small.en
mic: ok
```
Matches `format_result` exactly. Keep as-is.

### 2.3 CUDA construction-failure fallback log strings (voice_typing/daemon.py:1159-1172)

Verbatim daemon.py:
- `"CUDA recorder construction failed (%s); falling back to CPU (device=%s, compute_type=%s, models=%s/%s) — degraded but functional"`
- `"daemon started in degraded CPU mode (construction-failure fallback)"`

README quotes (elided with `...`/`(...)`):
- `CUDA recorder construction failed (...); falling back to CPU ... — degraded but functional`
- `daemon started in degraded CPU mode`

**Minor accuracy nit:** README drops the `(construction-failure fallback)` suffix on the
second string. The elision (`...`) is acceptable for a user-facing doc, but for maximum
fidelity the implementer MAY include it. Not required (the `...` convention signals elision).

### 2.4 Mic-retry rate-limit strings (voice_typing/daemon.py:964-997, 1028)

Verbatim:
- RealtimeSTT emits per-~3s: `Microphone connection failed: <e>. Retrying...`
- The rate-limit filter (`_MicRetryRateLimitFilter`, `dedup_seconds: float = 60.0,
  summary_every: int = 20`) rewrites repeats into a single WARNING:
  `"Microphone still unavailable after {count} retry attempts (last error: {error})"`

README says: full traceback once, then "a single WARNING summary roughly once per minute".
**VERIFIED ACCURATE** — the `dedup_seconds=60.0` window IS "roughly once per minute" (it
also emits on every 20th attempt; "roughly" covers that). Keep.

### 2.5 Mic probe re-runs on each arm (voice_typing/daemon.py:541-546)

`_arm()` calls `self._refresh_mic_status()` (line 546). README claim "the probe re-runs on
each arm" / "After fixing the source, arm again with voicectl toggle" — **VERIFIED ACCURATE.** Keep.

### 2.6 install.sh portaudio preflight (install.sh ~lines 48-62) — the GAP source

Verbatim behavior:
- `if ! command -v pacman` → warn "non-Arch host" and CONTINUE (skip the check).
- `elif ! pacman -Q portaudio` → print to stderr:
  `"install.sh: portaudio not installed (PyAudio system dependency). Run: sudo pacman -S
   --noconfirm portaudio, then re-run ./install.sh"` then `exit 1`.
- This runs BEFORE `[1/7] uv sync`.

So install.sh DOES check portaudio automatically and aborts with an actionable command.
The README "Install" section's numbered list (1-6) does NOT mention this. **This is the gap.**

---

## 3. Accuracy verification for clauses (a) + (b) — expected to PASS as-is

Before touching anything, the implementer should read the README sections below and confirm
they match §2's ground truth. They already do (verified 2026-07-08):

- **README "### Wrong microphone" (~line 202-217):** has the `mic:` line, `mic: ok`,
  `mic: unavailable (<reason>)`, and "the probe re-runs on each arm". ✓ Matches §2.1/§2.5.
- **README "## Logs, status, stopping" rate-limit paragraph (~line 237-241):** has the
  "traceback once then WARNING summary roughly once per minute" language. ✓ Matches §2.4.
- **README "## CPU-only mode" #3 (~line 160-171):** has the construction-failure fallback
  narrative + the exact log-line quotes + `voicectl status` shows `device: cpu (int8)`.
  ✓ Matches §2.3.
- **README "### cuDNN load error" degradation paragraph (~line 197-201):** has "degrades to
  CPU automatically instead of crash-looping". ✓ Matches §2.3 + the bugfix intent.

If any of these are found INACCURATE during implementation, fix to match §2. If accurate,
leave them UNTOUCHED (do not re-edit working prose — that risks regressions).

---

## 4. Clause (c) — the ONE required addition (Install section portaudio preflight)

**Current README "## Install" numbered list (~README lines 27-38):**
```
1. `uv sync` (creates or refreshes `.venv/`).
2. A CUDA smoke that prints `VERDICT=cuda-ok` or `VERDICT=cpu-fallback-required`.
3. Prefetches the whisper models into `~/.cache/huggingface` (warn-only on miss).
4. Installs, daemon-reloads, enables, and restarts the systemd user unit.
5. Copies `config.toml` to `~/.config/voice-typing/config.toml` if absent (never
   overwrites an existing one).
6. Prints the usage line, the tmux snippet, the Hyprland source line, and the logs
   command.
```
**Missing:** the portaudio preflight that runs BEFORE `uv sync` (§2.6).

**Required change:** prepend a step describing the portaudio preflight, renumber the list.
The verbatim replacement is in the PRP Implementation Blueprint (Task 2). Key accuracy
points the prose MUST capture (from §2.6):
- It runs `pacman -Q portaudio` (Arch-specific).
- On failure it ABORTS (exit 1) with the exact command `sudo pacman -S --noconfirm portaudio`
  and tells the user to re-run `./install.sh`.
- Non-Arch hosts (no pacman) get a warning and CONTINUE (no abort) — the user installs
  portaudio themselves.

This complements (does not duplicate) the "## Requirements" bullet (~line 18) which already
says: "`portaudio` (PyAudio build dep). Check it with `pacman -Q portaudio`." — keep that
bullet; it's the "you need this" statement, while the new Install step is "install.sh
verifies it for you". They are complementary, not redundant.

---

## 5. Clause (d) — conditional does NOT fire (NO exit-code table in README)

`grep -niE 'exit|rc=|\$[?]|return code' README.md` → "(none)". The README documents
`voicectl status` OUTPUT but never its exit codes. The item's clause (d) is explicitly
conditional ("IF exit codes are documented, note … exit 64"). Since none are documented,
the conditional is unsatisfied → **DO NOTHING for (d).**

The exit-code-64 contract (bugfix Issue 7 / P1.M2.T4.S1) IS documented where it belongs: in
`voice_typing/ctl.py`'s module docstring + `main()` docstring + argparse `description=` (all
updated by that task, now landed). Adding a NEW exit-code table to the README is OUT of scope
(this task sweeps EXISTING cross-cutting docs; it does not introduce new doc surfaces). The
"changeset-wide README sync is P1.M3.T1.S1" note in the P1.M2.T4.S1 research referred to
checking the conditional, not mandating a table.

**Implementer guidance:** verify the grep still returns none AFTER your edits (you should not
have added any). If it does, you over-reached — remove the exit-code addition.

---

## 6. Clause (e) — coherence sweep: stale-claim hunt

Scan the README for claims that contradict the post-bugfix state. Verified clean spots:
- "Restart=on-failure loops it forever" (README ~line 143, Voice-activity section) — this is
  about a BAD CONFIG KEY (TypeError), which WOULD still crash-loop (the CPU fallback is for
  CUDA construction failure, NOT config errors). **NOT stale — keep.** Do not "fix" this.
- No claim of "silent mic failure" remains (the mic-health surface + rate-limit are now
  documented). ✓
- No claim of "crash-loop on CUDA failure" remains (the degradation narrative is now there). ✓
- The "## Requirements" bullet "NVIDIA GPU with CUDA drivers. Optional: the daemon
  auto-falls-back to CPU (slower)." (~line 13) is consistent with the CPU-only-mode section. ✓

The sweep should find NOTHING to change beyond clause (c). If the implementer finds a genuine
stale claim, fix it minimally; if not, do not invent edits (clause (e) is a verification pass).

---

## 7. Style + scope boundaries (the README's voice)

- **README voice** (line 6-7): "for two readers: dustin, six months from now, and anyone who
  clones the repo … assumes a Linux power user who wants exact commands, not hand-holding."
  → TERSE, command-first, no marketing language, no hand-holding. Match this EXACTLY in any
  added prose. No exclamation marks, no "exciting", no em-dash spam (the existing README uses
  plain hyphens and short sentences).
- **Scope:** edit README.md ONLY. Do NOT touch any source file, PRD.md, tasks.json,
  prd_snapshot.md, .gitignore, install.sh, ctl.py, daemon.py, etc. (this is Mode B docs,
  not code). The bugfix code is DONE; this task only documents it.
- **No new files.** Single-file edit.
- **Don't restate bugfix history** (Issue numbers, "this was a bug") — the README is
  user-facing, not a changelog. Describe behavior, not the fix. (e.g. write "install.sh
  checks for portaudio", NOT "Issue 6 fixed: portaudio check added".)

---

## 8. Validation approach (no test framework applies to a README edit)

- No pytest/ruff/mypy gate for a markdown file. Validation is:
  1. `grep -nE '^#{1,3} ' README.md` — section structure intact (15 headers pre-edit).
  2. `grep -niE 'portaudio' README.md` — now appears in BOTH Requirements AND Install.
  3. `grep -niE 'exit|rc=' README.md` — STILL "(none)" (clause (d) not over-reached).
  4. Manual read of the edited Install section for accuracy against §2.6 / §4.
  5. Optional: render-check (markdown is valid) — `grep -c '^```' README.md` should be EVEN
     (balanced fenced blocks). Pre-edit count is even; post-edit must stay even.
- A "links still valid" check is unnecessary (README has one internal anchor link:
  `[Wrong microphone](#wrong-microphone)` in the Logs section — unchanged by clause (c)).

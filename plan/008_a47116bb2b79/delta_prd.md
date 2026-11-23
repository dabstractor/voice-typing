# Delta PRD: Rev 3/Rev 4 remainder — media ducking, bulk text delivery, defect pipeline

**Base:** PRD.md as of Rev 2 (previous session's spec). **Current:** PRD.md Rev 4 (HEAD 2335a9e, 2026-11-22).
**Diff size:** large — one new feature section (§4.2quinquies, ~90 lines), one very large new normative section (§4.2sexies R.1–R.8, ~180 lines), plus a defect-triage block in §8. However, **most of the Rev 3 prose diff is already implemented and verified on `main`** — this delta PRD exists to (a) fence off that landed work from re-implementation and (b) spec the three genuinely unimplemented work packages.

**Precedence (from the current PRD, governs this delta):** for `output.delivery="bulk-text"`, §4.2sexies supersedes conflicting output/keyboard/fallback/logging/acceptance instructions, including §4.2quater, §4.3, T8, and acceptance #11–12. Rev 3 takes precedence on the legacy `stream-edit` path. Recorder lifecycle, installation safety, local processing, and unrelated requirements still apply.

Where it says MUST, do it; where it says SHOULD, do it unless it demonstrably fails on this machine.

---

## 1. Diff analysis — what changed vs the Rev 2 spec, and its implementation state

| PRD change | Rev | Repo state at HEAD 2335a9e |
|---|---|---|
| Minimal-diff tail revision (LCP `k`, rewind only `len(tail)−k`, ≥2 s divergence debounce; commit correction never debounced) — §4.2quater rule 1/2 | Rev 3-era | **LANDED** `4640041`, `cf2dfb1`, `eac2d03` (case-insensitive extends). `voice_typing/streaming.py` `StreamingOutput` |
| HALT (any real keypress while armed disarms; modifier-only exempt; 1.5 s grace; legacy freeze via `cancel.keypress_action="freeze"`) — §4.2quater rule 5 | Rev 3 | **LANDED** `0e7dd05`; config key present (`config.py:181`) |
| Immediate stop default, graceful drain opt-in (`asr.graceful_stop`) | Rev 3 | **LANDED** `0e7dd05`; `config.py:79` |
| Rewind accounting invariant (clamp to own tail, journal, dropped finals reset boundary) | Rev 3 | **LANDED** (clamped rewinds, `0e7dd05`; `tests/test_zero_diff_rewind.py` 3/3) |
| Session-boundary audio purge (clear buffered audio at EVERY arm AND disarm) | Rev 3b | **LANDED** `965f903` |
| Continuation separator (lazy, prefix-diff-invisible, rewind-deletable) | Rev 3c | **LANDED** `26d570b` (`streaming.py` `_lead_sep`) |
| Injector pacing (~12 ms/char, serialized spawns ≥25 ms floor, ydotool primary, separators ride inside text payloads) | Rev 3d | **LANDED** `e5409a1` + `f0d8d0a` (persistent ydotoold socket) — **but the socket client has the SOCK_STREAM/SOCK_DGRAM bug; fix unmerged (D3)** |
| Robustness invariants (supervised abort handler, `VOICECTL_TIMEOUT` socket bound, evdev re-enumeration, SUPER+ALT+Escape panic bind) | Rev 3 | **LANDED** (`ctl.py:164`, `key_listener.py`, `hypr-binds.conf:60`) |
| `asr.compute_type` config key (float16 default) | 2026-11-18 | **LANDED** `bcfd171`, `48a7eb8` |
| §4.2quinquies Media ducking | new | **NOT IMPLEMENTED** — no `AudioDucker`, no `[audio]` config keys (verified: zero grep hits) → **D1** |
| §4.2sexies Bulk text delivery (R.1–R.8) | Rev 4 | **NOT IMPLEMENTED** — no `output.delivery` key, no bulk controller/TargetAdapter, no `voicectl session` → **D2**. Research spikes exist and are citable: `tools/paste-lab/`, `tools/im-lab/` (route RESOLVED 2026-11-22), `tools/asr-lab/` |
| §8 Known-defects block (datagram merge, cancel auto-repeat, suppression latch) | 2026-11-18 | **OPEN** — `fix/ydotoold-datagram` (33321c6, 11 tests) exists as an unmerged branch; two investigations open → **D3** |
| T8 minimal-diff asserts; acceptance #11 refresh; #13 added | Rev 3/4 | #11 **LANDED** (ACCEPTANCE.md row 11, 77 passed across streaming suites); #13 awaits D2 |
| §9 future-work prose (hybrid engine, hotwords, asr-lab findings) | informational | No action — out of scope by definition |

**Do not re-implement anything in the LANDED rows.** The delta session builds only D1, D2, D3 below.

---

## 2. Scope delta — the three work packages

### D1. Media ducking while listening (§4.2quinquies — implement in full)

The spec in §4.2quinquies is normative and complete; implement it as written. Summary of the binding requirements (all details in the PRD):

- **New module** `voice_typing/audio_ducker.py` (or similar): an `AudioDucker` protocol with `engage()`/`release()` over a mocked-able backend. Two tiers, strictly best-effort: (1) **MPRIS pause** (primary) — pause `Playing` players at arm; at disarm resume ONLY players we paused, that were Playing before, and that are still Paused now (user sovereignty). (2) **Sink-volume duck** (fallback tier) — store default-sink volume at arm, set `duck_volume_pct`, restore at disarm ONLY if current volume still equals what we last set.
- **Lifecycle wiring:** engage where the arm toast fires; release on EVERY disarm path — manual stop/toggle-off, idle auto-stop, Rev 3 HALT keypress disarm, daemon quit — but NOT on Backspace-cancel (mic stays hot). Wire inside `voice_typing/daemon.py` at the existing arm/disarm seams (the same sites that fire the Recording/Recording-Stopped toasts); do not add a new top-level thread when the existing arm/disarm methods suffice.
- **Crash-safety:** `ducked` field in the feedback state file (extend `voice_typing/feedback.py` state writer); post-crash restart self-heals (best-effort release at startup when set); add a best-effort `ExecStopPost` restore to `systemd/voice-typing.service`.
- **Failure discipline (non-negotiable):** ducking is an enhancement, NEVER a gate. Every audio call is a subprocess under a hard timeout ≤1 s; failures journal ONE line and are otherwise invisible; arm latency must not measurably change (engage runs concurrently with recorder arming, arm does not wait). Engage/release idempotent; release without engage is a no-op.
- **Config (Mode A doc-with-work):** new `[audio]` section — `duck_mode = "off"` (`"mpris"` | `"volume"` | `"off"`) and `duck_volume_pct = 15` — added to `voice_typing/config.py` + `config.toml` in lockstep with the key-set test (PRD: 24 → 26 keys; find the exact pinning test in `tests/test_config_repo_default.py` / `test_config.py` and update it). Ships `"off"`; the default flips to `"mpris"` **the round this lands** (i.e., in this delta, once tests pass). Self-documenting comments in `config.toml`.
- **Tests (unit, no real audio — mocked backend):** the six PRD cases (a) resume-only-what-we-paused (user-paused player stays paused); (b) volume restore skipped when user changed volume mid-dictation; (c) release fires on every disarm path incl. HALT and auto-stop; (d) a hung backend call (mocked 5 s sleep) does not delay arm beyond bound; (e) engage/release idempotence; (f) crash-recovery: `ducked` flag → release at next daemon start.
- **Acceptance (PRD):** music playing → arm → pauses within ~1 s, resumes at stop; `duck_mode="volume"` ducks to 15% and restores exactly; user changes never overridden; journal shows engage/release lines; `duck_mode="off"` byte-identical to today.

### D2. Bulk text delivery — paste as policy (§4.2sexies Rev 4 — the dominant package)

**§4.2sexies R.1–R.8 is the normative specification; this PRD adds only work breakdown and repo grounding — read R.1–R.8 before planning tasks.** Binding shape:

- **New code, separate from legacy:** a bulk-delivery controller + `TargetAdapter` (new modules, e.g. `voice_typing/bulk_delivery.py` + adapter modules) — SEPARATE from `StreamingOutput` (`voice_typing/streaming.py`) and `typing_backends.py`, which stay untouched for `stream-edit`. The bulk adapter MUST NOT expose `type_character`/`press_backspace` or any typing fallback. Core adapter contract per R.3: `acquire` (bind the specific editable field, opaque handle + revision, fail BEFORE delivery for non-editable/password/selected/unidentified fields), `show(session, utterance, seq, expected_revision, rendered_span)` executed on the target's event loop returning `applied | unchanged | refused | unknown`, `finalize` (zero-diff ⇒ zero edits; differing ⇒ ONE replacement of verified owned text), `leave`/`cancel`.
- **Route is DECIDED — do not re-run discovery (R.2/R.4):** `zwp_input_method_v2` adapter is PRIMARY (insert = `commit_string`+`commit`; correction = `delete_surrounding_text(before,0)`+`commit_string`+`commit` in ONE atomic commit; verify via `surrounding_text`; takeover via keyboard-grab key events). Field-class coverage per the R.2 matrix: full on GTK-class, insert-only on foot/kitty, UNAVAILABLE on ghostty 1.3.1 (clipboard paste as insert fallback there only, under the R.6 contract). The pi chat-prompt milestone rides the documented extension seam (`ctx.ui.setEditorComponent()` / `ctx.fork({position:"before"})` — prove at G3). Handle the exclusive seat-IM-slot `unavailable` event by reporting `delivery_state=unsupported` — never displace the user's IME. Chunk corrections >4000 bytes without violating the one-edit rule, else refuse with `delivery_reason`.
- **Implementation order (R.4, mandatory):** (1) G1 baseline FIRST; (2) G2 controller vs fake target; (3) prove insert AND correct in real fields before any mic integration; (4) then integrate recognition, keeping the first working route runnable. Development MUST NOT change the operator's service, config, or bindings as a side effect — `output.delivery` stays opt-in (`"stream-edit"` default) until G6.
- **G1 baseline:** record pre-change results of `test_streaming_commit`, `test_zero_diff_rewind`, key-listener, control-socket, and config suites; reconcile the legacy separator failures measured at the 2026-11 handoff (`test_streaming_commit.py` 10 failed / 22 passed; `test_zero_diff_rewind.py` 3/3) against the lazy-separator contract and separate them from NEW failures — no blanket skips, no legacy behavior changes to fake parity. (Current ACCEPTANCE.md cites 77 passed across the three streaming suites — re-measure at this HEAD and record what is actually red before touching anything.)
- **Ordering/takeover/failure (R.5):** session generation per arm; utterance identities at the decode source carried through `RecorderHost`'s event relay (extend the `partial`/`final` payloads); `_dispatch` enqueues-and-returns on the reader thread (no subprocess/editor wait under the control lock); one writer per target, one op in flight, bounded queue (default 32; overflow stops delivery, never drops a barrier); takeover revoked AT THE TARGET (key/caret/selection/click/focus/tab-switch/target death), arming chord ignored; bulk `voicectl cancel` performs NO legacy `len(tail)-1` compensation — route it BEFORE `daemon.cancel`'s legacy backspace call; any `unknown`/`refused`/stall past the 250 ms engineering deadline disarms bulk delivery AND recording with one concise reason — never retry an operation that may have landed.
- **Config + status + CLI (Mode A doc-with-work):**
  - `config.py`/`config.toml`: `output.delivery = "stream-edit"` (add; `"bulk-text"` requires `streaming=true`, `graceful_stop=false`, `keypress_action="disarm"` — enforce at load with a clear error). Key-set test updated in lockstep.
  - `feedback.py` state + `voicectl status`: `delivery_mode`, `delivery_state` (`inactive|active|unsupported|fault`), `delivery_reason`, last confirmed op — never the surrounding user document. New bulk-path logs carry counts and times, not recognition text.
  - `ctl.py`: add `session` command — prints the most recent COMPLETED session; `session --copy` copies exactly that text (no added newline, never types/erases/submits, exit 1 + clipboard untouched when none exists; truncation reported on stderr and in the reply). Update `_COMMANDS`, docstring, `--help` epilog. Any bind for it is USER-assigned — never install one, never touch `hypr-binds.conf` for this.
  - **Session recovery (R.6):** daemon memory holds the last nonempty arm→disarm session (accepted final per utterance + last visible/recognized unfinished tail, exactly once each; rejected final keeps only the shown tail; deliberate cancels and late finals excluded; previous completed session survives empty/failed arms; ≤2 sessions × 1 MiB UTF-8, on overflow keep newest-complete + report truncation; cleared at daemon exit; no crash persistence, no new transcript-bearing logs).
- **Clipboard contract (R.6, only if the clipboard fallback is used):** preserve all prior formats/bytes, distinguish original ownership from a later identical copy, protect simultaneous user paste, keep partials out of the configured clipboard-history watcher, PRIMARY untouched. If unprovable with the local manager → adapter unavailable; never disable the manager. G4 gate applies.
- **Verification gates (R.7 = PRD T9):** G2 fake-target traces (the enumerated deterministic scenarios); G3 real-field matrix (pi prompt in isolated Ghostty first, then graphical editor, browser field — assert editor contents + caret + visible prompt; rows report `untested | insert-only | blocked (reason) | verified`); G4 clipboard (only if used); G5 timing (speech-end→word-visible median ≤500 ms, p95 <1 s; update-ready→first-changed-frame p95 ≤100 ms insert / ≤50 ms correct; ≥100 insertions and ≥100 corrections per claimed route; a sustained five-word backlog or sentence-end dump fails regardless of medians). All under repo timeout discipline; automation MUST NOT exercise the live desktop, real clipboard, default mic, or active service — private compositor + synthetic input + isolated app instances; only fixtures enter version control; evidence stays bounded (AGENTS.md Rule 3).
- **G6 graduation:** flipping the shipped default additionally requires the verified G3 matrix plus ≥3 representative completed writing sessions beating 110 wpm effective proofread throughput — operator-dependent evidence. If it cannot be produced this session, report that and stay opt-in. Never claim "works on Wayland" from one row; a passing transport probe never flips a NOT VERIFIED claim to passed.
- **Acceptance:** PRD §7 item 13 verbatim (visibility with no typing fallback; one-edit corrections; zero-diff ⇒ zero edits; takeover/refusal/unknown stops delivery without retries or post-stop writes; `voicectl session [--copy]`; graduation gated on G3+G6).

### D3. Legacy defect pipeline (§8 Known defects — small, independent, NOT prerequisites for D2 per R.8)

1. **Merge `fix/ydotoold-datagram`** (branch exists, commit 33321c6, 11 tests, packing proven byte-identical to the real CLI by two captures) — fixes `ydotoold_client`'s SOCK_STREAM-against-SOCK_DGRAM failure (every connection since f0d8d0a failed with Errno 91 → 56 journal warnings/week of degraded per-burst CLI spawns). **Plus** add the 6 ms press→release contact gap to the socket path (protocol finding: the CLI gaps every event; the socket path currently does not). Land on `main` as a normal reviewable merge; keep tests green.
2. **Cancel auto-repeat compensation:** physical Backspace auto-repeat violates the one-keystroke=one-character assumption → under-compensation manufactures belief-desync. Fix per §8: fire cancel only while armed AND a tail is pending; idempotent; compensation by subtraction (value 2 = autorepeat is already filtered in `key_listener.py` — audit the daemon-side accounting against sustained holds).
3. **Cancel-suppression window latch:** latched window dropped finals 4× in the week of 2026-11-12..18. `4640041` ("self-healing cancel window") landed a partial fix — investigate whether the latch timing is fully closed (replay the incident traces / add a regression test; if already closed, record that evidence in the task, don't gold-plate).

---

## 3. Reference completed work (do NOT rebuild)

- Rev 3 machinery (HALT, instant stop, clamped rewinds, purges, separator, pacing, robustness invariants): commits `0e7dd05`, `965f903`, `26d570b`, `e5409a1`, `f0d8d0a`. `voice_typing/streaming.py`, `daemon.py`, `key_listener.py`, `ctl.py`, `ydotoold_client.py`.
- Minimal-diff revision + debounce + case-insensitive extends: `4640041`, `cf2dfb1`, `eac2d03`; pinned by `tests/test_streaming_core.py`, `test_streaming_commit.py`, `test_zero_diff_rewind.py`.
- `compute_type` key: `bcfd171`/`48a7eb8`.
- Labs (evidence, citable — R.2 table): `tools/paste-lab/ghostty_probe.py`, `tools/im-lab/` (wlwire, im_probe, fields, imlab_run, globals), `tools/asr-lab/` (bake-off, voice clips). Route discovery is DONE — `2335a9e`.
- Prior research that still applies: `plan/007_cfc245548aec/architecture/` (`realtimestt_internals.md` for child seams — R.5's utterance-identity work extends the same event relay; `daemon_control_map.md` for arm/disarm seams D1 hooks; `substrate_map.md` for config/test pinning patterns). Note those files describe the Rev 2-era tree — line numbers have drifted; trust structure, re-locate symbols.

## 4. Documentation impact

**Mode A — doc-with-work (rides with each package, not standalone tasks):**
- D1: `config.toml` `[audio]` comments (the user-facing reference); `voice_typing/daemon.py` docstring ducking note; `systemd/voice-typing.service` ExecStopPost comment.
- D2: `config.toml` `output.delivery` comment; `ctl.py` docstring/`--help` (`session`); `feedback.py` state-field docs (`delivery_*`); adapter module docstrings carrying the R.2/R.3 contracts.
- D3: none beyond commit message + test names.

**Mode B — changeset-level sync (final task, depends on all above):** `README.md` — new Media ducking section (tiers, config, sovereignty guarantees), new Bulk text delivery section (opt-in flag, delivery states, `voicectl session`, explicit "unverified until G3/G6" framing per R.2's no-over-claim rule), config table rows for `[audio]` + `output.delivery`, troubleshooting additions (seat IM exclusivity/fcitx5, terminal field-class matrix, clipboard contract). `install.sh` printed usage gains `session`. `tests/ACCEPTANCE.md`: add the ducking row and row #13 with actual command output links; refresh row #12 if D3 changes cancel behavior. Every claim verified against the code as landed — no aspirational prose.

## 5. Delta acceptance criteria

1. **D1:** the six ducking unit tests pass (mocked backend); the §4.2quinquies acceptance scenarios behave as specified; `duck_mode="off"` is byte-identical to today; default is `"mpris"` with evidence; config key-set test updated (24 → 26).
2. **D2:** gates G1–G5 executed in order with recorded evidence (bounded, fixtures only); G3 matrix rows for the pi prompt in isolated Ghostty at minimum, reported `verified | insert-only | blocked (reason)`; zero typing-fallback paths reachable in bulk mode; `output.delivery="bulk-text"` enforces its precondition triple at config load; `voicectl session [--copy]` semantics per R.6; `stream-edit` (default) behavior unchanged — G1 suites show no new failures vs the recorded baseline. G6 either satisfied with real writing-session evidence (default flips) or explicitly reported unmet (stays opt-in). No over-claiming: any field/latency not verified stays labeled unverified.
3. **D3:** `fix/ydotoold-datagram` merged with the 6 ms gap, suites green, journal-noise regression gone (assert via tests, not journal scraping); cancel auto-repeat audit closed with a regression test or recorded evidence; suppression-latch investigation closed the same way.
4. All work under AGENTS.md discipline (two timeouts on every non-trivial command; never foreground the daemon; bounded scratch); everything committed to `main` with sensible messages.

## 6. Out of scope (unchanged from PRD §9 + R.8 notes)

- Route discovery (RESOLVED — never re-run); streaming-transducer migration (DEAD per asr-lab); recognition-quality work beyond R.8's callback comparison (hybrid engine, hotwords — future work); making ducking a gate on arm; changing the operator's service/config/bindings as a side effect of D2 development; Graduation (G6 default flip) without the writing-session evidence.

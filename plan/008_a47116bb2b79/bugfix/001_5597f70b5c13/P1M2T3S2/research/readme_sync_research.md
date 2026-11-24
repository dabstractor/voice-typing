# Research Note — P1.M2.T3.S2: Sync README.md to the landed fixes and limits

> Mode B docs task: ONE file edited (README.md). Static inspection only — no live services, no
> daemon, no CLI runs. Consumes: P1.M1.T1.S3 (hermetic), P1.M1.T2.S1 (panic pin),
> P1.M1.T3.S1 (CPU guidance), P1.M2.T2.S3 (refreshed G5), P1.M2.T3.S1 (refreshed G6, parallel).

## §0 — VERIFIED FACTS (live tree, 2026-11-24)

| # | Fact | Evidence |
|---|---|---|
| F1 | hypr-binds.conf ships THREE binds: toggle (CTRL SUPER ALT, D), cancel (SUPER ALT, Backspace), and the panic bind `bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing` with a comment calling it a "hard-kill … bypasses voicectl and the control socket entirely (systemd SIGTERMs/SIGKILLs)". The conf's own wording overstates; the README must be precise (item LOGIC): it is an **explicit systemd stop bypassing the socket, NOT an instant SIGKILL** — SIGTERM → bounded single-flight teardown (join ≤5 s + killpg, README already documents this at ~:626-637) → SIGKILL only at the TimeoutStopSec=15 outer net. | hypr-binds.conf tail |
| F2 | The panic-bind test exemption LANDED (P1.M1.T2.S1): `tests/test_systemd_unit.py:330-336` carries `_PANIC_BIND = ("SUPER ALT", "Escape", "exec", "systemctl --user stop voice-typing")` — the portability check exempts exactly this tuple. The suite carries no unexplained red for it. | test_systemd_unit.py:330-336 |
| F3 | README's Hotkey section (@82) documents ONLY the two voicectl binds (block @103-104). The panic bind is entirely undocumented in README — the gap this task closes. | README.md:82-115 |
| F4 | G5 refreshed and ON DISK (P1.M2.T2.S3, Complete): `tests/G5_TIMING_EVIDENCE.md` dated 2026-11-24, HEAD 2909e03 — **both routes FAIL**. pi-ghostty: speech→visible median **6714.0 ms** (improved 7786.2→6714.0, "−14%" via S2's 0.05 s bulk cadence + S1's prompt dispatch), sentence-end dump persists, counts 14/14 < 100, NEW paint-qualified frame basis (S5 observer) FAILs 11266.2/13150.8 ms ready→first-changed-frame. im-gtk: counts 4/0 < 100, backlog max 57 words sustained, frame basis still the **field change-log proxy** → frame bars UNVERIFIED. "BUG-002 and PRD acceptance #13 remain OPEN … G6/README claims must not proceed on this evidence (P1.M2.T3 owns them)." | G5_TIMING_EVIDENCE.md:1-40 |
| F5 | G6 current doc (pre-S1-refresh on disk): STAY OPT-IN, unmet A/B/C/D @ 2026-11-23 69952ae. S1's CONTRACT (implementing now): decision stays STAY OPT-IN (A/B/D independently unmet; C still fails per F4), new current block + verbatim dated archive, and it RECORDS the decision + reason "for P1.M2.T3.S2's README use". README must quote S1's CURRENT block (new date/@HEAD), not the 69952ae line. | G6_GRADUATION.md:27; S1 PRP |
| F6 | Hermetic fixture LANDED (P1.M1.T1.S1/S2): `tests/conftest.py` hosts `hermetic_daemon_media` (opt-in fixture) + `hermetic_cfg()` builder — daemon-constructing tests get a fake media ducker; the live session bus is never touched. P1.M1.T1.S3 pinned default-to-fake wiring + ordered subprocess isolation. | tests/conftest.py:3-38 |
| F7 | G1 CPU addendum LANDED (P1.M1.T3.S1): `tests/G1_BASELINE.md` now records test_daemon.py as "CPU-only (~16 s, hermetic post-T1)" with its named 20-case baseline + set-diff rule in the addendum at the end. | G1_BASELINE.md:9-11, ~278 |
| F8 | All README link targets resolve: `plan/008_a47116bb2b79/architecture/g3_field_matrix.md`, `…/g4_clipboard_verdicts.jsonl`, `tests/D1_DUCK_EVIDENCE.md`, `tests/G6_WRITING_SESSIONS.md` all exist. | ls verified |
| F9 | Media ducking README section (@204-249) is CONSISTENT with the landed code: mpris default, sovereignty triple, crash safety (ducked flag + ExecStopPost + ducking_heal), D1 evidence 12/12. Audit-only; no contradiction found at research time. Config table: `audio.duck_mode` "mpris", `audio.duck_volume_pct` 15, `output.delivery` "stream-edit" — all still correct. | README.md:204-249, 343-382 |
| F10 | Production partial source remains **stabilized** (daemon.py:221 `_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"`, with a plain/stabilized map @233-234 for the paired comparison). The remediation was prompt dispatch + cadence, NOT a callback swap — README must not claim the update callback is wired. | daemon.py:219-234 |
| F11 | README section map (line anchors): Hotkey @82; Media ducking @204; Bulk @251 (G6 date cite @257; timing paragraph ~@295-299 with the stale "12.6 s"); Feedback @324; Configuration @343; Logs @537; Model lifecycle @591; file ends ~@638. | grep verified |

## §1 — THE README EDIT MAP (4 edits, 1 audit)

### Edit 1 — Hotkey section (@82-115): document the panic bind
- Add the third bind line to the code block (mirror hypr-binds.conf): `bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing`.
- Add a short paragraph (wording per item LOGIC + F1): **Super+Alt+Escape is the panic bind — an explicit `systemctl --user stop` that bypasses voicectl and the control socket entirely** (works even when the socket is wedged). It is **not an instant SIGKILL**: systemd SIGTERMs the main process and the daemon's bounded single-flight teardown completes in seconds (link the existing [Logs/Model lifecycle] teardown wording); SIGKILL only fires at the unit's outer `TimeoutStopSec=15` net. A stop is intentional — `Restart=on-failure` does not bring it back — so re-arm with `systemctl --user start voice-typing` after the wedge is cleared.
- Optionally one clause noting the portability test exempts exactly this one documented bind (F2) — keep it to a clause, not a paragraph.

### Edit 2 — Bulk text delivery (@251-306): align status + timings to F4/F5
- **G6 cite (@255-258)**: replace the `(2026-11-23 @ 69952ae)` decision quote with S1's refreshed CURRENT block's decision line + date/@HEAD (verbatim string match — see validation). Decision remains STAY OPT-IN; all four conditions still unmet.
- **Outstanding-inputs sentence (@258-263)**: mirror S1's refreshed "Outstanding inputs" (G5 timing still outstanding with F4's specifics; A/B/D items unchanged from S1's doc — do not invent or drop).
- **Timing paragraph (@295-299)** — replace the stale "12.6 s" text with the 2026-11-24 qualification (F4): both routes FAIL; pi-ghostty median improved 12.6 s → **6.7 s** (update-granular dispatch + 0.05 s bulk cadence landed) but stays ~13× the 500 ms bar, sentence-end dump persists, and its **paint-qualified** frame bars (real visible change) FAIL at 11.3 s / 13.2 s p95; im-gtk stays count/backlog-bound (4 insertions / 0 corrections vs ≥100/≥100; 57-word sustained backlog) and its frame bars remain UNVERIFIED (**field change-log proxy** — an editor-state proxy, not paint).
- **Add the scope distinction (item LOGIC, mandatory)**: these timings come from the isolated G5 lab's instrumentation on EXACTLY TWO routes (im-gtk, pi-ghostty); the im-gtk frame numbers are an editor-state proxy, the pi numbers are paint-qualified; they are **not** a claim about the field-class matrix above (G3), and **nothing is operator acceptance** (that is G6 condition D — 0 sessions on record). Keep "no route streams words at speaking pace yet; BUG-002 / acceptance #13 remain open" as the closer.
- Do NOT soften "opt-in, experimental"; do NOT change the default (`stream-edit`); do NOT add promotion language anywhere.

### Edit 3 — NEW short "## Running the tests" section (end of file, after Model lifecycle ~@638)
4-6 lines consuming F6+F7 (the "changed test isolation/CPU pointers … only where useful" clause):
the unit suite is hermetic (daemon-constructing tests build against the fake media ducker via
`tests/conftest.py`'s `hermetic_daemon_media` / `hermetic_cfg` — running pytest never touches the
live session bus or pauses your playing media, and subprocess-recorder tests stay order-independent);
`tests/test_daemon.py` is CPU-only (~16 s, no CUDA, no model load) with its 20 legacy
lazy-separator reds baselined in `tests/G1_BASELINE.md` (G1 CPU addendum) — diff failures against
that named set; run one file per call under GNU timeout.

### Audit — Media ducking (@204-249) + validation-overview wording
No content change expected (F9). Re-read for contradictions against the landed state; the only
known neighboring staleness is the First-run ducking sentence (already correct). If a genuine
contradiction is found (e.g., a claim tests touch the bus), fix minimally and record it.

## §2 — WHAT MUST NOT CHANGE
- hypr-binds.conf (its "hard-kill" comment stays as-is — this task is README-only, Mode B).
- tests/G5_TIMING_EVIDENCE.md, tests/G6_GRADUATION.md (S3/S1 own them — consume verbatim).
- Any default/config wording that is already correct (mpris default, delivery stream-edit).
- The G3 matrix table (versions are part of the claim; unchanged).
- PRD.md / companion specs / tasks.json (forbidden).

## §3 — VALIDATION (static inspection only; mock/no live services or CLI — item LOGIC)
```bash
cd /home/dustin/projects/voice-typing
# 1. Bind block matches hypr-binds.conf (3 binds, exact MODS/key/cmd):
diff <(grep '^bind = ' hypr-binds.conf) <(sed -n '/^bind = CTRL SUPER ALT, D/,/^bind = SUPER ALT, Escape/p' README.md | grep '^bind = ') && echo BINDS-MATCH
# 2. README's G6 decision line == S1's current G6 line (string equality):
grep -o "G6 DECISION: STAY OPT-IN ([^)]*)" README.md tests/G6_GRADUATION.md | sort -u | wc -l   # → 1 unique form
grep -n "Assessed" tests/G6_GRADUATION.md | head -1    # S1's current date — README cites the same date
# 3. Every timing number README cites exists in the G5 file:
for n in 6714.0 11266.2 13150.8 57 12.6; do grep -q "$n" tests/G5_TIMING_EVIDENCE.md && echo "$n ok"; done
# 4. Links resolve + config defaults match:
ls plan/008_a47116bb2b79/architecture/g3_field_matrix.md plan/008_a47116bb2b79/architecture/g4_clipboard_verdicts.jsonl tests/D1_DUCK_EVIDENCE.md tests/G6_WRITING_SESSIONS.md
grep -n 'duck_mode.*"mpris"\|duck_volume_pct.*15\|delivery.*"stream-edit"' voice_typing/config.py | head -3
# 5. No promotion leaked: the Bulk header still says opt-in/experimental; no "graduated"/"verified" claims:
sed -n '251,253p' README.md; grep -niE 'graduat|operator-accepted|verified on' README.md | grep -v G6 | head
# 6. Pure sanity (no daemon, no service): timeout 300 .venv/bin/python -m pytest tests/test_config.py -q
git status --short   # → README.md only
```

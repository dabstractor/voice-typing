Create a PRP for Subtask P1.M1.T1.S1 of the PRD. Store it at plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T1S1/PRP.md.

SCOPE: Write ONLY this item's PRP (P1.M1.T1.S1). You were asked for ONE PRP. Writing PRPs for other items in this session is allowed ONLY after you clear the MULTI-PRP BATCHING POLICY in the prompt (full task tree + full PRD + thorough per-item research for EVERY PRP you write). When in doubt, write one.
<item_title>Establish a hermetic media fixture at the first-arm seam</item_title>
<item_description>CONTRACT DEFINITION:
1. RESEARCH NOTE: architecture/system_context.md § BUG-001: _build_default_ducker is inert until _arm; the earlier ducking_heal.read_ducked_flag can independently start a live heal. There is no existing tests/conftest.py.
2. INPUT: voice_typing/daemon.py:VoiceTypingDaemon(..., ducker=), _build_default_ducker, and tests/test_key_listener.py:_wire_daemon with fake recorder/backend/mic.
3. LOGIC: Add an opt-in, function-scoped tests/conftest.py fixture hermetic_daemon_media. Give it a helper callable (cfg) -> cfg that makes a test-owned config with duck_mode='off' and private test state; preserve unrelated fields and never mutate a production default or a shared supplied config. Provide a fail-closed check at the daemon's factory lookup and isolate persisted duck-flag reads on fixture invocation, not at collection. Apply it at _wire_daemon/arming callers. Mock real media, recorder, mic and backend; never globally patch subprocess.run or allow a real media command to prove failure.
4. OUTPUT: hermetic_daemon_media fixture and migrated key-listener arms consumed by P1.M1.T1.S2 and P1.M1.T1.S3. Ordinary arm/stop starts neither vt-ducking nor vt-duck-heal, even if operator state would say ducked; unguarded factory use under the fixture fails synchronously.
5. DOCS: none — test-only contract; document fixture use and intentional fake-heal exceptions in its docstring.</item_description>
<prd_selectors>["h2.0","h2.2","h3.0","h2.5"]</prd_selectors>
<selected_prd_content>
heading:h2.0:
## Overview

End-to-end PRD-validation hunt over the Rev-4 delta (D1 media ducking, D2 bulk-text delivery, D3 legacy defects) at HEAD 573d78f. Ran \~1,450 pure tests across 30+ suites: bulk contracts/controller/dispatch (126), ducking (69+31), IM transport/adapters (304), config/feedback/ctl/session (213), support labs (194), the G1 15-suite set, and the full test\_daemon.py — plus direct behavioral probes (rendered\_equal Unicode cases, session-recovery exclusion rules and the 1 MiB cap, config precondition triple, busctl side-effect proof, live voicectl CLI). Verified D3 closure landed (datagram merge + 6 ms contact gap + no-storm guard + hold-trace + suppression-chain bound all green), ducking sovereignty logic is correct (Stopped-vs-Paused restart hazard is guarded in the backend), session recovery matches R.6 exactly, G6/G3/README claims stay honestly labeled unverified, and a base-vs-HEAD worktree diff proves the delta introduced no regressions in the legacy suites (it fixed one). Four findings: (1) MAJOR, introduced by the duck\_mode default flip — daemon-constructing tests fire real busctl --user calls against the live session, deterministically breaking later subprocess-recorder tests and able to pause the operator's playing media with no resume (R.7 violation); (2) MAJOR — the shipped bulk-text path fails its normative R.1 live-visibility requirement (both G5 routes: up to 57-word sustained backlog, sentence-end dumps, 12.6 s median speech→visible on pi-ghostty; only the laggy stabilized callback is wired despite R.8's mandate to compare callbacks) — honestly recorded in-repo and kept opt-in, but acceptance #13 is unmet; (3) MINOR — permanently red, unclassified VT-003 test vs the intentional panic bind; (4) MINOR — test\_daemon.py is wrongly classified as a CUDA hang vector, leaving its 20 legacy reds outside the G1 inventory. The 16 documented legacy lazy-separator reds (test\_streaming\_commit/core/freeze) and the real-model watch set (test\_streaming.py 3P/4F) reproduce exactly as baselined — pre-existing, classified, not re-filed. No daemon was foregrounded; the live systemd daemon was never armed by me; the base worktree and scratch files were removed.
heading:h2.2:
## Major Issues (Should Fix)

Issues that significantly impact user experience or functionality.

### Issue 1: Ducking default flip makes unit tests fire real busctl --user calls against the live desktop session (test pollution + operator media can be paused)

**Severity**: Major
**ID**: BUG-001
**Location**: voice\_typing/daemon.py:1022-1023 (real ducker built on default config) and voice\_typing/daemon.py:1804 (\_arm → \_duck\_engage); test sites tests/test\_key\_listener.py:459-477, 483

**Description**:
P1.M2.T4.S1 flipped the shipped default audio.duck\_mode from "off" to "mpris" (voice\_typing/config.py, config.toml:61), but the many tests that construct a default-config VoiceTypingDaemon and call \_arm() were not made hermetic. daemon.py:1022-1023 builds a REAL AsyncDucker(AudioDucker(MprisBusctlBackend)) whenever duck\_mode != "off", and \_arm() (daemon.py:1804) dispatches \_duck\_engage(), so every such test spawns a leaked 'vt-ducking' daemon worker that runs /usr/bin/busctl --user against the operator's LIVE session bus (/run/user/1000/bus). Two consequences: (1) CROSS-FILE TEST POLLUTION — the leaked worker's subprocess.run calls (kwargs {'timeout': 1.0, 'check': False, 'stdout': PIPE, 'stderr': DEVNULL} from ducking\_mpris.py:\_run) land inside later tests' monkeypatched subprocess.run recorders, producing order-dependent failures (tests/test\_typing\_backends.py::test\_wtype\_passes\_check\_true and test\_wtype\_invokes\_exact\_argv fail whenever an arming key\_listener test precedes them); (2) LIVE-SIDE EFFECT — the engage path enumerates MPRIS players and PAUSES every Playing+CanPause one (ducking\_mpris.py:\_engage\_mpris), with no resume because the test daemons never disarm; on a desktop with music/video playing, running the unit suite pauses the operator's media. This violates PRD §4.2sexies R.7's law that automation MUST NOT exercise the live desktop. Verified live in this session: constructing a default-config daemon and calling \_arm() produced real calls 'busctl --user call org.freedesktop.DBus ... ListNames' and 'busctl --user get-property org.mpris.MediaPlayer2.brave.instance479674 ... PlaybackStatus' (the operator's real Brave browser endpoint). Affected arming tests include tests/test\_key\_listener.py:459 (test\_zero\_keyboard\_warning\_fires\_once\_at\_first\_arm) and :477 (test\_no\_warning\_when\_keyboards\_watched), plus default-config arm sites in tests/test\_bulk\_dispatch.py, tests/test\_daemon.py, tests/test\_voicectl.py, tests/test\_session\_recovery.py, tests/test\_context\_prompt\_refresh.py, tests/test\_bulk\_context\_prompt.py, tests/test\_ime\_manager.py (none set duck\_mode or inject a ducker; only test\_no\_warning\_before\_listener\_started at tests/test\_key\_listener.py:492-509 explicitly sets duck\_mode="off", with a comment acknowledging the noise).

**Steps to Reproduce**:
Deterministic (3/3 runs): cd /home/dustin/projects/voice-typing && timeout 300 .venv/bin/pytest tests/test\_key\_listener.py::test\_zero\_keyboard\_warning\_fires\_once\_at\_first\_arm tests/test\_typing\_backends.py -q → 1 failed: tests/test\_typing\_backends.py::test\_wtype\_passes\_check\_true (recorder.calls\[0] kwargs are the leaked busctl call's {'timeout': 1.0, 'check': False, ...} instead of wtype's check=True). Same failure occurs with the full files tests/test\_key\_listener.py + tests/test\_typing\_backends.py (3/3), and intermittently (2/5) with the 8-file batch tests/{test\_control\_socket,test\_key\_listener,test\_typing\_backends,test\_textproc,test\_prompt\_engine,test\_context\_prompt\_refresh,test\_systemd\_unit,test\_ydotoold\_client}.py. Live-session proof: python snippet constructing VoiceTypingConfig() (default duck\_mode='mpris') + VoiceTypingDaemon(...).\_arm(), sleep 2.5s with a subprocess.run spy → 2 real /usr/bin/busctl --user calls observed targeting org.freedesktop.DBus and org.mpris.MediaPlayer2.brave.instance479674.

### Issue 2: bulk-text delivery fails its normative R.1 live-visibility requirement — words land at utterance granularity (up to 57-word backlog, sentence-end dumps) per the repo's own G5 gate

**Severity**: Major
**ID**: BUG-002
**Location**: voice\_typing/daemon.py:221 (\_PARTIAL\_CALLBACK\_ATTR = on\_realtime\_transcription\_stabilized) and voice\_typing/bulk\_controller.py (utterance-granularity delivery); evidence: tests/G5\_TIMING\_EVIDENCE.md

**Description**:
PRD §4.2sexies R.1 (normative, Rev 4): "Words MUST become visible in the focused editable field as recognition updates arrive — the operator reads the newest words at the insertion point while still speaking... never a sentence-end dump", and R.7 G5: "A sustained five-word backlog or a sentence-end dump fails regardless of medians." The shipped bulk-text path does not meet this: the repo's own timing gate (tests/G5\_TIMING\_EVIDENCE.md, 2026-11-23 @ c9a0a45) records BOTH routes as FAIL — im-gtk: one visible commit per replay (20 insertions / 0 corrections vs the ≥100/≥100 floors; 'the controller's per-utterance coalescing never let a partial op paint before its final superseded it'), sustained backlog max 57 words; pi-ghostty: speech→word-visible median 12,616 ms / p95 13,203 ms (bars: ≤500 ms / <1 s), sentence-end dump flagged, backlog max 57 words. A contributing cause is that only the laggy on\_realtime\_transcription\_stabilized callback is wired as the partial source (voice\_typing/daemon.py:221 \_PARTIAL\_CALLBACK\_ATTR, with the in-code comment acknowledging the on\_realtime\_transcription\_update fallback), while PRD R.8 explicitly prescribes comparing the earliest usable update callback against the stabilized one and choosing by VISIBLE word lag — that comparison was not performed. Net effect: with output.delivery="bulk-text", PRD acceptance #13's clause 'every recognition update is visible in the focused field' is not satisfied — dictation behaves like wait-for-silence delivery, exactly the experience the PRD's problem statement (§1) set out to eliminate. Mitigation context (why major, not critical): the mode is opt-in, G6 graduation honestly stayed opt-in (tests/G6\_GRADUATION.md), and the failures are recorded rather than hidden; but the feature delivered for §4.2sexies does not conform to its own normative spec.

**Steps to Reproduce**:
Read tests/G5\_TIMING\_EVIDENCE.md (verdict table: im-gtk fail 'backlog sustained; counts 20/0 < 100'; pi-ghostty fail 'speech→visible 12.6 s median; backlog sustained; sentence-end dump'; thresholds-vs-measured table shows both routes breach 'sustained ≥5-word backlog must-not' with max 57 words). Re-run per the file's own commands: timeout -k 2 1500 env G5\_TIMING\_LAB=1 .venv/bin/python tests/g5\_timing\_lab.py --route im-gtk (and --route pi-ghostty with PI\_BIN), each exits 1 with an honest-fail JSON verdict line. Static confirmation of the late partial source: voice\_typing/daemon.py:219-221 wires only on\_realtime\_transcription\_stabilized.
heading:h3.0:
### Issue 1: Ducking default flip makes unit tests fire real busctl --user calls against the live desktop session (test pollution + operator media can be paused)

**Severity**: Major
**ID**: BUG-001
**Location**: voice\_typing/daemon.py:1022-1023 (real ducker built on default config) and voice\_typing/daemon.py:1804 (\_arm → \_duck\_engage); test sites tests/test\_key\_listener.py:459-477, 483

**Description**:
P1.M2.T4.S1 flipped the shipped default audio.duck\_mode from "off" to "mpris" (voice\_typing/config.py, config.toml:61), but the many tests that construct a default-config VoiceTypingDaemon and call \_arm() were not made hermetic. daemon.py:1022-1023 builds a REAL AsyncDucker(AudioDucker(MprisBusctlBackend)) whenever duck\_mode != "off", and \_arm() (daemon.py:1804) dispatches \_duck\_engage(), so every such test spawns a leaked 'vt-ducking' daemon worker that runs /usr/bin/busctl --user against the operator's LIVE session bus (/run/user/1000/bus). Two consequences: (1) CROSS-FILE TEST POLLUTION — the leaked worker's subprocess.run calls (kwargs {'timeout': 1.0, 'check': False, 'stdout': PIPE, 'stderr': DEVNULL} from ducking\_mpris.py:\_run) land inside later tests' monkeypatched subprocess.run recorders, producing order-dependent failures (tests/test\_typing\_backends.py::test\_wtype\_passes\_check\_true and test\_wtype\_invokes\_exact\_argv fail whenever an arming key\_listener test precedes them); (2) LIVE-SIDE EFFECT — the engage path enumerates MPRIS players and PAUSES every Playing+CanPause one (ducking\_mpris.py:\_engage\_mpris), with no resume because the test daemons never disarm; on a desktop with music/video playing, running the unit suite pauses the operator's media. This violates PRD §4.2sexies R.7's law that automation MUST NOT exercise the live desktop. Verified live in this session: constructing a default-config daemon and calling \_arm() produced real calls 'busctl --user call org.freedesktop.DBus ... ListNames' and 'busctl --user get-property org.mpris.MediaPlayer2.brave.instance479674 ... PlaybackStatus' (the operator's real Brave browser endpoint). Affected arming tests include tests/test\_key\_listener.py:459 (test\_zero\_keyboard\_warning\_fires\_once\_at\_first\_arm) and :477 (test\_no\_warning\_when\_keyboards\_watched), plus default-config arm sites in tests/test\_bulk\_dispatch.py, tests/test\_daemon.py, tests/test\_voicectl.py, tests/test\_session\_recovery.py, tests/test\_context\_prompt\_refresh.py, tests/test\_bulk\_context\_prompt.py, tests/test\_ime\_manager.py (none set duck\_mode or inject a ducker; only test\_no\_warning\_before\_listener\_started at tests/test\_key\_listener.py:492-509 explicitly sets duck\_mode="off", with a comment acknowledging the noise).

**Steps to Reproduce**:
Deterministic (3/3 runs): cd /home/dustin/projects/voice-typing && timeout 300 .venv/bin/pytest tests/test\_key\_listener.py::test\_zero\_keyboard\_warning\_fires\_once\_at\_first\_arm tests/test\_typing\_backends.py -q → 1 failed: tests/test\_typing\_backends.py::test\_wtype\_passes\_check\_true (recorder.calls\[0] kwargs are the leaked busctl call's {'timeout': 1.0, 'check': False, ...} instead of wtype's check=True). Same failure occurs with the full files tests/test\_key\_listener.py + tests/test\_typing\_backends.py (3/3), and intermittently (2/5) with the 8-file batch tests/{test\_control\_socket,test\_key\_listener,test\_typing\_backends,test\_textproc,test\_prompt\_engine,test\_context\_prompt\_refresh,test\_systemd\_unit,test\_ydotoold\_client}.py. Live-session proof: python snippet constructing VoiceTypingConfig() (default duck\_mode='mpris') + VoiceTypingDaemon(...).\_arm(), sleep 2.5s with a subprocess.run spy → 2 real /usr/bin/busctl --user calls observed targeting org.freedesktop.DBus and org.mpris.MediaPlayer2.brave.instance479674.
heading:h2.5:
## Recommendations

* Make every daemon-constructing test hermetic: default cfg.audio.duck\_mode='off' in shared fixtures (or inject a fake through the existing ducker= seam) and keep exactly one dedicated ducking-wiring test with a \_FakeDucker — this removes both the order-dependent test pollution and the live-desktop side effect.
* Pursue R.1/R.8 for bulk-text: wire the plain on\_realtime\_transcription\_update callback (daemon.py:219 already documents the switch), re-run the G5 harness word-aligned, and re-evaluate whether partial ops can dispatch at update granularity ahead of their final.
* Exempt the documented SUPER+ALT+Escape panic bind in test\_hypr\_binds\_use\_portable\_home\_launcher (or mark the line) so the suite carries no unexplained red.
* Reclassify tests/test\_daemon.py as a pure CPU suite in AGENTS.md and the G1 baseline, and fold its 20 legacy lazy-separator reds into the documented classification so future sweeps can diff against a complete inventory.
</selected_prd_content>
<prd_index>
h1.0 Bug Fix Requirements
 h2.0 Overview
 h2.1 Critical Issues (Must Fix)
 h2.2 Major Issues (Should Fix)
  h3.0 Issue 1: Ducking default flip makes unit tests fire real busctl --user calls against the live desktop session (test pollution + operator media can be paused)
  h3.1 Issue 2: bulk-text delivery fails its normative R.1 live-visibility requirement — words land at utterance granularity (up to 57-word backlog, sentence-end dumps) per the repo's own G5 gate
 h2.3 Minor Issues (Nice to Fix)
  h3.2 Issue 1: Permanently failing test: test_hypr_binds_use_portable_home_launcher rejects the documented SUPER+ALT+Escape panic bind
  h3.3 Issue 2: test_daemon.py misclassified as a CUDA hang vector and excluded from the G1 baseline — its 20 legacy-red tests were never classified
 h2.4 Testing Summary
 h2.5 Recommendations
---
para:17 list:2
</prd_index>
<issue_feedback>

</issue_feedback>
<plan_status>Task Status Summary
==================================================

P1: Rev-4 bug fixes and isolated acceptance - Planned
  P1.M1: Hermetic tests and complete baseline classification - Planned
    P1.M1.T1: Keep daemon tests off the desktop media bus - Planned
      P1.M1.T1.S1: Establish a hermetic media fixture at the first-arm seam - Researching (2 points)
      P1.M1.T1.S2: Migrate ordinary daemon constructors and test consumers - Planned (2 points)
      P1.M1.T1.S3: Pin default-to-fake duck wiring and ordered subprocess isolation - Planned (1 points)
    P1.M1.T2: Reconcile VT-003 with the shipped panic bind - Planned
      P1.M1.T2.S1: Pin the exact panic exception in the portability check - Planned (1 points)
    P1.M1.T3: Classify the daemon CPU suite in G1 - Planned
      P1.M1.T3.S1: Record the named 20-case daemon baseline and correct test guidance - Planned (1 points)
  P1.M2: Deliver words during speech and qualify both bulk routes - Planned
    P1.M2.T1: Establish a comparable, representative G5 experiment - Planned
      P1.M2.T1.S1: Select exactly one callback across the recorder spawn boundary - Planned (2 points)
      P1.M2.T1.S2: Start the production IM route on the bulk arm worker - Planned (2 points)
      P1.M2.T1.S3: Align changed-span field observations and expose attribution gaps - Planned (2 points)
      P1.M2.T1.S4: Wire the isolated route runner to compare real recorder builds - Planned (2 points)
      P1.M2.T1.S5: Qualify a private Pi prompt frame observation - Planned (2 points)
      P1.M2.T1.S6: Run the paired callback comparison and localize visible lag - Planned (2 points)
    P1.M2.T2: Ship and verify update-granular bulk delivery - Planned
      P1.M2.T2.S1: Keep partial dispatch prompt and fail closed under bursts - Planned (2 points)
      P1.M2.T2.S2: Remediate the measured source-to-field bottleneck - Planned (2 points)
      P1.M2.T2.S3: Qualify the selected production source on both routes - Planned (2 points)
    P1.M2.T3: Sync changeset-level documentation - Planned
      P1.M2.T3.S1: Refresh tests/G6_GRADUATION.md from current evidence - Planned (0.5 points)
      P1.M2.T3.S2: Sync README.md overview to the landed fixes and limits - Planned (0.5 points)</plan_status>

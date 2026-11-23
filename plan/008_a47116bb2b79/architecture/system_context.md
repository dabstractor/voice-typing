# plan/008 architecture index — voice-typing delta (D1 ducking, D2 bulk delivery, D3 defects)

Repo HEAD at research time: `2335a9e` (main). All findings cite file:line AT THAT HEAD; re-locate
symbols before editing. Tasks: `../tasks.json` (P1, 7 milestones, 25 tasks, 47 subtasks).

## Findings files

| File | Grounds | Used by |
|---|---|---|
| `d1_ducking_seams.md` | Arm/disarm choke points (`_arm` toast daemon.py:1415; `_disarm` :1454; `request_shutdown` :2177; `_handle_dead_host` edge), feedback `ducked` recipe, `[audio]` config lockstep (key-set pin `tests/test_config_repo_default.py:37-63`, 24→26), systemd ExecStopPost, test seams (`_make_daemon` tests/test_daemon.py:682-700), env: NO D-Bus libs in venv → subprocess busctl/wpctl | P1.M2 |
| `d2_bulk_delivery_map.md` | recorder_host event payloads (5 `final` puts :644/:742/:745/:1052/:1054; `_dispatch` :426-479), bulk-cancel intercept (`daemon.cancel` :1754, compensation :1781), StreamingOutput do-not-touch surface, ctl/feedback additive-key recipes, im-lab/paste-lab/asr-lab reuse table, **version drift: installed hyprland 0.57.2 / kitty 0.51 / ghostty 1.4.0 vs measured matrix**, pi extension seam (`setEditorComponent` CustomEditor contract; fork is NOT text injection), 9 open risks | P1.M3–M6 |
| `d3_defects_g1_baseline.md` | **G1 baseline: 379 passed / 20 failed across 15 pure suites** (commit 10F/22P = handoff; core 2F; freeze 4F; streaming.py 3P/4F — a/b NOT separator-shaped; zero_diff 3/3; ACCEPTANCE row 11 stale). D3.1: clean merge (33321c6, zero overlap; 6 ms gap in NEITHER socket path). D3.2: hold-trace audit (autorepeat filtered at key_listener.py:81; uncompensated OS deletions during paced burst; no test simulates). D3.3: NOT closed — stamp-refresh-per-press chains the suppression window (daemon.py:1788-1792); 7-step replay scenario written out | P1.M1, P1.M7.T2 |
| `external_tech_notes.md` | IM-v2 semantics (confidence-labeled, no web this run — machine evidence in im-lab is stronger), pywayland recommendation (subprocess isolation) BUT pywayland not in venv → wlwire lineage stands, MPRIS busctl argv forms + tracked-pause-set design, wpctl grammar/absolute-%/node-id-snapshot, wl-clipboard (PRIMARY untouched; `-t text/plain`; multi-format restore impossible), no gtk4-demo — hand-written GTK field apps | P1.M2, P1.M4, P1.M5 |

## Load-bearing decisions baked into tasks.json

1. D1 backends are subprocess-only (no new Python deps); MPRIS = tracked pause set via busctl,
   volume = concrete-node-id snapshot + conditional restore. Engage/release spawn threads — never
   under `self._lock`.
2. D2 route is DECIDED (im-lab spike): IM-v2 primary via a wlwire-lineage daemon-owned subprocess;
   no route discovery work; ghostty 1.4.0 forces a matrix re-run before the clipboard fallback is
   built (it is conditional).
3. G1 baseline numbers are pre-recorded; implementers re-verify then classify, never skip.
4. Legacy `stream-edit` behavior must stay byte-identical; bulk code never touches
   `StreamingOutput`/`typing_backends` and exposes no typing surface.

Prior-session grounding (Rev-2 era, trust structure not line numbers):
`plan/007_cfc245548aec/architecture/{daemon_control_map,realtimestt_internals,substrate_map}.md`.

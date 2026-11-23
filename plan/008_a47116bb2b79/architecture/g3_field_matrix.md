# G3 field-class matrix — re-run at installed versions (P1.M4.T5.S2)

- Date: 2026-11-23  |  HEAD: 148aeda
- Command: `timeout 420 env IME_G3_MATRIX_LAB=1 .venv/bin/python tests/ime_g3_matrix_lab.py`
- kernel: 7.2.7-arch1-1
- sway: sway version 1.12
- foot: foot version: 1.28.0 (Sep 08 2026, branch 'makepkg') +pgo +ime +graphemes +toplevel-tag +blur -assertions
- kitty: kitty 0.51.0 created by Kovid Goyal
- ghostty: Ghostty 1.4.0-arch2
- hyprland: Hyprland 0.57.2 built from branch v0.57.2 at commit 11cbc6c577b84ffb1edf4df3fc5b6128c3ae6947 clean (VERSION: bump to 0.57.2).
- pacman -Q (verbatim): foot 1.28.0-2 | kitty 0.51.0-1 | ghostty 1.4.0-2 | hyprland 0.57.2-1 | sway 1:1.12-4 | gtk4 1:4.24.1-1

> **A G2/lab pass never marks a row verified.** Only this harness's
> app-side witnesses (term.json / field dump + host reason strings)
> record a row, and only with live versions attached. t_ms values
> are mechanism-level info, NEVER G5 timing (no speech in this run).

| field class | measured version | status |
|---|---|---|
| gtk (S1) | (S1's run, see plan/008_a47116bb2b79/architecture/g3_gtk_rows.md) | im-v2 full — cited, NOT re-run |
| foot | 1.28.0-2 | insert-only (1.28.0-2 + evidence: foot row, verdicts.jsonl) |
| kitty | 0.51.0-1 | insert-only (0.51.0-1 + evidence: kitty row, verdicts.jsonl) |
| ghostty | 1.4.0-2 | blocked (activate not_activated at 1.4.0-2 — IM route unavailable for this class; evidence: ghostty row, verdicts.jsonl) |
| Hyprland relay | 0.57.2 (11cbc6c5) | blocked (nested Hyprland: aquamarine CBackend::create() abort on every variant — full diagnosis in open items) |

## Hyprland isolated-boot ladder (≤3 attempts, fresh env per variant)
- nested-wayland: failed; delta: UNSET WLR_BACKENDS, WLR_LIBINPUT_NO_DEVICES, DISPLAY,
  WLR_RENDERER; SET WAYLAND_DISPLAY=<private sway>, XDG_CURRENT_DESKTOP=Hyprland,
  WLR_RENDERER=pixman, LIBGL_ALWAYS_SOFTWARE=1, MESA_SHADER_CACHE_DISABLE=true; err head:
  aquamarine CBackend::create() abort — "Wayland backend cannot start: Missing protocols"
  (root cause: open item 2)
- aq-headless: failed; delta: UNSET the same + WAYLAND_DISPLAY; SET AQ_NO_KMS_REQUIREMENT=1,
  AQ_DRM_DEVICES="" (pinned empty per the upstream virtual-gpu recipe); err head: aquamarine
  CBackend::create() abort — "Cannot open backend: no allocator available" (root cause:
  open item 3)
- legacy-x11: failed; delta: the full disposable-desktop env VERBATIM incl.
  WLR_BACKENDS=x11 + nested WAYLAND_DISPLAY (the 2026-11-22 hypr_nest.py posture, re-run
  for provenance); err head: aquamarine CBackend::create() abort — same shape as recorded

## Route table (derives the P1.M5.T3 decision — unit-tested)
clipboard_fallback_m5t3: needed (ghostty-class insert blocked at 1.4.0-2)
```json
{
 "clipboard_fallback_m5t3": "needed (ghostty-class insert blocked at 1.4.0-2)",
 "field_classes": {
  "foot": {
   "corrections": "cooperating-editor seam (M5.T1)",
   "evidence": "foot row at 1.28.0-2",
   "route": "im-v2 insert-only"
  },
  "ghostty": {
   "evidence": "ghostty row at 1.4.0-2",
   "route": "clipboard insert-fallback (R.6)"
  },
  "gtk": {
   "evidence": "plan/008_a47116bb2b79/architecture/g3_gtk_rows.md",
   "route": "im-v2 full"
  },
  "kitty": {
   "corrections": "cooperating-editor seam (M5.T1)",
   "evidence": "kitty row at 0.51.0-1",
   "route": "im-v2 insert-only"
  }
 },
 "hyprland_relay": "blocked (nested Hyprland: terminate called after throwing an instance of 'std::runtime_error' what(): CBackend::create() failed! Hyprland has crashed :( Consult the crash report at /tmp/ @ nested-wayland,aq-headless,legacy-x11)"
}
```

## Evidence excerpts (capped)
### foot
  t_ms (mechanism): {"correct": 10.593, "insert": 10.772, "insert_unicode": 10.597}
  host reasons: {"acquire": "no surrounding text", "show_correct": "applied"}
  line after probes: 'hello from imv2Zoë — naïve 日本語 🫡'
  preedit: not exercised — the product host transport serves acquire/show/cancel/grab/verify/leave/ping only; it has no preedit command (the im-lab im_probe ctl preedit/endpreedit diagnostic has no IM-v2 host equivalent)
  screenshot sha256[:16]: 96b8f32af580dd04
### kitty
  t_ms (mechanism): {"correct": 222.474, "insert": 222.008, "insert_unicode": 222.904}
  host reasons: {"acquire": "no surrounding text", "show_correct": "unknown"}
  line after probes: 'hello from imv2Zoë — naïve 日本語 🫡'
  preedit: not exercised — the product host transport serves acquire/show/cancel/grab/verify/leave/ping only; it has no preedit command (the im-lab im_probe ctl preedit/endpreedit diagnostic has no IM-v2 host equivalent)
  screenshot sha256[:16]: 1cb846a607549874
### ghostty
  t_ms (mechanism): {"insert": 0.0}
  host reasons: {"acquire": "not activated"}
  line after probes: ''
  preedit: not exercised — the product host transport serves acquire/show/cancel/grab/verify/leave/ping only; it has no preedit command (the im-lab im_probe ctl preedit/endpreedit diagnostic has no IM-v2 host equivalent)
  screenshot sha256[:16]: a91d8131218d6a52

Summary: 4 of 5 rows measured at the installed set (gate exit 0, every branch legal): foot/kitty = insert-only (delete_surrounding_text ignored, surrounding_text never sent), ghostty 1.4.0 = blocked (text-input not activated), Hyprland relay = blocked with per-variant root causes. ghostty-class insert is blocked => the P1.M5.T3 clipboard insert-fallback is NEEDED.

## Open items
- ghostty 1.5.0 watch — PR #15246 'gtk: preserve IME commits triggered by key release' is milestone 1.5.0, after the 1.4.0 cut (upstream-changelog-drift.md); retest this row at 1.5.0. Drift note: 1.4.0 measured WORSE than the 1.3.1 baseline (text-input not activated at all under the product host, vs 'activated but commits lost').
- Hyprland nested-wayland root cause (corrects the 2026-11-22 hypothesis): aquamarine 0.16 binds xdg_wm_base v6 and zwp_linux_dmabuf_v1 (Wayland.cpp:125/133/147); the private sway 1.12 parent advertises xdg_wm_base v5 (wlroots ceiling) and NO linux-dmabuf global under pixman software rendering -> 'Missing protocols'. The inherited WLR_BACKENDS=x11 is EXONERATED: aquamarine reads no WLR_* variables at all.
- Hyprland headless root cause: the GBM allocator needs a DRM fd from a session-backed DRM implementation; libseat cannot open a seat under the disposable Xvfb seat (no seatd socket; logind session busy) -> 'no allocator available' (Backend.cpp:164-177; CHeadlessBackend::drmFD() == -1). A booted isolated Hyprland needs a real seat — out of reach for the disposable-desktop recipe (R.7 isolation); re-attempt only from a TTY-backed seat, same ladder.
- kitty 0.51: ~224 ms per insert mechanism-level vs foot ~10 ms — information only, NEVER G5 timing (no speech in this run); kitty host show reply was 'unknown' while the app-side witness proved delivery — IM-side reply taxonomy is never a terminal text channel (R.7).


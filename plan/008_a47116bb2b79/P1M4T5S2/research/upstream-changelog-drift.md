# Upstream changelog drift — Wayland IME capability matrix re-run

Researched 2026-11-23 from primary sources (GitHub APIs, raw source at release tags,
sw.kovidgocal.net changelog, ghostty.org website repo, hyprland-wiki, Codeberg API).
Verdicts are per matrix question. "Fixed in X" = change is in released version X.

## Ghostty 1.4.0 (baseline 1.3.1) — released 2026-10-27

**Q: Did the gtk-IME "IME commit lost" fix land — do text-input-v3 commit_string bytes
reach the pty? — verdict: NOT-FIXED in 1.4.0 (merged for 1.5.0).**

- The commit-loss fix is PR ghostty-org/ghostty#15246 "gtk: preserve IME commits
  triggered by key release", merged 2026-11-17, milestone **1.5.0** — i.e. AFTER the
  1.4.0 release (2026-10-27; mdx header "released on October 27, 2026"). Latest tag is
  v1.4.0; no 1.4.1 patch exists (GitHub tags list, checked 2026-11-23).
  https://github.com/ghostty-org/ghostty/pull/15246
- PR #15246 body matches the tracked symptom exactly: with client preedit disabled in
  Fcitx5, a commit emitted synchronously during `filterKeypress` is buffered as
  ordinary key text, and "when the triggering event is a key release, legacy key
  encoding discards that text" — commit bytes never reach the pty. Reproduced on
  1.3.1 under Fcitx5/WowType (GTK 4.14.5, libadwaita 1.5.0, isolated Xvfb session).
- 1.4.0 notes contain NO gtk commit-delivery fix; grep of 1-4-0.mdx for commit/IME
  shows the "composed is now committed instead of lost" line is macOS-only.
  https://github.com/ghostty-org/website/blob/main/docs/install/release-notes/1-4-0.mdx
- What 1.4.0 DID land for GTK IME (lesser items): GH-14729 "gtk: keep IME cursor
  location updated during preedit on Wayland" (candidate window follows cursor while
  composing) and GH-12479 (OOB fix: IME preedit wide chars composed between existing
  wide chars, Korean). Both in 1-4-0.mdx.
- No open gtk-IME PR remains; open IME PRs are #12244 (draw IME cursor) and #15137
  (macOS Korean) — GitHub issue search `is:pr ime in:title`, 2026-11-23.

## Kitty 0.50 / 0.51 (baseline 0.49.1)

Versions: 0.49.2 [2026-10-01], 0.50.0 [2026-11-03], 0.51.0 [2026-11-18],
0.51.1 [2026-11-23]. https://sw.kovidgoyal.net/kitty/changelog/

**Q: delete_surrounding_text support? — verdict: NOT-FIXED (still silently ignored).**
- glfw/wl_text_input.c at tag v0.51.1 is byte-identical to master (diff verified
  2026-11-23). Handler `text_input_delete_surrounding_text` (L98-100) only emits a
  debug log; it performs no deletion. Registered in the listener table at L147.
  https://github.com/kovidgoyal/kitty/blob/v0.51.1/glfw/wl_text_input.c
- Changelog 0.50.0/0.51.x IME entries are preedit/candidate-window positioning only:
  0.50.0 "IME: Keep the candidate window anchored at the start of the pre-edit text
  and at the cursor" (+ macOS commit-on-switch), 0.50.0 "IME: Show the cursor at the
  position reported by the input method inside the pre-edit text", 0.51.0 "IME: Move
  cursor position within pre-edit text (#10807)". Nothing about delete_surrounding.

**Q: Does kitty ever SEND surrounding_text (zwp_text_input_v3 .surrounding_text)?**
- **No.** wl_text_input.c (v0.51.1) never calls `zwp_text_input_v3_set_surrounding_text`;
  the only requests issued are enable/disable/commit/set_content_type/set_cursor_rectangle
  (grep of full file, 2026-11-23). (For contrast, macOS-only "input methods can read the
  text around the cursor" landed in 0.49.0, #10492 — NSTextView, not Wayland.)
- No kitty issue/PR mentions delete_surrounding_text (GitHub search total_count=0).

## Hyprland 0.57.x (baseline 0.56.2)

Versions: 0.57.0 [2026-10-28], 0.57.1 [2026-11-03], 0.57.2 [2026-11-09];
0.56.2 [2026-08-05]. https://github.com/hyprwm/Hyprland/releases

**Q: zwp_input_method_v2 / zwp_text_input_v3 relay changes? — verdict: NOT-FIXED /
no behavior change.**
- Only IME-adjacent entries in 0.57.0 release body: "input-method: avoid dirtying
  popup state for rectangle notifications" (commit b3fd5b498 — popup redraw bookkeeping,
  not relay semantics) and "desktop: render IME above all desktop components (#15646)"
  — the latter is ALSO listed in the v0.56.2 release body, so not net-new vs baseline.
  0.57.1 / 0.57.2 bodies: no IME/text-input items.
- File-level diff v0.56.2 → v0.57.2 (raw fetch at tags, 2026-11-23) of
  src/managers/input/InputMethodRelay.{cpp,hpp}, src/managers/input/TextInput.{cpp,hpp},
  src/protocols/TextInputV3.{cpp,hpp}, src/protocols/InputMethodV2.cpp:
  every changed hunk is the `LOGM(...)`→`LOG(...)` logging-macro refactor. Zero
  changes to commit/preedit/surrounding/keyboard-grab relay logic.

**Q: nested Hyprland under software rendering (x11/llvmpipe) — what makes an isolated
session boot headless? — verdict: UNKNOWN-in-part / documented workaround exists.**
- Root cause of `CBackend::create() failed` under X11: aquamarine has NO X11 backend —
  eBackendType is DRM | HEADLESS | WAYLAND only (src/backend/Backend.cpp
  `backendTypeToName`). Hyprland's own failure message: "Make sure you're running
  either on a tty or on a Wayland session, NOT an X11 one." (src/Compositor.cpp,
  identical v0.56.2 and v0.57.2). Nested-under-X11 is unsupported, full stop;
  llvmpipe is not the deciding factor.
- `WLR_RENDERER` / `WLR_BACKENDS` are dead: zero references in the whole aquamarine
  tree (full clone grep of src+include, 2026-11-23) — they are wlroots variables.
  Aquamarine env vars (docs/env.md + code): AQ_DRM_DEVICES, AQ_NO_ATOMIC,
  AQ_MGPU_NO_EXPLICIT, AQ_NO_MODIFIERS, AQ_LIBINPUT_NO_PLUGINS, AQ_TRACE, plus
  AQ_NO_KMS_REQUIREMENT (src/backend/Session.cpp:289, undocumented in env.md).
- Backend request order is identical in v0.56.2 and v0.57.2 (src/Compositor.cpp
  ~L311-325): HEADLESS=MANDATORY, DRM=IF_AVAILABLE, WAYLAND=FALLBACK — so a Wayland
  parent session or a bare TTY both work; an X11 parent leaves only DRM+headless.
- Documented headless recipe (wiki, checked 2026-11-23):
  https://github.com/hyprwm/hyprland-wiki/blob/main/content/configuring/extra/virtual-gpu.md
  - On a render-only / no-output GPU: `AQ_NO_KMS_REQUIREMENT=1`; Hyprland then
    auto-creates output `HEADLESS-0` at 1920x1080@60 (configurable).
  - Pin devices with `AQ_DRM_DEVICES=/dev/dri/cardX:...` when several nodes exist.
  - Reach it via wayvnc / Sunshine / Apollo (screencopy-based), started under the
    Hyprland process so they inherit its env.
  - Manual output: `hyprctl output create headless <name>` — still present in v0.57.2
    (src/ipc/s1/Commands.cpp:1854 routes to the aquamarine headless backend).
- Software GL: aquamarine itself reads no Mesa envs; the standard Mesa levers
  (`GALLIUM_DRIVER=llvmpipe`, `LIBGL_ALWAYS_SOFTWARE=1`) govern its EGL/GL stack.
  This Mesa part is inference from standard Mesa behavior, not a Hyprland doc claim.
- UNVERIFIED: boot with literally zero /dev/dri nodes. The headless backend builds
  swapchains on the primary GBM allocator (src/backend/Headless.cpp createOutput), so
  a GPU-less/vkms-less boot is unproven; the wiki only covers render-node scenarios.

## foot 1.28 (one paragraph)

foot 1.28.0 (released 2026-09-02, https://codeberg.org/dnkl/foot/releases) contains no
input-method changes in its release notes, and there has been no delete_surrounding_text
work: Codeberg issue searches for "surrounding"/"delete_surrounding" return nothing
IME-related. Source at tag 1.28.0 (ime.c) is explicit: commit_string bytes are written
to the pty via `term_to_slave()` (~L203), while delete_surrounding_text is received,
logged, and its before/after lengths stored — but never applied; the code comments say
"We don't support deleting surrounding text. But, we also never call
set_surrounding_text() so hopefully we should never receive any requests to delete
surrounding text" (L188-192) and "Calculate surrounding text to send - not supported"
(L211). https://codeberg.org/dnkl/foot/src/tag/1.28.0/ime.c — so foot, like kitty,
never sends surrounding_text and ignores delete_surrounding_text. Post-1.28 master
merged two small IME PRs — #2480 "ime: reset view and cancel selection on input"
(2026-10-25) and #2491 "ime: reset view & cancel selection on text commit"
(2026-11-12) — view/selection resets, not surrounding-text work.

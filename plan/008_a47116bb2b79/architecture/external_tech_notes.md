# Research: external-technology brief for plan/008 — Wayland IM-v2, pywayland, MPRIS/wpctl ducking, wl-clipboard, GTK field apps

## Summary
An input-method-v2 client on Hyprland reaches GTK4 fields via the compositor's text-input-v3 ↔ input-method-v2 relay using only three tiny protocol surfaces; pywayland in a subprocess is the right client library; ducking/restoring needs tracked-player MPRIS pause sets plus wpctl float+mute snapshots; wl-copy (clipboard selection only) with an explicit `-t text/plain` is the safe `--copy` route. Version-specific externals below are confidence-labeled: see Method.

## Method & limitations (read first)
- **No `web_search`/`source_check` tool was registered in this subagent run, and no shell/exec tool exists here.** Every external claim is from canonical sources as known to the researcher, cited by URL and confidence-labeled; nothing below was fetched or validated online this run. Local probes were read-only file reads (existence/content) via the file tool — weaker than executing the brief's exact commands, which was impossible here.
- Local probes actually performed: `.venv/lib/python3.12/site-packages/{dbus_next,pydbus,jeepney,pywayland,evdev}/__init__.py`; `/usr/share/gir-1.0/Gtk-{3,4}.0.gir`; `/usr/share/licenses/{cliphist,wl-clip-persist,clippie}/LICENSE`; `/usr/share/wayland-protocols/*` (absent); `/usr/share/wayland/wayland.xml` (present); `/etc/os-release`; `.venv/pyvenv.cfg`; `pyproject.toml`.
- Not run (no shell): `command -v cliphist …`, `systemctl --user list-units`, `/usr/bin/python3 -c 'import gi'`, `wpctl --help`. Approximated by file probes where possible; flagged below.
- Machine facts taken as given by the brief (not re-derived): Arch; Hyprland 0.56.2; PipeWire 1.6.x + pipewire-pulse; playerctl/wpctl/pactl/wl-copy/wl-paste installed; GTK4 fields lab-verified on the IM-v2 route; foot & kitty insert-only; ghostty 1.3.1 IM-dead.

## Findings

### 1. Wayland input-method-v2 family
Sources: [input-method-unstable-v2.xml](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/unstable/input-method/unstable/v2/input-method-unstable-v2.xml), [text-input-unstable-v3.xml](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/unstable/text-input/unstable/v3/text-input-unstable-v3.xml). **Caveat: the `wayland-protocols` package is not installed on this box (all `/usr/share/wayland-protocols` probes ENOENT), so the XML text could not be re-read locally this run; the following is from knowledge of the canonical XML — confidence medium-high, re-verify wording when web access returns.**

1.1 **Manager & seat exclusivity.** `zwp_input_method_manager_v2.create_input_method(seat)` returns a `zwp_input_method_v2`. At most one input method holds a seat's IM slot; a client that arrives while another IM owns the seat receives the `unavailable` event and should destroy its object. **Support:** interpretation of canonical XML. **Confidence:** medium-high. Sources: XML (above); wlroots implementation [wlr_input_method_v2.c](https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/master/types/input_method_v2/wlr_input_method_v2.c).

1.2 **activate/deactivate.** `activate(context)` fires per focus-gain and mints a **new** `zwp_input_method_context_v2` each time; `deactivate(context)` tells the IM to finish and destroy that context. State is per-context and discarded on deactivate. **Support:** interpretation. **Confidence:** medium-high.

1.3 **Context requests.** `commit_string(serial, text)`, `preedit_string(serial, text, commit)`, `delete_surrounding_text(before_length, after_length)` (byte counts around cursor), `commit(serial)` (atomically apply the double-buffered batch), `grab_keyboard` → new `wl_keyboard`. The context also carries forwarding requests (`grab_key`, `keysym`, `modifiers`) and events (`surrounding_text(text,cursor,anchor)`, `reset`, `content_type`, `preferred_language`, `text_input_rectangle`). The forwarding-request details are the shakiest memory in this inventory — verify against the XML. **Support:** interpretation. **Confidence:** medium (inventory), high (commit_string/preedit/delete_surrounding/commit/grab_keyboard/surrounding_text).

1.4 **Evaluation order within one `commit(serial)`.** The brief's order — preedit-replace → delete-surrounding → insert-commit — is consistent with the protocol's double-buffered semantics and with how wlroots' input-method relay and fcitx5 apply a commit batch. The XML documents each request but (to my knowledge) does not spell a numbered order; the order is normative-by-implementation. **Support:** interpretation. **Confidence:** medium. **Flag:** confirm from XML text.

1.5 **4000-byte commit_string limit.** The input-method-v2 (and text-input-v3) XML defines **no** size limit — this is not a protocol constraint. The cap is implementation-side; I could **not** pin its origin this run (no web). It must be verified against Hyprland/wlroots/toolkit sources before being attributed anywhere. **Support:** researcher inference from protocol knowledge + missing evidence. **Confidence:** medium (that the protocol sets no limit), unresolved (origin). **Design note regardless of origin: chunk commits to ≤4000 bytes.**

1.6 **grab_keyboard mechanics.** `grab_keyboard(new_id wl_keyboard)` returns a `wl_keyboard` whose `key`/`modifiers` events are delivered **to the IM on that object** while the grab holds; grabbing diverts keys from the app. Release happens on deactivate/destroy. **Support:** interpretation. **Confidence:** medium-high.

1.7 **text-input-v3 client side.** `zwp_text_input_v3`: `enable`/`disable`, `set_surrounding_text`, `set_content_type`, `commit_state(serial)`; the compositor replies `commit(serial)`. GTK4 text widgets bind it automatically via the Wayland IM backend (no `GTK_IM_MODULE` needed); GTK3 needs its "wayland" IM module (set `GTK_IM_MODULE=wayland` if the environment overrides it). Qt uses QtWayland's input context when `QT_IM_MODULE` is unset. **Support:** interpretation + toolkit docs. **Confidence:** medium-high. Sources: [GTK4 docs](https://docs.gtk.org/gtk4/), [text-input-v3 XML](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/unstable/text-input/unstable/v3/text-input-unstable-v3.xml).

1.8 **Why GTK fields work: the relay.** Compositors implement **both** interfaces and bridge them: wlroots' input-method relay (used by sway; Hyprland implements the same pair), Mutter's MetaInputMethodV2, KWin. A v3 `commit_state` from a GTK field becomes a v2 context commit to the IM; IM `commit_string` is inserted into the field. This is the whole reason an IM-v2 IME needs no app cooperation. **Support:** interpretation (well-established architecture). **Confidence:** high. Sources: [wlroots](https://gitlab.freedesktop.org/wlroots/wlroots), [Hyprland](https://github.com/hyprwm/Hyprland).

1.9 **Hyprland 2025–2026 IM-v2 issues (fcitx5 coexistence, surrounding_text relay).** NOT verifiable this run (no web). From knowledge only, recurring themes: second-IM seat takeover (`unavailable`), preedit visibility in some clients, and compositors not relaying `surrounding_text`. Specific issue numbers/fix versions: **missing evidence** — do not cite any until verified. Sources to mine: [Hyprland issues](https://github.com/hyprwm/Hyprland/issues).

**Design implication for voice-typing:** build the IM-v2 client as a seat-exclusive singleton that ignores surrounding/preedit (insert-only like foot/kitty), commits text in ≤4000-byte chunks, and treats `unavailable` as "another IM owns the seat — fail loudly, don't retry."

### 2. pywayland vs C/Rust helper
Sources: [pywayland GitHub](https://github.com/flacjacket/pywayland), [docs](https://pywayland.readthedocs.io/en/latest/), [PyPI](https://pypi.org/project/pywayland/).

2.1 pywayland is a thin ctypes binding over libwayland plus a scanner; current release line is 0.4.x (latest I can attest is ~0.4.18, 2024/2025 — **low confidence on exact current version; verify on PyPI**). **Local: NOT installed in `.venv`** (probe ENOENT; `evdev` present validates the probe). It is not currently a dependency (per `pyproject.toml`).

2.2 Scanner pattern (docs-based, **medium confidence** — verify flag spelling with `python -m pywayland.scanner --help`):
- CLI: `python -m pywayland.scanner -i input-method-unstable-v2.xml -o gen/` (regenerate from the canonical XML).
- Programmatic:
```python
from pywayland.scanner import Protocol
proto = Protocol.parse_file("input-method-unstable-v2.xml")
proto.output("gen")   # emits gen/ modules exposing ZwpInputMethodManagerV2 etc.
```

2.3 Threading/event model: `WlDisplay.connect()`, blocking `display.dispatch()` on a dedicated thread, `display.get_fd()`/`fileno()` for selector-driven loops, per-thread event queues possible but must not be mixed. Long-lived client pattern: dispatch thread reads events, control thread issues requests and `flush()`es before blocking reads. **Support:** interpretation of docs. **Confidence:** medium.

2.4 Python IME precedent: I know of **no widely-used IM-v2 input method built on pywayland** (fcitx5 = C++, ibus = C). **Missing evidence** — cannot cite one; this raises integration risk slightly but the protocol surface here is tiny.

2.5 **RECOMMENDATION (one): pywayland, in a dedicated subprocess owned by the daemon.** Justification: (a) the used surface is ~5 requests/events — binding maturity barely matters; (b) subprocess isolation keeps pywayland's C-extension/ABI risk out of the CUDA-heavy daemon, and a crash costs only dictation, not the model; (c) regeneration from the canonical XML is mechanical maintenance; (d) Python matches repo tooling and tests; (e) the subprocess IPC (e.g., JSONL on stdin) keeps the door open to swap in a ~300-LOC C helper (`wayland-scanner` + libwayland-client) if pywayland's dispatch loop or the keyboard-grab paths prove brittle — without touching daemon code. **Support:** researcher inference over 2.1–2.4. **Confidence:** medium-high.

**Design implication for voice-typing:** a `voice-typing-ime` subprocess (pywayland, pyproject dep) speaking JSONL to the daemon; activation/deactivation and commit text cross that boundary; nothing Wayland-linked runs inside the daemon.

### 3. MPRIS ducking
Sources: [MPRIS spec — Player](https://specifications.freedesktop.org/mpris-spec/latest/Player_Interface.html), [D-Bus spec](https://dbus.freedesktop.org/doc/dbus-specification.html), [playerctl](https://github.com/altdesktop/playerctl).

3.1 Semantics: `PlaybackStatus` ∈ {"Playing","Paused","Stopped"}; `Pause()`/`Play()` methods; `CanPause`/`CanPlay`/`CanControl` gates. Check `CanControl`/`CanPause` before pausing; `Play()` on a stopped player restarts — resume with `Play()` only what you paused. **Support:** direct spec knowledge. **Confidence:** high.

3.2 Discovery: `org.freedesktop.DBus.ListNames()` → well-known names under `org.mpris.MediaPlayer2.*`; `NameOwnerChanged(name, old, new)` gives identity stability by mapping well-known → unique (`:1.N`) owners. **Support:** D-Bus spec. **Confidence:** high.

3.3 **Local: `dbus_next` and `pydbus` (and `jeepney`) are ABSENT from `.venv`** (file probes; layout validated by evdev hit). Not importable without new deps → per the brief, drive MPRIS via subprocess argv:
- List: `busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ListNames`
- Status: `busctl --user get-property <name> /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player PlaybackStatus`
- Pause: `busctl --user call <name> /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player Pause`
- Play: `busctl --user call <name> /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player Play`
- gdbus equivalents: `gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.ListNames`; property read via `gdbus call --session --dest <name> --object-path /org/mpris/MediaPlayer2 --method org.freedesktop.DBus.Properties.Get org.mpris.MediaPlayer2.Player PlaybackStatus`. (I could not verify that gdbus has a direct `get` verb — the `Properties.Get` call form is safe.) **Confidence:** high for the forms' validity (busctl verbs `call`/`get-property` are standard), medium for gdbus nuance.

3.4 playerctl pitfalls: `--all-players` acts on the player set present at invocation (a player starting later is missed); a bare `playerctl play`/`pause` targets the *most recently active* player only — **unsafe for exact restore**; also some players (mpd, browser tabs) appear/vanish constantly. **Support:** interpretation of playerctl docs. **Confidence:** medium-high.

3.5 Mid-dictation race (requirement: a player started during dictation must NOT be resumed): enumerate + pause at duck time; store the exact set of well-known names that had `PlaybackStatus == "Playing"` (and `CanPause`); at stop, **intersect the stored set with a fresh ListNames** and resume only that intersection, checking `PlaybackStatus == "Paused"` first. No NameOwnerChanged subscription needed (optional hardening: also capture unique owners via `GetNameOwner` to avoid resuming a new owner of a recycled name). **Support:** researcher inference over 3.1–3.4. **Confidence:** high (as a design).

**Design implication for voice-typing:** ducking = tracked-pause-set (busctl, no new deps), never `playerctl --all-players pause` + `playerctl play`.

### 4. wpctl volume
Sources: [wpctl.c](https://gitlab.freedesktop.org/pipewire/wireplumber/-/blob/master/src/tools/wpctl.c), [WirePlumber docs](https://pipewire.pages.freedesktop.org/wireplumber/). Confidence note: could not run `wpctl --help` this run; grammar/semantics from source knowledge — medium-high.

4.1 Output grammar: `wpctl get-volume @DEFAULT_AUDIO_SINK@` prints exactly `Volume: <float>` and appends ` [MUTED]` when muted — e.g. `Volume: 0.65`, `Volume: 0.65 [MUTED]`. One line, single aggregate value. **Confidence:** high (stable, widely observed grammar).

4.2 `wpctl set-volume @DEFAULT_AUDIO_SINK@ 15%`: **percent without a sign prefix is an absolute set** (to 15% of full scale); `+`/`-` prefixes make it relative; a plain float (`0.15`) is also absolute. **Confidence:** medium-high (consistent with wpctl source semantics; verify once with `wpctl --help` in a shell).

4.3 Restore: feed the float **parsed from a prior `get-volume`** straight back to `set-volume` — both sides use the same scale, so the round-trip restores the exact prior value; also snapshot/restore mute separately (`wpctl set-mute @DEFAULT_AUDIO_SINK@ 1|0`) since mute is independent node state and volume persists while muted. Per-channel volumes are not exposed per-channel by wpctl — `set-volume` applies one value across channels (fine for a round-trip of the aggregate, but a per-channel-balanced sink restores approximately). **Confidence:** medium-high.

4.4 `@DEFAULT_AUDIO_SINK@` is resolved by the session manager **per wpctl invocation** (wpctl is a one-shot client). If the default sink changes mid-dictation, a restore-by-selector targets the **new** device, not the ducked one. **Confidence:** high (stateless one-shot semantics).

**Design implication for voice-typing:** at duck time, resolve and store the concrete node id (e.g. from `wpctl status`) + float volume + mute state; restore by that id (skip gracefully if the node is gone), never blindly by `@DEFAULT_AUDIO_SINK@`.

### 5. wl-clipboard
Sources: [wl-clipboard](https://github.com/bugaevc/wl-clipboard), [wl-copy(1)](https://man.archlinux.org/man/wl-copy.1), [wl-clip-persist](https://github.com/Linus789/wl-clip-persist), [cliphist](https://github.com/christianhe99/cliphist).

5.1 Selections: wl-copy/wl-paste default to the **clipboard** selection; `--primary` targets PRIMARY. Plain `wl-copy` never touches PRIMARY. **Confidence:** high.

5.2 Lifetime: wl-copy **forks**; the parent exits immediately, a background child serves the data offer and the selection lives only while that server runs. When the server exits (or is killed), the offer content is gone unless a clipboard manager snapshotted it — exactly the gap `wl-clip-persist` exists to fill. **Confidence:** high.

5.3 `--paste-once` serves exactly the first paste request then exits (one-shot semantics). `-c`/`--clear` clears the selection. Exit codes: parent exits non-zero on failure to connect/serve; exact codes unverified this run. **Confidence:** medium-high.

5.4 Multi-format: multiple `-t mime` flags offer one **input stream** under several MIME types; wl-copy cannot ingest different content per type, therefore **it cannot faithfully restore a multi-format selection** (save/restore via `wl-paste | wl-copy` collapses to one type). **Confidence:** medium-high (man-page behavior).

5.5 Managers (cliphist etc.) observe via the data-control protocol (`wl-paste --watch`) and snapshot **every** offer — so if one runs, `--copy` text will land in clipboard history regardless of clearing. **Confidence:** medium-high. Sources: [wlr-data-control-v1](https://gitlab.freedesktop.org/wlroots/wlr-protocols/-/blob/master/unstable/wlr-data-control-unstable-v1.xml), [ext-data-control-v1](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/staging/ext-data-control/ext-data-control-v1.xml).

5.6 **Local probes:** no `/usr/share/licenses/{cliphist,wl-clip-persist,clippie}` directories exist → none of the three appear installed as Arch/AUR packages with standard layout (medium confidence; AUR layouts vary). `systemctl --user list-units` **not run** (no shell) — clipboard-manager *service* presence remains unverified; belt-and-braces: treat history capture as possible.

5.7 Safest `voicectl session --copy` pattern: `printf %s "$text" | wl-copy -t text/plain` — clipboard selection only (PRIMARY untouched), explicit MIME (don't rely on wl-copy's tty autodetect), persistent serve until the next selection (normal paste UX). Use `--paste-once` only if one-shot semantics are wanted. If prior-clipboard restoration is required, save/restore single-type via `wl-paste --no-newline` and document the multi-format loss (5.4). **Support:** inference over 5.1–5.5. **Confidence:** high.

**Design implication for voice-typing:** `--copy` = wl-copy clipboard-only with explicit `-t text/plain`; never restore-then-clear via playerctl-style broad ops; accept that a running manager will record it.

### 6. Isolated GTK field apps
6.1 **Local:** `/usr/share/gir-1.0/Gtk-4.0.gir` and `Gtk-3.0.gir` are present → GTK4+GTK3 with introspection data installed. **PyGObject (`gi`) is NOT found** in `/usr/lib/python3.12|3.13/site-packages` or `~/.local/lib/python3.13` (all probes ENOENT) → `/usr/bin/python3 -c 'import gi; …'` would very likely **fail** (medium-high confidence; the exact command was not executable this run). A ~20-line Gtk.Entry probe app therefore needs `pacman -S python-gobject` or a tiny separate venv with PyGObject (or use `gtk4-demo`, which is installed with gtk4 and has entry/text-view pages).
6.2 Env for text-input-v3 under a private compositor (e.g. lab sway): `WAYLAND_DISPLAY=<private>`, `XDG_RUNTIME_DIR` set, `GDK_BACKEND=wayland`; GTK3 additionally `GTK_IM_MODULE=wayland` if anything overrides it; GTK4 needs no IM env. **Confidence:** medium (standard toolkit guidance; cite [GTK docs](https://docs.gtk.org/gtk4/) — verify in the lab).
6.3 Terminals (one line each): **foot** implements text-input-v3 client-side — https://codeberg.org/dnkl/foot — IME-capable; on this box insert-only (given). **kitty** gained Wayland IME via text-input-v3 (kitty ≥0.26, medium confidence) — [kitty docs](https://sw.kovidgoyal.net/kitty/); insert-only here (given). **ghostty** 1.3.1 is IM-dead on this box (given lab fact; upstream tracker https://github.com/ghostty-org/ghostty) — do not route through it.

**Design implication for voice-typing:** target GTK4 fields as the primary verification surface (already lab-proven), keep the probe app as a dependency-light PyGObject mini-app run in its own venv or via gtk4-demo under a private compositor; treat foot/kitty as insert-only sinks and ghostty as out of scope.

## Contradictions
- **ghostty**: upstream advertises text-input/IME support generally, but the lab fact for this machine is 1.3.1 IM-dead — recorded as environment-specific, not resolved (trust the lab fact for this box).
- **brief's "% without +/- is absolute" (wpctl)**: no contradicting evidence found, but it is asserted on source knowledge, not a live `wpctl --help` — one shell check should settle it.
- None of the other external claims had conflicting sources this run (and none could be fetched).

## Missing evidence
- Exact current pywayland version + scanner flag spelling (PyPI/docs fetch needed).
- Origin of the 4000-byte commit_string cap (grep Hyprland/wlroots/toolkit sources) — protocol sets no limit.
- Hyprland input-method-v2 issue numbers + fix versions, 2025–2026 (fcitx5 coexistence, surrounding_text relay).
- Live grammar confirmation of `wpctl get-volume`/`--help`; gdbus property verb; wl-copy exit codes.
- Clipboard-manager presence: no shell, so `systemctl --user list-units` and `command -v cliphist wl-clip-persist clippie` were not run (license-dir probes suggest absent).
- Executable `import gi` check (file-probe says absent).
- input-method-v2 XML text itself (wayland-protocols absent locally; cited from upstream knowledge).

## Sources
- Kept: wayland-protocols input-method-v2 XML (gitlab.freedesktop.org/wayland/wayland-protocols — canonical protocol semantics); text-input-v3 XML (same repo); wlroots (input-method implementation/relay semantics); Hyprland repo/issues (topic for follow-up verification); pywayland GitHub/RTD/PyPI (bindings, scanner, threading model); MPRIS Player spec + D-Bus spec (ducking semantics); playerctl repo (–all-players pitfalls); wireplumber wpctl.c + docs (volume grammar/semantics); wl-clipboard GitHub + wl-copy man page (selections, forking lifetime, -t, -c, --paste-once); wl-clip-persist (offer-lifetime motivation); cliphist (manager observation model); wlr/ext-data-control XMLs (manager observation path); GTK docs (text-input-v3 activation env); foot/kitty/ghostty trackers (terminal IME support).
- Rejected/deprioritized: none — no web search was performed in this run (no tool); all externals come from the canonical sources above via researcher knowledge and are confidence-labeled accordingly.

## Next steps (highest value)
1. With web access: verify the 4000-byte cap's origin (Hyprland/wlroots source search); pin pywayland's current version and scanner flags; pull Hyprland IM-v2 issue list 2025–2026 with fix versions; read wpctl.c for the exact percent-vs-relative parsing.
2. With shell: run the brief's exact probes (`command -v cliphist wl-clip-persist clippie`, `systemctl --user list-units`, `/usr/bin/python3 -c 'import gi'`, `wpctl --help`, `wpctl get-volume @DEFAULT_AUDIO_SINK@`) and re-read the input-method-v2 XML after installing `wayland-protocols`.

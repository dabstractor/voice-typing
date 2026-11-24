# External research: wl-clipboard (wl-copy / wl-paste) — exact-text clipboard semantics

Date researched: 2026-11-24. Web/primary-source research only; the local desktop clipboard was never read or written.

## Version context (load-bearing)

- Upstream repo: **https://github.com/bugaevc/wl-clipboard** (GPLv3+, author Sergey Bugaev).
- Latest release: **v2.3.0**, published 2026-03-22 (`https://github.com/bugaevc/wl-clipboard/releases`, tag list verified via GitHub API). Widely-deployed previous release: **v2.2.1**, published 2023-08-27.
- I diffed the man pages and the relevant source (`wl-paste.c`, `util/misc.c`) between v2.2.1 and v2.3.0/master. Task-relevant behavior is **identical**; the only man-page changes are the new `--sensitive` wl-copy option and `CLIPBOARD_STATE` wording. Man page sources: master is dated 2026-08-06 (`data/wl-clipboard.1`, plus tiny `.so`-stub files `wl-copy.1` / `wl-paste.1` that just include it).
- Canonical flag docs live in the **man page**, not the README (the README says: "Please see the wl-clipboard(1) man page for more details.").
  - Raw man source (canonical): https://github.com/bugaevc/wl-clipboard/blob/master/data/wl-clipboard.1
  - Rendered with section anchors: https://man.archlinux.org/man/wl-clipboard.1 — verified anchors `#DESCRIPTION`, `#OPTIONS`, `#ENVIRONMENT`, `#BUGS`, `#EXAMPLES` exist in the page HTML (checked 2026-11-24)
  - Another rendered mirror: https://www.mankier.com/1/wl-clipboard (anchor names not verified)
- Source files cited below (all on `master`, fetched from raw.githubusercontent.com on 2026-11-24):
  - `src/wl-copy.c` — https://github.com/bugaevc/wl-clipboard/blob/master/src/wl-copy.c
  - `src/wl-paste.c` — https://github.com/bugaevc/wl-clipboard/blob/master/src/wl-paste.c
  - `src/util/misc.c` — https://github.com/bugaevc/wl-clipboard/blob/master/src/util/misc.c
  - `src/util/files.c` — https://github.com/bugaevc/wl-clipboard/blob/master/src/util/files.c
  - `src/types/copy-action.c` — https://github.com/bugaevc/wl-clipboard/blob/master/src/types/copy-action.c

---

## 1. wl-copy

### Default selection: CLIPBOARD (not PRIMARY) — CONFIRMED

Man page (`-p` entry in https://man.archlinux.org/man/wl-clipboard.1#OPTIONS):

> **-p, --primary** — Use the "primary" clipboard instead of the regular clipboard.

So default = the regular (Ctrl+V / CLIPBOARD) selection via `wl_data_device.set_selection`; `-p`/`--primary` switches to the primary selection protocol (zwp_primary_selection / gtk-primary-selection, whichever the compositor has). Source `wl-copy.c`: `registry_find_device_manager(registry, options.primary)`; if missing → `complain_about_selection_support()` → stderr `"The compositor does not seem to support primary selection"` (or a build-without-support message), `exit(1)`.

### -t / --type mime/type — CONFIRMED

Man page:

> **-t mime/type, --type mime/type** — Override the automatically selected MIME type. For wl-copy this option controls which type wl-copy will offer the content as. For wl-paste it controls which of the offered types wl-paste will request the content in. In addition to specific MIME types such as image/png, wl-paste also accepts generic type names such as text and image…

Without `-t`, wl-copy infers the type from the copied content by running `xdg-mime`(1) (man page DESCRIPTION). Important for text offers (source `wl-copy.c`, "Create the source" block): if the type is unset or textual, wl-copy additionally offers the generic text aliases `text/plain`, `text/plain;charset=utf-8`, `TEXT`, `STRING`, `UTF8_STRING` (constants verified in `src/util/string.h`), all served from the same data.

### -f / --foreground and the default forking behavior — CONFIRMED (source-level)

Man page:

> **-f, --foreground (for wl-copy)** — By default, wl-copy forks and serves data requests in the background; this option overrides that behavior, causing wl-copy to run in the foreground.

Source-verified mechanics (`wl-copy.c`, `copy-action.c`):

- **Fork ordering / pipeline safety:** wl-copy first consumes **all of stdin** into a temp file (`dump_stdin_into_a_temp_file()`), infers the MIME type, then sets the selection; `do_set_selection()` in `copy-action.c` calls `device_set_selection(...)` followed by `wl_display_roundtrip(...)`, and only then invokes `did_set_selection_callback`, which forks and has the **parent `exit(0)`**. Net effect: when the `wl-copy` command returns 0, the compositor has already processed `set_selection`; an immediately following `wl-paste` is not racing an unset clipboard at the protocol level. (CONFIRMED from source statement ordering in master, 2026-11; treated as source-level fact about wl-clipboard's own code path.)
- **The background child** redirects stdin/stdout to `/dev/null`, `chdir("/")`, ignores `SIGHUP`, and keeps serving paste requests until the selection is cancelled (`cancelled_callback → exit(0)`, e.g. when another client or a clipboard manager replaces/takes over the selection) or, with `-o`, after one paste (`pasted_callback → exit(0)`).
- **Implications for piping/verification:** use the *default* (forked) mode in scripts: `printf %s "$text" | wl-copy` reads all of stdin, sets the selection, and returns. `--foreground` makes wl-copy **block indefinitely** until the selection is cancelled/replaced — in a normal desktop session that usually only happens when another app copies something — so `--foreground` in a non-interactive script is a hang risk, and the forked parent's exit status is the only observable status.
- wl-copy ignores SIGPIPE and, when reading from argv instead of stdin, copies its command-line arguments.

### --trim-newline — CONFIRMED (exact semantics from source)

Man page:

> **-n, --trim-newline (for wl-copy)** — Do not copy the trailing newline character if it is present in the input file.

Source `util/files.c: trim_trailing_newline()` (master): seeks to the last byte; **if and only if it is exactly `'\n'`, truncates the file by that one byte** (empty file = no-op). Applied **only on the stdin path** (`wl-copy.c` calls it right after `dump_stdin_into_a_temp_file()`; the argv-text path is not trimmed). Therefore:

- Exactly **one** trailing newline is removed, never more (`a\n\n` → `a\n`).
- **Exact-text idiom (no newline added or removed at all):** `printf %s "$text" | wl-copy` — wl-copy itself never appends anything; it copies stdin bytes verbatim. `--trim-newline` is the belt-and-braces variant for producers that add a trailing `\n` (`echo`, `printf '%s\n'`), e.g. `printf '%s\n' "$text" | wl-copy --trim-newline`.
- Corroborating third-party usage: sc-im issue comment, 2022-04: "wl-copy -n copies hello (without the \n that echo appends)" — https://github.com/andmarti1424/sc-im/issues/681 (UNVERIFIED page fetch; found via search snippet).

### --paste-once — CONFIRMED

Man page:

> **-o, --paste-once (for wl-copy)** — Only serve one paste request and then exit. Unless a clipboard manager specifically designed to prevent this is in use, this has the effect of clearing the clipboard after the first paste, which is useful for copying sensitive data such as passwords. Note that this may break pasting into some clients that expect to be able to paste multiple times, in particular pasting into XWayland windows is known to break when this option is used.

### --clear — CONFIRMED

Man page:

> **-c, --clear (for wl-copy)** — Instead of copying anything, clear the clipboard so that nothing is copied.

Source: with `--clear`, wl-copy skips creating/offering a source entirely and sets an empty selection; `did_set_selection_callback` exits 0 right after (`exit(0)` in the `options.clear` branch). BUGS section notes (see §5) that `--clear` doesn't always interact well with overeager clipboard managers.

### Exit codes & "not on Wayland" behavior — CONFIRMED (source-grepped, v2.2.1 and master identical)

- **0** — success (parent, after fork; `--clear`; first paste under `-o`; cancellation), `-v`, `-h`.
- **1** — every error path: unknown option (getopt error + usage to stderr), **failure to connect to a Wayland server**, no such seat / missing wl_seat, missing wl_data_device_manager or primary-selection support, missing data-control support (wl-paste watch), temp-file open failure, and `wl_display_dispatch` failure (`perror("wl_display_dispatch"); return 1;`).
- **Exact output when `$WAYLAND_DISPLAY` is unset / no Wayland server reachable** (`src/util/misc.c: complain_about_wayland_connection()`, verbatim from source; text identical in v2.2.1 and master — verified by diff), then **`exit(1)`**:

```
Failed to connect to a Wayland server
Note: WAYLAND_DISPLAY is unset (falling back to wayland-0)
Note: XDG_RUNTIME_DIR is set to <value>
Please check whether <XDG_RUNTIME_DIR>/wayland-0 socket exists and is accessible.
```

  Variants (same function): if errno ≠ 0 the first line gets `: <strerror>` appended; if `WAYLAND_DISPLAY` **is** set the note reads `Note: WAYLAND_DISPLAY is set to <value>`; if `XDG_RUNTIME_DIR` is unset the note reads `Note: XDG_RUNTIME_DIR is unset` and the "Please check" line is omitted. `wl_display_connect(NULL)` semantics (man page ENVIRONMENT, https://man.archlinux.org/man/wl-clipboard.1#ENVIRONMENT): connects to the socket named by `$WAYLAND_DISPLAY` (falling back to `wayland-0`) under `$XDG_RUNTIME_DIR`. On an X11 session or plain SSH, the connect fails → the above message → **exit status 1**. Practical consequence for scripts: `wl-copy`/`wl-paste` under `set -e` will abort cleanly with status 1 when not on Wayland.

---

## 2. wl-paste

### --no-newline semantics: default appends `\n` ALWAYS for text (not tty-conditional) — CONFIRMED

Man page:

> **-n, --no-newline (for wl-paste)** — Do not append a newline character after the pasted clipboard content. This option is automatically enabled for non-text content types and when using the --watch mode.

Source (`wl-paste.c`, master; the v2.2.1 source is line-for-line the same here — verified by diff):

```c
/* Never append a newline character to binary content */
if (!mime_type_is_text(mime_type)) {
    options.no_newline = 1;
}
...
if (!options.no_newline && !options.watch) {
    rc = write(STDOUT_FILENO, "\n", 1);
```

There is **no `isatty()` check anywhere** in `wl-paste.c` (grep count 0 in both v2.2.1 and master, checked 2026-11-24). Answer to the open question: plain `wl-paste` appends exactly one trailing `\n` to **textual** clipboard content **unconditionally** — to a tty, a pipe, or a file alike — unless `-n/--no-newline` is given; it never appends to non-text MIME types, and never in `--watch` mode. So **every byte-exact read of text must use `wl-paste --no-newline`** (short form `wl-paste -n`).

### -l / --list-types — CONFIRMED

Man page:

> **-l, --list-types (for wl-paste)** — Instead of pasting the selection, output the list of MIME types it is offered in.

Source: prints one MIME type per line, then `exit(0)`. With an **empty** clipboard (NULL offer, non-watch mode) it takes the shared empty-clipboard path below (exit 1), *not* an empty list.

### --watch — CONFIRMED

Man page:

> **-w command..., --watch command... (for wl-paste)** — Instead of pasting once and exiting, continuously watch the clipboard for changes, and run the specified command each time a new selection appears. The spawned process can read the clipboard contents from its standard input. … This mode requires a compositor that supports the wlroots data-control protocol.

(master adds: wl-paste also sets `CLIPBOARD_TYPE` for the spawned command; v2.3.0+ only.) Empty-clipboard events in watch mode spawn the command with `CLIPBOARD_STATE=nil` and stdin attached to `/dev/null` (source `selection_callback`); it keeps running. `CLIPBOARD_STATE` values: `data`, `nil` (empty), `clear` (after `wl-copy --clear`; wl-clipboard currently never actually sets `clear`), `sensitive` (v2.3.0: set when `x-kde-passwordManagerHint` is offered). See https://man.archlinux.org/man/wl-clipboard.1#ENVIRONMENT.

### Exit codes — CONFIRMED

- **0** — success; `--list-types` success; `-v`; `-h`.
- **1** — **empty clipboard (non-watch mode):** `bail("Nothing is copied")` prints `Nothing is copied` to stderr and `exit(1)` (source, both versions).
- **1** — requested/inferred type not offered: stderr `Clipboard content is not available as requested type "..."` (or `inferred output type "..."`), followed by `Use "wl-paste --list-types" to view available types.` (+ ` Use "--type" to explicitly specify a type.` if no explicit type), `exit(1)`.
- **1** — usage errors (`Unexpected argument: ...` etc.), Wayland-connection failure (same `complain_about_wayland_connection()` text/exit as wl-copy, §1), pipe/exec failures, `wl_display_dispatch` failure.

---

## 3. Script round-trip verification — byte-exact semantics

Idiom:

```bash
printf %s "$text" | wl-copy
wl-paste --no-newline | cmp - <(printf %s "$text")
```

Semantics, element by element:

- `printf %s "$text"` emits the exact bytes of `$text` with **no** trailing newline (contrast `echo "$text"` / `printf '%s\n'`, which append `\n`). wl-copy copies stdin verbatim (never appends; `--trim-newline` would remove one trailing `\n` if present — with `printf %s` there is none to remove).
- `wl-paste --no-newline` writes the clipboard's raw bytes with nothing appended (§2). Omitting `-n` makes text comparisons fail whenever `$text` doesn't end in `\n`, because wl-paste adds one unconditionally.
- `cmp - <(...)`: `cmp` (GNU coreutils; BusyBox `cmp` also supports it) treats the operand `-` as stdin and compares **byte for byte**; exit status 0 iff the streams are identical, 1 on the first differing byte or length mismatch (message like `cmp: EOF on - after byte N`, or `- <file> differ: byte X, line Y`). Under `set -e`/`set -o pipefail` this is a strict byte-equality assertion of the round-trip.
- Portability caveat: `<(...)` process substitution is bash/zsh/ksh, not POSIX sh. POSIX-safe variant: `wl-paste -n | cmp - expected_bytes_file`.
- Suggested hardened form for a Wayland CLI that must copy EXACT text:

  ```bash
  copy_exact() {  # $1 = text
      printf %s "$1" | wl-copy || return 1
      wl-paste --no-newline | cmp -s - <(printf %s "$1")
  }
  ```

  (`cmp -s` = silent, status only; checking wl-copy's exit status matters because a missing Wayland session exits 1 — see §1.)
- Residual caveats for verification (flagged, not silently resolved):
  - **Concurrent selection change** between the copy and the verify read (another app or the user copying) will fail the compare — correct behavior for a verification, but a source of flaky CI in a live session.
  - **GTK3 apps copy text with CRLF**; wl-clipboard does not normalize (man page BUGS, workaround `dos2unix`). If `$text` is compared against a clipboard set by a GTK3 app, `\r\n` mismatches are expected. https://man.archlinux.org/man/wl-clipboard.1#BUGS
  - **Clipboard managers** can serve the data on the original copier's behalf (§5); they are expected to serve the same bytes, but any manager bug is outside wl-clipboard's control (UNVERIFIED for any specific manager).
  - On compositors **without** data-control support, wl-paste briefly opens a tiny transparent popup surface to receive focus and access the clipboard; man page BUGS warns this can flash, and *can manifest as a hang* if the compositor never focuses the popup — relevant if a verification step wedges. Same URL as above.
  - Reading the clipboard with wl-paste does not modify it (it is a read-only consumer; the popup hack is a focus workaround, not a selection change). CONFIRMED from wl-paste source paths (no `set_selection` call in `wl-paste.c`).

---

## 4. Canonical README quotes — https://github.com/bugaevc/wl-clipboard

README (anchor for the top section: https://github.com/bugaevc/wl-clipboard#wl-clipboard-wayland-clipboard-utilities, retrieved 2026-11-24) introduces the tools and defers flag docs to the man page:

> This project implements two command-line Wayland clipboard utilities, `wl-copy` and `wl-paste`, that let you easily copy data between the clipboard and Unix pipes, sockets, files and so on.
>
> ```bash
> # Copy a simple text message:
> $ wl-copy Hello world!
>
> # Copy the list of files in ~/Downloads:
> $ ls ~/Downloads | wl-copy
>
> # Copy an image:
> $ wl-copy < ~/Pictures/photo.png
>
> # Copy the previous command:
> $ wl-copy "!!"
>
> # Paste to a file:
> $ wl-paste > clipboard.txt
>
> # Sort clipboard contents:
> $ wl-paste | sort | wl-copy
>
> # Upload clipboard contents to a pastebin on each change:
> $ wl-paste --watch nc paste.example.org 5555
> ```
>
> Please see the wl-clipboard(1) man page for more details.

Man page EXAMPLES section includes the exact-text paste idiom: `wl-paste -n > clipboard.txt` ("Paste to a file, without appending a newline"). https://man.archlinux.org/man/wl-clipboard.1#EXAMPLES

Other README anchors: `#installing` ("wl-clipboard is likely available in your favorite Linux or BSD distro"), `#license` (GPLv3+), `#related-projects` (wl-clipboard-x11 wrapper; wl-clipboard-rs Rust reimplementation).

---

## 5. wl-copy replacing existing offers; clipboard managers watching CLIPBOARD

- **One data source per selection; a new copy replaces the previous one.** Wayland's `wl_data_device.set_selection` request sets *the* selection from one client's data source ("This request asks the compositor to set the selection to the data from the source on behalf of the client… To unset the selection, set the source to NULL." — wayland.xml protocol source, https://gitlab.freedesktop.org/wayland/wayland/-/blob/main/protocol/wayland.xml, request `wl_data_device:set_selection`, checked 2026-11-24). Inference (mine, protocol-level, not stated verbatim by wl-clipboard docs): each `wl-copy` invocation therefore makes the compositor advertise a fresh offer list and invalidates the previous selection's offers — there is no merging of old and new offers.
- **A single wl-copy invocation offers one "real" MIME type** (explicit `-t` or inferred), plus — when the type is unset or textual — the alias offers `text/plain`, `text/plain;charset=utf-8`, `TEXT`, `STRING`, `UTF8_STRING`, all backed by the same bytes (source `wl-copy.c`, §1).
- **No multi-MIME copying.** Man page BUGS (https://man.archlinux.org/man/wl-clipboard.1#BUGS): "There is currently no way to copy data in multiple MIME types, such as multiple image formats, at the same time." Upstream tracking issue: https://github.com/bugaevc/wl-clipboard/issues/71
- Same BUGS section: "When trying to paste content copied with wl-copy, wl-copy does not check whether the requested MIME type is among those it has offered, and always provides the same data in response."
- **Clipboard managers.** On compositors with data-control (zwlr/ext-data-control-v1), managers watch CLIPBOARD with `wl-paste --watch` — the canonical idiom per the Arch Wiki Clipboard page (cliphist: `exec wl-paste --watch cliphist store`; clipman: `wl-paste -t text --watch clipman store --no-persist`; primary variant `wl-paste -p -t text --watch …`): https://wiki.archlinux.org/title/Clipboard (retrieved 2026-11-24). Interplay with wl-copy, from source + man page:
  - A manager typically **takes over** the selection right after a copy, which cancels the forked wl-copy's source → its background process exits 0 (`cancelled_callback`). Without a manager, the forked wl-copy keeps running to serve pastes.
  - Overeager managers can defeat `--clear`/`--paste-once` semantics — man page BUGS: "wl-copy --clear and wl-copy --paste-once don't always interact well with clipboard managers that are overeager to preserve clipboard contents." (Same for the `--paste-once` "clipboard manager specifically designed to prevent this" caveat in §1.)
  - v2.3.0 added `wl-copy --sensitive` (man page: "Hint that the data being copied contains passwords, keys, or other sensitive content. Some clipboard managers may react by not persisting the copied data in the clipboard history."), corresponding to the offer of `x-kde-passwordManagerHint` and `CLIPBOARD_STATE=sensitive` for watch-mode consumers.

---

## Evidence labels

- CONFIRMED (primary source, URL + date): all man-page quotes (canonical `data/wl-clipboard.1` on master and v2.3.0/v2.2.1 tags; rendered mirror man.archlinux.org, anchors verified); all exit codes and stderr strings (`src/wl-copy.c`, `src/wl-paste.c`, `src/util/misc.c`, fetched 2026-11-24); `--trim-newline` single-byte semantics (`src/util/files.c`); no-`isatty` newline behavior (`src/wl-paste.c`, master + v2.2.1 diffed); fork-after-roundtrip ordering (`src/types/copy-action.c` + `src/wl-copy.c`); wayland.xml `set_selection` wording (gitlab.freedesktop.org, 2026-11-24); release dates (GitHub API, 2026-11-24); Arch Wiki watch-based manager examples (wiki.archlinux.org, 2026-11-24).
- UNVERIFIED: sc-im #681 comment text (search snippet only); mankier.com mirror anchor names (page found via search, anchors not checked).
- CONFLICTING: none found. Note only that distro-packaged v2.2.1 (2023) predates `--sensitive`; every other flag/behavior documented here is identical across v2.2.1, v2.3.0, and master.

#!/usr/bin/env python3
"""ime_g3_field_edit — the G3 instrumented GRAPHICAL EDITOR field (P1.M5.T2.S2).
argv: <root> [--readonly] [--tag NAME]

Fork lineage: tests/ime_g3_field_gtk.py (P1.M4.T5.S1, itself forked from
tools/im-lab/field_gtk.py — both READ-ONLY evidence records, never edited).
Runs on SYSTEM python3 — PyGObject/gi is system-wide, the daemon venv has no
gi. This app is the hand-written TextView-class document editor (no editor app
is installed on this box; M4.T5.S1 precedent "hand-written field apps only"):
Gtk.TextView inside a Gtk.ScrolledWindow — a genuinely different IM consumer
from Gtk.Entry (buffer-based, preedit-in-view, its own surrounding-text path;
the gedit-class widget).

Kept from the lineage verbatim: ATOMIC state dump (field*.tmp + os.replace ->
field*.json), ready flag via GLib.idle_add lineage (dump("init") + ready file
in activate), 2000-dump cap, RING_MAX=256 per-frame samples, RLE_CAP=64 pairs,
add_tick_callback frame oracle with the frame-kind dump on hash change, GTK +
PyGObject versions in every dump, --readonly/--tag handling.

Replaced for the TextView (dump schema v2 unchanged — waiters port as-is):
  - text  = full buffer text (get_bounds + get_text)
  - pos   = buffer.get_iter_at_mark(buffer.get_insert()).get_offset() (CHARS)
  - cseq  = TextBuffer "changed" signal count (GTK fires 1-2 per commit)
  - cursor dumps on buffer "mark-set" of the insert mark (Entry's
    notify::cursor-position has no TextView equivalent)
  - 'activated' = ENTER-PRESS counter via EventControllerKey (Return /
    KP_Enter / ISO_Enter) — must stay 0 (no submission anywhere)
  - 'keys'  = received NON-Enter key counter (must stay 0 — IM commits
    generate zero key events; grabbed keys never reach the app at all)
  - --readonly -> text_view.set_editable(False) +
    set_cursor_visible(False) (docs.gtk.org/gtk4/method.TextView.set_editable)
    under the title "vtg3-editor-ro"
  - window title "vtg3-editor" (+ "-ro"/"-<tag>" suffixes), app id
    "org.vtg3.editor"

Dump schema v2 (superset, identical shape to the Entry field):
  {seq, cseq, kind, text, pos, t, frames, activated, keys, editable, gtk,
   pygobject, ring_rle, dump_capped}
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gio, Gtk, Gdk  # noqa: E402

MAX_DUMPS = 2000  # im-lab lineage: bounded scratch, then stop writing
RING_MAX = 256  # per-frame samples kept (bounded)
RLE_CAP = 64  # pairs in a dump's ring_rle (newest kept)
WINDOW_TITLE = "vtg3-editor"
_ENTER_KEYVALS = frozenset({Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter})


def main() -> int:
    args = [a for a in sys.argv[1:]]
    readonly = "--readonly" in args
    tag = ""
    if "--tag" in args:
        tag = args[args.index("--tag") + 1]
    root = Path(args[0])
    suffix = f"-{tag}" if tag else ""

    seq = {"all": 0, "changed": 0, "activated": 0, "keys": 0, "frames": 0}
    ring: collections.deque = collections.deque(maxlen=RING_MAX)
    state = {
        "dump_capped": False,
        "last_dumped_hash": None,
        "view": None,
        "buffer": None,
    }

    gtk_version = (
        f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
    )

    def dump(kind: str) -> None:
        view, buf = state["view"], state["buffer"]
        if view is None or buf is None:
            return
        if seq["all"] >= MAX_DUMPS:
            if state["dump_capped"]:  # already marked — silence forever after
                return
            state["dump_capped"] = True  # fall through: write the marking dump
        seq["all"] += 1
        if kind == "changed":
            seq["changed"] += 1
        (s, e) = buf.get_bounds()
        text = buf.get_text(s, e, False)
        pos = buf.get_iter_at_mark(buf.get_insert()).get_offset()
        state_ = {
            "seq": seq["all"],
            "cseq": seq["changed"],
            "kind": kind,
            "text": text,
            "pos": pos,
            "t": round(time.monotonic() * 1000, 3),
            "frames": seq["frames"],
            "activated": seq["activated"],
            "keys": seq["keys"],
            "editable": bool(view.get_editable()),
            "gtk": gtk_version,
            "dump_capped": state["dump_capped"],
            "ring_rle": _rle(list(ring)),
        }
        tmp = root / f"field{suffix}.tmp"
        tmp.write_text(json.dumps(state_, ensure_ascii=False))
        os.replace(tmp, root / f"field{suffix}.json")

    def _rle(samples) -> list:
        """Collapse the per-frame ring into [(hash, n), …], newest-LAST, cap 64."""
        out: list[list] = []
        for h, _pos, _cseq, _t in samples:
            if out and out[-1][0] == h:
                out[-1][1] += 1
            else:
                out.append([h, 1])
        return out[-RLE_CAP:]

    def on_tick(_view, _frame_clock):
        """One sample per painted frame; keeps the clock alive (SOURCE_CONTINUE).
        Never raises into the GTK main loop."""
        try:
            buf = state["buffer"]
            if buf is None or state["view"] is None or not state["view"].get_mapped():
                return GLib.SOURCE_CONTINUE
            (s, e) = buf.get_bounds()
            text = buf.get_text(s, e, False)
            h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
            pos = buf.get_iter_at_mark(buf.get_insert()).get_offset()
            seq["frames"] += 1
            ring.append((h, pos, seq["changed"], time.monotonic()))
            if h != state["last_dumped_hash"]:
                state["last_dumped_hash"] = h
                dump("frame")
        except Exception:  # noqa: BLE001 — an oracle hiccup must not kill the loop
            pass
        return GLib.SOURCE_CONTINUE

    app = Gtk.Application(
        application_id="org.vtg3.editor", flags=Gio.ApplicationFlags.NON_UNIQUE
    )

    def activate(_app):
        title = WINDOW_TITLE + ("-ro" if readonly else "")
        win = Gtk.ApplicationWindow(application=app, title=title)
        win.set_default_size(700, 320)
        view = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            monospace=True,
            top_margin=8,
            left_margin=8,
        )
        if readonly:
            view.set_editable(False)  # the REFUSING target (non-editable view)
            view.set_cursor_visible(False)
        view.add_tick_callback(on_tick)
        buf = view.get_buffer()
        state["view"] = view
        state["buffer"] = buf
        scroller = Gtk.ScrolledWindow(
            hexpand=True, vexpand=True, min_content_width=640, min_content_height=280
        )
        scroller.set_child(view)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=20)
        box.append(scroller)
        win.set_child(box)

        insert_mark = buf.get_insert()

        def on_changed(_buf):
            dump("changed")

        def on_mark_set(_buf, _iter, mark):
            if mark is insert_mark:
                dump("cursor")

        ctrl = Gtk.EventControllerKey()

        def _key(_c, keyval, _keycode, _state):
            if keyval in _ENTER_KEYVALS:
                seq["activated"] += 1  # Enter/submission counter — must stay 0
                dump("activate")
            else:
                seq["keys"] += 1  # received-key counter — must stay 0 on the IM route
            return False  # never consume — the counters stay observational

        ctrl.connect("key-pressed", _key)
        view.add_controller(ctrl)
        buf.connect("changed", on_changed)
        buf.connect("mark-set", on_mark_set)
        win.present()
        dump("init")  # the field file exists before the first IM event
        ready = {
            "gtk": gtk_version,
            "pygobject": gi.__version__,
            "readonly": readonly,
            "title": title,
        }
        payload = json.dumps(ready, ensure_ascii=False)
        (root / f"field{suffix}.ready").write_text(payload)

    app.connect("activate", activate)
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""ime_g3_field_gtk — the G3 instrumented GTK4 field (P1.M4.T5.S1). argv:
<root> [--readonly] [--tag NAME]

Fork of tools/im-lab/field_gtk.py (im-lab evidence run 2026-11-22, 29 rows /
24 pass — see plan/008_a47116bb2b79/P1M4T5S1/research/imlab-pattern.md; the
original is an EVIDENCE record and is never edited). Runs on SYSTEM python3 —
PyGObject/gi is system-wide, the daemon venv has no gi (d2 map §6).

Kept from the lineage: Gtk.Application field app, window titled
"imlab-g3-field-gtk", one Gtk.Entry, `changed` + `notify::cursor-position`
signals, ATOMIC state dump (field*.tmp + os.replace -> field*.json), ready flag
via GLib.idle_add, 2000-dump cap.

G3 additions (the frame-level single-edit oracle hardware):
  - add_tick_callback on the entry: per-frame sample (sha1(text)[:8], pos,
    cseq, t) into a bounded ring (deque maxlen=256); a `frames` counter counts
    painted ticks. The tick callback keeps the frame clock alive every frame
    while mapped (docs.gtk.org/gtk4/method.Widget.add_tick_callback.html).
  - a dump also fires on a tick when the text hash CHANGED since the last dump
    (kind="frame") — so a commit's painting frame is INSIDE the window the
    harness later analyzes, not lost after the last signal dump.
  - ring_rle: run-length-encoded text-hash ring [[hash, n], …] newest-LAST,
    capped at 64 pairs — per-frame payload never leaves the app.
  - `activate` signal counter (Enter/submission must stay 0) + a
    Gtk.EventControllerKey received-key counter (the IM route commits text
    with ZERO key events — delivery cannot self-trigger).
  - GTK version + editable flag in every dump; --readonly boots the REFUSING
    target (Gtk.Entry not editable; docs.gtk.org/gtk4/method.Entry.set_editable)
    under the title "imlab-g3-field-gtk-ro" and files field-<tag>.*.

Dump schema v2 (superset of the im-lab schema — waiters port as-is):
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
from gi.repository import GLib, Gio, Gtk  # noqa: E402

MAX_DUMPS = 2000  # im-lab lineage: bounded scratch, then stop writing
RING_MAX = 256  # per-frame samples kept (bounded)
RLE_CAP = 64  # pairs in a dump's ring_rle (newest kept)
WINDOW_TITLE = "imlab-g3-field-gtk"


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
    state = {"dump_capped": False, "last_dumped_hash": None, "entry": None}

    gtk_version = (
        f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
    )

    def dump(kind: str, entry) -> None:
        if seq["all"] >= MAX_DUMPS:
            if state["dump_capped"]:  # already marked — silence forever after
                return
            state["dump_capped"] = True  # fall through: write the marking dump
        seq["all"] += 1
        if kind == "changed":
            seq["changed"] += 1
        text = entry.get_text()
        state_ = {
            "seq": seq["all"],
            "cseq": seq["changed"],
            "kind": kind,
            "text": text,
            "pos": entry.get_position(),
            "t": round(time.monotonic() * 1000, 3),
            "frames": seq["frames"],
            "activated": seq["activated"],
            "keys": seq["keys"],
            "editable": bool(entry.get_editable()),
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

    def on_tick(_widget, _frame_clock):
        """One sample per painted frame; keeps the clock alive (SOURCE_CONTINUE).
        Never raises into the GTK main loop."""
        try:
            entry = state["entry"]
            if entry is None or not entry.get_mapped():
                return GLib.SOURCE_CONTINUE
            text = entry.get_text()
            h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
            seq["frames"] += 1
            ring.append((h, entry.get_position(), seq["changed"], time.monotonic()))
            if h != state["last_dumped_hash"]:
                state["last_dumped_hash"] = h
                dump("frame", entry)
        except Exception:  # noqa: BLE001 — an oracle hiccup must not kill the loop
            pass
        return GLib.SOURCE_CONTINUE

    app = Gtk.Application(
        application_id="org.imlab.g3field", flags=Gio.ApplicationFlags.NON_UNIQUE
    )

    def activate(_app):
        title = WINDOW_TITLE + ("-ro" if readonly else "")
        win = Gtk.ApplicationWindow(application=app, title=title)
        entry = Gtk.Entry(hexpand=True, placeholder_text="g3 field", width_request=600)
        if readonly:
            entry.set_editable(False)
        state["entry"] = entry
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=40)
        box.append(entry)
        win.set_child(box)
        ctrl = Gtk.EventControllerKey()

        def on_activate(_e):
            seq["activated"] += 1
            dump("activate", _e)

        def _key(_c, _keyval, _keycode, _state):
            seq["keys"] += 1
            return False  # never consume — the counter must stay observational

        entry.connect("changed", lambda e: dump("changed", e))
        entry.connect("notify::cursor-position", lambda e, _p: dump("cursor", e))
        entry.connect("activate", on_activate)
        ctrl.connect("key-pressed", _key)
        ctrl.connect("key-released", _key)
        entry.add_controller(ctrl)
        entry.add_tick_callback(on_tick)
        win.present()
        dump("init", entry)  # the field file exists before the first IM event
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

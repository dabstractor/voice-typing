"""GTK4 editable field for the im-lab spike. argv: <root>

A real toolkit text field (Gtk.Entry). Dumps its own state atomically to
<root>/field.json on every change / cursor move / preedit update, capped at
2000 dumps. cseq counts document edits only (changed signal), seq counts all
dumps — that distinction is how rows assert "ONE visible edit" vs "zero".
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

MAX_DUMPS = 2000


def main() -> int:
    root = Path(sys.argv[1])
    seq = {"all": 0, "changed": 0}

    def dump(kind: str, entry, preedit: str | None = None) -> None:
        if seq["all"] >= MAX_DUMPS:
            return
        seq["all"] += 1
        if kind == "changed":
            seq["changed"] += 1
        state = {"seq": seq["all"], "cseq": seq["changed"], "kind": kind,
                 "text": entry.get_text(), "pos": entry.get_position(),
                 "t": round(time.monotonic() * 1000, 3)}
        if preedit is not None:
            state["preedit"] = preedit
        tmp = root / "field.tmp"
        tmp.write_text(json.dumps(state, ensure_ascii=False))
        os.replace(tmp, root / "field.json")

    app = Gtk.Application(application_id="org.imlab.field")

    def activate(_app):
        win = Gtk.ApplicationWindow(application=app, title="imlab-field-gtk")
        entry = Gtk.Entry(hexpand=True, placeholder_text="spike field")
        entry.props.width_request = 600
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=40)
        box.append(entry)
        win.set_child(box)
        entry.connect("changed", lambda e: dump("changed", e))
        entry.connect("notify::cursor-position", lambda e, _p: dump("cursor", e))
        win.present()
        GLib.idle_add(lambda: (root / "field.ready").touch() or False)

    app.connect("activate", activate)
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())

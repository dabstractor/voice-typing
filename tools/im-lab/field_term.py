"""Terminal-side editable field for the im-lab spike. argv: <root>

Runs inside the terminal under test and uses GNU readline — a real
full-featured line editor with its own caret, kill ring and undo. A poll
thread dumps the live line buffer to <root>/term.json (atomic replace,
capped at 2000 writes). This measures what the terminal DELIVERS to the app:
if a commit_string arrives as plain text the buffer grows by exactly that
text; bracketed-paste markers would show up here if any were sent.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import readline

MAX_DUMPS = 2000


def main() -> int:
    root = Path(sys.argv[1])
    state = {"line": "", "seq": 0, "t": 0.0}

    def poll():
        while state["seq"] < MAX_DUMPS:
            line = readline.get_line_buffer()
            if line != state["line"]:
                state["line"] = line
                state["seq"] += 1
                state["t"] = round(time.monotonic() * 1000, 3)
                tmp = root / "term.tmp"
                tmp.write_text(json.dumps(state, ensure_ascii=False))
                os.replace(tmp, root / "term.json")
            time.sleep(0.005)

    (root / "term.ready").touch()
    state["seq"] = 1
    tmp = root / "term.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    os.replace(tmp, root / "term.json")
    t = threading.Thread(target=poll, daemon=True)
    t.start()
    try:
        line = input("")
    except EOFError:
        line = state["line"]
    (root / "term.final").write_text(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

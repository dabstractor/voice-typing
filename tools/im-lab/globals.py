"""Passive registry listing: connect, get_registry, one sync, print globals.

Read-only observation of a compositor (no binds of functional interfaces,
no input, no clipboard, no surfaces). Used to learn which text-injection
protocols a compositor advertises: zwp_input_method_manager_v2 (IME route),
zwp_virtual_keyboard_manager_v1 (typing route), zwlr_data_control_manager_v1
(clipboard route), zwp_text_input_manager_v3 (app side).

Run: WAYLAND_DISPLAY=<sock> python3 globals.py [json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wlwire import Client, WlError

INTEREST = (
    "zwp_input_method_manager_v2",
    "zwp_input_method_manager_v1",
    "zwp_text_input_manager_v3",
    "zwp_virtual_keyboard_manager_v1",
    "zwlr_data_control_manager_v1",
    "zwp_primary_selection_device_manager_v1",
    "wl_seat",
)


def main() -> int:
    try:
        c = Client()
        c.registry = c.new("wl_registry")
        c.request(1, "wl_display", "get_registry", c.registry)
        c.roundtrip()
    except (WlError, OSError) as e:
        print(json.dumps({"error": str(e)}))
        return 1
    found = {name: ver for name, ver in c.globals.values() if name in INTEREST}
    if len(sys.argv) > 1 and sys.argv[1] == "json":
        print(json.dumps({"globals": sorted(f"{n} v{v}" for n, v in c.globals.values()),
                          "text_injection": found}))
    else:
        print(json.dumps({"text_injection": found}, indent=None))
        print(f"total globals: {len(c.globals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

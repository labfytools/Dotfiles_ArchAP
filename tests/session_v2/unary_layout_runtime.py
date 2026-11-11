#!/usr/bin/env python3
"""TEST_ONLY: reconstruct nested unary tabbed/stacked under isolated SwayFX.

No IPC goes to the user's Sway socket; all processes are lab-owned children.
"""
from common import *
from lab import Lab, Surfaces, build_helper
from session_v2.ipc import Sway
from session_v2.schema import validate
from session_v2.snapshot import capture
from session_v2.executor import Executor
from session_v2.storage import private_dir


def target(layout):
    data = fixture({"splith": ["A", "B"]})
    data["version"] = 2
    data["focus_workspace"] = "TEST_ONLY_TARGET"
    for slot in data["window_slots"]:
        slot["state"]["scratchpad"] = "none"
    data["workspaces"][0]["root"]["children"][1] = {
        "layout": layout, "children": [{"slot_id": "B"}]}
    next(s for s in data["window_slots"] if s["slot_id"] == "B")["tree_path"] = [1, 0]
    return validate(data)


def main():
    with Lab() as lab:
        helper = build(lab.directory)
        surface_binary = build_helper(lab.directory)
        runtime = private_dir(lab.directory / "runtime-v2")
        sway = Sway(lab.socket)
        for layout in ("tabbed", "stacked"):
            data = target(layout)
            apps = Surfaces(lab, surface_binary)
            lab.command('workspace "TEST_ONLY_SOURCE"')
            try:
                apps.create("TEST_ONLY_app-A")
                apps.create("TEST_ONLY_app-B")
                result = Executor(sway, catalog(data), None, runtime,
                                  helper, lab.env).apply(data, True)
                saved = capture(sway, catalog(data), None)
                root = next(w["root"] for w in saved["workspaces"]
                            if w["workspace"] == "TEST_ONLY_TARGET")
                assert root["layout"] == "splith", root
                child = root["children"][1]
                assert child["layout"] == layout and len(child["children"]) == 1, root
                assert result["status"] == "success", result
                print(f"HEADLESS_{layout.upper()}_RECONSTRUCTION=PASS", flush=True)
            finally:
                apps.close()


if __name__ == "__main__":
    main()

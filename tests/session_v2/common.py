"""Fixtures isolées ; imports production réels, sockets headless possédés."""
import copy
import os
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[2]
BACKEND = Path(os.environ.get("LABFY_SESSION_V2_BACKEND", str(REPO / "quickshell/.config/quickshell/labfy-sway")))
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO / "tests/session_v2/fixtures"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
from session_v2.applications import Catalog, Spec
from session_v2.schema import validate


def fixture(shape=None, workspace="TEST_ONLY_TARGET"):
    shape = shape or {"splitv": ["A", {"splith": ["B", "C"]}]}
    slots, apps = [], []
    def tree(n, path=()):
        if isinstance(n, str):
            app = "app-" + n
            slots.append({"slot_id": n, "application_id": app, "workspace": workspace,
                          "tree_path": list(path), "state": {"floating": False, "geometry": None, "fullscreen": False, "scratchpad": False},
                          "identity_requirement": "exact", "identity_evidence": {"type": "application-singleton", "id": app}})
            apps.append({"application_id": app, "desktop_entry": app + ".desktop", "strategy": "managed-autostart", "expected_windows": 1,
                         "managed_by": "autostart", "identity_provider": None})
            return {"slot_id": n}
        layout, children = next(iter(n.items()))
        return {"layout": layout, "children": [tree(c, path + (i,)) for i, c in enumerate(children)]}
    root = tree(shape)
    return validate({"schema": "labfy.sway.session-v2", "version": 1,
                     "metadata": {"created_ns": time.time_ns(), "sway_session": "test", "reason": "manual"},
                     "outputs": [{"name": "HEADLESS-1"}], "applications": apps, "window_slots": slots,
                     "workspaces": [{"workspace": workspace, "output": "HEADLESS-1", "root": root}], "focus": slots[0]["slot_id"]})


def catalog(data):
    return Catalog(tuple(Spec(a["application_id"], a["desktop_entry"], ("TEST_ONLY_" + a["application_id"],),
                              a["strategy"], (), a["identity_provider"]) for a in data["applications"]))


def build(directory):
    import subprocess
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "gtk+-3.0", "gdk-wayland-3.0"], text=True).split()
    binary = Path(directory) / "labfy-v2-anchor"
    subprocess.run(["cc", "-std=c17", "-Wall", "-Wextra", "-Werror", str(BACKEND / "session_v2/anchor_helper.c"), "-o", str(binary), *flags], check=True)
    return binary

# Les résultats TEST_ONLY restent locaux et ne sont jamais publiés avec les sources.
EVIDENCE = Path(os.environ.get("LABFY_SESSION_V2_EVIDENCE", str(REPO / "build/session-v2-tests")))

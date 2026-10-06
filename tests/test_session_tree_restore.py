"""STEP19C : compilation pure du sous-ensemble d'arbre Sway prouvé."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "quickshell/.config/quickshell/labfy-sway/session/session_tree_restore.py"


def load_module():
    spec = importlib.util.spec_from_file_location("session_tree_restore_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tree = load_module()


def load_executor():
    path = ROOT / "quickshell/.config/quickshell/labfy-sway/session/session_executor.py"
    spec = importlib.util.spec_from_file_location("session_tree_executor_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


executor = load_executor()


def make_snapshot(
    *,
    live=False,
    layout="splith",
    order=(1, 2, 3),
    nested=False,
    workspace_layout="splith",
    floating_four=False,
):
    prefix = "l" if live else "w"
    con_base = 100 if live else 900
    windows = []
    for number in range(1, 5 if floating_four else 4):
        window_id = f"{prefix}{number}"
        parent = f"{prefix}root"
        branch = "tiling"
        index = order.index(number) if number in order else 0
        floating = False
        if number == 4:
            parent = None
            branch = "floating"
            index = 0
            floating = True
        elif nested and number in {2, 3}:
            parent = f"{prefix}nested"
            index = number - 2
        windows.append({
            "window_id": window_id,
            "runtime": {"con_id": con_base + number, "pid": 200 + number},
            "workspace": "8",
            "floating": floating,
            "percent": 0.5 if nested and number in {2, 3} else 1 / 3,
            "tree_position": {"parent_container_id": parent, "branch": branch, "index": index},
        })
    children = []
    for number in order:
        if nested and number == 2:
            children.append({"kind": "container", "id": f"{prefix}nested"})
            continue
        if nested and number == 3:
            continue
        children.append({"kind": "window", "id": f"{prefix}{number}"})
    containers = [{
        "container_id": f"{prefix}root",
        "layout": layout,
        "percent": 1.0,
        "children": children,
        "floating_children": [],
    }]
    if nested:
        containers.append({
            "container_id": f"{prefix}nested",
            "layout": "splitv" if layout == "splith" else "splith",
            "percent": 2 / 3,
            "children": [
                {"kind": "window", "id": f"{prefix}2"},
                {"kind": "window", "id": f"{prefix}3"},
            ],
            "floating_children": [],
        })
    roots = {
        "tiling": [{"kind": "container", "id": f"{prefix}root"}],
        "floating": ([{"kind": "window", "id": f"{prefix}4"}] if floating_four else []),
    }
    return {
        "workspaces": [{"name": "8", "layout": workspace_layout, "roots": roots}],
        "containers": containers,
        "windows": windows,
    }


def make_plan(source, live, *, omit=()):
    actions = []
    for number in range(1, len(source["windows"]) + 1):
        if number in omit:
            continue
        live_window = live["windows"][number - 1]
        actions.append({
            "action": "reuse-window",
            "source_window": f"w{number}",
            "live_window": copy.deepcopy(live_window),
        })
    actions.append({"action": "restore-tree-position", "source_window": "w1"})
    return {"actions": actions}


class TreeCompilerTest(unittest.TestCase):
    def compile(self, source, live, **kwargs):
        return tree.compile_tree_restore(source, live, make_plan(source, live, **kwargs))

    def test_identical_tree_has_no_operations(self):
        result = self.compile(make_snapshot(), make_snapshot(live=True))
        self.assertEqual(result["operations"], [])

    def test_root_splith(self):
        result = self.compile(make_snapshot(layout="splith"), make_snapshot(live=True, layout="tabbed"))
        self.assertEqual(result["operations"][-1]["layout"], "splith")

    def test_root_splitv(self):
        result = self.compile(make_snapshot(layout="splitv"), make_snapshot(live=True, layout="splith"))
        self.assertEqual(result["operations"][-1]["layout"], "splitv")

    def test_root_tabbed(self):
        result = self.compile(make_snapshot(layout="tabbed"), make_snapshot(live=True, layout="splith"))
        self.assertEqual(result["operations"][-1]["layout"], "tabbed")

    def test_root_stacked(self):
        result = self.compile(make_snapshot(layout="stacked"), make_snapshot(live=True, layout="splith"))
        self.assertEqual(result["operations"][-1]["layout"], "stacked")

    def test_child_order_diff_uses_typed_relative_moves(self):
        result = self.compile(make_snapshot(order=(1, 2, 3)), make_snapshot(live=True, order=(3, 1, 2)))
        self.assertEqual([item["operation"] for item in result["operations"]], ["move-relative"])
        self.assertEqual(result["operations"][0]["relation"], "after")

    def test_nested_supported_tree(self):
        result = self.compile(make_snapshot(nested=True), make_snapshot(live=True))
        self.assertEqual(
            [item["operation"] for item in result["operations"]],
            ["set-split-orientation", "move-relative"],
        )

    def test_nested_unsupported_tree(self):
        source = make_snapshot(nested=True)
        nested = source["containers"][1]
        nested["children"] = [{"kind": "container", "id": "wdeep"}]
        source["containers"].append({
            "container_id": "wdeep", "layout": "splith", "percent": 1.0,
            "children": [{"kind": "window", "id": "w2"}, {"kind": "window", "id": "w3"}],
            "floating_children": [],
        })
        with self.assertRaisesRegex(tree.TreeRestoreError, "unsupported-nested-tree"):
            self.compile(source, make_snapshot(live=True))

    def test_missing_target_window(self):
        with self.assertRaisesRegex(tree.TreeRestoreError, "missing-target-window"):
            self.compile(make_snapshot(), make_snapshot(live=True), omit=(3,))

    def test_unexpected_live_window(self):
        source = make_snapshot(floating_four=True)
        live = make_snapshot(live=True, floating_four=True)
        live["workspaces"][0]["roots"]["floating"] = []
        live["workspaces"][0]["roots"]["tiling"].append({"kind": "window", "id": "l4"})
        live["windows"][3]["floating"] = False
        with self.assertRaisesRegex(tree.TreeRestoreError, "unexpected-live-window"):
            self.compile(source, live)

    def test_floating_branch_is_preserved_and_excluded(self):
        result = self.compile(make_snapshot(floating_four=True), make_snapshot(live=True, floating_four=True))
        self.assertEqual(result["operations"], [])
        self.assertNotIn("w4", repr(result["workspaces"][0]["target_tree"]))

    def test_percent_is_explicitly_unsupported(self):
        source = make_snapshot()
        live = make_snapshot(live=True)
        live["windows"][0]["percent"] = 0.9
        result = self.compile(source, live)
        self.assertEqual(result["percent_capability"], "unsupported")
        self.assertEqual(result["operations"], [])

    def test_determinism(self):
        source = make_snapshot(layout="stacked", order=(1, 2, 3))
        live = make_snapshot(live=True, layout="splitv", order=(3, 2, 1))
        self.assertEqual(self.compile(source, live), self.compile(copy.deepcopy(source), copy.deepcopy(live)))

    def test_hostile_values_are_rejected(self):
        with self.assertRaisesRegex(tree.TreeRestoreError, "invalid-operation-layout"):
            tree.validate_operation({
                "operation": "set-container-layout", "workspace": "8", "source_window": "w1",
                "layout": "tabbed; exec evil",
            })
        with self.assertRaisesRegex(tree.TreeRestoreError, "invalid-operation-workspace"):
            tree.validate_operation({
                "operation": "move-relative", "workspace": "8; exec evil", "source_window": "w1",
                "relation": "after", "reference_window": "w2",
            })

    def test_runtime_tree_drift_stops_before_second_command(self):
        source = make_snapshot(layout="tabbed")
        live_before = make_snapshot(live=True, layout="splith")
        live_after_first = make_snapshot(live=True, layout="tabbed")
        live_drifted = make_snapshot(live=True, layout="tabbed", order=(2, 1, 3))
        states = iter((live_before, live_after_first, live_drifted))
        commands = []

        class Planner:
            @staticmethod
            def match_windows(saved, candidates):
                return {str(saved[0]["window_id"]): {"confidence": "exact", "live_index": 0}}, []

        compilation = {
            "operations": [
                {"operation": "set-container-layout", "workspace": "8", "source_window": "w1", "layout": "tabbed"},
                {"operation": "set-container-layout", "workspace": "8", "source_window": "w1", "layout": "stacked"},
            ]
        }
        with self.assertRaisesRegex(executor.RestoreExecutionError, "RESTORE_TREE_DRIFTED"):
            executor._execute_tree_compilation(
                source,
                make_plan(source, live_before),
                compilation,
                {"w1": 101, "w2": 102, "w3": 103},
                collector=lambda: copy.deepcopy(next(states)),
                planner_module=Planner,
                tree_module=tree,
                runner=lambda argv, _timeout: commands.append(list(argv)) or SimpleNamespace(
                    returncode=0, stdout='[{"success":true}]', stderr=""
                ),
                monotonic=lambda: 0.0,
                sleeper=lambda _delay: None,
            )
        self.assertEqual(len(commands), 1)


if __name__ == "__main__":
    unittest.main()

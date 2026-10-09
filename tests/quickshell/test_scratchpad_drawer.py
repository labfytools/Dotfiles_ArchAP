"""Contrats du modèle scratchpad Sway, sans toucher au bureau réel."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


BACKEND = (Path(__file__).resolve().parents[2] / "quickshell/.config/quickshell"
           / "labfy-sway/scratchpad/backend.py")
spec = importlib.util.spec_from_file_location("drawer_backend", BACKEND)
drawer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drawer)


def app(cid, name="Application", app_id="demo", state="none"):
    return {"id": cid, "type": "con", "name": name, "app_id": app_id,
            "scratchpad_state": state, "nodes": [], "floating_nodes": []}


def tree(*nodes):
    return {"id": 1, "type": "root", "nodes": [
        {"id": 2, "type": "output", "name": "__i3", "nodes": [
            {"id": 3, "type": "workspace", "name": "__i3_scratch",
             "nodes": [], "floating_nodes": [n for n in nodes if n.get("hidden")]}]},
        {"id": 4, "type": "output", "name": "DP-2", "nodes": [
            {"id": 5, "type": "workspace", "name": 'Travail ; "A"',
             "nodes": [], "floating_nodes": [n for n in nodes if not n.get("hidden")]}]}]}


class DrawerModelTest(unittest.TestCase):
    def test_empty_and_duplicate_app_identity(self):
        self.assertEqual(drawer.members(tree()), [])
        a, b = app(20, "Premier", state="fresh"), app(21, "Second", state="fresh")
        a["hidden"] = True
        result = drawer.members(tree(a, b))
        self.assertEqual([(x["id"], x["shown"]) for x in result], [(20, False), (21, True)])

    def test_group_is_blocked_even_when_apps_are_nested(self):
        group = {"id": 10, "type": "floating_con", "scratchpad_state": "fresh",
                 "nodes": [{"id": 11, "type": "con", "nodes": [app(20)],
                            "floating_nodes": [app(21)]}], "floating_nodes": []}
        group["hidden"] = True
        self.assertTrue(all(x["group"] for x in drawer.members(tree(group))))

    def test_workspace_quoting_and_missing_target(self):
        self.assertEqual(drawer.quoted_workspace('Travail ; "A"'), "'Travail ; \"A\"'")
        with self.assertRaises(drawer.DrawerError):
            drawer.quoted_workspace("A 'B' and \"C\"")
        with self.assertRaises(drawer.DrawerError):
            drawer.valid_app(tree(), 99)
        with patch.object(drawer, "sway", return_value=[{"name": "A", "output": "DP-2", "visible": True}]):
            with self.assertRaises(drawer.DrawerError):
                drawer.target_workspace("HDMI-A-1")

    def test_non_app_container_is_rejected(self):
        group = {"id": 30, "type": "con", "nodes": [app(31)], "floating_nodes": []}
        with self.assertRaises(drawer.DrawerError):
            drawer.valid_app(tree(group), 30)

    def test_store_rejects_multi_app_parent(self):
        group = {"id": 30, "type": "floating_con", "nodes": [app(31), app(32)],
                 "floating_nodes": []}
        with self.assertRaises(drawer.DrawerError):
            drawer.valid_app(tree(group), 31)

    def test_repeated_show_only_focuses_and_repeated_hide_sends_nothing(self):
        displayed = tree(app(20, state="fresh"))
        hidden = app(20, state="fresh")
        hidden["hidden"] = True
        hidden_tree = tree(hidden)
        workspaces = [{"name": 'Travail ; "A"', "output": "DP-2", "visible": True}]

        def answer(kind, current):
            return current if kind == "get_tree" else workspaces

        with patch.object(drawer, "sway", side_effect=lambda kind: answer(kind, displayed)), \
                patch.object(drawer, "safe_command") as sent:
            self.assertTrue(drawer.operate("show", 20, "DP-2")["shown"])
            sent.assert_called_once_with("[con_id=20] focus")
        with patch.object(drawer, "sway", side_effect=lambda kind: answer(kind, hidden_tree)), \
                patch.object(drawer, "safe_command") as sent:
            self.assertFalse(drawer.operate("hide", 20, "DP-2")["shown"])
            sent.assert_not_called()

    def test_rejected_command_does_not_report_success(self):
        with patch.object(drawer, "sway", return_value=tree(app(20))), \
                patch.object(drawer, "safe_command", side_effect=drawer.DrawerError("refusée")):
            with self.assertRaisesRegex(drawer.DrawerError, "refusée"):
                drawer.operate("store", 20, "DP-2")


if __name__ == "__main__":
    unittest.main()

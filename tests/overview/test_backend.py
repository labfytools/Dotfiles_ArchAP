import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


BACKEND = Path(__file__).resolve().parents[2] / "quickshell/.config/quickshell/labfy-sway/overview/backend.py"
spec = importlib.util.spec_from_file_location("overview_backend", BACKEND)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class OverviewBackendTests(unittest.TestCase):
    def test_lock_guard_blocks_all_capture_entrypoints(self):
        # CONTRACT: no compositor read or grim call follows an active lock
        # guard, including the window-preview path.
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}):
            (Path(directory) / "labfy-lock.capture-guard").write_text("active\n")
            with patch.object(backend, "state", side_effect=AssertionError("capture reached state")):
                self.assertEqual(backend.capture("HEADLESS-1"), {"captured": False})
                self.assertEqual(backend.capture_windows({1}), {"captured": [], "nextCursor": 0})

    def test_state_keeps_floating_and_excludes_layer_shell(self):
        rect = {"x": 0, "y": 0, "width": 1000, "height": 700}
        tiled = {"type": "con", "id": 10, "app_id": "native-app", "name": "Native",
                 "foreign_toplevel_identifier": "a" * 32,
                 "rect": rect, "nodes": [], "floating_nodes": []}
        floating = {"type": "floating_con", "id": 11, "app_id": "xwayland-app",
                    "window_properties": {"class": "xwayland-app"}, "name": "Floating",
                    "rect": rect, "floating": "user_on", "nodes": [], "floating_nodes": []}
        workspace = {"type": "workspace", "id": 4, "name": "1: travail", "rect": rect,
                     "layout": "splith", "nodes": [tiled], "floating_nodes": [floating]}
        output = {"type": "output", "id": 3, "name": "eDP-1", "nodes": [workspace],
                  "floating_nodes": []}
        tree = {"type": "root", "nodes": [output], "floating_nodes": []}
        ws = [{"id": 4, "name": "1: travail", "num": 1, "output": "eDP-1",
               "visible": True, "focused": True}]
        outputs = [{"name": "eDP-1", "active": True, "focused": True, "rect": rect,
                    "layer_shell_surfaces": [{"namespace": "labfy-sway-bar"}]}]
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}):
            with patch.object(backend, "sway", side_effect=lambda kind: {
                "get_tree": tree, "get_workspaces": ws, "get_outputs": outputs}[kind]):
                result = backend.state()
        self.assertEqual(len(result["cards"]), 10)
        self.assertEqual([window["id"] for window in result["cards"][0]["windows"]], [10, 11])
        self.assertTrue(result["cards"][0]["windows"][1]["floating"])
        self.assertEqual(result["cards"][0]["windows"][0]["foreignId"], "a" * 32)
        self.assertFalse(result["cards"][1]["exists"])
        outputs[0]["layer_shell_surfaces"].append({"namespace": "labfy-applications-menu"})
        with patch.object(backend, "sway", side_effect=lambda kind: {
                "get_tree": tree, "get_workspaces": ws, "get_outputs": outputs}[kind]):
            self.assertEqual(backend.state()["overlayOutputs"], ["eDP-1"])

    def test_move_uses_only_valid_con_id_and_workspace(self):
        cards = [{"number": 1, "revision": "before", "windows": [{"id": 42}]},
                 {"number": 4, "revision": "destination", "windows": []}]
        moved = [{"number": 1, "revision": "after", "windows": []},
                 {"number": 4, "revision": "after-destination", "windows": [{"id": 42}]}]
        fake = subprocess.CompletedProcess([], 0, '[{"success":true}]', "")
        with patch.object(backend, "state", side_effect=[{"cards": cards}, {"cards": moved},
                                                        {"cards": cards}, {"cards": cards}]), \
                patch.object(backend.subprocess, "run", return_value=fake) as run:
            result = backend.command("move", 4, 42)
            self.assertTrue(result["ok"])
            self.assertEqual((result["source"], result["destination"], result["changedWorkspaces"]),
                             (1, 4, [1, 4]))
            self.assertEqual(run.call_args.args[0], ["swaymsg", "-r", "[con_id=42]",
                                                     "move", "container", "to", "workspace", "number", "4"])
            with self.assertRaises(ValueError):
                backend.command("move", 11, 42)
            with self.assertRaises(ValueError):
                backend.command("move", 4, 43)
            self.assertEqual(run.call_count, 1)

    def test_revision_changes_for_layout_geometry_and_move_but_not_title_or_focus(self):
        rect = {"x": 0, "y": 0, "width": 1000, "height": 700}
        window = {"type": "con", "id": 42, "app_id": "test", "name": "Original",
                  "focused": False, "rect": dict(rect), "nodes": [], "floating_nodes": []}
        workspace = {"type": "workspace", "id": 4, "num": 1, "output": "eDP-1",
                     "layout": "splith", "rect": rect, "nodes": [window], "floating_nodes": []}
        first = backend.structure_revision(workspace, workspace, rect)
        window["name"] = "Nouveau titre"
        window["focused"] = True
        self.assertEqual(first, backend.structure_revision(workspace, workspace, rect))
        workspace["layout"] = "tabbed"
        self.assertNotEqual(first, backend.structure_revision(workspace, workspace, rect))
        workspace["layout"] = "splith"
        window["rect"] = {**rect, "width": 500}
        self.assertNotEqual(first, backend.structure_revision(workspace, workspace, rect))
        window["rect"] = rect
        workspace["nodes"] = []
        self.assertNotEqual(first, backend.structure_revision(workspace, workspace, rect))

    def test_changed_workspace_rejects_old_snapshot_and_empty_workspace_removes_it(self):
        rect = {"x": 0, "y": 0, "width": 1000, "height": 700}
        window = {"type": "con", "id": 42, "app_id": "test", "name": "Test",
                  "rect": dict(rect), "nodes": [], "floating_nodes": []}
        workspace = {"type": "workspace", "id": 4, "num": 1, "output": "eDP-1",
                     "layout": "splith", "rect": rect, "nodes": [window], "floating_nodes": []}
        tree = {"type": "root", "nodes": [{"type": "output", "nodes": [workspace]}]}
        workspaces = [{"id": 4, "num": 1, "output": "eDP-1", "visible": True, "focused": True}]
        outputs = [{"name": "eDP-1", "active": True, "focused": True, "rect": rect}]
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                patch.object(backend, "sway", side_effect=lambda kind: {
                    "get_tree": tree, "get_workspaces": workspaces, "get_outputs": outputs}[kind]):
            path = backend.snapshot_path("eDP-1", 1)
            path.write_bytes(b"JPEG")
            original = backend.structure_revision(workspace, workspaces[0], rect)
            backend.snapshot_metadata_path("eDP-1", 1).write_text(json.dumps({
                "version": 1, "output": "eDP-1", "number": 1, "workspaceId": 4,
                "revision": original, "capturedNs": 123, "imageMtimeNs": path.stat().st_mtime_ns}))
            self.assertNotEqual(backend.state()["cards"][0]["snapshot"], "")
            window["name"] = "Titre changé"
            self.assertNotEqual(backend.state()["cards"][0]["snapshot"], "")
            window["rect"] = {**rect, "width": 500}
            changed = backend.state()["cards"][0]
            self.assertEqual(changed["snapshot"], "")
            self.assertEqual([item["id"] for item in changed["windows"]], [42])
            workspace["nodes"] = []
            empty = backend.state()["cards"][0]
            self.assertEqual(empty["snapshot"], "")
            self.assertEqual(empty["windows"], [])
            self.assertFalse(path.exists())
            self.assertFalse(backend.snapshot_metadata_path("eDP-1", 1).exists())

    def test_capture_rejects_overlay_and_mid_capture_change(self):
        card = {"number": 1, "workspaceId": 4, "revision": "first", "visible": True,
                "output": "eDP-1", "windows": [{"id": 42}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}):
            with patch.object(backend, "state", return_value={
                    "cards": [card], "overlayOutputs": ["eDP-1"]}):
                self.assertFalse(backend.capture("eDP-1")["captured"])

            def fake_grim(args, **_kwargs):
                Path(args[-1]).write_bytes(b"JPEG")
                return subprocess.CompletedProcess(args, 0, "", "")

            changed = {**card, "revision": "second"}
            with patch.object(backend, "state", side_effect=[
                    {"cards": [card], "overlayOutputs": []},
                    {"cards": [changed], "overlayOutputs": []}]), \
                    patch.object(backend.subprocess, "run", side_effect=fake_grim):
                self.assertFalse(backend.capture("eDP-1")["captured"])
            self.assertFalse(backend.snapshot_path("eDP-1", 1).exists())

    def test_capture_publishes_metadata_only_for_stable_visible_workspace(self):
        card = {"number": 7, "workspaceId": 164, "revision": "stable", "visible": True,
                "output": "eDP-1", "windows": [{"id": 42}]}

        def fake_grim(args, **_kwargs):
            Path(args[-1]).write_bytes(b"JPEG")
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                patch.object(backend, "state", return_value={"cards": [card], "overlayOutputs": []}), \
                patch.object(backend.subprocess, "run", side_effect=fake_grim):
            result = backend.capture("eDP-1", expected_number=7, expected_workspace_id=164)
            self.assertTrue(result["captured"])
            self.assertIsNotNone(backend.valid_snapshot("eDP-1", 7, 164, "stable"))
            self.assertIsNone(backend.valid_snapshot("eDP-1", 7, 164, "changed"))
            self.assertIsNone(backend.valid_snapshot("eDP-1", 7, 999, "stable"))
            self.assertFalse(backend.capture("eDP-1", expected_number=8)["captured"])
            self.assertFalse(backend.capture("eDP-1", expected_revision="changed")["captured"])

    def test_removed_workspace_cleans_only_its_cache_entries(self):
        tree = {"type": "root", "nodes": [], "floating_nodes": []}
        outputs = [{"name": "eDP-1", "active": True, "focused": True}]
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                patch.object(backend, "sway", side_effect=lambda kind: {
                    "get_tree": tree, "get_workspaces": [], "get_outputs": outputs}[kind]):
            obsolete = backend.snapshot_path("eDP-1", 8)
            retained = backend.cache_dir() / "unrelated.txt"
            obsolete.write_bytes(b"old")
            retained.write_bytes(b"other")
            backend.state()
            self.assertFalse(obsolete.exists())
            self.assertTrue(retained.exists())

    def test_window_preview_survives_workspace_move_but_not_window_close(self):
        rect = {"x": 0, "y": 0, "width": 1000, "height": 700}
        window = {"type": "con", "id": 42, "app_id": "test", "name": "Test",
                  "foreign_toplevel_identifier": "a" * 32,
                  "rect": rect, "nodes": [], "floating_nodes": []}
        source = {"type": "workspace", "id": 4, "num": 7, "output": "eDP-1",
                  "layout": "splith", "rect": rect, "nodes": [window], "floating_nodes": []}
        destination = {"type": "workspace", "id": 5, "num": 8, "output": "eDP-1",
                       "layout": "splith", "rect": rect, "nodes": [], "floating_nodes": []}
        tree = {"type": "root", "nodes": [source, destination]}
        workspaces = [{"id": 4, "num": 7, "output": "eDP-1", "visible": True, "focused": True},
                      {"id": 5, "num": 8, "output": "eDP-1", "visible": False, "focused": False}]
        outputs = [{"name": "eDP-1", "active": True, "focused": True, "rect": rect}]
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                patch.object(backend, "sway", side_effect=lambda kind: {
                    "get_tree": tree, "get_workspaces": workspaces, "get_outputs": outputs}[kind]):
            path = backend.window_preview_path(42)
            path.write_bytes(b"JPEG")
            backend.window_preview_metadata_path(42).write_text(json.dumps({
                "version": 1, "conId": 42, "foreignId": "a" * 32,
                "capturedNs": 123, "imageMtimeNs": path.stat().st_mtime_ns}))
            before = backend.state()["cards"]
            self.assertNotEqual(before[6]["windows"][0]["preview"], "")
            source["nodes"] = []
            destination["nodes"] = [window]
            moved = backend.state()["cards"]
            self.assertEqual(moved[6]["windows"], [])
            self.assertEqual(moved[7]["windows"][0]["preview"], path.as_uri())
            destination["nodes"] = []
            backend.state()
            self.assertFalse(path.exists())

    def test_individual_capture_uses_foreign_id_and_checks_window_lifetime(self):
        foreign_id = "b" * 32
        window = {"id": 42, "foreignId": foreign_id, "preview": ""}
        before = {"cards": [{"number": 7, "windows": [window]}]}
        closed = {"cards": [{"number": 7, "windows": []}]}

        def fake_grim(args, **_kwargs):
            Path(args[-1]).write_bytes(b"JPEG")
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                patch.object(backend.subprocess, "run", side_effect=fake_grim) as run:
            with patch.object(backend, "state", side_effect=[before, before]):
                result = backend.capture_windows({7})
            self.assertEqual(result["captured"], [42])
            self.assertEqual(run.call_args.args[0][0:3], ["grim", "-T", foreign_id])
            self.assertIsNotNone(backend.valid_window_preview(42, foreign_id))
            self.assertIsNone(backend.valid_window_preview(42, "c" * 32))
            with patch.object(backend, "state", side_effect=[before, closed]):
                result = backend.capture_windows({7})
            self.assertEqual(result["captured"], [])

    def test_individual_captures_are_batched(self):
        windows = [{"id": ident, "foreignId": f"{ident:032x}", "preview": ""}
                   for ident in range(1, 18)]
        cards = {"cards": [{"number": 7, "windows": windows}]}

        def fake_grim(args, **_kwargs):
            Path(args[-1]).write_bytes(b"JPEG")
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                patch.object(backend, "state", return_value=cards), \
                patch.object(backend.subprocess, "run", side_effect=fake_grim) as run:
            first = backend.capture_windows({7})
            self.assertEqual(first["captured"], list(range(1, 17)))
            self.assertEqual(first["nextCursor"], 16)
            second = backend.capture_windows({7}, cursor=first["nextCursor"])
            self.assertEqual(second["captured"], [17])
            self.assertEqual(second["nextCursor"], 0)
            self.assertEqual(run.call_count, 17)


if __name__ == "__main__":
    unittest.main()

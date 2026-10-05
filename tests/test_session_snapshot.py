"""Contrat Session Snapshot V1 sur arbres Sway synthétiques."""

import copy
import concurrent.futures
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "quickshell/.config/quickshell/labfy-sway/session/session_snapshot.py"
)
SPEC = importlib.util.spec_from_file_location("session_snapshot", SOURCE)
snapshot_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot_module)


def leaf(
    con_id,
    app_id,
    *,
    focused=False,
    floating="auto_off",
    fullscreen=0,
    properties=None,
    scratchpad_state="none",
):
    return {
        "id": con_id,
        "type": "con",
        "name": f"titre {con_id}",
        "app_id": app_id,
        "window": con_id if properties else None,
        "window_properties": properties,
        "pid": 90000 + con_id,
        "nodes": [],
        "floating_nodes": [],
        "layout": "none",
        "orientation": "none",
        "percent": 0.5,
        "rect": {"x": con_id, "y": 2, "width": 300, "height": 200},
        "focused": focused,
        "urgent": False,
        "marks": [f"mark-{con_id}"],
        "floating": floating,
        "fullscreen_mode": fullscreen,
        "scratchpad_state": scratchpad_state,
    }


def container(con_id, layout, children, floating_nodes=None):
    return {
        "id": con_id,
        "type": "con",
        "name": None,
        "nodes": children,
        "floating_nodes": floating_nodes or [],
        "layout": layout,
        "orientation": "horizontal" if layout in {"splith", "tabbed"} else "vertical",
        "percent": 1.0,
        "rect": {"x": 0, "y": 0, "width": 1200, "height": 800},
        "focused": False,
        "urgent": False,
        "marks": [],
    }


def fixture():
    firefox_one = leaf(11, "firefox")
    firefox_two = leaf(12, "firefox", fullscreen=1)
    kitty = leaf(13, "kitty", focused=True)
    xwayland = leaf(14, None, properties={"class": "LegacyApp", "instance": "legacy"})
    unknown = leaf(15, "not-catalogued")
    floating = leaf(16, "float-app", floating="user_on")
    tabbed = container(21, "tabbed", [firefox_one, firefox_two])
    stacked = container(22, "stacked", [kitty, xwayland])
    splitv = container(23, "splitv", [tabbed, stacked])
    splith = container(24, "splith", [splitv, unknown], [floating])
    workspace = {
        "id": 4,
        "type": "workspace",
        "name": "dev",
        "nodes": [splith],
        "floating_nodes": [],
        "layout": "splith",
        "orientation": "horizontal",
    }
    scratch = leaf(30, "scratch-app", floating="user_on", scratchpad_state="changed")
    tree = {
        "id": 1,
        "type": "root",
        "nodes": [
            {
                "id": 2,
                "type": "output",
                "name": "__i3",
                "nodes": [{"id": 3, "type": "workspace", "name": "__i3_scratch", "nodes": [], "floating_nodes": [scratch]}],
                "floating_nodes": [],
            },
            {"id": 5, "type": "output", "name": "DP-1", "nodes": [workspace], "floating_nodes": []},
        ],
    }
    outputs = [{
        "name": "DP-1",
        "active": True,
        "focused": True,
        "rect": {"x": 0, "y": 0, "width": 1200, "height": 800},
        "scale": 1.25,
        "transform": "normal",
        "current_mode": {"width": 1920, "height": 1080, "refresh": 60000},
    }]
    workspaces = [{
        "name": "dev",
        "num": -1,
        "output": "DP-1",
        "focused": True,
        "visible": True,
        "urgent": False,
        "rect": {"x": 0, "y": 0, "width": 1200, "height": 800},
        "layout": "splith",
        "orientation": "horizontal",
    }]
    version = {"variant": "sway", "human_readable": "0.6", "sway_original_version": "1.12.0"}
    entries = [
        {"desktop_entry": "firefox.desktop", "stem": "firefox", "startup_wm_class": "firefox", "name": "Firefox"},
        {"desktop_entry": "kitty.desktop", "stem": "kitty", "startup_wm_class": "kitty", "name": "Kitty"},
        {"desktop_entry": "legacy.desktop", "stem": "legacy-desktop", "startup_wm_class": "LegacyApp", "name": "Legacy"},
    ]
    return version, outputs, workspaces, tree, entries


class SessionSnapshotTest(unittest.TestCase):
    def build(self):
        version, outputs, workspaces, tree, entries = fixture()
        with mock.patch.object(snapshot_module, "_basename_from_pid", return_value=None):
            return snapshot_module.build_snapshot(
                version,
                outputs,
                workspaces,
                tree,
                captured_at="2026-01-01T00:00:00.000Z",
                environment={"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "sway"},
                desktop_entries=entries,
                managed_autostart={"float-app"},
            )

    def test_layout_tree_order_and_simple_workspace(self):
        snapshot = self.build()
        self.assertEqual(snapshot["workspaces"][0]["name"], "dev")
        self.assertEqual(snapshot["workspaces"][0]["roots"]["tiling"], [{"kind": "container", "id": "c1"}])
        layouts = {item["layout"] for item in snapshot["containers"]}
        self.assertTrue({"splith", "splitv", "tabbed", "stacked"}.issubset(layouts))
        top = snapshot["containers"][0]
        self.assertEqual([ref["kind"] for ref in top["children"]], ["container", "window"])

    def test_simple_direct_window_and_empty_workspace(self):
        version, outputs, workspaces, tree, entries = fixture()
        direct = leaf(40, "firefox")
        real_output = tree["nodes"][1]
        real_output["nodes"][0]["nodes"] = [direct]
        empty = {
            "id": 41, "type": "workspace", "name": "2", "nodes": [],
            "floating_nodes": [], "layout": "splith", "orientation": "horizontal",
        }
        real_output["nodes"].append(empty)
        workspaces.append({
            "name": "2", "num": 2, "output": "DP-1", "focused": False,
            "visible": False, "urgent": False,
            "rect": {"x": 0, "y": 0, "width": 1200, "height": 800},
            "layout": "splith", "orientation": "horizontal",
        })
        with mock.patch.object(snapshot_module, "_basename_from_pid", return_value=None):
            snapshot = snapshot_module.build_snapshot(version, outputs, workspaces, tree, desktop_entries=entries)
        self.assertEqual(snapshot["workspaces"][0]["roots"]["tiling"][0]["kind"], "window")
        self.assertEqual(snapshot["workspaces"][1]["roots"], {"tiling": [], "floating": []})

    def test_floating_fullscreen_focus_and_marks(self):
        snapshot = self.build()
        floating = next(window for window in snapshot["windows"] if window["app_id"] == "float-app")
        fullscreen = next(window for window in snapshot["windows"] if window["runtime"]["con_id"] == 12)
        kitty = next(window for window in snapshot["windows"] if window["app_id"] == "kitty")
        self.assertTrue(floating["floating"])
        self.assertEqual(floating["classification"]["managed_by"], "sway-autostart")
        self.assertEqual(fullscreen["fullscreen_mode"], 1)
        self.assertEqual(snapshot["focus"]["window_id"], kitty["window_id"])
        self.assertEqual(kitty["marks"], ["mark-13"])

    def test_duplicate_app_ids_keep_distinct_snapshot_ordinals(self):
        windows = [window for window in self.build()["windows"] if window["app_id"] == "firefox"]
        self.assertEqual([window["snapshot_identity"] for window in windows], ["firefox#1", "firefox#2"])
        self.assertNotEqual(windows[0]["window_id"], windows[1]["window_id"])

    def test_desktop_identity_exact_xwayland_and_unresolved(self):
        snapshot = self.build()
        firefox = next(window for window in snapshot["windows"] if window["app_id"] == "firefox")
        legacy = next(window for window in snapshot["windows"] if window["xwayland"]["class"] == "LegacyApp")
        unknown = next(window for window in snapshot["windows"] if window["app_id"] == "not-catalogued")
        self.assertEqual(firefox["restore_identity"]["desktop_entry"], "firefox.desktop")
        self.assertEqual(legacy["restore_identity"]["matched_by"], "StartupWMClass")
        self.assertEqual(legacy["restore_identity"]["confidence"], "exact")
        self.assertEqual(unknown["restore_identity"]["confidence"], "unresolved")

    def test_hidden_scratchpad_is_not_a_user_workspace(self):
        snapshot = self.build()
        scratch = next(window for window in snapshot["windows"] if window["app_id"] == "scratch-app")
        self.assertIsNone(scratch["workspace"])
        self.assertTrue(scratch["scratchpad"]["member"])
        self.assertEqual(scratch["scratchpad"]["visibility"], "hidden")
        self.assertEqual(snapshot["restore_hints"]["scratchpad_roots"], [{"kind": "window", "id": scratch["window_id"]}])

    def test_visible_scratchpad_member_stays_on_real_workspace(self):
        version, outputs, workspaces, tree, entries = fixture()
        visible = leaf(42, "scratch-visible", scratchpad_state="fresh")
        tree["nodes"][1]["nodes"][0]["floating_nodes"] = [visible]
        with mock.patch.object(snapshot_module, "_basename_from_pid", return_value=None):
            snapshot = snapshot_module.build_snapshot(version, outputs, workspaces, tree, desktop_entries=entries)
        window = next(item for item in snapshot["windows"] if item["app_id"] == "scratch-visible")
        self.assertEqual(window["workspace"], "dev")
        self.assertEqual(window["scratchpad"]["visibility"], "visible")

    def test_unique_executable_basename_is_only_heuristic(self):
        entries = [{"desktop_entry": "odd-name.desktop", "stem": "tool", "startup_wm_class": None, "name": "Tool"}]
        identity = snapshot_module.resolve_desktop_entry("unrelated", {}, "tool", entries)
        self.assertEqual(identity, {
            "desktop_entry": "odd-name.desktop",
            "confidence": "heuristic",
            "matched_by": "executable-basename",
        })

    def test_title_and_timestamp_do_not_affect_structural_projection(self):
        first = self.build()
        second = copy.deepcopy(first)
        second["metadata"]["captured_at"] = "2027-02-02T00:00:00Z"
        second["windows"][0]["title_hint"] = "titre dynamique différent"
        self.assertEqual(
            snapshot_module.structural_projection(first),
            snapshot_module.structural_projection(second),
        )

    def test_validator_rejects_broken_tree_relation(self):
        snapshot = self.build()
        snapshot["workspaces"][0]["roots"]["tiling"][0]["id"] = "absent"
        with self.assertRaises(snapshot_module.SnapshotError):
            snapshot_module.validate_snapshot(snapshot)

    def test_validator_rejects_duplicate_reference(self):
        snapshot = self.build()
        root = snapshot["workspaces"][0]["roots"]["tiling"][0]
        snapshot["workspaces"][0]["roots"]["tiling"].append(copy.deepcopy(root))
        with self.assertRaises(snapshot_module.SnapshotError):
            snapshot_module.validate_snapshot(snapshot)

    def test_autostart_parser_excludes_shell_wrappers_and_keeps_direct_apps(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "autostart"
            path.write_text(
                "exec limusic-app\n"
                "exec python3 ~/.config/sway/scripts/inactive-windows-transparency.py\n"
                "exec sh -c 'private command'\n",
                encoding="utf-8",
            )
            self.assertEqual(
                snapshot_module.parse_sway_autostart(path),
                {"limusic-app", "inactive-windows-transparency.py"},
            )

    def test_no_command_line_or_environment_field_exists(self):
        serialized_keys = repr(self.build()).casefold()
        self.assertNotIn("cmdline", serialized_keys)
        self.assertNotIn("command_line", serialized_keys)
        self.assertNotIn("/proc/", serialized_keys)
        self.assertNotIn("environment", serialized_keys)


class PersistentSessionTest(unittest.TestCase):
    """Contrats STEP18B dans un XDG state isolé du compte utilisateur."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.environment = {"XDG_STATE_HOME": str(self.state)}
        version, outputs, workspaces, tree, entries = fixture()
        with mock.patch.object(snapshot_module, "_basename_from_pid", return_value=None):
            self.snapshot = snapshot_module.build_snapshot(
                version,
                outputs,
                workspaces,
                tree,
                captured_at="2026-01-01T00:00:00.000Z",
                environment={"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "sway"},
                desktop_entries=entries,
                managed_autostart={"float-app"},
            )

    def collector(self, _autostart):
        return copy.deepcopy(self.snapshot)

    def save(self, name="dev", **kwargs):
        return snapshot_module.save_session(
            name,
            environment=self.environment,
            collector=self.collector,
            retry_delay=0,
            **kwargs,
        )

    @property
    def sessions(self):
        return self.state / "labfy-sway/sessions"

    def write_raw(self, name, value=None, payload=None):
        snapshot_module.sessions_directory(self.environment)
        path = self.sessions / f"{name}.json"
        if payload is None:
            payload = json.dumps(value).encode("utf-8")
        path.write_bytes(payload)
        path.chmod(0o600)
        return path

    def test_xdg_path_fallback_and_private_directory_permissions(self):
        path = snapshot_module.sessions_directory(self.environment)
        self.assertEqual(path, self.sessions)
        self.assertEqual(stat.S_IMODE((self.state / "labfy-sway").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        fallback = snapshot_module.sessions_directory({}, self.root / "home")
        self.assertEqual(fallback, self.root / "home/.local/state/labfy-sway/sessions")
        with self.assertRaises(snapshot_module.SnapshotError):
            snapshot_module.sessions_directory({"XDG_STATE_HOME": "relative"}, self.root)

    def test_safe_and_invalid_names_prevent_path_traversal(self):
        for name in ("default", "Dev_01", "osint-prod", "A" * 64):
            self.assertEqual(snapshot_module.normalize_session_name(name), name)
        for name in ("", "..", ".", "a/b", "../dev", "a b", "é", "A" * 65, "nul\0name"):
            with self.subTest(name=repr(name)):
                with self.assertRaises(snapshot_module.SnapshotError):
                    snapshot_module.normalize_session_name(name)

    def test_atomic_first_save_permissions_and_persistent_metadata(self):
        previous_umask = os.umask(0)
        try:
            saved = self.save()
        finally:
            os.umask(previous_umask)
        path = self.sessions / "dev.json"
        self.assertTrue(path.is_file())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.sessions.stat().st_mode), 0o700)
        self.assertEqual(saved["schema"], snapshot_module.SCHEMA)
        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["metadata"]["session_name"], "dev")
        self.assertEqual(saved["metadata"]["created_at"], saved["metadata"]["updated_at"])
        self.assertFalse(list(self.sessions.glob("*.tmp")))

    def test_atomic_update_preserves_created_at_and_advances_updated_at(self):
        first = self.save()
        first_bytes = (self.sessions / "dev.json").read_bytes()
        self.snapshot["metadata"]["captured_at"] = "2026-01-01T00:00:01.000Z"
        second = self.save()
        self.assertEqual(second["metadata"]["created_at"], first["metadata"]["created_at"])
        self.assertGreater(second["metadata"]["updated_at"], first["metadata"]["updated_at"])
        self.assertNotEqual(second["metadata"]["captured_at"], first["metadata"]["captured_at"])
        self.assertNotEqual((self.sessions / "dev.json").read_bytes(), first_bytes)
        self.assertEqual([path.name for path in self.sessions.glob("*.json")], ["dev.json"])

    def test_list_show_delete_round_trip(self):
        saved = self.save("trainlog")
        listed, warnings = snapshot_module.list_sessions(environment=self.environment)
        self.assertEqual(warnings, [])
        self.assertEqual(listed, [{
            "name": "trainlog",
            "updated_at": saved["metadata"]["updated_at"],
            "windows": 7,
            "workspaces": 1,
        }])
        shown = snapshot_module.show_session("trainlog", environment=self.environment)
        self.assertEqual(shown, saved)
        snapshot_module.delete_session("trainlog", environment=self.environment)
        self.assertFalse((self.sessions / "trainlog.json").exists())
        self.assertTrue(self.sessions.is_dir())
        with self.assertRaises(snapshot_module.SnapshotError):
            snapshot_module.show_session("trainlog", environment=self.environment)

    def test_corrupt_invalid_relation_and_unknown_files_are_ignored_by_list(self):
        self.save("valid")
        self.write_raw("truncated", payload=b'{"schema":')
        invalid_relation = copy.deepcopy(snapshot_module.show_session("valid", environment=self.environment))
        invalid_relation["workspaces"][0]["roots"]["tiling"][0]["id"] = "absent"
        self.write_raw("relation", invalid_relation)
        unknown_schema = copy.deepcopy(invalid_relation)
        unknown_schema["schema"] = "unknown"
        self.write_raw("schema", unknown_schema)
        listed, warnings = snapshot_module.list_sessions(environment=self.environment)
        self.assertEqual([item["name"] for item in listed], ["valid"])
        self.assertEqual(len(warnings), 3)
        for name in ("truncated", "relation", "schema"):
            with self.assertRaises(snapshot_module.SnapshotError):
                snapshot_module.show_session(name, environment=self.environment)

    def test_unknown_version_has_explicit_error(self):
        snapshot = self.save("future")
        snapshot["version"] = 99
        self.write_raw("future", snapshot)
        with self.assertRaisesRegex(snapshot_module.SnapshotError, "unsupported snapshot version"):
            snapshot_module.show_session("future", environment=self.environment)

    def test_oversized_snapshot_is_rejected_before_json_loading(self):
        self.write_raw("huge", payload=b"{" + b" " * snapshot_module.MAX_SNAPSHOT_BYTES)
        with self.assertRaisesRegex(snapshot_module.SnapshotError, "trop volumineux"):
            snapshot_module.show_session("huge", environment=self.environment)

    def test_explicit_save_repairs_corrupt_regular_target(self):
        self.write_raw("repair", payload=b"not-json")
        saved = self.save("repair")
        self.assertEqual(snapshot_module.show_session("repair", environment=self.environment), saved)

    def test_symlink_target_is_refused_for_save_show_and_delete(self):
        snapshot_module.sessions_directory(self.environment)
        external = self.root / "external"
        external.write_text("do not touch", encoding="utf-8")
        (self.sessions / "evil.json").symlink_to(external)
        with self.assertRaisesRegex(snapshot_module.SnapshotError, "lien symbolique"):
            self.save("evil")
        with self.assertRaises(snapshot_module.SnapshotError):
            snapshot_module.show_session("evil", environment=self.environment)
        with self.assertRaisesRegex(snapshot_module.SnapshotError, "lien symbolique"):
            snapshot_module.delete_session("evil", environment=self.environment)
        self.assertEqual(external.read_text(encoding="utf-8"), "do not touch")

    def test_managed_directory_symlink_is_refused(self):
        self.state.mkdir()
        external = self.root / "outside"
        external.mkdir()
        (self.state / "labfy-sway").symlink_to(external, target_is_directory=True)
        with self.assertRaises(snapshot_module.SnapshotError):
            snapshot_module.sessions_directory(self.environment)

    def test_interrupted_update_keeps_old_snapshot_and_cleans_temporary(self):
        self.save()
        path = self.sessions / "dev.json"
        before = path.read_bytes()

        def interrupt(_temporary):
            raise snapshot_module.SnapshotError("interruption simulée avant rename")

        with self.assertRaisesRegex(snapshot_module.SnapshotError, "interruption simulée"):
            self.save(before_replace=interrupt)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(snapshot_module.show_session("dev", environment=self.environment)["schema"], snapshot_module.SCHEMA)
        self.assertFalse(list(self.sessions.glob("*.tmp")))

    def test_concurrent_saves_are_serialized_and_valid(self):
        def operation(_index):
            return self.save()["metadata"]["updated_at"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            timestamps = list(executor.map(operation, range(12)))
        shown = snapshot_module.show_session("dev", environment=self.environment)
        self.assertEqual(shown["metadata"]["created_at"], min(timestamps))
        self.assertEqual(shown["metadata"]["updated_at"], max(timestamps))
        self.assertFalse(list(self.sessions.glob("*.tmp")))

    def test_retry_inconsistent_ipc_then_success(self):
        calls = 0

        def flaky(_autostart):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise snapshot_module.SnapshotError("snapshot V1 invalide: relation IPC")
            return self.collector(None)

        saved = snapshot_module.save_session(
            "retry",
            environment=self.environment,
            collector=flaky,
            retry_delay=0,
        )
        self.assertEqual(calls, 3)
        self.assertEqual(saved["metadata"]["session_name"], "retry")

    def test_retry_exhaustion_keeps_previous_snapshot(self):
        self.save("stable")
        path = self.sessions / "stable.json"
        before = path.read_bytes()
        calls = 0

        def inconsistent(_autostart):
            nonlocal calls
            calls += 1
            raise snapshot_module.SnapshotError("snapshot V1 invalide: relation IPC")

        with self.assertRaisesRegex(snapshot_module.SnapshotError, "SAVE_FAILED_INCONSISTENT_STATE"):
            snapshot_module.save_session(
                "stable",
                environment=self.environment,
                collector=inconsistent,
                retry_delay=0,
            )
        self.assertEqual(calls, 3)
        self.assertEqual(path.read_bytes(), before)

    def test_structural_equivalence_excludes_persistence_timestamps_and_titles(self):
        first = self.save()
        second = copy.deepcopy(first)
        second["metadata"]["created_at"] = "2030-01-01T00:00:00.000Z"
        second["metadata"]["updated_at"] = "2030-01-01T00:00:01.000Z"
        second["metadata"]["captured_at"] = "2030-01-01T00:00:02.000Z"
        second["windows"][0]["title_hint"] = "volatile"
        self.assertEqual(
            snapshot_module.structural_projection(first),
            snapshot_module.structural_projection(second),
        )

    def test_cli_save_list_show_delete(self):
        outputs = []
        with mock.patch.dict(os.environ, self.environment, clear=False), mock.patch.object(
            snapshot_module, "collect", side_effect=lambda _path: self.collector(None)
        ):
            for arguments in (("save", "cli"), ("list",), ("show", "cli"), ("delete", "cli")):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                    self.assertEqual(snapshot_module.main(arguments), 0)
                self.assertEqual(stderr.getvalue(), "")
                outputs.append(json.loads(stdout.getvalue()))
        self.assertEqual(outputs[0]["name"], "cli")
        self.assertEqual(outputs[1][0]["name"], "cli")
        self.assertEqual(outputs[2]["metadata"]["session_name"], "cli")
        self.assertEqual(outputs[3], {"deleted": "cli"})
        self.assertFalse((self.sessions / "cli.json").exists())


if __name__ == "__main__":
    unittest.main()

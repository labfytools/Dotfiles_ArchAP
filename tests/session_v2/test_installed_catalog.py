"""Installed desktop discovery: inert trees/files, no real applications launched."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from common import BACKEND, Catalog, Spec
from test_xwayland import Sway
from session_v2.applications import DEFAULT, installed_specs, launch, launch_count, _gio
from session_v2.checkpoint import Store
from session_v2.errors import Failure, Deferred
from session_v2.executor import Executor
from session_v2.ipc import workspace, X11_CLASS_PREFIX
from session_v2.recovery import JOURNAL
from session_v2.schema import validate
from session_v2.snapshot import capture


class DesktopCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.Gio, self.GioUnix, self.GLib = _gio()

    def desktop(self, identifier="org.test.Editor.desktop", extra="", executable="/usr/bin/true"):
        path = self.root / identifier
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Desktop Entry]\nType=Application\nName=TEST_ONLY\nExec=" + executable + "\n" + extra)
        path.chmod(0o600)
        app = self.GioUnix.DesktopAppInfo.new_from_filename(str(path))
        self.assertIsNotNone(app)
        return app

    def catalog(self, *apps):
        return Catalog(desktop_apps=apps)

    def test_explicit_catalog_is_hermetic(self):
        with patch("session_v2.applications.installed_specs") as discovery:
            self.assertEqual(Catalog(()).specs, {})
            self.assertEqual(Catalog(DEFAULT).specs["firefox"].provider, "firefox-session-window-uuid")
            discovery.assert_not_called()

    def test_exact_desktop_and_declared_class_with_no_title_matching(self):
        app = self.desktop(extra="StartupWMClass=TestEditor\n")
        catalog = self.catalog(app)
        spec = catalog.classify({"app_id": "org.test.Editor"})
        self.assertEqual(spec.application_id, "org.test.Editor.desktop")
        self.assertEqual(spec.strategy, "application-self-restore")
        self.assertEqual(catalog.classify({"app_id": "TestEditor"}), spec)
        self.assertEqual(catalog.classify({"app_id": None, "window": 12,
                                         "window_properties": {"class": "TestEditor"}}), spec)
        for identity in ("testeditor", "org.test.Unregistered"):
            with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
                catalog.classify({"app_id": identity, "name": "TestEditor"})
        with self.assertRaisesRegex(Failure, "SURFACE_IDENTITY_RESERVED"):
            catalog.classify({"app_id": "x11-class:TestEditor"})

    def test_menu_visibility_does_not_disable_installed_window_support(self):
        hidden = self.desktop("hidden.desktop", "Hidden=true\n")
        helper = self.desktop("helper.desktop", "NoDisplay=true\n")
        terminal = self.desktop("terminal.desktop", "Terminal=true\n")
        other = self.desktop("other.desktop", "OnlyShowIn=TEST_ONLY_UNKNOWN_DESKTOP;\n")
        future_webapp = self.desktop("firefox.webapp-new.desktop")
        # GIO itself may reject an absent Exec; a valid wrapper path with a
        # missing runtime target must not be inferred as a unique app identity.
        catalog = self.catalog(hidden, helper, terminal, other, future_webapp)
        self.assertEqual(catalog.excluded, {"hidden.desktop": "hidden",
                         "terminal.desktop": "terminal-content",
                         "firefox.webapp-new.desktop": "provider-required"})
        self.assertEqual(len(catalog.specs), len(DEFAULT) + 2)
        self.assertEqual(catalog.classify({"app_id": "helper"}).desktop_entry, "helper.desktop")
        self.assertEqual(catalog.classify({"app_id": "other"}).desktop_entry, "other.desktop")

    def test_shared_aliases_refuse_but_exact_declared_ids_remain(self):
        first = self.desktop("org.test.First.desktop", "StartupWMClass=SharedWindow\n")
        second = self.desktop("org.test.Second.desktop", "StartupWMClass=SharedWindow\n")
        catalog = self.catalog(first, second)
        for identity in ("SharedWindow", "true"):
            with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
                catalog.classify({"app_id": identity})
        for wm_class in ("SharedWindow", "true"):
            with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
                catalog.classify({"app_id": None, "window": 1, "window_properties": {"class": wm_class}})
        self.assertEqual(catalog.classify({"app_id": "org.test.First"}).desktop_entry, "org.test.First.desktop")

    def test_exact_desktop_identity_outranks_an_executable_alias(self):
        canonical = self.desktop("true.desktop")
        other = self.desktop("org.test.Other.desktop")
        self.assertEqual(self.catalog(canonical, other).classify({"app_id": "true"}).desktop_entry, "true.desktop")

    def test_native_desktop_id_outranks_other_launcher_wm_class(self):
        canonical = self.desktop("org.test.Native.desktop")
        helper = self.desktop("org.test.Helper.desktop", "NoDisplay=true\nStartupWMClass=org.test.Native\n")
        catalog = self.catalog(canonical, helper)
        self.assertEqual(catalog.classify({"app_id": "org.test.Native"}).desktop_entry, "org.test.Native.desktop")
        self.assertEqual(catalog.classify({"app_id": None, "window": 1, "window_properties": {"class": "org.test.Native"}}).desktop_entry, "org.test.Helper.desktop")

    def test_static_policy_cannot_be_replaced_by_desktop_metadata(self):
        override = self.desktop("firefox.desktop", "StartupWMClass=OtherFirefox\n")
        impostor = self.desktop("org.test.Impostor.desktop", "StartupWMClass=firefox\n")
        catalog = self.catalog(override, impostor)
        self.assertEqual(catalog.classify({"app_id": "firefox"}), next(s for s in DEFAULT if s.application_id == "firefox"))
        with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
            catalog.classify({"app_id": "OtherFirefox"})
        self.assertEqual(catalog.specs["whatsapp-web"].managed_by, "sway-autostart")
        with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
            catalog.classify({"app_id": None, "window": 1, "window_properties": {"class": "firefox"}})

    def test_launch_uses_pinned_desktop_file_without_snapshot_arguments(self):
        app = self.desktop(executable='"/usr/bin/true" "%U"')
        spec = self.catalog(app).classify({"app_id": "org.test.Editor"})
        with patch("session_v2.applications.subprocess.Popen") as popen:
            launch(spec, 1, {"TEST_ONLY": "1"})
            popen.assert_called_once()
            self.assertEqual(popen.call_args.args[0], ["/usr/bin/gio", "launch", app.get_filename()])
            self.assertNotIn("shell", popen.call_args.kwargs)
            self.assertEqual(popen.call_args.kwargs["env"], {"TEST_ONLY": "1"})
        with self.assertRaisesRegex(Failure, "APPLICATION_LAUNCH_FAILED"):
            launch(spec, 2)
        forged = {"application_id": spec.application_id, "desktop_entry": "/tmp/evil.desktop",
                  "strategy": spec.strategy, "managed_by": None, "identity_provider": None}
        with self.assertRaisesRegex(Failure, "APPLICATION_POLICY_MISMATCH"):
            self.catalog(app).validate(forged)

    def test_changed_or_writable_launcher_is_not_executed(self):
        app = self.desktop()
        spec = self.catalog(app).classify({"app_id": "org.test.Editor"})
        path = Path(app.get_filename())
        path.write_text(path.read_text() + "Comment=changed\n")
        with patch("session_v2.applications.subprocess.Popen") as popen:
            with self.assertRaisesRegex(Failure, "APPLICATION_LAUNCH_FAILED"):
                launch(spec, 1)
            popen.assert_not_called()
        path.chmod(0o666)
        self.assertEqual(self.catalog(app).excluded[app.get_id()], "invalid-desktop-file")

    def test_nonregular_launcher_is_refused_without_reading_it(self):
        app = self.desktop()
        spec = self.catalog(app).classify({"app_id": "org.test.Editor"})
        path = Path(app.get_filename())
        path.unlink()
        os.mkfifo(path)
        with patch("session_v2.applications.subprocess.Popen") as popen:
            with self.assertRaisesRegex(Failure, "APPLICATION_LAUNCH_FAILED"):
                launch(spec, 1)
            popen.assert_not_called()

    def test_flatpak_export_symlink_and_shared_wrapper(self):
        target = self.desktop("export/org.test.Flatpak.desktop", executable="/usr/bin/env TEST_ONLY=1 /usr/bin/true")
        alias = self.root / "org.test.Flatpak.desktop"
        alias.symlink_to(target.get_filename())
        app = self.GioUnix.DesktopAppInfo.new_from_filename(str(alias))
        spec = self.catalog(app).classify({"app_id": "org.test.Flatpak"})
        self.assertEqual(spec.desktop_signature[0], str(Path(target.get_filename()).resolve()))
        self.assertNotIn("env", spec.app_ids)
        with patch("session_v2.applications.subprocess.Popen") as popen:
            launch(spec, 1)
            popen.assert_called_once()

    def test_xdg_user_override_hidden_and_system_flatpak_roots(self):
        local, system, flatpak = (self.root / name for name in ("local", "system", "flatpak"))
        for directory in (local, system, flatpak):
            (directory / "applications").mkdir(parents=True)
        def put(directory, identifier, extra=""):
            (directory / "applications" / identifier).write_text("[Desktop Entry]\nType=Application\nName=TEST_ONLY\nExec=/usr/bin/true\n" + extra)
        put(system, "org.test.Shadow.desktop", "StartupWMClass=SystemClass\n")
        put(local, "org.test.Shadow.desktop", "StartupWMClass=LocalClass\n")
        put(system, "org.test.Deleted.desktop")
        put(local, "org.test.Deleted.desktop", "Hidden=true\n")
        put(flatpak, "org.test.Flatpak.desktop")
        program = "import sys,json;sys.path.insert(0,sys.argv[1]);from session_v2.applications import Catalog;c=Catalog();print(json.dumps({s.desktop_entry:s.app_ids for s in c.specs.values() if s.desktop_signature is not None}))"
        env = {**os.environ, "XDG_DATA_HOME": str(local), "XDG_DATA_DIRS": str(system) + ":" + str(flatpak), "XDG_CURRENT_DESKTOP": "sway"}
        data = json.loads(subprocess.check_output(["python3", "-B", "-c", program, str(BACKEND)], env=env, text=True, timeout=5))
        self.assertIn("LocalClass", data["org.test.Shadow.desktop"])
        self.assertNotIn("SystemClass", data["org.test.Shadow.desktop"])
        self.assertNotIn("org.test.Deleted.desktop", data)
        self.assertIn("org.test.Flatpak.desktop", data)

    def source(self):
        catalog = self.catalog(self.desktop())
        sway = Sway()
        sway.add("org.test.Editor", 7, focus=False)
        sway.add("org.test.Editor", 8, focus=True)
        data = capture(sway, catalog, None)
        return catalog, sway, data

    def test_multiwindow_capture_persists_layout_only_and_preserves_v1(self):
        catalog, sway, data = self.source()
        self.assertEqual(data["applications"][0]["expected_windows"], 2)
        self.assertEqual(data["applications"][0]["strategy"], "application-self-restore")
        self.assertTrue(all(slot["identity_requirement"] == "interchangeable" for slot in data["window_slots"]))
        for forbidden in ("argv", "desktop_signature", str(self.root)):
            self.assertNotIn(forbidden, json.dumps(data))
        store = Store(self.root / "state")
        store.checkpoint(data)
        self.assertEqual(store.last(), data)
        old = copy.deepcopy(data)
        old["version"] = 1
        old.pop("focus_workspace")
        for slot in old["window_slots"]: slot["state"]["scratchpad"] = False
        with self.assertRaisesRegex(Failure, "SCHEMA_STRATEGY"): validate(old)
        schema = json.loads((BACKEND / "session_v2/schema-v2.json").read_text())
        self.assertIn("application-self-restore", schema["$defs"]["application"]["properties"]["strategy"]["enum"])
        schema = json.loads((BACKEND / "session_v2/schema-v1.json").read_text())
        self.assertNotIn("application-self-restore", schema["$defs"]["application"]["properties"]["strategy"]["enum"])

    def test_launch_count_is_once_for_absent_app_and_zero_for_partial_presence(self):
        app = {"strategy": "application-self-restore", "expected_windows": 3}
        self.assertEqual([launch_count(app, count) for count in (0, 1, 2, 3)], [1, 0, 0, 0])
        with self.assertRaisesRegex(Failure, "UNEXPECTED_EXTRA_WINDOW"): launch_count(app, 4)

    def test_prewarm_launches_once_and_requires_full_window_set(self):
        catalog, sway, data = self.source()
        workspace(sway.value, "1")["nodes"] = []
        engine = Executor(sway, catalog, None, self.root / "runtime", "/forbidden", process_identity=lambda pid: 123)
        def once(spec, count, env):
            self.assertEqual(count, 1)
            sway.add("org.test.Editor", 20, focus=False)
            sway.add("org.test.Editor", 21, focus=True)
            return []
        with patch("session_v2.executor.launch", side_effect=once) as launcher, patch.object(engine, "_apply", return_value="admitted"):
            self.assertEqual(engine.apply(data, True, timeout=.5), "admitted")
            launcher.assert_called_once()
        self.assertEqual(sway.commands, [])
        self.assertFalse((self.root / "runtime" / JOURNAL).exists())

    def test_partial_generic_restore_defers_without_layout_or_retry_launch(self):
        catalog, sway, data = self.source()
        workspace(sway.value, "1")["nodes"] = []
        runtime = self.root / "runtime"
        engine = Executor(sway, catalog, None, runtime, "/forbidden", process_identity=lambda pid: 123)
        def only_one(spec, count, env):
            sway.add("org.test.Editor", 20, focus=True)
            return []
        with patch("session_v2.executor.launch", side_effect=only_one) as launcher, patch.object(engine, "_apply") as apply:
            for _ in range(2):
                with self.assertRaisesRegex(Deferred, "APPLICATION_WINDOWS_INCOMPLETE"):
                    engine.apply(data, True, timeout=.08)
            launcher.assert_called_once()
            apply.assert_not_called()
        self.assertEqual(sway.commands, [])
        self.assertFalse((runtime / JOURNAL).exists())


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gi
gi.require_version("GioUnix", "2.0")
from gi.repository import GioUnix


BACKEND = Path(__file__).resolve().parents[2] / "quickshell/.config/quickshell/labfy-sway/applications/backend.py"
SPEC = importlib.util.spec_from_file_location("applications_backend", BACKEND)
backend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backend)


def desktop(path, *, command, terminal=False, extra=""):
    path.write_text("[Desktop Entry]\nType=Application\nName=Fixture\n"
                    f"Exec={command}\nTerminal={'true' if terminal else 'false'}\n{extra}")
    return GioUnix.DesktopAppInfo.new_from_filename(str(path))


class FavoritesTests(unittest.TestCase):
    def test_seed_order_atomic_update_and_missing_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state/favorites.json"
            self.assertEqual(backend.read_favorites(path), (False, []))
            backend.write_favorites(path, "seed", ["firefox.desktop", "removed.desktop"])
            backend.write_favorites(path, "seed", ["other.desktop"])
            backend.write_favorites(path, "add", ["kitty.desktop"])
            self.assertEqual(backend.read_favorites(path)[1],
                             ["firefox.desktop", "removed.desktop", "kitty.desktop"])
            backend.write_favorites(path, "remove", ["firefox.desktop"])
            self.assertEqual(backend.read_favorites(path)[1],
                             ["removed.desktop", "kitty.desktop"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(set(json.loads(path.read_text())), {"version", "ids"})

    def test_bad_state_does_not_get_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "favorites.json"
            path.write_text('{"version":1,"ids":["bad/path.desktop"]}')
            with self.assertRaises(ValueError):
                backend.write_favorites(path, "add", ["kitty.desktop"])
            self.assertIn("bad/path.desktop", path.read_text())


class LaunchTests(unittest.TestCase):
    def test_graphical_uses_desktop_id_and_uwsm_service(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = desktop(Path(temporary) / "fixture.desktop", command="/usr/bin/true %F")
            calls = []
            class Result:
                returncode = 0
            backend.launch("fixture.desktop", loader=lambda _id: app,
                           runner=lambda *args, **kwargs: calls.append((args, kwargs)) or Result())
            self.assertEqual(calls[0][0][0],
                             ["uwsm", "app", "-t", "service", "--", "fixture.desktop"])

    def test_quoted_firefox_style_exec_uses_desktop_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = desktop(Path(temporary) / "fixture.desktop",
                          command='"/usr/bin/true" "-taskbar-tab" "fixture-id" '
                                  '"-new-window" "https://example.invalid/" %U')
            self.assertIsNotNone(app)
            runner = Mock(return_value=SimpleNamespace(returncode=0))
            backend.launch("fixture.desktop", loader=lambda _id: app, runner=runner)
            self.assertEqual(runner.call_args.args[0],
                             ["uwsm", "app", "-t", "service", "--", "fixture.desktop"])

    def test_quoted_executable_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "program directory" / "fixture executable"
            executable.parent.mkdir()
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            app = desktop(root / "fixture.desktop",
                          command=f'"{executable}" "argument avec espace" %F')
            self.assertIsNotNone(app)
            runner = Mock(return_value=SimpleNamespace(returncode=0))
            backend.launch("fixture.desktop", loader=lambda _id: app, runner=runner)
            self.assertEqual(runner.call_args.args[0][-1], "fixture.desktop")

    def test_quoted_kitty_is_not_wrapped_twice(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = desktop(Path(temporary) / "kitty-fixture.desktop",
                          command='"/usr/bin/kitty" "--hold"', terminal=True)
            self.assertIsNotNone(app)
            self.assertEqual(backend.terminal_launch_info(app).get_commandline().count("kitty"), 1)

    def test_unavailable_executable_is_still_refused(self):
        for unavailable in ("removed", "not_executable"):
            with self.subTest(unavailable=unavailable), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                executable = root / "fixture-command"
                executable.write_text("#!/bin/sh\nexit 0\n")
                executable.chmod(0o700)
                app = desktop(root / "fixture.desktop", command=f'"{executable}"')
                self.assertIsNotNone(app)
                if unavailable == "removed":
                    executable.unlink()
                else:
                    executable.chmod(0o600)
                runner = Mock()
                with self.assertRaisesRegex(ValueError, "Exécutable introuvable"):
                    backend.launch("fixture.desktop", loader=lambda _id: app, runner=runner)
                runner.assert_not_called()

    def test_dbus_activation_does_not_require_exec(self):
        app = Mock()
        app.get_is_hidden.return_value = False
        app.get_nodisplay.return_value = False
        app.should_show.return_value = True
        app.get_executable.return_value = None
        app.get_boolean.side_effect = lambda key: key == "DBusActivatable"
        app.get_commandline.side_effect = AssertionError("D-Bus has no Exec to parse")
        app.launch.return_value = True
        runner = Mock()
        backend.launch("org.example.Fixture.desktop", loader=lambda _id: app, runner=runner)
        app.launch.assert_called_once_with([], None)
        app.get_commandline.assert_not_called()
        runner.assert_not_called()

    def test_terminal_preserves_desktop_exec_fields_and_kitty(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = desktop(root / "fixture.desktop",
                          command='/usr/bin/printf "argument avec espace" %c %k',
                          terminal=True, extra=f"Path={root}\n")
            transformed = backend.terminal_launch_info(app)
            self.assertFalse(transformed.get_boolean("Terminal"))
            self.assertEqual(transformed.get_executable(), "uwsm")
            self.assertIn("kitty -- /usr/bin/printf", transformed.get_commandline())
            self.assertIn(str(root / "fixture.desktop"), transformed.get_commandline())
            self.assertEqual(transformed.get_string("Path"), str(root))

    def test_terminal_entry_already_running_kitty_is_not_wrapped_twice(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = desktop(Path(temporary) / "kitty-fixture.desktop",
                          command="kitty --hold", terminal=True)
            self.assertEqual(backend.terminal_launch_info(app).get_commandline().count("kitty"), 1)

    def test_invalid_id_and_missing_entry(self):
        with self.assertRaises(ValueError):
            backend.launch("/tmp/arbitrary.desktop")
        with self.assertRaises(ValueError):
            backend.launch("missing-fixture.desktop", loader=lambda _id: None)

    def test_nodisplay_entry_is_refused_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = desktop(Path(temporary) / "hidden.desktop", command="/usr/bin/true",
                          extra="NoDisplay=true\n")
            with self.assertRaisesRegex(ValueError, "indisponible"):
                backend.launch("hidden.desktop", loader=lambda _id: app,
                               runner=lambda *_args, **_kwargs: self.fail("launch called"))

    def test_nextcloud_uses_gio_command_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = desktop(Path(temporary) / "fixture.desktop", command="/usr/bin/true %u")
            prepared = Mock()
            prepared.launch.return_value = True
            runner = Mock()
            with patch.object(backend, "uwsm_launch_info", return_value=prepared) as prepare:
                backend.launch("com.nextcloud.desktopclient.nextcloud.desktop",
                               loader=lambda _id: app, runner=runner)
            prepare.assert_called_once_with(app)
            prepared.launch.assert_called_once_with([], None)
            runner.assert_not_called()

    def test_nextcloud_cloudproviders_and_source_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.desktop"
            app = desktop(path, command="/usr/bin/true %u", extra=
                          "SingleMainWindow=true\nImplements=org.freedesktop.CloudProviders\n"
                          "[org.freedesktop.CloudProviders]\n"
                          "BusName=org.example.Fixture\nObjectPath=/org/example/Fixture\n")
            before = path.read_bytes()
            prepared = backend.uwsm_launch_info(app)
            self.assertEqual(prepared.get_executable(), "uwsm")
            self.assertEqual(prepared.get_commandline(),
                             "uwsm app -t service -- /usr/bin/true %u")
            self.assertEqual(prepared.get_string("Implements"),
                             "org.freedesktop.CloudProviders")
            self.assertTrue(prepared.get_boolean("SingleMainWindow"))
            self.assertFalse(prepared.get_boolean("Terminal"))
            self.assertFalse(prepared.get_boolean("DBusActivatable"))
            self.assertEqual(path.read_bytes(), before)

    def test_graphical_wrapper_expands_fields_without_shell_or_kitty(self):
        for field in ("%u", "%F"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bindir = root / "bin"
                bindir.mkdir()
                recorder = bindir / "uwsm"
                recorder.write_text("#!/usr/bin/python3\nimport json,os,sys\n"
                                    "with open(os.environ['LABFY_LAUNCH_TEST_CAPTURE'],'w') as f:"
                                    " json.dump({'argv':sys.argv[1:],'cwd':os.getcwd()},f)\n")
                recorder.chmod(0o700)
                executable = root / "program with spaces"
                executable.write_text("#!/bin/sh\nexit 99\n")
                executable.chmod(0o700)
                output = root / "captured.json"
                entry = root / "entry with spaces.desktop"
                app = desktop(entry,
                              command=f'"{executable}" "argument avec espace" {field} %c %k %%',
                              extra=f"Path={root}\n")
                self.assertIsNotNone(app)
                env = {"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
                       "LABFY_LAUNCH_TEST_CAPTURE": str(output)}
                with patch.dict(os.environ, env):
                    prepared = backend.uwsm_launch_info(app)
                    self.assertTrue(prepared.launch([], None))
                    deadline = time.monotonic() + 3
                    while not output.exists() and time.monotonic() < deadline:
                        time.sleep(.01)
                self.assertTrue(output.exists())
                observed = json.loads(output.read_text())
                self.assertEqual(observed["argv"],
                                 ["app", "-t", "service", "--", str(executable),
                                  "argument avec espace", "Fixture", str(entry), "%"])
                self.assertEqual(observed["cwd"], str(root))

    def test_nextcloud_launch_failure_and_missing_uwsm_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = desktop(Path(temporary) / "fixture.desktop", command="/usr/bin/true %u")
            prepared = Mock()
            prepared.launch.return_value = False
            runner = Mock()
            with patch.object(backend, "uwsm_launch_info", return_value=prepared):
                with self.assertRaisesRegex(ValueError, "lancement refusée"):
                    backend.launch("com.nextcloud.desktopclient.nextcloud.desktop",
                                   loader=lambda _id: app, runner=runner)
            with patch.object(backend.shutil, "which",
                              side_effect=lambda name: None if name == "uwsm" else "/usr/bin/true"):
                with self.assertRaisesRegex(ValueError, "UWSM indisponible"):
                    backend.launch("com.nextcloud.desktopclient.nextcloud.desktop",
                                   loader=lambda _id: app, runner=runner)
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()

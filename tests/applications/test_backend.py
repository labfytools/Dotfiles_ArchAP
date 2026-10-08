import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

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


if __name__ == "__main__":
    unittest.main()

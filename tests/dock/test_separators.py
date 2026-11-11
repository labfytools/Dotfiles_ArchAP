"""Separators persist independently of the v1 favorites file."""
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[2] / "quickshell/.config/quickshell/labfy-sway/applications"
sys.path.insert(0, str(APP))
import backend
import dock_separators as sep


class SeparatorPersistence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.favorites = Path(self.temp.name) / "labfy-sway/applications-favorites.json"
        backend.write_favorites(self.favorites, "seed",
                                ["a.desktop", "b.desktop", "c.desktop"])
        self.original = self.favorites.read_bytes()
        self.path = sep.path_for(self.favorites)

    def test_add_move_delete_durable(self):
        self.assertEqual(sep.read(self.path), [])
        first = sep.write(self.path, "add", [1])
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["position"], 1)
        identifier = first[0]["id"]
        self.assertRegex(identifier, r"^sep-[0-9a-f]{12}$")
        self.assertEqual(sep.read(self.path), first)
        self.assertEqual(sep.write(self.path, "move", [identifier, 2])[0]["position"], 2)
        second = sep.write(self.path, "add", [0])
        self.assertEqual([x["position"] for x in second], [0, 2])
        self.assertEqual(sep.write(self.path, "remove", [identifier])[0]["position"], 0)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.favorites.read_bytes(), self.original)

    def test_invalid_actions_never_replace_previous_state(self):
        entry = sep.write(self.path, "add", [1])[0]
        before = self.path.read_bytes()
        invalid = [("add", [1]), ("add", [-1]), ("add", [True]),
                   ("add", ["1"]), ("add", [65]), ("move", [entry["id"], 65]),
                   ("move", ["sep-000000000000", 3]), ("move", [entry["id"], False]),
                   ("remove", ["../escape"]), ("remove", ["sep-000000000000"]),
                   ("invalid", [])]
        for action, value in invalid:
            with self.subTest(action=action, value=value), self.assertRaises(ValueError):
                sep.write(self.path, action, value)
            self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.favorites.read_bytes(), self.original)

    def test_corrupt_and_symlink_state_refuse_overwrite(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('{"version":1,"separators":[{"id":"invalid","position":2}]}')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            sep.write(self.path, "add", [1])
        self.assertEqual(self.path.read_bytes(), before)
        self.path.unlink()
        self.path.symlink_to(self.favorites)
        with self.assertRaises(ValueError):
            sep.write(self.path, "add", [1])
        self.assertEqual(self.favorites.read_bytes(), self.original)

    def test_concurrent_changes_stay_atomic_and_bounded(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            items = list(pool.map(lambda i: sep.write(self.path, "add", [i]),
                                  range(10)))
        self.assertEqual(len(items), 10)
        self.assertEqual(len(sep.read(self.path)), 10)
        for index in range(10, 16):
            sep.write(self.path, "add", [index])
        with self.assertRaisesRegex(ValueError, "Trop de séparateurs"):
            sep.write(self.path, "add", [16])
        self.assertEqual(len(sep.read(self.path)), 16)
        self.assertEqual(self.favorites.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()

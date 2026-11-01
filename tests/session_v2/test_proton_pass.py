"""Password manager capture uses only the normal window placement contract."""
import json
import tempfile
import unittest
from unittest.mock import patch
from common import *
from test_scratchpad import source
from session_v2.checkpoint import Store
from session_v2.errors import Failure
from session_v2.executor import Executor
from session_v2.ipc import walk, workspace
from session_v2.recovery import JOURNAL
from session_v2.snapshot import capture


def password_manager():
    sway = source()
    hidden = workspace(sway.value, "__i3_scratch")["floating_nodes"][0]
    hidden.update(app_id="proton-pass", name="TEST_ONLY_PRIVATE_WINDOW_TITLE")
    return sway, hidden


class ProtonPassTests(unittest.TestCase):
    def test_hidden_window_capture_store_round_trip(self):
        sway, hidden = password_manager()
        before = sway.tree()
        data = capture(sway, Catalog(), None)
        app = next(a for a in data["applications"] if a["application_id"] == "proton-pass")
        slot = next(s for s in data["window_slots"] if s["application_id"] == "proton-pass")
        self.assertEqual((app["desktop_entry"], app["strategy"], app["expected_windows"]),
                         ("proton-pass.desktop", "single-window", 1))
        self.assertEqual(slot["state"]["scratchpad"], "hidden")
        self.assertEqual(slot["state"]["geometry"], hidden["rect"])
        self.assertIsNone(slot["workspace"])
        self.assertEqual(slot["identity_evidence"],
                         {"type": "application-singleton", "id": "proton-pass"})
        self.assertNotIn("TEST_ONLY_PRIVATE_WINDOW_TITLE", json.dumps(data))
        self.assertEqual(sway.tree(), before)
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary))
            store.checkpoint(data)
            self.assertEqual(store.last(), data)

    def test_existing_hidden_window_is_not_launched_again(self):
        sway, _ = password_manager()
        data = capture(sway, Catalog(), None)
        with tempfile.TemporaryDirectory() as temporary:
            engine = Executor(sway, Catalog(), None, Path(temporary),
                              "/forbidden", process_identity=lambda pid: 123)
            with patch("session_v2.executor.launch") as launch, patch.object(engine, "_apply", return_value="admitted"):
                self.assertEqual(engine.apply(data, True), "admitted")
                launch.assert_not_called()
            self.assertFalse((Path(temporary) / JOURNAL).exists())
        self.assertEqual(sway.commands, [])

    def test_ambiguous_or_unknown_window_still_refuses(self):
        sway, _ = password_manager()
        sway.add("proton-pass", 99, focus=False)
        with self.assertRaisesRegex(Failure, "APPLICATION_POLICY_MISMATCH"):
            capture(sway, Catalog(), None)
        self.assertEqual(sway.commands, [])
        sway, hidden = password_manager()
        hidden["app_id"] = "proton-pass-unregistered"
        with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
            capture(sway, Catalog(), None)


if __name__ == "__main__":
    unittest.main()

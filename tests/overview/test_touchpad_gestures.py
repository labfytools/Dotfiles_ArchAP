"""Contrôles du dispatcher sans geste matériel ni effet sur la session."""

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "sway/.config/sway/scripts/touchpad-gestures"
loader = importlib.machinery.SourceFileLoader("touchpad_gestures", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
gesture = importlib.util.module_from_spec(spec)
loader.exec_module(gesture)


class TouchpadGestureTests(unittest.TestCase):
    def run_action(self, action, overview=None, auth=None, output="eDP-1"):
        overview = overview or {"loaded": False, "requested": False}
        auth = auth or {"registered": True, "active": False, "dialog": False,
                        "queryRunning": False}
        calls = []

        def fake_run(*args):
            calls.append(args)
            if args[:3] == ("swaymsg", "-t", "get_workspaces"):
                return json.dumps([{"focused": False, "output": "HDMI-A-1"},
                                   {"focused": True, "output": output}])
            if args[:3] == ("swaymsg", "-t", "get_version"):
                return '{}'
            if args[:2] == ("swaymsg", "-r"):
                return '[{"success":true}]'
            raise AssertionError(args)

        def fake_state(target):
            calls.append(("state", target))
            return auth if target == "polkitUi" else overview

        def fake_ipc(target, operation):
            calls.append(("ipc", target, operation))
            if operation == "active":
                return "true" if overview["loaded"] or overview["requested"] else "false"
            if operation == "close":
                overview["loaded"] = False
                overview["requested"] = False
            return "true"

        with patch.object(gesture, "run", fake_run), \
                patch.object(gesture, "state", fake_state), \
                patch.object(gesture, "ipc", fake_ipc):
            result = gesture.dispatch(action)
        return result, calls

    def test_open_and_close_use_explicit_ipc(self):
        for action in ("open", "close"):
            with self.subTest(action=action):
                result, calls = self.run_action(action)
                self.assertEqual(result, 0)
                self.assertIn(("ipc", "overviewUi-eDP-1", action), calls)
                self.assertFalse(any(call[:2] == ("swaymsg", "-r") for call in calls))

    def test_horizontal_closes_before_native_workspace_command(self):
        result, calls = self.run_action("next", {"loaded": True, "requested": True})
        self.assertEqual(result, 0)
        self.assertLess(calls.index(("ipc", "overviewUi-eDP-1", "close")),
                        calls.index(("swaymsg", "-r", "workspace", "next_on_output")))
        self.assertIn(("swaymsg", "-t", "get_version", "-r"), calls)
        self.assertFalse(any("move" in str(call) for call in calls))

    def test_previous_uses_current_output_and_no_move(self):
        result, calls = self.run_action("prev")
        self.assertEqual(result, 0)
        self.assertIn(("swaymsg", "-r", "workspace", "prev_on_output"), calls)
        self.assertFalse(any("move" in str(call) for call in calls))

    def test_overview_targets_focused_output_not_first_output(self):
        result, calls = self.run_action("open", output="DP-2")
        self.assertEqual(result, 0)
        self.assertIn(("ipc", "overviewUi-DP-2", "open"), calls)

    def test_polkit_blocks_all_actions(self):
        for action in ("open", "close", "next", "prev"):
            with self.subTest(action=action):
                result, calls = self.run_action(action, auth={"registered": True, "active": True})
                self.assertEqual(result, 0)
                self.assertEqual(calls, [("state", "polkitUi")])

    def test_incomplete_polkit_state_fails_closed(self):
        result, calls = self.run_action("next", auth={"registered": True})
        self.assertEqual(result, 0)
        self.assertEqual(calls, [("state", "polkitUi")])

    def test_ipc_failure_is_bounded_and_fails_closed(self):
        with patch.object(gesture, "state", side_effect=subprocess.TimeoutExpired("quickshell", 1.5)):
            self.assertEqual(gesture.main(["touchpad-gestures", "next"]), 1)


if __name__ == "__main__":
    unittest.main()

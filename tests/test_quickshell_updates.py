import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "quickshell/.config/quickshell/labfy-sway/bin/check-updates.py"
SPEC = importlib.util.spec_from_file_location("quickshell_updates", SOURCE)
updates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updates)


class CountTests(unittest.TestCase):
    def check_count(self, command, returncode, stdout, stderr, expected):
        result = subprocess.CompletedProcess(command, returncode, stdout, stderr)
        with mock.patch.object(updates.subprocess, "run", return_value=result) as run:
            if isinstance(expected, type) and issubclass(expected, Exception):
                with self.assertRaises(expected):
                    updates.count(command)
            else:
                self.assertEqual(updates.count(command), expected)
            run.assert_called_once_with(command, capture_output=True, text=True, timeout=120, check=False)

    def test_checkupdates_counts_lines(self):
        self.check_count(["checkupdates"], 0, "pkg-a 1 -> 2\npkg-b 3 -> 4\n", "", 2)

    def test_checkupdates_no_updates(self):
        self.check_count(["checkupdates"], 2, "", "", 0)

    def test_checkupdates_code_one_is_error(self):
        self.check_count(["checkupdates"], 1, "", "", RuntimeError)

    def test_checkupdates_code_two_with_stderr_is_error(self):
        self.check_count(["checkupdates"], 2, "", "erreur inattendue", RuntimeError)

    def test_yay_no_updates(self):
        self.check_count(["yay", "-Qua"], 1, "", "", 0)

    def test_yay_counts_lines(self):
        self.check_count(["yay", "-Qua"], 0, "aur-a 1 -> 2\naur-b 3 -> 4\n", "", 2)


if __name__ == "__main__":
    unittest.main()

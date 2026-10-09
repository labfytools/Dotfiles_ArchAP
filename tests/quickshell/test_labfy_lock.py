"""Contrôles TEST_ONLY sur un compositeur Sway headless enfant."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "session_v2/fixtures"))
from headless import Lab

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "bin/.local/bin/labfy-lock"


class LockLifecycleTests(unittest.TestCase):
    def test_refuses_second_lock(self):
        with Lab() as lab:
            # CONTRACT: un autre processus détient déjà WlSessionLock ; le
            # wrapper ne doit pas déclarer sa propre acquisition secure.
            lab.env["LABFY_LOCK_GENERATION"] = "foreign"
            holder = lab.start(["quickshell", "--path", str(ROOT / "quickshell/.config/quickshell/labfy-lock")])
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                observed = subprocess.run(
                    ["quickshell", "ipc", "--pid", str(holder.pid), "call", "lock", "state"],
                    env=lab.env, capture_output=True, text=True, timeout=2)
                if observed.stdout.strip() == "foreign:secure":
                    break
                time.sleep(.08)
            self.assertEqual(observed.stdout.strip(), "foreign:secure")
            attempt = subprocess.run([str(WRAPPER)], env=lab.env,
                                     capture_output=True, text=True, timeout=12)
            self.assertNotEqual(attempt.returncode, 0)
            self.assertNotIn("secure", attempt.stdout)

    def test_concurrent_secure_and_crash_reacquisition(self):
        with Lab() as lab:
            first = subprocess.Popen([str(WRAPPER)], env=lab.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            second = subprocess.Popen([str(WRAPPER)], env=lab.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(first.communicate(timeout=12)[1], "")
            self.assertEqual(second.communicate(timeout=12)[1], "")
            self.assertEqual((first.returncode, second.returncode), (0, 0))
            record = json.loads((lab.directory / "labfy-lock.launch").read_text())
            pid = record["pid"]
            try:
                observed = subprocess.run(
                    ["quickshell", "ipc", "--pid", str(pid), "call", "lock", "state"],
                    env=lab.env, capture_output=True, text=True, timeout=2)
                self.assertEqual(observed.stdout.strip(), record["generation"] + ":secure")
                # No callable IPC path may authorize unlock.
                forbidden = subprocess.run(
                    ["quickshell", "ipc", "--pid", str(pid), "call", "lock", "unlock"],
                    env=lab.env, capture_output=True, text=True, timeout=2)
                # Some QuickShell versions return 0 even for an unknown method;
                # the compositor state is the authoritative observation.
                self.assertNotIn(record["generation"] + ":secure", forbidden.stdout)
                still_locked = subprocess.run(
                    ["quickshell", "ipc", "--pid", str(pid), "call", "lock", "state"],
                    env=lab.env, capture_output=True, text=True, timeout=2)
                self.assertEqual(still_locked.stdout.strip(), record["generation"] + ":secure")
                # Dynamic outputs remain owned by the same lock conversation.
                for command in ("create_output", "output HEADLESS-2 mode 800x600",
                                "output HEADLESS-2 scale 1.5",
                                "output HEADLESS-2 mode 1024x768",
                                "output HEADLESS-2 disable"):
                    lab.command(command)
                    time.sleep(.12)
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        state = subprocess.run(
                            ["quickshell", "ipc", "--pid", str(pid), "call", "lock", "state"],
                            env=lab.env, capture_output=True, text=True, timeout=2)
                        if state.stdout.strip() == record["generation"] + ":secure":
                            break
                        time.sleep(.05)
                    self.assertEqual(state.stdout.strip(), record["generation"] + ":secure", command)
                self.assertTrue(Path(f"/proc/{pid}").exists())
            finally:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and Path(f"/proc/{pid}").exists():
                time.sleep(.05)
            retry = subprocess.run([str(WRAPPER)], env=lab.env,
                                   capture_output=True, text=True, timeout=12)
            self.assertEqual(retry.returncode, 0, retry.stderr)
            replacement = json.loads((lab.directory / "labfy-lock.launch").read_text())
            self.assertNotEqual(replacement["generation"], record["generation"])
            os.kill(replacement["pid"], signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()

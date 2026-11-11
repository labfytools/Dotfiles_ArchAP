"""Non-destructive tests of the actual update collector and terminal boundary."""
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "quickshell/.config/quickshell/labfy-sway"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


updates = load("quickshell_updates", BASE / "bin/check-updates.py")
terminal = load("quickshell_update_terminal", BASE / "bin/update-terminal.py")


class CollectorTests(unittest.TestCase):
    def collect(self, command, code, stdout="", stderr=""):
        with mock.patch.object(updates.subprocess, "run", return_value=subprocess.CompletedProcess(command, code, stdout, stderr)):
            return updates.packages(command, "Arch" if command[0] == "checkupdates" else "AUR")

    def test_zero(self):
        self.assertEqual(self.collect(["checkupdates"], 2), [])
        self.assertEqual(self.collect(["yay", "-Qua"], 1), [])
        self.assertEqual(self.collect(["yay", "-Qua"], 0), [])

    def test_versions_and_sensitive(self):
        rows = self.collect(["checkupdates"], 0, "linux-zen 1 -> 2\nmesa 3 -> 4\nquickshell-git 4 -> 5\n")
        self.assertEqual([p["sensitive"] for p in rows], ["Noyau", "Graphique", "Session"])
        self.assertEqual(rows[0]["installed"], "1")
        self.assertEqual(rows[0]["available"], "2")
        self.assertEqual(rows[0]["origin"], "Arch")
        self.assertEqual(self.collect(["yay", "-Qua"], 0, "pkg-git 1 -> 2\n")[0]["origin"], "AUR")

    def test_aur_relative_age_suffix_keeps_versions_and_count(self):
        output = ("proton-pass-bin 1.43.0-1 -> 1.43.1-1 [12h36m]\n"
                  "example-bin 2:2.0-1 -> 2:2.1-1 [2d3h]\n"
                  "plain-git 1 -> 2\n")
        rows = self.collect(["yay", "-Qua"], 0, output)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["name"], "proton-pass-bin")
        self.assertEqual(rows[0]["available"], "1.43.1-1")
        self.assertEqual(rows[1]["available"], "2:2.1-1")
        self.assertEqual([row["origin"] for row in rows], ["AUR"] * 3)

    def test_age_suffix_is_bounded_and_aur_only(self):
        for output in ("pkg 1 -> 2 [something went wrong]\n",
                       "pkg 1 -> 2 [12h36m] extra\n",
                       "pkg 1 -> 2 [123456789h]\n" * 100):
            with self.subTest(output=output[:40]), self.assertRaises(RuntimeError):
                self.collect(["yay", "-Qua"], 0, output)
        with self.assertRaises(RuntimeError):
            self.collect(["checkupdates"], 0, "pkg 1 -> 2 [12h36m]\n")

    def test_errors_not_zero(self):
        for command, code, stdout, stderr in ((["checkupdates"], 1, "", ""), (["checkupdates"], 2, "", "failure"),
                                             (["yay"], 1, "", "network"), (["yay"], 0, "bad output", "")):
            with self.subTest(command=command, code=code, stderr=stderr):
                with self.assertRaises(RuntimeError):
                    self.collect(command, code, stdout, stderr)

    def test_snapshot_success_partial_failure_offline_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            row = dict(name="linux", installed="1", available="2", origin="Arch", sensitive="Noyau")
            with mock.patch.object(updates, "packages", side_effect=[[row], []]):
                self.assertFalse(updates.check(runtime))
            path = runtime / "labfy-quickshell-updates.json"
            self.assertEqual(json.loads(path.read_text())["totalUpdates"], 1)
            with mock.patch.object(updates, "packages", side_effect=[RuntimeError("network"), []]), mock.patch.object(updates, "offline", return_value=True):
                self.assertTrue(updates.check(runtime))
            state = json.loads(path.read_text())
            self.assertTrue(state["offline"])
            self.assertFalse(state["checking"])
            self.assertEqual(state["packages"], [row])
            self.assertEqual(state["totalUpdates"], 1)
            with mock.patch.object(updates, "packages", side_effect=[[], []]):
                self.assertFalse(updates.check(runtime))
            self.assertEqual(json.loads(path.read_text())["totalUpdates"], 0)

    def test_corrupt_snapshot_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            path = runtime / "labfy-quickshell-updates.json"
            updates.publish(path, dict(repoUpdates="invalid", packages=[None]))
            with mock.patch.object(updates, "packages", side_effect=[[], []]):
                self.assertFalse(updates.check(runtime))
            self.assertEqual(json.loads(path.read_text())["totalUpdates"], 0)

    def test_lock_prevents_second_check(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, XDG_RUNTIME_DIR=folder), mock.patch.object(updates.sys, "argv", ["check-updates.py"]):
            with open(Path(folder)/"labfy-updates.lock", "w") as lock:
                updates.fcntl.flock(lock, updates.fcntl.LOCK_EX)
                with mock.patch.object(updates, "check") as check:
                    self.assertEqual(updates.main(), 0)
                    check.assert_not_called()

    def test_offline_probe(self):
        with mock.patch.object(updates.socket, "create_connection", side_effect=OSError("offline")):
            self.assertTrue(updates.offline())

    def test_news_explicit_only_and_safe_links(self):
        data = b'''<rss><channel><item><title>linux requires manual intervention</title><link>https://archlinux.org/news/test/</link><pubDate>today</pubDate></item><item><title>linux update</title><link>https://archlinux.org/news/other/</link></item><item><title>bad</title><link>file:///etc/passwd</link></item></channel></rss>'''
        rows = updates.parse_news(data)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["manual"])
        self.assertFalse(rows[1]["manual"])

    def test_news_offline_cache_and_backoff(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, XDG_CACHE_HOME=folder):
            cache = Path(folder)/"labfy-update-news.json"
            updates.publish(cache, dict(fetched=1, items=[dict(title="cached")]))
            with mock.patch.object(updates.urllib.request, "urlopen", side_effect=OSError("offline")) as urlopen:
                first = updates.news()
                second = updates.news()
                self.assertEqual(first["items"], second["items"])
                self.assertIn("cache conservé", second["error"])
                self.assertEqual(urlopen.call_count, 1)

    def test_maintenance_read_only_and_partial_scan(self):
        # Synthetic /etc fixture includes forbidden-to-change files and an access error.
        def walk(root, **kwargs):
            self.assertEqual(root, "/etc")
            self.assertFalse(kwargs["followlinks"])
            kwargs["onerror"](PermissionError("restricted"))
            yield "/etc", [], ["foo.pacnew", "bar.pacsave", "normal"]
        log = mock.mock_open(read_data=b"[2026-11-08] [ALPM] transaction completed\n")
        log.return_value.tell.return_value = 55
        with mock.patch("builtins.open", log), mock.patch.object(updates.os, "walk", side_effect=walk), mock.patch.object(updates, "output", return_value="bad.service loaded failed failed demo\n"):
            result = updates.maintenance()
        self.assertEqual(result["files"], ["/etc/bar.pacsave", "/etc/foo.pacnew"])
        self.assertEqual(len(result["failed"]), 2)
        self.assertTrue(result["errors"])
        self.assertTrue(result["history"])
        self.assertTrue(result["reboot"])


class TerminalTests(unittest.TestCase):
    def test_preview_never_installs(self):
        with mock.patch.object(terminal.sys, "argv", ["terminal", "--dry-run"]), mock.patch("builtins.input", return_value=""), mock.patch.object(terminal.subprocess, "call") as call, mock.patch.object(terminal.subprocess, "run") as run, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(terminal.main(), 0)
            call.assert_not_called()
            run.assert_not_called()

    def test_declined_confirmation_never_installs(self):
        with mock.patch.object(terminal.sys, "argv", ["terminal"]), mock.patch.object(terminal.sys.stdin, "isatty", return_value=True), mock.patch.object(terminal.os, "geteuid", return_value=1000), mock.patch.object(terminal.shutil, "which", return_value="/usr/bin/yay"), mock.patch("builtins.input", return_value="non"), mock.patch.object(terminal.subprocess, "call") as call, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(terminal.main(), 0)
            call.assert_not_called()

    def test_confirmed_argv_with_fake_process_only(self):
        # Even the affirmative branch is intercepted: no real package manager is run.
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, XDG_RUNTIME_DIR=folder), mock.patch.object(terminal.sys, "argv", ["terminal"]), mock.patch.object(terminal.sys.stdin, "isatty", return_value=True), mock.patch.object(terminal.os, "geteuid", return_value=1000), mock.patch.object(terminal.shutil, "which", return_value="/usr/bin/yay"), mock.patch("builtins.input", side_effect=["METTRE A JOUR", ""]), mock.patch.object(terminal.subprocess, "call", return_value=0) as call, mock.patch.object(terminal.subprocess, "run") as run, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(terminal.main(), 0)
            argv = call.call_args.args[0]
            self.assertEqual(argv[:3], ["yay", "-Syu", "--confirm"])
            self.assertIn("--sudoloop=false", argv)
            self.assertNotIn("--noconfirm", argv)
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

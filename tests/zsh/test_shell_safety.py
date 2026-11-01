"""Tests Zsh isolés, sans toucher aux données personnelles ni au système."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


def shell(command, *, cwd=None, stdin=None):
    env = os.environ.copy()
    env["ZDOTDIR"] = str(REPO / "zsh")
    return subprocess.run(
        ["zsh", "-ic", command], cwd=cwd, input=stdin, text=True,
        capture_output=True, env=env, timeout=20
    )


class ShellSafetyTests(unittest.TestCase):
    def test_unique_path(self):
        p = shell("print -- PATH_BEGIN; print -rl -- $path; print -- PATH_END")
        self.assertEqual(p.returncode, 0, p.stderr)
        entries = p.stdout.split("PATH_BEGIN\n", 1)[1].split("PATH_END", 1)[0].strip().splitlines()
        self.assertTrue(entries)
        self.assertEqual(len(entries), len(set(entries)))

    def test_orphans_args_and_empty_result(self):
        p = shell('pacman() { print -rl -- alpha beta; }; '
                  'sudo() { print -r -- "CALL $*"; }; orphans')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("CALL pacman -Rns -- alpha beta", p.stdout)
        empty = shell('pacman() { return 1; }; '
                      'sudo() { print -- ERROR_CALL; }; orphans')
        self.assertEqual(empty.returncode, 0, empty.stderr)
        self.assertIn("Aucun paquet orphelin", empty.stdout)
        self.assertNotIn("ERROR_CALL", empty.stdout)

    def test_update_stops_if_pacman_fails(self):
        success = shell('sudo() { print -r -- "CALL $*"; }; '
                        'aurupdate() { print -- AUR_CALLED; }; update')
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertIn("CALL pacman -Syu", success.stdout)
        self.assertIn("AUR_CALLED", success.stdout)
        fail = shell('sudo() { return 7; }; '
                     'aurupdate() { print -- SHOULD_NOT_RUN; }; update')
        self.assertEqual(fail.returncode, 7)
        self.assertNotIn("SHOULD_NOT_RUN", fail.stdout)

    def test_clean_exe_confirms_and_preserves_scripts(self):
        with tempfile.TemporaryDirectory(prefix="zsh-test-elf-") as td:
            root = Path(td)
            elf = root / "binary"
            if not Path("/usr/bin/true").exists():
                self.skipTest("ELF fixture unavailable")
            shutil.copy2("/usr/bin/true", elf)
            elf.chmod(0o755)
            script = root / "utility.py"
            script.write_text("#!/usr/bin/env python3\nprint('safe')\n")
            script.chmod(0o755)
            preview = shell("clean-exe --dry-run", cwd=td)
            self.assertIn("./binary", preview.stdout)
            self.assertNotIn("./utility.py", preview.stdout)
            self.assertTrue(elf.exists())
            cancel = shell("clean-exe", cwd=td, stdin="NON\n")
            self.assertEqual(cancel.returncode, 1)
            self.assertTrue(elf.exists())
            confirm = shell("clean-exe", cwd=td, stdin="SUPPRIMER\n")
            self.assertEqual(confirm.returncode, 0, confirm.stderr)
            self.assertFalse(elf.exists())
            self.assertTrue(script.exists())

    def test_clean_exe_ignores_git_tracked_binary(self):
        with tempfile.TemporaryDirectory(prefix="zsh-test-git-elf-") as td:
            root = Path(td)
            binary = root / "tracked-program"
            if not Path("/usr/bin/true").exists():
                self.skipTest("ELF fixture unavailable")
            shutil.copy2("/usr/bin/true", binary)
            binary.chmod(0o755)
            subprocess.run(["git", "init", "-q", td], check=True)
            subprocess.run(["git", "-C", td, "add", "tracked-program"], check=True)
            preview = shell("clean-exe --dry-run", cwd=td)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("Aucun exécutable ELF local", preview.stdout)
            self.assertTrue(binary.exists())

    def test_vrm_confirms_only_real_virtualenv(self):
        with tempfile.TemporaryDirectory(prefix="zsh-test-venv-") as td:
            root = Path(td)
            env = root / "venv"
            env.mkdir()
            (env / "pyvenv.cfg").write_text("home=/usr/bin\n")
            unrelated = root / ".venv"
            unrelated.mkdir()
            (unrelated / "keep.txt").write_text("keep")
            preview = shell("vrm --dry-run", cwd=td)
            self.assertIn("venv", preview.stdout)
            self.assertTrue(env.exists())
            cancel = shell("vrm", cwd=td, stdin="NON\n")
            self.assertEqual(cancel.returncode, 1)
            self.assertTrue(env.exists())
            accept = shell("vrm", cwd=td, stdin="SUPPRIMER\n")
            self.assertEqual(accept.returncode, 0, accept.stderr)
            self.assertFalse(env.exists())
            self.assertTrue((unrelated / "keep.txt").exists())

    def test_osint_invalid_arguments_do_not_run_commands(self):
        for command in ("geoip", "shot unknown", "subdomains"):
            with self.subTest(command=command):
                p = shell(command)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assertIn("Usage", p.stderr)


if __name__ == "__main__":
    unittest.main()

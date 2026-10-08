import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[2] / "quickshell/.config/quickshell/labfy-sway/clipboard/backend.py"
PNG = subprocess.run(["magick", "-size", "1x1", "xc:red", "png:-"], capture_output=True, check=True).stdout


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = str(self.root / "db")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "wl-copy"
        fake.write_text("#!/usr/bin/env python3\nimport os,sys,pathlib\n"
                        "pathlib.Path(os.environ['TEST_CLIP_BYTES']).write_bytes(sys.stdin.buffer.read())\n"
                        "pathlib.Path(os.environ['TEST_CLIP_MIME']).write_text(sys.argv[2])\n")
        fake.chmod(0o700)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        XDG_RUNTIME_DIR=str(self.root), TEST_CLIP_BYTES=str(self.root / "copied"),
                        TEST_CLIP_MIME=str(self.root / "mime"))

    def store(self, data):
        subprocess.run(["cliphist", "-db-path", self.db, "store"], input=data, check=True)

    def action(self, action, ident=None, success=True):
        argv = [sys.executable, str(BACKEND), action]
        if ident is not None:
            argv.append(str(ident))
        argv.extend(["--db-path", self.db])
        argv.extend(["--wl-copy-path", str(self.bin / "wl-copy")])
        result = subprocess.run(argv, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success)
        return json.loads(result.stdout)

    def test_text_image_exact_delete_wipe_and_cache(self):
        self.assertEqual(self.action("list")["items"], [])
        payloads = [b"first", "accent é\nline\t$`".encode(), PNG]
        for payload in payloads:
            self.store(payload)
        items = self.action("list")["items"]
        self.assertEqual(len(items), 3)
        self.assertTrue(items[0]["image"])
        self.assertFalse(items[1]["image"])
        self.action("select", items[1]["id"])
        self.assertEqual((self.root / "copied").read_bytes(), payloads[1])
        self.assertEqual((self.root / "mime").read_text(), "text/plain;charset=utf-8")
        self.action("select", items[0]["id"])
        self.assertEqual((self.root / "copied").read_bytes(), PNG)
        self.assertEqual((self.root / "mime").read_text(), "image/png")
        self.assertTrue(self.action("thumb", items[0]["id"])["path"].startswith("file:"))
        self.action("clean")
        self.assertEqual(list(self.root.glob("labfy-cliphist-panel-*/*.png")), [])
        self.action("delete", items[1]["id"])
        remaining = self.action("list")["items"]
        self.assertEqual([x["id"] for x in remaining], [items[0]["id"], items[2]["id"]])
        self.action("delete", "999999", success=False)
        self.assertEqual(len(self.action("list")["items"]), 2)
        self.action("wipe")
        self.assertEqual(self.action("list")["items"], [])


if __name__ == "__main__":
    unittest.main()

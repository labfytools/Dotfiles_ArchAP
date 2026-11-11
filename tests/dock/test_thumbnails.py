"""Private, one-shot thumbnail contract; never grabs a desktop during tests."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SOURCE = (Path(__file__).resolve().parents[2] /
          "quickshell/.config/quickshell/labfy-sway/bin/dock-thumbnails.py")
spec = importlib.util.spec_from_file_location("labfy_dock_thumbnails", SOURCE)
thumbs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thumbs)


class ThumbnailContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = mock.patch.dict(os.environ, XDG_RUNTIME_DIR=self.temp.name)
        env.start()
        self.addCleanup(env.stop)
        self.a = {"id": "51", "foreignId": "a" * 32}
        self.b = {"id": "52", "foreignId": "b" * 32}

    def test_strict_window_ids_and_limit(self):
        valid = thumbs.validate(json.dumps([self.a, self.b]))
        self.assertEqual(valid, [("51", "a" * 32), ("52", "b" * 32)])
        for values in ([], [self.a] * 2, [self.a] * 9,
                       [{"id": "../../x", "foreignId": "a" * 32}],
                       [{"id": "51", "foreignId": "../target"}],
                       [{"id": "51", "foreignId": "A" * 32}],
                       [{"id": 51, "foreignId": "a" * 32}],
                       [{"id": "51", "foreignId": "a" * 32, "title": "private"}]):
            with self.subTest(rows=values), self.assertRaises(ValueError):
                thumbs.validate(json.dumps(values))

    def test_approved_ids_only_private_files_and_cleanup(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            folder = Path(argv[argv.index("-dir") + 1])
            self.assertTrue(folder.is_dir())
            self.assertEqual(folder.parent, thumbs.cache_root())
            self.assertEqual(folder.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(argv[argv.index("-ids")+1], "a" * 32 + "," + "b" * 32)
            self.assertEqual(argv[argv.index("-size")+1], "224")
            for ident in ("a" * 32, "b" * 32):
                (folder / (ident + ".png")).write_bytes(thumbs.PNG_MAGIC + b"specimen")
            return mock.Mock(returncode=0)
        with mock.patch.object(thumbs.subprocess, "run", side_effect=runner):
            result = thumbs.capture(json.dumps([self.a, self.b]), tool="/mock/trusted-capture")
        self.assertEqual(set(result["images"]), {"51", "52"})
        self.assertEqual(result["error"], "")
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(uri.startswith(thumbs.cache_root().as_uri())
                            for uri in result["images"].values()))
        thumbs.purge(thumbs.cache_root(), all_dirs=True)
        self.assertEqual(list(thumbs.cache_root().iterdir()), [])

    def test_failure_does_not_leak_files_or_capture_other_windows(self):
        with mock.patch.object(thumbs.subprocess, "run", return_value=mock.Mock(returncode=3)):
            self.assertEqual(thumbs.capture(json.dumps([self.a]), tool="/mock/fail")["images"], {})
        self.assertEqual(list(thumbs.cache_root().iterdir()), [])

    def test_invalid_and_symlink_cache_refused(self):
        root = thumbs.cache_root()
        root.rmdir()
        root.symlink_to(Path(self.temp.name))
        with self.assertRaises(ValueError):
            thumbs.cache_root()


if __name__ == "__main__":
    unittest.main()

"""Permission and diagnostic regressions with synthetic files only."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[2]/'quickshell/.config/quickshell/labfy-sway/clipboard/backend.py'
spec=importlib.util.spec_from_file_location('clipboard_privacy',SOURCE)
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class Privacy(unittest.TestCase):
    def test_database_mode_is_tightened_without_content_change(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'db';p.write_bytes(b'TEST_ONLY');p.chmod(0o644)
            b.command(str(p),'list')
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            self.assertEqual(p.read_bytes(),b'TEST_ONLY')

    def test_symlink_database_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'sentinel';target.write_bytes(b'TEST_ONLY');target.chmod(0o644)
            db=Path(directory)/'db';db.symlink_to(target)
            r=subprocess.run([sys.executable,'-B',str(SOURCE),'list','--db-path',str(db)],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertNotIn('TEST_ONLY',r.stdout+r.stderr)
            self.assertNotIn(str(target),r.stdout+r.stderr)
            self.assertEqual(target.stat().st_mode&0o777,0o644)

    def test_thumbnail_symlink_and_insecure_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict(os.environ,LABFY_CLIPHIST_TEST_CACHE_DIR=directory):
                (root/('labfy-cliphist-panel-'+str(os.getuid()))).symlink_to(root,target_is_directory=True)
                with self.assertRaises((RuntimeError,OSError)):b.cache_dir()
            root.chmod(0o755)
            with patch.dict(os.environ,LABFY_CLIPHIST_TEST_CACHE_DIR=directory):
                with self.assertRaises((RuntimeError,OSError)):b.cache_dir()

if __name__=='__main__':unittest.main()

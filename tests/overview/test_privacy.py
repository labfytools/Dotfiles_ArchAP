"""Synthetic cache/IPC only: never inspect or capture personal windows."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('overview_privacy',Path(__file__).resolve().parents[2]/'quickshell/.config/quickshell/labfy-sway/overview/backend.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class Privacy(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        e=patch.dict(os.environ,XDG_RUNTIME_DIR=self.temp.name,XDG_CONFIG_HOME=self.temp.name)
        e.start();self.addCleanup(e.stop)
        old=os.umask(0o077);self.addCleanup(os.umask,old)
        self.window={'id':42,'app':'TEST_ONLY','foreignId':'b'*32}
        self.model={'cards':[{'number':1,'windows':[self.window]}]}

    def write_policy(self,value):
        p=self.root/'labfy-sway/overview-capture.json';p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(value))

    def test_no_capture_when_closed(self):
        with patch.object(b,'overview_open',return_value=False),patch.object(b.subprocess,'run',side_effect=AssertionError('capture while closed')):
            self.assertEqual(b.capture_windows({1})['captured'],[])

    def test_disabled_policy_and_exclusions_do_not_reach_grim(self):
        for rules in [{'enabled':False},{'excludeApps':['TEST_*']}]:
            self.write_policy(rules)
            with patch.object(b,'overview_open',return_value=True),patch.object(b,'state',return_value=self.model),patch.object(b.subprocess,'run',side_effect=AssertionError('excluded capture')):
                self.assertEqual(b.capture_windows({1})['captured'],[])

    def test_invalid_policy_fails_closed(self):
        self.write_policy({'enabled':'yes'})
        self.assertFalse(b.policy()['enabled'])
        p=self.root/'labfy-sway/overview-capture.json';p.unlink();p.symlink_to('/dev/zero')
        self.assertFalse(b.policy()['enabled'])

    def test_directory_symlink_and_insecure_mode_rejected(self):
        outside=self.root/'outside';outside.mkdir();target=self.root/'labfy-workspace-overview'
        target.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError):b.cache_dir()
        target.unlink();target.mkdir(mode=0o755);target.chmod(0o755)
        with self.assertRaises(RuntimeError):b.cache_dir()
        self.assertEqual(target.stat().st_mode&0o777,0o755)

    def test_symlink_manifest_and_image_never_followed(self):
        sentinel=self.root/'sentinel';sentinel.write_bytes(b'KEEP')
        b.window_preview_path(42).symlink_to(sentinel)
        self.assertIsNone(b.valid_window_preview(42,'b'*32))
        b.purge()
        self.assertEqual(sentinel.read_bytes(),b'KEEP')

    def test_purge_does_not_touch_unrecognized_files(self):
        c=b.cache_dir();(c/'unrelated.txt').write_text('KEEP');(c/'window-1.jpg').write_bytes(b'JPEG')
        b.purge();self.assertTrue((c/'unrelated.txt').exists());self.assertFalse((c/'window-1.jpg').exists())

    def test_count_and_byte_quotas(self):
        c=b.cache_dir()
        for i in range(6):(c/f'window-{i}.jpg').write_bytes(b'x'*8)
        with patch.object(b,'MAX_CACHE_FILES',4),patch.object(b,'MAX_CACHE_BYTES',16):b.enforce_quota()
        files=list(c.glob('*.jpg'));self.assertLessEqual(len(files),4);self.assertLessEqual(sum(p.stat().st_size for p in files),16)

    def test_lock_during_capture_rejects_pixels_and_reaps_temporary(self):
        def grim(args,**kwargs):
            Path(args[-1]).write_bytes(b'JPEG')
            (self.root/'labfy-lock.capture-guard').write_text('active\n')
            return subprocess.CompletedProcess(args,0)
        with patch.object(b,'overview_open',return_value=True),patch.object(b,'state',return_value=self.model),patch.object(b.subprocess,'run',side_effect=grim):
            self.assertEqual(b.capture_windows({1})['captured'],[])
        self.assertFalse(list(b.cache_dir().glob('*.jpg')))

    def test_capture_timeout_cleans_temporary(self):
        with patch.object(b,'overview_open',return_value=True),patch.object(b,'state',return_value=self.model),patch.object(b.subprocess,'run',side_effect=subprocess.TimeoutExpired('grim',2)):
            self.assertEqual(b.capture_windows({1})['captured'],[])
        self.assertFalse(list(b.cache_dir().glob('tmp*')))

    def test_policy_change_purges_excluded_cached_window(self):
        rect={'x':0,'y':0,'width':100,'height':100}
        node={'type':'workspace','id':1,'num':1,'nodes':[dict(type='con',id=42,app_id='TEST_ONLY',rect=rect)],'rect':rect}
        data={'get_tree':node,'get_workspaces':[dict(id=1,num=1,output='HEADLESS-1')],'get_outputs':[]}
        (b.cache_dir()/'window-42.jpg').write_bytes(b'JPEG')
        self.write_policy({'excludeApps':['TEST_ONLY']})
        with patch.object(b,'sway',side_effect=lambda kind:data[kind]):
            row=b.state()['cards'][0]['windows'][0]
        self.assertTrue(row['excluded']);self.assertEqual(row['preview'],'');self.assertFalse((b.cache_dir()/'window-42.jpg').exists())

    def test_lock_epoch_invalidates_previous_preview(self):
        p=b.window_preview_path(42);p.write_bytes(b'JPEG')
        b.window_preview_metadata_path(42).write_text(json.dumps(dict(version=1,conId=42,foreignId='b'*32,lockRevision=[],capturedNs=1,imageMtimeNs=p.stat().st_mtime_ns)))
        self.assertIsNotNone(b.valid_window_preview(42,'b'*32))
        (self.root/'labfy-lock.capture-guard').write_text('released\n')
        self.assertIsNone(b.valid_window_preview(42,'b'*32))

if __name__=='__main__':unittest.main()

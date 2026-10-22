import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


class UserUpdateTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('user_update', ROOT/'scripts/mosaic-user-update.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);m=self.m;m.UID=os.getuid();m.ALIASES={}
        m.SOURCE=self.root/'source';m.SOURCE.mkdir()
        units=self.root/'units';units.mkdir();m.WANTS=units/'target.wants'
        m.STATE=self.root/'durable';m.STATE.mkdir(mode=0o700)
        m.TARGETS={key:((m.WANTS/'quickshell-labfy-mosaic.service' if key=='wants' else units/key),mode,source) for key,(_,mode,source) in m.TARGETS.items()}
        for key,(path,mode,source) in m.TARGETS.items():
            if key in ('session','manifest','qml'):
                path.write_text('old:'+key);path.chmod(mode)
            if source:
                candidate=m.SOURCE/source;candidate.parent.mkdir(parents=True,exist_ok=True)
                candidate.write_text('new:'+key)
        self.bundle=m.STATE/'bundle';m.prepare(self.bundle)

    def assert_state(self,kind):
        manifest,_,current=self.m.check(self.bundle)
        for key in self.m.TARGETS:self.assertEqual(current[key],manifest['files'][key][kind])

    def test_durable_barrier_failure_never_publishes_or_rolls_back(self):
        original = os.fsync
        for failed in (self.bundle/'mosaic-user-update.py', self.bundle.parent):
            with self.subTest(failed=failed):
                def sync(fd):
                    if Path(os.readlink('/proc/self/fd/'+str(fd))) == failed:
                        raise OSError('barrier failure')
                    return original(fd)
                with patch.object(os,'fsync',side_effect=sync), patch.object(self.m,'publish') as publish:
                    with self.assertRaises(OSError):self.m.transact(self.bundle,'apply')
                    publish.assert_not_called()
                self.assert_state('old')
                self.assertFalse((self.bundle/'state').exists())

    def test_real_apply_rollback_idempotence(self):
        for operation,kind in [('apply','new'),('apply','new'),('rollback','old'),('rollback','old')]:
            self.m.transact(self.bundle,operation);self.assert_state(kind)
        self.assertFalse(self.m.WANTS.exists())

    def test_error_after_second_file_restores_all(self):
        original=self.m.write;count=[0]
        def fail(path,*args,**kw):
            if path in [row[0] for row in self.m.TARGETS.values()]:
                count[0]+=1
                if count[0]==2:raise OSError('synthetic write failure')
            return original(path,*args,**kw)
        with patch.object(self.m,'write',side_effect=fail),self.assertRaises(OSError):self.m.transact(self.bundle,'apply')
        self.assert_state('old')
        self.assertEqual((self.bundle/'state').read_text(),'original\n')

    def test_crash_after_each_file_and_activation_link_recovers(self):
        # Vrais rename et vraie mort sans finally : couvre aussi l'ultime lien wants.
        for stop in range(1,7):
            with self.subTest(rename=stop):
                pid=os.fork()
                if pid==0:
                    original=os.replace;count=[0]
                    def die(src,dst,*args,**kw):
                        original(src,dst,*args,**kw)
                        if Path(dst) in [row[0] for row in self.m.TARGETS.values()]:
                            count[0]+=1
                            if count[0]==stop:os._exit(77)
                    os.replace=die
                    try:self.m.transact(self.bundle,'apply')
                    finally:os._exit(78)
                _,status=os.waitpid(pid,0);self.assertEqual(os.waitstatus_to_exitcode(status),77)
                self.assertEqual((self.bundle/'state').read_text(),'applying\n')
                with self.assertRaisesRegex(ValueError,'Interruption restaurée'):self.m.transact(self.bundle,'apply')
                self.assert_state('old')
        self.m.transact(self.bundle,'apply');self.m.transact(self.bundle,'rollback');self.assert_state('old')

    def test_drift_and_corrupted_backup_prevent_any_publication(self):
        target=self.m.TARGETS['qml'][0];original=target.read_bytes();target.write_text('outside')
        with self.assertRaisesRegex(ValueError,'divergente'):self.m.transact(self.bundle,'apply')
        self.assertFalse(self.m.TARGETS['service'][0].exists());target.write_bytes(original)
        backup=self.bundle/'qml.old';backup.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'SHA'):self.m.transact(self.bundle,'rollback')
        self.assertEqual(self.m.TARGETS['session'][0].read_text(),'old:session')

    def test_symlink_mode_and_missing_parent_refused(self):
        path=self.m.TARGETS['session'][0];data=path.read_bytes();path.chmod(0o644)
        with self.assertRaises(ValueError):self.m.check(self.bundle)
        path.chmod(0o600);path.unlink();path.symlink_to(self.m.TARGETS['qml'][0])
        with self.assertRaises((ValueError,OSError)):self.m.check(self.bundle)
        path.unlink();path.write_bytes(data);path.chmod(0o600)
        self.m.WANTS.symlink_to(self.root/'does-not-exist')
        with self.assertRaises(ValueError):self.m.check(self.bundle)

    def test_closed_manifest_scope_and_metadata(self):
        path=self.bundle/'manifest.json';original=path.read_bytes();obj=json.loads(original)
        obj['files']['escape']=obj['files']['qml'];path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):self.m.check(self.bundle)
        path.write_bytes(original);obj=json.loads(original);obj['files']['qml']['new']['mode']=0o777
        path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):self.m.check(self.bundle)

    def test_main_durable_lock_and_lab_independence(self):
        import shutil
        shutil.rmtree(self.m.SOURCE)
        for operation in ('apply','rollback'):
            with patch.object(sys,'argv',['mosaic-user-update.py',operation,str(self.bundle)]):self.m.main()
        self.assert_state('old')

    def test_main_rejects_nondurable_location(self):
        with patch.object(sys,'argv',['mosaic-user-update.py','apply',str(self.root/'nondurable')]),self.assertRaises(SystemExit):self.m.main()


if __name__=='__main__':unittest.main()

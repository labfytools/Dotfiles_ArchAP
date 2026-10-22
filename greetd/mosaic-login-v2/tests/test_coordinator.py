import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_user_update as user_tests

ROOT=Path(__file__).resolve().parents[2]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture=user_tests.UserUpdateTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.user=self.fixture.m;self.ub=self.fixture.bundle;self.root=self.fixture.root
        self.rt=module('root_tool',ROOT/'scripts/session-update.py');self.rt.OWNER=os.getuid()
        self.rb=self.root/'root-bundle';self.rb.mkdir(mode=0o700)
        installed=self.root/'installed';installed.mkdir()
        self.rt.TARGETS={key:installed/key for key in self.rt.TARGETS};self.rt.ORIGINALS={}
        manifest={'version':1,'files':{}}
        for name,path in self.rt.TARGETS.items():
            old,new=('old:'+name).encode(),('new:'+name).encode();path.write_bytes(old);path.chmod(0o644)
            for kind,data in [('old',old),('new',new)]:
                target=self.rb/(name+'.'+kind);target.write_bytes(data);target.chmod(0o600)
            self.rt.ORIGINALS[name]=self.rt.digest(old)
            manifest['files'][name]={'old':self.rt.digest(old),'new':self.rt.digest(new)}
        self.rt.atomic_write(self.rb/'manifest.json',(json.dumps(manifest)+'\n').encode(),0o600)
        self.co=module('coordinator',ROOT/'scripts/login-recovery-update.py')
        for name in ('session-update.py', 'login-recovery-update.py'):
            self.rt.atomic_write(self.rb/name,(ROOT/'scripts'/name).read_bytes(),0o600)
        for name in ('user-seal.json','protected.json'):
            self.rt.atomic_write(self.rb/name,b'{}\n',0o600)

        self.guard=patch.object(self.rt,'trusted_parents');self.guard.start();self.addCleanup(self.guard.stop)
        def user_action(bundle,op):
            if op=='check':self.user.check(bundle)
            elif op=='durable-barrier':self.user.durable_bundle(bundle)
            else:self.user.transact(bundle,op)
        self.ua=user_action
        self.up=patch.object(self.co,'user_action',side_effect=user_action);self.up.start();self.addCleanup(self.up.stop)

    def assert_both(self,kind):
        self.fixture.assert_state(kind)
        for name,path in self.rt.TARGETS.items():self.assertEqual(path.read_bytes(),(kind+':'+name).encode())

    def call(self,operation):self.co.coordinate(self.rb,operation,self.rt,self.ub)

    def test_barriers_cover_both_bundles_before_first_publication(self):
        original_sync, original_replace = os.fsync, os.replace
        synced = set(); published = []
        required = {p for bundle in (self.rb,self.ub) for p in bundle.iterdir()}
        required.update(p for bundle in (self.rb,self.ub) for p in (bundle,*bundle.parents))
        targets = set(self.rt.TARGETS.values()) | {row[0] for row in self.user.TARGETS.values()}
        def sync(fd):
            result = original_sync(fd)
            synced.add(Path(os.readlink('/proc/self/fd/'+str(fd))))
            return result
        def replace(src,dst,*args,**kwargs):
            if Path(dst) in targets:
                self.assertTrue(required <= synced, str(required-synced))
                published.append(Path(dst))
            return original_replace(src,dst,*args,**kwargs)
        with patch.object(os,'fsync',side_effect=sync),patch.object(os,'replace',side_effect=replace):
            self.call('apply')
        self.assertTrue(published);self.assert_both('new')

    def test_either_barrier_failure_changes_zero_targets(self):
        original = os.fsync
        for failed in (self.rb/'session-update.py',self.rb/'login-recovery-update.py',
                       self.rb/'user-seal.json',self.rb/'protected.json',self.rb.parent,
                       self.ub/'mosaic-user-update.py',self.ub.parent):
            with self.subTest(failed=failed):
                def sync(fd):
                    if Path(os.readlink('/proc/self/fd/'+str(fd))) == failed:
                        raise OSError('barrier failure')
                    return original(fd)
                with patch.object(os,'fsync',side_effect=sync),patch.object(self.rt,'publish') as rp,patch.object(self.user,'publish') as up:
                    with self.assertRaises(OSError):self.call('apply')
                    rp.assert_not_called();up.assert_not_called()
                self.assert_both('old')
                self.assertFalse((self.rb/'batch-state').exists())
                self.assertFalse((self.rb/'state').exists())
                self.assertFalse((self.ub/'state').exists())

    def test_coordinated_apply_rollback_and_idempotence(self):
        for op,kind in [('apply','new'),('apply','new'),('rollback','old'),('rollback','old')]:
            self.call(op);self.assert_both(kind)

    def test_root_error_rolls_back_user_and_root(self):
        original=self.rt.transact
        def fail(bundle,operation):
            if operation=='apply':raise OSError('synthetic root failure')
            return original(bundle,operation)
        with patch.object(self.rt,'transact',side_effect=fail),self.assertRaises(OSError):self.call('apply')
        self.assert_both('old');self.assertEqual((self.rb/'batch-state').read_text(),'original\n')

    def test_kill_between_user_and_root_then_recover_both(self):
        for boundary in ('after-user','after-root'):
            with self.subTest(boundary=boundary):
                pid=os.fork()
                if pid==0:
                    try:
                        if boundary=='after-user':
                            def die(bundle,op):
                                self.ua(bundle,op)
                                if op=='apply':os._exit(77)
                            self.co.user_action=die
                        else:
                            original=self.rt.transact
                            def die(bundle,op):
                                original(bundle,op)
                                if op=='apply':os._exit(77)
                            self.rt.transact=die
                        self.call('apply')
                    finally:os._exit(78)
                _,status=os.waitpid(pid,0);self.assertEqual(os.waitstatus_to_exitcode(status),77)
                self.assertEqual((self.rb/'batch-state').read_text(),'applying\n')
                with self.assertRaisesRegex(ValueError,'Lot interrompu restauré'):self.call('apply')
                self.assert_both('old')

    def test_failed_root_rollback_still_restores_user_and_keeps_journal(self):
        self.call('apply')
        with patch.object(self.rt,'transact',side_effect=OSError('root unavailable')),self.assertRaisesRegex(ValueError,'Rollback incomplet'):self.call('rollback')
        self.fixture.assert_state('old')
        self.assertEqual((self.rb/'batch-state').read_text(),'rolling-back\n')
        self.call('rollback');self.assert_both('old')

    def test_user_seal_checks_real_bytes(self):
        seal={p.name:self.rt.digest(p.read_bytes()) for p in self.ub.iterdir() if p.name not in ('state',)}
        self.rt.atomic_write(self.rb/'user-seal.json',(json.dumps(seal)+'\n').encode(),0o600)
        self.co.seal_user(self.rb,self.ub,self.rt)
        (self.ub/'qml.new').write_text('corruption')
        with self.assertRaisesRegex(ValueError,'divergent'):self.co.seal_user(self.rb,self.ub,self.rt)

    def test_global_apply_refused_without_root_or_durable_paths(self):
        with patch.object(sys,'argv',['login-recovery-update.py','apply',str(self.rb),str(self.ub)]),self.assertRaises(SystemExit):self.co.main()
        self.assert_both('old')


if __name__=='__main__':unittest.main()

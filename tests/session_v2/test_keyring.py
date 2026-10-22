"""Real Gio client against a private mock bus; never accesses the desktop bus."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from common import BACKEND, REPO, Path, os, sys
from session_v2 import keyring, cli
from session_v2.errors import Failure
from session_v2.storage import private_dir, lock


class KeyringTests(unittest.TestCase):
    @contextlib.contextmanager
    def service(self, mode):
        with tempfile.TemporaryDirectory(prefix='labfy-keyring-TEST_ONLY-') as tmp:
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
            for name in ('HOME', 'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME'):
                path = Path(tmp) / name; path.mkdir(mode=0o700); env[name] = str(path)
            # No standard service directories: an "absent" fixture must not
            # accidentally activate the installed real GNOME Keyring daemon.
            config = Path(tmp) / 'bus.conf'
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + tmp + '</listen>'
                '<auth>EXTERNAL</auth><policy context="default"><allow own="*"/>'
                '<allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>')
            daemon = subprocess.Popen(['dbus-daemon', '--config-file=' + str(config), '--nofork', '--print-address=1'],
                                      env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            server = None
            try:
                address = daemon.stdout.readline().strip()
                env['DBUS_SESSION_BUS_ADDRESS'] = address
                if mode != 'absent':
                    server = subprocess.Popen([sys.executable, '-B', str(REPO / 'tests/session_v2/fixtures/secret_service.py'), mode],
                                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual(server.stdout.readline().strip(), 'READY')
                with patch.dict(os.environ, env, clear=True):
                    yield env, server
            finally:
                for proc in (server, daemon):
                    if proc is not None:
                        proc.terminate()
                        try: proc.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill(); proc.communicate(timeout=5)
                            raise

    def test_actual_dbus_states(self):
        cases = [('ready', False, 'READY'), ('locked', False, 'LOCKED'),
                 ('accept', True, 'READY'), ('immediate', True, 'READY'),
                 ('cancel', True, 'CANCELLED'), ('still-locked', True, 'LOCKED'),
                 ('wrong-password', True, 'UNAVAILABLE'), ('timeout', True, 'UNAVAILABLE'),
                 ('absent', False, 'UNAVAILABLE'), ('missing', False, 'UNAVAILABLE'),
                 ('different', False, 'UNAVAILABLE'), ('login-different', False, 'UNAVAILABLE'),
                 ('dbus-timeout', False, 'UNAVAILABLE'), ('error', False, 'UNAVAILABLE')]
        for mode, unlock, expected in cases:
            with self.subTest(mode=mode), self.service(mode):
                value = keyring.check(unlock, timeout=.15)
                self.assertEqual(value['state'], 'KEYRING_' + expected, value)
                self.assertEqual(set(value), {'state', 'reason'})
                if mode == 'absent':
                    owner = subprocess.run(['busctl', '--address=' + os.environ['DBUS_SESSION_BUS_ADDRESS'],
                        'call', 'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                        'NameHasOwner', 's', keyring.BUS], capture_output=True, text=True, timeout=5)
                    self.assertEqual(owner.stdout.strip(), 'b false')

    def test_two_processes_and_restart(self):
        with self.service('timeout') as (env, server):
            argv = [sys.executable, '-B', str(BACKEND / 'session-v2.py'), 'keyring-unlock', '--execute']
            child = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(server.stdout.readline().strip(), 'UNLOCK')
                self.assertEqual(server.stdout.readline().strip(), 'PROMPT')
                # A new QuickShell/CLI must discover busy from the kernel lock.
                status = subprocess.run([*argv[:3], 'keyring-status'], env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(json.loads(status.stdout)['state'], 'KEYRING_UNLOCKING')
                duplicate = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(json.loads(duplicate.stdout)['state'], 'KEYRING_UNLOCKING')
                runtime = Path(env['XDG_RUNTIME_DIR']) / 'labfy-sway'
                from session_v2.startup import acknowledge
                self.assertEqual(acknowledge(runtime, 'TEST_ONLY', 'new')['choice'], 'new')
            finally:
                child.terminate()
                try: child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill(); child.communicate(timeout=5)
                    raise
            status = subprocess.run([*argv[:3], 'keyring-status'], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(json.loads(status.stdout)['state'], 'KEYRING_LOCKED')
            # No readiness/cache/secret persists; only private lock and startup decision.
            files = list((Path(env['XDG_RUNTIME_DIR']) / 'labfy-sway').rglob('*'))
            self.assertTrue(all(p.name in ('session-v2', 'keyring.lock', 'transaction.lock', 'startup.json') for p in files))

    def test_apply_last_cannot_bypass_gate(self):
        with self.service('locked'):
            with patch.object(cli, 'Store') as store, patch.object(cli, 'Sway'), \
                 patch.object(cli, 'Catalog'), patch.object(cli, 'FirefoxProvider'), \
                 patch.object(cli, 'Executor') as executor, contextlib.redirect_stdout(io.StringIO()) as out:
                store.return_value.last.return_value = {}
                self.assertEqual(cli.main(['apply-last', '--execute']), 2)
                self.assertEqual(json.loads(out.getvalue())['reason'], 'KEYRING_LOCKED')
                executor.assert_not_called()

    def test_ready_preserves_executor_result_and_recovery_required(self):
        for code in (None, 'RECOVERY_REQUIRED', 'RECOVERY_FOCUS_MISMATCH'):
            with self.subTest(code=code), self.service('ready'):
                with patch.object(cli, 'Store'), patch.object(cli, 'Sway'), patch.object(cli, 'Catalog'), \
                     patch.object(cli, 'FirefoxProvider'), patch.object(cli, 'Executor') as executor, \
                     contextlib.redirect_stdout(io.StringIO()) as out:
                    if code: executor.return_value.apply.side_effect = Failure(code)
                    else: executor.return_value.apply.return_value = {'status': 'TEST_ONLY_EXECUTOR_RESULT'}
                    rc = cli.main(['apply-last', '--execute'])
                    self.assertEqual(rc, 2 if code else 0)
                    self.assertEqual(json.loads(out.getvalue()), {'status': 'failed', 'reason': code} if code else {'status': 'TEST_ONLY_EXECUTOR_RESULT'})
                    executor.return_value.apply.assert_called_once()

    def test_unlock_never_restores(self):
        with self.service('accept'):
            with patch.object(cli, 'Executor') as executor, contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(['keyring-unlock', '--execute']), 0)
                self.assertEqual(json.loads(out.getvalue())['state'], 'KEYRING_READY')
                executor.assert_not_called()

    def test_remote_error_text_is_never_logged_or_persisted(self):
        with self.service('error') as (env, _):
            value = subprocess.run([sys.executable, '-B', str(BACKEND / 'session-v2.py'), 'keyring-status'],
                                   env=env, capture_output=True, text=True, timeout=10)
            self.assertNotIn('TEST_ONLY_SENSITIVE_SENTINEL', value.stdout + value.stderr)
            self.assertEqual(json.loads(value.stdout)['state'], 'KEYRING_UNAVAILABLE')
            for path in Path(env['XDG_RUNTIME_DIR']).rglob('*'):
                if path.is_file(): self.assertNotIn(b'TEST_ONLY_SENSITIVE_SENTINEL', path.read_bytes())

    def test_apply_is_excluded_during_unlock(self):
        with self.service('ready') as (env, _):
            runtime = private_dir(Path(env['XDG_RUNTIME_DIR']) / 'labfy-sway')
            with keyring.admission(runtime), patch.object(cli, 'Store'), patch.object(cli, 'Sway'), \
                 patch.object(cli, 'Catalog'), patch.object(cli, 'FirefoxProvider'), \
                 patch.object(cli, 'Executor') as executor, contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(['apply-last', '--execute']), 2)
                self.assertEqual(json.loads(out.getvalue())['reason'], 'TRANSACTION_BUSY')
                executor.assert_not_called()

    def test_transaction_prevents_prompt(self):
        with self.service('locked') as (env, server):
            runtime = private_dir(Path(env['XDG_RUNTIME_DIR']) / 'labfy-sway')
            with lock(private_dir(runtime / 'session-v2')):
                self.assertEqual(keyring.command(runtime, True)['state'], 'KEYRING_UNLOCKING')
            self.assertEqual(keyring.check()['state'], 'KEYRING_LOCKED')


if __name__ == '__main__': unittest.main()

"""Watchdog réel sur socketpair/pipes possédés ; aucun signal de session."""
import threading
import socket
import tempfile
import unittest
from unittest.mock import patch
from common import *
from session_v2.guard import run
from session_v2.storage import atomic, loads


class GuardProtocolTests(unittest.TestCase):
    def exercise(self, messages):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)/'attempt.json'
            atomic(report, {'status': 'running', 'anchors_cleaned': 0})
            parent, child = socket.socketpair(type=socket.SOCK_SEQPACKET)
            parent.settimeout(5)
            engine_r, engine_w = os.pipe()
            anchor_r, anchor_w = os.pipe()
            writer_r, writer_w = os.pipe()
            rows, replies, errors = [], [], []
            def helper():
                # A real pipe models the quit consumed before process exit.
                rows.append(('quit', os.read(writer_r, 64)))
                os.close(anchor_w)
            worker = threading.Thread(target=helper)
            worker.start()
            config = dict(control=child.detach(), engine_fd=engine_r, anchor_fd=anchor_r,
                          writer_fd=writer_w, anchor_pid=99999999, allowed=[], helpers=[],
                          socket='/TEST_ONLY', report=str(report), deadline=5)
            class Sway:
                def __init__(self, path): pass
                def windows(self): return []
            def resume(*args): rows.append(('resume', None)); return True
            def guarded():
                try: run(config)
                except BaseException as exc: errors.append(exc)
            try:
                with patch('session_v2.guard.Sway', Sway), \
                     patch('session_v2.guard.resume_helpers', side_effect=resume), \
                     patch('session_v2.guard.signal.pidfd_send_signal'), \
                     patch('session_v2.guard.resume_pending') as recovery:
                    guard = threading.Thread(target=guarded)
                    guard.start()
                    replies.append(loads(parent.recv(4096)))
                    for message in messages:
                        parent.sendall(message)
                        replies.append(loads(parent.recv(4096)))
                        if message == b'prepare':
                            self.assertEqual(replies[-1]['status'], 'prepared')
                            self.assertEqual(rows, [('quit', b'quit\n')])
                        if message == b'resume' and b'prepare' in messages:
                            self.assertEqual(replies[-1]['status'], 'resumed')
                    guard.join(5)
                    self.assertFalse(guard.is_alive())
                    self.assertEqual(errors, [])
                    if messages == [b'prepare', b'resume', b'finish']: recovery.assert_not_called()
            finally:
                parent.close()
                worker.join(5)
                for fd in (engine_r, engine_w, anchor_r, writer_r): os.close(fd)
            if b'prepare' in messages: self.assertEqual(rows[0], ('quit', b'quit\n'))
            return replies

    def test_prepare_quits_before_resume_and_finish_has_no_delayed_exit(self):
        replies = self.exercise([b'prepare', b'resume', b'finish'])
        self.assertEqual([r['status'] for r in replies], ['ready', 'prepared', 'resumed', 'finished'])

    def test_resume_without_prepare_refuses_and_still_cleans_owned_helper(self):
        self.assertEqual(self.exercise([b'resume'])[-1]['status'], 'failed')


if __name__ == '__main__': unittest.main()

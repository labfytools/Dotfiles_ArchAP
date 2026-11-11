"""TEST_ONLY: late ChatGPT X11 window remapping during prewarm.

An old con_id may be replaced before the transaction. Never admit the
transient leaf, and never relax identities after Recovery starts.
"""
import copy
import time
import unittest
from unittest.mock import Mock

from common import *
from session_v2.executor import Executor
from session_v2.errors import Failure


class StartupX11StabilityTests(unittest.TestCase):
    @staticmethod
    def state(ident, app, ws, pid):
        return {
            "con_id": ident, "app_id": app, "pid": pid,
            "starttime": "123", "workspace": ws, "output": "HEADLESS-1",
            "path": [0], "floating": False, "geometry": None,
            "scratchpad": "none",
        }

    def setUp(self):
        self.sway = Mock(session="a" * 64)
        self.engine = Executor.__new__(Executor)
        self.engine.sway = self.sway
        self.base = {5: self.state(5, "limusic-app", "10", 500)}
        self.spec = Spec("chatgpt", "chatgpt.desktop",
                         ("x11-class:Chatgpt",), "single-window",
                         ("/usr/bin/chatgpt",))
        self.allowed = {"limusic-app", "x11-class:Chatgpt"}

    def test_late_remap_is_reobserved_before_pinning(self):
        started = time.monotonic()
        def sample():
            elapsed = time.monotonic() - started
            con_id = 17 if elapsed < .07 else 32
            return {**copy.deepcopy(self.base),
                    con_id: self.state(con_id, "x11-class:Chatgpt", "1", 753170)}
        self.engine._observe_prepared = sample
        result = self.engine._settle_fresh_chatgpt(
            self.base, self.spec, self.sway.session, self.allowed,
            .7, minimum_age=.22, stable_for=.09)
        self.assertIn(32, result)
        self.assertNotIn(17, result)
        self.sway.command.assert_not_called()

    def test_preexisting_client_change_is_never_accepted(self):
        def sample():
            d = copy.deepcopy(self.base)
            d[5]["pid"] = 501
            d[17] = self.state(17, "x11-class:Chatgpt", "1", 753170)
            return d
        self.engine._observe_prepared = sample
        with self.assertRaisesRegex(Failure, "TARGET_OBSERVATION_CHANGED"):
            self.engine._settle_fresh_chatgpt(
                self.base, self.spec, self.sway.session, self.allowed,
                .4, minimum_age=.1, stable_for=.05)

    def test_unknown_new_application_is_not_admitted(self):
        self.engine._observe_prepared = lambda: {
            **copy.deepcopy(self.base),
            17: self.state(17, "x11-class:Chatgpt", "1", 753170),
            99: self.state(99, "intruder", "2", 999),
        }
        with self.assertRaisesRegex(Failure, "APPLICATION_MEMBERSHIP_CHANGED"):
            self.engine._settle_fresh_chatgpt(
                self.base, self.spec, self.sway.session, self.allowed,
                .3, minimum_age=.1, stable_for=.05)

    def test_incomplete_settle_deferred_before_transaction(self):
        self.engine._observe_prepared = lambda: {
            **copy.deepcopy(self.base),
            17: self.state(17, "x11-class:Chatgpt", "1", 753170),
        }
        with self.assertRaisesRegex(Failure, "APPLICATION_WINDOWS_INCOMPLETE"):
            self.engine._settle_fresh_chatgpt(
                self.base, self.spec, self.sway.session, self.allowed,
                .08, minimum_age=.3, stable_for=.05)
        self.sway.command.assert_not_called()


if __name__ == "__main__":
    unittest.main()

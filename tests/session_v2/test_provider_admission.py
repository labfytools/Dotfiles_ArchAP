"""Provider admission before Recovery/staging; inert windows and private journals."""
import tempfile
import unittest
from unittest.mock import patch
from common import *
from login_focus import checkpoint, UUID
from test_prewarm import Sway, Provider
from session_v2.errors import Deferred, Failure
from session_v2.executor import Executor
from session_v2.ipc import walk, workspace
from session_v2.recovery import Recovery, JOURNAL, RECEIPT, focus_proof


class ProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)
        self.sway = Sway()
        self.sway.add("kitty", 20, focus=False)
        self.sway.add("firefox", 21)
        self.provider = Provider()
        self.engine = Executor(self.sway, Catalog(), self.provider, self.runtime, "/forbidden")
        self.data = checkpoint()
        launch = patch("session_v2.executor.launch", side_effect=AssertionError("NO_LAUNCH_EXPECTED"))
        launch.start()
        self.addCleanup(launch.stop)

    def assert_no_transaction(self):
        self.assertEqual(self.sway.commands, [])
        self.assertFalse((self.runtime / JOURNAL).exists())
        self.assertFalse((self.runtime / "session-v2-restore-attempt.json").exists())

    def test_unavailable_is_deferred_before_mutation_and_durable_attempt(self):
        with patch.object(self.provider, "resolve", side_effect=Failure("FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")), \
             patch.object(self.engine, "_apply", side_effect=AssertionError("ADMISSION_REQUIRED")):
            with self.assertRaisesRegex(Deferred, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE"):
                self.engine.apply(self.data, True)
        self.assert_no_transaction()

    def test_exact_uuid_missing_is_not_relabelled_transient(self):
        with patch.object(self.provider, "resolve", side_effect=Failure("EXACT_WINDOW_IDENTITY_MISSING")), \
             patch.object(self.engine, "_apply", side_effect=AssertionError("ADMISSION_REQUIRED")):
            with self.assertRaisesRegex(Failure, "EXACT_WINDOW_IDENTITY_MISSING") as result:
                self.engine.apply(self.data, True)
            self.assertNotIsInstance(result.exception, Deferred)
        self.assert_no_transaction()

    def test_partial_provider_mapping_never_admits_the_batch(self):
        with patch.object(self.provider, "resolve", return_value={UUID: 999}), \
             patch.object(self.engine, "_apply", side_effect=AssertionError("ADMISSION_REQUIRED")):
            with self.assertRaisesRegex(Deferred, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE"):
                self.engine.apply(self.data, True)
        self.assert_no_transaction()

    def test_success_rechecks_complete_batch_and_focus_before_apply(self):
        resolved = []
        def resolve(expected, nodes, timeout):
            self.assertEqual(expected, {UUID})
            self.assertEqual([n["id"] for n in nodes], [21])
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 6)
            self.assert_no_transaction()
            resolved.append(True)
            return {UUID: 21}
        def admitted(data, timeout, lock_fd, proof, prepared):
            self.assertEqual(resolved, [True])
            self.assertEqual(set(prepared), {5, 20, 21})
            self.assertEqual(proof, focus_proof(self.sway))
            self.assert_no_transaction()
            return "admitted"
        with patch.object(self.provider, "resolve", side_effect=resolve), \
             patch.object(self.engine, "_apply", side_effect=admitted):
            self.assertEqual(self.engine.apply(self.data, True), "admitted")

    def test_changes_during_provider_wait_are_refused_before_apply(self):
        for change, reason in (
            ("identity", "TARGET_OBSERVATION_CHANGED"),
            ("new-window", "APPLICATION_MEMBERSHIP_CHANGED"),
            ("order", "TARGET_OBSERVATION_CHANGED"),
            ("focus", "RESTORE_FOCUS_UNSTABLE"),
            ("session", "SWAY_SESSION_CHANGED"),
        ):
            with self.subTest(change=change):
                self.sway = Sway()
                self.sway.add("kitty", 20, focus=False)
                self.sway.add("firefox", 21)
                self.engine.sway = self.sway
                def resolve(expected, nodes, timeout):
                    if change == "identity":
                        next(n for n in walk(self.sway.value) if n["id"] == 20)["app_id"] = "different"
                    elif change == "new-window":
                        self.sway.add("TEST_ONLY_FOREIGN", 22, focus=False)
                    elif change == "order":
                        workspace(self.sway.value, "1")["nodes"].reverse()
                    elif change == "focus":
                        for n in walk(self.sway.value):
                            n["focused"] = n["id"] == 20
                    else:
                        self.sway.session = "b" * 64
                    return {UUID: 21}
                with patch.object(self.provider, "resolve", side_effect=resolve), \
                     patch.object(self.engine, "_apply", side_effect=AssertionError("ADMISSION_REQUIRED")):
                    with self.assertRaisesRegex(Failure, reason):
                        self.engine.apply(self.data, True)
                self.assert_no_transaction()

    def test_provider_failure_preserves_previous_completed_incident(self):
        recovery = Recovery(self.sway, self.runtime, "b" * 32, "labfy-v2-stage-" + "b" * 32)
        recovery.data["status"] = "complete"
        recovery.publish()
        recovery.receipt("complete", [], [])
        attempt = self.runtime / "session-v2-restore-attempt.json"
        attempt.write_bytes(b'{"TEST_ONLY":"prior-attempt"}\n')
        paths = [self.runtime / JOURNAL, self.runtime / RECEIPT, attempt]
        original = {p: p.read_bytes() for p in paths}
        with patch.object(self.provider, "resolve", side_effect=Failure("FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")), \
             patch.object(self.engine, "_apply", side_effect=AssertionError("ADMISSION_REQUIRED")):
            with self.assertRaises(Deferred):
                self.engine.apply(self.data, True)
        self.assertEqual({p: p.read_bytes() for p in paths}, original)
        self.assertEqual(self.sway.commands, [])

    def test_late_provider_failure_stays_a_transaction_failure(self):
        with patch.object(self.engine, "_apply", side_effect=Failure("FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")) as apply:
            with self.assertRaisesRegex(Failure, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE") as result:
                self.engine.apply(self.data, True)
            self.assertNotIsInstance(result.exception, Deferred)
            apply.assert_called_once()


if __name__ == "__main__":
    unittest.main()

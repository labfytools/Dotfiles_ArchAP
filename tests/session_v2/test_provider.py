import os
import threading
import time
import unittest
import uuid
from common import *
from session_v2.storage import private_dir, atomic, read
from session_v2.firefox_identity import FirefoxProvider, process_start
from session_v2.errors import Failure
import tempfile


class ProviderTests(unittest.TestCase):
    def test_missing_collision_and_live_publisher(self):
        class SwayStub:
            session = "a" * 64
            def windows(self): return [{"id": 11, "app_id": "firefox"}, {"id": 12, "app_id": "firefox"}]
        with tempfile.TemporaryDirectory() as directory:
            provider = FirefoxProvider(SwayStub(), directory)
            a, b = str(uuid.uuid4()), str(uuid.uuid4())
            def publish(values):
                end = time.monotonic() + 2
                while time.monotonic() < end:
                    request = provider.directory / "request.json"
                    if request.exists() and read(request)["expires_ns"] > time.monotonic_ns(): break
                    time.sleep(.005)
                for ident, value in zip((11,12), values):
                    atomic(provider.directory / f"{ident}.json", {"schema": "firefox-session-window-uuid", "version": 1,
                          "session": SwayStub.session, "uuid": value, "con_id": ident, "observed_ns": time.monotonic_ns(),
                          "publisher_pid": os.getpid(), "publisher_start": process_start(os.getpid())})
            for values, expected_error in (((a,b), None), ((a,a), "EXACT_WINDOW_IDENTITY_COLLISION"), ((a,str(uuid.uuid4())), "EXACT_WINDOW_IDENTITY_MISSING")):
                thread = threading.Thread(target=publish, args=(values,)); thread.start()
                try:
                    if expected_error:
                        with self.assertRaisesRegex(Failure, expected_error): provider.resolve([a,b], SwayStub().windows(), 1)
                    else: self.assertEqual(provider.resolve([a,b], SwayStub().windows(), 1), {a:11,b:12})
                finally: thread.join()
            self.assertTrue(provider.available())
            with self.assertRaisesRegex(Failure, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE"):
                provider.capture(SwayStub().windows(), .05)


if __name__ == "__main__": unittest.main()

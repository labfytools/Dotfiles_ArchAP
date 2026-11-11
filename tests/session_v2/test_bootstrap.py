"""Protocole réel stdio et faux socket possédé ; aucun profil/socket utilisateur."""
import json
import socket
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from common import BACKEND, REPO, Path, os, sys
from session_v2.native_host import bootstrap_eligibility, classify, validate, EXTENSION_ID, APP_IDS, WEBAPP_IDS
from session_v2.errors import Failure


REQUEST = {"op": "bootstrap-eligibility"}
MAP = {"op": "map-window", "uuid": "11111111-1111-4111-8111-111111111111", "runtime_token": "a" * 32}
CLASSIFY = {"op": "classify-window", "runtime_token": MAP["runtime_token"]}
WEBAPP = "firefox.webapp-fcd72ebe-94c5-4209-b3f6-bbaa7784cded"
IMMICH_WEBAPP = "firefox.webapp-40f22022-70af-4784-81ee-100e6a56dc50"


def surface(app_id="firefox", con_id=42):
    return {"id": con_id, "app_id": app_id, "name": "[LABFY:" + MAP["runtime_token"] + "] private suffix"}


def frame(value):
    raw = json.dumps(value).encode()
    return struct.pack("=I", len(raw)) + raw


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        # AF_UNIX est borné à 108 octets : un worktree profond ne doit pas
        # rendre ces sockets TEST_ONLY dépendants du chemin du dépôt.
        self.tmp = tempfile.TemporaryDirectory(prefix="labfy-v2-bootstrap-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("home", "state", "runtime"):
            (self.root / name).mkdir(mode=0o700)
        self.env = {"PATH": os.defpath, "HOME": str(self.root / "home"),
                    "XDG_STATE_HOME": str(self.root / "state"), "XDG_RUNTIME_DIR": str(self.root / "runtime"),
                    "SWAYSOCK": str(self.root / "sway.sock")}
        self.store = self.root / "state/labfy-sway/session-v2"
        self.automatic = self.store / "automatic"
        self.last = self.automatic / "last.json"

    def prepare(self):
        self.automatic.mkdir(parents=True, mode=0o700)
        # pathlib parents use umask, make the entire owned namespace explicit.
        (self.store.parent).chmod(0o700)
        self.store.chmod(0o700)

    def observe(self):
        with patch.dict(os.environ, self.env, clear=True):
            result = bootstrap_eligibility()
        self.assertEqual(set(result), {"result", "baseline_enrollment_allowed"})
        self.assertEqual(result["result"], "OK")
        self.assertIs(type(result["baseline_enrollment_allowed"]), bool)
        return result["baseline_enrollment_allowed"]

    def wire(self, raw, extension=EXTENSION_ID, serve=False, nodes=None):
        # Le vrai host contrôle lstat/UID du socket. Le faux serveur n'accepte
        # que GET_TREE/GET_VERSION ; toute commande mutatrice échoue.
        server = socket.socket(socket.AF_UNIX)
        server.bind(self.env["SWAYSOCK"])
        server.listen()
        server.settimeout(.1)
        stop, errors = threading.Event(), []
        tree = {"id": 0, "nodes": [surface()] if nodes is None else nodes}
        def run():
            try:
                while not stop.is_set():
                    try: client, _ = server.accept()
                    except TimeoutError: continue
                    with client:
                        client.settimeout(2)
                        header = bytearray()
                        while len(header) < 14: header.extend(client.recv(14 - len(header)))
                        magic, size, kind = struct.unpack("<6sII", header)
                        self.assertEqual((magic, size), (b"i3-ipc", 0))
                        self.assertIn(kind, (4, 7))
                        if kind == 4: self.assertTrue(serve)
                        payload = json.dumps(tree if kind == 4 else {"human_readable": "TEST_ONLY"}).encode()
                        client.sendall(struct.pack("<6sII", b"i3-ipc", len(payload), kind) + payload)
            except Exception as error: errors.append(error)
        thread = threading.Thread(target=run)
        thread.start()
        try:
            result = subprocess.run([sys.executable, "-B", str(BACKEND / "session-v2-native-host.py"),
                                     "/fixture/manifest.json", extension], env=self.env, input=raw,
                                    capture_output=True, timeout=8)
        finally:
            stop.set(); thread.join(3); server.close()
            (self.root / "sway.sock").unlink()
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result.stderr, b"")
        answers, output = [], result.stdout
        while output:
            self.assertGreaterEqual(len(output), 4)
            size, = struct.unpack("=I", output[:4])
            self.assertTrue(0 < size <= 4096)
            self.assertGreaterEqual(len(output), 4 + size)
            answers.append(json.loads(output[4:4 + size]))
            output = output[4 + size:]
        return result.returncode, answers

    def test_absent_no_creation(self):
        self.assertTrue(self.observe())
        self.assertFalse(self.store.parent.exists())
        self.assertEqual(self.wire(frame(REQUEST)), (0, [{"result": "OK", "baseline_enrollment_allowed": True}]))
        self.assertFalse(self.store.parent.exists())

    def test_absent_last_existing_directory(self):
        self.prepare()
        self.assertTrue(self.observe())
        self.assertEqual(list(self.automatic.iterdir()), [])

    def test_present_and_corrupt_always_refuse(self):
        self.prepare()
        for raw in (b'{}', b'not json', b'', b'{"private":"never exported"}'):
            with self.subTest(raw=raw):
                self.last.write_bytes(raw); self.last.chmod(0o600)
                self.assertFalse(self.observe())
                self.assertEqual(self.wire(frame(REQUEST))[1], [{"result": "OK", "baseline_enrollment_allowed": False}])
                self.assertEqual(self.last.read_bytes(), raw)

    def test_named_only_without_automatic_refuses(self):
        from common import fixture
        from session_v2.checkpoint import Store
        Store(self.store).save("named", fixture())
        self.assertFalse(self.last.exists())
        self.assertFalse(self.observe())
        self.automatic.rmdir()
        before = {p.relative_to(self.store): (p.lstat().st_mode, p.lstat().st_size, p.lstat().st_mtime_ns) for p in self.store.rglob("*")}
        self.assertFalse(self.observe())
        self.assertEqual(self.wire(frame(REQUEST))[1], [{"result": "OK", "baseline_enrollment_allowed": False}])
        self.assertEqual(before, {p.relative_to(self.store): (p.lstat().st_mode, p.lstat().st_size, p.lstat().st_mtime_ns) for p in self.store.rglob("*")})

    def test_empty_sessions_with_or_without_automatic_allows_without_creation(self):
        self.prepare()
        sessions = self.store / "sessions"
        sessions.mkdir(mode=0o700)
        for automatic in (True, False):
            with self.subTest(automatic=automatic):
                if not automatic: self.automatic.rmdir()
                before = {p.relative_to(self.store) for p in self.store.rglob("*")}
                self.assertTrue(self.observe())
                self.assertEqual(before, {p.relative_to(self.store) for p in self.store.rglob("*")})

    def test_sessions_any_entry_refuses_without_content_read(self):
        self.prepare()
        self.automatic.rmdir()  # Absence d'automatic ne court-circuite pas sessions.
        sessions = self.store / "sessions"
        sessions.mkdir(mode=0o700)
        entry = sessions / "unexpected"
        for kind in ("file", "symlink", "fifo", "directory"):
            with self.subTest(kind=kind):
                if kind == "file": entry.write_bytes(b"not a checkpoint")
                elif kind == "symlink": entry.symlink_to(self.root / "missing")
                elif kind == "fifo": os.mkfifo(entry, 0o600)
                else: entry.mkdir(mode=0o700)
                try:
                    self.assertFalse(self.observe())
                    self.assertEqual(self.wire(frame(REQUEST))[1], [{"result": "OK", "baseline_enrollment_allowed": False}])
                finally:
                    if kind == "directory": entry.rmdir()
                    else: entry.unlink()

    def test_sessions_unsafe_directory_refuses(self):
        self.prepare()
        sessions = self.store / "sessions"
        sessions.mkdir(mode=0o700)
        for mode in (0, 0o300, 0o755):
            with self.subTest(mode=mode):
                sessions.chmod(mode)
                try: self.assertFalse(self.observe())
                finally: sessions.chmod(0o700)
        sessions.rmdir()
        sessions.symlink_to(self.root / "home")
        self.assertFalse(self.observe())
        sessions.unlink()
        os.mkfifo(sessions, 0o600)
        self.assertFalse(self.observe())

    def test_sessions_list_error_refuses(self):
        self.prepare()
        (self.store / "sessions").mkdir(mode=0o700)
        with patch("session_v2.native_host.os.listdir", side_effect=PermissionError):
            self.assertFalse(self.observe())

    def test_last_with_sessions_absent_refuses(self):
        self.prepare()
        self.last.write_bytes(b"not JSON")
        self.assertFalse((self.store / "sessions").exists())
        self.assertFalse(self.observe())
        self.assertFalse((self.store / "sessions").exists())

    def test_unreadable_and_nonprivate_directory_refuse(self):
        self.prepare()
        for mode in (0, 0o300, 0o755):
            self.automatic.chmod(mode)
            try:
                self.assertFalse(self.observe())
                self.assertEqual(self.wire(frame(REQUEST))[1], [{"result": "OK", "baseline_enrollment_allowed": False}])
            finally: self.automatic.chmod(0o700)

    def test_valid_store_checkpoint_and_unreadable_file_refuse(self):
        from common import fixture
        from session_v2.checkpoint import Store
        Store(self.store).checkpoint(fixture())
        self.assertFalse(self.observe())
        before = self.last.read_bytes()
        self.last.chmod(0)
        try:
            self.assertEqual(self.wire(frame(REQUEST))[1], [{"result": "OK", "baseline_enrollment_allowed": False}])
        finally: self.last.chmod(0o600)
        self.assertEqual(self.last.read_bytes(), before)

    def test_symlinks_and_special_last_refuse_without_open(self):
        self.prepare()
        self.last.symlink_to(self.root / "missing")
        self.assertFalse(self.observe()); self.last.unlink()
        os.mkfifo(self.last, 0o600)
        self.assertFalse(self.observe()); self.last.unlink()
        self.automatic.rmdir(); self.automatic.symlink_to(self.root / "home")
        self.assertFalse(self.observe())

    def test_state_symlink_and_relative_state_refuse(self):
        (self.root / "state").rmdir()
        (self.root / "state").symlink_to(self.root / "home")
        self.assertFalse(self.observe())
        self.env["XDG_STATE_HOME"] = "relative"
        self.assertFalse(self.observe())

    def test_home_fallback_matches_canonical_location(self):
        del self.env["XDG_STATE_HOME"]
        self.assertTrue(self.observe())
        target = self.root / "home/.local/state/labfy-sway/session-v2/automatic"
        target.mkdir(parents=True, mode=0o700)
        (target / "last.json").write_text("invalid")
        self.assertFalse(self.observe())

    def test_socket_authority_failure_refuses_absence(self):
        from unittest.mock import Mock
        sway = Mock()
        sway.request.side_effect = PermissionError
        with patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(bootstrap_eligibility(sway), {"result": "OK", "baseline_enrollment_allowed": False})
        sway.request.assert_called_once_with(7)

    def test_os_error_is_not_absence(self):
        with patch("session_v2.native_host.os.open", side_effect=PermissionError):
            self.assertFalse(self.observe())

    def test_envelope_and_framing_rejected(self):
        for message in ({**REQUEST, "uuid": MAP["uuid"]}, {**REQUEST, "path": "forbidden"},
                        {"op": "unknown"}, {}, [], {"op": True}):
            self.assertNotEqual(self.wire(frame(message))[1][0]["result"], "OK")
        duplicate = b'{"op":"bootstrap-eligibility","op":"unknown"}'
        for raw in (struct.pack("=I", 4097), struct.pack("=I", 0),
                    struct.pack("=I", len(duplicate)) + duplicate):
            code, answers = self.wire(raw)
            self.assertTrue(not answers or answers[0]["result"] != "OK")

    def test_allowlist_denied(self):
        self.assertEqual(self.wire(frame(REQUEST), extension="other@invalid"), (1, []))

    def test_interleaved_operations_map_unchanged(self):
        code, answers = self.wire(frame(REQUEST) + frame(MAP) + frame(REQUEST), serve=True)
        self.assertEqual(code, 0)
        self.assertEqual(answers, [{"result": "OK", "baseline_enrollment_allowed": True},
                                  {"result": "OK", "uuid": MAP["uuid"], "con_id": 42},
                                  {"result": "OK", "baseline_enrollment_allowed": True}])
        observations = list((self.root / "runtime").glob("labfy-sway/session-v2/firefox/*/42.json"))
        self.assertEqual(len(observations), 1)
        record = json.loads(observations[0].read_text())
        self.assertEqual(record["uuid"], MAP["uuid"])
        self.assertEqual(record["publisher_pid"] > 0, True)
        self.assertFalse(self.store.exists())

    def assert_no_observations(self):
        observations = [p for p in (self.root / "runtime").rglob("*.json") if p.stem.isdigit()]
        self.assertEqual(observations, [])
        self.assertFalse(self.store.exists())

    def test_classify_exact_catalogue_and_no_uuid_publication(self):
        self.assertEqual(APP_IDS, {"firefox", "org.mozilla.firefox"})
        self.assertEqual(WEBAPP_IDS, {WEBAPP, IMMICH_WEBAPP})
        for app_id, kind in (("firefox", "browser"), ("org.mozilla.firefox", "browser"),
                             (WEBAPP, "managed-webapp"), (IMMICH_WEBAPP, "managed-webapp")):
            with self.subTest(app_id=app_id):
                code, answers = self.wire(frame(CLASSIFY), serve=True, nodes=[surface(app_id)])
                self.assertEqual(code, 0)
                self.assertEqual(answers, [{"result": "OK", "kind": kind,
                                           "runtime_token": CLASSIFY["runtime_token"], "con_id": 42}])
                self.assert_no_observations()

    def test_classify_closed_envelope_and_token(self):
        invalid = [
            ({**CLASSIFY, "uuid": MAP["uuid"]}, "MESSAGE_SCHEMA"),
            ({**CLASSIFY, "kind": "managed-webapp"}, "MESSAGE_SCHEMA"),
            ({**CLASSIFY, "app_id": WEBAPP}, "MESSAGE_SCHEMA"),
            ({"op": "classify-window"}, "MESSAGE_SCHEMA"),
        ]
        for token in (None, True, 32, "", "a" * 31, "a" * 33, "A" * 32, "g" * 32):
            invalid.append(({**CLASSIFY, "runtime_token": token}, "INVALID_TOKEN"))
        for message, expected in invalid:
            with self.subTest(message=message):
                with self.assertRaises(Failure) as caught: validate(message)
                self.assertEqual(caught.exception.code, expected)
                self.assertEqual(self.wire(frame(message))[1], [{"result": expected}])
        self.assert_no_observations()

    def test_classify_real_framing_rejects_duplicate_and_bounds(self):
        duplicate = b'{"op":"classify-window","runtime_token":"' + b'a' * 32 + b'","runtime_token":"' + b'b' * 32 + b'"}'
        for raw in (struct.pack("=I", len(duplicate)) + duplicate,
                    struct.pack("=I", 4097), struct.pack("=I", 0),
                    struct.pack("=I", 80) + b'{"op":"classify-window"}'):
            with self.subTest(raw=raw):
                _, answers = self.wire(raw)
                self.assertTrue(not answers or all(a["result"] != "OK" for a in answers))
        self.assert_no_observations()

    def test_classify_unknown_never_becomes_managed_webapp(self):
        for app_id in ("firefox.webapp-unregistered", WEBAPP + "-suffix", "Firefox", "kitty", "x11-class:firefox"):
            with self.subTest(app_id=app_id):
                self.assertEqual(self.wire(frame(CLASSIFY), serve=True, nodes=[surface(app_id)])[1],
                                 [{"result": "WINDOW_CLASS_UNSUPPORTED"}])
        x11 = {**surface(None), "window": 123, "window_properties": {"class": "firefox"}}
        self.assertEqual(self.wire(frame(CLASSIFY), serve=True, nodes=[x11])[1],
                         [{"result": "WINDOW_CLASS_UNSUPPORTED"}])
        self.assert_no_observations()

    def test_classify_collision_including_unknown_fails_closed(self):
        for second in ("org.mozilla.firefox", WEBAPP, "unregistered"):
            with self.subTest(second=second):
                self.assertEqual(self.wire(frame(CLASSIFY), serve=True,
                                           nodes=[surface(), surface(second, 43)])[1],
                                 [{"result": "EXACT_WINDOW_IDENTITY_COLLISION"}])
        self.assert_no_observations()

    def test_classify_requires_exact_prefix_with_bounded_timeout(self):
        for name in ("private unmarked", "prefix " + surface()["name"],
                     "[LABFY:" + "b" * 32 + "] private suffix"):
            sway = Mock()
            sway.windows.return_value = [{**surface(), "name": name}]
            with self.subTest(name=name), patch("session_v2.native_host.time.monotonic", side_effect=[0, 3]):
                with self.assertRaises(Failure) as caught: classify(sway, CLASSIFY)
                self.assertEqual(caught.exception.code, "CORRELATION_TIMEOUT")
                sway.windows.assert_called_once_with()

    def test_classify_requires_positive_integer_container(self):
        for identity in (None, True, 0, -1, "42"):
            sway = Mock()
            sway.windows.return_value = [surface(con_id=identity)]
            with self.subTest(identity=identity):
                with self.assertRaises(Failure) as caught: classify(sway, CLASSIFY)
                self.assertEqual(caught.exception.code, "WINDOW_CLASS_UNSUPPORTED")

    def test_classify_does_not_extend_map_to_webapp(self):
        for webapp in (WEBAPP, IMMICH_WEBAPP):
            with self.subTest(webapp=webapp):
                code, answers = self.wire(frame(CLASSIFY) + frame(MAP), serve=True, nodes=[surface(webapp)])
                self.assertEqual(code, 0)
                self.assertEqual(answers, [{"result": "OK", "kind": "managed-webapp",
                                           "runtime_token": CLASSIFY["runtime_token"], "con_id": 42},
                                          {"result": "CORRELATION_TIMEOUT"}])
                self.assert_no_observations()

    def test_classify_interleaved_browser_map_and_bootstrap_remain_compatible(self):
        code, answers = self.wire(frame(REQUEST) + frame(CLASSIFY) + frame(MAP) + frame(CLASSIFY), serve=True)
        self.assertEqual(code, 0)
        classification = {"result": "OK", "kind": "browser",
                          "runtime_token": CLASSIFY["runtime_token"], "con_id": 42}
        self.assertEqual(answers, [{"result": "OK", "baseline_enrollment_allowed": True}, classification,
                                  {"result": "OK", "uuid": MAP["uuid"], "con_id": 42}, classification])
        observations = [p for p in (self.root / "runtime").rglob("*.json") if p.stem.isdigit()]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].name, "42.json")
        self.assertEqual(json.loads(observations[0].read_text())["uuid"], MAP["uuid"])
        self.assertFalse(self.store.exists())

    def test_classify_rejects_wrong_operation(self):
        with self.assertRaises(Failure) as caught: classify(Mock(), MAP)
        self.assertEqual(caught.exception.code, "OP_NOT_ALLOWED")

    def test_checkpoint_created_between_observations(self):
        self.prepare()
        self.assertTrue(self.observe())
        self.last.write_text("corrupt is still present")
        self.assertFalse(self.observe())


if __name__ == "__main__": unittest.main()

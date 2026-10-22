"""Protocole réel stdio et faux socket possédé ; aucun profil/socket utilisateur."""
import json
import socket
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from common import BACKEND, REPO, Path, os, sys
from session_v2.native_host import bootstrap_eligibility, EXTENSION_ID


REQUEST = {"op": "bootstrap-eligibility"}
MAP = {"op": "map-window", "uuid": "11111111-1111-4111-8111-111111111111", "runtime_token": "a" * 32}


def frame(value):
    raw = json.dumps(value).encode()
    return struct.pack("=I", len(raw)) + raw


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        base = REPO / "build/bootstrap-fixtures"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
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

    def wire(self, raw, extension=EXTENSION_ID, serve=False):
        # Le vrai host contrôle lstat/UID du socket. Le faux serveur n'accepte
        # que GET_TREE/GET_VERSION ; toute commande mutatrice échoue.
        server = socket.socket(socket.AF_UNIX)
        server.bind(self.env["SWAYSOCK"])
        server.listen()
        server.settimeout(.1)
        stop, errors = threading.Event(), []
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
                        tree = {"id": 0, "nodes": [{"id": 42, "app_id": "firefox", "name": "[LABFY:" + MAP["runtime_token"] + "] private suffix"}]}
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

    def test_checkpoint_created_between_observations(self):
        self.prepare()
        self.assertTrue(self.observe())
        self.last.write_text("corrupt is still present")
        self.assertFalse(self.observe())


if __name__ == "__main__": unittest.main()

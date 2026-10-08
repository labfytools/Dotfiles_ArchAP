import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "bin/.local/bin/labfy-removable-media"
SPEC = importlib.util.spec_from_loader(
    "labfy_removable_media_ipc",
    SourceFileLoader("labfy_removable_media_ipc", str(SCRIPT)),
)
assert SPEC and SPEC.loader
media = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = media
SPEC.loader.exec_module(media)


class IpcTests(unittest.TestCase):
    def test_request_allowlist_and_shape(self):
        self.assertEqual(media.validate_request({"operation": "list"}), ("list", None))
        with self.assertRaises(media.RequestError):
            media.validate_request({"operation": "format", "runtime_id": "/tmp/x"})
        with self.assertRaises(media.RequestError):
            media.validate_request({"operation": "list", "extra": True})
        with self.assertRaises(media.RequestError):
            media.validate_request({"operation": "mount", "runtime_id": "sdb1"})

    def test_socket_mode_and_json_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "media.sock"
            seen = []
            server = media.JsonSocketServer(
                path, lambda request: seen.append(request) or {"ok": True}
            )
            server.start()
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(str(path))
            thread = threading.Thread(
                target=lambda: server._serve_connection(server.socket.accept()[0])
            )
            thread.start()
            client.sendall(b'{"operation":"list"}\n')
            response = json.loads(client.makefile("rb").readline())
            client.close()
            thread.join(2)
            server.socket.close()
            self.assertFalse(thread.is_alive())
            self.assertEqual(response, {"ok": True})
            self.assertEqual(seen, [{"operation": "list"}])

    def test_oversized_request_is_rejected_without_calling_handler(self):
        called = []
        server = media.JsonSocketServer(Path("unused"), lambda request: called.append(request))
        server_side, client_side = socket.socketpair()
        thread = threading.Thread(target=server._serve_connection, args=(server_side,))
        thread.start()
        client_side.sendall(b"x" * (media.MAX_REQUEST + 1))
        response = json.loads(client_side.makefile("rb").readline())
        thread.join(2)
        client_side.close()
        self.assertFalse(response["ok"])
        self.assertIn("volumineuse", response["error"])
        self.assertEqual(called, [])

    def test_slow_incomplete_request_times_out_without_calling_handler(self):
        called = []
        server = media.JsonSocketServer(Path("unused"), lambda request: called.append(request))
        server_side, client_side = socket.socketpair()
        previous_timeout = media.READ_TIMEOUT
        media.READ_TIMEOUT = 0.05
        try:
            thread = threading.Thread(
                target=server._serve_connection, args=(server_side,)
            )
            thread.start()
            client_side.sendall(b'{"operation":')
            response = json.loads(client_side.makefile("rb").readline())
            thread.join(2)
        finally:
            media.READ_TIMEOUT = previous_timeout
            client_side.close()
        self.assertFalse(thread.is_alive())
        self.assertFalse(response["ok"])
        self.assertIn("Délai de lecture", response["error"])
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()

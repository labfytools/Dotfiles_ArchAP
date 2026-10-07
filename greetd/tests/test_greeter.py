import contextlib
import io
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import sys
import tempfile
import threading
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from auth import AuthFlow
from greetd_ipc import Client, ProtocolError, SESSION_COMMAND, MAX_FRAME
from accounts import users
from system_state import battery, backlight, set_brightness
from avatar_backend import AvatarError, render_png, source_path
from avatar_icon import system_icon

SECRET = "LABFY_SYNTHETIC_SECRET_59f3c4e2"


class FakeGreetd:
    def __init__(self, replies):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name + "/socket"
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(self.path)
        self.server.listen(1)
        self.replies = replies
        self.requests = []
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        connection, _ = self.server.accept()
        with connection:
            for reply in self.replies:
                header = connection.recv(4)
                if not header:
                    break
                size = struct.unpack("=I", header)[0]
                assert size <= MAX_FRAME
                data = b""
                while len(data) < size:
                    data += connection.recv(size - len(data))
                request = json.loads(data)
                self.requests.append(request)
                if request["type"] == "start_session":
                    assert request["cmd"] == SESSION_COMMAND
                    assert request["env"] == []
                encoded = json.dumps(reply).encode()
                connection.sendall(struct.pack("=I", len(encoded)) + encoded)

    def close(self):
        self.server.close()
        self.thread.join(2)
        self.temp.cleanup()


def msg(kind, value="Message PAM"):
    return {"type": "auth_message", "auth_message_type": kind, "auth_message": value}


class Tests(unittest.TestCase):
    def test_full_pam_sequence_and_secret_absent_from_outputs(self):
        fake = FakeGreetd([msg("secret"), msg("info"), msg("visible"), msg("error"), msg("secret"),
                            {"type": "success"}, {"type": "success"}])
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                flow = AuthFlow(fake.path)
                self.assertEqual(flow.begin("example")["auth_message_type"], "secret")
                self.assertEqual(flow.answer(SECRET)["auth_message_type"], "info")
                self.assertEqual(flow.answer()["auth_message_type"], "visible")
                self.assertEqual(flow.answer("code")["auth_message_type"], "error")
                self.assertEqual(flow.answer()["auth_message_type"], "secret")
                self.assertEqual(flow.answer("second")["type"], "success")
                self.assertEqual(flow.start()["type"], "success")
            self.assertNotIn(SECRET, output.getvalue())
            self.assertEqual(fake.requests[1]["response"], SECRET)
            self.assertNotIn("response", fake.requests[2])
            self.assertEqual(fake.requests[-1]["cmd"], SESSION_COMMAND)
        finally:
            fake.close()

    def test_auth_error_retry(self):
        first = FakeGreetd([msg("secret"), {"type": "error", "error_type": "auth_error", "description": "bad"}, {"type": "success"}])
        second = FakeGreetd([msg("visible"), {"type": "success"}, {"type": "success"}])
        try:
            flow = AuthFlow(first.path)
            flow.begin("example")
            self.assertEqual(flow.answer("wrong")["error_type"], "auth_error")
            self.assertFalse(flow.authenticated)
            flow.socket_path = second.path
            self.assertEqual(flow.begin("manual-nss-user")["auth_message_type"], "visible")
            self.assertEqual(flow.answer("code")["type"], "success")
            self.assertEqual(flow.start()["type"], "success")
            self.assertEqual(second.requests[0]["username"], "manual-nss-user")
        finally:
            first.close()
            second.close()

    def test_accounts(self):
        Row = pwd.struct_passwd
        entries = [Row(("system", "x", 999, 1, "", "/", "/bin/bash")),
                   Row(("human", "x", 1000, 1, "", "/", "/bin/bash")),
                   Row(("blocked", "x", 1001, 1, "", "/", "/usr/bin/nologin")),
                   Row(("false", "x", 1002, 1, "", "/", "/bin/false")),
                   Row(("another", "x", 1003, 1, "Example", "/", "/bin/zsh"))]
        self.assertEqual(users(entries, (1000, 60000)), ["another", "human"])

    def test_battery_and_backlight(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertIsNone(battery(root))
            bat = root / "BAT1"
            bat.mkdir()
            (bat / "capacity").write_text("60")
            for status in ("Charging", "Discharging", "Full", "Not charging"):
                (bat / "status").write_text(status)
                self.assertEqual(battery(root), (60, status))
            light = root / "backlight" / "amdgpu_bl1"
            light.mkdir(parents=True)
            (light / "max_brightness").write_text("400000")
            (light / "brightness").write_text("200000")
            self.assertEqual(backlight(root / "backlight"), (light, 400000, 200000))
            set_brightness(light, 400000, 10)
            self.assertEqual((light / "brightness").read_text(), "40000")
            set_brightness(light, 400000, 100)
            self.assertEqual((light / "brightness").read_text(), "400000")
            (light / "max_brightness").write_text("0")
            self.assertIsNone(backlight(root / "backlight"))
            (light / "max_brightness").unlink()
            self.assertIsNone(backlight(root / "backlight"))
            self.assertIsNone(backlight(root / "missing"))
            with self.assertRaises(OSError):
                set_brightness(root / "missing", 400000, 50)

    def test_reject_oversized_response(self):
        temp = tempfile.TemporaryDirectory()
        path = temp.name + "/socket"
        server = socket.socket(socket.AF_UNIX)
        server.bind(path)
        server.listen(1)
        def serve():
            conn, _ = server.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(struct.pack("=I", MAX_FRAME + 1))
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with Client(path) as client:
                with self.assertRaises(ProtocolError):
                    client.create("example")
        finally:
            server.close()
            thread.join(2)
            temp.cleanup()

    def test_avatar_conversion_and_system_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "portrait.jpg"
            Image.new("RGB", (400, 200), (10, 20, 30)).save(original)
            self.assertEqual(source_path(original.as_uri()), original)
            converted = root / "avatar.png"
            render_png(original, converted)
            with Image.open(converted) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (256, 256))
            with self.assertRaises(AvatarError):
                source_path("https://example.invalid/avatar.png")
            too_large = root / "too-large.jpg"
            too_large.write_bytes(b"x" * (12 * 1024 * 1024 + 1))
            with self.assertRaises(AvatarError):
                source_path(str(too_large))
            self.assertIsNone(system_icon("../etc/passwd", root))
            self.assertIsNone(system_icon("example", root))
            (root / "example").symlink_to(converted)
            self.assertIsNone(system_icon("example", root))


if __name__ == "__main__":
    unittest.main()

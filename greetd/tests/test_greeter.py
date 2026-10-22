import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import sys
import tempfile
import time
from unittest.mock import patch
import threading
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from auth import AuthFlow
from greetd_ipc import Client, ProtocolError, session_command, SESSION_COMMANDS, MAX_FRAME
from accounts import users
from system_state import battery, backlight, set_brightness
from avatar_backend import AvatarError, render_png, source_path
from avatar_icon import system_icon

STABLE = ["/usr/bin/uwsm", "start", "sway.desktop"]
MOSAIC = ["/usr/bin/uwsm", "start", "swayfx-mosaic-test.desktop"]

SECRET = "LABFY_SYNTHETIC_SECRET_59f3c4e2"


class FakeGreetd:
    def __init__(self, replies):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name + "/socket"
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(self.path)
        self.server.listen(1)
        self.server.settimeout(3)
        self.failure = None
        self.replies = replies
        self.requests = []
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            connection, _ = self.server.accept()
            connection.settimeout(3)
            with connection:
                for reply in self.replies:
                    header = self.read(connection, 4)
                    if not header:
                        break
                    size = struct.unpack("=I", header)[0]
                    assert size <= MAX_FRAME
                    request = json.loads(self.read(connection, size))
                    self.requests.append(request)
                    # None simule la perte du socket après réception de la requête.
                    if reply is None:
                        break
                    if callable(reply):
                        reply = reply()
                    encoded = json.dumps(reply).encode()
                    connection.sendall(struct.pack("=I", len(encoded)) + encoded)
        except Exception as exc:
            self.failure = exc

    @staticmethod
    def read(connection, count):
        data = b""
        while len(data) < count:
            part = connection.recv(count - len(data))
            if not part:
                return data
            data += part
        return data

    def close(self):
        self.server.close()
        self.thread.join(2)
        self.temp.cleanup()
        if self.thread.is_alive():
            raise AssertionError("Serveur fictif encore actif")
        if self.failure:
            raise self.failure


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
            self.assertEqual(fake.requests[-1]["cmd"], STABLE)
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

    def test_mosaic_multi_prompt_secret_and_info(self):
        fake = FakeGreetd([msg("info"), msg("visible"), msg("secret"),
                           {"type": "success"}, {"type": "success"}])
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                flow = AuthFlow(fake.path)
                flow.begin("example", "mosaic")
                flow.answer()
                flow.answer("visible-code")
                flow.answer(SECRET)
                flow.start()
            self.assertNotIn(SECRET, output.getvalue())
            self.assertEqual(fake.requests[-1], {"type": "start_session", "cmd": MOSAIC, "env": []})
        finally:
            fake.close()

    def test_exact_commands_and_empty_environment(self):
        for selection, expected in (("stable", STABLE), ("mosaic", MOSAIC), (None, STABLE)):
            with self.subTest(selection=selection):
                fake = FakeGreetd([{"type": "success"}, {"type": "success"}])
                try:
                    flow = AuthFlow(fake.path)
                    if selection is None:
                        flow.begin("example")
                    else:
                        flow.begin("example", selection)
                    self.assertEqual(flow.start(), {"type": "success"})
                    self.assertEqual(fake.requests[-1], {"type": "start_session", "cmd": expected, "env": []})
                    with self.assertRaises(ProtocolError):
                        flow.start()
                    self.assertFalse(flow.authenticated)
                finally:
                    fake.close()

    def test_allowlist_rejects_types_and_injection_before_ipc(self):
        invalid = (None, True, False, 0, 1, [], ["stable"], {}, "/usr/bin/sway",
                   "sway.desktop", "default", "stable ", "Stable", "mosaic --help",
                   "stable;sh", "$(id)", "stable\n", "stаble", "ｍosaic", "mosaic\x00")
        from unittest.mock import patch
        with patch.object(Client, "request") as request:
            client = object.__new__(Client)
            for choice in invalid:
                with self.subTest(choice=choice):
                    with self.assertRaises(ValueError):
                        client.start(choice)
                    with self.assertRaises(ValueError):
                        AuthFlow("/missing").begin("example", choice)
            with self.assertRaises(TypeError):
                client.start("stable", "extra")
            with self.assertRaises(TypeError):
                client.start("stable", env=["HOME=/bad"])
            with self.assertRaises(TypeError):
                session_command("stable", "extra")
            with self.assertRaises(TypeError):
                AuthFlow().start("mosaic")
            request.assert_not_called()
        self.assertEqual(session_command(), tuple(STABLE))
        with self.assertRaises(TypeError):
            SESSION_COMMANDS["stable"] = tuple(MOSAIC)
        with self.assertRaises(TypeError):
            session_command()[0] = "sh"

    def test_changed_identity_cancels_previous_conversation(self):
        # Le vrai begin réinitialise PAM, même si seul le choix de session change.
        for username in ("example", "other"):
            first = FakeGreetd([msg("secret"), {"type": "success"}])
            second = FakeGreetd([msg("secret"), {"type": "success"}, {"type": "success"}])
            try:
                flow = AuthFlow(first.path)
                flow.begin("example", "mosaic")
                flow.socket_path = second.path
                flow.begin(username, "stable")
                self.assertEqual(first.requests[-1], {"type": "cancel_session"})
                self.assertEqual(flow.selection, "stable")
                self.assertEqual(flow.username, username)
                flow.answer(SECRET)
                flow.start()
                self.assertEqual(second.requests[-1]["cmd"], STABLE)
            finally:
                first.close()
                second.close()

    def test_launch_refusal_never_falls_back_and_consumes_auth(self):
        fake = FakeGreetd([{"type": "success"},
                           {"type": "error", "error_type": "error", "description": "missing desktop"},
                           {"type": "success"}])
        try:
            flow = AuthFlow(fake.path)
            flow.begin("example", "mosaic")
            self.assertEqual(flow.start()["type"], "error")
            self.assertIsNone(flow.client)
            with self.assertRaises(ProtocolError):
                flow.start()
            launches = [r for r in fake.requests if r["type"] == "start_session"]
            self.assertEqual(launches, [{"type": "start_session", "cmd": MOSAIC, "env": []}])
        finally:
            fake.close()

    def test_v2_launch_refusal_then_fresh_stable_authentication(self):
        # Un refus Mosaic consomme PAM ; Stable nécessite une nouvelle conversation.
        first = FakeGreetd([msg("secret"), {"type": "success"},
                            {"type": "error", "error_type": "error"}, {"type": "success"}])
        second = FakeGreetd([msg("secret"), {"type": "success"}, {"type": "success"}])
        try:
            flow = AuthFlow(first.path)
            flow.begin("example", "mosaic")
            flow.answer(SECRET)
            self.assertEqual(flow.start()["type"], "error")
            self.assertIsNone(flow.selection)
            flow.socket_path = second.path
            flow.begin("example", "stable")
            self.assertFalse(flow.authenticated)
            flow.answer(SECRET)
            flow.start()
            self.assertEqual(first.requests[-2], {"type": "start_session", "cmd": MOSAIC, "env": []})
            self.assertEqual(second.requests[-1], {"type": "start_session", "cmd": STABLE, "env": []})
        finally:
            first.close()
            second.close()

    def test_socket_loss_resets_every_stage(self):
        for replies, operation in (([None], "begin"), ([msg("secret"), None], "answer"),
                                   ([{"type": "success"}, None], "start")):
            fake = FakeGreetd(replies)
            try:
                flow = AuthFlow(fake.path)
                with self.assertRaises((ProtocolError, OSError)):
                    flow.begin("example", "mosaic")
                    if operation == "answer":
                        flow.answer(SECRET)
                    elif operation == "start":
                        flow.start()
                self.assertIsNone(flow.client)
                self.assertIsNone(flow.selection)
                self.assertIsNone(flow.username)
                self.assertFalse(flow.authenticated)
            finally:
                fake.close()

    def test_unknown_user_error_and_invalid_username_reset(self):
        fake = FakeGreetd([{"type": "error", "error_type": "auth_error"}, {"type": "success"}])
        try:
            flow = AuthFlow(fake.path)
            self.assertEqual(flow.begin("unknown", "mosaic")["type"], "error")
            self.assertIsNone(flow.client)
            self.assertIsNone(flow.selection)
            for value in (True, [], "", "bad\nname"):
                with self.assertRaises(ValueError):
                    flow.begin(value)
        finally:
            fake.close()

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


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("session_update", Path(__file__).resolve().parents[1] / "scripts/session-update.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir(mode=0o700)
        self.module.OWNER = os.getuid()
        self.module.TARGETS = {name: self.root / name for name in self.module.TARGETS}
        self.module.ORIGINALS = {}
        manifest = {"version": 1, "files": {}}
        for name, target in self.module.TARGETS.items():
            old, new = ("old:" + name).encode(), ("new:" + name).encode()
            target.write_bytes(old)
            target.chmod(0o644)
            (self.bundle / (name + ".old")).write_bytes(old)
            (self.bundle / (name + ".new")).write_bytes(new)
            manifest["files"][name] = {"old": self.module.digest(old), "new": self.module.digest(new)}
            self.module.ORIGINALS[name] = self.module.digest(old)
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        (self.bundle / "session-update.py").write_bytes(Path(self.module.__file__).read_bytes())
        for item in self.bundle.iterdir():
            item.chmod(0o600)
        # Seule la confiance des parents est adaptée au LAB non-root sous /var/tmp.
        # Lecture, SHA, permissions, journal, fsync et rename sont ceux du vrai outil.
        self.guard = patch.object(self.module, "trusted_parents")
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def assert_state(self, prefix):
        for name, path in self.module.TARGETS.items():
            self.assertEqual(path.read_bytes(), (prefix + ":" + name).encode())
            self.assertEqual(path.stat().st_mode & 0o7777, 0o644)

    def test_durable_barrier_failure_never_publishes_or_rolls_back(self):
        original = os.fsync
        for failed in (self.bundle / 'session-update.py', self.bundle.parent):
            with self.subTest(failed=failed):
                def sync(fd):
                    if Path(os.readlink('/proc/self/fd/' + str(fd))) == failed:
                        raise OSError('barrier failure')
                    return original(fd)
                with patch.object(os, 'fsync', side_effect=sync), patch.object(self.module, 'publish') as publish:
                    with self.assertRaises(OSError):
                        self.module.transact(self.bundle, 'apply')
                    publish.assert_not_called()
                self.assert_state('old')
                self.assertFalse((self.bundle / 'state').exists())

    def test_apply_and_rollback_idempotent(self):
        for operation, state in (("apply", "new"), ("apply", "new"),
                                 ("rollback", "old"), ("rollback", "old")):
            self.module.transact(self.bundle, operation)
            self.assert_state(state)

    def test_ordinary_write_failure_rolls_back_complete_batch(self):
        original = self.module.atomic_write
        writes = []
        def failing(path, *args):
            if path in self.module.TARGETS.values():
                writes.append(path)
                if len(writes) == 2:
                    raise OSError("échec synthétique")
            return original(path, *args)
        with patch.object(self.module, "atomic_write", side_effect=failing):
            with self.assertRaises(OSError):
                self.module.transact(self.bundle, "apply")
        self.assert_state("old")
        self.assertEqual((self.bundle / "state").read_text(), "original\n")

    def test_killed_process_recovers_before_new_apply(self):
        # Le fils meurt après le deuxième vrai rename, sans exécuter except/finally.
        pid = os.fork()
        if pid == 0:
            original = self.module.atomic_write
            count = [0]
            def die(path, *args):
                original(path, *args)
                if path in self.module.TARGETS.values():
                    count[0] += 1
                    if count[0] == 2:
                        os._exit(77)
            self.module.atomic_write = die
            try:
                self.module.transact(self.bundle, "apply")
            finally:
                os._exit(78)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 77)
        self.assertEqual((self.bundle / "state").read_text(), "applying\n")
        with self.assertRaisesRegex(ValueError, "interrompue restaurée"):
            self.module.transact(self.bundle, "apply")
        self.assert_state("old")
        self.module.transact(self.bundle, "apply")
        self.assert_state("new")
        self.module.transact(self.bundle, "rollback")
        self.assert_state("old")

    def test_drift_bad_hash_mode_symlink_rejected_before_write(self):
        target = next(iter(self.module.TARGETS.values()))
        original = target.read_bytes()
        target.write_bytes(b"outside change")
        with self.assertRaises(ValueError):
            self.module.transact(self.bundle, "apply")
        self.assertFalse((self.bundle / "state").exists())
        self.assertEqual(target.read_bytes(), b"outside change")
        target.write_bytes(original)
        target.chmod(0o666)
        with self.assertRaises(ValueError):
            self.module.transact(self.bundle, "apply")
        target.chmod(0o644)
        backup = target.with_suffix(".link-target")
        target.rename(backup)
        target.symlink_to(backup)
        with self.assertRaises(OSError):
            self.module.transact(self.bundle, "apply")
        target.unlink()
        backup.rename(target)
        (self.bundle / (target.name + ".new")).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.module.transact(self.bundle, "apply")
        self.assert_state("old")


@unittest.skipUnless(os.environ.get("LABFY_GTK_TESTS") == "1", "rendu GTK Wayland explicitement activé seulement")
class GtkTests(unittest.TestCase):
    def pump(self, condition):
        from gi.repository import GLib
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            time.sleep(0.005)
        self.assertTrue(condition(), "retour GTK absent")

    def test_gtk_css_parses_without_error(self):
        from labfy_greeter import Gtk
        provider = Gtk.CssProvider()
        errors = []
        provider.connect("parsing-error", lambda _provider, _section, error: errors.append(str(error)))
        provider.load_from_path(str(Path(__file__).resolve().parents[1] / "style/labfy-greeter.css"))
        self.assertEqual(errors, [])

    def test_real_widgets_preview_and_pam_snapshot_busy_retry(self):
        import labfy_greeter as ui
        from gi.repository import Gtk
        app = ui.Greeter(preview=True)
        app.register(None)
        with patch.object(ui, "AuthFlow", side_effect=AssertionError("PAM en aperçu")):
            app.activate()
        try:
            self.assertEqual(app.session_choice(), "stable")
            app.session_selector.set_selected(1)
            self.assertEqual(app.session_choice(), "mosaic")
            self.assertIsNone(app.flow)
            app.submit()
            app.perform(lambda: self.fail("worker en aperçu"))
            self.assertFalse(app.busy)
            self.assertFalse(app.button.get_sensitive())
            self.assertFalse(app.entry.get_sensitive())
            self.assertFalse(app.slider.get_sensitive())
            entered, release = threading.Event(), threading.Event()
            def delayed_failure():
                entered.set()
                release.wait(3)
                return {"type": "error", "error_type": "auth_error"}
            first = FakeGreetd([msg("secret"), delayed_failure, {"type": "success"}])
            second = FakeGreetd([msg("secret"), {"type": "success"},
                                {"type": "error", "error_type": "error"}, {"type": "success"}])
            try:
                # Même fenêtre que l'aperçu, sans fullscreen ni socket/session réels.
                app.preview = False
                app.flow = AuthFlow(first.path)
                app.selector.set_model(Gtk.StringList.new(["example", "other", "Autre utilisateur…"]))
                app.selection_ready = True
                app.user_changed()
                self.pump(lambda: not app.busy)
                self.assertEqual(app.flow.selection, "mosaic")
                app.entry.set_text(SECRET)
                app.submit()
                self.assertTrue(entered.wait(2))
                for widget in (app.selector, app.session_selector, app.manual, app.button, app.entry):
                    self.assertFalse(widget.get_sensitive())
                app.submit()  # double clic : aucun deuxième worker/réponse
                release.set()
                self.pump(lambda: not app.busy)
                self.assertIsNone(app.flow.client)
                self.assertTrue(app.session_selector.get_sensitive())
                self.assertEqual(len([r for r in first.requests if r["type"] == "post_auth_message_response"]), 1)
                app.flow.socket_path = second.path
                app.session_selector.set_selected(0)
                self.pump(lambda: not app.busy)
                self.assertEqual(app.flow.selection, "stable")
                app.entry.set_text(SECRET)
                app.submit()
                self.pump(lambda: not app.busy and "Lancement" in app.error.get_text())
                self.assertIsNone(app.flow.client)
                self.assertEqual(second.requests[-2], {"type": "start_session", "cmd": STABLE, "env": []})
                self.assertTrue(app.selector.get_sensitive())
            finally:
                release.set()
                first.close()
                second.close()
        finally:
            app.preview = True
            app.window.destroy()
            app.quit()


if __name__ == "__main__":
    unittest.main()

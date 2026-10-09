"""Isolated session-bus tests for the ScreenSaver/QuickShell bridge.

Run with ``python tests/test_idle_bridge.py``; it creates its own private bus.
The fake QuickShell owns only a private Unix socket; no daily bus is touched.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "quickshell/.config/quickshell/labfy-sway/idlebridge/bridge.py"
NAME = "org.freedesktop.ScreenSaver"
PATH = "/org/freedesktop/ScreenSaver"


class FakeShell:
    def __init__(self, path):
        self.path = str(path)
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(self.path)
        self.listener.listen(2)
        self.listener.settimeout(0.25)
        self.lock = threading.Condition()
        self.counts = []
        self.connection = None
        self.running = True
        self.ack = True
        self.pending = []
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while self.running:
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn.settimeout(0.25)
            with self.lock:
                self.connection = conn
                self.counts.append(0)  # QuickShell drops state on connect.
                self.lock.notify_all()
            data = bytearray()
            while self.running:
                try:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data.extend(chunk)
                    while b"\n" in data:
                        line, _, rest = data.partition(b"\n")
                        data = bytearray(rest)
                        frame = json.loads(line)
                        with self.lock:
                            self.counts.append(frame["count"])
                            answer = {"type": "ack", "generation": frame["generation"],
                                      "sequence": frame["sequence"], "applied": True}
                            if self.ack:
                                conn.sendall((json.dumps(answer) + "\n").encode())
                            else:
                                self.pending.append(answer)
                            self.lock.notify_all()
                except socket.timeout:
                    continue
                except OSError:
                    break
            with self.lock:
                if self.connection is conn:
                    self.connection = None
                    self.counts.append(0)  # QuickShell drops state on disconnect.
                    self.lock.notify_all()
            conn.close()

    def wait_count(self, count, after=0, timeout=5):
        end = time.monotonic() + timeout
        with self.lock:
            while True:
                if count in self.counts[after:]:
                    return len(self.counts)
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f"count {count} absent after {after}: {self.counts}")
                self.lock.wait(remaining)

    def release_ack(self):
        with self.lock:
            while self.pending and self.connection:
                frame = self.pending.pop(0)
                self.connection.sendall((json.dumps(frame) + "\n").encode())
            self.ack = True

    def disconnect(self):
        with self.lock:
            if self.connection:
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def close(self):
        self.running = False
        self.disconnect()
        self.listener.close()
        self.thread.join(timeout=2)


def bus_connection():
    return Gio.DBusConnection.new_for_address_sync(
        os.environ["DBUS_SESSION_BUS_ADDRESS"],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)


def call(conn, method, signature, args, result):
    return conn.call_sync(NAME, PATH, NAME, method, GLib.Variant(signature, args),
                          GLib.VariantType.new(result), Gio.DBusCallFlags.NONE, 3000, None).unpack()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="idle-bridge-test-")
        self.path = Path(self.temp.name) / "shell.sock"
        self.shell = FakeShell(self.path)
        env = dict(os.environ, LABFY_IDLE_BRIDGE_SOCKET=str(self.path), XDG_RUNTIME_DIR=self.temp.name)
        self.proc = subprocess.Popen([sys.executable, str(BRIDGE)], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.a = bus_connection()
        self.b = bus_connection()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            try:
                if bus_connection().call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                     "org.freedesktop.DBus", "NameHasOwner", GLib.Variant("(s)", (NAME,)),
                     GLib.VariantType.new("(b)"), Gio.DBusCallFlags.NONE, 500, None).unpack()[0]:
                    break
            except GLib.Error:
                pass
            time.sleep(0.05)
        else:
            raise AssertionError(f"bridge did not acquire name: {self.proc.poll()}")
        self.shell.wait_count(0)
        # Wait for the initial snapshot acknowledgment to reach the helper.
        for _ in range(30):
            try:
                call(self.a, "Inhibit", "(ss)", ("test", "one"), "(u)")
                self.shell.wait_count(1)
                break
            except GLib.Error:
                time.sleep(0.05)
        else:
            raise AssertionError("bridge did not become ready")
        # The setup request belongs to client A and is removed before each test.
        first = max(self.shell.counts)
        self.assertEqual(first, 1)
        # The only active cookie is obtained from the last test call by using
        # a dedicated second fresh setup in each test would be wasteful. Close
        # A and reopen it, relying on NameOwnerChanged cleanup.
        self.a.close_sync(None)
        self.shell.wait_count(0, after=2)
        self.a = bus_connection()

    def tearDown(self):
        for conn in (self.a, self.b):
            try:
                conn.close_sync(None)
            except GLib.Error:
                pass
        self.proc.terminate()
        try:
            self.proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.communicate()
        self.shell.close()
        self.temp.cleanup()

    def test_independent_cookies_and_ownership(self):
        start = len(self.shell.counts)
        one = call(self.a, "Inhibit", "(ss)", ("", ""), "(u)")[0]
        self.shell.wait_count(1, start)
        two = call(self.a, "Inhibit", "(ss)", ("same", "same"), "(u)")[0]
        self.shell.wait_count(2, start)
        three = call(self.b, "Inhibit", "(ss)", ("same", "same"), "(u)")[0]
        self.shell.wait_count(3, start)
        self.assertEqual(len({one, two, three}), 3)
        self.assertTrue(all((one, two, three)))
        with self.assertRaises(GLib.Error):
            call(self.b, "UnInhibit", "(u)", (one,), "()")
        self.assertEqual(self.shell.counts[-1], 3)
        call(self.a, "UnInhibit", "(u)", (one,), "()")
        self.shell.wait_count(2, start)
        with self.assertRaises(GLib.Error):
            call(self.a, "UnInhibit", "(u)", (one,), "()")
        with self.assertRaises(GLib.Error):
            call(self.a, "UnInhibit", "(u)", (0,), "()")
        self.a.close_sync(None)
        self.shell.wait_count(1, start)
        call(self.b, "UnInhibit", "(u)", (three,), "()")
        self.shell.wait_count(0, start)
        self.a = bus_connection()

    def test_reconnect_and_conflict(self):
        cookie = call(self.a, "Inhibit", "(ss)", ("test", "hold"), "(u)")[0]
        self.shell.wait_count(1)
        rival = subprocess.run([sys.executable, str(BRIDGE)], env=dict(os.environ,
            LABFY_IDLE_BRIDGE_SOCKET=str(self.path), XDG_RUNTIME_DIR=self.temp.name),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3)
        self.assertEqual(rival.returncode, 2)
        self.shell.disconnect()
        self.shell.wait_count(0, after=len(self.shell.counts) - 1)
        self.shell.wait_count(1, after=len(self.shell.counts) - 1, timeout=5)
        call(self.a, "UnInhibit", "(u)", (cookie,), "()")
        self.shell.wait_count(0)

    def test_cancel_before_ack(self):
        with self.shell.lock:
            self.shell.ack = False
        # Async D-Bus call lets the test close the caller while QuickShell has
        # seen the provisional count but has not acknowledged it.
        done = threading.Event()
        self.a.call(NAME, PATH, NAME, "Inhibit", GLib.Variant("(ss)", ("test", "hold")),
                    GLib.VariantType.new("(u)"), Gio.DBusCallFlags.NONE, 3000, None,
                    lambda *_args: done.set())
        mark = len(self.shell.counts)
        self.shell.wait_count(1, mark)
        self.a.close_sync(None)
        self.a = bus_connection()
        self.shell.release_ack()
        self.shell.wait_count(0, mark)

    def test_unavailable_shell_fails_new_acquisition(self):
        self.shell.close()
        time.sleep(0.4)
        with self.assertRaises(GLib.Error):
            call(self.a, "Inhibit", "(ss)", ("test", "hold"), "(u)")

    def test_cookie_not_reused_after_bridge_restart(self):
        first = call(self.a, "Inhibit", "(ss)", ("test", "hold"), "(u)")[0]
        call(self.a, "UnInhibit", "(u)", (first,), "()")
        self.proc.terminate()
        self.proc.communicate(timeout=3)
        env = dict(os.environ, LABFY_IDLE_BRIDGE_SOCKET=str(self.path), XDG_RUNTIME_DIR=self.temp.name)
        self.proc = subprocess.Popen([sys.executable, str(BRIDGE)], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        end = time.monotonic() + 5
        while time.monotonic() < end:
            try:
                second = call(self.a, "Inhibit", "(ss)", ("test", "again"), "(u)")[0]
                break
            except GLib.Error:
                time.sleep(0.05)
        else:
            raise AssertionError("restarted bridge did not become ready")
        self.assertGreater(second, first)
        with self.assertRaises(GLib.Error):
            call(self.a, "UnInhibit", "(u)", (first,), "()")
        call(self.a, "UnInhibit", "(u)", (second,), "()")


if __name__ == "__main__":
    if os.environ.get("LABFY_IDLE_BRIDGE_PRIVATE_BUS") != "1":
        result = subprocess.run(["dbus-run-session", "--", "env",
            "LABFY_IDLE_BRIDGE_PRIVATE_BUS=1", sys.executable,
            str(Path(__file__).resolve()), *sys.argv[1:]])
        sys.exit(result.returncode)
    unittest.main()

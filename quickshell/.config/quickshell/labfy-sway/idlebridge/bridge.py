#!/usr/bin/env python3
"""Bridge the session ScreenSaver inhibit API to QuickShell's Wayland surface.

CONTRACT: this process owns cookies and D-Bus caller lifetimes; QuickShell owns
the only Wayland IdleInhibitor. No request state is persisted across restarts.
"""

import json
import os
import socket
import stat
import struct
import sys
import uuid
from collections import deque

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


NAME = "org.freedesktop.ScreenSaver"
PATH = "/org/freedesktop/ScreenSaver"
IFACE = NAME
MAX_REQUESTS = 256
MAX_QUEUE = 256
MAX_TEXT_BYTES = 512
MAX_FRAME = 4096
ACK_SECONDS = 3
XML = """<node>
  <interface name="org.freedesktop.ScreenSaver">
    <method name="Inhibit">
      <arg name="application_name" type="s" direction="in"/>
      <arg name="reason_for_inhibit" type="s" direction="in"/>
      <arg name="cookie" type="u" direction="out"/>
    </method>
    <method name="UnInhibit">
      <arg name="cookie" type="u" direction="in"/>
    </method>
  </interface>
</node>"""


class Bridge:
    def __init__(self, socket_path, runtime):
        self.socket_path = socket_path
        self.runtime = runtime
        self.counter_path = os.path.join(runtime, "labfy-idle-bridge.counter")
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.loop = GLib.MainLoop()
        self.requests = {}  # cookie -> unique D-Bus sender; labels are never retained.
        self.queue = deque()
        self.current = None
        self.dirty = False
        self.sock = None
        self.watch = None
        self.retry = None
        self.ack_timer = None
        self.inbuf = bytearray()
        self.outbuf = bytearray()
        self.generation = uuid.uuid4().hex
        self.sequence = 0
        self.awaiting_sequence = None
        self.ready = False
        # CONTRACT: only the next cookie number, never an inhibition request,
        # persists in the session runtime dir. A stale UnInhibit after helper
        # restart cannot release a newer request in the same D-Bus session.
        self.next_cookie = self.read_counter() + 1

    def read_counter(self):
        try:
            fd = os.open(self.counter_path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return 0
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 11:
                raise RuntimeError("invalid cookie counter file")
            data = os.read(fd, 12)
            if not data.endswith(b"\n") or not data[:-1].isdigit():
                raise RuntimeError("corrupt cookie counter file")
            value = int(data[:-1])
            if value > 0xFFFFFFFF:
                raise RuntimeError("cookie counter out of range")
            return value
        finally:
            os.close(fd)

    def persist_cookie(self, cookie):
        # WHY: write/rename/fsync precedes the D-Bus success reply. A crash
        # can skip a number but cannot roll back a cookie already returned.
        temporary = self.counter_path + f".tmp.{os.getpid()}"
        data = f"{cookie}\n".encode("ascii")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                if os.write(fd, data) != len(data):
                    raise OSError("short cookie counter write")
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, self.counter_path)
        except OSError:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        directory = os.open(self.runtime, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def has_owner(self, name):
        reply = self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                   "org.freedesktop.DBus", "NameHasOwner",
                                   GLib.Variant("(s)", (name,)), GLib.VariantType.new("(b)"),
                                   Gio.DBusCallFlags.NONE, 1000, None)
        return reply.unpack()[0]

    def start(self):
        if self.has_owner(NAME):
            raise NameConflict("org.freedesktop.ScreenSaver already has an owner")
        info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        self.bus.register_object(PATH, info, self.on_method, None, None)
        # WHY: GTK's proxy uses DO_NOT_AUTO_START. A session service must own
        # the name proactively; RequestName without REPLACE_EXISTING cannot
        # steal it from another implementation in the check/acquire race.
        reply = self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                   "org.freedesktop.DBus", "RequestName",
                                   GLib.Variant("(su)", (NAME, 4)),
                                   GLib.VariantType.new("(u)"),
                                   Gio.DBusCallFlags.NONE, 1000, None)
        if reply.unpack()[0] != 1:
            raise NameConflict("org.freedesktop.ScreenSaver name acquisition failed")
        self.bus.signal_subscribe("org.freedesktop.DBus", "org.freedesktop.DBus",
                                  "NameOwnerChanged", "/org/freedesktop/DBus", None,
                                  Gio.DBusSignalFlags.NONE, self.on_name_owner_changed)
        self.bus.connect("closed", self.on_bus_closed)
        self.connect_socket()
        self.loop.run()

    def on_bus_closed(self, *_args):
        self.loop.quit()

    @staticmethod
    def fail(invocation, name, message):
        try:
            invocation.return_dbus_error(name, message)
        except Exception:
            pass  # The unique D-Bus caller may already have disconnected.

    def on_method(self, _connection, sender, _path, _interface, method, params, invocation):
        if method == "Inhibit":
            app, reason = params.unpack()
            if len(app.encode("utf-8")) > MAX_TEXT_BYTES or len(reason.encode("utf-8")) > MAX_TEXT_BYTES:
                return self.fail(invocation, "org.freedesktop.DBus.Error.LimitsExceeded", "label too long")
            if not self.ready or len(self.queue) >= MAX_QUEUE or len(self.requests) >= MAX_REQUESTS:
                return self.fail(invocation, "org.freedesktop.DBus.Error.LimitsExceeded"
                                 if self.ready else "org.freedesktop.DBus.Error.NoReply",
                                 "bridge unavailable or full")
            self.queue.append({"kind": "add", "sender": sender, "invocation": invocation})
            self.advance()
        elif method == "UnInhibit":
            cookie = params.unpack()[0]
            owner = self.requests.get(cookie)
            if owner is None:
                return self.fail(invocation, "org.freedesktop.DBus.Error.InvalidArgs", "unknown cookie")
            if owner != sender:
                return self.fail(invocation, "org.freedesktop.DBus.Error.AccessDenied", "cookie owner differs")
            if not self.ready:
                # CONTRACT: never retain an orphan merely because QuickShell
                # is down. Its socket disconnect already cleared the surface.
                del self.requests[cookie]
                self.dirty = True
                return self.fail(invocation, "org.freedesktop.DBus.Error.NoReply",
                                 "QuickShell unavailable during release")
            if len(self.queue) >= MAX_QUEUE:
                return self.fail(invocation, "org.freedesktop.DBus.Error.LimitsExceeded", "bridge queue full")
            self.queue.append({"kind": "remove", "sender": sender,
                               "cookie": cookie, "invocation": invocation})
            self.advance()

    def advance(self):
        if self.current or self.awaiting_sequence is not None or not self.ready:
            return
        if self.dirty:
            self.dirty = False
            self.snapshot(None)
            return
        while self.queue:
            op = self.queue.popleft()
            if not self.has_owner(op["sender"]):
                self.fail(op["invocation"], "org.freedesktop.DBus.Error.NameHasNoOwner",
                          "requester disconnected")
                continue
            if op["kind"] == "add":
                if len(self.requests) >= MAX_REQUESTS or self.next_cookie > 0xFFFFFFFF:
                    self.fail(op["invocation"], "org.freedesktop.DBus.Error.LimitsExceeded",
                              "cookie capacity exhausted")
                    continue
                op["cookie"] = self.next_cookie
                self.next_cookie += 1
                try:
                    self.persist_cookie(op["cookie"])
                except OSError:
                    self.fail(op["invocation"], "org.freedesktop.DBus.Error.Failed",
                              "cookie counter could not be persisted")
                    continue
                self.requests[op["cookie"]] = op["sender"]
            else:
                if self.requests.get(op["cookie"]) != op["sender"]:
                    self.fail(op["invocation"], "org.freedesktop.DBus.Error.InvalidArgs",
                              "cookie already released")
                    continue
                del self.requests[op["cookie"]]
            self.current = op
            self.snapshot(op)
            return

    def snapshot(self, op):
        if not self.sock:
            return self.disconnect()
        self.sequence += 1
        self.awaiting_sequence = self.sequence
        frame = {"type": "snapshot", "version": 1, "generation": self.generation,
                 "sequence": self.sequence, "count": len(self.requests)}
        self.outbuf.extend((json.dumps(frame, separators=(",", ":")) + "\n").encode())
        self.update_watch()
        self.ack_timer = GLib.timeout_add_seconds(ACK_SECONDS, self.on_ack_timeout)

    def on_ack_timeout(self):
        self.ack_timer = None
        self.disconnect()
        return GLib.SOURCE_REMOVE

    def on_name_owner_changed(self, _bus, _sender, _path, _interface, _signal, params):
        name, _old, new = params.unpack()
        if not name.startswith(":") or new:
            return
        old_count = len(self.requests)
        for cookie, owner in list(self.requests.items()):
            if owner == name:
                del self.requests[cookie]
        for op in list(self.queue):
            if op["sender"] == name:
                self.queue.remove(op)
                self.fail(op["invocation"], "org.freedesktop.DBus.Error.NameHasNoOwner",
                          "requester disconnected")
        if self.current and self.current["sender"] == name:
            self.current["cancelled"] = True
        if len(self.requests) != old_count:
            self.dirty = True
        self.advance()

    def connect_socket(self):
        self.retry = None
        if self.sock:
            return GLib.SOURCE_REMOVE
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.15)
        try:
            sock.connect(self.socket_path)
            # The runtime directory is 0700, and SO_PEERCRED also rejects a
            # misdirected path served by a different Unix uid.
            uid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET,
                                socket.SO_PEERCRED, struct.calcsize("3i")))[1]
            if uid != os.getuid():
                raise PermissionError("QuickShell socket uid differs")
        except (OSError, PermissionError):
            sock.close()
            self.retry = GLib.timeout_add_seconds(1, self.connect_socket)
            return GLib.SOURCE_REMOVE
        sock.setblocking(False)
        self.sock = sock
        self.ready = False
        self.inbuf.clear()
        self.outbuf.clear()
        self.update_watch()
        self.snapshot(None)  # Complete initial state before accepting calls.
        return GLib.SOURCE_REMOVE

    def update_watch(self):
        if self.watch:
            GLib.source_remove(self.watch)
        condition = GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR
        if self.outbuf:
            condition |= GLib.IO_OUT
        self.watch = GLib.io_add_watch(self.sock.fileno(), condition, self.on_socket_event)

    def on_socket_event(self, _fd, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            self.disconnect()
            return GLib.SOURCE_REMOVE
        try:
            if condition & GLib.IO_OUT and self.outbuf:
                sent = self.sock.send(self.outbuf)
                del self.outbuf[:sent]
            if condition & GLib.IO_IN:
                chunk = self.sock.recv(1024)
                if not chunk:
                    self.disconnect()
                    return GLib.SOURCE_REMOVE
                self.inbuf.extend(chunk)
                if len(self.inbuf) > MAX_FRAME:
                    self.disconnect()
                    return GLib.SOURCE_REMOVE
                while b"\n" in self.inbuf:
                    line, _, rest = self.inbuf.partition(b"\n")
                    self.inbuf = bytearray(rest)
                    self.on_frame(line)
        except (OSError, ValueError):
            self.disconnect()
            return GLib.SOURCE_REMOVE
        if self.sock:
            self.update_watch()
        return GLib.SOURCE_REMOVE

    def on_frame(self, line):
        try:
            frame = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return self.disconnect()
        if (not isinstance(frame, dict) or frame.get("type") != "ack"
                or frame.get("generation") != self.generation
                or type(frame.get("sequence")) is not int
                or frame["sequence"] != self.awaiting_sequence
                or frame.get("applied") is not True):
            return self.disconnect()
        if self.ack_timer:
            GLib.source_remove(self.ack_timer)
            self.ack_timer = None
        self.awaiting_sequence = None
        op = self.current
        self.current = None
        if op is None:
            self.ready = True
        elif op.get("cancelled") or not self.has_owner(op["sender"]):
            if op["kind"] == "add":
                self.requests.pop(op["cookie"], None)
                self.dirty = True
            self.fail(op["invocation"], "org.freedesktop.DBus.Error.NameHasNoOwner",
                      "requester disconnected")
        elif op["kind"] == "add":
            op["invocation"].return_value(GLib.Variant("(u)", (op["cookie"],)))
        else:
            op["invocation"].return_value(GLib.Variant("()", ()))
        self.advance()

    def disconnect(self):
        if self.ack_timer:
            GLib.source_remove(self.ack_timer)
            self.ack_timer = None
        if self.watch:
            GLib.source_remove(self.watch)
            self.watch = None
        if self.sock:
            self.sock.close()
            self.sock = None
        self.ready = False
        self.awaiting_sequence = None
        self.inbuf.clear()
        self.outbuf.clear()
        # WHY: QuickShell clears the application contribution on disconnect.
        # Roll back an unacknowledged transaction before the next full snapshot.
        if self.current:
            op = self.current
            self.current = None
            if op["kind"] == "add":
                self.requests.pop(op["cookie"], None)
            elif not op.get("cancelled") and self.has_owner(op["sender"]):
                self.requests[op["cookie"]] = op["sender"]
            self.fail(op["invocation"], "org.freedesktop.DBus.Error.NoReply",
                      "QuickShell did not acknowledge")
        while self.queue:
            op = self.queue.popleft()
            self.fail(op["invocation"], "org.freedesktop.DBus.Error.NoReply",
                      "QuickShell unavailable")
        self.dirty = False
        if not self.retry:
            self.retry = GLib.timeout_add_seconds(1, self.connect_socket)


class NameConflict(RuntimeError):
    pass


def main():
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not runtime or not os.path.isabs(runtime):
        raise RuntimeError("XDG_RUNTIME_DIR must be absolute")
    info = os.stat(runtime)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError("XDG_RUNTIME_DIR must be private to this user")
    path = os.environ.get("LABFY_IDLE_BRIDGE_SOCKET", os.path.join(runtime, "labfy-idle-bridge.sock"))
    if not os.path.isabs(path):
        raise RuntimeError("socket path must be absolute")
    Bridge(path, runtime).start()


if __name__ == "__main__":
    try:
        main()
    except NameConflict as error:
        print(f"idle bridge: {error}", file=sys.stderr)
        sys.exit(2)
    except (GLib.Error, RuntimeError) as error:
        print(f"idle bridge: {error}", file=sys.stderr)
        sys.exit(1)

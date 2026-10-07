"""Laboratoire headless Phase 2 ; sockets explicites, enfants possédés et bornés."""
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
from headless import Lab as BaseLab, walk


def until(function, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = function()
        if value:
            return value
        time.sleep(.02)
    raise TimeoutError("TEST_ONLY_TIMEOUT")


class IPC:
    def __init__(self, path):
        self.socket = path
        if not path.startswith("/tmp/labfy-session-v2-TEST_ONLY-"):
            raise ValueError("NON_TEST_SOCKET_FORBIDDEN")

    def ipc(self, command=None, kind=None):
        message_type = {"get_tree": 4, "get_outputs": 3, "get_workspaces": 1, "get_version": 7}.get(kind, 0)
        payload = (command or "").encode()
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3)
            connection.connect(self.socket)
            connection.sendall(struct.pack("<6sII", b"i3-ipc", len(payload), message_type) + payload)
            def read(n):
                data = bytearray()
                while len(data) < n:
                    part = connection.recv(n - len(data))
                    if not part: raise RuntimeError("IPC_CLOSED")
                    data.extend(part)
                return bytes(data)
            magic, size, _ = struct.unpack("<6sII", read(14))
            if magic != b"i3-ipc" or size > 4 * 1024 * 1024:
                raise ValueError("IPC_BOUNDS")
            return json.loads(read(size))

    def command(self, command):
        result = self.ipc(command)
        if not result or not all(x.get("success") for x in result):
            raise RuntimeError((command, result))
        return result

    def tree(self): return self.ipc(kind="get_tree")
    def windows(self): return [n for n in walk(self.tree()) if n.get("app_id")]


class Lab(BaseLab):
    def ipc(self, command=None, kind=None):
        return IPC(self.socket).ipc(command, kind)

    def spawn(self, argv, stdin=None, env=None, pass_fds=()):
        log = (self.directory / f"p2-{len(self.children)}.log").open("w")
        self.logs.append(log)
        process = subprocess.Popen(argv, stdin=stdin, stdout=log, stderr=log,
                                   env=env or self.env, start_new_session=True, pass_fds=pass_fds)
        self.children.append(process)
        return process


class Surfaces:
    def __init__(self, lab, binary):
        self.lab = lab
        self.proc = lab.spawn([str(binary)], stdin=subprocess.PIPE)
        self.pidfd = os.pidfd_open(self.proc.pid)
        self.ids = set()

    def create(self, app_id):
        before = {n["id"] for n in self.lab.windows()}
        self.proc.stdin.write(f"create {app_id}\n".encode())
        self.proc.stdin.flush()
        found = until(lambda: [n for n in self.lab.windows() if n["id"] not in before
                              and n["pid"] == self.proc.pid and n["app_id"] == app_id])
        if len(found) != 1: raise ValueError("SURFACE_AMBIGUOUS")
        self.ids.add(found[0]["id"])
        return found[0]

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.write(b"quit\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=5)
        until(lambda: not any(n["id"] in self.ids for n in self.lab.windows()))
        self.proc.stdin.close()
        os.close(self.pidfd)


def build_helper(directory):
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "gtk+-3.0", "gdk-wayland-3.0"],
                           text=True, capture_output=True, check=True).stdout.split()
    binary = directory / "TEST_ONLY_surfaces"
    subprocess.run(["cc", "-std=c17", "-Wall", "-Wextra", "-Werror", str(ROOT / "surfaces.c"), "-o", str(binary), *flags], check=True)
    return binary


def workspace_node(tree, name):
    return next((n for n in walk(tree) if n.get("type") == "workspace" and n.get("name") == name), None)


def location(tree, identity):
    def search(node, workspace=None, path=()):
        if node.get("type") == "workspace":
            workspace, path = node["name"], ()
        if node["id"] == identity:
            return workspace, path
        for i, child in enumerate(node.get("nodes", [])):
            found = search(child, workspace, path + (i,))
            if found: return found
    return search(tree)


def shape(tree, name, mapping):
    node = workspace_node(tree, name)
    if not node: return None
    def normalize(n):
        if n.get("app_id"):
            return mapping.get(n["id"], "UNEXPECTED:" + n["app_id"])
        children = [normalize(c) for c in n.get("nodes", [])]
        if len(children) == 1 and n["layout"] in ("splith", "splitv", "none"):
            return children[0]
        return {n["layout"]: children}
    return normalize(node)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

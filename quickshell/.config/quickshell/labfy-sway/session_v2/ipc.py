"""Sway IPC explicite et borné. Le socket identifie la session, pas un PID persisté."""
import hashlib
import json
import os
import socket
import stat
import struct
import time
from .errors import Failure, require


def walk(node):
    yield node
    for c in node.get("nodes", []) + node.get("floating_nodes", []): yield from walk(c)


def until(fn, timeout=5, code="RUNTIME_TIMEOUT"):
    end = time.monotonic() + timeout
    while True:
        value = fn()
        if value: return value
        if time.monotonic() >= end: raise Failure(code)
        time.sleep(.025)


class Sway:
    def __init__(self, path):
        require(type(path) is str and os.path.isabs(path), "SWAY_SOCKET_INVALID")
        st = os.lstat(path)
        require(stat.S_ISSOCK(st.st_mode) and st.st_uid == os.getuid(), "SWAY_SOCKET_INVALID")
        self.path = path
        self.identity = (st.st_dev, st.st_ino)
        self.session = hashlib.sha256(f"{path}:{st.st_dev}:{st.st_ino}:{st.st_ctime_ns}".encode()).hexdigest()

    def request(self, kind, payload=b""):
        st = os.lstat(self.path)
        require((st.st_dev, st.st_ino) == self.identity and st.st_uid == os.getuid(), "SWAY_SESSION_CHANGED")
        with socket.socket(socket.AF_UNIX) as connection:
            end = time.monotonic() + 3
            connection.settimeout(3)
            connection.connect(self.path)
            _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            require(uid == os.getuid(), "SWAY_PEER_INVALID")
            connection.sendall(struct.pack("<6sII", b"i3-ipc", len(payload), kind) + payload)
            def take(n):
                result = bytearray()
                while len(result) < n:
                    require(time.monotonic() < end, "IPC_TIMEOUT")
                    connection.settimeout(max(.001, end - time.monotonic()))
                    part = connection.recv(n - len(result))
                    require(part, "IPC_CLOSED")
                    result.extend(part)
                return result
            magic, size, answer = struct.unpack("<6sII", take(14))
            require(magic == b"i3-ipc" and answer == kind and size <= 4 * 1024 * 1024, "IPC_BOUNDS")
            return json.loads(take(size))

    def tree(self): return self.request(4)
    def outputs(self): return self.request(3)
    def windows(self): return [n for n in walk(self.tree()) if n.get("app_id") or n.get("window")]
    def command(self, text):
        result = self.request(0, text.encode())
        require(result and all(r.get("success") for r in result), "SWAY_COMMAND_FAILED")


def location(tree, identity):
    def find(node, ws=None, path=()):
        if node.get("type") == "workspace": ws, path = node["name"], ()
        if node["id"] == identity: return ws, path
        for i, c in enumerate(node.get("nodes", [])):
            found = find(c, ws, path + (i,))
            if found: return found
        for c in node.get("floating_nodes", []):
            found = find(c, ws, ())
            if found: return found
    return find(tree)


def workspace(tree, name):
    return next((n for n in walk(tree) if n.get("type") == "workspace" and n.get("name") == name), None)


def canonical(tree, name, mapping):
    ws = workspace(tree, name)
    if not ws or not ws["nodes"]: return None
    def norm(node):
        if node.get("app_id") or node.get("window"): return mapping.get(node["id"], "UNEXPECTED")
        children = [norm(c) for c in node.get("nodes", [])]
        if len(children) == 1 and node["layout"] in ("splith", "splitv", "none"): return children[0]
        return {node["layout"]: children}
    return norm(ws)

#!/usr/bin/env python3
"""Expériences TEST_ONLY ; jamais importé ni lancé par le code de production.

CONTRAT : IPC exclusivement vers le socket du compositeur enfant headless.
Les seuls processus arrêtés sont des enfants détenus par cette expérience.
Les arbres conservés ne contiennent que des fenêtres synthétiques.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent


def run(argv, **kwargs):
    return subprocess.run(argv, text=True, capture_output=True, timeout=10, **kwargs)


def walk(node):
    yield node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        yield from walk(child)


class Lab:
    def __init__(self):
        self.directory = Path(tempfile.mkdtemp(prefix="labfy-session-v2-TEST_ONLY-"))
        self.children = []
        self.logs = []
        self.socket = None
        self.env = dict(os.environ)
        for key in ("SWAYSOCK", "I3SOCK", "DISPLAY", "WAYLAND_DISPLAY"):
            self.env.pop(key, None)
        self.env.update(XDG_RUNTIME_DIR=str(self.directory), TMPDIR=str(self.directory), WLR_BACKENDS="headless",
                        WLR_HEADLESS_OUTPUTS="1", WLR_RENDERER="gles2",
                        WLR_RENDERER_ALLOW_SOFTWARE="1", LIBGL_ALWAYS_SOFTWARE="true")

    def start(self, argv):
        log = (self.directory / f"child-{len(self.children)}.log").open("w")
        self.logs.append(log)
        proc = subprocess.Popen(argv, env=self.env, stdout=log, stderr=log,
                                start_new_session=True)
        self.children.append(proc)
        return proc

    def __enter__(self):
        try:
            self.sway = self.start(["sway", "-c", str(ROOT / "headless.conf")])
            end = time.monotonic() + 15
            while time.monotonic() < end:
                sockets = list(self.directory.glob("sway-ipc.*.sock"))
                displays = [p for p in self.directory.glob("wayland-*") if p.is_socket()]
                if sockets and displays:
                    self.socket = str(sockets[0])
                    self.env.update(SWAYSOCK=self.socket, WAYLAND_DISPLAY=displays[0].name)
                    self.tree()
                    return self
                if self.sway.poll() is not None:
                    raise RuntimeError((self.directory / "child-0.log").read_text()[-6000:])
                time.sleep(.1)
            raise RuntimeError("Délai de démarrage headless dépassé")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def ipc(self, command=None, kind=None):
        assert self.socket and self.socket.startswith(str(self.directory) + "/")
        args = ["swaymsg", "-s", self.socket, "-r"]
        args += ["-t", kind] if kind else [command]
        result = run(args, env=self.env)
        return json.loads(result.stdout)

    def command(self, text):
        reply = self.ipc(text)
        if not all(item.get("success") for item in reply):
            raise RuntimeError((text, reply))
        return reply

    def tree(self):
        return self.ipc(kind="get_tree")

    def windows(self):
        return [n for n in walk(self.tree()) if n.get("app_id")]

    def kitty(self, identity):
        before = {n["id"] for n in self.windows()}
        self.start(["kitty", "--config", "NONE", "--class", identity,
                    "--title", "TEST_ONLY", "-o", "linux_display_server=wayland",
                    "-o", "confirm_os_window_close=0", "/usr/bin/sleep", "180"])
        end = time.monotonic() + 10
        while time.monotonic() < end:
            found = [n for n in self.windows() if n["id"] not in before and n["app_id"] == identity]
            if len(found) == 1:
                return found[0]["id"]
            time.sleep(.1)
        raise RuntimeError("Fenêtre Kitty TEST_ONLY absente")

    def empty(self, workspace):
        old = self.windows()
        for n in old:
            assert n["app_id"].startswith("TEST_ONLY")
            self.command(f'[con_id={n["id"]}] kill')
        self.wait_absent([n["id"] for n in old])
        self.command(f'workspace "{workspace}"')
        time.sleep(.15)

    def wait_absent(self, ids):
        # Une réponse IPC à kill ne prouve pas encore le retrait du top-level.
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if not set(ids).intersection(n["id"] for n in self.windows()):
                return
            time.sleep(.05)
        raise RuntimeError("Fenêtre TEST_ONLY encore présente après fermeture")

    def shape(self, workspace):
        def node(n):
            if n.get("app_id"):
                return n["app_id"]
            children = [node(c) for c in n.get("nodes", [])]
            if len(children) == 1:
                return children[0]
            return {n.get("layout"): children}
        found = [n for n in walk(self.tree()) if n.get("type") == "workspace" and n.get("name") == workspace]
        return node(found[0]) if found else None

    def __exit__(self, *_):
        # INVARIANT : même après exception, aucun helper détenu ne reste stoppé.
        for proc in reversed(self.children):
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGCONT)
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=3)
        for log in self.logs:
            log.close()

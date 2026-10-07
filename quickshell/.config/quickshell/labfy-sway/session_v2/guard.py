"""Watchdog externe : reprise ne dépendant jamais du finally de l'executor.

CONTRACT : PIDFD hérités, UID/executable/script/SWAYSOCK vérifiés avant signal.
Le lock de transaction est hérité : pas de tentative concurrente pendant recovery.
INVARIANT : un helper initialement stoppé n'est jamais repris par Labfy.
Limite : la mort simultanée du watchdog/compositeur n'est pas une transaction ACID.
"""
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import sys
import time
from .errors import require
from .ipc import Sway, until
from .storage import atomic, read, loads


def helper_state(pid): return Path(f"/proc/{pid}/status").read_text().split("State:\t", 1)[1][0]


def verify_helper(pid, sway_socket, script):
    root = Path(f"/proc/{pid}")
    require(root.stat().st_uid == os.getuid(), "HELPER_UID_INVALID")
    argv = (root / "cmdline").read_bytes().split(b"\0")
    expected_exe = str(Path(sys.executable).resolve())
    require(str((root / "exe").resolve()) == expected_exe, "HELPER_EXECUTABLE_INVALID")
    require(len(argv) > 1 and os.fsdecode(argv[1]) == script, "HELPER_SCRIPT_INVALID")
    with (root / "environ").open("rb") as stream: env = stream.read(65537)
    require(len(env) <= 65536 and (b"SWAYSOCK=" + os.fsencode(sway_socket)) in env.split(b"\0"), "HELPER_SESSION_INVALID")


def discover(sway_socket):
    script = shutil.which("autotiling")
    if not script: return []
    script = os.path.abspath(script)
    helpers = []
    for root in Path("/proc").iterdir():
        if not root.name.isdigit(): continue
        fd = None
        try:
            verify_helper(int(root.name), sway_socket, script)
            fd = os.pidfd_open(int(root.name))
            verify_helper(int(root.name), sway_socket, script)
            helpers.append({"pid": int(root.name), "fd": fd, "script": script})
            fd = None
        except Exception as exc:
            # Les autres processus ne sont ni des erreurs de restore, ni ciblés.
            from .errors import Failure
            if not isinstance(exc, (OSError, ValueError, Failure)): raise
        finally:
            if fd is not None: os.close(fd)
    if len(helpers) > 8:
        for h in helpers: os.close(h["fd"])
        require(False, "HELPER_COUNT_LIMIT")
    return helpers


class Guard:
    def __init__(self, sway, anchors, runtime, report_path, lock_fd, deadline=120):
        self.helpers = discover(sway.path)
        self.parent, child = socket.socketpair(type=socket.SOCK_SEQPACKET)
        engine_fd = os.pidfd_open(os.getpid())
        read_fd, write_fd = os.pipe()
        config = {"socket": sway.path, "engine_fd": engine_fd, "anchor_pid": anchors.process.pid,
                  "anchor_fd": anchors.pidfd, "writer_fd": anchors.process.stdin.fileno(), "allowed": sorted(anchors.allowed),
                  "helpers": self.helpers, "control": child.fileno(), "report": str(report_path), "deadline": deadline}
        fds = (read_fd, engine_fd, anchors.pidfd, anchors.process.stdin.fileno(), child.fileno(), lock_fd,
               *(h["fd"] for h in self.helpers))
        try:
            self.process = subprocess.Popen([sys.executable, "-B", "-m", "session_v2.guard", str(read_fd)],
                              pass_fds=fds, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                              env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)})
        except Exception:
            os.close(write_fd)
            self.parent.close()
            for h in self.helpers: os.close(h["fd"])
            raise
        finally:
            os.close(read_fd)
            os.close(engine_fd)
            child.close()
        with os.fdopen(write_fd, "wb") as stream: stream.write(json.dumps(config).encode())
        self.parent.settimeout(10)
        try:
            self.ready = loads(self.parent.recv(4096), 4096)
            require(self.ready.get("status") == "ready", "GUARD_START_FAILED")
        except Exception:
            # EOF réveille le guard même si l'executor n'a pas reçu l'ACK.
            self.parent.close()
            for h in self.helpers: os.close(h["fd"])
            self.process.wait(timeout=15)
            raise

    def resume(self):
        self.parent.sendall(b"resume")
        self.parent.settimeout(15)
        answer = loads(self.parent.recv(4096), 4096)
        require(answer.get("status") == "resumed", "GUARD_RECOVERY_FAILED")
        return answer

    def finish(self):
        self.parent.sendall(b"finish")
        self.parent.settimeout(15)
        answer = loads(self.parent.recv(4096), 4096)
        self.process.wait(timeout=5)
        self.parent.close()
        for h in self.helpers: os.close(h["fd"])
        require(answer.get("status") == "finished", "GUARD_RECOVERY_FAILED")
        return answer


def resume_helpers(stopped, sway_socket, counts):
    """Une identité devenue invalide ne doit pas empêcher les autres reprises.

    CONTRACT : ne jamais signaler un processus non vérifié ; tenter tous les
    helpers encore dus, puis signaler un échec global sans perdre leurs états.
    """
    okay = True
    for h in stopped:
        if h.get("resumed"): continue
        try:
            verify_helper(h["pid"], sway_socket, h["script"])
            signal.pidfd_send_signal(h["fd"], signal.SIGCONT)
            until(lambda: helper_state(h["pid"]) not in ("T", "t"), 2)
            h["resumed"] = True
            counts["helpers_resumed"] += 1
        except (ProcessLookupError, FileNotFoundError): h["resumed"] = True
        except Exception: okay = False
    return okay


def run(config):
    control = socket.socket(fileno=config["control"])
    stopped = []
    counts = {"helpers_suspended": 0, "helpers_resumed": 0}
    normal = False
    sway = Sway(config["socket"])
    def resume():
        return resume_helpers(stopped, config["socket"], counts)
    try:
        for h in config["helpers"]:
            verify_helper(h["pid"], config["socket"], h["script"])
            if helper_state(h["pid"]) in ("T", "t"): continue
            # Enregistrer l'obligation avant SIGSTOP : une exception après signal
            # ne doit pas perdre la responsabilité de reprise.
            stopped.append(h)
            signal.pidfd_send_signal(h["fd"], signal.SIGSTOP)
            until(lambda: helper_state(h["pid"]) in ("T", "t"), 2)
            counts["helpers_suspended"] += 1
        control.sendall(json.dumps({"status": "ready", **counts}).encode())
        end = time.monotonic() + config["deadline"]
        while True:
            readable, _, _ = select.select([config["engine_fd"], control], [], [], max(0, end - time.monotonic()))
            if config["engine_fd"] in readable: break
            if control in readable:
                message = control.recv(16)
                if message == b"resume":
                    require(resume(), "GUARD_RECOVERY_FAILED")
                    control.sendall(json.dumps({"status": "resumed", **counts}).encode())
                    continue
                normal = message == b"finish"
                break
            if not readable:
                signal.pidfd_send_signal(config["engine_fd"], signal.SIGKILL)
                until(lambda: bool(select.select([config["engine_fd"]], [], [], 0)[0]), 3)
                break
        require(resume(), "GUARD_RECOVERY_FAILED")
        def owned(n):
            signal.pidfd_send_signal(config["anchor_fd"], 0)
            return n.get("pid") == config["anchor_pid"] and n.get("app_id") in config["allowed"]
        cleaned = 0
        for old in sway.windows():
            if not owned(old): continue
            fresh = next((n for n in sway.windows() if n["id"] == old["id"]), None)
            if fresh and owned(fresh):
                sway.command(f'[con_id={fresh["id"]}] kill')
                cleaned += 1
        until(lambda: not any(owned(n) for n in sway.windows()))
        os.write(config["writer_fd"], b"quit\n")
        if not normal:
            data = read(config["report"])
            if data["status"] != "success":
                data.update(status="interrupted", phase="recovered", reason="EXECUTOR_INTERRUPTED")
            data.update(**counts)
            data["anchors_cleaned"] += cleaned
            atomic(config["report"], data)
        else: control.sendall(json.dumps({"status": "finished", "anchors_cleaned": cleaned, **counts}).encode())
    except Exception:
        resume()
        # Arrêter seulement le helper possédé retire aussi ses anchors orphelins.
        try: signal.pidfd_send_signal(config["anchor_fd"], signal.SIGTERM)
        except ProcessLookupError: pass
        try:
            data = read(config["report"])
            data.update(status="interrupted", phase="guard-error", reason="GUARD_RECOVERY_FAILED", **counts)
            atomic(config["report"], data)
            control.sendall(b'{"status":"failed"}')
        except (OSError, BrokenPipeError): pass
    finally:
        resume()
        control.close()
        os.close(config["writer_fd"])


if __name__ == "__main__":
    with os.fdopen(int(sys.argv[1]), "rb") as stream: config = loads(stream.read(65537), 65536)
    run(config)

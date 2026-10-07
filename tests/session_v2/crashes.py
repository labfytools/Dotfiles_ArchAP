"""SIGKILL réels de l'executor production, jamais du guard ni d'un utilisateur."""
import json
import os
import signal
import time
from common import *
from lab import Lab, Surfaces, build_helper, until
from session_v2.storage import atomic, private_dir, read
from session_v2.executor import Executor
from session_v2.ipc import Sway


def worker(path):
    config = read(path)
    def progress(phase, count):
        if [phase, count] == config["point"]:
            atomic(Path(config["runtime"]) / "kill-ready.json", {"phase": phase, "count": count})
            while True: time.sleep(1)
    Executor(Sway(config["socket"]), catalog(config["data"]), None, config["runtime"], config["binary"],
             os.environ.copy(), progress).apply(config["data"], True)


def main():
    cases = []
    with Lab() as lab:
        binary, helper_binary = build(lab.directory), build_helper(lab.directory)
        for i, point in enumerate((("anchor", 1), ("all-anchors", 4), ("swap", 1), ("swap", 3),
                                    ("before-cleanup", 0), ("cleanup", 1), ("after-resume", 4), ("normal", 0), ("initial-stopped", 0))):
            runtime = private_dir(lab.directory / f"crash-{i}")
            data = fixture({"splitv": [{"splith": ["A", "B"]}, {"splith": ["C", "D"]}]})
            apps = Surfaces(lab, helper_binary)
            lab.command('workspace TEST_ONLY_SOURCE')
            ids = [apps.create("TEST_ONLY_" + a["application_id"])["id"] for a in data["applications"]]
            foreign = apps.create("labfy-v2-anchor-" + "f" * 32 + "-foreign")["id"]
            helper = lab.spawn(["autotiling"])
            time.sleep(.15)
            helper_fd = os.pidfd_open(helper.pid)
            if point[0] == "initial-stopped": signal.pidfd_send_signal(helper_fd, signal.SIGSTOP)
            config = {"socket": lab.socket, "runtime": str(runtime), "binary": str(binary), "data": data, "point": list(point)}
            atomic(runtime / "config.json", config)
            process = lab.spawn([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(runtime / "config.json")])
            killed = None
            try:
                if point[0] not in ("normal", "initial-stopped"):
                    until(lambda: (runtime / "kill-ready.json").exists() or process.poll() is not None, 15)
                    assert process.poll() is None
                    killed = time.monotonic()
                    process.kill()
                process.wait(timeout=25)
                report = runtime / "session-v2-restore-attempt.json"
                until(lambda: report.exists() and read(report)["status"] != "running", 10)
                if killed: until(lambda: read(report)["phase"] == "recovered", 10)
                result = read(report)
                state = Path(f"/proc/{helper.pid}/status").read_text().split("State:\t", 1)[1][0]
                windows = lab.windows()
                row = {"point": list(point), "returncode": process.returncode, "report": result,
                       "kill_to_recovery_ms": (time.monotonic() - killed) * 1000 if killed else None,
                       "apps_preserved": set(ids).issubset(n["id"] for n in windows),
                       "foreign_preserved": any(n["id"] == foreign for n in windows),
                       "state_preserved": state == "T" if point[0] == "initial-stopped" else state not in ("T", "t"),
                       "anchors_remaining": sum(n.get("app_id", "").startswith("labfy-v2-anchor-") and n["id"] != foreign for n in windows)}
                assert row["apps_preserved"] and row["foreign_preserved"] and row["state_preserved"] and row["anchors_remaining"] == 0, row
                assert result["status"] == ("interrupted" if killed else "success"), row
                if killed: assert row["kill_to_recovery_ms"] < 3000
                cases.append(row)
                print(point, "PASS", flush=True)
            finally:
                if process.poll() is None: process.kill(); process.wait()
                signal.pidfd_send_signal(helper_fd, signal.SIGCONT)
                helper.terminate(); helper.wait(timeout=3)
                os.close(helper_fd)
                apps.close()
    out = private_dir(EVIDENCE)
    atomic(out / "crash.json", {"cases": cases})


if __name__ == "__main__":
    if "--worker" in sys.argv: worker(sys.argv[2])
    else: main()

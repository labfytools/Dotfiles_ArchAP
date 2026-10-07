"""Échecs runtime du moteur production : conservation des apps et reprise."""
import time
from common import *
from lab import Lab, Surfaces, build_helper
from session_v2.ipc import Sway
from session_v2.executor import Executor
from session_v2.errors import Failure
from session_v2.storage import private_dir, atomic, read


def main():
    rows = []
    with Lab() as lab:
        binary, appbin = build(lab.directory), build_helper(lab.directory)
        runtime = private_dir(lab.directory / "labfy-sway")
        for mode, reason in (("missing", "APPLICATION_WINDOWS_INCOMPLETE"), ("extra", "UNEXPECTED_EXTRA_WINDOW"), ("occupied", "WORKSPACE_OCCUPIED")):
            data = fixture()
            apps = Surfaces(lab, appbin)
            lab.command('workspace TEST_ONLY_SOURCE')
            members = data["applications"][:-1] if mode == "missing" else data["applications"]
            ids = [apps.create("TEST_ONLY_" + a["application_id"])["id"] for a in members]
            if mode == "extra": ids.append(apps.create("TEST_ONLY_app-A")["id"])
            if mode == "occupied":
                lab.command('workspace TEST_ONLY_TARGET')
                ids.append(apps.create("TEST_ONLY_FOREIGN")["id"])
            helper = lab.spawn(["autotiling"]); time.sleep(.15)
            try:
                try: Executor(Sway(lab.socket), catalog(data), None, runtime, binary, lab.env).apply(data, True, timeout=.3)
                except Failure as exc: assert exc.code == reason, (exc.code, reason)
                else: raise AssertionError(mode)
                report = read(runtime / "session-v2-restore-attempt.json")
                assert report["status"] == "failed" and report["reason"] == reason, report
                assert set(ids).issubset(n["id"] for n in lab.windows())
                assert not any(n.get("app_id", "").startswith("labfy-v2-anchor-") for n in lab.windows())
                assert Path(f"/proc/{helper.pid}/status").read_text().split("State:\t", 1)[1][0] not in ("T", "t")
                rows.append({"case": mode, "report": report, "apps_preserved": True, "anchors_remaining": 0, "helper_recovered": True})
            finally:
                helper.terminate(); helper.wait(timeout=3); apps.close()
    atomic(private_dir(EVIDENCE) / "failures.json", {"cases": rows})
    print(len(rows), "runtime failures PASS")


if __name__ == "__main__": main()

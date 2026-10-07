import argparse
import time
from common import *
from lab import Lab, Surfaces, build_helper, until
from session_v2.ipc import Sway
from session_v2.executor import Executor
from session_v2.storage import private_dir, atomic
from session_v2.snapshot import capture


def main(smoke=False):
    rows = []
    shapes = ["A", {"splith": ["A", "B"]}, {"splitv": ["A", "B"]},
              {"splith": ["A", "B", "C"]}, {"splitv": ["A", "B", "C"]},
              {"splitv": ["A", {"splith": ["B", "C"]}]},
              {"splith": ["A", {"splitv": ["B", "C"]}]},
              {"splitv": [{"splith": ["A", "B"]}, {"splith": ["C", "D"]}]},
              {"splith": [{"splitv": ["A", "B"]}, {"splitv": ["C", "D"]}]},
              {"splitv": ["A", {"splith": ["B", {"splitv": ["C", "D"]}]}]},
              {"tabbed": ["A", "B", "C"]}, {"stacked": ["A", "B", "C"]},
              {"splitv": ["A", {"tabbed": ["B", "C"]}]}, {"splith": ["A", {"stacked": ["B", "C"]}]}]
    with Lab() as lab:
        binary = build(lab.directory)
        test_binary = build_helper(lab.directory)
        runtime = private_dir(lab.directory / "labfy-sway")
        sway = Sway(lab.socket)
        for index, shape in enumerate(shapes[:1] if smoke else shapes):
            for reverse in ([False] if smoke else [False, True]):
                data = fixture(shape)
                apps = Surfaces(lab, test_binary)
                lab.command('workspace "TEST_ONLY_SOURCE"')
                order = list(reversed(data["applications"])) if reverse else data["applications"]
                for app in order: apps.create("TEST_ONLY_" + app["application_id"])
                helper = lab.spawn(["autotiling"])
                time.sleep(.15)
                try:
                    result = Executor(sway, catalog(data), None, runtime, binary, lab.env).apply(data, True)
                    snapped = capture(sway, catalog(data), None)
                    assert len(snapped["window_slots"]) == len(data["window_slots"])
                    assert result["helpers_suspended"] == result["helpers_resumed"] == 1
                    rows.append({"shape": shape, "reverse": reverse, "result": result, "capture": "PASS"})
                    print(index, reverse, "PASS", flush=True)
                finally:
                    helper.terminate(); helper.wait(timeout=3)
                    apps.close()
        if not smoke:
            for count in (3, 5, 10):
                data = fixture({"splith": [chr(65+i) for i in range(count)]})
                apps = Surfaces(lab, test_binary)
                lab.command('workspace "TEST_ONLY_SOURCE"')
                for a in data["applications"]: apps.create("TEST_ONLY_" + a["application_id"])
                result = Executor(sway, catalog(data), None, runtime, binary, lab.env).apply(data, True)
                rows.append({"performance_windows": count, "result": result})
                apps.close()
            data = fixture()
            second = fixture({"splith": ["D", "E"]}, "TEST_ONLY_SECOND")
            for key in ("applications", "window_slots", "workspaces"): data[key] += second[key]
            apps = Surfaces(lab, test_binary)
            lab.command('workspace "TEST_ONLY_SOURCE"')
            for a in data["applications"]: apps.create("TEST_ONLY_" + a["application_id"])
            result = Executor(sway, catalog(data), None, runtime, binary, lab.env).apply(data, True)
            rows.append({"multi_workspace": True, "result": result})
            apps.close()
            data = fixture({"splith": ["A", "B"]})
            data["workspaces"][0]["root"] = {"slot_id": "A"}
            data["window_slots"][0]["tree_path"] = []
            slot = data["window_slots"][1]
            slot["tree_path"] = []
            slot["state"].update(floating=True, geometry={"x": 30, "y": 40, "width": 400, "height": 240})
            apps = Surfaces(lab, test_binary)
            lab.command('workspace "TEST_ONLY_SOURCE"')
            for a in data["applications"]: apps.create("TEST_ONLY_" + a["application_id"])
            result = Executor(sway, catalog(data), None, runtime, binary, lab.env).apply(data, True)
            rows.append({"floating": True, "result": result})
            apps.close()
            # Même processus, même app_id et même titre : seule la cardinalité
            # autorise ces slots explicitement interchangeables/best-effort.
            for identity in ("interchangeable", "best-effort"):
                data = fixture({"splith": ["A", "B", "C"]})
                data["applications"] = [data["applications"][0]]
                data["applications"][0]["expected_windows"] = 3
                for slot in data["window_slots"]:
                    slot.update(application_id="app-A", identity_requirement=identity, identity_evidence=None)
                apps = Surfaces(lab, test_binary)
                lab.command('workspace "TEST_ONLY_SOURCE"')
                for _ in range(3): apps.create("TEST_ONLY_app-A")
                result = Executor(sway, catalog(data), None, runtime, binary, lab.env).apply(data, True)
                assert result["identity_level"] == identity
                rows.append({"same_app_three": True, "identity": identity, "result": result})
                apps.close()
    out = EVIDENCE
    private_dir(out)
    atomic(out / ("smoke.json" if smoke else "runtime.json"), {"cases": rows})


if __name__ == "__main__": main("--smoke" in sys.argv)

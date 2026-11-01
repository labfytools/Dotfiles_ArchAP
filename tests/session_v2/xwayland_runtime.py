"""Real XWayland TEST_ONLY, with private compositor, config and children only."""
import json
import re
from unittest.mock import patch
from common import *
from lab import Lab as BaseLab, Surfaces, build_helper, until
from session_v2.errors import Failure
from session_v2.executor import Executor
from session_v2.ipc import Sway, walk, location, surface_identity
from session_v2.recovery import observe, process_start, JOURNAL, recovery_status
from session_v2.snapshot import capture
from session_v2.storage import private_dir

WEBAPP = "firefox.webapp-fcd72ebe-94c5-4209-b3f6-bbaa7784cded"


class Lab(BaseLab):
    def start(self, argv):
        if self.socket is None and "-c" in argv:
            config = self.directory / "headless-x11.conf"
            original = Path(argv[argv.index("-c") + 1]).read_text()
            config.write_text(original.replace("xwayland disable", "xwayland enable"))
            argv = list(argv)
            argv[argv.index("-c") + 1] = str(config)
        return super().start(argv)

    def __enter__(self):
        super().__enter__()
        try:
            # Read only the DISPLAY from our compositor's child environment.
            # No inherited desktop socket, Xauthority, bus or profile is used.
            helper, marker = self.directory / "display.py", self.directory / "display"
            helper.write_text("import os\nfrom pathlib import Path\nPath(" + repr(str(marker))
                              + ").write_text(os.environ.get('DISPLAY', ''))\n")
            self.command("exec /usr/bin/python3 " + json.dumps(str(helper)))
            until(marker.exists)
            display = marker.read_text()
            assert re.fullmatch(r":[0-9]+(?:\.[0-9]+)?", display), "NO_PRIVATE_X_DISPLAY"
            self.env.update(DISPLAY=display, GDK_BACKEND="wayland")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def windows(self):
        return [n for n in walk(self.tree()) if n.get("app_id") or n.get("window")]

    def x11(self, wm_class):
        process = self.spawn(["/usr/bin/xterm", "-class", wm_class, "-name", "TEST_ONLY",
                              "-title", "TEST_ONLY", "-e", "/usr/bin/sleep", "180"])
        found = until(lambda: [n for n in self.windows() if n.get("pid") == process.pid
                               and n.get("window_properties", {}).get("class") == wm_class])
        assert len(found) == 1 and found[0]["app_id"] is None
        return found[0], process


def main():
    with Lab() as lab:
        print("TEST_ONLY_DIRECTORY=" + str(lab.directory), flush=True)
        binary = build(lab.directory)
        native = Surfaces(lab, build_helper(lab.directory))
        sway = Sway(lab.socket)
        lab.command('workspace "TEST_ONLY_TARGET"')
        chat, chat_process = lab.x11("Chatgpt")
        whatsapp = native.create(WEBAPP)
        time.sleep(.2)
        data = capture(sway, Catalog(), None)
        assert {a["application_id"] for a in data["applications"]} == {"chatgpt", "whatsapp-web"}
        assert all(s["identity_requirement"] == "exact" for s in data["window_slots"])
        (lab.directory / "snapshot.json").write_text(json.dumps(data, indent=2))
        for node in (chat, whatsapp):
            lab.command(f'[con_id={node["id"]}] move container to workspace "TEST_ONLY_SOURCE"')
        lab.command('workspace "TEST_ONLY_FOREIGN"')
        foreign, foreign_process = lab.x11("TEST_ONLY_Unknown")
        time.sleep(.2)
        tree = sway.tree()
        foreign_before = observe(tree, next(n for n in walk(tree) if n["id"] == foreign["id"]), process_start)
        before_ids = {n["id"] for n in sway.windows()}
        commands = []
        raw_command = sway.command
        def command(text):
            commands.append(text)
            return raw_command(text)
        sway.command = command
        runtime = private_dir(lab.directory / "runtime")
        # The production catalogue is used unchanged; all real app launches are
        # forbidden. Our xterm and GTK clients expose synthetic protocol IDs only.
        with patch("session_v2.executor.launch", side_effect=AssertionError("REAL_APP_LAUNCH_FORBIDDEN")):
            result = Executor(sway, Catalog(), None, runtime, binary, lab.env).apply(data, True)
        assert result["status"] == "success", result
        assert result["final_tree_verified"] and result["final_focus_verified"]
        tree = sway.tree()
        assert {n["id"] for n in sway.windows()} == before_ids
        assert location(tree, chat["id"])[0] == location(tree, whatsapp["id"])[0] == "TEST_ONLY_TARGET"
        live_foreign = next(n for n in walk(tree) if n["id"] == foreign["id"])
        assert observe(tree, live_foreign, process_start) == foreign_before
        assert live_foreign["focused"]
        assert chat_process.poll() is None and foreign_process.poll() is None
        journal = json.loads((runtime / JOURNAL).read_text())
        assert recovery_status(runtime)["status"] == "complete"
        assert [e["app_id"] for e in journal["foreign"]] == ["x11-class:TEST_ONLY_Unknown"]
        entry = next(e for e in journal["windows"] if e["origin"]["con_id"] == chat["id"])
        assert entry["origin"]["app_id"] == entry["expected"]["app_id"] == "x11-class:Chatgpt"
        assert any(c.startswith(f'[con_id={chat["id"]}] swap container with con_id ') for c in commands)
        # An unknown X11 class stays protected foreign evidence and is still
        # refused by capture; it never becomes an admissible catalogue target.
        try:
            capture(sway, Catalog(), None)
        except Failure as exc:
            assert exc.code == "APPLICATION_UNSUPPORTED", exc.code
        else:
            raise AssertionError("UNKNOWN_CLASS_WAS_SAVED")
        assert surface_identity(live_foreign) == "x11-class:TEST_ONLY_Unknown"
        evidence = {"result": result, "unknown_x11_preserved": True,
                    "unknown_x11_capture_refused": True, "focus_preserved": True,
                    "x11_app_id_remains_null": next(n for n in sway.windows() if n["id"] == chat["id"])["app_id"] is None,
                    "commands": commands}
        (lab.directory / "xwayland-result.json").write_text(json.dumps(evidence, indent=2))
        print("XWAYLAND_RUNTIME=PASS", flush=True)
        native.close()


if __name__ == "__main__":
    main()

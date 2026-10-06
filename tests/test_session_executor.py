"""STEP19B/19C : exécuteur contrôlé, tous les effets externes sont simulés."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    from tests.test_session_restore import session, window
except ModuleNotFoundError:  # unittest discovery ajoute directement tests/ à sys.path.
    from test_session_restore import session, window


ROOT = Path(__file__).resolve().parents[1]
SESSION_DIR = ROOT / "quickshell/.config/quickshell/labfy-sway/session"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SESSION_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = load_module("session_restore_executor_test", "session_restore.py")
executor = load_module("session_executor_test", "session_executor.py")
snapshot_backend = load_module("session_snapshot_executor_test", "session_snapshot.py")


DESKTOP_ENTRIES = [{
    "desktop_entry": "kitty.desktop",
    "stem": "kitty",
    "startup_wm_class": "kitty",
    "name": "kitty",
}]


def kitty_saved(**kwargs):
    defaults = {"workspace": "3", "con_id": 10, "pid": 1000}
    defaults.update(kwargs)
    return window("w1", "kitty", desktop_entry="kitty.desktop", executable="kitty", **defaults)


class FakeWorld:
    def __init__(self, windows=(), *, launch_window=None, focused_workspace=None):
        self.windows = [copy.deepcopy(item) for item in windows]
        self.launch_window = copy.deepcopy(launch_window)
        self.focused_workspace = focused_workspace
        self.commands = []

    def collect(self):
        focused = next((item["window_id"] for item in self.windows if item.get("focused")), None)
        value = session(self.windows, focused=focused)
        if self.focused_workspace is not None:
            if not any(item.get("name") == self.focused_workspace for item in value["workspaces"]):
                value["workspaces"].append({
                    "name": self.focused_workspace,
                    "output": "eDP-1",
                    "layout": "splith",
                    "orientation": "horizontal",
                })
            value["focus"]["workspace"] = self.focused_workspace
        return value

    def run(self, argv, timeout):
        self.commands.append(list(argv))
        if argv[:4] == ["uwsm", "app", "--", "kitty.desktop"]:
            if self.launch_window is not None:
                self.windows.append(copy.deepcopy(self.launch_window))
                self.launch_window = None
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        command = argv[-1]
        prefix, operation = command.split("] ", 1)
        con_id = int(prefix.removeprefix("[con_id="))
        target = next(item for item in self.windows if item["runtime"]["con_id"] == con_id)
        if operation.startswith("move container to workspace number "):
            target["workspace"] = operation.rsplit(" ", 1)[1]
        elif operation == "floating enable":
            target["floating"] = True
        elif operation == "floating disable":
            target["floating"] = False
        elif operation == "fullscreen enable":
            target["fullscreen_mode"] = 1
        elif operation == "fullscreen disable":
            target["fullscreen_mode"] = 0
        elif operation == "move scratchpad":
            target["scratchpad"] = {"member": True, "visibility": "hidden", "state": "fresh"}
            target["workspace"] = None
            target["output"] = None
        elif operation == "scratchpad show":
            target["scratchpad"] = {"member": True, "visibility": "visible", "state": "changed"}
            target["workspace"] = self.focused_workspace or "3"
            target["output"] = "eDP-1"
        elif operation == "focus":
            for item in self.windows:
                item["focused"] = item is target
        return SimpleNamespace(returncode=0, stdout='[{"success":true}]', stderr="")


def execute(source, world, **kwargs):
    plan = planner.build_restore_plan(source, world.collect())
    return executor.execute_fresh_plan(
        source,
        plan,
        collector=world.collect,
        planner_module=planner,
        desktop_entries=DESKTOP_ENTRIES,
        resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
        runner=world.run,
        timeout=0.01,
        sleeper=lambda _delay: None,
        **kwargs,
    ), plan


class SessionExecutorTest(unittest.TestCase):
    def test_apply_requires_explicit_execute(self):
        stderr = io.StringIO()
        with mock.patch.object(snapshot_backend, "apply_session") as apply, mock.patch("sys.stderr", stderr):
            self.assertEqual(snapshot_backend.main(("apply", "dev")), 1)
        apply.assert_not_called()
        self.assertIn("REQUIRES_EXPLICIT_EXECUTE", stderr.getvalue())

    def test_apply_execute_reaches_executor(self):
        report = {"schema": executor.REPORT_SCHEMA, "status": "success"}
        output = io.StringIO()
        with mock.patch.object(snapshot_backend, "apply_session", return_value=report) as apply, mock.patch("sys.stdout", output):
            self.assertEqual(snapshot_backend.main(("apply", "dev", "--execute")), 0)
        apply.assert_called_once()
        self.assertEqual(json.loads(output.getvalue()), report)

    def test_plan_blocking_happens_before_mutation(self):
        saved = kitty_saved(parent="c1")
        live = copy.deepcopy(saved)
        live["tree_position"]["parent_container_id"] = None
        container = {
            "container_id": "c1", "parent_container_id": None,
            "tree_position": {"branch": "tiling", "index": 0},
            "layout": "splitv", "orientation": "vertical", "percent": 1.0,
        }
        source = session([saved], persistent=True, containers=[container])
        world = FakeWorld([live])
        plan = planner.build_restore_plan(source, world.collect())
        with self.assertRaisesRegex(executor.RestoreExecutionError, "RESTORE_BLOCKED_UNSUPPORTED_ACTION"):
            executor.execute_fresh_plan(
                source, plan, collector=world.collect, planner_module=planner,
                desktop_entries=DESKTOP_ENTRIES,
                resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                runner=world.run,
            )
        self.assertEqual(world.commands, [])

    def test_command_reconstruction_ignores_arbitrary_argv(self):
        saved = kitty_saved()
        source = session([saved], persistent=True)
        world = FakeWorld([], launch_window=kitty_saved(con_id=22, pid=2000, workspace="3"))
        plan = planner.build_restore_plan(source, world.collect())
        launch = next(item for item in plan["actions"] if item["action"] == "launch-application")
        launch["launch"]["argv"] = ["sh", "-c", "touch /tmp/forbidden"]
        result = executor.execute_fresh_plan(
            source, plan, collector=world.collect, planner_module=planner,
            desktop_entries=DESKTOP_ENTRIES,
            resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
            runner=world.run, timeout=0.01, sleeper=lambda _delay: None,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(world.commands[0], ["uwsm", "app", "--", "kitty.desktop"])

    def test_default_uwsm_launch_is_direct_and_nonblocking(self):
        process = SimpleNamespace(returncode=None)
        with mock.patch.object(executor.subprocess, "Popen", return_value=process) as popen, mock.patch.object(
            executor.subprocess, "run"
        ) as run:
            self.assertIs(
                executor._default_runner(["uwsm", "app", "--", "kitty.desktop"], 10.0),
                process,
            )
        popen.assert_called_once_with(
            ["uwsm", "app", "--", "kitty.desktop"],
            stdin=executor.subprocess.DEVNULL,
            stdout=executor.subprocess.DEVNULL,
            stderr=executor.subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        run.assert_not_called()

    def test_desktop_entry_is_revalidated(self):
        source = session([kitty_saved()], persistent=True)
        world = FakeWorld([])
        plan = planner.build_restore_plan(source, world.collect())
        with self.assertRaisesRegex(executor.RestoreExecutionError, "DesktopEntry absente"):
            executor.execute_fresh_plan(
                source, plan, collector=world.collect, planner_module=planner,
                desktop_entries=[], resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                runner=world.run,
            )
        self.assertEqual(world.commands, [])

    def test_restore_lock_is_private_and_exclusive(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            path.chmod(0o700)
            with executor.restore_lock(path):
                self.assertEqual((path / ".restore.lock").stat().st_mode & 0o777, 0o600)
                with self.assertRaisesRegex(executor.RestoreExecutionError, "RESTORE_ALREADY_RUNNING"):
                    with executor.restore_lock(path):
                        self.fail("second lock unexpectedly acquired")

    def test_restore_lock_rejects_non_private_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            path.chmod(0o755)
            with self.assertRaisesRegex(executor.RestoreExecutionError, "répertoire sessions non privé"):
                with executor.restore_lock(path):
                    self.fail("unsafe directory unexpectedly accepted")

    def test_ambiguous_reuse_blocks_before_mutation(self):
        saved = kitty_saved()
        source = session([saved], persistent=True)
        world = FakeWorld([
            kitty_saved(con_id=81, pid=8001),
            kitty_saved(con_id=82, pid=8002),
        ])
        plan = planner.build_restore_plan(source, world.collect())
        self.assertEqual(plan["actions"][0]["confidence"], "ambiguous")
        with self.assertRaisesRegex(executor.RestoreExecutionError, "ambiguous-runtime-match"):
            executor.execute_fresh_plan(
                source, plan, collector=world.collect, planner_module=planner,
                desktop_entries=DESKTOP_ENTRIES,
                resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                runner=world.run,
            )
        self.assertEqual(world.commands, [])

    def test_reuse_is_validated_noop(self):
        saved = kitty_saved(con_id=10)
        source = session([saved], persistent=True)
        world = FakeWorld([copy.deepcopy(saved)])
        result, _plan = execute(source, world)
        self.assertEqual(result["actions"][0]["status"], "success")
        self.assertEqual(world.commands, [])

    def test_autostart_skip_is_validated_noop(self):
        saved = kitty_saved(category="autostart-managed-application", managed_by="sway-autostart")
        source = session([saved], persistent=True)
        world = FakeWorld([])
        result, _plan = execute(source, world)
        self.assertEqual(result["actions"][0]["status"], "skipped")
        self.assertEqual(world.commands, [])

    def test_launch_waits_for_new_matching_window(self):
        source = session([kitty_saved()], persistent=True)
        launched = kitty_saved(con_id=55, pid=5000, workspace="3")
        world = FakeWorld([], launch_window=launched)
        result, _plan = execute(source, world)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["runtime_windows"], {"w1": 55})

    def test_launch_timeout(self):
        source = session([kitty_saved()], persistent=True)
        world = FakeWorld([])
        ticks = iter((0.0, 0.0, 1.0))
        result, _plan = execute(source, world, monotonic=lambda: next(ticks))
        self.assertEqual(result["status"], "failed")
        self.assertIn("RESTORE_LAUNCH_TIMEOUT", result["reason"])

    def test_launch_aborts_if_inventory_drifted_before_uwsm(self):
        source = session([kitty_saved()], persistent=True)
        initial = session([])
        plan = planner.build_restore_plan(source, initial)
        intruder = window("w9", "other", desktop_entry="other.desktop", con_id=99, pid=9000)
        commands = []
        result = executor.execute_fresh_plan(
            source, plan, collector=lambda: session([intruder]), planner_module=planner,
            desktop_entries=DESKTOP_ENTRIES,
            resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
            runner=lambda argv, _timeout: commands.append(list(argv)),
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("inventaire con_id modifié avant lancement", result["reason"])
        self.assertEqual(commands, [])

    def test_launch_ambiguous(self):
        source = session([kitty_saved()], persistent=True)
        first = kitty_saved(con_id=51, pid=5001, workspace="3")
        second = kitty_saved(con_id=52, pid=5002, workspace="3")
        world = FakeWorld([])

        def run(argv, timeout):
            world.commands.append(list(argv))
            world.windows.extend([first, second])
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        world.run = run
        result, _plan = execute(source, world)
        self.assertEqual(result["status"], "failed")
        self.assertIn("RESTORE_LAUNCH_AMBIGUOUS", result["reason"])

    def test_move_is_targeted_and_confirmed(self):
        saved = kitty_saved(workspace="3", con_id=10)
        live = kitty_saved(workspace="2", con_id=44)
        source = session([saved], persistent=True)
        world = FakeWorld([live])
        result, _plan = execute(source, world)
        self.assertEqual(result["status"], "success")
        self.assertIn("[con_id=44] move container to workspace number 3", world.commands[-1])

    def test_floating_enable_and_disable(self):
        for desired, current, expected in ((True, False, "floating enable"), (False, True, "floating disable")):
            with self.subTest(desired=desired):
                source = session([kitty_saved(floating=desired)], persistent=True)
                world = FakeWorld([kitty_saved(floating=current, con_id=88)])
                result, _plan = execute(source, world)
                self.assertEqual(result["status"], "success")
                self.assertTrue(any(expected in command[-1] for command in world.commands))

    def test_fullscreen_workspace_mode_and_disabled(self):
        for desired, current, expected in ((1, 0, "fullscreen enable"), (0, 1, "fullscreen disable")):
            with self.subTest(desired=desired):
                source = session([kitty_saved(fullscreen=desired)], persistent=True)
                world = FakeWorld([kitty_saved(fullscreen=current, con_id=89)])
                result, _plan = execute(source, world)
                self.assertEqual(result["status"], "success")
                self.assertTrue(any(expected in command[-1] for command in world.commands))

    def test_unsupported_fullscreen_blocks_before_mutation(self):
        source = session([kitty_saved(fullscreen=2)], persistent=True)
        world = FakeWorld([kitty_saved(fullscreen=0, con_id=90)])
        plan = planner.build_restore_plan(source, world.collect())
        with self.assertRaisesRegex(executor.RestoreExecutionError, "unsupported-fullscreen-mode"):
            executor.execute_fresh_plan(
                source, plan, collector=world.collect, planner_module=planner,
                desktop_entries=DESKTOP_ENTRIES,
                resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                runner=world.run,
            )
        self.assertEqual(world.commands, [])

    def test_focus_is_last(self):
        saved = kitty_saved(workspace="3", focused=True)
        source = session([saved], persistent=True, focused="w1")
        world = FakeWorld([kitty_saved(workspace="2", con_id=91, focused=False)])
        result, plan = execute(source, world)
        self.assertEqual(plan["actions"][-1]["action"], "restore-focus")
        self.assertTrue(world.commands[-1][-1].endswith(" focus"))
        self.assertEqual(result["status"], "success")

    def test_postcondition_polling_accepts_delayed_focus_visibility(self):
        saved = kitty_saved(con_id=92)
        states = [kitty_saved(con_id=92, focused=False), kitty_saved(con_id=92, focused=True)]
        sleeps = []

        def collect():
            return session([states.pop(0) if len(states) > 1 else states[0]])

        result = executor._wait_for_postcondition(
            saved,
            92,
            lambda item: bool(item.get("focused")),
            "focus cible non atteint",
            collector=collect,
            planner_module=planner,
            monotonic=lambda: 0.0,
            sleeper=sleeps.append,
        )
        self.assertTrue(result["focused"])
        self.assertEqual(sleeps, [executor.POLL_INTERVAL_SECONDS])

    def test_runtime_con_id_disappeared(self):
        saved = kitty_saved()
        source = session([saved], persistent=True)
        initial = session([copy.deepcopy(saved)])
        plan = planner.build_restore_plan(source, initial)
        result = executor.execute_fresh_plan(
            source, plan, collector=lambda: session([]), planner_module=planner,
            desktop_entries=DESKTOP_ENTRIES,
            resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
            runner=lambda *_args: self.fail("mutation must not run"),
        )
        self.assertIn("con_id disparu", result["reason"])

    def test_runtime_identity_changed(self):
        saved = kitty_saved()
        source = session([saved], persistent=True)
        plan = planner.build_restore_plan(source, session([copy.deepcopy(saved)]))
        changed = window("w9", "evil", desktop_entry="evil.desktop", con_id=10, pid=999)
        result = executor.execute_fresh_plan(
            source, plan, collector=lambda: session([changed]), planner_module=planner,
            desktop_entries=DESKTOP_ENTRIES,
            resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
            runner=lambda *_args: self.fail("mutation must not run"),
        )
        self.assertIn("identité modifiée", result["reason"])

    def test_snapshot_hash_is_unchanged_and_plan_is_fresh(self):
        saved = kitty_saved()
        source = session([saved], persistent=True, name="fresh")
        world = FakeWorld([copy.deepcopy(saved)])
        loads = []

        def loader(name):
            loads.append(name)
            return copy.deepcopy(source)

        with tempfile.TemporaryDirectory() as temporary:
            report = executor.apply_session(
                "fresh", None, sessions_path=Path(temporary), snapshot_loader=loader,
                live_collector=lambda _path: world.collect(), planner_module=planner,
                desktop_loader=lambda: DESKTOP_ENTRIES,
                resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                runner=world.run,
            )
        self.assertEqual(loads, ["fresh", "fresh"])
        self.assertTrue(report["snapshot_unchanged"])
        self.assertEqual(report["snapshot_hash_before"], report["snapshot_hash_after"])
        self.assertEqual(report["plan"]["live"]["windows"][0]["runtime"]["con_id"], 10)

    def test_unsupported_and_manual_actions_abort(self):
        for action_type in ("restore-tree-position", "restore-scratchpad-hidden", "restore-scratchpad-visible", "manual-required", "unknown-action"):
            with self.subTest(action=action_type):
                source = session([kitty_saved()], persistent=True)
                plan = planner.build_restore_plan(source, session([kitty_saved()]))
                injected = copy.deepcopy(plan["actions"][0])
                injected.update(action_id="a999", action=action_type, phase="tree-layout", depends_on=[])
                plan["actions"] = [injected]
                world = FakeWorld([kitty_saved()])
                with self.assertRaisesRegex(executor.RestoreExecutionError, "RESTORE_BLOCKED_UNSUPPORTED_ACTION"):
                    executor.execute_fresh_plan(
                        source, plan, collector=world.collect, planner_module=planner,
                        desktop_entries=DESKTOP_ENTRIES,
                        resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                        runner=world.run,
                    )
                self.assertEqual(world.commands, [])

    def test_malicious_workspace_is_never_a_command(self):
        source = session([kitty_saved(workspace="3")], persistent=True)
        world = FakeWorld([kitty_saved(workspace="2", con_id=77)])
        plan = planner.build_restore_plan(source, world.collect())
        move = next(item for item in plan["actions"] if item["action"] == "move-to-workspace")
        move["desired_workspace"] = "3; exec touch /tmp/forbidden"
        with self.assertRaisesRegex(executor.RestoreExecutionError, "unsupported-non-numeric-workspace"):
            executor.execute_fresh_plan(
                source, plan, collector=world.collect, planner_module=planner,
                desktop_entries=DESKTOP_ENTRIES,
                resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                runner=world.run,
            )
        self.assertEqual(world.commands, [])

    def test_malicious_desktop_entry_is_blocked_before_command(self):
        saved = kitty_saved()
        saved["restore_identity"]["desktop_entry"] = "kitty.desktop;touch"
        source = session([saved], persistent=True)
        world = FakeWorld([])
        plan = planner.build_restore_plan(source, world.collect())
        with self.assertRaisesRegex(executor.RestoreExecutionError, "identité de lancement non exacte"):
            executor.execute_fresh_plan(
                source, plan, collector=world.collect, planner_module=planner,
                desktop_entries=[{
                    "desktop_entry": "kitty.desktop;touch", "stem": "kitty",
                    "startup_wm_class": "kitty", "name": "hostile",
                }],
                resolve_desktop_entry=snapshot_backend.resolve_desktop_entry,
                runner=world.run,
            )
        self.assertEqual(world.commands, [])

    def test_title_and_app_id_are_not_interpolated_into_commands(self):
        malicious = kitty_saved(workspace="3")
        malicious["title_hint"] = "] exec touch /tmp/forbidden"
        source = session([malicious], persistent=True)
        world = FakeWorld([kitty_saved(workspace="2", con_id=73)])
        result, _plan = execute(source, world)
        self.assertEqual(result["status"], "success")
        serialized = json.dumps(world.commands)
        self.assertNotIn("touch", serialized)
        self.assertNotIn("title", serialized)

    def test_scratchpad_hidden_target_is_targeted_and_confirmed(self):
        hidden = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = kitty_saved(workspace=None, output=None, scratchpad=hidden)
        live = kitty_saved(workspace="3", con_id=81)
        world = FakeWorld([live], focused_workspace="3")
        result, plan = execute(session([saved], persistent=True), world)
        self.assertEqual(result["status"], "success")
        self.assertIn("restore-scratchpad-hidden", [item["action"] for item in plan["actions"]])
        self.assertIn(["swaymsg", "-r", "[con_id=81] move scratchpad"], world.commands)

    def test_scratchpad_visible_target_uses_targeted_show(self):
        visible = {"member": True, "visibility": "visible", "state": "changed"}
        hidden = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = kitty_saved(workspace="3", scratchpad=visible)
        live = kitty_saved(workspace=None, output=None, con_id=82, scratchpad=hidden)
        world = FakeWorld([live], focused_workspace="3")
        result, plan = execute(session([saved], persistent=True), world)
        self.assertEqual(result["status"], "success")
        self.assertIn("restore-scratchpad-visible", [item["action"] for item in plan["actions"]])
        self.assertEqual(world.commands, [["swaymsg", "-r", "[con_id=82] scratchpad show"]])

    def test_scratchpad_already_hidden_is_noop(self):
        hidden = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = kitty_saved(workspace=None, output=None, scratchpad=hidden)
        live = kitty_saved(workspace=None, output=None, con_id=83, scratchpad=hidden)
        world = FakeWorld([live], focused_workspace="3")
        result, plan = execute(session([saved], persistent=True), world)
        self.assertEqual(result["status"], "success")
        self.assertNotIn("restore-scratchpad-hidden", [item["action"] for item in plan["actions"]])
        self.assertEqual(world.commands, [])

    def test_scratchpad_already_visible_is_noop(self):
        visible = {"member": True, "visibility": "visible", "state": "changed"}
        saved = kitty_saved(workspace="3", scratchpad=visible)
        live = kitty_saved(workspace="3", con_id=84, scratchpad=visible)
        world = FakeWorld([live], focused_workspace="3")
        result, plan = execute(session([saved], persistent=True), world)
        self.assertEqual(result["status"], "success")
        self.assertNotIn("restore-scratchpad-visible", [item["action"] for item in plan["actions"]])
        self.assertEqual(world.commands, [])

    def test_unexpected_user_scratchpad_is_never_cycled(self):
        hidden = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = kitty_saved(workspace=None, output=None, scratchpad=hidden)
        target = kitty_saved(workspace="3", con_id=85)
        user = window(
            "w9", "firefox", desktop_entry="firefox.desktop", executable="firefox",
            workspace=None, output=None, con_id=99, pid=9999, scratchpad=hidden,
        )
        world = FakeWorld([target, user], focused_workspace="3")
        result, _plan = execute(session([saved], persistent=True), world)
        self.assertEqual(result["status"], "success")
        self.assertEqual(world.commands, [["swaymsg", "-r", "[con_id=85] move scratchpad"]])
        self.assertEqual(world.windows[1]["scratchpad"], hidden)

    def test_scratchpad_target_disappeared_stops(self):
        hidden = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = kitty_saved(workspace=None, output=None, scratchpad=hidden)
        live = kitty_saved(workspace="3", con_id=86)
        world = FakeWorld([live], focused_workspace="3")
        plan = planner.build_restore_plan(session([saved], persistent=True), world.collect())
        world.windows.clear()
        result = executor.execute_fresh_plan(
            session([saved], persistent=True), plan, collector=world.collect,
            planner_module=planner, desktop_entries=DESKTOP_ENTRIES,
            resolve_desktop_entry=snapshot_backend.resolve_desktop_entry, runner=world.run,
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("con_id disparu", result["reason"])
        self.assertEqual(world.commands, [])

    def test_scratchpad_identity_changed_stops(self):
        hidden = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = kitty_saved(workspace=None, output=None, scratchpad=hidden)
        live = kitty_saved(workspace="3", con_id=87)
        world = FakeWorld([live], focused_workspace="3")
        plan = planner.build_restore_plan(session([saved], persistent=True), world.collect())
        world.windows[0]["app_id"] = "firefox"
        world.windows[0]["restore_identity"]["app_id"] = "firefox"
        world.windows[0]["restore_identity"]["desktop_entry"] = "firefox.desktop"
        world.windows[0]["executable_basename"] = "firefox"
        result = executor.execute_fresh_plan(
            session([saved], persistent=True), plan, collector=world.collect,
            planner_module=planner, desktop_entries=DESKTOP_ENTRIES,
            resolve_desktop_entry=snapshot_backend.resolve_desktop_entry, runner=world.run,
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("identité modifiée", result["reason"])
        self.assertEqual(world.commands, [])

    def test_multiple_scratchpad_identity_is_ambiguous(self):
        visible = {"member": True, "visibility": "visible", "state": "changed"}
        hidden = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = kitty_saved(workspace="3", scratchpad=visible)
        one = kitty_saved(workspace=None, output=None, con_id=88, pid=188, scratchpad=hidden)
        two = kitty_saved(workspace=None, output=None, con_id=89, pid=189, scratchpad=hidden)
        world = FakeWorld([one, two], focused_workspace="3")
        plan = planner.build_restore_plan(session([saved], persistent=True), world.collect())
        with self.assertRaisesRegex(executor.RestoreExecutionError, "ambiguous-runtime-match"):
            executor.execute_fresh_plan(
                session([saved], persistent=True), plan, collector=world.collect,
                planner_module=planner, desktop_entries=DESKTOP_ENTRIES,
                resolve_desktop_entry=snapshot_backend.resolve_desktop_entry, runner=world.run,
            )
        self.assertEqual(world.commands, [])

    def test_source_contains_no_shell_execution_primitive(self):
        source = (SESSION_DIR / "session_executor.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("exec(", source)
        self.assertNotIn("shell=True", source)


if __name__ == "__main__":
    unittest.main()

"""Contrat Restore Plan V1 : intentions déterministes et aucune exécution."""

import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RESTORE_SOURCE = ROOT / "quickshell/.config/quickshell/labfy-sway/session/session_restore.py"
SNAPSHOT_SOURCE = ROOT / "quickshell/.config/quickshell/labfy-sway/session/session_snapshot.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


restore = load_module("session_restore_test", RESTORE_SOURCE)
snapshot_backend = load_module("session_snapshot_restore_test", SNAPSHOT_SOURCE)


def window(
    window_id,
    app_id,
    *,
    desktop_entry=None,
    identity_confidence="exact",
    title=None,
    workspace="1",
    output="eDP-1",
    category="user-application",
    managed_by=None,
    floating=False,
    fullscreen=0,
    focused=False,
    con_id=100,
    pid=1000,
    parent=None,
    index=0,
    xclass=None,
    instance=None,
    executable=None,
    scratchpad=None,
):
    return {
        "window_id": window_id,
        "snapshot_identity": f"{app_id or xclass or executable or 'unknown'}#{window_id[1:]}",
        "runtime": {"con_id": con_id, "pid": pid},
        "workspace": workspace,
        "output": output,
        "app_id": app_id,
        "xwayland": {"class": xclass, "instance": instance},
        "executable_basename": executable or app_id,
        "title_hint": title,
        "restore_identity": {
            "app_id": app_id,
            "class": xclass,
            "instance": instance,
            "desktop_entry": desktop_entry,
            "confidence": identity_confidence,
            "matched_by": "desktop-id" if desktop_entry else None,
        },
        "restore_adapter": "generic-desktop" if desktop_entry else "unknown",
        "classification": {"category": category, "managed_by": managed_by},
        "focused": focused,
        "urgent": False,
        "floating": floating,
        "fullscreen_mode": fullscreen,
        "rect": {"x": 0, "y": 0, "width": 800, "height": 600},
        "percent": 1.0,
        "marks": [],
        "scratchpad": scratchpad or {"member": False, "visibility": "not-applicable", "state": "none"},
        "tree_position": {"parent_container_id": parent, "branch": "tiling", "index": index},
    }


def session(
    windows,
    *,
    persistent=False,
    name="test",
    outputs=("eDP-1",),
    workspace_outputs=None,
    containers=None,
    focused=None,
    captured_at="2026-10-05T00:00:00.000Z",
):
    workspace_outputs = workspace_outputs or {}
    workspace_names = []
    for item in windows:
        workspace = item.get("workspace")
        if workspace is not None and workspace not in workspace_names:
            workspace_names.append(workspace)
    metadata = {
        "captured_at": captured_at,
        "desktop": "sway:wlroots:swayfx",
        "session_type": "wayland",
    }
    if persistent:
        metadata.update({
            "session_name": name,
            "created_at": captured_at,
            "updated_at": captured_at,
        })
    focused_id = focused
    if focused_id is None:
        focused_id = next((item["window_id"] for item in windows if item.get("focused")), None)
    return {
        "schema": "labfy.sway.session-snapshot",
        "version": 1,
        "metadata": metadata,
        "compositor": {
            "variant": "sway",
            "version": "0.6",
            "sway_version": "1.12.0",
            "layout_engine": "sway-native",
        },
        "outputs": [
            {"name": item, "active": True, "focused": index == 0}
            for index, item in enumerate(outputs)
        ],
        "workspaces": [
            {
                "name": item,
                "output": workspace_outputs.get(item, outputs[0] if outputs else None),
                "layout": "splith",
                "orientation": "horizontal",
            }
            for item in workspace_names
        ],
        "containers": containers or [],
        "windows": copy.deepcopy(windows),
        "focus": {
            "output": outputs[0] if outputs else None,
            "workspace": next((item.get("workspace") for item in windows if item["window_id"] == focused_id), None),
            "container_id": None,
            "window_id": focused_id,
        },
    }


def action_types(plan):
    return [item["action"] for item in plan["actions"]]


class RestorePlannerTest(unittest.TestCase):
    def test_exact_reuse_identical_session_has_no_mutation(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", focused=True)
        live = copy.deepcopy(saved)
        live["runtime"] = {"con_id": 999, "pid": 8888}
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        self.assertEqual(action_types(plan), ["reuse-window"])
        self.assertEqual(plan["matches"][0]["confidence"], "exact")
        self.assertEqual(plan["diagnostics"]["mutating_commands_executed"], 0)

    def test_missing_exact_user_application_uses_future_uwsm_backend(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", focused=True)
        plan = restore.build_restore_plan(session([saved], persistent=True), session([]))
        launch = next(item for item in plan["actions"] if item["action"] == "launch-application")
        self.assertEqual(launch["launch"]["argv"], ["uwsm", "app", "--", "firefox.desktop"])
        self.assertFalse(launch["launch"]["execute_in_step19a"])

    def test_synthetic_firefox_kitty_limusic_with_only_limusic_live(self):
        saved = [
            window("w1", "firefox", desktop_entry="firefox.desktop"),
            window("w2", "kitty", desktop_entry="kitty.desktop", executable="kitty"),
            window("w3", "limusic-app", desktop_entry="limusic.desktop", workspace="10", category="autostart-managed-application", managed_by="sway-autostart"),
        ]
        live = [copy.deepcopy(saved[2])]
        plan = restore.build_restore_plan(session(saved, persistent=True), session(live))
        launches = [item["desktop_entry"] for item in plan["actions"] if item["action"] == "launch-application"]
        self.assertEqual(launches, ["firefox.desktop", "kitty.desktop"])
        self.assertEqual(sum(item["action"] == "reuse-window" for item in plan["actions"]), 1)

    def test_existing_application_on_wrong_workspace_is_reused_then_moved(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", workspace="1", focused=True)
        live = window("w1", "firefox", desktop_entry="firefox.desktop", workspace="2", focused=True)
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        self.assertIn("reuse-window", action_types(plan))
        self.assertIn("move-to-workspace", action_types(plan))
        self.assertNotIn("launch-application", action_types(plan))
        move = next(item for item in plan["actions"] if item["action"] == "move-to-workspace")
        self.assertEqual(move["desired_workspace"], "1")

    def test_multi_window_matches_only_best_title_and_never_reuses_twice(self):
        saved_a = window("w1", "firefox", desktop_entry="firefox.desktop", title="Firefox — A")
        saved_b = window("w2", "firefox", desktop_entry="firefox.desktop", title="Firefox — B")
        live_b = window("w1", "firefox", desktop_entry="firefox.desktop", title="Firefox — B", pid=5000)
        plan = restore.build_restore_plan(session([saved_a, saved_b], persistent=True), session([live_b]))
        self.assertEqual(len(plan["matches"]), 1)
        self.assertEqual(plan["matches"][0]["source_window"], "w2")
        launch = next(item for item in plan["actions"] if item["action"] == "launch-application")
        self.assertEqual(launch["source_window"], "w1")

    def test_title_hint_is_not_required_identity(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", title="Ancien titre")
        live = window("w9", "firefox", desktop_entry="firefox.desktop", title="Nouveau titre")
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        self.assertEqual(plan["matches"][0]["source_window"], "w1")

    def test_app_id_without_desktop_entry_is_high_confidence(self):
        saved = window("w1", "custom-app", identity_confidence="unresolved")
        live = window("w7", "custom-app", identity_confidence="unresolved")
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        self.assertEqual(plan["matches"][0]["confidence"], "high")
        self.assertIn("app-id", plan["matches"][0]["matched_by"])

    def test_xwayland_class_without_app_id_is_high_confidence(self):
        saved = window("w1", None, xclass="LegacyApp", executable=None, identity_confidence="unresolved")
        live = window("w8", None, xclass="LegacyApp", executable=None, identity_confidence="unresolved")
        saved["executable_basename"] = None
        live["executable_basename"] = None
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        self.assertEqual(plan["matches"][0]["confidence"], "high")
        self.assertEqual(plan["matches"][0]["matched_by"], ["class"])

    def test_indistinguishable_live_candidates_are_ambiguous_but_one_to_one(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop")
        first = window("w1", "firefox", desktop_entry="firefox.desktop", pid=2000)
        second = window("w2", "firefox", desktop_entry="firefox.desktop", pid=3000)
        plan = restore.build_restore_plan(session([saved], persistent=True), session([first, second]))
        self.assertEqual(len(plan["matches"]), 1)
        self.assertEqual(plan["matches"][0]["confidence"], "ambiguous")

    def test_absent_autostart_application_is_not_launched(self):
        saved = window("w1", "limusic-app", desktop_entry="limusic.desktop", category="autostart-managed-application", managed_by="sway-autostart")
        plan = restore.build_restore_plan(session([saved], persistent=True), session([]))
        self.assertEqual(action_types(plan), ["skip-autostart-managed"])
        self.assertNotIn("launch-application", action_types(plan))

    def test_unresolved_window_requires_manual_action(self):
        saved = window("w1", None, identity_confidence="unresolved", executable=None)
        saved["executable_basename"] = None
        plan = restore.build_restore_plan(session([saved], persistent=True), session([]))
        self.assertEqual(action_types(plan), ["manual-required"])
        self.assertEqual(plan["actions"][0]["reason"], "no-exact-launch-identity")

    def test_missing_output_is_explicit_and_has_no_fallback_launch(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", output="HDMI-A-1")
        plan = restore.build_restore_plan(session([saved], persistent=True, outputs=("HDMI-A-1",)), session([], outputs=("eDP-1",)))
        self.assertEqual(action_types(plan), ["manual-required"])
        self.assertEqual(plan["actions"][0]["policy"], "deferred-no-fallback")

    def test_floating_difference_produces_intention_only(self):
        saved = window("w1", "kitty", desktop_entry="kitty.desktop", floating=True)
        live = window("w1", "kitty", desktop_entry="kitty.desktop", floating=False)
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        action = next(item for item in plan["actions"] if item["action"] == "restore-floating")
        self.assertTrue(action["desired_floating"])

    def test_fullscreen_difference_produces_intention_only(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", fullscreen=1)
        live = window("w1", "firefox", desktop_entry="firefox.desktop", fullscreen=0)
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        action = next(item for item in plan["actions"] if item["action"] == "restore-fullscreen")
        self.assertEqual(action["desired_fullscreen_mode"], 1)

    def test_layout_difference_is_partially_supported(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", parent="c1")
        live = window("w1", "firefox", desktop_entry="firefox.desktop")
        container = {
            "container_id": "c1", "parent_container_id": None,
            "tree_position": {"branch": "tiling", "index": 0},
            "layout": "splitv", "orientation": "vertical", "percent": 1.0,
        }
        plan = restore.build_restore_plan(session([saved], persistent=True, containers=[container]), session([live]))
        action = next(item for item in plan["actions"] if item["action"] == "restore-tree-position")
        self.assertEqual(action["capability"], "partially-supported")

    def test_scratchpad_hidden_intention(self):
        scratch = {"member": True, "visibility": "hidden", "state": "fresh"}
        saved = window("w1", "kitty", desktop_entry="kitty.desktop", workspace=None, output=None, scratchpad=scratch)
        live = window("w1", "kitty", desktop_entry="kitty.desktop")
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        self.assertIn("restore-scratchpad-hidden", action_types(plan))

    def test_focus_is_last_after_mutating_intentions(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", workspace="1", focused=True)
        live = window("w1", "firefox", desktop_entry="firefox.desktop", workspace="2", focused=True)
        plan = restore.build_restore_plan(session([saved], persistent=True, focused="w1"), session([live], focused="w1"))
        self.assertEqual(plan["actions"][-1]["action"], "restore-focus")
        self.assertTrue(plan["actions"][-1]["depends_on"])

    def test_infrastructure_is_never_launched(self):
        saved = window("w1", "quickshell", desktop_entry="org.quickshell.desktop", category="session-infrastructure")
        plan = restore.build_restore_plan(session([saved], persistent=True), session([]))
        self.assertEqual(action_types(plan), ["manual-required"])
        self.assertNotIn("launch-application", action_types(plan))

    def test_runtime_ids_are_observations_not_matching_identity(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop", con_id=7, pid=10)
        live = window("w9", "firefox", desktop_entry="firefox.desktop", con_id=900, pid=9999)
        plan = restore.build_restore_plan(session([saved], persistent=True), session([live]))
        self.assertEqual(plan["matches"][0]["source_window"], "w1")
        self.assertEqual(plan["policy"]["runtime_identity_fields"], [])
        self.assertEqual(plan["live"]["windows"][0]["runtime"], {"con_id": 900, "pid": 9999})

    def test_same_inputs_produce_byte_equivalent_plan(self):
        saved = [
            window("w1", "firefox", desktop_entry="firefox.desktop", title="A"),
            window("w2", "firefox", desktop_entry="firefox.desktop", title="B"),
        ]
        live = [window("w7", "firefox", desktop_entry="firefox.desktop", title="B")]
        source = session(saved, persistent=True)
        current = session(live)
        first = restore.build_restore_plan(source, current)
        second = restore.build_restore_plan(copy.deepcopy(source), copy.deepcopy(current))
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_cli_plan_uses_only_loader_collector_and_pure_planner(self):
        saved = window("w1", "firefox", desktop_entry="firefox.desktop")
        source = session([saved], persistent=True, name="cli")
        current = session([copy.deepcopy(saved)])
        before = copy.deepcopy(source)
        output = io.StringIO()
        with mock.patch.object(snapshot_backend, "show_session", return_value=source) as loader, mock.patch.object(
            snapshot_backend, "collect", return_value=current
        ) as collector, mock.patch.object(snapshot_backend, "validate_snapshot") as validator, mock.patch("sys.stdout", output):
            self.assertEqual(snapshot_backend.main(("plan", "cli")), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["schema"], "labfy.sway.restore-plan")
        loader.assert_called_once_with("cli")
        collector.assert_called_once()
        validator.assert_called_once_with(current)
        self.assertEqual(source, before)
        self.assertEqual(result["diagnostics"]["applications_launched"], 0)

    def test_planner_module_has_no_process_or_filesystem_execution_api(self):
        source_text = RESTORE_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", source_text)
        self.assertNotIn("subprocess.", source_text)
        self.assertNotIn("swaymsg", source_text)
        self.assertNotIn("os.system", source_text)


if __name__ == "__main__":
    unittest.main()

"""Explicit X11 identity; inert trees and owned temporary journals only."""
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from common import *
from test_prewarm import Sway as BaseSway
from session_v2.applications import launch_count
from session_v2.anchors import Anchors
from session_v2.errors import Failure
from session_v2.executor import Executor, preflight
from session_v2.ipc import surface_identity, X11_CLASS_PREFIX, walk, workspace
from session_v2.recovery import Recovery, JOURNAL, observe
from session_v2.snapshot import capture


KEY = X11_CLASS_PREFIX + "Chatgpt"
WEBAPP = "firefox.webapp-fcd72ebe-94c5-4209-b3f6-bbaa7784cded"
IMMICH_WEBAPP = "firefox.webapp-40f22022-70af-4784-81ee-100e6a56dc50"


class Sway(BaseSway):
    def __init__(self):
        super().__init__()
        for ws in self.value["nodes"][0]["nodes"]:
            ws.update(nodes=[], layout="splith", focused=False)
    def windows(self):
        return [n for n in walk(self.tree()) if n.get("app_id") or n.get("window")]
    def x11(self, identity=7, wm_class="Chatgpt", where="1", focus=True):
        node = self.add(None, identity, where, focus)
        node.update(window=0x10000 + identity, window_properties={"class": wm_class, "instance": "TEST_ONLY"})
        return node


def source():
    sway = Sway()
    sway.x11()
    sway.add("kitty", 8, focus=False)
    return sway


class XwaylandTests(unittest.TestCase):
    def test_typed_identity_is_exact_pure_and_requires_x11_window(self):
        node = source().windows()[0]
        original = copy.deepcopy(node)
        self.assertEqual(surface_identity(node), KEY)
        self.assertEqual(node, original)
        for change in ({"window": None}, {"window": True}, {"window": 0},
                       {"window_properties": {}}, {"window_properties": {"class": ""}}):
            self.assertIsNone(surface_identity({**node, **change}))
        self.assertEqual(surface_identity({**node, "app_id": "native-chatgpt"}), "native-chatgpt")
        with self.assertRaisesRegex(Failure, "SURFACE_IDENTITY_RESERVED"):
            surface_identity({**node, "app_id": KEY, "window": None})

    def test_catalog_rejects_unknown_class_and_native_prefix_impersonation(self):
        catalog = Catalog()
        node = source().windows()[0]
        spec = catalog.classify(node)
        self.assertEqual((spec.application_id, spec.strategy, spec.argv),
                         ("chatgpt", "single-window", ("/usr/bin/chatgpt",)))
        for wm_class in ("OtherApp", "chatgpt", None):
            with self.subTest(wm_class=wm_class), self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
                catalog.classify({**node, "window_properties": {"class": wm_class}})
        with self.assertRaisesRegex(Failure, "SURFACE_IDENTITY_RESERVED"):
            catalog.classify({"app_id": KEY})
        with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
            catalog.classify({"app_id": None})

    def test_capture_uses_application_singleton_without_runtime_identity(self):
        sway = source()
        original = sway.tree()
        data = capture(sway, Catalog(), None)
        app = next(a for a in data["applications"] if a["application_id"] == "chatgpt")
        slot = next(s for s in data["window_slots"] if s["application_id"] == "chatgpt")
        self.assertEqual(app["desktop_entry"], "chatgpt.desktop")
        self.assertEqual(slot["identity_evidence"], {"type": "application-singleton", "id": "chatgpt"})
        self.assertEqual(sway.tree(), original)
        for forbidden in (KEY, "window_properties", "con_id", "starttime"):
            self.assertNotIn(forbidden, json.dumps(data))

    def test_multiple_chatgpt_windows_refused_before_writing_snapshot(self):
        sway = source(); sway.x11(9, focus=False)
        with self.assertRaisesRegex(Failure, "APPLICATION_POLICY_MISMATCH"):
            capture(sway, Catalog(), None)
        self.assertEqual(sway.commands, [])

    def test_class_change_during_capture_is_not_a_stable_snapshot(self):
        sway = source(); original_windows = sway.windows
        def changed():
            next(n for n in walk(sway.value) if n.get("id") == 7)["window_properties"]["class"] = "OtherApp"
            return original_windows()
        sway.windows = changed
        with self.assertRaisesRegex(Failure, "SNAPSHOT_CHANGED"):
            capture(sway, Catalog(), None)

    def test_preflight_and_prewarm_admit_present_x11_without_launch(self):
        sway = source(); data = capture(sway, Catalog(), None)
        self.assertIn("chatgpt", preflight(data, sway, Catalog(), None))
        with tempfile.TemporaryDirectory() as temporary:
            engine = Executor(sway, Catalog(), None, Path(temporary), "/forbidden", process_identity=lambda pid: 123)
            def admitted(data, timeout, lock_fd, proof, prepared):
                self.assertEqual(prepared[7]["app_id"], KEY)
                self.assertFalse((Path(temporary) / JOURNAL).exists())
                return "admitted"
            with patch("session_v2.executor.launch") as launch, patch.object(engine, "_apply", side_effect=admitted):
                self.assertEqual(engine.apply(data, True), "admitted")
                launch.assert_not_called()
        self.assertEqual(sway.commands, [])

    def test_prewarm_launches_one_missing_chatgpt_then_observes_x11(self):
        sway = source(); data = capture(sway, Catalog(), None)
        workspace(sway.value, "1")["nodes"] = [n for n in workspace(sway.value, "1")["nodes"] if n["id"] != 7]
        workspace(sway.value, "1")["nodes"][0]["focused"] = True
        with tempfile.TemporaryDirectory() as temporary:
            engine = Executor(sway, Catalog(), None, Path(temporary), "/forbidden", process_identity=lambda pid: 123)
            calls = []
            def launch(spec, count, env):
                calls.append((spec.application_id, count)); sway.x11(9); return [object()]
            def settled(baseline, spec, session, allowed, timeout):
                self.assertEqual(spec.application_id, "chatgpt")
                self.assertEqual(session, sway.session)
                self.assertNotIn(9, baseline)
                self.assertIn(KEY, allowed)
                return engine._observe_prepared()
            with patch("session_v2.executor.launch", side_effect=launch), \
                 patch.object(engine, "_settle_fresh_chatgpt", side_effect=settled) as gate, \
                 patch.object(engine, "_apply", return_value="admitted"):
                self.assertEqual(engine.apply(data, True), "admitted")
                gate.assert_called_once()
            self.assertEqual(calls, [("chatgpt", 1)])
            self.assertFalse((Path(temporary) / JOURNAL).exists())
        self.assertEqual(sway.commands, [])

    def test_recovery_keeps_typed_identity_and_excludes_target_from_foreign(self):
        sway = source(); other = sway.x11(9, "OtherApp", focus=False)
        with tempfile.TemporaryDirectory() as temporary:
            recovery = Recovery(sway, Path(temporary), "b" * 32, "labfy-v2-stage-" + "b" * 32, start=lambda pid: 123)
            recovery.baseline({KEY, "kitty"})
            self.assertEqual([s["con_id"] for s in recovery.data["foreign"]], [9])
            node = next(n for n in sway.windows() if n["id"] == 7)
            recovery.admit(node)
            identity = recovery.data["windows"][0]["origin"]
            self.assertEqual((identity["con_id"], identity["app_id"], identity["pid"], identity["starttime"]),
                             (7, KEY, os.getpid(), 123))
            before = (Path(temporary) / JOURNAL).read_bytes()
            next(n for n in walk(sway.value) if n.get("id") == 7)["window_properties"]["class"] = "OtherApp"
            with self.assertRaisesRegex(Failure, "TARGET_IDENTITY_CHANGED"):
                recovery.admit(node)
            self.assertEqual((Path(temporary) / JOURNAL).read_bytes(), before)
            self.assertEqual(sway.commands, [])

    def test_old_untyped_x11_journal_cannot_gain_identity_silently(self):
        sway = source()
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            recovery = Recovery(sway, runtime, "b" * 32, "labfy-v2-stage-" + "b" * 32, start=lambda pid: 123)
            node = next(n for n in sway.windows() if n["id"] == 7)
            recovery.admit(node)
            for field in ("origin", "expected"):
                recovery.data["windows"][0][field]["app_id"] = None
            recovery.publish()
            before = (runtime / JOURNAL).read_bytes()
            with self.assertRaisesRegex(Failure, "TARGET_IDENTITY_CHANGED"):
                recovery.admit(node)
            self.assertEqual((runtime / JOURNAL).read_bytes(), before)
            self.assertEqual(sway.commands, [])

    def test_explicit_webapps_autostart_owns_launch_and_unknown_is_refused(self):
        catalog = Catalog()
        for identity, expected_id in ((WEBAPP, "whatsapp-web"), (IMMICH_WEBAPP, "immich-web")):
            with self.subTest(identity=identity):
                spec = catalog.classify({"app_id": identity})
                self.assertEqual(spec.application_id, expected_id)
                self.assertEqual((spec.strategy, spec.managed_by, spec.argv),
                                 ("managed-autostart", "sway-autostart", ()))
                app = dict(application_id=spec.application_id, desktop_entry=spec.desktop_entry,
                           strategy=spec.strategy, expected_windows=1,
                           managed_by=spec.managed_by, identity_provider=None)
                self.assertEqual(catalog.validate(app), spec)
                self.assertEqual(launch_count(app, 0), 0)
                self.assertEqual(launch_count(app, 1), 0)
                with self.assertRaisesRegex(Failure, "UNEXPECTED_EXTRA_WINDOW"):
                    launch_count(app, 2)
        for identity in ("firefox.webapp-unregistered", IMMICH_WEBAPP + "-suffix"):
            with self.assertRaisesRegex(Failure, "APPLICATION_UNSUPPORTED"):
                catalog.classify({"app_id": identity})

    def test_swap_accepts_exact_x11_target_and_rejects_identity_changes(self):
        for change in (None, "class", "pid"):
            with self.subTest(change=change):
                sway = Sway()
                output = sway.value["nodes"][0]
                output["nodes"].append(dict(id=30, type="workspace", name="STAGE", layout="splith", nodes=[]))
                target = copy.deepcopy(sway.x11(where="STAGE"))
                anchor = sway.add("TEST_ONLY_ANCHOR", 99, focus=False)
                anchors = Anchors.__new__(Anchors)
                anchors.sway = sway; anchors.anchor = lambda slot: anchor
                if change == "class":
                    workspace(sway.value, "STAGE")["nodes"][0]["window_properties"]["class"] = "OtherApp"
                if change == "pid": workspace(sway.value, "STAGE")["nodes"][0]["pid"] += 1
                def swap(command):
                    sway.commands.append(command)
                    a, b = workspace(sway.value, "1")["nodes"], workspace(sway.value, "STAGE")["nodes"]
                    a[0], b[0] = b[0], a[0]
                sway.command = swap
                if change:
                    with self.assertRaisesRegex(Failure, "TARGET_IDENTITY_CHANGED"):
                        anchors.swap("slot-1", target, "1", "STAGE", (KEY,))
                    self.assertEqual(sway.commands, [])
                else:
                    anchors.swap("slot-1", target, "1", "STAGE", (KEY,))
                    self.assertEqual(sway.commands, ["[con_id=7] swap container with con_id 99"])
                    self.assertEqual(workspace(sway.value, "1")["nodes"][0]["id"], 7)


if __name__ == "__main__": unittest.main()

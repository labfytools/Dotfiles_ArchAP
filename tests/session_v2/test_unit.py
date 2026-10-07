import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import uuid
from common import *
from session_v2.errors import Failure
from session_v2 import schema
from session_v2.checkpoint import Store
from session_v2.storage import atomic, read, loads, lock, private_dir
from session_v2.layout import compile_plan
from session_v2.applications import launch_count
from session_v2.slots import assign
from session_v2.native_host import validate as native_validate
from session_v2.cli import migration


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="labfy-session-v2-unit-")
        self.root = Path(self.temp.name)
        self.data = fixture()
    def tearDown(self): self.temp.cleanup()

    def test_schema_exact(self):
        self.assertEqual(schema.validate(self.data), self.data)
        for key in self.data:
            broken = copy.deepcopy(self.data); del broken[key]
            with self.assertRaises(Failure): schema.validate(broken)
        self.data["pid"] = 1
        with self.assertRaises(Failure): schema.validate(self.data)

    def test_types_version_and_identity(self):
        for value in (True, 2, "1", None):
            broken = copy.deepcopy(self.data); broken["version"] = value
            with self.assertRaises(Failure): schema.validate(broken)
        self.data["applications"][0]["expected_windows"] = True
        with self.assertRaises(Failure): schema.validate(self.data)

    def test_references(self):
        for mutate in (lambda d: d["window_slots"][0].update(application_id="absent"),
                       lambda d: d.update(focus="absent"),
                       lambda d: d["window_slots"][0].update(tree_path=[7]),
                       lambda d: d["applications"][0].update(expected_windows=2)):
            d = copy.deepcopy(self.data); mutate(d)
            with self.assertRaises(Failure): schema.validate(d)

    def test_unsupported_states(self):
        for key in ("fullscreen", "scratchpad"):
            d = copy.deepcopy(self.data); d["window_slots"][0]["state"][key] = True
            with self.assertRaisesRegex(Failure, "CAPABILITY_UNSUPPORTED"): schema.validate(d)

    def test_command_injection(self):
        for value in ('x; exec echo bad', '../x', 'x"', 'x\n'):
            d = copy.deepcopy(self.data); d["workspaces"][0]["workspace"] = value
            with self.assertRaises(Failure): schema.validate(d)

    def test_plan_pure(self):
        plan = compile_plan(self.data, "a" * 32)
        self.assertEqual(sum(o.kind == "create" for o in plan), 3)
        self.assertTrue(all(o.kind in ("workspace", "create", "focus", "layout") for o in plan))
        self.assertFalse(any("launch" in str(o) for o in plan))

    def test_checkpoint_permissions(self):
        store = Store(self.root)
        store.save("example", self.data)
        self.assertEqual(store.load("example"), self.data)
        self.assertEqual(store.path("example").stat().st_mode & 0o777, 0o600)
        self.assertEqual(store.sessions.stat().st_mode & 0o777, 0o700)
        store.checkpoint(self.data)
        self.assertEqual(store.last(), self.data)
        self.assertEqual(store.list(), ["example"])
        store.delete("example")
        self.assertEqual(store.list(), [])

    def test_intermediate_directory_permissions(self):
        private_dir(self.root / "one/two/three")
        for name in ("one", "one/two", "one/two/three"):
            self.assertEqual((self.root / name).stat().st_mode & 0o777, 0o700)

    def test_cli_storage_checkpoint_and_startup_mock(self):
        from session_v2.cli import main
        state = private_dir(self.root / "state")
        runtime = private_dir(self.root / "runtime")
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "XDG_RUNTIME_DIR": str(runtime)}):
            with patch("session_v2.cli.Sway") as sway, patch("session_v2.cli.FirefoxProvider"), patch("session_v2.cli.capture", return_value=self.data) as capture_mock:
                sway.return_value.session = "new-session"
                empty = io.StringIO()
                with redirect_stdout(empty): self.assertEqual(main(["startup-status", "--socket", "/mock"]), 0)
                self.assertEqual(json.loads(empty.getvalue()), {"eligible": False, "claimed": False})
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["checkpoint-last", "--execute", "--reason", "logout", "--socket", "/mock"]), 0)
                    self.assertEqual(main(["save", "example", "--execute", "--socket", "/mock"]), 0)
                self.assertEqual(capture_mock.call_args_list[0].args[3], "logout")
                def cli(args):
                    output = io.StringIO()
                    with redirect_stdout(output): code = main(args)
                    self.assertEqual(code, 0)
                    return json.loads(output.getvalue())
                self.assertEqual(cli(["list"]), {"sessions": ["example"]})
                self.assertEqual(cli(["show", "example"]), self.data)
                self.assertTrue(cli(["plan", "example"])["operations"])
                self.assertTrue(cli(["startup-status", "--execute", "--socket", "/mock"])["eligible"])
                self.assertFalse(cli(["startup-status", "--socket", "/mock"])["eligible"])
                self.assertEqual(cli(["delete", "example", "--execute"]), {"status": "deleted"})

    def test_checkpoint_failed_validation_preserves_old(self):
        store = Store(self.root); store.save("a", self.data)
        invalid = copy.deepcopy(self.data); invalid["version"] = 9
        with self.assertRaises(Failure): store.save("a", invalid)
        self.assertEqual(store.load("a"), self.data)
        self.assertFalse(list(store.sessions.glob(".tmp-*")))

    def test_paths_links(self):
        store = Store(self.root)
        for name in ("../a", "a/b", "", "/tmp/a", ".", "a.json", None):
            with self.assertRaises(Failure): store.path(name)
        target = self.root / "outside"; atomic(target, {})
        store.path("evil").symlink_to(target)
        with self.assertRaises((Failure, OSError)): store.save("evil", self.data)
        self.assertEqual(read(target), {})

    def test_json_strict(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{}junk', b'\xff', b'[' * 2000):
            with self.assertRaises(Failure): loads(raw)

    def test_lock(self):
        with lock(self.root):
            with self.assertRaisesRegex(Failure, "TRANSACTION_BUSY"):
                with lock(self.root): pass

    def test_launch_policy(self):
        a = self.data["applications"][0].copy()
        for strategy, expected, present, launches in (
            ("managed-autostart", 2, 0, 0), ("single-window", 1, 0, 1), ("single-window", 1, 1, 0),
            ("browser-self-restore", 2, 0, 1), ("browser-self-restore", 2, 1, 0),
            ("terminal", 3, 1, 2), ("multi-instance", 3, 1, 2)):
            a.update(strategy=strategy, expected_windows=expected)
            self.assertEqual(launch_count(a, present), launches)
        a.update(strategy="unknown")
        with self.assertRaises(Failure): launch_count(a, 0)

    def test_counts(self):
        slots = self.data["window_slots"]
        with self.assertRaisesRegex(Failure, "APPLICATION_WINDOWS_INCOMPLETE"): assign(slots, [])
        with self.assertRaisesRegex(Failure, "UNEXPECTED_EXTRA_WINDOW"): assign(slots, [{"id": x} for x in range(4)])

    def test_exact_inverted(self):
        values = [str(uuid.uuid4()), str(uuid.uuid4())]
        slots = [{"slot_id": str(i), "identity_requirement": "exact", "identity_evidence": {"type": schema.PROVIDER, "id": u}} for i,u in enumerate(values)]
        self.assertEqual(assign(slots, [{"id": 99}, {"id": 12}], {values[0]: 12, values[1]: 99}), {"0": 12, "1": 99})
        with self.assertRaisesRegex(Failure, "EXACT_WINDOW_IDENTITY_MISSING"): assign(slots, [{"id": 99}, {"id": 12}], {})
        with self.assertRaisesRegex(Failure, "EXACT_WINDOW_IDENTITY_COLLISION"): assign(slots, [{"id": 99}, {"id": 12}], {u: 99 for u in values})

    def test_interchangeable_best_effort(self):
        for level in ("interchangeable", "best-effort"):
            slots = [{"slot_id": s, "identity_requirement": level, "identity_evidence": None} for s in ("B", "A")]
            self.assertEqual(assign(slots, [{"id": 9}, {"id": 2}]), {"A": 2, "B": 9})

    def test_native_strict(self):
        good = {"op": "map-window", "uuid": str(uuid.uuid4()), "runtime_token": "a" * 32}
        self.assertEqual(native_validate(good), good)
        for bad in ([], {}, {**good, "command": "x"}, {**good, "uuid": 2}, {**good, "runtime_token": "a;exec x"}, {**good, "op": "exec"}):
            with self.assertRaises(Failure): native_validate(bad)

    def test_cli_execute_required(self):
        for command in ("apply", "apply-last", "save", "delete", "checkpoint-last", "capture"):
            p = subprocess.run([sys.executable, "-B", str(BACKEND / "session-v2.py"), command], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(json.loads(p.stdout)["reason"], "EXECUTE_REQUIRED")

    def test_coexistence_and_migration(self):
        v1 = self.root / "legacy.json"
        atomic(v1, {"schema": "labfy.sway.session-snapshot", "version": 1, "windows": [{"app_id": "firefox"}]})
        before = v1.read_bytes()
        result = migration(v1)
        self.assertEqual(result["classification"], "needs exact identity")
        Store(private_dir(self.root / "session-v2")).checkpoint(self.data)
        self.assertEqual(v1.read_bytes(), before)
        atomic(v1, {"schema": "labfy.sway.session-snapshot", "version": 9, "windows": []})
        with self.assertRaisesRegex(Failure, "V1_FORMAT_UNRECOGNIZED"): migration(v1)

    def test_multi_output_preflight_synthetic(self):
        from session_v2.executor import preflight
        from unittest.mock import Mock
        second = fixture("D", "TEST_ONLY_SECOND")
        second["workspaces"][0]["output"] = "SYNTHETIC-2"
        data = copy.deepcopy(self.data)
        data["outputs"].append({"name": "SYNTHETIC-2"})
        for key in ("applications", "window_slots", "workspaces"): data[key] += second[key]
        sway = Mock()
        sway.outputs.return_value = [{"name": o["name"], "active": True} for o in data["outputs"]]
        sway.windows.return_value = []
        sway.tree.return_value = {"nodes": []}
        self.assertEqual(len(preflight(data, sway, catalog(data), None)), 4)
        sway.outputs.return_value.pop()
        with self.assertRaisesRegex(Failure, "OUTPUT_UNAVAILABLE"): preflight(data, sway, catalog(data), None)
        sway.command.assert_not_called()

    def test_resume_attempts_all_owned_helpers(self):
        from session_v2.guard import resume_helpers
        helpers = [{"pid": i, "fd": i, "script": "/test/autotiling"} for i in (100, 101)]
        counts = {"helpers_resumed": 0}
        with patch("session_v2.guard.verify_helper", side_effect=[Failure("HELPER_SESSION_INVALID"), None]), \
             patch("session_v2.guard.signal.pidfd_send_signal") as send, \
             patch("session_v2.guard.helper_state", return_value="S"):
            self.assertFalse(resume_helpers(helpers, "/test/socket", counts))
            self.assertEqual(counts["helpers_resumed"], 1)
            self.assertEqual(send.call_args.args[0], 101)
            self.assertTrue(helpers[1]["resumed"])
            self.assertNotIn("resumed", helpers[0])

    def test_report_rejects_private_fields_and_bool_version(self):
        from session_v2.observability import Attempt, validate as validate_report
        report = Attempt(self.root / "attempt.json", "a" * 32, self.data).data
        for key in ("title", "url", "argv", "environment", "cookies"):
            with self.assertRaisesRegex(Failure, "REPORT_SCHEMA"): validate_report({**report, key: "forbidden"})
        with self.assertRaisesRegex(Failure, "REPORT_SCHEMA"): validate_report({**report, "version": True})

    def test_json_schema_matches_fixture(self):
        import jsonschema
        contract = json.loads((BACKEND / "session_v2/schema-v1.json").read_text())
        jsonschema.Draft202012Validator.check_schema(contract)
        jsonschema.validate(self.data, contract)
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate({**self.data, "pid": 1}, contract)


if __name__ == "__main__": unittest.main()

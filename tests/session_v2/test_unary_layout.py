"""Regression: unary tabbed/stacked Sway containers are restorable V2 nodes.

No commands are sent to the user's active compositor.
"""
import copy
import json
import tempfile
import unittest

from common import *
from test_prewarm import Sway
from session_v2.snapshot import capture
from session_v2.ipc import workspace, canonical
from session_v2.schema import validate
from session_v2.layout import compile_plan
from session_v2.checkpoint import Store
from session_v2.errors import Failure


class UnaryLayoutTests(unittest.TestCase):
    def sample(self, layout):
        sway = Sway()
        ws = workspace(sway.value, "1")
        workspace(sway.value, "10")["layout"] = "splith"
        ws["layout"] = "splith"
        first = sway.add("kitty", 7, focus=True)
        second = sway.add("proton-pass", 8, focus=False)
        ws["nodes"] = [
            first,
            {"id": 70, "type": "con", "layout": layout, "nodes": [second]},
        ]
        return sway

    def test_unary_tabbed_and_stacked_capture_schema_and_persistence(self):
        for layout in ("tabbed", "stacked"):
            with self.subTest(layout=layout):
                sway = self.sample(layout)
                before = sway.tree()
                data = capture(sway, Catalog(), None)
                root = next(w["root"] for w in data["workspaces"] if w["workspace"] == "1")
                self.assertEqual(root["layout"], "splith")
                group = root["children"][1]
                self.assertEqual(group["layout"], layout)
                self.assertEqual(len(group["children"]), 1)
                slot = group["children"][0]["slot_id"]
                self.assertEqual(next(s["tree_path"] for s in data["window_slots"]
                                      if s["slot_id"] == slot), [1, 0])
                self.assertEqual(validate(data), data)
                self.assertEqual(sway.tree(), before)
                plan = compile_plan(data, "a" * 32)
                self.assertTrue(any(op.kind == "layout" and op.layout == layout and
                                    op.parent == (1,) for op in plan))
                mapping = {7: root["children"][0]["slot_id"], 8: slot}
                self.assertEqual(canonical(before, "1", mapping),
                                 {"splith": [root["children"][0]["slot_id"],
                                             {layout: [slot]}]})
                with tempfile.TemporaryDirectory() as path:
                    store = Store(Path(path))
                    store.save("unary", data)
                    self.assertEqual(store.load("unary"), data)
                try:
                    import jsonschema
                except ImportError:
                    continue
                schema = json.loads((BACKEND / "session_v2/schema-v2.json").read_text())
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.Draft202012Validator(schema).validate(data)

    def test_unary_split_and_none_remain_normalized(self):
        for layout in ("splith", "splitv", "none"):
            with self.subTest(layout=layout):
                sway = self.sample(layout)
                data = capture(sway, Catalog(), None)
                root = next(w["root"] for w in data["workspaces"] if w["workspace"] == "1")
                self.assertIn("slot_id", root["children"][1])
                self.assertEqual(len(data["window_slots"]), 3)

    def test_invalid_unary_split_stays_rejected(self):
        data = capture(self.sample("tabbed"), Catalog(), None)
        root = next(w["root"] for w in data["workspaces"] if w["workspace"] == "1")
        root["children"][1]["layout"] = "splitv"
        with self.assertRaisesRegex(Failure, "TREE_ARITY"):
            validate(data)
        try:
            import jsonschema
        except ImportError:
            return
        from jsonschema import ValidationError
        contract = json.loads((BACKEND / "session_v2/schema-v2.json").read_text())
        with self.assertRaises(ValidationError):
            jsonschema.validate(data, contract)


if __name__ == "__main__":
    unittest.main()

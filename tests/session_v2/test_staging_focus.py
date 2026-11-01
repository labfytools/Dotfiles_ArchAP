"""Focus staging admission: synthetic trees; no compositor or client mutation."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from common import *
from session_v2.executor import Executor, staging_order
from session_v2.recovery import JOURNAL, command_focus
from session_v2.ipc import walk, workspace
from session_v2.errors import Failure, Deferred
from test_prewarm import Sway, Provider
from login_focus import checkpoint

def leaf(identity, **extra):
    return dict(id=identity, type="con", app_id="TEST_ONLY", nodes=[], floating_nodes=[],
                focused=False, **extra)

def branch(identity, children, focus=None):
    return dict(id=identity, type="con", layout="splith", nodes=children,
                floating_nodes=[], focused=False, focus=focus or [n["id"] for n in children])

def admitted_tree():
    # Exact admission ancestry: 37 / (16 / (58,60)), including unary wrappers.
    root = branch(32, [branch(38, [
        branch(52, [branch(54, [leaf(37)])]),
        branch(51, [branch(65, [leaf(16)]),
                    branch(59, [branch(64, [leaf(58)]), branch(61, [leaf(60)])])],
               [65, 59])], [51, 52])])
    ws = dict(id=29, type="workspace", name="1", layout="splith", nodes=[root],
              floating_nodes=[], focused=False, focus=[32])
    return dict(id=1, type="root", nodes=[dict(id=2, type="output", name="HEADLESS-1", nodes=[ws])])

class StagingFocusTests(unittest.TestCase):
    def setUp(self):
        self.tree = admitted_tree()
        self.nodes = {n["id"]: n for n in walk(self.tree)}
        self.stage = [self.nodes[i] for i in (37, 16, 58, 60)]
        self.nodes[16]["focused"] = True

    def order(self):
        return [n["id"] for n in staging_order(self.tree, self.stage)]

    def focus(self, identity):
        for n in walk(self.tree): n["focused"] = n["id"] == identity

    def test_focused_leaf_is_last_and_other_order_is_stable(self):
        before = copy.deepcopy(self.tree)
        self.assertEqual(self.order(), [37, 58, 60, 16])
        self.assertEqual(self.tree, before)
        self.assertEqual([n["id"] for n in self.stage], [37, 16, 58, 60])

    def test_internal_focus_keeps_entire_branch_last(self):
        self.focus(59)
        self.stage = [self.nodes[i] for i in (58, 37, 60, 16)]
        self.assertEqual(self.order(), [37, 16, 58, 60])

    def test_foreign_source_leaf_refuses(self):
        self.nodes[38]["nodes"].append(leaf(99))
        with self.assertRaisesRegex(Failure, "RESTORE_FOCUS_STAGING_UNPROVEN"):
            self.order()

    def test_shown_scratchpad_source_leaf_refuses(self):
        workspace(self.tree, "1")["floating_nodes"].append(leaf(99, scratchpad_state="changed"))
        with self.assertRaisesRegex(Failure, "RESTORE_FOCUS_STAGING_UNPROVEN"):
            self.order()

    def test_internal_focus_with_nonstaged_descendant_survives(self):
        self.nodes[59]["nodes"].append(leaf(99))
        self.focus(59)
        self.stage = [self.nodes[i] for i in (58, 37, 60, 16)]
        self.assertEqual(self.order(), [37, 16, 58, 60])

    def test_foreign_focus_is_preserved_without_reordering(self):
        foreign = leaf(99)
        self.nodes[38]["nodes"].append(foreign)
        self.focus(99)
        self.assertEqual(self.order(), [37, 16, 58, 60])

    def test_workspace_focus_is_preserved_with_foreign_survivor(self):
        self.nodes[38]["nodes"].append(leaf(99))
        self.focus(29)
        self.assertEqual(self.order(), [37, 16, 58, 60])

    def test_hidden_scratchpad_elsewhere_does_not_block_empty_source(self):
        scratch = dict(id=100, type="workspace", name="__i3_scratch", nodes=[],
                       floating_nodes=[leaf(99, scratchpad_state="changed")], focused=False)
        self.tree["nodes"][0]["nodes"].append(scratch)
        self.assertEqual(self.order(), [37, 58, 60, 16])

    def test_existing_internal_ancestor_prediction_is_not_weakened(self):
        self.assertEqual(command_focus(self.tree, 16, 'move container to workspace "TEST_ONLY_STAGE"'),
                         dict(con_id=32, workspace="1"))

    def test_foreign_source_outside_checkpoint_refuses_before_journals_or_moves(self):
        sway = Sway()
        sway.add("kitty", 11, focus=False)
        sway.add("firefox", 12)
        old = workspace(sway.value, "1")
        other = dict(id=90, type="workspace", name="OTHER", layout="splith",
                     nodes=old["nodes"], focused=False)
        old["nodes"] = []
        sway.value["nodes"][0]["nodes"].append(other)
        sway.add("TEST_ONLY_FOREIGN", 99, "OTHER", focus=False)
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            with patch("subprocess.Popen", side_effect=AssertionError("NO_PROCESS_ALLOWED")):
                with self.assertRaisesRegex(Deferred, "RESTORE_FOCUS_STAGING_UNPROVEN"):
                    Executor(sway, Catalog(), Provider(), runtime, "/forbidden").apply(checkpoint(), True)
            self.assertEqual(sway.commands, [])
            self.assertFalse((runtime / JOURNAL).exists())
            self.assertFalse((runtime / "session-v2-restore-attempt.json").exists())

if __name__ == "__main__":
    unittest.main()

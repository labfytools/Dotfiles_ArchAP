"""Ressources temporaires avec PID runtime épinglé et identité exacte.

La propriété ne découle jamais d'un préfixe. Tout kill est précédé d'une nouvelle
lecture et d'un contrôle pidfd + PID du helper + app_id autorisé de la transaction.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from .errors import require
from .ipc import until, canonical, location
from .layout import compile_plan, trees
from .model import normalized


class Anchors:
    def __init__(self, sway, data, tx, executable, env=None):
        require(Path(executable).is_absolute() and Path(executable).is_file(), "ANCHOR_HELPER_UNAVAILABLE")
        self.sway, self.data, self.tx = sway, data, tx
        self.plan = compile_plan(data, tx)
        self.ids = {}
        self.active = True
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, env=env, start_new_session=True)
        self.pidfd = os.pidfd_open(self.process.pid)
        self.allowed = {self.identity(s["slot_id"]) for s in data["window_slots"] if not s["state"]["floating"]}

    def identity(self, slot): return "labfy-v2-anchor-" + self.tx + "-" + slot

    def owned(self, node):
        signal.pidfd_send_signal(self.pidfd, 0)
        return node.get("pid") == self.process.pid and node.get("app_id") in self.allowed

    def anchor(self, slot):
        require(self.active, "TRANSACTION_INACTIVE")
        found = [n for n in self.sway.windows() if n.get("app_id") == self.identity(slot)]
        require(len(found) == 1 and self.owned(found[0]), "ANCHOR_OWNERSHIP_INVALID")
        return found[0]

    def mutate(self, slot, operation):
        node = self.anchor(slot)
        self.sway.command(f'[con_id={node["id"]}] {operation}')

    def build(self, progress=lambda *_: None):
        outputs = {w["workspace"]: w["output"] for w in self.data["workspaces"]}
        for op in self.plan:
            if op.kind == "workspace":
                self.sway.command("workspace " + json.dumps(op.workspace))
                self.sway.command("move workspace to output " + json.dumps(outputs[op.workspace]))
            elif op.kind == "create":
                self.process.stdin.write(("create " + self.identity(op.slot_id) + "\n").encode())
                self.process.stdin.flush()
                until(lambda: any(n.get("app_id") == self.identity(op.slot_id) for n in self.sway.windows()))
                self.ids[op.slot_id] = self.anchor(op.slot_id)["id"]
                progress("anchor", len(self.ids))
            elif op.kind == "focus": self.mutate(op.slot_id, "focus")
            elif op.kind == "layout":
                self.mutate(op.slot_id, "focus")
                layout = "stacking" if op.layout == "stacked" else op.layout
                if op.root: self.mutate(op.slot_id, "layout " + layout)
                else:
                    self.mutate(op.slot_id, "split " + ("v" if op.layout == "splitv" else "h"))
                    if op.layout in ("tabbed", "stacked"): self.mutate(op.slot_id, "layout " + layout)
            else: require(False, "ANCHOR_PLAN_INVALID")
        self.verify(self.ids)
        progress("all-anchors", len(self.ids))

    def verify(self, mapping):
        tree = self.sway.tree()
        reverse = {v: k for k, v in mapping.items()}
        for t in trees(self.data):
            require(canonical(tree, t.workspace, reverse) == normalized(t.root), "FINAL_TREE_MISMATCH")

    def swap(self, slot, target, target_workspace, stage, allowed_app_ids):
        anchor = self.anchor(slot)
        before = self.sway.tree()
        live = next((n for n in self.sway.windows() if n["id"] == target["id"]), None)
        require(live and live.get("pid") == target.get("pid") and live.get("app_id") == target.get("app_id") and live.get("app_id") in allowed_app_ids,
                "TARGET_IDENTITY_CHANGED")
        prior_a, prior_t = location(before, anchor["id"]), location(before, target["id"])
        require(prior_a and prior_a[0] == target_workspace and prior_t and prior_t[0] == stage, "SWAP_WORKSPACE_CHANGED")
        self.sway.command(f'[con_id={live["id"]}] swap container with con_id {anchor["id"]}')
        after = self.sway.tree()
        require(location(after, live["id"]) == prior_a and location(after, anchor["id"]) == prior_t, "SWAP_POSTCONDITION_FAILED")
        self.anchor(slot)

    def cleanup(self, progress=lambda *_: None):
        progress("before-cleanup", 0)
        count = 0
        for old in self.sway.windows():
            if not self.owned(old): continue
            fresh = next((n for n in self.sway.windows() if n["id"] == old["id"]), None)
            if fresh and self.owned(fresh):
                self.sway.command(f'[con_id={fresh["id"]}] kill')
                count += 1
                progress("cleanup", count)
        until(lambda: not any(self.owned(n) for n in self.sway.windows()))
        return count

    def close(self):
        self.active = False
        if not self.process.stdin.closed: self.process.stdin.close()
        try: self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            signal.pidfd_send_signal(self.pidfd, signal.SIGTERM)
            self.process.wait(timeout=3)
        os.close(self.pidfd)

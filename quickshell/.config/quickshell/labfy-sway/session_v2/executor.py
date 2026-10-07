"""Transaction de restauration fail-safe, sans promesse de rollback ACID.

Les applications sont conservées après erreur. Seul le helper possédé peut être
supprimé. La vérification de l'arbre n'est jamais remplacée par la cardinalité.
"""
import json
import time
import uuid
from pathlib import Path
from .errors import Failure, require
from .schema import validate, PROVIDER
from .storage import lock, private_dir
from .ipc import location, workspace, walk, until
from .applications import launch_count, launch
from .anchors import Anchors
from .guard import Guard
from .observability import Attempt
from .slots import assign


def preflight(data, sway, catalog, provider):
    validate(data)
    active = {o["name"] for o in sway.outputs() if o.get("active")}
    require({o["name"] for o in data["outputs"]}.issubset(active), "OUTPUT_UNAVAILABLE")
    specs = {a["application_id"]: catalog.validate(a) for a in data["applications"]}
    if any(a["identity_provider"] == PROVIDER for a in data["applications"]):
        require(provider is not None, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")
    nodes = sway.windows()
    admitted = set()
    for a in data["applications"]:
        members = [n for n in nodes if n.get("app_id") in specs[a["application_id"]].app_ids]
        launch_count(a, len(members))
        admitted.update(n["id"] for n in members)
    tree = sway.tree()
    for w in data["workspaces"]:
        ws = workspace(tree, w["workspace"])
        if ws:
            require(all(n["id"] in admitted for n in walk(ws) if n.get("app_id") or n.get("window")), "WORKSPACE_OCCUPIED")
    return specs


class Executor:
    def __init__(self, sway, catalog, provider, runtime, anchor_binary, env=None, progress=None):
        self.sway, self.catalog, self.provider = sway, catalog, provider
        self.runtime = private_dir(runtime)
        self.binary, self.env = anchor_binary, env
        self.progress = progress or (lambda *_: None)

    def apply(self, data, execute=False, timeout=30):
        require(execute is True, "EXECUTE_REQUIRED")
        require(type(timeout) in (int, float) and 0 < timeout <= 60, "TIMEOUT_INVALID")
        with lock(private_dir(self.runtime / "session-v2")) as lock_fd:
            return self._apply(data, timeout, lock_fd)

    def _apply(self, data, timeout, lock_fd):
        validate(data)
        tx = uuid.uuid4().hex
        attempt = Attempt(self.runtime / "session-v2-restore-attempt.json", tx, data)
        anchors, guard = None, None
        mapping = {}
        stage = "labfy-v2-stage-" + tx
        try:
            specs = preflight(data, self.sway, self.catalog, self.provider)
            attempt.update(phase="guard")
            anchors = Anchors(self.sway, data, tx, self.binary, self.env)
            guard = Guard(self.sway, anchors, self.runtime, attempt.path, lock_fd)
            attempt.update(helpers_suspended=guard.ready["helpers_suspended"])
            all_ids = {a for s in specs.values() for a in s.app_ids}
            def stage_node(n):
                fresh = next((x for x in self.sway.windows() if x["id"] == n["id"]), None)
                require(fresh and fresh.get("pid") == n.get("pid") and fresh.get("app_id") == n.get("app_id") and fresh.get("app_id") in all_ids,
                        "TARGET_IDENTITY_CHANGED")
                self.sway.command(f'[con_id={n["id"]}] move container to workspace ' + json.dumps(stage))
            for n in self.sway.windows():
                if n.get("app_id") in all_ids: stage_node(n)
            def progress(phase, count):
                values = {"phase": phase}
                if phase == "anchor": values["anchors_created"] = count
                elif phase == "cleanup": values["anchors_cleaned"] = count
                attempt.update(**values)
                self.progress(phase, count)
            start = time.monotonic()
            anchors.build(progress)
            attempt.data["timings_ms"]["anchor_build"] = (time.monotonic() - start) * 1000
            attempt.update(phase="launch")
            self.sway.command("workspace " + json.dumps(stage))
            children = []
            start = time.monotonic()
            for app in data["applications"]:
                spec = specs[app["application_id"]]
                count = sum(n.get("app_id") in spec.app_ids for n in self.sway.windows())
                children.extend(launch(spec, launch_count(app, count), self.env))
            end = time.monotonic() + timeout
            groups = {}
            while True:
                nodes = self.sway.windows()
                groups = {a["application_id"]: [n for n in nodes if n.get("app_id") in specs[a["application_id"]].app_ids] for a in data["applications"]}
                require(all(len(groups[a["application_id"]]) <= a["expected_windows"] for a in data["applications"]), "UNEXPECTED_EXTRA_WINDOW")
                if all(len(groups[a["application_id"]]) == a["expected_windows"] for a in data["applications"]): break
                require(time.monotonic() < end, "APPLICATION_WINDOWS_INCOMPLETE")
                time.sleep(.025)
            attempt.data["timings_ms"]["application_wait"] = (time.monotonic() - start) * 1000
            attempt.update(phase="resolve", applications_observed=len(groups))
            for app in data["applications"]:
                members = [s for s in data["window_slots"] if s["application_id"] == app["application_id"]]
                identity = None
                if app["identity_provider"] == PROVIDER:
                    expected = [s["identity_evidence"]["id"] for s in members if s["identity_requirement"] == "exact"]
                    identity = self.provider.resolve(expected, groups[app["application_id"]]) if expected else self.provider.capture(groups[app["application_id"]])
                    attempt.data["providers"] = [PROVIDER]
                    attempt.data["identity_resolutions"] = [{"uuid": k, "con_id": v} for k, v in identity.items()]
                mapping.update(assign(members, groups[app["application_id"]], identity))
            captured = {n["id"]: n for group in groups.values() for n in group}
            for n in captured.values():
                if location(self.sway.tree(), n["id"])[0] != stage: stage_node(n)
                if n.get("type") == "floating_con" or n.get("floating") in ("user_on", "auto_on"):
                    self.sway.command(f'[con_id={n["id"]}] floating disable')
            start = time.monotonic()
            for slot in data["window_slots"]:
                if slot["state"]["floating"]: continue
                target = captured[mapping[slot["slot_id"]]]
                anchors.swap(slot["slot_id"], target, slot["workspace"], stage, specs[slot["application_id"]].app_ids)
                attempt.update(phase="swap", anchors_swapped=attempt.data["anchors_swapped"] + 1)
                self.progress("swap", attempt.data["anchors_swapped"])
            attempt.data["timings_ms"]["swap"] = (time.monotonic() - start) * 1000
            start = time.monotonic()
            anchors.cleanup(progress)
            attempt.data["timings_ms"]["cleanup"] = (time.monotonic() - start) * 1000
            start = time.monotonic()
            anchors.verify(mapping)
            self._floating(data, mapping, captured)
            self._verify(data, mapping, specs, anchors)
            attempt.data["timings_ms"]["verification"] = (time.monotonic() - start) * 1000
            attempt.update(final_tree_verified=True, slots_filled=len(mapping), phase="focus")
            if data["focus"]:
                self.sway.command(f'[con_id={mapping[data["focus"]]}] focus')
            answer = guard.resume()
            attempt.update(helpers_resumed=answer["helpers_resumed"], phase="final-verification")
            self.progress("after-resume", len(mapping))
            self._verify(data, mapping, specs, anchors)
            require(data["focus"] is None or any(n["id"] == mapping[data["focus"]] and n.get("focused") for n in self.sway.windows()), "FINAL_FOCUS_MISMATCH")
            attempt.update(final_focus_verified=True, status="success", reason="SUCCESS", phase="complete")
            guard.finish()
            guard = None
            return attempt.data
        except Exception as exc:
            code = exc.code if isinstance(exc, Failure) else "RESTORE_INTERNAL_ERROR"
            attempt.update(status="failed", reason=code, phase="cleanup-error")
            raise Failure(code) from None
        finally:
            if guard is not None:
                try:
                    answer = guard.finish()
                    attempt.update(helpers_resumed=answer["helpers_resumed"], anchors_cleaned=attempt.data["anchors_cleaned"] + answer["anchors_cleaned"])
                except Exception: attempt.update(status="failed", reason="GUARD_RECOVERY_FAILED")
            if anchors is not None: anchors.close()

    def _floating(self, data, mapping, captured):
        for s in data["window_slots"]:
            if not s["state"]["floating"]: continue
            target = mapping[s["slot_id"]]
            n = next((n for n in self.sway.windows() if n["id"] == target), None)
            require(n and n.get("pid") == captured[target].get("pid"), "TARGET_IDENTITY_CHANGED")
            self.sway.command(f'[con_id={target}] move container to workspace ' + json.dumps(s["workspace"]))
            # Sway rattache une fenêtre déplacée en coordonnées à l'espace
            # visible de l'output : rendre la cible visible avant sa géométrie.
            self.sway.command("workspace " + json.dumps(s["workspace"]))
            output = next(w["output"] for w in data["workspaces"] if w["workspace"] == s["workspace"])
            self.sway.command("move workspace to output " + json.dumps(output))
            self.sway.command(f'[con_id={target}] floating enable')
            g = s["state"]["geometry"]
            self.sway.command(f'[con_id={target}] resize set width {g["width"]} px height {g["height"]} px')
            self.sway.command(f'[con_id={target}] move absolute position {g["x"]} px {g["y"]} px')

    def _verify(self, data, mapping, specs, anchors):
        anchors.verify(mapping)
        output_for = {w["name"]: o["name"] for o in self.sway.tree().get("nodes", [])
                      for w in walk(o) if w.get("type") == "workspace"}
        require(all(output_for.get(w["workspace"]) == w["output"] for w in data["workspaces"]), "FINAL_OUTPUT_MISMATCH")
        nodes = self.sway.windows()
        for a in data["applications"]:
            observed = sum(n.get("app_id") in specs[a["application_id"]].app_ids for n in nodes)
            require(observed >= a["expected_windows"], "APPLICATION_WINDOWS_INCOMPLETE")
            require(observed <= a["expected_windows"], "UNEXPECTED_EXTRA_WINDOW")
        for s in data["window_slots"]:
            n = next((n for n in nodes if n["id"] == mapping[s["slot_id"]]), None)
            require(n and n.get("app_id") in specs[s["application_id"]].app_ids, "TARGET_IDENTITY_CHANGED")
            if s["state"]["floating"]:
                require(location(self.sway.tree(), n["id"])[0] == s["workspace"] and n.get("floating") in ("auto_on", "user_on") and
                        all(n["rect"][k] == v for k, v in s["state"]["geometry"].items()), "FLOATING_GEOMETRY_MISMATCH")
        for a in data["applications"]:
            if a["identity_provider"] != PROVIDER: continue
            members = [n for n in nodes if n.get("app_id") in specs[a["application_id"]].app_ids]
            identities = self.provider.capture(members)
            for s in data["window_slots"]:
                if s["application_id"] == a["application_id"] and s["identity_requirement"] == "exact":
                    require(identities.get(s["identity_evidence"]["id"]) == mapping[s["slot_id"]], "EXACT_WINDOW_IDENTITY_MISSING")

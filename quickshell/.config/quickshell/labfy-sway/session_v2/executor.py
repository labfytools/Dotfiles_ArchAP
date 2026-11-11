"""Transaction de restauration fail-safe, sans promesse de rollback ACID.

Les applications sont conservées après erreur. Seul le helper possédé peut être
supprimé. La vérification de l'arbre n'est jamais remplacée par la cardinalité.
"""
import json
import os
import time
import uuid
from pathlib import Path
from .errors import Failure, Deferred, require
from .schema import validate, PROVIDER
from .storage import lock, private_dir
from .ipc import location, workspace, walk, surface_identity
from .applications import launch_count, launch
from .anchors import Anchors
from .guard import Guard
from .observability import Attempt
from .startup import record_deferred
from .slots import assign
from .layout import compile_placements
from .recovery import Recovery, RecordedSway, resume_pending, process_start, focus_proof, placement, observe, recovery_status, scratchpad_state


def process_owner(pid):
    require(type(pid) is int and pid > 0, "APPLICATION_OWNER_INVALID")
    try: return Path(f"/proc/{pid}").stat().st_uid
    except OSError: raise Failure("TARGET_IDENTITY_CHANGED") from None



def staging_order(tree, nodes):
    """Keep a disappearing focused branch until its workspace can become empty.

    Sway's IPC focus lists expose sibling order, not the global cross-depth
    inactive stack. Removing a focused leaf can therefore choose an internal
    ancestor or a surviving view with the same public tree. Avoid that unknown
    transition; never infer a replacement focus or loosen Recovery's checks.
    """
    nodes = list(nodes)
    selected = next((n for n in walk(tree) if n.get("focused")), None)
    if not selected or selected.get("type") == "workspace":
        return nodes
    descendants = {n["id"] for n in walk(selected) if n.get("app_id") or n.get("window")}
    staged = {n["id"] for n in nodes}
    if descendants and descendants.issubset(staged):
        where = location(tree, selected["id"])
        source = workspace(tree, where[0]) if where else None
        require(source is not None, "RESTORE_FOCUS_STAGING_UNPROVEN")
        remaining = {n["id"] for n in walk(source) if n.get("app_id") or n.get("window")} - staged
        # This includes foreign clients and shown scratchpads outside the focused
        # branch. Hidden scratchpads on __i3_scratch do not occupy this workspace.
        require(not remaining, "RESTORE_FOCUS_STAGING_UNPROVEN")
    # If a non-staged descendant remains, the focused internal node survives.
    # Moving its selected leaves last still preserves that exact focus identity.
    return ([n for n in nodes if n["id"] not in descendants] +
            [n for n in nodes if n["id"] in descendants])

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
        members = [n for n in nodes if surface_identity(n) in specs[a["application_id"]].app_ids]
        launch_count(a, len(members))
        admitted.update(n["id"] for n in members)
    tree = sway.tree()
    for w in data["workspaces"]:
        ws = workspace(tree, w["workspace"])
        if ws:
            require(all(n["id"] in admitted for n in walk(ws) if n.get("app_id") or n.get("window")), "WORKSPACE_OCCUPIED")
    # Refuse an unprovable focused-source transition before durable journals.
    staging_order(tree, [n for n in walk(tree) if (n.get("app_id") or n.get("window")) and
                         n["id"] in admitted and scratchpad_state(n, location(tree, n["id"])[0]) == "none"])
    return specs


class Executor:
    def __init__(self, sway, catalog, provider, runtime, anchor_binary, env=None, progress=None, process_identity=process_start):
        self.sway, self.catalog, self.provider = sway, catalog, provider
        self.runtime = private_dir(runtime)
        self.binary, self.env = anchor_binary, env
        self.progress = progress or (lambda *_: None)
        self.process_identity = process_identity

    def apply(self, data, execute=False, timeout=30):
        require(execute is True, "EXECUTE_REQUIRED")
        require(type(timeout) in (int, float) and 0 < timeout <= 60, "TIMEOUT_INVALID")
        with lock(private_dir(self.runtime / "session-v2")) as lock_fd:
            # Avant recovery aussi : une reprise peut elle-même muter l'arbre.
            record_deferred(self.runtime, self.sway.session)
            try:
                # Une intention active/ambiguë exige une reprise explicite ;
                # apply ne déplace jamais un ancien lot avant le prewarm.
                require(recovery_status(self.runtime)["status"] in ("idle", "complete", "recovered"), "RECOVERY_REQUIRED")
                receipt = resume_pending(self.sway, self.runtime, self.process_identity)
                require(not receipt or receipt["status"] != "RECOVERY_REQUIRED", "RECOVERY_REQUIRED")
                try:
                    proof, prepared = self._prewarm(data, timeout)
                    self._admit_providers(data, proof, prepared, min(timeout, 6))
                except Failure as exc:
                    if exc.code in ("APPLICATION_LAUNCH_FAILED", "APPLICATION_WINDOWS_INCOMPLETE", "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE",
                                    "RESTORE_FOCUS_STAGING_UNPROVEN"):
                        raise Deferred(exc.code) from None
                    raise
                return self._apply(data, timeout, lock_fd, proof, prepared)
            except Failure as exc:
                if isinstance(exc, Deferred) or exc.code in ("RESTORE_FOCUS_UNAVAILABLE", "RESTORE_FOCUS_UNSTABLE"):
                    record_deferred(self.runtime, self.sway.session, exc.code)
                raise

    def _admit_providers(self, data, proof, prepared, timeout):
        """Prove the complete Firefox identity set before any layout mutation.

        An absent publisher is deferred. A missing saved UUID remains an exact
        identity failure. External waits cannot silently replace the admitted
        window batch or its focus proof; later transaction checks still apply.
        """
        applications = [a for a in data["applications"] if a["identity_provider"] == PROVIDER]
        if not applications: return
        specs = preflight(data, self.sway, self.catalog, self.provider)
        for app in applications:
            members = [n for n in self.sway.windows()
                       if surface_identity(n) in specs[app["application_id"]].app_ids]
            expected = {s["identity_evidence"]["id"] for s in data["window_slots"]
                        if s["application_id"] == app["application_id"] and s["identity_requirement"] == "exact"}
            mapping = (self.provider.resolve(expected, members, timeout=timeout) if expected
                       else self.provider.capture(members, timeout=timeout))
            require(expected.issubset(mapping), "EXACT_WINDOW_IDENTITY_MISSING")
            require(set(mapping.values()) == {n["id"] for n in members}, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")
            require(self.sway.session == proof[0], "SWAY_SESSION_CHANGED")
            self._check_prepared(prepared, self._observe_prepared())
            preflight(data, self.sway, self.catalog, self.provider)
            require(focus_proof(self.sway) == proof, "RESTORE_FOCUS_UNSTABLE")

    def _observe_prepared(self, exclude=lambda node: False):
        """Identités runtime volatiles ; aucune attribution causale du focus.

        CONTRACT : seul le propriétaire local est admissible, avec PID/starttime
        relus. Les observations ne sont ni un journal ni une autorité IPC.
        """
        tree = self.sway.tree()
        nodes = [n for n in walk(tree) if (n.get("app_id") or n.get("window")) and not exclude(n)]
        require(len(nodes) <= 512, "RECOVERY_WINDOW_LIMIT")
        states = {}
        for node in nodes:
            require(process_owner(node.get("pid")) == os.getuid(), "APPLICATION_OWNER_INVALID")
            try: states[node["id"]] = observe(tree, node, self.process_identity)
            except OSError: raise Failure("TARGET_IDENTITY_CHANGED") from None
        return states

    def _settle_fresh_chatgpt(self, baseline, spec, session, allowed, timeout,
                              minimum_age=12.0, stable_for=2.0):
        """Wait for a newly launched ChatGPT XWayland window to stop remapping.

        This is PRE-TRANSACTION only. A freshly spawned ChatGPT process may
        replace its first X11 window/con_id several seconds after mapping.
        Never pin that first window as a durable Recovery origin. Pre-existing
        clients remain immutable; only the newly launched application's
        pre-admission identity may change. There is no retry after admission.
        """
        started = time.monotonic()
        deadline = started + timeout
        last, stable_since = None, None
        while True:
            now = time.monotonic()
            require(now < deadline, "APPLICATION_WINDOWS_INCOMPLETE")
            require(self.sway.session == session, "SWAY_SESSION_CHANGED")
            current = self._observe_prepared()
            self._check_prepared(baseline, current, exact=False)
            require(all(s["app_id"] in allowed for i, s in current.items() if i not in baseline),
                    "APPLICATION_MEMBERSHIP_CHANGED")
            candidates = [s for s in current.values() if s["app_id"] in spec.app_ids]
            signature = None
            if len(candidates) == 1:
                s = candidates[0]
                signature = (s["con_id"], s["pid"], s["starttime"], s["app_id"], placement(s))
            if signature != last:
                last, stable_since = signature, now if signature is not None else None
            if (signature is not None and now - started >= minimum_age
                    and stable_since is not None and now - stable_since >= stable_for):
                return current
            time.sleep(.05)

    def _prewarm(self, data, timeout):
        """PHASE 0 sous le verrou V2, avant Recovery/Attempt et tout IPC mutant.

        WHY : les mappings naturels peuvent prendre le focus ; ils doivent tous
        précéder sa preuve, jamais réinitialiser une preuve dans Recovery.
        CONTRACT : catalogue seulement, aucune fermeture, aucun déplacement.
        INVARIANT : un retry recompte les fenêtres vivantes ; un échec conserve
        les lancements et les journaux antérieurs. Aucun PID lancé ne confère
        d'autorité sur le focus ni sur une future réadmission.
        """
        session = self.sway.session
        specs = preflight(data, self.sway, self.catalog, self.provider)
        initial = self._observe_prepared()
        observed = initial
        all_ids = {identity for spec in specs.values() for identity in spec.app_ids}
        end = time.monotonic() + timeout
        # Un autostart absent ne doit jamais conduire au staging du lot partiel.
        for app in data["applications"]:
            if app["strategy"] == "managed-autostart":
                require(sum(s["app_id"] in specs[app["application_id"]].app_ids for s in initial.values()) == app["expected_windows"],
                        "APPLICATION_WINDOWS_INCOMPLETE")
        for app in data["applications"]:
            preflight(data, self.sway, self.catalog, self.provider)
            current = self._observe_prepared()
            self._check_prepared(observed, current, exact=False)
            observed = current
            require(self.sway.session == session, "SWAY_SESSION_CHANGED")
            require(all(s["app_id"] in all_ids for i, s in current.items() if i not in initial), "APPLICATION_MEMBERSHIP_CHANGED")
            spec = specs[app["application_id"]]
            count = sum(s["app_id"] in spec.app_ids for s in current.values())
            # Une instance déjà présente (y compris après échec partiel) ne
            # donne jamais lieu à une nouvelle ouverture au retry.
            missing = launch_count(app, count) if count == 0 else 0
            if missing:
                require(time.monotonic() < end, "APPLICATION_WINDOWS_INCOMPLETE")
                try: children = launch(spec, missing, self.env)
                except OSError: raise Failure("APPLICATION_LAUNCH_FAILED") from None
                # ChatGPT's freshly launched X11 shell may replace its first
                # window ~7s after startup. Wait before observing a durable
                # origin; an existing window never gets this exception.
                if spec.application_id == "chatgpt" and children:
                    observed = self._settle_fresh_chatgpt(observed, spec, session,
                                    all_ids, max(.001, end - time.monotonic()))
        while True:
            require(self.sway.session == session, "SWAY_SESSION_CHANGED")
            current = self._observe_prepared()
            self._check_prepared(observed, current, exact=False)
            observed = current
            require(all(s["app_id"] in all_ids for i, s in current.items() if i not in initial), "APPLICATION_MEMBERSHIP_CHANGED")
            counts = [sum(s["app_id"] in specs[a["application_id"]].app_ids for s in current.values()) for a in data["applications"]]
            require(all(n <= a["expected_windows"] for a, n in zip(data["applications"], counts)), "UNEXPECTED_EXTRA_WINDOW")
            if all(n == a["expected_windows"] for a, n in zip(data["applications"], counts)): break
            require(time.monotonic() < end, "APPLICATION_WINDOWS_INCOMPLETE")
            time.sleep(.025)
        proof = focus_proof(self.sway)
        preflight(data, self.sway, self.catalog, self.provider)
        self._check_prepared(current, self._observe_prepared())
        require(proof[0] == session and focus_proof(self.sway) == proof, "RESTORE_FOCUS_UNSTABLE")
        return proof, current

    @staticmethod
    def _check_prepared(before, after, exact=True):
        require((set(before) == set(after)) if exact else set(before).issubset(after), "APPLICATION_MEMBERSHIP_CHANGED")
        # Insertion naturelle : le chemin peut changer, jamais identité,
        # workspace, output ou état d'une fenêtre déjà observée.
        require(all(placement(s) == placement(after[i]) for i, s in before.items()), "TARGET_OBSERVATION_CHANGED")
        def order(states):
            return [s["con_id"] for s in sorted(states, key=lambda s: (s["workspace"], s["path"], s["con_id"])) if not s["floating"]]
        require(order(before.values()) == order(after[i] for i in before), "TARGET_OBSERVATION_CHANGED")

    def _apply(self, data, timeout, lock_fd, proof, prepared):
        validate(data)
        tx = uuid.uuid4().hex
        attempt = Attempt(self.runtime / "session-v2-restore-attempt.json", tx, data, publish=False)
        anchors, guard, recovery = None, None, None
        raw_sway = self.sway
        succeeded = False
        mapping = {}
        stage = "labfy-v2-stage-" + tx
        try:
            specs = preflight(data, self.sway, self.catalog, self.provider)
            self._check_prepared(prepared, self._observe_prepared())
            recovery = Recovery(raw_sway, self.runtime, tx, stage, self.process_identity, proof=proof)
            # WHY : la dernière preuve Sway peut encore refuser après preflight.
            # CONTRACT : aucun journal de tentative sur ce refus ; Recovery
            # vérifie aussi la preuve avant sa première publication durable.
            attempt.publish()
            all_ids = {a for s in specs.values() for a in s.app_ids}
            recovery.baseline(all_ids)
            self.sway = RecordedSway(raw_sway, recovery)
            attempt.update(phase="guard")
            anchors = Anchors(self.sway, data, tx, self.binary, self.env)
            recovery.anchor_owned = anchors.owned
            guard = Guard(self.sway, anchors, self.runtime, attempt.path, lock_fd)
            attempt.update(helpers_suspended=guard.ready["helpers_suspended"])
            # WHY : Guard/Anchors peuvent attendre pendant qu'un client remplace
            # une surface. CONTRACT : le lot phase0 est la seule autorité ; ni
            # app_id ni cardinalité ne permettent une nouvelle admission.
            # INVARIANT : tout le lot est revérifié avant le premier move, puis
            # avant chaque staging ; aucune relance n'est permise ici.
            current = self._observe_prepared()
            self._check_prepared(prepared, current)
            # WHY : des parents unaires peuvent décaler les chemins pendant
            # Guard sans changer le lot validé. CONTRACT : admettre l'observation
            # courante déjà comparée, jamais les chemins périmés de phase0.
            # INVARIANT : Recovery relit strictement cette observation ; ni
            # identité, placement, ordre ni preuve de focus ne sont élargis.
            prepared = current
            initial_nodes = {n["id"]: n for n in self.sway.windows()}
            require(set(initial_nodes) == set(prepared), "APPLICATION_MEMBERSHIP_CHANGED")
            targets = {i: initial_nodes[i] for i, state in prepared.items() if state["app_id"] in all_ids}
            for identity, node in targets.items():
                recovery.admit(node, prepared[identity])
            def check_batch():
                current = self._observe_prepared(anchors.owned)
                expected = dict(prepared)
                expected.update({e["origin"]["con_id"]: e["expected"] for e in recovery.data["windows"]})
                # Les chemins se compactent lors de nos déplacements ; les
                # placements non déplacés et toutes les identités restent fixes.
                require(set(current) == set(expected), "APPLICATION_MEMBERSHIP_CHANGED")
                require(all(placement(state) == placement(current[i]) for i, state in expected.items()),
                        "TARGET_OBSERVATION_CHANGED")
            def stage_node(n):
                check_batch()
                require(n["id"] in targets, "TARGET_IDENTITY_CHANGED")
                recovery.admit(n)
                self.sway.command(f'[con_id={n["id"]}] move container to workspace ' + json.dumps(stage))
            # Check the whole captured batch before interpreting focus admission:
            # a newly mapped client is a membership change, not a staging deferral.
            check_batch()
            # Recheck after Guard, using the same exact admitted batch.
            # Both hidden and shown scratchpads keep their existing treatment.
            staged = [n for n in targets.values() if prepared[n["id"]]["scratchpad"] == "none"]
            for n in staging_order(self.sway.tree(), staged):
                stage_node(n)
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
            start = time.monotonic()
            for app in data["applications"]:
                spec = specs[app["application_id"]]
                count = sum(surface_identity(n) in spec.app_ids for n in self.sway.windows())
                missing = launch_count(app, count)
                require(missing == 0 and count == app["expected_windows"], "APPLICATION_WINDOWS_INCOMPLETE")
                # PHASE 0 possède les lancements ; aucun nouveau mapping attendu
                # sous Recovery, même si une fenêtre disparaît entre les phases.

            end = time.monotonic() + timeout
            groups = {}
            while True:
                nodes = self.sway.windows()
                groups = {a["application_id"]: [n for n in nodes if surface_identity(n) in specs[a["application_id"]].app_ids] for a in data["applications"]}
                require(all(len(groups[a["application_id"]]) <= a["expected_windows"] for a in data["applications"]), "UNEXPECTED_EXTRA_WINDOW")
                if all(len(groups[a["application_id"]]) == a["expected_windows"] for a in data["applications"]): break
                require(time.monotonic() < end, "APPLICATION_WINDOWS_INCOMPLETE")
                time.sleep(.025)
            attempt.data["timings_ms"]["application_wait"] = (time.monotonic() - start) * 1000
            # WHY : le provider peut attendre plusieurs secondes, pendant
            # lesquelles PID/starttime, emplacement ou membres peuvent changer.
            # CONTRACT : épingler avant cet appel puis contrôler avant admission.
            # INVARIANT : ces observations ne donnent aucune propriété du focus
            # ni preuve de lancement ; toute divergence de focus reste refusée.
            captured = {n["id"]: n for group in groups.values() for n in group}
            pinned = {identity: recovery.pin(n) for identity, n in captured.items()}
            attempt.update(phase="resolve", applications_observed=len(groups))
            for app in data["applications"]:
                members = [s for s in data["window_slots"] if s["application_id"] == app["application_id"]]
                identity = None
                if app["identity_provider"] == PROVIDER:
                    expected = [s["identity_evidence"]["id"] for s in members if s["identity_requirement"] == "exact"]
                    identity = self.provider.resolve(expected, groups[app["application_id"]]) if expected else self.provider.capture(groups[app["application_id"]])
                    attempt.data["providers"] = [PROVIDER]
                    attempt.data["identity_resolutions"] = [{"uuid": k, "con_id": v} for k, v in identity.items()]
                mapping.update(assign(members, groups[app["application_id"]], identity, pinned))
            # CONTRACT : le provider ne peut introduire une admission hors du
            # lot phase0, même si un remplacement conserve la cardinalité.
            check_batch()
            require(set(captured) == set(targets), "APPLICATION_MEMBERSHIP_CHANGED")
            live_ids = {n["id"] for n in self.sway.windows() if surface_identity(n) in all_ids}
            require(live_ids == set(captured), "APPLICATION_MEMBERSHIP_CHANGED")
            # Un intrus hors catalogue n'est pas rendu admissible par son absence
            # des groupes applicatifs. Les seules cartes temporaires autorisées
            # appartiennent au helper d'ancres vérifié.
            expected_members = set(captured) | {n["con_id"] for n in recovery.data["foreign"]}
            require({n["id"] for n in self.sway.windows() if not anchors.owned(n)} == expected_members,
                    "APPLICATION_MEMBERSHIP_CHANGED")
            # Valider le lot entier avant les déplacements post-provider ; les
            # clients préexistants sont déjà au stage. Aucun contrôle du dernier
            # membre seulement après les mutations des précédents.
            for n in captured.values():
                recovery.admit(n, pinned[n["id"]])
            for n in captured.values():
                if recovery.snapshot(n["id"])["scratchpad"] != "none": continue
                if location(self.sway.tree(), n["id"])[0] != stage: stage_node(n)
                if n.get("type") == "floating_con" or n.get("floating") in ("user_on", "auto_on"):
                    self.sway.command(f'[con_id={n["id"]}] floating disable')
            start = time.monotonic()
            for slot in data["window_slots"]:
                if slot["state"]["floating"]: continue
                target = captured[mapping[slot["slot_id"]]]
                require(recovery.snapshot(target["id"])["scratchpad"] == "none", "SCRATCHPAD_ASSIGNMENT_UNPROVEN")
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
            # WHY : quitter le helper après SIGCONT ajoute une transition
            # Wayland pendant la validation finale. CONTRACT : finir sa vie
            # possédée sous suspension, contrôler le focus avant de le choisir.
            # INVARIANT : aucune divergence ne donne droit à refocaliser.
            recovery.boundary("before-guard-prepare")
            guard.prepare()
            recovery.boundary("after-guard-prepare")
            # WHY : restaurer le checkpoint ne possède pas le focus d'un client
            # tiers déjà actif. CONTRACT : son identité/emplacement de baseline
            # reste inchangé ; le focus du snapshot ne remplace que celui du lot.
            origin_focus = recovery.data["focus_origin"]["con_id"]
            foreign_focus = next((n for n in recovery.data["foreign"] if n["con_id"] == origin_focus), None)
            target_focus = mapping[data["focus"]] if data["focus"] else None
            if foreign_focus is not None:
                require(placement(recovery.snapshot(origin_focus)) == placement(foreign_focus), "FOREIGN_WINDOW_CHANGED")
                target_focus = origin_focus
            if target_focus is None and origin_focus is not None and data.get("focus_workspace") is None:
                # focus=null préserve la feuille réellement prouvée après mapping.
                # L'identité complète reste celle de Recovery, jamais celle d'un
                # app_id ou de la pile de focus d'un split arbitraire.
                origin = next((e["origin"] for e in recovery.data["windows"] if e["origin"]["con_id"] == origin_focus), None)
                current = recovery.snapshot(origin_focus)
                require(origin and current and all(current[k] == origin[k] for k in ("con_id", "app_id", "pid", "starttime")),
                        "RECOVERY_FOCUS_IDENTITY_CHANGED")
                target_focus = origin_focus
            if target_focus is not None:
                require(recovery.snapshot(target_focus)["scratchpad"] != "hidden", "RESTORE_FOCUS_UNAVAILABLE")
                self.sway.command(f'[con_id={target_focus}] focus')
            else:
                origin_workspace = data.get("focus_workspace") or recovery.data["focus_origin"]["workspace"]
                require((origin_focus is None or data.get("focus_workspace")) and origin_workspace and origin_workspace != stage, "RESTORE_FOCUS_UNAVAILABLE")
                self.sway.command("workspace " + json.dumps(origin_workspace))
            final_focus = recovery.data["focus_expected"]
            require(final_focus["workspace"] != stage, "FINAL_FOCUS_IN_STAGE")
            recovery.boundary("before-helper-resume")
            answer = guard.resume()
            attempt.update(helpers_resumed=answer["helpers_resumed"], phase="final-verification")
            recovery.boundary("after-helper-resume")
            self.progress("after-resume", len(mapping))
            self._verify(data, mapping, specs, anchors)
            recovery.check_command_focus(self.sway.tree(), final_focus, "final-verification")
            recovery.boundary("before-guard-finish")
            guard.finish()
            guard = None
            recovery.boundary("after-guard-finish")
            self._verify(data, mapping, specs, anchors)
            recovery.complete(lambda tree: self._verify_structure(data, mapping, specs, anchors, tree))
            attempt.update(final_focus_verified=True, status="success", reason="SUCCESS", phase="complete")
            succeeded = True
            return attempt.data
        except Exception as exc:
            code = exc.code if isinstance(exc, Failure) else "RESTORE_INTERNAL_ERROR"
            if recovery is not None:
                attempt.update(status="failed", reason=code, phase="cleanup-error")
            raise Failure(code) from None
        finally:
            if guard is not None:
                try:
                    answer = guard.finish()
                    attempt.update(helpers_resumed=answer["helpers_resumed"], anchors_cleaned=attempt.data["anchors_cleaned"] + answer["anchors_cleaned"])
                except Exception:
                    # WHY : le premier échec explique la transaction ; une erreur
                    # secondaire de cleanup ne doit jamais le masquer.
                    if attempt.data["reason"] in ("NONE", "SUCCESS"):
                        attempt.update(status="failed", reason="GUARD_RECOVERY_FAILED")
            if anchors is not None:
                try: anchors.close()
                except Exception:
                    if attempt.data["reason"] in ("NONE", "SUCCESS"):
                        attempt.update(status="failed", reason="ANCHOR_CLEANUP_FAILED")
            self.sway = raw_sway
            if recovery is not None and not succeeded:
                try: Recovery(raw_sway, self.runtime, start=self.process_identity).recover()
                except Exception:
                    # Le journal durable subsiste ; le prochain apply refuse ou
                    # reprend sous le même lock, sans nouvelle restauration.
                    pass

    def _floating(self, data, mapping, captured):
        slots = {s["slot_id"]: s for s in data["window_slots"]}
        for placement_op in compile_placements(data):
            s = slots[placement_op["slot_id"]]
            target = mapping[s["slot_id"]]
            n = next((n for n in self.sway.windows() if n["id"] == target), None)
            require(n and n.get("pid") == captured[target].get("pid"), "TARGET_IDENTITY_CHANGED")
            scratch = s["state"]["scratchpad"]
            current = self.sway.recovery.snapshot(target)
            if scratch in ("hidden", "shown"):
                prefix = f'[con_id={target}] '
                if not current["floating"]: self.sway.command(prefix + "floating enable")
                if current["scratchpad"] != "hidden": self.sway.command(prefix + "move scratchpad")
                if scratch == "shown":
                    self.sway.command("workspace " + json.dumps(s["workspace"]))
                    output = next(w["output"] for w in data["workspaces"] if w["workspace"] == s["workspace"])
                    self.sway.command("move workspace to output " + json.dumps(output))
                    self.sway.command(prefix + "scratchpad show")
                # Hidden geometry can be set without showing the leaf. IPC rect
                # is the contract, not the transform of a future user show.
                g = s["state"]["geometry"]
                self.sway.command(prefix + f'resize set width {g["width"]} px height {g["height"]} px')
                self.sway.command(prefix + f'move absolute position {g["x"]} px {g["y"]} px')
                continue
            require(current["scratchpad"] == "none", "SCRATCHPAD_ASSIGNMENT_UNPROVEN")
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

        # V2 can capture an empty focused workspace alongside hidden leaves.
        # WHY : after launch/staging Sway may destroy it. CONTRACT : recreate
        # only that explicitly persisted workspace/output, never __i3_scratch.
        for w in data["workspaces"]:
            if w["root"] is None and not any(s["workspace"] == w["workspace"] for s in data["window_slots"]):
                self.sway.command("workspace " + json.dumps(w["workspace"]))
                self.sway.command("move workspace to output " + json.dumps(w["output"]))

    def _verify(self, data, mapping, specs, anchors):
        # WHY : capture est une frontière externe potentiellement lente.
        # CONTRACT : UUID exact conservé, puis nouvelle observation complète ;
        # aucun contrôle ancien ne couvre les mutations pendant le provider.
        nodes = self.sway.windows()
        for a in data["applications"]:
            if a["identity_provider"] != PROVIDER: continue
            members = [n for n in nodes if surface_identity(n) in specs[a["application_id"]].app_ids]
            identities = self.provider.capture(members)
            for s in data["window_slots"]:
                if s["application_id"] == a["application_id"] and s["identity_requirement"] == "exact":
                    require(identities.get(s["identity_evidence"]["id"]) == mapping[s["slot_id"]], "EXACT_WINDOW_IDENTITY_MISSING")

        self._verify_structure(data, mapping, specs, anchors, self.sway.tree())

    def _verify_structure(self, data, mapping, specs, anchors, tree):
        """Dernière observation structurelle, sans appel provider ni IPC mutant.

        INVARIANT : ce contrôle ne prétend pas empêcher un changement après
        l'observation. Le focus verrouillé reste celui de Recovery.
        """
        recovery = self.sway.recovery
        tree = recovery.validate_final(tree)
        anchors.verify(mapping, tree)
        expected_members = set(mapping.values()) | {n["con_id"] for n in recovery.data["foreign"]}
        require({n["id"] for n in walk(tree) if (n.get("app_id") or n.get("window")) and not anchors.owned(n)} == expected_members,
                "APPLICATION_MEMBERSHIP_CHANGED")
        output_for = {w["name"]: o["name"] for o in tree.get("nodes", [])
                      for w in walk(o) if w.get("type") == "workspace"}
        require(all(output_for.get(w["workspace"]) == w["output"] for w in data["workspaces"]), "FINAL_OUTPUT_MISMATCH")
        nodes = [n for n in walk(tree) if n.get("app_id") or n.get("window")]
        for a in data["applications"]:
            observed = sum(surface_identity(n) in specs[a["application_id"]].app_ids for n in nodes)
            require(observed >= a["expected_windows"], "APPLICATION_WINDOWS_INCOMPLETE")
            require(observed <= a["expected_windows"], "UNEXPECTED_EXTRA_WINDOW")
        for s in data["window_slots"]:
            n = next((n for n in nodes if n["id"] == mapping[s["slot_id"]]), None)
            require(n and surface_identity(n) in specs[s["application_id"]].app_ids, "TARGET_IDENTITY_CHANGED")
            scratch = s["state"]["scratchpad"]
            require(scratchpad_state(n, location(tree, n["id"])[0]) == ("none" if scratch is False else scratch), "FINAL_SCRATCHPAD_MISMATCH")
            if s["state"]["floating"]:
                require(location(tree, n["id"])[0] == ("__i3_scratch" if scratch == "hidden" else s["workspace"]) and n.get("floating") in ("auto_on", "user_on") and
                        all(n["rect"][k] == v for k, v in s["state"]["geometry"].items()), "FLOATING_GEOMETRY_MISMATCH")
        return tree

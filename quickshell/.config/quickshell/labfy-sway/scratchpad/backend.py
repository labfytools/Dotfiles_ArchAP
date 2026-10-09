#!/usr/bin/env python3
"""Vue et commandes ponctuelles du scratchpad natif SwayFX."""

import argparse
import json
import re
import subprocess
import sys


class DrawerError(Exception):
    pass


def sway(kind):
    result = subprocess.run(["swaymsg", "-r", "-t", kind], capture_output=True,
                            text=True, timeout=5, check=True)
    return json.loads(result.stdout)


def command(value):
    # CONTRACT: argv évite le shell, mais Sway possède sa propre grammaire.
    # Seuls des con_id numériques et des noms de workspace cités y entrent.
    result = subprocess.run(["swaymsg", "-r", value], capture_output=True,
                            text=True, timeout=5, check=True)
    replies = json.loads(result.stdout)
    if not isinstance(replies, list) or not replies or not all(
            item.get("success") is True for item in replies):
        raise DrawerError("Commande Sway refusée : " + str(replies))


def safe_command(value):
    # CONTRACT: une demande Polkit arrivée entre le clic et l'IPC empêche
    # encore la transition ; une lecture indisponible échoue sans déplacement.
    try:
        result = subprocess.run(["qs", "-c", "labfy-sway", "ipc", "call",
                                 "polkitUi", "state"], capture_output=True,
                                text=True, timeout=3, check=True)
        state = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise DrawerError("État Polkit indisponible") from error
    if state.get("active") or state.get("dialog"):
        raise DrawerError("Authentification en cours")
    command(value)


def quoted_workspace(name):
    if (not isinstance(name, str) or not name or len(name) > 256
            or any(ord(char) < 32 or char == "$" for char in name)):
        raise DrawerError("Nom de workspace invalide")
    # Sway garde littéralement un backslash devant un guillemet dans l'IPC.
    # Choisir l'autre délimiteur conserve le nom exact et protège , et ;.
    if '"' not in name:
        return '"' + name + '"'
    if "'" not in name:
        return "'" + name + "'"
    raise DrawerError("Nom de workspace contenant les deux types de guillemets non pris en charge")


def walk(node, workspace=None, scratch=False, parent=None):
    if node.get("type") == "workspace":
        workspace = node.get("name")
    scratch = scratch or node.get("scratchpad_state") not in (None, "none")
    yield node, workspace, scratch, parent
    for child in (node.get("nodes") or []) + (node.get("floating_nodes") or []):
        yield from walk(child, workspace, scratch, node)


def application_count(root):
    return sum(bool(node.get("app_id") or (node.get("window_properties") or {}).get("class"))
               for node, _, _, _ in walk(root)
               if node.get("type") in ("con", "floating_con"))


def members(tree):
    result = []
    def visit(node, workspace=None, scratch_root=None):
        if node.get("type") == "workspace":
            workspace = node.get("name")
        if scratch_root is None and node.get("scratchpad_state") not in (None, "none"):
            scratch_root = node
        if node.get("type") not in ("con", "floating_con"):
            app = None
        else:
            app = node.get("app_id") or (node.get("window_properties") or {}).get("class")
        if app and scratch_root is not None:
            # Un groupe scratchpad est une seule unité de déplacement. L'UI le
            # signale et bloque les actions individuelles ambiguës.
            result.append({"id": node["id"], "app": app, "title": node.get("name") or app,
                           "workspace": workspace, "shown": workspace != "__i3_scratch",
                           "group": application_count(scratch_root) > 1,
                           "border": node.get("border")})
        for child in (node.get("nodes") or []) + (node.get("floating_nodes") or []):
            visit(child, workspace, scratch_root)

    visit(tree)
    return result


def target_workspace(output):
    workspaces = sway("get_workspaces")
    target = next((item for item in workspaces if item.get("output") == output
                   and item.get("visible") is True), None)
    if target is None:
        raise DrawerError("Aucun workspace visible sur cette sortie")
    return target["name"]


def valid_app(tree, con_id):
    found = next(((node, parent, workspace) for node, workspace, _, parent in walk(tree)
                  if node.get("id") == con_id), None)
    if found is None:
        raise DrawerError("La fenêtre a disparu")
    node, parent, workspace = found
    app = node.get("app_id") or (node.get("window_properties") or {}).get("class")
    if node.get("type") not in ("con", "floating_con") or not app:
        raise DrawerError("Ce conteneur n'est pas une fenêtre applicative")
    if (node.get("nodes") or node.get("floating_nodes")):
        raise DrawerError("Un groupe de fenêtres ne peut pas être rangé comme une seule fenêtre")
    # Sway remonte au conteneur flottant parent pour certaines commandes
    # ciblées. Refuser un parent multi-app avant de déplacer tout le groupe.
    if parent and parent.get("type") in ("con", "floating_con") and application_count(parent) > 1:
        raise DrawerError("Fenêtre dans un groupe : déplacement individuel indisponible")
    return node, parent, workspace


def operate(action, con_id, output):
    tree = sway("get_tree")
    node, parent, workspace = valid_app(tree, con_id)
    found = next((item for item in members(tree) if item["id"] == con_id), None)
    if action == "store":
        if found is None:
            safe_command(f"[con_id={con_id}] move scratchpad")
        elif found["group"]:
            raise DrawerError("Groupe scratchpad : action individuelle désactivée")
        elif found["shown"]:
            safe_command(f"[con_id={con_id}] move scratchpad")
    else:
        if found is None:
            raise DrawerError("Cette fenêtre n'appartient plus au tiroir")
        if found["group"]:
            raise DrawerError("Groupe scratchpad : action individuelle désactivée")
        destination = target_workspace(output)
        if action == "show":
            if found["shown"] and workspace == destination:
                safe_command(f"[con_id={con_id}] focus")
            else:
                safe_command("workspace " + quoted_workspace(destination))
                safe_command(f"[con_id={con_id}] scratchpad show")
                safe_command(f"[con_id={con_id}] focus")
        elif action == "hide":
            if found["shown"]:
                # scratchpad show sur un autre workspace déplace la fenêtre au
                # lieu de la masquer : move scratchpad est la transition directe.
                safe_command(f"[con_id={con_id}] move scratchpad")
        elif action == "release":
            safe_command(f"[con_id={con_id}] move container to workspace "
                    + quoted_workspace(destination))
            # Sway conserve scratchpad_state après un simple move. Son retrait
            # natif passe par floating disable ; réactiver ensuite le flottement
            # restitue la politique visible sans toucher au layout du workspace.
            safe_command(f"[con_id={con_id}] floating disable")
            safe_command(f"[con_id={con_id}] floating enable")
            safe_command(f"[con_id={con_id}] focus")
        else:
            raise DrawerError("Action inconnue")
    final_tree = sway("get_tree")
    after = next((item for item in members(final_tree) if item["id"] == con_id), None)
    if action == "store" and after is None or action == "release" and after is not None:
        raise DrawerError("L'état final du tiroir ne correspond pas à l'action")
    if action in ("show", "hide") and (after is None or after["shown"] != (action == "show")):
        raise DrawerError("La visibilité finale ne correspond pas à l'action")
    if action == "store" and (after is None or after["shown"]):
        raise DrawerError("La fenêtre n'est pas masquée dans le tiroir")
    if action == "show" and after["workspace"] != destination:
        raise DrawerError("La fenêtre n'est pas sur le workspace choisi")
    if action == "release":
        final_node, _, final_workspace = valid_app(final_tree, con_id)
        if final_workspace != destination or final_node.get("floating") not in ("user_on", "auto_on"):
            raise DrawerError("La fenêtre n'est pas flottante sur le workspace choisi")
    return {"ok": True, "member": after is not None, "shown": bool(after and after["shown"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "store", "show", "hide", "release"])
    parser.add_argument("con_id", nargs="?", type=int)
    parser.add_argument("output", nargs="?")
    args = parser.parse_args()
    if args.action == "list":
        tree = sway("get_tree")
        focused = next((node["id"] for node, _, _, _ in walk(tree)
                        if node.get("focused") is True), 0)
        print(json.dumps({"entries": members(tree), "focused": focused}, ensure_ascii=False))
        return
    if args.con_id is None or args.con_id <= 0 or (args.action != "store" and not args.output):
        raise DrawerError("Arguments invalides")
    print(json.dumps(operate(args.action, args.con_id, args.output)))


if __name__ == "__main__":
    try:
        main()
    except (DrawerError, subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        sys.exit(1)

"""Décision persistante par instance Sway, distincte du booléen de l'UI.

CONTRACT : restored exige le rapport final de la transaction reçue par l'UI.
Aucune décision ne ferme de fenêtre ni ne déclenche de restauration.
"""
from .errors import Failure, require
from .storage import private_dir, lock, read, atomic
from .observability import validate


def successful(report):
    validate(report)
    return (report['status'] == 'success' and report['final_tree_verified'] and report['final_focus_verified']
            and report['slots_expected'] == report['slots_filled']
            and report['applications_expected'] == report['applications_observed']
            and report['anchors_created'] == report['anchors_cleaned']
            and report['helpers_suspended'] == report['helpers_resumed'])


def acknowledge(runtime, session, choice, transaction_id=None):
    require(choice in ('new', 'restored'), 'STARTUP_CHOICE_INVALID')
    directory = private_dir(runtime / 'session-v2')
    marker = directory / 'startup.json'
    with lock(directory):
        if choice == 'restored':
            claimed = read(marker)
            report = read(runtime / 'session-v2-restore-attempt.json', validate)
            require(claimed.get('session') == session and transaction_id == report['transaction_id']
                    and successful(report), 'RESTORE_ACKNOWLEDGEMENT_FAILED')
        atomic(marker, {'session': session, 'choice': choice, 'transaction_id': transaction_id if choice == 'restored' else None})
    return {'status': 'acknowledged', 'choice': choice}


def record_deferred(runtime, session, reason=None):
    """Appelé sous le verrou de transaction déjà détenu par Executor.

    WHY : un redémarrage QML ne doit pas perdre le retry explicite DEFERRED.
    CONTRACT : seul le claim de cette session sans décision peut être annoté.
    INVARIANT : ce marqueur UI n'autorise aucun IPC ni aucune reprise automatique.
    """
    marker = runtime / "session-v2/startup.json"
    if not marker.exists(): return
    seen = read(marker)
    if seen.get("session") == session and "choice" not in seen:
        atomic(marker, {"session": session, "deferred": reason is not None, "deferred_reason": reason})


def status(runtime, session, last, execute=False):
    """Un claim sans décision reste visible après redémarrage de QuickShell.

    CONTRACT : un backend détenant le lock n'est jamais relancé par le chooser.
    Aucune reprise automatique : l'utilisateur reçoit état et annulation.
    """
    if last is None: return {"eligible": False, "claimed": False}
    directory = private_dir(runtime / "session-v2")
    marker = directory / "startup.json"
    def inspect():
        seen = read(marker) if marker.exists() else {}
        same = seen.get("session") == session
        eligible = last["metadata"]["sway_session"] != session and not (same and seen.get("choice") in ("new", "restored"))
        return seen, same, eligible
    in_progress = False
    try:
        with lock(directory):
            seen, same, eligible = inspect()
            if execute and eligible and not same: atomic(marker, {"session": session})
    except Failure as exc:
        if exc.code != "TRANSACTION_BUSY": raise
        seen, same, eligible = inspect()
        in_progress = True
    return {"eligible": eligible, "claimed": bool(eligible and (same or (execute and not in_progress))),
            "in_progress": in_progress, "deferred": bool(same and eligible and not in_progress and seen.get("deferred") is True),
            "deferred_reason": seen.get("deferred_reason") if same else None,
            "interrupted": bool(same and eligible and not in_progress),
            "windows": len(last["window_slots"]), "workspaces": len(last["workspaces"])}

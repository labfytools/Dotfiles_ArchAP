"""Décision persistante par instance Sway, distincte du booléen de l'UI.

CONTRACT : restored exige le rapport final de la transaction reçue par l'UI.
Aucune décision ne ferme de fenêtre ni ne déclenche de restauration.
"""
from .errors import require
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

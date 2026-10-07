import QtQuick

QtObject {
    id: gate

    required property var actions
    property string checkpointSuccessStatus: "success"
    property var pendingAction: null
    property var checkpointAction: null
    property bool busy: false
    property string errorMessage: ""

    signal confirmationRequested()
    signal checkpointRequested(string reason)
    signal commandRequested(var command)
    signal checkpointFailed()

    function actionFor(id) {
        return actions.find(item => item.id === id);
    }

    function requestAction(id) {
        const selected = actionFor(id);
        if (!selected || busy) return;
        if (id === "lock") {
            commandRequested(selected.command);
            return;
        }
        pendingAction = selected;
        confirmationRequested();
    }

    function confirmAction(id) {
        if (!pendingAction || pendingAction.id !== id || busy) return;
        if (!pendingAction.checkpointReason) {
            commandRequested(pendingAction.command);
            return;
        }
        // WHY: le popup peut perdre sa visibilité pendant le Process asynchrone.
        // CONTRACT: l'action confirmée reste l'autorité jusqu'au résultat du checkpoint.
        // INVARIANT: aucune commande destructive n'est émise avant un succès JSON exit 0.
        checkpointAction = pendingAction;
        errorMessage = "";
        busy = true;
        checkpointRequested(checkpointAction.checkpointReason);
    }

    function checkpointFinished(exitCode, exitStatus, stdoutText, stderrText) {
        if (!busy || !checkpointAction) return;
        let response = undefined;
        try { response = JSON.parse(stdoutText); } catch (_) {}
        const completedAction = checkpointAction;
        busy = false;
        checkpointAction = null;
        if (exitCode === 0 && exitStatus === 0 && response
                && response.status === checkpointSuccessStatus) {
            pendingAction = null;
            commandRequested(completedAction.command);
            return;
        }
        pendingAction = completedAction;
        errorMessage = stderrText.trim() || "Le backend de sauvegarde a échoué.";
        checkpointFailed();
    }

    function cancel() {
        if (busy) return;
        pendingAction = null;
        checkpointAction = null;
        errorMessage = "";
    }

    function quitWithoutCheckpoint() {
        if (!pendingAction || busy) return;
        const command = pendingAction.command;
        pendingAction = null;
        checkpointAction = null;
        commandRequested(command);
    }
}

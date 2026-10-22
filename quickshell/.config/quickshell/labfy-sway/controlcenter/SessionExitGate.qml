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
        // CONTRACT: backend reason is diagnostic data, never exit authority.
        // Keep the action gated until saved or an explicit human bypass.
        const reason = response && typeof response.reason === "string"
            && /^[A-Z][A-Z0-9_]{0,95}$/.test(response.reason) ? response.reason : "";
        const explanations = {
            CAPABILITY_UNSUPPORTED: "Un état de fenêtre n’est pas pris en charge par le backend installé (par exemple fullscreen ou scratchpad avec un ancien backend).",
            SNAPSHOT_CHANGED: "Les fenêtres ont changé pendant la capture. Réessayez une fois leur état stabilisé.",
            SNAPSHOT_FOCUS_AMBIGUOUS: "Sway ne fournit pas un focus unique pour cette capture.",
            FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE: "Le fournisseur d’identité Firefox nécessaire à la sauvegarde est indisponible.",
            RECOVERY_REQUIRED: "Une ancienne restauration exige une inspection humaine. Elle ne sera pas reprise automatiquement.",
            SCRATCHPAD_CONTAINER_UNSUPPORTED: "Ce scratchpad contient un groupe de fenêtres dont la restauration sûre n’est pas prise en charge."
        };
        errorMessage = reason ? reason + " — " + (explanations[reason] || "Le backend a refusé la sauvegarde. Conservez la session ouverte et examinez ce code.")
            : stderrText.trim() || "Le backend de sauvegarde a échoué sans code de diagnostic.";
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

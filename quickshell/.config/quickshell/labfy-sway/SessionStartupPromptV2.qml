import QtQuick
import Quickshell
import Quickshell.Wayland
import "controlcenter"
import "theme"
import "sessionui"
import "sessionui/Protocol.js" as Protocol

PanelWindow {
    id: popup
    required property var barWindow
    required property bool startupHost
    property bool interactionArmed: false
    property bool failed: false
    property bool restored: false
    property bool detailsVisible: false
    property bool attempted: false
    property bool startupChecked: false
    property bool releasing: false
    property bool inProgress: false
    property bool watchingBackend: false
    property bool retryAllowed: false
    property bool awaitingUserFocus: false
    property int releaseTicks: 0
    property int releaseClearTicks: 0
    property string failureMessage: "Impossible de restaurer complètement la session."
    property string technicalDetails: ""
    property int windowCount: 0
    property int workspaceCount: 0
    readonly property bool busy: SessionV2Service.busy || watchingBackend
    property bool unlockingRequested: false
    readonly property bool keyringReady: SessionV2Service.keyringReady
    function unlockRequested() {
        if (!interactionArmed || busy || SessionV2Service.keyringBusy || unlockingRequested) return;
        // CONTRACT: release exclusive keyboard before presenting the native
        // prompt. Keep New session clickable throughout the unlock operation.
        unlockingRequested = true;
        unlockRelease.start();
    }
    Timer {
        id: unlockRelease
        interval: 50; repeat: true
        onTriggered: {
            if (popup.focusable) return;
            stop(); popup.unlockingRequested = false;
            SessionV2Service.checkKeyring(true);
        }
    }
    Timer {
        interval: 2000; repeat: true
        running: popup.visible && SessionV2Service.keyringState === "KEYRING_UNLOCKING" && !popup.releasing && !popup.unlockingRequested
        onTriggered: SessionV2Service.checkKeyring(false)
    }
    function restoreRequested() {
        if (!keyringReady || !interactionArmed || busy || releasing || (attempted && !retryAllowed)) return;
        if (!SessionV2Service.prepareRestore(popup)) return;
        attempted = true;
        failed = false;
        retryAllowed = false;
        releasing = true;
        releaseTicks = 0;
        releaseClearTicks = 0;
        // WHY : visible=false seul ne vaut pas retrait de la backing window.
        // CONTRACT : deux observations QML après retrait, bornées à 1,5 s.
        // Le backend exige ensuite sa propre preuve Sway avant tout journal.
        visible = false;
        releasePoll.start();
    }
    function newSessionRequested() {
        if (interactionArmed && !busy) {
            unlockRelease.stop(); unlockingRequested = false;
            SessionV2Service.cancelKeyring();
            SessionV2Service.run("ack-new", "", "", popup);
        }
    }
    function releaseFailed() {
        releasePoll.stop();
        SessionV2Service.cancelRestore(popup);
        releasing = false;
        failed = true;
        retryAllowed = true;
        // Un retrait expiré ne doit pas recréer la capture clavier au retry.
        awaitingUserFocus = true;
        failureMessage = "Restauration différée : le dialogue n’a pas libéré sa surface. Réessayez ou choisissez Nouvelle session.";
        visible = true;
    }
    function fail(value) {
        inProgress = false;
        if (value && /^KEYRING_/.test(value.reason)) {
            // Admission failed before Executor: preserve the explicit retry
            // path without fabricating a restore attempt or clearing Recovery.
            attempted = false; failed = false; restored = false;
            visible = true; SessionV2Service.checkKeyring(false); return;
        }
        failed = true;
        restored = false;
        retryAllowed = !!value && value.status === "DEFERRED";
        // WHY : rouvrir une layer exclusive après DEFERRED recrée le focus nul.
        // CONTRACT : l'utilisateur active lui-même sa fenêtre/workspace puis
        // clique Réessayer ; ce panneau reste sans clavier même pendant le clic.
        // INVARIANT : aucune cible IPC inférée, aucun retry automatique ; le
        // backend doit encore prouver le focus après retrait de cette surface.
        awaitingUserFocus = retryAllowed;
        const prewarmDeferred = retryAllowed && (value.reason === "APPLICATION_LAUNCH_FAILED"
                                                   || value.reason === "APPLICATION_WINDOWS_INCOMPLETE");
        failureMessage = prewarmDeferred
            ? "Préparation incomplète. Les fenêtres ouvertes sont conservées, sans déplacement. Vérifiez les applications, puis cliquez Réessayer. Aucune application déjà présente ne sera relancée."
            : retryAllowed
            ? "Restauration différée : aucun focus stable n’est prouvé. Ce dialogue ne capte plus le clavier. Activez vous-même une fenêtre ou un espace avec vos raccourcis Sway, puis cliquez Réessayer. Sinon, choisissez Nouvelle session."
            : "Impossible de restaurer complètement la session. Consultez les détails ou choisissez Nouvelle session.";
        visible = true;
        // Détails provient uniquement de Restore Attempt V2, jamais d'un log.
        technicalDetails = Protocol.details(value);
        if (!retryAllowed) SessionV2Service.run("restore-status", "", "", popup);
    }
    Timer {
        id: releasePoll
        interval: 25
        repeat: true
        onTriggered: {
            popup.releaseTicks += 1;
            if (popup.visible || popup.focusable) { popup.releaseFailed(); return; }
            popup.releaseClearTicks = popup.backingWindowVisible ? 0 : popup.releaseClearTicks + 1;
            if (popup.releaseClearTicks >= 2) {
                stop();
                popup.releasing = false;
                if (SessionV2Service.startRestore(popup)) popup.inProgress = true;
                else popup.releaseFailed();
            } else if (popup.releaseTicks >= 60) popup.releaseFailed();
        }
    }
    Component.onDestruction: SessionV2Service.cancelRestore(popup)
    Timer {
        interval: 1000
        repeat: true
        running: popup.watchingBackend
        onTriggered: SessionV2Service.run("startup-status", "", "", popup)
    }
    Timer {
        interval: 350
        repeat: true
        running: popup.startupHost && !popup.startupChecked
        // Un owner recréé pendant un Process existant attend son terme ; le
        // premier refus busy ne doit pas perdre le seul chemin de diagnostic.
        onTriggered: {
            if (SessionV2Service.run("startup-status", "", "", popup)) popup.startupChecked = true;
        }
    }
    Timer { id: arm; interval: 750; onTriggered: popup.interactionArmed = popup.visible }
    Timer { id: closeSuccess; interval: 600; onTriggered: popup.visible = false }
    Connections {
        target: SessionV2Service
        function onCompleted(owner, kind, value, okay) {
            if (owner !== popup) return;
            if (kind === "startup-status") {
                if (!okay) {
                    popup.watchingBackend = false;
                    popup.fail(value);
                    return;
                }
                popup.watchingBackend = value.in_progress === true;
                popup.inProgress = popup.watchingBackend;
                popup.visible = value.eligible === true && value.claimed === true && !popup.watchingBackend;
                if (popup.visible && value.deferred === true) {
                    popup.attempted = true;
                    popup.fail({status: "DEFERRED", reason: value.deferred_reason});
                } else if (popup.visible && value.interrupted === true) {
                    popup.attempted = true;
                    popup.failed = true;
                    popup.failureMessage = "Une restauration précédente a été interrompue ou attend une décision. Consultez les détails ou choisissez Nouvelle session.";
                    SessionV2Service.run("restore-status", "", "", popup);
                }
                if (popup.visible) {
                    SessionV2Service.checkKeyring(false);
                    popup.windowCount = value.windows || 0;
                    popup.workspaceCount = value.workspaces || 0;
                }
            } else if (kind === "apply-last") {
                if (okay && Protocol.restoreSucceeded(value))
                    SessionV2Service.run("ack-restored", "", value.transaction_id, popup);
                else popup.fail(value);
            } else if (kind === "ack-restored") {
                if (okay && value.status === "acknowledged" && value.choice === "restored") {
                    popup.inProgress = false;
                    popup.restored = true;
                    popup.visible = true;
                    closeSuccess.start();
                } else popup.fail();
            } else if (kind === "ack-new") {
                if (okay && value.status === "acknowledged") popup.visible = false;
                else popup.fail(value);
            } else if (kind === "restore-status") {
                popup.technicalDetails = okay ? Protocol.details(value) : "Rapport de restauration indisponible.";
            }
        }
    }

    // Layer-shell, jamais un PopupWindow grabbing au nouveau login.
    screen: barWindow.screen
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0
    aboveWindows: true
    focusable: visible && !unlockingRequested && !SessionV2Service.keyringBusy && SessionV2Service.keyringState !== "KEYRING_UNLOCKING" && !awaitingUserFocus && !releasing && !inProgress && !restored
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "labfy-session-startup-v2"
    visible: false
    color: "transparent"
    onVisibleChanged: {
        if (startupHost) SessionV2Service.startupChooserVisible = visible;
        interactionArmed = false;
        if (visible) arm.restart(); else arm.stop();
    }
    PanelWindow {
        screen: popup.screen
        visible: popup.inProgress
        focusable: false
        exclusionMode: ExclusionMode.Ignore
        exclusiveZone: 0
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "labfy-session-progress-v2"
        anchors { top: true }
        implicitWidth: 340
        implicitHeight: 54
        color: Theme.popupBackground
        Text {
            anchors.centerIn: parent
            text: "Restauration de la session en cours…"
            color: Theme.foreground
        }
    }
    FocusScope {
        id: modal
        anchors.fill: parent
        focus: popup.visible
        // Aucun focus par défaut sur Restore. Les touches en transit n'agissent
        // pas, et Escape ne vaut jamais une demande de restauration.
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape || event.key === Qt.Key_Enter
                    || event.key === Qt.Key_Return || event.key === Qt.Key_Space) event.accepted = true;
        }
        Rectangle { anchors.fill: parent; color: Qt.rgba(0, 0, 0, 0.65) }
        MouseArea { anchors.fill: parent }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(460, Math.max(280, modal.width - 32))
            height: content.implicitHeight + 40
            color: Theme.popupBackground
            radius: 8
            border.color: Theme.lavender
            Column {
                id: content
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 }
                spacing: 14
                Text { text: "Session précédente"; color: Theme.foreground; font.pixelSize: 19; font.bold: true }
                Text {
                    width: parent.width
                    text: popup.failed ? popup.failureMessage
                        : popup.restored ? "Session restaurée"
                        : popup.busy && popup.attempted ? "Restauration en cours…"
                        : popup.keyringReady ? "Une session précédente est disponible."
                        : SessionV2Service.keyringState === "KEYRING_CANCELLED" ? "Déverrouillage annulé. Réessayez ou choisissez Nouvelle session."
                        : SessionV2Service.keyringState === "KEYRING_UNAVAILABLE" ? "Trousseau indisponible. Réessayez ou choisissez Nouvelle session. (" + SessionV2Service.keyringReason + ")"
                        : SessionV2Service.keyringState === "KEYRING_UNLOCKING" ? "Déverrouillage du trousseau en cours…"
                        : "Le trousseau doit être déverrouillé avant la restauration de votre session."
                    color: Theme.foreground
                    wrapMode: Text.Wrap
                }
                Text {
                    width: parent.width
                    visible: popup.detailsVisible
                    text: popup.technicalDetails
                    color: Theme.secondaryForeground
                    wrapMode: Text.Wrap
                }
                Row {
                    spacing: 10
                    visible: !popup.restored && (!popup.attempted || popup.failed)
                    ActionButton {
                        visible: popup.failed
                        label: "Détails"
                        enabled: !popup.busy
                        onClicked: popup.detailsVisible = !popup.detailsVisible
                    }
                    ActionButton {
                        label: "Nouvelle session"
                        enabled: popup.interactionArmed && !popup.busy
                        onClicked: popup.newSessionRequested()
                    }
                    ActionButton {
                        visible: !popup.keyringReady
                        label: "Déverrouiller le trousseau"
                        enabled: popup.interactionArmed && !popup.busy && !SessionV2Service.keyringBusy && !popup.unlockingRequested
                        onClicked: popup.unlockRequested()
                    }
                    ActionButton {
                        visible: popup.keyringReady && (!popup.failed || popup.retryAllowed)
                        label: popup.retryAllowed ? "Réessayer" : "Restaurer"
                        enabled: popup.keyringReady && popup.interactionArmed && !popup.busy && (!popup.attempted || popup.retryAllowed)
                        onClicked: popup.restoreRequested()
                    }
                }
            }
        }
    }
}

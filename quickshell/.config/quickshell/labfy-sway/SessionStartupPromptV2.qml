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
    property string technicalDetails: ""
    property int windowCount: 0
    property int workspaceCount: 0
    readonly property bool busy: SessionV2Service.busy
    function restoreRequested() {
        if (!interactionArmed || busy || attempted || failed) return;
        if (SessionV2Service.run("apply-last", "", "", popup)) attempted = true;
    }
    function newSessionRequested() {
        if (interactionArmed && !busy) SessionV2Service.run("ack-new", "", "", popup);
    }
    function fail() {
        failed = true;
        restored = false;
        // Détails provient uniquement de Restore Attempt V2, jamais d'un log.
        SessionV2Service.run("restore-status", "", "", popup);
    }
    Timer {
        interval: 350
        running: popup.startupHost
        onTriggered: SessionV2Service.run("startup-status", "", "", popup)
    }
    Timer { id: arm; interval: 750; onTriggered: popup.interactionArmed = popup.visible }
    Timer { id: closeSuccess; interval: 600; onTriggered: popup.visible = false }
    Connections {
        target: SessionV2Service
        function onCompleted(owner, kind, value, okay) {
            if (owner !== popup) return;
            if (kind === "startup-status") {
                popup.visible = okay && value.eligible === true && value.claimed === true;
                if (popup.visible) {
                    popup.windowCount = value.windows || 0;
                    popup.workspaceCount = value.workspaces || 0;
                }
            } else if (kind === "apply-last") {
                if (okay && Protocol.restoreSucceeded(value))
                    SessionV2Service.run("ack-restored", "", value.transaction_id, popup);
                else popup.fail();
            } else if (kind === "ack-restored") {
                if (okay && value.status === "acknowledged" && value.choice === "restored") {
                    popup.restored = true;
                    closeSuccess.start();
                } else popup.fail();
            } else if (kind === "ack-new") {
                if (okay && value.status === "acknowledged") popup.visible = false;
                else popup.fail();
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
    focusable: true
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "labfy-session-startup-v2"
    visible: false
    color: "transparent"
    onVisibleChanged: {
        if (startupHost) SessionV2Service.startupChooserVisible = visible;
        interactionArmed = false;
        if (visible) arm.restart(); else arm.stop();
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
                    text: popup.failed ? "Impossible de restaurer complètement la session."
                        : popup.restored ? "Session restaurée"
                        : popup.busy && popup.attempted ? "Restauration en cours…"
                        : popup.windowCount + " fenêtres • " + popup.workspaceCount + " espaces"
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
                        visible: !popup.failed
                        label: "Restaurer"
                        enabled: popup.interactionArmed && !popup.busy && !popup.attempted
                        onClicked: popup.restoreRequested()
                    }
                }
            }
        }
    }
}

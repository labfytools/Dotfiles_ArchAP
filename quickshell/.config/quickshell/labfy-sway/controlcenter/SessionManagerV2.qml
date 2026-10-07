import QtQuick
import QtQuick.Controls
import "../theme"
import "../sessionui"
import "../sessionui/Protocol.js" as Protocol

Item {
    id: page
    required property bool activePage
    signal backRequested()
    property var sessions: []
    property string selected: ""
    property string feedback: ""
    property string details: ""
    property bool restoreFailed: false
    property bool detailsVisible: false
    readonly property bool busy: SessionV2Service.busy
    implicitHeight: content.implicitHeight
    onActivePageChanged: if (activePage && !busy) SessionV2Service.run("list", "", "", page)
    Connections {
        target: SessionV2Service
        function onCompleted(owner, kind, value, okay) {
            if (owner !== page) return;
            if (kind === "list") { if (okay) page.sessions = value.sessions; return; }
            if (kind === "apply") {
                if (okay && Protocol.restoreSucceeded(value)) page.feedback = "Session restaurée";
                else {
                    page.restoreFailed = true;
                    page.feedback = "Impossible de restaurer complètement la session.";
                    SessionV2Service.run("restore-status", "", "", page);
                }
            } else if (kind === "restore-status") page.details = Protocol.details(value);
            else if (!okay) page.feedback = "L’opération n’a pas pu aboutir.";
            else if (kind === "plan") page.feedback = "Plan structurel : " + value.operations.length + " opérations. Aucune fenêtre modifiée.";
            else {
                page.feedback = kind === "save" ? "Session sauvegardée" : "Session supprimée";
                SessionV2Service.run("list", "", "", page);
            }
        }
    }
    Column {
        id: content
        width: parent.width
        spacing: 12
        Text { text: "Gestionnaire de sessions V2"; color: Theme.foreground; font.pixelSize: 17; font.bold: true }
        Text { width: parent.width; text: page.feedback; visible: text.length > 0; color: Theme.foreground; wrapMode: Text.Wrap }
        Text { width: parent.width; text: page.details; visible: page.detailsVisible; color: Theme.secondaryForeground; wrapMode: Text.Wrap }
        Column {
            width: parent.width
            spacing: 10
            visible: !page.restoreFailed
            TextField {
                id: nameField
                width: parent.width
                placeholderText: "Nom de la session"
                enabled: !page.busy
                maximumLength: 64
            }
            ActionButton {
                label: "Sauvegarder"
                enabled: !page.busy && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(nameField.text)
                    && page.sessions.indexOf(nameField.text) < 0
                onClicked: SessionV2Service.run("save", nameField.text, "", page)
            }
            ComboBox {
                id: selection
                width: parent.width
                model: page.sessions
                enabled: !page.busy
                onCurrentTextChanged: page.selected = currentText
            }
            Row {
                spacing: 8
                ActionButton {
                    label: "Aperçu"
                    enabled: !page.busy && page.selected.length > 0
                    onClicked: SessionV2Service.run("plan", page.selected, "", page)
                }
                ActionButton {
                    label: "Restaurer"
                    enabled: !page.busy && page.selected.length > 0
                    onClicked: { page.feedback = "Restauration en cours…"; SessionV2Service.run("apply", page.selected, "", page); }
                }
                ActionButton {
                    label: "Supprimer"
                    enabled: !page.busy && page.selected.length > 0
                    onClicked: SessionV2Service.run("delete", page.selected, "", page)
                }
            }
        }
        Row {
            spacing: 8
            ActionButton {
                visible: page.restoreFailed
                label: "Détails"
                enabled: !page.busy
                onClicked: page.detailsVisible = !page.detailsVisible
            }
            ActionButton {
                label: page.restoreFailed ? "Nouvelle session" : "Retour"
                enabled: !page.busy
                onClicked: { page.restoreFailed = false; page.feedback = ""; page.detailsVisible = false; page.backRequested(); }
            }
        }
    }
}

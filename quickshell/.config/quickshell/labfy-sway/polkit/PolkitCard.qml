import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import "../theme"

Item {
    id: card
    required property var flow
    property bool busy: false
    property bool awaitingIdentityPrompt: false
    property var pendingIdentity: null
    property bool detailsOpen: false
    readonly property bool waiting: !!flow && flow.isResponseRequired && !flow.isCompleted && !flow.isCancelled
    readonly property bool canEdit: waiting && !busy
    // INVARIANT: une touche Entrée sur un champ secret vide ne doit pas
    // consommer une tentative PAM. Une invite visible peut admettre une
    // réponse vide ; Polkit reste maître de sa validation.
    readonly property bool canSubmit: canEdit && (flow.responseVisible || answer.text.length > 0)
    implicitWidth: 480
    implicitHeight: content.implicitHeight + 36
    signal cancelled()

    // CONTRACT: only the bound native AuthFlow receives the response. The
    // field is cleared immediately; no answer enters logs, IPC or storage.
    function submitResponse() {
        const target = flow;
        if (!target || target !== card.flow || !canSubmit) return false;
        busy = true;
        target.submit(answer.text);
        answer.clear();
        return true;
    }
    function cancelRequest() {
        const target = flow;
        answer.clear();
        busy = true;
        if (target && !target.isCompleted && !target.isCancelled)
            target.cancelAuthenticationRequest();
        cancelled();
    }
    function selectIdentity(identity) {
        const target = flow;
        if (!target || !target.identities || target.identities.indexOf(identity) < 0) return;
        answer.clear();
        busy = true;
        awaitingIdentityPrompt = true;
        pendingIdentity = identity;
        target.selectedIdentity = identity;
    }
    function clearResponse() { answer.clear(); }
    function identityLabel(identity) {
        if (!identity) return "";
        return identity.displayName + " (" + identity.string + " · "
            + (identity.isGroup ? "GID " : "UID ") + identity.id + ")";
    }
    function focusResponse() { if (waiting) answer.forceActiveFocus(); else cancelButton.forceActiveFocus(); }
    onFlowChanged: { answer.clear(); busy = false; awaitingIdentityPrompt = false;
        pendingIdentity = null; detailsOpen = false; }
    Timer {
        id: identityPromptFallback
        interval: 1000
        running: card.awaitingIdentityPrompt
        // WHY: QuickShell 0.3.1 does not expose a session generation. When two
        // identities receive the same prompt, its notify values do not change.
        // The native setter has already replaced the session synchronously;
        // this bounded wait permits the new conversation to present its prompt.
        onTriggered: {
            if (card.flow && card.flow.selectedIdentity === card.pendingIdentity
                    && card.flow.isResponseRequired && !card.flow.isCompleted) {
                card.awaitingIdentityPrompt = false;
                card.busy = false;
                card.focusResponse();
            }
        }
    }
    onWaitingChanged: {
        if (waiting) {
            if (!awaitingIdentityPrompt) busy = false;
            answer.clear();
            Qt.callLater(focusResponse);
        } else answer.clear();
    }
    Connections {
        target: card.flow
        function onAuthenticationFailed() { card.busy = false; answer.clear(); }
        function onSelectedIdentityChanged() { answer.clear(); }
        function onInputPromptChanged() {
            answer.clear();
            if (card.awaitingIdentityPrompt && card.flow && card.flow.isResponseRequired) {
                card.awaitingIdentityPrompt = false;
                card.busy = false;
                Qt.callLater(card.focusResponse);
            }
        }
        function onIsResponseRequiredChanged() {
            if (card.awaitingIdentityPrompt && card.flow && card.flow.isResponseRequired) {
                card.awaitingIdentityPrompt = false;
                card.busy = false;
                Qt.callLater(card.focusResponse);
            }
        }
        function onIsCompletedChanged() { answer.clear(); }
        function onIsCancelledChanged() { answer.clear(); }
    }

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 18
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Rectangle {
                width: 38; height: 38; radius: 4
                color: Theme.buttonBackground
                Text { anchors.centerIn: parent; text: "󰌾"; color: Theme.accentForeground
                    font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 23 }
            }
            Text { Layout.fillWidth: true; text: "Authentification requise"; color: Theme.foreground
                font.pixelSize: 18; font.bold: true; wrapMode: Text.Wrap }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Image { Layout.preferredWidth: 24; Layout.preferredHeight: 24
                source: card.flow && card.flow.iconName ? Quickshell.iconPath(card.flow.iconName) : ""
                visible: status === Image.Ready; fillMode: Image.PreserveAspectFit }
            Text { Layout.fillWidth: true; text: card.flow ? card.flow.message : ""
                textFormat: Text.PlainText; color: Theme.foreground; wrapMode: Text.Wrap; font.pixelSize: 14 }
        }
        Text { Layout.fillWidth: true; text: "Compte d’authentification";
            color: Theme.secondaryForeground; font.pixelSize: 12 }
        Text { Layout.fillWidth: true; visible: !!card.flow && card.flow.identities.length === 1
            text: card.flow && card.flow.selectedIdentity
                ? card.flow.selectedIdentity.displayName + " (" + card.flow.selectedIdentity.string + ")" : ""
            textFormat: Text.PlainText; color: Theme.foreground; font.pixelSize: 14; elide: Text.ElideRight }
        ComboBox {
            id: identityChoice
            Layout.fillWidth: true
            visible: !!card.flow && card.flow.identities.length > 1
            model: card.flow ? card.flow.identities.map(identity => ({ label: card.identityLabel(identity) })) : []
            textRole: "label"
            currentIndex: card.flow && card.flow.identities
                ? card.flow.identities.indexOf(card.flow.selectedIdentity) : -1
            onActivated: index => card.selectIdentity(card.flow.identities[index])
            background: Rectangle { radius: 4; color: Theme.inputBackground
                border.color: identityChoice.activeFocus ? Theme.focus : Theme.inputBorder }
            contentItem: Text { text: identityChoice.displayText; textFormat: Text.PlainText
                color: Theme.foreground
                verticalAlignment: Text.AlignVCenter; leftPadding: 10; elide: Text.ElideRight }
            delegate: ItemDelegate {
                width: identityChoice.width
                text: modelData.label
                contentItem: Text { text: parent.text; textFormat: Text.PlainText
                    color: Theme.foreground
                    verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                background: Rectangle { color: parent.highlighted ? Theme.buttonHover : Theme.popupBackground }
            }
            popup: Popup {
                y: identityChoice.height
                width: identityChoice.width
                implicitHeight: Math.min(contentItem.implicitHeight, 240)
                contentItem: ListView { clip: true; implicitHeight: contentHeight
                    model: identityChoice.popup.visible ? identityChoice.delegateModel : null
                    currentIndex: identityChoice.highlightedIndex }
                background: Rectangle { radius: 4; color: Theme.popupBackground
                    border.color: Theme.outline }
            }
        }
        Text { Layout.fillWidth: true
            text: card.flow && card.flow.inputPrompt ? card.flow.inputPrompt : "En attente de la demande…"
            textFormat: Text.PlainText; color: Theme.secondaryForeground; wrapMode: Text.Wrap; font.pixelSize: 12 }
        TextField {
            id: answer
            objectName: "polkitResponse"
            Layout.fillWidth: true
            enabled: card.canEdit
            visible: card.waiting
            echoMode: card.flow && card.flow.responseVisible ? TextInput.Normal : TextInput.Password
            color: Theme.foreground
            placeholderTextColor: Theme.secondaryForeground
            selectionColor: Theme.accent
            selectedTextColor: Theme.onAccent
            selectByMouse: true
            placeholderText: card.flow && card.flow.responseVisible ? "Réponse" : "Réponse confidentielle"
            Keys.onReturnPressed: event => { card.submitResponse(); event.accepted = true; }
            Keys.onEnterPressed: event => { card.submitResponse(); event.accepted = true; }
            background: Rectangle { radius: 4; color: Theme.inputBackground
                border.color: answer.activeFocus ? Theme.focus : Theme.inputBorder }
        }
        Text { Layout.fillWidth: true
            visible: !!card.flow && (!!card.flow.supplementaryMessage || card.flow.failed)
            text: card.flow ? (card.flow.supplementaryMessage
                || (card.flow.failed ? "Authentification refusée. Réessayez." : "")) : ""
            textFormat: Text.PlainText
            color: card.flow && (card.flow.supplementaryMessage
                ? card.flow.supplementaryIsError : card.flow.failed)
                ? Theme.danger : Theme.secondaryForeground
            wrapMode: Text.Wrap; font.pixelSize: 12 }
        Text { Layout.fillWidth: true; visible: !card.waiting
            text: card.flow && card.flow.isCompleted ? "Demande terminée" : "En attente de l’agent d’authentification…"
            color: Theme.secondaryForeground; font.pixelSize: 12 }
        Button {
            id: detailButton
            text: card.detailsOpen ? "Masquer l’identifiant de l’action" : "Détails de l’action"
            flat: true
            onClicked: card.detailsOpen = !card.detailsOpen
            contentItem: Text { text: detailButton.text; color: Theme.accentForeground
                font.pixelSize: 12; verticalAlignment: Text.AlignVCenter }
        }
        Text { Layout.fillWidth: true; visible: card.detailsOpen
            text: card.flow ? card.flow.actionId : ""; textFormat: Text.PlainText
            color: Theme.secondaryForeground; wrapMode: Text.WrapAnywhere; font.pixelSize: 11 }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button { id: cancelButton; text: "Annuler"; onClicked: card.cancelRequest()
                background: Rectangle { radius: 4; color: cancelButton.hovered ? Theme.buttonHover : Theme.buttonBackground
                    border.color: cancelButton.activeFocus ? Theme.focus : Theme.outline }
                contentItem: Text { text: cancelButton.text; color: Theme.foreground
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter } }
            Button { id: submitButton; text: "Authentifier"; enabled: card.canSubmit
                onClicked: card.submitResponse()
                background: Rectangle { radius: 4; color: Theme.accent
                    border.color: submitButton.activeFocus ? Theme.foreground : Theme.accent }
                contentItem: Text { text: submitButton.text; color: Theme.onAccent
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter } }
        }
    }
    Shortcut { sequence: "Escape"; context: Qt.WindowShortcut; onActivated: card.cancelRequest() }
}

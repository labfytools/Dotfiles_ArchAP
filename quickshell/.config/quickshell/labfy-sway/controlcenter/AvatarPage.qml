import QtQuick
import QtQuick.Dialogs
import Quickshell.Io
import "../components"
import "../theme"

Item {
    id: page
    required property bool activePage
    signal backRequested()
    property string currentPath: ""
    property string selectedUrl: ""
    property string feedback: ""
    property bool failed: false
    readonly property string backend: "/usr/local/libexec/labfy-greeter/avatar_backend.py"

    onActivePageChanged: if (activePage) {
        feedback = "";
        currentProcess.command = ["python3", backend, "current"];
        currentProcess.running = true;
    }

    Process {
        id: currentProcess
        stdout: StdioCollector { id: currentOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (!page.activePage) return;
            if (code !== 0 || status !== 0) {
                page.failed = true;
                page.feedback = "Service avatar indisponible.";
                page.currentPath = "";
                return;
            }
            try {
                const result = JSON.parse(currentOutput.text);
                page.currentPath = result.path || "";
            } catch (_) {
                page.failed = true;
                page.feedback = "Service avatar indisponible.";
                page.currentPath = "";
            }
        }
    }
    Process {
        id: setProcess
        stdout: StdioCollector { id: setOutput; waitForEnd: true }
        onExited: (code, status) => {
            try {
                const result = JSON.parse(setOutput.text);
                if (code !== 0 || status !== 0 || !result.path) {
                    page.failed = true;
                    page.feedback = result.error || "Impossible de modifier l’avatar.";
                    return;
                }
                page.currentPath = result.path;
                page.selectedUrl = "";
                page.failed = false;
                page.feedback = "Avatar enregistré pour le prochain écran de connexion.";
            } catch (_) {
                page.failed = true;
                page.feedback = "Impossible de modifier l’avatar.";
            }
        }
    }
    FileDialog {
        id: picker
        title: "Choisir un avatar"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp)"]
        onAccepted: {
            page.selectedUrl = selectedFile.toString();
            page.feedback = "";
        }
    }

    Column {
        anchors.fill: parent
        spacing: 13
        Row {
            spacing: 8; height: 30
            ActionButton { label: ""; onClicked: page.backRequested() }
            Text { text: "Avatar"; color: Theme.foreground; font.pixelSize: 16; font.bold: true; height: 30; verticalAlignment: Text.AlignVCenter }
        }
        Text {
            width: parent.width
            text: "Image affichée sur l’écran de connexion"
            color: Theme.secondaryForeground
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }
        Rectangle {
            width: 112; height: 112; radius: 8
            anchors.horizontalCenter: parent.horizontalCenter
            color: Theme.buttonBackground
            border.color: Theme.border
            clip: true
            Image {
                id: avatarImage
                anchors.fill: parent; anchors.margins: 2
                source: page.selectedUrl || (page.currentPath ? "file://" + page.currentPath : "")
                fillMode: Image.PreserveAspectCrop
                sourceSize.width: 256; sourceSize.height: 256
                asynchronous: true; cache: false
                visible: source !== "" && status === Image.Ready
            }
            NerdIcon {
                anchors.centerIn: parent
                text: ""; color: Theme.accent; font.pixelSize: 44
                visible: avatarImage.status !== Image.Ready
            }
        }
        Row {
            spacing: 8
            ActionButton { label: "Choisir une image"; enabled: !setProcess.running; onClicked: picker.open() }
            ActionButton {
                label: setProcess.running ? "Enregistrement…" : "Appliquer"
                enabled: !!page.selectedUrl && !setProcess.running
                onClicked: {
                    page.feedback = "";
                    setProcess.command = ["python3", page.backend, "set", page.selectedUrl];
                    setProcess.running = true;
                }
            }
        }
        Text {
            width: parent.width
            text: page.feedback
            visible: !!page.feedback
            color: page.failed ? Theme.warningForeground : Theme.successForeground
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }
        Text {
            width: parent.width
            text: "PNG, JPEG ou WebP · 12 Mio maximum. L’image est ajustée au format carré."
            color: Theme.secondaryForeground
            font.pixelSize: 10
            wrapMode: Text.Wrap
        }
    }
}

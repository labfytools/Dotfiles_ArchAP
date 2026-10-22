import QtQuick
import Quickshell
import Quickshell.Io
import "../components"
import "../controlcenter"
import "../theme"

Item {
    id: indicator
    signal toggleRequested()
    property alias popupOpen: popup.visible
    readonly property string backend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/printing/backend.py"
    // TEST_ONLY: fixtures visuelles sans accès à une file ou à l'action cancel.
    readonly property string testState: Quickshell.env("LABFY_PRINTING_TEST_STATE") || ""
    property var printingData: ({schema: "labfy.printing", version: 1, scheduler: false,
        default_printer: null, printers: [], jobs: []})
    property string actionError: ""
    readonly property int jobCount: printingData.jobs.length
    readonly property bool active: printingData.jobs.some(job => job.state === "processing")
        || printingData.printers.some(printer => printer.state === "printing")
    readonly property bool error: printingData.printers.some(printer => printer.state === "error"
        || printer.state === "offline" || printer.state === "stopped")
    readonly property var defaultPrinter: printingData.printers.find(printer => printer.default)
    width: jobCount ? 44 : 26
    height: 26

    function validState(value) {
        return value && value.schema === "labfy.printing" && value.version === 1
            && typeof value.scheduler === "boolean"
            && (value.default_printer === null || typeof value.default_printer === "string")
            && Array.isArray(value.printers) && Array.isArray(value.jobs)
            && value.printers.every(printer => printer && typeof printer.name === "string"
                && typeof printer.state === "string" && typeof printer.default === "boolean")
            && value.jobs.every(job => job && Number.isSafeInteger(job.id) && job.id > 0
                && typeof job.document === "string" && typeof job.printer === "string"
                && typeof job.state === "string");
    }

    function refresh() {
        // INVARIANT: un seul processus de lecture à la fois, y compris après clic.
        if (!testState && !statusProcess.running) {
            statusProcess.command = ["python3", "-B", backend, "status"];
            statusProcess.running = true;
            statusDeadline.restart();
        }
    }
    function cancelJob(identifier) {
        if (testState || !Number.isSafeInteger(identifier) || identifier <= 0
                || identifier > 2147483647 || cancelProcess.running) return;
        actionError = "";
        // CONTRACT: argv direct ; le nom du document n'entre jamais dans la commande.
        cancelProcess.command = ["python3", "-B", backend, "cancel", String(identifier)];
        cancelProcess.running = true;
    }
    function stateLabel(value) {
        switch (value) {
        case "ready": return "Prête";
        case "printing": return "Impression en cours";
        case "stopped": return "En pause";
        case "offline": return "Hors ligne";
        case "error": return "Erreur";
        case "pending": return "En attente";
        case "held": return "En pause";
        case "processing": return "Impression en cours";
        default: return "Indisponible";
        }
    }
    readonly property string tooltip: !printingData.scheduler ? "Impression — indisponible"
        : defaultPrinter && (defaultPrinter.state === "error"
            || defaultPrinter.state === "offline") ? "Impression — erreur"
        : jobCount ? "Impression — " + jobCount + (jobCount === 1
            ? " travail en attente" : " travaux en attente")
        : defaultPrinter ? "Impression — " + stateLabel(defaultPrinter.state)
        : "Impression — aucune imprimante"

    function fixture(mode) {
        if (mode === "unavailable") return {schema: "labfy.printing", version: 1,
            scheduler: false, default_printer: null, printers: [], jobs: []};
        if (mode === "jobs") return {schema: "labfy.printing", version: 1,
            scheduler: true, default_printer: "ENVY_5000",
            printers: [{name: "ENVY_5000", state: "printing", default: true},
                {name: "Brother_Laser", state: "stopped", default: false}],
            jobs: [{id: 12, document: "document.pdf", printer: "ENVY_5000", state: "processing"},
                {id: 13, document: "rapport.pdf", printer: "Brother_Laser", state: "pending"}]};
        return {schema: "labfy.printing", version: 1, scheduler: true,
            default_printer: "ENVY_5000",
            printers: [{name: "ENVY_5000", state: "ready", default: true}], jobs: []};
    }
    onPopupOpenChanged: if (popupOpen) refresh()
    Component.onCompleted: {
        if (testState) printingData = fixture(testState);
        else refresh();
    }

    Timer {
        // WHY: cinq secondes pendant une file active, trente secondes au repos.
        interval: indicator.jobCount > 0 || indicator.active || indicator.popupOpen
            ? 5000 : 30000
        repeat: true
        running: !indicator.testState
        onTriggered: indicator.refresh()
    }
    Timer {
        id: statusDeadline
        interval: 8000
        // CONTRACT: une requête CUPS bloquée ne conserve pas son processus.
        onTriggered: if (statusProcess.running) statusProcess.running = false
    }
    Process {
        id: statusProcess
        stdout: StdioCollector { id: statusOutput; waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: (code, status) => {
            statusDeadline.stop();
            if (code !== 0) {
                indicator.printingData = {schema: "labfy.printing", version: 1,
                    scheduler: false, default_printer: null, printers: [], jobs: []};
                return;
            }
            try {
                const value = JSON.parse(statusOutput.text);
                if (!indicator.validState(value)) throw new Error("État invalide");
                indicator.printingData = value;
            } catch (_) {
                indicator.printingData = {schema: "labfy.printing", version: 1,
                    scheduler: false, default_printer: null, printers: [], jobs: []};
            }
        }
    }
    Process {
        id: cancelProcess
        stdout: StdioCollector { waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: (code, status) => {
            indicator.actionError = code === 0 ? "" : "Annulation impossible";
            indicator.refresh();
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: pointer.containsMouse || popup.visible ? Theme.border : "transparent"
    }
    Row {
        anchors.centerIn: parent
        spacing: 3
        NerdIcon {
            text: "󰐪"
            color: !indicator.printingData.scheduler ? Theme.disabledForeground
                : indicator.error ? Theme.red
                : indicator.active ? Theme.yellow : Theme.peach
            font.pixelSize: 23
        }
        Text {
            visible: indicator.jobCount > 0
            text: String(indicator.jobCount)
            color: Theme.secondaryForeground
            font.pixelSize: 10
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        onClicked: indicator.toggleRequested()
    }
    StatusTooltip {
        target: indicator
        hovered: pointer.containsMouse && !popup.visible
        message: indicator.tooltip
    }
    PopupWindow {
        id: popup
        anchor.item: indicator
        anchor.edges: Edges.Bottom | Edges.Left
        anchor.gravity: Edges.Bottom | Edges.Right
        anchor.margins.bottom: -6
        visible: false
        grabFocus: false
        color: "transparent"
        implicitWidth: 400
        implicitHeight: Math.min(540, content.implicitHeight + 24)

        Rectangle {
            anchors.fill: parent
            radius: 4
            color: Theme.popupBackground
            border.color: Theme.outline
            Flickable {
                anchors.fill: parent
                anchors.margins: 12
                clip: true
                contentWidth: width
                contentHeight: content.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: content
                    width: parent.width
                    spacing: 10
                    Text {
                        width: parent.width
                        text: "Imprimante par défaut"
                        color: Theme.accentForeground
                        font.pixelSize: 16
                        font.bold: true
                    }
                    Text {
                        width: parent.width
                        text: !indicator.printingData.scheduler ? "CUPS indisponible"
                            : indicator.defaultPrinter ? indicator.defaultPrinter.name
                            : "Aucune imprimante par défaut"
                        color: Theme.foreground
                        font.pixelSize: 14
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        text: indicator.defaultPrinter
                            ? indicator.stateLabel(indicator.defaultPrinter.state)
                            : "Indisponible"
                        color: Theme.secondaryForeground
                        font.pixelSize: 11
                    }
                    Text {
                        width: parent.width
                        text: "Imprimantes"
                        color: Theme.accentForeground
                        font.pixelSize: 14
                        font.bold: true
                    }
                    Text {
                        visible: indicator.printingData.printers.length === 0
                        text: indicator.printingData.scheduler ? "Aucune imprimante configurée"
                            : "CUPS indisponible"
                        color: Theme.secondaryForeground
                        font.pixelSize: 11
                    }
                    Repeater {
                        model: indicator.printingData.printers
                        Rectangle {
                            required property var modelData
                            width: content.width
                            height: 48
                            radius: 4
                            color: Theme.buttonBackground
                            border.color: Theme.outline
                            Column {
                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 3
                                Text {
                                    width: parent.width
                                    text: modelData.name + (modelData.default ? "  ·  Par défaut" : "")
                                    color: Theme.foreground
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: indicator.stateLabel(modelData.state)
                                    color: modelData.state === "error" || modelData.state === "offline"
                                        ? Theme.red
                                        : Theme.secondaryForeground
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        text: "Travaux"
                        color: Theme.accentForeground
                        font.pixelSize: 14
                        font.bold: true
                    }
                    Text {
                        visible: indicator.jobCount === 0
                        text: "Aucun travail en attente"
                        color: Theme.secondaryForeground
                        font.pixelSize: 11
                    }
                    Repeater {
                        model: indicator.printingData.jobs
                        Rectangle {
                            required property var modelData
                            width: content.width
                            height: 69
                            radius: 4
                            color: Theme.buttonBackground
                            border.color: Theme.outline
                            Column {
                                anchors.left: parent.left
                                anchors.right: cancelButton.left
                                anchors.top: parent.top
                                anchors.margins: 7
                                spacing: 4
                                Text {
                                    width: parent.width
                                    text: modelData.document
                                    color: Theme.foreground
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: modelData.printer + " · " + indicator.stateLabel(modelData.state)
                                        + " · #" + modelData.id
                                    color: Theme.secondaryForeground
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                            }
                            ActionButton {
                                id: cancelButton
                                anchors.right: parent.right
                                anchors.rightMargin: 7
                                anchors.verticalCenter: parent.verticalCenter
                                label: "Annuler"
                                enabled: !cancelProcess.running
                                onClicked: indicator.cancelJob(modelData.id)
                            }
                        }
                    }
                    Text {
                        visible: indicator.actionError.length > 0
                        text: indicator.actionError
                        color: Theme.red
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
}

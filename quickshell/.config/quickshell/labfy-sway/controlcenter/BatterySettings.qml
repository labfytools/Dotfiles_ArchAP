import QtQuick
import QtQuick.Controls
import Quickshell.Io
import Quickshell.Services.UPower
import "../components"
import "../theme"

Item {
    id: page
    signal backRequested()
    signal thresholdApplied()
    property bool activePage: false
    property string phase: "Idle"
    property string feedback: ""
    property bool edited: false
    property bool keypadVisible: false
    property bool keypadFresh: true
    property int requestedValue: -1
    property int readAttempts: 0
    readonly property var battery: UPower.displayDevice
    readonly property bool available: battery && battery.ready && battery.isPresent
    readonly property int percent: available ? Math.round(battery.percentage * 100) : 0
    readonly property string batteryState: !available ? "Indisponible"
        : battery.state === UPowerDeviceState.Charging ? "En charge"
        : battery.state === UPowerDeviceState.FullyCharged ? "Pleine"
        : battery.state === UPowerDeviceState.PendingCharge ? "En attente de charge"
        : battery.state === UPowerDeviceState.PendingDischarge ? "En attente de décharge"
        : battery.state === UPowerDeviceState.Discharging ? "Décharge"
        : battery.state === UPowerDeviceState.Empty ? "Vide" : "État inconnu"
    readonly property int reportedThreshold: {
        const raw = thresholdFile.text().trim();
        if (!/^[0-9]{1,3}$/.test(raw)) return -1;
        const value = Number(raw);
        return value >= 0 && value <= 100 ? value : -1;
    }
    readonly property bool validProposed: /^[0-9]{1,3}$/.test(valueField.text)
        && Number(valueField.text) >= 40 && Number(valueField.text) <= 100
    readonly property bool helperReady: helperFile.text().includes("LABFY_TLP_PERSISTENT_V1")

    implicitHeight: keypadVisible ? 502 : 350

    // Une modification externe invalide le dernier message de succès local.
    onReportedThresholdChanged: if (phase === "Success" && reportedThreshold !== requestedValue) {
        phase = "Idle";
        feedback = "";
    }

    function propose(value) {
        if (phase === "Applying") return;
        valueField.text = String(value);
        edited = true;
        phase = "Idle";
        feedback = "";
    }

    function keypadPress(key) {
        if (phase === "Applying") return;
        if (key === "OK") {
            keypadVisible = false;
            return;
        }
        if (key === "C") valueField.text = "";
        else if (key === "⌫") valueField.text = keypadFresh ? "" : valueField.text.slice(0, -1);
        else {
            const prefix = keypadFresh ? "" : valueField.text;
            if (prefix.length >= 3) return;
            valueField.text = prefix + String(key);
        }
        keypadFresh = false;
        edited = true;
        phase = "Idle";
        feedback = "";
    }

    function apply() {
        if (phase === "Applying" || writer.running || !validProposed
                || reportedThreshold < 0 || !helperReady) return;
        requestedValue = Number(valueField.text);
        if (!Number.isInteger(requestedValue) || requestedValue < 40 || requestedValue > 100) return;
        phase = "Applying";
        feedback = "Application en cours…";
        writer.command = ["sudo", "-n", "/usr/local/sbin/batlimit-set", String(requestedValue)];
        writer.running = true;
        applyTimeout.start();
    }

    function verifyReadback() {
        if (phase !== "Applying") return;
        if (reportedThreshold === requestedValue) {
            phase = "Success";
            feedback = "Limite configurée : " + reportedThreshold + " %";
            edited = false;
            thresholdApplied();
        } else if (readAttempts < 3) {
            readAttempts++;
            readbackTimer.start();
        } else {
            phase = "Error";
            feedback = reportedThreshold >= 0
                ? "Valeur rapportée par le pilote : " + reportedThreshold + " %"
                : "Impossible de relire la limite rapportée";
        }
    }

    onActivePageChanged: {
        if (activePage) {
            thresholdFile.reload();
            helperFile.reload();
            Qt.callLater(() => valueField.forceActiveFocus());
        }
        if (phase !== "Applying") {
            edited = false;
            keypadVisible = false;
            keypadFresh = true;
            phase = "Idle";
            feedback = "";
            if (reportedThreshold >= 0) valueField.text = String(reportedThreshold);
        }
    }

    // Le pilote peut ne pas émettre d'événement inotify : la relecture après écriture est obligatoire.
    FileView {
        id: thresholdFile
        path: "/sys/class/power_supply/BAT1/charge_control_end_threshold"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            if (page.phase === "Applying" && !writer.running) page.verifyReadback();
            else if (!page.edited && page.phase !== "Applying" && page.reportedThreshold >= 0)
                valueField.text = String(page.reportedThreshold);
        }
        onLoadFailed: error => {
            if (page.phase !== "Applying" || writer.running) return;
            if (page.readAttempts < 3) {
                page.readAttempts++;
                readbackTimer.start();
            } else {
                page.phase = "Error";
                page.feedback = "Impossible de relire la limite rapportée";
            }
        }
    }


    // L'ancien helper écrit seulement sysfs : interdire son appel tant que le déploiement manque.
    FileView {
        id: helperFile
        path: "/usr/local/sbin/batlimit-set"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
    }

    Process {
        id: writer
        stdout: StdioCollector { id: helperOutput; waitForEnd: true }
        stderr: StdioCollector { id: helperError; waitForEnd: true }
        onExited: (exitCode, exitStatus) => {
            applyTimeout.stop();
            if (exitCode !== 0 || exitStatus !== 0) {
                page.phase = "Error";
                page.feedback = helperError.text.includes("invalid_value")
                    ? "Valeur comprise entre 40 et 100"
                    : "Impossible d'appliquer la limite de charge";
                return;
            }
            if (helperOutput.text.trim() !== "SUCCESS " + page.requestedValue) {
                page.phase = "Error";
                page.feedback = "Réponse inattendue du service de charge";
                return;
            }
            page.readAttempts = 0;
            thresholdFile.reload();
        }
    }

    Timer {
        id: readbackTimer
        interval: 150
        repeat: false
        onTriggered: thresholdFile.reload()
    }

    Timer {
        id: applyTimeout
        interval: 25000
        repeat: false
        onTriggered: {
            if (page.phase === "Applying") {
                page.phase = "Error";
                page.feedback = "Délai dépassé pour appliquer la limite";
                writer.running = false;
            }
        }
    }

    Column {
        anchors.fill: parent
        spacing: 12

        Item {
            width: parent.width
            height: 28
            NerdIcon {
                id: backIcon
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: ""
            }
            Text {
                anchors.left: backIcon.right
                anchors.leftMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: "Batterie"
                color: Theme.foreground
                font.pixelSize: 16
                font.bold: true
            }
            MouseArea {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 100
                onClicked: page.backRequested()
            }
        }

        Rectangle {
            width: parent.width
            height: 68
            radius: 4
            color: Theme.buttonBackground
            NerdIcon {
                id: batteryIcon
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                font.pixelSize: 18
                text: page.percent <= 15 ? "󰁺" : page.percent <= 30 ? "󰁻"
                    : page.percent <= 50 ? "󰁽" : page.percent <= 75 ? "󰁿" : "󰁹"
            }
            Column {
                anchors.left: batteryIcon.right
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text {
                    text: page.available ? page.percent + " %" : "Batterie indisponible"
                    color: Theme.foreground
                    font.pixelSize: 16
                }
                Text {
                    text: page.batteryState
                    color: Theme.secondaryForeground
                    font.pixelSize: 12
                }
            }
        }

        Text {
            text: "Limite de charge"
            color: Theme.foreground
            font.pixelSize: 14
        }

        Row {
            width: parent.width
            spacing: 8
            Rectangle {
                width: 42; height: 38; radius: 4
                color: minusPointer.containsMouse ? Theme.border : Theme.buttonBackground
                Text { anchors.centerIn: parent; text: "−"; color: Theme.foreground; font.pixelSize: 18 }
                MouseArea {
                    id: minusPointer
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: page.phase !== "Applying" && page.reportedThreshold >= 0
                    onClicked: page.propose(Math.max(40, (page.validProposed
                        ? Number(valueField.text) : page.reportedThreshold) - 5))
                }
            }
            TextField {
                id: valueField
                width: parent.width - 100
                height: 38
                horizontalAlignment: TextInput.AlignHCenter
                color: Theme.foreground
                font.pixelSize: 16
                maximumLength: 3
                inputMethodHints: Qt.ImhDigitsOnly
                validator: RegularExpressionValidator { regularExpression: /[0-9]{0,3}/ }
                enabled: page.phase !== "Applying"
                selectByMouse: true
                onTextEdited: {
                    page.edited = true;
                    page.phase = "Idle";
                    page.feedback = "";
                }
                TapHandler {
                    onTapped: {
                        page.keypadVisible = true;
                        page.keypadFresh = true;
                    }
                }
                background: Rectangle {
                    radius: 4
                    color: Theme.buttonBackground
                    border.color: page.validProposed ? Theme.border : Theme.danger
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: "%"
                    color: Theme.secondaryForeground
                    font.pixelSize: 13
                }
            }
            Rectangle {
                width: 42; height: 38; radius: 4
                color: plusPointer.containsMouse ? Theme.border : Theme.buttonBackground
                Text { anchors.centerIn: parent; text: "+"; color: Theme.foreground; font.pixelSize: 18 }
                MouseArea {
                    id: plusPointer
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: page.phase !== "Applying" && page.reportedThreshold >= 0
                    onClicked: page.propose(Math.min(100, (page.validProposed
                        ? Number(valueField.text) : page.reportedThreshold) + 5))
                }
            }
        }

        Grid {
            visible: page.keypadVisible
            width: parent.width
            columns: 4
            spacing: 4
            Repeater {
                model: ["1", "2", "3", "⌫", "4", "5", "6", "C",
                    "7", "8", "9", "OK", "", "0", "", ""]
                delegate: Rectangle {
                    required property string modelData
                    width: (parent.width - 12) / 4
                    height: 32
                    radius: 4
                    opacity: modelData !== "" ? 1 : 0
                    color: keyPointer.containsMouse ? Theme.border : Theme.buttonBackground
                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        color: Theme.foreground
                        font.pixelSize: 13
                    }
                    MouseArea {
                        id: keyPointer
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: modelData !== ""
                        onClicked: page.keypadPress(modelData)
                    }
                }
            }
        }

        Row {
            spacing: 8
            Repeater {
                model: [60, 80, 100]
                delegate: Rectangle {
                    required property int modelData
                    width: 60; height: 32; radius: 4
                    color: page.reportedThreshold === modelData ? Theme.emphasisBackground : Theme.buttonBackground
                    border.color: page.validProposed && Number(valueField.text) === modelData
                        ? Theme.accent : "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        color: Theme.foreground
                        font.pixelSize: 13
                    }
                    MouseArea {
                        anchors.fill: parent
                        enabled: page.phase !== "Applying"
                        onClicked: page.propose(modelData)
                    }
                }
            }
        }

        Text {
            text: page.reportedThreshold >= 0
                ? "Limite rapportée : " + page.reportedThreshold + " %" : "Limite indisponible"
            color: Theme.secondaryForeground
            font.pixelSize: 12
        }

        Rectangle {
            width: parent.width
            height: 36
            radius: 4
            color: Theme.accent
            opacity: applyPointer.enabled ? 1 : 0.5
            Text {
                anchors.centerIn: parent
                text: page.phase === "Applying" ? "Application…" : "Appliquer"
                color: Theme.onAccent
                font.pixelSize: 13
            }
            MouseArea {
                id: applyPointer
                anchors.fill: parent
                hoverEnabled: true
                enabled: page.phase !== "Applying" && page.validProposed
                    && page.reportedThreshold >= 0 && page.helperReady
                    && Number(valueField.text) !== page.reportedThreshold
                onClicked: page.apply()
            }
        }

        Text {
            width: parent.width
            text: page.feedback.length ? page.feedback
                : !page.validProposed ? "Valeur comprise entre 40 et 100"
                : !page.helperReady ? "Service de charge non déployé" : ""
            color: page.phase === "Error" || !page.validProposed || !page.helperReady
                ? Theme.danger : Theme.success
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
    }
}

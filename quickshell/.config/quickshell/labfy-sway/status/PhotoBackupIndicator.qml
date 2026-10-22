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
    readonly property string backend: (Quickshell.env("HOME") || "")
        + "/.local/bin/labfy-photo-backup"
    readonly property string statePath: (Quickshell.env("XDG_STATE_HOME")
        || (Quickshell.env("HOME") + "/.local/state")) + "/labfy-photo-backup/status.json"
    // TEST_ONLY : aucune commande ni lecture de statut réel dans les fixtures.
    readonly property string testState: Quickshell.env("LABFY_PHOTO_BACKUP_TEST_STATE") || ""
    property var backupData: ({schema: "labfy.photo-backup", version: 1,
        disk_present: false, mounted: false, phase: "idle", progress_bytes: 0,
        total_bytes: 0, progress_percent: 0, error: null, last_success: null})
    property bool statusReadable: false
    property bool startPending: false
    property string actionError: ""
    readonly property bool busy: ["planning", "copying", "verifying"].indexOf(backupData.phase) !== -1
    readonly property bool hasError: backupData.phase === "error" || Boolean(backupData.error)
        || actionError.length > 0 || !statusReadable
    readonly property bool canStart: statusReadable && backupData.disk_present
        && backupData.mounted && !busy && !startPending && !startProcess.running
    readonly property real progress: Math.max(0, Math.min(100, backupData.progress_percent))
    readonly property real usbSpeed: typeof backupData.usb_speed_mbps === "number"
        && isFinite(backupData.usb_speed_mbps) && backupData.usb_speed_mbps > 0
        ? backupData.usb_speed_mbps : 0
    readonly property string statusLabel: !statusReadable ? "État indisponible"
        : !backupData.mounted ? "SSD présent, en attente du montage"
        : startPending ? "Démarrage…"
        : backupData.phase === "planning" ? "Préparation de la sauvegarde…"
        : backupData.phase === "copying" ? "Copie en cours"
        : backupData.phase === "verifying" ? "Vérification en cours"
        : hasError ? "Sauvegarde interrompue"
        : backupData.phase === "success" ? "Sauvegarde vérifiée"
        : "Prêt à sauvegarder"

    visible: backupData.disk_present
    width: visible ? (busy ? 58 : 26) : 0
    height: 26
    onVisibleChanged: if (!visible) popup.visible = false
    onPopupOpenChanged: if (popupOpen) refresh()
    Component.onCompleted: {
        if (testState) {
            backupData = fixture(testState);
            statusReadable = true;
        } else refresh();
    }

    function fixture(mode) {
        const value = {schema: "labfy.photo-backup", version: 1,
            disk_present: mode !== "absent", mounted: mode !== "absent" && mode !== "unmounted",
            phase: "idle", progress_bytes: 0, total_bytes: 0, progress_percent: 0,
            error: null, last_success: "2026-10-21T12:30:00+02:00", usb_speed_mbps: 10000};
        if (mode === "copying" || mode === "verifying") {
            value.phase = mode;
            value.total_bytes = 40 * 1024 * 1024 * 1024;
            value.progress_bytes = 17 * 1024 * 1024 * 1024;
            value.progress_percent = 42.5;
        } else if (mode === "error") {
            value.phase = "error";
            value.error = "Le SSD a été déconnecté pendant la sauvegarde. Rebranche-le pour reprendre.";
        } else if (mode === "success") value.phase = "success";
        if (mode === "usb2") value.usb_speed_mbps = 480;
        return value;
    }

    function validState(value) {
        return value && value.schema === "labfy.photo-backup" && value.version === 1
            && typeof value.disk_present === "boolean" && typeof value.mounted === "boolean"
            && ["idle", "planning", "copying", "verifying", "success", "error"].indexOf(value.phase) !== -1
            && Number.isSafeInteger(value.progress_bytes) && value.progress_bytes >= 0
            && Number.isSafeInteger(value.total_bytes) && value.total_bytes >= 0
            && typeof value.progress_percent === "number" && isFinite(value.progress_percent)
            && (value.error === null || typeof value.error === "string")
            && (value.last_success === null || typeof value.last_success === "string");
    }
    function refresh() {
        if (testState || statusProcess.running) return;
        // Le backend identifie le SSD par UUID ; le label n'autorise aucune écriture.
        statusProcess.command = [backend, "status"];
        statusProcess.running = true;
        statusDeadline.restart();
    }
    function startBackup() {
        if (testState || !canStart) return;
        actionError = "";
        startPending = true;
        startDeadline.restart();
        // Le service reste indépendant d'une fermeture du popup ou d'un reload QML.
        startProcess.command = ["systemctl", "--user", "start", "--no-block",
            "labfy-photo-backup.service"];
        startProcess.running = true;
    }
    function formatSize(bytes) {
        let amount = bytes;
        const units = ["o", "Kio", "Mio", "Gio", "Tio"];
        let unit = 0;
        while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit++; }
        return (unit ? amount.toFixed(1) : String(amount)) + " " + units[unit];
    }
    function lastSuccessLabel() {
        if (!backupData.last_success) return "Aucune sauvegarde vérifiée pour le moment";
        const date = new Date(backupData.last_success);
        if (isNaN(date.getTime())) return "Dernière sauvegarde vérifiée : date indisponible";
        return "Dernière vérification : " + Qt.formatDateTime(date, "dd/MM/yyyy 'à' hh:mm");
    }
    function diagnostics() {
        const position = indicator.mapToItem(null, 0, 0);
        return {visible: visible, open: popupOpen, mounted: backupData.mounted,
            phase: backupData.phase, progress: progress, busy: busy, canStart: canStart,
            test_mode: testState, status_query_running: statusProcess.running,
            start_command_running: startProcess.running,
            x: position.x, y: position.y, width: width, height: height};
    }

    FileView {
        id: stateFile
        path: indicator.testState ? "" : indicator.statePath
        watchChanges: true
        printErrors: false
        onFileChanged: { reload(); refreshSoon.restart(); }
    }
    FileView {
        path: indicator.testState ? "" : Quickshell.env("XDG_RUNTIME_DIR")
            + "/labfy-removable-media.json"
        watchChanges: true
        printErrors: false
        // Le protocole des supports amovibles reste indépendant et inchangé.
        onFileChanged: { reload(); refreshSoon.restart(); }
    }
    Timer { id: refreshSoon; interval: 200; onTriggered: indicator.refresh() }
    Timer {
        interval: indicator.busy ? 1000 : 5000
        repeat: true
        running: !indicator.testState
        // 1 s pendant la copie/vérification, 5 s au repos pour limiter les processus.
        onTriggered: indicator.refresh()
    }
    Timer {
        id: statusDeadline
        interval: 4500
        onTriggered: if (statusProcess.running) statusProcess.running = false
    }
    Timer {
        id: startDeadline
        interval: 8000
        onTriggered: { indicator.startPending = false; indicator.refresh(); }
    }
    Process {
        id: statusProcess
        stdout: StdioCollector { id: statusOutput; waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: (code, exitStatus) => {
            statusDeadline.stop();
            try {
                if (code !== 0) throw new Error("Statut indisponible");
                const value = JSON.parse(statusOutput.text);
                if (!indicator.validState(value)) throw new Error("État invalide");
                indicator.backupData = value;
                indicator.statusReadable = true;
                if (indicator.busy) {
                    indicator.startPending = false;
                    startDeadline.stop();
                }
            } catch (_) { indicator.statusReadable = false; }
        }
    }
    Process {
        id: startProcess
        stdout: StdioCollector { waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: (code, exitStatus) => {
            if (code !== 0) {
                indicator.actionError = "Le démarrage de la sauvegarde a échoué.";
                indicator.startPending = false;
                startDeadline.stop();
            }
            refreshSoon.restart();
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
            text: "󰋊"
            font.pixelSize: 21
            color: indicator.hasError ? Theme.danger
                : indicator.busy || indicator.startPending ? Theme.warningForeground
                : indicator.backupData.phase === "success" ? Theme.successForeground
                : Theme.accentForeground
        }
        Text {
            visible: indicator.busy
            anchors.verticalCenter: parent.verticalCenter
            text: Math.floor(indicator.progress) + "%"
            color: Theme.secondaryForeground
            font.pixelSize: 9
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
        message: "Sauvegarde photos — " + indicator.statusLabel
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
        implicitWidth: 380
        implicitHeight: content.implicitHeight + 24
        Rectangle {
            anchors.fill: parent
            radius: 4
            color: Theme.popupBackground
            border.color: Theme.outline
            Column {
                id: content
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 12
                spacing: 10
                Text {
                    text: "Sauvegarde photos"
                    color: Theme.accentForeground
                    font.pixelSize: 16
                    font.bold: true
                }
                Text {
                    text: "Phototheque → PHOTO_BAK"
                    color: Theme.foreground
                    font.pixelSize: 13
                    font.bold: true
                }
                Text {
                    text: "Photos, RAW, XMP et catalogues"
                    color: Theme.secondaryForeground
                    font.pixelSize: 11
                }
                Text {
                    visible: indicator.usbSpeed > 0
                    text: "Liaison USB : " + (indicator.usbSpeed >= 1000
                        ? String(indicator.usbSpeed / 1000) + " Gbit/s"
                        : String(indicator.usbSpeed) + " Mbit/s")
                    color: indicator.usbSpeed < 5000 ? Theme.warningForeground
                        : Theme.secondaryForeground
                    font.pixelSize: 11
                }
                Text {
                    width: parent.width
                    text: indicator.statusLabel
                    color: indicator.hasError ? Theme.danger
                        : indicator.busy ? Theme.warningForeground : Theme.successForeground
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
                Rectangle {
                    visible: indicator.busy
                    width: parent.width
                    height: 5
                    radius: 2
                    color: Theme.border
                    Rectangle {
                        width: parent.width * indicator.progress / 100
                        height: parent.height
                        radius: 2
                        color: Theme.accent
                    }
                }
                Text {
                    visible: indicator.busy && indicator.backupData.total_bytes > 0
                    text: indicator.formatSize(indicator.backupData.progress_bytes) + " / "
                        + indicator.formatSize(indicator.backupData.total_bytes)
                        + " · " + Math.floor(indicator.progress) + "%"
                    color: Theme.secondaryForeground
                    font.pixelSize: 11
                }
                Text {
                    width: parent.width
                    text: indicator.lastSuccessLabel()
                    color: Theme.secondaryForeground
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
                Text {
                    visible: indicator.actionError.length > 0 || Boolean(indicator.backupData.error)
                    width: parent.width
                    text: indicator.actionError || indicator.backupData.error || ""
                    color: Theme.danger
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
                ActionButton {
                    label: indicator.busy ? "Sauvegarde en cours…" : "Sauvegarder maintenant"
                    enabled: indicator.canStart
                    onClicked: indicator.startBackup()
                }
                Text {
                    width: parent.width
                    text: "Les fichiers effacés sur le PC et les anciennes versions restent sur le SSD."
                    color: Theme.secondaryForeground
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
            }
        }
    }
}

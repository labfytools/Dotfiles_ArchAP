import QtQuick
import Quickshell
import Quickshell.Io
import "../components"
import "../controlcenter"
import "../theme"
import "StatusColorRoles.js" as StatusColorRoles

Item {
    id: indicator

    signal toggleRequested()
    property alias popupOpen: popup.visible
    readonly property string statePath: Quickshell.env("XDG_RUNTIME_DIR")
        + "/labfy-removable-media.json"
    readonly property string clientPath: (Quickshell.env("HOME") || "")
        + "/.local/bin/labfy-removable-mediactl"
    // TEST_ONLY: états visuels déterministes, activés uniquement par une variable
    // explicite dans le processus QuickShell ; le chemin de production reste le FileView.
    readonly property string testState: Quickshell.env("LABFY_REMOVABLE_MEDIA_TEST_STATE") || ""
    readonly property var devices: testState ? fakeDevices(testState) : readDevices()
    readonly property int deviceCount: devices.length
    readonly property bool hasBusyDevice: devices.some(device => device.busy)
    readonly property bool hasErrorDevice: devices.some(device => Boolean(device.error))
    readonly property var publicDeviceKeys: [
        "actions", "busy", "display_name", "ejectable", "error", "filesystem",
        "kind", "label", "mount_point", "mounted", "power_off_capable",
        "removable", "runtime_id", "safe_remove_runtime_id", "size_bytes"
    ]
    readonly property var allowedActions: ["mount", "unmount", "open", "safe-remove"]

    visible: deviceCount > 0
    width: visible ? 26 : 0
    height: 26

    onDeviceCountChanged: if (deviceCount === 0) popup.visible = false

    function hasExactKeys(device, expectedKeys) {
        const keys = Object.keys(device).sort();
        if (keys.length !== expectedKeys.length) return false;
        return keys.every((key, index) => key === expectedKeys[index]);
    }

    function validDevice(device) {
        return device !== null && typeof device === "object"
            // CONTRACT: la vue ne tolère aucune extension implicite du protocole
            // public, notamment une URI ou une identité matérielle MTP.
            && hasExactKeys(device, publicDeviceKeys)
            && typeof device.runtime_id === "string" && device.runtime_id.length > 0
            && typeof device.safe_remove_runtime_id === "string"
            && device.safe_remove_runtime_id.length > 0
            && (device.kind === "block" || device.kind === "mtp")
            && Array.isArray(device.actions)
            && device.actions.every((action, index) =>
                typeof action === "string"
                    && allowedActions.indexOf(action) !== -1
                    && device.actions.indexOf(action) === index)
            && typeof device.display_name === "string"
            && (device.label === null || typeof device.label === "string")
            && (device.filesystem === null || typeof device.filesystem === "string")
            && Number.isSafeInteger(device.size_bytes) && device.size_bytes >= 0
            && (device.mount_point === null || typeof device.mount_point === "string")
            && typeof device.mounted === "boolean"
            && typeof device.removable === "boolean"
            && typeof device.ejectable === "boolean"
            && typeof device.power_off_capable === "boolean"
            && typeof device.busy === "boolean"
            && (device.error === null || typeof device.error === "string");
    }

    function readDevices() {
        const raw = snapshot.text();
        if (!raw) return [];
        try {
            const value = JSON.parse(raw);
            // CONTRACT: ignorer intégralement un snapshot d'un autre protocole ou
            // partiellement écrit ; aucune commande ne doit viser ses identifiants.
            if (value === null || typeof value !== "object"
                    || !hasExactKeys(value, ["devices", "schema", "updated_at", "version"])
                    || value.schema !== "labfy.removable-media" || value.version !== 2
                    || !Array.isArray(value.devices) || !Number.isSafeInteger(value.updated_at)
                    || value.updated_at < 0
                    || !value.devices.every(validDevice))
                throw new Error("Snapshot incompatible");
            return value.devices;
        } catch (error) {
            console.warn("État des supports amovibles illisible :", error);
            return [];
        }
    }

    function fakeBlockDevice(busy, error) {
        return {
            runtime_id: "test-volume-usb",
            safe_remove_runtime_id: "test-drive-usb",
            kind: "block",
            actions: ["unmount", "open", "safe-remove"],
            display_name: "Clé USB de test",
            label: "LABFY",
            filesystem: "exfat",
            size_bytes: 64000000000,
            mount_point: "/run/media/test/LABFY",
            mounted: true,
            removable: true,
            ejectable: true,
            power_off_capable: false,
            busy: busy,
            error: error
        };
    }

    function fakeMtpDevice(busy, error) {
        return {
            runtime_id: "test-mtp-session",
            safe_remove_runtime_id: "test-mtp-session",
            kind: "mtp",
            actions: ["unmount", "open", "safe-remove"],
            display_name: "Stockage du téléphone",
            label: "Téléphone Android",
            filesystem: "mtp",
            size_bytes: 128000000000,
            mount_point: "/run/user/1000/gvfs/mtp:host=test",
            mounted: true,
            removable: true,
            ejectable: false,
            power_off_capable: false,
            busy: busy,
            error: error
        };
    }

    function fakeDevices(mode) {
        if (mode === "0") return [];
        if (mode === "USB") return [fakeBlockDevice(false, "")];
        if (mode === "MTP") return [fakeMtpDevice(false, "")];
        if (mode === "USB+MTP")
            return [fakeBlockDevice(false, ""), fakeMtpDevice(false, "")];
        if (mode === "busy") return [fakeMtpDevice(true, "")];
        if (mode === "error")
            return [fakeBlockDevice(false, "Le support nécessite une vérification.")];
        console.warn("LABFY_REMOVABLE_MEDIA_TEST_STATE inconnu :", mode);
        return [];
    }

    function hasAction(device, action) {
        return device.actions.indexOf(action) !== -1;
    }

    function formatSize(bytes) {
        if (bytes <= 0) return "Taille inconnue";
        const units = ["o", "Kio", "Mio", "Gio", "Tio"];
        let value = bytes;
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit++;
        }
        return (unit === 0 ? String(value) : value.toFixed(value >= 10 ? 0 : 1))
            + " " + units[unit];
    }

    function runAction(action, device) {
        // INVARIANT: les identifiants TEST_ONLY ne quittent jamais le renderer.
        if (testState || actionProcess.running || device.busy || !hasAction(device, action))
            return;
        let target = device.runtime_id;
        if (action === "safe-remove") target = device.safe_remove_runtime_id;
        // CONTRACT: le client est l'unique frontière de commande et reçoit un
        // argv direct. Les identifiants opaques ne traversent jamais un shell.
        actionProcess.command = [clientPath, action, target];
        actionProcess.running = true;
    }

    FileView {
        id: snapshot
        path: indicator.statePath
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
    }

    // WHY: le fichier peut être créé après QuickShell et son répertoire parent
    // existait déjà ; un watcher de fichier absent ne reçoit pas toujours la création.
    Timer {
        interval: 5000
        repeat: true
        running: !indicator.testState && !snapshot.loaded
        onTriggered: snapshot.reload()
    }

    Timer {
        id: refreshAfterAction
        interval: 250
        onTriggered: snapshot.reload()
    }

    Process {
        id: actionProcess
        stderr: StdioCollector { id: actionErrors; waitForEnd: true }
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0)
                console.warn("Action sur le support amovible échouée :",
                    actionErrors.text.trim() || ("code " + exitCode));
            refreshAfterAction.restart();
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: pointer.containsMouse || popup.visible ? Theme.border : "transparent"
    }

    NerdIcon {
        anchors.centerIn: parent
        text: indicator.hasBusyDevice || actionProcess.running ? "󰔟" : "󰕓"
        color: Theme[StatusColorRoles.removable(indicator.hasErrorDevice,
            indicator.hasBusyDevice || actionProcess.running)]
        font.pixelSize: 18
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        enabled: indicator.deviceCount > 0
        onClicked: indicator.toggleRequested()
    }

    StatusTooltip {
        target: indicator
        hovered: pointer.containsMouse && !popup.visible
        message: indicator.deviceCount + (indicator.deviceCount === 1
            ? " support amovible" : " supports amovibles")
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
        implicitHeight: Math.min(560, popupContent.implicitHeight + 24)

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
                contentHeight: popupContent.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: popupContent
                    width: parent.width
                    spacing: 10

                    Text {
                        width: parent.width
                        text: "Supports amovibles"
                        color: Theme.accentForeground
                        font.pixelSize: 16
                        font.bold: true
                    }

                    Repeater {
                        model: indicator.devices

                        Rectangle {
                            required property var modelData
                            width: popupContent.width
                            height: cardContent.implicitHeight + 20
                            radius: 5
                            color: Theme.buttonBackground
                            border.color: modelData.error ? Theme.danger : Theme.outline

                            Column {
                                id: cardContent
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 10
                                spacing: 5

                                Text {
                                    width: parent.width
                                    text: modelData.display_name || modelData.label || "Support amovible"
                                    color: Theme.foreground
                                    font.pixelSize: 14
                                    font.bold: true
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: modelData.kind === "mtp"
                                        ? "Appareil MTP • " + indicator.formatSize(modelData.size_bytes)
                                        : (modelData.label ? modelData.label + " • " : "")
                                            + (modelData.filesystem
                                                || "Système de fichiers inconnu")
                                            + " • " + indicator.formatSize(modelData.size_bytes)
                                    color: Theme.secondaryForeground
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: modelData.busy ? "Opération en cours…"
                                        : modelData.kind === "mtp" && modelData.mounted
                                            ? (modelData.mount_point
                                                ? "Connexion ouverte sur " + modelData.mount_point
                                                : "Connexion ouverte")
                                        : modelData.kind === "mtp" ? "Connexion fermée"
                                        : modelData.mounted ? "Monté sur " + modelData.mount_point
                                        : "Non monté"
                                    color: modelData.busy ? Theme.warningForeground
                                        : modelData.mounted ? Theme.successForeground
                                        : Theme.secondaryForeground
                                    font.pixelSize: 11
                                    elide: Text.ElideMiddle
                                }

                                Text {
                                    visible: modelData.kind === "mtp"
                                        && indicator.hasAction(modelData, "safe-remove")
                                    width: parent.width
                                    text: "Fermer la connexion déconnecte proprement l’appareil de cette session."
                                    color: Theme.secondaryForeground
                                    font.pixelSize: 11
                                    wrapMode: Text.Wrap
                                }

                                Text {
                                    visible: Boolean(modelData.error)
                                    width: parent.width
                                    text: modelData.error
                                    color: Theme.danger
                                    font.pixelSize: 11
                                    wrapMode: Text.Wrap
                                }

                                Flow {
                                    width: parent.width
                                    spacing: 6

                                    ActionButton {
                                        visible: indicator.hasAction(modelData, "open")
                                        label: "Ouvrir"
                                        enabled: !indicator.testState && !modelData.busy
                                            && !actionProcess.running
                                        onClicked: indicator.runAction("open", modelData)
                                    }
                                    ActionButton {
                                        visible: indicator.hasAction(modelData, "mount")
                                        label: "Monter"
                                        enabled: !indicator.testState && !modelData.busy
                                            && !actionProcess.running
                                        onClicked: indicator.runAction("mount", modelData)
                                    }
                                    ActionButton {
                                        visible: indicator.hasAction(modelData, "unmount")
                                        label: "Démonter"
                                        enabled: !indicator.testState && !modelData.busy
                                            && !actionProcess.running
                                        onClicked: indicator.runAction("unmount", modelData)
                                    }
                                    ActionButton {
                                        visible: indicator.hasAction(modelData, "safe-remove")
                                        label: modelData.kind === "mtp"
                                            ? "Fermer la connexion" : "Retirer en sécurité"
                                        enabled: !indicator.testState && !modelData.busy
                                            && !actionProcess.running
                                        onClicked: indicator.runAction("safe-remove", modelData)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Bluetooth
import "../components"

Item {
    id: page
    required property var adapter
    required property bool activePage
    signal backRequested()
    property var scanOwnedAdapter: null
    property string stage: "main" // main, details, forget, block
    property string selectedAddress: ""
    property string message: ""
    readonly property var devices: adapter && adapter.devices ? adapter.devices.values : []
    readonly property var connectedDevices: devices.filter(d => d.connected)
    readonly property var pairedDevices: devices.filter(d => !d.connected && d.paired)
    readonly property var newDevices: devices.filter(d => !d.connected && !d.paired)
    readonly property var selectedDevice: devices.find(d => d.address === selectedAddress) || null
    readonly property bool scanWanted: activePage && adapter !== null && adapter.enabled

    // CONTRACT: l'adaptateur revient à son état initial si ce panneau a lancé la découverte.
    function syncScan() {
        if (scanOwnedAdapter && (!scanWanted || scanOwnedAdapter !== adapter)) {
            scanOwnedAdapter.discovering = false;
            scanOwnedAdapter = null;
        }
        if (scanWanted && !adapter.discovering) {
            adapter.discovering = true;
            scanOwnedAdapter = adapter;
        }
    }
    onScanWantedChanged: syncScan()
    onAdapterChanged: syncScan()
    onActivePageChanged: if (!activePage) { stage = "main"; selectedAddress = ""; message = ""; }
    Component.onDestruction: if (scanOwnedAdapter) scanOwnedAdapter.discovering = false

    function nameOf(device) { return device ? (device.name || device.deviceName || "Appareil Bluetooth") : "Appareil indisponible"; }
    function stateOf(device) {
        if (!device) return "Indisponible";
        if (device.pairing) return "Appairage…";
        if (device.state === BluetoothDeviceState.Connecting) return "Connexion…";
        if (device.state === BluetoothDeviceState.Disconnecting) return "Déconnexion…";
        if (device.connected) return "Connecté";
        return device.paired ? "Appairé • déconnecté" : "Non appairé";
    }
    function choose(device) { selectedAddress = device.address; message = ""; stage = "details"; }
    function back() {
        if (stage === "main") backRequested();
        else if (stage === "forget" || stage === "block") stage = "details";
        else stage = "main";
        message = "";
    }

    Column {
        anchors.fill: parent; spacing: 10
        Row {
            width: parent.width; height: 30; spacing: 8
            ActionButton { label: ""; onClicked: page.back() }
            Text {
                width: parent.width - 60; height: 30; verticalAlignment: Text.AlignVCenter
                text: page.stage === "main" ? "Bluetooth" : page.nameOf(page.selectedDevice)
                color: "#cdd6f4"; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight
            }
        }
        Text { width: parent.width; visible: page.message.length > 0; text: page.message; wrapMode: Text.Wrap; color: "#f9e2af"; font.pixelSize: 12 }
        Loader {
            width: parent.width; height: Math.max(0, parent.height - y)
            sourceComponent: page.stage === "main" ? mainComponent : page.stage === "details"
                ? detailsComponent : page.stage === "forget" ? forgetComponent : blockComponent
        }
    }

    Component {
        id: mainComponent
        ScrollView {
            clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: page.width; spacing: 10
                Row {
                    width: parent.width; spacing: 8
                    Text { width: parent.width - 100; text: !page.adapter ? "Adaptateur indisponible" : page.adapter.enabled ? "Bluetooth activé" : "Bluetooth désactivé"; color: "#cdd6f4"; font.pixelSize: 13 }
                    ActionButton { label: page.adapter && page.adapter.enabled ? "Désactiver" : "Activer"; enabled: !!page.adapter; onClicked: page.adapter.enabled = !page.adapter.enabled }
                }
                Text { text: page.scanWanted ? "Recherche d'appareils…" : "Scan arrêté"; color: "#a6adc8"; font.pixelSize: 11 }
                Text { visible: page.devices.length === 0; text: "Aucun appareil connu"; color: "#a6adc8"; font.pixelSize: 12 }
                Text { visible: page.connectedDevices.length > 0; text: "Connectés"; color: "#cba6f7"; font.bold: true; font.pixelSize: 13 }
                Repeater {
                    model: ScriptModel { values: page.connectedDevices; objectProp: "address" }
                    delegate: deviceRowComponent
                }
                Text { visible: page.pairedDevices.length > 0; text: "Appairés"; color: "#cba6f7"; font.bold: true; font.pixelSize: 13 }
                Repeater {
                    model: ScriptModel { values: page.pairedDevices; objectProp: "address" }
                    delegate: deviceRowComponent
                }
                Text { visible: page.newDevices.length > 0; text: "Nouveaux appareils"; color: "#cba6f7"; font.bold: true; font.pixelSize: 13 }
                Repeater {
                    model: ScriptModel { values: page.newDevices; objectProp: "address" }
                    delegate: deviceRowComponent
                }
            }
        }
    }
    Component {
        id: deviceRowComponent
        Rectangle {
            required property var modelData
            readonly property var device: modelData
            width: page.width; height: 48; radius: 4
            color: pointer.containsMouse ? "#45475a" : "#313244"
            Image {
                id: iconImage; anchors.left: parent.left; anchors.leftMargin: 9; anchors.verticalCenter: parent.verticalCenter
                width: 19; height: 19; source: device.icon ? Quickshell.iconPath(device.icon, true) : ""
                visible: status === Image.Ready; fillMode: Image.PreserveAspectFit
            }
            NerdIcon {
                anchors.centerIn: iconImage; visible: !iconImage.visible
                text: "󰂯"; color: "#cba6f7"; font.pixelSize: 17
            }
            Column {
                anchors.left: parent.left; anchors.leftMargin: 38; anchors.right: parent.right
                anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                Text { width: parent.width; text: page.nameOf(device); color: "#cdd6f4"; font.pixelSize: 12; elide: Text.ElideRight }
                Text { text: page.stateOf(device) + (device.batteryAvailable ? " • " + Math.round(device.battery * 100) + " %" : ""); color: "#a6adc8"; font.pixelSize: 11 }
            }
            MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; onClicked: page.choose(device) }
        }
    }
    Component {
        id: detailsComponent
        ScrollView {
            clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: page.width; spacing: 10
                Text { text: page.selectedDevice ? page.stateOf(page.selectedDevice) : "Appareil indisponible"; color: "#cdd6f4"; font.pixelSize: 13 }
                Text { visible: !!page.selectedDevice && page.selectedDevice.deviceName !== page.selectedDevice.name; text: "Nom d'origine : " + (page.selectedDevice ? page.selectedDevice.deviceName : ""); color: "#a6adc8"; font.pixelSize: 11 }
                Text { visible: !!page.selectedDevice && page.selectedDevice.batteryAvailable; text: "Batterie : " + (page.selectedDevice ? Math.round(page.selectedDevice.battery * 100) : 0) + " %"; color: "#cdd6f4"; font.pixelSize: 12 }
                Text { text: page.selectedDevice ? "Appairé : " + (page.selectedDevice.paired ? "oui" : "non") + " • Lié : " + (page.selectedDevice.bonded ? "oui" : "non") : ""; color: "#a6adc8"; font.pixelSize: 11 }
                Row {
                    spacing: 8
                    ActionButton {
                        label: page.selectedDevice && page.selectedDevice.pairing ? "Annuler l'appairage"
                            : page.selectedDevice && !page.selectedDevice.paired ? "Appairer"
                            : page.selectedDevice && page.selectedDevice.connected ? "Déconnecter" : "Connecter"
                        enabled: !!page.selectedDevice && (page.selectedDevice.pairing
                            || (page.selectedDevice.state !== BluetoothDeviceState.Connecting
                                && page.selectedDevice.state !== BluetoothDeviceState.Disconnecting))
                        onClicked: {
                            const device = page.selectedDevice;
                            if (device.pairing) device.cancelPair();
                            else if (!device.paired) device.pair();
                            else if (device.connected) device.disconnect();
                            else device.connect();
                        }
                    }
                    ActionButton { label: "Oublier"; danger: true; visible: !!page.selectedDevice && page.selectedDevice.paired; onClicked: page.stage = "forget" }
                }
                Row {
                    spacing: 8
                    Text { width: 165; text: "Appareil de confiance"; color: "#cdd6f4"; font.pixelSize: 12 }
                    ActionButton { label: page.selectedDevice && page.selectedDevice.trusted ? "Activé" : "Désactivé"; enabled: !!page.selectedDevice && page.selectedDevice.paired; onClicked: page.selectedDevice.trusted = !page.selectedDevice.trusted }
                }
                Row {
                    spacing: 8
                    Text { width: 165; text: "Bloqué"; color: "#cdd6f4"; font.pixelSize: 12 }
                    ActionButton { label: page.selectedDevice && page.selectedDevice.blocked ? "Oui" : "Non"; enabled: !!page.selectedDevice; onClicked: { if (page.selectedDevice.blocked) page.selectedDevice.blocked = false; else page.stage = "block"; } }
                }
                Text { width: parent.width; wrapMode: Text.Wrap; text: "Un appareil bloqué ne peut pas se connecter."; color: "#a6adc8"; font.pixelSize: 11 }
                Row {
                    visible: !!page.selectedDevice && page.selectedDevice.paired
                        && page.adapter && page.adapter.enabled
                        && page.selectedDevice.wakeAllowed !== undefined
                    spacing: 8
                    Text { width: 165; text: "Autoriser le réveil"; color: "#cdd6f4"; font.pixelSize: 12 }
                    ActionButton { label: page.selectedDevice && page.selectedDevice.wakeAllowed ? "Activé" : "Désactivé"; onClicked: page.selectedDevice.wakeAllowed = !page.selectedDevice.wakeAllowed }
                }
                Text { text: "Nom local"; color: "#cba6f7"; font.pixelSize: 13; font.bold: true }
                TextField {
                    id: aliasInput; width: page.width
                    text: page.selectedDevice ? page.selectedDevice.name : ""
                    placeholderText: "Alias local"; selectByMouse: true
                    color: "#cdd6f4"; placeholderTextColor: "#6c7086"
                    background: Rectangle { color: "#313244"; border.color: aliasInput.activeFocus ? "#cba6f7" : "#585b70"; radius: 4 }
                }
                Row {
                    spacing: 8
                    ActionButton { label: "Réinitialiser"; enabled: !!page.selectedDevice; onClicked: { page.selectedDevice.name = ""; aliasInput.text = page.selectedDevice.name; } }
                    ActionButton { label: "Enregistrer"; enabled: !!page.selectedDevice; onClicked: page.selectedDevice.name = aliasInput.text.trim() }
                }
                Text { text: "Informations techniques : " + (page.selectedDevice ? page.selectedDevice.address : ""); color: "#6c7086"; font.pixelSize: 10 }
            }
        }
    }
    Component {
        id: forgetComponent
        Column {
            spacing: 10
            Text { width: page.width; wrapMode: Text.Wrap; text: "Oublier " + page.nameOf(page.selectedDevice) + " ?"; color: "#f38ba8"; font.pixelSize: 13 }
            Text { width: page.width; wrapMode: Text.Wrap; text: "Cela supprimera les informations de pairage."; color: "#a6adc8"; font.pixelSize: 12 }
            Row {
                spacing: 8
                ActionButton { label: "Annuler"; onClicked: page.stage = "details" }
                ActionButton { label: "Oublier"; danger: true; onClicked: { if (page.selectedDevice) page.selectedDevice.forget(); page.stage = "main"; } }
            }
        }
    }
    Component {
        id: blockComponent
        Column {
            spacing: 10
            Text { width: page.width; wrapMode: Text.Wrap; text: "Bloquer " + page.nameOf(page.selectedDevice) + " ?"; color: "#f38ba8"; font.pixelSize: 13 }
            Text { width: page.width; wrapMode: Text.Wrap; text: "Un appareil bloqué ne peut pas se connecter."; color: "#a6adc8"; font.pixelSize: 12 }
            Row {
                spacing: 8
                ActionButton { label: "Annuler"; onClicked: page.stage = "details" }
                ActionButton { label: "Bloquer"; danger: true; onClicked: { if (page.selectedDevice) page.selectedDevice.blocked = true; page.stage = "details"; } }
            }
        }
    }
}

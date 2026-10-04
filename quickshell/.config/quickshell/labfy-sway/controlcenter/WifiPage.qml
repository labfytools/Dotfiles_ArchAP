import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Networking
import "../components"

Item {
    id: page
    required property var wifiDevice
    required property bool activePage
    signal backRequested()
    property var scanOwnedDevice: null
    property string stage: "main" // main, details, password, forget
    property string selectedName: ""
    property int selectedProfile: -1
    property string message: ""
    readonly property bool passwordOpen: stage === "password" && activePage
    readonly property bool scanWanted: activePage && Networking.wifiEnabled
        && Networking.wifiHardwareEnabled && wifiDevice !== null
    readonly property var sortedNetworks: {
        if (!wifiDevice || !wifiDevice.networks) return [];
        const networks = wifiDevice.networks.values.slice();
        networks.sort((a, b) => {
            const group = network => network.connected ? 0 : network.known ? 1 : 2;
            return group(a) - group(b) || b.signalStrength - a.signalStrength
                || a.name.localeCompare(b.name);
        });
        const names = new Set();
        return networks.filter(network => {
            if (!network.name || names.has(network.name)) return false;
            names.add(network.name);
            return true;
        });
    }
    readonly property var currentNetwork: sortedNetworks.find(n => n.connected) || null
    readonly property var selectedNetwork: sortedNetworks.find(n => n.name === selectedName) || null
    readonly property var profiles: selectedNetwork && selectedNetwork.nmSettings
        ? selectedNetwork.nmSettings : []

    // CONTRACT: ne rendre au repos que le scan que cette page a lancé.
    function syncScan() {
        if (scanOwnedDevice && (!scanWanted || scanOwnedDevice !== wifiDevice)) {
            scanOwnedDevice.scannerEnabled = false;
            scanOwnedDevice = null;
        }
        if (scanWanted && !wifiDevice.scannerEnabled) {
            wifiDevice.scannerEnabled = true;
            scanOwnedDevice = wifiDevice;
        }
    }
    onScanWantedChanged: syncScan()
    onWifiDeviceChanged: syncScan()
    onActivePageChanged: if (!activePage) { stage = "main"; selectedName = ""; message = ""; }
    Component.onDestruction: if (scanOwnedDevice) scanOwnedDevice.scannerEnabled = false

    function securityLabel(network) {
        if (!network) return "";
        switch (network.security) {
        case WifiSecurityType.Open: return "Ouvert";
        case WifiSecurityType.WpaPsk: return "WPA";
        case WifiSecurityType.Wpa2Psk: return "WPA2";
        case WifiSecurityType.Sae: return "WPA3 SAE";
        case WifiSecurityType.WpaEap: case WifiSecurityType.Wpa2Eap: return "Entreprise";
        default: return WifiSecurityType.toString(network.security);
        }
    }
    function pskSupported(network) {
        return network && (network.security === WifiSecurityType.WpaPsk
            || network.security === WifiSecurityType.Wpa2Psk
            || network.security === WifiSecurityType.Sae);
    }
    function stateLabel(network) {
        return network.stateChanging ? (network.state === ConnectionState.Disconnecting
            ? "Déconnexion…" : "Connexion…") : network.connected ? "Connecté"
            : network.known ? "Connu" : "Disponible";
    }
    function failureLabel(reason) {
        switch (reason) {
        case ConnectionFailReason.NoSecrets: return "Secret absent ou incorrect";
        case ConnectionFailReason.WifiAuthTimeout: return "Délai d'authentification dépassé";
        case ConnectionFailReason.WifiNetworkLost: return "Réseau disparu";
        case ConnectionFailReason.WifiClientDisconnected: return "Connexion annulée";
        case ConnectionFailReason.WifiClientFailed: return "Connexion échouée";
        default: return "Échec de connexion";
        }
    }
    function choose(network) { selectedName = network.name; selectedProfile = -1; message = ""; stage = "details"; }
    function connectSelected() {
        const network = selectedNetwork;
        if (!network || network.stateChanging || network.connected) return;
        message = "";
        if (!Networking.wifiEnabled || !Networking.wifiHardwareEnabled) {
            message = "Radio Wi-Fi désactivée ou bloquée"; return;
        }
        if (network.known || network.security === WifiSecurityType.Open) network.connect();
        else if (pskSupported(network)) stage = "password";
        else message = "Configuration avancée requise";
    }
    function back() {
        if (stage === "main") backRequested();
        else if (stage === "password" || stage === "forget") {
            if (stage === "password" && body.item && body.item.passwordInput)
                body.item.passwordInput.clear();
            stage = "details";
        }
        else stage = "main";
        message = "";
    }
    Connections {
        target: page.selectedNetwork
        function onConnectionFailed(reason) { page.message = page.failureLabel(reason); page.stage = "details"; }
    }

    Column {
        anchors.fill: parent
        spacing: 10
        Row {
            width: parent.width; height: 30; spacing: 8
            ActionButton { label: ""; onClicked: page.back() }
            Text {
                width: parent.width - 100; height: 30; verticalAlignment: Text.AlignVCenter
                text: page.stage === "main" ? "Wi-Fi" : page.stage === "password"
                    ? "Se connecter à " + page.selectedName : page.stage === "forget"
                    ? "Oublier un réseau" : page.selectedName
                color: "#cdd6f4"; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight
            }
        }
        Text {
            width: parent.width; visible: page.message.length > 0
            text: page.message; wrapMode: Text.Wrap; color: "#f9e2af"; font.pixelSize: 12
        }
        Loader {
            id: body
            width: parent.width; height: Math.max(0, parent.height - y)
            sourceComponent: page.stage === "main" ? mainComponent : page.stage === "details"
                ? detailsComponent : page.stage === "password" ? passwordComponent : forgetComponent
            onLoaded: if (page.stage === "password" && item && item.passwordInput)
                Qt.callLater(() => { if (body.item && body.item.passwordInput) body.item.passwordInput.forceActiveFocus(); })
        }
    }

    Component {
        id: mainComponent
        ScrollView {
            clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: page.width; spacing: 9
                Row {
                    width: parent.width; spacing: 8
                    Text { width: parent.width - 100; text: "Wi-Fi " + (Networking.wifiEnabled ? "activé" : "désactivé"); color: "#cdd6f4"; font.pixelSize: 13 }
                    ActionButton {
                        label: Networking.wifiEnabled ? "Désactiver" : "Activer"
                        enabled: Networking.wifiHardwareEnabled
                        onClicked: Networking.wifiEnabled = !Networking.wifiEnabled
                    }
                }
                Text { text: page.scanWanted ? "Recherche de réseaux…" : "Scan arrêté"; color: "#a6adc8"; font.pixelSize: 11 }
                Text { text: "Réseau actuel"; color: "#cba6f7"; font.bold: true; font.pixelSize: 13 }
                Rectangle {
                    width: parent.width; height: 66; radius: 4; color: "#313244"
                    Text {
                        anchors.left: parent.left; anchors.leftMargin: 10; anchors.top: parent.top; anchors.topMargin: 8
                        text: page.currentNetwork ? page.currentNetwork.name : "Aucun réseau connecté"
                        color: "#cdd6f4"; font.pixelSize: 13; font.bold: true
                    }
                    Text {
                        anchors.left: parent.left; anchors.leftMargin: 10; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
                        text: page.currentNetwork ? page.securityLabel(page.currentNetwork) + " • "
                            + Math.round(page.currentNetwork.signalStrength * 100) + " %" : ""
                        color: "#a6adc8"; font.pixelSize: 11
                    }
                    ActionButton {
                        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                        label: "Détails"; visible: !!page.currentNetwork
                        onClicked: page.choose(page.currentNetwork)
                    }
                }
                Text { text: "Réseaux disponibles"; color: "#cba6f7"; font.bold: true; font.pixelSize: 13 }
                Text {
                    visible: page.sortedNetworks.length === 0
                    text: !Networking.wifiHardwareEnabled ? "Wi-Fi bloqué matériellement" : "Aucun réseau visible"
                    color: "#a6adc8"; font.pixelSize: 12
                }
                Repeater {
                    model: ScriptModel { values: page.sortedNetworks; objectProp: "name" }
                    delegate: Rectangle {
                        required property var modelData
                        readonly property var network: modelData
                        width: page.width; height: 44; radius: 4
                        color: pointer.containsMouse ? "#45475a" : "#313244"
                        NerdIcon {
                            anchors.left: parent.left; anchors.leftMargin: 9; anchors.verticalCenter: parent.verticalCenter
                            text: network.connected ? "" : network.security === WifiSecurityType.Open ? "󰖩" : ""
                            color: network.connected ? "#a6e3a1" : "#cdd6f4"; font.pixelSize: 16
                        }
                        Text {
                            anchors.left: parent.left; anchors.leftMargin: 37; anchors.right: strength.left
                            anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            text: network.name + " • " + page.stateLabel(network)
                            color: "#cdd6f4"; font.pixelSize: 12; elide: Text.ElideRight
                        }
                        Text {
                            id: strength; anchors.right: parent.right; anchors.rightMargin: 9
                            anchors.verticalCenter: parent.verticalCenter
                            text: Math.round(network.signalStrength * 100) + "%"
                            color: "#a6adc8"; font.pixelSize: 11
                        }
                        MouseArea {
                            id: pointer; anchors.fill: parent; hoverEnabled: true
                            onClicked: {
                                page.choose(network);
                                if (network.known && !network.connected && !network.stateChanging)
                                    page.connectSelected();
                            }
                        }
                    }
                }
                Text { text: "Réseaux enregistrés visibles"; color: "#cba6f7"; font.bold: true; font.pixelSize: 13 }
                Repeater {
                    model: ScriptModel { values: page.sortedNetworks.filter(n => n.known); objectProp: "name" }
                    delegate: ActionButton {
                        required property var modelData
                        label: modelData.name + "  •  " + (modelData.nmSettings ? modelData.nmSettings.length : 0) + " profil(s)"
                        onClicked: page.choose(modelData)
                    }
                }
            }
        }
    }
    Component {
        id: detailsComponent
        ScrollView {
            clip: true; ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: page.width; spacing: 10
                Text { text: page.selectedNetwork ? page.stateLabel(page.selectedNetwork) + " • " + page.securityLabel(page.selectedNetwork) + " • " + Math.round(page.selectedNetwork.signalStrength * 100) + " %" : "Réseau indisponible"; color: "#cdd6f4"; font.pixelSize: 13 }
                Row {
                    spacing: 8
                    ActionButton {
                        label: page.selectedNetwork && page.selectedNetwork.connected ? "Déconnecter" : "Se connecter"
                        enabled: !!page.selectedNetwork && !page.selectedNetwork.stateChanging
                        onClicked: {
                            if (page.selectedNetwork.connected) page.selectedNetwork.disconnect();
                            else page.connectSelected();
                        }
                    }
                    ActionButton {
                        label: "Oublier"; danger: true
                        visible: !!page.selectedNetwork && page.selectedNetwork.known
                        onClicked: { page.selectedProfile = -1; page.stage = "forget"; }
                    }
                }
                Text { text: "Profils NetworkManager"; color: "#cba6f7"; font.pixelSize: 13; font.bold: true }
                Text { visible: page.profiles.length === 0; text: "Aucun profil enregistré"; color: "#a6adc8"; font.pixelSize: 12 }
                Repeater {
                    model: page.profiles
                    delegate: Row {
                        required property var modelData
                        required property int index
                        spacing: 6
                        Text { width: 205; text: modelData.id + "\n" + modelData.uuid; color: "#cdd6f4"; font.pixelSize: 11; wrapMode: Text.WrapAnywhere }
                        ActionButton { label: "Utiliser"; onClicked: { page.message = ""; page.selectedNetwork.connectWithSettings(modelData); } }
                        ActionButton { label: "Oublier"; danger: true; onClicked: { page.selectedProfile = index; page.stage = "forget"; } }
                    }
                }
            }
        }
    }
    Component {
        id: passwordComponent
        Column {
            property alias passwordInput: input
            spacing: 10
            Text { text: "Mot de passe"; color: "#cdd6f4"; font.pixelSize: 13 }
            TextField {
                id: input; width: page.width; echoMode: TextInput.Password
                placeholderText: "Mot de passe Wi-Fi"; selectByMouse: true
                color: "#cdd6f4"; placeholderTextColor: "#6c7086"
                background: Rectangle { color: "#313244"; border.color: input.activeFocus ? "#cba6f7" : "#585b70"; radius: 4 }
                onAccepted: submit.clicked()
            }
            Row {
                spacing: 8
                ActionButton { label: "Annuler"; onClicked: { input.clear(); page.stage = "details"; } }
                ActionButton {
                    id: submit; label: "Se connecter"
                    onClicked: {
                        // CONTRACT: le secret ne quitte ce champ que pour l'appel natif NM ; jamais de log ni de fichier.
                        const secret = input.text;
                        input.clear();
                        if (!(secret.length >= 8 && secret.length <= 63) && !/^[0-9a-fA-F]{64}$/.test(secret)) {
                            page.message = "Mot de passe : 8–63 caractères ou 64 chiffres hexadécimaux";
                            return;
                        }
                        if (page.selectedNetwork) page.selectedNetwork.connectWithPsk(secret);
                        page.stage = "details";
                    }
                }
            }
        }
    }
    Component {
        id: forgetComponent
        Column {
            spacing: 10
            Text { width: page.width; wrapMode: Text.Wrap; text: "Oublier " + page.selectedName + " ?"; color: "#f38ba8"; font.pixelSize: 13 }
            Text { width: page.width; wrapMode: Text.Wrap; text: page.selectedProfile >= 0 ? "Seul le profil sélectionné sera supprimé." : "Tous les profils de ce réseau seront supprimés."; color: "#a6adc8"; font.pixelSize: 12 }
            Row {
                spacing: 8
                ActionButton { label: "Annuler"; onClicked: page.stage = "details" }
                ActionButton { label: "Oublier"; danger: true; onClicked: {
                    if (page.selectedProfile >= 0 && page.selectedProfile < page.profiles.length)
                        page.profiles[page.selectedProfile].forget();
                    else if (page.selectedNetwork) page.selectedNetwork.forget();
                    page.stage = "main";
                } }
            }
        }
    }
}

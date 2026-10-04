import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.I3
import Quickshell.Networking
import Quickshell.Bluetooth
import "../components"

PopupWindow {
    id: popup

    required property var barWindow
    property int currentPage: 0 // 0 = MAIN, 1 = Wi-Fi, 2 = Bluetooth, 3 = Session, 4 = confirmation, 5 = Batterie.
    signal thresholdApplied()
    property var pendingAction: null
    // Une seule table associe les libellés, confirmations et commandes de session.
    readonly property var sessionActions: [
        { id: "lock", label: "Verrouiller", icon: "", accent: "#b4befe", command: ["swaylock"] },
        { id: "suspend", label: "Veille", icon: "", accent: "#b4befe",
            confirmTitle: "Mettre l'ordinateur en veille ?",
            description: "La session sera verrouillée avant la veille.",
            command: ["systemctl", "suspend"] },
        { id: "logout", label: "Déconnexion", icon: "", accent: "#fab387",
            confirmTitle: "Se déconnecter ?",
            description: "La session SwayFX en cours sera fermée.", command: null },
        { id: "reboot", label: "Redémarrer", icon: "", accent: "#f9e2af",
            confirmTitle: "Redémarrer l'ordinateur ?",
            description: "La session en cours sera fermée.",
            command: ["systemctl", "reboot"] },
        { id: "poweroff", label: "Éteindre", icon: "", accent: "#f38ba8",
            confirmTitle: "Éteindre l'ordinateur ?",
            description: "La session en cours sera fermée.",
            command: ["systemctl", "poweroff"] }
    ]
    readonly property var wifiDevice: Networking.devices.values.find(device => device.type === DeviceType.Wifi) || null
    readonly property var adapter: Bluetooth.defaultAdapter

    // Une nouvelle ouverture recommence sur MAIN ; les pages libèrent leurs scans à la fermeture.
    onVisibleChanged: if (!visible) {
        currentPage = 0;
        pendingAction = null;
    }

    function requestSessionAction(id) {
        const selected = sessionActions.find(item => item.id === id);
        if (!selected) return;
        if (id === "lock") {
            executeSessionAction(id);
            return;
        }
        pendingAction = selected;
        currentPage = 4;
    }

    function executeSessionAction(id) {
        const selected = sessionActions.find(item => item.id === id);
        if (!selected) return;
        // Fermer le popup avant toute commande qui peut verrouiller ou terminer la session.
        visible = false;
        if (id === "logout") I3.dispatch("exit");
        else Quickshell.execDetached(selected.command);
    }

    anchor.window: barWindow
    anchor.rect.x: barWindow.width - implicitWidth - 8
    anchor.rect.y: barWindow.height + 6
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right

    implicitWidth: 400
    implicitHeight: currentPage === 0 ? mainPage.implicitHeight + 32
        : currentPage === 3 ? sessionPage.implicitHeight + 32
        : currentPage === 4 ? confirmationPage.implicitHeight + 32
        : currentPage === 5 ? batteryPage.implicitHeight + 32 : 440
    visible: false
    // CONTRACT: PopupWindow n'applique un changement de grabFocus qu'après
    // fermeture/réouverture ; le prendre dès MAIN garde le clavier disponible
    // pour le mot de passe Wi-Fi et l'alias Bluetooth après navigation interne.
    grabFocus: true
    color: "transparent"

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: "#1e1e2e"
        border.color: "#45475a"

        StackLayout {
            anchors.fill: parent
            anchors.margins: 16
            currentIndex: popup.currentPage

            Column {
                id: mainPage
                spacing: 18

                Text {
                    text: "Réglages rapides"
                    color: "#cdd6f4"
                    font.pixelSize: 16
                    font.bold: true
                }

                Row {
                    width: parent.width
                    spacing: 8

                    WifiTile {
                        width: (parent.width - parent.spacing) / 2
                        wifiDevice: popup.wifiDevice
                        onDetailsRequested: popup.currentPage = 1
                    }
                    BluetoothTile {
                        width: (parent.width - parent.spacing) / 2
                        adapter: popup.adapter
                        onDetailsRequested: popup.currentPage = 2
                    }
                }

                VolumeSlider { width: parent.width }
                BrightnessSlider { width: parent.width }
                PowerProfile { width: parent.width }

                Item {
                    width: parent.width
                    height: 30

                    Rectangle {
                        anchors.right: parent.right
                        width: 40
                        height: 30
                        radius: 4
                        color: powerPointer.containsMouse ? "#45475a" : "#313244"

                        NerdIcon {
                            anchors.centerIn: parent
                            text: ""
                        }
                        MouseArea {
                            id: powerPointer
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton
                            onClicked: popup.currentPage = 3
                        }
                    }
                }
            }

            WifiPage {
                id: wifiPage
                wifiDevice: popup.wifiDevice
                activePage: popup.visible && popup.currentPage === 1
                onBackRequested: popup.currentPage = 0
            }

            BluetoothPage {
                id: bluetoothPage
                adapter: popup.adapter
                activePage: popup.visible && popup.currentPage === 2
                onBackRequested: popup.currentPage = 0
            }

            SessionPage {
                id: sessionPage
                actions: popup.sessionActions
                onBackRequested: popup.currentPage = 0
                onActionRequested: id => popup.requestSessionAction(id)
            }

            ConfirmAction {
                id: confirmationPage
                actionInfo: popup.pendingAction || ({ id: "", label: "", confirmTitle: "",
                    description: "", accent: "#cdd6f4" })
                onCancelled: {
                    popup.pendingAction = null;
                    popup.currentPage = 3;
                }
                onConfirmed: id => {
                    if (popup.pendingAction && popup.pendingAction.id === id)
                        popup.executeSessionAction(id);
                }
            }

            BatterySettings {
                id: batteryPage
                activePage: popup.visible && popup.currentPage === 5
                onBackRequested: popup.currentPage = 0
                onThresholdApplied: popup.thresholdApplied()
            }
        }
    }
}

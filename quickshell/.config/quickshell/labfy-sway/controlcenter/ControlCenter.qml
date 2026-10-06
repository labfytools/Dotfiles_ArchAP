import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Networking
import Quickshell.Bluetooth
import "../components"
import "../theme"

PopupWindow {
    id: popup

    required property var barWindow
    // CONTRACT: indices externes historiques conservés ; tout nouveau routage
    // passe par ces noms afin de ne pas multiplier les indices StackLayout.
    readonly property var pages: ({ main: 0, wifi: 1, bluetooth: 2, session: 3,
        confirmation: 4, battery: 5, appearance: 6, wallpaper: 7, theme: 8,
        nightLight: 9, sunMode: 10, locationTime: 11, sessionManager: 12 })
    property int currentPage: pages.main
    function openPage(name) { if (pages[name] !== undefined) currentPage = pages[name]; }
    signal thresholdApplied()
    property var pendingAction: null
    // Une seule table associe les libellés, confirmations et commandes de session.
    readonly property var sessionActions: [
        { id: "lock", label: "Verrouiller", icon: "", accent: Theme.accent, command: ["swaylock"] },
        { id: "suspend", label: "Veille", icon: "", accent: Theme.accent,
            confirmTitle: "Mettre l'ordinateur en veille ?",
            description: "La session sera verrouillée avant la veille.",
            command: ["systemctl", "suspend"] },
        { id: "logout", label: "Déconnexion", icon: "", accent: Theme.urgent,
            confirmTitle: "Se déconnecter ?",
            description: "La session SwayFX en cours sera fermée.",
            command: ["uwsm", "stop"] },
        { id: "reboot", label: "Redémarrer", icon: "", accent: Theme.warning,
            confirmTitle: "Redémarrer l'ordinateur ?",
            description: "La session en cours sera fermée.",
            command: ["systemctl", "reboot"] },
        { id: "poweroff", label: "Éteindre", icon: "", accent: Theme.danger,
            confirmTitle: "Éteindre l'ordinateur ?",
            description: "La session en cours sera fermée.",
            command: ["systemctl", "poweroff"] }
    ]
    readonly property var wifiDevice: Networking.devices.values.find(device => device.type === DeviceType.Wifi) || null
    readonly property var adapter: Bluetooth.defaultAdapter

    // Une nouvelle ouverture recommence sur MAIN ; les pages libèrent leurs scans à la fermeture.
    onVisibleChanged: if (!visible) {
        openPage("main");
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
        openPage("confirmation");
    }

    function executeSessionAction(id) {
        const selected = sessionActions.find(item => item.id === id);
        if (!selected) return;
        // Fermer le popup avant toute commande qui peut verrouiller ou terminer la session.
        visible = false;
        // CONTRACT: UWSM possède le cycle de vie de Sway ; son arrêt doit donc
        // passer par la commande déclarée, comme les autres actions de session.
        if (selected.command) Quickshell.execDetached(selected.command);
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
        : currentPage === 5 ? batteryPage.implicitHeight + 32
        : currentPage === pages.wallpaper ? 550
        : currentPage === pages.appearance ? 520
        : currentPage === pages.locationTime || currentPage === pages.sessionManager ? 650 : 440
    visible: false
    // CONTRACT: PopupWindow n'applique un changement de grabFocus qu'après
    // fermeture/réouverture ; le prendre dès MAIN garde le clavier disponible
    // pour le mot de passe Wi-Fi et l'alias Bluetooth après navigation interne.
    grabFocus: true
    color: "transparent"

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: Theme.popupBackground
        border.color: Theme.outline

        StackLayout {
            anchors.fill: parent
            anchors.margins: 16
            currentIndex: popup.currentPage

            Column {
                id: mainPage
                spacing: 18

                Text {
                    text: "Réglages rapides"
                    color: Theme.foreground
                    font.pixelSize: 16
                    font.bold: true
                }

                Row {
                    width: parent.width
                    spacing: 8

                    WifiTile {
                        width: (parent.width - parent.spacing) / 2
                        wifiDevice: popup.wifiDevice
                        onDetailsRequested: popup.openPage("wifi")
                    }
                    BluetoothTile {
                        width: (parent.width - parent.spacing) / 2
                        adapter: popup.adapter
                        onDetailsRequested: popup.openPage("bluetooth")
                    }
                }

                VolumeSlider { width: parent.width }
                BrightnessSlider { width: parent.width }
                PowerProfile { width: parent.width }

                Rectangle {
                    width: parent.width; height: 38; radius: 4
                    color: appearancePointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
                    NerdIcon { anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: "󰸉"; color: Theme.accent; font.pixelSize: 18 }
                    Text { anchors.left: parent.left; anchors.leftMargin: 42; anchors.verticalCenter: parent.verticalCenter; text: "Apparence"; color: Theme.foreground; font.pixelSize: 13 }
                    MouseArea { id: appearancePointer; anchors.fill: parent; hoverEnabled: true; onClicked: popup.openPage("appearance") }
                }

                Item {
                    width: parent.width
                    height: 30

                    Rectangle {
                        anchors.right: parent.right
                        width: 40
                        height: 30
                        radius: 4
                        color: powerPointer.containsMouse ? Theme.border : Theme.buttonBackground

                        NerdIcon {
                            anchors.centerIn: parent
                            text: ""
                        }
                        MouseArea {
                            id: powerPointer
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton
                            onClicked: popup.openPage("session")
                        }
                    }
                }
            }

            WifiPage {
                id: wifiPage
                wifiDevice: popup.wifiDevice
                activePage: popup.visible && popup.currentPage === 1
                onBackRequested: popup.openPage("main")
            }

            BluetoothPage {
                id: bluetoothPage
                adapter: popup.adapter
                activePage: popup.visible && popup.currentPage === 2
                onBackRequested: popup.openPage("main")
            }

            SessionPage {
                id: sessionPage
                actions: popup.sessionActions
                onBackRequested: popup.openPage("main")
                onManagerRequested: popup.openPage("sessionManager")
                onActionRequested: id => popup.requestSessionAction(id)
            }

            ConfirmAction {
                id: confirmationPage
                actionInfo: popup.pendingAction || ({ id: "", label: "", confirmTitle: "",
                    description: "", accent: Theme.foreground })
                onCancelled: {
                    popup.pendingAction = null;
                    popup.openPage("session");
                }
                onConfirmed: id => {
                    if (popup.pendingAction && popup.pendingAction.id === id)
                        popup.executeSessionAction(id);
                }
            }

            BatterySettings {
                id: batteryPage
                activePage: popup.visible && popup.currentPage === 5
                onBackRequested: popup.openPage("main")
                onThresholdApplied: popup.thresholdApplied()
            }

            AppearancePage {
                onBackRequested: popup.openPage("main")
                onWallpaperRequested: popup.openPage("wallpaper")
                onThemeRequested: popup.openPage("theme")
                onNightLightRequested: popup.openPage("nightLight")
                onSunModeRequested: popup.openPage("sunMode")
                onLocationTimeRequested: popup.openPage("locationTime")
            }

            WallpaperPage {
                activePage: popup.visible && popup.currentPage === popup.pages.wallpaper
                onBackRequested: popup.openPage("appearance")
            }

            ThemePage {
                onBackRequested: popup.openPage("appearance")
            }
            NightLightPage {
                onBackRequested: popup.openPage("appearance")
            }
            SunModePage {
                onBackRequested: popup.openPage("appearance")
            }
            LocationTimePage {
                onBackRequested: popup.openPage("appearance")
            }
            SessionManager {
                activePage: popup.visible && popup.currentPage === popup.pages.sessionManager
                onBackRequested: popup.openPage("session")
            }
        }
    }
}

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Networking
import Quickshell.Bluetooth
import "../components"
import "../theme"
import "../sessionui"

PopupWindow {
    id: popup

    required property var barWindow
    // CONTRACT: indices externes historiques conservés ; tout nouveau routage
    // passe par ces noms afin de ne pas multiplier les indices StackLayout.
    readonly property var pages: ({ main: 0, wifi: 1, bluetooth: 2, session: 3,
        confirmation: 4, battery: 5, appearance: 6, wallpaper: 7, theme: 8,
        nightLight: 9, sunMode: 10, locationTime: 11, sessionManager: 12,
        checkpointFailure: 13, avatar: 14, audio: 15 })
    property int currentPage: pages.main
    function openPage(name) { if (pages[name] !== undefined) currentPage = pages[name]; }
    signal thresholdApplied()
    // CONTRACT: la barre appelle les mêmes instances que les curseurs du
    // panneau ; les valeurs affichées restent celles des backends observés.
    readonly property bool volumeAvailable: volumeSlider.sinkAudio !== null
    readonly property bool volumeMuted: volumeSlider.muted
    readonly property int volumePercent: volumeSlider.percent
    readonly property bool brightnessAvailable: brightnessSlider.available
    readonly property int brightnessPercent: brightnessSlider.percent
    function adjustVolume(steps) { volumeSlider.adjustBy(steps); }
    function adjustBrightness(steps) { brightnessSlider.adjustBy(steps); }
    readonly property var pendingAction: sessionExitGate.pendingAction
    readonly property string checkpointError: sessionExitGate.errorMessage
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME")
        || ((Quickshell.env("HOME") || "") + "/.config")
    readonly property string sessionBackend: configHome
        + "/quickshell/labfy-sway/session-v2.py"
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
            checkpointReason: "logout",
            command: ["uwsm", "stop"] },
        { id: "reboot", label: "Redémarrer", icon: "", accent: Theme.warning,
            confirmTitle: "Redémarrer l'ordinateur ?",
            description: "La session en cours sera fermée.",
            checkpointReason: "reboot",
            command: ["systemctl", "reboot"] },
        { id: "poweroff", label: "Éteindre", icon: "", accent: Theme.danger,
            confirmTitle: "Éteindre l'ordinateur ?",
            description: "La session en cours sera fermée.",
            checkpointReason: "poweroff",
            command: ["systemctl", "poweroff"] }
    ]
    readonly property var wifiDevice: Networking.devices.values.find(device => device.type === DeviceType.Wifi) || null
    readonly property var adapter: Bluetooth.defaultAdapter

    // Une nouvelle ouverture recommence sur MAIN ; les pages libèrent leurs scans à la fermeture.
    onVisibleChanged: if (!visible) {
        openPage("main");
        if (!sessionExitGate.busy) sessionExitGate.cancel();
    }

    function requestSessionAction(id) {
        sessionExitGate.requestAction(id);
    }

    function confirmSessionAction(id) {
        sessionExitGate.confirmAction(id);
    }

    function quitWithoutCheckpoint() {
        sessionExitGate.quitWithoutCheckpoint();
    }

    SessionExitGate {
        id: sessionExitGate
        actions: popup.sessionActions
        checkpointSuccessStatus: "saved"
        onConfirmationRequested: popup.openPage("confirmation")
        onCheckpointRequested: reason => {
            // WHY: Sway IPC doit rester vivant jusqu'à la fin de la capture.
            // CONTRACT: argv direct, puis aucune action système avant validation du résultat.
            if (!SessionV2Service.run("checkpoint-last", "", reason, popup))
                sessionExitGate.checkpointFinished(2, 0, "{}", "Une opération de session est déjà en cours.");
        }
        onCommandRequested: command => {
            // CONTRACT: UWSM possède le cycle de vie de Sway ; lock/suspend et
            // les sorties utilisent toujours exactement l'argv de sessionActions.
            popup.visible = false;
            Quickshell.execDetached(command);
        }
        onCheckpointFailed: {
            popup.openPage("checkpointFailure");
            popup.visible = true;
        }
    }

    Connections {
        target: SessionV2Service
        function onCompleted(owner, kind, value, okay) {
            if (owner === popup && kind === "checkpoint-last")
                sessionExitGate.checkpointFinished(okay ? 0 : 2, 0,
                    JSON.stringify(value), okay ? "" : "Le checkpoint V2 a échoué.");
        }
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
        : currentPage === pages.appearance ? 610
        : currentPage === pages.locationTime || currentPage === pages.sessionManager ? 650
        : currentPage === pages.audio ? 620 : 440
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

                VolumeSlider { id: volumeSlider; width: parent.width }
                BrightnessSlider { id: brightnessSlider; width: parent.width }
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
                    sessionExitGate.cancel();
                    popup.openPage("session");
                }
                onConfirmed: id => {
                    if (popup.pendingAction && popup.pendingAction.id === id)
                        popup.confirmSessionAction(id);
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
                onAvatarRequested: popup.openPage("avatar")
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
            SessionManagerV2 {
                activePage: popup.visible && popup.currentPage === popup.pages.sessionManager
                onBackRequested: popup.openPage("session")
            }

            Column {
                id: checkpointFailurePage
                spacing: 16

                Text {
                    width: parent.width
                    text: "La session n’a pas pu être sauvegardée."
                    color: Theme.warningForeground
                    font.pixelSize: 16
                    font.bold: true
                    wrapMode: Text.Wrap
                }
                Text {
                    width: parent.width
                    text: popup.checkpointError
                    color: Theme.secondaryForeground
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
                Row {
                    spacing: 8
                    ActionButton {
                        label: "Annuler"
                        enabled: !sessionExitGate.busy
                        onClicked: {
                            sessionExitGate.cancel();
                            popup.openPage("session");
                        }
                    }
                    ActionButton {
                        danger: true
                        enabled: !sessionExitGate.busy
                        label: popup.pendingAction && popup.pendingAction.id === "reboot"
                            ? "Redémarrer sans sauvegarder"
                            : popup.pendingAction && popup.pendingAction.id === "poweroff"
                                ? "Éteindre sans sauvegarder"
                                : "Quitter sans sauvegarder"
                        onClicked: popup.quitWithoutCheckpoint()
                    }
                }
            }
            // Append-only: historical StackLayout indices remain unchanged.
            AvatarPage {
                activePage: popup.visible && popup.currentPage === popup.pages.avatar
                onBackRequested: popup.openPage("appearance")
            }
            AudioMixerPage {
                activePage: popup.visible && popup.currentPage === popup.pages.audio
                volumeControl: volumeSlider
                onBackRequested: popup.openPage("main")
            }
        }
    }
}

import QtQuick
import Quickshell
import Quickshell.Wayland
import "modules"
import "controlcenter"
import "windows"
import "datecenter"
import "notifications"
import "status"
import "theme"

PanelWindow {
    id: bar
    // Identité layer-shell stable pour cibler seulement cette barre dans SwayFX.
    WlrLayershell.namespace: "labfy-sway-bar"

    required property var modelData
    required property var notificationService
    screen: modelData

    anchors {
        left: true
        right: true
        top: true
    }

    margins {
        top: 6
        left: 8
        right: 8
    }

    implicitHeight: 34
    // La couche basse laisse les fenêtres plein écran conserver leur priorité.
    aboveWindows: false
    // CONTRACT: le PopupWindow reçoit les frappes seulement si son parent
    // layer-shell est focusable dès son ouverture. OnDemand n'accapare pas
    // le clavier hors interaction avec la barre ou son popup.
    focusable: true
    color: Theme.panelBackground

    // CONTRACT: toute la capsule centrale partage le même popup et la même exclusion XOR.
    function toggleDateCenter() {
        const opening = !dateCenter.visible && !dateCenter.opening;
        controlCenter.visible = false;
        windowStrip.closeMenu();
        if (opening) dateCenter.requestOpen();
        else dateCenter.requestClose();
    }

    Item {
        id: leftArea
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        // Garder les titres longs hors de la capsule centrale.
        width: Math.max(0, centerClock.x - 8)
        height: bar.height
        clip: true

        Workspaces {
            id: workspaces
            screen: bar.screen
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
        }

        WindowStrip {
            id: windowStrip
            screen: bar.screen
            anchors.left: workspaces.right
            anchors.leftMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            maxWidth: Math.max(0, leftArea.width - x - 8)
            onMenuOpened: {
                controlCenter.visible = false;
                dateCenter.requestClose();
            }
        }
    }

    Clock {
        id: centerClock
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        open: dateCenter.visible || dateCenter.opening
        unreadCount: bar.notificationService.unreadCount
        criticalUnreadCount: bar.notificationService.criticalUnreadCount
        onToggled: bar.toggleDateCenter()
    }

    Item {
        id: rightArea
        anchors.left: centerClock.right
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: bar.height
        clip: true

        // INVARIANT: la zone droite s'étend depuis le bord sans modifier l'ancrage central.
        RightStatusArea {
            id: rightStatusArea
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            barWindow: bar
            wifiDevice: controlCenter.wifiDevice
            adapter: controlCenter.adapter
            controlCenterOpen: controlCenter.visible
            onOpenPageRequested: page => {
                dateCenter.requestClose();
                windowStrip.closeMenu();
                controlCenter.currentPage = page;
                controlCenter.visible = true;
            }
            onToggleControlCenterRequested: {
                const opening = !controlCenter.visible;
                dateCenter.requestClose();
                windowStrip.closeMenu();
                controlCenter.currentPage = 0;
                controlCenter.visible = opening;
            }
        }
    }

    ControlCenter {
        id: controlCenter
        barWindow: bar
        onThresholdApplied: rightStatusArea.refreshBatteryThreshold()
    }

    DateCenter {
        id: dateCenter
        barWindow: bar
        clockItem: centerClock
        notificationService: bar.notificationService
    }
    NotificationToastArea {
        barWindow: bar
        service: bar.notificationService
    }
}

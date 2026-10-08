import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.I3
import Quickshell.Wayland
import "modules"
import "controlcenter"
import "windows"
import "datecenter"
import "notifications"
import "status"
import "theme"
import "clipboard"
import "overview"

PanelWindow {
    id: bar
    // Identité layer-shell stable pour cibler seulement cette barre dans SwayFX.
    WlrLayershell.namespace: "labfy-sway-bar"

    required property var modelData
    required property var notificationService
    required property bool startupHost
    required property bool resizeMode
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

    function closeClipboard() {
        if (clipboardLoader.item && !clipboardLoader.item.closing)
            clipboardLoader.item.dismiss(true);
    }
    // CONTRACT: clic et IPC suivent la même exclusion que les panneaux de barre.
    function toggleClipboard() {
        if (clipboardLoader.active) {
            closeClipboard();
        } else {
            closeOverview();
            controlCenter.visible = false;
            dateCenter.requestClose();
            windowStrip.closeMenu();
            rightStatusArea.closeRemovableMedia();
            clipboardLoader.active = true;
        }
        return true;
    }

    // CONTRACT: un seul écran reçoit l'Overview ; une capture sans overlay
    // précède l'ouverture afin de montrer le workspace actif tel qu'affiché.
    function closeOverview() {
        overviewRequested = false;
        if (overviewLoader.item) overviewLoader.item.dismiss();
    }
    function toggleOverview() {
        if (overviewRequested || overviewLoader.active) { closeOverview(); return true; }
        closeClipboard();
        controlCenter.visible = false;
        dateCenter.requestClose();
        windowStrip.closeMenu();
        rightStatusArea.closeRemovableMedia();
        overviewRequested = true;
        if (!overviewCapture.running) overviewCapture.running = true;
        return true;
    }
    property bool overviewRequested: false
    readonly property string overviewBackend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/overview/backend.py"
    IpcHandler {
        target: "overviewUi-" + bar.screen.name
        function toggle(): bool { return bar.toggleOverview(); }
        function state(): string {
            return JSON.stringify({ loaded: overviewLoader.active,
                visible: !!overviewLoader.item && overviewLoader.item.visible,
                requested: bar.overviewRequested,
                cards: overviewLoader.item ? overviewLoader.item.cards.map(item => ({
                    number: item.number, windows: item.windows.length,
                    snapshot: item.snapshot !== "", output: item.output
                })) : [],
                bounds: overviewLoader.item ? {
                    x: overviewLoader.item.cardX, y: overviewLoader.item.cardY,
                    width: overviewLoader.item.cardWidth, height: overviewLoader.item.cardHeight
                } : null });
        }
    }
    Process {
        id: overviewCapture
        command: ["python3", "-B", bar.overviewBackend, "capture", "--output", bar.screen.name]
        onExited: (code, status) => {
            if (bar.overviewRequested) overviewLoader.active = true;
            else if (code !== 0) console.warn("Capture du workspace impossible");
        }
    }
    // CONTRACT: un workspace nouvellement visible reçoit une capture après
    // que Sway a présenté sa première frame, sans attendre le cycle de 15 s.
    Connections {
        target: I3
        function onRawEvent(event) {
            if (event.type === "workspace") overviewCaptureRefresh.restart();
        }
    }
    Timer {
        id: overviewCaptureRefresh
        interval: 350; repeat: false
        onTriggered: {
            if (!overviewCapture.running && !overviewLoader.active && !clipboardLoader.active
                    && !controlCenter.visible && !dateCenter.visible)
                overviewCapture.running = true;
        }
    }
    // Un seul snapshot toutes les 15 secondes pour le workspace actuellement
    // visible ; aucune boucle de capture pendant l'Overview ou un autre panneau.
    Timer {
        interval: 15000; repeat: true; running: true; triggeredOnStart: true
        onTriggered: {
            if (!overviewCapture.running && !overviewLoader.active && !clipboardLoader.active
                    && !controlCenter.visible && !dateCenter.visible)
                overviewCapture.running = true;
        }
    }
    LazyLoader {
        id: overviewLoader
        active: false
        WorkspaceOverview {
            barWindow: bar
            onOverviewDismissed: { bar.overviewRequested = false; overviewLoader.active = false; }
        }
    }

    // CONTRACT: contrôle événementiel par écran pour ouvrir les pages depuis
    // les raccourcis et les vérifications visuelles ; aucun état n'est dupliqué.
    IpcHandler {
        target: "appearanceUi-" + bar.screen.name
        function openPage(page: string): bool {
            if (controlCenter.pages[page] === undefined) return false;
            bar.closeClipboard();
            dateCenter.requestClose();
            windowStrip.closeMenu();
            controlCenter.openPage(page);
            controlCenter.visible = true;
            return true;
        }
        function close(): bool { controlCenter.visible = false; return true; }
        function openDateCenter(): bool { bar.toggleDateCenter(); return true; }
        function openWindowMenu(): bool {
            bar.closeClipboard();
            controlCenter.visible = false;
            dateCenter.requestClose();
            return windowStrip.openActiveMenu();
        }
    }

    // CONTRACT: un seul écran reçoit l'appel IPC ; le composant et ses données
    // n'existent que pendant l'ouverture ou le nettoyage de fermeture.
    IpcHandler {
        target: "clipboardUi-" + bar.screen.name
        function toggle(): bool { return bar.toggleClipboard(); }
        function state(): string {
            // Diagnostic sans nombre, identifiant ni aperçu de presse-papiers.
            return JSON.stringify({ loaded: clipboardLoader.active,
                visible: !!clipboardLoader.item && clipboardLoader.item.visible,
                searchFocused: !!clipboardLoader.item && clipboardLoader.item.searchFocused,
                listLoaded: !!clipboardLoader.item && clipboardLoader.item.listLoaded,
                bounds: clipboardLoader.item ? {
                    x: clipboardLoader.item.cardX, y: clipboardLoader.item.cardY,
                    width: clipboardLoader.item.cardWidth, height: clipboardLoader.item.cardHeight
                } : null });
        }
    }
    LazyLoader {
        id: clipboardLoader
        active: false
        ClipboardPanel {
            barWindow: bar
            onCleanupFinished: clipboardLoader.active = false
        }
    }

    // CONTRACT: toute la capsule centrale partage le même popup et la même exclusion XOR.
    function toggleDateCenter() {
        const opening = !dateCenter.visible && !dateCenter.opening;
        closeOverview();
        closeClipboard();
        controlCenter.visible = false;
        windowStrip.closeMenu();
        rightStatusArea.closeRemovableMedia();
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

        Rectangle {
            id: resizeIndicator
            visible: bar.resizeMode
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: visible ? resizeLabel.implicitWidth + 12 : 0
            height: 24
            radius: 4
            color: Theme.buttonBackground
            Text {
                id: resizeLabel
                anchors.centerIn: parent
                text: "RESIZE"
                font.pixelSize: 11
                font.bold: true
                color: Theme.peach
            }
        }

        Workspaces {
            id: workspaces
            screen: bar.screen
            anchors.left: resizeIndicator.right
            anchors.leftMargin: resizeIndicator.visible ? 6 : 0
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
                bar.closeOverview();
                bar.closeClipboard();
                controlCenter.visible = false;
                dateCenter.requestClose();
                rightStatusArea.closeRemovableMedia();
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
            audioBrightnessController: controlCenter
            clipboardOpen: clipboardLoader.active && !!clipboardLoader.item && !clipboardLoader.item.closing
            onOpenPageRequested: page => {
                bar.closeOverview();
                bar.closeClipboard();
                dateCenter.requestClose();
                windowStrip.closeMenu();
                rightStatusArea.closeRemovableMedia();
                controlCenter.currentPage = page;
                controlCenter.visible = true;
            }
            onToggleControlCenterRequested: {
                bar.closeOverview();
                const opening = !controlCenter.visible;
                bar.closeClipboard();
                dateCenter.requestClose();
                windowStrip.closeMenu();
                rightStatusArea.closeRemovableMedia();
                controlCenter.currentPage = 0;
                controlCenter.visible = opening;
            }
            onToggleRemovableMediaRequested: {
                bar.closeOverview();
                const opening = !rightStatusArea.removableMediaOpen;
                bar.closeClipboard();
                controlCenter.visible = false;
                dateCenter.requestClose();
                windowStrip.closeMenu();
                rightStatusArea.setRemovableMediaOpen(opening);
            }
            onToggleClipboardRequested: bar.toggleClipboard()
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
    SessionStartupPromptV2 {
        barWindow: bar
        startupHost: bar.startupHost
    }
}

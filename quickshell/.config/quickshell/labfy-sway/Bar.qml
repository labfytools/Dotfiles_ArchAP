import QtQuick
import QtQuick.Controls
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
import "applications"

PanelWindow {
    id: bar
    // Identité layer-shell stable pour cibler seulement cette barre dans SwayFX.
    WlrLayershell.namespace: "labfy-sway-bar"

    required property var modelData
    required property var notificationService
    required property bool startupHost
    required property bool resizeMode
    required property var applicationCoordinator
    required property bool authenticationActive
    required property var keepAwakeController
    required property var drawerService
    required property var osdService
    screen: modelData

    function closeDrawer() { drawerIndicator.close(false) }
    function toggleDrawer() { drawerIndicator.toggle() }

    // INVARIANT: une seule surface de barre porte l'inhibiteur, même avec
    // plusieurs sorties. La tasse et les demandes applicatives sont deux
    // propriétaires indépendants ; la libération de l'un préserve l'autre.
    IdleInhibitor {
        id: idleInhibitor
        window: bar
        enabled: bar.startupHost && (bar.keepAwakeController.keepAwake
                                     || bar.keepAwakeController.applicationRequestCount > 0)
        // WHY: les transitions seules permettent de dater un éventuel trou
        // d'inhibition entre deux générations, sans journal par frame.
        onEnabledChanged: console.info("Inhibiteur activé", enabled,
                                       "génération", bar.keepAwakeController.keepAwakeGeneration,
                                       "ms", Date.now())
        onWindowChanged: console.info("Surface inhibiteur présente", window === bar,
                                      "génération", bar.keepAwakeController.keepAwakeGeneration,
                                      "ms", Date.now())
    }
    // CONTRACT: le mapping observé ne vaut pas accusé d'inhibition du compositeur.
    onBackingWindowVisibleChanged: {
        if (startupHost) console.info("Surface barre mappée", backingWindowVisible,
                                      "génération", keepAwakeController.keepAwakeGeneration,
                                      "ms", Date.now());
    }
    Component.onCompleted: {
        if (startupHost) console.info("Hôte inhibiteur créé", idleInhibitor.enabled,
                                      backingWindowVisible, "génération",
                                      keepAwakeController.keepAwakeGeneration, "ms", Date.now());
    }
    Component.onDestruction: {
        if (startupHost) console.info("Hôte inhibiteur détruit", "génération",
                                      keepAwakeController.keepAwakeGeneration, "ms", Date.now());
    }

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

    property string applicationsError: ""
    property string queuedApplicationId: ""
    readonly property string applicationsBackend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/applications/backend.py"
    function closeApplications() { applicationCoordinator.applicationsOutput = ""; }
    function toggleApplications() {
        if (authenticationActive) return false;
        if (applicationCoordinator.applicationsOutput !== screen.name) applicationsError = "";
        applicationCoordinator.toggleApplications(screen.name);
        return true;
    }
    function launchApplication(id) {
        if (applicationLaunch.running || launchDelay.running) return;
        queuedApplicationId = id;
        closeApplications();
        // WHY: release exclusive layer focus before the new client requests it.
        launchDelay.start();
    }
    Timer {
        id: launchDelay
        interval: 140; repeat: false
        onTriggered: {
            applicationLaunch.command = ["python3", "-B", bar.applicationsBackend,
                "launch", bar.queuedApplicationId];
            applicationLaunch.running = true;
        }
    }
    Process {
        id: applicationLaunch
        stdout: StdioCollector { id: launchOutput; waitForEnd: true }
        onExited: (code, status) => {
            let result = {};
            try { result = JSON.parse(launchOutput.text); } catch (_) {}
            if (code !== 0 || result.error) {
                bar.applicationsError = result.error || "Lancement impossible";
                if (!bar.applicationCoordinator.applicationsOutput)
                    bar.applicationCoordinator.toggleApplications(bar.screen.name);
            }
            bar.queuedApplicationId = "";
        }
    }
    Connections {
        target: bar.applicationCoordinator
        function onAuthenticationOpening() {
            bar.closeApplications();
            // INVARIANT: no Overview screenshot may contain the auth surface.
            overviewCapture.running = false;
            overviewCaptureRefresh.stop();
            if (overviewLoader.item) overviewLoader.item.skipDismissCaptures = true;
            bar.closeOverview();
            bar.closeClipboard();
            controlCenter.visible = false;
            dateCenter.requestClose();
            windowStrip.closeMenu();
            rightStatusArea.closeRemovableMedia();
            bar.closeDrawer();
        }
        function onApplicationsOpening(output) {
            bar.closeOverview();
            bar.closeClipboard();
            controlCenter.visible = false;
            dateCenter.requestClose();
            windowStrip.closeMenu();
            rightStatusArea.closeRemovableMedia();
            bar.closeDrawer();
        }
    }
    IpcHandler {
        target: "applicationsUi-" + bar.screen.name
        function toggle(): bool { return bar.toggleApplications(); }
        function state(): string {
            return JSON.stringify({ loaded: applicationsLoader.active,
                visible: !!applicationsLoader.item && applicationsLoader.item.visible,
                searchFocused: !!applicationsLoader.item && applicationsLoader.item.searchFocused,
                navigationFocused: !!applicationsLoader.item && applicationsLoader.item.navigationFocused,
                gridFocused: !!applicationsLoader.item && applicationsLoader.item.gridFocused,
                category: applicationsLoader.item ? applicationsLoader.item.selectedCategory : "",
                resultCount: applicationsLoader.item ? applicationsLoader.item.visibleApps.length : 0,
                firstIds: applicationsLoader.item ? applicationsLoader.item.visibleApps.slice(0, 4).map(item => item.id) : [],
                bounds: applicationsLoader.item ? {
                    x: applicationsLoader.item.cardX, y: applicationsLoader.item.cardY,
                    width: applicationsLoader.item.cardWidth,
                    height: applicationsLoader.item.cardHeight
                } : null });
        }
    }
    LazyLoader {
        id: applicationsLoader
        active: bar.applicationCoordinator.applicationsOutput === bar.screen.name
        ApplicationsMenu {
            barWindow: bar
            errorMessage: bar.applicationsError
            onMenuDismissed: bar.closeApplications()
            onLaunchRequested: id => bar.launchApplication(id)
        }
    }

    function closeClipboard() {
        if (clipboardLoader.item && !clipboardLoader.item.closing)
            clipboardLoader.item.dismiss(true);
    }
    // CONTRACT: clic et IPC suivent la même exclusion que les panneaux de barre.
    function toggleClipboard() {
        if (authenticationActive) return false;
        if (clipboardLoader.active) {
            closeClipboard();
        } else {
            closeApplications();
            closeOverview();
            controlCenter.visible = false;
            dateCenter.requestClose();
            windowStrip.closeMenu();
            rightStatusArea.closeRemovableMedia();
            bar.closeDrawer();
            clipboardLoader.active = true;
        }
        return true;
    }

    // CONTRACT: un seul écran reçoit l'Overview ; une capture sans overlay
    // précède l'ouverture afin de montrer le workspace actif tel qu'affiché.
    function closeOverview() {
        overviewRequested = false;
        if (overviewLoader.item) overviewLoader.item.dismiss();
        return true;
    }
    function openOverview() {
        if (authenticationActive) return false;
        // INVARIANT: deux ouvertures ne créent ni une seconde capture ni une fermeture.
        if (overviewRequested || overviewLoader.active) return true;
        closeApplications();
        closeClipboard();
        controlCenter.visible = false;
        dateCenter.requestClose();
        windowStrip.closeMenu();
        rightStatusArea.closeRemovableMedia();
        bar.closeDrawer();
        overviewRequested = true;
        if (!overviewCapture.running) overviewCapture.running = true;
        return true;
    }
    function toggleOverview() {
        if (authenticationActive) return false;
        if (overviewRequested || overviewLoader.active) return closeOverview();
        return openOverview();
    }
    property bool overviewRequested: false
    readonly property string overviewBackend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/overview/backend.py"
    IpcHandler {
        target: "overviewUi-" + bar.screen.name
        function toggle(): bool { return bar.toggleOverview(); }
        // CONTRACT: chaque geste demande un état explicite. La fermeture retire
        // la demande avant qu'une capture asynchrone puisse afficher la vue.
        function open(): bool { return bar.openOverview(); }
        function close(): bool { return bar.closeOverview(); }
        // CONTRACT: le dispatcher ne lit pas la liste potentiellement longue
        // des cartes pour attendre la libération du panneau.
        function active(): bool { return bar.overviewRequested || overviewLoader.active; }
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
            if (bar.overviewRequested && !bar.authenticationActive) overviewLoader.active = true;
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
            if (!bar.authenticationActive && !overviewCapture.running && !overviewLoader.active && !clipboardLoader.active
                    && !applicationsLoader.active
                    && !controlCenter.visible && !dateCenter.visible)
                overviewCapture.running = true;
        }
    }
    // Un seul snapshot toutes les 15 secondes pour le workspace actuellement
    // visible ; aucune boucle de capture pendant l'Overview ou un autre panneau.
    Timer {
        interval: 15000; repeat: true; running: true; triggeredOnStart: true
        onTriggered: {
            if (!bar.authenticationActive && !overviewCapture.running && !overviewLoader.active && !clipboardLoader.active
                    && !applicationsLoader.active
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
            if (bar.authenticationActive) return false;
            if (controlCenter.pages[page] === undefined) return false;
            bar.closeApplications();
            bar.closeClipboard();
            dateCenter.requestClose();
            windowStrip.closeMenu();
            controlCenter.openPage(page);
            controlCenter.visible = true;
            return true;
        }
        function close(): bool { controlCenter.visible = false; return true; }
        function openDateCenter(): bool {
            if (bar.authenticationActive) return false;
            bar.toggleDateCenter(); return true;
        }
        function openWindowMenu(): bool {
            if (bar.authenticationActive) return false;
            bar.closeApplications();
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
    IpcHandler {
        target: "drawerUi-" + bar.screen.name
        function toggle(): bool { bar.toggleDrawer(); return true; }
        function close(): bool { bar.closeDrawer(); return true; }
        function state(): string {
            return JSON.stringify({count: bar.drawerService ? bar.drawerService.entries.length : 0,
                open: drawerIndicator.open, busy: bar.drawerService ? bar.drawerService.busy : false,
                error: bar.drawerService ? bar.drawerService.error : ""});
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
        if (authenticationActive) return;
        const opening = !dateCenter.visible && !dateCenter.opening;
        closeApplications();
        closeOverview();
        closeClipboard();
        controlCenter.visible = false;
        windowStrip.closeMenu();
        rightStatusArea.closeRemovableMedia();
        bar.closeDrawer();
        if (opening) dateCenter.requestOpen();
        else dateCenter.requestClose();
    }

    // CONTRACT: le tiroir prend le focus clavier sur une seule sortie et
    // libère tous les autres panneaux transitoires avant son ouverture.
    function prepareDrawer() {
        closeApplications();
        closeOverview();
        closeClipboard();
        controlCenter.visible = false;
        dateCenter.requestClose();
        windowStrip.closeMenu();
        rightStatusArea.closeRemovableMedia();
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
            id: applicationsButton
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: 30; height: 28; radius: 4
            color: bar.applicationCoordinator.applicationsOutput === bar.screen.name
                ? Theme.buttonPressed : applicationsPointer.containsMouse
                    ? Theme.buttonHover : "transparent"
            Text {
                anchors.centerIn: parent
                text: "󰣇"; color: Theme.lavender
                font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 25
            }
            MouseArea {
                id: applicationsPointer
                anchors.fill: parent; hoverEnabled: true
                onClicked: bar.toggleApplications()
            }
        }

        // Même séparation neutre que les groupes de droite, sans zone de clic.
        Rectangle {
            id: applicationsSeparator
            anchors.left: applicationsButton.right
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: 1; height: 14
            color: Theme.separator
        }

        Rectangle {
            id: resizeIndicator
            visible: bar.resizeMode
            anchors.left: applicationsSeparator.right
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

        // CONTRACT: une seule instance, dans le même groupe de navigation que
        // les workspaces ; sa largeur n'occupe aucun espace si le tiroir est vide.
        DrawerIndicator {
            id: drawerIndicator
            anchors.left: resizeIndicator.right
            anchors.leftMargin: visible && resizeIndicator.visible ? 6 : 0
            anchors.verticalCenter: parent.verticalCenter
            service: bar.drawerService
            barWindow: bar
            output: bar.screen.name
            authenticationActive: bar.authenticationActive
            onOpened: bar.prepareDrawer()
        }

        Workspaces {
            id: workspaces
            screen: bar.screen
            anchors.left: drawerIndicator.right
            anchors.leftMargin: drawerIndicator.visible ? 6
                : resizeIndicator.visible ? 6 : 0
            anchors.verticalCenter: parent.verticalCenter
        }

        Rectangle {
            id: workspacesSeparator
            anchors.left: workspaces.right
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: 1; height: 14
            color: Theme.separator
        }

        WindowStrip {
            id: windowStrip
            screen: bar.screen
            drawerService: bar.drawerService
            authenticationActive: bar.authenticationActive
            anchors.left: workspacesSeparator.right
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            maxWidth: Math.max(0, leftArea.width - x - 8)
            onMenuOpened: {
                bar.closeApplications();
                bar.closeOverview();
                bar.closeClipboard();
                controlCenter.visible = false;
                dateCenter.requestClose();
                rightStatusArea.closeRemovableMedia();
                bar.closeDrawer();
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
            onAdjustedFromBar: kind => bar.osdService.barAction(kind, bar.screen)
            keepAwakeController: bar.keepAwakeController
            clipboardOpen: clipboardLoader.active && !!clipboardLoader.item && !clipboardLoader.item.closing
            onOpenPageRequested: page => {
                bar.closeApplications();
                bar.closeOverview();
                bar.closeClipboard();
                dateCenter.requestClose();
                windowStrip.closeMenu();
                rightStatusArea.closeRemovableMedia();
                bar.closeDrawer();
                controlCenter.currentPage = page;
                controlCenter.visible = true;
            }
            onToggleControlCenterRequested: {
                bar.closeApplications();
                bar.closeOverview();
                const opening = !controlCenter.visible;
                bar.closeClipboard();
                dateCenter.requestClose();
                windowStrip.closeMenu();
                rightStatusArea.closeRemovableMedia();
                bar.closeDrawer();
                controlCenter.currentPage = 0;
                controlCenter.visible = opening;
            }
            onToggleRemovableMediaRequested: {
                bar.closeApplications();
                bar.closeOverview();
                const opening = !rightStatusArea.removableMediaOpen;
                bar.closeClipboard();
                controlCenter.visible = false;
                dateCenter.requestClose();
                windowStrip.closeMenu();
                rightStatusArea.setRemovableMediaOpen(opening);
                bar.closeDrawer();
            }
            onToggleClipboardRequested: bar.toggleClipboard()
        }
    }

    ControlCenter {
        id: controlCenter
        barWindow: bar
        keepAwakeController: bar.keepAwakeController
        onThresholdApplied: rightStatusArea.refreshBatteryThreshold()
        onVisibleChanged: bar.osdService.setPanel(bar.screen, visible, currentPage)
        onCurrentPageChanged: bar.osdService.setPanel(bar.screen, visible, currentPage)
    }
    // CONTRACT: seul l'hôte existant transmet les lectures partagées ; les
    // autres barres ne multiplient pas les événements lors d'un changement.
    Connections {
        target: controlCenter
        function snapshot() {
            if (!bar.startupHost) return;
            bar.osdService.sampleSink(controlCenter.volumeIdentity,
                controlCenter.volumeAvailable, controlCenter.volumeRaw,
                controlCenter.volumePercent, controlCenter.volumeMuted);
            bar.osdService.sampleBrightness(controlCenter.brightnessIdentity,
                controlCenter.brightnessAvailable, controlCenter.brightnessRaw,
                controlCenter.brightnessPercent);
        }
        function onVolumeIdentityChanged() { snapshot(); }
        function onVolumeAvailableChanged() { snapshot(); }
        function onVolumeRawChanged() { snapshot(); }
        function onVolumeMutedChanged() { snapshot(); }
        function onBrightnessAvailableChanged() { snapshot(); }
        function onBrightnessRawChanged() { snapshot(); }
        Component.onCompleted: snapshot()
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

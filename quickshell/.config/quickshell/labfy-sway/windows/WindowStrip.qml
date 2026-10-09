import QtQuick
import Quickshell
import Quickshell.I3
import Quickshell.I3._Ipc
import Quickshell.Io

Item {
    id: strip

    required property var screen
    required property var drawerService
    required property bool authenticationActive
    required property int maxWidth
    property var tree: null
    property bool componentReady: false
    property bool refreshRunning: false
    property bool refreshPending: false
    property var menuAnchor: null
    property var menuWindow: null
    signal menuOpened()

    // monitorFor(screen) peut rester null dans un binding créé avant l'inventaire IPC.
    // Le modèle réactif des moniteurs réévalue le workspace dès que Sway l'annonce.
    readonly property var monitor: I3.monitors.values.find(item => item.name === screen.name) || null
    readonly property var activeWorkspace: monitor ? monitor.activeWorkspace : null
    readonly property var windows: windowsForWorkspace(tree, activeWorkspace)
    readonly property var activeWindow: windows.find(window => window.focused) || null
    readonly property var secondaryWindows: activeWindow
        ? windows.filter(window => window.id !== activeWindow.id) : []

    width: maxWidth
    height: 26
    clip: true

    // L'arbre Sway est la source du workspace : une sortie seule ne distingue pas ses fenêtres.
    function windowsForWorkspace(root, workspace) {
        if (!root || !workspace) return [];

        function findWorkspace(node) {
            if (node.type === "workspace" && node.id === workspace.id) return node;
            for (const child of (node.nodes || []).concat(node.floating_nodes || [])) {
                const found = findWorkspace(child);
                if (found) return found;
            }
            return null;
        }

        const node = findWorkspace(root);
        if (!node) return [];
        const found = [];

        function collect(container) {
            const appId = container.app_id
                || (container.window_properties && container.window_properties.class) || "";
            if ((container.type === "con" || container.type === "floating_con") && appId) {
                found.push({
                    id: container.id,
                    title: container.name || appId,
                    appId: appId,
                    appKey: appId.toLowerCase(),
                    focused: container.focused === true
                });
            }
            for (const child of (container.nodes || []).concat(container.floating_nodes || []))
                collect(child);
        }

        collect(node);
        const focusedIndex = found.findIndex(window => window.focused);
        if (focusedIndex > 0)
            found.unshift(found.splice(focusedIndex, 1)[0]);
        return found;
    }

    // Process.running devient vrai après la demande de lancement : ce verrou ferme aussi cet intervalle.
    // Une rafale IPC garde au plus un relevé supplémentaire en attente.
    function requestRefresh() {
        if (!componentReady) return;
        if (refreshRunning) {
            refreshPending = true;
            return;
        }
        refreshRunning = true;
        treeReader.running = true;
    }

    // Les titres animés peuvent changer plusieurs fois par seconde : l'événement IPC
    // contient déjà le nouveau titre, sans nécessiter un relevé complet de l'arbre.
    function applyTitleEvent(event) {
        if (!tree || refreshRunning) return false;
        let update;
        try {
            update = JSON.parse(event.data);
        } catch (error) {
            return false;
        }
        if (update.change !== "title" || !update.container) return false;

        function updateNode(node) {
            if (node.id === update.container.id) {
                node.name = update.container.name;
                return true;
            }
            for (const child of (node.nodes || []).concat(node.floating_nodes || [])) {
                if (updateNode(child)) return true;
            }
            return false;
        }

        if (!updateNode(tree)) return false;
        tree = Object.assign({}, tree);
        return true;
    }

    function closeMenu() {
        windowMenu.visible = false;
    }
    function openActiveMenu() {
        if (!activeWindow) return false;
        showMenu(activeButton, activeWindow);
        return true;
    }

    function showMenu(item, windowInfo) {
        if (authenticationActive) return;
        if (windowMenu.visible && menuWindow && menuWindow.id === windowInfo.id) {
            windowMenu.visible = false;
            return;
        }
        windowMenu.visible = false;
        menuAnchor = item;
        menuWindow = windowInfo;
        windowMenu.visible = true;
        menuOpened();
    }

    // Des changements de workspace arrivent pendant la construction QML : démarrer après celle du Process.
    Component.onCompleted: {
        componentReady = true;
        Qt.callLater(requestRefresh);
    }
    onMonitorChanged: requestRefresh()
    onActiveWorkspaceChanged: {
        closeMenu();
        requestRefresh();
    }
    onWindowsChanged: {
        if (menuWindow && !windows.some(window => window.id === menuWindow.id))
            closeMenu();
    }

    Connections {
        target: I3
        function onConnected() { strip.requestRefresh(); }
        function onRawEvent(event) {
            if (event.type === "workspace")
                strip.requestRefresh();
        }
    }

    // QuickShell 0.3.1 n'abonne I3.rawEvent qu'à workspace/output.
    I3IpcListener {
        subscriptions: ["window"]
        onIpcEvent: event => {
            // Chaque abonnement confirmé, initial ou rétabli, impose un snapshot complet.
            if (event.type === "subscribe") {
                try {
                    if (JSON.parse(event.data).success === true)
                        strip.requestRefresh();
                    else
                        console.warn("Abonnement aux fenêtres Sway refusé");
                } catch (error) {
                    console.warn("Réponse d'abonnement Sway illisible :", error);
                }
                return;
            }
            if (!strip.applyTitleEvent(event))
                strip.requestRefresh();
        }
    }

    Process {
        id: treeReader
        command: ["swaymsg", "-t", "get_tree", "-r"]
        stdout: StdioCollector { id: treeOutput; waitForEnd: true }

        onExited: (exitCode, exitStatus) => {
            if (exitCode === 0) {
                try {
                    strip.tree = JSON.parse(treeOutput.text);
                } catch (error) {
                    console.warn("Arbre Sway illisible :", error);
                }
            } else {
                console.warn("Relevé de l'arbre Sway échoué :", exitCode);
            }
            strip.refreshRunning = false;
            if (strip.refreshPending) {
                strip.refreshPending = false;
                Qt.callLater(strip.requestRefresh);
            }
        }
    }

    Row {
        id: buttons
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4

        WindowButton {
            id: activeButton
            visible: strip.activeWindow !== null
            windowInfo: strip.activeWindow || ({ id: 0, title: "", appId: "", appKey: "" })
            primary: true
            maxPrimaryWidth: Math.max(26, Math.min(400,
                strip.width - strip.secondaryWindows.length * 30 - 8))
            menuOpen: windowMenu.visible && strip.menuWindow
                && strip.menuWindow.id === windowInfo.id
            onMenuRequested: (item, windowInfo) => strip.showMenu(item, windowInfo)
        }

        Repeater {
            model: ScriptModel {
                values: strip.secondaryWindows
                objectProp: "id"
            }

            delegate: WindowButton {
                required property var modelData
                windowInfo: modelData
                primary: false
                maxPrimaryWidth: 26
                menuOpen: windowMenu.visible && strip.menuWindow
                    && strip.menuWindow.id === windowInfo.id
                onMenuRequested: (item, windowInfo) => strip.showMenu(item, windowInfo)
            }
        }
    }

    WindowMenu {
        id: windowMenu
        anchorItem: strip.menuAnchor
        selectedWindow: strip.menuWindow
        windows: strip.windows
        onStoreRequested: id => {
            strip.closeMenu();
            strip.drawerService.act("store", id, strip.screen.name);
        }
    }
}

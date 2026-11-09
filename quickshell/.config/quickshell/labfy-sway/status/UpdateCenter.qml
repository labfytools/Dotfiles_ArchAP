import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import "../theme"

PopupWindow {
    id: center
    required property var barWindow
    required property var indicator
    required property var updateState
    property string query: ""
    property string origin: "Tous"
    // WHY: Process.running may change on the next event-loop turn. Synchronous
    // admission flags reject two clicks delivered in the same turn.
    property bool refreshPending: false
    property bool terminalPending: false
    property bool confirming: false
    property string actionError: ""
    property var maintenance: ({history: [], files: [], failed: [], errors: [], reboot: ""})
    property var news: ({items: []})
    readonly property string backend: Qt.resolvedUrl("../bin/check-updates.py").toString().replace("file://", "")
    readonly property string terminalBackend: Qt.resolvedUrl("../bin/update-terminal.py").toString().replace("file://", "")
    property double tick: Date.now()
    readonly property bool staleCheck: Boolean(center.updateState.checking) && (!center.updateState.checkStarted || tick - new Date(center.updateState.checkStarted).getTime() > 270000)
    readonly property bool checking: refreshPending || refreshProcess.running || (Boolean(center.updateState.checking) && !staleCheck)
    readonly property var filtered: (center.updateState.packages || []).filter(p =>
        (origin === "Tous" || p.origin === origin) && p.name.toLowerCase().includes(query.toLowerCase()))
    anchor.window: barWindow
    anchor.rect.x: Math.max(8, barWindow.width - implicitWidth - 8)
    anchor.rect.y: barWindow.height + 6
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    implicitWidth: Math.min(660, barWindow.screen.width - 24)
    implicitHeight: Math.min(720, barWindow.screen.height - barWindow.height - 30)
    color: "transparent"
    visible: false
    // CONTRACT: grab is fixed before mapping; outside click and Escape close the popup.
    grabFocus: true
    onVisibleChanged: {
        confirming = false;
        tick = Date.now();
        if (visible) {
            if (!maintenanceProcess.running) maintenanceProcess.running = true;
            if (!newsProcess.running) newsProcess.running = true;
        }
    }
    function refresh() {
        if (checking || terminalPending) return;
        actionError = "";
        refreshPending = true;
        refreshProcess.running = true;
    }
    function terminal(preview) {
        if (terminalPending || checking || (!preview && !confirming)) return;
        confirming = false;
        // CONTRACT: direct argv, never a shell, package name or remote command.
        // The dedicated app_id selects only this terminal for the Sway floating rule.
        terminalProcess.command = ["kitty", "--class", "labfy-update-center", "--title", "Labfy Update Center", "python3", "-B", terminalBackend];
        if (preview) terminalProcess.command = terminalProcess.command.concat(["--dry-run"]);
        terminalPending = true;
        terminalProcess.running = true;
        visible = false;
    }
    Process {
        id: refreshProcess
        command: ["systemctl", "--user", "start", "labfy-quickshell-updates.service"]
        stderr: StdioCollector { id: refreshError }
        onExited: (code, status) => {
            center.refreshPending = false;
            indicator.reload();
            if (code !== 0) center.actionError = refreshError.text || "Échec du service de vérification";
        }
    }
    Process {
        id: terminalProcess
        onExited: (code, status) => {
            center.terminalPending = false;
            indicator.reload();
            if (code !== 0) center.actionError = "Terminal terminé avec le code " + code;
        }
    }
    Process {
        id: maintenanceProcess
        command: ["python3", "-B", center.backend, "maintenance"]
        stdout: StdioCollector { id: maintenanceOutput; waitForEnd: true }
        onExited: (code, status) => {
            try { center.maintenance = JSON.parse(maintenanceOutput.text); }
            catch (_) { center.maintenance = {history: [], files: [], failed: [], errors: ["Maintenance indisponible"], reboot: "État inconnu"}; }
        }
    }
    Process {
        id: newsProcess
        command: ["python3", "-B", center.backend, "news"]
        stdout: StdioCollector { id: newsOutput; waitForEnd: true }
        onExited: (code, status) => {
            try { center.news = JSON.parse(newsOutput.text); }
            catch (_) { center.news = {items: [], error: "Flux indisponible"}; }
        }
    }
    Rectangle {
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: center.visible = false
        radius: 4
        color: Theme.popupBackground
        border.color: Theme.outline
        Column {
            anchors.fill: parent; anchors.margins: 12; spacing: 8
            Row {
                width: parent.width; spacing: 8
                Text { text: "Labfy Update Center"; color: Theme.lavender; font.pixelSize: 17; font.bold: true; width: parent.width - 38 }
                UpdateAction { text: "×"; onClicked: center.visible = false }
            }
            Text {
                width: parent.width
                text: center.updateState.totalUpdates + (center.updateState.totalUpdates === 1 ? " mise à jour · " : " mises à jour · ") + center.updateState.repoUpdates + " officielles · " + center.updateState.aurUpdates + " AUR"
                color: Theme.foreground; font.pixelSize: 13
            }
            Text {
                width: parent.width
                text: "Dernière tentative : " + (center.updateState.lastCheck ? new Date(center.updateState.lastCheck).toLocaleString(Qt.locale("fr_FR")) : "en attente")
                    + (center.updateState.error && center.updateState.lastSuccess ? "\nDernier succès : " + new Date(center.updateState.lastSuccess).toLocaleString(Qt.locale("fr_FR")) : "")
                color: Theme.secondaryForeground; font.pixelSize: 11; wrapMode: Text.Wrap
            }
            Text {
                width: parent.width
                text: center.checking ? "Vérification en cours…" : center.staleCheck ? "Vérification interrompue ou expirée · actualisez pour réessayer." : center.updateState.error ? (center.updateState.offline ? "Connexion indisponible · " : "") + center.updateState.error + "\nRésultats précédents conservés pour les sources en échec."
                    : "Contrôles terminés · " + (center.updateState.totalUpdates ? "mises à jour disponibles" : "système à jour")
                color: center.updateState.error ? Theme.yellow : Theme.secondaryForeground; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText
            }
            Row {
                spacing: 6
                UpdateAction { text: "Actualiser"; enabled: !center.checking && !center.terminalPending; onClicked: center.refresh() }
                UpdateAction { text: "Mettre à jour le système"; enabled: !center.checking && !center.terminalPending; onClicked: center.confirming = !center.confirming }
                UpdateAction { text: "Aperçu Kitty"; enabled: !center.checking && !center.terminalPending; onClicked: center.terminal(true) }
            }
            Column {
                visible: center.confirming; width: parent.width; spacing: 5
                Text { width: parent.width; text: "Ouvrir Kitty pour une mise à jour complète Arch + AUR ? Une seconde confirmation sera demandée dans le terminal. Lisez les annonces Arch avant de continuer."; wrapMode: Text.Wrap; color: Theme.yellow; font.pixelSize: 12 }
                Row {
                    spacing: 8
                    UpdateAction { text: "Confirmer l’ouverture"; onClicked: center.terminal(false) }
                    UpdateAction { text: "Annuler"; onClicked: center.confirming = false }
                }
            }
            Text { visible: !!center.actionError; width: parent.width; text: center.actionError; color: Theme.red; wrapMode: Text.Wrap; textFormat: Text.PlainText; font.pixelSize: 11 }
            TabBar {
                id: tabs; objectName: "updateTabs"; width: parent.width
                background: Rectangle { color: Theme.surface0; radius: 4 }
                Repeater {
                    model: ["Paquets", "Maintenance", "Annonces Arch"]
                    TabButton {
                        required property string modelData
                        text: modelData
                        contentItem: Text { text: parent.text; color: Theme.foreground; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12 }
                        background: Rectangle { radius: 4; color: parent.checked ? Theme.surface2 : Theme.surface0 }
                    }
                }
            }
            Item {
                width: parent.width
                height: parent.height - y
                Column {
                    anchors.fill: parent; spacing: 6; visible: tabs.currentIndex === 0
                    Row {
                        width: parent.width; spacing: 6
                        TextField {
                            width: parent.width - 180; height: 30; placeholderText: "Rechercher un paquet…"
                            color: Theme.foreground; placeholderTextColor: Theme.secondaryForeground
                            background: Rectangle { color: Theme.inputBackground; border.color: Theme.inputBorder; radius: 4 }
                            onTextChanged: center.query = text
                        }
                        Repeater { model: ["Tous", "Arch", "AUR"]; UpdateAction { required property string modelData; text: modelData; border.color: center.origin === modelData ? Theme.lavender : Theme.outline; onClicked: center.origin = modelData } }
                    }
                    Text { width: parent.width; text: "Les repères noyau, système, graphique et session sont informatifs, sans prédiction de panne."; color: Theme.secondaryForeground; font.pixelSize: 11; wrapMode: Text.Wrap }
                    Text { visible: center.filtered.length === 0; text: "Aucun paquet à afficher"; color: Theme.secondaryForeground; font.pixelSize: 12 }
                    ListView {
                        width: parent.width; height: parent.height - y; clip: true
                        objectName: "updatePackageList"
                        model: center.filtered; spacing: 3; boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { }
                        delegate: Rectangle {
                            required property var modelData
                            width: ListView.view.width; height: 49; radius: 4; color: Theme.surface0
                            Column {
                                anchors.fill: parent; anchors.margins: 6; spacing: 3
                                Text { width: parent.width; text: modelData.name + " · " + modelData.origin + (modelData.sensitive ? " · " + modelData.sensitive : ""); color: modelData.sensitive ? Theme.yellow : Theme.foreground; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: 12 }
                                Text { width: parent.width; text: modelData.installed + " → " + modelData.available; color: Theme.secondaryForeground; textFormat: Text.PlainText; elide: Text.ElideRight; font.pixelSize: 11 }
                            }
                        }
                    }
                }
                Flickable {
                    anchors.fill: parent; clip: true; visible: tabs.currentIndex === 1
                    contentWidth: width; contentHeight: maintenanceColumn.implicitHeight; boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { }
                    Column {
                        id: maintenanceColumn; width: parent.width; spacing: 8
                        Text { text: maintenanceProcess.running ? "Lecture en cours…" : "Relevé : " + (center.maintenance.time || "indisponible"); color: Theme.secondaryForeground; font.pixelSize: 11 }
                        Text { width: parent.width; text: center.maintenance.reboot; color: Theme.yellow; font.pixelSize: 12; wrapMode: Text.Wrap }
                        Text { width: parent.width; text: (center.maintenance.errors || []).join("\n"); visible: !!text; color: Theme.yellow; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Text { text: ".pacnew / .pacsave · /etc · lecture seule"; color: Theme.lavender; font.pixelSize: 13 }
                        Text { width: parent.width; text: center.maintenance.files.join("\n") || "Aucun fichier détecté dans les chemins accessibles"; color: Theme.foreground; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Text { text: "Services en échec"; color: Theme.lavender; font.pixelSize: 13 }
                        Text { width: parent.width; text: center.maintenance.failed.join("\n") || "Aucun échec signalé dans les périmètres lus"; color: Theme.foreground; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Row {
                            spacing: 6
                            UpdateAction { text: "Journal système"; onClicked: Quickshell.execDetached(["kitty", "journalctl", "-b", "-p", "warning"]) }
                            UpdateAction { text: "Journal du collecteur"; onClicked: Quickshell.execDetached(["kitty", "journalctl", "--user", "-u", "labfy-quickshell-updates.service"]) }
                        }
                        Text { text: "Dernières transactions · /var/log/pacman.log"; color: Theme.lavender; font.pixelSize: 13 }
                        Text { width: parent.width; text: center.maintenance.history.join("\n") || "Aucune transaction lisible"; color: Theme.foreground; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                    }
                }
                ListView {
                    anchors.fill: parent; clip: true; visible: tabs.currentIndex === 2
                    model: center.news.items || []; spacing: 6; boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { }
                    header: Column {
                        width: parent.width; spacing: 6
                        Text { width: parent.width; text: "Flux officiel archlinux.org · cache 6 h\nAucune correspondance automatique avec les paquets installés."; color: Theme.secondaryForeground; font.pixelSize: 11; wrapMode: Text.Wrap }
                        Text { width: parent.width; text: newsProcess.running ? "Chargement…" : center.news.error || "Cache : " + (center.news.time || "indisponible"); color: Theme.yellow; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                    }
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width; height: newsText.implicitHeight + 16; radius: 4; color: Theme.surface0
                        Text { id: newsText; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8; text: modelData.title + "\n" + modelData.date + (modelData.manual ? "\nIntervention manuelle explicitement annoncée" : ""); color: modelData.manual ? Theme.yellow : Theme.foreground; font.pixelSize: 12; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { if (/^https:\/\/archlinux\.org\//.test(modelData.link)) Qt.openUrlExternally(modelData.link); } }
                    }
                }
            }
        }
    }
}

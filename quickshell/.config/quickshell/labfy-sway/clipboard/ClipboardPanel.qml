import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "../theme"

PanelWindow {
    id: panel
    required property var barWindow
    signal cleanupFinished()
    property var items: []
    property var results: []
    property int selected: 0
    property string operation: ""
    property string activeId: ""
    property string thumbnail: ""
    property bool confirming: false
    property bool closing: false
    property var queuedAction: null
    property string message: ""
    property bool listLoaded: false
    readonly property bool searchFocused: search.activeFocus
    readonly property real cardX: card.x
    readonly property real cardY: card.y
    readonly property real cardWidth: card.width
    readonly property real cardHeight: card.height
    // Le test QtTest cible la vraie hiérarchie d'items, jamais le backend réel.
    readonly property Item interactionRoot: contentRoot
    readonly property Item clearActionItem: clearLabel
    readonly property Item confirmActionItem: confirmLabel
    readonly property Item cancelActionItem: cancelLabel
    readonly property Item removeActionItem: removeLabel
    readonly property Item resultList: list
    readonly property string backend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/clipboard/backend.py"
    readonly property string isolatedDb: Quickshell.env("LABFY_CLIPHIST_TEST_DB") || ""
    readonly property string isolatedWlCopy: Quickshell.env("LABFY_CLIPHIST_TEST_WL_COPY") || ""

    // WHY: l'appel IPC ne satisfait pas la contrainte de parent du grab PopupWindow.
    // CONTRACT: le focus exclusif existe seulement durant cette surface éphémère.
    screen: barWindow.screen
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0
    aboveWindows: true
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    WlrLayershell.namespace: "labfy-clipboard-history"
    color: "transparent"

    function run(action, ident) {
        if (helper.running) return false;
        operation = action;
        activeId = ident || "";
        helper.command = ["python3", "-B", backend, action]
            .concat(ident ? [ident] : [])
            .concat(isolatedDb ? ["--db-path", isolatedDb] : [])
            .concat(isolatedWlCopy ? ["--wl-copy-path", isolatedWlCopy] : []);
        helper.running = true;
        return true;
    }
    function refresh() { run("list", ""); }
    function request(action, ident) {
        // Une miniature en cours ne doit pas faire perdre une commande clavier.
        if (helper.running) { queuedAction = { action: action, ident: ident || "" }; return; }
        run(action, ident);
    }
    function filter() {
        const query = search.text.toLocaleLowerCase();
        results = items.filter(item => !query || (!item.image && item.preview.toLocaleLowerCase().includes(query)));
        selected = 0;
        updateThumbnail();
    }
    function currentItem() { return selected >= 0 && selected < results.length ? results[selected] : null; }
    function updateThumbnail() {
        thumbnail = "";
        const item = currentItem();
        if (item && item.image && !helper.running && !queuedAction) run("thumb", item.id);
    }
    function choose() {
        const item = currentItem();
        if (item && !confirming) request("select", item.id);
    }
    function remove() {
        const item = currentItem();
        if (item && !confirming) request("delete", item.id);
    }
    function dismiss(force) {
        if (confirming && !force) { confirming = false; return; }
        if (closing) return;
        closing = true;
        queuedAction = null;
        visible = false;
        items = []; results = []; thumbnail = "";
        if (!helper.running) run("clean", "");
    }

    Process {
        id: helper
        running: false
        stdout: StdioCollector { id: output; waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: (code, status) => {
            const action = panel.operation;
            const requestedId = panel.activeId;
            let data = {};
            try { data = JSON.parse(output.text); } catch (_) {}
            panel.operation = "";
            panel.activeId = "";
            if (panel.closing) {
                if (action === "clean") panel.cleanupFinished();
                else panel.run("clean", "");
                return;
            }
            if (code !== 0 || status !== 0 || data.error) {
                panel.message = "Opération impossible. Réessayez.";
                if (panel.queuedAction) {
                    const next = panel.queuedAction;
                    panel.queuedAction = null;
                    panel.run(next.action, next.ident);
                }
                return;
            }
            if (action === "list") {
                panel.items = data.items || [];
                panel.listLoaded = true;
                panel.filter();
            } else if (action === "thumb") {
                const current = panel.currentItem();
                if (current && current.id === requestedId) panel.thumbnail = data.path || "";
                else panel.updateThumbnail();
            } else if (action === "select") panel.dismiss();
            else if (action === "delete" || action === "wipe") {
                panel.confirming = false;
                panel.refresh();
            }
            if (panel.queuedAction && !helper.running) {
                const next = panel.queuedAction;
                panel.queuedAction = null;
                panel.run(next.action, next.ident);
            }
        }
    }

    // La surface Wayland est créée après Component.onCompleted : demander le
    // focus au tour suivant, une fois le layer-shell visible et focusable.
    Timer { interval: 120; running: true; onTriggered: search.forceActiveFocus() }
    // WHY: TextField consomme Return avant Keys.onPressed sur cette version de Qt.
    // CONTRACT: Entrée active l'entrée sélectionnée même pendant la recherche.
    Shortcut { sequence: "Return"; context: Qt.WindowShortcut; enabled: panel.visible && !panel.confirming; onActivated: panel.choose() }
    Shortcut { sequence: "Enter"; context: Qt.WindowShortcut; enabled: panel.visible && !panel.confirming; onActivated: panel.choose() }
    Component.onCompleted: refresh()

    Item {
        id: contentRoot
        anchors.fill: parent
        Keys.onPressed: event => { if (event.key === Qt.Key_Escape) { panel.dismiss(); event.accepted = true; } }
        MouseArea { anchors.fill: parent; onClicked: panel.dismiss(true) }
        Rectangle {
            id: card
            // CONTRACT: même marge droite et même départ vertical que le
            // Control Center ; la surface complète conserve son focus clavier.
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: panel.barWindow.height + 12
            anchors.rightMargin: 16
            width: Math.max(0, Math.min(540, parent.width - 32))
            height: Math.max(0, Math.min(500, parent.height - anchors.topMargin - 16))
            radius: 4
            color: "#1e1e2e"
            border.color: "#45475a"
            border.width: 1
            MouseArea { anchors.fill: parent; onClicked: {} }
            Column {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12
                Row {
                    width: parent.width; height: 30
                    Text { text: "󰅇  Presse-papiers"; width: Math.max(0, parent.width - countLabel.implicitWidth - clearLabel.implicitWidth - 8); elide: Text.ElideRight
                        color: "#cdd6f4"; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 18; font.bold: true }
                    Item { width: 8; height: 1 }
                    Text { id: countLabel; text: panel.items.length + " / 50"; color: "#a6adc8"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    Text { id: clearLabel; text: "  Tout effacer"; color: "#f38ba8"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter
                        MouseArea { anchors.fill: parent; onClicked: panel.confirming = true } }
                }
                Rectangle {
                    width: parent.width; height: 40; radius: 4; color: "#313244"; border.color: search.activeFocus ? "#b4befe" : "#45475a"
                    TextField {
                        id: search
                        anchors.fill: parent; anchors.margins: 2
                        placeholderText: "Rechercher dans les textes…"
                        color: "#cdd6f4"; placeholderTextColor: "#a6adc8"
                        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 13
                        background: Item {}
                        onTextChanged: panel.filter()
                        Keys.onPressed: event => {
                            if (event.key === Qt.Key_Down) { panel.selected = Math.min(panel.results.length - 1, panel.selected + 1); list.positionViewAtIndex(panel.selected, ListView.Contain); panel.updateThumbnail(); event.accepted = true; }
                            else if (event.key === Qt.Key_Up) { panel.selected = Math.max(0, panel.selected - 1); list.positionViewAtIndex(panel.selected, ListView.Contain); panel.updateThumbnail(); event.accepted = true; }
                            else if (event.key === Qt.Key_Escape) { panel.dismiss(); event.accepted = true; }
                            else if (event.key === Qt.Key_Delete && (event.modifiers & Qt.ControlModifier)) { panel.remove(); event.accepted = true; }
                        }
                    }
                }
                Text { visible: panel.message !== ""; text: panel.message; color: "#f38ba8"; font.pixelSize: 12 }
                Text { visible: panel.confirming; text: "Effacer tout l’historique ? Cette action est irréversible."; color: "#f9e2af"; font.pixelSize: 12 }
                Row {
                    visible: panel.confirming; spacing: 16
                    Text { id: confirmLabel; text: "Confirmer la purge"; color: "#f38ba8"; font.bold: true
                        MouseArea { anchors.fill: parent; onClicked: panel.request("wipe", "") } }
                    Text { id: cancelLabel; text: "Annuler"; color: "#b4befe"; MouseArea { anchors.fill: parent; onClicked: panel.confirming = false } }
                }
                Item {
                    width: parent.width
                    height: Math.max(0, parent.height - y - 36)
                    Text { anchors.centerIn: parent; visible: panel.results.length === 0; text: panel.items.length === 0 ? "Historique vide" : "Aucun résultat textuel"; color: "#a6adc8" }
                    ListView {
                        id: list
                        anchors.fill: parent
                        visible: panel.results.length > 0
                        clip: true; spacing: 6
                        model: panel.results
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: list.width - 12; height: modelData.image && panel.selected === index ? 122 : 66
                            radius: 4
                            color: panel.selected === index ? "#45475a" : "#313244"
                            border.color: panel.selected === index ? "#b4befe" : "transparent"
                            Row {
                                anchors.fill: parent; anchors.margins: 10; spacing: 10
                                Text { text: modelData.image ? "" : "󰦨"; color: "#b4befe"; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 19 }
                                Column {
                                    width: parent.width - 35; spacing: 5
                                    Text { text: modelData.image ? "Image" : "Texte"; color: "#b4befe"; font.bold: true; font.pixelSize: 12 }
                                    Text { width: parent.width; text: modelData.preview; color: "#cdd6f4"; font.pixelSize: 12; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
                                    Image { visible: modelData.image && panel.selected === index && panel.thumbnail !== ""; source: visible ? panel.thumbnail : ""; width: 180; height: 75; fillMode: Image.PreserveAspectFit; asynchronous: true; cache: false }
                                }
                            }
                            MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: mouse => {
                                    panel.selected = index;
                                    if (mouse.button === Qt.RightButton) panel.remove();
                                    else panel.choose();
                                }
                            }
                        }
                    }
                }
                Row {
                    width: parent.width; height: 20
                    Text { text: parent.width < 410 ? "↑ ↓  Entrée  Échap" : "↑ ↓ parcourir   Entrée copier   Ctrl+Suppr retirer   Échap fermer";
                        width: Math.max(0, parent.width - removeLabel.implicitWidth - 8); elide: Text.ElideRight
                        color: "#a6adc8"; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 11 }
                    Item { width: 8; height: 1 }
                    Text { id: removeLabel; text: "Supprimer"; color: "#f38ba8"; font.pixelSize: 12
                        MouseArea { anchors.fill: parent; onClicked: panel.remove() } }
                }
            }
        }
    }
}

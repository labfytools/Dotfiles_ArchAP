import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "../theme"
import "ApplicationsModel.js" as ApplicationsModel

PanelWindow {
    id: menu
    required property var barWindow
    signal menuDismissed()
    signal launchRequested(string desktopId)
    property string errorMessage: ""
    property var allApps: []
    property var favoriteIds: []
    property string selectedCategory: "Toutes"
    property int selectedIndex: 0
    property int navIndex: 0
    property bool closing: false
    readonly property var categoryItems: ApplicationsModel.categories(allApps)
    readonly property var navigation: [{ key: "Favoris", icon: "󰓎" },
        { key: "Toutes", icon: "󰀻" }].concat(categoryItems)
    readonly property var visibleApps: ApplicationsModel.results(
        allApps, selectedCategory, search.text, favoriteIds)
    readonly property bool searchFocused: search.activeFocus
    readonly property bool navigationFocused: navigationList.activeFocus
    readonly property bool gridFocused: grid.activeFocus
    readonly property real cardX: card.x
    readonly property real cardY: card.y
    readonly property real cardWidth: card.width
    readonly property real cardHeight: card.height

    // WHY: an IPC-opened PopupWindow cannot acquire a reliable parent grab here.
    // CONTRACT: this transient layer surface owns focus only while visible,
    // and the transparent outside area consumes the closing click.
    screen: barWindow.screen
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0
    aboveWindows: true
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    WlrLayershell.namespace: "labfy-applications-menu"
    color: "transparent"

    function refreshCatalog() {
        allApps = ApplicationsModel.catalog(DesktopEntries.applications.values);
        if (!favoriteIds.length && selectedCategory === "Favoris") selectedCategory = "Toutes";
    }
    function chooseCategory(key) {
        selectedCategory = key;
        navIndex = navigation.findIndex(item => item.key === key);
        selectedIndex = 0;
        grid.positionViewAtBeginning();
    }
    function currentApp() {
        return selectedIndex >= 0 && selectedIndex < visibleApps.length
            ? visibleApps[selectedIndex] : null;
    }
    function chooseApp() {
        const app = currentApp();
        if (app) launchRequested(app.id);
    }
    function toggleFavorite(id) {
        const had = favoriteIds.includes(id);
        favoriteIds = had ? favoriteIds.filter(value => value !== id) : favoriteIds.concat([id]);
        Quickshell.execDetached(["python3", "-B", backend, "favorites", had ? "remove" : "add", id]);
        if (selectedCategory === "Favoris" && favoriteIds.length === 0) chooseCategory("Toutes");
    }
    function dismiss() {
        if (closing) return;
        // INVARIANT: keep this surface alive through the pointer release so
        // an outside click cannot land on an application or the bar beneath.
        closing = true;
        dismissDelay.start();
    }
    Timer {
        id: dismissDelay
        interval: 150; repeat: false
        onTriggered: { menu.visible = false; menu.menuDismissed(); }
    }
    readonly property string backend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/applications/backend.py"

    onVisibleAppsChanged: selectedIndex = Math.min(selectedIndex, Math.max(0, visibleApps.length - 1))
    Connections {
        target: DesktopEntries
        function onApplicationsChanged() { menu.refreshCatalog(); }
    }
    Process {
        id: favoritesReader
        command: ["python3", "-B", menu.backend, "favorites", "read"]
        stdout: StdioCollector { id: favoritesOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0) { menu.errorMessage = "Favoris indisponibles"; return; }
            try {
                const data = JSON.parse(favoritesOutput.text);
                if (data.exists) {
                    menu.favoriteIds = data.ids;
                } else {
                    const suggested = ApplicationsModel.initialFavorites(menu.allApps);
                    menu.favoriteIds = suggested;
                    Quickshell.execDetached(["python3", "-B", menu.backend, "favorites", "seed"]
                        .concat(suggested));
                }
                menu.selectedCategory = menu.favoriteIds.some(id => menu.allApps.some(app => app.id === id))
                    ? "Favoris" : "Toutes";
                menu.navIndex = menu.selectedCategory === "Favoris" ? 0 : 1;
            } catch (_) { menu.errorMessage = "Favoris invalides"; }
        }
    }
    Component.onCompleted: {
        refreshCatalog();
        favoritesReader.running = true;
    }
    // The Wayland surface exists after completion; focus at the next frame.
    Timer { interval: 120; running: true; repeat: false; onTriggered: search.forceActiveFocus() }

    Item {
        anchors.fill: parent
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape) { menu.dismiss(); event.accepted = true; }
        }
        MouseArea { anchors.fill: parent; onClicked: menu.dismiss() }
        Rectangle {
            id: card
            x: 16
            y: menu.barWindow.height + 12
            width: Math.max(0, Math.min(680, parent.width - x - 16))
            height: Math.max(0, Math.min(560, parent.height - y - 16))
            radius: 4
            color: Theme.popupBackground
            border.color: Theme.outline
            border.width: 1
            MouseArea { anchors.fill: parent; onClicked: {} }

            Column {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12
                Row {
                    width: parent.width; height: 26
                    spacing: 8
                    Text {
                        text: "󰀻"; color: Theme.lavender
                        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 24
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "Applications"; color: Theme.foreground
                        font.pixelSize: 17; font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Rectangle {
                    width: parent.width; height: 40; radius: 4
                    color: Theme.inputBackground
                    border.color: search.activeFocus ? Theme.lavender : Theme.inputBorder
                    TextField {
                        id: search
                        anchors.fill: parent; anchors.margins: 2
                        placeholderText: "Rechercher une application…"
                        color: Theme.foreground
                        placeholderTextColor: Theme.secondaryForeground
                        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 13
                        background: Item {}
                        onTextChanged: { menu.selectedIndex = 0; grid.positionViewAtBeginning(); }
                        Keys.onPressed: event => {
                            if (event.key === Qt.Key_Escape) { menu.dismiss(); event.accepted = true; }
                            else if (event.key === Qt.Key_Backtab ||
                                     (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier))) {
                                grid.forceActiveFocus(); event.accepted = true;
                            } else if (event.key === Qt.Key_Down) {
                                grid.forceActiveFocus(); menu.selectedIndex = 0; event.accepted = true;
                            } else if (event.key === Qt.Key_Tab) {
                                navigationList.forceActiveFocus(); event.accepted = true;
                            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                menu.chooseApp(); event.accepted = true;
                            }
                        }
                    }
                }
                Text {
                    visible: menu.errorMessage !== ""
                    width: parent.width; text: menu.errorMessage
                    color: Theme.danger; font.pixelSize: 12; elide: Text.ElideRight
                }
                Item {
                    width: parent.width
                    height: Math.max(0, parent.height - y)
                    Rectangle {
                        id: sidebar
                        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
                        width: Math.min(170, Math.max(126, parent.width * 0.28))
                        radius: 4; color: Theme.buttonBackground
                        ListView {
                            id: navigationList
                            anchors.fill: parent; anchors.margins: 5
                            clip: true; spacing: 3
                            model: menu.navigation
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                            Keys.onPressed: event => {
                                if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                                    menu.navIndex = Math.max(0, Math.min(menu.navigation.length - 1,
                                        menu.navIndex + (event.key === Qt.Key_Down ? 1 : -1)));
                                    positionViewAtIndex(menu.navIndex, ListView.Contain);
                                    event.accepted = true;
                                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                    menu.chooseCategory(menu.navigation[menu.navIndex].key); event.accepted = true;
                                } else if (event.key === Qt.Key_Backtab ||
                                           (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier))) {
                                    search.forceActiveFocus(); event.accepted = true;
                                } else if (event.key === Qt.Key_Tab) {
                                    grid.forceActiveFocus(); event.accepted = true;
                                } else if (event.key === Qt.Key_Escape) {
                                    menu.dismiss(); event.accepted = true;
                                }
                            }
                            delegate: Rectangle {
                                required property var modelData
                                required property int index
                                width: navigationList.width; height: 37; radius: 4
                                color: menu.selectedCategory === modelData.key ? Theme.buttonPressed
                                    : navPointer.containsMouse ? Theme.buttonHover : "transparent"
                                border.color: navigationList.activeFocus && menu.navIndex === index
                                    ? Theme.lavender : "transparent"
                                Row {
                                    anchors.fill: parent; anchors.leftMargin: 10; spacing: 8
                                    Text { text: modelData.icon; color: Theme.lavender
                                        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 16
                                        anchors.verticalCenter: parent.verticalCenter }
                                    Text { text: modelData.key === "Toutes" ? "Toutes les applications" : modelData.key
                                        width: Math.max(0, parent.width - x - 5); elide: Text.ElideRight
                                        color: Theme.foreground; font.pixelSize: 12
                                        anchors.verticalCenter: parent.verticalCenter }
                                }
                                MouseArea { id: navPointer; anchors.fill: parent; hoverEnabled: true
                                    onClicked: { menu.chooseCategory(modelData.key); navigationList.forceActiveFocus(); } }
                            }
                        }
                    }
                    Item {
                        anchors.left: sidebar.right; anchors.leftMargin: 12
                        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
                        Text {
                            anchors.centerIn: parent
                            visible: menu.visibleApps.length === 0
                            text: search.text ? "Aucun résultat" : "Aucune application"
                            color: Theme.secondaryForeground; font.pixelSize: 14
                        }
                        GridView {
                            id: grid
                            anchors.fill: parent
                            visible: menu.visibleApps.length > 0
                            clip: true
                            model: menu.visibleApps
                            cellWidth: Math.max(80, Math.floor(width / (width >= 420 ? 4 : 3)))
                            cellHeight: 104
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                            Keys.onPressed: event => {
                                const columns = Math.max(1, Math.floor(width / cellWidth));
                                let next = menu.selectedIndex;
                                if (event.key === Qt.Key_Left) next--;
                                else if (event.key === Qt.Key_Right) next++;
                                else if (event.key === Qt.Key_Up) next -= columns;
                                else if (event.key === Qt.Key_Down) next += columns;
                                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                    menu.chooseApp(); event.accepted = true; return;
                                } else if (event.key === Qt.Key_Space) {
                                    const app = menu.currentApp(); if (app) menu.toggleFavorite(app.id);
                                    event.accepted = true; return;
                                } else if (event.key === Qt.Key_Backtab ||
                                           (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier))) {
                                    navigationList.forceActiveFocus(); event.accepted = true; return;
                                } else if (event.key === Qt.Key_Tab) {
                                    search.forceActiveFocus(); event.accepted = true; return;
                                } else if (event.key === Qt.Key_Escape) {
                                    menu.dismiss(); event.accepted = true; return;
                                } else return;
                                menu.selectedIndex = Math.max(0, Math.min(menu.visibleApps.length - 1, next));
                                positionViewAtIndex(menu.selectedIndex, GridView.Contain);
                                event.accepted = true;
                            }
                            delegate: Item {
                                required property var modelData
                                required property int index
                                width: grid.cellWidth; height: grid.cellHeight
                                Rectangle {
                                    anchors.fill: parent; anchors.margins: 3; radius: 4
                                    color: menu.selectedIndex === index && grid.activeFocus
                                        ? Theme.buttonPressed : appPointer.containsMouse ? Theme.buttonHover : "transparent"
                                    border.color: menu.selectedIndex === index && grid.activeFocus
                                        ? Theme.lavender : "transparent"
                                }
                                Image {
                                    id: appIcon
                                    anchors.top: parent.top; anchors.topMargin: 12
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: 46; height: 46
                                    source: modelData.icon.startsWith("/") ? "file://" + modelData.icon
                                        : Quickshell.iconPath(modelData.icon || "application-x-executable",
                                            "application-x-executable")
                                    sourceSize.width: 46; sourceSize.height: 46
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                }
                                Text {
                                    visible: appIcon.status === Image.Error
                                    anchors.centerIn: appIcon
                                    text: "󰀻"; color: Theme.lavender
                                    font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 32
                                }
                                Text {
                                    anchors.top: appIcon.bottom; anchors.topMargin: 5
                                    anchors.left: parent.left; anchors.right: parent.right
                                    anchors.leftMargin: 6; anchors.rightMargin: 6
                                    text: modelData.name; color: Theme.foreground
                                    font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter
                                    maximumLineCount: 2; wrapMode: Text.Wrap; elide: Text.ElideRight
                                }
                                MouseArea {
                                    id: appPointer; anchors.fill: parent; hoverEnabled: true
                                    onClicked: {
                                        menu.selectedIndex = index;
                                        menu.launchRequested(modelData.id);
                                    }
                                    ToolTip.visible: containsMouse && modelData.name.length > 18
                                    ToolTip.text: modelData.name
                                    ToolTip.delay: 600
                                }
                                Rectangle {
                                    anchors.right: parent.right; anchors.top: parent.top
                                    anchors.rightMargin: 5; anchors.topMargin: 4
                                    width: 24; height: 24; radius: 4
                                    color: starPointer.containsMouse ? Theme.buttonPressed : Theme.buttonBackground
                                    Text { anchors.centerIn: parent
                                        text: menu.favoriteIds.includes(modelData.id) ? "" : "󰓏"
                                        color: Theme.lavender
                                        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 13 }
                                    MouseArea { id: starPointer; anchors.fill: parent; hoverEnabled: true
                                        onClicked: menu.toggleFavorite(modelData.id)
                                        ToolTip.visible: containsMouse
                                        ToolTip.text: menu.favoriteIds.includes(modelData.id)
                                            ? "Retirer des favoris" : "Ajouter aux favoris"
                                        ToolTip.delay: 600 }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

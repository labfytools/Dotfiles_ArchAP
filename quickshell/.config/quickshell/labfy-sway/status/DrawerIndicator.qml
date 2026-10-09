import QtQuick
import Quickshell
import Quickshell.I3
import Quickshell.Wayland
import "../components"
import "../theme"

Item {
    id: indicator
    required property var service
    required property var barWindow
    required property string output
    required property bool authenticationActive
    property int previousFocus: 0
    property int selectedIndex: 0
    property int selectedAction: 0
    property real anchorX: 8
    readonly property bool open: popup.visible
    signal opened()

    visible: !!service && service.entries.length > 0
    width: visible ? iconRow.implicitWidth + 4 : 0
    height: 26
    onVisibleChanged: if (!visible) popup.visible = false
    function close(restore) {
        if (!popup.visible) return;
        popup.visible = false;
        if (restore && !authenticationActive && previousFocus > 0)
            Qt.callLater(() => I3.dispatch("[con_id=" + previousFocus + "] focus"));
    }
    function toggle() {
        if (authenticationActive) return;
        if (popup.visible) { close(true); return; }
        opened();
        previousFocus = service.focusedId;
        selectedIndex = 0;
        selectedAction = 0;
        service.refresh();
        // Le panneau et la barre utilisent la même sortie. Les coordonnées
        // locales de la barre plus sa marge évitent toute origine globale.
        anchorX = mapToItem(null, 0, 0).x + barWindow.margins.left;
        popup.visible = true;
        Qt.callLater(() => keys.forceActiveFocus());
    }
    function perform(entry, action) {
        if (!entry || entry.group || service.busy || authenticationActive) return;
        // WHY: la surface popup libère le focus avant scratchpad show/focus.
        close(false);
        Qt.callLater(() => service.act(action, entry.id, output));
    }

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: popup.visible || pointer.containsMouse ? Theme.border : "transparent"
    }
    Row {
        id: iconRow
        anchors.centerIn: parent
        spacing: 3
        NerdIcon { text: "󰅖"; color: Theme.teal; font.pixelSize: 19 }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: indicator.service ? String(indicator.service.entries.length) : ""
            color: Theme.foreground
            font.pixelSize: 11
        }
    }
    MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; onClicked: indicator.toggle() }
    StatusTooltip { target: indicator; hovered: pointer.containsMouse && !popup.visible
        message: "Tiroir de fenêtres" }

    PanelWindow {
        id: popup
        screen: indicator.barWindow.screen
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        exclusiveZone: 0
        aboveWindows: true
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
        WlrLayershell.namespace: "labfy-scratchpad-drawer"
        visible: false
        color: "transparent"
        MouseArea { anchors.fill: parent; onClicked: indicator.close(true) }
        Rectangle {
            anchors.top: parent.top
            anchors.topMargin: 40
            x: Math.max(8, Math.min(indicator.anchorX, popup.width - width - 8))
            width: Math.min(420, Math.max(0, popup.width - 16))
            height: Math.max(0, Math.min(540, popup.height - 48, body.implicitHeight + 24))
            radius: 5
            color: Theme.popupBackground
            border.color: Theme.outline
            FocusScope {
                id: keys
                anchors.fill: parent
                focus: true
                Keys.onPressed: event => {
                    const count = indicator.service ? indicator.service.entries.length : 0;
                    if (event.key === Qt.Key_Escape) indicator.close(true);
                    else if (event.key === Qt.Key_Down && count)
                        indicator.selectedIndex = (indicator.selectedIndex + 1) % count;
                    else if (event.key === Qt.Key_Up && count)
                        indicator.selectedIndex = (indicator.selectedIndex + count - 1) % count;
                    else if (event.key === Qt.Key_Left || event.key === Qt.Key_Right)
                        indicator.selectedAction = 1 - indicator.selectedAction;
                    else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        const entry = indicator.service.entries[indicator.selectedIndex];
                        if (entry) indicator.perform(entry, indicator.selectedAction === 1
                            ? "release" : entry.shown ? "hide" : "show");
                    } else return;
                    event.accepted = true;
                }
                Flickable {
                    anchors.fill: parent
                    anchors.margins: 12
                    contentWidth: width
                    contentHeight: body.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Column {
                        id: body
                        width: parent.width
                        spacing: 8
                        Text { text: "Tiroir de fenêtres"; color: Theme.foreground
                            font.pixelSize: 15; font.bold: true }
                        Text { visible: !!indicator.service && indicator.service.error.length > 0
                            text: indicator.service ? indicator.service.error : ""; color: Theme.red
                            width: parent.width; wrapMode: Text.Wrap }
                        Repeater {
                            model: indicator.service ? indicator.service.entries : []
                            Rectangle {
                                required property var modelData
                                required property int index
                                readonly property var desktop: DesktopEntries.heuristicLookup(modelData.app)
                                width: body.width
                                height: 68
                                radius: 4
                                color: index === indicator.selectedIndex ? Theme.border : Theme.buttonBackground
                                Image {
                                    id: appIcon
                                    x: 8; y: 8; width: 26; height: 26
                                    source: desktop && desktop.icon
                                        ? (desktop.icon.startsWith("/") ? "file://" + desktop.icon
                                            : Quickshell.iconPath(desktop.icon, "application-x-executable"))
                                        : Quickshell.iconPath("application-x-executable")
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                }
                                Text { anchors.centerIn: appIcon; visible: appIcon.status === Image.Error
                                    text: "󰀻"; color: Theme.teal; font.pixelSize: 19 }
                                Text { x: 42; y: 6; width: parent.width - 50
                                    text: desktop ? desktop.name : modelData.app
                                    color: Theme.foreground; font.bold: true; font.pixelSize: 12
                                    elide: Text.ElideRight; textFormat: Text.PlainText }
                                Text { x: 42; y: 24; width: parent.width - 50
                                    text: modelData.title; color: Theme.secondaryForeground
                                    font.pixelSize: 11; elide: Text.ElideRight; textFormat: Text.PlainText }
                                Text { x: 8; y: 49
                                    text: modelData.group ? "Groupe : action individuelle indisponible"
                                        : modelData.shown ? "Affichée" : "Masquée"
                                    color: Theme.secondaryForeground; font.pixelSize: 10 }
                                Rectangle {
                                    x: parent.width - 205; y: 44; width: 85; height: 20; radius: 3
                                    color: actionPointer.containsMouse ? Theme.buttonHover : Theme.border
                                    border.width: index === indicator.selectedIndex
                                        && indicator.selectedAction === 0 ? 1 : 0
                                    border.color: Theme.teal
                                    Text { anchors.centerIn: parent; text: modelData.shown ? "Masquer" : "Afficher"
                                        color: Theme.foreground; font.pixelSize: 10 }
                                    MouseArea { id: actionPointer; anchors.fill: parent; hoverEnabled: true
                                        enabled: !modelData.group && !indicator.service.busy
                                        onClicked: indicator.perform(modelData, modelData.shown ? "hide" : "show") }
                                }
                                Rectangle {
                                    x: parent.width - 114; y: 44; width: 106; height: 20; radius: 3
                                    color: releasePointer.containsMouse ? Theme.buttonHover : Theme.border
                                    border.width: index === indicator.selectedIndex
                                        && indicator.selectedAction === 1 ? 1 : 0
                                    border.color: Theme.teal
                                    Text { anchors.centerIn: parent; text: "Remettre ici"
                                        color: Theme.foreground; font.pixelSize: 10 }
                                    MouseArea { id: releasePointer; anchors.fill: parent; hoverEnabled: true
                                        enabled: !modelData.group && !indicator.service.busy
                                        onClicked: indicator.perform(modelData, "release") }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

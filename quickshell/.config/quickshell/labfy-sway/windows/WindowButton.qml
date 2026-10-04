import QtQuick
import Quickshell
import Quickshell.I3
import "../components"

Rectangle {
    id: button

    required property var windowInfo
    required property bool primary
    required property int maxPrimaryWidth
    property bool menuOpen: false
    signal menuRequested(var item, var windowInfo)

    readonly property string appName: windowInfo.appId || "Fenêtre"
    readonly property string fullTitle: windowInfo.title || appName
    readonly property string glyph: {
        const app = windowInfo.appKey || "";
        if (app.includes("firefox")) return "";
        if (app.includes("kitty") || app.includes("terminal")
                || app.includes("foot") || app.includes("alacritty")) return "";
        return "";
    }

    width: primary
        ? Math.min(maxPrimaryWidth, Math.max(26, icon.implicitWidth + title.implicitWidth + 22))
        : 26
    height: 26
    radius: 4
    color: primary ? "#45475a" : pointer.containsMouse ? "#45475a" : "#313244"
    border.width: primary ? 1 : 0
    border.color: "#cba6f7"

    NerdIcon {
        id: icon
        anchors.left: parent.left
        anchors.leftMargin: primary ? 8 : 0
        anchors.verticalCenter: parent.verticalCenter
        width: primary ? implicitWidth : parent.width
        text: button.glyph
        // CONTRACT: le fallback reste centré dans les boutons secondaires de 26 px.
        font.pixelSize: 16
    }

    Text {
        id: title
        visible: button.primary
        anchors.left: icon.right
        anchors.leftMargin: 6
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        text: button.fullTitle
        color: "#cdd6f4"
        font.pixelSize: 13
        elide: Text.ElideRight
        maximumLineCount: 1
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton

        onContainsMouseChanged: {
            if (containsMouse && !button.primary && !button.menuOpen)
                tooltipDelay.start();
            else {
                tooltipDelay.stop();
                button.showTooltip = false;
            }
        }

        onClicked: mouse => {
            button.showTooltip = false;
            if (mouse.button === Qt.RightButton)
                button.menuRequested(button, button.windowInfo);
            else
                I3.dispatch("[con_id=" + button.windowInfo.id + "] focus");
        }
    }

    property bool showTooltip: false

    Timer {
        id: tooltipDelay
        interval: 400
        repeat: false
        onTriggered: button.showTooltip = true
    }

    PopupWindow {
        anchor.item: button
        anchor.edges: Edges.Bottom | Edges.Left
        anchor.gravity: Edges.Bottom | Edges.Right
        // Une marge négative place le popup sous le bouton avec 6 px d'espace.
        anchor.margins.bottom: -6
        visible: button.showTooltip && !button.menuOpen
        grabFocus: false
        color: "transparent"
        implicitWidth: 300
        implicitHeight: tooltipContent.implicitHeight + 16

        Rectangle {
            anchors.fill: parent
            radius: 4
            color: "#313244"
            border.color: "#45475a"

            Column {
                id: tooltipContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 8
                spacing: 3

                Text {
                    text: button.appName
                    color: "#cdd6f4"
                    font.pixelSize: 12
                    font.bold: true
                }
                Text {
                    width: parent.width
                    text: button.fullTitle
                    color: "#a6adc8"
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }
            }
        }
    }
}

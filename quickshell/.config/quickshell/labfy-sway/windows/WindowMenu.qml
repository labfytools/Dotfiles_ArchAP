import QtQuick
import Quickshell
import Quickshell.I3

PopupWindow {
    id: menu

    property var anchorItem: null
    property var selectedWindow: null
    property var windows: []
    readonly property var appWindows: selectedWindow
        ? windows.filter(window => window.appKey === selectedWindow.appKey) : []
    readonly property var entry: selectedWindow
        ? DesktopEntries.heuristicLookup(selectedWindow.appId) : null
    readonly property var actions: entry ? entry.actions : []

    anchor.item: anchorItem
    anchor.edges: Edges.Bottom | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    // Une marge négative place le menu sous le bouton avec 6 px d'espace.
    anchor.margins.bottom: -6

    implicitWidth: 300
    implicitHeight: content.implicitHeight + 24
    visible: false
    // Laisser les boutons de barre recevoir les clics d'exclusion XOR.
    grabFocus: false
    color: "transparent"

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: "#1e1e2e"
        border.color: "#45475a"

        Column {
            id: content
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 12
            spacing: 7

            Text {
                width: parent.width
                text: menu.entry ? menu.entry.name
                    : menu.selectedWindow ? menu.selectedWindow.appId : ""
                color: "#cdd6f4"
                font.pixelSize: 15
                font.bold: true
                elide: Text.ElideRight
            }

            Text {
                text: "Fenêtres ouvertes"
                color: "#a6adc8"
                font.pixelSize: 11
            }

            Repeater {
                model: menu.appWindows

                Rectangle {
                    required property var modelData
                    width: content.width
                    height: 30
                    radius: 4
                    color: pointer.containsMouse ? "#45475a" : "#313244"

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.title
                        color: "#cdd6f4"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }

                    MouseArea {
                        id: pointer
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            menu.visible = false;
                            I3.dispatch("[con_id=" + modelData.id + "] focus");
                        }
                    }
                }
            }

            Text {
                visible: menu.actions.length > 0
                text: "Actions"
                color: "#a6adc8"
                font.pixelSize: 11
            }

            Repeater {
                model: menu.actions

                Rectangle {
                    required property var modelData
                    width: content.width
                    height: 30
                    radius: 4
                    color: actionPointer.containsMouse ? "#45475a" : "#313244"

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.name
                        color: "#cdd6f4"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }

                    MouseArea {
                        id: actionPointer
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            menu.visible = false;
                            modelData.execute();
                        }
                    }
                }
            }
        }
    }
}

import QtQuick
import Quickshell
import Quickshell.I3
import "../theme"

PopupWindow {
    id: menu

    property var anchorItem: null
    property var selectedWindow: null
    property var windows: []
    signal storeRequested(int id)
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
        color: Theme.popupBackground
        border.color: Theme.outline

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
                color: Theme.foreground
                font.pixelSize: 15
                font.bold: true
                elide: Text.ElideRight
            }

            Text {
                text: "Fenêtres ouvertes"
                color: Theme.secondaryForeground
                font.pixelSize: 11
            }

            Repeater {
                model: menu.appWindows

                Rectangle {
                    required property var modelData
                    width: content.width
                    height: 30
                    radius: 4
                    color: pointer.containsMouse ? Theme.border : Theme.buttonBackground

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.title
                        color: Theme.foreground
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

            Rectangle {
                width: content.width
                height: 32
                radius: 4
                color: storePointer.containsMouse ? Theme.border : Theme.buttonBackground
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Ranger dans le tiroir"
                    color: Theme.foreground
                    font.pixelSize: 12
                }
                MouseArea {
                    id: storePointer
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        const id = menu.selectedWindow ? menu.selectedWindow.id : 0;
                        menu.visible = false;
                        if (id > 0) menu.storeRequested(id);
                    }
                }
            }

            Text {
                visible: menu.actions.length > 0
                text: "Actions"
                color: Theme.secondaryForeground
                font.pixelSize: 11
            }

            Repeater {
                model: menu.actions

                Rectangle {
                    required property var modelData
                    width: content.width
                    height: 30
                    radius: 4
                    color: actionPointer.containsMouse ? Theme.border : Theme.buttonBackground

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.name
                        color: Theme.foreground
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

import QtQuick

Rectangle {
    id: button
    property string label: ""
    property bool danger: false
    signal clicked()
    implicitWidth: caption.implicitWidth + 20
    implicitHeight: 30
    radius: 4
    color: !enabled ? "#313244" : pointer.containsMouse ? "#585b70" : "#45475a"
    opacity: enabled ? 1 : 0.55
    Text {
        id: caption
        anchors.centerIn: parent
        text: button.label
        color: button.danger ? "#f38ba8" : "#cdd6f4"
        font.pixelSize: 12
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        enabled: button.enabled
        onClicked: button.clicked()
    }
}

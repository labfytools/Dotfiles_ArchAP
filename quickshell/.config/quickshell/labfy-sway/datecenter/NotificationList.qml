import QtQuick

Item {
    id: list
    required property var service
    property bool confirmClear: false
    readonly property var rows: service.records
    // CONTRACT: l'état vide conserve une vraie zone sans réserver la place du player.
    // La liste seule défile au-delà de 307 px de contenu.
    implicitHeight: rows.length ? 28 + Math.min(307, rows.length * 94) : 80
    height: implicitHeight
    Timer { interval: 5000; running: list.confirmClear; onTriggered: list.confirmClear = false }
    Text { id: title; text: "Notifications"; color: "#cdd6f4"; font.pixelSize: 14; font.bold: true }
    Text {
        anchors.right: parent.right
        text: list.confirmClear ? "Confirmer : tout effacer" : "Tout effacer"
        visible: list.rows.length > 0
        color: confirm.containsMouse ? "#f38ba8" : "#a6adc8"
        font.pixelSize: 11
        MouseArea {
            id: confirm
            anchors.fill: parent
            hoverEnabled: true
            onClicked: {
                if (list.confirmClear) { list.service.clearAll(); list.confirmClear = false; }
                else list.confirmClear = true;
            }
        }
    }
    Text {
        visible: list.rows.length === 0
        anchors.top: title.bottom; anchors.topMargin: 8
        text: "Aucune notification récente"
        color: "#a6adc8"; font.pixelSize: 12
    }
    ListView {
        anchors.top: title.bottom; anchors.topMargin: 8
        anchors.left: parent.left; anchors.right: parent.right
        height: parent.height - title.height - 8
        visible: list.rows.length > 0
        clip: true; spacing: 7; boundsBehavior: Flickable.StopAtBounds
        model: list.rows
        delegate: NotificationItem {
            required property var modelData
            width: ListView.view.width
            notification: modelData
            service: list.service
        }
    }
}

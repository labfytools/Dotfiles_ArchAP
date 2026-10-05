import QtQuick
import Quickshell
import "../theme"

PopupWindow {
    id: popup
    required property var barWindow
    required property var clockItem
    required property var notificationService
    property bool opening: false

    // L'horloge reste le point d'ancrage du panneau.
    anchor.window: barWindow
    anchor.rect.x: clockItem.x + clockItem.width / 2 - implicitWidth / 2
    anchor.rect.y: barWindow.height + 6
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    implicitWidth: 450
    // WHY: Column.implicitHeight conservait la plus grande hauteur atteinte après
    // suppression d'items ; childrenRect.height reflète les zones visibles.
    // INVARIANT: le Player conserve ses 116 px et seule la liste fait défiler ses items.
    implicitHeight: Math.min(600, content.childrenRect.height + 32)
    visible: false
    // CONTRACT: seule la liste effectivement visible vaut consultation.
    onVisibleChanged: notificationService.setDateCenterVisible(visible)
    // Laisser les boutons de barre recevoir les clics d'exclusion XOR.
    grabFocus: false
    color: "transparent"
    function requestOpen() { opening = false; visible = true; }
    function requestClose() { opening = false; visible = false; }

    SystemClock { id: clock; precision: SystemClock.Minutes }
    Connections {
        target: AppearanceController
        function onTimezoneRevisionChanged() { clock.enabled = false; clock.enabled = true; }
    }
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
            anchors.margins: 16
            spacing: 14
            Text {
                text: clock.date.toLocaleDateString(Qt.locale("fr_FR"), "dddd d MMMM")
                color: Theme.accentForeground; font.pixelSize: 17; font.bold: true
            }
            MediaPlayer { width: parent.width }
            NotificationList { width: parent.width; service: popup.notificationService }
        }
    }
}

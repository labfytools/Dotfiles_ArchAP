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
    anchor.rect.x: Math.max(0, Math.min(barWindow.width - implicitWidth,
        clockItem.x + clockItem.width / 2 - implicitWidth / 2))
    anchor.rect.y: barWindow.height + 6
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    // CONTRACT: preserve the fixed player; only the notification viewport
    // yields space on fractional-scale and small outputs, below the bar.
    readonly property real availableHeight: Math.max(0, Math.min(600,
        barWindow.screen.height - barWindow.height - 6 - 16))
    implicitWidth: Math.min(450, Math.max(0, barWindow.screen.width - 32))
    // WHY: Column.implicitHeight conservait la plus grande hauteur atteinte après
    // suppression d'items ; childrenRect.height reflète les zones visibles.
    // INVARIANT: le Player conserve ses 116 px et seule la liste fait défiler ses items.
    implicitHeight: Math.min(600, content.childrenRect.height + 32)
    visible: false
    // CONTRACT: seule la liste effectivement visible vaut consultation.
    onVisibleChanged: notificationService.setDateCenterVisible(visible)
    // WHY: sans grab, les clics hors du PopupWindow ne lui sont jamais signalés.
    // CONTRACT: le grab est actif dès l'ouverture ; QuickShell remet visible
    // à false lorsque le compositeur ferme le popup sur clic extérieur.
    // INVARIANT: ne pas changer le grab pendant que le panneau est visible.
    grabFocus: true
    color: "transparent"
    function requestOpen() { opening = false; visible = true; }
    function requestClose() { opening = false; visible = false; }
    Keys.onEscapePressed: event => { requestClose(); event.accepted = true; }

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
                id: dateHeading
                text: clock.date.toLocaleDateString(Qt.locale("fr_FR"), "dddd d MMMM")
                color: Theme.accentForeground; font.pixelSize: 17; font.bold: true
            }
            MediaPlayer { id: mediaCard; width: parent.width }
            NotificationList {
                width: parent.width
                service: popup.notificationService
                maximumHeight: Math.max(0, popup.availableHeight - 32 - dateHeading.implicitHeight
                    - (mediaCard.visible ? mediaCard.height + 2 * content.spacing : content.spacing))
            }
        }
    }
}

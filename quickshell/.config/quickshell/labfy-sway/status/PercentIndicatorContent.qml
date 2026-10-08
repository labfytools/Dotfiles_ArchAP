import QtQuick
import "../components"
import "../theme"
import "PercentPresentation.js" as PercentPresentation

Item {
    id: content
    required property string glyph
    required property bool available
    required property int percent
    property color tint: Theme.foreground
    // CONTRACT: l'accent colore le pictogramme ; la valeur reste du texte,
    // sauf lorsqu'un indicateur transmet déjà une alerte par sa valeur.
    property color valueTint: Theme.foreground
    // Les glyphes Nerd Font ont des silhouettes différentes à taille égale.
    property int glyphPixelSize: 22
    readonly property int iconSlotWidth: 22
    // Cinq caractères monospace à 12 px (« 100 % ») tiennent dans 38 px.
    readonly property int valueSlotWidth: 38
    readonly property int iconValueGap: 4
    width: 2 + iconSlotWidth + iconValueGap + valueSlotWidth
    height: 26

    NerdIcon {
        width: content.iconSlotWidth
        height: parent.height
        anchors.left: parent.left
        anchors.leftMargin: 2
        anchors.verticalCenter: parent.verticalCenter
        text: content.glyph
        font.pixelSize: content.glyphPixelSize
        color: content.tint
    }
    Text {
        anchors.left: parent.left
        anchors.leftMargin: 2 + content.iconSlotWidth + content.iconValueGap
        anchors.verticalCenter: parent.verticalCenter
        width: content.valueSlotWidth
        horizontalAlignment: Text.AlignLeft
        text: PercentPresentation.label(content.available, content.percent)
        color: content.valueTint
        font.family: "JetBrainsMono Nerd Font Mono"
        font.pixelSize: 12
    }
}

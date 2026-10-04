import QtQuick
import "../theme"

Text {
    font.family: "JetBrainsMono Nerd Font Mono"
    // CONTRACT: taille de base des glyphes dans les zones de barre de 26 px ; les contextes spéciaux la surchargent.
    font.pixelSize: 18
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    color: Theme.foreground
}

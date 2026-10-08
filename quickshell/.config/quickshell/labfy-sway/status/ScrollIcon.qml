import QtQuick
import Quickshell
import "../theme"
import "ScrollSteps.js" as ScrollSteps

Item {
    id: iconButton
    required property string glyph
    required property string label
    required property int percent
    property int glyphPixelSize: 22
    property color glyphColor: Theme.foreground
    property bool available: false
    signal adjusted(int steps)
    // CONTRACT: la hitbox et la valeur partagent la même largeur stable que
    // la batterie ; le texte débute à 4 px de l'icône, sans vide variable.
    width: content.width
    height: 26
    property var scrollState: ({ remainder: 0, source: "" })
    // CONTRACT: le chemin Qt et le diagnostic injecté traversent exactement
    // la même accumulation et le même signal vers le contrôle existant.
    function applyWheel(pixel, angle, inverted, phase, touchpad) {
        if (!available) return;
        const result = ScrollSteps.advance(scrollState,
            pixel, angle, inverted, phase, touchpad);
        scrollState = result;
        if (result.steps) adjusted(result.steps);
        return result;
    }
    Accessible.role: Accessible.Button
    Accessible.name: label

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: pointer.containsMouse ? Theme.border : "transparent"
    }
    PercentIndicatorContent {
        id: content
        glyph: iconButton.glyph
        available: iconButton.available
        percent: iconButton.percent
        tint: iconButton.available ? iconButton.glyphColor : Theme.disabledForeground
        valueTint: iconButton.available ? Theme.foreground : Theme.disabledForeground
        glyphPixelSize: iconButton.glyphPixelSize
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        hoverEnabled: true
    }
    StatusTooltip {
        target: iconButton
        hovered: pointer.containsMouse
        message: iconButton.available ? iconButton.label + " : " + iconButton.percent
            + " %\nDéfiler pour régler par pas de 1 %" : iconButton.label + " indisponible"
    }
    WheelHandler {
        target: null
        invertible: false
        // Qt n'accepte que Mouse par défaut : activer explicitement TouchPad.
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        // WHY: le handler est limité à la largeur de cet indicateur ; aucun autre
        // élément de la barre ne transforme un mouvement en réglage.
        onWheel: event => {
            // Qt Wayland peut exposer un geste à deux doigts sans pixelDelta ;
            // les petits angleDelta restent donc classés comme touchpad.
            const touchpad = event.pixelDelta.y !== 0
                || (event.device && event.device.type === PointerDevice.TouchPad)
                || (event.angleDelta.y !== 0 && Math.abs(event.angleDelta.y) < 120);
            const result = iconButton.applyWheel(event.pixelDelta.y,
                event.angleDelta.y, event.inverted, event.phase, touchpad);
            if (Quickshell.env("LABFY_SCROLL_DEBUG") === "1")
                console.log("Scroll", iconButton.label, "pixel", event.pixelDelta.y,
                    "angle", event.angleDelta.y, "phase", event.phase,
                    "inverted", event.inverted, "touchpad", touchpad,
                    "steps", result ? result.steps : 0);
        }
    }
}

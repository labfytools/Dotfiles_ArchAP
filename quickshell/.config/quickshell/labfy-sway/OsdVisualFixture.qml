import Quickshell
import Quickshell.Wayland
import "osd"
import "theme"

// Données de démonstration uniquement : aucun backend audio ni rétroéclairage.
ShellRoot {
    // Fond de démonstration neutre sous la carte translucide : la capture ne
    // révèle aucun pixel du bureau ni d'une application réelle.
    PanelWindow {
        screen: Quickshell.screens[0]
        anchors { left: true; bottom: true }
        margins.left: Math.max(0, Math.round((screen.width - implicitWidth) / 2))
        margins.bottom: Math.min(40, Math.max(8, Math.round(screen.height / 20)))
        implicitWidth: Math.min(320, Math.max(1, screen.width - 16))
        implicitHeight: 80
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        WlrLayershell.namespace: "labfy-osd-visual-backdrop"
        mask: Region { width: 0; height: 0 }
        color: Theme.surface0
    }
    OsdWindow {
        hostScreen: Quickshell.screens[0]
        kind: "brightness"
        percent: 42
        muted: false
    }
}

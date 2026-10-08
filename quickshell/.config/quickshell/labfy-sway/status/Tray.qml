import QtQuick
import Quickshell.Services.SystemTray

Row {
    id: tray
    required property var barWindow
    spacing: 4
    // Le modèle natif suit les inscriptions et retraits D-Bus sans scrutation.
    Repeater {
        model: SystemTray.items
        delegate: TrayItem {
            required property var modelData
            item: modelData
            barWindow: tray.barWindow
        }
    }
}

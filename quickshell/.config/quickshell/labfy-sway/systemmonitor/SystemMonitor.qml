import QtQuick
import Quickshell
import "../components"

PopupWindow {
    id: popup
    required property var barWindow

    anchor.window: barWindow
    anchor.rect.x: barWindow.width - implicitWidth - 8
    anchor.rect.y: barWindow.height + 6
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right

    implicitWidth: 400
    implicitHeight: content.implicitHeight + 32
    visible: false
    // Le panneau est informatif ; laisser les boutons de barre recevoir les clics XOR.
    grabFocus: false
    color: "transparent"

    SystemMetrics { id: metrics; active: popup.visible }

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: "#1e1e2e"
        border.color: "#45475a"

        Column {
            id: content
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 16
            spacing: 16

            Row {
                spacing: 8
                NerdIcon { text: "󰍛"; font.pixelSize: 18 }
                Text { text: "Moniteur système"; color: "#cdd6f4"; font.pixelSize: 16; font.bold: true }
            }

            MetricRow {
                label: "CPU"
                percentage: metrics.cpuPercent
                value: (metrics.cpuPercent >= 0 ? Math.round(metrics.cpuPercent) + " %" : "—")
                    + (metrics.cpuTemp >= 0 ? "    " + Math.round(metrics.cpuTemp) + " °C" : "")
                accent: metrics.cpuPercent >= 90 ? "#f38ba8" : metrics.cpuPercent >= 70 ? "#fab387" : "#cba6f7"
            }

            MetricRow {
                label: "RAM"
                percentage: metrics.ramPercent
                value: metrics.ramPercent >= 0
                    ? metrics.ramUsedGiB.toFixed(1) + " / " + metrics.ramTotalGiB.toFixed(1)
                        + " GiB    " + Math.round(metrics.ramPercent) + " %" : "—"
                accent: metrics.ramPercent >= 90 ? "#f38ba8" : metrics.ramPercent >= 75 ? "#fab387" : "#cba6f7"
            }

            MetricRow {
                visible: metrics.gpuPercent >= 0 || metrics.gpuTemp >= 0
                label: "GPU"
                percentage: metrics.gpuPercent
                value: (metrics.gpuPercent >= 0 ? Math.round(metrics.gpuPercent) + " %" : "")
                    + (metrics.gpuTemp >= 0 ? (metrics.gpuPercent >= 0 ? "    " : "")
                        + Math.round(metrics.gpuTemp) + " °C" : "")
            }

            MetricRow {
                label: "Disque /"
                percentage: metrics.diskPercent
                value: metrics.diskPercent >= 0
                    ? metrics.diskUsedGiB.toFixed(0) + " / " + metrics.diskTotalGiB.toFixed(0)
                        + " GiB    " + Math.round(metrics.diskPercent) + " %" : "—"
            }

            Row {
                width: parent.width
                Text { id: loadLabel; text: "Charge (1/5/15 min)"; color: "#cdd6f4"; font.pixelSize: 12 }
                Item { width: Math.max(0, parent.width - loadValue.width - loadLabel.width); height: 1 }
                Text { id: loadValue; text: metrics.loadAverage || "—"; color: "#bac2de"; font.pixelSize: 12 }
            }
            Row {
                width: parent.width
                Text { id: uptimeLabel; text: "En marche"; color: "#cdd6f4"; font.pixelSize: 12 }
                Item { width: Math.max(0, parent.width - uptimeValue.width - uptimeLabel.width); height: 1 }
                Text { id: uptimeValue; text: metrics.uptimeText || "—"; color: "#bac2de"; font.pixelSize: 12 }
            }
        }
    }
}

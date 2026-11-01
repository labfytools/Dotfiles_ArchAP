import QtQuick
import QtQuick.Controls
import Quickshell
import "../theme"

PopupWindow {
    id: popup
    required property var barWindow
    required property var indicator
    required property var service
    signal dismissed()
    anchor.window: barWindow
    anchor.rect.x: Math.max(12, (barWindow.width - implicitWidth) / 2)
    anchor.rect.y: barWindow.height + 6
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    readonly property real usableWidth: Math.max(0, barWindow.screen.width - 24)
    readonly property real usableHeight: Math.max(0, barWindow.screen.height - barWindow.height - 28)
    implicitWidth: Math.min(1500, usableWidth, Math.max(600, usableWidth * 0.9))
    implicitHeight: Math.min(920, usableHeight, Math.max(440, usableHeight * 0.82))
    visible: false
    grabFocus: true
    color: "transparent"
    onVisibleChanged: { service.processesVisible = visible; if (!visible) dismissed(); }
    Component.onCompleted: Qt.callLater(() => { popup.visible = true; })
    Component.onDestruction: service.processesVisible = false
    Shortcut { sequence: "Escape"; enabled: popup.visible; onActivated: popup.visible = false }

    readonly property bool narrow: width < 850
    readonly property string mono: "JetBrainsMono Nerd Font"
    readonly property var d: service.data || ({})
    readonly property var m: d.memory || ({})
    readonly property var g: d.gpu || ({})
    readonly property var z: d.zram || ({})
    readonly property var psi: d.psi || ({})
    readonly property var t: d.temperatures || ({})
    readonly property var disk: d.disk || ({})
    readonly property var h: service.histories
    property string sortKey: "cpu"
    property int selectedPid: -1
    readonly property var sortedProcesses: {
        const rows = service.processRows.slice();
        if (sortKey === "rss") rows.sort((a,b) => b.rss - a.rss || (b.cpu || 0) - (a.cpu || 0));
        return rows;
    }
    function valid(v) { return v !== null && v !== undefined && isFinite(v); }
    function fmt(v, n) { return valid(v) ? Number(v).toFixed(n === undefined ? 0 : n) : "—"; }
    function gib(v) { return valid(v) ? (v / 1073741824).toFixed(2) + " Gio" : "indisponible"; }
    function rate(v) { return valid(v) ? (v / 1048576).toFixed(2) + " Mio/s" : "indisponible"; }
    function share(a,b) { return valid(a) && valid(b) && b > 0 ? Math.max(0, Math.min(100, 100 * a / b)) : 0; }
    function coreKeys() { return Object.keys(service.usage.threads || {}).sort((a,b) => Number(a.slice(3)) - Number(b.slice(3))); }

    component Section: Rectangle {
        property string heading: ""
        radius: 3; color: Theme.popupBackground; border.width: 1; border.color: Theme.outline
        Text { x: 10; y: 2; text: " " + parent.heading + " "; color: Theme.lavender
            font.family: popup.mono; font.pixelSize: 12; font.bold: true; font.capitalization: Font.AllUppercase
            Rectangle { anchors.fill: parent; anchors.margins: -1; z: -1; color: Theme.popupBackground } }
    }
    component Meter: Item {
        property string label: ""
        property string value: ""
        property real fraction: 0
        property color tint: Theme.lavender
        height: 21
        Text { id: meterLabel; width: 48; text: parent.label; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 11 }
        Rectangle { id: track; x: 49; width: Math.max(0, parent.width - 49 - 175); height: 7; y: 5; radius: 2; color: Theme.buttonBackground
            Rectangle { width: parent.width * Math.max(0, Math.min(100, fraction)) / 100; height: parent.height; radius: 2; color: tint } }
        Text { x: parent.width - 171; width: 171; text: parent.value; color: Theme.foreground
            horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; font.family: popup.mono; font.pixelSize: 11 }
    }
    Rectangle {
        anchors.fill: parent; radius: 4; color: Theme.panelBackground; border.color: Theme.outline
        Text { id: heading; x: 14; y: 8; text: "󰍛  MONITEUR MATÉRIEL"; color: Theme.lavender
            font.family: popup.mono; font.pixelSize: 14; font.bold: true }
        Text { anchors.right: parent.right; anchors.rightMargin: 14; y: 10; text: "10 min  ·  Échap pour fermer";
            color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
        Flickable {
            id: dashboard
            x: 10; y: 34; width: parent.width - 20; height: parent.height - 44
            contentWidth: width; contentHeight: grid.height; clip: true
            boundsBehavior: Flickable.StopAtBounds
            Item {
                id: grid; width: dashboard.width
                readonly property real gap: 8
                readonly property real topHeight: 320
                readonly property real midHeight: popup.narrow ? 400 : 300
                readonly property real bottomHeight: popup.narrow ? 150 : 130
                height: popup.narrow ? topHeight * 2 + midHeight * 2 + bottomHeight * 2 + 5 * gap
                    : Math.max(dashboard.height, topHeight + midHeight + bottomHeight + 2 * gap)
                Section {
                    id: cpuBox; heading: "CPU"; x: 0; y: 0
                    width: popup.narrow ? grid.width : grid.width * 0.55 - grid.gap / 2; height: grid.topHeight
                    Text { x: 12; y: 16; text: popup.fmt(service.usage.cpu, 1) + " %"; color: Theme.lavender
                        font.family: popup.mono; font.pixelSize: 27; font.bold: true; width: 115 }
                    Text { x: 130; y: 23; width: parent.width - 142; elide: Text.ElideRight
                        text: "T " + popup.fmt(popup.t.cpu, 1) + " °C    " +
                            "f " + (popup.d.frequencies && popup.d.frequencies.length ? popup.fmt(popup.d.frequencies[0].currentMHz) : "—") +
                            " MHz    charge " + (popup.d.load ? popup.d.load.join(" / ") : "—")
                        color: Theme.foreground; font.family: popup.mono; font.pixelSize: 11 }
                    Sparkline { x: 12; y: 57; width: parent.width - 24; height: 108
                        points: popup.h.cpu; ceiling: 100; stroke: Theme.lavender; gridVisible: true; fillVisible: true }
                    Text { x: 13; y: 170; text: "CPU LOGIQUES · % PAR CŒUR"; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                    Repeater {
                        model: popup.coreKeys()
                        Item {
                            required property string modelData
                            readonly property int indexNumber: Number(modelData.slice(3))
                            x: 12 + (indexNumber >= 8 ? cpuBox.width / 2 : 0)
                            y: 187 + (indexNumber % 8) * 16
                            width: (cpuBox.width - 50) / 2; height: 14
                            Text { x: 0; text: modelData; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                            Rectangle { x: 43; y: 4; width: Math.max(10, parent.width - 83); height: 5; color: Theme.buttonBackground; radius: 1
                                Rectangle { width: parent.width * popup.share(service.usage.threads[modelData], 100) / 100; height: parent.height; color: Theme.lavender; radius: 1 } }
                            Text { anchors.right: parent.right; width: 36; horizontalAlignment: Text.AlignRight
                                text: popup.fmt(service.usage.threads[modelData]); color: Theme.foreground; font.family: popup.mono; font.pixelSize: 10 }
                        }
                    }
                }
                Section {
                    id: gpuBox; heading: "GPU · AMD RADEON"; y: popup.narrow ? cpuBox.height + grid.gap : 0
                    x: popup.narrow ? 0 : cpuBox.width + grid.gap
                    width: popup.narrow ? grid.width : grid.width - x; height: grid.topHeight
                    Text { x: 12; y: 17; text: popup.fmt(popup.g.activity) + " %"; color: Theme.mauve; font.family: popup.mono; font.pixelSize: 26; font.bold: true }
                    Text { anchors.right: parent.right; anchors.rightMargin: 12; y: 26
                        text: "T " + popup.fmt(popup.t.gpu, 1) + " °C  ·  " + popup.fmt(popup.g.frequencyMHz) + " MHz"
                        color: Theme.foreground; font.family: popup.mono; font.pixelSize: 11 }
                    Sparkline { x: 12; y: 57; width: parent.width - 24; height: Math.max(75, parent.height * 0.51)
                        points: popup.h.gpu; ceiling: 100; stroke: Theme.mauve; gridVisible: true; fillVisible: true }
                    Text { x: 12; y: parent.height - 63; text: "VRAM dédiée"; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                    Text { anchors.right: parent.right; anchors.rightMargin: 12; y: parent.height - 63; text: popup.gib(popup.g.vramUsed) + " / " + popup.gib(popup.g.vramTotal)
                        color: Theme.foreground; font.family: popup.mono; font.pixelSize: 10 }
                    Text { x: 12; y: parent.height - 40; text: "GTT partagée"; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                    Text { anchors.right: parent.right; anchors.rightMargin: 12; y: parent.height - 40; text: popup.gib(popup.g.gttUsed) + " / " + popup.gib(popup.g.gttTotal)
                        color: Theme.foreground; font.family: popup.mono; font.pixelSize: 10 }
                }
                Section {
                    id: memoryBox; heading: "MÉMOIRE · SWAP · ZRAM · PSI"
                    x: 0; y: (popup.narrow ? gpuBox.y + gpuBox.height : cpuBox.height) + grid.gap
                    width: popup.narrow ? grid.width : grid.width * 0.43 - grid.gap / 2; height: grid.midHeight
                    Column {
                        x: 12; y: 20; width: parent.width - 24; spacing: 4
                        Meter { width: parent.width; label: "RAM"; value: popup.gib(popup.m.used) + " / " + popup.gib(popup.m.total); fraction: popup.share(popup.m.used,popup.m.total) }
                        Meter { width: parent.width; label: "SWAP"; value: popup.gib(popup.m.swapUsed) + " / " + popup.gib(popup.m.swapTotal); fraction: popup.share(popup.m.swapUsed,popup.m.swapTotal); tint: Theme.mauve }
                        Meter { width: parent.width; label: "ZRAM"; value: popup.gib(popup.z.logical) + " logique"; fraction: popup.share(popup.z.logical,popup.m.swapTotal); tint: Theme.lavender }
                        Text { text: "Disponible " + popup.gib(popup.m.available) + "   Cache " + popup.gib(popup.m.cache); color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                        Text { text: "zram compressée " + popup.gib(popup.z.compressed) + "   RAM " + popup.gib(popup.z.consumed) + "   ×" + popup.fmt(popup.z.ratio,2)
                            color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                        Rectangle { width: parent.width; height: 1; color: Theme.outline }
                        Text { text: "PSI · TEMPS D'ATTENTE MÉMOIRE"; color: Theme.lavender; font.family: popup.mono; font.pixelSize: 11 }
                        Sparkline { width: parent.width; height: Math.max(48, memoryBox.height - 197); points: popup.h.psi; ceiling: 100; stroke: Theme.mauve; gridVisible: true; fillVisible: true }
                        Text { text: "some  " + (popup.psi.some ? popup.psi.some.map(v => popup.fmt(v,2) + "%").join("   ") : "indisponible"); color: Theme.foreground; font.family: popup.mono; font.pixelSize: 10 }
                        Text { text: "full  " + (popup.psi.full ? popup.psi.full.map(v => popup.fmt(v,2) + "%").join("   ") : "indisponible"); color: Theme.foreground; font.family: popup.mono; font.pixelSize: 10 }
                    }
                }
                Section {
                    id: processBox; heading: "PROCESSUS · CPU % D'UN CŒUR"
                    x: popup.narrow ? 0 : memoryBox.width + grid.gap
                    y: popup.narrow ? memoryBox.y + memoryBox.height + grid.gap : memoryBox.y
                    width: popup.narrow ? grid.width : grid.width - x; height: grid.midHeight
                    Rectangle { x: 8; y: 18; width: parent.width - 16; height: 24; color: Theme.buttonBackground
                        Text { x: 6; width: 65; text: "PID"; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 11 }
                        Text { x: 72; width: parent.width - 240; text: "NOM"; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 11 }
                        Text { x: parent.width - 165; width: 70; text: "CPU %"; color: popup.sortKey === "cpu" ? Theme.lavender : Theme.subtext1; font.family: popup.mono; font.pixelSize: 11
                            MouseArea { anchors.fill: parent; onClicked: popup.sortKey = "cpu" } }
                        Text { x: parent.width - 90; width: 85; text: "RAM"; color: popup.sortKey === "rss" ? Theme.lavender : Theme.subtext1; font.family: popup.mono; font.pixelSize: 11
                            MouseArea { anchors.fill: parent; onClicked: popup.sortKey = "rss" } }
                    }
                    ListView {
                        id: processList; x: 8; y: 44; width: parent.width - 16; height: parent.height - 52; clip: true
                        model: popup.sortedProcesses; keyNavigationWraps: false; focus: true
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: processList.width; height: 21
                            color: popup.selectedPid === modelData.pid ? Theme.buttonPressed : index % 2 ? Theme.popupBackground : "transparent"
                            Text { x: 6; width: 65; text: modelData.pid; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                            Text { x: 72; width: Math.max(40, parent.width - 240); text: modelData.name; elide: Text.ElideRight; color: Theme.foreground; font.family: popup.mono; font.pixelSize: 10 }
                            Text { x: parent.width - 165; width: 70; text: popup.fmt(modelData.cpu,1); horizontalAlignment: Text.AlignRight; color: Theme.lavender; font.family: popup.mono; font.pixelSize: 10 }
                            Text { x: parent.width - 90; width: 85; text: popup.gib(modelData.rss); horizontalAlignment: Text.AlignRight; color: Theme.foreground; font.family: popup.mono; font.pixelSize: 10 }
                            MouseArea { anchors.fill: parent; onClicked: { popup.selectedPid = modelData.pid; processList.currentIndex = index; } }
                        }
                        Keys.onUpPressed: { currentIndex = Math.max(0, currentIndex - 1); popup.selectedPid = currentItem ? currentItem.modelData.pid : -1; }
                        Keys.onDownPressed: { currentIndex = Math.min(count - 1, currentIndex + 1); popup.selectedPid = currentItem ? currentItem.modelData.pid : -1; }
                    }
                    Text { anchors.centerIn: processList; visible: processList.count === 0; text: "Aucun processus disponible"; color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 11 }
                }
                Section {
                    id: diskBox; heading: "STOCKAGE · / · " + (popup.disk.filesystem || "indisponible")
                    x: 0; y: (popup.narrow ? processBox.y + processBox.height : memoryBox.y + memoryBox.height) + grid.gap
                    width: popup.narrow ? grid.width : grid.width * 0.43 - grid.gap / 2; height: grid.bottomHeight
                    Column { x: 12; y: 23; width: parent.width - 24; spacing: 8
                        Meter { width: parent.width; label: "UTIL."; value: popup.gib(popup.disk.used) + " / " + popup.gib(popup.disk.total); fraction: popup.share(popup.disk.used,popup.disk.total) }
                        Text { text: "Espace utilisable : " + popup.gib(popup.disk.available); color: Theme.foreground; font.family: popup.mono; font.pixelSize: 11 }
                        Text { width: parent.width; wrapMode: Text.WordWrap; text: "Occupation logique du système de fichiers ; l'allocation interne Btrfs n'est pas affichée."
                            color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                    }
                }
                Section {
                    id: netBox; heading: "RÉSEAU · " + (popup.d.network ? popup.d.network.interface : "déconnecté")
                    x: popup.narrow ? 0 : diskBox.width + grid.gap
                    y: popup.narrow ? diskBox.y + diskBox.height + grid.gap : diskBox.y
                    width: popup.narrow ? grid.width : grid.width - x; height: grid.bottomHeight
                    Text { x: 12; y: 17; text: "↓ " + popup.rate(service.rates.rx) + "   ↑ " + popup.rate(service.rates.tx);
                        color: Theme.foreground; font.family: popup.mono; font.pixelSize: 11 }
                    Text { anchors.right: parent.right; anchors.rightMargin: 12; y: 17; text: "échelle 0–10 Mio/s";
                        color: Theme.subtext1; font.family: popup.mono; font.pixelSize: 10 }
                    Sparkline { x: 12; y: 38; width: parent.width - 24; height: 43; points: popup.h.rx; ceiling: 10485760; stroke: Theme.lavender; gridVisible: true; fillVisible: true }
                    Sparkline { x: 12; y: 86; width: parent.width - 24; height: 43; points: popup.h.tx; ceiling: 10485760; stroke: Theme.mauve; gridVisible: true; fillVisible: true }
                }
            }
        }
    }
}

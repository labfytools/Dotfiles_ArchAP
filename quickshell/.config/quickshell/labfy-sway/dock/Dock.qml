import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import "../applications"
import "../theme"
import "AutoHide.js" as AutoHide

PanelWindow {
    id: dock
    required property var modelData
    property bool suppressed: false
    screen: modelData
    anchors.bottom: true
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0
    aboveWindows: true
    WlrLayershell.layer: WlrLayer.Top
    // CONTRACT: the dock and its in-surface menus never accept keyboard focus.
    // Layer surfaces are absent from get_tree, hence Session V2 snapshots.
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    WlrLayershell.namespace: "labfy-sway-dock"
    color: "transparent"
    implicitWidth: Math.max(96, Math.min(screen.width - 24, items.width + 28))
    implicitHeight: 360
    property string phase: "hidden"
    readonly property bool revealed: phase === "shown" || phase === "waiting" || phase === "held"
    property bool pressed: false
    property string draggingId: ""
    property var contextEntry: null
    property real contextX: 0
    property real pointerX: -1000
    readonly property bool held: pressed || draggingId !== "" || contextEntry !== null
    readonly property var entries: FavoritesService.dockEntries
    readonly property int pinnedCount: FavoritesService.ids.length
    property alias contentItemRow: items
    property alias surfaceBody: body
    property alias contextCard: context
    property alias edgeArea: sensor
    // INVARIANT: only the bottom activation strip receives input while hidden.
    // Visible input follows the animated body, with a bridge to the edge.
    mask: Region {
        item: sensor
        Region { item: body; intersection: dock.revealed ? Intersection.Combine : Intersection.Subtract }
        Region { item: context; intersection: context.visible ? Intersection.Combine : Intersection.Subtract }
    }
    function reconcile(event) {
        phase = AutoHide.next(phase, event || "input", {
            suppressed: suppressed, held: held,
            body: bodyHover.hovered || contextHover.hovered,
            edge: sensor.containsMouse
        });
    }
    onHeldChanged: reconcile()
    onSuppressedChanged: { contextEntry = null; draggingId = ""; pressed = false; reconcile(); }
    onEntriesChanged: {
        if (contextEntry) {
            contextEntry = entries.find(entry => entry.id === contextEntry.id) || null;
        }
    }
    Timer {
        id: deadline
        interval: dock.phase === "arming" ? 180 : 450
        running: dock.phase === "arming" || dock.phase === "waiting"
        onTriggered: dock.reconcile("deadline")
    }
    function activate(entry) {
        if (entry.windows.length === 1) FavoritesService.focusWindow(entry.windows[0].id);
        else if (entry.windows.length > 1) openContext(entry, width / 2);
        else if (!entry.missing) FavoritesService.launch(entry.id);
    }
    function openContext(entry, x) {
        contextX = x;
        contextEntry = entry;
    }
    function closeContext() { contextEntry = null; }
    MouseArea {
        id: sensor
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        width: dock.revealed ? dock.width : Math.min(360, dock.width)
        height: 4
        hoverEnabled: true
        onEntered: dock.reconcile()
        onExited: dock.reconcile()
        onClicked: dock.closeContext()
    }
    Item {
        id: body
        width: parent.width
        height: 110
        y: dock.revealed ? dock.height - height : dock.height + 4
        Behavior on y { NumberAnimation { duration: 210; easing.type: Easing.OutCubic } }
        HoverHandler {
            id: bodyHover
            onHoveredChanged: { dock.reconcile(); if (!hovered) dock.pointerX = -1000; }
            onPointChanged: dock.pointerX = point.position.x
        }
        Rectangle {
            // Discreet local shadow, no screen capture or blur sampling.
            x: 2; y: 34; width: parent.width - 4; height: 70
            radius: 26; color: Theme.shadow
        }
        Rectangle {
            x: 0; y: 29; width: parent.width; height: 70
            radius: 25
            color: Qt.rgba(Theme.base.r, Theme.base.g, Theme.base.b, Theme.highContrast ? 1 : 0.89)
            border.color: Theme.strongBorder; border.width: 1
        }
        Flickable {
            id: viewport
            x: 12; y: 0; width: parent.width - 24; height: 105
            contentWidth: items.width; contentHeight: height
            clip: true
            interactive: dock.draggingId === ""
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
            Row {
                id: items
                height: viewport.height
                spacing: 3
                move: Transition { NumberAnimation { properties: "x"; duration: 110; easing.type: Easing.OutCubic } }
                Repeater {
                    id: icons
                    model: dock.entries
                    delegate: Item {
                        id: tile
                        required property var modelData
                        required property int index
                        readonly property bool separator: index === dock.pinnedCount && dock.pinnedCount > 0
                        readonly property real center: viewport.x + x + width / 2 - viewport.contentX
                        // WHY: measuring against the animated x/width feeds
                        // scale back into its own binding. Stable resting slots
                        // keep magnification deterministic and free of loops.
                        readonly property real baseCenter: viewport.x + index * 57 + 27
                            + (index >= dock.pinnedCount && dock.pinnedCount > 0 ? 13 : 0) - viewport.contentX
                        readonly property real growth: dock.revealed && bodyHover.hovered
                            ? AutoHide.influence(baseCenter - dock.pointerX) : 0
                        width: 54 + growth * 19 + (separator ? 13 : 0)
                        height: 105
                        Behavior on width { NumberAnimation { duration: 95; easing.type: Easing.OutCubic } }
                        Rectangle {
                            visible: tile.separator
                            x: 2; y: 45; width: 1; height: 32; color: Theme.strongBorder
                        }
                        ApplicationIcon {
                            id: icon
                            width: 46 + tile.growth * 21; height: width
                            x: (parent.width - width + (tile.separator ? 12 : 0)) / 2
                            y: 83 - height
                            iconSource: tile.modelData.iconSource || ""
                            opacity: dock.draggingId === tile.modelData.id ? 0.5 : 1
                            Behavior on width { NumberAnimation { duration: 95; easing.type: Easing.OutCubic } }
                        }
                        Rectangle {
                            anchors.horizontalCenter: icon.horizontalCenter
                            y: 90; width: 4; height: 4; radius: 2
                            color: Theme.lavender; visible: tile.modelData.windows.length > 0
                        }
                        MouseArea {
                            id: pointer
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                            hoverEnabled: true
                            preventStealing: tile.modelData.pinned
                            property real startX: 0
                            property real startY: 0
                            property bool moved: false
                            onPressed: mouse => {
                                dock.pressed = true; startX = mouse.x; startY = mouse.y; moved = false;
                            }
                            onPositionChanged: mouse => {
                                if (pressed && pressedButtons === Qt.LeftButton && tile.modelData.pinned
                                    && Math.hypot(mouse.x - startX, mouse.y - startY) > 8) {
                                    moved = true; dock.draggingId = tile.modelData.id;
                                }
                            }
                            onReleased: mouse => {
                                if (moved) {
                                    const p = mapToItem(items, mouse.x, mouse.y);
                                    let before = "";
                                    for (let i = 0; i < icons.count; ++i) {
                                        const candidate = icons.itemAt(i);
                                        if (candidate.modelData.pinned && candidate.modelData.id !== dock.draggingId
                                            && p.x < candidate.x + candidate.width / 2) {
                                            before = candidate.modelData.id; break;
                                        }
                                    }
                                    FavoritesService.move(dock.draggingId, before);
                                } else if (mouse.button === Qt.RightButton) {
                                    dock.openContext(tile.modelData, tile.center);
                                } else if (mouse.button === Qt.MiddleButton) {
                                    if (!tile.modelData.missing && tile.modelData.newInstance)
                                        FavoritesService.launch(tile.modelData.id);
                                } else {
                                    dock.closeContext(); dock.activate(tile.modelData);
                                }
                                dock.draggingId = ""; dock.pressed = false;
                            }
                            onCanceled: { dock.draggingId = ""; dock.pressed = false; }
                            ToolTip.visible: containsMouse && !dock.held
                            ToolTip.text: tile.modelData.name
                            ToolTip.delay: 600
                        }
                    }
                }
            }
        }
    }
    Rectangle {
        id: context
        visible: dock.contextEntry !== null
        width: Math.min(330, dock.width)
        height: Math.min(230, contextContent.height + 16)
        x: Math.max(0, Math.min(dock.width - width, dock.contextX - width / 2))
        y: dock.height - 116 - height
        radius: 12; color: Theme.popupBackground
        border.color: Theme.strongBorder
        HoverHandler { id: contextHover; onHoveredChanged: dock.reconcile() }
        Flickable {
            anchors.fill: parent; anchors.margins: 8
            contentHeight: contextContent.height; clip: true
            Column {
                id: contextContent
                width: parent.width
                Text {
                    width: parent.width; height: 28
                    text: dock.contextEntry ? dock.contextEntry.name : ""
                    color: Theme.lavender; elide: Text.ElideRight; font.bold: true
                }
                Repeater {
                    model: dock.contextEntry ? dock.contextEntry.windows : []
                    delegate: DockAction {
                        required property var modelData
                        width: contextContent.width
                        text: modelData.title + " · " + modelData.workspace
                        onTriggered: { FavoritesService.focusWindow(modelData.id); dock.closeContext(); }
                    }
                }
                DockAction {
                    width: parent.width
                    visible: !!dock.contextEntry && !dock.contextEntry.missing
                    text: "Ouvrir"
                    onTriggered: { FavoritesService.launch(dock.contextEntry.id); dock.closeContext(); }
                }
                DockAction {
                    width: parent.width
                    visible: !!dock.contextEntry && (dock.contextEntry.pinned || !dock.contextEntry.missing)
                    objectName: "dock-pin-action"
                    text: dock.contextEntry && dock.contextEntry.pinned ? "Désépingler" : "Épingler"
                    onTriggered: { FavoritesService.toggle(dock.contextEntry.id); dock.closeContext(); }
                }
                DockAction { width: parent.width; text: "Fermer le menu"; onTriggered: dock.closeContext() }
            }
        }
    }
    Text {
        visible: dock.revealed && FavoritesService.error !== "" && !context.visible
        anchors.horizontalCenter: parent.horizontalCenter
        y: dock.height - 140
        text: FavoritesService.error; color: Theme.danger; font.pixelSize: 12
    }
}

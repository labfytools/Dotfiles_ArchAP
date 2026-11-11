import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland
import Quickshell.Io
import "../applications"
import "../theme"
import "AutoHide.js" as AutoHide
import "DockModel.js" as DockModel

PanelWindow {
    id: dock
    required property var modelData
    property bool suppressed: false
    screen: modelData
    // The transparent layer spans the output so the bottom edge is reachable
    // at every horizontal position. The visible dock remains centered below.
    anchors.left: true
    anchors.right: true
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
    implicitWidth: screen.width
    implicitHeight: 360
    readonly property real visualWidth: Math.max(96, Math.min(screen.width - 24, items.width + 52))
    property string phase: "hidden"
    readonly property bool revealed: phase === "shown" || phase === "waiting" || phase === "held"
    property bool pressed: false
    property string draggingId: ""
    property var contextEntry: null
    property real contextX: 0
    property real pointerX: -1000
    // The preview is a transient, focusless popup opened only on pointer dwell.
    property string previewId: ""
    property string pendingPreviewId: ""
    property real previewAnchorX: 0
    property var previewImages: ({})
    property int previewGeneration: 0
    property int captureGeneration: -1
    property string captureAppId: ""
    readonly property var previewEntry: entries.find(e => e.id === previewId) || null
    readonly property bool previewVisible: previewId !== "" && previewEntry !== null
        && previewEntry.windows.length > 0 && contextEntry === null
    readonly property string captureScript: decodeURIComponent(
        Qt.resolvedUrl("../bin/dock-thumbnails.py").toString().replace(/^file:\/\//, ""))
    readonly property bool held: pressed || draggingId !== "" || contextEntry !== null || previewVisible
    readonly property var entries: DockModel.entries(FavoritesService.dockEntries, FavoritesService.separators)
    readonly property int pinnedCount: FavoritesService.ids.length
    property alias contentItemRow: items
    property alias surfaceBody: body
    property alias contextCard: context
    property alias contextDismissArea: dismissZone
    property alias edgeArea: sensor
    // INVARIANT: only the four-pixel, full-output bottom strip receives input
    // while hidden. When revealed, the centered visual body also receives input.
    // The edge strip must never acquire holes when the popup is closed.
    // Empty conditional regions, rather than Subtract, avoid carving the
    // (still geometrically present) hidden context/dismiss zone out of it.
    mask: Region {
        item: sensor
        Region {
            id: bodyInputMask
            x: body.x; y: body.y
            width: dock.revealed ? body.width : 0
            height: dock.revealed ? body.height : 0
            intersection: Intersection.Combine
        }
        Region {
            id: dismissInputMask
            x: dismissZone.x; y: dismissZone.y
            width: context.visible ? dismissZone.width : 0
            height: context.visible ? dismissZone.height : 0
            intersection: Intersection.Combine
        }
        Region {
            id: contextInputMask
            x: context.x; y: context.y
            width: context.visible ? context.width : 0
            height: context.visible ? context.height : 0
            intersection: Intersection.Combine
        }
        Region {
            id: previewInputMask
            x: previewPopup.x; y: previewPopup.y
            width: dock.previewVisible ? previewPopup.width : 0
            height: dock.previewVisible ? previewPopup.height : 0
            intersection: Intersection.Combine
        }
    }
    // Exposed for the private compositor's input-mask regression assertions.
    property alias bodyMaskRegion: bodyInputMask
    property alias dismissMaskRegion: dismissInputMask
    property alias contextMaskRegion: contextInputMask
    property alias previewPopupItem: previewPopup
    property alias previewCardsRow: cardRow
    property alias previewMaskRegion: previewInputMask
    property alias previewArmRunning: previewArm.running
    function reconcile(event) {
        phase = AutoHide.next(phase, event || "input", {
            suppressed: suppressed, held: held,
            body: bodyHover.hovered || contextHover.hovered,
            edge: sensor.containsMouse
        });
    }
    onHeldChanged: reconcile()
    onSuppressedChanged: {
        contextEntry = null; draggingId = ""; pressed = false;
        closePreview(); reconcile();
    }
    onEntriesChanged: {
        if (contextEntry) {
            contextEntry = entries.find(entry => entry.id === contextEntry.id) || null;
        }
        if (previewId && (!previewEntry || previewEntry.windows.length === 0))
            closePreview();
    }
    Timer {
        id: deadline
        interval: dock.phase === "arming" ? 180 : 450
        running: dock.phase === "arming" || dock.phase === "waiting"
        onTriggered: dock.reconcile("deadline")
    }
    function activate(entry) {
        if (entry.windows.length === 1) FavoritesService.focusWindow(entry.windows[0].id);
        else if (entry.windows.length > 1) openContext(entry, body.width / 2);
        else if (!entry.missing) FavoritesService.launch(entry.id);
    }
    function openContext(entry, x) {
        closePreview();
        contextX = x;
        contextEntry = entry;
        contextDismiss.restart();
    }
    function closeContext() {
        contextDismiss.stop();
        contextEntry = null;
    }
    // Hover state and the same 4px trigger keep the dock alive; the menu
    // owns only a small temporary outside-click region, not the whole screen.
    Timer {
        id: contextDismiss
        interval: 480
        onTriggered: {
            if (dock.contextEntry && !contextHover.hovered && !dismissZone.containsMouse)
                dock.closeContext();
        }
    }
    // Capture is one-shot on hover, never continuous and never on a timer
    // while idle. A stale response cannot replace a newer hover selection.
    function queuePreview(entry, x) {
        if (suppressed || contextEntry || !entry || !entry.windows
                || entry.windows.length === 0 || entry.kind || pressed) return;
        if (previewId === entry.id || pendingPreviewId === entry.id) {
            previewClose.stop();
            return;
        }
        previewAnchorX = x;
        pendingPreviewId = entry.id;
        previewClose.stop();
        previewArm.restart();
    }
    function leavePreviewTile(id) {
        // Child MouseAreas can briefly lose hover without leaving the
        // dock surface (scaled icon and tooltip). The body owns the stable
        // pointer position, and changes between adjacent icons are tracked
        // there instead of closing the popup spuriously.
        if (!bodyHover.hovered && pendingPreviewId === id) previewArm.stop();
        if (!bodyHover.hovered && !previewHover.hovered) previewClose.restart();
    }
    function trackPreview(x, y) {
        if (y < 32 || y > 100 || !revealed || contextEntry || pressed
                || draggingId !== "" || suppressed) return;
        const rowX = x - viewport.x - items.x + viewport.contentX;
        for (let i = 0; i < icons.count; ++i) {
            const tile = icons.itemAt(i);
            if (!tile || tile.divider || tile.modelData.windows.length === 0) continue;
            if (rowX >= tile.x && rowX <= tile.x + tile.width) {
                queuePreview(tile.modelData, tile.center);
                return;
            }
        }
        previewArm.stop();
        if (previewVisible && !previewHover.hovered) previewClose.restart();
    }
    function closePreview() {
        previewArm.stop();
        previewClose.stop();
        pendingPreviewId = "";
        previewId = "";
        previewImages = ({});
        ++previewGeneration;
        thumbsCleanup.restart();
    }
    function showPreview() {
        if (!pendingPreviewId || suppressed || contextEntry || pressed) return;
        const next = entries.find(e => e.id === pendingPreviewId);
        if (!next || next.windows.length === 0) return;
        previewId = next.id;
        previewImages = ({});
        ++previewGeneration;
        requestThumbnails();
    }
    function requestThumbnails() {
        if (!previewVisible || thumbnailJob.running) return;
        const candidates = previewEntry.windows.filter(w => w.foreignId)
            .slice(0, 8).map(w => ({id: String(w.id), foreignId: w.foreignId}));
        if (!candidates.length) return;
        captureAppId = previewId;
        captureGeneration = previewGeneration;
        thumbnailJob.command = ["python3", "-B", captureScript,
                                "capture", JSON.stringify(candidates)];
        thumbnailJob.running = true;
    }
    Timer {
        id: previewArm
        interval: 330
        onTriggered: dock.showPreview()
    }
    Timer {
        id: previewClose
        interval: 620
        onTriggered: { if (!previewHover.hovered) dock.closePreview(); }
    }
    Timer {
        id: thumbsCleanup
        interval: 1250
        onTriggered: {
            if (!dock.previewVisible && !thumbnailJob.running && !cleanupJob.running)
                cleanupJob.running = true;
            else if (!dock.previewVisible) restart();
        }
    }
    Process {
        id: thumbnailJob
        stdout: StdioCollector { id: thumbnailReply; waitForEnd: true }
        onExited: {
            if (captureGeneration === dock.previewGeneration
                    && captureAppId === dock.previewId && dock.previewVisible) {
                try {
                    const result = JSON.parse(thumbnailReply.text);
                    dock.previewImages = result.images || ({});
                } catch (_) {
                    dock.previewImages = ({});
                }
            } else if (dock.previewVisible) {
                Qt.callLater(dock.requestThumbnails);
            } else {
                thumbsCleanup.restart();
            }
        }
    }
    Process {
        id: cleanupJob
        command: ["python3", "-B", dock.captureScript, "clear"]
        running: false
    }
    function movePinned(id, direction) {
        const target = DockModel.moveTarget(FavoritesService.ids, id, direction);
        if (target) FavoritesService.move(target.id, target.before);
    }
    function separatorPositionAt(localX) {
        let position = 0;
        for (let i = 0; i < icons.count; ++i) {
            const candidate = icons.itemAt(i);
            if (candidate && candidate.modelData.pinned
                    && localX > candidate.x + candidate.width / 2)
                ++position;
        }
        return position;
    }
    MouseArea {
        id: sensor
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 4
        hoverEnabled: true
        onEntered: dock.reconcile()
        onExited: dock.reconcile()
        onClicked: dock.closeContext()
    }
    Item {
        id: body
        width: dock.visualWidth
        x: (dock.width - width) / 2
        height: 110
        y: dock.revealed ? dock.height - height : dock.height + 4
        Behavior on y { NumberAnimation { duration: 210; easing.type: Easing.OutCubic } }
        HoverHandler {
            id: bodyHover
            onHoveredChanged: {
                dock.reconcile();
                if (!hovered) {
                    dock.pointerX = -1000;
                    previewArm.stop();
                    if (dock.previewVisible && !previewHover.hovered)
                        previewClose.restart();
                }
            }
            onPointChanged: {
                dock.pointerX = point.position.x;
                dock.trackPreview(point.position.x, point.position.y);
            }
        }
        // WHY: an analytic shadow needs neither a captured backdrop nor a
        // moving blur source. Its geometry stays fixed throughout hover.
        RectangularShadow {
            x: 16; y: 43; width: parent.width - 32; height: 48
            radius: 20; blur: 24; spread: 2
            color: Qt.rgba(0, 0, 0, 0.32)
        }
        Rectangle {
            x: 14; y: 36; width: parent.width - 28; height: 58
            radius: 20
            color: Qt.rgba(Theme.base.r, Theme.base.g, Theme.base.b, Theme.highContrast ? 0.94 : 0.16)
            border.color: Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, Theme.highContrast ? 0.5 : 0.09)
            border.width: 1
        }
        Flickable {
            id: viewport
            x: 12; y: 0; width: parent.width - 24; height: 105
            // CONTRACT: reserve visual overflow inside the clipped viewport,
            // including at both scroll limits, for the 1.39x end icons.
            contentWidth: items.width + 24; contentHeight: height
            clip: true
            interactive: dock.draggingId === ""
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
            Row {
                id: items
                x: 12
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
                        readonly property bool customDivider: modelData.kind === "separator"
                        readonly property bool automaticDivider: modelData.kind === "automatic-separator"
                        readonly property bool divider: customDivider || automaticDivider
                        readonly property real center: viewport.x + items.x + x + width / 2 - viewport.contentX
                        // Slots stay fixed while icon scale changes; separators
                        // have no zoom and cannot launch an application.
                        readonly property real baseCenter: center
                        readonly property real growth: !divider && dock.revealed && bodyHover.hovered
                            ? AutoHide.influence(baseCenter - dock.pointerX) : 0
                        width: customDivider ? 20 : automaticDivider ? 13 : 54
                        height: 105
                        Rectangle {
                            visible: tile.divider
                            x: (parent.width - width) / 2; y: 45; width: 1; height: 32
                            color: tile.customDivider ? Theme.lavender : Theme.strongBorder
                        }
                        ApplicationIcon {
                            id: icon
                            // WHY: ApplicationIcon derives sourceSize from width.
                            // Fixed dimensions avoid async SVG reload/fallback flashes.
                            visible: !tile.divider
                            width: 46; height: 46
                            x: (parent.width - width) / 2
                            y: 37
                            transformOrigin: Item.Bottom
                            scale: 1 + tile.growth * 0.39
                            Behavior on scale { NumberAnimation { duration: 80; easing.type: Easing.OutCubic } }
                            iconSource: tile.modelData.iconSource || ""
                            opacity: dock.draggingId === tile.modelData.id ? 0.5 : 1
                        }
                        // One lavender dot per real Sway toplevel. Compress
                        // spacing instead of turning multiple windows into one.
                        Row {
                            id: windowDots
                            property int count: tile.divider ? 0 : tile.modelData.windows.length
                            spacing: count <= 8 ? 2 : 0.5
                            anchors.horizontalCenter: icon.horizontalCenter
                            y: 91
                            Repeater {
                                model: windowDots.count
                                delegate: Rectangle {
                                    width: Math.max(1, Math.min(4,
                                        (46 - windowDots.spacing * (windowDots.count - 1))
                                        / windowDots.count))
                                    height: width
                                    radius: width / 2
                                    color: Theme.lavender
                                }
                            }
                        }
                        readonly property int dotCount: windowDots.count
                        MouseArea {
                            id: pointer
                            anchors.fill: parent
                            visible: !tile.automaticDivider
                            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                            hoverEnabled: true
                            preventStealing: tile.modelData.pinned || tile.customDivider
                            property real startX: 0
                            property real startY: 0
                            property bool moved: false
                            onEntered: {
                                if (!tile.divider) dock.queuePreview(tile.modelData, tile.center);
                            }
                            onExited: dock.leavePreviewTile(tile.modelData.id)
                            onPressed: mouse => {
                                dock.closePreview();
                                dock.pressed = true; startX = mouse.x; startY = mouse.y; moved = false;
                            }
                            onPositionChanged: mouse => {
                                if (pressed && pressedButtons === Qt.LeftButton
                                        && (tile.modelData.pinned || tile.customDivider)
                                    && Math.hypot(mouse.x - startX, mouse.y - startY) > 8) {
                                    moved = true; dock.draggingId = tile.modelData.id;
                                }
                            }
                            onReleased: mouse => {
                                if (moved) {
                                    const p = mapToItem(items, mouse.x, mouse.y);
                                    if (tile.customDivider) {
                                        FavoritesService.moveSeparator(dock.draggingId, dock.separatorPositionAt(p.x));
                                    } else {
                                        let before = "";
                                        for (let i = 0; i < icons.count; ++i) {
                                            const candidate = icons.itemAt(i);
                                            if (candidate.modelData.pinned && candidate.modelData.id !== dock.draggingId
                                                    && p.x < candidate.x + candidate.width / 2) {
                                                before = candidate.modelData.id; break;
                                            }
                                        }
                                        FavoritesService.move(dock.draggingId, before);
                                    }
                                } else if (mouse.button === Qt.RightButton) {
                                    dock.openContext(tile.modelData, tile.center);
                                } else if (tile.customDivider) {
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
                            ToolTip.visible: containsMouse && !dock.held && !dock.previewVisible
                            ToolTip.text: tile.customDivider ? "Séparateur — clic pour gérer" : tile.modelData.name
                            ToolTip.delay: 600
                        }
                    }
                }
            }
        }
    }
    // On-demand window chooser above the existing dock. The main panel stays
    // input-transparent outside the chooser, body and full-width bottom sensor.
    Rectangle {
        id: previewPopup
        objectName: "dock-window-preview"
        visible: dock.previewVisible
        width: Math.min(dock.width - 24,
            Math.min(4, dock.previewEntry ? dock.previewEntry.windows.length : 0) * 198 + 20)
        height: 170
        x: Math.max(8, Math.min(dock.width - width - 8,
            body.x + dock.previewAnchorX - width / 2))
        y: body.y - height + 18
        radius: 12
        color: Qt.rgba(Theme.popupBackground.r, Theme.popupBackground.g,
                       Theme.popupBackground.b, Theme.highContrast ? 0.94 : 0.85)
        border.color: Theme.strongBorder
        z: 5
        HoverHandler {
            id: previewHover
            onHoveredChanged: {
                if (hovered) previewClose.stop();
                else if (dock.previewVisible) previewClose.restart();
                dock.reconcile();
            }
        }
        Flickable {
            id: previewScroll
            anchors.fill: parent
            anchors.margins: 10
            contentWidth: cardRow.width
            contentHeight: height
            clip: true
            interactive: contentWidth > width
            boundsBehavior: Flickable.StopAtBounds
            Row {
                id: cardRow
                height: previewScroll.height
                spacing: 8
                Repeater {
                    model: dock.previewEntry ? dock.previewEntry.windows : []
                    delegate: DockPreviewCard {
                        required property var modelData
                        windowData: modelData
                        iconSource: dock.previewEntry ? dock.previewEntry.iconSource || "" : ""
                        imageSource: dock.previewImages[String(modelData.id)] || ""
                        onActivated: {
                            FavoritesService.focusWindow(modelData.id);
                            dock.closePreview();
                        }
                    }
                }
            }
        }
    }
    // An outside click near the menu dismisses it without launching another
    // app. Moving beyond this margin starts a short close grace instead.
    MouseArea {
        id: dismissZone
        objectName: "dock-context-dismiss-zone"
        visible: context.visible
        x: Math.max(0, context.x - 68)
        y: Math.max(0, context.y - 52)
        width: Math.min(dock.width - x, context.width + 136)
        height: dock.height - y
        hoverEnabled: true
        onEntered: contextDismiss.stop()
        onExited: contextDismiss.restart()
        onClicked: dock.closeContext()
    }
    Rectangle {
        id: context
        visible: dock.contextEntry !== null
        width: Math.min(330, body.width)
        height: Math.min(230, contextContent.height + 16)
        // contextX is local to the centered visual dock, not to the
        // full-width input surface.
        x: Math.max(0, Math.min(dock.width - width, body.x + dock.contextX - width / 2))
        y: dock.height - 116 - height
        radius: 12
        // 15% transparent (85% opaque), except accessibility mode.
        // Keep menu text fully opaque for readability.
        color: Qt.rgba(Theme.popupBackground.r, Theme.popupBackground.g,
                       Theme.popupBackground.b, Theme.highContrast ? 0.94 : 0.85)
        border.color: Theme.strongBorder
        HoverHandler {
            id: contextHover
            onHoveredChanged: {
                if (hovered) contextDismiss.stop();
                else if (!dismissZone.containsMouse) contextDismiss.restart();
                dock.reconcile();
            }
        }
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
                    visible: !!dock.contextEntry && !dock.contextEntry.kind
                            && !dock.contextEntry.missing
                    text: "Ouvrir"
                    onTriggered: { FavoritesService.launch(dock.contextEntry.id); dock.closeContext(); }
                }
                DockAction {
                    width: parent.width
                    visible: !!dock.contextEntry && !dock.contextEntry.kind
                            && (dock.contextEntry.pinned || !dock.contextEntry.missing)
                    objectName: "dock-pin-action"
                    text: dock.contextEntry && dock.contextEntry.pinned ? "Désépingler" : "Épingler"
                    onTriggered: { FavoritesService.toggle(dock.contextEntry.id); dock.closeContext(); }
                }
                DockAction {
                    width: parent.width
                    visible: !!dock.contextEntry && !!dock.contextEntry.pinned
                            && DockModel.moveTarget(FavoritesService.ids, dock.contextEntry.id, -1) !== null
                    text: "Déplacer à gauche"
                    onTriggered: { dock.movePinned(dock.contextEntry.id, -1); dock.closeContext(); }
                }
                DockAction {
                    width: parent.width
                    visible: !!dock.contextEntry && !!dock.contextEntry.pinned
                            && DockModel.moveTarget(FavoritesService.ids, dock.contextEntry.id, 1) !== null
                    text: "Déplacer à droite"
                    onTriggered: { dock.movePinned(dock.contextEntry.id, 1); dock.closeContext(); }
                }
                DockAction {
                    width: parent.width
                    readonly property int position: dock.contextEntry
                        ? FavoritesService.ids.indexOf(dock.contextEntry.id) : -1
                    visible: position >= 0 && !DockModel.hasSeparator(FavoritesService.separators, position)
                    text: "Ajouter séparateur avant"
                    onTriggered: { FavoritesService.addSeparator(position); dock.closeContext(); }
                }
                DockAction {
                    width: parent.width
                    readonly property int position: dock.contextEntry
                        ? FavoritesService.ids.indexOf(dock.contextEntry.id) + 1 : -1
                    visible: !!dock.contextEntry && !!dock.contextEntry.pinned
                        && !DockModel.hasSeparator(FavoritesService.separators, position)
                    text: "Ajouter séparateur après"
                    onTriggered: { FavoritesService.addSeparator(position); dock.closeContext(); }
                }
                DockAction {
                    width: parent.width
                    visible: !!dock.contextEntry && dock.contextEntry.kind === "separator"
                        && dock.contextEntry.position > 0
                        && !DockModel.hasSeparator(FavoritesService.separators, dock.contextEntry.position - 1)
                    text: "Déplacer séparateur à gauche"
                    onTriggered: {
                        FavoritesService.moveSeparator(dock.contextEntry.id, dock.contextEntry.position - 1);
                        dock.closeContext();
                    }
                }
                DockAction {
                    width: parent.width
                    visible: !!dock.contextEntry && dock.contextEntry.kind === "separator"
                        && dock.contextEntry.position < FavoritesService.ids.length
                        && !DockModel.hasSeparator(FavoritesService.separators, dock.contextEntry.position + 1)
                    text: "Déplacer séparateur à droite"
                    onTriggered: {
                        FavoritesService.moveSeparator(dock.contextEntry.id, dock.contextEntry.position + 1);
                        dock.closeContext();
                    }
                }
                DockAction {
                    width: parent.width
                    objectName: "dock-remove-separator"
                    visible: !!dock.contextEntry && dock.contextEntry.kind === "separator"
                    text: "Supprimer le séparateur"
                    onTriggered: { FavoritesService.removeSeparator(dock.contextEntry.id); dock.closeContext(); }
                }

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

import QtQuick
import Quickshell
import Quickshell.I3
import Quickshell.I3._Ipc
import Quickshell.Io
import Quickshell.Wayland
import "../theme"

PanelWindow {
    id: overview
    required property var barWindow
    signal overviewDismissed()
    property var cards: []
    property int selectedWorkspace: 1
    property bool initialSelectionSet: false
    property int selectedWindow: 0
    property int moveTarget: 0
    property int dropTarget: 0
    property string message: ""
    property bool refreshPending: false
    property string actionName: ""
    property var dirtyCaptures: []
    property var pendingWindowNumbers: []
    property var activeWindowNumbers: []
    property int windowCaptureCursor: 0
    readonly property string backend: (Quickshell.env("XDG_CONFIG_HOME") ||
        (Quickshell.env("HOME") + "/.config")) + "/quickshell/labfy-sway/overview/backend.py"
    readonly property real cardX: card.x
    readonly property real cardY: card.y
    readonly property real cardWidth: card.width
    readonly property real cardHeight: card.height
    readonly property Item interactionRoot: keyboardRoot
    readonly property real gridContentHeight: grid.height
    readonly property real gridViewportHeight: scroll.height

    // WHY: la surface layer-shell prend le clavier, comme ClipboardPanel.
    // INVARIANT: sa disparition rend le focus au client Sway précédent sans touche injectée.
    screen: barWindow.screen
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0
    aboveWindows: true
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    WlrLayershell.namespace: "labfy-workspace-overview"
    color: "transparent"

    function dismiss() {
        visible = false;
        // WHY: grim inclurait cette surface overlay. Après sa disparition,
        // seules les sorties visibles dont l'arbre a changé sont recapturées.
        for (const card of dirtyCaptures) {
            Quickshell.execDetached(["python3", "-B", backend, "capture", "--output", card.output,
                "--number", String(card.number), "--workspace-id", String(card.workspaceId),
                "--revision", card.revision,
                "--settle-ms", "300"]);
        }
        overviewDismissed();
    }
    function applyState(data) {
        const next = data.cards || [];
        const changedWindows = [];
        if (!cards.length) {
            for (const current of next)
                if (current.windows.length && (current.visible
                        || current.windows.some(window => !window.preview)))
                    changedWindows.push(current.number);
        }
        if (cards.length) {
            for (const current of next) {
                const old = cards.find(value => value.number === current.number);
                if (old && current.windows.length && (old.revision !== current.revision
                        || (!old.visible && current.visible))) changedWindows.push(current.number);
                if (!old || old.revision === current.revision || !current.visible
                        || !current.output) continue;
                if (current.windows.length === 0) {
                    dirtyCaptures = dirtyCaptures.filter(value => value.output !== current.output);
                    continue;
                }
                // CONTRACT: comparer les arbres avant/après repère aussi bien
                // la source que la destination d'un déplacement confirmé IPC.
                dirtyCaptures = dirtyCaptures.filter(value => value.output !== current.output)
                    .concat([{ output: current.output, number: current.number,
                        workspaceId: current.workspaceId, revision: current.revision }]);
                if (current.output !== screen.name && !captureDebounce.running)
                    captureDebounce.start();
            }
        }
        if (changedWindows.length) queueWindowCaptures(changedWindows);
        if (JSON.stringify(cards) !== JSON.stringify(next)) cards = next;
        if (!initialSelectionSet || !cards.some(value => value.number === selectedWorkspace && value.exists)) {
            const focused = cards.find(value => value.focused);
            if (focused) selectedWorkspace = focused.number;
            initialSelectionSet = true;
        }
        selectedWindow = Math.min(selectedWindow, currentWindows().length);
        if (selectedWindow === 0) moveTarget = 0;
    }
    function queueWindowCaptures(numbers) {
        for (const number of numbers)
            if (!pendingWindowNumbers.includes(number)) pendingWindowNumbers.push(number);
        if (!windowCapture.running && !windowCaptureDebounce.running) windowCaptureDebounce.start();
    }
    function startWindowCapture() {
        if (windowCapture.running) return;
        if (windowCaptureCursor === 0) {
            if (!pendingWindowNumbers.length) return;
            activeWindowNumbers = pendingWindowNumbers;
            pendingWindowNumbers = [];
        }
        windowCapture.command = ["python3", "-B", backend, "capture-windows", "--numbers",
            activeWindowNumbers.join(","), "--cursor", String(windowCaptureCursor)];
        windowCapture.running = true;
    }
    function refresh() {
        if (reader.running) { refreshPending = true; return; }
        reader.running = true;
    }
    function scheduleRefresh() {
        // INVARIANT: un flux de titres animés ne repousse jamais indéfiniment
        // la lecture d'une fermeture ou d'un déplacement de fenêtre.
        if (!debounce.running) debounce.start();
    }
    function applyTitleEvent(event) {
        let data;
        try { data = JSON.parse(event.data); } catch (_) { return false; }
        if (data.change !== "title" || !data.container) return false;
        let found = false;
        const updated = cards.map(card => Object.assign({}, card, { windows: card.windows.map(window => {
            if (window.id !== data.container.id) return window;
            found = true;
            return Object.assign({}, window, { title: data.container.name || window.app });
        }) }));
        if (found) cards = updated;
        return found;
    }
    function execute(action, number, ident) {
        if (actor.running || number < 1 || number > 10) return;
        actionName = action;
        const args = ["python3", "-B", backend, action, "--number", String(number)];
        if (ident > 0) args.push("--con-id", String(ident));
        actor.command = args;
        actor.running = true;
    }
    function activateWorkspace(number) { execute("workspace", number, 0); }
    function focusWindow(number, ident) { execute("focus", number, ident); }
    function moveWindow(ident, number) {
        if (!ident || number < 1 || number > 10) return;
        execute("move", number, ident);
    }
    function currentWindows() {
        const item = cards.find(value => value.number === selectedWorkspace);
        return item ? item.windows : [];
    }
    function navigate(delta) {
        selectedWorkspace = Math.max(1, Math.min(10, selectedWorkspace + delta));
        selectedWindow = 0;
    }
    function workspaceAt(x, y) {
        // CONTRACT: le dépôt exige un point dans une carte réelle, même si
        // Qt rogne l'item glissé à la limite de sa miniature.
        for (let index = 0; index < workspaceRepeater.count; index++) {
            const item = workspaceRepeater.itemAt(index);
            if (!item) continue;
            const point = item.mapFromItem(keyboardRoot, x, y);
            if (point.x >= 0 && point.y >= 0 && point.x < item.width && point.y < item.height)
                return item.number;
        }
        return 0;
    }

    Component.onCompleted: refresh()
    Timer { id: debounce; interval: 220; repeat: false; onTriggered: overview.refresh() }
    Timer {
        id: captureDebounce
        interval: 350; repeat: false
        onTriggered: overview.captureNextOtherOutput()
    }
    Timer {
        id: windowCaptureDebounce
        interval: 250; repeat: false
        onTriggered: overview.startWindowCapture()
    }
    function captureNextOtherOutput() {
        if (otherCapture.running) return;
        const card = dirtyCaptures.find(value => value.output !== screen.name);
        if (!card) return;
        otherCapture.command = ["python3", "-B", backend, "capture", "--output", card.output,
            "--number", String(card.number), "--workspace-id", String(card.workspaceId),
            "--revision", card.revision];
        otherCapture.running = true;
    }
    Timer { interval: 120; running: true; onTriggered: keyboardRoot.forceActiveFocus() }
    I3IpcListener {
        subscriptions: ["window"]
        onIpcEvent: event => {
            if (event.type === "subscribe") {
                overview.scheduleRefresh();
            } else if (!overview.applyTitleEvent(event)) overview.scheduleRefresh();
        }
    }
    Connections {
        target: I3
        function onRawEvent(event) {
            if (event.type === "workspace" || event.type === "output") overview.scheduleRefresh();
        }
        function onConnected() { overview.scheduleRefresh(); }
    }
    Process {
        id: reader
        command: ["python3", "-B", overview.backend, "state"]
        stdout: StdioCollector { id: readerOutput; waitForEnd: true }
        onExited: (code, status) => {
            if (code === 0) {
                try {
                    const data = JSON.parse(readerOutput.text);
                    overview.applyState(data);
                } catch (error) { overview.message = "Lecture des workspaces impossible."; }
            } else overview.message = "Lecture des workspaces impossible.";
            if (overview.refreshPending) {
                overview.refreshPending = false;
                Qt.callLater(overview.refresh);
            }
        }
    }
    Process {
        id: otherCapture
        stdout: StdioCollector { id: otherCaptureOutput; waitForEnd: true }
        onExited: (code, status) => {
            let result = {};
            try { result = JSON.parse(otherCaptureOutput.text); } catch (_) {}
            const args = otherCapture.command;
            const output = args[args.indexOf("--output") + 1];
            if (code === 0 && result.captured)
                overview.dirtyCaptures = overview.dirtyCaptures.filter(value =>
                    value.output !== output || value.revision !== result.revision);
            overview.refresh();
            if (result.captured && overview.dirtyCaptures.some(value => value.output !== overview.screen.name))
                captureDebounce.restart();
        }
    }
    Process {
        id: windowCapture
        stdout: StdioCollector { id: windowCaptureOutput; waitForEnd: true }
        onExited: (code, status) => {
            let result = {};
            try { result = JSON.parse(windowCaptureOutput.text); } catch (_) {}
            overview.refresh();
            if (code === 0 && result.nextCursor > 0) {
                overview.windowCaptureCursor = result.nextCursor;
            } else {
                overview.windowCaptureCursor = 0;
                overview.activeWindowNumbers = [];
            }
            if (overview.windowCaptureCursor > 0 || overview.pendingWindowNumbers.length)
                windowCaptureDebounce.start();
        }
    }
    Process {
        id: actor
        stdout: StdioCollector { id: actorOutput; waitForEnd: true }
        onExited: (code, status) => {
            let result = {};
            try { result = JSON.parse(actorOutput.text); } catch (_) {}
            if (code !== 0 || !result.ok) {
                overview.message = "Action Sway impossible ; la vue a été actualisée.";
                overview.refresh();
                return;
            }
            overview.applyState(result.state);
            overview.message = "";
            if (overview.actionName === "move") {
                overview.selectedWindow = 0;
                overview.moveTarget = 0;
                overview.refresh();
            } else overview.dismiss();
        }
    }

    Item {
        id: keyboardRoot
        anchors.fill: parent
        focus: true
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape) { overview.dismiss(); event.accepted = true; }
            else if (event.key === Qt.Key_Left) { overview.navigate(-1); event.accepted = true; }
            else if (event.key === Qt.Key_Right) { overview.navigate(1); event.accepted = true; }
            else if (event.key === Qt.Key_Up) { overview.navigate(-columns); event.accepted = true; }
            else if (event.key === Qt.Key_Down) { overview.navigate(columns); event.accepted = true; }
            else if (event.key === Qt.Key_Tab) {
                const windows = overview.currentWindows();
                if (windows.length) overview.selectedWindow = (overview.selectedWindow + 1) % (windows.length + 1);
                event.accepted = true;
            } else if (event.key === Qt.Key_M && overview.selectedWindow > 0) {
                overview.moveTarget = overview.selectedWorkspace === 10 ? 1 : overview.selectedWorkspace + 1;
                event.accepted = true;
            } else if (event.key >= Qt.Key_0 && event.key <= Qt.Key_9 && overview.moveTarget) {
                overview.moveTarget = event.key === Qt.Key_0 ? 10 : event.key - Qt.Key_0;
                event.accepted = true;
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                const windows = overview.currentWindows();
                if (overview.moveTarget && overview.selectedWindow > 0)
                    overview.moveWindow(windows[overview.selectedWindow - 1].id, overview.moveTarget);
                else if (overview.selectedWindow > 0)
                    overview.focusWindow(overview.selectedWorkspace, windows[overview.selectedWindow - 1].id);
                else overview.activateWorkspace(overview.selectedWorkspace);
                event.accepted = true;
            }
        }
        MouseArea { anchors.fill: parent; onClicked: overview.dismiss() }

        readonly property int columns: card.width >= 1030 ? 5 : card.width >= 750 ? 4 : card.width >= 560 ? 3 : 2
        Rectangle {
            id: card
            anchors.centerIn: parent
            width: Math.max(0, Math.min(1140, parent.width - 32))
            // WHY: deux rangées de cinq cartes tenaient à 30 px près ; ce
            // profil garde 16 px de marge d'écran et supprime le scroll normal.
            height: Math.max(0, Math.min(keyboardRoot.columns === 5 ? 566 : 730, parent.height - 32))
            radius: 4
            color: Theme.popupBackground
            border.color: Theme.outline
            border.width: 1
            MouseArea { anchors.fill: parent; onClicked: {} }

            Column {
                id: content
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                Item {
                    id: header
                    width: parent.width; height: 44
                    Rectangle {
                        id: headerAccent
                        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                        width: 3; height: 32; radius: 1
                        color: Theme.lavender
                    }
                    Column {
                        anchors.left: headerAccent.right; anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text { text: "Vue d’ensemble"; color: Theme.foreground; font.pixelSize: 20; font.bold: true }
                        Text { text: "Espaces de travail · captures et disposition actuelle";
                            color: Theme.secondaryForeground; font.pixelSize: 11 }
                    }
                    Rectangle {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        width: 94; height: 24; radius: 3
                        color: Theme.surface0; border.color: Theme.separator
                        visible: header.width > 520
                        Text { anchors.centerIn: parent; text: "10 ESPACES";
                            color: Theme.accentForeground; font.pixelSize: 10; font.bold: true }
                    }
                }
                Text {
                    id: messageLabel
                    visible: overview.message !== ""; height: visible ? 18 : 0
                    text: overview.message; color: Theme.warningForeground; font.pixelSize: 12
                }
                Flickable {
                    id: scroll
                    width: parent.width
                    // CONTRACT: la grille utilise toute la hauteur réellement
                    // restante ; le footer et l'espacement ne sont comptés qu'une fois.
                    height: Math.max(0, parent.height - y - footer.height - content.spacing)
                    contentWidth: width
                    contentHeight: grid.height
                    clip: true
                    interactive: contentHeight > height + 1
                    boundsBehavior: Flickable.StopAtBounds
                    Grid {
                        id: grid
                        width: scroll.width
                        columns: keyboardRoot.columns
                        spacing: 10
                        Repeater {
                            id: workspaceRepeater
                            model: overview.cards
                            delegate: Rectangle {
                                id: workspaceCard
                                required property var modelData
                                readonly property int number: modelData.number
                                readonly property bool active: modelData.focused
                                readonly property bool occupied: modelData.windows.length > 0
                                readonly property bool hovered: cardHover.hovered || cardPointer.containsMouse
                                readonly property bool dropHighlighted: overview.dropTarget === number || dropArea.containsDrag
                                width: (grid.width - (grid.columns - 1) * grid.spacing) / grid.columns
                                height: grid.columns === 5 ? 210 : grid.columns === 4 ? 190
                                    : grid.columns === 3 ? 140 : 175
                                radius: 4
                                color: dropHighlighted ? Theme.surface2
                                    : active ? Theme.surface1
                                    : hovered ? Theme.buttonHover
                                    : occupied ? Theme.surface0 : Theme.mantle
                                border.color: dropHighlighted ? Theme.lavender
                                    : overview.selectedWorkspace === number ? Theme.lavender
                                    : hovered ? Theme.overlay1
                                    : occupied ? Theme.strongBorder : Theme.separator
                                border.width: dropHighlighted || overview.selectedWorkspace === number ? 2 : 1
                                Behavior on color { ColorAnimation { duration: 110 } }
                                HoverHandler { id: cardHover }
                                Rectangle {
                                    anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter
                                    width: parent.width - 16; height: 2; radius: 1
                                    color: workspaceCard.active || workspaceCard.dropHighlighted
                                        ? Theme.lavender : "transparent"
                                }
                                DropArea {
                                    id: dropArea
                                    anchors.fill: parent
                                    keys: ["labfy-workspace-window"]
                                    onDropped: drop => {
                                        if (drop.source && drop.source.conId > 0
                                                && drop.source.sourceWorkspace !== workspaceCard.number) {
                                            overview.moveWindow(drop.source.conId, workspaceCard.number);
                                            drop.acceptProposedAction();
                                        }
                                    }
                                }
                                MouseArea {
                                    id: cardPointer
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: overview.activateWorkspace(workspaceCard.number)
                                }
                                Column {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 5
                                    Item {
                                        id: cardHeader
                                        width: parent.width; height: 24
                                        Rectangle {
                                            id: numberBadge
                                            anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                                            width: 30; height: 22; radius: 3
                                            color: workspaceCard.active || workspaceCard.dropHighlighted
                                                ? Theme.lavender : Theme.surface1
                                            Text {
                                                anchors.centerIn: parent
                                                text: String(workspaceCard.number).padStart(2, "0")
                                                color: workspaceCard.active || workspaceCard.dropHighlighted
                                                    ? Theme.onAccent : Theme.foreground
                                                font.bold: true; font.pixelSize: 12
                                            }
                                        }
                                        Text {
                                            anchors.left: numberBadge.right; anchors.leftMargin: 7
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Math.max(0, parent.width - 78)
                                            text: workspaceCard.modelData.output || "Disponible"
                                            color: workspaceCard.occupied ? Theme.foreground : Theme.secondaryForeground
                                            font.pixelSize: 11; elide: Text.ElideRight
                                        }
                                        Text {
                                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                            text: workspaceCard.occupied ? String(workspaceCard.modelData.windows.length) : "—"
                                            color: workspaceCard.occupied ? Theme.accentForeground : Theme.disabledForeground
                                            font.pixelSize: 11; font.bold: workspaceCard.occupied
                                        }
                                    }
                                    Item {
                                        id: preview
                                        width: parent.width
                                        height: Math.max(0, parent.height - cardHeader.height
                                            - provenance.implicitHeight - parent.spacing * 2)
                                        clip: true
                                        Rectangle {
                                            anchors.fill: parent; radius: 3
                                            color: Theme.crust; border.color: Theme.separator
                                        }
                                        Image {
                                            anchors.fill: parent
                                            source: workspaceCard.modelData.snapshot ? workspaceCard.modelData.snapshot
                                                + "?t=" + workspaceCard.modelData.snapshotTime : ""
                                            visible: workspaceCard.modelData.snapshot !== ""
                                                && workspaceCard.modelData.windows.length > 0
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            cache: false
                                        }
                                        Column {
                                            anchors.centerIn: parent
                                            visible: workspaceCard.modelData.windows.length === 0
                                                && !workspaceCard.dropHighlighted
                                            spacing: 7
                                            Rectangle {
                                                anchors.horizontalCenter: parent.horizontalCenter
                                                width: 30; height: 21; radius: 2
                                                color: "transparent"; border.color: Theme.overlay0
                                                Rectangle {
                                                    anchors.left: parent.left; anchors.right: parent.right
                                                    anchors.top: parent.top; anchors.margins: 3
                                                    height: 2; radius: 1; color: Theme.overlay0
                                                }
                                            }
                                            Text { anchors.horizontalCenter: parent.horizontalCenter
                                                text: "Espace vide"; color: Theme.secondaryForeground;
                                                font.pixelSize: 12; font.bold: true }
                                        }
                                        Repeater {
                                            model: workspaceCard.modelData.windows
                                            delegate: Rectangle {
                                                id: windowVisual
                                                required property var modelData
                                                required property int index
                                                property int conId: modelData.id
                                                property int sourceWorkspace: workspaceCard.number
                                                readonly property var outputRect: workspaceCard.modelData.outputRect || workspaceCard.modelData.rect
                                                readonly property real sx: outputRect && outputRect.width ? preview.width / outputRect.width : 1
                                                readonly property real sy: outputRect && outputRect.height ? preview.height / outputRect.height : 1
                                                x: Math.max(0, (modelData.rect.x - (outputRect ? outputRect.x : 0)) * sx)
                                                y: Math.max(0, (modelData.rect.y - (outputRect ? outputRect.y : 0)) * sy)
                                                width: Math.max(15, Math.min(preview.width - x, modelData.rect.width * sx))
                                                height: Math.max(15, Math.min(preview.height - y, modelData.rect.height * sy))
                                                radius: 2
                                                clip: true
                                                color: workspaceCard.modelData.snapshot ? "#1e1e2e35" : Theme.surface1
                                                border.color: modelData.focused || (overview.selectedWorkspace === workspaceCard.number
                                                    && overview.selectedWindow === index + 1) ? Theme.lavender : Theme.overlay0
                                                border.width: modelData.focused ? 2 : 1
                                                Image {
                                                    anchors.fill: parent
                                                    source: !workspaceCard.modelData.snapshot && windowVisual.modelData.preview
                                                        ? windowVisual.modelData.preview + "?t=" + windowVisual.modelData.previewTime : ""
                                                    visible: !workspaceCard.modelData.snapshot
                                                        && windowVisual.modelData.preview !== ""
                                                    fillMode: Image.PreserveAspectCrop
                                                    asynchronous: true
                                                    cache: false
                                                }
                                                // WHY: déplacer la zone source hors du preview rogné
                                                // perdait les positions de la souris et l'état de dépôt.
                                                // Le proxy vit dans la surface, la miniature reste en place.
                                                Rectangle {
                                                    id: dragProxy
                                                    parent: keyboardRoot
                                                    z: 1000
                                                    width: 138; height: 34; radius: 3
                                                    opacity: windowPointer.drag.active ? 1 : 0
                                                    color: Theme.surface2
                                                    border.color: Theme.lavender; border.width: 1
                                                    Drag.active: windowPointer.drag.active
                                                    Drag.source: windowVisual
                                                    Drag.keys: ["labfy-workspace-window"]
                                                    Drag.hotSpot.x: width / 2
                                                    Drag.hotSpot.y: height / 2
                                                    Text {
                                                        anchors.fill: parent; anchors.margins: 6
                                                        text: windowVisual.modelData.app
                                                        color: Theme.foreground; font.pixelSize: 11
                                                        font.bold: true; elide: Text.ElideRight
                                                        verticalAlignment: Text.AlignVCenter
                                                    }
                                                }
                                                Text {
                                                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                                                    height: Math.min(28, parent.height)
                                                    leftPadding: 3
                                                    text: windowVisual.modelData.app + " · " + windowVisual.modelData.title
                                                    color: Theme.foreground; font.pixelSize: 9; elide: Text.ElideRight
                                                    verticalAlignment: Text.AlignVCenter
                                                    Rectangle { anchors.fill: parent; z: -1; color: "#11111bc9" }
                                                }
                                                MouseArea {
                                                    id: windowPointer
                                                    anchors.fill: parent
                                                    drag.target: dragProxy
                                                    drag.threshold: 6
                                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                                    onPressed: {
                                                        const point = windowVisual.mapToItem(keyboardRoot, 0, 0);
                                                        dragProxy.x = point.x;
                                                        dragProxy.y = point.y;
                                                        overview.selectedWorkspace = workspaceCard.number;
                                                    }
                                                    onClicked: mouse => {
                                                        overview.selectedWindow = windowVisual.index + 1;
                                                        if (mouse.button === Qt.RightButton) {
                                                            overview.moveTarget = workspaceCard.number === 10 ? 1 : workspaceCard.number + 1;
                                                            keyboardRoot.forceActiveFocus();
                                                        } else if (!drag.active)
                                                            overview.focusWindow(workspaceCard.number, windowVisual.conId);
                                                    }
                                                    onPositionChanged: mouse => {
                                                        if (!drag.active) return;
                                                        const point = windowPointer.mapToItem(keyboardRoot, mouse.x, mouse.y);
                                                        const target = overview.workspaceAt(point.x, point.y);
                                                        overview.dropTarget = target !== workspaceCard.number ? target : 0;
                                                    }
                                                    onReleased: mouse => {
                                                        if (drag.active) {
                                                            const point = windowPointer.mapToItem(keyboardRoot, mouse.x, mouse.y);
                                                            const target = overview.workspaceAt(point.x, point.y);
                                                            if (target && target !== workspaceCard.number)
                                                                overview.moveWindow(windowVisual.conId, target);
                                                        }
                                                        overview.dropTarget = 0;
                                                    }
                                                    onCanceled: overview.dropTarget = 0
                                                }
                                            }
                                        }
                                        Rectangle {
                                            anchors.fill: parent; z: 2; radius: 3
                                            color: "transparent"; border.color: Theme.overlay0
                                            border.width: 1
                                        }
                                        Rectangle {
                                            anchors.fill: parent; z: 3; radius: 3
                                            visible: workspaceCard.dropHighlighted
                                            // Qt lit #AARRGGBB : alpha faible, accent Lavender.
                                            color: "#32b4befe"
                                            border.color: Theme.lavender; border.width: 2
                                            Text { anchors.centerIn: parent; text: "Déposer ici";
                                                color: Theme.foreground; font.pixelSize: 12; font.bold: true }
                                        }
                                    }
                                    Text {
                                        id: provenance
                                        text: workspaceCard.modelData.windows.length === 0
                                            ? "Aucune fenêtre"
                                            : workspaceCard.modelData.snapshot
                                            ? (workspaceCard.modelData.visible ? "Capture · sortie visible" : "Dernière capture · fenêtre actualisée")
                                            : workspaceCard.modelData.windows.some(window => window.preview)
                                            ? "Dernières images · fenêtres"
                                            : "Géométrie · arbre Sway"
                                        color: Theme.secondaryForeground; font.pixelSize: 10; elide: Text.ElideRight
                                        width: parent.width
                                    }
                                }
                            }
                        }
                    }
                }
                Rectangle {
                    id: footer
                    width: parent.width; height: 32; radius: 3
                    color: Theme.mantle; border.color: Theme.separator
                    Row {
                        anchors.left: parent.left; anchors.leftMargin: 11
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 13
                        visible: overview.moveTarget === 0
                        Row { spacing: 5
                            Text { text: "← ↑ ↓ →"; color: Theme.lavender; font.pixelSize: 11; font.bold: true }
                            Text { text: "naviguer"; color: Theme.secondaryForeground; font.pixelSize: 11 }
                        }
                        Row { spacing: 5
                            Text { text: "Tab"; color: Theme.lavender; font.pixelSize: 11; font.bold: true }
                            Text { text: "fenêtre"; color: Theme.secondaryForeground; font.pixelSize: 11 }
                        }
                        Row { spacing: 5
                            Text { text: "M"; color: Theme.lavender; font.pixelSize: 11; font.bold: true }
                            Text { text: "déplacer"; color: Theme.secondaryForeground; font.pixelSize: 11 }
                        }
                        Row { spacing: 5
                            Text { text: "Entrée"; color: Theme.lavender; font.pixelSize: 11; font.bold: true }
                            Text { text: "activer"; color: Theme.secondaryForeground; font.pixelSize: 11 }
                            visible: footer.width > 620
                        }
                        Text { text: "Clic droit ou glisser : déplacer"; color: Theme.secondaryForeground;
                            font.pixelSize: 11; visible: footer.width > 820 }
                    }
                    Text {
                        anchors.left: parent.left; anchors.leftMargin: 11
                        anchors.verticalCenter: parent.verticalCenter
                        visible: overview.moveTarget !== 0
                        text: "Déplacer vers " + overview.moveTarget + " · 1–9 ou 0=10 · Entrée confirmer"
                        color: Theme.accentForeground; font.pixelSize: 11; font.bold: true
                    }
                    Text {
                        anchors.right: parent.right; anchors.rightMargin: 11
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Échap  fermer"; color: Theme.secondaryForeground; font.pixelSize: 11
                    }
                }
            }
        }
    }
}

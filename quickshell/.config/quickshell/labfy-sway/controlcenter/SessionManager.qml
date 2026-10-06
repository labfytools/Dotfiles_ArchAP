import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import "../components"
import "../theme"

Item {
    id: page

    required property bool activePage
    signal backRequested()

    // WHY: la configuration peut être déployée pour n'importe quel utilisateur.
    // CONTRACT: le backend est celui de la configuration QuickShell XDG active.
    // INVARIANT: aucun nom utilisateur ni chemin de dépôt n'est encodé ici.
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME")
        || ((Quickshell.env("HOME") || "") + "/.config")
    readonly property string backend: configHome
        + "/quickshell/labfy-sway/session/session_snapshot.py"

    property string view: "list"
    property string phase: "idle"
    property string operation: ""
    property string pendingName: ""
    property string nameDraft: ""
    property string errorMessage: ""
    property string technicalDetails: ""
    property string feedback: ""
    property var sessions: []
    property var selectedSession: null
    property var snapshot: null
    property var plan: null
    property var restoreReport: null
    readonly property bool busy: backendProcess.running || phase === "running"
    readonly property bool mutatingBusy: busy
        && ["save", "delete", "apply"].includes(operation)
    readonly property bool validName: /^[A-Za-z0-9_-]{1,64}$/.test(nameDraft)

    function commandFor(kind, name) {
        // CONTRACT: chaque argument reste une valeur argv indépendante ; le nom
        // de session ne traverse jamais une interpolation ou un shell.
        const argv = ["python3", backend, "--compact"];
        if (kind === "apply") argv.push("--execute");
        argv.push(kind);
        if (name) argv.push(name);
        return argv;
    }

    function run(kind, name) {
        // WHY: les locks backend protègent les données, mais pas le double-clic.
        // CONTRACT: un unique Process porte list/show/plan et les mutations.
        // INVARIANT: aucune nouvelle opération ne démarre tant qu'il est occupé.
        if (busy) return false;
        operation = kind;
        pendingName = name || "";
        phase = "running";
        if (kind !== "list") {
            errorMessage = "";
            technicalDetails = "";
        }
        if (kind !== "list") feedback = "";
        backendProcess.command = commandFor(kind, pendingName);
        backendProcess.running = true;
        return true;
    }

    function refresh() { run("list", ""); }

    function openCreate() {
        if (busy) return;
        nameDraft = "";
        errorMessage = "";
        view = "create";
    }

    function requestSave() {
        if (!validName || busy) return;
        const exists = sessions.some(item => item.name === nameDraft);
        view = exists ? "duplicate" : "create";
        if (!exists) run("save", nameDraft);
    }

    function openDetails(item) {
        if (busy || !item) return;
        selectedSession = item;
        snapshot = null;
        view = "details";
        run("show", item.name);
    }

    function preview() {
        if (!selectedSession || busy) return;
        plan = null;
        view = "plan";
        run("plan", selectedSession.name);
    }

    function goBack() {
        errorMessage = "";
        technicalDetails = "";
        if (view === "list") {
            backRequested();
        } else if (["create", "duplicate", "details"].includes(view)) {
            view = "list";
        } else if (["plan", "deleteConfirm"].includes(view)) {
            view = "details";
        } else if (view === "restoreConfirm") {
            view = "plan";
        } else {
            view = plan ? "plan" : "details";
        }
    }

    function parseJson(text) {
        try { return JSON.parse(text); }
        catch (_) { return undefined; }
    }

    function errorFor(raw) {
        const value = raw || "Erreur backend inconnue";
        if (value.includes("RESTORE_ALREADY_RUNNING"))
            return "Une restauration est déjà en cours.";
        if (value.includes("RESTORE_TREE_DRIFTED"))
            return "La disposition des fenêtres a changé pendant la restauration. Aucun traitement supplémentaire n’a été effectué.";
        if (value.includes("RESTORE_LAUNCH_TIMEOUT"))
            return "Une application n’a pas créé sa fenêtre dans le délai prévu.";
        if (value.includes("RESTORE_LAUNCH_AMBIGUOUS"))
            return "La nouvelle fenêtre ne peut pas être identifiée sans ambiguïté.";
        if (value.includes("RESTORE_BLOCKED_UNSUPPORTED_ACTION"))
            return "Le preflight a bloqué des actions non prises en charge.";
        if (value.includes("session introuvable"))
            return "Cette session n’existe plus.";
        return "L’opération a échoué.";
    }

    function finishFailure(stdoutText, stderrText) {
        const parsed = parseJson(stdoutText);
        const raw = (parsed && parsed.reason) || stderrText.trim() || stdoutText.trim();
        phase = "error";
        errorMessage = errorFor(raw);
        technicalDetails = raw;
        if (operation === "apply") {
            restoreReport = parsed || ({ status: "failed", reason: raw });
            view = "result";
        } else if ((operation === "show" || operation === "plan")
                && raw.includes("session introuvable")) {
            selectedSession = null;
            snapshot = null;
            plan = null;
            view = "list";
            Qt.callLater(refresh);
        }
    }

    function acceptSuccess(value) {
        if (operation === "list") {
            if (!Array.isArray(value)) return false;
            sessions = value;
        } else if (operation === "show") {
            if (!value || !value.metadata || !Array.isArray(value.windows)
                    || !Array.isArray(value.workspaces)) return false;
            snapshot = value;
        } else if (operation === "plan") {
            if (!value || value.read_only !== true || !Array.isArray(value.actions)) return false;
            plan = value;
        } else if (operation === "save") {
            if (!value || value.name !== pendingName) return false;
            feedback = "Session sauvegardée";
            view = "list";
            Qt.callLater(refresh);
        } else if (operation === "delete") {
            if (!value || value.deleted !== pendingName) return false;
            selectedSession = null;
            snapshot = null;
            plan = null;
            feedback = "Session supprimée";
            view = "list";
            Qt.callLater(refresh);
        } else if (operation === "apply") {
            if (!value || value.status !== "success") return false;
            restoreReport = value;
            view = "result";
        }
        return true;
    }

    function formatDate(value) {
        const date = new Date(value);
        if (isNaN(date.getTime())) return value || "Date inconnue";
        const now = new Date();
        const sameDay = date.getFullYear() === now.getFullYear()
            && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
        const time = date.toLocaleTimeString(Qt.locale(), "HH:mm");
        return sameDay ? "Mis à jour aujourd’hui à " + time
            : "Mis à jour le " + date.toLocaleDateString(Qt.locale(), "dd/MM/yyyy") + " à " + time;
    }

    function plural(count, singular, pluralValue) {
        return count + " " + (count === 1 ? singular : pluralValue);
    }

    function applicationLabel(item) {
        if (!item) return "Application inconnue";
        const identity = item.restore_identity || {};
        const desktop = identity.desktop_entry || item.desktop_entry;
        if (desktop) {
            const stem = desktop.replace(/\.desktop$/, "");
            return stem.charAt(0).toUpperCase() + stem.slice(1);
        }
        return identity.app_id || item.app_id || identity.class
            || (item.xwayland && item.xwayland.class)
            || item.executable_basename || "Application inconnue";
    }

    function countAction(kind) {
        if (!plan || !Array.isArray(plan.actions)) return 0;
        return plan.actions.filter(item => item.action === kind).length;
    }

    function isBlocking(item) {
        return item && (item.action === "manual-required" || item.confidence === "ambiguous");
    }

    function blockerCount() {
        if (!plan || !Array.isArray(plan.actions)) return 0;
        return plan.actions.filter(item => isBlocking(item)).length;
    }

    function groupFor(action) {
        if (action === "reuse-window") return "RÉUTILISER";
        if (action === "launch-application") return "LANCER";
        if (action === "move-to-workspace") return "DÉPLACER";
        if (action === "restore-tree-position") return "LAYOUT";
        if (action === "restore-floating") return "FLOATING";
        if (action === "restore-fullscreen") return "FULLSCREEN";
        if (action.indexOf("restore-scratchpad") === 0) return "SCRATCHPAD";
        if (action === "restore-focus") return "FOCUS";
        if (action === "manual-required") return "INTERVENTION MANUELLE";
        return "AUTRE";
    }

    function actionText(item) {
        const label = item.desktop_entry
            ? applicationLabel({ desktop_entry: item.desktop_entry })
            : (item.snapshot_identity || item.source_window || "Fenêtre");
        if (item.action === "reuse-window" && item.confidence === "ambiguous")
            return "! " + label + " : correspondance ambiguë";
        if (item.action === "reuse-window") return "✓ " + label;
        if (item.action === "launch-application") return "+ " + label;
        if (item.action === "move-to-workspace") return "→ " + label + " vers WS " + item.desired_workspace;
        if (item.action === "restore-tree-position") return "▦ Restaurer la disposition de " + label;
        if (item.action === "restore-floating") return "◫ Restaurer le mode flottant de " + label;
        if (item.action === "restore-fullscreen") return "󰊓 Restaurer le plein écran de " + label;
        if (item.action === "restore-scratchpad-hidden") return "↘ " + label + " → cachée";
        if (item.action === "restore-scratchpad-visible") return "↗ " + label + " → visible";
        if (item.action === "restore-focus") return "◎ Rendre le focus à " + label;
        if (item.reason === "missing-output") return "! Écran " + (item.desired_output || "requis") + " absent";
        if (item.reason === "no-exact-launch-identity") return "! Application " + label + " non identifiable";
        return "! " + label + " : " + (item.reason || "intervention requise");
    }

    function resultCount(key) {
        return restoreReport && Number.isInteger(restoreReport[key]) ? restoreReport[key] : 0;
    }

    onActivePageChanged: {
        if (activePage) {
            view = "list";
            errorMessage = "";
            technicalDetails = "";
            feedback = "";
            selectedSession = null;
            snapshot = null;
            plan = null;
            restoreReport = null;
            refresh();
        }
    }

    Process {
        id: backendProcess
        running: false
        // CONTRACT: stdout reste un document JSON complet ; stderr ne participe
        // jamais au parsing et conserve les diagnostics destinés à l'utilisateur.
        stdout: StdioCollector { id: backendOutput; waitForEnd: true }
        stderr: StdioCollector { id: backendError; waitForEnd: true }
        onExited: (exitCode, exitStatus) => {
            const stdoutText = backendOutput.text;
            const stderrText = backendError.text;
            if (exitCode !== 0 || exitStatus !== 0) {
                page.finishFailure(stdoutText, stderrText);
                return;
            }
            const value = page.parseJson(stdoutText);
            if (value === undefined || !page.acceptSuccess(value)) {
                page.phase = "error";
                page.errorMessage = "Réponse invalide du gestionnaire de sessions.";
                page.technicalDetails = stderrText.trim() || "JSON stdout invalide ou inattendu";
                return;
            }
            page.phase = "success";
            if (stderrText.trim().length > 0)
                page.errorMessage = stderrText.trim();
        }
    }

    Column {
        anchors.fill: parent
        spacing: 10

        Row {
            width: parent.width
            height: 30
            spacing: 8
            ActionButton { label: ""; enabled: !page.busy; onClicked: page.goBack() }
            Text {
                width: parent.width - saveButton.width - 82
                height: 30
                verticalAlignment: Text.AlignVCenter
                text: page.view === "list" ? "Sessions"
                    : page.view === "details" || page.view === "deleteConfirm" ? "Détail de la session"
                    : page.view === "plan" || page.view === "restoreConfirm" ? "Aperçu de restauration"
                    : page.view === "result" ? "Restauration" : "Sauvegarder une session"
                color: Theme.foreground
                font.pixelSize: 16
                font.bold: true
                elide: Text.ElideRight
            }
            ActionButton {
                id: saveButton
                visible: page.view === "list"
                enabled: !page.busy
                label: "Sauvegarder"
                onClicked: page.openCreate()
            }
        }

        Text {
            width: parent.width
            visible: page.busy
            text: page.operation === "apply" ? "Restauration en cours…"
                : page.operation === "list" ? "Actualisation…" : "Traitement en cours…"
            color: Theme.secondaryForeground
            font.pixelSize: 12
        }
        Text {
            width: parent.width
            visible: page.errorMessage.length > 0 && page.view !== "result"
            text: page.errorMessage
            wrapMode: Text.Wrap
            color: Theme.warningForeground
            font.pixelSize: 12
        }
        Text {
            width: parent.width
            visible: page.feedback.length > 0 && page.view === "list"
            text: page.feedback
            wrapMode: Text.Wrap
            color: Theme.successForeground
            font.pixelSize: 12
        }

        Loader {
            width: parent.width
            height: parent.height - y
            sourceComponent: page.view === "list" ? listComponent
                : page.view === "create" ? createComponent
                : page.view === "duplicate" ? duplicateComponent
                : page.view === "details" ? detailsComponent
                : page.view === "deleteConfirm" ? deleteComponent
                : page.view === "plan" ? planComponent
                : page.view === "restoreConfirm" ? restoreConfirmComponent
                : resultComponent
        }
    }

    Component {
        id: listComponent
        Item {
            Text {
                anchors.centerIn: parent
                visible: !page.busy && page.sessions.length === 0
                text: "Aucune session sauvegardée"
                color: Theme.secondaryForeground
                font.pixelSize: 14
            }
            ActionButton {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.verticalCenter
                anchors.topMargin: 24
                visible: !page.busy && page.sessions.length === 0
                label: "Sauvegarder la session actuelle"
                onClicked: page.openCreate()
            }
            ScrollView {
                anchors.fill: parent
                visible: page.sessions.length > 0
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Column {
                    width: page.width - 14
                    spacing: 8
                    Repeater {
                        model: page.sessions
                        delegate: Rectangle {
                            required property var modelData
                            width: parent.width
                            height: 72
                            radius: 4
                            color: sessionPointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
                            Column {
                                anchors.left: parent.left; anchors.leftMargin: 12
                                anchors.right: parent.right; anchors.rightMargin: 34
                                anchors.verticalCenter: parent.verticalCenter; spacing: 3
                                Text { width: parent.width; text: modelData.name; elide: Text.ElideRight; color: Theme.foreground; font.pixelSize: 13; font.bold: true }
                                Text { text: page.plural(modelData.windows, "fenêtre", "fenêtres") + " • " + page.plural(modelData.workspaces, "espace", "espaces"); color: Theme.secondaryForeground; font.pixelSize: 11 }
                                Text { width: parent.width; text: page.formatDate(modelData.updated_at); elide: Text.ElideRight; color: Theme.disabledForeground; font.pixelSize: 10 }
                            }
                            Text { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: ""; color: Theme.accentForeground; font.pixelSize: 13 }
                            MouseArea { id: sessionPointer; anchors.fill: parent; hoverEnabled: true; enabled: !page.busy; onClicked: page.openDetails(modelData) }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: createComponent
        Column {
            spacing: 12
            Text { text: "Nom de la session"; color: Theme.foreground; font.pixelSize: 13; font.bold: true }
            TextField {
                id: nameInput
                width: parent.width
                text: page.nameDraft
                maximumLength: 64
                placeholderText: "Développement"
                enabled: !page.busy
                onTextEdited: page.nameDraft = text
                onAccepted: page.requestSave()
            }
            Text {
                width: parent.width
                text: page.nameDraft.length === 0 ? "1 à 64 caractères : A-Z, a-z, 0-9, - et _."
                    : page.validName ? "Nom valide" : "Utiliser uniquement A-Z, a-z, 0-9, - et _ (64 caractères maximum)."
                color: page.nameDraft.length === 0 || page.validName ? Theme.secondaryForeground : Theme.warningForeground
                wrapMode: Text.Wrap; font.pixelSize: 11
            }
            ActionButton { label: "Sauvegarder"; enabled: page.validName && !page.busy; onClicked: page.requestSave() }
        }
    }

    Component {
        id: duplicateComponent
        Column {
            spacing: 16
            Text { width: parent.width; text: "La session existe déjà.\nMettre à jour cette sauvegarde ?"; wrapMode: Text.Wrap; color: Theme.foreground; font.pixelSize: 14; font.bold: true }
            Row {
                spacing: 8
                ActionButton { label: "Annuler"; enabled: !page.busy; onClicked: page.view = "create" }
                ActionButton { label: "Mettre à jour"; enabled: !page.busy; onClicked: page.run("save", page.nameDraft) }
            }
        }
    }

    Component {
        id: detailsComponent
        ScrollView {
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: page.width - 14
                spacing: 9
                Text { width: parent.width; text: page.selectedSession ? page.selectedSession.name : ""; wrapMode: Text.Wrap; color: Theme.foreground; font.pixelSize: 17; font.bold: true }
                Text { visible: !!page.snapshot; text: "Créée : " + page.formatDate(page.snapshot ? page.snapshot.metadata.created_at : "").replace("Mis à jour ", ""); color: Theme.secondaryForeground; font.pixelSize: 11 }
                Text { visible: !!page.snapshot; text: "Mise à jour : " + page.formatDate(page.snapshot ? page.snapshot.metadata.updated_at : "").replace("Mis à jour ", ""); color: Theme.secondaryForeground; font.pixelSize: 11 }
                Text { visible: !!page.snapshot; text: page.plural(page.snapshot ? page.snapshot.workspaces.length : 0, "espace", "espaces") + " • " + page.plural(page.snapshot ? page.snapshot.windows.length : 0, "fenêtre", "fenêtres"); color: Theme.foreground; font.pixelSize: 12 }
                Text { visible: !!page.snapshot; text: "Moteur de disposition : " + (page.snapshot ? page.snapshot.compositor.layout_engine : ""); color: Theme.secondaryForeground; font.pixelSize: 11 }
                Text { visible: !!page.snapshot; text: "FENÊTRES"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
                Repeater {
                    model: page.snapshot ? page.snapshot.windows : []
                    delegate: Rectangle {
                        required property var modelData
                        width: parent.width; height: 38; radius: 4; color: Theme.buttonBackground
                        Text { anchors.left: parent.left; anchors.leftMargin: 9; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 90; text: page.applicationLabel(modelData); elide: Text.ElideRight; color: Theme.foreground; font.pixelSize: 12 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 9; anchors.verticalCenter: parent.verticalCenter; text: modelData.workspace ? "WS " + modelData.workspace : modelData.scratchpad && modelData.scratchpad.member ? "Scratchpad" : "—"; color: Theme.secondaryForeground; font.pixelSize: 11 }
                    }
                }
                Row {
                    visible: !!page.snapshot
                    spacing: 8
                    ActionButton { label: "Mettre à jour"; enabled: !page.mutatingBusy && !page.busy; onClicked: page.run("save", page.selectedSession.name) }
                    ActionButton { label: "Prévisualiser"; enabled: !page.busy; onClicked: page.preview() }
                    ActionButton { label: "Supprimer"; danger: true; enabled: !page.mutatingBusy && !page.busy; onClicked: page.view = "deleteConfirm" }
                }
            }
        }
    }

    Component {
        id: deleteComponent
        Column {
            spacing: 16
            Text { width: parent.width; text: "Supprimer « " + (page.selectedSession ? page.selectedSession.name : "") + " » ?"; wrapMode: Text.Wrap; color: Theme.danger; font.pixelSize: 15; font.bold: true }
            Text { width: parent.width; text: "Cette sauvegarde sera définitivement supprimée."; wrapMode: Text.Wrap; color: Theme.secondaryForeground; font.pixelSize: 12 }
            Row {
                spacing: 8
                ActionButton { label: "Annuler"; enabled: !page.busy; onClicked: page.view = "details" }
                ActionButton { label: "Supprimer"; danger: true; enabled: !page.busy; onClicked: page.run("delete", page.selectedSession.name) }
            }
        }
    }

    Component {
        id: planComponent
        Column {
            spacing: 8
            Text { visible: !!page.plan && page.blockerCount() > 0; width: parent.width; text: "Restauration incomplète"; color: Theme.warningForeground; font.pixelSize: 13; font.bold: true }
            Grid {
                visible: !!page.plan
                columns: 3; spacing: 5
                Repeater {
                    model: page.plan ? [
                        ["Réutilisées", page.countAction("reuse-window")], ["À lancer", page.countAction("launch-application")], ["À déplacer", page.countAction("move-to-workspace")],
                        ["Layout", page.countAction("restore-tree-position")], ["Floating", page.countAction("restore-floating")], ["Fullscreen", page.countAction("restore-fullscreen")],
                        ["Scratchpad", page.countAction("restore-scratchpad-hidden") + page.countAction("restore-scratchpad-visible")], ["Focus", page.countAction("restore-focus")], ["Intervention", page.blockerCount()]
                    ] : []
                    delegate: Rectangle {
                        required property var modelData
                        width: (page.width - 24) / 3; height: 48; radius: 4; color: Theme.buttonBackground
                        Column { anchors.centerIn: parent; Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData[1]; color: Theme.foreground; font.pixelSize: 15; font.bold: true } Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData[0]; color: Theme.secondaryForeground; font.pixelSize: 9 } }
                    }
                }
            }
            Text { visible: !!page.plan; text: "ACTIONS"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
            ScrollView {
                width: parent.width; height: 245; visible: !!page.plan; clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Column {
                    width: page.width - 14; spacing: 4
                    Repeater {
                        model: page.plan ? page.plan.actions : []
                        delegate: Rectangle {
                            required property var modelData
                            width: parent.width; height: actionText.implicitHeight + 20; radius: 4
                            color: page.isBlocking(modelData) ? Theme.buttonHover : Theme.buttonBackground
                            Column { anchors.left: parent.left; anchors.leftMargin: 9; anchors.right: parent.right; anchors.rightMargin: 9; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                                Text { text: page.groupFor(modelData.action); color: page.isBlocking(modelData) ? Theme.warningForeground : Theme.accentForeground; font.pixelSize: 9; font.bold: true }
                                Text { id: actionText; width: parent.width; text: page.actionText(modelData); wrapMode: Text.Wrap; color: Theme.foreground; font.pixelSize: 11 }
                            }
                        }
                    }
                }
            }
            Text { visible: !!page.plan; width: parent.width; wrapMode: Text.Wrap; text: "La restauration replace les fenêtres et le layout. L’état interne des applications n’est pas garanti (onglets, documents, contenu d’un terminal, etc.). Les proportions exactes des splits ne sont pas restaurées."; color: Theme.secondaryForeground; font.pixelSize: 10 }
            Text { visible: !!page.plan; width: parent.width; wrapMode: Text.Wrap; text: "L’état sera revérifié au moment de la restauration. La sauvegarde utilisée sera son état actuel au moment de l’exécution."; color: Theme.secondaryForeground; font.pixelSize: 10 }
            ActionButton { visible: !!page.plan; label: "Restaurer"; enabled: !page.busy; onClicked: page.view = "restoreConfirm" }
        }
    }

    Component {
        id: restoreConfirmComponent
        Column {
            spacing: 16
            Text { width: parent.width; text: "Restaurer « " + (page.selectedSession ? page.selectedSession.name : "") + " » ?"; wrapMode: Text.Wrap; color: Theme.foreground; font.pixelSize: 15; font.bold: true }
            Text { width: parent.width; text: "Les applications manquantes pourront être lancées et les fenêtres existantes déplacées."; wrapMode: Text.Wrap; color: Theme.secondaryForeground; font.pixelSize: 12 }
            Text { width: parent.width; text: "Un plan frais et le preflight seront recalculés avant toute action."; wrapMode: Text.Wrap; color: Theme.secondaryForeground; font.pixelSize: 11 }
            Row {
                spacing: 8
                ActionButton { label: "Annuler"; enabled: !page.busy; onClicked: page.view = "plan" }
                ActionButton { label: "Restaurer"; enabled: !page.busy; onClicked: page.run("apply", page.selectedSession.name) }
            }
        }
    }

    Component {
        id: resultComponent
        Column {
            spacing: 12
            Text { width: parent.width; text: page.restoreReport && page.restoreReport.status === "success" ? "Session restaurée" : "Restauration interrompue"; color: page.restoreReport && page.restoreReport.status === "success" ? Theme.successForeground : Theme.warningForeground; font.pixelSize: 16; font.bold: true }
            Text { visible: page.restoreReport && page.restoreReport.status === "success"; text: page.plural(page.resultCount("applications_launched"), "application lancée", "applications lancées") + " • " + page.plural(page.resultCount("mutating_commands_executed"), "action exécutée", "actions exécutées"); color: Theme.foreground; font.pixelSize: 12 }
            Text { visible: page.errorMessage.length > 0; width: parent.width; text: page.errorMessage; wrapMode: Text.Wrap; color: Theme.warningForeground; font.pixelSize: 12 }
            Text { visible: page.technicalDetails.length > 0; width: parent.width; text: "Détails : " + page.technicalDetails; wrapMode: Text.Wrap; color: Theme.disabledForeground; font.pixelSize: 10 }
            Row {
                spacing: 8
                ActionButton { label: "Fermer"; enabled: !page.busy; onClicked: { page.view = "details"; page.restoreReport = null; } }
                ActionButton { label: "Actualiser"; enabled: !page.busy; onClicked: { page.view = "list"; page.restoreReport = null; page.refresh(); } }
            }
        }
    }
}

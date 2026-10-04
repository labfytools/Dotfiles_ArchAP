import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Notifications

QtObject {
    id: store
    // CONTRACT: ce fichier appartient à XDG_STATE_HOME, jamais aux dotfiles.
    readonly property string path: Quickshell.statePath("notifications.json")
    readonly property int maxRecords: 200
    property var records: []
    // CONTRACT: le compte dérive uniquement des records durables, jamais des toasts.
    readonly property int unreadCount: records.filter(r => r.read === false).length
    readonly property int criticalUnreadCount: records.filter(r => r.read === false
        && r.urgency === NotificationUrgency.Critical).length
    property int nextId: 1
    property bool ready: false

    property FileView file: FileView {
        path: store.path
        blockWrites: true
        atomicWrites: true
        onLoaded: store.load()
        onLoadFailed: store.load()
        onSaveFailed: error => console.warn("Historique notifications : écriture échouée", error)
    }

    function load() {
        if (ready) return;
        let value = null;
        let migrationNeeded = false;
        try {
            const raw = file.text();
            value = raw ? JSON.parse(raw) : null;
            if (value && (value.version === 1 || value.version === 2) && Array.isArray(value.records)) {
                migrationNeeded = value.version === 1 || value.records.some(r => r
                    && (typeof r.read !== "boolean" || !("readAt" in r)));
                records = value.records.filter(r => r && Number.isSafeInteger(r.internalId)
                    && r.internalId > 0 && typeof r.summary === "string").slice(0, maxRecords)
                    .map(r => Object.assign({}, r, {
                        // WHY: les anciens imports et historiques précèdent la notion de consultation.
                        read: typeof r.read === "boolean" ? r.read : true,
                        readAt: typeof r.readAt === "string" ? r.readAt : null
                    }));
                nextId = Math.max(Number.isSafeInteger(value.nextId) && value.nextId > 0
                    ? value.nextId : 1, 1, ...records.map(r => r.internalId + 1));
            }
        } catch (error) {
            console.warn("Historique notifications illisible : conservation du fichier", error);
            return;
        }
        ready = true;
        // INVARIANT: la migration conserve chaque champ utilisateur et persiste le schéma v2.
        if (migrationNeeded) save();
    }

    // INVARIANT: tout changement visible est écrit atomiquement avant retour à l'UI.
    function save() {
        if (!ready) return;
        file.setText(JSON.stringify({ version: 2, nextId: nextId, records: records }));
    }

    function upsert(record) {
        const rest = records.filter(r => r.internalId !== record.internalId);
        records = [record].concat(rest).slice(0, maxRecords);
        nextId = Math.max(nextId, record.internalId + 1);
        save();
    }

    function remove(internalId) {
        records = records.filter(r => r.internalId !== internalId);
        save();
    }

    function clear() {
        records = [];
        save();
    }

    function markAllRead() {
        if (unreadCount === 0) return;
        const now = new Date().toISOString();
        records = records.map(r => r.read === false
            ? Object.assign({}, r, { read: true, readAt: now }) : r);
        save();
    }
}

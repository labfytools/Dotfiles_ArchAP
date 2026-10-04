import QtQuick
import Quickshell.Services.Notifications

Item {
    id: service
    property NotificationStore store: NotificationStore {}
    property var active: []
    property var toasts: []
    // CONTRACT: compteur de popups visibles, partagé entre les sorties écran.
    property int visibleDateCenters: 0
    readonly property var records: store.records
    readonly property int unreadCount: store.unreadCount
    readonly property int criticalUnreadCount: store.criticalUnreadCount

    // WHY: les objets live restent suivis pour dismiss, expire et action.invoke.
    NotificationServer {
        id: server
        keepOnReload: true
        bodySupported: true
        bodyMarkupSupported: false
        bodyHyperlinksSupported: false
        bodyImagesSupported: false
        actionsSupported: true
        actionIconsSupported: false
        imageSupported: true
        inlineReplySupported: false
        persistenceSupported: true
        onNotification: notification => service.receive(notification)
    }

    Component {
        id: watcher
        Connections {
            required property var watched
            required property int internalId
            target: watched
            function onClosed(reason) { service.closed(watched, internalId); }
            function onSummaryChanged() { service.update(watched, internalId); }
            function onBodyChanged() { service.update(watched, internalId); }
            function onAppNameChanged() { service.update(watched, internalId); }
            function onAppIconChanged() { service.update(watched, internalId); }
            function onImageChanged() { service.update(watched, internalId); }
            function onUrgencyChanged() { service.update(watched, internalId); }
            function onActionsChanged() { service.pulse(); }
        }
    }

    function pulse() {
        active = active.slice();
        toasts = toasts.slice();
    }

    function snapshot(n, internalId, old) {
        return {
            internalId: internalId,
            receivedAt: old ? old.receivedAt : new Date().toISOString(),
            closedAt: null,
            sourceNotificationId: n.id,
            appName: n.appName || "",
            appIcon: n.appIcon || "",
            desktopEntry: n.desktopEntry || "",
            summary: n.summary || "",
            body: n.body || "",
            image: n.image || "",
            urgency: n.urgency,
            resident: !!n.resident,
            transient: false,
            // CONTRACT: une mise à jour conserve le statut de consultation du même record.
            read: old ? old.read : false,
            readAt: old ? old.readAt : null
        };
    }

    function receive(n) {
        n.tracked = true;
        // INVARIANT: un replaces_id garde son identité logique et son record.
        const previous = active.find(a => a.notification === n || a.notification.id === n.id);
        const persisted = !n.transient;
        const existing = !previous && n.lastGeneration
            ? records.find(r => r.sourceNotificationId === n.id && !r.closedAt) : null;
        const internalId = previous ? previous.internalId : existing ? existing.internalId : store.nextId++;
        if (previous && previous.watcher) previous.watcher.destroy();
        const entry = { notification: n, internalId: internalId, transient: !persisted };
        entry.watcher = watcher.createObject(service, { watched: n, internalId: internalId });
        active = active.filter(a => a !== previous).concat([entry]);
        if (persisted && store.ready) {
            const old = records.find(r => r.internalId === internalId);
            store.upsert(snapshot(n, internalId, old));
            // INVARIANT: un record reçu pendant une consultation visible est lu
            // avant le prochain rendu, sans délai ni seconde source de vérité.
            if (visibleDateCenters > 0) store.markAllRead();
        }
        if (!n.lastGeneration) toasts = toasts.filter(t => t.internalId !== internalId).concat([entry]);
    }

    function update(n, internalId) {
        if (!active.some(a => a.notification === n && a.internalId === internalId)) return;
        const old = records.find(r => r.internalId === internalId);
        if (old) store.upsert(snapshot(n, internalId, old));
        pulse();
    }

    function closed(n, internalId) {
        const entry = active.find(a => a.notification === n && a.internalId === internalId);
        if (!entry) return;
        active = active.filter(a => a !== entry);
        toasts = toasts.filter(a => a !== entry);
        const record = records.find(r => r.internalId === internalId);
        if (record) store.upsert(Object.assign({}, record, { closedAt: new Date().toISOString() }));
        if (entry.watcher) entry.watcher.destroy();
    }

    function expire(internalId) {
        const entry = active.find(a => a.internalId === internalId);
        if (entry) entry.notification.expire();
    }

    function dismiss(internalId) {
        // Suppression d'abord: le signal closed ne doit pas recréer le record.
        store.remove(internalId);
        const entry = active.find(a => a.internalId === internalId);
        if (entry) entry.notification.dismiss();
        toasts = toasts.filter(a => a.internalId !== internalId);
    }

    function clearAll() {
        store.clear();
        const living = active.slice();
        for (const entry of living) entry.notification.dismiss();
        toasts = [];
    }

    function setDateCenterVisible(isVisible) {
        // Une consultation ne dépend ni du toast ni de l'expiration D-Bus.
        visibleDateCenters = Math.max(0, visibleDateCenters + (isVisible ? 1 : -1));
        if (isVisible) store.markAllRead();
    }

    function live(internalId) {
        const entry = active.find(a => a.internalId === internalId);
        return entry ? entry.notification : null;
    }
}

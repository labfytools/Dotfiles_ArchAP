// CONTRACT: only public application identity and counts cross into the lock
// process. The private record never enters the serialized result.
function project(records) {
    const groups = {};
    let total = 0;
    for (const record of records.slice(0, 200)) {
        if (!record || record.read !== false) continue;
        total++;
        const name = typeof record.appName === "string"
            && /^[^\r\n\t]{1,48}$/.test(record.appName) ? record.appName : "Application";
        const icon = typeof record.appIcon === "string"
            && /^[A-Za-z0-9_.-]{1,64}$/.test(record.appIcon) ? record.appIcon : "";
        const key = name + "\n" + icon;
        if (!groups[key]) groups[key] = { name: name, icon: icon, count: 0 };
        groups[key].count++;
    }
    return { version: 1, generatedAt: Date.now(), total: total,
        apps: Object.values(groups).slice(0, 4) };
}

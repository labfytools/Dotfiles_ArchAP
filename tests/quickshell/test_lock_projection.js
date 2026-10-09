const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('quickshell/.config/quickshell/labfy-sway/notifications/LockProjection.js', 'utf8');
const context = vm.createContext({});
vm.runInContext(source, context);
const result = JSON.parse(JSON.stringify(context.project([
    { read: false, appName: 'Messagerie', appIcon: 'mail-client',
      summary: 'Code 123456', body: 'Contact privé', image: '/private.png' },
    { read: false, appName: 'Messagerie', appIcon: 'mail-client', summary: 'Autre secret' },
    { read: true, appName: 'Navigateur', summary: 'Ne pas montrer' },
    { read: false, appName: 'Nom\nSecret', appIcon: 'file:///private' }
])))
assert.equal(result.total, 3);
assert.deepEqual(result.apps, [
    { name: 'Messagerie', icon: 'mail-client', count: 2 },
    { name: 'Application', icon: '', count: 1 }
]);
const serialized = JSON.stringify(result);
for (const forbidden of ['123456', 'Contact privé', '/private.png', 'Autre secret', 'Nom\nSecret'])
    assert(!serialized.includes(forbidden), forbidden);

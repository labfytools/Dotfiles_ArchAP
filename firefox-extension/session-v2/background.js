/* Identité locale, aucune donnée de navigation. Pas de canal de commande du
 * laboratoire. Le host n'accepte que map-window et ne peut piloter Firefox.
 * L'UUID appartient à la fenêtre logique, pas à son adresse runtime windowId.
 */
"use strict";
const KEY = "labfy.session.window_uuid";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let port = null;
let pending = null;
let busy = false;

function connect() {
  if (port) return port;
  const current = browser.runtime.connectNative("org.labfy.session_v2_identity");
  port = current;
  current.onMessage.addListener(answer => {
    if (port !== current) return;
    if (answer.event === "capture") { cycle(); return; }
    if (!pending) return;
    const p = pending;
    pending = null;
    p.resolve(answer);
  });
  current.onDisconnect.addListener(() => {
    if (port !== current) return;
    port = null;
    if (pending) { pending.reject(new Error("PROVIDER_UNAVAILABLE")); pending = null; }
  });
  return port;
}
async function request(message) {
  const p = connect();
  return await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      if (pending) { pending = null; p.disconnect(); port = null; reject(new Error("PROVIDER_TIMEOUT")); }
    }, 5000);
    pending = {resolve: v => { clearTimeout(timer); resolve(v); }, reject: e => { clearTimeout(timer); reject(e); }};
    try { p.postMessage(message); }
    catch (e) { clearTimeout(timer); pending = null; reject(e); }
  });
}
async function ids() {
  const windows = await browser.windows.getAll({populate: false, windowTypes: ["normal"]});
  if (windows.length > 256) throw new Error("WINDOW_LIMIT");
  return windows.map(w => w.id);
}
async function cycle() {
  if (busy) return;
  busy = true;
  try {
    const rows = [];
    for (const id of await ids()) {
      let value = await browser.sessions.getWindowValue(id, KEY);
      if (value === undefined) {
        // Relecture avant attribution ; une ancienne UUID absente du snapshot
        // restera un échec exact, jamais une correspondance par ordre.
        await sleep(200);
        value = await browser.sessions.getWindowValue(id, KEY);
        if (value === undefined) {
          value = crypto.randomUUID();
          await browser.sessions.setWindowValue(id, KEY, value);
        }
      }
      if (!UUID.test(value)) throw new Error("INVALID_UUID");
      rows.push({id, uuid: value});
    }
    // Les doublons sont également refusés par le provider. Les publier permet
    // un diagnostic de collision au lieu d'un silence ambigu.
    for (const row of rows) {
      const runtime_token = crypto.randomUUID().replaceAll("-", "");
      try {
        await browser.windows.update(row.id, {titlePreface: `[LABFY:${runtime_token}] `});
        const answer = await request({op: "map-window", uuid: row.uuid, runtime_token});
        if (answer.result !== "OK" || answer.uuid !== row.uuid || !Number.isSafeInteger(answer.con_id)) throw new Error("PROVIDER_ERROR");
      } finally {
        await browser.windows.update(row.id, {titlePreface: ""});
      }
    }
  } catch (_) {
    // Aucune chaîne d'erreur externe ou donnée de page dans un log.
  } finally { busy = false; }
}
async function start() {
  for (const id of await ids()) {
    try { await browser.windows.update(id, {titlePreface: ""}); } catch (_) {}
  }
  connect();
  // Reconnexion seulement : pas de titlePreface ni requête Sway en idle.
  setInterval(() => { if (!port) connect(); }, 1000);
}
start().catch(() => {});

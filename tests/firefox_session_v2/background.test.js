"use strict";
const {test, afterEach} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(process.env.BACKGROUND_SOURCE || path.join(__dirname, "../../firefox-extension/session-v2/background.js"), "utf8");
const A = "11111111-1111-4111-8111-111111111111";
const B = "22222222-2222-4222-8222-222222222222";
const KEY = "labfy.session.window_uuid";
const fixtures = [];
afterEach(() => {
  // Assertions thrown inside extension callbacks may be deliberately caught.
  // Record forbidden reads as well, so those catches cannot hide a privacy regression.
  for (const f of fixtures.splice(0)) assert.deepEqual(f.forbiddenReads, []);
});
const plain = value => JSON.parse(JSON.stringify(value));
const flush = async () => { for (let i = 0; i < 240; ++i) await Promise.resolve(); };
function event() {
  const listeners = [];
  return {addListener: fn => listeners.push(fn), emit: (...args) => listeners.map(fn => fn(...args))};
}
async function fixture(options = {}) {
  let now = 0, sequence = 0, random = 0;
  const timers = new Map(), values = options.values || new Map();
  const state = {ids: options.ids || [1], values, forbiddenReads: [], writes: [], maps: [], updates: [], ports: [], reads: [], mode: "ok", creates: 0, read: options.read, write: options.write, enumerate: options.enumerate};
  state.bootstrap = options.bootstrap; state.bootstraps = [];
  state.classifications = []; state.kinds = options.kinds || new Map();
  state.conIds = options.conIds || new Map();
  fixtures.push(state);
  const schedule = (fn, ms, interval = 0) => { const id = ++sequence; timers.set(id, {at: now + ms, fn, interval}); return id; };
  // Poisoned properties make any navigation/content inspection fail the test.
  function window(id) {
    const w = {id, type: "normal"};
    for (const name of ["title", "url", "tabs", "width", "height"]) Object.defineProperty(w, name, {get() { state.forbiddenReads.push(name); assert.fail(`Forbidden window property: ${name}`); }});
    return w;
  }
  let nextWindow = Math.max(0, ...state.ids);
  const onMessage = event();
  const runtime = {
    id: "session-v2@labfy.org", onMessage, onInstalled: event(),
    getURL: name => `moz-extension://synthetic/${name}`,
    connectNative(name) {
      assert.equal(name, "org.labfy.session_v2_identity");
      const p = {onMessage: event(), onDisconnect: event(), disconnected: false,
        disconnect() { p.disconnected = true; p.onDisconnect.emit(); },
        postMessage(message) {
          assert.equal(p.disconnected, false);
          const m = plain(message);
          if (m.op === "classify-window") {
            assert.deepEqual(Object.keys(m).sort(), ["op", "runtime_token"]);
            const marked = state.updates.findLast(u => u.titlePreface === `[LABFY:${m.runtime_token}] `);
            assert.ok(marked, "classification must correlate its own prefix");
            state.classifications.push({id: marked.id, ...m});
            if (state.classifyHook) return state.classifyHook(p, m, marked.id);
            const kind = state.kinds.get(marked.id) || "browser";
            if (!["browser", "managed-webapp"].includes(kind)) p.onMessage.emit({result: "WINDOW_CLASS_UNSUPPORTED"});
            else p.onMessage.emit({result: "OK", kind, runtime_token: m.runtime_token,
              con_id: state.conIds.get(marked.id) ?? 1000 + marked.id});
            return;
          }
          if (m.op === "bootstrap-eligibility") {
            assert.deepEqual(m, {op: "bootstrap-eligibility"});
            state.bootstraps.push({port: state.ports.indexOf(p)});
            if (state.bootstrapHook) return state.bootstrapHook(p);
            if (state.bootstrap === "throw") throw new Error("bootstrap post failure");
            if (state.bootstrap === "disconnect") { p.disconnect(); return; }
            if (state.bootstrap !== "hold") p.onMessage.emit(state.bootstrap === "invalid" ? {result: "OK", baseline_enrollment_allowed: "true"} :
              {result: "OK", baseline_enrollment_allowed: state.bootstrap === true});
            return;
          }
          assert.deepEqual(Object.keys(m).sort(), ["op", "runtime_token", "uuid"]);
          state.maps.push({port: state.ports.indexOf(p), ...m});
          if (state.mode === "throw") throw new Error("synthetic post failure");
          if (state.mode === "disconnect") { p.disconnect(); return; }
          if (state.mode === "ok") {
            const marked = state.updates.findLast(u => u.titlePreface === `[LABFY:${m.runtime_token}] `);
            assert.ok(marked, "mapping must correlate its own prefix");
            if ((state.kinds.get(marked.id) || "browser") !== "browser") p.onMessage.emit({result: "CORRELATION_TIMEOUT"});
            else p.onMessage.emit({result: "OK", uuid: m.uuid, con_id: state.conIds.get(marked.id) ?? 1000 + marked.id});
          }
        }};
      state.ports.push(p);
      return p;
    },
  };
  const browser = {runtime, windows: {
    onCreated: event(), onRemoved: event(),
    create: async query => {
      assert.deepEqual(plain(query), {type: "normal"}); ++state.creates;
      const id = ++nextWindow;
      state.ids.push(id);
      return window(id);
    },
    getAll: async query => { if (state.enumerate) state.enumerate(state); assert.deepEqual(plain(query), {populate: false, windowTypes: ["normal"]}); return state.ids.map(window); },
    update: async (id, change) => { assert.deepEqual(Object.keys(change), ["titlePreface"]); state.updates.push({id, ...plain(change)}); if (state.update) return state.update(id, change); },
  }, sessions: {
    onChanged: event(),
    getWindowValue: async (id, key) => {
      assert.equal(key, KEY); state.reads.push({id, at: now});
      return state.read ? state.read(id, now) : values.get(id);
    },
    setWindowValue: async (id, key, value) => {
      assert.equal(key, KEY); state.writes.push({id, value, at: now});
      if (state.write) return state.write(id, value);
      values.set(id, value);
    },
    getTabValue: () => { state.forbiddenReads.push("getTabValue"); assert.fail("Tab fallback forbidden"); },
    setTabValue: () => { state.forbiddenReads.push("setTabValue"); assert.fail("Tab witness writes forbidden"); },
  }, tabs: new Proxy({}, {get() { state.forbiddenReads.push("tabs API"); assert.fail("Tab content API forbidden"); }})};
  vm.runInNewContext(source, {browser, performance: {now: () => now}, crypto: {randomUUID: () => options.random ? options.random(++random) : `99999999-9999-4999-8999-${String(++random).padStart(12, "0")}`},
    setTimeout: (fn, ms) => schedule(fn, ms), clearTimeout: id => timers.delete(id), setInterval: (fn, ms) => schedule(fn, ms, ms)});
  state.tick = async ms => {
    const end = now + ms;
    await flush();
    while (true) {
      const next = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!next) break;
      const [id, t] = next; now = t.at; timers.delete(id);
      if (t.interval) timers.set(id, {...t, at: now + t.interval});
      t.fn(); await flush();
    }
    now = end; await flush();
  };
  state.open = (id = ++nextWindow, extra = {}) => {
    if (!state.ids.includes(id)) state.ids.push(id);
    const w = window(id);
    Object.assign(w, extra);
    browser.windows.onCreated.emit(w);
    return id;
  };
  state.close = id => { state.ids = state.ids.filter(value => value !== id); browser.windows.onRemoved.emit(id); };
  state.changed = () => browser.sessions.onChanged.emit();
  state.install = (reason = "install") => runtime.onInstalled.emit({reason});
  state.status = async () => plain(await onMessage.emit({op: "identity-status"}, {id: runtime.id})[0]);
  state.rawMessage = (message, sender) => onMessage.emit(message, sender)[0];
  state.capture = async () => {
    const results = state.ports.at(-1).onMessage.emit({event: "capture"});
    await flush();
    state.captureResult = results[0];
  };
  if (options.install) state.install();
  await flush();
  return state;
}


const ready = async f => { await f.tick(33000); assert.equal((await f.status()).phase, "READY"); };
const capture = async f => { await f.capture(); await f.tick(2000); return plain(await f.captureResult); };
// Assertion ancienne remplacée : install seul n'est pas une preuve d'absence de checkpoint.
test("installation sans autorité backend : baseline bloquée même si install arrive après start", async () => {
  const f = await fixture({ids: [1, 2]});
  await f.tick(10000); f.install(); await ready(f);
  assert.equal(f.writes.length, 0);
  assert.equal((await capture(f)).result, "REFUSED");
  assert.equal(f.creates, 0);
});
test("Ctrl+N après prêt et longtemps après settle : automatique unique et capturable", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(); await f.tick(999); assert.equal(f.writes.length, 0);
  await f.tick(3001); assert.equal(f.writes.length, 1);
  await f.tick(120000); f.open(); await f.tick(4000);
  assert.equal(f.writes.length, 2); assert.equal(new Set(f.writes.map(w => w.value)).size, 2);
  assert.equal((await capture(f)).result, "OK"); assert.equal(f.maps.length, 3);
});
test("startup restore undefined au-delà du boot : aucune écriture puis valeur tardive préservée", async () => {
  const f = await fixture(); await f.tick(70000);
  assert.equal((await f.status()).phase, "READY");
  assert.equal((await f.status()).result, "REFUSED");
  f.values.set(1, A); assert.equal((await capture(f)).result, "OK");
  f.open(); await f.tick(10000); assert.equal(f.writes.length, 1);
});
test("onCreated durant startup : UUID reçu avant stabilisation préservé", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await f.tick(10000); f.open(2);
  await f.tick(15000); assert.equal(f.writes.length, 0);
  f.values.set(2, B); await f.tick(12000); assert.equal((await f.status()).phase, "READY");
  f.open(3); await f.tick(4000); assert.deepEqual(f.writes.map(w => w.id), [3]);
});
test("installation baseline bloquée ; valeur du candidat boot reçue avant stabilisation préservée", async () => {
  const f = await fixture({install: true}); f.open(2); await f.tick(25000);
  assert.equal(f.writes.length, 0); f.values.set(2, B); await f.tick(14000);
  assert.deepEqual(f.writes.map(w => w.id), []); assert.equal(f.values.get(2), B);
});
test("deux fenêtres mêmes contenus, créations simultanées : deux identités distinctes", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); f.open(3); await f.tick(4000);
  assert.deepEqual(f.writes.map(w => w.id), [2, 3]);
  assert.equal(new Set(f.writes.map(w => w.value)).size, 2);
});
test("signal onChanged : UUID restauré reçu pendant guard préservé", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.changed(); f.open(2); await f.tick(4000);
  assert.equal(f.writes.length, 0); f.values.set(2, B); await f.tick(6000);
  assert.equal((await capture(f)).result, "OK"); assert.equal(f.values.get(2), B);
});
test("onChanged pendant observation : passage révoqué puis candidat réobservé", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); await f.tick(1500); f.changed(); await f.tick(15000);
  assert.equal(f.writes.length, 1); assert.equal((await capture(f)).result, "OK");
});
test("sessionId positif protège ; absence de sessionId ne prouve rien", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2, {sessionId: "closed-session"}); await f.tick(10000); assert.equal(f.writes.length, 0);
});
test("restauration tardive non signalée avec UUID pendant observation conservé", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); await f.tick(1500); f.values.set(2, B); await f.tick(5000);
  assert.equal(f.writes.length, 0); assert.equal((await capture(f)).result, "OK");
});
test("limite irréductible : restauration sans signal ni extData ressemble à Ctrl+N", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); await f.tick(4000);
  // Ce test expose le compromis, pas une preuve de classification parfaite.
  assert.equal(f.writes.length, 1);
  f.values.set(2, B); assert.equal((await capture(f)).result, "REFUSED");
  assert.equal(f.writes.length, 1); assert.equal(f.values.get(2), B);
});
test("API rejection sur candidat : refus sans retry, capture peut lire valeur tardive", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.read = id => { if (id === 2) throw new Error("synthetic rejection"); return A; };
  f.open(2); await f.tick(5000); assert.equal(f.writes.length, 0);
  f.read = id => id === 1 ? A : undefined; await f.tick(5000); assert.equal(f.writes.length, 0);
  f.values.set(2, B); f.read = null; assert.equal((await capture(f)).result, "OK");
});
test("provider reconnect, captures concurrentes et ancien port ne changent aucune identité", async () => {
  const f = await fixture({values: new Map([[1, A]])}); f.mode = "hold";
  await f.capture(); await f.capture(); assert.equal(f.maps.length, 1);
  const old = f.ports[0]; old.disconnect(); await flush();
  f.mode = "ok"; await f.tick(1000); assert.equal((await capture(f)).result, "OK");
  old.onMessage.emit({result: "OK", uuid: B, con_id: 999});
  assert.equal(f.writes.length, 0); assert.equal(f.updates.at(-1).titlePreface, "");
});
test("timeout natif et post failure restent récupérables sans vieux timer destructeur", async () => {
  const f = await fixture({values: new Map([[1, A]])}); f.mode = "hold";
  await f.capture(); await f.tick(5000); assert.equal(f.ports[0].disconnected, true);
  await f.tick(1000); f.mode = "throw"; await f.capture(); await flush();
  await f.tick(1000); f.mode = "ok"; assert.equal((await capture(f)).result, "OK");
  assert.equal(f.ports.at(-1).disconnected, false);
});
test("collision persistée refuse lot entier et collision générée refuse le mint", async () => {
  const f = await fixture({ids: [1, 2], values: new Map([[1, A], [2, A]])});
  assert.equal((await capture(f)).result, "REFUSED"); assert.equal(f.maps.length, 0);
  const g = await fixture({values: new Map([[1, A]]), random: () => A}); await ready(g);
  g.open(2); await g.tick(4000); assert.equal(g.writes.length, 0);
});
test("tab move, ordre et fenêtre restante ne récupèrent aucune identité", async () => {
  const f = await fixture({ids: [9, 2], values: new Map([[9, A], [2, B]])});
  assert.equal((await capture(f)).result, "OK"); f.ids.reverse();
  assert.equal((await capture(f)).result, "OK");
  assert.deepEqual(f.maps.map(m => m.uuid), [B, A, B, A]);
  f.values.delete(2); f.close(9); assert.equal((await capture(f)).result, "REFUSED");
  await f.tick(35000); assert.equal(f.writes.length, 0);
});
test("update/restart : jamais enrôler baseline absente, mêmes valeurs autoritaires", async () => {
  for (const reason of ["update", "browser_update", undefined]) {
    const f = await fixture(); if (reason) f.install(reason);
    await f.tick(70000); assert.equal(f.writes.length, 0);
  }
  const f = await fixture({values: new Map([[1, A]])}); await ready(f); f.open(2); await f.tick(4000);
  const g = await fixture({ids: [8], values: new Map([[8, f.values.get(2)]])});
  assert.equal((await capture(g)).result, "OK"); assert.equal(g.writes.length, 0);
});
test("window close avant mint : seul le candidat remplaçant est réobservé", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); await f.tick(1000); f.close(2); f.open(3); await f.tick(10000);
  assert.deepEqual(f.writes.map(w => w.id), [3]);
});
test("écriture appliquée mais rejetée : pas de retry ni capture concurrente partielle", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.write = (id, value) => { f.values.set(id, value); throw new Error("uncertain"); };
  f.open(2); await f.tick(1000); await f.capture(); assert.equal((await f.captureResult).result, "BUSY");
  await f.tick(8000); assert.equal(f.writes.length, 1);
  assert.equal((await capture(f)).result, "OK"); assert.equal(f.writes.length, 1);
});
test("API suspendue : arrêt définitif, pas d'accumulation d'appels", async () => {
  const f = await fixture({read: () => new Promise(() => {})});
  await f.capture(); await f.tick(40000); const count = f.reads.length;
  await f.capture(); await f.tick(10000);
  assert.equal(f.reads.length, count); assert.equal(f.writes.length, 0);
  assert.equal((await f.status()).result, "REFUSED");
});
test("valeurs invalides et limites locales refusent sans fausse réussite", async () => {
  for (const invalid of [null, "", "wrong", 42, {uuid: A}]) {
    const f = await fixture({values: new Map([[1, invalid]]), install: true});
    await f.tick(35000); assert.equal((await capture(f)).result, "REFUSED"); assert.equal(f.writes.length, 0);
  }
  const f = await fixture({ids: Array.from({length: 257}, (_, i) => i)});
  assert.equal((await capture(f)).result, "REFUSED"); assert.equal(f.reads.length, 0);
});
test("capture seule reste non-mutante, absence tardive récupérée hors délai", async () => {
  const f = await fixture({read: (_, now) => now >= 7000 ? A : undefined});
  assert.equal((await capture(f)).result, "REFUSED"); await f.tick(6000);
  assert.equal((await capture(f)).result, "OK"); assert.equal(f.writes.length, 0);
});
test("une lecture rejetée ne libère pas l'opération tant que sa sœur est pendante", async () => {
  const f = await fixture({ids: [1, 2], read: id => {
    if (id === 1) throw new Error("reject"); return new Promise(() => {});
  }});
  await f.capture(); const count = f.reads.length;
  await f.capture(); assert.equal(f.reads.length, count);
  await f.tick(10000); assert.equal(f.reads.length, count); assert.equal(f.writes.length, 0);
});
test("valeur tardive à la dernière relecture avant mint est préservée", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  let finalReads = 0;
  f.read = (id, now) => id === 1 ? A : now >= 36000 && ++finalReads >= 2 ? B : undefined;
  f.open(2); await f.tick(5000);
  assert.equal(f.writes.length, 0); assert.equal((await capture(f)).result, "OK");
});
test("immuabilité entre opérations : changement UUID refuse publication entière", async () => {
  const f = await fixture({values: new Map([[1, A]])}); assert.equal((await capture(f)).result, "OK");
  f.values.set(1, B); const before = f.maps.length;
  assert.equal((await capture(f)).result, "REFUSED"); assert.equal(f.maps.length, before);
  await f.tick(35000); assert.equal(f.writes.length, 0);
});
test("API suspendue pendant écriture : aucun retry, aucune capture d'identité partielle", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  let release;
  f.write = () => new Promise(resolve => { release = resolve; });
  f.open(2); await f.tick(6000); assert.equal(f.writes.length, 1);
  assert.equal((await capture(f)).result, "REFUSED");
  f.values.set(2, f.writes[0].value); release(); await f.tick(10000);
  assert.equal(f.writes.length, 1); assert.equal((await capture(f)).result, "REFUSED");
});
test("restart pendant observation perd toute autorisation de mint", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f); f.open(2); await f.tick(1000);
  const g = await fixture({ids: [...f.ids], values: f.values}); await g.tick(70000);
  assert.equal(g.writes.length, 0); assert.equal((await capture(g)).result, "REFUSED");
});
test("rejeter une lecture baseline au premier install la protège définitivement", async () => {
  const f = await fixture({install: true, read: () => { throw new Error("read rejected"); }});
  await f.tick(2000); f.read = null; await f.tick(40000);
  assert.equal(f.writes.length, 0); assert.equal((await capture(f)).result, "REFUSED");
});
test("fenêtre sessionId ambiguë bloque capture mais pas mint du Ctrl+N suivant", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.changed(); f.open(2, {sessionId: "restored"}); await f.tick(6000); f.open(3); await f.tick(10000);
  assert.deepEqual(f.writes.map(w => w.id), [3]); assert.equal((await f.status()).result, "REFUSED");
});
test("capture native avant fin d'installation n'attribue aucune identité", async () => {
  const f = await fixture({install: true});
  assert.equal((await capture(f)).result, "REFUSED"); assert.equal(f.writes.length, 0);
  await f.tick(31000); assert.equal(f.writes.length, 0);
});
test("message historique create-window supprimé : aucune création et aucune attribution", async () => {
  const f = await fixture();
  assert.equal(f.rawMessage({op: "create-window"}, {id: "session-v2@labfy.org"}), undefined);
  assert.equal(f.creates, 0); assert.equal(f.writes.length, 0);
});
test("vérification divergente après écriture refuse aussi les publications suivantes", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.write = id => { f.values.set(id, B); };
  f.open(2); await f.tick(5000); assert.equal(f.writes.length, 1);
  assert.equal((await capture(f)).result, "REFUSED");
  assert.equal(f.maps.length, 0); assert.equal(f.values.get(2), B);
  await f.tick(5000); assert.equal(f.writes.length, 1);
});
test("listener synchrone : onCreated pendant le premier getAll reste en quarantaine", async () => {
  const f = await fixture({install: true, enumerate: state => {
    state.enumerate = null; state.open(2);
  }});
  await f.tick(35000); assert.equal(f.writes.length, 0);
  f.values.set(2, B); await f.tick(5000);
  assert.deepEqual(f.writes.map(w => w.id), []); assert.equal(f.values.get(2), B);
});
test("une preuve lue dans un lot partiellement rejeté ne peut devenir un mint", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2);
  f.read = id => { if (id === 1) throw new Error("sibling rejection"); return B; };
  await f.capture(); assert.equal((await f.captureResult).result, "REFUSED");
  f.read = null; await f.tick(10000); assert.equal(f.writes.length, 0);
});
test("une valeur invalide observée puis disparue ne permet jamais de mint", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); f.values.set(2, "corrupt");
  await f.capture(); assert.equal((await f.captureResult).result, "REFUSED");
  f.values.delete(2); await f.tick(10000); assert.equal(f.writes.length, 0);
});
test("rejets non Error : refus explicite, sans exception dans le gestionnaire d'erreur", async () => {
  for (const rejected of [null, "read failed"]) {
    const f = await fixture({values: new Map([[1, A]])}); await ready(f);
    f.read = () => Promise.reject(rejected); f.open(2); await f.tick(2000);
    const status = await f.status(); assert.equal(status.result, "REFUSED"); assert.equal(status.reason, "API_REJECTED");
    assert.equal((await capture(f)).result, "REFUSED"); assert.equal(f.writes.length, 0);
  }
});

// Audit corrective : attentes produit, exécutables aussi contre la source pré-patch.
test("audit BOOT : Ctrl+N à 10 secondes puis première capture automatique", async () => {
  const f = await fixture({values: new Map([[1, A]])});
  await f.tick(10000); f.open(2); await f.tick(25000);
  assert.deepEqual(f.writes.map(w => w.id), [2]);
  assert.equal((await capture(f)).result, "OK");
});
test("audit historique absent : ne bloque pas les futurs Ctrl+N même après 60s", async () => {
  const f = await fixture(); f.install("update"); await f.tick(70000);
  assert.equal((await f.status()).result, "REFUSED");
  f.open(2); await f.tick(6000); assert.deepEqual(f.writes.map(w => w.id), [2]);
  assert.equal((await capture(f)).result, "REFUSED");
  f.close(1); f.open(3); await f.tick(6000);
  assert.deepEqual(f.writes.map(w => w.id), [2, 3]);
  assert.equal((await capture(f)).result, "OK");
});
test("audit fermeture onglet : observation retentée puis Ctrl+N suivant", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); await f.tick(1500); f.changed(); await f.tick(12000);
  assert.deepEqual(f.writes.map(w => w.id), [2]);
  f.open(3); await f.tick(6000); assert.deepEqual(f.writes.map(w => w.id), [2, 3]);
});
test("audit deux Ctrl+N espacés de 1s : mêmes candidats retentés", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2); await f.tick(1000); f.open(3); await f.tick(8000);
  assert.deepEqual(f.writes.map(w => w.id), [2, 3]);
  assert.equal((await capture(f)).result, "OK");
});
test("audit type facultatif : getAll normal confirme le candidat", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2, {type: undefined}); await f.tick(6000);
  assert.deepEqual(f.writes.map(w => w.id), [2]);
});
test("audit réinstallation avec checkpoint passé : install seul ne permet aucun mint baseline", async () => {
  // Le checkpoint externe est invisible à cette VM comme au background ;
  // aucune autorité backend d'absence n'a été reçue.
  const f = await fixture({install: true}); await f.tick(70000);
  assert.equal(f.writes.length, 0);
  assert.equal((await f.status()).result, "REFUSED");
});

test("timeout titlePreface : nettoyage unique après règlement tardif sans relancer le marquage", async () => {
  const f = await fixture({values: new Map([[1, A]])});
  let release;
  f.update = (_, change) => change.titlePreface ? new Promise(resolve => { release = resolve; }) : undefined;
  await f.capture(); await f.tick(3000);
  assert.equal((await f.captureResult).result, "REFUSED");
  assert.equal(f.updates.filter(u => u.titlePreface).length, 1);
  const before = f.updates.length;
  release(); await f.tick(10000);
  assert.equal(f.updates.length, before + 1);
  assert.equal(f.updates.at(-1).titlePreface, "");
  assert.equal((await f.status()).result, "REFUSED");
  assert.equal((await f.status()).prefixCleanupPending, false);
  await f.tick(10000); assert.equal(f.updates.length, before + 1);
});
test("popup explicite et type absent hors getAll normal : aucun mint", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.open(2, {type: "popup"}); f.ids = [1];
  f.open(3, {type: undefined}); f.ids = [1];
  await f.tick(10000); assert.equal(f.writes.length, 0);
});
test("update : UUID baseline reçu tardivement est lu sans réécriture", async () => {
  const f = await fixture(); f.install("update"); await f.tick(70000);
  f.open(2); await f.tick(6000); assert.deepEqual(f.writes.map(w => w.id), [2]);
  f.values.set(1, A); await f.tick(3000);
  assert.equal((await capture(f)).result, "OK");
  assert.deepEqual(f.writes.map(w => w.id), [2]);
  assert.equal((await f.status()).result, "READY");
});

test("activité après écriture : ne retente pas l'écriture, conserve les autres candidats", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.write = (id, value) => {
    f.values.set(id, value);
    if (id === 2) f.open(3);
  };
  f.open(2); await f.tick(10000);
  assert.deepEqual(f.writes.map(w => w.id), [2, 3]);
  assert.equal((await capture(f)).result, "OK");
});

// P0 : doit échouer contre le background pré-protocole conservé en preuve.
test("P0 premier install avec absence attestée : deux UUID stables sans clic", async () => {
  for (const early of [true, false]) {
    const f = await fixture({ids: [1, 2], bootstrap: true, install: early});
    if (!early) { await f.tick(35000); f.install(); }
    await f.tick(45000);
    assert.deepEqual(f.writes.map(w => w.id), [1, 2]);
    assert.equal(new Set(f.writes.map(w => w.value)).size, 2);
    assert.equal(f.bootstraps.length, 2); // Recheck avant chacune des écritures.
    await f.tick(60000); assert.equal(f.writes.length, 2);
    assert.equal((await capture(f)).result, "OK");
  }
});

test("bootstrap refus/timeout/erreur : baseline isolée, Ctrl+N BOOT et futur automatiques", async () => {
  for (const bootstrap of [false, "hold", "throw", "disconnect", "invalid"]) {
    const f = await fixture({install: true, bootstrap});
    await f.tick(10000); f.open(2);
    await f.tick(40000);
    assert.deepEqual(f.writes.map(w => w.id), [2], String(bootstrap));
    assert.equal(f.bootstraps.length, 1);
    f.bootstrap = true; await f.tick(20000); // La reconnexion n'est pas une nouvelle autorité.
    f.open(3); await f.tick(6000);
    assert.deepEqual(f.writes.map(w => w.id), [2, 3]);
    assert.equal(f.bootstraps.length, 1);
    assert.equal(f.values.has(1), false);
  }
});

test("bootstrap : checkpoint créé entre deux écritures refuse la seconde", async () => {
  const f = await fixture({ids: [1, 2], install: true, bootstrap: true});
  f.write = (id, value) => { f.values.set(id, value); f.bootstrap = false; };
  await f.tick(45000);
  assert.deepEqual(f.writes.map(w => w.id), [1]);
  assert.equal(f.bootstraps.length, 2);
  assert.equal(f.values.has(2), false);
  await f.tick(60000); assert.equal(f.bootstraps.length, 2);
});

test("bootstrap en vol : capture coalescée, pas de mélange avec map-window", async () => {
  const f = await fixture({install: true, bootstrap: "hold"});
  await f.tick(33000);
  assert.equal(f.bootstraps.length, 1);
  await f.capture(); assert.equal((await f.captureResult).result, "BUSY");
  assert.equal(f.maps.length, 0);
  f.ports.at(-1).onMessage.emit({result: "OK", baseline_enrollment_allowed: true});
  await f.tick(1000);
  assert.equal(f.writes.length, 1);
  assert.equal((await capture(f)).result, "OK");
  assert.equal(f.maps.length, 1);
});

test("capture en vol retarde bootstrap ; onInstalled ne poste rien en concurrence", async () => {
  const f = await fixture({values: new Map([[1, A]]), bootstrap: true});
  f.mode = "hold"; await f.capture();
  f.install(); await f.tick(3000);
  assert.equal(f.bootstraps.length, 0);
  assert.equal(f.maps.length, 1);
  f.ports.at(-1).onMessage.emit({result: "OK", uuid: A, con_id: 1001});
  f.mode = "ok"; await f.tick(40000);
  assert.equal(f.writes.length, 0); assert.equal(f.bootstraps.length, 0);
});

test("bootstrap réponse positive après onChanged : lot révoqué sans retry baseline", async () => {
  const f = await fixture({install: true, bootstrap: "hold"});
  await f.tick(33000); assert.equal(f.bootstraps.length, 1);
  f.changed(); f.ports.at(-1).onMessage.emit({result: "OK", baseline_enrollment_allowed: true});
  await f.tick(30000); assert.equal(f.writes.length, 0);
  assert.equal(f.bootstraps.length, 1);
  f.open(2); await f.tick(6000); assert.deepEqual(f.writes.map(w => w.id), [2]);
});

test("bootstrap : UUID arrivé pendant attestation préservé, aucun overwrite", async () => {
  const f = await fixture({install: true, bootstrap: "hold"});
  await f.tick(33000);
  f.values.set(1, A);
  f.ports.at(-1).onMessage.emit({result: "OK", baseline_enrollment_allowed: true});
  await f.tick(20000);
  assert.equal(f.writes.length, 0); assert.equal(f.values.get(1), A);
  assert.equal((await capture(f)).result, "OK");
});

test("bootstrap : rollback UUID connu et écriture incertaine jamais retentés", async () => {
  const f = await fixture({install: true, bootstrap: true});
  f.write = (id, value) => { f.values.set(id, value); throw new Error("uncertain baseline"); };
  await f.tick(45000); assert.equal(f.writes.length, 1);
  f.values.delete(1); await f.tick(20000);
  assert.equal(f.writes.length, 1); assert.equal(f.bootstraps.length, 1);
  assert.equal((await capture(f)).result, "REFUSED");
});

test("bootstrap : restart et update restent sans autorité malgré host positif", async () => {
  for (const reason of [undefined, "update", "browser_update"]) {
    const f = await fixture({bootstrap: true}); if (reason) f.install(reason);
    await f.tick(45000); assert.equal(f.writes.length, 0); assert.equal(f.bootstraps.length, 0);
    f.open(2); await f.tick(6000); assert.deepEqual(f.writes.map(w => w.id), [2]);
  }
});

test("bootstrap : événement pré-photographie/sessionId protège même avec host positif", async () => {
  const f = await fixture({install: true, bootstrap: true, enumerate: state => {
    state.enumerate = null; state.open(2);
  }});
  f.open(1, {sessionId: "restored"});
  await f.tick(45000); assert.equal(f.writes.length, 0); assert.equal(f.bootstraps.length, 0);
});

test("bootstrap : timeout déconnecte, réponse ancien port ignorée, map reconnecté", async () => {
  const f = await fixture({install: true, bootstrap: "hold"});
  await f.tick(33000); const old = f.ports.at(-1);
  await f.tick(10000); assert.equal(old.disconnected, true);
  old.onMessage.emit({result: "OK", baseline_enrollment_allowed: true});
  f.values.set(1, A); f.bootstrap = true;
  assert.equal((await capture(f)).result, "OK");
  assert.equal(f.writes.length, 0); assert.equal(f.bootstraps.length, 1);
  assert.notEqual(f.ports.at(-1), old);
});

test("bootstrap : réponses natives non exactes refusées sans écriture baseline", async () => {
  for (const answer of [{result: "REFUSED"}, {result: "OK"},
    {result: "OK", baseline_enrollment_allowed: true, extra: true},
    {result: "OK", baseline_enrollment_allowed: 1}]) {
    const f = await fixture({install: true});
    f.bootstrapHook = p => p.onMessage.emit(answer);
    await f.tick(45000); assert.equal(f.writes.length, 0);
    assert.equal(f.bootstraps.length, 1);
    f.open(2); await f.tick(6000); assert.deepEqual(f.writes.map(w => w.id), [2]);
  }
});


// Régression webapp : son type WebExtension est normal, mais ses extData ne
// sont pas persistées par Firefox. Seul le host peut attester son exclusion.
test("webapp premier ID sans UUID : seule la fenêtre navigateur est publiée", async () => {
  const f = await fixture({ids: [1, 2], kinds: new Map([[1, "managed-webapp"]]), values: new Map([[2, B]])});
  assert.equal((await capture(f)).result, "OK");
  assert.deepEqual(f.maps.map(m => m.uuid), [B]);
  assert.ok(f.classifications.some(c => c.id === 1));
  assert.ok(f.reads.every(r => r.id === 2));
  assert.deepEqual(f.writes, []);
});

test("webapp exclue de tout mint baseline ou Ctrl+N, navigateur nouveau conservé", async () => {
  const f = await fixture({ids: [1, 2], install: true, bootstrap: true,
    kinds: new Map([[1, "managed-webapp"]]), values: new Map([[2, B]])});
  await ready(f); f.kinds.set(3, "managed-webapp"); f.open(3); f.open(4);
  await f.tick(10000);
  assert.deepEqual(f.writes.map(w => w.id), [4]);
  assert.ok(f.reads.every(r => ![1, 3].includes(r.id)));
  assert.equal(f.values.has(1), false); assert.equal(f.values.has(3), false);
  assert.equal((await capture(f)).result, "OK");
});

test("navigateur normal sans UUID reste refusé même avec une webapp exclue", async () => {
  const f = await fixture({ids: [1, 2], kinds: new Map([[1, "managed-webapp"]])});
  const result = await capture(f);
  assert.equal(result.result, "REFUSED"); assert.equal(result.reason, "INVALID_UUID");
  assert.deepEqual(f.maps, []); assert.deepEqual(f.writes, []);
  await f.tick(70000);
  assert.equal((await f.status()).result, "REFUSED"); assert.deepEqual(f.writes, []);
});

test("classe inconnue : refus avant lecture, aucun retry périodique de marquage", async () => {
  const f = await fixture({kinds: new Map([[1, "unknown"]]), values: new Map([[1, A]])});
  await f.tick(2000);
  const count = f.classifications.length;
  await f.tick(70000);
  assert.equal(f.classifications.length, count); assert.equal(count, 1);
  assert.equal((await capture(f)).reason, "WINDOW_CLASS_UNAVAILABLE");
  assert.deepEqual(f.reads, []); assert.deepEqual(f.maps, []); assert.deepEqual(f.writes, []);
});

test("classe ou con_id converti : preuve fraîche refusée durablement jusqu'au close", async () => {
  for (const change of ["kind", "con_id"]) {
    const f = await fixture({values: new Map([[1, A]])});
    assert.equal((await capture(f)).result, "OK");
    const published = f.maps.length;
    if (change === "kind") f.kinds.set(1, "managed-webapp"); else f.conIds.set(1, 9999);
    assert.equal((await capture(f)).reason, "WINDOW_CLASS_CHANGED");
    f.kinds.clear(); f.conIds.clear();
    assert.equal((await capture(f)).reason, "WINDOW_CLASS_CHANGED");
    assert.equal(f.maps.length, published); assert.deepEqual(f.writes, []);
    f.close(1); f.open(1); f.values.set(1, A);
    assert.equal((await capture(f)).result, "OK");
  }
});

test("webapp devenue navigateur : ne jamais conserver une exclusion ancienne", async () => {
  const f = await fixture({ids: [1, 2], kinds: new Map([[1, "managed-webapp"]]), values: new Map([[2, B]])});
  assert.equal((await capture(f)).result, "OK");
  f.kinds.set(1, "browser"); f.values.set(1, A);
  assert.equal((await capture(f)).reason, "WINDOW_CLASS_CHANGED");
  assert.deepEqual(f.maps.map(m => m.uuid), [B]); assert.deepEqual(f.writes, []);
});

test("ensemble changé pendant classification : aucun UUID lu ni publié", async () => {
  const f = await fixture({values: new Map([[1, A]])});
  f.classifyHook = (p, m, id) => {
    f.open(2); f.classifyHook = null;
    p.onMessage.emit({result: "OK", kind: "browser", runtime_token: m.runtime_token, con_id: 1000 + id});
  };
  await f.capture();
  assert.equal((await f.captureResult).reason, "WINDOW_SET_CHANGED");
  // Before the next independent autoStep, this refused capture read no UUID.
  assert.deepEqual(f.reads, []); assert.deepEqual(f.maps, []); assert.deepEqual(f.writes, []);
});

test("cache borné : aucun marquage idle après le premier classement", async () => {
  const f = await fixture({values: new Map([[1, A]])});
  await f.tick(2000); const classified = f.classifications.length, updates = f.updates.length;
  await f.tick(90000);
  assert.equal(classified, 1); assert.equal(f.classifications.length, classified);
  assert.equal(f.updates.length, updates); assert.deepEqual(f.maps, []);
  assert.equal((await capture(f)).result, "OK");
  assert.equal(f.classifications.length, classified + 2);
});

test("réponse classification fermée : jeton, classe, con_id et champs exacts", async () => {
  for (const change of [{runtime_token: "0".repeat(32)}, {kind: "skip"}, {con_id: 0}, {con_id: true}, {extra: true}]) {
    const f = await fixture({values: new Map([[1, A]])});
    f.classifyHook = (p, m) => p.onMessage.emit({result: "OK", kind: "browser", runtime_token: m.runtime_token, con_id: 1001, ...change});
    assert.equal((await capture(f)).reason, "WINDOW_CLASS_UNAVAILABLE");
    assert.deepEqual(f.reads, []); assert.deepEqual(f.maps, []); assert.deepEqual(f.writes, []);
  }
});


test("conversion juste avant mint : aucune écriture sous une classe périmée", async () => {
  const f = await fixture({values: new Map([[1, A]])}); await ready(f);
  f.classifyHook = (p, m, id) => {
    const count = f.classifications.filter(c => c.id === id).length;
    p.onMessage.emit({result: "OK", kind: id === 2 && count > 1 ? "managed-webapp" : "browser",
      runtime_token: m.runtime_token, con_id: 1000 + id});
  };
  f.open(2); await f.tick(6000);
  assert.deepEqual(f.writes, []); assert.equal(f.values.has(2), false);
  assert.equal((await capture(f)).reason, "WINDOW_CLASS_CHANGED");
});

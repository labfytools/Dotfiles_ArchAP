/* WHY : Firefox Release ne fournit pas de barrière sessionstore ni de preuve
 * de nouveauté pour Ctrl+N. L'automatisme ci-dessous est un compromis observé,
 * pas un CAS : une restauration sans signal avec extData très tardives reste
 * indiscernable. Les fenêtres ambiguës observées restent protégées.
 * CONTRACT : baseline uniquement sur install et absence de checkpoint attestée
 * par le host avant chaque écriture. Capture native
 * sans mutation d’identité ni de tab data.
 * INVARIANT : aucune réattribution, aucun contenu/titre/URL lu, une opération
 * active, une seule tentative d'écriture par fenêtre et instance.
 */
"use strict";
const KEY = "labfy.session.window_uuid";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const POLL_MS = 250;
const OBSERVE_MS = 2000;
const STARTUP_MS = 30000;
const API_MS = 2000;
const started = performance.now();
const RESTORE_GUARD_MS = 5000;
let phase = "BOOT";
let baseline = null;
let installed = false;
let bootstrapClosed = false;
const protectedBaseline = new Set();
let changedAt = started;
let restoreUntil = started;
let revision = 0;
let lastError = null;
const candidates = new Set();
const quarantine = new Set();
const attempted = new Set();
const known = new Map();
let halted = false;
let port = null;
let pending = null;
let active = false;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
// Les rejets WebExtension ne sont pas nécessairement des objets Error.
const failureReason = error => error && typeof error.message === "string" ? error.message : "API_REJECTED";

// Un appel API bloqué n'est pas annulable. Après timeout, aucune nouvelle
// opération ordinaire n’est lancée avant redémarrage. Seul un effacement de
// préfixe après règlement du marquage expiré reste autorisé (voir mark).
async function api(call) {
  if (halted) throw new Error("API_RESTART_REQUIRED");
  let timer;
  try {
    return await Promise.race([Promise.resolve().then(call), new Promise((_, reject) => {
      timer = setTimeout(() => { halted = true; reject(new Error("API_TIMEOUT")); }, API_MS);
    })]);
  } finally { clearTimeout(timer); }
}
function connect() {
  if (port) return port;
  const current = browser.runtime.connectNative("org.labfy.session_v2_identity");
  port = current;
  current.onMessage.addListener(answer => {
    if (port !== current || !answer || typeof answer !== "object") return;
    if (answer.event === "capture") return cycle();
    if (pending && pending.port === current) pending.resolve(answer);
  });
  current.onDisconnect.addListener(() => {
    if (port !== current) return;
    port = null;
    if (pending && pending.port === current) pending.reject(new Error("PROVIDER_UNAVAILABLE"));
  });
  return current;
}
async function request(message) {
  if (pending) throw new Error("REQUEST_BUSY");
  const current = connect();
  return await new Promise((resolve, reject) => {
    let timer;
    // Chaque callback ne possède que sa demande et son port : une expiration
    // ancienne ne peut ni rejeter ni déconnecter une nouvelle connexion.
    const finish = (callback, value) => {
      if (pending !== operation) return;
      pending = null;
      clearTimeout(timer);
      callback(value);
    };
    const operation = {port: current, resolve: v => finish(resolve, v), reject: e => finish(reject, e)};
    pending = operation;
    timer = setTimeout(() => {
      if (pending !== operation) return;
      operation.reject(new Error("PROVIDER_TIMEOUT"));
      if (port === current) port = null;
      current.disconnect();
    }, 5000);
    try { current.postMessage(message); }
    catch (e) {
      operation.reject(e);
      if (port === current) port = null;
      current.disconnect();
    }
  });
}
async function ids() {
  const windows = await api(() => browser.windows.getAll({populate: false, windowTypes: ["normal"]}));
  if (windows.length > 256) throw new Error("WINDOW_LIMIT");
  const result = windows.map(w => w.id).sort((a, b) => a - b);
  if (result.some(id => !Number.isSafeInteger(id) || id < 0) || new Set(result).size !== result.length) throw new Error("WINDOW_IDS");
  return result;
}
function validate(rows, complete = true) {
  const seen = new Set();
  for (const {uuid} of rows) {
    if (uuid === undefined && !complete) continue;
    if (typeof uuid !== "string" || !UUID.test(uuid)) throw new Error("INVALID_UUID");
    if (seen.has(uuid)) throw new Error("UUID_COLLISION");
    seen.add(uuid);
  }
}
async function sample(expected) {
  const current = await ids();
  if (current.length !== expected.length || current.some((id, i) => id !== expected[i])) throw new Error("WINDOW_SET_CHANGED");
  // Attendre aussi les lectures sœurs en échec : Promise.all rejetterait trop
  // tôt et autoriserait une nouvelle capture avec des appels encore en vol.
  const reads = await Promise.allSettled(current.map(async id => ({id, uuid: await api(() => browser.sessions.getWindowValue(id, KEY))})));
  const failure = reads.find(read => read.status === "rejected");
  const rows = reads.filter(read => read.status === "fulfilled").map(read => read.value);
  let identityChanged = false;
  for (const row of rows) {
    // Même un lot rejeté contient des preuves : ne pas oublier une valeur
    // reçue parce qu'une lecture sœur rejette ou qu'un autre UUID est invalide.
    // Une valeur invalide observée n'autorise pas non plus un mint ultérieur.
    if (known.has(row.id) && known.get(row.id) !== row.uuid) identityChanged = true;
    if (row.uuid !== undefined && !known.has(row.id)) known.set(row.id, row.uuid);
  }
  if (failure) throw failure.reason;
  validate(rows, false);
  if (identityChanged) throw new Error("IDENTITY_CHANGED");
  return rows;
}
async function observe() {
  const expected = await ids();
  const end = performance.now() + OBSERVE_MS;
  while (true) {
    const rows = await sample(expected);
    // Une identité connue est utilisable immédiatement. L'absence attend toute
    // la période bornée, sans jamais devenir une preuve de nouveauté.
    if (rows.every(row => row.uuid !== undefined) || performance.now() >= end) return rows;
    await sleep(POLL_MS);
  }
}
// WHY : un update expiré peut appliquer son préfixe après le finally.
// CONTRACT : après règlement de cet appel seulement, un unique effacement de
// secours ; jamais de relance de l'API bloquée ni de nouvelles captures.
// LIMIT : si Firefox ne règle jamais l'appel (ou l'effacement), aucune garantie
// de nettoyage temporelle n'est possible. Redémarrage requis, nettoyage start.
let prefixCleanupPending = false;
async function mark(id, token) {
  return api(() => {
    const operation = Promise.resolve().then(() => browser.windows.update(id, {titlePreface: `[LABFY:${token}] `}));
    const settled = () => {
      if (!halted) return;
      prefixCleanupPending = true;
      void Promise.resolve().then(() => browser.windows.update(id, {titlePreface: ""}))
        .then(() => { prefixCleanupPending = false; }, () => {});
    };
    void operation.then(settled, settled);
    return operation;
  });
}
async function publish(rows) {
  validate(rows);
  // Valider le lot complet avant le premier message, puis chaque UUID juste
  // avant usage. Ce protocole n'est pas un CAS avec le sessionstore Firefox.
  const fresh = await sample(rows.map(row => row.id));
  if (fresh.some((row, i) => row.uuid !== rows[i].uuid)) throw new Error("IDENTITY_CHANGED");
  for (const row of rows) {
    if (await api(() => browser.sessions.getWindowValue(row.id, KEY)) !== row.uuid) throw new Error("IDENTITY_CHANGED");
    const runtime_token = crypto.randomUUID().replaceAll("-", "");
    try {
      await mark(row.id, runtime_token);
      const answer = await request({op: "map-window", uuid: row.uuid, runtime_token});
      if (answer.result !== "OK" || answer.uuid !== row.uuid || !Number.isSafeInteger(answer.con_id)) throw new Error("PROVIDER_ERROR");
    } finally {
      await api(() => browser.windows.update(row.id, {titlePreface: ""}));
    }
  }
}
async function cycle() {
  // Coalescence sans queue ; la capture ne peut voir un mint partiellement
  // vérifié. Les erreurs restent explicites pour le diagnostic, sans nouveau
  // message natif non supporté par le provider strict existant.
  if (active) return {result: "BUSY"};
  active = true;
  try {
    await publish(await observe());
    lastError = null;
    return {result: "OK"};
  } catch (error) {
    lastError = failureReason(error);
    return {result: "REFUSED", reason: lastError};
  } finally { active = false; }
}
function changed() { changedAt = performance.now(); ++revision; }
// CONTRACT : avant la résolution du premier getAll, la provenance est ambiguë.
// Après cette photographie, onCreated ouvre une candidature, y compris en BOOT.
// Ce choix produit n'est PAS une preuve contre une restauration sans signal.
browser.windows.onCreated.addListener(window => {
  if (window.type !== undefined && window.type !== "normal") return;
  changed();
  if (!Number.isSafeInteger(window.id) || window.id < 0 || candidates.size + quarantine.size >= 256) {
    phase = "PROTECTED";
    return;
  }
  if (window.sessionId) protectedBaseline.add(window.id);
  if (baseline !== null && !window.sessionId && !quarantine.has(window.id)) candidates.add(window.id);
  else { quarantine.add(window.id); protectedBaseline.add(window.id); }
});
browser.windows.onRemoved.addListener(id => {
  changed();
  candidates.delete(id); quarantine.delete(id); attempted.delete(id); known.delete(id); protectedBaseline.delete(id);
  if (baseline) baseline.delete(id);
});
browser.sessions.onChanged.addListener(() => {
  // Liste fermée modifiée (y compris fermeture d'onglet), sans provenance.
  // Invalider l'observation, attendre le calme, conserver les candidatures.
  changed();
  restoreUntil = performance.now() + RESTORE_GUARD_MS;
});
browser.runtime.onInstalled.addListener(details => {
  // WHY : install couvre aussi une réinstallation avec checkpoint externe.
  // CONTRACT : événement conservé avant/après start, aucun autre reason admis.
  if (details.reason === "install" && !installed) { installed = true; changed(); }
});
browser.runtime.onMessage.addListener((message, sender) => {
  if (sender.id !== browser.runtime.id || !message || message.op !== "identity-status") return undefined;
  return Promise.resolve({phase, result: halted || phase === "PROTECTED" || quarantine.size || lastError ? "REFUSED" : active || candidates.size ? "WAIT" : phase === "READY" ? "READY" : "WAIT",
    reason: lastError, prefixCleanupPending, quarantined: quarantine.size, pending: candidates.size});
});
async function autoStep() {
  if (active || halted || phase === "PROTECTED") return;
  active = true;
  let targets = [];
  try {
    const expected = await ids();
    if (baseline === null) baseline = new Set(expected);
    const epoch = revision;
    const rows = await sample(expected);
    for (const row of rows) {
      if (row.uuid !== undefined) { candidates.delete(row.id); quarantine.delete(row.id); }
      else if (!candidates.has(row.id)) quarantine.add(row.id);
    }
    const now = performance.now();
    if (phase === "BOOT") {
      if (now - started < STARTUP_MS || now - changedAt < OBSERVE_MS || now < restoreUntil) return;
      // Une ancienne absence empêche la capture exacte, pas les futurs Ctrl+N.
      phase = "READY";
    }
    if (now < restoreUntil) return;
    // Une seule tentative de lot baseline par instance. Refus, timeout ou
    // activité invalident ce droit ; la reconnexion ne le ressuscite jamais.
    const bootstrap = new Set(installed && !bootstrapClosed ? rows.filter(row =>
      baseline.has(row.id) && row.uuid === undefined && !protectedBaseline.has(row.id)
      && !known.has(row.id) && !attempted.has(row.id)).map(row => row.id) : []);
    if (installed) bootstrapClosed = true;
    targets = rows.filter(row => row.uuid === undefined && (candidates.has(row.id) || bootstrap.has(row.id)) && !attempted.has(row.id)).map(row => row.id);
    if (!targets.length) { lastError = quarantine.size ? "AMBIGUOUS_WINDOW" : null; return; }
    // Observations répétées du lot complet ; un changement d'ensemble, une
    // erreur ou un signal session durant l'attente révoque cette tentative.
    const observed = targets.length ? await observe() : rows;
    if (epoch !== revision) throw new Error("WINDOW_ACTIVITY");
    const fresh = await sample(expected);
    if (epoch !== revision) throw new Error("WINDOW_ACTIVITY");
    let bootstrapAllowed = true;
    for (const id of targets) {
      if (bootstrap.has(id)) {
        // WHY : réduire la course avec un checkpoint créé durant l'observation
        // ou l'écriture sœur. Jamais d'autorité mémorisée entre deux fenêtres.
        // CONTRACT : protocole exact, booléen strict, fail closed sans retry.
        if (bootstrapAllowed) {
          try {
            const answer = await request({op: "bootstrap-eligibility"});
            bootstrapAllowed = Object.keys(answer).length === 2 && answer.result === "OK" && answer.baseline_enrollment_allowed === true;
          } catch { bootstrapAllowed = false; }
        }
        if (!bootstrapAllowed) continue;
      }
      if (fresh.find(row => row.id === id).uuid !== undefined) { candidates.delete(id); continue; }
      if ((quarantine.has(id) && !bootstrap.has(id)) || attempted.has(id)) throw new Error("QUARANTINED");
      if (observed.some(row => row.id === id && row.uuid !== undefined)) throw new Error("IDENTITY_CHANGED");
      // Dernière lecture intégrale avant CHAQUE écriture. Les cibles sœurs
      // absentes restent isolées ; une ancienne ambiguïté ne devient pas cible.
      const before = await sample(expected);
      if (epoch !== revision) throw new Error("WINDOW_ACTIVITY");
      if (before.find(row => row.id === id).uuid !== undefined) continue;
      const value = crypto.randomUUID();
      validate([...before.filter(row => row.id !== id), {id, uuid: value}], false);
      await api(() => {
        if (epoch !== revision) throw new Error("WINDOW_ACTIVITY");
        // INVARIANT : marquer au point d'appel, jamais pour une lecture avortée.
        // Rejet/timeout peut cacher un effet ; aucune seconde écriture ensuite.
        attempted.add(id);
        known.set(id, value);
        return browser.sessions.setWindowValue(id, KEY, value);
      });
      const verified = await sample(expected);
      if (epoch !== revision) throw new Error("WINDOW_ACTIVITY");
      if (verified.find(row => row.id === id).uuid !== value) throw new Error("WRITE_UNCERTAIN");
      candidates.delete(id); quarantine.delete(id);
    }
    lastError = quarantine.size ? "AMBIGUOUS_WINDOW" : null;
  } catch (error) {
    lastError = failureReason(error);
    // CONTRACT : une activité avant écriture annule ce passage. Seuls les
    // candidats onCreated seront relus après calme ; aucune écriture incertaine
    // n'est retentée. Les erreurs de lecture/identité restent conservatrices.
    // Une erreur de lecture baseline interdit également une autorisation future.
    if (installed) bootstrapClosed = true;
    const transient = ["WINDOW_ACTIVITY", "WINDOW_SET_CHANGED"].includes(lastError);
    for (const id of transient ? targets : [...candidates]) {
      if (!transient || attempted.has(id)) { candidates.delete(id); quarantine.add(id); }
    }
  } finally { active = false; }
}
async function start() {
  active = true;
  // La baseline est capturée avant les nettoyages ; les événements déjà reçus
  // restent protégés indépendamment de leur présence dans cette photographie.
  try { baseline = new Set(await ids()); }
  catch (error) { phase = "PROTECTED"; lastError = failureReason(error); }
  try {
    for (const id of await ids()) {
      try { await api(() => browser.windows.update(id, {titlePreface: ""})); } catch {}
    }
  } catch { /* Une erreur d'énumération ne doit pas supprimer la reconnexion. */ }
  try { connect(); } catch {}
  // Reconnexion seulement ; aucune requête de corrélation en idle.
  setInterval(() => { if (!port) { try { connect(); } catch {} } }, 1000);
  active = false;
}
// Un seul passage périodique, sans queue ni promesse empilée pendant un appel
// lent. Toutes les lectures/écritures et captures partagent le verrou active.
setInterval(() => { void autoStep(); }, 1000);
void start().catch(() => {});

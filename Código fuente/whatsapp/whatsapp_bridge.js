#!/usr/bin/env node
/**
 * whatsapp_bridge.js — Puente REST para WhatsApp usando Baileys
 * Rubencho AI  ·  Baileys 7 (direcciones LID de WhatsApp)
 *
 * Además de enviar mensajes y atender el chat propio, guarda en el PC:
 *   · la agenda (nombres de los contactos)            → whatsapp_store/contactos.json
 *   · los mensajes de los chats individuales (no grupos) → whatsapp_store/mensajes/
 * para que Rubencho los pueda leer SOLO cuando el usuario se lo pide.
 * Los mensajes de otras personas nunca se envían solos a la IA.
 */

const express = require('express');
const {
    default: makeWASocket,
    DisconnectReason,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    jidNormalizedUser,          // normaliza "número:device@s.whatsapp.net" → "número@s.whatsapp.net"
    normalizeMessageContent,
    getContentType,
    downloadMediaMessage,
    BufferJSON,
    proto,
    jidEncode,
    jidDecode,
    encodeWAMessage,
    encodeSignedDeviceIdentity,
    generateMessageIDV2,
} = require('@whiskeysockets/baileys');
const pino   = require('pino');
const QRCode = require('qrcode');
const path   = require('path');
const os     = require('os');
const fs     = require('fs');

const PORT        = parseInt(process.env.WHATSAPP_BRIDGE_PORT || '3847', 10);
// Rubencho AI le indica dónde guardar la sesión (carpeta de datos de la app)
const SESSION_DIR = process.env.RUBENCHO_WA_SESSION ||
    path.join(process.env.APPDATA || os.homedir(), 'Rubencho AI', 'whatsapp_session');
const STORE_DIR   = process.env.RUBENCHO_WA_STORE ||
    path.join(path.dirname(SESSION_DIR), 'whatsapp_store');
const MSG_DIR       = path.join(STORE_DIR, 'mensajes');
const CONTACTS_FILE = path.join(STORE_DIR, 'contactos.json');
const MAX_PER_CHAT  = parseInt(process.env.RUBENCHO_WA_MAX_STORE || '400', 10);
// Claves de la sincronización de la app (agenda…) que el móvil no nos ha pasado.
// Baileys solo las menciona en su log, así que se capturan de ahí.
const missingAppStateKeys = new Set();
function makeLogger(base) {
    const wrap = lvl => (obj, ...rest) => {
        try {
            const txt = typeof obj === 'string' ? obj : JSON.stringify(obj);
            for (const m of txt.matchAll(/failed to find key \\?"([A-Za-z0-9+/=]+)\\?"/g))
                missingAppStateKeys.add(m[1]);
        } catch {}
        return base[lvl](obj, ...rest);
    };
    return {
        get level() { return base.level; }, set level(v) { base.level = v; },
        trace: wrap('trace'), debug: wrap('debug'), info: wrap('info'),
        warn: wrap('warn'), error: wrap('error'), fatal: wrap('fatal'),
        child: bindings => makeLogger(base.child(bindings)),
    };
}
// diagnóstico: RUBENCHO_WA_LOG=info
const logger      = makeLogger(pino({ level: process.env.RUBENCHO_WA_LOG || 'silent' }));

for (const d of [SESSION_DIR, MSG_DIR]) if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });

let sock           = null;
let authState      = null;
let qrBase64       = null;
let isConnected    = false;
let selfJid        = null;
let reconnectTimer = null;
const contactsCache = {};      // jid (teléfono o lid) → nombre, para resolver y detectar el chat propio

// Cola de mensajes entrantes del chat propio (para que Python los consuma)
const incomingQueue = [];

// IDs de mensajes enviados por el bridge — para no procesarlos como entrantes
const sentByBridge = new Set();
setInterval(() => sentByBridge.clear(), 120_000); // limpieza cada 2 min

// IDs ya encolados/procesados — evita duplicados aunque Python haya vaciado la cola
// WhatsApp puede entregar el mismo mensaje en formatos @lid y @s.whatsapp.net
const processedMsgIds = new Set();
setInterval(() => processedMsgIds.clear(), 300_000); // limpieza cada 5 min

// Todos los formatos de chatId que se han confirmado como "chat propio"
const knownSelfChatJids = new Set();

// LID propio (Linked ID — formato nuevo de WhatsApp). Se carga desde creds.json
// o se aprende del primer mensaje @lid recibido.
let selfLidJid = null;

// Intentar leer el LID desde el archivo de credenciales de Baileys (creds.json).
// Baileys lo guarda como creds.me.lid tras la primera conexión con LID.
function loadSelfLidFromCreds() {
    try {
        const credsPath = path.join(SESSION_DIR, 'creds.json');
        if (!fs.existsSync(credsPath)) return null;
        const creds = JSON.parse(fs.readFileSync(credsPath, 'utf8'));
        const lid = creds?.me?.lid || null;
        if (lid) {
            let normLid = lid;
            try { normLid = jidNormalizedUser(lid); } catch {}
            selfLidJid = normLid;
            knownSelfChatJids.add(lid);
            knownSelfChatJids.add(normLid);
            pushLog('🔑', `LID cargado de creds.json: ${normLid}`);
        }
        return lid;
    } catch { return null; }
}

// Log de eventos para la página de diagnóstico (/debug-page). Los avisos de cada
// mensaje van aparte para que no tapen los eventos importantes.
const eventLog = [];
const msgLog = [];
const ROUTINE_ICONS = new Set(['📨', '📋', '🔍', '⏭️', '✅']);
function pushLog(icon, msg) {
    const entry = { time: new Date().toLocaleTimeString('es-ES'), icon, msg };
    const log = ROUTINE_ICONS.has(icon) ? msgLog : eventLog;
    log.unshift(entry);
    if (log.length > 80) log.length = 80;
}

// Sesión de Baileys con nombres de fichero válidos en Windows. Los identificadores
// de las claves de sincronización distinguen mayúsculas («AAAAAIUb» ≠ «AAAAAIUB»)
// pero Windows no: las dos claves acababan en el mismo fichero, que se corrompía.
// Ahora cada una se guarda con su identificador en hexadecimal.
async function useSafeAuthState(dir) {
    const base = await useMultiFileAuthState(dir);
    const TYPE = 'app-state-sync-key';
    const safe = id => 'hex' + Buffer.from(id, 'base64').toString('hex');
    const keys = {
        get: async (type, ids) => {
            if (type !== TYPE) return base.state.keys.get(type, ids);
            const got = await base.state.keys.get(type, ids.map(safe));
            const out = {}, legacy = [];
            for (const id of ids) {
                if (got[safe(id)]) out[id] = got[safe(id)];
                else legacy.push(id);
            }
            if (legacy.length) {                     // claves guardadas con el nombre antiguo
                const old = await base.state.keys.get(type, legacy);
                for (const id of legacy) out[id] = old[id] || null;
            }
            return out;
        },
        set: async data => {
            if (data[TYPE]) {
                const m = {};
                for (const [id, v] of Object.entries(data[TYPE])) m[safe(id)] = v;
                data = { ...data, [TYPE]: m };
            }
            return base.state.keys.set(data);
        },
    };
    return { state: { creds: base.state.creds, keys }, saveCreds: base.saveCreds };
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
function norm(jid) { try { return jidNormalizedUser(jid); } catch { return jid || ''; } }
function isIgnoredJid(jid) {
    return !jid || jid.endsWith('@g.us') || jid.endsWith('@broadcast') ||
           jid.endsWith('@newsletter') || jid === 'status@broadcast';
}
function atomicWrite(file, data) {
    const tmp = file + '.tmp';
    fs.writeFileSync(tmp, data);
    fs.renameSync(tmp, file);
}

// ══════════════════════════════════════════════════════════════════════════
//  Contactos (agenda) — se guardan en el PC para no depender de la sincronización
// ══════════════════════════════════════════════════════════════════════════
// clave: jid de teléfono (o lid si no se conoce el teléfono) → { name, notify, jid, lid }
let contacts = {};
const lidToPn = {};            // lid → jid de teléfono
let contactsSaveTimer = null;
let refreshing = false;
let needsRelink = false;       // faltan claves que el móvil no envía: hay que volver a vincular

function loadContacts() {
    try {
        const d = JSON.parse(fs.readFileSync(CONTACTS_FILE, 'utf8'));
        contacts = d.contacts || {};
        Object.assign(lidToPn, d.lidToPn || {});
    } catch { contacts = {}; }
    for (const [k, c] of Object.entries(contacts)) {
        const name = c.name || c.notify;
        if (!name) continue;
        contactsCache[k] = name;
        if (c.lid) contactsCache[c.lid] = name;
    }
}
function saveContacts() {
    if (contactsSaveTimer) { clearTimeout(contactsSaveTimer); contactsSaveTimer = null; }
    try { atomicWrite(CONTACTS_FILE, JSON.stringify({ contacts, lidToPn })); }
    catch (e) { console.error('[Bridge] No se pudieron guardar los contactos:', e.message); }
}
function saveContactsSoon() {
    if (!contactsSaveTimer) contactsSaveTimer = setTimeout(saveContacts, 1500);
}
function namedCount() { return Object.values(contacts).filter(c => c.name).length; }

function upsertContact(c) {
    if (!c || !c.id) return;
    const id = norm(c.id);
    if (isIgnoredJid(id)) return;
    let pn  = c.jid ? norm(c.jid) : c.phoneNumber ? norm(c.phoneNumber)
            : (id.endsWith('@s.whatsapp.net') ? id : null);
    if (pn && !pn.endsWith('@s.whatsapp.net')) pn = null;
    const lid = c.lid ? norm(c.lid) : (id.endsWith('@lid') ? id : null);
    if (lid && !pn && lidToPn[lid]) pn = lidToPn[lid];
    if (lid && pn && lidToPn[lid] !== pn) { lidToPn[lid] = pn; mergeChat(lid, pn); }
    const key = pn || lid;
    if (!key) return;
    const cur = contacts[key] || (lid && contacts[lid]) || {};
    if (pn && lid && key !== lid && contacts[lid]) delete contacts[lid];
    const next = { ...cur, jid: pn || cur.jid || null, lid: lid || cur.lid || null };
    if (c.name) next.name = c.name;                      // nombre guardado en la agenda
    if (c.notify) next.notify = c.notify;                // nombre que se ha puesto la persona
    else if (c.verifiedName && !next.notify) next.notify = c.verifiedName;
    contacts[key] = next;
    const name = next.name || next.notify;
    if (name) {
        contactsCache[key] = name;
        if (next.lid) contactsCache[next.lid] = name;
    }
    saveContactsSoon();
}

// Mensaje de protocolo directo al móvil principal (dispositivo 0), sin el sobre
// «enviado desde otro dispositivo» que Baileys pone a todo lo que va a uno mismo
// (con ese sobre el móvil no atiende las peticiones).
async function sendToMyPhone(message) {
    const { user } = jidDecode(authState.creds.me.id);
    const phoneJid = jidEncode(user, 's.whatsapp.net');
    await sock.assertSessions([phoneJid], false);
    const { type, ciphertext } = await sock.signalRepository.encryptMessage({
        jid: phoneJid, data: encodeWAMessage(message) });
    const content = [{ tag: 'enc', attrs: { v: '2', type }, content: ciphertext }];
    if (type === 'pkmsg')
        content.push({ tag: 'device-identity', attrs: {},
                       content: encodeSignedDeviceIdentity(authState.creds.account, true) });
    await sock.sendNode({
        tag: 'message',
        attrs: { id: generateMessageIDV2(authState.creds.me.id), type: 'text', to: phoneJid,
                 category: 'peer', push_priority: 'high_force' },
        content,
    });
}

// Pide al móvil las claves de sincronización que faltan (lo mismo que hace
// WhatsApp Web). El móvil responde con un mensaje que Baileys guarda solo.
async function requestAppStateKeys(ids) {
    await sendToMyPhone({
        protocolMessage: {
            type: proto.Message.ProtocolMessage.Type.APP_STATE_SYNC_KEY_REQUEST,
            appStateSyncKeyRequest: { keyIds: ids.map(id => ({ keyId: Buffer.from(id, 'base64') })) },
        },
    });
}
async function haveKeys(ids) {
    const got = await authState.keys.get('app-state-sync-key', ids);
    return ids.every(id => !!got[id]);
}

async function syncContactsOnce() {
    await authState.keys.set({ 'app-state-sync-version': { critical_unblock_low: null } });
    await sock.resyncAppState(['critical_unblock_low'], true);
    // Los eventos llegan un poco después: esperar a que el número deje de cambiar
    let last = -1, stable = 0;
    for (let i = 0; i < 40 && stable < 4; i++) {
        await sleep(400);
        const n = namedCount();
        stable = n === last ? stable + 1 : 0;
        last = n;
    }
}

// Vuelve a descargar la agenda entera desde WhatsApp (colección de contactos de la
// sincronización de la app), sin tener que volver a escanear el QR.
async function refreshContacts() {
    if (!sock || !isConnected || !authState || refreshing) return false;
    refreshing = true;
    pushLog('👥', 'Sincronizando la agenda de contactos…');
    try {
        for (let attempt = 1; attempt <= 4; attempt++) {
            missingAppStateKeys.clear();
            await syncContactsOnce();
            if (!missingAppStateKeys.size) break;
            const ids = [...missingAppStateKeys];
            pushLog('🔑', `Faltan ${ids.length} claves de sincronización: se piden al móvil (intento ${attempt})`);
            await requestAppStateKeys(ids);
            let ok = false;
            for (let i = 0; i < 40 && !ok; i++) { await sleep(500); ok = await haveKeys(ids); }
            if (!ok) {
                needsRelink = namedCount() === 0;
                pushLog('⚠️', 'El móvil no ha enviado las claves: para tener la agenda hay que volver a vincular');
                break;
            }
            pushLog('🔑', 'Claves recibidas del móvil');
        }
        if (namedCount() > 0) needsRelink = false;
        saveContacts();
        pushLog('👥', `Agenda sincronizada: ${namedCount()} contactos`);
        return namedCount() > 0;
    } catch (e) {
        pushLog('⚠️', `No se pudo sincronizar la agenda: ${e.message}`);
        return false;
    } finally {
        refreshing = false;
    }
}

// ══════════════════════════════════════════════════════════════════════════
//  Mensajes guardados (solo chats individuales)
// ══════════════════════════════════════════════════════════════════════════
const chatCache = {};
const dirtyChats = new Set();
let chatsSaveTimer = null;

function chatFile(id) { return path.join(MSG_DIR, id.replace(/[^0-9A-Za-z@._-]/g, '_') + '.json'); }
function getChat(id) {
    if (!chatCache[id]) {
        try { chatCache[id] = JSON.parse(fs.readFileSync(chatFile(id), 'utf8'), BufferJSON.reviver); }
        catch { chatCache[id] = []; }
    }
    return chatCache[id];
}
function flushChats() {
    if (chatsSaveTimer) { clearTimeout(chatsSaveTimer); chatsSaveTimer = null; }
    for (const id of dirtyChats) {
        try { atomicWrite(chatFile(id), JSON.stringify(chatCache[id] || [], BufferJSON.replacer)); }
        catch (e) { console.error('[Bridge] No se pudo guardar el chat:', e.message); }
    }
    dirtyChats.clear();
}
function saveChatSoon(id) {
    dirtyChats.add(id);
    if (!chatsSaveTimer) chatsSaveTimer = setTimeout(flushChats, 2000);
}
// Si un chat se guardó con su lid y luego se conoce su teléfono, se juntan
function mergeChat(fromId, toId) {
    if (!fromId || !toId || fromId === toId) return;
    const src = getChat(fromId);
    if (!src.length) return;
    const dst = getChat(toId);
    const ids = new Set(dst.map(e => e.id));
    for (const e of src) if (!ids.has(e.id)) dst.push(e);
    dst.sort((a, b) => a.ts - b.ts);
    if (dst.length > MAX_PER_CHAT) dst.splice(0, dst.length - MAX_PER_CHAT);
    chatCache[fromId] = [];
    try { fs.rmSync(chatFile(fromId), { force: true }); } catch {}
    saveChatSoon(toId);
}
// Relación LID ↔ teléfono que va conociendo Baileys
function learnLid(lid, pn) {
    lid = norm(lid || ''); pn = norm(pn || '');
    if (!lid.endsWith('@lid') || !pn.endsWith('@s.whatsapp.net') || lidToPn[lid] === pn) return;
    lidToPn[lid] = pn;
    if (contacts[lid]) upsertContact({ id: pn, lid, ...contacts[lid] });
    saveContactsSoon();
    mergeChat(lid, pn);
}
// Chat al que pertenece un mensaje (jid de teléfono si se conoce; si no, el lid)
function canonChat(remoteJid, key) {
    const id = norm(remoteJid || '');
    if (id.endsWith('@lid')) {
        // sender_pn = teléfono de quien escribe (solo vale si no lo he escrito yo)
        const alt = key && !key.fromMe && (key.remoteJidAlt || key.senderPn);
        if (alt) learnLid(id, alt);
        if (lidToPn[id]) return lidToPn[id];
    }
    return id;
}
// Contenido de un mensaje guardado, para reenviarlo si el otro móvil lo pide
function findStoredMessage(key) {
    const e = getChat(canonChat(key?.remoteJid || '')).find(x => x.id === key?.id);
    if (!e) return undefined;
    if (e.raw?.message) return e.raw.message;
    return e.text != null ? { conversation: e.text } : undefined;
}
function toMs(ts) {
    if (!ts) return Date.now();
    const n = typeof ts === 'object' ? (typeof ts.toNumber === 'function' ? ts.toNumber() : Number(ts.low)) : Number(ts);
    return n > 1e12 ? n : n * 1000;
}
const SKIP_TYPES = new Set(['protocolMessage', 'senderKeyDistributionMessage', 'reactionMessage',
    'messageContextInfo', 'pollUpdateMessage', 'keepInChatMessage', 'pinInChatMessage',
    'encReactionMessage', 'editedMessage']);
const MEDIA_TYPES = new Set(['imageMessage', 'audioMessage', 'videoMessage', 'stickerMessage',
    'documentMessage', 'ptvMessage']);

function storeMessage(msg) {
    const rj = msg?.key?.remoteJid;
    if (!rj || isIgnoredJid(rj) || !msg.key.id) return;
    const content = normalizeMessageContent(msg.message);
    if (!content) return;
    const ctype = getContentType(content);
    if (!ctype || SKIP_TYPES.has(ctype)) return;
    const id  = canonChat(rj, msg.key);
    const arr = getChat(id);
    if (arr.some(e => e.id === msg.key.id)) return;
    const c = content[ctype] || {};
    const e = {
        id: msg.key.id, fromMe: !!msg.key.fromMe, ts: toMs(msg.messageTimestamp), kind: ctype,
        key: { remoteJid: rj, fromMe: !!msg.key.fromMe, id: msg.key.id },
    };
    if (msg.pushName && !msg.key.fromMe) e.push = msg.pushName;
    if (ctype === 'conversation') e.text = content.conversation;
    else if (ctype === 'extendedTextMessage') e.text = c.text;
    else if (MEDIA_TYPES.has(ctype)) {
        if (c.caption) e.caption = c.caption;
        if (c.seconds) e.seconds = c.seconds;
        if (c.fileName) e.fileName = c.fileName;
        if (c.mimetype) e.mimetype = c.mimetype;
        if (c.ptt) e.ptt = true;
        e.raw = { key: msg.key, message: msg.message, messageTimestamp: msg.messageTimestamp };
    }
    else if (ctype === 'contactMessage') e.text = c.displayName || '';
    else if (ctype === 'locationMessage' || ctype === 'liveLocationMessage') e.text = c.name || c.address || '';
    else if (ctype.startsWith('pollCreationMessage')) e.text = c.name || '';
    else e.text = c.text || c.caption || '';
    arr.push(e);
    arr.sort((a, b) => a.ts - b.ts);
    if (arr.length > MAX_PER_CHAT) arr.splice(0, arr.length - MAX_PER_CHAT);
    saveChatSoon(id);
}

const app = express();
app.use(express.json());

function resolveJid(to) {
    to = (to || '').trim();

    // Nunca resolver a grupos (@g.us)
    if (to.includes('@g.us')) return null;
    if (to.includes('@')) {
        return (to.endsWith('@s.whatsapp.net') || to.endsWith('@lid')) ? to : null;
    }

    // Buscar por nombre — solo contactos individuales, nunca grupos.
    // Primero el nombre exacto; si no, una coincidencia parcial ÚNICA.
    const needle = to.toLowerCase();
    const entries = Object.entries(contacts).filter(([, c]) => c.name);
    const exact = entries.filter(([, c]) => c.name.toLowerCase() === needle);
    if (exact.length === 1) return exact[0][0];
    const partial = entries.filter(([, c]) => c.name.toLowerCase().includes(needle));
    if (partial.length === 1) return partial[0][0];
    if (exact.length || partial.length) return null;   // ambiguo: mejor no adivinar

    // Número de teléfono
    const digits = to.replace(/[\s\-\(\)\.\+]/g, '');
    if (/^\d{7,}$/.test(digits)) return digits + '@s.whatsapp.net';
    return null;
}

async function startSocket() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    try {
        const { state, saveCreds } = await useSafeAuthState(SESSION_DIR);
        authState = state;
        const { version }          = await fetchLatestBaileysVersion();
        console.log(`[Bridge] Baileys WA ${version.join('.')}`);

        sock = makeWASocket({
            version,
            logger,
            auth:              state,
            browser:           ['Rubencho AI', 'Chrome', '120.0.0'],
            generateHighQualityLinkPreview: false,
            syncFullHistory:   false,
            // Sin esto, Baileys descarta TODO el historial (también el reciente que
            // WhatsApp envía al vincular y el que se pide bajo demanda)
            shouldSyncHistoryMessage: h =>
                h.syncType !== proto.HistorySync.HistorySyncType.FULL,
            // Si un móvil no consigue descifrar un mensaje pide que se le reenvíe;
            // Baileys guarda los recientes y, si no, se busca aquí
            getMessage: async key => findStoredMessage(key),
        });

        sock.ev.on('lid-mapping.update', ({ lid, pn }) => learnLid(lid, pn));

        sock.ev.on('contacts.update', updates => { for (const c of updates) upsertContact(c); });
        sock.ev.on('contacts.upsert', list => { for (const c of list) upsertContact(c); });

        // Historial inicial (al vincular) y bajo demanda: contactos, chats y mensajes
        sock.ev.on('messaging-history.set', ({ contacts: histContacts, chats, messages, syncType }) => {
            for (const c of histContacts || []) upsertContact(c);
            for (const chat of chats || []) {
                if (chat.id && chat.name && !contacts[canonChat(chat.id)]?.name)
                    upsertContact({ id: chat.id, name: chat.name });
            }
            let n = 0;
            for (const m of messages || []) { try { storeMessage(m); n++; } catch {} }
            pushLog('🗂️', `Historial recibido (tipo ${syncType}): ${n} mensajes, ${(histContacts || []).length} contactos`);
        });

        // También pillamos contactos de los chats entrantes
        sock.ev.on('chats.upsert', chats => {
            for (const chat of chats) {
                if (chat.id && chat.name && !isIgnoredJid(chat.id) && !contacts[canonChat(chat.id)]?.name)
                    upsertContact({ id: chat.id, name: chat.name });
            }
        });

        // ── Mensajes: se guardan todos los de chats individuales; a Python solo
        //    se le pasan (como órdenes) los del chat propio ───────────────────
        sock.ev.on('messages.upsert', ({ messages: msgs, type }) => {
            pushLog('📨', `messages.upsert | type="${type}" | n=${msgs.length}`);

            for (const msg of msgs) {
                try { storeMessage(msg); } catch (e) { pushLog('⚠️', `No se pudo guardar un mensaje: ${e.message}`); }

                const chatId = msg.key?.remoteJid || '';
                const msgId  = msg.key?.id        || '';
                const fromMe = !!msg.key?.fromMe;
                const content = normalizeMessageContent(msg.message) || {};
                const text   = content.conversation || content.extendedTextMessage?.text || '';
                // Audios (notas de voz): Rubencho los descarga y los transcribe
                const audio  = content.audioMessage;

                pushLog('📋', `chatId="${chatId}" fromMe=${fromMe} type="${type}" id="${msgId.substring(0,14)}"`);

                // Filtros básicos
                if (!chatId || chatId.endsWith('@g.us') || chatId === 'status@broadcast') continue;
                if (!text.trim() && !audio) { pushLog('⏭️', 'SKIP: sin texto ni audio'); continue; }

                // Deduplicar (mismo msg puede llegar en @lid y @s.whatsapp.net)
                if (msgId && processedMsgIds.has(msgId)) {
                    pushLog('⏭️', 'SKIP: duplicado'); continue;
                }

                // Filtrar respuestas del bridge
                if (sentByBridge.has(msgId)) {
                    sentByBridge.delete(msgId);
                    pushLog('⏭️', 'SKIP: respuesta bridge (rastreado)'); continue;
                }
                if (fromMe && msgId.startsWith('BAE')) {
                    pushLog('⏭️', 'SKIP: respuesta bridge (BAE)'); continue;
                }

                // ── Detección del chat propio ──────────────────────────────
                let normalChat = chatId;
                try { normalChat = jidNormalizedUser(chatId); } catch {}

                const isPhoneMatch = !!(selfJid && (() => {
                    try { return jidNormalizedUser(selfJid) === normalChat; } catch { return false; }
                })());
                const isKnownJid = knownSelfChatJids.has(chatId) || knownSelfChatJids.has(normalChat);

                // Aprendizaje de LID — solo ocurre UNA VEZ y solo si:
                // 1) Aún no sabemos el LID  2) El msg es @lid  3) Es fromMe
                // 4) type=notify (msgs a otros suelen llegar como append)
                // 5) No es un contacto conocido en cache
                let justLearnedLid = false;
                if (!isPhoneMatch && !isKnownJid && !selfLidJid
                    && fromMe && chatId.endsWith('@lid') && type === 'notify'
                    && !contactsCache[chatId] && !contactsCache[normalChat]) {
                    selfLidJid = normalChat;
                    knownSelfChatJids.add(chatId);
                    knownSelfChatJids.add(normalChat);
                    justLearnedLid = true;
                    pushLog('🧠', `LID propio aprendido: ${normalChat}`);
                }

                const isSelfChat = isPhoneMatch || isKnownJid || justLearnedLid;
                pushLog('🔍', `normalChat="${normalChat}" phone=${isPhoneMatch} known=${isKnownJid} learned=${justLearnedLid} → self=${isSelfChat}`);

                if (!isSelfChat) { pushLog('⏭️', 'SKIP: no es chat propio (solo se guarda)'); continue; }

                // ── Encolar ────────────────────────────────────────────────
                pushLog('✅', audio ? `ENCOLADO: audio de ${audio.seconds || '?'} s`
                                    : `ENCOLADO: "${text.substring(0, 60)}"`);
                knownSelfChatJids.add(chatId);
                knownSelfChatJids.add(normalChat);
                processedMsgIds.add(msgId);
                const item = { text, timestamp: Date.now(), id: msgId };
                if (audio) item.audio = { jid: chatId, seconds: audio.seconds || 0 };
                incomingQueue.push(item);
            }
        });

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                try {
                    qrBase64    = await QRCode.toDataURL(qr);
                    isConnected = false;
                    pushLog('📱', `QR generado → http://localhost:${PORT}/qr-page`);
                    console.log(`[Bridge] QR listo -> http://localhost:${PORT}/qr-page`);
                } catch (e) { console.error('[Bridge] Error QR:', e.message); }
            }
            if (connection === 'close') {
                isConnected = false;
                qrBase64    = null;
                const code  = lastDisconnect?.error?.output?.statusCode;
                const loggedOut = code === DisconnectReason.loggedOut;
                pushLog('🔴', `Desconectado. code=${code} loggedOut=${loggedOut}`);
                if (loggedOut) {
                    knownSelfChatJids.clear();
                    try { fs.rmSync(SESSION_DIR, { recursive: true, force: true }); } catch (_) {}
                    fs.mkdirSync(SESSION_DIR, { recursive: true });
                }
                reconnectTimer = setTimeout(startSocket, 4000);
            } else if (connection === 'open') {
                isConnected = true;
                qrBase64    = null;
                selfJid     = sock.user?.id || null;

                knownSelfChatJids.clear();
                selfLidJid = null;

                if (selfJid) {
                    knownSelfChatJids.add(selfJid);
                    try { knownSelfChatJids.add(jidNormalizedUser(selfJid)); } catch {}
                }

                // Buscar LID en todas las fuentes disponibles
                const lidCandidates = [
                    sock.user?.lid,
                    state.creds?.me?.lid,
                ];
                for (const lid of lidCandidates) {
                    if (lid && !selfLidJid) {
                        let normLid = lid;
                        try { normLid = jidNormalizedUser(lid); } catch {}
                        selfLidJid = normLid;
                        knownSelfChatJids.add(lid);
                        knownSelfChatJids.add(normLid);
                        pushLog('🔑', `LID detectado en sock/creds: ${normLid}`);
                    }
                }
                // Si no está en memoria, intentar leerlo del archivo
                if (!selfLidJid) loadSelfLidFromCreds();
                if (!selfLidJid) pushLog('⚠️', 'LID no encontrado aún — se aprenderá del primer msg @lid');

                pushLog('🟢', `Conectado | selfJid=${selfJid} | selfLid=${selfLidJid} | conocidos=[${[...knownSelfChatJids].join(', ')}]`);
                console.log(`[Bridge] Conectado como ${selfJid}`);

                // Si aún no tenemos la agenda guardada (y Baileys no la ha traído al
                // vincular), se intenta descargar una vez
                setTimeout(() => { if (isConnected && namedCount() === 0) refreshContacts(); }, 30000);
            }
        });

        sock.ev.on('creds.update', saveCreds);
    } catch (err) {
        console.error('[Bridge] Error iniciando socket:', err.message);
        reconnectTimer = setTimeout(startSocket, 5000);
    }
}

app.get('/status', (req, res) =>
    res.json({ connected: isConnected, has_qr: !!qrBase64, self: selfJid,
               contacts: namedCount(), refreshing, needs_relink: needsRelink }));

// Desvincula este dispositivo y muestra un QR nuevo. Al volver a vincular, WhatsApp
// envía claves nuevas, la agenda completa y el historial reciente de los chats.
app.post('/relink', async (req, res) => {
    pushLog('🔗', 'Volviendo a vincular WhatsApp…');
    res.json({ ok: true, message: 'Desvinculando… en unos segundos habrá un QR nuevo.' });
    needsRelink = false;
    try {
        if (sock && isConnected) { await sock.logout(); return; }   // → 'close' borra la sesión
    } catch (e) { pushLog('⚠️', `logout: ${e.message}`); }
    try { sock?.end?.(undefined); } catch {}
    try { fs.rmSync(SESSION_DIR, { recursive: true, force: true }); } catch {}
    fs.mkdirSync(SESSION_DIR, { recursive: true });
    knownSelfChatJids.clear();
    setTimeout(startSocket, 1500);
});

// Endpoint de diagnóstico JSON
app.get('/debug', (req, res) => {
    res.json({
        connected:  isConnected,
        selfJid,
        queueSize:  incomingQueue.length,
        queue:      [...incomingQueue],
        contacts:   namedCount(),
    });
});

// Página de diagnóstico visual — ábrela en el navegador mientras pruebas
app.get('/debug-page', (req, res) => {
    const statusColor = isConnected ? '#25D366' : '#e74c3c';
    const statusText  = isConnected ? `✅ Conectado como ${selfJid}` : '❌ No conectado';
    const toRows = list => list.map(e => {
        const bg = e.icon === '✅' ? '#1a3a1a'
                 : e.icon === '⚠️' ? '#3a2a00'
                 : e.icon === '⏭️' ? '#2a2a2a'
                 : '#1a1a2a';
        return `<tr style="background:${bg}">
            <td style="color:#888;white-space:nowrap;padding:3px 8px">${e.time}</td>
            <td style="padding:3px 8px">${e.icon}</td>
            <td style="font-family:monospace;font-size:13px;padding:3px 8px;word-break:break-all">${e.msg}</td>
        </tr>`;
    }).join('');
    const rows = toRows(eventLog);
    const msgRows = toRows(msgLog);
    const queueRows = incomingQueue.length === 0
        ? '<tr><td colspan="2" style="color:#666;padding:8px">Cola vacía</td></tr>'
        : incomingQueue.map(m => `<tr>
            <td style="color:#888;padding:3px 8px;font-size:12px">${new Date(m.timestamp).toLocaleTimeString('es-ES')}</td>
            <td style="font-family:monospace;padding:3px 8px">${m.text.substring(0,80)}</td>
          </tr>`).join('');

    res.send(`<!DOCTYPE html><html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Rubencho AI — Bridge Debug</title>
  <meta http-equiv="refresh" content="3">
  <style>
    body { background:#111; color:#ddd; font-family:sans-serif; padding:20px; margin:0 }
    h2   { color:#25D366; margin:0 0 4px }
    h3   { color:#aaa; margin:16px 0 6px; font-size:14px; text-transform:uppercase; letter-spacing:1px }
    .status { padding:10px 16px; border-radius:8px; background:#1a1a1a; border:1px solid ${statusColor}; color:${statusColor}; margin-bottom:16px; font-weight:bold }
    table { width:100%; border-collapse:collapse; background:#161616; border-radius:8px; overflow:hidden }
    tr:hover { filter:brightness(1.2) }
    .hint { color:#555; font-size:12px; margin-top:4px }
  </style>
</head>
<body>
  <h2>🤖 Rubencho AI — Bridge Diagnóstico</h2>
  <p class="hint">Se refresca solo cada 3 segundos · ${new Date().toLocaleTimeString('es-ES')}</p>

  <div class="status">${statusText} · ${namedCount()} contactos en la agenda</div>

  <h3>📥 Cola de mensajes pendientes (${incomingQueue.length})</h3>
  <table><tbody>${queueRows}</tbody></table>

  <h3>📜 Eventos</h3>
  <table><tbody>${rows || '<tr><td style="color:#555;padding:8px">Sin eventos aún.</td></tr>'}</tbody></table>

  <h3>📨 Mensajes recibidos (solo se guardan; a Rubencho solo le llegan los de tu chat propio)</h3>
  <table><tbody>${msgRows || '<tr><td style="color:#555;padding:8px">Sin mensajes aún. Mándate un WA...</td></tr>'}</tbody></table>
</body></html>`);
});

app.get('/qr', (req, res) => {
    if (isConnected) return res.json({ ok: true,  message: 'Ya conectado.' });
    if (!qrBase64)   return res.json({ ok: false, message: 'QR no disponible aun.' });
    res.json({ ok: true, qr: qrBase64 });
});

app.get('/qr-page', (req, res) => {
    if (isConnected) return res.send(`<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><title>WhatsApp Bridge</title>
<style>body{background:#111;color:#fff;font-family:sans-serif;text-align:center;padding:60px}h2{color:#25D366}</style></head>
<body><h2>Conectado</h2><p>Bridge activo en puerto ${PORT}</p><p style="color:#555">${selfJid||''}</p></body></html>`);

    if (!qrBase64) return res.send(`<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><title>Esperando QR</title>
<style>body{background:#111;color:#aaa;font-family:sans-serif;text-align:center;padding:60px}</style>
<script>setTimeout(()=>location.reload(),3000)</script></head>
<body><h2 style="color:#f90">Generando QR...</h2><p>Recargando automaticamente...</p></body></html>`);

    res.send(`<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><title>QR — Rubencho AI</title>
<style>body{background:#111;color:#fff;font-family:sans-serif;text-align:center;padding:40px}
h2{color:#25D366}img{max-width:280px;border-radius:16px;padding:12px;background:#fff;margin:20px auto;display:block}
.hint{background:#1a2a1a;border:1px solid #25D366;border-radius:8px;padding:16px;max-width:400px;margin:0 auto}
p{color:#aaa;font-size:.9rem}</style>
<script>setTimeout(()=>location.reload(),20000)</script></head>
<body>
  <h2>Vincula WhatsApp con Rubencho AI</h2>
  <img src="${qrBase64}" alt="QR">
  <div class="hint">
    <p><strong>Como escanear:</strong></p>
    <p>1. Abre WhatsApp en tu movil</p>
    <p>2. Tres puntos > Dispositivos vinculados</p>
    <p>3. Vincular un dispositivo</p>
    <p>4. Escanea este QR</p>
  </div>
</body></html>`);
});

// Agenda: solo los contactos guardados con nombre (nunca grupos)
app.get('/contacts', (req, res) => {
    const list = Object.entries(contacts)
        .filter(([, c]) => c.name)
        .map(([jid, c]) => ({ jid, name: c.name,
                              phone: (c.jid || '').replace('@s.whatsapp.net', '') || null }))
        .sort((a, b) => a.name.localeCompare(b.name, 'es'));
    res.json({ ok: true, contacts: list, count: list.length, refreshing });
});

app.post('/contacts/refresh', async (req, res) => {
    if (!isConnected) return res.status(503).json({ ok: false, error: 'WhatsApp no conectado.' });
    const ok = await refreshContacts();
    res.json({ ok, count: namedCount(), needs_relink: needsRelink });
});

// Últimos mensajes guardados de un chat individual. Si hay menos de los pedidos,
// se piden los anteriores al móvil (historial bajo demanda) y se espera unos segundos.
app.get('/history', async (req, res) => {
    const jid = String(req.query.jid || '').trim();
    const count = Math.max(1, Math.min(200, parseInt(req.query.count || '10', 10) || 10));
    if (!jid || isIgnoredJid(jid)) return res.status(400).json({ ok: false, error: 'Chat no válido.' });
    const id = canonChat(jid);
    const c = contacts[id];
    if (c?.lid && c.lid !== id) mergeChat(c.lid, id);
    let arr = getChat(id);
    let requested = false;
    if (arr.length < count && arr.length > 0 && isConnected && req.query.ondemand !== '0') {
        const oldest = arr[0];
        try {
            const want = Math.min(50, count - arr.length);
            await sock.fetchMessageHistory(want, oldest.key, oldest.ts);
            requested = true;
            const before = arr.length;
            const t0 = Date.now();
            let direct = false;
            while (Date.now() - t0 < 9000) {
                await sleep(400);
                arr = getChat(id);
                if (arr.length >= count) break;
                if (!direct && arr.length === before && Date.now() - t0 > 3500) {
                    direct = true;                      // el móvil no ha respondido: petición directa
                    await sendToMyPhone({ protocolMessage: {
                        type: proto.Message.ProtocolMessage.Type.PEER_DATA_OPERATION_REQUEST_MESSAGE,
                        peerDataOperationRequestMessage: {
                            peerDataOperationRequestType:
                                proto.Message.PeerDataOperationRequestType.HISTORY_SYNC_ON_DEMAND,
                            historySyncOnDemandRequest: {
                                chatJid: oldest.key.remoteJid, oldestMsgFromMe: oldest.key.fromMe,
                                oldestMsgId: oldest.key.id, oldestMsgTimestampMs: oldest.ts,
                                onDemandMsgCount: want,
                            },
                        },
                    } }).catch(e => pushLog('⚠️', `Petición directa de historial: ${e.message}`));
                }
            }
        } catch (e) { pushLog('⚠️', `Historial bajo demanda: ${e.message}`); }
    }
    const out = arr.slice(-count).map(({ raw, key, ...rest }) => ({ ...rest, media: !!raw }));
    res.json({ ok: true, messages: out, total: arr.length, requested });
});

// Descarga la foto, audio, vídeo o documento de un mensaje guardado
app.get('/media', async (req, res) => {
    const id  = canonChat(String(req.query.jid || ''));
    const mid = String(req.query.id || '');
    const e = getChat(id).find(x => x.id === mid);
    if (!e || !e.raw) return res.status(404).json({ ok: false, error: 'Mensaje no encontrado.' });
    if (!isConnected || !sock) return res.status(503).json({ ok: false, error: 'WhatsApp no conectado.' });
    try {
        const buf = await downloadMediaMessage(e.raw, 'buffer', {},
            { logger, reuploadRequest: sock.updateMediaMessage });
        if (buf.length > 25 * 1024 * 1024)
            return res.status(413).json({ ok: false, error: 'Archivo demasiado grande.' });
        res.json({ ok: true, kind: e.kind, mimetype: e.mimetype || '', seconds: e.seconds || 0,
                   base64: buf.toString('base64') });
    } catch (err) {
        res.status(500).json({ ok: false, error: `No se pudo descargar: ${err.message}` });
    }
});

app.get('/self', (req, res) => res.json({ ok: true, jid: selfJid }));

// Devuelve y vacía la cola de mensajes entrantes del chat propio
app.get('/messages', (req, res) => {
    const msgs = incomingQueue.splice(0);   // vacía la cola y devuelve lo que había
    res.json({ ok: true, messages: msgs });
});

app.post('/send', async (req, res) => {
    const { to, message } = req.body || {};
    if (!to || !message) return res.status(400).json({ ok:false, error:'Faltan "to" y/o "message".' });
    if (!isConnected || !sock) return res.status(503).json({ ok:false, error:'WhatsApp no conectado.' });
    const jid = resolveJid(to);
    if (!jid) return res.status(400).json({ ok:false, error:`No se pudo resolver: "${to}"` });
    try {
        const messageId = generateMessageIDV2(sock.user?.id);
        sentByBridge.add(messageId);
        await sock.sendMessage(jid, { text: message }, { messageId });
        res.json({ ok:true, message:`Mensaje enviado` });
    } catch(e) { res.status(500).json({ ok:false, error:e.message }); }
});

app.post('/send_self', async (req, res) => {
    const { message } = req.body || {};
    if (!message) return res.status(400).json({ ok:false, error:'Falta "message".' });
    if (!isConnected || !sock) return res.status(503).json({ ok:false, error:'WhatsApp no conectado.' });
    if (!selfJid) return res.status(503).json({ ok:false, error:'JID propio desconocido.' });
    try {
        // Siempre enviar al JID base sin device suffix (número@s.whatsapp.net)
        // para que el mensaje vaya al "Saved Messages" estándar y no a un device específico
        const selfChatJid = jidNormalizedUser(selfJid);
        // El ID se guarda ANTES de enviar para que messages.upsert no lo procese como entrante
        const messageId = generateMessageIDV2(sock.user?.id);
        sentByBridge.add(messageId);
        await sock.sendMessage(selfChatJid, { text: message }, { messageId });
        pushLog('📤', `Enviado al chat propio (ID rastreado: ${messageId.substring(0,14)})`);
        res.json({ ok:true, message:'Mensaje enviado a tu chat contigo mismo' });
    } catch(e) { res.status(500).json({ ok:false, error:e.message }); }
});

app.post('/stop', (req, res) => {
    flushChats();
    saveContacts();
    res.json({ ok:true, message:'Bridge cerrándose...' });
    setTimeout(()=>process.exit(0), 600);
});

process.on('exit', () => { try { flushChats(); saveContacts(); } catch {} });

app.listen(PORT, '127.0.0.1', () => {
    console.log(`\n[Bridge] Escuchando en http://localhost:${PORT}`);
    console.log(`[Bridge] Pagina QR:    http://localhost:${PORT}/qr-page\n`);
    loadContacts();
    loadSelfLidFromCreds(); // intentar cargar LID antes de conectar
    startSocket();
});

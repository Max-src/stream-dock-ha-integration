// A fake `hass` for the card harness: implements hass.connection.subscribeMessage,
// hass.connection.sendMessagePromise, hass.callWS and the connection's
// ready / disconnected events, with the protocol.md section 5 messages.
// Never talks to a real Home Assistant.

import { layout293s, layoutAkp03e, layoutDashboard } from './layouts.mjs';

const KEY_PX = 85;
const BAND_PX = 80;

/* ---------------- Fake pictures ---------------- */

const KEY_LOOKS = [
  ['Lamp', 45], ['Music', 280], ['Mute', 0], ['Scene', 200], ['Fan', 170],
  ['Door', 25], ['Heat', 12], ['TV', 220], ['Blinds', 95], ['Night', 250],
  ['Coffee', 30], ['Away', 320], ['Cam', 190], ['Lock', 140], ['Vol', 60],
];

function canvas(size) {
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  return c;
}

function toBase64(c) {
  return c.toDataURL('image/jpeg', 0.86).replace(/^data:image\/jpeg;base64,/, '');
}

let hashCounter = 0;
function hashOf(text) {
  // Cheap stable hash for a description of the picture.
  let h = 0xcbf29ce4 ^ hashCounter;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619) >>> 0;
  return h.toString(16).padStart(8, '0') + text.length.toString(16).padStart(8, '0');
}

/** A numbered coloured square, as a key picture. */
export function keyPicture(n, scale, { title, hue, on = false } = {}) {
  const size = KEY_PX * scale;
  const c = canvas(size);
  const g = c.getContext('2d');
  const look = KEY_LOOKS[(n - 1) % KEY_LOOKS.length];
  const h = hue ?? look[1];
  const grad = g.createLinearGradient(0, 0, 0, size);
  grad.addColorStop(0, `hsl(${h} 70% ${on ? 58 : 44}%)`);
  grad.addColorStop(1, `hsl(${h} 75% ${on ? 38 : 24}%)`);
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  g.fillStyle = 'rgba(255,255,255,.95)';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.font = `700 ${Math.round(size * 0.42)}px Segoe UI, Arial, sans-serif`;
  g.fillText(String(n), size / 2, size * 0.42);
  g.font = `600 ${Math.round(size * 0.15)}px Segoe UI, Arial, sans-serif`;
  g.fillText(title ?? look[0], size / 2, size * 0.8);
  if (on) {
    g.fillStyle = '#fff';
    g.beginPath();
    g.arc(size * 0.84, size * 0.16, size * 0.06, 0, Math.PI * 2);
    g.fill();
  }
  const desc = `key${n}|${scale}|${title ?? look[0]}|${h}|${on}`;
  return { hash: hashOf(desc), data: toBase64(c) };
}

/** A band tile: small status picture. */
export function bandPicture(i, scale, text) {
  const size = BAND_PX * scale;
  const c = canvas(size);
  const g = c.getContext('2d');
  g.fillStyle = '#05070a';
  g.fillRect(0, 0, size, size);
  const colors = ['#4fc3f7', '#81c784', '#ffb74d'];
  g.strokeStyle = colors[i % 3];
  g.lineWidth = size * 0.07;
  g.beginPath();
  g.arc(size / 2, size / 2, size * 0.36, Math.PI * 0.75, Math.PI * (0.75 + 1.5 * (0.2 + 0.25 * i)));
  g.stroke();
  g.fillStyle = '#fff';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.font = `600 ${Math.round(size * 0.22)}px Segoe UI, Arial, sans-serif`;
  g.fillText(text, size / 2, size / 2);
  return { hash: hashOf(`band${i}|${scale}|${text}`), data: toBase64(c) };
}

/**
 * Alert pictures: one amber picture across all screen keys (gaps included),
 * cut into the part under each key, as the app sends them (protocol section 6).
 */
export function alertPictures(layout, scale, { title, message, color = [255, 166, 0] }) {
  const keys = layout.controls.filter((c) => c.type === 'key' && c.screen);
  const minX = Math.min(...keys.map((k) => k.x));
  const minY = Math.min(...keys.map((k) => k.y));
  const maxX = Math.max(...keys.map((k) => k.x + k.w));
  const maxY = Math.max(...keys.map((k) => k.y + k.h));
  const unit = KEY_PX * scale;
  const W = Math.round((maxX - minX) * unit);
  const H = Math.round((maxY - minY) * unit);
  const big = document.createElement('canvas');
  big.width = W;
  big.height = H;
  const g = big.getContext('2d');
  const [r, gr, b] = color;
  const grad = g.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.7);
  grad.addColorStop(0, `rgb(${r},${gr},${b})`);
  grad.addColorStop(1, `rgb(${Math.round(r * 0.7)},${Math.round(gr * 0.6)},${Math.round(b * 0.5)})`);
  g.fillStyle = grad;
  g.fillRect(0, 0, W, H);
  // A bell icon in the middle.
  const cx = W / 2;
  const cy = H / 2;
  const s = H * 0.2;
  g.fillStyle = '#1b1300';
  g.beginPath();
  g.moveTo(cx - s, cy + s * 0.6);
  g.quadraticCurveTo(cx - s * 0.8, cy - s * 0.9, cx, cy - s);
  g.quadraticCurveTo(cx + s * 0.8, cy - s * 0.9, cx + s, cy + s * 0.6);
  g.closePath();
  g.fill();
  g.beginPath();
  g.arc(cx, cy + s * 0.8, s * 0.25, 0, Math.PI * 2);
  g.fill();
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.font = `700 ${Math.round(H * 0.13)}px Segoe UI, Arial, sans-serif`;
  g.fillText(title, cx, H * 0.15);
  g.font = `500 ${Math.round(H * 0.075)}px Segoe UI, Arial, sans-serif`;
  g.fillText(message, cx, H * 0.86);

  const out = {};
  for (const k of keys) {
    const c = canvas(KEY_PX * scale);
    c.getContext('2d').drawImage(big, (k.x - minX) * unit, (k.y - minY) * unit, k.w * unit, k.h * unit,
      0, 0, c.width, c.height);
    out[k.name] = { hash: hashOf(`alert|${title}|${k.name}|${scale}`), data: toBase64(c) };
  }
  return out;
}

/* ---------------- Fake integration ---------------- */

function padState(id, kind, model, name, layout, extra = {}) {
  return {
    id, kind, model, name,
    connected: true, screen_on: true, brightness: 60,
    mini_monitor: kind === 'dashboard' ? null : false,
    profile: { id: '51ac0e9f7d2b8346', name: 'Home' },
    profiles: [{ id: '51ac0e9f7d2b8346', name: 'Home', pages: 3 }],
    page: 1, pages: 3, look: 'c2a91f0e33b7d455', alert: false,
    layout, ...extra,
  };
}

export function createMockHass({ log = () => {}, latency = 40 } = {}) {
  const pads = new Map();
  const addPad = (padId, deviceId, pc, state, empty = []) => {
    pads.set(padId, {
      padId, deviceId, pc, online: true, state, empty: new Set(empty),
      toggles: new Set(), titles: {}, alert: null, subs: new Set(), errors: {}, scale: 2,
    });
  };
  addPad('9d04e1b7a2c35f18', 'dev_293s', 'DESKTOP-MAX',
    padState('9d04e1b7a2c35f18', 'stream_dock_293s', 'Stream Dock 293S', 'Desk pad', layout293s), ['key_14']);
  addPad('2b7e91c4d05a3f68', 'dev_akp03e', 'DESKTOP-MAX',
    padState('2b7e91c4d05a3f68', 'akp03e', 'AKP03E', 'Side knobs', layoutAkp03e,
      { profile: { id: 'aa11', name: 'Media' }, pages: 1 }));
  addPad('f00dfeed12345678', 'dev_dash', 'LAPTOP-OFFICE',
    padState('f00dfeed12345678', 'dashboard', 'Dashboard pad', 'Living room', layoutDashboard,
      { profile: { id: 'bb22', name: 'Evening' }, page: 2, pages: 4 }), ['key_8']);

  // Some press errors, as the integration returns them (protocol 5.3).
  pads.get('9d04e1b7a2c35f18').errors.key_5 = { code: 'failed', message: 'That key opens programs, which Home Assistant isn’t allowed to press' };
  pads.get('2b7e91c4d05a3f68').errors.button_3 = { code: 'control_off', message: 'Control is off' };
  pads.get('f00dfeed12345678').errors.key_4 = { code: 'unauthorized', message: 'Unauthorized' };

  function picturesFor(p, scale) {
    const out = {};
    if (p.alert) Object.assign(out, alertPictures(p.state.layout, scale, p.alert));
    for (const c of p.state.layout.controls) {
      if (!c.screen || out[c.name]) continue;
      if (p.empty.has(c.name)) { out[c.name] = null; continue; }
      if (c.type === 'band') {
        const i = Number(c.name.split('_')[1]) - 1;
        out[c.name] = bandPicture(i, scale, ['12%', '48%', '5%'][i] || '');
      } else {
        const n = Number(c.name.split('_')[1]);
        const hue = (KEY_LOOKS[(n - 1) % KEY_LOOKS.length][1] + (p.state.page - 1) * 47) % 360;
        out[c.name] = keyPicture(n, scale, { on: p.toggles.has(c.name), title: p.titles[c.name], hue });
      }
    }
    return out;
  }

  const listeners = { ready: new Set(), disconnected: new Set() };
  const connection = {
    connected: true,
    addEventListener(type, cb) { listeners[type]?.add(cb); },
    removeEventListener(type, cb) { listeners[type]?.delete(cb); },
    async sendMessagePromise(msg) { return handleCommand(msg); },
    async subscribeMessage(callback, msg, options) {
      log('send', msg, options);
      await delay(latency);
      if (!connection.connected) throw { code: 'not_connected', message: 'Not connected' };
      if (msg.type !== 'stream_dock_ha/watch') throw { code: 'unknown_command', message: 'Unknown command' };
      const p = pads.get(msg.pad_id);
      if (!p) throw { code: 'not_found', message: 'Unknown pad' };
      const scale = msg.scale ?? 2;
      const sub = { callback, scale };
      p.subs.add(sub);
      setTimeout(() => {
        if (!p.subs.has(sub)) return;
        emit(sub, { kind: 'pad', online: p.online, pc: p.pc, pad: p.state });
        emit(sub, { kind: 'pictures', complete: true, scale, pictures: picturesFor(p, scale) });
      }, latency);
      return async () => {
        log('unsubscribe', { pad_id: msg.pad_id, scale });
        p.subs.delete(sub);
      };
    },
  };

  function emit(sub, event) {
    log('event', event.kind === 'pictures'
      ? { kind: 'pictures', complete: event.complete, scale: event.scale, names: Object.keys(event.pictures) }
      : { kind: event.kind, online: event.online, pc: event.pc, pad: event.pad?.name });
    sub.callback(event);
  }

  function sendPad(p) {
    p.state = { ...p.state, look: Math.random().toString(16).slice(2, 18) };
    for (const sub of p.subs) emit(sub, { kind: 'pad', online: p.online, pc: p.pc, pad: p.state });
  }

  function sendPictures(p, names, complete = false) {
    for (const sub of p.subs) {
      const all = picturesFor(p, sub.scale);
      const pictures = complete ? all : Object.fromEntries(names.map((n) => [n, all[n] ?? null]));
      emit(sub, { kind: 'pictures', complete, scale: sub.scale, pictures });
    }
  }

  async function handleCommand(msg) {
    log('send', msg);
    await delay(latency);
    if (!connection.connected) throw { code: 'not_connected', message: 'Lost connection' };
    if (msg.type === 'stream_dock_ha/pads') {
      return { pads: [...pads.values()].map((p) => ({
        pad_id: p.padId, name: p.state.name, pc: p.pc, kind: p.state.kind, online: p.online, device_id: p.deviceId,
      })) };
    }
    if (msg.type === 'stream_dock_ha/press') {
      const p = pads.get(msg.pad_id);
      if (!p) throw { code: 'not_found', message: 'Unknown pad' };
      if (!p.online) throw { code: 'offline', message: 'The PC is offline' };
      const control = p.state.layout.controls.find((c) => c.name === msg.control);
      if (!control) throw { code: 'failed', message: `No control ${msg.control}` };
      if (p.alert) { p.alert = null; p.state = { ...p.state, alert: false }; sendPad(p); sendPictures(p, [], true); return {}; }
      if (!p.state.screen_on) { p.state = { ...p.state, screen_on: true }; sendPad(p); return {}; }
      if (p.errors[msg.control]) throw p.errors[msg.control];
      if (control.type === 'key') {
        if (p.toggles.has(control.name)) p.toggles.delete(control.name); else p.toggles.add(control.name);
        sendPictures(p, [control.name]);
      }
      if (control.type === 'knob_left' || control.type === 'knob_right') {
        const k = p.state.layout.controls.find((c) => c.name === 'key_1');
        const v = (p.vol ?? 50) + (control.type === 'knob_left' ? -5 : 5);
        p.vol = Math.max(0, Math.min(100, v));
        p.titles[k.name] = `Vol ${p.vol}`;
        sendPictures(p, [k.name]);
      }
      return {};
    }
    throw { code: 'unknown_command', message: 'Unknown command' };
  }

  const hass = {
    connection,
    states: {},
    entities: {
      'select.desk_pad_profile': { entity_id: 'select.desk_pad_profile', platform: 'stream_dock_ha', device_id: 'dev_293s' },
    },
    callWS: (msg) => handleCommand(msg),
  };

  // Controls for the harness and scenarios.
  const control = {
    pads,
    setOnline(padId, online) { const p = pads.get(padId); p.online = online; sendPad(p); },
    setConnected(padId, connected) { const p = pads.get(padId); p.state = { ...p.state, connected }; sendPad(p); },
    setScreen(padId, on) { const p = pads.get(padId); p.state = { ...p.state, screen_on: on }; sendPad(p); },
    setMiniMonitor(padId, on) { const p = pads.get(padId); p.state = { ...p.state, mini_monitor: on }; sendPad(p); },
    showAlert(padId, alert) {
      const p = pads.get(padId); p.alert = alert; p.state = { ...p.state, alert: true };
      sendPad(p); sendPictures(p, [], true);
    },
    clearAlert(padId) { const p = pads.get(padId); p.alert = null; p.state = { ...p.state, alert: false }; sendPad(p); sendPictures(p, [], true); },
    updatePicture(padId, name, title) {
      const p = pads.get(padId); p.empty.delete(name); p.titles[name] = title; p.toggles.add(name); sendPictures(p, [name]);
    },
    clearPicture(padId, name) { const p = pads.get(padId); p.empty.add(name); sendPictures(p, [name]); },
    nextPage(padId) {
      const p = pads.get(padId); p.state = { ...p.state, page: (p.state.page % p.state.pages) + 1 };
      hashCounter++; sendPad(p); sendPictures(p, [], true);
    },
    dropConnection() {
      connection.connected = false;
      for (const p of pads.values()) p.subs.clear(); // the socket took them
      listeners.disconnected.forEach((cb) => cb(connection, 'disconnected'));
    },
    restoreConnection() {
      connection.connected = true;
      listeners.ready.forEach((cb) => cb(connection, 'ready'));
    },
    subscriberCount(padId) { return pads.get(padId).subs.size; },
  };

  return { hass, control };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

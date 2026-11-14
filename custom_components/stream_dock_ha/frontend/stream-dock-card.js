/*
 * Stream Dock cards:
 * - custom:stream-dock-card, a live "virtual stream dock" for one pad;
 * - custom:stream-dock-key-card, one key of it, or a few;
 * - custom:stream-dock-screen-card, its Mini Monitor as one screen.
 *
 * Pressing a key here presses the real one. Served by the stream_dock_ha
 * integration; see docs/protocol.md, sections 3.2, 3.4, 5 and 6.
 *
 * One self-contained ES module: no build step, no network imports.
 */

const CARD_TYPE = 'stream-dock-card';
const KEY_CARD_TYPE = 'stream-dock-key-card';
const SCREEN_CARD_TYPE = 'stream-dock-screen-card';
const CARD_VERSION = '0.1.12';

/** Picture sizes at scale 1 (protocol 3.4). */
const KEY_PX = 85;
/** Room around the controls on the pad body, in key units, when the app doesn't say. */
const BODY_MARGIN = 0.3;
/** A Mini Monitor picture older than this is taken off the keys, in ms. */
const FRAME_STALE_MS = 3000;
/** How long an error message stays, in ms. */
const TOAST_MS = 3000;
/** Shortest visible press, in ms, so a quick tap still shows. */
const MIN_PRESS_MS = 110;

const KNOB_PARTS = { knob_left: 'left', knob_right: 'right', knob_press: 'press' };

/** Layouts seen per pad, so a re-created card draws at once and picks its scale right. */
const layoutCache = new Map();

/* ------------------------------------------------------------------ */
/* Pure logic (exported for the unit tests in frontend-dev/)           */
/* ------------------------------------------------------------------ */

function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** A scale the protocol accepts: 1, 2 or 3. */
export function clampScale(value, fallback = 2) {
  const n = Math.round(Number(value));
  if (!Number.isFinite(n)) return fallback;
  return Math.min(3, Math.max(1, n));
}

/**
 * The picture scale for keys drawn `keyPx` CSS pixels wide on a screen with
 * `dpr` device pixels per CSS pixel. Pictures are 85 px per scale step; a
 * little upscaling (up to 20 %) is accepted before asking for the next step.
 */
export function chooseScale(keyPx, dpr = 1) {
  const k = Number(keyPx);
  if (!Number.isFinite(k) || k <= 0) return 2;
  const ratio = Number(dpr) > 0 ? Number(dpr) : 1;
  return clampScale(Math.ceil((k * ratio) / KEY_PX - 0.2));
}

/** Key size in CSS pixels when a pad body of `bodyUnits` key units fills `widthPx`. */
export function keySizePx(widthPx, bodyUnits) {
  const w = Number(widthPx);
  const u = Number(bodyUnits);
  if (!(w > 0) || !(u > 0)) return 0;
  return w / u;
}

/**
 * How the pad's front and keys look, from its PadState's `body` (protocol
 * 3.2), so the card draws it as the app does. An app that doesn't send it gets
 * the card's own dark pad. `edge` and `corner` are in key units; key and band
 * corners are parts of their width, 0.5 being round.
 */
export function bodyLook(body) {
  const b = body && typeof body === 'object' ? body : {};
  const part = (value, fallback, most) => {
    const n = Number(value);
    return value != null && Number.isFinite(n) && n >= 0 ? Math.min(most, n) : fallback;
  };
  const rgb = Array.isArray(b.front) && b.front.length === 3 && b.front.every((v) => Number.isFinite(Number(v)))
    ? b.front.map((v) => Math.min(255, Math.max(0, Math.round(Number(v)))))
    : null;
  return {
    front: rgb ? `rgb(${rgb.join(', ')})` : null,
    // A see-through front: the keys float on the card.
    clear: 'front' in b && !rgb,
    light: !!rgb && rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114 > 150,
    edge: part(b.edge, BODY_MARGIN, 2),
    corner: part(b.corner, 0.32, 2),
    keyCorner: part(b.key_corner, 0.11, 0.5),
    bandCorner: part(b.band_corner, 0.09, 0.5),
  };
}

/**
 * Turns a protocol Layout into what the card draws: the pad body size in key
 * units (controls plus a margin) and one item per drawn thing, with its box in
 * key units and in percent of the body. A knob's three parts become one item.
 */
export function computeLayout(layout, margin = BODY_MARGIN) {
  const controls = layout && Array.isArray(layout.controls) ? layout.controls : [];
  let minX = 0;
  let minY = 0;
  let maxX = Math.max(0, num(layout && layout.width));
  let maxY = Math.max(0, num(layout && layout.height));
  const items = [];
  const knobs = new Map();

  for (const c of controls) {
    if (!c || typeof c.name !== 'string' || !c.name) continue;
    const x = num(c.x);
    const y = num(c.y);
    const w = num(c.w, 1) > 0 ? num(c.w, 1) : 1;
    const h = num(c.h, 1) > 0 ? num(c.h, 1) : 1;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + w);
    maxY = Math.max(maxY, y + h);

    const part = KNOB_PARTS[c.type];
    if (part) {
      const group = typeof c.group === 'string' && c.group
        ? c.group
        : c.name.replace(/_(left|right|press)$/, '');
      let knob = knobs.get(group);
      if (!knob) {
        knob = { kind: 'knob', id: `knob:${group}`, group, x, y, w, h, parts: {} };
        knobs.set(group, knob);
        items.push(knob);
      }
      knob.parts[part] = { name: c.name, press: c.press !== false };
      continue;
    }

    let kind = c.type;
    if (kind !== 'key' && kind !== 'band' && kind !== 'button') {
      // A type from a later protocol: draw it as a key if it shows a picture.
      kind = c.screen ? 'key' : 'button';
    }
    const screen = typeof c.screen === 'boolean' ? c.screen : kind !== 'button';
    items.push({ kind, id: c.name, name: c.name, x, y, w, h, screen, press: c.press !== false });
  }

  const width = maxX - minX + 2 * margin;
  const height = maxY - minY + 2 * margin;
  for (const item of items) {
    item.left = item.x - minX + margin;
    item.top = item.y - minY + margin;
    item.box = {
      left: (item.left / width) * 100,
      top: (item.top / height) * 100,
      width: (item.w / width) * 100,
      height: (item.h / height) * 100,
    };
  }
  // The band's tiles share one black side screen, as on the 293S.
  const bands = items.filter((item) => item.kind === 'band');
  let strip = null;
  if (bands.length) {
    const left = Math.min(...bands.map((b) => b.left));
    const top = Math.min(...bands.map((b) => b.top));
    const right = Math.max(...bands.map((b) => b.left + b.w));
    const bottom = Math.max(...bands.map((b) => b.top + b.h));
    strip = {
      w: Math.min(...bands.map((b) => b.w)),
      box: {
        left: (left / width) * 100,
        top: (top / height) * 100,
        width: ((right - left) / width) * 100,
        height: ((bottom - top) / height) * 100,
      },
    };
  }
  return {
    version: layout && layout.version != null ? String(layout.version) : null,
    width,
    height,
    items,
    strip,
  };
}

/**
 * A pad's Layout and body as the card draws them, with a version that changes
 * when either the layout or the room round it does.
 */
export function laidOut(layout, body) {
  const look = bodyLook(body);
  const computed = computeLayout(layout, look.edge);
  const version = layout && layout.version != null
    ? String(layout.version)
    : JSON.stringify((layout && layout.controls) || []);
  computed.version = `${version}@${look.edge}`;
  computed.look = look;
  return computed;
}

function normalisePicture(raw) {
  if (!raw || typeof raw !== 'object' || typeof raw.data !== 'string' || !raw.data) return null;
  return { hash: raw.hash != null ? String(raw.hash) : null, data: raw.data };
}

function samePicture(a, b) {
  if (!a || !b) return !a && !b;
  if (a.hash != null && b.hash != null) return a.hash === b.hash;
  return a.data === b.data;
}

/**
 * Applies one `pictures` event to the pictures held so far.
 * `prev` is a Map of control name to { hash, data }; empty keys are absent.
 * `complete: true` replaces the whole set (anything absent is empty);
 * otherwise the event is merged in, `null` meaning empty.
 * Returns the new Map and the names whose picture actually changed.
 */
/**
 * Where each control's part of a Mini Monitor frame is (protocol 3.6), as CSS
 * background sizes and positions, so every key shows its own part of the one
 * picture. Controls without a sane part are left out.
 */
export function frameParts(frame) {
  const parts = new Map();
  const W = num(frame && frame.width);
  const H = num(frame && frame.height);
  const tiles = frame && Array.isArray(frame.tiles) ? frame.tiles : [];
  if (!(W > 0) || !(H > 0)) return parts;
  const at = (offset, size, whole) => (whole > size ? (offset / (whole - size)) * 100 : 0);
  for (const t of tiles) {
    if (!t || typeof t.name !== 'string') continue;
    const x = num(t.x); const y = num(t.y); const w = num(t.w); const h = num(t.h);
    if (!(w > 0) || !(h > 0) || x < 0 || y < 0 || x + w > W || y + h > H) continue;
    parts.set(t.name, {
      size: `${(W / w) * 100}% ${(H / h) * 100}%`,
      position: `${at(x, w, W)}% ${at(y, h, H)}%`,
    });
  }
  return parts;
}

/**
 * The box, in percent of the pad body, that one Mini Monitor picture covers
 * when it goes across the gaps: every control that has a part of it.
 */
export function frameBox(layout, frame) {
  const names = new Set((frame && Array.isArray(frame.tiles) ? frame.tiles : []).map((t) => t && t.name));
  const boxes = ((layout && layout.items) || []).filter((item) => names.has(item.name)).map((item) => item.box);
  if (!boxes.length) return null;
  const left = Math.min(...boxes.map((b) => b.left));
  const top = Math.min(...boxes.map((b) => b.top));
  const right = Math.max(...boxes.map((b) => b.left + b.width));
  const bottom = Math.max(...boxes.map((b) => b.top + b.height));
  return { left, top, width: right - left, height: bottom - top };
}

export function mergePictures(prev, event) {
  const before = prev instanceof Map ? prev : new Map();
  const complete = !!(event && event.complete);
  const incoming = event && event.pictures && typeof event.pictures === 'object' ? event.pictures : {};
  const next = complete ? new Map() : new Map(before);
  const changed = new Set();

  if (complete) {
    for (const [name, pic] of before) {
      if (pic && !Object.prototype.hasOwnProperty.call(incoming, name)) changed.add(name);
    }
  }
  for (const name of Object.keys(incoming)) {
    const pic = normalisePicture(incoming[name]);
    const old = before.get(name) || null;
    if (pic) next.set(name, pic);
    else next.delete(name);
    if (!samePicture(old, pic)) changed.add(name);
  }
  return { pictures: next, changed: [...changed] };
}

/** A control name a person can read: key_3 -> "Key 3", top_knob_left -> "Top knob, turn left". */
export function humanizeControl(name) {
  const text = String(name || '');
  const knob = /^(.*)_knob_(left|right|press)$/.exec(text);
  if (knob) {
    const what = { left: 'turn left', right: 'turn right', press: 'press' }[knob[2]];
    return `${capitalise(knob[1].replace(/_/g, ' '))} knob, ${what}`;
  }
  return capitalise(text.replace(/_/g, ' ').trim());
}

function capitalise(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** The short message shown when a press fails (protocol 5.3 error codes). */
export function pressErrorText(err) {
  const code = err && typeof err === 'object' ? err.code : undefined;
  const message = err && typeof err === 'object' && typeof err.message === 'string'
    ? err.message.trim()
    : typeof err === 'string' ? err.trim() : '';
  switch (code) {
    case 'offline': return 'The PC is offline';
    case 'control_off': return "Home Assistant control is off in the app";
    case 'unauthorized': return 'Only administrators can press keys here';
    case 'not_found': return 'This pad is no longer known';
    case 'failed': return message || 'The PC refused the press';
    default: return message || (code ? String(code) : "Couldn't press the key");
  }
}

/**
 * What covers the pad, if anything. `block` means presses are not sent;
 * `dim` darkens the pictures. Only the most important one is shown. With
 * Mini Monitor's `frames` showing, the card needs no word about it.
 */
export function padOverlay({ online = true, linkDown = false, pad = null, frames = false, frameError = false } = {}) {
  if (linkDown) return { kind: 'link', text: 'Reconnecting to Home Assistant…', sub: '', dim: true, block: true };
  if (online === false) return { kind: 'offline', text: 'PC offline', sub: 'Showing the last pictures', dim: true, block: true };
  if (!pad) return null;
  if (pad.connected === false) return { kind: 'unplugged', text: 'Pad unplugged', sub: 'Keys still run on the PC', dim: false, block: false };
  if (pad.screen_on === false) return { kind: 'screen_off', text: 'Screen off — press to wake', sub: '', dim: true, block: false };
  if (pad.mini_monitor === true && !frames) {
    return frameError
      ? { kind: 'mini_monitor', text: 'Mini Monitor is on', sub: "Its pictures arrive but this browser can't show them", dim: false, block: false }
      : { kind: 'mini_monitor', text: 'Mini Monitor is on', sub: 'Waiting for its pictures', dim: false, block: false };
  }
  return null;
}

/** How long to wait before retry number `attempt` (0 first) of a failed watch or lookup. */
export const RETRY_DELAYS_MS = [2000, 5000, 15000, 30000];
export function retryDelayMs(attempt) {
  const n = Number.isFinite(attempt) && attempt > 0 ? Math.floor(attempt) : 0;
  return RETRY_DELAYS_MS[Math.min(n, RETRY_DELAYS_MS.length - 1)];
}

/** The pad_id a `stream_dock_ha/pads` result gives for a config's device_id, or null. */
export function resolvePadId(config, padsResult) {
  if (!config) return null;
  if (config.device_id) {
    const pads = padsResult && Array.isArray(padsResult.pads) ? padsResult.pads : [];
    const pad = pads.find((p) => p && p.device_id === config.device_id);
    return pad && pad.pad_id ? pad.pad_id : null;
  }
  return config.pad_id || null;
}

/** The header's right-hand text: "Home · 2 / 3". */
export function headerDetail(pad, showProfile) {
  if (!pad || !showProfile) return '';
  const parts = [];
  if (pad.profile && pad.profile.name) parts.push(pad.profile.name);
  if (num(pad.pages) > 1) parts.push(`${num(pad.page, 1)} / ${num(pad.pages)}`);
  return parts.join(' · ');
}

/** Normalised card config; throws on values HA should report as a config error. */
export function normaliseConfig(config) {
  if (!config || typeof config !== 'object') throw new Error('Invalid configuration');
  const out = { ...config };
  if (out.scale != null && out.scale !== '') {
    const n = Number(out.scale);
    if (!Number.isFinite(n) || n < 1 || n > 3) throw new Error('scale must be 1, 2 or 3');
    out.scale = clampScale(n);
  } else {
    delete out.scale;
  }
  // The title shows when there is one: no separate switch. An old card's
  // show_name is dropped.
  delete out.show_name;
  out.show_profile = out.show_profile !== false;
  out.show_card_background = out.show_card_background !== false;
  if (typeof out.title !== 'string' || !out.title.trim()) delete out.title;
  // Extras, each one can be turned off or on in the editor.
  out.tilt = out.tilt === true;
  out.show_page_buttons = out.show_page_buttons === true;
  out.press_effect = out.press_effect !== false;
  out.show_pad_presses = out.show_pad_presses !== false;
  // Cards saved before 0.1.2 may still say whether to vibrate.
  delete out.haptic;
  return out;
}

/**
 * The controls a one-key card shows, from what the person typed: a key
 * number (3), several (1, 2, 6-7), or control names (key_3, band_1,
 * button_2, top_knob). Keeps their order and drops repeats.
 */
export function parseControls(value) {
  const parts = Array.isArray(value) ? value : String(value == null ? '' : value).split(/[\s,;]+/);
  const out = [];
  const add = (name) => { if (name && !out.includes(name)) out.push(name); };
  for (const raw of parts) {
    const text = String(raw == null ? '' : raw).trim().toLowerCase();
    if (!text) continue;
    const range = /^(\d+)\s*-\s*(\d+)$/.exec(text);
    if (range) {
      const [a, b] = [Number(range[1]), Number(range[2])];
      for (let n = Math.min(a, b); n <= Math.max(a, b) && n - Math.min(a, b) < 64; n++) if (n > 0) add(`key_${n}`);
    } else if (/^\d+$/.test(text)) {
      if (Number(text) > 0) add(`key_${Number(text)}`);
    } else if (/^[a-z0-9_]+$/.test(text)) {
      add(text);
    }
  }
  return out;
}

/** The gap between controls a key card puts side by side, in key units, as on the 293S. */
const ROW_GAP = 0.25;

/**
 * A Layout with only the controls `names` asks for. A knob is asked for by its
 * group (top_knob) or any of its parts. Null when none of them is in the layout.
 *
 * By default they're put side by side in the order asked for, `perRow` to a
 * row (0: all in one), each centred in its row. With `asOnPad` they keep
 * where they are on the pad, moved so they start at 0, 0.
 */
export function focusLayout(layout, names, { asOnPad = false, perRow = 0 } = {}) {
  const wanted = new Set(names || []);
  const controls = (layout && Array.isArray(layout.controls) ? layout.controls : []).filter((c) => {
    if (!c || typeof c.name !== 'string') return false;
    if (wanted.has(c.name)) return true;
    if (!KNOB_PARTS[c.type]) return false;
    const group = typeof c.group === 'string' && c.group ? c.group : c.name.replace(/_(left|right|press)$/, '');
    return wanted.has(group) || ['left', 'right', 'press'].some((part) => wanted.has(`${group}_${part}`));
  });
  if (!controls.length) return null;
  const moved = asOnPad ? placedAsOnPad(controls) : placedInRows(controls, [...wanted], perRow);
  return {
    version: `${layout && layout.version != null ? layout.version : ''}:${[...wanted].join(',')}:${asOnPad ? 'pad' : `row${perRow}`}`,
    width: Math.max(...moved.map((c) => c.x + (num(c.w, 1) > 0 ? num(c.w, 1) : 1))),
    height: Math.max(...moved.map((c) => c.y + (num(c.h, 1) > 0 ? num(c.h, 1) : 1))),
    controls: moved,
  };
}

function placedAsOnPad(controls) {
  const minX = Math.min(...controls.map((c) => num(c.x)));
  const minY = Math.min(...controls.map((c) => num(c.y)));
  return controls.map((c) => ({ ...c, x: num(c.x) - minX, y: num(c.y) - minY }));
}

/** A knob's three parts move as one; everything else on its own. */
function controlUnit(c) {
  if (!KNOB_PARTS[c.type]) return c.name;
  return typeof c.group === 'string' && c.group ? c.group : c.name.replace(/_(left|right|press)$/, '');
}

function placedInRows(controls, wanted, perRow) {
  const units = new Map();
  for (const c of controls) {
    const unit = controlUnit(c);
    if (!units.has(unit)) units.set(unit, []);
    units.get(unit).push(c);
  }
  // The order asked for: a knob by the first of its group or parts named.
  const rank = (unit) => {
    const at = wanted.findIndex((name) => name === unit || name.startsWith(`${unit}_`));
    return at < 0 ? wanted.length : at;
  };
  const ordered = [...units.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
  const size = (n, fallback) => (num(n, fallback) > 0 ? num(n, fallback) : fallback);
  const across = Math.max(0, Math.floor(num(perRow))) || ordered.length;
  const out = [];
  let y = 0;
  for (let start = 0; start < ordered.length; start += across) {
    const row = ordered.slice(start, start + across).map(([, parts]) => ({
      parts, w: size(parts[0].w, 1), h: size(parts[0].h, 1),
    }));
    const tall = Math.max(...row.map((u) => u.h));
    let x = 0;
    for (const u of row) {
      for (const c of u.parts) out.push({ ...c, x, y: y + (tall - u.h) / 2 });
      x += u.w + ROW_GAP;
    }
    y += tall + ROW_GAP;
  }
  return out;
}

/** The name Home Assistant shows for a pad's device, for a new card's title. */
export function padNameOf(hass, deviceId) {
  const device = hass && hass.devices && deviceId ? hass.devices[deviceId] : null;
  return device ? String(device.name_by_user || device.name || '') : '';
}

/**
 * The pad's own entities, found by its device and their translation keys:
 * the profile select, the page number, the press event and the Mini Monitor
 * switch. Any can be missing.
 */
export function padEntities(hass, deviceId) {
  const found = { profile: null, page: null, press: null, mini_monitor: null };
  if (!hass || !hass.entities || !deviceId) return found;
  const domains = { profile: 'select', page: 'number', press: 'event', mini_monitor: 'switch' };
  for (const entry of Object.values(hass.entities)) {
    if (!entry || entry.device_id !== deviceId || entry.platform !== 'stream_dock_ha') continue;
    const id = String(entry.entity_id || '');
    for (const [key, domain] of Object.entries(domains)) {
      if (found[key] || !id.startsWith(`${domain}.`)) continue;
      if (entry.translation_key ? entry.translation_key === key : id.endsWith(`_${key}`)) found[key] = id;
    }
  }
  return found;
}

/** The control a press event entity's state names, or null for none or a dismissal. */
export function pressedControl(stateObj) {
  if (!stateObj || !stateObj.attributes) return null;
  const type = stateObj.attributes.event_type;
  if (typeof type !== 'string' || !type || type === 'dismissed') return null;
  return { control: type, at: String(stateObj.state || ''), source: stateObj.attributes.source || null };
}

/* ------------------------------------------------------------------ */
/* The element                                                          */
/* ------------------------------------------------------------------ */

const STYLE = `
:host { display: block; }
ha-card { display: block; overflow: hidden; height: 100%; box-sizing: border-box; }
ha-card:not(:defined) {
  background: var(--ha-card-background, var(--card-background-color, #1c1c1c));
  border-radius: var(--ha-card-border-radius, 12px);
  border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
  box-shadow: var(--ha-card-box-shadow, none);
  color: var(--primary-text-color);
}
.wrap { padding: 12px; position: relative; }
/* No card background: no frame, and the pad takes all the room. */
ha-card.plain { background: transparent; border: none; box-shadow: none; overflow: visible; border-radius: 0; }
ha-card.plain .wrap { padding: 0; }
ha-card.plain .header { padding: 0 2px 8px; }
.header {
  display: flex; align-items: baseline; gap: 8px; padding: 0 4px 10px;
  font-family: var(--ha-card-header-font-family, inherit);
  color: var(--primary-text-color);
}
.header[hidden] { display: none; }
.name { font-size: 16px; font-weight: 500; flex: 1 1 auto; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.detail { font-size: 13px; color: var(--secondary-text-color); white-space: nowrap; flex: 0 0 auto; }
.chip { font-size: 11px; font-weight: 600; letter-spacing: .02em; padding: 1px 7px; border-radius: 9px;
  background: var(--warning-color, #ffa600); color: #1a1200; flex: 0 0 auto; }
.chip[hidden] { display: none; }

.frame {
  position: relative; width: 100%; container-type: inline-size;
  --bw: 7; --bh: 4; --pad-r: .32; --key-r: .11; --band-r: .09;
  aspect-ratio: var(--bw) / var(--bh);
  --u: calc(100cqw / var(--bw));
  -webkit-tap-highlight-color: transparent;
  user-select: none; -webkit-user-select: none;
}
.frame[hidden] { display: none; }
.pad {
  position: absolute; inset: 0;
  border-radius: calc(var(--u) * var(--pad-r));
  background:
    radial-gradient(120% 90% at 30% 0%, rgba(255,255,255,.07), rgba(255,255,255,0) 60%),
    linear-gradient(180deg, #24262a 0%, #17181b 100%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08), inset 0 -2px 6px rgba(0,0,0,.5),
    0 2px 6px rgba(0,0,0,.25);
  transition: filter .25s ease;
}
/* The front's colour from the app, lit a little from the top. */
.pad.painted {
  background:
    radial-gradient(120% 90% at 30% 0%, rgba(255,255,255,.09), rgba(255,255,255,0) 60%),
    var(--front);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.14), inset 0 -2px 6px rgba(0,0,0,.16),
    0 1px 2px rgba(0,0,0,.18), 0 2px 8px rgba(0,0,0,.14);
}
/* A light front, like the white 293S: flat, with a fine edge so it still
   stands out on a light page, and only a faint shadow under it and its keys. */
.pad.painted.light {
  background: var(--front);
  box-shadow: 0 0 0 1px rgba(0,0,0,.09), 0 1px 3px rgba(0,0,0,.07);
}
.pad.light .key, .pad.light .strip { box-shadow: 0 0 0 1px rgba(0,0,0,.05); }
/* No front: only an outline shows where the pad is, as in the app. */
.pad.clear {
  background: none; box-shadow: none;
  outline: 1px solid var(--divider-color, rgba(127,127,127,.35)); outline-offset: -1px;
}
.pad.dim .ctl, .pad.dim .knob { filter: brightness(.38) saturate(.6); }
.pad.dim { }

.ctl, .knob { position: absolute; box-sizing: border-box; transition: transform .14s ease, filter .25s ease; }
.ctl[data-control], .knob [data-control] { cursor: pointer; touch-action: manipulation; }
.ctl:focus-visible, .knob [data-control]:focus-visible {
  outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; z-index: 2;
}
.ctl:focus, .knob [data-control]:focus { outline: none; }
.ctl:focus-visible, .knob [data-control]:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); }

.key, .band {
  border-radius: calc(var(--key-r) * 100%);
  background: #000;
  box-shadow: 0 calc(var(--u) * .015) calc(var(--u) * .04) rgba(0,0,0,.35);
  overflow: hidden;
}
.band { border-radius: calc(var(--band-r) * 100%); box-shadow: none; }
.strip {
  position: absolute; background: #000; pointer-events: none;
  border-radius: calc(var(--u) * var(--band-r) * var(--sw, .82));
  box-shadow: 0 calc(var(--u) * .015) calc(var(--u) * .04) rgba(0,0,0,.35);
}
.key img, .band img {
  position: absolute; inset: 0; width: 100%; height: 100%; display: block;
  object-fit: cover; pointer-events: none; -webkit-user-drag: none;
}
.key:not(.pic) img, .band:not(.pic) img { display: none; }
/* Mini Monitor: each key shows its part of one picture. */
.mm { position: absolute; inset: 0; background-image: var(--mm); background-repeat: no-repeat;
  pointer-events: none; display: none; }
.pad.mini .mm { display: block; }
/* Across the gaps: one picture, square-edged, in the screen's proportions. */
.mm-whole { position: absolute; display: none; pointer-events: none; z-index: 1;
  background-image: var(--mm); background-repeat: no-repeat; background-size: contain; background-position: center; }
.pad.mini.seamless .mm-whole { display: block; }
.pad.mini.seamless .mm { display: none; }
.pad.mini.seamless .covered { visibility: hidden; }
.key.down { transform: scale(.92); filter: brightness(.82); transition-duration: .05s; }

/* Press effect: the key sinks and a soft light spreads from where it was hit. */
.fx .key.down, .fx .band.down { transform: scale(.9) translateY(calc(var(--u) * .02)); }
.ripple { position: absolute; border-radius: 50%; pointer-events: none; z-index: 2;
  width: 160%; aspect-ratio: 1; left: var(--rx, 50%); top: var(--ry, 50%);
  background: radial-gradient(circle, rgba(255,255,255,.55) 0%, rgba(255,255,255,.18) 40%, rgba(255,255,255,0) 70%);
  transform: translate(-50%, -50%) scale(.1); opacity: 1; animation: ripple .45s ease-out forwards; }
@keyframes ripple { to { transform: translate(-50%, -50%) scale(1); opacity: 0; } }

/* A press made elsewhere (the pad, a pad on screen, an automation): a ring round the key. */
.ctl.lit::after, .knob.lit::after {
  content: ''; position: absolute; inset: calc(var(--u) * -.05); border-radius: inherit; pointer-events: none;
  box-shadow: 0 0 0 calc(var(--u) * .035) var(--primary-color, #03a9f4), 0 0 calc(var(--u) * .25) var(--primary-color, #03a9f4);
  animation: lit .9s ease-out forwards; z-index: 3; }
.ctl.lit { overflow: visible; }
.ctl.lit img, .ctl.lit .mm { border-radius: inherit; }
@keyframes lit { 0% { opacity: 1; } 60% { opacity: .9; } 100% { opacity: 0; } }

/* Tilted: the pad lies on the desk, leaning back, with its thickness and a
   soft shadow under it. The keys stay live and pressable. */
.frame.tilted { perspective: calc(var(--u) * 16); perspective-origin: 50% 0%;
  aspect-ratio: var(--bw) / calc(var(--bh) * .86 + .5); }
.frame.tilted .pad, .frame.tilted .overlay {
  inset: auto 3% calc(var(--u) * .34) 3%; height: calc(100% - var(--u) * .34);
  transform-origin: 50% 100%; transform: rotateX(24deg) scale(.95, 1.1); }
.frame.tilted .pad {
  --side: #0b0c0e;
  box-shadow: 0 calc(var(--u) * .16) 0 0 var(--side), 0 calc(var(--u) * .3) calc(var(--u) * .3) rgba(0,0,0,.45),
    inset 0 1px 0 rgba(255,255,255,.1);
}
.frame.tilted .pad.painted { --side: color-mix(in srgb, var(--front) 72%, #000); }
.frame.tilted .pad.painted.light { --side: color-mix(in srgb, var(--front) 82%, #000);
  box-shadow: 0 calc(var(--u) * .16) 0 0 var(--side), 0 calc(var(--u) * .3) calc(var(--u) * .3) rgba(0,0,0,.22),
    0 0 0 1px rgba(0,0,0,.06); }
.frame.tilted .pad.clear { box-shadow: none; }
.frame.tilted .key { box-shadow: 0 calc(var(--u) * .04) 0 rgba(0,0,0,.55), 0 calc(var(--u) * .06) calc(var(--u) * .08) rgba(0,0,0,.3); }
.frame.tilted .pad.light .key { box-shadow: 0 calc(var(--u) * .04) 0 rgba(0,0,0,.28), 0 0 0 1px rgba(0,0,0,.05); }

/* Profile and page buttons under the pad. */
.bar { display: flex; align-items: center; gap: 6px; padding-top: 10px; flex-wrap: wrap; }
.bar[hidden] { display: none; }
.bar .group { display: flex; align-items: center; gap: 2px; min-width: 0; }
.bar .group[hidden] { display: none; }
.bar .group.profile { flex: 1 1 auto; }
.bar button {
  font: inherit; font-size: 18px; line-height: 1; width: 32px; height: 32px; border-radius: 50%; border: none;
  background: none; color: var(--primary-text-color); cursor: pointer; flex: 0 0 auto;
}
.bar button:hover { background: rgba(127,127,127,.15); }
.bar button:disabled { opacity: .35; cursor: default; background: none; }
.bar select {
  font: inherit; font-size: 14px; min-width: 0; flex: 1 1 auto; max-width: 220px; padding: 5px 8px; border-radius: 8px;
  color: var(--primary-text-color); background: var(--secondary-background-color, rgba(127,127,127,.12));
  border: 1px solid var(--divider-color, rgba(127,127,127,.3));
}
.bar .page { font-size: 13px; color: var(--secondary-text-color); white-space: nowrap; min-width: 42px; text-align: center; }

/* One-key card: the keys alone, without the pad round them. */
.pad.bare { background: none; box-shadow: none; outline: none; }

/* Mini Monitor screen card. */
.screen { position: absolute; inset: 0; background: #000; border-radius: 6px; overflow: hidden;
  box-shadow: 0 0 0 3px #1a1b1e, 0 2px 8px rgba(0,0,0,.3); }
ha-card.plain .screen { box-shadow: none; }
.screen .shot { position: absolute; inset: 0; background-image: var(--mm); background-size: contain;
  background-position: center; background-repeat: no-repeat; }
.screen-off { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
  position: absolute; inset: 0; color: rgba(255,255,255,.75); font-size: 14px; text-align: center; padding: 12px; }
.screen-off[hidden] { display: none; }
.screen-off button {
  font: inherit; font-size: 14px; padding: 7px 16px; border-radius: 18px; border: none; cursor: pointer;
  background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
}
.screen-off button[hidden] { display: none; }
.screen.mouse { cursor: crosshair; touch-action: none; }
.screen .badge { position: absolute; right: 8px; top: 8px; width: 22px; height: 22px; border-radius: 6px;
  background: rgba(0,0,0,.55); display: none; align-items: center; justify-content: center; pointer-events: none; }
.screen.mouse.live .badge { display: flex; }
.screen .badge svg { width: 14px; height: 14px; fill: #fff; opacity: .85; }

.button {
  border-radius: 50%;
  background: radial-gradient(circle at 50% 35%, #3a3c41 0%, #232428 70%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 calc(var(--u) * .03) calc(var(--u) * .08) rgba(0,0,0,.7),
    0 0 0 calc(var(--u) * .025) #0c0d0e;
}
.button.down { transform: scale(.88); filter: brightness(.8); transition-duration: .05s; }
.inert { cursor: default; }

.knob { border-radius: 50%; }
.knob .body {
  position: absolute; inset: 0; border-radius: 50%;
  background:
    radial-gradient(circle at 50% 50%, rgba(0,0,0,0) 56%, rgba(0,0,0,.35) 57%, rgba(0,0,0,0) 60%),
    repeating-conic-gradient(from 0deg, #3b3d42 0deg 4deg, #2a2c30 4deg 8deg);
  box-shadow: 0 0 0 calc(var(--u) * .035) #0b0c0d, 0 calc(var(--u) * .05) calc(var(--u) * .12) rgba(0,0,0,.7),
    inset 0 1px 0 rgba(255,255,255,.15);
  transition: transform .18s ease;
}
.knob .half {
  position: absolute; top: 0; bottom: 0; width: 50%;
  display: flex; align-items: center;
  color: rgba(255,255,255,.55); font-size: max(9px, calc(var(--u) * var(--kw, 1) * .15)); line-height: 1;
}
.knob .half.left { left: 0; border-radius: 9999px 0 0 9999px; justify-content: flex-start; padding-left: 7%; }
.knob .half.right { right: 0; border-radius: 0 9999px 9999px 0; justify-content: flex-end; padding-right: 7%; }
.knob .half span { pointer-events: none; text-shadow: 0 1px 2px rgba(0,0,0,.8); }
.knob .centre {
  position: absolute; left: 27%; top: 27%; width: 46%; height: 46%; border-radius: 50%;
  background: radial-gradient(circle at 50% 30%, #44464c 0%, #26282c 75%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.18), 0 0 0 calc(var(--u) * .02) #0b0c0d, 0 1px 4px rgba(0,0,0,.6);
  transition: transform .14s ease;
}
.knob.turn-left .body { transform: rotate(-18deg); }
.knob.turn-right .body { transform: rotate(18deg); }
.knob.turn-left .half.left, .knob.turn-right .half.right { color: #fff; }
.knob.push .centre { transform: scale(.88); filter: brightness(.8); }

.overlay {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  pointer-events: none; border-radius: calc(var(--u) * var(--pad-r));
}
.overlay[hidden] { display: none; }
.overlay.block { pointer-events: auto; cursor: not-allowed; }
.overlay.top { align-items: flex-start; }
.overlay.top .note {
  flex-direction: row; gap: 6px; align-items: baseline; padding: 3px 11px; border-radius: 999px;
  transform: translateY(-45%); white-space: nowrap; max-width: 92%; overflow: hidden;
}
.overlay.top .note .title { font-size: clamp(11px, 3.2cqw, 14px); }
.overlay.top .note .sub { font-size: clamp(10px, 2.6cqw, 12px); overflow: hidden; text-overflow: ellipsis; }
.overlay.top .note .sub::before { content: '· '; }
@container (max-width: 300px) { .overlay.top .note .sub { display: none; } }
.note {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  max-width: 86%; padding: 7px 14px; border-radius: 12px; text-align: center;
  background: rgba(10,11,13,.82); color: #f2f2f2;
  box-shadow: 0 2px 10px rgba(0,0,0,.45);
  backdrop-filter: blur(2px);
}
.note .title { font-size: clamp(12px, 4.2cqw, 18px); font-weight: 600; }
.note .sub { font-size: clamp(10px, 3cqw, 13px); color: rgba(255,255,255,.7); }
.note .sub:empty { display: none; }

.toast {
  position: absolute; left: 50%; bottom: 18px; transform: translate(-50%, 8px);
  max-width: calc(100% - 48px); box-sizing: border-box;
  padding: 8px 14px; border-radius: 10px; font-size: 13px; line-height: 1.3; text-align: center;
  background: var(--error-color, #db4437); color: var(--text-primary-color, #fff);
  box-shadow: 0 3px 12px rgba(0,0,0,.35);
  opacity: 0; transition: opacity .18s ease, transform .18s ease; pointer-events: none; z-index: 5;
}
.toast.show { opacity: 1; transform: translate(-50%, 0); }

.message {
  padding: 24px 12px; text-align: center; color: var(--secondary-text-color); font-size: 14px;
}
.message[hidden] { display: none; }
.message.error { color: var(--error-color, #db4437); }
@media (prefers-reduced-motion: reduce) {
  .pad, .ctl, .knob, .knob .body, .knob .centre, .toast { transition: none !important; }
  .ripple { display: none; }
  .ctl.lit::after, .knob.lit::after { animation: none; }
}
`;

/** The editors' labels and help, shared by the three cards. */
const LABELS = {
  device_id: 'Pad',
  title: 'Title',
  controls: 'Keys',
  show_card_background: 'Show card background',
  show_pad_body: 'Show the pad round the keys',
  keep_pad_layout: 'Keep the keys where they are on the pad',
  per_row: 'Keys per row (empty: all in one row)',
  show_profile: 'Show the profile and page',
  tilt: 'Tilted 3D look',
  show_page_buttons: 'Profile and page buttons',
  press_effect: 'Press effect',
  show_pad_presses: 'Show presses made on the pad',
  show_turn_on: 'Offer to turn Mini Monitor on',
  mouse: 'Use the mouse on Mini Monitor',
  scale: 'Picture scale (empty: automatic)',
};
const HELPERS = {
  title: 'Shown above the keys. Leave it empty for no title.',
  controls: 'A key number as the app counts them (3), several for a group (1, 2, 6-7), or names such as band_1, button_2 or top_knob.',
  keep_pad_layout: 'Off: the keys sit side by side in the order typed.',
  per_row: 'Ignored while the keys keep their places on the pad.',
  show_card_background: 'Off: no frame round the card, and the pad uses all the room.',
  tilt: 'The pad leans back as if lying on a desk. Keys still press.',
  show_page_buttons: 'Buttons under the pad to change its profile and page.',
  press_effect: 'The key sinks and lights up where you tap it.',
  show_pad_presses: 'A ring flashes round a key pressed on the real pad, on a pad on screen or by an automation.',
  show_turn_on: 'A button to turn it on when it is off. It needs permission to change the Mini Monitor switch.',
  mouse: "Click, drag, right-click (a long press on a phone) and scroll on the PC's Mini Monitor display. It moves the PC's real pointer. Administrators only, and the app must allow it.",
  scale: 'Leave empty to match the screen. 1 is sharpest on small cards, 3 on big high-DPI screens.',
};

/** An editor section that opens in place. */
function section(title, icon, schema, expanded = false) {
  return { type: 'expandable', name: '', flatten: true, title, icon, schema, ...(expanded ? { expanded: true } : {}) };
}

const DEVICE_FIELD = {
  name: 'device_id',
  required: true,
  selector: {
    device: {
      filter: [{ integration: 'stream_dock_ha' }],
      entity: [{ domain: 'select', integration: 'stream_dock_ha' }],
    },
  },
};

const Base = typeof HTMLElement !== 'undefined' ? HTMLElement : class {};

export class StreamDockCard extends Base {
  constructor() {
    super();
    this._config = null;
    this._hass = null;
    this._conn = null;
    this._connHandlers = null;
    this._linkDown = false;
    this._watch = null;
    this._device = null; // { conn, deviceId, promise, padId }
    this._padId = null;
    this._pad = null;
    this._online = true;
    this._loaded = false;
    this._pictures = new Map();
    this._layout = null; // computeLayout() result
    this._els = new Map(); // control name -> { el, img, item }
    this._autoScale = null;
    this._built = false;
    this._syncQueued = false;
    this._message = null;
    this._toastTimer = null;
    this._down = null;
    this._resizeTimer = null;
    this._ro = null;
    this._retryTimer = null;
    this._retryAttempt = 0;
  }

  /* ---------- Lovelace API ---------- */

  static getConfigForm() {
    return {
      schema: [
        {
          type: 'expandable',
          name: '',
          flatten: true,
          expanded: true,
          title: 'Pad',
          icon: 'mdi:view-grid-outline',
          schema: [
            {
              name: 'device_id',
              required: true,
              selector: {
                device: {
                  filter: [{ integration: 'stream_dock_ha' }],
                  entity: [{ domain: 'select', integration: 'stream_dock_ha' }],
                },
              },
            },
            { name: 'title', selector: { text: {} } },
          ],
        },
        {
          type: 'expandable',
          name: '',
          flatten: true,
          title: 'Appearance',
          icon: 'mdi:palette-outline',
          schema: [
            { name: 'show_card_background', selector: { boolean: {} } },
              { name: 'show_profile', selector: { boolean: {} } },
            { name: 'tilt', selector: { boolean: {} } },
          ],
        },
        {
          type: 'expandable',
          name: '',
          flatten: true,
          title: 'Extras',
          icon: 'mdi:gesture-tap-button',
          schema: [
            { name: 'show_page_buttons', selector: { boolean: {} } },
            { name: 'press_effect', selector: { boolean: {} } },
            { name: 'show_pad_presses', selector: { boolean: {} } },
          ],
        },
        {
          type: 'expandable',
          name: '',
          flatten: true,
          title: 'Pictures',
          icon: 'mdi:image-outline',
          schema: [
            { name: 'scale', selector: { number: { min: 1, max: 3, step: 1, mode: 'box' } } },
          ],
        },
      ],
      computeLabel: (s) => LABELS[s.name],
      computeHelper: (s) => HELPERS[s.name],
    };
  }

  static getStubConfig(hass) {
    const entities = hass && hass.entities ? Object.values(hass.entities) : [];
    const select = entities.find((e) => e && e.platform === 'stream_dock_ha'
      && typeof e.entity_id === 'string' && e.entity_id.startsWith('select.') && e.device_id);
    const deviceId = select ? select.device_id : '';
    const out = { device_id: deviceId, show_card_background: true, show_profile: true };
    const name = padNameOf(hass, deviceId);
    if (name) out.title = name;
    return out;
  }

  /** The pad's Layout as this card draws it: all of it, here. */
  _laidOut(layout, body) {
    return laidOut(layout, body);
  }

  static normalise(config) {
    return normaliseConfig(config);
  }

  setConfig(config) {
    const next = this.constructor.normalise(config);
    const prev = this._config;
    this._config = next;
    if (prev && (prev.device_id !== next.device_id || prev.pad_id !== next.pad_id)) {
      this._device = null;
      this._cancelRetry(true);
    }
    // What the card shows of the pad can change with its settings.
    if (this._built && this._pad && this._pad.layout) this._layoutChanged(this._laidOut(this._pad.layout, this._pad.body));
    if (this._built) this._renderChrome();
    this._sync();
    this._onEntities();
  }

  set hass(hass) {
    this._hass = hass;
    this._sync();
    this._onEntities();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    const layout = this._layout || this._cachedLayout();
    const header = this._config && (this._config.title || this._config.show_profile) ? 1 : 0;
    if (!layout) return 4 + header;
    // About 450 px wide in masonry; one size unit is 50 px.
    return Math.max(2, Math.ceil((450 * layout.height) / layout.width / 50) + header);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: 'auto', min_rows: 2 };
  }

  /* ---------- DOM lifecycle ---------- */

  connectedCallback() {
    if (!this._built) this._build();
    if (typeof ResizeObserver !== 'undefined' && !this._ro) {
      this._ro = new ResizeObserver(() => this._onResize());
      this._ro.observe(this._frame);
    }
    // Nothing is watched, so nothing streamed, while the card can't be seen:
    // its browser tab hidden, or the card scrolled well out of view.
    if (typeof IntersectionObserver !== 'undefined' && !this._io) {
      this._io = new IntersectionObserver((entries) => {
        const seen = entries.some((entry) => entry.isIntersecting);
        if (seen !== this._inView) { this._inView = seen; this._sync(); }
      }, { rootMargin: '200px' });
      this._io.observe(this._card);
    }
    if (!this._onVisibility) {
      this._onVisibility = () => this._sync();
      document.addEventListener('visibilitychange', this._onVisibility);
    }
    this._sync();
  }

  /** Whether someone could see the card now. */
  _seen() {
    const tabShown = typeof document === 'undefined' || document.visibilityState !== 'hidden';
    return tabShown && this._inView !== false;
  }

  disconnectedCallback() {
    this._cancelRetry(true);
    this._stopWatch();
    this._unbindConnection();
    if (this._ro) { this._ro.disconnect(); this._ro = null; }
    if (this._io) { this._io.disconnect(); this._io = null; this._inView = undefined; }
    if (this._onVisibility) {
      document.removeEventListener('visibilitychange', this._onVisibility);
      this._onVisibility = null;
    }
    clearTimeout(this._resizeTimer);
    this._releaseDown();
    this._clearFrame();
  }

  _build() {
    const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="wrap">
          <div class="header" part="header">
            <span class="name"></span>
            <span class="chip" hidden title="Press any key to dismiss">Alert</span>
            <span class="detail"></span>
          </div>
          <div class="message" hidden></div>
          <div class="frame" hidden>
            <div class="pad"></div>
            <div class="overlay" hidden><div class="note"><span class="title"></span><span class="sub"></span></div></div>
          </div>
          <div class="bar" hidden>
            <div class="group profile">
              <button class="prev-profile" title="Previous profile" aria-label="Previous profile">‹</button>
              <select class="profiles" aria-label="Profile"></select>
              <button class="next-profile" title="Next profile" aria-label="Next profile">›</button>
            </div>
            <div class="group pages">
              <button class="prev-page" title="Previous page" aria-label="Previous page">‹</button>
              <span class="page"></span>
              <button class="next-page" title="Next page" aria-label="Next page">›</button>
            </div>
          </div>
          <div class="toast" role="status" aria-live="polite"></div>
        </div>
      </ha-card>`;
    this._card = root.querySelector('ha-card');
    this._header = root.querySelector('.header');
    this._nameEl = root.querySelector('.name');
    this._detailEl = root.querySelector('.detail');
    this._chipEl = root.querySelector('.chip');
    this._messageEl = root.querySelector('.message');
    this._frame = root.querySelector('.frame');
    this._padEl = root.querySelector('.pad');
    this._overlayEl = root.querySelector('.overlay');
    this._toastEl = root.querySelector('.toast');
    this._barEl = root.querySelector('.bar');
    this._barEl.addEventListener('click', (e) => this._onBarClick(e));
    this._barEl.querySelector('.profiles').addEventListener('change', (e) => this._chooseProfile(e.target.value));

    const pad = this._padEl;
    pad.addEventListener('pointerdown', (e) => this._onPointerDown(e));
    pad.addEventListener('pointerup', (e) => this._onPointerUp(e));
    pad.addEventListener('pointercancel', () => this._releaseDown());
    pad.addEventListener('pointerleave', (e) => { if (this._down && this._down.pointerId === e.pointerId) this._releaseDown(); });
    pad.addEventListener('keydown', (e) => this._onKeyDown(e));
    pad.addEventListener('contextmenu', (e) => { if (e.target.closest && e.target.closest('[data-control]')) e.preventDefault(); });

    this._built = true;
    const cached = this._cachedLayout();
    if (cached && !this._layout) this._buildControls(cached);
    this._renderChrome();
  }

  /* ---------- Connection and subscription ---------- */

  _sync() {
    if (this._syncQueued) return;
    this._syncQueued = true;
    Promise.resolve().then(() => {
      this._syncQueued = false;
      this._doSync().catch((err) => this._showMessage(String(err && err.message || err), true));
    });
  }

  async _doSync() {
    const conn = this._hass && this._hass.connection;
    if (!this.isConnected || !conn || !this._config) {
      if (!this.isConnected) this._stopWatch();
      return;
    }
    this._bindConnection(conn);
    if (this._linkDown) return; // wait for "ready"

    let padId = this._config.pad_id || null;
    if (this._config.device_id) {
      padId = await this._resolveDevice(conn, this._config.device_id);
      if (this._hass.connection !== conn || !this.isConnected) return;
      if (!padId) { // message already shown; a retry is scheduled
        this._stopWatch();
        return;
      }
    }
    if (!padId) {
      this._stopWatch();
      this._showMessage('Choose a Stream Dock pad in the card settings.');
      return;
    }

    if (padId !== this._padId) this._resetPad(padId);
    if (!this._seen()) {
      // Keeps the last pictures, and watches again when it can be seen.
      this._stopWatch();
      this._clearFrame();
      return;
    }
    const scale = this._desiredScale();
    const key = `${padId}|${scale}`;
    if (this._watch && this._watch.conn === conn && this._watch.key === key) return;

    this._stopWatch();
    const watch = { conn, key, padId, scale, unsub: null, failed: false };
    this._watch = watch;
    try {
      const unsub = await conn.subscribeMessage(
        (event) => { if (this._watch === watch) this._onEvent(event); },
        { type: 'stream_dock_ha/watch', pad_id: padId, scale },
        { resubscribe: false },
      );
      if (this._watch !== watch) { safeUnsub(unsub); return; }
      watch.unsub = unsub;
      this._cancelRetry(true);
    } catch (err) {
      if (this._watch !== watch) return;
      watch.failed = true; // kept until the retry, so hass updates don't retry at once
      this._scheduleRetry();
      const code = err && err.code;
      this._showMessage(code === 'not_found'
        ? "This pad isn't known to Home Assistant."
        : code === 'unknown_command'
          ? 'The Stream Dock HA integration is not loaded.'
          : `Couldn't watch the pad: ${(err && err.message) || code || err}`, true);
    }
  }

  async _resolveDevice(conn, deviceId) {
    const d = this._device;
    // A failed or empty lookup is only reused while its retry is pending.
    if (!d || d.conn !== conn || d.deviceId !== deviceId || (d.failed && !this._retryTimer)) {
      const entry = { conn, deviceId, padId: null, promise: null, failed: false };
      entry.promise = conn.sendMessagePromise
        ? conn.sendMessagePromise({ type: 'stream_dock_ha/pads' })
        : this._hass.callWS({ type: 'stream_dock_ha/pads' });
      entry.promise = entry.promise.then(
        (result) => {
          entry.padId = resolvePadId({ device_id: deviceId }, result);
          if (!entry.padId) {
            this._lookupFailed(entry);
            this._showMessage("This device isn't a Stream Dock pad.", true);
          }
          return entry.padId;
        },
        (err) => {
          this._lookupFailed(entry);
          const code = err && err.code;
          this._showMessage(code === 'unknown_command'
            ? 'The Stream Dock HA integration is not loaded.'
            : `Couldn't list the pads: ${(err && err.message) || code || err}`, true);
          return null;
        },
      );
      this._device = entry;
    }
    return this._device.promise;
  }

  _lookupFailed(entry) {
    entry.failed = true;
    if (this._device === entry) this._scheduleRetry();
  }

  /* ---------- Retrying a failed watch or lookup, with backoff ---------- */

  _scheduleRetry() {
    if (this._retryTimer || !this.isConnected) return;
    const delay = retryDelayMs(this._retryAttempt);
    this._retryAttempt += 1;
    this._retryTimer = setTimeout(() => {
      this._retryTimer = null;
      if (!this.isConnected) return;
      if (this._device && this._device.failed) this._device = null;
      if (this._watch && this._watch.failed) this._watch = null;
      this._sync();
    }, delay);
  }

  _cancelRetry(resetBackoff) {
    clearTimeout(this._retryTimer);
    this._retryTimer = null;
    if (resetBackoff) this._retryAttempt = 0;
  }

  _bindConnection(conn) {
    if (this._conn === conn) return;
    this._unbindConnection();
    this._stopWatch();
    this._device = null;
    this._conn = conn;
    const onReady = () => {
      this._cancelRetry(true);
      this._linkDown = false;
      this._watch = null; // the old subscription died with the old socket
      this._device = null;
      this._renderChrome();
      this._sync();
    };
    const onDown = () => {
      this._linkDown = true;
      this._watch = null;
      this._renderChrome();
    };
    this._connHandlers = { onReady, onDown };
    if (typeof conn.addEventListener === 'function') {
      conn.addEventListener('ready', onReady);
      conn.addEventListener('disconnected', onDown);
    }
    this._linkDown = conn.connected === false;
  }

  _unbindConnection() {
    const conn = this._conn;
    if (conn && this._connHandlers && typeof conn.removeEventListener === 'function') {
      conn.removeEventListener('ready', this._connHandlers.onReady);
      conn.removeEventListener('disconnected', this._connHandlers.onDown);
    }
    this._conn = null;
    this._connHandlers = null;
  }

  _stopWatch() {
    const watch = this._watch;
    this._watch = null;
    if (watch && watch.unsub) safeUnsub(watch.unsub);
  }

  _resetPad(padId) {
    this._padId = padId;
    this._pad = null;
    this._online = true;
    this._loaded = false;
    this._pictures = new Map();
    this._clearFrame();
    this._autoScale = null;
    this._layout = null;
    this._els.clear();
    if (this._built) {
      this._padEl.textContent = '';
      const cached = this._cachedLayout();
      if (cached) this._buildControls(cached);
    }
    this._message = null;
    this._renderChrome();
  }

  _cachedLayout() {
    const cached = this._padId && layoutCache.get(this._padId);
    return cached ? this._laidOut(cached.layout, cached.body) : null;
  }

  /* ---------- Scale ---------- */

  _desiredScale() {
    if (this._config && this._config.scale != null) return clampScale(this._config.scale);
    const auto = this._measureScale();
    if (auto) this._autoScale = auto;
    return this._autoScale || 2;
  }

  _measureScale() {
    if (!this._frame) return null;
    const width = this._frame.clientWidth || (this.clientWidth ? this.clientWidth - 24 : 0);
    if (!(width > 0)) return null;
    const layout = this._layout || this._cachedLayout();
    const units = layout ? layout.width : 7; // a guess until the layout arrives
    const dpr = typeof window !== 'undefined' && window.devicePixelRatio ? window.devicePixelRatio : 1;
    return chooseScale(keySizePx(width, units), dpr);
  }

  _onResize() {
    clearTimeout(this._resizeTimer);
    this._resizeTimer = setTimeout(() => {
      if (this._config && this._config.scale == null && this._watch) {
        const scale = this._measureScale();
        if (scale && scale !== this._watch.scale) this._sync();
      }
    }, 300);
  }

  /* ---------- Events from the integration ---------- */

  _onEvent(event) {
    if (!event || typeof event !== 'object') return;
    if (event.kind === 'pad') this._onPad(event);
    else if (event.kind === 'pictures') this._onPictures(event);
    else if (event.kind === 'frame') this._onFrame(event);
  }

  /* ---------- Mini Monitor ---------- */

  _onFrame(event) {
    if (!this._built || !this._pad || this._pad.mini_monitor !== true) return;
    if (typeof event.data !== 'string' || !event.data) return;
    const tiles = JSON.stringify(event.tiles || []) + `${event.width}x${event.height}`;
    if (tiles !== this._frameTiles) {
      this._frameTiles = tiles;
      this._frameParts = frameParts(event);
      this._frameMeta = { tiles: event.tiles || [] };
      this._placeFrameParts();
    }
    this._padEl.classList.toggle('seamless', event.seamless === true);
    // A blob is lighter, but a browser that can't show one gets the picture
    // as a data: address, as the key pictures are.
    let url = null;
    let blob = false;
    if (!this._frameAsData) {
      try {
        const bytes = Uint8Array.from(atob(event.data), (c) => c.charCodeAt(0));
        url = URL.createObjectURL(new Blob([bytes], { type: 'image/jpeg' }));
        blob = true;
      } catch (_err) {
        this._frameAsData = true;
      }
    }
    if (!url) url = `data:image/jpeg;base64,${event.data}`;
    const drop = (u) => { if (u && u.startsWith('blob:')) URL.revokeObjectURL(u); };
    // Shown once decoded, so the keys never flash empty between pictures. A
    // picture decoded after a newer one is dropped, but a slow decode isn't
    // dropped just because the next picture came in meanwhile.
    const serial = (this._frameSerial = (this._frameSerial || 0) + 1);
    const img = new Image();
    const loaded = new Promise((ok, fail) => { img.onload = ok; img.onerror = fail; });
    img.src = url;
    const show = () => {
      if (serial <= (this._frameShown || 0) || !this._built) { drop(url); return; }
      this._frameShown = serial;
      this._frameFails = 0;
      const old = this._frameUrl;
      this._frameUrl = url;
      this._frame.style.setProperty('--mm', `url("${url}")`);
      this._padEl.classList.add('mini');
      if (old) drop(old);
      if (!old || this._frameError) { this._frameError = false; this._renderChrome(); }
      clearTimeout(this._frameTimer);
      this._frameTimer = setTimeout(() => this._clearFrame(), FRAME_STALE_MS);
    };
    const failed = () => {
      drop(url);
      this._frameFails = (this._frameFails || 0) + 1;
      // A blob that won't show: data: addresses from now on.
      if (blob) this._frameAsData = true;
      if (this._frameFails >= 3 && !this._frameUrl && !this._frameError) { this._frameError = true; this._renderChrome(); }
    };
    // Some browsers' decode() refuses pictures that load fine (older Safari,
    // in the phone app among them): then it's shown once loaded.
    const ready = img.decode ? img.decode().catch(() => loaded) : loaded;
    ready.then(show, failed);
  }

  /** Gives each key its part of the picture, with a layer to show it in. */
  _placeFrameParts() {
    const parts = this._frameParts || new Map();
    // The one picture across the gaps, over all those keys.
    let whole = this._padEl.querySelector(':scope > .mm-whole');
    const box = this._frameMeta && frameBox(this._layout, this._frameMeta);
    if (!box) { if (whole) whole.remove(); } else {
      if (!whole) {
        whole = document.createElement('div');
        whole.className = 'mm-whole';
        this._padEl.appendChild(whole);
      }
      whole.style.left = `${box.left}%`;
      whole.style.top = `${box.top}%`;
      whole.style.width = `${box.width}%`;
      whole.style.height = `${box.height}%`;
    }
    let bandCovered = false;
    for (const [name, entry] of this._els) {
      const part = parts.get(name);
      entry.el.classList.toggle('covered', !!part);
      if (part && entry.item && entry.item.kind === 'band') bandCovered = true;
      let layer = entry.el.querySelector(':scope > .mm');
      if (!part) { if (layer) layer.remove(); continue; }
      if (!layer) {
        layer = document.createElement('div');
        layer.className = 'mm';
        entry.el.appendChild(layer);
      }
      layer.style.backgroundSize = part.size;
      layer.style.backgroundPosition = part.position;
    }
    const strip = this._padEl.querySelector(':scope > .strip');
    if (strip) strip.classList.toggle('covered', bandCovered);
  }

  _clearFrame() {
    clearTimeout(this._frameTimer);
    this._frameSerial = (this._frameSerial || 0) + 1;
    this._frameShown = this._frameSerial; // pictures still decoding stay off
    const had = !!this._frameUrl;
    if (this._frameUrl && this._frameUrl.startsWith('blob:')) URL.revokeObjectURL(this._frameUrl);
    this._frameUrl = null;
    if (this._built) {
      this._padEl.classList.remove('mini', 'seamless');
      this._frame.style.removeProperty('--mm');
      if (had) this._renderChrome();
    }
  }

  _onPad(event) {
    this._online = event.online !== false;
    const pad = event.pad && typeof event.pad === 'object' ? event.pad : this._pad;
    this._pad = pad;
    this._loaded = true;
    this._message = null;
    if (pad && pad.layout) {
      layoutCache.set(this._padId, { layout: pad.layout, body: pad.body });
      this._layoutChanged(this._laidOut(pad.layout, pad.body));
    }
    if (!pad || pad.mini_monitor !== true) this._clearFrame();
    this._renderChrome();
  }

  /** Draws a new layout if it differs from the one drawn; null: nothing of it to show. */
  _layoutChanged(computed) {
    if (!computed) {
      this._layout = null;
      this._els.clear();
      if (this._built) this._padEl.textContent = '';
      this._message = { text: this._nothingToShow(), error: true, missing: true };
      return;
    }
    if (this._message && this._message.missing) this._message = null;
    if (!this._layout || this._layout.version !== computed.version) {
      this._buildControls(computed);
      // The real layout can change the key size: check the scale.
      if (this._config.scale == null && this._watch) {
        const scale = this._measureScale();
        if (scale && scale !== this._watch.scale) this._sync();
      }
    } else {
      // The front's colour or the keys' corners can change on their own.
      this._applyBody(computed.look);
    }
  }

  _nothingToShow() {
    return 'This pad has nothing to show.';
  }

  _onPictures(event) {
    const { pictures, changed } = mergePictures(this._pictures, event);
    this._pictures = pictures;
    for (const name of changed) this._applyPicture(name);
  }

  /* ---------- Rendering ---------- */

  _buildControls(layout) {
    if (!this._built) { this._layout = layout; return; }
    this._layout = layout;
    this._els.clear();
    const frag = document.createDocumentFragment();
    if (layout.strip) {
      const strip = document.createElement('div');
      strip.className = 'strip';
      const b = layout.strip.box;
      strip.style.left = `${b.left}%`;
      strip.style.top = `${b.top}%`;
      strip.style.width = `${b.width}%`;
      strip.style.height = `${b.height}%`;
      strip.style.setProperty('--sw', String(layout.strip.w));
      frag.appendChild(strip);
    }
    for (const item of layout.items) {
      const el = document.createElement('div');
      const b = item.box;
      el.style.left = `${b.left}%`;
      el.style.top = `${b.top}%`;
      el.style.width = `${b.width}%`;
      el.style.height = `${b.height}%`;
      if (item.kind === 'knob') {
        el.className = 'knob';
        el.style.setProperty('--kw', String(item.w));
        el.innerHTML = '<div class="body"></div>';
        const parts = [
          ['left', 'half left', '<span>↺</span>'],
          ['right', 'half right', '<span>↻</span>'],
          ['press', 'centre', ''],
        ];
        for (const [part, cls, inner] of parts) {
          const info = item.parts[part];
          if (!info) continue;
          const p = document.createElement('div');
          p.className = cls;
          p.innerHTML = inner;
          this._makePressable(p, info.name, info.press);
          p.dataset.part = part;
          el.appendChild(p);
          this._els.set(info.name, { el: p, knob: el, img: null, item });
        }
      } else {
        el.className = `ctl ${item.kind}`;
        let img = null;
        if (item.screen && item.kind !== 'button') {
          img = document.createElement('img');
          img.alt = '';
          img.draggable = false;
          img.decoding = 'async';
          el.appendChild(img);
        }
        this._makePressable(el, item.name, item.press);
        this._els.set(item.name, { el, knob: null, img, item });
      }
      frag.appendChild(el);
    }
    this._padEl.textContent = '';
    this._padEl.appendChild(frag);
    this._frame.style.setProperty('--bw', String(layout.width));
    this._frame.style.setProperty('--bh', String(layout.height));
    this._applyBody(layout.look);
    for (const name of this._els.keys()) this._applyPicture(name);
    this._placeFrameParts();
  }

  _applyBody(look) {
    if (!this._built || !look) return;
    const pad = this._padEl;
    const style = this._frame.style;
    pad.classList.toggle('painted', !!look.front);
    pad.classList.toggle('clear', look.clear);
    pad.classList.toggle('light', look.light);
    pad.classList.toggle('bare', !!look.bare);
    if (look.front) style.setProperty('--front', look.front);
    else style.removeProperty('--front');
    style.setProperty('--pad-r', String(look.corner));
    style.setProperty('--key-r', String(look.keyCorner));
    style.setProperty('--band-r', String(look.bandCorner));
  }

  _makePressable(el, name, press) {
    if (press) {
      el.dataset.control = name;
      el.setAttribute('role', 'button');
      el.tabIndex = 0;
      el.setAttribute('aria-label', humanizeControl(name));
    } else {
      el.classList.add('inert');
      el.setAttribute('aria-hidden', 'true');
    }
  }

  _applyPicture(name) {
    const entry = this._els.get(name);
    if (!entry || !entry.img) return;
    const pic = this._pictures.get(name);
    if (pic) {
      const src = `data:image/jpeg;base64,${pic.data}`;
      if (entry.img.getAttribute('src') !== src) entry.img.src = src;
      entry.el.classList.add('pic');
    } else {
      entry.el.classList.remove('pic');
      entry.img.removeAttribute('src');
    }
  }

  _renderChrome() {
    if (!this._built || !this._config) return;
    const cfg = this._config;
    const pad = this._pad;

    this._card.classList.toggle('plain', cfg.show_card_background === false);
    this._frame.classList.toggle('tilted', cfg.tilt === true);
    this._padEl.classList.toggle('fx', cfg.press_effect !== false);
    this._renderBar();

    // Header: the card's title, when it has one.
    const name = cfg.title || '';
    const detail = headerDetail(pad, cfg.show_profile);
    this._header.hidden = !name && !detail;
    this._nameEl.textContent = name;
    this._detailEl.textContent = detail;
    this._chipEl.hidden = !(pad && pad.alert);

    // Message or pad
    const hasLayout = !!this._layout;
    if (this._message && (!hasLayout || this._message.error)) {
      this._messageEl.textContent = this._message.text;
      this._messageEl.classList.toggle('error', !!this._message.error);
      this._messageEl.hidden = false;
    } else if (!hasLayout) {
      this._messageEl.textContent = this._padId ? 'Loading the pad…' : '';
      this._messageEl.classList.remove('error');
      this._messageEl.hidden = !this._padId;
    } else {
      this._messageEl.hidden = true;
    }
    this._frame.hidden = !hasLayout;

    // Overlay
    const overlay = this._overlayFor({
      online: this._online, linkDown: this._linkDown, pad, frames: !!this._frameUrl, frameError: !!this._frameError,
    });
    this._overlay = overlay;
    this._padEl.classList.toggle('dim', !!(overlay && overlay.dim));
    if (overlay) {
      this._overlayEl.hidden = false;
      this._overlayEl.className = `overlay ${overlay.kind}${overlay.block ? ' block' : ''}${overlay.dim ? '' : ' top'}`;
      this._overlayEl.querySelector('.title').textContent = overlay.text;
      this._overlayEl.querySelector('.sub').textContent = overlay.sub || '';
    } else {
      this._overlayEl.hidden = true;
    }
  }

  /** What covers the pad now (padOverlay); the screen card leaves some out. */
  _overlayFor(state) {
    return padOverlay(state);
  }

  _showMessage(text, error = false) {
    this._message = text ? { text, error } : null;
    this._renderChrome();
  }

  /* ---------- Pressing ---------- */

  _target(e) {
    const path = typeof e.composedPath === 'function' ? e.composedPath() : [e.target];
    for (const node of path) {
      if (node === this._padEl) break;
      if (node && node.dataset && node.dataset.control) return node;
    }
    return null;
  }

  _onPointerDown(e) {
    if (e.button !== undefined && e.button !== 0) return;
    const el = this._target(e);
    if (!el) return;
    this._releaseDown();
    this._down = { pointerId: e.pointerId, el, control: el.dataset.control, at: Date.now() };
    this._showDown(el, true);
    this._ripple(el, e);
  }

  _onPointerUp(e) {
    const down = this._down;
    if (!down || down.pointerId !== e.pointerId) return;
    const el = this._target(e);
    this._releaseDown();
    if (el === down.el) this._press(down.control);
  }

  _onKeyDown(e) {
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
    const el = this._target(e);
    if (!el) return;
    e.preventDefault();
    if (e.repeat) return;
    this._showDown(el, true);
    this._ripple(el, null);
    setTimeout(() => this._showDown(el, false), MIN_PRESS_MS + 40);
    this._press(el.dataset.control);
  }

  _releaseDown() {
    const down = this._down;
    if (!down) return;
    this._down = null;
    const wait = Math.max(0, MIN_PRESS_MS - (Date.now() - down.at));
    if (wait) setTimeout(() => this._showDown(down.el, false), wait);
    else this._showDown(down.el, false);
  }

  _showDown(el, on) {
    const part = el.dataset.part;
    if (part) {
      const knob = el.parentElement;
      const cls = part === 'left' ? 'turn-left' : part === 'right' ? 'turn-right' : 'push';
      if (knob) knob.classList.toggle(cls, on);
    } else {
      el.classList.toggle('down', on);
    }
  }

  async _press(control) {
    if (!control || !this._hass || !this._padId) return;
    this._pressedHere = { control, at: Date.now() };
    const entry = this._els.get(control);
    if (entry && entry.item) {
      const press = entry.item.kind === 'knob'
        ? Object.values(entry.item.parts).find((p) => p.name === control)?.press
        : entry.item.press;
      if (press === false) return;
    }
    if (this._overlay && this._overlay.block) {
      this._toast(this._overlay.kind === 'offline' ? 'The PC is offline' : 'Not connected to Home Assistant');
      return;
    }
    try {
      await this._hass.callWS({ type: 'stream_dock_ha/press', pad_id: this._padId, control });
    } catch (err) {
      this._toast(pressErrorText(err));
    }
  }

  /** A soft light spreading from where the key was hit. */
  _ripple(el, e) {
    if (!this._config || this._config.press_effect === false) return;
    if (!el.classList.contains('key') && !el.classList.contains('band')) return;
    const ripple = document.createElement('span');
    ripple.className = 'ripple';
    const r = el.getBoundingClientRect();
    if (e && r.width > 0 && r.height > 0 && (e.clientX || e.clientY)) {
      const at = (v) => `${Math.min(100, Math.max(0, v * 100))}%`;
      ripple.style.setProperty('--rx', at((e.clientX - r.left) / r.width));
      ripple.style.setProperty('--ry', at((e.clientY - r.top) / r.height));
    }
    el.appendChild(ripple);
    setTimeout(() => ripple.remove(), 500);
  }

  /* ---------- The pad's entities: presses made elsewhere, profile and page ---------- */

  _onEntities() {
    const hass = this._hass;
    const cfg = this._config;
    if (!hass || !cfg) return;
    if (this._entitiesFor !== hass.entities || this._entitiesDevice !== cfg.device_id) {
      this._entities = padEntities(hass, cfg.device_id);
      this._entitiesFor = hass.entities;
      this._entitiesDevice = cfg.device_id;
      this._pressStamp = undefined;
    }
    const found = this._entities;
    const states = hass.states || {};
    const press = found.press ? states[found.press] : null;
    const stamp = press ? String(press.state) : null;
    if (stamp !== this._pressStamp) {
      const first = this._pressStamp === undefined;
      this._pressStamp = stamp;
      const pressed = !first && cfg.show_pad_presses !== false ? pressedControl(press) : null;
      if (pressed) this._light(pressed.control);
    }
    const look = (id) => {
      const st = id && states[id];
      return st ? `${st.state}|${JSON.stringify(st.attributes && st.attributes.options)}|${st.attributes && st.attributes.max}` : '';
    };
    const key = `${cfg.show_page_buttons}|${look(found.profile)}|${look(found.page)}|${look(found.mini_monitor)}`;
    if (key !== this._entitiesKey) {
      this._entitiesKey = key;
      this._renderChrome();
    }
  }

  /** A ring round a control pressed somewhere else than this card. */
  _light(control) {
    const here = this._pressedHere;
    if (here && here.control === control && Date.now() - here.at < 2500) return;
    const entry = this._els.get(control);
    if (!entry) return;
    const el = entry.knob || entry.el;
    el.classList.remove('lit');
    void el.offsetWidth; // starts the ring again
    el.classList.add('lit');
    if (entry.knob) {
      this._showDown(entry.el, true);
      setTimeout(() => this._showDown(entry.el, false), 260);
    }
    clearTimeout(el._litTimer);
    el._litTimer = setTimeout(() => el.classList.remove('lit'), 950);
  }

  _renderBar() {
    const bar = this._barEl;
    if (!bar) return;
    const cfg = this._config;
    const hass = this._hass;
    const found = this._entities || {};
    const states = (hass && hass.states) || {};
    const profile = cfg && cfg.show_page_buttons && found.profile ? states[found.profile] : null;
    const page = cfg && cfg.show_page_buttons && found.page ? states[found.page] : null;
    bar.hidden = !(profile || page) || !this._layout;
    if (bar.hidden) return;
    const off = (st) => !st || st.state === 'unavailable' || st.state === 'unknown';

    const profileGroup = bar.querySelector('.group.profile');
    profileGroup.hidden = !profile;
    if (profile) {
      const select = profileGroup.querySelector('select');
      const options = Array.isArray(profile.attributes.options) ? profile.attributes.options.map(String) : [];
      const now = [...select.options].map((o) => o.value);
      if (now.join('\n') !== options.join('\n')) {
        select.textContent = '';
        for (const name of options) {
          const option = document.createElement('option');
          option.value = name;
          option.textContent = name;
          select.appendChild(option);
        }
      }
      select.value = profile.state;
      select.disabled = off(profile);
      for (const b of profileGroup.querySelectorAll('button')) b.disabled = off(profile) || options.length < 2;
    }

    const pageGroup = bar.querySelector('.group.pages');
    pageGroup.hidden = !page;
    if (page) {
      const n = Math.round(num(page.state, 0));
      const max = Math.round(num(page.attributes.max, 1));
      pageGroup.querySelector('.page').textContent = off(page) ? '–' : `${n} / ${max}`;
      pageGroup.querySelector('.prev-page').disabled = off(page) || n <= 1;
      pageGroup.querySelector('.next-page').disabled = off(page) || n >= max;
    }
  }

  _onBarClick(e) {
    const button = e.target.closest && e.target.closest('button');
    if (!button || button.disabled) return;
    const found = this._entities || {};
    const states = (this._hass && this._hass.states) || {};
    if (button.classList.contains('prev-profile') || button.classList.contains('next-profile')) {
      const service = button.classList.contains('prev-profile') ? 'select_previous' : 'select_next';
      this._call('select', service, { entity_id: found.profile, cycle: true });
    } else if (button.classList.contains('prev-page') || button.classList.contains('next-page')) {
      const st = states[found.page];
      if (!st) return;
      const by = button.classList.contains('prev-page') ? -1 : 1;
      this._call('number', 'set_value', { entity_id: found.page, value: Math.round(num(st.state, 1)) + by });
    }
  }

  _chooseProfile(option) {
    const found = this._entities || {};
    if (found.profile && option) this._call('select', 'select_option', { entity_id: found.profile, option });
  }

  async _call(domain, service, data) {
    if (!this._hass || !data.entity_id) return;
    try {
      await this._hass.callService(domain, service, data);
    } catch (err) {
      this._toast((err && err.message) || `Couldn't ${service.replace(/_/g, ' ')}`);
    }
  }

  _toast(text) {
    if (!this._toastEl) return;
    this._toastEl.textContent = text;
    this._toastEl.classList.add('show');
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => this._toastEl.classList.remove('show'), TOAST_MS);
  }
}

function safeUnsub(unsub) {
  try {
    const result = typeof unsub === 'function' ? unsub() : undefined;
    if (result && typeof result.catch === 'function') result.catch(() => {});
  } catch (_err) {
    // The subscription may already be gone with its socket.
  }
}

/* ------------------------------------------------------------------ */
/* One key, or a few: custom:stream-dock-key-card                       */
/* ------------------------------------------------------------------ */

/** A one-key card's config: which controls, and no header unless asked for. */
export function normaliseKeyConfig(config) {
  if (!config || typeof config !== 'object') throw new Error('Invalid configuration');
  const out = normaliseConfig({ show_profile: false, ...config });
  out.focus = parseControls(out.controls);
  out.show_pad_body = out.show_pad_body === true;
  out.keep_pad_layout = out.keep_pad_layout === true;
  const perRow = Math.floor(Number(out.per_row));
  out.per_row = Number.isFinite(perRow) && perRow > 0 ? Math.min(perRow, 64) : 0;
  out.show_page_buttons = false;
  out.tilt = false;
  return out;
}

export class StreamDockKeyCard extends StreamDockCard {
  static normalise(config) {
    return normaliseKeyConfig(config);
  }

  static getConfigForm() {
    return {
      schema: [
        section('Key', 'mdi:gesture-tap-button', [
          DEVICE_FIELD,
          { name: 'controls', required: true, selector: { text: {} } },
          { name: 'keep_pad_layout', selector: { boolean: {} } },
          { name: 'per_row', selector: { number: { min: 1, max: 20, step: 1, mode: 'box' } } },
          { name: 'title', selector: { text: {} } },
        ], true),
        section('Appearance', 'mdi:palette-outline', [
          { name: 'show_card_background', selector: { boolean: {} } },
          { name: 'show_pad_body', selector: { boolean: {} } },
        ]),
        section('Extras', 'mdi:creation-outline', [
          { name: 'press_effect', selector: { boolean: {} } },
          { name: 'show_pad_presses', selector: { boolean: {} } },
        ]),
        section('Pictures', 'mdi:image-outline', [
          { name: 'scale', selector: { number: { min: 1, max: 3, step: 1, mode: 'box' } } },
        ]),
      ],
      computeLabel: (s) => LABELS[s.name],
      computeHelper: (s) => HELPERS[s.name],
    };
  }

  static getStubConfig(hass) {
    return { device_id: StreamDockCard.getStubConfig(hass).device_id, controls: '1', show_card_background: true };
  }

  getCardSize() {
    const layout = this._layout;
    const header = this._config && this._config.title ? 1 : 0;
    return Math.max(1, Math.ceil(layout ? (150 * layout.height) / layout.width / 50 : 3) + header);
  }

  getGridOptions() {
    return { columns: 3, min_columns: 2, rows: 'auto', min_rows: 1 };
  }

  /** Only the chosen controls; without the pad round them, unless asked for. */
  _laidOut(layout, body) {
    const config = this._config || {};
    const focused = focusLayout(layout, config.focus || [], {
      asOnPad: config.keep_pad_layout === true,
      perRow: config.keep_pad_layout ? 0 : config.per_row,
    });
    if (!focused) return null;
    const bare = !(this._config && this._config.show_pad_body);
    // A sliver of room so a key's shadow and ring aren't cut off.
    const computed = laidOut(focused, bare ? { ...(body || {}), front: null, edge: 0.06 } : body);
    if (bare) computed.look.bare = true;
    return computed;
  }

  _nothingToShow() {
    const asked = this._config && this._config.focus.length ? this._config.focus.map(humanizeControl).join(', ') : '';
    return asked ? `This pad has no ${asked}.` : 'Choose which key to show in the card settings.';
  }

  /** Each key shows its own part of Mini Monitor: one picture across a few keys would be squeezed. */
  _onFrame(event) {
    super._onFrame({ ...event, seamless: false });
  }
}

/* ------------------------------------------------------------------ */
/* Mini Monitor as one screen: custom:stream-dock-screen-card           */
/* ------------------------------------------------------------------ */

export function normaliseScreenConfig(config) {
  if (!config || typeof config !== 'object') throw new Error('Invalid configuration');
  const out = normaliseConfig({ show_profile: false, ...config });
  out.show_turn_on = out.show_turn_on !== false;
  out.mouse = out.mouse === true;
  out.show_page_buttons = false;
  out.tilt = false;
  out.show_pad_presses = false;
  return out;
}

/** The screen card's words for where Mini Monitor is: null once its picture shows. */
export function screenNote({ pad = null, frames = false, canTurnOn = false } = {}) {
  if (frames || !pad) return null;
  if (pad.mini_monitor === null || pad.mini_monitor === undefined) {
    return { text: "This pad can't show Mini Monitor.", button: false };
  }
  if (pad.mini_monitor !== true) return { text: 'Mini Monitor is off.', button: canTurnOn };
  return { text: 'Waiting for the screen…', button: false };
}

export class StreamDockScreenCard extends StreamDockCard {
  static normalise(config) {
    return normaliseScreenConfig(config);
  }

  static getConfigForm() {
    return {
      schema: [
        section('Pad', 'mdi:monitor-screenshot', [DEVICE_FIELD, { name: 'title', selector: { text: {} } }], true),
        section('Appearance', 'mdi:palette-outline', [
          { name: 'show_card_background', selector: { boolean: {} } },
          { name: 'show_turn_on', selector: { boolean: {} } },
        ]),
        section('Mouse', 'mdi:mouse', [{ name: 'mouse', selector: { boolean: {} } }]),
      ],
      computeLabel: (s) => LABELS[s.name],
      computeHelper: (s) => HELPERS[s.name],
    };
  }

  static getStubConfig(hass) {
    return StreamDockCard.getStubConfig(hass);
  }

  getCardSize() {
    return 5 + (this._config && this._config.title ? 1 : 0);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 4, rows: 'auto', min_rows: 2 };
  }

  /** Key pictures aren't shown here: ask for the smallest. */
  _desiredScale() {
    return 1;
  }

  _laidOut(_layout, body) {
    const look = { ...bodyLook({ ...(body || {}), front: null }), bare: true };
    return { version: 'screen', width: 16, height: 9, items: [], strip: null, look };
  }

  _buildControls(layout) {
    this._layout = layout;
    if (!this._built) return;
    this._els.clear();
    if (!this._padEl.querySelector('.screen')) {
      this._padEl.innerHTML = `
        <div class="screen"><div class="shot"></div>
          <div class="badge" title="The mouse works here"><svg viewBox="0 0 24 24"><path d="M11 1.07C7.05 1.56 4 4.92 4 9h7V1.07M13 1.07V9h7c0-4.08-3.05-7.44-7-7.93M4 15c0 4.42 3.58 8 8 8s8-3.58 8-8v-4H4v4z"/></svg></div>
          <div class="screen-off" hidden><span class="what"></span><button type="button" hidden>Turn on Mini Monitor</button></div>
        </div>`;
      this._padEl.querySelector('.screen-off button').addEventListener('click', () => this._turnOn());
      this._bindMouse(this._padEl.querySelector('.screen'));
    }
    if (!this._screenSize) {
      this._frame.style.setProperty('--bw', '16');
      this._frame.style.setProperty('--bh', '9');
    }
    this._applyBody(layout.look);
  }

  /** The card takes the screen's own shape. */
  _onFrame(event) {
    const W = num(event && event.width);
    const H = num(event && event.height);
    if (W > 0 && H > 0 && this._screenSize !== `${W}x${H}`) {
      this._screenSize = `${W}x${H}`;
      this._frame.style.setProperty('--bw', String(W));
      this._frame.style.setProperty('--bh', String(H));
    }
    super._onFrame({ ...event, seamless: false });
  }

  _placeFrameParts() {}

  _overlayFor(state) {
    const overlay = padOverlay(state);
    return overlay && (overlay.kind === 'mini_monitor' || overlay.kind === 'screen_off' || overlay.kind === 'unplugged') ? null : overlay;
  }

  _renderChrome() {
    super._renderChrome();
    const screen = this._screenEl;
    if (screen) {
      screen.classList.toggle('mouse', !!(this._config && this._config.mouse));
      screen.classList.toggle('live', !!this._frameUrl);
    }
    const off = this._built && this._padEl.querySelector('.screen-off');
    if (!off) return;
    const found = this._entities || {};
    const note = screenNote({
      pad: this._pad,
      frames: !!this._frameUrl,
      canTurnOn: this._config.show_turn_on !== false && !!found.mini_monitor && this._online,
    });
    off.hidden = !note;
    if (note) {
      off.querySelector('.what').textContent = note.text;
      off.querySelector('button').hidden = !note.button;
    }
  }

  _turnOn() {
    const found = this._entities || {};
    if (found.mini_monitor) this._call('switch', 'turn_on', { entity_id: found.mini_monitor });
  }

  /* ---------- The mouse (protocol 5.4) ---------- */

  _mouseOn() {
    return !!(this._config && this._config.mouse && this._frameUrl && this._padId && this._hass);
  }

  _bindMouse(screen) {
    this._screenEl = screen;
    this._mouse = new MouseQueue((item) => this._hass.callWS({ type: 'stream_dock_ha/mouse', pad_id: this._padId, ...item }));
    this._mouse.onError = (err) => {
      const now = Date.now();
      if (now - (this._mouseToastAt || 0) < 4000) return;
      this._mouseToastAt = now;
      this._toast(mouseErrorText(err));
    };
    const at = (e) => {
      const r = screen.getBoundingClientRect();
      const part = (v, from, size) => (size > 0 ? Math.min(1, Math.max(0, (v - from) / size)) : 0.5);
      return { x: part(e.clientX, r.left, r.width), y: part(e.clientY, r.top, r.height) };
    };
    screen.addEventListener('pointerdown', (e) => {
      if (!this._mouseOn() || this._held) return;
      const button = e.pointerType === 'mouse' ? MOUSE_BUTTONS[e.button] : 'left';
      if (!button) return;
      e.preventDefault();
      try { screen.setPointerCapture(e.pointerId); } catch (_err) { /* not capturable */ }
      const point = at(e);
      const held = { pointerId: e.pointerId, button, point, x: e.clientX, y: e.clientY, touch: e.pointerType !== 'mouse', down: false, done: false };
      this._held = held;
      if (!held.touch) {
        held.down = true;
        this._mouse.push({ action: 'down', ...point, button });
      } else {
        // A finger: a tap clicks, a drag drags, a long press right-clicks.
        held.timer = setTimeout(() => {
          held.done = true;
          this._mouse.push({ action: 'click', ...held.point, button: 'right' });
        }, LONG_PRESS_MS);
      }
    });
    screen.addEventListener('pointermove', (e) => {
      const held = this._held;
      if (!held) {
        // Hovering with a mouse moves the pointer too, a few times a second.
        if (e.pointerType === 'mouse' && this._mouseOn() && Date.now() - (this._hoverAt || 0) > 100) {
          this._hoverAt = Date.now();
          this._mouse.push({ action: 'move', ...at(e) });
        }
        return;
      }
      if (held.pointerId !== e.pointerId || held.done) return;
      if (held.touch && !held.down) {
        if (Math.hypot(e.clientX - held.x, e.clientY - held.y) < DRAG_PX) return;
        clearTimeout(held.timer);
        held.down = true;
        this._mouse.push({ action: 'down', ...held.point, button: held.button });
      }
      this._mouse.push({ action: 'move', ...at(e) });
    });
    const end = (e, cancelled) => {
      const held = this._held;
      if (!held || held.pointerId !== e.pointerId) return;
      this._held = null;
      clearTimeout(held.timer);
      if (held.done) return;
      const point = cancelled ? held.point : at(e);
      if (!held.down) {
        if (!cancelled) this._mouse.push({ action: 'click', ...held.point, button: 'left' });
        return;
      }
      this._mouse.push({ action: 'up', ...point, button: held.button });
    };
    screen.addEventListener('pointerup', (e) => end(e, false));
    screen.addEventListener('pointercancel', (e) => end(e, true));
    screen.addEventListener('contextmenu', (e) => { if (this._config && this._config.mouse) e.preventDefault(); });
    screen.addEventListener('wheel', (e) => {
      if (!this._mouseOn()) return;
      e.preventDefault();
      const notches = wheelNotches(this, e);
      if (notches) this._mouse.push({ action: 'scroll', ...at(e), amount: notches });
    }, { passive: false });
  }

}

/** Which button a mouse's `button` is. */
const MOUSE_BUTTONS = ['left', 'middle', 'right'];
/** How long a finger stays still for a right-click, in ms. */
const LONG_PRESS_MS = 550;
/** How far a finger moves before it drags, in CSS pixels. */
const DRAG_PX = 8;

/**
 * Sends the card's mouse to Home Assistant one at a time and in order, so a
 * drag arrives as down, moves, up. While one is on its way, moves in a row
 * are merged into the latest, so a slow connection doesn't fall behind.
 */
export class MouseQueue {
  constructor(send) {
    this._send = send;
    this._items = [];
    this._busy = false;
    this.onError = null;
  }

  push(item) {
    const last = this._items[this._items.length - 1];
    if (item.action === 'move' && last && last.action === 'move') this._items[this._items.length - 1] = item;
    else this._items.push(item);
    this._run();
  }

  async _run() {
    if (this._busy) return;
    this._busy = true;
    while (this._items.length) {
      const item = this._items.shift();
      try {
        await this._send(item);
      } catch (err) {
        if (this.onError) this.onError(err);
      }
    }
    this._busy = false;
  }
}

/** Wheel notches from a wheel event, keeping the rest of a partial one: positive is away from you. */
export function wheelNotches(holder, e) {
  const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 400 : 1;
  holder._wheel = (holder._wheel || 0) + e.deltaY * unit;
  const notches = Math.trunc(holder._wheel / 100);
  holder._wheel -= notches * 100;
  return notches ? -notches : 0;
}

/** The short message shown when the mouse doesn't work. */
export function mouseErrorText(err) {
  const code = err && typeof err === 'object' ? err.code : undefined;
  const message = err && typeof err === 'object' && typeof err.message === 'string' ? err.message.trim() : '';
  switch (code) {
    case 'unauthorized': return 'Only administrators can use the mouse here';
    case 'offline': return 'The PC is offline';
    case 'control_off': return 'Home Assistant control is off in the app';
    case 'unknown_command': return 'Update the Stream Dock HA integration to use the mouse';
    default: return message || (code ? String(code) : "The mouse didn't reach the PC");
  }
}

/* ------------------------------------------------------------------ */
/* Registration                                                         */
/* ------------------------------------------------------------------ */

const CARDS = [
  [CARD_TYPE, StreamDockCard, 'Stream Dock pad', 'A live Stream Dock pad: see its keys and press them from the dashboard.'],
  [KEY_CARD_TYPE, StreamDockKeyCard, 'Stream Dock key', 'One key of a Stream Dock pad, or a few, live and pressable.'],
  [SCREEN_CARD_TYPE, StreamDockScreenCard, 'Stream Dock Mini Monitor', "A pad's Mini Monitor as one screen, in its own shape."],
];

if (typeof customElements !== 'undefined') {
  for (const [type, element] of CARDS) {
    if (!customElements.get(type)) customElements.define(type, element);
  }
  // eslint-disable-next-line no-console
  console.info(`%c STREAM-DOCK-CARD %c ${CARD_VERSION} `, 'background:#222;color:#fff', 'background:#ffa600;color:#000');
}

if (typeof window !== 'undefined') {
  window.customCards = window.customCards || [];
  for (const [type, , name, description] of CARDS) {
    if (!window.customCards.some((c) => c && c.type === type)) {
      window.customCards.push({ type, name, description, preview: false });
    }
  }
}

/*
 * Stream Dock pad card: custom:stream-dock-card
 *
 * Shows a live "virtual stream dock" for one pad of the Stream Dock HA app.
 * Pressing a key here presses the real one. Served by the stream_dock_ha
 * integration; see docs/protocol.md, sections 3.2, 3.4, 5 and 6.
 *
 * One self-contained ES module: no build step, no network imports.
 */

const CARD_TYPE = 'stream-dock-card';
const CARD_VERSION = '0.1.0';

/** Picture sizes at scale 1 (protocol 3.4). */
const KEY_PX = 85;
/** Room around the controls on the pad body, in key units. */
const BODY_MARGIN = 0.3;
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
  return {
    version: layout && layout.version != null ? String(layout.version) : null,
    width,
    height,
    items,
  };
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
 * `dim` darkens the pictures. Only the most important one is shown.
 */
export function padOverlay({ online = true, linkDown = false, pad = null } = {}) {
  if (linkDown) return { kind: 'link', text: 'Reconnecting to Home Assistant…', sub: '', dim: true, block: true };
  if (online === false) return { kind: 'offline', text: 'PC offline', sub: 'Showing the last pictures', dim: true, block: true };
  if (!pad) return null;
  if (pad.connected === false) return { kind: 'unplugged', text: 'Pad unplugged', sub: 'Keys still run on the PC', dim: false, block: false };
  if (pad.screen_on === false) return { kind: 'screen_off', text: 'Screen off — press to wake', sub: '', dim: true, block: false };
  if (pad.mini_monitor === true) return { kind: 'mini_monitor', text: 'Mini Monitor is on', sub: 'The pad shows the PC screen', dim: false, block: false };
  return null;
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
  out.show_name = out.show_name !== false;
  out.show_profile = out.show_profile !== false;
  out.haptic = out.haptic !== false;
  return out;
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
  --bw: 7; --bh: 4;
  aspect-ratio: var(--bw) / var(--bh);
  --u: calc(100cqw / var(--bw));
  -webkit-tap-highlight-color: transparent;
  user-select: none; -webkit-user-select: none;
}
.frame[hidden] { display: none; }
.pad {
  position: absolute; inset: 0;
  border-radius: calc(var(--u) * 0.32);
  background:
    radial-gradient(120% 90% at 30% 0%, rgba(255,255,255,.07), rgba(255,255,255,0) 60%),
    linear-gradient(180deg, #24262a 0%, #17181b 100%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08), inset 0 -2px 6px rgba(0,0,0,.5),
    0 2px 6px rgba(0,0,0,.25);
  transition: filter .25s ease;
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
  border-radius: 11%;
  background: #08090a;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.06), 0 calc(var(--u) * .03) calc(var(--u) * .06) rgba(0,0,0,.6);
  overflow: hidden;
}
.band { border-radius: 9%; }
.key img, .band img {
  position: absolute; inset: 0; width: 100%; height: 100%; display: block;
  object-fit: cover; pointer-events: none; -webkit-user-drag: none;
}
.key:not(.pic) img, .band:not(.pic) img { display: none; }
.key.down { transform: scale(.92); filter: brightness(.82); transition-duration: .05s; }

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
  pointer-events: none; border-radius: calc(var(--u) * .32);
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
}
`;

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
  }

  /* ---------- Lovelace API ---------- */

  static getConfigForm() {
    return {
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
        {
          type: 'grid',
          name: '',
          schema: [
            { name: 'show_name', selector: { boolean: {} } },
            { name: 'show_profile', selector: { boolean: {} } },
            { name: 'haptic', selector: { boolean: {} } },
          ],
        },
        { name: 'scale', selector: { number: { min: 1, max: 3, step: 1, mode: 'box' } } },
      ],
      computeLabel: (s) => ({
        device_id: 'Pad',
        show_name: 'Show name',
        show_profile: 'Show profile',
        haptic: 'Vibrate on press',
        scale: 'Picture scale (empty: automatic)',
      })[s.name],
      computeHelper: (s) => (s.name === 'scale'
        ? 'Leave empty to match the screen. 1 is sharpest on small cards, 3 on big high-DPI screens.'
        : undefined),
    };
  }

  static getStubConfig(hass) {
    const entities = hass && hass.entities ? Object.values(hass.entities) : [];
    const select = entities.find((e) => e && e.platform === 'stream_dock_ha'
      && typeof e.entity_id === 'string' && e.entity_id.startsWith('select.') && e.device_id);
    return {
      device_id: select ? select.device_id : '',
      show_name: true,
      show_profile: true,
    };
  }

  setConfig(config) {
    const next = normaliseConfig(config);
    const prev = this._config;
    this._config = next;
    if (prev && (prev.device_id !== next.device_id || prev.pad_id !== next.pad_id)) {
      this._device = null;
    }
    if (this._built) this._renderChrome();
    this._sync();
  }

  set hass(hass) {
    this._hass = hass;
    this._sync();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    const layout = this._layout || this._cachedLayout();
    const header = this._config && (this._config.show_name || this._config.show_profile) ? 1 : 0;
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
    this._sync();
  }

  disconnectedCallback() {
    this._stopWatch();
    this._unbindConnection();
    if (this._ro) { this._ro.disconnect(); this._ro = null; }
    clearTimeout(this._resizeTimer);
    this._releaseDown();
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
          <div class="toast" role="status" aria-live="polite"></div>
        </div>
      </ha-card>`;
    this._header = root.querySelector('.header');
    this._nameEl = root.querySelector('.name');
    this._detailEl = root.querySelector('.detail');
    this._chipEl = root.querySelector('.chip');
    this._messageEl = root.querySelector('.message');
    this._frame = root.querySelector('.frame');
    this._padEl = root.querySelector('.pad');
    this._overlayEl = root.querySelector('.overlay');
    this._toastEl = root.querySelector('.toast');

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
      if (!padId) return; // message already shown
    }
    if (!padId) {
      this._stopWatch();
      this._showMessage('Choose a Stream Dock pad in the card settings.');
      return;
    }

    if (padId !== this._padId) this._resetPad(padId);
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
    } catch (err) {
      if (this._watch !== watch) return;
      watch.failed = true; // keep it, so we don't retry on every hass update
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
    if (!d || d.conn !== conn || d.deviceId !== deviceId) {
      const entry = { conn, deviceId, padId: null, promise: null };
      entry.promise = conn.sendMessagePromise
        ? conn.sendMessagePromise({ type: 'stream_dock_ha/pads' })
        : this._hass.callWS({ type: 'stream_dock_ha/pads' });
      entry.promise = entry.promise.then(
        (result) => {
          entry.padId = resolvePadId({ device_id: deviceId }, result);
          if (!entry.padId) this._showMessage("This device isn't a Stream Dock pad.", true);
          return entry.padId;
        },
        (err) => {
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

  _bindConnection(conn) {
    if (this._conn === conn) return;
    this._unbindConnection();
    this._stopWatch();
    this._device = null;
    this._conn = conn;
    const onReady = () => {
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
    const layout = this._padId && layoutCache.get(this._padId);
    return layout ? computeLayout(layout) : null;
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
  }

  _onPad(event) {
    this._online = event.online !== false;
    const pad = event.pad && typeof event.pad === 'object' ? event.pad : this._pad;
    this._pad = pad;
    this._loaded = true;
    this._message = null;
    if (pad && pad.layout) {
      const version = pad.layout.version != null ? String(pad.layout.version) : JSON.stringify(pad.layout.controls || []);
      if (!this._layout || this._layout.version !== version) {
        layoutCache.set(this._padId, pad.layout);
        const computed = computeLayout(pad.layout);
        computed.version = version;
        this._buildControls(computed);
        // The real layout can change the key size: check the scale.
        if (this._config.scale == null && this._watch) {
          const scale = this._measureScale();
          if (scale && scale !== this._watch.scale) this._sync();
        }
      }
    }
    this._renderChrome();
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
    for (const name of this._els.keys()) this._applyPicture(name);
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

    // Header
    const name = (pad && pad.name) || '';
    const detail = headerDetail(pad, cfg.show_profile);
    const showHeader = (cfg.show_name && !!name) || !!detail;
    this._header.hidden = !showHeader;
    this._nameEl.textContent = cfg.show_name ? name : '';
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
    const overlay = padOverlay({ online: this._online, linkDown: this._linkDown, pad });
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
    this._haptic();
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
    setTimeout(() => this._showDown(el, false), MIN_PRESS_MS + 40);
    this._haptic();
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

  _haptic() {
    if (this._config && this._config.haptic === false) return;
    this.dispatchEvent(new CustomEvent('haptic', { detail: 'light', bubbles: true, composed: true }));
  }

  async _press(control) {
    if (!control || !this._hass || !this._padId) return;
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
/* Registration                                                         */
/* ------------------------------------------------------------------ */

if (typeof customElements !== 'undefined' && !customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, StreamDockCard);
  // eslint-disable-next-line no-console
  console.info(`%c STREAM-DOCK-CARD %c ${CARD_VERSION} `, 'background:#222;color:#fff', 'background:#ffa600;color:#000');
}

if (typeof window !== 'undefined') {
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c && c.type === CARD_TYPE)) {
    window.customCards.push({
      type: CARD_TYPE,
      name: 'Stream Dock pad',
      description: 'A live Stream Dock pad: see its keys and press them from the dashboard.',
      preview: false,
    });
  }
}

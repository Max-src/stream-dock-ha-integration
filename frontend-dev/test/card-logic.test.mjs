// Unit tests for the card's pure logic. Run: node --test frontend-dev/test
import { test, mock } from 'node:test';
import assert from 'node:assert/strict';
import {
  clampScale, chooseScale, keySizePx, computeLayout, mergePictures, humanizeControl,
  pressErrorText, padOverlay, resolvePadId, headerDetail, normaliseConfig, StreamDockCard,
  retryDelayMs, RETRY_DELAYS_MS, bodyLook, laidOut, frameParts,
} from '../../custom_components/stream_dock_ha/frontend/stream-dock-card.js';
import { layout293s, layoutAkp03e, layoutDashboard, bodyWhite, bodyClear } from '../layouts.mjs';

test('clampScale keeps 1..3 and rounds', () => {
  assert.equal(clampScale(0), 1);
  assert.equal(clampScale(1.4), 1);
  assert.equal(clampScale(2.6), 3);
  assert.equal(clampScale(9), 3);
  assert.equal(clampScale('x'), 2);
  assert.equal(clampScale(undefined, 1), 1);
});

test('chooseScale follows key size times devicePixelRatio', () => {
  assert.equal(chooseScale(60, 1), 1);
  assert.equal(chooseScale(85, 1), 1);
  assert.equal(chooseScale(100, 1), 1); // 18 % upscaling is fine
  assert.equal(chooseScale(110, 1), 2);
  assert.equal(chooseScale(60, 2), 2); // 120 device px
  assert.equal(chooseScale(85, 2), 2);
  assert.equal(chooseScale(85, 3), 3);
  assert.equal(chooseScale(400, 3), 3); // clamped
  assert.equal(chooseScale(0, 2), 2); // unknown size: protocol default
  assert.equal(chooseScale(50, 0), 1); // bad dpr counts as 1
});

test('keySizePx', () => {
  assert.equal(keySizePx(892, 8.92), 100);
  assert.equal(keySizePx(0, 5), 0);
  assert.equal(keySizePx(400, 0), 0);
});

test('computeLayout: 293S body, boxes and margins', () => {
  const l = computeLayout(layout293s, 0.3);
  assert.equal(l.version, layout293s.version);
  // 5 keys a quarter apart, then the band at 6.25 + 0.82 = 7.07, plus margins.
  assert.ok(Math.abs(l.width - (7.07 + 0.6)) < 1e-9, `width ${l.width}`);
  assert.ok(Math.abs(l.height - (3.5 + 0.6)) < 1e-9, `height ${l.height}`);
  assert.equal(l.items.filter((i) => i.kind === 'key').length, 15);
  assert.equal(l.items.filter((i) => i.kind === 'band').length, 3);
  const key7 = l.items.find((i) => i.name === 'key_7');
  assert.ok(Math.abs(key7.left - (1 * 1.25 + 0.3)) < 1e-9);
  assert.ok(Math.abs(key7.top - (1 * 1.25 + 0.3)) < 1e-9);
  assert.ok(Math.abs(key7.box.width - (1 / l.width) * 100) < 1e-9);
  const band = l.items.find((i) => i.name === 'band_1');
  assert.equal(band.press, false);
  assert.equal(band.screen, true);
  // The band tiles sit on one strip, from the top of the first to the bottom of the last.
  const band3 = l.items.find((i) => i.name === 'band_3');
  assert.ok(Math.abs(l.strip.box.top - band.box.top) < 1e-9);
  assert.ok(Math.abs(l.strip.box.top + l.strip.box.height - (band3.box.top + band3.box.height)) < 1e-9);
  assert.ok(Math.abs(l.strip.box.width - band.box.width) < 1e-9);
  assert.equal(l.strip.w, 0.82);
  assert.equal(computeLayout(layoutDashboard).strip, null);
});

test('bodyLook: the front, corners and edge from the app, with safe fallbacks', () => {
  const white = bodyLook(bodyWhite);
  assert.deepEqual(white, {
    front: 'rgb(255, 255, 255)', clear: false, light: true,
    edge: 0.3, corner: 0.3, keyCorner: 0.165, bandCorner: 0.175,
  });
  const clear = bodyLook(bodyClear);
  assert.equal(clear.front, null);
  assert.equal(clear.clear, true);
  assert.equal(clear.keyCorner, 0.5);
  assert.equal(bodyLook({ front: [10, 20, 30] }).light, false);
  // An older app sends no body: the card's own dark pad, not a see-through one.
  const none = bodyLook(undefined);
  assert.equal(none.front, null);
  assert.equal(none.clear, false);
  assert.equal(none.edge, 0.3);
  // Nonsense is clamped or ignored.
  const odd = bodyLook({ front: [300, -5, 'x'], key_corner: 9, edge: -1, corner: null });
  assert.equal(odd.front, null);
  assert.equal(odd.keyCorner, 0.5);
  assert.equal(odd.edge, 0.3);
  assert.equal(odd.corner, 0.32);
  assert.equal(bodyLook({ front: [300, -5, 7.6] }).front, 'rgb(255, 0, 8)');
});

test('laidOut: the edge from the body, and a version that follows it', () => {
  const a = laidOut(layout293s, bodyWhite);
  assert.ok(Math.abs(a.width - (7.07 + 0.6)) < 1e-9);
  assert.equal(a.look.front, 'rgb(255, 255, 255)');
  const b = laidOut(layout293s, { ...bodyWhite, edge: 0.5 });
  assert.ok(Math.abs(b.width - (7.07 + 1.0)) < 1e-9);
  assert.notEqual(a.version, b.version);
  // A colour alone keeps the version: the controls aren't rebuilt for it.
  assert.equal(laidOut(layout293s, { ...bodyWhite, front: [0, 0, 0] }).version, a.version);
});

test('computeLayout: grows the body when controls lie outside width/height', () => {
  // protocol.md's own example has band_1 at x 7.98 with width 7.08.
  const l = computeLayout({ version: 'v', width: 7.08, height: 4.12, controls: [
    { name: 'key_1', type: 'key', x: 0, y: 0, w: 1, h: 1, screen: true, press: true },
    { name: 'band_1', type: 'band', x: 7.98, y: 0, w: 0.94, h: 0.94, screen: true, press: false },
  ] }, 0);
  assert.ok(Math.abs(l.width - 8.92) < 1e-9);
  const band = l.items.find((i) => i.name === 'band_1');
  assert.ok(band.box.left + band.box.width <= 100 + 1e-9);
});

test('computeLayout: knob parts become one knob item', () => {
  const l = computeLayout(layoutAkp03e);
  const knobs = l.items.filter((i) => i.kind === 'knob');
  assert.equal(knobs.length, 3);
  const top = knobs.find((k) => k.group === 'top_knob');
  assert.deepEqual(Object.keys(top.parts).sort(), ['left', 'press', 'right']);
  assert.equal(top.parts.left.name, 'top_knob_left');
  assert.equal(l.items.filter((i) => i.kind === 'button').length, 3);
  assert.equal(l.items.filter((i) => i.kind === 'key').length, 6);
});

test('computeLayout: knob without group, unknown type, bad input', () => {
  const l = computeLayout({ controls: [
    { name: 'dial_knob_left', type: 'knob_left', x: 0, y: 0, w: 1, h: 1 },
    { name: 'dial_knob_press', type: 'knob_press', x: 0, y: 0, w: 1, h: 1, press: false },
    { name: 'strip_1', type: 'touch_strip', x: 1, y: 0, w: 2, h: 0.5, screen: true, press: true },
    { type: 'key' }, null,
  ] });
  assert.equal(l.items.length, 2);
  assert.equal(l.items[0].group, 'dial_knob');
  assert.equal(l.items[0].parts.press.press, false);
  assert.equal(l.items[1].kind, 'key');
  assert.deepEqual(computeLayout(null).items, []);
});

test('mergePictures: partial merge, null and unchanged hashes', () => {
  const a = { hash: 'a', data: 'AAA' };
  const b = { hash: 'b', data: 'BBB' };
  let r = mergePictures(new Map(), { complete: true, pictures: { key_1: a, key_2: b, key_3: null } });
  assert.deepEqual(r.changed.sort(), ['key_1', 'key_2']);
  assert.equal(r.pictures.size, 2);

  r = mergePictures(r.pictures, { complete: false, pictures: { key_1: { hash: 'a', data: 'AAA' }, key_2: null } });
  assert.deepEqual(r.changed, ['key_2']);
  assert.equal(r.pictures.has('key_2'), false);
  assert.equal(r.pictures.get('key_1').hash, 'a');

  r = mergePictures(r.pictures, { pictures: { key_1: { hash: 'a2', data: 'A2' } } });
  assert.deepEqual(r.changed, ['key_1']);
});

test('mergePictures: complete replaces, absent becomes empty', () => {
  const prev = new Map([['key_1', { hash: '1', data: 'x' }], ['key_2', { hash: '2', data: 'y' }]]);
  const r = mergePictures(prev, { complete: true, pictures: { key_2: { hash: '2', data: 'y' } } });
  assert.deepEqual(r.changed, ['key_1']);
  assert.deepEqual([...r.pictures.keys()], ['key_2']);
  assert.notEqual(r.pictures, prev, 'returns a new Map');
  assert.equal(prev.size, 2, 'does not mutate the old Map');
});

test('mergePictures: compares data when hash is missing, ignores junk', () => {
  const prev = new Map([['k', { hash: null, data: 'x' }]]);
  assert.deepEqual(mergePictures(prev, { pictures: { k: { data: 'x' } } }).changed, []);
  assert.deepEqual(mergePictures(prev, { pictures: { k: { data: 'y' } } }).changed, ['k']);
  assert.deepEqual(mergePictures(prev, { pictures: { k: { hash: 'h' } } }).changed, ['k']); // no data = empty
  assert.deepEqual(mergePictures(prev, null).changed, []);
});

test('humanizeControl', () => {
  assert.equal(humanizeControl('key_3'), 'Key 3');
  assert.equal(humanizeControl('button_1'), 'Button 1');
  assert.equal(humanizeControl('band_2'), 'Band 2');
  assert.equal(humanizeControl('top_knob_left'), 'Top knob, turn left');
  assert.equal(humanizeControl('lower_right_knob_right'), 'Lower right knob, turn right');
  assert.equal(humanizeControl('lower_left_knob_press'), 'Lower left knob, press');
});

test('pressErrorText', () => {
  assert.equal(pressErrorText({ code: 'failed', message: 'not allowed from Home Assistant' }), 'not allowed from Home Assistant');
  assert.equal(pressErrorText({ code: 'offline', message: 'whatever' }), 'The PC is offline');
  assert.equal(pressErrorText({ code: 'control_off' }), 'Home Assistant control is off in the app');
  assert.equal(pressErrorText({ code: 'unauthorized' }), 'Only administrators can press keys here');
  assert.equal(pressErrorText({ code: 'weird', message: 'Strange' }), 'Strange');
  assert.equal(pressErrorText({ code: 'weird' }), 'weird');
  assert.equal(pressErrorText(undefined), "Couldn't press the key");
});

test('padOverlay priorities', () => {
  const pad = { connected: true, screen_on: true, mini_monitor: false };
  assert.equal(padOverlay({ pad }), null);
  assert.equal(padOverlay({ online: false, pad: { ...pad, mini_monitor: true } }).kind, 'offline');
  assert.equal(padOverlay({ online: false, pad }).block, true);
  assert.equal(padOverlay({ linkDown: true, pad }).kind, 'link');
  const unplugged = padOverlay({ pad: { ...pad, connected: false } });
  assert.equal(unplugged.kind, 'unplugged');
  assert.equal(unplugged.block, false, 'unplugged pads stay pressable');
  const off = padOverlay({ pad: { ...pad, screen_on: false } });
  assert.equal(off.text, 'Screen off — press to wake');
  assert.equal(off.dim, true);
  assert.equal(off.block, false);
  assert.equal(padOverlay({ pad: { ...pad, mini_monitor: true } }).text, 'Mini Monitor is on');
  // Once its pictures show on the keys, no word is needed.
  assert.equal(padOverlay({ pad: { ...pad, mini_monitor: true }, frames: true }), null);
  assert.equal(padOverlay({ pad: { ...pad, mini_monitor: null } }), null);
});

test('resolvePadId', () => {
  const pads = { pads: [{ pad_id: 'aaaa', device_id: 'dev1' }, { pad_id: 'bbbb', device_id: 'dev2' }] };
  assert.equal(resolvePadId({ device_id: 'dev2' }, pads), 'bbbb');
  assert.equal(resolvePadId({ device_id: 'nope' }, pads), null);
  assert.equal(resolvePadId({ pad_id: 'cccc' }, pads), 'cccc');
  assert.equal(resolvePadId({ pad_id: 'cccc', device_id: 'dev1' }, pads), 'aaaa', 'device_id wins');
  assert.equal(resolvePadId({}, pads), null);
});

test('headerDetail', () => {
  const pad = { profile: { name: 'Home' }, page: 2, pages: 3 };
  assert.equal(headerDetail(pad, true), 'Home · 2 / 3');
  assert.equal(headerDetail({ ...pad, pages: 1 }, true), 'Home');
  assert.equal(headerDetail(pad, false), '');
  assert.equal(headerDetail(null, true), '');
});

test('normaliseConfig', () => {
  assert.deepEqual(normaliseConfig({ pad_id: 'x' }), { pad_id: 'x', show_name: true, show_profile: true });
  assert.equal(normaliseConfig({ pad_id: 'x', scale: '3' }).scale, 3);
  assert.equal('scale' in normaliseConfig({ pad_id: 'x', scale: '' }), false);
  assert.throws(() => normaliseConfig({ pad_id: 'x', scale: 5 }));
  assert.throws(() => normaliseConfig(null));
  // The old vibrate setting is dropped.
  assert.equal('haptic' in normaliseConfig({ haptic: false }), false);
});

test('config form and Lovelace hooks', () => {
  const form = StreamDockCard.getConfigForm();
  const device = form.schema.find((s) => s.name === 'device_id');
  assert.deepEqual(device.selector.device.filter, [{ integration: 'stream_dock_ha' }]);
  assert.equal(device.selector.device.entity[0].domain, 'select');
  const stub = StreamDockCard.getStubConfig({ entities: {
    'select.desk_pad_profile': { entity_id: 'select.desk_pad_profile', platform: 'stream_dock_ha', device_id: 'dev9' },
  } });
  assert.equal(stub.device_id, 'dev9');
  assert.equal(StreamDockCard.getStubConfig(undefined).device_id, '');
});

test('retryDelayMs: 2 s, 5 s, 15 s, 30 s, then every 30 s', () => {
  assert.deepEqual(RETRY_DELAYS_MS, [2000, 5000, 15000, 30000]);
  assert.deepEqual([0, 1, 2, 3, 4, 5, 50].map(retryDelayMs), [2000, 5000, 15000, 30000, 30000, 30000, 30000]);
  assert.equal(retryDelayMs(-1), 2000);
  assert.equal(retryDelayMs(undefined), 2000);
  assert.equal(retryDelayMs(NaN), 2000);
  assert.equal(retryDelayMs(1.7), 5000);
});

// A card without a DOM: enough for the connection logic.
function headlessCard(config) {
  const card = new StreamDockCard();
  Object.defineProperty(card, 'isConnected', { value: true, configurable: true });
  card._config = normaliseConfig(config);
  card.syncs = 0;
  card._sync = () => { card.syncs += 1; };
  return card;
}

test('a failed device lookup is retried with backoff, not cached', async (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  let calls = 0;
  let fail = true;
  const conn = {
    connected: true,
    sendMessagePromise: async () => {
      calls += 1;
      if (fail) throw { code: 'not_set_up', message: 'Add the integration' };
      return { pads: [{ pad_id: 'p1', device_id: 'd1' }] };
    },
  };
  const card = headlessCard({ device_id: 'd1' });
  card._hass = { connection: conn };

  assert.equal(await card._resolveDevice(conn, 'd1'), null);
  assert.equal(calls, 1);
  // While the retry is pending, hass updates don't ask again.
  assert.equal(await card._resolveDevice(conn, 'd1'), null);
  assert.equal(calls, 1);

  mock.timers.tick(1999);
  assert.equal(card.syncs, 0);
  mock.timers.tick(1);
  assert.equal(card.syncs, 1, 'retried after 2 s');
  assert.equal(card._device, null, 'the failed lookup was dropped');

  // Second failure: the next try waits 5 s.
  assert.equal(await card._resolveDevice(conn, 'd1'), null);
  assert.equal(calls, 2);
  mock.timers.tick(4999);
  assert.equal(card.syncs, 1);
  mock.timers.tick(1);
  assert.equal(card.syncs, 2, 'retried after 5 s more');

  fail = false;
  assert.equal(await card._resolveDevice(conn, 'd1'), 'p1');
  assert.equal(calls, 3);
  assert.equal(await card._resolveDevice(conn, 'd1'), 'p1');
  assert.equal(calls, 3, 'a good lookup is cached');
});

test('a device that is not a pad is not cached either', async (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  let calls = 0;
  const conn = { connected: true, sendMessagePromise: async () => { calls += 1; return { pads: [] }; } };
  const card = headlessCard({ device_id: 'd1' });
  card._hass = { connection: conn };
  assert.equal(await card._resolveDevice(conn, 'd1'), null);
  assert.ok(card._retryTimer, 'a retry is scheduled');
  mock.timers.tick(2000);
  assert.equal(await card._resolveDevice(conn, 'd1'), null);
  assert.equal(calls, 2);
});

test('a failed watch is retried with backoff; success resets it', async (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  let watches = 0;
  let fail = true;
  const conn = {
    connected: true,
    subscribeMessage: async () => {
      watches += 1;
      if (fail) throw { code: 'not_set_up', message: 'Reloading' };
      return () => {};
    },
  };
  const card = headlessCard({ pad_id: 'p1', scale: 2 });
  card._hass = { connection: conn };

  await card._doSync();
  assert.equal(watches, 1);
  assert.equal(card._watch.failed, true);
  await card._doSync(); // a hass update: no new try yet
  assert.equal(watches, 1);

  mock.timers.tick(2000);
  assert.equal(card._watch, null, 'the failed watch was dropped');
  await card._doSync();
  assert.equal(watches, 2);
  mock.timers.tick(4999);
  assert.equal(card._watch.failed, true, 'still waiting for 5 s');
  mock.timers.tick(1);
  fail = false;
  await card._doSync();
  assert.equal(watches, 3);
  assert.equal(card._watch.failed, false);
  assert.equal(card._retryTimer, null);
  assert.equal(card._retryAttempt, 0, 'backoff reset after success');
});

test('no pad id stops the watch; leaving the page stops retrying', async (t) => {
  mock.timers.enable({ apis: ['setTimeout'] });
  t.after(() => mock.timers.reset());
  const conn = { connected: true, sendMessagePromise: async () => ({ pads: [] }) };
  const card = headlessCard({ device_id: 'd1' });
  card._hass = { connection: conn };
  let stopped = false;
  card._watch = { conn, key: 'old|2', unsub: () => { stopped = true; }, failed: false };
  await card._doSync();
  assert.equal(stopped, true, 'the old watch was ended');
  assert.equal(card._watch, null);
  assert.ok(card._retryTimer);
  card._unbindConnection = () => {};
  card.disconnectedCallback();
  assert.equal(card._retryTimer, null);
  assert.equal(card._retryAttempt, 0);
});

test('frameParts: each key shows its own part of the one picture', () => {
  const parts = frameParts({
    width: 600, height: 300,
    tiles: [
      { name: 'key_1', x: 0, y: 0, w: 100, h: 100 },
      { name: 'key_2', x: 250, y: 100, w: 100, h: 100 },
      { name: 'key_3', x: 500, y: 200, w: 100, h: 100 },
      { name: 'bad', x: 550, y: 0, w: 100, h: 100 },
      { name: 'zero', x: 0, y: 0, w: 0, h: 100 },
    ],
  });
  // The picture is drawn 6 keys wide and 3 high behind each key...
  assert.deepEqual(parts.get('key_1'), { size: '600% 300%', position: '0% 0%' });
  // ...shifted so the key's own part shows: CSS positions run 0% to 100%.
  assert.deepEqual(parts.get('key_2'), { size: '600% 300%', position: '50% 50%' });
  assert.deepEqual(parts.get('key_3'), { size: '600% 300%', position: '100% 100%' });
  assert.equal(parts.has('bad'), false, 'outside the picture');
  assert.equal(parts.has('zero'), false);
  assert.equal(frameParts({ width: 0, height: 10, tiles: [] }).size, 0);
  assert.equal(frameParts(null).size, 0);
  // A picture exactly one key big.
  assert.deepEqual(frameParts({ width: 85, height: 85, tiles: [{ name: 'k', x: 0, y: 0, w: 85, h: 85 }] }).get('k'),
    { size: '100% 100%', position: '0% 0%' });
});

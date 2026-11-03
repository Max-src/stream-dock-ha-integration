// Unit tests for the card's pure logic. Run: node --test frontend-dev/test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  clampScale, chooseScale, keySizePx, computeLayout, mergePictures, humanizeControl,
  pressErrorText, padOverlay, resolvePadId, headerDetail, normaliseConfig, StreamDockCard,
} from '../../custom_components/stream_dock_ha/frontend/stream-dock-card.js';
import { layout293s, layoutAkp03e, layoutDashboard } from '../layouts.mjs';

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
  // 5 keys + 4 gaps of 0.52, then band at 7.98 + 0.94 = 8.92, plus margins.
  assert.ok(Math.abs(l.width - (8.92 + 0.6)) < 1e-9, `width ${l.width}`);
  assert.ok(Math.abs(l.height - (4.12 + 0.6)) < 1e-9, `height ${l.height}`);
  assert.equal(l.items.filter((i) => i.kind === 'key').length, 15);
  assert.equal(l.items.filter((i) => i.kind === 'band').length, 3);
  const key7 = l.items.find((i) => i.name === 'key_7');
  assert.ok(Math.abs(key7.left - (1 * 1.52 + 0.3)) < 1e-9);
  assert.ok(Math.abs(key7.top - (1 * 1.56 + 0.3)) < 1e-9);
  assert.ok(Math.abs(key7.box.width - (1 / l.width) * 100) < 1e-9);
  const band = l.items.find((i) => i.name === 'band_1');
  assert.equal(band.press, false);
  assert.equal(band.screen, true);
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
  assert.deepEqual(normaliseConfig({ pad_id: 'x' }), { pad_id: 'x', show_name: true, show_profile: true, haptic: true });
  assert.equal(normaliseConfig({ pad_id: 'x', scale: '3' }).scale, 3);
  assert.equal('scale' in normaliseConfig({ pad_id: 'x', scale: '' }), false);
  assert.throws(() => normaliseConfig({ pad_id: 'x', scale: 5 }));
  assert.throws(() => normaliseConfig(null));
  assert.equal(normaliseConfig({ haptic: false }).haptic, false);
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

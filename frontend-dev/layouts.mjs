// Realistic Layouts (protocol 3.2) for the harness and the tests, worked out
// as the app's src/model/layout.rs does, with the gaps as they're seen.

function key(n, x, y) {
  return { name: `key_${n}`, type: 'key', x, y, w: 1, h: 1, screen: true, press: true };
}

function round(v) {
  return Math.round(v * 1000) / 1000;
}

/** Stream Dock 293S: 5 x 3 keys a quarter of a key apart, three band tiles on the right. */
export const layout293s = (() => {
  const g = 0.25;
  const tile = 0.82;
  const controls = [];
  let n = 1;
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 5; c++) controls.push(key(n++, round(c * (1 + g)), round(r * (1 + g))));
  }
  const bandX = round(5 * (1 + g)); // 6.25
  // Centred on the keys: (3.5 - 3.32) / 2 above and below.
  const bandTop = (3 + 2 * g - (2 * (1 + g) + tile)) / 2;
  for (let i = 0; i < 3; i++) {
    controls.push({
      name: `band_${i + 1}`, type: 'band', x: bandX, y: round(bandTop + i * (1 + g)),
      w: tile, h: tile, screen: true, press: false,
    });
  }
  return { version: '77e0b4a1c9d2f356', width: round(bandX + tile), height: round(3 + 2 * g), controls };
})();

/**
 * AKP03E: 6 screen keys in 2 rows of 3, three round buttons below, one big knob
 * at the top right and two small ones below it.
 */
export const layoutAkp03e = (() => {
  const g = 0.26;
  const controls = [];
  let n = 1;
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 3; c++) controls.push(key(n++, round(c * (1 + g)), round(r * (1 + g))));
  }
  const d = 0.62;
  for (let c = 0; c < 3; c++) {
    controls.push({
      name: `button_${c + 1}`, type: 'button', x: round(0.5 + c * (1 + g) - d / 2), y: round(2 + g + 0.26),
      w: d, h: d, screen: false, press: true,
    });
  }
  const right = 3 + 2 * g + 0.35;
  const knob = (group, x, y, size) => ['left', 'right', 'press'].map((part) => ({
    name: `${group}_${part}`, type: `knob_${part}`, group, x: round(x), y: round(y), w: size, h: size,
    screen: false, press: true,
  }));
  controls.push(...knob('top_knob', right + 2.35 / 2 - 0.8, 0, 1.6));
  controls.push(...knob('lower_left_knob', right, 1.9, 1.0));
  controls.push(...knob('lower_right_knob', right + 2.35 - 1.0, 1.9, 1.0));
  return { version: '1c0de03e5a7b9f21', width: round(right + 2.35), height: round(2 + 2 * g + 0.62 + 0.2), controls };
})();

/** A 4 x 2 dashboard pad (an on-screen pad in the app). */
export const layoutDashboard = (() => {
  const g = 0.25;
  const controls = [];
  let n = 1;
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 4; c++) controls.push(key(n++, round(c * (1 + g)), round(r * (1 + g))));
  }
  return { version: 'd45b0a8e2c7f3611', width: round(4 + 3 * g), height: round(2 + g), controls };
})();

/** PadState `body`s: a white 293S with rounded keys, a black AKP03E, a see-through dashboard pad. */
export const bodyWhite = { front: [255, 255, 255], edge: 0.3, corner: 0.3, key_corner: 0.165, band_corner: 0.175 };
export const bodyBlack = { front: [0, 0, 0], edge: 0.3, corner: 0.3, key_corner: 0.165, band_corner: 0.175 };
export const bodyClear = { front: null, edge: 0.3, corner: 0.3, key_corner: 0.5, band_corner: 0.2 };

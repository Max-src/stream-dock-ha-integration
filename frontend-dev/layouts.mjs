// Realistic Layouts (protocol 3.2) for the harness and the tests.

function key(n, x, y) {
  return { name: `key_${n}`, type: 'key', x, y, w: 1, h: 1, screen: true, press: true };
}

function round(v) {
  return Math.round(v * 1000) / 1000;
}

/** Stream Dock 293S: 5 x 3 keys, gaps 0.52 across and 0.56 down, three band tiles on the right. */
export const layout293s = (() => {
  const gx = 0.52;
  const gy = 0.56;
  const controls = [];
  let n = 1;
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 5; c++) controls.push(key(n++, round(c * (1 + gx)), round(r * (1 + gy))));
  }
  const bandX = round(5 + 4 * gx + 0.9); // 7.98
  for (let i = 0; i < 3; i++) {
    controls.push({
      name: `band_${i + 1}`, type: 'band', x: bandX, y: round(i * (1 + gy) + 0.03),
      w: 0.94, h: 0.94, screen: true, press: false,
    });
  }
  return { version: '77e0b4a1c9d2f356', width: round(bandX + 0.94), height: round(3 + 2 * gy), controls };
})();

/**
 * AKP03E: 6 screen keys in 2 rows of 3, three round buttons below, one big knob
 * at the top right and two small ones below it (geometry from the app's pad_view.rs).
 */
export const layoutAkp03e = (() => {
  const g = 0.12;
  const controls = [];
  let n = 1;
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 3; c++) controls.push(key(n++, round(c * (1 + g)), round(r * (1 + g))));
  }
  const d = 0.62;
  for (let c = 0; c < 3; c++) {
    controls.push({
      name: `button_${c + 1}`, type: 'button', x: round(0.5 + c * (1 + g) - d / 2), y: 2.38,
      w: d, h: d, screen: false, press: true,
    });
  }
  const right = 3 + 2 * g + 0.35;
  const knob = (group, x, y, size) => ['left', 'right', 'press'].map((part) => ({
    name: `${group}_${part}`, type: `knob_${part}`, group, x: round(x), y: round(y), w: size, h: size,
    screen: false, press: true,
  }));
  controls.push(...knob('top_knob', right + 2.35 / 2 - 0.8, 0, 1.6));
  controls.push(...knob('lower_left_knob', right, 1.85, 1.0));
  controls.push(...knob('lower_right_knob', right + 2.35 - 1.0, 1.85, 1.0));
  return { version: '1c0de03e5a7b9f21', width: round(right + 2.35), height: 3.0, controls };
})();

/** A 4 x 2 dashboard pad (an on-screen pad in the app). */
export const layoutDashboard = (() => {
  const g = 0.15;
  const controls = [];
  let n = 1;
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 4; c++) controls.push(key(n++, round(c * (1 + g)), round(r * (1 + g))));
  }
  return { version: 'd45b0a8e2c7f3611', width: round(4 + 3 * g), height: round(2 + g), controls };
})();

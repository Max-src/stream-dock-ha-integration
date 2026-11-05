// Screenshots of the harness with headless Edge. Usage: node frontend-dev/shots.mjs
// Also runs the in-browser self-test (via --dump-dom) and prints its result.
// Edge always runs with the one lasting profile in edge.mjs: see why there.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { edge, lockProfile } from './edge.mjs';
import { startServer } from './serve.mjs';

lockProfile();
const OUT = fileURLToPath(new URL('./shots/', import.meta.url));
mkdirSync(OUT, { recursive: true });
const PORT = 8766;
const server = await startServer(PORT);
const base = `http://127.0.0.1:${PORT}/frontend-dev/index.html`;

const shots = [
  ['normal', '?shots', '1340,470'],
  ['update', '?shots&s=update', '1340,470'],
  ['offline', '?shots&s=offline', '1340,470'],
  ['mini-unplugged', '?shots&s=mini', '1340,470'],
  ['mini-seamless', '?shots&s=mini-seamless', '1340,470'],
  ['plain', '?shots&s=plain', '1340,470'],
  ['plain-light', '?shots&s=plain&theme=light', '1340,470'],
  ['plain-bare', '?shots&s=plain-bare&theme=light', '1340,470'],
  ['alert', '?shots&s=alert', '1340,470'],
  ['screen-off', '?shots&s=screenoff', '1340,470'],
  ['press-errors', '?shots&s=error', '1340,470'],
  ['reconnecting', '?shots&s=reconnect', '1340,470'],
  ['light-theme', '?shots&theme=light', '1340,470'],
  ['no-ha-card', '?shots&nohacard', '1340,470'],
  ['hidpi-2x', '?shots', '1340,470', ['--force-device-scale-factor=2']],
  ['narrow', '?shots&narrow&s=mini', '900,330'],
  ['extras', '?shots&s=extras', '1340,560'],
  ['extras-light', '?shots&s=extras&theme=light', '1340,560'],
  ['keys', '?shots&s=keys', '1700,330'],
  ['keys-light', '?shots&s=keys&theme=light', '1700,330'],
  ['screen-card-off', '?shots&s=screen', '1340,420'],
  ['screen-card-on', '?shots&s=screen&on', '1340,420'],
  ['screen-card-mouse', '?shots&s=screen&on&mouse', '1340,420'],
];
const only = process.argv[2];
for (const [name, query, size, extra = []] of shots) {
  if (only && only !== name && only !== 'selftest') continue;
  if (only === 'selftest') break;
  await edge([...extra, `--window-size=${size}`, '--virtual-time-budget=2500', `--screenshot=${join(OUT, name + '.png')}`, base + query]);
  console.log('shot', name);
}
const dom = await edge(['--virtual-time-budget=16000', '--dump-dom', base + '?s=selftest']);
const m = /<pre id="results">([\s\S]*?)<\/pre>/.exec(dom);
console.log(m ? m[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&gt;/g, '>').replace(/&lt;/g, '<') : 'no self-test output');
server.close();

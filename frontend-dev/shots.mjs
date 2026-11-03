// Screenshots of the harness with headless Edge. Usage: node frontend-dev/shots.mjs
// Also runs the in-browser self-test (via --dump-dom) and prints its result.
import { execFile } from 'node:child_process';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { startServer } from './serve.mjs';

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const OUT = fileURLToPath(new URL('./shots/', import.meta.url));
mkdirSync(OUT, { recursive: true });
const PORT = 8766;
const server = await startServer(PORT);
const base = `http://127.0.0.1:${PORT}/frontend-dev/index.html`;

function edge(args) {
  const profile = mkdtempSync(join(tmpdir(), 'sdc-edge-'));
  return new Promise((ok, fail) => execFile(EDGE, ['--headless', '--disable-gpu', '--hide-scrollbars',
    '--no-first-run', '--no-default-browser-check', '--force-prefers-reduced-motion', `--user-data-dir=${profile}`, ...args],
    { maxBuffer: 64 * 1024 * 1024, timeout: 60000 }, (err, stdout) => (err ? fail(err) : ok(stdout))));
}

const shots = [
  ['normal', '?shots', '1340,470'],
  ['update', '?shots&s=update', '1340,470'],
  ['offline', '?shots&s=offline', '1340,470'],
  ['mini-unplugged', '?shots&s=mini', '1340,470'],
  ['mini-seamless', '?shots&s=mini-seamless', '1340,470'],
  ['plain', '?shots&s=plain', '1340,470'],
  ['alert', '?shots&s=alert', '1340,470'],
  ['screen-off', '?shots&s=screenoff', '1340,470'],
  ['press-errors', '?shots&s=error', '1340,470'],
  ['reconnecting', '?shots&s=reconnect', '1340,470'],
  ['light-theme', '?shots&theme=light', '1340,470'],
  ['no-ha-card', '?shots&nohacard', '1340,470'],
  ['hidpi-2x', '?shots', '1340,470', ['--force-device-scale-factor=2']],
  ['narrow', '?shots&narrow&s=mini', '900,330'],
];
const only = process.argv[2];
for (const [name, query, size, extra = []] of shots) {
  if (only && only !== name && only !== 'selftest') continue;
  if (only === 'selftest') break;
  await edge([...extra, `--window-size=${size}`, '--virtual-time-budget=2500', `--screenshot=${join(OUT, name + '.png')}`, base + query]);
  console.log('shot', name);
}
const dom = await edge(['--virtual-time-budget=8000', '--dump-dom', base + '?s=selftest']);
const m = /<pre id="results">([\s\S]*?)<\/pre>/.exec(dom);
console.log(m ? m[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&gt;/g, '>').replace(/&lt;/g, '<') : 'no self-test output');
server.close();

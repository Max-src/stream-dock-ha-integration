// Headless Edge for the harness scripts, always with the same profile.
//
// Never start headless Edge or Chrome with a new temporary --user-data-dir.
// The first time a profile starts, Edge checks whether the Windows password
// is blank by logging on with an empty one. Windows counts that as a failed
// logon, and 10 of them lock the account. Edge keeps the answer in the
// profile's "Local State" ("os_password_blank"), so a reused profile asks
// once and never again. Reuse frontend-dev/.edge-profile; never delete it or
// its "Local State".
//
// One Edge at a time may use the profile: a lock file next to it makes a
// second script stop with a message rather than share it. A script that
// truly needs Edges in parallel gives each its own lasting folder
// (.edge-profile-1, .edge-profile-2, ...), never one per launch.
import { execFile } from 'node:child_process';
import { closeSync, mkdirSync, openSync, readFileSync, rmSync, writeSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
export const PROFILE = fileURLToPath(new URL('./.edge-profile/', import.meta.url));
const LOCK = fileURLToPath(new URL('./.edge-profile.lock', import.meta.url));

function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === 'EPERM';
  }
}

let held = false;

/** Takes the profile for this process, or exits saying who has it. */
export function lockProfile() {
  if (held) return;
  mkdirSync(PROFILE, { recursive: true });
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const fd = openSync(LOCK, 'wx');
      writeSync(fd, String(process.pid));
      closeSync(fd);
      held = true;
      const release = () => { if (held) { held = false; rmSync(LOCK, { force: true }); } };
      process.on('exit', release);
      for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { release(); process.exit(130); });
      return;
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
      const owner = Number(readFileSync(LOCK, 'utf8')) || 0;
      if (owner && alive(owner)) {
        console.error(`Another script (process ${owner}) is using the headless Edge profile ${PROFILE}. Wait for it to finish, then run this again.`);
        process.exit(1);
      }
      rmSync(LOCK, { force: true }); // left by a script that died
    }
  }
  throw new Error(`Couldn't take ${LOCK}`);
}

/** Runs headless Edge once with the shared profile and gives its output. */
export function edge(args) {
  lockProfile();
  return new Promise((ok, fail) => execFile(EDGE, ['--headless', '--disable-gpu', '--hide-scrollbars',
    '--no-first-run', '--no-default-browser-check', '--force-prefers-reduced-motion', `--user-data-dir=${PROFILE}`, ...args],
    { maxBuffer: 64 * 1024 * 1024, timeout: 60000 }, (err, stdout) => (err ? fail(err) : ok(stdout))));
}

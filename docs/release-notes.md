The first public release of the Stream Dock HA integration: the PCs running the [Stream Dock HA app](https://github.com/Max-src/stream-dock-ha), and their pads, become devices in Home Assistant, and dashboard cards show a pad's keys live and press them.

## Before you install

- **The app comes first.** Install [Stream Dock HA 1.1.0 or later](https://github.com/Max-src/stream-dock-ha/releases/latest) on each Windows PC with a pad, and connect it to Home Assistant with a token from an administrator user.
- Home Assistant 2026.8 or later.

## Install

From the Marketplace (Home Assistant 2026.11 or later), with HACS, or by hand: see [Install](https://github.com/Max-src/stream-dock-ha-integration#install). Then add **Stream Dock HA** under **Settings > Devices & services**, and tick **Press keys, switch profiles and pages, and change keys** in the app's **Settings > Home Assistant**.

## What's in it

- **Devices**: each PC, with each of its pads under it, and virtual pads, which are grids of keys made for dashboards.
- **Entities** for each pad: profile, page, screen on or off with its brightness, Mini Monitor, whether it's plugged in, presses, a picture of the pad and alerts. For each PC: microphone mute, processor, memory and graphics card use, the last press, and whether it's online.
- **Actions** for everything the app can do from Home Assistant: profiles, pages, keys, brightness, screen, Mini Monitor, alerts over the whole pad, and something on one key for a while (`show_on_key`).
- **Device triggers** for every key, button and knob, and a `stream_dock_ha_event` for every press.
- **Dashboard cards**, added by the integration itself, with nothing to download: a whole pad, one key or a few, and Mini Monitor as one screen, with the PC's mouse for administrators.
- **Blueprints**: a knob that dims a light, a key that toggles an entity, an on-air light that follows the microphone, and a doorbell alert with the door camera.

## Changes since 0.1.12

- **Diagnostics leave out names:** the PC's name, its Windows user and machine id, and profile, key and alert titles are redacted, so diagnostics can be shared in an issue.
- The README says who can see a pad's screen on a dashboard, and how to keep it to administrators.
- Icons for the **Show on a key** and **Clear a key** actions.
- The card's files are checked off Home Assistant's event loop.
- Listed under **Buttons & remotes** and **Computers & network** in the Marketplace.

## Coming from a copy made by hand

Versions up to 0.1.11 were only copied by hand. To move to the Marketplace or HACS, delete `/config/custom_components/stream_dock_ha` first, install it from there, then restart Home Assistant. Your devices, entities and settings stay, because they're kept by Home Assistant, not in that folder.

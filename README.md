# Stream Dock HA integration

A Home Assistant integration for the **Stream Dock HA** Windows app, which runs Stream Dock 293S and AJAZZ AKP03E pads, and pads on a dashboard.

With it, Home Assistant:

- shows each PC and each pad as a device, with entities for the profile, page, screen, Mini Monitor and more;
- has actions for everything the app can do from Home Assistant: profiles, pages, keys, brightness, alerts;
- fires a device trigger and a `stream_dock_ha_event` for every press;
- serves a dashboard card, `custom:stream-dock-card`, that shows a pad's keys live and lets you press them.

The app connects to Home Assistant over its usual connection. Nothing listens on the PC. When the app closes, that PC's entities become unavailable.

## Install

1. Copy the `custom_components/stream_dock_ha` folder into Home Assistant's `/config/custom_components` folder.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration**, and add **Stream Dock HA**.
4. In the app on each PC, open **Settings > Home Assistant** and tick **Let Home Assistant control this app**.

Each PC appears as soon as its app connects.

### Options

**Only administrators can press keys on dashboards** (off by default). When it's off, anyone logged in to Home Assistant can press keys on a card.

## The card

The integration loads the card on every dashboard. Add it with:

```yaml
type: custom:stream-dock-card
device_id: <the pad's device id>
```

or pick **Stream Dock pad** in the card list, then pick a pad. `pad_id` works instead of `device_id`, and `scale` (1 to 3) is optional. The card shows the pad's keys as the pad shows them. Tap a key to press it. Pads of a PC that's off are shown as offline.

## Entities

For each pad:

| Entity | What it does |
| --- | --- |
| Profile (select) | The profile showing. Choosing one switches to it |
| Page (number) | The page showing, from 1 |
| Screen (light) | Turns the screen off or on, and sets its brightness |
| Mini Monitor (switch) | Only on pads that can show it |
| Connected (binary sensor) | The physical pad is plugged in. Not on dashboard pads |
| Press (event) | Each press, named after the control. `dismissed` when a press only cleared an alert or woke the screen |
| Picture (image) | A picture of the whole pad |
| Alert (notify) | Sends a message as an alert over the keys |

For each PC:

| Entity | What it does |
| --- | --- |
| Microphone muted (binary sensor) | |
| CPU, Memory, GPU (sensors) | Disabled by default |
| Last press (sensor) | The time of the last press on any of its pads |
| Online (binary sensor) | Whether the app is connected. Always available |

## Actions

Each action takes a pad's `device_id`, plus the fields of the app's command of the same name.

| Actions | |
| --- | --- |
| `show_profile`, `next_profile`, `previous_profile`, `first_profile` | Change profile |
| `add_profile`, `rename_profile`, `duplicate_profile`, `delete_profile` | Edit profiles |
| `show_page`, `next_page`, `previous_page`, `add_page`, `delete_page` | Pages |
| `set_key`, `add_key`, `clear_key`, `press_key`, `swap_keys`, `copy_key`, `move_key` | Keys. In `copy_key` and `move_key`, `to` can hold a `device_id` to target another pad |
| `get_key`, `get_state` | Return the key or the pads' state as response data |
| `set_brightness`, `set_screen`, `mini_monitor` | The pad |
| `show_alert`, `clear_alert` | Alerts, with an optional camera |

Example:

```yaml
action: stream_dock_ha.show_alert
data:
  device_id: 0123456789abcdef0123456789abcdef
  title: Someone's at the door
  icon: mdi:doorbell
  camera: camera.front_door
  seconds: 60
```

An action fails when the PC is offline, when the app doesn't answer within 10 seconds, or when the app says no. Actions that change something can only be used by administrators, and by automations and scripts.

## Automations

Use the device trigger **"key_3" pressed** on a pad, or listen to the `stream_dock_ha_event` event. Its data holds `device_id`, `pad_id`, `control`, `profile`, `page`, `title`, `source` and `dismissed`.

Blueprints in [`blueprints/automation/stream_dock_ha`](blueprints/automation/stream_dock_ha):

- **Knob dims a light**: turning a knob dims or brightens a light, pressing it toggles the light;
- **Key toggles an entity**;
- **Microphone drives an on-air light**;
- **Doorbell alert**: shows the door camera on a pad when the doorbell rings.

## Development

The protocol between the app, this integration and the card is in [`docs/protocol.md`](docs/protocol.md).

Run the tests on Linux or WSL with Python 3.14:

```sh
uv venv --python 3.14 ~/venvs/stream-dock-ha
. ~/venvs/stream-dock-ha/bin/activate
uv pip install pytest-homeassistant-custom-component==0.13.375 home-assistant-frontend==20260930.5
pytest
```

## License

MIT

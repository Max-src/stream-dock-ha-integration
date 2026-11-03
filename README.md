# Stream Dock HA integration

A Home Assistant integration for the **Stream Dock HA** Windows app, which runs Stream Dock 293S and AJAZZ AKP03E pads, and pads on a dashboard.

With it, Home Assistant:

- shows each PC and each pad as a device, with entities for the profile, page, screen, Mini Monitor and more;
- has actions for everything the app can do from Home Assistant: profiles, pages, keys, brightness, alerts;
- fires a device trigger and a `stream_dock_ha_event` for every press;
- serves a dashboard card, `custom:stream-dock-card`, that shows a pad's keys live and lets you press them.

The app connects to Home Assistant over its usual connection. Nothing listens on the PC. When the app closes, that PC's entities become unavailable.

## Install

You need Home Assistant 2026.8 or later, and the Stream Dock HA app 1.1.0 or later on each PC.

### 1. Put the integration in Home Assistant

**By hand:**

1. Download this repository.
2. Copy its `custom_components/stream_dock_ha` folder into the `custom_components` folder inside Home Assistant's configuration folder, so you have `/config/custom_components/stream_dock_ha/manifest.json`. Create `custom_components` if it isn't there. The File editor or Samba add-ons can do this.
3. Restart Home Assistant.

**With HACS**, once this repository is public: in HACS, open the menu, choose **Custom repositories**, add `https://github.com/Max-src/stream-dock-ha-integration` with the type **Integration**, then download **Stream Dock HA** and restart Home Assistant.

### 2. Add it

Go to **Settings > Devices & services**, choose **Add integration** and pick **Stream Dock HA**. There's nothing to fill in, and it's added once for all your PCs.

### 3. Connect the app on each PC

1. In the app, open **Settings > Home Assistant** and connect it to Home Assistant, if it isn't already. **Use a token from an administrator user.** Home Assistant only lets administrators use the integration's commands, so with another user's token the PC never appears. To make one, log in as an administrator, open your profile, then **Security > Long-lived access tokens > Create token**.
2. Tick **Let Home Assistant control this app**.
3. Leave **Show this PC in the Stream Dock HA integration** ticked, as it is at first. You can change the PC's name there; Home Assistant follows it.

The line under them should read **Integration: connected as** the PC's name. The PC and its pads then appear under **Settings > Devices & services > Stream Dock HA**. If the line says something else, see [Troubleshooting](#troubleshooting).

Keys that open programs or websites, press keys or type text can't be pressed from Home Assistant until you allow it: in the app, select the key and set its **Pressing from Home Assistant** to **Always**. Home Assistant can't change that setting.

### Options

**Only administrators can press keys on dashboards** (off by default), under the integration's **Configure**. When it's off, anyone logged in to Home Assistant can press keys on a card.

## The card

The integration adds the card to Home Assistant's dashboards by itself: there's no resource to add, and no HACS frontend download.

To add it with the editor, edit a dashboard, choose **Add card**, pick **Stream Dock pad**, then pick a pad. The editor also has:

| Setting | What it does |
| --- | --- |
| Show name | The pad's name above the keys. On by default |
| Show profile | The profile and page it's showing. On by default |
| Vibrate on press | A short vibration on phones that can. On by default |
| Picture scale | 1 to 3. Leave it empty to match the screen |

Or in YAML:

```yaml
type: custom:stream-dock-card
device_id: <the pad's device id>
show_name: true
show_profile: true
haptic: true
scale: 2
```

`pad_id` works instead of `device_id`. Only `device_id` or `pad_id` is needed.

The card shows the pad's keys as the pad shows them, live, alerts included. Tap a key to press it. Pads of a PC that's off are shown dimmed, with their last pictures, and can't be pressed.

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

- **Stream Dock knob dims a light**: turning a knob dims or brightens a light, pressing it toggles the light;
- **Stream Dock key toggles an entity**;
- **Stream Dock microphone drives an on-air light**;
- **Stream Dock doorbell alert**: shows the door camera on a pad when the doorbell rings.

To use them, copy the `stream_dock_ha` folder into `/config/blueprints/automation/`, so you have `/config/blueprints/automation/stream_dock_ha/doorbell_alert.yaml`, then restart Home Assistant or reload automations. They appear under **Settings > Automations & scenes > Blueprints**, where **Create automation** on one of them sets it up. Once this repository is public, **Import blueprint** with a blueprint's GitHub address works too.

## Troubleshooting

The app says how the integration is doing in **Settings > Home Assistant**, on the line under **Show this PC in the Stream Dock HA integration**. That line shows only while the app is connected to Home Assistant and the box is ticked; if it's missing, check the address and token above it first.

| The app says | What to do |
| --- | --- |
| Integration: not installed in Home Assistant | Copy the integration into Home Assistant and restart it ([step 1](#1-put-the-integration-in-home-assistant)). The app asks again each time it connects |
| Integration: add Stream Dock HA in Home Assistant's Devices & services | It's installed but not added yet ([step 2](#2-add-it)) |
| The integration needs a token from an administrator user | Home Assistant answered `unauthorized`: the app's token belongs to a user who isn't an administrator. Make a token as an administrator, and paste it in the app |
| Integration: update the Stream Dock HA integration | The integration is older than the app. Update it and restart Home Assistant |
| Integration: update this app | The app is older than the integration. Update the app |
| Integration: waiting for Home Assistant | The app has asked and is waiting for an answer. If it stays, restart Home Assistant |

On a card or from an action:

| You see | What it means |
| --- | --- |
| A key refused, saying it opens programs or presses keys, or can't be pressed | That key's **Pressing from Home Assistant** setting, in the app. **Automatic** refuses keys that open programs or websites, press keys or type text, and **Never** refuses everything. Choose **Always** to allow it |
| Home Assistant control is off in the app | Tick **Let Home Assistant control this app** in the app |
| Only administrators can press keys here | The option **Only administrators can press keys on dashboards** is on, and you're not an administrator |
| PC offline | The app on that PC is closed, or not connected to Home Assistant |
| An action fails after 10 seconds | The app didn't answer. Check that it's running and connected |

The app's `pad-log.txt`, next to its settings in `%APPDATA%\StreamDockHA`, lists what it heard from the integration. **Download diagnostics** on the integration's page in Home Assistant gives its side.

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

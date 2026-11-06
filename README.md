# Stream Dock HA integration

A Home Assistant integration for the **Stream Dock HA** Windows app, which runs Stream Dock 293S and AJAZZ AKP03E pads, and pads on a dashboard.

With it, Home Assistant:

- shows each PC and each pad as a device, with entities for the profile, page, screen, Mini Monitor and more;
- has actions for everything the app can do from Home Assistant: profiles, pages, keys, brightness, alerts;
- fires a device trigger and a `stream_dock_ha_event` for every press;
- serves dashboard cards: a whole pad (`custom:stream-dock-card`), one key or a few (`custom:stream-dock-key-card`), and Mini Monitor as one screen (`custom:stream-dock-screen-card`), all live, with keys you can press;
- can show something on one key for a while: words, an icon, a picture or a camera (`stream_dock_ha.show_on_key`).

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

The line under them should read **Integration: connected as** the PC's name. The PC then appears under **Settings > Devices & services > Stream Dock HA**, with each of its pads under it. If the line says something else, see [Troubleshooting](#troubleshooting).

Keys that open programs or websites, press keys or type text can't be pressed from Home Assistant until you allow it: in the app, select the key and set its **Pressing from Home Assistant** to **Always**. Home Assistant can't change that setting.

### Options

**Only administrators can press keys on dashboards** (off by default), under the integration's **Configure**. When it's off, anyone logged in to Home Assistant can press keys on a card.

## The cards

The integration adds the cards to Home Assistant's dashboards by itself: there's no resource to add, and no HACS frontend download. It lists the card in the dashboards' resources (or, when those are written in YAML, loads it with every page). The browser checks for a newer card at each page load, so after updating the integration a new card shows with a page refresh; changes to the integration itself still need a restart.

### Stream Dock pad

To add it with the editor, edit a dashboard, choose **Add card**, pick **Stream Dock pad**, then pick a pad. The editor's settings are in four sections:

| Section | Setting | What it does |
| --- | --- | --- |
| Pad | Pad | Which pad the card shows |
| Pad | Title | Shown above the keys. Leave it empty for no title. A new card starts with the pad's name |
| Appearance | Show card background | Off: no frame round the card, and the pad uses all the room. On by default |
| Appearance | Show the profile and page | What the pad is showing. On by default |
| Appearance | Tilted 3D look (`tilt`) | The pad leans back as if lying on a desk, with its thickness and a shadow. Keys still press. Off by default |
| Extras | Profile and page buttons (`show_page_buttons`) | Buttons under the pad to change its profile and page, through its Profile and Page entities. Off by default |
| Extras | Press effect (`press_effect`) | The key sinks and lights up where you tap it. On by default |
| Extras | Show presses made on the pad (`show_pad_presses`) | A ring flashes round a key pressed on the real pad, on a pad on screen or by an automation. On by default |
| Pictures | Picture scale | 1 to 3. Leave it empty to match the screen |

Or in YAML:

```yaml
type: custom:stream-dock-card
device_id: <the pad's device id>
title: Desk
show_card_background: true
show_profile: true
tilt: false
show_page_buttons: false
press_effect: true
show_pad_presses: true
scale: 2
```

`pad_id` works instead of `device_id`. Only `device_id` or `pad_id` is needed.

The card shows the pad's keys as the pad shows them, live, alerts included. Tap a key to press it. Pads of a PC that's off are shown dimmed, with their last pictures, and can't be pressed. A card only follows its pad while it can be seen: in a hidden browser tab, or scrolled well out of view, it keeps its last pictures and nothing is sent to it.

With Mini Monitor on, the card shows the PC screen across the pad's keys, as the pad does. The app sends a few pictures a second, only while a card shows that pad; set how many in the app's **Settings > Home Assistant**. When the app reaches Home Assistant through the internet, it sends those pictures straight to Home Assistant's local address instead (**Settings > System > Network** in Home Assistant), if it has one.

## Entities

For each pad:

| Entity | What it does |
| --- | --- |
| Profile (select) | The profile showing. Choosing one switches to it |
| Page (number) | The page showing, from 1 |
| Screen (light) | Turns the screen off or on, and sets its brightness |
| Mini Monitor (switch) | Only on pads that can show it |
| Connected (binary sensor) | The physical pad is plugged in. Not on virtual pads |
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

### Stream Dock key

One key of a pad, or a few, live and pressable: a key for the coffee machine next to the kitchen lights, say. Pick **Stream Dock key**, a pad, and the keys:

```yaml
type: custom:stream-dock-key-card
device_id: <the pad's device id>
controls: "3"            # or "1, 2, 6-7" for a group, or band_1, button_2, top_knob
show_card_background: true
show_pad_body: false     # true: the pad's front round the keys
press_effect: true
show_pad_presses: true
```

Keys are counted as in the app: left to right, then down, from 1.

### Stream Dock Mini Monitor

A pad's Mini Monitor as one screen, in the screen's own shape, without the gaps between keys. When Mini Monitor is off, it says so and offers a button to turn it on (`show_turn_on: false` hides it; it needs permission to change the pad's Mini Monitor switch). It only receives pictures while it can be seen.

```yaml
type: custom:stream-dock-screen-card
device_id: <the pad's device id>
title: Desk screen
show_card_background: true
show_turn_on: true
mouse: false
```

With **Use the mouse on Mini Monitor** (`mouse: true`), the card works like a remote screen: click, drag, right-click (a long press on a phone), scroll, and hover with a mouse. It moves the PC's real pointer onto the Mini Monitor display. Only administrators can use it, and only once the app allows it: **Settings > Home Assistant > Dashboard cards can use the mouse on Mini Monitor**, under **Let Home Assistant control this app**. A small mouse sign in the corner shows it's on.

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
| `show_alert`, `clear_alert` | Alerts over the whole pad, with an optional camera |
| `show_on_key`, `clear_on_key` | Something on one key for a while: words, an icon, a picture or a camera. Pressing that key takes it away and does nothing else |

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

Or on one key, for 30 seconds unless `seconds` says otherwise (0: until pressed):

```yaml
action: stream_dock_ha.show_on_key
data:
  device_id: 0123456789abcdef0123456789abcdef
  key: 3
  title: Washer
  message: 12 min left
  icon: mdi:washing-machine
  color: [33, 150, 243]
  seconds: 60
```

`picture` takes an `image.*` entity, a Home Assistant path such as `/local/doorbell.png`, a web address or a `data:` address; `camera` a camera entity, refreshed live; `fit` is `fill`, `fit` or `stretch`. `clear_on_key` takes the key away, or every key of the pad without one.

To try it by hand, [`examples/node-red/stream-dock-playground.json`](examples/node-red/stream-dock-playground.json) is a Node-RED flow with buttons for each kind (words, a camera, a picture, the weather, a countdown, a wave of colours) and one that reacts when such a key is pressed. In Node-RED: **Menu > Import**, pick the file, **Import**, then **Deploy**. Set the pad in the tab's `PAD` environment variable, and the Home Assistant server in the nodes if yours isn't the add-on's.

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

The card's tests: `node --test frontend-dev/test/*.mjs`. Screenshots of the card and its in-browser self-test: `node frontend-dev/shots.mjs` (headless Edge).

**Never start headless Edge or Chrome with a new temporary `--user-data-dir`.** Each new profile makes a failed Windows logon (Edge checks whether the password is blank), and 10 of them lock the account. Reuse `frontend-dev/.edge-profile` through [`frontend-dev/edge.mjs`](frontend-dev/edge.mjs), never delete it or its `Local State`, and let its lock file keep scripts from sharing it at the same time. A script that needs Edges in parallel gives each its own lasting folder (`.edge-profile-1`, `.edge-profile-2`), never one per launch.

## License

MIT

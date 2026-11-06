# Stream Dock HA integration protocol (version 1)

This is the contract between three programs:

- **the app**: Stream Dock HA on a Windows PC (this repository);
- **the integration**: the `stream_dock_ha` custom integration in Home Assistant (repository `ha-integration`);
- **the card**: the `custom:stream-dock-card` dashboard card, served by the integration.

Any change to a message here must change all three, and this file first. The integration keeps a copy at `ha-integration/docs/protocol.md`; this one is the source.

## 1. Shape of the connection

The app already keeps one WebSocket connection open to Home Assistant (`/api/websocket`), logged in with the person's token. The integration adds its own WebSocket commands, all named `stream_dock_ha/...`. The app calls them on that same connection, so nothing listens on the PC.

```
 App (PC 1) ──┐                                ┌── Card (browser, tablet …)
 App (PC 2) ──┼── HA WebSocket ── integration ─┼── Card
 App (PC n) ──┘    stream_dock_ha/*            └── HA entities, actions, device triggers
```

- Any number of PCs connect at once. Each PC can have any number of pads.
- The app is the **only** source of truth and the **only** renderer. The integration keeps what the app last said, and passes messages along. The card only shows pictures and sends presses.
- When the app's connection closes, everything from that PC becomes unavailable at once. Nothing on the PC's pads works without the PC, by design.
- If the integration isn't installed, `stream_dock_ha/connect` fails with `unknown_command`. The app then carries on exactly as before, and tries again on its next connection.

Message ids follow Home Assistant's rules: the app keeps using its single increasing counter for everything it sends.

## 2. Identities

| Id | Format | Made by | Lifetime |
| --- | --- | --- | --- |
| `instance_id` | 16 lowercase hex characters, random | The app, the first time it runs | Kept in the settings |
| `machine` | 16 lowercase hex characters: FNV-1a 64 of `"stream-dock-ha:" + MachineGuid` (`HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`; `"unknown"` if missing) | The app, each start | Never stored by the app; stored by the integration |
| `pad_id` | 16 lowercase hex characters, random | The app, when a pad is first set up in it (a physical pad or a virtual pad) | Kept in the settings |
| profile `id` | 16 lowercase hex characters, random | The app, when a profile is made | Kept in the settings |

Duplicates can only come from copying a settings file, so they are handled in two places:

1. **In the app, without Home Assistant.** The settings store `instance_machine`, the `machine` value when the `instance_id` was made. At start, if the current `machine` differs, the settings were copied from another PC: the app makes a new `instance_id` **and new ids for every pad**, then stores the new `instance_machine`.
2. **In the integration.** It stores, for each `instance_id`, the `machine` it came from. For each `pad_id`, it stores the `instance_id` it belongs to.
   - `connect` with a known `instance_id` but a different `machine` is refused with error code `renew_instance`. The same applies when another live connection already uses that `instance_id` with a different `machine`. The app then makes new instance and pad ids and sends `connect` again.
   - The same `instance_id` and `machine` on a new connection is the same PC coming back, for example after a network drop. The new connection replaces the old one, and the old one's subscription is ended.
   - `state` with a `pad_id` that belongs to another `instance_id` gets that id back in `renew_pads`. The app makes a new id for each listed pad, moves its profiles over to it, saves, and sends `state` again.
   - A renewed pad is a new device in Home Assistant. Cards and automations that pointed at the old one must be pointed at the new one. This only happens to settings copied between PCs.

## 3. Commands the app sends

### 3.1 `stream_dock_ha/connect` (a subscription)

Sent once after login, before anything else.

```json
{
  "id": 41,
  "type": "stream_dock_ha/connect",
  "protocol": 1,
  "app_version": "1.1.0",
  "instance_id": "3f9c1a7e5b2d4c60",
  "machine": "a81e44c09d1b2f37",
  "name": "DESKTOP-MAX",
  "control": true
}
```

- `name` is the PC's name (`COMPUTERNAME`) unless the person renamed it in the app.
- `control` mirrors the app's **Press keys, switch profiles and pages, and change keys** setting. When it's `false`, the integration still shows everything, but it refuses changes and presses with the error `control_off`, without asking the app.

Result on success:

```json
{ "id": 41, "type": "result", "success": true,
  "result": { "protocol": 1, "integration_version": "0.1.2",
              "local_url": "http://192.168.1.20:8123", "frame_key": "9f3c…32 hex" } }
```

- `local_url` is Home Assistant's address on the home network, or `null` when it doesn't know one. `frame_key` is new for each `connect`. Both are for Mini Monitor frames (section 3.6); an older integration sends neither, and then the app sends no frames.

Errors (`success: false`, `error.code`):

| Code | Meaning | What the app does |
| --- | --- | --- |
| `unknown_command` | The integration isn't installed | Carries on without it, tries again on the next connection |
| `protocol_mismatch` | Protocol versions differ; `error.message` says which the integration speaks | Logs it, shows "Update the Stream Dock HA integration" or "Update the app" in Settings > Home Assistant, carries on without it |
| `renew_instance` | Duplicate, see section 2 | New instance and pad ids, then `connect` again on the same socket |
| `not_set_up` | The integration is installed but has no config entry | Shows "Add the Stream Dock HA integration in Home Assistant's Devices & services" |
| `unauthorized` | The token isn't an administrator's | Shows "The integration needs a token from an administrator user", and carries on without it |

Any other app command sent on a socket that has no live `connect` gets the error `not_connected`. This happens, for example, after the integration was reloaded, which ends the subscription. It also happens while the integration is reloading. The app then sends `connect` again on the same socket.

Once the result is in, the subscription stays open. The integration pushes events down it (section 4) until the connection closes. The app sends a full `state` right after a successful `connect`.

### 3.2 `stream_dock_ha/state`

Everything about this PC and its pads, in full each time. It's sent:

- after `connect`;
- within 250 ms of any change that alters it (debounced);
- at least every 60 s.

Changes to `pc.cpu`, `pc.memory` and `pc.gpu` alone send it at most every 10 s.

```json
{
  "id": 42,
  "type": "stream_dock_ha/state",
  "name": "DESKTOP-MAX",
  "control": true,
  "pc": {
    "mic_muted": false,
    "cpu": 12,
    "memory": 48,
    "gpu": 5,
    "last_press": "2026-11-03T09:12:44Z"
  },
  "pads": [ PadState, ... ]
}
```

`pc` fields can be `null` when unknown. `last_press` is the time of the last press on any of this PC's pads, physical or on screen, in UTC.

**PadState**

```json
{
  "id": "9d04e1b7a2c35f18",
  "kind": "stream_dock_293s",
  "model": "Stream Dock 293S",
  "name": "Desk pad",
  "connected": true,
  "screen_on": true,
  "brightness": 25,
  "mini_monitor": false,
  "profile": { "id": "51ac0e9f7d2b8346", "name": "Home" },
  "profiles": [ { "id": "51ac0e9f7d2b8346", "name": "Home", "pages": 3 } ],
  "page": 1,
  "pages": 3,
  "look": "c2a91f0e33b7d455",
  "alert": false,
  "layout": Layout,
  "body": Body
}
```

| Field | Meaning |
| --- | --- |
| `kind` | `stream_dock_293s`, `akp03e` or `dashboard`. Later models add values |
| `connected` | The physical pad is plugged in and working. Always `true` for `dashboard` |
| `screen_on` | `false` while the screen is off, by the timer or by `set_screen` |
| `brightness` | 0 to 100 |
| `mini_monitor` | `true` or `false`, or `null` for a pad that can't show it (`dashboard`) |
| `page` | Counted from 1 |
| `look` | Changes whenever the pad's screen keys would look different, including its layout, its `body` and whether the screen is on. Band tiles are left out, because they follow the PC's load every 3 s. The integration uses it for the `image` entity's `image_last_updated` without needing pictures |
| `alert` | An alert is covering the keys (section 6) |

**Layout**

Where every control is, in **key units**: 1.0 is the width of one key. The gaps between keys as they're seen are already included, so a key in column `c` starts at `x = c * (1 + gap_x)`. They're a quarter of a key on the 293S and virtual pads, and 0.26 on the AKP03E, as the app's window and pads on screen draw them. They aren't the pad's own gap setting, which is the screen hidden between keys that pictures across keys skip.

```json
{
  "version": "77e0b4a1c9d2f356",
  "width": 8.92,
  "height": 4.12,
  "controls": [
    { "name": "key_1",  "type": "key",  "x": 0.0,  "y": 0.0, "w": 1.0, "h": 1.0, "screen": true,  "press": true },
    { "name": "band_1", "type": "band", "x": 7.98, "y": 0.0, "w": 0.94, "h": 0.94, "screen": true, "press": false },
    { "name": "button_1", "type": "button", "x": 0.0, "y": 3.4, "w": 0.6, "h": 0.6, "screen": false, "press": true },
    { "name": "top_knob_left",  "type": "knob_left",  "group": "top_knob", "x": 4.6, "y": 0.0, "w": 1.0, "h": 1.0, "screen": false, "press": true },
    { "name": "top_knob_right", "type": "knob_right", "group": "top_knob", "x": 4.6, "y": 0.0, "w": 1.0, "h": 1.0, "screen": false, "press": true },
    { "name": "top_knob_press", "type": "knob_press", "group": "top_knob", "x": 4.6, "y": 0.0, "w": 1.0, "h": 1.0, "screen": false, "press": true }
  ]
}
```

(The numbers above are only an illustration.)

- `type` is `key`, `button`, `knob_left`, `knob_right`, `knob_press` or `band`. A knob's three parts share `group` and geometry: the card draws one knob with a left half, a right half and a centre.
- `screen`: the control shows a picture. `press`: pressing it does something.
- `width` and `height` cover every control, band tiles and knobs included.
- `version` changes when the layout changes, for example when a virtual pad's profile has a different grid.
- Control names are the ones in [home-assistant-control.md](home-assistant-control.md): `key_N` counted from 1, left to right then down; `button_N`; `<knob>_knob_<left|right|press>`; and `band_N`, from the top, for the 293S's band tiles.

**Body**

How the pad looks round its controls, so the card draws it as the app's window does.

```json
{ "front": [255, 255, 255], "edge": 0.3, "corner": 0.3, "key_corner": 0.165, "band_corner": 0.175 }
```

| Field | Meaning |
| --- | --- |
| `front` | The front's colour as `[r, g, b]`, or `null` for a see-through front: the keys float on whatever is behind the pad |
| `edge` | The front round the controls, in key units |
| `corner` | How round the front's corners are, in key units |
| `key_corner`, `band_corner` | How round the keys' and band tiles' corners are, as a part of their width: 0 is square, 0.5 is round. Pictures already have black in their cut corners; on another front the card rounds them off |

An app that sends no `body` gets the card's own dark pad.

Result: `{ "renew_pads": [] }`. A non-empty list means "make new ids for these pads", as section 2 describes.

### 3.3 `stream_dock_ha/pressed`

Sent for every press on any of this PC's pads, whatever the press did, as long as the integration is connected. It doesn't depend on the control setting.

```json
{ "id": 43, "type": "stream_dock_ha/pressed",
  "pad_id": "9d04e1b7a2c35f18", "control": "key_3",
  "profile": "Home", "page": 1, "title": "Desk lamp",
  "source": "pad" }
```

`source` is one of:

- `pad`: the physical pad
- `screen`: a pad on screen in the app
- `dashboard`: the card
- `action`: a Home Assistant action or event command
- `hotkey`: a keyboard shortcut

A press that only dismissed an alert or woke the screen carries `"dismissed": true` and ran nothing. Result: empty.

### 3.4 `stream_dock_ha/pictures`

Sent only for pads the integration asked to watch (section 4.2), at the scale it asked for. A picture is sent as soon as it changes, at most 10 times a second per pad.

```json
{ "id": 44, "type": "stream_dock_ha/pictures",
  "pad_id": "9d04e1b7a2c35f18", "scale": 2, "complete": false,
  "pictures": {
    "key_1": { "hash": "1b7c03e9aa4d2f60", "data": "<base64 JPEG>" },
    "key_2": null
  } }
```

- Keys in `pictures` are control names. `null` means "nothing to show" (an empty key or a dark screen), which the card draws as the pad's empty key.
- `complete: true` means this message holds every `screen` control. Anything absent is `null`. The app sends a complete set after each `watch` change for that pad, and whenever the layout version changes.
- Pictures are JPEG, square, `85 * scale` pixels for keys and `80 * scale` for band tiles. For an alert, they are the parts of the alert picture under each key, exactly as the pad shows them.
- One message stays under 1 MB of JSON. A bigger update is split into several messages, with `complete` only on the first.
- While Mini Monitor is on, the pictures are the keys the pad would show without it. The card shows Mini Monitor as a note over the pad, and the PC's screen is never sent.

Result: empty.

### 3.5 `stream_dock_ha/reply`

The answer to a command event (section 4.1).

```json
{ "id": 45, "type": "stream_dock_ha/reply",
  "request_id": "r-17", "ok": true, "result": { "profile": "Games" } }
```

or `"ok": false, "error": "That key opens programs, which Home Assistant isn't allowed to press"`. Result: empty.

### 3.6 `stream_dock_ha/frame`

One Mini Monitor picture of a pad, for the cards showing it: the whole picture as one JPEG, and where each control's part of it is, in its pixels. The parts under the gaps between keys aren't anyone's, as on the pad.

```json
{ "id": 46, "type": "stream_dock_ha/frame",
  "instance_id": "51ac0e9f7d2b8346", "key": "<frame_key>", "pad_id": "9d04e1b7a2c35f18",
  "width": 557, "height": 349, "data": "<base64 JPEG>",
  "tiles": [ { "name": "key_1", "x": 0, "y": 0, "w": 85, "h": 85 }, ... ],
  "seamless": false }
```

- `seamless: true` follows the app's **One picture across the gaps** setting (Monitor tab): the card then shows the whole picture once over the area of those controls, gaps included, square-edged and in the picture's own proportions, instead of a part on each key. It's optional and `false` when left out.

- The app sends frames only for pads a card is watching (section 4.2), only while that pad's Mini Monitor is on, only when the picture changed, and at most as often as the app's **Mini Monitor on dashboard cards** setting says (5 a second by default).
- Frames name their PC and its `frame_key` rather than relying on the socket, because they may come on a second connection to `local_url`. The app opens it when `local_url` isn't the address it already uses, and the person allows it. That keeps the pictures on the home network when the app reaches Home Assistant through the internet. While that connection is down, frames go on the usual one.
- Errors: `not_connected` when the PC isn't connected or the key is wrong, `not_found` for a pad that isn't that PC's. A frame no card is watching is accepted and dropped. Frames aren't kept.

## 4. Events the integration sends to the app

They arrive on the `connect` subscription:

```json
{ "id": 41, "type": "event", "event": { "kind": "...", ... } }
```

### 4.1 `command`

```json
{ "kind": "command", "request_id": "r-17",
  "data": { "command": "show_profile", "pad": "9d04e1b7a2c35f18", "profile": "Games",
            "source": "action", "user": "Max" } }
```

- `data` is exactly a command of [home-assistant-control.md](home-assistant-control.md), as `remote::apply` takes it. `pad` is always a `pad_id` here.
- `source` is `action` (an HA action, or a change to an entity such as the profile select or the screen light) or `dashboard` (the card).
- `user` is the HA user's name when there is one, for the app's log.
- The app answers every command with exactly one `stream_dock_ha/reply` with the same `request_id`. The integration waits up to 10 s and then gives up with "The PC didn't answer".

Commands added for the integration, also available through the event route:

| Command | Fields | What it does | Reply `result` |
| --- | --- | --- | --- |
| `set_screen` | `pad`, `on` | Turns the pad's screen off (dark until turned on again or pressed) or back on | `{ "on": true }` |
| `snapshot` | `pad`, optional `scale` (1–3, default 1) | A picture of the whole pad, laid out as in the layout with the body's `edge` round it, on the pad's front colour (dark grey if clear). The band's tiles sit on one black strip | `{ "content_type": "image/jpeg", "data": "<base64>" }` |
| `show_alert` | `pad`, and optional `title`, `message`, `icon` (`mdi:…`), `color` ([r,g,b]), `seconds` (0 = until pressed; default 0), `camera` (a camera entity whose picture fills the alert) | Covers the pad's screen keys with one alert picture; see section 6 | `{}` |
| `clear_alert` | `pad` | Takes the alert away | `{}` |
| `show_on_key` | `pad`, `key` (a number counted from 1, also as text, or a control's name such as `key_3`) or `control`, and optional `title`, `message`, `icon` (`mdi:…`), `color` ([r,g,b]), `seconds` (0 = until pressed; default 30), `camera` (a camera entity) or `picture`, `fit` (`fill`, the default, `fit` or `stretch`) | Shows something on one screen key for a while; see section 6.1 | `{ "control": "key_3" }` |
| `clear_on_key` | `pad`, optional `key` or `control` | Takes that off one key, or off all the pad's keys without a key | `{ "cleared": 1 }`, how many it took away |
| `mouse` | `pad`, `action` (`move`, `down`, `up`, `click` or `scroll`), `x` and `y` (where on the Mini Monitor picture, as parts of its width and height, 0 to 1), optional `button` (`left`, the default, `right` or `middle`) and `amount` (wheel notches for `scroll`, away from you when positive, default 1, at most 20 either way) | Moves the PC's real pointer to that point of Mini Monitor's display and presses, lets go, clicks or turns the wheel there. Needs `ha_mouse` (section 7). A button pressed with `down` is let go by itself after 10 s without its `up` | `{}` |

`press_key` takes `source` too. Its `control` accepts screen keys too (`key_3`), which is what the card sends. While Mini Monitor is on, a press from the physical pad or a pad on screen only brings the keys back, as today. A press from `dashboard` or `action` runs the key and leaves Mini Monitor on, because whoever sent it is looking at the card, not the pad. Alerts and a dark screen swallow presses from every source, as section 6 says. Section 7 says what Home Assistant is allowed to press.

### 4.2 `watch`

```json
{ "kind": "watch", "pads": { "9d04e1b7a2c35f18": 2 } }
```

The full set of this PC's pads that some card is showing, with the largest scale asked for (1–3). It's sent right after `connect` (often as `{}`) and whenever the set changes. An empty map means "send no pictures". For each pad that is new in the map or whose scale changed, the app sends a complete `pictures` set at once.

## 5. The card's commands (browser to integration)

They use the dashboard user's own login.

### 5.1 `stream_dock_ha/pads`

```json
{ "type": "stream_dock_ha/pads" }
```

Result:

```json
{ "pads": [ { "pad_id": "...", "name": "Desk pad", "pc": "DESKTOP-MAX",
              "kind": "stream_dock_293s", "online": true, "device_id": "<HA device id>" } ] }
```

It lists every known pad, including pads of PCs that are offline. The card's editor uses it.

### 5.2 `stream_dock_ha/watch` (a subscription)

```json
{ "type": "stream_dock_ha/watch", "pad_id": "...", "scale": 2 }
```

`scale` is optional: 1, 2 or 3, default 2. It's refused with `not_found` for an unknown pad. Events:

- `{ "kind": "pad", "online": true, "listed": true, "pc": "DESKTOP-MAX", "pad": PadState }`: first, then on every change. `online` says the PC is connected. `listed` says the pad was in that PC's latest `state` (false when the person removed it from the app). When the PC goes away, `online: false` comes with the last known `pad`.
- `{ "kind": "pictures", "complete": true, "scale": 2, "pictures": { "key_1": { "hash": "...", "data": "..." }, ... } }`: first the full set the integration holds (if any), then whatever the app sends.
- `{ "kind": "frame", "width": 557, "height": 349, "data": "<base64 JPEG>", "tiles": [...], "seamless": false }`: a Mini Monitor picture, as in section 3.6. The card shows each control's part of it over its key, while the pad's `mini_monitor` is `true`, and goes back to the key pictures when frames stop for 3 seconds.

- The `scale` of pictures can differ from the one asked for: the app draws at the largest scale any card wants, and the integration's cache can hold an older scale until the new set arrives. Cards show whatever arrives, sized to fit.
- A big update can come in several `pictures` events, so a pad may look half-updated for a moment.
- After Home Assistant's connection drops and comes back, a card subscribes again. The integration then replays the `pad` event and the complete picture set it holds.

While at least one card watches a pad, the integration includes it in the `watch` it sends that pad's app. When the last card leaves, it takes it out.

### 5.3 `stream_dock_ha/press`

```json
{ "type": "stream_dock_ha/press", "pad_id": "...", "control": "key_3" }
```

The integration checks the user may press (section 7), then sends the app `press_key` with `source: "dashboard"`, and returns the app's reply. Errors:

- `not_found`: unknown pad
- `offline`: the PC isn't connected
- `control_off`: the app's control setting is off
- `unauthorized`: the user isn't allowed to press
- `failed`: the app said no, or didn't answer within 10 s; `message` says why

### 5.4 `stream_dock_ha/mouse`

```json
{ "type": "stream_dock_ha/mouse", "pad_id": "...", "action": "click", "x": 0.5, "y": 0.5, "button": "left", "amount": 1 }
```

The mouse on Mini Monitor, from the Mini Monitor card. `action` is `move`, `down`, `up`, `click` or `scroll`; `x` and `y` say where on the frame's picture (section 3.6), as parts of its width and height; `button` and `amount` are optional, as in the app's `mouse` command. Only administrators may send it. The integration sends the app `mouse` with `source: "dashboard"` and returns the app's reply. Errors:

- `not_found`: unknown pad
- `offline`: the PC isn't connected
- `control_off`: the app's control setting is off
- `unauthorized`: the user isn't an administrator
- `failed`: the app said no, or didn't answer within 10 s; `message` says why, for example `Mouse from dashboard cards is off in Stream Dock HA (Monitor tab)` or `Mini Monitor isn't showing on this pad`

These commands can also fail with `not_set_up` when the integration has no config entry.

## 6. Alerts

An alert covers all of a pad's screen keys with one picture, drawn across the gaps the way a stretched camera is. The band and the buttons stay as they are.

- **Picture:** the alert's colour (default a strong amber), with its icon, title and message placed inside the keys so the gaps don't hide them: the title along the top row, the icon in a key of its own, and the message along the bottom, running on from key to key.
- **With `camera`:** the camera's live picture fills the alert instead, refreshed as camera keys are, and the title stays as a strip at the top.
- **Pressing:** the card shows a "press any key to dismiss" hint. Keyboard shortcuts aren't presses on the pad: they run as usual and leave the alert up. Any press on that pad (a key, a button, a knob, on the pad, on screen or on the card) dismisses the alert and does nothing else. It's announced with `dismissed: true`.
- **`seconds`:** a value above 0 takes the alert away by itself after that long.
- **A new alert replaces the old one.** Alerts aren't saved: they're gone when the app restarts.

### 6.1 Something on one key (`show_on_key`)

Like an alert, but on a single screen key, over whatever that key shows on the pad's running profile, whichever page it's on. It shows on the pad, on pads on screen and on cards.

- **The key** is addressed on the pad's running profile: `key` as a number (`3` or `"3"`) or a control's name (`"key_3"`), or `control`. A button, a knob or a band tile is refused: it has no key screen.
- **What it shows:** the colour (default the alerts' amber), the `title` and `message` as lines of words, and the `icon` above them. Without words or a picture, a bell. With `camera`, the camera's live picture fills the key, refreshed as camera keys are. With `picture`, a still picture fills it: an `image.*` entity (fetched from `/api/image_proxy/…`), a path on Home Assistant (`/local/door.png`), a web address, or a `data:image/…;base64,…` address. The app's token is only sent to Home Assistant's own address. A picture that can't be fetched or read is refused with the reason, and nothing is shown. `camera` and `picture` can't go together. Words are drawn over a camera or picture.
- **`seconds`:** 30 when left out; 0 keeps it until the key is pressed.
- **Several keys** can show something at once. A new one on the same key replaces the old one. An alert covers them all while it's up.
- **Pressing that key** (on the pad, on screen, on a card or with `press_key`, but not a keyboard shortcut) takes it away and does nothing else, announced as a press with `dismissed: true` and that key's control. Other keys work as usual. A press that only wakes a dark screen, takes Mini Monitor away or dismisses an alert leaves it up. A `press_key` naming another profile or page than the one showing presses that key as usual.
- They aren't saved: they're gone when the app restarts.

## 7. Who may do what

### In the app

These rules apply to every route Home Assistant has into the app (events, actions, entities, the card).

1. **Press keys, switch profiles and pages, and change keys** (`ha_control`, off by default) must be on for any command but `state`, `get_key` and `snapshot`.
2. Each key has **Pressing from Home Assistant** (`remote`), one of:
   - `auto` (the default): it can be pressed, unless one of its steps acts on the PC (`open`, `website`, `shortcut`, `type_text`).
   - `allow`: it can always be pressed.
   - `deny`: it can never be pressed.

   This applies to `press_key` from any `source` but `pad`, `screen` and `hotkey`.
3. Home Assistant can't change a key's `remote`: a `set_key` that tries is refused. A `set_key` that changes `actions` puts `remote` back to `auto`.
4. Adding steps that act on the PC still needs **Add keys that open programs or press keys** (`ha_control_programs`).
5. `mouse` also needs **Cards can use the mouse** in the **Monitor** tab (`ha_mouse`, off by default), which works only with **Press keys, switch profiles and pages, and change keys** on. It's refused from sources `pad`, `screen` and `hotkey`. Keys' `remote` doesn't apply to it.

### In the integration

- Changing an entity (the profile select, the page number, the screen light, the Mini Monitor switch) follows Home Assistant's usual entity permissions, like any other device.
- Actions that change things (everything but `get_state`, `get_key` and `snapshot`) are refused with `unauthorized` when they're called by a logged-in user who isn't an administrator. Automations and scripts, which run without a user, are allowed.
- The card's `press` is allowed for any logged-in user, unless the integration's option **Only administrators can press keys on dashboards** is on.
- The card's `mouse` is only for administrators: it moves the PC's real pointer.
- **The app's commands need an administrator's token:** `connect`, `state`, `pressed`, `pictures` and `reply`. A non-admin user gets `unauthorized`, so nobody can pose as a PC from a dashboard login. The app's event route already needs an admin token, so nothing changes for the person. The integration remembers which HA user each PC connected as, for the log.
- **PC and pad ids share one space.** `connect` with an `instance_id` that is a known pad id gets `renew_instance`. A `state` listing a pad whose id is a known `instance_id` gets that id back in `renew_pads`.
- **Request ids are random**, 16 hex characters prefixed `r-`, so they can't be guessed or repeated across reloads.
- **Only real controls are kept.** The integration keeps pictures only for the layout's `screen` controls, and drops its cache when the layout version changes.

## 8. What the integration creates

Device identifiers are `("stream_dock_ha", instance_id)` for a PC and `("stream_dock_ha", pad_id)` for a pad. Each pad's device has `via_device` set to its PC's device.

| Entity | Device | Unique id | Notes |
| --- | --- | --- | --- |
| `select` Profile | pad | `<pad_id>_profile` | Options are profile names. Selecting sends `show_profile` |
| `number` Page | pad | `<pad_id>_page` | 1 to `pages`, box mode. Setting it sends `show_page` |
| `light` Screen | pad | `<pad_id>_screen` | On/off follows `screen_on`; brightness 0–100 is shown as 0–255. `turn_off` sends `set_screen` off; `turn_on` sends `set_screen` on, and `set_brightness` if a brightness is given |
| `switch` Mini Monitor | pad | `<pad_id>_mini_monitor` | Only when `mini_monitor` isn't `null` |
| `binary_sensor` Connected | pad | `<pad_id>_connected` | Connectivity. Not created for `dashboard` pads |
| `event` Press | pad | `<pad_id>_press` | Event types are the layout's pressable control names, plus `dismissed`. Attributes: `profile`, `page`, `title`, `source` |
| `image` Picture | pad | `<pad_id>_picture` | Fetched with `snapshot` when asked for. `image_last_updated` changes with `look` |
| `notify` Alert | pad | `<pad_id>_alert` | `send_message` sends `show_alert` with `title` and `message` |
| `binary_sensor` Microphone muted | PC | `<instance_id>_mic_muted` | |
| `sensor` CPU, Memory, GPU | PC | `<instance_id>_cpu`, `…_memory`, `…_gpu` | %, measurement. Disabled by default |
| `sensor` Last press | PC | `<instance_id>_last_press` | Timestamp |
| `binary_sensor` Online | PC | `<instance_id>_online` | Connectivity. The one entity that stays available while the PC is offline |

Every entity but **Online** is unavailable while its PC is offline. A pad's entities are also unavailable while its pad isn't listed in the latest `state`. A virtual pad (`dashboard`) its PC no longer lists was deleted in the app, so the integration removes its device and entities. A physical pad listed nowhere for good is removed by deleting its device in Home Assistant, which the integration allows.

Each press also fires the bus event `stream_dock_ha_event` with `device_id`, `pad_id`, `control`, `profile`, `page`, `title`, `source`, `dismissed`. Device triggers are built on it: type `pressed`, subtype the control name. The app keeps firing its own `stream_dock_ha_pressed` events as before, for existing automations.

### Actions (`stream_dock_ha.*`)

Each action takes `device_id` (a pad device; a selector limited to this integration), plus the fields of the app command of the same name. The integration turns it into a `command` event for that pad's PC, with `pad` set to the `pad_id`.

| Action | App command | Response data |
| --- | --- | --- |
| `show_profile`, `next_profile`, `previous_profile`, `first_profile` | same | optional |
| `show_page`, `next_page`, `previous_page`, `add_page`, `delete_page` | same | optional |
| `add_profile`, `rename_profile`, `duplicate_profile`, `delete_profile` | same | optional |
| `set_key`, `add_key`, `clear_key`, `press_key`, `swap_keys`, `copy_key`, `move_key` | same | optional |
| `get_key`, `get_state` | `get_key`, `state` | only |
| `set_brightness`, `set_screen`, `mini_monitor` | same | optional |
| `show_alert`, `clear_alert` | same | optional |
| `show_on_key`, `clear_on_key` | same; `key` takes a number or a control's name | optional |

An action fails (raises `HomeAssistantError`) when the app answers `ok: false`, the PC is offline, or there's no answer within 10 s.

### Stored by the integration

These go in `.storage/stream_dock_ha`, so entities exist (unavailable) after Home Assistant restarts while a PC is off:

- each known PC: `instance_id`, `machine`, `name`;
- each pad: its last `PadState` without pictures.

Pictures are kept only in memory.

## 9. Versions

- `protocol` is 1. A change that an older side would misread raises it. Adding an optional field doesn't.
- The integration accepts only its own protocol number, and the app does the same. Each side shows the other's version in its diagnostics.

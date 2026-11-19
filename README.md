<img src="brand/logo.png" alt="Bugne" width="233">

# Bugne for Home Assistant

A Home Assistant custom integration for [Bugne](https://github.com/Tupile/bugne-releases),
an ESP32-based audio player for kids (web radios, podcasts, local SD music,
Sendspin/Music Assistant, an alarm clock and quiet hours). It talks to the
device's local HTTP API, no cloud involved, and is discovered automatically
on your network via zeroconf.

## Features

| Entity | Type | Description |
|---|---|---|
| Player | `media_player` | Play/pause/stop, next/previous, volume, seek (local files, firmware 1.5.0+), source (web radios), play a specific SD track, sleep timer (`set_sleep_timer` service) |
| Notifications | services | Show a text on the device screen with up to two answer buttons (`send_notification`, `clear_notification`), see below |
| Signal strength | `sensor` (diagnostic) | Wi-Fi RSSI |
| Last boot | `sensor` (diagnostic) | Device uptime, as a timestamp |
| Free memory | `sensor` (diagnostic, disabled by default) | Free heap |
| SD card free space | `sensor` (diagnostic) | Free space on the SD card |
| SD card | `binary_sensor` (diagnostic) | Whether an SD card is inserted |
| Times-tables game | `switch` (config) | Show/hide the on-device game |
| Quiet hours 1 / 2 | `switch` (config) | Enable/disable each quiet-hours window |
| Alarm N | `switch` (config) | Enable/disable each configured alarm, one per alarm |
| Volume limit | `number` (config) | Parental volume ceiling |
| Reboot | `button` (diagnostic) | Restart the device |
| Check for firmware update | `button` (diagnostic) | Trigger a live GitHub OTA check |
| Refresh podcasts | `button` | Refresh all podcast RSS feeds |
| Firmware | `update` | Install the latest firmware via GitHub OTA |
| Screen | `camera` (diagnostic) | On-demand screenshot of the device screen |

## Installation

### HACS (custom repository)

1. In HACS, go to **Integrations**, open the menu (top right), choose
   **Custom repositories**.
2. Add `https://github.com/Tupile/bugne-hass` as an **Integration**.
3. Install "Bugne" from HACS, then restart Home Assistant.

### Manual

1. Copy `custom_components/bugne` into your Home Assistant `custom_components`
   directory.
2. Restart Home Assistant.

## Configuration

Bugne devices on the network are discovered automatically (zeroconf) and show
up under **Settings -> Devices & Services -> Discovered**. You can also add
one manually with **Add Integration -> Bugne**, entering its IP address or
hostname.

If the device's web config page has a password set, enter it during setup
(any username works, Basic Auth only checks the password). Leave it empty if
the device has no password.

The polling interval (default 5 seconds) can be changed from the integration's
**Configure** options.

### Agenda screen (calendar and weather)

The device can show the next three events of a calendar and the weather on
its own screen. In the integration's **Configure** options, pick a calendar
entity, a weather entity, or both. Home Assistant then sends the text to the
device whenever it changes; nothing is configured on the device itself.

- On the device, the home screen clock shows the current weather and the
  temperature. Tap it to open the agenda screen.
- The screen shows the current weather as a pictogram, the temperature,
  today's minimum and maximum (daily forecast), a droplet when the hourly
  forecast announces rain within the hour, and the next three events of the
  coming seven days.
- Dates are written in the language of Home Assistant (English, French or
  German; English otherwise).
- Needs device firmware 1.27.0 or newer. The device keeps the data in memory
  only and hides it after two hours without news from Home Assistant.

### Notifications with answers

Home Assistant can show a text on the device, with up to two answer buttons.
A bell appears at the top of the device's home screen and a short message
announces it; a tap on the bell opens the notification. There is no sound and
a sleeping screen stays off. The device holds one notification at a time: a
new one replaces the previous one, and a reboot loses it.

Send one with the `bugne.send_notification` action on the player entity:

```yaml
action: bugne.send_notification
target:
  entity_id: media_player.bugne
data:
  title: Home
  message: Turn off the living room?
  id: living-room-off
  actions:
    - id: "yes"
      label: "Yes"
    - id: "no"
      label: "No"
```

The answer fires the `bugne_notification_action` event, with `id`, `action`,
`device_id` and `entry_id`:

```yaml
triggers:
  - trigger: event
    event_type: bugne_notification_action
    event_data:
      id: living-room-off
      action: "yes"
actions:
  - action: light.turn_off
    target:
      entity_id: light.living_room
```

- Without `actions` the device shows a single OK button and no event is fired.
- `bugne.clear_notification` removes the notification from the device.
- Quote `"yes"` and `"no"` in YAML: bare, they are booleans.
- The device posts the answer to a Home Assistant webhook, so it must reach
  Home Assistant's local URL (Settings, System, Network). A `.local` name
  works over `http://` only; with `https://` use a name the device can
  resolve through DNS and a certificate from a public authority.
- If Home Assistant cannot be reached, the device says so and keeps the
  notification, so the answer can be tried again.
- An answer can reach Home Assistant twice when the network is slow: prefer
  `turn_on` / `turn_off` to `toggle` in the automation.
- Needs device firmware 1.29.0 or newer.

## Note (FR)

Cette intégration pilote un [Bugne](https://github.com/Tupile/bugne-releases), un
lecteur audio pour enfants. Voir le dépôt du projet pour le firmware et la
documentation matérielle.

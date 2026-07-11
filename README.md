# Bugne for Home Assistant

A Home Assistant custom integration for [Bugne](https://github.com/Tupile/bugne-releases),
an ESP32-based audio player for kids (web radios, podcasts, local SD music,
Sendspin/Music Assistant, an alarm clock and quiet hours). It talks to the
device's local HTTP API, no cloud involved, and is discovered automatically
on your network via zeroconf.

## Features

| Entity | Type | Description |
|---|---|---|
| Player | `media_player` | Play/pause/stop, next/previous, volume, source (web radios), play a specific SD track, sleep timer (`set_sleep_timer` service) |
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

## Note (FR)

Cette intégration pilote un [Bugne](https://github.com/Tupile/bugne-releases), un
lecteur audio pour enfants. Voir le dépôt du projet pour le firmware et la
documentation matérielle.

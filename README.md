# Broadlink2MQTT

<p align="center">
  <img src="broadlink2mqtt/logo.png" alt="Broadlink2MQTT" width="360"/>
</p>

![GitHub Release](https://img.shields.io/github/v/release/pranjal-joshi/Broadlink2MQTT?style=for-the-badge&logo=github&logoColor=white&label=RELEASE&color=10B981)
[![License](https://img.shields.io/github/license/pranjal-joshi/Broadlink2MQTT?style=for-the-badge&logo=scroll&logoColor=white&label=LICENSE&color=orange)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-41BDF5?style=for-the-badge&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/addons/)
[![Docs](https://img.shields.io/badge/docs-github.io-8A2BE2?style=for-the-badge)](https://pranjal-joshi.github.io/Broadlink2MQTT/)

**Your Broadlink blaster, as real Home Assistant infrared entities.** This
add-on bridges Broadlink RM devices to MQTT, publishing them as native
`infrared` emitter and receiver entities through MQTT discovery — so they work
with device integrations like LG Infrared, with `infrared.send_command`, and
with anything else that consumes the infrared platform.

> 👀 **New here?** Start with the [documentation site](https://pranjal-joshi.github.io/Broadlink2MQTT/),
> or jump to [Installation](#installation) below.

## Why an add-on and not an integration?

Home Assistant 2026.4 added `infrared` entities, and 2026.8 added the MQTT
emitter/receiver schemas. The official Broadlink integration still cannot offer
them, because an RM device **cannot listen passively** — a receiver entity has
to hold it in learning mode and poll it.

[home-assistant/core#177767][pr] proposed exactly that and was closed:

> The Infrared receiver entity is meant to be used by devices that can receive
> constantly […] I don't think it should be implemented for Broadlink until
> Broadlink provides a firmware that allows for constant receiving.

The objection is about *where the state machine lives*, not whether it works.
Outside of core — where a capture window can be driven by a switch you control —
the same approach is perfectly sound. This add-on is that state machine, moved
into its own process, wired to MQTT discovery so Home Assistant needs no custom
code at all.

[pr]: https://github.com/home-assistant/core/pull/177767

## Features

- 📡 **Infrared emitter entity** — send raw timings, with `repeat_count` support
- 🎯 **Infrared receiver entity** — captured signals reported as raw timings
- 🎓 **Learning mode switch** — opens a bounded, self-closing capture window
- 📋 **Last captured code sensor** — base64 packet and raw timings as attributes
- 🌡️ **Temperature & humidity** — for RM pro, RM4 mini and RM4 pro
- 🔍 **Auto-discovery** — UDP broadcast, plus explicit IPs for other subnets
- 🔌 **Zero-config MQTT** — picks up the broker from the Supervisor
- 🏠 **No custom components** — pure MQTT discovery, nothing to install in HA

## Installation

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fpranjal-joshi%2FBroadlink2MQTT)

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add `https://github.com/pranjal-joshi/Broadlink2MQTT`
3. Install **Broadlink2MQTT**, then **Start**

Defaults work out of the box if you run the Mosquitto broker add-on — the
add-on asks the Supervisor for your broker, so there are no credentials to copy.

> ⚠️ **Remove your blaster from the official Broadlink integration first.** Both
> compete for the same IR front end.

## Configuration

Everything is optional. The common case is to change nothing.

```yaml
mqtt_host: ""              # blank = use the Supervisor's MQTT service
base_topic: broadlink2mqtt
discovery_prefix: homeassistant
auto_discover: true
devices: []                # add by IP if broadcast does not reach the device
capture_window: 15         # seconds of listening after the switch turns on
capture_limit: 60          # hard cap on one session
log_level: info
```

Full reference: [DOCS.md](broadlink2mqtt/DOCS.md) or the
[configuration page](https://pranjal-joshi.github.io/Broadlink2MQTT/configuration.html).

## Usage

**Capture a code** — turn on *Learning mode*, press a button on your remote. The
receiver entity fires and *Last captured code* holds the result. The window
extends with each capture and closes itself.

**Send a code:**

```yaml
actions:
  - action: infrared.send_command
    target:
      entity_id: infrared.living_room_blaster_emitter
    data:
      timings: [9000, -4500, 560, -560, 560, -1690, 560]
      modulation: 38000
      repeat_count: 1
```

## Limitations

| Limitation | Why |
|---|---|
| Modulation always reported as 38 kHz | Broadlink hardware does not report the captured carrier frequency |
| No RF (315/433 MHz) | HA's infrared entities are IR only; RF captures are rejected, not mis-reported |
| `aarch64` and `amd64` only | `cryptography` has no musl wheels for 32-bit ARM |
| Learning mode lingers ~30 s after a window closes | The firmware has no "exit learning" command |

## Credits

The capture-window state machine is ported from
[home-assistant/core#177767](https://github.com/home-assistant/core/pull/177767)
(Apache-2.0), including its timing constants. The IR codec arithmetic lives
upstream in [python-broadlink](https://github.com/mjg59/python-broadlink).

## License

MIT — see [LICENSE](LICENSE).

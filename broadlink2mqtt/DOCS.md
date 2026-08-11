# Broadlink2MQTT

Bridges Broadlink RM infrared blasters to Home Assistant as native **MQTT
infrared emitter and receiver entities**, plus a learning-mode switch for
capturing codes.

## Why this exists

Home Assistant 2026.4 added `infrared` entities, and 2026.8 added the MQTT
emitter/receiver schemas. The official Broadlink integration cannot provide
them: an RM device cannot listen passively, so a receiver entity has to hold it
in learning mode and poll it. [core#177767][pr] proposed exactly that and was
closed, because a core receiver entity is expected to be listening constantly.

Outside of core, where the capture window can be driven by a switch you control,
the same approach works fine. That is what this add-on does.

[pr]: https://github.com/home-assistant/core/pull/177767

## Installation

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add `https://github.com/pranjal-joshi/Broadlink2MQTT`
3. Install **Broadlink2MQTT** from the store listing that appears
4. Start it — the defaults work if you run the Mosquitto broker add-on

## Configuration

### MQTT

Leave `mqtt_host` blank and the add-on asks the Supervisor for the broker you
already configured — no credentials to copy. Fill these in only to point at an
external broker.

| Option | Default | Description |
|---|---|---|
| `mqtt_host` | *(blank)* | Broker hostname. Blank = use the Supervisor's MQTT service. |
| `mqtt_port` | `1883` | Broker port. |
| `mqtt_username` | *(blank)* | Broker username. |
| `mqtt_password` | *(blank)* | Broker password. |
| `mqtt_ssl` | `false` | Connect with TLS. |
| `base_topic` | `broadlink2mqtt` | Root of every topic this add-on owns. |
| `discovery_prefix` | `homeassistant` | Must match your MQTT integration's discovery prefix. |

### Devices

| Option | Default | Description |
|---|---|---|
| `auto_discover` | `true` | Find devices by UDP broadcast on startup. |
| `discovery_timeout` | `5` | Seconds to wait for discovery replies. |
| `devices` | `[]` | Devices to add by IP, for when broadcast does not reach them. |

Auto-discovery uses a UDP broadcast that does not cross VLANs or subnets. If
your blaster is on another network segment, list it explicitly:

```yaml
auto_discover: false
devices:
  - host: 192.168.1.50
    name: Living Room Blaster
  - host: 192.168.1.51
```

`name` is optional and only sets the device name in Home Assistant.

### Capture behaviour

You should not need to touch these. The values come from [core#177767][pr],
where they were tuned against real hardware.

| Option | Default | Description |
|---|---|---|
| `capture_window` | `15` | Seconds to listen after the switch is turned on, and after each capture. |
| `capture_limit` | `60` | Hard cap on one listening session, however many codes arrive. |
| `poll_interval` | `1` | Seconds between `check_data` polls. |
| `rearm_interval` | `20` | Re-arm learning mode this often, ahead of the device's own timeout. |
| `publish_sensors` | `true` | Publish temperature/humidity for devices that have them. |
| `log_level` | `info` | Set to `debug` when reporting a problem. |

## Entities

Each blaster arrives as one device with these entities:

| Entity | Type | Purpose |
|---|---|---|
| **Emitter** | `infrared` | Send IR. Consumed by device integrations like LG Infrared, or `infrared.send_command`. |
| **Receiver** | `infrared` | Reports captured signals. Fires while learning mode is on. |
| **Learning mode** | `switch` | Opens the capture window. Auto-closes; see below. |
| **Last captured code** | `sensor` | The most recent capture. Full base64 and raw timings are in its attributes. |
| **Temperature** / **Humidity** | `sensor` | RM4 mini/pro and RM pro only. |

## Capturing a code

1. Turn on **Learning mode**. The blaster's LED lights up.
2. Point a remote at it and press a button.
3. The **Receiver** entity updates, and **Last captured code** holds the result.
4. The switch turns itself off after `capture_window` seconds of quiet, or
   `capture_limit` seconds total.

Each capture extends the window, so you can record several buttons in one
session without touching the switch again.

To grab the raw code for use elsewhere:

```jinja
{{ state_attr('sensor.<device>_last_captured_code', 'base64') }}
{{ state_attr('sensor.<device>_last_captured_code', 'timings') }}
```

### Keeping it listening longer

`capture_limit` caps a single session deliberately — learning mode keeps the
device's radio and LED active and blocks transmission. If you want a long
capture session, raise `capture_limit`, or re-trigger the switch:

```yaml
automation:
  - alias: Hold IR learning open
    triggers:
      - trigger: state
        entity_id: switch.living_room_blaster_learning_mode
        to: "off"
    conditions:
      - condition: state
        entity_id: input_boolean.ir_capture_session
        state: "on"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.living_room_blaster_learning_mode
```

## Sending a code

Use the emitter entity directly:

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

Or publish to the command topic yourself:

```yaml
actions:
  - action: mqtt.publish
    data:
      topic: broadlink2mqtt/a1b2c3d4e5f6/emitter/set
      payload: >-
        {"timings": [9000, -4500, 560], "modulation": 38000, "repeat_count": 0}
```

## MQTT topics

With `base_topic: broadlink2mqtt` and a device whose MAC is `a1:b2:c3:d4:e5:f6`:

| Topic | Direction | Payload |
|---|---|---|
| `broadlink2mqtt/status` | out | `online` / `offline` (last will) |
| `broadlink2mqtt/a1b2c3d4e5f6/availability` | out | `online` / `offline` |
| `broadlink2mqtt/a1b2c3d4e5f6/emitter/set` | **in** | `{"timings": [...], "modulation": 38000, "repeat_count": 0}` |
| `broadlink2mqtt/a1b2c3d4e5f6/receiver/state` | out | `{"timings": [...], "modulation": 38000}` |
| `broadlink2mqtt/a1b2c3d4e5f6/learn/set` | **in** | `ON` / `OFF` |
| `broadlink2mqtt/a1b2c3d4e5f6/learn/state` | out | `ON` / `OFF` |
| `broadlink2mqtt/a1b2c3d4e5f6/code/state` | out | `{"short", "base64", "timings", "modulation"}` |
| `broadlink2mqtt/a1b2c3d4e5f6/sensor/state` | out | `{"temperature": 21.4, "humidity": 48.0}` |

## Running as a plain container

Outside the Supervisor there is no `/data/options.json`, so every option is read from an
environment variable of the same name in upper case — `MQTT_HOST`, `MQTT_USERNAME`,
`MQTT_PASSWORD`, `AUTO_DISCOVER`, `CAPTURE_LIMIT`, `LOG_LEVEL` and the rest. The one
exception is `devices`, which becomes `DEVICES` as a comma-separated list of IPs.

On a Docker bridge network, set `AUTO_DISCOVER=false` and pin the blaster with `DEVICES`.
Broadcast discovery needs host networking, but talking to a known IP is plain unicast and
works through Docker's NAT.

```yaml
services:
  broadlink2mqtt:
    image: ghcr.io/pranjal-joshi/broadlink2mqtt:1.0.2
    restart: unless-stopped
    environment:
      - MQTT_HOST=mosquitto
      - MQTT_USERNAME=addons
      - MQTT_PASSWORD=${MQTT_PASSWORD:?set it in .env}
      - AUTO_DISCOVER=false
      - DEVICES=192.168.1.50
    networks: [ha_network]
    depends_on: [mosquitto]
```

## Known limitations

- **Remove the device from the official Broadlink integration.** Both fight over
  the same IR front end, and `remote.learn_command` will fail while a capture
  window is open.
- **Modulation is always reported as 38 kHz.** Broadlink hardware does not tell
  you the carrier frequency it captured, and the encoder's 32.84 µs tick assumes
  38 kHz. Signals at other carriers still round-trip, but the reported
  `modulation` is a fixed value, not a measurement.
- **RF (315/433 MHz) is not supported.** RM pro and RM4 pro can learn RF, but
  Home Assistant's infrared entities are IR only. RF captures are rejected
  rather than reported as bogus IR.
- **The device stays in learning mode briefly after a window closes.** There is
  no "exit learning" command; the firmware times out on its own within ~30 s.
- **Only `aarch64` and `amd64`.** `cryptography`, which `python-broadlink`
  depends on, has no musl wheels for 32-bit ARM.

## Troubleshooting

**No devices found.** Check that the add-on's host networking is on (it is by
default), that the blaster is on the same subnet, and that it is not already
locked to the Broadlink cloud app. Otherwise list it by IP under `devices`.

**Codes capture but the emitter does nothing.** Almost always a range or aim
problem — an RM mini's emitter is directional. Try `repeat_count: 1`.

**The learning switch turns itself off immediately.** The device rejected
`enter_learning`, usually because something else holds the session. Remove the
device from the official Broadlink integration and restart the add-on.

**Nothing appears in Home Assistant.** Confirm `discovery_prefix` matches the
MQTT integration's setting, then check the add-on log for `Announced N entities`.

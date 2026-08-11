# Changelog

## 1.0.0

Initial release.

### Added

- **Infrared emitter entity** per Broadlink RM device, via MQTT discovery.
  Accepts Home Assistant's `{timings, modulation, repeat_count}` payload and
  encodes it to the Broadlink packet format.
- **Infrared receiver entity** that reports captured signals as raw timings.
- **Learning mode switch** that opens a bounded capture window, holding the
  device armed and polling it, then closing on its own.
- **Last captured code sensor** exposing the base64 packet and raw timings as
  attributes, for reuse with `remote.send_command` or elsewhere.
- **Temperature and humidity sensors** for RM pro, RM4 mini and RM4 pro.
- **Auto-discovery** by UDP broadcast, plus explicit `devices` entries by IP
  for blasters on another subnet.
- **Supervisor MQTT integration** — leave `mqtt_host` blank and the broker
  configured in Home Assistant is used automatically.
- Availability tracking with an MQTT last will, and re-announcement when Home
  Assistant restarts.

### Notes

- `repeat_count` is applied by patching byte 1 of the packet; upstream's
  `pulses_to_data` leaves it at zero.
- RF captures are rejected rather than reported as IR.
- Built for `aarch64` and `amd64` only — `cryptography` has no musl wheels for
  32-bit ARM.

# Changelog

## 1.1.0-beta.1

Pre-release. Continuous listening is new and only lightly proven — see the
caveats before enabling it.

### Added

- **Continuous listening (`always_listen`, experimental, off by default).**
  Keeps the receiver armed permanently so pressing a physical remote keeps
  Home Assistant in sync. Measured on an RM4 mini this is cheap: 46 ms median
  per poll, no errors over 90 s, under 5% of wall-clock in device I/O.

  It is best-effort, not reliable, and the limits are structural rather than
  fixable: the blaster cannot transmit and listen at once, so a command sent
  while you press the remote loses one of the two; it is briefly deaf after
  every capture and every transmission; and its LED stays lit continuously.
  For dependable always-on reception, a dedicated ESPHome IR receiver is the
  right hardware.

- **Capture health diagnostic entity.** Publishes listening state, capture
  count, noise discarded, duplicates suppressed, and error streaks. Continuous
  listening is best-effort, so its unreliability is exposed as data rather
  than left to be inferred from a flaky automation at midnight.

- **Watchdog.** After five consecutive device failures the receiver backs off
  to 30 s and reports unavailable, instead of hammering a sick device.

### Fixed

- **Ambient interference is no longer reported as an IR code.** Fluorescent
  flicker, PIR sensors and camera illuminators trip the device's capture just
  as a remote does; an idle RM4 mini produced one such capture roughly every
  18 seconds. Captures whose median space exceeds 10 ms are now discarded —
  no consumer protocol has a within-frame gap that long (NEC's longest is
  4.5 ms), while the measured interference had every space beyond 20 ms.
  Without this, continuous listening would bury real remotes under thousands
  of phantom signals a day.

- **A press arriving just before a session renewal was thrown away.** The
  listen loop called `enter_learning()` before `check_data()` on a re-arm
  tick, and arming discards whatever the device is holding. It now reads
  first, then re-arms. Inherited from core#177767.

- **Held buttons no longer republish every poll.** Identical captures within
  one second are suppressed and counted.

## 1.0.2

### Fixed

- **The container never started.** s6-overlay runs `CMD` with a cleaned
  environment, so the `PYTHONPATH=/app/src` set by `ENV` was stripped and the
  entrypoint died with `No module named broadlink2mqtt`, crash-looping forever.
  This affected every deployment — add-on and plain container alike. `CMD` now
  goes through `with-contenv`, which re-imports the container environment from
  `/run/s6/container_environment`.
- **Configuration was invisible outside the Supervisor.** The same stripping
  discarded runtime `-e` / compose `environment:` values, so a container
  deployment could not be configured at all. Fixed by the same change.
- The package is additionally registered with a `.pth` file in site-packages,
  so importing our own code no longer depends on `PYTHONPATH` surviving at all.
  Written via `site.getsitepackages()` rather than a hardcoded path, so it
  follows the base image's Python version.

Both faults were invisible to CI: the image built and published cleanly, and
nothing in the pipeline ever ran it.

## 1.0.1

### Added

- **Full environment-variable parity for plain containers.** `discovery_timeout`,
  `capture_window`, `capture_limit`, `poll_interval` and `rearm_interval` are now
  read from the environment like every other option. Previously they were only
  settable through the Supervisor's `options.json`, so a Docker deployment was
  stuck with the defaults — which matters most for `CAPTURE_LIMIT`, since the
  60-second default is tight for working through a whole remote.
- Documented the bridge-network setup: with `AUTO_DISCOVER=false` and the blaster
  pinned by `DEVICES`, no host networking is needed. Broadcast discovery requires
  it, but talking to a known IP is plain unicast and works through Docker's NAT.

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

# Contributing

Thanks for wanting to help. This add-on talks to real hardware that behaves in
ways no test can fully capture, so hardware-tested changes are especially
valuable.

## Development setup

```bash
git clone https://github.com/pranjal-joshi/Broadlink2MQTT
cd Broadlink2MQTT

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
pre-commit install
```

## Running the checks

```bash
ruff check .
ruff format --check .
pytest tests/ -v
```

## Running the bridge outside Home Assistant

The bridge reads `/data/options.json` when the Supervisor provides one, and
falls back to environment variables otherwise:

```bash
MQTT_HOST=192.168.1.10 \
MQTT_USERNAME=homeassistant \
MQTT_PASSWORD=secret \
LOG_LEVEL=debug \
PYTHONPATH=broadlink2mqtt/src \
python -m broadlink2mqtt
```

Add `DEVICES=192.168.1.50,192.168.1.51` to skip broadcast discovery.

## Project layout

```
broadlink2mqtt/           the add-on
├── config.yaml           options schema shown in the Home Assistant UI
├── build.yaml            base images per architecture
├── Dockerfile
├── DOCS.md               the add-on's Documentation tab
└── src/broadlink2mqtt/
    ├── codec.py          timings <-> Broadlink packet
    ├── device.py         discovery, auth, the front-end lock
    ├── receiver.py       the capture-window state machine
    ├── discovery.py      MQTT discovery payloads
    └── bridge.py         orchestration
docs/                     the GitHub Pages site
tests/
```

## Things worth knowing

- **The codec is thin on purpose.** `pulses_to_data` / `data_to_pulses` live in
  `python-broadlink`; `codec.py` only bridges the sign convention and patches
  the repeat byte, which upstream leaves at zero.
- **The front-end lock is load-bearing.** A Broadlink device can transmit *or*
  be armed for learning, never both. `FrontEnd.generation` is how the receiver
  loop notices a transmit invalidated its learning session. Do not bypass it.
- **The capture constants are tuned.** `POLL_INTERVAL`, `REARM_INTERVAL`,
  `TRANSMIT_COOLDOWN` and friends come from
  [core#177767](https://github.com/home-assistant/core/pull/177767), where they
  were arrived at against real RM hardware. Change them with evidence.

## Releasing

1. Bump `version` in `broadlink2mqtt/config.yaml`
2. Update `broadlink2mqtt/CHANGELOG.md`
3. Tag `vX.Y.Z` — release.yml verifies the tag matches `config.yaml`, publishes
   the release, then builds and pushes the images to ghcr.io

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

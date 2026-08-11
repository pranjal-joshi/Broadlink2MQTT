"""Constants for Broadlink2MQTT."""

from __future__ import annotations

from typing import Final

NAME: Final = "Broadlink2MQTT"
VERSION: Final = "1.0.0"

# --- Broadlink IR packet layout -------------------------------------------
# byte 0     packet type (0x26 = IR)
# byte 1     repeat count
# bytes 2-3  payload length, little endian
# bytes 4+   pulse durations in 32.84 us ticks
IR_PACKET_TYPE: Final = 0x26
REPEAT_BYTE: Final = 0x01
HEADER_LEN: Final = 4
MAX_REPEAT: Final = 0xFF

# Broadlink hardware does not report the carrier frequency it captured, and
# pulses_to_data()'s 32.84 us tick assumes 38 kHz, so every signal we emit or
# report uses that modulation.
DEFAULT_MODULATION: Final = 38000

# --- Capture window tuning -------------------------------------------------
# These are the values from home-assistant/core#177767, which were arrived at
# against real RM hardware. Changing them is not recommended.
POLL_INTERVAL: Final = 1.0
REARM_INTERVAL: Final = 20.0
ERROR_BACKOFF: Final = 5.0
TRANSMIT_COOLDOWN: Final = 0.3
CAPTURE_WINDOW: Final = 15.0
CAPTURE_LIMIT: Final = 60.0

# --- MQTT ------------------------------------------------------------------
DEFAULT_BASE_TOPIC: Final = "broadlink2mqtt"
DEFAULT_DISCOVERY_PREFIX: Final = "homeassistant"
PAYLOAD_ONLINE: Final = "online"
PAYLOAD_OFFLINE: Final = "offline"
PAYLOAD_ON: Final = "ON"
PAYLOAD_OFF: Final = "OFF"

SENSOR_INTERVAL: Final = 60.0

# Device types that expose an IR front end.
IR_DEVICE_TYPES: Final = frozenset({"RMMINI", "RMMINIB", "RMPRO", "RM4MINI", "RM4PRO"})

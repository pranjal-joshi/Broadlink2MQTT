"""Constants for Broadlink2MQTT."""

from __future__ import annotations

from typing import Final

NAME: Final = "Broadlink2MQTT"
VERSION: Final = "1.1.0-beta.1"

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

# --- Signal plausibility ---------------------------------------------------
# Ambient IR trips a capture just as a remote does. Real protocols keep their
# within-frame spaces to a few milliseconds (NEC's longest is 4.5 ms); the
# interference measured on an idle RM4 mini had every space beyond 20 ms.
MAX_MEDIAN_SPACE_US: Final = 10_000

# A held remote sends repeat frames every ~110 ms; without this the same code
# would be republished on every poll.
DEDUPE_INTERVAL: Final = 1.0

# --- Watchdog --------------------------------------------------------------
# Consecutive device failures before the receiver is declared degraded: it
# backs off hard and reports unavailable rather than hammering a sick device.
DEGRADED_AFTER_ERRORS: Final = 5
DEGRADED_BACKOFF: Final = 30.0

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

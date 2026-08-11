"""MQTT discovery payloads.

Home Assistant's MQTT integration grows the entities; this module only
describes them. Nothing here talks to a Broadlink device.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import (
    NAME,
    PAYLOAD_OFF,
    PAYLOAD_OFFLINE,
    PAYLOAD_ON,
    PAYLOAD_ONLINE,
    VERSION,
)
from .device import BroadlinkDevice

PROJECT_URL = "https://github.com/pranjal-joshi/Broadlink2MQTT"


@dataclass(slots=True, frozen=True)
class Topics:
    """Every topic used by one device."""

    availability: str
    emitter_command: str
    receiver_state: str
    learn_command: str
    learn_state: str
    code_state: str
    sensor_state: str
    health_state: str

    @classmethod
    def build(cls, base_topic: str, slug: str) -> Topics:
        """Return the topic set for a device."""
        root = f"{base_topic}/{slug}"
        return cls(
            availability=f"{root}/availability",
            emitter_command=f"{root}/emitter/set",
            receiver_state=f"{root}/receiver/state",
            learn_command=f"{root}/learn/set",
            learn_state=f"{root}/learn/state",
            code_state=f"{root}/code/state",
            sensor_state=f"{root}/sensor/state",
            health_state=f"{root}/health/state",
        )


def _device_block(device: BroadlinkDevice) -> dict[str, Any]:
    """Return the device registry block shared by every entity."""
    return {
        "identifiers": [f"broadlink2mqtt_{device.slug}"],
        "connections": [["mac", device.mac]],
        "name": device.name,
        "manufacturer": device.api.manufacturer or "Broadlink",
        "model": device.api.model or device.api.type,
        "configuration_url": f"http://{device.host}",
    }


def _origin_block() -> dict[str, Any]:
    """Return the origin block that attributes the entities to this bridge."""
    return {"name": NAME, "sw_version": VERSION, "support_url": PROJECT_URL}


def _availability(status_topic: str, topics: Topics) -> dict[str, Any]:
    """Require both the bridge and the device to be online."""
    return {
        "availability": [
            {"topic": status_topic},
            {"topic": topics.availability},
        ],
        "availability_mode": "all",
        "payload_available": PAYLOAD_ONLINE,
        "payload_not_available": PAYLOAD_OFFLINE,
    }


def build_entities(
    device: BroadlinkDevice,
    topics: Topics,
    status_topic: str,
    discovery_prefix: str,
    *,
    include_sensors: bool,
) -> list[tuple[str, dict[str, Any]]]:
    """Return (config_topic, payload) pairs for every entity of a device.

    Passing an empty payload to a config topic is how MQTT discovery removes an
    entity, which is why the topics are returned alongside the payloads.
    """
    slug = device.slug
    common = _device_block(device), _origin_block(), _availability(status_topic, topics)
    device_block, origin_block, availability = common

    def base(object_id: str, name: str) -> dict[str, Any]:
        return {
            "name": name,
            "unique_id": f"broadlink2mqtt_{slug}_{object_id}",
            "object_id": f"{device.slug}_{object_id}",
            "device": device_block,
            "origin": origin_block,
            **availability,
        }

    entities: list[tuple[str, dict[str, Any]]] = [
        (
            f"{discovery_prefix}/infrared/{slug}/emitter/config",
            {
                **base("emitter", "Emitter"),
                "schema": "emitter",
                "command_topic": topics.emitter_command,
            },
        ),
        (
            f"{discovery_prefix}/infrared/{slug}/receiver/config",
            {
                **base("receiver", "Receiver"),
                "schema": "receiver",
                "state_topic": topics.receiver_state,
            },
        ),
        (
            f"{discovery_prefix}/switch/{slug}/learn/config",
            {
                **base("learn", "Learning mode"),
                "command_topic": topics.learn_command,
                "state_topic": topics.learn_state,
                "payload_on": PAYLOAD_ON,
                "payload_off": PAYLOAD_OFF,
                "icon": "mdi:school",
                "entity_category": "config",
            },
        ),
        (
            f"{discovery_prefix}/sensor/{slug}/last_code/config",
            {
                **base("last_code", "Last captured code"),
                "state_topic": topics.code_state,
                "value_template": "{{ value_json.short }}",
                "json_attributes_topic": topics.code_state,
                "icon": "mdi:remote",
                "entity_category": "diagnostic",
            },
        ),
        (
            # Continuous listening is best-effort. This entity is how that
            # shows up as data — noise rate, error streaks, capture counts —
            # instead of being guessed at from a flaky automation.
            f"{discovery_prefix}/sensor/{slug}/capture_health/config",
            {
                **base("capture_health", "Capture health"),
                "state_topic": topics.health_state,
                "value_template": "{{ value_json.status }}",
                "json_attributes_topic": topics.health_state,
                "icon": "mdi:radar",
                "entity_category": "diagnostic",
            },
        ),
    ]

    if include_sensors and device.supports_sensors:
        entities.append(
            (
                f"{discovery_prefix}/sensor/{slug}/temperature/config",
                {
                    **base("temperature", "Temperature"),
                    "state_topic": topics.sensor_state,
                    "value_template": "{{ value_json.temperature }}",
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "unit_of_measurement": "°C",
                },
            )
        )
        if device.api.type in ("RM4MINI", "RM4PRO"):
            entities.append(
                (
                    f"{discovery_prefix}/sensor/{slug}/humidity/config",
                    {
                        **base("humidity", "Humidity"),
                        "state_topic": topics.sensor_state,
                        "value_template": "{{ value_json.humidity }}",
                        "device_class": "humidity",
                        "state_class": "measurement",
                        "unit_of_measurement": "%",
                    },
                )
            )

    return entities

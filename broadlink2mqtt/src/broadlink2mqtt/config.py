"""Runtime configuration.

Options come from the add-on's ``/data/options.json`` when running under the
Supervisor, and from environment variables when running as a plain container.
If no MQTT host is configured, the Supervisor's MQTT service is used.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

from .const import (
    CAPTURE_LIMIT,
    CAPTURE_WINDOW,
    DEFAULT_BASE_TOPIC,
    DEFAULT_DISCOVERY_PREFIX,
    POLL_INTERVAL,
    REARM_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

OPTIONS_PATH = Path("/data/options.json")
SUPERVISOR_MQTT_URL = "http://supervisor/services/mqtt"


@dataclass(slots=True)
class DeviceConfig:
    """A manually configured Broadlink device."""

    host: str
    mac: str | None = None
    name: str | None = None


@dataclass(slots=True)
class Config:
    """Bridge configuration."""

    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_ssl: bool = False
    base_topic: str = DEFAULT_BASE_TOPIC
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX
    auto_discover: bool = True
    discovery_timeout: int = 5
    devices: list[DeviceConfig] = field(default_factory=list)
    capture_window: float = CAPTURE_WINDOW
    capture_limit: float = CAPTURE_LIMIT
    poll_interval: float = POLL_INTERVAL
    rearm_interval: float = REARM_INTERVAL
    always_listen: bool = False
    publish_sensors: bool = True
    log_level: str = "info"

    @property
    def status_topic(self) -> str:
        """Bridge-wide availability topic, used as the MQTT last will."""
        return f"{self.base_topic}/status"


def _read_options() -> dict[str, Any]:
    """Read add-on options, falling back to environment variables."""
    if OPTIONS_PATH.is_file():
        try:
            return json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _LOGGER.warning("Could not read %s: %s", OPTIONS_PATH, err)

    options: dict[str, Any] = {}
    # Strings and numbers alike; load_config() coerces each to its real type.
    for key in (
        "mqtt_host",
        "mqtt_port",
        "mqtt_username",
        "mqtt_password",
        "base_topic",
        "discovery_prefix",
        "log_level",
        "discovery_timeout",
        "capture_window",
        "capture_limit",
        "poll_interval",
        "rearm_interval",
    ):
        if (value := os.environ.get(key.upper())) is not None:
            options[key] = value
    for key in ("auto_discover", "mqtt_ssl", "publish_sensors", "always_listen"):
        if (value := os.environ.get(key.upper())) is not None:
            options[key] = value.strip().lower() in ("1", "true", "yes", "on")
    if hosts := os.environ.get("DEVICES", "").strip():
        options["devices"] = [
            {"host": h.strip()} for h in hosts.split(",") if h.strip()
        ]
    return options


async def _supervisor_mqtt() -> dict[str, Any] | None:
    """Ask the Supervisor for the MQTT service the user already configured."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                SUPERVISOR_MQTT_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response,
        ):
            if response.status != 200:
                _LOGGER.debug("Supervisor MQTT service returned %s", response.status)
                return None
            payload = await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Could not reach the Supervisor MQTT service: %s", err)
        return None

    return payload.get("data") or None


async def load_config() -> Config:
    """Build the runtime configuration."""
    options = _read_options()

    config = Config(
        mqtt_host=str(options.get("mqtt_host") or ""),
        mqtt_port=int(options.get("mqtt_port") or 1883),
        mqtt_username=str(options.get("mqtt_username") or ""),
        mqtt_password=str(options.get("mqtt_password") or ""),
        mqtt_ssl=bool(options.get("mqtt_ssl", False)),
        base_topic=str(options.get("base_topic") or DEFAULT_BASE_TOPIC).strip("/"),
        discovery_prefix=str(
            options.get("discovery_prefix") or DEFAULT_DISCOVERY_PREFIX
        ).strip("/"),
        auto_discover=bool(options.get("auto_discover", True)),
        discovery_timeout=int(options.get("discovery_timeout") or 5),
        devices=[
            DeviceConfig(
                host=str(entry["host"]).strip(),
                mac=(str(entry["mac"]).strip() or None) if entry.get("mac") else None,
                name=(str(entry["name"]).strip() or None)
                if entry.get("name")
                else None,
            )
            for entry in options.get("devices") or []
            if entry.get("host")
        ],
        capture_window=float(options.get("capture_window") or CAPTURE_WINDOW),
        capture_limit=float(options.get("capture_limit") or CAPTURE_LIMIT),
        poll_interval=float(options.get("poll_interval") or POLL_INTERVAL),
        rearm_interval=float(options.get("rearm_interval") or REARM_INTERVAL),
        always_listen=bool(options.get("always_listen", False)),
        publish_sensors=bool(options.get("publish_sensors", True)),
        log_level=str(options.get("log_level") or "info"),
    )

    if not config.mqtt_host:
        if service := await _supervisor_mqtt():
            config.mqtt_host = service.get("host", "")
            config.mqtt_port = int(service.get("port", 1883))
            config.mqtt_username = service.get("username", "") or ""
            config.mqtt_password = service.get("password", "") or ""
            config.mqtt_ssl = bool(service.get("ssl", False))
            _LOGGER.info(
                "Using the Supervisor MQTT service at %s:%s",
                config.mqtt_host,
                config.mqtt_port,
            )
        else:
            raise ValueError(
                "No MQTT broker configured. Set 'mqtt_host' in the add-on options, "
                "or install the Mosquitto broker add-on so it can be detected "
                "automatically."
            )

    if config.capture_limit < config.capture_window:
        _LOGGER.warning(
            "capture_limit (%.0fs) is below capture_window (%.0fs); raising it",
            config.capture_limit,
            config.capture_window,
        )
        config.capture_limit = config.capture_window

    return config

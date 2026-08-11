"""Broadlink device handling: discovery, authentication and front-end access."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import partial
from typing import Any

import broadlink
from broadlink.exceptions import AuthorizationError, BroadlinkException

from .config import DeviceConfig
from .const import IR_DEVICE_TYPES

_LOGGER = logging.getLogger(__name__)


def format_mac(mac: bytes) -> str:
    """Return a MAC address as a colon-separated lowercase string."""
    return ":".join(format(octet, "02x") for octet in mac)


def device_slug(mac: bytes) -> str:
    """Return a topic- and entity-safe identifier for a device."""
    return "".join(format(octet, "02x") for octet in mac)


class FrontEnd:
    """Serializes access to the IR front end of a device.

    The device can either transmit or be armed for learning, never both, and an
    armed learning session is invalidated by anything else using the front end.
    Callers that transmit take :meth:`exclusive`; the receiver loop, which keeps
    the device armed, watches :attr:`generation` to notice its session is gone.

    Ported from ``BroadlinkFrontEnd`` in home-assistant/core#177767.
    """

    def __init__(self) -> None:
        """Initialize the front end."""
        self.lock = asyncio.Lock()
        self.generation = 0

    @asynccontextmanager
    async def exclusive(self) -> AsyncIterator[None]:
        """Hold the front end, invalidating any armed learning session."""
        async with self.lock:
            self.generation += 1
            yield


class BroadlinkDevice:
    """An authenticated Broadlink device."""

    def __init__(self, api: broadlink.Device, name: str | None = None) -> None:
        """Initialize the device."""
        self.api = api
        self.front_end = FrontEnd()
        self.slug = device_slug(api.mac)
        self.mac = format_mac(api.mac)
        self.name = name or f"{api.model or api.type} {self.mac[-5:].replace(':', '')}"
        self.available = True

    @property
    def host(self) -> str:
        """Return the device's IP address."""
        return str(self.api.host[0])

    @property
    def supports_sensors(self) -> bool:
        """Return True if the device exposes temperature/humidity sensors."""
        return hasattr(self.api, "check_sensors")

    async def async_auth(self) -> None:
        """Authenticate with the device."""
        await asyncio.to_thread(self.api.auth)

    async def async_request(self, func: Callable[..., Any], *args: Any) -> Any:
        """Send a request to the device, re-authenticating once if rejected.

        python-broadlink is synchronous, so every call is handed to a worker
        thread. Authorization is lost whenever the device reboots or another
        client takes it over, and the only recovery is a fresh ``auth()``.
        """
        try:
            return await asyncio.to_thread(func, *args)
        except AuthorizationError:
            _LOGGER.debug("%s: authorization lost, re-authenticating", self.name)
            await self.async_auth()
            return await asyncio.to_thread(func, *args)


async def _setup(api: broadlink.Device, name: str | None) -> BroadlinkDevice | None:
    """Authenticate a discovered device and wrap it."""
    if api.type not in IR_DEVICE_TYPES:
        _LOGGER.debug("Ignoring %s at %s: no IR front end", api.type, api.host[0])
        return None

    device = BroadlinkDevice(api, name)
    try:
        await device.async_auth()
    except (BroadlinkException, OSError) as err:
        _LOGGER.error("Could not authenticate with %s: %s", device.host, err)
        return None

    _LOGGER.info(
        "Found %s (%s) at %s [%s]", device.name, api.type, device.host, device.mac
    )
    return device


async def async_find_devices(
    configured: list[DeviceConfig],
    auto_discover: bool,
    timeout: int,
) -> list[BroadlinkDevice]:
    """Return every usable device, from the configured list and the network."""
    devices: dict[str, BroadlinkDevice] = {}

    for entry in configured:
        try:
            api = await asyncio.to_thread(
                partial(broadlink.hello, entry.host, timeout=timeout)
            )
        except (BroadlinkException, OSError) as err:
            _LOGGER.error("No Broadlink device at %s: %s", entry.host, err)
            continue
        if device := await _setup(api, entry.name):
            devices[device.slug] = device

    if auto_discover:
        try:
            found = await asyncio.to_thread(
                partial(broadlink.discover, timeout=timeout)
            )
        except (BroadlinkException, OSError) as err:
            _LOGGER.error("Network discovery failed: %s", err)
            found = []

        for api in found:
            if device_slug(api.mac) in devices:
                continue
            if device := await _setup(api, None):
                devices[device.slug] = device

    return list(devices.values())

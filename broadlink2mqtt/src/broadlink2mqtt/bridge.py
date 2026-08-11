"""The bridge: Broadlink devices on one side, MQTT on the other."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import ssl
from dataclasses import dataclass, field
from typing import Any

import aiomqtt
from broadlink.exceptions import BroadlinkException

from .codec import timings_to_packet
from .config import Config
from .const import (
    DEFAULT_MODULATION,
    PAYLOAD_OFF,
    PAYLOAD_OFFLINE,
    PAYLOAD_ON,
    PAYLOAD_ONLINE,
    SENSOR_INTERVAL,
)
from .device import BroadlinkDevice, async_find_devices
from .discovery import Topics, build_entities
from .receiver import CaptureWindow

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY = 5.0


@dataclass(slots=True)
class DeviceRuntime:
    """Everything the bridge tracks for one device."""

    device: BroadlinkDevice
    topics: Topics
    window: CaptureWindow
    available: bool = True
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


class Bridge:
    """Connects Broadlink devices to Home Assistant over MQTT."""

    def __init__(self, config: Config) -> None:
        """Initialize the bridge."""
        self._config = config
        self._runtimes: dict[str, DeviceRuntime] = {}
        self._handlers: dict[str, Any] = {}
        self._client: aiomqtt.Client | None = None
        self._shutdown = asyncio.Event()

    # -- lifecycle ---------------------------------------------------------

    async def async_setup(self) -> None:
        """Find and authenticate devices."""
        config = self._config
        devices = await async_find_devices(
            config.devices, config.auto_discover, config.discovery_timeout
        )
        if not devices:
            raise RuntimeError(
                "No Broadlink devices found. Add them under 'devices' in the "
                "add-on options, and make sure the add-on is on the same network "
                "as the device (host networking must stay enabled)."
            )

        for device in devices:
            topics = Topics.build(config.base_topic, device.slug)
            runtime = DeviceRuntime(
                device=device,
                topics=topics,
                window=CaptureWindow(
                    device,
                    on_signal=self._make_signal_callback(device.slug),
                    on_state=self._make_state_callback(device.slug),
                    on_health=self._make_health_callback(device.slug),
                    window=config.capture_window,
                    limit=config.capture_limit,
                    poll_interval=config.poll_interval,
                    rearm_interval=config.rearm_interval,
                    always_listen=config.always_listen,
                ),
            )
            self._runtimes[device.slug] = runtime
            self._handlers[topics.emitter_command] = self._make_emit_handler(
                device.slug
            )
            self._handlers[topics.learn_command] = self._make_learn_handler(device.slug)

        self._handlers[f"{config.discovery_prefix}/status"] = self._handle_ha_status

    async def async_run(self) -> None:
        """Serve until shutdown, reconnecting to the broker as needed."""
        config = self._config
        tls_context = ssl.create_default_context() if config.mqtt_ssl else None

        while not self._shutdown.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=config.mqtt_host,
                    port=config.mqtt_port,
                    username=config.mqtt_username or None,
                    password=config.mqtt_password or None,
                    tls_context=tls_context,
                    identifier=f"broadlink2mqtt-{config.base_topic}",
                    will=aiomqtt.Will(
                        topic=config.status_topic,
                        payload=PAYLOAD_OFFLINE,
                        qos=1,
                        retain=True,
                    ),
                ) as client:
                    self._client = client
                    _LOGGER.info(
                        "Connected to MQTT at %s:%s", config.mqtt_host, config.mqtt_port
                    )
                    await self._async_announce()
                    await self._async_start_device_tasks()

                    for topic in self._handlers:
                        await client.subscribe(topic, qos=1)

                    async for message in client.messages:
                        await self._async_dispatch(message)

            except aiomqtt.MqttError as err:
                self._client = None
                await self._async_stop_device_tasks()
                if self._shutdown.is_set():
                    break
                _LOGGER.warning(
                    "MQTT connection lost (%s); reconnecting in %.0fs",
                    err,
                    RECONNECT_DELAY,
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._shutdown.wait(), RECONNECT_DELAY)

    async def async_shutdown(self) -> None:
        """Close capture windows and mark everything offline."""
        _LOGGER.info("Shutting down")
        self._shutdown.set()

        for runtime in self._runtimes.values():
            with contextlib.suppress(Exception):
                await runtime.window.async_shutdown()

        await self._async_stop_device_tasks()

        if self._client is not None:
            with contextlib.suppress(aiomqtt.MqttError):
                await self._publish(
                    self._config.status_topic, PAYLOAD_OFFLINE, retain=True
                )

    # -- MQTT plumbing -----------------------------------------------------

    async def _publish(
        self, topic: str, payload: str, *, retain: bool = False, qos: int = 1
    ) -> None:
        """Publish, ignoring the call if the broker is not connected."""
        if self._client is None:
            return
        await self._client.publish(topic, payload, qos=qos, retain=retain)

    async def _async_announce(self) -> None:
        """Publish discovery configs and mark the bridge online."""
        config = self._config
        await self._publish(config.status_topic, PAYLOAD_ONLINE, retain=True)

        for runtime in self._runtimes.values():
            entities = build_entities(
                runtime.device,
                runtime.topics,
                config.status_topic,
                config.discovery_prefix,
                include_sensors=config.publish_sensors,
            )
            for topic, payload in entities:
                await self._publish(topic, json.dumps(payload), retain=True)

            await self._publish(
                runtime.topics.availability,
                PAYLOAD_ONLINE if runtime.available else PAYLOAD_OFFLINE,
                retain=True,
            )
            await self._publish(
                runtime.topics.learn_state,
                PAYLOAD_ON if runtime.window.is_open else PAYLOAD_OFF,
                retain=True,
            )
            await self._publish(
                runtime.topics.health_state,
                json.dumps(
                    runtime.window.health.as_dict()
                    | {"status": runtime.window.health.status}
                ),
                retain=True,
            )
            _LOGGER.info(
                "Announced %d entities for %s", len(entities), runtime.device.name
            )

    async def _async_dispatch(self, message: aiomqtt.Message) -> None:
        """Route an incoming message to its handler."""
        handler = self._handlers.get(str(message.topic))
        if handler is None:
            return

        payload = message.payload
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8", errors="replace")

        try:
            await handler(str(payload))
        except Exception:
            _LOGGER.exception("Error handling a message on %s", message.topic)

    # -- device tasks ------------------------------------------------------

    async def _async_start_device_tasks(self) -> None:
        """Start the sensor poll, and continuous listening where enabled."""
        for runtime in self._runtimes.values():
            # Continuous listening starts with the bridge rather than waiting
            # for the switch, so a remote press syncs Home Assistant from boot.
            if runtime.window.always_listen and not runtime.window.is_open:
                await runtime.window.async_open()

            if (
                self._config.publish_sensors
                and runtime.device.supports_sensors
                and not runtime.tasks
            ):
                runtime.tasks.append(
                    asyncio.create_task(
                        self._async_poll_sensors(runtime),
                        name=f"{runtime.device.slug} sensors",
                    )
                )

    async def _async_stop_device_tasks(self) -> None:
        """Cancel the periodic tasks."""
        for runtime in self._runtimes.values():
            for task in runtime.tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            runtime.tasks.clear()

    async def _async_poll_sensors(self, runtime: DeviceRuntime) -> None:
        """Publish temperature/humidity, and use it as a reachability check."""
        device = runtime.device
        while not self._shutdown.is_set():
            try:
                async with device.front_end.lock:
                    readings = await device.async_request(device.api.check_sensors)
            except (BroadlinkException, OSError) as err:
                _LOGGER.debug("%s: sensor poll failed: %s", device.name, err)
                await self._async_set_available(runtime, False)
            else:
                await self._async_set_available(runtime, True)
                await self._publish(
                    runtime.topics.sensor_state, json.dumps(readings), retain=True
                )

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._shutdown.wait(), SENSOR_INTERVAL)

    async def _async_set_available(
        self, runtime: DeviceRuntime, available: bool
    ) -> None:
        """Publish a change in device reachability."""
        if runtime.available == available:
            return
        runtime.available = available
        _LOGGER.info(
            "%s is %s",
            runtime.device.name,
            "back online" if available else "unreachable",
        )
        await self._publish(
            runtime.topics.availability,
            PAYLOAD_ONLINE if available else PAYLOAD_OFFLINE,
            retain=True,
        )

    # -- handlers ----------------------------------------------------------

    def _make_emit_handler(self, slug: str):
        """Return the handler for a device's emitter command topic."""

        async def handler(payload: str) -> None:
            runtime = self._runtimes[slug]
            device = runtime.device

            try:
                data = json.loads(payload)
                timings = [int(t) for t in data["timings"]]
                repeat = int(data.get("repeat_count") or 0)
            except (ValueError, KeyError, TypeError) as err:
                _LOGGER.error(
                    "%s: bad emitter payload (%s): %s", device.name, err, payload
                )
                return

            try:
                packet = timings_to_packet(timings, repeat)
            except ValueError as err:
                _LOGGER.error("%s: could not encode the signal: %s", device.name, err)
                return

            try:
                async with device.front_end.exclusive():
                    await device.async_request(device.api.send_data, packet)
            except (BroadlinkException, OSError) as err:
                _LOGGER.error("%s: failed to send the signal: %s", device.name, err)
                await self._async_set_available(runtime, False)
                return

            await self._async_set_available(runtime, True)
            _LOGGER.debug(
                "%s: sent %d edges, repeat=%d", device.name, len(timings), repeat
            )

        return handler

    def _make_learn_handler(self, slug: str):
        """Return the handler for a device's learning-mode switch."""

        async def handler(payload: str) -> None:
            runtime = self._runtimes[slug]
            if payload.strip().upper() == PAYLOAD_ON:
                await runtime.window.async_open()
            else:
                await runtime.window.async_close()

        return handler

    def _make_signal_callback(self, slug: str):
        """Return the callback that publishes a captured signal."""

        async def callback(timings: list[int], packet: bytes) -> None:
            topics = self._runtimes[slug].topics
            await self._publish(
                topics.receiver_state,
                json.dumps({"timings": timings, "modulation": DEFAULT_MODULATION}),
            )

            code = base64.b64encode(packet).decode("ascii")
            await self._publish(
                topics.code_state,
                json.dumps(
                    {
                        # The sensor state column is capped at 255 characters,
                        # so the full code travels as an attribute.
                        "short": f"{code[:32]}…" if len(code) > 32 else code,
                        "base64": code,
                        "timings": timings,
                        "modulation": DEFAULT_MODULATION,
                    }
                ),
                retain=True,
            )

        return callback

    def _make_health_callback(self, slug: str):
        """Return the callback that publishes receiver health."""

        async def callback() -> None:
            runtime = self._runtimes[slug]
            health = runtime.window.health
            await self._publish(
                runtime.topics.health_state,
                json.dumps(health.as_dict() | {"status": health.status}),
                retain=True,
            )
            # A receiver the watchdog has given up on should read as
            # unavailable, not as silently working.
            if health.degraded and runtime.available:
                await self._async_set_available(runtime, False)
            elif not health.degraded and not runtime.available:
                await self._async_set_available(runtime, True)

        return callback

    def _make_state_callback(self, slug: str):
        """Return the callback that publishes the learning-mode switch state."""

        async def callback(is_open: bool) -> None:
            await self._publish(
                self._runtimes[slug].topics.learn_state,
                PAYLOAD_ON if is_open else PAYLOAD_OFF,
                retain=True,
            )

        return callback

    async def _handle_ha_status(self, payload: str) -> None:
        """Re-announce when Home Assistant restarts."""
        if payload.strip().lower() == PAYLOAD_ONLINE:
            _LOGGER.info("Home Assistant came back online; re-announcing")
            await self._async_announce()

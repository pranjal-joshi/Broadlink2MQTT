"""IR capture: bounded windows, or continuous listening.

A Broadlink RM cannot listen passively. It has to be put into learning mode and
polled, which lights its LED and monopolises the IR front end.

The bounded-window state machine is ported from
``BroadlinkInfraredReceiverEntity`` in home-assistant/core#177767, which was
closed because Home Assistant's receiver entity expects a device that is always
listening. Outside of core, where the window is driven by a switch the user
controls, the same logic is fine.

``always_listen`` opts into never closing that window, so a remote press keeps
Home Assistant in sync. Measured on an RM4 mini this is cheap — 46 ms median
per poll, no errors over 90 s — but it is best-effort, not reliable: the device
cannot transmit and listen at once, and it is deaf for a moment after every
capture and every transmission. The health counters exist so that unreliability
is visible in Home Assistant rather than inferred at midnight.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from broadlink.exceptions import BroadlinkException, ReadError, StorageError

from .codec import is_plausible_ir, packet_to_timings
from .const import (
    DEDUPE_INTERVAL,
    DEGRADED_AFTER_ERRORS,
    DEGRADED_BACKOFF,
    ERROR_BACKOFF,
    TRANSMIT_COOLDOWN,
)
from .device import BroadlinkDevice

_LOGGER = logging.getLogger(__name__)

SignalCallback = Callable[[list[int], bytes], Awaitable[None]]
StateCallback = Callable[[bool], Awaitable[None]]
HealthCallback = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class CaptureHealth:
    """What the receiver has actually been doing.

    Published as a diagnostic entity: continuous listening is best-effort, and
    a user debugging a flaky automation needs to see the noise and error rates
    rather than guess at them.
    """

    listening: bool = False
    captures: int = 0
    noise_discarded: int = 0
    duplicates_suppressed: int = 0
    errors: int = 0
    consecutive_errors: int = 0
    degraded: bool = False
    last_capture: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable snapshot."""
        return asdict(self)

    @property
    def status(self) -> str:
        """A one-word summary for the entity state."""
        if self.degraded:
            return "degraded"
        return "listening" if self.listening else "idle"


class CaptureWindow:
    """Holds a device in learning mode and reports what it hears."""

    def __init__(
        self,
        device: BroadlinkDevice,
        on_signal: SignalCallback,
        on_state: StateCallback,
        *,
        window: float,
        limit: float,
        poll_interval: float,
        rearm_interval: float,
        always_listen: bool = False,
        on_health: HealthCallback | None = None,
    ) -> None:
        """Initialize the capture window."""
        self._device = device
        self._on_signal = on_signal
        self._on_state = on_state
        self._on_health = on_health
        self._window = window
        self._limit = limit
        self._poll_interval = poll_interval
        self._rearm_interval = rearm_interval
        self._always_listen = always_listen

        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._ends_at: float | None = None
        self._hard_limit = 0.0
        self._suspended = False

        self._last_packet: bytes | None = None
        self._last_packet_at = 0.0

        self.health = CaptureHealth()

    @property
    def always_listen(self) -> bool:
        """Return True when this receiver never closes its window."""
        return self._always_listen

    @property
    def is_open(self) -> bool:
        """Return True while the receiver should be listening."""
        if self._stop.is_set():
            return False
        if self._always_listen:
            return not self._suspended
        return self._ends_at is not None and time.monotonic() < self._ends_at

    async def async_open(self) -> None:
        """Start listening, or restart a bounded window that is already open."""
        self._suspended = False
        if not self._always_listen:
            now = time.monotonic()
            self._hard_limit = now + self._limit
            self._ends_at = now + self._window

        self._ensure_task()
        await self._async_set_listening(True)

    async def async_close(self) -> None:
        """Stop listening.

        In continuous mode this is a user override that holds until the switch
        is turned back on — the device stops listening rather than the window
        simply expiring.
        """
        self._suspended = True
        self._ends_at = None

    async def async_shutdown(self) -> None:
        """Stop listening and wait for the device request in flight to finish.

        Cancelling would release the front end while a request is still running
        in its worker thread, leaving a transmit free to talk over it.
        """
        self._stop.set()
        self._ends_at = None
        if self._task is not None:
            await self._task

    def _ensure_task(self) -> None:
        """Start the listen loop if it is not already running."""
        if self._task is None and not self._stop.is_set():
            self._task = asyncio.create_task(
                self._async_listen(), name=f"{self._device.slug} ir receiver"
            )
            _LOGGER.info(
                "%s: listening for IR codes%s",
                self._device.name,
                " (continuous)" if self._always_listen else "",
            )

    def _extend(self) -> None:
        """Keep a bounded window open while codes keep arriving."""
        if not self._always_listen:
            self._ends_at = min(time.monotonic() + self._window, self._hard_limit)

    async def _idle(self, delay: float) -> None:
        """Wait between polls, returning early on shutdown."""
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), delay)

    async def _async_set_listening(self, listening: bool) -> None:
        """Publish a change in listening state."""
        self.health.listening = listening
        await self._on_state(listening)
        await self._async_publish_health()

    async def _async_publish_health(self) -> None:
        """Push the health snapshot out, if anyone is listening for it."""
        if self._on_health is not None:
            await self._on_health()

    async def _async_record_error(self, err: Exception) -> None:
        """Count a device failure and trip the watchdog if they keep coming."""
        health = self.health
        health.errors += 1
        health.consecutive_errors += 1
        _LOGGER.debug("%s: failed to listen for IR: %s", self._device.name, err)

        if not health.degraded and health.consecutive_errors >= DEGRADED_AFTER_ERRORS:
            health.degraded = True
            _LOGGER.warning(
                "%s: %d consecutive failures while listening; backing off to "
                "%.0fs and reporting unavailable until it recovers",
                self._device.name,
                health.consecutive_errors,
                DEGRADED_BACKOFF,
            )
        await self._async_publish_health()

    async def _async_clear_errors(self) -> None:
        """A poll succeeded; forget the error streak."""
        health = self.health
        recovered = health.degraded
        health.consecutive_errors = 0
        health.degraded = False
        if recovered:
            _LOGGER.info("%s: receiver recovered", self._device.name)
        await self._async_publish_health()

    async def _async_listen(self) -> None:
        """Capture IR signals until the receiver is closed.

        A capture is only readable while the learning session that recorded it
        is still valid, so the session is renewed after every capture, whenever
        a transmission invalidated it, and before the device times it out.
        """
        device = self._device
        front_end = device.front_end
        armed_generation: int | None = None
        armed_until = 0.0

        while self.is_open and not self._stop.is_set():
            if (
                armed_generation is not None
                and armed_generation != front_end.generation
            ):
                # Let the repeat frames of the transmission that invalidated our
                # session pass, so we do not capture our own output.
                await asyncio.sleep(TRANSMIT_COOLDOWN)

            packet: bytes | None = None
            try:
                async with front_end.lock:
                    # Read before arming. enter_learning() discards whatever the
                    # device is holding, so arming first would throw away a code
                    # that arrived in the moment before a scheduled renewal.
                    if armed_generation == front_end.generation:
                        try:
                            packet = await device.async_request(device.api.check_data)
                        except (ReadError, StorageError):
                            packet = None

                    if (
                        armed_generation != front_end.generation
                        or armed_until <= time.monotonic()
                        or packet is not None
                    ):
                        await device.async_request(device.api.enter_learning)
                        armed_generation = front_end.generation
                        armed_until = time.monotonic() + self._rearm_interval

            except (BroadlinkException, OSError) as err:
                armed_generation = None
                await self._async_record_error(err)
                await self._idle(
                    DEGRADED_BACKOFF if self.health.degraded else ERROR_BACKOFF
                )
                continue

            if self.health.consecutive_errors:
                await self._async_clear_errors()

            if packet is not None:
                await self._async_handle_packet(packet)

            await self._idle(self._poll_interval)

        self._ends_at = None
        self._task = None
        _LOGGER.info("%s: stopped listening for IR codes", device.name)
        await self._async_set_listening(False)

    async def _async_handle_packet(self, packet: bytes) -> None:
        """Decode a captured packet, screen it, and report it."""
        name = self._device.name
        now = time.monotonic()

        if packet == self._last_packet and now - self._last_packet_at < DEDUPE_INTERVAL:
            self.health.duplicates_suppressed += 1
            self._last_packet_at = now
            self._extend()
            return

        try:
            timings = packet_to_timings(packet)
        except ValueError as err:
            _LOGGER.debug("%s: discarding packet: %s", name, err)
            return

        if not is_plausible_ir(timings):
            # Ambient interference, not a remote. Counted rather than silently
            # dropped, because a high rate is the thing worth acting on.
            self.health.noise_discarded += 1
            _LOGGER.debug(
                "%s: discarding a capture that is not a plausible IR frame "
                "(%d edges); likely ambient interference",
                name,
                len(timings),
            )
            await self._async_publish_health()
            return

        self._last_packet = packet
        self._last_packet_at = now
        self.health.captures += 1
        self.health.last_capture = datetime.now(UTC).isoformat(timespec="milliseconds")

        self._extend()
        _LOGGER.info("%s: captured an IR code (%d edges)", name, len(timings))
        await self._on_signal(timings, packet)
        await self._async_publish_health()

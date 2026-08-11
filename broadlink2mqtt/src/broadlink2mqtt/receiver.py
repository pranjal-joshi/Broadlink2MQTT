"""Bounded IR capture windows.

A Broadlink RM cannot listen passively. It has to be put into learning mode and
polled, which lights its LED and monopolises the IR front end, so it only
listens during a capture window that someone explicitly opens.

The state machine here is ported from ``BroadlinkInfraredReceiverEntity`` in
home-assistant/core#177767, which was closed because Home Assistant's receiver
entity expects a device that is always listening. Outside of core, where the
window can be driven by a switch the user controls, the same logic is fine.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from broadlink.exceptions import BroadlinkException, ReadError, StorageError

from .codec import packet_to_timings
from .const import ERROR_BACKOFF, TRANSMIT_COOLDOWN
from .device import BroadlinkDevice

_LOGGER = logging.getLogger(__name__)

SignalCallback = Callable[[list[int], bytes], Awaitable[None]]
StateCallback = Callable[[bool], Awaitable[None]]


class CaptureWindow:
    """Holds a device in learning mode for a bounded window."""

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
    ) -> None:
        """Initialize the capture window."""
        self._device = device
        self._on_signal = on_signal
        self._on_state = on_state
        self._window = window
        self._limit = limit
        self._poll_interval = poll_interval
        self._rearm_interval = rearm_interval

        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._ends_at: float | None = None
        self._hard_limit = 0.0

    @property
    def is_open(self) -> bool:
        """Return True while the window has time left on it."""
        return self._ends_at is not None and time.monotonic() < self._ends_at

    async def async_open(self) -> None:
        """Open a capture window, or start it over if one is already open."""
        now = time.monotonic()
        self._hard_limit = now + self._limit
        self._ends_at = now + self._window

        if self._task is None and not self._stop.is_set():
            self._task = asyncio.create_task(
                self._async_listen(), name=f"{self._device.slug} ir receiver"
            )
            _LOGGER.info("%s: listening for IR codes", self._device.name)

        await self._on_state(True)

    async def async_close(self) -> None:
        """Ask the window to close; the listener finishes its current poll."""
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

    def _extend(self) -> None:
        """Keep the window open while codes keep arriving, up to the limit."""
        self._ends_at = min(time.monotonic() + self._window, self._hard_limit)

    async def _idle(self, delay: float) -> None:
        """Wait between polls, returning early on shutdown."""
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), delay)

    async def _async_listen(self) -> None:
        """Capture IR signals until the window closes.

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
                    if (
                        armed_generation != front_end.generation
                        or armed_until <= time.monotonic()
                    ):
                        await device.async_request(device.api.enter_learning)
                        armed_generation = front_end.generation
                        armed_until = time.monotonic() + self._rearm_interval

                    try:
                        packet = await device.async_request(device.api.check_data)
                    except (ReadError, StorageError):
                        packet = None

            except (BroadlinkException, OSError) as err:
                _LOGGER.debug("%s: failed to listen for IR: %s", device.name, err)
                armed_generation = None
                await self._idle(ERROR_BACKOFF)
                continue

            if packet is not None:
                armed_generation = None
                await self._async_handle_packet(packet)

            await self._idle(self._poll_interval)

        self._ends_at = None
        self._task = None
        _LOGGER.info("%s: stopped listening for IR codes", device.name)
        await self._on_state(False)

    async def _async_handle_packet(self, packet: bytes) -> None:
        """Decode a captured packet and report it."""
        try:
            timings = packet_to_timings(packet)
        except ValueError as err:
            _LOGGER.debug("%s: discarding packet: %s", self._device.name, err)
            return

        self._extend()
        _LOGGER.info(
            "%s: captured an IR code (%d edges)", self._device.name, len(timings)
        )
        await self._on_signal(timings, packet)

"""Tests for the capture state machine, against a fake device.

These cover the behaviour that used to be provable only with hardware in hand:
the read-before-arm ordering, the noise guard, dedupe, the watchdog, and that
continuous listening does not close on its own.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from broadlink.exceptions import ReadError
from broadlink2mqtt.codec import timings_to_packet
from broadlink2mqtt.const import DEGRADED_AFTER_ERRORS
from broadlink2mqtt.device import FrontEnd
from broadlink2mqtt.receiver import CaptureWindow

from tests.test_plausibility import AMBIENT_NOISE, nec

GOOD = timings_to_packet(nec(0x04, 0x08))
OTHER = timings_to_packet(nec(0x04, 0x02))
NOISE = timings_to_packet(AMBIENT_NOISE)


class FakeApi:
    """Stands in for a python-broadlink device."""

    def __init__(self, script: list[Any]) -> None:
        # Each entry is a packet to return, None for "nothing captured",
        # or an Exception instance to raise.
        self.script = list(script)
        self.calls: list[str] = []

    def enter_learning(self) -> None:
        self.calls.append("arm")

    def check_data(self) -> bytes:
        self.calls.append("read")
        item = self.script.pop(0) if self.script else None
        if isinstance(item, Exception):
            raise item
        if item is None:
            raise ReadError(-4)
        return item


class FakeDevice:
    """The subset of BroadlinkDevice that CaptureWindow touches."""

    def __init__(self, script: list[Any]) -> None:
        self.api = FakeApi(script)
        self.front_end = FrontEnd()
        self.name = "Fake RM"
        self.slug = "fake"

    async def async_request(self, func: Any, *args: Any) -> Any:
        return func(*args)


def build(device: FakeDevice, **kwargs: Any) -> tuple[CaptureWindow, list, list]:
    """Return a window plus the lists its callbacks append to."""
    signals: list[tuple[list[int], bytes]] = []
    states: list[bool] = []

    async def on_signal(timings: list[int], packet: bytes) -> None:
        signals.append((timings, packet))

    async def on_state(listening: bool) -> None:
        states.append(listening)

    options: dict[str, Any] = {
        "window": 0.3,
        "limit": 5.0,
        "poll_interval": 0.01,
        "rearm_interval": 60.0,
    }
    options.update(kwargs)
    return CaptureWindow(device, on_signal, on_state, **options), signals, states


async def run_briefly(window: CaptureWindow, seconds: float = 0.25) -> None:
    """Open the window, let the loop turn, then shut it down."""
    await window.async_open()
    await asyncio.sleep(seconds)
    await window.async_shutdown()


async def test_publishes_a_plausible_capture() -> None:
    device = FakeDevice([None, GOOD])
    window, signals, _ = build(device)
    await run_briefly(window)

    assert len(signals) == 1
    assert signals[0][1] == GOOD
    assert window.health.captures == 1
    assert window.health.noise_discarded == 0


async def test_discards_ambient_noise_without_publishing() -> None:
    device = FakeDevice([None, NOISE, NOISE])
    window, signals, _ = build(device)
    await run_briefly(window)

    assert signals == []
    assert window.health.noise_discarded >= 1
    assert window.health.captures == 0


async def test_suppresses_a_repeated_capture() -> None:
    device = FakeDevice([None, GOOD, GOOD, GOOD])
    window, signals, _ = build(device)
    await run_briefly(window)

    assert len(signals) == 1, "identical packets within a second must collapse"
    assert window.health.duplicates_suppressed >= 1


async def test_a_different_code_is_not_suppressed() -> None:
    device = FakeDevice([None, GOOD, OTHER])
    window, signals, _ = build(device)
    await run_briefly(window)

    assert [s[1] for s in signals] == [GOOD, OTHER]


class BufferingFakeApi(FakeApi):
    """A fake that models the one behaviour the ordering depends on.

    A real device holds a capture until it is read, and ``enter_learning()``
    throws that buffer away. Without modelling that discard the two orderings
    are indistinguishable — which is how the bug survived being ported.
    """

    def __init__(self) -> None:
        super().__init__([])
        self.pending: bytes | None = None

    def enter_learning(self) -> None:
        self.calls.append("arm")
        self.pending = None  # arming discards whatever the device was holding

    def check_data(self) -> bytes:
        self.calls.append("read")
        held, self.pending = self.pending, None
        if held is None:
            raise ReadError(-4)
        return held


async def test_a_press_landing_between_polls_is_not_discarded() -> None:
    """The read must come first, or a scheduled renewal eats the capture.

    The press is scheduled in the gap *between* two passes, and
    ``rearm_interval=0`` makes the next pass a renewal. Reading first delivers
    it; arming first wipes the buffer before the read ever runs.

    Timing matters here: within a single pass both orderings issue one read and
    one arm, so only a capture arriving between passes tells them apart.
    """
    device = FakeDevice([])
    device.api = BufferingFakeApi()
    window, signals, _ = build(device, rearm_interval=0.0, poll_interval=0.05)

    async def press_between_polls() -> None:
        await asyncio.sleep(0.03)  # after pass one, before pass two
        device.api.pending = GOOD

    await window.async_open()
    await press_between_polls()
    await asyncio.sleep(0.2)
    await window.async_shutdown()

    assert [s[1] for s in signals] == [GOOD], (
        f"a re-arm discarded the capture; calls: {device.api.calls}"
    )


async def test_watchdog_trips_after_consecutive_failures() -> None:
    """Tested directly: the loop backs off 5s per error, far longer than a test.

    Five failures in a row must mark the receiver degraded, and one success
    must clear it.
    """
    device = FakeDevice([])
    window, _, _ = build(device)

    for _ in range(DEGRADED_AFTER_ERRORS - 1):
        await window._async_record_error(OSError("boom"))
    assert window.health.degraded is False, "tripped too early"

    await window._async_record_error(OSError("boom"))
    assert window.health.degraded is True
    assert window.health.consecutive_errors == DEGRADED_AFTER_ERRORS
    assert window.health.status == "degraded"

    await window._async_clear_errors()
    assert window.health.degraded is False
    assert window.health.consecutive_errors == 0
    assert window.health.errors == DEGRADED_AFTER_ERRORS, "the total must not reset"


async def test_continuous_listening_does_not_close_itself() -> None:
    device = FakeDevice([])
    window, _, _ = build(device, window=0.05, always_listen=True)
    await window.async_open()
    await asyncio.sleep(0.3)  # far beyond the bounded window
    still_open = window.is_open
    await window.async_shutdown()

    assert still_open is True
    assert window.always_listen is True


async def test_a_bounded_window_closes_on_its_own() -> None:
    device = FakeDevice([])
    window, _, states = build(device, window=0.08, poll_interval=0.01)
    await window.async_open()
    await asyncio.sleep(0.4)
    open_after = window.is_open
    await window.async_shutdown()

    assert open_after is False
    assert states[0] is True
    assert states[-1] is False


async def test_the_switch_suspends_continuous_listening() -> None:
    device = FakeDevice([])
    window, _, _ = build(device, always_listen=True, poll_interval=0.01)
    await window.async_open()
    await asyncio.sleep(0.05)
    await window.async_close()
    await asyncio.sleep(0.1)
    suspended = window.is_open
    await window.async_shutdown()

    assert suspended is False


@pytest.mark.parametrize("always", [False, True])
async def test_health_reports_listening_state(always: bool) -> None:
    device = FakeDevice([])
    published: list[str] = []

    async def on_health() -> None:
        published.append(window.health.status)

    window, _, _ = build(device, always_listen=always, on_health=on_health)
    await window.async_open()
    assert window.health.listening is True
    await asyncio.sleep(0.05)
    await window.async_shutdown()

    assert "listening" in published

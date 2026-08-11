"""Conversion between Home Assistant IR timings and Broadlink packets.

Home Assistant's infrared entities speak signed microsecond timings: positive
values are carrier-on (a pulse), negative values are carrier-off (a space).
Broadlink devices speak their own packet format, documented in ``const``.

The arithmetic itself already lives upstream in ``broadlink.remote`` as
``pulses_to_data`` / ``data_to_pulses``; this module only bridges the two
conventions and fills in the one field the upstream encoder leaves blank.
"""

from __future__ import annotations

from collections.abc import Sequence

from broadlink.remote import data_to_pulses, pulses_to_data

from .const import HEADER_LEN, IR_PACKET_TYPE, MAX_REPEAT, REPEAT_BYTE


def timings_to_packet(timings: Sequence[int], repeat_count: int = 0) -> bytes:
    """Encode signed microsecond timings into a Broadlink IR packet.

    ``pulses_to_data`` takes unsigned durations, so the sign convention is
    dropped here: the alternation is positional, and the device infers it.

    It also never writes byte 1, leaving the repeat count at zero, so the
    caller's ``repeat_count`` is patched in afterwards.
    """
    if not timings:
        raise ValueError("timings must not be empty")
    if not 0 <= repeat_count <= MAX_REPEAT:
        raise ValueError(f"repeat_count must be 0-{MAX_REPEAT}, got {repeat_count}")

    packet = bytearray(pulses_to_data([abs(timing) for timing in timings]))
    packet[REPEAT_BYTE] = repeat_count
    return bytes(packet)


def packet_to_timings(packet: bytes) -> list[int]:
    """Decode a Broadlink IR packet into signed microsecond timings.

    The device reports alternating durations starting with a pulse, while
    Home Assistant expects pulses positive and spaces negative.

    Raises ValueError for RF packets (type 0xb2/0xd7) and malformed data, so
    a device that was left in RF learning mode cannot leak a bogus IR signal.
    """
    if len(packet) < HEADER_LEN:
        raise ValueError(f"packet too short: {len(packet)} bytes")
    if packet[0] != IR_PACKET_TYPE:
        raise ValueError(f"not an IR packet: type 0x{packet[0]:02x}")

    timings = [
        duration if index % 2 == 0 else -duration
        for index, duration in enumerate(data_to_pulses(bytes(packet)))
    ]
    if not timings:
        raise ValueError("packet contained no pulses")
    return timings

"""Tests for the IR codec."""

from __future__ import annotations

import pytest
from broadlink2mqtt.codec import packet_to_timings, timings_to_packet
from broadlink2mqtt.const import IR_PACKET_TYPE, REPEAT_BYTE

# A NEC-style header plus a few bits, in signed microseconds.
NEC_TIMINGS = [9000, -4500, 560, -560, 560, -1690, 560, -560, 560, -1690, 560]


def test_encodes_the_ir_packet_type() -> None:
    packet = timings_to_packet(NEC_TIMINGS)
    assert packet[0] == IR_PACKET_TYPE


def test_encodes_the_payload_length_little_endian() -> None:
    packet = timings_to_packet(NEC_TIMINGS)
    assert 256 * packet[3] + packet[2] == len(packet) - 4


def test_repeat_count_lands_in_byte_one() -> None:
    """pulses_to_data leaves byte 1 at zero, so the codec has to fill it in."""
    assert timings_to_packet(NEC_TIMINGS)[REPEAT_BYTE] == 0
    assert timings_to_packet(NEC_TIMINGS, repeat_count=3)[REPEAT_BYTE] == 3


def test_repeat_count_does_not_disturb_the_payload() -> None:
    plain = timings_to_packet(NEC_TIMINGS)
    repeated = timings_to_packet(NEC_TIMINGS, repeat_count=5)
    assert plain[2:] == repeated[2:]


@pytest.mark.parametrize("repeat", [-1, 256, 1000])
def test_rejects_out_of_range_repeat_counts(repeat: int) -> None:
    with pytest.raises(ValueError, match="repeat_count"):
        timings_to_packet(NEC_TIMINGS, repeat_count=repeat)


def test_rejects_empty_timings() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        timings_to_packet([])


def test_round_trip_preserves_sign_alternation() -> None:
    decoded = packet_to_timings(timings_to_packet(NEC_TIMINGS))
    assert [t > 0 for t in decoded] == [t > 0 for t in NEC_TIMINGS]


def test_round_trip_is_accurate_within_one_tick() -> None:
    """The 32.84 us tick and integer truncation lose a little on each edge."""
    decoded = packet_to_timings(timings_to_packet(NEC_TIMINGS))
    assert len(decoded) == len(NEC_TIMINGS)
    for original, result in zip(NEC_TIMINGS, decoded, strict=True):
        assert abs(abs(original) - abs(result)) <= 33


def test_long_durations_survive_the_escape_sequence() -> None:
    """Durations over 255 ticks (~8.4 ms) are encoded as 0, hi, lo."""
    timings = [60000, -30000, 500]
    decoded = packet_to_timings(timings_to_packet(timings))
    for original, result in zip(timings, decoded, strict=True):
        assert abs(abs(original) - abs(result)) <= 33


def test_rejects_rf_packets() -> None:
    """An RF capture must not be reported as an IR signal."""
    packet = bytearray(timings_to_packet(NEC_TIMINGS))
    packet[0] = 0xB2
    with pytest.raises(ValueError, match="not an IR packet"):
        packet_to_timings(bytes(packet))


def test_rejects_short_packets() -> None:
    with pytest.raises(ValueError, match="too short"):
        packet_to_timings(b"\x26\x00")


def test_rejects_a_header_with_no_pulses() -> None:
    with pytest.raises(ValueError, match="no pulses"):
        packet_to_timings(bytes([IR_PACKET_TYPE, 0, 0, 0]))

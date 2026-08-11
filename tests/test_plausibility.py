"""Tests for the ambient-interference guard.

The noise fixture is not invented: it is a real capture taken from an idle
RM4 mini, which produced roughly one of these every 18 seconds with nothing
pointed at it. Every space is an integer multiple of ~21.4 ms.
"""

from __future__ import annotations

import pytest
from broadlink2mqtt.codec import is_plausible_ir, packet_to_timings, timings_to_packet

from tests.helpers import AMBIENT_NOISE, nec


def test_rejects_real_ambient_interference() -> None:
    assert is_plausible_ir(AMBIENT_NOISE) is False


def test_accepts_a_real_nec_frame() -> None:
    assert is_plausible_ir(nec(0x04, 0x08)) is True


@pytest.mark.parametrize(
    ("address", "command"),
    [(0x04, 0x08), (0x5E, 0x1A), (0x7F, 0x51), (0x00, 0xFF)],
)
def test_accepts_nec_frames_generally(address: int, command: int) -> None:
    assert is_plausible_ir(nec(address, command)) is True


def test_accepts_a_frame_with_a_long_trailing_gap() -> None:
    """Median, not maximum: one long trailing space must not reject a frame."""
    assert is_plausible_ir([*nec(0x04, 0x08), -100_000]) is True


def test_accepts_rc5_style_timings() -> None:
    """RC5 uses 889 us marks and spaces — well inside the threshold."""
    rc5 = [889, -889, 1778, -1778, 889, -889, 889, -889, 1778, -889]
    assert is_plausible_ir(rc5) is True


def test_rejects_too_few_spaces() -> None:
    assert is_plausible_ir([560]) is False
    assert is_plausible_ir([560, -560]) is False


def test_rejects_an_empty_signal() -> None:
    assert is_plausible_ir([]) is False


def test_survives_a_codec_round_trip() -> None:
    """The guard runs on decoded packets, so it must agree after a round trip."""
    decoded = packet_to_timings(timings_to_packet(nec(0x04, 0x08)))
    assert is_plausible_ir(decoded) is True

    noisy = packet_to_timings(timings_to_packet(AMBIENT_NOISE))
    assert is_plausible_ir(noisy) is False

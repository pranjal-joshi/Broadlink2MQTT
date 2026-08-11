"""Shared signal fixtures.

Kept out of the test modules so they can be imported without one test file
depending on another.
"""

from __future__ import annotations

# A real capture taken from an idle RM4 mini, with no remote in use. The device
# produced roughly one of these every 18 seconds; every space is an integer
# multiple of ~21.4 ms, which is a periodic interference source rather than a
# protocol.
AMBIENT_NOISE = [
    328, -21641, 197, -85810, 229, -64399, 262, -42560, 656, -20919,
    164, -42954, 295, -42462, 164, -21904, 164, -107288, 164, -64333,
    229, -21214, 328, -21148, 229, -107649, 164, -109455,
]  # fmt: skip


def nec(address: int, command: int) -> list[int]:
    """Build a 32-bit NEC frame as signed microsecond timings."""
    timings = [9000, -4500]
    for byte in (address, 255 - address, command, 255 - command):
        for bit in range(8):
            timings.append(560)
            timings.append(-1690 if (byte >> bit) & 1 else -560)
    timings.append(560)
    return timings

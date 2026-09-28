#!/usr/bin/env python3
"""Write the binary fixture files used by the golden tests.

The files are small and deterministic, and they are checked in. Rerun this
after changing it: python tests/fixtures/make_fixtures.py
"""

import struct
from pathlib import Path

HERE = Path(__file__).parent


def counter() -> bytes:
    """Frames 250..259 of tgen's counter.tgen example (7-byte records, little-endian)."""
    return b"".join(
        struct.pack("<BBBI", i % 256, (i // 2) % 256, i % 4 + 1, i) for i in range(250, 260)
    )


FIXTURES = {
    "counter.bin": counter,
}


def main() -> None:
    for name, make in FIXTURES.items():
        (HERE / name).write_bytes(make())
        print(f"wrote {name}")


if __name__ == "__main__":
    main()

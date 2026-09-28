#!/usr/bin/env python3
"""Write the binary fixture files used by the golden tests.

The files are small and deterministic, and they are checked in. Rerun this
after changing it:

    python tests/fixtures/make_fixtures.py

Typed fixtures come in pairs, NAME.le.bin and NAME.be.bin, holding the same
values in little- and big-endian byte order. Every record is 16 bytes unless
noted otherwise.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

HERE = Path(__file__).parent

# --- values -------------------------------------------------------------------

INT16 = [0, 1, -1, 2, 0x7FFF, -0x8000, 0x1234, 0x00FF, -0x0100, 0x5555, -0x5556, 1000]
INT16 += [1 << k for k in range(15)] + [-(1 << 15)]  # walking ones
INT16 += [0x0F0F, 0x7F80, -12345, 31]  # pad to a multiple of 8 values

INT32 = [0, 1, -1, 2, 0x7FFFFFFF, -0x80000000, 0x03915ED3, 0x12345678, -100, 0x00FF00FF]
INT32 += [0x0000FFFF, -0x10000]
INT32 += [1 << k for k in range(31)] + [-(1 << 31)]  # walking ones
INT32 += [123456789, -987654321, 0x7F7F7F7F, 42]

F32_MAX = struct.unpack("<f", b"\xff\xff\x7f\x7f")[0]
F32_TINY = struct.unpack("<f", b"\x01\x00\x00\x00")[0]  # smallest denormal
FLOAT32 = [0.0, -0.0, 1.0, -1.5, math.pi, 0.1, 1 / 3, 1e-10, 12345678.0, -2.5e20]
FLOAT32 += [F32_MAX, 1.17549435e-38, F32_TINY, math.inf, -math.inf, math.nan]

FLOAT64 = [0.0, -0.0, 1.0, -1.5, math.pi, 0.1, 1 / 3, 1e-300, 123456789012345.0, -2.5e200]
FLOAT64 += [1.7976931348623157e308, 2.2250738585072014e-308, 5e-324, math.inf, -math.inf]
FLOAT64 += [math.nan]

# (real, imaginary) pairs at known angles and magnitudes
COMPLEX = [(1, 0), (0, 1), (-1, 0), (0, -1), (3, 4), (-3, 4), (1, 1), (0, 0)]
COMPLEX += [(0.5, -0.8660254), (-2, -2), (1e-3, 1e3), (-0.0, 0.0), (7, -24), (1.5, 2.5)]
COMPLEX += [(-1, -0.0), (100, 1)]


def pack(order: str, code: str, values) -> bytes:
    return struct.pack(f"{order}{len(values)}{code}", *values)


def complex_bytes(order: str, code: str) -> bytes:
    return pack(order, code, [x for pair in COMPLEX for x in pair])


# --- untyped fixtures ---------------------------------------------------------


def bytes256() -> bytes:
    """Every byte value, 0..255 (sixteen 16-byte records)."""
    return bytes(range(256))


def ascii_text() -> bytes:
    """Text with tabs, newlines, NULs, DEL and high bytes (32-byte records)."""
    lines = [
        b"Hello, World! pick picks bytes.\n",
        b"Tab\there\0nul\x7fdel\x1besc\x80\xff\xa0\xc3\xa9x\n",
        b"  leading spaces and a quote ' \"\n",
        b"0123456789ABCDEFGHIJ[]{}()<>?/\\\n",
    ]
    data = b"".join(line.ljust(32, b".")[:32] for line in lines)
    assert len(data) == 128
    return data


def seq() -> bytes:
    """100 8-byte records: uint32 record number, uint16 3*n, then 'AB' (little-endian)."""
    return b"".join(struct.pack("<IH2s", n, 3 * n, b"AB") for n in range(100))


def header() -> bytes:
    """A 20-byte header, ten 12-byte records, and a 5-byte partial record."""
    head = b"HEADER-20-BYTES-----"
    recs = b"".join(struct.pack("<If4s", n, n / 2, b"R%03d" % n) for n in range(10))
    return head + recs + b"PART!"


def counter() -> bytes:
    """Frames 250..259 of tgen's counter.tgen example (7-byte records, little-endian)."""
    return b"".join(
        struct.pack("<BBBI", i % 256, (i // 2) % 256, i % 4 + 1, i) for i in range(250, 260)
    )


# --- fixtures matching the bundled symbol files -------------------------------


def moc(order: str) -> bytes:
    """Four records of the 'moc' layout: 21 doubles."""
    recs = []
    for n in range(4):
        t = 1000.0 + n / 400
        vals = [n, t, 1 / 400, 10.0 * n, -5.0, 8000.0 + n]  # xRec time prf posS posC posH
        vals += [200.0, 0.5, -0.25]  # velocity
        vals += [0.01 * k for k in range(9)]  # af1..af3
        vals += [0.1, -0.02 * n, 0.003]  # yaw pitch roll (radians)
        recs.append(pack(order, "d", vals))
    return b"".join(recs)


def corr(order: str) -> bytes:
    """Three 116-byte records of the 'corr' layout."""
    recs = []
    for n in range(3):
        rec = struct.pack(f"{order}ii", 100 + n, 1)
        rec += pack(order, "d", [0.5 * k + n for k in range(1, 13)])
        rec += struct.pack(f"{order}iii", 10 * n, 20 * n, 30 * n)
        assert len(rec) == 116
        recs.append(rec)
    return b"".join(recs)


def aux(order: str) -> bytes:
    """Three 128-byte records of the AIRSAR 'aux' header layout, with packed bit fields."""
    recs = []
    for n in range(3):
        rec = bytearray(128)
        struct.pack_into(f"{order}IHBBI", rec, 0, 0x03915ED3, 128, 16, 0b10100101, 7000 + n)
        struct.pack_into(f"{order}HIH", rec, 12, 3, 0xDEADBEEF, 0x8001)
        hrs, day = 13 + n, 200 + n
        struct.pack_into(f"{order}H", rec, 20, hrs | (day << 7))
        acc, sec, minute = 2, 45 - n, 30
        struct.pack_into(f"{order}H", rec, 22, acc | (sec << 2) | (minute << 9))
        struct.pack_into(f"{order}IH", rec, 82, 123456 + n, 999)
        struct.pack_into(f"{order}H", rec, 88, n)
        rec[90:122] = bytes((n + k) % 256 for k in range(32))
        recs.append(bytes(rec))
    return b"".join(recs)


def subcom(order: str) -> bytes:
    """Two 4096-byte records of the AIRSAR 'subcom' layout (text fields and time tags)."""
    recs = []
    for n in range(2):
        rec = bytearray(b" " * 4096)
        struct.pack_into(f"{order}HH", rec, 0, 4096, 3100 + n)
        for offset, text in [
            (439, b"Death Valley"),
            (464, b"Imel"),
            (489, b"Operator %d" % n),
            (539, b"POLSAR"),
            (638, b"-282"),
            (1131, b"Operator notes: clear skies, no wind."),
        ]:
            rec[offset : offset + len(text)] = text
        struct.pack_into(f"{order}BBHBBBI", rec, 1412, 7, 4, 1996, 18, 30 + n, 15, 250000000)
        struct.pack_into(f"{order}I", rec, 1476, 55555 + n)
        rec[3004] = 3
        rec[3005:3011] = b"980817"
        rec[3011:3015] = b"EOSD"
        recs.append(bytes(rec))
    return b"".join(recs)


def hw(order: str) -> bytes:
    """Three records of the 'hw' layout: 12 doubles."""
    return b"".join(
        pack(order, "d", [n, 50.0 + n, 0.0025, 34.2, -118.17, 700.0, 1, 2, 3, 0.5, 0.01, 0.02])
        for n in range(3)
    )


def airmoc(order: str) -> bytes:
    """Three 104-byte records of the 'airmoc' layout: a double and 24 floats."""
    return b"".join(
        struct.pack(f"{order}d", 5000.0 + n) + pack(order, "f", [n + k / 8 for k in range(24)])
        for n in range(3)
    )


# --- the list of files ----------------------------------------------------------

PAIRED = {
    "int16": lambda o: pack(o, "h", INT16),
    "int32": lambda o: pack(o, "i", INT32),
    "float32": lambda o: pack(o, "f", FLOAT32),
    "float64": lambda o: pack(o, "d", FLOAT64),
    "complex64": lambda o: complex_bytes(o, "f"),
    "complex128": lambda o: complex_bytes(o, "d"),
    "moc": moc,
    "corr": corr,
    "aux": aux,
    "subcom": subcom,
    "hw": hw,
    "airmoc": airmoc,
}

SINGLE = {
    "bytes.bin": bytes256,
    "ascii.bin": ascii_text,
    "seq.bin": seq,
    "header.bin": header,
    "counter.bin": counter,
    "empty.bin": lambda: b"",
}


def main() -> None:
    for name, make in SINGLE.items():
        (HERE / name).write_bytes(make())
    for name, make in PAIRED.items():
        for suffix, order in [("le", "<"), ("be", ">")]:
            (HERE / f"{name}.{suffix}.bin").write_bytes(make(order))
    print(f"wrote {len(SINGLE) + 2 * len(PAIRED)} fixtures")


if __name__ == "__main__":
    main()

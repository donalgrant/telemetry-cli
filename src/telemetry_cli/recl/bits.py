"""Record lengths in bits (recl -bits).

Frames in a raw bit stream (PCM telemetry off a bit synchronizer, say) needn't
be a whole number of bytes: 25 words of 10 bits make a 250-bit frame. Then no
shift by whole bytes lines frames up, and comparing bytes can't find the
length.

So -bits treats the data as a stream of bits and, for a length of L bits,
scores the fraction of bit positions i at which the 8 bits starting at i equal
the 8 bits starting at i + L: the bit-level version of comparing bytes.
(Comparing 8-bit windows, rather than single bits, keeps what makes the byte
comparison work: a sync word still matches exactly, random windows match 1
time in 256, and a counter's low bits don't pull the answer toward multiples.)

Trying every length at every bit position would be slow, so by default the
lengths come from the data: a sync word makes the same 24-bit window appear
once per frame, where in random data a given 24-bit value is rare. The gaps
between repeats of the most common 24-bit windows are the likely lengths, and
they (and their divisors) are what gets scored.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

PROPOSAL_WIDTH = 24  # bits in the windows whose repeats suggest lengths
SCORE_WIDTH = 8  # bits in the windows compared for scoring
TOP_WINDOWS = 16  # how many of the most common windows to follow
TOP_GAPS = 8  # how many of the most common gaps to propose


def windows(data: bytes | np.ndarray, width: int, *, lsb: bool = False) -> np.ndarray:
    """The value of the ``width`` bits starting at each bit position.

    Bits are read most significant first in each byte, or least significant
    first with ``lsb``. Positions run up to the last full window.
    """
    b = np.frombuffer(bytes(data), dtype=np.uint8)
    if lsb:  # reverse the bits of each byte, then read most significant first
        b = np.packbits(np.unpackbits(b, bitorder="little"))
    k = (width + 7) // 8 + 1  # bytes spanned by a window at any bit offset
    m = len(b) - k + 1
    if m <= 0:
        return np.zeros(0, dtype=np.uint32)
    acc = np.zeros(m, dtype=np.uint64)
    for j in range(k):
        acc = (acc << np.uint64(8)) | b[j : j + m].astype(np.uint64)
    out = np.empty(8 * m, dtype=np.uint64)
    mask = np.uint64((1 << width) - 1)
    for s in range(8):
        out[s::8] = (acc >> np.uint64(8 * k - width - s)) & mask
    return out.astype(np.uint32) if width <= 32 else out


def propose(w: np.ndarray, lo: int, hi: int, fact: int) -> list[int]:
    """Lengths (bits) suggested by gaps between repeats of common windows."""
    if len(w) == 0:
        return []
    values, counts = np.unique(w, return_counts=True)
    common = values[counts >= 3]
    if len(common) == 0:
        return []
    common = common[np.argsort(counts[counts >= 3])[-TOP_WINDOWS:]]
    gaps: Counter[int] = Counter()
    for v in common:
        pos = np.flatnonzero(w == v)
        gaps.update(int(g) for g in np.diff(pos) if g >= PROPOSAL_WIDTH)  # not runs sliding along
    ok = [g for g, _ in gaps.most_common() if lo <= g <= hi and g % fact == 0]
    proposals = ok[:TOP_GAPS]
    lengths = set()
    for g in proposals:
        lengths.update(d for d in range(max(lo, 1), g + 1) if g % d == 0 and d % fact == 0)
    return sorted(lengths)


def scores(w: np.ndarray, lengths: list[int]) -> tuple[list[float], list[float]]:
    """(fraction of equal windows L bits apart, number compared) for each length."""
    out, counts = [], []
    n = len(w)
    for r in lengths:
        if r < 1 or n < 2 * r:
            out.append(0.0)
            counts.append(0.0)
            continue
        out.append(float((w[: n - r] == w[r:]).mean()))
        counts.append(float(n - r))
    return out, counts


def describe(bits: int) -> str:
    """'250 bits (31 bytes + 2 bits)'."""
    whole, extra = divmod(bits, 8)
    unit = "byte" if whole == 1 else "bytes"
    if not extra:
        return f"{bits} bits ({whole} {unit})"
    return f"{bits} bits ({whole} {unit} + {extra} bit{'' if extra == 1 else 's'})"

"""Finding records' sync words (recl -sync).

Given the record length, fold the data into rows of one record each and see
which bit positions hold the same value in (nearly) every record. The longest
run of such positions that has both 0s and 1s is reported: usually a sync
word, together with any fixed bits beside it (the top bits of a counter that
never gets that high, say), which can't be told apart from the sync by
looking at the data. Runs of only 0s or only 1s (padding, unused high bits)
are passed over when there is a mixed run.

The record length itself can come from the sync word: it makes the same bit
pattern repeat once per record, so the most common gap between repeats of
the most common 24-bit patterns is the record length. That works where
comparing bytes doesn't, for records of one continuously sampled signal.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from .bits import PROPOSAL_WIDTH, TOP_WINDOWS, windows

CONSTANT = 0.85  # a bit position is constant if this fraction of records agree
MIN_BITS = 8  # the shortest run reported as a sync pattern
ERRORS_ALLOWED = 0.1  # "nearly matches": at most this fraction of the pattern's bits differ


@dataclass
class Sync:
    offset: int  # bit position of the pattern in each record (from the start of the data)
    bits: str  # the pattern, as 0s and 1s
    mixed: bool  # has both 0s and 1s
    records: int  # records checked
    exact: float  # fraction of them in which the pattern matches exactly
    near: float  # ... matches with at most ERRORS_ALLOWED of its bits wrong

    @property
    def value(self) -> int:
        return int(self.bits, 2)

    def hex(self) -> str:
        return f"0x{self.value:0{(len(self.bits) + 3) // 4}x}"


MIN_SHARE = 0.5  # the most common gap must be at least this share of them all


@dataclass
class Repeats:
    gap: int  # the most common gap, in bits
    count: int  # how often it occurs
    share: float  # its fraction of all the gaps

    @property
    def fixed(self) -> bool:
        """Do records seem to be a fixed length? (Most gaps are the same.)"""
        return self.share >= MIN_SHARE


def length_from_repeats(data: bytes, *, lsb: bool = False, unit: int = 1) -> Repeats | None:
    """The gaps between repeats of the most common 24-bit patterns, if any repeat.

    For records of a fixed length with a sync word, most gaps are the record
    length. unit=8 keeps only gaps that are a whole number of bytes.
    """
    w = windows(data, PROPOSAL_WIDTH, lsb=lsb)
    if len(w) == 0:
        return None
    values, counts = np.unique(w, return_counts=True)
    keep = counts >= 3
    if not keep.any():
        return None
    common = values[keep][np.argsort(counts[keep])[-TOP_WINDOWS:]]
    gaps: Counter[int] = Counter()
    for v in common:
        # A pattern can't recur closer than its own width: shorter gaps are
        # runs (of zero bytes, say) sliding along, not repeats.
        gaps.update(
            int(g) for g in np.diff(np.flatnonzero(w == v)) if g >= PROPOSAL_WIDTH and g % unit == 0
        )
    if not gaps:
        return None
    gap, count = gaps.most_common(1)[0]
    return Repeats(gap, count, count / sum(gaps.values()))


def find(data: bytes, length_bits: int, *, lsb: bool = False) -> Sync | None:
    """The sync pattern of records length_bits long, or None if nothing is constant."""
    b = np.frombuffer(bytes(data), dtype=np.uint8)
    stream = np.unpackbits(b, bitorder="little" if lsb else "big")
    L = length_bits
    rows = len(stream) // L
    if rows < 2:
        return None
    ones = stream[: rows * L].reshape(rows, L).mean(axis=0)
    constancy = np.maximum(ones, 1 - ones)
    majority = (ones >= 0.5).astype(np.uint8)
    good = constancy >= CONSTANT
    if not good.any():
        return None
    runs = _circular_runs(good)
    best = max(
        runs,
        key=lambda r: (_mixed(majority, *r), r[1], -r[0]),
    )
    start, n = best
    if n < MIN_BITS:
        return None
    idx = (start + np.arange(n)) % L
    pattern = majority[idx]
    # check each record: the pattern starts at start + k*L in the stream
    firsts = np.arange(start, len(stream) - n + 1, L)
    got = stream[firsts[:, None] + np.arange(n)]
    wrong = (got != pattern).sum(axis=1)
    return Sync(
        offset=int(start),
        bits="".join(map(str, pattern.tolist())),
        mixed=_mixed(majority, start, n),
        records=len(firsts),
        exact=float((wrong == 0).mean()),
        near=float((wrong <= ERRORS_ALLOWED * n).mean()),
    )


def _circular_runs(good: np.ndarray) -> list[tuple[int, int]]:
    """(start, length) of each run of True, treating the array as a circle."""
    L = len(good)
    if good.all():
        return [(0, L)]
    runs = []
    for i in range(L):
        if good[i] and not good[(i - 1) % L]:
            n = 0
            while n < L and good[(i + n) % L]:
                n += 1
            runs.append((i, n))
    return runs


def _mixed(majority: np.ndarray, start: int, n: int) -> bool:
    bits = majority[(start + np.arange(n)) % len(majority)]
    return bool(bits.min() != bits.max())

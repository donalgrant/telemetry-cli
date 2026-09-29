"""Finding records' sync words (recl -sync).

Given the record length, line the records up and see which bit positions hold
the same value in (nearly) every record. Records are lined up on the repeats
of the most common bit pattern that recurs once per record, which copes with
bit slips; failing that, the data are folded into rows of one record each. The longest
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
    offset: int  # bit position of the pattern in the first record, from the start of the data
    bits: str  # the pattern, as 0s and 1s
    mixed: bool  # has both 0s and 1s
    records: int  # records checked
    exact: float  # fraction of them in which the pattern matches exactly
    near: float  # ... matches with at most ERRORS_ALLOWED of its bits wrong
    irregular: int = 0  # gaps between the pattern's repeats that aren't one record

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
    """The sync pattern of records length_bits long, or None if nothing is constant.

    If a bit pattern repeats every record, the records are lined up on its
    repeats, which finds the sync word even where bits were lost or added
    (a bit slip moves every later record). Otherwise the data are folded into
    rows of one record each.
    """
    b = np.frombuffer(bytes(data), dtype=np.uint8)
    stream = np.unpackbits(b, bitorder="little" if lsb else "big")
    positions = _anchor(data, length_bits, lsb)
    if positions is not None:
        found = _find_anchored(stream, positions, length_bits)
        if found is not None:
            return found
    return _find_folded(stream, length_bits)


MAX_ANCHORS = 4000  # occurrences used to measure which bits are constant


ANCHOR_SHARE = 0.8  # of an anchor's gaps, the fraction that must be exactly one record


def _anchor(data: bytes, L: int, lsb: bool) -> np.ndarray | None:
    """Positions of a 24-bit pattern that repeats exactly every L bits, if there is one.

    Of the most common patterns, it takes one whose repeats are almost all
    exactly one record apart (a sync word's are; a pattern that merely turns
    up about once a record, at the edge of padding say, isn't), preferring
    the most repeats, then the most changes between 0 and 1.
    """
    w = windows(data, PROPOSAL_WIDTH, lsb=lsb)
    if len(w) == 0:
        return None
    values, counts = np.unique(w, return_counts=True)
    best = None
    for j in np.argsort(counts)[::-1][:TOP_WINDOWS]:
        v = int(values[j])
        if counts[j] < 3:
            continue
        pos = np.flatnonzero(w == v)
        gaps = np.diff(pos)
        if not len(gaps) or (gaps == L).mean() < ANCHOR_SHARE:
            continue
        changes = bin(v ^ (v >> 1)).count("1") - (v >> (PROPOSAL_WIDTH - 1))
        key = (int((gaps == L).sum()), changes)
        if best is None or key > best[0]:
            best = (key, pos)
    if best is None:
        return None
    kept = [int(best[1][0])]
    for p in best[1][1:].tolist():
        if p - kept[-1] >= L // 2:  # not a second match inside one record
            kept.append(p)
    return np.array(kept)


def _find_anchored(stream: np.ndarray, positions: np.ndarray, L: int) -> Sync | None:
    width = PROPOSAL_WIDTH
    lo, hi = -(L - width), L  # bits around each occurrence to look at
    inside = positions[(positions + lo >= 0) & (positions + hi <= len(stream))]
    if len(inside) < 2:
        return None
    sample = inside[:: max(1, len(inside) // MAX_ANCHORS)]
    around = stream[sample[:, None] + np.arange(lo, hi)]
    ones = around.mean(axis=0)
    good = np.maximum(ones, 1 - ones) >= CONSTANT
    majority = (ones >= 0.5).astype(np.uint8)
    # grow the run from the anchor's own bits, at -lo .. -lo + width
    first, last = -lo, -lo + width
    while first > 0 and good[first - 1] and last - first < L:
        first -= 1
    while last < len(good) and good[last] and last - first < L:
        last += 1
    start, n = first + lo, last - first  # relative to each occurrence
    pattern = majority[first:last]
    starts = positions + start
    starts = starts[(starts >= 0) & (starts + n <= len(stream))]
    got = stream[starts[:, None] + np.arange(n)]
    wrong = (got != pattern).sum(axis=1)
    return Sync(
        # where the pattern falls in the first record (its first occurrence
        # may be later, if earlier ones have bit errors)
        offset=int(starts[0]) % L,
        bits="".join(map(str, pattern.tolist())),
        mixed=bool(pattern.min() != pattern.max()),
        records=len(starts),
        exact=float((wrong == 0).mean()),
        near=float((wrong <= ERRORS_ALLOWED * n).mean()),
        irregular=int((np.diff(positions) != L).sum()),
    )


def _find_folded(stream: np.ndarray, L: int) -> Sync | None:
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

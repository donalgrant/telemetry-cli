"""Cutting frames out of a bit stream and writing each on byte boundaries.

A frame of L bits becomes ceil(L/8) bytes: its bits first, most significant
bit first, then padding (or, with ``left``, the padding first). Frames are
found either by stepping a fixed L bits from an offset, or by searching for a
sync pattern, which copes with the bit slips of real serial streams.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..recl.bits import windows

MAX_SYNC_BITS = 56  # the longest pattern the window search handles
_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


class RealignError(ValueError):
    pass


def stream_bits(data: bytes, *, lsb: bool = False) -> np.ndarray:
    return np.unpackbits(
        np.frombuffer(bytes(data), dtype=np.uint8), bitorder="little" if lsb else "big"
    )


def pack_frames(frames: np.ndarray, *, left: bool = False, fill: int = 0) -> bytes:
    """Frames (rows of bits) as bytes, each padded to whole bytes."""
    n, length = frames.shape
    pad = -length % 8
    if pad:
        padding = np.full((n, pad), fill, dtype=np.uint8)
        frames = np.hstack([padding, frames] if left else [frames, padding])
    return np.packbits(frames, axis=1).tobytes()


def fixed(bits: np.ndarray, length: int, offset: int = 0, limit: int | None = None) -> np.ndarray:
    """Frames of `length` bits, one after another from bit `offset`."""
    if length < 1:
        raise RealignError("the frame length must be at least 1 bit")
    if offset < 0:
        raise RealignError("the offset can't be negative")
    n = max((len(bits) - offset) // length, 0)
    if limit is not None:
        n = min(n, limit)
    return bits[offset : offset + n * length].reshape(n, length)


@dataclass
class Found:
    starts: list[int]  # bit position of each frame
    errors: list[int]  # bit errors in its sync pattern
    gaps: dict[int, int] = field(default_factory=dict)  # gap between frames: how often


def search(data: bytes, pattern: str, length: int, *, lsb: bool = False, errors: int = 0,
           slip: int = 8, limit: int | None = None) -> Found:  # fmt: skip
    """Frames that start where `pattern` (0s and 1s) matches, with at most `errors` bits wrong.

    A match well inside the previous frame is skipped (a false match in its
    data). One up to `slip` bits before the previous frame's end starts a new
    frame: bits were lost from the stream. (The previous frame then runs into
    this one's first bits.)
    """
    if not pattern or set(pattern) - {"0", "1"}:
        raise RealignError(f"the sync pattern must be 0s and 1s, not {pattern!r}")
    k = len(pattern)
    if k > MAX_SYNC_BITS:
        raise RealignError(f"the sync pattern can be at most {MAX_SYNC_BITS} bits")
    if k > length:
        raise RealignError("the sync pattern is longer than the frame")
    values = windows(data, k, lsb=lsb).astype(np.uint64)  # the k bits at each position
    diff = values ^ np.uint64(int(pattern, 2))
    wrong = np.zeros(len(diff), dtype=np.int64)
    for _ in range((k + 7) // 8):
        wrong += _POPCOUNT[(diff & np.uint64(0xFF)).astype(np.uint8)]
        diff >>= np.uint64(8)
    last_start = 8 * len(data) - length  # a frame must fit
    candidates = np.flatnonzero(wrong <= errors)
    starts, errs, gaps = [], [], {}
    for p in candidates.tolist():
        if p > last_start:
            break
        if starts and p < starts[-1] + length - slip:
            continue  # inside the previous frame
        if starts:
            gap = p - starts[-1]
            gaps[gap] = gaps.get(gap, 0) + 1
        starts.append(p)
        errs.append(int(wrong[p]))
        if limit is not None and len(starts) >= limit:
            break
    return Found(starts, errs, gaps)


def gather(bits: np.ndarray, starts: list[int], length: int) -> np.ndarray:
    idx = np.asarray(starts, dtype=np.int64)[:, None] + np.arange(length)
    return bits[idx] if len(starts) else np.zeros((0, length), dtype=np.uint8)

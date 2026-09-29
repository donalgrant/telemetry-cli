"""Scoring candidate record lengths.

For a record length R, the score of a buffer is the fraction of its bytes
that equal the byte R bytes further on. For unrelated random data that is
about 1/256; it is higher when records are R bytes long, since records of
the same format tend to have the same bytes in the same places (sync words,
flags, the high bytes of counters and slowly varying values). Scores are
averaged over the buffers.

(Comparing whole bytes works better than counting agreeing bits, which is
what the Perl original set out to do: a counter's low bits agree more often
at multiples of the record length than at the length itself, which pulls a
bit count toward multiples, and bits agree often at small shifts in text.)

A length R is scored only in buffers of at least 2R bytes (as in the Perl);
elsewhere its score is 0.
"""

from __future__ import annotations

import numpy as np


def agreement(buffers: np.ndarray, lengths: list[int]) -> np.ndarray:
    """Scores, shape (number of buffers, number of lengths)."""
    nbuf, size = buffers.shape
    out = np.zeros((nbuf, len(lengths)))
    for j, r in enumerate(lengths):
        if r < 1 or size < 2 * r:
            continue
        out[:, j] = (buffers[:, : size - r] == buffers[:, r:]).mean(axis=1)
    return out


def compared(buffers: np.ndarray, lengths: list[int]) -> np.ndarray:
    """How many byte pairs were compared for each length, over all buffers."""
    nbuf, size = buffers.shape
    r = np.array(lengths)
    return np.where(size >= 2 * r, 1.0 * (size - r) * nbuf, 0.0)


def choose(
    lengths: list[int],
    scores: list[float],
    counts: list[float] | None = None,
    tolerance: float = 0.25,
) -> int:
    """The record length the scores point to.

    Multiples of the record length score about as well as the length itself,
    since the data repeat at those too; the longer ones only less precisely,
    as fewer bytes overlap. So the answer is the smallest length that divides
    the best-scoring one and scores nearly as well: within three standard
    errors of it, or within ``tolerance`` of its height above a typical
    score, whichever is more. It must also score at least half that height
    above a typical score, so that a length with no structure of its own (1,
    say) isn't chosen when the signal is weak.

    A typical score is the lower quartile: with short records, most of the
    candidates may be multiples of the record length, so the median may not
    be typical. With fewer than five candidates, the lowest score stands in,
    and the structure check is skipped.

    ``counts`` are the numbers of byte pairs compared, for the standard errors.
    """
    best = max(range(len(lengths)), key=lambda j: (scores[j], -lengths[j]))
    few = len(lengths) < 5
    baseline = float(min(scores) if few else np.percentile(scores, 25))
    height = scores[best] - baseline
    p = min(max(baseline, 1 / 256), 1 - 1 / 256)

    def stderr(j):  # of a fraction near the baseline
        return float(np.sqrt(p * (1 - p) / counts[j])) if counts and counts[j] > 0 else 0.0

    for j in sorted(range(len(lengths)), key=lambda j: lengths[j]):
        r = lengths[j]
        if not r or lengths[best] % r:
            continue
        margin = max(tolerance * height, 3 * np.hypot(stderr(j), stderr(best)))
        # nearly as good as the best, and clearly better than a typical length
        if scores[j] >= scores[best] - margin and (few or scores[j] - baseline >= height / 2):
            return j
    return best

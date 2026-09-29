"""The recl command: estimate the record length of a binary file.

    recl filename [ options ]
    cat filename | recl - [ options ]

Run ``recl -help`` for help.
"""

from __future__ import annotations

import sys
from typing import BinaryIO, TextIO

import numpy as np

from .._cli import broken_pipe
from .._getopt import OptionError, getoptions
from .._msg import Messenger
from .._perl import perl_str
from .corr import agreement, choose, compared

SPECS = ["v|verbose", "h|help", "f|full", "q|quiet", "part|partial", "skip|header=i", "min=i",
         "max=i", "minrecs=i", "maxbufs=i", "fact|factor|mult=i", "only=s", "limit=i",
         "reduce=f"]  # fmt: skip

HELP = """\
recl - estimate the record length of a binary file

SYNOPSIS
    recl filename [ options ]
    cat filename | recl - [ options ]

DESCRIPTION
    recl compares the file with itself shifted by each possible record
    length R, and reports the R at which the most bytes are equal: records
    of the same format tend to have the same bytes in the same places. It
    prints

        RESULT R      the estimated record length
        CORR x        the percentage of bytes equal to the byte R bytes on
                      (about 0.4 for unrelated random data)

    and notes about the lengths it checked. Every multiple of the record
    length agrees about as well as the length itself; recl reports the
    smallest.

    Unless -partial is given, recl assumes the file (after any header) holds
    whole records, so it only checks lengths that divide its size.

OPTIONS
    Options can be abbreviated.

    -skip=bytes (or -header)
        Skip a header of this many bytes.
    -min=bytes, -max=bytes
        The shortest and longest record lengths to check. By default, 1 and
        half the data (see -minrecs).
    -minrecs=N
        The file holds at least N records (default 2): the same as
        -max=(size-skip)/N. -max takes precedence.
    -fact=bytes (also -factor, -mult)
        The record length is a multiple of this, e.g. 8 for doubles.
    -only=list
        Check only these lengths (comma-separated).
    -partial
        Don't assume whole records: check every length in range.
    -maxbufs=N
        Use only the first N buffers (of twice the longest length checked).
    -limit=bytes
        Use only the first this many bytes of data.
    -reduce=factor
        Use only the first 1/factor of the data (factor >= 1).
    -full
        Compare the data (or the part -limit or -reduce keep) as one piece,
        rather than buffer by buffer.
    -verbose
        Show the score of every length in every buffer, and a sorted table.
    -quiet
        Show only the result.
    -help
        Show this help.

The full manual is at
    https://github.com/donalgrant/telemetry-cli/blob/main/docs/recl.md
"""


class ReclError(ValueError):
    pass


def candidate_lengths(databytes: int, lo: int, hi: int, fact: int, partial: bool) -> list[int]:
    """Lengths in [lo, hi] that are multiples of fact (and divide databytes, unless partial)."""
    return [
        r for r in range(max(lo, 1), hi + 1) if r % fact == 0 and (partial or databytes % r == 0)
    ]


def main(
    argv: list[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    stderr = stderr if stderr is not None else sys.stderr

    def error(message: str, status: int = 1) -> int:
        print(f"recl: {message}", file=stderr)
        return status

    try:
        o, args = getoptions(argv, SPECS)
    except OptionError as e:
        return error(f"{e} (see 'recl -help')", 2)
    if o.get("h"):
        stdout.write(HELP.encode())
        return 0
    if not args:
        return error("no input file given (use - for stdin); see 'recl -help'", 2)
    try:
        return _run(args[0], o, stdin, stdout)
    except ReclError as e:
        return error(str(e))
    except OSError as e:
        return error(f"Can't open {args[0]} for input: {e.strerror}")
    except BrokenPipeError:
        return broken_pipe(stdout)


def _run(file: str, o: dict, stdin: BinaryIO, stdout: BinaryIO) -> int:
    lines: list[str] = []

    class _Out:
        def write(self, s):
            lines.append(s)

    msg = Messenger(_Out())
    if file == "-":
        data = stdin.read()
    else:
        with open(file, "rb") as f:
            data = f.read()

    skip = o.get("skip", 0)
    reduce = o.get("reduce", 1.0)
    if reduce < 1:
        raise ReclError("-reduce must be at least 1")
    fact = o.get("fact", 1)
    if fact < 1:
        raise ReclError("-fact must be at least 1")
    databytes = len(data) - skip
    if databytes < 2:
        raise ReclError(f"too little data: {max(databytes, 0)} bytes after the header")
    hi = o["max"] if "max" in o else databytes // o.get("minrecs", 2)

    if "only" in o:
        try:
            lengths = [int(x) for x in o["only"].split(",") if x.strip()]
        except ValueError:
            raise ReclError(
                f"-only needs a comma-separated list of lengths: {o['only']!r}"
            ) from None
    else:
        lengths = candidate_lengths(databytes, o.get("min", 1), hi, fact, bool(o.get("part")))
    msg("Checking Record Lengths " + ", ".join(map(str, lengths)) + " bytes")
    _flush(lines, stdout)
    if not lengths:
        raise ReclError("no record lengths to check; see the -min, -max and -fact options")
    if min(lengths) < 1:
        raise ReclError("record lengths must be at least 1 byte")

    use = np.frombuffer(data, dtype=np.uint8)[skip:]
    if "limit" in o:
        use = use[: max(o["limit"], 0)]
    use = use[: int(len(use) / reduce)]

    bufsiz = 2 * max(lengths)
    if o.get("f") or len(use) < bufsiz:
        buffers = use[np.newaxis, :]  # one piece
    else:
        nbuf = len(use) // bufsiz
        if "maxbufs" in o:
            nbuf = min(nbuf, max(o["maxbufs"], 1))
        buffers = use[: nbuf * bufsiz].reshape(nbuf, bufsiz)

    scores = agreement(buffers, lengths)  # (buffers, lengths)
    if o.get("v"):
        running = np.cumsum(scores, axis=0)
        for i in range(scores.shape[0]):
            for j, r in enumerate(lengths):
                msg(f"buf {i + 1} reclen {r} corr {perl_str(float(scores[i, j]))} "
                    f"accum-corr {perl_str(float(running[i, j]))}")  # fmt: skip
    mean = scores.mean(axis=0).tolist()
    chosen = choose(lengths, mean, compared(buffers, lengths).tolist())
    if o.get("v"):
        msg("Table of Sorted Correlations")
        for j in sorted(range(len(lengths)), key=lambda j: (-mean[j], lengths[j])):
            msg(f"{100 * mean[j]:5.2f}% for reclen {lengths[j]}")
    msg(lengths[chosen], "RESULT")
    if not o.get("q"):
        msg(perl_str(100.0 * mean[chosen]), "CORR")
        msg(f"Based on {buffers.shape[0]} buffers, each of length {buffers.shape[1]}")
    _flush(lines, stdout)
    stdout.flush()
    return 0


def _flush(lines: list[str], stdout: BinaryIO) -> None:
    stdout.write("".join(lines).encode())
    lines.clear()

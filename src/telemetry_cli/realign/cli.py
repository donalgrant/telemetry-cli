"""The realign command: put bit-offset frames on byte boundaries.

    realign [options] file length_bits [offset_bits] > frames.dat
    cat file | realign - [options] length_bits [offset_bits]

Run ``realign -help`` for help.
"""

from __future__ import annotations

import sys
from typing import BinaryIO, TextIO

from .._cli import broken_pipe
from .._getopt import OptionError, getoptions
from . import frames as fr

SPECS = ["sync=s", "errors=i", "slip=i", "lsb", "left", "fill=i", "max=i", "offset=i", "q|quiet",
         "h|help"]  # fmt: skip

HELP = """\
realign - put frames that start at any bit on byte boundaries

SYNOPSIS
    realign [options] file length_bits [offset_bits] > frames.dat
    cat file | realign - [options] length_bits [offset_bits]

DESCRIPTION
    In a raw bit stream, frames needn't start at the start of a byte, nor be
    a whole number of bytes long. realign cuts the stream into frames of
    length_bits bits, starting offset_bits bits in (default 0), and writes
    each frame starting on a byte boundary, padded with 0 bits to whole bytes.
    A 250-bit frame becomes 32 bytes, which pick can then decode. recl -bits
    -sync reports the frame length and offset.

    With -sync, realign finds each frame by its sync pattern instead of
    stepping a fixed number of bits, which copes with bit slips (a bit lost
    or added in the stream).

OPTIONS
    -sync=bits
        Find frames where this pattern of 0s and 1s (up to 56 bits) starts.
    -errors=n
        With -sync: allow up to n wrong bits in the pattern (default 0).
    -slip=n
        With -sync: a pattern up to n bits before the end of the previous
        frame starts a new frame (bits were lost); default 8. Matches
        earlier than that are taken to be false ones in the data.
    -lsb
        The input's bits are least significant first in each byte. (Frames
        are always written most significant bit first.)
    -left
        Pad at the start of each frame rather than the end.
    -fill=1
        Pad with 1 bits rather than 0.
    -max=n
        Write at most n frames.
    -offset=n
        The same as giving offset_bits.
    -quiet
        No summary on stderr.
    -help
        Show this help.

The full manual is at
    https://github.com/donalgrant/telemetry-cli/blob/main/docs/realign.md
"""


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
        print(f"realign: {message}", file=stderr)
        return status

    try:
        o, args = getoptions(argv, SPECS)
    except OptionError as e:
        return error(f"{e} (see 'realign -help')", 2)
    if o.get("h"):
        stdout.write(HELP.encode())
        return 0
    if len(args) < 2:
        return error("give a file (or -) and a frame length in bits; see 'realign -help'", 2)
    try:
        length = int(args[1])
        offset = int(args[2]) if len(args) > 2 else o.get("offset", 0)
    except ValueError:
        return error("the frame length and offset must be numbers of bits", 2)
    fill = o.get("fill", 0)
    if fill not in (0, 1):
        return error("-fill must be 0 or 1", 2)
    try:
        if args[0] == "-":
            data = stdin.read()
        else:
            with open(args[0], "rb") as f:
                data = f.read()
    except OSError as e:
        return error(f"Can't open {args[0]} for input: {e.strerror}")

    lsb = bool(o.get("lsb"))
    try:
        if "sync" in o:
            found = fr.search(data, o["sync"], length, lsb=lsb, errors=o.get("errors", 0),
                              slip=o.get("slip", 8), limit=o.get("max"))  # fmt: skip
            starts = [p for p in found.starts if p >= offset]
            frames = fr.gather(fr.stream_bits(data, lsb=lsb), starts, length)
            summary = _sync_summary(found, starts, length)
        else:
            frames = fr.fixed(fr.stream_bits(data, lsb=lsb), length, offset, o.get("max"))
            left_over = 8 * len(data) - offset - len(frames) * length
            summary = [f"{len(frames)} frames of {length} bits from bit {offset}; "
                       f"{max(left_over, 0)} bits left over"]  # fmt: skip
        stdout.write(fr.pack_frames(frames, left=bool(o.get("left")), fill=fill))
        stdout.flush()
    except fr.RealignError as e:
        return error(str(e))
    except BrokenPipeError:
        return broken_pipe(stdout)
    if not o.get("q"):
        nbytes = (length + 7) // 8
        pad = 8 * nbytes - length
        summary.append(f"each written as {nbytes} bytes ({pad} padding bits)")
        for line in summary:
            print(f"realign: {line}", file=stderr)
    return 0


def _sync_summary(found: fr.Found, starts: list[int], length: int) -> list[str]:
    lines = [f"{len(starts)} frames found by the sync pattern"]
    with_errors = sum(1 for e in found.errors if e)
    if with_errors:
        lines[0] += f" ({with_errors} with bit errors in it)"
    others = {g: n for g, n in found.gaps.items() if g != length}
    if others:
        slips = ", ".join(
            f"{g} bits ({n}x)" for g, n in sorted(others.items(), key=lambda x: -x[1])[:5]
        )
        lines.append(f"frames other than {length} bits apart (bit slips, or lost frames): {slips}")
    return lines

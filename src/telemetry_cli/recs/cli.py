"""The recs command: extract records from a stream of data.

    recs filename [ options ] record_start_match [ reclen_bytes ]
    cat filename | recs - [ options ] record_start_match [ reclen_bytes ]

Run ``recs -help`` for help.
"""

from __future__ import annotations

import os
import sys
from typing import BinaryIO, TextIO

from .._getopt import OptionError, getoptions
from .extract import Extractor, RecsError

SPECS = ["v", "x", "z", "mml=i", "e=s", "a", "f=s", "r", "test", "help", "min_reclen=i",
         "max_reclen=i", "append=s", "prepend=s", "nl"]  # fmt: skip

HELP = """\
recs - record extraction utility

SYNOPSIS
    recs filename [ options ] record_start_match [ reclen_bytes ]
    cat filename | recs - [ options ] record_start_match [ reclen_bytes ]

DESCRIPTION
    recs extracts records from a data stream. The arguments are:

    filename
        File from which to extract records. If filename is '-', then
        stdin is used for input.

    record_start_match
        String to match for the beginning of a record. By default, this is
        a simple string, but see the -r option.

    reclen_bytes
        Number of bytes for each record. If not given, records are
        extracted from each record_start_match to the next one (or to the
        end marker given with -e).

OPTIONS
    Options can be abbreviated, and can go anywhere on the command line.

    -a  Start a new record at every match of the start marker, even if the
        number of bytes for a record has not yet been read. Missing bytes
        are filled with the fill string.

    -f=string
        Fill string for padded records. By default, a null byte.

    -e=string
        String to match for the end of a record.

    -r  Interpret match strings as regular expressions (Python syntax),
        rather than simple strings.

    -x  Exclude the bytes matching the start marker from the records.

    -z  Exclude the bytes matching the end marker from the records.

    -mml=bytes
        The maximum expected length of a match. This keeps matches from
        being missed when they straddle a buffer boundary. A warning is
        printed if a longer match is found. By default, the length of the
        match string, which is not a good guess for a regex such as '\\d+'.

    -min_reclen=bytes
        Minimum record length: shorter records are padded with the fill
        string. Works for fixed-length and marker-to-marker extraction.

    -max_reclen=bytes
        Maximum record length: longer records are truncated.

    -prepend=string
        A string to write before each record.

    -append=string
        A string to write after each record.

    -nl Write a newline after each record (after the -append string).

    -v  Verbose (accepted, but has no effect).

    -help
        Show this help.

The full manual is at
    https://github.com/donalgrant/telemetry-cli/blob/main/docs/recs.md
"""


def _bytes(s: str) -> bytes:
    """A command-line string as the bytes the user typed."""
    return os.fsencode(s)


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
        print(f"recs: {message}", file=stderr)
        return status

    try:
        o, args = getoptions(argv, SPECS)
    except OptionError as e:
        return error(f"{e} (see 'recs -help')", 2)
    if o.get("help"):
        stdout.write(HELP.encode())
        return 0
    if o.get("test"):
        print("recs: the -test self-tests are now part of telemetry-cli's test suite", file=stderr)
        return 0
    if not args:
        return error("no input file given (use - for stdin); see 'recs -help'", 2)
    if len(args) < 2:
        return error("no record start marker given; see 'recs -help'", 2)
    file, match = args[0], _bytes(args[1])
    if not match:
        return error("the record start marker is empty", 2)
    try:
        out_length = int(args[2]) if len(args) > 2 else -1
    except ValueError:
        return error(f"the record length must be a number of bytes, not {args[2]!r}", 2)

    if out_length < 0 and "e" not in o:
        # with no record length and no end marker, take records from start to start
        o["e"] = args[1]
        o.setdefault("a", 1)
    append = _bytes(o.get("append", "")) + (b"\n" if o.get("nl") else b"")
    options = {
        "xbeg": o.get("x"),
        "xend": o.get("z"),
        "mml": o.get("mml", len(match)),
        "sp": o.get("a"),
        "fill": _bytes(o["f"]) if "f" in o else None,
        "regex": o.get("r"),
        "nmin": o.get("min_reclen"),
        "nmax": o.get("max_reclen"),
        "pre": _bytes(o["prepend"]) if "prepend" in o else None,
        "post": append,
    }

    def warn(message: str) -> None:
        print(f"recs: warning: {message}", file=stderr)

    try:
        if file == "-":
            inp = stdin
        else:
            inp = open(file, "rb")  # noqa: SIM115
    except OSError as e:
        return error(f"Can't open {file} for input: {e.strerror}")
    try:
        E = Extractor(inp, stdout, options, warn=warn)
        if out_length < 0:
            stop = _bytes(o["e"])
            (E.reg_reg if o.get("r") else E.str_str)(match, stop)
        else:
            (E.reg_n if o.get("r") else E.str_n)(match, out_length)
    except RecsError as e:
        return error(str(e))
    except BrokenPipeError:
        return 0
    finally:
        if inp is not stdin:
            inp.close()
    stdout.flush()
    return 0

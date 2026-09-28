"""The tgen command: generate telemetry records from a command file.

    tgen [ options ] command_file [ nframes [ firstframe ] ] > telemetry.dat
    tgen --convert old_perl_command_file > new_command_file

Run ``tgen -help`` for help.
"""

from __future__ import annotations

import sys
from typing import BinaryIO, TextIO

from .. import __version__
from .._cli import broken_pipe
from .._getopt import OptionError, getoptions
from .._perl import numify, truthy
from . import cmdfile
from .convert import convert
from .runtime import Generator, TgenError

SPECS = ["h|help|man", "r|random|random_fill", "f|fill=i", "n|notify=i", "q|quiet",
         "v|version", "seed=i", "convert"]  # fmt: skip

USAGE = """\
Usage:
    tgen [ options ] command_file [ nframes [ firstframe ] ] > telemetry.dat
    tgen --convert perl_command_file > python_command_file
    tgen -help
"""

HELP = (
    USAGE
    + """
tgen reads a command file and writes records (frames) laid out as it says:
nframes of them (default 1), numbering them from firstframe (default 0).

Options:
    -r, -random       fill unspecified bytes with random values
    -f, -fill=n       fill unspecified bytes with the byte n (default 0)
    -n, -notify=n     report progress on stderr every n frames (default 100)
    -q, -quiet        no progress reports
    -seed=n           seed the random numbers (rand and -r), for repeatable output
    -convert          translate a Perl tgen command file to the Python form
    -v, -version      show the version
    -h, -help         show this help

A command file holds item specifications, one per line:

    name # offset # trigger # type # value

Each field is Python code, evaluated for every frame. The value is packed
with the type (a Perl pack template such as 'C', 'L', 'a10' or f"C{n}") and
written at the byte offset, if the trigger is true. A negative offset means
"evaluate the value but don't write it". Other lines are Python statements,
run once at the start; lines starting with #, ! or ; are comments.

In the code, I is the frame number, F the fill byte, and P.name.value an
item's value. The full manual, with examples, is at
    https://github.com/donalgrant/telemetry-cli/blob/main/docs/tgen.md
"""
)


def main(
    argv: list[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    stdout = stdout if stdout is not None else sys.stdout.buffer
    stderr = stderr if stderr is not None else sys.stderr

    def error(message: str, status: int = 1) -> int:
        print(f"tgen: {message}", file=stderr)
        return status

    try:
        o, args = getoptions(argv, SPECS)
    except OptionError as e:
        return error(f"{e} (see 'tgen -help')", 2)
    if o.get("v"):
        print(f"tgen (Python), from telemetry-cli {__version__}", file=stderr)
        return 0
    if o.get("h"):
        stdout.write(HELP.encode())
        return 0
    if not args:
        stderr.write(USAGE)
        return 2
    try:
        with open(args[0], encoding="latin-1") as f:
            text = f.read()
    except OSError as e:
        return error(f"Can't read {args[0]}:  {e.strerror}")
    if o.get("convert"):
        stdout.write(convert(text).encode("latin-1"))
        return 0

    def count(i, default):
        if len(args) <= i:
            return default
        v = numify(args[i])
        return int(v) if truthy(args[i]) and v else default  # Perl: shift || default

    nframes, first = count(1, 1), count(2, 0)
    fill = "random" if o.get("r") else o.get("f", 0)
    try:
        items, statements = cmdfile.parse(text)
        gen = Generator(
            items, statements, fill=fill, seed=o.get("seed"), stderr=stderr, source=args[0]
        )
        gen.run(
            stdout,
            nframes,
            first,
            notify=o.get("n") or 100,
            quiet=bool(o.get("q")),
            progress=lambda m: print(m, file=stderr),
        )
    except TgenError as e:
        return error(str(e))
    except BrokenPipeError:
        return broken_pipe(stdout)
    stdout.flush()
    return 0

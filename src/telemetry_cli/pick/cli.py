"""The pick command: extract and print fields from fixed-length binary records.

    pick file.dat reclen [ fieldRequests | options | parameters ]
    cat file.dat | pick reclen [ fieldRequests | options | parameters ]

Run ``pick ?`` for help.
"""

from __future__ import annotations

import sys
from typing import BinaryIO, TextIO

from .._cli import broken_pipe
from .commandline import UsageError, parse, resolve, wants_help
from .fields import FieldError, parse_fields
from .formats import FormatError, render
from .help import help_text


class _Input:
    """Record input with the Perl original's seek rules.

    Files can seek anywhere; stdin can only skip forward (a request to go
    back is ignored, as in the Perl).
    """

    def __init__(self, stream: BinaryIO, seekable: bool):
        self.stream = stream
        self.seekable = seekable
        self.pos = 0

    def seek(self, target: int) -> bool:
        if not target:
            return True
        n = target - self.pos
        if not n:
            return True
        if self.seekable:
            if target < 0:
                return False
            self.pos = target
            self.stream.seek(n, 1)
            return True
        if n < 1:
            return True
        self.pos = target
        return len(self.stream.read(n)) > 0

    def read(self, n: int) -> bytes:
        return self.stream.read(n)


def main(
    argv: list[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
    host_order: str | None = None,
) -> int:
    """Run pick. Returns the exit status.

    host_order ("big" or "little") overrides the machine's byte order, which
    is used when the data's order isn't given; the tests use it to check
    pick's big-endian behavior on any machine.
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    stderr = stderr if stderr is not None else sys.stderr
    host = host_order or sys.byteorder
    try:
        return _run(argv, stdin, stdout, stderr, host)
    except (UsageError, FieldError, FormatError) as e:
        stdout.flush()
        print(f"pick: {e}", file=stderr)
        topics = getattr(e, "topics", "")
        if isinstance(e, FormatError):
            topics = "f"
        if topics:
            print(f"(see 'pick --help {topics}')", file=stderr)
        return 1
    except BrokenPipeError:
        return broken_pipe(stdout)


def _help_argv(argv: list[str]) -> list[str]:
    """Turn ``--help [topic]`` / ``-h [topic]`` into pick's ``?topic`` form."""
    if argv and argv[0] in ("--help", "-h"):
        topic = argv[1] if len(argv) > 1 else ""
        return ["??" if topic == "all" else "?" + topic.lstrip("?") if topic else "help"]
    return argv


def _run(argv, stdin, stdout, stderr, host) -> int:
    cmd = parse(_help_argv(argv))
    if wants_help(cmd.text):
        stdout.write(
            help_text(
                cmd.text,
                cmd.symbols if cmd.symbol_file else None,
                cmd.symbol_file or "",
            ).encode("latin-1")
        )
        return 0
    plan = resolve(cmd)
    opts = cmd.opts
    order = host if cmd.order in (None, "native") else cmd.order
    if opts["r"]:
        order = "big" if order == "little" else "little"
    fields = parse_fields(plan.fields_text, plan.size, binary=opts["u"])
    if plan.size <= 0:  # the Perl printed empty records forever
        raise UsageError("the record size must be at least 1 byte", "p")

    if plan.file == "-":
        if plan.from_stdin_default and not opts["q"]:
            print("Reading from stdin", file=stderr)
        source = _Input(stdin, seekable=False)
        return _loop(source, plan, fields, opts, order, host, stdout)
    try:
        f = open(plan.file, "rb")  # noqa: SIM115
    except OSError as e:
        raise UsageError(f"can't read {plan.file}: {e.strerror}") from None
    with f:
        return _loop(_Input(f, seekable=True), plan, fields, opts, order, host, stdout)


def _loop(source: _Input, plan, fields, opts, order, host, stdout) -> int:
    if plan.head and not source.seek(plan.head):
        raise UsageError("End of file while seeking past header")
    newline = not (opts["u"] or opts["b"] or opts["s"])
    record, lines = plan.start, 0
    while True:
        if not source.seek(record * plan.size + plan.head):
            break
        data = source.read(plan.size)
        if len(data) != plan.size:
            break
        out = bytearray()
        if opts["l"]:
            out += f"{lines} ".encode()
        if opts["n"]:
            out += f"{record} ".encode()
        if opts["m"]:
            out += f"{source.pos} ".encode()
        out += render(data, fields, order=order, host=host, fast_binary=opts["b"])
        if newline:
            out += b"\n"
        stdout.write(out)
        source.pos += plan.size
        record += plan.skip + 1
        lines += 1
        if plan.stop >= 0 and record > plan.stop:
            break
    stdout.flush()
    return 0

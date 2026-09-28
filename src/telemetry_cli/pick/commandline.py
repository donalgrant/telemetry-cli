"""Reading a pick command line.

pick doesn't parse its arguments one by one. Like the Perl original, it joins
them into one string and removes pieces in this order: options (``-nlr``),
numeric parameters (``start=5``, ``head=4z``), word parameters (``file=...``,
``sym=...``), then expands symbols from a symbol file. What is left is an
optional file name, the record size, and the field requests. This is why
parameters can go anywhere on the command line.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .._perl import truthy
from .fields import DTYPES, NBYTES, parse_size

OPTIONS = "mnblqrsu"
NUM_PARAMS = "start|head|stop|skip|nrecs|every|length|size|header|rec"
WORD_PARAMS = "file|filename|sym|symFile|symTable"
MAX_SYMBOL_EXPANSIONS = 100_000


class UsageError(ValueError):
    """A problem with the command line. ``topics`` names help to suggest."""

    def __init__(self, message: str, topics: str = ""):
        super().__init__(message)
        self.topics = topics


@dataclass
class Command:
    opts: dict[str, bool]
    params: dict[str, int | str | None]
    text: str  # what's left after options, parameters and symbols are removed
    symbols: dict[str, str] = field(default_factory=dict)
    symbol_file: str | None = None
    order: str | None = None  # order=big|little, if given


def parse_options(s: str) -> tuple[str, dict[str, bool]]:
    opts = dict.fromkeys(OPTIONS, False)
    while m := re.search(r"\s([-]([a-zA-Z]+))", s):
        tag, name = m.group(1), m.group(2)
        for k in OPTIONS:
            if k in name:
                opts[k] = True
                name = name.replace(k, "")
        if name:
            raise UsageError(f"Unrecognized option-->{name}<--", "o")
        s = s.replace(tag, "", 1)
    return s, opts


def parse_params(s: str) -> tuple[str, dict]:
    params: dict[str, int | str | None] = {}
    num = re.compile(rf"(({NUM_PARAMS})\s*=\s*(\d+)([{DTYPES}]?))", re.IGNORECASE)
    while m := num.search(s):
        whole, key, value, unit = m.groups()
        s = s[: m.start()] + s[m.end() :]
        params[key] = int(value) * (NBYTES[unit] if unit else 1)
    word = re.compile(rf"(({WORD_PARAMS})\s*=\s*(\S+))", re.IGNORECASE)
    while m := word.search(s):
        s = s[: m.start()] + s[m.end() :]
        params[m.group(2)] = m.group(3)
    return s, params


def parse_order(s: str) -> tuple[str, str | None]:
    """The order=big|little parameter (new in the Python version)."""
    m = re.search(r"(?<!\S)order\s*=\s*(\S+)", s)
    if not m:
        return s, None
    value = m.group(1).lower()
    if value not in ("big", "little", "native"):
        raise UsageError(f"order must be big, little or native, not {m.group(1)!r}", "p")
    return s[: m.start()] + s[m.end() :], value


def find_symbol_file(name: str) -> Path:
    if os.path.exists(name):
        return Path(name)
    path = os.environ.get("PICKPATH", "") + "/" + name
    if os.path.exists(path):
        return Path(path)
    bundled = resources.files("telemetry_cli.pick") / "symbols" / name
    if "/" not in name and bundled.is_file():
        return Path(str(bundled))
    raise UsageError(f"Couldn't find symbol table-->{path}<--", "q")


def read_symbols(path: Path) -> dict[str, str]:
    symbols: dict[str, str] = {}
    for line in path.read_text(encoding="latin-1").split("\n"):
        line = re.sub(r";.*", "", line)
        m = re.search(r"(\S+)\s*=\s*(.+)", line)
        if m and truthy(m.group(1)) and truthy(m.group(2)):
            symbols[m.group(1)] = m.group(2)
    return symbols


def expand_symbols(s: str, symbols: dict[str, str]) -> str:
    """Replace symbol names with their definitions, repeatedly, as whole words.

    Names match without regard to case, but the replacement is looked up by
    the text as written, so a name typed in the wrong case expands to nothing
    (as in the Perl).
    """
    if not symbols:
        return s
    try:
        pattern = re.compile(r"\b(" + "|".join(symbols) + r")\b", re.IGNORECASE)
    except re.error as e:
        raise UsageError(f"can't use the symbol names in this table: {e}", "q") from None
    for _ in range(MAX_SYMBOL_EXPANSIONS):
        m = pattern.search(s)
        if not m:
            return s
        s = s[: m.start()] + symbols.get(m.group(1), "") + s[m.end() :]
    raise UsageError("symbol definitions refer to themselves without end", "q")


def parse(argv: list[str]) -> Command:
    s = " ".join(argv)
    s, opts = parse_options(s)
    s, params = parse_params(s)
    s, order = parse_order(s)
    if "=" in s:
        raise UsageError(f"Unexpected '=' in command line after parsing parms:\n     {s}", "p")
    cmd = Command(opts=opts, params=params, text=s, order=order)
    for key in ("symTable", "symFile"):
        if truthy(params.get(key)) and not truthy(params.get("sym")):
            params["sym"] = params[key]
            break
    if truthy(params.get("sym")):
        path = find_symbol_file(str(params["sym"]))
        cmd.symbol_file = str(params["sym"]) if os.path.exists(str(params["sym"])) else str(path)
        cmd.symbols = read_symbols(path)
        cmd.text = expand_symbols(cmd.text, cmd.symbols)
        for key in ("head", "size", "length"):
            if key in cmd.symbols:
                m = re.search(rf"(\d+)([{DTYPES}]?)", cmd.symbols[key])
                params[key] = int(m.group(1)) * NBYTES.get(m.group(2) or "b", 1) if m else None
    return cmd


def wants_help(text: str) -> bool:
    return "?" in text or not truthy(text) or "help" in text


@dataclass
class Plan:
    """Where to read and which records, after the file name and size are found."""

    file: str
    size: int
    head: int
    start: int
    stop: int
    skip: int
    fields_text: str
    from_stdin_default: bool


def resolve(cmd: Command) -> Plan:
    params = cmd.params
    s = cmd.text.lstrip()
    args = re.split(r"\s", s) if s else []
    while args and args[-1] == "":  # Perl's split drops trailing empty fields
        args.pop()
    file = params.get("file")
    default_stdin = False
    if not truthy(file):
        if args and args[0] and os.path.exists(args[0]):
            file = args.pop(0)
            s = s.replace(file, "", 1)
        else:
            file = "-"
            default_stdin = True
    if "rec" in params:
        params["start"] = params["stop"] = params["rec"]
    head = params.get("head") or params.get("header") or 0
    size = params.get("size") or params.get("length")
    if not size:
        first = args[0] if args else ""
        size = parse_size(first)
        if size is None:
            raise UsageError(f"Can't find record size; looking at {first}")
        s = s.replace(first, "", 1)
    skip = params.get("skip")
    if skip is None:
        skip = params["every"] - 1 if "every" in params else 0
        if skip < 0:  # the Perl reread the same record forever
            raise UsageError("every must be at least 1", "p")
    if int(size) <= 0:  # the Perl printed empty records forever
        raise UsageError("the record size must be at least 1 byte", "p")
    start, stop, nrecs = params.get("start"), params.get("stop"), params.get("nrecs")
    if start is None or stop is None:
        if start is not None:
            stop = start + nrecs - 1 if nrecs is not None else -1
        elif stop is not None:
            start = stop - nrecs + 1 if nrecs is not None else 0
        elif nrecs is not None:
            start, stop = 0, nrecs - 1
        else:
            start, stop = 0, -1
    return Plan(
        file=str(file),
        size=int(size),
        head=int(head),
        start=int(start),
        stop=int(stop),
        skip=int(skip),
        fields_text=s,
        from_stdin_default=default_stdin,
    )

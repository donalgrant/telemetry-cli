"""Command-line options as Perl's Getopt::Long read them (with its default settings).

recs, recl and tgen used Getopt::Long, so their options behave like this:

- an option starts with one or two dashes: ``-mml 4``, ``--mml=4``;
- names are case-insensitive and can be shortened to any unique prefix
  (``-ma`` for ``-max_reclen``);
- a value comes after ``=`` or as the next argument, even one starting with a
  dash (``-e -r`` sets ``e`` to ``-r``);
- options and other arguments can be mixed; ``--`` ends the options, and a
  lone ``-`` is an argument.

Specs use Getopt::Long's syntax: ``"name|alias"`` for a flag, and ``=i``,
``=f`` or ``=s`` for an integer, float or string value.

Unlike the Perl tools, which printed a warning and carried on, a bad option is
an error here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(?=\d|\.\d)\d*(\.\d*)?([eE][-+]?\d+)?$")


class OptionError(ValueError):
    pass


@dataclass
class _Spec:
    key: str  # the first name, used as the result key
    names: list[str]
    kind: str | None  # None (a flag), "i", "f" or "s"


def _parse_specs(specs: list[str]) -> list[_Spec]:
    out = []
    for spec in specs:
        m = re.fullmatch(r"([\w|]+)(?:=([ifs]))?", spec)
        if not m:
            raise ValueError(f"bad option spec {spec!r}")
        names = m.group(1).split("|")
        out.append(_Spec(names[0], names, m.group(2)))
    return out


def getoptions(argv: list[str], specs: list[str]) -> tuple[dict, list[str]]:
    """Parse argv. Returns (options by their first name, remaining arguments)."""
    table = _parse_specs(specs)
    opts: dict = {}
    args: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        i += 1
        if a == "--":
            args += argv[i:]
            break
        if not a.startswith("-") or a == "-":
            args.append(a)
            continue
        body = a[2:] if a.startswith("--") else a[1:]
        name, eq, value = body.partition("=")
        spec, name = _find(table, name)
        if spec.kind is None:
            if eq:
                raise OptionError(f"Option {name} does not take an argument")
            opts[spec.key] = 1
            continue
        if not eq:
            if i >= len(argv):
                raise OptionError(f"Option {name} requires an argument")
            value = argv[i]
            i += 1
        elif value == "":
            raise OptionError(f"Option {name} requires an argument")
        opts[spec.key] = _convert(spec, name, value)
    return opts, args


def _find(table: list[_Spec], name: str) -> tuple[_Spec, str]:
    """The option a (possibly shortened) name refers to, and its full name."""
    low = name.lower()
    for s in table:
        for n in s.names:
            if n.lower() == low:
                return s, n
    matches: dict[str, tuple[_Spec, str]] = {}
    for s in table:
        for n in s.names:
            if n.lower().startswith(low) and low:
                matches.setdefault(s.key, (s, n))
    if len(matches) == 1:
        return next(iter(matches.values()))
    if not matches:
        raise OptionError(f"Unknown option: {low}")
    names = ", ".join(sorted(n for _, n in matches.values()))
    raise OptionError(f"Option {name} is ambiguous ({names})")


def _convert(spec: _Spec, name: str, value: str):
    if spec.kind == "i":
        if not _INT.match(value):
            raise OptionError(f'Value "{value}" invalid for option {name} (number expected)')
        return int(value)
    if spec.kind == "f":
        if not _FLOAT.match(value):
            raise OptionError(f'Value "{value}" invalid for option {name} (real number expected)')
        return float(value)
    return value

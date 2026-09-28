"""Reading tgen command files.

A command file has three kinds of lines:

- comments: lines starting with ``#``, ``!`` or ``;`` in the first column;
- item specifications, with at least four `` # `` separators (a ``#`` with
  white space on both sides)::

      name # offset # trigger # type # value

- statements, run once before any record is generated.

A line ending in a backslash continues on the next line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SEPARATOR = re.compile(r"\s+[#]\s+")


@dataclass
class Item:
    name: str
    offset: str
    trigger: str
    type: str
    value: str
    line: int  # where the specification starts in the file


@dataclass
class Statement:
    code: str
    line: int


def logical_lines(text: str):
    """(line number, text) of each logical line, with continuations joined."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    i = 0
    while i < len(lines):
        start = i + 1
        line = lines[i]
        i += 1
        while line.endswith("\\"):
            line = line[:-1]
            if i < len(lines):
                line += lines[i]
                i += 1
        yield start, line


def parse(text: str) -> tuple[list[Item], list[Statement]]:
    items, statements = [], []
    for n, line in logical_lines(text):
        if line[:1] in ("#", "!", ";"):
            continue
        if len(SEPARATOR.findall(line)) >= 4:
            fields = [f.strip() for f in SEPARATOR.split(line)]
            items.append(Item(*fields[:5], line=n))  # further fields are ignored
        elif line.strip():
            statements.append(Statement(line.strip(), n))
    return items, statements

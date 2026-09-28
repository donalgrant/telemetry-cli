"""pick's field-request language: data types, print requests, moves and groups.

A print request is ``N type Offset :bitOffset:nBits formats`` (e.g. ``4d0+30``,
``w5:1:7bdx``); a move is ``(+|-)N type`` (e.g. ``+5z``); and requests can be
grouped with brackets and repeated (``20[ f +99f i -100f ]``). See
``pick ?r``, ``pick ?m`` and ``pick ?g``.

This follows the Perl original closely, including how groups are rewritten
and how the current position may run past either end of the record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .._perl import truthy

DTYPES = "SAbcswuidfzZ"
PFORMS = "udxnsgGoMPRIDbSAcU"

SIZE_MATCH = re.compile(rf"^((\d+)([{DTYPES}])?)$")
DATA_MATCH = re.compile(
    rf"(^(\d+)?([{DTYPES}])((\d+)([+-]\d+)?)?(:(\d+)(?::(\d+))?)?([{PFORMS}]+)?$)"
)
MOVE_MATCH = re.compile(rf"((^[+-]\d+)([{DTYPES}])?$)")

# bytes per item of each data type
NBYTES = {"S": 1, "A": 1, "b": 1, "c": 1, "s": 2, "w": 2}
NBYTES |= {"u": 4, "i": 4, "f": 4, "d": 8, "z": 8, "Z": 16}

# default print formats
DEFAULT_FORMAT = {"b": "x", "c": "c", "s": "d", "w": "u", "S": "S", "A": "A"}
DEFAULT_FORMAT |= {"u": "u", "i": "d", "f": "g", "d": "g", "z": "RI", "Z": "RI"}

# struct codes used to unpack each type (for complex types: one component)
STRUCT = {"b": "B", "s": "h", "w": "H", "u": "I", "i": "i", "f": "f", "d": "d"}
STRUCT |= {"z": "f", "Z": "d"}


class FieldError(ValueError):
    """A field request pick can't use."""


@dataclass
class Field:
    """One print request, with its position resolved."""

    src: str  # the request as written
    pos: int  # byte position of the first item in the record (may be negative)
    t: str  # data type letter
    m: int  # number of items
    formats: str  # print formats
    nb: int  # bytes per item
    first_bit: int  # bit offset (0 when none given)
    nbits: int  # number of bits used
    mask: int
    bits: bool  # was a bit offset given?

    @property
    def out_bytes(self) -> int:
        """Bytes of output per item for bit-limited formats (Perl's $nb)."""
        return (7 + self.nbits) // 8


def parse_size(token: str) -> int | None:
    """A record size like ``256``, ``21d`` or ``4z``, in bytes; None if it isn't one."""
    m = SIZE_MATCH.search(token)
    if not m:
        return None
    return int(m.group(2)) * NBYTES[m.group(3) or "b"]


class Parser:
    """Parse field requests, tracking the current position as the Perl did."""

    def __init__(self, record_size: int, *, binary: bool = False):
        self.size = record_size
        self.binary = binary  # -u: print everything as 'U'
        self.pos = 0
        self.fields: list[Field] = []

    def field(self, f: str) -> None:
        m = MOVE_MATCH.search(f)
        if m:
            t = m.group(3) or "b"
            self.pos += int(m.group(2)) * NBYTES[t]
            return
        m = DATA_MATCH.search(f)
        if not m:
            raise FieldError(f"{f}:  Matched neither a move nor a data request")
        _, mult, t, offset, n, byte_off, bitspec, first_bit, nbits, formats = m.groups()
        mult = int(mult) if truthy(mult) else 1  # Perl: $m ||= 1, so "0i" is "i" ("00i" is not)
        formats = formats or DEFAULT_FORMAT[t]
        nb = NBYTES[t]
        if offset:
            o = int(byte_off) if byte_off else 0
            cpos = nb * int(n) + o
            self.pos = nb * (int(n) + mult) + o
        else:
            cpos = self.pos
            self.pos += nb * mult
        if self.pos > self.size:
            raise FieldError("data requested beyond record length")
        nbits = int(nbits) if nbits is not None else 8 * nb
        # Perl built the mask one bit at a time in a 64-bit integer; 0 bits gave 1.
        mask = (1 << min(max(nbits, 1), 64)) - 1
        if self.binary:
            formats = "U"
        self.fields.append(
            Field(
                src=f,
                pos=cpos,
                t=t,
                m=mult,
                formats=formats,
                nb=nb,
                first_bit=int(first_bit) if first_bit else 0,
                nbits=nbits,
                mask=mask,
                bits=bitspec is not None,
            )
        )

    def token(self, t: str, groups: list[str]) -> None:
        t = t.replace("\\", "")
        m = re.search(r"(\d*)(Y)(\d+)", t)
        if not m:
            self.field(t)
            return
        repeat = int(m.group(1)) if truthy(m.group(1)) else 1
        k = int(m.group(3))
        body = groups[k] if k < len(groups) else ""
        for _ in range(repeat):
            for sub in body.split():
                self.token(sub, groups)


def extract_groups(text: str) -> tuple[str, list[str]]:
    """Replace each innermost ``[ ... ]`` with ``Y<n>`` until none are left.

    Returns the rewritten text and the group bodies. Like the Perl, the body is
    used as a regular expression (with + and - escaped) to find the group again.
    """
    groups: list[str] = []
    while m := re.search(r"\[([^\[\]]*)\]", text):
        body = re.sub(r"([+-])", r"\\\1", m.group(1))
        try:
            pattern = re.compile(r"\[" + body + r"\]")
        except re.error as e:
            raise FieldError(f"can't parse group [{m.group(1)}]: {e}") from None
        new = pattern.sub(f"Y{len(groups)} ", text, count=1)
        if new == text:  # the Perl looped forever here
            raise FieldError(f"can't parse group [{m.group(1)}]")
        text = new
        groups.append(body)
    return text, groups


def parse_fields(text: str, record_size: int, *, binary: bool = False) -> list[Field]:
    """Parse the field-request part of a pick command line."""
    text, groups = extract_groups(text)
    p = Parser(record_size, binary=binary)
    for tok in text.split():
        p.token(tok, groups)
    return p.fields

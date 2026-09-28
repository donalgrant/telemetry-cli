"""A subset of Perl's pack/unpack, built on struct.

tgen command files give their field types as Perl pack templates ('L', 'a10',
'C256', 'd2'), and pick's data types map onto the same letters. This module
reproduces Perl's behavior for the letters those tools use:

    c C       8-bit signed / unsigned
    s S       16-bit signed / unsigned
    l L i I   32-bit signed / unsigned
    q Q       64-bit signed / unsigned
    n N       16 / 32-bit unsigned, big-endian
    v V       16 / 32-bit unsigned, little-endian
    f d       single / double float
    a A Z     byte strings: null-padded, space-padded, null-terminated
    x         a null byte

Each letter can take a repeat count (``C4``) or ``*``, and the integer and
float letters wider than a byte take a ``<`` or ``>`` byte-order modifier. Without a modifier
the byte order is native, as in Perl.

As in Perl, integers are truncated toward zero and wrap to the field width, so
``pack('C', 257)`` is ``b'\\x01'`` and ``pack('L', -1)`` is ``b'\\xff\\xff\\xff\\xff'``.
Missing values pack as zero (or as empty strings for a/A/Z).
"""

from __future__ import annotations

import math
import re
import struct
import sys

from ._perl import numify as _to_number

# letter -> (struct code, size in bytes, signed?)  for the integer letters
_INTS = {
    "c": ("b", 1, True),
    "C": ("B", 1, False),
    "s": ("h", 2, True),
    "S": ("H", 2, False),
    "l": ("i", 4, True),
    "L": ("I", 4, False),
    "i": ("i", 4, True),
    "I": ("I", 4, False),
    "q": ("q", 8, True),
    "Q": ("Q", 8, False),
    "n": ("H", 2, False),
    "N": ("I", 4, False),
    "v": ("H", 2, False),
    "V": ("I", 4, False),
}
_FIXED_ORDER = {"n": ">", "N": ">", "v": "<", "V": "<"}
_FLOATS = {"f": "f", "d": "d"}
_STRINGS = "aAZ"

_ITEM = re.compile(r"\s*([cCsSlLiIqQnNvVfdaAZx])([<>])?(\*|\d+)?\s*")
NATIVE = "<" if sys.byteorder == "little" else ">"


class PackError(ValueError):
    """A template this module can't handle."""


def parse(template: str) -> list[tuple[str, str, int | None]]:
    """Split a template into (letter, byte order, count) items.

    The count is None when omitted and -1 for ``*``.
    """
    items = []
    pos = 0
    while pos < len(template):
        m = _ITEM.match(template, pos)
        if not m or m.end() == pos:
            if template[pos:].strip() == "":
                break
            raise PackError(f"unsupported pack template {template!r} at {template[pos:]!r}")
        letter, order, count = m.groups()
        if order and (letter in _STRINGS or letter in _FIXED_ORDER or letter in "cCx"):
            raise PackError(f"'{order}' is not allowed after '{letter}' in {template!r}")
        order = _FIXED_ORDER.get(letter, order or NATIVE)
        n = None if count is None else (-1 if count == "*" else int(count))
        items.append((letter, order, n))
        pos = m.end()
    return items


def _to_int(v, size: int, signed: bool) -> int:
    x = _to_number(v)
    if isinstance(x, float):
        x = 0 if math.isnan(x) else (int(x) if math.isfinite(x) else (-1 if x < 0 else 2**64 - 1))
    bits = 8 * size
    x &= (1 << bits) - 1
    if signed and x >= 1 << (bits - 1):
        x -= 1 << bits
    return x


def _to_bytes(v) -> bytes:
    if v is None:
        return b""
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).encode("latin-1")


def pack(template: str, *values) -> bytes:
    """Pack values like Perl's pack(template, values)."""
    out = bytearray()
    vals = list(values)
    i = 0

    def take():
        nonlocal i
        v = vals[i] if i < len(vals) else None
        i += 1
        return v

    for letter, order, count in parse(template):
        if letter == "x":
            out += b"\0" * (1 if count is None else max(count, 0))
        elif letter in _STRINGS:
            s = _to_bytes(take())
            if count == -1:
                out += s + (b"\0" if letter == "Z" else b"")
            else:
                n = 1 if count is None else count
                pad = b" " if letter == "A" else b"\0"
                if letter == "Z" and n > 0:
                    s = s[: n - 1]
                out += s[:n].ljust(n, pad)
        else:
            reps = len(vals) - i if count == -1 else (1 if count is None else count)
            for _ in range(max(reps, 0)):
                v = take()
                if letter in _FLOATS:
                    x = float(_to_number(0 if v is None else v))
                    out += struct.pack(order + _FLOATS[letter], x)
                else:
                    code, size, signed = _INTS[letter]
                    out += struct.pack(order + code, _to_int(0 if v is None else v, size, signed))
    return bytes(out)


def unpack(template: str, data: bytes) -> tuple:
    """Unpack data like Perl's unpack(template, data).

    Strings come back as bytes. Like Perl, unpacking stops quietly when the
    data run out.
    """
    out = []
    pos = 0
    for letter, order, count in parse(template):
        if letter == "x":
            pos += 1 if count is None else max(count, 0)
        elif letter in _STRINGS:
            n = len(data) - pos if count == -1 else (1 if count is None else count)
            s = data[pos : pos + n]
            pos += len(s)
            if letter == "A":
                s = s.rstrip(b" \0\t\n\r\f")
            elif letter == "Z":
                s = s.split(b"\0", 1)[0]
            out.append(s)
        else:
            if letter in _FLOATS:
                fmt, size = order + _FLOATS[letter], struct.calcsize(_FLOATS[letter])
            else:
                code, size, _ = _INTS[letter]
                fmt = order + code
            reps = (len(data) - pos) // size if count == -1 else (1 if count is None else count)
            for _ in range(reps):
                if pos + size > len(data):
                    break
                out.append(struct.unpack_from(fmt, data, pos)[0])
                pos += size
    return tuple(out)


def calcsize(template: str) -> int:
    """Bytes produced by a template with fixed counts (no ``*``)."""
    return len(pack(template))

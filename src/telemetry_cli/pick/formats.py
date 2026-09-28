"""Printing pick's fields: the print formats (``pick ?f``).

The output matches the Perl original's, including its spacing: most formats
are followed by a space, and x, o, d and u on byte types print another space
after each byte.

Byte order: each item is first put into big-endian order (each half separately
for complex types), and then printed the way the Perl printed on the
big-endian machines it was written for. So the output doesn't depend on the
machine pick runs on, only on the data's byte order.
"""

from __future__ import annotations

import math
import struct

from .._perl import multiply, sprintf, substr
from .fields import STRUCT, Field

PI = 3.14159265359  # the Perl original's value, used for the D format

FORMAT = {"u": "%u", "d": "%d", "x": "%02x", "o": "%03o", "g": "%g", "G": "%25.18g"}
FORMAT |= {"M": "%g", "P": "%g", "R": "%g", "I": "%g", "D": "%g"}

# names of the ASCII control characters, 0..31
ASCII_NAMES = (  # noqa: SIM905 (a list literal would take 32 lines)
    "nul soh stx etx eot enq ack bel bs ht nl vt np cr so si "
    "dle dc1 dc2 dc3 dc4 nak syn etb can em sub esc fs gs rs us"
).split()


class FormatError(ValueError):
    """A print format that can't be used with a field's data type."""


def reversed_order(t: str, nb: int) -> list[int]:
    """Byte indices that reverse an item's byte order (each half, for complex)."""
    if t in "zZ":
        half = nb // 2
        return [*range(half - 1, -1, -1), *range(nb - 1, half - 1, -1)]
    return list(range(nb - 1, -1, -1))


def reorder(data: bytes, order: list[int]) -> bytes:
    """data rearranged by index; missing bytes become zero (as in the Perl)."""
    return bytes(data[i] if i < len(data) else 0 for i in order)


def _index(seq, i):
    """Perl's $array[i]: negative indices count from the end; out of range is undef."""
    if -len(seq) <= i < len(seq):
        return seq[i]
    return None


def _value(d: bytes, t: str):
    """The first item of type t in d (big-endian), as Perl's unpack gave it."""
    if t in "cSA":  # unpacked as a one-character string
        return d[:1].decode("latin-1")
    code = STRUCT[t]
    size = struct.calcsize(code)
    return struct.unpack(">" + code, d[:size])[0] if len(d) >= size else None


def _bit_field(d0: bytes, f: Field) -> bytes:
    """Apply a field's bit offset and mask, as the Perl's "slow" path did."""
    nb, out = f.nb, f.out_bytes
    r = [d0[j] if j < len(d0) else 0 for j in range(nb)]
    if nb > 4:  # bit fields aren't available for these types
        return bytes(r[j] if j < nb else 0 for j in range(out))
    u = 0
    for x in r:
        u = (u << 8) | x
    u = (u >> f.first_bit) & f.mask
    d = []
    for _ in range(out):
        d.append(u & 0xFF)
        u >>= 8
    d += [0] * (nb - out)
    return bytes(reversed(d))


def render(data: bytes, fields: list[Field], *, order: str, host: str, fast_binary: bool) -> bytes:
    """The output for one record."""
    out = bytearray()
    for f in fields:
        if fast_binary:  # -b: the bytes as they are
            out += substr(data, f.pos, f.nb * f.m)
            continue
        rev = reversed_order(f.t, f.nb)
        for i in range(f.m):
            d0 = substr(data, f.pos + i * f.nb, f.nb * f.m)
            item = d0[: f.nb]
            full = len(item) == f.nb
            # big-endian view of the item
            canon = reorder(item, rev) if order == "little" and full else d0
            nbytes = f.out_bytes
            for p in f.formats:
                d = _bit_field(canon, f) if f.bits else canon
                if p == "U":
                    out += _unformatted(d, d0, f, order=order, host=host)
                elif f.t in "zZ":
                    out += _complex(d, f, p).encode()
                else:
                    out += _scalar(d, f, p, nbytes).encode("latin-1")
                if p not in "SAUn":
                    out += b" "
    return bytes(out)


def _unformatted(d: bytes, d0: bytes, f: Field, *, order: str, host: str) -> bytes:
    """The 'U' format: the item's bytes, in the host's byte order."""
    nbytes = f.out_bytes
    if f.bits and f.nb <= 4:
        # the masked value's low bytes (the Perl wrote the wrong end of them)
        value = d[len(d) - nbytes :]
        return value[::-1] if host == "little" else value
    if f.bits:
        return d[:nbytes][::-1] if host == "little" and nbytes == f.nb else d[:nbytes]
    if order == host:
        return d0[:nbytes]
    return reorder(d0[: f.nb], reversed_order(f.t, f.nb))[:nbytes]


def _complex(d: bytes, f: Field, p: str) -> str:
    code = STRUCT[f.t]
    size = struct.calcsize(code)
    parts = [struct.unpack_from(">" + code, d, k * size)[0] for k in range(min(2, len(d) // size))]
    re_, im = (parts + [0.0, 0.0])[:2]
    if p == "R":
        return sprintf("%g", re_)
    if p == "I":
        return sprintf("%g", im)
    if p == "g":  # documented as RI; the Perl rejected it
        return sprintf("%g", re_) + " " + sprintf("%g", im)
    if p == "M":
        return sprintf("%g", math.sqrt(re_ * re_ + im * im))
    if p == "P":
        return sprintf("%g", math.atan2(im, re_))
    if p == "D":
        return sprintf("%g", multiply(180.0, math.atan2(im, re_)) / PI)
    raise FormatError(f"Unrecognized print format for complex type: {p}")


def _scalar(d: bytes, f: Field, p: str, nbytes: int) -> str:
    t, nb = f.t, f.nb
    if p in "cSA":
        text = []
        for k in range(nb):
            ch = d[k : k + 1]
            o = ch[0] if ch else 0
            if ch and 0x20 <= o <= 0x7E:
                text.append(chr(o))
            elif o < 128:
                if p == "c":
                    text.append(ASCII_NAMES[o] if o < 32 else "del")
                elif p == "S":
                    text.append(f"({ASCII_NAMES[o] if o < 32 else 'del'})")
            elif p == "c":
                text.append(f"{o:o}")
            elif p == "S":
                text.append(f"({o:o})")
        return "".join(text)
    if p in "udgG" and t not in "cb":
        return sprintf(FORMAT[p], _value(d, t))
    if p == "D":
        return sprintf("%g", multiply(_value(d, t), 180.0) / PI)
    if p == "n":
        return "\n"
    if p == "s":
        return ""
    if p in "xodu":
        k = list(d[:nb])
        return "".join(sprintf(FORMAT[p], _index(k, j)) + " " for j in range(nb - nbytes, nb))
    if p == "b":
        k = list(reversed(d[:nb]))
        bout: list[int] = []
        for j in range(nbytes):
            x = _index(k, j) or 0
            for _ in range(8):
                bout.insert(0, x & 1)
                x >>= 1
        n = len(bout)
        text = []
        for bb in range(n - f.nbits, n):
            text.append(str(_index(bout, bb) or 0))
            if (n - (bb + 1)) % 4 == 0:
                text.append(" ")
        return "".join(text)
    raise FormatError(f"unrecognized print format-->{p}<--")

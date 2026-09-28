"""Small pieces of Perl semantics that the ported tools' output depends on.

- numify: Perl's numeric value of a string (leading number, else 0)
- to_iv / to_uv: Perl's conversion of a number to a signed / unsigned 64-bit
  integer, as used by printf's %d, %u, %x and %o
- sprintf: printf for the conversions pick uses, including Perl's spelling of
  infinities and NaN ("Inf", "-Inf", "NaN")
- substr: Perl's substr, which counts negative offsets from the end
- truthy: Perl's idea of a true string ("" and "0" are false)
"""

from __future__ import annotations

import math
import re

_NUMBER = re.compile(
    r"\s*([+-]?)(?:(inf(?:inity)?|nan)|(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?))",
    re.IGNORECASE,
)
IV_MIN, IV_MAX, UV_MAX = -(2**63), 2**63 - 1, 2**64 - 1


def numify(v) -> int | float:
    """Perl's numeric value of v. None (undef) and non-numeric strings are 0.

    Handles ordinary numeric strings, "inf"/"nan", and Perl's odd reading of a
    leading sign followed by another signed number ("--1" is 1, "- 1" is -1).
    """
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, (bytes, bytearray)):
        v = bytes(v).decode("latin-1")
    m = _NUMBER.match(v)
    if m:
        return _number(m)
    m = re.match(r"\s*([+-])\s*", v)
    if m:
        inner = _NUMBER.match(v, m.end())
        if inner and not inner.group(0)[:1].isspace():
            x = _number(inner)
            return -x if m.group(1) == "-" else x
    return 0


def _number(m: re.Match) -> int | float:
    sign, special, digits = m.groups()
    if special:
        x = math.inf if special[0] in "iI" else math.nan
    elif any(c in digits for c in ".eE"):
        x = float(digits)
    else:
        x = int(digits)
    return -x if sign == "-" else x


def to_iv(v) -> int:
    """Perl's IV (signed 64-bit) value of a finite number."""
    x = numify(v)
    if isinstance(x, int):
        if x < IV_MIN:
            return IV_MIN
        return x if x <= IV_MAX else min(x, UV_MAX) - 2**64
    if x < IV_MIN:
        return IV_MIN
    if x < 2**63:
        return int(x)
    uv = UV_MAX if x >= 2**64 else int(x)  # Perl goes through UV here
    return uv - 2**64


def to_uv(v) -> int:
    """Perl's UV (unsigned 64-bit) value of a finite number."""
    x = numify(v)
    if isinstance(x, int):
        return min(x, UV_MAX) if x >= 0 else max(x, IV_MIN) & UV_MAX
    if x < 0:
        return to_iv(x) & UV_MAX
    return UV_MAX if x >= 2**64 else int(x)


def multiply(a, b) -> int | float:
    """Perl's a * b: integer arithmetic when both are integer-valued (so -0.0 * 180 is 0)."""

    def as_int(x):
        x = numify(x)
        if isinstance(x, float) and x.is_integer() and IV_MIN <= x <= UV_MAX:
            return int(x)
        return x

    a, b = as_int(a), as_int(b)
    if isinstance(a, int) and isinstance(b, int) and IV_MIN <= a * b <= UV_MAX:
        return a * b
    return float(a) * float(b)


def _special(x) -> str | None:
    """Perl's text for an infinity or NaN, else None."""
    if isinstance(x, float) and not math.isfinite(x):
        if math.isnan(x):
            return "NaN"
        return "Inf" if x > 0 else "-Inf"
    return None


_CONV = re.compile(r"%(-?)(0?)(\d*)(?:\.(\d+))?([dugGxosc%])")


def sprintf(fmt: str, *args) -> str:
    """Perl's sprintf for the flag/width/precision/conversion subset pick uses."""
    it = iter(args)

    def conv(m: re.Match) -> str:
        left, zero, width, prec, c = m.groups()
        if c == "%":
            return "%"
        v = next(it, None)
        x = numify(v) if c != "s" else v
        text = _special(x) if c != "s" else None
        if text is not None:
            w = int(width or 0)
            return text.ljust(w) if left else text.rjust(w)
        spec = f"%{left}{zero}{width}" + (f".{prec}" if prec is not None else "")
        if c == "d":
            return (spec + "d") % to_iv(x)
        if c == "u":
            return (spec + "d") % to_uv(x)
        if c in "xo":
            return (spec + c) % to_uv(x)
        if c in "gG":
            return (spec + c) % float(x)
        if c == "c":
            return (spec + "c") % chr(to_iv(x) & 0x10FFFF)
        return (spec + "s") % ("" if v is None else v)

    return _CONV.sub(conv, fmt)


def substr(data: bytes, offset: int, length: int | None = None) -> bytes:
    """Perl's substr(data, offset, length) for non-negative length.

    A negative offset counts from the end; a start before the beginning is
    clipped (so substr("abc", -5, 4) is "ab"). Past the end gives b"".
    """
    n = len(data)
    start = n + offset if offset < 0 else offset
    if start > n:
        return b""
    end = n if length is None else start + max(length, 0)
    return data[max(start, 0) : max(min(end, n), 0)]


def truthy(s) -> bool:
    """Perl truth of a scalar: undef, "", "0" and 0 are false."""
    if s is None:
        return False
    if isinstance(s, str):
        return s not in ("", "0")
    return bool(s)

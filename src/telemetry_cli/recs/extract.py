"""Extracting records from a byte stream by their start and end markers.

This is a close port of the Perl original's three classes: a fixed-size
buffer over the input (BStream), string and regex search in that buffer
(Match_Stream), and the extractor (Extract_Records). The buffer mechanics are
kept as they were, because whether a marker that straddles two buffers is
found depends on them; see the ``mml`` option.

Regexes are Python regexes (on bytes, with ``.`` matching newlines, as the
Perl's ``/s`` did). For the simple patterns recs is used with, they behave
like Perl's.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import BinaryIO

from .._perl import truthy

Finder = Callable[["MatchStream", bytes], tuple[int, int]]


class RecsError(ValueError):
    pass


class BStream:
    """A buffer of up to ``size`` bytes over a binary stream, refilled as it is consumed."""

    def __init__(self, fp: BinaryIO, size: int = 1024):
        self.fp = fp
        self.size = size or 1024  # size=0 is not allowed
        self.data = b""
        self.consumed = 0  # net bytes taken from the front (for spotting endless loops)
        self._add_bytes()

    def _add_bytes(self, offset: int = 0, nbytes: int | None = None) -> int:
        nbytes = self.size if nbytes is None else nbytes
        chunk = self.fp.read(nbytes) if nbytes > 0 else b""
        # Perl read into substr($data, $offset, $size - $offset)
        self.data = self.data[:offset] + chunk + self.data[self.size :]
        return len(chunk)

    def __len__(self) -> int:
        return len(self.data)

    @property
    def full(self) -> bool:
        return self.size <= len(self.data)

    def get(self, n: int | None = None, offset: int = 0) -> bytes | None:
        """n bytes from offset (all by default); None if n or offset is past the end."""
        length = len(self.data)
        n = length if n is None else n
        if n > length or offset > length:
            return None
        n = min(n, length - offset)
        return self.data[offset : offset + n]

    def shift_bytes(self, nbytes: int | None = None) -> bytes:
        """Remove and return up to nbytes from the front, then refill to size."""
        nbytes = self.size if nbytes is None else nbytes
        length = len(self.data)
        nbytes = min(nbytes, length)
        out = self.data[:nbytes]
        self.data = self.data[nbytes:]
        self.consumed += len(out)
        to_add = self.size - (length - nbytes)
        if to_add > 0:
            self._add_bytes(length - nbytes, to_add)
        return out

    def unshift_bytes(self, src: bytes) -> int:
        self.data = src + self.data
        self.consumed -= len(src)
        return len(src)


class MatchStream(BStream):
    def str_find(self, s: bytes) -> tuple[int, int]:
        return self.data.find(s), len(s)

    def reg_find(self, pattern: bytes) -> tuple[int, int]:
        m = _regex(pattern).search(self.data)
        return (m.start(), m.end() - m.start()) if m else (-1, 0)


_REGEX_CACHE: dict[bytes, re.Pattern] = {}


def _regex(pattern: bytes) -> re.Pattern:
    if pattern not in _REGEX_CACHE:
        try:
            _REGEX_CACHE[pattern] = re.compile(pattern, re.DOTALL)
        except re.error as e:
            text = pattern.decode("latin-1")
            raise RecsError(f"can't use the regex {text!r}: {e}") from None
    return _REGEX_CACHE[pattern]


def _perl_substr_from_end(data: bytes, n: int) -> tuple[bytes, bytes]:
    """Perl's (substr($r, -n), substr($r, 0, -n)). With n == 0 that is ($r, "")."""
    if n == 0:
        return data, b""
    if n >= len(data):
        return data, b""
    return data[-n:], data[:-n]


# Option names and defaults, as in the Perl's %OPTION table, except that the
# default fill is a null byte, as documented. (The Perl's default was the
# number 0, which padded records with the character "0".)
DEFAULTS = {
    "fill": b"\0",
    "pad": 0,
    "regex": 1,
    "mml": 0,
    "sp": 0,
    "xbeg": 0,
    "xend": 0,
    "pre": b"",
    "post": b"",
    "reclen": 0,
    "nmin": 0,
    "nmax": 0,
    "bufsiz": 1024,
}


class Extractor:
    """Extract records from ``inp`` and write them to ``out``.

    Options (all optional): fill, pad, regex, mml, sp, xbeg, xend, pre, post,
    reclen, nmin, nmax, bufsiz, with the Perl original's meanings. ``warn`` is
    called with the text of each warning.
    """

    # guards against inputs that made the Perl loop forever
    MAX_STEPS_WITHOUT_PROGRESS = 10_000

    def __init__(
        self,
        inp: BinaryIO,
        out: BinaryIO,
        options: dict | None = None,
        *,
        defaults: dict | None = None,
        warn: Callable[[str], None] = lambda m: None,
    ):
        self.inp, self.out, self.warn = inp, out, warn
        self.o: dict = {}
        self.record = b""
        for k, v in (defaults or DEFAULTS).items():
            self._set(k, v)
        for k, v in (options or {}).items():
            if v is not None:
                self._set(k, v)

    # --- options, with the Perl setters' side effects ---------------------------

    def _set(self, key: str, value) -> None:
        setter = getattr(self, f"set_{key}", None)
        if setter:
            setter(value)
        else:
            self.o[key] = value

    def set_pad(self, v) -> None:
        self.o["pad"] = v
        if truthy(self.o.get("reclen")) and truthy(v):
            self.o["nmin"] = self.o["reclen"]

    def set_nmin(self, v) -> None:
        self.o["nmin"] = v
        if truthy(v) and not truthy(self.o.get("pad")):
            self.o["pad"] = 1

    def set_reclen(self, v) -> None:
        self.o["reclen"] = v
        if self.o.get("mml") is None:
            self.set_mml(DEFAULTS["mml"])
        self._grow_buffer()
        if truthy(v):
            self.o["nmax"] = v
        if truthy(self.o.get("pad")) and truthy(v):
            self.set_nmin(v)

    def set_mml(self, v) -> None:
        self.o["mml"] = v
        if self.o.get("reclen") is None:
            self.set_reclen(DEFAULTS["reclen"])
        self._grow_buffer()

    def _grow_buffer(self) -> None:
        need = 2 * ((self.o.get("reclen") or 0) + (self.o.get("mml") or 0))
        if need > self.o.get("bufsiz", 0):
            self.o["bufsiz"] = need

    # --- the record being built -------------------------------------------------

    def clear_rec(self) -> None:
        self.record = b""

    def add_rec(self, b: bytes) -> None:
        self.record += b

    def trim_rec(self) -> None:
        if len(self.record) > self.o["nmax"]:
            self.record = self.record[: self.o["nmax"]]

    def fill_rec(self) -> None:
        fill = _fill_bytes(self.o["fill"])
        if not fill and len(self.record) < self.o["nmin"]:
            raise RecsError("the fill string is empty, so records can't be padded")
        while len(self.record) < self.o["nmin"]:
            self.add_rec(fill)

    def pop_rec(self, n: int) -> bytes:
        popped, self.record = _perl_substr_from_end(self.record, n)
        return popped

    def dump_rec(self) -> None:
        if truthy(self.o["nmin"]):
            self.fill_rec()
        if truthy(self.o["nmax"]):
            self.trim_rec()
        self.out.write(self.o["pre"] + self.record + self.o["post"])

    def find_in_rec(self, match: bytes, offset: int | None = 0) -> tuple[int, int]:
        offset = offset or 0
        rest = self.record[offset:]
        if truthy(self.o["regex"]):
            m = _regex(match).search(rest)
            if not m:
                return -1, 0
            mb = m.end() - m.start()
            self._check_mml(mb)
            return offset + m.start(), mb
        return offset + rest.find(match), len(match)

    def _check_mml(self, nbytes: int) -> None:
        if nbytes > self.o["mml"]:
            self.warn(f"Matched bytes ({nbytes}) is larger than mml parameter ({self.o['mml']})")

    # --- moving through the stream ---------------------------------------------------

    def _finder(self) -> Finder:
        return MatchStream.reg_find if truthy(self.o["regex"]) else MatchStream.str_find

    def _discard_to_match(self, match: bytes) -> int | None:
        find = self._finder()
        shift = self.M.size - self.o["mml"]
        while True:
            r = find(self.M, match)
            if not (r[0] < 0 and len(self.M)):
                break
            self._check_mml(r[1])
            self.M.shift_bytes(shift)
        if r[0] < 0:
            return None
        self.M.shift_bytes(r[0])
        return r[1]

    def _extract_to_match(self, match: bytes) -> int | None:
        find = self._finder()
        shift = self.M.size - self.o["mml"]
        while True:
            r = find(self.M, match)
            if not (r[0] < 0 and len(self.M)):
                break
            self.add_rec(self.M.shift_bytes(shift))
        if r[0] < 0:
            return None
        self._check_mml(r[1])
        self.add_rec(self.M.shift_bytes(r[0] + r[1]))
        return r[1]

    def _extract_nbytes(self, n: int) -> int:
        """Add n bytes to the record; return how many were missing at the end of input."""
        while n > (length := len(self.M)):
            if not length:
                if not truthy(self.o["pad"]):
                    return n
                self.fill_rec()
                self.trim_rec()
                return 0
            self.add_rec(self.M.shift_bytes())
            n -= length  # (the Perl subtracted the length, even if it shifted less)
        if n > 0:
            self.add_rec(self.M.shift_bytes(n))
        return 0

    # --- the two kinds of extraction -------------------------------------------------

    def match_n(self, match: bytes, reclen: int, mml: int | None = None, max_recs=-1) -> int:
        """Records of reclen bytes, each starting at a match."""
        mml = mml or len(match)
        if mml > self.o["mml"]:
            self.set_mml(mml)
        self.set_reclen(reclen)
        self.M = MatchStream(self.inp, self.o["bufsiz"])
        i, stuck, last = 0, 0, None
        while (i <= max_recs or max_recs < 0) and len(self.M) > 0:
            last, stuck = self._progress(last, stuck)
            mb_start = self._discard_to_match(match)
            if mb_start is None:
                break
            if truthy(self.o["xbeg"]):
                self.M.shift_bytes(mb_start)
            self.clear_rec()
            missing = self._extract_nbytes(self.o["reclen"])
            if truthy(self.o["sp"]):
                rec_offset = 0 if truthy(self.o["xbeg"]) else mb_start
                r = self.find_in_rec(match, rec_offset)
                if r[0] >= rec_offset:
                    # another start marker: put the rest back on the stream
                    self.M.unshift_bytes(self.pop_rec(len(self.record) - r[0]))
                    if not truthy(self.o["pad"]):
                        continue
            if missing and not truthy(self.o["pad"]):
                break  # an incomplete record, and not padding
            self.dump_rec()
            i += 1
        return i

    def match_match(
        self, start: bytes, stop: bytes | None = None, mml: int | None = None, max_recs=-1
    ) -> int:
        """Records from each start marker to the following stop marker."""
        stop = start if stop is None else stop
        mml = mml or max(len(start), len(stop))
        if mml > self.o["mml"]:
            self.set_mml(mml)
        self.M = MatchStream(self.inp, self.o["bufsiz"])
        i, stuck, last = 0, 0, None
        while (i <= max_recs or max_recs < 0) and len(self.M) > 0:
            last, stuck = self._progress(last, stuck)
            mb_start = self._discard_to_match(start)
            if mb_start is None:
                break
            self.clear_rec()
            mb0 = 0
            if truthy(self.o["xbeg"]):
                self.M.shift_bytes(mb_start)
            else:
                mb0 = self._extract_to_match(start)
            mb = self._extract_to_match(stop)
            if truthy(self.o["sp"]):
                r = self.find_in_rec(start, mb0)
                if r[0] >= (mb0 or 0):
                    self.M.unshift_bytes(self.pop_rec(len(self.record) - r[0]))
                    self.dump_rec()  # no stop marker: dump what we have
                    i += 1
                    continue
            if not mb:
                self.clear_rec()  # only complete records
                return i
            if truthy(self.o["xend"]):
                self.pop_rec(mb)
            self.dump_rec()
            i += 1
        return i

    def _progress(self, most, stuck):
        """Stop if many passes in a row consume no new input."""
        if most is not None and self.M.consumed <= most:
            stuck += 1
            if stuck > self.MAX_STEPS_WITHOUT_PROGRESS:
                raise RecsError("the markers match without consuming any input; stopping")
            return most, stuck
        return self.M.consumed, 0

    # Perl-style entry points: str_* use plain strings, reg_* regexes
    def str_n(self, match, reclen, *a):
        self.o["regex"] = 0
        return self.match_n(match, reclen, *a)

    def reg_n(self, match, reclen, *a):
        self.o["regex"] = 1
        return self.match_n(match, reclen, *a)

    def str_str(self, start, stop=None, *a):
        self.o["regex"] = 0
        return self.match_match(start, stop, *a)

    def reg_reg(self, start, stop=None, *a):
        self.o["regex"] = 1
        return self.match_match(start, stop, *a)


def _fill_bytes(fill) -> bytes:
    """The fill as bytes. (A number is its digits, as in Perl: 0 is "0".)"""
    if isinstance(fill, bytes):
        return fill
    if isinstance(fill, str):
        return fill.encode("latin-1")
    return str(fill).encode()

"""The recs Perl script's own test suite (its -test option), ported to pytest.

The Perl tests changed the extractor's defaults as they went, so they run in
order, in one function per class, as they did there.
"""

from __future__ import annotations

import io

import pytest

from telemetry_cli.recs.extract import DEFAULTS, BStream, Extractor, MatchStream


def bstream_checks(B):
    assert len(B) == 5, "BStream length after create"
    assert B.size == 5
    assert B.full
    assert B.get() == b"abcde"
    assert B.get(1) == b"a"
    assert B.get(3, 2) == b"cde"
    assert B.get(6) is None, "Can't request more than BStream length"
    assert B.get(2, 5) == b"", "Request truncated to BStream length"

    assert B.shift_bytes(1) == b"a"
    assert B.get() == b"bcdef"
    assert B.shift_bytes(6) == b"bcdef", "Maximum shift is BStream size"
    assert B.get() == b"ghijk"

    assert B.shift_bytes() == b"ghijk"
    assert len(B) == 2
    assert B.get(2) == b"lm", "Default shift is by length"
    assert B.get(B.size) is None
    assert B.get(1, 3) is None

    B.unshift_bytes(b"xyz")
    assert B.get() == b"xyzlm"
    B.unshift_bytes(b"abcabcabcabc")
    assert B.get() == b"abcabcabcabcxyzlm", "Can unshift to expand buffer size"
    B.shift_bytes()
    assert B.get() == b"cabcabcxyzlm", "shift_bytes shifts by size, not length"


def test_bstream():
    bstream_checks(BStream(io.BytesIO(b"abcdefghijklm"), 5))


def test_match_stream():
    M = MatchStream(io.BytesIO(b"abcdefghijklm"), 5)
    assert M.str_find(b"b") == (1, 1)
    assert M.str_find(b"cde") == (2, 3)
    assert M.str_find(b":") == (-1, 1)
    assert M.str_find(b"def") == (-1, 3), "Partial match also not found"
    assert M.reg_find(b".") == (0, 1)
    assert M.reg_find(b"..") == (0, 2)
    assert M.reg_find(rb"\d") == (-1, 0)
    assert M.reg_find(b"[bcd]+") == (1, 3)
    assert M.reg_find(b".{5}") == (0, 5)
    assert M.reg_find(b".{6}") == (-1, 0)
    bstream_checks(M)  # these must work on a MatchStream too


class Suite:
    """The Perl tests' Extract_Records::change_default_* calls, and their checks."""

    def __init__(self):
        self.defaults = dict(DEFAULTS, fill=0)  # the Perl's default fill was 0

    def default(self, **kw):
        self.defaults.update(kw)

    def fixed(self, src, match, reclen, answer, regex=False):
        out = io.BytesIO()
        E = Extractor(io.BytesIO(src), out, defaults=self.defaults)
        n = (E.reg_n if regex else E.str_n)(match, reclen)
        got = out.getvalue() if n else None
        assert got == answer, f"Extract {reclen} bytes using {match!r} from {src[:50]!r}"

    def between(self, src, start, stop, answer, regex=False):
        out = io.BytesIO()
        E = Extractor(io.BytesIO(src), out, defaults=self.defaults)
        n = (E.reg_reg if regex else E.str_str)(start, stop)
        got = out.getvalue() if n else None
        assert got == answer, f"Extract from {start!r} to {stop!r} in {src[:50]!r}"


def test_extract_records():
    t = Suite()
    t.fixed(b"abcdefabcdefgabcdefg", b"bc", 3, b"bcdbcdbcd")
    t.fixed(b"abcdezxabcde", b"zx", 1, b"z")  # carefully constructed to do cross-buf match
    t.fixed(b"abc123abc123def456def456", rb"([\d]{2}|[abc]{2})", 2, b"ab12ab124545", True)
    t.fixed(b"abc123abc123def456def456", rb"\d[abcdef]", 3, b"3ab3de6de", True)
    t.fixed(b"abc", b".", 10, None)  # check failure to match
    t.fixed(b"abc", rb"\d", 10, None, True)
    t.default(pad=1, fill=b"xyz")
    t.fixed(b"abc", b".", 10, b"abcxyzxyzx", True)  # check pad/fill

    t.default(pad=0, fill=0)
    t.between(b"11aoeu23aounth77aoesunth", b"ao", b"e", b"aoeaounth77aoe")
    t.between(b"11aoeu23aounth77aoesunth", rb"\d\d", rb"\d", b"11aoeu2", True)

    # minimum record length
    t.default(fill=b"!@#$%^&*+=", nmin=10, pad=1)
    t.between(b"11aoeu23aounth77aoesunth", b"ao", b"e", b"aoe!@#$%^&*+=aounth77aoe")
    t.default(nmax=10)
    t.between(b"11aoeu23aounth77aoesunth", rb"\d\d", rb"\d", b"11aoeu2!@#", True)
    t.default(fill=0, nmin=0, pad=0, nmax=0)

    t.default(xend=1)  # exclude end markers from output records
    t.between(b"11aoeu23aounth77aoesunth", b"ao", b"e", b"aoaounth77ao")
    t.between(b"11aoeu23aounth77aoesunth", rb"\d\d", rb"\d", b"11aoeu", True)

    t.default(xbeg=1)  # also exclude start markers from output records
    t.between(b"11aoeu23aounth77aoesunth", b"ao", b"e", b"unth77ao")
    t.between(b"11aoeu23aounth77aoesunth", rb"\d\d", rb"\d", b"aoeu", True)

    t.fixed(b"abcdezxabcde", b"zx", 1, b"a")
    t.fixed(b"abc123abc123def456def456", rb"([\d]{2}|[abcde]{2})", 2, b"c1ab3d6d", True)

    t.default(pre=b"NR)")
    t.between(b"11aoeu23aounth77aoesunth", b"ao", b"e", b"NR)NR)unth77ao")
    t.between(b"11aoeu23aounth77aoesunth2", rb"\d\d", rb"\d", b"NR)aoeuNR)aoesunth", True)
    t.fixed(b"abcdezxabcde", b"zx", 1, b"NR)a")
    t.fixed(b"abc123abc123def456def456", rb"([\d]{2}|[abcde]{2})", 2, b"NR)c1NR)abNR)3dNR)6d", True)
    t.default(pre=b"")

    t.default(post=b"<--")
    t.between(b"11aoeu23aounth77aoesunth", b"ao", b"e", b"<--unth77ao<--")
    t.between(b"11aoeu23aounth77aoesunth2", rb"\d\d", rb"\d", b"aoeu<--aoesunth<--", True)
    t.fixed(b"abcdezxabcde", b"zx", 1, b"a<--")
    t.fixed(b"abc123abc123def456def456", rb"([\d]{2}|[abcde]{2})", 2, b"c1<--ab<--3d<--6d<--", True)
    t.default(post=b"")

    # a couple of multi-buffer tests
    letters = bytes(range(ord("a"), ord("z") + 1)) * 1000  # 26 thousand characters
    src = letters + b"123imel" + letters + b"124david"
    t.fixed(src, b"12", 4, b"3ime4dav")
    t.between(src, rb"\d+\D", b"a", b"mel", True)

    # nmax
    src += letters
    t.between(src, rb"\d+", rb"\d+", b"imel" + letters, True)
    t.default(nmax=10)
    t.between(src, rb"\d+", rb"\d+", b"imelabcdef", True)
    t.default(nmax=0)

    # start priority with a fixed record length
    src = b"abcde:abcd:abc:abcdefg:abc"
    t.default(xbeg=0, xend=0, pad=0, fill=b"x", sp=0)
    t.fixed(src, b":", 6, b":abcd::abcde")
    t.fixed(src, b"[:]", 6, b":abcd::abcde", True)
    t.default(pad=1)
    t.fixed(src, b":", 6, b":abcd::abcde:abcxx")
    t.fixed(src, b"[:]", 6, b":abcd::abcde:abcxx", True)
    t.default(sp=1)
    t.fixed(src, b":", 6, b":abcdx:abcxx:abcde:abcxx")
    t.fixed(src, b"[:]", 6, b":abcdx:abcxx:abcde:abcxx", True)
    t.default(pad=0)
    t.fixed(src, b":", 6, b":abcde")
    t.fixed(src, b"[:]", 6, b":abcde", True)
    t.default(sp=0, pad=0)

    # start priority with match-to-match
    t.default(xbeg=0, pad=0, fill=b"x", sp=0)
    t.between(src, b":", b":", b":abcd::abcdefg:")
    t.between(src, b"[:]", b"[:]", b":abcd::abcdefg:", True)
    t.default(sp=1)
    t.between(src, b":", b":", b":abcd:abc:abcdefg")
    t.default(pad=1, nmin=7)
    t.between(src, b":", b":", b":abcdxx:abcxxx:abcdefg")
    t.between(src, b":", b"e", b":abcdxx:abcxxx:abcdex")


def test_the_perl_suite_passes_on_the_perl():
    """Sanity check that the Perl version passes its own tests (when perl is here)."""
    import shutil

    from conftest import LEGACY, perl

    if not shutil.which("perl") or not LEGACY.is_dir():
        pytest.skip("needs perl and the legacy/ Perl sources")
    p = perl([str(LEGACY / "recs" / "recs"), "-test"])
    assert b"not ok" not in p.stdout

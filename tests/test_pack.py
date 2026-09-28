import math
import struct

import pytest
from conftest import perl
from hypothesis import given, settings
from hypothesis import strategies as st

from telemetry_cli._pack import NATIVE, PackError, calcsize, pack, parse, unpack


def test_parse_counts_and_orders():
    assert parse("C") == [("C", NATIVE, None)]
    assert parse("L>2 a10 d*") == [("L", ">", 2), ("a", NATIVE, 10), ("d", NATIVE, -1)]
    assert parse("n") == [("n", ">", None)]
    assert parse("V") == [("V", "<", None)]


@pytest.mark.parametrize("bad", ["L2q!", "y", "a>4", "n<", "x<", "C>"])
def test_parse_rejects_unsupported(bad):
    with pytest.raises(PackError):
        parse(bad)


@pytest.mark.parametrize(
    "template,values,expected",
    [
        ("C", [257], b"\x01"),
        ("c", [-1], b"\xff"),
        ("C", [3.9], b"\x03"),
        ("C", [-3.9], b"\xfd"),
        ("S>", [0x1234], b"\x12\x34"),
        ("S<", [0x1234], b"\x34\x12"),
        ("n", [0x1234], b"\x12\x34"),
        ("V", [1], b"\x01\0\0\0"),
        ("L>", [-1], b"\xff\xff\xff\xff"),
        ("C3", [1, 2], b"\x01\x02\x00"),  # missing values pack as zero
        ("C2", [1, 2, 3], b"\x01\x02"),  # extra values are ignored
        ("C*", [1, 2, 3], b"\x01\x02\x03"),
        ("a4", ["ab"], b"ab\0\0"),
        ("A4", ["ab"], b"ab  "),
        ("Z4", ["abcdef"], b"abc\0"),
        ("a2", ["abcdef"], b"ab"),
        ("a", ["xyz"], b"x"),
        ("a*", ["xyz"], b"xyz"),
        ("Z*", ["xyz"], b"xyz\0"),
        ("x2 C", [7], b"\0\0\x07"),
        ("C", ["12abc"], b"\x0c"),  # Perl uses a string's leading number
        ("C", ["abc"], b"\x00"),
        ("f>", [1.5], struct.pack(">f", 1.5)),
        ("d<2", [1.0, -2.0], struct.pack("<2d", 1.0, -2.0)),
    ],
)
def test_pack(template, values, expected):
    assert pack(template, *values) == expected


def test_unpack_strings_and_numbers():
    data = b"ab  " + b"cd\0e" + struct.pack(">h", -2) + struct.pack("<f", 0.5)
    assert unpack("A4 Z4 s> f<", data) == (b"ab", b"cd", -2, 0.5)
    assert unpack("C*", b"\x01\x02") == (1, 2)
    assert unpack("L", b"\x01\x02") == ()  # stops quietly when data run out


def test_calcsize():
    assert calcsize("L S C a10 d") == 4 + 2 + 1 + 10 + 8


# --- differential tests against Perl's pack/unpack ---------------------------

INT_LETTERS = "cCsSlLiIqQnNvV"
PERL_PACK = "print pack(shift, @ARGV)"
PERL_UNPACK = (
    "binmode STDIN; local $/; my $d=<STDIN>; "
    "print join(',', map { sprintf(/^-?\\d+$/ ? '%s' : '%.17g', $_) } unpack(shift, $d))"
)


def _template(letter, order, count):
    return letter + ("" if letter in "cCnNvV" else order) + count


@pytest.mark.oracle
@settings(max_examples=200, deadline=None)
@given(
    letter=st.sampled_from(INT_LETTERS),
    order=st.sampled_from(["", "<", ">"]),
    values=st.lists(
        st.one_of(
            st.integers(-(2**63), 2**64 - 1),
            st.floats(-1e6, 1e6, allow_nan=False),
        ),
        min_size=1,
        max_size=4,
    ),
)
def test_integer_pack_matches_perl(letter, order, values):
    template = _template(letter, order, str(len(values)))
    args = [repr(v) if isinstance(v, float) else str(v) for v in values]
    expected = perl(["-e", PERL_PACK, template, *args]).stdout
    assert pack(template, *args) == expected


@pytest.mark.oracle
@settings(max_examples=100, deadline=None)
@given(
    letter=st.sampled_from("fd"),
    order=st.sampled_from(["", "<", ">"]),
    values=st.lists(st.floats(-1e30, 1e30, allow_nan=False), min_size=1, max_size=4),
)
def test_float_pack_matches_perl(letter, order, values):
    template = letter + order + str(len(values))
    args = [repr(v) for v in values]
    assert pack(template, *args) == perl(["-e", PERL_PACK, template, *args]).stdout


@pytest.mark.oracle
@settings(max_examples=100, deadline=None)
@given(
    letter=st.sampled_from("aAZ"),
    count=st.sampled_from(["", "1", "3", "8", "*"]),
    text=st.text(alphabet="abc xyz", max_size=10),
)
def test_string_pack_matches_perl(letter, count, text):
    template = letter + count
    assert pack(template, text) == perl(["-e", PERL_PACK, template, text]).stdout


@pytest.mark.oracle
@settings(max_examples=150, deadline=None)
@given(
    letter=st.sampled_from(INT_LETTERS + "fd"),
    order=st.sampled_from(["", "<", ">"]),
    data=st.binary(min_size=0, max_size=24),
)
def test_unpack_matches_perl(letter, order, data):
    template = _template(letter, order, "*")
    got = unpack(template, data)
    text = perl(["-e", PERL_UNPACK, template], stdin=data).stdout.decode()
    expected = [float(x) if letter in "fd" else int(x) for x in text.split(",") if x]
    assert len(got) == len(expected)
    for g, e in zip(got, expected, strict=True):
        assert g == e or (math.isnan(g) and math.isnan(e))

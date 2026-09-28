import math

import pytest
from conftest import perl
from hypothesis import given, settings
from hypothesis import strategies as st

from telemetry_cli._perl import numify, sprintf, substr, to_iv, to_uv, truthy

NAN = math.nan
INF = math.inf
VALUES = [0, -1, 3.9, -3.9, 1e20, -1e20, 2.0**63, 2.0**64, INF, -INF, NAN, -0.0]
VALUES += ["A", "5", "", None, 255, 4294967295, -2147483648]
FORMATS = ["%d", "%u", "%g", "%25.18g", "%02x", "%03o"]


def _perl_literal(v):
    if v is None:
        return "undef"
    if isinstance(v, str):
        return '"' + v + '"'
    if isinstance(v, float) and math.isnan(v):
        return '(unpack("f<", pack("V",0x7fc00000)))'
    if isinstance(v, float) and math.isinf(v):
        return "9**9**9" if v > 0 else "-9**9**9"
    return repr(v)


@pytest.mark.oracle
def test_sprintf_matches_perl_on_edge_values():
    for fmt in FORMATS:
        code = "".join(f'printf("[{fmt}]\\n", {_perl_literal(v)});' for v in VALUES)
        expected = perl(["-e", code]).stdout.decode().splitlines()
        got = [f"[{sprintf(fmt, v)}]" for v in VALUES]
        assert got == expected, fmt


@pytest.mark.oracle
@settings(max_examples=200, deadline=None)
@given(
    fmt=st.sampled_from(FORMATS),
    v=st.one_of(
        st.integers(-(2**70), 2**70),
        st.floats(allow_nan=False),
        st.text(alphabet="0123456789.eE+- xa", max_size=6),
    ),
)
def test_sprintf_matches_perl(fmt, v):
    lit = repr(v) if not isinstance(v, str) else "'" + v + "'"
    if isinstance(v, float) and math.isinf(v):
        lit = _perl_literal(v)
    if isinstance(v, int):
        lit = f'"{v}"'  # Perl reads big integer literals as floats; pass the digits
    expected = perl(["-e", f'printf("{fmt}", {lit})']).stdout.decode()
    assert sprintf(fmt, v) == expected


@pytest.mark.parametrize(
    "v,expected",
    [("12abc", 12), ("  -3.5e2x", -350.0), ("abc", 0), ("", 0), (None, 0), (".5", 0.5)],
)
def test_numify(v, expected):
    assert numify(v) == expected


def test_numify_specials():
    assert numify("Inf") == INF
    assert numify("-infinity") == -INF
    assert math.isnan(numify("NaN"))


def test_iv_uv():
    assert to_iv(1e20) == -1
    assert to_iv(-1e20) == -(2**63)
    assert to_uv(-1) == 2**64 - 1
    assert to_uv(-3.9) == 2**64 - 3
    assert to_uv(-1e20) == 2**63


@pytest.mark.parametrize(
    "offset,length,expected",
    [
        (-1, 4, b"c"),
        (-3, 2, b"ab"),
        (-5, 2, b""),
        (-5, 4, b"ab"),
        (-5, 10, b"abc"),
        (3, 2, b""),
        (4, 1, b""),
        (2, 5, b"c"),
        (0, 0, b""),
        (1, None, b"bc"),
    ],
)
def test_substr_matches_perl(offset, length, expected):
    assert substr(b"abc", offset, length) == expected


def test_truthy():
    assert not truthy("0") and not truthy("") and not truthy(None) and not truthy(0)
    assert truthy("00") and truthy("0.0") and truthy(" ") and truthy(1)

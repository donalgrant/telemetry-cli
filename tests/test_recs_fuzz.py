"""Differential fuzzing of recs: random streams, markers and options, Perl vs Python.

Streams are built from a small alphabet, with markers dropped in at random
places (often across the 1024-byte buffer boundary), and the options drawn at
random. The fill is always given (as "#", which the alphabet lacks), since
the default fill is a deliberate fix.

    pytest tests/test_recs_fuzz.py
    HYPOTHESIS_PROFILE=deep pytest tests/test_recs_fuzz.py
"""

from __future__ import annotations

import io
import os
import re
import subprocess

import pytest
from conftest import LEGACY, PERL
from hypothesis import given
from hypothesis import strategies as st

from telemetry_cli.recs.cli import main

pytestmark = pytest.mark.oracle

ALPHABET = b"abcXYZ:\n\x00\xff\xfe"
MARKERS = [b"XY", b"XYZ", b"::", b"a:", b"\xff\xfe", b"Z"]  # (argv can't hold a NUL)
REGEXES = [(r"X+Y", 3), (r"[:]{2}", 2), (r"a\d*:", 2), (r"\xff.", 2), (r"(XY|::)", 2)]
WARN = re.compile(rb"WARN \d{5}_\S+ (Matched bytes \(\d+\) is larger than mml parameter \(\d+\))\n")


@st.composite
def streams(draw):
    n = draw(st.integers(0, 2600))
    body = bytearray(
        draw(st.binary(min_size=n, max_size=n)).translate(
            bytes(ALPHABET[i % len(ALPHABET)] for i in range(256))
        )
    )
    for _ in range(draw(st.integers(0, 12))):
        m = draw(st.sampled_from(MARKERS))
        # favor positions near the default buffer boundary
        pos = draw(st.one_of(st.integers(0, len(body)), st.integers(1015, 1030)))
        body[pos:pos] = m
    return bytes(body)


@st.composite
def options(draw):
    opts = []
    for flag in ["-x", "-z", "-a", "-nl"]:
        if draw(st.booleans()):
            opts.append(flag)
    if draw(st.integers(0, 3)) == 0:
        opts.append(f"-min_reclen={draw(st.integers(1, 30))}")
    if draw(st.integers(0, 3)) == 0:
        opts.append(f"-max_reclen={draw(st.integers(1, 30))}")
    if draw(st.integers(0, 4)) == 0:
        opts.append(f"-mml={draw(st.integers(1, 6))}")
    if draw(st.integers(0, 4)) == 0:
        opts += ["-prepend", "<", "-append", ">"]
    return [*opts, "-f", "#"]


def run_both(args, data):
    env = {**os.environ}
    try:
        p = subprocess.run(
            [PERL, "-I", str(LEGACY), str(LEGACY / "recs" / "recs"), "-", *args],
            input=data,
            capture_output=True,
            timeout=10,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        p = None
    out, err = io.BytesIO(), io.StringIO()
    code = main(["-", *args], stdin=io.BytesIO(data), stdout=out, stderr=err)
    return p, (code, out.getvalue(), err.getvalue())


def check(args, data):
    perl, (code, out, err) = run_both(args, data)
    if perl is None:  # the Perl hung; the Python must stop with an error
        assert code != 0, args
        return
    assert code == 0, (args, err)
    warnings = [w.decode() for w in WARN.findall(perl.stdout)]
    assert out == WARN.sub(b"", perl.stdout), args
    got = [line for line in err.splitlines() if line.strip()]
    assert len(got) == len(warnings), (args, err, warnings)


@given(data=streams(), marker=st.sampled_from(MARKERS), opts=options(), reclen=st.integers(1, 60))
def test_fixed_length_matches_perl(data, marker, opts, reclen):
    check([*opts, os.fsdecode(marker), str(reclen)], data)


@given(
    data=streams(),
    start=st.sampled_from(MARKERS),
    stop=st.one_of(st.none(), st.sampled_from(MARKERS)),
    opts=options(),
)
def test_marker_to_marker_matches_perl(data, start, stop, opts):
    end = [] if stop is None else ["-e", os.fsdecode(stop)]
    check([*opts, *end, os.fsdecode(start)], data)


@given(
    data=streams(),
    regex=st.sampled_from(REGEXES),
    stop=st.one_of(st.none(), st.sampled_from(REGEXES)),
    opts=options(),
    reclen=st.one_of(st.none(), st.integers(1, 40)),
)
def test_regex_matches_perl(data, regex, stop, opts, reclen):
    end = [] if stop is None or reclen is not None else ["-e", stop[0]]
    length = [] if reclen is None else [str(reclen)]
    check(["-r", *opts, *end, regex[0], *length], data)

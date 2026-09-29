"""recl finds the record length of files whose record length is known.

The files are made with tgen: records of a sync word, a counter and random
bytes. recl can only find a length when there is enough data for the
structure to stand out from the noise; the tests make enough.
"""

from __future__ import annotations

import io
import subprocess
import sys

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from telemetry_cli.recl.cli import candidate_lengths, main
from telemetry_cli.recl.corr import agreement, choose
from telemetry_cli.tgen import cmdfile
from telemetry_cli.tgen.runtime import Generator


def records(reclen: int, nrecs: int, seed: int = 0) -> bytes:
    text = (
        "sync  # 0 # 1 # 'N' # 0x03915ed3\n"
        "count # 4 # 1 # 'n' # pmod(I, 65536)\n"
        f"data  # 6 # 1 # 'C{reclen - 6}' # [int(rand(256)) for _ in range({reclen - 6})]\n"
    )
    items, statements = cmdfile.parse(text)
    out = io.BytesIO()
    Generator(items, statements, seed=seed, stderr=io.StringIO()).run(out, nrecs, 0, quiet=True)
    return out.getvalue()


def enough_records(reclen: int) -> int:
    """Enough records for their 5 repeating bytes (sync, counter) to stand out.

    Comparing bytes, the noise is about sqrt((1/256)/(bytes compared)), so a
    few dozen records are plenty; this allows a margin.
    """
    return 40


def recl(data: bytes, *opts) -> tuple[int, str]:
    out, err = io.BytesIO(), io.StringIO()
    code = main(["-", *opts], stdin=io.BytesIO(data), stdout=out, stderr=err)
    return code, out.getvalue().decode() + err.getvalue()


def result(data: bytes, *opts) -> int:
    code, text = recl(data, "-q", *opts)
    assert code == 0, text
    return int(text.split("RESULT ")[1].split()[0])


# --- finding the record length ------------------------------------------------------


@pytest.mark.parametrize("reclen", [7, 8, 12, 48, 100, 128, 257, 512, 1000])
def test_finds_the_record_length(reclen):
    assert result(records(reclen, enough_records(reclen))) == reclen


@settings(max_examples=60, deadline=None)
@given(reclen=st.integers(7, 700), seed=st.integers(0, 1000))
def test_finds_random_record_lengths(reclen, seed):
    assert result(records(reclen, enough_records(reclen), seed)) == reclen


@settings(max_examples=30, deadline=None)
@given(reclen=st.integers(7, 300), cut=st.integers(1, 299), seed=st.integers(0, 1000))
def test_partial_last_record(reclen, cut, seed):
    data = records(reclen, enough_records(reclen), seed)[: -(cut % reclen or 1)]
    assert result(data, "-partial", f"-max={3 * reclen}") == reclen


def test_header_is_skipped():
    data = b"HEADER" * 17 + records(48, 200)
    assert result(data, "-skip=102") == 48


def test_factor_and_range():
    data = records(96, 200)
    assert result(data, "-fact=32") == 96
    assert result(data, "-min=90", "-max=100") == 96


def test_only():
    data = records(48, 200)
    for only in ["48", "24,48,96", "96,48,24", "8,16,32,48,64", "5,10,40,50"]:
        want = 48 if "48" in only else None
        got = result(data, f"-only={only}")
        assert got == want if want else got in (5, 10, 40, 50)


def test_limit_reduce_full_and_maxbufs():
    data = records(64, 300)
    for opts in (["-limit=6400"], ["-reduce=3"], ["-full"], ["-maxbufs=2"], ["-full", "-reduce=2"]):
        assert result(data, "-max=200", *opts) == 64


def test_limit_reduce_change_what_is_used():
    data = records(64, 300)
    _, text = recl(data, "-max=200", "-limit=4000")
    assert "Based on 10 buffers, each of length 400" in text
    _, text = recl(data, "-max=200", "-full", "-reduce=4")
    assert "Based on 1 buffers, each of length 4800" in text


# --- the pieces ------------------------------------------------------------------------


def test_scores_are_fractions_of_equal_bytes():
    buffers = np.frombuffer(b"abcabcabcXbc", dtype=np.uint8)[None, :]
    s = agreement(buffers, [1, 3, 7])[0]
    assert s[0] == 0.0
    assert s[1] == pytest.approx(8 / 9)  # one of the nine pairs differs (the X)
    assert s[2] == 0.0  # needs at least 14 bytes to be scored


def test_counters_dont_pull_toward_multiples():
    """A counter's low bits agree more at multiples of the length; bytes don't."""
    assert result(records(298, 96, 310)) == 298


@pytest.mark.parametrize("reclen", [7, 60, 300, 1000])
def test_works_with_little_data(reclen):
    assert result(records(reclen, 12, 1)) == reclen


def test_choose_prefers_the_smallest_equal_divisor():
    lengths = [1, 2, 3, 4, 6, 8, 12, 24]
    scores = [0.50, 0.51, 0.50, 0.52, 0.50, 0.70, 0.50, 0.701]
    assert lengths[choose(lengths, scores)] == 8
    scores[5] = 0.60  # 8 no longer nearly as good as 24
    assert lengths[choose(lengths, scores)] == 24


def test_choose_ignores_divisors_without_structure():
    lengths = [1, 2, 4, 8, 16, 32]
    scores = [0.0040, 0.0041, 0.0039, 0.0042, 0.0040, 0.0100]
    counts = [1e6] * 6  # standard error 0.00006: 32's signal is significant
    assert lengths[choose(lengths, scores, counts)] == 32


def test_candidates():
    assert candidate_lengths(24, 1, 12, 1, False) == [1, 2, 3, 4, 6, 8, 12]
    assert candidate_lengths(24, 3, 12, 2, False) == [4, 6, 8, 12]
    assert candidate_lengths(25, 4, 8, 1, True) == [4, 5, 6, 7, 8]


# --- the command line ------------------------------------------------------------------


def test_output_lines():
    code, text = recl(records(12, 400), "-max=24")
    lines = text.splitlines()
    assert code == 0
    # the divisors of 4800 up to 24
    assert (
        lines[0] == "NOTE Checking Record Lengths 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 20, 24 bytes"
    )
    assert lines[1] == "RESULT 12" and lines[2].startswith("CORR ")
    assert lines[3] == "NOTE Based on 100 buffers, each of length 48"


def test_verbose_table_is_in_percent():
    _, text = recl(records(12, 400), "-v", "-only=6,12")
    table = text.split("Table of Sorted Correlations\n")[1].splitlines()
    assert table[0].startswith("NOTE ") and "% for reclen 12" in table[0]
    assert float(table[0].split()[1].rstrip("%")) > 10  # a percentage, not a fraction


@pytest.mark.parametrize(
    "args,message",
    [
        ([], "no input file"),
        (["-", "-min=90", "-max=80"], "no record lengths"),
        (["-", "-only=x"], "-only needs"),
        (["-", "-only=0,4"], "at least 1 byte"),
        (["-", "-reduce=0.5"], "-reduce must be"),
        (["-", "-fact=0"], "-fact must be"),
        (["-", "-bogus"], "Unknown option"),
        (["no-such-file"], "Can't open"),
    ],
)
def test_errors(args, message):
    out, err = io.BytesIO(), io.StringIO()
    code = main(args, stdin=io.BytesIO(records(8, 20)), stdout=out, stderr=err)
    assert code != 0 and message in err.getvalue()


def test_too_little_data():
    code, text = recl(b"x")
    assert code != 0 and "too little data" in text


def test_help():
    out = io.BytesIO()
    assert main(["-help"], stdout=out) == 0 and b"RESULT" in out.getvalue()


def test_runs_as_a_program():
    p = subprocess.run(
        [sys.executable, "-m", "telemetry_cli.recl", "-", "-q", "-max=40"],
        input=records(16, 300),
        capture_output=True,
        check=False,
    )
    assert p.returncode == 0 and p.stdout.decode().splitlines()[1] == "RESULT 16"

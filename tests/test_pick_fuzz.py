"""Differential fuzzing: random pick command lines, run through the Perl and the Python.

Hypothesis builds random field requests (types, counts, offsets, bit fields,
formats, moves and nested groups), a random record size and random data. The
big-host copy of the Perl (see tools/make_golden.py) and the Python version,
emulating a big-endian machine, must then agree.

Anything these tests find should be added to tests/golden/pick/cases.py, so it
is checked on every run without perl.

    pytest tests/test_pick_fuzz.py                        # the CI budget
    HYPOTHESIS_PROFILE=deep pytest tests/test_pick_fuzz.py  # a longer search
"""

from __future__ import annotations

import io
import subprocess
import sys

import pytest
from conftest import PERL, ROOT
from hypothesis import given
from hypothesis import strategies as st

from telemetry_cli.pick.cli import main

sys.path.insert(0, str(ROOT / "tools"))
from make_golden import big_host_pick, swap_nl  # noqa: E402

pytestmark = pytest.mark.oracle

TYPES = "SAbcswuidfzZ"
NBYTES = {"S": 1, "A": 1, "b": 1, "c": 1, "s": 2, "w": 2, "u": 4, "i": 4, "f": 4, "d": 8}
NBYTES |= {"z": 8, "Z": 16}
INT_FORMATS = "udxosnbcSAD"
FLOAT_FORMATS = "gGDxobsncSAud"
COMPLEX_FORMATS = "RIMPD"  # 'g' on complex is a deliberate fix
MATCHED_NEITHER = b"Matched neither a move nor a data request"


def formats_for(t: str):
    pool = COMPLEX_FORMATS if t in "zZ" else FLOAT_FORMATS if t in "fd" else INT_FORMATS
    return st.text(alphabet=pool, min_size=0, max_size=3)


@st.composite
def print_request(draw):
    t = draw(st.sampled_from(TYPES))
    count = draw(st.one_of(st.just(""), st.integers(1, 4).map(str)))
    offset = ""
    if draw(st.booleans()):
        offset = str(draw(st.integers(0, 6)))
        if draw(st.booleans()):
            offset += draw(st.sampled_from("+-")) + str(draw(st.integers(0, 9)))
    bits = ""
    if NBYTES[t] <= 4 and draw(st.integers(0, 3)) == 0:
        bits = ":" + str(draw(st.integers(0, 8 * NBYTES[t] - 1)))
        if draw(st.booleans()):
            bits += ":" + str(draw(st.integers(1, 8 * NBYTES[t])))
    return f"{count}{t}{offset}{bits}{draw(formats_for(t))}"


@st.composite
def move(draw):
    sign = draw(st.sampled_from("+-"))
    t = draw(st.sampled_from(["", *TYPES]))
    return f"{sign}{draw(st.integers(0, 6))}{t}"


def requests(depth=0):
    item = st.one_of(print_request(), print_request(), move())
    if depth < 2:
        item = st.one_of(item, group(depth + 1))
    return st.lists(item, min_size=1, max_size=4).map(
        lambda xs: [t for x in xs for t in (x if isinstance(x, list) else [x])]
    )


@st.composite
def group(draw, depth):
    repeat = draw(st.sampled_from(["", "1", "2", "3"]))
    return [f"{repeat}[", *draw(requests(depth)), "]"]


OPTION_SETS = ["", "-n", "-l", "-m", "-nlm", "-s"]


def run_perl(args, data):
    try:
        p = subprocess.run(
            [PERL, str(big_host_pick()), *swap_nl(args)],
            input=data,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    return p


def run_python(args, data):
    out, err = io.BytesIO(), io.StringIO()
    code = main(args, stdin=io.BytesIO(data), stdout=out, stderr=err, host_order="big")
    return code, out.getvalue(), err.getvalue()


def check_same(args, data):
    perl = run_perl(args, data)
    code, out, err = run_python(args, data)
    if perl is None:  # the Perl hung; the Python must stop with an error
        assert code != 0, f"perl hung but python succeeded: {args}"
        return
    if MATCHED_NEITHER in perl.stdout:
        assert code != 0 and MATCHED_NEITHER.decode() in err, args
        return
    if perl.returncode != 0:
        message = perl.stderr.decode("latin-1").strip().splitlines()[-1]
        message = message.split(" at ")[0]
        assert code != 0, f"perl failed ({message}) but python succeeded: {args}"
        assert message in err, (args, err)
        return
    assert code == 0, (args, err)
    assert out == perl.stdout, args


@given(
    reqs=requests(),
    size=st.integers(1, 48),
    nrecs=st.integers(0, 3),
    opts=st.sampled_from(OPTION_SETS),
    seed=st.binary(min_size=0, max_size=200),
)
def test_random_requests_match_perl(reqs, size, nrecs, opts, seed):
    data = (seed * (1 + size * nrecs // max(len(seed), 1)))[: size * nrecs] if seed else b""
    data = data.ljust(size * nrecs, b"\x5a")
    args = [str(size), "-q", *([opts] if opts else []), *reqs]
    check_same(args, data)


NEAR_MISS = st.text(alphabet="0123456789+-:[]SAbcswuidfzZudxnsgGoMPRIDU", min_size=1, max_size=6)


@given(tokens=st.lists(NEAR_MISS, min_size=1, max_size=4), size=st.integers(1, 32))
def test_near_miss_requests_match_perl(tokens, size):
    """Mostly-invalid requests: both versions must fail, or agree on the output."""
    data = bytes(range(256))[: size * 2]
    check_same([str(size), "-q", *tokens], data)


@given(
    params=st.lists(
        st.sampled_from(
            ["start=1", "stop=2", "skip=1", "every=2", "nrecs=2", "rec=1", "head=3", "head=1i"]
        ),
        max_size=3,
    ),
    size=st.integers(1, 12),
)
def test_record_selection_matches_perl(params, size):
    data = bytes(range(256))[:100]
    check_same([str(size), "-q", "-nlm", "b", *params], data)


# --- little-endian hosts ------------------------------------------------------------
#
# On a little-endian host, pick must read each item as little-endian. The
# big-host Perl run with -r does exactly that, one item at a time, so it is the
# reference, except for complex types (whose -r swapped their parts), the U
# format (which writes in the host's order) and reads that run off the start
# of the record (where the Perl's -r filled in zeros). The strategy avoids those.

LE_TYPES = "SAbcswuidf"


@st.composite
def le_print_request(draw):
    t = draw(st.sampled_from(LE_TYPES))
    count = draw(st.one_of(st.just(""), st.integers(1, 3).map(str)))
    offset = ""
    if draw(st.booleans()):
        offset = str(draw(st.integers(0, 4))) + draw(st.sampled_from(["", "+1", "+3"]))
    bits = ""
    if NBYTES[t] <= 4 and draw(st.integers(0, 2)) == 0:
        bits = ":" + str(draw(st.integers(0, 8 * NBYTES[t] - 1)))
        if draw(st.booleans()):
            bits += ":" + str(draw(st.integers(1, 8 * NBYTES[t])))
    pool = FLOAT_FORMATS if t in "fd" else INT_FORMATS
    return f"{count}{t}{offset}{bits}{draw(st.text(alphabet=pool, max_size=3))}"


le_requests = st.lists(
    st.one_of(le_print_request(), st.integers(0, 4).map(lambda n: f"+{n}")), min_size=1, max_size=5
)


def run_perl_le_reference(args, data):
    try:
        return subprocess.run(
            [PERL, str(big_host_pick()), *swap_nl(args), "-r"],
            input=data,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


@given(reqs=le_requests, size=st.integers(1, 40), data=st.binary(min_size=0, max_size=120))
def test_little_endian_host_reads_items_little_endian(reqs, size, data):
    args = [str(size), "-q", *reqs]
    perl = run_perl_le_reference(args, data)
    out, err = io.BytesIO(), io.StringIO()
    code = main(args, stdin=io.BytesIO(data), stdout=out, stderr=err, host_order="little")
    assert perl is not None
    if MATCHED_NEITHER in perl.stdout or perl.returncode != 0:
        assert code != 0, args
        return
    assert code == 0, (args, err.getvalue())
    assert out.getvalue() == perl.stdout, args

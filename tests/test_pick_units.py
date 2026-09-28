"""Unit and property tests of pick's internals and its new features.

The golden and fuzz tests check pick's output against the Perl. These check the
stages one at a time (so a failure points at the stage that broke) and cover
behavior the Perl can't check: the order= parameter, --help topics, bundled
symbol tables, and the fixes.
"""

from __future__ import annotations

import io
import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

from telemetry_cli.pick.cli import main
from telemetry_cli.pick.commandline import (
    UsageError,
    expand_symbols,
    parse,
    parse_options,
    parse_params,
    read_symbols,
    resolve,
)
from telemetry_cli.pick.fields import FieldError, extract_groups, parse_fields, parse_size


def pick(*args, data=b"", host="little"):
    out, err = io.BytesIO(), io.StringIO()
    code = main(list(args), stdin=io.BytesIO(data), stdout=out, stderr=err, host_order=host)
    return code, out.getvalue(), err.getvalue()


# --- options and parameters ----------------------------------------------------


def test_options_are_letters_after_a_space():
    s, opts = parse_options("file 8 -nl u -q")
    assert opts["n"] and opts["l"] and opts["q"] and not opts["r"]
    assert s.split() == ["file", "8", "u"]


def test_first_word_is_never_an_option():
    s, opts = parse_options("-q file")
    assert not opts["q"] and s == "-q file"


def test_unknown_option_letters_are_reported():
    with pytest.raises(UsageError, match="-->zx<--"):
        parse_options("f -nzx")


def test_parameters_anywhere_with_units_and_spaces():
    s, params = parse_params("f start = 5 8 head=2i u file=abc")
    assert params == {"start": 5, "head": 8, "file": "abc"}
    assert s.split() == ["f", "8", "u"]


def test_parameter_names_keep_their_case():
    # the Perl matched START=5 but stored it under START, so it had no effect
    _, params = parse_params("f START=5")
    assert params == {"START": 5}


def test_unexpected_equals():
    with pytest.raises(UsageError, match="Unexpected '='"):
        parse(["f", "8", "foo=3"])


@pytest.mark.parametrize(
    "token,size", [("8", 8), ("8b", 8), ("2i", 8), ("21d", 168), ("4z", 32), ("1Z", 16)]
)
def test_record_sizes(token, size):
    assert parse_size(token) == size


@pytest.mark.parametrize("token", ["", "x", "-8", "8q", "8 "])
def test_not_record_sizes(token):
    assert parse_size(token) is None


@pytest.mark.parametrize(
    "params,expected",
    [
        ([], (0, -1, 0)),
        (["rec=4"], (4, 4, 0)),
        (["start=3", "nrecs=2"], (3, 4, 0)),
        (["stop=5", "nrecs=2"], (4, 5, 0)),
        (["nrecs=3"], (0, 2, 0)),
        (["every=10"], (0, -1, 9)),
        (["every=10", "skip=2"], (0, -1, 2)),
    ],
)
def test_record_selection(tmp_path, params, expected):
    f = tmp_path / "x.bin"
    f.write_bytes(b"")
    plan = resolve(parse([str(f), "8", "u", *params]))
    assert (plan.start, plan.stop, plan.skip) == expected


# --- symbols -----------------------------------------------------------------------


def test_symbols_expand_recursively_as_whole_words(tmp_path):
    table = tmp_path / "t"
    table.write_text("; comment\na = d0\nab = d1 ; trailing comment\nboth = a ab\nx = 0\n")
    symbols = read_symbols(table)
    assert symbols == {"a": "d0", "ab": "d1 ", "both": "a ab"}  # "0" is false in Perl
    assert expand_symbols("both", symbols).split() == ["d0", "d1"]
    assert expand_symbols("ab a", symbols).split() == ["d1", "d0"]


def test_symbol_in_the_wrong_case_expands_to_nothing():
    assert expand_symbols("A a", {"a": "d0"}).split() == ["d0"]


def test_self_referential_symbols_are_an_error():
    with pytest.raises(UsageError, match="refer to themselves"):
        expand_symbols("x", {"x": "x x"})


def test_bundled_symbol_tables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PICKPATH", raising=False)
    data = struct.pack(">21d", *range(21))
    code, out, _ = pick("sym=moc", "-q", "pos", data=data, host="big")  # moc sets the length
    assert code == 0 and out == b"3 4 5 \n"


def test_missing_symbol_table(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PICKPATH", str(tmp_path))
    code, _, err = pick("8", "sym=nope", "u")
    assert code != 0 and "Couldn't find symbol table" in err


# --- field requests ------------------------------------------------------------------


def test_groups_are_rewritten_innermost_first():
    text, groups = extract_groups("2[ b 3[ w +1 ] ] i")
    assert groups == [" w \\+1 ", " b 3Y0  "]  # the repeat count stays with the name
    assert text.split() == ["2Y1", "i"]


def test_positions_follow_moves_and_offsets():
    fields = parse_fields("i +4 w i0+1 2[ b +1 ]", 32)
    assert [(f.t, f.pos, f.m) for f in fields] == [
        ("i", 0, 1),
        ("w", 8, 1),
        ("i", 1, 1),
        ("b", 5, 1),
        ("b", 7, 1),
    ]


def test_count_zero_means_one_but_double_zero_is_zero():
    assert parse_fields("0i", 8)[0].m == 1
    assert parse_fields("00i", 8)[0].m == 0


def test_beyond_record_length():
    with pytest.raises(FieldError, match="beyond record length"):
        parse_fields("3i", 8)


def test_moves_may_go_past_the_end_until_something_is_read():
    assert parse_fields("+100 -100 i", 4)[0].pos == 0


def test_bit_field_mask():
    f = parse_fields("w:3:5", 2)[0]
    assert (f.first_bit, f.nbits, f.mask, f.bits) == (3, 5, 0b11111, True)
    assert parse_fields("w", 2)[0].bits is False


# --- output: byte order and the fixes -----------------------------------------------

VALUE = 0x03915ED3


@pytest.mark.parametrize("host", ["big", "little"])
def test_value_order_on_any_host(host):
    for order, data in [("little", struct.pack("<I", VALUE)), ("big", struct.pack(">I", VALUE))]:
        code, out, _ = pick("4", "-q", f"order={order}", "u0d", "u0x", "u0:0:8d", "u0:24:8b",
                            data=data, host=host)  # fmt: skip
        assert code == 0
        assert out == b"59858643 03 91 5e d3  211 0000 0011  \n"


def test_r_reverses_the_order_in_effect():
    data = struct.pack(">I", VALUE)
    assert pick("4", "-q", "-r", "ud", data=data, host="little")[1] == b"59858643 \n"
    assert pick("4", "-q", "order=little", "-r", "ud", data=data, host="big")[1] == b"59858643 \n"


def test_bad_order():
    code, _, err = pick("4", "order=middle", "u")
    assert code != 0 and "order must be" in err


def test_complex_r_reverses_each_part():
    data = struct.pack("<ff", 3.0, 4.0)
    for host in ("big", "little"):
        _, out, _ = pick("8", "-q", "order=little", "zRIM", data=data, host=host)
        assert out == b"3 4 5 \n"


def test_complex_g_means_ri():
    data = struct.pack(">ff", 3.0, -4.0)
    assert pick("8", "-q", "zg", data=data, host="big")[1] == b"3 -4 \n"  # same as zRI


def test_l_prints_line_numbers_and_n_record_numbers():
    data = bytes(range(8))
    _, out, _ = pick("2", "-q", "-l", "-n", "b", "every=2", data=data)
    assert out.splitlines() == [b"0 0 00  ", b"1 2 04  "]  # line number, record number


@pytest.mark.parametrize("host", ["big", "little"])
def test_u_of_a_bit_field_writes_the_masked_value(host):
    data = struct.pack(">I", VALUE)
    _, out, _ = pick("4", "-q", "-s", "order=big", "u:8:16U", data=data, host=host)
    # bits 8..23 of 0x03915ed3 are 0x915e, written in the host's order
    assert out == (b"\x91\x5e" if host == "big" else b"\x5e\x91")


@given(values=st.lists(st.integers(-(2**31), 2**31 - 1), min_size=1, max_size=8))
def test_binary_output_round_trips(values):
    data = struct.pack(f"<{len(values)}i", *values)
    for opt in ("-b", "-u"):
        _, out, _ = pick("4", "-q", opt, "i", data=data, host="little")
        assert out == data


@given(values=st.lists(st.integers(0, 2**16 - 1), min_size=1, max_size=8))
def test_u_with_r_swaps_bytes(values):
    data = struct.pack(f"<{len(values)}H", *values)
    _, out, _ = pick("2", "-q", "-r", "-u", "w", data=data, host="little")
    assert out == struct.pack(f">{len(values)}H", *values)


@given(
    values=st.lists(st.integers(-(2**31), 2**31 - 1), min_size=1, max_size=6),
    fmt=st.sampled_from(["d", "u", "x", "o", "b", "dxb", "D", "g"]),
)
def test_output_depends_only_on_the_data_order(values, fmt):
    """Same values, stored either way, read on either host: identical output."""
    outs = set()
    for order, code in [("little", "<"), ("big", ">")]:
        data = struct.pack(f"{code}{len(values)}i", *values)
        for host in ("big", "little"):
            outs.add(pick("4", "-q", f"order={order}", f"i{fmt}", data=data, host=host)[1])
    assert len(outs) == 1


# --- help, errors and files --------------------------------------------------------------


HELP_FLAGS = [
    (["--help"], "pick Usage"),
    (["--help", "t"], "data types"),
    (["-h", "?f"], "printFormatList"),
    (["--help", "all"], "Groups"),
]


@pytest.mark.parametrize("args,marker", HELP_FLAGS)
def test_help_flags(args, marker):
    code, out, _ = pick(*args)
    assert code == 0 and marker in out.decode()


def test_help_lists_symbols(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "t").write_text("b = d0\na = d1\n")
    _, out, _ = pick("sym=t", "?")
    assert out.decode().endswith("Symbols defined in t:\na=d1\nb=d0\n")


def test_errors_go_to_stderr_with_a_nonzero_status():
    code, out, err = pick("8", "q", data=bytes(16))
    assert code != 0 and out == b""
    assert "Matched neither a move nor a data request" in err


def test_unreadable_file(tmp_path):
    code, _, err = pick(f"file={tmp_path / 'missing'}", "8", "u")
    assert code != 0 and "can't read" in err


def test_every_zero_and_size_zero_are_errors():
    assert pick("8", "u", "every=0", data=bytes(16))[0] != 0
    assert pick("0", "-q", data=bytes(16))[0] != 0  # a bare "0" is false: it prints help


def test_reading_from_stdin_is_announced_unless_quiet():
    assert pick("1", "b", data=b"\x01")[2] == "Reading from stdin\n"
    assert pick("1", "-q", "b", data=b"\x01")[2] == ""


def test_broken_pipe_is_quiet():
    class Closed(io.BytesIO):
        def write(self, b):
            raise BrokenPipeError

    code = main(["1", "-q", "b"], stdin=io.BytesIO(b"\x01"), stdout=Closed(), stderr=io.StringIO())
    assert code == 0


def test_runs_as_a_program(tmp_path):
    import subprocess
    import sys

    f = tmp_path / "x.bin"
    f.write_bytes(bytes([1, 2, 3, 4]))
    p = subprocess.run(
        [sys.executable, "-m", "telemetry_cli.pick", str(f), "2", "-q", "2bd"],
        capture_output=True,
        check=False,
    )
    assert p.returncode == 0 and p.stdout == b"1  2  \n3  4  \n"

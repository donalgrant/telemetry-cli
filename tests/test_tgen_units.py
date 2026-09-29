"""tgen's command-file parser, runtime and command line."""

from __future__ import annotations

import contextlib
import io
import struct
import subprocess
import sys
import threading

import pytest

from telemetry_cli.tgen import cmdfile
from telemetry_cli.tgen.cli import main
from telemetry_cli.tgen.runtime import Drand48, Generator, TgenError, cat, perl_true, pmod


def gen(text, *, fill="0", seed=1, **kw):
    items, statements = cmdfile.parse(text)
    return Generator(items, statements, fill=fill, seed=seed, stderr=io.StringIO(), **kw)


def frames(text, n=1, first=0, **kw):
    out = io.BytesIO()
    gen(text, **kw).run(out, n, first, quiet=True)
    return out.getvalue()


def test_parse_items_statements_comments_continuations():
    items, statements = cmdfile.parse(
        "# c\n! c\n; c\nx = 1\na # 0 # 1 \\\n # 'C' # 7 # extra field\n  \nb#1#1#'C'#2\n"
    )
    assert [(i.name, i.offset, i.trigger, i.type, i.value, i.line) for i in items] == [
        ("a", "0", "1", "'C'", "7", 5)
    ]
    # 'b#1#...' has no spaces around its #s, so it's a statement (a Python comment)
    assert [s.code for s in statements] == ["x = 1", "b#1#1#'C'#2"]


def test_frame_layout_padding_and_overlap():
    text = "a # 2 # 1 # 'C' # 1\nb # 0 # 1 # 'S>' # 0x0203\nc # 3 # 1 # 'C' # 9\n"
    assert frames(text, fill=7) == bytes([2, 3, 1, 9])
    assert frames("a # 3 # 1 # 'C' # 1\n", fill=255) == b"\xff\xff\xff\x01"


def test_triggers_and_negative_offsets():
    text = "t # -1 # 1 # X # I*10\nv # 0 # I % 2 # 'C' # P.t.value\nw # 1 # 1 # 'C' # 5\n"
    assert frames(text, 3) == b"\x00\x05" + b"\x0a\x05" + b"\x00\x05"


def test_fields_with_statements_and_assignments():
    text = "COUNT = 0\nc # 0 # 1 # 'C' # COUNT = COUNT + 2; COUNT + 1\nd # 1 # 1 # 'C' # e = 4\n"
    assert frames(text, 2) == b"\x03\x04\x05\x04"


def test_value_and__value():
    text = "r # -1 # 1 # X # rand()\nv # 0 # 1 # 'f<2' # [P.r.value, P.r.value]\n"
    text += "w # 8 # 1 # 'f<2' # [P.r._value, P.r._value]\n"
    a, b, c, d = struct.unpack("<4f", frames(text))
    assert a == b and c != d


def test_random_fill_reads_differ():
    text = "a # 0 # 1 # 'C3' # [F, F, F]\n"
    assert len(set(frames(text, fill="random", seed=3))) > 1
    assert frames(text, fill=9) == b"\x09\x09\x09"


def test_fill_changes_mid_run():
    text = "z # -1 # I == 1 # X # F = 255\nb # 2 # 1 # 'C' # 1\n"
    assert frames(text, 2) == b"\x00\x00\x01\xff\xff\x01"


def test_drand48_matches_perl():
    r = Drand48(42)
    assert [r.random() for _ in range(3)] == [
        0.74452500006100664,
        0.34270147871890799,
        0.11108528244416149,
    ]


def test_helpers():
    assert pmod(7.9, 3) == 1 and pmod(-7, 3) == 2
    assert cat("a", 1, 2.5, 1 / 3, None) == "a12.50.333333333333333"
    assert not perl_true("0") and perl_true("0.0") and perl_true([]) and not perl_true(0.0)
    with pytest.raises(ZeroDivisionError):
        pmod(1, 0)


def test_file_helpers_open_each_file_once(tmp_path):
    data = tmp_path / "d.bin"
    data.write_bytes(struct.pack("<4f", 0.0, 1.0, 2.0, 3.0))
    text = f"D = r'{data}'\n"
    text += "a # 0 # 1 # 'a4' # subcom_file(D, 4*I, 4)\n"
    text += "b # 4 # 1 # 'f<' # file_lookup(D, 4*I, 4, 'f<')\n"
    text += "c # 8 # 1 # 'l<' # seek_file(D, '4*O', 4, 'f<', 'X >= 2.5')\n"
    text += "d # 12 # 1 # 'l<' # seek_file(D, '4*O', 4, 'f<', 'X > 99')\n"
    g = gen(text)
    out = io.BytesIO()
    g.run(out, 2, 0, quiet=True)
    frame = out.getvalue()[16:]
    assert frame[:4] == struct.pack("<f", 1.0)
    assert struct.unpack("<fll", frame[4:]) == (1.0, 12, -1)
    assert len(g.files) == 1


def test_file_errors(tmp_path):
    with pytest.raises(TgenError, match="Can't read from"):
        frames("a # 0 # 1 # 'C' # file_lookup('/no/such/file', 0, 1, 'C')\n")


@pytest.mark.parametrize(
    "text,message",
    [
        ("a # 0 # 1 # 'C' # 1 +\n", "can't parse"),
        ("a # 0 # 1 # 'C' # nothing_here\n", "NameError"),
        ("a # 0 # 1 # 'q!' # 1\n", "unsupported pack template"),
        ("x = (\n", "can't parse"),
    ],
)
def test_errors_say_where(text, message):
    with pytest.raises(TgenError, match=message) as e:
        frames(text)
    assert "command file:1" in str(e.value)


def test_debug_traces_to_stderr():
    g = gen("DEBUG = 1\na # 0 # 1 # 'C' # 7\n")
    g.run(io.BytesIO(), 1, 0, quiet=True)
    assert "a.value: '7' -> 7" in g.stderr.getvalue()


def test_changing_I_changes_the_record_count():
    text = "r # -1 # 1 # X # rand()\nx # -1 # 1 # X # I = I - 1 if P.r.value < 0.5 else I\n"
    text += "a # 0 # 1 # 'C' # 1\n"
    assert len(frames(text, 20, seed=5)) > 20


# --- the command line ----------------------------------------------------------------


def run(*args, cwd=None):
    out, err = io.BytesIO(), io.StringIO()
    return main(list(args), stdout=out, stderr=err), out.getvalue(), err.getvalue()


def test_cli(tmp_path):
    f = tmp_path / "c.tgen"
    f.write_text("a # 0 # 1 # 'C' # I\n")
    assert run("-q", str(f), "3", "5")[1] == b"\x05\x06\x07"
    code, out, err = run("-n", "2", str(f), "4")
    assert out == b"\x00\x01\x02\x03" and err.splitlines() == ["1/3", "3/3"]


def test_cli_help_version_usage_convert(tmp_path):
    assert b"item specifications" in run("-help")[1]
    assert "telemetry-cli" in run("-v")[2]
    code, _, err = run()
    assert code == 2 and "Usage" in err
    p = tmp_path / "p.tgen"
    p.write_text("a # 0 # 1 # 'C' # $::I % 4\n")
    assert run("--convert", str(p))[1] == b"a # 0 # 1 # 'C' # pmod(I, 4)\n"


def test_cli_errors(tmp_path):
    assert "Can't read" in run(str(tmp_path / "missing"))[2]
    assert "Unknown option: zz" in run("-zz", "x")[2]
    f = tmp_path / "bad.tgen"
    f.write_text("a # 0 # 1 # 'C' # oops\n")
    code, _, err = run(str(f))
    assert code == 1 and "NameError" in err and "bad.tgen:1" in err


def test_broken_pipe_is_quiet(tmp_path):
    f = tmp_path / "c.tgen"
    f.write_text("a # 0 # 1 # 'C' # 1\n")

    class Closed(io.BytesIO):
        def write(self, b):
            raise BrokenPipeError

    assert main(["-q", str(f), "5"], stdout=Closed(), stderr=io.StringIO()) == 0


def test_runs_as_a_program(tmp_path):
    f = tmp_path / "c.tgen"
    f.write_text("a # 0 # 1 # 'C' # I\n")
    p = subprocess.run(
        [sys.executable, "-m", "telemetry_cli.tgen", "-q", str(f), "3"],
        capture_output=True,
        check=False,
    )
    assert p.returncode == 0 and p.stdout == b"\x00\x01\x02"


@pytest.mark.parametrize("tool", ["tgen", "pick", "recs"])
def test_closing_the_pipe_early_is_quiet(tool, tmp_path):
    """`tool ... | head -c 10`: no error report when the reader stops."""
    f = tmp_path / "c.tgen"
    f.write_text("a # 0 # 1 # 'C1000' # [1] * 1000\n")
    args = {
        "tgen": ["-q", str(f), "5000"],
        "pick": ["1", "-q", "b"],
        "recs": ["-", "-x", "a", "1"],
    }[tool]
    p = subprocess.Popen(
        [sys.executable, "-m", f"telemetry_cli.{tool}", *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def feed():
        with contextlib.suppress(BrokenPipeError):
            if tool != "tgen":
                p.stdin.write(b"a" * 2_000_000)
            p.stdin.close()

    writer = threading.Thread(target=feed)
    writer.start()
    p.stdout.read(10)
    p.stdout.close()
    assert p.wait(timeout=60) == 0
    writer.join()
    assert p.stderr.read() == b""


def test_bitstring_and_the_B_type():
    from telemetry_cli.tgen.runtime import bitstring

    assert bitstring([3, 5], 4) == "00110101"
    assert bitstring(1023, 10) == "1" * 10
    assert bitstring([-1, 2], [3, 5]) == "11100010"  # two's complement, mixed widths
    assert bitstring([], 8) == ""
    with pytest.raises(ValueError, match="2 values but 3 widths"):
        bitstring([1, 2], [1, 2, 3])
    text = "w # 0 # 1 # 'B20' # bitstring([0xABC, I], [12, 8])\n"
    text += "l # 3 # 1 # 'b8' # '10000000'\n"
    assert frames(text, 2) == bytes([0xAB, 0xC0, 0x00, 0x01]) + bytes([0xAB, 0xC0, 0x10, 0x01])

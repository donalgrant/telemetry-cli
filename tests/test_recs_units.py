"""recs's command line, its fixes, and the guard against endless loops."""

from __future__ import annotations

import io
import subprocess
import sys

import pytest

from telemetry_cli.recs.cli import main
from telemetry_cli.recs.extract import Extractor, RecsError

STREAM = b"noise<rec>one</rec>junk<rec>two</rec><rec>three</rec>tail"


def recs(*args, data=STREAM):
    out, err = io.BytesIO(), io.StringIO()
    code = main(list(args), stdin=io.BytesIO(data), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_start_to_start_from_stdin():
    assert recs("-", "-nl", "<rec>")[1] == b"<rec>one</rec>junk\n<rec>two</rec>\n"


def test_file_input(tmp_path):
    f = tmp_path / "s"
    f.write_bytes(STREAM)
    assert recs(str(f), "-x", "-z", "-e", "</rec>", "<rec>")[1] == b"onetwothree"


def test_padding_is_null_bytes_by_default():
    code, out, _ = recs("-", "-x", "-z", "-e", "</rec>", "-min_reclen=5", "<rec>")
    assert out == b"one\0\0two\0\0three"


def test_warnings_go_to_stderr():
    # \w+ matches more than its own 3 bytes
    code, out, err = recs("-", "-r", r"\w+")
    assert code == 0 and out.startswith(b"noise<rec>")
    assert "recs: warning: Matched bytes (5) is larger than mml parameter (3)" in err


def test_help():
    code, out, _ = recs("-help")
    assert code == 0 and b"record extraction utility" in out


def test_self_test_option():
    code, _, err = recs("-test")
    assert code == 0 and "test suite" in err


@pytest.mark.parametrize(
    "args,message",
    [
        ((), "no input file"),
        (("-",), "no record start marker"),
        (("-", ""), "marker is empty"),
        (("-", "x", "ten"), "must be a number"),
        (("-", "-bogus", "x"), "Unknown option: bogus"),
        (("-", "-r", "[", "4"), "can't use the regex"),
        (("no-such-file", "x"), "Can't open no-such-file"),
    ],
)
def test_errors(args, message):
    code, _, err = recs(*args)
    assert code != 0 and message in err


def test_markers_that_consume_nothing_are_stopped():
    with pytest.raises(RecsError, match="without consuming"):
        Extractor(io.BytesIO(STREAM), io.BytesIO()).str_n(b"<rec>", 0)


def test_empty_fill_is_an_error_when_padding():
    code, _, err = recs("-", "-x", "-z", "-e", "</rec>", "-f", "", "-min_reclen=9", "<rec>")
    assert code != 0 and "fill string is empty" in err


def test_broken_pipe_is_quiet():
    class Closed(io.BytesIO):
        def write(self, b):
            raise BrokenPipeError

    code = main(
        ["-", "<rec>", "4"], stdin=io.BytesIO(STREAM), stdout=Closed(), stderr=io.StringIO()
    )
    assert code == 0


def test_runs_as_a_program():
    p = subprocess.run(
        [sys.executable, "-m", "telemetry_cli.recs", "-", "-x", "<rec>", "3"],
        input=STREAM,
        capture_output=True,
        check=False,
    )
    assert p.returncode == 0 and p.stdout == b"onetwothr"

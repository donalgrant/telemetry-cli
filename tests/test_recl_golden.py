"""recl's output has the Perl original's form, on every golden case.

The Perl's scores were wrong, so the numbers that come from them (RESULT,
CORR and the scores in -verbose output) are masked; see
tests/golden/recl/cases.py.
"""

from __future__ import annotations

import io
import re

import pytest
from golden_cases import TESTS, expected, load_cases

from telemetry_cli.recl.cli import main

CASES = load_cases("recl")
MASKS = [
    (re.compile(r"^RESULT \d+$"), "RESULT #"),
    (re.compile(r"^CORR \S+$"), "CORR #"),
    (re.compile(r"corr \S+ accum-corr \S+$"), "corr # accum-corr #"),
    (re.compile(r"^NOTE +\S+% for reclen \d+$"), "NOTE #% for reclen #"),
]


def masked(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        for pattern, repl in MASKS:
            line = pattern.sub(repl, line)
        out.append(line)
    return out


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_recl(case, monkeypatch):
    monkeypatch.chdir(TESTS)
    out, err = io.BytesIO(), io.StringIO()
    code = main(case.args, stdin=io.BytesIO(case.stdin_bytes()), stdout=out, stderr=err)
    if case.error:
        assert code != 0 and case.error in err.getvalue()
        return
    exp = expected("recl", case)
    if exp.stderr == ["(timed out)"]:  # the Perl looped forever (no lengths to check)
        assert code != 0 and "no record lengths" in err.getvalue()
        return
    if not exp.ok and "Illegal division by zero" in exp.stderr:
        # The Perl had no whole buffer to use; the Python compares the data as
        # one piece. The lengths checked are the same.
        assert code == 0, err.getvalue()
        assert masked(out.getvalue().decode())[0] == masked(exp.stdout.decode())[0]
        return
    assert code == 0, err.getvalue()
    got = masked(out.getvalue().decode())
    want = masked(exp.stdout.decode())
    if case.fix:  # hand-maintained: the Python version's own output
        assert got == want
        return
    assert exp.ok
    assert got == want

"""tgen reproduces the Perl original's output on every golden case.

Progress reports are compared line by line; other stderr output is ignored,
since the Perl also printed warnings about its own code there.
"""

from __future__ import annotations

import io
import re

import pytest
from golden_cases import TESTS, expected, load_cases

from telemetry_cli.tgen.cli import main

CASES = load_cases("tgen")
PROGRESS = re.compile(r"^\d+/\d+$")


def progress(lines):
    return [line for line in lines if PROGRESS.match(line)]


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_tgen(case, monkeypatch):
    monkeypatch.chdir(TESTS)
    out, err = io.BytesIO(), io.StringIO()
    code = main(case.args, stdout=out, stderr=err)
    if case.error:
        assert code != 0 and case.error in err.getvalue()
        return
    exp = expected("tgen", case)
    if not exp.ok:
        assert code != 0, out.getvalue()[:200]
        return
    assert code == 0, err.getvalue()
    assert out.getvalue() == exp.stdout
    assert progress(err.getvalue().splitlines()) == progress(exp.stderr)

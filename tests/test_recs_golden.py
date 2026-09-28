"""recs reproduces the Perl original's output on every golden case.

The Perl printed warnings into stdout, between the records; tools/make_golden.py
moves them to the expected stderr, where the Python version prints them.
"""

from __future__ import annotations

import io

import pytest
from golden_cases import TESTS, expected, load_cases

from telemetry_cli.recs.cli import main

CASES = load_cases("recs")


def run_recs(case, monkeypatch):
    monkeypatch.chdir(TESTS)
    out, err = io.BytesIO(), io.StringIO()
    code = main(case.args, stdin=io.BytesIO(case.stdin_bytes()), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_recs(case, monkeypatch):
    code, out, err = run_recs(case, monkeypatch)
    if case.error:
        assert code != 0, out[:200]
        assert case.error in err
        return
    exp = expected("recs", case)
    if not exp.ok:
        assert code != 0, out[:200]
        assert exp.stderr[-1].split(" at ")[0].split(":")[0] in err
        return
    assert code == 0, err
    assert out == exp.stdout
    warnings = [line for line in err.splitlines() if line.strip()]
    assert len(warnings) == len(exp.stderr), err
    for got, want in zip(warnings, exp.stderr, strict=True):
        assert want in got

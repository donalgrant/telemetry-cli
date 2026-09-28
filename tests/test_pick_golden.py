"""pick reproduces the Perl original's output on every golden case.

See tests/golden_cases.py for how cases work, and tests/golden/pick/cases.py
for the case matrix.
"""

from __future__ import annotations

import io
import os

import pytest
from golden_cases import TESTS, expected, load_cases

from telemetry_cli import __version__
from telemetry_cli.pick.cli import main

CASES = load_cases("pick")
MATCHED_NEITHER = b"Matched neither a move nor a data request"
BY_ID = {c.id: c for c in CASES}


def run_pick(case, monkeypatch):
    monkeypatch.chdir(TESTS)
    monkeypatch.delenv("PICKPATH", raising=False)
    for k, v in case.env.items():
        monkeypatch.setenv(k, v)
    out, err = io.BytesIO(), io.StringIO()
    code = main(
        case.args,
        stdin=io.BytesIO(case.stdin_bytes()),
        stdout=out,
        stderr=err,
        host_order=case.host,
    )
    return code, out.getvalue(), err.getvalue()


def _lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_pick(case, monkeypatch):
    code, out, err = run_pick(case, monkeypatch)

    if case.mirror:
        twin = BY_ID[case.mirror]
        code2, out2, err2 = run_pick(twin, monkeypatch)
        assert (code, out) == (code2, out2), f"differs from {twin.id}"
        return

    if case.error:
        assert code != 0, out
        assert case.error in err
        return

    exp = expected("pick", case)
    if MATCHED_NEITHER in exp.stdout:
        # The Perl printed this error to stdout and exited 0; now it's an error.
        assert code != 0, out
        assert MATCHED_NEITHER.decode() in err
        return
    if not exp.ok:
        assert code != 0, f"expected an error ({exp.stderr[-1:]}); got output {out[:200]!r}"
        message = exp.stderr[-1] if exp.stderr else ""
        assert message in err, err
        return

    assert code == 0, err
    if case.fix == "pick help text":  # the help shows the version
        out = out.replace(__version__.encode(), b"VERSION")
    assert out == exp.stdout
    assert _lines(err) == exp.stderr


def test_every_case_is_checked():
    """Mirror cases must point at a case with an oracle."""
    for c in CASES:
        if c.mirror:
            assert not BY_ID[c.mirror].mirror, c.id
    assert os.path.isdir(TESTS / "fixtures")

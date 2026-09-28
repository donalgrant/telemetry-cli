"""The golden case tables are well-formed and their outputs have been generated."""

import pytest
from golden_cases import GOLDEN, load_cases, load_index

TOOLS = sorted(d.name for d in GOLDEN.iterdir() if d.is_dir())


def _needs_output(case):
    return not case.mirror and not (case.fix and case.error)


@pytest.mark.parametrize("tool", TOOLS)
def test_every_case_has_golden_output(tool):
    index = load_index(tool)
    cases = [c for c in load_cases(tool) if _needs_output(c)]
    missing = [c.id for c in cases if c.id not in index]
    assert not missing, f"run: python tools/make_golden.py {tool}"
    for c in cases:
        assert (GOLDEN / tool / f"{c.id}.out").exists(), c.id


@pytest.mark.parametrize("tool", TOOLS)
def test_no_orphan_outputs(tool):
    ids = {c.id for c in load_cases(tool)}
    orphans = [f.name for f in (GOLDEN / tool).glob("*.out") if f.stem not in ids]
    assert not orphans

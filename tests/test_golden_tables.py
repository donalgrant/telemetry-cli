"""The golden case tables are well-formed and their outputs have been generated."""

import pytest
from golden_cases import GOLDEN, load_cases, load_index

TOOLS = sorted(d.name for d in GOLDEN.iterdir() if d.is_dir())


@pytest.mark.parametrize("tool", TOOLS)
def test_every_case_has_golden_output(tool):
    index = load_index(tool)
    missing = [c.id for c in load_cases(tool) if c.id not in index]
    assert not missing, f"run: python tools/make_golden.py {tool}"
    for c in load_cases(tool):
        assert (GOLDEN / tool / f"{c.id}.out").exists()

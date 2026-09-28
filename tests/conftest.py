import os
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

# Profiles for the Hypothesis tests that compare against perl. "ci" is the
# default; use HYPOTHESIS_PROFILE=deep (or --hypothesis-profile=deep) for a
# longer search.
_fuzz = {"deadline": None, "suppress_health_check": [HealthCheck.too_slow]}
settings.register_profile("ci", max_examples=150, **_fuzz)
settings.register_profile("deep", max_examples=5000, **_fuzz)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))

HERE = Path(__file__).parent
ROOT = HERE.parent
LEGACY = ROOT / "legacy"
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"

PERL = shutil.which("perl")


def perl(args, stdin=b"", cwd=None):
    """Run perl with the legacy library path: perl(args, stdin) -> CompletedProcess."""
    return subprocess.run(
        [PERL, "-I", str(LEGACY), *args],
        input=stdin,
        capture_output=True,
        cwd=cwd,
        check=False,
    )


def pytest_collection_modifyitems(config, items):
    if PERL:
        return
    skip = pytest.mark.skip(reason="perl not available")
    for item in items:
        if "oracle" in item.keywords:
            item.add_marker(skip)

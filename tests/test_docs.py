"""Every ```console example in the docs and README runs and prints what it shows.

A console block is a series of "$ command" lines, each followed by its
expected output. The commands run with bash in a fresh temporary directory,
with the package's commands on the PATH. Trailing spaces are ignored, since
pick's output lines end with spaces that don't survive in Markdown.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
BLOCK = re.compile(r"^```console\n(.*?)^```", re.MULTILINE | re.DOTALL)


def blocks():
    for doc in DOCS:
        for n, m in enumerate(BLOCK.finditer(doc.read_text()), 1):
            yield pytest.param(m.group(1), id=f"{doc.name}-{n}")


def steps(block: str):
    """(command, expected output lines) pairs."""
    out = []
    for line in block.splitlines():
        if line.startswith("$ "):
            out.append((line[2:], []))
        elif out:
            out[-1][1].append(line.rstrip())
    return out


@pytest.fixture(scope="module")
def workdir(tmp_path_factory):
    # blocks within one document may build on each other's files
    return tmp_path_factory.mktemp("docs")


@pytest.mark.parametrize("block", list(blocks()))
def test_console_example(block, workdir):
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
    env.pop("PICKPATH", None)
    for command, expected in steps(block):
        p = subprocess.run(
            ["bash", "-c", command], cwd=workdir, env=env, capture_output=True, text=True,
            check=False,
        )  # fmt: skip
        got = [line.rstrip() for line in p.stdout.splitlines()]
        assert got == expected, f"$ {command}\n{p.stderr}"

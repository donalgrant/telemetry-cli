"""Every ```console example in the docs and README runs and prints what it shows.

A console block is a series of "$ command" lines, each followed by its
expected output. A block preceded by an HTML comment ``<!-- file: NAME -->``
is written to the file NAME before the examples after it run. The commands
run with bash in a fresh temporary directory, with the package's commands on
the PATH. Trailing spaces are ignored, since
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
MARK = "@@command-"
BLOCK = re.compile(
    r"(?:<!-- file: (\S+) -->\n)?^```(console|\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL
)


def blocks():
    """(files to write, console block) for each console block, in order."""
    for doc in DOCS:
        files: dict[str, str] = {}
        n = 0
        for m in BLOCK.finditer(doc.read_text()):
            name, kind, body = m.groups()
            if name:
                files[name] = body
            elif kind == "console":
                n += 1
                yield pytest.param(dict(files), body, id=f"{doc.name}-{n}")


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


@pytest.mark.parametrize("files,block", list(blocks()))
def test_console_example(files, block, workdir):
    for name, text in files.items():
        (workdir / name).write_text(text)
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
    env.pop("PICKPATH", None)
    # Run the block's commands in one shell, as a reader would type them, so
    # variables carry over; a marker line before each command splits the output.
    commands = steps(block)
    script = "".join(f"echo '{MARK}{i}'\n{command}\n" for i, (command, _) in enumerate(commands))
    p = subprocess.run(
        ["bash", "-c", script], cwd=workdir, env=env, capture_output=True, text=True,
        check=False,
    )  # fmt: skip
    outputs = re.split(rf"^{MARK}\d+\n", p.stdout, flags=re.MULTILINE)[1:]
    assert len(outputs) == len(commands), p.stderr
    for (command, expected), out in zip(commands, outputs, strict=True):
        got = [line.rstrip() for line in out.splitlines()]
        assert got == expected, f"$ {command}\n{p.stderr}"

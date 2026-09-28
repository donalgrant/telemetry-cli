"""Golden test cases: the command lines run through the Perl originals.

Each tool has a directory ``tests/golden/<tool>/`` holding

    cases.toml   hand-written cases
    cases.py     optional; defines CASES, a list of generated cases
    index.json   written by tools/make_golden.py: exit status and stderr per case
    <id>.out     written by tools/make_golden.py: the exact stdout bytes

A case is a table with these keys:

    id     unique name, used for the .out file
    args   argument list (paths are relative to tests/)
    stdin  optional path of a file to feed on stdin (relative to tests/)
    env    optional extra environment variables
    fix    optional: the Python version deliberately differs from the Perl here.
           The value names the CHANGELOG entry. make_golden.py never overwrites
           the .out and index entry of a fix case; they are maintained by hand.
    note   optional free text

Commands run with tests/ as the working directory.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

TESTS = Path(__file__).parent
GOLDEN = TESTS / "golden"
_ID = re.compile(r"^[A-Za-z0-9._+-]+$")


@dataclass
class Case:
    id: str
    args: list[str]
    stdin: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    fix: str | None = None
    note: str | None = None

    def stdin_bytes(self) -> bytes:
        return (TESTS / self.stdin).read_bytes() if self.stdin else b""


def load_cases(tool: str) -> list[Case]:
    d = GOLDEN / tool
    raw: list[dict] = []
    toml_file = d / "cases.toml"
    if toml_file.exists():
        raw += tomllib.loads(toml_file.read_text()).get("case", [])
    py_file = d / "cases.py"
    if py_file.exists():
        spec = importlib.util.spec_from_file_location(f"golden_{tool}_cases", py_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        raw += list(mod.CASES)
    cases = [Case(**c) for c in raw]
    seen = set()
    for c in cases:
        if not _ID.match(c.id):
            raise ValueError(f"{tool}: bad case id {c.id!r}")
        if c.id in seen:
            raise ValueError(f"{tool}: duplicate case id {c.id!r}")
        seen.add(c.id)
    return cases


# Perl's die appends " at <script> line N." (and ", <FH> line M."); drop it so
# messages can be compared across implementations.
_PERL_AT = re.compile(r" at \S+ line \d+(?:, <\w+> (?:line|chunk) \d+)?\.$")


def normalize_stderr(text: str) -> list[str]:
    return [_PERL_AT.sub("", line).rstrip() for line in text.splitlines() if line.strip()]


@dataclass
class Expected:
    stdout: bytes
    ok: bool  # exit status zero?
    stderr: list[str]


def load_index(tool: str) -> dict:
    f = GOLDEN / tool / "index.json"
    return json.loads(f.read_text()) if f.exists() else {}


def expected(tool: str, case: Case) -> Expected:
    entry = load_index(tool)[case.id]
    return Expected(
        stdout=(GOLDEN / tool / f"{case.id}.out").read_bytes(),
        ok=entry["exit"] == 0,
        stderr=entry["stderr"],
    )

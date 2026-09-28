"""Golden test cases: the command lines run through the Perl originals.

Each tool has a directory ``tests/golden/<tool>/`` holding

    cases.toml   hand-written cases
    cases.py     optional; defines CASES, a list of generated cases
    index.json   written by tools/make_golden.py: exit status and stderr per case
    <id>.out     written by tools/make_golden.py: the exact stdout bytes

A case is a table with these keys:

    id     unique name, used for the .out file. Ids must differ other than in
           case (macOS disks ignore case); generated ids write an uppercase
           letter X as "+x".
    args   argument list (paths are relative to tests/)
    stdin  optional path of a file to feed on stdin (relative to tests/)
    env    optional extra environment variables
    note   optional free text
    host   "little" (default) or "big": the byte order of the machine the case
           emulates. Big-host cases run a copy of the Perl patched to read data
           as big-endian (see tools/make_golden.py). That is how pick behaved on
           the Sun and SGI machines it was written for, and it is the reference
           for pick's intended behavior. The Python side runs with the same host
           order.
    error  optional: the Python version must fail, with this text in stderr.
           Needed only where the Perl reported an error but exited 0. When the
           Perl exits nonzero, the case is an error case automatically.
    oracle optional, "big-host-r": get the expected output of this little-host
           case by running the big-host Perl with -r switched on (or off).
           That reads every item as little-endian, one item at a time: the
           intended behavior. Use it where a little-endian file has no
           big-endian twin to mirror (e.g. items that overlap other items).
           Not valid for complex types (whose -r was wrong) or the U format.
    fix    optional: the Python version deliberately differs from the Perl here.
           The value names the CHANGELOG entry. A fix case also needs one of:
    mirror    the id of another case whose Python output this case must equal
              (no Perl run). Used where the little-endian Perl is wrong and the
              big-host case is the reference.
    perl_args arguments that make the Perl produce the intended output, e.g.
              "zRI" for the documented meaning of "zg".
              If neither is given, <id>.out is maintained by hand.

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
    host: str = "little"
    error: str | None = None
    mirror: str | None = None
    perl_args: list[str] | None = None
    oracle: str | None = None

    @property
    def runs_perl(self) -> bool:
        return not self.mirror and not (self.fix and self.perl_args is None and not self.oracle)

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
        if c.id.lower() in seen:  # .out files must not clash on case-insensitive disks
            raise ValueError(f"{tool}: duplicate case id {c.id!r} (ignoring case)")
        if c.host not in ("little", "big"):
            raise ValueError(f"{tool}/{c.id}: host must be 'little' or 'big'")
        if c.oracle not in (None, "big-host-r") or (c.oracle and c.host != "little"):
            raise ValueError(f"{tool}/{c.id}: oracle 'big-host-r' is for little-host cases")
        if (c.mirror or c.perl_args is not None or c.oracle) and not c.fix:
            raise ValueError(f"{tool}/{c.id}: mirror, perl_args and oracle need a fix entry")
        seen.add(c.id.lower())
    ids = {c.id for c in cases}
    for c in cases:
        if c.mirror and c.mirror not in ids:
            raise ValueError(f"{tool}/{c.id}: mirror {c.mirror!r} is not a case")
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

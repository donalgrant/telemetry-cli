"""Differential fuzzing of tgen and its converter.

Hypothesis writes random Perl command files: items at random offsets, with
arithmetic, %, bit operations, rand(), references to earlier items, triggers,
string and array values, and fill modes. Each file runs through the Perl tgen
as it is, and through the Python tgen after tgen --convert, with the same
seed; the output must be byte for byte the same.

    pytest tests/test_tgen_fuzz.py
    HYPOTHESIS_PROFILE=deep pytest tests/test_tgen_fuzz.py
"""

from __future__ import annotations

import io
import subprocess

import pytest
from conftest import LEGACY, PERL
from hypothesis import given
from hypothesis import strategies as st

from telemetry_cli.tgen import cmdfile
from telemetry_cli.tgen.convert import convert
from telemetry_cli.tgen.runtime import Generator

pytestmark = pytest.mark.oracle

INT_TYPES = ["C", "c", "S", "s", "L", "l", "n", "N", "v", "V"]
FLOAT_TYPES = ["f", "d"]


@st.composite
def int_expr(draw, names, depth=0):
    atoms = ["$::I", str(draw(st.integers(0, 300))), "$::k"] + [
        f"$P{{{n}}}{{value}}" for n in names
    ]
    if depth > 2 or draw(st.integers(0, 2)) == 0:
        return draw(st.sampled_from(atoms))
    a = draw(int_expr(names, depth + 1))
    b = draw(int_expr(names, depth + 1))
    op = draw(st.sampled_from(["+", "-", "*", "%", "&", "|"]))
    if op == "%":
        return f"({a}) % ({draw(st.integers(1, 17))})"
    if op in "&|":
        return f"(abs({a}) {op} abs({b}))"
    return f"({a} {op} {b})"


@st.composite
def float_expr(draw, names):
    a = draw(int_expr(names))
    form = draw(st.integers(0, 3))
    if form == 0:
        return f"({a}) / {draw(st.integers(1, 9))}.0"
    if form == 1:
        return f"rand({draw(st.integers(1, 100))})"
    if form == 2:
        return f"sqrt(abs({a}))"
    return f"int(rand(1000)) + ({a})/3"


@st.composite
def command_file(draw):
    lines = ["$::k=" + str(draw(st.integers(0, 50))) + ";"]
    names: list[str] = []
    for n in range(draw(st.integers(1, 7))):
        name = f"item{n}"
        kind = draw(st.sampled_from(["int", "float", "text", "array", "calc"]))
        offset = str(draw(st.integers(0, 40)))
        trigger = draw(st.sampled_from(["1", "1", "$::I % 2", "($::I % 3) == 1", "$::k > 10"]))
        if kind == "int":
            typ, value = f"'{draw(st.sampled_from(INT_TYPES))}'", draw(int_expr(names))
        elif kind == "float":
            typ, value = f"'{draw(st.sampled_from(FLOAT_TYPES))}'", draw(float_expr(names))
        elif kind == "text":
            typ = f"'{draw(st.sampled_from(['a', 'A', 'Z']))}{draw(st.integers(1, 8))}'"
            value = f"'id' . {draw(int_expr(names))}"
        elif kind == "array":
            k = draw(st.integers(1, 4))
            typ = f"'{draw(st.sampled_from(INT_TYPES))}{k}'"
            value = "[ " + ", ".join(draw(int_expr(names)) for _ in range(k)) + " ]"
        else:
            offset, typ, value = "-1", "X", draw(int_expr(names))
        lines.append(f"{name} # {offset} # {trigger} # {typ} # {value}")
        if trigger == "1" and kind in ("int", "float", "calc"):
            # later items may use its value. (Using a string or array value as a
            # number gave garbage in the Perl, and is an error in the Python.)
            names.append(name)
    return "\n".join(lines) + "\n"


def run_perl(text, args, seed, tmp_path):
    f = tmp_path / "cmd.tgen"
    f.write_text(text)
    p = subprocess.run(
        [
            PERL,
            "-I",
            str(LEGACY),
            "-e",
            "$0 = shift @ARGV; srand(shift @ARGV); do $0; die $@ if $@",
            str(LEGACY / "tgen" / "tgen"),
            str(seed),
            *args,
            str(f),
            "6",
            "3",
        ],  # fmt: skip
        capture_output=True,
        timeout=20,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
        cwd=tmp_path,
    )
    return p


def run_python(text, fill, seed):
    items, statements = cmdfile.parse(convert(text))
    out = io.BytesIO()
    Generator(items, statements, fill=fill, seed=seed, stderr=io.StringIO()).run(
        out, 6, 3, quiet=True
    )
    return out.getvalue()


@given(
    text=command_file(), fill=st.sampled_from(["0", "255", "random"]), seed=st.integers(0, 2**31)
)
def test_random_command_files_match_perl(text, fill, seed, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tgen")
    args = ["-q", "-r"] if fill == "random" else ["-q", "-f", fill]
    perl = run_perl(text, args, seed, tmp)
    assert perl.returncode == 0, perl.stderr.decode()[-500:]
    got = run_python(text, "random" if fill == "random" else int(fill), seed)
    assert got == perl.stdout, text

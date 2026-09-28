"""tgen --convert: Perl command files to the Python form."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURES, LEGACY

from telemetry_cli.tgen.convert import convert, expr, statement

PERL_FIXTURES = sorted((FIXTURES / "tgen" / "perl").glob("*.tgen"))
EXAMPLES = Path(__file__).parent.parent / "src" / "telemetry_cli" / "tgen" / "examples"


@pytest.mark.parametrize("perl", PERL_FIXTURES, ids=[p.stem for p in PERL_FIXTURES])
def test_fixtures_are_the_converter_output(perl):
    """The Python fixtures (checked by the golden tests) are exactly what --convert makes."""
    assert convert(perl.read_text()) == (FIXTURES / "tgen" / perl.name).read_text()


@pytest.mark.parametrize(
    "name", [p.name for p in sorted((LEGACY / "tgen" / "examples").glob("*.tgen"))]
)
def test_bundled_examples_are_the_converted_originals(name):
    got = convert((LEGACY / "tgen" / "examples" / name).read_text())
    bundled = (EXAMPLES / name).read_text()
    if name == "subcom.tgen":  # reads itself, from its own directory
        old = "FILE='../examples/subcom.tgen'  # use this file for example subcom data"
        new = "FILE='subcom.tgen'  # use this file for example subcom data (run from its directory)"
        got = got.replace(old, new)
    assert got == bundled


@pytest.mark.parametrize(
    "perl,python",
    [
        ("$::I % 256", "pmod(I, 256)"),
        ("($::I/2) % 256", "pmod(I/2, 256)"),
        ("$P{pn}{value}&0xff", "pand(P.pn.value, 0xff)"),
        ("($::I & 3) | 0x40", "por(pand(I, 3), 0x40)"),
        ("$P{random_number}{_value}>0.5", "P.random_number._value>0.5"),
        ("$::F=0", "F=0"),
        ("--$::I if $P{random}{value}<0.5", "I = I - 1 if P.random.value<0.5 else I"),
        ("$::COUNT1++ if $::x>0.5; $::COUNT1;", "COUNT1 = COUNT1 + 1 if x>0.5 else COUNT1; COUNT1"),
        ("[ map { $_ * 2 } (1..$::n) ]", "[ _ * 2  for _ in range(1, n + 1)]"),
        ("my $a=45.0/57.3; [cos($a),sin($a)]", "a=45.0/57.3; [cos(a),sin(a)]"),
        ('"C$::ns"', 'f"C{ns}"'),
        ('"L"', '"L"'),
        ("$::name . '!'", "cat(name, '!')"),
        ("' #'.' '", "cat(' #', ' ')"),
        ("1.5 + .5", "1.5 + .5"),
        ("$::a && !$::b || $::c", "a  and   not b  or  c"),
        (
            "seek_file('a', '8*$::O', 4, 'f', '$::X>$::I/10.0')",
            "seek_file('a', '8*O', 4, 'f', 'X>I/10.0')",
        ),  # fmt: skip
    ],
)
def test_field_translation(perl, python):
    assert expr(perl) == python


@pytest.mark.parametrize(
    "perl,python",
    [
        ("$::PN = 0x03915ed3;  # PN sequence constant", "PN = 0x03915ed3  # PN sequence constant"),
        ("@::f = map { $::f0+$_*$::df } (1..$::nf);", "f = [ f0+_*df  for _ in range(1, nf + 1)]"),
        (
            'print STDERR "Debugging is ON!\\n" if $::DEBUG;',
            'if DEBUG: print("Debugging is ON!\\n", file=stderr, end="")',
        ),  # fmt: skip
    ],
)
def test_statement_translation(perl, python):
    assert statement(perl) == python


def test_untranslatable_lines_are_marked():
    out = convert("$::PRF=sub { 420.0+$::T/10.0; }\nx # 0 # 1 # 'C' # $h->{a}\n")
    lines = out.splitlines()
    assert lines[0] == "# TODO(convert): this line still contains Perl"
    assert lines[2] == "# TODO(convert): this line still contains Perl"


def test_comments_and_continuations():
    out = convert("# c1\n! c2\n; c3\na # 0 \\\n  # 1 # 'C' # 7\n")
    assert out.splitlines() == ["# c1", "! c2", "; c3", "a # 0   # 1 # 'C' # 7"]


def test_the_perl_scratch_files(tmp_path, monkeypatch):
    """tgen's own scratch test files: one uses a Perl closure (marked), the other a
    function it never defines (converted, and fails loudly when run)."""
    import io

    from telemetry_cli.tgen.cli import main

    assert "TODO(convert)" in convert((LEGACY / "tgen" / "tests" / "aux.cmd").read_text())
    gen = tmp_path / "gen.tgen"
    gen.write_text(convert((LEGACY / "tgen" / "tests" / "gen.cmd").read_text()))
    monkeypatch.chdir(tmp_path)
    err = io.StringIO()
    assert main([str(gen)], stdout=io.BytesIO(), stderr=err) != 0
    assert "NameError" in err.getvalue()

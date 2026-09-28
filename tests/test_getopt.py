"""_getopt reads options the way Perl's Getopt::Long did."""

import json

import pytest
from conftest import perl
from hypothesis import given
from hypothesis import strategies as st

from telemetry_cli._getopt import OptionError, getoptions

RECS = ["v", "x", "z", "mml=i", "e=s", "a", "f=s", "r", "test", "help", "min_reclen=i",
        "max_reclen=i", "append=s", "prepend=s", "nl"]  # fmt: skip
RECL = ["v|verbose", "h|help", "f|full", "q|quiet", "part|partial", "skip|header=i", "min=i",
        "max=i", "minrecs=i", "maxbufs=i", "fact|factor|mult=i", "only=s", "limit=i",
        "reduce=f"]  # fmt: skip

PERL_GETOPT = r"""
use Getopt::Long; use JSON::PP;
my @specs = split(/,/, shift);
my %o; local $SIG{__WARN__} = sub { print STDERR $_[0] };
my $ok = GetOptions(\%o, @specs);
print encode_json({ok => $ok ? 1 : 0, opts => \%o, args => \@ARGV});
"""


def perl_getopt(specs, argv):
    p = perl(["-e", PERL_GETOPT, ",".join(specs), *argv])
    r = json.loads(p.stdout)
    return r, p.stderr.decode().strip()


@pytest.mark.parametrize(
    "argv,opts,args",
    [
        (["file", "ab", "4", "-x"], {"x": 1}, ["file", "ab", "4"]),
        (["-X", "file"], {"x": 1}, ["file"]),
        (["-e=zz", "--e", "yy"], {"e": "yy"}, []),
        (["-ma", "10", "-min=2"], {"max_reclen": 10, "min_reclen": 2}, []),
        (["-n", "-p", ">"], {"nl": 1, "prepend": ">"}, []),
        (["-e", "-r"], {"e": "-r"}, []),
        (["-", "--", "-x"], {}, ["-", "-x"]),
        (["-mml", "+3", "-f", ""], {"mml": 3, "f": ""}, []),
    ],
)
def test_recs_options(argv, opts, args):
    assert getoptions(argv, RECS) == (opts, args)


@pytest.mark.parametrize(
    "argv,message",
    [
        (["-mml=x"], 'Value "x" invalid for option mml (number expected)'),
        (["-m", "3"], "Option m is ambiguous (max_reclen, min_reclen, mml)"),
        (["-5"], "Unknown option: 5"),
        (["-xz"], "Unknown option: xz"),
        (["-e"], "Option e requires an argument"),
        (["-e="], "Option e requires an argument"),
        (["-x=1"], "Option x does not take an argument"),
    ],
)
def test_recs_option_errors(argv, message):
    with pytest.raises(OptionError, match=message.replace("(", r"\(").replace(")", r"\)")):
        getoptions(argv, RECS)


def test_aliases_share_one_key():
    assert getoptions(["-verbose", "--mult", "8", "-header=4"], RECL) == (
        {"v": 1, "fact": 8, "skip": 4},
        [],
    )
    assert getoptions(["-reduce", "2.5"], RECL)[0] == {"reduce": 2.5}


WORDS = ["-x", "-X", "-mml", "-mml=4", "-m", "-ma", "-min", "-e", "-e=q", "-f", "--nl", "-n",
         "-n=1", "-a", "-ap", "-p", "-t", "-5", "--", "-", "file", "ab", "3", "-3", "x", "-r",
         "-mml=", "-MA=2"]  # fmt: skip


@pytest.mark.oracle
@given(argv=st.lists(st.sampled_from(WORDS), max_size=6))
def test_matches_getopt_long(argv):
    expected, warning = perl_getopt(RECS, argv)
    try:
        opts, args = getoptions(argv, RECS)
    except OptionError as e:
        assert not expected["ok"]
        assert str(e) in warning
        return
    assert expected["ok"], warning
    assert (opts, args) == (expected["opts"], expected["args"])

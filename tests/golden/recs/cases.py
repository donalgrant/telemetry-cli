"""Generated recs golden cases. See tests/golden_cases.py for the format.

Markers with bytes above 0x7f go into argv as surrogate escapes (os.fsdecode),
which is how both the Perl and the Python version receive raw bytes.
"""

from __future__ import annotations

import itertools
import os

CASES: list[dict] = []

SYNC = os.fsdecode(bytes.fromhex("03915ed3"))  # a plain-string marker
SYNC_RE = r"\x03\x91\x5e\xd3"  # the same, as a regex
FILL_FIX = "recs null fill"


def add(id, args, **kw):
    CASES.append({"id": id, "args": list(args), **kw})


def pads(args) -> bool:
    """Does this command line pad records, with the default fill?"""
    pad_opts = {"-a", "-min_reclen", "-min"}
    return any(a.split("=")[0] in pad_opts for a in args) and not any(
        a.split("=")[0] == "-f" for a in args
    )


def add_padded(id, args, **kw):
    """A case that may pad with the default fill. The Perl padded with the
    character "0"; the Python pads with nulls, as documented. The Perl, given
    -f with a byte that isn't in the input, shows where the padding goes."""
    if pads(args):
        kw |= {"fix": FILL_FIX, "perl_args": [*args, "-f", "\x01"], "perl_sub": ["01", "00"]}
    add(id, args, **kw)


# --- fixed-length records ----------------------------------------------------------

FIXED = [
    ("frames", "fixtures/frames.bin", SYNC, SYNC_RE),
    ("lines", "fixtures/lines.txt", "BEGIN", "BEGIN [0-9]+"),
    ("testfile", "fixtures/recs-testfile.txt", "345", "[0-9]{3}5"),
    ("big", "fixtures/big.bin", "@@REC", "@@REC[0-9]{2}"),
]
LENGTHS = [1, 4, 8, 13, 100, 1000, 3000]
FIXED_OPTIONS = [
    [],
    ["-x"],
    ["-a"],
    ["-a", "-x"],
    ["-min_reclen=50"],
    ["-max_reclen=6"],
    ["-a", "-f", "#"],
    ["-prepend", "<<", "-append", ">>"],
    ["-nl"],
    ["-append", "|", "-nl"],
    ["-mml=2"],
    ["-mml", "20"],
]
for (name, path, plain, regex), n, opts in itertools.product(FIXED, LENGTHS, FIXED_OPTIONS):
    tag = "_".join(o.strip("-").replace("=", "") for o in opts if o.startswith("-")) or "plain"
    add_padded(f"fixed-{name}-{n}-{tag}", [path, *opts, plain, str(n)])
    if n in (4, 100, 3000):
        add_padded(f"fixed-{name}-{n}-{tag}-r", [path, "-r", *opts, regex, str(n)])

# --- marker to marker ---------------------------------------------------------------------

BETWEEN = [
    ("lines", "fixtures/lines.txt", "BEGIN", "END", r"BEGIN \d+", r"END\n"),
    ("frames", "fixtures/frames.bin", SYNC, os.fsdecode(b"\x05"), SYNC_RE, r"[\x00-\x05]"),
    ("big", "fixtures/big.bin", "@@REC", "zz", r"@@REC\d\d", r"z{2,}"),
    ("testfile", "fixtures/recs-testfile.txt", "90", "\n", r"9\d", r"\n"),
]
BETWEEN_OPTIONS = [[], ["-x"], ["-z"], ["-x", "-z"], ["-a"], ["-a", "-x"], ["-max_reclen=10"],
                   ["-min_reclen=40", "-f=."], ["-min_reclen=40"], ["-prepend=[", "-append=]"],
                   ["-nl"], ["-mml=1"]]  # fmt: skip
for (name, path, start, stop, rstart, rstop), opts in itertools.product(BETWEEN, BETWEEN_OPTIONS):
    tag = "_".join(o.strip("-").split("=")[0] for o in opts) or "plain"
    # start to start (no end marker, no length)
    add_padded(f"between-{name}-start-{tag}", [path, *opts, start])
    add_padded(f"between-{name}-end-{tag}", [path, *opts, "-e", stop, start])
    add_padded(f"between-{name}-start-{tag}-r", [path, "-r", *opts, rstart])
    add_padded(f"between-{name}-end-{tag}-r", [path, "-r", *opts, f"-e={rstop}", rstart])

# --- stdin, option spelling, odd inputs ----------------------------------------------------

add("stdin-fixed", ["-", "BEGIN", "20"], stdin="fixtures/lines.txt")
add("stdin-between", ["-", "-e", "END", "BEGIN"], stdin="fixtures/lines.txt")
add("stdin-regex", ["-", "-r", SYNC_RE, "9"], stdin="fixtures/frames.bin")
add("options-first", ["-x", "-nl", "fixtures/lines.txt", "BEGIN", "8"])
add("options-abbreviated", ["fixtures/lines.txt", "-ma=5", "-pre", "*", "BEGIN", "8"])
add("options-double-dash", ["fixtures/lines.txt", "--nl", "--e=END", "BEGIN"])
add("options-uppercase", ["fixtures/lines.txt", "-X", "-NL", "BEGIN", "8"])
add(
    "end-of-options",
    ["fixtures/lines.txt", "--", "-", "3"],
    note="a marker that looks like an option",
)
add("marker-not-found", ["fixtures/lines.txt", "NOWHERE", "8"])
add("marker-not-found-between", ["fixtures/lines.txt", "NOWHERE"])
add("end-not-found", ["fixtures/lines.txt", "-e", "NOWHERE", "BEGIN"])
add("empty-input", ["fixtures/empty.bin", "BEGIN", "8"])
add("empty-input-between", ["fixtures/empty.bin", "BEGIN"])
add("zero-length", ["fixtures/lines.txt", "BEGIN", "0"], fix="recs endless loops",
    error="without consuming any input")  # fmt: skip
add("zero-length-x", ["fixtures/lines.txt", "-x", "-nl", "BEGIN", "0"])
add("regex-alternation", ["fixtures/lines.txt", "-r", "value|name", "6"])
add("regex-dot-matches-newline", ["fixtures/lines.txt", "-r", r"D\n.n", "6"])
add("regex-class", ["fixtures/lines.txt", "-r", "-e", r"[0-9]\n", "[a-z]+="])
add("long-match-warning", ["fixtures/big.bin", "-r", "-mml=1", r"@@REC\d+", "10"])
# Matches longer than -mml allows for print warnings (in marker-to-marker mode,
# and when -a looks for another start marker inside a record).
add("warn-start-to-start", ["fixtures/lines.txt", "-r", r"\w+"])
add("warn-end-marker", ["fixtures/recs-testfile.txt", "-r", "-e", r"\d+", "[0-9]{3}"])
add("warn-a-fixed", ["fixtures/lines.txt", "-r", "-a", "-f", ".", r"\w+", "12"])
add("warn-big-buffers", ["fixtures/big.bin", "-r", "-e", r"[a-f]+", r"@@REC\d+"])
add("warn-a-between", ["fixtures/lines.txt", "-r", "-a", "-e", r"END\n+", r"BEGIN \d+"])
add("verbose-accepted", ["fixtures/lines.txt", "-v", "BEGIN", "8"])

# --- errors -----------------------------------------------------------------------------

add("err-missing-file", ["fixtures/no-such-file", "BEGIN", "8"])
add("err-no-args", [], fix="recs arguments", error="no input file")
add("err-no-marker", ["fixtures/lines.txt"], fix="recs arguments", error="no record start marker")
add("err-bad-length", ["fixtures/lines.txt", "BEGIN", "ten"], fix="recs arguments",
    error="record length must be a number")  # fmt: skip
add("err-unknown-option", ["fixtures/lines.txt", "-q", "BEGIN"], fix="recs options",
    error="Unknown option: q")  # fmt: skip
add("err-ambiguous-option", ["fixtures/lines.txt", "-m", "3", "BEGIN"], fix="recs options",
    error="Option m is ambiguous")  # fmt: skip
add("err-bad-value", ["fixtures/lines.txt", "-mml=x", "BEGIN"], fix="recs options",
    error='Value "x" invalid for option mml')  # fmt: skip
add("err-bad-regex", ["fixtures/lines.txt", "-r", "(", "8"], error="(")
add("err-empty-fill",  # the Perl padded with "" forever
    ["fixtures/lines.txt", "-f", "", "-min_reclen=90", "BEGIN", "80"],
    fix="recs endless loops", error="fill string is empty")  # fmt: skip

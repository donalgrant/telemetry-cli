"""Generated recl golden cases. See tests/golden_cases.py for the format.

The Perl recl's scores were wrong (it compared only the first eighth of the
bits), so its RESULT and CORR values, and the scores in -verbose output,
aren't a reference; tests/test_recl_golden.py masks them. Everything else is
compared: which lengths are checked, the output lines and their order, and
the buffer counts. Whether recl finds the right length is tested separately,
on files of known record length (tests/test_recl_units.py).
"""

from __future__ import annotations

CASES: list[dict] = []


def add(id, args, **kw):
    CASES.append({"id": id, "args": list(args), **kw})


FILES = {
    "seq": "fixtures/seq.bin",  # 100 8-byte records
    "counter": "fixtures/counter.bin",  # 10 7-byte records
    "moc": "fixtures/moc.le.bin",  # 4 168-byte records
    "int32": "fixtures/int32.le.bin",  # 12 16-byte records
    "aux": "fixtures/aux.le.bin",  # 3 128-byte records
    "testfile": "fixtures/recs-testfile.txt",  # 3071 bytes of text
}
OPTIONS = {
    "default": [],
    "quiet": ["-q"],
    "max": ["-max=40"],
    "min-max": ["-min", "4", "-max", "30"],
    "fact": ["-fact=4"],
    "factor-alias": ["--mult", "2", "-max=50"],
    "partial": ["-partial", "-max=40"],
    "part-alias": ["-part", "-min=5", "-max=20"],
    "skip": ["-skip=4", "-max=60"],
    "header-alias": ["-header", "2", "-max=60"],
    "minrecs": ["-minrecs=5"],
    "maxbufs": ["-maxbufs=2", "-max=20"],
    "only": ["-only=7,8,16"],
    "verbose": ["-v", "-only", "4,8,16"],
    "verbose-q": ["-verbose", "-quiet", "-only=4,8"],
}
for fname, path in FILES.items():
    for oname, opts in OPTIONS.items():
        add(f"{fname}-{oname}", [path, *opts])

# The Perl accepted -full, -limit and -reduce but ignored them.
UNUSED = "recl options"
add("limit", ["fixtures/seq.bin", "-limit=400", "-max=40"], fix=UNUSED)
add("reduce", ["fixtures/seq.bin", "-reduce=4", "-max=40"], fix=UNUSED)
add("full", ["fixtures/seq.bin", "-full", "-max=40"], fix=UNUSED)
# The Perl sized its buffers from the last -only length, not the longest.
add("only-unsorted", ["fixtures/seq.bin", "-only=8,16,7"], fix="recl options")
# Reading stdin: the Perl needed -max, and took it as the file size.
add("stdin", ["-", "-max=40"], stdin="fixtures/seq.bin", fix="recl stdin")
# The Perl divided by zero when the data were shorter than a buffer...
add("short-data", ["fixtures/counter.bin", "-max=60"], fix="recl short data")
# ...and read zero-byte buffers forever when no lengths were left to check.
add("err-no-lengths", ["fixtures/seq.bin", "-min=90", "-max=80"], fix="recl endless loops",
    error="no record lengths")  # fmt: skip
add("err-missing-file", ["fixtures/no-such-file"], error="Can't open")
add("err-bad-option", ["fixtures/seq.bin", "-bogus"], fix="recl options", error="Unknown option")
add("err-only", ["fixtures/seq.bin", "-only=a,b"], fix="recl options", error="-only needs")

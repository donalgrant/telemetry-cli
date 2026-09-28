"""Generated pick golden cases.

The case format is described in tests/golden_cases.py. Most cases come in
pairs: a big-host case reading the big-endian fixture, which the patched Perl
answers correctly, and a little-host case reading the little-endian fixture.
Where the little-endian Perl is wrong, the little-host case is a "mirror" of
its big-host twin: the Python output of the two must be identical.

Paths are relative to tests/. PICKPATH points at tests/fixtures/sym.
"""

from __future__ import annotations

CASES: list[dict] = []
SYM_ENV = {"PICKPATH": "fixtures/sym"}

# The byte order of the little-endian Perl's output is wrong for these formats
# on multi-byte types, and for all bit fields (CHANGELOG: "pick byte order").
ORDER_FIX = "pick byte order"
ORDER_SENSITIVE_FORMATS = set("xobcSA")


def tag(text: str) -> str:
    """Case-safe text for an id: uppercase X becomes "+x" (S and s are different types)."""
    return "".join("+" + c.lower() if c.isupper() else c for c in text)


def add(id, args, **kw):
    CASES.append(
        {
            "id": tag(id),
            "args": list(args),
            **{k: tag(v) if k == "mirror" else v for k, v in kw.items()},
        }
    )


def paired(id, fixture, rest, *, sensitive=None, **kw):
    """Add a big-host case and its little-host twin.

    fixture is a name like "int32" (reading NAME.be.bin / NAME.le.bin), or a
    plain file name, used for both hosts. sensitive says whether the
    little-endian Perl gets this case wrong; the little-host case is then a
    mirror of the big-host one.
    """
    be = f"fixtures/{fixture}.be.bin" if "." not in fixture else f"fixtures/{fixture}"
    le = f"fixtures/{fixture}.le.bin" if "." not in fixture else f"fixtures/{fixture}"
    add(f"be-{id}", [be, *rest], host="big", **kw)
    if sensitive:
        add(f"le-{id}", [le, *rest], fix=ORDER_FIX, mirror=f"be-{id}", **kw)
    else:
        add(f"le-{id}", [le, *rest], **kw)


# --- data types ---------------------------------------------------------------

SIZE = {"S": 1, "A": 1, "b": 1, "c": 1, "s": 2, "w": 2, "u": 4, "i": 4, "f": 4, "d": 8}
SIZE |= {"z": 8, "Z": 16}
FIXTURE = {"S": "bytes.bin", "A": "bytes.bin", "b": "bytes.bin", "c": "bytes.bin"}
FIXTURE |= {"s": "int16", "w": "int16", "u": "int32", "i": "int32", "f": "float32"}
FIXTURE |= {"d": "float64", "z": "complex64", "Z": "complex128"}
FORMATS = "udxnsgGoMPRIDbSAcU"
COMPLEX_FIX = "pick complex g"


def order_sensitive(t, formats, bits=False):
    return SIZE[t] > 1 and (bits or bool(ORDER_SENSITIVE_FORMATS & set(formats)))


def complex_g(t, fmt):
    """The docs say 'g' on a complex type means RI; the Perl rejected it."""
    return t in "zZ" and "g" in fmt


def type_case(id, t, request, formats, extra=(), bits=False):
    """A whole-record request of type t, on its typed fixture with 16-byte records."""
    rest = ["16", "-q", *extra, request]
    kw = {}
    if complex_g(t, formats):
        kw = {"fix": COMPLEX_FIX, "perl_args": None}
    if kw:
        fixture = FIXTURE[t]
        be = f"fixtures/{fixture}.be.bin"
        le = f"fixtures/{fixture}.le.bin"
        fixed = [request.replace("g", "RI")]
        add(
            f"be-{id}",
            [be, *rest],
            host="big",
            fix=COMPLEX_FIX,
            perl_args=[be, "16", "-q", *extra, *fixed],
        )
        add(f"le-{id}", [le, *rest], fix=COMPLEX_FIX, mirror=f"be-{id}")
        return
    paired(id, FIXTURE[t], rest, sensitive=order_sensitive(t, formats, bits))


# Every type with every print format (and with its default format), for all
# the items in each record.
for t, size in SIZE.items():
    n = 16 // size
    type_case(f"type-{t}-default", t, f"{n}{t}", "")
    for fmt in FORMATS:
        type_case(f"type-{t}-{fmt}", t, f"{n}{t}{fmt}", fmt)
    # several formats on one field, and a format list with spacers
    type_case(f"type-{t}-multi", t, f"{n}{t}dux", "dux")
    type_case(f"type-{t}-spacers", t, f"{n}{t}sgsn", "sgsn")
    type_case(f"type-{t}-MP", t, f"{n}{t}MP", "MP")

# The same type-by-format matrix read with -r from the opposite-order file.
# On a big-endian host, -r reads little-endian data.
for t, size in SIZE.items():
    if size == 1:
        continue
    n = 16 // size
    for fmt in ["", "d", "u", "x", "b", "g", "D", "MP"]:
        name = f"r-{t}-{fmt or 'default'}"
        request = f"{n}{t}{fmt}"
        if t in "zZ":
            # -r reversed a complex number's 8 or 16 bytes as a whole, which
            # also swapped its real and imaginary parts. Now each part is
            # reversed on its own, so this reads the same as the big-endian file.
            if complex_g(t, fmt):
                continue
            add(
                f"be-{name}",
                [f"fixtures/{FIXTURE[t]}.le.bin", "16", "-q", "-r", request],
                host="big",
                fix="pick complex -r",
                mirror=f"be-type-{t}-{fmt or 'default'}",
            )
            continue
        add(f"be-{name}", [f"fixtures/{FIXTURE[t]}.le.bin", "16", "-q", "-r", request], host="big")
        if order_sensitive(t, fmt):
            add(
                f"le-{name}",
                [f"fixtures/{FIXTURE[t]}.be.bin", "16", "-q", "-r", request],
                fix=ORDER_FIX,
                mirror=f"be-type-{t}-{fmt or 'default'}",
            )
        else:
            add(f"le-{name}", [f"fixtures/{FIXTURE[t]}.be.bin", "16", "-q", "-r", request])

# --- counts and offsets ----------------------------------------------------------

for t, size in SIZE.items():
    if t in "SA":
        continue
    n = 16 // size
    requests = {
        "first": f"{t}0",
        "second": f"{t}1" if n > 1 else f"{t}0",
        "last": f"{t}{n - 1}",
        "beyond": f"{t}{n}",
        "count-all": f"{n}{t}",
        "count-too-many": f"{n + 1}{t}",
        "count-at": f"{n}{t}0",
        "plus-byte": f"{t}0+1" if size < 16 else f"{t}0+0",
        "last-byte": f"{t}0+{16 - size}",
        "past-last-byte": f"{t}0+{17 - size}",
        "minus-bytes": f"{t}1-{size}" if n > 1 else f"{t}0-0",
        "negative": f"{t}0-1",
        "sequential": " ".join([t] * n),
        "sequential-too-many": " ".join([t] * (n + 1)),
        "absolute-then-next": f"{t}{n - 1} {t}0 {t}" if n > 1 else f"{t}0 {t}0",
    }
    for name, req in requests.items():
        paired(f"offset-{t}-{name}", FIXTURE[t], ["16", "-q", *req.split()])

# --- bit fields -------------------------------------------------------------------

BIT_FORMATS = ["", "d", "x", "b", "bdx"]
for t in "bcswiu":
    size, bits = SIZE[t], 8 * SIZE[t]
    n = 16 // size
    offsets = sorted({0, 3, bits // 2, bits - 1}) if size > 1 else [0, 3, 7]
    for fb in offsets:
        for nb in dict.fromkeys([None, 1, 3, bits - fb, bits]):
            spec = f":{fb}" if nb is None else f":{fb}:{nb}"
            # more bits than the type has: one format is enough
            for fmt in BIT_FORMATS if nb != bits or fb == 0 else ["d"]:
                name = f"bits-{t}{spec.replace(':', '_')}-{fmt or 'default'}"
                request = f"{n}{t}{spec}{fmt}"
                # 1-byte types are the same in either byte order
                paired(name, FIXTURE[t], ["16", "-q", request], sensitive=size > 1)

# bit fields on 4-byte floats are allowed; larger types ignore the bit spec
for t, spec in [("f", ":1"), ("f", ":4:8"), ("d", ":3"), ("z", ":2:5")]:
    n = 16 // SIZE[t]
    for fmt in ["", "x", "b"]:
        name = f"bits-{t}{spec.replace(':', '_')}-{fmt or 'default'}"
        paired(name, FIXTURE[t], ["16", "-q", f"{n}{t}{spec}{fmt}"], sensitive=True)

# bit fields with -r: a big host reading little-endian data
for t in "swiu":
    n = 16 // SIZE[t]
    for spec in [":0:8", ":3:5", f":{8 * SIZE[t] - 4}"]:
        for fmt in ["d", "x", "b"]:
            name = f"bits-r-{t}{spec.replace(':', '_')}-{fmt}"
            add(
                f"be-{name}",
                [f"fixtures/{FIXTURE[t]}.le.bin", "16", "-q", "-r", f"{n}{t}{spec}{fmt}"],
                host="big",
            )

# --- moves and groups -------------------------------------------------------------

MOVES = {
    "forward-bytes": "+4 i",
    "back-bytes": "i -4 i",
    "forward-typed": "+1i i",
    "back-typed": "2i -1i i",
    "forward-short": "+1w w",
    "complex-units": "+1z i",
    "to-end": "+12 i",
    "past-end": "+13 i",
    "move-past-end-no-read": "3i +4",
    "move-only": "+4",
    "back-before-start": "-1i i",
    "space-idiom": "i -1 bs i",
    "space-idiom-at-start": "-1 bs i",
    "space-after": "i bs -1 i",
    "zero-move": "+0 i",
    "minus-zero": "-0 i",
    "many": "+1 +1 +1 +1 i -2 -2 w",
}
for name, req in MOVES.items():
    paired(f"move-{name}", "int32", ["16", "-q", *req.split()])

GROUPS = {
    "simple": ["[", "i", "]"],
    "simple-tight": ["[i]"],
    "one-token": ["[ i w ]"],
    "repeat": ["4[", "i", "]"],
    "repeat-too-many": ["5[", "i", "]"],
    "repeat-one": ["1[", "i", "]"],
    "repeat-zero": ["0[", "i", "]"],
    "with-moves": ["2[", "w", "+2", "]"],
    "back-and-forth": ["4[", "w", "+2", "-4", "i", "]"],
    "nested": ["2[", "2[", "b", "]", "+2", "]"],
    "nested-inner-repeat": ["2[", "b", "3[", "b", "+1", "]", "-3", "]"],
    "nested-three": ["2[", "2[", "2[", "b", "]", "]", "]", "i"],
    "two-groups": ["[", "i", "]", "2[", "w", "]"],
    "group-then-field": ["2[", "i", "]", "i"],
    "escaped": ["\\[", "2i", "\\]"],
    "escaped-repeat": ["2\\[", "i", "\\]"],
    "prefix-with-space": ["2", "[", "i", "]"],
    "formats-inside": ["2[", "ix", "id", "ib", "]"],
    "empty": ["[", "]", "i"],
}
for name, req in GROUPS.items():
    paired(f"group-{name}", "int32", ["16", "-q", *req], sensitive="formats" in name)

# The POD's field-request examples, on the big 4096-byte subcom records. Their
# items overlap the fixture's fields, so the little-endian file has no
# big-endian twin: the big-host Perl reading it with -r is the reference.
POD_EXAMPLES = {
    "4d-2z-5i": ["4d0+30", "2z", "5i"],
    "6-f-i": ["6[", "f", "i", "]"],
    "20-groups": ["20[", "f", "3[", "wx", "cb", "]", "+1000", "i:27d", "-1091", "]"],
    "format-list": ["f", "wb", "zMPn", "i0+57osss", "Z", "b5:1:7bdx"],
}
for name, req in POD_EXAMPLES.items():
    add(f"be-pod-{name}", ["fixtures/subcom.be.bin", "4096", "-q", *req], host="big")
    if not any(t in r for r in req for t in "zZ"):
        add(
            f"le-pod-{name}",
            ["fixtures/subcom.le.bin", "4096", "-q", *req],
            fix=ORDER_FIX,
            oracle="big-host-r",
        )

# --- options ----------------------------------------------------------------------

SEQ = "fixtures/seq.bin"  # 100 8-byte records: uint32 n, uint16 3n, "AB"
OPTIONS = {
    "l": ["-l"],
    "n": ["-n"],
    "m": ["-m"],
    "nlm": ["-nlm"],
    "separate": ["-n", "-l", "-m"],
    "repeated": ["-nn"],
    "s": ["-s"],
    "r": ["-r"],
    "lr": ["-lr"],
    "u": ["-u"],
    "b": ["-b"],
    "ub": ["-ub"],
    "not-quiet": [],
    "unknown": ["-z"],
    "unknown-mixed": ["-nzl"],
    "uppercase": ["-N"],
    "after-fields": ["__FIELDS__", "-l"],
}
for name, opts in OPTIONS.items():
    fields = ["u", "wd", "2S"]
    rest = ["8", *opts] if "__FIELDS__" not in opts else ["8", *fields, "-l"]
    if "__FIELDS__" in opts:
        fields = []
    q = [] if name == "not-quiet" else ["-q"]
    add(f"opt-{name}", [SEQ, *rest[:1], *q, *rest[1:], *fields, "nrecs=5"])

# the first word is never an option: "-q" is taken as the file name
add("opt-first-word", ["-q", SEQ, "8", "u"])
# a move written like an option
add("opt-move-like-option", [SEQ, "8", "-q", "u", "-z"])
add("opt-move-typed", [SEQ, "8", "-q", "u", "-1z"])

# --- parameters: record selection -------------------------------------------------

PARAMS = {
    "none": [],
    "start": ["start=95"],
    "stop": ["stop=3"],
    "start-stop": ["start=10", "stop=13"],
    "start-after-stop": ["start=13", "stop=10"],
    "rec": ["rec=42"],
    "rec-first": ["rec=0"],
    "rec-last": ["rec=99"],
    "rec-beyond": ["rec=100"],
    "nrecs": ["nrecs=3"],
    "start-nrecs": ["start=50", "nrecs=3"],
    "stop-nrecs": ["stop=50", "nrecs=3"],
    "stop-nrecs-before-zero": ["stop=1", "nrecs=5"],
    "skip": ["skip=9"],
    "skip-start": ["skip=30", "start=5"],
    "every": ["every=25"],
    "every-one": ["every=1", "nrecs=3"],
    "every-and-skip": ["every=25", "skip=1", "nrecs=4"],
    "skip-stop": ["skip=2", "stop=10"],
    "start-beyond": ["start=200"],
    "stop-beyond": ["start=97", "stop=200"],
    "head": ["head=4"],
    "head-typed": ["head=1i"],
    "header-synonym": ["header=8"],
    "head-start": ["head=8", "start=2", "nrecs=2"],
    "spaces": ["start", "=", "5", "nrecs", "=", "2"],
    "space-before": ["start", "=5", "nrecs=2"],
    "space-after": ["start=", "5", "nrecs=2"],
    "uppercase": ["START=5", "nrecs=2"],
    "mixed-case": ["Start=5", "nrecs=2"],
    "before-fields": ["__PARAMS_FIRST__"],
    "repeated": ["start=5", "start=7", "nrecs=2"],
    "unknown": ["foo=3"],
    "stray-equals": ["="],
}
for name, params in PARAMS.items():
    if params == ["__PARAMS_FIRST__"]:
        add(f"param-{name}", [SEQ, "start=5", "nrecs=2", "8", "-q", "u", "w"])
        continue
    add(f"param-{name}", [SEQ, "8", "-q", "u", "w", *params])

# record size: positional, typed, and as a parameter
SIZES = {
    "bytes": ["8"],
    "typed-b": ["8b"],
    "typed-i": ["2i"],
    "typed-d": ["1d"],
    "typed-z": ["1z"],
    "param-size": ["size=8"],
    "param-length": ["length=8"],
    "param-typed": ["size=2w"],
    "larger": ["16"],
    "smaller": ["6"],
    "missing": [],
    "zero": ["0"],
}
for name, size in SIZES.items():
    add(f"size-{name}", [SEQ, *size, "-q", "u", "w", "nrecs=3"])

# the file: positional, file=, filename=, missing
add("file-param", ["8", "-q", "u", f"file={SEQ}", "nrecs=2"])
add("file-param-filename", ["8", "-q", "u", f"filename={SEQ}", "nrecs=2"])
add("file-param-dash", ["8", "-q", "u", "file=-", "nrecs=2"], stdin=SEQ)
add("file-not-first", ["8", SEQ, "-q", "u"], error="Matched neither")
add("file-missing", ["fixtures/no-such-file", "8", "-q", "u"])
add(
    "file-param-missing",
    ["8", "-q", "u", "file=fixtures/no-such-file"],
    fix="pick missing file",
    error="fixtures/no-such-file",
)

# --- streams ----------------------------------------------------------------------

STREAMS = {
    "stdin": ["8", "-q", "u", "w", "nrecs=3"],
    "stdin-not-quiet": ["8", "u", "nrecs=3"],
    "stdin-start": ["8", "-q", "u", "start=10", "nrecs=3"],
    "stdin-skip": ["8", "-q", "u", "skip=9", "nrecs=5"],
    "stdin-every": ["8", "-q", "u", "every=33"],
    "stdin-head": ["8", "-q", "u", "head=4", "nrecs=3"],
    "stdin-rec": ["8", "-q", "u", "rec=50"],
    "stdin-stop": ["8", "-q", "u", "stop=4"],
    "stdin-binary": ["8", "-q", "-b", "u", "w", "nrecs=3"],
}
for name, args in STREAMS.items():
    add(name, args, stdin=SEQ)

HEADER = "fixtures/header.bin"  # 20-byte header, ten 12-byte records, 5 extra bytes
add("header-records", [HEADER, "12", "-q", "u", "f", "4S", "head=20"])
add("header-records-stdin", ["12", "-q", "u", "f", "4S", "head=20"], stdin=HEADER)
add("header-partial-last", [HEADER, "12", "-q", "u", "head=20", "start=9"])
add("header-too-long", [HEADER, "12", "-q", "u", "head=200"])
add("header-too-long-stdin", ["12", "-q", "u", "head=200"], stdin=HEADER)
add("header-as-record", [HEADER, "20", "-q", "20S", "rec=0"])
add("header-m", [HEADER, "12", "-q", "-m", "u", "head=20", "every=3"])
add("header-m-stdin", ["12", "-q", "-m", "u", "head=20", "every=3"], stdin=HEADER)
add("empty-file", ["fixtures/empty.bin", "8", "-q", "u"])
add("empty-stdin", ["8", "-q", "u"])
add("empty-stdin-head", ["8", "-q", "u", "head=4"])
add("counter-pod", ["fixtures/counter.bin", "7", "-q", "3bd", "ud"])

# --- ASCII -------------------------------------------------------------------------

ASCII = "fixtures/ascii.bin"  # four 32-byte lines
for fmt in ["", "c", "S", "A", "x", "d", "u", "o", "b", "U"]:
    for t in "cbSA":
        add(f"ascii-{t}-{fmt or 'default'}", [ASCII, "32", "-q", f"32{t}{fmt}"])
add("ascii-bytes-all-c", ["fixtures/bytes.bin", "256", "-q", "256c"])
add("ascii-bytes-all-S", ["fixtures/bytes.bin", "256", "-q", "256S"])
add("ascii-bytes-all-A", ["fixtures/bytes.bin", "256", "-q", "256A"])
add("ascii-pod-80c", [ASCII, "32", "-q", "32c", "-1", "bn"])
add("ascii-pod-80c-error", [ASCII, "32", "-q", "32c", "bn"])
add("ascii-every-other", [ASCII, "32", "-q", "16[", "cc", "+1", "]", "skip=1"])

# --- symbol files --------------------------------------------------------------------

SYMBOLS = {
    "moc": ["velocities", "pos", "orientD", "all", "af", "xrec time", "yawD pitchd"],
    "corr": ["record ready r0 los", "mag perp par", "rangeCell azCell azGroup"],
    "aux": [
        "pn f_size h_size flag",
        "gmt_sec gmt_min gmt_hrs gmt_day gmt_acc",
        "status f_control",
        "gmt_ms gmt_bin",
        "egi_time ins_time_tag index",
        "mux_dat",
    ],
    "subcom": [
        "target invstg hp_opr",
        "notes",
        "six_year six_month six_day six_hour",
        "six_min six_sec six_nsec six_f_cnt",
        "motionSensorFlag hdrVersion eosd",
    ],
    "hw": ["pos orient v", "frame time tprf"],
    "airmoc": ["time lat lon", "atens"],
}
for sym, requests in SYMBOLS.items():
    for k, req in enumerate(requests):
        # Symbol tables name bit fields and hex output, and some items overlap
        # others (aux's gmt_bin spans two shorts), so the little-endian file
        # has no big-endian twin: the big-host Perl with -r is the reference.
        args = [f"sym={sym}", "-q", *req.split()]
        add(f"be-sym-{sym}-{k}", [f"fixtures/{sym}.be.bin", *args], host="big", env=SYM_ENV)
        add(
            f"le-sym-{sym}-{k}",
            [f"fixtures/{sym}.le.bin", *args],
            env=SYM_ENV,
            fix=ORDER_FIX,
            oracle="big-host-r",
        )

paired("sym-moc-every", "moc", ["sym=moc", "-q", "velocities", "every=2"], env=SYM_ENV)
paired("sym-moc-n", "moc", ["sym=moc", "-q", "-n", "tube"], env=SYM_ENV)
paired("sym-moc-first", "moc", ["-q", "pos", "sym=moc"], env=SYM_ENV)
paired("sym-symFile", "moc", ["symFile=moc", "-q", "pos"], env=SYM_ENV)
paired("sym-symTable", "moc", ["symTable=moc", "-q", "pos"], env=SYM_ENV)
paired("sym-path", "moc", ["sym=fixtures/sym/moc", "-q", "pos"])
paired("sym-case-exact", "moc", ["sym=moc", "-q", "xRec", "xrec"], env=SYM_ENV)
paired("sym-case-other", "moc", ["sym=moc", "-q", "XREC", "posS"], env=SYM_ENV)
paired("sym-size-override", "moc", ["sym=moc", "-q", "size=84", "pos"], env=SYM_ENV)
paired("sym-mixed-fields", "moc", ["sym=moc", "-q", "pos", "d0", "+8", "d"], env=SYM_ENV)
add("sym-missing", [SEQ, "sym=no-such-table", "-q", "u"], env=SYM_ENV)
add("sym-list", ["sym=moc", "?"], env=SYM_ENV, fix="pick help text")
paired("sym-edge", "moc", ["sym=edge", "-q", "a", "ab", "A", "both", "twice"], env=SYM_ENV)
paired("sym-edge-head", "moc", ["sym=edge", "-q", "i", "every=2"], env=SYM_ENV)

# --- help and errors ---------------------------------------------------------------

for topic in ["", "?", "??", "?p", "?r", "?f", "?t", "?m", "?o", "?g", "?x", "?q", "?v", "help"]:
    add(f"help-{topic.replace('?', 'Q') or 'none'}", [topic] if topic else [], fix="pick help text")
add("help-after-args", [SEQ, "8", "?t"], fix="pick help text")

ERRORS = {
    "beyond-record": [SEQ, "8", "-q", "3u"],
    "bad-format-byte": [SEQ, "8", "-q", "bg"],
    "bad-format-int": [SEQ, "8", "-q", "uM"],
    "bad-format-complex": ["fixtures/complex64.le.bin", "16", "-q", "zx"],
    "bad-format-complex-G": ["fixtures/complex64.le.bin", "16", "-q", "zG"],
    "bad-format-float": ["fixtures/float32.le.bin", "16", "-q", "fR"],
    "unknown-type": [SEQ, "8", "-q", "q"],
    "garbage-field": [SEQ, "8", "-q", "u", "hello"],
    "bad-bits": [SEQ, "8", "-q", "u:x"],
}
for name, args in ERRORS.items():
    error = "Matched neither" if name in ("unknown-type", "garbage-field", "bad-bits") else None
    add(f"err-{name}", args, **({"error": error} if error else {}))

# Command lines that made the Perl loop forever are errors now.
HANGS = "pick endless loops"
add("err-every-zero", [SEQ, "8", "-q", "u", "every=0"], fix=HANGS, error="every must be")
add("err-size-zero", [SEQ, "0", "-q"], fix=HANGS, error="record size")
add("err-size-zero-param", [SEQ, "size=0", "-q"], error="Can't find record size")

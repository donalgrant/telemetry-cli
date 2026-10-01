# telemetry-cli

Command-line tools for binary telemetry, built for Unix pipelines:

- **pick** decodes fields from fixed-length binary records: integers, floats,
  complex numbers, characters and bit fields, in any byte order
  ([manual](https://github.com/donalgrant/telemetry-cli/blob/main/docs/pick.md)).
- **recs** extracts records from a byte stream by their start (and end)
  markers ([manual](https://github.com/donalgrant/telemetry-cli/blob/main/docs/recs.md)).
- **recl** estimates the record length of a binary file
  ([manual](https://github.com/donalgrant/telemetry-cli/blob/main/docs/recl.md)).
- **tgen** generates synthetic telemetry from a command file describing each
  record ([manual](https://github.com/donalgrant/telemetry-cli/blob/main/docs/tgen.md)).
- **realign** puts frames that start at any bit (in a raw bit stream) on byte
  boundaries, so pick can read them
  ([manual](https://github.com/donalgrant/telemetry-cli/blob/main/docs/realign.md)).

```console
$ printf '\x00\x00\x00\x01\xff\xfeHi\x00\x00\x00\x02\x00\x07ok' > demo.bin
$ pick demo.bin 8 -q order=big u s 2S
1 -2 Hi
2 7 ok
$ pick demo.bin 8 -q order=big -n u0x w2b
0 00 00 00 01  1111 1111 1111 1110
1 00 00 00 02  0000 0000 0000 0111
```

Together: tgen makes a stream, recs pulls the frames out of it, recl finds
their length, and pick decodes them. See
[Using the tools together](https://github.com/donalgrant/telemetry-cli/blob/main/docs/pipelines.md).

## Install

Requires Python 3.10 or later. The package is `telemetry-cli` on PyPI, and is
best installed as an isolated command-line tool:

```text
pipx install telemetry-cli
# or
uv tool install telemetry-cli
```

Either installs the commands `pick`, `recs`, `recl`, `tgen` and `realign`. You can also
`pip install telemetry-cli` in a virtual environment.

## History

These are Python ports of tools written at JPL. pick and recl began together
as C++ tools, for a project whose telemetry arrived with no documentation of
its structure: recl to find the length of the records, and pick to take them
apart and work out what was in them. (A bit reminiscent of the film
*Contact*.) Both were later rewritten in Perl (pick by 2000), and tgen (2003)
and recs joined them.

The command lines are the same, and so is the output, apart from fixes listed
in the [CHANGELOG](https://github.com/donalgrant/telemetry-cli/blob/main/CHANGELOG.md):
chiefly pick's byte-order handling on little-endian machines, and recl's
measurement. tgen's command files are now Python; `tgen --convert` translates
the old Perl ones. The Perl originals, with their history, are in
[legacy/](https://github.com/donalgrant/telemetry-cli/tree/main/legacy).

## Development

```text
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

The tests compare each tool with its Perl original. `tests/golden/` holds the
Perl's output for large tables of command lines (about 2,200 for pick, 700
for recs), and the tests check that the Python version reproduces it byte for
byte. Where it deliberately differs, the case names the CHANGELOG entry that
explains why. With perl installed, further tests run random command lines
through both versions and compare them (`HYPOTHESIS_PROFILE=deep pytest` for
a longer search), and `python tools/make_golden.py --check` confirms the saved
output is current. The examples in the documentation run as tests too.

[How telemetry-cli is built](https://github.com/donalgrant/telemetry-cli/blob/main/docs/DESIGN.md)
describes the design for developers: how each tool works, the rules the port
follows, the tests, and every change from the Perl, with the reasons.

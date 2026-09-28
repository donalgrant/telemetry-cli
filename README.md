# telemetry-cli

Command-line tools for binary telemetry, from the command line and in Unix
pipelines:

- **pick** extracts fields from fixed-length binary records and prints them
  ([manual](docs/pick.md)).
- **recs** extracts records from a byte stream by their start and end markers
  ([manual](docs/recs.md)).
- **recl** estimates the record length of a binary file (not yet ported).
- **tgen** generates synthetic telemetry from a command file
  ([manual](docs/tgen.md)).

They are Python ports of Perl tools written at JPL. The command lines are
unchanged, and so is the output, apart from the fixes listed in the
[CHANGELOG](CHANGELOG.md). The Perl originals are in [legacy/](legacy/).

```console
$ printf '\x00\x00\x00\x01\xff\xfeHi\x00\x00\x00\x02\x00\x07ok' > demo.bin
$ pick demo.bin 8 -q order=big u s 2S
1 -2 Hi
2 7 ok
$ pick demo.bin 8 -q order=big -n u0x w2b
0 00 00 00 01  1111 1111 1111 1110
1 00 00 00 02  0000 0000 0000 0111
```

## Install

Requires Python 3.10 or later. Not yet on PyPI; to install from GitHub:

```text
pipx install git+https://github.com/donalgrant/telemetry-cli.git
```

For development, from a checkout:

```text
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

## Tests

The tests compare each tool with its Perl original. `tests/golden/` holds the
Perl's output for a large table of command lines (about 2,200 for pick), and
the tests check that the Python version reproduces it byte for byte. Where
the Python version deliberately differs, the case says which CHANGELOG entry
explains why.

With perl installed, further tests run random command lines through both
versions and compare them (`HYPOTHESIS_PROFILE=deep pytest` for a longer
search). `python tools/make_golden.py --check` confirms the saved output is
current. See [tests/golden_cases.py](tests/golden_cases.py) for how the cases
work.

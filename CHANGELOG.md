# Changelog

## Unreleased

### Documentation

- A new tutorial, [a spacecraft housekeeping stream](docs/tutorial-housekeeping.md),
  walks line by line through a tgen command file with a thermostat, correlated
  channels, a spinning quaternion and a subcommutated channel, then decodes it
  with pick and turns it into a CSV to plot. Its examples run in the test suite.
- pick's help (`pick ?q`) and manual pipe the symbol-table example to
  feedgnuplot, a command-line front end to gnuplot, instead of xmgr, and say
  that xmgr lives on as Grace (`xmgrace -nxy`).
- The tgen manual views the caltone sweep with `magick` (ImageMagick 7), which
  replaced `convert`.
- pick's manual and help (`pick ?f`) say that a field request can take any
  number of print formats, repeats included (`s2xdx`), and that with a count
  each item is printed in all of them before the next.

## 1.1.0 (2026-09-28)

Bit-level telemetry: recl finds frame lengths in bits and where frames start,
a new command, realign, puts frames that start at any bit on byte boundaries
for pick, and tgen can write bit strings.

### recl

- **`-bits`** finds record lengths in bits, for frames that aren't a whole
  number of bytes, such as PCM frames of 10- or 12-bit words in a raw bit
  stream. It compares 8-bit windows at every bit position, and by default
  checks the lengths suggested by repeating bit patterns (sync words); with
  `-min`/`-max` or `-only` it checks the lengths given, in bits. The result
  is shown in bits and bytes: `RESULT 250 bits (31 bytes + 2 bits)`.
- **`-lsb`** reads bits least significant first (with `-bits`).
- **`-sync`** finds the bits that are the same in every record (usually a
  sync word, with any fixed bits beside it) and reports where they are
  (`SYNC offset length bits`), with suggested `pick head=` and `recs`
  arguments. The record length then comes from the repeats of the pattern
  when there are any, which works for records of one continuously sampled
  signal, where comparing bytes doesn't. If the pattern repeats at varying
  intervals, recl says the records may vary in length. Records are lined up
  on the pattern's repeats, so bit slips don't hide it; recl reports them.

### realign (new)

- **realign** cuts a bit stream into frames of any number of bits, starting
  at any bit, and writes each on byte boundaries, padded to whole bytes, so
  pick can decode them. With `-sync`, it finds frames by their sync pattern
  (optionally with bit errors) instead, which survives bit slips.
  `recl -bits -sync` reports the frame length and offset, and suggests the
  realign command. Without a file name, realign reads stdin.

### tgen

- **The `B` and `b` pack types** pack a string of `0`s and `1`s as bits, most
  or least significant first in each byte, as Perl's `pack` does. The Perl
  tgen had them through Perl; the Python version's first release didn't.
- **`bitstring(values, width)`** turns words of any width into such a
  string, for telemetry words of 10 or 12 bits: `bitstring([3, 5], 4)` is
  `'00110101'`.

## 1.0.0 (2026-09-28)

The first release.

`telemetry-cli` brings four Perl tools into one Python package: `pick`, `recs`,
`recl` and `tgen`. The originals, with their git history, are in `legacy/`.

The command-line interfaces are unchanged. Output is identical to the
originals' except for the fixes listed here. Each fix is named by the golden
test cases that check it (`fix = "..."` in `tests/golden/*/cases.*`).

### pick

pick is ported. It passes about 2,200 golden cases that compare its output
byte for byte with the Perl original's.

**Fixes**

- **Byte order** (`pick byte order`). pick was written on big-endian machines.
  On little-endian machines, which is nearly all of them today, the Perl
  version:
  - got bit fields wrong (`u:0:8d` printed the wrong byte);
  - printed `x`, `o` and `b` output, and `c`/`S`/`A` output of multi-byte
    types, in memory order rather than value order (`0x03915ed3` as `ux`
    printed `d3 5e 91 03`).

  pick now behaves the same on every machine: it prints each value as the
  Perl did on a big-endian machine. `-r` and the new `order=` parameter say
  how the data are stored.
- **`-r` on complex numbers** (`pick complex -r`) reversed all 8 (or 16) bytes
  at once, which also swapped the real and imaginary parts. Now each part is
  reversed on its own.
- **`g` on complex types** (`pick complex g`) is documented as meaning `RI`,
  but the Perl rejected it. It now prints the real and imaginary parts.
- **`-l` and `-n`** did the reverse of what the documentation says: `-l`
  printed the record number and `-n` the line count. They now match the
  documentation: `-l` prints the line number and `-n` the record number.
- **Errors go to stderr, with a nonzero exit status.** The Perl printed "Matched
  neither a move nor a data request" to stdout and exited 0. It also dumped
  the help text to stdout before other errors, and ignored a `file=` that
  couldn't be opened (`pick missing file`).
- **Endless loops are errors** (`pick endless loops`): `every=0`, a record
  size of 0, a symbol defined in terms of itself, and some malformed groups
  made the Perl run forever.
- **Help text** (`pick help text`):
  - The format list said `'x' octal`; it is `'o'`.
  - The example using awk lost its `$1` and `$2` (Perl expanded them as
    variables) and its line continuations.
  - The version text is updated, and the pointer to `perldoc` is replaced
    by a link to the manual.
  - Several examples miscounted items, which count from 0: `z60-2` is the
    61st complex number, not the 60th; `w5` and `b5` are the sixth short and
    char, not the fifth; `Z20` is the 21st double complex; `f500` is the
    501st float.
  - The group example `20[ f +96f i -100f ]` was off by three floats: it
    doesn't pair each float with the int 400 bytes on. That's
    `20[ f +99f i -100f ]`.
- **`U` output of bit fields** writes the masked value's bytes. The Perl wrote
  the wrong end of them.

**New**

- `order=big|little|native` gives the data's byte order. The default,
  `native`, is the machine's order, as before.
- `pick --help [topic]` works like `pick ?topic`, which is handy in zsh, where
  an unquoted `?p` is a filename pattern.
- The symbol tables from the original distribution (`moc`, `aux`, `corr`,
  `subcom`, `hw`, `airmoc`, ...) are bundled. `sym=moc` finds them when the
  file isn't in the current directory or in `$PICKPATH`.

### recs

recs is ported. It passes about 700 golden cases (every way of finding
records, crossed with its options, on text, binary and 40 kB inputs) and the
Perl script's own `-test` suite, ported to pytest.

**Fixes**

- **Padding** (`recs null fill`) uses null bytes by default, as documented.
  The Perl padded records with the character `0`.
- **Warnings go to stderr.** The Perl wrote them to stdout, in the middle of
  the extracted records, with its own source line numbers.
- **Command-line errors** (`recs options`, `recs arguments`) stop recs with a
  message and a nonzero status. The Perl warned about a bad option and
  carried on without it, and with a missing marker or a non-numeric length it
  quietly wrote nothing.
- **Endless loops are errors** (`recs endless loops`): padding with an empty
  fill string, and markers that match without consuming anything (such as a
  record length of 0 without `-x`), made the Perl run forever.
- `-test` ran the Perl script's built-in tests; it now says they have moved
  into the test suite.

Regexes (`-r`) are now Python's rather than Perl's. They agree on the kinds of
patterns recs is used with.

### tgen

tgen is ported. Its command files are now Python, and `tgen --convert`
translates Perl command files. The eight example command files from the
original, and further test files covering the rest of the language, give the
same output byte for byte as the Perl tgen did with the originals. That
includes random output: both versions use Perl's random number generator
(drand48), so a seeded run matches the Perl run with the same `srand` seed.
Random tests generate thousands of Perl command files, convert them, and
compare the two versions' output.

**Changes**

- **Command files are Python.** The layout is the same (five `#`-separated
  fields, comments, continuation lines); the code in the fields is Python.
  `$::I` is `I`, `$P{name}{value}` is `P.name.value`, and helpers give Perl's
  `%`, bit operators and `.` where the behavior differs from Python's.
- **`tgen --convert`** translates Perl command files, and marks lines it can't
  translate with `# TODO(convert)`.
- **Errors in a field stop tgen** with the file, line and field. The Perl
  silently used the field's source text as its value, which usually packed as
  0.
- **`-seed=n`** (new) makes random output repeatable.
- The file helpers open each file once, rather than once per frame.
- A bad option is an error; the Perl warned and carried on.

### recl

recl is ported, and its measurement is fixed, so its results differ from the
Perl version's (which were usually wrong). The command line and output lines
are the same; about 100 golden cases compare everything but the scores with
the Perl. Whether recl finds the right length is tested on files of known
record length made with tgen, including random lengths up to 700 bytes,
headers, partial last records and `-fact`.

**Fixes**

- **The measurement** counted agreeing bits in only the first eighth of each
  buffer. On a file of 48-byte records, the Perl answered 3. recl now counts
  the bytes equal to the byte one record length on, over the whole buffer,
  and reports the smallest of a length and its multiples when they score
  alike (they always nearly do). Counting bytes rather than bits needs much
  less data, and isn't pulled toward multiples of the length by counters. So
  `CORR` is now a percentage of equal bytes (about 0.4 for random data),
  not of agreeing bits (about 50).
- **`-full`, `-limit` and `-reduce`** (`recl options`) were accepted but
  ignored. They now work.
- **`-only`** sized buffers from the last length listed rather than the
  longest, so longer lengths were never scored.
- **The `-verbose` table** showed fractions labeled as percentages.
- **stdin** (`recl stdin`) required `-max`, which was then taken as the file
  size. stdin now works like a file.
- **Short data** (`recl short data`): data shorter than one buffer made the
  Perl divide by zero; it is now compared as one piece.
- **No lengths to check** (`recl endless loops`), e.g. `-min=90 -max=80`,
  made the Perl loop forever; it is now an error. So are a bad option and an
  unreadable `-only` list.

It is also much faster.

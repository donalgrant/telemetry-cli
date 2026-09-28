# Changelog

## Unreleased

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

### recl (not yet ported)

- The autocorrelation counted only the first eighth of the bits in each
  buffer, so it usually guessed wrong. `-full`, `-limit` and `-reduce` were
  accepted but ignored.

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

### recl (not yet ported)

- The autocorrelation counted only the first eighth of the bits in each
  buffer, so it usually guessed wrong. `-full`, `-limit` and `-reduce` were
  accepted but ignored.

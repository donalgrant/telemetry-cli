# pick

Extract fields from fixed-length binary records and print them.

```text
pick file.dat reclen [ fieldRequests | options | parameters ]
cat file.dat | pick reclen [ fieldRequests | options | parameters ]
```

pick reads a file (or stdin) as a series of fixed-length records, optionally
after a header, and prints the fields you ask for from each record: one line
of output per record. It is meant for pipelines: pick out a few values and
send them on to awk, a plotting program, or another pick.

Field requests are short codes. `4d0+30` means four doubles starting at byte
30; `w5:1:7bdx` means bits 1 to 7 of the sixth unsigned short, printed in
binary, decimal and hex. A symbol table can give names to the fields of a file
format, so you can write `pick sym=moc run.moc velocities` instead.

For built-in help, run `pick ?` (in zsh, quote it: `pick '?'`, or use
`pick --help`). Topics are `?p` parameters, `?r` field requests, `?f` print
formats, `?t` data types, `?m` moves, `?o` options, `?g` groups, `?x`
examples, `?q` symbol tables, `?v` version, and `??` everything.

## A first example

The examples on this page use a small file of three 8-byte records. Each holds
a big-endian unsigned int, a signed short and two characters:

```console
$ printf '\x00\x00\x00\x01\xff\xfeHi\x00\x00\x00\x02\x00\x07ok\x00\x00\x00\x03\x80\x00!?' > demo.bin
$ pick demo.bin 8 -q order=big u s 2S
1 -2 Hi
2 7 ok
3 -32768 !?
```

The file comes first, then the record length in bytes, then the fields. `u`
is an unsigned int, `s` a signed short, and `2S` two characters. `-q` turns off
diagnostic messages and `order=big` says the data are big-endian (see
[Byte order](#byte-order)).

Each field starts where the previous one ended, unless it gives a position.
Parameters and options can go anywhere after the file name:

```console
$ pick demo.bin 8 order=big rec=1 -q u w 2S
2 7 ok
$ pick demo.bin 8 -q order=big every=2 -l u
0 1
1 3
```

Reading from stdin works the same way, without the file name:

```console
$ cat demo.bin | pick 8 -q order=big +4 wd -1 bs 2A
65534  Hi
7  ok
32768  !?
```

Here `+4` skips the int, `wd` prints the short as an unsigned decimal, and
`-1 bs` backs up one byte and reads it just to print a space.

## Options

Options are single letters, combined (`-nlr`) or separate (`-n -l -r`). The
first word on the command line is never taken as an option.

| Option | Meaning |
|---|---|
| `-l` | print the line number (0, 1, 2, ...) at the start of every line |
| `-n` | print the record number at the start of every line |
| `-m` | print the record's byte position in the file |
| `-r` | reverse the byte order of the data |
| `-u` | print every field in binary (the `U` format) |
| `-b` | print the requested bytes as they are: fast, no bit fields or byte reversal |
| `-q` | quiet: no diagnostic messages on stderr |
| `-s` | don't end each record's output with a newline |

## Parameters

Parameters have the form `key=value`, with or without spaces around the `=`.
Record numbers count from zero.

| Parameter | Meaning |
|---|---|
| `file=name` | the file to read (`filename` is a synonym); an alternative to giving it first |
| `size=n` | the record length (`length` is a synonym); an alternative to giving it second |
| `start=n` | the first record to extract (default 0) |
| `stop=n` | the last record to extract (default: the end of the file) |
| `rec=n` | extract just this record |
| `nrecs=n` | how many records to extract, from `start` (or back from `stop`) |
| `skip=n` | skip this many records after each one extracted |
| `every=n` | extract every nth record (the same as `skip=n-1`) |
| `head=n` | skip an n-byte header before counting records (`header` is a synonym) |
| `sym=table` | use a symbol table (`symFile` and `symTable` are synonyms) |
| `order=o` | the data's byte order: `big`, `little`, or `native` (the default) |

`size`, `head` and the record length can be given in units of a data type:
`head=4z` skips a header of four single-precision complex numbers (32 bytes),
and a record length of `21d` is 168 bytes.

## Field requests

There are two kinds of field requests: prints and moves. A print request reads
items from the record and prints them; a move changes the current position in
the record without printing anything.

### Print requests

```text
N type Offset :bitOffset:nBits printFormats
```

written without spaces, for example `4d0+30`, `i:7`, `w5:1:7bdx` or `zMP`.

- **N** is the number of items to read, 1 if omitted.
- **type** is the data type, below.
- **Offset** is `dataOffset` or `dataOffset+byteOffset` (or `-byteOffset`).
  `dataOffset` counts items of this type from the start of the record, and
  `byteOffset` adds bytes to that. Like all counting in pick, both count from
  0: `u0` is the first unsigned int, and `u1` the second, starting at byte 4.
  `z60-2` is the 61st single-precision complex number, moved two bytes toward
  the start of the record; `z0+478` is the complex number that starts at byte
  478. Without an offset, the request reads the items after the previous
  request.
- **bitOffset** and **nBits** select bits, for types of 4 bytes or less. Bit 0
  is the least significant. `i:7` uses bits 7 to 31 of an int, and `w5:1:7`
  bits 1 to 7 of the sixth unsigned short (`w0` being the first).
- **printFormats** are zero or more print formats, below. There is no limit
  on how many, and a format may be repeated. Each is printed in turn: `bdx`
  prints the value in binary, then decimal, then hex; `s2dxob` prints the
  third short as a decimal, in hex, in octal and in binary; `s2xdx` prints it
  in hex, as a decimal and in hex again. With a count N, each item is
  printed in all the formats before the next item: `2b6dx` prints the
  byte at 6 as a decimal and in hex, then the byte at 7 the same way.

```console
$ pick demo.bin 8 -q order=big w2:4:4d w2:0:4d w2b
15 14 1111 1111 1111 1110
0 7 0000 0000 0000 0111
0 0 1000 0000 0000 0000
$ pick demo.bin 8 -q order=big nrecs=1 s2dxob
-2 ff fe  377 376  1111 1111 1111 1110
$ pick demo.bin 8 -q order=big nrecs=1 s2xdx
ff fe  -2 ff fe
$ pick demo.bin 8 -q order=big 2b6dx
72  48  105  69
111  6f  107  6b
33  21  63  3f
```

### Moves

```text
(+|-)N type
```

A move goes forward or back by N items of the type, or N bytes without a type.
`+2 -237 +5z -3i` moves forward 2 bytes, back 237 bytes, forward 40 bytes and
back 12 bytes. A position can go past either end of the record as long as
nothing is read there.

### Groups

Brackets group requests, and a number in front repeats the group. Quote the
brackets, or escape them, to keep the shell from interpreting them.

```console
$ pick demo.bin 8 -q order=big '2[ w ]' +2 2S
0 1 Hi
0 2 ok
0 3 !?
```

Groups can be nested. There must be no space between the repeat count and
the bracket.

A group's moves are relative to where its last request left off, which makes
the arithmetic easy to get wrong. Take records of 100 floats followed by 100
ints (here made with [tgen](tgen.md)), and read each float with the int 400
bytes after it:

<!-- file: pairs.tgen -->
```text
floats # 0   # 1 # 'f>100' # [float(k) for k in range(100)]
ints   # 400 # 1 # 'l>100' # [1000 + k for k in range(100)]
```

```console
$ tgen -q pairs.tgen | pick 800 -q order=big '3[ f +99f i -100f ]'
0 1000 1 1001 2 1002
```

After `f`, the position is 4 bytes in; `+99f` moves on 396 bytes to byte 400,
where `i` reads the int; `-100f` moves back 400 bytes, to byte 4, where the
next float starts. (The original documentation gave this example as
`20[ f +96f i -100f ]`, which is off by three floats.)

## Data types

| Type | Bytes | Meaning | Default format |
|---|---|---|---|
| `c` | 1 | signed char | `c` |
| `b` | 1 | unsigned char | `x` |
| `S` | 1 | character (as `c`) | `S` |
| `A` | 1 | character (as `c`) | `A` |
| `s` | 2 | signed short | `d` |
| `w` | 2 | unsigned short | `u` |
| `i` | 4 | signed int | `d` |
| `u` | 4 | unsigned int | `u` |
| `f` | 4 | single-precision float | `g` |
| `d` | 8 | double-precision float | `g` |
| `z` | 8 | single-precision complex | `RI` |
| `Z` | 16 | double-precision complex | `RI` |

The type decides whether an integer is signed, and the format only decides
how it's shown; see [Quirks](#quirks). Only `s` and `i` are read as signed:
`c` is read as unsigned, like `b`, despite its name.

## Print formats

| Format | Meaning | For |
|---|---|---|
| `x` | hexadecimal, a byte at a time | all but complex |
| `o` | octal, a byte at a time | all but complex |
| `b` | binary, in groups of four bits | all but complex |
| `c` | characters; non-printing ones by name (`nul`, `esc`) or in octal | all but complex |
| `S` | characters, with no space between items; non-printing ones in parentheses | all but complex |
| `A` | characters, leaving out non-printing ones | all but complex |
| `U` | the value's bytes, unformatted, in this machine's byte order | all types |
| `d` | decimal | integers (and floats, truncated) |
| `u` | unsigned decimal | integers (and floats, truncated) |
| `g` | floating point (for complex types, the same as `RI`) | floats (and integers) |
| `G` | floating point with 18 significant digits, 25 characters wide | floats (and integers) |
| `D` | degrees: the value is in radians (for complex types, the phase) | floats (and integers) |
| `R` `I` | real and imaginary part | complex |
| `M` `P` | magnitude, and phase in radians | complex |
| `n` | a newline | all types |
| `s` | a space | all types |

Most formats are followed by a space, and `x`, `o`, `d` and `u` on byte types
print a space after each byte, so output lines end with spaces.

## Quirks

pick has kept some surprising behavior from the original, so that old
scripts keep working. These examples read a 12-byte record: the byte `ff`,
the letter `A`, the short -2, the int -2 and the float -1.5.

```console
$ printf '\xffA\xff\xfe\xff\xff\xff\xfe\xbf\xc0\x00\x00' > quirks.bin
```

**The type decides the sign, not the format.** Only `s` and `i` are read as
signed; `c`, `b`, `w` and `u` are read as unsigned. `d` prints the value as
it was read, so it doesn't make an unsigned type signed, and `c` ("signed
char") prints 255, not -1. `u` on a negative value prints it as a 64-bit
unsigned number. No format shows an unsigned type as signed.

```console
$ pick quirks.bin 12 -q order=big c0d b0d w1d u1d
255  255  65534 4294967294
$ pick quirks.bin 12 -q order=big s1d s1u i1u
-2 18446744073709551614 18446744073709551614
```

**Bit fields are unsigned**, even on signed types: bits 4 to 15 of the short
-2 are 4095, and bits 1 to 31 of the int -2 are 2147483647.

```console
$ pick quirks.bin 12 -q order=big s1:4 i1:1
4095 2147483647
```

On the 4-byte float `f`, a bit field shifts and masks the float's bits, then
reads the result as a float again, which rarely means anything. On the larger
types (`d`, `z`, `Z`), a bit field is silently ignored: `d0:4` prints the same
as `d0`.

**Formats work outside their types.**
- `d` and `u` on a float truncate it toward zero, so `u` on -1.5 prints -1
  as a 64-bit unsigned number.
- `g`, `G` and `D` work on integers, and `D` takes the integer to be radians.
- `x`, `o` and `b` always show the stored bytes, one at a time. `s1o` is
  `377 376`, not the octal number `177776`, and `x` on a float shows its
  IEEE bytes.

```console
$ pick quirks.bin 12 -q order=big f2d f2u f2x
-1 18446744073709551615 bf c0 00 00
$ pick quirks.bin 12 -q order=big i1g i1D s1o s1x
-2 -114.592 377 376  ff fe
```

Complex types are the exception. They take only `g`, `R`, `I`, `M`, `P`, `D`
and `U`, and any other format, even `G`, is an error.

**Characters.**
- `c` shows a non-printing byte by name (`nul`, `ht`, `nl`, `del`) or in
  octal (`377`), with no brackets, so it can look like ordinary text.
- On a multi-byte type, `c` runs the bytes together: the float -1.5 is
  `277300nulnul`.
- `S` puts brackets around non-printing bytes, so they can't be mistaken
  for text.
- `A` leaves them out, so its output can be shorter than the data.

```console
$ pick quirks.bin 12 -q order=big b0c f2c f2S 2A0
377 277300nulnul (277)(300)(nul)(nul)A
```

`2A0` reads two bytes, `ff` and `A`, but prints only the `A`. It runs into
the `S` output because, as with `S`, there's no space after `A`.

**`G` pads to 25 characters** (it's the C format `%25.18g`), which lines
numbers up in columns but can be surprising on its own:

```console
$ pick quirks.bin 12 -q order=big f2G
                     -1.5
```

**A request with only `n` or `s` prints no value.** The default format is
used only when a request has no formats at all. So `b0s` prints just a space,
which is how the idiom `-1 bs` prints a space without moving:

```console
$ pick quirks.bin 12 -q order=big b0s b0d
 255
```

These all behave as they did in the Perl version. What pick changed is
listed under [Differences from the Perl version](#differences-from-the-perl-version).

## Byte order

pick prints each value in its natural order: a hex dump of the unsigned int
0x03915ed3 is `03 91 5e d3`, whatever machine pick runs on. You tell pick how
the data are stored:

- By default the data are taken to be in this machine's byte order
  (little-endian on nearly all current machines).
- `order=big` or `order=little` gives the order explicitly.
- `-r` reverses whichever order is in effect. For complex numbers, the real
  and imaginary parts are reversed separately.

```console
$ pick demo.bin 8 -q order=little u
16777216
33554432
50331648
$ pick demo.bin 8 -q order=little -r u
1
2
3
```

The `U` format writes values in this machine's byte order, so `pick file 4
-q -r -u u` swaps the byte order of a file of ints. The `-b` option writes the
requested bytes unchanged.

## Symbol tables

A symbol table gives names to pick requests. Here is the table for the `moc`
motion-compensation files:

```text
; This is the symbol table for .moc files, which
; are the radar motion compensation files for section 334.

length=21d  ; length is 21 double-precision (8 byte) numbers

xRec = d0G
time = d1G
posS = d3
posC = d4
posH = d5
pos = posS posC posH
velS = d6
velC = d7
velH = d8
vel = velS velC velH
orientD = 3d18D
velocities = posS vel
```

Each line is `name = requests`, and a semicolon starts a comment. Names can be
used in other definitions (`pos` above). Names match whole words; case doesn't
matter for matching, but a name typed in a different case than it was
defined expands to nothing. `length` (or `size`) and `head` set those
parameters rather than defining names.

```text
pick sym=moc run.moc velocities every=100
```

pick looks for the table in the current directory, then in the directory named
by the `PICKPATH` environment variable, and then among the tables that come
with pick: `moc`, `airmoc`, `aux`, `corr`, `corrOld`, `hw`, `subcom` and
`subcom_2002`, formats from JPL radar projects (AIRSAR, the ATI processor
and others). `pick sym=moc ?` lists a table's symbols.

A shell alias makes a table into a command. Here its output goes to
[feedgnuplot](https://github.com/dkogan/feedgnuplot), a command-line front end
to gnuplot, for display (`brew install feedgnuplot` on a Mac):

```text
alias pickMocomp='pick sym=moc'
pickMocomp run.moc velocities skip=100 | feedgnuplot --domain --lines
```

`velocities` is `posS vel`, the along-track position and three velocities, so
each line is x followed by three y values. With `--domain`, feedgnuplot takes
the first column as x and draws each of the others as a curve. (The original
of this example piped to xmgr, which lives on as
[Grace](https://plasma-gate.weizmann.ac.il/Grace/): `xmgrace -nxy` reads the
same columns.)

## More examples

```text
pick file1.dat 256 20c100c rec=1
```

Prints twenty characters starting at byte 100 (the 101st byte) of the second
256-byte record (`rec=1`).

```text
pick file2.dat 5120f 10f500 head=5i start=500
```

Prints ten floats starting at the 501st float (`f500`) of each 20480-byte
record, from record 500 (the 501st record) on, after a 20-byte header.

```text
pick file3.dat 80 40[ cc +1 ] skip=1
```

Prints every other character of every other record.

```text
pick gold225-1.laux 128 +90 32b -b \
   start=`pick gold225-1.laux 128 +88 w -n \
          | awk '{ if ($2==0) { print $1 ; exit;}}'` \
   | pick 4096 +439 50A
```

Three picks extract a field from an AIRSAR subcommutated header. The inner
pick prints each record's index field with its record number; awk finds the
first record whose index is 0, where a new subcommutated header begins. The
first pick then extracts the 32-byte header fragments (in binary, `-b`) from
that record on, and the last pick reads them as 4096-byte headers and prints
50 characters at byte 439.

## Errors

pick reports errors on stderr and exits with a nonzero status.

- **Couldn't find symbol table**: the table isn't in the current directory, in
  `$PICKPATH`, or among the bundled tables.
- **data requested beyond record length**: the requests go past the end of the
  record. Moves can, but reads can't: `pick ascii.txt 80 80c bn` fails, and
  `pick ascii.txt 80 80c -1 bn` is the way to add a newline.
- **Matched neither a move nor a data request**: a word pick couldn't read.
- **Unrecognized option**: often a move without a number, like `-z` for `-1z`.
- **Unexpected '='**: a `key=value` pick doesn't know.
- **Can't find record size**: the record length must come after the file name,
  even when reading stdin.

## Differences from the Perl version

pick was first written in C++ at JPL, together with the first recl, to
decode telemetry that arrived with no documentation of its structure. It was
then rewritten in Perl; that version's history, in `legacy/pick`, runs from
2000 to 2012. It was ported to Python in 2026. The command line is the same.
The output is the same, except for the fixes listed in the
[CHANGELOG](../CHANGELOG.md), chiefly about byte order on little-endian
machines.

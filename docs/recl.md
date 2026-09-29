# recl

Estimate the record length of a binary file.

```text
recl filename [ options ]
cat filename | recl - [ options ]
```

Given a file of fixed-length records whose length you don't know, recl
guesses it. Records of the same format tend to have the same bytes in the
same places: a sync word, flags, the high bytes of counters and of slowly
changing values. So more bytes equal the byte one record length further on
than the byte any other distance on. recl measures that, for each possible
length.

## Example

Make a file of 500 48-byte records, each a sync word, a counter and random
bytes, with [tgen](tgen.md):

<!-- file: frames.tgen -->
```text
sync  # 0 # 1 # 'N'   # 0x03915ed3
count # 4 # 1 # 'n'   # pmod(I, 65536)
data  # 6 # 1 # 'C42' # [int(rand(256)) for _ in range(42)]
```

```console
$ tgen -q -seed=1 frames.tgen 500 > frames.dat
$ recl frames.dat -max=100
NOTE Checking Record Lengths 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 20, 24, 25, 30, 32, 40, 48, 50, 60, 64, 75, 80, 96, 100 bytes
RESULT 48
CORR 10.7730263157895
NOTE Based on 120 buffers, each of length 200
```

`RESULT` is the estimate. `CORR` is the percentage of bytes that equal the
byte that many bytes further on; for unrelated random data it is about 0.4
(1 in 256). Here, 5 of each record's 48 bytes repeat: the sync word and the
counter's high byte. Unless told otherwise (`-partial`), recl assumes the file
holds whole records, so it only checks lengths that divide the file's size.

Every multiple of the record length agrees about as well as the length
itself, since the data repeat at those too, and one of them may score a
little higher by chance. recl reports the smallest length that divides the
best-scoring one and scores nearly as well:

```console
$ recl frames.dat -v -only=24,48,96 | tail -6
NOTE 10.87% for reclen 96
NOTE 10.75% for reclen 48
NOTE  0.37% for reclen 24
RESULT 48
CORR 10.75
NOTE Based on 125 buffers, each of length 192
```

## Options

Options can be abbreviated, and take their values after `=` or as the next
argument.

| Option | Meaning |
|---|---|
| `-skip=n` (`-header`) | skip an n-byte header |
| `-min=n`, `-max=n` | the shortest and longest lengths to check (default: 1, and half the data) |
| `-minrecs=n` | the file has at least n records (default 2): the same as `-max=`(size−skip)/n; `-max` wins |
| `-fact=n` (`-factor`, `-mult`) | the record length is a multiple of n, e.g. 8 for a file of doubles |
| `-only=a,b,...` | check only these lengths |
| `-partial` | don't assume whole records: check every length in the range |
| `-maxbufs=n` | use only the first n buffers |
| `-limit=n` | use only the first n bytes of data |
| `-reduce=f` | use only the first 1/f of the data (f ≥ 1) |
| `-full` | compare the data as one piece, not buffer by buffer |
| `-verbose` | show every length's score in every buffer, and a sorted table |
| `-quiet` | show only the result |
| `-help` | show help |

recl compares the data in buffers of twice the longest length it checks,
and averages the scores over the buffers. Data shorter than one buffer, or
all of it with `-full`, is compared as one piece.

```console
$ (printf 'HEADER-HEADER!'; cat frames.dat) > withhead.dat
$ recl withhead.dat -skip=14 -max=100 -q
NOTE Checking Record Lengths 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 20, 24, 25, 30, 32, 40, 48, 50, 60, 64, 75, 80, 96, 100 bytes
RESULT 48
$ head -c 23000 frames.dat | recl - -partial -min=40 -max=60 -q
NOTE Checking Record Lengths 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60 bytes
RESULT 48
```

## How much data recl needs

Not much, if something in each record repeats. The fraction of equal bytes
varies by about √(p/n) from one sample of n byte pairs to another, where p is
the fraction for a typical length (about 1/256 for random data), while a
record of R bytes of which k repeat raises the fraction by about k/R. A dozen
of the example's records are enough:

```console
$ tgen -q -seed=1 frames.tgen 12 | recl - -q
NOTE Checking Record Lengths 1, 2, 3, 4, 6, 8, 9, 12, 16, 18, 24, 32, 36, 48, 64, 72, 96, 144, 192, 288 bytes
RESULT 48
```

When nothing repeats exactly (records of noisy measurements, say), the high
bytes of values that change slowly still do, but more records are needed.
`-verbose` shows how clearly the best length stands out. Knowing something
about the format helps too: `-fact`, `-min` and `-max` rule out lengths, and
`-only` checks just a few.

## Differences from the Perl version

recl was written in Perl; its history in `legacy/recl` starts in 2012. The
command line and output lines are the same, but the results differ, because
the Perl version's measurement was broken (see the
[CHANGELOG](../CHANGELOG.md)):

- It counted agreeing bits, and only in the first eighth of each buffer, so
  it usually guessed wrong. recl now counts equal bytes, in the whole buffer,
  and reports the smallest of a length and its multiples when they score
  alike. (Counting bits, even all of them, works less well: a counter's low
  bits agree more often at multiples of the record length than at the length
  itself, and in text, bits agree often at any small shift.) So `CORR` is now
  a percentage of equal bytes, not of agreeing bits.
- `-full`, `-limit` and `-reduce` were accepted but ignored; they now work.
- With `-only`, buffers were sized from the last length listed rather than the
  longest, so longer lengths were never scored.
- The `-verbose` table showed fractions labeled as percentages; it now shows
  percentages.
- Reading stdin required `-max`, which was then taken as the file's size. stdin
  now works like a file.
- Data shorter than one buffer made the Perl divide by zero, and a set of
  options that left no lengths to check made it loop forever. Now the first
  is compared as one piece and the second is an error.

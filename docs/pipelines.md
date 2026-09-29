# Using the tools together

The four tools are built to be combined in pipelines: [tgen](tgen.md) makes
telemetry, [recs](recs.md) pulls records out of a stream, [recl](recl.md)
finds how long they are, and [pick](pick.md) decodes them. The two examples
here also run as part of the test suite.

## From a stream to decoded fields

A telemetry stream: 20-byte frames, each starting with the CCSDS sync word
`1ACFFC1D` and followed by 1 to 30 bytes of noise.

<!-- file: stream.tgen -->
```text
sync   # 0  # 1 # 'N'  # 0x1ACFFC1D
count  # 4  # 1 # 'N'  # I
temp   # 8  # 1 # 'f>' # 20.0 + I / 8
status # 12 # 1 # 'n'  # pmod(I, 16) << 12 | 0x042
name   # 14 # 1 # 'a6' # f"R{I:05d}"
gap    # 19 + int(rand(30)) + 1 # 1 # 'C' # F
```

The last item puts a byte at a random offset after the frame, so the frames
are followed by a random amount of random fill (`-r`):

```console
$ tgen -q -r -seed=7 stream.tgen 400 > stream.dat
```

recs pulls out 20 bytes at each sync word, and recl confirms the length:

```console
$ recs stream.dat "$(printf '\x1a\xcf\xfc\x1d')" 20 > frames.dat
$ recl frames.dat -q -max=100
NOTE Checking Record Lengths 1, 2, 4, 5, 8, 10, 16, 20, 25, 32, 40, 50, 64, 80, 100 bytes
RESULT 20
```

pick decodes each frame: the sync word, the counter (in hex), the
temperature, the two parts of the status word, and the name:

```console
$ pick frames.dat 20 -q order=big -n u ux f w6:12:4d w6:0:12x 6S | head -3
0 449838109 00 00 00 00  20 0 00 42  R00000
1 449838109 00 00 00 01  20.125 1 00 42  R00001
2 449838109 00 00 00 02  20.25 2 00 42  R00002
```

`w6:12:4d` and `w6:0:12x` read the same short (the seventh, at byte 12)
twice: its top 4 bits in decimal, and its low 12 bits in hex.

## A subcommutated header

Some formats spread a large, slowly changing header over many frames, a
piece in each: a subcommutated header. Here a 240-byte header travels 16
bytes per 32-byte frame, so it takes 15 frames to send it once.

<!-- file: header.tgen -->
```text
mission # 0   # 1 # 'A16'  # 'AIRSAR-SIM'
date    # 16  # 1 # 'a10'  # '2026-09-28'
version # 26  # 1 # 'n'    # 3
count   # 28  # 1 # 'N'    # 123456
coeffs  # 32  # 1 # 'd>10' # [k / 8 for k in range(10)]
notes   # 112 # 1 # 'A128' # 'clear skies, no wind; ' * 5
```

<!-- file: subcom.tgen -->
```text
SLICE = 16
LENGTH = 240
sync      # 0  # 1 # 'N'   # 0x03915ed3
frame     # 4  # 1 # 'N'   # I
sub_index # 8  # 1 # 'n'   # pmod(I * SLICE, LENGTH)
sub_data  # 10 # 1 # 'a16' # subcom_file('header.dat', P.sub_index.value, SLICE)
signal    # 26 # 1 # 'f>'  # sin(I / 10)
```

`sub_index` says which piece of the header a frame carries, and
`subcom_file` reads that piece. The recording starts at frame 7, partway
through a header:

```console
$ tgen -q header.tgen > header.dat
$ tgen -q subcom.tgen 100 7 > frames.dat
```

To get the header back, find the first frame whose `sub_index` is 0, and
extract the 16 bytes at byte 10 of every frame from there, in binary (`-b`).
That gives a stream of whole headers, which pick can read as 240-byte
records:

```console
$ start=$(pick frames.dat 30 -q -n order=big w4d | awk '$2 == 0 { print $1; exit }')
$ echo $start
8
$ pick frames.dat 30 -q -b +10 16b start=$start | pick 240 -q order=big 16S -1 bs 10S -1 bs wd ud 4d
AIRSAR-SIM       2026-09-28 3 123456 0 0.125 0.25 0.375
AIRSAR-SIM       2026-09-28 3 123456 0 0.125 0.25 0.375
AIRSAR-SIM       2026-09-28 3 123456 0 0.125 0.25 0.375
AIRSAR-SIM       2026-09-28 3 123456 0 0.125 0.25 0.375
AIRSAR-SIM       2026-09-28 3 123456 0 0.125 0.25 0.375
AIRSAR-SIM       2026-09-28 3 123456 0 0.125 0.25 0.375
$ pick frames.dat 30 -q -b +10 16b start=$start | head -c 240 | cmp - header.dat && echo same
same
```

(`-1 bs` backs up a byte and prints only a space, to separate the strings.)

This is the pattern of pick's AIRSAR example (`pick ?x`), which found the
start of each subcommutated header with a second pick and awk, extracted the
pieces with a first, and decoded them with a third.

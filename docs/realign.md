# realign

Put frames that start at any bit on byte boundaries.

```text
realign [options] file length_bits [offset_bits] > frames.dat
cat file | realign - [options] length_bits [offset_bits]
```

In a raw bit stream, such as PCM telemetry straight off a bit synchronizer,
frames needn't start at the start of a byte, nor be a whole number of bytes
long. [pick](pick.md) reads records byte by byte, so it can't decode them as
they are. realign cuts the stream into frames and writes each one starting on
a byte boundary, padded with 0 bits to a whole number of bytes: a 250-bit
frame becomes 32 bytes, with the frame's bit 0 as the first byte's top bit.

## Example

A stream of 250-bit frames (25 words of 10 bits), recorded starting 3 bits
before a frame, made with [tgen](tgen.md):

<!-- file: pcm.tgen -->
```text
W = 10
words = lambda n: [0b1111101011, 0b1100110011, 0b0100000111, n % 1024] \
    + [(97 * k + n // 4) % 1024 for k in range(21)]
stream = '101' + ''.join(bitstring(words(n), W) for n in range(400))
chunk # 0 # 1 # 'B1000' # stream[1000 * I : 1000 * (I + 1)]
```

[recl](recl.md) finds the frame length and where the frames start, and
suggests the realign command:

```console
$ tgen -q pcm.tgen 100 > pcm.dat
$ recl pcm.dat -bits -sync -q
NOTE Record length from repeats of a bit pattern: every 250 bits (4345 of 4469 repeats, 97%)
RESULT 250 bits (31 bytes + 2 bits)
SYNC 3 31 1111101011110011001101000001110
```

realign then puts each frame on byte boundaries, and pick can read it. The
counter is the fourth word, bits 30 to 39 of each frame: bits 16 to 25 of the
32-bit value that starts at byte 3.

```console
$ realign pcm.dat 250 3 2>&1 > frames.dat
realign: 399 frames of 250 bits from bit 3; 247 bits left over
realign: each written as 32 bytes (6 padding bits)
$ pick frames.dat 32 -q order=big -n u0+3:16:10d | head -3
0 0
1 1
2 2
```

## Bit slips

Serial streams sometimes lose or gain a bit (a bit slip), and every frame
after it is then out of step. Here, the stream loses one bit in frame 150:

<!-- file: slip.tgen -->
```text
W = 10
words = lambda n: [0b1111101011, 0b1100110011, 0b0100000111, n % 1024] \
    + [(97 * k + n // 4) % 1024 for k in range(21)]
whole = '101' + ''.join(bitstring(words(n), W) for n in range(400))
stream = whole[:37580] + whole[37581:] + '0'
chunk # 0 # 1 # 'B1000' # stream[1000 * I : 1000 * (I + 1)]
```

Stepping 250 bits at a time goes wrong from frame 151 on:

```console
$ tgen -q slip.tgen 100 > slip.dat
$ realign slip.dat 250 3 -q | pick 32 -q order=big u0+3:16:10d | sed -n '150,152p'
149
150
302
```

With `-sync`, realign finds each frame by its sync word instead, and reports
the frames that weren't the usual distance apart:

```console
$ realign slip.dat 250 -sync=1111101011110011001101000001110 2>&1 > frames.dat
realign: 399 frames found by the sync pattern
realign: frames other than 250 bits apart (bit slips, or lost frames): 249 bits (1x)
realign: each written as 32 bytes (6 padding bits)
$ pick frames.dat 32 -q order=big u0+3:16:10d | sed -n '150,152p'
149
150
151
```

A match of the pattern up to 8 bits before the end of the previous frame
(`-slip` changes this) starts a new frame: bits were lost. An earlier match
is taken to be the pattern turning up by chance in the data. `-errors=n`
lets the pattern match with up to n bits wrong, for streams with bit errors.
`recl -bits -sync` notices slips too, and suggests the `-sync` form.

## Options

Options can be abbreviated, and take their values after `=` or as the next
argument.

| Option | Meaning |
|---|---|
| `-sync=bits` | find frames by this pattern of 0s and 1s (up to 56 bits), rather than every `length_bits` |
| `-errors=n` | with `-sync`: allow up to n wrong bits in the pattern |
| `-slip=n` | with `-sync`: a match up to n bits early starts a new frame (default 8) |
| `-lsb` | the input's bits are least significant first in each byte (frames are always written most significant bit first) |
| `-left` | pad at the start of each frame rather than the end |
| `-fill=1` | pad with 1 bits rather than 0 |
| `-max=n` | write at most n frames |
| `-offset=n` | the same as giving `offset_bits` |
| `-quiet` | no summary on stderr |
| `-help` | show help |

# Tutorial: a spacecraft housekeeping stream

This walks through a [tgen](tgen.md) command file that makes realistic-looking
spacecraft housekeeping telemetry, and through the commands that generate,
decode and plot it. It assumes you have read the first page of the
[tgen manual](tgen.md); it doesn't repeat the reference material, it shows how
the pieces combine when you design a command file from scratch. The decoding
half uses [pick](pick.md).

Every example here is run by the test suite, so the output shown is real.

## What we are building

One **frame** is 54 bytes, big-endian, produced 10 times a second. It has the
kind of content a real housekeeping packet has:

| Bytes | Item | Type | What it holds |
|---|---|---|---|
| 0-3 | `sync` | u32 | the constant `0x1ACFFC1D`, so a reader can find frame boundaries |
| 4-7 | `count` | u32 | frame number |
| 8-15 | `time` | double | seconds since start |
| 16-19 | `bus_v` | float | bus voltage, about 28 V |
| 20-23 | `bus_i` | float | bus current, amps |
| 24-27 | `batt_t` | float | battery temperature, C |
| 28-43 | `quat` | 4 floats | attitude quaternion, spinning once a minute |
| 44-49 | `wheels` | 3 x s16 | reaction wheel speeds, rpm |
| 50 | `mode` | u8 | bit 0 always set; bit 1 = heater on |
| 51 | `subid` | u8 | which subcommutated channel is in `subval` |
| 52-53 | `subval` | s16 | that channel's value, in 0.01 C |

The physics is deliberately small, but the channels **interact**, which is what
makes the data interesting to plot and to decode:

- The battery temperature drifts between 12 and 18 C under a **thermostat**.
- The heater turns up the **heater current**, dips the **bus voltage**, and sets
  a bit in the **mode** byte.
- The battery temperature also appears, in a different unit, in the
  **subcommutated** channel.

## The command file

<!-- file: hk.tgen -->
```text
# Spacecraft housekeeping: 54-byte big-endian frames at 10 Hz
#
#  0 sync    u   0x1ACFFC1D        28 quat   4f  spin once a minute, with nutation
#  4 count   u   frame number      44 wheels 3s  reaction wheel speeds, rpm
#  8 time    d   seconds           50 mode   b   bit 1: heater on
# 16 bus_v   f   volts             51 subid  b   which subcommutated channel
# 20 bus_i   f   amps              52 subval s   that channel, in 0.01 C
# 24 batt_t  f   battery temp, C
T = 15.0
heater = 0
spin = 2 * pi / 600
nq = lambda q: [c / sqrt(sum(x * x for x in q)) for c in q]
sync   # 0  # 1 # 'N'    # 0x1ACFFC1D
count  # 4  # 1 # 'N'    # I
time   # 8  # 1 # 'd>'   # I / 10
bus_i  # 20 # 1 # 'f>'   # heater = 1 if T < 12 else (0 if T > 18 else heater); 2.1 + 1.4 * heater + 0.05 * (rand() - 0.5)
batt_t # 24 # 1 # 'f>'   # T = T + 0.001 * ((35 if heater else -5) - T); T + 0.02 * (rand() - 0.5)
bus_v  # 16 # 1 # 'f>'   # 28 - 0.15 * heater + 0.4 * sin(2 * pi * I / 1800) + 0.02 * (rand() - 0.5)
quat   # 28 # 1 # 'f>4'  # nq([cos(spin * I / 2), 0.03 * sin(I / 13), 0.03 * cos(I / 13), sin(spin * I / 2)])
wheels # 44 # 1 # 's>3'  # [int(1500 + 300 * sin(I / 200)), int(-800 + 50 * sin(I / 50)), int(200 * cos(I / 300))]
mode   # 50 # 1 # 'C'    # 1 + 2 * heater
subid  # 51 # 1 # 'C'    # pmod(I, 4)
subval # 52 # 1 # 's>'   # int(100 * [T, 20 + 2 * sin(I / 400), 5 + 0.001 * I, -10 + 3 * cos(I / 250)][P.subid.value])
```

Ten minutes of data, 6000 frames of 54 bytes:

```console
$ tgen -q -seed=1 hk.tgen 6000 > hk.dat
$ wc -c < hk.dat | tr -d ' '
324000
```

The rest of this page goes through the file line by line.

### The header comment

The comment block is the frame layout table (offset, name, type), written in
[pick's](pick.md) type letters (`u`, `d`, `f`, `s`, `b`), which is what you need
later to decode the data. Write the table first, then the file; when the two
disagree, the bug is usually an offset. Lines starting with `#`, `!` or `;` in
column 1 are comments.

### The state

```text
T = 15.0
heater = 0
spin = 2 * pi / 600
nq = lambda q: [c / sqrt(sum(x * x for x in q)) for c in q]
```

These lines have no ` # ` separators, so tgen treats them as Python statements,
run **once, before frame 0**. They create variables that the items share.

- `T` is the true battery temperature, starting at 15 C. It is *state*: each
  frame's value depends on the last frame's. That is how you make a stream that
  looks like a system, not like noise. An item can read and update it.
- `heater` is the thermostat state (0 or 1).
- `spin = 2*pi/600` is the spin angle per frame in radians: 600 frames at 10 Hz
  is 60 s, one turn a minute.
- `nq` is a helper function that scales a 4-element list to unit length, used
  for the quaternion. Naming it once keeps the quaternion line readable.

### sync, count and time

```text
sync   # 0  # 1 # 'N'    # 0x1ACFFC1D
count  # 4  # 1 # 'N'    # I
time   # 8  # 1 # 'd>'   # I / 10
```

Each line is `name # offset # trigger # type # value`. The trigger `1` means
"write it every frame". `'N'` is an unsigned 32-bit integer in **big-endian**
order (Perl's "network order"), and `'d>'` is a double, with `>` for big-endian.
`sync` is a constant, so a decoder has a word to synchronise on. `count` is the
frame number `I`. `time` is `I / 10`: 0.0, 0.1, 0.2, ..., one 10 Hz tick per
frame. It is computed from the frame number, not from a clock, so the output is
reproducible.

Use an explicit byte order for anything you share: `'L'` is the same size as
`'N'` but in the byte order of the machine that ran tgen, so the file would
change with the computer.

### bus_i, and the thermostat

```text
bus_i  # 20 # 1 # 'f>'   # heater = 1 if T < 12 else (0 if T > 18 else heater); 2.1 + 1.4 * heater + 0.05 * (rand() - 0.5)
```

This is the densest line. The value field holds **two statements** separated by a
semicolon, and, as the tgen manual says, the field's value is the last one.

1. `heater = 1 if T < 12 else (0 if T > 18 else heater)` is a thermostat with
   **hysteresis**: switch on below 12 C, off above 18 C, and between 12 and 18
   keep doing whatever it was doing (`else heater` is the hold). With a single
   threshold instead, the heater would chatter.
2. `2.1 + 1.4 * heater + 0.05 * (rand() - 0.5)` is what gets written: a 2.1 A
   baseline, 1.4 A more with the heater on, and +/-0.025 A of noise (`rand()` is
   uniform in [0, 1), so `rand() - 0.5` is in [-0.5, 0.5)).

### batt_t, the thermal model

```text
batt_t # 24 # 1 # 'f>'   # T = T + 0.001 * ((35 if heater else -5) - T); T + 0.02 * (rand() - 0.5)
```

Again two statements.

1. `T = T + 0.001 * (target - T)` is a first-order lag: each frame, `T` closes
   0.1 % of the gap to a *target* temperature, 35 C with the heater on and -5 C
   with it off. That is a time constant of 1000 frames, 100 s. The thermostat's
   switch points (12 and 18) sit well inside that range, so the temperature moves
   in gently curved segments, as a real thermal control loop does on a plot.
2. `T + 0.02 * (rand() - 0.5)` is the **reported** value: `T` plus +/-0.01 C of
   sensor noise. The noise is added to the output but never stored back into `T`,
   so measurement noise doesn't feed back into the physics. Keep the state clean,
   and put noise only in the value that is written.

The mode byte (below) shows the heater switching. Here are the frames where it
changes:

```console
$ pick hk.dat 54 -q order=big b50d | awk 'NR > 1 && $1 != p { print NR - 1 } { p = $1 }' | head -4
163
466
769
1072
```

The heater changes state every 303 frames (30.3 s), about one cycle a minute.

### bus_v, a second quantity that follows the heater

```text
bus_v  # 16 # 1 # 'f>'   # 28 - 0.15 * heater + 0.4 * sin(2 * pi * I / 1800) + 0.02 * (rand() - 0.5)
```

28 V nominal, 0.15 V lower while the heater draws current, plus a slow
180-second (1800-frame) swing of +/-0.4 V standing in for the orbit or solar
cycle, plus noise. The heater shows up as small steps riding on the wave.

Notice that this item has the **lower offset (16)** but comes **after** `bus_i`
(20) and `batt_t` (24) in the file. Offsets say where a value goes; file order
says when it is computed. The two are independent.

### quat, a list

```text
quat   # 28 # 1 # 'f>4'  # nq([cos(spin * I / 2), 0.03 * sin(I / 13), 0.03 * cos(I / 13), sin(spin * I / 2)])
```

`'f>4'` is four big-endian floats, so the value is a list of four numbers: a unit
quaternion, scalar first.

- `cos(spin*I/2)` and `sin(spin*I/2)` are the scalar and z parts of a rotation
  about the z axis by the angle `spin * I`: one turn every 600 frames.
- `0.03 sin(I/13)` and `0.03 cos(I/13)` are small x and y parts that circle with
  a period of about 82 frames (8 s): the **nutation**, a wobble on top of the
  spin.
- `nq(...)` normalises the result, since the four parts as written aren't quite
  unit length.

At frame 0 the scalar is 1 and the z part is 0; at 150 they are 0.707 each; at
300 the scalar is 0 and z is 1; at 600 the scalar is -1 (a full turn is `-q`, as
quaternions go). On a plot, `q0` against `q3` traces a circle.

### wheels, integers

```text
wheels # 44 # 1 # 's>3'  # [int(1500 + 300 * sin(I / 200)), int(-800 + 50 * sin(I / 50)), int(200 * cos(I / 300))]
```

Three big-endian **signed** 16-bit values (`s>3`): three sine waves of different
period and amplitude, centred on 1500, -800 and 0 rpm. `int()` is needed because
`s` packs an integer, and the sign matters, since the second wheel is negative.
Each wheel has a different centre, amplitude and period so that the three curves
are easy to tell apart.

### mode, a packed flag byte

```text
mode   # 50 # 1 # 'C'    # 1 + 2 * heater
```

One unsigned byte, `1 + 2 * heater`. Bit 0 is always 1 (a "powered" flag, say)
and bit 1 is the heater, so the byte is 1 with the heater off and 3 with it on.
That is the usual way status bits are packed, and it's why the decoding step
below has to pull the heater out with `int(mode / 2) % 2`.

### subid and subval, subcommutation

```text
subid  # 51 # 1 # 'C'    # pmod(I, 4)
subval # 52 # 1 # 's>'   # int(100 * [T, 20 + 2 * sin(I / 400), 5 + 0.001 * I, -10 + 3 * cos(I / 250)][P.subid.value])
```

**Subcommutation** is how real telemetry fits many slowly changing channels into
a few bytes: one slot in every frame carries a different channel each time, and a
counter (`subid`) says which. Here `subid` counts 0, 1, 2, 3, 0, ... and `subval`
carries:

| subid | channel | in the model |
|---|---|---|
| 0 | battery temperature | the true `T` |
| 1 | solar panel | 20 C plus a slow wobble |
| 2 | tank | 5 C, slowly warming |
| 3 | radiator | -10 C plus a wobble |

The value is a Python list of four numbers, indexed by `P.subid.value`: the value
the `subid` item wrote in *this* frame (see the tgen manual's table of names). The
index and the `subid` byte can therefore never disagree, whatever you later
change. `int(100 * ...)` scales to hundredths of a degree so that it fits a
16-bit integer (+/-327.67 C). Every channel arrives every fourth frame: 2.5 Hz.

Channel 0 carries `T`, the *stored* temperature, not the noisy `batt_t`: a
cleaner copy of the same thing, in different units. In frame 0, `batt_t` is
14.9791 while `subval` is 1498 (14.98 C).

### Order of evaluation

Item lines run in file order, so within one frame:

```text
sync, count, time         constants and counters
bus_i                     decides heater (from last frame's T)
batt_t                    updates T, using this frame's heater
bus_v                     reads heater
quat, wheels              independent
mode                      reads heater
subid, subval             read T after this frame's update
```

That order is the design. If `batt_t` came before `bus_i`, the temperature would
be updated with the previous frame's `heater`, and `bus_v`, `mode` and `bus_i`
would disagree with it by one frame. When one item depends on another, put the
dependency first in the file; the byte offsets are free to be in any order. (As
written, `heater` itself is decided from the *previous* frame's `T`, a one-frame
lag that doesn't show, as in a real controller.)

All 54 bytes are covered by items, so the fill byte is never used, and the frame
length comes for free: tgen makes a frame as long as its last item ends
(`subval`, at 52, two bytes).

## The tgen command

```text
tgen -q -seed=1 hk.tgen 6000 > hk.dat
```

| Part | Meaning |
|---|---|
| `-q` | no progress reports on stderr (otherwise one every 100 frames) |
| `-seed=1` | seed the random numbers, so `rand()` is repeatable and this command always makes the *same* file. Without it, the noise differs on every run. |
| `hk.tgen` | the command file |
| `6000` | the number of frames: 6000 x 54 = 324,000 bytes, ten minutes at 10 Hz |
| `> hk.dat` | tgen writes the frames to standard output; redirect them to a file, or pipe them |

A third argument sets the first frame number: `tgen -q hk.tgen 6000 1000` starts
at `I = 1000`. To look at frames as they are made, pipe straight into pick, as
below.

## The first frame, byte by byte

pick's `b` type with the `x` format is a hex dump. Frame 0:

```console
$ tgen -q -seed=1 hk.tgen 1 | pick 54 -q 54bx
1a  cf  fc  1d  00  00  00  00  00  00  00  00  00  00  00  00  41  e0  0d  b7  40  04  ee  e7  41  6f  aa  5a  3f  7f  e2  87  00  00  00  00  3c  f5  a6  44  00  00  00  00  05  dc  fc  e0  00  c8  01  00  05  da
```

With the fields marked:

```text
1acffc1d                sync
00000000                count = 0
0000000000000000        time = 0.0
41e00db7                bus_v = 28.0067
4004eee7                bus_i = 2.07708
416faa5a                batt_t = 14.9791
3f7fe287 00000000       q0 = 0.99955, q1 = 0
3cf5a644 00000000       q2 = 0.0299865, q3 = 0
05dc fce0 00c8          wheels = 1500, -800, 200
01                      mode = 1 (heater off)
00                      subid = 0
05da                    subval = 1498 (14.98 C)
```

Every value can be found by hand. For example `05dc` is 1500, `fce0` is -800 as a
signed 16-bit number, and `1acffc1d` is the sync word: the layout table, the
`pack` types and the bytes agree.

## Decoding with pick

```console
$ pick hk.dat 54 -q order=big rec=0 u1 d1 3f4 4f7 3s22 b50d b51d s26
0 0 28.0067 2.07708 14.9791 0.99955 0 0.0299865 0 1500 -800 200 1  0  1498
```

pick reads fixed-length records and prints fields: the decoder half of the pair.
Its requests are written from the layout table:

| Request | Meaning |
|---|---|
| `hk.dat 54` | the file, and the record length: 54 bytes |
| `-q` | quiet: no diagnostics |
| `order=big` | the data are big-endian. **Required**: pick's default is this machine's order, and the numbers would be garbage. |
| `rec=0` | only record 0 (leave it out to print all 6000) |
| `u1` | one unsigned 4-byte int at **item** 1, which is byte 4: `count`. (`u0` would be the sync word, which we skip.) |
| `d1` | one double at item 1, byte 8: `time` |
| `3f4` | three floats from float item 4 (byte 16): `bus_v`, `bus_i`, `batt_t` |
| `4f7` | four floats from float item 7 (byte 28): `q0` to `q3` |
| `3s22` | three signed shorts from short item 22 (byte 44): the wheels |
| `b50d` | the byte at 50, in **d**ecimal: `mode` |
| `b51d` | the byte at 51, in decimal: `subid` |
| `s26` | a signed short at short item 26 (byte 52): `subval` (`d` is the default format for `s`) |

An offset in pick counts **items of that type**, from 0, not bytes: `3f4` starts
at byte 4 x 4 = 16, and `s26` at 26 x 2 = 52. That is why the layout comment
gives byte offsets and the pick request uses different numbers; the conversion is
worth doing carefully. (pick also takes byte offsets, like `f0+16`, and `+n`
moves, if you prefer to count bytes.)

## From pick to a plot

pick prints text, so any text tool can take over. This awk script turns the
fields into a CSV with named columns:

<!-- file: tocsv.awk -->
```text
# pick output (count time bus_v bus_i batt_t q0..q3 w1..w3 mode subid subval) -> CSV
BEGIN { OFS = ","; print "time,count,bus_v,bus_i,batt_t,q0,q1,q2,q3,wheel1,wheel2,wheel3,heater,T_battery,T_panel,T_tank,T_radiator" }
{
  split(",,,", sub4, ",")          # four empty subcom cells
  sub4[$14 + 1] = $15 / 100
  print $2, $1, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, int($13 / 2) % 2, sub4[1], sub4[2], sub4[3], sub4[4]
}
```

```console
$ pick hk.dat 54 -q order=big u1 d1 3f4 4f7 3s22 b50d b51d s26 | awk -f tocsv.awk | head -5
time,count,bus_v,bus_i,batt_t,q0,q1,q2,q3,wheel1,wheel2,wheel3,heater,T_battery,T_panel,T_tank,T_radiator
0,0,28.0067,2.07708,14.9791,0.99955,0,0.0299865,0,1500,-800,200,0,14.98,,,
0.1,1,27.9914,2.0918,14.9613,0.999537,0.00230438,0.0298978,0.00523361,1501,-799,199,0,,20,,
0.2,2,28.0078,2.08438,14.9499,0.999496,0.00459513,0.0296323,0.0104671,1502,-798,199,0,,,5,
0.3,3,28.0057,2.09331,14.9171,0.999427,0.00685871,0.0291916,0.0157003,1504,-797,199,0,,,,-7
```

- `BEGIN` prints the header row.
- `split(",,,", sub4, ",")` makes an array of four empty strings.
- `sub4[$14 + 1] = $15 / 100` puts this frame's `subval` into the slot named by
  `subid` (field 14), converting hundredths of a degree to degrees. awk arrays
  count from 1, hence the `+ 1`.
- `print` reorders the columns (time first), turns `mode` back into a heater flag
  (`int($13 / 2) % 2`: shift right one bit, keep one bit), and prints the four
  temperature cells, **three of them empty** on any given row.

The empty cells are deliberate. A plotting program shows `T_battery`, `T_panel`,
`T_tank` and `T_radiator` as four separate curves with one point every fourth
row: subcommutation, unpacked. Load the CSV into a plotting program such as
[PlotJuggler](https://plotjuggler.io) (File, Load data), or plot straight from
the pipe with [feedgnuplot](https://github.com/dkogan/feedgnuplot), a
command-line front end to gnuplot (`brew install feedgnuplot` on a Mac):

```text
pick hk.dat 54 -q order=big d1 3f4 | feedgnuplot --domain --lines --legend 0 bus_v --legend 1 bus_i --legend 2 batt_t
```

## Design notes

What makes this file a good template:

1. **Write the layout table first**, in the decoder's vocabulary.
2. **Keep hidden state in variables** (`T`, `heater`), with the noise added only to
   the value written.
3. **Make channels depend on each other** (heater to current to voltage to mode
   bit to temperature). It costs one variable and gives a decoder real structure
   to be tested against.
4. **Put dependencies first** in the file; offsets don't depend on order.
5. **Use an explicit byte order** (`N`, `'f>'`, `'s>3'`), never the machine's.
6. **Seed the random numbers**, so a test is repeatable.
7. **One line per item**, aligned, so the file reads as the table.

## Exercises

1. Change the thermostat limits to 10 and 20 and rerun the heater-edge command
   above: the interval between changes grows.
2. Add a trailer at offset 54, for example `crc # 54 # 1 # 'n' # 0xBEEF` (a 16-bit
   big-endian word). The frame becomes 56 bytes: update the layout comment and
   pick's record length. For a real checksum, put `import zlib` on a statement
   line and use `zlib.crc32(...)` with the type `'N'` (4 bytes).
3. Add a fifth subcommutated channel: change `pmod(I, 4)` to `pmod(I, 5)`, extend
   the list, and fix the awk (`split(",,,,", ...)` and one more column).
4. Make the heater fail at frame 3000, by wrapping the thermostat as
   `heater = (1 if T < 12 else (0 if T > 18 else heater)) if I < 3000 else 0;`.
   The battery temperature falls away toward -5 C (it is 3.4 C at frame 3900)
   while the mode bit stays flat. Faults like this are what test data is for.
5. Drop a counter value: give `count` the trigger `I % 100 != 50`. Frame 50 is
   still written, but its `count` isn't, so it holds the fill byte (0): a skipped
   counter a decoder has to spot. Compare `turing.tgen` in the tgen manual, where
   changing `I` changes how many frames are made.

# tgen

Generate telemetry: records whose layout is described by a command file.

```text
tgen [ options ] command_file [ nframes [ firstframe ] ] > telemetry.dat
tgen --convert perl_command_file > python_command_file
```

tgen writes `nframes` records (frames) to stdout, 1 by default, numbering
them from `firstframe` (default 0). The command file says which bytes of each
frame hold what: counters, constants, calculated values, random data, or
data read from other files. tgen is useful for testing software that reads
telemetry, and for packaging data computed elsewhere into a telemetry format.
[pick](pick.md) is the natural tool for looking at the result.

## A first example

<!-- file: counter.tgen -->
```text
# Generate different counters
every_pulse_byte       # 0 # 1 # 'C' # pmod(I, 256)
every_other_pulse_byte # 1 # 1 # 'C' # pmod(I/2, 256)
count_to_4             # 2 # 1 # 'C' # pmod(I, 4) + 1
every_pulse_long       # 3 # 1 # 'L' # I
```

Each item line gives a name, a byte offset, a trigger, a type and a value.
`I` is the frame number. Ten frames starting at 250, looked at with pick:

```console
$ tgen -q counter.tgen 10 250 | pick 7 -q 3bd ud
250  125  3  250
251  125  4  251
252  126  1  252
253  126  2  253
254  127  3  254
255  127  4  255
0  128  1  256
1  128  2  257
2  129  3  258
3  129  4  259
```

## Options

Options can be abbreviated (`-q`, `-qu`, `--quiet`) and given as `-f 255` or
`--fill=255`.

| Option | Meaning |
|---|---|
| `-f n`, `-fill=n` | the byte value (0 to 255) for bytes no item sets (default 0); also the value of `F` |
| `-r`, `-random` | fill with random bytes; `F` gives a new random byte on every use |
| `-seed=n` | seed the random numbers (`rand` and `-r`), so a run can be repeated |
| `-n n`, `-notify=n` | report progress on stderr every n frames (default 100) |
| `-q`, `-quiet` | no progress reports |
| `-convert` | translate a Perl tgen command file to the Python form, below |
| `-v`, `-version` | show the version |
| `-h`, `-help` | show help |

## The command file

A command file has three kinds of lines:

- **Comments**, starting with `#`, `!` or `;` in the first column.
- **Item specifications**, with at least four field separators: a `#` with
  white space on both sides. Fields after the fifth are ignored, so a
  trailing ` # comment` is fine.
- **Statements**: any other line is Python, run once before the first frame.
  Use them to set constants: `PN = 0x03915ed3`.

A line ending in a backslash continues on the next line.

### Item specifications

```text
name # offset # trigger # type # value
```

Every field except the name is Python code, evaluated for every frame, in the
order the items appear in the file (which needn't be the order of their
bytes in the frame). A field can hold several statements separated by
semicolons; its value is the last one's.

- **name** identifies the item, for `P.name.value` (below).
- **offset** is the byte where the value goes, counting from 0. It can vary
  from frame to frame, for example `int(rand()*252)+4`. Items may overlap:
  the later one wins. A **negative offset** means "evaluate the value, but
  don't write it", which makes the item a per-frame calculation.
- **trigger**: when false, the item is skipped for this frame. False means
  0, `None`, `""` or `"0"`, as in Perl.
- **type** is a Perl `pack` template: `'C'` (unsigned byte), `'c'`, `'S'`,
  `'s'` (16 bits), `'L'`, `'l'` (32 bits), `'n'`, `'N'` (big-endian 16 and 32
  bits), `'v'`, `'V'` (little-endian), `'f'`, `'d'` (floats), `'a10'` (a
  null-padded 10-byte string), `'A10'` (space-padded), `'Z10'`
  (null-terminated), `'B16'` (16 bits, from a string of `0`s and `1`s,
  most significant bit first; `'b16'` for least significant first). Integer
  and float types can take `<` or `>` for the byte order; without one, it is
  this machine's. A count takes a list: `f"C{n}"` with the value `[1, 2, 3]`.
  The type isn't evaluated for items with a negative offset.
- **value** is the value to write.

Frames are as long as their last item. Bytes that no item sets are filled
with the fill byte.

### Names in the code

| Name | Meaning |
|---|---|
| `I` | the frame number; an item may change it (see below) |
| `F` | the fill byte. Set `F = 255` to change the fill, or `F = "random"` for random fill; with random fill, every use of `F` gives a new random byte |
| `P.name.value` | an item's value in this frame, or in the last frame if the item hasn't been evaluated yet (likewise `.offset`, `.trigger`, `.type`) |
| `P.name._value` | evaluates the item's value field again (and `._offset` etc.) |
| `X`, `O` | set by `seek_file` |
| `DEBUG` | set true to trace every evaluation on stderr |
| `rand(n)` | a random float in [0, n), 1 by default (Perl's generator, so `-seed` runs repeat) |
| `pmod`, `pand`, `por`, `pxor`, `pshl`, `pshr` | Perl's `%`, `&`, `\|`, `^`, `<<`, `>>`, on integers |
| `cat(a, b, ...)` | Perl's `.`: join values as text |
| `bitstring(values, width)` | values as a string of bits for the `B` type: `bitstring([3, 5], 4)` is `'00110101'`; `width` may be a list, one per value |
| `sprintf` | Perl's sprintf |
| `pi`, `sin`, `cos`, `tan`, `atan2`, `sqrt`, `exp`, `log`, `floor`, `ceil` | from Python's `math` |
| `stderr` | for diagnostics: `print(..., file=stderr)`. Don't print to stdout, which is the data |

### Reading other files

- **`subcom_file(file, offset, nbytes)`** returns `nbytes` bytes of `file`
  from `offset`, for an `'a'` type: this is how to put subcommutated data
  into frames.
- **`file_lookup(file, offset, nbytes, type)`** returns the first value
  unpacked (with a pack template) from those bytes.
- **`seek_file(file, offset, nbytes, type, condition)`** reads `nbytes` at
  `offset` for O = 0, 1, 2, ..., unpacking each value into `X`, until
  `condition` is true, and returns the offset (or -1 at the end of the file).
  `offset` and `condition` are code, as strings: for a file of (angle, gain)
  float pairs, `seek_file('ant.dat', '8*O', 4, 'f', 'X > I/10.0')` finds the
  first angle greater than the frame number divided by 10.

Each file is opened once per run.

## Examples

These are the examples that come with the original tgen, translated. They are
also in the package, in `telemetry_cli/tgen/examples/`.

### Changing behavior frame by frame

<!-- file: cond_fill.tgen -->
```text
zero_fill # -1 # I % 3 == 0 # X # F = 0
rail_fill # -1 # I % 3 == 1 # X # F = 255
rand_fill # -1 # I % 3 == 2 # X # F = "random"
pulse     # 0  # 1 # 'C' # I
last_byte # 9  # 1 # 'C' # F
```

The first three items only set the fill, depending on the frame number:

```console
$ tgen -q -seed=1 cond_fill.tgen 4 | pick 10 -q 10bx
00  00  00  00  00  00  00  00  00  00
01  ff  ff  ff  ff  ff  ff  ff  ff  ff
02  d5  56  90  00  30  fd  c0  5d  74
03  00  00  00  00  00  00  00  00  00
```

### Lists of values

<!-- file: list.tgen -->
```text
n = 4
sync  # 0 # 1 # 'N'      # 0x03915ed3
count # 4 # 1 # f"C{n}"  # [I * k for k in range(n)]
```

```console
$ tgen -q list.tgen 3 1 | pick 8 -q order=big ux 4bd
03 91 5e d3  0  1  2  3
03 91 5e d3  0  2  4  6
03 91 5e d3  0  3  6  9
```

### Random record lengths

<!-- file: random_size.tgen -->
```text
pn   # 0                 # 1 # 'L' # 0x03915ed3
data # int(rand()*252)+4 # 1 # 'C' # F
```

The offset of the last byte is random, so each frame's length is too:

```console
$ tgen -q -seed=2 random_size.tgen 3 | wc -c | tr -d ' '
428
```

### A variable number of frames

<!-- file: turing.tgen -->
```text
random   # 0  # 1 # 'f' # rand(1.0)
finished # -1 # 1 # X   # I = I - 1 if P.random.value < 0.5 else I
```

Changing `I` changes how many frames are written: here, only random numbers
of 0.5 or more count toward the number asked for.

```console
$ tgen -q -seed=4 turing.tgen 10 | pick 4 -q f | wc -l | tr -d ' '
22
```

### value and _value

<!-- file: value.tgen -->
```text
random_number # 0 # 1 # 'f' # rand(1.0)
COUNT1 = 0
COUNT2 = 0
value_1 # 4 # 1 # 'S' # COUNT1 = COUNT1 + 1 if P.random_number._value > 0.5 else COUNT1; COUNT1
value_2 # 6 # 1 # 'S' # COUNT2 = COUNT2 + 1 if P.random_number.value > 0.5 else COUNT2; COUNT2
```

`value_2` counts the frames whose random number is above 0.5. `value_1`
doesn't: `_value` calls `rand` again.

```console
$ tgen -q -seed=9 value.tgen 4 | pick 8 -q f 2wd
0.00804881 0 0
0.742382 0 1
0.470977 1 1
0.150752 2 1
```

### Words that aren't whole bytes

Telemetry words are often 10 or 12 bits. `bitstring` and the `B` type pack
them: two 12-bit words, then a 16-bit count, in 5 bytes:

<!-- file: words.tgen -->
```text
packed # 0 # 1 # 'B40' # bitstring([0xABC, I, 1000 + I], [12, 12, 16])
```

```console
$ tgen -q words.tgen 3 | pick 5 -q 5bx
ab  c0  00  03  e8
ab  c0  01  03  e9
ab  c0  02  03  ea
```

Frames whose length isn't a whole number of bytes go several to a record: see
[recl's `-bits`](recl.md#records-that-arent-whole-bytes).

### A caltone sweep

<!-- file: calsweep.tgen -->
```text
pi = 3.141592654                    # (the original's value of pi)
nf = 10                             # number of caltones
f0 = 5.0e6                          # lowest caltone frequency
f_max = 35.0e6                      # highest caltone frequency
df = (f_max - f0) / (nf - 1)        # frequency step
f = [f0 + k*df for k in range(1, nf + 1)]
fs = 90.0e6                         # sampling rate
a = 2.0 * pi / fs
ns = 256                            # samples per frame

calfreq # -1 # 1 # X      # pmod(I/32, nf)   # 32 frames per caltone
data    # 0  # 1 # f"C{ns}" # [128 + int(128.0*cos(a*k*f[P.calfreq.value])) for k in range(1, ns)]
```

This simulates the caltone sweep of an AIRSAR calibration sequence: 256
8-bit samples per frame, stepping through ten frequencies.

```console
$ tgen -q calsweep.tgen 500 > calsweep.dat
$ pick calsweep.dat 256 -q every=100 8bd
234  178  106  41  4  8  52  121
164  22  30  178  255  150  14  41
78  41  248  121  14  226  164  1
14  204  106  92  215  8  255  22
191  64  0  65  192  0  191  64
```

It is best seen as an image, one row per frame. With
[ImageMagick](https://imagemagick.org) (`brew install imagemagick` on a Mac):

```text
magick -depth 8 -size 256x500 gray:calsweep.dat calsweep.png
```

The image shows bands of 32 rows, one per caltone. The spacing of the fringes
changes from band to band as the frequency steps, and the pattern repeats
after the ten caltones, 320 rows down. (ImageMagick 6 and earlier call the
command `convert`, with the same arguments.)

## Converting Perl command files

The original tgen was written in Perl, and its command files were Perl code.
`tgen --convert` translates them:

<!-- file: old.tgen -->
```text
$::PN = 0x03915ed3;
pn    # 0 # 1          # 'N' # $::PN
lo    # 4 # 1          # 'C' # $::PN & 0xff
count # 5 # $::I % 2   # 'C' # $::I
```

```console
$ tgen --convert old.tgen
PN = 0x03915ed3
pn    # 0 # 1          # 'N' # PN
lo    # 4 # 1          # 'C' # pand(PN, 0xff)
count # 5 # pmod(I, 2)   # 'C' # I
```

It handles `$::name` variables, `$P{item}{field}`, arithmetic, `%` and the
bit operators (with Perl's integer semantics), string concatenation,
interpolated strings (`"C$::ns"`), `map { ... } (1..n)`, `++` and `--`, and
statement modifiers (`$::x++ if ...`). A line it can't translate, such as one
defining a Perl `sub`, gets a `# TODO(convert)` comment line above it. The
converted file then fails with an error until someone finishes it by hand,
rather than doing something different.

Converted files give byte-for-byte the same output as the Perl tgen did with
the originals, including random output when the Perl ran with the same seed.

## Differences from the Perl version

tgen was written in Perl at JPL in 2003. The command line is the same, and a
converted command file generates the same data. The differences:

- Command files are Python, not Perl (see above).
- An error in a field stops tgen, with the file, line and field. The Perl
  silently used the text of the field as its value.
- Files read by `subcom_file`, `file_lookup` and `seek_file` are opened once,
  not once per frame (a to-do item in the original).
- A bad option is an error; the Perl warned and carried on.
- `-seed` is new.

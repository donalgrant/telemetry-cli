# How telemetry-cli is built

This guide explains the design of telemetry-cli for developers. It covers
what each part does, how the parts fit together, why they were built this
way, and how the Python differs from the Perl it replaces. It is also meant
to teach. Some of the problems here come up in many other projects:

- porting a program whose exact output other people rely on;
- using the old program as a test oracle;
- imitating another language's semantics only where they matter;
- detecting a period in noisy data;
- running a small language embedded in a config file safely.

Where a design choice has a reason that isn't obvious, or a first attempt
went wrong, this guide says so.

The tools began at JPL. pick and recl were C++ programs, written together to
decode telemetry that arrived with no description of its structure. Later
they were rewritten in Perl, along with recs and tgen. The Perl originals,
with their git history, are in `legacy/`. Section 2 sets out the rules the
port follows, and section 9 lists every place the Python deliberately
differs from the Perl, with the reason for each.

Contents:

1. [The layers](#1-the-layers)
2. [Ground rules of the port](#2-ground-rules-of-the-port)
3. [pick: a command line that is a language](#3-pick-a-command-line-that-is-a-language)
4. [recs: a faithful buffer](#4-recs-a-faithful-buffer)
5. [recl: finding a period](#5-recl-finding-a-period)
6. [tgen: a language inside a config file](#6-tgen-a-language-inside-a-config-file)
7. [realign: frames at any bit](#7-realign-frames-at-any-bit)
8. [Testing](#8-testing)
9. [Changes from the Perl, and why](#9-changes-from-the-perl-and-why)
10. [Lessons from the bugs](#10-lessons-from-the-bugs)
11. [Exercises](#11-exercises)

---

## 1. The layers

The package is about 4,400 lines of Python in `src/telemetry_cli/`. Its only
runtime dependency is numpy. Each tool is a subpackage with a `cli.py`.
Below the tools is a thin layer of shared modules, each of which reproduces
one piece of Perl behavior that the output depends on:

```
  tools        pick/          recs/          recl/          tgen/          realign/
               commandline    extract        corr           cmdfile        frames, cli
               fields         cli            bits           runtime          │
               formats                       sync           convert          │
               help, symbols/                cli            cli              │
               cli                            ▲                              │
                                              └──── realign reuses recl.bits ┘
                   │              │              │              │              │
  shared       _perl.py   numbers, printf, substr, truthiness as Perl has them
               _pack.py   Perl's pack/unpack letters (for tgen)
               _getopt.py Getopt::Long's option syntax (recs, recl, tgen, realign)
               _msg.py    Util::Msg's "TAG text" lines (recl's output format)
               _cli.py    a quiet exit when stdout closes early (tool | head)
```

| module | lines | replaces |
|---|---:|---|
| `pick/` (with help text and symbol tables) | ~1,300 | `pick` (1,662 lines of Perl) |
| `recs/` | ~580 | `recs` (892) |
| `recl/` | ~780 | `recl` (256) |
| `tgen/` | ~890 | `tgen` (1,247) |
| `realign/` | ~260 | new |
| `_perl`, `_pack`, `_getopt`, `_msg`, `_cli` | ~570 | Perl itself, Getopt::Long, `Util/Msg.pm` (222) |

recl is the only module that grew. Its Perl measurement was broken
(section 5), and recl gained `-bits` and `-sync`. pick and recs are close
ports and kept the Perl's structure. tgen changed most in kind, since its
command files are now Python (section 6).

Every `main()` has the same shape. It takes `argv`, `stdin`, `stdout` and
`stderr` as arguments, defaulting to the real ones, and pick also takes
`host_order`. It returns an exit status instead of calling `sys.exit`. So a
test can run any tool in-process on bytes and inspect everything it wrote,
and the golden tests can emulate a big-endian machine on a little-endian
one (section 8).

---

## 2. Ground rules of the port

### Byte-identical, with every exception named

The tools are used in pipelines and scripts, so their exact output is an
interface: someone's awk script depends on pick's column spacing. The rule
is that **the Python's output equals the Perl's, byte for byte**, except
for deliberate changes, and each of those is:

- named in the CHANGELOG (for example "pick byte order" or "recs null fill");
- tagged with that name (`fix = "pick byte order"`) on the golden test cases
  that check it;
- given a reference for the right answer that is not the Python itself.
  Each case names one of three: another case to mirror, Perl arguments that
  produce the intended output, or a different Perl run (section 8).

This makes "is this difference a bug?" a question with an answer. A
difference with no `fix` tag is a bug in the port. One with a tag is a
decision someone made and wrote down.

What counts as a deliberate change (section 9 has them all):

- **Bugs where the Perl contradicts its own documentation.** For example,
  pick's `-l` and `-n` were swapped, and recs padded with `"0"` where the
  documentation says null bytes. The documentation won, because it is what
  users were told.
- **Behavior that depended on the machine.** pick printed different bytes on
  little-endian machines. The big-endian behavior, which matches what the
  author intended, is now the behavior everywhere.
- **Failures that were silent.** Errors printed to stdout with exit status 0,
  endless loops, and bad options that were ignored now stop with a message
  on stderr and a nonzero exit status.
- **Measurements that didn't work.** recl's scoring is replaced, so its
  output differs from the Perl's.

What was **kept**, even when it is odd, is behavior a user could reasonably
rely on:

- pick's spacing;
- `G` padding to 25 characters;
- the data type, not the format, deciding the sign;
- `PI = 3.14159265359` in the `D` format;
- how pick reads its command line;
- how a recs marker that straddles two buffers is found.

The rule for these is to document them, not fix them. pick's manual has a
Quirks section for exactly that.

### The Perl is the oracle

The port has a reference implementation available: the old program, still
runnable. `tools/make_golden.py` runs the Perl in `legacy/` on every golden
case and stores its stdout byte for byte, plus its exit status and stderr.
The Hypothesis fuzz tests (`-m oracle`) run the Perl live on random inputs.
The expected output is never written by hand from what the Python prints,
because that only tests that the Python agrees with itself. (The help text
is the exception: its corrections are maintained by hand, and
`make_golden.py --fixes` rewrites those cases.)

### Imitate Perl only where the output shows it

Perl and Python differ in many small ways that a port can trip over. Here
are some of them:

| Perl | Python |
|---|---|
| `"12abc" + 0` is 12 | `int("12abc")` raises |
| `-0.0 * 180` is `0` (integer arithmetic) | `-0.0` |
| `printf "%d", "1e400"` saturates to the largest integer | overflow, or `inf` |
| `"0"` is false | `"0"` is true |
| `substr($s, -3)` counts from the end | slices, with different edge cases |
| floats print with 15 significant digits | `repr` prints 17 |
| `%` on floats truncates both operands to integers | `%` is a float remainder |

Each such difference that reaches the output is handled by one small,
tested function in `_perl.py`: `numify`, `multiply`, `sprintf`, `substr`,
`truthy`, `perl_str`, `to_iv` and `to_uv`. They are used only where needed.
The rest of the code is ordinary Python. This keeps the port readable. It
reads as a Python program that calls `numify` in the three places Perl's
string-to-number rules matter, not as a Perl interpreter written in Python.

`_pack.py` and `_getopt.py` follow the same idea at a larger scale:

- `_pack.py` implements the pack letters that tgen command files use
  (`c C s S l L i I q Q n N v V f d a A Z B b x`), with Perl's rules for
  counts, padding and out-of-range values.
- `_getopt.py` implements the parts of Getopt::Long that users type:
  - one or two dashes;
  - case-insensitive names;
  - unique prefixes (`-ma` for `-max_reclen`);
  - `-e -r` setting `e` to `-r`;
  - `--` ending the options.

  It has one deliberate difference: a bad option raises `OptionError`,
  where Getopt::Long warned and carried on.

### Bytes, latin-1 and stdout

All data are bytes. The command-line strings that become data, such as recs
markers, pick's character formats and tgen strings, go through latin-1. Its
256 code points map one to one onto byte values, so any byte survives the
round trip. The Perl worked on bytes the same way.

A tool piped into `head` gets a broken pipe when `head` exits. Python would
print a traceback, or an error at shutdown when it flushes stdout. Every
tool catches this and exits 0 through `_cli.broken_pipe`, which points
stdout at `/dev/null` so the final flush is silent, as Unix tools do.

Exit codes: recs, recl, tgen and realign exit 2 for usage errors (as
argparse and most Unix tools do) and 1 for runtime errors. pick exits 1 for
every error, with a hint naming the help topic to read
(`(see 'pick --help p')`).

---

## 3. pick: a command line that is a language

pick's command line is a small language:

```text
pick data.bin 36 -q order=big start=2 '3[ bd 3[ w bd ] bn +1 ]'
     file     record  options and       field requests: types, formats,
              size    parameters        moves and repeated groups
```

### Reading the command line by subtraction

pick does not parse its arguments one by one, and neither did the Perl. It
joins argv into one string and **removes pieces from it in a fixed order**
(`commandline.parse`):

1. options (`-nlr`), from the letters `mnblqrsu`;
2. numeric parameters (`start=5`, `head=4z`, where a type letter gives units
   of that type's size);
3. word parameters (`file=`, `sym=`);
4. `order=`, which is new;
5. a check that no stray `=` is left;
6. symbols, which are expanded from a symbol table (`$PICKPATH`, then the
   bundled tables).

Whatever is left is an optional file name, the record size, and the field
requests (or a help request such as `?f`). Then `resolve()` works out the
details.

This explains several things users notice, such as parameters working
anywhere on the line. It also means the order of the steps is part of the
interface. For example, parameters are removed before symbols are expanded,
so a symbol that expands to `start=2` doesn't set a parameter. Instead, the
symbols named `head`, `size` and `length` set those parameters
specially. So the port keeps the Perl's order step for step, and doesn't
use argparse. **When a command line is a language, port the
parser, not the grammar you would design today.**

Symbol expansion is the one place where the Perl could loop forever: a
symbol defined in terms of itself never stops expanding. The port stops
after `MAX_SYMBOL_EXPANSIONS` (100,000) and reports an error.

### Field requests

`fields.py` has the request grammar, as regexes built from two alphabets:

- data types, `DTYPES = "SAbcswuidfzZ"`;
- print formats, `PFORMS = "udxnsgGoMPRIDbSAcU"`.

A request is `count type offset±delta :bit:nbits formats`, a move is `±N
type`, and a group is `N[ ... ]`. Groups are handled the way the Perl did:

- each innermost `[ ... ]` is replaced by a token `Y<n>`, which is expanded
  later;
- the group is found again by using its body as a regex, with `+` and `-`
  escaped.

That is odd, but it decides which malformed groups are accepted, so it was
kept. One case changed: when the substitution changes nothing, the Perl
went round the loop forever, and the port raises an error.

### Formats and byte order

`formats.render` turns one record into output. The interesting decision is
byte order.

pick was written on big-endian Sun and SGI machines. The Perl unpacked each
item in the machine's own byte order, and its byte formats (`x`, `o`, `b`,
`c`) showed bytes in memory order. On a big-endian machine, memory order
*is* value order, so `ux` on 0x03915ed3 printed `03 91 5e d3`. On today's
little-endian machines the same command printed `d3 5e 91 03`, and bit
fields picked the wrong byte. The tool's output depended on the machine it
ran on, and on the machines people now use, it was wrong.

The port separates two questions the Perl had tangled together:

- **How are the data stored?** That's `-r` or `order=big|little|native`.
- **How is a value shown?** Always as on a big-endian machine, in value
  order.

So `render` first puts each item into big-endian order. For complex types
it does this to each half separately, so the real and imaginary parts don't
swap; that was a second Perl bug. Then it prints the item the way the Perl
did on the machines it was written for. The output depends only on the
data and the command line.

The golden tests check this against the Perl. They can't run a Sun, so
`make_golden.py` emulates one: it runs a copy of the Perl in which the
unpack letters (`%tTypes`) are patched to be big-endian (section 8).

The rest of `render` keeps the Perl's details:

- the spacing: a space after most formats, and also after each byte for
  `x`/`o`/`d`/`u` on byte types;
- `G` as `%25.18g`;
- `D` using the Perl's value of π;
- `multiply` for the `D` conversion, so that `-0.0` degrees prints as `0`,
  as Perl's integer arithmetic gave;
- `sprintf` saturating `"1e400"` under `%d`.

### Input

`cli._Input` wraps the input. A file can seek anywhere. On stdin, pick can
only read forward, so a move backwards past what has been read is ignored,
as in the Perl.

### Help

`help.py` holds the help topics as text (`pick ?f`, `?x`, ...), corrected
where the Perl's help was wrong. The examples miscounted items (which count
from 0), and the awk example lost its `$1` because Perl interpolated it.
Help is checked by golden cases maintained by hand.

---

## 4. recs: a faithful buffer

recs extracts records from a stream by start and end markers (strings,
regexes or lengths). `extract.py` is a close port of the Perl's three
classes:

- `BStream`, a fixed-size buffer over the input that is refilled as it is
  consumed;
- `MatchStream`, string and regex search in that buffer;
- `Extractor`, the record logic: `match_n` (a marker plus a length) and
  `match_match` (start and end markers).

### Why keep the buffer mechanics?

A cleaner design would read the input into memory, or use a streaming regex
library. The port didn't do that, because **the buffer is visible in the
output**. The buffer advances by `size − mml` bytes, so consecutive buffers
overlap by `mml` (the maximum marker length) bytes. As a result, a marker
that straddles two buffers is found only if it is no longer than `mml`.
That's documented behavior, with an option to control it, and a different
buffer would find different records in some inputs. So `BStream._add_bytes`
reproduces even the Perl's `substr($data, $offset, $size - $offset)`
refill.

### The progress guard

Some inputs made the Perl loop forever, such as a marker that matches the
empty string, or a record length of 0. Recognizing every such case in
advance is hard, so the extractor checks for progress instead:

- `BStream.consumed` counts the net bytes taken from the front of the
  stream;
- if `MAX_STEPS_WITHOUT_PROGRESS` (10,000) steps pass without it growing,
  recs stops with an error.

**When a loop's termination is hard to prove, measure progress and give up
on its absence.**

### Python regexes

`-r` patterns are now Python regexes, compiled on bytes with `DOTALL`, as
Perl's `/s` did, and cached. A full Perl regex engine would have been a
large dependency for a small benefit. For the simple patterns recs is used
with, the two languages agree. The fuzz tests check that against the Perl,
on random data with a set of patterns of that kind.

---

## 5. recl: finding a period

recl estimates the record length of a binary file: given bytes, find the
period. It is the one tool where the port changed the algorithm.

### What the Perl did, and why it failed

For each candidate length R, the Perl XNORed the buffer with itself shifted
by R bytes, and meant to count the 1 bits:

```perl
my $r = ~("$b0" ^ "$ba");                    # NXOR
while ($i < $l - $a) { $f += vec($r, $i++, 1) }
```

`vec($r, $i, 1)` indexes **bits**, but the loop stops at the length in
**bytes**. So only the first eighth of each buffer was counted. Even with
that fixed, counting agreeing bits is a poor score:

- **Counters pull it toward multiples.** A counter's low bits agree more
  often at multiples of the record length than at the length itself.
- **Text gives false matches.** Bits agree often at small shifts in text.

On a file of 48-byte records, the Perl answered 3.

### Comparing bytes

`corr.agreement` scores a length R as **the fraction of bytes equal to the
byte R bytes further on**. For random data that is about 1/256. When
records are R bytes long it is higher, because records of one format share
bytes in the same places: sync words, flags, the high bytes of counters,
slowly varying values. With numpy this is one vectorized comparison per
length:

```python
(buffers[:, : size - r] == buffers[:, r:]).mean(axis=1)
```

That is why recl is now much faster as well as right. **A score with a known
baseline (1/256) is easier to interpret than one that drifts with the
data.**

### Choosing among multiples

Multiples of the record length score about as well as the length itself,
because the data repeat at those too. `corr.choose` therefore:

1. finds the best-scoring length;
2. takes a *typical* score as a baseline. That is the lower quartile, not
   the median, because with short records most candidates may be multiples
   and score high. With fewer than 5 candidates, the lowest score is used;
3. returns the **smallest divisor of the best length** that scores nearly as
   well. "Nearly as well" means within the larger of two margins: 25% of the
   best length's height above the baseline, or three combined standard
   errors from the counts of bytes compared;
4. also requires the divisor to score at least half that height above the
   baseline, so that a length with no structure of its own, such as 1, isn't
   chosen when the signal is weak.

Each rule came from a test file on which a simpler rule failed. The
close-the-loop tests (section 8) use random record lengths up to 700 bytes
with headers and partial last records, and they are what keep these rules
honest.

### `-bits`: periods that aren't whole bytes

PCM frames of 10- or 12-bit words needn't be a whole number of bytes:
25 words of 10 bits make a 250-bit frame. No whole-byte shift lines those
frames up. `bits.py` applies the same idea to bits:

- **Scoring:** score a length of L bits by how often the **8-bit window**
  starting at bit i equals the one at bit i + L. A window keeps the
  properties that made byte comparison work: a sync word still matches
  exactly, random windows match 1 time in 256, and counters don't pull the
  answer toward multiples.
- **Windows:** `windows()` computes the value of the `width` bits starting
  at every bit position, as uint64 shift-and-mask arithmetic over 8 bit
  offsets at once.
- **Proposals:** trying every length at every bit would be slow. A sync word
  makes the same 24-bit window appear once per frame, which random data
  rarely do, so the default candidates are:
  - the gaps between repeats of the 16 most common 24-bit windows;
  - their divisors.

  Then only those candidates are scored. **Let the data propose the
  candidates; score only those.**

### `-sync`: where records start

Given the length, `sync.py` lines the records up and looks for bit positions
that hold the same value in at least 85% of records (`CONSTANT`). The
records are lined up in one of two ways:

- **anchored** on the repeats of the most common once-per-record pattern,
  which copes with bit slips;
- **folded** into rows of one record each, if anchoring fails. Runs can then
  wrap around the end of the row.

It reports the longest run that contains both 0s and 1s (`MIN_BITS` = 8 or
more). Runs of all 0s or all 1s are usually padding, and are passed over
when a mixed run exists. The result is usually the sync word plus any
constant bits beside it. Those can't be told apart from the sync by looking
at the data, and the output says so.

The output also suggests the `realign`, `pick head=` and `recs` arguments
for the next step. **A diagnostic tool should end with the next command to
run.**

---

## 6. tgen: a language inside a config file

tgen generates synthetic telemetry from a command file. Each line defines an
item with five `#`-separated fields: name, offset, trigger, pack type and
value. Each field is code, evaluated for every record.

### Why the command files became Python

In the Perl, the fields were Perl code, and `r_eval` evaluated them. To make
one item refer to another, `r_eval` substituted the referenced field's
*source text* into the expression and evaluated the result, recursively.
Keeping Perl as the field language would have meant embedding a Perl
interpreter, or writing one. The choice was to make the fields Python,
which gives three things:

- tgen evaluates fields with Python's own compiler;
- users write a language they are more likely to know;
- **`tgen --convert`** translates existing Perl command files, so old files
  still work.

### Compiling a field: `_FieldCode`

A field may hold several statements, separated by semicolons, and its value
is that of the last one. `_FieldCode` uses `ast` to split the field:

- it parses the field as a module;
- if the last statement is an expression, that expression is the value;
- if it is an assignment (`x = 3`, `n += 1`), the value is the assignment
  target, read back;
- it compiles the rest to run first with `exec`, and the value with `eval`.

Each field is compiled once and run for every record in one shared
namespace, which is where state such as counters lives. An exception is
reported with the file, line, item and field. The Perl's `r_eval` returned
the field's source text when evaluation failed, which usually packed as 0,
so mistakes produced silent zeros.

### `F`, the fill byte

The fill value `F` must give a *new* random byte on every read when it's set
to a random fill, but a plain variable gives the same value each time. So
`_ReadFill`, an `ast.NodeTransformer`, rewrites every *load* of the name `F`
into a call, `_read_fill()`. Stores (`F = "ran"`) are left alone. **An AST
transform can give a variable the semantics of a function call without
changing the language users write.**

### `P.name.value`: matching the Perl's text substitution

Items refer to each other as `P.name.value` (the Perl's `$P{name}{value}`).
Because the Perl pasted values in as text, a float came back rounded to
Perl's 15 significant digits. `ItemValues._get` imitates that: it
round-trips each float through `perl_str`. Without it, chains of dependent
float items drift from the Perl's output in the last digit. `P.name._value`,
which is new, evaluates the field again rather than reading the stored
value.

### Random numbers: Perl's drand48

Seeded runs must match the Perl's, byte for byte, so the golden and fuzz
tests can include random items. Perl uses its own `drand48`:

- a 48-bit linear congruential generator, A = 0x5DEECE66D, C = 0xB, M = 2⁴⁸;
- seeded as `(seed << 16) + 0x330E`.

`Drand48` is that generator in six lines. `-seed=n` is new, and gives a
repeatable run without editing the command file.

### Perl's operators as functions

Python's `%`, `&`, `|`, `^`, `<<` and `>>` differ from Perl's. Perl's `%`
truncates both operands to integers first, and its bit operators work on
unsigned 64-bit integers. Command files rely on Perl's versions, so the
namespace provides helpers: `pmod`, `pand`, `por`, `pxor`, `pshl` and
`pshr`, plus `cat` for Perl's `.`. The translator uses them.

### The translator: `convert.py`

`--convert` mostly rewrites text with regexes, in stages:

- `$::x` and `$P{a}{b}` become names and attribute access;
- interpolated strings become Python strings;
- `map` over ranges becomes a comprehension;
- `++` and statement modifiers (`x if y`) are rewritten;
- `print` is translated.

Regexes can't rewrite operators safely, though: `a % b + c` must become
`pmod(a, b) + c`, and that needs the parse tree. So `_integer_ops` parses
the code (by now mostly Python), finds each integer `BinOp`, and **splices
replacements into the original text**:

- it uses each node's `col_offset` and `end_col_offset` span;
- it works from the end of the text toward the start, so that earlier
  offsets stay valid as later spans are replaced.

Everything outside those spans keeps the user's own spelling, spacing and
parentheses, which `ast.unparse` would have normalized away.

Anything still Perl-looking afterwards gets a `# TODO(convert)` line above
it. Running a file with leftover Perl then fails loudly instead of quietly
computing something else. **A translator should be honest about what it
didn't translate.**

---

## 7. realign: frames at any bit

realign is new. Raw bit streams from a bit synchronizer have frames that
start at any bit, not on byte boundaries, so pick can't read them directly.
realign cuts the stream into frames and writes each frame on byte
boundaries (`frames.py`):

- **`fixed()`:** frames of L bits from a given offset. The bits are reshaped
  into rows of L.
- **`search()`:** finds each frame by its sync pattern, which copes with the
  bit slips of real serial links. It reuses `recl.bits.windows`. Patterns
  can be up to 56 bits (`MAX_SYNC_BITS`), and near matches are counted with
  a popcount table. `-errors` sets how many bits may differ, and `-slip`
  how far to look for the next frame (8 bits by default).
- **`pack_frames()`:** writes each frame as ceil(L/8) bytes with
  `np.packbits`. The padding goes after the frame's bits, or before them
  with `-left`.

`-lsb` reads the *input* least significant bit first. The output is always
written most significant bit first, which is what pick expects. realign was
designed to follow `recl -sync`: `-sync` prints the realign command to run,
and realign's output is ready for pick.

---

## 8. Testing

There are about 3,500 tests, and the coverage gate fails below 95% of
branches. They are layered so that each kind catches what the others
miss.

### Golden cases

Each tool has a `tests/golden/<tool>/` directory:

- `cases.toml` holds cases written by hand;
- an optional `cases.py` generates more, for example pick's matrix of types
  × formats × byte orders;
- `tools/make_golden.py` runs the Perl on every case and writes the stdout
  bytes (`<id>.out`), plus the exit status and stderr (`index.json`).

The cases number about 1,750 for pick, 700 for recs, 100 for recl and 85 for
tgen. The tests then run the Python on each case and compare the bytes.

The keys in `tests/golden_cases.py` encode the rules from section 2:

| key | meaning |
|---|---|
| `fix` | the Python deliberately differs here; the value names the CHANGELOG entry |
| `mirror` | expected output = the Python output of another case (a fix's reference) |
| `perl_args` / `perl_sub` | run the Perl differently to get the intended output (`zRI` for the documented meaning of `zg`) |
| `host = "big"` | emulate a big-endian machine: run a copy of the Perl with big-endian unpack letters |
| `oracle = "big-host-r"` | the intended little-endian output is the big-host Perl run with `-r` toggled |
| `error` | the Perl exited 0 but the Python must fail with this message |

The big-host emulation works like this:

- `make_golden.big_host_pick` patches `%tTypes` in a temporary copy of the
  Perl;
- the Python runs the same case with `host_order="big"`;
- both sides then see the same machine.

This is how the byte-order fix is tested against the *Perl's* intended
behavior, not the Python's.

`make_golden.py --check` is run in CI to make sure the stored outputs are
current. Case ids must differ when case is ignored, because macOS disks are
case-insensitive. Generated ids therefore write an uppercase X as `+x`.

### Differential fuzzing

The Hypothesis tests (`test_*_fuzz.py`, marked `oracle`) generate random
command lines and data, run both the Perl and the Python, and compare the
results:

- for **pick**, random requests over random records;
- for **recs**, random markers, lengths and options;
- for **tgen**, random Perl command files. The test converts each file with
  `--convert`, runs it with the Python generator, and compares the bytes
  with the Perl's output, which tests the translator and the runtime
  together.

Profiles set the depth: `ci` runs 150 examples and `deep` runs 5,000
(`HYPOTHESIS_PROFILE=deep`). Fuzzing found Perl behaviors no one would have
written a case for (section 10).

### Close the loop

recl's answers can't be checked against the Perl, which was wrong, so
`test_pipelines.py` uses tgen instead. tgen generates data whose structure
is known: frames of 7, 37, 256 and 1,000 bytes, random lengths, headers,
the AIRSAR subcommutated header, and PCM bit frames. Then recs, recl and
pick must recover that structure. **When there is no oracle, generate data
whose answer you know.**

### Docs as tests

`test_docs.py` runs every ```` ```console ```` block in the README and in
`docs/`. Each `$ command` line runs in bash in a temporary directory, and
its output must match the lines that follow it. A `<!-- file: NAME -->`
comment before a code block writes that block to a file first, which is how
the manuals carry their tgen command files. So every example in the manuals
works. This guide avoids console blocks, because its examples illustrate
rather than demonstrate.

### CI and release

- CI runs ruff, the tests on Python 3.10–3.13 with the coverage gate, and
  `make_golden --check`.
- `release.yml` publishes from a tag:
  - the tag must equal the package version;
  - it builds the package and runs `twine check`;
  - it publishes to TestPyPI, then to PyPI through an environment that
    needs approval, using trusted publishing (no stored tokens).

---

## 9. Changes from the Perl, and why

Every deliberate difference from the Perl is listed here. "Kind" is one of:

- **fix**: the Perl contradicted its documentation, or failed;
- **portability**: the behavior depended on the machine;
- **safety**: a silent failure or endless loop became an error;
- **new**: a capability the Perl didn't have;
- **dialect**: a change of language.

### Across all tools

| Perl | Python | kind | why |
|---|---|---|---|
| Errors and warnings went to stdout, mixed into the data, often with exit status 0 | stderr, with a nonzero exit status | safety | stdout is data in a pipeline; a script must be able to detect failure |
| Bad options were warned about and ignored (Getopt::Long) | an error, exit 2 | safety | ignoring `-mmll 4` silently gives wrong output |
| Broken pipe killed the tool, or printed an error | exits 0 quietly | fix | `tool \| head` is normal use |
| Four scripts, installed by hand | one package (`pipx install telemetry-cli`), five commands, tested on 3.10–3.13 | new | installation and maintenance |

### pick

| Perl | Python | kind | why |
|---|---|---|---|
| Items unpacked in the machine's byte order; byte formats and bit fields wrong on little-endian machines | values shown as on a big-endian machine; `-r` or `order=` say how the data are stored | portability | output should depend on the data, not the computer; big-endian behavior was the intent |
| `-r` on complex types reversed all 8 or 16 bytes, swapping the real and imaginary parts | each half reversed separately | fix | a complex number is two numbers |
| `g` on complex types was rejected | prints the real and imaginary parts, as documented (`RI`) | fix | the documentation said so |
| `-l` printed the record number and `-n` the line number | swapped back to match the documentation | fix | the documentation said so |
| "Matched neither a move nor a data request" on stdout, exit 0; help dumped before errors | the error on stderr, exit 1, with a help-topic hint | safety | |
| `file=` that couldn't be opened was ignored | an error | safety | |
| `every=0`, record size 0, a self-referential symbol, some malformed groups: endless loops | errors (expansions capped at 100,000) | safety | |
| `U` on bit fields wrote the wrong end of the masked value | the masked value's bytes | fix | |
| Help: `'x' octal`; awk example lost `$1`, `$2`; examples miscounted items (which count from 0); group example off by three floats; nested-group example read before the record | corrected | fix | the help is documentation |
| — | `order=big\|little\|native` | new | saying how the data are stored, rather than reversing it |
| — | `pick --help topic` | new | zsh treats an unquoted `?p` as a filename pattern |
| Symbol tables were separate files | bundled; `sym=moc` finds them | new | they were part of the distribution |
| Spacing, `G` width, π, the type deciding the sign, `c` read as unsigned, parse order | **kept**, and documented under Quirks | — | users' scripts depend on them |

### recs

| Perl | Python | kind | why |
|---|---|---|---|
| Padded with the character `0` | null bytes, as documented | fix | |
| Warnings to stdout, between records, with Perl line numbers | stderr | safety | they corrupted the extracted data |
| Missing marker or non-numeric length: wrote nothing, exit 0 | an error | safety | |
| Empty fill string, markers that consume nothing: endless loops | errors (the progress guard) | safety | |
| Perl regexes | Python regexes (bytes, `DOTALL`) | dialect | no Perl regex engine in Python; they agree on recs' patterns |
| `-test` ran built-in tests | says the tests moved to the suite | — | |
| The buffer mechanics (`mml`) | **kept** | — | they decide which straddling markers are found |

### recl

| Perl | Python | kind | why |
|---|---|---|---|
| Counted agreeing bits in the first 1/8 of each buffer (`vec` over bits, bounded by bytes); answered 3 for 48-byte records | fraction of equal bytes over the whole buffer; smallest qualifying divisor of the best length | fix | the measurement didn't work; bytes have a known baseline and aren't pulled to multiples |
| `CORR` ≈ 50 for random data (percent of bits) | ≈ 0.4 (percent of bytes) | fix | follows from the new score |
| `-full`, `-limit`, `-reduce` accepted but ignored | they work | fix | |
| `-only` sized buffers from the last length listed | from the longest | fix | longer lengths were never scored |
| `-verbose` table labeled fractions as percentages | correct labels | fix | |
| stdin needed `-max`, which was taken as the file size | stdin works like a file | fix | |
| Short data divided by zero; `-min` > `-max` looped forever | one piece; an error | safety | |
| Slow (a bit loop in Perl) | numpy, vectorized | — | |
| — | `-bits`, `-lsb`, `-sync` | new | PCM frames that aren't whole bytes; finding where records start |

### tgen

| Perl | Python | kind | why |
|---|---|---|---|
| Fields were Perl, evaluated by recursive text substitution (`r_eval`) | fields are Python, compiled once with `ast` | dialect | no Perl interpreter needed; a better-known language |
| — | `tgen --convert` translates Perl command files, marking leftovers `# TODO(convert)` | new | old files still work |
| A field that failed to evaluate silently became its own source text (usually packed as 0) | an error with the file, line, item and field | safety | silent zeros in generated data are hard to notice |
| Files reopened for every frame | opened once | fix | speed |
| Bad option warned about | an error | safety | |
| — | `-seed=n`; `P.name._value`; `B`/`b` pack types and `bitstring()` | new | repeatable runs; re-evaluation; bit streams for `recl -bits` |
| drand48 random numbers, 15-digit text values of `$P{}{}` | **kept** (`Drand48`, `perl_str`) | — | seeded output matches the Perl byte for byte |

---

## 10. Lessons from the bugs

Some of these are bugs the tests found. Others are traps that the port had
to design around. Most are behaviors of the *Perl* that no one had written
down.

- **Overflowing numeric strings.** Perl's `%d` on the string `"1e400"`
  prints the largest 64-bit integer, not "Inf". Hypothesis found this on
  CI. `_perl.sprintf` now saturates. *A fuzz test against an oracle finds
  the behaviors you didn't know to ask about.*
- **Negative zero.** In the `D` format, `-0.0 × 180/π` prints `0` in Perl,
  which multiplies integer-valued numbers as integers, but `-0` in Python.
  That's why `_perl.multiply` exists. *Two languages can agree on
  every operation and still differ on the value of a float's sign.*
- **The order errors are reported in.** With both a bad field and a record
  size of 0, the Perl reports the field error. The port at first checked the
  size first, so the check moved after field parsing. *When matching error messages,
  the order of checks is part of the interface.*
- **Text substitution leaks precision.** tgen's `$P{x}{value}` went through
  Perl's 15-digit printing on every reference. A faithful port has to
  imitate the loss as well as the arithmetic: `ItemValues._get`.
- **Case-insensitive file systems.** Two golden cases whose ids differ only
  in case would overwrite each other's `.out` file on macOS. So ids are
  checked to be unique ignoring case, and generated ids spell uppercase X
  as `+x`. *Test data on disk is subject to the disk's rules.*
- **A port can preserve a bug's cause but not its symptom.** recl's `vec`
  bug looked like weak results, not like a bug. It was found only when the
  close-the-loop tests demanded the right answer on files of known
  structure. *For a tool that measures something, test it on inputs where
  the answer is known.*

---

## 11. Exercises

1. **Trace a command line.** Take
   `pick data.bin 36 -q order=big start=2 sym=moc '3[ bd 3[ w bd ] bn +1 ]'`
   and write down the string after each step of `commandline.parse`. Which
   step would break if symbols were expanded before parameters were
   removed?
2. **Byte order by hand.** For the four bytes `03 91 5e d3` stored
   little-endian, predict pick's output for `u`, `ux`, `u:0:8d` and `uU` on
   a little-endian host. Check with pick, then find the lines in
   `formats.render` responsible.
3. **Break the straddle.** Make a file in which a 6-byte start marker
   straddles recs' buffer boundary. Show that recs finds it with
   `-mml 6` and misses it with `-mml 4`. Why can't a larger `mml` simply be
   the default?
4. **A weak signal.** Generate records of length 40 with tgen whose only
   structure is a 2-byte counter. Run `recl -verbose` and explain each step
   of `choose()` on the table. What happens if the baseline is the median
   instead of the lower quartile?
5. **A new pack letter.** Add `j` (Perl's signed IV) to `_pack.py`, with a
   golden tgen case generated from the Perl. Where must the CHANGELOG entry
   go?
6. **Teach the converter.** Find a Perl construct `--convert` marks as
   `TODO(convert)`, such as the ternary `?:`. Translate it, and add a fuzz
   strategy that generates it, so the Perl checks your translation.
7. **Slips.** Use tgen to make a PCM stream of 250-bit frames, delete one bit
   in the middle, and run `recl -bits -sync` and `realign`. How many frames
   are lost at the slip, and which option controls it?
8. **An opt-in feature.** Issue #24 asks for plotting-friendly pick output.
   Design the option so that no existing golden case changes. Which section
   2 rule makes that a requirement?

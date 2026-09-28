# recs

Extract records from a stream of data, using the markers that start (and
optionally end) each record.

```text
recs filename [ options ] record_start_match [ reclen_bytes ]
cat filename | recs - [ options ] record_start_match [ reclen_bytes ]
```

Telemetry often arrives as a stream in which each record begins with a sync
pattern, and whatever lies between records is noise. recs finds the markers
and writes the records out, back to back, ready for fixed-length tools such
as [pick](pick.md). It reads a file, or stdin when the file name is `-`.

## Three ways to find records

The examples use this small stream:

```console
$ printf 'noise<rec>one</rec>junk<rec>two</rec><rec>three</rec>tail' > stream.txt
```

**From each start marker to the next** (give only the start marker). The last
record isn't written, because no start marker follows it. `-nl` puts each
record on its own line here:

```console
$ recs stream.txt -nl '<rec>'
<rec>one</rec>junk
<rec>two</rec>
```

**From a start marker to an end marker** (`-e`). `-x` and `-z` leave the
markers out:

```console
$ recs stream.txt -nl -e '</rec>' '<rec>'
<rec>one</rec>
<rec>two</rec>
<rec>three</rec>
$ recs stream.txt -nl -x -z -e '</rec>' '<rec>'
one
two
three
```

**A fixed number of bytes from each start marker** (give the length):

```console
$ recs stream.txt -nl '<rec>' 8
<rec>one
<rec>two
<rec>thr
$ recs stream.txt -nl -x '<rec>' 3
one
two
thr
```

With `-r`, markers are regular expressions:

```console
$ recs stream.txt -nl -r '<[a-z]+>' 6
<rec>o
<rec>t
<rec>t
```

## Options

Options can go anywhere on the command line, can be abbreviated to any unique
prefix (`-max` for `-max_reclen`), and take their values after `=` or as the
next argument. Put `--` before a marker that starts with a dash.

| Option | Meaning |
|---|---|
| `-e string` | the end-of-record marker |
| `-r` | markers are regular expressions (Python syntax; `.` matches newlines too) |
| `-x` | leave the start marker out of each record |
| `-z` | leave the end marker out of each record |
| `-a` | start a new record at every start marker, even if the current one isn't complete yet; a short record is padded |
| `-min_reclen=n` | pad shorter records to n bytes |
| `-max_reclen=n` | truncate longer records to n bytes |
| `-f string` | the fill for padding (default: a null byte) |
| `-prepend string` | write this before each record |
| `-append string` | write this after each record |
| `-nl` | write a newline after each record (after the `-append` string) |
| `-mml=n` | the longest match expected (see below) |
| `-help` | show help |

```console
$ recs stream.txt -nl -x -z -e '</rec>' -min_reclen=6 -f . '<rec>'
one...
two...
three.
$ recs stream.txt -x -z -e '</rec>' -prepend '[' -append ']' -nl '<rec>'
[one]
[two]
[three]
$ cat stream.txt | recs - -nl -x -z -e '</rec>' '<rec>'
one
two
three
```

## Markers that straddle buffers

recs reads its input in buffers (at least 1024 bytes, and at least twice the
record length plus `-mml`), and keeps the last `-mml` bytes of each buffer to
look for a marker that starts there and ends in the next one. `-mml` is the
length of the longest marker, which recs takes to be the length of the marker
string. That's right for plain strings, but not for a regex like `\d+`, so
give `-mml` for regexes that can match more than their own length. recs warns
(on stderr) when it finds a longer match than `-mml` allows for.

## Differences from the Perl version

recs was written in Perl; its history in `legacy/recs` starts in 2012. The
Python version has the same command line and output, except for these fixes
(see the [CHANGELOG](../CHANGELOG.md)):

- Padding uses null bytes by default, as documented. The Perl padded with the
  character `0`.
- Warnings go to stderr. The Perl wrote them to stdout, in the middle of the
  records.
- A bad option, a missing argument, or a record length that isn't a number is
  an error. The Perl warned and carried on, or quietly wrote nothing.
- Inputs that made the Perl loop forever are errors: an empty fill string
  when padding is needed, and markers that match without consuming anything
  (such as a record length of 0 without `-x`).
- Regexes are Python's, not Perl's. The two agree on the patterns recs is
  typically used with.
- The `-test` option ran the Perl script's built-in tests. They are now part
  of telemetry-cli's test suite.

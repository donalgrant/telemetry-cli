"""pick's built-in help (``pick ?``, ``pick ?p``, ...).

The text is the Perl original's, with corrections noted in the CHANGELOG.
"""

from __future__ import annotations

from .. import __version__

USAGE = """
pick Usage:

   pick filename recordLength -options parameters fields
   cat datafile | pick recordLength -options parameters fields

The filename must be the first command line argument if specified.
The record length (bytes, or specify data type units) must be the
next command line argument.  See ?p for alternatives.

Detailed Help available:
       'pick ?p' for help on parameters
       'pick ?r' for help on field requests
       'pick ?f' for help on printFormatLists
       'pick ?t' for help on data types
       'pick ?m' for help on move requests
       'pick ?o' for help on options
       'pick ?g' for help on groupings and multiplers
       'pick ?x' for some examples
       'pick ?q' for help on symbol files
       'pick ?v' for version and author
       'pick ??' for all help available
(Pipe the output to more, i.e., 'pick ?? | more' for readability.)

In zsh, quote the question mark ('pick "?p"'), or use 'pick --help p'.
The full manual is at
   https://github.com/donalgrant/telemetry-cli/blob/main/docs/pick.md

"""

PARAMETERS = """

The parameters are of the form:
   key1 = val1 key2 = val2 ...

The available parameter keywords are listed below.
The value is a number of records for the start, stop,
skip, nrecs, rec and every keys, a number of bytes
or data type words (see data type help) for the head,
length and size keys.  The file key takes an ascii filename.

file:   alternative way to specify filename.
        (filename is a synonym for file)
size:   alternative way to specify recordLength.
        (length is a synonym)

start:  First record to extract (zero offset), default 0
stop:   Last record to extract, default is '-1', indicating EOF.
skip:   Number of records to skip between each extract.
        (default is zero; extract every record)
head:   Number of bytes or data words to skip before
        counting records.  E.g., head=256 ignores a
        256-byte header, head=4z ignores a header of
        four single-precision complexes.  (32 bytes)

rec:    Extract a single record (same as start=stop=rec)
nrecs:  Use instead of specifying both start and stop;
        determines number of records to extract.  I.e,
        start=0 nrecs=11 is the same as start=0, stop=10
every:  Use instead of skip; every=10 gets every 10th record.
        (i.e., same as skip=9)

order:  Byte order of the data: big, little, or native (the
        default, this machine's order).  The -r option
        reverses whichever order is in effect.

"""

OPTIONS = """

The options are of the form -opt1opt2... or -opt1 -opt2:

l:  print a line number for every output line.
n:  print a record number for every output line.
m:  print the byte location in the file for every output line.
r:  reverse the order of the bytes.
u:  all output is in binary format only; ignore print requests
b:  fast version of 'u' option:  no bit masking or byte reversal
q:  quiet output; turn off diagnostic messages, which are sent to STDERR
s:  suppress c/r after printing for each record

For example,
              'pick file.dat 20f -nlr ...'
would print each line with the line number, then
  the record number, followed by whatever data were
  requested in the command line (represented by '...').
  These data would be interpreted in reverse byte order
  before printing.

"""

FIELDS = """

There are two kinds of field requests: moves and prints.
  A print request will also move the current location in
  the record.  A move request generates no output.

Type 'pick ?m' for help on move requests.

A print request has the format:

N'type'Offset:bitOffset:nBits'printFormatList'

and must be separated by spaces from every other
command line argument.  The components are defined as:

N: Number of sequential fields of this data type
   to extract and print.  N is optional, with a
   default value of 1.  It must not have a sign
   prefixed ('+' or '-').

type:  The data type of the fields to extract and print.
       Type 'pick ?t' for information on data types.

Offset:  The 'Offset' has the form:
              dataOffset(+|-)byteOffset
         where dataOffset is the absolute location
         of this item in the record in numbers of items
         of type 'type', and the byteOffset is the
         the desired offset in bytes from this location.
         'Offset' is an optional parameter, if not
         specified, the next item in the record will be
         selected.  The 'byteOffset' is an optional
         component of the 'Offset'.  However, if it
         is used, then the 'dataOffset' must also be
         specified, even if '0'.  The sign must be
         included as part of the byteOffset.
         For example, the field
                     z60-2
         selects the 61st single-precision complex item (z0 is the first),
         offset towards the beginning of the record by
         two bytes.  A common convenient way to specify
         an absolute byte location within a record is to
         specify the dataOffset as zero with a positive
         byte offset.  For example, the request above
         could also be written:
                     z0+478
         which selects the complex number at an offset
         of 478 bytes from the beginning of the record.
         The counting for byte and data offsets, as with
         all other counting in pick, is zero-offset.

bitOffset:  (Not available for data types with more than 4 bytes.)
            An optional field which specifies the first
            bit of the data field to use.  'bitOffset'
            is zero offset.  For example, the field
                          i:7
            selects the next integer, and only uses
            the eighth through 32nd bits (7--31)
            for printing.  Bit zero is the LSB.

nBits:  (Not available for data types with more than 4 bytes.)
        If a 'bitOffset' is specified, 'nBits' may
        be used to to select the number of bits,
        starting from the 'bitOffset', to be printed.
        For example, the field
                        w5:1:7
        selects the second through eighth bits (1-7)
        of the sixth unsigned short in the record (w0 is the first).

printFormatList:  Zero or more print formats used to
                  specify the format of the output for
                  this field request.
                  Type 'pick ?f' for detailed help.

"""

FORMATS = """

  printFormatList:  The printing formats available are:

          Available to all Data Types:
          'x' hex               'o' octal
          'b' binary            'c' ascii

          'S' ascii, with no space between items.
          'A' ascii, won't print non-printing characters.

          'U' unformatted (binary bytes) output

          Available to Integral Data Types Only:
          'd' decimal           'u' unsigned decimal

          Available to Floating Data Types Only:
          'g' floating  (For complex types, equivalent to RI format.)
          'G' same as 'g', but with lots of digits.
          'D' degrees; assumes the data value is in
              radians, and performs the conversion to
              output degrees.

          Available to Complex Data Types Only:
          'R' real component    'I' imaginary component
          'M' magnitude         'P' phase in radians
                                'D' phase in degrees

          Non-data print formats for all types:
          'n' insert CR/LF      's' insert <sp>

          A 'printFormatList' is composed of zero or more
          printing formats, as many as desired, in any order,
          repeats allowed.  Each is printed in turn: 'uxox'
          prints an unsigned int in hex, then octal, then hex
          again.  With a count, each item is printed in all
          the formats before the next item.
          If none is specified, the defaults will be used:
             Data Type       Default Printformat
                A                    A
                S                    S
                c                    c
                b                    x
                s                    d
                w                    u
                i                    d
                u                    u
                f                    g
                d                    g
                z                    RI
                Z                    RI

          For example:
              f wb zMPn i0+57osss Z b5:1:7bdx
          Prints a single precision floating point in 'g'
          format, an unsigned short in binary, a single-
          precision complex's magnitude and phase followed
          by a newline, the integer at byte offset 57 in
          octal followed by three extra spaces, a
          double-precision complex's real and imaginary
          component, and bits 1-7 of the sixth unsigned
          char interpreted first as binary, then decimal
          and finally hexadecimal.

"""

MOVES = """

  A move request has the format:
    (+|-)N'type'
  where the '+' or '-' specifies the move direction,
    N is the number of data words to move (bytes if no
    'type' identifier is specified).  See below for 'type'
    specifiers.
  Examples:  +2 -237 +5z -3i
    these move the current location in the record by
    forward 2 bytes, back 237 bytes, forward 40 bytes
    and back 12 bytes, respectively.

"""

TYPES = """

         The following data types are supported by pick:
         (Sizes in bytes are listed in brackets.)

         Integral Data Types:
          'c' [1] signed char;     'b' [1] unsigned char
          's' [2] signed short;    'w' [2] unsigned short
          'i' [4] signed int;      'u' [4] unsigned int

         whether or not an integral data type is signed only
         really matters to the default output printformat.
         The printformat used determines whether the data are
         interpreted as signed or unsigned.

          'S' [1] is a synonym for 'c', but uses
                  the 'S' printFormat as default.
          'A' [1] is a synonym for 'c', but uses
                  the 'A' printFormat as default.

         Floating Types:
          'f' [4] single float;    'd' [8] double float
          'z' [8] float complex;   'Z' [16] double complex

"""

GROUPS = """

  Groups and group multipliers:

  Any number of fields may be enclosed in brackets
  to form a group.  For example:
           [ 4f i ]
  requests a group of four floats followed by an integer.

  In order to avoid being interpreted by the shell, one
  may need to escape the '[]'s with a backslash '\\' or by
  enclosing the string within single quotes:
           '[ 4f i ]'
  This is a syntax quite like the Unix awk command line.

  A numerical prefix to the group designates a repetition
  factor for the group.  For example:
           20[ f +99f i -100f ]
  requests 20 pairs of floats and integers, where each
  integer starts 400 bytes after its float, but
  the floats and the integers themselves are sequential.
  There must be no space between the prefix and the opening
  bracket.
"""

SYMBOLS = """

  pick Symbol Files:

  As a convenience for dealing with standard file formats,
  such as the ifproc mocomp file, the AIRSAR mocomp file,
  SRTM telemetry, AIRSAR headers and subcommutated headers,
  TOPEX/Poseidon SDR's and GDR's, GeoSAR time-dependent parameter
  files, etc, one may define a symbol file as a set of
  (possibly recursive) key = value definitions mapping more
  easily remembered mnemonics onto admittedly less-obvious pick
  commands.  For example, to define the ifproc mocomp symbol file,
  the following file is created:

; This is the symbol table for .moc files, which
; are the radar motion compensation files for section 334.

length=21d  ; length is 21 double-precision (8 byte) numbers

; these are the components of the file

xRec = d0G
xrec = d0G
time = d1G
utc = d1G
prf = d2 ; actually 1/prf...
tprf = d2
posS = d3
posC = d4
posH = d5
pos = posS posC posH
velS = d6
velC = d7
velH = d8
vel = velS velC velH
af1S = d9
af1C = d10
af1H = d11
af1 = 3d9
af2 = 3d12
af3 = 3d15
az = d18
yaw = d18
pitch = d19
roll = d20
orient = 3d18
azD = d18D
yawD = d18D
pitchd = d19D
rollD = d20D
orientD = 3d18D
all = 21d0
af = af1 af2 af3
angles = posS orientD
velocities = posS vel
tube = pos


  Note that the file is very similar to RDF (though pre-dating
  it by a couple of years), with comment fields delimited by
  semi-colons.  However, the values are interpreted recursively:
  the 'af' key's value, 'af1 af2 af3' is defined elsewhere in the
  file.

  Note also that the symbols 'length', 'size' and 'head' are reserved
  for pick; in a symbol file they do not define new symbols
  but rather serve as parameter definitions.  For example, in
  this mocomp file, the record length is set at the beginning of
  the file to be 21 doubles long.

  If this file is in the present-working directory, named 'moc',
  and a mocomp file named test.moc is available, then one could
  use commands like:

        pick sym=moc test.moc velocities every=100

  to print out the velocities as a function of along-track position
  for every hundredth entry in the file.  A nice shortcut is to
  use an environmental variable, recognized by pick:  PICKPATH,
  to specify a folder of such symbol files.  If the filename specified
  by the sym parameter isn't in the present-working directory, then
  pick will search the folder specified by PICKPATH.  For example,
  add the lines to the .zshenv file:

        export PICKPATH=/users/imel/.pick
        alias pickMocomp='pick sym=moc'

  and put a copy of the moc file listed above in that folder.
  Now, the above command is:

        pickMocomp test.moc velocities skip=100 | feedgnuplot --domain --lines

  where we've piped the output to feedgnuplot, a command-line front
  end to gnuplot, for display: the first column is x, and each of the
  others is a curve.  (xmgr, which this example used to use, lives on
  as Grace, whose xmgrace reads the same columns with -nxy; see its
  -pipe option for reading stdin.)

"""

EXAMPLES = """

  Example Field Requests:

  4d0+30 2z 5i

  Extract, starting at byte 30 in the record, four
  double-precision floats, print in floating point format,
  two single-precision complex's, print real followed
  by imaginary components for each, and five 4-byte
  signed integers, printing in signed decimal format.

  6[ f i ]

  From the present position in the record,
  extract a series of 6 4-byte float and
  4-byte integer pairs, printing the
  floats in floating point format and the
  integers in signed decimal format.

  Z20 +1280Z ZMP

  Extract the twenty-first double-precision complex
  in the record, print in floating point format
  (real <sp> imaginary), move forward 1280 double
  precision complexes (1280*16 bytes) and extract
  another double precision complex, printing the
  magnitude followed by the phase in radians.

  20[ f 3[ wx cb ] +1000 i:27d -1091 ]

  Extract a 4-byte float (print in floating point),
  3 unsigned short-signed char pairs, printing the
  short in hex and the char in binary, move forward
  1000 bytes, extract a four-byte signed integer,
  printing only the 5 most significant bits
  in decimal format, and move back 1091 bytes.
  Repeat this operation 20 times for each record.
  (Each repetition moves back 74 bytes overall, so from
  the second one on, reads start before the beginning of
  the record, and come from the end of the record.)

  Note that for moves, the current position in the record
  is the location after the most recent request.  For example,
  in the above, the +1000 byte move is referenced from the
  position after the third short/byte pair.

  Complete Examples

  pick file1.dat 256 20c100c rec=1

  Prints twenty characters in ascii format starting
  at byte 100 for the second (256-byte) record only
  in file1.dat.

  pick file2.dat 5120f 10f500 head=5i start=500

  Prints in floating point format ten consecutive
  single-precision floats starting at the 501st
  float in the record, for every record starting
  with record number 500 (the 501'st 5120*4=20480 byte
  record in file2.dat). The record count begins after a
  5 integer (20 byte) header.

  pick file3.dat 80 40[ cc +1 ] skip=1

  Prints every other character in each record
  (ascii format), skipping every other record.
  (The first character in the file is printed.)

  pick gold225-1.laux 128 +90 32b -b \\
     start=`pick gold225-1.laux 128 +88 w -n \\
     | awk '{ if ($2==0) { print $1 ; exit;}}'` \\
  | pick 4096 +439 50A

  This command line actually launches three pick processes
  in order to extract a field from an AIRSAR subcommutated
  header.  The first 'pick' command extracts the subcommutated
  header, starting with the record specified by the result
  of the second pick command, which extracts the index field
  from the header.  When the index field reaches zero, a new
  subcommutated header begins.  So the output of the second
  pick command is sent to awk to look for the record corresponding
  to an index value of zero.  The output of the first pick command
  is now a set of subcommutated headers (in their original binary
  format) which is piped to the third pick command, which selects
  the desired field:  50 Ascii characters starting at an offset
  from the beginning of the record by 439 bytes.

"""


def version() -> str:
    return f"""
This is pick (Python), from telemetry-cli {__version__}.
It is a port of pick (perl) Revision 3.6, 4 October 2012.

Written by David A. Imel.
Please report problems at:
          https://github.com/donalgrant/telemetry-cli/issues

"""


ALL = [OPTIONS, PARAMETERS, FIELDS, TYPES, FORMATS, MOVES, GROUPS, SYMBOLS, EXAMPLES]

# (pattern test, texts) in the order the Perl original checked them
TOPICS = {"r": FIELDS, "t": TYPES, "p": PARAMETERS, "m": MOVES, "o": OPTIONS}
TOPICS |= {"f": FORMATS, "x": EXAMPLES, "g": GROUPS, "q": SYMBOLS}


def help_text(text: str, symbols: dict[str, str] | None = None, symbol_file: str = "") -> str:
    """The help pick prints for a command line ``text`` that asked for help.

    As in the Perl, every topic whose marker appears is printed, in a fixed order.
    """
    out = []
    if not text or text in ("0",) or "help" in text or "-h" in text or "?h" in text:
        out.append(USAGE)
    if "??" in text:
        out += ALL
        out.append(version())
    if text.endswith("?"):
        out.append(USAGE)
    for letter in "rtpmof":
        if "?" + letter in text:
            out.append(TOPICS[letter])
    if "?v" in text:
        out.append(version())
    for letter in "xgq":
        if "?" + letter in text:
            out.append(TOPICS[letter])
    if symbols is not None:
        out.append(f"Symbols defined in {symbol_file}:\n")
        out += [f"{k}={symbols[k]}\n" for k in sorted(symbols)]
    return "".join(out)

"""The tools together, as shell pipelines: close-the-loop tests.

1. tgen writes a stream of frames separated by junk; recs extracts the frames
   by their sync word; recl finds their length; pick decodes them. Every
   decoded field must be what the tgen command file says.
2. tgen writes a header, and frames that carry it 16 bytes at a time (a
   subcommutated header); pick finds where a header starts, extracts the
   pieces, and decodes the reassembled header, as in pick's AIRSAR example.

These run the installed commands, like a user would.
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(sys.executable).parent


def sh(command: str, cwd: Path) -> str:
    env = {**os.environ, "PATH": f"{BIN}{os.pathsep}{os.environ['PATH']}"}
    env.pop("PICKPATH", None)
    p = subprocess.run(
        ["bash", "-c", "set -eo pipefail; " + command],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )
    assert p.returncode == 0, f"$ {command}\n{p.stderr.decode()}"
    return p.stdout.decode("latin-1")


# --- 1. tgen -> recs -> recl -> pick ---------------------------------------------------

STREAM = """\
# 20-byte frames, each followed by {gap} bytes of fill
sync   # 0  # 1 # 'N'  # 0x1ACFFC1D
count  # 4  # 1 # 'N'  # I
temp   # 8  # 1 # 'f>' # 20.0 + I / 8
status # 12 # 1 # 'n'  # pmod(I, 16) << 12 | 0x042
name   # 14 # 1 # 'a6' # f"R{{I:05d}}"
gap    # {gap_offset} # 1 # 'C' # F
"""
SYNC = "$(printf '\\x1a\\xcf\\xfc\\x1d')"


def expected_frame(i: int) -> str:
    """What pick should print for frame i: the tgen file's values."""
    temp = 20.0 + i / 8
    return (
        f"{i} 449838109 {' '.join(f'{b:02x}' for b in struct.pack('>I', i))}  "
        f"{temp:g} {i % 16} 00 42  R{i:05d}"
    )


@pytest.mark.parametrize(
    "gap,fill,seed",
    [
        ("1 to 30 random", "-r", 7),
        ("1 to 30 random", "-r", 1996),
        ("1 to 30 zero", "-f 0", 3),
        ("100 to 300 random", "-r", 11),
    ],
)
def test_close_the_loop(tmp_path, gap, fill, seed):
    lo, hi = (1, 30) if gap.startswith("1 ") else (100, 300)
    (tmp_path / "stream.tgen").write_text(
        STREAM.format(gap=gap, gap_offset=f"19 + {lo} + int(rand({hi - lo + 1}))")
    )
    n = 300
    sh(f"tgen -q {fill} -seed={seed} stream.tgen {n} > stream.dat", tmp_path)

    # recs: extract 20-byte records at each sync word
    sh(f"recs stream.dat {SYNC} 20 > frames.dat", tmp_path)
    assert (tmp_path / "frames.dat").stat().st_size == 20 * n

    # recl: their length
    assert "RESULT 20\n" in sh("recl frames.dat -q", tmp_path)

    # pick: decode every field
    got = sh("pick frames.dat 20 -q order=big -n u ux f w6:12:4d w6:0:12x 6S", tmp_path)
    assert [line.rstrip() for line in got.splitlines()] == [expected_frame(i) for i in range(n)]


def test_close_the_loop_with_a_regex_and_markers(tmp_path):
    """The same, extracting with a regex from sync word to sync word."""
    (tmp_path / "stream.tgen").write_text(
        STREAM.format(gap="random", gap_offset="19 + 1 + int(rand(30))")
    )
    sh("tgen -q -f 0 -seed=5 stream.tgen 200 > stream.dat", tmp_path)
    sh(r"recs stream.dat -r '\x1a\xcf\xfc\x1d' -max_reclen=20 > frames.dat", tmp_path)
    # start to start drops the last frame, which has no sync word after it
    assert (tmp_path / "frames.dat").stat().st_size == 20 * 199
    assert "RESULT 20\n" in sh("recl frames.dat -q", tmp_path)
    got = sh("pick frames.dat 20 -q order=big -n u ux f w6:12:4d w6:0:12x 6S", tmp_path)
    assert [line.rstrip() for line in got.splitlines()] == [expected_frame(i) for i in range(199)]


@pytest.mark.parametrize("reclen", [7, 37, 256, 1000])
def test_recl_finds_what_tgen_made(tmp_path, reclen):
    (tmp_path / "frames.tgen").write_text(
        "sync  # 0 # 1 # 'N' # 0x03915ed3\n"
        "count # 4 # 1 # 'n' # pmod(I, 65536)\n"
        f"noise # 6 # 1 # 'C{reclen - 6}' # [int(rand(256)) for _ in range({reclen - 6})]\n"
    )
    sh("tgen -q -seed=2 frames.tgen 60 > frames.dat", tmp_path)
    assert f"RESULT {reclen}\n" in sh("recl frames.dat -q", tmp_path)
    counts = sh(f"pick frames.dat {reclen} -q order=big +4 wd", tmp_path).split()
    assert counts == [str(i) for i in range(60)]


# --- 2. a subcommutated header ---------------------------------------------------------

HEADER = """\
# a 240-byte header, sent a piece at a time in the frames
mission # 0   # 1 # 'A16'  # 'AIRSAR-SIM'
date    # 16  # 1 # 'a10'  # '2026-09-28'
version # 26  # 1 # 'n'    # 3
count   # 28  # 1 # 'N'    # 123456
coeffs  # 32  # 1 # 'd>10' # [k / 8 for k in range(10)]
notes   # 112 # 1 # 'A128' # 'clear skies, no wind; ' * 5
"""
FRAMES = """\
# frames carrying the header {slice} bytes at a time
SLICE = {slice}
LENGTH = 240
sync      # 0  # 1 # 'N' # 0x03915ed3
frame     # 4  # 1 # 'N' # I
sub_index # 8  # 1 # 'n' # pmod(I * SLICE, LENGTH)
sub_data  # 10 # 1 # f"a{{SLICE}}" # subcom_file('header.dat', P.sub_index.value, SLICE)
signal    # {signal} # 1 # 'f>' # sin(I / 10)
"""


@pytest.mark.parametrize("slice_,first", [(16, 7), (16, 0), (8, 29), (24, 3), (48, 1)])
def test_subcommutated_header(tmp_path, slice_, first):
    frame_len = 10 + slice_ + 4
    per_header = 240 // slice_
    (tmp_path / "header.tgen").write_text(HEADER)
    (tmp_path / "frames.tgen").write_text(FRAMES.format(slice=slice_, signal=10 + slice_))
    sh("tgen -q header.tgen > header.dat", tmp_path)
    n = 5 * per_header + 3  # several headers, starting and ending partway through one
    sh(f"tgen -q frames.tgen {n} {first} > frames.dat", tmp_path)

    # The first frame that starts a header (its sub_index is 0), as in pick's
    # AIRSAR example: pick prints the index with the record number, awk finds it.
    start = sh(
        f"pick frames.dat {frame_len} -q -n order=big w4d | awk '$2 == 0 {{ print $1; exit }}'",
        tmp_path,
    ).strip()
    assert int(start) == (-first) % per_header

    # The header pieces from there on, in binary, reassemble the header
    pieces = f"pick frames.dat {frame_len} -q -b +10 {slice_}b start={start}"
    header = (tmp_path / "header.dat").read_bytes()
    stream = sh(f"{pieces} | od -An -v -tx1", tmp_path).split()
    stream = bytes(int(x, 16) for x in stream)
    complete = len(stream) // 240
    assert complete >= 4
    assert stream[: 240 * complete] == header * complete

    # and decode, header by header, to what header.tgen says
    got = sh(
        f"{pieces} | pick 240 -q order=big 16S -1 bs 10S -1 bs wd ud 10d", tmp_path
    ).splitlines()
    # mission (A16: space-padded), date, version, count, coefficients
    want = f"{'AIRSAR-SIM':16} 2026-09-28 3 123456 " + " ".join(f"{k / 8:g}" for k in range(10))
    assert [line.rstrip() for line in got] == [want] * complete
    notes = sh(f"{pieces} | pick 240 -q +112 128A rec=0", tmp_path).rstrip()
    assert notes == ("clear skies, no wind; " * 5).rstrip()


# --- 3. bit-level frames: tgen -> recl -bits (-> pick) -------------------------------------

PCM = """\
# PCM frames of {words} {width}-bit words: a 3-word sync, a counter, and channels,
# after {lead} bits of junk. The stream is built once, then written {record_bytes}
# bytes per tgen record, with the B (bit string) pack type.
W = {width}
sync = [0b1111101011, 0b1100110011, 0b0100000111]
words = lambda n: [s % 2**W for s in sync] + [n % 2**W] \\
    + [(97 * k + n // 4) % 2**W for k in range({words} - 4)]
stream = bitstring([1, 0, 1] * {lead}, 1)[:{lead}] \\
    + ''.join(bitstring(words(n), W) for n in range({nframes}))
chunk # 0 # 1 # '{letter}{record_bits}' # stream[{record_bits} * I : {record_bits} * (I + 1)]
"""


@pytest.mark.parametrize(
    "words,width,lead,lsb",
    [(25, 10, 0, False), (25, 10, 3, False), (111, 7, 5, False), (64, 12, 0, False),
     (21, 11, 0, False), (25, 10, 6, True)],
)  # fmt: skip
def test_bit_level_frames(tmp_path, words, width, lead, lsb):
    import math

    frame_bits = words * width
    record_bytes = math.lcm(frame_bits, 8) // 8  # the byte-aligned period
    frames_per_record = 8 * record_bytes // frame_bits
    nframes = 60 * frames_per_record
    (tmp_path / "pcm.tgen").write_text(
        PCM.format(words=words, width=width, lead=lead, nframes=nframes,
                   record_bytes=record_bytes, record_bits=8 * record_bytes,
                   letter="b" if lsb else "B")
    )  # fmt: skip
    nrecords = (lead + nframes * frame_bits) // (8 * record_bytes)
    sh(f"tgen -q pcm.tgen {nrecords} > pcm.dat", tmp_path)

    order = "-lsb" if lsb else "-bits"
    assert f"RESULT {frame_bits} bits" in sh(f"recl pcm.dat {order} -q", tmp_path)
    if lsb:
        return
    # comparing bytes finds only the byte-aligned period
    assert f"RESULT {record_bytes}\n" in sh(f"recl pcm.dat -q -max={2 * record_bytes}", tmp_path)
    if lead:
        return
    # each record starts with a frame: pick reads its counter (word 3) as a bit field
    first_byte = 3 * width // 8
    shift = 8 * first_byte + 32 - 4 * width
    got = sh(f"pick pcm.dat {record_bytes} -q order=big u0+{first_byte}:{shift}:{width}d", tmp_path)
    counters = [int(x) for x in got.split()]
    want = [(r * frames_per_record) % 2**width for r in range(nrecords)]
    assert counters == want

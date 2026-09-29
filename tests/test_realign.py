"""realign: frames that start at any bit, written on byte boundaries."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from telemetry_cli.realign.cli import main
from telemetry_cli.realign.frames import RealignError, fixed, pack_frames, search, stream_bits

BIN = Path(sys.executable).parent
SYNC_WORDS = [0b1111101011, 0b1100110011, 0b0100000111]
SYNC_BITS = "".join(format(w, "010b") for w in SYNC_WORDS)


def pcm_bits(n: int, words: int = 25, width: int = 10, lead: str = "101") -> str:
    """n PCM frames as a string of bits: sync, counter, channels; after `lead`."""
    top = (1 << width) - 1
    frames = []
    for i in range(n):
        values = SYNC_WORDS + [i & top] + [(97 * k + i // 4) & top for k in range(words - 4)]
        frames.append("".join(format(v, f"0{width}b") for v in values))
    return lead + "".join(frames)


def to_bytes(bits: str) -> bytes:
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big") if bits else b""


def realign(data: bytes, *args) -> tuple[int, bytes, str]:
    out, err = io.BytesIO(), io.StringIO()
    code = main(["-", *args], stdin=io.BytesIO(data), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def counters(frames: bytes, width: int = 10, frame_bytes: int = 32) -> list[int]:
    """Each realigned frame's counter (word 3), read from its bits."""
    out = []
    for k in range(len(frames) // frame_bytes):
        bits = "".join(format(b, "08b") for b in frames[k * frame_bytes : (k + 1) * frame_bytes])
        out.append(int(bits[3 * width : 4 * width], 2))
    return out


# --- the pieces --------------------------------------------------------------------------


def test_fixed_and_pack():
    b = stream_bits(bytes([0b10110011, 0b11110000]))
    f = fixed(b, 5, 1)
    assert f.tolist() == [[0, 1, 1, 0, 0], [1, 1, 1, 1, 1], [1, 0, 0, 0, 0]]
    assert pack_frames(f) == bytes([0b01100000, 0b11111000, 0b10000000])
    assert pack_frames(f, left=True) == bytes([0b00001100, 0b00011111, 0b00010000])
    assert pack_frames(f, fill=1) == bytes([0b01100111, 0b11111111, 0b10000111])
    assert fixed(b, 5, 1, limit=2).shape == (2, 5)
    assert pack_frames(fixed(b, 8, 0)) == bytes([0b10110011, 0b11110000])  # whole bytes: unchanged


def test_fixed_errors():
    with pytest.raises(RealignError):
        fixed(stream_bits(b"ab"), 0)
    with pytest.raises(RealignError):
        fixed(stream_bits(b"ab"), 4, -1)


def test_search():
    data = to_bytes(pcm_bits(20, lead="11"))
    found = search(data, SYNC_BITS, 250)
    assert found.starts == [2 + 250 * k for k in range(20)] and found.gaps == {250: 19}
    with pytest.raises(RealignError, match="0s and 1s"):
        search(data, "10x1", 250)
    with pytest.raises(RealignError, match="at most 56"):
        search(data, "1" * 57, 250)
    with pytest.raises(RealignError, match="longer than the frame"):
        search(data, SYNC_BITS, 20)


def test_search_with_bit_errors_in_the_sync():
    bits = list(pcm_bits(30))
    for k in (4, 11, 20):  # flip a bit in three frames' sync words
        i = 3 + 250 * k + 7
        bits[i] = "1" if bits[i] == "0" else "0"
    data = to_bytes("".join(bits))
    assert len(search(data, SYNC_BITS, 250).starts) == 27
    found = search(data, SYNC_BITS, 250, errors=1)
    assert len(found.starts) == 30 and sum(1 for e in found.errors if e) == 3


# --- the command line ------------------------------------------------------------------------


def test_fixed_stepping():
    data = to_bytes(pcm_bits(100, lead="101"))
    code, out, err = realign(data, "250", "3")
    assert code == 0 and len(out) == 100 * 32
    assert counters(out) == list(range(100))
    assert "100 frames of 250 bits from bit 3" in err and "32 bytes (6 padding bits)" in err


def test_options():
    data = to_bytes(pcm_bits(50))
    assert realign(data, "250", "-offset=3", "-q")[1] == realign(data, "250", "3", "-q")[1]
    assert len(realign(data, "250", "3", "-max=7", "-q")[1]) == 7 * 32
    left = realign(data, "250", "3", "-left", "-q")[1]
    assert left[0] >> 2 == 0 and left[0] & 0b11 == 0b11  # 6 padding bits, then the frame
    filled = realign(data, "250", "3", "-fill=1", "-q")[1]
    assert filled[31] & 0b111111 == 0b111111
    bits = np.array([int(c) for c in pcm_bits(50)], dtype=np.uint8)
    lsb = np.packbits(bits, bitorder="little").tobytes()  # least significant bit first
    assert counters(realign(lsb, "250", "3", "-lsb", "-q")[1]) == list(range(50))


def test_a_bit_slip():
    """A bit lost in frame 30: fixed stepping goes wrong from there; -sync doesn't."""
    bits = pcm_bits(80)
    slipped = bits[: 3 + 30 * 250 + 77] + bits[3 + 30 * 250 + 78 :]
    data = to_bytes(slipped)
    fixed_out = counters(realign(data, "250", "3", "-q")[1])
    assert fixed_out[:30] == list(range(30)) and fixed_out[31:] != list(range(31, len(fixed_out)))
    code, out, err = realign(data, "250", f"-sync={SYNC_BITS}")
    assert counters(out) == list(range(80))
    assert "249 bits (1x)" in err  # the short frame


def test_the_file_is_optional(tmp_path, monkeypatch):
    data = to_bytes(pcm_bits(20))
    out = io.BytesIO()
    assert main(["250", "3", "-q"], stdin=io.BytesIO(data), stdout=out, stderr=io.StringIO()) == 0
    assert counters(out.getvalue()) == list(range(20))
    # a file whose name is a number is still a file
    monkeypatch.chdir(tmp_path)
    (tmp_path / "250").write_bytes(data)
    out = io.BytesIO()
    assert main(["250", "250", "3", "-q"], stdin=io.BytesIO(b""), stdout=out) == 0
    assert counters(out.getvalue()) == list(range(20))


@pytest.mark.parametrize(
    "args,message",
    [
        ([], "give a frame length"),
        (["-", "x"], "must be numbers"),
        (["-", "250", "-fill=2"], "-fill must be"),
        (["-", "0"], "at least 1 bit"),
        (["-", "250", "-sync=abc"], "0s and 1s"),
        (["-", "250", "-bogus"], "Unknown option"),
        (["no-such-file", "250"], "Can't open"),
    ],
)
def test_errors(args, message):
    err = io.StringIO()
    code = main(args, stdin=io.BytesIO(b"\x00" * 100), stdout=io.BytesIO(), stderr=err)
    assert code != 0 and message in err.getvalue()


def test_help():
    out = io.BytesIO()
    assert main(["-help"], stdout=out) == 0 and b"byte boundaries" in out.getvalue()


# --- together: tgen -> recl -bits -sync -> realign -> pick ------------------------------------

PCM_TGEN = """\
W = 10
words = lambda n: [0b1111101011, 0b1100110011, 0b0100000111, n % 1024] \\
    + [(97 * k + n // 4) % 1024 for k in range(21)]
stream = '10110' + ''.join(bitstring(words(n), W) for n in range(400))
chunk # 0 # 1 # 'B1000' # stream[1000 * I : 1000 * (I + 1)]
"""


def test_close_the_loop(tmp_path):
    env = {**os.environ, "PATH": f"{BIN}{os.pathsep}{os.environ['PATH']}"}

    def sh(cmd):
        p = subprocess.run(["bash", "-c", "set -eo pipefail; " + cmd], cwd=tmp_path, env=env,
                           capture_output=True, check=False)  # fmt: skip
        assert p.returncode == 0, p.stderr.decode()
        return p.stdout.decode()

    (tmp_path / "pcm.tgen").write_text(PCM_TGEN)
    sh("tgen -q pcm.tgen 100 > pcm.dat")
    report = sh("recl pcm.dat -bits -sync")
    assert "RESULT 250 bits" in report and "SYNC 5 " in report
    # run the realign command recl suggests, as printed
    suggestion = next(line for line in report.splitlines() if "realign" in line)
    command = suggestion.split(": ", 1)[1].split("; or")[0]
    assert command == "realign pcm.dat 250 5"
    sh(f"{command} -q > frames.dat")
    got = sh("pick frames.dat 32 -q order=big u0+3:16:10d").split()
    assert [int(x) for x in got] == list(range(399))  # the 400th frame is cut short

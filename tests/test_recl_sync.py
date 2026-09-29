"""recl -sync: where records start, and their sync word."""

from __future__ import annotations

import io
import os
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from telemetry_cli.recl.cli import main
from telemetry_cli.recl.sync import _circular_runs, find, length_from_repeats

SYNC32 = "00011010110011111111110000011101"  # 0x1ACFFC1D


def frames(n: int, reclen: int = 24, junk: bytes = b"", seed: int = 0) -> bytes:
    """Records: the CCSDS sync word, then random bytes (so nothing else is constant)."""
    rng = np.random.default_rng(seed)
    body = rng.integers(0, 256, (n, reclen - 4), dtype=np.uint8)
    recs = b"".join(bytes.fromhex("1ACFFC1D") + row.tobytes() for row in body)
    return junk + recs


def recl(data: bytes, *opts) -> tuple[int, str]:
    out, err = io.BytesIO(), io.StringIO()
    code = main(["-", *opts], stdin=io.BytesIO(data), stdout=out, stderr=err)
    return code, out.getvalue().decode() + err.getvalue()


def sync_line(text: str) -> tuple[int, int, str]:
    line = next(line for line in text.splitlines() if line.startswith("SYNC "))
    _, offset, n, bits = line.split()
    return int(offset), int(n), bits


@pytest.mark.parametrize("junk", [0, 1, 5, 23])
def test_byte_records_after_junk(junk):
    code, text = recl(frames(200, junk=b"J" * junk), "-sync")
    assert code == 0 and "RESULT 24\n" in text
    offset, n, bits = sync_line(text)
    assert (offset, n, bits) == (8 * (junk % 24), 32, SYNC32)  # the SYNC offset is in bits
    if junk % 24 == 0:
        assert "Records start at byte 0" in text


def test_the_suggested_recs_command_extracts_the_records(tmp_path):
    data = frames(150, junk=b"JUNK!")
    (tmp_path / "d.bin").write_bytes(data)
    code, text = recl(data, "-sync")
    assert "head=5" in text  # the junk
    cmd = next(line for line in text.splitlines() if "To extract records" in line)
    cmd = cmd.split(": ", 1)[1].replace("FILE", "d.bin")
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
    p = subprocess.run(["bash", "-c", cmd], cwd=tmp_path, env=env, capture_output=True, check=True)
    assert p.stdout == data[5:]


def test_bit_frames():
    import test_recl_bits as B

    for lead in (0, 3, 13):
        code, text = recl(B.pcm(25, 10, 300, lead=lead), "-bits", "-sync")
        assert code == 0 and "RESULT 250 bits" in text
        offset, n, bits = sync_line(text)
        assert offset == lead
        sync = "".join(format(w, "010b") for w in B.SYNC)
        assert bits.startswith(sync)  # the sync, and any constant bits after it


def test_bit_errors():
    import test_recl_bits as B

    code, text = recl(B.pcm(25, 10, 400, lead=2, errors=0.02, seed=4), "-bits", "-sync")
    assert "RESULT 250 bits" in text
    offset, n, bits = sync_line(text)
    assert offset == 2 and n >= 20
    note = next(line for line in text.splitlines() if "are the same in" in line)
    near = float(note.split("are the same in ")[1].split("%")[0])
    assert near > 90


def test_continuous_signal():
    """One signal sampled record after record: comparing bytes picks the sample
    spacing, but the sync word's repeats give the record length."""
    recs = b"".join(
        struct.pack(">I", 0x1ACFFC1D)
        + struct.pack(
            ">20H", *[int(30000 + 1000 * np.sin(0.001 * (i * 20 + k))) for k in range(20)]
        )
        for i in range(200)
    )
    code, text = recl(recs, "-q")
    assert "RESULT 44\n" not in text
    code, text = recl(recs, "-sync", "-q")
    assert "RESULT 44\n" in text
    assert sync_line(text)[0] == 0


def test_records_of_varying_length():
    rng = np.random.default_rng(5)
    stream = b"".join(
        bytes.fromhex("1ACFFC1D")
        + rng.integers(0, 256, 10 + int(rng.integers(0, 40)), np.uint8).tobytes()
        for _ in range(300)
    )
    code, text = recl(stream, "-sync")
    assert "varying intervals" in text and "recs" in text


def test_nothing_constant():
    rng = np.random.default_rng(6)
    code, text = recl(rng.integers(0, 256, 4800, dtype=np.uint8).tobytes(), "-sync", "-only=48")
    assert "no sync pattern found" in text


def test_only_one_length():
    code, text = recl(frames(100), "-sync", "-only=24")
    assert "RESULT 24\n" in text and sync_line(text)[:2] == (0, 32)


def test_quiet():
    code, text = recl(frames(100, junk=b"xyz"), "-sync", "-q")
    assert [line.split()[0] for line in text.splitlines()] == ["NOTE", "RESULT", "SYNC"]


def test_pieces():
    assert _circular_runs(np.array([1, 1, 0, 0, 1], bool)) == [(4, 3)]
    assert _circular_runs(np.array([1, 1, 1], bool)) == [(0, 3)]
    assert _circular_runs(np.array([0, 1, 0, 1], bool)) == [(1, 1), (3, 1)]
    r = length_from_repeats(frames(100))
    assert r.gap == 192 and r.fixed
    assert length_from_repeats(b"") is None
    s = find(frames(100), 192)
    assert s.bits == SYNC32 and s.hex() == "0x1acffc1d" and s.exact == 1.0
    assert find(frames(1), 192) is None  # one record: nothing to compare


def test_a_short_constant_field_is_found_by_folding():
    """No 24-bit pattern repeats (the constant field is only 12 bits wide),
    so the data are folded into records to find it."""
    rng = np.random.default_rng(8)
    recs = rng.integers(0, 256, (300, 16), dtype=np.uint8)
    recs[:, 5] = 0xA5  # 8 constant bits...
    recs[:, 6] = (recs[:, 6] & 0x0F) | 0x30  # ...and 4 more
    s = find(recs.tobytes(), 128)
    assert (s.offset, s.bits) == (40, "101001010011") and s.irregular == 0


def test_zero_padding_before_a_sync_word():
    """Zero padding at the end of each record is as constant as the next
    record's sync word, so the pattern includes it; recl says so."""
    rng = np.random.default_rng(9)
    recs = np.zeros((200, 24), dtype=np.uint8)
    recs[:, 0:4] = np.frombuffer(bytes.fromhex("1ACFFC1D"), np.uint8)
    recs[:, 4:12] = rng.integers(0, 256, (200, 8), dtype=np.uint8)  # then zeros: padding
    s = find(recs.tobytes(), 192)
    assert s.bits.endswith(SYNC32) and s.offset + len(s.bits) - 32 == 192  # sync at 0 (192)
    assert s.irregular == 0
    code, text = recl(recs.tobytes(), "-sync")
    assert "RESULT 24\n" in text and "may be padding at the end of the record before" in text


def test_too_few_records():
    assert find(frames(1), 192) is None
    assert find(b"\x00" * 30, 192) is None

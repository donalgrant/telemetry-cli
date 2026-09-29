"""recl -bits: record lengths that aren't a whole number of bytes."""

from __future__ import annotations

import io

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from telemetry_cli.recl.bits import describe, propose, scores, windows
from telemetry_cli.recl.cli import main

SYNC = [0b1111101011, 0b1100110011, 0b0100000111]  # a 30-bit sync, as three 10-bit words


def pcm(words: int, width: int, n: int, *, lead: int = 0, errors: float = 0.0,
        lsb: bool = False, seed: int = 0) -> bytes:  # fmt: skip
    """n frames of `words` words of `width` bits: sync, a counter, then channels.

    Each channel word has its own level, drifting slowly from frame to frame,
    plus a little noise, as in commutated PCM. `lead` random bits come first,
    so frames start mid-byte; `errors` is the fraction of bits flipped.
    """
    rng = np.random.default_rng(seed)
    top = (1 << width) - 1
    level = rng.integers(0, top + 1, words)
    drift = rng.uniform(-0.3, 0.3, words)
    parts = [rng.integers(0, 2, lead, dtype=np.uint8)]
    for i in range(n):
        values = [v & top for v in SYNC] + [i & top]
        values += [int(level[k] + drift[k] * i + rng.integers(0, 3)) & top for k in range(4, words)]
        parts.append(
            np.array([(v >> (width - 1 - b)) & 1 for v in values for b in range(width)], np.uint8)
        )
    bits = np.concatenate(parts)
    if errors:
        bits ^= (rng.random(len(bits)) < errors).astype(np.uint8)
    return np.packbits(bits, bitorder="little" if lsb else "big").tobytes()


def recl(data: bytes, *opts) -> tuple[int, str]:
    out, err = io.BytesIO(), io.StringIO()
    code = main(["-", *opts], stdin=io.BytesIO(data), stdout=out, stderr=err)
    return code, out.getvalue().decode() + err.getvalue()


def result(data: bytes, *opts) -> int:
    code, text = recl(data, "-bits", "-q", *opts)
    assert code == 0, text
    return int(text.split("RESULT ")[1].split()[0])


# --- finding lengths ---------------------------------------------------------------


@pytest.mark.parametrize(
    "words,width",
    [(25, 10), (64, 12), (16, 10), (11, 9), (40, 7), (32, 8), (100, 10), (24, 16)],
)
@pytest.mark.parametrize("lead", [0, 3, 7])
def test_finds_pcm_frame_lengths(words, width, lead):
    assert result(pcm(words, width, 200, lead=lead)) == words * width


@settings(max_examples=40, deadline=None)
@given(
    words=st.integers(6, 80),
    width=st.integers(7, 16),
    lead=st.integers(0, 40),
    seed=st.integers(0, 10_000),
)
def test_finds_random_pcm_layouts(words, width, lead, seed):
    assert result(pcm(words, width, 120, lead=lead, seed=seed)) == words * width


@pytest.mark.parametrize("errors", [0.001, 0.01, 0.05])
def test_bit_errors(errors):
    assert result(pcm(25, 10, 400, errors=errors, seed=1)) == 250


def test_lsb_first():
    data = pcm(25, 10, 200, lead=5, lsb=True)
    assert result(data, "-lsb") == 250
    # read most significant bit first, the same data show no 250-bit frames
    assert result(data) != 250 if recl(data, "-bits", "-q")[0] == 0 else True


def test_byte_aligned_frames_too():
    data = pcm(12, 8, 200)  # 96-bit frames: 12 bytes
    assert result(data) == 96
    code, text = recl(data, "-q")
    assert "RESULT 12\n" in text


def test_byte_mode_sees_only_the_byte_aligned_period():
    """250-bit frames repeat byte-aligned every 4 frames: 125 bytes."""
    data = pcm(25, 10, 400)
    code, text = recl(data, "-q")
    assert "RESULT 125\n" in text
    assert result(data) == 250


def test_range_only_and_fact():
    data = pcm(25, 10, 200, lead=2)
    assert result(data, "-min=200", "-max=300") == 250
    assert result(data, "-only=125,250,500") == 250
    assert result(data, "-min=100", "-max=600", "-fact=50") == 250
    code, text = recl(data, "-bits", "-min=240", "-max=245", "-q")
    assert "Checking Record Lengths 240, 241, 242, 243, 244, 245 bits" in text


def test_skip_limit_reduce():
    data = b"HEADER" * 5 + pcm(25, 10, 300)
    assert result(data, "-skip=30") == 250
    assert result(data, "-limit=4000") == 250
    assert result(data, "-reduce=2") == 250


def test_no_repeating_pattern():
    rng = np.random.default_rng(3)
    code, text = recl(rng.integers(0, 256, 4000, dtype=np.uint8).tobytes(), "-bits")
    assert code != 0 and "no bit pattern repeats" in text


# --- output ----------------------------------------------------------------------------


def test_output_lines():
    code, text = recl(pcm(25, 10, 200, lead=4), "-bits")
    lines = text.splitlines()
    assert code == 0
    assert lines[0].startswith("NOTE Checking Record Lengths ") and lines[0].endswith(" bits")
    assert lines[1] == "RESULT 250 bits (31 bytes + 2 bits)"
    assert lines[2].startswith("CORR ")
    assert lines[3].startswith("NOTE Based on ") and "most significant bit first" in lines[3]


def test_verbose_table():
    code, text = recl(pcm(25, 10, 200), "-bits", "-v", "-only=125,250")
    table = text.split("Table of Sorted Correlations\n")[1].splitlines()
    assert table[0].endswith("% for reclen 250 bits")


@pytest.mark.parametrize(
    "bits,text",
    [
        (250, "250 bits (31 bytes + 2 bits)"),
        (96, "96 bits (12 bytes)"),
        (9, "9 bits (1 byte + 1 bit)"),
        (7, "7 bits (0 bytes + 7 bits)"),
    ],
)  # fmt: skip
def test_describe(bits, text):
    assert describe(bits) == text


# --- the pieces --------------------------------------------------------------------------


def naive_windows(data: bytes, width: int, lsb: bool) -> list[int]:
    bits = np.unpackbits(np.frombuffer(data, np.uint8), bitorder="little" if lsb else "big")
    k = (width + 7) // 8 + 1
    n = 8 * (len(data) - k + 1)
    return [int("".join(map(str, bits[i : i + width])), 2) for i in range(max(n, 0))]


@settings(max_examples=60, deadline=None)
@given(data=st.binary(min_size=0, max_size=40), width=st.sampled_from([1, 5, 8, 10, 16, 24]),
       lsb=st.booleans())  # fmt: skip
def test_windows_match_a_naive_bit_reader(data, width, lsb):
    assert windows(data, width, lsb=lsb).tolist() == naive_windows(data, width, lsb)


def test_scores_and_proposals():
    w = windows(pcm(25, 10, 100), 8)
    s, counts = scores(w, [250, 251, 10**9])
    assert s[0] > 0.1 > s[1] and s[2] == 0.0 and counts[2] == 0
    proposals = propose(windows(pcm(25, 10, 100), 24), 1, 10_000, 1)
    assert 250 in proposals and 125 in proposals  # the length and its divisors
    assert propose(windows(b"", 24), 1, 100, 1) == []

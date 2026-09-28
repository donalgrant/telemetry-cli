"""Helpers shared by the command-line programs."""

from __future__ import annotations

import contextlib
import os
import sys


def broken_pipe(stdout) -> int:
    """Handle stdout closing early (``tool | head``): exit quietly, with status 0.

    Python would otherwise report the error when it flushes stdout at exit.
    """
    if stdout is sys.stdout.buffer:
        with contextlib.suppress(OSError, ValueError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0

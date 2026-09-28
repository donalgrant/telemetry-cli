"""Tagged diagnostic messages, replacing the Perl Util::Msg module.

Util::Msg printed each message as ``TAG text``, with ``NOTE`` as the default
tag, and could hide or select tags. recl's result lines (``RESULT 48``,
``CORR 97.5``) use this format, so it is part of recl's output.
"""

from __future__ import annotations

import sys
from typing import TextIO


class Messenger:
    """Print ``TAG text`` lines to a stream, optionally filtering by tag."""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        hide: set[str] | frozenset[str] = frozenset(),
        default_tag: str = "NOTE",
    ):
        self._stream = stream
        self.hide = set(hide)
        self.default_tag = default_tag
        self.counts: dict[str, int] = {}

    @property
    def stream(self) -> TextIO:
        # Look up sys.stderr at call time, so pytest's capsys sees the output.
        return self._stream if self._stream is not None else sys.stderr

    def __call__(self, text: object = "", tag: str | None = None) -> None:
        tag = tag or self.default_tag
        if tag in self.hide:
            return
        self.counts[tag] = self.counts.get(tag, 0) + 1
        print(f"{tag} {text}", file=self.stream)

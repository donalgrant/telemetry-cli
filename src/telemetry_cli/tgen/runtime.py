"""Generating records from a parsed command file.

Each field of an item specification is Python code, evaluated for every
record in one shared namespace. A field may hold several statements
separated by semicolons; its value is that of the last one (an expression,
or the value assigned by an assignment).

The namespace provides:

    I            the record counter
    F            the fill byte: each read gives the fill value, or a new
                 random byte when F is set to a string containing "ran"
                 (as with the -r option)
    X, O         set by seek_file
    DEBUG        set true to trace evaluation on stderr
    P            the items: P.name.value is the item's value for this record
                 (or the last record, if it hasn't been evaluated yet), and
                 P.name._value evaluates its value field again. Likewise for
                 name, offset, trigger and type.
    rand, srand  Perl-compatible random numbers (drand48)
    subcom_file, file_lookup, seek_file
                 read data from files
    pmod         Perl's % (on the integer parts of its operands)
    pand, por, pxor, pshl, pshr
                 Perl's &, |, ^, << and >> (on unsigned 64-bit integers)
    cat          Perl's . (join values as text; numbers as Perl prints them)
    bitstring    words as a string of bits for the B pack type:
                 bitstring([3, 5], 4) is "00110101"
    sprintf      Perl's sprintf
    pi, sin, cos, tan, atan2, sqrt, exp, log, floor, ceil
    stderr       for diagnostics (stdout is the data)
"""

from __future__ import annotations

import ast
import math
import sys
from collections.abc import Callable
from typing import BinaryIO, TextIO

from .. import _pack
from .._perl import UV_MAX, numify, perl_str, sprintf, to_uv
from .cmdfile import Item, Statement


class TgenError(ValueError):
    pass


class Drand48:
    """Perl's random number generator (Perl_drand48), so seeded runs match Perl's."""

    A, C, M = 0x5DEECE66D, 0xB, 1 << 48

    def __init__(self, seed: int | None = None):
        if seed is None:
            import os

            seed = int.from_bytes(os.urandom(4), "little")
        self.seed(seed)

    def seed(self, seed: int) -> None:
        self.x = ((int(seed) & 0xFFFFFFFF) << 16) + 0x330E

    def random(self) -> float:
        self.x = (self.A * self.x + self.C) % self.M
        return self.x / self.M


def perl_true(v) -> bool:
    """Perl's truth of a field's value: undef, 0, "" and "0" are false."""
    if v is None:
        return False
    if isinstance(v, str):
        return v not in ("", "0")
    if isinstance(v, (list, tuple, bytes)):
        return True  # a reference, or a non-empty string of bytes
    return bool(v)


def pmod(a, b):
    """Perl's a % b: both operands are truncated to integers first."""
    a, b = int(numify(a)), int(numify(b))
    if b == 0:
        raise ZeroDivisionError("Illegal modulus zero")
    return a % b


def bitstring(values, width) -> str:
    """Values as a string of bits, most significant first, for the B pack type.

    width is one number of bits for every value, or a list, one per value.
    Values are taken modulo 2**width (so negative ones are two's complement).
    """
    if isinstance(values, (int, float)):
        values = [values]
    values = list(values)
    widths = list(width) if isinstance(width, (list, tuple)) else [width] * len(values)
    if len(widths) != len(values):
        raise ValueError(f"bitstring: {len(values)} values but {len(widths)} widths")
    out = []
    for v, w in zip(values, widths, strict=True):
        w = int(w)
        out.append(format(int(numify(v)) % (1 << w), f"0{w}b") if w > 0 else "")
    return "".join(out)


def cat(*values) -> str:
    """Perl's string concatenation."""
    return "".join(perl_str(v) for v in values)


class _FieldCode:
    """A compiled field: statements, then the expression whose value is the field's."""

    def __init__(self, src: str, where: str):
        self.src, self.where = src, where
        try:
            tree = ast.parse(src.strip() or "None", mode="exec")
        except SyntaxError as e:
            raise TgenError(f"{where}: can't parse {src!r}: {e.msg}") from None
        tree = _ReadFill().visit(tree)
        body = tree.body
        last = body[-1] if body else ast.Expr(ast.Constant(None))
        if isinstance(last, ast.Expr):
            result = last.value
            body = body[:-1]
        elif isinstance(last, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            target = last.targets[-1] if isinstance(last, ast.Assign) else last.target
            result = _loaded(target)
        else:
            result = ast.Constant(None)
        self.stmts = compile(ast.fix_missing_locations(ast.Module(body, [])), where, "exec")
        self.expr = compile(ast.fix_missing_locations(ast.Expression(result)), where, "eval")

    def run(self, ns: dict):
        try:
            exec(self.stmts, ns)
            return eval(self.expr, ns)
        except TgenError:
            raise
        except Exception as e:
            raise TgenError(f"{self.where}: {type(e).__name__}: {e}  (in {self.src!r})") from None


def _loaded(target: ast.expr) -> ast.expr:
    """An expression reading back an assignment target (with reads of F as reads)."""
    node = ast.parse(ast.unparse(target), mode="eval").body
    return _ReadFill().visit(node)


class _ReadFill(ast.NodeTransformer):
    """Turn each read of F into a call, so it can give a new random byte every time."""

    def visit_Name(self, node: ast.Name):
        if node.id == "F" and isinstance(node.ctx, ast.Load):
            return ast.copy_location(ast.Call(ast.Name("_read_fill", ast.Load()), [], []), node)
        return node


class ItemValues:
    """P.name: one item's current values, and its fields for re-evaluation."""

    def __init__(self, gen: Generator, item: Item):
        self._gen, self._item = gen, item
        self.name = item.name
        self._current: dict = {}

    def _get(self, field: str):
        # The Perl pasted $P{name}{field} into the code as text, so a float
        # came back with 15 significant digits.
        v = self._current.get(field)
        return float(perl_str(v)) if isinstance(v, float) and math.isfinite(v) else v

    offset = property(lambda self: self._get("offset"))
    trigger = property(lambda self: self._get("trigger"))
    type = property(lambda self: self._get("type"))
    value = property(lambda self: self._get("value"))

    @property
    def _name(self):
        return self._item.name

    @property
    def _offset(self):
        return self._gen._code(self._item, "offset").run(self._gen.ns)

    @property
    def _trigger(self):
        return self._gen._code(self._item, "trigger").run(self._gen.ns)

    @property
    def _type(self):
        return self._gen._code(self._item, "type").run(self._gen.ns)

    @property
    def _value(self):
        return self._gen._code(self._item, "value").run(self._gen.ns)

    def __getitem__(self, key: str):
        return getattr(self, key)


class Items:
    def __init__(self):
        self._items: dict[str, ItemValues] = {}

    def __getattr__(self, name: str) -> ItemValues:
        try:
            return self.__dict__["_items"][name]
        except KeyError:
            raise AttributeError(f"no item named {name!r}") from None

    def __getitem__(self, name: str) -> ItemValues:
        return self._items[name]


class Generator:
    def __init__(
        self,
        items: list[Item],
        statements: list[Statement],
        *,
        fill="0",
        seed: int | None = None,
        stderr: TextIO | None = None,
        source: str = "command file",
    ):
        self.items = items
        self.source = source
        self.stderr = stderr if stderr is not None else sys.stderr
        self.rng = Drand48(seed)
        self.files: dict[str, BinaryIO] = {}
        self._compiled: dict[tuple[int, str], _FieldCode] = {}
        self.P = Items()
        for it in items:
            self.P._items[it.name] = ItemValues(self, it)
        self.ns: dict = self._namespace(fill)
        for st in statements:
            _FieldCode(st.code, f"{source}:{st.line}").run(self.ns)

    # --- the namespace --------------------------------------------------------

    def _namespace(self, fill) -> dict:
        ns = {
            "I": 0,
            "F": fill,
            "X": None,
            "O": 0,
            "DEBUG": 0,
            "P": self.P,
            "rand": self.rand,
            "srand": self.srand,
            "subcom_file": self.subcom_file,
            "file_lookup": self.file_lookup,
            "seek_file": self.seek_file,
            "pmod": pmod,
            "pand": lambda a, b: to_uv(a) & to_uv(b),
            "por": lambda a, b: to_uv(a) | to_uv(b),
            "pxor": lambda a, b: to_uv(a) ^ to_uv(b),
            "pshl": lambda a, b: (to_uv(a) << to_uv(b)) & UV_MAX if to_uv(b) < 64 else 0,
            "pshr": lambda a, b: to_uv(a) >> to_uv(b) if to_uv(b) < 64 else 0,
            "cat": cat,
            "bitstring": bitstring,
            "sprintf": sprintf,
            "stderr": self.stderr,
            "_read_fill": self.read_fill,
        }
        for name in ("pi", "sin", "cos", "tan", "atan2", "sqrt", "exp", "log", "floor", "ceil"):
            ns[name] = getattr(math, name)
        return ns

    def rand(self, n=1):
        """Perl's rand: a float in [0, n); rand(0) is rand(1)."""
        n = numify(n) or 1
        return self.rng.random() * n

    def srand(self, seed=0):
        self.rng.seed(int(numify(seed)))
        return seed

    def read_fill(self):
        """The value of F: the fill, or a random byte if the fill is "random"."""
        mode = self.ns["F"]
        if isinstance(mode, str) and "ran" in mode:
            return int(self.rng.random() * 256)
        return mode

    # --- file helpers (each file is opened once) ------------------------------

    def _file(self, name) -> BinaryIO:
        name = str(name)
        if name not in self.files:
            try:
                self.files[name] = open(name, "rb")  # noqa: SIM115
            except OSError as e:
                raise TgenError(f"Can't read from {name}:  {e.strerror}") from None
        return self.files[name]

    def _read(self, name, offset, nbytes) -> bytes | None:
        f = self._file(name)
        offset = int(numify(offset))
        if offset < 0:
            return None
        f.seek(offset)
        return f.read(max(int(numify(nbytes)), 0))

    def subcom_file(self, file, offset, nbytes):
        """nbytes of file starting at offset, as a byte string."""
        data = self._read(file, offset, nbytes)
        return b"" if data is None else data

    def file_lookup(self, file, offset, nbytes, unpack_type):
        """The first value unpacked from nbytes of file at offset (0 if they can't be read)."""
        nbytes = int(numify(nbytes))
        data = self._read(file, offset, nbytes)
        if data is None or len(data) != nbytes:
            return 0
        values = _pack.unpack(str(unpack_type), data)
        return values[0] if values else None

    def seek_file(self, file, offset, nbytes, unpack_type, cond):
        """Read nbytes at offset (evaluated with O = 0, 1, 2, ...) until cond is true.

        offset and cond are code, as strings; X holds the value just read.
        Returns the offset that satisfied cond, or -1 at the end of the file.
        """
        offset_code = _FieldCode(str(offset), "seek_file offset")
        cond_code = _FieldCode(str(cond), "seek_file condition")
        nbytes = int(numify(nbytes))
        self.ns["O"] = 0
        while True:
            at = offset_code.run(self.ns)
            data = self._read(file, at, nbytes)
            if data is None or len(data) != nbytes:
                return -1
            values = _pack.unpack(str(unpack_type), data)
            self.ns["X"] = values[0] if values else None
            if self.ns.get("DEBUG"):
                print(f"o={self.ns['O']}; seek_value={self.ns['X']}", file=self.stderr)
            self.ns["O"] += 1
            if perl_true(cond_code.run(self.ns)):
                return at

    # --- generating -------------------------------------------------------------

    def _code(self, item: Item, field: str) -> _FieldCode:
        key = (id(item), field)
        if key not in self._compiled:
            self._compiled[key] = _FieldCode(
                getattr(item, field), f"{self.source}:{item.line} ({item.name}, {field})"
            )
        return self._compiled[key]

    def _eval(self, item: Item, field: str):
        value = self._code(item, field).run(self.ns)
        if self.ns.get("DEBUG"):
            print(f"{item.name}.{field}: {getattr(item, field)!r} -> {value!r}", file=self.stderr)
        return value

    def frame(self) -> bytes:
        frame: list[int | None] = []
        for item in self.items:
            cur = self.P._items[item.name]._current
            cur["offset"] = offset = self._eval(item, "offset")
            cur["trigger"] = trigger = self._eval(item, "trigger")
            if not perl_true(trigger):
                continue
            if numify(offset) < 0:  # a calculation only: evaluate the value, don't pack
                cur["value"] = self._eval(item, "value")
                continue
            cur["type"] = type_ = self._eval(item, "type")
            cur["value"] = value = self._eval(item, "value")
            values = list(value) if isinstance(value, (list, tuple)) else [value]
            try:
                packed = _pack.pack(str(type_), *values)
            except _pack.PackError as e:
                raise TgenError(f"{self.source}:{item.line} ({item.name}): {e}") from None
            start = int(numify(offset))
            end = start + len(packed)
            if end > len(frame):
                frame.extend([None] * (end - len(frame)))
            frame[start:end] = packed
        out = bytearray()
        for b in frame:
            if b is None:
                out.append(int(numify(self.read_fill())) & 0xFF)
            else:
                out.append(b)
        return bytes(out)

    def run(
        self,
        out: BinaryIO,
        nframes: int,
        first: int,
        *,
        notify: int = 100,
        quiet: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        last = first + nframes - 1
        self.ns["I"] = first
        while numify(self.ns["I"]) <= last:
            out.write(self.frame())
            i = int(numify(self.ns["I"]))
            if not quiet and not (i + 1) % notify and progress:
                progress(f"{i}/{last}")
            self.ns["I"] = self.ns["I"] + 1
        for f in self.files.values():
            f.close()

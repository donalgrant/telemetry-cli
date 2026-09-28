"""Translate a Perl tgen command file into the Python form (``tgen --convert``).

The translation is pattern-based. It handles what tgen command files usually
contain: ``$::name`` variables, ``$P{item}{field}``, arithmetic, string
concatenation, interpolated strings, ``map { ... } (a..b)``, ``++``/``--``,
and statement modifiers (``x if y``). Anything else that looks like Perl is
left as it is, with a ``# TODO(convert)`` comment line above it, so that
running the result fails loudly rather than doing something different.
"""

from __future__ import annotations

import ast
import re

from .cmdfile import SEPARATOR, logical_lines

_PERLISH = re.compile(
    r"\$|@|->|\bsub\b|=~|\bmy\b|\bprint\b(?!\()|\?|\blast\b|\bnext\b|\beq\b|\bne\b"
)


def convert(text: str) -> str:
    out = []
    for _, line in logical_lines(text):
        if line[:1] in ("#", "!", ";") or not line.strip():
            out.append(line)
            continue
        if len(SEPARATOR.findall(line)) >= 4:
            parts = SEPARATOR.split(line)
            seps = SEPARATOR.findall(line)
            fields = [parts[0].strip()] + [expr(p.strip()) for p in parts[1:5]]
            todo = [f for f in fields[1:] if _PERLISH.search(_strip_strings(f))]
            rest = "".join(s + p for s, p in zip(seps[4:], parts[5:], strict=False))
            new = fields[0] + "".join(s + f for s, f in zip(seps, fields[1:], strict=False)) + rest
        else:
            new = statement(line.strip())
            todo = [new] if _PERLISH.search(_strip_strings(new)) else []
        if todo:
            out.append("# TODO(convert): this line still contains Perl")
        out.append(new)
    return "\n".join(out) + "\n"


# --- pieces --------------------------------------------------------------------

_STRING = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")


def _strip_strings(s: str) -> str:
    return _STRING.sub('""', s)


def _split_code(s: str):
    """Alternating (code, string literal) pieces of s."""
    pos = 0
    for m in _STRING.finditer(s):
        yield s[pos : m.start()], False
        yield m.group(0), True
        pos = m.end()
    yield s[pos:], False


def _variables(code: str) -> str:
    code = re.sub(r"\$P\{\s*(\w+)\s*\}\s*\{\s*(\w+)\s*\}", r"P.\1.\2", code)
    code = re.sub(r"[$@]::(\w+)", r"\1", code)
    code = re.sub(r"\bmy\s+[$@](\w+)", r"\1", code)
    code = re.sub(r"\$_\b", "_", code)
    code = re.sub(r"[$@](\w+)", r"\1", code)
    return code


def _string(lit: str) -> str:
    """A Perl string literal as Python: double-quoted strings interpolate."""
    if lit.startswith("'"):
        if "$" in lit:  # code in a string, for seek_file's offset and condition
            return "'" + _code(lit[1:-1]) + "'"
        return lit
    body = lit[1:-1]
    if not re.search(r"[$@]", body.replace("\\$", "").replace("\\@", "")):
        return lit
    body = body.replace("{", "{{").replace("}", "}}")
    body = re.sub(r"\$(?:::)?(\w+)", r"{\1}", body)
    return 'f"' + body + '"'


def _ranges(code: str) -> str:
    return re.sub(r"\(\s*([^()]+?|\([^()]*\))\s*\.\.\s*(\([^()]*\)|[^()]+?)\s*\)",
                  r"range(\1, \2 + 1)", code)  # fmt: skip


def _maps(code: str) -> str:
    # [ map { EXPR } (LIST) ]  and  map { EXPR } (LIST)
    code = re.sub(r"\[\s*map\s*\{(.*)\}\s*(range\(.*\)|\(.*\))\s*\]", r"[\1 for _ in \2]", code)
    code = re.sub(r"\bmap\s*\{(.*)\}\s*(range\(.*\)|\(.*\))", r"[\1 for _ in \2]", code)
    return code


def _operators(code: str) -> str:
    code = re.sub(r"&&", " and ", code)
    code = re.sub(r"\|\|", " or ", code)
    code = re.sub(r"!(?!=)", " not ", code)
    code = re.sub(r"\beq\b", "==", code)
    code = re.sub(r"\bne\b", "!=", code)
    return code


# Perl operators whose operands are integers, and the helpers that do the same
_INTEGER_OPS = {ast.Mod: "pmod", ast.BitAnd: "pand", ast.BitOr: "por", ast.BitXor: "pxor",
                ast.LShift: "pshl", ast.RShift: "pshr"}  # fmt: skip


def _integer_ops(code: str) -> str:
    """Rewrite %, &, |, ^, << and >> as calls to helpers with Perl's integer semantics.

    Only those expressions change; the rest of the text is kept as written.
    """
    if not re.search(r"%|&|\||\^|<<|>>", _strip_strings(code)) or "\n" in code:
        return code
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # still Perl; it will be marked for review
    src = code.encode()

    def needs(node) -> bool:
        return any(isinstance(n, ast.BinOp) and type(n.op) in _INTEGER_OPS for n in ast.walk(node))

    def span(node) -> tuple[int, int]:
        return node.col_offset, node.end_col_offset

    def render(node) -> bytes:
        if isinstance(node, ast.BinOp) and type(node.op) in _INTEGER_OPS:
            fn = _INTEGER_OPS[type(node.op)].encode()
            return fn + b"(" + render(node.left) + b", " + render(node.right) + b")"
        start, end = span(node)
        text = src[start:end]
        for child in sorted(
            (c for c in ast.iter_child_nodes(node) if hasattr(c, "col_offset") and needs(c)),
            key=lambda c: c.col_offset,
            reverse=True,
        ):
            cs, ce = span(child)
            text = text[: cs - start] + render(child) + text[ce - start :]
        return text

    out = src
    for stmt in sorted(tree.body, key=lambda n: n.col_offset, reverse=True):
        if needs(stmt):
            s0, e0 = span(stmt)
            out = out[:s0] + render(stmt) + out[e0:]
    return out.decode()


def _code(code: str) -> str:
    return _operators(_maps(_ranges(_variables(code))))


def _finish(code: str) -> str:
    return _integer_ops(code)


def _concat_pieces(s: str) -> list[str]:
    """s split at Perl's string-concatenation operator (.), outside strings and brackets.

    A dot next to a digit is part of a number, and ".." is a range.
    """
    pieces, depth, start, i, quote = [], 0, 0, 0, None
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "." and depth == 0:
            before, after = s[i - 1 : i], s[i + 1 : i + 2]
            if "." not in (before, after) and not (before.isdigit() or after.isdigit()):
                pieces.append(s[start:i])
                start = i + 1
        i += 1
    pieces.append(s[start:])
    return pieces


def _translate(s: str) -> str:
    pieces = _concat_pieces(s)
    if len(pieces) > 1:  # Perl's . joins strings, and numbers as text
        return "cat(" + ", ".join(_translate(p.strip()) for p in pieces) + ")"
    out = []
    for piece, is_string in _split_code(s):
        out.append(_string(piece) if is_string else _code(piece))
    return "".join(out)


def _increments(stmt: str) -> str:
    """x++ / ++x / x-- / --x as assignments."""
    m = re.fullmatch(r"\s*(?:(\+\+|--)\s*(\S+?)|(\S+?)\s*(\+\+|--))\s*", stmt)
    if not m:
        return stmt
    op = m.group(1) or m.group(4)
    target = m.group(2) or m.group(3)
    return f"{target} = {target} {'+' if op == '++' else '-'} 1"


def _statements(s: str) -> list[str]:
    parts, depth, cur, quote = [], 0, "", None
    for ch in s:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _modifier(stmt: str, *, as_expression: bool) -> str:
    """Perl's `STATEMENT if CONDITION`."""
    m = re.fullmatch(r"(.+?)\s+if\s+(.+)", stmt)
    if not m or " else " in stmt:
        return _increments(stmt)
    body, cond = _increments(m.group(1)), m.group(2)
    if not as_expression:
        return f"if {cond}: {body}"
    a = re.fullmatch(r"(\w+(?:\.\w+)*)\s*=\s*(.+)", body)
    if a:
        return f"{a.group(1)} = {a.group(2)} if {cond} else {a.group(1)}"
    return f"({body}) if ({cond}) else None"


def _print(stmt: str) -> str:
    m = re.fullmatch(r"print\s+STDERR\s+(.+?)((?:\s+if\s+.+)?)", stmt)
    if not m:
        return stmt
    return f'print({m.group(1)}, file=stderr, end=""){m.group(2)}'


def expr(field: str) -> str:
    """A Perl item field (an expression, or statements whose last value counts)."""
    stmts = [_translate(_print(s)) for s in _statements(field)]
    return _finish("; ".join(_modifier(s, as_expression=True) for s in stmts))


def statement(line: str) -> str:
    """A Perl statement line (run once)."""
    code, comment = _split_comment(line)
    stmts = [_translate(_print(s)) for s in _statements(code)]
    new = _finish("; ".join(_modifier(s, as_expression=False) for s in stmts))
    return new + (f"  {comment}" if comment else "")


def _split_comment(line: str) -> tuple[str, str]:
    """Code and a trailing # comment (outside strings)."""
    pos = 0
    for piece, is_string in _split_code(line):
        if not is_string and "#" in piece:
            i = pos + piece.index("#")
            return line[:i].rstrip(), line[i:]
        pos += len(piece)
    return line, ""

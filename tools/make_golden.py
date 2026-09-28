#!/usr/bin/env python3
"""Run the legacy Perl tools over the golden cases and save their output.

    python tools/make_golden.py pick            # regenerate pick's golden files
    python tools/make_golden.py --check         # verify all tools' files are current
    python tools/make_golden.py pick -k bits    # only cases whose id contains "bits"
    python tools/make_golden.py pick --fixes    # rewrite hand-maintained fix outputs
                                                # from the Python version (review the diff!)

See tests/golden_cases.py for the case format. Cases that don't run the Perl
(mirror cases and hand-maintained fix cases) are never overwritten.

Two adjustments make the Perl a reference for pick's intended behavior:

- Big-host cases run a copy of pick patched to unpack data as big-endian,
  which is how pick behaved on the big-endian machines it was written for.
  On little-endian machines its bit fields and byte-order-dependent formats
  come out wrong (see CHANGELOG).
- pick's -l and -n options did the reverse of their documentation. The
  Python version follows the documentation, so the letters are swapped in the
  arguments given to the Perl.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from golden_cases import GOLDEN, TESTS, Case, load_cases, load_index, normalize_stderr  # noqa: E402

TOOLS = ["pick", "recs", "recl", "tgen"]
LEGACY = ROOT / "legacy"
ORACLE_DIR = ROOT / "build" / "oracle"

# pick's Perl unpack letter for each data type, and its big-endian equivalent.
_PICK_TYPES_NATIVE = (
    "%tTypes=( S=>'a', A=>'a', b=>'C', c=>'a', s=>'s', w=>'S', \n"
    "          u=>'I', i=>'i', f=>'f', d=>'d', z=>'f', Z=>'d' ); "
)
_PICK_TYPES_BIG = (
    "%tTypes=( S=>'a', A=>'a', b=>'C', c=>'a', s=>'s>', w=>'S>', \n"
    "          u=>'I>', i=>'i>', f=>'f>', d=>'d>', z=>'f>', Z=>'d>' ); "
)


def big_host_pick() -> Path:
    """Write pick patched to behave as on a big-endian machine; return its path."""
    src = (LEGACY / "pick" / "pick").read_text(encoding="latin-1")
    if _PICK_TYPES_NATIVE not in src:
        sys.exit("legacy pick changed: can't find its %tTypes table to patch")
    patched = src.replace(_PICK_TYPES_NATIVE, _PICK_TYPES_BIG)
    # The usage text prints $0; keep it identical to the unpatched script's.
    patched = patched.replace("perldoc $0", "perldoc ../legacy/pick/pick")
    ORACLE_DIR.mkdir(parents=True, exist_ok=True)
    out = ORACLE_DIR / "pick-big-host"
    out.write_text(patched, encoding="latin-1")
    return out


_OPTION = re.compile(r"^-[a-zA-Z]+$")


def swap_nl(args: list[str]) -> list[str]:
    """Swap the n and l option letters (pick's options are -letters after the first word)."""
    table = str.maketrans("nl", "ln")
    return [a if i == 0 or not _OPTION.match(a) else a.translate(table) for i, a in enumerate(args)]


def flip_r(args: list[str]) -> list[str]:
    """Switch pick's -r option: remove it where given, otherwise add it."""
    if any(i and _OPTION.match(a) and "r" in a for i, a in enumerate(args)):
        out = []
        for i, a in enumerate(args):
            if i and _OPTION.match(a) and "r" in a:
                a = a.replace("r", "")
                if a == "-":
                    continue
            out.append(a)
        return out
    return [*args, "-r"]


def oracle_command(tool: str, case: Case) -> tuple[str, list[str]]:
    """The script (relative to tests/) and arguments to run for a case."""
    args = case.perl_args if case.perl_args is not None else case.args
    # Relative paths, because pick's usage text prints $0 and the golden
    # output must not depend on where the repo is checked out.
    script = os.path.relpath(LEGACY / tool / tool, TESTS)
    if tool == "pick":
        args = swap_nl(args)
        if case.host == "big" or case.oracle == "big-host-r":
            script = os.path.relpath(big_host_pick(), TESTS)
        if case.oracle == "big-host-r":
            args = flip_r(args)
    elif case.host != "little":
        sys.exit(f"{tool}/{case.id}: only pick cases can set host")
    return script, args


def run_perl(tool: str, case: Case) -> tuple[bytes, int, list[str]]:
    perl = shutil.which("perl")
    if not perl:
        sys.exit("perl is required to generate golden files")
    script, args = oracle_command(tool, case)
    p = subprocess.run(
        [perl, "-I", "../legacy", script, *args],
        input=case.stdin_bytes(),
        capture_output=True,
        cwd=TESTS,
        env={**os.environ, **case.env},
        timeout=20,
        check=False,
    )
    out, err = p.stdout, normalize_stderr(p.stderr.decode("latin-1"))
    if tool == "recs":
        # recs printed its warnings (via Util::Msg, with caller info) into
        # stdout, in the middle of the records; they belong on stderr.
        warnings = [m.decode() for m in _RECS_WARN.findall(out)]
        out = _RECS_WARN.sub(b"", out)
        err += warnings
    if case.perl_sub:
        out = out.replace(bytes.fromhex(case.perl_sub[0]), bytes.fromhex(case.perl_sub[1]))
    return out, p.returncode, err


_RECS_WARN = re.compile(
    rb"WARN \d{5}_\S+ (Matched bytes \(\d+\) is larger than mml parameter \(\d+\))\n"
)


def python_output(tool: str, case: Case) -> tuple[bytes, int]:
    """Run the Python version of a tool in-process, as the tests do."""
    import importlib
    import io

    from telemetry_cli import __version__

    main = importlib.import_module(f"telemetry_cli.{tool}.cli").main
    saved_env, saved_cwd = dict(os.environ), os.getcwd()
    try:
        os.chdir(TESTS)
        os.environ.pop("PICKPATH", None)
        os.environ.update(case.env)
        out = io.BytesIO()
        code = main(
            case.args,
            stdin=io.BytesIO(case.stdin_bytes()),
            stdout=out,
            stderr=io.StringIO(),
            **({"host_order": case.host} if tool == "pick" else {}),
        )
    finally:
        os.chdir(saved_cwd)
        os.environ.clear()
        os.environ.update(saved_env)
    # help text shows the version; store a placeholder
    return out.getvalue().replace(__version__.encode(), b"VERSION"), code


def write_fixes(tool: str, pattern: str | None) -> int:
    d = GOLDEN / tool
    index = load_index(tool)
    n = 0
    for case in load_cases(tool):
        if case.runs_perl or case.mirror or case.error or (pattern and pattern not in case.id):
            continue
        out, code = python_output(tool, case)
        (d / f"{case.id}.out").write_bytes(out)
        index[case.id] = {"exit": code, "stderr": []}
        n += 1
    (d / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    print(f"{tool}: wrote {n} hand-maintained outputs from the Python version")
    return 0


def process(tool: str, pattern: str | None, check: bool) -> int:
    d = GOLDEN / tool
    all_cases = load_cases(tool)
    cases = [c for c in all_cases if not pattern or pattern in c.id]
    old = load_index(tool)
    index = dict(old)
    problems = 0
    for case in cases:
        out_file = d / f"{case.id}.out"
        if not case.runs_perl:
            if not (case.mirror or case.error) and (case.id not in old or not out_file.exists()):
                print(f"{tool}/{case.id}: fix case has no hand-written expected output")
                problems += 1
            continue
        out, code, err = run_perl(tool, case)
        entry = {"exit": code, "stderr": err}
        if check:
            if old.get(case.id) != entry or not out_file.exists() or out_file.read_bytes() != out:
                print(f"{tool}/{case.id}: golden output is stale")
                problems += 1
        else:
            out_file.write_bytes(out)
            index[case.id] = entry
    if not check:
        if not pattern:  # drop entries for cases that no longer exist or no longer run perl
            keep = {c.id for c in all_cases if not c.mirror}
            for stale in set(index) - keep:
                del index[stale]
            for f in d.glob("*.out"):
                if f.stem not in keep:
                    f.unlink()
        (d / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
        print(f"{tool}: {len(cases)} cases ({sum(c.runs_perl for c in cases)} run through perl)")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tools", nargs="*", metavar="tool", help=f"one of {', '.join(TOOLS)}")
    ap.add_argument("-k", dest="pattern", help="only cases whose id contains this")
    ap.add_argument("--check", action="store_true", help="verify instead of writing")
    ap.add_argument(
        "--fixes", action="store_true", help="write fix cases' outputs from the Python version"
    )
    a = ap.parse_args()
    if bad := set(a.tools) - set(TOOLS):
        ap.error(f"unknown tool(s): {', '.join(sorted(bad))}")
    tools = a.tools or [t for t in TOOLS if (GOLDEN / t).is_dir()]
    if a.fixes:
        return sum(write_fixes(t, a.pattern) for t in tools)
    problems = sum(process(t, a.pattern, a.check) for t in tools)
    if a.check:
        print("golden files are current" if not problems else f"{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

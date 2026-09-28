#!/usr/bin/env python3
"""Run the legacy Perl tools over the golden cases and save their output.

    python tools/make_golden.py pick            # regenerate pick's golden files
    python tools/make_golden.py --check         # verify all tools' files are current
    python tools/make_golden.py pick -k bits    # only cases whose id contains "bits"

See tests/golden_cases.py for the case format. Cases marked ``fix`` are
maintained by hand and are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from golden_cases import GOLDEN, TESTS, Case, load_cases, load_index, normalize_stderr  # noqa: E402

TOOLS = ["pick", "recs", "recl", "tgen"]


def run_perl(tool: str, case: Case) -> tuple[bytes, int, list[str]]:
    perl = shutil.which("perl")
    if not perl:
        sys.exit("perl is required to generate golden files")
    # A relative path, because pick's usage text prints $0 and the golden
    # output must not depend on where the repo is checked out.
    script = os.path.relpath(ROOT / "legacy" / tool / tool, TESTS)
    env = {**os.environ, **case.env}
    p = subprocess.run(
        [perl, "-I", "../legacy", script, *case.args],
        input=case.stdin_bytes(),
        capture_output=True,
        cwd=TESTS,
        env=env,
        timeout=60,
        check=False,
    )
    return p.stdout, p.returncode, normalize_stderr(p.stderr.decode("latin-1"))


def process(tool: str, pattern: str | None, check: bool) -> int:
    d = GOLDEN / tool
    cases = [c for c in load_cases(tool) if not pattern or pattern in c.id]
    old = load_index(tool)
    index = dict(old)
    problems = 0
    for case in cases:
        if case.fix:
            if case.id not in old or not (d / f"{case.id}.out").exists():
                print(f"{tool}/{case.id}: fix case has no hand-written expected output")
                problems += 1
            continue
        out, code, err = run_perl(tool, case)
        entry = {"exit": code, "stderr": err}
        out_file = d / f"{case.id}.out"
        if check:
            if old.get(case.id) != entry or not out_file.exists() or out_file.read_bytes() != out:
                print(f"{tool}/{case.id}: golden output is stale")
                problems += 1
        else:
            out_file.write_bytes(out)
            index[case.id] = entry
    if not check:
        if not pattern:  # drop entries for cases that no longer exist
            ids = {c.id for c in load_cases(tool)}
            for stale in set(index) - ids:
                del index[stale]
                (d / f"{stale}.out").unlink(missing_ok=True)
        (d / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
        print(f"{tool}: wrote {len(cases)} cases")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tools", nargs="*", metavar="tool", help=f"one of {', '.join(TOOLS)}")
    ap.add_argument("-k", dest="pattern", help="only cases whose id contains this")
    ap.add_argument("--check", action="store_true", help="verify instead of writing")
    a = ap.parse_args()
    if bad := set(a.tools) - set(TOOLS):
        ap.error(f"unknown tool(s): {', '.join(sorted(bad))}")
    tools = a.tools or [t for t in TOOLS if (GOLDEN / t).is_dir()]
    problems = sum(process(t, a.pattern, a.check) for t in tools)
    if a.check:
        print("golden files are current" if not problems else f"{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

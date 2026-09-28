"""Generated tgen golden cases. See tests/golden_cases.py for the format.

Each case names a Python command file, fixtures/tgen/NAME.tgen (made from the
Perl original by tgen --convert). tools/make_golden.py runs the Perl tgen on
the original, fixtures/tgen/perl/NAME.tgen, and turns -seed=N into srand(N):
both versions use Perl's drand48, so even random output must match.
"""

from __future__ import annotations

CASES: list[dict] = []


def add(id, args, **kw):
    CASES.append({"id": id, "args": list(args), **kw})


DETERMINISTIC = ["counter", "null_data", "arb_data", "calsweep", "subcom", "features", "files"]
RANDOM = ["random_size", "cond_fill", "valueV_value", "turing"]
FRAMES = {
    "one": [],
    "zero-means-one": ["0"],
    "ten": ["10"],
    "from-250": ["10", "250"],
    "from-million": ["3", "1000000"],
}

for name in DETERMINISTIC:
    for tag, frames in FRAMES.items():
        add(f"{name}-{tag}", ["-q", f"fixtures/tgen/{name}.tgen", *frames])
    add(f"{name}-fill", ["-q", "-f", "255", f"fixtures/tgen/{name}.tgen", "5"])
    add(f"{name}-random-fill", ["-q", "-r", "-seed=11", f"fixtures/tgen/{name}.tgen", "5"])

for name in RANDOM:
    for seed in (1, 42, 1996):
        add(f"{name}-seed{seed}", ["-q", f"-seed={seed}", f"fixtures/tgen/{name}.tgen", "40"])
        add(
            f"{name}-seed{seed}-r",
            ["-q", "-r", f"-seed={seed}", f"fixtures/tgen/{name}.tgen", "25"],
        )
    add(f"{name}-from-100", ["-q", "-seed=5", f"fixtures/tgen/{name}.tgen", "10", "100"])

# progress reports on stderr
add("notify-default", ["fixtures/tgen/counter.tgen", "250"])
add("notify-every-7", ["-n", "7", "fixtures/tgen/counter.tgen", "30", "3"])
add("notify-long-name", ["--notify=4", "fixtures/tgen/counter.tgen", "12"])
add("option-spellings", ["--fill=9", "-quiet", "fixtures/tgen/arb_data.tgen", "2"])
add("option-random-fill-long", ["--random_fill", "-seed", "3", "-q", "fixtures/tgen/arb_data.tgen"])

# errors
add("err-missing-file", ["fixtures/tgen/no-such-file.tgen"])
add("err-no-args", [], note="usage")
add("err-unknown-option", ["-z", "fixtures/tgen/counter.tgen"], fix="tgen options",
    error="Unknown option: z")  # fmt: skip

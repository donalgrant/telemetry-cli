"""Allow ``python -m telemetry_cli.recs``."""

import sys

from .cli import main

sys.exit(main())

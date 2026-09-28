"""Allow ``python -m telemetry_cli.pick``."""

import sys

from .cli import main

sys.exit(main())

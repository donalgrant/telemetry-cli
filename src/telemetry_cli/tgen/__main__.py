"""Allow ``python -m telemetry_cli.tgen``."""

import sys

from .cli import main

sys.exit(main())

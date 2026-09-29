"""Allow ``python -m telemetry_cli.recl``."""

import sys

from .cli import main

sys.exit(main())

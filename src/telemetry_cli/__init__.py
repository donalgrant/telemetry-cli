"""telemetry-cli: command-line tools for binary telemetry."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("telemetry-cli")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"

"""Event-driven real estate price tracking for Vietnamese listing sites.

Layers (dependencies point inwards only):
    domain -> application -> infrastructure -> entrypoints
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("real-estate-price-tracking-systems")
except PackageNotFoundError:  # running from a source checkout without installing
    __version__ = "0.0.0"

__all__ = ["__version__"]

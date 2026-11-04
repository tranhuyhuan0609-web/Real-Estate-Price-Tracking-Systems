"""Shared pytest fixtures. Test layout:

tests/unit/         fast, no I/O
tests/contract/     configuration and architecture rules
tests/integration/  real PostGIS / MongoDB / Kafka via testcontainers (marker: integration)
tests/fixtures/     captured, anonymised sample payloads
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

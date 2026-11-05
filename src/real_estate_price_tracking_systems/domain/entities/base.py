"""Shared building blocks for domain models."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""A string that is stripped and must not be empty afterwards."""


class StrictBaseModel(BaseModel):
    """Base for models built from YAML or payloads we own.

    ``extra="forbid"`` turns a typo in a field name into a validation error instead of a value
    that is silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

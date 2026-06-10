"""Shared Pydantic base models."""

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """Base model with strict, immutable defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")
